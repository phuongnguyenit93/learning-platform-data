# Buffer memory và batch memory

Kafka producer gửi record theo cơ chế bất đồng bộ. Khi ứng dụng gọi `KafkaTemplate.send()`, record được serialize, xác định partition rồi đưa vào bộ đệm của producer. Các record cùng partition được gom thành batch trước khi sender thread gửi request tới broker. Hai cấu hình quan trọng chi phối bộ nhớ và batching là **`buffer.memory`** và **`batch.size`**.

`buffer.memory` giới hạn tổng dung lượng bộ nhớ producer dùng để giữ các record đang chờ gửi. `batch.size` xác định kích thước mục tiêu của batch cho từng partition. Hai giá trị này có quan hệ trực tiếp: nhiều partition đang có dữ liệu có thể cần nhiều batch đồng thời, khiến buffer pool cạn dù từng batch chưa đầy.

## 1. Luồng dữ liệu trong Kafka producer

Khi ứng dụng gửi record, Kafka producer không gửi ngay từng record thành một request độc lập. Producer tích lũy record theo topic-partition trong `RecordAccumulator`, sau đó sender thread lấy các batch đã sẵn sàng để gửi.

```text
Application
    |
    | KafkaTemplate.send(record)
    v
Serialize key/value
    |
    v
Chọn partition
    |
    v
RecordAccumulator
    |
    +---- Topic A / Partition 0: [batch A0]
    +---- Topic A / Partition 1: [batch A1]
    +---- Topic B / Partition 0: [batch B0]
    |
    v
Sender thread lấy các batch đã sẵn sàng
    |
    v
Gom batch theo broker và gửi ProduceRequest
    |
    v
Kafka broker acknowledge
```

Producer cần bộ nhớ để giữ record trước khi gửi, giữ batch đang được xây dựng và quản lý các request đang chờ phản hồi. Batching giúp giảm số request, tận dụng network tốt hơn và thường cải thiện hiệu quả nén.

## 2. buffer.memory là gì?

`buffer.memory` là tổng dung lượng bộ nhớ mà producer có thể sử dụng để buffer record đang chờ gửi tới broker. Kafka producer dùng một buffer pool để cấp phát bộ nhớ cho các batch trong `RecordAccumulator`.

Ví dụ cấu hình:

```properties
buffer.memory=67108864
```

Giá trị trên tương đương 64 MiB. Kafka producer mặc định thường dùng 32 MiB (`33554432` bytes); hãy kiểm tra default theo phiên bản Kafka client mà ứng dụng đang chạy.

Khi producer gửi record nhanh hơn tốc độ broker có thể nhận và xác nhận, các batch tích lũy trong buffer pool. Nếu không còn đủ bộ nhớ để cấp phát batch mới, thread gọi `send()` có thể phải chờ. Nếu chờ quá `max.block.ms`, thao tác gửi có thể thất bại với timeout trước khi trả về future.

`buffer.memory` là ngân sách cho record accumulator, không phải giới hạn tổng heap của JVM. Producer còn dùng bộ nhớ cho object, metadata, compression, request đang in-flight, callback và các cấu trúc nội bộ khác. Vì vậy không nên đặt `buffer.memory` bằng toàn bộ heap được cấp cho ứng dụng.

## 3. batch.size là gì?

`batch.size` là kích thước mục tiêu của batch theo từng partition, tính bằng byte. Producer cố gắng gom nhiều record cùng partition vào một batch cho tới khi batch đầy hoặc tới thời điểm gửi theo `linger.ms`.

Ví dụ:

```properties
batch.size=32768
```

Giá trị 32 KiB cho phép producer gom các record cùng partition vào batch có kích thước mục tiêu 32 KiB. Kafka producer mặc định thường dùng 16 KiB (`16384` bytes), nhưng nên kiểm tra theo Kafka client version.

`batch.size` không phải kích thước tối đa của toàn bộ request tới broker. Một request có thể chứa nhiều batch thuộc nhiều partition. Một record lớn hơn `batch.size` có thể cần một batch riêng lớn hơn; nó không được ghép cùng các record khác theo cách batching thông thường. Kích thước record/request vẫn chịu giới hạn như `max.request.size` và giới hạn message/batch phía broker.

## 4. Phân biệt buffer.memory và batch.size

| Thuộc tính | `buffer.memory` | `batch.size` |
| --- | --- | --- |
| Phạm vi | Tổng ngân sách buffer của producer | Kích thước mục tiêu cho batch từng partition |
| Đơn vị | Byte | Byte |
| Ảnh hưởng | Quyết định lượng record có thể chờ trong producer | Quyết định mức gom record trong mỗi batch |
| Khi quá nhỏ | Buffer pool nhanh cạn, `send()` phải chờ | Batch đầy nhanh, nhiều request nhỏ hơn |
| Khi quá lớn | Tăng memory footprint và chỉ hấp thụ burst lâu hơn | Có thể tăng hiệu quả batching nhưng dùng bộ nhớ kém hiệu quả khi traffic thấp |

Có thể hình dung `buffer.memory` là ngân sách chung, còn `batch.size` là kích thước mục tiêu của từng phần ngân sách được cấp cho partition đang có dữ liệu.

## 5. BufferPool và RecordAccumulator

Trong Kafka producer, `RecordAccumulator` quản lý các batch chờ gửi theo `TopicPartition`. Khi có record mới, producer tìm batch hiện tại của partition đó để nối thêm record. Nếu không còn chỗ, producer cần cấp phát batch mới từ `BufferPool`.

`BufferPool` quản lý các buffer có thể tái sử dụng. Khi sender thread gửi batch và bộ nhớ batch được giải phóng, vùng nhớ có thể quay lại pool để dùng cho batch khác. Nhờ đó producer giảm số lần cấp phát object/buffer mới trong luồng gửi.

Một partition đang có traffic thường cần ít nhất một batch đang mở. Nếu nhiều partition đồng thời nhận record, producer có thể cần nhiều batch cùng lúc. Khi batch cũ đã đầy nhưng chưa được gửi/giải phóng, partition có thể cần thêm buffer cho batch tiếp theo.

Vì vậy, không thể chỉ nhìn số record trung bình hoặc `batch.size` để kết luận `buffer.memory` đủ. Cần xem số partition hoạt động đồng thời, kích thước record, tốc độ gửi, thời gian chờ broker và số batch đang chờ.

## 6. Mối quan hệ giữa số partition và bộ nhớ

Batch được tạo theo partition. Một producer gửi tới nhiều partition có thể phải giữ nhiều batch riêng, kể cả khi mỗi partition chỉ có vài record.

Ví dụ minh họa với `batch.size=32 KiB`:

| Partition đang có traffic | Bộ nhớ mục tiêu nếu mỗi partition có một batch 32 KiB |
| ---: | ---: |
| 10 | Khoảng 320 KiB |
| 100 | Khoảng 3,200 KiB (xấp xỉ 3.125 MiB) |
| 500 | Khoảng 16,000 KiB (xấp xỉ 15.625 MiB) |
| 1,000 | Khoảng 32,000 KiB (xấp xỉ 31.25 MiB) |

Đây chỉ là ước lượng để hiểu fan-out theo partition, không phải công thức cấp phát cố định. Batch được cấp phát theo nhu cầu; một partition có thể có nhiều batch chờ, record lớn có thể cần buffer lớn hơn, và memory còn chịu ảnh hưởng của compression, in-flight requests cùng overhead khác.

Một producer phục vụ hàng trăm topic-partition có thể cạn buffer dù tổng throughput không quá cao, vì record phân tán khiến nhiều batch nhỏ cùng tồn tại. Khi đó tăng `batch.size` có thể làm tăng lượng bộ nhớ giữ cho các partition đang hoạt động nhưng chưa chắc cải thiện hiệu suất nếu traffic mỗi partition thấp.

## 7. linger.ms ảnh hưởng đến batch như thế nào?

`linger.ms` là khoảng thời gian producer có thể chờ thêm record để batch đầy hơn trước khi gửi. Batch cũng có thể được gửi sớm khi đã đầy hoặc khi producer cần giải phóng tài nguyên theo cơ chế nội bộ.

Ví dụ:

```properties
batch.size=32768
linger.ms=5
```

Producer có thể chờ tối đa khoảng 5 ms để gom thêm record cùng partition. Nếu batch đầy sớm, nó có thể được gửi trước khi hết thời gian linger.

| Cấu hình | Tác động thường gặp |
| --- | --- |
| `linger.ms=0` | Giảm thời gian chờ batching, nhưng có thể tạo nhiều batch nhỏ khi traffic thấp |
| `linger.ms` nhỏ | Có thêm cơ hội gom record, thường tăng batch fullness với chi phí latency nhỏ |
| `linger.ms` lớn | Có thể tăng throughput và hiệu quả nén, nhưng tăng thời gian chờ trước khi gửi |

Default của `linger.ms` đã thay đổi giữa các phiên bản Kafka client; Kafka client 4.x có default khác các dòng cũ. Không sao chép một giá trị mặc định từ tài liệu phiên bản khác mà không kiểm tra dependency thực tế.

## 8. Compression và batch memory

Kafka nén theo batch. Khi một batch chứa nhiều record tương tự nhau, thuật toán nén thường đạt hiệu quả tốt hơn so với nén từng record riêng lẻ.

Ví dụ:

```properties
batch.size=65536
linger.ms=5
compression.type=zstd
```

`compression.type` có thể là `none`, `gzip`, `snappy`, `lz4` hoặc `zstd` tùy phiên bản client/broker hỗ trợ. Compression giúp giảm byte truyền qua mạng và dung lượng lưu trữ, đổi lại tiêu tốn CPU và thêm chi phí bộ nhớ để xử lý dữ liệu.

`batch.size` được dùng để quyết định mức gom dữ liệu; không nên giả định batch luôn chiếm đúng kích thước sau nén. Việc nén xảy ra trên batch và kích thước dữ liệu sau nén có thể nhỏ hơn đáng kể so với dữ liệu ban đầu.

Khi tăng `batch.size` để cải thiện compression ratio, hãy đo CPU, latency, batch fullness và network throughput. Nếu CPU đã bão hòa, tăng compression level hoặc chọn thuật toán nặng hơn có thể làm throughput giảm.

## 9. Điều gì xảy ra khi buffer.memory cạn?

Khi ứng dụng gọi `send()`, producer có thể cần chờ metadata hoặc chờ buffer pool cấp phát vùng nhớ cho batch. `max.block.ms` giới hạn thời gian chờ đồng bộ cho một số thao tác như lấy metadata và cấp phát buffer.

Luồng khi buffer pool cạn:

```text
Application gọi send()
        |
        v
Producer cần buffer cho batch
        |
        v
BufferPool không còn đủ memory
        |
        v
Thread gọi send() chờ buffer được giải phóng
        |
        +---- Có buffer trước max.block.ms ---> Tiếp tục gửi
        |
        +---- Hết max.block.ms ---------------> TimeoutException
```

Điểm cần nhớ: `KafkaTemplate.send()` thường trả về future cho kết quả gửi bất đồng bộ, nhưng bản thân lời gọi `send()` vẫn có thể block trước khi trả về nếu cần chờ metadata hoặc buffer. `max.block.ms` không phải thời gian chờ broker acknowledge.

Nếu buffer thường xuyên cạn, tăng `buffer.memory` có thể hấp thụ burst lâu hơn. Nhưng nếu producer liên tục tạo dữ liệu nhanh hơn broker có thể nhận, buffer lớn hơn chỉ trì hoãn thời điểm backpressure xuất hiện.

## 10. Phân biệt max.block.ms, request.timeout.ms và delivery.timeout.ms

Ba timeout này giải quyết các giai đoạn khác nhau:

| Thuộc tính | Kiểm soát | Khi hết hạn |
| --- | --- | --- |
| `max.block.ms` | Thời gian `send()` có thể block để chờ metadata hoặc buffer allocation | Lời gọi `send()` có thể ném timeout trước khi trả về future |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request tới broker | Request có thể được retry nếu lỗi có thể retry |
| `delivery.timeout.ms` | Tổng thời gian tối đa để producer báo kết quả gửi sau khi record được chấp nhận vào luồng gửi | Future/callback kết thúc với lỗi nếu chưa gửi thành công |

`delivery.timeout.ms` bao gồm thời gian record chờ trước khi gửi, thời gian chờ broker phản hồi và các lần retry. Giá trị này cần lớn hơn hoặc bằng `request.timeout.ms + linger.ms` theo ràng buộc Kafka producer.

Không tăng `max.block.ms` để xử lý broker phản hồi chậm; hãy điều tra buffer pressure hoặc metadata availability. Không tăng `delivery.timeout.ms` để chữa buffer pool cạn nếu lời gọi `send()` đang timeout trước khi future được tạo.

## 11. max.request.size và record lớn

`batch.size` không phải giới hạn duy nhất cho kích thước dữ liệu. `max.request.size` giới hạn kích thước request mà producer có thể gửi và cũng ảnh hưởng giới hạn record batch lớn nhất. Broker có giới hạn tương ứng như `message.max.bytes`; replica fetch cũng cần đủ khả năng lấy batch.

Khi gửi payload lớn:

- Kiểm tra kích thước sau serialization, không chỉ kích thước object Java.
- Kiểm tra `max.request.size` phía producer.
- Kiểm tra `message.max.bytes` hoặc giới hạn topic/broker tương ứng.
- Kiểm tra `replica.fetch.max.bytes` và cấu hình fetch liên quan.
- Cân nhắc compression, chia nhỏ event hoặc lưu object lớn ở object storage rồi gửi reference.

Tăng `buffer.memory` không cho phép gửi record vượt giới hạn request/broker. Nếu một record quá lớn, producer hoặc broker vẫn có thể từ chối dù buffer còn nhiều bộ nhớ.

## 12. Cấu hình buffer.memory và batch.size trong Spring Boot

Spring Boot cung cấp property riêng cho `batch-size` và `buffer-memory` trong `spring.kafka.producer`. Các thuộc tính Kafka khác có thể đặt trong `properties`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      batch-size: 32768
      buffer-memory: 67108864
      compression-type: zstd
      properties:
        "[linger.ms]": 5
        "[max.block.ms]": 10000
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 120000
        "[max.request.size]": 1048576
```

Trong ví dụ:

- Mỗi batch có kích thước mục tiêu 32 KiB.
- Producer buffer pool có ngân sách 64 MiB.
- Producer chờ tối đa 5 ms để gom thêm record.
- Compression dùng Zstandard nếu Kafka client và broker hỗ trợ.
- Lời gọi gửi có giới hạn chờ metadata/buffer 10 giây.
- Request timeout là 30 giây và delivery timeout là 120 giây.
- Request size tối đa cấu hình ở mức 1 MiB.

Các giá trị chỉ là điểm bắt đầu minh họa, không phải cấu hình tối ưu chung. `delivery.timeout.ms` cần thỏa quan hệ với `request.timeout.ms + linger.ms`; hãy kiểm tra thêm retry, broker limits và yêu cầu latency của hệ thống.

## 13. Cấu hình bằng ProducerFactory trong Java

Khi tự tạo producer factory, có thể đặt các cấu hình tương ứng bằng `ProducerConfig`:

```java
@Bean
public ProducerFactory<String, String> producerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

    props.put(ProducerConfig.BATCH_SIZE_CONFIG, 32 * 1024);
    props.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 64L * 1024 * 1024);
    props.put(ProducerConfig.LINGER_MS_CONFIG, 5);
    props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "zstd");
    props.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, 10_000);
    props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
    props.put(ProducerConfig.MAX_REQUEST_SIZE_CONFIG, 1024 * 1024);

    return new DefaultKafkaProducerFactory<>(props);
}
```

Ví dụ minh họa các cấu hình producer; cần bổ sung security, idempotence, `acks`, retries và các property theo môi trường. Nếu dùng Spring Boot auto-configuration, ưu tiên cấu hình qua `application.yml` thay vì tự tạo factory chỉ để thay đổi hai giá trị bộ nhớ.

## 14. Ước lượng buffer.memory ban đầu

Không có một công thức duy nhất cho mọi workload, nhưng có thể dùng cách ước lượng để chọn giá trị thử nghiệm:

1. Xác định số partition tối đa một producer có thể gửi đồng thời.
2. Ước lượng số batch đang mở/chờ trên mỗi partition trong giờ cao điểm.
3. Nhân số batch đồng thời với kích thước batch mục tiêu.
4. Cộng headroom cho burst, record lớn và dao động tốc độ broker.
5. Đảm bảo phần memory còn lại đủ cho JVM, serializer, compression và các thành phần khác.

Ví dụ producer thường xuyên có 200 partition hoạt động, giả sử trung bình có một batch 32 KiB đang mở trên mỗi partition:

\[
200 \times 32\,\text{KiB} = 6.25\,\text{MiB}
\]

Đây chỉ là dung lượng cho một batch mục tiêu mỗi partition. Nếu một số partition có nhiều batch chờ, traffic burst hoặc record lớn, nhu cầu thực tế cao hơn. Không nên lấy kết quả này làm giá trị cấu hình cuối cùng mà không đo buffer pool dưới tải.

## 15. Cách chọn batch.size

Chọn `batch.size` theo kích thước record và tốc độ record trên từng partition:

| Đặc điểm workload | Hướng thử nghiệm |
| --- | --- |
| Record nhỏ, traffic cao trên ít partition | Tăng batch size vừa phải để gom được nhiều record |
| Record nhỏ, traffic phân tán trên nhiều partition | Đo memory footprint; batch quá lớn có thể để nhiều vùng buffer chưa đầy |
| Record lớn | Đặt batch size phù hợp kích thước record; kiểm tra `max.request.size` và broker limits |
| Ưu tiên latency thấp | Batch nhỏ hơn và linger thấp, sau đó đo request rate |
| Ưu tiên throughput | Thử batch lớn hơn, linger phù hợp và compression |

Batch size lớn không tự động tăng throughput. Nếu partition traffic thấp, producer có thể gửi batch chưa đầy khi hết linger. Nếu broker/network là bottleneck, batch lớn có thể giúp giảm request overhead nhưng không làm tăng năng lực xử lý vô hạn.

## 16. Dấu hiệu buffer pressure và metrics

Kafka producer cung cấp metrics để quan sát buffer pool và batching. Các metric hữu ích gồm:

| Metric | Ý nghĩa | Dấu hiệu cần chú ý |
| --- | --- | --- |
| `buffer-available-bytes` | Bộ nhớ buffer pool còn khả dụng | Thấp kéo dài hoặc thường xuyên về gần 0 |
| `buffer-total-bytes` | Tổng dung lượng buffer pool | Đối chiếu với `buffer.memory` |
| `waiting-threads` | Số thread đang chờ buffer allocation | Lớn hơn 0 kéo dài là dấu hiệu producer bị backpressure |
| `bufferpool-wait-time` | Tổng thời gian chờ buffer pool | Tăng nhanh khi producer bị nghẽn |
| `bufferpool-wait-ratio` | Tỷ lệ thời gian chờ buffer | Tăng cho thấy ứng dụng mất thời gian chờ bộ nhớ |
| `batch-size-avg` | Kích thước batch trung bình | Quá thấp có thể cho thấy batching chưa hiệu quả |
| `records-per-request-avg` | Số record trung bình mỗi request | Thấp có thể làm tăng request overhead |
| `compression-rate-avg` | Tỷ lệ nén trung bình | Đánh giá hiệu quả compression |
| `record-queue-time-avg` | Thời gian record nằm trong producer queue | Tăng có thể phản ánh linger hoặc broker chậm |
| `request-latency-avg` | Độ trễ request trung bình | Tăng có thể chỉ ra broker/network bottleneck |

Tên metric và cách export phụ thuộc Kafka client/Micrometer integration. Hãy kiểm tra metric thực tế được expose trong phiên bản đang chạy.

## 17. Tuning theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Hướng điều tra/thử nghiệm |
| --- | --- | --- |
| `buffer-available-bytes` gần 0, `waiting-threads` tăng | Producer tạo dữ liệu nhanh hơn tốc độ gửi hoặc broker chậm | Kiểm tra broker/network, tăng buffer có giới hạn, điều tiết upstream |
| `batch-size-avg` thấp, request rate cao | Batch chưa gom đủ record | Thử tăng `linger.ms`, xem traffic theo partition và batch size |
| Batch nhỏ dù traffic cao toàn topic | Traffic phân tán trên quá nhiều partition | Đo throughput từng partition; kiểm tra key distribution và partition count |
| Queue time cao, broker latency cao | Broker hoặc network là bottleneck | Kiểm tra broker load, request latency, throttling và replication |
| Heap tăng dù buffer.memory ổn định | Object payload, serializer, callback hoặc in-flight memory | Profile heap và allocation; không chỉ tăng buffer pool |
| Record lớn bị từ chối | Vượt `max.request.size` hoặc broker limit | Kiểm tra kích thước sau serialization và giới hạn hai phía |
| CPU cao khi compression bật | Thuật toán/level nén tốn CPU | Benchmark `lz4`, `snappy`, `zstd`, `gzip` theo workload |

Không thay đồng thời `buffer.memory`, `batch.size`, `linger.ms` và compression rồi kết luận một cấu hình tốt hơn. Thay từng nhóm biến và giữ workload, partition count, record size tương đương để xác định nguyên nhân.

## 18. Kiểm thử tải và benchmark

Để tuning buffer và batch memory, cần workload gần thực tế:

- Kích thước payload đại diện, gồm record nhỏ, trung bình và lớn.
- Số partition và phân phối key giống production.
- Tốc độ producer theo giờ cao điểm và burst.
- Broker/network có cấu hình tương đương mục tiêu.
- Compression và acknowledgement giống cấu hình dự kiến triển khai.
- Consumer/broker load đủ để tạo tình huống sender không thể gửi tức thời.

Đo ít nhất:

1. Producer records/sec và bytes/sec.
2. p50/p95/p99 send latency và record queue time.
3. Batch size trung bình và records/request.
4. Buffer available bytes, wait ratio và waiting threads.
5. CPU, heap, GC và network throughput.
6. Error/timeout rate khi tăng tải vượt năng lực broker.

Chạy baseline trước, thay một cấu hình, lặp lại nhiều lần và so sánh kết quả. Tăng `buffer.memory` có thể giúp hấp thụ burst nhưng không nên xem đó là cải thiện throughput nếu latency và queue time tiếp tục tăng.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `send()` block lâu | Buffer pool cạn hoặc metadata chưa sẵn sàng | Quan sát `waiting-threads`, `buffer-available-bytes`, metadata/network |
| Timeout trước khi nhận future | Chờ buffer/metadata vượt `max.block.ms` | Phân biệt với broker acknowledgement timeout; tìm nguyên nhân buffer pressure |
| Future send thất bại sau khi trả về | Delivery hết hạn, request lỗi hoặc retry không thành công | Kiểm tra `delivery.timeout.ms`, `request.timeout.ms`, retries và broker logs |
| Tăng buffer.memory nhưng nghẽn vẫn tiếp diễn | Producer throughput dài hạn cao hơn broker capacity | Điều tiết producer hoặc tăng năng lực broker/partition phù hợp |
| Tăng batch.size nhưng heap tăng mạnh | Nhiều partition cùng giữ batch lớn | Đo active partition và memory pool; cân nhắc giảm batch size |
| Batch fullness thấp | Traffic phân tán hoặc linger quá thấp | Thử linger phù hợp và xem throughput theo partition |
| Request rate cao | Quá nhiều batch nhỏ | Điều chỉnh batch/linger và đánh giá key distribution |
| Compression không cải thiện throughput | CPU nén trở thành bottleneck hoặc payload khó nén | Benchmark thuật toán và CPU cost |
| Record lớn bị broker từ chối | Vượt request/message limit | Đồng bộ giới hạn producer, broker và replica fetch |

## 20. Checklist cấu hình production

- [ ] `buffer.memory` phù hợp heap budget và burst traffic.
- [ ] `batch.size` được chọn theo record size và số partition hoạt động.
- [ ] `linger.ms` cân bằng latency với batching.
- [ ] Compression được benchmark về CPU, network và batch size.
- [ ] `max.block.ms` phù hợp thời gian chờ metadata/buffer cho phép.
- [ ] `request.timeout.ms` và `delivery.timeout.ms` được cấu hình nhất quán.
- [ ] `max.request.size` tương thích với giới hạn broker/topic.
- [ ] Có metrics buffer pool, batch fullness, queue time và request latency.
- [ ] Có load test với partition/key distribution đại diện.
- [ ] Có giới hạn backpressure ở upstream khi broker không theo kịp.
- [ ] Không xem `buffer.memory` là giới hạn tổng heap của JVM.

## 21. Kết luận

`buffer.memory` và `batch.size` giải quyết hai phạm vi khác nhau trong Kafka producer. `buffer.memory` là ngân sách chung cho record đang chờ gửi; `batch.size` là kích thước mục tiêu của batch theo từng partition. Số partition hoạt động, tốc độ record, `linger.ms`, compression và tốc độ broker cùng quyết định mức sử dụng bộ nhớ thực tế.

Khi buffer pool cạn, lời gọi `send()` có thể chờ đến `max.block.ms`; đây là hiện tượng khác với timeout chờ broker phản hồi hoặc hết `delivery.timeout.ms`. Hãy đo `buffer-available-bytes`, `waiting-threads`, batch size, queue time và request latency trước khi tuning. Tăng buffer chỉ hấp thụ burst lâu hơn; muốn cải thiện throughput bền vững, cần cân bằng batch, linger, compression, partitioning và năng lực broker.

## Tài liệu tham khảo

- [Apache Kafka — Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — KafkaProducer API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Apache Kafka — Producer Metrics](https://kafka.apache.org/documentation/#producer_monitoring)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
