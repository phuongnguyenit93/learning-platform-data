# Idempotent receiver cho inbound adapter

**Chương:** Reliability  
**Bài học:** Idempotent receiver cho inbound adapter  
**Module:** Spring Integration Adapters  
**Phạm vi:** Thiết kế luồng nhận message từ file/SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu, xác định bản tin trùng và bảo vệ tác vụ nghiệp vụ khỏi side effect lặp lại. Nội dung kết nối inbound adapter, gateway, poller, MessageChannel, Spring Integration Idempotent Receiver, MetadataStore, retry, acknowledgment, transaction, dead-letter và vòng đời kết nối.

## 1. Vì sao inbound adapter có thể nhận một message nhiều lần?

Một inbound adapter chuyển sự kiện hoặc dữ liệu từ hệ thống bên ngoài thành **Spring Message**, rồi đưa vào **MessageChannel**. Trong thực tế, nhiều nguồn chỉ có thể bảo đảm giao hàng **at-least-once**: một bản tin có thể được đưa đến hơn một lần.

Ví dụ:

- **SFTP/File:** Poller nhìn thấy file cũ sau khi restart, metadata filter bị reset, file được tải lại hoặc cùng một record xuất hiện trong hai lần import.
- **HTTP:** Client timeout khi server đã xử lý request và tự gửi lại cùng thao tác.
- **JMS/AMQP:** Consumer rollback hoặc connection đứt trước acknowledgment, broker redeliver.
- **Kafka:** Consumer xử lý xong nhưng chưa commit offset, sau rebalance nhận lại record.
- **JDBC:** Poller đọc lại hàng chưa được đánh dấu xử lý hoặc transaction rollback.
- **Batch/integration:** Một replay có chủ đích có thể đi cùng đường với message đầu tiên.

Nếu handler gọi API tạo đơn hàng, trừ tiền, lưu báo cáo hoặc ghi file, việc xử lý trùng có thể gây **side effect không hợp lệ**. Mẫu **Idempotent Receiver** giải quyết vấn đề theo hướng: *cùng một thao tác nghiệp vụ được nhận nhiều lần nhưng không tạo thêm tác động nghiệp vụ ngoài dự định*.

### 1.1. Ví dụ xuyên suốt

Ứng dụng nhận đơn hàng từ ba kênh:

~~~text
SFTP inbound polling --+
                      +--> normalize --> inboundOrdersChannel
HTTP inbound gateway -+                          |
                                                 v
                                idempotency check / guard
                                                 |
                                   order business handler
                                                 |
                                    database + partner API
~~~

Đơn hàng có `tenantId=T42`, `orderId=ORD-971`. Hai lần nhận bản tin đại diện **cùng thao tác tạo đơn** không được tạo hai bản ghi hoặc gọi đối tác hai lần một cách không kiểm soát.

Tuy nhiên nếu nghiệp vụ có **hai thao tác hợp lệ khác nhau** trên cùng đơn (ví dụ tạo và hủy, hoặc cập nhật phiên bản 2), chúng không được bị coi là trùng chỉ vì có cùng `orderId`. Đó là lý do **định nghĩa idempotency key** quan trọng hơn bản thân bộ lọc.

## 2. Idempotent Receiver là gì?

Trong các mẫu tích hợp hệ thống, **Idempotent Receiver** giúp endpoint nhận diện và xử lý lại những message đã xuất hiện theo một chính sách nhất quán. Có thể:

1. **Loại bỏ duplicate** trước khi handler tạo side effect.
2. **Đánh dấu duplicate** để handler chọn một nhánh xử lý khác.
3. **Trả lại kết quả đã lưu** của thao tác trước đó, nếu hệ thống là request-reply và có result store.
4. **Đối soát trạng thái chưa chắc chắn** thay vì mặc định bỏ hoặc phát lại.

Idempotency nghiệp vụ khác với việc lọc một object Java giống nhau. Hai Spring Messages có header `id` khác nhau vẫn có thể đại diện cho cùng một đơn hàng. Ngược lại, hai event trên cùng aggregate vẫn có thể là hai thao tác hợp lệ.

### 2.1. Quy tắc cơ bản

Với một **operation key K**, trạng thái mong muốn thường là:

~~~text
first(K)     -> xử lý hoặc nhận trách nhiệm xử lý K
duplicate(K) -> không tự tạo thêm business side effect
new(K2)      -> xử lý bình thường nếu là thao tác khác
~~~

Đây là mục tiêu nghiệp vụ. Một **metadata selector** chỉ trả lời xem khóa đã được đánh dấu hay chưa; tính idempotent end-to-end còn phụ thuộc transaction, concurrency, hệ thống đích và chính sách xử lý lỗi.

### 2.2. Idempotent khác deduplication như thế nào?

| Khái niệm | Trọng tâm | Giới hạn |
| --- | --- | --- |
| **Deduplication** | Phát hiện các delivery có cùng key | Không tự bảo đảm tác vụ đầu tiên đã thành công |
| **Idempotent business operation** | Lặp cùng operation mà kết quả nghiệp vụ không đổi ngoài dự kiến | Cần contract/database/downstream phù hợp |
| **Exactly-once processing** | Ngữ nghĩa tổng thể mỗi operation có đúng một hiệu ứng | Không thể suy ra chỉ từ một inbound filter |
| **At-least-once delivery** | Nguồn có thể gửi lại để tránh mất message | Application phải dự kiến duplicate |
| **At-most-once delivery** | Tránh gửi lặp bằng cách chấp nhận nguy cơ mất message | Không bảo đảm tất cả nghiệp vụ được thực hiện |
| **Replay** | Gửi lại có kiểm soát một event/operation | Phải phân biệt replay hợp lệ với event mới |

**Kết luận:** Idempotent Receiver là **một lớp bảo vệ**; thường cần phối hợp với unique constraint, transactional inbox/outbox, downstream idempotency key và reconciliation.

## 3. Vị trí của idempotent receiver trong Spring Integration

Spring Integration có hai lớp kiểm soát dễ bị nhầm:

- **Source-level filter:** Chọn file hoặc record được inbound adapter/poller nhận. Ví dụ các họ *accept-once file filter*, persistent file filter và metadata filters. Những filter này hoạt động **ở phía nguồn**, tùy adapter.
- **Message-level idempotent receiver:** Chặn hoặc nhận biết duplicate **sau khi message đã vào luồng**, gần handler tạo side effect. Cơ chế liên quan gồm **IdempotentReceiverInterceptor**, **MessageSelector** và **MetadataStoreSelector**.

Đừng mặc định một filter nguồn đủ thay thế kiểm tra nghiệp vụ, hoặc một idempotent receiver ở handler thay thế việc quản lý checkpoint của broker.

### 3.1. Sơ đồ luồng

~~~mermaid
flowchart LR
    SRC["File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC source"] --> ADP["Inbound adapter / gateway / poller"]
    ADP --> CH["MessageChannel"]
    CH --> KEY["Xác định operation key"]
    KEY --> GUARD["IdempotentReceiverInterceptor / MessageSelector"]
    GUARD -->|New| HANDLER["Business handler"]
    GUARD -->|Duplicate| DUP["Discard / mark / cached result"]
    HANDLER --> DB["Database / external system"]
    HANDLER --> STATE["Processed state / inbox"]
    DUP --> AUD["Metrics / audit"]
    STATE --> AUD
~~~

Một **advice** của Spring Integration được gắn vào **endpoint/handler thích hợp**, không phải cứ khai báo bean thì tất cả inbound adapters đều tự được bảo vệ. Nếu parse hoặc một bước khác có side effect **trước** vị trí guard, side effect đó vẫn có thể lặp.

### 3.2. Vị trí đặt guard

Nên xác định **side effect đầu tiên**:

1. Nhận message và đọc metadata.
2. Chuẩn hóa thông tin cần dùng để tạo key.
3. Kiểm tra/đăng ký key bằng cơ chế có atomicity phù hợp.
4. Thực thi business handler hoặc định tuyến duplicate.
5. Ghi kết quả và xử lý ack/checkpoint.

Nếu cần parse dữ liệu chỉ để lấy key, parser phải có xử lý lỗi riêng. Nếu có cập nhật DB hoặc gửi HTTP trước guard, idempotent receiver không bảo vệ được các thao tác ấy.

## 4. API Spring Integration liên quan

| Thành phần | Vai trò | Cần lưu ý |
| --- | --- | --- |
| **IdempotentReceiverInterceptor** | Advice triển khai mẫu idempotent receiver quanh handler phù hợp | Cần cấu hình selector và hành vi duplicate |
| **MessageSelector** | Quyết định message được chấp nhận hay bị xem là duplicate | Logic nhận diện key phải xác định rõ |
| **MetadataStoreSelector** | Dùng metadata store để chọn message theo key/value | Store phải phù hợp concurrency và durability |
| **MetadataStore** | Lưu trạng thái key/value | Store chỉ trong bộ nhớ không bền qua restart |
| **ConcurrentMetadataStore** | Hỗ trợ các thao tác cập nhật có tính atomic theo contract | Cần backend triển khai atomic giữa instance nếu chạy phân tán |
| **MessageChannel** | Truyền message tới handler/duplicate route | DirectChannel không tự là durable broker |
| **MessageFilter** | Một lựa chọn filter/route khác ở mức flow | Không tự giải quyết transaction với side effect |
| **AcceptOnceFileListFilter** | Filter file đã thấy ở inbound file adapter | Không tương đương business operation dedupe |
| **Persistent file filters** | Lưu dấu file ở metadata store phù hợp | Phải chọn key và chính sách thay đổi file đúng |
| **ErrorMessage / errorChannel** | Định tuyến lỗi xử lý | Không tự quyết định ack/DLQ hay trạng thái business |

### 4.1. Chú ý quan trọng về duplicateMessage header

Theo cách triển khai **IdempotentReceiverInterceptor**, một duplicate **có thể được đánh dấu bằng header** như `duplicateMessage` để downstream biết, thay vì mặc nhiên bị loại khỏi handler. Để **không thực thi handler nghiệp vụ** với duplicate, cần thiết kế rõ **discard channel/rejection behavior** theo API của phiên bản đang dùng.

Không nên viết test chỉ kiểm tra selector trả `false` rồi kết luận business handler chắc chắn không chạy. Hãy test **handler invocation thực tế**.

### 4.2. Source file filter và message filter khác nhau

~~~text
SFTP persistent filter:
    "File remote X đã được chấp nhận để download chưa?"

Message-level idempotent receiver:
    "Operation Y biểu diễn bởi record trong file X
     đã được xử lý theo hợp đồng nghiệp vụ chưa?"
~~~

Một file có thể chứa 1.000 bản ghi, một bản ghi có thể thất bại trong khi 999 bản ghi còn lại thành công. Lọc toàn file không trả lời được trạng thái từng operation.

## 5. Thiết kế idempotency key đúng nghĩa nghiệp vụ

**Idempotency key** là định danh ổn định cho *một thao tác nghiệp vụ*, không nhất thiết là định danh của một message transport.

### 5.1. So sánh các cách tạo key

| Key | Mức phù hợp | Vấn đề |
| --- | --- | --- |
| **Spring MessageHeaders.ID** | Thường không phù hợp dedupe nghiệp vụ xuyên delivery | Message mới thường có ID khác |
| **HTTP request ID sinh mới mỗi lần** | Chỉ phù hợp nếu caller tái sử dụng cùng ID cho retry | Caller tạo ID mới sẽ không phát hiện duplicate |
| **Kafka topic + partition + offset** | Có ích khi dedupe **chính record transport** | Republish cùng event có offset khác |
| **JMSMessageID / broker delivery ID** | Có ích trong một số redelivery | Có thể thay đổi khi republish qua broker khác |
| **File path + mtime/size** | Có ích khi lọc phiên bản file | Không đủ cho record hoặc file content thay đổi cùng tên |
| **Tenant + operation type + business ID + version** | Thường phù hợp cho nghiệp vụ đã định nghĩa rõ | Cần tránh gộp các thao tác thật sự khác |
| **Content hash** | Phù hợp trong trường hợp payload equality là định nghĩa duplicate | Trùng nội dung chưa chắc trùng ý định; thay serialization có thể khác hash |

### 5.2. Ví dụ key cho đơn hàng

~~~text
tenantId    = T42
operation   = CREATE_ORDER
orderId     = ORD-971
version     = 1

idempotencyKey = "order:create:v1:T42:ORD-971"
~~~

Nếu cùng order ID được phép phát sinh event **UPDATE_ORDER:v2**, cần một key khác. Nếu phát lại cùng CREATE_ORDER do mất HTTP response, key phải giữ nguyên.

### 5.3. Quy tắc tạo key

1. **Stable:** Không thay ở mỗi retry, redelivery, poll hoặc replay.
2. **Unique theo ý định:** Hai thao tác hợp lệ khác nhau không bị gộp chung.
3. **Scoped:** Bao gồm tenant, ứng dụng, operation type hoặc version khi cần.
4. **Canonical:** Quy định chuẩn hóa chữ hoa/thường, khoảng trắng, timestamp, timezone và encoding.
5. **Có giới hạn kích thước:** Không đưa nguyên payload hoặc PII vào tên key.
6. **Khả năng truy vết:** Có cách liên hệ key với business record mà không công khai dữ liệu nhạy cảm.
7. **Rõ retention:** Biết sau bao lâu key được phép tái sử dụng hoặc hết hiệu lực.

Không dùng `message.toString()` làm key. Biểu diễn message có thể thay đổi do headers, payload wrapper hoặc format của thư viện.

### 5.4. Khi message thiếu key

**Không được** lặng lẽ gán cùng một key mặc định như `unknown` cho mọi message thiếu business ID. Điều đó có thể làm bản tin hợp lệ bị drop hàng loạt.

Chọn một chính sách rõ:

- Reject và gửi vào validation error channel/quarantine.
- Yêu cầu upstream cung cấp key theo contract.
- Dùng một chiến lược fallback **được mô tả và kiểm thử**, nếu nghiệp vụ cho phép.

## 6. MetadataStore và tính bền vững

**MetadataStoreSelector** dựa vào metadata store để xác định key đã được chấp nhận trước đó hay chưa. Chọn store sai làm mất toàn bộ ý nghĩa của dedupe khi scale-out hoặc restart.

### 6.1. In-memory và persistent store

| Store | Khi phù hợp | Hạn chế |
| --- | --- | --- |
| **SimpleMetadataStore** | Demo, unit test hoặc luồng single-process không yêu cầu chống trùng sau restart | Mất dữ liệu khi restart; không chia sẻ đa instance |
| **JDBC-backed metadata store** | Cần durability và phối hợp nhiều instance với DB phù hợp | Kết nối DB, transaction, schema, cleanup và contention |
| **Redis-backed metadata store** | Cần state dùng chung và throughput phù hợp | Phải xét tính bền vững, atomic operations, eviction, failover |
| **Các shared store khác được hỗ trợ** | Phù hợp topology cụ thể | Phải đọc contract atomicity và khả năng phục hồi |

Tên bean/store cụ thể phụ thuộc phiên bản Spring Integration. Dù chọn backend nào, phải xác minh store đáp ứng **read/write atomic** theo contract cần thiết và **không bị mất key** khi một instance khởi động lại.

### 6.2. Race condition giữa hai consumer

~~~mermaid
sequenceDiagram
    participant A as Instance A
    participant B as Instance B
    participant S as Shared metadata store
    A->>S: Check key K
    B->>S: Check key K
    S-->>A: Chưa có
    S-->>B: Chưa có
    A->>S: Mark K
    B->>S: Mark K
    Note over A,B: Nếu check-then-put không atomic, cả hai có thể xử lý
~~~

Một **read rồi write tách biệt** không đủ dưới concurrency. Cần thao tác có semantics **put-if-absent/compare-and-set** phù hợp, hoặc unique constraint/locking/transaction ở database. Đối với nhiều instance, atomicity phải nằm ở **shared backend**, không chỉ trong một `synchronized` của JVM.

### 6.3. Durability, TTL và eviction

Nếu dedupe key tồn tại 7 ngày nhưng source có thể replay event từ 30 ngày trước, sau ngày 7 hệ thống có thể xử lý lại event cũ. Vì vậy retention phải theo:

- Thời gian replay/redelivery tối đa của nguồn.
- Business correctness window (ví dụ tránh tạo giao dịch trùng suốt vòng đời đơn hàng).
- Thời hạn lưu dữ liệu và chính sách quyền riêng tư.
- Dung lượng và hiệu năng metadata store.
- Cơ chế reset/migration đã được phê duyệt.

**TTL không phải lúc nào cũng an toàn.** Với những thao tác có hậu quả lâu dài, dùng unique constraint hoặc idempotency record nghiệp vụ bền vững có thể thích hợp hơn cache ngắn hạn.

## 7. Ví dụ cấu hình Java DSL và IdempotentReceiverInterceptor

Đây là ví dụ **minh họa thiết kế** dùng Spring Integration Java DSL. Cần đối chiếu import, overload và phiên bản Spring Integration thực tế của dự án khi chạy; các interface `OrderService` và lớp xử lý duplicate do ứng dụng tự định nghĩa.

### 7.1. Bean MetadataStoreSelector + advice

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.MessageChannel;

@Configuration
public class InboundIdempotencyConfig {

    @Bean
    public MessageChannel inboundOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel duplicateOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    public ConcurrentMetadataStore exampleMetadataStore() {
        // CHỈ minh họa single-JVM: production đa instance cần shared store.
        return new SimpleMetadataStore();
    }

    @Bean
    public IdempotentReceiverInterceptor orderIdempotentAdvice(
            ConcurrentMetadataStore exampleMetadataStore,
            @Qualifier("duplicateOrdersChannel") MessageChannel duplicates) {

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> {
                    String tenant = requireHeader(message, "tenantId");
                    String operationId = requireHeader(message, "operationId");
                    return "order:create:v1:" + tenant + ":" + operationId;
                },
                exampleMetadataStore);

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(selector);

        // Cấu hình tuyến duplicate để không thực thi business handler
        // trong những trường hợp selector từ chối.
        advice.setDiscardChannel(duplicates);
        return advice;
    }

    private static String requireHeader(
            org.springframework.messaging.Message<?> message, String name) {
        Object value = message.getHeaders().get(name);
        if (value == null || value.toString().isBlank()) {
            throw new IllegalArgumentException("Missing header: " + name);
        }
        return value.toString();
    }

    @Bean
    public IntegrationFlow ordersProcessingFlow(
            OrderService orderService,
            IdempotentReceiverInterceptor orderIdempotentAdvice) {

        return IntegrationFlow.from("inboundOrdersChannel")
                .handle(orderService, "createOrder",
                        endpoint -> endpoint.advice(orderIdempotentAdvice))
                .get();
    }
}
~~~

**Giải thích:**

- Message từ inbound adapter đi vào `inboundOrdersChannel`.
- Handler `OrderService.createOrder(...)` được gắn **advice**.
- Selector tính key từ hai header ổn định, store dùng để quyết định key đã xuất hiện.
- Duplicate được đưa tới `duplicateOrdersChannel` theo cấu hình, không coi log duplicate là business success.
- `SimpleMetadataStore` chỉ phục vụ demo. Hãy thay bằng **persistent shared store có cơ chế atomic phù hợp**, không dùng lại nguyên trạng cho production nhiều pod.
- Method `OrderService.createOrder` và các headers là **contract của ứng dụng**, không phải Spring tự tạo.

**Lưu ý quan trọng:** Một interceptor ghi nhận key ở thời điểm nhận có thể đánh dấu key **trước khi business handler thực sự commit**. Ví dụ này dạy cách nối các component, chưa phải bảo đảm exactly-once hoặc crash safety. Phần sau trình bày cách nâng cấp thành thiết kế production.

### 7.2. Flow xử lý duplicate

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class DuplicateOrdersHandler {

    @ServiceActivator(inputChannel = "duplicateOrdersChannel")
    public void acceptDuplicate(Message<?> message) {
        // Ghi metric/audit theo operationId. Không gọi createOrder lần nữa.
        // Không ghi payload hoặc PII thô vào log.
        // Nếu là request-reply, phải trả kết quả theo contract riêng.
    }
}
~~~

Ở flow one-way, duplicate có thể được ack sau khi xác định đã được xử lý thành công ở lần trước. Nhưng nếu key được đánh dấu trước khi business commit hoặc trạng thái đang `PROCESSING`, **không được kết luận duplicate đã hoàn tất**. Trong trường hợp đó cần tìm trạng thái nghiệp vụ và quyết định chờ, retry hoặc reconciliation.

### 7.3. Nếu không dùng IdempotentReceiverInterceptor?

Có thể dùng **MessageFilter** với một `MessageSelector` và discard channel, hoặc tự viết service handler dùng **database unique constraint**. Lựa chọn phụ thuộc:

- Guard ở vị trí nào?
- Cần xử lý duplicate như một business response hay chỉ discard?
- Có transaction chung giữa metadata và side effect không?
- Cần bảo đảm across multiple instances không?
- Replay cần so sánh payload, version và trạng thái thế nào?

Không buộc mọi inbound adapter vào một interceptor nếu bản thân nguồn hoặc DB đã có cơ chế idempotency nghiệp vụ phù hợp hơn.

## 8. Nguy cơ lớn nhất: đánh dấu processed trước khi xử lý xong

Hãy xét một implementation đơn giản:

~~~text
T0: receive(K)
T1: putIfAbsent(K, "seen") -> success
T2: business handler gọi downstream
T3: downstream timeout hoặc process crash
T4: broker redeliver K
T5: selector thấy K "seen" -> đánh dấu duplicate -> discard
~~~

Tại T3 có thể chưa có business outcome. Nếu T5 bỏ message, hệ thống đã biến **at-least-once** thành **lost business operation**.

### 8.1. Bốn trạng thái tối thiểu cho inbox

~~~text
NEW
  -> PROCESSING
  -> COMPLETED
  -> FAILED_RETRYABLE
  -> FAILED_FINAL / NEEDS_RECONCILIATION
~~~

Phải phân biệt:

- **COMPLETED:** Có bằng chứng business effect đã commit hoặc kết quả cuối được xác nhận.
- **PROCESSING:** Một worker đang sở hữu thao tác; cần lease/timeout để tránh kẹt vô hạn.
- **FAILED_RETRYABLE:** Được phép xử lý lại theo chính sách, giữ cùng operation key.
- **NEEDS_RECONCILIATION:** Không rõ downstream đã xử lý chưa, không replay mù.
- **FAILED_FINAL:** Lỗi đầu vào hoặc nghiệp vụ được xác nhận không thể xử lý.

Một boolean `seen=true` không thể biểu diễn đủ những tình huống này.

### 8.2. Transactional inbox pattern

Nếu business side effect nằm trong **cùng database**, có thể dùng một transaction:

1. Insert inbox row với unique key.
2. Nếu key đã tồn tại, đọc kết quả/trạng thái.
3. Nếu chưa có, thực hiện logic DB và lưu `COMPLETED` **trong cùng transaction**.
4. Commit đồng thời bản ghi inbox và thay đổi nghiệp vụ.

Nếu transaction rollback trước commit, key chưa được ghi hoàn tất; lần delivery sau có thể xử lý. Nếu key trùng sau commit, có thể trả hoặc bỏ qua dựa trên kết quả đã lưu.

~~~sql
-- Mô hình SQL minh họa; cú pháp khóa và ON CONFLICT thay đổi theo DB.
CREATE TABLE inbound_inbox (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_key      VARCHAR(250) NOT NULL,
    payload_hash       VARCHAR(128) NOT NULL,
    state              VARCHAR(40) NOT NULL,
    result_reference   VARCHAR(250),
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_key)
);
~~~

Unique constraint bảo vệ nhiều worker khỏi cùng tạo một inbox row. Nhưng khi side effect là **HTTP API bên ngoài**, DB transaction không tự bao trùm request từ xa: vẫn cần downstream idempotency key, outbox hoặc reconciliation.

### 8.3. Đổi giữa duplicate suppression và outcome replay

Đối với **HTTP inbound gateway**, caller retry thường muốn nhận **cùng business result**. Nếu chỉ discard duplicate và không trả reply, caller có thể timeout rồi retry vô hạn.

Đối với **JMS one-way event** đã commit, có thể chấp nhận duplicate và ack mà không gọi handler lần nữa.

Đối với **event đang PROCESSING**, có thể cần trả trạng thái accepted/pending hoặc yêu cầu caller thử lại theo hợp đồng; không giả mạo thành công khi chưa có kết quả.

## 9. Transaction, acknowledgment và checkpoint

Một idempotent receiver không thay thế **ack/offset commit** của message source. Để tránh mất hoặc xử lý trùng, cần chỉ ra **ai chịu trách nhiệm** tại mỗi ranh giới.

| Nguồn | Điểm checkpoint/ack | Rủi ro khi đánh dấu key quá sớm |
| --- | --- | --- |
| **HTTP inbound** | Response HTTP gửi cho caller | Trả success dù business chưa commit |
| **JMS** | Session acknowledgment / transaction commit | Ack message đã bị discard dù processing đầu lỗi |
| **AMQP** | Ack/nack và DLX/redelivery policy | Ack trước khi lưu outcome bền |
| **Kafka** | Consumer offset commit, ack mode và error handler | Commit offset dù business side effect chưa hoàn tất |
| **File/SFTP** | File filter, staging, archive/move, metadata | File bị bỏ qua ở poll tiếp theo dù record xử lý chưa xong |
| **JDBC polling** | Row claim, processed flag, transaction | Hàng bị đánh dấu processed trước khi external call thành công |

Không suy ra chính xác ack behavior từ việc flow dùng `DirectChannel` hay `IdempotentReceiverInterceptor` mà chưa xem listener container, error handler, transaction manager, thread boundary và cấu hình của adapter.

### 9.1. Hai tình huống cần integration test

**Tình huống A — Business thành công, ack thất bại:** Source redeliver. Receiver phải thấy outcome `COMPLETED` và không tạo side effect lần hai, đồng thời hoàn tất ack theo chính sách.

**Tình huống B — Đã ghi marker, business thất bại:** Source redeliver. Receiver **không được bỏ qua vô điều kiện**; phải có phương án rollback marker, lease/retry hoặc truy vấn inbox state.

### 9.2. Ranh giới transaction không đi xuyên mọi hệ thống

Một transaction JDBC không tự bao trùm SFTP server, HTTP partner và Kafka broker nếu không có cơ chế giao dịch/phối hợp tương ứng. Với luồng đa hệ thống, thiết kế thực tế thường là:

- At-least-once delivery.
- Business idempotency với key ổn định.
- Inbox/outbox để điều phối local state.
- Reconciliation cho remote outcome chưa chắc chắn.
- Retry và dead-letter có giới hạn.

Không tuyên bố **exactly-once end-to-end** chỉ vì selector đã phát hiện duplicate trong memory.

## 10. Retry, redelivery, recoverer và duplicate detection

Retry và idempotency bổ sung cho nhau:

- **Retry:** Thử lại lỗi tạm thời, có thể gọi handler nhiều lần.
- **Redelivery:** Source phát lại vì chưa nhận ack/commit.
- **Idempotency:** Giảm hoặc ngăn business effect lặp lại.
- **Recoverer/DLQ:** Quyết định xử lý sau khi retry hết lượt hoặc lỗi không thể retry.

~~~mermaid
flowchart TD
    IN["Source event K"] --> KEY["Compute stable operation key"]
    KEY --> STATE{"Inbox/selector state"}
    STATE -->|New| EXEC["Handle business operation"]
    STATE -->|Completed| ACK["Return cached result / ack duplicate"]
    STATE -->|Processing| WAIT["Wait / retry / reconcile"]
    STATE -->|Failed/retryable| EXEC
    EXEC --> R{"Outcome"}
    R -->|Success| DONE["Persist COMPLETED + result"]
    R -->|Transient failure| RETRY["Bounded retry + backoff"]
    RETRY --> EXEC
    R -->|Exhausted/unknown| REC["Recovery store / DLQ / reconciliation"]
    REC --> AUD["Audit + owner + replay policy"]
    DONE --> ACK
~~~

### 10.1. Lỗi lặp retry tầng tầng

Nếu handler retry 3 attempts và broker redeliver 4 lần, tổng số lần gọi downstream có thể tới **12**, chưa kể retry trong HTTP client. Dedupe key tốt giúp giảm side effects nhưng không thay thế **retry budget** và backpressure.

### 10.2. Khi nào cần remove marker sau lỗi?

Một metadata store kiểu “seen key” có thể cần xóa marker khi handler chưa tạo side effect để cho phép xử lý lại. Tuy nhiên **xóa marker tùy tiện cũng nguy hiểm** nếu downstream đã commit nhưng response bị mất.

Chỉ xóa hoặc chuyển trạng thái marker dựa trên **chứng cứ outcome** và cơ chế concurrency đã thiết kế. Với HTTP timeout không rõ kết quả, ưu tiên `NEEDS_RECONCILIATION` thay vì xóa key rồi gửi lại mù.

### 10.3. Recovery phải giữ operation key

Khi message vào DLQ rồi replay, hãy giữ **operation ID gốc**, thêm `replayAttempt` hoặc `replayId` riêng để kiểm toán. Nếu tạo idempotency key mới mỗi replay, cơ chế chống trùng mất tác dụng.

## 11. File và SFTP inbound: hai lớp dedupe

File/SFTP là ví dụ điển hình cho sự khác nhau giữa **filter file** và **business idempotency**.

### 11.1. Filter ở lớp file

Một inbound adapter/poller có thể dùng **accept-once** hoặc **persistent metadata filter** để tránh tải lại file đã thấy. Key thường dựa vào path và thông tin thay đổi file theo adapter.

Đây là kiểm soát **file discovery**, không phải xác nhận tất cả records trong file đã được xử lý.

~~~text
/incoming/orders-2026-11-23.csv
   record 1: ORD-971  -> COMPLETED
   record 2: ORD-972  -> FAILED_RETRYABLE
   record 3: ORD-973  -> COMPLETED

File-level: "đã tải file"
Record-level: "đã hoàn tất ORD-971, ORD-973; còn ORD-972"
~~~

### 11.2. Kịch bản file được upload nhiều lần

Nếu đối tác gửi lại cùng file với tên khác, file filter theo path có thể coi là file mới. Nhưng các business operation keys vẫn trùng và được bảo vệ bởi inbox. Ngược lại, nếu đối tác cập nhật nội dung nhưng giữ tên file, filter chỉ dựa path có thể bỏ qua bản cập nhật hợp lệ.

Thiết kế phải xác định contract:

- File là **immutable** sau upload hay có thể sửa?
- Tên file mang version/checksum không?
- Có trạng thái `upload-complete` hoặc atomic rename để tránh đọc file chưa hoàn chỉnh không?
- Cần move/rename/cleanup remote file sau bước nào?
- Nếu một record lỗi, có giữ toàn file hay xử lý một phần?

### 11.3. Persistent accept-once filter và restarts

Filter chỉ trong memory có thể quên các file đã chấp nhận sau restart. Persistent metadata filter giúp bảo vệ qua restart **nếu** metadata store bền và được chia sẻ đúng giữa nhiều instance.

Tuy nhiên một file đã chấp nhận nhưng xử lý lỗi có thể vẫn bị loại khỏi poll tiếp theo. Vì vậy cần thiết kế **rollback/cleanup filter metadata hoặc per-record recovery** theo vòng đời file thật, không mặc định filter sẽ biết side effect đã commit.

## 12. HTTP inbound gateway: duplicate không phải luôn trả 200

Với HTTP inbound gateway, duplicate thường do caller gửi lại sau timeout, network error hoặc chủ động retry. Ứng dụng cần một **request idempotency contract**:

1. Client gửi **Idempotency-Key** hoặc business operation ID ổn định.
2. Server kiểm tra key theo tenant + operation + endpoint/phiên bản nếu cần.
3. Nếu **chưa thấy key**, server xử lý và lưu result trong inbox.
4. Nếu **đã COMPLETED** với cùng request fingerprint, trả **cùng business result** hoặc reference theo contract.
5. Nếu **PROCESSING**, trả trạng thái pending/accepted hoặc phản hồi tạm theo API contract.
6. Nếu key tồn tại nhưng request body khác, trả **conflict** thay vì coi là duplicate hợp lệ.

### 12.1. Ví dụ hợp đồng HTTP

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: order-create-T42-ORD-971

{"tenantId":"T42","orderId":"ORD-971","amount":150000}
~~~

Khi đã có kết quả:

~~~json
{
  "operationId": "order-create-T42-ORD-971",
  "status": "COMPLETED",
  "orderReference": "ORD-971"
}
~~~

Lược đồ trên chỉ minh họa. Với hệ thống thật phải quy định status code, response body, thời hạn replay, kiểm tra fingerprint và bảo vệ key tránh bị client khác đoán/chiếm.

### 12.2. Vì sao discard duplicate có thể làm HTTP caller treo?

Nếu interceptor chuyển duplicate tới một **discard channel one-way**, nhưng caller đang chờ reply từ **gateway**, không có gì bảo đảm caller nhận được kết quả nghiệp vụ. Có thể timeout hoặc thiếu reply theo cấu hình endpoint.

Với inbound gateway, một **idempotent service** đọc inbox và trả cached result thường thích hợp hơn việc chỉ discard. Nếu muốn dùng interceptor, phải thiết kế đường duplicate **có reply hợp lệ** và test đúng request-reply semantics.

## 13. JMS, AMQP và Kafka: idempotency với broker

### 13.1. JMS inbound

JMS có message ID và redelivery metadata, nhưng business dedupe nên dựa vào **operation ID** nếu thao tác có thể được republish hoặc đi qua bridge. Khi listener rollback, cùng message có thể được nhận lại; metadata store không được chặn delivery mới nếu lần trước chưa commit nghiệp vụ.

Kiểm thử:

- Thành công nhưng session commit lỗi → redelivery không tạo side effect trùng.
- Handler lỗi trước commit → delivery sau vẫn có đường xử lý lại.
- DLQ đạt ngưỡng → failure record được lưu và có replay policy.

### 13.2. AMQP/RabbitMQ inbound

RabbitMQ thường có consumer ack/nack và dead-letter exchange theo cấu hình. Idempotent receiver bảo vệ business handler; nó **không tự quyết định** broker ack/nack. Khi recoverer đã lưu failure bền và trả về bình thường, adapter/container có thể ack theo chính sách. Nếu persistence failure xảy ra, message phải tiếp tục được giữ theo chiến lược đã kiểm chứng.

Không dùng `redelivered` flag như bằng chứng duy nhất: duplicate hợp lệ cũng có thể đến qua publish mới và không mang flag redelivered.

### 13.3. Kafka inbound

Kafka offset và event ID có hai ý nghĩa:

~~~text
Transport identity:
    topic + partition + offset

Business operation identity:
    tenant + eventId + operation/version
~~~

Nếu chỉ muốn tránh xử lý lại **cùng record** sau rebalance, transport key có thể hữu ích. Nếu publisher **republish cùng business event** ở offset mới, cần business key để chống trùng. Với Kafka consumers phải kiểm tra offset commit, ack mode, listener error handler, DLT và transaction thật.

### 13.4. Broker-level dedupe và app-level dedupe

Một broker có thể cung cấp cơ chế giảm duplicate trong phạm vi nhất định, nhưng không tự đảm bảo không trùng side effect khi consumer crash sau DB commit và trước ack. **Application-level idempotency** và database constraints vẫn thường cần thiết.

## 14. JDBC inbound polling: row state và unique key

Với **JDBC inbound adapter**, poller thường chọn các hàng thỏa điều kiện rồi chuyển thành message. Nếu query không chuyển trạng thái hàng hoặc transaction rollback, hàng đó có thể xuất hiện ở poll tiếp theo.

### 14.1. Trạng thái hàng nghiệp vụ

~~~text
NEW -> CLAIMED -> PROCESSING -> COMPLETED
                    |             |
                    v             v
               RETRY_PENDING   ARCHIVED
                    |
                    v
              NEEDS_RECONCILIATION
~~~

Trong thiết kế cạnh tranh nhiều poller, dùng **claim token, optimistic locking, transaction hoặc row locking** được database hỗ trợ để tránh hai worker cùng nhận một hàng chưa xử lý. Chỉ dựa trên `SELECT ... WHERE processed=false` là không đủ nếu nhiều instance cùng poll.

### 14.2. Phân biệt row ID và operation ID

Ví dụ một hàng mới trong bảng staging chứa `row_id=901`, `order_id=ORD-971`. Nếu upstream insert cùng event lần nữa vào `row_id=902`, dedupe theo row ID không phát hiện duplicate nghiệp vụ.

Thiết kế có thể chọn:

- **Row key:** Tốt để ngăn đọc lại một hàng trong một vòng xử lý.
- **Business operation key:** Tốt để ngăn tạo lại cùng đơn khi có nhiều bản ghi khác nhau.
- **Unique constraint:** Thực thi quy tắc bất biến tại DB với concurrency.

Một số hệ thống cần **cả ba**.

### 14.3. Khi side effect nằm ngoài DB

Nếu poller đọc hàng DB rồi gọi HTTP API bên ngoài, không có transaction JDBC đơn giản nào bảo đảm atomic giữa:

1. Đánh dấu hàng đã xử lý trong DB.
2. Gửi request tới HTTP đối tác.
3. Nhận response/ack từ đối tác.

Nên có **outbox/inbox**, idempotency key phía API, trạng thái `OUTCOME_UNKNOWN` và đối soát. Nếu API đối tác không hỗ trợ idempotency, cần đánh giá đặc biệt nguy cơ duplicate trước khi retry.

## 15. Xử lý concurrent messages và scale-out

Trong production, các luồng có thể có:

- Nhiều consumer threads trong một JVM.
- Nhiều pods/instances dùng chung Kafka topic hoặc RabbitMQ queue.
- Hai nguồn khác nhau gửi cùng business operation.
- Replay job chạy đồng thời với live ingestion.

Một `HashSet` hay `SimpleMetadataStore` riêng mỗi instance không đủ để chống trùng toàn hệ thống khi hai instance cùng xử lý một business key.

### 15.1. Thiết kế claim atomic

Giả mã an toàn hơn cho business state:

~~~text
handle(message):
    key = canonicalBusinessKey(message)
    fingerprint = normalizedPayloadFingerprint(message)
    claim = inbox.tryInsertOrLock(key, fingerprint)

    if claim == ALREADY_COMPLETED:
        return inbox.previousResult(key)

    if claim == SAME_KEY_DIFFERENT_PAYLOAD:
        return conflictAndAudit(key)

    if claim == IN_PROGRESS:
        return pendingOrRetryAccordingToContract(key)

    if claim == OWNED:
        result = performBusinessOperationWithIdempotency(key)
        inbox.completeAtomicallyWhenPossible(key, result)
        return result

    return recordRecoveryNeeded(key)
~~~

**Điểm mạnh:** Phân biệt `COMPLETED` và `IN_PROGRESS`, đồng thời không biến một lần claim thành bằng chứng xử lý thành công.

### 15.2. Lease và fencing

Nếu worker A claim key K nhưng mất kết nối, worker B có thể cần tiếp quản. Một lease có timeout giúp phục hồi, nhưng nếu A tỉnh lại và vẫn gửi downstream, có thể xảy ra xử lý song song.

Đối với tác vụ quan trọng, có thể dùng **fencing token hoặc version** để downstream/local state từ chối owner cũ khi có cơ chế hỗ trợ. Timeout của lease **không tự bảo đảm** worker cũ đã dừng tạo side effect.

### 15.3. Payload fingerprint và conflict detection

Cùng operation key nhưng payload khác nhau nên là **conflict**, trừ khi contract định nghĩa rõ cách hợp nhất:

~~~text
K = order:create:T42:ORD-971

Message A: amount=150000, currency=VND
Message B: amount=999000, currency=VND

Nếu K giống nhau nhưng business input khác:
    Không âm thầm bỏ B như duplicate bình thường.
    Không tự chạy B như operation mới.
    Đưa vào kiểm tra contract và lưu bằng chứng conflict.
~~~

Fingerprint nên dựa trên dữ liệu canonical được phép, tránh phụ thuộc vào serialization không ổn định hoặc đưa PII thô vào key/metrics.

## 16. Vòng đời key: thời gian giữ, thay đổi schema, replay

### 16.1. Retention policy

Một idempotency record cần giữ bao lâu? Không có một TTL đúng cho mọi hệ thống. Cần xét:

1. Broker retention và khả năng redelivery.
2. Khoảng thời gian người dùng/đối tác được retry request.
3. Cửa sổ replay thủ công hoặc xử lý backfill.
4. Tính vĩnh viễn của side effect như tạo đơn hàng, thanh toán.
5. Chính sách lưu trữ và xóa dữ liệu theo yêu cầu bảo mật.
6. Chi phí DB/Redis và cơ chế archive key.

Nếu một giao dịch không được phép thực hiện lần hai **vĩnh viễn**, chỉ dùng cache TTL 24 giờ thường không đủ. DB unique constraint hoặc business state phải tiếp tục bảo vệ thao tác.

### 16.2. Key namespace và version

Khi business contract thay đổi, có thể cần versioned namespace:

~~~text
payments:charge:v1:tenant42:order971
payments:charge:v2:tenant42:order971
~~~

**Không tự nâng version key mỗi lần deploy**, vì điều đó sẽ cho phép cùng operation cũ được xử lý lại như một operation mới. Version chỉ thay khi **ngữ nghĩa của thao tác hoặc hợp đồng dedupe thực sự đổi** và có kế hoạch migration.

### 16.3. Replay có và không muốn dedupe

Hai nhu cầu khác nhau:

- **Redelivery/retry:** Cần bảo vệ chống lặp, thường giữ nguyên operation key.
- **Reprocess dữ liệu với phiên bản logic mới:** Có thể cần một job ID hoặc operation type mới để tạo kết quả mới một cách hợp lệ.

Chính sách replay nên quy định **người phê duyệt, trạng thái business hiện tại, key dùng lại hay tạo mới, giới hạn throughput và cách rollback**. Đừng xóa cả metadata store chỉ để “chạy lại cho nhanh”.

## 17. Idempotent receiver và MessageChannel

**MessageChannel** ảnh hưởng đến thread, thứ tự và cách lỗi lan truyền. Nó không tự quyết định một bản tin đã được xử lý đúng một lần.

| Channel/cơ chế | Điều cần lưu ý |
| --- | --- |
| **DirectChannel** | Dispatch đồng bộ thường cùng thread; exception có thể lan tới caller tùy endpoint |
| **ExecutorChannel** | Tách thread; transaction/thread context upstream không tự truyền nguyên vẹn |
| **QueueChannel** | Có buffer message, nhưng tính bền phụ thuộc cấu hình backing store |
| **PublishSubscribeChannel** | Một event có thể tới nhiều subscriber; mỗi subscriber có side effect riêng |
| **MessageBridge** | Nối channel, không đồng nghĩa dedupe business |
| **Pollable channel** | Poller và handler boundary có cơ chế retry/error riêng |

### 17.1. Fan-out cần nhiều idempotency key?

Nếu một event đơn hàng cần:

1. Lưu order ở DB.
2. Gửi thông báo email.
3. Đồng bộ sang hệ thống kế toán.

Một key toàn cục `orderId` với **một cờ processed** có thể sai: DB thành công nhưng email thất bại, rồi bản tin được retry và bị chặn toàn bộ.

Cần phân tách **per-consumer/per-operation key**:

~~~text
order-db:create:T42:ORD-971
notification:send-confirmation:T42:ORD-971
accounting:export-invoice:T42:ORD-971
~~~

Mỗi side effect có ownership, outcome và retry/recovery độc lập. Đối với fan-out, có thể dùng outbox để đảm bảo event cho từng consumer không bị bỏ sót khi một nhánh lỗi.

### 17.2. Header nào có thể mất?

Transformer hoặc gateway có thể tạo message mới, khiến một số headers do ứng dụng thêm bị thay đổi hoặc không được copy theo cách dự kiến. Hãy xác minh `tenantId`, `operationId`, `correlationId` đi xuyên các ranh giới adapter theo contract.

Không dùng message header được cấp ngẫu nhiên tại mỗi hop làm idempotency key; nên lấy key từ **business payload chuẩn hóa hoặc metadata nguồn ổn định**.

## 18. Error handling và duplicate decision

Với inbound adapter, cần có **hai tuyến lỗi rõ ràng**:

1. **Duplicate đã xử lý:** Không chạy business handler lần nữa, nhưng vẫn xác nhận hợp đồng phản hồi/ack.
2. **Message không thể xử lý:** Validation fail, business failure, transient retry exhausted hoặc outcome unknown cần error flow/quarantine/recovery.

### 18.1. Bảng quyết định

| Trạng thái | Hướng xử lý | Có ack nguồn được không? |
| --- | --- | --- |
| Key mới, business COMMITTED | Lưu result, chuyển COMPLETED | Theo cấu hình nguồn, sau khi có bằng chứng commit |
| Key trùng, trạng thái COMPLETED | Return cached result hoặc ack duplicate | Thường được nếu contract/ack đã kiểm chứng |
| Key trùng, đang PROCESSING | Chờ, báo pending, retry có giới hạn | Tùy source và khả năng lưu trạng thái |
| Key trùng, payload khác | Conflict/quarantine | Phải có chính sách rõ, không trả success mù |
| Key đã claim nhưng business FAILED | Retry/rollback hoặc recovery | Không nên ack nếu sẽ làm mất trách nhiệm xử lý |
| Outcome downstream UNKNOWN | Reconciliation trước replay | Chỉ ack nếu trạng thái đã được tiếp nhận bền theo thiết kế |
| MetadataStore không khả dụng | Fail closed hoặc cơ chế dự phòng đã phê duyệt | Không bỏ qua guard rồi xử lý song song tùy tiện |

**Lưu ý:** Một quyết định duplicate **không đồng nghĩa thông báo lỗi nghiệp vụ**. Với nhiều API, duplicate của operation đã hoàn tất có thể được trả lại kết quả thành công ban đầu. Với event consumer, duplicate có thể được ack yên lặng.

### 18.2. Duplicate path thất bại

Nếu discard channel có handler ghi audit thất bại, hành vi exception và ack phụ thuộc cấu hình channel/endpoint. Cần phân loại:

- Audit/metric mang tính best effort có thể không chặn business outcome.
- Ghi trạng thái bắt buộc để xác minh recovery không được bỏ qua.
- Một duplicate đang `PROCESSING` có thể cần retry/đợi, không chỉ log rồi ack.

### 18.3. Không tạo infinite error loop

~~~text
Main handler failure -> error channel
Error channel -> retry same handler
Idempotency marker vẫn "seen"
Handler sau retry bị discard -> giả "success"
~~~

Khi kết nối retry, error channel và idempotent guard, cần có state machine rõ để không biến một failure thành duplicate được ack nhầm hoặc một vòng retry vô hạn.

## 19. Kiến trúc production đề xuất

Với một tác vụ cần chắc chắn và có side effect, kiến trúc có thể gồm:

~~~mermaid
flowchart TD
    S["Inbound adapter / gateway"] --> V["Validate + canonical key"]
    V --> IN["Transactional inbox / atomic claim"]
    IN --> Q{"Operation state"}
    Q -->|New / retryable| H["Business handler"]
    Q -->|Completed| CACHE["Cached result / duplicate ack"]
    Q -->|Processing| P["Pending / lease / retry"]
    Q -->|Conflict| C["Quarantine + audit"]
    H --> DB["Local DB side effect"]
    H --> OUT["Outbox entry for remote call"]
    DB --> DONE["Persist result + COMPLETE"]
    OUT --> WORK["Outbound worker + idempotency key"]
    WORK --> API["Remote API / broker"]
    API --> REC["Reconciliation + outcome"]
    REC --> DONE
    DONE --> ACK["Ack source / reply"]
~~~

Không nhất thiết mọi ứng dụng cần đủ mọi thành phần. Với event chỉ cập nhật bảng DB, **transaction + unique key** có thể đã đáp ứng tốt. Với workflow tích hợp nhiều hệ thống ngoài, **inbox/outbox + idempotency + reconciliation** thường cần được đánh giá.

### 19.1. Ví dụ một transaction local

Giả mã có chú thích:

~~~java
@Transactional
public OrderResult receive(CreateOrder command) {
    String key = operationKey(command);

    InboxEntry existing = inbox.findAndLockOrClaim(key);

    if (existing.isCompleted()) {
        return existing.previousResult();
    }
    if (existing.isOwnedByAnotherWorker()) {
        throw new ProcessingInProgressException(key);
    }
    if (existing.hasDifferentPayloadFingerprint(command)) {
        throw new IdempotencyConflictException(key);
    }

    // Các thay đổi dưới đây phải cùng transaction khi dùng local JDBC.
    Order order = orderRepository.createIfAbsent(command);
    inbox.markCompleted(key, order.toResult());
    return order.toResult();
}
~~~

Đây là **mã thiết kế**, không phải một phương thức Spring Data/JPA có sẵn: `findAndLockOrClaim`, `createIfAbsent`, `previousResult` và các exception là API do ứng dụng định nghĩa. Khi triển khai, phải bảo vệ trường hợp **hai transaction cùng không thấy key**, dùng unique constraint/locking và xử lý conflict SQL phù hợp.

### 19.2. Outbox cho side effect ngoài database

Trong cùng transaction với cập nhật business state, hệ thống có thể ghi **outbox event**. Một outbound worker riêng đọc outbox và gửi tới hệ thống ngoài cùng **idempotency key**. Nếu gửi thành công nhưng chưa đánh dấu outbox đã gửi, retry sẽ có cùng key, hạn chế tác động trùng ở downstream.

Không gọi HTTP đối tác trực tiếp trong một transaction dài rồi mặc định có exactly-once. Giao dịch local DB không thể tự rollback những side effects đã xảy ra ở hệ thống ngoài.

## 20. Test matrix cho idempotent receiver

Kiểm thử phải chứng minh **behavior thực** của handler, store, transaction và source adapter. Không chỉ unit test rằng `MetadataStoreSelector` trả true/false.

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Message lần đầu | Key mới | Handler gọi đúng một lần, outcome lưu |
| Redelivery sau success | Cùng operation key | Không tạo side effect lần hai |
| Different operations | Khác key hợp lệ | Cả hai được xử lý |
| Same key, different payload | Fingerprint khác | Conflict/quarantine; không lặng lẽ bỏ |
| Missing key | Thiếu tenant/event ID | Reject/validation flow rõ |
| Concurrent duplicate | Hai thread cùng key | Atomic claim; không cả hai đều thực hiện effect |
| Multiple instances | Hai pods cùng shared store | Không duplicate do mỗi JVM có cache riêng |
| Restart | Restart app giữa deliveries | Trạng thái processed còn tồn tại nếu yêu cầu |
| Crash after marker | Marker ghi, business chưa commit | Message không bị drop vĩnh viễn |
| Commit then ack failure | DB commit, broker redelivery | Duplicate được nhận diện, ack sau xử lý đúng |
| HTTP outcome unknown | Server có thể đã commit | Reconcile; không tự gửi lặp |
| Store outage | MetadataStore mất kết nối | Fail-safe theo policy, không bypass guard |
| Key TTL expiry | Replay event cũ sau cleanup | Hành vi theo retention contract được kiểm chứng |
| Reply gateway | HTTP retry cùng key | Có cached result/pending/conflict đúng contract |
| Fan-out partial failure | Consumer A success, B fail | A không lặp; B còn đường retry |
| DLQ replay | Replay có owner và approval | Giữ nguyên business key và audit trail |

### 20.1. Test duplicate header và discard

Với **IdempotentReceiverInterceptor**, nên assert:

1. Khi key mới, handler được gọi và có kết quả dự kiến.
2. Khi key trùng và **không có discard channel**, hành vi duplicate header/handler của phiên bản đang dùng được kiểm chứng.
3. Khi **có discard channel**, duplicate đi đúng tuyến và business handler **không tạo side effect**.
4. Duplicate path lỗi thì source ack/commit theo chính sách đã chọn.
5. Request-reply gateway có reply đúng contract.

### 20.2. Test lỗi và rollback

Các điểm fail injection:

~~~text
F1: before key claim
F2: after key claim, before business handler
F3: after local DB side effect, before transaction commit
F4: after transaction commit, before broker ack
F5: after remote API side effect, before response
F6: during failure archive/DLQ publish
F7: during process restart / rebalance
~~~

Tại mỗi điểm, kiểm tra **không mất operation** và **không có business effect lặp ngoài contract**.

### 20.3. Kiểm thử producer độc lập

Không chỉ tự gửi một message hai lần trong cùng test. Hãy mô phỏng **hai source khác nhau** hoặc một event được republish ở ID transport mới nhưng cùng business operation key. Cách này phát hiện thiết kế dedupe sai vì quá phụ thuộc message ID của framework hoặc broker.

## 21. Metrics, logging và audit

### 21.1. Các chỉ số nên có

| Metric | Mục đích |
| --- | --- |
| `inbound_messages_total` | Tổng message nhận theo source |
| `idempotent_accepted_total` | Message/key mới được chấp nhận |
| `idempotent_duplicate_total` | Duplicate được phát hiện |
| `idempotent_conflict_total` | Cùng key nhưng khác payload theo contract |
| `idempotency_store_error_total` | Lỗi store hoặc atomic claim |
| `idempotency_in_progress` | Số operation chưa có outcome cuối |
| `idempotency_completed_total` | Operation thực sự hoàn tất |
| `idempotency_reconciled_total` | Outcome unknown đã đối soát |
| `idempotency_replay_total` | Replay được phê duyệt |
| `inbound_ack_latency` | Thời gian từ nhận đến ack/reply |
| `inbound_redelivery_total` | Source redelivery quan sát được |
| `inbox_oldest_pending_age` | Tuổi operation chưa hoàn tất lâu nhất |

Không dùng **operationId, tenant ID hoặc message ID** làm metric label có cardinality cao nếu sẽ tạo hàng triệu series. Đưa correlation metadata vào tracing/log được phân quyền và hạn chế hiển thị dữ liệu nhạy cảm.

### 21.2. Structured logging

~~~json
{
  "event": "idempotent_receiver.duplicate_detected",
  "flow": "orders-inbound",
  "source": "jms-orders",
  "operationType": "CREATE_ORDER",
  "operationKeyRef": "hash:7c5d...",
  "decision": "ALREADY_COMPLETED",
  "messageCorrelationId": "trace-84021",
  "processingOutcome": "cached-result",
  "occurredAt": "2026-11-23T08:10:15Z"
}
~~~

Đây là ví dụ **schema ứng dụng**, không phải dữ liệu Spring Integration tự ghi đầy đủ. Tùy chính sách, có thể lưu hash hoặc reference thay vì business key rõ. Không log raw token, SFTP password, Authorization header, dữ liệu cá nhân hoặc payload của đối tác nếu không cần.

### 21.3. Những cảnh báo đáng ưu tiên

- Duplicate rate tăng đột biến sau deploy, restart hoặc broker rebalance.
- Inbox/metadata store không khả dụng.
- Operation ở `PROCESSING` quá lâu hoặc lease hết hạn nhiều lần.
- `SAME_KEY_DIFFERENT_PAYLOAD` xuất hiện nhiều.
- DLQ/backlog pending tăng trong khi ack rate vẫn cao.
- Key store bị eviction bất thường hoặc memory reset.
- Duplicate gây timeout trên HTTP inbound gateway.
- Cùng operation được xử lý nhiều lần bởi hai instance.
- Số trạng thái `OUTCOME_UNKNOWN` tăng sau sự cố downstream.

## 22. Runbook xử lý duplicate và idempotency failure

### 22.1. Bước 1 — Xác định phạm vi

Thu thập:

1. Source adapter, queue/topic/file, poller và endpoint.
2. Environment, tenant, business operation và correlation ID.
3. Lần cuối business handler xử lý thành công.
4. Tình trạng idempotency store, inbox, database transaction.
5. Retry, broker redelivery, offset/ack và dead-letter state.
6. Những deployment/restart/rebalance hoặc thay đổi key strategy gần đây.

### 22.2. Bước 2 — Phân loại sự cố

| Nhóm | Dấu hiệu | Hành động |
| --- | --- | --- |
| **Harmless duplicate** | Inbox COMPLETED, payload khớp | Ack hoặc trả cached result theo contract |
| **Missing business effect** | Key đã marked nhưng chưa có outcome | Giữ/reopen theo quy trình; đối soát trước xử lý lại |
| **Concurrent processing** | Hai worker claim cùng key | Kiểm tra atomic store, unique constraint, lease/fencing |
| **Store reset/eviction** | Duplicate sau restart hoặc TTL | Khôi phục store/retention, xem side effects bị lặp |
| **Upstream bad key** | Cùng key cho hai request khác nội dung | Quarantine, sửa contract với producer |
| **Downstream outcome unknown** | Timeout sau khi gửi | Query trạng thái đối tác trước replay |
| **Ack mismatch** | Source ack trước commit business | Sửa transaction/error path, điều tra message có thể mất |

### 22.3. Bước 3 — Replay an toàn

Trước khi replay:

- Đọc lại business state và kết quả downstream nếu có.
- Xác nhận operation ID gốc và payload fingerprint.
- Xác định cần giữ key hay tạo **một operation mới có chủ ý**.
- Xác nhận owner/approval nếu liên quan thanh toán, dữ liệu nhạy cảm hoặc production.
- Giới hạn replay rate và chạy canary nếu backlog lớn.
- Ghi audit: ai replay, vì sao, kết quả nào, có tạo side effect hay không.

**Không xóa bảng inbox hoặc flush toàn bộ Redis chỉ để replay một message.** Hành động đó có thể cho phép hàng nghìn operation đã hoàn tất bị lặp.

### 22.4. Bước 4 — Đóng sự cố

Chỉ đóng khi:

1. Không còn operation bị bỏ qua dù chưa hoàn tất.
2. Không có side effect duplicate ngoài phạm vi được chấp nhận.
3. Source checkpoint/ack/offset tương thích với business state.
4. Inbox, metadata store và DLQ đủ bền, có owner và monitoring.
5. Chênh lệch với downstream đã được đối soát.
6. Root cause ở key strategy, transaction, broker hoặc concurrency đã được xử lý hoặc ghi ngoại lệ rõ.

## 23. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `MessageHeaders.ID` làm business key | Retry nhận message mới có ID khác | Dùng stable operation ID |
| Dùng `orderId` cho cả CREATE và UPDATE | Chặn event hợp lệ | Namespace theo operation/version |
| `SimpleMetadataStore` cho cluster nhiều pods | Mỗi pod tự coi cùng key là mới | Shared atomic persistent store |
| Check-then-put không atomic | Hai worker cùng xử lý | CAS/unique constraint/transaction |
| Ghi `seen` rồi coi là `COMPLETED` | Crash làm mất business operation | State machine/transactional inbox |
| Discard duplicate mặc định cho HTTP gateway | Caller không nhận reply đúng | Cached result/pending/conflict response |
| Filter SFTP file như bằng chứng tất cả rows đã xử lý | Record lỗi bị bỏ qua | Per-record business state và recovery |
| Xóa key sau mọi timeout | Lặp side effect đã commit bên ngoài | Reconciliation trước retry |
| Set TTL quá ngắn | Replay cũ tạo side effect lần hai | Retention theo business window |
| Không kiểm tra payload fingerprint | Cùng key nhưng dữ liệu khác bị bỏ | Conflict detection |
| Một key chung cho mọi subscriber | Nhánh A thành công chặn nhánh B retry | Per-operation/per-consumer state |
| Coi broker duplicate flag là đủ | Republish event không có redelivery flag | Business operation key |
| Không test ack sau duplicate | Message mất hoặc redeliver vô hạn | Integration test theo adapter/container |
| Lưu payload/key nhạy cảm vào metric/log | Lộ dữ liệu, cardinality quá lớn | Redaction, reference và metric labels thấp |
| Tạo key mới khi replay | Mất idempotency xuyên replay | Giữ operation ID, tách replay audit ID |
| Retry vô hạn khi store không truy cập được | Quá tải source và backlog | Fail-safe, backoff, alert và capacity plan |
| Không có cleanup/retention policy | Metadata store phình to hoặc eviction mù | Lifecycle, archive, review theo rủi ro |

## 24. Tình huống thực hành: SFTP, JMS và HTTP cùng tạo đơn hàng

Hệ thống **Learning Orders** nhận đơn từ:

- Một file CSV qua SFTP mỗi giờ.
- Một hàng đợi JMS chứa event tạo đơn.
- Một HTTP inbound gateway phục vụ client gửi đơn trực tiếp.

Tất cả cùng chuẩn hóa về:

~~~yaml
# Contract nghiệp vụ minh họa; không phải headers Spring mặc định
tenantId: T42
operationType: CREATE_ORDER
orderId: ORD-971
operationVersion: 1
payloadFingerprint: sha256-of-canonical-business-fields
correlationId: trace-84021
source:
  adapter: sftp-or-jms-or-http
idempotency:
  key: order:create:v1:T42:ORD-971
~~~

### 24.1. Đợt nhận đầu tiên

SFTP mang record `ORD-971`. Receiver claim key, ghi transaction DB và result `COMPLETED`. File checkpoint được cập nhật theo quy trình nguồn. Hệ thống giữ metadata cần thiết cho audit.

### 24.2. JMS gửi lại

Một event JMS có cùng business key đi tới sau đó. Receiver thấy `COMPLETED` cùng fingerprint; không gọi createOrder lần thứ hai. Broker ack theo thiết kế và log duplicate với source = JMS.

### 24.3. HTTP client retry

Client không nhận được HTTP response ban đầu nên gửi lại cùng Idempotency-Key. API đọc result đã lưu và trả lại **order reference** theo contract, thay vì chỉ discard và khiến client tiếp tục timeout.

### 24.4. Payload khác nhưng key trùng

Client gửi amount khác nhưng cùng operation ID. Hệ thống ghi `IDEMPOTENCY_CONFLICT`, không âm thầm bỏ request và không tạo một đơn thứ hai. Owner hoặc client cần xác minh đây là request sai hay một operation mới chưa được định danh đúng.

### 24.5. Crash giữa claim và commit

Giả sử pod crash sau khi mark `PROCESSING` nhưng trước commit. Worker kế tiếp nhìn thấy state chưa hoàn tất, kiểm tra lease và business outcome rồi tiếp quản theo chính sách. Không được coi `PROCESSING` là `COMPLETED`.

### 24.6. Luồng kiểm chứng

~~~mermaid
flowchart TD
    A["Source event / file record / HTTP request"] --> B["Canonical key + fingerprint"]
    B --> C["Atomic inbox claim"]
    C --> D{"Existing state?"}
    D -->|Completed + same payload| E["Ack / cached result"]
    D -->|Different payload| F["Conflict + audit"]
    D -->|Processing| G["Pending / reconcile"]
    D -->|New| H["Transactional business operation"]
    H --> I{"Commit thành công?"}
    I -->|Có| J["Store COMPLETED + result"]
    I -->|Không| K["Retry/recovery theo source"]
    J --> E
    K --> L["No lost message + failure evidence"]
~~~

## 25. Bài tập tự kiểm tra

### Bài 1. Message ID đổi sau replay

**Tình huống:** Kafka event được republish ở offset mới, Spring Message ID mới, nhưng `businessEventId` không đổi. Receiver dùng message ID làm key.

**Đáp án:** Receiver có thể xử lý trùng. Cần stable business event/operation key nếu muốn chống duplicate xuyên republish, không chỉ transport ID.

### Bài 2. Key được lưu trước handler

**Tình huống:** MetadataStore đã đánh dấu key nhưng handler lỗi trước DB commit. Source redeliver và selector trả duplicate.

**Đáp án:** Có nguy cơ mất operation. Cần đồng bộ trạng thái với transaction nghiệp vụ, hoặc inbox `PROCESSING/COMPLETED` với cơ chế phục hồi và kiểm tra outcome.

### Bài 3. Hai pods chạy cùng lúc

**Tình huống:** Mỗi pod có `SimpleMetadataStore` riêng. Cả hai nhận cùng operation.

**Đáp án:** Cả hai có thể coi key là mới. Cần shared atomic metadata store hoặc unique constraint/transactional inbox để phối hợp giữa instances.

### Bài 4. HTTP duplicate bị discard

**Tình huống:** HTTP inbound gateway nhận lại cùng request; duplicate route chỉ log và không gửi reply.

**Đáp án:** Client có thể timeout tiếp. Nên trả cached result, pending hoặc conflict theo contract HTTP; kiểm thử request-reply và không giả thành công khi business chưa commit.

### Bài 5. SFTP file có nhiều records

**Tình huống:** Filter đánh dấu CSV đã tải, nhưng record thứ hai trong file lỗi. Sau restart file không được đọc lại.

**Đáp án:** File accept-once không xác nhận từng record thành công. Cần per-record state, recovery/quarantine và chính sách quản lý file checkpoint.

### Bài 6. Same key, different payload

**Tình huống:** Hai request dùng cùng idempotency key nhưng amount khác nhau.

**Đáp án:** Không tự coi là duplicate hợp lệ. So fingerprint/canonical data và trả conflict hoặc đưa vào đối soát theo contract.

### Bài 7. TTL ngắn hơn replay window

**Tình huống:** Dedupe key bị xóa sau một ngày nhưng hệ thống cho phép replay event trong một tuần.

**Đáp án:** Sau khi key hết hạn, event cũ có thể tạo side effect mới. Cần điều chỉnh retention hoặc bảo vệ tại tầng nghiệp vụ lâu hơn.

### Bài 8. Fan-out hai consumer

**Tình huống:** Consumer A lưu DB thành công; B gửi email lỗi. Một cờ `processed=true` chung làm cả hai không được chạy lại.

**Đáp án:** Thiết kế sai ranh giới operation. Tách trạng thái idempotency cho từng consumer/side effect hoặc áp outbox cho phân phối đáng tin.

## 26. Checklist triển khai idempotent receiver

1. **Xác định operation:** Biết chính xác tác vụ nghiệp vụ cần không lặp.
2. **Key ổn định:** Tenant + operation + business ID/version theo contract, không phụ thuộc header ngẫu nhiên.
3. **Kiểm tra fingerprint:** Cùng key nhưng payload khác phải có conflict policy.
4. **Đặt guard sớm:** Trước side effect cần bảo vệ, sau bước chuẩn hóa key đáng tin.
5. **Hiểu interceptor:** Duplicates có thể được đánh dấu header; cấu hình discard/handling và test handler invocation.
6. **Chọn store đúng:** Demo có thể in-memory; production multi-instance cần shared atomic/durable store hoặc inbox DB.
7. **Không đánh đồng seen/completed:** Phân biệt PROCESSING, COMPLETED, FAILED và OUTCOME_UNKNOWN.
8. **Xử lý concurrency:** Atomic claim, unique constraint, lease/fencing khi cần.
9. **Phù hợp source:** File/SFTP checkpoint, JMS/AMQP ack, Kafka offset, JDBC row claim, HTTP reply.
10. **Transaction rõ:** Khi có DB local, đồng bộ inbox và side effect trong cùng transaction nếu khả thi.
11. **Downstream idempotency:** Dùng stable key và reconciliation cho remote API/side effect.
12. **Retry hữu hạn:** Phân biệt retryable/non-retryable; tránh nhiều tầng retry không giới hạn.
13. **Recovery bền vững:** DLQ/quarantine/error flow có owner, retention, replay policy và kiểm chứng.
14. **Replay đúng key:** Giữ operation ID, tách replay ID cho audit.
15. **Retention có căn cứ:** TTL đủ cho replay và correctness window, tránh eviction không kiểm soát.
16. **Scale-out an toàn:** Test hai pods/threads, restart và store outage.
17. **Gateway contract đúng:** Duplicate trả kết quả, trạng thái đang xử lý hoặc conflict có ý nghĩa.
18. **Fan-out độc lập:** Mỗi side effect/consumer có trạng thái riêng khi cần.
19. **Observability:** Dedupe rate, conflict, pending age, store error, redelivery, reconciliation.
20. **Security:** Redact secrets/PII, kiểm soát quyền metadata store và replay tool.
21. **Kiểm thử failure injection:** Crash trước/sau claim, commit, ack và remote call.
22. **Runbook:** Có hướng dẫn tìm operation mất, duplicate thật và cách replay an toàn.

## 27. Tổng kết

**Idempotent receiver cho inbound adapter** là phương pháp bảo vệ luồng Spring Integration trước redelivery, retry và replay tạo tác vụ trùng. **IdempotentReceiverInterceptor**, **MessageSelector** và **MetadataStoreSelector** hỗ trợ nhận diện duplicate tại handler; các file/SFTP accept-once filters hỗ trợ tránh đọc lại nguồn. Nhưng **không nên xem một cờ seen trong metadata store là bằng chứng nghiệp vụ đã thành công**.

Thiết kế tin cậy cần bắt đầu từ **business operation key đúng**, tiếp tục bằng **atomic claim và durability**, **transactional inbox hoặc unique constraint** khi phù hợp, **idempotency của downstream**, và **ack/checkpoint đúng theo adapter**. HTTP gateway cần reply có hợp đồng; JMS/AMQP/Kafka cần kiểm thử redelivery và commit; File/SFTP cần tách file-level filter khỏi per-record outcome; JDBC cần trạng thái hàng và transaction. Sau cùng, **retry, dead-letter, replay, correlation, monitoring và reconciliation** phải được kết nối để hệ thống không chỉ giảm duplicate mà còn **không bỏ sót thao tác hợp lệ khi xảy ra lỗi**.
