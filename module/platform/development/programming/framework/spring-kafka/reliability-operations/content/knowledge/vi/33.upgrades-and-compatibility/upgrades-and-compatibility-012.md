# Theo dõi release notes cho Spring Kafka Reliability Operations

## 1. Vì sao theo dõi release notes là một nhiệm vụ vận hành?

Một ứng dụng Spring Kafka có thể chạy ổn định suốt nhiều tháng nhưng bắt đầu gặp sự cố sau khi cập nhật một thư viện, đổi phiên bản Spring Boot, nâng cấp Kafka broker hoặc thay JDK. Thay đổi không nhất thiết làm code biên dịch lỗi. Nó có thể tác động đến **consumer group coordination, transaction, retry, deserialization, offset commit, delivery guarantee và cấu hình mặc định** — những hành vi chỉ bộc lộ khi có lỗi mạng, rebalance hoặc process restart.

Ví dụ một pipeline:

~~~text
Order Service
     |
     v
Kafka producer ----> orders.created
                           |
                           v
                  Spring Kafka @KafkaListener
                           |
                           +-- Validate
                           +-- Update database
                           +-- Publish orders.enriched
                           |
                           v
                    Commit offset
~~~

Nếu nâng cấp làm thay đổi cách cấu hình error handler hoặc transaction manager, job có thể tiếp tục nhận message nhưng **retry nhiều hơn dự kiến, chuyển DLT sai, commit offset không đúng thời điểm hoặc đọc record chưa được commit**. Việc theo dõi release notes giúp phát hiện và kiểm thử những thay đổi này **trước khi rollout**.

Trong chương **Spring Kafka Reliability Operations → Nâng cấp và tương thích**, bài **Theo dõi release notes** hướng dẫn xây một quy trình liên tục:

1. Biết chính xác những thành phần và phiên bản đang chạy.
2. Theo dõi nguồn release notes, migration guides và security advisories chính thống.
3. Phân loại thay đổi theo tác động lên độ tin cậy.
4. Đối chiếu compatibility matrix và dependency graph.
5. Chuyển từng thay đổi thành action, owner và test có thể kiểm chứng.
6. Thực hiện upgrade qua canary, đo metric và chuẩn bị rollback.
7. Lưu bằng chứng để các đợt nâng cấp sau không lặp lại cùng cuộc điều tra.

Điều quan trọng: **release notes không chỉ dành cho developer khi muốn dùng tính năng mới**. Đây là đầu vào cho quản trị thay đổi, vận hành production, bảo mật và kiểm soát chất lượng dữ liệu.

## 2. Phân biệt release notes, changelog, migration guide và advisory

Các tài liệu này có vai trò khác nhau:

| Loại tài liệu | Nội dung thường gặp | Câu hỏi cần trả lời |
|---|---|---|
| **Release notes** | Tính năng, bug fixes, thay đổi hành vi, deprecation | Phiên bản mới có gì ảnh hưởng đến hệ thống? |
| **Changelog** | Danh sách thay đổi chi tiết, commit/issue/PR | Thay đổi cụ thể nằm ở đâu? |
| **Migration/upgrade guide** | Thao tác bắt buộc, API bị loại bỏ, cấu hình mới | Cần sửa code/config thế nào? |
| **Compatibility matrix** | Bộ phiên bản framework/client/broker/JDK được hỗ trợ | Tổ hợp đang dùng có hợp lệ không? |
| **Security advisory** | Lỗ hổng, phạm vi ảnh hưởng, bản vá, mitigation | Có phải nâng cấp khẩn cấp không? |
| **Deprecation notice** | API/config sẽ ngừng hỗ trợ | Cần lập kế hoạch trước mốc nào? |
| **Known issues** | Hồi quy hoặc hạn chế của bản release | Có nên hoãn bản nâng cấp này? |
| **Issue/PR discussion** | Bối cảnh và trường hợp góc | Có liên quan tới workload thực của mình không? |

Ví dụ một release note ghi:

~~~text
Changed default retry behavior for a listener component.
See migration guide for configuration changes.
~~~

Không thể chỉ ghi “đã đọc release notes” rồi đóng task. Phải xác định **listener nào đang dùng**, default cũ và mới, tác động lên số lần xử lý, thời gian xử lý poison message, DLT routing, rồi viết regression test chứng minh policy mong muốn.

Ngược lại, một mục thay đổi giao diện quản trị không liên quan tới runtime Kafka có thể được ghi nhận là **not applicable** sau khi kiểm tra, thay vì tạo công việc không cần thiết.

### Không đồng nhất mức thay đổi phiên bản với mức rủi ro

- **Major release** thường chứa thay đổi tương thích lớn, nhưng không có nghĩa mọi hệ thống đều sẽ gặp lỗi.
- **Minor release** có thể có tính năng mới, thay đổi default hoặc migration concern tùy dự án.
- **Patch release** thường sửa lỗi, nhưng một bản vá concurrency, consumer rebalance hay transaction vẫn có thể thay đổi behavior mà test cần bao phủ.
- **Security patch** có thể cần ưu tiên cao dù số phiên bản tăng rất nhỏ.

Đừng quyết định “patch thì an toàn để auto deploy” chỉ bằng SemVer. Phải đánh giá **thành phần và đường chạy thực tế**.

## 3. Bản đồ các thành phần cần theo dõi

Một hệ thống Spring Kafka không chỉ phụ thuộc vào một artifact:

~~~text
Application / business code
     |
     +-- Spring Boot version / BOM
     |       |
     |       +-- Spring Framework
     |       +-- Spring Kafka
     |       +-- Micrometer / Actuator
     |       +-- Spring Retry (nếu được dùng)
     |
     +-- Kafka Java clients
     |       +-- Producer / Consumer / AdminClient
     |
     +-- Serialization / Schema Registry / Avro, JSON, Protobuf
     |
     +-- Kafka broker cluster / KRaft / cluster protocol
     |
     +-- Kafka Connect, MirrorMaker, Streams (nếu có)
     |
     +-- Deployment: JDK, container image, Kubernetes, Helm
     |
     +-- External systems: DB, outbox, transaction boundaries
~~~

Hãy lập inventory tối thiểu:

| Thành phần | Cần lưu gì | Vì sao? |
|---|---|---|
| Spring Boot | Version, BOM/platform | Quyết định version thư viện được quản lý |
| Spring Kafka | Resolved version của spring-kafka | Listener, KafkaTemplate, retry, transaction APIs |
| kafka-clients | Resolved runtime version | Producer/consumer protocol và defaults |
| Spring Framework | Version | Lifecycle, transactions, observability, bean APIs |
| Spring Retry | Version nếu dùng | Backoff/retry semantics ở tầng ứng dụng |
| Kafka broker | Version từng broker và trạng thái rollout | Protocol/features và vận hành cluster |
| JDK | Vendor/version/major | Compatibility và runtime security |
| Serializer/registry | Client/serializer version và schema compatibility mode | Tránh consumer đọc sai payload |
| Test libraries | spring-kafka-test, Testcontainers version | Độ tin cậy của integration tests |
| Container image | Image digest, build revision | Reproducibility và rollback |
| Config baseline | Policy version, key client/topic | Phát hiện config drift cùng đợt nâng cấp |

**Phải lấy version đã được resolve**, không chỉ version được viết trong build file. Dependency management, transitive dependency, constraints hoặc một plugin có thể làm version runtime khác với version developer tưởng đang sử dụng.

## 4. Những nguồn release notes đáng tin cậy

Theo dõi từ **nhà phát hành và tài liệu chính thức** trước, sau đó dùng issue/PR để đào sâu:

| Thành phần | Nguồn ưu tiên | Ghi chú |
|---|---|---|
| Spring Kafka | https://github.com/spring-projects/spring-kafka/releases | Release entries, tag, vấn đề liên quan |
| Spring Kafka | https://docs.spring.io/spring-kafka/reference/ | Reference guide và mục What's New / migration phù hợp version |
| Apache Kafka | https://kafka.apache.org/downloads | Bản phát hành chính thức và các liên kết |
| Apache Kafka | https://kafka.apache.org/documentation/ | Broker/client config, protocol, upgrade guides |
| Apache Kafka source | https://github.com/apache/kafka/releases | Tag/release metadata khi cần đối chiếu |
| Spring Boot | https://github.com/spring-projects/spring-boot/releases | Release notes liên quan đến BOM, autoconfiguration |
| Spring Boot | https://docs.spring.io/spring-boot/ | Dependency versions và tài liệu migration theo release |
| Spring Framework | https://github.com/spring-projects/spring-framework/releases | Thay đổi nền tảng có thể ảnh hưởng Spring Kafka |
| GitHub Advisories | https://github.com/advisories | Tìm theo package và phạm vi version |
| NVD / CVE | https://nvd.nist.gov/ | Tham khảo mã CVE, không thay thế advisory vendor |

URL là các **điểm bắt đầu tra cứu**, không phải tuyên bố về phiên bản mới nhất. Khi thực hiện một đợt nâng cấp thật, cần mở **tag/version đích cụ thể**, kiểm tra ngày phát hành, migration guide, issue đã được xác nhận và hỗ trợ của nhà phát hành.

### Release feed và notification

Cách theo dõi khả thi:

- Dùng GitHub **Watch → Custom → Releases** cho các repository quan trọng.
- Theo dõi nguồn feed, RSS hoặc automation được vendor cung cấp nếu ổn định.
- Dùng Dependabot/Renovate để tạo PR khi dependency có bản mới, nhưng coi PR đó là **tín hiệu cần review**, không phải phê duyệt deploy.
- Theo dõi advisory bảo mật trong hệ thống quản lý lỗ hổng của tổ chức.
- Tạo lịch review định kỳ cho runtime và broker, không chỉ chờ đến lúc nâng cấp.

Không nên dựa vào một blog cá nhân hoặc bài đăng mạng xã hội làm nguồn duy nhất cho một thay đổi ảnh hưởng tính toàn vẹn message.

## 5. Thiết lập inventory phiên bản đang vận hành

Trước khi đọc phiên bản mới, phải biết phiên bản hiện tại. Ví dụ một record inventory:

~~~yaml
service: orders-event-worker
environment: production
release: orders-worker-2026.11
buildRevision: "<git-sha>"
imageDigest: "<sha256-image-digest>"

runtime:
  javaMajor: 21
  springBoot: "<resolved-version>"
  springKafka: "<resolved-version>"
  kafkaClients: "<resolved-version>"
  springRetry: "<resolved-version-if-present>"

kafka:
  cluster: prod-kafka-a
  brokerVersions: ["<broker-version>"]
  clientMode: consumer-and-producer
  transactionalProducer: true
  listenerConcurrency: 4
  consumerGroup: orders-worker-v1

reliabilityContract:
  ackMode: MANUAL
  isolationLevel: read_committed
  deadLetterTopic: orders.events.dlt
  retryPolicyId: orders-retry-v3
~~~

Các giá trị đặt trong dấu ngoặc kép như \`<resolved-version>\` chỉ là placeholder, không phải version đang tồn tại. Trong vận hành thật, inventory cần có **thời điểm thu thập và nguồn evidence**. Một manifest không được cập nhật sau deploy thì không còn đáng tin.

### Nên lấy version từ đâu?

1. Build tool: dependency graph đã resolve.
2. Container image: build metadata, SBOM và image digest.
3. Runtime: Spring Boot build info hoặc endpoint nội bộ có phân quyền.
4. Kafka cluster: công cụ quản trị broker, metrics và danh sách broker version.
5. Config baseline: GitOps/Helm revision, topic configs và listener configuration.

Không nên suy ra Kafka broker version từ version \`kafka-clients\` của ứng dụng. Đây là **hai thành phần được nâng cấp độc lập** với compatibility constraints riêng.

## 6. Xem resolved dependencies bằng Gradle

Những lệnh thường hữu ích khi kiểm tra phiên bản thực tế của ứng dụng Gradle:

~~~bash
# Xem toàn bộ dependency graph ở runtime.
./gradlew dependencies --configuration runtimeClasspath

# Tìm version Spring Kafka cuối cùng đã được resolve.
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-kafka

# Tìm Kafka Java client thực sử dụng.
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency kafka-clients

# Nếu dùng Spring Retry.
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-retry

# Phân biệt dependencies của test với runtime.
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Các lệnh là **hướng dẫn để người học sử dụng trong dự án**, không phải kết quả đã chạy cho bài học này. Trong repository có nhiều subprojects, cần thêm path project tương ứng, ví dụ \`:orders-worker:dependencyInsight\`. Tên configuration cũng có thể khác với plugin hoặc module type đang dùng.

### Đặc biệt lưu ý dependency management của Spring Boot

Một dự án dùng Spring Boot BOM có thể không khai báo version trực tiếp cho \`spring-kafka\`:

~~~groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

Phiên bản được chọn có thể đến từ BOM/constraints. Nếu ứng dụng override \`kafka-clients\` thủ công, điều đó có thể tạo tổ hợp không nằm trong compatibility matrix mà bộ Spring Boot release đã kiểm thử.

Quy trình hợp lý:

1. Chọn **Spring Boot line** được dự án hỗ trợ.
2. Xem dependency versions mà BOM quản lý.
3. Đối chiếu Spring Kafka và kafka-clients compatibility.
4. Chỉ override version nếu có lý do rõ, phạm vi kiểm thử đủ và đã ghi vào quyết định nâng cấp.
5. Kiểm tra \`runtimeClasspath\` **và** \`testRuntimeClasspath\` sau thay đổi.

Không mặc định “Kafka client phiên bản cao hơn thì luôn tương thích tuyệt đối với mọi broker cũ”. Kafka có chính sách tương thích protocol được tài liệu hóa, nhưng tính năng mới, version floor và behavior của các thành phần tích hợp cần được xác nhận cụ thể.

## 7. Lập compatibility matrix thay vì đoán theo số phiên bản

Trong một upgrade, có ít nhất bốn chiều độc lập:

~~~text
Spring Boot line
       |
       +--> Spring Framework line
       |
       +--> Spring Kafka line
                    |
                    +--> kafka-clients version
                    |
                    +--> Kafka broker supported versions
                    |
                    +--> JDK required/supported
~~~

Một bảng quyết định có thể viết:

| Dimension | Currently deployed | Proposed target | Evidence | Status |
|---|---|---|---|---|
| Spring Boot | từ SBOM/build | target version | Official dependency table | OPEN |
| Spring Kafka | runtime resolved | target release | Release notes + compatibility | OPEN |
| kafka-clients | runtime resolved | target resolved | Dependency graph + docs | OPEN |
| Kafka broker | cluster inventory | target cluster | Kafka upgrade guide | OPEN |
| Java | runtime version | target JDK | Support requirements | OPEN |
| Serializer/registry | artifact/version | target version | Vendor compatibility | OPEN |
| Schema | producer/consumer versions | target schema | Registry compatibility settings | OPEN |

Trong bảng trên, **OPEN** có nghĩa còn cần kiểm tra bằng tài liệu thực; đừng đánh dấu PASS chỉ vì ứng dụng biên dịch được.

### Client-broker compatibility khác API compatibility

- **Client ↔ broker:** giao thức Kafka và feature support khi client/broker khác version.
- **Spring Kafka ↔ Kafka client:** sự tương thích giữa wrapper framework và thư viện Kafka.
- **Source/binary API:** Java code có biên dịch/chạy với class/method mới không.
- **Behavioral compatibility:** output, error handling, offsets, transactions có giữ đúng như trước không.
- **Data compatibility:** serializer và consumer có đọc được record đã tồn tại không.
- **Operational compatibility:** monitoring, ACL, TLS, deployment, JDK và config defaults có phù hợp không.

Một kiểm thử unit xanh chỉ chứng minh một phần của compatibility; nó không thay thế kiểm thử broker/consumer group hoặc schema.

## 8. Cách đọc một release note theo phương pháp có hệ thống

Không đọc qua tiêu đề rồi kết luận “không liên quan”. Với mỗi release mục tiêu:

1. Xác định **version hiện tại** và **version đích**.
2. Thu thập **toàn bộ release notes của các phiên bản nằm giữa**, không chỉ bản đích.
3. Đọc migration guide và danh sách known issues.
4. Tìm keywords liên quan đến runtime của hệ thống.
5. Gắn từng mục với component đang dùng.
6. Đánh giá thay đổi có ảnh hưởng reliability contract không.
7. Tạo action: code, config, test, rollout, monitoring hoặc không áp dụng.
8. Ghi source URL, version, owner, rationale và trạng thái.

### Bộ từ khóa ưu tiên cho Spring Kafka

~~~text
transaction
KafkaTransactionManager
producer factory
KafkaTemplate
consumer factory
listener container
AckMode / acknowledge
offset commit
rebalance / assignment
error handler
DefaultErrorHandler
AfterRollbackProcessor
retry / backoff
retry topic / DLT
batch listener
deserializer
JsonDeserializer
observation / Micrometer
authentication / authorization
deprecation / removed
configuration default
~~~

### Bộ từ khóa ưu tiên cho Kafka broker/clients

~~~text
KIP
consumer group protocol
rebalance
transaction coordinator
producer idempotence
acks
min.insync.replicas
ISR
transactional.id
record format
metadata.version
KRaft
ZooKeeper migration
security / CVE
SASL / TLS
retention / compaction
quota
offset
client compatibility
~~~

**KIP** là Kafka Improvement Proposal, giúp hiểu thay đổi lớn nhưng thường không phải checklist nâng cấp hoàn chỉnh. Cần xem release note và upgrade guide xác định **khi nào tính năng thực sự có mặt và bắt đầu được dùng**.

## 9. Chuyển release notes thành risk assessment

Đánh giá mỗi thay đổi dựa trên **độ liên quan**, **mức độ ảnh hưởng** và **khả năng xảy ra trong workload**:

| Category | Thay đổi ví dụ | Rủi ro cần xem |
|---|---|---|
| API removal | Phương thức cũ bị loại | Compile/runtime failure |
| Default changed | Consumer/producer config khác | Behavior ngoài ý định |
| Retry/error handling | Thay đổi policy hoặc class | Poison message, DLT, replay |
| Transactions | Commit/abort/fencing behavior | Duplicate/lost output |
| Consumer group | Rebalance/assignment protocol | Stop-the-world, lag, offset |
| Serialization | Schema, type mapping, header | Deserialization failure |
| Security | CVE, TLS/SASL change | Exploit/không kết nối được |
| Monitoring | Metric/tag thay đổi | Alert im lặng hoặc nhiễu |
| Dependency | Kafka client/Java minimum version | Unsupported combination |
| Performance | Polling/batching/fetch behavior | Memory, latency, throughput |

Một ma trận ưu tiên đơn giản:

| Mức | Điều kiện điển hình | Hành động |
|---|---|---|
| **Critical** | Lỗ hổng đang bị khai thác, mất dữ liệu, sai transaction/offset trong luồng trọng yếu | Escalate, mitigation/upgrade khẩn theo quy trình |
| **High** | Thay đổi retry/DLT, idempotence, broker compatibility hoặc schema có nguy cơ gián đoạn | Action có owner, integration test và canary bắt buộc |
| **Medium** | Hành vi cần xác minh, thay đổi performance/tuning | Test trước rollout, đo metric và rollback plan |
| **Low** | Documentation, change không dùng tới | Ghi nhận not applicable hoặc follow-up |
| **Unknown** | Chưa đủ evidence để đánh giá | Không tự cho PASS; yêu cầu điều tra |

Mức độ do **impact của hệ thống**, không chỉ nhãn “bug fix” trong release notes. Một bug fix của Kafka producer ảnh hưởng transaction có thể là thay đổi High với ứng dụng thanh toán, nhưng không áp dụng cho một service chỉ đọc thông tin không transactional.

## 10. Mẫu release review record để audit

Nên lưu một record cho **mỗi change item có tác động**, không dồn nhiều mục vào một dòng tự do:

~~~yaml
reviewId: kafka-rel-2026-11-001
service: orders-event-worker
environment: production
reviewedAt: "2026-11-16"

component: spring-kafka
fromVersion: "<currently-resolved>"
toVersion: "<target-version>"
sourceType: release-notes
sourceUrl: "<official-release-url>"
changeId: "RELEASE-ITEM-EXAMPLE"

summary: "Ví dụ: thay đổi listener error handling"
affectedFeature: error-handler-and-dlt
isApplicable: true
risk: HIGH
reason: "Service dùng error handler tương ứng"

actions:
  code: "Kiểm tra API/config"
  config: "Xác minh retry attempts và DLT destination"
  tests: "Poison message -> retry -> DLT; no unexpected offset commit"
  rollout: "Canary trên consumer group phù hợp"

owner: kafka-platform-team
status: IN_REVIEW
evidence:
  compatibilityMatrix: PENDING
  integrationTests: PENDING
  canary: PENDING
~~~

Toàn bộ mục trong YAML là **ví dụ quy trình**, không phải nội dung của một release có thật. Khi tạo record thật, điền URL và version chính xác từ nguồn chính thức.

### Status nên phân biệt

~~~text
DISCOVERED
  |
  v
TRIAGED
  |
  +--> NOT_APPLICABLE (có rationale)
  |
  v
ACTION_REQUIRED
  |
  v
IMPLEMENTED
  |
  v
TESTED
  |
  v
CANARY_VERIFIED
  |
  v
ROLLED_OUT
  |
  v
CLOSED
~~~

Đừng coi **release note đã được đọc** là tương đương **change đã được triển khai và xác minh**. Một mục có thể đã triage nhưng vẫn chờ migration test.

## 11. Theo dõi những thay đổi liên quan Spring Kafka API

Khi Spring Kafka thay đổi release line, những điểm cần đối chiếu thường là:

- \`KafkaTemplate\`: cách gửi message, kiểu kết quả async, callback/error propagation.
- \`ProducerFactory\`, \`ConsumerFactory\`: khởi tạo clients, config maps, lifecycle.
- \`@KafkaListener\`: annotation attributes, batch mode, argument resolution.
- \`ConcurrentKafkaListenerContainerFactory\`: concurrency, ack mode, transaction wiring.
- \`CommonErrorHandler\`, \`DefaultErrorHandler\`: retry, seek, delivery-attempt headers, recovery.
- \`DeadLetterPublishingRecoverer\`: destination, headers, producer behavior.
- Retry topics, retry backoff và DLT processing.
- \`KafkaTransactionManager\`: cách cấu hình transactional listener và producer.
- Message converters/serializers và error handling deserializer.
- Micrometer Observation / metric tags.

Ví dụ **lịch sử một dạng migration cần chú ý**: ở các dòng Spring Kafka khác nhau, API bất đồng bộ của \`KafkaTemplate.send\` từng được thay đổi theo hướng \`CompletableFuture\`. Khi chuyển release line, code đang dùng callback/future type cũ có thể cần sửa. Không dựa vào ví dụ lịch sử này để khẳng định phiên bản mới nhất vừa thay đổi; hãy xác nhận chính xác migration guide của **fromVersion → toVersion**.

Ví dụ kiểm tra tại compile time:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String payload) {
        return kafkaTemplate.send("orders.events", orderId, payload);
    }
}
~~~

Ví dụ trên phù hợp với API có kiểu trả về tương ứng; code cần build với Spring Kafka target version. **Compile green** chứng minh surface API tương thích nhưng không chứng minh transaction commit, broker ACK hay consumer offset đúng.

## 12. Consumer groups và offsets: nhóm thay đổi cần ưu tiên cao

Khi release notes nhắc **group protocol, rebalance, cooperative assignment, static membership, max.poll.interval.ms hoặc offset management**, hãy nối ngay với luồng xử lý thực.

~~~text
Consumer 1 reads offset 100
        |
        v
Business processing
        |
        +-- DB write
        |
        v
Offset acknowledgement/commit
~~~

Nếu thay đổi làm consumer bị rebalance trong khi xử lý, item có thể được đọc lại. Nếu offset được commit trước side effect cần thiết, rủi ro là mất dữ liệu nghiệp vụ. Nếu side effect đã commit nhưng offset chưa commit, record có thể được xử lý trùng khi replay.

Các câu hỏi review:

1. Consumer đang dùng \`enable.auto.commit\` và \`AckMode\` nào?
2. Có sử dụng **manual acknowledgment** hoặc async processing không?
3. Thời gian xử lý tối đa có nhỏ hơn \`max.poll.interval.ms\` hợp lý không?
4. Có **idempotency theo message key/eventId** khi replay không?
5. Có DLT và chính sách poison message cụ thể không?
6. Offset commit có cùng Kafka transaction với output trong consume-process-produce không?
7. Consumer group có sử dụng protocol/assignor mới không?

Không thay \`group.id\` chỉ để “tránh lỗi nâng cấp”: group mới có thể đọc lại từ đầu hoặc bỏ qua dữ liệu tùy \`auto.offset.reset\` và retention.

## 13. Producer delivery và transaction: đọc release notes ở ranh giới đúng

Với producer thông thường, quan tâm:

- \`acks\`, \`enable.idempotence\`, \`retries\`.
- \`delivery.timeout.ms\`, \`request.timeout.ms\`, \`linger.ms\`.
- \`max.in.flight.requests.per.connection\`.
- Compression, batching, buffer pool và quota.
- Serializer và partitioning.

Với transactional producer, còn phải kiểm tra:

- \`transactional.id\` và cơ chế prefix per instance.
- \`KafkaTransactionManager\` và listener transaction wiring.
- Transaction timeout, fencing và coordinator behavior.
- \`read_committed\` visibility ở downstream.
- Consumer offsets có được commit trong cùng Kafka transaction không.

### Minh họa nguyên tắc test

~~~text
Transaction TX1:
  send(order.created, O100)
  send(order.audit, O100)
  COMMIT
    -> read_committed consumer sees both

Transaction TX2:
  send(order.created, O101)
  exception before commit
  ABORT
    -> read_committed consumer sees neither
~~~

Sau upgrade, nếu release note có thay đổi transaction hoặc error handling, cần chạy **integration test với broker thật** thay vì chỉ mock KafkaTemplate.

**Send ACK chưa phải transaction commit.** Một record có thể đã được broker nhận trong transaction rồi bị abort. Khi client mất kết nối đúng lúc commit, outcome có thể chưa rõ với ứng dụng; đừng tự kết luận exception đồng nghĩa transaction chắc chắn rollback.

## 14. Broker upgrade và compatibility không chỉ là Java dependency

Kafka broker và client được nâng cấp độc lập. Release notes của Kafka broker có thể đề cập:

- Quy trình rolling upgrade.
- Quản lý **metadata version/feature level** và thời điểm kích hoạt tính năng mới.
- KRaft, controller quorum hoặc thay đổi công cụ quản trị.
- Broker defaults, topic configs và protocol versions.
- Transaction coordinator và group coordinator.
- Partition reassignment, replica/ISR và leader election.
- Security protocol, SASL/TLS và authorization.
- Kafka CLI behavior, metric names hoặc log format.

Một số thay đổi broker có thể **khó rollback sau khi feature level hoặc metadata version được nâng**. Vì vậy, kế hoạch rollback phải dựa trên **upgrade guide của target Kafka release**, không mặc định quay lại container image cũ là đủ.

### Cách tổ chức review broker

~~~text
Current brokers + client inventory
             |
             v
Read every Kafka upgrade guide in the range
             |
             v
Check rolling-upgrade prerequisites
             |
             v
Upgrade non-production cluster
             |
             v
Validate produce/consume/transaction/rebalance
             |
             v
Canary/rolling production upgrade
             |
             v
Check ISR, under-replicated partitions, latency
             |
             v
Only then enable irreversible feature changes
~~~

Các bước này là mô hình quy trình. Thứ tự thật sự phải theo **tài liệu của phiên bản broker đang áp dụng**, đặc biệt khi có thay đổi quorum/controller hoặc quy trình chuyển đổi thế hệ Kafka.

### Bằng chứng tương thích client-broker

Một smoke test nên có:

| Test | Điều cần xác minh |
|---|---|
| Producer write với acks đã phê duyệt | Broker ACK, record visible |
| Consumer join group | Assignment hoạt động |
| Restart consumer | Không mất record hoặc commit offset sai |
| Rebalance dưới tải | Replay/lag trong ngưỡng |
| Transaction commit/abort | read_committed visibility đúng |
| AdminClient operations cần thiết | ACL/config tooling vẫn hoạt động |
| SASL/TLS | Authentication và certificate chain đúng |
| Serializer/schema | Consumer mới đọc được dữ liệu cũ |
| Metrics/alerts | Dashboard không mất tín hiệu |

Không diễn giải “message A đến topic thành công” thành bằng chứng toàn bộ compatibility matrix đã đạt.

## 15. Các thay đổi về serialization và schema compatibility

Đôi khi release notes của Spring Kafka hoặc serializer thay đổi:

- JSON type headers và trusted packages.
- Default type mapping hoặc message converter.
- ErrorHandlingDeserializer behavior.
- Schema Registry client versions.
- Avro/Protobuf/JSON Schema serialization.
- Header names và serialization format.

Một thay đổi schema có thể khiến producer mới ghi dữ liệu mà consumer cũ không đọc được trong rolling deployment.

### Ví dụ schema evolution

Version cũ:

~~~json
{
  "eventId": "E101",
  "orderId": "O101",
  "status": "CREATED"
}
~~~

Version mới:

~~~json
{
  "eventId": "E101",
  "orderId": "O101",
  "status": "CREATED",
  "sourceSystem": "checkout"
}
~~~

Thêm field có thể tương thích nếu consumer cũ bỏ qua field lạ và schema/serializer policy cho phép, nhưng **không mặc định đúng** với mọi deserializer. Cần kiểm tra registry compatibility mode và code của consumer cũ.

Với rolling deployment, test nên bao gồm:

- Producer cũ → consumer mới.
- Producer mới → consumer cũ.
- Consumer mới đọc record tồn tại từ trước trong topic.
- Record lỗi schema vào DLT đúng, không loop vô hạn.
- Không đổi message key/partitioning bất ngờ.

Khi thay **key serializer hoặc partitioner**, cùng business key có thể đi sang partition khác, làm thay đổi kỳ vọng ordering. Release review phải quan tâm cả **key**, không chỉ value payload.

## 16. Security advisories và ưu tiên cập nhật

Không phải mọi bản phát hành cần deploy ngay, nhưng **security advisory** đòi hỏi quy trình riêng.

Một advisory có thể cho biết:

- Package và phiên bản bị ảnh hưởng.
- Loại lỗ hổng, CVE/GHSA nếu có.
- Điều kiện khai thác và attack surface.
- Bản vá hoặc workaround.
- Hạn chế compatibility khi nâng cấp.

### Quy trình xử lý

1. Xác minh advisory từ nhà phát hành hoặc nguồn đáng tin cậy.
2. Kiểm tra **resolved runtime dependencies**, không chỉ build declaration.
3. Đối chiếu điều kiện khai thác với cấu hình đang chạy.
4. Phân loại severity theo asset, dữ liệu, reachability và exploitability.
5. Chọn bản vá, mitigation tạm thời hoặc cô lập tính năng.
6. Kiểm tra compatibility trước khi rollout; không bỏ qua reliability tests.
7. Thực hiện canary/expedited rollout theo mức khẩn.
8. Xác minh không còn phiên bản dễ bị ảnh hưởng trên **tất cả instances**.
9. Ghi evidence và đóng advisory ticket.

**Không chỉ xét số CVSS.** Một lỗ hổng ít nghiêm trọng trên lý thuyết có thể ảnh hưởng nặng nếu dịch vụ exposed; ngược lại một CVE ở module không load có thể cần đánh giá reachability chi tiết. Không tự tuyên bố “không ảnh hưởng” nếu chưa có bằng chứng.

SBOM và dependency inventory giúp trả lời **dịch vụ nào dùng artifact/version bị ảnh hưởng**. Cần giữ lịch sử SBOM theo mỗi image release, không chỉ của HEAD trên main branch.

## 17. Lưu release notes thành backlog có owner

Một cách quản lý là tạo **upgrade review issue** cho mỗi dải version:

~~~text
Issue: Review Spring Kafka <from> -> <to>

Owner: Kafka platform + application owner
Scope: orders-event-worker, production
Related: Kafka clients, Boot BOM, broker, JDK

Release docs:
  [Official Spring Kafka release/migration links]

Items:
  [ ] Breaking API changes reviewed
  [ ] Client/broker/JDK compatibility confirmed
  [ ] Default/config changes reviewed
  [ ] Retry/error handler/DLT reviewed
  [ ] Transaction and offset behavior tested
  [ ] Schema backward/forward compatibility tested
  [ ] Security advisories reviewed
  [ ] Canary and rollback plan approved

Decision: APPROVE / DEFER / BLOCK
Rationale:
Evidence links:
~~~

Không để comment “looks good” là bằng chứng duy nhất. Quyết định tốt cần có:

- Đường dẫn tới release notes **của dải phiên bản**.
- Những mục có tác động và owner xử lý.
- Dữ liệu test và môi trường đã dùng.
- Các ngoại lệ được chấp thuận.
- Kế hoạch rollback.
- Người chịu trách nhiệm theo dõi sau deploy.

Nếu item không áp dụng, ghi rõ lý do: ví dụ service **không dùng Kafka Streams**, nhưng release chỉ thay đổi một operator của Kafka Streams. Điều này giảm review lặp đi lặp lại ở các lần sau.

## 18. Tự động phát hiện bản release mới, nhưng không tự động kết luận an toàn

Automation có thể phát hiện **có release mới**, còn đánh giá compatibility vẫn cần logic và review thích hợp.

Một quy trình:

~~~text
Release feed / repository event
                 |
                 v
Fetch version + published date + official URL
                 |
                 v
Compare with inventory/BOM
                 |
                 v
Create review issue/PR
                 |
                 v
Owner triages release notes
                 |
                 v
CI compatibility tests
                 |
                 v
Approval + staged rollout
~~~

Ví dụ một request đọc metadata release từ GitHub API:

~~~bash
# Chỉ lấy metadata release; ví dụ, cần kiểm soát rate limit,
# authentication và network policy ở pipeline thật.
curl --fail --silent --show-error \
  https://api.github.com/repos/spring-projects/spring-kafka/releases
~~~

API trả danh sách release entries; công cụ phải lọc theo policy **stable/prerelease**, đọc publishedAt/tag và tránh tạo issue trùng. Không mặc định entry đầu tiên là phiên bản cần triển khai, hoặc tag gần nhất chắc chắn tương thích với Spring Boot BOM của ứng dụng.

Nếu dùng Renovate/Dependabot:

- Giới hạn major/minor/patch lanes theo policy.
- Nhóm dependency có liên quan khi cần kiểm tra cùng nhau.
- Tránh auto-merge release có breaking/behavior change không có test tương ứng.
- Nhắc reviewer xem **migration notes** và resolved graph.
- Chạy integration tests với broker/test runtime phù hợp.

### Tần suất theo dõi

Ví dụ cadence:

| Khi nào | Việc cần làm |
|---|---|
| Hằng ngày hoặc qua alert | Theo dõi security advisories ảnh hưởng dependency quan trọng |
| Hằng tuần | Kiểm tra release entries mới và gắn owner |
| Hằng tháng | Review nâng cấp nhỏ, dependency drift, backlog |
| Trước mỗi deployment | Kiểm tra release range trong build và changelog nội bộ |
| Trước broker/JDK major upgrade | Review compatibility matrix, migration guide, rollback constraints |
| Sau sự cố hoặc outage | Kiểm tra bản sửa liên quan trong các release mới |

Cadence là ví dụ vận hành. Mức độ thường xuyên cần phù hợp SLA, chính sách vá lỗi và khả năng đội ngũ.

## 19. So sánh configuration defaults trong upgrade

Thay đổi default là một nguồn lỗi khó thấy vì build file không đổi chỗ cấu hình application. Những thuộc tính cần chốt tường minh khi reliability contract yêu cầu:

| Layer | Thuộc tính ví dụ | Rủi ro |
|---|---|---|
| Producer | acks, enable.idempotence | Delivery/dedup không như thiết kế |
| Producer | retries, delivery.timeout.ms | Timeout hoặc retry storm |
| Producer | transaction.timeout.ms | Abort transaction dài |
| Consumer | enable.auto.commit | Offset commit sai ranh giới |
| Consumer | isolation.level | Đọc dữ liệu từ transaction aborted |
| Consumer | max.poll.interval.ms | Rebalance khi xử lý lâu |
| Consumer | auto.offset.reset | Tạo group mới đọc sai vị trí |
| Listener | AckMode, concurrency | Offset/throughput khác |
| Error handling | backoff, maxFailures, DLT | Poison message loop hoặc skip sai |
| Topic/broker | min.insync.replicas, replication | Durability suy giảm |

Không coi danh sách trên là **default values** của một Kafka version cụ thể. Nó là checklist những key cần so.

Một quy trình cấu hình:

~~~text
Approved config baseline
          |
          v
Old resolved runtime/factory config
          |
          v
New resolved runtime/factory config
          |
          v
Diff typed values and defaults
          |
          v
Verify behavior with broker-based tests
~~~

Phải phân biệt:

1. Giá trị **explicit** trong app.
2. Giá trị **Spring Boot binding/default**.
3. Giá trị **Kafka client default**.
4. Giá trị **effective runtime** sau customizers.
5. Giá trị **broker/topic** thực tế.

Nếu cả hai version đều không khai báo \`isolation.level\`, có thể cần xét default client của từng version. Nếu ứng dụng phụ thuộc bắt buộc vào \`read_committed\`, tốt nhất cấu hình tường minh theo contract.

## 20. Xây test suite bám sát những thay đổi đã review

Mục tiêu không phải chạy nhiều test cho có, mà là **mỗi mục release notes quan trọng có test chống hồi quy tương ứng**.

Một ma trận gợi ý:

| Nhóm release change | Integration test cần chạy |
|---|---|
| Producer client | Send ACK, retry, idempotency, ordering theo key |
| Consumer client | Poll, offset commit, rebalance và restart |
| Spring Kafka listener | AckMode, error propagation, pause/resume |
| Retry / error handler | Transient fail, retry limit, poison message → DLT |
| Transactions | Commit/abort và read_committed visibility |
| Consume-process-produce | Output cùng offset commit trong Kafka transaction |
| Deserialization | Payload cũ/mới, invalid schema → policy đúng |
| Security | SASL/TLS, ACL và authentication failures |
| Broker upgrade | Rolling upgrade, mixed-version phase, under-replicated ISR |
| Observability | Metric/tag và alert vẫn phát |
| Deployment | Canary, pod replacement, clean shutdown |
| Backpressure | Throughput, lag, max.poll.interval, bounded memory |

### Test với broker thực

**EmbeddedKafka** phù hợp với integration tests nhanh. **Testcontainers** thích hợp khi cần pin broker image/version, cấu hình gần production hoặc mô phỏng lifecycle/network issue.

Test Kafka transactions phải dùng \`read_committed\` consumer thật; test chỉ verify \`KafkaTemplate.send()\` bằng Mockito không chứng minh commit.

Ví dụ đoạn test cấu hình consumer để xác minh transaction visibility:

~~~java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;

Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG,
        "upgrade-compatibility-test-group");
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
        "earliest");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
        false);
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG,
        "read_committed");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
~~~

Đây là cấu hình consumer minh họa, không phải class test hoàn chỉnh. Trong test thực nên tạo group ID riêng cho mỗi case, chờ partition assignment với timeout hữu hạn và xác nhận cả **commit visible** lẫn **abort invisible**.

### Tình huống failure injection

Test độ tin cậy đặc biệt quan trọng khi release note nói tới retry/transactions:

~~~text
1. Consumer nhận event
2. Handler ghi DB hoặc phát Kafka output
3. Tiêm lỗi trước offset commit
4. Restart/rebalance consumer
5. Kiểm tra replay và idempotency
6. Đối soát expected vs actual output
~~~

Nếu đã ghi DB nhưng chưa commit Kafka offset, message có thể được đọc lại. Kafka transaction không tự rollback database. Với luồng dual-write, nên kiểm tra **transactional outbox** hoặc cơ chế idempotent/reconciliation đang có.

Không coi việc test pass một message và một broker là bằng chứng đầy đủ cho failover nhiều broker hoặc production traffic.

## 21. Gắn release item với test tự động

Một cách tổ chức là thêm metadata vào ticket hoặc repo:

~~~yaml
changeReview:
  id: SK-RELEASE-REVIEW-017
  component: spring-kafka
  fromVersion: "<from>"
  toVersion: "<to>"
  affectedArea: retry-and-dlt

tests:
  - id: retry-transient-succeeds
    expected: "exactly one business output"
  - id: retry-exhausted-to-dlt
    expected: "DLT record and offset according to policy"
  - id: poison-message-no-infinite-loop
    expected: "bounded retry and forward progress"

deploymentGate:
  compatibilityConfirmed: false
  integrationTestsPassed: false
  rollbackPlanApproved: false
~~~

Đây là record minh họa, không phải cấu hình mà Gradle tự hiểu. CI/CD có thể được thiết kế để đọc file nếu dự án muốn tự động gate. Phần quan trọng là **link từ một release change đến một test và bằng chứng**, không chỉ bảng checklist chung.

Ví dụ: nếu release notes đề cập consumer rebalance logic, có thể thêm test cố ý stop một consumer giữa xử lý và xác minh group giữ đúng thông tin offset, không duplicate side effect ngoài idempotency contract.

## 22. Kế hoạch nâng cấp theo tầng

Tránh nâng đồng thời mọi thành phần mà không có mục tiêu rõ. Một thứ tự phù hợp tùy compatibility requirements:

~~~text
Review release notes + compatibility matrix
                 |
                 v
Resolve dependency graph and build
                 |
                 v
Unit tests + source API migration
                 |
                 v
Kafka integration tests in CI
                 |
                 v
Staging with representative broker/config
                 |
                 v
Load/failure/restart tests
                 |
                 v
Production canary
                 |
                 v
Progressive rollout
                 |
                 v
Post-release observation and closure
~~~

**Nâng broker trước client hay client trước broker** phụ thuộc Kafka release target và chính sách supported upgrade path. Không áp một thứ tự duy nhất cho mọi thế hệ Kafka; phải xem upgrade guide.

### Trong rolling deployment

Có thể tồn tại tạm thời:

~~~text
Pod A: new Spring Kafka/client versions
Pod B: old Spring Kafka/client versions
Pod C: old Spring Kafka/client versions
~~~

Vì vậy, cần kiểm tra:

- Các client cũ/mới cùng join group được không.
- Có thay đổi consumer group protocol/assignor không.
- Payload producer mới tương thích consumer cũ không.
- Transactional producer prefix/identity có gây fencing không.
- DLT/error handling có khác giữa pods không.
- Metrics và log correlation có thể phân biệt release nào tạo lỗi.

Không đổi consumer group ID tùy tiện khi canary để né rebalance; nếu cần group mới cho shadow testing, phải có chiến lược tránh duplicate side effect.

## 23. Quan sát canary: cần metric nào?

Sau khi lên bản mới, đừng chỉ nhìn “pod Ready”. Đo cả Kafka và nghiệp vụ:

| Chỉ số | Dấu hiệu bất thường |
|---|---|
| Consumer lag theo group/partition | Lag tăng hoặc không giảm |
| Rebalance frequency/duration | Group churn, partition assignment không ổn định |
| Commit failure rate | Offset commit lỗi tăng |
| Processing error rate | Deserialization/handler exceptions tăng |
| Retry attempts/exhausted | Dependency hoặc behavior thay đổi |
| DLT publish rate | Record bị loại bất thường |
| Producer record error/retry rate | Gửi thất bại hoặc latency tăng |
| Produce latency / request latency | Broker/client throughput suy giảm |
| Transaction commit/abort rate | Giao dịch bất thường |
| Producer fencing errors | Transactional identity conflict |
| JVM heap/GC/threads | Memory regression |
| Broker ISR/under-replication | Reliability backend suy giảm |
| Business reconciliation | Thiếu, thừa hoặc trùng event |

Ví dụ log có cấu trúc:

~~~text
event=kafka.upgrade.canary.observation
service=orders-event-worker
release=orders-worker-2026.11
versionProfile=target
cluster=prod-kafka-a
consumerGroup=orders-worker-v1
finding=REBALANCE_RATE_INCREASED
severity=HIGH
~~~

Tên event và dữ liệu là ví dụ. Không log raw message payload, auth headers, token hoặc customerId chỉ để chẩn đoán compatibility.

### Đặt ngưỡng so sánh

Đừng đánh giá dựa vào một snapshot đơn lẻ. Dùng **baseline trước rollout**, so canary với instance cũ cùng thời điểm nếu có thể, tính tới input traffic, ngày giờ và partition assignment.

Ví dụ chính sách: rollout dừng nếu error rate tăng vượt ngưỡng đã thống nhất, lag tăng liên tục dù input volume ổn định, hoặc DLT unexpectedly có record từ schema mới. Ngưỡng số phải do đội vận hành xác định theo SLA thực tế; không lấy một con số ngẫu nhiên làm chuẩn chung.

## 24. Rollback và những giới hạn phải ghi trước khi nâng cấp

**Rollback artifact** không phải lúc nào cũng tương đương rollback trạng thái dữ liệu.

Một ứng dụng Spring Kafka mới có thể đã:

- Ghi event theo schema mà consumer cũ không đọc được.
- Commit offsets vượt vị trí consumer cũ có thể xử lý an toàn.
- Thay đổi topic partition count hoặc cleanup policy.
- Thực thi side effects ngoài Kafka.
- Dùng transactional IDs/producer epochs ảnh hưởng producer cũ.
- Áp dụng migration database hoặc thay đổi cấu hình broker không dễ đảo ngược.

### Kế hoạch rollback tối thiểu

1. Giữ image digest và dependency lock của bản hoạt động trước.
2. Kiểm tra schema backward/forward compatibility trước rollout.
3. Phân biệt **rollback application** và **rollback Kafka broker/feature level**.
4. Ghi lại config revisions, topic changes, ACL changes, group offsets cần quan sát.
5. Xác định điểm dừng producer/consumer để tránh hai owner cùng xử lý.
6. Chuẩn bị idempotent replay hoặc reconciliation khi offset/output không còn tương ứng.
7. Xác nhận các thay đổi **không thể đảo ngược** trước khi phê duyệt.
8. Kiểm tra sau rollback bằng consumer/broker test và business reconciliation.

Không reset consumer offsets chỉ vì rollback ứng dụng. Reset offset có thể tạo reprocessing lớn và duplicate, hoặc bỏ qua message; cần backup và quyết định theo runbook đã phê duyệt.

### Ví dụ rủi ro schema khi rollback

~~~text
New producer emits field/type not supported by old consumer
      |
      v
Application rollback to old consumer
      |
      v
Old consumer cannot deserialize messages already in topic
~~~

Giải pháp không đơn giản là quay lại jar cũ. Cần contract schema có thể đọc song song trong rolling window, hoặc migration/consumer handling tương ứng.

## 25. Release notes trong xử lý incident

Khi một phiên bản mới gây lỗi production, release notes là **một nguồn giả thuyết**, không phải bằng chứng kết luận.

Ví dụ incident:

~~~text
After deployment:
  consumer lag increases
  rebalance count rises
  DLT rate becomes non-zero
~~~

Quy trình:

1. Xác định thời điểm đầu tiên xuất hiện triệu chứng.
2. Đối chiếu deployment revision, JVM, Spring Kafka, kafka-clients và broker versions.
3. Kiểm tra config drift có xảy ra đồng thời không.
4. Tìm trong release notes những thay đổi liên quan consumer group, error handler hoặc deserialization.
5. So log/metrics giữa canary và phiên bản cũ.
6. Cố gắng tái hiện trong môi trường test với dữ liệu synthetic.
7. Nếu mức ảnh hưởng cao, rollback/mitigate theo runbook; không chờ nghiên cứu xong toàn bộ.
8. Sau khi ổn định, liên kết root cause với release change, bổ sung regression test.

Không kết luận “Kafka version mới gây lỗi” chỉ vì hai sự kiện cùng thời điểm; broker load, ConfigMap change hoặc upstream schema release cũng có thể là nguyên nhân.

### Hotfix và CVE

Nếu phát hiện bản đang chạy có lỗ hổng cần vá nhanh, có thể có **expedited change path**: rút ngắn quy trình phê duyệt nhưng vẫn giữ những test tối quan trọng như authentication, produce/consume, transactions hoặc offsets đối với workload tương ứng. Không bỏ toàn bộ compatibility test chỉ vì nhãn security update.

## 26. Phân công trách nhiệm theo vai trò

Một quy trình theo dõi thường xuyên cần có owner rõ ràng:

| Vai trò | Trách nhiệm |
|---|---|
| **Application team** | Inventory, code migration, business regression tests |
| **Kafka platform team** | Broker upgrade, topic/ACL/quotas, cluster health |
| **Security team** | Advisory triage, severity, deadline vá lỗi |
| **SRE/Operations** | Monitoring, canary, rollback, incident response |
| **QA/Testing** | Integration/failure scenarios, test evidence |
| **Change owner** | Gộp evidence và phê duyệt/đề xuất rollout |

Trong một nhóm nhỏ, một người có thể đảm nhiệm nhiều vai trò. Tuy nhiên, mỗi finding vẫn cần **một owner chính**, deadline và trạng thái.

### Gợi ý lịch họp review release

Cuộc review ngắn có thể trả lời:

- Tuần này có release hoặc advisory nào mới liên quan inventory?
- Có mục Critical/High chưa được triage?
- Bản target có nằm trong support/compatibility matrix không?
- Test nào cần thêm trước khi merge?
- Broker/client rollout nào đang được lên lịch?
- Có drift hoặc canary regression ở lần nâng cấp gần nhất?

Giữ các quyết định trong issue/knowledge base để người vận hành ca sau đọc được mà không phải hỏi lại toàn bộ bối cảnh.

## 27. Ví dụ phân tích một release note giả định từ đầu đến cuối

**Tình huống giả định**, không phải một release note thật:

~~~text
Component: Spring Kafka
Target: next approved release
Change: listener recovery behavior now uses a different default.
~~~

Ứng dụng hiện tại:

~~~text
Input topic: payments.requests
Consumer group: payment-verifier
Retries: bounded
DLT: payments.requests.dlt
Business rule: every valid request eventually reaches processed or DLT
~~~

### Bước A — Xác định tính áp dụng

Code đang sử dụng một error handler bị ảnh hưởng. Do đó **applicable=true**. Không chỉ đọc một mục release notes; mở migration guide và source/issue gắn với change để biết khác biệt thực tế.

### Bước B — Viết risk statement

Nếu default retry chuyển từ hữu hạn sang lâu hơn dự kiến, một poison message có thể giữ partition quá lâu. Nếu recovery chuyển sang cách acknowledge khác, offset có thể được commit khác với contract. Đây là **risk cần kiểm thử**, không phải kết luận chưa có bằng chứng.

### Bước C — Quyết định explicit config

Đặt retry/backoff/recoverer theo policy thay vì phụ thuộc default. Ví dụ **mang tính minh họa**:

~~~java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

DefaultErrorHandler handler = new DefaultErrorHandler(
        deadLetterPublishingRecoverer,
        new FixedBackOff(1_000L, 2L));
~~~

Trong ví dụ, \`deadLetterPublishingRecoverer\` là bean được cấu hình với KafkaTemplate và topic policy phù hợp. \`FixedBackOff(1000, 2)\` biểu diễn khoảng nghỉ một giây và số lần retry theo policy của Spring Kafka/BackOff đang dùng; cần xác minh semantics chính xác của target version và test cả số lần delivery/recovery, không suy ra bừa từ constructor.

### Bước D — Viết test

Test broker-based:

1. Event hợp lệ → xử lý thành công, offset tiến.
2. Transient exception → retry rồi thành công, không DLT.
3. Permanent exception → retry hết, DLT có đúng event một lần theo contract.
4. Consumer restart đúng lúc error → không mất event.
5. DLT publish thất bại → recovery policy không âm thầm commit sai offset.

### Bước E — Canary và closure

Quan sát retry attempts, DLT rate, lag và handler exceptions. Chỉ đóng release review khi canary đạt và evidence được lưu. Nếu test fail, giữ version cũ hoặc áp dụng workaround đã được phê duyệt.

Ví dụ này cho thấy **một câu release note ngắn có thể trở thành nhiều hành động cụ thể**.

## 28. Những sai lầm thường gặp

**Chỉ xem release notes của bản đích.** Có thể bỏ qua breaking change nằm ở phiên bản trung gian.

**Không biết runtime resolved versions.** BOM hoặc transitive dependency có thể khác build declaration.

**Chỉ theo dõi Spring Kafka, bỏ qua kafka-clients và broker.** Reliability nằm ở cả framework và protocol/broker.

**Coi patch release luôn không rủi ro.** Bug fix transaction, rebalance hoặc retry có thể thay đổi behavior.

**Dựa vào một bài blog thay vì nguồn chính thức.** Có thể thiếu thông tin migration hoặc known issues.

**Nhầm compile success với behavioral compatibility.** Transactions, offsets và DLT cần test có broker thật.

**Đọc release notes rồi không tạo action/owner.** Rủi ro chưa được xử lý dù checklist ghi đã đọc.

**Auto-merge dependency update vào production.** Có thể trộn version không hỗ trợ hoặc đổi default.

**Nâng broker và client tùy tiện cùng lúc.** Khi gặp regression khó xác định nguyên nhân; thứ tự phải theo guide.

**Bỏ qua schema khi rolling deployment.** Producer mới có thể tạo record consumer cũ không đọc được.

**Không theo dõi JDK và container image.** Library có thể yêu cầu runtime/platform khác.

**Không xem deprecation cho đến khi API bị xóa.** Khi ấy việc migration gấp dễ tạo lỗi.

**Không kiểm tra hỗ trợ rollback của broker feature level.** Có thay đổi không thể quay lại chỉ bằng thay image.

**Chỉ xem technical metrics.** Cần business reconciliation để phát hiện missing/duplicate event.

**Không phân biệt Kafka exactly-once với DB + Kafka exactly-once.** Giao dịch giữa hai resource không tự atomic.

**Không lưu decision log và evidence.** Mỗi lần upgrade đội lại kiểm tra từ đầu.

**Bỏ qua security advisories khi không có bản major mới.** Lỗ hổng có thể được vá ở patch release.

**Gán nhầm ngày xuất bản với ngày triển khai.** Một release cũ có thể mới được đưa vào hệ thống hôm nay; inventory và release note review phải theo version range thực.

**Không có owner khi cảnh báo xuất hiện.** Release tracking trở thành feed thông tin không được xử lý.

## 29. Quy trình thực hành chuẩn cho mỗi đợt nâng cấp

Một checklist thực tế:

1. **Freeze inventory**: lấy runtime resolved dependencies, Kafka broker/JDK versions, image digest và config baseline.
2. **Chọn target**: dựa trên support policy, security, bug fix hoặc nhu cầu tính năng; không chọn chỉ vì số version lớn hơn.
3. **Thu thập toàn bộ release notes trong khoảng phiên bản**, cùng migration guide và advisories.
4. **Lập compatibility matrix** cho Spring Boot, Spring Kafka, kafka-clients, Kafka broker, JDK và serializer/schema.
5. **Triage release items** theo applicability/risk; tạo action, owner và rationale.
6. **Review config defaults và wiring**: factories, consumer groups, error handlers, transactions, retry/DLT.
7. **Áp dụng code/config migration** trong PR có thể review, giữ dependency graph nhất quán.
8. **Chạy unit + integration + failure tests** cho những reliability contracts bị tác động.
9. **Test staging với broker và dữ liệu đại diện**, đo lag, retries, commit, memory và reconciliation.
10. **Chuẩn bị canary và rollback**, ghi rõ các thay đổi dữ liệu/config/broker không dễ đảo ngược.
11. **Rollout từng bước**, theo dõi metrics và so với baseline trước nâng cấp.
12. **Close release review** khi evidence đủ; cập nhật inventory, SBOM, config policy và runbook.

### Tiêu chí hoàn thành

| Hạng mục | Bằng chứng |
|---|---|
| Current/target versions | Dependency graph và cluster inventory |
| Release range | Official URLs cho các version trung gian |
| Compatibility | Matrix có nguồn evidence |
| Security | Advisory triage |
| Code/API | Build/tests cho target release |
| Behavior | Transaction, offset, retry, DLT regression tests |
| Schema | Old/new producer-consumer compatibility |
| Deployment | Canary metrics và rollout logs |
| Rollback | Runbook được review |
| Ownership | Action items đã hoàn tất hoặc ngoại lệ có hạn |

## 30. Tổng kết

**Theo dõi release notes** trong Spring Kafka Reliability Operations là một quy trình kỹ thuật lặp lại, không phải một hoạt động đọc tin một lần. Release notes cho biết **cái gì đã thay đổi**; inventory và compatibility matrix cho biết **thành phần nào đang chịu ảnh hưởng**; tests và canary cho biết **hợp đồng reliability có còn được giữ nguyên không**.

Một quy trình tốt bắt đầu từ version thực sự được resolve, dùng nguồn release chính thức, không bỏ qua migration guide hay advisories, và chuyển mỗi thay đổi quan trọng thành việc có owner, test, evidence và rollback plan. Đặc biệt cần ưu tiên **offset commits, retry/DLT, consumer rebalance, producer idempotence, Kafka transactions, broker compatibility và message schema** vì đây là nơi một upgrade vẫn biên dịch thành công nhưng âm thầm làm dữ liệu bị xử lý sai.

Khi release tracking được gắn vào CI/CD, security triage, compatibility testing và quan sát production, đội ngũ có thể nâng cấp Spring Kafka và Kafka một cách có kiểm soát: **tiếp nhận sửa lỗi và tính năng mới mà không đánh đổi tính toàn vẹn dữ liệu hoặc khả năng phục hồi của hệ thống**.
