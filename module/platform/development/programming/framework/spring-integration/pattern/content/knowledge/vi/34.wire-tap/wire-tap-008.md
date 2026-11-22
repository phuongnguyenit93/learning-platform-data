# Ẩn payload nhạy cảm trong tap

**Chương:** Wire tap  
**Bài học:** Ẩn payload nhạy cảm trong tap  
**Phạm vi:** `SPRING_INTEGRATION_PATTERN` — sử dụng Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; kết hợp Wire Tap với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, kiểm thử và quan sát các nhánh xử lý.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **Wire Tap** hữu ích cho quan sát nhưng có thể vô tình sao chép dữ liệu bí mật sang log, metrics, trace, queue hoặc hệ thống giám sát.
2. Phân biệt **quan sát thông điệp gốc** và **phát thông điệp giám sát đã được tối thiểu hóa dữ liệu**; nhận biết rằng Wire Tap của Spring Integration không tự che payload.
3. Thiết kế danh sách cho phép (**allowlist**) cho trường audit; hạn chế sao chép toàn bộ headers hoặc `Message.toString()`.
4. Triển khai một luồng Spring Integration tạo **safe audit event** trước khi gắn `.wireTap()`, để tap chỉ thấy thông tin đã được chọn lọc.
5. Khi buộc phải tap luồng gốc, xác định đúng vùng tin cậy, ranh giới đồng bộ/bất đồng bộ, cách biến đổi dữ liệu ở điểm sớm nhất và các rủi ro còn lại.
6. Kiểm thử các đường rò rỉ gián tiếp qua exception, `errorChannel`, retry, DLQ, tracing và serialization; xác minh rằng payload nghiệp vụ chính không bị sửa.
7. Quy định retention, phân quyền, giới hạn nhãn metrics và điều kiện chấp nhận mất sự kiện giám sát.

## 2. Wire Tap giúp gì và rủi ro nằm ở đâu?

Trong Enterprise Integration Patterns, **Wire Tap** sao chép luồng thông điệp quan sát được sang một nhánh phụ, trong khi nhánh chính vẫn tiếp tục làm công việc của nó. Spring Integration cung cấp cơ chế Wire Tap qua `WireTap` channel interceptor và cách khai báo thuận tiện trong Java DSL như `.wireTap("tapChannel")`.

~~~mermaid
flowchart LR
    A["Inbound adapter"] --> C["businessInput"]
    C --> B["Business handler"]
    B --> D["Kết quả nghiệp vụ"]
    C -. "Wire Tap" .-> T["tapChannel"]
    T --> O["Logging / metrics / audit"]
~~~

Nhánh tap có thể giúp điều tra thông điệp đi qua từng điểm, đo lỗi, tính throughput và hỗ trợ correlation. Nhưng điều nguy hiểm là **message đi vào tap thường chính là message mà channel đang xử lý**; bản thân `WireTap` không đóng vai trò `Transformer` tự xóa bí mật.

Một message xử lý thanh toán có thể chứa:

- Payload: email khách hàng, thông tin tài khoản, token thanh toán, địa chỉ, ghi chú, số tiền.
- Headers: `Authorization`, `Cookie`, `apiKey`, metadata truy vết, mã người dùng, routing key hoặc đối tượng `replyChannel`.
- Error context: `MessagingException.getFailedMessage()`, exception message và stack trace có thể chứa thông điệp gốc hoặc trường nhạy cảm.

Nếu tap gửi nguyên message tới logging handler, dữ liệu trên có nguy cơ xuất hiện ở nơi lưu log, hệ thống quan sát, bản sao lưu và tài khoản truy cập log. Một luồng xử lý nghiệp vụ bảo mật **không đồng nghĩa** nhánh tap cũng có cùng mức kiểm soát truy cập và lưu giữ dữ liệu.

## 3. Chọn chính sách theo mức độ nhạy cảm

Điểm khởi đầu phải là **mục đích quan sát**, sau đó mới quyết định trường dữ liệu nào thực sự cần truyền.

| Nhóm dữ liệu | Ví dụ | Hướng xử lý mặc định trong tap |
|---|---|---|
| Bí mật xác thực | Mật khẩu, session cookie, JWT, API key, private key | **Không chuyển vào nhánh tap**, kể cả dạng mask từng phần nếu không có mục đích được phê duyệt. |
| Dữ liệu thanh toán | Số thẻ, mã bảo mật, account token, thông tin giao dịch chi tiết | Không log nguyên bản; chỉ phát tín hiệu nghiệp vụ tối thiểu phù hợp chính sách bảo vệ dữ liệu. |
| Dữ liệu nhận dạng | Email, số điện thoại, địa chỉ, tên, định danh cá nhân | Bỏ qua hoặc dùng tham chiếu đã được phân loại, có kiểm soát truy cập và retention. |
| Payload tự do | JSON body, lời nhắn, file CSV, lỗi kèm request body | Không dùng `toString()` hoặc dump toàn bộ payload; chọn một số trường an toàn đã xác định. |
| Metadata kỹ thuật | Loại sự kiện, phiên bản schema, kết quả, latency bucket, endpoint logical name | Có thể cho phép sau khi xét khả năng nhận dạng và cardinality. |
| ID/correlation | `eventId`, `correlationId`, trace ID | **Không mặc định là vô hại**; có thể liên kết tới cá nhân hoặc giao dịch; cân nhắc mã tham chiếu thay thế. |

Ví dụ yêu cầu quan sát “bao nhiêu thanh toán được xử lý, loại lỗi nào tăng” thường chỉ cần `operation=PAYMENT`, `outcome`, `errorCategory`, `durationBucket` và thời điểm. Không cần bản sao toàn bộ `PaymentRequest`.

**Allowlist an toàn hơn denylist.** Nếu chỉ liệt kê những trường bị cấm (`password`, `token`), một trường mới như `accessCredential` có thể đi vào log sau lần thay đổi schema tiếp theo. Với allowlist, trường mới mặc định không xuất hiện trong sự kiện giám sát.

## 4. Hai cách tap: raw message và safe event

### 4.1 Tap trực tiếp vào message nghiệp vụ

~~~mermaid
flowchart LR
    R["PaymentRequest có secret"] --> C["businessChannel"]
    C --> H["Payment handler"]
    C -. "Wire Tap" .-> T["rawTap"]
    T --> X["Redact / mask"]
    X --> L["Audit logger"]
~~~

Đây là mô hình thường gặp khi tap được đặt sẵn trên channel nghiệp vụ. **Redact ở handler phía sau tap không làm biến mất việc payload gốc đã đi vào `rawTap`**. Đường đi tới handler, `MessageChannel`, interceptor, thread queue, error flow hoặc log debug ở giữa vẫn có cơ hội nhìn thấy dữ liệu nhạy cảm. Nếu chính sách yêu cầu dữ liệu bí mật không rời vùng xử lý chính, mô hình này chưa đáp ứng.

### 4.2 Tạo safe event trước rồi mới tap

~~~mermaid
flowchart LR
    R["PaymentRequest: dữ liệu nhạy cảm"] --> P["Business processor trong vùng tin cậy"]
    P --> D["Business DB"]
    P --> M["Tạo SafeAuditEvent theo allowlist"]
    M --> S["safeAuditInput"]
    S --> A["Audit sink"]
    S -. "Wire Tap chỉ thấy SafeAuditEvent" .-> T["Metrics / tracing"]
~~~

Ở mô hình này, một thành phần có quyền xem dữ liệu gốc tạo ra **một đối tượng mới, tối thiểu hóa thông tin**. Chỉ đối tượng mới đi vào `safeAuditInput`; Wire Tap được gắn ở nhánh safe event, vì vậy payload gốc không cần đi qua nhánh quan sát.

Đây là lựa chọn phù hợp khi người viết log/metrics hoặc nhà cung cấp quan sát có quyền truy cập hạn chế. Nó cũng làm rõ rằng hành vi phát audit là **quyết định nghiệp vụ**; Wire Tap chỉ sao chép sự kiện audit đã an toàn sang các consumer phụ.

## 5. Java DSL: chống rò rỉ từ ngay thiết kế flow

Ví dụ một yêu cầu `CheckoutCommand` có `customerEmail` và `accessToken` chỉ dành cho service xử lý. Nhánh tap phải quan sát một `SafeAuditEvent` tách biệt.

### 5.1 Định nghĩa dữ liệu

~~~java
public record CheckoutCommand(
        String eventId,
        String customerEmail,
        String accessToken,
        long amountInCents) {
}

// Không có email, token, số tài khoản hoặc payload tự do.
public record SafeAuditEvent(
        String operation,
        String outcome,
        String failureCategory) {
}
~~~

`SafeAuditEvent` dùng các giá trị **tập hợp nhỏ và được quy định trước**, tránh đưa một mã lỗi tùy ý có thể chứa dữ liệu đầu vào vào `failureCategory`. Nếu cần liên kết từng yêu cầu, hãy dùng mã tham chiếu không suy ra trực tiếp từ dữ liệu cá nhân và xử lý quyền truy cập/retention như dữ liệu có khả năng liên kết.

### 5.2 Luồng nghiệp vụ tạo sự kiện đã lọc

Đoạn sau minh họa Spring Integration Java DSL; đã lược bỏ import thông dụng và giả định có một `CheckoutService` xử lý nghiệp vụ. Để đơn giản, ví dụ phát `CHECKOUT_COMPLETED` sau khi lời gọi xử lý trả về thành công.

~~~java
@Configuration
@EnableIntegration
public class SafeTapConfig {

    @Bean
    MessageChannel checkoutInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel safeAuditInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel safeTapMetrics(TaskExecutor auditExecutor) {
        return new ExecutorChannel(auditExecutor);
    }

    @Bean
    IntegrationFlow checkoutFlow(
            CheckoutService checkoutService,
            @Qualifier("safeAuditInput") MessageChannel auditInput) {

        return IntegrationFlow.from("checkoutInput")
                .handle(CheckoutCommand.class, (command, headers) -> {
                    checkoutService.process(command);

                    SafeAuditEvent safe = new SafeAuditEvent(
                            "CHECKOUT", "COMPLETED", "NONE");

                    // Chỉ đưa SafeAuditEvent lên audit channel.
                    auditInput.send(MessageBuilder.withPayload(safe).build());
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow auditFlow(SafeAuditRepository repository) {
        return IntegrationFlow.from("safeAuditInput")
                .wireTap("safeTapMetrics")
                .handle(SafeAuditEvent.class, (event, headers) -> {
                    repository.append(event);
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow auditMetricsFlow(AuditMetrics metrics) {
        return IntegrationFlow.from("safeTapMetrics")
                .handle(SafeAuditEvent.class, (event, headers) -> {
                    metrics.increment(event.operation(), event.outcome());
                    return null;
                })
                .get();
    }
}
~~~

Các giao diện `CheckoutService`, `SafeAuditRepository`, `AuditMetrics` và bean `auditExecutor` là thành phần ứng dụng cần cung cấp khi chạy ví dụ. `auditExecutor` nên có giới hạn số worker, queue và chính sách từ chối rõ ràng.

Điểm cần kiểm tra trong flow:

1. `checkoutInput` nhận `CheckoutCommand`; **không có Wire Tap trên channel này**.
2. Handler xử lý dữ liệu nhạy cảm trong thành phần có quyền truy cập phù hợp.
3. Handler chỉ tạo `SafeAuditEvent` với các trường đã được duyệt.
4. `.wireTap("safeTapMetrics")` được gắn trong flow **đầu vào đã được sanitization**; nhánh metrics chỉ nhận `SafeAuditEvent`.
5. Nhánh audit chính lưu bản ghi an toàn; nhánh metrics dùng executor để giảm công việc trực tiếp trên thread xử lý, nhưng vẫn phải xử lý đầy queue và rejection.

**Giới hạn của ví dụ:** thao tác nghiệp vụ và ghi audit ở đây không được minh họa như một transaction nguyên tử. Nếu nghiệp vụ đã commit nhưng `auditInput.send()` thất bại, trạng thái có thể là “nghiệp vụ thành công, audit thiếu”. Đối với audit bắt buộc và không được phép mất bản ghi, cần **transactional outbox** hoặc một cơ chế nhất quán với kho lưu trữ nghiệp vụ. Với telemetry best-effort, chính sách lỗi có thể cho phép bỏ qua có đo đếm. Quyết định này phải được nêu rõ trước khi triển khai.

### 5.3 Vì sao không chỉ dùng `WireTap` kèm selector?

Một `WireTap` có thể nhận `MessageSelector` để **chọn message nào được chuyển sang tap**. Selector giúp giảm lượng message nhưng không có nhiệm vụ biến đổi payload thành đối tượng đã ẩn dữ liệu.

Ví dụ một predicate chỉ chọn `operation=CHECKOUT` vẫn đưa **message được chọn** tới tap. Nếu nó chứa token, token vẫn có nguy cơ bị lộ. Cần thực hiện sanitization **trước khi bước quan sát tiếp nhận**, hoặc bảo đảm raw tap nằm hoàn toàn trong vùng tin cậy với chính sách kiểm soát chặt.

## 6. Trường hợp phải quan sát channel nghiệp vụ gốc

Có hệ thống cần một hook trên `businessChannel` để phát metric về số message ngay cả khi handler sau đó lỗi. Nếu không thể dời hook, có thể xây dựng một **`ChannelInterceptor` tùy biến tạo message giám sát đã lọc**, thay vì sử dụng `WireTap` mặc định để gửi nguyên message.

~~~java
public final class SafeTelemetryInterceptor implements ChannelInterceptor {

    private final MessageChannel safeTelemetryChannel;

    public SafeTelemetryInterceptor(MessageChannel safeTelemetryChannel) {
        this.safeTelemetryChannel = safeTelemetryChannel;
    }

    @Override
    public Message<?> preSend(
            Message<?> original,
            MessageChannel sourceChannel) {

        // Không log original, headers hoặc original.toString().
        String kind = original.getPayload() instanceof CheckoutCommand
                ? "CHECKOUT"
                : "OTHER";

        SafeAuditEvent safe =
                new SafeAuditEvent(kind, "RECEIVED", "NONE");

        safeTelemetryChannel.send(
                MessageBuilder.withPayload(safe).build());

        return original; // Giữ nguyên message nghiệp vụ.
    }
}
~~~

Đây là **interceptor mô phỏng mục đích quan sát của Wire Tap**, không phải `WireTap` chuẩn. Khác biệt quan trọng: nó **không gửi bản sao của raw message** tới nhánh telemetry; message mới chỉ có ba trường an toàn.

Có thể gắn interceptor vào `DirectChannel` đã tạo:

~~~java
@Bean
DirectChannel guardedCheckoutChannel(
        @Qualifier("safeTelemetryChannel") MessageChannel telemetry) {

    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new SafeTelemetryInterceptor(telemetry));
    return channel;
}
~~~

Một số điểm cần lưu ý:

- `preSend()` chạy trong đường gửi của channel; gọi `send()` tới telemetry có thể **block**, ném exception hoặc bị từ chối. Muốn telemetry best-effort, phải xử lý failure có chủ đích; không được âm thầm làm thay đổi trạng thái nghiệp vụ.
- Chỉ xác định **loại sự kiện cố định**, không lấy nội dung từ `original.toString()`, exception message hay giá trị header không rõ nguồn gốc.
- Khi cần audit có tính pháp lý, việc nuốt lỗi telemetry có thể không chấp nhận được; ưu tiên ghi bền vững cùng transaction hoặc outbox.
- Các interceptor khác trên cùng channel vẫn có thể thấy message gốc. **Quyền truy cập vào channel gốc phải được kiểm soát**; custom interceptor không tự ngăn được một logger khác đã cấu hình trên channel đó.

### 6.1 Dấu hiệu phải tránh trong mã

~~~java
// ANTI-PATTERN — không dùng cho message chứa dữ liệu nhạy cảm.
IntegrationFlow.from("checkoutInput")
        .wireTap("generalLogs") // Gửi original Message vào nhánh logs.
        .handle(checkoutService)
        .get();

// ANTI-PATTERN — sao chép toàn bộ headers từ message nhạy cảm.
Message<SafeAuditEvent> unsafeAudit =
        MessageBuilder.withPayload(new SafeAuditEvent(
                "CHECKOUT", "RECEIVED", "NONE"))
                .copyHeaders(originalMessage.getHeaders())
                .build();
~~~

Đoạn thứ hai trông như đã thay payload an toàn nhưng **headers còn nguyên**: các trường như token, cookie, ID khách hàng, trace baggage hoặc giá trị tùy biến khác có thể đi vào telemetry. Khi tạo `SafeAuditEvent`, ưu tiên tạo message **mới không copy headers**, rồi chỉ thêm những metadata đã xét duyệt.

## 7. Tối thiểu hóa dữ liệu khác với che một vài ký tự

Có ba mức xử lý thường được dùng, với rủi ro rất khác nhau.

| Biện pháp | Ví dụ | Giới hạn |
|---|---|---|
| **Omit** (bỏ trường) | Không phát `customerEmail` | Ít nguy cơ nhất khi trường không phục vụ mục tiêu quan sát. |
| **Redact** (thay bằng giá trị trung tính) | `customerEmail = "[REDACTED]"` | Vẫn có thể lộ tên trường, kiểu dữ liệu; dễ sai khi schema thay đổi. |
| **Pseudonymize** (thay bằng mã liên kết) | Mã nội bộ/opaque audit reference | Vẫn có thể là dữ liệu có khả năng liên kết; cần quản lý khóa, ánh xạ, retention và quyền truy cập. |

Nếu chỉ cần đo throughput, hãy chọn **omit**. Nếu cần phân biệt giao dịch để điều tra, sử dụng một **opaque reference** có giới hạn truy cập và không thể suy ra từ email hoặc số điện thoại. Băm thường (`SHA-256(email)`) không đủ để ẩn danh email: tập giá trị đầu vào có thể bị đoán và băm đối chiếu. Khi thật sự cần pseudonym ổn định, có thể xem xét HMAC với khóa được quản lý an toàn hoặc một bảng mapping tách biệt, tùy yêu cầu tổ chức.

**Mask không đồng nghĩa an toàn tuyệt đối.** Ví dụ số điện thoại giữ bốn số cuối có thể kết hợp với các log khác để tái nhận dạng. Ngay cả `correlationId`, `orderId` hay `traceId` có thể liên kết về khách hàng, nên chỉ đưa vào tap khi có nhu cầu cụ thể và đã đánh giá mức nhạy cảm.

## 8. Headers, exception và đường rò rỉ ít thấy

### 8.1 Headers

Headers của Spring Messaging có thể bao gồm metadata rất hữu ích như `MessageHeaders.ID`, `correlationId`, `replyChannel`, `errorChannel`, `contentType`, cùng các custom header. Tuy nhiên:

- Header do client đưa lên có thể chứa bí mật mà producer vô tình chuyển tiếp.
- Một header `Authorization` hay `Cookie` phải được coi là nhạy cảm ngay cả khi payload đã sạch.
- `MessageBuilder.copyHeaders(...)` có thể đưa lại dữ liệu nhạy cảm vào một message audit.
- `replyChannel`/`errorChannel` có thể chứa object/địa chỉ liên quan đến hạ tầng nội bộ, không nên serialize tùy ý ra ngoài.

Chỉ thêm các header **được allowlist** vào safe audit message. Không cần mang header kỹ thuật gốc sang log để đếm số message.

### 8.2 Exception và failedMessage

Spring Integration có thể phát `ErrorMessage` chứa `Throwable`. Khi exception là `MessagingException`, nó có thể giữ `getFailedMessage()`, tức message làm phát sinh lỗi, gồm payload và headers.

Vì vậy, những hành vi sau có thể làm rò rỉ dữ liệu dù luồng tap chính đã sanitize:

- Ghi `log.error("{}", errorMessage)` hoặc serialize cả `ErrorMessage`.
- Ghi exception kèm object message mà không kiểm soát cách `toString()` biểu diễn dữ liệu.
- Chuyển toàn bộ `failedMessage` vào DLQ/quarantine chung cho nhóm vận hành không được phép xem dữ liệu.
- Thêm payload hoặc thông tin nhận dạng vào span attributes, trace baggage hoặc MDC.
- Ghi phản hồi từ đối tác có echo lại request/token trong exception message.

Đường lỗi nên dùng một **error classifier** tạo bản ghi `SafeErrorSignal` chỉ có: tên logical endpoint, nhóm lỗi được định nghĩa trước, trạng thái retry, thời điểm, tham chiếu truy vết đã được phê duyệt. Nếu cần lưu message gốc để phục hồi, hãy đưa nó vào **kho quarantine an toàn với quyền truy cập và retention riêng**, không trộn với log thông thường.

### 8.3 Retry, replay và DLQ

Retry có thể làm cùng một message được tap nhiều lần. Vì vậy:

- Đếm message tap được **khác** đếm số business event duy nhất.
- Một retry có thể tái tạo Spring message với ID mới; muốn đánh dấu sự kiện trùng phải dùng event key ổn định.
- DLQ hoặc retry topic có thể giữ bản sao payload nhạy cảm lâu hơn kỳ vọng của primary store.
- Tracing hoặc metrics gắn `eventId` làm label có thể tạo high cardinality và tăng nguy cơ tái nhận dạng.

Nếu cần audit “đã xử lý bao nhiêu giao dịch duy nhất”, hãy xây dựng consumer idempotent cho safe events hoặc phép đếm dựa trên dữ liệu nghiệp vụ được phép sử dụng.

## 9. Tap đồng bộ, bất đồng bộ và lỗi ở nhánh phụ

Một Wire Tap là nhánh phụ về **mục đích**; nó không mặc định là bất đồng bộ về **thread**.

| Tap channel | Hành vi điển hình | Điều cần kiểm soát |
|---|---|---|
| `DirectChannel` | Tap handler có thể chạy trên thread đang gửi message. | Latency, exception lan ra luồng chính, phạm vi quyền truy cập. |
| `ExecutorChannel` | Giao xử lý tap cho executor. | Queue executor, rejection, số worker, error handler, shutdown. |
| `QueueChannel` | Giữ message cho poller xử lý sau. | Dung lượng, tồn tại trong bộ nhớ hay persistent store, dữ liệu nhạy cảm nằm chờ. |
| Outbound adapter/broker | Phát dữ liệu tới hệ thống khác. | Header mapping, encryption, retention, auth, ACK/confirm, các bản sao lưu. |

Dùng `ExecutorChannel` cho tap có thể giảm tác động latency của consumer, nhưng executor đầy sẽ tạo lỗi/rejection; queue không giới hạn có thể tăng memory. Không coi việc có async boundary là bằng chứng log an toàn.

**Lựa chọn theo tính chất dữ liệu:**

- **Telemetry best-effort:** định nghĩa rõ có thể mất một số bản ghi; dùng bounded executor, metric báo mất dữ liệu và kiểm soát ảnh hưởng lên luồng chính.
- **Audit bắt buộc:** cần lưu bền vững và chứng minh tính đầy đủ, thứ tự, nhất quán theo phạm vi; cân nhắc transactional outbox hoặc giao dịch phù hợp, không dựa vào Wire Tap in-memory thuần.
- **Điều tra lỗi có payload gốc:** dùng kho bằng chứng hạn chế truy cập, mã hóa, TTL và quy trình mở quyền rõ ràng thay vì phát raw payload sang kênh quan sát chung.

## 10. Router, Filter, Transformer, Splitter và Aggregator ảnh hưởng thế nào?

### 10.1 Router và Filter

Wire Tap trước Router quan sát cả message sẽ bị Filter loại hoặc Router đưa sang nhánh khác; tap sau Router chỉ quan sát một nhánh đã chọn. Nếu mục tiêu là thống kê lý do bị loại, phát **safe signal** có `reasonCode` thuộc tập giá trị kiểm soát, thay vì log toàn bộ message bị loại.

### 10.2 Transformer

Transformer có thể giúp tạo message giám sát tối thiểu, nhưng cần kiểm tra nó **không kế thừa header nhạy cảm** từ message đầu vào. Tên “Transformer” không tự bảo đảm sanitizer, bởi một transformer có thể copy metadata cũ theo mặc định hoặc logic tùy chỉnh.

Đặt sanitization ở **ranh giới đi sang nhánh quan sát** và test payload/header thực tế sau bước chuyển đổi. Một đường `rawTap → Transformer → log` vẫn có raw message trên `rawTap`.

### 10.3 Splitter/Aggregator

Splitter có thể tạo nhiều message con, mỗi message có payload và correlation/sequence headers. Nếu gắn tap sau Splitter, dữ liệu bí mật có thể bị nhân bản trong nhiều bản ghi. Aggregator giữ message group trong store, vì vậy nếu message con chứa dữ liệu nhạy cảm, store này cũng là nơi phải bảo vệ; tap không thay thế chính sách retention và access control của group store.

Đối với thống kê nhánh, dùng `segmentType`, `sequencePositionBucket` hoặc kết quả cuối được định nghĩa trước; không phát thẳng payload của từng phân đoạn.

### 10.4 Gateway và request–reply

Một Gateway có thể đặt `replyChannel`, `errorChannel`, correlation và các header hỗ trợ request–reply. Nếu tap message request/reply, thông tin bí mật có thể xuất hiện **cả chiều đi lẫn chiều về**, đặc biệt ở error message. Nên tạo safe audit event từ các mốc: `REQUEST_STARTED`, `REQUEST_COMPLETED`, `REQUEST_TIMED_OUT`, kèm mã nguyên nhân đã kiểm soát, thay vì log request/response nguyên bản.

## 11. Kiểm thử không lộ payload

Một test phù hợp cần chứng minh hai điều: **tap không nhận dữ liệu cấm** và **luồng nghiệp vụ vẫn nhận đúng message gốc**.

### 11.1 Fixture riêng cho safe tap

Giả sử có các bean `safeAuditInput`, `safeTapMetrics` được nối bởi `auditFlow`. Khi viết test, dùng một `QueueChannel` thay cho tap metrics để chủ động nhận message, **không để một consumer khác cạnh tranh lấy** trong cùng test fixture.

~~~java
@Configuration
@EnableIntegration
class SafeAuditTapTestConfig {

    @Bean
    MessageChannel safeAuditInput() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel capturedTap() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow auditedFlow() {
        return IntegrationFlow.from("safeAuditInput")
                .wireTap("capturedTap")
                .handle(SafeAuditEvent.class, (event, headers) -> null)
                .get();
    }
}
~~~

Test JUnit 5:

~~~java
@SpringJUnitConfig(SafeAuditTapTestConfig.class)
class SafeAuditTapTest {

    @Autowired
    @Qualifier("safeAuditInput")
    MessageChannel input;

    @Autowired
    @Qualifier("capturedTap")
    PollableChannel tap;

    @Test
    void tapOnlySeesAllowlistedAuditPayload() {
        // Các chuỗi nhạy cảm chỉ dùng trong fixture thử nghiệm,
        // không đi vào message audit hoặc log sản phẩm.
        String forbiddenEmail = "secret@example.invalid";
        String forbiddenToken = "test-token-never-log";

        SafeAuditEvent safe =
                new SafeAuditEvent("CHECKOUT", "COMPLETED", "NONE");

        assertTrue(input.send(
                MessageBuilder.withPayload(safe).build()));

        Message<?> observed = tap.receive(1_000);
        assertNotNull(observed);
        assertInstanceOf(SafeAuditEvent.class, observed.getPayload());

        String visible = observed.toString();
        assertFalse(visible.contains(forbiddenEmail));
        assertFalse(visible.contains(forbiddenToken));
        assertEquals("CHECKOUT",
                ((SafeAuditEvent) observed.getPayload()).operation());
    }
}
~~~

Ví dụ này xác minh kiểu payload và sự vắng mặt của các chuỗi bí mật **trong tap fixture**. Nó không thay thế test tích hợp của toàn bộ `checkoutFlow`, nơi phải gửi `CheckoutCommand` thực và xác minh service vẫn nhận đủ dữ liệu hợp lệ trong vùng tin cậy, trong khi **không có tap nào gắn lên raw channel**.

### 11.2 Những assertion quan trọng khác

- Tap **không** chứa các header `Authorization`, `Cookie`, `accessToken`, `customerEmail` hoặc payload gốc trong bất kỳ trường nào.
- Error flow không ghi `failedMessage` nguyên bản vào logging sink.
- Sau khi thêm một trường `newSecret` vào DTO, safe audit schema vẫn **không tự xuất hiện** trường mới.
- Transformer và Header Enricher không vô ý copy toàn bộ headers từ raw message sang `SafeAuditEvent`.
- Nếu audit sink lỗi, chính sách với luồng nghiệp vụ được kiểm thử: rollback hay best-effort phải đúng như hợp đồng.
- Retry cùng event không tạo số liệu giao dịch duy nhất sai lệch; có deduplication nếu nghiệp vụ yêu cầu.
- Với tracing/metrics, không có nội dung nhạy cảm trong span attributes, log MDC hoặc label có cardinality cao.
- Nếu lưu evidence/quarantine, quyền truy cập và retention của kho đó được kiểm tra riêng.

**Lưu ý về test:** assert trên `toString()` chỉ là một kiểm tra bổ sung. Kiểm thử hiệu quả hơn là dùng schema audit cố định, kiểm soát nơi Wire Tap được gắn, đánh giá tập header được phép và kiểm tra những sink thực tế nhận dữ liệu.

## 12. Ma trận kiểm thử lỗi và rò rỉ

| Tình huống | Kích hoạt | Kết quả cần chứng minh |
|---|---|---|
| Message có token | Gửi payload và header chứa token thử nghiệm | Không có raw token trong tap, log, metric, trace ngoài vùng tin cậy. |
| Schema có trường mới | Thêm trường nhạy cảm vào DTO | Allowlist audit không tự mở rộng. |
| Transformer tạo message mới | Chuyển đổi trước nhánh tap | Không copy header bí mật, không thay payload nghiệp vụ ngoài ý định. |
| Tap handler lỗi | Cho metrics subscriber ném exception | Chính sách xử lý lỗi được quan sát; không giả định nhánh phụ không ảnh hưởng luồng chính. |
| Executor đầy | Giới hạn queue và tạo tải | Không gây mất kiểm soát bộ nhớ; ghi nhận số tín hiệu giám sát bị từ chối. |
| Business handler throw | Giả lập lỗi DB hoặc validation | `ErrorMessage`/exception không làm log lộ `failedMessage`. |
| Message được redeliver | Gửi lại cùng business event | Không tạo double-count nếu metric yêu cầu đếm unique event. |
| Broker/DLQ nhận lỗi | Gây serialization, timeout hoặc conversion failure | Dữ liệu gốc chỉ nằm ở kho được phép, không rơi vào audit sink chung. |
| Gateway timeout | Cắt kết nối hoặc trì hoãn reply | Không log toàn bộ request/reply; error category đã chuẩn hóa. |
| Quyền truy cập audit | Dùng tài khoản chỉ có quyền metrics | Không thể đọc raw payload hoặc bằng chứng nhạy cảm. |

Để chẩn đoán, nên theo dõi cả **số audit event đã phát**, **số được sink chấp nhận**, **số bị từ chối** và **độ trễ**. Một hệ thống không log payload nhưng bỏ mất toàn bộ bản ghi quan trọng cũng chưa đạt mục tiêu audit.

## 13. Vận hành: lưu giữ, phân quyền và chi phí

An toàn của tap không chỉ phụ thuộc vào mã Java:

- **Phân quyền:** chỉ cấp quyền xem raw message cho nhóm xử lý được ủy quyền; dashboard và log thông thường chỉ nhận safe events.
- **Retention:** định nghĩa thời gian lưu theo mục đích. Không giữ payload nhạy cảm trong log vô hạn; áp dụng xóa/TTL và xử lý bản sao lưu phù hợp.
- **Encryption:** mã hóa đường truyền và dữ liệu lưu khi có dữ liệu cần bảo vệ; kiểm soát khóa và truy cập.
- **Data lineage:** xác định nguồn dữ liệu, field nào sang audit, sink nào lưu, ai có quyền truy cập và thời điểm xóa.
- **Sampling:** chỉ giúp giảm khối lượng, **không bảo vệ bí mật** nếu message lấy mẫu vẫn mang token.
- **Metrics cardinality:** không dùng `eventId`, email hoặc full URL có dữ liệu người dùng làm nhãn metric; dùng nhóm loại thao tác và trạng thái có số giá trị giới hạn.
- **Kiểm toán thay đổi:** mọi lần thêm header, interceptor, outbound adapter hoặc `.log()` trên raw channel phải được xem lại điểm tap và danh sách trường an toàn.

Một bảng policy đơn giản có thể đặt cạnh thiết kế:

| Sink | Cho phép | Không cho phép |
|---|---|---|
| Metrics dashboard | Tên operation, outcome, error category thuộc tập cố định | Email, token, ID từng giao dịch, payload tùy ý. |
| Application log thông thường | Endpoint name, request class, duration bucket, trace reference đã duyệt | Raw message, toàn bộ headers, exception chứa request body. |
| Audit store riêng | SafeAuditEvent và metadata cần cho nghiệp vụ theo chính sách | Copy tràn lan mọi trường “để dùng sau”. |
| Secure quarantine | Dữ liệu gốc chỉ khi thực sự cần phục hồi, có bảo vệ riêng | Truy cập rộng rãi như log debug; lưu không thời hạn. |

## 14. Những sai lầm thường gặp

1. **Coi `.wireTap()` là hàm che dữ liệu.** Wire Tap chuyển message sang nhánh phụ; nó không tự redact.
2. **Redact sau raw tap rồi tin rằng không còn lộ dữ liệu.** Message gốc đã được gửi tới tap channel, qua interceptor/queue và có thể đi vào error path.
3. **Chỉ che payload, quên headers.** Token hoặc dữ liệu người dùng thường nằm trong metadata.
4. **Dump `Message.toString()` hoặc `ErrorMessage`.** Payload, failed message hay exception có thể bị ghi ra log.
5. **Dùng denylist tên trường.** Trường mới dễ lọt qua nếu không được bổ sung vào danh sách cấm.
6. **Hash email thông thường rồi coi là vô danh.** Giá trị từ tập dữ liệu có thể đoán được và đối chiếu; pseudonym vẫn cần quản lý như dữ liệu có khả năng liên kết.
7. **Gắn nhiều global interceptors mà không rà soát phạm vi.** Một `@GlobalChannelInterceptor` hoặc logging handler có thể chạm vào channel chứa dữ liệu gốc.
8. **Cho rằng tap bất đồng bộ không ảnh hưởng flow.** Executor queue đầy, rejection hoặc shutdown vẫn cần policy.
9. **Không phân biệt telemetry best-effort với audit bắt buộc.** Bản ghi pháp lý/kiểm toán cần tính bền vững và khả năng đối chiếu cụ thể.
10. **Bỏ qua retry và DLQ.** Dữ liệu nhạy cảm có thể bị sao chép nhiều lần hoặc giữ ở hệ thống có retention khác.
11. **Chỉ assert payload an toàn.** Traces, metrics, log MDC, headers và error handler cũng là kênh rò rỉ.
12. **Dùng correlation ID không kiểm soát.** Một mã có thể liên kết về giao dịch hoặc cá nhân ngay cả khi không chứa tên hay email.

## 15. Checklist trước khi triển khai

- [ ] Mục tiêu observability/audit được xác định rõ; mọi field của safe event có lý do sử dụng.
- [ ] Không có `WireTap` mặc định trên channel raw chứa bí mật nếu nhánh tap không được phép nhìn thấy dữ liệu đó.
- [ ] Safe event được tạo **trước khi vào tap channel**; payload chỉ chứa các trường allowlist.
- [ ] Headers của safe event được tạo mới hoặc allowlist; không copy toàn bộ header gốc.
- [ ] Không log `Message`, `ErrorMessage`, `failedMessage` hoặc payload exception nguyên bản.
- [ ] Error channel, retry, DLQ, Kafka/JMS/AMQP adapter, tracing và metrics đã được xét nguy cơ rò rỉ.
- [ ] Chọn chính sách rõ cho best-effort telemetry và audit bắt buộc; có giải pháp lưu bền vững khi cần.
- [ ] Bounded executor/queue, backpressure và cảnh báo khi tap lỗi hoặc bị từ chối.
- [ ] Audit store có quyền truy cập, mã hóa, retention, xóa và quản lý bản sao lưu phù hợp.
- [ ] Unit test và integration test dùng giá trị bí mật giả để phát hiện rò rỉ; không dùng credential thật.
- [ ] Thêm trường DTO, header mapper hoặc interceptor mới đều phải chạy lại test privacy.
- [ ] Đã kiểm tra luồng nghiệp vụ vẫn dùng payload chính xác và không bị sửa bởi nhánh observability.

## 16. Tổng kết

Wire Tap là công cụ quan sát hữu ích trong Spring Integration, nhưng **không có chức năng tự ẩn dữ liệu nhạy cảm**. Muốn tránh lộ bí mật, cách thiết kế rõ ràng nhất là tạo **safe audit event theo allowlist trước khi sự kiện đi vào channel được tap**, chỉ mang metadata cần thiết tới logging/metrics/tracing. Nếu phải quan sát raw channel, hãy dùng ranh giới tin cậy và một interceptor tùy biến chỉ phát tín hiệu an toàn, đồng thời kiểm soát các interceptor khác có thể nhìn thấy dữ liệu gốc.

Đối với hệ thống vận hành thực tế, hãy kiểm thử payload **và** headers, exception, error channel, retry/DLQ, transaction, async rejection, correlation và retention. Nhánh quan sát chỉ thực sự hữu ích khi vừa cung cấp bằng chứng đủ để điều tra, vừa tránh đưa dữ liệu bí mật ra khỏi phạm vi sử dụng được phép.
