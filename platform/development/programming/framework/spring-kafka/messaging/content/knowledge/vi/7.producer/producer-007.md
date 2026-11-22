# Gửi đồng bộ và bất đồng bộ

## 1. Cách Kafka producer gửi record

Trong Spring Kafka, `KafkaTemplate` là API thường dùng để gửi record đến Kafka. Khi gọi `send()`, ứng dụng chuyển topic, key và value (cùng metadata tùy chọn) cho Kafka producer. Producer serialize dữ liệu thành byte, đưa record vào bộ đệm gửi và giao việc truyền đến broker cho luồng I/O nền.

Điểm cần phân biệt là **cách gửi của producer** và **cách ứng dụng chờ kết quả**. Kafka producer gửi bất đồng bộ theo thiết kế. `KafkaTemplate.send()` trả về một `CompletableFuture<SendResult<K, V>>` trong Spring Kafka hiện đại. Ứng dụng có thể tiếp tục làm việc và nhận kết quả qua callback, hoặc chờ future hoàn tất để tạo hành vi đồng bộ ở phía luồng gọi.

```text
Service nghiệp vụ
      |
      | KafkaTemplate.send(topic, key, value)
      v
KafkaTemplate / ProducerFactory
      |
      v
KafkaProducer ── serialize ── producer buffer
      |                              |
      | trả CompletableFuture        | sender I/O nền
      v                              v
Luồng gọi tiếp tục             Kafka broker
                                     |
                                     v
                              broker acknowledgement
                                     |
                                     v
                              hoàn tất future
```

Future hoàn tất thành công khi producer nhận xác nhận theo cấu hình `acks` (hoặc theo chế độ xác nhận đã chọn). Điều này cho biết broker đã xử lý yêu cầu ghi ở mức xác nhận tương ứng; nó **không** chứng minh consumer đã nhận hoặc xử lý xong sự kiện.

## 2. Gửi bất đồng bộ với KafkaTemplate

Gửi bất đồng bộ là cách sử dụng tự nhiên của `KafkaTemplate.send()`: gọi phương thức, nhận future và không chặn luồng hiện tại để đợi broker xác nhận. Ứng dụng có thể trả future cho tầng gọi hoặc đăng ký callback để xử lý kết quả.

### Ví dụ publisher

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
                log.error("Cannot publish event {}", event.eventId(), exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info("Published event {} to {}-{} at offset {}",
                    event.eventId(), metadata.topic(), metadata.partition(),
                    metadata.offset());
        });

        return future;
    }
}
```

Trong ví dụ:

- `KafkaTemplate.send()` trả về future ngay sau khi producer nhận yêu cầu gửi và chuẩn bị gửi record.
- `whenComplete()` đăng ký hành động khi future hoàn tất, dù thành công hay thất bại.
- Khi thành công, `SendResult` cung cấp `RecordMetadata` như topic, partition và offset.
- Khi thất bại, callback nhận exception để log, cập nhật trạng thái hoặc kích hoạt xử lý phù hợp.
- Phương thức trả future cho tầng gọi để tầng đó có thể theo dõi kết quả thay vì bỏ mất thông tin gửi.

Callback không nên thực hiện công việc nặng hoặc chờ một tác vụ khác. Nó có thể chạy trên thread hoàn tất thao tác gửi; nếu callback chặn lâu, nó có thể ảnh hưởng đến khả năng xử lý các callback khác. Hãy giữ callback ngắn, hoặc chuyển công việc nặng sang executor được quản lý rõ ràng.

### Xử lý kết quả bằng CompletableFuture

Ngoài `whenComplete()`, có thể dùng các phép biến đổi của `CompletableFuture`:

```java
CompletableFuture<String> result =
        kafkaTemplate.send("orders", event.orderId(), event)
                .thenApply(sendResult -> {
                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    return metadata.topic() + "-" + metadata.partition()
                            + "-" + metadata.offset();
                });
```

`thenApply()` biến đổi kết quả thành một giá trị mới. `thenAccept()` dùng khi chỉ cần tiêu thụ kết quả; `whenComplete()` phù hợp khi muốn quan sát kết quả mà vẫn giữ nguyên giá trị hoàn tất. `exceptionally()` có thể chuyển lỗi thành một kết quả thay thế, nhưng cần thận trọng: nếu trả về giá trị mặc định mà không ghi nhận lỗi, ứng dụng có thể che giấu việc gửi thất bại.

Trong Spring Kafka 3.x trở lên, API gửi trả `CompletableFuture`. Các phiên bản Spring Kafka 2.x cũ sử dụng `ListenableFuture`; khi làm việc với dự án cũ, cần theo đúng kiểu trả về của phiên bản đang dùng thay vì sao chép ví dụ mới vào mã nguồn cũ.

## 3. Gửi đồng bộ bằng cách chờ future

Mặc dù `send()` là bất đồng bộ, ứng dụng có thể chờ kết quả bằng `get()` hoặc `join()`. Khi đó luồng gọi bị chặn cho đến khi producer nhận xác nhận hoặc thao tác thất bại.

### Dùng get() với timeout

```java
public SendResult<String, OrderCreated> publishAndWait(
        OrderCreated event) {
    try {
        return kafkaTemplate.send("orders", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
                "Interrupted while waiting for Kafka acknowledgement",
                exception);
    } catch (ExecutionException exception) {
        throw new IllegalStateException(
                "Kafka rejected or failed to send the event",
                exception.getCause());
    } catch (TimeoutException exception) {
        throw new IllegalStateException(
                "Timed out waiting for Kafka acknowledgement; outcome may be unknown",
                exception);
    }
}
```

`get(10, TimeUnit.SECONDS)` chặn luồng gọi tối đa 10 giây. Nếu broker xác nhận sớm hơn, phương thức trả `SendResult`; nếu gửi thất bại, `ExecutionException` chứa nguyên nhân; nếu hết thời gian chờ, `TimeoutException` được ném ra.

Khi bắt `InterruptedException`, cần khôi phục trạng thái interrupt bằng `Thread.currentThread().interrupt()` để tầng quản lý thread có thể nhận biết tín hiệu dừng.

**Timeout khi chờ không đồng nghĩa record chắc chắn chưa được gửi.** Future có thể hoàn tất sau thời điểm `get()` ném `TimeoutException`, bởi yêu cầu gửi vẫn đang được producer xử lý. Nếu tầng gọi lập tức gửi lại cùng sự kiện, broker có thể nhận cả hai lần. Cần dùng event ID ổn định, xử lý idempotent và một chính sách retry có kiểm soát để tránh tạo tác dụng phụ trùng lặp.

### Dùng join()

```java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders", event.orderId(), event).join();
```

`join()` cũng chặn luồng gọi đến khi future hoàn tất, nhưng không nhận timeout trực tiếp và thường bọc lỗi trong `CompletionException`. Với request xử lý cần giới hạn thời gian, `get(timeout, unit)` thường dễ kiểm soát hơn. Không nên gọi `join()` trên event loop hoặc thread phục vụ request có yêu cầu độ trễ chặt nếu chưa đánh giá nguy cơ chặn thread.

## 4. So sánh gửi đồng bộ và bất đồng bộ

| Tiêu chí | Gửi bất đồng bộ | Chờ đồng bộ |
|---|---|---|
| Cách gọi | Gọi `send()` và tiếp tục; xử lý kết quả qua future/callback | Gọi `send().get()` hoặc `send().join()` |
| Luồng gọi | Không chờ broker xác nhận | Bị chặn cho đến khi có kết quả hoặc timeout |
| Thông lượng | Có thể gửi nhiều record đang chờ cùng lúc, tận dụng batching của producer | Có thể giảm thông lượng nếu chờ từng record tuần tự |
| Xử lý lỗi | Xử lý qua future callback hoặc truyền future cho tầng gọi | Bắt lỗi ngay tại vị trí chờ kết quả |
| Phù hợp | Luồng event có thể tiếp tục và theo dõi kết quả sau | Cần kết quả broker trước khi trả kết quả nghiệp vụ hoặc thực hiện bước tiếp theo |
| Rủi ro chính | Bỏ quên future khiến lỗi gửi không được quan sát; callback chặn thread | Chặn thread, tăng latency và gây nghẽn nếu dùng quá nhiều |

Gửi bất đồng bộ không có nghĩa là “không cần quan tâm kết quả”. Nếu sự kiện quan trọng, ứng dụng phải quan sát future và quyết định cách xử lý lỗi. Gửi đồng bộ cũng không đảm bảo consumer xử lý ngay; nó chỉ chờ xác nhận ghi từ Kafka broker.

## 5. Cấu hình producer liên quan đến xác nhận gửi

Chiến lược chờ kết quả ở tầng ứng dụng cần đi cùng cấu hình producer. Một cấu hình thường dùng cho sự kiện nghiệp vụ quan trọng:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
```

- `acks=all` yêu cầu leader chờ các replica hiện có trong ISR xác nhận theo giao thức replication trước khi trả thành công.
- `enable.idempotence=true` giúp producer tránh tạo record trùng do retry nội bộ của producer trong phạm vi bảo đảm của Kafka.
- `delivery.timeout.ms` giới hạn tổng thời gian producer cố gắng hoàn tất gửi record, bao gồm thời gian chờ xác nhận và retry theo cấu hình client.

`acks=all` không tự động có nghĩa mọi replica theo replication factor đều xác nhận nếu replica không nằm trong ISR. Có thể kết hợp `min.insync.replicas` ở cấu hình topic/broker để yêu cầu số replica trong ISR tối thiểu khi ghi. Cấu hình producer và broker phải được thiết kế cùng nhau.

Ngoài ra, `max.block.ms` có thể khiến chính lời gọi `send()` chặn trong lúc chờ metadata hoặc chờ chỗ trong producer buffer. Vì vậy, API trả future không có nghĩa mọi đường đi của lời gọi luôn không chặn tuyệt đối. Cần cấu hình timeout và theo dõi latency phù hợp với tải thực tế.

## 6. Xử lý lỗi khi gửi bất đồng bộ

Lỗi gửi có thể xuất hiện ở nhiều giai đoạn:

- Lỗi cấu hình hoặc serialize dữ liệu trước khi record được gửi.
- Broker không khả dụng, lỗi mạng hoặc timeout.
- Broker từ chối ghi do quyền truy cập, topic hoặc điều kiện ISR.
- Producer hết thời gian giao record sau các lần retry.

Khi future hoàn tất exceptionally, ứng dụng cần phân loại lỗi. Lỗi tạm thời có thể được retry theo chính sách; lỗi cấu hình hoặc dữ liệu không hợp lệ cần sửa nguyên nhân. Không nên retry vô hạn hoặc retry mọi exception giống nhau.

Ví dụ xử lý lỗi trong callback:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders", event.orderId(), event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        Throwable cause = exception.getCause() != null
                ? exception.getCause() : exception;
        log.error("Publish failed for eventId={}", event.eventId(), cause);
        // Ghi nhận trạng thái thất bại hoặc đưa vào quy trình retry có kiểm soát.
        return;
    }

    log.info("Publish confirmed: topic={}, partition={}, offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset());
});
```

Nếu callback chỉ log lỗi rồi bỏ qua, tầng nghiệp vụ có thể không biết sự kiện đã thất bại. Với sự kiện phải được phát chắc chắn, cần lưu trạng thái gửi, dùng transactional outbox hoặc một cơ chế retry bền vững phù hợp với ranh giới transaction của hệ thống.

Không nên gọi `future.get()` ngay sau `send()` trong một đoạn mã được gọi là “bất đồng bộ”; làm vậy biến luồng gọi thành đồng bộ. Cũng không nên gọi `CompletableFuture.runAsync(() -> kafkaTemplate.send(...))` chỉ để làm cho Kafka gửi bất đồng bộ, vì Kafka producer vốn đã gửi trên I/O thread nền và việc bọc thêm executor không tạo thêm bảo đảm giao nhận.

## 7. Gửi nhiều record và batching

Kafka producer có thể gom nhiều record vào batch theo partition để giảm số request mạng. Gửi bất đồng bộ cho phép ứng dụng đưa nhiều record vào producer buffer trước khi chờ kết quả, nhờ đó producer có cơ hội batching tốt hơn.

Các thuộc tính thường ảnh hưởng đến batching:

- `batch.size`: kích thước batch mục tiêu theo partition.
- `linger.ms`: thời gian producer có thể chờ thêm record để tạo batch lớn hơn.
- `buffer.memory`: dung lượng bộ đệm producer.
- `max.in.flight.requests.per.connection`: số request chưa nhận phản hồi trên một kết nối.

Ví dụ cấu hình:

```yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 32768
        linger.ms: 5
        buffer.memory: 67108864
```

Các giá trị trên chỉ là ví dụ minh họa, không phải cấu hình tối ưu chung. Batch lớn hoặc `linger.ms` cao có thể tăng throughput nhưng cũng làm tăng độ trễ và bộ nhớ sử dụng. Cần đo với kích thước record, số partition, lưu lượng và SLA thực tế.

Nếu gọi `send().get()` tuần tự sau mỗi record, ứng dụng thường không tận dụng tốt khả năng gom batch vì luôn chờ xác nhận trước khi gửi record tiếp theo. Nếu cần gửi nhiều record, có thể gửi các future trước rồi chờ tất cả hoàn tất:

```java
List<CompletableFuture<SendResult<String, OrderCreated>>> futures =
        events.stream()
                .map(event -> kafkaTemplate.send(
                        "orders", event.orderId(), event))
                .toList();

CompletableFuture<Void> allSends =
        CompletableFuture.allOf(futures.toArray(CompletableFuture[]::new));

allSends.join(); // Chỉ hoàn tất thành công nếu tất cả future thành công.
```

Trong production, cần xử lý exception của `allOf`, theo dõi từng future để biết record nào thành công/thất bại và tránh retry mù toàn bộ batch. `allOf()` không tự cung cấp danh sách kết quả; có thể đọc từng future sau khi nhóm hoàn tất.

## 8. Ordering khi gửi đồng bộ và bất đồng bộ

Kafka đảm bảo thứ tự record trong phạm vi một partition. Producer gửi record có cùng key thường định tuyến về cùng partition theo partitioner đang cấu hình. Tuy nhiên, việc gửi bất đồng bộ từ nhiều thread có thể khiến các yêu cầu được đưa vào producer theo thứ tự cạnh tranh giữa các thread.

Nếu nghiệp vụ cần giữ thứ tự theo entity:

- Dùng key ổn định như `orderId` để các sự kiện của cùng đơn hàng vào cùng partition.
- Tránh gửi song song các sự kiện cùng entity từ nhiều thread nếu thứ tự gọi không được kiểm soát.
- Bật idempotent producer và giữ cấu hình producer tương thích để retry không làm đảo thứ tự trong phạm vi bảo đảm của Kafka.
- Nếu cần chuỗi sự kiện nghiêm ngặt, hãy thiết kế thứ tự phát từ service nghiệp vụ và kiểm thử khi retry, timeout hoặc rebalance.

Gửi đồng bộ theo từng record trên một thread giúp đơn giản hóa trình tự chờ xác nhận, nhưng không tạo thứ tự toàn cục giữa các partition. Ngược lại, gửi bất đồng bộ không tự phá thứ tự nếu các record được gửi cùng partition theo đúng trình tự; điều cần kiểm soát là thứ tự phát và concurrency.

## 9. Gửi sự kiện trong luồng nghiệp vụ

Khi một đơn hàng được tạo, Order Service có thể gửi `OrderCreated` và cần quyết định lúc nào trả kết quả cho API gọi nó.

**Chờ xác nhận Kafka trước khi trả kết quả:** phù hợp khi API chỉ được coi là hoàn tất sau khi broker xác nhận đã ghi record. Cách này làm request chờ Kafka và cần timeout phù hợp. Nếu timeout, kết quả gửi có thể chưa rõ; cần event ID và xử lý retry an toàn.

**Trả kết quả trước, theo dõi gửi bất đồng bộ:** có thể giảm thời gian chờ của request nhưng yêu cầu ứng dụng có cách theo dõi lỗi và bảo đảm sự kiện không bị mất khi process dừng. Chỉ tạo future rồi bỏ quên không phải chiến lược giao nhận tin cậy.

Nếu việc lưu đơn hàng vào database và phát sự kiện phải nguyên tử, gọi `KafkaTemplate.send()` sau khi commit database vẫn có khoảng hở: database có thể đã commit nhưng ứng dụng dừng trước khi Kafka nhận sự kiện. Với trường hợp này, hãy xem xét Transactional Outbox: ghi đơn hàng và bản ghi outbox trong cùng transaction database, sau đó một publisher riêng gửi outbox sang Kafka và đánh dấu trạng thái đã gửi.

## 10. Kiểm thử gửi đồng bộ và bất đồng bộ

Kiểm thử nên xác minh cả kết quả gửi và hành vi của luồng gọi:

1. **Gửi thành công:** gửi record đến broker test, chờ future hoàn tất và kiểm tra topic, partition, offset trong `SendResult`.
2. **Không chặn luồng gọi:** gọi publisher bất đồng bộ và xác nhận phương thức trả future trước khi callback hoàn tất trong điều kiện test được kiểm soát.
3. **Lỗi gửi:** dùng broker dừng hoặc cấu hình sai để xác nhận future hoàn tất exceptional và lỗi được ghi nhận.
4. **Timeout:** giới hạn thời gian chờ ở tầng gọi và xác minh hệ thống không giả định record chắc chắn chưa được ghi.
5. **Nhiều record:** gửi một nhóm record, kiểm tra tất cả future và xác minh không bỏ sót lỗi của một phần batch.
6. **Ordering:** gửi các sự kiện cùng key, xác nhận chúng vào cùng partition và được đọc theo thứ tự append.
7. **Dừng ứng dụng:** kiểm tra cách ứng dụng xử lý future còn pending khi shutdown và có cơ chế lưu lại sự kiện chưa gửi hay không.

Có thể dùng `spring-kafka-test` hoặc Kafka test starter tương ứng với dòng Spring Boot để kiểm thử tích hợp. Với timeout mạng, broker failover và tải lớn, nên bổ sung kiểm thử với Kafka broker/container gần với môi trường triển khai.

## 11. Lựa chọn chiến lược trong ứng dụng Spring Kafka

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Gửi một sự kiện và cần biết broker xác nhận trước khi tiếp tục | `kafkaTemplate.send(...).get(timeout, unit)` |
| Gửi sự kiện và để tầng gọi tự quyết định thời điểm chờ | Trả `CompletableFuture<SendResult<K, V>>` |
| Ghi log hoặc cập nhật metric khi gửi hoàn tất | `whenComplete()` với callback ngắn |
| Biến metadata gửi thành kết quả khác | `thenApply()` hoặc `thenCompose()` |
| Gửi nhiều record để tận dụng batching | Gọi nhiều `send()` trước, sau đó theo dõi các future hoặc `allOf()` |
| Sự kiện phải được phát bền vững cùng transaction nghiệp vụ database | Transactional Outbox và publisher có retry |

Đối với phần lớn producer trong Spring Kafka, nên giữ API bất đồng bộ và để tầng gọi quyết định có cần chờ kết quả hay không. Khi phải chờ, đặt timeout hữu hạn, phân biệt timeout với lỗi xác nhận và thiết kế retry theo event ID để không tạo bản ghi nghiệp vụ trùng.

## 12. Tổng kết

- `KafkaTemplate.send()` gửi bất đồng bộ và trả `CompletableFuture<SendResult<K, V>>` trong Spring Kafka hiện đại.
- Gọi `get()` hoặc `join()` khiến luồng gọi chờ kết quả, tạo cách sử dụng đồng bộ ở phía ứng dụng.
- `whenComplete()`, `thenApply()` và các phép biến đổi future giúp xử lý kết quả mà không chặn luồng gọi.
- Thành công của future phản ánh xác nhận ghi theo cấu hình producer, không chứng minh consumer đã xử lý sự kiện.
- Timeout khi chờ không chứng minh record chưa được gửi; retry cần event ID và idempotency.
- `acks`, idempotence, delivery timeout, batching và partition key ảnh hưởng đến độ tin cậy, latency và thứ tự.
- Với sự kiện quan trọng, phải quan sát lỗi và cân nhắc Outbox để tránh mất sự kiện giữa database và Kafka.

Hiểu rõ sự khác nhau giữa gửi bất đồng bộ và chờ đồng bộ giúp thiết kế producer phù hợp với SLA của ứng dụng. `KafkaTemplate` cung cấp cơ chế gửi nền; ứng dụng quyết định cách chờ, xử lý lỗi và bảo đảm sự kiện được phát đi một cách đáng tin cậy.
