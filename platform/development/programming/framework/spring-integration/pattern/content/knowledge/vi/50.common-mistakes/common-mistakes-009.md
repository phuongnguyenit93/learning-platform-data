# Wire tap làm chậm hoặc lộ dữ liệu

## 1. Bối cảnh: quan sát flow nhưng vô tình ảnh hưởng hệ thống chính

Trong module **SPRING_INTEGRATION_PATTERN**, chúng ta học các *Enterprise Integration Patterns* của Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng và dễ kiểm thử. Khi ghép Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation thành một flow, nhu cầu **xem message đang đi đâu** là rất thực tế.

Spring Integration cung cấp **Wire Tap** để quan sát message đi qua một channel mà không cần thay đổi nghiệp vụ của consumer chính. Đội ngũ thường thêm Wire Tap để debug, ghi log, làm metrics hoặc kiểm tra các nhánh. Tuy nhiên, một tap cấu hình thiếu kiểm soát có thể gây **hai nhóm sự cố độc lập**:

1. **Làm chậm flow chính:** tap đưa message qua handler đồng bộ, truy vấn database, serialize payload lớn hoặc ghi log chậm. Thread gửi message phải làm thêm việc trước khi flow chính đi tiếp.
2. **Lộ dữ liệu:** tap đưa nguyên payload/headers vào log, tracing, queue, dịch vụ phân tích hoặc hệ thống bên thứ ba; trong đó có thể chứa token, thông tin cá nhân, số tài khoản, nội dung đơn hàng hoặc dữ liệu nhạy cảm khác.

Ví dụ, luồng `PaymentRequested` có thể chứa `commandId`, thông tin thanh toán và token xác thực của hệ thống đối tác. Tap dùng để đếm request không cần xem toàn bộ payload. Nếu cấu hình logger in `message.toString()` hoặc `headers` ở mức INFO, dữ liệu không cần thiết bị sao chép vào kho log với thời hạn lưu và phạm vi truy cập khác ứng dụng nghiệp vụ.

> **Nguyên tắc:** Wire Tap là **cơ chế sao nhánh quan sát**, không phải một lời hứa “chạy miễn phí”, “luôn bất đồng bộ” hay “được phép ghi tất cả message”. Muốn dùng an toàn phải thiết kế **kênh đích, ngân sách hiệu năng, phạm vi dữ liệu, xử lý lỗi và mục đích lưu trữ**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích Wire Tap hoạt động như `ChannelInterceptor` và vì sao tap đồng bộ có thể tăng độ trễ.
- Phân biệt tap để debug, đo metrics và hệ thống audit bắt buộc.
- Chọn `DirectChannel`, `ExecutorChannel`, queue hoặc broker đúng với mục tiêu quan sát và giao nhận.
- Thiết kế allowlist/redaction, ngăn rò rỉ payload, headers, secrets và dữ liệu cá nhân.
- Phát hiện backpressure, executor rejection, lỗi handler tap, log quá lớn và cấu hình global tap quá rộng.
- Kiểm thử đường nghiệp vụ và đường quan sát độc lập, kể cả khi tap chậm hoặc không hoạt động.

## 2. Wire Tap là gì trong Spring Integration?

Wire Tap là một **`ChannelInterceptor`** có thể đăng ký trên channel để gửi message đi qua đó tới một **tap channel** bổ sung. Luồng chính vẫn có điểm đến riêng. Trong Java DSL, có thể dùng toán tử `wireTap(...)`; toán tử `log(...)` cũng được hiện thực bằng một Wire Tap nối tới `LoggingHandler`.

```mermaid
flowchart LR
    A[Inbound event] --> C[Business input channel]
    C --> W[WireTap interceptor]
    W --> T[Tap channel]
    T --> L[Metrics / safe log / diagnostic]
    W --> B[Business handler]
    B --> N[Next business step]
```

**Chú ý:** Sơ đồ biểu diễn hai đường xử lý; **không** hàm ý rằng tap luôn chạy đồng thời với handler nghiệp vụ. Tính đồng bộ/bất đồng bộ đến từ **kiểu channel đích và executor**.

| Thành phần | Vai trò | Điều cần tránh hiểu nhầm |
| --- | --- | --- |
| `WireTap` | Intercept message và chuyển thêm một bản tới tap channel | Không tự tạo thread hoặc persistence. |
| `DirectChannel` đích | Gọi handler tap trên thread gửi theo dispatch đồng bộ | Tap chậm có thể làm tăng latency của flow chính. |
| `ExecutorChannel` đích | Dispatch handler tap trên executor | Không tự bảo đảm task không bị từ chối, dữ liệu được lưu hay logger không nghẽn. |
| `QueueChannel` đích | Buffer message chờ consumer/poller | Queue trong RAM không bền vững; đầy queue có thể gây backpressure hoặc send failure. |
| `LoggingHandler` / DSL `log()` | Ghi message theo level/category/expression | Mặc định có thể log payload; không phải bộ lọc dữ liệu nhạy cảm. |
| `MessageStore` / broker | Lưu message theo cơ chế được cấu hình | Không tự thay thế audit transaction hoặc chính sách bảo vệ dữ liệu. |

Wire Tap không nên được xem là bản sao độc lập đã được **deep-copy**: message Spring thường chứa headers không thay đổi sau khi tạo, nhưng **payload có thể là một đối tượng Java mutable**. Nếu một handler tap hoặc business handler sửa trực tiếp object payload, hai nhánh có thể thấy dữ liệu thay đổi hoặc xảy ra race khi chạy song song. Nên dùng immutable DTO, không mutate payload chung, hoặc tạo **diagnostic DTO riêng** trước khi truyền sang hệ thống quan sát.

### 2.1. Wire Tap không giống Publish-Subscribe Channel

`PublishSubscribeChannel` phân phối message cho nhiều subscriber như một chức năng chính của channel. Wire Tap là **một nhánh quan sát gắn với một channel có luồng chính**. Cả hai đều có thể gửi message tới nhiều thành phần và đều cần đánh giá đồng bộ, backpressure, lỗi và durability. Dùng Wire Tap không tự giải quyết bài toán “mỗi consumer nghiệp vụ phải nhận tất cả event kể cả khi offline”.

### 2.2. Tap chỉ thấy message ở vị trí được gắn

Một tap đặt **sau Filter** không thấy message Filter đã loại; một tap đặt trước Transformer thấy payload gốc; một tap sau Transformer thấy payload đã biến đổi. Nếu gắn global Wire Tap lên nhiều channel, **cùng một event có thể bị quan sát nhiều lần** theo hành trình của nó. Không lấy số lần tap handler được gọi làm số lượng giao dịch đã hoàn tất khi chưa xác định rõ điểm đặt.

## 3. Vì sao tap đồng bộ làm chậm flow chính?

Giả sử request đi qua `DirectChannel` và Wire Tap gửi message tới một tap channel cũng là `DirectChannel`. Khi intercept, đường tap gọi handler quan sát **đồng bộ** trước khi message tiếp tục đi qua consumer chính.

```mermaid
sequenceDiagram
    autonumber
    participant R as Request thread
    participant C as Channel + WireTap
    participant L as Tap handler (DirectChannel)
    participant B as Business handler
    R->>C: send(message)
    C->>L: tap.send(message)
    Note over R,L: Serialize/log/IO đồng bộ, giữ request thread
    L-->>C: Handler tap kết thúc
    C->>B: Giao message cho business handler
    B-->>R: Xử lý tiếp
```

Thời gian của request có thể tăng xấp xỉ theo công việc tap cộng thêm; độ trễ thực tế còn phụ thuộc cách dispatch, logger, contention và điểm đo. Nếu tap gọi một dịch vụ ngoài với timeout 2 giây, một flow nghiệp vụ vốn mất 50 ms có thể bị kéo dài đáng kể dù nghiệp vụ không cần dữ liệu tap để hoàn tất.

### 3.1. Những nguồn gây độ trễ phổ biến

| Nguồn chậm | Vì sao ảnh hưởng | Cách khắc phục |
| --- | --- | --- |
| Serialize toàn bộ object graph | Payload lớn, nested object, lazy-loading hoặc `toString()` nặng | Chỉ trích xuất trường allowlist nhỏ, định dạng cố định. |
| Ghi log sync ra đĩa/network | Appender hoặc collector có I/O chậm, lock nội bộ | Cân nhắc async logging có giới hạn; không coi async appender là durable. |
| Tap gọi HTTP/database | Thread chính chờ mạng/transaction | Đưa quan sát best effort sang bounded executor hoặc kiến trúc event bền vững riêng. |
| Quá nhiều global taps | Một message bị serialize/log nhiều lần trên nhiều channel | Thu hẹp channel pattern, sampling và tránh trùng điểm đo. |
| Tap chặn vì channel đầy | Buffer hết chỗ, hoặc executor hết khả năng nhận task | Đặt capacity, timeout/rejection policy rõ, đo queue depth. |
| Lock/CPU/GC | Tạo quá nhiều log string, JSON, stack trace | Giảm volume và kích thước event, đo CPU/heap/GC và latency. |

**Đo đúng:** hãy so sánh p50/p95/p99 latency và throughput của business flow **trước và sau** khi thêm tap, dưới cùng profile tải. Đo riêng thời gian tính projection/serialize và thời gian chờ vào tap channel; chỉ nhìn trung bình có thể che mất đuôi latency.

### 3.2. Async không tự động nghĩa là “không ảnh hưởng”

Nếu tap channel sử dụng executor, caller thường chỉ phải dispatch task rồi tiếp tục, nhưng **chi phí tạo task, kiểm tra queue, chọn handler và quản lý lỗi vẫn xảy ra**. Khi executor bão hòa, policy có thể:

- **Từ chối task** (ví dụ `AbortPolicy`) và làm phát sinh lỗi lúc dispatch.
- **Chạy trên thread caller** (ví dụ `CallerRunsPolicy`), đưa độ trễ tap quay lại đường chính.
- **Chờ hoặc buffer** tùy cấu hình, tăng độ trễ hoặc heap usage.
- **Bỏ task** với policy riêng, khiến dữ liệu quan sát bị mất nếu không có metrics/alert.

Vì thế lựa chọn async chỉ là **đổi điểm chịu tải**, không xóa chi phí hoặc đảm bảo delivery. Hãy ghi rõ liệu quan sát được phép mất dữ liệu (*best effort*) hay không.

## 4. Vì sao Wire Tap có thể làm lộ dữ liệu?

Một `Message<?>` có thể chứa thông tin nhạy cảm ở cả **payload** và **headers**. Ví dụ:

| Vị trí | Ví dụ có thể xuất hiện | Rủi ro nếu ghi toàn bộ |
| --- | --- | --- |
| Payload | Địa chỉ giao hàng, thông tin khách hàng, trường thanh toán, nội dung tài liệu | PII hoặc dữ liệu nghiệp vụ bị đưa sang hệ thống log ngoài phạm vi kiểm soát. |
| Headers | `Authorization`, cookie, API key, session ID, JWT, metadata đối tác | Lộ thông tin xác thực hoặc liên kết phiên. |
| Exception | URL có token, lỗi SQL chứa tham số, chuỗi raw response | Dữ liệu nhạy cảm xuất hiện trong stack trace hoặc message lỗi. |
| Serialized `toString()` | Object nested, trường mới thêm trong DTO | Vô tình mở rộng tập trường được log sau một lần thay đổi model. |
| Trace/baggage | Correlation ID, tên khách hàng, địa chỉ, metadata do upstream đưa vào | Metadata theo trace bị lan sang nhiều hệ thống và thời hạn lưu dài. |

Không cần ghi toàn bộ payload để nhận biết một flow đã đi qua channel nào. **Dữ liệu ít nhất cần thiết** cho mục tiêu quan sát thường chỉ gồm tên event, message ID, mã nhánh, kết quả xử lý, latency và một correlation ID đã được đánh giá độ nhạy.

### 4.1. Các anti-pattern về logging

```java
// PHẢN VÍ DỤ: chứa toàn bộ payload/headers, có thể có secrets.
logger.info("message={}", message);

// PHẢN VÍ DỤ: serialize mọi trường rồi đưa ra log collector.
logger.debug("payload={}", objectMapper.writeValueAsString(message.getPayload()));

// PHẢN VÍ DỤ: log tất cả HTTP/message headers.
logger.info("headers={}", message.getHeaders());
```

Tăng log level từ DEBUG lên INFO để debug production có thể làm lượng dữ liệu nhạy cảm bị ghi tăng đột biến. `LoggingHandler` với tùy chọn full-message đặc biệt nguy hiểm khi headers có thông tin xác thực. Không mặc định rằng log collector, tracing backend hoặc đội ngũ có quyền đọc log được phép xem tất cả dữ liệu nghiệp vụ.

### 4.2. “Mask bằng regex” chưa đủ

Regex che số thẻ hoặc token trong chuỗi log không chứng minh mọi dạng nested object, encoded payload, trường mới hoặc exception message đã được che. Với dữ liệu rủi ro cao, nên **allowlist trường có thể phát ra**, phân loại và xác thực schema trước khi serialize, rồi áp dụng redaction bổ sung như tuyến phòng thủ thứ hai. Kiểm thử dữ liệu đầu ra chứ không chỉ nhìn code che dữ liệu.

### 4.3. Hệ quả vận hành của việc lộ dữ liệu

Một payload đã vào hệ thống log có thể được sao chép sang dashboard, backup, alert, hệ thống tìm kiếm hoặc file tải về, mỗi nơi có thời hạn lưu và quyền truy cập khác nhau. Thiết kế tap cần xem xét **data classification, retention, encryption, access control, audit truy cập, môi trường staging/production và quy trình xóa dữ liệu**.

## 5. Ranh giới kiến trúc: diagnostic, tracing và audit không giống nhau

| Nhu cầu | Mức bảo đảm cần thiết | Cơ chế nên cân nhắc |
| --- | --- | --- |
| Debug luồng message tạm thời | Best effort, sampling, có thể tắt nhanh | Wire Tap với log an toàn hoặc kênh quan sát bounded. |
| Metrics vận hành | Có thể tổng hợp, không cần mọi payload | Counter/timer có nhãn cardinality thấp, ghi tại endpoint phù hợp. |
| Distributed tracing | Quan hệ giữa spans, correlation, latency | Instrumentation/observation và trace sampling; không ghi payload mặc định. |
| Audit nghiệp vụ bắt buộc | Không được mất quyết định/tác động quan trọng theo hợp đồng | Ghi audit cùng transaction hoặc transactional outbox + consumer bền vững. |
| Khôi phục nghiệp vụ sau restart | Dữ liệu và trạng thái durable | Broker có cấu hình durability, inbox/outbox, idempotent state machine. |

**Audit khác diagnostic log.** Nếu sau thanh toán bắt buộc có `PaymentSettledAudit`, việc chỉ Wire Tap vào logger/`ExecutorChannel` không đủ để bảo đảm audit được lưu. Nếu business transaction commit xong rồi ứng dụng crash trước khi tap publish, sự kiện audit có thể mất. Cần cơ chế ghi bền vững có ranh giới transaction và chính sách giao lại phù hợp.

Một audit log có thể chứa trường nhạy cảm nếu thực sự bắt buộc, nhưng phải có **data model tối thiểu và kiểm soát quyền truy cập độc lập**, không sao chép nguyên message để “đỡ phải thiết kế”.

## 6. Ví dụ Java DSL: Wire Tap chỉ quan sát một channel

Ví dụ sau tạo một luồng chính và một tap riêng. `businessIngress` và `businessRequests` là `DirectChannel`, còn `diagnosticTapInput` dùng `ExecutorChannel` để cách ly phần lớn thời gian xử lý log khỏi thread của flow chính. Dùng executor **có giới hạn** và chính sách từ chối rõ ràng.

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
public class BoundedDiagnosticTapConfig {

    @Bean
    public MessageChannel businessIngress() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel businessRequests() {
        return new DirectChannel();
    }

    @Bean
    public ThreadPoolTaskExecutor diagnosticExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("diagnostic-tap-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(200);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        // Spring quản lý vòng đời và initialize() của bean này.
        return executor;
    }

    @Bean
    public MessageChannel diagnosticTapInput(
            @Qualifier("diagnosticExecutor") ThreadPoolTaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    public IntegrationFlow businessFlowWithTap() {
        return IntegrationFlow.from("businessIngress")
                .wireTap("diagnosticTapInput")
                .channel("businessRequests")
                .get();
    }
}
```

Ví dụ cấu hình chỉ có ý nghĩa khi **các channel đích có consumer thực sự**. Thêm một `ServiceActivator` ở `businessRequests` để xử lý nghiệp vụ, và một handler ở `diagnosticTapInput` để ghi telemetry an toàn. Nếu chưa có subscriber cho `DirectChannel` đích, lời gọi gửi message có thể thất bại vì **cấu hình flow**, không phải do Wire Tap.

**Giới hạn cần hiểu:**

- `AbortPolicy` không làm message diagnostic được lưu lại: khi executor bão hòa, task có thể bị từ chối và ảnh hưởng thao tác send của flow chính. Đừng coi cấu hình trên là “fire-and-forget tuyệt đối”.
- Nếu đường quan sát được phép mất dữ liệu, ứng dụng cần chính sách xử lý rejections được thiết kế/test rõ thay vì để lỗi bất ngờ lan ngược; luôn đếm số task bị loại.
- Nếu audit bắt buộc, **không** giải quyết bằng cách chuyển sang policy lặng lẽ drop task; dùng outbox/broker durable.
- Dù dùng `ExecutorChannel`, message/payload được tham chiếu ở các thread khác nhau; tránh mutate object payload và tránh giữ object lớn không cần thiết trong queue.

### 6.1. Handler quan sát chỉ dùng trường allowlist

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class DiagnosticTapObserver {
    private static final Logger log =
            LoggerFactory.getLogger(DiagnosticTapObserver.class);

    @ServiceActivator(inputChannel = "diagnosticTapInput")
    public void observe(Message<?> message) {
        // Không log payload, không in headers.toString().
        // Phân loại giá trị header về một tập tên sự kiện đã cho phép.
        Object rawType = message.getHeaders().get("eventType");
        String type = switch (rawType instanceof String text ? text : "") {
            case "PAYMENT_REQUESTED" -> "PAYMENT_REQUESTED";
            case "PAYMENT_SETTLED" -> "PAYMENT_SETTLED";
            default -> "OTHER";
        };

        log.info("tap_event={} message_id={}",
                 type, message.getHeaders().getId());
    }
}
```

`MessageHeaders.ID` là ID của message do Spring tạo, không nhất thiết là ID nghiệp vụ cần dùng để correlate ACK. Nếu cần theo `commandId`, đánh giá trước mức nhạy cảm của định danh đó và chính sách log; không đưa token hoặc thông tin khách hàng vào log chỉ vì chúng nằm trong header.

Trong production, không nên để việc ghi log chậm, logging appender gặp lỗi hoặc lưu trace dài hạn trở thành yêu cầu bắt buộc của luồng thanh toán. Cần phân định **best effort diagnostics** với **business audit**.

## 7. Java DSL `log()` cũng có chi phí và nguy cơ rò rỉ

Trong Spring Integration DSL, toán tử `log()` được xây trên Wire Tap kết hợp với `LoggingHandler`. Vì thế nó **không mặc định tách sang một thread khác**.

```java
import org.springframework.integration.handler.LoggingHandler;

// Ví dụ đoạn giữa IntegrationFlow: chỉ log message ID.
.filter(...)
.log(LoggingHandler.Level.DEBUG,
     "app.integration.safe",
     message -> message.getHeaders().getId())
.route(...)
```

Ví dụ trên chỉ là **đoạn DSL đặt trong một flow đã có `filter(...)` và `route(...)`**, không phải file Java độc lập để biên dịch. Chọn expression cho phép chỉ ghi một ID không nhạy cảm thay vì đưa `payload` hoặc toàn bộ `headers` vào log.

### 7.1. `log()` ở cuối flow

`log()` là một operator quan sát. **Từ Spring Integration 6.0**, toán tử `log()` ở cuối flow được điều chỉnh để không làm thay đổi hành vi của flow so với khi bỏ toán tử; nếu cuối flow **không cần reply**, tài liệu khuyến nghị thêm `nullChannel()` sau `log()`. Với flow **cần reply**, phải thiết kế handler/channel trả kết quả đúng hợp đồng, không cho rằng thêm `log()` sẽ tự tạo reply để Gateway không timeout. Các phiên bản Java DSL cũ hơn có quy tắc terminal `log()`/`logAndReply()` khác, nên kiểm tra tài liệu đúng phiên bản đang dùng.

Với một luồng one-way thật sự không cần kết quả, có thể kết thúc flow sau log theo cấu hình tương ứng. Với một luồng trả kết quả tài chính, logging không được thay thế việc tạo output message.

### 7.2. Global Wire Tap cần đặc biệt thận trọng

`@GlobalChannelInterceptor` và global wire-tap có thể gắn lên nhiều channel theo pattern. Đây là công cụ mạnh để debug nhưng dễ:

- Log lặp cùng message tại 5–10 vị trí, tăng CPU/I/O và chi phí lưu.
- Chụp payload **trước khi** bước redaction/Transformer chạy.
- Quan sát cả channel chứa token, dữ liệu khách hàng, thông tin callback và lỗi.
- Vô tình áp dụng sang flow mới khi tên channel khớp pattern quá rộng.

Khi cần global tap, chọn tên channel rõ ràng, giới hạn môi trường và thời hạn bật, test pattern với danh sách channel đã được phép, kiểm soát mức log và quyền thay đổi cấu hình. Tránh pattern quá rộng như `*` trong production.

## 8. Tạo diagnostic event riêng thay vì chuyển nguyên Message ra ngoài

Ngay cả khi logger chỉ in hai trường, handler tap **vẫn nhận toàn bộ message gốc**. Nếu đường tap đi tới một broker, APM agent hoặc service của bên thứ ba, cần biến message thành **diagnostic event tối thiểu** trước khi vượt qua trust boundary.

Một mô hình dữ liệu đơn giản:

```java
import java.util.UUID;
import org.springframework.messaging.Message;

record TapObservation(
        UUID messageId,
        String eventType,
        boolean hasCorrelation) {
}

final class TapObservationProjector {
    private TapObservationProjector() {}

    static TapObservation from(Message<?> original) {
        Object rawType = original.getHeaders().get("eventType");
        String safeType = switch (rawType instanceof String text ? text : "") {
            case "PAYMENT_REQUESTED" -> "PAYMENT_REQUESTED";
            case "PAYMENT_SETTLED" -> "PAYMENT_SETTLED";
            default -> "OTHER";
        };

        boolean hasCorrelation =
                original.getHeaders().containsKey("correlationId");

        return new TapObservation(
                original.getHeaders().getId(),
                safeType,
                hasCorrelation);
    }
}
```

Lớp projector **không** đọc payload, `Authorization`, cookie hoặc các header ngoài allowlist. Nó chỉ phát ba trường đã được phê duyệt về mục đích quan sát. Khi cần lưu và truyền event ra ngoài, serialize **`TapObservation`**, không serialize `Message<?>` gốc.

Nếu muốn thêm `commandId`, `customerId`, `errorMessage` hoặc URL, cần được review như một thay đổi về dữ liệu: chúng có thể chứa thông tin nhạy cảm hoặc có cardinality cao. Với một số mục đích thống kê, chỉ cần biến Boolean `hasCorrelation` hay phân loại kết quả, không cần lưu giá trị ID thật.

**Lưu ý:** projector trong handler tap vẫn phải chạy ở nơi có quyền nhìn message gốc; một kiến trúc có yêu cầu bảo mật rất cao có thể phát diagnostic DTO **ngay tại producer hoặc sau bước sanitize** để không cho một thành phần quan sát chung nhận dữ liệu gốc.

## 9. Conditional Wire Tap và sampling

Spring Integration hỗ trợ **conditional wire tap** bằng `MessageSelector` hoặc `selector-expression`. Điều này hữu ích để quan sát những loại message được phép hoặc chỉ những sự kiện cần debug.

Ví dụ quy tắc có thể áp dụng:

```text
Được quan sát:
  - eventType=PAYMENT_REQUESTED
  - environment=staging
  - diagnosticEnabled=true

Không được quan sát:
  - eventType=SECRET_ROTATED
  - eventType=CUSTOMER_DOCUMENT_UPLOADED
  - payload chưa được phân loại độ nhạy
```

Đây là **quy tắc minh họa**, không phải cú pháp config đầy đủ. Nếu dùng selector, hãy bảo đảm:

- Selector **không** gọi dịch vụ ngoài, serialize toàn bộ payload hoặc gây side effect.
- Có chính sách mặc định **không tap** khi không xác định được phân loại dữ liệu.
- Sampling có giới hạn và đo rõ tỷ lệ mẫu để tránh hiểu nhầm thống kê.
- Không coi sampling là cách ghi audit bắt buộc: audit cần đủ sự kiện theo hợp đồng.
- Không bật debug động cho toàn bộ payment/personal-data flow chỉ vì có một lỗi nhỏ cần tìm.

### 9.1. Tránh double-counting

Nếu một `OrderCreated` đi qua `inboundChannel`, `normalizedChannel` và `dispatchedChannel`, một global tap có thể ghi ba “observation” cho cùng event. Để đo **số đơn đã tạo**, hãy tăng metric ở thời điểm transaction nghiệp vụ commit; để đo **số lần channel chuyển message**, đặt tên riêng và kèm `channel` với tập giá trị thấp.

## 10. Backpressure, lỗi tap và error channel

Wire Tap không thay thế kiến trúc xử lý lỗi. Các tình huống cần xem xét theo kiểu channel:

| Tap channel | Khi handler tap chậm | Khi handler tap ném lỗi | Hướng kiểm soát |
| --- | --- | --- | --- |
| `DirectChannel` | Có thể chặn sender thread | Exception có thể ảnh hưởng sender và flow chính | Không dùng handler có I/O chậm, hoặc chuyển quan sát ra ngoài đường chính. |
| `ExecutorChannel` | Task/queue tích tụ; tới giới hạn thì rejection | Exception trên worker đi theo cơ chế error handling bất đồng bộ | Bounded executor, metrics queue/reject, error flow, policy suy giảm rõ ràng. |
| `QueueChannel` trong RAM | Buffer tích tụ, tiêu thụ heap | Consumer/poller báo lỗi theo cấu hình | Capacity, poller, retry, cảnh báo và không nhận diện là persistence. |
| Broker adapter | Phụ thuộc publish confirm/ACK và network | Có thể lỗi transport và retry | Nếu audit cần bền vững, dùng outbox và delivery contract thích hợp. |

### 10.1. Đừng làm lỗi quan sát trở thành lỗi nghiệp vụ một cách vô ý

Một handler tap đồng bộ có thể ném exception khi logger, serializer hay database chậm. Nếu exception quay lại thread gửi, ứng dụng có thể đánh dấu **cả thanh toán** thất bại chỉ vì không ghi được diagnostic log. Đây là mức coupling không phù hợp cho best-effort observability.

Ngược lại, nếu tap thực sự thực hiện một **bước audit bắt buộc**, bỏ mọi exception cũng sai. Audit phải được đưa vào transaction hoặc durable event pipeline có chính sách nhất quán với nghiệp vụ. Mỗi tap phải có mục tiêu được ghi rõ:

- **Best effort:** chỉ giữ metrics/log tối thiểu, có thể giảm sampling hoặc bỏ một số observation khi quá tải, đồng thời đếm và cảnh báo.
- **Must deliver:** đưa event an toàn và tối thiểu vào state/outbox bền vững; consumer có retry, DLQ, idempotency, đối soát.

Không thể vừa bảo đảm “audit không bao giờ mất” vừa bảo đảm “tap không bao giờ ảnh hưởng latency” chỉ bằng việc đổi sang một `ExecutorChannel` trong RAM.

### 10.2. Error channel không tự đồng nghĩa redelivery

Trong các luồng bất đồng bộ, `ErrorMessage` có thể đi tới `errorChannel` để quan sát/điều phối lỗi. Việc có một error channel **không** đảm bảo event gốc còn trong broker, chưa ACK hoặc được tự retry. Với MessageSource/adapter/broker, cần kiểm tra riêng transaction, acknowledgement, offset, retry advice và DLQ.

### 10.3. Không “chữa” backpressure bằng buffer vô hạn

Khi tap handler xử lý chậm hơn tốc độ message tới, queue sẽ lớn dần. Một buffer vô hạn chỉ dời sự cố từ latency sang **tăng bộ nhớ, GC và OOM**. Cần quy định mức capacity, thời hạn xử lý backlog, chính sách từ chối và ngưỡng cảnh báo. Nếu cần backlog bền vững, dùng storage/broker với retention và năng lực vận hành phù hợp.

## 11. Bảo mật log và observability theo vòng đời dữ liệu

Một checklist trước khi bật Wire Tap trong production:

| Mục kiểm soát | Câu hỏi cần trả lời |
| --- | --- |
| Phân loại dữ liệu | Flow có chứa PII, thông tin tài chính, token, cookie, hồ sơ hoặc dữ liệu bên thứ ba không? |
| Mục đích | Tap phục vụ debug, metric, tracing hay audit bắt buộc? |
| Allowlist | Những trường nào được phép ra khỏi business boundary? |
| Thời hạn lưu | Log giữ bao lâu, khác gì dữ liệu nghiệp vụ gốc? |
| Quyền truy cập | Ai có thể xem log, dashboard, trace, file export và backup? |
| Mã hóa | Đường truyền tới collector và dữ liệu lưu có được bảo vệ theo chính sách không? |
| Lỗi/exception | Stack trace và exception message có chứa thông tin nhạy cảm hay không? |
| Thay đổi schema | Nếu DTO thêm trường mới, tap có tự ghi trường ấy không? |
| Môi trường | Staging, production, incident mode có chính sách bật log khác nhau không? |
| Incident response | Có thể tắt tap nhanh, tra cứu log đã xuất và xử lý sự cố lộ dữ liệu không? |

Đừng ghi token/credential dù chỉ trong môi trường test chia sẻ. Nếu buộc phải lưu một định danh để tìm dấu vết, xem xét mã định danh nội bộ không nhạy cảm hoặc token hóa/HMAC theo chính sách; không log trực tiếp email, số điện thoại hay ID khách hàng khi mục tiêu chỉ là đo số message.

Một khối log an toàn hơn:

```text
event=wiretap_observed
flow=payments
channel=normalizedPayments
messageType=PAYMENT_REQUESTED
hasCorrelation=true
observationSize=SMALL
```

Các dòng trên là **format minh họa do ứng dụng tự ghi**, không phải cấu hình logger mặc định. Các trường phải được gán từ tập giá trị được kiểm soát hoặc chuẩn hóa nhằm tránh log injection và cardinality cao.

## 12. Kiểm thử: chứng minh luồng chính không phụ thuộc vào bản sao quan sát

Kiểm thử cần bao gồm **đúng đường đi message**, **đúng phạm vi dữ liệu** và **hành vi khi tap lỗi**. Trước hết có thể kiểm thử fan-out với `QueueChannel` chỉ dùng trong test để nhận message từ hai nhánh.

### 12.1. Một cấu hình test cô lập

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class TapFanOutTestConfig {
    @Bean
    public MessageChannel testIngress() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel businessProbe() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel tapProbe() {
        return new QueueChannel(10);
    }

    @Bean
    public IntegrationFlow testTapFlow() {
        return IntegrationFlow.from("testIngress")
                .wireTap("tapProbe")
                .channel("businessProbe")
                .get();
    }
}
```

Hai `QueueChannel` trong test chỉ là **điểm nhận có giới hạn để kiểm tra**, không phải thiết kế production và không chứng minh durability.

### 12.2. Spring integration test cho hai nhánh

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TapFanOutTestConfig.class)
class TapFanOutTest {

    @Autowired @Qualifier("testIngress")
    MessageChannel ingress;

    @Autowired @Qualifier("businessProbe")
    QueueChannel business;

    @Autowired @Qualifier("tapProbe")
    QueueChannel diagnostic;

    @Test
    void observesMessageWithoutRemovingItFromBusinessPath() {
        Message<String> input = MessageBuilder.withPayload("event")
                .setHeader("eventType", "PAYMENT_REQUESTED")
                .build();

        assertTrue(ingress.send(input));

        Message<?> businessReceived = business.receive(1_000);
        Message<?> tapReceived = diagnostic.receive(1_000);

        assertNotNull(businessReceived);
        assertNotNull(tapReceived);
        assertEquals(input.getHeaders().getId(),
                     businessReceived.getHeaders().getId());
        assertEquals(input.getHeaders().getId(),
                     tapReceived.getHeaders().getId());
    }
}
```

Test này kiểm chứng một message được gửi vào hai đường ở **cấu hình thử nghiệm**. Nó chưa chứng minh tap bất đồng bộ không làm chậm, chưa đo độ trễ và chưa chứng minh dữ liệu được redacted.

### 12.3. Unit test của allowlist projector

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

class TapObservationProjectorTest {

    @Test
    void doesNotExportSensitivePayloadOrHeaders() {
        Message<Map<String, String>> sensitiveMessage =
                MessageBuilder.withPayload(Map.of(
                        "personalDocument", "synthetic-private-value",
                        "paymentToken", "synthetic-token-value"))
                .setHeader("Authorization", "Bearer synthetic-credential")
                .setHeader("eventType", "PAYMENT_REQUESTED")
                .setHeader("correlationId", "operation-42")
                .build();

        TapObservation observation =
                TapObservationProjector.from(sensitiveMessage);

        assertEquals("PAYMENT_REQUESTED", observation.eventType());
        assertTrue(observation.hasCorrelation());
        assertEquals(sensitiveMessage.getHeaders().getId(),
                     observation.messageId());

        String emitted = observation.toString();
        assertFalse(emitted.contains("synthetic-private-value"));
        assertFalse(emitted.contains("synthetic-token-value"));
        assertFalse(emitted.contains("synthetic-credential"));
        assertFalse(emitted.contains("operation-42"));
    }
}
```

Test sử dụng **giá trị mô phỏng**, không dùng credential thật. Muốn kiểm tra dữ liệu thực tế thoát ra khỏi hệ thống, cần test tại ranh giới serialize/logger/collector: kiểm tra JSON/log cuối cùng, cấu hình appender và cả exception paths.

### 12.4. Những trường hợp cần bổ sung

| Test case | Cách kiểm tra | Kết quả cần đạt |
| --- | --- | --- |
| Tap đồng bộ chậm | Dùng latch ở handler tap và đo đường gửi | Hiểu được điểm chặn và độ trễ, tránh giả định tap luôn async. |
| Tap async quá tải | Executor nhỏ, queue bounded, tạo burst có kiểm soát | Rejection/backpressure đúng policy, có metric và không thành lỗi nghiệp vụ bất ngờ. |
| Logging handler ném exception | Làm hỏng tap handler trong test | Error path đúng theo channel đồng bộ/bất đồng bộ. |
| PII trong payload | Dữ liệu mô phỏng chứa email/token | Dữ liệu nhạy cảm không có trong event serialize/log. |
| Secret trong headers | Header `Authorization`, cookie, token mô phỏng | Không bị serialize hoặc log bởi tap. |
| Flow có nhiều tap | Gắn tap tại các channel nối tiếp | Metrics không bị hiểu nhầm là số transaction nghiệp vụ. |
| Đổi schema | Thêm một trường nhạy cảm mới trong DTO | Allowlist không tự xuất thêm dữ liệu. |
| Broker/audit outage | Tạm dừng sink, kiểm tra outbox/backlog | Nếu audit bắt buộc thì event được lưu và khôi phục đúng. |
| Restart giữa publish | Fault injection trước/sau commit | Không suy từ Wire Tap rằng quan sát được bảo đảm durable. |

Các bài test hiệu năng nên thực hiện với cùng phiên bản build, workload, payload size và mức log. Test concurrency phải dùng điểm đồng bộ có thể quan sát được thay vì `Thread.sleep()` đoán thứ tự.

## 13. Observability và các dấu hiệu tap đang gây hại

Một bảng dashboard hữu ích không chỉ theo dõi số message mà cần cho thấy **tác động của đường tap lên business flow**:

| Chỉ số | Tại sao cần |
| --- | --- |
| Business p95/p99 latency | Phát hiện độ trễ tăng sau khi bật Wire Tap hoặc logging. |
| Tap enqueue/dispatch duration | Phát hiện sender bị chặn ở điểm gửi vào kênh quan sát. |
| Tap handler duration | Xem serializer, formatter, logger, network có chậm không. |
| Tap queue depth / oldest age | Phát hiện backlog và nguy cơ OOM. |
| Executor active threads / rejected tasks | Phát hiện quá tải và policy đang tác động. |
| Tap error / dropped observation count | Xác định dữ liệu quan sát không đầy đủ. |
| Log bytes per second / ingestion errors | Đo chi phí và nguy cơ quá tải collector. |
| Redaction policy violations | Phát hiện dữ liệu chưa được phép lọt vào event/log. |
| Audit outbox lag | Với audit bắt buộc, đánh giá việc lưu/phát sự kiện bền vững. |

Không dùng `traceId`, `commandId`, email hoặc raw URL có tham số làm nhãn cho mọi metric: cardinality sẽ tăng và có nguy cơ lộ dữ liệu. Chúng có thể xuất hiện trong log/trace **sau khi được phê duyệt và xử lý an toàn**; metric nên dùng tên flow/channel/event type đã được kiểm soát.

### 13.1. Dấu hiệu cần điều tra

- p99 latency tăng ngay sau khi nâng log level.
- CPU/GC tăng, log volume đột biến khi thêm `toString()` hoặc serialize JSON.
- Executor diagnostic hết queue, rejected count tăng.
- Một lỗi logger hoặc collector làm business request thất bại.
- Dashboard hiển thị nhiều “payment processed” hơn số giao dịch đã commit vì tap nhiều channel.
- Event mới chứa trường token nhưng log schema lại tự động in toàn bộ payload.
- ErrorMessage có raw exception text lộ URL, token hoặc thông tin khách hàng.

Nên có cách **tắt/giảm tap nhanh** khi incident, nhưng phải xác định trước đâu là dữ liệu được phép mất (diagnostics) và đâu là audit bắt buộc không thể bỏ.

## 14. Lộ trình sửa một Wire Tap đang gây sự cố

Nếu production đã gặp latency cao hoặc rò rỉ dữ liệu từ tap, có thể xử lý theo thứ tự sau:

1. **Xác định phạm vi:** liệt kê flow/channel bị tap, cấu hình global patterns, operator `log()` và những logging adapter đang hoạt động.
2. **Khoanh loại dữ liệu:** đánh dấu những payload/headers có PII, payment data, credential, token hoặc thông tin đối tác.
3. **Đánh giá ảnh hưởng:** đo latency và log volume trước/sau bật tap; quan sát thread dump, executor, queue và collector.
4. **Chặn rò rỉ:** tắt logging full message ở nơi không được phép; áp allowlist và hạn chế truy cập dữ liệu log đã xuất theo quy trình ứng phó sự cố.
5. **Tách trách nhiệm:** debug/metrics best effort đi qua đường quan sát có giới hạn; audit bắt buộc được ghi bằng transaction/outbox.
6. **Giới hạn tải:** cấu hình executor/buffer bounded và policy khi quá tải được test; không giấu lỗi bằng cách bỏ mọi exception.
7. **Giảm volume:** giới hạn tap vào channel cần quan sát, dùng selector/sampling có kiểm soát, tránh trùng điểm đo.
8. **Kiểm thử regression:** dữ liệu mô phỏng nhạy cảm, thay đổi schema, tap lỗi, restart và benchmark p95/p99.
9. **Theo dõi sau triển khai:** đo queue, rejection, log ingestion, policy violations và độ trễ nghiệp vụ.

Đừng chuyển toàn bộ tap sang async chỉ vì “có vẻ nhanh hơn” rồi bỏ qua chi phí bảo vệ thông tin. Async là giải pháp điều phối tải; **data minimization** mới là nguyên tắc kiểm soát dữ liệu phát ra.

## 15. Bài thực hành: chẩn đoán và thay thế tap trong payment flow

Một API thanh toán có flow:

```text
paymentInput
  -> validate
  -> log(fullMessage)
  -> route(provider)
  -> call payment adapter
  -> reply Gateway
```

Khi tăng traffic, p99 tăng; đồng thời hệ thống log có bản ghi `Authorization` và trường token từ payload. Hãy thực hiện:

1. Vẽ vị trí tap và xác định handler/log appender nào có thể chặn request thread.
2. Chỉ ra vì sao `log(fullMessage)` nguy hiểm, kể cả khi message được truyền qua channel đúng.
3. Viết lại operator log chỉ ghi message ID hoặc `TapObservation` allowlist.
4. Tạo bounded `ExecutorChannel` cho diagnostics; xác định rõ behavior khi executor bị từ chối task.
5. Nếu audit thanh toán bắt buộc, thiết kế outbox riêng và chứng minh không phụ thuộc vào diagnostic tap.
6. Tạo DTO immutable cho message, tránh handler tap sửa payload mà Router/Transformer chính đang dùng.
7. Kiểm thử với header `Authorization` và token mô phỏng; kiểm tra output cuối cùng của serializer/logger không chứa giá trị đó.
8. Tạo benchmark khi tap bật/tắt, so sánh business p95/p99 và tap queue depth.
9. Cho logger/collector chậm rồi lỗi; kiểm tra đường business và error flow theo chính sách đã chọn.
10. Thêm metrics diagnostic drop/rejection, audit backlog và cảnh báo khi policy logging thay đổi.

**Câu hỏi tự đánh giá**

- Vì sao Wire Tap không tự chạy bất đồng bộ dù được gọi là “tap”?
- Nếu tap channel là `DirectChannel` còn handler gọi HTTP chậm, thread nào bị giữ?
- Vì sao `ExecutorChannel` không chứng minh audit message đã được lưu bền vững?
- Sự khác nhau giữa lỗi của tap và lỗi nghiệp vụ nên được biểu diễn thế nào?
- Vì sao chỉ log `message.toString()` có thể làm lộ nhiều trường hơn dự kiến?
- Tại sao redaction bằng regex không thay thế allowlist/schema review?
- Tại sao payload mutable có thể gây race khi hai nhánh xử lý song song?
- Nếu tap gắn trên ba channel, metrics đếm message có thể bị hiểu sai ra sao?
- Khi một event audit bắt buộc, outbox đóng cửa sổ mất message nào?

## 16. Tài liệu tham khảo

- [Spring Integration Reference — Configuring Message Channels: Wire Tap](https://docs.spring.io/spring-integration/reference/channel/configuration.html): nguyên lý `ChannelInterceptor`, tính đồng bộ theo channel, conditional/global wire tap và cấu hình target channel.
- [Spring Integration Reference — Java DSL: Wire Tap](https://docs.spring.io/spring-integration/reference/dsl/java-wiretap.html): toán tử `wireTap()` và vị trí thêm interceptor trong flow.
- [Spring Integration Reference — Java DSL: Operator log()](https://docs.spring.io/spring-integration/reference/dsl/java-log.html): `log()`, `LoggingHandler` và hành vi cuối flow từ phiên bản 6.0.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): hành vi exception ở channel đồng bộ/bất đồng bộ và `errorChannel`.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): các loại channel, dispatch, buffering và ranh giới đồng bộ.
- [Spring Framework Reference — Task Execution](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `ThreadPoolTaskExecutor`, giới hạn queue và quản lý thread pool.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): thực hành tránh ghi bí mật, thông tin nhạy cảm và kiểm soát log.

> **Ghi nhớ:** **Wire Tap quan sát một luồng, không được mặc nhiên làm chậm hoặc sao chép mọi dữ liệu của luồng đó.** Chọn tap channel theo ngân sách latency và độ tin cậy; thu hẹp vị trí/đối tượng quan sát, chỉ phát trường allowlist, kiểm soát executor/backpressure và tách audit bắt buộc sang một cơ chế bền vững. Cuối cùng phải kiểm thử cả hiệu năng lẫn dữ liệu thực tế rời khỏi ứng dụng.
