# Partition key

Khi một ứng dụng phát nhiều event cùng lúc, hệ thống cần quyết định event nào đi tới partition, queue hoặc consumer nào. Quyết định này ảnh hưởng trực tiếp tới thứ tự xử lý, khả năng mở rộng và phân phối tải. Partition key là giá trị ổn định được dùng để gom các event có quan hệ với nhau vào cùng một vùng xử lý.

Trong hệ thống Spring Modulith, cần phân biệt hai lớp định tuyến. Ở bên trong ứng dụng, Spring Modulith phân phối application event tới các listener đã đăng ký theo kiểu event và ranh giới module. Khi event được externalize ra message broker như Kafka, partition key thuộc lớp vận chuyển và quyết định cách broker phân vùng thông điệp. Một partition key được chọn tốt giúp giữ thứ tự trong phạm vi nghiệp vụ cần thiết mà vẫn phân phối tải giữa các partition.

Bài này giải thích cách chọn partition key theo aggregate, tenant và yêu cầu thứ tự; cách đưa key vào luồng event; các giới hạn khi thay đổi số partition; cách xử lý hot partition, duplicate và schema; cùng những kiểm thử cần có.

## 1. Partition key giải quyết vấn đề gì?

Giả sử hệ thống xử lý các event OrderPlaced, PaymentCaptured và OrderShipped. Với cùng một đơn hàng, nghiệp vụ có thể yêu cầu các event được xử lý theo thứ tự phát sinh. Trong khi đó, event của những đơn hàng khác nhau có thể xử lý song song.

Nếu mọi event được gửi vào một partition duy nhất, thứ tự dễ quản lý nhưng thông lượng bị giới hạn bởi một luồng xử lý. Nếu phân phối ngẫu nhiên vào nhiều partition, hệ thống có thể tăng mức song song nhưng các event của cùng đơn hàng có thể tới những consumer khác nhau và hoàn tất không đúng thứ tự.

Partition key tạo ra quy tắc nhóm:

- Các event có cùng key được đưa về cùng partition theo thuật toán phân vùng của broker.
- Các key khác nhau có thể được phân phối lên các partition khác nhau.
- Với broker bảo đảm thứ tự trong từng partition như Kafka, event của cùng key có thể được đọc theo thứ tự ghi trong partition đó.

Ví dụ, dùng orderId làm key:

~~~text
Partition 0: order-A / OrderPlaced
              order-A / PaymentCaptured
              order-A / OrderShipped

Partition 1: order-B / OrderPlaced
              order-B / PaymentFailed

Partition 2: order-C / OrderPlaced
              order-C / PaymentCaptured
~~~

Các event của order-A cùng đi vào partition 0; order-B và order-C có thể được xử lý độc lập ở partition khác. Việc chọn partition cụ thể trong ví dụ chỉ minh họa; broker quyết định bằng partitioner và cấu hình thực tế.

Partition key không làm cho toàn hệ thống có thứ tự toàn cục. Nó xác định phạm vi event cần được gom cùng nhau để broker có thể bảo đảm thứ tự trong phạm vi partition.

## 2. Phân biệt định tuyến module và phân vùng broker

Spring Modulith tổ chức module dựa trên ranh giới nghiệp vụ. ApplicationEventPublisher phát event trong ứng dụng, còn các listener như @ApplicationModuleListener nhận event phù hợp. Event Publication Registry có thể theo dõi publication cho từng listener và hỗ trợ phục hồi publication chưa hoàn tất.

Các cơ chế đó không tự động phân phối listener theo partition key. Trong luồng nội bộ, việc listener nào nhận event được xác định bởi loại event và cấu hình listener. Nếu listener chạy bất đồng bộ, thứ tự và concurrency phụ thuộc cơ chế thực thi cùng thiết kế ứng dụng.

Khi event được chuyển qua ranh giới tiến trình tới broker, partition key mới tham gia quyết định partition hoặc nhóm xử lý. Một luồng điển hình:

~~~mermaid
flowchart LR
    A[Module nghiệp vụ] --> B[Application event]
    B --> C[Event Publication Registry]
    C --> D[Externalization hoặc outbox relay]
    D --> E[Message broker]
    E --> F[Partitioner dùng partition key]
    F --> G[Partition 0]
    F --> H[Partition 1]
    F --> I[Partition 2]
    G --> J[Consumer group]
    H --> J
    I --> J
~~~

Ví dụ, module Order phát OrderPlaced. Một listener nội bộ có thể cập nhật read model trong cùng ứng dụng. Nếu event cần gửi tới các service bên ngoài, adapter hoặc relay chuyển nó thành message có key là orderId. Cùng một event có thể phục vụ cả listener nội bộ và luồng externalization; hai đường giao event có thể có semantics, retry và trạng thái khác nhau.

Không nên gán ý nghĩa partition key cho @ApplicationModuleListener nếu implementation không sử dụng key đó. Hãy đặt key ở lớp transport khi tạo message cho broker.

## 3. Chọn partition key theo aggregate

### 3.1. Aggregate ID là lựa chọn mặc định tốt

Nếu cần giữ thứ tự các thay đổi của cùng một aggregate, dùng aggregate ID làm partition key. Ví dụ:

- orderId cho vòng đời đơn hàng.
- accountId cho các thay đổi số dư tài khoản.
- shipmentId cho các cập nhật vận chuyển.
- customerId nếu các event cần thứ tự ở phạm vi khách hàng.

Key nên phản ánh đúng phạm vi mà nghiệp vụ yêu cầu tuần tự hóa. Nếu hai event chỉ cần thứ tự trong cùng một đơn hàng, không cần dùng customerId khiến mọi đơn hàng của một khách hàng bị gom vào cùng partition.

Ví dụ event có định danh aggregate và sequence:

~~~java
public record OrderEvent(
        UUID eventId,
        UUID orderId,
        long orderVersion,
        String eventType,
        Instant occurredAt
) {}
~~~

Khi chuyển event sang Kafka, adapter dùng orderId làm key:

~~~java
@Component
@RequiredArgsConstructor
class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event
    ) {
        String key = event.orderId().toString();

        return kafkaTemplate.send(
                "order-events",
                key,
                event
        );
    }
}
~~~

Ví dụ dùng Spring Kafka để minh họa cách truyền key. Serializer, topic, broker acknowledgement và xử lý lỗi cần cấu hình theo ứng dụng. Nếu dùng Spring Modulith externalization hoặc outbox relay, hãy chuyển partition key từ event/metadata sang message record tại adapter tương ứng; chi tiết API phụ thuộc integration và phiên bản thư viện.

### 3.2. Key phải ổn định qua vòng đời event

Các event cùng aggregate phải tạo ra cùng một key. Không dùng giá trị thay đổi theo từng lần publish như timestamp, random UUID mới hoặc ID của lần retry.

Key cần được xác định một lần từ dữ liệu nghiệp vụ có định danh ổn định. Khi retry hoặc replay, dùng lại key gốc. Nếu tạo key mới cho mỗi lần gửi, broker có thể đưa cùng event vào partition khác, làm mất tính tuần tự mong muốn.

Đối với event được lưu trong outbox, có thể lưu aggregate_id riêng và dùng nó làm key khi relay gửi message. Không nên suy ra key từ JSON payload bằng cách parse tùy tiện ở nhiều nơi; hãy có một quy tắc mapping tập trung và được kiểm thử.

### 3.3. Key khác event ID

Event ID định danh một lần phát sinh event và thường được dùng cho deduplication. Partition key xác định nhóm event cần cùng partition. Hai giá trị này có mục đích khác nhau:

| Giá trị | Ví dụ | Mục đích |
|---|---|---|
| eventId | evt-7f... | Nhận diện event, chống xử lý trùng |
| aggregateId | order-42 | Gom các event của một aggregate vào cùng partition |
| correlationId | checkout-91 | Liên kết các bước trong một luồng nghiệp vụ |
| causationId | evt-previous | Chỉ ra event/command gây ra event hiện tại |

Không dùng eventId làm partition key nếu mục tiêu là giữ thứ tự theo aggregate; mỗi event có eventId khác nhau nên sẽ không được gom chung.

## 4. Chọn phạm vi key: aggregate, tenant hay kết hợp?

Không có một key đúng cho mọi ứng dụng. Hãy chọn phạm vi nhỏ nhất vẫn đáp ứng yêu cầu thứ tự và cô lập tải.

| Partition key | Khi phù hợp | Rủi ro |
|---|---|---|
| aggregateId | Cần thứ tự trong một đơn hàng/tài khoản/giao dịch | Nhiều aggregate nóng có thể lệch tải |
| tenantId | Mọi event của tenant cần tuần tự hoặc tenant là đơn vị xử lý | Tenant lớn có thể tạo hot partition |
| tenantId + aggregateId | Cần tránh trùng ID giữa tenant và giữ thứ tự trong aggregate | Cần chuẩn hóa cách tạo composite key |
| customerId | Các aggregate của một khách hàng phải được xử lý tuần tự | Một khách hàng hoạt động nhiều có thể tạo điểm nóng |
| eventId | Chỉ khi không cần gom event theo aggregate | Không giữ thứ tự theo nghiệp vụ |

Với multi-tenant, nếu aggregate ID chỉ duy nhất trong phạm vi tenant, composite key có thể là:

~~~java
String partitionKey = tenantId + ":" + orderId;
~~~

Nếu aggregate ID đã duy nhất toàn hệ thống và tenant không phải phạm vi tuần tự hóa, có thể chỉ dùng aggregate ID. Tránh đưa tenant vào key chỉ vì hệ thống có nhiều tenant; mỗi key nên có lý do nghiệp vụ.

Composite key cần chuẩn hóa encoding để tránh nhập nhằng. Nếu thành phần có thể chứa dấu phân cách, hãy dùng định dạng có escaping, length-prefix hoặc encoding ổn định. Không để các giá trị như tenant-a:order-b được tạo từ hai cách serialize khác nhau.

## 5. Kafka partitioning và bảo đảm thứ tự

Kafka lưu message trong topic theo partition. Producer gửi key và partitioner chọn partition tương ứng. Với partitioner mặc định, các message có cùng key thường được ánh xạ tới cùng partition khi cấu hình partition count và thuật toán không thay đổi.

Trong một partition, Kafka giữ thứ tự offset. Consumer đọc partition theo thứ tự đó. Trong consumer group, tại một thời điểm một partition được gán cho một consumer trong group. Vì vậy, nếu mọi event của một aggregate cùng key và cùng partition, consumer group có thể xử lý chúng theo thứ tự đọc của partition.

Tuy nhiên, cần phân biệt ba khái niệm:

- Thứ tự ghi: thứ tự message được broker append vào partition.
- Thứ tự đọc: consumer nhận message theo offset trong partition.
- Thứ tự hoàn tất nghiệp vụ: thời điểm side effect của consumer thực sự commit.

Nếu consumer xử lý bất đồng bộ nhiều message trong cùng partition rồi commit kết quả không theo thứ tự, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự đọc. Khi nghiệp vụ yêu cầu tuần tự, consumer cần xử lý tuần tự trong partition hoặc dùng cơ chế sequence/version để phát hiện và chặn event đến sai thứ tự.

Một consumer có thể kiểm tra orderVersion:

~~~java
@Transactional
public void handle(OrderEvent event) {
    OrderProjection projection = projections.get(event.orderId());

    if (event.orderVersion() <= projection.version()) {
        return; // event cũ hoặc đã được áp dụng
    }

    if (event.orderVersion() != projection.version() + 1) {
        throw new OutOfOrderEventException(
                event.orderId(),
                projection.version(),
                event.orderVersion()
        );
    }

    projection.apply(event);
    projections.save(projection);
}
~~~

Ví dụ này giả định projection bắt đầu từ version liên tục và mọi version đều được phát. Nếu event được lọc hoặc snapshot đã nhảy version, cần điều chỉnh quy tắc sequence tương ứng. Không nên dùng timestamp thay thế cho version nếu aggregate có sequence đáng tin cậy.

## 6. Số partition và thay đổi partition count

Số partition ảnh hưởng tới mức song song tối đa, khả năng phân phối tải và ánh xạ key. Tăng partition count có thể giúp tăng concurrency, nhưng không phải thao tác trung tính đối với ordering.

Với partitioner dựa trên hash(key) modulo số partition, khi số partition thay đổi, cùng một key có thể được ánh xạ tới partition khác. Message cũ vẫn nằm ở partition cũ, message mới có thể sang partition mới. Consumer đọc hai partition độc lập, vì vậy không còn một luồng offset duy nhất bảo đảm thứ tự giữa toàn bộ lịch sử của key đó.

Trước khi tăng partition count cho topic cần thứ tự theo aggregate, hãy đánh giá:

- Có thể chấp nhận thay đổi thứ tự trong giai đoạn chuyển đổi không?
- Có cần drain hoặc pause producer trước khi thay đổi không?
- Có thể tạo topic phiên bản mới và chuyển đổi theo checkpoint không?
- Consumer có kiểm tra aggregate sequence để phát hiện event đến sai thứ tự không?
- Các hệ thống downstream có dựa vào thứ tự broker hay có cơ chế version riêng?

Nếu cần giữ thứ tự nghiêm ngặt qua nhiều năm, phải có kế hoạch partitioning và migration từ đầu. Một lựa chọn là dùng topic mới với quy tắc phân vùng mới, replay/catch-up có kiểm soát rồi chuyển consumer. Chi tiết triển khai phụ thuộc broker và yêu cầu downtime.

Không chọn số partition chỉ dựa trên số consumer mong muốn. Hãy cân nhắc thông lượng, kích thước message, số aggregate hoạt động đồng thời, độ trễ và chi phí quản trị.

## 7. Hot partition và phân phối tải

Partition key tốt giữ thứ tự nhưng cũng có thể tạo hot partition. Nếu một key phát sinh lượng event lớn hơn nhiều key khác, toàn bộ event của key đó dồn về một partition. Tăng số consumer không giúp xử lý nhanh hơn nếu partition nóng vẫn chỉ được một consumer trong group sở hữu tại một thời điểm.

Dấu hiệu hot partition:

- Một partition có lag cao trong khi các partition khác gần như rỗng.
- Throughput hoặc byte rate chênh lệch lớn giữa các partition.
- Consumer xử lý một số key chiếm phần lớn thời gian.
- Một tenant hoặc aggregate tạo lượng event vượt xa phần còn lại.

Các cách xử lý:

1. Đo phân phối key trước khi thay đổi chiến lược.
2. Xác định liệu thứ tự cần thiết ở phạm vi aggregate, tenant hay toàn bộ entity.
3. Nếu key quá rộng, thu hẹp phạm vi tuần tự hóa, ví dụ từ customerId xuống orderId khi nghiệp vụ cho phép.
4. Nếu một aggregate thực sự cần thông lượng rất cao, xem xét chia nhỏ aggregate hoặc thiết kế luồng xử lý theo sequence có kiểm soát.
5. Tách luồng event có đặc tính tải khác nhau sang topic riêng nếu điều đó phản ánh ranh giới nghiệp vụ rõ ràng.

Không thêm random suffix vào key chỉ để chia tải nếu các event của cùng aggregate phải có thứ tự. Làm vậy sẽ phân tán cùng một aggregate ra nhiều partition. Chỉ dùng sharding key có suffix khi có một cơ chế sequence/merge rõ ràng ở phía consumer và nghiệp vụ chấp nhận sự phức tạp đó.

## 8. Null key, key thay đổi và duplicate

### 8.1. Null key

Nếu producer gửi message không có key, partitioner có thể phân phối theo round-robin, sticky hoặc thuật toán cụ thể của client. Cách phân phối này phù hợp khi không cần thứ tự theo aggregate, nhưng không bảo đảm các event liên quan được gom cùng partition.

Với luồng cần ordering, hãy từ chối hoặc cảnh báo event thiếu key trước khi gửi. Đừng âm thầm thay key bằng eventId hoặc timestamp.

### 8.2. Key thay đổi

Một aggregate cần có key ổn định. Nếu key đổi giữa các phiên bản ứng dụng, event trước và sau thay đổi có thể nằm ở hai partition khác nhau. Khi thay đổi định danh hoặc chiến lược key, cần migration plan và kiểm tra sequence.

Nếu aggregate được hợp nhất hoặc chuyển tenant, hãy xác định mốc chuyển đổi và cách xử lý event cũ. Có thể cần lưu key version hoặc routing metadata để relay biết event thuộc chính sách nào.

### 8.3. Duplicate vẫn có thể xảy ra

Partition key không phải idempotency key và không ngăn broker hoặc producer gửi trùng. Retry sau timeout có thể tạo duplicate; consumer vẫn cần eventId và deduplication.

Một bảng processed_event có thể dùng unique constraint theo consumer và event ID:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ghi nhận event ID và side effect database trong cùng transaction. Nếu consumer gọi dịch vụ ngoài, dùng idempotency key riêng cho API đó hoặc đối soát trước khi gửi lại. Partition key chỉ giúp nhóm và sắp xếp event trong phạm vi partition.

## 9. Partition key trong các broker khác nhau

Thuật ngữ và semantics không giống nhau ở mọi broker.

| Hệ thống | Cơ chế tương ứng | Cần lưu ý |
|---|---|---|
| Apache Kafka | Message key và partitioner | Cùng key thường ánh xạ tới cùng partition; ordering nằm trong partition |
| RabbitMQ | Routing key kết hợp exchange và binding | Routing key chọn queue theo loại exchange; không tự tạo ordering theo aggregate trên nhiều consumer |
| Amazon SQS FIFO | MessageGroupId | Message cùng group được xử lý theo thứ tự trong group; group khác có thể xử lý song song |
| Các broker/sharding khác | Routing key hoặc shard key | Phải kiểm tra quy tắc hash, ordering, redelivery và giới hạn concurrency của sản phẩm |

Không chuyển nguyên khái niệm Kafka partition key sang RabbitMQ routing key. Với RabbitMQ, routing key là chuỗi dùng để exchange định tuyến message tới queue theo binding; nó không nhất thiết là khóa phân vùng ổn định. Với SQS FIFO, MessageGroupId thể hiện nhóm thứ tự và có semantics riêng của dịch vụ.

Khi viết adapter, đặt tên field theo khái niệm trung lập như routingKey hoặc orderingKey ở domain/transport boundary, rồi ánh xạ sang message key, routing key hoặc MessageGroupId theo broker. Tài liệu và test cần ghi rõ semantics cụ thể.

## 10. Kết hợp partition key với outbox và Spring Modulith

Trong ứng dụng Spring Modulith, service nghiệp vụ có thể publish application event trong transaction. Nếu event cần được chuyển tới broker đáng tin cậy, transactional outbox lưu event cùng transaction nghiệp vụ. Relay đọc outbox rồi gửi message với key đã chọn.

Ví dụ:

~~~java
@Transactional
public UUID place(PlaceOrderCommand command) {
    Order order = orders.place(command);

    OrderPlaced event = new OrderPlaced(
            UUID.randomUUID(),
            order.getId(),
            order.version(),
            clock.instant()
    );

    outbox.append(
            event.eventId(),
            event.orderId(),
            event.orderVersion(),
            "OrderPlaced",
            event
    );

    return order.getId();
}
~~~

Relay lấy aggregate ID từ bản ghi outbox làm key:

~~~java
public void publish(OutboxRecord record) {
    String key = record.aggregateId().toString();

    kafkaTemplate.send(
            record.destination(),
            key,
            record.payload()
    );
}
~~~

Để giữ thứ tự của cùng aggregate, relay còn phải tránh gửi version sau trước version trước. Chỉ dùng key không bảo đảm thứ tự nếu nhiều relay gửi đồng thời và gửi event của cùng aggregate theo thứ tự khác nhau. Có thể claim theo aggregate, serialize việc gửi theo key hoặc để consumer kiểm tra sequence và xử lý gap.

Nếu ứng dụng dùng Event Publication Registry cho listener nội bộ, publication hoàn tất của listener nội bộ không đồng nghĩa broker đã nhận integration event. Hai luồng cần metric, retry và trạng thái riêng. Nếu dùng externalization tích hợp sẵn, xác minh cách adapter xác định destination, key và acknowledgement theo đúng phiên bản thư viện.

## 11. Quan sát phân vùng và vận hành

Để biết partition key có hoạt động đúng, quan sát ở cả producer, broker và consumer.

**Producer:**

- Tỷ lệ event thiếu key hoặc key không hợp lệ.
- Số lượng key khác nhau và phân phối event theo key.
- Tỷ lệ lỗi gửi, retry và thời gian chờ acknowledgement.
- Số event theo event type, tenant và aggregate.

**Broker:**

- Message rate và byte rate theo partition.
- Partition leader/replica health nếu broker có khái niệm tương ứng.
- Retention, under-replicated partitions và lỗi publish.
- Consumer lag theo partition.

**Consumer:**

- Throughput, latency và lỗi theo partition.
- Aggregate sequence gap hoặc event đến sai thứ tự.
- Duplicate bị loại qua idempotency.
- Số key hoặc aggregate chiếm phần lớn thời gian xử lý.

Không log toàn bộ payload chỉ để tìm partition key. Ghi key hoặc hash an toàn, eventId, aggregateId, sequence, partition và correlationId để truy vết. Nếu key chứa dữ liệu nhạy cảm, dùng ID opaque hoặc hash ổn định; không dùng email, số điện thoại hay thông tin cá nhân làm key.

Khi phát hiện một partition nóng, hãy so sánh phân phối key trước khi tăng partition count hoặc thay đổi partitioner. Một thay đổi key có thể ảnh hưởng thứ tự và cần migration như thay đổi hợp đồng message.

## 12. Kiểm thử chiến lược partition key

Các test cần chứng minh quy tắc key ổn định và thứ tự được giữ trong phạm vi yêu cầu.

| Kịch bản | Điều cần xác minh |
|---|---|
| Hai event của cùng aggregate | Cùng key được tạo ra |
| Event của hai aggregate khác nhau | Key khác nhau theo quy tắc đã chọn |
| Retry cùng event | Key giữ nguyên qua các lần gửi |
| Replay từ outbox | Key được lấy từ metadata gốc, không tạo mới |
| Event thiếu aggregate ID | Bị từ chối hoặc đưa vào luồng lỗi theo chính sách |
| Tenant có ID trùng nhau | Composite key không gây va chạm |
| Key chứa ký tự phân cách | Encoding tạo ra giá trị không nhập nhằng |
| Consumer nhận version tăng dần | Projection áp dụng đúng thứ tự |
| Consumer nhận version bị thiếu | Gap được phát hiện và có retry/recovery |
| Hai relay gửi cùng aggregate | Không gửi version sau trước version trước |
| Partition count thay đổi | Kịch bản migration và ordering được kiểm tra |
| Key phân phối lệch | Metric phát hiện hot partition |

Unit test cho hàm tạo key có thể kiểm tra quy tắc ghép tenant và aggregate. Integration test với broker thật hoặc môi trường broker tương thích cần xác minh message thực sự được ghi vào partition mong đợi và consumer quan sát thứ tự phù hợp.

Một test chỉ kiểm tra KafkaTemplate.send(topic, key, payload) được gọi với key đúng chưa chứng minh broker partitioner và consumer thực thi đúng. Với yêu cầu ordering quan trọng, hãy kiểm tra end-to-end ở cấp broker.

## 13. Quy trình chọn partition key

Khi thiết kế một luồng event mới, có thể đi theo trình tự:

1. Xác định loại event và nơi nhận: listener nội bộ Spring Modulith hay broker bên ngoài.
2. Xác định ranh giới nghiệp vụ cần giữ thứ tự: aggregate, tenant hay một nhóm khác.
3. Chọn ID ổn định làm key và xác định encoding.
4. Đưa key vào metadata/outbox để retry và replay luôn dùng lại key gốc.
5. Xác định số partition, partitioner và concurrency dựa trên throughput thực tế.
6. Đặt quy tắc sequence/version ở consumer nếu thứ tự nghiệp vụ quan trọng.
7. Đo phân phối key, lag và hot partition trước khi tăng partition hoặc đổi key.
8. Kiểm thử duplicate, retry, replay, migration và event đến sai thứ tự.

Partition key tốt phản ánh đúng phạm vi tuần tự hóa của nghiệp vụ. Trong nhiều hệ thống, aggregate ID là lựa chọn tự nhiên vì nó gom các thay đổi của cùng một aggregate mà vẫn cho phép các aggregate khác chạy song song. Với Spring Modulith, việc định tuyến event nội bộ vẫn dựa trên listener và ranh giới module; khi event đi qua broker, adapter/relay mới ánh xạ aggregate key sang cơ chế partition hoặc routing cụ thể.
