# Đánh giá tính năng bị loại bỏ, cấu hình đổi mặc định và API deprecated

Nâng cấp Apache Kafka không chỉ là thay phiên bản broker. Mỗi release có thể loại bỏ tính năng cũ, đổi giá trị mặc định, đánh dấu API deprecated hoặc thay đổi hành vi trong những tình huống cụ thể. Một hệ thống vẫn khởi động được sau nâng cấp chưa chắc đã giữ nguyên latency, throughput, durability, consumer assignment hay cách vận hành.

Bài này hướng dẫn cách đánh giá thay đổi theo đúng phiên bản nguồn và đích, nhận diện những mục cần xử lý trong code/configuration, xây dựng compatibility matrix và kiểm chứng trước khi triển khai. Các ví dụ tập trung vào thay đổi có tác động rõ trong các dòng Kafka 2.x, 3.x và 4.x. Luôn đối chiếu release notes và configuration reference của đúng minor release vì trạng thái API/config có thể thay đổi theo phiên bản.

## 1. Phân biệt removed, deprecated và changed default

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Removed | Tính năng, config, option hoặc API không còn tồn tại trong release đích | Thay thế trước khi nâng cấp; cấu hình cũ có thể làm broker/tool không khởi động hoặc client không compile |
| Deprecated | Vẫn còn nhưng không được khuyến nghị; có thể bị loại bỏ trong release tương lai | Lập kế hoạch thay thế, theo dõi compiler warning và release notes |
| Changed default | Giá trị mặc định hoặc hành vi khi không khai báo cấu hình đã thay đổi | Đánh giá hành vi thực tế; quyết định pin giá trị cũ hay chấp nhận default mới |
| Behavior change | API/config còn tồn tại nhưng semantics, timing hoặc edge case thay đổi | Viết regression test cho hành vi bị ảnh hưởng |
| Compatibility change | Yêu cầu runtime, protocol, metadata format hoặc topology thay đổi | Kiểm tra thứ tự nâng cấp, client compatibility và rollback boundary |

**Removed không đồng nghĩa deprecated.** Một API deprecated ở bản nguồn vẫn có thể còn hoạt động trong bản đích; ngược lại, một tính năng đã bị loại bỏ không thể giữ lại bằng cách đặt cấu hình cũ.

**Changed default không tự động ghi đè cấu hình đang khai báo.** Nếu ứng dụng đặt tường minh `linger.ms=0`, việc default của Kafka mới đổi thành 5 ms không làm cấu hình đó tự đổi. Rủi ro thường xuất hiện ở nơi không khai báo giá trị, nơi lấy default từ code, hoặc nơi framework tự tạo producer/consumer properties.

## 2. Lập bản đồ phiên bản nguồn và đích

Trước khi tìm deprecated API, ghi lại chính xác thành phần đang chạy. Kafka cluster có thể sử dụng broker và client khác phiên bản; Connect worker, connector plugin, Kafka Streams application, Schema Registry và monitoring exporter cũng có vòng đời release riêng.

Một inventory tối thiểu:

| Thành phần | Thông tin cần ghi |
|---|---|
| Broker | Kafka version, distribution/vendor, KRaft hay ZooKeeper, số broker/controller |
| Java runtime | JDK version, vendor, JVM flags, GC |
| Java clients | `kafka-clients` version theo từng service |
| Spring Kafka | Spring Boot, Spring Kafka và Kafka client version thực tế sau dependency resolution |
| Kafka Streams | Kafka Streams library, state store/serde và topology |
| Kafka Connect | Worker version, connector plugin version, converter và SMT |
| Admin tooling | CLI version, script wrapper, automation dùng `--bootstrap-server` hay option cũ |
| Infrastructure | Kubernetes/operator, Helm chart, Ansible/Terraform và container image |
| Protocol/data | Metadata version, topic configs, RF, ACL, transaction và serialization format |

Không suy luận version client từ version broker. Một ứng dụng có thể đóng gói Kafka client qua dependency transitive; kiểm tra dependency tree hoặc SBOM để xác nhận artifact thực tế.

### Ví dụ kiểm tra dependency Maven

```bash
mvn dependency:tree -Dincludes=org.apache.kafka
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
```

Nếu dùng Spring Boot dependency management, ghi cả version do BOM quản lý và version được resolve ở runtime. Không tự nâng `kafka-clients` vượt khỏi ma trận hỗ trợ của framework chỉ để xóa một compiler warning.

## 3. Đọc release notes và migration guide đúng cách

Không chỉ đọc changelog của phiên bản lớn. Một upgrade từ 3.6 lên 4.0 đi qua nhiều minor release; thay đổi có thể xuất hiện ở 3.7, 3.8 hoặc 3.9 và tạo điều kiện bắt buộc trước khi lên 4.0.

Với mỗi release trong đường nâng cấp, kiểm tra:

1. Upgrade notes và migration guide.
2. Removed/deprecated features.
3. Broker configuration changes.
4. Producer, consumer và admin client configuration changes.
5. Java API changes và binary compatibility.
6. KRaft/quorum/metadata version changes.
7. Kafka Connect, Streams và connector compatibility.
8. Security protocol, TLS/SASL và ACL changes.
9. Metrics/JMX name hoặc semantics changes.
10. Known issues, limitations và downgrade restrictions.

Nên tạo một bảng thay đổi có owner và trạng thái xử lý, thay vì chỉ lưu link release notes trong ticket.

| Trường | Nội dung |
|---|---|
| Source version | Phiên bản hiện tại |
| Target version | Phiên bản dự định nâng cấp |
| Affected component | Broker, client, Connect, Streams, tooling |
| Change type | Removed, deprecated, changed default, behavior |
| Existing usage | Code/config/automation đang sử dụng |
| Impact | Startup, compile, throughput, latency, durability, operations |
| Remediation | Thay API, bỏ config, pin default hoặc đổi topology |
| Validation | Test/benchmark/chaos scenario cần chạy |
| Owner/status | Người phụ trách và trạng thái hoàn tất |

## 4. Thay đổi lớn: ZooKeeper mode bị loại bỏ trong Kafka 4.0

Kafka 4.0 chỉ hỗ trợ KRaft. ZooKeeper mode đã bị loại bỏ khỏi Kafka 4.0; broker 4.0 không còn dùng `zookeeper.connect` để vận hành cluster và các thao tác CLI cũ dựa trên `--zookeeper` không còn là đường quản trị hợp lệ.

Đây là thay đổi kiến trúc, không phải chỉ đổi một property.

### Trước đây: cluster ZooKeeper

Trong cluster cũ, broker cấu hình ZooKeeper:

```properties
broker.id=1
zookeeper.connect=zk-1:2181,zk-2:2181,zk-3:2181
listeners=PLAINTEXT://broker-1:9092
```

Một số lệnh admin cũ có thể trỏ thẳng ZooKeeper:

```bash
kafka-topics.sh --zookeeper zk-1:2181 --list
```

### Sau khi chuyển sang KRaft

KRaft dùng controller quorum để quản lý metadata. Broker kết nối tới controller theo cấu hình và listener của cluster KRaft. CLI quản trị kết nối qua broker/bootstrap server:

```bash
kafka-topics.sh --bootstrap-server broker-1:9092 --list
```

Cấu hình KRaft cụ thể phụ thuộc Kafka release, static/dynamic quorum, node role và security protocol. Không sao chép một file cấu hình KRaft mẫu mà chưa xác minh property bắt buộc của đúng phiên bản.

### Điều kiện trước khi nâng lên Kafka 4.0

- Cluster phải được chuyển sang KRaft theo migration procedure được hỗ trợ ở release nguồn.
- Kiểm tra mọi broker đã chạy KRaft và metadata quorum khỏe.
- Tìm tất cả automation còn dùng `--zookeeper`, `zookeeper.connect`, ZooKeeper CLI hoặc đọc trực tiếp ZooKeeper znodes.
- Chuyển script tạo topic, ACL, config và consumer group sang Admin API/CLI dựa trên `--bootstrap-server`.
- Kiểm tra monitoring, backup, disaster recovery và operator không còn phụ thuộc ZooKeeper.
- Xác minh Connect/Streams/client/plugin tương thích với broker/client version đích.
- Lập kế hoạch rollback trước khi vượt qua điểm migration/finalization không thể quay lại ZooKeeper.

**Không nâng trực tiếp một cluster ZooKeeper lên Kafka 4.0.** Hãy thực hiện migration sang KRaft ở phiên bản Kafka còn hỗ trợ quy trình migration, hoàn tất và xác minh cluster KRaft trước khi nâng broker lên 4.0. Migration ZooKeeper-to-KRaft có các bước và giới hạn riêng; tuân thủ đúng guide của release đang chạy.

## 5. Tìm dependency ẩn vào ZooKeeper

Ngay cả khi broker config đã chuyển sang KRaft, automation hoặc công cụ ngoài vẫn có thể gọi ZooKeeper.

Tìm trong repository, deployment manifests và script:

```bash
rg -n -i "zookeeper\.connect|--zookeeper|zkCli|zookeeper:" .
```

Phân loại kết quả:

| Kết quả tìm thấy | Cách xử lý |
|---|---|
| Broker config `zookeeper.connect` | Loại bỏ sau khi migration KRaft hoàn tất |
| CLI `--zookeeper` | Chuyển sang `--bootstrap-server` và kiểm tra authentication |
| ZooKeeper shell/zkCli | Thay bằng Kafka Admin API, CLI hoặc công cụ quản trị KRaft |
| Application đọc znode | Thiết kế lại để dùng Kafka API/metadata hoặc một registry/service phù hợp |
| Monitoring exporter scrape ZooKeeper | Chuyển sang broker/controller metrics và quorum health |
| Runbook backup ZooKeeper data | Viết lại theo metadata/quorum backup và disaster recovery của KRaft |
| Helm chart/operator còn dựng ZooKeeper | Chuyển sang topology KRaft được vendor/operator hỗ trợ |

Không xóa mọi chuỗi có chữ ZooKeeper một cách tự động. Một số tài liệu lịch sử hoặc tool quản lý một hệ thống ZooKeeper khác trong cùng nền tảng có thể không liên quan tới Kafka.

## 6. Java runtime baseline cũng là một phần của upgrade

Kafka 4.0 nâng baseline Java cho broker/tooling lên Java 17. Trước khi nâng broker image, kiểm tra:

- JDK trong container/VM của broker và controller.
- JDK trong image dùng để chạy Kafka CLI.
- Script startup, `JAVA_HOME`, JVM flags và GC options.
- Base image/OS có còn hỗ trợ JDK mục tiêu không.
- Monitoring agent, security agent và profiler có tương thích với JDK mới không.
- Các plugin hoặc custom Kafka component chạy cùng process có phụ thuộc Java cũ không.

Client Java và broker có thể có yêu cầu runtime khác nhau theo release. Không kết luận rằng mọi application client phải nâng JDK chỉ vì broker cần Java 17; kiểm tra yêu cầu riêng của `kafka-clients`, Spring Boot và framework ứng dụng.

Ví dụ kiểm tra runtime trong container:

```bash
java -version
echo "$JAVA_HOME"
```

Nếu chạy Kafka dưới systemd, kiểm tra environment của service và command thực tế, không chỉ Java trong shell đăng nhập của quản trị viên.

## 7. Producer defaults thay đổi: idempotence và acks

Một thay đổi quan trọng trong dòng Kafka 3.0 là producer bật idempotence mặc định (`enable.idempotence=true`) khi không có cấu hình xung đột. Giá trị mặc định của `acks` cũng là `all` trong dòng client hiện đại.

Tác động:

- Producer có thể tự động retry mà tránh duplicate do retry trong phạm vi idempotent producer session.
- Ordering được bảo đảm trong điều kiện cấu hình idempotence hợp lệ.
- Producer có thể có behavior và throughput khác so với client cũ vốn dùng `acks=1` hoặc tắt idempotence.
- Nếu các property xung đột với yêu cầu idempotence, client có thể báo lỗi cấu hình hoặc không bật idempotence theo default như mong đợi; phải kiểm tra log startup và effective properties.

Không nhầm idempotent producer với exactly-once end-to-end. Idempotence chống duplicate do producer retry trong một producer session; giao dịch Kafka và xử lý offset/output cần cấu hình transaction semantics riêng.

### Kiểm tra producer properties

```java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "kafka-1:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());

// Khai báo rõ durability và retry semantics cần thiết.
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
props.put(ProducerConfig.RETRIES_CONFIG, Integer.toString(Integer.MAX_VALUE));
props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, "5");
```

Đoạn code trên chỉ minh họa cấu hình producer; các import `ProducerConfig`, `StringSerializer` và khởi tạo `KafkaProducer` cần được bổ sung theo ứng dụng. Kiểm tra giới hạn `max.in.flight.requests.per.connection` và các ràng buộc khác theo Kafka client version đang dùng.

Nếu muốn behavior ổn định qua nhiều lần nâng cấp, đặt rõ các property quan trọng thay vì dựa vào default. Tuy vậy, không pin mọi config một cách máy móc: chỉ pin các giá trị có quyết định vận hành và ghi lý do.

## 8. Producer linger.ms: default đổi từ 0 lên 5 ms trong Kafka 4.0

Kafka 4.0 đổi default `linger.ms` của producer từ 0 ms lên 5 ms. Producer có thể chờ một khoảng ngắn để gom thêm record vào batch trước khi gửi; trong tải phù hợp, batching tốt hơn có thể cải thiện throughput và hiệu quả compression.

Tác động cần đánh giá:

- **Latency:** record có thể chờ thêm tối đa khoảng linger window khi batch chưa đầy; tổng latency còn phụ thuộc broker/network/queue.
- **Throughput:** batch lớn hơn có thể giảm request overhead và tăng compression efficiency.
- **CPU/network:** batching có thể giảm số request, nhưng kết quả phụ thuộc payload và partition distribution.
- **Low traffic:** producer ít record có thể cảm nhận rõ hơn khoảng chờ; high traffic thường lấp batch nhanh.
- **SLA:** service yêu cầu latency rất thấp cần benchmark p95/p99, không chỉ đo average.

Nếu hệ thống đang dựa vào default 0 ms, nâng client lên Kafka 4.0 có thể thay đổi behavior dù không sửa code.

### Pin behavior cũ khi cần

```java
props.put(ProducerConfig.LINGER_MS_CONFIG, "0");
```

### Chọn batching có chủ đích

```java
props.put(ProducerConfig.LINGER_MS_CONFIG, "5");
props.put(ProducerConfig.BATCH_SIZE_CONFIG, Integer.toString(32 * 1024));
```

Đừng mặc định 5 ms hoặc 10 ms là tối ưu cho mọi ứng dụng. Benchmark với record size, số partition, producer concurrency và latency SLO thực tế. Đọc producer config reference của đúng Kafka client release để xác nhận default.

## 9. Cách đánh giá changed default trong toàn bộ cấu hình

Với mỗi property, xác định ba lớp giá trị:

1. **Code default:** giá trị mà thư viện client khai báo.
2. **Framework default:** giá trị Spring Boot, Spring Kafka, Connect worker hoặc operator có thể áp dụng.
3. **Effective runtime value:** giá trị cuối cùng sau khi merge file, environment, command-line, secret và programmatic override.

Giá trị runtime có thể khác cả code default lẫn file cấu hình. Ví dụ `spring.kafka.producer.properties.linger.ms` có thể override giá trị do Kafka client đặt; một custom `ProducerFactory` còn có thể merge thêm map riêng.

Lập bảng cấu hình:

| Property | Scope | Source value | Target default | Effective value | Quyết định |
|---|---|---:|---:|---:|---|
| `enable.idempotence` | Producer | false/không đặt | true trong client hiện đại nếu không xung đột | Xác minh | Pin true nếu yêu cầu durability/ordering |
| `acks` | Producer | 1/không đặt | all trong client hiện đại | Xác minh | Đánh giá durability và latency |
| `linger.ms` | Producer | 0/không đặt | 5 ms từ Kafka 4.0 | Xác minh | Pin theo latency/throughput SLO |
| `auto.offset.reset` | Consumer | earliest/latest/không đặt | Kiểm tra đúng release | Xác minh | Bảo đảm hành vi khi không có offset hợp lệ |
| `partition.assignment.strategy` | Consumer | Class list/không đặt | Kiểm tra đúng release | Xác minh | Đánh giá rebalance behavior |
| `cleanup.policy` | Topic | delete/compact/không đặt | Topic default | Xác minh theo topic | Bảo vệ retention/data semantics |

Bảng này là mẫu audit, không phải danh sách đầy đủ các default change của mọi Kafka release. Không suy ra giá trị target từ bảng nếu chưa đối chiếu release reference.

## 10. Deprecated Java API: poll(long) và poll(Duration)

Kafka Java Consumer đã deprecated overload `poll(long timeout)` từ lâu và cung cấp `poll(Duration)` để biểu diễn timeout rõ ràng.

Code cũ:

```java
ConsumerRecords<String, String> records = consumer.poll(1000);
```

Code mới:

```java
ConsumerRecords<String, String> records =
    consumer.poll(Duration.ofSeconds(1));
```

Ví dụ vòng lặp consumer:

```java
import java.time.Duration;
import java.util.Collections;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public final class EventReader {
    public void run(Properties properties) {
        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(properties)) {
            consumer.subscribe(Collections.singletonList("orders.events"));

            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(500));

                records.forEach(record -> {
                    // Validate và xử lý record.
                    System.out.printf(
                        "partition=%d offset=%d key=%s%n",
                        record.partition(), record.offset(), record.key());
                });
            }
        }
    }
}
```

Đây là skeleton minh họa; production code cần xử lý exception, shutdown signal, commit policy, retry/DLQ và backpressure. Không commit offset trước khi business processing hoàn tất nếu yêu cầu at-least-once.

Khi thay `poll(long)` bằng `poll(Duration)`, giữ nguyên timeout thực tế. Ví dụ `poll(1000)` tương ứng `Duration.ofMillis(1000)`, không phải `Duration.ofSeconds(1000)`.

## 11. Cách xử lý deprecated API có kiểm soát

Không thay mọi API deprecated bằng một API có tên gần giống. Với từng warning:

1. Xác định API owner: Kafka client, Streams, Connect plugin hay framework.
2. Đọc Javadoc của đúng version source và target.
3. Xem `@Deprecated(since=..., forRemoval=...)` nếu có.
4. Đọc migration note để biết replacement và khác biệt semantics.
5. Viết test chứng minh behavior mới tương đương yêu cầu.
6. Thay từng nhóm API nhỏ, compile và chạy integration test.
7. Xóa suppression cũ sau khi thay xong.

Ví dụ API cũ có thể vẫn tồn tại nhưng đã có overload nhận `Duration`, collection hoặc options object. Khi thay, cần giữ timeout, null handling, exception behavior và thread ownership.

### Không dùng SuppressWarnings("deprecation") để che nợ kỹ thuật

Chỉ suppress khi có lý do rõ ràng, phạm vi nhỏ và ticket theo dõi. Nếu suppress cả package, đội phát triển có thể bỏ sót API bị loại bỏ trong release tiếp theo.

## 12. Tìm deprecated API và cấu hình cũ trong source

Tìm các API/config thường có thay đổi qua các release:

```bash
rg -n -i "zookeeper\.connect|--zookeeper|zkCli|zookeeper:" .
rg -n "poll\([0-9]+\)|linger\.ms|enable\.idempotence|acks|auto\.offset\.reset|partition\.assignment\.strategy" .
```

Search chỉ tạo danh sách ứng viên. Một chuỗi có thể nằm trong tài liệu, test fixture hoặc code không còn chạy; phải xem caller và runtime configuration.

Bật compiler warning trong build để nhìn thấy deprecated API:

```bash
mvn -DskipTests compile
```

Với Gradle:

```bash
./gradlew compileJava
```

Kiểm tra dependency version thực tế trước khi kết luận warning đến từ Kafka hay wrapper/framework.

## 13. Đánh giá API compatibility và client/broker compatibility

Kafka protocol compatibility không có nghĩa mọi client library version đều có cùng API hoặc feature. Cần tách:

- **Source compatibility:** source code còn compile không?
- **Binary compatibility:** bytecode đã build có chạy với dependency mới không?
- **Wire protocol compatibility:** client và broker có giao tiếp được không?
- **Feature compatibility:** feature mới có được broker/client version hỗ trợ không?
- **Semantic compatibility:** hành vi runtime có giữ đúng contract không?

Ví dụ, một Java client cũ có thể vẫn kết nối broker mới nhưng không dùng được API/feature mới. Ngược lại, client mới kết nối broker cũ có thể tự hạ khả năng protocol hoặc báo feature không hỗ trợ.

Không nâng `kafka-clients` chỉ vì broker đã lên version mới. Kiểm tra compatibility policy của release và framework; ưu tiên phiên bản client được Spring Boot/Spring Kafka hỗ trợ.

## 14. Rolling upgrade và metadata version

Với các release hỗ trợ rolling upgrade, quá trình thường có các giai đoạn:

1. Kiểm tra release notes và version hop được hỗ trợ.
2. Đảm bảo cluster health, replica ISR và controller quorum ổn định.
3. Chuẩn bị broker config tương thích trong thời gian mixed-version.
4. Nâng broker theo thứ tự và quy trình được release guide yêu cầu.
5. Theo dõi broker registration, leader movement, ISR, request errors và client latency.
6. Sau khi tất cả broker đã ở version đích, thực hiện bước finalize/upgrade metadata feature level nếu release guide yêu cầu.
7. Xác minh feature mới được bật và lưu rollback boundary.

Trong KRaft, metadata version/feature level quyết định metadata feature được phép sử dụng. Không tự động nâng metadata version ngay khi broker đầu tiên đã lên bản mới. Hãy chờ đúng điều kiện và thao tác finalize trong upgrade guide.

Các property tương thích giữa broker version, như inter-broker protocol hoặc metadata version, có semantics theo release. Không copy một giá trị từ runbook cũ sang phiên bản mới nếu release guide đã thay quy trình.

### Rollback boundary

Trước khi finalize metadata version hoặc bật feature không tương thích với binary cũ, xác định rõ có thể rollback về version nào. Sau khi metadata format/feature level đã được nâng, downgrade broker binary có thể không còn được hỗ trợ.

Lưu lại:
- Broker version trước/sau.
- Metadata version trước/sau.
- Config thay đổi.
- Topic/partition/ISR baseline.
- Snapshot/backup và restore procedure.
- Điểm cuối cùng có thể rollback an toàn.

## 15. Đánh giá Kafka Connect và connector plugin

Connect worker có version và lifecycle riêng. Một Kafka Connect worker có thể chạy với broker version khác trong giới hạn compatibility, nhưng connector plugin phụ thuộc API, converter và runtime classpath.

Audit các thành phần:

- Connector plugin version và vendor support matrix.
- `plugin.path` và thư viện phụ thuộc.
- Source/sink task count, offset storage và config/status storage topics.
- Converter (JSON, Avro, Protobuf, String, ByteArray).
- SMT và custom transformation.
- REST API automation.
- Worker configs và connector-level overrides.
- Error handling, DLQ và retry behavior.

Không nâng broker rồi giả định connector plugin sẽ tự tương thích. Test connector trên worker version đích với hệ thống nguồn/đích đại diện, đặc biệt các connector JDBC, Debezium, cloud storage và custom plugin.

## 16. Đánh giá Kafka Streams

Kafka Streams application thường được deploy độc lập với broker. Nâng broker không tự nâng thư viện Kafka Streams trong ứng dụng; nâng thư viện Streams cũng có thể thay đổi state store, topology optimization, metrics hoặc protocol behavior.

Kiểm tra:

- Kafka Streams library và `kafka-clients` version.
- State store changelog và repartition topics.
- `application.id`, `processing.guarantee` và transaction behavior.
- RocksDB version/native library nếu dùng.
- Serde/schema compatibility.
- Standby replica, task migration và restoration time.
- Interactive queries và custom state store.
- Metrics name/tag và alerting.
- Rebalance khi rolling deploy nhiều instance khác version.

Khi rolling deploy Streams app, cân nhắc mixed-version instance trong cùng `application.id`. Test task assignment, state restoration và transaction semantics trước khi triển khai rộng.

## 17. Kiểm thử changed default bằng test có kiểm soát

Đừng chỉ so sánh file config. Chạy cùng workload trên client version cũ và mới, cùng broker hoặc môi trường tương đương, rồi thay đổi một biến mỗi lần.

| Test | Đo lường |
|---|---|
| Producer low traffic | p50/p95/p99 send latency với linger cũ/mới |
| Producer high traffic | Throughput, batch size, request rate, compression ratio |
| Producer retry | Duplicate behavior, retry rate, delivery timeout |
| Producer ordering | Ordering per key/partition khi retry và nhiều in-flight request |
| Consumer poll | Processing time, poll cadence, max.poll.interval và rebalance |
| Consumer assignment | Rebalance duration, partition distribution, cooperative/eager behavior |
| Broker restart | Leader election, ISR recovery và client errors |
| Transactional producer | Commit/abort latency, transaction timeout, fencing |
| Connect | Task restart, offset continuity, DLQ và data correctness |
| Streams | State restoration, task migration, output correctness và lag |

Dùng cùng dataset, partition count, replication factor, compression, TLS, producer concurrency và consumer group count. Ghi lại cả average lẫn percentile; average tốt có thể che giấu p99 latency tăng.

## 18. Quy trình audit end-to-end trước khi nâng cấp

### Bước 1: đóng băng baseline

- Ghi lại broker/client/Connect/Streams/Java version.
- Export effective broker/topic configs.
- Ghi lại producer/consumer properties.
- Chụp baseline throughput, latency, error rate, consumer lag, ISR và controller quorum.
- Lưu các script/admin command đang dùng.

### Bước 2: đọc thay đổi từng release

- Tạo danh sách removed/deprecated/default/behavior changes.
- Ghi phiên bản xuất hiện và phiên bản bị loại bỏ (nếu có).
- Gắn owner cho từng service/plugin/config.
- Phân loại mức độ: blocker, high, medium, low.

### Bước 3: sửa code và config

- Thay API deprecated.
- Loại bỏ config/CLI option đã bị remove.
- Chuyển ZooKeeper dependency sang KRaft nếu target Kafka 4.0.
- Pin default quan trọng khi cần giữ behavior.
- Nâng JDK và framework theo compatibility matrix.

### Bước 4: kiểm thử trong staging

- Compile toàn bộ service và plugin.
- Chạy unit/integration test.
- Chạy benchmark producer/consumer.
- Test broker restart, controller failover và consumer rebalance.
- Kiểm tra Connect/Streams, schema và data correctness.
- Thử rollback theo đúng boundary.

### Bước 5: triển khai production

- Chọn maintenance window và batch/rolling strategy.
- Nâng theo thứ tự được hỗ trợ.
- Theo dõi SLO và cluster health sau mỗi bước.
- Chỉ finalize metadata/feature level khi đủ điều kiện.
- Lưu kết quả và cập nhật runbook.

## 19. Ví dụ compatibility matrix cho nâng cấp 3.x lên 4.0

Bảng sau là ví dụ định hướng cho một cluster đang dùng Kafka 3.x và dự kiến lên 4.0; phải xác minh minor version cụ thể trước khi áp dụng.

| Hạng mục | Trước nâng cấp | Mục tiêu Kafka 4.0 | Việc cần làm |
|---|---|---|---|
| Metadata mode | Có thể là ZooKeeper hoặc KRaft | KRaft bắt buộc | Nếu đang ZooKeeper, migrate trên release còn hỗ trợ trước khi nâng 4.0 |
| `zookeeper.connect` | Có trong broker config ZooKeeper | Không còn hỗ trợ | Chuyển topology sang KRaft và bỏ property cũ |
| CLI `--zookeeper` | Có ở tooling cũ | Không dùng được | Chuyển script sang `--bootstrap-server` |
| Broker Java runtime | Theo yêu cầu 3.x | Java 17 baseline cho broker/tooling | Nâng image/JDK và test agent |
| Producer idempotence | Có thể explicit false hoặc dựa default | Default hiện đại là true nếu không xung đột | Xác minh effective value và retry/ordering |
| Producer linger | Default trước 4.0 là 0 ms | Default 4.0 là 5 ms | Benchmark latency/batching; pin nếu cần |
| Consumer Java API | Có thể gọi `poll(long)` | API này deprecated; dùng Duration | Thay source và giữ đúng timeout |
| Connect/plugin | Theo worker/plugin version cũ | Cần version tương thích target | Test plugin, converter, SMT và REST automation |
| Streams | Library cũ | Library tương thích target | Test state restore, rebalance và transaction |
| Rollback | Phụ thuộc version/protocol/metadata | Có thể bị giới hạn sau finalize | Xác định rollback boundary và backup |

## 20. Những lỗi thường gặp khi audit upgrade

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra broker version | Client, Connect hoặc Streams không tương thích | Inventory toàn bộ runtime và dependency |
| Chỉ grep file properties | Bỏ sót config từ environment/framework/secret | Kiểm tra effective runtime properties |
| Coi deprecated là đã removed | Tạo migration không cần thiết hoặc sai deadline | Xác nhận trạng thái trong release đích |
| Coi changed default là config bị rewrite | Bỏ qua cấu hình explicit vẫn giữ nguyên | Phân biệt explicit config và default |
| Không kiểm tra producer linger.ms | Latency/batching đổi sau nâng client | Benchmark và pin theo SLO |
| Nâng Kafka 4.0 khi còn ZooKeeper | Cluster không thể chạy theo topology cũ | Migration KRaft trước upgrade |
| Dùng `poll(1000)` mà đổi thành 1000 giây | Consumer timeout sai nghiêm trọng | Chuyển đúng đơn vị sang Duration |
| Nâng client không theo framework support | Classpath conflict hoặc runtime incompatibility | Dùng compatibility matrix của framework |
| Finalize metadata version quá sớm | Mất đường rollback về binary cũ | Chỉ finalize khi đủ điều kiện |
| Không test connector/Streams | Task fail, state restore chậm hoặc data sai | Test plugin và app trên staging |
| Chỉ nhìn average latency | Bỏ sót p99 regression | So sánh percentile và error rate |

## 21. Checklist trước khi xác nhận sẵn sàng nâng cấp

**Inventory và compatibility**

- [ ] Đã ghi broker, client, Connect, Streams, Java và plugin version.
- [ ] Đã xác định source version và target version chính xác.
- [ ] Đã kiểm tra version hop được hỗ trợ và migration guide từng release.
- [ ] Đã có compatibility matrix cho framework/client/plugin.

**Removed/deprecated**

- [ ] Đã liệt kê tính năng/config/CLI option bị loại bỏ.
- [ ] Đã tìm ZooKeeper dependency nếu target Kafka 4.0.
- [ ] Đã tìm deprecated Java API và compiler warnings.
- [ ] Đã có owner và remediation cho từng mục.

**Changed defaults**

- [ ] Đã so sánh source/target defaults.
- [ ] Đã kiểm tra effective runtime properties.
- [ ] Đã đánh giá `enable.idempotence`, `acks` và `linger.ms`.
- [ ] Đã pin các giá trị quan trọng khi cần giữ behavior.
- [ ] Đã benchmark latency, throughput, batching và retry.

**Migration và rollback**

- [ ] KRaft migration hoàn tất trước khi nâng Kafka 4.0.
- [ ] Java runtime phù hợp với broker/tooling target.
- [ ] Connect/Streams/plugin đã test.
- [ ] Metadata version/feature level chỉ finalize đúng thời điểm.
- [ ] Backup, rollback boundary và recovery runbook đã được diễn tập.

**Production readiness**

- [ ] Staging integration test và load test PASS.
- [ ] Consumer lag, ISR, controller quorum và SLO có dashboard/alert.
- [ ] Có maintenance window và rolling plan.
- [ ] Có tiêu chí stop/rollback rõ ràng.
- [ ] Sau upgrade có đối chiếu dữ liệu, offset, transaction và connector state.

## 22. Ghi nhớ

Khi đánh giá upgrade Kafka, hãy phân biệt rõ tính năng đã bị loại bỏ, API/config deprecated, default thay đổi và behavior change. Removed cần thay thế trước khi nâng cấp; deprecated cần có lộ trình; changed default cần kiểm tra effective runtime value và benchmark tác động.

Các ví dụ cần nhớ: Kafka 4.0 yêu cầu KRaft và loại bỏ ZooKeeper mode, vì vậy cluster ZooKeeper phải migrate trước; producer `linger.ms` default tăng từ 0 lên 5 ms ở Kafka 4.0; idempotence producer mặc định bật trong dòng Kafka 3.0 hiện đại nếu không có cấu hình xung đột; Java Consumer nên dùng `poll(Duration)` thay overload `poll(long)` đã deprecated.

Một upgrade an toàn dựa trên version inventory, release notes, compatibility matrix, regression/benchmark test và rollback boundary. Không finalize metadata feature level hay triển khai rộng cho đến khi cluster, client, Connect, Streams và automation đều vượt qua các kiểm tra cần thiết.

## Tài liệu tham khảo

- [Apache Kafka – Upgrade Guide](https://kafka.apache.org/documentation/#upgrade)
- [Apache Kafka – Release Notes](https://kafka.apache.org/downloads)
- [Apache Kafka – KRaft](https://kafka.apache.org/documentation/#kraft)
- [Apache Kafka – Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka – Java API](https://kafka.apache.org/40/javadoc/)
- [Apache Kafka – Kafka Connect](https://kafka.apache.org/documentation/#connect)
- [Apache Kafka – Kafka Streams](https://kafka.apache.org/documentation/streams/)

