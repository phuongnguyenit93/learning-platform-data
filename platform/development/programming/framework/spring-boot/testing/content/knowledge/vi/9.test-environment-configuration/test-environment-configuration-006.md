# @DynamicPropertySource cho port, URL và tài nguyên tạo động trong Spring Boot Test

## 1. Tại sao cần thuộc tính động trong môi trường kiểm thử?

Trong một bài kiểm thử tích hợp Spring Boot, ứng dụng cần biết địa chỉ của database, HTTP mock server, message broker hoặc một dịch vụ phụ trợ. Những tài nguyên này thường được tạo **ngay lúc test chạy**, với cổng và URL không biết trước:

- Testcontainers ánh xạ cổng PostgreSQL `5432` trong container sang một **cổng ngẫu nhiên trên máy chạy test**.
- Một HTTP stub server lắng nghe tại cổng `0` để hệ điều hành cấp cổng còn trống.
- Một broker dùng tên host, cổng hoặc chứng chỉ chỉ có sau khi tài nguyên khởi động.
- Các test chạy song song cần endpoint riêng để tránh xung đột cổng cố định.

Nếu ghi cứng `localhost:5432`, `localhost:8080` hoặc URL của máy lập trình vào `application-test.yml`, bài test có thể xanh ở một máy nhưng thất bại trên CI hoặc chạy nhầm sang dịch vụ đang tồn tại. **`@DynamicPropertySource`** cho phép test **đăng ký property được tính từ tài nguyên đang hoạt động** vào `Environment` của Spring TestContext, trước khi các bean phụ thuộc được tạo.

Mục tiêu là để code đang kiểm tra vẫn đọc những key như `spring.datasource.url`, `partner.base-url` hoặc `messaging.bootstrap-servers` như bình thường, trong khi **test sở hữu nguồn giá trị** và quản lý vòng đời tài nguyên.

**Nguyên tắc:** tạo hoặc chuẩn bị tài nguyên kiểm thử → đăng ký tên property và cách lấy giá trị → Spring khởi tạo context → bean đọc property → test thực hiện assertion. Đừng nhầm đăng ký `Supplier` với việc tự khởi động tài nguyên.

## 2. @DynamicPropertySource là gì?

`@DynamicPropertySource` thuộc Spring TestContext Framework, trong package:

```java
org.springframework.test.context.DynamicPropertySource
```

Một method được đánh dấu annotation này thường phải là **`static`**, nhận **một tham số `DynamicPropertyRegistry`** và trả về `void`:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", () -> dynamicBaseUrl());
}
```

Đây là đoạn minh họa cú pháp: `dynamicBaseUrl()` phải được định nghĩa trong lớp test, không phải một chương trình Java độc lập. API quan trọng là:

```java
registry.add("property.name", supplierOfValue);
```

- **Tên property** là key mà bean/application thực sự đọc, ví dụ `spring.datasource.url` hoặc `demo.ping.base-url`.
- **`Supplier<?>`** cung cấp giá trị khi thuộc tính cần được phân giải. Không bắt buộc tự xây chuỗi property từ trước thời điểm đăng ký.
- Spring gắn dynamic property vào `Environment` của test context, nên `@Value`, `Environment.getProperty(...)` và cơ chế bind phù hợp có thể đọc nó.
- Dynamic properties có độ ưu tiên cao trong cơ chế Spring TestContext, thường **ghi đè các giá trị trùng key** đến từ `@TestPropertySource`, biến môi trường, system properties và application property sources được nạp.
- Method có thể được kế thừa theo hệ thống test context, nhưng sự khác biệt tài nguyên giữa các lớp con cần xử lý cẩn thận vì context cache.

**Giới hạn:** `@DynamicPropertySource` không tự cài JUnit extension, không tạo database/broker, không tự expose cổng, không kết nối tới Docker và không biến một `@ContextConfiguration` nhỏ thành toàn bộ ứng dụng Boot. Nó chỉ cung cấp giá trị động vào môi trường test.

## 3. Hiểu rõ vòng đời: đăng ký trước, giải giá trị khi cần

Đối với test tích hợp, thứ tự khái niệm thường là:

```text
Test class và tài nguyên kiểm thử được chuẩn bị
      │
      ├─ PostgreSQL container / HTTP stub / broker sẵn sàng
      │      (có thể được điều phối bởi JUnit extension hoặc mã test)
      │
      ├─ Spring TestContext phát hiện method @DynamicPropertySource
      │      registry.add("...", Supplier)
      │
      ├─ ApplicationContext bắt đầu refresh
      │      bean cần property → Environment gọi Supplier
      │
      ├─ Bean nhận URL / host / port phù hợp
      │
      └─ @Test thực thi với cấu hình đã inject
```

**Điểm tinh tế:** `registry.add` đăng ký một **supplier**, không phải lời gọi trực tiếp tới `getMappedPort` nếu ta truyền method reference hoặc lambda. Theo cơ chế dynamic properties, supplier được đánh giá khi property được phân giải; một property có thể được đọc nhiều lần. Vì vậy:

- **Khởi tạo tài nguyên phải có thứ tự hợp lý**: đến lúc Spring đọc property, server/container phải chạy hoặc đã có thông tin cổng đáng tin cậy.
- **Supplier nên trả một giá trị ổn định** trong vòng đời context. Không mở một server mới, tạo port mới hoặc reset trạng thái vào mỗi lần `get()`.
- **Đừng cố đọc mapped port trước khi container start**. Với Testcontainers, việc gọi `getMappedPort` quá sớm có thể lỗi vì cổng chưa được ánh xạ.
- **Không tạo URL bằng cách đoán cổng** hoặc chỉ lấy cổng nội bộ của container. URL phải dựa trên host và cổng **mà JVM test có thể kết nối đến**.

Ví dụ đúng về ý tưởng với một container đã được quản lý lifecycle:

```java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
registry.add("spring.datasource.username", postgres::getUsername);
registry.add("spring.datasource.password", postgres::getPassword);
```

Đây là **đoạn minh họa trong test có biến `postgres` kiểu PostgreSQLContainer**, không phải tệp độc lập. Các method reference giúp trì hoãn việc lấy URL và thông tin kết nối cho tới khi Spring thật sự cần property.

## 4. Ví dụ chạy được với Java 17+: HTTP server cổng ngẫu nhiên

Ví dụ không cần Docker, database hay mạng bên ngoài. Một HTTP server cục bộ chỉ dùng JDK 17 sẽ được bind với **port `0`**, để hệ điều hành cấp cổng trống. Test đăng ký `demo.ping.base-url` qua `@DynamicPropertySource`. Spring tạo một bean client đọc URL đó; test gửi HTTP thật tới server cục bộ và xác nhận phản hồi.

Cần một dự án có Java 17+, Spring TestContext và JUnit Jupiter. Trong dự án Spring Boot, `spring-boot-starter-test` thường cung cấp các thư viện test cần thiết. Ví dụ cố ý dùng `@ContextConfiguration` thay vì nạp toàn bộ Boot để chỉ chứng minh cơ chế **dynamic property → bean wiring → HTTP call**.

### 4.1. Client thật đọc base URL qua constructor

Tệp `src/main/java/com/example/testing/PingClient.java`:

```java
package com.example.testing;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Objects;

public final class PingClient {

    private final URI baseUri;
    private final HttpClient httpClient;

    public PingClient(URI baseUri, Duration connectTimeout) {
        this.baseUri = Objects.requireNonNull(baseUri, "baseUri");
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();
    }

    public URI baseUri() {
        return baseUri;
    }

    public String ping() {
        HttpRequest request = HttpRequest.newBuilder(
                        baseUri.resolve("/ping"))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        try {
            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " +
                        response.statusCode());
            }

            return response.body();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Ping interrupted", e);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
```

Đây là class Java thuần. `PingClient` không biết test chạy ở port nào; nó chỉ nhận `URI` lúc được tạo. `HttpClient` và `HttpServer` đều có trong JDK 17, nên ví dụ không cần thêm thư viện HTTP mock bên ngoài. Phần Spring tham gia khi đưa URL động vào constructor qua một bean configuration.

### 4.2. Test tạo server, đăng ký URL và xác nhận bean nhận đúng địa chỉ

Tệp `src/test/java/com/example/testing/PingClientDynamicPropertyTest.java`:

```java
package com.example.testing;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = PingClientDynamicPropertyTest.TestConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PingClientDynamicPropertyTest {

    private static final HttpServer SERVER = startServer();

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        PingClient pingClient(
                @Value("${demo.ping.base-url}") String baseUrl,
                @Value("${demo.ping.connect-timeout-ms}") long timeoutMs) {
            return new PingClient(
                    URI.create(baseUrl),
                    Duration.ofMillis(timeoutMs));
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("demo.ping.base-url",
                () -> "http://127.0.0.1:" +
                        SERVER.getAddress().getPort());
        registry.add("demo.ping.connect-timeout-ms",
                () -> "1000");
    }

    @Autowired
    private PingClient client;

    @Autowired
    private Environment environment;

    @Test
    void injectsDynamicallyAssignedPortAndReachesServer() {
        int port = SERVER.getAddress().getPort();

        assertTrue(port > 0);
        assertEquals(
                "http://127.0.0.1:" + port,
                client.baseUri().toString());
        assertEquals(
                client.baseUri().toString(),
                environment.getProperty("demo.ping.base-url"));
        assertEquals("pong", client.ping());
    }

    @AfterAll
    static void stopServer() {
        SERVER.stop(0);
    }

    private static HttpServer startServer() {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0),
                    0);

            server.createContext("/ping", exchange -> {
                byte[] body = "pong".getBytes(StandardCharsets.UTF_8);
                try {
                    exchange.getResponseHeaders().set(
                            "Content-Type",
                            "text/plain; charset=utf-8");
                    exchange.sendResponseHeaders(200, body.length);
                    try (OutputStream output =
                                 exchange.getResponseBody()) {
                        output.write(body);
                    }
                } finally {
                    exchange.close();
                }
            });

            server.start();
            return server;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
```

### 4.3. Điều gì đang xảy ra?

1. Trường `SERVER` tạo `HttpServer` với `new InetSocketAddress("127.0.0.1", 0)`. Cổng `0` có nghĩa **yêu cầu hệ điều hành chọn cổng khả dụng**; sau khi bind, `SERVER.getAddress().getPort()` trả về cổng được cấp.
2. `startServer()` tạo route `/ping` trả text `pong` qua HTTP và khởi động server **trước khi bean client cần URL**.
3. Method `properties(DynamicPropertyRegistry)` là `static`; nó đăng ký một supplier cho `demo.ping.base-url` và một supplier cho timeout. URL được suy ra từ cổng **đã thực sự được cấp**, không phải `8080` hay `0`.
4. `TestConfig` là cấu hình Spring tối thiểu; tham số `@Value` lấy property từ context và truyền vào constructor của client. Không có component scan rộng, không có server của Spring Boot, database hay broker.
5. `@Autowired` đưa `PingClient` và `Environment` của test context vào lớp test.
6. Test xác nhận cổng lớn hơn 0, URL trong client khớp URL dynamic property và `client.ping()` nhận chính xác `"pong"`.
7. `@AfterAll` đóng server khi lớp test hoàn thành. `@DirtiesContext(AFTER_CLASS)` giúp loại context này khỏi cache khi test class kết thúc, tránh giữ một client có URL trỏ đến server đã dừng.

Tại mỗi lần chạy, cổng có thể khác nhau. **Không có stdout cố định về số cổng**: điều được assert là mối quan hệ đúng giữa cổng thật, dynamic property và địa chỉ client. Việc test đạt nghĩa là kết nối HTTP tới stub cục bộ thành công và cơ chế inject URL hoạt động trong cấu hình đã khai báo, **không chứng minh** một dịch vụ bên ngoài hoặc full Spring Boot context hoạt động đúng.

### 4.4. Chạy test

Với Gradle wrapper (Linux/macOS):

```bash
./gradlew test --tests "com.example.testing.PingClientDynamicPropertyTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.PingClientDynamicPropertyTest"
```

Với Maven wrapper (Linux/macOS):

```bash
./mvnw -Dtest=PingClientDynamicPropertyTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=PingClientDynamicPropertyTest test
```

Các lệnh giả định đã có wrapper và runner hỗ trợ JUnit Jupiter; Gradle thường cần `useJUnitPlatform()` cho task `test`. JDK phải cung cấp module `jdk.httpserver`, có trong JDK 17. Nếu build dùng `module-info.java` với Java Platform Module System, có thể cần khai báo `requires jdk.httpserver;` trong cấu hình module phù hợp. Trong dự án Spring Boot thông thường chạy trên classpath, các tệp ở trên là đủ khi dependencies test đã được thiết lập.

Sau khi chạy, xem kết quả của đúng lớp trong `build/reports/tests/test/index.html` (Gradle task `test`) hoặc `target/surefire-reports/` (Maven Surefire). Không coi một build xanh nhưng test bị skip hoặc dùng cache là bằng chứng test được thực thi mới.

## 5. Tình huống thực tế: Testcontainers cấp JDBC URL động

Cách dùng rất phổ biến là Spring Boot integration test khởi động PostgreSQL bằng Testcontainers, rồi đẩy ba thuộc tính vào cấu hình datasource:

```java
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

Lưu ý: `getJdbcUrl()` thường chứa hostname và host-mapped port được cấp **sau khi container được khởi động**. Đăng ký method reference giúp trì hoãn truy cập thay vì đọc cổng quá sớm. Không dùng `jdbc:postgresql://localhost:5432/...` trừ khi bạn thật sự đã cấu hình Testcontainers xuất cổng cố định và có lý do test đặc biệt.

### 5.1. Một lớp test tích hợp minh họa

Ví dụ dưới đây dùng API `org.testcontainers.containers.PostgreSQLContainer` và Testcontainers JUnit Jupiter theo kiểu phổ biến ở các phiên bản Testcontainers 1.x; **tọa độ artifact/package có thể thay đổi giữa các phiên bản lớn**, vì vậy cần chọn Testcontainers và JDBC driver tương thích với dự án. Test này cần Docker/container runtime khả dụng, PostgreSQL driver và Spring JDBC auto-configuration (ví dụ `spring-boot-starter-jdbc`) cùng thư viện Testcontainers tương ứng.

Tệp `src/test/java/com/example/testing/PostgresDynamicPropertiesTest.java`:

```java
package com.example.testing;

import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        classes = PostgresDynamicPropertiesTest.TestBootConfig.class)
class PostgresDynamicPropertiesTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestBootConfig {
    }

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("catalog_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void dataSourceProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired
    private DataSource dataSource;

    @Test
    void canOpenConnectionToDynamicPostgres() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertTrue(connection.isValid(2));
        }
    }
}
```

Test trên là một integration test đầy đủ về **khả năng tạo `DataSource` và mở kết nối JDBC** với PostgreSQL đã khởi động trong môi trường Testcontainers phù hợp. Nó chưa kiểm tra entity mapping, migration, SQL query hay rollback/commit; muốn kiểm chứng những điều đó cần bổ sung test dữ liệu thích hợp. Nếu chưa có Docker hoặc thiếu dependency, test có thể thất bại ở setup trước khi tới assertion.

Trong dự án Spring Boot hỗ trợ các công cụ tích hợp Testcontainers mới hơn, ví dụ `@ServiceConnection` của Spring Boot từ dòng phiên bản hỗ trợ, có thể tự nối một số service container với auto-configuration mà không cần đăng ký thủ công mọi property. **`@DynamicPropertySource` vẫn hữu ích cho key tùy biến, HTTP stub và những tài nguyên không được tự nhận dạng.** Không dùng cả hai phương pháp để cấu hình cùng một kết nối mà không hiểu rõ thứ tự ưu tiên.

## 6. Host, container port và mapped port: đừng nhầm

Với Testcontainers, ít nhất ba khái niệm phải phân biệt:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| **Container port** | PostgreSQL lắng nghe ở `5432` bên trong container | Chỉ là cổng trong network namespace của container |
| **Mapped host port** | Docker ánh xạ sang `32785` trên host ở một lần chạy giả định | Cổng mà tiến trình JVM test có thể sử dụng từ host phù hợp |
| **Host/address của container** | Giá trị từ `container.getHost()` | Địa chỉ host phù hợp theo môi trường Docker/Testcontainers; không phải lúc nào cũng cố định `localhost` |

Nếu phải tạo URL thủ công cho một `GenericContainer`, dạng khái niệm có thể là:

```java
registry.add("demo.service.url", () ->
        "http://" + serviceContainer.getHost()
        + ":" + serviceContainer.getMappedPort(8080));
```

Đây là **đoạn minh họa**: `serviceContainer` phải là container được khai báo và khởi động, cổng `8080` phải thực sự được expose và service phải sử dụng giao thức HTTP. Đối với PostgreSQL, ưu tiên `getJdbcUrl()` của container chuyên dụng thay vì tự ghép JDBC URL từ các thành phần.

**Cổng `0` là yêu cầu cấp phát, không phải cổng để gọi.** Với HTTP server cục bộ, `new InetSocketAddress(..., 0)` yêu cầu một cổng trống; sau khi bind, lấy port thực. Với Spring Boot server chạy `webEnvironment = RANDOM_PORT`, giá trị `server.port=0` cũng là cấu hình yêu cầu cấp phát cổng; nó **không bằng số cổng được cấp**.

## 7. Phân biệt @DynamicPropertySource và @LocalServerPort

Hai annotation phục vụ các vấn đề khác nhau:

- **`@DynamicPropertySource`** đưa giá trị tài nguyên **ngoài/được tạo cho test** vào `Environment` trước khi bean phụ thuộc cần nó, ví dụ URL của PostgreSQL container hoặc mock HTTP server.
- **`@LocalServerPort`** của Spring Boot nhận **cổng thực tế mà embedded HTTP server của chính ứng dụng Boot đang lắng nghe** trong test có khởi động web server, điển hình `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

Ví dụ mẫu về Boot server (không phải lớp test đầy đủ):

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {
    @LocalServerPort
    int actualPort;

    @Test
    void portIsAssigned() {
        assertTrue(actualPort > 0);
    }
}
```

Mẫu trên cần imports và một Boot application có cấu hình web hợp lệ. **Đừng cố lấy `@LocalServerPort` từ field instance để cung cấp cho `@DynamicPropertySource` static**, vì dynamic properties thường được đăng ký trước khi test instance nhận injection; và actual port của embedded server chỉ có sau khi server khởi động. Với `RANDOM_PORT`, sử dụng `@LocalServerPort`, `WebTestClient`, `TestRestTemplate` hoặc HTTP client theo setup của Boot test.

Ngược lại, nếu Boot app **cần gọi một HTTP mock server** khi bean của nó được tạo, URL của mock server là đầu vào cấu hình và nên được cung cấp bằng dynamic property trước khi context refresh.

## 8. Ưu tiên property khi có nhiều nguồn cấu hình

Spring có thể lấy cùng key từ nhiều nguồn:

- `application.yml`, `application-test.yml` hoặc file property theo cơ chế Boot.
- `@TestPropertySource` của Spring TestContext.
- Biến môi trường, system properties, property được truyền qua command line/build.
- Những key đăng ký bằng `@DynamicPropertySource`.

Trong Spring TestContext, dynamic properties thường có **độ ưu tiên cao hơn** các nguồn đã nêu. Nếu đã khai báo `partner.base-url=http://localhost:8080` trong file test nhưng `@DynamicPropertySource` đăng ký `partner.base-url=http://127.0.0.1:<dynamicPort>`, bean thường nhìn thấy URL động.

Điều này rất hữu ích khi muốn override môi trường mặc định, nhưng cũng dễ gây nhầm:

1. **Trùng key nhưng khác tên thật sự được bind:** `partner.base-url` khác `partner.url`; cần kiểm tra `@Value` hoặc prefix của `@ConfigurationProperties` mà code đang đọc.
2. **Giá trị dynamic bị che bởi test khác hoặc cấu hình riêng của bean:** xem cách context được dựng và nguồn property của đúng bean, không dựa vào cảm giác.
3. **Supplier trả `null` hoặc throw exception:** bean đọc property có thể fail lúc context initialization.
4. **Property thay đổi sau khi bean đã tạo:** việc đổi giá trị mà supplier trả về không tự động cấu hình lại các bean đã khởi tạo và lưu giá trị cũ. Dynamic property là **cơ chế cấu hình lúc test context được dựng**, không phải hệ thống refresh bean theo thời gian thực.

Khi cần chẩn đoán, inject `Environment` vào test rồi kiểm tra key thực tế, như ví dụ `environment.getProperty("demo.ping.base-url")`. Cũng cần kiểm tra bean đã nhận giá trị đó hay chưa; chỉ thấy giá trị trong `Environment` không tự chứng minh adapter đã dùng nó để kết nối.

## 9. Context cache và tài nguyên có vòng đời riêng

Spring TestContext có thể cache `ApplicationContext` giữa các test có cấu hình tương đương. Trong khi đó, một PostgreSQL container hoặc mock HTTP server có thể được khởi động/dừng ở phạm vi từng test class.

Đây là nguồn lỗi khó chẩn đoán:
- Lớp A dựng context, supplier trả URL có port A.
- A kết thúc và dừng server/container A.
- Lớp B dùng cấu hình context tương tự nhưng tạo tài nguyên B có port B.
- Nếu Spring **tái sử dụng context đang giữ bean từ A**, client có thể vẫn trỏ port A mặc dù supplier ở B khác.

Các cách xử lý tùy phạm vi:
- Dùng một tài nguyên chia sẻ có vòng đời dài bằng hoặc dài hơn các context sử dụng nó, với cơ chế test suite quản lý rõ ràng.
- Đảm bảo test classes có cấu hình cache key khác nhau khi tài nguyên riêng của chúng thực sự khác.
- Dùng `@DirtiesContext` ở lớp hoặc thời điểm phù hợp để buộc context được bỏ khỏi cache, khi bean của context cũ đã gắn với tài nguyên sẽ dừng.
- Không tạo tài nguyên khác nhau trong các lớp con nhưng dùng nguyên trạng cùng method `@DynamicPropertySource` được kế thừa và trông đợi cache tự nhận ra mỗi port khác nhau.

Ví dụ HTTP server ở mục 4 dùng `@DirtiesContext(AFTER_CLASS)` vì server sẽ dừng ở `@AfterAll`. Cách này có chi phí dựng lại context khi test khác cần context tương tự; chỉ dùng khi có rủi ro state/lifecycle thật sự. Không thêm `@DirtiesContext` vào mọi test mà không cân nhắc hiệu năng.

**Test chạy song song:** Nếu nhiều test cùng dùng một mutable static server field hoặc `System.setProperty` toàn JVM, trạng thái có thể đụng nhau. Ưu tiên tài nguyên riêng và dynamic property đã gắn với đúng context, hoặc tài nguyên chia sẻ được đồng bộ hóa/cấu hình rõ ràng. Không thao tác `System.setProperty("spring.datasource.url", ...)` tùy tiện trong nhiều test vì nó ảnh hưởng toàn bộ JVM.

## 10. Lựa chọn cơ chế cấu hình đúng cho từng trường hợp

| Bài toán | Cơ chế phù hợp | Lý do |
|---|---|---|
| URL HTTP stub server có port được cấp tự động | `@DynamicPropertySource` + supplier trả URL sau khi server start | Property gắn với tài nguyên runtime thật |
| JDBC URL/username/password của Testcontainers | `@DynamicPropertySource` hoặc cơ chế service connection hỗ trợ của Boot | Không hard-code host/mapped port |
| Cấu hình hằng `feature.enabled=true` | `@TestPropertySource`, test properties của Boot hoặc config rõ ràng | Không cần dynamic supplier |
| Muốn kiểm tra cổng **HTTP server của ứng dụng Boot** | `@LocalServerPort` với `RANDOM_PORT` | Cổng chỉ có sau khi server chạy |
| Chỉ kiểm tra hàm thuần Java | Unit test với constructor parameters | Không cần Spring property/context |
| Cần property thay đổi trong từng test method | Tạo context/bean hợp lý cho từng trường hợp hoặc thiết kế lại injection | Dynamic property không phải công cụ đổi cấu hình live trong cùng context |
| Nhiều module/suite dùng chung container | Quản lý lifecycle và context cache rõ ràng | Tránh URL stale hoặc tài nguyên bị dừng sớm |
| Test dùng API ngoài thật | Stub/container cục bộ hoặc test môi trường chuyên biệt có kiểm soát | Tránh phụ thuộc mạng, bí mật và dữ liệu production |

**Không đưa mật khẩu thật vào mã test.** Username/password mẫu của container chỉ là thông tin test tạm thời. Với dịch vụ bên ngoài, dùng token giả hoặc secret được cung cấp an toàn cho môi trường test; tránh in URL chứa credential vào log nếu không cần thiết.

## 11. Lỗi thường gặp và cách chẩn đoán

### 11.1. Method @DynamicPropertySource không đúng chữ ký

Sai khi dùng instance method, method có tham số khác, hoặc một giá trị trả về:

```java
// Sai: không phải static method theo yêu cầu của Spring TestContext.
@DynamicPropertySource
void properties(DynamicPropertyRegistry registry) {
    registry.add("demo.url", () -> "http://127.0.0.1:9000");
}
```

Đoạn này là **ví dụ cố ý sai**, không được dùng trong test hoàn chỉnh. Cách đúng là method `static void` nhận đúng một `DynamicPropertyRegistry`. Nếu test fail trước thân `@Test`, xem thông báo discovery/configuration của Spring TestContext và stack trace.

### 11.2. Đọc mapped port trước khi container hoạt động

Sai về ý tưởng:

```java
String url = "http://" + container.getHost()
        + ":" + container.getMappedPort(8080); // Có thể quá sớm!
registry.add("demo.url", () -> url);
```

Đây là **đoạn minh họa rủi ro**, giả định `container` đã được khai báo. Cần bảo đảm container đã start trước khi truy cập mapped port; thông thường đăng ký supplier truy cập thông tin khi property cần được phân giải, ví dụ `() -> "..."+container.getMappedPort(8080)`, với vòng đời container được điều phối đúng.

### 11.3. Dùng port nội bộ như port host

Một container expose cổng `5432` không có nghĩa JVM test có thể truy cập `localhost:5432`. Lấy mapped port và host đúng, hoặc dùng API connection URL của container chuyên dụng. Trên môi trường chạy Docker từ xa, `container.getHost()` càng quan trọng.

### 11.4. Không đăng ký đúng key mà bean đọc

Nếu code dùng `@Value("${payment.gateway-url}")` mà test lại đăng ký `payment.url`, bean vẫn có thể nhận fallback từ file config hoặc fail do thiếu placeholder. Kiểm tra **key chính xác**, binding của `@ConfigurationProperties` và `Environment` trong test.

### 11.5. Supplier trả giá trị biến đổi mỗi lần gọi

Sai:

```java
registry.add("demo.url", () -> startAnotherServerAndReturnUrl());
```

Đây là **đoạn phản ví dụ**, function chưa được định nghĩa vì chỉ minh họa anti-pattern: nếu mỗi lần resolve tạo một server mới thì bean khác nhau có thể nhận URL khác nhau và rò tài nguyên. Hãy khởi tạo server theo lifecycle có chủ đích, sau đó supplier chỉ đọc địa chỉ ổn định của server đó.

### 11.6. Context cũ trỏ đến tài nguyên đã dừng

Dấu hiệu: test chạy riêng đạt nhưng chạy toàn suite fail `Connection refused` hoặc timeout, nhất là giữa các lớp dùng cùng Spring context cache. Xem thời điểm tạo/dừng container/server, giá trị URL trong bean và việc context có bị cache hay không. Dùng lifecycle thống nhất hoặc `@DirtiesContext` khi phù hợp.

### 11.7. Lẫn lộn cổng Boot app và cổng mock server

`@LocalServerPort` đọc cổng embedded server sau khi Boot khởi động; `@DynamicPropertySource` cung cấp URL mock server/container cho các bean trước khi chúng cần cấu hình. Đừng cố lấy giá trị instance-injected `@LocalServerPort` trong một static supplier hoặc dùng `server.port=0` làm cổng thật.

### 11.8. Kết luận quá rộng từ test đã pass

Một test đọc được `spring.datasource.url` trong `Environment` không chứng minh JDBC kết nối thành công. Một test `DataSource.getConnection()` thành công không chứng minh migration hoặc query JPA đúng. Một test HTTP stub `ping` thành công không chứng minh API bên ngoài thật đáp ứng cùng hợp đồng. **Assertion phải kiểm chứng ranh giới mà bài test được thiết kế để bảo vệ.**

## 12. Checklist triển khai @DynamicPropertySource an toàn

- [ ] Đã xác định property nào thực sự cần giá trị động (host, mapped port, JDBC URL, endpoint, credential test).
- [ ] Method `@DynamicPropertySource` là `static void`, nhận một `DynamicPropertyRegistry`, trong lớp test được Spring TestContext xử lý.
- [ ] Test đã tích hợp Spring TestContext qua `SpringExtension`, `@SpringBootTest` hoặc cơ chế phù hợp.
- [ ] Tài nguyên được tạo và sẵn sàng **trước thời điểm bean cần đọc** property.
- [ ] Supplier không tạo tài nguyên mới mỗi lần gọi; giá trị ổn định trong vòng đời context.
- [ ] URL dùng host và cổng **thực sự truy cập được**, không nhầm `container port`, `mapped port` hay `server.port=0`.
- [ ] Key đăng ký khớp với `@Value`, `@ConfigurationProperties` hoặc các thuộc tính auto-configuration đang được sử dụng.
- [ ] Đã kiểm tra bean thật nhận giá trị đúng, và có assertion hành vi như mở kết nối JDBC hoặc gọi HTTP stub.
- [ ] Đã xử lý việc stop/cleanup tài nguyên và context cache, nhất là khi có test classes/subclasses dùng endpoint khác nhau.
- [ ] Không dùng system properties toàn JVM hoặc cổng cố định vô tình gây xung đột khi chạy song song.
- [ ] Đã phân biệt `@LocalServerPort` của Boot với dynamic property của tài nguyên phụ trợ.
- [ ] Kết quả test được xác nhận qua task/report thực tế; không suy diễn toàn bộ hạ tầng production đã được kiểm thử.

**Kết luận:** `@DynamicPropertySource` nối **thông tin chỉ có ở thời điểm chạy test** (port, URL, credentials và tài nguyên tạm) với **Spring `Environment` trước khi bean sử dụng chúng**. Đăng ký supplier đúng chữ ký, quản lý tài nguyên sống đủ lâu, dùng host/mapped port thực tế và cân nhắc context caching sẽ giúp test Spring Boot lặp lại được trên máy phát triển và CI mà không cần hard-code địa chỉ hạ tầng.