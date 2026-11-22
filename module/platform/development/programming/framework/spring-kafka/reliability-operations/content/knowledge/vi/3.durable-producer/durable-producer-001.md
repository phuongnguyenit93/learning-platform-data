# KafkaTemplate và đường đi của send

## 1. Vai trò của KafkaTemplate trong Spring Kafka

`KafkaTemplate<K, V>` là API ở tầng ứng dụng để gửi record đến Kafka. Nó che đi phần lớn thao tác cấp thấp của Kafka producer, đồng thời tích hợp với hệ sinh thái Spring như message conversion, transaction, producer factory và callback bất đồng bộ.

Trong một ứng dụng Spring Kafka, đường đi phổ biến là:

1. Mã nghiệp vụ gọi một phương thức `KafkaTemplate.send(...)`.
2. KafkaTemplate tạo hoặc nhận một `ProducerRecord`, sau đó lấy producer từ `ProducerFactory`.
3. Kafka producer serialize key/value, xác định partition và đưa record vào bộ đệm gửi.
4. Sender thread của Kafka gom record thành batch và gửi Produce request đến broker leader của partition.
5. Broker xử lý record và phản hồi theo cấu hình `acks`.
6. Callback của producer hoàn tất `CompletableFuture<SendResult<K, V>>` mà KafkaTemplate trả về.
7. Ứng dụng nhận kết quả hoặc lỗi và ghi nhận trạng thái gửi.

Sơ đồ này mô tả đường đi ở mức khái quát:

~~~mermaid
sequenceDiagram
    participant S as Service nghiệp vụ
    participant T as KafkaTemplate
    participant F as ProducerFactory
    participant P as KafkaProducer
    participant A as Record accumulator
    participant B as Broker leader

    S->>T: send(topic, key, value)
    T->>F: lấy producer
    F-->>T: KafkaProducer
    T->>P: send(ProducerRecord, callback)
    P->>P: serialize key/value
    P->>P: chọn partition
    P->>A: append record vào batch
    A->>B: Produce request
    B-->>A: Produce response
    A-->>P: callback metadata hoặc exception
    P-->>T: hoàn tất callback
    T-->>S: CompletableFuture hoàn tất
~~~

KafkaTemplate chịu trách nhiệm kết nối API Spring với producer Kafka. Việc gửi qua mạng, batching, retry ở tầng producer và giao thức broker do Kafka client thực hiện. Broker không gọi ngược listener của ứng dụng gửi; consumer ở phía nhận sẽ đọc record độc lập sau đó.

## 2. ProducerFactory và KafkaProducer

### 2.1. ProducerFactory

`ProducerFactory<K, V>` là abstraction Spring Kafka dùng để tạo và cung cấp Kafka producer. `DefaultKafkaProducerFactory` là implementation phổ biến, nhận cấu hình producer như bootstrap servers, serializer, acks, retry, compression và các thiết lập client khác.

KafkaTemplate dùng ProducerFactory để lấy producer phù hợp cho lần gửi. Factory cũng là nơi quản lý vòng đời producer và hỗ trợ producer gắn với transaction khi ứng dụng bật Kafka transaction. Vì vậy, khi cấu hình nhiều KafkaTemplate hoặc nhiều producer factory, cần xác định rõ template nào gửi đến cụm Kafka nào và dùng bộ serializer/transaction nào.

Ví dụ cấu hình bằng Java:

~~~java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory(
        KafkaProperties kafkaProperties
    ) {
        Map<String, Object> properties = new HashMap<>(
            kafkaProperties.buildProducerProperties()
        );

        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> orderProducerFactory
    ) {
        return new KafkaTemplate<>(orderProducerFactory);
    }
}
~~~

Đây là ví dụ minh họa; cách lấy cấu hình từ `KafkaProperties` có thể khác giữa các phiên bản Spring Boot. Trong dự án thực tế, nên dùng một nguồn cấu hình thống nhất và tránh tạo nhiều producer factory trùng lặp nếu không có yêu cầu riêng.

### 2.2. KafkaProducer

`KafkaProducer<K, V>` là client của Apache Kafka. Producer nhận record, thực hiện serialize, chọn partition, quản lý buffer và gửi request bất đồng bộ. KafkaTemplate gọi API producer và chuyển kết quả về abstraction của Spring.

Thông thường, mã nghiệp vụ không cần tự khởi tạo KafkaProducer. Dùng KafkaTemplate giúp ứng dụng tích hợp với cấu hình Spring, quản lý tài nguyên và transaction của framework. Trường hợp cần thao tác cấp thấp hoặc một API Kafka client chưa được KafkaTemplate bọc lại, có thể dùng callback truy cập producer qua các API execute của template, nhưng nên giới hạn logic ở đó để không làm rò rỉ chi tiết client vào service.

## 3. Các cách gọi KafkaTemplate.send

KafkaTemplate cung cấp nhiều overload để mô tả record ở mức độ chi tiết khác nhau. Những overload thường dùng gồm:

| Cách gọi | Khi sử dụng |
|---|---|
| `send(topic, data)` | Gửi value vào topic, để partitioner quyết định partition |
| `send(topic, key, data)` | Gửi record có key để định tuyến và giữ thứ tự theo key |
| `send(topic, partition, key, data)` | Chỉ định partition cụ thể |
| `send(topic, partition, timestamp, key, data)` | Chỉ định partition và timestamp |
| `send(ProducerRecord)` | Kiểm soát đầy đủ topic, partition, timestamp, key, value và headers |
| `send(Message<?>)` | Gửi Spring Message, tận dụng payload và message headers |
| `sendDefault(...)` | Gửi đến default topic đã cấu hình cho KafkaTemplate |

Chữ ký overload cụ thể có thể thay đổi theo phiên bản Spring Kafka. Khi nâng cấp dependency, hãy đối chiếu API của phiên bản đang dùng.

### 3.1. Gửi value đơn giản

~~~java
@Service
@RequiredArgsConstructor
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event
    ) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
~~~

Trong ví dụ, `orderId` là key. Các event cùng key thường được gửi đến cùng partition theo partitioner mặc định, nhờ đó Kafka giữ thứ tự của các record đó trong partition. Nếu không truyền key, producer vẫn có thể chọn partition theo cơ chế partitioner và chính sách batching của client.

### 3.2. Tạo ProducerRecord để kiểm soát metadata

Khi cần đặt timestamp, partition hoặc header, tạo `ProducerRecord` trước khi gọi send:

~~~java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
    OrderCreated event,
    String correlationId
) {
    ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders", null, event.orderId(), event);

    record.headers().add(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8)
    );

    return kafkaTemplate.send(record);
}
~~~

`ProducerRecord` giúp mã gửi thể hiện rõ metadata của record. Cần bảo đảm giá trị header được mã hóa theo quy ước nhất quán giữa producer và consumer. Tránh đặt dữ liệu bí mật hoặc payload lớn vào headers.

Nếu chỉ định partition tường minh, partition đó được dùng thay cho kết quả do partitioner tính toán. Ứng dụng phải bảo đảm partition tồn tại và việc chỉ định thủ công không phá vỡ chiến lược phân phối tải.

### 3.3. Gửi Spring Message

`send(Message<?>)` hữu ích khi ứng dụng đã làm việc với abstraction `Message<?>` của Spring Messaging. Payload trở thành value và một số header có thể được ánh xạ thành metadata Kafka thông qua message converter.

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, "orders")
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .setHeader("correlation-id", correlationId)
    .build();

kafkaTemplate.send(message);
~~~

Cách ánh xạ header phụ thuộc message converter và cấu hình Spring Kafka. Nếu cần kiểm soát rõ ràng partition, timestamp hoặc Kafka headers, `ProducerRecord` thường dễ đọc và ít phụ thuộc quy ước chuyển đổi hơn.

## 4. Đường đi bên trong lời gọi send

### 4.1. Từ service đến KafkaTemplate

Khi service gọi `send()`, KafkaTemplate tạo record từ các tham số hoặc nhận record do ứng dụng cung cấp. Với `send(Message<?>)`, template sử dụng message converter để chuyển Spring Message thành ProducerRecord.

Sau đó template lấy producer từ ProducerFactory. Nếu template được cấu hình để dùng transaction, producer có thể gắn với transaction đang hoạt động. Trong trường hợp thông thường, factory cung cấp producer cho lần gửi và quản lý việc tái sử dụng hoặc đóng producer theo cơ chế của factory.

Điểm cần nhớ: KafkaTemplate không tự lưu record vào broker. Nó là lớp điều phối lời gọi đến Kafka client; trạng thái gửi cuối cùng phụ thuộc producer, mạng và phản hồi broker.

### 4.2. Serialize key và value

Kafka producer cần chuyển key và value thành byte array trước khi gửi. Serializer được cấu hình riêng cho key và value, ví dụ:

- `StringSerializer` chuyển chuỗi thành byte.
- `JsonSerializer` của Spring Kafka chuyển object thành JSON.
- Serializer Avro hoặc Protobuf có thể được dùng khi hệ thống quản lý schema theo các định dạng tương ứng.

Nếu serializer thất bại, producer có thể báo lỗi ngay trong quá trình gọi send hoặc hoàn tất future theo đường lỗi, tùy thời điểm và loại lỗi. Đây là lỗi ở phía client; record chưa được broker xác nhận.

Producer và consumer phải thống nhất định dạng dữ liệu. Với JSON, cần thống nhất cấu trúc event, type header hoặc cấu hình kiểu đích ở consumer. Một serializer thành công chỉ chứng minh object đã được chuyển thành bytes, không chứng minh consumer có thể deserialize hoặc hiểu đúng schema.

### 4.3. Chọn partition

Producer xác định partition theo thứ tự ưu tiên khái quát:

1. Nếu ProducerRecord chỉ định partition, producer dùng partition đó.
2. Nếu có key, partitioner dùng key và metadata topic để chọn partition.
3. Nếu không có key, partitioner chọn partition theo chính sách của client, có thể cân bằng tải và tận dụng batching.

Partition là đơn vị thứ tự của Kafka. Hai record cùng partition được đọc theo thứ tự offset; hai record ở partition khác nhau không có thứ tự tổng thể được bảo đảm.

Nếu nghiệp vụ cần thứ tự theo đơn hàng, tài khoản hoặc aggregate, hãy dùng định danh ổn định của thực thể làm key. Khi thay đổi số partition, ánh xạ key sang partition có thể thay đổi; việc tăng partition có thể ảnh hưởng thứ tự của một key giữa các record cũ và mới. Vì vậy, thay đổi partition count là quyết định vận hành cần đánh giá trước.

### 4.4. Buffer và batching

Sau khi serialize và xác định partition, producer đưa record vào bộ đệm gửi. Kafka client gom record cùng partition thành batch để giảm số request và tăng throughput. Sender thread gửi các batch đã sẵn sàng đến broker.

Các cấu hình có ảnh hưởng trực tiếp:

| Cấu hình | Vai trò |
|---|---|
| `batch.size` | Kích thước batch mục tiêu cho một partition |
| `linger.ms` | Thời gian producer có thể chờ thêm record để batch đầy hơn |
| `buffer.memory` | Dung lượng bộ đệm producer dùng cho các record đang chờ gửi |
| `compression.type` | Thuật toán nén batch |
| `max.request.size` | Giới hạn kích thước request mà producer gửi |

Batch lớn và linger cao có thể tăng throughput, nhưng cũng làm tăng thời gian chờ trước khi gửi. Buffer quá nhỏ hoặc broker chậm có thể khiến producer phải chờ buffer hoặc gặp lỗi hết thời gian chờ. Cần đo tải thực tế để cân bằng latency và throughput.

### 4.5. Gửi request và nhận phản hồi broker

Sender thread gửi Produce request đến broker leader của partition. Broker kiểm tra quyền ghi, trạng thái partition, điều kiện ISR và các ràng buộc khác; sau đó xử lý record theo giao thức Kafka.

Producer chờ phản hồi theo cấu hình `acks`:

- `acks=0`: không chờ broker xác nhận.
- `acks=1`: chờ leader xác nhận sau khi ghi.
- `acks=all`: chờ các replica trong ISR đáp ứng điều kiện xác nhận theo cấu hình cụm.

Sau khi nhận phản hồi, Kafka client gọi callback cho record hoặc batch liên quan. KafkaTemplate chuyển kết quả đó thành `SendResult` hoặc hoàn tất future với exception.

Một response thành công cho biết producer đã nhận xác nhận theo chính sách acks. Nó không có nghĩa consumer đã đọc record hoặc nghiệp vụ downstream đã hoàn tất.

## 5. Xử lý kết quả bất đồng bộ

### 5.1. CompletableFuture trong Spring Kafka 3.x

Từ Spring Kafka 3.0, các phương thức send trả về `CompletableFuture<SendResult<K, V>>`. Ứng dụng có thể đăng ký callback bằng `whenComplete`, `thenAccept` hoặc `exceptionally`.

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send("orders", event.orderId(), event)
        .whenComplete((result, error) -> {
            if (error != null) {
                log.error("Publish failed for order {}", event.orderId(), error);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "Published order {} to {}-{} offset {}",
                event.orderId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

`SendResult<K, V>` chứa record đã gửi và `RecordMetadata` do Kafka client trả về. Metadata thường cung cấp topic, partition, offset, timestamp và kích thước record. Những dữ liệu này hữu ích cho log, trace và điều tra khi có sự cố.

Trước Spring Kafka 3.0, API send thường trả về `ListenableFuture`. Khi đọc ví dụ cũ hoặc nâng cấp ứng dụng, cần chú ý khác biệt này để không dùng nhầm kiểu future hoặc callback.

### 5.2. Kết hợp nhiều thao tác bất đồng bộ

Nếu cần gửi nhiều event mà không chặn thread, có thể kết hợp các future:

~~~java
public CompletableFuture<Void> publishAll(List<OrderCreated> events) {
    List<CompletableFuture<SendResult<String, OrderCreated>>> sends =
        events.stream()
            .map(event -> kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
            ))
            .toList();

    return CompletableFuture.allOf(
        sends.toArray(CompletableFuture[]::new)
    );
}
~~~

`allOf` hoàn tất khi tất cả future hoàn tất. Nếu một future lỗi, future tổng hợp cũng hoàn tất bất thường. Nếu cần kết quả chi tiết cho từng event, hãy giữ danh sách future và thu thập kết quả/lỗi riêng thay vì chỉ dựa vào future tổng hợp.

Không nên tạo số lượng future không giới hạn cho một đợt gửi lớn. Cần giới hạn concurrency hoặc kích thước lô ở tầng ứng dụng để tránh làm đầy producer buffer, tăng heap và tạo áp lực lên broker.

### 5.3. Gửi đồng bộ bằng cách chờ future

Có trường hợp nghiệp vụ cần biết kết quả gửi trước khi tiếp tục. Có thể chờ future với timeout:

~~~java
public SendResult<String, OrderCreated> publishAndWait(
    OrderCreated event
) throws InterruptedException, ExecutionException, TimeoutException {
    return kafkaTemplate
        .send("orders", event.orderId(), event)
        .get(5, TimeUnit.SECONDS);
}
~~~

Cách này chặn thread gọi cho đến khi có kết quả hoặc hết thời gian chờ. Chỉ nên dùng khi có lý do rõ ràng và timeout được thiết kế phù hợp. Nếu gọi trong request thread của web server với lưu lượng cao, việc chờ đồng bộ có thể làm cạn thread pool và tăng latency toàn hệ thống.

Timeout khi chờ future không chứng minh record chưa được ghi. Broker có thể đã ghi record nhưng phản hồi bị mất hoặc đến muộn. Nếu ứng dụng gửi lại sau timeout, có thể phát sinh record trùng; event ID ổn định và consumer idempotency giúp xử lý trường hợp đó.

### 5.4. Callback nên làm gì?

Callback nên thực hiện công việc ngắn gọn: ghi log, tăng metric, hoàn tất future nghiệp vụ hoặc chuyển kết quả đến một cơ chế xử lý có kiểm soát. Callback của Kafka producer có thể chạy trên thread xử lý I/O của producer. Tránh thực hiện truy vấn database chậm, gọi HTTP đồng bộ hoặc xử lý CPU nặng trực tiếp trong callback vì có thể làm chậm tiến trình gửi các record khác.

Nếu cần xử lý tiếp sau khi gửi, có thể dùng executor riêng hoặc cơ chế event nội bộ. Executor phải có giới hạn hàng đợi và chính sách từ chối rõ ràng; nếu không, chuyển công việc ra thread khác chỉ dời vấn đề quá tải sang một nơi khác.

## 6. Những loại lỗi trên đường đi của send

Lỗi gửi có thể xuất hiện ở nhiều thời điểm:

| Giai đoạn | Ví dụ lỗi | Ý nghĩa |
|---|---|---|
| Tạo record | Topic hoặc tham số không hợp lệ | Ứng dụng tạo record sai |
| Serialize | Serializer không chuyển được object | Lỗi định dạng hoặc dữ liệu |
| Lấy metadata/buffer | Hết thời gian chờ metadata hoặc buffer | Client không thể chuẩn bị gửi đúng hạn |
| Gửi đến broker | Network exception, broker unavailable | Không liên lạc được hoặc kết nối bị gián đoạn |
| Broker xử lý | Authorization, record too large, not enough replicas | Broker từ chối theo quyền hoặc chính sách |
| Chờ xác nhận | Request timeout hoặc delivery timeout | Không nhận được kết quả cuối cùng trong thời hạn |

### 6.1. Lỗi đồng bộ và lỗi bất đồng bộ

Không phải mọi lỗi đều xuất hiện sau khi future được trả về. Một số lỗi cấu hình, lỗi tạo record hoặc lỗi client có thể xảy ra ngay khi gọi send. Những lỗi xảy ra sau khi record được đưa vào tiến trình gửi thường được báo qua callback/future.

Do đó, nếu cần xử lý lỗi đầy đủ, đặt cả lời gọi send trong khối try/catch và đăng ký callback trên future:

~~~java
public void publish(OrderCreated event) {
    try {
        kafkaTemplate.send("orders", event.orderId(), event)
            .whenComplete((result, error) -> {
                if (error != null) {
                    recordSendFailure(event, error);
                } else {
                    recordSendSuccess(event, result.getRecordMetadata());
                }
            });
    } catch (RuntimeException immediateFailure) {
        recordSendFailure(event, immediateFailure);
    }
}
~~~

Không ghi nhận thành công chỉ vì phương thức send đã trả về một future. Chỉ callback/future hoàn tất thành công mới cho biết producer đã nhận kết quả thành công theo cấu hình xác nhận.

### 6.2. Timeout và ý nghĩa của kết quả không rõ ràng

Một số timeout cần phân biệt:

- `max.block.ms` giới hạn thời gian các API producer có thể chờ metadata hoặc dung lượng buffer trước khi ném lỗi.
- `request.timeout.ms` giới hạn thời gian chờ phản hồi cho một request.
- `delivery.timeout.ms` giới hạn tổng thời gian từ lúc gọi send đến khi báo thành công hoặc thất bại, bao gồm thời gian chờ batch, request và retry.

Tên cấu hình và mặc định có thể thay đổi theo Kafka client version. Cần kiểm tra tài liệu đúng phiên bản đang chạy.

Khi delivery timeout xảy ra, producer không thể luôn kết luận broker chưa ghi record. Ví dụ broker ghi record nhưng response bị mất trên mạng. Ứng dụng cần xử lý tình huống kết quả không rõ ràng như một khả năng duplicate nếu gửi lại.

### 6.3. Retry ở producer và retry ở ứng dụng

Kafka producer có retry nội bộ cho lỗi tạm thời theo cấu hình client. Với idempotent producer, Kafka dùng producer ID và sequence number để chống duplicate do retry nội bộ trong phạm vi cơ chế idempotence.

Retry ở tầng ứng dụng là lần gọi send mới, thường xuất hiện khi service retry request, khởi động lại hoặc gửi lại event sau khi không chắc kết quả trước đó. Producer idempotence không tự nhận diện mọi lần gửi lại từ ứng dụng như cùng một nghiệp vụ. Vì vậy, event nên có ID ổn định và consumer nên có cơ chế idempotent.

## 7. Cấu hình producer liên quan đến send

Một cấu hình minh họa trong Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
        batch.size: 32768
        compression.type: snappy
~~~

Ý nghĩa vận hành:

- `bootstrap-servers` cung cấp địa chỉ bootstrap để client khám phá cụm broker.
- `acks: all` yêu cầu xác nhận theo ISR, cần kết hợp với replication factor và `min.insync.replicas` ở broker/topic.
- `enable.idempotence: true` giảm nguy cơ duplicate do retry nội bộ producer.
- `delivery.timeout.ms` giới hạn tổng thời gian gửi; không nên đặt quá thấp nếu hệ thống có độ trễ mạng hoặc broker biến động.
- `request.timeout.ms` giới hạn thời gian chờ cho một request.
- `linger.ms` và `batch.size` ảnh hưởng đến batching và latency.
- `compression.type` giảm dung lượng truyền tải, đổi lại tiêu tốn CPU cho nén/giải nén.

Không nên sao chép nguyên bộ giá trị này vào mọi môi trường. Hãy chọn timeout theo SLA, đo throughput và latency, kiểm tra giới hạn broker và theo dõi tỷ lệ retry. Nếu cấu hình idempotence tường minh, các ràng buộc tương thích giữa acks, retries và max in flight phải được giữ theo yêu cầu của Kafka client version.

## 8. KafkaTemplate với transaction

KafkaTemplate có thể tham gia Kafka transaction khi được cấu hình với transactional ProducerFactory. Transaction hữu ích khi một luồng cần gửi nhiều record nguyên tử, hoặc khi consumer đọc record, xử lý và gửi output record trong cùng transaction Kafka.

Ví dụ dùng transaction ở tầng template:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("order-events", orderId, orderCreated);
    operations.send("audit-events", orderId, auditEvent);
    return true;
});
~~~

Hai record được gửi trong cùng transaction của Kafka. Nếu callback kết thúc bình thường, transaction được commit; nếu có exception, transaction có thể bị abort theo cơ chế của template. Cần kiểm tra cách xử lý exception và cấu hình transaction trong phiên bản Spring Kafka cụ thể.

Một transaction Kafka không bao gồm database hoặc HTTP service. Nếu ứng dụng cập nhật database rồi publish event, có thể xảy ra trạng thái database đã commit nhưng Kafka transaction thất bại, hoặc ngược lại tùy thứ tự thao tác. Với yêu cầu nhất quán giữa database và Kafka, transactional outbox thường là thiết kế phù hợp: ghi dữ liệu nghiệp vụ và outbox row trong cùng database transaction, sau đó publisher đọc outbox và gửi Kafka.

## 9. Flush, close và vòng đời producer

### 9.1. Flush

`flush()` yêu cầu producer đẩy các record đang chờ trong buffer đi và chờ quá trình gửi hoàn tất theo hành vi của Kafka client. KafkaTemplate cũng cung cấp phương thức flush.

Không nên gọi flush sau mỗi record trong luồng throughput cao vì nó làm giảm hiệu quả batching. Chỉ bật auto flush hoặc gọi flush khi có yêu cầu cụ thể, ví dụ cần ép các record đang đệm được gửi trước một điểm đồng bộ.

### 9.2. Vòng đời producer

Producer là tài nguyên có kết nối mạng, buffer và thread nền. Spring Kafka quản lý producer thông qua ProducerFactory và vòng đời bean/container. Ứng dụng thông thường không nên tự đóng producer lấy từ template sau mỗi lần gửi.

Nếu dùng callback execute để thao tác producer cấp thấp, cần tuân thủ hợp đồng quản lý tài nguyên của API đó. Không giữ producer ngoài phạm vi quản lý của factory, không tự đóng producer được factory quản lý và không tạo một producer mới cho từng record.

## 10. Quan sát đường đi của send

Để vận hành ổn định, nên quan sát cả kết quả ở tầng ứng dụng và chỉ số của Kafka producer.

| Điểm quan sát | Thông tin hữu ích | Mục đích |
|---|---|---|
| Trước send | Event ID, topic, key, correlation ID | Biết ứng dụng định gửi event nào |
| Future/callback | Thành công, exception, thời gian hoàn tất | Biết producer đã nhận kết quả gì |
| SendResult | Topic, partition, offset, timestamp | Truy vết vị trí record đã ghi |
| Producer metrics | Request latency, record retry, error rate, buffer available bytes, batch size | Phát hiện broker chậm hoặc producer bị nghẽn |
| Broker metrics | Request handler, network processor, ISR, partition health | Xác định vấn đề ở cụm Kafka |

Khi log thành công, nên ghi topic, partition, offset và event ID. Khi log lỗi, ghi exception class, topic và event ID để hỗ trợ điều tra. Tránh ghi toàn bộ payload nếu payload chứa thông tin cá nhân hoặc dữ liệu nhạy cảm.

Các chỉ số producer có thể được lấy thông qua Kafka client metrics hoặc tích hợp monitoring của ứng dụng. Tên metric cụ thể phụ thuộc Kafka client version và hệ thống metrics. Những nhóm metric thường cần quan sát gồm request latency, record send rate, retry rate, error rate, buffer utilization, batch size và compression rate.

## 11. Những lỗi thiết kế thường gặp

**Bỏ qua future:** Service gọi send rồi bỏ qua kết quả. Lỗi bất đồng bộ không được ghi nhận ở tầng nghiệp vụ, khiến ứng dụng tưởng event đã gửi thành công.

**Chờ đồng bộ mọi lần gửi:** Dùng `get()` hoặc `join()` ngay sau mỗi send làm mất lợi ích bất đồng bộ, tăng latency và có thể làm cạn thread pool.

**Retry mù sau timeout:** Timeout không chứng minh record chưa được ghi. Gửi lại không có event ID ổn định có thể tạo side effect trùng ở consumer.

**Gửi payload quá lớn:** Record lớn gây áp lực lên producer buffer, network và broker. Nên giới hạn kích thước event, chỉ gửi dữ liệu cần thiết và dùng object storage/reference nếu payload lớn.

**Không đặt key:** Producer có thể phân phối record mà không giữ được thứ tự theo thực thể nghiệp vụ. Nếu thứ tự theo key là yêu cầu, phải chọn key có ý nghĩa nghiệp vụ.

**Gọi flush liên tục:** Flush mỗi record làm giảm batching và throughput.

**Xử lý nặng trong callback:** Callback chạy trên đường xử lý của producer; thao tác chậm có thể ảnh hưởng các lần gửi khác.

**Nhầm xác nhận gửi với xử lý nghiệp vụ:** Future thành công chỉ xác nhận producer nhận kết quả gửi theo acks. Nó không chứng minh consumer đã xử lý hoặc database đã commit.

## 12. Quy trình chẩn đoán khi send lỗi

Khi một event không xuất hiện ở phía consumer, có thể lần theo theo trình tự:

1. Xác nhận service đã gọi send với đúng topic, key và event ID.
2. Kiểm tra exception đồng bộ ngay tại lời gọi send.
3. Kiểm tra future/callback có hoàn tất thành công hay thất bại.
4. Nếu thành công, dùng topic, partition và offset trong SendResult để tìm record ở phía Kafka.
5. Nếu timeout hoặc network exception, xem producer retry, delivery timeout, broker availability và trạng thái partition.
6. Nếu record đã tồn tại, chuyển hướng điều tra sang consumer group, offset, lag, deserialization và listener.

Cách phân lớp này giúp tránh sửa consumer khi producer chưa gửi được, hoặc retry producer khi record đã được broker ghi và vấn đề thực tế nằm ở consumer.

## 13. Nguyên tắc sử dụng KafkaTemplate trong ứng dụng

- Inject KafkaTemplate qua constructor để service dễ kiểm thử và phụ thuộc rõ ràng.
- Dùng overload đơn giản cho trường hợp thông thường; dùng ProducerRecord khi cần kiểm soát metadata.
- Chọn key theo thực thể nghiệp vụ cần giữ thứ tự.
- Theo dõi future/callback và ghi nhận cả lỗi đồng bộ lẫn lỗi bất đồng bộ.
- Không block thread nếu không có yêu cầu đồng bộ rõ ràng; nếu phải chờ, luôn đặt timeout.
- Đặt giới hạn cho số lượng gửi đồng thời và kích thước batch ở tầng ứng dụng.
- Chọn serializer/deserializer và schema tương thích giữa producer với consumer.
- Cấu hình acks, idempotence, retry và timeout theo SLA cùng khả năng của cụm.
- Dùng transaction khi cần atomicity trong Kafka; dùng outbox/inbox cho ranh giới database.
- Ghi log event ID, topic, partition, offset và correlation ID để truy vết.

Khi hiểu rõ đường đi từ KafkaTemplate đến producer buffer, broker response và future callback, đội vận hành có thể xác định chính xác send đang thất bại ở bước nào, phân biệt lỗi client với lỗi broker và xử lý timeout mà không tạo duplicate ngoài ý muốn.
