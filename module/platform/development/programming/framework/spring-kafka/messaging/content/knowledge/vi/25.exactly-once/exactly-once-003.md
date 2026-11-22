# Idempotent producer trong Kafka và Spring Kafka

Idempotent producer giúp Kafka tránh ghi trùng một batch khi producer phải gửi lại request do timeout, mất kết nối hoặc broker phản hồi không rõ ràng. Kafka nhận diện lần gửi lại bằng producer ID và sequence number, nhờ đó retry nội bộ của cùng producer không tạo thêm bản ghi trùng trong log.

Trong Spring Kafka, KafkaTemplate sử dụng Kafka producer của ProducerFactory. Vì vậy, idempotence được cấu hình ở Kafka producer client; đây không phải một chế độ deduplication riêng của listener hoặc một phương thức đặc biệt của KafkaTemplate.

Điều cần nhớ là idempotent producer bảo vệ retry nội bộ trong cùng producer session. Nó không tự loại bỏ hai lần gọi send() độc lập cho cùng event, không deduplicate giữa nhiều producer instance và không làm cho side effect ở database/API trở thành exactly-once.

## 1. Vấn đề duplicate khi producer retry

Giả sử producer gửi một batch tới broker:

1. Broker ghi batch vào log.
2. Broker gửi response xác nhận.
3. Response bị mất trên đường mạng.
4. Producer không biết broker đã ghi thành công hay chưa.
5. Producer gửi lại batch vì request timeout.

Nếu broker không nhận diện được đây là cùng một lần gửi, batch có thể được append lần thứ hai. Đây là duplicate do retry ở tầng transport.

```text
Producer                    Broker
   |                           |
   |------ batch A ----------->|
   |                           | append A
   |<----- response -----------X  response bị mất
   |                           |
   |------ retry batch A ----->|
   |                           | nhận diện PID + sequence
   |<----- response -----------|
```

Với idempotence, broker theo dõi sequence của producer cho từng partition. Khi nhận lại batch có sequence đã được ghi nhận, broker nhận diện đó là retry của batch cũ và không append thêm bản sao.

Nếu không bật idempotence, producer vẫn có thể retry theo cấu hình retries, nhưng trong tình huống response bị mất sau khi broker append, ứng dụng có nguy cơ nhận duplicate trong topic.

## 2. Producer ID và sequence number

Kafka sử dụng hai thông tin chính để nhận diện batch được gửi từ một producer:

- **Producer ID (PID):** định danh producer do Kafka cấp khi producer khởi tạo cơ chế idempotence.
- **Sequence number:** số thứ tự batch của producer trên từng topic-partition.

Producer gắn PID và sequence number vào ProduceRequest. Broker lưu trạng thái sequence tương ứng với producer và partition. Khi nhận batch tiếp theo, broker kiểm tra sequence để phát hiện batch mới, batch lặp hoặc sequence không hợp lệ.

Ví dụ minh họa:

| Partition | Producer ID | Sequence batch | Kết quả |
|---|---:|---:|---|
| orders-0 | 71 | 0 | Ghi batch đầu tiên |
| orders-0 | 71 | 1 | Ghi batch tiếp theo |
| orders-0 | 71 | 1 | Nhận diện retry của batch đã ghi |
| orders-0 | 71 | 2 | Ghi batch mới |
| orders-1 | 71 | 0 | Sequence được quản lý riêng theo partition |

Các số trong bảng chỉ để minh họa. Sequence thực tế được Kafka quản lý theo protocol; ứng dụng không tự gán PID hoặc sequence number.

Sequence được theo dõi riêng cho mỗi topic-partition. Một producer có thể gửi tới nhiều partition và có tiến độ sequence độc lập trên từng partition.

## 3. Bật idempotent producer

Property chính là enable.idempotence. Khi bật, Kafka producer sử dụng PID và sequence number để chống duplicate do retry nội bộ.

Các điều kiện cấu hình quan trọng:

- enable.idempotence=true.
- acks=all.
- retries lớn hơn 0.
- max.in.flight.requests.per.connection không vượt quá 5.

Nếu idempotence được bật tường minh nhưng các property xung đột với điều kiện trên, Kafka producer có thể từ chối khởi tạo bằng lỗi cấu hình. Hãy kiểm tra cấu hình hiệu lực thay vì chỉ nhìn file YAML.

Ví dụ cấu hình tối thiểu:

```yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
```

acks=all yêu cầu broker xác nhận theo điều kiện ISR. retries cho phép producer thử lại các lỗi retriable. Idempotence kết hợp với sequence tracking để broker nhận diện retry của cùng batch.

## 4. Cấu hình với Spring Boot application.yml

Spring Boot bind producer properties vào Kafka client. Có thể cấu hình thêm timeout và backoff để retry nằm trong SLA publish:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 120000
        "[retry.backoff.ms]": 200
```

Trong ví dụ:

- enable.idempotence=true bật cơ chế idempotent producer.
- acks=all đáp ứng yêu cầu acknowledgment của idempotence.
- retries cho phép retry khi Kafka client phân loại lỗi là retriable.
- max.in.flight.requests.per.connection=5 nằm trong giới hạn tương thích với idempotence.
- request.timeout.ms giới hạn thời gian chờ response của một request.
- delivery.timeout.ms giới hạn tổng thời gian giao một record, gồm batching, request và retry.
- retry.backoff.ms đặt khoảng chờ giữa các lần retry.

Các key Kafka có dấu chấm được đặt trong ngoặc vuông để Spring Boot giữ nguyên tên property khi bind map. Tên cấu hình và default cần được kiểm tra theo phiên bản Spring Boot/Kafka client mà dự án đang dùng.

Kafka client hiện đại thường bật idempotence mặc định nếu không có cấu hình xung đột. Tuy nhiên, khai báo tường minh giúp ý định vận hành dễ review và tránh phụ thuộc vào default của version. Từ Kafka 3.0, enable.idempotence mặc định là true; ở các client cũ hơn, cần kiểm tra default tương ứng.

## 5. Cấu hình bằng Java ProducerFactory

Nếu tự tạo ProducerFactory, khai báo các property trực tiếp:

```java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);

        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
        properties.put(
                ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
                5);

        properties.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
        properties.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> orderProducerFactory) {
        return new KafkaTemplate<>(orderProducerFactory);
    }
}
```

Khi tự tạo factory, ứng dụng chịu trách nhiệm cung cấp bootstrap server, serializer, security và các producer properties cần thiết. Không giả định một ProducerFactory tự khai báo sẽ tự nhận toàn bộ cấu hình Spring Boot.

Nếu có nhiều KafkaTemplate dùng các ProducerFactory khác nhau, mỗi factory có thể có chính sách idempotence riêng. Hãy kiểm tra đúng template mà publisher thực tế inject.

## 6. KafkaTemplate không tự deduplicate theo event ID

Sau khi bật idempotence, producer có thể chống duplicate do retry cùng batch. Nhưng hai lời gọi sau là hai logical send độc lập:

```java
kafkaTemplate.send("orders", "order-42", event);
kafkaTemplate.send("orders", "order-42", event);
```

Kafka producer gán sequence tiếp theo cho lần gửi thứ hai. Broker xem đây là một batch mới hợp lệ, dù key và payload giống nhau. Do đó, topic có thể chứa hai record.

Idempotence không đọc eventId, không so sánh payload và không biết hai lần gọi send() đại diện cho cùng một hành động nghiệp vụ. Key Kafka cũng không phải khóa deduplication: cùng key có thể xuất hiện trong nhiều record hợp lệ.

Nếu nghiệp vụ yêu cầu chống gửi trùng do application retry, cần một cơ chế ở tầng ứng dụng như:

- Event ID ổn định được tạo một lần và giữ nguyên khi thử lại.
- Outbox pattern để ghi event cùng transaction nghiệp vụ.
- Inbox/deduplication table ở consumer với unique constraint trên event ID.
- Idempotent API ở dịch vụ downstream.

## 7. Phạm vi bảo đảm của idempotence

Idempotent producer bảo vệ retry nội bộ trong cùng producer session. Nó không phải một khóa duy nhất vĩnh viễn cho event.

| Tình huống | Idempotent producer xử lý? | Ghi chú |
|---|---|---|
| Kafka client retry cùng batch do timeout | Có | Broker nhận diện PID và sequence |
| Response bị mất sau khi broker append | Có | Retry cùng batch không tạo thêm append |
| Application gọi send() hai lần | Không | Hai lần gửi độc lập có sequence khác nhau |
| Hai producer instance gửi cùng event | Không | Mỗi producer có PID/session riêng |
| Application restart rồi gửi lại event cũ | Không tự động | Producer session mới không có dedup theo event ID |
| Consumer xử lý xong nhưng crash trước khi commit offset | Không | Đây là duplicate ở tầng consumer processing |
| Database commit thành công nhưng consumer chưa commit Kafka offset | Không | Cần idempotent consumer hoặc transaction/outbox phù hợp |

Vì vậy, nên mô tả chính xác là “exactly-once trong phạm vi retry của producer”, không gọi đây là exactly-once end-to-end cho toàn hệ thống.

## 8. Idempotence và thứ tự record

Retry có thể làm thay đổi thứ tự nếu nhiều request đang in-flight. Giả sử producer gửi batch A rồi batch B:

1. A gặp lỗi tạm thời.
2. B được broker xử lý thành công.
3. A được gửi lại sau đó.

Với cấu hình không idempotent và nhiều request in-flight, record của B có thể được ghi trước A. Điều này có thể làm thứ tự record trong một partition khác với thứ tự producer gửi.

Khi idempotence bật, Kafka hỗ trợ giữ thứ tự cho tối đa năm request in-flight trên mỗi connection. Vì vậy, giá trị max.in.flight.requests.per.connection không vượt quá 5 vẫn cho phép tận dụng pipeline mà giữ ordering theo producer sequence.

Ví dụ:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
```

Kafka chỉ bảo đảm thứ tự trong một partition. Idempotence không tạo thứ tự toàn cục giữa nhiều partition. Nếu các event của cùng aggregate cần đúng thứ tự, hãy dùng cùng message key để chúng được định tuyến vào cùng partition.

## 9. acks=all và min.insync.replicas

Idempotence yêu cầu acks=all, nhưng cần hiểu thêm cấu hình replication để đánh giá độ bền dữ liệu.

- acks=all yêu cầu leader chờ các replica trong ISR đáp ứng điều kiện ghi.
- min.insync.replicas đặt số replica tối thiểu cần có trong ISR để broker chấp nhận ghi với acks=all.
- Replication factor quyết định số replica được cấu hình cho partition.

Ví dụ topic có replication factor 3 và min.insync.replicas=2. Nếu ISR giảm xuống còn một replica, producer có thể nhận lỗi NotEnoughReplicasException hoặc lỗi liên quan và retry trong giới hạn delivery timeout.

Idempotence không tạo replica và không thay thế cấu hình durability. Nếu broker/ISR không phục hồi trước delivery timeout, future vẫn có thể thất bại. Hãy thiết kế replication factor, min ISR và SLA phục hồi cùng nhau.

## 10. Idempotent producer không đồng nghĩa transactional producer

Hai cơ chế liên quan nhưng phạm vi khác nhau:

| Cơ chế | Bảo đảm chính | Phạm vi |
|---|---|---|
| Idempotent producer | Retry cùng batch không tạo duplicate trong log | Producer session |
| Transactional producer | Ghi nhiều record/partition và commit hoặc abort như một transaction Kafka | Nhiều partition/topic trong transaction |
| Consume-process-produce transaction | Gộp output records và consumer offsets trong transaction Kafka | Luồng consume-transform-produce |

Transactional producer sử dụng idempotence; khi cấu hình transactional.id, Kafka producer tự bật idempotence và yêu cầu các điều kiện liên quan. Tuy nhiên, chỉ bật idempotence không tự tạo transaction hoặc gộp consumer offset với output record.

Ví dụ, nếu ứng dụng đọc một record, gửi output rồi commit consumer offset bằng các thao tác riêng, crash ở giữa vẫn có thể tạo duplicate hoặc mất liên kết giữa input và output. Muốn bảo đảm exactly-once cho Kafka-to-Kafka processing, cần transaction và cấu hình listener/container phù hợp.

Transaction Kafka cũng không tự bao phủ database hoặc HTTP API. Side effect bên ngoài Kafka vẫn cần outbox, inbox, idempotency key hoặc một cơ chế phối hợp transaction riêng.

## 11. Producer restart và producer instance mới

Idempotence dựa trên PID và sequence state của producer. Khi producer bị đóng và tạo instance mới, instance mới có thể nhận PID mới. Nó không tự biết rằng event mà application gửi lại đã được producer cũ ghi thành công trước khi process dừng.

Ví dụ:

```text
Producer instance A
  -> gửi event evt-100
  -> broker ghi thành công
  -> application mất response / process dừng

Producer instance B sau restart
  -> application gửi lại evt-100
  -> producer B xem đây là lần gửi mới
  -> topic có thể có thêm một record evt-100
```

Đây là lý do event ID nghiệp vụ vẫn quan trọng dù idempotence đã bật. Nếu producer cần gửi lại một event sau restart mà không tạo tác động trùng, consumer hoặc downstream cần deduplicate theo event ID.

Transactional producer với transactional.id ổn định có thêm cơ chế producer epoch/fencing để quản lý producer session cùng transactional identity. Đây là một phần của transactional semantics, không phải hành vi deduplication nghiệp vụ của idempotent producer thông thường.

## 12. Xử lý kết quả gửi bằng KafkaTemplate

KafkaTemplate.send(...) trả về future. Retry nội bộ diễn ra trong Kafka producer trước khi future hoàn tất:

```java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event) {

    return kafkaTemplate.send(
            "orders.created.v1",
            event.orderId(),
            event);
}
```

Quan sát kết quả cuối cùng:

```java
publish(event).whenComplete((result, exception) -> {
    if (exception != null) {
        log.error(
                "Publish failed: eventId={}",
                event.eventId(),
                exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info(
            "Published eventId={} topic={} partition={} offset={}",
            event.eventId(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset());
});
```

Từ Spring Kafka 3.0, send() trả về CompletableFuture; các phiên bản cũ sử dụng ListenableFuture. send() cũng có thể ném lỗi đồng bộ trước khi trả future, ví dụ lỗi serialization hoặc producer đã đóng. Lỗi giao hàng cuối cùng sau khi record được nhận vào producer thường được báo qua future.

Không coi việc send() trả về future là bằng chứng broker đã ghi record. Chỉ khi future hoàn tất thành công, ứng dụng mới nhận được SendResult và RecordMetadata.

## 13. Lỗi retry được và không retry được

Idempotence không biến mọi lỗi thành lỗi có thể retry. Kafka producer phân loại lỗi dựa trên exception và trạng thái client/broker.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Network exception, request timeout, leader chưa sẵn sàng | Producer có thể retry trong delivery timeout |
| ISR chưa đáp ứng | NotEnoughReplicasException | Có thể retry khi ISR phục hồi |
| Serialization | Object không serialize được | Sửa serializer/payload; retry broker không giải quyết |
| Authorization | ACL không cho ghi topic | Sửa quyền; retry không tự cấp quyền |
| Topic/partition không hợp lệ | Metadata hoặc cấu hình topic sai | Sửa cấu hình/metadata |
| Record quá lớn | Vượt giới hạn producer/broker/topic | Giảm payload hoặc điều chỉnh giới hạn phù hợp |

Danh sách retriable chính xác phụ thuộc Kafka client version và exception cụ thể. Không phân loại chỉ bằng message text; khi cần, kiểm tra cause chain và loại exception Kafka trả về.

## 14. Cấu hình xung đột và lỗi khởi tạo producer

Khi enable.idempotence=true, các property liên quan phải tương thích. Ví dụ:

```yaml
spring:
  kafka:
    producer:
      acks: 1
      properties:
        "[enable.idempotence]": true
```

Đây là cấu hình xung đột vì idempotence yêu cầu acks=all. Kafka producer có thể ném ConfigException khi khởi tạo.

Một ví dụ khác là đặt max.in.flight.requests.per.connection lớn hơn 5 trong khi idempotence bật. Hãy kiểm tra:

- Có property nào được set ở application.yml, profile hoặc environment variable không.
- Có custom ProducerFactory ghi đè property Boot không.
- Có nhiều KafkaTemplate dùng các factory khác nhau không.
- Kafka client version có default hoặc giới hạn nào khác không.

Khi cấu hình idempotence tường minh, nên khai báo đồng bộ acks, retries và max.in.flight.requests.per.connection để tránh một profile môi trường vô tình vô hiệu hóa cơ chế này.

## 15. Kiểm tra cấu hình producer thực tế

Có thể kiểm tra cấu hình ProducerFactory sau khi Spring khởi tạo bean:

```java
@Autowired
private ProducerFactory<String, OrderCreated> producerFactory;

@Test
void shouldEnableIdempotence() {
    Map<String, Object> properties =
            producerFactory.getConfigurationProperties();

    assertThat(properties.get(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG))
            .isEqualTo(true);
    assertThat(properties.get(ProducerConfig.ACKS_CONFIG))
            .isEqualTo("all");
    assertThat(properties.get(ProducerConfig.RETRIES_CONFIG))
            .isEqualTo(Integer.MAX_VALUE);
    assertThat(properties.get(
            ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION))
            .isEqualTo(5);
}
```

Kiểm tra map cấu hình giúp phát hiện property bị profile hoặc custom factory ghi đè. Tuy nhiên, nó chưa chứng minh broker đã xử lý retry đúng; cần thêm integration test với Kafka broker.

Lưu ý kiểu dữ liệu trong map có thể là String, Integer, Boolean hoặc kiểu số khác tùy cách cấu hình. Khi viết assertion, chuẩn hóa kiểu hoặc kiểm tra qua ProducerConfig/Producer thực tế theo dependency đang dùng.

## 16. Kiểm thử idempotent producer

Kiểm thử đầy đủ cần xác minh cấu hình và hành vi:

1. Producer gửi record bình thường; future hoàn tất thành công.
2. Producer gặp lỗi mạng hoặc broker tạm ngắt sau khi request được gửi; client retry trong delivery timeout.
3. Broker phục hồi; retry cùng batch không tạo duplicate do transport retry.
4. Delivery timeout hết hạn; future hoàn tất exceptionally.
5. Application gọi send() hai lần cho cùng event; xác minh đây là hai logical send riêng.
6. Producer restart rồi application phát lại event cũ; xác minh idempotent consumer/deduplication xử lý event ID trùng nếu nghiệp vụ yêu cầu.
7. Cấu hình xung đột; producer fail fast thay vì chạy với semantics không mong muốn.

Với Testcontainers hoặc broker test chuyên dụng, có thể mô phỏng broker restart/network interruption. Tình huống “broker đã append nhưng response bị mất” khó tái tạo ổn định; nên dùng fault injection/proxy hoặc integration test được kiểm soát thay vì chỉ dừng broker ngẫu nhiên.

Không nên dùng Thread.sleep cố định để kết luận không có duplicate. Hãy chờ future, consumer nhận record và điều kiện test bằng polling có timeout; dùng topic và event ID riêng cho mỗi test.

## 17. Idempotent consumer vẫn cần thiết

Producer idempotence không ngăn consumer xử lý lại record khi offset chưa được commit. Ví dụ:

1. Consumer đọc event evt-100.
2. Consumer ghi dữ liệu vào database thành công.
3. JVM crash trước khi commit Kafka offset.
4. Sau restart, Kafka giao lại evt-100.
5. Consumer có thể ghi cùng thay đổi database lần thứ hai.

Một idempotent consumer có thể lưu eventId đã xử lý trong cùng transaction database với nghiệp vụ:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Khi nhận event, consumer ghi event_id vào bảng với unique constraint. Nếu ID đã tồn tại, consumer biết event đã được xử lý và có thể bỏ qua phần side effect lặp. Việc ghi marker và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction database để tránh trạng thái nửa chừng.

Với hệ thống Kafka-to-Kafka, transaction Kafka có thể gộp output records và input offsets. Với database hoặc API ngoài Kafka, cần thiết kế idempotency/outbox/inbox phù hợp.

## 18. Quan sát idempotent producer trong production

Idempotence hoạt động bên trong producer client. Ứng dụng thường không nhận một callback riêng cho mỗi lần retry; thay vào đó, theo dõi producer metrics và kết quả cuối cùng của future.

Các metric hữu ích:

- record-retry-rate: tỷ lệ batch được retry.
- record-error-rate: tỷ lệ batch gặp lỗi.
- record-send-rate: tốc độ gửi record.
- request-latency-avg và request-latency-max: độ trễ request.
- record-queue-time-avg: thời gian record nằm trong accumulator.
- requests-in-flight: số request chưa có response.
- buffer-available-bytes: dung lượng buffer còn trống.

Tên metric cụ thể phụ thuộc Kafka client version và metrics reporter. Kết hợp metric với log publish failure, event ID và metadata topic/partition/offset; tránh ghi payload nhạy cảm.

Nếu retry rate tăng cao, kiểm tra broker latency, ISR, network, request timeout và buffer pressure. Idempotence giảm duplicate do retry nhưng không loại bỏ nguyên nhân gây retry hoặc cải thiện năng lực broker.

## 19. Các lỗi thường gặp

**Bật idempotence nhưng producer không khởi tạo:** kiểm tra acks, retries và max.in.flight.requests.per.connection có thỏa điều kiện không.

**Vẫn có duplicate event:** xác định duplicate do retry nội bộ, application gọi send nhiều lần, producer restart hay consumer xử lý lại. Idempotence chỉ giải quyết trường hợp retry nội bộ của producer session.

**Nghĩ cùng message key sẽ tự deduplicate:** key quyết định partitioning/compaction semantics theo cấu hình topic, không phải khóa loại bỏ record trùng trong log append.

**Nghĩ idempotence là exactly-once end-to-end:** cần phân biệt producer retry, consumer offset, transaction và side effect ngoài Kafka.

**Đặt max.in.flight.requests.per.connection quá cao:** cấu hình có thể xung đột với idempotence. Giữ không vượt 5 khi bật idempotence.

**Dùng acks=1 với idempotence:** producer có thể không khởi tạo vì idempotence yêu cầu acks=all.

**Tăng retries nhưng không tăng delivery timeout:** record vẫn có thể hết thời gian giao hàng trước khi đủ số lần thử.

**Gọi KafkaTemplate.send() lại trong callback lỗi:** đây là lần gửi mới, có thể tạo duplicate; cần event ID và deduplication ở tầng ứng dụng.

**Chỉ test property, không test broker behavior:** cấu hình đúng chưa chứng minh retry thực tế và duplicate suppression.

## 20. Checklist production

- Kafka client version hỗ trợ idempotent producer và default của version đã được xác định.
- enable.idempotence=true được cấu hình tường minh khi cần bảo đảm này.
- acks=all, retries>0 và max.in.flight.requests.per.connection<=5.
- request.timeout.ms, delivery.timeout.ms và linger.ms có quan hệ hợp lệ.
- Topic có replication factor và min.insync.replicas phù hợp yêu cầu durability.
- Mọi KafkaTemplate dùng đúng ProducerFactory có idempotence.
- Không nhầm producer retry với application retry.
- Event ID ổn định được dùng khi nghiệp vụ cần dedup qua restart hoặc nhiều producer.
- Consumer có idempotency/inbox nếu database side effect có thể bị gọi lại.
- Dùng Kafka transaction khi cần exactly-once cho consume-process-produce trong Kafka.
- Đã kiểm thử broker interruption, delivery timeout, application resend và producer restart.
- Theo dõi retry rate, request latency, buffer pressure và future failure.

Idempotent producer dùng producer ID và sequence number để broker nhận diện retry của cùng batch, tránh duplicate do lỗi transport trong một producer session. Hãy bật cơ chế này cùng acks=all, retries và giới hạn in-flight tương thích. Với duplicate do application resend, producer restart hoặc consumer replay, vẫn cần event ID, idempotent consumer, outbox/inbox hoặc Kafka transaction theo đúng phạm vi bảo đảm mà hệ thống yêu cầu.

## Tài liệu tham khảo

- [Apache Kafka – Producer Configs](https://kafka.apache.org/documentation/#producerconfigs_enable.idempotence)
- [Apache Kafka – Design: Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
- [Spring for Apache Kafka – Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
