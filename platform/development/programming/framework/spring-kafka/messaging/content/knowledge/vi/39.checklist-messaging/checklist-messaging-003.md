# Checklist cấu hình producer

Producer là thành phần đưa event từ ứng dụng vào Kafka. Một producer được cấu hình tốt cần đáp ứng đồng thời độ bền dữ liệu, khả năng xử lý lỗi, throughput, latency, bảo mật và khả năng quan sát. Trong Spring Kafka, cấu hình producer thường được khai báo bằng Spring Boot properties hoặc một `ProducerFactory` tùy chỉnh; `KafkaTemplate` sử dụng factory đó để gửi record.

Checklist này dùng trước khi triển khai producer mới hoặc thay đổi cấu hình producer đang chạy. Các giá trị trong ví dụ là điểm bắt đầu để đánh giá, không phải cấu hình tối ưu cho mọi workload. Hãy chọn theo SLA, kích thước event, số partition, năng lực broker và yêu cầu nghiệp vụ.

## 1. Xác định yêu cầu trước khi cấu hình

Trước khi chọn serializer, acknowledgement hay compression, cần thống nhất producer đang phục vụ loại luồng dữ liệu nào.

- [ ] Xác định topic đích và service sở hữu topic.
- [ ] Xác định loại event, schema, key và kích thước payload điển hình.
- [ ] Xác định event có cần giữ thứ tự theo entity/key hay không.
- [ ] Xác định mức mất dữ liệu có thể chấp nhận khi broker hoặc network gặp sự cố.
- [ ] Xác định throughput trung bình, peak records/second và bytes/second.
- [ ] Xác định latency mục tiêu, ví dụ p95/p99 từ lúc ứng dụng gửi tới khi broker xác nhận.
- [ ] Xác định producer có cần transaction hay chỉ cần idempotent delivery.
- [ ] Xác định môi trường chạy: local, test, staging, production, Kubernetes hay VM.
- [ ] Xác định consumer và connector nào sẽ đọc topic để kiểm tra tương thích serializer/compression.
- [ ] Xác định người chịu trách nhiệm vận hành, dashboard, alert và quy trình xử lý publish failure.

Không nên chọn cấu hình chỉ dựa vào số record mỗi giây. Một producer gửi nhiều event nhỏ tới nhiều partition có đặc điểm batching khác producer gửi payload lớn tới một vài partition.

## 2. Kiểm tra Kafka cluster và topic đích

Producer chỉ gửi thành công khi broker và topic đáp ứng cấu hình đã chọn.

- [ ] `bootstrap.servers` trỏ tới bootstrap endpoint của đúng cluster và đúng môi trường.
- [ ] DNS, route, firewall và TLS handshake từ ứng dụng tới broker hoạt động.
- [ ] Topic đích đã được provision hoặc có quy trình tạo topic được kiểm soát.
- [ ] Số partition phù hợp với throughput và mức song song của consumer.
- [ ] Replication factor phù hợp với số broker và yêu cầu chịu lỗi.
- [ ] `min.insync.replicas` của topic phù hợp với acknowledgement policy.
- [ ] Topic có `max.message.bytes` đủ cho record/batch theo thiết kế.
- [ ] Topic cleanup policy và retention đúng với vòng đời event.
- [ ] Có kiểm tra leader/ISR và broker health trước khi rollout.

Với producer dùng `acks=all`, `min.insync.replicas` giúp đặt ngưỡng replica in-sync tối thiểu để broker chấp nhận ghi. Ví dụ topic có replication factor 3 và `min.insync.replicas=2` sẽ yêu cầu ít nhất hai replica in-sync cho ghi theo `acks=all`. Nếu ISR tụt dưới ngưỡng, producer nhận lỗi thay vì âm thầm chấp nhận mức độ bền thấp hơn.

Không đặt replication factor lớn hơn số broker có thể lưu replica. Cấu hình local một broker thường khác production cluster nhiều broker.

## 3. Cấu hình kết nối và định danh producer

Với Spring Boot, cấu hình kết nối cơ bản trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.internal:9092
      - kafka-2.example.internal:9092
      - kafka-3.example.internal:9092
    producer:
      client-id: orders-service
```

Checklist kết nối:

- [ ] Dùng nhiều bootstrap broker endpoint nếu môi trường cung cấp danh sách broker.
- [ ] Không hard-code địa chỉ production trong source code.
- [ ] Phân tách cấu hình local, test, staging và production bằng profile/secret/config management.
- [ ] Đặt `client.id` có thể nhận diện service, instance và môi trường khi cần.
- [ ] Không dùng `client.id` làm transactional ID; hai thuộc tính có mục đích khác nhau.
- [ ] Xác minh ứng dụng kết nối đúng cluster trước khi cho phép publish event nghiệp vụ.

`bootstrap.servers` chỉ là danh sách địa chỉ ban đầu để client lấy metadata; producer có thể kết nối tới các broker khác sau khi nhận metadata từ cluster.

## 4. Chọn key và partition strategy

Key ảnh hưởng tới partition mà record được gửi tới và do đó ảnh hưởng thứ tự xử lý.

- [ ] Chọn key ổn định theo entity cần giữ thứ tự, ví dụ `orderId`, `accountId` hoặc `customerId`.
- [ ] Không dùng random key nếu các event cùng entity cần được xử lý tuần tự.
- [ ] Kiểm tra phân bố key để tránh một key nóng dồn tải vào một partition.
- [ ] Không đổi key format hoặc partitioner mà chưa đánh giá tác động tới ordering.
- [ ] Chỉ chỉ định partition trực tiếp khi có yêu cầu vận hành rõ ràng.
- [ ] Nếu key là null, hiểu rõ partitioner sẽ phân phối record như thế nào trong phiên bản Kafka client đang dùng.
- [ ] Giữ tương thích giữa key serializer của producer và key deserializer của consumer.

Kafka chỉ bảo đảm thứ tự trong một partition. Các record cùng key thường được đưa vào cùng partition theo partitioner mặc định, nhưng thay đổi partition count có thể làm key được ánh xạ sang partition khác. Không giả định thứ tự toàn cục giữa nhiều partition.

Ví dụ gửi event với key là `orderId`:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders.events", orderId, payload);
    }
}
```

Trong ví dụ, các event của cùng `orderId` thường được route tới cùng partition, giữ thứ tự tương đối trong partition đó.

## 5. Cấu hình serializer và schema

Serializer chuyển key/value từ Java object thành byte array. Producer và consumer phải thống nhất wire format.

- [ ] Chọn key serializer đúng kiểu key: String, Long, UUID hoặc byte array.
- [ ] Chọn value serializer phù hợp: JSON, Avro, Protobuf, JSON Schema hoặc bytes.
- [ ] Kiểm tra generated schema classes và serializer dependency có trên runtime classpath.
- [ ] Nếu dùng Schema Registry, cấu hình đúng `schema.registry.url` và credential.
- [ ] Chọn subject naming strategy nhất quán.
- [ ] Quyết định `auto.register.schemas` có được phép bật trong môi trường đó hay không.
- [ ] Kiểm tra compatibility policy trước khi deploy schema mới.
- [ ] Không nhầm Spring Kafka `JsonSerializer` với Confluent `KafkaJsonSchemaSerializer`.
- [ ] Xác minh consumer và connector có thể deserialize payload do producer phát ra.
- [ ] Có kiểm thử cho payload cũ, payload mới và lỗi serialization.

Ví dụ producer JSON trong Spring Boot:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Nếu dùng Avro với Confluent Schema Registry, value serializer có thể là `io.confluent.kafka.serializers.KafkaAvroSerializer`; consumer cần deserializer tương ứng. Không cấu hình producer Avro rồi để consumer dùng `StringDeserializer`.

Lỗi serialize thường không được khắc phục bằng retry gửi lại cùng object. Hãy phân biệt lỗi dữ liệu/serializer với lỗi tạm thời của broker hoặc network.

## 6. Chọn acknowledgement policy

Producer property `acks` quyết định số xác nhận broker mà producer chờ trước khi coi send thành công.

| Giá trị | Hành vi | Cân nhắc |
|---|---|---|
| `0` | Producer không chờ broker acknowledgement | Throughput/latency có thể tốt hơn nhưng không biết broker có nhận record hay không |
| `1` | Chờ leader xác nhận local write | Có thể mất record nếu leader lỗi trước khi replica khác nhận dữ liệu |
| `all` hoặc `-1` | Chờ tất cả replica hiện có trong ISR xác nhận | Thường phù hợp event nghiệp vụ cần độ bền cao; kết hợp `min.insync.replicas` |

Ví dụ Spring Boot:

```yaml
spring:
  kafka:
    producer:
      acks: all
```

Checklist:

- [ ] Chọn `acks=all` cho event không thể dễ dàng tái tạo hoặc nghiệp vụ cần độ bền cao.
- [ ] Kiểm tra topic `min.insync.replicas` để policy có ý nghĩa thực tế.
- [ ] Chỉ dùng `acks=0` khi chấp nhận không có xác nhận broker và đã đo rõ rủi ro.
- [ ] Không coi `acks=all` là bảo đảm dữ liệu đã được consumer xử lý.
- [ ] Định nghĩa rõ API publish trả thành công ở thời điểm nào: broker ack, transaction commit hay downstream processing.

`acks=all` không có nghĩa mọi replica được cấu hình trong replication factor đều phải online; nó yêu cầu các replica đang thuộc ISR. Ngưỡng `min.insync.replicas` đặt mức ISR tối thiểu để broker chấp nhận ghi.

## 7. Idempotence, retry và timeout

Lỗi network có thể khiến producer không biết broker đã ghi record hay chưa. Retry giúp gửi lại request; idempotent producer giúp Kafka loại duplicate do retry của cùng producer session/sequence trong phạm vi bảo đảm của Kafka.

- [ ] Bật `enable.idempotence=true` cho producer cần hạn chế duplicate do retry.
- [ ] Không cấu hình xung đột giữa idempotence, `acks`, `retries` và `max.in.flight.requests.per.connection`.
- [ ] Nếu bật idempotence, giữ `max.in.flight.requests.per.connection` trong giới hạn Kafka hỗ trợ (tối đa 5 với producer idempotent hiện đại).
- [ ] Đặt `delivery.timeout.ms` theo thời gian tối đa ứng dụng chấp nhận một lần gửi.
- [ ] Đặt `request.timeout.ms` phù hợp với latency broker/network và nhỏ hơn `delivery.timeout.ms`.
- [ ] Hiểu `max.block.ms` giới hạn thời gian các lời gọi có thể block khi metadata/buffer chưa sẵn sàng.
- [ ] Không đặt retry count thấp chỉ để che lỗi; với idempotence, Kafka client có thể retry trong giới hạn delivery timeout.
- [ ] Phân loại lỗi retryable và non-retryable ở tầng ứng dụng.
- [ ] Với timeout không rõ kết quả, dùng event ID/idempotency ở consumer nếu nghiệp vụ không chịu được duplicate.

Ví dụ cấu hình reliability:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[max.block.ms]": 60000
```

Kafka producer hiện đại thường bật idempotence mặc định khi các điều kiện tương thích được đáp ứng, nhưng khai báo rõ giúp reviewer nhìn thấy chủ đích. Hãy kiểm tra giá trị effective của Kafka client thay vì dựa vào giả định về default giữa các phiên bản.

Idempotence không làm side effect database, HTTP hoặc email trở thành exactly-once. Nếu ứng dụng retry toàn bộ nghiệp vụ và gửi lại event với một producer session khác, cần event ID và consumer idempotency để ngăn xử lý trùng.

## 8. Phân biệt producer retry với retry nghiệp vụ

Có hai lớp retry khác nhau:

| Lớp | Phạm vi | Ví dụ |
|---|---|---|
| Kafka producer retry | Gửi lại request khi lỗi tạm thời theo Kafka client | Broker leader đổi, request timeout hoặc lỗi network retryable |
| Application retry | Gọi lại logic nghiệp vụ hoặc publish operation | Service gọi lại use case sau khi nhận lỗi, job retry hoặc outbox publisher chạy lại |

- [ ] Không thêm vòng retry application dày đặc bên ngoài Kafka retry mà không có backoff.
- [ ] Không retry vô hạn lỗi serialization, authorization hoặc record quá lớn.
- [ ] Với retry ở application layer, có giới hạn attempts, backoff và metric.
- [ ] Nếu kết quả send timeout không rõ ràng, không mặc định rằng record chắc chắn chưa được ghi.
- [ ] Dùng outbox hoặc cơ chế phát event bền vững nếu cần bảo đảm thay đổi database và publish event không bị tách rời.

Producer retry không thay thế consumer retry hoặc dead-letter handling. Mỗi lớp giải quyết một loại lỗi ở một ranh giới khác nhau.

## 9. Cấu hình batching và linger

Kafka gom record thành batch theo partition để giảm số request và tăng hiệu quả compression.

- [ ] Đo `batch.size` trung bình và tỷ lệ batch đầy trước khi thay đổi.
- [ ] Chọn `batch.size` theo throughput, số partition và ngân sách memory.
- [ ] Dùng `linger.ms` để cho producer thêm thời gian gom record khi batch chưa đầy.
- [ ] Đo p95/p99 latency sau khi thay đổi linger.
- [ ] Kiểm tra `buffer.memory` đủ cho số lượng partition và producer concurrency.
- [ ] Theo dõi producer buffer exhaustion và số thread chờ buffer.
- [ ] Không gọi `flush()` sau mỗi message; thao tác đó làm mất lợi ích batching.

Ví dụ điểm bắt đầu:

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      buffer-memory: 67108864
      properties:
        "[linger.ms]": 5
```

`batch-size` và `buffer-memory` tính theo byte. Các giá trị 64 KiB và 64 MiB chỉ là ví dụ; workload có payload lớn hoặc nhiều partition có thể cần ngân sách khác. Tăng batch size không đảm bảo batch sẽ đầy nếu lưu lượng trên từng partition thấp.

## 10. Chọn compression

Compression giảm bytes truyền và lưu nhưng tăng CPU nén/giải nén.

- [ ] Chạy baseline với `none`.
- [ ] Thử `lz4`, `snappy`, `zstd` và `gzip` trên payload đại diện.
- [ ] Cấu hình `spring.kafka.producer.compression-type` hoặc `compression.type`.
- [ ] Kiểm tra topic `compression.type` có giữ codec producer (`producer`) hay yêu cầu broker recompress.
- [ ] Đo `compression-rate-avg`, batch size, CPU producer/broker/consumer và network bytes.
- [ ] Xác minh connector và client ngoài Java hỗ trợ codec được chọn.
- [ ] Không chọn codec chỉ dựa trên compression ratio; phải xét latency và CPU.

Ví dụ:

```yaml
spring:
  kafka:
    producer:
      compression-type: lz4
```

`lz4` thường là điểm bắt đầu hợp lý khi cần cân bằng CPU và network, nhưng kết quả thực tế phụ thuộc dữ liệu. Payload đã nén hoặc mã hóa có thể không giảm đáng kể.

## 11. Giới hạn kích thước record và request

Payload lớn có thể vượt giới hạn producer, broker hoặc consumer fetch.

- [ ] Đo kích thước key, value, headers và record batch thực tế.
- [ ] Kiểm tra producer `max.request.size`.
- [ ] Kiểm tra broker `message.max.bytes` và topic `max.message.bytes` theo phiên bản Kafka.
- [ ] Kiểm tra consumer `fetch.max.bytes` và `max.partition.fetch.bytes`.
- [ ] Không tăng giới hạn chỉ ở producer mà quên broker và consumer.
- [ ] Đánh giá memory, network, GC và thời gian serialize cho payload lớn.
- [ ] Cân nhắc lưu blob lớn ở object storage và chỉ gửi reference/metadata qua Kafka.

Compression không bảo đảm record quá lớn sẽ hợp lệ. Một record đơn lẻ lớn vẫn có thể vượt giới hạn ngay cả khi batch có tỷ lệ nén tốt.

## 12. Bảo mật và ACL

Producer production cần xác thực với cluster và chỉ có quyền publish vào topic được giao.

- [ ] Chọn security protocol đúng: `SASL_SSL`, `SSL` hoặc protocol theo cluster.
- [ ] Cấu hình SASL mechanism và credential qua secret manager/secret environment.
- [ ] Cấu hình truststore/keystore khi cluster yêu cầu TLS client authentication.
- [ ] Không commit password, API key, JAAS config hoặc private key vào repository.
- [ ] Principal của producer có `WRITE` và `DESCRIBE` trên topic cần publish theo ACL policy.
- [ ] Nếu dùng transaction, principal có quyền cần thiết trên transactional ID.
- [ ] Kiểm tra certificate rotation và credential expiration.
- [ ] Có kiểm thử kết nối trong môi trường giống production.

Ví dụ minh họa SASL/SSL; tên mechanism và credential phải lấy từ cluster:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": PLAIN
      "[sasl.jaas.config]": 'org.apache.kafka.common.security.plain.PlainLoginModule required username="API_KEY" password="API_SECRET";'
```

Thay `API_KEY` và `API_SECRET` bằng giá trị được inject từ secret manager ở runtime; không lưu credential thật trong file cấu hình hoặc source control. Không dùng cấu hình PLAIN qua kết nối không mã hóa. Với SASL/SSL, TLS bảo vệ credential và dữ liệu trên đường truyền. Cách xác thực cụ thể phải theo hướng dẫn của Kafka platform đang sử dụng.

## 13. Transaction khi cần publish nguyên tử

Nếu một nghiệp vụ cần gửi nhiều record như một đơn vị commit/abort, có thể dùng Kafka transaction. Với Spring Boot, cấu hình `transaction-id-prefix` để producer factory hỗ trợ transaction.

- [ ] Chỉ bật transaction khi use case cần atomic multi-record hoặc consume-transform-produce.
- [ ] Cấu hình `spring.kafka.producer.transaction-id-prefix` duy nhất giữa các instance đang hoạt động.
- [ ] Bảo đảm `KafkaTemplate` và `KafkaTransactionManager` dùng đúng `ProducerFactory`.
- [ ] Đặt `transaction.timeout.ms` trong giới hạn broker.
- [ ] Consumer cần bỏ qua record transaction bị abort phải dùng `isolation.level=read_committed`.
- [ ] Nếu cần commit input offset cùng output record, dùng transactional listener container/offset coordination đúng cách.
- [ ] Không giả định transaction Kafka bao gồm database hoặc HTTP service.

Ví dụ prefix cho một instance:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-pod-a-orders-tx-
```

Prefix phải khác nhau giữa các pod/instance đồng thời để tránh producer fencing. Nếu chỉ gửi một record độc lập và không cần atomic multi-record, idempotent producer có thể đủ mà không cần transaction.

## 14. Sử dụng KafkaTemplate an toàn

`KafkaTemplate` được thiết kế để dùng chung trong ứng dụng Spring. Nó lấy producer từ `ProducerFactory`, quản lý send operation và cung cấp future để nhận kết quả.

- [ ] Inject một `KafkaTemplate` đã cấu hình thay vì tạo producer mới cho từng message.
- [ ] Kiểm tra topic, key, value và headers trước khi gửi.
- [ ] Dùng future/callback để quan sát send success và failure.
- [ ] Không block thread request quá lâu nếu không có yêu cầu đồng bộ.
- [ ] Không gọi `flush()` cho từng record.
- [ ] Không nuốt exception trong callback nếu hệ thống cần ghi nhận publish failure.
- [ ] Đưa event ID/correlation ID vào header hoặc payload theo contract.
- [ ] Không log toàn bộ payload có dữ liệu nhạy cảm.

Ví dụ với Spring Kafka 3.x:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
class EventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    EventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String topic,
            String key,
            String payload
    ) {
        return kafkaTemplate.send(topic, key, payload);
    }
}
```

Spring Kafka 3.x trả `CompletableFuture` từ send API; phiên bản cũ có thể dùng `ListenableFuture`. Hãy theo đúng API của dependency trong dự án.

Nếu cần phản hồi cho caller sau khi broker xác nhận, caller có thể chờ future ở ranh giới phù hợp. Không giữ HTTP request thread chờ Kafka vô hạn; đặt timeout và xử lý trạng thái chưa rõ kết quả một cách có idempotency.

## 15. Observability cho producer

Không thể vận hành producer tốt nếu chỉ biết ứng dụng có log exception.

- [ ] Export Kafka producer metrics qua JMX/Micrometer theo stack monitoring.
- [ ] Theo dõi `record-send-rate`, `record-error-rate` và `record-retry-rate`.
- [ ] Theo dõi `request-latency-avg`/`request-latency-max`.
- [ ] Theo dõi `record-queue-time-avg` và `batch-size-avg`.
- [ ] Theo dõi `compression-rate-avg`.
- [ ] Theo dõi `buffer-available-bytes` và `waiting-threads`.
- [ ] Theo dõi timeout, serialization failure, authorization failure và broker disconnect.
- [ ] Gắn `client.id`, service, environment và topic vào log/metric khi có thể.
- [ ] Có correlation ID/event ID để truy vết publish với consumer.
- [ ] Đặt alert cho error rate, latency, buffer pressure và publish failure kéo dài.

Một số dấu hiệu thường gặp:

| Dấu hiệu | Nguyên nhân cần kiểm tra |
|---|---|
| `record-error-rate` tăng | Broker, ACL, serialization, message size hoặc timeout |
| `record-retry-rate` tăng | Network chập chờn, leader change hoặc broker quá tải |
| `record-queue-time-avg` tăng | Producer buffer chờ gửi, broker chậm hoặc batch chưa được drain |
| `buffer-available-bytes` thấp | Producer không gửi kịp hoặc buffer memory quá nhỏ |
| `waiting-threads` tăng | Thread ứng dụng chờ metadata/buffer lâu |
| Request latency tăng | Broker/network, ISR hoặc request queue |
| Compression ratio xấu | Batch nhỏ hoặc payload ít khả năng nén |

Metric name và cách export có thể khác theo Kafka client version. Đặt dashboard dựa trên metric thực tế được expose trong môi trường triển khai.

## 16. Kiểm thử producer trước khi phát hành

Unit test mock `KafkaTemplate` chỉ xác minh code gọi đúng method; nó không xác minh broker acknowledgement, serializer, ACL hay transaction marker.

- [ ] Unit test event mapping: field, key, headers và topic.
- [ ] Kiểm tra serialization/deserialization round-trip.
- [ ] Integration test với Kafka broker thật hoặc Testcontainers/Embedded Kafka phù hợp.
- [ ] Xác minh record được ghi đúng topic, partition và key.
- [ ] Xác minh send future thành công và lỗi được truyền tới caller.
- [ ] Kiểm thử broker unavailable, timeout và retry behavior.
- [ ] Kiểm thử record vượt giới hạn kích thước.
- [ ] Kiểm thử ACL thiếu quyền.
- [ ] Nếu dùng schema registry, kiểm thử schema registration/lookup và compatibility.
- [ ] Nếu dùng transaction, kiểm thử commit, abort và consumer `read_committed`.
- [ ] Chạy tải đại diện để đo throughput, latency, CPU, network và compression.

Test nên xác minh kết quả ở broker/consumer thay vì chỉ kiểm tra số lần gọi mock. Với transaction và idempotence, cần broker thực để xác minh semantics.

## 17. Checklist rollout và thay đổi cấu hình

Thay đổi producer config có thể tác động tới toàn bộ event stream. Triển khai theo bước và có khả năng rollback.

- [ ] Ghi lại cấu hình hiện tại và baseline metrics trước thay đổi.
- [ ] Thay đổi một nhóm thuộc tính mỗi lần để biết nguyên nhân kết quả.
- [ ] Kiểm tra tương thích broker/client và consumer trước khi dùng codec hoặc property mới.
- [ ] Thử ở staging với dữ liệu và throughput gần production.
- [ ] Canary một instance hoặc một producer workload nhỏ nếu có thể.
- [ ] Theo dõi error rate, latency, retry, buffer, CPU và network sau rollout.
- [ ] Xác minh consumer nhận event đúng schema và đúng thứ tự theo key.
- [ ] Có rollback plan và biết cấu hình nào có thể đổi runtime, cấu hình nào cần restart.
- [ ] Không đổi serializer, key strategy, transaction ID prefix và compression cùng lúc nếu chưa có kiểm thử tổng thể.
- [ ] Cập nhật runbook, dashboard và tài liệu cấu hình sau khi thay đổi.

Một số producer property được áp dụng khi producer mới được tạo; thay đổi cấu hình Spring không nhất thiết cập nhật các producer instance đang tồn tại. Hãy xác định lifecycle/restart behavior của `ProducerFactory` và ứng dụng trước khi dựa vào dynamic config.

## 18. Bảng cấu hình tham khảo

Bảng dưới đây là mẫu khởi đầu cho một producer event nghiệp vụ; hãy điều chỉnh theo tải và yêu cầu của hệ thống.

| Thuộc tính | Ví dụ | Mục đích |
|---|---|---|
| `bootstrap-servers` | `kafka-1:9092,kafka-2:9092` | Kết nối cluster |
| `client-id` | `orders-service` | Nhận diện producer trong metrics/log |
| `key-serializer` | `StringSerializer` | Serialize key |
| `value-serializer` | `JsonSerializer` | Serialize value |
| `acks` | `all` | Chờ ISR xác nhận |
| `enable.idempotence` | `true` | Chống duplicate do producer retry trong phạm vi Kafka |
| `delivery.timeout.ms` | `120000` | Giới hạn thời gian hoàn tất send |
| `request.timeout.ms` | `30000` | Timeout cho request broker |
| `batch-size` | `65536` | Mục tiêu kích thước batch |
| `linger.ms` | `5` | Thời gian gom batch |
| `buffer-memory` | `67108864` | Bộ nhớ producer accumulator |
| `compression-type` | `lz4` | Nén record batch |
| `max.request.size` | Theo payload/SLA | Giới hạn request producer |

Ví dụ tổng hợp:

```yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.internal:9092
      - kafka-2.example.internal:9092
    producer:
      client-id: orders-service
      acks: all
      batch-size: 65536
      buffer-memory: 67108864
      compression-type: lz4
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[max.block.ms]": 60000
        "[linger.ms]": 5
```

Mẫu này không bao gồm security, Schema Registry hoặc transaction vì các cấu hình đó phụ thuộc cluster và contract cụ thể. Không copy nguyên xi sang production nếu chưa xác minh `min.insync.replicas`, message size limits, credential, throughput và latency SLA.

## 19. Checklist cuối trước production

### Kết nối và topic

- [ ] Đúng cluster, bootstrap servers và môi trường.
- [ ] Topic tồn tại, partition/replication/ISR đúng.
- [ ] Topic size limit và retention phù hợp.

### Serialization và key

- [ ] Key/value serializer khớp contract consumer.
- [ ] Schema Registry/subject/compatibility đã được kiểm tra nếu có.
- [ ] Key giữ ordering đúng và không gây hot partition.

### Reliability

- [ ] `acks` phù hợp mức độ bền dữ liệu.
- [ ] Idempotence được bật khi cần.
- [ ] Retry và timeout có giới hạn hợp lý.
- [ ] Lỗi serialize/authorization không bị retry vô hạn.
- [ ] Event ID/idempotency có cho nghiệp vụ dễ bị gửi trùng.

### Performance

- [ ] Batch, linger, buffer và compression được benchmark.
- [ ] CPU, network, latency và buffer pressure nằm trong ngân sách.
- [ ] Record/request size nằm trong giới hạn toàn pipeline.

### Security và vận hành

- [ ] TLS/SASL và ACL đúng quyền tối thiểu.
- [ ] Secret không nằm trong source control.
- [ ] Metrics, logs, traces và alerts đã được cấu hình.
- [ ] Integration test và rollout/rollback plan đã sẵn sàng.
- [ ] Có owner và runbook xử lý publish failure.

Producer được cấu hình đúng khi event được serialize theo contract, gửi tới đúng partition, broker xác nhận theo mức độ bền đã chọn, lỗi được quan sát và throughput/latency nằm trong SLA. Hãy dùng checklist này như cổng kiểm tra trước production, sau đó tiếp tục đối chiếu metric thực tế để điều chỉnh cấu hình theo workload thay vì coi các giá trị ví dụ là mặc định tối ưu.
