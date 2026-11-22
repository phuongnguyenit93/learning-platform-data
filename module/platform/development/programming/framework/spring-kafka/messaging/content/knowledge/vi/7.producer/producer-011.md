# Batching ở phía producer

Kafka producer không cần gửi từng record thành một request riêng. Producer có thể gom nhiều record thành một batch rồi gửi batch tới broker, giúp giảm số request, tận dụng mạng tốt hơn và thường tăng throughput. Batching cũng tạo ra một đánh đổi: producer có thể phải chờ thêm một khoảng ngắn để gom đủ dữ liệu, làm tăng độ trễ gửi. Trong Spring Kafka, cơ chế batching này nằm ở Kafka client được `KafkaTemplate` sử dụng; vì vậy cần hiểu các thuộc tính của producer client để cấu hình đúng.

## 1. Batching hoạt động như thế nào?

Khi ứng dụng gọi `KafkaTemplate.send()` hoặc `KafkaProducer.send()`, record được serialize và đưa vào vùng đệm của producer. Kafka client tổ chức các batch theo partition đích. Một batch chỉ chứa các record dành cho cùng một partition; record của partition khác được gom trong batch khác, dù có thể được gửi trong cùng một request mạng.

Luồng xử lý khái quát:

```text
Ứng dụng gọi send(record)
          |
          v
Serialize key/value và chọn partition
          |
          v
RecordAccumulator lưu record vào batch của partition
          |
          +---- batch đủ kích thước ------------------+
          |                                           |
          +---- hết linger.ms ------------------------+----> Sender gửi request
          |                                           |       tới broker
          +---- buffer cần được giải phóng ------------+          |
                                                              v
                                                     Broker xử lý batch
                                                              |
                                                              v
                                                   Callback/Future hoàn tất
```

`RecordAccumulator` là vùng đệm logic nơi client gom record. Một luồng gửi nền (Sender) lấy các batch sẵn sàng và gửi chúng tới broker. Producer có thể gửi nhiều batch của nhiều partition trong một request, nhưng việc gom record vào batch vẫn diễn ra theo từng partition.

Batch thường được gửi khi đạt giới hạn kích thước, khi hết thời gian chờ `linger.ms`, khi producer cần giải phóng buffer hoặc khi ứng dụng gọi thao tác flush/close. Batch không nhất thiết luôn đầy: nếu lưu lượng thấp, hết `linger.ms` có thể khiến batch nhỏ được gửi đi. Mục tiêu cấu hình là đạt kích thước batch đủ tốt mà không làm tăng độ trễ quá mức.

## 2. Các thuộc tính quyết định batching

| Thuộc tính | Vai trò | Ảnh hưởng khi tăng |
|---|---|---|
| `batch.size` | Kích thước mục tiêu tối đa của một batch theo byte cho mỗi partition | Có thêm chỗ để gom record; có thể tăng throughput và mức nén, nhưng dùng nhiều buffer hơn |
| `linger.ms` | Thời gian producer chờ thêm record trước khi gửi batch chưa đầy | Có cơ hội gom nhiều record hơn; tăng độ trễ chờ trong điều kiện tải thấp |
| `buffer.memory` | Tổng dung lượng bộ nhớ producer dành cho các record đang chờ gửi | Chịu được nhiều dữ liệu chờ hơn, nhưng tăng mức sử dụng bộ nhớ |
| `compression.type` | Thuật toán nén batch trước khi gửi | Giảm byte truyền và dung lượng lưu, đổi lại tiêu tốn CPU |
| `max.request.size` | Giới hạn kích thước request gửi tới broker | Giới hạn kích thước request; cần phối hợp với kích thước record và batch |

`batch.size` được tính theo byte và áp dụng cho batch của từng partition, không phải giới hạn tổng bộ nhớ của toàn producer. Record lớn có thể khiến batch chỉ chứa một hoặc vài record; Kafka không chia một record lớn thành nhiều record nhỏ để vừa batch. Kích thước record còn chịu các giới hạn khác như `max.request.size` ở producer và giới hạn message/batch tương ứng phía broker/topic.

`linger.ms` đặt thời gian chờ tối đa để có thêm record cho batch. Khi tải cao, batch có thể đầy trước khi hết thời gian chờ; khi tải thấp, producer thường gửi batch khi hết `linger.ms`. Vì vậy, tăng `linger.ms` không bảo đảm batch luôn đầy, nhưng có thể cải thiện mức gom dữ liệu khi record đến rải rác.

`buffer.memory` là ngân sách bộ nhớ cho các record đã được chấp nhận nhưng chưa gửi xong. Khi buffer gần cạn, lời gọi `send()` có thể phải chờ tối đa `max.block.ms` để có chỗ trống hoặc để lấy metadata. Nếu không giải phóng được buffer trong thời gian này, producer có thể ném `TimeoutException`. Tăng buffer chỉ trì hoãn thời điểm đầy nếu tốc độ tạo record liên tục cao hơn tốc độ gửi; cần xử lý nguyên nhân nghẽn.

Giá trị mặc định của các thuộc tính có thể thay đổi theo phiên bản Kafka client. Ví dụ thường gặp trong nhiều phiên bản là `batch.size` 16 KiB và `linger.ms` 0 ms, nhưng một số phiên bản mới đã điều chỉnh mặc định của `linger.ms`. Hãy xem cấu hình hiệu lực và tài liệu đúng phiên bản thư viện đang chạy trước khi dựa vào con số mặc định.

## 3. Vì sao batch được gom theo partition?

Kafka lưu log độc lập cho từng partition. Mỗi batch được gửi tới một partition cụ thể và broker ghi batch đó vào log của partition. Nếu producer gửi record có key, partitioner chọn partition theo key (với partitioner mặc định, cách tính cụ thể phụ thuộc cấu hình và phiên bản). Các record cùng key thường đi cùng partition, do đó có thể cùng được gom vào một batch.

Số partition ảnh hưởng trực tiếp tới khả năng gom batch. Nếu ứng dụng gửi cùng một lượng record nhưng phân tán đều trên rất nhiều partition, mỗi partition nhận ít record hơn trong một khoảng thời gian. Kết quả là nhiều batch nhỏ có thể được gửi đi. Điều này không có nghĩa nên giảm partition tùy tiện: partition còn quyết định khả năng song song, ordering và tải consumer. Hãy cân bằng số partition với throughput, số consumer và yêu cầu nghiệp vụ.

Với record không có key, partitioner có thể sử dụng cơ chế sticky partitioning để tạm thời tập trung record vào một partition, giúp batch hiệu quả hơn rồi chuyển sang partition khác. Cách phân phối cụ thể phụ thuộc Kafka client và partitioner đang dùng. Nếu ứng dụng tự viết partitioner, cần cân nhắc cả phân phối tải lẫn hiệu quả batching.

## 4. Compression và batching

Kafka nén dữ liệu ở cấp batch. Khi một batch có nhiều record tương tự nhau, thuật toán nén thường tận dụng được tính lặp tốt hơn so với các request chứa rất ít record. Có thể cấu hình `compression.type` như `none`, `gzip`, `snappy`, `lz4` hoặc `zstd`, tùy phiên bản client, broker và môi trường hỗ trợ.

Ví dụ lựa chọn `lz4`:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[compression.type]": lz4
```

Nén có thể giảm băng thông và dung lượng dữ liệu trên đĩa, nhưng tạo thêm chi phí CPU. `gzip` thường có tỷ lệ nén tốt nhưng tốn CPU hơn; `lz4` và `snappy` thường ưu tiên tốc độ; `zstd` có thể cân bằng tỷ lệ nén và tốc độ tùy mức cấu hình. Hãy đo trên dữ liệu thực tế của ứng dụng thay vì chọn chỉ dựa trên tên thuật toán.

Broker thường lưu batch theo định dạng nén được producer gửi, nên compression có thể giảm cả lưu lượng mạng và dung lượng log. Hiệu quả thực tế còn phụ thuộc dữ liệu, mức đầy batch, số partition và việc broker/consumer có phải chuyển đổi định dạng message hay không.

## 5. Cấu hình batching trong Spring Boot

Spring Boot ánh xạ một số thuộc tính producer thông dụng thành cấu hình Kafka client. Ví dụ sau đặt batch mục tiêu 32 KiB, chờ tối đa 10 ms để gom thêm record, dành 64 MiB buffer và dùng LZ4:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      batch-size: 32768
      buffer-memory: 67108864
      properties:
        "[linger.ms]": 10
        "[compression.type]": lz4
```

Trong cấu hình này:

- `batch-size` tương ứng `batch.size`, đơn vị byte.
- `linger.ms` cho producer thêm tối đa 10 ms để gom record.
- `buffer-memory` tương ứng `buffer.memory`, đơn vị byte.
- `compression.type` chỉ định thuật toán nén batch.
- `acks: all` yêu cầu broker xác nhận theo chính sách ISR của topic; đây là lựa chọn độ bền dữ liệu, không phải thuộc tính tạo batch.

Các giá trị trên chỉ là điểm bắt đầu để thử nghiệm. Với ứng dụng cần độ trễ rất thấp, `linger.ms` nhỏ có thể phù hợp hơn. Với luồng sự kiện có throughput cao, có thể thử batch lớn hơn và thời gian chờ dài hơn nếu ngân sách latency cho phép. Cần kiểm tra cả `delivery.timeout.ms`, `request.timeout.ms`, `max.block.ms` và giới hạn message ở broker khi điều chỉnh các giá trị này.

## 6. Cấu hình bằng Java và KafkaTemplate

Nếu tự tạo `ProducerFactory`, có thể truyền trực tiếp các thuộc tính của Kafka client:

```java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> producerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.BATCH_SIZE_CONFIG, 32 * 1024);
        props.put(ProducerConfig.LINGER_MS_CONFIG, 10);
        props.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 64L * 1024 * 1024);
        props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(
                props,
                new StringSerializer(),
                new JsonSerializer<>());
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> kafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

Ví dụ lược bớt import và cấu hình serializer phụ thuộc phiên bản Spring Kafka. Nếu dùng cấu hình tự động của Spring Boot, không cần tạo lại `ProducerFactory` chỉ để đổi `batch.size` hoặc `linger.ms`; có thể đặt các thuộc tính trong `application.yml` như phần trước.

`enable.idempotence=true` giúp producer hạn chế bản ghi trùng do retry trong phạm vi đảm bảo của Kafka producer. Nó không thay thế idempotency trong nghiệp vụ khi ứng dụng gửi lại cùng một sự kiện bằng một lần gọi mới, cũng không quyết định cách gom batch.

## 7. Gửi bất đồng bộ để producer có cơ hội gom batch

`KafkaTemplate.send()` trả về một future để ứng dụng theo dõi kết quả gửi. Trong Spring Kafka 3.x, kiểu trả về là `CompletableFuture<SendResult<K, V>>`:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .whenComplete((result, error) -> {
                    if (error != null) {
                        // Ghi nhận lỗi gửi và xử lý theo chính sách của ứng dụng.
                        log.error("Cannot publish order event", error);
                        return;
                    }

                    RecordMetadata metadata = result.getRecordMetadata();
                    log.debug("Published to partition {}, offset {}",
                            metadata.partition(), metadata.offset());
                });
    }
}
```

Producer có thể tiếp tục nhận record trong khi Sender thread gửi các batch ở nền. Tránh gọi `get()` ngay sau mỗi `send()` trong vòng lặp throughput cao nếu không cần kết quả đồng bộ; việc chờ từng record làm chậm tốc độ đưa dữ liệu vào accumulator và giảm cơ hội gom batch. Có thể giữ lại future và xử lý kết quả bất đồng bộ hoặc chờ theo nhóm ở ranh giới phù hợp.

Không gọi `flush()` sau mỗi record. `flush()` yêu cầu gửi các record đang chờ ngay lập tức, làm batch có thể nhỏ và giảm lợi ích của `linger.ms`. Chỉ flush khi có ranh giới nghiệp vụ thực sự cần đẩy dữ liệu đang đệm ra, ví dụ trước khi kết thúc một giai đoạn xử lý hoặc đóng ứng dụng theo cách được quản lý. `KafkaTemplate` thường không bật auto-flush mặc định; nếu bật `autoFlush`, hãy hiểu rằng mỗi lần gửi có thể bị flush và batching sẽ giảm.

Với phiên bản Spring Kafka cũ, API future có thể là `ListenableFuture` thay vì `CompletableFuture`. Hãy dùng API tương ứng với phiên bản thư viện của dự án.

## 8. Cân bằng throughput và latency

Batching là một bài toán cân bằng. Batch lớn hơn và `linger.ms` dài hơn có thể giảm số request và tăng hiệu quả nén, nhưng tăng thời gian record phải chờ trước khi được gửi. Cần chọn dựa trên mục tiêu cụ thể:

| Mục tiêu | Hướng thử nghiệm |
|---|---|
| Độ trễ thấp | Giảm `linger.ms`, giữ batch size hợp lý và tránh flush không cần thiết |
| Throughput cao | Thử tăng `batch.size`, `linger.ms` và compression; đo CPU, mạng và latency |
| Giảm băng thông | Bật compression và bảo đảm batch đủ lớn để thuật toán nén hiệu quả |
| Lưu lượng đến không đều | Thử `linger.ms` vừa phải, kiểm tra queue time và batch size ở cả giờ thấp điểm lẫn cao điểm |
| Nhiều partition | Đánh giá lượng record trên từng partition; batch nhỏ có thể do record bị phân tán |

Ví dụ, nếu ứng dụng chỉ phát một record mỗi giây cho một partition và `linger.ms` là 10 ms, producer không thể đợi đủ nhiều record trong 10 ms để tạo batch lớn. Tăng `batch.size` từ 16 KiB lên 64 KiB không tự tạo thêm dữ liệu; batch vẫn có thể chỉ chứa một record. Trong trường hợp này, tăng `linger.ms` chỉ hữu ích nếu chấp nhận thêm độ trễ để chờ record tiếp theo.

Ngược lại, nếu hàng nghìn record mỗi giây được phân phối trên một số partition nhỏ, batch có thể đầy rất nhanh. Khi đó, tăng `linger.ms` có thể ít cải thiện throughput nhưng vẫn làm tăng latency ở những thời điểm tải giảm. Hãy thử nhiều mức tải, không chỉ benchmark ở mức tải cao nhất.

## 9. Những timeout và giới hạn liên quan

Các thuộc tính sau thường bị nhầm với batching:

| Thuộc tính | Ý nghĩa |
|---|---|
| `max.block.ms` | Thời gian tối đa `send()` có thể chờ khi cần metadata hoặc buffer trống |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request gửi tới broker |
| `delivery.timeout.ms` | Tổng thời gian tối đa để một record được gửi thành công, tính cả các lần retry |
| `max.request.size` | Giới hạn kích thước request của producer |
| `acks` | Mức xác nhận mà producer yêu cầu từ broker |
| `retries` | Số lần producer thử lại khi gặp lỗi có thể retry; cần phối hợp với idempotence và delivery timeout |

`linger.ms` không phải timeout giao nhận. Khi batch đã được gửi, `request.timeout.ms` và `delivery.timeout.ms` mới chi phối thời gian chờ phản hồi và thử lại. Một cấu hình `delivery.timeout.ms` phải lớn hơn hoặc bằng tổng `request.timeout.ms` và `linger.ms` theo ràng buộc của Kafka client. Nếu điều chỉnh timeout, kiểm tra tính hợp lệ giữa các giá trị.

`max.request.size` không phải kích thước của một batch riêng lẻ. Một request có thể chứa batch từ nhiều partition; giới hạn request và giới hạn message/batch phía broker/topic cần tương thích với record lớn nhất mà ứng dụng gửi. Khi gặp lỗi record quá lớn, tăng `batch.size` không nhất thiết giải quyết được.

## 10. Đo hiệu quả batching

Không nên đánh giá batching chỉ bằng việc tăng `batch.size` hoặc `linger.ms`. Hãy đo các chỉ số producer dưới cùng một tải và cùng điều kiện mạng:

| Metric | Cách đọc |
|---|---|
| `batch-size-avg` / `batch-size-max` | Kích thước batch trung bình và lớn nhất theo byte |
| `records-per-request-avg` | Số record trung bình trong mỗi request |
| `compression-rate-avg` | Tỷ lệ nén trung bình của batch |
| `record-queue-time-avg` / `record-queue-time-max` | Thời gian record chờ trong producer trước khi gửi |
| `buffer-available-bytes` | Dung lượng buffer còn trống |
| `request-latency-avg` | Độ trễ request tới broker |
| `record-send-rate` / `record-error-rate` | Tốc độ gửi record và tỷ lệ lỗi |

Các metric Kafka producer thường được xuất qua JMX; tên metric và cách tích hợp với hệ thống monitoring phụ thuộc client và nền tảng quan sát. Theo dõi đồng thời throughput, p95/p99 latency, CPU, network throughput và lỗi gửi. Nếu batch size tăng nhưng CPU nén quá cao hoặc latency vượt SLA, cấu hình mới có thể không phù hợp.

Một quy trình thử nghiệm thực tế:

1. Ghi lại cấu hình hiện tại và đặt một tải thử đại diện cho production.
2. Đo throughput, latency, batch size, records per request, queue time và CPU.
3. Thay đổi từng nhóm cấu hình nhỏ, ví dụ `linger.ms` trước rồi mới tới `batch.size`.
4. Thử ở tải thấp, tải trung bình và tải đỉnh để xem độ trễ khi batch không đầy.
5. Kiểm tra buffer có thường xuyên cạn, có `TimeoutException`, retry hoặc record error hay không.
6. Chọn cấu hình đạt SLA latency và throughput với mức sử dụng CPU/bộ nhớ chấp nhận được.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `batch-size-avg` luôn rất nhỏ | Lưu lượng thấp, nhiều partition, `linger.ms` quá ngắn hoặc producer flush liên tục | Đo lượng record trên từng partition; thử tăng `linger.ms` vừa phải và bỏ flush không cần thiết |
| Latency tăng sau khi bật batching | `linger.ms` quá cao hoặc queue bị nghẽn | Giảm thời gian chờ, kiểm tra queue time và tốc độ broker |
| `send()` bị chặn rồi timeout | Buffer đầy, broker chậm hoặc metadata chưa sẵn sàng | Kiểm tra `buffer-available-bytes`, `max.block.ms`, broker và network; không chỉ tăng buffer |
| Producer dùng nhiều CPU | Compression tốn CPU hoặc serialize quá nặng | So sánh thuật toán nén, đo CPU và tối ưu serializer |
| Lỗi message/request quá lớn | Record lớn hoặc giới hạn producer/broker/topic không tương thích | Kiểm tra `max.request.size` và giới hạn message/batch ở broker/topic |
| Tăng batch size nhưng throughput không đổi | Batch không đầy, bottleneck nằm ở broker, network, serialization hoặc ứng dụng | Dựa trên metric để tìm nút thắt trước khi tiếp tục tăng kích thước |

## Checklist trước khi đưa vào production

- `batch.size` và `linger.ms` được chọn dựa trên throughput cùng ngân sách latency.
- Đã tính tới số partition và cách phân phối key khi đánh giá batch size.
- `buffer.memory` đủ cho lưu lượng dự kiến nhưng không gây áp lực bộ nhớ quá mức.
- Compression được benchmark trên dữ liệu thật và mức sử dụng CPU đã được kiểm tra.
- `max.request.size`, giới hạn message phía broker/topic và kích thước record tương thích.
- Timeout `max.block.ms`, `request.timeout.ms` và `delivery.timeout.ms` được cấu hình nhất quán.
- Ứng dụng xử lý kết quả gửi bất đồng bộ và không flush từng record nếu không cần thiết.
- Có metric để theo dõi batch size, queue time, buffer, throughput, latency và lỗi gửi.

Batching ở phía producer là cơ chế tối ưu đường truyền và khả năng xử lý của Kafka. Cấu hình hiệu quả phụ thuộc lượng record trên mỗi partition, kích thước record, độ trễ cho phép, compression và năng lực broker. Hãy thay đổi có kiểm soát và xác minh bằng metric ở tải đại diện để tìm được điểm cân bằng phù hợp.
