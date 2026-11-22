# Nhận CompletableFuture từ thao tác gửi

## 1. Vì sao KafkaTemplate trả về CompletableFuture?

Kafka producer được thiết kế để gửi record bất đồng bộ. Khi ứng dụng gọi `KafkaTemplate.send()`, producer tiếp nhận record, serialize key/value, đưa record vào bộ đệm và gửi đến broker bằng luồng I/O nền. Ứng dụng không cần chờ broker ngay tại lời gọi đó.

Spring Kafka cung cấp kết quả gửi dưới dạng `CompletableFuture<SendResult<K, V>>`. Future đại diện cho một thao tác gửi đang diễn ra hoặc đã hoàn tất. Khi producer hoàn tất thao tác theo cấu hình `acks`, future hoàn tất thành công với `SendResult`; nếu thao tác gửi thất bại, future hoàn tất ở trạng thái exceptional. Với `acks=0`, producer không chờ broker gửi acknowledgement nên mức xác nhận yếu hơn.

```text
OrderService
    |
    | KafkaTemplate.send("orders", orderId, event)
    v
KafkaTemplate / KafkaProducer
    |                         \
    | trả CompletableFuture    \ gửi qua I/O thread
    v                           v
OrderService tiếp tục       Kafka broker
                                |
                                | acknowledgement hoặc lỗi
                                v
                         hoàn tất CompletableFuture
                                |
                                v
                      callback / future continuation
```

Future giúp tách thời điểm gửi yêu cầu khỏi thời điểm nhận kết quả. Tầng nghiệp vụ có thể trả future cho tầng gọi, đăng ký callback, biến đổi kết quả hoặc kết hợp nhiều thao tác bất đồng bộ.

## 2. Kiểu dữ liệu nhận được từ send()

Trong Spring Kafka 3.0 trở lên, các overload của `KafkaTemplate.send()` trả về `CompletableFuture<SendResult<K, V>>`. Các phiên bản Spring Kafka cũ sử dụng `ListenableFuture`; khi làm việc với dự án cũ, hãy kiểm tra API của đúng phiên bản thay vì mặc định rằng kiểu trả về luôn là `CompletableFuture`.

Ví dụ khai báo kiểu future:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders", "ORD-100", event);
```

Trong đó:

- `String` là kiểu key của record.
- `OrderCreated` là kiểu value trước khi serializer chuyển thành byte.
- `SendResult<String, OrderCreated>` chứa record đã gửi và metadata do broker trả về.

`SendResult` có hai thông tin quan trọng:

| Phương thức | Giá trị | Cách sử dụng |
|---|---|---|
| `getProducerRecord()` | `ProducerRecord<K, V>` đã được gửi | Kiểm tra topic, key, value, partition được chỉ định và headers |
| `getRecordMetadata()` | `RecordMetadata` từ Kafka broker | Lấy topic, partition, offset, timestamp và kích thước record đã serialize |

Offset trong `RecordMetadata` chỉ có ý nghĩa trong partition tương ứng. Không dùng riêng offset làm ID duy nhất cho sự kiện trên toàn cụm; nên có `eventId` do ứng dụng tạo để truy vết nghiệp vụ.

## 3. Nhận future từ các overload của KafkaTemplate

Các overload gửi khác nhau về thông tin đầu vào, nhưng cùng trả về future chứa `SendResult`:

```java
// Topic và value
CompletableFuture<SendResult<String, OrderCreated>> a =
        kafkaTemplate.send("orders", event);

// Topic, key và value
CompletableFuture<SendResult<String, OrderCreated>> b =
        kafkaTemplate.send("orders", event.orderId(), event);

// Topic, partition, key và value
CompletableFuture<SendResult<String, OrderCreated>> c =
        kafkaTemplate.send("orders", 2, event.orderId(), event);

// ProducerRecord có thể mang timestamp, headers và partition
ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders", event.orderId(), event);
CompletableFuture<SendResult<String, OrderCreated>> d =
        kafkaTemplate.send(record);
```

Ví dụ minh họa các overload phổ biến. Nếu chỉ cung cấp topic và value, partitioner quyết định partition. Nếu cung cấp key, partitioner thường dùng key để chọn partition. Nếu chỉ định partition trực tiếp, ứng dụng chịu trách nhiệm bảo đảm partition đó tồn tại.

Với `Message<?>` của Spring Messaging hoặc các overload `sendDefault()`, future vẫn biểu diễn kết quả gửi và có kiểu generic phù hợp với key/value của `KafkaTemplate`.

## 4. Đăng ký callback bằng whenComplete()

`whenComplete()` đăng ký hành động chạy khi future hoàn tất, dù thành công hay thất bại. Callback nhận hai tham số: kết quả và exception. Nếu thành công, exception là `null`; nếu thất bại, kết quả thường là `null`.

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total) {}

@Service
public class OrderEventPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        CompletableFuture<SendResult<String, OrderCreated>> future =
                kafkaTemplate.send("orders", event.orderId(), event);

        future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Publish failed, eventId={}", event.eventId(), exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info("Published eventId={} to topic={}, partition={}, offset={}",
                    event.eventId(), metadata.topic(), metadata.partition(),
                    metadata.offset());
        });

        return future;
    }
}
```

Phương thức `publish()` trả chính future gửi Kafka cho tầng gọi. Callback chỉ ghi log và không chờ thêm công việc khác. Nhờ đó, tầng gọi vẫn có thể tiếp tục theo dõi kết quả hoặc kết hợp future với các tác vụ khác.

`whenComplete()` trả về một future mới. Future mới giữ kết quả ban đầu nếu callback chạy bình thường; nếu callback tự ném exception, future mới có thể hoàn tất exceptional. Vì vậy, nếu logic callback có thể lỗi và kết quả của callback quan trọng, hãy giữ lại future được trả về hoặc xử lý exception bên trong callback.

## 5. Đọc metadata sau khi gửi thành công

`SendResult` chỉ có khi thao tác gửi thành công. Có thể dùng `thenApply()` để ánh xạ kết quả gửi thành một đối tượng receipt gọn hơn.

```java
public record PublishReceipt(
        String topic,
        int partition,
        long offset,
        long timestamp) {}

public CompletableFuture<PublishReceipt> publishWithReceipt(
        OrderCreated event) {
    return kafkaTemplate.send("orders", event.orderId(), event)
            .thenApply(sendResult -> {
                RecordMetadata metadata = sendResult.getRecordMetadata();
                return new PublishReceipt(
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset(),
                        metadata.timestamp());
            });
}
```

`thenApply()` chỉ chạy khi future trước đó hoàn tất thành công. Nếu gửi thất bại, lỗi được chuyển tiếp sang future kết quả; hàm ánh xạ không được gọi. Cách này giúp service chỉ công bố thông tin cần thiết thay vì để tầng trên phụ thuộc trực tiếp vào toàn bộ `SendResult`.

## 6. Phân biệt các phương thức xử lý CompletableFuture

`CompletableFuture` cung cấp nhiều phép nối tiếp để xử lý thành công, thất bại hoặc cả hai:

| Phương thức | Khi nào chạy? | Kết quả |
|---|---|---|
| `thenApply(fn)` | Khi future trước thành công | Biến đổi giá trị thành một giá trị mới |
| `thenAccept(consumer)` | Khi future trước thành công | Tiêu thụ kết quả, không trả giá trị nghiệp vụ mới (`Void`) |
| `thenRun(action)` | Khi future trước thành công | Chạy hành động không cần nhận kết quả |
| `thenCompose(fn)` | Khi future trước thành công và hàm trả về một future khác | Nối hai thao tác bất đồng bộ, tránh future lồng nhau |
| `whenComplete(action)` | Khi future thành công hoặc thất bại | Quan sát kết quả/lỗi và giữ nguyên kết quả nếu callback không lỗi |
| `handle(fn)` | Khi future thành công hoặc thất bại | Biến đổi cả kết quả lẫn lỗi thành một kết quả mới |
| `exceptionally(fn)` | Khi future thất bại | Chuyển lỗi thành một giá trị thay thế nếu có thể phục hồi |

Ví dụ nối tiếp hai thao tác bất đồng bộ:

```java
CompletableFuture<PublishReceipt> receiptFuture =
        kafkaTemplate.send("orders", event.orderId(), event)
                .thenApply(sendResult -> {
                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    return new PublishReceipt(
                            metadata.topic(), metadata.partition(),
                            metadata.offset(), metadata.timestamp());
                });

CompletableFuture<AuditResult> auditFuture = receiptFuture
        .thenCompose(auditService::recordPublishReceipt);
```

Giả sử `recordPublishReceipt()` trả về `CompletableFuture<AuditResult>`. `thenCompose()` nối future audit vào chuỗi hiện tại. Nếu dùng `thenApply()` ở đây, kiểu kết quả sẽ thành `CompletableFuture<CompletableFuture<AuditResult>>`, khiến tầng gọi phải xử lý future lồng nhau.

## 7. Xử lý lỗi từ future

Khi producer không gửi được record, future có thể hoàn tất exceptional. Nguyên nhân có thể là lỗi serialize, lỗi kết nối, timeout, broker từ chối ghi, thiếu quyền truy cập hoặc điều kiện ISR không đáp ứng. Một số lỗi phát sinh ngay trong lúc chuẩn bị lời gọi gửi có thể được ném trực tiếp từ `send()` trước khi caller nhận được future; nếu cần xử lý đầy đủ, hãy đặt cả lời gọi `send()` và phần theo dõi future trong phạm vi xử lý exception phù hợp.

Có thể xử lý lỗi bằng `exceptionally()`:

```java
CompletableFuture<PublishReceipt> receiptFuture =
        kafkaTemplate.send("orders", event.orderId(), event)
                .thenApply(sendResult -> {
                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    return new PublishReceipt(
                            metadata.topic(), metadata.partition(),
                            metadata.offset(), metadata.timestamp());
                })
                .exceptionally(exception -> {
                    log.error("Cannot publish eventId={}",
                            event.eventId(), exception);
                    throw new CompletionException(exception);
                });
```

Trong ví dụ, exception được ghi log rồi ném lại dưới dạng `CompletionException`, do đó future vẫn thất bại. Nếu thay bằng một receipt mặc định, future sẽ chuyển thành thành công; chỉ nên làm vậy khi tầng nghiệp vụ thực sự chấp nhận kết quả thay thế.

Khi cần xử lý cả hai nhánh thành công/thất bại thành một kiểu kết quả thống nhất, dùng `handle()`:

```java
public record PublishOutcome(
        boolean published,
        PublishReceipt receipt,
        String errorMessage) {}

CompletableFuture<PublishOutcome> outcomeFuture =
        kafkaTemplate.send("orders", event.orderId(), event)
                .handle((sendResult, exception) -> {
                    if (exception != null) {
                        return new PublishOutcome(
                                false, null, exception.getMessage());
                    }

                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    PublishReceipt receipt = new PublishReceipt(
                            metadata.topic(), metadata.partition(),
                            metadata.offset(), metadata.timestamp());
                    return new PublishOutcome(true, receipt, null);
                });
```

`handle()` biến lỗi thành dữ liệu nghiệp vụ. Cách này hữu ích khi caller muốn nhận trạng thái rõ ràng, nhưng cần tránh coi `published=false` là một kết quả gửi thành công. Hệ thống vẫn phải ghi nhận thất bại và quyết định retry, lưu lại hoặc báo lỗi cho người gọi.

### Unwrap exception

Khi dùng `get()`, lỗi thường được bọc trong `ExecutionException`; với `join()` và một số stage của `CompletableFuture`, lỗi thường được bọc trong `CompletionException`. Có thể lần theo `getCause()` để tìm nguyên nhân gốc:

```java
Throwable cause = exception;
while ((cause instanceof CompletionException
        || cause instanceof ExecutionException)
        && cause.getCause() != null) {
    cause = cause.getCause();
}

log.error("Kafka publish root cause", cause);
```

Trong thực tế, hãy phân loại lỗi theo loại exception Kafka/Spring Kafka và bối cảnh gửi. Không nên chỉ phân tích message text vì nội dung thông báo có thể thay đổi theo phiên bản.

## 8. Callback chạy trên thread nào?

Các stage không có hậu tố `Async`, như `thenApply()`, `thenAccept()` hoặc `whenComplete()`, có thể chạy trên thread hoàn tất future. Với Kafka producer, callback xác nhận gửi thường được gọi từ luồng I/O của producer; do đó, logic gắn vào future có thể chạy trên thread quan trọng đối với quá trình gửi.

Không nên thực hiện các thao tác sau trong callback không async:

- Gọi HTTP hoặc database có thể chờ lâu.
- Chờ một future khác bằng `get()` hoặc `join()`.
- Thực hiện tính toán nặng hoặc xử lý batch lớn.
- Gọi lại Kafka theo cách tạo chuỗi chờ lẫn nhau.

Nếu cần công việc nặng, dùng stage bất đồng bộ với executor được quản lý:

```java
CompletableFuture<PublishReceipt> receiptFuture =
        kafkaTemplate.send("orders", event.orderId(), event)
                .thenApplyAsync(sendResult -> {
                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    return new PublishReceipt(
                            metadata.topic(), metadata.partition(),
                            metadata.offset(), metadata.timestamp());
                }, publishExecutor);
```

`publishExecutor` nên là executor có giới hạn thread/queue và được quản lý vòng đời bởi Spring. Nếu không truyền executor, các stage `*Async()` thường dùng `ForkJoinPool.commonPool()`, không phải lúc nào cũng phù hợp với workload của ứng dụng.

## 9. Chờ một future hoặc nhiều future

Nếu tầng gọi cần chờ kết quả, có thể dùng `get(timeout, unit)` hoặc `join()`. Hai cách này chặn thread gọi; chúng không thay đổi bản chất gửi bất đồng bộ của Kafka producer.

```java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders", event.orderId(), event)
                .get(5, TimeUnit.SECONDS);
```

Với `get()`, cần xử lý `InterruptedException`, `ExecutionException` và `TimeoutException`. Nếu timeout xảy ra, kết quả gửi có thể chưa rõ: yêu cầu có thể vẫn đang được producer xử lý và future có thể hoàn tất sau đó. Không được mặc định rằng timeout nghĩa là record chưa tới broker.

Khi gửi nhiều record, `CompletableFuture.allOf()` giúp đợi tất cả future hoàn tất:

```java
List<CompletableFuture<SendResult<String, OrderCreated>>> futures =
        events.stream()
                .map(event -> kafkaTemplate.send(
                        "orders", event.orderId(), event))
                .toList();

CompletableFuture<Void> all =
        CompletableFuture.allOf(futures.toArray(CompletableFuture[]::new));

all.whenComplete((ignored, exception) -> {
    if (exception != null) {
        log.error("At least one event could not be published", exception);
        return;
    }

    log.info("All {} events were acknowledged by Kafka", futures.size());
});
```

`allOf()` chỉ tạo future tổng hợp kiểu `Void`; nó không trả danh sách `SendResult`. Nếu một future thành phần thất bại, future tổng hợp cũng thất bại. Một số record khác vẫn có thể đã được gửi thành công, vì vậy không nên retry toàn bộ danh sách một cách mù quáng. Hãy theo dõi từng future và event ID để biết record nào cần xử lý tiếp.

## 10. Timeout, cancel và trạng thái không chắc chắn

Ba tình huống cần phân biệt:

| Tình huống | Ý nghĩa |
|---|---|
| Future hoàn tất thành công | Producer nhận xác nhận theo cấu hình `acks` |
| Future hoàn tất exceptional | Producer không hoàn tất được thao tác gửi; cần xem nguyên nhân |
| Caller hết thời gian chờ | Caller ngừng chờ; thao tác gửi có thể vẫn đang diễn ra hoặc kết quả chưa xác định |

`future.cancel(true)` tác động đến trạng thái `CompletableFuture`, nhưng không nên giả định nó có thể thu hồi record đã được đưa vào Kafka producer hoặc hủy chắc chắn yêu cầu mạng đang diễn ra. Nếu cần hủy một tác vụ nghiệp vụ, phải thiết kế trạng thái và idempotency ở tầng ứng dụng; không dựa vào cancel để chứng minh Kafka chưa nhận record.

Khi retry sau timeout, dùng `eventId` ổn định và thiết kế consumer idempotent. Nếu gửi lại cùng một sự kiện, consumer có thể nhận hai record giống nhau dù producer có idempotence, bởi idempotent producer chủ yếu bảo vệ retry nội bộ của một producer session theo phạm vi Kafka, không tự khử trùng lặp các lần gọi `send()` mới của ứng dụng.

## 11. CompletableFuture không phải xác nhận xử lý nghiệp vụ

Future của `KafkaTemplate.send()` biểu diễn kết quả ghi record vào Kafka. Khi future thành công, điều đó không có nghĩa:

- Consumer đã poll record.
- Listener đã xử lý xong nghiệp vụ.
- Database của consumer đã commit.
- Email, thanh toán hoặc API downstream đã hoàn tất.

Nếu cần biết consumer đã xử lý, cần thiết kế cơ chế phản hồi riêng, ví dụ event kết quả, request-reply qua Kafka hoặc trạng thái nghiệp vụ được lưu ở nơi phù hợp. Không diễn giải `SendResult` như một receipt xác nhận toàn bộ workflow.

Nếu việc ghi dữ liệu nghiệp vụ vào database và gửi event phải nhất quán, hãy xem xét Transactional Outbox. `CompletableFuture` chỉ giúp quan sát kết quả gửi bất đồng bộ; nó không tạo transaction phân tán giữa database và Kafka.

## 12. Kiểm thử future từ thao tác gửi

Kiểm thử cần xác minh cả kiểu kết quả, nhánh thành công, nhánh thất bại và hành vi thread:

1. **Kiểu trả về:** xác nhận `KafkaTemplate.send()` trả `CompletableFuture<SendResult<K, V>>` theo phiên bản Spring Kafka của dự án.
2. **Thành công:** gửi record đến broker test, chờ future và kiểm tra topic, partition, offset trong `SendResult`.
3. **Callback:** xác nhận `whenComplete()` nhận kết quả ở nhánh thành công và exception ở nhánh lỗi.
4. **Composition:** xác nhận `thenApply()` biến đổi metadata và `thenCompose()` nối future thứ hai đúng cách.
5. **Exception:** làm broker không khả dụng hoặc cấu hình sai để xác nhận future hoàn tất exceptional và nguyên nhân được ghi nhận.
6. **Timeout:** tạo tình huống phản hồi chậm, xác nhận tầng gọi không coi timeout là bằng chứng record chưa được ghi.
7. **Nhiều record:** kiểm tra `allOf()` và trạng thái từng future khi chỉ một phần gửi thất bại.
8. **Threading:** xác nhận callback nặng được chuyển sang executor phù hợp thay vì chặn luồng I/O của producer.

Có thể dùng `spring-kafka-test` hoặc Kafka test starter phù hợp với dòng Spring Boot. Với lỗi mạng, broker failover và timeout thực tế, nên bổ sung kiểm thử với broker/container gần với môi trường triển khai.

## 13. Tổng kết

- `KafkaTemplate.send()` trả về `CompletableFuture<SendResult<K, V>>` trong Spring Kafka 3.0 trở lên.
- `SendResult` chứa `ProducerRecord` và `RecordMetadata`, giúp xác định topic, partition và offset đã được broker xác nhận.
- `whenComplete()` quan sát cả thành công và thất bại; `thenApply()` biến đổi kết quả; `thenCompose()` nối một future khác.
- `exceptionally()` và `handle()` giúp xử lý lỗi, nhưng không được biến thất bại thành thành công giả.
- Callback không async có thể chạy trên thread hoàn tất future; giữ callback ngắn và dùng executor cho công việc nặng.
- Timeout hoặc cancel không chứng minh record chưa được gửi; retry cần event ID và idempotency.
- Future xác nhận kết quả ghi Kafka, không xác nhận consumer đã hoàn tất nghiệp vụ.

Khi hiểu rõ `CompletableFuture` và `SendResult`, có thể xây dựng producer Spring Kafka không chặn luồng gọi, quan sát lỗi gửi và truyền kết quả bất đồng bộ qua các tầng service một cách có kiểm soát.
