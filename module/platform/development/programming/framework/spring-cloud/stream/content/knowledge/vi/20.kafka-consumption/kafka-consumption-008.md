# Nhận theo lô với batch-mode và List payload

Kafka consumer thường nhận dữ liệu bằng cách gọi `poll()`. Một lần poll có thể trả về nhiều record từ các partition được gán cho consumer. Với chế độ record listener mặc định, Spring Cloud Stream gọi function một lần cho mỗi record. Khi bật `batch-mode`, Kafka Binder chuyển các record của một lần poll thành một danh sách và gọi function với `List<T>` hoặc `Message<List<T>>`.

Batch mode giúp giảm chi phí gọi handler và phù hợp với các thao tác có thể xử lý nhiều bản ghi cùng lúc, chẳng hạn ghi dữ liệu theo lô hoặc tổng hợp sự kiện. Tuy nhiên, một batch là tập hợp các Kafka record riêng biệt được nhận trong một lần poll; nó không phải một Kafka record duy nhất chứa mảng JSON. Việc xử lý theo lô cũng làm thay đổi cách truy cập header, retry, acknowledgement và DLQ. Cần hiểu rõ các điểm này trước khi bật chế độ.

## 1. Batch mode hoạt động như thế nào?

Trong chế độ thông thường, Kafka Binder chuyển từng record thành một message và gọi function cho từng record. Với `batch-mode: true`, binder đưa toàn bộ record nhận được từ một lần poll vào một danh sách rồi gọi function một lần.

Ví dụ topic có các record:

```text
Poll lần 1:
  partition 0: offset 120, OrderCreated(order-101)
  partition 0: offset 121, OrderCreated(order-102)
  partition 1: offset  88, OrderCreated(order-103)
```

Với record mode, function có thể được gọi ba lần. Với batch mode, function nhận một payload có ba phần tử:

```text
Consumer<List<OrderCreated>>
    |
    +-- OrderCreated(order-101)
    +-- OrderCreated(order-102)
    +-- OrderCreated(order-103)
```

Batch được tạo từ các record Kafka trả về trong lần poll đó. Kích thước thực tế không nhất thiết bằng `max.poll.records`; đây là giới hạn trên cho số record mà một lần `poll()` trả về. Số record còn phụ thuộc dữ liệu sẵn có, partition assignment và các thuộc tính fetch của Kafka consumer.

Batch mode được hỗ trợ với mô hình functional của Spring Cloud Stream. Không dùng `@StreamListener` để nhận batch; API đó không hỗ trợ chế độ này.

## 2. Bật batch-mode cho input binding

Giả sử ứng dụng có function xử lý sự kiện đơn hàng:

```java
@Bean
Consumer<List<OrderCreated>> processOrderBatch(
        OrderBatchService orderBatchService) {

    return events -> orderBatchService.process(events);
}
```

Cấu hình input binding:

```yaml
spring:
  cloud:
    function:
      definition: processOrderBatch
    stream:
      bindings:
        processOrderBatch-in-0:
          destination: orders.created
          group: order-batch-service
          consumer:
            batch-mode: true
```

Thuộc tính `batch-mode` thuộc common consumer binding properties. Nó bật chế độ listener nhận nhiều record trong một lần gọi. Chỉ đặt thuộc tính này cho input binding Kafka cần nhận batch; không đặt ở binder-level hoặc producer binding.

Group có tên giúp các instance của dịch vụ cùng chia partition. Mỗi lần poll của một consumer chỉ bao gồm record từ những partition được gán cho consumer đó.

## 3. Hai kiểu chữ ký được hỗ trợ

Khi batch mode được bật, Kafka Binder hỗ trợ hai kiểu đầu vào chính:

```java
Consumer<List<OrderCreated>>
```

và:

```java
Consumer<Message<List<OrderCreated>>>
```

Kiểu đầu tiên nhận danh sách payload. Nó đơn giản khi logic chỉ cần dữ liệu nghiệp vụ. Tuy nhiên, function không nhận message headers.

Kiểu thứ hai nhận một message bao ngoài danh sách payload. Function có thể đọc headers ở cấp batch, nhưng các giá trị header thường là collection tương ứng với từng phần tử, không phải một giá trị đơn áp dụng cho toàn batch.

Không hỗ trợ kiểu `List<Message<OrderCreated>>` trong batch mode. Không nên tự giả định binder sẽ tạo một Message đầy đủ riêng cho từng phần tử.

### Chỉ cần payload: List<T>

```java
@Bean
Consumer<List<OrderCreated>> processOrderBatch(
        OrderBatchService service) {

    return events -> {
        if (events.isEmpty()) {
            return;
        }

        service.process(events);
    };
}
```

Đây là lựa chọn đơn giản khi service chỉ cần danh sách sự kiện. Không có headers nên nếu cần event ID, Kafka offset, partition hoặc correlation metadata, hãy dùng kiểu `Message<List<T>>`.

### Cần metadata: Message<List<T>>

```java
@Bean
Consumer<Message<List<OrderCreated>>> processOrderBatch(
        OrderBatchService service) {

    return batch -> {
        List<OrderCreated> events = batch.getPayload();

        Object eventIds = batch.getHeaders().get("eventId");
        Object correlationIds =
            batch.getHeaders().get("correlationId");

        service.process(events, eventIds, correlationIds);
    };
}
```

Ví dụ minh họa việc đọc header. Khi batch có nhiều record, header tùy chỉnh được biểu diễn dưới dạng collection; phần tử thứ `i` tương ứng với payload ở vị trí `i`. Cần kiểm tra kiểu và kích thước collection trước khi ghép metadata với sự kiện. Không lấy một giá trị header đơn rồi áp dụng cho mọi record nếu header đó thực chất là danh sách.

## 4. Cách đọc batch headers theo đúng thứ tự

Giả sử batch có ba sự kiện và mỗi record mang `eventId` riêng. Khi dùng `Message<List<OrderCreated>>`, header map có thể chứa:

```text
payload:
  [order-101, order-102, order-103]

headers:
  eventId:
    [evt-501, evt-502, evt-503]
  correlationId:
    [checkout-A, checkout-B, checkout-C]
```

Các collection header có cùng thứ tự tương ứng với danh sách payload. Có thể ghép theo chỉ số:

```java
@Bean
Consumer<Message<List<OrderCreated>>> processOrderBatch(
        OrderBatchService service) {

    return batch -> {
        List<OrderCreated> events = batch.getPayload();

        List<?> eventIds = asList(
            batch.getHeaders().get("eventId")
        );

        if (!eventIds.isEmpty() && eventIds.size() != events.size()) {
            throw new IllegalStateException(
                "eventId header count does not match batch size"
            );
        }

        for (int i = 0; i < events.size(); i++) {
            String eventId = eventIds.isEmpty()
                ? null
                : String.valueOf(eventIds.get(i));

            service.process(events.get(i), eventId);
        }
    };
}

private List<?> asList(Object value) {
    if (value == null) {
        return List.of();
    }
    if (value instanceof Collection<?> collection) {
        return new ArrayList<>(collection);
    }
    return List.of(value);
}
```

Đây là ví dụ minh họa; trong dự án cần đặt helper ở lớp phù hợp và quyết định rõ header nào bắt buộc. Nếu header được chuyển đổi thành kiểu collection khác, hãy chuẩn hóa theo kiểu thực tế của binder. Không dùng `List.copyOf()` nếu collection có thể chứa `null`, vì hàm này không chấp nhận phần tử null.

Với Kafka batch listener, một số metadata được cung cấp dưới dạng danh sách. Nếu cần truy cập các header đã chuyển đổi theo từng record, Spring Cloud Stream Kafka Binder còn cung cấp header `kafka_batchConvertedHeaders` trong một số đường xử lý; header này chứa danh sách map metadata theo thứ tự payload. Hãy đối chiếu phiên bản binder và Spring Kafka đang dùng trước khi phụ thuộc vào header này.

## 5. Kích thước batch và Kafka consumer properties

Batch size chịu ảnh hưởng của Kafka consumer properties. Các thuộc tính thường được xem xét:

| Thuộc tính | Vai trò |
|---|---|
| `max.poll.records` | Giới hạn số record tối đa trả về từ một lần `poll()` |
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả fetch response |
| `fetch.max.wait.ms` | Thời gian broker tối đa chờ để đạt `fetch.min.bytes` |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu fetch cho mỗi partition |
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần poll trước khi consumer bị xem là không còn tiến triển |

Ví dụ cấu hình theo binding:

```yaml
spring:
  cloud:
    function:
      definition: processOrderBatch
    stream:
      bindings:
        processOrderBatch-in-0:
          destination: orders.created
          group: order-batch-service
          consumer:
            batch-mode: true
      kafka:
        bindings:
          processOrderBatch-in-0:
            consumer:
              configuration:
                max.poll.records: 200
                fetch.min.bytes: 1024
                fetch.max.wait.ms: 100
```

`max.poll.records` đặt giới hạn 200 record cho mỗi lần poll trong ví dụ. Đây không phải cam kết mọi batch luôn có 200 phần tử. Nếu topic đang ít dữ liệu, batch có thể nhỏ hơn; nếu record chưa đủ điều kiện fetch theo cấu hình, consumer có thể nhận batch nhỏ hoặc chờ theo thời gian fetch.

Tăng `max.poll.records` có thể giảm số lần gọi listener và tăng throughput, nhưng cũng làm tăng lượng dữ liệu phải giữ và xử lý trong một lần. Nếu handler xử lý quá lâu, consumer có thể vượt `max.poll.interval.ms`, bị rời group và kích hoạt rebalance. Hãy đo thời gian xử lý batch thực tế trước khi tăng giới hạn.

## 6. Batch mode khác producer batching và List payload do ứng dụng phát

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Consumer batch mode | Một lần Kafka poll trả về nhiều record và function nhận một `List<T>` |
| Producer batching | Kafka producer gom nhiều record vào request/batch mạng để tăng hiệu quả truyền |
| Một payload dạng List | Producer phát một Kafka record duy nhất có value chứa danh sách dữ liệu, ví dụ JSON array |

Consumer batch mode không biến nhiều Kafka record thành một record mới. Các record vẫn có key, partition, offset, timestamp và metadata riêng. Binder chỉ gom chúng thành một danh sách ở ranh giới gọi function.

Nếu producer gửi JSON array trong một record, consumer record mode có thể giải mã payload đó thành `List<T>` tùy converter và kiểu đích; đó không phải Kafka batch mode. Ngược lại, khi bật batch mode, `List<T>` thường là danh sách các value từ nhiều record riêng biệt.

Producer batching cũng độc lập với consumer batch mode. Kafka producer có thể gom record để gửi hiệu quả ngay cả khi consumer nhận từng record một.

## 7. Xử lý toàn batch hay từng phần tử?

Có hai cách tổ chức xử lý:

- Gọi một service nhận toàn bộ `List<T>` để thực hiện thao tác theo lô, chẳng hạn batch insert hoặc gọi API hỗ trợ bulk.
- Lặp qua từng phần tử để áp dụng quy tắc nghiệp vụ riêng.

Ví dụ xử lý theo lô:

```java
@Service
public class OrderBatchService {

    private final OrderRepository repository;

    public OrderBatchService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(List<OrderCreated> events) {
        List<Order> orders = events.stream()
            .map(Order::from)
            .toList();

        repository.saveAll(orders);
    }
}
```

Cách này phù hợp khi các thao tác có thể dùng chung transaction hoặc API bulk. Tuy nhiên, transaction database của batch không tự động bao gồm Kafka offset commit. Nếu database commit thành công rồi consumer lỗi trước khi offset được commit, các record có thể được giao lại. Cần idempotency hoặc deduplication.

Nếu xử lý từng phần tử trong vòng lặp và phần tử thứ ba thất bại sau khi hai phần tử đầu đã commit độc lập, toàn bộ batch có thể bị xử lý lại tùy error handler và acknowledgement. Khi đó hai phần tử đầu có thể chạy lần nữa. Hãy xác định rõ transaction boundary và đảm bảo thao tác có thể lặp an toàn.

## 8. Retry trong batch mode

Kafka Binder không hỗ trợ retry nội bộ theo `maxAttempts` như record mode khi batch mode được bật. Trong chế độ này, `maxAttempts` bị ghi đè thành `1`. Vì vậy, không nên cấu hình `max-attempts: 5` rồi kỳ vọng binder tự gọi lại function năm lần cho cả batch.

Nếu cần retry, có thể cấu hình `DefaultErrorHandler` của Spring Kafka thông qua `ListenerContainerCustomizer` hoặc error handler phù hợp với phiên bản Spring Kafka đang dùng. Error handler có thể áp dụng backoff, retry hoặc recover theo record/batch semantics.

Một hướng khác là sử dụng manual acknowledgement và `Acknowledgment.nack(index, sleep)` trong batch listener để xác nhận phần trước chỉ số lỗi và yêu cầu phần còn lại được giao lại theo semantics của Spring Kafka. Cần hiểu rõ AckMode, vị trí index và cách container xử lý phần batch còn lại. API này không thay thế việc thiết kế idempotency.

Không áp dụng mẫu retry của record listener cho batch listener mà chưa kiểm tra. Cách framework định vị record lỗi và seek/replay có thể khác nhau.

## 9. Acknowledgement và xử lý một phần batch

Khi xử lý batch, một exception có thể làm cả lần gọi listener thất bại. Nếu không có chiến lược partial acknowledgement, record đã xử lý trước đó cũng có thể được giao lại khi offset chưa được commit.

Nếu cần xác nhận thủ công, có thể nhận `Acknowledgment` từ header của `Message<List<T>>` theo cấu hình manual ack phù hợp. Ví dụ khái quát:

```java
@Bean
Consumer<Message<List<OrderCreated>>> processOrderBatch(
        OrderBatchService service) {

    return batch -> {
        Acknowledgment acknowledgment =
            batch.getHeaders().get(
                KafkaHeaders.ACKNOWLEDGMENT,
                Acknowledgment.class
            );

        List<OrderCreated> events = batch.getPayload();

        for (int i = 0; i < events.size(); i++) {
            service.process(events.get(i));

            // Chỉ thực hiện ack/nack theo chiến lược đã thiết kế.
        }

        if (acknowledgment != null) {
            acknowledgment.acknowledge();
        }
    };
}
```

Ví dụ chỉ minh họa vị trí truy cập acknowledgment; không nên sao chép mà chưa cấu hình `ackMode` và xác định transaction/commit strategy. Việc gọi `acknowledge()` sau vòng lặp chỉ phù hợp nếu toàn bộ phần tử đã xử lý thành công theo hợp đồng nghiệp vụ.

Với partial batch failure, Spring Kafka cung cấp API `nack(index, sleep)` trong các chế độ acknowledgement được hỗ trợ. Cần đọc tài liệu Spring Kafka của phiên bản đang dùng để xác minh cách commit offset trước index và redeliver phần còn lại. Không gọi `acknowledge()` trước khi xử lý hoàn tất nếu điều đó có thể làm mất khả năng giao lại phần chưa xử lý.

## 10. DLQ khi bật batch mode

Kafka Binder hỗ trợ DLQ cho batch mode từ phiên bản 4.0.2. Cần lưu ý hành vi quan trọng: khi sử dụng DLQ trên consumer binding batch mode, tất cả record nhận được từ lần poll trước có thể được chuyển tới DLT, không chỉ riêng record gây lỗi.

Điều này có thể làm các record hợp lệ trong cùng batch xuất hiện trong DLT cùng với record lỗi. Vì vậy, quy trình vận hành cần:

- Giữ event ID và metadata để xác định record thực sự gây lỗi.
- Không replay toàn bộ batch một cách mù quáng.
- Kiểm tra idempotency trước khi phát lại record đã được xử lý một phần.
- Có công cụ lọc và replay theo record.
- Xác minh hành vi DLT của phiên bản Kafka Binder đang dùng.

Nếu yêu cầu cô lập chính xác một record lỗi và tiếp tục các record khác, hãy cân nhắc batch error handler, partial acknowledgement hoặc quay lại record mode. Chọn cơ chế theo yêu cầu thứ tự, throughput và khả năng phục hồi.

## 11. Null payload và tombstone records

Kafka có thể có tombstone record với value null, đặc biệt trong compacted topic. Khi nhận batch, phần tử tương ứng trong danh sách có thể là `null` cho cả kiểu `List<T>` và `Message<List<T>>`.

Không giả định mọi phần tử trong batch đều khác null. Nếu consumer đọc compacted topic hoặc luồng có tombstone, cần xử lý null có chủ đích:

```java
@Bean
Consumer<List<OrderSnapshot>> processSnapshots(
        SnapshotService service) {

    return snapshots -> {
        for (OrderSnapshot snapshot : snapshots) {
            if (snapshot == null) {
                // Xử lý tombstone theo hợp đồng của ứng dụng.
                continue;
            }

            service.apply(snapshot);
        }
    };
}
```

Tùy nghiệp vụ, tombstone có thể mang ý nghĩa xóa key khỏi trạng thái compacted. Bỏ qua null chỉ đúng nếu ứng dụng không cần xử lý thao tác xóa đó.

## 12. Observability và tracing trong batch mode

Tracing propagation không được hỗ trợ trực tiếp theo cách giống record listener khi nhận batch. Một batch có thể chứa record từ nhiều partition và producer khác nhau, mỗi record có thể mang trace context riêng hoặc không có trace context. Framework không thể gán một trace ID duy nhất cho toàn batch mà vẫn giữ đúng quan hệ nguồn gốc.

Khi dùng `Message<List<T>>`, Kafka Binder có thể cung cấp header `kafka_batchConvertedHeaders` chứa các map header theo từng record. Nếu cần tạo observation/span cho từng sự kiện, ứng dụng phải tự ghép metadata với phần tử tương ứng và quản lý vòng đời observation.

Nên ghi nhận các metric:

- Số batch nhận được.
- Số record trong mỗi batch.
- Thời gian xử lý batch và thời gian xử lý từng record nếu có.
- Số batch lỗi, số record lỗi và số lần redelivery.
- Consumer lag theo group/partition.
- Số record đưa vào DLT và số record replay.

Không chỉ đo số lần function được gọi; một lần gọi có thể xử lý một record hoặc hàng trăm record. Throughput nên được đo bằng số record/giây, đồng thời theo dõi độ trễ của từng record.

## 13. Khi nào nên dùng batch mode?

Batch mode phù hợp khi:

- Mỗi lần poll thường có nhiều record.
- Service hoặc database hỗ trợ bulk operation.
- Chi phí gọi function hoặc transaction theo từng record đáng kể.
- Có thể chấp nhận xử lý và phục hồi theo ranh giới batch.
- Ứng dụng có chiến lược idempotency, retry và DLQ phù hợp.

Record mode thường phù hợp hơn khi:

- Mỗi record cần retry hoặc DLQ độc lập.
- Xử lý cần độ trễ thấp cho từng sự kiện.
- Header/tracing cần được xử lý theo từng record bằng cơ chế chuẩn.
- Lỗi một record không nên ảnh hưởng các record khác.
- Logic nghiệp vụ đơn giản và không có lợi ích rõ ràng từ bulk processing.

Batch không tự động nhanh hơn trong mọi trường hợp. Batch lớn có thể làm tăng latency, memory pressure và thời gian xử lý trước khi commit offset. Hãy đo bằng workload thực tế.

## 14. Kiểm thử batch consumer

Nên kiểm thử ít nhất các tình huống sau:

1. Batch có một record.
2. Batch có nhiều record từ cùng partition.
3. Batch có record từ nhiều partition.
4. Payload được chuyển đổi đúng thành `List<T>`.
5. Header collection được ghép đúng thứ tự với payload.
6. Một record sai schema làm batch thất bại theo chính sách dự kiến.
7. Một record lỗi sau khi các record trước đã có side effect.
8. Retry/error handler xử lý batch theo đúng chính sách.
9. DLQ chứa đúng record hoặc toàn batch theo semantics phiên bản binder.
10. Tombstone/null được xử lý đúng.
11. Consumer restart trước khi offset commit và redelivery xảy ra.
12. Batch lớn không vượt giới hạn thời gian poll hoặc bộ nhớ.

Test Binder có thể xác minh một số logic function và binding trong bộ nhớ, nhưng không mô phỏng đầy đủ Kafka consumer poll batch, partition assignment, offset commit, batch nack hoặc DLT. Dùng integration test với Kafka thật, chẳng hạn qua Testcontainers, để xác minh những hành vi này.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Function vẫn nhận từng record | Chưa bật `consumer.batch-mode` cho đúng input binding | Kiểm tra binding name và cấu hình |
| Không đọc được headers | Function dùng `List<T>` | Đổi sang `Message<List<T>>` |
| Header không phải một giá trị đơn | Batch headers được biểu diễn thành collection | Ghép header với payload theo cùng index |
| Dùng `List<Message<T>>` bị lỗi | Kiểu chữ ký này không được hỗ trợ trong batch mode | Dùng `List<T>` hoặc `Message<List<T>>` |
| Retry không chạy theo maxAttempts | Binder retry không hỗ trợ trong batch mode; maxAttempts bị đặt thành 1 | Cấu hình error handler phù hợp |
| Nhiều record xuất hiện trong DLT | DLQ batch có thể chuyển toàn bộ batch của poll trước | Phân tích từng record và replay có chọn lọc |
| Consumer bị rebalance | Xử lý batch lâu, vượt `max.poll.interval.ms` | Giảm batch size, tối ưu handler hoặc điều chỉnh timeout phù hợp |
| Null làm handler lỗi | Batch có tombstone record | Xử lý null theo hợp đồng |
| Tracing batch không có một trace ID | Batch có thể chứa nhiều nguồn và trace context | Xử lý metadata theo từng record |

## 16. Checklist production

- Bật `batch-mode: true` đúng input binding Kafka và dùng functional programming model.
- Chọn `List<T>` nếu chỉ cần payload; chọn `Message<List<T>>` nếu cần headers.
- Không dùng `List<Message<T>>` trong batch mode.
- Nhớ rằng batch là nhiều Kafka record từ một lần poll, không phải một record có JSON array.
- Điều chỉnh `max.poll.records`, fetch settings và `max.poll.interval.ms` theo thời gian xử lý.
- Giới hạn kích thước batch và theo dõi memory/latency.
- Ghép batch headers theo index, không coi chúng là scalar.
- Thiết kế idempotency vì batch có thể được giao lại sau lỗi.
- Không dựa vào `max-attempts` để retry batch; cấu hình error handler phù hợp.
- Hiểu DLQ batch có thể chuyển tất cả record của poll trước vào DLT.
- Xử lý tombstone/null nếu topic có compacted records.
- Theo dõi record throughput, batch size, consumer lag, retry và DLT.
- Kiểm thử offset, redelivery, partial failure và DLQ với Kafka thật.

## 17. Tài liệu tham khảo

- [Spring Cloud Stream Kafka Binder — Consuming Batches](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/consume-batches.html), kiểu chữ ký batch, headers, retry, DLQ và observability.
- [Spring Cloud Stream Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html), cấu hình Kafka consumer và binder.
- [Apache Kafka Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs), `max.poll.records`, fetch settings và `max.poll.interval.ms`.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/), batch listener, error handler và manual acknowledgement.

Batch mode của Kafka Binder gom các record nhận trong một lần poll thành `List<T>` để function xử lý theo lô. Chọn `Message<List<T>>` khi cần metadata, ghi nhớ rằng headers cũng được gom theo từng record và retry/DLQ có semantics riêng. Khi batch size, acknowledgement, idempotency và error handling được thiết kế đồng bộ, consumer có thể tăng hiệu quả xử lý mà vẫn kiểm soát được việc phục hồi khi một record trong batch gặp lỗi.

