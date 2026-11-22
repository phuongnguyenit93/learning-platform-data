# Testcontainers bổ sung quản lý hạ tầng thật

Một ứng dụng Spring hiếm khi chạy độc lập. Nó có thể cần PostgreSQL, Redis, Kafka, RabbitMQ, Elasticsearch, một dịch vụ giả lập cloud hoặc nhiều thành phần hạ tầng khác. Trong production, các thành phần này có phiên bản, protocol, cấu hình và vòng đời riêng. Nếu test chỉ thay chúng bằng mock hoặc database thay thế, bài kiểm thử có thể bỏ sót lỗi tích hợp.

Testcontainers là thư viện Java giúp test quản lý các dịch vụ đó dưới dạng container. Test khai báo image, cấu hình, cổng, network và điều kiện sẵn sàng; Testcontainers tạo container, cung cấp endpoint động cho ứng dụng và dọn tài nguyên theo lifecycle đã chọn. Nhờ vậy, test có thể dùng hạ tầng thật trong phạm vi nhỏ, có thể tái tạo và không cần phụ thuộc một server dùng chung.

Trong Spring Framework Testing, Testcontainers bổ sung khả năng quản lý hạ tầng cho Spring Test. Spring vẫn quản lý `ApplicationContext`, bean, transaction và dependency injection; Testcontainers quản lý dịch vụ bên ngoài mà các bean đó kết nối tới. Hai phần kết hợp để kiểm tra đường tích hợp thực tế.

## 1. Testcontainers quản lý điều gì?

Testcontainers điều khiển container runtime tương thích Docker. Thay vì viết script riêng để cài và khởi động PostgreSQL hoặc Kafka trên máy developer, test khai báo một đối tượng Java mô tả dịch vụ cần có.

```text
JUnit test
    |
    v
Testcontainers API
    |
    | create / start / wait / stop
    v
Container runtime
    |
    +--------------------+--------------------+
    |                    |                    |
    v                    v                    v
PostgreSQL           Redis                 RabbitMQ
    |                    |                    |
    +--------------------+--------------------+
                         |
                         v
                Spring ApplicationContext
                         |
                         v
                 Integration assertions
```

Testcontainers có thể quản lý:

- Container có module chuyên biệt như PostgreSQL, MySQL, Kafka, RabbitMQ hoặc Redis.
- Image tùy chỉnh, dịch vụ nội bộ hoặc chương trình chỉ có thể chạy trong container.
- Network giữa nhiều container để chúng giao tiếp bằng alias và cổng nội bộ.
- Cổng được publish ra test process để ứng dụng chạy trên host kết nối vào.
- Environment variables, command, file cấu hình, volume và dữ liệu khởi tạo.
- Điều kiện readiness, timeout, log và cleanup.

Testcontainers không thay thế Spring IoC container. Nó không tự quyết định bean nào được inject, transaction nào được commit hoặc endpoint HTTP nào được gọi. Nó cung cấp hạ tầng ngoài tiến trình; Spring được cấu hình để kết nối tới hạ tầng đó.

## 2. Vì sao hạ tầng thật quan trọng trong integration test?

Một mock có thể xác nhận service gọi `repository.save(...)`, nhưng không xác nhận database thực thi được câu SQL. H2 có thể chạy nhanh, nhưng không đảm bảo tương đương PostgreSQL về JSONB, sequence, collation, locking hoặc cú pháp migration. Mock `KafkaTemplate` có thể xác nhận lệnh publish được gọi, nhưng không kiểm tra broker, serializer hoặc consumer group.

Container kiểm thử tạo ranh giới tích hợp thật:

| Thành phần | Điều test có thể xác nhận |
|---|---|
| Database | Driver, SQL, migration, constraint, transaction, index và isolation |
| Cache | Protocol, serialization, TTL, eviction và cấu hình client |
| Message broker | Kết nối, publish/consume, routing, acknowledgement, topic/queue và serializer |
| Search engine | Mapping, query DSL, analyzer và index lifecycle |
| Cloud emulator | Cấu hình SDK, endpoint, request signing và thao tác với dịch vụ giả lập |
| Dịch vụ nội bộ | Protocol, health check, cấu hình và khả năng giao tiếp giữa các thành phần |

Container test không có nghĩa phải chạy mọi dịch vụ trong mọi test. Hãy chọn đúng dịch vụ mà hợp đồng tích hợp đang phụ thuộc. Unit test vẫn phù hợp cho logic thuần; container test tập trung vào nơi ứng dụng giao tiếp với công nghệ bên ngoài.

## 3. Các khái niệm nền tảng

Một container Testcontainers thường được mô tả bởi các thuộc tính sau:

| Thuộc tính | Ý nghĩa |
|---|---|
| Image | Image và phiên bản dịch vụ cần chạy |
| Exposed port | Cổng nội bộ mà dịch vụ lắng nghe |
| Mapped port | Cổng host được runtime ánh xạ để test process kết nối |
| Environment | Biến môi trường để cấu hình image |
| Command | Lệnh hoặc tham số khởi động |
| Volume/bind mount | Dữ liệu hoặc file được chia sẻ với container |
| Network | Mạng để các container giao tiếp với nhau |
| Wait strategy | Điều kiện xác định dịch vụ đã sẵn sàng |
| Lifecycle | Thời điểm tạo, start, stop và dọn container |

Điểm quan trọng là phân biệt cổng nội bộ và cổng host. Ví dụ PostgreSQL lắng nghe cổng `5432` trong container, nhưng Testcontainers có thể ánh xạ nó sang `32781` trên host. Test phải lấy cổng động từ container, không giả định hai cổng giống nhau.

## 4. Thêm dependencies và quản lý phiên bản

Testcontainers được chia thành các module. Một dự án thường cần module JUnit Jupiter và module tương ứng với dịch vụ. Ví dụ theo cách khai báo module Testcontainers 1.x:

```groovy
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:1.20.6"))
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.testcontainers:rabbitmq")
}
```

Với Maven, dùng BOM trong `dependencyManagement` để mọi module Testcontainers có cùng phiên bản:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>1.20.6</version>
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
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các tọa độ trên minh họa cách dùng dòng 1.x. Khi dự án dùng major version khác, hãy theo BOM và tên module của major version đó; không trộn module từ các major version khác nhau. Driver JDBC, Spring Data, Spring AMQP hoặc Spring Kafka vẫn là dependency của ứng dụng, không được Testcontainers thay thế.

## 5. Dùng module chuyên biệt khi có sẵn

Với các công nghệ phổ biến, Testcontainers cung cấp class tiện ích để thiết lập image, cổng và readiness. Ví dụ PostgreSQL:

```java
import org.testcontainers.containers.PostgreSQLContainer;

PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine")
        .withDatabaseName("orders")
        .withUsername("test")
        .withPassword("test");
```

Module chuyên biệt giúp giảm cấu hình thủ công và thường có wait strategy phù hợp với dịch vụ đó. Các API lấy connection detail cũng rõ nghĩa hơn, chẳng hạn `getJdbcUrl()`, `getUsername()` và `getPassword()`.

Ví dụ RabbitMQ:

```java
import org.testcontainers.containers.RabbitMQContainer;

RabbitMQContainer rabbit = new RabbitMQContainer("rabbitmq:3.13-management-alpine")
        .withUser("test", "test", "/")
        .withPermission("/", "test", ".*", ".*", ".*");
```

Ví dụ Redis:

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7.4-alpine"))
        .withExposedPorts(6379);
```

Nếu module chuyên biệt có sẵn, ưu tiên module đó vì nó đóng gói các chi tiết đặc thù. `GenericContainer` phù hợp khi image không có module riêng hoặc test cần cấu hình image theo cách đặc biệt.

## 6. GenericContainer cho dịch vụ tùy biến

`GenericContainer` cho phép khởi chạy hầu hết image có thể chạy trong container runtime. Test tự khai báo cổng, biến môi trường, command và readiness.

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;

GenericContainer<?> fakeIdentity = new GenericContainer<>(
        DockerImageName.parse("ghcr.io/example/identity-test:2.1.0"))
        .withExposedPorts(8080)
        .withEnv("ADMIN_USER", "test-admin")
        .withEnv("ADMIN_PASSWORD", "test-password")
        .waitingFor(Wait.forHttp("/health").forStatusCode(200));
```

Sau khi start, lấy địa chỉ truy cập từ test process:

```java
fakeIdentity.start();
String host = fakeIdentity.getHost();
int port = fakeIdentity.getMappedPort(8080);
String baseUrl = "http://" + host + ":" + port;
```

`getMappedPort(8080)` trả về cổng host tương ứng với cổng `8080` trong container. Không nối cứng `localhost:8080` vì runtime có thể ánh xạ sang cổng khác hoặc host không phải `localhost` trong một số môi trường.

Nếu image cần file cấu hình, có thể copy file vào container trước khi start hoặc mount một thư mục test. Giữ file cấu hình trong test resources và tránh đưa secret production vào image hoặc log.

## 7. Quản lý lifecycle bằng JUnit Jupiter

Testcontainers tích hợp JUnit 5 qua `@Testcontainers` và `@Container`:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class RedisIntegrationTests {

    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4-alpine")
            .withExposedPorts(6379);

    @Test
    void startsRedisForTheTestClass() {
        assertThat(REDIS.isRunning()).isTrue();
    }
}
```

JUnit extension quản lý việc start và stop các field được đánh dấu `@Container`.

| Khai báo | Lifecycle |
|---|---|
| `static @Container` | Start một lần cho test class; stop sau class |
| Instance `@Container` | Start trước mỗi test method; stop sau mỗi method |
| Container tự start thủ công | Test code tự chịu trách nhiệm stop và cleanup |

Dùng static container khi các test method có thể chia sẻ cùng một dịch vụ và quản lý dữ liệu riêng. Dùng instance container khi cần trạng thái dịch vụ hoàn toàn mới cho từng method, nhưng lưu ý thời gian startup có thể tăng đáng kể.

Ví dụ quản lý thủ công:

```java
GenericContainer<?> redis = new GenericContainer<>("redis:7.4-alpine")
        .withExposedPorts(6379);

try {
    redis.start();
    // Tạo client và thực hiện test.
}
finally {
    redis.stop();
}
```

Trong test JUnit, extension thường dễ đọc hơn. Quản lý thủ công hữu ích khi container được tạo động trong helper, khi cần phối hợp nhiều container hoặc khi framework test không dùng JUnit Jupiter.

## 8. Kết nối Spring Boot tới container

Testcontainers khởi động dịch vụ, còn Spring cần endpoint để tạo bean client. Có hai cơ chế phổ biến: `@ServiceConnection` và `@DynamicPropertySource`.

### `@ServiceConnection`

Spring Boot 3.1 trở lên hỗ trợ service connection cho các loại container được nhận diện. Ví dụ PostgreSQL:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class RepositoryIntegrationTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot tạo `ConnectionDetails` cho service mà nó hỗ trợ và dùng thông tin đó trong auto-configuration. Dependency `spring-boot-testcontainers` phải có trong test classpath.

### `@DynamicPropertySource`

Khi cần ánh xạ property cụ thể hoặc container không có service connection factory, dùng `@DynamicPropertySource`:

```java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
    registry.add("spring.datasource.username", POSTGRES::getUsername);
    registry.add("spring.datasource.password", POSTGRES::getPassword);
}
```

Cách này hoạt động với mọi property mà ứng dụng cần, bao gồm URL của dịch vụ nội bộ, API endpoint giả lập hoặc broker tùy chỉnh. Nó cũng giúp test giữ nguyên cấu hình client production, chỉ thay endpoint sang container.

## 9. Phân biệt host port và container network

Khi test process chạy trên host và kết nối tới container, dùng host cùng mapped port:

```java
String host = redis.getHost();
int mappedPort = redis.getMappedPort(6379);
```

Khi một container cần kết nối tới container khác trên cùng Docker network, dùng network alias và cổng nội bộ. Không dùng mapped host port cho giao tiếp container-to-container.

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.wait.strategy.Wait;

Network network = Network.newNetwork();

GenericContainer<?> redis = new GenericContainer<>("redis:7.4-alpine")
        .withNetwork(network)
        .withNetworkAliases("cache")
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());

GenericContainer<?> worker = new GenericContainer<>("example/worker:1.0.0")
        .withNetwork(network)
        .withEnv("REDIS_HOST", "cache")
        .withEnv("REDIS_PORT", "6379");
```

Trong ví dụ này, `worker` kết nối tới host `cache` và cổng `6379` trên cùng network. Alias `cache` được Docker DNS phân giải. Nếu test process cần kết nối tới Redis, nó vẫn dùng `redis.getHost()` và `redis.getMappedPort(6379)`.

Khi tự tạo `Network`, hãy đóng network sau khi test hoàn tất. Nếu container được JUnit extension quản lý, có thể dùng helper/lifecycle rõ ràng để tránh để network tồn tại sau test.

## 10. Quản lý phụ thuộc giữa nhiều container

Một hệ thống test có thể cần nhiều dịch vụ: database, broker, cache và ứng dụng phụ trợ. Hãy thể hiện rõ dependency và readiness:

```text
PostgreSQL ----+
               |
Redis ---------+----> Spring application test
               |
RabbitMQ ------+
```

Các container có thể cùng một network để giao tiếp trực tiếp. Với mỗi dịch vụ:

1. Khởi động container nền tảng.
2. Chờ readiness condition của dịch vụ đó.
3. Cung cấp host/port hoặc network alias cho dịch vụ phụ thuộc.
4. Khởi động container phụ thuộc.
5. Chờ ứng dụng phụ thuộc sẵn sàng.
6. Chạy test và dọn theo thứ tự ngược lại.

Một số API có thể khai báo dependency bằng `dependsOn(...)` hoặc wait strategy tùy loại container. Tuy nhiên, chỉ khởi động theo thứ tự không đủ; cần chờ dịch vụ thật sự nhận kết nối. Nếu có nhiều container, nên gom phần khai báo vào một fixture hoặc test configuration thay vì lặp lại cấu hình ở từng test method.

## 11. Readiness: running không có nghĩa là ready

Container runtime có thể báo container đang chạy trong khi database vẫn đang khởi tạo schema hoặc broker chưa mở listener. Testcontainers dùng wait strategy để xác định khi nào test có thể kết nối.

Một số loại readiness:

| Wait strategy | Điều kiện |
|---|---|
| `Wait.forListeningPort()` | Cổng dịch vụ bắt đầu lắng nghe |
| `Wait.forHttp("/health")` | Endpoint health trả status mong đợi |
| `Wait.forLogMessage(...)` | Log chứa thông báo sẵn sàng |
| Wait strategy riêng | Một điều kiện đặc thù của dịch vụ |

Ví dụ:

```java
GenericContainer<?> service = new GenericContainer<>("example/service:1.0.0")
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health")
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofMinutes(2)));
```

Không dùng `Thread.sleep(5000)` để đoán service đã sẵn sàng. Sleep có thể quá ngắn trên CI hoặc lãng phí thời gian khi service khởi động nhanh. Wait strategy kiểm tra một điều kiện có ý nghĩa và có timeout rõ ràng.

## 12. Dùng Docker Compose cho một cụm dịch vụ

Khi hạ tầng gồm nhiều container có cấu hình liên quan, Docker Compose có thể mô tả chúng trong một file YAML: service, image, environment, volume, network và dependency. Testcontainers có hỗ trợ tích hợp Compose để khởi động cụm dịch vụ từ cấu hình này.

Một file Compose tối giản:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d orders"]
      interval: 2s
      timeout: 2s
      retries: 20

  redis:
    image: redis:7.4-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 2s
      retries: 20
```

Compose hữu ích khi developer cần cùng một cụm dịch vụ để chạy local và test. Tuy nhiên, không nên để test phụ thuộc vào một Compose stack đã được người dùng khởi động từ trước mà không kiểm soát version và lifecycle. Hãy để Testcontainers quản lý việc start/stop stack hoặc dùng các container khai báo trực tiếp trong test.

API Compose của Testcontainers đã thay đổi giữa các phiên bản. Hãy dùng module và cách khai báo theo phiên bản Testcontainers mà dự án quản lý; nguyên tắc quan trọng là test phải kiểm soát rõ file Compose, project name, cổng được publish, readiness và cleanup.

## 13. Tạo image hoặc dịch vụ test tùy chỉnh

Không phải mọi dịch vụ đều có image chính thức phù hợp. Có thể build image từ Dockerfile dành riêng cho test hoặc dùng image nội bộ đã được publish.

Ví dụ dùng `ImageFromDockerfile`:

```java
import org.testcontainers.images.builder.ImageFromDockerfile;

ImageFromDockerfile image = new ImageFromDockerfile()
        .withFileFromClasspath("Dockerfile", "test-service/Dockerfile")
        .withFileFromClasspath("app.jar", "test-service/app.jar");

GenericContainer<?> service = new GenericContainer<>(image)
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health").forStatusCode(200));
```

Image build giúp test có thể chạy một dịch vụ nội bộ cùng mã nguồn với repository. Để build ổn định, cần kiểm soát Dockerfile, base image và dependency. Nếu build image quá lâu hoặc nhiều test dùng chung một image, cân nhắc build một lần trong pipeline rồi pull image đã gắn tag bất biến.

## 14. Dữ liệu, volume và cleanup

Container riêng giúp cô lập process, nhưng dữ liệu vẫn có thể tồn tại trong suốt lifecycle của container. Nếu nhiều test method dùng chung database container, row hoặc queue từ test trước có thể ảnh hưởng test sau.

Một số chiến lược:

| Chiến lược | Tác động | Khi dùng |
|---|---|---|
| Container mới cho mỗi method | Cách ly mạnh, startup tốn hơn | Test cần trạng thái dịch vụ mới hoàn toàn |
| Container dùng chung cho class | Nhanh hơn, cần reset dữ liệu | Nhiều test dùng cùng schema và image |
| Schema/database riêng cho từng test | Cách ly dữ liệu, dùng chung server | Test song song hoặc migration riêng |
| Xóa fixture sau test | Giữ container sống lâu | Dữ liệu có thể dọn an toàn bằng transaction hoặc SQL |
| Dùng key duy nhất | Giảm xung đột giữa test | Test concurrent hoặc dữ liệu bất đồng bộ |

`@Transactional` và rollback chỉ áp dụng cho transaction được Spring Test quản lý. Message đã gửi tới broker, transaction ở thread khác hoặc công việc async có thể tồn tại sau rollback. Với broker, hãy tạo queue/topic riêng hoặc xóa message/state theo từng test.

Volume có thể lưu dữ liệu qua vòng đời container. Điều này hữu ích khi cần tái sử dụng dữ liệu hoặc cung cấp file cấu hình, nhưng volume dùng chung cũng làm tăng nguy cơ test phụ thuộc state cũ. Chỉ bật persistence khi đó là điều cần kiểm tra.

## 15. Container lifecycle và Spring TestContext cache

Spring TestContext Framework có thể cache `ApplicationContext` giữa nhiều test class. Nếu một bean trong context giữ connection tới container đã bị JUnit extension dừng sau class đầu tiên, class tiếp theo có thể tái sử dụng context cũ nhưng endpoint đã không còn hoạt động.

Vì vậy, container lifecycle phải tương thích với context lifecycle:

- Với một test class độc lập, static `@Container` thường là lựa chọn đơn giản.
- Với nhiều test class dùng chung context, container cần sống ít nhất lâu bằng context được cache.
- Nếu dùng singleton container tự quản lý, test suite phải xác định rõ ai start và ai stop.
- Không stop container ở `@AfterAll` của một class nếu Spring có thể tái sử dụng context đó ở class khác.
- Khi endpoint động thay đổi, Spring có thể tạo context mới vì dynamic properties khác nhau; điều này có thể ảnh hưởng cache và thời gian chạy.

Singleton pattern có thể giảm thời gian startup nhưng cần xử lý việc cleanup ở cuối test suite. Đừng trộn singleton tự quản lý với `@Container` extension cho cùng một container, vì hai cơ chế có thể tranh quyền lifecycle.

## 16. Container reuse: nhanh hơn nhưng có trạng thái tồn tại

Testcontainers có hỗ trợ reuse container trong một số môi trường phát triển. Reuse có thể giúp tiết kiệm thời gian khi database hoặc broker nặng, nhưng container không được dừng sau mỗi lần test và state có thể tồn tại giữa các lần chạy.

Reuse phù hợp khi:

- Developer chạy lặp lại cùng một nhóm test local.
- Có cơ chế reset database, queue, topic và cache rõ ràng.
- Không yêu cầu test luôn bắt đầu từ image state mới.

Reuse không phù hợp khi:

- CI cần môi trường sạch và kết quả tái lập.
- Test phụ thuộc vào schema hoặc dữ liệu mới.
- Nhiều branch hoặc test suite có thể ghi vào cùng container.
- Không có quy trình reset state đáng tin cậy.

Không bật reuse chỉ để làm test xanh nhanh hơn. Trước hết, đo thời gian startup và tối ưu image cache, parallelism, lifecycle hoặc test grouping. Nếu bật reuse, hãy xem đó là một lựa chọn môi trường local có chủ đích.

## 17. Chẩn đoán khi container không khởi động

Khi test thất bại trước assertion, nguyên nhân có thể nằm ở runtime, image pull, readiness hoặc cấu hình container. Hãy phân loại lỗi:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy Docker environment | Docker daemon/socket không truy cập được | Kiểm tra runtime và quyền của process test |
| Image pull thất bại | Registry không truy cập được, tag sai hoặc thiếu quyền | Kiểm tra image name, tag và registry credentials |
| Container exit ngay sau start | Environment hoặc command sai | Đọc container logs và exit code |
| Timeout khi chờ readiness | Health endpoint/cổng/log không đúng hoặc service khởi động lỗi | Kiểm tra wait strategy và log startup |
| Spring không kết nối được | Dùng nhầm host/cổng hoặc property chưa được nạp | Kiểm tra mapped port, `getHost()` và dynamic property |
| Test class sau thất bại | Container đã dừng nhưng context được cache | Kiểm tra sự phối hợp lifecycle giữa JUnit và Spring |

Có thể lấy log container trong test hoặc khi xử lý lỗi:

```java
String logs = container.getLogs();
System.out.println(logs);
```

Trong CI, nên lưu log container khi test thất bại để biết dịch vụ dừng ở đâu. Tránh in secret hoặc dữ liệu nhạy cảm có thể xuất hiện trong log.

## 18. Chạy Testcontainers trong CI

Testcontainers cần Docker-compatible runtime mà process chạy test có thể truy cập. Runner CI phải cấp Docker daemon/socket hoặc cấu hình remote runtime được hỗ trợ.

Pipeline cần quan tâm:

- Runtime sẵn sàng trước khi chạy Gradle/Maven.
- Quyền truy cập Docker socket/daemon được cấp cho đúng user.
- Registry image có thể truy cập và image được cache hợp lý.
- Runner có đủ CPU, RAM và disk để chạy database/broker.
- Timeout của job đủ cho pull image và startup service.
- Test parallelism không vượt quá tài nguyên thực tế.
- Container được dọn sau khi job kết thúc hoặc bị hủy.

Nếu runner không có container runtime, Testcontainers không thể hoạt động theo cách thông thường. Có thể dùng service container do CI cung cấp, một môi trường hạ tầng test chuyên biệt hoặc runner khác có Docker support. Không nên âm thầm bỏ qua test tích hợp quan trọng; hãy thể hiện rõ nhóm test nào cần runtime.

## 19. Testcontainers so với các lựa chọn khác

| Công cụ | Hạ tầng được quản lý ở đâu | Phù hợp với |
|---|---|---|
| Mockito/fake | Trong process test | Unit test và kiểm tra tương tác |
| Embedded database/broker | Trong process hoặc runtime nhúng | Test nhanh khi hành vi đủ gần production |
| `MockRestServiceServer` | Tầng Spring request factory | Kiểm tra hợp đồng HTTP client không cần socket |
| Testcontainers | Container runtime cục bộ/remote | Tích hợp với dịch vụ thật và protocol thật |
| Docker Compose chạy thủ công | Môi trường bên ngoài test | Developer stack hoặc môi trường test được quản lý riêng |
| Dịch vụ dùng chung trên môi trường test | Hạ tầng trung tâm | Kiểm thử hệ thống hoặc môi trường tích hợp dài hạn |

Testcontainers không phải lựa chọn duy nhất và cũng không cần xuất hiện trong mọi test. Giá trị của nó là tạo hạ tầng gần production với lifecycle do test kiểm soát, giúp giảm phụ thuộc vào dịch vụ dùng chung và cấu hình thủ công trên máy developer.

## 20. Quy trình chọn và quản lý hạ tầng bằng Testcontainers

1. Xác định dịch vụ bên ngoài nào ảnh hưởng trực tiếp tới hợp đồng đang kiểm tra.
2. Chọn module Testcontainers chuyên biệt nếu có; nếu không, dùng `GenericContainer` hoặc image test tùy chỉnh.
3. Pin image version và quản lý module bằng BOM tương ứng.
4. Quyết định container sống theo method, class hay test suite.
5. Khai báo cổng, environment, volume, network và readiness.
6. Kết nối Spring bằng `@ServiceConnection` hoặc `@DynamicPropertySource`.
7. Tách dữ liệu, queue/topic và cache giữa các test.
8. Phối hợp container lifecycle với Spring context cache.
9. Lưu log và chẩn đoán startup failure rõ ràng.
10. Bảo đảm CI có runtime, quyền truy cập và tài nguyên cần thiết.
11. Chỉ dùng reuse khi state có thể được reset và lợi ích đã được đo lường.

## 21. Tài liệu tham khảo

- [Testcontainers for Java — Documentation](https://java.testcontainers.org/): API, module, lifecycle, network, wait strategy và CI.
- [Testcontainers — JUnit 5 Quickstart](https://java.testcontainers.org/quickstart/junit_5_quickstart/): tích hợp `@Testcontainers` và `@Container`.
- [Testcontainers — Generic Container](https://java.testcontainers.org/features/creating_container/): cấu hình image, port, environment và command.
- [Testcontainers — Networking](https://java.testcontainers.org/features/networking/): mapped ports, host và container network.
- [Testcontainers — Reusable Containers](https://java.testcontainers.org/features/reuse/): điều kiện và giới hạn của container reuse.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và tích hợp với Spring Boot.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): cấu hình property động trong Spring TestContext.

Testcontainers bổ sung khả năng quản lý hạ tầng thật cho Spring tests: tạo đúng dịch vụ, cấp endpoint động, chờ sẵn sàng, kết nối Spring và dọn tài nguyên theo lifecycle có chủ đích. Hãy chọn phạm vi container vừa đủ cho hợp đồng tích hợp cần xác nhận, quản lý state giữa các test và giữ cấu hình có thể tái lập trên cả máy developer lẫn CI.
