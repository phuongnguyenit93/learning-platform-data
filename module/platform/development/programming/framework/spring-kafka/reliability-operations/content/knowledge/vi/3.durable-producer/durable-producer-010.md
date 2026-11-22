# compression.type và áp lực CPU

Kafka có thể nén record trước khi gửi qua mạng và lưu vào log. Nén thường giảm số byte truyền giữa producer, broker và consumer, đồng thời giảm dung lượng log trên đĩa. Đổi lại, ứng dụng phải dùng CPU để nén và giải nén dữ liệu. Vì vậy, chọn `compression.type` là một quyết định cân bằng giữa băng thông, dung lượng lưu trữ, thông lượng và độ trễ xử lý.

Trong Spring Kafka, cấu hình này thường được đặt ở producer vì producer tạo record batch và nén batch trước khi gửi. Codec phù hợp phụ thuộc vào hình dạng payload, kích thước batch, giới hạn CPU và nút thắt thực tế của hệ thống. Một codec có tỷ lệ nén tốt nhất chưa chắc tạo ra throughput tốt nhất nếu CPU producer đang bão hòa.

## 1. `compression.type` điều khiển điều gì?

`compression.type` là thuộc tính của Kafka producer xác định codec dùng để nén record batch. Các giá trị phổ biến được Kafka hỗ trợ gồm:

| Giá trị | Đặc điểm thường gặp | Khi nên thử |
|---|---|---|
| `none` | Không nén; gần như không tốn CPU cho nén/giải nén nhưng truyền và lưu nhiều byte hơn | Payload đã được nén, CPU rất hạn chế hoặc tải chưa bị giới hạn bởi mạng/đĩa |
| `gzip` | Tỷ lệ nén thường cao, đổi lại chi phí CPU và độ trễ nén có thể lớn | Băng thông hoặc dung lượng lưu trữ là nút thắt và CPU còn dư |
| `snappy` | Nén và giải nén nhanh, tỷ lệ nén thường ở mức vừa phải | Cần giảm byte truyền với chi phí CPU tương đối thấp |
| `lz4` | Ưu tiên tốc độ, thường có độ trễ thấp và chi phí CPU vừa phải | Luồng throughput cao, cần cân bằng giữa CPU và dung lượng |
| `zstd` | Có thể đạt tỷ lệ nén cao; mức CPU phụ thuộc compression level | Muốn giảm byte mạnh và có thể điều chỉnh mức nén theo CPU sẵn có |

`none` thường là mặc định nếu producer không được cấu hình compression. Các codec và compression level khả dụng còn phụ thuộc phiên bản Kafka client, broker và thư viện codec. Trước khi triển khai một codec mới, xác nhận toàn bộ cluster và các consumer sử dụng có hỗ trợ nó.

Ví dụ, producer có thể tạo một batch gồm nhiều sự kiện JSON cùng partition rồi nén batch đó bằng LZ4. Broker nhận batch đã nén và lưu dữ liệu theo định dạng batch của Kafka. Consumer giải nén batch trước khi chuyển record cho ứng dụng.

## 2. Kafka nén theo batch, không nén riêng từng record

Producer gom record vào các batch theo partition. Khi batch được gửi, Kafka nén phần dữ liệu của batch. Điều này có hai hệ quả:

- Nhiều record cùng partition trong một batch thường nén hiệu quả hơn việc gửi từng record nhỏ lẻ, vì codec có nhiều dữ liệu để tìm mẫu lặp.
- Producer có nhiều partition hoạt động nhưng mỗi partition chỉ nhận ít record có thể tạo ra nhiều batch nhỏ. Tỷ lệ nén khi đó thường kém hơn so với một luồng có cùng tổng số record nhưng gom được batch lớn hơn.

Hai cấu hình ảnh hưởng trực tiếp đến kích thước batch là `batch.size` và `linger.ms`:

- `batch.size` đặt giới hạn kích thước batch mà producer cố gắng gom cho mỗi partition. Đây là giới hạn gom batch, không phải kích thước tối đa của một record.
- `linger.ms` cho producer thêm thời gian chờ record khác đến để batch có thể đầy hơn trước khi gửi. Tăng giá trị này có thể cải thiện batching và compression, nhưng cũng tăng thời gian chờ của record khi tải thấp.

`buffer.memory` giới hạn bộ nhớ producer dành cho các record đang chờ gửi. Tăng `batch.size` hoặc `linger.ms` có thể làm thay đổi lượng dữ liệu nằm trong buffer và thời gian record chờ. Cần điều chỉnh các giá trị này cùng nhau, theo tải thực tế.

```text
Records của partition 0 ----> Batch 0 ----> Compress ----+
Records của partition 1 ----> Batch 1 ----> Compress ----+----> Broker
Records của partition 2 ----> Batch 2 ----> Compress ----+

Mỗi partition có batch riêng. Một batch đầy thường tạo cơ hội nén tốt hơn batch chỉ có một vài record.
```

Không nên tăng `batch.size` vô hạn chỉ để đạt compression ratio cao. Batch lớn hơn có thể tăng bộ nhớ sử dụng, thời gian chờ và kích thước request. Hãy cân bằng throughput, latency và bộ nhớ.

## 3. Nén tác động đến CPU ở những đâu?

Một luồng producer → broker → consumer có thể tiêu tốn CPU ở nhiều vị trí:

1. **Producer:** Kafka client nén batch trước khi gửi. Codec càng tốn CPU thì producer càng cần nhiều năng lực xử lý để duy trì cùng tốc độ record.
2. **Broker:** broker xử lý request, lưu batch và phục vụ consumer. Khi broker giữ nguyên codec do producer gửi, broker tránh được bước chuyển codec. Nếu cấu hình broker/topic yêu cầu codec lưu trữ khác codec producer, broker có thể phải giải nén rồi nén lại, làm tăng CPU và độ trễ phía broker.
3. **Consumer:** client giải nén batch trước khi đưa record cho listener. Nén mạnh có thể giảm byte fetch qua mạng và dữ liệu đọc từ đĩa, nhưng consumer vẫn phải có CPU để giải nén.

Do đó, giảm network bytes không đồng nghĩa giảm tổng chi phí tài nguyên. Một cấu hình có thể làm producer CPU tăng, broker network giảm và consumer CPU tăng. Hãy theo dõi từng thành phần thay vì chỉ nhìn CPU của broker.

### Khi CPU là nút thắt

Nếu producer đã sử dụng gần hết CPU hoặc bị CPU throttling, chọn codec tốn CPU hơn có thể làm giảm tốc độ gửi. Record chờ lâu hơn trong buffer, request được tạo chậm hơn và độ trễ end-to-end tăng. Khi buffer không được giải phóng đủ nhanh, producer có thể phát sinh thời gian chờ buffer hoặc lỗi gửi khi quá thời hạn cấu hình.

Ở consumer, giải nén tiêu tốn CPU có thể làm listener xử lý chậm, consumer lag tăng và thời gian poll kéo dài. Ở broker, CPU dành cho chuyển đổi codec có thể cạnh tranh với request handling và các tác vụ broker khác.

### Khi mạng hoặc đĩa là nút thắt

Nếu CPU còn dư nhưng mạng hoặc I/O đĩa đang bão hòa, nén có thể cải thiện throughput tổng thể. Ít byte hơn được truyền và ghi xuống log; broker cũng có thể giữ được nhiều dữ liệu hữu ích hơn trong page cache. Lợi ích này thường rõ hơn với payload văn bản hoặc dữ liệu có nhiều trường, tên thuộc tính và giá trị lặp.

Payload đã nén sẵn như ảnh JPEG, video, file ZIP hoặc dữ liệu đã được ứng dụng mã hóa thường khó nén thêm. Khi đó, chi phí CPU có thể tăng trong khi số byte giảm rất ít. Với payload có entropy cao, hãy benchmark `none` cùng các codec thay vì mặc định rằng nén luôn có lợi.

## 4. Chọn codec theo workload

Không có codec tốt nhất cho mọi hệ thống. Bảng dưới đây là điểm khởi đầu để benchmark, không phải thứ hạng tuyệt đối:

| Nhu cầu chính | Codec nên đưa vào thử nghiệm | Điều cần quan sát |
|---|---|---|
| Độ trễ thấp và throughput cao | `lz4`, `snappy` | CPU producer/consumer, p95/p99 latency và bytes/request |
| Giảm dung lượng mạnh khi CPU còn dư | `zstd`, `gzip` | Compression ratio, CPU time trên mỗi MB và throughput |
| CPU producer đang bão hòa | `none`, `lz4`, `snappy` | CPU giảm có đủ bù cho network bytes tăng hay không |
| Network hoặc disk throughput đang là nút thắt | `lz4`, `zstd`, `gzip` | Network/disk bytes giảm, broker CPU và consumer CPU |
| Payload phần lớn đã nén hoặc mã hóa | `none` trước, sau đó đo `lz4` | Tỷ lệ giảm byte thực tế so với CPU bổ sung |

Một cách bắt đầu thường hợp lý cho luồng sự kiện JSON throughput cao là thử LZ4. Nếu network hoặc lưu trữ vẫn là nút thắt và CPU còn dư, thử Zstandard với các mức nén khác nhau. Nếu workload có CPU rất hạn chế, đo Snappy hoặc tắt nén. Với gzip, chỉ chọn sau khi kết quả benchmark cho thấy lợi ích giảm byte xứng đáng với chi phí CPU.

### Compression level

Một số codec hỗ trợ `compression.level`. Level thấp thường ưu tiên tốc độ, level cao thường ưu tiên tỷ lệ nén và có thể tiêu tốn CPU nhiều hơn. Ý nghĩa và miền giá trị phụ thuộc codec cùng phiên bản client; không nên sao chép một level từ cấu hình gzip sang Zstandard hoặc LZ4 mà không kiểm tra tài liệu phiên bản đang chạy.

Chỉ cấu hình level sau khi đã chọn codec và có số đo cho thấy cần điều chỉnh. Một level nén cao có thể giảm thêm một ít byte nhưng làm producer chậm đi đáng kể. Mục tiêu là tối ưu chi phí tổng thể trên mỗi record, không phải tối thiểu hóa kích thước batch bằng mọi giá.

## 5. Cấu hình compression trong Spring Boot

Spring Boot cung cấp thuộc tính `spring.kafka.producer.compression-type`, được ánh xạ sang Kafka producer property `compression.type`.

```yaml
spring:
  kafka:
    producer:
      compression-type: lz4
      batch-size: 65536
      properties:
        linger.ms: 5
```

Ví dụ trên chọn LZ4, đặt batch size 64 KiB và cho producer chờ tối đa 5 ms để gom thêm record. Đây là giá trị khởi đầu để thử nghiệm; tải, số partition và yêu cầu latency có thể khiến cấu hình phù hợp khác đi.

Nếu codec đang dùng hỗ trợ compression level và ứng dụng cần điều chỉnh, có thể truyền Kafka property trực tiếp:

```yaml
spring:
  kafka:
    producer:
      compression-type: zstd
      properties:
        compression.level: 3
        linger.ms: 5
```

Level `3` ở đây chỉ là ví dụ cấu hình cho môi trường đã xác nhận phiên bản Zstandard client hỗ trợ giá trị đó. Hãy kiểm tra miền giá trị và đo CPU trước khi dùng trong production. Nếu không có lý do rõ ràng để thay đổi level, bắt đầu bằng mặc định của codec thường dễ vận hành hơn.

Có thể cấu hình trực tiếp khi tạo `ProducerFactory`:

```java
Map<String, Object> props = new HashMap<>();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class);
props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
props.put(ProducerConfig.BATCH_SIZE_CONFIG, 64 * 1024);
props.put(ProducerConfig.LINGER_MS_CONFIG, 5);

ProducerFactory<String, OrderEvent> producerFactory =
        new DefaultKafkaProducerFactory<>(props);
KafkaTemplate<String, OrderEvent> kafkaTemplate =
        new KafkaTemplate<>(producerFactory);
```

Trong một ứng dụng Spring Kafka, `KafkaTemplate` sử dụng producer do `ProducerFactory` tạo ra. Cấu hình compression gắn với producer đó và thường áp dụng cho mọi topic mà producer gửi. Nếu các nhóm topic có yêu cầu codec khác nhau, có thể cần các `ProducerFactory`/`KafkaTemplate` riêng với cấu hình rõ ràng cho từng nhóm.

## 6. Phân biệt cấu hình producer với cấu hình broker/topic

Tên `compression.type` cũng xuất hiện ở cấu hình log của broker và cấu hình topic. Ý nghĩa của nó ở phía broker khác với thuộc tính producer:

- **Producer `compression.type`:** codec client dùng để nén batch trước khi gửi.
- **Broker/topic `compression.type=producer`:** broker giữ codec mà producer đã sử dụng.
- **Broker/topic đặt một codec cụ thể:** broker có thể chuyển batch sang codec được yêu cầu khi ghi log. Quá trình chuyển đổi có thể cần giải nén và nén lại, làm tăng CPU và latency của broker.
- **Broker/topic `compression.type=uncompressed`:** dữ liệu được lưu không nén; broker phải xử lý việc giải nén nếu batch đến đang được nén.

Vì vậy, nếu producer đã gửi LZ4 nhưng topic yêu cầu lưu gzip, hệ thống có thể phải thực hiện thêm công việc nén ở broker. Trước khi kết luận CPU tăng là do producer codec, hãy kiểm tra cấu hình topic và broker cùng codec thực tế của batch được lưu.

Consumer không chọn codec của batch đã được ghi. Kafka client đọc codec trong record batch và giải nén theo codec đó. Consumer phải dùng phiên bản client tương thích với codec được sử dụng.

## 7. Đo compression ratio và chi phí CPU

Đừng chọn codec chỉ dựa vào một chỉ số. Cần so sánh lượng byte tiết kiệm với CPU tiêu thụ và ảnh hưởng lên độ trễ. Các producer metric hữu ích gồm:

| Metric | Ý nghĩa khi điều tra |
|---|---|
| `compression-rate-avg` | Theo dõi mức nén trung bình của batch; đối chiếu với request size và byte truyền để hiểu hiệu quả codec. |
| `batch-size-avg` | Cho biết batch thực tế có đầy hay thường nhỏ hơn cấu hình `batch.size`. |
| `records-per-request-avg` | Cho biết producer đang gom được bao nhiêu record trong mỗi request. |
| `request-size-avg` | Theo dõi kích thước request gửi đến broker. |
| `record-queue-time-avg` | Thời gian record chờ trong producer trước khi được gửi; tăng mạnh có thể báo hiệu producer hoặc broker đang chậm. |
| `request-latency-avg` | Thời gian request hoàn tất theo góc nhìn producer. |
| `record-send-rate` | Tốc độ gửi record, cần đọc cùng CPU và latency. |
| `bufferpool-wait-time` | Thời gian producer chờ lấy buffer; tăng có thể cho thấy buffer bị giữ lâu hoặc producer không gửi kịp. |

Tên metric và cách hiển thị có thể thay đổi theo phiên bản Kafka client và hệ thống metrics. Hãy kiểm tra metric thực tế được export trong môi trường của ứng dụng. Với compression rate, đọc định nghĩa của phiên bản client để hiểu chiều của tỷ lệ; đối chiếu thêm request bytes và uncompressed record bytes để tránh diễn giải ngược.

Ngoài producer metrics, theo dõi:

- CPU usage và CPU throttling của từng producer pod/instance.
- CPU của consumer và thời gian xử lý listener.
- Consumer lag, records consumed rate và fetch size.
- Broker CPU, request handler idle percentage, network bytes in/out và disk throughput.
- p50, p95, p99 latency từ lúc record được tạo đến lúc downstream hoàn tất xử lý.

CPU trung bình thấp không loại trừ tình trạng một core hoặc một container bị bão hòa. Với ứng dụng chạy trong container, xem cả CPU limit và thời gian bị throttling. Nếu producer có nhiều partition nhưng một instance xử lý nhiều record, đo CPU trên từng instance để phát hiện phân bố tải không đều.

## 8. Benchmark có kiểm soát

Một benchmark hữu ích cần giữ workload ổn định để sự khác biệt quan sát được chủ yếu đến từ codec. Thực hiện theo quy trình sau:

1. Chọn payload đại diện: JSON nhiều trường lặp, JSON ít lặp, Avro/Protobuf hoặc payload đã nén sẵn nếu hệ thống thực sự sử dụng.
2. Giữ nguyên số partition, replication factor, số producer, số consumer, batch size và linger khi so sánh codec.
3. Chạy từng codec (`none`, `lz4`, `snappy`, `zstd`, và `gzip` nếu phù hợp) với cùng tốc độ tải và thời gian đủ dài để qua giai đoạn warm-up.
4. Ghi throughput record/s và MB/s, CPU producer/broker/consumer, network bytes, disk bytes, compression metric và p95/p99 latency.
5. Lặp lại ở tải bình thường và tải đỉnh; quan sát cả khi CPU gần giới hạn.
6. Thử điều chỉnh `batch.size`, `linger.ms` hoặc compression level sau khi đã có baseline codec. Chỉ thay đổi một nhóm biến mỗi lần.

Ví dụ bảng ghi kết quả:

| Codec | Records/s | Producer CPU | Consumer CPU | Network MB/s | p99 latency | Ghi chú |
|---|---:|---:|---:|---:|---:|---|
| `none` | đo thực tế | đo thực tế | đo thực tế | đo thực tế | đo thực tế | Baseline |
| `lz4` | đo thực tế | đo thực tế | đo thực tế | đo thực tế | đo thực tế | Ưu tiên tốc độ |
| `snappy` | đo thực tế | đo thực tế | đo thực tế | đo thực tế | đo thực tế | So sánh CPU |
| `zstd` | đo thực tế | đo thực tế | đo thực tế | đo thực tế | đo thực tế | Thử level khác nhau |
| `gzip` | đo thực tế | đo thực tế | đo thực tế | đo thực tế | đo thực tế | Đo chi phí CPU |

Không dùng số liệu benchmark của một payload để suy ra kết quả cho payload khác. Một luồng JSON có nhiều tên trường lặp có thể nén tốt, trong khi payload protobuf nhỏ hoặc nội dung đã nén sẵn có thể cho kết quả khác đáng kể.

## 9. Đọc các dấu hiệu khi production bị áp lực CPU

Các triệu chứng thường gặp cần được đối chiếu với metric:

| Dấu hiệu | Khả năng cần kiểm tra | Hướng điều tra |
|---|---|---|
| Producer CPU tăng, network bytes giảm, throughput không tăng | Codec đang tiêu thụ CPU nhiều hơn phần network tiết kiệm được | So sánh LZ4/Snappy với Zstd/Gzip hoặc `none`; kiểm tra CPU throttling. |
| Producer CPU cao và `record-queue-time-avg` tăng | Producer tạo/gửi batch chậm hoặc broker phản hồi chậm | Đối chiếu CPU producer, request latency, batch size và broker metrics. |
| Broker CPU tăng sau khi đổi codec | Broker có thể đang chuyển đổi codec hoặc chịu tải request lớn hơn | Kiểm tra `compression.type` của topic/broker và codec producer. |
| Consumer CPU tăng, lag tăng dù network fetch bytes giảm | Giải nén hoặc xử lý nghiệp vụ đang giới hạn consumer | Đo CPU consumer, listener latency và codec tương thích. |
| Compression ratio thấp, CPU vẫn tăng | Payload khó nén hoặc batch quá nhỏ | Kiểm tra payload, batch size, records per request và partition count. |
| CPU thấp hơn khi tắt nén nhưng network/disk bão hòa | Hệ thống có thể bị giới hạn bởi I/O | Benchmark LZ4 hoặc Zstd với batch đủ lớn để giảm bytes. |

Khi producer CPU bị throttling, tăng số thread hoặc tăng concurrency không chắc cải thiện được throughput. Nhiều thread có thể làm tranh chấp CPU nặng hơn. Trước tiên xác định phần CPU dành cho serialization, compression, ứng dụng và các tác vụ khác; sau đó điều chỉnh codec, batching hoặc phân bổ tài nguyên.

## 10. Các nguyên tắc cấu hình thực tế

- Bắt đầu bằng codec phù hợp với tải và đo baseline; LZ4 là một lựa chọn thử nghiệm phổ biến cho luồng throughput cao.
- Tăng compression level chỉ khi network/disk cần giảm thêm và CPU còn đủ dư địa.
- Dùng `batch.size` và `linger.ms` để cải thiện batch, nhưng giữ giới hạn latency và bộ nhớ của ứng dụng.
- Kiểm tra codec được hỗ trợ bởi mọi Kafka client trong hệ thống trước khi rollout.
- Kiểm tra broker/topic có giữ codec producer hay đang chuyển đổi sang codec khác.
- Theo dõi CPU riêng ở producer, broker và consumer; không đánh giá chỉ từ network bytes.
- Đo ở tải đỉnh và trong điều kiện CPU limit thực tế, không chỉ benchmark trên máy phát triển.
- Nếu các luồng có payload và yêu cầu khác nhau, cân nhắc cấu hình producer riêng thay vì ép mọi topic dùng chung một codec.

## 11. Ví dụ quyết định chọn codec

Giả sử dịch vụ nhận sự kiện đơn hàng JSON và phát hàng chục nghìn record mỗi giây. Producer pod gần chạm CPU limit, consumer lag đang ổn định và broker network chưa bão hòa. Trong trường hợp này, chuyển từ `none` sang Zstandard level cao có thể làm producer chậm hơn dù request nhỏ đi. Hãy thử LZ4 hoặc Snappy trước, rồi so sánh CPU trên mỗi record và p99 latency.

Ở tình huống khác, producer có CPU dư nhưng broker network và disk throughput đã gần giới hạn. Payload JSON có nhiều tên trường và giá trị lặp. Zstandard có thể giảm byte đáng kể và giúp tăng thông lượng tổng thể; tuy vậy, phải kiểm tra CPU giải nén ở consumer và CPU broker nếu topic buộc chuyển codec.

Nếu payload chủ yếu là ảnh JPEG hoặc nội dung ZIP, bắt đầu với `none` có thể hợp lý hơn vì dữ liệu đã được nén. Chỉ giữ codec khác nếu benchmark cho thấy số byte giảm đủ lớn để bù chi phí CPU.

Chọn `compression.type` bằng số đo của toàn tuyến producer → broker → consumer. Một cấu hình tốt giảm chi phí tổng thể và giữ latency trong giới hạn nghiệp vụ, kể cả khi tải tăng; tỷ lệ nén cao riêng lẻ không phải mục tiêu cuối cùng.
