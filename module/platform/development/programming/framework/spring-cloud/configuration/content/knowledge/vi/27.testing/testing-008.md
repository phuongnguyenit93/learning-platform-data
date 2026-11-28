# Dùng Testcontainers cho broker, Vault, Consul hoặc Zookeeper

Spring Cloud Config thường tích hợp với các hệ thống bên ngoài: Git hoặc secret store làm nguồn cấu hình, Consul/ZooKeeper cung cấp service discovery hay KV, RabbitMQ/Kafka vận chuyển Spring Cloud Bus event. Unit test có thể kiểm tra binding và logic bằng mock, nhưng không chứng minh ứng dụng tương tác đúng với giao thức, authentication, port mapping hoặc phiên bản dịch vụ thật.

**Testcontainers** cho phép kiểm thử tích hợp bằng cách khởi động dependency thật trong container dùng riêng cho test, cấp endpoint động cho Spring Boot rồi hủy container sau khi hoàn tất. Cách này giúp kiểm tra đường đi thực tế của cấu hình và message mà vẫn giữ môi trường test có thể tái tạo, cô lập và không phụ thuộc vào một dịch vụ dùng chung lâu dài.

## 1. Khi nào cần Testcontainers?

Nên dùng Testcontainers khi kết quả kiểm thử phụ thuộc vào hành vi thực của một hệ thống bên ngoài:

- RabbitMQ/Kafka: exchange, queue/topic, consumer group, acknowledgment, retry và delivery.
- Vault: KV engine, path, policy, token, lease và phản hồi lỗi quyền truy cập.
- Consul: KV path, ACL, service registration và Config Client integration.
- ZooKeeper: namespace, znode, ACL, connection session và context lookup.
- Config Server/Git: HTTP response, application/profile/label, clone/fetch và revision metadata.

Mock hữu ích để kiểm tra logic đơn vị và lỗi có thể mô phỏng dễ dàng. Nhưng mock không thể phát hiện sai tên queue, khác biệt API giữa các phiên bản server, lỗi TLS, quyền ACL thiếu hoặc một client gửi request tới sai port. Testcontainers bổ sung lớp kiểm thử với dịch vụ thật.

| Loại test | Dependency | Mục tiêu |
| --- | --- | --- |
| Unit test | Mock/stub | Logic nghiệp vụ, mapping và nhánh xử lý |
| Binding test | Spring context nhỏ | `@ConfigurationProperties`, conversion, validation |
| Integration test | Testcontainers | Giao tiếp thật với broker, Vault, Consul, ZooKeeper hoặc Config Server |
| End-to-end/staging | Hệ thống triển khai gần production | Luồng nhiều service, network policy, TLS, HA và vận hành |

Testcontainers không thay thế test đơn vị. Chỉ đưa những dependency cần thiết vào container để mỗi test vẫn nhanh và có mục tiêu rõ ràng.

## 2. Dependency và môi trường chạy

Với JUnit 5, dependency cốt lõi là Testcontainers JUnit Jupiter. Các module chuyên biệt có thể cung cấp container class cho một số dịch vụ; nếu module hoặc API không có trong phiên bản đang dùng, có thể dùng `GenericContainer` với image chính thức.

Ví dụ Maven với BOM và JUnit Jupiter:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>${testcontainers.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>rabbitmq</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Ví dụ Gradle:

```kotlin
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:$testcontainersVersion"))
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:rabbitmq")
}
```

Quản lý phiên bản Testcontainers bằng một BOM để các module dùng cùng dòng. Artifact và package của module chuyên biệt có thể thay đổi theo major version; xác nhận với tài liệu của đúng phiên bản đã khóa trong dự án. Không kéo phiên bản mới nhất riêng lẻ vào một dự án đang dùng Spring Boot/Spring Cloud cũ mà chưa kiểm tra tương thích.

Testcontainers cần một Docker-compatible container runtime có thể truy cập từ tiến trình test, ví dụ Docker Engine hoặc môi trường tương thích được hỗ trợ. Trong CI, runner phải có quyền kết nối tới daemon/socket hoặc endpoint runtime. Nếu không có runtime, test cần được đánh dấu/skip theo cấu hình môi trường rõ ràng; không biến lỗi thiếu Docker thành một test pass giả.

## 3. Vòng đời container với JUnit 5

JUnit Jupiter extension quản lý container qua `@Testcontainers` và `@Container`:

```java
@Testcontainers
class BrokerIntegrationTests {

    @Container
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse("rabbitmq:3.13-management"));

    @Test
    void brokerStarts() {
        assertThat(rabbit.isRunning()).isTrue();
    }
}
```

- Container field `static` được khởi động một lần cho class test và dừng sau class.
- Container field không `static` được khởi động/dừng theo vòng đời từng test method.
- Container dùng chung giúp tiết kiệm thời gian, nhưng test phải cô lập dữ liệu và queue/key để không phụ thuộc thứ tự chạy.
- Container riêng cho từng test tăng isolation nhưng làm suite chậm hơn.

Chọn vòng đời theo loại dữ liệu. Nếu test thay đổi cấu hình broker, xóa KV path hoặc tạo policy Vault, cần cleanup rõ ràng hoặc container riêng để test không ảnh hưởng nhau.

## 4. Cấp endpoint động cho Spring Boot

Testcontainers thường ánh xạ port trong container sang một host port ngẫu nhiên. Không hard-code `localhost:5672`, `8200`, `8500` hoặc `2181` vì host port có thể thay đổi giữa các lần chạy và giữa các máy.

`@DynamicPropertySource` đăng ký giá trị runtime vào Spring `Environment`:

```java
@Testcontainers
@SpringBootTest
class BillingMessagingIntegrationTests {

    @Container
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse("rabbitmq:3.13-management"));

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }
}
```

Các giá trị được lấy sau khi container khởi động. Với các dịch vụ khác, có thể đăng ký tương tự:

| Dịch vụ | Thuộc tính Spring thường cần cấp |
| --- | --- |
| RabbitMQ | `spring.rabbitmq.host`, `spring.rabbitmq.port`, username/password |
| Kafka | `spring.kafka.bootstrap-servers` |
| Vault | `spring.cloud.vault.uri`, token/authentication properties |
| Consul | `spring.cloud.consul.host`, `spring.cloud.consul.port` |
| ZooKeeper | `spring.cloud.zookeeper.connect-string` |

Một số Spring Boot version hỗ trợ `@ServiceConnection` cho các loại container được nhận diện. Khi container/module có service connection factory tương thích, annotation này có thể tự cung cấp `ConnectionDetails` cho auto-configuration. Không phải mọi `GenericContainer` hoặc mọi Spring Cloud integration đều có service connection tự động; `@DynamicPropertySource` vẫn là cách tường minh và phổ biến.

**Lưu ý về Config Data import:** `spring.config.import` được xử lý rất sớm trong quá trình chuẩn bị `Environment`. Nếu địa chỉ container cần thiết để resolver tìm location, hãy bảo đảm giá trị import location có sẵn trước giai đoạn Config Data resolution. Có thể truyền qua thuộc tính test/system property được thiết lập trước khi Spring Boot khởi động hoặc dùng initializer phù hợp với phiên bản; không giả định mọi dynamic property được thêm sau đó đều có thể thay đổi một import đã được xử lý.

## 5. Kiểm thử RabbitMQ cho Spring Cloud Bus

RabbitMQ là broker thường dùng với Spring Cloud Bus. Test có thể khởi động container, cấp host/port và xác minh producer/consumer thực sự trao đổi được message.

Ví dụ cấu hình test:

```java
@Testcontainers
@SpringBootTest
class BusRabbitIntegrationTests {

    @Container
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse("rabbitmq:3.13-management"));

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
        registry.add("spring.cloud.bus.enabled", () -> "true");
    }

    @Test
    void applicationConnectsToRealBroker() {
        assertThat(rabbit.isRunning()).isTrue();
        // Assert bean/health của integration thực tế trong ứng dụng.
    }
}
```

Để kiểm tra Bus đầy đủ, không chỉ assert container đang chạy. Nên kiểm tra:

1. Ứng dụng tạo được kết nối tới broker.
2. Exchange/queue hoặc topology cần thiết được tạo.
3. Một instance phát refresh event hoặc message thử nghiệm.
4. Consumer nhận được event trong thời gian giới hạn.
5. Event đi tới đúng destination và không bị xử lý lặp gây side effect.
6. Khi broker dừng hoặc kết nối bị ngắt, ứng dụng ghi nhận lỗi và phục hồi theo chính sách retry/reconnect.

Nếu kiểm thử `/actuator/busrefresh`, cần bật endpoint và cấu hình Spring Cloud Bus trong test application. Response HTTP thành công từ endpoint phát event không chứng minh mọi consumer đã refresh; test nên quan sát kết quả ở consumer hoặc revision của từng client.

## 6. Kiểm thử Kafka broker

Nếu production dùng Kafka, hãy test bằng Kafka broker thật thay vì giả định RabbitMQ và Kafka có cùng semantics. Khác biệt về topic, partition, consumer group, offset, acknowledgment và redelivery có thể ảnh hưởng cách Bus event được phân phối.

Testcontainers có module Kafka trong các phiên bản tương ứng. Ví dụ khái quát:

```java
@Testcontainers
class KafkaIntegrationTests {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer(
                    DockerImageName.parse("apache/kafka-native:3.8.0"));

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.kafka.bootstrap-servers",
                kafka::getBootstrapServers);
    }
}
```

Package/class và image compatibility của Kafka container phụ thuộc Testcontainers major version. Với một số dòng cũ, API có thể dùng package khác hoặc image Confluent; hãy theo đúng module documentation và cấu hình compatibility strategy của phiên bản đang dùng.

Các test nên tạo topic/consumer group riêng theo test run, chờ consumer assignment bằng điều kiện có giới hạn và kiểm tra message key/payload/correlation ID. Tránh dùng `Thread.sleep` cố định để chờ consumer vì làm test chậm và dễ flaky; dùng Awaitility hoặc polling assertion với timeout rõ ràng.

## 7. Kiểm thử Vault bằng container

Vault phù hợp để kiểm tra Spring Cloud Vault Config Data, KV path, token và policy. Có thể dùng Vault container chuyên biệt nếu module đang khóa cung cấp, hoặc `GenericContainer` với image Vault chính thức.

Ví dụ môi trường phát triển trong test bằng `GenericContainer`:

```java
static final String TEST_VAULT_TOKEN = "test-root-token";

@Container
static final GenericContainer<?> vault =
        new GenericContainer<>(DockerImageName.parse("hashicorp/vault:1.17"))
                .withExposedPorts(8200)
                .withEnv("VAULT_DEV_ROOT_TOKEN_ID", TEST_VAULT_TOKEN)
                .withEnv("VAULT_DEV_LISTEN_ADDRESS", "0.0.0.0:8200")
                .withCommand("server", "-dev")
                .waitingFor(Wait.forHttp("/v1/sys/health")
                        .forPort(8200)
                        .forStatusCode(200));
```

Lấy URI động:

```java
String vaultUri = "http://" + vault.getHost() + ":" +
        vault.getMappedPort(8200);
```

Dev mode sử dụng token đặc quyền và cấu hình không phù hợp production. Chỉ dùng token giả trong container test cô lập; không dùng Vault root token thật, không mount dữ liệu production và không mở cổng container ra mạng không tin cậy.

Một test Vault có thể kiểm tra:

- Config Client đọc đúng KV context/path.
- KV v1 hoặc KV v2 được cấu hình đúng với backend mount.
- Token có quyền `read` đúng path.
- Token thiếu policy bị từ chối.
- Secret được bind vào property mà không in plaintext ra log.
- Lease/renewal hoặc token renewal hoạt động theo cấu hình nếu ứng dụng sử dụng các tính năng đó.

Nếu test cần kiểm tra policy, hãy khởi tạo KV engine, secret và policy riêng trong container trước khi Spring context được tạo. Sau test, container bị hủy để loại bỏ dữ liệu thử nghiệm.

## 8. Kiểm thử Consul Config

Consul container cho phép kiểm tra KV context, profile và ACL với một Consul Agent thật. Có thể dùng module Consul chuyên biệt hoặc `GenericContainer`.

Ví dụ với Consul dev agent:

```java
@Container
static final GenericContainer<?> consul =
        new GenericContainer<>(DockerImageName.parse("hashicorp/consul:1.18"))
                .withExposedPorts(8500)
                .withCommand("agent", "-dev", "-client=0.0.0.0")
                .waitingFor(Wait.forHttp("/v1/status/leader")
                        .forPort(8500)
                        .forStatusCode(200));
```

Đăng ký endpoint:

```java
@DynamicPropertySource
static void consulProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.cloud.consul.host", consul::getHost);
    registry.add("spring.cloud.consul.port",
            () -> consul.getMappedPort(8500));
}
```

Consul dev mode thường tắt ACL và dùng cấu hình đơn giản để test. Nếu cần kiểm tra ACL, phải khởi động Consul với ACL enabled, bootstrap policy/token riêng và truyền token test vào ứng dụng. Không dùng dev mode để kết luận policy production an toàn.

Các ca test nên bao gồm:

- Ghi key vào `prefix/application,profile` và xác nhận Config Client đọc đúng.
- Kiểm tra default context và application-specific context có thứ tự ưu tiên mong muốn.
- Kiểm tra profile separator đúng với path.
- Kiểm tra missing key, optional import và lỗi ACL.
- Xác minh thay đổi KV được client nhận sau refresh theo chính sách của phiên bản.

## 9. Kiểm thử ZooKeeper Config

ZooKeeper container giúp kiểm tra znode path, context và ACL thực tế. Có thể dùng `ZookeeperContainer` nếu module Testcontainers đang dùng hỗ trợ, hoặc `GenericContainer` với image ZooKeeper.

Ví dụ:

```java
@Container
static final GenericContainer<?> zookeeper =
        new GenericContainer<>(DockerImageName.parse("zookeeper:3.9"))
                .withExposedPorts(2181)
                .withEnv("ZOO_4LW_COMMANDS_WHITELIST", "ruok")
                .waitingFor(Wait.forListeningPort());
```

`Wait.forListeningPort()` chỉ xác nhận port client đã mở, chưa chứng minh session ZooKeeper có thể được thiết lập. Sau khi container start, nên dùng chính ZooKeeper client/Curator của ứng dụng để kết nối và chờ trạng thái `SyncConnected` trong một timeout hữu hạn. Nếu image cung cấp health check hoặc log startup đáng tin cậy, có thể kết hợp thêm wait strategy tương ứng.

Đăng ký connect string:

```java
@DynamicPropertySource
static void zookeeperProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.cloud.zookeeper.connect-string", () ->
            zookeeper.getHost() + ":" + zookeeper.getMappedPort(2181));
}
```

Kiểm tra các context tự động theo root/application/profile, explicit context nếu ứng dụng dùng, key precedence, ACL và hành vi khi session bị mất. Với test ACL, cần khởi động ZooKeeper với cấu hình xác thực phù hợp; một container mặc định không chứng minh ACL production đã được thiết lập.

## 10. Chờ container sẵn sàng đúng cách

Container ở trạng thái running chưa chắc dịch vụ bên trong đã sẵn sàng nhận request. Docker chỉ xác nhận tiến trình/container đang chạy; ứng dụng có thể chưa mở port, chưa hoàn tất bootstrap hoặc chưa tạo topology.

Testcontainers cung cấp các wait strategy:

- `Wait.forHttp(...)`: chờ HTTP endpoint trả status mong muốn.
- `Wait.forListeningPort()`: chờ port lắng nghe.
- `Wait.forLogMessage(...)`: chờ log startup đặc trưng.
- Health check của image/container nếu được cấu hình đáng tin cậy.

Ví dụ:

```java
new GenericContainer<>(DockerImageName.parse("hashicorp/consul:1.18"))
        .withExposedPorts(8500)
        .waitingFor(Wait.forHttp("/v1/status/leader")
                .forPort(8500)
                .forStatusCode(200));
```

Không dùng `Thread.sleep(5000)` như readiness check. Máy CI chậm hoặc nhanh khác nhau; sleep cố định vừa làm suite chậm vừa có thể vẫn chạy trước khi service sẵn sàng. Nếu dịch vụ cần thêm bước bootstrap như tạo KV mount hoặc queue, hãy chờ endpoint ready rồi chạy bước initialization rõ ràng.

## 11. Khởi tạo dữ liệu và dọn dẹp

Test cần dữ liệu xác định và không phụ thuộc vào thứ tự chạy. Có thể dùng `@BeforeAll` hoặc helper khởi tạo để tạo:

- RabbitMQ exchange/queue/binding riêng.
- Kafka topic và consumer group có suffix theo test run.
- Vault KV mount, secret path và policy test.
- Consul KV prefix riêng.
- ZooKeeper znode namespace riêng.

Khi container được tạo mới cho từng class, việc hủy container sẽ loại bỏ dữ liệu. Nếu dùng container tĩnh chung cho nhiều test, phải xóa key/queue/topic sau test hoặc dùng namespace duy nhất để tránh test trước làm ảnh hưởng test sau.

Không dùng container reuse như mặc định trong CI vì trạng thái cũ có thể tồn tại giữa các lần chạy. Reuse có thể hữu ích cho phát triển local, nhưng test phải tự làm sạch và không được dựa vào dữ liệu từ lần chạy trước.

## 12. Kiểm thử Spring Cloud Config Client cùng backend

Để kiểm tra Config Client thực sự nhận cấu hình từ một backend, có thể kết hợp Testcontainers với `@SpringBootTest` hoặc một context integration riêng.

Ví dụ cho Consul Config:

1. Khởi động Consul container.
2. Ghi các key cần thiết vào context test, ví dụ `config/billing-api,prod`.
3. Cung cấp Consul host/port và active profile cho ứng dụng.
4. Khởi động Config Client với Config Data import tương ứng.
5. Lấy `@ConfigurationProperties` bean và assert giá trị đã bind.
6. Thay đổi key, kích hoạt refresh nếu feature được dùng và xác minh bean/Environment theo lifecycle thực tế.

Với Vault hoặc ZooKeeper, quy trình tương tự nhưng phần chuẩn bị dữ liệu và authentication khác nhau. Đừng chỉ assert HTTP 200 của backend; hãy xác nhận property cuối cùng mà ứng dụng sử dụng và nguồn property source.

Khi kiểm tra Config Server dùng Git backend, có thể thêm Git repository test riêng hoặc một repository fixture local. Test cần xác nhận application/profile/label, revision metadata và cách server phản ứng khi branch/label không tồn tại.

## 13. Kiểm thử lỗi và phục hồi

Testcontainers cho phép tạo failure condition có kiểm soát:

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Broker dừng | Stop container hoặc ngắt network | Producer/consumer ghi nhận lỗi, reconnect theo policy |
| Vault token thiếu quyền | Dùng token không có policy đọc path | Request bị từ chối, ứng dụng không dùng nhầm secret khác |
| Consul context không tồn tại | Không tạo key hoặc dùng sai path | Optional/fail-fast theo cấu hình |
| ZooKeeper mất session | Restart container hoặc ngắt kết nối | Client reconnect và đọc lại context theo policy |
| Backend khởi động chậm | Tăng startup delay có kiểm soát | Wait strategy/startup retry hoạt động, không dùng sleep cố định |
| Config Server mất kết nối | Dừng server hoặc chặn network | Client startup/refresh phản ứng đúng với optional, retry và fallback |

Failure test phải có timeout, stop condition và cleanup. Không làm test treo vô hạn nếu dependency không sẵn sàng. Với các thử nghiệm phá hủy như restart broker hoặc backend, dùng container riêng cho test class để không ảnh hưởng test song song.

## 14. Parallel tests và chia sẻ container

JUnit có thể chạy test song song. Nếu nhiều test dùng cùng một container tĩnh, chúng có thể ghi đè key, xóa queue hoặc thay đổi policy của nhau.

Một số cách cô lập:

- Tạo container riêng theo class hoặc test khi cần trạng thái sạch.
- Đặt suffix cho topic, queue, KV path và znode theo test identifier.
- Tránh thao tác xóa toàn bộ namespace khi test khác vẫn đang chạy.
- Nếu phải chia sẻ container, dùng helper quản lý fixture và đồng bộ thao tác thay đổi trạng thái.
- Không phụ thuộc thứ tự test hoặc giá trị được ghi từ test trước.

Đối với broker, topic/queue riêng là lựa chọn tốt để kiểm tra consumer độc lập. Với Vault/Consul/ZooKeeper, namespace riêng giúp cleanup chính xác và giảm rủi ro xóa nhầm dữ liệu test khác.

## 15. Tích hợp vào CI

CI runner cần Docker-compatible runtime và quyền truy cập image registry. Một pipeline điển hình:

1. Build ứng dụng và test unit/binding trước.
2. Chạy nhóm integration test cần Testcontainers.
3. Pull image đã pin version/digest.
4. Khởi động container và chờ readiness.
5. Chạy test với endpoint port động.
6. Thu thập log container khi test fail.
7. Dừng và xóa container/network/volume theo lifecycle.
8. Xuất test report và phân loại lỗi code, infrastructure hay thiếu container runtime.

Trong CI, tránh dùng tag image `latest` vì thay đổi image ngoài ý muốn có thể làm test hôm nay khác test hôm qua. Pin image tag cụ thể hoặc digest, cập nhật có chủ đích và chạy lại suite khi nâng cấp.

Nếu CI chạy trong môi trường không cho phép Docker-in-Docker, có thể dùng remote Docker daemon hoặc runner có runtime được hỗ trợ. Cần bảo vệ socket/daemon vì quyền điều khiển Docker thường tương đương quyền cao trên host.

## 16. Chẩn đoán test flaky

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Container running nhưng test connection refused | Service chưa ready hoặc port mapping sai | Thêm wait strategy theo protocol/health endpoint |
| Test pass local, fail CI | Runtime, CPU, DNS, architecture hoặc image pull khác | Pin image, kiểm tra daemon và tăng timeout hợp lý |
| Test phụ thuộc thứ tự | Dữ liệu trong container dùng chung chưa cleanup | Namespace riêng hoặc container riêng |
| Kafka consumer không nhận message | Topic/group chưa sẵn sàng, offset hoặc assignment chưa hoàn tất | Chờ điều kiện consumer, kiểm tra topic/group và timeout |
| Vault test 403 | Token hoặc policy sai | Kiểm tra auth path, mount, policy và token test |
| Consul/ZooKeeper test đọc sai key | Context path/profile/root khác dự kiến | In metadata/path an toàn và kiểm tra fixture KV/znode |
| Port cố định bị chiếm | Nhiều test hoặc process khác dùng cùng host port | Dùng mapped port động từ Testcontainers |
| Container không dừng | Test bị kill hoặc lifecycle cấu hình sai | Dùng JUnit extension, xem container logs và CI cleanup |

Khi test fail, thu thập log container, image/tag, startup duration, mapped port và request path. Không in token, password hoặc secret plaintext trong test output.

## 17. Bảo mật trong integration test

Container test vẫn có thể làm lộ dữ liệu nếu dùng credential thật hoặc log response nhạy cảm:

- Dùng token/password giả, chỉ có hiệu lực trong container test.
- Không mount secret production hoặc Docker credential cá nhân không cần thiết.
- Không expose container port ra mạng công cộng; dùng port mapping local của Testcontainers.
- Dùng image chính thức hoặc image nội bộ đã được kiểm tra và pin version.
- Không log toàn bộ response Config Server, Vault secret hoặc Actuator `env`.
- Dùng ACL/policy test nếu cần xác minh authorization, không mặc định dev mode tương đương production.
- Cleanup dữ liệu, volume và network theo lifecycle; tránh để test container chứa secret sau khi test kết thúc.

Dev mode của Vault/Consul thường được cấu hình đơn giản, có thể tắt ACL hoặc dùng token đặc quyền. Chúng hữu ích cho test luồng cơ bản nhưng không thay thế test riêng cho TLS, ACL, policy và auth method của môi trường thật.

## 18. Checklist chọn dịch vụ và phạm vi test

| Dependency production | Testcontainers nên kiểm tra |
| --- | --- |
| RabbitMQ | Connection, exchange/queue, Bus event, reconnect và redelivery |
| Kafka | Bootstrap servers, topic, consumer group, offsets và Bus event |
| Vault | KV path/version, token, policy, secret binding và renewal nếu dùng |
| Consul | KV context, profile, ACL, service/config integration |
| ZooKeeper | Znode context, profile, ACL, session và reconnect |

Trước khi thêm container vào test suite, hãy trả lời:

- [ ] Có cần giao thức/server thật hay mock đủ để kiểm tra mục tiêu?
- [ ] Đã pin Testcontainers module/API và image version tương thích chưa?
- [ ] CI có Docker-compatible runtime không?
- [ ] Container có wait strategy đúng readiness không?
- [ ] Port được lấy động, không hard-code?
- [ ] Spring property được cấp trước đúng giai đoạn khởi tạo?
- [ ] Dữ liệu test có namespace riêng và cleanup không?
- [ ] Test có timeout, assertion và failure diagnostics rõ ràng không?
- [ ] Token/credential có phải dữ liệu giả và không xuất hiện trong log không?
- [ ] Có test negative case cho lỗi kết nối, quyền và context không tồn tại không?

## 19. Tài liệu tham khảo

- [Testcontainers for Java](https://java.testcontainers.org/): JUnit 5, container lifecycle, wait strategies và module documentation.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): tích hợp Testcontainers và `@ServiceConnection`.
- [Spring Cloud Bus Reference](https://docs.spring.io/spring-cloud-bus/reference/): cấu hình broker và phân phối event.
- [Spring Cloud Vault Reference](https://docs.spring.io/spring-cloud-vault/reference/): Vault authentication, Config Data và secret backend.
- [Spring Cloud Consul Reference](https://docs.spring.io/spring-cloud-consul/reference/): Consul Config và service discovery.
- [Spring Cloud Zookeeper Reference](https://docs.spring.io/spring-cloud-zookeeper/reference/): Zookeeper Config và discovery.

Testcontainers tạo ra một môi trường tích hợp gần thực tế, có thể tái tạo cho broker và backend cấu hình. Khi pin image, chờ readiness đúng giao thức, cấp port động, cô lập dữ liệu và kiểm tra cả trường hợp lỗi, nhóm có thể phát hiện sớm khác biệt giữa mock và dịch vụ thật. Bộ test nên tập trung vào contract mà ứng dụng sử dụng: kết nối, quyền, path/context, message delivery, binding và khả năng phục hồi.
