# Compression type

Kafka producer có thể nén record trước khi gửi tới broker. Nén giúp giảm lượng byte truyền qua network, dung lượng lưu trên disk và lưu lượng replication giữa các broker. Đổi lại, producer và consumer phải tiêu tốn CPU để nén và giải nén; broker cũng có thể tốn CPU nếu policy của topic yêu cầu giải nén rồi nén lại batch.

Thuộc tính `compression.type` chọn codec mà producer dùng để nén record batch. Kafka hỗ trợ các lựa chọn phổ biến `none`, `gzip`, `snappy`, `lz4` và `zstd`. Với Spring Kafka, cấu hình này được truyền qua `ProducerFactory` mà `KafkaTemplate` sử dụng; trong Spring Boot có thể khai báo `spring.kafka.producer.compression-type`.

## 1. Compression hoạt động ở cấp batch

Kafka producer không nén từng record thành một file riêng. Producer gom record thành batch theo partition, sau đó nén batch trước khi gửi Produce request. Vì vậy hiệu quả nén phụ thuộc vào codec, kích thước payload, mức độ lặp lại của dữ liệu và số record có thể gom vào cùng batch.

```text
Producer
  Record A ---+
  Record B ---+----> Batch của partition 0 ----+
  Record C ---+                                |
                                               v
                                      Compression codec
                                               |
                                               v
                                      Compressed batch
                                               |
                                               v
                                          Kafka broker
                                               |
                                  lưu trữ / replication
                                               |
                                               v
                                      Consumer fetch
                                               |
                                               v
                                      Decompress batch
                                               |
                                               v
                                      Listener nhận record
```

Các điểm cần nhớ:

- Compression được áp dụng cho record batch, thường riêng theo từng partition.
- Batch có nhiều record và payload có mẫu lặp thường nén hiệu quả hơn batch nhỏ hoặc dữ liệu ngẫu nhiên.
- Consumer Kafka giải nén batch tự động; listener nhận key/value đã được deserialize như bình thường.
- Ứng dụng không cần tự gọi codec để giải nén record do Kafka client đọc.
- Compression không thay đổi thứ tự record trong partition và không thay thế serializer/deserializer.

Nếu một producer gửi ít record tới rất nhiều partition, mỗi partition có thể chỉ có batch nhỏ. Tổng lưu lượng topic cao không bảo đảm từng batch đều đủ lớn để đạt compression ratio tốt.

## 2. Các giá trị của compression.type

Producer property `compression.type` nhận các giá trị codec sau:

| Giá trị | Đặc điểm tổng quát | Khi nên thử |
|---|---|---|
| `none` | Không nén; ít CPU nhất nhưng truyền và lưu nhiều byte hơn | Payload nhỏ, CPU producer đã bão hòa hoặc cần baseline so sánh |
| `gzip` | Tỷ lệ nén thường tốt, đổi lại CPU nén/giải nén cao hơn | Network/disk là nút thắt và CPU còn dư |
| `snappy` | Ưu tiên tốc độ, tỷ lệ nén thường ở mức vừa phải | Cần giảm byte với chi phí CPU tương đối thấp |
| `lz4` | Tốc độ nén/giải nén cao, thường phù hợp luồng throughput lớn | Muốn cân bằng giữa CPU và network |
| `zstd` | Tỷ lệ nén thường tốt, có thể điều chỉnh mức nén ở client hỗ trợ | Payload lớn hoặc cần giảm network/disk đáng kể và có ngân sách CPU |

Không có codec tốt nhất cho mọi workload. Ví dụ JSON có nhiều tên field và chuỗi lặp có thể nén tốt, trong khi payload đã nén, mã hóa hoặc chứa dữ liệu ngẫu nhiên có thể giảm rất ít. Hãy benchmark bằng dữ liệu gần với production.

`producer` không phải giá trị codec của producer. Đây là một lựa chọn trong topic configuration `compression.type`, có nghĩa broker giữ codec mà producer đã dùng. Producer property dùng `none`, `gzip`, `snappy`, `lz4` hoặc `zstd`.

## 3. Nén và giải nén ở những thành phần nào?

Trong luồng thông thường:

1. Producer serialize object thành bytes.
2. Producer gom record thành batch theo partition.
3. Producer nén batch theo `compression.type`.
4. Broker nhận và lưu batch; broker có thể giữ nguyên codec hoặc chuyển codec theo topic policy.
5. Replication và consumer fetch truyền dữ liệu theo dạng batch được lưu.
6. Kafka consumer giải nén batch trước khi chuyển record tới ứng dụng.

Vì consumer giải nén tự động, code listener không cần biết producer đã chọn gzip hay lz4. Tuy nhiên, consumer vẫn chịu chi phí CPU giải nén. Nếu tăng throughput bằng cách nén mạnh hơn, hãy theo dõi CPU của consumer để chắc rằng giải nén không trở thành nút thắt mới.

Compression giảm kích thước dữ liệu trên đường truyền và khi lưu trữ, nhưng không làm payload nghiệp vụ nhỏ hơn sau khi listener nhận record. Nếu listener parse JSON lớn hoặc chuyển đổi object tốn CPU, cần tối ưu bước đó riêng.

## 4. Cấu hình compression.type trong Spring Boot

Spring Boot có thuộc tính `spring.kafka.producer.compression-type`. Ví dụ chọn lz4:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      compression-type: lz4
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Thuộc tính `compression-type` được ánh xạ tới Kafka producer property `compression.type`. Nếu muốn cấu hình trực tiếp qua map properties, có thể viết:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[compression.type]": zstd
```

Nên chọn một nơi cấu hình để tránh hai giá trị mâu thuẫn. Nếu đồng thời khai báo `compression-type` và `properties["compression.type"]`, hãy xác minh property cuối cùng mà producer factory nhận được.

`KafkaTemplate` không có một compression setting độc lập cho từng lần gọi `send()`. Compression là cấu hình của Kafka producer do `ProducerFactory` tạo ra. Nếu một ứng dụng cần hai chính sách compression khác nhau, có thể tạo hai producer factory/template riêng với cấu hình được quản lý rõ ràng.

## 5. Cấu hình bằng ProducerFactory trong Java

Khi không dùng Spring Boot auto-configuration hoặc cần kiểm soát producer properties trực tiếp, đặt `ProducerConfig.COMPRESSION_TYPE_CONFIG` trong cấu hình factory:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class KafkaProducerConfiguration {

    @Bean
    ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "zstd");

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

Mọi record được gửi bằng template này sẽ dùng codec được cấu hình trên producer factory. Trong production, bootstrap server, serializer và compression type nên lấy từ cấu hình môi trường thay vì hard-code.

## 6. Compression kết hợp với batch.size và linger.ms

Kafka nén batch, do đó hiệu quả compression chịu ảnh hưởng lớn bởi khả năng gom record:

- `batch.size` đặt dung lượng mục tiêu cho batch theo partition.
- `linger.ms` cho producer thêm thời gian gom record khi batch chưa đầy.
- `compression.type` chọn codec áp dụng cho batch.

Ví dụ cấu hình:

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      compression-type: lz4
      properties:
        "[linger.ms]": 5
```

Với lưu lượng đủ cao, batch có thể đầy trước khi hết linger. Với lưu lượng thấp, producer có thể chờ tới thời điểm linger để gửi batch chưa đầy. Batch lớn hơn có thể cải thiện tỷ lệ nén, nhưng cũng tăng bộ nhớ cần thiết và có thể làm tăng latency khi phải chờ gom record.

Không tăng `batch.size` hoặc `linger.ms` một cách độc lập chỉ để có compression ratio thấp hơn. Cần xem đồng thời:

- Batch size trung bình và tỷ lệ batch đầy.
- Thời gian record nằm trong producer buffer.
- p95/p99 producer latency.
- CPU producer và consumer.
- Bytes in/out của broker và network.

Nếu payload đã nén tốt hoặc batch quá nhỏ, tăng linger có thể chỉ làm tăng latency mà không giảm được nhiều byte.

## 7. Topic compression.type và broker policy

Producer quyết định codec ban đầu, nhưng topic có thể quy định cách broker lưu batch bằng topic configuration `compression.type`.

Các lựa chọn thường gặp ở topic:

| Topic compression.type | Hành vi |
|---|---|
| `producer` | Giữ codec mà producer đã sử dụng; đây là giá trị mặc định phổ biến |
| `uncompressed` | Broker giải nén và lưu batch không nén |
| `gzip`, `snappy`, `lz4`, `zstd` | Broker lưu batch theo codec được chỉ định; có thể phải giải nén rồi nén lại nếu codec đầu vào khác |

Ví dụ giữ nguyên codec do producer chọn:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --alter \
  --add-config compression.type=producer
```

Ví dụ buộc topic lưu batch bằng zstd:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --alter \
  --add-config compression.type=zstd
```

Khi broker phải chuyển codec, broker tiêu tốn CPU để giải nén và nén lại. Vì vậy, chọn topic policy khác producer codec có thể làm giảm lợi ích tổng thể nếu broker trở thành nút thắt.

Không nhầm producer property `compression.type` với topic property cùng tên. Producer property chọn codec gửi ban đầu; topic property quyết định broker giữ codec đó hay chuyển sang codec khác.

## 8. Kiểm tra topic policy hiện tại

Có thể đọc cấu hình topic bằng Kafka CLI:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --describe
```

Nếu topic không có override riêng cho `compression.type`, nó có thể kế thừa mặc định `producer` theo cấu hình Kafka. Hãy kiểm tra cả cấu hình topic và producer khi compression ratio hoặc CPU không giống kỳ vọng.

Trong môi trường được quản lý bằng IaC hoặc Kafka operator, nên thay đổi topic config qua nguồn cấu hình chuẩn của tổ chức để tránh drift giữa cluster và repository.

## 9. Chọn codec theo đặc điểm payload

Kích thước và nội dung payload thường ảnh hưởng compression ratio:

| Payload | Hành vi nén thường gặp | Gợi ý thử nghiệm |
|---|---|---|
| JSON nhiều field và chuỗi lặp | Có nhiều mẫu lặp, thường nén tốt | lz4, zstd, gzip |
| JSON rất nhỏ, record rời rạc | Overhead batch có thể chiếm tỷ lệ lớn | none, lz4 hoặc tăng batch hợp lý |
| Avro/Protobuf binary | Có thể đã gọn hơn JSON nhưng vẫn có dữ liệu lặp | lz4, zstd, none |
| Ảnh/video hoặc payload đã nén | Ít khả năng giảm thêm | none hoặc codec nhanh sau khi đo |
| Dữ liệu mã hóa/ngẫu nhiên | Thường khó nén | none |

Không dùng bảng này như quy tắc cứng. Avro/Protobuf không đồng nghĩa payload đã được nén; dữ liệu nhị phân vẫn có thể giảm kích thước với codec phù hợp. Cần thử trên mẫu dữ liệu thực.

## 10. Compression ratio và cách đọc số liệu

Có thể định nghĩa tỷ lệ kích thước sau nén:

```text
compression ratio = compressed bytes / uncompressed bytes
```

Ví dụ, batch ban đầu 100 KiB và sau nén còn 35 KiB:

```text
compression ratio = 35 / 100 = 0.35
size reduction    = 1 - 0.35 = 65%
```

Ratio càng thấp nghĩa là lượng byte sau nén càng nhỏ so với ban đầu. Tuy nhiên, ratio thấp không tự động đồng nghĩa hệ thống nhanh hơn: codec có thể dùng nhiều CPU hơn, batch có thể phải chờ lâu hơn và broker có thể phải recompress.

Khi đọc metric `compression-rate-avg` của Kafka producer, cần xem định nghĩa metric của phiên bản client đang dùng. Metric này thường biểu diễn tỷ lệ kích thước batch sau nén so với trước nén; giá trị thấp hơn cho biết nén hiệu quả hơn. Đừng nhầm metric này với phần trăm tiết kiệm byte.

## 11. Đo hiệu năng trước khi chọn codec

Một benchmark có ích cần giữ workload tương đương giữa các lần thử:

1. Chuẩn bị tập payload đại diện cho production, gồm kích thước nhỏ/vừa/lớn và dữ liệu lặp/ngẫu nhiên.
2. Giữ nguyên số partition, key distribution, producer concurrency và tốc độ phát record.
3. Chạy baseline với `none`.
4. Thử lần lượt `lz4`, `snappy`, `zstd` và `gzip`.
5. Đo producer throughput, broker network bytes, consumer throughput và end-to-end latency.
6. Ghi CPU của producer, broker và consumer.
7. Lặp lại ở tải thấp và tải cao để thấy tác động của batch fill và linger.
8. Chọn codec đạt SLA latency/throughput với chi phí CPU và network hợp lý.

Các metric có thể theo dõi:

| Metric | Dùng để đánh giá |
|---|---|
| `compression-rate-avg` | Tỷ lệ kích thước batch sau nén |
| `batch-size-avg` | Batch trung bình có đủ lớn để nén hiệu quả không |
| `record-send-rate` | Số record producer gửi mỗi giây |
| `request-latency-avg` / `request-latency-max` | Thời gian broker phản hồi request |
| `record-queue-time-avg` | Thời gian record chờ trong producer accumulator |
| `record-retry-rate` và `record-error-rate` | Retry và lỗi khi gửi |
| CPU và network bytes | Chi phí tài nguyên thực tế của codec |

Tên metric và cách export phụ thuộc Kafka client, JMX, Micrometer và hệ thống monitoring. So sánh số liệu trên cùng phiên bản client và cùng cách thu thập.

## 12. Ảnh hưởng tới broker, replication và storage

Khi topic dùng `compression.type=producer`, broker thường giữ compression codec mà producer gửi. Điều này có thể giảm:

- Bytes nhận qua network ở broker.
- Bytes lưu trong log segment.
- Bytes truyền qua replication giữa broker.
- Bytes consumer phải fetch từ broker.

Nếu topic buộc broker chuyển codec, broker phải giải nén và nén lại batch, làm tăng CPU và có thể tăng latency append. Khi nhiều producer dùng codec khác nhau nhưng topic buộc một codec chung, cần benchmark tải CPU broker.

Compression không thay đổi replication factor, số partition hoặc cơ chế retention. Nó làm thay đổi kích thước dữ liệu vật lý, nên có thể ảnh hưởng tốc độ tăng dung lượng disk nhưng không thay thế capacity planning.

## 13. Giới hạn kích thước record và request

Compression có thể làm batch nhỏ hơn khi truyền và lưu, nhưng không nên dùng nó để né các giới hạn kích thước:

- Producer có giới hạn request như `max.request.size`.
- Broker/topic có giới hạn batch/message như `message.max.bytes` hoặc `max.message.bytes` tùy cấu hình và phiên bản.
- Consumer có các giới hạn fetch như `fetch.max.bytes` và `max.partition.fetch.bytes`.

Hãy kiểm tra kích thước record/batch theo cả dữ liệu gốc lẫn dữ liệu đã nén và bảo đảm consumer có thể fetch batch hợp lệ. Một record đơn lẻ quá lớn vẫn có thể gây lỗi dù codec có tỷ lệ nén tốt.

Không tăng mọi giới hạn cùng lúc. Payload lớn có thể gây áp lực memory, network và GC ở cả producer lẫn consumer.

## 14. Tương thích codec giữa client và cluster

Producer và consumer cần Kafka client hỗ trợ codec được sử dụng. Với cluster có nhiều phiên bản broker, hãy xác minh compatibility theo phiên bản Kafka client/broker và quy trình rolling upgrade của tổ chức, đặc biệt khi chọn codec mới như zstd.

Các điểm cần kiểm tra:

- Kafka client runtime có implementation codec cần thiết trên classpath.
- Mọi consumer cần đọc topic đều hỗ trợ codec producer đang phát.
- Broker có thể giữ hoặc chuyển codec theo topic policy.
- Các công cụ CLI, connector, MirrorMaker hoặc ứng dụng ngoài Java có thể đọc được codec đó.
- Upgrade broker/client không làm mất khả năng đọc các batch cũ đang lưu trong log.

Không chỉ kiểm tra producer gửi thành công. Cần kiểm tra consumer, connector và công cụ vận hành đọc được dữ liệu đã nén trong topic.

## 15. Compression và serializer là hai lớp khác nhau

Serializer quyết định cách object Java được chuyển thành bytes; compression codec quyết định cách batch bytes được nén.

| Lớp | Ví dụ | Nhiệm vụ |
|---|---|---|
| Serializer | StringSerializer, JsonSerializer, KafkaAvroSerializer | Chuyển key/value thành bytes |
| Compression | gzip, snappy, lz4, zstd | Nén record batch |
| Deserializer | StringDeserializer, JsonDeserializer, KafkaAvroDeserializer | Chuyển bytes trở lại object |

Ví dụ ứng dụng có thể dùng `JsonSerializer` cho value và `lz4` cho batch. Consumer dùng `JsonDeserializer`; Kafka client giải nén batch trước rồi deserializer chuyển payload JSON thành object.

Không cấu hình `KafkaAvroSerializer` chỉ vì muốn nén dữ liệu. Avro là serialization format; gzip/lz4/zstd là compression codec. Hai cơ chế có thể dùng cùng nhau.

## 16. Lưu ý khi dùng KafkaTemplate và nhiều producer factory

`KafkaTemplate` lấy producer từ `ProducerFactory`. Vì vậy compression type được quyết định tại factory, không phải bởi từng `send()` call:

```java
KafkaTemplate<String, String> fastTemplate = templateUsingLz4;
KafkaTemplate<String, String> compactTemplate = templateUsingZstd;

fastTemplate.send("orders.events", "order-1", payload);
compactTemplate.send("archive.events", "order-1", payload);
```

Ví dụ trên giả định ứng dụng có hai template được tạo từ hai producer factory với cấu hình compression riêng. Nếu nhiều template dùng chung một factory, chúng cũng dùng chung producer configuration và codec.

Chỉ tạo nhiều factory khi có nhu cầu vận hành rõ ràng; mỗi factory làm tăng số producer, buffer và connection cần quản lý. Nếu toàn bộ topic có cùng yêu cầu, một producer factory với một codec thường đơn giản hơn.

## 17. Troubleshooting compression

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Compression ratio gần 1.0 | Payload ít lặp, batch nhỏ, dữ liệu đã nén hoặc producer property chưa được áp dụng |
| Producer CPU tăng cao | Codec tốn CPU, compression level cao hoặc throughput vượt capacity |
| Broker CPU tăng sau khi đổi topic config | Broker có thể đang giải nén và nén lại batch |
| Consumer CPU tăng | Giải nén cộng với deserialize/parse đang thành nút thắt |
| Network giảm nhưng latency tăng | Codec tốn CPU, linger/batch wait hoặc broker recompression |
| Producer báo codec không hỗ trợ | Kafka client version hoặc runtime dependency thiếu implementation |
| Consumer/connector không đọc được topic | Client hoặc connector chưa hỗ trợ codec đang lưu trong log |
| Kích thước record vẫn vượt giới hạn | Payload gốc hoặc batch vượt giới hạn; compression không bảo đảm mọi record sẽ nhỏ hơn ngưỡng |

Khi điều tra, xác nhận giá trị producer `compression.type`, topic `compression.type`, Kafka client version, batch size thực tế và metric compression. Tránh chỉ nhìn một metric ratio mà kết luận hiệu năng đã tốt hơn.

## 18. Những nhầm lẫn thường gặp

1. **Cho rằng Kafka nén từng record riêng lẻ.** Producer nén record batch theo partition.
2. **Cho rằng consumer phải tự giải nén.** Kafka client giải nén trước khi listener nhận record.
3. **Cho rằng zstd luôn tốt hơn gzip hoặc lz4.** Kết quả phụ thuộc payload, CPU, batch và workload.
4. **Nhầm `producer` là codec của producer.** Đây là topic policy để giữ codec producer đã chọn.
5. **Chỉ cấu hình producer mà bỏ qua topic policy.** Topic có thể buộc broker chuyển codec hoặc lưu uncompressed.
6. **Tăng batch/linger chỉ để cải thiện compression ratio.** Có thể làm latency và memory tăng.
7. **Cho rằng compression thay thế serializer.** Serializer chuyển object thành bytes; compression nén batch bytes.
8. **Cho rằng compression giúp vượt giới hạn message.** Các giới hạn request/batch vẫn phải được đáp ứng.
9. **Chỉ đo network mà bỏ qua CPU.** Codec giảm byte nhưng có thể làm producer, broker hoặc consumer bão hòa CPU.
10. **Không kiểm tra connector và consumer ngoài Java.** Mọi client đọc topic phải hỗ trợ codec đang được lưu.

`compression.type` là một lựa chọn hiệu năng ở cấp producer batch. Hãy bắt đầu bằng dữ liệu đại diện, đo compression ratio cùng CPU, network, throughput và p95/p99 latency; sau đó chọn codec phù hợp với SLA. Với Spring Kafka, cấu hình `spring.kafka.producer.compression-type` hoặc producer property tương ứng, đồng thời kiểm tra topic policy để broker không âm thầm recompress theo cách làm tăng chi phí.
