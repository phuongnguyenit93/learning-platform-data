# Mapped port, container network và URL từ ứng dụng đến dịch vụ trong Testcontainers

## 1. Một dịch vụ, nhiều địa chỉ — chọn URL theo nơi ứng dụng chạy

Khi viết integration test Spring Boot với Testcontainers, bạn có thể thấy container đã `STARTED` nhưng ứng dụng vẫn báo `Connection refused`, `UnknownHostException` hoặc timeout. Nguyên nhân phổ biến không phải service hỏng mà là **URL được xây cho sai vị trí của client**.

Ví dụ một HTTP service lắng nghe trong container ở **port 5678**. Docker có thể publish cổng đó ra một **host port ngẫu nhiên** như 49172. Nếu cả hai container được nối vào cùng một user-defined Docker network, service còn có thể được truy cập bằng **DNS alias** như `echo-service:5678`.

```text
                           MÁY CHẠY TEST / JVM
                         Spring Boot integration test
                                     |
                                     | http://<getHost()>:<getMappedPort(5678)>
                                     v
                    +-----------------------------------+
                    | Docker host / published TCP port  |
                    | ví dụ: host:49172 -> 5678         |
                    +-----------------+-----------------+
                                      |
                                      v
        +----------- Docker user-defined network --------------+
        |                                                       |
        |  [service container]                  [app container]  |
        |  alias: echo-service                  HTTP client      |
        |  listen: 0.0.0.0:5678                     |            |
        |          ^                                  |            |
        |          +------ http://echo-service:5678 --+            |
        |                                                       |
        +-------------------------------------------------------+
```

Các con số và tên host trong sơ đồ **chỉ để minh họa**: port host do Testcontainers cấp phát khi container khởi động, không có giá trị cố định để ghi vào cấu hình.

**Hai quy tắc quan trọng nhất:**

1. **JVM/test process → service container:** `container.getHost()` kết hợp `container.getMappedPort(INTERNAL_PORT)`, sau khi container đã start.
2. **Application container → service container trên cùng Docker network:** `http://<network-alias>:<INTERNAL_PORT>`, **không dùng mapped host port** cho đường kết nối nội bộ.

Một URL không “đúng cho mọi nơi”. Hãy luôn hỏi: **process thực sự mở socket nằm trên host, trong container nào, hay ở mạng khác?**

## 2. Các khái niệm phải phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Container port** | Port mà process dịch vụ nghe **bên trong container** | HTTP echo: `5678` |
| **Exposed port** | Port nội bộ được khai báo để Testcontainers/Docker publish ra host | `withExposedPorts(5678)` |
| **Mapped host port** | Port TCP thật trên phía host được gán cho exposed port | Ví dụ `49172`, lấy bằng `getMappedPort(5678)` |
| **Container host** | Hostname/IP nơi **test process** có thể kết nối tới published port | `getHost()`, không luôn là `localhost` |
| **Docker network** | Mạng gắn các container để giao tiếp trực tiếp | `Network.newNetwork()` |
| **Network alias** | DNS name của container trong user-defined network | `echo-service` |
| **Published port** | Cổng được NAT/forward từ host vào container | `host:49172 → container:5678` |
| **URL from the client** | URL được tạo theo môi trường thực thi **client** | `http://echo-service:5678` từ app container |
| **Binding address** | Interface mà server lắng nghe trong container | `0.0.0.0:5678` để chấp nhận kết nối từ container khác |
| **Readiness** | Dịch vụ đã đủ khả năng trả request, khác container chỉ ở trạng thái running | `Wait.forHttp("/").forPort(5678)` |

`EXPOSE` trong Dockerfile, `withExposedPorts`, `-p` của Docker CLI và URL thực của ứng dụng có liên quan nhưng **không đồng nghĩa**. Một process có thể đang nghe đúng port nội bộ mà chưa được publish ra host. Ngược lại, publish port không cứu được server chỉ lắng nghe `127.0.0.1` bên trong container khi client đến từ một địa chỉ mạng khác.

### 2.1. Phân biệt port nội bộ với port host

Giả sử Testcontainers chạy:

```java
static final int HTTP_PORT = 5678;

GenericContainer<?> echo =
        new GenericContainer<>(
                DockerImageName.parse("hashicorp/http-echo:1.0.0"))
                .withExposedPorts(HTTP_PORT);
```

Đây là đoạn minh họa, cần import `GenericContainer`, `DockerImageName`, và phải `start()` trước khi gọi `getMappedPort`. `withExposedPorts(5678)` yêu cầu ánh xạ port nội bộ 5678 thành **một host port ngẫu nhiên**. Nó **không** có nghĩa host cũng sử dụng 5678.

Sau khi start:

```java
echo.start();

String host = echo.getHost();
int hostPort = echo.getMappedPort(HTTP_PORT);
String url = "http://" + host + ":" + hostPort;
```

Trong test host-based, URL đó mới là endpoint dành cho JVM. Một biến `HTTP_PORT` gắn với service không nên bị ghi đè bằng `hostPort`: hai port có **vai trò khác nhau** và thường không trùng nhau.

### 2.2. Vì sao `getHost()` không nên thay bằng `localhost`?

Trên máy có Docker daemon cục bộ, published port thường truy cập được từ `localhost`. Nhưng trong CI, Docker-in-Docker, Docker daemon từ xa hoặc Testcontainers Cloud, host mà JVM cần kết nối tới **có thể khác**. API Testcontainers `getHost()` cung cấp địa chỉ truy cập theo môi trường được Testcontainers nhận diện.

Không áp dụng:

```java
String wrongUrl = "http://localhost:5678";
```

rồi coi đây là URL chung cho mọi nơi. Port 5678 trong chuỗi trên là **internal port**, còn `localhost` trong container khác lại chỉ **chính container ấy**.

**Đặc biệt:** `getHost()` không phải lời hứa trả về IP của chính container. Tên phương thức cũ `getContainerIpAddress()` dễ gây nhầm lẫn; Testcontainers khuyến nghị dùng `getHost()` kết hợp `getMappedPort()`.

## 3. Quy tắc chọn địa chỉ theo vị trí client

| Client ở đâu? | Service ở đâu? | Host cần dùng | Port cần dùng | Công thức |
|---|---|---|---|---|
| JVM/test runner chạy ngoài container service | Testcontainers service | `service.getHost()` | `service.getMappedPort(INTERNAL)` | `http://host:mappedPort` |
| Spring Boot app chạy ngay trong JVM test (RANDOM_PORT/NONE) | Testcontainers service | `service.getHost()` | `getMappedPort(INTERNAL)` | Inject `downstream.base-url` động |
| App container A | Service container B, **cùng Docker network** | B's network alias | B's internal port | `http://service-alias:5678` |
| App container A | Service container B ở network khác | Không có DNS alias chia sẻ | Chưa xác định | Nối cùng network hoặc thiết kế gateway/exposed route |
| Container A | HTTP server đang chạy trên máy test host | `host.testcontainers.internal` | Host port đã được `exposeHostPorts` | `http://host.testcontainers.internal:port` |
| Test process | PostgreSQLContainer | `postgres.getHost()` hoặc `getJdbcUrl()` | Mapped port 5432 | Ưu tiên `postgres.getJdbcUrl()` |
| App container cùng network | PostgreSQL container | Alias như `postgres-db` | Nội bộ `5432` | `jdbc:postgresql://postgres-db:5432/dbname` |
| App trong Docker Compose | Service Compose cùng project network | Compose service name | Internal port | `http://backend:5678` |
| App trong Kubernetes | Service nội bộ Kubernetes | Kubernetes Service DNS | Service port | URL theo Service, **không** dùng Testcontainers mapping |

**Chú ý:** app chạy trong container không nhất thiết nằm trong cùng Docker network của service chỉ vì chúng đều được Docker khởi tạo. Phải **attach vào cùng một network** hoặc cung cấp một route hợp lệ. DNS alias chỉ hoạt động theo phạm vi mạng gắn vào container.

### 3.1. Mô hình “test host → container” và “container → container” khác nhau ở lớp NAT

Trong đường host → container, Docker phải publish một cổng và NAT/forward lưu lượng vào cổng nội bộ:

```text
test JVM -> host:mappedPort -> Docker port forwarding -> container:internalPort
```

Trong đường hai container trên cùng user-defined network, client trực tiếp kết nối tới địa chỉ DNS/service của container đích:

```text
app container -> DNS echo-service -> service container:internalPort
```

Vì không đi qua host-published port, **mapped host port không có vai trò** trong URL nội bộ này. Thêm `withExposedPorts()` có thể hữu ích để JVM cũng truy cập/health-check container, nhưng không bắt buộc chỉ để hai container đã nối mạng nói chuyện bằng cổng nội bộ.

## 4. Quy trình test đáng tin cậy từ JVM tới một HTTP container

Hợp đồng ví dụ: một ứng dụng Spring Boot có endpoint `GET /api/echo`. Controller gọi `EchoGateway` qua `RestClient`, gateway lại gọi HTTP service **được Testcontainers khởi động**. Ta muốn chứng minh:
- Spring Boot **thực sự** gọi service container.
- URL dịch vụ dùng đúng **host + mapped port** lấy lúc runtime.
- Ứng dụng Spring Boot tự nghe ở **một port HTTP khác** do `RANDOM_PORT` cấp phát.
- Không hard-code cổng 5678 trên host và không khởi động mock client làm cho test xanh giả.

Chọn image `hashicorp/http-echo:1.0.0`, lắng nghe `5678`, trả text được chỉ định qua tham số `-text`. Container rất nhỏ và phù hợp một network contract test. Không dùng image `latest` để tránh việc behavior âm thầm thay đổi theo thời gian.

### 4.1. Cấu trúc project

```text
build.gradle
src/main/java/com/example/portlab/
    PortLabApplication.java
    EchoGateway.java
    EchoController.java
src/test/java/com/example/portlab/
    EchoHttpIntegrationTest.java
    ContainerNetworkTest.java
```

Ví dụ dùng **Java 17+, Spring Boot 3.5.8, Testcontainers, JUnit Jupiter và Docker/container runtime**. Nếu dự án của bạn dùng Spring Boot 4.x, điều chỉnh dependency/test API theo BOM của dự án.

### 4.2. Gradle Groovy DSL

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management chọn những phiên bản tương thích cho starter, Spring Framework, JUnit và Testcontainers. `org.testcontainers:junit-jupiter` tích hợp `@Testcontainers`/`@Container`, còn `testcontainers` chứa core classes như `GenericContainer` và `Network`.

Đây là `build.gradle` tương đối tối thiểu; muốn chạy bằng `./gradlew` cần Gradle wrapper đã tồn tại. Testcontainers cần một Docker-compatible runtime được hỗ trợ và có quyền tải image. Không cần mở sẵn port 5678 trên máy, vì Testcontainers publish host port ngẫu nhiên.

### 4.3. Spring Boot application class

Tệp `src/main/java/com/example/portlab/PortLabApplication.java`:

```java
package com.example.portlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortLabApplication.class, args);
    }
}
```

Đây là class gốc để Spring component scan tìm gateway/controller. Không chạy `main()` riêng nếu mục tiêu là integration test: JUnit sẽ khởi tạo Spring context theo `@SpringBootTest`.

### 4.4. Gateway dùng property thay vì hard-code URL

Tệp `src/main/java/com/example/portlab/EchoGateway.java`:

```java
package com.example.portlab;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class EchoGateway {

    private final RestClient client;

    public EchoGateway(
            RestClient.Builder builder,
            @Value("${demo.echo.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public String fetchMessage() {
        String text = client.get()
                .uri("/")
                .retrieve()
                .body(String.class);

        return Objects.requireNonNull(text).strip();
    }
}
```

Tại sao lại có `@Value("${demo.echo.base-url}")`?
- `EchoGateway` **không biết** container sẽ publish ra host port nào.
- Khi Spring tạo bean, property `demo.echo.base-url` được cung cấp từ **`@DynamicPropertySource`** trong test.
- Trong production, bạn có thể đặt cùng property từ environment, config server hoặc deployment manifest, nhưng giá trị production phải là URL thật theo topology deployment.
- `RestClient.Builder` được Spring Boot starter web auto-configure; `RestClient` là synchronous HTTP client. Dùng nó trong ứng dụng MVC/JUnit ví dụ này phù hợp; WebFlux thuần thường dùng `WebClient` với cùng cách chọn URL.

`Objects.requireNonNull(text)` khiến response không có body gây lỗi rõ ràng, thay vì báo test xanh với `null`. `strip()` bỏ newline cuối mà HTTP echo image có thể thêm; test bảo vệ **giá trị nghiệp vụ**, không phụ thuộc một newline của container image.

### 4.5. Controller nối endpoint app với gateway

Tệp `src/main/java/com/example/portlab/EchoController.java`:

```java
package com.example.portlab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    private final EchoGateway gateway;

    public EchoController(EchoGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/api/echo")
    public String echo() {
        return gateway.fetchMessage();
    }
}
```

Khi HTTP test gọi `/api/echo`, đường thực thi là:

```text
TestRestTemplate [JVM]
    -> Spring Boot HTTP listener [RANDOM_PORT]
    -> EchoController
    -> EchoGateway / RestClient
    -> http://<echo.getHost()>:<echo.getMappedPort(5678)>/
    -> Testcontainers HTTP echo service
    -> response "hello-from-container"
```

**Hai port động:** `@LocalServerPort` là port do **Spring Boot application** nghe; `echo.getMappedPort(5678)` là port do **Docker publish cho container dịch vụ**. Chúng là hai đối tượng độc lập, không thay thế được cho nhau.

### 4.6. JUnit integration test đầy đủ: app → container

Tệp `src/test/java/com/example/portlab/EchoHttpIntegrationTest.java`:

```java
package com.example.portlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EchoHttpIntegrationTest {

    private static final int ECHO_PORT = 5678;

    @Container
    static final GenericContainer<?> ECHO =
            new GenericContainer<>(
                    DockerImageName.parse("hashicorp/http-echo:1.0.0"))
                    .withExposedPorts(ECHO_PORT)
                    .withCommand(
                            "-listen=:5678",
                            "-text=hello-from-container")
                    .waitingFor(
                            Wait.forHttp("/")
                                    .forPort(ECHO_PORT)
                                    .forStatusCode(200));

    @DynamicPropertySource
    static void echoProperties(DynamicPropertyRegistry registry) {
        registry.add("demo.echo.base-url", () ->
                "http://" + ECHO.getHost()
                        + ":" + ECHO.getMappedPort(ECHO_PORT));
    }

    @Autowired
    TestRestTemplate http;

    @LocalServerPort
    int applicationPort;

    @Test
    void springBootReallyCallsEchoContainer() {
        ResponseEntity<String> response =
                http.getForEntity("/api/echo", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "hello-from-container",
                response.getBody());
    }

    @Test
    void applicationPortAndContainerMappingAreKnownAtRuntime() {
        assertTrue(ECHO.isRunning());
        assertNotNull(ECHO.getHost());
        assertTrue(ECHO.getMappedPort(ECHO_PORT) > 0);
        assertTrue(applicationPort > 0);

        // Không assert 2 ports phải khác nhau:
        // host port được cấp động, trùng số là có thể.
    }
}
```

**Ý nghĩa của annotations và API:**

- `@Container` đánh dấu **static container** được JUnit Testcontainers extension quản lý trong lifecycle class. Container được start trước khi các test phụ thuộc nó chạy và dừng ở cuối lifecycle tương ứng.
- `withExposedPorts(ECHO_PORT)` đề nghị publish **cổng bên trong** 5678 sang một host port bất kỳ.
- `withCommand("-listen=:5678", "-text=...")` buộc HTTP echo service lắng nghe trên tất cả interfaces, không chỉ loopback bên trong container.
- `Wait.forHttp("/")` đợi **HTTP 200 trên endpoint** thay vì chỉ chờ process/container running. Việc container đã start không chứng minh HTTP server đã sẵn sàng.
- `@DynamicPropertySource` đăng ký một `Supplier<String>` cho `demo.echo.base-url`. Supplier chỉ được gọi khi property được resolve; thời điểm đó container phải đã start để `getMappedPort` trả giá trị.
- `TestRestTemplate` gửi HTTP vào **ứng dụng Spring Boot** theo random port. Ứng dụng sau đó gọi HTTP echo container qua URL đã inject.
- `getHost()` và `getMappedPort(5678)` được đọc **lúc runtime**, không giữ một con số map port trong file cấu hình.

Hai `@Test` có mục tiêu khác nhau: test 1 thực sự kiểm tra end-to-end **test client → app HTTP → downstream container**, còn test 2 kiểm tra các điều kiện về start và mapping. **Test 2 một mình không đủ làm bằng chứng endpoint có thể kết nối được**; chỉ test 1 mới thực hiện request thật.

### 4.7. Cách chạy và kết quả mong đợi

Linux/macOS với Gradle wrapper:

```bash
./gradlew test --tests "com.example.portlab.EchoHttpIntegrationTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.portlab.EchoHttpIntegrationTest"
```

Nếu dự án dùng Maven wrapper với dependencies tương đương:

```bash
./mvnw -Dtest=EchoHttpIntegrationTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=EchoHttpIntegrationTest test
```

Khi môi trường Docker và dependencies phù hợp, ta **mong đợi** hai test methods được thực thi. Test 1 mong đợi HTTP 200 và body `hello-from-container`, test 2 mong đợi host/ports hợp lệ. **Không có stdout cố định của hai test** vì code không `System.out.println`; hãy đọc report thực tế ở `build/reports/tests/test/index.html` hoặc `target/surefire-reports/` trước khi tuyên bố runtime PASS.

## 5. `@DynamicPropertySource`: nối container URL vào Spring Boot configuration

Spring TestContext cung cấp `@DynamicPropertySource` và `DynamicPropertyRegistry` để đưa những endpoint được cấp phát **khi chạy test** vào `Environment`.

```java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("demo.echo.base-url", () ->
            "http://" + ECHO.getHost()
                    + ":" + ECHO.getMappedPort(5678));
}
```

Một method `@DynamicPropertySource` thường cần **static**, trả `void` và có đúng một tham số `DynamicPropertyRegistry`. Supplier được đánh giá **khi property được truy cập**, chứ không nhất thiết ngay lúc method đăng ký được gọi.

### 5.1. Vì sao không tạo URL trước khi container start?

Đây là anti-pattern:

```java
static final String WRONG_URL =
        "http://" + ECHO.getHost() + ":"
                + ECHO.getMappedPort(5678);
```

Nếu `ECHO` chưa được start ở giai đoạn static initialization, `getMappedPort` không có mapping và có thể ném `IllegalStateException`. Thay bằng Supplier qua `@DynamicPropertySource` hoặc code chạy **sau `container.start()`**.

Điểm tinh tế: Supplier lazy **không phải phép màu**. Nếu một bean cần property trước lúc container thật sự start, test vẫn fail. Cần điều phối lifecycle đúng, ví dụ static `@Container` do JUnit extension quản lý và Spring test context khởi tạo theo lifecycle phù hợp.

### 5.2. Property nào thuộc client, property nào thuộc server?

| Property | Thuộc về | Ý nghĩa |
|---|---|---|
| `server.port=0` / `@SpringBootTest(RANDOM_PORT)` | **Ứng dụng Spring Boot** | App HTTP server dùng port ngẫu nhiên |
| `demo.echo.base-url` | **HTTP client trong app** | Base URL của downstream service |
| `spring.datasource.url` | **JDBC client trong app** | JDBC URL tới database test |
| `spring.data.redis.host/port` | **Redis client trong app** | Endpoint Redis test |
| `spring.kafka.bootstrap-servers` | **Kafka client trong app** | Bootstrap servers đã advertise đúng topology |
| `getMappedPort(5678)` | **Testcontainers service** | Host port được publish cho cổng nội bộ 5678 |

Đừng đưa `echo.getMappedPort(5678)` vào `server.port` của ứng dụng. Cách đó không thiết lập downstream URL, mà chỉ khiến app cố nghe trên một cổng vốn có thể đã bị Docker sử dụng. Hai phía có vai trò hoàn toàn khác nhau.

### 5.3. Precedence của dynamic properties

Theo Spring TestContext, các property được đăng ký bởi `@DynamicPropertySource` có **độ ưu tiên cao** hơn `@TestPropertySource`, system properties, environment variables hoặc `@PropertySource` thông thường. Vì vậy, khi test bất ngờ kết nối tới container dù file `application-test.yml` ghi host khác, hãy kiểm tra dynamic properties.

Nếu một base class dùng `@DynamicPropertySource` cho nhiều subclasses mà mỗi subclass đổi container/endpoint, Spring context cache có thể giữ bean với URL cũ. Khi đó cân nhắc đưa lifecycle container lên phạm vi tương ứng hoặc dùng `@DirtiesContext` có chủ đích — **không cần `@DirtiesContext` cho mọi test mặc định**.

## 6. Docker network và DNS alias: app container → service container

Khi **cả client và service đều chạy trong container**, cách kết nối tự nhiên là cùng một user-defined Docker network và dùng **network alias**.

```java
try (Network network = Network.newNetwork()) {
    // Attach service và app container vào cùng network.
    // Service được gọi qua "echo-service:5678".
}
```

`Network` là tài nguyên của Testcontainers; cần import `org.testcontainers.containers.Network` và dọn sau khi test. **Không suy ra từ `withExposedPorts` rằng hai container đã nối cùng network**; chúng là hai khái niệm riêng.

### 6.1. URL theo vị trí chạy của ứng dụng

Với service container alias `echo-service`, process bên trong **client/app container** gọi:

```text
http://echo-service:5678/
```

Không gọi:

```text
http://localhost:5678/       # localhost là CHÍNH app container
http://echo-service:49172/   # 49172 là host mapped port, không phải port nội bộ
```

Đây là các giá trị minh họa; khi service dùng TLS/HTTPS, URL phải có `https`, certificates/trust configuration đúng, và container đang listen ở port tương ứng. Không tự chuyển thành HTTPS chỉ vì Docker network đã có tên alias.

**DNS alias có phạm vi mạng**. Tên `echo-service` không nhất thiết resolve trong JVM chạy trên host, vì JVM đó không nằm trong Docker DNS domain của user-defined network. Nếu muốn test JVM gọi service, dùng `getHost()+getMappedPort()` ngay cả khi container còn có network alias.

### 6.2. Bộ JUnit Testcontainers đầy đủ: container A gọi container B

Test sau khởi động một HTTP echo server và một Alpine container trên **cùng network**. Alpine dùng BusyBox `wget` gửi HTTP request tới alias của server. **Không cần biết mapped host port** để hai container nói chuyện.

Tệp `src/test/java/com/example/portlab/ContainerNetworkTest.java`:

```java
package com.example.portlab;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContainerNetworkTest {

    private static final int INTERNAL_HTTP_PORT = 5678;

    @Test
    void clientContainerUsesDnsAliasAndInternalPort() throws Exception {
        try (
                Network network = Network.newNetwork();

                GenericContainer<?> service =
                        new GenericContainer<>(
                                DockerImageName.parse(
                                        "hashicorp/http-echo:1.0.0"))
                                .withNetwork(network)
                                .withNetworkAliases("echo-service")
                                .withExposedPorts(INTERNAL_HTTP_PORT)
                                .withCommand(
                                        "-listen=:5678",
                                        "-text=from-network")
                                .waitingFor(
                                        Wait.forHttp("/")
                                                .forPort(INTERNAL_HTTP_PORT)
                                                .forStatusCode(200));

                GenericContainer<?> client =
                        new GenericContainer<>(
                                DockerImageName.parse("alpine:3.20"))
                                .withNetwork(network)
                                .withCommand("sh", "-c", "sleep 120")
        ) {
            service.start();
            client.start();

            // Chạy wget BÊN TRONG client container.
            Container.ExecResult response =
                    client.execInContainer(
                            "wget",
                            "-q", "-O", "-",
                            "http://echo-service:5678/");

            assertEquals(0, response.getExitCode());
            assertEquals(
                    "from-network",
                    response.getStdout().trim());

            assertTrue(service.isRunning());
            assertTrue(client.isRunning());
        }
    }
}
```

Đây là **JUnit test chạy với container runtime thật** khi image phù hợp. Những điểm quan trọng:

- `Network.newNetwork()` tạo một user-defined network riêng cho test.
- `service.withNetwork(network)` và `client.withNetwork(network)` nối cả hai container vào **cùng một network**.
- `service.withNetworkAliases("echo-service")` tạo tên DNS có thể được container client resolve.
- `withExposedPorts(5678)` trên service ở ví dụ này phục vụ **readiness check từ host**; command bên trong Alpine **không** dùng mapped port.
- `Wait.forHttp("/")` bảo đảm server trả HTTP 200 trước khi khởi chạy client.
- `execInContainer` chạy `wget` từ vị trí client container. Vì vậy `echo-service:5678` là endpoint **đúng thực tế** của client đó.
- `try-with-resources` đóng client, service và network khi kết thúc, giảm nguy cơ rò tài nguyên.
- `alpine:3.20` dùng BusyBox `wget` thường có sẵn. Trong một môi trường có image tùy biến không chứa công cụ này, cần dùng client image/tool tương ứng thay vì kết luận network sai.

**Phân biệt kết quả:** Một container network test xanh chứng minh DNS alias và đường container-to-container hoạt động trong network đã tạo. Nó **không tự chứng minh** rằng Spring Boot app trong JVM test đang dùng alias đó; app host-based thuộc test khác ở mục 4.

### 6.3. Nếu Spring Boot application cũng được đóng gói thành container?

Khi app chạy trong container A và backend ở container B, cấu hình app nên được cung cấp theo **địa chỉ mà container A nhìn thấy**, ví dụ:

```properties
demo.echo.base-url=http://echo-service:5678
```

Đây là **cấu hình minh họa**, chỉ hợp lệ khi cả hai container cùng network và service B dùng alias `echo-service`. Để truyền qua biến môi trường cho Spring Boot:

```text
DEMO_ECHO_BASE_URL=http://echo-service:5678
```

Spring Boot relaxed binding có thể ánh xạ tên biến môi trường này sang `demo.echo.base-url`. Test code nào khởi động app container phải cung cấp biến/connection details theo **container network**, không dùng thẳng URL `getHost()+getMappedPort()` lấy cho JVM test.

Ngược lại, nếu **Spring Boot test tự chạy trong JVM** (không ở app container), nó cần địa chỉ published host port từ `getHost()`/`getMappedPort()`, kể cả Docker daemon nằm trên máy khác. “Ứng dụng Spring Boot” không quyết định URL; **nơi process ứng dụng đang chạy** mới quyết định.

## 7. Container → host process: `host.testcontainers.internal`

Một hướng khác: server HTTP hoặc mock service chạy **trên máy test host**, còn client chạy bên trong một container. Trong trường hợp này, client container không dùng `localhost`, vì `localhost` trỏ về chính container.

Testcontainers cho phép expose một **host port** vào các container được khởi động sau đó:

```java
// Bước 1: host HTTP server đã START và đang nghe localPort.
Testcontainers.exposeHostPorts(localPort);

// Bước 2: sau đó mới start client container.
// Bên trong container, dùng:
// http://host.testcontainers.internal:<localPort>/
```

Đây là **đoạn minh họa**, có import `org.testcontainers.Testcontainers` và biến `localPort` lấy từ server thật. Không chạy độc lập nếu chưa có host server.

Thứ tự cần tuân thủ:
1. **Khởi động server trên host** và xác định port mà nó thật sự nghe.
2. Gọi `Testcontainers.exposeHostPorts(localPort)` **trước khi start** client container.
3. Khởi động client container.
4. Từ bên trong client container, gọi `http://host.testcontainers.internal:localPort/`.
5. Đóng client/server và giải phóng port sau test.

Testcontainers hỗ trợ cơ chế forwarding để địa chỉ `host.testcontainers.internal` có thể được dùng trong các môi trường Docker khác nhau. Đừng thay bằng `127.0.0.1` từ phía container. Tùy cấu hình, có thể dùng `container.withAccessToHost(true)`, nhưng việc đó **không thay thế** nhu cầu đăng ký port bằng `exposeHostPorts` khi mô hình yêu cầu.

### 7.1. Test host HTTP server có RANDOM_PORT

Giả sử Spring Boot đang chạy HTTP thật với `@SpringBootTest(RANDOM_PORT)` và `@LocalServerPort int appPort`. Nếu muốn một container client gọi lại **ứng dụng Spring Boot trên host**, bạn có thể expose chính `appPort` bằng `Testcontainers.exposeHostPorts(appPort)`, rồi mới start client container, sau đó gọi:

```text
http://host.testcontainers.internal:<appPort>/api/echo
```

**Tránh đảo thứ tự:** nếu client container đã start trước khi biết `appPort` và gọi `exposeHostPorts`, cơ chế forwarding có thể chưa sẵn sàng. Nếu một test extension tự start container quá sớm, chuyển lifecycle client container sang vị trí sau khi application server đã khởi động.

### 7.2. Host-to-container và container-to-host không đảo chuỗi URL cho nhau được

- **Host → container**: `container.getHost()` + `container.getMappedPort(internal)`.
- **Container → host**: `host.testcontainers.internal` + `localPort` đã expose.
- **Container → container**: `network alias` + `internal port`.

Đây là ba topology khác nhau. Không nên dùng chung một hard-coded `service.url` cho cả ba khi application được chạy ở các vị trí khác nhau.

## 8. PostgreSQL, Redis, Kafka: URL nào từ ứng dụng đến dịch vụ?

Một trong các lỗi quan trọng nhất khi chuyển từ HTTP container sang các dịch vụ stateful là **mỗi client có cách khai báo endpoint riêng**. Quy tắc network vẫn giống nhưng URL/connection format khác.

### 8.1. PostgreSQLContainer từ JVM Spring Boot test

`PostgreSQLContainer` tự cung cấp JDBC URL bao gồm host/port đã map và database name. Khi Spring Boot **chạy trong test JVM**, dùng:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("app_test")
                .withUsername("test")
                .withPassword("test");

@DynamicPropertySource
static void dbProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Đây là **đoạn minh họa trong `@Testcontainers` Spring Boot test**, cần imports `PostgreSQLContainer`, `Container`, `@DynamicPropertySource`, `DynamicPropertyRegistry`, dependency `org.testcontainers:postgresql` và PostgreSQL driver. Đừng tự ghép `jdbc:postgresql://localhost:5432`: `getJdbcUrl()` của container đã phản ánh mapped host port thực.

**Khi app là một container riêng cùng Docker network**, URL cho app lại theo alias/internal port:

```text
jdbc:postgresql://postgres-db:5432/app_test
```

Điều kiện là PostgreSQL container phải tham gia cùng Docker network với alias `postgres-db`; credentials/schema phải khớp. `postgres.getJdbcUrl()` thích hợp cho JVM test process, **không mặc định phù hợp bên trong một app container khác**, vì nó có thể chứa Docker host address/host-published port không cần thiết hoặc không truy cập được từ app container.

### 8.2. Redis: host, port, TLS, password

Từ JVM test:

```java
registry.add("spring.data.redis.host", redis::getHost);
registry.add("spring.data.redis.port",
        () -> redis.getMappedPort(6379));
```

Đây là ví dụ trong `@DynamicPropertySource`, với `redis` là container đã start. Nếu client Redis ở container cùng Docker network alias `redis-cache`, dùng host `redis-cache` và internal port `6379`.

Không đồng nhất TCP reachability với Redis readiness/authentication. Cần cấu hình password, ACL, TLS/scheme tương ứng và thử command thật như `PING` hoặc `SET/GET` trong test.

### 8.3. Kafka có advertised listeners

Kafka không giống HTTP/Redis chỉ cần một host/port. Client ban đầu kết nối tới **bootstrap servers**, nhưng broker trả metadata chứa **advertised listener addresses**; các broker endpoints cũng phải truy cập được từ **vị trí client**.

Do đó, trong một test JVM dùng Testcontainers Kafka container, nên lấy `kafka.getBootstrapServers()` hoặc dùng Spring Boot `@ServiceConnection` được hỗ trợ, **không tự xây** `localhost:9092`. Nếu một app container trên Docker network là client Kafka, cần broker listener được advertise cho network ấy, không chỉ một container alias làm bootstrap URL.

Một test có TCP connect tới bootstrap address nhưng fail ngay khi subscribe/publish topics có thể là **advertised listener mismatch**, không phải lỗi authentication hoặc topic.

### 8.4. HTTP/GRPC/gRPC health checks

HTTP `http://host:port`, HTTPS `https://host:port`, gRPC authority và JDBC URLs có syntax/behavior khác nhau. `getHost()+getMappedPort()` giải quyết **network address** nhưng không tự sửa:
- TLS truststore, hostname verification, mTLS identity.
- HTTP base path hoặc server context path.
- gRPC HTTP/2 transport/ALPN.
- Proxy/NO_PROXY settings.
- Redis/Kafka/PostgreSQL protocol negotiation.
- Authentication và application readiness.

**Không cố làm một TLS test xanh bằng cách tắt certificate verification cho production code.** Khi service dùng HTTPS, phải kiểm tra chứng chỉ/hostname đúng topology.

## 9. Spring Boot `@ServiceConnection` so với tự khai báo @DynamicPropertySource

Spring Boot hỗ trợ **Testcontainers service connections** qua module `spring-boot-testcontainers` và `@ServiceConnection`. Khi có connection details factory phù hợp, Boot tự tạo `ConnectionDetails` cho service như PostgreSQL, Redis, Kafka, RabbitMQ.

Ví dụ với PostgreSQL:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

Đây là **fragment** bổ sung vào build có Spring Boot BOM, không phải toàn bộ `build.gradle`.

```java
@Testcontainers
@SpringBootTest
class RepositoryIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Đây là lớp minh họa, cần imports `@Testcontainers`, `@SpringBootTest`, `@Container`, `@ServiceConnection` và JDBC/JPA application config phù hợp. Khi được Boot nhận diện, connection details có thể giúp bạn **không cần tự viết** `spring.datasource.url` và username/password.

**Không áp dụng `@ServiceConnection` bừa cho một GenericContainer HTTP echo tùy ý:** Boot cần một `ContainerConnectionDetailsFactory` hỗ trợ đúng service/connection details. Với property tùy biến `demo.echo.base-url` của ví dụ, **`@DynamicPropertySource` là lựa chọn đúng và rõ ràng**.

### 9.1. Chú ý khi vừa có ServiceConnection vừa có properties

Spring Boot cho biết **connection details có thể ưu tiên hơn connection-related configuration properties**. Nếu bạn vừa khai báo `@ServiceConnection` PostgreSQL vừa đặt `spring.datasource.url` từ nơi khác, cần xác định nguồn Boot thật sự dùng, không kết luận dựa vào một dòng `application-test.yml`.

Khi test có nhiều datasources/Redis connections hoặc dùng container tùy biến, chọn một chiến lược cấu hình nhất quán:
- Dịch vụ được Boot nhận diện: ưu tiên service connection nếu phù hợp.
- Endpoint tùy biến: dynamic properties từ `getHost()/getMappedPort()`.
- App container → container cùng network: alias/internal port trong env/config của app container.

**Không chọn endpoint ngẫu nhiên bằng cách parse log rồi đưa vào config.** Testcontainers đã cung cấp API chính thức để lấy connection details theo topology.

## 10. Readiness không phải running: Testcontainers wait strategies

Một container có trạng thái `running` chưa chắc service đã:
- Bind xong TCP port.
- Chạy xong migrations/seed dữ liệu.
- Sẵn sàng trả HTTP 200.
- Đăng ký xong broker listeners.
- Chấp nhận authentication/requests.

Ví dụ HTTP:

```java
new GenericContainer<>(
        DockerImageName.parse("hashicorp/http-echo:1.0.0"))
        .withExposedPorts(5678)
        .waitingFor(
                Wait.forHttp("/")
                        .forPort(5678)
                        .forStatusCode(200));
```

Đây là đoạn cấu hình container minh họa, chưa start. `Wait.forHttp` kiểm tra endpoint từ nơi Testcontainers có thể truy cập published port và chờ một HTTP status mong đợi, không chỉ dựa trên việc log “server started”.

| Dấu hiệu | Đã đủ để khẳng định service sẵn sàng? | Lý do |
|---|---|---|
| `container.isRunning()` | **Chưa** | Process container đang sống, app có thể chưa listen |
| `getMappedPort(internal) > 0` | **Chưa** | Docker đã gán port, không bảo đảm protocol readiness |
| TCP socket kết nối được | **Chưa chắc** | HTTP/DB migrations/auth/broker metadata còn có thể lỗi |
| HTTP health trả 200 đúng contract | Thường **phù hợp cho HTTP service** | Nhưng có thể chưa xác minh những nghiệp vụ sâu hơn |
| Database query đơn giản chạy | Có bằng chứng kết nối và schema/query phù hợp | Không tự chứng minh transaction isolation/production load |
| Test app gọi downstream và assert payload | Có bằng chứng end-to-end cụ thể | Không thay toàn bộ security/load/migration tests |

**Chọn readiness condition theo protocol.** Với PostgreSQLContainer, Testcontainers module đã có startup/waiting behavior riêng; với Redis hoặc Kafka cần kiểm tra những command/protocol quan trọng. Không dùng `Thread.sleep(5000)` để cố đoán thời gian service khởi động; test có thể flaky trên CI.

### 10.1. Timeout và logs

Nếu service không ready, xem logs của container đang lỗi:

```java
String logs = container.getLogs();
```

Đó là **đoạn minh họa**, có biến `container` là Testcontainers instance. Không ghi tràn toàn bộ logs vào CI nếu có password/token trong logs; nên redact và chỉ giữ phần cần điều tra. Cân nhắc `withStartupTimeout(Duration.ofSeconds(...))` trên container hoặc startup check strategy nếu thực sự cần, thay vì tăng timeout vô hạn.

Lỗi timeout có thể do image pull/network/Docker daemon chứ không phải do HTTP code của app. Phân biệt **container create/start**, **port binding**, **readiness**, **application call** và **assertion** thành các giai đoạn để khoanh vùng.

## 11. Remote Docker, CI, Windows, macOS và Docker-in-Docker

Testcontainers có thể làm việc với Docker Desktop trên Windows/macOS, Linux Docker daemon, CI executor hoặc môi trường Testcontainers Cloud. Sự khác biệt quan trọng nằm ở **địa chỉ mà test runner thực sự dùng để truy cập published ports**.

- Với Docker Desktop, `getHost()` thường trả hostname có thể kết nối từ JVM test; không tự kết luận mọi môi trường đều giống nhau.
- Với Docker daemon từ xa, published port có thể nằm trên **Docker host khác máy chạy JVM**. `localhost` của JVM vì vậy là sai.
- Với Docker-in-Docker, có nhiều namespace mạng: runner container, daemon container và service containers có thể khác nhau. `getHost()`/Testcontainers runtime config giải quyết một số topology, nhưng bạn vẫn phải đặt các thành phần trong mạng truy cập được.
- Với Testcontainers Cloud hoặc remote container runtimes, mapped ports được forward theo cơ chế môi trường; dùng API được Testcontainers cung cấp, không tự đoán địa chỉ Docker bridge.
- Trong CI chạy test JVM **bên trong container**, `getHost()` là đầu mối phù hợp cho đường được Testcontainers hỗ trợ; đừng thay nó bằng container IP lấy từ `docker inspect` và giả định bridge routing luôn có.
- Hạn chế firewall, corporate proxy, VPN và `NO_PROXY` có thể khiến một hostname resolve được nhưng HTTP client vẫn timeout.

**Điểm chẩn đoán:** log host, internal port, mapped port và client runtime context khi lỗi, nhưng **không log username/password/token hoặc nguyên JDBC URL nếu URL chứa secret**. Việc thay URL bằng `localhost` vì “máy em chạy được” làm test kém portable.

## 12. Port mapping và network isolation khi chạy song song

Testcontainers dùng host ports ngẫu nhiên vì chạy nhiều tests/containers song song không nên giẫm lên cùng cổng như `5432`, `6379`, `8080`.

Một số tình huống thường gặp:
- Hai PostgreSQL containers cùng listen `5432` **nội bộ**; mỗi container có host mapped port khác.
- Hai containers cùng Docker network có thể dùng `5432` nội bộ ở **hai địa chỉ/aliases khác nhau** mà không xung đột.
- Hai service có cùng network alias `db` có thể gây DNS ambiguous; cần đặt alias **khác nhau và ổn định** nếu test cần chọn đúng instance.
- Khi container restart, host mapped port **có thể đổi**; không cache URL từ instance cũ.
- Spring context cache có thể giữ client được tạo với endpoint cũ nếu container lifecycle ngắn hơn context.
- `withFixedExposedPort`/fixed host port bindings làm test dễ conflict; tránh nếu không có lý do xác định và điều phối rõ.
- Network alias chỉ resolve trong network mà container đã attach; không lấy network alias làm “public DNS name” cho tất cả test runners.

Một test chạy song song an toàn phải tránh key/database/topic trùng nhau, không chỉ tránh port conflict. Mapped ports giảm rủi ro **đụng cổng**, nhưng không thay thế isolation data state.

## 13. Spring context cache và lifecycle của container

Có một loại lỗi khó thấy: mỗi test class có static `@Container` riêng, JUnit extension dừng container khi class kết thúc, nhưng Spring TestContext có thể giữ `ApplicationContext` và `RestClient`/datasource beans đang chứa **địa chỉ container đã dừng**.

Các biểu hiện:
- Test A chạy độc lập xanh; chạy cả suite thì test B kết nối tới port cũ.
- `@DynamicPropertySource` khai báo ở superclass dùng lại cho subclasses nhưng mỗi subclass có container khác.
- Context cache tái sử dụng client bean đã resolve property ở thời điểm container A chạy.
- Container được restart khiến `getMappedPort` thay đổi nhưng bean đã được construct bằng URL cũ.
- `@ServiceConnection` dùng container lifecycle không khớp phạm vi context.

Cách xử lý:
1. Cho container sống **ít nhất lâu bằng context** được dùng với URL của nó, nếu chia sẻ context.
2. Dùng một container quản lý phù hợp trên toàn bộ test suite hoặc tách `ApplicationContext` theo cấu hình thực tế.
3. Khi dynamic endpoint thay đổi giữa các classes dùng chung base configuration, cân nhắc `@DirtiesContext` để buộc tạo context mới.
4. Không dùng `@DirtiesContext` cho tất cả test như giải pháp mặc định: nó làm tăng thời gian bootstrap, và không phải cách dọn database records.
5. Nếu test cố ý restart container, hãy tạo lại client/configuration phụ thuộc URL thay vì tiếp tục dùng bean cũ.

**Nguyên tắc:** Dù `Supplier` của `@DynamicPropertySource` là lazy, một khi Spring đã tạo `EchoGateway` với `baseUrl` cụ thể, thay đổi container mapping sau đó **không tự viết lại RestClient** bên trong bean ấy.

## 14. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân rất hay gặp | Kiểm tra và sửa |
|---|---|---|
| `Connection refused: localhost:5678` | Dùng internal port trên host, thay vì mapped port | `getHost()+getMappedPort(5678)` |
| `getMappedPort` ném `IllegalStateException` | Gọi trước khi container start | Đặt URL trong supplier/lifecycle sau start |
| `getMappedPort(5678)` không có binding | Quên `withExposedPorts(5678)` hoặc sai internal port | Khai báo exposed port và kiểm tra server thực sự listen |
| URL `http://localhost:5678` từ app container fail | `localhost` trỏ chính app container | Network alias `echo-service:5678` nếu cùng network |
| `UnknownHostException: echo-service` | App/test JVM ngoài Docker network hoặc khác network | Xác định vị trí client, attach cùng network hoặc dùng host mapping |
| TCP port open nhưng HTTP 503 | Service chưa ready, upstream config lỗi | Wait.forHttp / health endpoint và service logs |
| `Wait.forHttp` timeout | HTTP server chưa bind, sai route/status hoặc networking | Inspect container logs/port/binding/health path |
| HTTP client dùng `getMappedPort` bên trong app container | Nhầm port phía host với internal port | Dùng alias + internal port khi cùng network |
| Container khác resolve alias nhưng kết nối bị từ chối | Server chỉ bind 127.0.0.1 trong chính service container | Bind `0.0.0.0:<internalPort>` khi chấp nhận network clients |
| Test local xanh, CI fail vì localhost | Docker host/runner container/remote daemon khác | `getHost()`, CI network topology, firewall/proxy |
| `@DynamicPropertySource` không có tác dụng | Sai property key, supplier lỗi, bean không dùng property | Xem `Environment`, constructor/config client |
| `server.port` bị ghi bằng mapped port của backend | Trộn app listener với downstream service | Dùng `demo.echo.base-url` riêng |
| Test có ServiceConnection nhưng cấu hình URL bị bỏ qua | ConnectionDetails ưu tiên hơn properties | Chọn nguồn cấu hình một cách tường minh |
| PostgreSQL host test kết nối fail với 5432 | Dùng container internal port trên host | `postgres.getJdbcUrl()` |
| App container kết nối PostgreSQL bằng getJdbcUrl fail | JDBC URL có host-mapped endpoint không phù hợp container | `jdbc:postgresql://postgres-db:5432/db` cùng network |
| Kafka bootstrap connect được nhưng consumer fail | Advertised listeners không reachable từ client | Dùng module getter/service connection theo topology |
| `Connection refused` sau khi suite chạy nhiều lớp | Container đã dừng, Spring context cache giữ URL cũ | Đồng bộ lifecycle/context hoặc `@DirtiesContext` khi cần |
| Port conflict do parallel tests | Fixed host ports dùng chung | Để Testcontainers chọn random mapped ports |
| `SSLHandshakeException` dù TCP reachability tốt | Scheme, cert hostname/CA/truststore không khớp | Cấu hình HTTPS/TLS đúng, không tắt verification |
| Container → host URL không kết nối | Chưa `exposeHostPorts` hoặc gọi quá muộn | Start host service trước, expose port trước khi start container |
| Docker network alias trùng nhau | DNS tới nhiều container/đích không xác định | Đặt alias unique theo network/test |
| Sai địa chỉ khi chạy Docker Compose | Nhầm container name/service name/host publish port | Dùng Compose service DNS + internal port |
| Test “pass” mà chưa gọi backend | Chỉ assert container.isRunning() hoặc đã mock RestClient | Gọi thật qua Spring app, assert payload downstream |

### 14.1. Một chuỗi debug ngắn mà đáng tin

Khi có `Connection refused`:

1. Xác định **client chạy ở đâu**: test JVM trên host, JVM trong Docker, app container hay CI runner container.
2. Xác định service **lắng nghe trên port/interface nào** bên trong container.
3. Nếu host → container: kiểm tra `withExposedPorts`, container đã start, `getHost` và `getMappedPort` ở thời điểm kết nối.
4. Nếu container → container: kiểm tra hai bên cùng user-defined network, alias và internal port.
5. Nếu container → host: kiểm tra server host đã start trước, `exposeHostPorts` gọi trước client start, hostname `host.testcontainers.internal`.
6. Xác minh readiness bằng protocol, không chỉ `isRunning()`.
7. Tách DNS failure, TCP failure, HTTP error, authentication failure và assertion mismatch.
8. Kiểm tra Spring property thật được resolve vào bean nào; soát `@ServiceConnection`/dynamic properties precedence.
9. Kiểm tra cache/context lifecycle và container restart khi lỗi chỉ xuất hiện trong full suite.
10. Không dùng giải pháp “mở fixed port 5432/8080 trên tất cả CI hosts” để che lỗi mapping; điều đó dễ tạo race và security exposure.

## 15. Lưu ý an toàn và thiết kế môi trường test

Port mapping là một cách **mở đường truy cập mạng**. Không mặc định mọi container test đều được publish an toàn trên network công cộng.

- Chỉ expose những cổng **cần thiết** từ container; không tự publish database credentials/admin ports không dùng tới.
- Đặt tài khoản/password test riêng và database/schema cô lập.
- Với `getHost()` trả địa chỉ từ xa, xem xét security group/firewall của Docker host; đừng log secrets.
- Khi có HTTP service không authentication, chỉ dùng cho môi trường test cô lập; đừng áp dụng cấu hình đó cho production.
- Dùng Docker network riêng cho test khi cần giới hạn kết nối/container access.
- Nếu bài test yêu cầu gửi traffic ra ngoài môi trường do bạn không kiểm soát, thiết lập allowlist và không đưa production endpoints vào dynamic property sources.
- Khi service sử dụng HTTPS/mTLS, kiểm tra CA, hostname, truststore và certificate rotation như một phần contract.
- Không dựa vào `Network.newNetwork()` để bảo đảm **tuyệt đối** không có external network access: Docker container vẫn có thể có egress theo cấu hình mạng/runtime.
- Dọn containers/networks khi test kết thúc và theo dõi resource leak nếu CI jobs bị kill.

**Phân biệt isolation network với isolation dữ liệu:** một PostgreSQL database trong container riêng thường giúp test ổn định hơn, nhưng nếu các test dùng chung một container và cùng schema thì cần rollback/cleanup/unique IDs phù hợp. Network alias không tự dọn bản ghi.

## 16. Các lỗi suy luận phổ biến cần tránh

### Sai 1: “Container dùng port 5432, vậy host cũng truy cập bằng 5432”

Sai vì `withExposedPorts(5432)` thường map sang một **host port ngẫu nhiên**. Đúng là `container.getMappedPort(5432)` sau `start()`, hoặc `postgres.getJdbcUrl()` cho JDBC.

### Sai 2: “Container và app đều chạy trên cùng máy, vậy localhost dùng chung”

Sai. **Mỗi container có network namespace riêng**; `localhost` của app container chỉ đến app container. Với hai containers cùng Docker network, dùng DNS alias/container service name.

### Sai 3: “Network alias là tên DNS toàn cầu”

Sai. Alias chỉ có hiệu lực trong Docker network mà các container tham gia. JVM host có thể không resolve alias. Cần `getHost()+getMappedPort` cho host-side test.

### Sai 4: “Mapped port là thuộc tính cố định của image”

Sai. Image chỉ có thông tin nội bộ, và mapping được tạo khi container chạy. Mapping có thể thay khi start lại; không lưu host port vào source code hoặc môi trường bất biến.

### Sai 5: “Container running nghĩa là backend ready”

Sai. Chưa chắc service đã bind/ready. Dùng wait strategy đúng giao thức và assert request thực.

### Sai 6: “@ServiceConnection áp được cho mọi endpoint”

Sai. Boot cần connection details factory nhận diện service. Với một HTTP echo URL tùy biến, dùng `@DynamicPropertySource` hoặc cấu hình có chủ đích.

### Sai 7: “Một test pass trên host thì ứng dụng đóng gói container chắc chắn kết nối được”

Sai. URL của Spring app chạy trên host và URL của Spring app **chạy trong container** có thể khác hoàn toàn. Phải test đúng runtime topology.

## 17. Checklist trước khi hoàn tất test network và URL

- [ ] Đã xác định process **thực sự mở socket** nằm ở test JVM, app container hay host service.
- [ ] Biết server listen trên internal port nào và binding interface gì.
- [ ] Với JVM → container, đã khai báo `withExposedPorts(INTERNAL_PORT)`, start container trước khi lấy mapping.
- [ ] Đã dùng `getHost()` và `getMappedPort(INTERNAL_PORT)`, không hard-code localhost hoặc host port.
- [ ] Với container → container, hai container cùng network và có network alias đúng.
- [ ] URL nội bộ dùng **alias + internal port**, không dùng host-mapped port.
- [ ] Với container → host, host server start trước rồi `Testcontainers.exposeHostPorts(localPort)` trước khi start client container.
- [ ] `@DynamicPropertySource` đăng ký **supplier** và property key thực sự được HTTP/JDBC/Redis client sử dụng.
- [ ] Không nhầm `server.port`/ `@LocalServerPort` của app với port dịch vụ backend.
- [ ] Nếu dùng `@ServiceConnection`, đã kiểm tra factory phù hợp và precedence của ConnectionDetails.
- [ ] Với PostgreSQL, đã chọn `getJdbcUrl()` cho test JVM hoặc alias:5432 cho app container.
- [ ] Với Kafka, đã xác minh advertised listeners reachable từ client.
- [ ] Đã có readiness strategy, không dùng `Thread.sleep` đoán thời gian.
- [ ] Test thực sự gọi service và kiểm tra **status/body/DB query**, không chỉ kiểm tra `isRunning()`.
- [ ] Container lifecycle tương ứng Spring context cache; không giữ URL container đã dừng.
- [ ] Khi chạy CI/remote Docker, đã xử lý host/bridge/proxy/firewall đúng thay vì ép `localhost`.
- [ ] Parallel tests tránh fixed host ports, alias trùng và dữ liệu test dùng chung không được dọn.
- [ ] Không lộ credentials hoặc mở cổng production; test chạy trên môi trường cô lập.
- [ ] Đã chạy đúng test task và kiểm tra báo cáo JUnit thực tế trước khi ghi runtime PASS.

## 18. Tài liệu chuẩn để tra cứu

- [Testcontainers Java — Networking and communicating with containers](https://java.testcontainers.org/features/networking/): `withExposedPorts`, `getMappedPort`, `getHost`, host port forwarding và network aliases.
- [Testcontainers Java — JUnit 5 Quickstart](https://java.testcontainers.org/quickstart/junit_5_quickstart/): `@Testcontainers`, `@Container`, static/instance lifecycle.
- [Testcontainers Java — Waiting for containers to start or be ready](https://java.testcontainers.org/features/startup_and_waits/): HTTP/port/log/health waiting strategies.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): supplier lazy, precedence và context cache.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, connection details và tích hợp Testcontainers.
- [HashiCorp http-echo image](https://hub.docker.com/r/hashicorp/http-echo/tags): image tag `1.0.0`, command flags `-listen`/`-text`.
- [Docker — Bridge network driver](https://docs.docker.com/engine/network/drivers/bridge/): user-defined network và service DNS.
- [Docker — Publishing container ports](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/): khác biệt container internal port và published host port.

**Kết luận:** Địa chỉ service luôn phụ thuộc **nơi ứng dụng hoặc test client thực sự chạy**. JVM ngoài container dùng `getHost()+getMappedPort(internal)`; app container cùng network dùng `network alias+internal port`; container gọi host service dùng `host.testcontainers.internal` sau `Testcontainers.exposeHostPorts`. Spring Boot phải nhận đúng URL qua `@DynamicPropertySource` hoặc service connection phù hợp, sau khi container đã start và ready. Test đáng tin cậy phải thực hiện **request/DB operation thật**, kiểm tra kết quả, và giữ container lifecycle phù hợp với Spring context — không chỉ assert `isRunning()` hay hard-code `localhost`.