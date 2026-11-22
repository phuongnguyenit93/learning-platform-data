# @DynamicPropertySource cho địa chỉ và cổng cấp khi chạy

Trong kiểm thử tích hợp, một dịch vụ phụ trợ có thể được khởi động ở địa chỉ hoặc cổng chỉ biết tại thời điểm chạy. Ví dụ, Testcontainers tạo một PostgreSQL container và ánh xạ cổng nội bộ `5432` sang một cổng khả dụng trên máy host. Cổng host có thể khác nhau ở mỗi lần chạy để tránh xung đột với tiến trình khác. Một HTTP service giả lập cũng có thể chọn cổng ngẫu nhiên khi khởi động.

Ứng dụng Spring vẫn cần nhận được địa chỉ kết nối chính xác để tạo `DataSource`, HTTP client hoặc bean tích hợp. Nếu ghi cứng `localhost:5432` hoặc một cổng cố định trong file cấu hình test, bài kiểm thử có thể phụ thuộc vào môi trường của máy chạy. `@DynamicPropertySource` giải quyết vấn đề này bằng cách đăng ký các thuộc tính Spring từ những giá trị được cung cấp tại runtime.

Annotation này thường được dùng cùng Spring Test và Testcontainers. Một phương thức `static` nhận `DynamicPropertyRegistry`, sau đó đăng ký tên thuộc tính với một `Supplier`. Spring chỉ lấy giá trị khi thuộc tính được truy xuất, nhờ vậy có thể đọc host và mapped port sau khi tài nguyên kiểm thử đã được khởi động.

## 1. Vấn đề của địa chỉ và cổng cố định

Giả sử ứng dụng có cấu hình kết nối PostgreSQL:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders
    password: secret
```

Thiết lập này chỉ hoạt động nếu PostgreSQL thật sự chạy trên host tại cổng `5432`, database có tên `orders` và thông tin xác thực trùng khớp. Trong CI hoặc trên máy của thành viên khác, cổng đó có thể đã được sử dụng, database có thể chưa được cài đặt hoặc dịch vụ có thể chạy trong container với cổng host được ánh xạ khác.

Testcontainers thường cho phép container lắng nghe một cổng nội bộ cố định, rồi ánh xạ cổng đó sang một cổng khả dụng trên host. Ví dụ:

```text
PostgreSQL container
    container port: 5432
             |
             | Docker port mapping
             v
Test host
    host: localhost (hoặc host phù hợp với runtime)
    mapped port: 49172 (ví dụ, được cấp khi chạy)
```

Ứng dụng phải kết nối đến địa chỉ do container cung cấp, không thể giả định cổng host luôn là `5432`. Tương tự, nếu một dịch vụ HTTP được khởi động với cổng ngẫu nhiên, URL cần được tạo sau khi dịch vụ đã chọn cổng.

## 2. @DynamicPropertySource là gì?

`@DynamicPropertySource` là annotation của Spring Test dùng để đăng ký các thuộc tính động vào `Environment` khi Spring chuẩn bị `ApplicationContext` cho test. Phương thức được đánh dấu phải là `static` và nhận đúng một tham số kiểu `DynamicPropertyRegistry`.

Ví dụ khung:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("service.base-url", () -> "http://localhost:49172");
}
```

`registry.add(...)` nhận:

- Tên property mà ứng dụng sẽ đọc, chẳng hạn `spring.datasource.url` hoặc `partner.api.base-url`.
- Một `Supplier` trả về giá trị của property khi Spring cần đọc nó.

Phương thức này không tự khởi động server, không tự cấp cổng và không kiểm tra dịch vụ có sẵn sàng hay không. Nó chỉ kết nối các giá trị runtime đã được một thành phần khác tạo ra với cấu hình của Spring.

Các property được đăng ký theo cách này có độ ưu tiên cao hơn các nguồn cấu hình thông thường như `@TestPropertySource`, system properties, environment variables và các property source được thêm bằng `@PropertySource`. Vì vậy, một giá trị động có thể ghi đè cấu hình mặc định trong `application.yml` hoặc một giá trị test property source khi cùng tên thuộc tính được sử dụng.

## 3. Cấu trúc phương thức đăng ký

Spring cung cấp hai kiểu dữ liệu chính:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
```

Một phương thức đăng ký có dạng:

```java
@DynamicPropertySource
static void registerServiceProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.api.host", () -> "127.0.0.1");
    registry.add("partner.api.port", () -> 49172);
    registry.add("partner.api.base-url", () -> "http://127.0.0.1:49172");
}
```

Đây là ví dụ minh họa giá trị tĩnh được bọc trong supplier. Trong thực tế, supplier thường đọc host và cổng từ container hoặc server đã khởi động:

```java
registry.add("partner.api.host", partnerServer::getHost);
registry.add("partner.api.port", () -> partnerServer.getMappedPort(8080));
```

Ví dụ thứ hai chỉ minh họa ý tưởng; với API của từng server hoặc container, cần truyền cổng container nội bộ vào `getMappedPort(int)` nếu method yêu cầu tham số. Phần tiếp theo trình bày cách đăng ký đầy đủ.

Các điểm cần nhớ:

- Phương thức phải là `static`, vì Spring cần đọc cấu hình trước khi tạo test instance.
- Tham số phải là `DynamicPropertyRegistry`.
- `registry.add` nhận supplier, nên nên dùng method reference hoặc lambda để đọc giá trị khi cần.
- Tên property phải trùng với tên mà ứng dụng thực sự sử dụng.
- Tài nguyên cung cấp host và cổng phải còn hoạt động trong suốt thời gian `ApplicationContext` sử dụng các property đó.

## 4. Ví dụ đầy đủ với PostgreSQL Testcontainers

### 4.1. Khai báo dependency kiểm thử

Với dự án Spring Boot, starter kiểm thử thường đã cung cấp Spring Test và JUnit Jupiter. Cần thêm các module Testcontainers tương ứng với JUnit Jupiter và PostgreSQL.

Ví dụ Gradle Groovy:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    testImplementation platform(
        "org.testcontainers:testcontainers-bom:${testcontainersVersion}"
    )
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

`testcontainersVersion` cần được định nghĩa tập trung trong version catalog hoặc cấu hình Gradle của dự án. BOM Testcontainers đồng bộ các module Testcontainers với nhau. Không nên tùy tiện gán các phiên bản khác nhau cho `junit-jupiter`, `postgresql` và các module Testcontainers liên quan.

Ví dụ Maven:

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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
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

Ví dụ Maven giả định `${testcontainers.version}` được khai báo trong `properties` hoặc parent POM. Nếu dự án không dùng Spring Boot, vẫn có thể dùng `spring-test` và JUnit Jupiter riêng, miễn là dependency management đã đồng bộ các phiên bản cần thiết.

### 4.2. Đăng ký URL, username và password từ container

Giả sử ứng dụng có repository cần kết nối PostgreSQL. Test class có thể khai báo container tĩnh và đăng ký thuộc tính:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("orders")
                    .withPassword("secret");

    @DynamicPropertySource
    static void registerDataSourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void repositoryUsesRunningPostgresContainer() {
        assertNotNull(orderRepository);
    }
}
```

`@Container` đánh dấu container do Testcontainers JUnit Jupiter extension quản lý. Vì field là `static`, container có vòng đời cấp class và được dùng chung cho các test method trong class. PostgreSQL lắng nghe cổng nội bộ mặc định `5432`; Testcontainers ánh xạ cổng đó sang một cổng khả dụng trên host.

`getJdbcUrl()` trả về JDBC URL đã bao gồm host và mapped port. `getUsername()` và `getPassword()` trả về thông tin xác thực cấu hình cho container. Các method reference được truyền trực tiếp cho `registry.add`, do đó Spring có thể lấy giá trị khi property được phân giải.

Trong ứng dụng, Spring Boot đọc ba property `spring.datasource.*` để tạo `DataSource`. File `application.yml` có thể giữ các giá trị mặc định cho môi trường khác; dynamic properties của test sẽ có độ ưu tiên cao hơn trong context kiểm thử.

### 4.3. Vì sao nên dùng supplier?

Có thể viết:

```java
registry.add("spring.datasource.url", () -> postgres.getJdbcUrl());
```

hoặc:

```java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
```

Hai cách trên đều cung cấp supplier. Giá trị được lấy khi Spring truy xuất property, thay vì buộc phải gọi getter ngay trong lúc đăng ký. Điều này quan trọng vì host và mapped port chỉ có ý nghĩa sau khi container đã khởi động.

Không nên tính địa chỉ trước thời điểm container được khởi động rồi giữ lại một giá trị mặc định. Supplier cũng không làm cho container tự khởi động; lifecycle của container vẫn do Testcontainers hoặc mã quản lý server đảm nhiệm.

## 5. Đăng ký host và mapped port của một HTTP container

Không phải lúc nào ứng dụng cũng cần JDBC URL. Một service có thể gọi sang một HTTP dependency chạy trong container, chẳng hạn catalog service, identity provider hoặc mock API.

Giả sử container lắng nghe cổng nội bộ `8080`:

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

@Container
static final GenericContainer<?> partner =
        new GenericContainer<>(DockerImageName.parse("example/partner-api:1.0"))
                .withExposedPorts(8080);
```

Sau khi container được khởi động, Testcontainers cung cấp:

- `partner.getHost()`: host mà test process cần sử dụng để truy cập container.
- `partner.getMappedPort(8080)`: cổng trên host được ánh xạ từ cổng nội bộ `8080`.

Đăng ký thuộc tính base URL:

```java
@DynamicPropertySource
static void registerPartnerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.api.base-url", () ->
            "http://" + partner.getHost() + ":" + partner.getMappedPort(8080)
    );
}
```

Ứng dụng có thể đọc giá trị này qua `@Value`:

```java
@Component
class PartnerClient {

    private final RestClient restClient;

    PartnerClient(
            RestClient.Builder builder,
            @Value("${partner.api.base-url}") String baseUrl
    ) {
        this.restClient = builder.baseUrl(baseUrl).build();
    }
}
```

Hoặc dùng `@ConfigurationProperties` nếu có nhiều thuộc tính liên quan:

```java
@ConfigurationProperties(prefix = "partner.api")
public record PartnerApiProperties(URI baseUrl) {
}
```

Trong trường hợp dùng record binding, cần bật configuration properties scanning hoặc đăng ký class bằng `@EnableConfigurationProperties`. Kiểu `URI` giúp mô hình hóa địa chỉ endpoint rõ ràng hơn một chuỗi tùy ý.

Không nên ghép cứng `localhost` nếu môi trường Testcontainers có thể dùng Docker host khác. `getHost()` cung cấp địa chỉ mà Testcontainers xác định là có thể truy cập từ test process.

## 6. Đăng ký riêng host, port và URL

Một số client nhận host và port riêng thay vì base URL. Có thể đăng ký từng property:

```java
@DynamicPropertySource
static void registerPartnerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.api.host", partner::getHost);
    registry.add("partner.api.port", () -> partner.getMappedPort(8080));
}
```

Spring có thể chuyển đổi giá trị sang kiểu đích khi inject. Ví dụ:

```java
@Component
class PartnerConnectionSettings {

    private final String host;
    private final int port;

    PartnerConnectionSettings(
            @Value("${partner.api.host}") String host,
            @Value("${partner.api.port}") int port
    ) {
        this.host = host;
        this.port = port;
    }
}
```

Nếu ứng dụng sử dụng `@ConfigurationProperties`, có thể khai báo class chứa `host` và `port` rồi để Spring bind các property theo prefix. Cách đó thường phù hợp hơn khi cấu hình endpoint có thêm scheme, timeout, path hoặc authentication.

Nên đăng ký property theo đúng mô hình cấu hình của ứng dụng. Nếu client nhận một `URI` duy nhất, đăng ký base URL; nếu client cần host và port riêng, đăng ký hai thuộc tính riêng. Tránh duy trì nhiều property trùng ý nghĩa nếu chúng có thể bị lệch nhau.

## 7. Dùng với WireMock hoặc server chọn cổng ngẫu nhiên

Một server chạy ngay trong JVM cũng có thể chọn cổng khi khởi động. Ví dụ, WireMock hỗ trợ `dynamicPort()` và cung cấp port thực tế qua `port()`.

Một cách tổ chức là khởi động server tĩnh trước khi Spring tạo context, sau đó đăng ký port:

```java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;

class PartnerClientIntegrationTest {

    static final WireMockServer wireMock =
            new WireMockServer(options().dynamicPort());

    static {
        wireMock.start();
    }

    @DynamicPropertySource
    static void registerPartnerProperties(DynamicPropertyRegistry registry) {
        registry.add("partner.api.base-url", wireMock::baseUrl);
    }

    @AfterAll
    static void stopWireMock() {
        wireMock.stop();
    }
}
```

`baseUrl()` trả về URL có cổng thực tế của server. Ví dụ dùng static initializer để server đã chạy trước khi Spring phân giải property. Nếu dùng lifecycle mechanism khác, cần bảo đảm server đã start trước khi bean phụ thuộc vào endpoint được tạo.

Với server do JUnit extension quản lý, hãy xem xét thứ tự lifecycle giữa extension khởi động server và Spring Test khởi tạo context. Không nên giả định rằng một `@BeforeAll` bất kỳ luôn chạy trước mọi thao tác chuẩn bị context của Spring. Cách tổ chức lifecycle phải bảo đảm supplier chỉ được gọi khi server đã sẵn sàng và server không bị dừng trong lúc context còn sử dụng.

Trong test class thực tế, cần thêm dependency WireMock phù hợp với phiên bản đang sử dụng. Nếu test cần nhiều server, có thể đăng ký từng base URL dưới các property khác nhau.

## 8. Kết hợp với @TestPropertySource và application.yml

Một dự án thường vẫn giữ cấu hình mặc định trong `src/main/resources/application.yml`:

```yaml
partner:
  api:
    base-url: http://localhost:8080
```

Giá trị này có thể phục vụ cấu hình local hoặc môi trường được thiết lập riêng. Trong integration test, `@DynamicPropertySource` cung cấp URL thực tế:

```java
@DynamicPropertySource
static void registerPartnerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.api.base-url", partner::getBaseUrl);
}
```

Nếu test class đồng thời có:

```java
@TestPropertySource(properties = "partner.api.base-url=http://localhost:9999")
```

thì dynamic property cùng tên có độ ưu tiên cao hơn và giá trị từ supplier được sử dụng. Điều này hữu ích khi file test property cung cấp mặc định nhưng endpoint thật chỉ biết sau khi khởi động tài nguyên.

Hãy đặt tên property đúng với cấu hình ứng dụng. Nếu ứng dụng đọc `partner.client.url` nhưng test đăng ký `partner.api.base-url`, giá trị động sẽ không ảnh hưởng tới client. Một lỗi thường gặp là đăng ký đúng host/port nhưng dùng sai prefix so với `@ConfigurationProperties` hoặc `@Value`.

## 9. Kết hợp với @ServiceConnection trong Spring Boot

Trong một số bài kiểm thử Spring Boot dùng Testcontainers, có thể dùng `@ServiceConnection` thay cho việc tự đăng ký các thuộc tính kết nối phổ biến.

Ví dụ với PostgreSQL:

```java
@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot nhận diện loại container và tạo connection details cho dịch vụ tương ứng. Cách này tiện khi cần cấu hình datasource chuẩn mà không muốn tự ánh xạ URL, username và password.

`@DynamicPropertySource` vẫn hữu ích khi:

- Property không thuộc loại service connection mà Spring Boot tự nhận diện.
- Ứng dụng cần property riêng, chẳng hạn `partner.api.base-url`, API token giả lập hoặc cổng của service nội bộ.
- Dự án chỉ dùng Spring Framework và không dùng cơ chế service connection của Spring Boot.
- Cần kiểm soát rõ cách ánh xạ từ tài nguyên runtime sang tên property.

Không cần đăng ký lại `spring.datasource.*` bằng `@DynamicPropertySource` nếu `@ServiceConnection` đã cung cấp đầy đủ connection details và ứng dụng đang sử dụng cơ chế đó. Chọn một cách cấu hình nhất quán để tránh hai nguồn cùng cố gắng điều khiển một kết nối.

## 10. Vòng đời container, supplier và context cache

Một điểm quan trọng là `ApplicationContext` của Spring Test có thể được cache giữa các test class. Trong khi đó, container hoặc server có thể được khởi động và dừng theo vòng đời của test class. Hai vòng đời này phải tương thích.

### 10.1. Supplier không quản lý vòng đời tài nguyên

Đoạn mã:

```java
registry.add("partner.api.base-url", () ->
        "http://" + partner.getHost() + ":" + partner.getMappedPort(8080)
);
```

chỉ trả về địa chỉ của container. Nó không bảo đảm container còn chạy khi một bean sử dụng URL đó. Nếu container đã dừng, giá trị property có thể vẫn tồn tại trong context nhưng kết nối sẽ thất bại.

Vì vậy, tài nguyên cung cấp property phải sống ít nhất lâu bằng thời gian context cần dùng nó. Với container `static @Container`, Testcontainers quản lý container ở phạm vi class. Nếu context được tái sử dụng ngoài vòng đời container, cần điều chỉnh cách quản lý tài nguyên hoặc context.

### 10.2. Context cache và lớp con kế thừa DynamicPropertySource

Các phương thức `@DynamicPropertySource` có thể được kế thừa từ test class cha. Điều này hữu ích khi nhiều test class dùng chung một container hoặc cùng một test infrastructure.

Tuy nhiên, nếu lớp con dùng container khác hoặc các giá trị động thay đổi giữa các lớp con, Spring có thể tái sử dụng `ApplicationContext` đã cache với cấu hình được tạo từ giá trị trước đó. Khi đó, context có thể tiếp tục dùng địa chỉ cũ.

Spring Test documentation lưu ý rằng khi dynamic properties thay đổi giữa các subclass, có thể cần dùng `@DirtiesContext` để bảo đảm context cache được làm mới giữa các lớp. Ví dụ:

```java
@Testcontainers
abstract class AbstractDatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Các lớp con có thể dùng chung hạ tầng và cùng một vòng đời container. Nếu mỗi lớp con cần một container hoặc endpoint khác nhau, hãy cân nhắc context riêng, `@DirtiesContext` ở vị trí phù hợp hoặc quản lý container có vòng đời dài hơn context.

### 10.3. Tránh dừng server quá sớm

Một lỗi phổ biến là dừng WireMock hoặc container sau test class trong khi context vẫn được giữ trong cache và được test khác tái sử dụng. Khi đó, bean HTTP client vẫn chứa URL cũ nhưng server không còn chạy.

Các hướng xử lý thường dùng:

- Dùng tài nguyên có vòng đời phù hợp với context được cache.
- Dùng container tĩnh được chia sẻ giữa các test class có cùng cấu hình.
- Đánh dấu context cần loại khỏi cache bằng `@DirtiesContext` khi tài nguyên gắn với context đã kết thúc.
- Tách test class để các context và tài nguyên có vòng đời độc lập, dễ kiểm soát.

Không nên thêm `@DirtiesContext` cho mọi test theo thói quen vì nó làm giảm lợi ích cache và khiến suite chậm hơn. Chỉ dùng khi trạng thái context hoặc tài nguyên phụ thuộc vòng đời thực sự cần được làm mới.

## 11. Những lỗi thường gặp khi dùng @DynamicPropertySource

### 11.1. Phương thức không phải static

Spring cần đọc dynamic properties trong giai đoạn chuẩn bị context, trước khi test instance được tạo đầy đủ. Nếu phương thức không phải `static`, Spring không thể gọi theo hợp đồng của annotation. Hãy khai báo `static void`.

### 11.2. Sai tham số phương thức

Phương thức phải nhận một tham số `DynamicPropertyRegistry`. Không truyền `Environment`, `ApplicationContext` hoặc một registry tự tạo.

### 11.3. Đăng ký property nhưng không đúng tên

Nếu ứng dụng đọc `spring.datasource.url`, đăng ký `spring.datasource.jdbc-url` sẽ không tự động thay thế property đó. Kiểm tra prefix và tên trường trong cấu hình ứng dụng.

### 11.4. Đọc cổng trước khi container khởi động

Mapped port chỉ có sau khi container đã start. Dùng supplier để trì hoãn việc lấy giá trị và bảo đảm lifecycle của Testcontainers khởi động container trước khi Spring cần giá trị đó.

### 11.5. Dùng cổng container thay cho mapped port

`8080` có thể là cổng bên trong container, nhưng client chạy trên host cần cổng host đã được ánh xạ. Với Testcontainers, dùng `getMappedPort(8080)` và `getHost()`.

### 11.6. Giả định host luôn là localhost

Trong nhiều môi trường Docker, `localhost` có thể không trỏ tới nơi container có thể truy cập từ test process. Dùng `getHost()` để lấy host được Testcontainers cung cấp.

### 11.7. Container đã dừng nhưng context còn được cache

Context vẫn có thể chứa URL cũ sau khi container kết thúc. Đồng bộ vòng đời container với context hoặc làm mới context khi cần.

### 11.8. Supplier trả về giá trị không ổn định

Một supplier nên trả về cùng endpoint trong suốt vòng đời context. Nếu mỗi lần gọi supplier lại tạo cổng hoặc URL khác, các bean có thể nhận cấu hình không nhất quán. Hãy tạo tài nguyên một lần, giữ host và mapped port ổn định, rồi để supplier đọc các giá trị đó.

### 11.9. Mong đợi @DynamicPropertySource tự khởi động dịch vụ

Annotation chỉ đăng ký property. Nếu container hoặc server chưa được start, supplier có thể không lấy được host/port hoặc client không kết nối được. Cần quản lý lifecycle bằng Testcontainers, JUnit extension hoặc cơ chế khởi động phù hợp.

## 12. Quy trình áp dụng cho một endpoint được cấp khi chạy

Khi một integration test cần kết nối tới dịch vụ có địa chỉ hoặc cổng thay đổi, có thể tiến hành theo trình tự:

1. **Xác định dịch vụ cung cấp endpoint.** Ví dụ PostgreSQL, Redis, WireMock hoặc một HTTP container.
2. **Chọn cơ chế quản lý vòng đời.** Dùng Testcontainers JUnit extension, server lifecycle của thư viện hoặc một fixture dùng chung.
3. **Khởi động tài nguyên trước khi Spring cần property.** Xác nhận host và mapped port đã có thể truy xuất.
4. **Đăng ký property bằng `@DynamicPropertySource`.** Dùng đúng tên property mà ứng dụng đọc và truyền supplier để lấy giá trị runtime.
5. **Khởi tạo client hoặc bean từ property.** Có thể dùng `@Value`, `@ConfigurationProperties` hoặc cấu hình datasource tự động.
6. **Giữ tài nguyên hoạt động trong suốt vòng đời context.** Xem xét context cache và quan hệ kế thừa giữa các test class.
7. **Xác nhận hành vi tích hợp.** Thực hiện một thao tác thực sự qua repository hoặc HTTP client để chứng minh endpoint được cấu hình đúng.

Ví dụ, với PostgreSQL container, `getJdbcUrl()` cung cấp JDBC URL có host và mapped port. Với HTTP container, kết hợp `getHost()` và `getMappedPort(containerPort)` để tạo base URL. Cả hai trường hợp đều tránh ghi cứng cổng host và cho phép test chạy trên môi trường có cách cấp cổng khác nhau.

`@DynamicPropertySource` là cầu nối giữa tài nguyên kiểm thử được cấp phát tại runtime và `Environment` của Spring. Phương thức `static` đăng ký property qua `DynamicPropertyRegistry`; supplier cung cấp host, mapped port hoặc URL khi Spring cần đọc. Khi kết hợp đúng với Testcontainers hoặc server lifecycle, quản lý context cache và tên property của ứng dụng, bài kiểm thử có thể kết nối ổn định tới các dịch vụ có địa chỉ và cổng thay đổi theo từng lần chạy.
