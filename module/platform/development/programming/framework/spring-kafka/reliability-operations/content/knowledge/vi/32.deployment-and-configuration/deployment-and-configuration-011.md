# Kiểm tra configuration drift trong Spring Kafka Reliability Operations

## 1. Configuration drift là gì và vì sao cần kiểm tra?

**Configuration drift** là tình trạng cấu hình đang có hiệu lực trong hệ thống **khác với cấu hình đã được phê duyệt**, hoặc hai instance được kỳ vọng chạy giống nhau lại có cấu hình khác nhau. Trong ứng dụng Spring Kafka, drift có thể xuất hiện từ file cấu hình, biến môi trường, Kubernetes ConfigMap/Secret, Helm values, custom code, Spring profiles, Kafka broker, Kafka topic hoặc ACL.

Ví dụ một hệ thống xử lý đơn hàng đang được thiết kế để chỉ ghi event khi producer có mức bảo đảm phù hợp:

~~~text
Approved configuration (baseline)
  producer.acks = all
  producer.enable.idempotence = true
  consumer.enable.auto.commit = false
  consumer.isolation.level = read_committed
  topic orders.events min.insync.replicas = 2

                    |
               Deployment
                    |
                    v
Runtime ở Pod A                      Runtime ở Pod B
  acks=all                            acks=1
  enable.idempotence=true             enable.idempotence=false
  enable.auto.commit=false            enable.auto.commit=true
  isolation.level=read_committed      isolation.level=read_uncommitted
~~~

Pod B vẫn có thể chạy và gửi/nhận message, nhưng **reliability contract** đã khác. Nếu chỉ quan sát throughput và HTTP health check, hệ thống có thể không phát hiện nguy cơ mất event, commit offset sai thời điểm hoặc đọc record chưa được commit.

Trong chương **Spring Kafka Reliability Operations → Deployment và cấu hình**, bài này tập trung:

1. Xác định cấu hình **mong muốn** và cấu hình **thực tế**.
2. Phân biệt drift ở ứng dụng, Kafka client, listener, topic, broker và hạ tầng.
3. Kiểm tra những cấu hình tác động trực tiếp đến delivery, ordering, retry, transaction và replay.
4. Xây snapshot cấu hình **an toàn**, không tiết lộ secret.
5. Tích hợp drift detection vào CI/CD, startup, kiểm tra định kỳ và alert.
6. Quy định cách sửa drift mà không gây gián đoạn hoặc phá consumer offsets.
7. Kiểm thử drift detector và xác minh hành vi thực tế sau rollout.

**Cấu hình khác chưa chắc là lỗi.** Staging thường có một broker, production có nhiều broker; các giá trị timeout, concurrency hoặc topic retention có thể khác nhau theo môi trường. Drift chỉ được kết luận sau khi so với **baseline phù hợp với environment, service, cluster và version được phê duyệt**.

## 2. Ba nguồn sự thật phải được phân biệt

Một vấn đề nền tảng là **cấu hình trên Git không đồng nghĩa cấu hình tại runtime**, và cấu hình mà Spring Environment thấy cũng chưa chắc là cấu hình Kafka client thực dùng.

~~~text
1. Approved baseline
   Git / GitOps / Policy repository
            |
            v
2. Deployed configuration
   Helm rendered manifests / ConfigMap / Env / Secrets
            |
            v
3. Effective runtime configuration
   Spring Environment -> Kafka factories -> Kafka clients
            |
            v
4. Kafka cluster effective configuration
   Broker / Topic / ACL / Quotas / Replication / ISR
~~~

Các phép so sánh cần thiết:

| Phép so sánh | Phát hiện |
|---|---|
| Baseline ↔ Git deployment manifests | Pull request sửa config ngoài phê duyệt |
| Git desired ↔ Kubernetes live resources | Thay đổi thủ công bằng kubectl, admission controller hoặc operator |
| Deployed env/config ↔ Spring Environment | Profile, command-line argument, env override hoặc property precedence |
| Spring Environment ↔ Kafka Producer/ConsumerFactory | Customizer hoặc code ghi đè thuộc tính |
| Client factory ↔ Kafka client thực | Default của Kafka client, runtime update hoặc cấu hình bên ngoài |
| Baseline broker/topic ↔ AdminClient observations | Topic retention, min ISR, partition count, cleanup policy hoặc quota bị đổi |
| Pod A ↔ Pod B trong cùng release | Rolling update chưa hoàn tất, pod cũ, khác env/secret version |

**Không dùng một phép diff của application.yml để tuyên bố hệ thống không có drift.** Điều đó không cho biết một người đã tăng partition của topic ngoài Kafka hoặc một pod cũ đang dùng profile khác.

### Ví dụ drift không biểu hiện thành lỗi ngay

Consumer được thiết kế xử lý đơn hàng theo idempotent listener và tự quản lý acknowledgement. Một rollout làm **enable.auto.commit** thành true. Ứng dụng có thể vẫn nhận và xử lý record, nhưng offset có nguy cơ được commit theo cơ chế không mong muốn nếu container thực sự sử dụng cấu hình đó. Sự khác biệt chỉ bộc lộ khi process crash giữa xử lý.

Vì thế drift detection là công cụ **ngăn suy giảm độ tin cậy trước khi xảy ra sự cố**, không chỉ tìm nguyên nhân sau incident.

## 3. Những phạm vi cấu hình cần đưa vào kiểm soát

### 3.1. Kafka producer

Các thông số thường ảnh hưởng reliability:

| Thuộc tính Kafka client | Ý nghĩa | Cần kiểm tra gì? |
|---|---|---|
| **acks** | Mức broker ACK việc ghi | Baseline quy định all hay một mức khác |
| **enable.idempotence** | Giảm duplicate do producer retry theo semantics Kafka | Có đang bật và cấu hình tương thích không |
| **retries** | Số lần thử lại ở tầng producer | Có phù hợp delivery timeout và policy không |
| **delivery.timeout.ms** | Giới hạn thời gian hoàn tất delivery | Không nhỏ hơn điều kiện request/linger cần thiết |
| **request.timeout.ms** | Timeout chờ broker response | Phù hợp với latency và SLA |
| **linger.ms** | Gom record trước gửi | Không thay đổi latency/throughput ngoài chủ đích |
| **batch.size** | Buffer batch gửi theo partition | Không làm tăng memory bất thường |
| **max.in.flight.requests.per.connection** | Số request chưa ACK trên connection | Phù hợp idempotence/ordering |
| **compression.type** | Nén batch | Không tạo khác biệt bất ngờ về chi phí và dung lượng |
| **transactional.id** | Định danh producer transactional | Không trùng giữa các instance đang chạy |
| **transaction.timeout.ms** | Giới hạn thời gian transaction | Phù hợp xử lý và broker policy |
| **key.serializer/value.serializer** | Định dạng record | Không thay đổi contract dữ liệu bất ngờ |

Với Kafka producer hiện đại, bật idempotence có các ràng buộc như **acks=all**, **retries > 0** và **max.in.flight.requests.per.connection không vượt giới hạn được hỗ trợ**. Không “sửa drift” bằng cách bật một option đơn lẻ mà không xét tính tương thích của toàn bộ producer configuration.

**acks=all** cần được hiểu cùng với **replication factor, min.insync.replicas và tình trạng ISR**. Nếu topic chỉ có một replica thì acks=all không tạo ra độ chịu lỗi tương đương topic có nhiều replica.

### 3.2. Kafka consumer

| Thuộc tính | Rủi ro khi drift |
|---|---|
| **group.id** | Consumer vào group khác, đọc lại hoặc phân phối workload khác |
| **enable.auto.commit** | Offset được commit ngoài semantics application mong muốn |
| **auto.offset.reset** | Khi group chưa có offset, có thể bắt đầu ở earliest hoặc latest khác dự định |
| **isolation.level** | read_uncommitted có thể nhìn thấy transactional records chưa commit/đã abort |
| **max.poll.records** | Khối lượng message trong một poll vượt khả năng xử lý |
| **max.poll.interval.ms** | Consumer bị coi là không poll kịp, dẫn đến rebalance |
| **session.timeout.ms / heartbeat.interval.ms** | Liveness và behavior của group bị thay đổi |
| **fetch.min.bytes / fetch.max.wait.ms** | Thay đổi latency/throughput |
| **key.deserializer/value.deserializer** | Phá schema compatibility hoặc đọc sai kiểu |
| **allow.auto.create.topics** | Client vô tình kích hoạt tạo topic mới tùy broker/config |

**auto.offset.reset** không reset một consumer group đã có committed offset. Nó chỉ quyết định vị trí khi không có offset hợp lệ theo tình huống được Kafka client hỗ trợ. Vì vậy drift ở thuộc tính này có thể chưa thấy trong vận hành thường ngày, nhưng sẽ bộc lộ khi tạo group mới hoặc offset cũ không còn tồn tại.

### 3.3. Spring Kafka listener container

Kafka consumer config chỉ là một lớp. Spring Kafka còn có:

- **AckMode**: RECORD, BATCH, MANUAL, MANUAL_IMMEDIATE hoặc chế độ khác tùy container.
- **concurrency**: số consumer/container threads.
- **pollTimeout** và các cấu hình polling.
- **CommonErrorHandler**, DefaultErrorHandler, retry/backoff và recoverer.
- **DeadLetterPublishingRecoverer** và destination DLT.
- **KafkaAwareTransactionManager** khi listener chạy transactional.
- **AfterRollbackProcessor** với transactional listener.
- **RecordFilterStrategy** và batch listener mode.
- **Container pause/resume** và authentication retry.

Drift ở code cấu hình listener thường **không xuất hiện dưới một khóa Kafka client đơn giản**. Ví dụ đổi retry policy từ ba lần sang vô hạn, hoặc đổi DLT topic, có thể làm job lặp poison message dù application.yml không đổi.

### 3.4. Broker, topic và bảo mật

| Nhóm | Những điểm cần quan sát |
|---|---|
| Topic | Existence, partitions, replication factor, cleanup.policy, retention.ms/bytes |
| Durability | min.insync.replicas, ISR, leader availability, under-replicated partitions |
| Transactions | transaction.state.log.replication.factor, transaction.state.log.min.isr, transaction.max.timeout.ms |
| Group offsets | offsets.topic.replication.factor và durability metadata theo cluster |
| Access | ACL principal/resource/operation, authentication mechanism |
| Transport | security.protocol, TLS/SASL settings, certificate rotation |
| Quotas | Producer/consumer bandwidth, request quotas có thể ảnh hưởng timeout |
| Client/server compatibility | Kafka broker/client version, protocol behavior |

Một số thông số chỉ là **broker-level**, một số là **topic-level**, một số có default do broker áp dụng. AdminClient trả cấu hình hiệu lực cùng nguồn cấu hình tùy Kafka version/permission; lệnh chỉ hiển thị **dynamic overrides** có thể bỏ sót default quan trọng.

## 4. Tạo baseline có version và phạm vi rõ ràng

Một baseline tốt phải có **identity** để người vận hành biết họ đang so với chính sách nào:

~~~yaml
policyVersion: kafka-reliability-v4
service: orders-worker
environment: production
clusterAlias: kafka-prod-a
releaseChannel: stable

producer:
  acks: all
  enable.idempotence: true
  max.in.flight.requests.per.connection: 5

consumer:
  enable.auto.commit: false
  isolation.level: read_committed
  auto.offset.reset: earliest

listener:
  ackMode: BATCH
  concurrency: 3
  retryAttempts: 3
  dltTopic: orders.events.dlt

topics:
  orders.events:
    partitions: 6
    replicationFactor: 3
    min.insync.replicas: 2
    cleanup.policy: delete
~~~

Đây là **policy manifest minh họa**, không phải cú pháp Spring Boot tự động hiểu. Một công cụ drift detector riêng hoặc quy trình CI phải đọc và so sánh manifest này với những observation phù hợp.

Các giá trị production trên chỉ là ví dụ. Với staging một broker, baseline khác có thể dùng replication factor một và min ISR một theo mục tiêu test. Không được dùng một policy production để ép môi trường test có kiến trúc khác.

Baseline nên được:

1. Version hóa trong Git hoặc policy store có lịch sử thay đổi.
2. Gắn với service, cluster, environment và release được phê duyệt.
3. Review như code, đặc biệt với thay đổi reliability-sensitive.
4. Ghi rationale cho ngoại lệ có thời hạn.
5. Không chứa giá trị secret thô.
6. Có schema/type rõ để so sánh số, boolean, duration và danh sách.

### Tách policy khỏi observation

Nếu cùng một script lấy baseline từ **chính effective runtime config** rồi so sánh runtime với bản sao đó, detector sẽ luôn báo PASS dù cấu hình đã bị đổi. Nguồn expected phải độc lập và có cơ chế phê duyệt.

Không nên coi “giá trị mặc định của Kafka hiện tại” là baseline hợp lệ khi dịch vụ từng phụ thuộc vào default khác ở version trước. Với thuộc tính reliability quan trọng, **cấu hình tường minh** thường dễ kiểm soát hơn phụ thuộc vào default thư viện.

## 5. Hiểu property precedence của Spring Boot

Một ứng dụng có thể khai báo:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
~~~

Nhưng deployment có thể đặt biến môi trường hoặc command-line argument ghi đè một vài giá trị:

~~~text
SPRING_KAFKA_PRODUCER_ACKS=1
SPRING_KAFKA_CONSUMER_ENABLE_AUTO_COMMIT=true
~~~

Khi đó file application.yml trên image vẫn “đúng” nhưng runtime có thể khác. Spring Boot có thứ tự ưu tiên PropertySources (application files, environment variables, system properties, command-line arguments, config imports...), và mức ưu tiên cuối cùng phụ thuộc phiên bản, cách bootstrap và cấu hình.

Để phát hiện, cần đọc **effective Spring Environment** và, tốt hơn, **configuration map của ProducerFactory/ConsumerFactory** sau khi customizers đã áp dụng.

### Những nơi có thể ghi đè

- application.yml và application-{profile}.yml.
- SPRING_PROFILES_ACTIVE hoặc profile kích hoạt qua launch argument.
- Biến môi trường từ Deployment/Pod/ConfigMap/Secret.
- Spring Cloud Config hoặc config import khi có sử dụng.
- JVM system properties và command-line arguments.
- Java @Configuration tự tạo ProducerFactory, ConsumerFactory hoặc ListenerContainerFactory.
- BeanPostProcessor/customizer thay đổi properties.
- Kafka client defaults thay đổi sau upgrade.
- Dynamic broker/topic configs thay đổi ngoài ứng dụng.

Một pod có thể đang dùng bản ConfigMap cũ dù Git đã cập nhật. **ConfigMap được mount làm file** và **ConfigMap được inject qua environment** cũng có vòng đời cập nhật khác nhau: env của process đang chạy không tự đổi chỉ vì ConfigMap được sửa. Đừng mặc định mọi config drift sẽ được sửa bằng một lần update ConfigMap.

## 6. Thu thập effective configuration một cách an toàn

Có ba mức quan sát ở ứng dụng:

**Mức 1 — Spring Environment:** xác minh property đã resolve.

**Mức 2 — Kafka factory:** xác minh các thuộc tính producer/consumer mà Spring Kafka dự định truyền cho client.

**Mức 3 — Kafka client chạy thật:** xác minh behavior/metrics và những giá trị đã áp dụng sau defaults, override, client instantiation. Nếu không có công cụ đọc trực tiếp runtime config từ client, kết luận cần ghi rõ giới hạn.

Ví dụ ở Spring Environment:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class KafkaEnvironmentSnapshot {

    private final Environment environment;

    public KafkaEnvironmentSnapshot(Environment environment) {
        this.environment = environment;
    }

    public String producerAcks() {
        return environment.getProperty(
                "spring.kafka.producer.acks");
    }

    public String consumerAutoCommit() {
        return environment.getProperty(
                "spring.kafka.consumer.enable-auto-commit");
    }
}
~~~

Giá trị null có thể nghĩa là property không được khai báo tường minh; **không suy ra chắc chắn client cuối cùng nhận null hoặc không có default**. Các key Kafka nằm trong Spring Boot generic map (như producer.properties và consumer.properties) có cách bind riêng; nên đọc chúng từ bound KafkaProperties hoặc factory sau khi binding.

### Kiểm tra Kafka factory thay vì chỉ application.yml

Với các bean mặc định hoặc custom factory thuộc loại tương ứng:

~~~java
import java.util.Map;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;

public final class KafkaFactorySnapshot {

    public static Map<String, Object> producer(
            DefaultKafkaProducerFactory<?, ?> factory) {
        return factory.getConfigurationProperties();
    }

    public static Map<String, Object> consumer(
            DefaultKafkaConsumerFactory<?, ?> factory) {
        return factory.getConfigurationProperties();
    }
}
~~~

Các map này biểu diễn cấu hình **đã đưa vào factory**, nhưng không bắt buộc phản ánh mọi client default hoặc tất cả client instance đang tồn tại. Cũng có ứng dụng không dùng DefaultKafkaProducerFactory/DefaultKafkaConsumerFactory; khi đó cần adapter quan sát tương ứng. Đừng ép cast interface sang implementation nếu dự án dùng factory riêng.

**Không ghi toàn bộ configuration map vào log.** Nó có thể chứa SASL password, SSL keystore password, JAAS config hoặc tài liệu nội bộ. Chỉ xuất những key thuộc allowlist đã kiểm duyệt.

## 7. Chuẩn hóa dữ liệu trước khi diff

Cùng một cấu hình có thể biểu diễn dưới các dạng:

~~~text
true, "true", TRUE
30000, "30000"
30s, 30000ms
acks=all, acks="-1" (tùy client/version representation)
cleanup.policy=compact,delete hoặc delete,compact
~~~

So sánh chuỗi thô có thể tạo **false positive** khi hai giá trị có cùng semantics. Ngược lại, normalize quá mạnh có thể làm mất khác biệt quan trọng.

Quy tắc:

1. **Boolean:** parse sang true/false trước khi so.
2. **Duration:** chuyển sang milliseconds bằng parser có đơn vị rõ.
3. **Integer:** parse thành số, không so "05" với "5" theo chuỗi.
4. **Enum:** canonicalize đúng tập giá trị hợp lệ, không sửa lỗi chính tả âm thầm.
5. **List/set:** chỉ sort khi thứ tự **không mang ý nghĩa**; không sort Bootstrap servers hoặc danh sách cần ưu tiên nếu semantics yêu cầu.
6. **Kafka aliases:** chỉ coi hai dạng tương đương khi tài liệu của **client version đang dùng** xác nhận.
7. **Absent vs default:** phân biệt "không khai báo", "client default" và "explicit override" để có thể cảnh báo drift sau upgrade.
8. **Secrets:** không chuyển secret thành dữ liệu log có thể đọc hoặc fingerprint dễ brute-force.

Ví dụ một snapshot đã chuẩn hóa:

~~~json
{
  "service": "orders-worker",
  "environment": "production",
  "policyVersion": "kafka-reliability-v4",
  "producer": {
    "acks": "all",
    "enable.idempotence": true
  },
  "consumer": {
    "enable.auto.commit": false,
    "isolation.level": "read_committed"
  }
}
~~~

Một hash trên JSON chuẩn hóa có thể giúp so sánh hai pod, nhưng **hash chỉ có giá trị nếu đầu vào cùng schema và cách canonicalize ổn định**. Nếu hai pod cùng sai cấu hình, hash của chúng có thể giống nhau; vẫn phải so với baseline đã phê duyệt.

## 8. Dùng AdminClient kiểm tra topic configuration

Kafka broker/topic là nguồn cấu hình **ngoài Spring Environment**. AdminClient cho phép quan sát topic description và configs khi principal được cấp quyền.

Ví dụ Java:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.common.config.ConfigResource;

public class KafkaTopicConfigurationObserver {

    public static void observe(String bootstrapServers,
                               String topicName) throws Exception {

        Properties props = new Properties();
        props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers);

        ConfigResource topic = new ConfigResource(
                ConfigResource.Type.TOPIC, topicName);

        try (AdminClient admin = AdminClient.create(props)) {
            Map<ConfigResource, Config> configs =
                    admin.describeConfigs(List.of(topic))
                            .all()
                            .get(10, TimeUnit.SECONDS);

            Config config = configs.get(topic);

            for (String key : List.of(
                    "min.insync.replicas",
                    "cleanup.policy",
                    "retention.ms")) {

                ConfigEntry entry = config.get(key);
                if (entry != null && !entry.isSensitive()) {
                    // Đưa key, value, source vào snapshot allowlist.
                    // Không dump toàn bộ Config.
                    String effectiveValue = entry.value();
                    System.out.println(key + "=" + effectiveValue);
                }
            }

            var description = admin.describeTopics(
                    List.of(topicName))
                    .allTopicNames()
                    .get(10, TimeUnit.SECONDS)
                    .get(topicName);

            int partitionCount = description.partitions().size();
            System.out.println("partitions=" + partitionCount);
            // Replication factor có thể xem qua replicas của partition.
        }
    }
}
~~~

Code minh họa tập trung vào **allowlist configs**; trong ứng dụng production phải chuyển output sang logger/collector đã kiểm soát, sử dụng security properties phù hợp khi kết nối broker và xử lý timeout/authorization errors. Không lấy mật khẩu từ literal trong code.

Đối với replication factor:

~~~java
int minReplicaCount = description.partitions().stream()
        .mapToInt(p -> p.replicas().size())
        .min()
        .orElse(0);
~~~

Giá trị trên là **số replica nhỏ nhất quan sát được giữa các partition**, hữu ích khi phát hiện partition replication lệch nhau. Không giả định mọi partition có replication factor giống nhau nếu topic từng được reassignment.

### Cảnh giác với nguồn config

AdminClient có thể cho biết một ConfigEntry đến từ **default**, **dynamic topic config** hoặc các nguồn khác. Drift detector nên lưu cả **source** nếu có vì cùng giá trị hiệu lực nhưng override tồn tại ngoài chính sách vẫn là tín hiệu quản trị đáng quan tâm.

Một số giá trị nhạy cảm không được trả về ở dạng plaintext. Không cố bypass cơ chế che secret; chỉ kiểm tra metadata tham chiếu hoặc health/rotation trạng thái qua kênh được phép.

## 9. Định nghĩa policy và mức độ nghiêm trọng của drift

Không phải mọi khác biệt đều yêu cầu dừng service. Nên phân loại:

| Severity | Ví dụ | Phản ứng |
|---|---|---|
| **Critical** | Producer transactional mất transaction config; listener transactional không commit offsets đúng; consumer đọc read_uncommitted khi contract yêu cầu read_committed | Chặn promotion hoặc rollout; can thiệp trước khi nhận traffic |
| **High** | acks giảm, idempotence tắt, min ISR thấp hơn baseline, DLT routing sai | Cảnh báo khẩn và rollout fix được kiểm soát |
| **Medium** | max.poll.interval, retry backoff, concurrency ngoài profile | Điều tra tác động và sửa theo change window |
| **Low** | Client ID prefix, log level, metric tags đổi có chủ đích | Theo dõi hoặc phê duyệt ngoại lệ |
| **Unknown** | Không lấy được config do ACL/network/timeout | Báo UNKNOWN, không ghi PASS |

Đây là phân loại ví dụ, phụ thuộc business SLA. Với hệ thống thanh toán, thay đổi DLT policy có thể là critical. Với consumer đọc log analytics best-effort, mức độ có thể khác.

**Không mặc định kill mọi pod khi detector gặp một transient AdminClient timeout.** Startup fail-closed có thể hợp lý với các invariant cục bộ quan trọng, nhưng nếu liên tục restart tất cả pod chỉ vì broker admin endpoint tạm không phản hồi, drift detector có thể trở thành nguồn outage mới. Hãy tách:

- **Local critical invariant**: kiểm tra tại startup, có thể fail nhanh trước khi nhận traffic.
- **External observation**: retry có giới hạn, trạng thái UNKNOWN, đánh giá cùng cluster health.
- **Deployment gate**: chặn promotion nếu chưa chứng minh đạt baseline.
- **Runtime alert**: cảnh báo drift đã xuất hiện sau khi rollout.

## 10. Ví dụ detector so sánh snapshot an toàn

Detector nên hoạt động với những snapshot **đã allowlist và chuẩn hóa**, không nhận nguyên map config có secret rồi ghi chúng vào log.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class ConfigurationDriftDetector {

    public record Drift(
            String key, String expected, String actual) {
    }

    public List<Drift> compare(
            Map<String, String> approved,
            Map<String, String> observed) {

        List<Drift> drift = new ArrayList<>();

        for (Map.Entry<String, String> entry
                : approved.entrySet()) {

            String key = entry.getKey();
            String expected = entry.getValue();
            String actual = observed.get(key);

            if (!Objects.equals(expected, actual)) {
                drift.add(new Drift(
                        key, expected,
                        actual == null ? "[MISSING]" : actual));
            }
        }

        return List.copyOf(drift);
    }
}
~~~

Ví dụ sử dụng:

~~~java
Map<String, String> approved = Map.of(
        "producer.acks", "all",
        "producer.enable.idempotence", "true",
        "consumer.isolation.level", "read_committed",
        "consumer.enable.auto.commit", "false");

Map<String, String> observed = Map.of(
        "producer.acks", "1",
        "producer.enable.idempotence", "true",
        "consumer.isolation.level", "read_uncommitted",
        "consumer.enable.auto.commit", "false");

List<ConfigurationDriftDetector.Drift> drift =
        new ConfigurationDriftDetector().compare(
                approved, observed);

// drift gồm producer.acks và consumer.isolation.level.
~~~

**Đây là bộ so sánh snapshot, không phải bộ discovery Kafka hoàn chỉnh.** Trong triển khai thật cần thêm các adapter lấy dữ liệu từ ProducerFactory, ConsumerFactory, listener container, AdminClient và manifest hạ tầng, sau đó normalize type theo schema. Một key thực có thể mang giá trị default chưa xuất hiện trong map; phải phân biệt **missing observation** với **mismatch**.

### Không in giá trị nhạy cảm khi drift

Output nên có dạng:

~~~json
{
  "service": "orders-worker",
  "policyVersion": "kafka-reliability-v4",
  "status": "DRIFT_DETECTED",
  "findings": [
    {
      "key": "producer.acks",
      "expected": "all",
      "actual": "1",
      "severity": "HIGH"
    },
    {
      "key": "consumer.isolation.level",
      "expected": "read_committed",
      "actual": "read_uncommitted",
      "severity": "CRITICAL"
    }
  ]
}
~~~

Nếu key là password, token hoặc keystore secret, **không xuất expected/actual**. Tốt hơn là không đưa những key đó vào snapshot giá trị; kiểm tra sự tồn tại, version/rotation metadata và trạng thái kết nối qua cơ chế bảo mật riêng.

## 11. Kiểm tra invariant khi ứng dụng khởi động

Một cách phòng ngừa drift là fail fast khi **effective local config** mâu thuẫn với hợp đồng không thể thỏa hiệp.

Ví dụ kiểm tra Spring Environment:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class KafkaReliabilityStartupGuard
        implements ApplicationRunner {

    private final Environment environment;

    public KafkaReliabilityStartupGuard(
            Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        require(
                "spring.kafka.producer.acks", "all");
        require(
                "spring.kafka.consumer.enable-auto-commit",
                "false");
    }

    private void require(String property, String expected) {
        String actual = environment.getProperty(property);

        if (!expected.equalsIgnoreCase(actual)) {
            throw new IllegalStateException(
                    "Kafka reliability config mismatch: "
                            + property);
        }
    }
}
~~~

Guard này minh họa một **local startup assertion** cho những property được cấu hình rõ. Nó không quan sát topic broker, không phát hiện một custom ProducerFactory bỏ qua Spring property, và không chứng minh được mọi Kafka client default. Trong production nên kiểm tra **factory config đã bind**, policy version độc lập và vị trí kiểm tra phù hợp với deployment lifecycle.

**Không hardcode một baseline toàn môi trường rồi deploy vào staging và production mà không phân biệt profile.** Nếu một invariant chỉ đúng production, guard phải biết environment/release policy đã phê duyệt; không lờ drift bằng cách tắt guard tùy tiện.

### Startup guard hay health indicator?

- Startup guard thích hợp với **cấu hình tối quan trọng phải đúng trước khi xử lý message**.
- Health/Readiness indicator có thể biểu diễn cấu hình không hợp lệ khi app đã chạy, nhưng cần tránh làm mỗi lần broker admin timeout trở thành vòng lặp restart pod.
- Một drift detector độc lập ngoài service thường phù hợp hơn cho việc quét cluster/topic và nhiều service cùng lúc.

Chọn cơ chế theo mức độ ảnh hưởng, nơi sở hữu config và khả năng rollback.

## 12. Kubernetes, Helm và GitOps

Trong Kubernetes, drift có thể do:

- Sửa Deployment/ConfigMap bằng kubectl ngoài Git.
- Helm values ở production khác commit được review.
- Một pod chưa rollout, giữ image hoặc env cũ.
- Secret version khác nhau giữa pods.
- Operator/admission controller thay field.
- Auto-scaler thay số replicas theo thiết kế (không nên coi là lỗi nếu policy cho phép).
- ExternalSecret/Secret manager cập nhật mà ứng dụng chưa reload.
- Volume mounted config thay đổi nhưng JVM chưa áp dụng lại.

Ví dụ quy trình:

~~~text
Git approved values
       |
       v
helm template
       |
       v
Kubernetes desired manifests
       |
       v
kubectl diff / GitOps reconciliation
       |
       v
Pods receive config
       |
       v
Spring Kafka runtime snapshot
       |
       v
Kafka broker/topic effective configs
~~~

Các lệnh mẫu trên môi trường có quyền phù hợp:

~~~bash
# Render manifest từ chart và values đã được review.
helm template orders-worker ./chart \
  --namespace orders \
  --values values-production.yaml > rendered.yaml

# So mong muốn với trạng thái tài nguyên hiện tại.
kubectl diff --namespace orders -f rendered.yaml

# Xem version triển khai và rollout.
kubectl --namespace orders rollout status \
  deployment/orders-worker

# Xem template/config của Deployment.
kubectl --namespace orders get deployment \
  orders-worker -o yaml
~~~

**Chỉ dùng lệnh này khi có quyền và đúng namespace/cluster.** Manifest có thể chứa Secret hoặc reference nhạy cảm, nên không tự đưa toàn bộ output vào log CI công khai. Nên dùng GitOps controller như Argo CD/Flux hoặc policy engine nếu tổ chức đã có để phát hiện/sửa drift theo quy trình phê duyệt.

Các manifest Helm/GitOps không thể chứng minh Kafka **runtime behavior** nếu application có custom code tự tạo client. Phải nối hai lớp kiểm tra.

### Rollout một phần

Giả sử có bốn pod:

~~~text
orders-worker-v12: Pod A, Pod B
orders-worker-v11: Pod C, Pod D
~~~

Trong rolling deployment, việc có hai config version có thể là **trạng thái chuyển tiếp được phép**. Drift detector cần window và release target:

1. Ghi cả image digest và config/policy version trên pod.
2. Cho phép mixed versions trong thời gian rollout được định nghĩa.
3. Sau deadline, xác minh tất cả pod chạy version được duyệt.
4. Nếu rollout stuck, cảnh báo thay vì kết luận hệ thống đã đồng nhất.
5. Kiểm tra tính tương thích protocol/topic khi hai version xử lý đồng thời.

Không tự thay consumer group ID để “làm sạch” một pod cũ; đổi group ID có thể làm consumer đọc lại dữ liệu hoặc bỏ qua tùy offset reset.

## 13. Kiểm tra Kafka topic và broker ngoài deployment

Một số drift xảy ra bởi admin thao tác trực tiếp trên Kafka:

~~~text
Approved:
  topic orders.events
  partitions=6
  replication.factor=3
  min.insync.replicas=2

Observed:
  partitions=12
  replication.factor=3
  min.insync.replicas=1
~~~

Tăng partition không phải lúc nào cũng đảo ngược an toàn. Với message keyed theo orderId, việc thay partition count có thể đổi ánh xạ key → partition cho record mới, ảnh hưởng kỳ vọng về ordering nếu ứng dụng dựa vào cùng key luôn vào cùng partition trên suốt lịch sử.

Thay **min.insync.replicas=2 xuống 1** làm giảm mức bảo đảm khi producer dùng acks=all. Vấn đề không nhất thiết hiện ra ngay nếu tất cả broker đang khỏe.

### Kafka CLI dùng khi điều tra

Ví dụ tùy phiên bản CLI:

~~~bash
# Liệt kê cấu hình topic được ghi nhận là override.
kafka-configs.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --describe

# Quan sát partitions, replicas và ISR.
kafka-topics.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --topic orders.events \
  --describe
~~~

Lệnh kafka-configs.sh có thể không in mọi giá trị default của broker. Khi cần **effective value**, dùng AdminClient describeConfigs hoặc công cụ quản trị hiểu config sources; nếu principal không có quyền DESCRIBE_CONFIGS, báo trạng thái **UNKNOWN/UNAUTHORIZED** thay vì coi “không thấy override” là PASS.

### ACL cũng là cấu hình

Ví dụ cùng một consumer app nhưng ACL bị thay khiến principal không còn READ topic hoặc group. Ứng dụng có thể timeout/retry rồi trông giống lỗi network. Kiểm tra drift về quyền truy cập cần so **principal, resource pattern, operation và cluster scope** theo baseline, không dump credentials.

## 14. Tích hợp drift detection vào CI/CD

Một pipeline có thể kiểm soát các lớp:

~~~text
Pull Request
   |
   +-- Validate baseline schema
   +-- Diff new config against approved policy
   +-- Check config ownership + change approval
   |
   v
Build / Unit tests
   |
   +-- Bind Spring Kafka properties
   +-- Assert critical invariants
   |
   v
Integration tests (Testcontainers / EmbeddedKafka)
   |
   +-- Verify behavior: send, retry, commit, rollback, DLT
   |
   v
Deploy staging
   |
   +-- Compare rendered manifests
   +-- Snapshot actual factories and Kafka topics
   |
   v
Deploy production (canary)
   |
   +-- Compare canary config against approved policy
   +-- Observe delivery/consumer lag/errors
   |
   v
Full rollout + periodic drift scan
~~~

**Static diff không thay thế behavioral integration tests.** Cùng một config như acks=all có thể không đáp ứng reliability contract khi topic replication factor/min ISR sai. Ngược lại, test một lần gửi thành công không chứng minh config sẽ chịu được broker failure.

### Contract test quan trọng

| Test | Kết quả mong đợi |
|---|---|
| Producer acks khác all ở production | Pipeline fail hoặc finding HIGH |
| Producer idempotence tắt trái policy | Critical/High drift tùy contract |
| read_committed bị đổi read_uncommitted | Drift critical cho transactional consumer |
| enable.auto.commit bật ngoài policy | Drift theo ack/transaction model |
| Topic min ISR thấp hơn baseline | Drift high, có evidence AdminClient |
| Topic không tồn tại | Block deployment nếu topic bắt buộc |
| Listener error handler thiếu DLT | Drift theo reliability contract |
| Broker không truy vấn được | UNKNOWN, không PASS |
| Một pod lệch config version sau rollout | Cảnh báo sau transition window |
| Secret rotation đổi value nhưng app đã cập nhật hợp lệ | Không log/diff plaintext secret |

### Test với Spring Boot context

Một unit/integration test có thể đặt property override để xác nhận guard phản ứng. Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.mock.env.MockEnvironment;

class KafkaReliabilityStartupGuardTest {

    @Test
    void rejectsProducerAcksDrift() {
        MockEnvironment env = new MockEnvironment()
                .withProperty(
                        "spring.kafka.producer.acks", "1")
                .withProperty(
                        "spring.kafka.consumer.enable-auto-commit",
                        "false");

        KafkaReliabilityStartupGuard guard =
                new KafkaReliabilityStartupGuard(env);

        assertThrows(IllegalStateException.class,
                () -> guard.run(new DefaultApplicationArguments()));
    }
}
~~~

Test chỉ xác minh **local guard**; nó không chứng minh Kafka broker thực nhận config. Cần thêm Testcontainers/EmbeddedKafka và AdminClient assertions nếu yêu cầu phát hiện drift ở topic hoặc behavior của transactional consumer.

## 15. Drift sau khi ứng dụng đã chạy

Một số config chỉ được Kafka client đọc **khi được khởi tạo**. Ví dụ:

~~~text
10:00 Pod started
      Consumer created with isolation.level=read_committed

10:05 ConfigMap updated:
      isolation.level=read_uncommitted

10:06 JVM vẫn chạy với consumer cũ:
      read_committed

10:15 Pod restarted:
      Consumer mới đọc config thay đổi
      read_uncommitted
~~~

Nếu detector chỉ so file config mount mới với Git, nó có thể báo drift lúc 10:05; nhưng **actual consumer behavior chưa đổi đến khi client tạo lại**. Ngược lại, nếu detector chỉ đọc client cũ, nó có thể chưa thấy một drift sắp kích hoạt sau restart.

Do đó snapshot nên có:

- Deployed resource/config revision.
- Process startup time và app release version.
- Effective Spring properties sau bootstrap.
- Factory properties.
- Client instance generation/recreation time khi có thể quan sát.
- Broker/topic config và thời điểm lấy.

**Đừng tự kết luận rằng Spring refresh config sẽ hot-reload tất cả Kafka client properties.** Nhiều thay đổi cần recreate consumer/producer/container; một số có thể được update qua API hoặc behavior đặc thù. Kiểm tra theo version Spring Kafka và cấu hình thực.

## 16. Đánh giá drift liên quan transaction và exactly-once

Các hệ thống dùng Kafka transaction cần xem nhiều giá trị cùng nhau:

~~~text
Producer:
  transactionIdPrefix distinct per active instance
  transactional producer factory enabled

Listener:
  transaction manager associated with Kafka listener container
  offsets sent in Kafka transaction as designed

Consumer:
  isolation.level=read_committed for downstream
  enable.auto.commit=false if contract requires

Broker:
  transaction coordinator healthy
  transaction timeout limits compatible
  replication/ISR adequate
~~~

**Có transactionIdPrefix không chứng minh exactly-once end-to-end.** Nếu listener container không được cấu hình để commit consumer offset vào cùng Kafka transaction, hệ thống có thể vẫn commit output và offset không đồng bộ.

Drift detector nên kiểm tra cả **wiring của listener** và chạy behavioral test:

1. Consume input.
2. Gửi output trong transaction.
3. Khi thành công, output visible với read_committed và offset input commit như thiết kế.
4. Khi thất bại trước commit, output aborted và offset không tiến như transaction thành công.

Đối với dual-write **database + Kafka**, kiểm thử cần tách rõ transaction DB và transaction Kafka. Nếu yêu cầu tránh lost events, cân nhắc transactional outbox hoặc cơ chế reconcile; không coi việc bật Kafka transaction là giải quyết atomicity của hai resource.

## 17. Drift liên quan consumer lag, retry và DLT

Một thay đổi cấu hình không nhất thiết gây lỗi trực tiếp. Ví dụ:

~~~text
Approved:
  max.poll.records=200
  max.poll.interval.ms=300000
  listener concurrency=4
  retryAttempts=3

Observed:
  max.poll.records=2000
  max.poll.interval.ms=300000
  listener concurrency=1
  retryAttempts=100
~~~

Hệ quả có thể là một poll lấy quá nhiều record, xử lý lâu vượt max.poll.interval, rebalance, redelivery và consumer lag tăng. Retry quá nhiều còn giữ partition gặp poison message trong thời gian dài.

Phản ứng nên gồm:

- Đối chiếu config và change history.
- Xem latency xử lý mỗi record, poll duration, partition assignment và group rebalance count.
- Xác minh DLT/retry policy và giới hạn attempts.
- Dùng load test để chứng minh baseline mới không gây duplicate/lag ngoài mong muốn.
- Tránh đổi group ID hoặc reset offset như biện pháp khắc phục cấu hình đơn giản.

Các tham số có thể có giá trị khác nhau đúng chủ đích theo workload. Hãy so với **service-specific policy** chứ không dùng một baseline duy nhất cho mọi consumer.

## 18. Quan sát và cảnh báo configuration drift

Một drift event nên có đủ dữ liệu truy vết thay đổi:

~~~json
{
  "event": "kafka.configuration.drift.detected",
  "service": "orders-worker",
  "environment": "production",
  "clusterAlias": "kafka-prod-a",
  "policyVersion": "kafka-reliability-v4",
  "release": "orders-worker-2.8.1",
  "observedAt": "2026-11-16T10:30:00+07:00",
  "scope": "consumer",
  "key": "isolation.level",
  "expected": "read_committed",
  "actual": "read_uncommitted",
  "severity": "CRITICAL",
  "status": "DRIFT_DETECTED"
}
~~~

Đây là schema minh họa. Với field nhạy cảm, chỉ log key/scope và trạng thái, **không log actual/expected secret**.

Các metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| kafka_config_drift_findings | Số finding theo service, scope, severity |
| kafka_config_drift_scan_success | Lần quét có lấy đủ dữ liệu không |
| kafka_config_drift_scan_timestamp_seconds | Lần quét gần nhất |
| kafka_config_drift_age_seconds | Thời gian finding chưa được xử lý |
| kafka_config_drift_scan_duration_seconds | Thời gian thu thập và so sánh |
| kafka_reliability_policy_version_info | Thông tin version policy đang áp dụng |

Tên metric là **đề xuất**, không phải meter mặc định của Spring Kafka. Khi xuất qua Prometheus:

- Không dùng password, Kafka message key, customerId hoặc raw URL làm label.
- Tránh dùng mỗi pod UID hay transactional.id động làm label trên mọi metric nếu gây high cardinality.
- Dùng service, environment, scope, severity và policy revision khi số lượng giá trị được kiểm soát.

### Khi nào cảnh báo?

**Immediate alert** cho critical drift ở môi trường đang xử lý dữ liệu quan trọng. **Scheduled review** cho medium/low drift. **Scan failure/UNKNOWN** cũng cần alert sau ngưỡng nếu detector không thể kiểm tra cluster trong thời gian dài.

Không gửi cùng một alert mỗi lần quét khi finding chưa đổi; cần grouping/dedup và ghi nhận thời điểm firstSeen/lastSeen. Nếu có ngoại lệ được phê duyệt, phải có owner, lý do và expiration.

## 19. Runbook điều tra drift

Khi detector báo producer.acks từ all thành 1:

1. Xác định service, namespace, pod, image digest, Kafka cluster và policy version.
2. Kiểm tra drift có xuất hiện ở **tất cả pods** hay chỉ một số pods.
3. Đọc deployment manifest và effective Spring properties của các pod liên quan bằng kênh có quyền phù hợp.
4. Kiểm tra ProducerFactory config, client generation và custom configuration code.
5. Tra Git/Helm/GitOps change history, các manual overrides và thời điểm rollout.
6. Dùng AdminClient đối chiếu topic replication/min ISR và sức khỏe ISR.
7. Đánh giá đã có message bị ảnh hưởng hay chưa; kiểm tra output/offset và incident window.
8. Quyết định rollback hay rollout bản sửa có kiểm soát.
9. Sau sửa, xác minh effective runtime config và behavior, không chỉ diff Git.
10. Lưu audit lý do, người duyệt, thời điểm hoàn tất và test ngăn tái diễn.

### Không sửa bằng cách đổi mọi thứ cùng lúc

Nếu thấy acks, idempotence, min ISR, partitions và retry policy đều lệch, cần ưu tiên khôi phục **reliability invariant** theo thứ tự có kiểm soát. Thay partition count hoặc group ID có thể có tác động không thể rollback đơn giản, nên không áp dụng “đồng bộ lại với Git” một cách mù quáng.

### Sửa config tại nguồn sở hữu

| Drift source | Hướng xử lý |
|---|---|
| Git values sai | Pull request + review + rollout |
| Live Deployment bị sửa tay | GitOps reconcile / managed rollback |
| Env/profile override sai | Sửa source env/ConfigMap/Secret reference, restart có kiểm soát |
| ProducerFactory custom code | Sửa bean configuration, unit/integration test |
| Broker/topic override sai | Thao tác AdminClient/operator được phê duyệt |
| ACL/quota thay đổi | Phục hồi qua security/platform change control |
| Pod cũ sau rollout | Điều tra rollout, readiness, draining và canary |
| Dynamic config chưa được client áp dụng | Recreate client/container theo semantics hỗ trợ |

## 20. Bảo vệ thông tin khi thu thập configuration snapshot

Cấu hình Kafka có thể chứa:

- SASL JAAS config và password.
- SSL truststore/keystore paths và passwords.
- API tokens của Schema Registry hoặc các service liên quan.
- OAuth client secrets và callback handler config.
- Broker internal endpoints và thông tin topology.
- Tên topic/customer/tenant có tính nhạy cảm theo chính sách.

**Không dump nguyên Environment, KafkaProperties hoặc Kafka factory maps vào log.** Thay vào đó:

1. Duy trì allowlist các key reliability không nhạy cảm.
2. Với secret, chỉ kiểm tra metadata được phép như secret reference, rotation version hoặc trạng thái auth, không in giá trị.
3. Phân quyền snapshot/Actuator/configprops/env endpoints; không bật public.
4. Không lưu các file kubectl/Helm chứa secret vào artifact CI công khai.
5. Mã hóa đường truyền và lưu trữ snapshot ở hệ thống audit có retention phù hợp.
6. Tránh thông báo lỗi chứa raw value của cấu hình chưa được phân loại.
7. Đánh giá tác động của việc fingerprint một secret: secret có entropy thấp có thể bị đoán qua hash không khóa.

Một report có thể ghi:

~~~text
key=sasl.jaas.config
scope=consumer
status=SECRET_REFERENCE_CHANGED
expectedSecretVersion=v12
observedSecretVersion=v13
actualSecretValue=[NOT_COLLECTED]
~~~

Đây chỉ là minh họa khi hệ thống secret manager có metadata version được phép đọc. **Không mặc định secret version khác là drift xấu**: có thể là rotation được phê duyệt.

## 21. Ma trận kiểm thử drift detection

| Kịch bản | Thao tác tạo drift trong test | Expected detector result |
|---|---|---|
| DRIFT-01 | Không thay đổi baseline | PASS |
| DRIFT-02 | Producer acks all → 1 | HIGH/CRITICAL theo policy |
| DRIFT-03 | Producer idempotence true → false | Finding tương ứng |
| DRIFT-04 | Consumer read_committed → read_uncommitted | CRITICAL với transactional contract |
| DRIFT-05 | Consumer auto commit false → true | Finding theo ack model |
| DRIFT-06 | Consumer group.id bị đổi | Cảnh báo khả năng replay/offset behavior |
| DRIFT-07 | Topic min ISR 2 → 1 | HIGH |
| DRIFT-08 | Topic partition count thay đổi | Finding và yêu cầu xem ordering |
| DRIFT-09 | Topic không tồn tại | FAIL/UNKNOWN theo deploy policy |
| DRIFT-10 | AdminClient permission denied | UNKNOWN/UNAUTHORIZED, không PASS |
| DRIFT-11 | Spring property đúng nhưng factory custom override | Factory-level detector phát hiện |
| DRIFT-12 | Env override application.yml | Effective config khác file |
| DRIFT-13 | Một pod vẫn dùng old release | Finding sau rollout window |
| DRIFT-14 | Thay value secret khi rotation hợp lệ | Không leak secret; policy xử lý ngoại lệ |
| DRIFT-15 | Kafka client version upgrade đổi default | Phát hiện absent/default semantic change |
| DRIFT-16 | Listener DLT topic đổi | Listener policy finding |
| DRIFT-17 | Retry policy quá nhiều attempts | Cảnh báo theo SLA |
| DRIFT-18 | Topic config change ngoài Git | AdminClient observation khác baseline |
| DRIFT-19 | Một lần scan network timeout | UNKNOWN với retry có giới hạn |
| DRIFT-20 | Drift đã được sửa | Finding RESOLVED, history giữ nguyên |

### Các loại test nên có

**Unit test:** normalize boolean, duration, enum, missing key, unknown state; so expected/observed và severity chính xác.

**Spring context test:** cấu hình một profile/override cố ý, khởi động context, kiểm tra Kafka factories và startup guard. Tránh dựa hoàn toàn vào Environment khi customizers có thể đổi factory.

**Integration test với EmbeddedKafka/Testcontainers:** tạo topic và AdminClient, thay topic-level configs có kiểm soát, xác minh observer đọc đúng. Cần broker test độc lập và policy dành riêng cho test.

**Behavioral test:** với producer/consumer transactional, kiểm tra commit/abort visibility bằng consumer read_committed; với listener, kiểm tra offset/ retry/DLT theo contract. Đây là bằng chứng bổ sung rằng runtime thực thi đúng, không chỉ có chuỗi config đúng.

**Deployment test:** render Helm, so với live resources ở namespace test, kiểm tra image/config versions và behavior khi rolling update.

**Security test:** inject sentinel secret giả trong test environment, kiểm tra report/log không chứa literal sentinel.

## 22. Những sai lầm thường gặp

**Chỉ so application.yml với Git.** Env, profiles, custom factory, Kafka defaults và broker/topic config có thể khác.

**Lấy actual runtime làm baseline.** Detector tự so cùng một nguồn nên luôn PASS.

**So sánh raw strings mà không normalize type.** true và "true" có thể bị báo drift giả; nhưng normalize không được che mất khác biệt semantic.

**Coi property không khai báo là client nhận null.** Kafka client có defaults và Spring có binding/customization; cần phân biệt absent/default/explicit.

**Chỉ xem producer.acks mà bỏ qua min ISR/replication factor.** Bảo đảm durability phải xét đồng thời broker và topic.

**Cho rằng acks=all luôn ngăn mất record trong mọi failure mode.** Còn phụ thuộc replication, ISR, retention và điều kiện lỗi.

**Coi bật transactionIdPrefix là đủ exactly-once.** Listener offset transaction, read_committed downstream và side effects ngoài Kafka cần thiết kế riêng.

**Gọi read_uncommitted tương đương read_committed.** Một consumer có thể thấy record bị abort.

**Thay consumer group ID để sửa drift.** Có thể gây replay hoặc bỏ qua dữ liệu tùy offset reset.

**Tự giảm partition count để quay về baseline.** Kafka không hỗ trợ giảm partition theo cách đơn giản; cần kế hoạch migration nếu buộc phải thay đổi.

**Coi dynamic config không phản hồi là PASS.** Không quan sát được là UNKNOWN, không phải không có drift.

**Dump mọi config vào log để debug.** Có thể lộ SASL/SSL secrets và topology nhạy cảm.

**Tự restart tất cả pods khi broker admin API timeout.** Drift detector có thể gây outage thứ cấp.

**Không phân biệt rollout window với drift tồn tại lâu.** Trong rolling update, hai version có thể hợp lệ tạm thời.

**Sửa drift ở runtime mà không cập nhật source of truth.** Lần reconcile sau có thể ghi đè lại fix và drift tái diễn.

**Chỉ có cảnh báo mà không có owner, SLA và runbook.** Finding tồn tại lâu và không tạo thay đổi thực tế.

## 23. Quy trình triển khai kiểm tra configuration drift

Một quy trình vận hành có thể áp dụng theo các bước:

1. **Xác định reliability contract** của từng service: delivery, ordering, consumer offset, transaction, retry và DLT.
2. **Tạo baseline versioned** cho environment/cluster/service, không chứa secrets.
3. **Lập bản đồ nguồn config:** Git, Helm, ConfigMap/Secret, Spring Environment, Kafka factories, listener containers, broker/topic.
4. **Thu thập observed snapshot** qua các adapter được cấp quyền, chỉ allowlist giá trị an toàn.
5. **Chuẩn hóa theo schema** và phân biệt default/override, missing/unknown.
6. **So sánh với baseline độc lập**, sinh findings có severity và evidence.
7. **Đặt cổng CI/CD** cho critical config và canary/rollout policy.
8. **Quét định kỳ sau deploy**, phát hiện thay đổi tay hoặc pod lệch version.
9. **Kiểm tra behavioral contracts** ở test Kafka thật cho giao dịch, retry, DLT và offset.
10. **Alert có owner và expiration cho ngoại lệ**, giữ audit firstSeen/lastSeen/resolvedAt.
11. **Sửa tại nguồn sở hữu**, rollout cẩn thận và tránh đổi offset/partition ngoài kế hoạch.
12. **Xác minh kết quả sau sửa** ở runtime và broker, không chỉ khi Git diff về zero.

## 24. Tổng kết

**Kiểm tra configuration drift** trong Spring Kafka không đơn giản là kiểm tra một file YAML có thay đổi hay không. Reliability của hệ thống phụ thuộc vào **cấu hình hiệu lực ở nhiều lớp**: Spring Boot binding, producer và consumer factories, listener container, Kafka broker/topic, deployment infrastructure và sự khác biệt giữa các pod đang chạy.

Một cơ chế tin cậy phải có **approved baseline độc lập**, thu thập **observed snapshot có nguồn gốc rõ**, normalize dữ liệu, phân loại drift theo mức độ ảnh hưởng và không tiết lộ secret. Kết hợp **CI/CD diff, kiểm tra startup, quét runtime, AdminClient và behavioral tests** sẽ giúp phát hiện sớm những thay đổi có thể gây mất event, duplicate, sai offset, transaction visibility hoặc retry/DLT behavior.

Điểm quan trọng nhất là **không nhầm cấu hình nhìn thấy trên Git với hành vi thực tế**. Chỉ khi cấu hình cuối cùng được đối chiếu với baseline đúng môi trường, broker/topic được kiểm tra và các reliability contracts được test, đội vận hành mới có cơ sở để tin rằng một rollout không vô tình làm suy giảm độ tin cậy của Spring Kafka.
