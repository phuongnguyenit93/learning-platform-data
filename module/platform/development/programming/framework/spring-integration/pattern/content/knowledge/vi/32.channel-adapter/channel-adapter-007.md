# Adapter error channel

**Chương:** Channel adapter  
**Chủ đề:** Adapter error channel  
**Phạm vi học tập:** `SPRING_INTEGRATION_PATTERN` — triển khai Enterprise Integration Patterns bằng Spring Integration, phối hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation để các luồng thông điệp có thể kiểm thử, quan sát và phục hồi khi gặp sự cố.

## 1. Mục tiêu bài học

Khi hoàn thành bài học, bạn có thể:

- Giải thích vai trò của **error channel** ở ranh giới channel adapter và phân biệt với channel truyền dữ liệu thông thường.
- Biết khi nào exception được **ném về thread gọi**, khi nào được **đóng gói thành `ErrorMessage`**, và khi nào được chuyển cho error handler của listener/container.
- Đọc `MessagingException`, `failedMessage`, headers và correlation ID để xác định message nào gây lỗi.
- Thiết kế xử lý lỗi cho **polling inbound adapter**, **message-driven inbound adapter** và **outbound adapter**.
- Kết hợp error channel với retry, transaction, ACK/offset, dead-letter queue (DLQ), idempotency và quan sát vận hành.
- Viết kịch bản kiểm thử lỗi thật thay vì chỉ kiểm tra đã nhận được một bản ghi log.

## 2. Adapter error channel là gì?

**Channel adapter** đưa dữ liệu qua ranh giới giữa một hệ thống bên ngoài và luồng Spring Integration. **Inbound adapter** nhận từ file, email, JMS, AMQP, Kafka, HTTP hoặc nguồn khác rồi tạo `Message<?>` cho flow. **Outbound adapter** nhận message từ flow và gửi dữ liệu đến dịch vụ ngoài.

**Error channel** là một `MessageChannel` được dùng để chuyển thông tin lỗi dưới dạng `ErrorMessage`. Nó là một đường xử lý lỗi **ở tầng ứng dụng**. Nhờ vậy lỗi có thể được ghi nhận, phân loại, cảnh báo, cách ly hoặc định tuyến đến luồng khôi phục. Tuy nhiên, một error channel không mặc nhiên bảo đảm message sẽ được giao lại, giao dịch sẽ rollback hay consumer sẽ NACK: hành vi đó còn phụ thuộc adapter, thread, transaction manager, broker và cấu hình error handler.

Ví dụ, một polling adapter đọc file CSV và gửi tới Transformer. Nếu transformer không thể chuyển một cột thành số, cần trả lời bốn câu hỏi khác nhau:

1. **Lỗi xuất hiện ở đâu?** File adapter, Transformer, Service Activator hay hệ thống đích?
2. **Ai quan sát exception?** Thread gọi, poller, executor, listener container hay gateway?
3. **Lỗi được chuyển đi đâu?** Exception trả về caller, `ErrorMessage` trên error channel, retry advice hoặc cơ chế riêng của transport?
4. **Dữ liệu sẽ thế nào?** Giữ lại, rollback, redeliver, chuyển quarantine/DLQ hay đã bị coi là xử lý thành công?

Error channel giúp tổ chức câu trả lời thứ ba; muốn giải quyết đầy đủ phải xét cả bốn.

## 3. Luồng thành công và luồng lỗi

~~~mermaid
flowchart LR
  S["Nguồn ngoài: file / broker / HTTP"] --> A["Inbound adapter"]
  A --> C["inputChannel"]
  C --> X["Transformer / Router / Service Activator"]
  X --> O["Outbound adapter"]
  O --> T["Đích ngoài"]
  A -. "Lỗi được adapter/poller bắt" .-> E["errorChannel"]
  X -. "Lỗi được ranh giới async/poller bắt" .-> E
  O -. "Lỗi được tầng gọi bắt" .-> E
  E --> CL{"Phân loại"}
  CL --> L["Log + cảnh báo"]
  CL --> Q["Quarantine / DLQ"]
  CL --> R["Chính sách retry/khôi phục"]
~~~

Các mũi tên nét đứt là **khả năng khi có cơ chế bắt và phát lỗi phù hợp**, không phải cam kết mọi exception đều tự vào error channel. Ví dụ, một handler nối `DirectChannel` trên cùng thread có thể ném exception trực tiếp trở về phương thức `send()`; khi đó error channel không nhất thiết được dùng.

### 3.1 ErrorMessage khác message nghiệp vụ

Một message nghiệp vụ thường có payload như `OrderPlaced` hoặc `InvoiceFile`. Một `ErrorMessage` là message có payload kiểu `Throwable`; trong nhiều tình huống payload là `MessagingException`, chứa thông tin về message đã gây lỗi.

| Thành phần | Mục đích |
|---|---|
| `ErrorMessage` | Vỏ message để chuyển exception qua một `MessageChannel`. |
| `ErrorMessage.getPayload()` | `Throwable` cần phân loại và ghi nhận. |
| `MessagingException` | Exception có thể gắn với một message; gọi `getFailedMessage()` để lấy message liên quan nếu có. |
| `ErrorMessage.getOriginalMessage()` | Trong các trường hợp có sẵn, tham chiếu message gốc mà error publisher đã cung cấp. |
| `errorChannel` header | Địa chỉ channel xử lý lỗi theo hợp đồng của endpoint/gateway và lời gọi cụ thể. |
| `replyChannel` header | Đích trả kết quả reply; **không** dùng thay cho error channel. |
| Global `errorChannel` | Tên channel lỗi thông dụng được framework sử dụng trong những tình huống không có đích lỗi riêng phù hợp. |

Không phải mọi exception đều có `failedMessage`. Lỗi khi **poll nguồn** có thể xảy ra trước khi adapter tạo được một Spring `Message`; khi ấy chỉ có ngoại lệ và ngữ cảnh poller.

## 4. Quan trọng nhất: exception đang chạy trên thread nào?

Trong Spring Integration, semantics của lỗi gắn chặt với cách dispatch message.

| Bối cảnh | Hành vi điển hình | Điều cần xác minh |
|---|---|---|
| `DirectChannel` đồng bộ | Exception của handler thường quay về caller của `send()`. | Caller có bắt/ném lại không? Có poller hoặc adapter bên ngoài bắt lỗi rồi phát `ErrorMessage` không? |
| `ExecutorChannel` hoặc xử lý bất đồng bộ | Caller có thể kết thúc trước khi handler ném exception. | Executor/error handler nào nhận lỗi? Có error channel và subscribers không? |
| `QueueChannel` + poller | Poller lấy message và chạy downstream trong nhịp poll. | Error handling và transaction advice của poller; message có được trả lại nếu lỗi không? |
| Polling inbound adapter (file, JDBC...) | Poller điều khiển thời điểm lấy dữ liệu và gửi vào flow. | Cấu hình `errorChannel` trên poller/endpoint và cách source đánh dấu đã lấy. |
| Message-driven inbound adapter (AMQP/JMS...) | Listener/container nhận từ hệ thống ngoài. | Listener có phát `ErrorMessage` không? Cách exception ảnh hưởng ACK/rollback/requeue? |
| Outbound adapter nối trong luồng đồng bộ | Gửi ra ngoài có thể ném exception ngay trong thread xử lý. | Ai bắt exception: caller, advice, gateway hay poller ở phía trước? |
| Messaging gateway | Caller có thể đợi reply hoặc lỗi qua kênh tương ứng. | Timeout, mapping lỗi sang reply/HTTP status và exception trả về API. |

**Không nên viết quy tắc “mọi lỗi đều vào global errorChannel”.** Cùng một lỗi nghiệp vụ có thể đến caller hoặc error flow tùy vị trí của ranh giới bất đồng bộ và cấu hình endpoint.

## 5. Error channel riêng hay global errorChannel?

Spring Integration hỗ trợ các cơ chế chỉ định đích xử lý lỗi, tùy loại endpoint:

- **Endpoint/poller error channel:** định tuyến các lỗi mà chính adapter hoặc poller bắt được vào một channel đã đặt tên, ví dụ `adapterErrors`.
- **Header `errorChannel`:** một message có thể mang thông tin địa chỉ xử lý lỗi, thường gặp trong các request–reply hoặc async flow. Cách endpoint sử dụng header phụ thuộc hợp đồng tương ứng.
- **Global `errorChannel`:** channel mặc định theo tên `errorChannel` trong context, hữu ích cho lỗi chưa được chuyển đến một đích riêng.

Thứ tự lựa chọn đích và việc có phát lỗi hay không **không giống nhau ở mọi adapter**. Hãy đọc hợp đồng của adapter đang dùng và kiểm tra bằng test; tránh tuyên bố endpoint-level channel luôn thắng header hoặc ngược lại cho toàn bộ Spring Integration.

Nên dùng channel riêng cho mỗi nhóm xử lý có chính sách khác nhau. Ví dụ:

| Channel lỗi | Nguồn | Chính sách |
|---|---|---|
| `invoiceImportErrors` | Poller đọc file hóa đơn | Ghi nguyên nhân, cách ly file, báo người vận hành. |
| `orderConsumerErrors` | Consumer đơn hàng từ broker | Phân loại transient/permanent; liên kết với NACK/DLQ phù hợp. |
| `partnerOutboundErrors` | Gửi dữ liệu cho đối tác | Retry có giới hạn, circuit breaker, ghi lệnh chưa gửi. |
| `errorChannel` | Các lỗi chưa có đường xử lý riêng | Quan sát, cảnh báo; tránh để lỗi quan trọng biến mất trong log. |

Nếu dùng `PublishSubscribeChannel` cho error channel, mỗi subscriber cần có trách nhiệm rõ ràng; một subscriber lỗi có thể ảnh hưởng các subscriber khác tùy cấu hình dispatch/executor. Cần xác minh đường lỗi vẫn hoạt động khi hệ thống đang quá tải.

## 6. Ví dụ Java DSL: polling adapter đẩy lỗi vào channel riêng

Bài toán: mỗi giây ứng dụng kiểm tra thư mục `/srv/import/invoices` để nhập hóa đơn CSV. Nếu file hỏng hoặc importer lỗi, hệ thống cần nhận được thông tin chẩn đoán trên `invoiceImportErrors`.

Ví dụ dưới đây tập trung vào ranh giới `poller → flow → error channel`; giả sử đã có Spring Integration Java DSL, file adapter, Spring Configuration và bean `InvoiceImporter`.

~~~java
@Configuration
@EnableIntegration
public class InvoiceFileIntegration {

    @Bean
    public MessageChannel invoiceImportErrors() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow invoicesFromFolder(InvoiceImporter importer) {
        return IntegrationFlow
                .from(
                    Files.inboundAdapter(
                        new java.io.File("/srv/import/invoices"))
                        .patternFilter("*.csv"),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(java.time.Duration.ofSeconds(1))
                               .maxMessagesPerPoll(5)
                               .errorChannel("invoiceImportErrors"))
                )
                .handle(java.io.File.class, (file, headers) -> {
                    importer.importOnce(file.toPath());
                    return null;
                })
                .get();
    }

    public interface InvoiceImporter {
        void importOnce(java.nio.file.Path csvFile);
    }
}
~~~

**Giải thích từng phần:**

1. `Files.inboundAdapter(...)` tạo một message source; nó phát message có payload là file khi có file thỏa mãn điều kiện.
2. `Pollers.fixedDelay(...)` chủ động kéo dữ liệu; `maxMessagesPerPoll(5)` đặt giới hạn số message mỗi lần polling.
3. `.errorChannel("invoiceImportErrors")` khai báo đường xử lý lỗi của poller; khi lỗi đi qua cơ chế error handler của poller, lỗi được phát tới channel này theo hợp đồng.
4. `importer.importOnce(...)` thể hiện yêu cầu **idempotency**; việc import thực tế phải tránh tạo hóa đơn hai lần khi file được xử lý lại.
5. `return null` kết thúc flow một chiều sau khi hoàn tất handler.

Ví dụ chỉ cho thấy **cách chuyển lỗi**. Nó chưa triển khai đầy đủ archive/quarantine, transaction với database, bộ lọc file đã xử lý bền vững hay chuyển file an toàn sau commit. Những điều này cần thiết nếu phải phục hồi khi crash.

### 6.1 Handler tiếp nhận ErrorMessage

Có thể xây dựng một component Spring Integration để nhận lỗi từ channel đã cấu hình:

~~~java
@Component
public class InvoiceImportErrorHandler {

    private static final org.slf4j.Logger log =
            org.slf4j.LoggerFactory.getLogger(
                    InvoiceImportErrorHandler.class);

    @ServiceActivator(inputChannel = "invoiceImportErrors")
    public void onError(org.springframework.messaging.support.ErrorMessage error) {
        Throwable failure = error.getPayload();

        org.springframework.messaging.Message<?> failed = null;
        if (failure instanceof org.springframework.messaging.MessagingException ex) {
            failed = ex.getFailedMessage();
        }

        Object eventId = failed == null
                ? null
                : failed.getHeaders().get("eventId");

        log.error("Invoice import failed, eventId={}", eventId, failure);

        // Tiếp theo: phân loại lỗi, ghi bản ghi quarantine hoặc cảnh báo.
        // Không tự cho rằng thao tác ghi log này sẽ retry/requeue message.
    }
}
~~~

`failedMessage` có thể `null`; lỗi đọc file từ source có thể xảy ra trước khi message được tạo. Trên đường xử lý khác, `ErrorMessage.getOriginalMessage()` cũng có thể giúp lấy ngữ cảnh khi nguồn lỗi cung cấp.

**Lưu ý rất quan trọng:** handler trên chỉ **ghi nhận lỗi**. Nếu yêu cầu retry và phục hồi dữ liệu, phải thiết kế thêm cơ chế quyết định file nào được poll lại, file nào đưa vào quarantine, transaction nào được rollback và lỗi nào phải propagate. Không dùng logging handler như một phép bảo đảm xử lý thành công.

## 7. Nguồn lỗi theo vị trí trong channel adapter

### 7.1 Lỗi trước khi tạo Message

Adapter có thể lỗi ở kết nối FTP/SFTP, JDBC, HTTP, quyền truy cập file, cấu hình serializer hoặc authentication trước khi tạo `Message`. Trong trường hợp này:

- Không nhất thiết có `failedMessage` hoặc đầy đủ headers nghiệp vụ.
- Cần gắn metadata ngoài message: tên endpoint, destination, đường dẫn/file ID, thời điểm poll, exception type và trace ID của thao tác.
- Quy trình retry thường dựa trên **poller/source hoặc connection policy**, không phải cố gửi lại một message chưa từng được tạo.

### 7.2 Lỗi khi biến đổi và xử lý downstream

Inbound adapter có thể tạo message thành công nhưng `Transformer`, `Filter`, `Router` hoặc `Service Activator` phía sau ném lỗi. Nếu chúng chạy đồng bộ trong cùng poller transaction, exception có thể lan về poller và được error handler của poller quan sát. Nếu có một async channel ở giữa, lỗi xảy ra trên thread khác và phải cấu hình error handling ở ranh giới đó.

### 7.3 Lỗi outbound

Outbound adapter có thể gặp timeout khi gọi API, kết nối broker hỏng, database không nhận lệnh hoặc HTTP trả mã thất bại. Nếu outbound handler chạy từ `DirectChannel`, lỗi có thể trở về caller. Nếu handler chạy bởi poller hoặc executor, error handler của lớp đó có thể phát `ErrorMessage` theo cấu hình.

Phân biệt **timeout** và **thất bại xác định**: một HTTP request timeout có thể đã được đối tác xử lý. Retry mà không có idempotency key có thể tạo giao dịch trùng.

## 8. Message-driven inbound: error channel và broker ACK

Message-driven adapter thường được kích hoạt bởi một listener/container từ RabbitMQ, JMS hoặc hệ thống tương tự. Khi downstream ném exception, cần xét cả **Spring Integration error path** và **transport acknowledgement path**:

~~~mermaid
flowchart TD
  B["Broker giao message"] --> A["Inbound listener adapter"]
  A --> H{"Downstream processing"}
  H -->|Thành công| OK["ACK / commit theo cấu hình"]
  H -->|Exception| EH{"Ai xử lý exception?"}
  EH -->|Listener/container còn thấy lỗi| N["Rollback / NACK / retry / DLQ tùy transport"]
  EH -->|ErrorMessage được xử lý| E["Error channel handler"]
  E --> POLICY{"Chính sách trả về"}
  POLICY -->|Lỗi được coi là đã xử lý| ACK["Có thể ACK/commit"]
  POLICY -->|Lỗi được propagate hợp lệ| N
~~~

Các nhánh thể hiện **hành vi có thể có**, không phải mặc định của tất cả listener. Trong cấu hình cụ thể, một error flow hấp thụ exception có thể dẫn đến việc adapter coi lần delivery đã hoàn thành; một cấu hình khác có thể chuyển lỗi về container để rollback. Phải xác minh bằng kiểm thử với broker và container thật.

Một consumer xử lý đơn hàng nên có quy tắc:

- **Transient failure:** retry với backoff và giới hạn; nếu chưa thành công, giữ khả năng xử lý lại theo chính sách ACK/rollback.
- **Permanent failure:** cách ly payload hoặc định tuyến DLQ đúng cơ chế của broker; ghi lại lý do, `eventId`, thời điểm và số lần thử.
- **Business commit đã xảy ra nhưng ACK chưa kịp gửi:** message có thể được giao lại, nên nghiệp vụ phải idempotent.

### 8.1 Kafka cần chú ý riêng

Kafka là log theo partition và consumer dùng offset. Khi lỗi, việc gửi `ErrorMessage` vào Spring Integration channel **không tự điều khiển** seek, commit offset hay retry topic. Cần phối hợp cấu hình Kafka listener/container, error handler và retry/DLT policy. Thứ tự vẫn là thứ tự trong từng partition; xử lý lại nhiều lần có thể làm chậm các record phía sau cùng partition.

### 8.2 JMS và AMQP

- Với **JMS**, acknowledgment mode/transacted session và provider quyết định commit, rollback, redelivery; error channel của ứng dụng chỉ là một phần của pipeline.
- Với **AMQP/RabbitMQ**, cần phân biệt publisher confirm phía gửi, ACK/NACK phía consumer, requeue và dead-letter exchange; các cơ chế này không tự xuất hiện vì flow có tên `errorChannel`.

## 9. Error channel, retry advice, recovery và DLQ không thay thế nhau

| Cơ chế | Trả lời câu hỏi | Nó không tự bảo đảm |
|---|---|---|
| `errorChannel` | Lỗi được chuyển cho luồng xử lý nào? | Retry, rollback hoặc durable persistence. |
| Retry advice / retry template | Có thử lại thao tác lỗi trong cùng quá trình xử lý không? | Message còn sau process crash. |
| Poller/listener transaction | Thao tác nhận và cập nhật transactional resource được commit/rollback thế nào? | Rollback mọi hệ thống ngoài transaction. |
| Broker redelivery | Message nào được gửi lại khi chưa được xác nhận? | Chống duplicate business effects. |
| DLQ / quarantine | Message không thể xử lý được giữ ở đâu để kiểm tra? | Tự khắc phục lỗi dữ liệu, replay an toàn. |
| Idempotent consumer | Chạy lặp một sự kiện có gây tác động nghiệp vụ trùng không? | Producer/broker không mất message. |

### 9.1 Tránh retry vô hạn

Nếu handler mỗi lần lỗi đều throw, listener requeue ngay, và không có backoff, cùng một message lỗi có thể quay vòng liên tục, chiếm CPU, đè database và làm chậm message hợp lệ.

Chính sách mẫu:

1. Xác định lỗi **tạm thời** (network timeout, rate limit, tài nguyên bận) hay **vĩnh viễn** (schema sai, thiếu bắt buộc, quyền truy cập bị từ chối do cấu hình).
2. Retry tạm thời với số lần giới hạn, exponential backoff và jitter.
3. Khi vượt ngưỡng, lưu payload/tham chiếu cùng exception và correlation vào DLQ/quarantine có trách nhiệm vận hành rõ.
4. Dừng ACK hoặc commit sai thời điểm; phối hợp chính sách exception với broker/container.
5. Cho phép replay có kiểm soát sau khi sửa nguyên nhân; consumer phải idempotent.

### 9.2 Không nuốt exception một cách vô ý

Ví dụ lỗi DB phát sinh, poller chuyển `ErrorMessage` tới error flow, error handler chỉ log rồi trả về bình thường. Tùy cách error handler được lắp vào poller và transaction boundary, caller có thể coi lỗi đã được xử lý. Nếu yêu cầu rollback hoặc redelivery, cần thiết kế sao cho trạng thái thất bại **được biểu hiện tới đúng lớp có quyền rollback/NACK**, hoặc phục hồi message theo một cơ chế bền vững độc lập. Không dựa vào việc log ở error channel để suy ra giao dịch đã rollback.

Ngược lại, không phải cứ throw từ error handler là broker chắc chắn sẽ NACK; đôi khi exception ở error flow không còn nằm trên thread hoặc transaction gốc. Vì vậy phải kiểm thử end-to-end ở đúng adapter.

## 10. Correlation và giữ ngữ cảnh khi lỗi

Trong một luồng gồm Gateway → Router → Transformer → Splitter → Aggregator → outbound adapter, lỗi có thể xuất hiện sau nhiều lần tạo message mới. Một error handler tốt cần tái dựng được sự kiện nghiệp vụ bị ảnh hưởng.

Nên duy trì:

- **`eventId`**: định danh bất biến của sự kiện nghiệp vụ, dùng cho idempotency.
- **`correlationId`**: định danh nhóm message hoặc request–reply; cần nhất quán với chiến lược Aggregator.
- **`traceId`/`spanId`**: liên kết log và distributed tracing qua adapter/transport.
- **`source`/`destination`**: tên endpoint, protocol, queue/topic hoặc nguồn file ở mức cho phép.
- **Retry metadata**: số lần thử, thời điểm đầu tiên thất bại, loại lỗi, policy đã áp dụng.

`MessageHeaders.ID` (ID của từng Spring message) hữu ích để điều tra nhưng **không thay thế `eventId`**. Cùng một sự kiện có thể đi qua nhiều lần chuyển đổi và được publish lại với message ID khác.

Khi lỗi xảy ra trước khi tạo Spring message, lưu metadata của source hoặc poll cycle bằng cách khác. Tránh log token, secret, toàn bộ payload nhạy cảm hoặc dữ liệu cá nhân để chẩn đoán một lỗi thông thường.

## 11. Router, Filter, Splitter và Aggregator xử lý lỗi thế nào?

### 11.1 Router/Filter

Router có thể định tuyến message đến nhánh không có subscriber; Filter có thể loại bỏ message do điều kiện nghiệp vụ. **Thông điệp bị lọc hợp lệ không đồng nghĩa một exception.** Nên phân biệt rõ bỏ qua có chủ đích, lỗi dữ liệu vĩnh viễn và lỗi kỹ thuật cần retry.

Ví dụ `Filter` loại một file trùng vì `eventId` đã được xử lý: đó là quyết định nghiệp vụ, có thể xác nhận hoàn tất. Ngược lại, Transformer không parse được file là lỗi dữ liệu cần lưu quarantine và ghi nguyên nhân.

### 11.2 Splitter/Aggregator

Splitter tạo nhiều message con từ một nguồn; Aggregator giữ trạng thái nhóm cho tới khi thỏa release strategy. Nếu một phần message con thất bại:

- Error channel có thể nhận lỗi của **một message con**, trong khi Aggregator còn chờ toàn bộ nhóm.
- Cần xác định correlation key, sequence và timeout để tránh nhóm bị treo mãi.
- Muốn phục hồi qua restart, cần persistent `MessageGroupStore` và chiến lược chống duplicate child message phù hợp.
- Một lỗi trong nhánh không tự động rollback side effect đã commit ở nhánh khác.

### 11.3 Messaging Gateway

Gateway có thể biến việc gửi message thành một phương thức gọi có trả kết quả. Khi luồng chạy đồng bộ, exception có thể được ném về caller. Với reply/error channel và flow bất đồng bộ, cần quy định timeout, mapping lỗi sang response và xử lý reply muộn. Đối với HTTP, một error handler chỉ log rồi không tạo response có thể khiến client chờ tới timeout.

## 12. Thiết kế error flow phân loại lỗi

Một error flow có thể gồm ba bước: **chuẩn hóa thông tin lỗi → phân loại → áp chính sách**. Dùng `ErrorMessage` như dữ liệu đầu vào, không cần cố đưa mọi loại exception về một class duy nhất.

~~~mermaid
flowchart TD
  E["ErrorMessage / Throwable"] --> N["Trích xuất nguồn, failedMessage, eventId"]
  N --> K{"Phân loại nguyên nhân"}
  K -->|Sai schema / payload| Q["Quarantine + cảnh báo dữ liệu"]
  K -->|Network / timeout| RT["Retry hữu hạn + backoff"]
  K -->|Auth / config| OP["Cảnh báo vận hành + dừng nguồn lỗi"]
  K -->|Không nhận diện| U["Lưu ngữ cảnh + cảnh báo khẩn"]
  RT --> D{"Hết lần thử?"}
  D -->|Chưa| X["Thử theo retry policy"]
  D -->|Rồi| Q
~~~

**Phân loại cần xét nguyên nhân gốc**, ví dụ `MessagingException` có thể bọc `IOException`, `DataIntegrityViolationException`, exception parse hoặc timeout. Tuy vậy, chỉ phân loại theo class exception không đủ trong mọi hệ thống: HTTP 429 có thể là transient, HTTP 400 thường là permanent, nhưng phải dựa trên contract của API và thông tin response.

Ví dụ mã giả cho policy, dùng để mô tả hành vi thay vì gắn trực tiếp vào callback ACK của một broker cụ thể:

~~~text
onError(errorMessage):
    failed = extractFailedMessageIfPresent(errorMessage)
    reason = unwrapRootCause(errorMessage.payload)
    context = correlate(failed, endpointName, eventId, traceId)

    if permanent(reason):
        persistQuarantine(context, reason)
        applyTransportCompletionPolicy()
    else if retryable(reason) and retriesRemaining(context):
        scheduleRetryWithBackoff(context)
        applyTransportRetryPolicy()
    else:
        persistDeadLetter(context, reason)
        alertOperator(context)
        applyTransportCompletionPolicy()

    // completion/retry policy phải gắn với transaction, ACK hoặc offset
    // của adapter tương ứng; không được tự suy ra từ ErrorMessage.
~~~

Việc persist quarantine/DLQ cũng có thể thất bại; cần theo dõi và quyết định có tiếp tục ACK hay rollback. Trong các workflow mất message là không chấp nhận được, phải xử lý tình huống này như một lỗi nghiêm trọng thay vì lặng lẽ bỏ qua.

## 13. Bài thực hành: ba ranh giới lỗi

Xây dựng ứng dụng nhập hóa đơn từ file, kiểm tra rồi gửi sang một dịch vụ invoice bằng outbound HTTP adapter. Gắn `eventId` cho mỗi lần import; dùng handler idempotent ở phía tạo hóa đơn.

**Pha A — Polling source:** Tạo file CSV có cột số tiền không hợp lệ. Kiểm tra poller/error handler có phát `ErrorMessage` không; nếu có, payload là exception gì và `failedMessage` có tồn tại không. Sau đó kiểm tra file vẫn ở đâu và có được lấy lại không.

**Pha B — Downstream synchronous/async:** Dùng `DirectChannel` để nối Transformer và thử cho handler throw. Đổi ranh giới sang async channel rồi lặp lại. So sánh exception trở về caller với `ErrorMessage` tới error flow; kiểm tra cả khi error channel chưa có subscriber.

**Pha C — Broker outbound/inbound:** Dùng adapter nối broker thử lỗi lúc publish và lúc consume. Xác nhận sự khác biệt giữa outbound exception, publisher confirm, consumer ACK, rollback/redelivery và DLQ. Nếu dùng Kafka, kiểm tra offset commit và hành vi replay; không dùng ACK/RabbitMQ làm mô tả chung cho Kafka.

Bảng kiểm thử đề xuất:

| Trường hợp | Cách gây lỗi | Điều phải đo/quan sát |
|---|---|---|
| Poller không đọc được nguồn | Đổi quyền file hoặc tắt nguồn ngoài. | Error context còn endpoint/source không; có retry kết nối phù hợp không? |
| Transformer lỗi dữ liệu | CSV sai schema hoặc timestamp lỗi. | `ErrorMessage` chứa gì; xử lý quarantine và gắn eventId có chính xác không? |
| Service Activator lỗi tạm thời | Giả lập DB timeout. | Retry giới hạn, backoff; có rollback hoặc redelivery như mong đợi không? |
| Outbound timeout | Đích xử lý chậm hoặc ngắt kết nối. | Có khả năng đích đã nhận trước timeout không; idempotency key có được giữ không? |
| Duplicate delivery | Gửi lại cùng eventId. | Chỉ có một kết quả nghiệp vụ được commit. |
| Error handler cũng lỗi | Tắt DB dùng cho quarantine. | Lỗi mới có được ghi nhận/propagate? Có tránh ACK mất dữ liệu không? |
| Error channel không có subscriber | Cố cấu hình channel lỗi chưa nối handler. | Cách framework báo lỗi và vận hành có cảnh báo hay không. |
| Restart giữa chừng | Dừng tiến trình trước/sau business commit. | Dữ liệu còn, xử lý lại được và không tạo side effect trùng. |
| Nhiều consumer | Mở nhiều instance/threads. | Quan sát thứ tự, retry, consumer lag, DLQ depth và xử lý cạnh tranh. |

**Tiêu chí đạt:** có thể xác định message nào lỗi, exception từ tầng nào, ranh giới nào chịu trách nhiệm retry/ACK, trạng thái nghiệp vụ sau lỗi và bằng chứng khôi phục. Việc thấy một dòng log `ErrorMessage` **chưa đủ** để chứng minh hệ thống an toàn.

## 14. Chỉ số và cảnh báo trong production

Tập trung vào các chỉ số gắn với hành động vận hành:

| Chỉ số | Vì sao cần |
|---|---|
| `adapter.error.count` theo endpoint, loại exception | Phát hiện hệ thống ngoài hoặc converter hỏng theo cụm. |
| Tỉ lệ retry và số lần thử tối đa | Nhận biết lỗi transient biến thành retry storm. |
| Thời gian từ lỗi đầu tiên đến xử lý thành công | Đo độ trễ phục hồi và ảnh hưởng SLA. |
| DLQ/quarantine backlog và tuổi message lâu nhất | Giúp biết dữ liệu lỗi đang tồn đọng bao lâu. |
| Consumer lag/unacked message/offset lag | Đo nghẽn phía broker, theo đúng công nghệ sử dụng. |
| Error handler failures | Bảo đảm chính đường xử lý lỗi không thất bại âm thầm. |
| Duplicate detected / idempotency hit | Đo mức redelivery và khả năng chặn side effect trùng. |
| Số tác vụ nghiệp vụ đã commit | Phân biệt “message được transport” với “công việc hoàn thành”. |

Đặt alert theo mức độ ảnh hưởng nghiệp vụ: nhiều lỗi parse do một file poison khác với toàn bộ adapter mất kết nối. Gắn trace ID để đi từ nguồn ngoài qua channel, router, handler, outbound adapter tới hệ thống đích.

## 15. Các lỗi thiết kế thường gặp

1. **Tin rằng `errorChannel` tự động bắt mọi exception.** Exception ở `DirectChannel` có thể quay về caller; lỗi của container có đường xử lý riêng.
2. **Đánh đồng nhận ErrorMessage với rollback.** Việc phát message lỗi và quyết định transaction/ACK là hai hành động khác nhau.
3. **Chỉ ghi log rồi kết thúc.** Dữ liệu lỗi có thể bị bỏ qua hoặc bị đánh dấu xử lý xong mà không có cơ chế phục hồi.
4. **Retry vô hạn hoặc tức thời.** Có thể tạo vòng lặp poison message và làm nghẽn các công việc khác.
5. **Không xét `failedMessage == null`.** Lỗi source xảy ra trước khi adapter tạo message sẽ thiếu metadata nghiệp vụ.
6. **Dùng message ID làm định danh idempotency.** Một sự kiện nghiệp vụ có thể có nhiều Spring message ID qua retry/republish.
7. **Bỏ qua lỗi của chính error handler.** Quarantine store, logging sink hoặc alert service cũng có thể gặp sự cố.
8. **Không kiểm thử crash sau business commit trước ACK.** Đây là tình huống phổ biến gây duplicate khi có at-least-once delivery.
9. **Nhầm Kafka offset với ACK của work queue.** Kafka giữ log theo retention; xử lý lỗi cần quy tắc consumer/container riêng.
10. **Không giới hạn thông tin được log.** Exception và `failedMessage` có thể chứa payload nhạy cảm.

## 16. Checklist khi triển khai adapter error channel

- [ ] Đã xác định adapter inbound/outbound, thread đồng bộ hoặc async và lớp bắt exception thực tế.
- [ ] Đã chỉ định error channel theo hợp đồng endpoint; có handler/subscriber và có giám sát lỗi ngay tại error flow.
- [ ] Error handler xử lý được `Throwable`, `MessagingException`, `failedMessage` thiếu và lỗi trước lúc message hình thành.
- [ ] Đã giữ `eventId`, `correlationId`, trace context và metadata nguồn ở mức cần thiết.
- [ ] Retry policy có giới hạn, backoff, phân loại transient/permanent; có quarantine/DLQ và replay an toàn.
- [ ] Transaction, listener ACK/NACK hoặc offset commit được kiểm thử với adapter/broker thật.
- [ ] Có idempotency cho side effect quan trọng và kịch bản crash sau commit trước ACK.
- [ ] Error flow có phương án khi chính việc lưu lỗi, cảnh báo hoặc phát message lỗi thất bại.
- [ ] Có metric, log có cấu trúc, trace và alert cho lỗi liên tục, lỗi tồn đọng và retry storm.
- [ ] Đã thử restart, nguồn mất kết nối, async error, duplicate, poison message và backpressure.

**Kết luận:** Adapter error channel là nơi **chuyển và xử lý thông tin exception trong luồng Spring Integration**, giúp Router, Transformer, Service Activator và các adapter được quan sát và phục hồi có kiểm soát. Độ tin cậy của toàn hệ thống chỉ đạt được khi error channel được phối hợp với ranh giới thread, retry, lưu trữ, transaction, ACK/offset và idempotency của đúng transport đang sử dụng.
