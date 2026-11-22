# Cấu hình producer và consumer tách biệt trong Spring Kafka

## 1. Vì sao phải tách cấu hình producer và consumer?

Một ứng dụng dùng **Spring Kafka** có thể vừa **producer** (gửi bản ghi đến Kafka), vừa **consumer** (nhận bản ghi từ Kafka). Hai vai trò hoạt động trên cùng nền tảng, nhưng yêu cầu về độ tin cậy, hiệu năng, bảo mật và vận hành khác nhau.

Ví dụ một dịch vụ xử lý thanh toán:

```text
                                  payment-service
                   +-------------------------------------+
                   |                                     |
Payment commands   |  Consumer                          |
Kafka topic ------>|  @KafkaListener                     |
                   |        |                            |
                   |        v                            |
                   |  Validate + DB transaction          |
                   |        |                            |
                   |        v                            |
                   |  Producer                          |-----> payment-results
                   |  KafkaTemplate                      |       Kafka topic
                   |                                     |
                   +-------------------------------------+
```

Nếu dùng một khối cấu hình chung rồi áp cùng tham số cho cả hai phía, rất dễ hiểu sai:

- `acks`, `linger.ms`, `delivery.timeout.ms`, `enable.idempotence` chỉ có ý nghĩa với **producer**.
- `group.id`, `auto.offset.reset`, `enable.auto.commit`, `max.poll.records` chỉ có ý nghĩa với **consumer**.
- `concurrency` là lựa chọn của **listener container**, không phải số thread producer.
- `retries` của Kafka producer không giống retry nghiệp vụ trong listener hoặc retry gửi HTTP/DB.
- Các thuộc tính chung như `bootstrap.servers`, `security.protocol` có thể giống nhau nếu hai phía dùng cùng cluster, nhưng không nhất thiết phải giống khi kết nối các cluster hoặc tài khoản khác nhau.

**Cấu hình tách biệt** là đặt đúng tham số ở đúng thành phần, với trách nhiệm và chính sách vận hành rõ ràng. Tách biệt **không đồng nghĩa** lúc nào cũng phải tạo hai ứng dụng hoặc hai Kafka cluster.

### Sau bài này, bạn có thể

1. Tách `spring.kafka.producer.*`, `spring.kafka.consumer.*` và `spring.kafka.listener.*` trong Spring Boot.
2. Xác định khi nào dùng auto-configuration và khi nào cần các bean `ProducerFactory`, `ConsumerFactory`, `KafkaTemplate`, `ConcurrentKafkaListenerContainerFactory` riêng.
3. Triển khai ứng dụng consumer từ cluster A, producer sang cluster B mà không nhầm credentials, offset hoặc topic.
4. Hiểu ranh giới giữa producer delivery, listener processing, offset commit, retry, DLT và Kafka transaction.
5. Thiết kế profile, secrets, validation cấu hình, readiness, telemetry và kiểm thử độc lập cho hai phía.

**Phạm vi ví dụ:** Java 17+, Spring Boot 3.x và Spring Kafka 3.x. Tên property và API cụ thể cần được đối chiếu với minor version của stack thực tế; các ví dụ không đại diện cho mọi phiên bản Spring Kafka đã phát hành.

## 2. Bốn lớp cấu hình cần phân biệt

Một cấu hình Kafka trong ứng dụng Spring thường có nhiều lớp:

| Lớp | Thành phần | Mục đích |
|---|---|---|
| **Kafka client chung** | `bootstrap.servers`, TLS/SASL, DNS, client ID | Cách kết nối và xác thực |
| **Producer client** | `ProducerConfig`, `ProducerFactory`, `KafkaTemplate` | Gửi bản ghi, serializers, ack, retries, transaction |
| **Consumer client** | `ConsumerConfig`, `ConsumerFactory` | Đọc bản ghi, deserializers, group, fetch/poll, isolation |
| **Spring listener container** | `ConcurrentKafkaListenerContainerFactory`, `@KafkaListener` | Concurrency, ack mode, error handler, DLT/recovery |

Quan hệ:

```text
Spring Boot application
  |
  +-- Kafka configuration (common)
  |      bootstrap, common security
  |
  +-- Producer-specific config
  |      |
  |      +-- ProducerFactory
  |              |
  |              +-- KafkaTemplate
  |                      |
  |                      +-- send(...) -> Kafka broker
  |
  +-- Consumer-specific config
         |
         +-- ConsumerFactory
                 |
                 +-- ListenerContainerFactory
                         |
                         +-- @KafkaListener -> Kafka broker
```

Nếu dùng Spring Boot auto-configuration, Boot có thể tạo phần lớn các bean trên từ `spring.kafka.*`. Nếu ứng dụng khai báo bean tùy biến cùng type, một số auto-configured bean có thể **back off**. Vì vậy cần kiểm tra wiring thực sự thay vì tưởng rằng thêm một `ProducerFactory` tùy biến sẽ tự hoạt động song song với mọi bean mặc định.

## 3. Trường hợp phổ biến: cùng cluster, cấu hình riêng từng vai trò

Giả sử cả producer và consumer đều kết nối cluster Kafka chung. Ta nên dùng cấu hình phân cấp thay vì trộn mọi property vào một map không phân biệt vai trò.

```yaml
spring:
  application:
    name: payment-service

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[linger.ms]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000

    consumer:
      group-id: payment-commands-v1
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[max.poll.records]": 200
        "[max.poll.interval.ms]": 300000

    listener:
      ack-mode: record
      concurrency: 3
```

Đây là một cấu hình **minh họa**, không phải các giá trị tối ưu áp dụng mọi hệ thống. Dấu `${...}` trong ví dụ thực tế là cú pháp môi trường của Spring Boot, chẳng hạn `${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}`.

Ý nghĩa:

- `spring.kafka.bootstrap-servers`: kết nối chung nếu producer/consumer dùng cùng cluster.
- `spring.kafka.producer.*`: chính sách cho client **gửi** dữ liệu.
- `spring.kafka.consumer.*`: chính sách cho client **đọc** dữ liệu.
- `spring.kafka.listener.*`: hành vi container quản lý `@KafkaListener`.
- `properties`: chuyển các thuộc tính Kafka client nâng cao xuống thư viện Kafka; dạng key đặt trong dấu ngoặc vuông giúp Spring Boot binding map có tên chứa dấu chấm.

Chúng ta chưa đưa retry nghiệp vụ hoặc DLT vào YAML vì chúng thường cần **error handler/recoverer** được cấu hình riêng. Kafka producer retry và listener retry không phải một chức năng.

### 3.1. Thuộc tính chung và thuộc tính override

Ví dụ:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka-common:9092

    producer:
      bootstrap-servers: kafka-producer:9092

    consumer:
      bootstrap-servers: kafka-consumer:9092
```

Trong những phiên bản Boot hỗ trợ thuộc tính bootstrap riêng của từng vai trò, các cấu hình producer/consumer cụ thể có thể override giá trị chung. Điều này **không có nghĩa** chỉ cần đổi hai địa chỉ là đã hoàn thành cấu hình multi-cluster: credentials, truststore, ACL, topic admin, DLT và transaction cũng phải chọn đúng cluster.

Nếu dùng chung cluster và credentials, đặt địa chỉ và bảo mật ở cấp chung giúp giảm lặp. Nếu có **hai security domain độc lập**, đừng dựa vào những property chung vô tình bị kế thừa; thiết kế factory tách biệt và kiểm soát đầy đủ từng map cấu hình.

### 3.2. Không đặt nhầm thuộc tính Kafka

| Thuộc tính | Đúng chỗ | Dùng sai sẽ gây gì? |
|---|---|---|
| `acks=all` | Producer | Đặt bên consumer không đổi chính sách xác nhận gửi |
| `enable.idempotence=true` | Producer | Không làm listener xử lý message “đúng một lần” |
| `group.id` | Consumer | Producer không có consumer group để commit offset |
| `max.poll.records` | Consumer | Không điều khiển kích thước batch mà producer gửi |
| `auto.offset.reset` | Consumer | Không reset committed offset đang tồn tại |
| `ack-mode=record` | Listener container | Không đồng nghĩa Kafka producer `acks=all` |
| `concurrency=3` | Listener container | Không tự tạo 3 producer hoặc 3 partition |
| `transaction-id-prefix` | Producer/Spring transaction setup | Không tự tạo transaction xuyên DB và hai cluster |

**Nguyên tắc:** nếu không thể giải thích tham số ảnh hưởng đến **phía gửi, phía đọc hay phía xử lý callback**, chưa nên đặt nó ở cấu hình chung.

## 4. Producer: cấu hình ưu tiên dữ liệu được gửi bền vững

Producer có nhiệm vụ serialize key/value, tìm partition và gửi record. Lời gọi gửi thành công ở phía Java **không đồng nghĩa** record đã được broker xác nhận.

Một số property quan trọng:

| Property | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| `bootstrap.servers` | Broker ban đầu để lấy metadata | Phải trỏ đúng cluster |
| `key.serializer` | Chuyển key sang bytes | Key ảnh hưởng partitioning |
| `value.serializer` | Chuyển value sang bytes | Phải phù hợp contract consumer |
| `acks` | Mức xác nhận từ broker | `all` ưu tiên durability so với `0` |
| `enable.idempotence` | Hạn chế duplicate do producer retry trong điều kiện Kafka hỗ trợ | Không dedup các lần gửi nghiệp vụ mới |
| `retries` | Kafka client thử gửi lại với lỗi retryable | Bị giới hạn bởi delivery timeout/policy |
| `delivery.timeout.ms` | Hạn tối đa để gửi được record theo client | Cần phối hợp với request timeout/linger |
| `request.timeout.ms` | Timeout cho request chờ phản hồi | Không được hiểu là job timeout |
| `linger.ms` | Thời gian gom record trước khi gửi trong điều kiện phù hợp | Trade-off throughput và latency |
| `batch.size` | Kích thước buffer tối đa theo batch gửi đến partition, tính bằng bytes | **Không phải số Kafka records hay Spring Batch chunk size** |
| `compression.type` | Nén payload | Đổi CPU lấy network/disk |
| `max.in.flight.requests.per.connection` | Số request chưa có ACK trên mỗi kết nối | Phải phù hợp idempotence/ordering |

### 4.1. `acks=all` chưa phải exactly-once toàn ứng dụng

`acks=all` yêu cầu broker leader chờ xác nhận theo chính sách ISR, đem lại khả năng lưu bền vững tốt hơn `acks=0` trong tình huống phù hợp. Tuy nhiên kết quả còn phụ thuộc replication factor, `min.insync.replicas`, tình trạng ISR và vận hành cluster.

`enable.idempotence=true` giúp producer tránh một số duplicate sinh bởi **retry nội bộ của Kafka producer** theo cơ chế producer ID/sequence. Nó **không** chứng minh rằng:

- Ứng dụng không gọi `KafkaTemplate.send(...)` hai lần cho cùng sự kiện.
- Database đã commit hoặc chưa commit.
- Consumer chỉ xử lý một lần.
- Không có duplicate qua lần restart ứng dụng với một luồng gửi nghiệp vụ mới.
- Giao dịch được bảo đảm đồng thời trên hai Kafka cluster.

Nếu producer ứng dụng có thể gửi lại event sau crash, cần một **event ID/idempotency key** và nơi lưu trạng thái đủ bền vững, thường kết hợp transactional outbox.

### 4.2. Tối ưu throughput nhưng không đánh mất độ ổn định

Ví dụ một producer ghi audit volume lớn có thể thử `linger.ms` cao hơn hoặc bật compression; producer gửi lệnh thanh toán thời gian thực lại có thể ưu tiên độ trễ thấp.

Cấu hình cần được benchmark theo payload, số partition, network latency, broker quota và yêu cầu SLA. Không sao chép cùng một giá trị `batch.size` cho mọi loại topic mà không biết kích thước message và mục tiêu latency.

## 5. Consumer: cấu hình ưu tiên xử lý và offset an toàn

Consumer nhận record theo consumer group; Kafka lưu các vị trí offset đã commit cho mỗi group/topic/partition.

Những property quan trọng:

| Property | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| `group.id` | Định danh consumer group | Ảnh hưởng phân chia partition và committed offsets |
| `key.deserializer` | Chuyển bytes sang key | Phải tương thích producer |
| `value.deserializer` | Chuyển bytes sang value | Lỗi deserialization có thể xảy ra trước listener |
| `enable.auto.commit` | Kafka client tự động commit offset theo lịch | Thường đặt `false` cho listener cần quản lý theo kết quả xử lý |
| `auto.offset.reset` | Vị trí bắt đầu **khi không có offset hợp lệ** | Không phải nút replay mọi lần chạy |
| `max.poll.records` | Số record tối đa được trả về từ một lần poll | Không bằng số thread hoặc số partition |
| `max.poll.interval.ms` | Giới hạn khoảng cách giữa các lần poll cho xử lý kiểu poll | Listener chậm có thể khiến group rebalance |
| `fetch.min.bytes` / `fetch.max.wait.ms` | Trade-off batch fetch và latency | Tùy tải |
| `isolation.level` | `read_uncommitted` hoặc `read_committed` | `read_committed` bỏ qua bản ghi thuộc Kafka transaction bị abort |
| `client.id` | Định danh để quan sát client | Nên tách theo vai trò khi cần metrics/diagnostics |

`enable-auto-commit=false` là lựa chọn thường gặp khi dùng Spring Kafka listener container với ack mode rõ ràng. Khi đó **container** chịu trách nhiệm điều phối commit offset theo ack mode và error handler. Không suy ra rằng offset commit hoàn toàn bị tắt chỉ vì client property này là `false`.

### 5.1. `auto.offset.reset=earliest` không reset committed offset

Ví dụ:

```text
Topic: payment-commands, partition 0

Kafka offsets:
0 1 2 3 4 5 6 7 8 9

Consumer group payment-service-v1 đã commit offset 7
(nghĩa là vị trí tiếp theo = 7).

Restart consumer cùng group:
  -> tiếp tục tại committed position, không tự về offset 0.

Consumer group hoàn toàn mới, chưa có committed offset:
  auto.offset.reset=earliest -> bắt đầu từ earliest còn được giữ.
```

Nếu muốn replay một group đang tồn tại, cần quy trình seek/reset offset có kiểm soát và hiểu side effect trùng. Đổi `earliest` sang `latest` không phải phương pháp chống lỗi duplicate.

### 5.2. Commit offset sau xử lý tạo at-least-once, không tạo exactly-once DB

Khi listener xử lý một record và commit offset **sau** khi nghiệp vụ hoàn tất, có một khoảng sự cố:

```text
Consumer nhận event E-101
          |
          v
Update database thành công
          |
          v
JVM chết trước offset commit
          |
          v
Kafka giao lại E-101 sau restart/rebalance
```

Đây là lý do **at-least-once delivery** cần idempotent business processing. Bảng inbox/unique business event ID có thể ngăn cập nhật DB hai lần, ngay cả khi consumer đọc lại record.

Nếu offset được commit **trước** side effect hoàn tất, rủi ro ngược lại là bỏ sót sự kiện khi process chết. Vì vậy cần mô tả rõ điểm commit trong thiết kế và kiểm thử failure.

## 6. Listener container: nơi định nghĩa retry/ack/concurrency cho consumer

Trong Spring Kafka, client `KafkaConsumer` chỉ đọc message và tham gia group. `@KafkaListener` được framework chạy trong **listener container**; các lựa chọn như ack mode, concurrency và error handler được áp dụng tại lớp này.

Ví dụ cùng cluster, có thể để Spring Boot cấu hình container từ:

```yaml
spring:
  kafka:
    listener:
      ack-mode: record
      concurrency: 3
```

`record` thường tương ứng với commit sau khi record được listener xử lý thành công theo semantics container; khi listener ném exception, error handler quyết định retry, seek/recovery hoặc chuyển DLT.

Các mode khác gồm `batch`, `manual` và `manual_immediate` với hành vi cụ thể. Đừng đổi `ack-mode` chỉ để giảm số lần commit mà không hiểu lỗi/rebalance/duplicate.

### 6.1. Concurrency không thể vượt lợi ích của số partition

Giả sử topic có 3 partition và consumer group có một listener container `concurrency=8`. Trong group này, mỗi partition tại một thời điểm chỉ được gán cho một consumer, nên không thể có 8 consumer cùng thực sự đọc từ 3 partition đó. Một số consumer sẽ rảnh.

Ngược lại, khi tăng số partition, thứ tự record được Kafka bảo đảm **trong một partition**, không phải thứ tự toàn topic. Nếu key là `paymentId` và cần giữ thứ tự cập nhật của mỗi payment, producer nên chọn key ổn định để các record cùng payment được route nhất quán, trong điều kiện partitioning và số partition không thay đổi theo cách ảnh hưởng phân phối.

Tài liệu cấu hình nên ghi rõ số partition và lý do chọn concurrency, thay vì mặc định càng nhiều thread càng tốt.

## 7. Ví dụ Java tối giản với Spring Boot auto-configuration

Khi cả producer và consumer dùng một cluster, không bắt buộc tự tạo từng bean factory. Spring Boot có thể dựng `KafkaTemplate` và default listener container từ YAML.

### 7.1. Producer gọi `KafkaTemplate`

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public final class PaymentResultPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(PaymentResultPublisher.class);

    private final KafkaTemplate<String, String> kafkaTemplate;

    public PaymentResultPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String paymentId,
            String jsonPayload) {

        CompletableFuture<SendResult<String, String>> future =
                kafkaTemplate.send(
                        "payment-results.v1",
                        paymentId,
                        jsonPayload
                );

        future.whenComplete((result, error) -> {
            if (error != null) {
                log.error(
                        "Kafka send failed for paymentId={}",
                        paymentId,
                        error
                );
            } else {
                log.info(
                        "Kafka record acknowledged: topic={}, "
                                + "partition={}, offset={}",
                        result.getRecordMetadata().topic(),
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset()
                );
            }
        });

        return future;
    }
}
```

Trong Spring Kafka 3.x, `KafkaTemplate.send(...)` trả `CompletableFuture<SendResult<K,V>>`. Lời gọi `send` chỉ **bắt đầu thao tác gửi bất đồng bộ**; business code muốn bảo đảm có kết quả phải quan sát future hoặc dùng outbox nếu cần giao bền vững qua crash.

**Không đặt một lời gọi `send(...).get()` blocking kéo dài trong mọi listener** chỉ để “đảm bảo Kafka đã gửi”, vì có thể làm consumer chậm, vượt `max.poll.interval.ms` và giảm throughput. Nếu flow cần chờ có giới hạn, phải thiết kế timeout, error path và giới hạn tải rõ ràng.

### 7.2. Consumer dùng `@KafkaListener`

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public final class PaymentCommandListener {

    private final PaymentCommandService service;

    public PaymentCommandListener(PaymentCommandService service) {
        this.service = service;
    }

    @KafkaListener(topics = "payment-commands.v1")
    public void onMessage(String jsonPayload) {
        service.handle(jsonPayload);
    }
}
```

`PaymentCommandService` là service nghiệp vụ giả định. Nếu `service.handle(...)` ném exception, error handler/container được cấu hình sẽ quyết định kết quả. **Không catch mọi exception rồi return bình thường** nếu nghiệp vụ chưa thực sự hoàn tất, vì container có thể coi record đã xử lý thành công và commit offset.

Nếu consumer cần xác nhận thủ công, cấu hình `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE` và nhận `Acknowledgment` trong listener. Cần quản lý rõ thời điểm `acknowledge()` và các điều kiện retry/recovery.

## 8. Khi nào nên tạo các bean riêng?

Auto-configuration đủ cho nhiều ứng dụng chỉ có **một Kafka connection profile**. Các bean tường minh hữu ích khi:

- Consumer từ cluster **A** và producer sang cluster **B**.
- Hai phía dùng **different SASL credentials/truststores**.
- Có hai producer gửi các loại payload khác nhau, với serializer, timeout hoặc transaction policy khác.
- Có hai consumer group/topic cần những container factory hoặc error handler riêng.
- Có hệ thống DLT nằm ở cluster nguồn, còn kết quả business gửi sang cluster đích.
- Không muốn thay một cấu hình global rồi vô tình làm lệch hành vi của cả hai phía.

Tách biệt ở cấp bean giúp chỉ rõ **factory nào thuộc cluster nào**, nhưng yêu cầu kiểm tra wiring, qualifier và các trường hợp Spring Boot auto-config back off.

## 9. Cấu hình hai cluster độc lập

Giả sử:

- `inbound Kafka`: cluster A, chứa `payment-commands.v1`.
- `outbound Kafka`: cluster B, nhận `payment-results.v1`.
- Consumer dùng `inbound-consumer-group`.
- Producer gửi sang cluster B, không dùng group ID.
- Hai phía có thể cần thông tin xác thực khác nhau.

### 9.1. Application YAML giữ các vùng cấu hình riêng

```yaml
app:
  kafka:
    inbound:
      bootstrap-servers: ${KAFKA_INBOUND_BOOTSTRAP}
      group-id: payment-commands-processor-v1
      topic: payment-commands.v1
      concurrency: 3

    outbound:
      bootstrap-servers: ${KAFKA_OUTBOUND_BOOTSTRAP}
      topic: payment-results.v1
```

Các tên property `app.kafka.inbound.*` và `app.kafka.outbound.*` là **cấu hình riêng do ứng dụng định nghĩa**, không phải các Spring Boot Kafka properties tự động tạo factory. Ta cần code đọc và truyền chúng vào `ProducerFactory` và `ConsumerFactory`.

Để ví dụ tập trung vào tách vai trò, phần Java sau sử dụng serializer/deserializer `String`. Cấu hình xác thực sẽ được thêm tại từng map ở mục bảo mật.

### 9.2. ProducerFactory và KafkaTemplate dành riêng cho outbound

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
public class OutboundKafkaConfiguration {

    @Bean("outboundProducerFactory")
    ProducerFactory<String, String> outboundProducerFactory(
            @Value("${app.kafka.outbound.bootstrap-servers}")
            String bootstrapServers) {

        Map<String, Object> properties = new HashMap<>();

        properties.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers);
        properties.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(
                ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        properties.put(
                ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
        properties.put(
                ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
        properties.put(
                ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean("outboundKafkaTemplate")
    KafkaTemplate<String, String> outboundKafkaTemplate(
            @Qualifier("outboundProducerFactory")
            ProducerFactory<String, String> producerFactory) {

        return new KafkaTemplate<>(producerFactory);
    }
}
```

Trong ví dụ này, `outboundKafkaTemplate` được ràng buộc với `outboundProducerFactory` bằng `@Qualifier`. Không phụ thuộc bean mặc định `kafkaTemplate`, vì bean mặc định có thể trỏ đến một cluster khác hoặc không được tạo khi ứng dụng khai báo custom `ProducerFactory`.

### 9.3. ConsumerFactory và listener container dành riêng cho inbound

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
@EnableKafka
public class InboundKafkaConfiguration {

    @Bean("inboundConsumerFactory")
    ConsumerFactory<String, String> inboundConsumerFactory(
            @Value("${app.kafka.inbound.bootstrap-servers}")
            String bootstrapServers,
            @Value("${app.kafka.inbound.group-id}")
            String groupId) {

        Map<String, Object> properties = new HashMap<>();

        properties.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers);
        properties.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                groupId);
        properties.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        properties.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(
                ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 200);

        return new DefaultKafkaConsumerFactory<>(properties);
    }

    @Bean("inboundListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String>
    inboundListenerFactory(
            @Qualifier("inboundConsumerFactory")
            ConsumerFactory<String, String> consumerFactory,
            @Value("${app.kafka.inbound.concurrency:3}")
            int concurrency) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(concurrency);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD);

        // Sau khi lỗi được xử lý theo policy, DefaultErrorHandler
        // mặc định có cơ chế recover/log; chưa tự tạo DLT.
        factory.setCommonErrorHandler(
                new DefaultErrorHandler(
                        new FixedBackOff(1_000L, 2L)));

        return factory;
    }
}
```

`FixedBackOff(1_000L, 2L)` minh họa hai lượt retry sau lần xử lý lỗi ban đầu, với khoảng chờ 1 giây giữa các lần theo policy. Đây không phải tiêu chuẩn chung cho mọi lỗi. Một số exception có thể được phân loại non-retryable bởi error handler; khi hết retries, mặc định recoverer có thể log và coi lỗi đã được recover theo semantics tương ứng. **Chưa có DLT tự động** chỉ vì đã tạo `DefaultErrorHandler` như trên.

Nếu một lỗi nghiệp vụ bắt buộc phải vào DLT hoặc khiến processing dừng, cần cấu hình recoverer/classification phù hợp và kiểm thử hành vi offset sau recovery.

### 9.4. Gắn đúng template và listener factory

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Service
public final class OutboundEventPublisher {

    private final KafkaTemplate<String, String> template;

    public OutboundEventPublisher(
            @Qualifier("outboundKafkaTemplate")
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public void sendPaymentResult(
            String paymentId, String jsonPayload) {

        template.send(
                "payment-results.v1",
                paymentId,
                jsonPayload
        ).whenComplete((result, failure) -> {
            if (failure != null) {
                // Ghi log + recovery mechanism của ứng dụng.
                // Không coi event là đã giao thành công.
                reportPublicationFailure(paymentId, failure);
            }
        });
    }
}

@Component
public final class InboundPaymentListener {

    private final PaymentProcessingService service;

    public InboundPaymentListener(PaymentProcessingService service) {
        this.service = service;
    }

    @KafkaListener(
            topics = "payment-commands.v1",
            containerFactory = "inboundListenerFactory")
    public void handle(String payload) {
        service.process(payload);
    }
}
```

`PaymentProcessingService` và `reportPublicationFailure(...)` là các thành phần nghiệp vụ minh họa, cần được ứng dụng định nghĩa. Đoạn code thể hiện điểm chính: producer **không dùng consumer group**, consumer **không dùng producer acknowledgments**, và mỗi phía nhận đúng factory của nó.

Trong một hệ thống đáng tin cậy, `sendPaymentResult(...)` trả `void` mà không chờ future chỉ phù hợp cho đường best-effort hoặc khi có outbox/reconciliation bền vững ở lớp khác. Nếu kết quả gửi ảnh hưởng một quyết định nghiệp vụ, contract nên phản ánh việc gửi bất đồng bộ hoặc persist một outbound event trước khi xác nhận xử lý.

## 10. Tránh cấu hình mặc định vô tình kết nối sai cluster

Khi ứng dụng có nhiều Kafka bean cùng type, không nên dựa vào tên mặc định hoặc chỉ autowire theo type mà không xem wiring.

Ví dụ:

```java
@Autowired
private KafkaTemplate<String, String> kafkaTemplate;
```

Nếu có nhiều template, Spring có thể báo ambiguous dependency hoặc chọn bean theo cơ chế giải quyết phù hợp; kết quả không nên được giả định để phân biệt cluster.

Hãy đặt tên thể hiện vai trò:

```text
inboundConsumerFactory
inboundListenerFactory
inboundDlqProducerFactory    (nếu ghi DLT vào cluster nguồn)
inboundDlqKafkaTemplate

outboundProducerFactory
outboundKafkaTemplate
```

Với nhiều listener:

```java
@KafkaListener(
    topics = "payment-commands.v1",
    containerFactory = "inboundListenerFactory")
public void onCommand(String value) {
    // ...
}
```

**Không dùng một `KafkaTemplate` cho tất cả DLT và outbound event** chỉ vì cả hai đều thực hiện `send`. Nếu DLT thuộc cluster nguồn A nhưng `outboundKafkaTemplate` trỏ cluster B, recoverer có thể gửi lỗi sang sai hạ tầng hoặc gặp unknown topic/ACL.

### 10.1. Vì sao nên có cấu hình kiểm tra kết nối riêng?

Khi kết nối sai cluster, ứng dụng có thể vẫn khởi động thành công vì Kafka clients kết nối bất đồng bộ. Một health endpoint `UP` không tự chứng minh mọi topic, credentials và quyền ghi/đọc đều đúng.

Cần kiểm tra:

- Consumer có thể join đúng group trên cluster A?
- Topic inbound có tồn tại và số partition như dự kiến?
- Producer có thể publish vào topic outbound ở cluster B?
- DLT nếu có được cấp quyền ghi ở cluster thực sự chứa nó?
- Kafka admin/metadata client có dùng đúng bootstrap servers và credentials?
- Readiness dựa trên policy kết nối phù hợp, không tự fail toàn dịch vụ vì một downstream tạm không sẵn sàng nếu kiến trúc cho phép queue lại.

### 10.2. Không nhầm KafkaAdmin với factory của client

`KafkaAdmin` phục vụ thao tác quản lý topic/config theo cluster. Trong kiến trúc nhiều cluster, nếu khai báo một `NewTopic` với một `KafkaAdmin` mặc định mà không kiểm soát đích, topic có thể được quản lý ở **cluster sai**.

Trong production, nhiều tổ chức quản lý topic bằng IaC/platform team thay vì để mọi service tự tạo. Dù chọn cách nào, cần ghi rõ ownership, cluster, retention, partition count, replication, min ISR và ACL của từng topic.

## 11. Tách security protocol, credentials và ACL

Hai Kafka client có thể dùng cùng broker nhưng **khác principal**, ví dụ producer chỉ có quyền `WRITE` và consumer chỉ có quyền `READ` trên topic tương ứng. Điều này giảm phạm vi thiệt hại khi credential bị lộ.

Ví dụ thiết kế quyền:

| Vai trò | Cluster | Principal | Quyền tối thiểu minh họa |
|---|---|---|---|
| Inbound consumer | A | `payment-reader` | Read topic `payment-commands.v1`, read/join group phù hợp |
| Outbound producer | B | `payment-writer` | Write/describe topic `payment-results.v1` |
| Inbound DLT producer | A | `payment-dlt-writer` | Write topic `payment-commands.v1-dlt` |
| Topic operator | A/B | `kafka-admin` | Quyền quản trị riêng, không dùng trong app nếu không cần |

Kafka ACL và quyền cụ thể phụ thuộc broker, cơ chế auth và nền tảng managed Kafka. Không cấp producer quyền đọc mọi topic hoặc consumer quyền quản trị cluster chỉ để tránh lỗi permission.

### 11.1. Cấu hình SASL_SSL minh họa

Một số client Kafka cần:

```java
import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.common.config.SaslConfigs;

properties.put(
        CommonClientConfigs.SECURITY_PROTOCOL_CONFIG,
        "SASL_SSL");

properties.put(
        SaslConfigs.SASL_MECHANISM,
        "SCRAM-SHA-512");

properties.put(
        SaslConfigs.SASL_JAAS_CONFIG,
        jaasConfigurationFromSecretProvider);
```

`jaasConfigurationFromSecretProvider` đại diện cho một chuỗi cấu hình được lấy từ cơ chế secret/config bảo mật của ứng dụng, không phải tên biến Kafka API. Mỗi factory producer/consumer phải có **đúng authentication profile** của nó. Khi dùng mTLS hoặc managed identity/OAuth, các property sẽ khác.

Cần đặc biệt chú ý:

- Không đặt password/token vào `JobParameters`, log hoặc Git.
- Không ghi nguyên map `properties` ra log debug nếu chứa JAAS password.
- Đặt bootstrap/truststore theo đúng môi trường và cluster.
- Có chính sách rotate credentials, không cần redeploy code nếu hạ tầng cho phép.
- Các TLS certificate SAN/hostname verification phải phù hợp đích broker.
- Dùng network egress allowlist và quyền Kubernetes/service account tối thiểu.

**Không nên dùng chung một biến `KAFKA_PASSWORD` cho hai principal** khi mục tiêu là tách biệt security. Thay vào đó đặt secret reference riêng theo role.

## 12. Serialization phải tách theo contract topic

Producer quyết định dữ liệu được mã hóa ra bytes như thế nào. Consumer cần biết cách giải mã tương thích. Đây là **hợp đồng dữ liệu của topic**, không phải một thuộc tính có thể thay đổi tùy tiện trong profile.

Ví dụ một producer gửi JSON string đơn giản; consumer dùng `StringDeserializer` và chuyển JSON trong service. Đây là cách dễ triển khai nhưng cần validation/schema riêng.

Với Spring Kafka JSON serializer/deserializer:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer

    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.kafka.events.PaymentCommand
        "[spring.json.trusted.packages]": com.example.kafka.events
        "[spring.json.use.type.headers]": false
```

Đây là một **ví dụ thay thế cho trường hợp single-cluster**, không phải cấu hình dùng nguyên cùng lúc với các factory `String` ở phần multi-cluster. `PaymentCommand` là DTO giả định trong package của ứng dụng.

Những điểm cần hiểu:

- `JsonSerializer` có thể thêm type headers nếu được cấu hình tương ứng.
- `JsonDeserializer` cần biết type dự kiến hoặc type metadata hợp lệ.
- Đặt `trusted.packages=*` mà không đánh giá security sẽ mở rộng phạm vi class có thể được xem xét khi deserialize.
- `ErrorHandlingDeserializer` giúp đưa một số lỗi deserialization vào error-handling path của Spring Kafka thay vì để lỗi xảy ra trước listener mà không có thông tin phục hồi phù hợp.
- Consumer không nhất thiết phải tin type headers do bên ngoài gửi; có thể cấu hình target type rõ và không dùng headers nếu topic có schema thống nhất.
- Nếu producer/consumer dùng Avro, Protobuf hoặc Schema Registry, cả hai phía cần cùng schema evolution contract, credentials và cấu hình registry tương ứng.

### 12.1. Data contract độc lập với Java class

Đừng mặc định tất cả service cùng phiên bản Java class `com.example.PaymentCommand`. Trong distributed system, producer và consumer có thể deploy độc lập. Nên ghi:

```text
Topic: payment-commands.v1
Key: paymentId (String, nonblank)
Value: PaymentCommand version 1
Required fields: eventId, paymentId, amount, currency
Compatibility: backward-compatible schema evolution
Maximum payload size: 256 KiB (ví dụ)
PII: không chứa full card number
```

Các giá trị là giả định minh họa. Chúng cần được thực thi bằng validation và quy tắc schema, không chỉ bằng comment.

## 13. Retry của producer và retry của consumer là hai chuyện

Một câu hỏi vận hành rất phổ biến: “Đã bật retries rồi, sao message vẫn bị mất hoặc xử lý trùng?”

Vì có nhiều tầng retry:

| Retry | Được kích hoạt ở đâu? | Mục đích | Rủi ro |
|---|---|---|---|
| **Producer client retry** | KafkaProducer khi gặp lỗi retryable | Gửi record đến broker | Timeout/unknown outcome, app gửi lại có thể tạo duplicate |
| **Application publish retry** | Service sau khi future thất bại | Tạo lại yêu cầu publish nghiệp vụ | Nếu lần trước đã tới broker nhưng mất ACK, có thể gửi trùng |
| **Listener processing retry** | `DefaultErrorHandler` hoặc cơ chế retry listener | Xử lý record thất bại | Cùng record chạy business code nhiều lần |
| **DLT recovery** | Recoverer khi retries cạn | Chuyển record lỗi để xử lý riêng | DLT send cũng có thể lỗi |
| **Database retry** | Transaction/business service | Phục hồi lỗi DB tạm thời | Side effect ngoài DB có thể lặp |
| **Message broker redelivery** | Rebalance, offset chưa commit | Cung cấp lại record | Consumer phải idempotent |

Do đó, một chính sách đáng tin cậy thường có hai lớp:

- **Producer:** idempotence, `acks=all`, timeout phù hợp, quan sát send future, outbox nếu bắt buộc giao event sau business commit.
- **Consumer:** commit offset sau xử lý theo semantics đã định, retry có giới hạn, DLT hoặc stop khi lỗi không thể xử lý, idempotent business action.

### 13.1. Ví dụ consumer có lỗi validation không retry

Giả sử một record không có `paymentId`. Retry thêm 10 lần không làm payload tự sửa. Có thể phân loại exception đó là non-retryable và chuyển sang DLT/quarantine.

Ngược lại, lỗi database connection tạm thời có thể retry với backoff. **Không cấu hình retry mọi `Exception`** nếu nó khiến một poison message chiếm partition quá lâu hoặc tạo side effect lặp.

### 13.2. DLT cần producer có thể ghi về đúng cluster

Nếu consumer đọc cluster A và business output gửi cluster B, nhưng DLT `payment-commands.v1-dlt` nằm ở cluster A:

```text
Cluster A                         Cluster B
----------                        ----------
payment-commands                 payment-results
       |                                 ^
       v                                 |
 inbound consumer                  outbound producer
       |
       +-- recover failed record
                   |
                   v
          inbound DLT producer
            -> Cluster A
```

Cần một `KafkaTemplate` thứ hai trỏ cluster A dành cho DLT hoặc một routing setup được thiết kế rõ. **Không** truyền `outboundKafkaTemplate` (cluster B) vào `DeadLetterPublishingRecoverer` nếu DLT dự kiến nằm trên cluster A.

Ví dụ khung:

```java
// Chỉ minh họa wiring: inboundDltTemplate phải trỏ cluster A.
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(inboundDltTemplate);

DefaultErrorHandler handler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L));
```

Ngoài code cần xác định topic đích, partition mapping, ACL, handling của serialized error, thời gian retention và hành vi khi DLT publish thất bại. Việc recovery có thể được xem là đã xử lý record theo semantics container; nếu DLT gửi lỗi và recoverer không báo/không ném phù hợp, có nguy cơ mất đường xử lý sự cố.

## 14. Offset commit: ghi rõ mode thay vì chỉ đặt một boolean

`enable-auto-commit=false` không tự trả lời “offset được commit lúc nào?”. Có các lựa chọn của listener container.

### 14.1. `AckMode.RECORD`

Với record listener, container commit offset phù hợp sau khi mỗi record được xử lý thành công theo semantics container. Phù hợp với các hệ thống muốn dễ suy luận tiến độ và không cần ack thủ công.

### 14.2. `AckMode.BATCH`

Container commit theo nhóm records nhận được từ một `poll` sau khi processing theo cơ chế tương ứng. Có thể giảm overhead nhưng độ rộng của vùng xử lý lặp sau crash/rebalance có thể lớn hơn.

### 14.3. `AckMode.MANUAL` và `MANUAL_IMMEDIATE`

Listener nhận `Acknowledgment` và gọi `acknowledge()` vào thời điểm do ứng dụng kiểm soát. Ví dụ:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;

@KafkaListener(
        topics = "payment-commands.v1",
        containerFactory = "manualAckListenerFactory")
public void onMessage(
        String payload,
        Acknowledgment acknowledgment) {

    paymentService.processIdempotently(payload);
    acknowledgment.acknowledge();
}
```

Phải cấu hình `manualAckListenerFactory` với ack mode tương ứng; đoạn trên không thể dùng nguyên với factory ở mục trước đang `AckMode.RECORD`.

**Không đặt `acknowledge()` vào `finally`** nếu chưa xác nhận nghiệp vụ thành công. Lệnh ack cũng không bảo đảm không có redelivery trong mọi tình huống crash; cần kết hợp idempotency.

### 14.4. At-least-once vẫn có duplicate

Khi DB commit thành công nhưng offset chưa được commit, record có thể giao lại. Đó là tình huống bình thường trong kiến trúc at-least-once. Hãy lưu `eventId` ở inbox cùng transaction với thay đổi nghiệp vụ để nhận diện replay.

Nếu business action là gọi API không idempotent, chỉ đổi ack mode thường **không đủ** để đạt tính đúng đắn.

## 15. Kafka transactions và giới hạn exactly-once

Producer Kafka có thể tham gia Kafka transaction trong các cấu hình phù hợp; consumer `isolation.level=read_committed` chỉ trả record đã commit từ những producer transactional và cũng đọc record nontransactional bình thường.

Spring Kafka hỗ trợ mẫu read-process-write có transaction và gửi consumer offsets vào Kafka transaction khi được thiết lập đúng. Mẫu này có thể đạt **Kafka-to-Kafka exactly-once processing semantics** trong phạm vi điều kiện của Kafka transaction.

Tuy nhiên cần phân biệt:

- Producer idempotence ≠ business exactly once.
- Kafka transaction ≠ một giao dịch atomic với PostgreSQL tự động.
- Kafka transaction trên cluster B **không** bao trùm việc consumer đọc offsets từ cluster A.
- `read_committed` của consumer không tự khiến việc ghi database và offset commit trở thành một transaction.
- Nếu gửi email/HTTP, transaction Kafka không rollback những side effect đó.

### 15.1. Vì sao cross-cluster cần thiết kế khác?

Giả sử consumer đọc cluster A, producer gửi cluster B:

```text
Cluster A: consumed offset X
           |
           v
Application processes
           |
           v
Cluster B: produced record Y
```

Kafka không cung cấp một transaction duy nhất bao phủ offset của cluster A và record gửi cluster B. Nếu application crash giữa hai hành động, cần chịu được replay hoặc missing acknowledgment theo policy. Thường dùng **transactional inbox/outbox**, idempotent keys và reconciliation ở tầng ứng dụng.

Đừng bật một `transaction-id-prefix` rồi tuyên bố có exactly-once liên cluster. Trong hệ thống có transaction manager khác nhau, cần xem thứ tự commit, rủi ro crash và khả năng phục hồi cụ thể.

### 15.2. Khi nào nên dùng outbox?

Đối với xử lý nghiệp vụ cần ghi DB và publish sự kiện:

```text
Consumer from cluster A
          |
          v
DB transaction:
  upsert business state
  insert inbox eventId (dedup)
  insert outbox eventId + payload
  COMMIT
          |
          v
Outbox publisher -> cluster B
          |
          v
Consumer downstream dedup eventId
```

Nếu publisher crash sau khi Kafka B nhận event nhưng trước khi mark outbox delivered, event có thể được gửi lại. Đây là **at-least-once delivery với idempotent consumer**, không tự biến thành end-to-end exactly-once.

## 16. Profile môi trường: không copy configuration không kiểm soát

Một ứng dụng có thể triển khai trên `local`, `staging` và `production`. Nên phân biệt:

- **Bất biến theo code:** client role, contract topic, serializer type, retry classification logic.
- **Thay đổi theo môi trường:** bootstrap servers, credentials, pool/quota, concurrency, topic prefix nếu có.
- **Thay đổi theo workload:** fetch, linger, compression, timeout, concurrency, khi được đo và duyệt.
- **Thay đổi theo vận hành:** readiness/pausing, feature flag chuyển traffic, nhưng không được làm mất contract.

Ví dụ:

```yaml
# application.yml (defaults chung, không lưu secrets)
app:
  kafka:
    inbound:
      group-id: payment-commands-processor-v1
      topic: payment-commands.v1
      concurrency: 2
    outbound:
      topic: payment-results.v1
```

```yaml
# application-prod.yml (cấu hình theo production)
app:
  kafka:
    inbound:
      bootstrap-servers: ${KAFKA_INBOUND_BOOTSTRAP}
      concurrency: 4
    outbound:
      bootstrap-servers: ${KAFKA_OUTBOUND_BOOTSTRAP}
```

Đây là các property ứng dụng tự định nghĩa; Java factory phải đọc chúng. Không commit username/password hoặc nội dung JAAS thật vào profile.

### 16.1. Không dùng default local trong production cho endpoint quan trọng

Một cấu hình dạng:

```yaml
app:
  kafka:
    outbound:
      bootstrap-servers: ${KAFKA_OUTBOUND_BOOTSTRAP:localhost:9092}
```

thuận tiện cho phát triển, nhưng nếu thiếu env var ở production thì producer có thể lặng lẽ thử kết nối broker local hoặc kết nối sai môi trường.

Với endpoint quan trọng, nên **không có fallback localhost trong production**; thiếu cấu hình phải làm ứng dụng fail startup hoặc fail readiness rõ ràng. Có thể dùng default local chỉ trong profile phát triển.

### 16.2. Ghi rõ topic ownership

Tên topic có thể tách theo môi trường (`dev.payment-results.v1`) hoặc mỗi môi trường một cluster riêng (`payment-results.v1`). Bất kể cách chọn, contract phải ghi topic thực tế và cluster. Không ghép prefix bằng chuỗi thiếu kiểm soát rồi tạo topic trên môi trường sai.

## 17. Quản lý property bằng `@ConfigurationProperties`

Với ứng dụng lớn, hàng chục `@Value` khó bảo trì. Có thể bind những property ứng dụng như `app.kafka.inbound.*` và `app.kafka.outbound.*` vào các cấu hình typed.

Ví dụ sử dụng Java record và Spring Boot configuration properties:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.kafka")
public record KafkaRolesProperties(
        Inbound inbound,
        Outbound outbound
) {
    public record Inbound(
            String bootstrapServers,
            String groupId,
            String topic,
            int concurrency
    ) {
    }

    public record Outbound(
            String bootstrapServers,
            String topic
    ) {
    }
}
```

Đăng ký:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(KafkaRolesProperties.class)
public class KafkaRolesPropertiesConfiguration {
}
```

Sau đó các bean factory có thể nhận `KafkaRolesProperties` và dùng:

```java
String inboundServers =
        properties.inbound().bootstrapServers();

String outboundServers =
        properties.outbound().bootstrapServers();
```

Đây là phần giới thiệu binding typed. Trong production cần thêm validation:

- `inbound` và `outbound` không được null.
- Bootstrap không được trống, topic có tên hợp lệ.
- `concurrency` > 0, nằm trong giới hạn vận hành.
- `groupId` không trống và ổn định qua deploy nếu không có chủ đích thay group.
- Nếu yêu cầu cluster A/B khác nhau, xác định điều đó bằng contract thay vì chỉ so sánh chuỗi broker.
- Security profile tham chiếu đúng principal của từng role.

Có thể dùng Jakarta Bean Validation `@NotBlank`, `@NotNull`, `@Min(1)` với `@Validated` và dependency validation phù hợp. Spring Boot 3 dùng namespace `jakarta.validation`. Validation sớm hữu ích vì lỗi cấu hình Kafka client đôi khi chỉ biểu hiện sau khi ứng dụng đã mở listener.

## 18. Tách timeout, quota và hiệu năng cho hai phía

Producer và consumer xử lý tải theo hai chiều nên các ngưỡng vận hành cũng khác.

### 18.1. Producer throughput

Những yếu tố ảnh hưởng:

- `linger.ms`, `batch.size` (bytes), compression.
- Số partition và key distribution.
- Broker quota và request latency.
- Kích thước payload, message size limit.
- Network và TLS overhead.
- Số future đang chờ và memory buffer.

Một producer đẩy 10.000 event/giây có thể cần chính sách batching khác producer phát 10 event/giây nhưng yêu cầu latency thấp.

### 18.2. Consumer throughput

Những yếu tố ảnh hưởng:

- Số partition so với số active consumer.
- `max.poll.records` và thời gian processing mỗi record.
- Concurrency của listener.
- Tốc độ database/API downstream.
- Retry/backoff và DLT.
- Rebalance, thời gian commit offset.
- Executor/thread và memory pressure.

Giả sử processing trung bình một record mất 200 ms và một consumer thực thi tuần tự, throughput lý thuyết khoảng 5 records/s (bỏ qua overhead). Tăng `max.poll.records` không tự làm mỗi record xử lý nhanh hơn. Cần xem parallelism có an toàn theo business key hay không, hoặc tối ưu I/O.

### 18.3. Ngưỡng riêng của từng role

| Mục tiêu | Producer | Consumer |
|---|---|---|
| Latency | End-to-end time từ publish request đến broker ACK | Thời gian từ record có sẵn đến business commit |
| Backlog | Outstanding sends / outbox pending | Consumer lag / queue processing |
| Retry | Send attempts, delivery timeout | Error handler retries, redelivery, DLT |
| Capacity | Records/s, bytes/s, buffer pressure | Records/s, poll interval, DB throughput |
| Error | Serialization, authorization, broker unavailable | Deserialization, poison record, DB failure, rebalance |
| Security | Write ACL, serializer/registry access | Read ACL, group authorization, deserializer/registry access |

Nếu chỉ thấy producer throughput cao nhưng consumer lag cũng tăng liên tục, hệ thống chưa chắc đã xử lý end-to-end tốt. Cần dashboard gắn hai vai trò với cùng business event ID/correlation ID.

## 19. Monitoring và logging tách theo role

Các metric Kafka client thường phân biệt producer/consumer theo client ID, nhưng tên metric cụ thể còn phụ thuộc client version và registry. Spring Boot Actuator + Micrometer có thể đưa Kafka client metrics vào hệ thống quan sát.

Các nhóm cần xem:

**Producer:**

- Send rate, record size, request latency.
- Record error/retry rate.
- Buffer available/exhaustion, waiting time.
- Delivery timeout và send future failures.
- Outbox pending age nếu ứng dụng có outbox.

**Consumer:**

- Consumer lag theo group/topic/partition.
- Poll rate, records consumed rate.
- Commit latency/failure.
- Partition assignment/rebalance.
- Listener processing duration và lỗi.
- Số record chuyển DLT, độ tuổi DLT pending.
- DB latency và business outcome.

Một log hữu ích:

```text
event=kafka.producer.send_failed
role=outbound
topic=payment-results.v1
eventId=evt-101
errorCategory=TIMEOUT

event=kafka.consumer.processing_failed
role=inbound
topic=payment-commands.v1
group=payment-commands-processor-v1
partition=2
offset=152001
errorCategory=DATABASE_TRANSIENT
```

Không đặt `eventId`, partition offset riêng của từng record hay payload làm **tag Prometheus cardinality cao**. Dùng chúng trong log/traces có cấu trúc với retention và phân quyền phù hợp. Tránh log raw message có thông tin cá nhân hoặc secret.

### 19.1. Health không thay thế business readiness

Một ứng dụng có thể báo process `UP` nhưng:

- Producer không có quyền ghi topic outbound.
- Consumer không join được group.
- Listener đang bị pause.
- Topic inbound chưa được tạo.
- DLT producer đang trỏ sai cluster.
- Consumer lag tăng không giới hạn.

Readiness policy nên phản ánh chức năng thực sự cần thiết. Tuy nhiên cũng không nên mặc định cho toàn service `DOWN` ngay khi broker mất kết nối vài giây nếu kiến trúc có queue/outbox và cần giữ API đọc độc lập. Chọn policy theo trách nhiệm ứng dụng và cách triển khai.

## 20. Kiểm thử cấu hình producer và consumer

Có ít nhất ba mức kiểm thử, mỗi mức trả lời một câu hỏi khác nhau.

### 20.1. Unit test property binding

Kiểm tra `KafkaRolesProperties` nhận đúng giá trị và từ chối cấu hình sai. Ví dụ test các input:

| Case | Expected |
|---|---|
| Có inbound A, outbound B, group hợp lệ | Bind thành công |
| Thiếu outbound bootstrap | Fail validation |
| Concurrency bằng 0 | Fail validation |
| Group ID rỗng | Fail validation |
| Cấu hình security chỉ có ở inbound, không có ở outbound | Fail startup hoặc validate theo policy |
| Tên topic chứa giá trị không được hỗ trợ | Fail validation |

Unit test này không chứng minh Kafka client kết nối thành công, nhưng giúp phát hiện lỗi profile trước khi deploy.

### 20.2. Integration test cùng cluster bằng EmbeddedKafka

Với nhu cầu kiểm tra serialization, listener wiring và ack/error handling, `spring-kafka-test` có các tiện ích như `@EmbeddedKafka` hoặc `EmbeddedKafkaBroker`.

Ví dụ ý tưởng:

```java
@SpringBootTest
@EmbeddedKafka(
        partitions = 2,
        topics = {
                "test-payment-commands",
                "test-payment-results"
        })
class PaymentKafkaIntegrationTest {

    @Test
    void sendsAndConsumesEvent() {
        // Gửi test event bằng KafkaTemplate cấu hình cho embedded broker.
        // Đợi bằng Awaitility/latch với timeout hữu hạn.
        // Assert listener nhận event đúng một lần trong happy path.
        // Kiểm tra topic và key được chọn theo contract.
    }
}
```

Đây là **khung test**, chưa bao gồm cấu hình dynamic bootstrap của embedded broker hoặc các bean test fixture. Test thực phải chỉ rõ các client dùng bootstrap mà embedded broker cung cấp, có consumer group độc lập và làm sạch dữ liệu giữa các test.

Embedded Kafka hữu ích để kiểm tra flow cơ bản. Nhưng một embedded broker không chứng minh **hai cluster độc lập**, TLS/SASL thật, ACL, broker replication, quota hoặc failover production.

### 20.3. Integration test hai cluster bằng Testcontainers

Để kiểm tra inbound A → outbound B, có thể chạy **hai Kafka broker/cluster test riêng** qua Testcontainers hoặc môi trường tích hợp tương tự.

```text
Test container Kafka A             Test container Kafka B
    payment-commands                   payment-results
            |                                 ^
            v                                 |
     inboundListenerFactory            outboundKafkaTemplate
            |                                 |
            +------------ app ----------------+
```

Test cần xác minh:

1. Listener kết nối cluster A, join đúng group và nhận message từ A.
2. Business service xử lý xong thì producer gửi record sang cluster B.
3. Message xuất hiện trên B, **không** vô tình xuất hiện trên A.
4. Failure khi publish sang B được ghi nhận/retry qua outbox hoặc chính sách đã chọn.
5. Error handler gửi DLT về cluster A nếu đây là yêu cầu thiết kế.
6. Trường hợp thiếu credential ACL không dẫn tới sử dụng nhầm producer factory của cluster kia.
7. Consumer redelivery sau crash không làm DB ghi trùng.
8. Topic prefix và security settings đúng theo profile test.

Các bước này cần môi trường test có đủ tài nguyên; không nên coi test bằng hai topic trong **một cluster** là bằng chứng multi-cluster configuration hoạt động đúng.

### 20.4. Kiểm tra wiring bean tường minh

Có thể assert bean được chọn đúng bằng tên/qualifier:

```java
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

class KafkaWiringTest {

    @Autowired
    @Qualifier("outboundKafkaTemplate")
    KafkaTemplate<String, String> outbound;

    @Autowired
    @Qualifier("outboundProducerFactory")
    ProducerFactory<String, String> outboundFactory;

    @Test
    void templateUsesExpectedProducerFactory() {
        assertSame(outboundFactory, outbound.getProducerFactory());
    }
}
```

Đây là phần assertion minh họa và cần đặt trong Spring test context chứa các bean tương ứng. Nó kiểm tra wiring trong JVM, không tự chứng minh broker đích đúng. Các test khác cần xem effective `bootstrap.servers` và xác nhận bằng message thực.

### 20.5. Failure-injection test cho semantics

| Kịch bản | Điều cần chứng minh |
|---|---|
| Kafka broker A không sẵn sàng | Consumer báo lỗi/không xử lý sai, hồi phục khi broker trở lại |
| Kafka broker B không sẵn sàng | Producer future thất bại trong giới hạn thời gian; outbound event không bị mất nếu contract yêu cầu delivery bền vững |
| DLT producer sai cluster | Test phát hiện topic/ACL không khớp |
| Listener ném transient exception | Retry có giới hạn, không ack trước xử lý |
| Listener ném poison payload | Recovery/DLT theo policy, không retry vô hạn |
| DB commit xong, offset chưa commit | Message được xử lý idempotent khi redelivery |
| Producer gửi ACK không rõ do timeout | App-level resend không tạo business effect trùng |
| Schema thay đổi | Consumer xử lý tương thích hoặc chuyển lỗi tới quarantine |
| Rebalance giữa xử lý | Không ghi trùng/thiếu nghiệp vụ |
| Restart app | Consumer dùng lại committed offsets, không tự reset vì `earliest` |

## 21. Vận hành, rollout và thay đổi cấu hình an toàn

Tách cấu hình giúp deploy an toàn hơn, nhưng chỉ khi thay đổi được quản lý theo vai trò.

### 21.1. Trước khi triển khai

Ghi một bảng cấu hình hiệu lực:

| Trường | Inbound consumer | Outbound producer |
|---|---|---|
| Cluster | Kafka A | Kafka B |
| Bootstrap | Secret/config reference A | Secret/config reference B |
| Principal | reader principal | writer principal |
| Topic | `payment-commands.v1` | `payment-results.v1` |
| Group | `payment-commands-processor-v1` | Không áp dụng |
| Serializer/Deserializer | StringDeserializer | StringSerializer |
| Retry policy | Listener + DLT | Kafka producer + outbox |
| Delivery/commit | Record commit sau xử lý | ACK qua future |
| SLA | Consumer lag và processing latency | Publish ACK latency |
| Rollback plan | Pause/restart consumer có kiểm soát | Outbox replay/downgrade cấu hình |

Để xác nhận, cần kiểm tra effective properties, trạng thái bean và quyền cluster. Không in secret khi ghi nhận config.

### 21.2. Thay `group.id` là thay semantic replay

Thay `payment-commands-processor-v1` thành `payment-commands-processor-v2` thường tạo **consumer group mới**, không có committed offsets cũ. Với `auto.offset.reset=earliest`, group mới có thể đọc lại các record còn trong retention; nếu `latest`, nó có thể bỏ qua dữ liệu tồn tại trước khi group được tạo.

Đây là thay đổi **nghiệp vụ**, không phải chỉ đổi tên để dễ quản lý. Cần kế hoạch replay và idempotency.

### 21.3. Thay serializer cần migration contract

Nếu producer đổi từ JSON String sang Avro binary nhưng consumer vẫn dùng `StringDeserializer`, message có thể lỗi giải mã hoặc tạo nội dung không hợp lệ. Một rollout an toàn cần schema version, tương thích hai chiều hoặc topic version mới, cùng kiểm thử giữa phiên bản producer/consumer cũ và mới.

### 21.4. Thay concurrency

Tăng `concurrency` có thể tăng số consumer trong group, tạo rebalance, tăng DB load hoặc làm lộ race condition nếu listener không thread-safe. Nên benchmark, giám sát lag và DB pool, xác định key ordering; không thay chỉ dựa trên CPU của ứng dụng.

### 21.5. Tắt/bật consumer mà vẫn duy trì producer

Có hệ thống cần tạm pause inbound processing khi downstream lỗi nhưng vẫn cho producer gửi một số event. Vì hai role độc lập, có thể sử dụng listener registry/container controls hoặc cấu hình `autoStartup` với runbook rõ, thay vì tắt cả Kafka subsystem.

Cần phân biệt **pause** với **stop** và ảnh hưởng đến consumer group, offset, rebalances, readiness. Nếu ứng dụng tạm ngừng xử lý, backlog tiếp tục tăng; phải có capacity để catch up sau khi resume.

## 22. Các anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách xử lý |
|---|---|---|
| Nhét mọi property dưới một map chung | Dễ đặt nhầm parameter | Chia `producer`/`consumer`/`listener` |
| Nghĩ `acks=all` làm consumer xử lý đúng một lần | Duplicate vẫn có thể xảy ra | Idempotent consumer + transaction boundaries |
| Nghĩ `auto.offset.reset=earliest` là lệnh replay group hiện có | Không thay committed offsets | Kế hoạch reset/replay riêng |
| Bật `enable-auto-commit=true` nhưng trông chờ container ack theo business commit | Offset có thể không khớp thời điểm xử lý | Chọn ack mode/commit policy rõ |
| Catch exception trong listener rồi return | Container có thể commit offset dù business fail | Propagate lỗi hoặc recovery có chủ đích |
| Producer bỏ qua `CompletableFuture` | Không biết send thất bại | Theo dõi future/outbox |
| Dùng chung `KafkaTemplate` cho output B và DLT A | DLT đi sai cluster | Template/factory theo destination |
| Gắn `@KafkaListener` nhưng không chỉ `containerFactory` khi có nhiều factory | Có thể dùng factory mặc định ngoài ý muốn | Chỉ rõ listener factory |
| Có hai factories cùng type nhưng không `@Qualifier` | Wiring mơ hồ | Bean name, qualifier, test |
| Cùng credentials producer/consumer dù cần least privilege | Quyền rộng, khó rotate | Principal/ACL theo vai trò |
| Ghi JAAS password trong YAML commit Git | Lộ secret | Secret manager/env injection an toàn |
| `concurrency=8` với topic 3 partition và mong throughput tăng 8 lần | Consumer rảnh, DB load không như dự kiến | Tune theo partition/processing |
| Dùng chung client ID cho mọi role không kiểm soát | Metrics/diagnostics khó đọc | Client ID có role và instance |
| Cho `JsonDeserializer` tin mọi package | Mở rộng attack surface | Schema/type allowlist |
| Coi `read_committed` là DB/Kafka cross-cluster transaction | Sai bảo đảm consistency | Inbox/outbox và reconciliation |
| Test multi-cluster bằng hai topic một broker | Không phát hiện wiring sai cluster | Hai broker/cluster test độc lập |
| Đổi `group.id` trong deploy mà không có kế hoạch | Replay hoặc skip không mong muốn | Review offset/consumer group semantics |
| Tạo topic tự động trên cluster không kiểm soát | Sai môi trường/ACL | IaC hoặc KafkaAdmin tách biệt |
| Dùng default localhost trong production | Kết nối sai endpoint khi thiếu env | Fail fast khi config thiếu |
| Gắn payload/event ID vào mọi metrics label | Cardinality cao, có thể lộ dữ liệu | Stable labels + structured logs |

## 23. Bài tập thực hành: ứng dụng consumer A, producer B

Xây dựng dịch vụ `invoice-relay-service`. Nó đọc sự kiện `invoice-approved.v1` từ cluster A, ghi audit/inbox trong PostgreSQL, rồi publish `invoice-settlement-requested.v1` sang cluster B.

**Yêu cầu chức năng:**

1. Định nghĩa `app.kafka.inbound.*` và `app.kafka.outbound.*` với bootstrap, topic và các cấu hình khác nhau.
2. Tạo `inboundConsumerFactory` dùng `StringDeserializer`, `group.id=invoice-relay-v1`, tắt auto-commit và đặt `auto.offset.reset=earliest` cho group mới.
3. Tạo `inboundListenerFactory` với `AckMode.RECORD`, `concurrency=2` và error handler có bounded retry.
4. Tạo `outboundProducerFactory` dùng `StringSerializer`, `acks=all`, idempotence và delivery timeout hữu hạn.
5. Tạo `outboundKafkaTemplate`, inject bằng `@Qualifier` vào publisher; chứng minh listener dùng factory inbound.
6. Thiết kế và triển khai inbox/outbox để bảo đảm DB không xử lý cùng `eventId` hai lần và sự kiện outbound có thể được gửi lại sau crash.
7. Tạo thêm `inboundDlqKafkaTemplate` trỏ cluster A nếu DLT cần nằm cùng cluster với dữ liệu nguồn.
8. Phân tách credentials: principal đọc chỉ được read topic A/group, principal ghi chỉ được write topic B.
9. Viết validation cho các property ứng dụng: bootstrap/topic/group không được rỗng, concurrency > 0.
10. Viết integration test hai cluster riêng: gửi vào A, nhận ở B, không rò message sai cluster.
11. Mô phỏng lỗi producer B trong khi consumer A vẫn nhận: giải thích cách outbox giúp không mất sự kiện.
12. Mô phỏng DB đã commit nhưng offset A chưa commit: chứng minh replay không tạo bản ghi audit trùng.
13. Mô phỏng poison payload: message phải đi vào DLT/quarantine theo policy, không retry vô hạn.
14. Đổi consumer group ID sang `invoice-relay-v2` trên môi trường test và kiểm chứng hành vi offset.
15. Tăng concurrency từ 2 lên 6 khi topic có 3 partition; đo thực tế số consumer active và throughput.
16. Thiết kế dashboard riêng cho producer ACK latency/outbox pending và consumer lag/rebalance/DLT.

**Câu hỏi ôn tập:** Nếu consumer đọc Kafka A, producer ghi Kafka B và đã bật `enable.idempotence=true` với `acks=all`, có thể nói cả quá trình xử lý là exactly once không?

**Trả lời:** **Không.** Hai thuộc tính trên cải thiện độ tin cậy của producer trong phạm vi Kafka client/broker; chúng không tạo transaction nguyên tử bao phủ offset tiêu thụ trên A, thay đổi PostgreSQL và bản ghi được gửi sang B. Cần ranh giới transaction rõ ràng, inbox/outbox, idempotency và đối soát để đạt kết quả nghiệp vụ đáng tin cậy khi xảy ra retry/crash.

## 24. Tài liệu tham khảo

- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): cấu hình `spring.kafka`, producer/consumer/listener, KafkaTemplate và KafkaListener.
- [Spring Kafka Reference — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate` và send futures.
- [Spring Kafka Reference — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html): container, `@KafkaListener`, ack mode và concurrency.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retry và DLT.
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transactional processing và giới hạn.
- [Spring Kafka Reference — SerDes](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html): `JsonSerializer`, `JsonDeserializer` và error handling deserializer.
- [Spring Kafka Reference — Testing](https://docs.spring.io/spring-kafka/reference/testing.html): `spring-kafka-test`, Embedded Kafka và integration tests.
- [Apache Kafka Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): `acks`, idempotence, retries, linger, batch size và timeout.
- [Apache Kafka Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `group.id`, offset reset, poll, fetch và isolation.
- [Apache Kafka Security](https://kafka.apache.org/documentation/#security): TLS, SASL, ACL và client authentication.
