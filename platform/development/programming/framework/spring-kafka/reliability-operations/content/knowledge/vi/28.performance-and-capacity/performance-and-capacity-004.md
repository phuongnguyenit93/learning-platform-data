# Producer batching

Producer batching là cơ chế gom nhiều record Kafka thành một batch trước khi gửi chúng qua mạng tới broker. Trong ứng dụng Spring Kafka, `KafkaTemplate` cung cấp API gửi message, còn việc gom batch được thực hiện bởi Kafka Producer ở bên dưới. Vì vậy, hiệu quả batching phụ thuộc vào lưu lượng gửi, cách phân phối record tới partition, cấu hình producer và khả năng xử lý của broker.

Batching giúp giảm số request mạng, giảm chi phí xử lý trên mỗi record và thường cải thiện throughput. Khi batch có nhiều dữ liệu, compression cũng thường đạt hiệu quả tốt hơn. Đổi lại, producer có thể phải giữ record trong bộ đệm lâu hơn để chờ batch đầy, làm tăng latency. Mục tiêu vận hành là tìm điểm cân bằng giữa throughput, latency, bộ nhớ và tài nguyên CPU của producer lẫn broker.

## Producer batching hoạt động như thế nào?

Khi ứng dụng gọi `KafkaTemplate.send()`, Spring Kafka chuyển record tới Kafka Producer. Producer serialize key và value, xác định partition đích, rồi thêm record vào bộ đệm dành cho partition đó. Bộ đệm này được quản lý bởi `RecordAccumulator`.

Kafka Producer có một sender thread đọc các batch đã sẵn sàng và gửi chúng tới broker. Một batch thường được gửi khi đạt giới hạn kích thước `batch.size` hoặc khi thời gian chờ `linger.ms` hết. Áp lực bộ đệm và các điều kiện gửi khác cũng ảnh hưởng tới thời điểm gửi thực tế.

```text
Ứng dụng
   |
   | KafkaTemplate.send(record)
   v
Kafka Producer
   |
   | Serialize key/value và chọn partition
   v
RecordAccumulator
   |
   | Gom record vào batch riêng của từng partition
   v
Sender thread
   |
   | Batch đầy hoặc hết linger.ms
   v
Produce request --------------------> Kafka broker
   |
   | Kết quả gửi
   v
Callback / CompletableFuture
```

Việc gom batch diễn ra theo topic-partition. Các record thuộc hai partition khác nhau không được ghép vào cùng một batch, dù chúng được gửi từ cùng một ứng dụng hoặc cùng một topic. Một request mạng có thể mang nhiều batch cho nhiều partition, nhưng mỗi batch vẫn thuộc một partition cụ thể.

Ví dụ, nếu producer gửi liên tục record cho partition 0, batch của partition này có thể nhanh chóng đạt kích thước mục tiêu. Nếu record được phân tán tới 30 partition với lưu lượng thấp ở từng partition, mỗi batch có thể chứa ít record hơn và phải chờ `linger.ms` trước khi gửi. Vì vậy, tổng số record mỗi giây của ứng dụng chưa đủ để dự đoán kích thước batch; cần xem lưu lượng trên từng partition.

## Các cấu hình ảnh hưởng trực tiếp tới batching

### `batch.size`

`batch.size` đặt kích thước mục tiêu tối đa theo byte cho một batch của một partition. Khi batch đạt ngưỡng này, producer có thể gửi batch mà không cần đợi hết `linger.ms`.

- Giá trị nhỏ tạo batch nhỏ hơn, thường làm tăng số request và chi phí giao tiếp khi lưu lượng đủ lớn.
- Giá trị lớn cho phép gom nhiều dữ liệu hơn, có thể cải thiện throughput và compression.
- Batch lớn có thể cần nhiều bộ nhớ hơn, đặc biệt khi nhiều partition đồng thời có dữ liệu chờ gửi.

`batch.size` không phải giới hạn kích thước tuyệt đối cho một record đơn lẻ và cũng không phải giới hạn tổng kích thước của một request. Record lớn vẫn chịu các giới hạn kích thước message và request như `max.request.size` ở producer cùng cấu hình giới hạn message của broker/topic. Cần bảo đảm các giới hạn này tương thích khi hệ thống gửi record lớn.

### `linger.ms`

`linger.ms` là khoảng thời gian producer có thể chờ thêm record để lấp đầy batch trước khi gửi. Nếu batch đạt `batch.size` sớm hơn, producer có thể gửi ngay.

Tăng `linger.ms` thường có lợi khi lưu lượng trên mỗi partition chưa đủ cao để lấp đầy batch nhanh. Producer có thêm thời gian gom record, từ đó có thể giảm số request và tăng compression efficiency. Đổi lại, record có thể phải chờ lâu hơn trước khi được gửi, nhất là khi lưu lượng thấp.

Giảm `linger.ms` phù hợp khi ứng dụng ưu tiên latency thấp. Tuy nhiên, đặt giá trị quá thấp trong khi lưu lượng phân tán có thể khiến producer thường xuyên gửi các batch nhỏ. Giá trị mặc định có thể thay đổi theo phiên bản Kafka client; hãy kiểm tra phiên bản thực tế thay vì dựa vào một con số mặc định từ tài liệu của phiên bản khác.

### `buffer.memory`

`buffer.memory` xác định lượng bộ nhớ producer dành cho việc đệm record đang chờ gửi. Bộ nhớ này được dùng chung cho các partition của producer, không phải một vùng riêng cố định cho mỗi batch.

Khi tốc độ ứng dụng đưa record vào vượt quá tốc độ producer gửi dữ liệu đi, bộ đệm có thể đầy. Lúc đó lời gọi `send()` có thể phải chờ cấp phát bộ nhớ hoặc metadata, tối đa theo giới hạn `max.block.ms`, rồi phát sinh lỗi nếu không thể tiếp tục. Tăng `buffer.memory` có thể hấp thụ burst ngắn, nhưng không giải quyết được tình trạng producer liên tục gửi nhanh hơn năng lực broker hoặc mạng.

### `compression.type`

Compression được áp dụng trên batch. Batch có nhiều record thường tạo cơ hội nén tốt hơn so với nhiều batch rất nhỏ, đặc biệt khi các record có cấu trúc hoặc nội dung lặp lại.

Các codec thường gặp gồm `none`, `gzip`, `snappy`, `lz4` và `zstd`, tùy phiên bản Kafka client và môi trường triển khai. Mỗi codec có mức tiêu thụ CPU và tỷ lệ nén khác nhau. Chẳng hạn, LZ4 thường được cân nhắc khi cần tốc độ nén/giải nén cao; gzip hoặc zstd có thể phù hợp khi ưu tiên giảm băng thông hoặc dung lượng hơn và chấp nhận chi phí CPU tương ứng. Cần benchmark bằng dữ liệu gần với dữ liệu production.

### Các cấu hình liên quan khác

| Thuộc tính | Vai trò | Ảnh hưởng khi vận hành |
|---|---|---|
| `max.request.size` | Giới hạn kích thước request producer gửi | Cần phù hợp với kích thước record/batch và giới hạn broker/topic |
| `max.block.ms` | Giới hạn thời gian các thao tác gửi có thể chờ metadata hoặc bộ đệm | Hữu ích khi phát hiện producer bị chặn do thiếu bộ nhớ hoặc metadata |
| `acks` | Mức xác nhận producer yêu cầu từ broker | Ảnh hưởng độ bền dữ liệu và latency; không nên giảm chỉ để tăng batching |
| `enable.idempotence` | Hỗ trợ tránh ghi trùng do retry theo cơ chế producer idempotent | Có thể duy trì độ tin cậy khi producer retry; cần giữ các cấu hình tương thích |
| `max.in.flight.requests.per.connection` | Số request chưa được xác nhận tối đa trên một kết nối | Ảnh hưởng khả năng pipeline request; phải tương thích với idempotence và yêu cầu thứ tự |
| `delivery.timeout.ms` | Giới hạn tổng thời gian chờ gửi thành công, gồm retry | Cần tính đến khi đặt mục tiêu latency và timeout ở tầng ứng dụng |

Batching là tối ưu hiệu năng. Không nên đánh đổi các yêu cầu về xác nhận, thứ tự hoặc chống ghi trùng chỉ để tăng kích thước batch. Nếu producer cần idempotence, hãy giữ `enable.idempotence=true` và các giá trị liên quan tương thích với phiên bản Kafka client đang dùng.

## Cấu hình batching trong Spring Boot và Spring Kafka

Spring Boot ánh xạ các thuộc tính producer phổ biến thành cấu hình `spring.kafka.producer`. Các thuộc tính Kafka client chưa có trường chuyên biệt có thể đặt trong `spring.kafka.producer.properties`.

Ví dụ `application.yml`:

```yaml
spring:
  kafka:
    producer:
      acks: all
      batch-size: 32768
      buffer-memory: 67108864
      compression-type: lz4
      properties:
        "[linger.ms]": 5
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
```

Trong ví dụ này:

- `batch-size: 32768` đặt kích thước batch mục tiêu là 32 KiB.
- `linger.ms: 5` cho producer thêm tối đa khoảng chờ cấu hình để gom record khi batch chưa đầy.
- `buffer-memory: 67108864` dành khoảng 64 MiB cho bộ đệm producer.
- `compression-type: lz4` bật nén batch bằng LZ4.
- `acks: all` và `enable.idempotence: true` thể hiện một cấu hình chú trọng độ tin cậy; cần bảo đảm cấu hình broker và các thuộc tính liên quan đáp ứng yêu cầu tương ứng.

Đây là bộ giá trị minh họa để bắt đầu thử nghiệm, không phải cấu hình tối ưu cho mọi workload. Hãy đo trên môi trường có kích thước record, phân bố key, số partition và tốc độ gửi gần với production.

Có thể cấu hình tương đương trong `application.properties`:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.batch-size=32768
spring.kafka.producer.buffer-memory=67108864
spring.kafka.producer.compression-type=lz4
spring.kafka.producer.properties[linger.ms]=5
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
```

Khi ứng dụng tự tạo `ProducerFactory` hoặc `KafkaProducer` thay vì dùng cấu hình tự động của Spring Boot, cần bảo đảm các thuộc tính batching được truyền tới đúng producer đang được `KafkaTemplate` sử dụng. Việc thay đổi một file cấu hình không có tác dụng nếu bean producer thực tế ghi đè hoặc bỏ qua các thuộc tính đó.

## Gửi bất đồng bộ để batching có cơ hội phát huy

`KafkaTemplate.send()` thực hiện gửi bất đồng bộ và trả về kết quả tương lai. Ứng dụng có thể tiếp tục gửi các record tiếp theo trong khi producer đang gom batch hoặc chờ broker xác nhận. Đây là cách sử dụng phù hợp để Kafka Producer có đủ dữ liệu gom thành batch.

Ví dụ dưới đây dùng API `CompletableFuture` của Spring Kafka 3.x:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
    kafkaTemplate.send("orders", event.orderId(), event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.warn(
            "Kafka send failed: topic={}, errorType={}",
            "orders",
            exception.getClass().getSimpleName()
        );
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.debug(
        "Kafka send acknowledged: topic={}, partition={}, offset={}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
```

Trong ví dụ, callback chỉ ghi metadata kỹ thuật và loại exception, không ghi payload hoặc thông tin xác thực. Với phiên bản Spring Kafka cũ hơn, kiểu future trả về có thể khác; hãy dùng API tương ứng với phiên bản dự án.

Một số cách viết có thể vô tình làm mất lợi ích batching:

```java
// Không nên chờ từng record ngay sau khi gửi.
kafkaTemplate.send("orders", event).get();

// Không nên flush sau từng record.
kafkaTemplate.send("orders", event);
kafkaTemplate.flush();
```

Chờ kết quả ngay sau mỗi lần gửi khiến luồng gửi tuần tự phải đợi broker trước khi tiếp tục, làm giảm khả năng gom nhiều record. Gọi `flush()` sau mỗi record buộc producer đẩy dữ liệu đang đệm đi sớm, nên thường tạo batch nhỏ. Chỉ dùng `flush()` tại ranh giới nghiệp vụ hoặc vòng đời mà ứng dụng thực sự cần bảo đảm các record đã được đẩy khỏi bộ đệm; không biến nó thành thao tác mặc định sau mỗi message.

Gửi bất đồng bộ không có nghĩa là bỏ qua kết quả lỗi. Ứng dụng vẫn cần xử lý callback, retry theo chính sách phù hợp và theo dõi lỗi gửi. Nếu tạo quá nhiều tác vụ gửi đồng thời mà không có giới hạn, ứng dụng có thể gây áp lực lên bộ nhớ, thread pool hoặc broker. Hãy quản lý concurrency và backpressure ở tầng ứng dụng.

## Số partition và phân bố record ảnh hưởng tới batch

Vì batch được gom riêng theo partition, partitioner và key có ảnh hưởng trực tiếp tới hiệu quả batching.

- **Lưu lượng tập trung vào ít partition:** mỗi partition nhận nhiều record hơn, batch có thể đầy nhanh và đạt kích thước lớn.
- **Lưu lượng trải đều trên nhiều partition:** mỗi partition nhận ít record hơn trong cùng khoảng thời gian, batch có thể nhỏ và thường phải chờ `linger.ms`.
- **Key bị lệch:** một key nóng có thể dồn phần lớn record vào một partition, khiến partition đó trở thành nút thắt dù các partition khác còn rảnh.
- **Tăng số partition:** có thể tăng khả năng xử lý song song ở broker và consumer, nhưng cũng phân tán record của producer thành nhiều luồng batch riêng. Tăng partition không tự động làm batching hiệu quả hơn.

Không thay đổi key hoặc partition chỉ để làm batch lớn hơn nếu điều đó phá vỡ yêu cầu thứ tự theo entity, khả năng mở rộng consumer hoặc phân bố tải. Hãy xem xét cả throughput, tính đúng đắn của partitioning và khả năng xử lý của toàn pipeline.

## Đo hiệu quả batching

Không nên đánh giá batching chỉ bằng số record gửi thành công. Cần theo dõi cả chất lượng batch, thời gian chờ trong producer, latency đầu cuối và áp lực tài nguyên.

Một số producer metrics hữu ích qua JMX hoặc cơ chế thu thập metrics của Kafka client:

| Metric | Ý nghĩa khi phân tích |
|---|---|
| `batch-size-avg` | Kích thước batch trung bình; cho biết batch thực tế lớn đến đâu |
| `batch-size-max` | Kích thước batch lớn nhất quan sát được |
| `records-per-request-avg` | Số record trung bình trong một request; giúp đánh giá mức độ gom record |
| `compression-rate-avg` | Tỷ lệ nén quan sát được của batch |
| `record-queue-time-avg` | Thời gian record nằm trong producer trước khi gửi |
| `buffer-available-bytes` | Dung lượng bộ đệm producer còn khả dụng |
| `bufferpool-wait-time-total` | Tổng thời gian producer phải chờ buffer pool |
| `request-latency-avg` | Latency trung bình của request tới broker |

Tên metric và cách phơi bày có thể khác theo phiên bản Kafka client và hệ thống monitoring. Cần kiểm tra danh sách metric thực tế của client đang chạy. Ngoài producer metrics, hãy theo dõi throughput, p95/p99 latency của nghiệp vụ, CPU producer/broker, network throughput, tỷ lệ lỗi và tình trạng replica/ISR.

Một vài dấu hiệu thường gặp:

- `batch-size-avg` thấp và `records-per-request-avg` thấp: kiểm tra lưu lượng trên từng partition, cách phân phối key, `linger.ms` và việc ứng dụng có flush hoặc chờ sau từng lần gửi hay không.
- Batch thường xuyên gần ngưỡng `batch.size`, latency vẫn đạt mục tiêu: có thể thử tăng batch size để xem throughput hoặc compression có cải thiện không.
- `record-queue-time-avg` tăng: record đang chờ lâu trong producer; xem lại `linger.ms`, tình trạng broker, network và áp lực bộ đệm.
- `buffer-available-bytes` giảm liên tục hoặc thời gian chờ buffer tăng: producer có thể đang tạo record nhanh hơn khả năng gửi. Tăng buffer chỉ giúp hấp thụ burst; cần tìm nguyên nhân nghẽn nếu tình trạng kéo dài.
- Compression cải thiện nhưng CPU producer tăng mạnh: so sánh codec khác hoặc điều chỉnh kích thước batch dựa trên benchmark.

## Quy trình tinh chỉnh thực tế

Hãy tinh chỉnh từng nhóm thuộc tính trên một workload đại diện và giữ lại số liệu trước/sau để có thể so sánh.

1. **Thiết lập baseline:** ghi nhận throughput, p95/p99 latency, kích thước record, số partition, phân bố key, batch metrics, buffer wait, CPU và network.
2. **Kiểm tra đường gửi:** xác nhận ứng dụng không gọi `flush()` hoặc chờ kết quả từng record; kiểm tra producer thực tế nhận đúng cấu hình Spring Boot.
3. **Điều chỉnh `linger.ms`:** thử tăng từng bước nhỏ nếu batch còn nhỏ và hệ thống có dư địa latency. Dừng khi throughput không tăng đáng kể hoặc latency vượt mục tiêu.
4. **Điều chỉnh `batch.size`:** tăng khi batch thường xuyên chạm ngưỡng và có bằng chứng rằng batch lớn hơn đem lại lợi ích. Theo dõi bộ nhớ khi có nhiều partition hoạt động.
5. **Thử compression:** so sánh `none`, `lz4`, `snappy`, `zstd` hoặc codec được môi trường hỗ trợ bằng dữ liệu thực tế; đo CPU, băng thông và latency.
6. **Kiểm tra buffer và broker:** nếu producer bị chờ buffer, xác định broker, partition, network hoặc giới hạn downstream có đang tạo nút thắt hay không.
7. **Xác nhận độ tin cậy:** kiểm tra lại `acks`, idempotence, retry, timeout, thứ tự và hành vi khi broker lỗi; không chỉ dựa vào throughput trong bài benchmark thành công.

Benchmark nên chạy đủ lâu để vượt qua giai đoạn khởi động, có cả tải ổn định và burst, và dùng cùng cách đo latency từ ứng dụng tới khi nhận xác nhận. Chỉ thay đổi một nhóm thuộc tính mỗi lần giúp xác định thay đổi nào tạo ra kết quả. Sau khi chọn cấu hình, cần kiểm tra lại dưới tải gần production và trong tình huống broker chậm hoặc mất kết nối.

## Các lỗi cấu hình và vận hành thường gặp

**Đặt `batch.size` rất lớn để mong throughput luôn tăng.** Batch lớn chỉ có ích khi mỗi partition có đủ record để lấp đầy và producer có đủ bộ nhớ. Với lưu lượng thấp, batch vẫn có thể được gửi khi hết `linger.ms`; tăng kích thước mục tiêu không tự tạo thêm record.

**Tăng `linger.ms` mà không đo latency.** Producer có thể gom được nhiều record hơn nhưng thời gian chờ tăng, làm p99 latency vượt SLA. Hãy đặt giới hạn latency rõ ràng và kiểm tra cả tải thấp lẫn tải cao.

**Tăng `buffer.memory` để chữa nghẽn broker.** Bộ đệm lớn hơn có thể trì hoãn thời điểm ứng dụng bị backpressure, nhưng không làm broker xử lý nhanh hơn. Nếu tốc độ đầu vào liên tục vượt tốc độ đầu ra, bộ đệm cuối cùng vẫn đầy.

**Tăng partition chỉ để tạo thêm throughput.** Nhiều partition có thể giúp tăng song song, nhưng cũng làm batch bị phân tán và tăng chi phí quản lý. Cần tính đến consumer concurrency, thứ tự theo key, giới hạn broker và dung lượng lưu trữ.

**Gọi `flush()` hoặc chờ `.get()` sau từng record.** Cách này làm producer gửi sớm và giảm khả năng gom batch. Chỉ đồng bộ tại điểm nghiệp vụ thực sự cần kết quả ngay.

**Bỏ qua lỗi gửi vì API bất đồng bộ.** `send()` trả về trước khi broker xác nhận không đồng nghĩa record đã được ghi thành công. Phải xử lý future/callback, timeout và retry theo chính sách ứng dụng.

**Giảm yêu cầu xác nhận để làm benchmark đẹp hơn.** Cấu hình như `acks=0` có thể thay đổi latency và throughput nhưng làm thay đổi bảo đảm giao nhận. Benchmark phải giữ nguyên các yêu cầu độ tin cậy mà production cần.

## Nguyên tắc vận hành

Producer batching có hiệu quả khi record được gửi liên tục, phân bố hợp lý trên các partition và producer có đủ thời gian gom dữ liệu trước khi gửi. Hãy bắt đầu bằng cấu hình vừa phải, gửi bất đồng bộ, tránh flush từng record, rồi dùng metrics để điều chỉnh `batch.size`, `linger.ms`, `buffer.memory` và compression.

Khi triển khai production, luôn đánh giá batching cùng với latency đầu cuối, backpressure, phân bố partition, độ tin cậy của producer và năng lực broker. Một cấu hình tốt là cấu hình đạt mục tiêu throughput trong giới hạn latency và tài nguyên đã đặt ra, đồng thời giữ nguyên các bảo đảm giao nhận mà hệ thống yêu cầu.
