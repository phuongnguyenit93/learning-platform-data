# Gửi record không có key

Kafka record gồm topic, key, value, timestamp và headers. Trong nhiều luồng messaging, producer có thể gửi record mà không cung cấp key. Với Spring Kafka, cách đơn giản nhất là gọi `KafkaTemplate.send(topic, value)`. Khi key là `null` và producer không chỉ định partition, partitioner sẽ chọn partition đích dựa trên metadata và chính sách phân vùng đang cấu hình.

Gửi record không có key phù hợp với dữ liệu độc lập, không cần giữ thứ tự theo một thực thể nghiệp vụ, chẳng hạn telemetry, metric, log hoặc thông báo có thể xử lý riêng lẻ. Cách gửi này có thể giúp phân phối tải qua nhiều partition và tận dụng batching. Đổi lại, producer không thể dựa vào key để giữ các record liên quan ở cùng partition; Kafka chỉ bảo đảm thứ tự trong từng partition, không bảo đảm thứ tự toàn topic.

Bài học thuộc chương **Producer** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Key trong Kafka record có vai trò gì?

Một record Kafka có thể được mô tả bằng các trường chính:

| Thành phần | Vai trò |
| --- | --- |
| Topic | Luồng dữ liệu logic mà record được gửi vào. |
| Partition | Phân đoạn log nhận record; mỗi partition có thứ tự offset riêng. |
| Key | Giá trị producer có thể dùng để định tuyến record tới partition. |
| Value | Payload nghiệp vụ hoặc dữ liệu cần truyền. |
| Timestamp | Mốc thời gian gắn với record. |
| Headers | Metadata bổ sung như correlation ID, trace ID hoặc loại event. |
| Offset | Vị trí record trong một partition sau khi broker ghi nhận. |

Key thường được dùng để nhóm các record theo thực thể nghiệp vụ. Ví dụ, nếu key là `orderId`, các event của cùng một đơn hàng thường được gửi tới cùng partition theo partitioner mặc định. Consumer có thể đọc các event của đơn hàng đó theo thứ tự offset trong partition.

Khi key là `null`, producer không cung cấp định danh để partitioner băm và định tuyến theo thực thể. Partitioner sẽ chọn partition theo chiến lược của nó. Vì vậy:

- Record không có key vẫn có thể được gửi bình thường.
- Record vẫn được ghi vào một partition cụ thể; Kafka không lưu record bên ngoài partition.
- Các record liên tiếp có thể được ghi vào các partition khác nhau.
- Producer không có bảo đảm affinity theo orderId, customerId hoặc entity nào khác nếu không có key hay partitioner tùy chỉnh.
- Thứ tự toàn cục giữa các record của topic không được bảo đảm.

## 2. Gửi record không có key bằng KafkaTemplate

Spring Kafka cung cấp overload đơn giản để gửi value mà không truyền key:

~~~java
@Service
@RequiredArgsConstructor
public class TelemetryPublisher {

    private static final String TOPIC = "telemetry-events";

    private final KafkaTemplate<String, TelemetryEvent> kafkaTemplate;

    public CompletableFuture<SendResult<String, TelemetryEvent>> publish(
            TelemetryEvent event) {
        return kafkaTemplate.send(TOPIC, event);
    }
}
~~~

Trong ví dụ:

- Topic nhận dữ liệu là `telemetry-events`.
- Value là `TelemetryEvent`.
- Producer không cung cấp key.
- KafkaTemplate dùng producer do ProducerFactory quản lý.
- Serializer của value chuyển object thành byte trước khi gửi.

Kiểu key generic của KafkaTemplate vẫn có thể là `String` dù lần gửi này không có key. Generic type mô tả kiểu key mà template có thể xử lý; nó không buộc mọi record phải có key khác null.

Một event mẫu:

~~~java
public record TelemetryEvent(
    String deviceId,
    double temperature,
    Instant measuredAt
) {}
~~~

Ở ví dụ này, payload có trường `deviceId` nhưng producer không dùng trường đó làm Kafka key. Dữ liệu deviceId vẫn nằm trong value và consumer có thể đọc nó. Tuy nhiên, Kafka partitioner mặc định không tự lấy deviceId bên trong JSON payload để chọn partition.

Đây là điểm cần phân biệt: một field có trong payload không tự động trở thành record key. Muốn partition theo field đó, producer phải truyền field làm key hoặc dùng partitioner tùy chỉnh có khả năng đọc thông tin tương ứng.

## 3. Khai báo key null một cách tường minh

Cách `send(topic, value)` ở trên là rõ ràng nhất khi muốn gửi không key. Nếu cần tạo ProducerRecord trước khi gửi, có thể đặt key là `null`:

~~~java
ProducerRecord<String, TelemetryEvent> record =
    new ProducerRecord<>(
        "telemetry-events",
        null,
        event
    );

kafkaTemplate.send(record);
~~~

Constructor này nhận topic, key và value. Key null thể hiện producer không cung cấp key cho record.

Nếu muốn chỉ định partition nhưng vẫn không có key, có thể tạo ProducerRecord với partition cụ thể:

~~~java
ProducerRecord<String, TelemetryEvent> record =
    new ProducerRecord<>(
        "telemetry-events",
        2,
        null,
        event
    );

kafkaTemplate.send(record);
~~~

Ví dụ trên yêu cầu gửi vào partition số 2 và key vẫn null. Partition được chỉ định phải tồn tại trong topic. Cách này hữu ích khi ứng dụng chủ động điều phối partition, nhưng nó khác với hành vi tự chọn partition của partitioner mặc định.

Không nên chỉ định partition bằng một số cố định cho mọi record nếu chưa có lý do rõ ràng. Cách đó có thể dồn tải vào một partition và làm giảm khả năng song song.

## 4. Producer chọn partition thế nào khi key là null?

Nếu record không có key và producer cũng không chỉ định partition, Kafka partitioner chọn partition đích. Cách lựa chọn phụ thuộc partitioner được cấu hình và phiên bản Kafka client.

### 4.1. Partitioner mặc định và sticky partitioning

Trong các Kafka client hiện đại, partitioner mặc định thường sử dụng sticky partitioning cho record không có key. Thay vì đổi partition ở từng record, producer có xu hướng tiếp tục gửi record không key vào cùng một partition trong một khoảng thời gian hoặc cho đến khi batch của partition đó được gửi. Sau đó partitioner có thể chuyển sang partition khác.

Mục đích là gom các record thành batch lớn hơn. Mỗi batch được gửi hiệu quả hơn so với việc phân tán từng record nhỏ sang nhiều partition ngay lập tức.

Ví dụ minh họa:

~~~text
Topic telemetry-events có 3 partition

Đợt gửi A:
  Event 1 ─┐
  Event 2 ─┼──> Partition 1 (đang gom batch)
  Event 3 ─┤
  Event 4 ─┘

Batch được gửi xong, partitioner chuyển lựa chọn:

Đợt gửi B:
  Event 5 ─┐
  Event 6 ─┼──> Partition 0 (batch tiếp theo)
  Event 7 ─┘

Một đợt gửi sau có thể sử dụng Partition 2.
~~~

Đây chỉ là hình minh họa hành vi sticky, không phải lịch phân phối cố định. Không thể dựa vào sơ đồ để dự đoán event cụ thể sẽ vào partition nào.

Sticky partitioning giúp cải thiện batching khi record không có key và lưu lượng không cao. Tuy nhiên, nó không tạo quan hệ affinity theo nghiệp vụ. Khi partitioner chuyển sang partition khác, các event tiếp theo có thể đi tới partition khác.

Ở các Kafka client cũ hơn hoặc khi dùng custom partitioner, cách chọn partition có thể khác. Một số phiên bản cũ dùng chiến lược phân phối không key khác với sticky partitioning hiện đại. Vì vậy, khi cần hiểu chính xác hành vi, hãy kiểm tra phiên bản Kafka client và thuộc tính `partitioner.class` của producer.

### 4.2. Những yếu tố ảnh hưởng tới lựa chọn partition

Partitioner có thể xem xét:

- Danh sách partition của topic mà client biết qua metadata.
- Partition nào đang có leader khả dụng.
- Trạng thái batch đang được gom theo partition.
- Key của record nếu key không null.
- Partition được ứng dụng chỉ định trực tiếp.
- Thuật toán của partitioner tùy chỉnh nếu có.

Nếu producer chỉ định partition cụ thể, partitioner không cần tự lựa chọn partition theo key. Nếu producer không chỉ định partition và key null, partitioner dùng chiến lược dành cho record không key.

Không nên diễn giải hành vi này thành “Kafka luôn round-robin từng record”. Với sticky partitioning, nhiều record liên tiếp có thể vào cùng partition để gom batch trước khi chuyển sang partition khác.

## 5. Key null khác với key rỗng

Key null và key rỗng là hai trạng thái khác nhau:

| Trường hợp | Ý nghĩa |
| --- | --- |
| Key null | Record không có key. |
| Key là chuỗi rỗng `""` | Record có key dạng String nhưng giá trị rỗng; key được serialize thành dữ liệu byte không null. |
| Key là `"device-01"` | Record có key cụ thể để định tuyến theo partitioner. |

Với key rỗng, partitioner xem đây là key không null. Partitioner mặc định có thể băm key đã serialize để chọn partition. Vì các key rỗng giống nhau, chúng thường được định tuyến về cùng partition trong cùng topology partition.

Không nên thay key null bằng chuỗi rỗng nếu mục tiêu là để partitioner xử lý record như record không key. Hai cách có thể tạo phân phối và semantics khác nhau.

Ví dụ:

~~~java
// Không có key
kafkaTemplate.send("telemetry-events", event);

// Key là chuỗi rỗng
kafkaTemplate.send("telemetry-events", "", event);

// Có key theo thiết bị
kafkaTemplate.send("telemetry-events", event.deviceId(), event);
~~~

Ba lời gọi trên đều gửi cùng kiểu value nhưng có thể tạo hành vi partitioning khác nhau.

## 6. Gửi không key ảnh hưởng thế nào tới thứ tự?

Kafka bảo đảm thứ tự record trong phạm vi một partition. Consumer đọc một partition theo thứ tự offset. Kafka không tạo một thứ tự tổng thể giữa các partition.

Khi producer gửi không key, các record có thể được phân phối sang nhiều partition. Do đó, nếu hai event liên quan được ghi vào hai partition khác nhau, consumer group có thể xử lý chúng song song và không có bảo đảm event nào được quan sát trước trên toàn topic.

Ví dụ, hai event có thể được ghi như sau:

~~~text
Partition 0:
  offset 10: DeviceReported(deviceId=A)
  offset 11: DeviceReported(deviceId=C)

Partition 1:
  offset 20: DeviceReported(deviceId=B)
  offset 21: DeviceReported(deviceId=A)
~~~

Hai event của thiết bị A xuất hiện ở hai partition khác nhau trong ví dụ minh họa. Consumer không thể dựa vào offset để suy ra thứ tự toàn cục giữa offset 10 và offset 21, vì offset chỉ có ý nghĩa bên trong từng partition.

Nếu nghiệp vụ cần xử lý tuần tự theo thiết bị, hãy dùng deviceId làm key hoặc thiết kế partitioning phù hợp. Nếu event độc lập và có thể xử lý theo bất kỳ thứ tự nào, gửi không key có thể phù hợp.

Cũng cần lưu ý rằng sticky partitioning có thể giữ một nhóm record không key trên cùng partition trong một batch, nhưng đây là tối ưu batching chứ không phải bảo đảm thứ tự theo một entity. Đừng dùng hành vi sticky để thay thế key khi nghiệp vụ cần thứ tự.

## 7. Gửi không key có lợi ích gì?

### 7.1. Phù hợp với event độc lập

Một số dữ liệu không cần gom theo thực thể để giữ thứ tự:

- Metric định kỳ từ nhiều nguồn.
- Telemetry hoặc sensor reading có thể xử lý độc lập.
- Log ứng dụng.
- Event thống kê hoặc clickstream.
- Thông báo broadcast không cần thứ tự theo một entity cụ thể.

Trong các trường hợp này, consumer có thể xử lý mỗi record độc lập, dùng timestamp hoặc eventId trong payload để phân tích mà không yêu cầu Kafka key.

### 7.2. Có thể phân phối tải qua nhiều partition

Khi không có key, partitioner mặc định có thể phân phối các batch qua nhiều partition. Điều này tránh một key nóng duy nhất làm dồn mọi record vào cùng partition.

Tuy nhiên, không có key không bảo đảm phân phối hoàn toàn đồng đều ở mọi thời điểm. Sticky partitioning giữ record trên một partition trong một khoảng thời gian để batching; lưu lượng, metadata, số partition và partitioner đều ảnh hưởng phân phối tổng thể.

Nếu hệ thống có một producer lưu lượng thấp, một số batch có thể tập trung ở một partition trong thời gian ngắn. Khi cần phân phối tải ổn định hơn, phải đo trên workload thực tế thay vì giả định mọi record sẽ được round-robin.

### 7.3. Tận dụng batching và giảm overhead

Kafka producer gom record thành batch theo partition. Khi các record không key được sticky vào cùng partition, batch có thể đầy hơn trước khi gửi. Điều này giúp giảm số request nhỏ, tận dụng compression và tăng throughput.

Các cấu hình liên quan gồm:

- `batch.size`: kích thước batch mục tiêu theo partition.
- `linger.ms`: thời gian producer chờ thêm record để gom batch.
- `compression.type`: thuật toán nén batch.
- `buffer.memory`: bộ nhớ producer dành cho các record chờ gửi.

Không nên tăng linger hoặc batch size quá mức nếu ứng dụng nhạy với độ trễ. Tối ưu cần cân bằng latency, throughput, CPU và bộ nhớ.

## 8. Khi nào không nên gửi record không key?

Không key không phù hợp khi hệ thống cần Kafka định tuyến các event liên quan vào cùng partition.

Ví dụ:

- Các event thay đổi trạng thái cùng một order phải được xử lý theo thứ tự.
- Các giao dịch của một account phải được xử lý tuần tự theo accountId.
- Các thay đổi inventory cùng một SKU phải giữ thứ tự cập nhật.
- Consumer dùng partition ownership để serialize xử lý theo entity.

Nếu bỏ key trong các tình huống này, các event cùng entity có thể đi sang nhiều partition. Consumer có thể nhận chúng trên các thread khác nhau, khiến logic phụ thuộc thứ tự bị sai.

Có thể dùng một key nghiệp vụ ổn định như `orderId`, `accountId` hoặc `sku`:

~~~java
kafkaTemplate.send(
    "order-events",
    event.orderId(),
    event
);
~~~

Khi dùng key, các record có cùng key thường được định tuyến vào cùng partition theo partitioner mặc định. Đây là cơ sở để giữ thứ tự trong phạm vi key, nhưng vẫn cần lưu ý việc thay đổi số partition, custom partitioner và xử lý bất đồng bộ phía consumer.

Nếu không thể dùng một key đơn giản, hãy thiết kế partition key hoặc partitioner theo yêu cầu nghiệp vụ. Headers hoặc field nằm trong JSON value không tự động tham gia partitioning mặc định.

## 9. Consumer nhận record không key

Consumer vẫn đọc record bình thường dù key null. Listener có thể nhận payload trực tiếp nếu chỉ cần xử lý value:

~~~java
@Component
public class TelemetryListener {

    @KafkaListener(
        topics = "telemetry-events",
        groupId = "telemetry-processor"
    )
    public void onTelemetry(TelemetryEvent event) {
        telemetryService.process(event);
    }
}
~~~

Nếu cần kiểm tra key và metadata, listener có thể nhận `ConsumerRecord`:

~~~java
@Component
public class TelemetryListener {

    @KafkaListener(
        topics = "telemetry-events",
        groupId = "telemetry-audit"
    )
    public void onTelemetry(
            ConsumerRecord<String, TelemetryEvent> record) {

        if (record.key() == null) {
            log.debug(
                "Record không có key: topic={} partition={} offset={}",
                record.topic(),
                record.partition(),
                record.offset()
            );
        }

        telemetryService.process(record.value());
    }
}
~~~

Consumer có thể quan sát topic, partition, offset, timestamp, headers và key. Khi key null, `record.key()` trả về null; payload vẫn có thể chứa deviceId hoặc business identifier riêng.

Consumer group vẫn phân phối partition cho các consumer theo cơ chế bình thường. Record không key không làm thay đổi cách commit offset hoặc cách group coordinator quản lý membership.

## 10. Concurrency và khả năng mở rộng consumer

Giả sử topic có bốn partition và consumer group có hai consumer. Kafka có thể gán hai partition cho mỗi consumer. Các record không key được ghi vào những partition đó sẽ được consumer tương ứng đọc.

~~~text
Topic telemetry-events
  Partition 0 ──┐
  Partition 1 ──┼──> Consumer A (group telemetry-processor)
  Partition 2 ──┐
  Partition 3 ──┴──> Consumer B (group telemetry-processor)
~~~

Sơ đồ chỉ minh họa một assignment có thể xảy ra. Assignment thực tế phụ thuộc partition assignor và trạng thái consumer group.

Với Spring Kafka, có thể tăng concurrency của listener container:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, TelemetryEvent>
        telemetryListenerContainerFactory(
            ConsumerFactory<String, TelemetryEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, TelemetryEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    return factory;
}
~~~

Khi listener dùng factory này, Spring Kafka tạo nhiều consumer thuộc cùng group. Tuy nhiên, concurrency hữu ích không vượt số partition được gán cho group. Nếu topic có hai partition mà concurrency là sáu, tối đa hai consumer có partition để đọc tại một thời điểm.

Gửi không key có thể hỗ trợ tải được phân tán qua partition, nhưng throughput vẫn phụ thuộc số partition, năng lực broker, tốc độ producer và thời gian xử lý của consumer.

## 11. Record không key trên topic compacted

Log compaction sử dụng key để giữ trạng thái mới nhất theo từng key. Vì vậy, record không key không thể đại diện cho trạng thái mới nhất của một entity theo cơ chế compaction thông thường.

Một tombstone trong compacted topic là record có key khác null và value null. Tombstone đánh dấu key tương ứng cần bị loại bỏ khi compaction xử lý.

Cần phân biệt:

| Record | Ý nghĩa trong compacted topic |
| --- | --- |
| Key null, value khác null | Không có key để compaction nhóm theo entity. |
| Key khác null, value khác null | Một phiên bản dữ liệu cho key đó. |
| Key khác null, value null | Tombstone cho key tương ứng. |
| Key null, value null | Không phải tombstone cho một key nghiệp vụ cụ thể. |

Nếu topic được thiết kế để lưu trạng thái mới nhất theo accountId hoặc deviceId, producer cần gửi key tương ứng. Gửi không key phù hợp hơn với event log thông thường, nơi mỗi record là một sự kiện độc lập và retention được quản lý theo thời gian/dung lượng.

## 12. Theo dõi partition thực tế của record

Không nên giả định partition dựa trên thứ tự gọi send. Hãy đọc metadata trả về khi gửi thành công:

~~~java
public void publishAndLog(TelemetryEvent event) {
    kafkaTemplate.send("telemetry-events", event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Gửi telemetry thất bại", exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "topic={} partition={} offset={} timestamp={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset(),
                metadata.timestamp()
            );
        });
}
~~~

Metadata cho biết record đã được ghi vào topic, partition và offset nào theo kết quả gửi. Đây là bằng chứng tốt hơn việc đoán partition theo vòng lặp hoặc theo một quy tắc không được đảm bảo.

Có thể kiểm tra topic bằng Kafka CLI:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic telemetry-events
~~~

Lệnh describe cho biết số partition và leader/replica. Muốn quan sát record thực tế, có thể dùng console consumer hoặc công cụ quản trị có khả năng hiển thị key, partition và offset.

Khi đọc record bằng console consumer, cần bật hiển thị key nếu muốn xác nhận key null. Hãy phân biệt giá trị key null với chuỗi rỗng; cách hiển thị phụ thuộc công cụ.

## 13. Kiểm thử producer gửi không key

Một kiểm thử tích hợp nên xác nhận:

1. Producer gửi record tới đúng topic.
2. Key của record là null.
3. Value được serialize đúng.
4. Record được ghi vào một partition hợp lệ.
5. Consumer đọc được payload.
6. Consumer có thể quan sát partition và offset.
7. Không có giả định sai về thứ tự giữa nhiều partition.

Ví dụ kiểm tra metadata gửi:

~~~java
@Test
void shouldPublishTelemetryWithoutKey() throws Exception {
    TelemetryEvent event = new TelemetryEvent(
        "device-01",
        25.4,
        Instant.now()
    );

    SendResult<String, TelemetryEvent> result =
        kafkaTemplate.send("telemetry-events", event)
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getProducerRecord().key()).isNull();
    assertThat(result.getProducerRecord().value()).isEqualTo(event);
    assertThat(result.getRecordMetadata().topic())
        .isEqualTo("telemetry-events");
    assertThat(result.getRecordMetadata().partition())
        .isGreaterThanOrEqualTo(0);
}
~~~

Đoạn test minh họa API của Spring Kafka 3.x, trong đó SendResult cung cấp ProducerRecord và RecordMetadata. Với phiên bản Spring Kafka khác, cần kiểm tra API tương ứng.

Để kiểm thử end-to-end, có thể dùng Embedded Kafka hoặc Testcontainers. Consumer test nên đọc record từ topic và xác nhận payload. Nếu muốn kiểm tra key null ở phía consumer, hãy nhận ConsumerRecord và assert `record.key()` là null.

Không nên viết test yêu cầu một record không key luôn vào partition 0 hoặc yêu cầu nhiều record được phân phối theo đúng một chu kỳ round-robin. Hành vi partitioning phụ thuộc partitioner, metadata, batch và phiên bản Kafka client. Test nên kiểm tra các bảo đảm thực sự: key null, topic đúng, partition hợp lệ và payload chính xác.

## 14. Các lỗi và nhầm lẫn thường gặp

| Nhầm lẫn hoặc lỗi | Cách hiểu/điều tra |
| --- | --- |
| Không truyền key thì record không có partition. | Mọi record được ghi đều thuộc một partition; partitioner chọn partition nếu ứng dụng không chỉ định. |
| Kafka round-robin từng record khi key null. | Partitioner mặc định hiện đại thường dùng sticky partitioning; hành vi còn tùy phiên bản và cấu hình. |
| Các record không key luôn vào cùng một partition. | Sticky partitioning chỉ giữ partition trong một khoảng/batch; sau đó có thể đổi partition. |
| Field deviceId trong JSON tự trở thành key. | Partitioner mặc định chỉ nhận record key, không tự đọc field trong value. |
| Key rỗng tương đương key null. | Key rỗng là key không null và có thể được băm để chọn partition. |
| Không key vẫn bảo đảm thứ tự theo entity. | Không có affinity theo entity; các record liên quan có thể nằm ở nhiều partition. |
| Không key luôn phân phối đồng đều. | Phân phối phụ thuộc sticky behavior, partition availability, tải và partitioner. |
| Record không key có thể dùng làm tombstone cho một entity. | Tombstone cần key khác null và value null. |
| Tăng consumer concurrency luôn tăng throughput. | Số partition và năng lực xử lý giới hạn mức song song hữu ích. |
| Producer send thành công nghĩa consumer đã xử lý. | SendResult chỉ phản ánh kết quả gửi theo acknowledgement; consumer xử lý và commit độc lập. |

## 15. Checklist quyết định có gửi không key hay không

Trước khi chọn gửi record không key, hãy trả lời:

1. Các record có độc lập với nhau về mặt nghiệp vụ không?
2. Có cần giữ thứ tự theo orderId, accountId, deviceId hoặc một entity nào không?
3. Consumer có thể xử lý record từ nhiều partition song song không?
4. Topic có đủ partition cho throughput và concurrency mong muốn không?
5. Partitioner mặc định có phù hợp hay cần chỉ định partition/custom partitioner?
6. Có cần log lại partition và offset để truy vết không?
7. Topic có dùng log compaction hay cần tombstone theo key không?
8. Producer và consumer có xử lý duplicate/idempotency phù hợp không?
9. Test có xác nhận key thực sự null mà không giả định partition cố định không?
10. Hệ thống có metric để quan sát phân phối partition và consumer lag không?

Gửi record không có key là một lựa chọn hợp lệ khi mỗi event có thể được xử lý độc lập và không cần định tuyến theo thực thể. Cách này cho phép partitioner tối ưu việc phân phối và batching, nhưng ứng dụng phải chấp nhận rằng thứ tự chỉ tồn tại trong từng partition và không có bảo đảm affinity theo entity. Khi nghiệp vụ cần tuần tự theo một thực thể, hãy truyền key ổn định hoặc thiết kế partitioner có chủ đích.

