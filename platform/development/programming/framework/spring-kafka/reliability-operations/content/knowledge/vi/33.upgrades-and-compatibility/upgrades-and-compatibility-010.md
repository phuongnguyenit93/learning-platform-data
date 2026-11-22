# Smoke test sau upgrade trong Spring Kafka

## 1. Smoke test sau upgrade là gì?

Khi nâng cấp **Spring Kafka**, **Spring Boot**, **Kafka Java client**, Java runtime hoặc Kafka broker, ứng dụng có thể vẫn khởi động nhưng một phần luồng xử lý không còn đúng: producer ghi sai định dạng, listener không join consumer group, deserializer không đọc được event cũ, error handler thay đổi retry, DLT không nhận record lỗi hoặc offset không được commit như kỳ vọng.

**Smoke test sau upgrade** là một tập kiểm tra **ngắn, có thể lặp lại, có điều kiện PASS/FAIL rõ ràng**, nhằm xác định phiên bản vừa triển khai có còn thực hiện được những khả năng quan trọng nhất hay không.

Ví dụ hệ thống nhận sự kiện đơn hàng:

~~~text
Trước upgrade
    Spring Boot / Spring Kafka / Kafka clients (bản cũ)
                               |
                               v
                      Nâng cấp và deploy
                               |
                               v
                         Bản mới
                               |
                   +-----------+----------+
                   |           |          |
              Producer      Consumer   Error handler
                   |           |          |
                   v           v          v
               Kafka ack   DB side effect  Retry/DLT
                   |           |          |
                   +-----------+----------+
                               |
                     Metrics và offset
                               |
                       PASS / FAIL / UNKNOWN
                               |
                 Continue rollout / Halt
~~~

Smoke test trả lời câu hỏi: **“Bản build mới trên môi trường triển khai có hoạt động tối thiểu theo contract của ứng dụng không?”**

Nó **không chứng minh** rằng throughput đã đạt SLA dài hạn, mọi trường hợp crash/recovery đều an toàn hay pipeline đã có exactly-once semantics end-to-end. Những việc đó cần integration, recovery, load/soak hoặc chaos testing riêng.

Bài này thuộc **Spring Kafka Reliability Operations → Nâng cấp và tương thích**, sử dụng ví dụ với **Java 17, Spring Boot 3.x, Spring Kafka 3.x, Spring JDBC và PostgreSQL**. Khi nâng cấp sang phiên bản khác, phải đối chiếu compatibility matrix, migration notes và API thực tế của tổ hợp phiên bản đã chọn; không suy đoán tính tương thích từ ví dụ minh họa.

## 2. Phân biệt smoke test với các lớp kiểm thử khác

| Loại kiểm thử | Câu hỏi | Thời điểm |
| --- | --- | --- |
| **Unit test** | Logic parse, mapping, validation và business rule đúng? | CI mỗi lần thay đổi code |
| **Integration test** | Kafka, Spring listener, serializer, database và handler phối hợp được? | CI/staging |
| **Contract test** | Producer và consumer đọc được schema trước/sau upgrade? | Trước rollout khi đổi schema hoặc library |
| **Smoke test sau upgrade** | Bản đang deploy có thể gửi, nhận, xử lý và báo lỗi đúng? | Ngay sau deploy/canary |
| **Recovery test** | Crash sau DB commit trước offset commit có an toàn? | CI/staging chuyên biệt |
| **Load/soak test** | Hệ thống xử lý tải thật lâu dài, không tăng lag/GC bất thường? | Trước rollout lớn hoặc theo lịch |
| **Chaos/failover test** | Broker outage, network partition, node restart có được phục hồi? | Môi trường được kiểm soát |

Một bài smoke quá hẹp, chỉ gọi HTTP health endpoint, dễ cho kết quả PASS giả. Một bài smoke quá rộng, chạy hàng chục nghìn record hoặc kill broker, lại tạo rủi ro và làm chậm quyết định rollout.

Mục tiêu là chọn **ít bài nhất nhưng bao phủ các đường kỹ thuật có thể gãy sau nâng cấp**.

## 3. Liệt kê những phần có thể thay đổi do upgrade

Một ứng dụng Spring Kafka phụ thuộc nhiều tầng:

~~~text
Business listener / processor
           |
     Spring Kafka
           |
    Spring Framework
           |
    Kafka Java client
           |
  TLS / SASL / network
           |
      Kafka broker
           |
 Schema registry nếu có
~~~

Cần chuẩn bị **inventory phiên bản**:

| Thành phần | Điều cần ghi nhận |
| --- | --- |
| Spring Boot | Version trước/sau, BOM đang quản lý dependency |
| Spring Kafka | Version trước/sau, API listener/error handler/retry |
| Kafka clients | Version thực tế có trong artifact, không chỉ version khai báo |
| Java runtime | JVM vendor/version, TLS và truststore |
| Kafka broker | Version, phương án rolling upgrade nếu có |
| Schema registry | Avro/Protobuf/JSON schema, subject và auth |
| Database | JDBC driver, transaction manager, connection pool |
| Observability | Actuator, Micrometer, logging/tracing |
| Deployment | Image digest, ConfigMap, Secret, ACL, topic/group |

Các thay đổi cần chú ý:

- Default configuration của consumer/producer.
- Hành vi listener acknowledgement và offset commit.
- Deserializer, trusted packages, type headers và schema compatibility.
- DefaultErrorHandler, retry classifier và dead-letter publishing.
- **@RetryableTopic** và tên các retry topics/DLT.
- Kafka transactions, producer fencing và transactional.id.
- Listener concurrency, rebalance và assignment.
- Metrics/health indicators hoặc tên tags bị thay đổi.
- Compatibility giữa client mới với Kafka broker trong môi trường đích.

Không tự ép phiên bản **kafka-clients** khác với tập dependency do Spring Boot quản lý nếu chưa đánh giá tương thích. Ghi **build artifact/version chính xác**, không ghi “mới nhất” như một thông tin kiểm chứng.

## 4. Chọn smoke cases theo đường đi thực tế

Giả sử ứng dụng dùng **orders.events** làm topic chính, **orders.events.DLT** để giữ record lỗi và PostgreSQL để ghi kết quả.

| ID | Smoke case | Điều cần chứng minh |
| --- | --- | --- |
| S1 | Startup/connection | Bean, TLS/SASL, broker metadata và ACL hoạt động |
| S2 | Producer send | KafkaTemplate gửi record và nhận broker ack |
| S3 | Consumer/DB | Listener bản mới nhận record và commit business side effect |
| S4 | Offset progress | Consumer group tiến qua record theo ack/commit policy |
| S5 | Duplicate | Cùng eventId nhận hai lần nhưng chỉ một business effect |
| S6 | Error handler/DLT | Record lỗi được retry/recover và DLT nhận đúng |
| S7 | Serialization compatibility | Event cũ/mới được đọc theo contract |
| S8 | Kafka transactions | Nếu pipeline dùng transactions, commit/abort đúng |
| S9 | Observability | Metrics, logs, traces, alerts còn đủ tín hiệu |
| S10 | Canary health | Không tăng bất thường lag, rebalance, error, pod restart |

Không phải ứng dụng nào cũng cần S8. Nhưng nếu dùng **consume-transform-produce với Kafka transactions**, bỏ qua smoke transaction sau nâng cấp là bỏ qua một đường thiết yếu.

Nên có ít nhất **một event đi qua chính đường xử lý business** và một **nhánh lỗi** khi ứng dụng có retry/DLT. Một listener giả chỉ ghi log có thể bỏ sót regression trong transaction hoặc serializer production.

## 5. Quy tắc PASS, FAIL và UNKNOWN

Smoke gate cần được thống nhất trước rollout.

**PASS**: đủ bằng chứng rằng điều kiện bắt buộc đã đạt trong thời hạn hợp lý.

**FAIL**: có bằng chứng chức năng sai, ví dụ producer lỗi serializer, listener không xử lý, DB ghi sai, duplicate side effect hoặc DLT không publish được.

**UNKNOWN / INCONCLUSIVE**: không thu thập đủ bằng chứng, chẳng hạn không có quyền đọc consumer group hoặc công cụ quan sát bị mất kết nối.

Ví dụ contract của case S3:

~~~text
Input:
  topic = smoke.orders.events
  eventId = smoke-{unique-id}
  payload = valid OrderCreated

Expected:
  producer ack success
  consumer thuộc build nâng cấp thực sự nhận event
  DB có đúng một kết quả cho eventId
  không có DLT record tương ứng
  consumer progress phù hợp ack policy

Timeout:
  30 giây trong môi trường staging minh họa

Outcome:
  PASS / FAIL / UNKNOWN
~~~

**UNKNOWN không được tự động biến thành PASS**. Khi không đủ bằng chứng, gate nên giữ rollout ở mức hiện tại để điều tra.

Ngưỡng 30 giây chỉ là ví dụ; chọn timeout theo baseline, tài nguyên và yêu cầu của hạ tầng, không theo một giá trị tuyệt đối áp dụng cho mọi cụm.

## 6. Cô lập smoke khỏi dữ liệu nghiệp vụ production

Một smoke test đáng tin phải có thể chạy nhiều lần mà không tạo tác dụng phụ không mong muốn.

Nguyên tắc:

1. Dùng **topic smoke riêng** hoặc một namespace/canary đã cho phép test events.
2. Dùng **eventId** riêng cho mỗi lần test, không lấy ID giao dịch khách hàng.
3. Dùng database/tenant/account giả lập riêng để kiểm tra side effect.
4. Không gửi poison record vào production business topic nếu chưa có quy trình cho phép.
5. Không reset production consumer group offsets để kiểm thử.
6. Không xóa DLT hoặc deduplication table dùng chung trong quá trình cleanup fixture.
7. Chỉ cấp ACL cần thiết cho smoke runner.
8. Dùng trace/correlation ID để phân biệt test traffic và traffic thật.
9. Giữ evidence thất bại trước khi dọn fixture.
10. Không chạy smoke với hàng nghìn records để thay cho load test.

Topology ví dụ:

~~~text
Staging / canary namespace
       |
       +--> smoke.orders.events
       |          |
       |          v
       |       Listener cấu hình giống business listener
       |          |
       |          v
       |       smoke_processed_event (DB riêng)
       |
       +--> smoke.orders.events.DLT
                   |
                   v
                DLT observer
~~~

**Lưu ý về độ bao phủ:** listener smoke chỉ ghi marker là một probe an toàn, nhưng chưa chứng minh toàn bộ business pipeline. Nó nên tái sử dụng Spring Kafka listener container/error handler/serializer/transaction configuration và được kết hợp với integration test của nghiệp vụ thật. Nếu production logic hoàn toàn khác, cần có thêm canary event hoặc contract test phù hợp, nhưng vẫn phải bảo đảm không tác động dữ liệu thật ngoài ý muốn.

## 7. Baseline trước upgrade

Trước khi deploy, ghi lại:

| Nhóm | Baseline |
| --- | --- |
| Consumer | Lag, assigned partitions, rebalance rate |
| Producer | Error rate, acks, request latency, retry rate |
| Listener | Throughput, processing time, exception rate |
| Retry/DLT | Retry attempts, DLT ingress, publish failures |
| Database | Commit/rollback, connection pool saturation |
| JVM | CPU, memory, GC, thread count |
| Pods | Readiness, restarts, resource throttling |
| Business | Applied events, duplicates, reconciliation mismatches |

Một mẫu biên bản:

~~~text
service: order-consumer
environment: staging
release-candidate: <build-digest>
old-spring-boot: <actual-version>
new-spring-boot: <actual-version>
old-spring-kafka: <actual-version>
new-spring-kafka: <actual-version>
kafka-clients: <actual-version>
broker: <actual-version>
java: <actual-runtime>

baseline-window: 30 minutes before deploy
consumer-lag: <measured-range>
retry-rate: <measured-range>
DLT-ingress: <measured-range>
p95-processing-time: <measured-value>
~~~

Cần so sánh trong các cửa sổ traffic tương tự. Một lần smoke gửi vài message không đủ cơ sở kết luận performance không đổi, nhưng baseline giúp nhận biết dấu hiệu rõ khi rollout canary.

## 8. Startup smoke: kiểm tra nhiều hơn HTTP health

Ứng dụng có thể trả **HTTP 200** trong khi consumer chưa join group hoặc broker credentials không hợp lệ.

Cần xác nhận:

- Container đang chạy đúng image digest/release.
- Spring context và Kafka listener beans khởi tạo thành công.
- TLS/SASL authentication và Kafka ACLs hợp lệ.
- AdminClient đọc được topic metadata.
- Topic tồn tại với partition count dự kiến.
- Listener container thực sự **running**.
- Consumer group có member và assigned partitions phù hợp.
- Không có lỗi authorization/serializer/deserializer.
- Không rebalance liên tục hoặc crash loop.
- Readiness phản ánh dependency thực sự thiết yếu theo thiết kế.

Các exception hay xuất hiện:

~~~text
SaslAuthenticationException
TopicAuthorizationException
GroupAuthorizationException
UnknownTopicOrPartitionException
SerializationException
InvalidTopicException
NoClassDefFoundError
NoSuchMethodError
CertificateException
~~~

Nếu lỗi **NoSuchMethodError/NoClassDefFoundError**, hãy kiểm tra dependency compatibility/classpath. Nếu lỗi TLS hoặc ACL, kiểm tra truststore, secret và quyền của service account trên topic/group.

**AdminClient.describeCluster thành công không chứng minh listener xử lý record.** Đó mới là phần xác nhận kết nối.

## 9. Producer smoke: send, wait ack, ghi metadata

Spring Kafka 3.x cung cấp **KafkaTemplate.send** trả về **CompletableFuture<SendResult<K,V>>**. Smoke cần chờ broker acknowledgement thay vì chỉ gọi send rồi kết luận thành công.

~~~java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class SmokeProducer {

    private final KafkaTemplate<String, String> kafka;

    public SmokeProducer(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    public RecordMetadata send(
            String topic,
            String eventId,
            String payload) throws Exception {

        return kafka.send(topic, eventId, payload)
                .get(10, TimeUnit.SECONDS)
                .getRecordMetadata();
    }
}
~~~

Sau send, ghi bằng chứng:

~~~text
eventId: smoke-...
topic: smoke.orders.events
partition: 1
offset: 208
producer-ack: success
~~~

**Producer ack chỉ chứng minh Kafka đã ghi/ack record theo producer settings.** Nó chưa chứng minh listener thực sự nhận hoặc database đã commit.

Nếu production dùng Avro/Protobuf/JSON serializer và schema registry, hãy gửi một message qua **cùng serializer/converter/schema contract**, không chỉ dùng String serializer cho dễ test. Nhánh serialization là một trong những rủi ro nâng cấp lớn.

## 10. Consumer smoke phải quan sát được side effect

Một test KafkaConsumer độc lập tự đọc topic chỉ chứng minh **consumer của bài test** hoạt động. Để biết bản deploy mới có xử lý hay không, cần kiểm tra đầu ra của listener production/canary:

- Business row/marker được commit trong DB.
- Event output được tạo bởi đường consume-transform-produce.
- Một acknowledgement ứng dụng có correlation ID.
- Một audit record bền vững có build/version của consumer.
- Hoặc một probe được instrument đúng vào listener mà không đổi nghiệp vụ.

Ví dụ thiết lập bảng test:

~~~sql
CREATE TABLE smoke_processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    event_type VARCHAR(40) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Event:

~~~java
public record SmokeOrderEvent(
        String eventId,
        String orderId,
        String action) {
}
~~~

Service:

~~~java
@Service
public class SmokeOrderService {

    private final JdbcTemplate jdbc;

    public SmokeOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(SmokeOrderEvent event) {
        jdbc.update("""
            INSERT INTO smoke_processed_event(
                event_id, event_type
            ) VALUES (?, ?)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(),
            event.action());
    }
}
~~~

Đây là SQL PostgreSQL. **ON CONFLICT** giúp marker theo eventId không bị chèn hai lần khi nhận duplicate. Để chứng minh idempotency của một nghiệp vụ cộng tiền hoặc tạo đơn, cần assert thêm **side effect thực** trong fixture, không chỉ marker này.

## 11. Listener thử nghiệm có cùng cơ chế lỗi

Ví dụ listener đọc String JSON:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class SmokeOrderListener {

    private final ObjectMapper mapper;
    private final SmokeOrderService service;

    public SmokeOrderListener(
            ObjectMapper mapper, SmokeOrderService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
            topics = "smoke.orders.events",
            groupId = "smoke-order-processor-v1")
    public void consume(ConsumerRecord<String, String> record) {
        SmokeOrderEvent event;

        try {
            event = mapper.readValue(
                    record.value(), SmokeOrderEvent.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidSmokePayloadException(
                    "Invalid smoke event JSON", ex);
        }

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()) {
            throw new InvalidSmokePayloadException(
                    "Missing mandatory smoke event fields");
        }

        service.apply(event);
    }
}
~~~

Exception:

~~~java
public class InvalidSmokePayloadException
        extends RuntimeException {

    public InvalidSmokePayloadException(
            String message, Throwable cause) {
        super(message, cause);
    }

    public InvalidSmokePayloadException(String message) {
        super(message);
    }
}
~~~

Cấu hình ví dụ phải có **ObjectMapper, Spring JDBC, KafkaTemplate, topic** và transaction manager. Khi đưa vào staging, dùng cùng **ConsumerFactory, ListenerContainerFactory, CommonErrorHandler và serializer** với những thành phần tương ứng của production.

Không bật listener probe như một consumer chung trên production business group nếu chưa có kế hoạch; nó có thể tranh partition với consumer thật.

## 12. Integration smoke test bằng Spring Boot Test

Sau khi có listener smoke, một bài test có thể gửi event rồi chờ DB phản ánh kết quả:

~~~java
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(properties = {
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.listener.ack-mode=record"
})
class KafkaSmokeAfterUpgradeTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void producerAndListenerProcessSmokeEvent() throws Exception {
        String eventId = "smoke-" + UUID.randomUUID();

        String payload = """
            {"eventId":"%s","orderId":"SMOKE-001","action":"PROBE"}
            """.formatted(eventId);

        kafkaTemplate.send(
                "smoke.orders.events",
                eventId,
                payload).get(10, TimeUnit.SECONDS);

        await().atMost(Duration.ofSeconds(30))
                .untilAsserted(() -> {
                    Integer count = jdbc.queryForObject("""
                            SELECT COUNT(*)
                            FROM smoke_processed_event
                            WHERE event_id = ?
                            """,
                            Integer.class, eventId);

                    assertThat(count).isEqualTo(1);
                });
    }
}
~~~

Các điều kiện:

- Broker/topic test, listener và DataSource đã sẵn sàng.
- Bảng **smoke_processed_event** tồn tại và có quyền ghi.
- Có Spring Boot Test, JUnit 5, AssertJ, Awaitility và Kafka dependencies.
- Test dùng **eventId riêng**; không TRUNCATE table dùng chung khi test khác có thể đang chạy.
- Nếu consumer group chưa có committed offset và dùng **auto-offset-reset=latest**, đợi listener được assign partition **trước khi gửi** để tránh bỏ qua message đầu.
- Test case dùng launcher Spring context phù hợp với hạ tầng staging; không để test kết nối nhầm database production.

### Phân biệt test trong CI với post-deploy smoke

**@SpringBootTest** thường khởi động một application context mới trong test process. Nó chứng minh cấu hình/code của test process chạy được, nhưng **chưa chắc chứng minh một pod đã deploy mới đang tiêu thụ**.

Với post-deploy smoke thực, một runner bên ngoài nên:

1. Xác nhận service mới đã deploy và listener được assign.
2. Gửi event qua topic smoke.
3. Truy vấn DB/audit/output do **chính service đang chạy** tạo.
4. Xác định build/version của instance xử lý record.
5. Không khởi tạo một listener test trùng group khiến record bị process test nhận thay vì canary.

## 13. Đợi điều kiện thật, không dùng sleep tùy tiện

Kafka và Spring listener hoạt động bất đồng bộ. Ví dụ:

~~~java
kafkaTemplate.send(topic, key, payload);
Thread.sleep(1_000L);
assertThat(resultCount).isEqualTo(1);
~~~

Test này có thể fail ngẫu nhiên khi CI chậm, hoặc pass trước khi các bước sau được thực hiện.

Dùng **Awaitility**, CountDownLatch/test probe có identity rõ ràng, hoặc polling consumer group offsets có timeout. Điều kiện phải liên quan tới record của test, không chỉ “consumer lag bằng 0” trên một topic đang có dữ liệu khác.

Một ví dụ **timeout không thể quan sát** phải là UNKNOWN hoặc FAIL theo contract; không mặc định PASS vì không thấy lỗi.

## 14. Offset smoke: liệu consumer group đã tiến qua record?

Với record listener và chính sách commit offset, cần xác nhận **sau xử lý**, group đã tiến qua record kiểm thử.

Producer trả **RecordMetadata** chứa topic, partition và offset. Với Kafka committed offsets, offset đã commit thường là **vị trí kế tiếp cần tiêu thụ**, nên cần lớn hơn offset của record đã xử lý.

Ví dụ dùng AdminClient:

~~~java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.TopicPartition;

public boolean hasCommittedPast(
        String bootstrap,
        String groupId,
        TopicPartition partition,
        long recordOffset) throws Exception {

    try (AdminClient admin = AdminClient.create(
            Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrap))) {

        var committed = admin
                .listConsumerGroupOffsets(groupId)
                .partitionsToOffsetAndMetadata()
                .get(10, TimeUnit.SECONDS)
                .get(partition);

        return committed != null
                && committed.offset() > recordOffset;
    }
}
~~~

Đây là method minh họa, đặt trong class phù hợp. Cần quyền đọc consumer group và thời gian chờ commit hợp lý. **Không đoán partition=0** khi producer gửi message có key; hãy dùng topic/partition/offset từ RecordMetadata.

Cảnh báo:

- **Offset tiến không chứng minh business side effect đúng.** Error handler có thể recover/skip record rồi tiến offset.
- Với manual ack, async processing hoặc Kafka transaction, semantics và thời điểm commit có thể khác.
- Trên topic có traffic khác, offset tiến không đảm bảo chính eventId thử nghiệm đã được xử lý.
- Phải kết hợp **business marker/eventId và offset progress** để chứng minh hai khía cạnh riêng.
- Không reset production group offset trong smoke test.

## 15. Duplicate smoke sau nâng cấp

Nâng cấp có thể tác động commit timing, container concurrency hoặc retry behavior, làm lộ lỗi idempotency.

Một smoke case đơn giản:

~~~text
Kafka offset 200: eventId=smoke-a
Kafka offset 201: eventId=smoke-a

Kỳ vọng:
  listener nhận/hoàn tất cả hai attempts
  marker nghiệp vụ có một record
  side effect chỉ áp dụng một lần
~~~

Cần **đợi record thứ hai thực sự được xử lý** rồi mới assert dữ liệu cuối. Nếu chỉ thấy marker count=1 ngay sau offset 200, test có thể pass giả trong khi offset 201 chưa được consumer xử lý.

Các cách xác nhận:

- Consumer group committed offset vượt offset thứ hai.
- Test probe tại điểm hoàn tất listener.
- Business acknowledgement được phát khi mỗi attempt kết thúc.

Lưu ý **marker count=1** một mình không chứng minh nghiệp vụ idempotent nếu code vừa bỏ trùng marker vừa cộng side effect hai lần. Test nên assert cả **business result**, ví dụ số dư giả lập tăng đúng một lần.

Producer idempotence và Kafka transactions có thể giảm duplicate trong phạm vi Kafka, nhưng không tự bảo vệ mọi side effect tại JDBC/HTTP/email. Một bài smoke duplicate là cổng nhanh; crash gap **DB commit trước offset commit** cần integration/failure test sâu hơn.

## 16. Smoke retry và Dead Letter Topic

Nếu ứng dụng có **DefaultErrorHandler** và **DeadLetterPublishingRecoverer**, hãy kiểm tra sau upgrade:

- Error handler vẫn được gắn với listener container.
- Exception classifier vẫn phân biệt retryable/non-retryable.
- Backoff và số lần thử đúng contract.
- DLT topic, partition mapping và ACL tồn tại.
- DLT producer serializer hỗ trợ payload lỗi thực tế.
- Record DLT có key/value và source metadata đủ để điều tra.
- Khi DLT send thất bại, record gốc không bị coi đã recovery thành công một cách sai lệch.
- Offset commit sau recover được hiểu theo ack mode.

Cấu hình ví dụ:

~~~java
@Configuration
public class SmokeKafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler smokeErrorHandler(
            KafkaTemplate<String, String> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()));

        recoverer.setFailIfSendResultIsError(true);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(200L, 1L));

        handler.addNotRetryableExceptions(
                InvalidSmokePayloadException.class);

        return handler;
    }
}
~~~

Cần import các class Spring Kafka, **org.apache.kafka.common.TopicPartition**, **FixedBackOff** và cấu hình Spring Configuration. Bean cần được listener container factory sử dụng đúng cách; khi trong app có nhiều container factories, không dựa vào giả định mọi listener tự nhận handler này.

Với **FixedBackOff(200L, 1L)**, lỗi retryable được thử **một lần ban đầu và một lần retry**. Lỗi InvalidSmokePayloadException được phân loại non-retryable.

### Test poison JSON an toàn

Gửi vào **smoke.orders.events**:

~~~text
Payload lỗi:
  {"eventId":

Kỳ vọng:
  smoke.orders.events.DLT nhận record
  DB không có business side effect
  DLT record có original topic/partition/offset
  error category đúng
~~~

Không tự đưa poison JSON vào business topic production chỉ để smoke. DLT nên có partition tương thích với source nếu recoverer giữ nguyên partition index.

Nếu ứng dụng dùng **@RetryableTopic**, cần kiểm tra retry topics và DLT của topology non-blocking; một DefaultErrorHandler thẳng vào DLT không thay thế đường retry topics.

## 17. Deserialization smoke: lỗi có thể xảy ra trước listener

Hai trường hợp khác nhau:

~~~text
A. StringDeserializer
      |
      v
   Listener + Jackson parse
      |
   Có thể ném exception từ listener
~~~

~~~text
B. JsonDeserializer / AvroDeserializer
      |
      +--> Parse lỗi ngay khi KafkaConsumer.poll()
                 |
           Listener chưa được gọi
~~~

Nếu dùng deserializer trực tiếp và muốn đưa lỗi decode vào DLT, Spring Kafka thường cần **ErrorHandlingDeserializer** bao ngoài delegate để container error handling có thể xử lý thông tin lỗi.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
~~~

Thay **com.example.events.OrderEvent** bằng class thật. Không mở rộng trusted packages vô hạn chỉ để test pass.

Một record decode lỗi có thể được DLT recoverer gửi dưới dạng **raw byte[]**, còn record hợp lệ có thể là POJO. DLT producer serializer phải xử lý đúng cả hai dạng nếu pipeline có thể gửi chúng. Sau upgrade, smoke nên có **payload hợp lệ và payload không deserialize được** đúng với factory thực tế.

### Khi dùng Schema Registry

Cần kiểm tra:

1. Client mới có kết nối registry bằng auth/TLS hiện có.
2. Subject name strategy và schema ID không bị đổi ngoài ý muốn.
3. Consumer mới đọc được event viết bằng phiên bản producer cũ.
4. Trong rolling rollout, consumer cũ có đọc được event do producer mới viết không.
5. Các headers hoặc content type cần thiết được bảo toàn.
6. DLT/replay tool có thể lưu và đọc record có schema không hợp lệ.

Không chỉ gửi event từ producer mới tới consumer mới; điều này có thể PASS trong khi mixed-version rollout vẫn gây lỗi.

## 18. Transaction smoke nếu dùng Kafka EOS

Một số hệ thống dùng **Kafka transactions** trong pipeline consume-transform-produce. Khi đó cần kiểm tra chính đường giao dịch thay vì chỉ producer đơn giản.

~~~text
Input topic
     |
     v
Transactional listener
     |
     v
Transform + KafkaTemplate.send(output)
     |
     v
Kafka transaction commit
     |
     v
Consumer read_committed quan sát output
~~~

Smoke nên xác nhận:

- Transactional producer khởi tạo được.
- Không bị ProducerFencedException do transactional.id cấu hình sai.
- Output đã commit xuất hiện với consumer **isolation.level=read_committed**.
- Với fault injection kiểm soát, transaction abort không làm lộ output chưa commit.
- Offset/transaction semantics đúng với listener container configuration.

**Kafka exactly-once semantics không tự bao gồm PostgreSQL hoặc API bên ngoài.** Nếu listener ghi JDBC trong khi Kafka transaction đang chạy, phải hiểu transaction boundaries và dùng idempotency hoặc outbox khi cần.

Đừng bật transactions chỉ vì muốn smoke; hãy test theo contract mà app thực sử dụng.

## 19. Consumer group, rebalance và concurrency

Sau upgrade, một group có thể thay đổi assignment behavior hoặc xuất hiện rebalance bất thường.

Nên kiểm tra:

- Member count của consumer group.
- Số partition assigned cho mỗi member.
- Không có partition chưa được xử lý do sai subscription.
- Listener concurrency phù hợp số partition và database connection pool.
- Không rebalance liên tục khi traffic ổn định.
- max.poll.interval và xử lý record dài không gây evictions.
- Rolling deployment có old/new consumers cùng group như thiết kế.
- Group ID không bị thay đổi ngoài ý muốn.

**Lag bằng 0 không đủ chứng minh healthy.** Có thể topic không có dữ liệu, group nhầm tên hoặc error handler skip record. Cần một event mới đi qua đúng group đang chạy bản nâng cấp.

Trong canary shared group, record có thể được **pod cũ** nhận. Khi đó test chỉ thấy DB có output nhưng không biết bản mới đã xử lý được. Cần gắn build identity/tracing vào acknowledgement, hoặc tạo topic/group smoke riêng cho canary.

## 20. Observability gate

Sau nâng cấp, quan sát:

| Tín hiệu | Tiêu chí |
| --- | --- |
| Deployed build/image | Đúng phiên bản mới |
| Listener lifecycle | Running, assigned partition |
| Producer error | Không có send/serialization error mới |
| Consumer error | Không tăng bất thường |
| Offset/lag | Đang tiến theo traffic, không tăng vô hạn |
| Retry attempts | Phù hợp baseline và policy |
| DLT ingress | Chỉ có record smoke lỗi hoặc lỗi thật đã biết |
| DLT publish errors | Không có lỗi publish |
| DB commit/rollback | Commit đúng, rollback không tăng bất thường |
| Processing latency | Không vượt ngưỡng so baseline |
| JVM GC/CPU/memory | Không có dấu hiệu regression rõ |
| Pod restarts/readiness | Không crash loop, không flapping |
| Rebalance | Không liên tục ngoài deployment window |

Tên metric và tags có thể thay đổi theo Spring Kafka/Micrometer/Actuator version. Nếu dashboard trống sau upgrade, cần xác định instrumentation bị thay đổi hay ứng dụng không có traffic; **thiếu metric bắt buộc vẫn là vấn đề rollout**.

Không dùng eventId, orderId hay UUID làm Prometheus tags dài hạn. Chúng phù hợp với structured log/tracing và audit có phân quyền.

## 21. Rolling upgrade và compatibility giữa hai phiên bản

Trong rolling deployment:

~~~text
orders.events
     |
     +--> old consumer
     |
     +--> new consumer
~~~

Cần xác minh:

- **New producer -> old consumer** có còn đọc được không?
- **Old producer -> new consumer** có còn đọc được không?
- Schema evolution có backward/forward compatibility theo contract?
- Exception headers/DLT record còn được replay tool cũ đọc?
- Retry topic naming có thay đổi sau nâng Spring Kafka?
- Database migration có backward compatible với old/new code đang chạy đồng thời?
- Idempotency key và consumer scope giữ nguyên ý nghĩa?
- Transactional.id prefix có gây producer fencing?
- Cả old/new versions có được quan sát bằng cùng dashboard/alert rule?

Ví dụ contract fixtures:

~~~text
old writer payload -> new reader
new writer payload -> old reader
new writer payload -> new reader
~~~

Nếu schema mới không thể đọc bằng consumer cũ, rollout cần có chiến lược riêng: versioned topic, expand-contract, feature flag hoặc deploy order đã chứng minh an toàn. Đừng sử dụng một smoke happy path trên bản mới làm lý do bỏ qua old/new compatibility.

## 22. Canary rollout và điều kiện mở rộng

Một quy trình:

~~~text
Inventory + migration review
             |
             v
        CI / Staging
             |
      Integration tests
             |
             v
       Staging smoke
             |
          PASS?
        /       \
      No        Yes
      |          |
     Fix       Canary deploy
                 |
              Canary smoke
                 |
          PASS + healthy metrics?
             /           \
            No           Yes
            |             |
       Halt/rollback   Gradual rollout
                           |
                    Monitor errors/lag
                           |
                        Full rollout
                           |
                     Post-rollout smoke
~~~

Gates nên được viết trước, ví dụ:

| Gate | Điều kiện |
| --- | --- |
| G1: readiness | Build đúng, auth/topic/assignment thành công |
| G2: produce | Record test được ack, có partition/offset |
| G3: business | Listener bản mới tạo kết quả đúng |
| G4: progress | Consumer group đi qua record theo ack mode |
| G5: duplicate | Same eventId không tăng side effect |
| G6: failure path | Invalid input tới DLT, không gây business effect |
| G7: observability | Metrics/log/traces đủ để xác nhận kết quả |
| G8: canary | Không có lag/rebalance/error spike ngoài ngưỡng |

G8 là tín hiệu trong một **cửa sổ quan sát đã thống nhất**, không phải chỉ một phút sau khi deploy. Một smoke PASS nên dẫn tới **mở rộng từng bước**, không có nghĩa bỏ qua theo dõi canary.

## 23. Chuẩn bị rollback trước khi chạy smoke

Smoke chỉ hữu ích nếu FAIL có thể dẫn tới hành động kiểm soát được.

Chuẩn bị trước rollout:

- Image digest và configuration của phiên bản cũ.
- Kế hoạch DB migration **backward compatible** hoặc roll-forward khi không thể rollback.
- Event schema versioning và mixed-version strategy.
- Topic, retry topics, DLT, ACLs, consumer group ownership.
- Quy trình pause/drain listener để tránh thêm side effects khi khắc phục.
- Tiêu chí dừng rollout theo lag, retry, DLT, errors và business reconciliation.
- Người được ủy quyền rollback hoặc mở rộng rollout.
- Cách xác minh lại output và idempotency sau khi phục hồi.

**Rollback image không xóa Kafka records đã publish**. Nếu producer mới phát schema mà consumer cũ không hiểu, quay về image cũ có thể khiến hệ thống tệ hơn. Tương tự, offset đã commit, DLT records và business DB side effects không tự quay ngược.

Với thay đổi không thể lùi, có thể phải **roll forward** bằng bản sửa có kiểm soát. Ghi rõ điều này trước deploy, không quyết định vội giữa sự cố.

## 24. Chẩn đoán khi smoke thất bại

| Triệu chứng | Nguyên nhân có thể | Nơi cần kiểm tra |
| --- | --- | --- |
| App không khởi động | Version mismatch, classpath lỗi | Dependency tree, stack trace |
| Producer timeout | Kafka broker, ACL, DNS/TLS, ISR | Producer logs, broker health |
| Ack OK nhưng DB không đổi | Listener/group sai, deserialization fail | Assignment, consumer logs |
| Listener xử lý nhưng offset không tiến | Ack mode, commit/transaction error | Committed offsets, handler |
| Offset tiến nhưng business DB sai | Recover/skip, transaction rollback, bug | DLT, DB, audit |
| Poison record chặn consumer | Deserializer/error handler cấu hình sai | ErrorHandlingDeserializer |
| DLT không có record | Sai topic/partition/serializer/ACL | Recoverer logs, topic metadata |
| Retry nhiều hơn dự kiến | Backoff/exception classification thay đổi | Handler config, attempt count |
| DLT spike sau rollout | Schema không tương thích, bug deploy | Exception categories, release marker |
| Duplicate business effects | Marker/unique constraint/idempotency gap | DB transaction, operationId |
| Rebalance liên tục | Poll interval, group config, rollout churn | Kafka group metrics/logs |
| Smoke PASS nhưng production lỗi | Probe không dùng cùng path hoặc bản cũ xử lý | Trace build identity, contract coverage |

Không tăng concurrency hoặc chỉnh ack mode bừa để “làm test pass”. Những cài đặt đó có thể thay đổi ordering, retry, duplicate và memory pressure.

## 25. Tự động hóa smoke trong pipeline triển khai

Một smoke runner có thể nhận:

~~~text
environment
deployedImageDigest
expectedSpringKafkaVersion
bootstrapServersSecretReference
smokeTopic
smokeConsumerGroup
smokeDltTopic
smokeDbNamespace
timeouts
smokeRunId
~~~

Các bước chuẩn:

~~~text
1. Confirm build/deployment identity
2. Confirm Kafka connectivity/topic metadata
3. Confirm consumer assignment
4. Send valid event with unique eventId
5. Wait for business effect from deployed listener
6. Verify offset/processing progress
7. Send duplicate event, verify one effect
8. Send invalid event to isolated smoke topic
9. Verify retry/DLT and no bad side effect
10. Read metrics, logs, rebalance and readiness
11. Emit PASS/FAIL/UNKNOWN with evidence
12. Clean only fixtures owned by smokeRunId
~~~

Report minh họa:

~~~text
smokeRunId: smoke-20261116-01
environment: staging
build: <actual-image-digest>
topic: smoke.orders.events
group: smoke-order-processor-v1

startup-auth:      PASS
producer-ack:      PASS  (partition=1, offset=208)
business-effect:   PASS  (eventId=smoke-...)
offset-progress:   PASS
duplicate:         PASS
retry-DLT:         PASS
metrics:           PASS
overall:           PASS
~~~

Mỗi PASS cần có evidence cụ thể: RecordMetadata, DB query, committed offset, DLT record, metric window hoặc trace. Khi FAIL, report nên ghi **phase, error class, build digest, eventId, thời điểm, môi trường** theo chính sách dữ liệu.

Không tự đổi kết quả sang PASS khi một bước bắt buộc không thể quan sát. UNKNOWN nên giữ canary ở trạng thái chưa thể mở rộng.

## 26. Smoke test DLT không được trở thành sự cố thật

Để test DLT phải cố ý gửi record lỗi. Điều này tạo dữ liệu tồn đọng, có thể kích hoạt alert hoặc bị retry nhiều lần.

Nên:

- Dùng DLT smoke riêng, với retention được thống nhất.
- Dùng eventId/testRunId để phân biệt với lỗi sản xuất thực.
- Không dùng payload khách hàng thật.
- Không xoá records của group/topic khác.
- Không tự động replay mọi record của smoke DLT về topic nguồn.
- Không để smoke làm nghẽn partition production.
- Giới hạn tốc độ và số lần thử.
- Lưu evidence rồi chỉ dọn data fixtures thuộc đúng run.
- Không tăng retry tối đa vô hạn chỉ để tránh lỗi trong test.

DLT records là dữ liệu vận hành, có lifecycle, owner và quyền truy cập riêng. Nếu team không theo dõi DLT sau upgrade, một hệ thống có thể trông khỏe về HTTP nhưng đang tích lũy poison messages.

## 27. Một kịch bản smoke hoàn chỉnh

### Tiền điều kiện

~~~text
- Bản nâng cấp đã deploy ở staging/canary.
- Topic smoke.orders.events tồn tại, partition count đúng.
- DLT smoke.orders.events.DLT tồn tại.
- Consumer group smoke-order-processor-v1 đã được assign.
- PostgreSQL có bảng smoke_processed_event.
- KafkaTemplate và listener dùng config tương ứng production.
- Mỗi test có eventId riêng.
~~~

### Happy path

~~~text
1. Publish valid JSON.
2. Wait for producer ack.
3. Wait for DB marker/business effect.
4. Assert one record, correct value.
5. Verify consumer progress.
6. Verify no error/DLT for eventId.
~~~

### Duplicate path

~~~text
1. Publish same eventId/payload again.
2. Wait for second record to be processed.
3. Verify exactly one business effect.
4. Verify no unintended retry storm.
~~~

### Error path

~~~text
1. Publish invalid JSON to isolated smoke topic.
2. Wait for expected DLT record.
3. Verify original topic/partition/offset metadata.
4. Verify no business side effect.
5. Verify recovered progress and no DLT send error.
~~~

### Post-smoke observation

~~~text
1. Verify build version of processing instance.
2. Observe lag/rebalance/producer errors for agreed window.
3. Compare with pre-upgrade baseline.
4. Decide PASS / FAIL / UNKNOWN.
5. Continue rollout only when gate allows it.
~~~

Nếu một bước quá hạn, báo lỗi/UNKNOWN cùng bằng chứng; không dùng Thread.sleep rồi mặc định thành công.

## 28. Những sai lầm thường gặp

### Chỉ kiểm tra /health

HTTP healthy không chứng minh listener đã được gán partition hoặc xử lý Kafka record.

### Chỉ kiểm tra KafkaTemplate.send

Ack của producer không chứng minh consumer đã xử lý nghiệp vụ.

### Dùng consumer test khác với production listener

Một KafkaConsumer thử nghiệm tự đọc thành công không chứng minh Spring listener/transaction/error handler thật đúng.

### Không biết record do pod nào xử lý

Khi old/new cùng group, bản cũ có thể xử lý smoke event. Cần build identity hoặc canary group/topic riêng.

### Assert duplicate quá sớm

Sau record đầu, DB đã có một marker; record thứ hai có thể chưa đến. Đợi đủ attempts/progress trước khi kết luận.

### Dùng sleep cố định

Sleep khiến test flaky. Chờ theo điều kiện và timeout có quan sát được.

### Bỏ qua deserialization failure

JSON hợp lệ pass nhưng record lỗi bị kẹt trước listener. Cần test cả parse trong listener và deserializer delegate theo kiến trúc.

### Bỏ qua DLT và retry

Happy path pass nhưng poison message chặn partition hoặc DLT producer không có quyền ghi.

### Chỉ test new producer -> new consumer

Mixed-version rollout có thể gãy khi old consumer đọc payload mới. Cần contract checks hai chiều.

### Dùng smoke trên dữ liệu production thật

Tạo side effects không mong muốn, DLT giả và alert nghiệp vụ. Cần dữ liệu/canary namespace riêng.

### Rollback nhưng không tính schema/offset

Image cũ không tự đảo ngược event schema mới, DB migration, offset hoặc side effects đã commit.

### Coi smoke PASS là đủ cho tải thật

Smoke ít messages không đo được long-term throughput, GC, backpressure hoặc rebalance under load. Cần canary monitoring và performance tests.

## 29. Checklist sau upgrade

- [ ] Ghi đúng artifact/version trước và sau nâng cấp.
- [ ] Đối chiếu compatibility/migration notes cho tổ hợp thư viện thực.
- [ ] Có baseline lag, retry, DLT, errors, latency, GC và rebalance.
- [ ] Xác minh topic/partition/replication/ACL/retention.
- [ ] TLS/SASL và schema registry còn hoạt động.
- [ ] Có event smoke không gây ảnh hưởng dữ liệu thật.
- [ ] Producer nhận broker ack.
- [ ] Listener **bản mới** xử lý và commit business effect.
- [ ] Consumer group progress đúng contract.
- [ ] Duplicate không làm tăng tác động lần hai.
- [ ] Retry/DLT được kiểm chứng với input lỗi ở topic riêng.
- [ ] Deserialization error path được kiểm tra khi sử dụng.
- [ ] Kafka transactions được smoke nếu pipeline dùng.
- [ ] Producer/consumer old/new schema compatibility đã được đánh giá.
- [ ] Monitoring, logs, traces và alerts hiển thị được.
- [ ] Canary không có tăng lag/rebalance/error bất thường.
- [ ] Có gate PASS/FAIL/UNKNOWN và lưu bằng chứng.
- [ ] Có rollback hoặc roll-forward plan thực thi được.
- [ ] Fixture test có ownership và cleanup riêng.

## 30. Kết luận

**Smoke test sau upgrade** của Spring Kafka không kết thúc ở việc Spring context khởi động và producer gửi được một record. Một bài smoke đáng tin phải xác minh **bản build mới** thực sự **đọc, giải mã, xử lý, commit kết quả, cập nhật offset và recovery lỗi** theo contract.

Tập smoke nên nhỏ, chạy tự động, dùng dữ liệu test an toàn và trả kết quả có bằng chứng. Khi PASS, tiếp tục mở rộng rollout theo từng giai đoạn và quan sát canary. Khi FAIL hoặc UNKNOWN, giữ rollout, điều tra theo tầng Kafka/client/listener/DB/DLT và chỉ rollback khi đã đánh giá compatibility của schema và dữ liệu được ghi.

Kết hợp smoke gate với **contract tests, idempotency, recovery tests và monitoring** sẽ biến việc nâng cấp từ một hành động “deploy rồi hy vọng” thành một quy trình **có thể kiểm chứng, kiểm soát rủi ro và phục hồi an toàn**.

