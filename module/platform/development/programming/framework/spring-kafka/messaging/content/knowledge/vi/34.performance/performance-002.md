# Batch size và linger.ms

Kafka producer không nhất thiết gửi từng record ngay khi ứng dụng gọi `KafkaTemplate.send()`. Producer có thể gom nhiều record vào một batch rồi gửi chúng trong cùng request. Cơ chế batching giúp giảm số request, tận dụng network tốt hơn và thường cải thiện throughput. Hai cấu hình ảnh hưởng trực tiếp đến việc gom batch là `batch.size` và `linger.ms`.

`batch.size` xác định dung lượng batch mục tiêu cho mỗi partition. `linger.ms` cho producer thêm một khoảng thời gian ngắn để chờ record tiếp theo đến, nhờ đó batch có cơ hội đầy hơn trước khi gửi. Tăng hai giá trị này có thể tăng throughput và hiệu quả nén, nhưng cũng có thể làm tăng độ trễ và mức sử dụng bộ nhớ. Cần điều chỉnh dựa trên kích thước record, lưu lượng thực tế và yêu cầu latency của ứng dụng.

## 1. Producer batching hoạt động như thế nào?

Khi ứng dụng gọi `KafkaTemplate.send(topic, key, value)`, Spring Kafka chuyển lời gọi tới Kafka producer. Producer serialize key/value, xác định partition đích rồi đưa record vào bộ đệm dành cho partition đó. Nhiều record cùng partition có thể được gom thành một batch trước khi gửi broker.

```text
KafkaTemplate.send(record A, key -> partition 0) --+
KafkaTemplate.send(record B, key -> partition 0) --+--> Batch partition 0 --+
KafkaTemplate.send(record C, key -> partition 1) ------> Batch partition 1 --+--> Produce requests
KafkaTemplate.send(record D, key -> partition 0) --+                         |
                                                                           Kafka broker
```

Batch được hình thành riêng cho từng partition. Record gửi đến partition 0 không lấp đầy batch của partition 1. Vì vậy, cùng một lưu lượng tổng thể nhưng phân tán trên nhiều partition có thể tạo ra nhiều batch nhỏ hơn so với lưu lượng tập trung trên ít partition.

Producer gửi batch khi batch đạt ngưỡng dung lượng, khi thời gian chờ `linger.ms` hết, hoặc khi có điều kiện khác buộc producer gửi dữ liệu đang chờ, chẳng hạn `flush()` hay buffer cần được giải phóng. `linger.ms` là thời gian chờ tối đa bổ sung để gom thêm record, không phải cam kết mọi batch đều đợi đủ chính xác số mili giây đó.

## 2. batch.size: dung lượng batch cho mỗi partition

`batch.size` là cấu hình producer tính bằng byte, xác định dung lượng batch mục tiêu cho mỗi partition. Khi batch gần đầy, record mới có thể được đưa vào batch tiếp theo và batch hiện tại được gửi.

Ví dụ:

```properties
batch.size=65536
```

Giá trị trên tương đương 64 KiB cho batch của mỗi partition. Nó không có nghĩa producer chỉ được dùng tổng cộng 64 KiB cho tất cả partition, cũng không phải giới hạn kích thước tối đa của một record đơn lẻ.

Nếu batch quá nhỏ:

- Batch dễ được gửi với ít record.
- Số request có thể tăng và overhead network/protocol cao hơn.
- Hiệu quả nén theo batch có thể thấp.

Nếu batch quá lớn:

- Có thể tăng bộ nhớ cần cho các partition đang hoạt động.
- Với lưu lượng thấp, batch vẫn có thể được gửi khi `linger.ms` hết mà chưa đầy.
- Có thể làm tăng thời gian chờ hoặc bộ nhớ mà không cải thiện throughput nếu producer không có đủ record.

`batch.size` không thay thế `buffer.memory`. `buffer.memory` là ngân sách bộ nhớ producer dành cho các record đang chờ gửi trên toàn producer; `batch.size` là dung lượng batch theo partition. Khi có nhiều partition hoạt động đồng thời, producer có thể cần nhiều batch cùng tồn tại trong buffer.

## 3. linger.ms: chờ thêm để gom record

`linger.ms` xác định thời gian producer có thể chờ thêm để gom record vào batch trước khi gửi batch chưa đầy. Ví dụ:

```properties
linger.ms=5
```

Producer có thể chờ tối đa khoảng 5 ms để có thêm record cho batch. Nếu batch đầy trước thời điểm đó, producer gửi sớm mà không cần chờ hết 5 ms. Nếu không có record mới, batch được gửi khi thời gian chờ hết.

| Giá trị `linger.ms` | Tác động thường thấy |
| --- | --- |
| 0 ms | Ưu tiên gửi sớm; batch có thể nhỏ khi lưu lượng thấp |
| Vài ms | Có thêm cơ hội gom record, thường là điểm bắt đầu để thử nghiệm |
| Cao hơn | Có thể tăng batch size và compression ratio, nhưng tăng thời gian chờ của record trong điều kiện lưu lượng thấp |

Không nên hiểu `linger.ms` là độ trễ cố định cộng vào mọi record. Khi lưu lượng cao, batch có thể đầy rất nhanh và được gửi trước khi linger hết. Khi lưu lượng thấp, record có thể chờ gần hết thời gian linger mới được gửi. Độ trễ end-to-end còn phụ thuộc serialize, buffer queue, network, broker acknowledgment và consumer.

Giá trị mặc định phụ thuộc phiên bản `kafka-clients`. Kafka 4.0 thay đổi mặc định `linger.ms` lên 5 ms; các dòng client cũ thường dùng 0 ms. Hãy kiểm tra phiên bản client do Spring Boot/Spring Kafka quản lý thay vì dựa vào mặc định của một ví dụ khác.

## 4. batch.size và linger.ms phối hợp với nhau

Hai cấu hình giải quyết hai điều kiện khác nhau:

- `batch.size` đặt dung lượng batch theo partition.
- `linger.ms` cho batch thêm thời gian để nhận record mới.

Ví dụ, giả sử batch có dung lượng 64 KiB và producer đang nhận record trung bình 1 KiB:

| Tình huống | Kết quả có thể xảy ra |
| --- | --- |
| Lưu lượng cao, nhiều record cùng partition | Batch có thể đạt 64 KiB trước khi hết linger và được gửi sớm |
| Lưu lượng thấp, chỉ có vài record | Batch chưa đầy nhưng được gửi khi hết linger |
| Nhiều partition nhận record rải rác | Mỗi partition có batch riêng; nhiều batch có thể nhỏ dù tổng lưu lượng lớn |
| Một record lớn hơn batch.size | Record vẫn có thể được gửi riêng nếu các giới hạn request và broker cho phép; batch.size không phải giới hạn record tối đa |

Tăng `batch.size` mà không có đủ lưu lượng để lấp batch có thể không đem lại lợi ích. Tăng `linger.ms` giúp producer chờ thêm, nhưng chỉ hiệu quả nếu record mới tiếp tục đến đúng partition trong khoảng thời gian đó.

## 5. Cấu hình trong Spring Boot

Spring Boot cung cấp thuộc tính cho kích thước batch và buffer. Các Kafka producer property khác có thể được truyền qua map `spring.kafka.producer.properties`:

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      buffer-memory: 67108864
      compression-type: lz4
      properties:
        linger.ms: 5
        max.block.ms: 60000
```

Trong ví dụ:

- `batch-size: 65536` đặt batch size 64 KiB.
- `linger.ms: 5` cho phép chờ thêm tối đa khoảng 5 ms để gom record.
- `buffer-memory: 67108864` đặt buffer producer 64 MiB.
- `compression-type: lz4` bật nén batch bằng LZ4.
- `max.block.ms` giới hạn thời gian các lời gọi như `send()` có thể bị chặn khi chờ metadata hoặc buffer cấp phát.

Đây là giá trị khởi đầu minh họa, không phải cấu hình tối ưu cho mọi hệ thống. Tên thuộc tính Boot và cách bind map có thể thay đổi theo phiên bản; kiểm tra metadata của Spring Boot đang dùng nếu cấu hình không được áp dụng.

## 6. Cấu hình trực tiếp qua ProducerFactory

Nếu ứng dụng tự tạo `ProducerFactory`, có thể đặt Kafka producer config bằng các hằng số `ProducerConfig`:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Bean
ProducerFactory<String, String> producerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.BATCH_SIZE_CONFIG, 64 * 1024);
    props.put(ProducerConfig.LINGER_MS_CONFIG, 5);
    props.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 64L * 1024 * 1024);
    props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
    return new DefaultKafkaProducerFactory<>(props);
}

@Bean
KafkaTemplate<String, String> kafkaTemplate(
        ProducerFactory<String, String> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

Nếu dùng Spring Boot auto-configuration, thường chỉ cần đặt các thuộc tính YAML thay vì tự tạo producer factory. Không khai báo hai producer factory với cấu hình khác nhau rồi vô tình inject nhầm factory vào `KafkaTemplate`.

## 7. Compression và batch size

Kafka nén dữ liệu theo batch. Batch có nhiều record tương tự nhau thường có cơ hội nén tốt hơn so với nhiều request nhỏ. Các lựa chọn thường gặp:

| Codec | Đặc điểm tổng quát | Khi cân nhắc |
| --- | --- | --- |
| `none` | Không nén, giảm chi phí CPU nén/giải nén | Payload nhỏ hoặc CPU là nút thắt |
| `gzip` | Tỷ lệ nén thường tốt nhưng tốn CPU hơn | Khi tiết kiệm network/disk quan trọng hơn CPU |
| `snappy` | Nén/giải nén nhanh, mức nén vừa phải | Cần cân bằng CPU và network |
| `lz4` | Thường có tốc độ cao, độ trễ thấp | Workload thông lượng cao, nhạy latency |
| `zstd` | Có thể đạt tỷ lệ nén tốt với nhiều mức điều chỉnh | Khi cần cân bằng tỷ lệ nén và CPU theo workload |

Lựa chọn thực tế phụ thuộc dữ liệu. JSON có nhiều tên field lặp lại thường nén tốt hơn payload đã nén hoặc dữ liệu ngẫu nhiên. Hãy đo compression ratio, CPU producer/broker/consumer và network throughput trên dữ liệu đại diện.

Không nên tăng batch size chỉ để tối ưu compression ratio nếu latency đã vượt SLA. Cũng không nên bật codec tốn CPU mà không đo tác động tới producer và broker.

## 8. flush() và gửi đồng bộ có thể làm mất lợi ích batching

Producer batching hiệu quả khi nhiều lần `send()` có thể tích lũy trong buffer. Nếu gọi `flush()` sau từng record, producer phải đẩy dữ liệu đang chờ gửi ngay, làm giảm cơ hội gom nhiều record vào cùng batch.

```java
// Không nên làm trong đường gửi thông thường:
for (OrderCreated event : events) {
    kafkaTemplate.send("orders", event.orderId(), event);
    kafkaTemplate.flush();
}
```

Thông thường nên gửi liên tiếp và để producer tự quyết định thời điểm gửi theo batch size, linger và trạng thái buffer:

```java
for (OrderCreated event : events) {
    kafkaTemplate.send("orders", event.orderId(), event);
}
```

`flush()` phù hợp khi cần bảo đảm các record đang được buffer được đẩy đi trước một mốc lifecycle, ví dụ trước khi đóng producer hoặc trong một quy trình cần chờ publish hoàn tất. Không nên dùng flush như một thao tác mặc định sau mỗi send.

Tương tự, gọi `.get()` ngay sau từng `send()` trong một vòng lặp tuần tự khiến luồng gọi chờ từng record, làm giảm cơ hội tích lũy batch nếu không có thread khác gửi đồng thời. Trong đường throughput cao, có thể gửi bất đồng bộ rồi tổng hợp callback/future và chờ ở ranh giới lô công việc khi cần.

## 9. Các cấu hình liên quan cần theo dõi

`batch.size` và `linger.ms` không hoạt động độc lập. Một số cấu hình khác ảnh hưởng đến buffer, request và độ tin cậy:

| Cấu hình | Vai trò | Lưu ý |
| --- | --- | --- |
| `buffer.memory` | Tổng bộ nhớ producer dành cho record đang chờ | Nếu cạn buffer, `send()` có thể chờ đến `max.block.ms` rồi timeout |
| `max.block.ms` | Thời gian tối đa `send()` chờ metadata/buffer | Timeout có thể xảy ra trước khi record được đưa vào buffer |
| `max.request.size` | Giới hạn kích thước request producer | Phải tương thích với giới hạn message phía broker/topic |
| `compression.type` | Codec nén batch | Đo CPU và tỷ lệ nén cùng latency |
| `acks` | Mức xác nhận của broker | Chọn theo yêu cầu durability và replication |
| `enable.idempotence` | Chống duplicate do retry ở producer theo semantics Kafka | Giữ các cấu hình tương thích; không tắt chỉ để tăng throughput khi chưa đánh giá |
| `max.in.flight.requests.per.connection` | Số request chưa được xác nhận trên một connection | Cân nhắc cùng idempotence và yêu cầu ordering |

`batch.size` là dung lượng batch theo partition; `max.request.size` và broker/topic message limit liên quan đến kích thước request/record được chấp nhận. Một record lớn hơn batch size không đồng nghĩa chắc chắn bị từ chối; cần kiểm tra các giới hạn request và broker tương ứng.

## 10. Đo hiệu quả batching bằng producer metrics

Không thể kết luận batching tốt chỉ vì đã tăng `batch.size` hoặc `linger.ms`. Hãy theo dõi các metric producer, tùy phiên bản client và hệ thống metric đang tích hợp:

| Metric thường gặp | Ý nghĩa | Dùng để đánh giá |
| --- | --- | --- |
| `batch-size-avg` | Kích thước batch trung bình | Batch thực tế có lớn hơn sau khi điều chỉnh không |
| `batch-size-max` | Kích thước batch lớn nhất | Batch có thường xuyên chạm giới hạn không |
| `records-per-request-avg` | Số record trung bình trong một request | Mỗi request có mang nhiều record hơn không |
| `compression-rate-avg` | Tỷ lệ nén trung bình | Codec và batch size có cải thiện hiệu quả nén không |
| `record-queue-time-avg` | Thời gian record nằm trong producer queue | Linger/buffer có làm tăng thời gian chờ không |
| `request-latency-avg` | Độ trễ request tới broker | Network/broker có trở thành nút thắt không |
| `bufferpool-wait-time-total` | Tổng thời gian producer chờ buffer pool | Buffer có thiếu khi tải cao không |
| `record-send-rate` | Tốc độ gửi record | Throughput thay đổi thế nào |

Metric cụ thể có thể khác tên hoặc cách expose giữa các phiên bản Kafka client. Hãy xem JMX/Micrometer metrics thực tế của client và đối chiếu với tài liệu phiên bản đang chạy.

## 11. Quy trình tuning batch.size và linger.ms

Nên bắt đầu bằng một baseline có thể lặp lại:

1. Ghi nhận throughput hiện tại (records/s và bytes/s), p95/p99 publish latency, CPU, network và producer metrics.
2. Đo kích thước record trung bình và phân phối kích thước record, số partition nhận traffic và số producer instance.
3. Thử tăng `batch.size` theo từng bước vừa phải, giữ `linger.ms` không đổi; quan sát batch-size-avg và records-per-request-avg.
4. Thử tăng `linger.ms` từng bước nhỏ để xem batch có đầy hơn và throughput/compression có cải thiện không.
5. Kiểm tra p95/p99 latency, record queue time, buffer wait và memory; dừng tăng khi latency hoặc tài nguyên vượt ngưỡng.
6. Thử codec nén với dữ liệu đại diện và so sánh CPU, network cùng compression ratio.
7. Lặp lại dưới tải cao điểm và tải thấp; một cấu hình tốt ở peak có thể tăng latency quá mức khi lưu lượng thưa.

Chỉ thay đổi một nhóm tham số mỗi lần để biết yếu tố nào tạo ra khác biệt. Đo cả producer và broker; nếu broker/network đã bão hòa, tăng batch size có thể không cải thiện throughput.

## 12. Ví dụ chọn cấu hình theo mục tiêu

Các giá trị dưới đây chỉ là điểm bắt đầu để thử nghiệm, không phải công thức cố định:

| Mục tiêu | Hướng cấu hình ban đầu | Điều cần theo dõi |
| --- | --- | --- |
| Latency thấp, lưu lượng thưa | `linger.ms` rất nhỏ; batch size vừa phải | p95/p99 publish latency và records/request |
| Throughput cao, record đến liên tục | Tăng `batch.size`, thử `linger.ms` vài ms | Batch size trung bình, bytes/s, CPU và queue time |
| Network là nút thắt | Thử batch lớn hơn và codec phù hợp | Compression ratio, network bytes/s và CPU |
| Nhiều partition có traffic thưa | Xem lại số partition và linger; mỗi partition có batch riêng | Số batch nhỏ, request rate và queue time |
| Buffer thường xuyên cạn | Xem lại `buffer.memory`, tốc độ broker nhận và số producer | Buffer wait, send timeout và producer memory |

Không nên tăng số partition chỉ để tăng batch size. Partition ảnh hưởng song song hóa, ordering và cách producer chia batch; thay đổi partition count cần được đánh giá như một quyết định kiến trúc riêng.

## 13. Kiểm thử và các lỗi thường gặp

Khi kiểm thử batching, cần tạo đủ lưu lượng cùng partition để quan sát batch thực tế. Gửi một record rồi chờ kết quả không thể chứng minh producer gom được nhiều record. Có thể gửi nhiều record cùng key hoặc chỉ định partition trong test, sau đó quan sát producer metrics.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Batch size trung bình vẫn nhỏ | Lưu lượng thưa, nhiều partition, linger quá thấp | Đo traffic theo partition; thử linger tăng nhẹ |
| Throughput không tăng sau khi tăng batch | Broker/network/CPU là nút thắt khác | Đo request latency, broker load và network |
| Publish latency tăng rõ | Linger cao hoặc buffer queue tích lũy | Giảm linger, xem record queue time và SLA |
| Producer thường timeout khi send | Buffer thiếu hoặc broker không nhận kịp | Xem buffer wait, `buffer.memory`, `max.block.ms` và broker health |
| Compression ratio thấp | Payload khó nén hoặc batch nhỏ | Đo codec trên dữ liệu thật và tăng khả năng gom batch nếu phù hợp |
| Batching gần như không có | Flush sau mỗi send hoặc chờ future tuần tự | Loại flush không cần thiết và đánh giá cách gửi bất đồng bộ |

## 14. Checklist triển khai

- [ ] Hiểu `batch.size` áp dụng cho batch của từng partition.
- [ ] Hiểu `linger.ms` là thời gian chờ thêm tối đa để gom record, không phải độ trễ cố định của mọi record.
- [ ] Cấu hình rõ batch size và linger theo phiên bản `kafka-clients` thực tế.
- [ ] Đánh giá `buffer.memory`, `max.block.ms` và `max.request.size` cùng batch size.
- [ ] Đã đo record size và lưu lượng theo partition.
- [ ] Không gọi `flush()` sau từng record trong đường gửi thông thường.
- [ ] Không chờ từng future tuần tự nếu mục tiêu là gom batch ở throughput cao.
- [ ] Đã đánh giá codec nén cùng CPU, network và compression ratio.
- [ ] Theo dõi batch-size, records-per-request, queue time, buffer wait và publish latency.
- [ ] Đã load test ở cả tải thấp và tải cao, đồng thời kiểm tra p95/p99 latency.

`batch.size` quyết định dung lượng batch theo partition, còn `linger.ms` quyết định producer có thể chờ thêm bao lâu để gom record trước khi gửi. Kết hợp hai cấu hình với buffer, compression và cách gọi `KafkaTemplate` phù hợp sẽ giúp tăng hiệu quả batching; số liệu throughput và latency thực tế mới là căn cứ để chọn giá trị cuối cùng.
