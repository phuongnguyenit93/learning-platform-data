# Tổ chức kiểm thử Kafka trong CI và dọn tài nguyên ổn định

Kiểm thử Kafka trong CI thường thất bại vì hai nhóm nguyên nhân: môi trường không được cô lập và tài nguyên không được thu hồi đúng vòng đời. Hai job cùng tạo topic `orders-test`, hai consumer dùng chung `group.id`, hoặc một test để lại consumer đang chạy có thể làm test khác đọc nhầm record, không nhận partition hay không xóa được topic.

Một pipeline ổn định cần quản lý Kafka như tài nguyên có chủ sở hữu và thời hạn sống rõ ràng. Ưu tiên broker ephemeral theo job, đặt tên topic/group/transaction theo run và shard, chờ readiness bằng timeout hữu hạn, đóng client trước cleanup và chỉ xóa đúng tài nguyên do job đó tạo.

## 1. Mục tiêu của kiểm thử Kafka trong CI

CI cần trả lời các câu hỏi khác nhau ở từng tầng:

| Tầng | Mục tiêu | Môi trường phù hợp |
|---|---|---|
| Compile/unit | Kiểm tra business logic, mapping, validation và nhánh lỗi | Không cần broker |
| Kafka adapter integration | Kiểm tra producer/consumer, serializer, commit và listener | Một broker ephemeral |
| Contract/integration | Kiểm tra schema, topic config, retry/DLT và consumer group | Broker ephemeral cùng dependency cần thiết |
| Cluster/system | Kiểm tra replication, ISR, failover, KRaft quorum, ACL và quota | Cluster nhiều broker/controller |
| Performance | Đo throughput, latency và resource dưới tải | Môi trường benchmark riêng |

Không chạy toàn bộ test với cluster nhiều broker cho mỗi commit nếu phần lớn test chỉ cần kiểm tra logic adapter. Ngược lại, không dùng một broker đơn lẻ để kết luận RF, ISR hoặc leader failover hoạt động đúng.

Pipeline tốt giữ unit test nhanh, chạy integration test có broker ở stage riêng và dành cluster/system test cho lịch chạy hoặc thay đổi có rủi ro tương ứng.

## 2. Chọn mô hình môi trường Kafka cho CI

Có ba mô hình thường gặp:

| Mô hình | Cách hoạt động | Ưu điểm | Giới hạn |
|---|---|---|---|
| Broker ephemeral theo job | Mỗi CI job khởi tạo container Kafka riêng | Cô lập tốt, cleanup theo lifecycle container | Tốn thời gian và tài nguyên khởi động |
| Broker ephemeral theo test suite | Một container phục vụ một suite/class | Khởi động ít lần hơn, vẫn có vòng đời ngắn | Cần namespace riêng giữa test case và quản lý state |
| Broker dùng chung cho nhiều job | Nhiều job kết nối một cluster CI | Tiết kiệm tài nguyên cluster | Cần isolation bằng tên, ACL, quota và cleanup chính xác |

### Ưu tiên broker ephemeral

Với đa số integration test, một Kafka container riêng cho job hoặc suite là lựa chọn dễ kiểm soát nhất. Khi test kết thúc, container và data directory của nó bị hủy; topic, group offset và transaction state không tồn tại sang job sau.

Broker ephemeral một node phù hợp kiểm tra:

- Producer/consumer API và serialization.
- Consumer group cơ bản.
- Commit offset và retry topic ở mức integration.
- Transaction API với broker thực, nếu image/config hỗ trợ.
- Topic creation và topic-level config.

Nó không đủ để xác minh replication factor lớn hơn một, ISR shrink/expand giữa nhiều broker, leader failover, rack awareness hoặc controller quorum failure. Những kiểm thử đó cần cluster nhiều broker/controller được dựng riêng cho system test.

## 3. Tổ chức pipeline theo stage

~~~mermaid
flowchart TD
    A["Checkout + resolve dependencies"] --> B["Compile + static checks"]
    B --> C["Unit tests - no broker"]
    C --> D["Start ephemeral Kafka"]
    D --> E["Kafka adapter integration tests"]
    E --> F["Collect logs + test reports"]
    F --> G["Close clients + cleanup"]
    G --> H["Destroy container/network/volume"]
    H --> I["Publish CI result"]
~~~

Các nguyên tắc tổ chức:

1. Chạy compile và unit test trước để lỗi nhanh không phải chờ broker.
2. Chỉ khởi tạo Kafka khi stage integration bắt đầu.
3. Dùng image Kafka được pin version cụ thể, không dùng tag `latest`.
4. Kiểm tra broker readiness trước khi chạy test.
5. Tạo namespace riêng cho từng run/shard/test case.
6. Thu thập log trước khi container bị hủy.
7. Đóng producer, consumer, AdminClient và executor trước cleanup.
8. Dọn container/network/volume ngay cả khi test fail hoặc job bị cancel.

Không để stage integration phụ thuộc vào một broker CI đang chạy lâu ngày mà không biết trạng thái, version hoặc dữ liệu còn sót.

## 4. Khởi chạy Kafka bằng Testcontainers

Testcontainers có thể khởi chạy Kafka container từ JUnit. API/package và image được hỗ trợ thay đổi theo phiên bản Testcontainers; dùng module và ví dụ tương ứng với version đã pin trong build. Ví dụ sau minh họa lifecycle với Kafka module hiện đại:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class OrderKafkaIntegrationTest {
    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:PINNED_VERSION")
        );

    @Test
    void publishesAndConsumesOrder() {
        String bootstrapServers = kafka.getBootstrapServers();
        // Tạo producer/consumer bằng bootstrapServers của container.
        // Chạy assertion end-to-end rồi đóng client.
    }
}
~~~

`@Container static` thường tạo một container dùng chung cho các test trong class. Nếu cần isolation giữa class, có thể dùng container instance theo class hoặc suite fixture có namespace riêng. Không chia sẻ một broker static toàn bộ test run nếu test không được thiết kế để cô lập topic/group.

Một số phiên bản Testcontainers dùng package/class hoặc module artifact khác. Hãy giữ Testcontainers và Kafka module cùng version, pin image Kafka và xác nhận image tương thích với class KafkaContainer của version đó.

### Cấu hình dependency

Khai báo dependency kiểm thử theo version thống nhất:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:<junit-version>")
    testImplementation("org.testcontainers:junit-jupiter:<testcontainers-version>")
    testImplementation("org.testcontainers:kafka:<testcontainers-version>")
}
~~~

Artifact/module name của Kafka integration có thể khác giữa các major version Testcontainers. Dùng BOM hoặc version catalog để tránh module Kafka và JUnit extension bị lệch version.

### Không bật container reuse trong CI dùng chung

Container reuse hữu ích khi developer chạy test lặp lại ở máy cá nhân, nhưng làm state tồn tại giữa các lần chạy. Với CI, ưu tiên container mới theo job và tắt reuse để tránh topic, group offset hoặc transaction ID từ job trước ảnh hưởng job sau.

Nếu buộc phải dùng broker lâu dài, xử lý nó như shared service: có namespace, credential, quota, cleanup job và kiểm soát ownership riêng.

## 5. Đặt namespace riêng cho mỗi job và shard

Tên topic, consumer group và transactional ID phải duy nhất trong phạm vi các job có thể chạy đồng thời.

Một namespace có thể kết hợp CI run/build ID, job name hoặc matrix shard, test suite/case ID và random suffix ngắn để tránh va chạm khi runner tái sử dụng ID.

Ví dụ:

~~~text
run: build-8421
shard: integration-2
suite: order-flow

topic: ci-build-8421-integration-2-order-flow-orders
group: ci-build-8421-integration-2-order-flow-consumer
transactional.id: ci-build-8421-integration-2-order-flow-producer
~~~

Tên topic Kafka có giới hạn độ dài và tập ký tự hợp lệ. Helper tạo tên nên chuẩn hóa ký tự, giới hạn chiều dài và tránh tên chỉ gồm dấu chấm/gạch dưới. Không đưa toàn bộ UUID dài hoặc branch name chưa sanitize vào mọi resource name.

Ví dụ Java:

~~~java
public final class CiResourceNames {
    private final String prefix;

    public CiResourceNames(String runId, String shard, String suite) {
        this.prefix = sanitize("ci-" + runId + "-" + shard + "-" + suite);
    }

    public String topic(String logicalName) {
        return fit(prefix + "-" + sanitize(logicalName));
    }

    public String groupId(String logicalName) {
        return fit(prefix + "-group-" + sanitize(logicalName));
    }

    public String transactionalId(String logicalName) {
        return fit(prefix + "-tx-" + sanitize(logicalName));
    }

    private static String sanitize(String value) {
        return value.toLowerCase(Locale.ROOT)
            .replaceAll("[^a-z0-9._-]", "-")
            .replaceAll("-+", "-");
    }

    private static String fit(String value) {
        return value.length() <= 180
            ? value
            : value.substring(0, 180);
    }
}
~~~

Ví dụ helper minh họa nguyên tắc. Implementation thật nên xử lý chuỗi rỗng, tên chỉ có dấu phân cách, suffix collision và kiểm tra giới hạn naming theo quy tắc Kafka đang dùng.

### Phân biệt các loại ID

| ID | Ý nghĩa | Cần unique theo |
|---|---|---|
| `topic` | Nơi lưu record | Test run/shard/case |
| `group.id` | Danh tính consumer group | Nhóm consumer độc lập |
| `transactional.id` | Danh tính producer transactional và fencing scope | Producer instance cần tách biệt |
| `client.id` | Nhận diện client trong log/metric | Client instance hoặc role |
| `eventId` | Định danh business event | Fixture/test case |

Đổi client.id không tạo isolation cho consumer group. Đổi group.id không làm transactional producer độc lập. Phải cấp từng loại ID đúng mục đích.

## 6. Cô lập dữ liệu test

Topic riêng là lớp isolation đầu tiên; event fixture cũng cần riêng. Hai test cùng topic vẫn có thể đọc nhầm record nếu chúng dùng chung key, group hoặc assertion quá rộng.

Nên:

- Gắn runId, testCaseId và eventId vào payload/header.
- Dùng key có namespace test để không xung đột với fixture khác.
- Consumer dùng group ID riêng cho test case.
- Tạo topic với partition count/config đúng mục tiêu test.
- Đặt retention ngắn hoặc cleanup policy phù hợp môi trường ephemeral.
- Chỉ assert event thuộc test hiện tại.
- Tránh dùng một topic nghiệp vụ chung trên shared cluster CI nếu không có ownership registry.

Ví dụ header:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>(topic, "order-" + testCaseId, payload);
record.headers().add(
    "ci-run-id",
    runId.getBytes(StandardCharsets.UTF_8)
);
record.headers().add(
    "test-case-id",
    testCaseId.getBytes(StandardCharsets.UTF_8)
);
~~~

Không dựa vào timestamp hiện tại làm định danh duy nhất. Nhiều test có thể bắt đầu trong cùng một mili giây; dùng CI ID cộng UUID hoặc sequence ổn định hơn.

## 7. Tạo topic rõ ràng và kiểm tra readiness

Không dựa vào auto topic creation nếu test cần partition count hoặc config xác định. Tạo topic bằng AdminClient và đợi thao tác hoàn tất:

~~~java
NewTopic topic = new NewTopic(topicName, 1, (short) 1);
admin.createTopics(List.of(topic))
    .all()
    .get(10, TimeUnit.SECONDS);
~~~

Sau khi tạo, có thể gọi describeTopics() và xác nhận partition count/replica assignment trước khi chạy producer/consumer. Với topic cần config cụ thể, kiểm tra describeConfigs() thay vì giả định broker áp dụng đúng giá trị mặc định.

### Readiness không chỉ là port đã mở

Container có thể mở port trước khi broker sẵn sàng xử lý mọi request. Dùng readiness probe có timeout:

1. Chờ container health/listening theo cơ chế của Testcontainers.
2. Tạo AdminClient với bootstrap server được cấp động.
3. Gọi describeCluster() và xác nhận broker/node có mặt.
4. Tạo topic kiểm thử nhỏ hoặc describe topic đã tạo.
5. Chỉ khởi chạy test khi metadata request thành công.

Mọi bước chờ phải có deadline và thông báo lỗi nêu rõ endpoint, broker log và operation đang chờ. Không dùng vòng lặp vô hạn hoặc Thread.sleep() cố định để đoán broker đã sẵn sàng.

## 8. Quản lý client lifecycle

Resource cleanup phải theo thứ tự phụ thuộc. Producer/consumer đang hoạt động có thể giữ socket, group membership hoặc transaction chưa kết thúc; vì vậy không xóa topic trước khi đóng client.

Thứ tự teardown thường dùng:

1. Ngừng nhận công việc mới và dừng poll loop.
2. Chờ handler/worker đang xử lý hoàn tất trong timeout hữu hạn.
3. Commit/abort transaction theo kết quả test.
4. Đóng consumer để rời group.
5. Flush rồi đóng producer.
6. Đóng AdminClient.
7. Đóng executor/scheduler do test tạo.
8. Xóa topic/group do test sở hữu nếu dùng shared broker.
9. Hủy container/network/volume nếu broker ephemeral.

Ví dụ dùng try-with-resources:

~~~java
try (Admin admin = Admin.create(adminConfig);
     KafkaProducer<String, String> producer =
         new KafkaProducer<>(producerConfig);
     KafkaConsumer<String, String> consumer =
         new KafkaConsumer<>(consumerConfig)) {

    // Tạo topic, chạy test và xác minh record.
}
~~~

Trong thực tế, producer/consumer thường cần được đóng theo thứ tự riêng để bảo đảm consumer loop đã dừng và producer flush xong. Dùng fixture hoặc try/finally khi cần kiểm soát thứ tự; không giả định thứ tự close ngẫu nhiên của nhiều resource là phù hợp với ứng dụng.

### Dùng timeout khi đóng

Consumer có overload close(Duration) để giới hạn thời gian chờ leave group/cleanup. Nếu ứng dụng có thread poll riêng, dừng thread đó trước khi gọi close. Producer close(Duration) cũng giúp giới hạn thời gian chờ gửi đang pending. Ghi log nếu close timeout thay vì treo pipeline vô hạn.

## 9. Cleanup topic bằng AdminClient

Trên shared broker CI, chỉ xóa topic do test hiện tại tạo. Lưu tên resource ngay tại thời điểm tạo thay vì quét cluster rồi xóa mọi topic có hậu tố -test.

~~~java
Set<String> ownedTopics = new HashSet<>();

String topicName = names.topic("orders");
admin.createTopics(List.of(new NewTopic(topicName, 1, (short) 1)))
    .all()
    .get(10, TimeUnit.SECONDS);
ownedTopics.add(topicName);

// Sau khi producer/consumer đã đóng:
admin.deleteTopics(ownedTopics)
    .all()
    .get(30, TimeUnit.SECONDS);
~~~

Delete topic là thao tác bất đồng bộ trong cluster. Future hoàn tất phản ánh response của request, nhưng trong một số môi trường metadata propagation/deletion hoàn toàn có thể cần thêm thời gian. Nếu test tiếp theo cần xác nhận topic không còn, poll listTopics()/describeTopics() với deadline thay vì sleep cố định.

Nếu broker chạy trong container riêng cho job, thường không cần xóa từng topic trước khi dừng container; hủy container/data volume sẽ dọn toàn bộ state nhanh và ít race hơn. Vẫn nên đóng client trước khi dừng container để log và lỗi teardown rõ ràng.

### Không xóa topic nội bộ

Không đưa các topic hệ thống vào cleanup list:

- `__consumer_offsets`
- `__transaction_state`
- Topic nội bộ của Kafka Connect.
- Topic changelog/repartition do Kafka Streams quản lý nếu test không sở hữu lifecycle đó.

Chỉ xóa internal topic khi một test chuyên biệt tạo cluster độc lập và quy trình teardown đã được thiết kế rõ. Trong test thông thường, để broker/container hủy chúng.

## 10. Cleanup consumer group và offset

Consumer group có thể còn tồn tại sau khi consumer đóng vì metadata/offset được lưu trên broker. Nếu shared broker cần xóa group, trước tiên phải xác nhận mọi member đã rời group.

~~~java
consumer.close(Duration.ofSeconds(5));

admin.deleteConsumerGroups(List.of(groupId))
    .all()
    .get(20, TimeUnit.SECONDS);
~~~

Nếu group vẫn active, broker có thể từ chối xóa. Nếu group deletion chưa hoàn tất hoặc coordinator đang chuyển trạng thái, hãy kiểm tra lỗi cụ thể và chờ với deadline. Không lặp delete vô hạn.

Đối với broker ephemeral, hủy broker là cách cleanup group state đáng tin cậy nhất. Đối với shared broker, chỉ xóa group ID nằm trong ownership registry của test run. Không xóa group theo prefix rộng nếu prefix đó có thể thuộc job đang chạy song song.

Consumer group offset cleanup và topic deletion là hai việc khác nhau. Xóa topic không thay thế việc quản lý group; xóa group không xóa topic. Hãy ghi cả hai loại resource nếu test tạo cả hai.

## 11. Cleanup transactional ID và producer state

Transactional ID không phải resource có API delete giống topic. Producer cần gọi close() và hoàn tất transaction theo đúng nhánh commit/abort. Khi cùng một transactional ID được khởi tạo bởi producer instance mới, Kafka có thể fence producer cũ; điều này có thể là hành vi test cần xác minh, nhưng không nên xảy ra ngẫu nhiên do hai job dùng chung ID.

Trong CI:

- Tạo transactional ID riêng cho test run/shard/producer role.
- Không tái sử dụng transactional ID giữa test song song.
- Đóng producer trong teardown.
- Không dùng fencing như cơ chế cleanup thông thường.
- Với test chuyên biệt về fencing, kiểm soát rõ hai producer instance và assert producer cũ bị fence.

Với broker ephemeral, transaction metadata biến mất cùng broker. Với shared broker, tránh cố xóa __transaction_state hoặc thao tác nội bộ để reset producer state.

## 12. Fixture quản lý tài nguyên theo ownership

Một fixture nên biết chính xác nó đã tạo resource nào. Có thể xây dựng registry:

~~~java
public final class KafkaTestResources implements AutoCloseable {
    private final Admin admin;
    private final Set<String> topics = new LinkedHashSet<>();
    private final Set<String> groups = new LinkedHashSet<>();
    private final List<AutoCloseable> clients = new ArrayList<>();

    public KafkaTestResources(Admin admin) {
        this.admin = admin;
    }

    public void ownTopic(String topic) {
        topics.add(topic);
    }

    public void ownGroup(String groupId) {
        groups.add(groupId);
    }

    public void ownClient(AutoCloseable client) {
        clients.add(client);
    }

    @Override
    public void close() throws Exception {
        Exception failure = null;
        for (int i = clients.size() - 1; i >= 0; i--) {
            try {
                clients.get(i).close();
            } catch (Exception e) {
                if (failure == null) failure = e;
                else failure.addSuppressed(e);
            }
        }
        try {
            if (!groups.isEmpty()) {
                admin.deleteConsumerGroups(groups).all().get(20, TimeUnit.SECONDS);
            }
        } catch (Exception e) {
            if (failure == null) failure = e;
            else failure.addSuppressed(e);
        }
        try {
            if (!topics.isEmpty()) {
                admin.deleteTopics(topics).all().get(30, TimeUnit.SECONDS);
            }
        } catch (Exception e) {
            if (failure == null) failure = e;
            else failure.addSuppressed(e);
        }
        try {
            admin.close();
        } catch (Exception e) {
            if (failure == null) failure = e;
            else failure.addSuppressed(e);
        }
        if (failure != null) throw failure;
    }
}
~~~

Đây là skeleton để minh họa ownership, không phải fixture hoàn chỉnh cho mọi project. Trong implementation thật:

- Trong skeleton này, fixture nhận ownership của AdminClient được truyền vào và đóng nó sau cleanup; nếu fixture cha giữ ownership thì bỏ block admin.close() hoặc tách AdminClient khỏi fixture để tránh đóng hai lần.
- Không đăng ký AdminClient qua ownClient() trong skeleton này vì fixture giữ nó mở cho tới khi xóa group/topic xong.
- Consumer phải được đóng trước khi xóa group.
- Nếu client close lỗi, vẫn nên cố gắng cleanup các resource độc lập còn lại; không bỏ qua toàn bộ cleanup chỉ vì một client lỗi.
- Nếu xóa group thất bại, vẫn tiếp tục thử xóa topic và đóng AdminClient; lưu các lỗi bổ sung để teardown report đủ nguyên nhân.
- Lỗi cleanup không được che mất exception gốc của test. Dùng suppressed exception hoặc gắn cleanup failure vào test report.
- Với broker ephemeral, không cần delete group/topic riêng nếu container sẽ bị hủy; giữ fixture chỉ để đóng client.

Một lựa chọn khác là fixture Extension của JUnit Jupiter quản lý resource theo class/method lifecycle. Dù chọn cách nào, ownership phải rõ và teardown phải chạy trong finally/callback của framework.

## 13. Dọn tài nguyên khi test fail hoặc CI bị cancel

AfterEach/AfterAll và AutoCloseable xử lý được phần lớn lỗi assertion/runtime, nhưng không đảm bảo JVM luôn chạy teardown khi process bị kill, runner mất điện hoặc CI hủy container cưỡng bức.

Vì vậy cần hai lớp cleanup:

**Cleanup trong test process**

- Dùng try-with-resources hoặc JUnit extension.
- Dùng timeout hữu hạn cho poll, close, delete và executor shutdown.
- Lưu resource ownership ngay sau khi tạo thành công.
- Dùng hook teardown của Testcontainers để hủy container.

**Cleanup ở cấp CI runner**

- Mỗi job có container/network/volume label hoặc tên nhận diện theo run ID.
- Runner teardown hủy đúng tài nguyên thuộc job đã kết thúc.
- Self-hosted runner có scheduled janitor dọn resource quá hạn theo label/owner.
- Janitor không xóa resource còn lease/heartbeat hoạt động.
- Giữ log và test report trước khi xóa container.

Không chạy docker system prune -a hoặc xóa mọi container/volume trên shared self-hosted runner. Cách đó có thể phá môi trường của job khác hoặc service dùng chung. Chỉ dọn resource được gắn owner label và đã hết lease.

## 14. CI song song và matrix build

CI thường chạy nhiều job cùng lúc theo Kafka version, module hoặc test shard. Isolation cần được tính theo toàn bộ ma trận, không chỉ một job. Nếu thêm Java version vào matrix, giá trị java-version của setup step phải lấy từ cùng matrix.

Ví dụ GitHub Actions:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    shard: ["unit", "kafka-integration"]

steps:
  - name: Checkout
    uses: actions/checkout@v4
  - name: Set up Java
    uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: "21"
  - name: Run unit tests
    if: matrix.shard == 'unit'
    run: ./gradlew test
  - name: Run Kafka integration tests
    if: matrix.shard == 'kafka-integration'
    run: ./gradlew kafkaIntegrationTest
    env:
      CI_RUN_ID: ${{ github.run_id }}
      CI_RUN_ATTEMPT: ${{ github.run_attempt }}
      CI_JOB_ID: ${{ github.job }}
      CI_SHARD: ${{ matrix.shard }}
~~~

Đây là ví dụ GitHub Actions với Java 21 cố định; thay version action và Gradle task theo repository. Run ID, attempt, job và shard được lấy từ context của workflow để namespace không bị hardcode. Nếu thêm Java version vào matrix, truyền đúng giá trị matrix vào setup step.

Quy tắc cho parallel test:

- Mỗi job có Kafka container riêng, hoặc namespace riêng trên shared broker.
- Mỗi test case song song có topic/group/event ID riêng.
- Không dùng static mutable fixture chia sẻ giữa test class chạy song song.
- Không giả định test order hoặc test trước đã cleanup thành công.
- Không dùng một transactional ID cho nhiều thread/job.
- Không để cleanup của job A xóa resource job B.

### Khi nào chia sẻ một container trong cùng JVM?

Có thể dùng một Kafka container cho một test suite để tiết kiệm startup time nếu test tạo topic/group riêng, không phụ thuộc thứ tự, đóng client sau mỗi case, không thay đổi broker-wide config và có giới hạn song song phù hợp.

Nếu test thay đổi broker config, mô phỏng broker failure hoặc dùng chung internal state, hãy dùng container/cluster riêng cho test đó.

## 15. Chờ điều kiện bất đồng bộ có deadline

Producer send, consumer poll, group assignment, topic creation và deletion đều có phần bất đồng bộ. Test phải chờ điều kiện có ý nghĩa, có timeout và log khi hết hạn.

~~~java
long deadline = System.nanoTime() + Duration.ofSeconds(10).toNanos();
ConsumerRecord<String, String> received = null;

while (System.nanoTime() < deadline && received == null) {
    ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(200));
    for (ConsumerRecord<String, String> record : records) {
        if (expectedEventId.equals(record.key())) {
            received = record;
            break;
        }
    }
}

assertNotNull(received, "Timed out waiting for expected event");
~~~

Đây là ví dụ polling có deadline; trong test suite lớn có thể dùng Awaitility hoặc helper chung để giảm lặp code. Timeout cần đủ dài cho môi trường CI nhưng không quá dài đến mức che giấu lỗi. Khi timeout, báo topic, group ID, expected event ID và consumer assignment/position nếu lấy được.

Không dùng Thread.sleep(5000) để chờ broker, group hoặc record. Sleep không chứng minh điều kiện đã xảy ra; nó chỉ làm test chậm và vẫn flaky khi CI tải cao.

## 16. Retry và phân loại lỗi trong pipeline

Không phải mọi test fail đều nên được retry. Phân loại:

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Assertion/product defect | Sai payload, mất event, sai offset | Fail ngay, không retry để che lỗi |
| Test isolation defect | Trùng topic/group, dữ liệu từ test khác | Sửa namespace/ownership |
| Readiness/infrastructure | Docker daemon chậm, image pull timeout | Có thể retry bước setup có giới hạn |
| Resource exhaustion | Runner hết memory/disk hoặc container bị OOM | Fail và lưu diagnostics; điều chỉnh capacity |
| Kafka behavior regression | Rebalance, transaction hoặc replication sai | Fail; giữ log và tái hiện |
| Flaky timing | Timeout do điều kiện chờ không đúng | Sửa synchronization; retry chỉ để thu thập bằng chứng tạm thời |

Nếu bật retry test, báo cáo lần chạy đầu và số lần retry. Không chuyển một test chỉ pass ở lần retry thành trạng thái xanh mà không theo dõi flake rate.

## 17. Thu thập diagnostics trước khi cleanup

Khi test fail, diagnostics phải được lưu trước khi container/network bị xóa:

- JUnit XML/test report và stack trace.
- Kafka broker logs và container exit code.
- Testcontainers startup log và image/version.
- Broker metadata: cluster ID, broker list, topic/partition/leader/ISR.
- Consumer group state, assignment và lag nếu truy vấn được.
- Connector/task logs nếu test có Connect.
- Streams task/restore logs nếu test có Kafka Streams.
- Thread dump khi test treo.
- Docker resource usage và disk free space của runner.

Ví dụ log metadata trong teardown:

~~~java
try {
    DescribeClusterResult cluster = admin.describeCluster();
    log.info("Kafka cluster id: {}", cluster.clusterId().get(5, TimeUnit.SECONDS));
    log.info("Kafka nodes: {}", cluster.nodes().get(5, TimeUnit.SECONDS));
} catch (Exception diagnosticError) {
    log.warn("Could not collect Kafka diagnostics", diagnosticError);
}
~~~

Diagnostics không được làm cleanup treo vô hạn. Dùng timeout ngắn và bắt riêng lỗi thu thập. Redact credential, JAAS config, token, payload nhạy cảm và địa chỉ nội bộ trước khi upload artifact.

## 18. Dùng shared CI broker an toàn

Nếu tổ chức có Kafka cluster dùng chung cho CI:

1. Cấp principal riêng cho CI, quyền chỉ trên namespace test.
2. Đặt quota để một job lỗi không chiếm hết broker.
3. Dùng run ID và shard ID trong topic/group/transactional ID.
4. Ghi reservation của resource vào ownership registry trước khi tạo; sau khi tạo thành công, cập nhật trạng thái và expiry để vẫn truy vết được nếu job bị kill giữa chừng.
5. Chỉ cho phép cleanup đúng resource được registry ghi nhận.
6. Đặt retention ngắn cho topic test nếu nghiệp vụ cho phép.
7. Có janitor xóa resource hết hạn sau khi xác minh không còn owner hoạt động.
8. Theo dõi số topic, partition, group, disk và controller metadata.
9. Không dùng production cluster làm test target.

Shared broker tiết kiệm chi phí khởi tạo nhưng tạo ra chi phí vận hành isolation. Nếu không thể bảo đảm ownership và cleanup chính xác, dùng broker ephemeral theo job sẽ an toàn hơn.

## 19. Giới hạn tài nguyên của runner

Kafka cần memory, file descriptors, disk và CPU. Một pipeline có thể fail ngẫu nhiên nếu nhiều job khởi tạo broker đồng thời trên runner nhỏ.

Theo dõi số container Kafka đồng thời, memory limit/OOM, disk space/tốc độ ghi volume, CPU throttling/startup duration, segment/file descriptors, Docker network/port allocation và thời gian image pull.

Không giải quyết runner quá tải bằng cách tăng timeout vô hạn. Giới hạn concurrency của integration stage, dùng image cache hợp lý và dành runner đủ tài nguyên cho test cần broker.

## 20. Ví dụ cấu hình Gradle cho test groups

Có thể tách unit và integration test thành hai task:

~~~kotlin
tasks.test {
    useJUnitPlatform {
        excludeTags("kafka-integration", "kafka-cluster")
    }
}

tasks.register<Test>("kafkaIntegrationTest") {
    useJUnitPlatform {
        includeTags("kafka-integration")
    }
    shouldRunAfter(tasks.test)
    maxParallelForks = 1
}

tasks.register<Test>("kafkaClusterTest") {
    useJUnitPlatform {
        includeTags("kafka-cluster")
    }
    shouldRunAfter(tasks.named("kafkaIntegrationTest"))
    maxParallelForks = 1
}
~~~

Ví dụ trên tách test theo tag và giới hạn fork cho test cần broker. Có thể tăng parallelism sau khi mỗi fork có container hoặc namespace riêng và runner đủ tài nguyên. Không mặc định một Kafka container static có thể được chia sẻ an toàn giữa nhiều JVM fork.

## 21. Quy trình cleanup tổng thể

~~~mermaid
flowchart TD
    A["Test setup"] --> B["Register owned resources"]
    B --> C["Run test"]
    C --> D{"Test passed?"}
    D -->|Yes| E["Stop pollers and workers"]
    D -->|No| F["Collect bounded diagnostics"]
    F --> E
    E --> G["Close consumers and producers"]
    G --> H["Close AdminClient"]
    H --> I{"Ephemeral broker?"}
    I -->|Yes| J["Destroy container and data volume"]
    I -->|No| K["Delete owned groups and topics"]
    K --> L["Verify cleanup with deadline"]
    J --> M["Publish reports"]
    L --> M
~~~

Với shared broker, cleanup group/topic sau khi client đóng và xác minh ownership. Với ephemeral broker, hủy container và volume là bước cleanup state chính; không cần xóa từng topic nội bộ.

## 22. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Test đọc record của test khác | Topic/group dùng chung hoặc fixture không unique | Kiểm tra run ID, group ID, key và event ID |
| Consumer không nhận record | Chưa assign, offset reset sai, group cũ hoặc topic sai | Kiểm tra assignment, position, group và topic metadata |
| Topic vẫn tồn tại sau test | Delete async, client chưa đóng hoặc cleanup không chạy | Kiểm tra owner registry, broker log và deletion state |
| Không xóa được group | Consumer member còn active | Đóng poll loop/client, describe group rồi retry có giới hạn |
| Transactional producer bị fenced | Trùng transactional ID giữa test/job | Kiểm tra namespace và số producer dùng cùng ID |
| Container khởi động chậm | Image pull, runner CPU/memory/disk thiếu | Lưu startup logs, Docker stats và giới hạn concurrency |
| CI bị treo ở teardown | Close/delete không có timeout hoặc thread còn sống | Thread dump, timeout từng bước và shutdown executor |
| Test chỉ fail khi chạy song song | Static mutable state, shared topic/group hoặc port conflict | Chạy shard riêng, kiểm tra resource naming |
| Test pass khi retry | Race condition hoặc infrastructure không ổn định | Giữ report lần đầu, đo flake rate, sửa readiness/synchronization |
| Runner còn volume/container cũ | Job bị kill trước teardown | Janitor theo owner label và lease expiry |

## 23. Production checklist cho CI

- [ ] Unit test không khởi tạo Kafka khi không cần.
- [ ] Integration test dùng broker ephemeral theo job/suite hoặc namespace riêng trên shared broker.
- [ ] Kafka image và Testcontainers dependency được pin version.
- [ ] Readiness kiểm tra broker request thực tế, có deadline.
- [ ] Topic/group/transactional ID được namespace theo run/shard/test.
- [ ] Fixture ghi reservation vào ownership registry trước khi tạo resource và cập nhật trạng thái sau khi tạo thành công.
- [ ] Test data có event ID và correlation ID riêng.
- [ ] Consumer loop/worker dừng trước khi đóng consumer.
- [ ] Producer flush/close và transaction commit/abort theo kết quả test.
- [ ] AdminClient và executor được đóng.
- [ ] Shared broker chỉ xóa topic/group do job sở hữu.
- [ ] Không xóa internal topics của Kafka/Connect/Streams bằng cleanup chung.
- [ ] Topic/group deletion được chờ có timeout khi cần xác minh.
- [ ] Ephemeral container/network/volume bị hủy khi job hoàn tất hoặc cancel.
- [ ] Self-hosted runner janitor chỉ dọn resource đã hết lease và đúng owner label.
- [ ] Parallel matrix không dùng chung mutable fixture hoặc transactional ID.
- [ ] Retry không che assertion failure hoặc Kafka regression.
- [ ] Logs, JUnit reports và broker diagnostics được lưu trước cleanup.
- [ ] Secret và payload nhạy cảm được redact khỏi artifact.
- [ ] Multi-broker test được dùng cho replication, ISR và failover.
- [ ] Runner có đủ memory, disk, CPU và concurrency budget.

## 24. Bài tập thực hành

1. Tạo một JUnit integration test khởi động Kafka container, tạo topic theo run ID, gửi và đọc một event, rồi đóng mọi client.
2. Chạy hai test shard song song và chứng minh topic/group không trùng nhau.
3. Cố ý làm assertion fail; xác nhận broker log và JUnit report vẫn được lưu trước khi container bị hủy.
4. Tạo một consumer group trên shared broker thử nghiệm, đóng consumer rồi xóa group bằng AdminClient với timeout.
5. Cố ý để consumer không đóng; quan sát lỗi delete group và sửa teardown.
6. Hủy CI job giữa chừng trên self-hosted runner; xác minh janitor chỉ dọn container/volume có owner label và lease đã hết hạn.
7. Chạy integration suite với giới hạn concurrency khác nhau, ghi lại startup duration, memory peak và flake rate.

Một pipeline Kafka ổn định cần biết mỗi tài nguyên thuộc về ai, tồn tại trong bao lâu và được thu hồi ở bước nào. Broker ephemeral giúp đơn giản hóa state cleanup; namespace riêng bảo vệ test song song; teardown có timeout và diagnostics giúp xử lý cả lỗi ứng dụng lẫn lỗi hạ tầng. Chỉ cleanup đúng tài nguyên do test sở hữu, và dùng cluster nhiều broker riêng khi cần chứng minh replication hoặc failover.
