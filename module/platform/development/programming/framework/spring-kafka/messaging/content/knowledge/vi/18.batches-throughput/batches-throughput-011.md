# Đánh đổi latency với throughput

Khi xây dựng luồng messaging bằng Spring Kafka, một producer có thể gửi từng record ngay khi có sự kiện hoặc gom nhiều record thành batch trước khi gửi. Consumer cũng có thể lấy từng record hoặc xử lý nhiều record trong một lần `poll()`. Gom batch thường giảm số request, tận dụng network và compression tốt hơn, từ đó tăng throughput. Đổi lại, ứng dụng có thể phải chờ đủ dữ liệu hoặc hết thời gian gom batch, làm tăng latency.

Không có một cấu hình tối ưu cho mọi hệ thống. Luồng thông báo cần phản hồi nhanh thường ưu tiên latency thấp; luồng đồng bộ dữ liệu hoặc analytics thường ưu tiên throughput và hiệu quả tài nguyên. Muốn chọn đúng, cần nhìn cả producer, broker, consumer và hệ thống nghiệp vụ phía sau.

## 1. Phân biệt latency và throughput

Hai chỉ số mô tả hai khía cạnh khác nhau:

- **Latency** là thời gian một record đi từ mốc bắt đầu đến mốc kết thúc mà bạn quan tâm. Ví dụ, từ lúc producer gửi event đến lúc consumer hoàn tất xử lý.
- **Throughput** là lượng công việc hoàn thành trong một đơn vị thời gian, ví dụ record/giây hoặc MB/giây.

Một hệ thống có thể có throughput cao nhưng mỗi record phải chờ lâu trong batch hoặc queue. Ngược lại, một hệ thống gửi ngay từng record có thể cho latency thấp khi tải nhẹ nhưng tốn nhiều request và CPU khi tải lớn.

Khi đo latency, không chỉ xem giá trị trung bình. Hãy theo dõi p50, p95 và p99 để nhận ra một phần record bị chậm do batch wait, broker, network, retry hoặc dependency. Throughput cũng nên được đo ở nhiều điểm: producer gửi thành công, consumer đọc được và nghiệp vụ xử lý hoàn tất.

| Chỉ số | Câu hỏi trả lời |
|---|---|
| Producer latency | Producer mất bao lâu từ `send()` đến broker xác nhận? |
| End-to-end latency | Một sự kiện mất bao lâu từ lúc phát sinh đến khi consumer hoàn tất? |
| Records/sec | Có bao nhiêu record được gửi/đọc/xử lý mỗi giây? |
| Bytes/sec | Lượng dữ liệu thực tế truyền hoặc xử lý mỗi giây là bao nhiêu? |
| p95/p99 latency | Những record chậm nhất trong phân bố có mất bao lâu? |

Phải thống nhất mốc đo trước khi so sánh. Ví dụ, thời gian future của `KafkaTemplate.send()` hoàn tất không bao gồm thời gian consumer xử lý nghiệp vụ.

## 2. Producer batching hoạt động như thế nào?

Kafka producer không nhất thiết gửi một request riêng cho mỗi record. Producer gom record thành batch theo partition đích. Khi batch đủ lớn hoặc hết thời gian chờ, producer gửi batch tới broker.

Hai cấu hình quan trọng là:

- `batch.size`: dung lượng mục tiêu của batch cho mỗi partition, tính bằng byte.
- `linger.ms`: thời gian tối đa producer chờ để gom thêm record vào batch trước khi gửi, nếu batch chưa đầy.

Nếu batch đạt dung lượng trước khi hết `linger.ms`, producer có thể gửi ngay. Nếu lưu lượng thấp và batch chưa đầy, producer gửi khi hết thời gian chờ. Vì vậy, `linger.ms` có thể làm tăng latency ở tải thấp nhưng giúp batch đầy hơn khi có nhiều record đến gần nhau.

```text
Record A ----+
Record B ----+----> Batch cho partition 0 ----+
Record C ----+                               |
                                              +--> Produce request --> Broker
Record D --------> Batch cho partition 1 ---+

Batch được gửi khi đầy hoặc khi hết linger.ms.
```

Batch được tổ chức riêng theo partition. Nếu producer gửi tới nhiều partition nhưng mỗi partition chỉ nhận rất ít record, nhiều batch có thể không đầy dù tổng lưu lượng toàn topic khá lớn. Đây là lý do phân bố key và số partition ảnh hưởng tới hiệu quả batching.

### `batch.size` không phải giới hạn kích thước record

`batch.size` xác định dung lượng producer cố gắng dành cho batch của mỗi partition. Nó không phải giới hạn cứng cho kích thước một record. Record quá lớn so với batch có thể được gửi trong batch riêng; kích thước record/batch tối đa vẫn chịu các giới hạn producer, broker và topic như `max.request.size`, `message.max.bytes` hoặc `max.message.bytes` tùy cấu hình.

Tăng `batch.size` có thể giúp gom được nhiều record hơn, nhưng cũng làm tăng bộ nhớ dành cho buffer khi có nhiều partition hoạt động. Nếu lưu lượng thấp, batch lớn không tự động tạo thêm throughput; record vẫn có thể được gửi khi hết `linger.ms` với batch chưa đầy.

## 3. Điều chỉnh `linger.ms` và `batch.size`

Ví dụ cấu hình producer trong Spring Boot:

```yaml
spring:
  kafka:
    producer:
      batch-size: 32768
      properties:
        "[linger.ms]": 5
```

Trong ví dụ, producer dành batch mục tiêu 32 KiB cho mỗi partition và chờ tối đa khoảng 5 ms để gom thêm record khi batch chưa đầy. Đây là điểm bắt đầu để thử nghiệm, không phải cấu hình tối ưu cho mọi tải.

| Cấu hình | Tác động thường thấy khi tăng |
|---|---|
| `linger.ms` | Batch có cơ hội đầy hơn, giảm số request; latency ở tải thấp có thể tăng |
| `batch.size` | Batch có thể chứa nhiều byte hơn; tăng nhu cầu buffer và có thể không có ích nếu lưu lượng mỗi partition thấp |

Không nên đặt `linger.ms` quá cao chỉ để tăng batch utilization. Nếu SLA yêu cầu p99 dưới một ngưỡng chặt, thời gian chờ gom batch có thể chiếm phần lớn ngân sách latency ở tải thấp.

## 4. Compression và các cấu hình producer liên quan

Compression được áp dụng trên batch, nên batch lớn hơn thường giúp compression hiệu quả hơn. Kafka hỗ trợ các codec phổ biến như `none`, `gzip`, `snappy`, `lz4` và `zstd` tùy phiên bản broker/client.

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      properties:
        "[linger.ms]": 5
        "[compression.type]": lz4
        "[enable.idempotence]": true
```

| Codec | Đặc điểm tổng quát |
|---|---|
| `none` | Không nén; giảm CPU nhưng truyền nhiều byte hơn |
| `gzip` | Tỷ lệ nén thường tốt, đổi lại tốn CPU hơn |
| `snappy` | Ưu tiên tốc độ nén/giải nén, tỷ lệ nén vừa phải |
| `lz4` | Thường cân bằng tốt giữa tốc độ và tỷ lệ nén |
| `zstd` | Có thể đạt tỷ lệ nén tốt, cần đánh giá chi phí CPU theo mức nén và môi trường |

Chọn codec bằng cách đo CPU, network bytes và latency trên payload thật. JSON lặp nhiều field thường nén tốt hơn dữ liệu đã nén hoặc dữ liệu ngẫu nhiên. Nén không làm giảm số record và cũng không thay thế việc thiết kế payload hợp lý.

Các cấu hình khác cũng ảnh hưởng đến latency và độ tin cậy:

- `acks=all` chờ xác nhận từ các replica trong ISR theo chính sách Kafka; có thể tăng thời gian xác nhận nhưng tăng mức bảo đảm ghi.
- `enable.idempotence=true` giúp producer tránh duplicate do retry ở phạm vi đảm bảo của Kafka producer; cần giữ các cấu hình tương thích.
- `max.in.flight.requests.per.connection` ảnh hưởng số request đang chờ xác nhận trên một connection. Khi bật idempotence, hãy tuân theo giới hạn tương thích của phiên bản Kafka client.
- `buffer.memory` là dung lượng buffer producer dành cho record chưa được gửi. Khi buffer đầy, `send()` có thể phải chờ tối đa theo `max.block.ms`.
- `delivery.timeout.ms` giới hạn tổng thời gian producer cố gắng hoàn tất việc gửi trước khi báo lỗi; cần phối hợp với `request.timeout.ms` và retry settings.

Đừng giảm độ tin cậy của producer chỉ để cải thiện một con số latency mà không đánh giá rủi ro mất hoặc lặp dữ liệu.

## 5. Gửi bất đồng bộ bằng KafkaTemplate

`KafkaTemplate.send()` gửi record theo cơ chế bất đồng bộ và trả về future. Nếu ứng dụng chờ kết quả ngay sau mỗi lần gửi, lợi ích của batching và nhiều request đồng thời có thể giảm đáng kể.

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId,
            String payload
    ) {
        return kafkaTemplate.send("orders.events", orderId, payload);
    }
}
```

Caller có thể tiếp tục công việc khác và gắn callback để xử lý kết quả:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;

class OrderSendObserver {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSendObserver.class);

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderSendObserver(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void observe(String orderId, String payload) {
        kafkaTemplate.send("orders.events", orderId, payload)
                .whenComplete((result, error) -> {
                    if (error != null) {
                        log.error("Send order event failed: orderId={}", orderId, error);
                        return;
                    }

                    var metadata = result.getRecordMetadata();
                    log.debug(
                            "Sent order event: topic={}, partition={}, offset={}",
                            metadata.topic(), metadata.partition(), metadata.offset()
                    );
                });
    }
}
```

Ví dụ dùng API future của Spring Kafka 3.x. Với phiên bản cũ hơn, kiểu future và callback có thể khác. Không gọi `flush()` sau từng record trong luồng gửi thông thường: thao tác này buộc producer đẩy các record đang chờ và có thể phá hiệu quả gom batch. Chỉ flush tại ranh giới phù hợp, chẳng hạn trước khi đóng producer hoặc khi ứng dụng thực sự cần đẩy các record đang buffer.

Nếu nghiệp vụ cần xác nhận gửi thành công trước khi trả response, có thể chờ future ở ranh giới đó. Nhưng cần cân nhắc latency của request và tránh biến mọi lần gửi thành thao tác đồng bộ không cần thiết.

## 6. Consumer fetch batching và `max.poll.records`

Ở phía consumer cũng có hai giai đoạn riêng: Kafka client fetch dữ liệu theo byte từ broker, sau đó `poll()` trả record cho ứng dụng. Một số cấu hình quan trọng:

| Thuộc tính | Vai trò |
|---|---|
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu consumer mong muốn nhận từ broker trước khi broker trả fetch response, nếu có thể chờ |
| `fetch.max.wait.ms` | Thời gian tối đa broker chờ để đáp ứng `fetch.min.bytes` |
| `fetch.max.bytes` | Giới hạn tổng byte cho một fetch response, có ngoại lệ để bảo đảm consumer có thể tiến lên với batch đầu tiên |
| `max.partition.fetch.bytes` | Giới hạn byte fetch thông thường cho mỗi partition |
| `max.poll.records` | Số record tối đa trả về cho ứng dụng trong một lần `poll()` |

`fetch.min.bytes` và `fetch.max.wait.ms` ảnh hưởng việc broker gom dữ liệu trước khi trả response. `max.poll.records` giới hạn số record mà ứng dụng nhận từ một poll; nó không phải giới hạn byte và không đồng nghĩa với fetch batch size.

Ví dụ cấu hình consumer:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      max-poll-records: 200
      properties:
        "[fetch.min.bytes]": 32768
        "[fetch.max.wait.ms]": 20
```

Với lưu lượng cao, `fetch.min.bytes` có thể giúp giảm số fetch request bằng cách đợi thêm dữ liệu. Với lưu lượng thấp, broker có thể chờ tới `fetch.max.wait.ms` trước khi trả dữ liệu, làm tăng latency. Hãy chọn giá trị phù hợp với SLA và lưu lượng thực tế.

## 7. Record listener và batch listener

Spring Kafka hỗ trợ hai kiểu nhận record phổ biến:

- **Record listener:** container gọi phương thức listener cho từng record. Kafka client vẫn có thể lấy nhiều record trong một lần poll, nhưng ứng dụng xử lý callback từng record.
- **Batch listener:** container chuyển danh sách record từ một lần poll cho listener để xử lý theo nhóm.

Batch listener có thể giảm overhead gọi phương thức và tận dụng thao tác bulk ở database hoặc dịch vụ đích.

```java
import java.util.stream.Collectors;
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderBatchListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consume(List<ConsumerRecord<String, String>> records) {
        var orders = records.stream()
                .map(ConsumerRecord::value)
                .collect(Collectors.toList());

        bulkUpdate(orders);
    }

    private void bulkUpdate(List<String> orders) {
        // Ghi nhiều sự kiện bằng một thao tác bulk phù hợp.
    }
}
```

Factory được cấu hình ở chế độ batch:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class BatchListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        return factory;
    }
}
```

Kích thước batch thực tế có thể nhỏ hơn `max.poll.records` vì lượng dữ liệu sẵn sàng, partition assignment và giới hạn fetch. Một batch cũng có thể chứa record từ nhiều partition; Kafka chỉ bảo đảm thứ tự trong từng partition, không tạo thứ tự toàn cục cho cả danh sách.

## 8. Kích thước poll, concurrency và thời gian xử lý

Tăng `max.poll.records` có thể giúp consumer xử lý nhiều record hơn trong một chu kỳ, nhưng thời gian xử lý lô cũng tăng. Nếu listener xử lý đồng bộ, consumer phải gọi `poll()` tiếp theo trước khi vượt `max.poll.interval.ms`; nếu không, Kafka có thể xem consumer không còn tiến triển và kích hoạt rebalance.

Ước lượng ban đầu cho batch xử lý tuần tự:

\[
T_{batch} \approx N \times T_{record} + T_{overhead}
\]

Trong đó `N` là số record thực tế trong batch, `T_record` là thời gian xử lý một record và `T_overhead` là thời gian phụ như bulk operation, deserialize hoặc commit. Dùng percentile cao của thời gian xử lý để kiểm tra khoảng an toàn so với `max.poll.interval.ms`, không chỉ dùng giá trị trung bình.

Concurrency của listener tạo nhiều consumer trong cùng group, nhưng khả năng xử lý song song còn bị giới hạn bởi số partition được gán. Nếu topic có bốn partition, tăng concurrency từ bốn lên tám không tạo ra tám consumer cùng đọc dữ liệu của topic đó; một số consumer có thể không được gán partition.

Tăng concurrency có thể cải thiện throughput khi partition và hệ thống đích còn khả năng xử lý. Nếu database đã bão hòa, tăng consumer chỉ làm tăng số request cạnh tranh, lock, connection và latency.

## 9. Các yếu tố khác làm thay đổi latency và throughput

Batching chỉ là một phần của toàn bộ đường đi:

| Yếu tố | Tác động cần xem xét |
|---|---|
| Số partition | Tăng khả năng phân phối tải, nhưng quá nhiều partition có thể tăng overhead và làm batch theo partition thưa hơn |
| Phân bố key | Key lệch có thể tạo hot partition; một partition quá tải giới hạn throughput của luồng key đó |
| Payload size | Payload lớn tăng network, memory và chi phí serialize/deserialize |
| Compression | Giảm byte truyền nhưng tiêu tốn CPU |
| Replication và `acks` | Mức xác nhận ghi ảnh hưởng độ bền dữ liệu và latency producer |
| Broker/network | Disk, network, request queue và ISR có thể trở thành nút thắt |
| Consumer processing | Database, HTTP call, lock và CPU có thể giới hạn tốc độ xử lý |
| Retry | Backoff và lỗi lặp làm tăng latency và giảm throughput hữu ích |

Khi một partition có key nóng, tăng `batch.size` hoặc concurrency không giải quyết được mất cân bằng key. Cần xem xét key strategy, partition count và khả năng chia nhỏ thực thể nếu nghiệp vụ cho phép.

## 10. Chọn cấu hình theo mục tiêu

Các cấu hình dưới đây là điểm bắt đầu để benchmark. Chúng không phải giá trị mặc định hoặc khuyến nghị cố định; cần điều chỉnh theo kích thước payload, số partition, phần cứng, phiên bản Kafka và SLA.

| Mục tiêu | Producer gợi ý | Consumer gợi ý | Đánh đổi |
|---|---|---|---|
| Ưu tiên latency thấp | `linger.ms` rất thấp; batch vừa; compression tắt hoặc nhanh | `fetch.min.bytes` thấp; `fetch.max.wait.ms` thấp; poll batch vừa | Nhiều request hơn và throughput có thể thấp hơn |
| Cân bằng | `linger.ms` vài ms; batch vừa; thử `lz4` | Fetch wait ngắn; `max.poll.records` vừa; batch listener nếu phù hợp | Cân bằng giữa độ trễ và hiệu quả tài nguyên |
| Ưu tiên throughput | `linger.ms` cao hơn; batch lớn hơn; thử `lz4`/`zstd` | `fetch.min.bytes` cao hơn; poll batch lớn; xử lý bulk | Tăng thời gian chờ, bộ nhớ và thời gian xử lý một poll |

Ví dụ một profile cân bằng để bắt đầu đo:

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      properties:
        "[linger.ms]": 5
        "[compression.type]": lz4
        "[enable.idempotence]": true
    consumer:
      max-poll-records: 200
      properties:
        "[fetch.min.bytes]": 16384
        "[fetch.max.wait.ms]": 10
```

Profile này chỉ minh họa cách nhóm các cấu hình có liên quan. Trước khi dùng production, phải xác nhận `max.poll.interval.ms` đủ cho thời gian xử lý batch, kiểm tra `acks`/replication theo yêu cầu độ bền và đo p95/p99 dưới tải đại diện.

## 11. Quy trình benchmark và tuning

Để biết thay đổi có thực sự cải thiện hệ thống, hãy giữ nguyên workload và thay từng nhóm cấu hình có kiểm soát:

1. **Tạo baseline:** ghi lại payload size, số partition, producer/consumer concurrency, records/sec, bytes/sec và p50/p95/p99 latency.
2. **Đo producer:** theo dõi send latency, batch size thực tế, request rate, compression ratio, buffer availability, retry và error rate.
3. **Đo consumer:** theo dõi fetch latency, records-consumed-rate, records-lag-max, thời gian xử lý listener, commit latency và rebalance.
4. **Thử `linger.ms`:** tăng từng bước nhỏ và quan sát batch utilization so với latency ở tải thấp và tải cao.
5. **Thử `batch.size` và compression:** kiểm tra network bytes, CPU, memory và số request; không chỉ nhìn throughput.
6. **Thử fetch và `max.poll.records`:** tăng dần kích thước poll, kiểm tra thời gian xử lý batch so với `max.poll.interval.ms`.
7. **Thử concurrency:** chỉ tăng khi có đủ partition và dependency phía sau còn capacity.
8. **Kiểm tra tải đỉnh và lỗi:** mô phỏng burst, broker chậm, database chậm và retry để xem p99 cùng consumer lag có ổn định không.
9. **Chọn cấu hình theo SLO:** ưu tiên mức throughput đạt yêu cầu trong khi p95/p99, error rate và lag vẫn nằm trong giới hạn.

Mỗi lần thử nên chạy đủ lâu để hệ thống đạt trạng thái ổn định. Đo cả giai đoạn tải thấp vì đó là lúc `linger.ms` và `fetch.max.wait.ms` thường thể hiện rõ chi phí chờ.

## 12. Những nhầm lẫn thường gặp

1. **Cho rằng batch càng lớn thì luôn càng nhanh.** Batch lớn có thể tăng latency, bộ nhớ và thời gian xử lý mỗi poll.
2. **Cho rằng `linger.ms` là thời gian chờ cố định cho mọi record.** Batch có thể được gửi sớm khi đầy; linger là thời gian chờ tối đa để gom thêm dữ liệu.
3. **Cho rằng `batch.size` là giới hạn cứng của một record.** Nó là dung lượng mục tiêu cho batch theo partition; giới hạn record/message là cấu hình khác.
4. **Gọi `flush()` sau từng `KafkaTemplate.send()`.** Làm vậy thường phá hiệu quả batching và khiến luồng gửi chờ nhiều hơn.
5. **Nhầm `max.poll.records` với fetch byte limit.** Một cấu hình đếm record, các cấu hình fetch điều tiết dữ liệu theo byte và thời gian.
6. **Tăng concurrency vượt số partition rồi kỳ vọng throughput tăng tương ứng.** Consumer dư có thể không nhận partition.
7. **Chỉ đo throughput trung bình.** p95/p99 có thể xấu đi dù records/sec tăng.
8. **Tăng batch mà bỏ qua `max.poll.interval.ms`.** Listener có thể xử lý quá lâu và gây rebalance.
9. **Giảm `acks` hoặc tắt idempotence chỉ để giảm latency.** Cần đánh giá rõ tác động tới độ bền và khả năng xử lý retry.
10. **Chỉ tối ưu producer.** Consumer, partition skew, broker, network và database đều có thể là nút thắt.

Đánh đổi latency với throughput là quyết định end-to-end. Producer batching, compression, fetch batching và batch listener có thể tăng hiệu quả xử lý, nhưng mỗi lớp đều có thể thêm thời gian chờ hoặc tăng lượng công việc trong một chu kỳ. Hãy đo p95/p99 cùng throughput, lag và tài nguyên dưới tải thực tế, rồi chọn cấu hình đáp ứng SLA của nghiệp vụ thay vì tối đa hóa một chỉ số riêng lẻ.
