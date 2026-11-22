# Migration từ embedded broker cũ

Các dự án Spring Kafka cũ thường dùng embedded Kafka chạy cùng ZooKeeper thông qua `EmbeddedKafkaZKBroker` hoặc `EmbeddedKafkaRule`. Từ Spring Kafka 3.1, framework đã có embedded broker chạy KRaft. Đến Spring Kafka 4.0, Kafka 4.0 chỉ còn KRaft nên implementation ZooKeeper, dependency ZooKeeper và các API kiểm thử liên quan đã bị loại bỏ.

Migration cần rà soát cả cách tạo broker, JUnit rule, thuộc tính annotation, cấu hình port, broker properties và lifecycle test. Nếu chỉ nâng dependency mà giữ nguyên các API cũ, test sẽ lỗi biên dịch hoặc khởi động broker.

Bài này tập trung vào **embedded broker trong test** của Spring Kafka. Thay đổi embedded broker không tự động chuyển một Kafka cluster production từ ZooKeeper sang KRaft; đó là một quy trình nâng cấp cluster riêng.

## 1. Embedded broker cũ là gì?

Trước khi có KRaft embedded broker, `spring-kafka-test` khởi động một ZooKeeper nhúng cùng một hoặc nhiều Kafka broker nhúng. Implementation được dùng là `EmbeddedKafkaZKBroker`.

Một số dự án tạo broker trực tiếp:

```java
EmbeddedKafkaBroker broker =
    new EmbeddedKafkaZKBroker(1, false, 1, "orders");
```

Một số dự án dùng JUnit 4 rule:

```java
@ClassRule
public static EmbeddedKafkaRule broker =
    new EmbeddedKafkaRule(1, false, "orders");
```

Hoặc dùng `@EmbeddedKafka` để đăng ký broker trong Spring Test context.

Với mô hình cũ, test có cả Kafka broker và ZooKeeper process. Broker cần ZooKeeper để lưu metadata cluster. KRaft thay cơ chế metadata này bằng quorum controller tích hợp trong Kafka.

## 2. Lộ trình version của Spring Kafka

Không phải mọi phiên bản 3.x đều có cùng hành vi. Hãy xác định version đang chạy trước khi đổi code.

| Spring Kafka | Embedded broker | Cách chọn chế độ |
|---|---|---|
| 2.x đến 3.0 | `EmbeddedKafkaZKBroker` | Embedded Kafka dùng ZooKeeper |
| 3.1 | Có thêm `EmbeddedKafkaKraftBroker` | Có thể tạo KRaft broker trực tiếp; KRaft broker không hỗ trợ JUnit 4 |
| 3.2 | Có cả ZooKeeper và KRaft | Dùng `@EmbeddedKafka(kraft = true)` để chọn KRaft |
| 3.3 | Có cả hai implementation | `@EmbeddedKafka` vẫn mặc định dùng ZooKeeper; đặt `kraft = true` để chuyển KRaft |
| 4.0 trở lên | Chỉ còn `EmbeddedKafkaKraftBroker` | KRaft là lựa chọn duy nhất; API ZooKeeper bị loại bỏ |

Các mốc quan trọng:

- Spring Kafka 3.1 giới thiệu `EmbeddedKafkaKraftBroker`.
- Spring Kafka 3.2 bổ sung thuộc tính `kraft` cho `@EmbeddedKafka`.
- Trong Spring Kafka 3.3, implementation ZooKeeper vẫn là mặc định của annotation.
- Spring Kafka 4.0 nâng cấp lên Kafka client 4.0 và loại bỏ toàn bộ chức năng ZooKeeper.

Vì vậy, nếu dự án đang ở 3.3 và muốn chuyển sớm, hãy bật KRaft tường minh. Khi lên 4.0, phải xóa các tham chiếu ZooKeeper và thuộc tính lựa chọn KRaft vì KRaft đã là mặc định duy nhất.

## 3. Phân biệt migration test với migration Kafka production

Hai việc có liên quan đến KRaft nhưng khác phạm vi:

| Nội dung | Embedded broker migration | Production cluster migration |
|---|---|---|
| Mục tiêu | Chạy test bằng broker KRaft | Chuyển metadata cluster từ ZooKeeper sang KRaft |
| Thành phần thay đổi | Dependency test, class, annotation, JUnit, broker properties | Broker/controller, metadata, quorum, cấu hình cluster |
| Dữ liệu | Thường là dữ liệu test có thể tạo lại | Phải bảo toàn dữ liệu và metadata cluster |
| Có thể thay bằng đổi annotation? | Có thể, nếu test chỉ dùng embedded broker | Không |
| Công cụ/quy trình | Spring Kafka Test và JUnit | Quy trình ZooKeeper-to-KRaft migration của Apache Kafka |

Kafka 4.0 không còn hỗ trợ ZooKeeper mode. Cluster production đang chạy ZooKeeper phải được migrate sang KRaft trước khi nâng broker lên Kafka 4.0. Apache Kafka nêu điều kiện upgrade broker 4.0 từ các bản 3.3.x–3.9.x và yêu cầu metadata/software version phù hợp. Không dùng bài migration embedded broker này làm runbook chuyển cluster production.

`EmbeddedKafkaKraftBroker` chạy broker và controller trong combined mode. Nó phù hợp kiểm tra protocol Kafka và tích hợp Spring, nhưng không mô phỏng đầy đủ quorum controller nhiều node, network topology, ACL/TLS production hoặc lỗi node trong cluster. Với các tình huống đó, dùng Kafka container/cluster test riêng.

## 4. Kiểm tra dự án trước khi sửa

Tìm các tham chiếu cũ trong test source và cấu hình:

```bash
rg -n "EmbeddedKafkaZKBroker|EmbeddedKafkaRule|SPRING_EMBEDDED_ZOOKEEPER_CONNECT|zookeeperPort|zkConnectionTimeout|zkSessionTimeout|kraft" src/test pom.xml build.gradle*
```

Nếu dùng PowerShell không có `rg`, có thể tìm bằng:

```powershell
Get-ChildItem -Recurse src/test |
    Select-String -Pattern 'EmbeddedKafkaZKBroker|EmbeddedKafkaRule|SPRING_EMBEDDED_ZOOKEEPER_CONNECT|zookeeperPort|zkConnectionTimeout|zkSessionTimeout|kraft'
```

Rà soát các vị trí sau:

- Import `EmbeddedKafkaZKBroker`.
- Khởi tạo `new EmbeddedKafkaZKBroker(...)`.
- JUnit 4 `EmbeddedKafkaRule`, `@ClassRule` hoặc `@Rule`.
- Thuộc tính `kraft` trong annotation hoặc global embedded broker.
- Thuộc tính ZooKeeper như `zookeeperPort`, `zkConnectionTimeout`, `zkSessionTimeout`.
- Constant `SPRING_EMBEDDED_ZOOKEEPER_CONNECT`.
- Broker property hoặc system property có tên `zookeeper.*`.
- Test giả định Kafka broker dùng port cố định.
- Dependency ZooKeeper được khai báo trực tiếp chỉ để phục vụ embedded test.

Đọc dependency tree để xác định version thực tế của `spring-kafka`, `spring-kafka-test` và `kafka-clients`. Không chỉ dựa vào version khai báo trong file build vì Spring Boot BOM có thể quản lý version khác.

## 5. Chuyển @EmbeddedKafka từ ZooKeeper sang KRaft

### Trước migration: Spring Kafka 3.3 dùng ZooKeeper

Một test cũ có thể khai báo:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders"
)
class OrderKafkaIntegrationTest {
    // EmbeddedKafkaZKBroker được tạo mặc định.
}
```

Trong Spring Kafka 3.3, nếu muốn giữ cấu hình annotation nhưng chuyển broker sang KRaft, thêm `kraft = true`:

```java
@SpringBootTest
@EmbeddedKafka(
    kraft = true,
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {
    // EmbeddedKafkaKraftBroker được tạo.
}
```

Có thể inject interface `EmbeddedKafkaBroker` như trước:

```java
@Autowired
EmbeddedKafkaBroker embeddedKafka;
```

Nên inject interface thay vì implementation cụ thể để test ít phụ thuộc vào loại broker.

### Sau migration: Spring Kafka 4.x

Trong Spring Kafka 4.0 trở lên, bỏ `kraft = true` vì annotation không còn thuộc tính này:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;
}
```

Từ Spring Kafka 3.0.10, `bootstrapServersProperty` mặc định đã là `spring.kafka.bootstrap-servers`. Có thể bỏ thuộc tính này nếu dự án dùng default và không cần thể hiện rõ cấu hình:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders"
)
class OrderKafkaIntegrationTest {
}
```

Khi dùng Spring Boot, property này cho phép `KafkaTemplate`, consumer factory và listener container tự động kết nối đến broker ngẫu nhiên được tạo cho test.

## 6. Chuyển từ EmbeddedKafkaZKBroker sang EmbeddedKafkaKraftBroker

Một số test hoặc test fixture tự tạo broker bằng constructor. Khi đó cần đổi class và chữ ký constructor.

### Cách cũ

```java
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.EmbeddedKafkaZKBroker;

EmbeddedKafkaBroker broker =
    new EmbeddedKafkaZKBroker(
        1,
        false,
        1,
        "orders"
    );

broker.afterPropertiesSet();
```

Constructor cũ nhận số broker, `controlledShutdown`, số partition và topic.

### Cách mới

```java
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.EmbeddedKafkaKraftBroker;

EmbeddedKafkaBroker broker =
    new EmbeddedKafkaKraftBroker(
        1,
        1,
        "orders"
    );

broker.afterPropertiesSet();
```

KRaft constructor nhận số broker, số partition và danh sách topic. Tham số `controlledShutdown` của implementation ZooKeeper không còn trong constructor KRaft.

Nếu fixture tự quản lý lifecycle, phải gọi `destroy()` khi suite hoàn tất. Trong Spring Test context, ưu tiên để Spring quản lý bean lifecycle thay vì tự gọi `afterPropertiesSet()` và `destroy()` nhiều lần.

Đoạn code trên minh họa API constructor. Trong phần lớn test Spring, `@EmbeddedKafka` là cách khai báo gọn hơn và giúp framework quản lý lifecycle.

## 7. Chuyển JUnit 4 EmbeddedKafkaRule sang JUnit Jupiter

`EmbeddedKafkaRule` là wrapper JUnit 4 dành cho `EmbeddedKafkaZKBroker`. KRaft embedded broker không hỗ trợ JUnit 4. Spring Kafka 4.0 đã loại bỏ `EmbeddedKafkaRule` cùng hỗ trợ JUnit 4.

### Cách cũ: JUnit 4

```java
@RunWith(SpringRunner.class)
@SpringBootTest
public class OrderKafkaIntegrationTest {

    @ClassRule
    public static EmbeddedKafkaRule broker =
        new EmbeddedKafkaRule(1, false, "orders");

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Test
    public void sendsOrder() {
        // Test gửi message.
    }
}
```

### Cách mới: JUnit Jupiter

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders"
)
class OrderKafkaIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void sendsOrder() {
        // Test gửi message.
    }
}
```

Các thay đổi chính:

| JUnit 4 | JUnit Jupiter / Spring Kafka mới |
|---|---|
| `@RunWith(SpringRunner.class)` | Spring Boot test dùng `@SpringBootTest`; test Spring thuần dùng `@ExtendWith(SpringExtension.class)` hoặc `@SpringJUnitConfig` |
| `@ClassRule` | `@EmbeddedKafka` ở cấp class |
| `EmbeddedKafkaRule` | `EmbeddedKafkaBroker` do Spring quản lý |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before`, `@After` | `@BeforeEach`, `@AfterEach` |
| `@BeforeClass`, `@AfterClass` | `@BeforeAll`, `@AfterAll` |

Nếu test cần truy cập địa chỉ broker, inject `EmbeddedKafkaBroker`:

```java
@Autowired
EmbeddedKafkaBroker embeddedKafka;

@Test
void brokerIsAvailable() {
    String bootstrapServers = embeddedKafka.getBrokersAsString();

    assertThat(bootstrapServers).isNotBlank();
}
```

Không giữ `EmbeddedKafkaRule` trong code chỉ để chạy test với JUnit 4 khi đã nâng lên Spring Kafka 4.x.

## 8. Loại bỏ thuộc tính ZooKeeper trong @EmbeddedKafka

Spring Kafka 4.0 loại bỏ các thuộc tính annotation chỉ dành cho ZooKeeper:

- `zookeeperPort`
- `zkConnectionTimeout`
- `zkSessionTimeout`
- `kraft`

Ví dụ cấu hình cũ:

```java
@EmbeddedKafka(
    kraft = true,
    zookeeperPort = 0,
    zkConnectionTimeout = 20_000,
    zkSessionTimeout = 20_000,
    topics = "orders"
)
```

Cấu hình Spring Kafka 4.x:

```java
@EmbeddedKafka(
    topics = "orders",
    partitions = 1
)
```

Không thay các thuộc tính ZooKeeper bằng một thuộc tính KRaft tương đương. KRaft embedded broker quản lý controller/broker nội bộ và không khởi động ZooKeeper process.

Các cấu hình client như `bootstrap.servers`, serializer, deserializer, consumer group và listener concurrency vẫn được dùng theo cách thông thường. Chúng không phải cấu hình ZooKeeper.

## 9. Xử lý system property và constant ZooKeeper đã bị loại bỏ

Với embedded broker ZooKeeper, test có thể đọc:

```java
String zookeeperConnect =
    System.getProperty(
        EmbeddedKafkaBroker.SPRING_EMBEDDED_ZOOKEEPER_CONNECT
    );
```

Hoặc tham chiếu constant `SPRING_EMBEDDED_ZOOKEEPER_CONNECT`.

Khi chuyển sang Spring Kafka 4.x, bỏ logic này. Embedded KRaft broker không cung cấp ZooKeeper connect string.

Nếu ứng dụng test chỉ cần kết nối Kafka, dùng:

```java
String bootstrapServers = embeddedKafka.getBrokersAsString();
```

Hoặc dùng property được broker công bố:

```java
import org.springframework.beans.factory.annotation.Value;

@Value("${spring.kafka.bootstrap-servers}")
String bootstrapServers;
```

System property mặc định `spring.embedded.kafka.brokers` vẫn đại diện cho địa chỉ Kafka broker. Không nhầm nó với property ZooKeeper đã bị loại bỏ.

## 10. Chuyển global embedded broker sang KRaft

Spring Kafka 3.x cung cấp `GlobalEmbeddedKafkaTestExecutionListener` cho JUnit Platform. Tính năng này mặc định tắt.

Trong Spring Kafka 3.3, nếu dùng global broker và muốn chọn KRaft, có thể đặt:

```properties
spring.kafka.global.embedded.enabled=true
spring.kafka.embedded.kraft=true
spring.kafka.embedded.topics=orders
spring.kafka.embedded.partitions=1
```

Property `spring.kafka.embedded.kraft` chọn `EmbeddedKafkaKraftBroker` thay cho implementation ZooKeeper trong các version có hỗ trợ.

Khi chuyển sang Spring Kafka 4.x:

```properties
spring.kafka.global.embedded.enabled=true
spring.kafka.embedded.topics=orders
spring.kafka.embedded.partitions=1
```

Bỏ `spring.kafka.embedded.kraft` vì KRaft là implementation duy nhất. Không còn lựa chọn ZooKeeper để chuyển đổi.

Không kết hợp global embedded broker và `@EmbeddedKafka` theo từng test class trong cùng một suite nếu chưa có thiết kế lifecycle rõ ràng. Cả hai chia sẻ system properties và có thể ghi đè địa chỉ broker của nhau.

## 11. Điều chỉnh test phụ thuộc port cố định

Một khác biệt quan trọng của KRaft embedded broker là không hỗ trợ cấu hình custom Kafka ports như implementation ZooKeeper cũ.

Nếu test từng gọi:

```java
new EmbeddedKafkaZKBroker(1, false, "orders")
    .kafkaPorts(19092);
```

thì không thể giữ nguyên giả định port cố định khi chuyển sang KRaft embedded broker.

Hãy dùng địa chỉ động do broker trả về:

```java
String bootstrapServers = embeddedKafka.getBrokersAsString();
```

Với Spring Boot, để broker ghi địa chỉ vào `spring.kafka.bootstrap-servers`:

```java
@EmbeddedKafka(
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@SpringBootTest
class OrderKafkaIntegrationTest {
}
```

Nếu một tiến trình bên ngoài JVM cần kết nối đến broker bằng port cố định, embedded KRaft có thể không phải công cụ phù hợp. Hãy dùng Kafka container hoặc broker test riêng với port mapping có thể kiểm soát.

Không hard-code `localhost:9092` trong test khi broker được khởi động bằng port ngẫu nhiên.

## 12. Kiểm tra broker properties và replication factor

KRaft không dùng ZooKeeper, do đó loại bỏ các broker properties chỉ dành cho ZooKeeper như:

- `zookeeper.connect`
- `zookeeper.connection.timeout.ms`
- `zookeeper.session.timeout.ms`
- Các cấu hình ZooKeeper client authentication/SSL chỉ phục vụ kết nối ZooKeeper.

Các cấu hình Kafka broker và topic khác vẫn có thể cần thiết. Tuy nhiên, test phải phù hợp với số broker thực tế.

Với embedded broker một node:

- Replication factor của topic test phải không lớn hơn số broker.
- Nếu test transaction, internal transaction state topic phải dùng replication factor phù hợp với broker đơn.
- Không mang nguyên cấu hình replication factor của production cluster nhiều node vào test một node.
- Khi test nhiều broker embedded, kiểm tra số broker và min ISR trước khi đặt replication factor.

Ví dụ một broker cho transaction test:

```java
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1"
    }
)
@SpringBootTest
class TransactionalKafkaIntegrationTest {
}
```

Các broker properties chỉ nên được thêm khi test thực sự dùng transaction. Không cần cấu hình mọi internal topic cho test producer/consumer đơn giản.

## 13. Ví dụ integration test sau migration

Một test cơ bản có thể giữ nguyên logic gửi/nhận; phần thay đổi chủ yếu là embedded broker và JUnit.

Listener test:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderTestListener {

    private final BlockingQueue<String> received =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "orders-test-listener",
        topics = "orders",
        groupId = "orders-test-group"
    )
    public void listen(String payload) {
        received.add(payload);
    }

    public BlockingQueue<String> received() {
        return received;
    }
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    OrderTestListener listener;

    @Test
    void publishesAndConsumesOrder() throws Exception {
        kafkaTemplate.send(
            "orders",
            "order-42",
            "ORDER_CREATED"
        ).get(10, TimeUnit.SECONDS);

        String received =
            listener.received().poll(10, TimeUnit.SECONDS);

        assertThat(received).isEqualTo("ORDER_CREATED");
    }
}
```

Để tránh test phụ thuộc vào timing, trong suite thực tế nên chờ listener assignment trước khi gửi record, dùng topic/group cô lập và timeout hữu hạn. Đây là nguyên tắc kiểm thử Kafka nói chung, không phải thay đổi riêng của KRaft.

## 14. Quản lý lifecycle và Spring Test context

`EmbeddedKafkaBroker` triển khai lifecycle interface của Spring. Khi broker được đăng ký qua `@EmbeddedKafka` trong Spring Test context, hãy để Spring quản lý khởi tạo và hủy broker.

Nếu test tạo broker thủ công:

- Khởi tạo một lần trong fixture phù hợp.
- Không gọi `afterPropertiesSet()` lặp lại trên cùng instance.
- Gọi `destroy()` khi tất cả test dùng broker đã hoàn tất.
- Đóng producer/consumer do test tự tạo.
- Không để broker chạy sót trong Gradle daemon hoặc Maven Surefire fork.

Với `@EmbeddedKafka` kết hợp `@SpringJUnitConfig`, cần cân nhắc `@DirtiesContext` khi suite gặp race lúc JVM shutdown. Điều này giúp Spring đóng application context trước khi broker và temporary directory bị dọn dẹp. Không thêm annotation máy móc cho mọi test vì context sẽ bị tạo lại và suite có thể chậm hơn.

Dùng topic riêng cho từng test nếu có thể. Nếu tái sử dụng topic, xác định rõ consumer seek về đầu hay cuối partition; embedded broker helper có thể seek về đầu theo mặc định.

## 15. Những lỗi thường gặp sau migration

| Lỗi/hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `cannot find symbol EmbeddedKafkaZKBroker` | Spring Kafka 4.0 đã xóa class | Chuyển sang `EmbeddedKafkaKraftBroker` hoặc inject `EmbeddedKafkaBroker` |
| `cannot find symbol EmbeddedKafkaRule` | JUnit 4 rule đã bị loại bỏ | Chuyển sang JUnit Jupiter và `@EmbeddedKafka` |
| `kraft()` không tồn tại | Annotation 4.x không còn thuộc tính `kraft` | Xóa thuộc tính; KRaft là mặc định |
| Không tìm thấy `zookeeperPort` hoặc `zkSessionTimeout` | ZooKeeper annotation properties đã bị xóa | Xóa cấu hình ZooKeeper |
| Không resolve được `SPRING_EMBEDDED_ZOOKEEPER_CONNECT` | Constant ZooKeeper không còn | Dùng `getBrokersAsString()` hoặc bootstrap servers property |
| Broker không bind port đã chọn | KRaft embedded broker không hỗ trợ custom port | Dùng port động hoặc Kafka container |
| Topic creation thất bại vì replication factor | Replication factor lớn hơn số broker test | Điều chỉnh topic/internal topic replication theo broker count |
| Test treo sau khi nâng version | Listener chưa được assign hoặc client dùng sai bootstrap property | Chờ assignment và kiểm tra `spring.kafka.bootstrap-servers` |
| Test chạy không ổn định giữa các class | Global broker và per-class broker cùng ghi system property | Chọn một chiến lược lifecycle cho suite |
| Test compile nhưng lỗi runtime do Kafka client | `kafka-clients` bị override lệch với Spring Kafka | Dùng dependency management/BOM tương thích |

Khi gặp lỗi compile, tìm class/property đã bị xóa trước khi sửa test logic. Khi test compile nhưng không kết nối được broker, kiểm tra bootstrap servers, lifecycle và port trước khi điều tra listener.

## 16. Lộ trình migration theo từng bước

Thực hiện migration trong một nhánh thay đổi có thể review:

1. Ghi nhận version Spring Boot, Spring Kafka, `spring-kafka-test` và Kafka client đang dùng.
2. Tìm tất cả tham chiếu đến `EmbeddedKafkaZKBroker`, `EmbeddedKafkaRule` và ZooKeeper properties.
3. Nếu đang ở Spring Kafka 3.3, thêm `kraft = true` vào `@EmbeddedKafka` để chuyển test sang KRaft trước.
4. Chuyển JUnit 4 Rule sang JUnit Jupiter nếu suite còn dùng JUnit 4.
5. Thay direct constructor `EmbeddedKafkaZKBroker` bằng `EmbeddedKafkaKraftBroker`, hoặc tốt hơn là dùng interface `EmbeddedKafkaBroker` và annotation.
6. Thay port cố định bằng bootstrap address động.
7. Xóa ZooKeeper constants và properties khỏi test.
8. Nếu dùng global broker trên 3.x, bật `spring.kafka.embedded.kraft=true`; khi lên 4.x thì xóa property này.
9. Kiểm tra replication factor và broker properties của test.
10. Nâng Spring Kafka theo dependency management tương thích với Spring Boot và Kafka client.
11. Chạy toàn bộ test suite, đặc biệt test producer/listener, transaction, retry/DLT và test có nhiều broker.
12. Chỉ xóa dependency ZooKeeper trực tiếp nếu dependency đó không còn được dùng ở phần khác của dự án.

Nếu cần nâng Kafka cluster production lên 4.x, tạo một kế hoạch migration cluster riêng. Không thực hiện thao tác thay đổi metadata cluster trong bước migration test này.

## 17. Kiểm tra sau khi chuyển sang KRaft

Một migration hoàn tất cần xác minh hành vi test, không chỉ xác minh compile.

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Test context khởi động | Spring tạo được `EmbeddedKafkaBroker` |
| Bootstrap property | Kafka client kết nối đúng broker address động |
| Producer send | Record được broker xác nhận |
| Listener receive | Listener nhận đúng key/value/header |
| Topic/partition | Topic được tạo với số partition mong muốn |
| Consumer group | Listener được assign và commit offset theo cấu hình |
| Transaction test | Transaction commit/rollback hoạt động với internal topic replication phù hợp |
| Retry/DLT test | Error handler và DLT vẫn hoạt động |
| Lifecycle | Broker được đóng sau test suite |
| CI | Test chạy được trong môi trường CI mà không phụ thuộc ZooKeeper service bên ngoài |

Nếu test suite có cả embedded broker và Testcontainers, giữ ranh giới rõ ràng: test nào dùng broker nhúng, test nào cần container. Không để cùng một test class vô tình đọc bootstrap servers từ hai nguồn khác nhau.

## 18. Checklist trước khi nâng lên Spring Kafka 4

- Không còn import `EmbeddedKafkaZKBroker`.
- Không còn `EmbeddedKafkaRule`, `@ClassRule` hoặc JUnit 4 runner cho embedded broker.
- Không còn tham chiếu `SPRING_EMBEDDED_ZOOKEEPER_CONNECT`.
- Không còn `zookeeperPort`, `zkConnectionTimeout`, `zkSessionTimeout`.
- Không còn thuộc tính annotation `kraft`.
- Không còn global property `spring.kafka.embedded.kraft`.
- Test dùng `EmbeddedKafkaBroker` interface hoặc `EmbeddedKafkaKraftBroker`.
- Test dùng JUnit Jupiter.
- Broker address được đọc động, không hard-code port.
- Replication factor phù hợp số embedded broker.
- Kafka client version được quản lý tương thích với Spring Kafka.
- Test transaction, listener, retry và DLT chạy qua embedded KRaft.
- Lifecycle broker và Spring context được đóng đúng.
- CI không cần một ZooKeeper service riêng để chạy embedded Kafka test.

## 19. Ghi nhớ

- `EmbeddedKafkaZKBroker` là implementation embedded Kafka cũ có ZooKeeper.
- `EmbeddedKafkaKraftBroker` được giới thiệu từ Spring Kafka 3.1.
- Spring Kafka 3.2 cho phép chọn KRaft bằng `@EmbeddedKafka(kraft = true)`.
- Spring Kafka 3.3 vẫn mặc định dùng ZooKeeper cho `@EmbeddedKafka` nếu không bật `kraft`.
- Spring Kafka 4.0 chỉ còn KRaft, xóa `EmbeddedKafkaZKBroker`, `EmbeddedKafkaRule`, ZooKeeper dependency và các thuộc tính ZooKeeper.
- KRaft embedded broker không hỗ trợ custom Kafka ports; hãy lấy địa chỉ bằng `getBrokersAsString()` hoặc bootstrap property.
- Inject `EmbeddedKafkaBroker` interface giúp giảm phụ thuộc vào implementation.
- Migration embedded broker không phải migration Kafka production cluster.
- Test phải xác minh producer, listener, assignment, transaction và lifecycle sau khi đổi broker.

Chuyển embedded broker từ ZooKeeper sang KRaft giúp bộ kiểm thử Spring Kafka tương thích với hướng phát triển của Apache Kafka. Khi xử lý đúng các thay đổi về API, JUnit, annotation, port và lifecycle, test suite vẫn kiểm tra được luồng messaging mà không phụ thuộc ZooKeeper.

## Tài liệu tham khảo

- [Spring Kafka 3.3 – Testing Applications](https://docs.spring.io/spring-kafka/reference/3.3/testing.html)
- [Spring Kafka 4.1 – Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [EmbeddedKafkaKraftBroker API](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/test/EmbeddedKafkaKraftBroker.html)
- [EmbeddedKafkaZKBroker API](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/test/EmbeddedKafkaZKBroker.html)
- [Apache Kafka – Upgrading to 4.0](https://kafka.apache.org/40/getting-started/upgrade/)
- [Apache Kafka – KRaft vs ZooKeeper](https://kafka.apache.org/44/getting-started/zk2kraft/)


