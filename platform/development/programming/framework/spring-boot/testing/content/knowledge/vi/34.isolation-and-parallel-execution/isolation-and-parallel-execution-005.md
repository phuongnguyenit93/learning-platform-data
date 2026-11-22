# Port động và tránh tranh chấp tài nguyên mạng

## 1. Mục tiêu bài học

Trong nhóm **Cách ly và chạy song song** của **Spring Boot - testing**, một integration test không được ngầm giả định rằng cổng **8080, 8081, 9090, 5432, 6379 hoặc 8089** luôn trống. Khi chạy nhiều test classes, Gradle test forks, CI jobs, Docker containers hoặc nhiều ứng dụng trên một máy, các tiến trình có thể cùng cố bind một cổng cố định. Kết quả là lỗi **BindException: Address already in use**, test pass khi chạy riêng nhưng fail khi chạy cùng suite, hoặc test vô tình kết nối tới instance do tiến trình khác khởi động.

Giải pháp chính: **để chính server bind cổng 0, hệ điều hành cấp một cổng khả dụng, rồi đọc lại cổng thực từ server đã khởi động.** Với Spring Boot web integration test, dùng **@SpringBootTest(webEnvironment = RANDOM_PORT)** và **@LocalServerPort**. Với Java TCP listener riêng, dùng **new ServerSocket(0)**. Với downstream stub, dùng **WireMock dynamicPort**, **HttpServer bind port 0**, hoặc container mapped ports; truyền URL thật vào Spring bằng **@DynamicPropertySource** hay cơ chế service connections.

Bài dùng **Java 17, Spring Boot 3.4.5, Spring MVC, JUnit Jupiter và Spring TestContext**. Ví dụ hoàn chỉnh có endpoint **/api/ping**, endpoint proxy gọi một HTTP stub chỉ khi feature được bật, ba nhóm test:
1. **RANDOM_PORT** với HTTP client thật lấy cổng từ @LocalServerPort.
2. **@DynamicPropertySource** với downstream HTTP stub mở port 0 trước khi Boot ApplicationContext tạo.
3. **MockMvc** không mở TCP listener khi chỉ cần kiểm MVC request handling.
Thêm một plain JUnit test giữ hai ServerSocket(0) cùng lúc để minh họa cổng động và ownership.

Mục tiêu không phải sinh số port khó đoán; là **loại bỏ giả định cổng cố định, giới hạn quyền sở hữu tài nguyên và tránh race khi đặt cấu hình endpoint cho test**. Các lệnh và expected outcomes được giải thích theo source code; **không khẳng định đã thực thi Gradle/HTTP server trong lúc biên soạn**.

## 2. “Port động” nghĩa là gì?

Một TCP listener thường bind theo bộ **local address, local port, protocol và network namespace**. Nếu ứng dụng cố bind 127.0.0.1:8080 nhưng một process khác đã chiếm socket xung đột, OS sẽ từ chối theo bind/reuse rules. Việc cả hai test đều “chạy trên localhost” **không** làm cho port trở thành tài nguyên riêng cho mỗi test.

Trong Java:

~~~java
try (ServerSocket server = new ServerSocket(0)) {
    int actualPort = server.getLocalPort();
    System.out.println(actualPort);
}
~~~

Cổng **0** là yêu cầu hệ điều hành chọn cổng phù hợp khi bind. **getLocalPort()** đọc cổng thực **sau khi listener được tạo thành công**; giá trị là số dương trong khoảng port TCP hợp lệ, **không dự đoán được một số cố định**. Đây là snippet minh họa, không dự đoán stdout có thể khác nhau mỗi máy.

Trong Spring Boot:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpIntegrationTest {
    @LocalServerPort
    int port;
}
~~~

Boot khởi một **embedded web server thật**, cấu hình server port 0 và cho phép inject cổng đã bind qua **@LocalServerPort** vào test instance. Không nên assert port **chính xác bằng một con số cụ thể**. Hãy assert điều kiện hợp lệ và thực hiện HTTP request tới cổng đang dùng.

**Port động không đảm bảo tất cả tests độc lập.** Hai tests vẫn có thể ghi cùng database table, Redis key, file hoặc static singleton state. Nó chỉ giải quyết một nhóm tranh chấp tại bind/address và giúp tránh kết nối nhầm endpoint.

## 3. RANDOM_PORT khác MOCK, DEFINED_PORT và NONE

| WebEnvironment | Server socket thật | Cổng | Khi nên dùng |
| --- | --- | --- | --- |
| **MOCK** mặc định | Không | Không có local server port thực | Spring MVC controller/filter test bằng MockMvc |
| **RANDOM_PORT** | Có | OS cấp cổng khi bind | HTTP E2E mức ứng dụng, cookies, redirects, real client |
| **DEFINED_PORT** | Có | server.port hoặc mặc định 8080 | Ít dùng trong parallel integration tests |
| **NONE** | Không | Không có | Non-web context/config/service tests |

Trong Spring Boot 3.4, **@SpringBootTest không chỉ vì có chữ BootTest mà tự khởi HTTP server**. Mặc định **WebEnvironment.MOCK**, không mở listener. Nếu test dùng **@AutoConfigureMockMvc**, request đi qua mock servlet infrastructure trong process, không cần TCP port.

**RANDOM_PORT** thực sự bind socket và test có thể dùng Java HttpClient, RestClient, TestRestTemplate hoặc WebTestClient được cấu hình cho running server. Nếu user request cần cookie, redirect, session, headers qua network hoặc embedded server config, đây là test level phù hợp.

**DEFINED_PORT** dễ gây xung đột khi chạy parallel hoặc có app development đang chạy trên 8080. Chỉ dùng khi product requirement **thực sự bắt buộc một port cố định**, và test phải độc quyền giữ tài nguyên/network namespace.

**NONE** phù hợp khi bài chỉ quan tâm bean creation, @ConfigurationProperties, database service, queues hoặc background tasks không cần servlet web environment.

### RANDOM_PORT không có nghĩa unique per test method

Spring TestContext có **ApplicationContext cache**. Nếu nhiều test methods hoặc classes dùng cùng context configuration, chúng có thể được phục vụ bởi **cùng một context và cùng embedded web server**, do đó có **cùng port**. Vì vậy:
- Không assert mỗi test method nhận port khác.
- Không tạo state phụ thuộc port thay vì test identity.
- Không dùng @DirtiesContext chỉ để ép port khác nếu không có yêu cầu.
- Đừng ghép port với test name rồi coi nó là unique ID bền vững.
- Khi chạy hai JVM test forks riêng, mỗi JVM vẫn có thể bind một cổng khác nhờ port 0.

Nếu mỗi test cần process/server riêng, đó là **lifecycle isolation contract** khác với việc yêu cầu RANDOM_PORT.

## 4. TOCTOU: vì sao “tìm cổng rảnh rồi dùng sau” nguy hiểm?

Một anti-pattern:

~~~java
int candidate;
try (ServerSocket socket = new ServerSocket(0)) {
    candidate = socket.getLocalPort();
}
// Socket đã đóng: port KHÔNG còn được giữ cho mình.
startEmbeddedServer(candidate);
~~~

Đây là **trích đoạn phản ví dụ**. Khoảng thời gian giữa việc **check cổng rảnh** và **bind listener mới** là race **TOCTOU (time-of-check vs time-of-use)**. Sau khi đóng socket kiểm tra, bất kỳ tiến trình/test khác nào cũng có thể chiếm cổng đó.

Tương tự, đừng dùng:
- System command đọc netstat rồi chọn một cổng “chưa thấy có”.
- ServerSocket(0).getLocalPort() rồi close ngay để set server.port.
- Một hàm tự viết findAvailablePort(), rồi tin cổng được “reserve”.
- Một port cố định cộng test index nhưng không có ownership/lifecycle.
- Ping localhost:8089 không trả lời rồi kết luận port ấy rảnh.

**Đúng:** yêu cầu **chính server cuối cùng** bind port 0 và **giữ socket mở** trong suốt test. Lấy port từ server đang sống bằng @LocalServerPort, ServerSocket.getLocalPort(), WireMockRuntimeInfo hoặc Testcontainers.getMappedPort sau khi resource đã start.

### Khi nào nên giữ server socket tự tạo?

Nếu chính test tạo raw TCP server, giữ **ServerSocket** trong try-with-resources cho tới khi assertions hoàn tất. Nếu test muốn dùng HTTP stub, để **HTTP stub** quản lý socket port 0, thay vì dùng ServerSocket rời để “giành” port trước. Spring Boot embedded Tomcat/Jetty/Netty có lifecycle riêng: cấu hình **server.port=0**, không truyền port đoán trước.

### TIME_WAIT, SO_REUSEADDR và việc dùng lại cổng

Sau khi đóng TCP connections, OS có thể giữ connection state như TIME_WAIT; các socket options như SO_REUSEADDR/SO_REUSEPORT có semantics tùy OS. **Không dựa vào việc một port vừa giải phóng chắc chắn sẽ bind lại được ngay**, và cũng không cố “chữa” mọi BindException bằng reuse options. Port 0 với server-owned lifecycle là phương án mặc định bền vững cho tests.

## 5. Cấu trúc project thực hành

~~~text
settings.gradle
build.gradle
src/main/java/com/example/portqa/PortQaApplication.java
src/main/java/com/example/portqa/PingController.java
src/main/java/com/example/portqa/RemoteStatusProperties.java
src/main/java/com/example/portqa/RemoteStatusClient.java
src/main/java/com/example/portqa/RemoteStatusConfiguration.java
src/main/java/com/example/portqa/RemoteStatusController.java
src/test/java/com/example/portqa/RandomPortHttpTest.java
src/test/java/com/example/portqa/RandomPortRemoteStubTest.java
src/test/java/com/example/portqa/PingControllerMvcSliceTest.java
src/test/java/com/example/portqa/EphemeralPortSocketTest.java
~~~

**Ý đồ kiến trúc:** PingController không phụ thuộc upstream. RemoteStatusClient/RemoteStatusController chỉ tồn tại khi **remote.status.enabled=true**. Nhờ vậy test ping không cần start HTTP stub, còn integration test downstream có thể bật feature và đưa base URL động qua **@DynamicPropertySource**.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'spring-random-port-tests'
~~~

### 5.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll(['--add-modules', 'jdk.httpserver'])
}

tasks.named('test') {
    useJUnitPlatform()
    jvmArgs '--add-modules', 'jdk.httpserver'
}
~~~

**spring-boot-starter-web** cung cấp Spring MVC và RestClient.Builder auto-configuration. **spring-boot-starter-validation** dùng cho @NotNull trên URI config. **spring-boot-starter-test** kéo JUnit Jupiter, MockMvc, Spring TestContext và AssertJ. Java test stub sử dụng JDK module **jdk.httpserver**; Gradle cấu hình module rõ cho compile/test để dự án không dựa vào module resolver của runtime.

Không dùng Testcontainers/WireMock trong runnable project, nên chạy tests cốt lõi không cần Docker. Phần 12 có ví dụ các công cụ ấy khi project thật cần database/HTTP stubs phức tạp.

### 5.3. PortQaApplication.java

~~~java
package com.example.portqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortQaApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortQaApplication.class, args);
    }
}
~~~

Project chọn package đồng nhất com.example.portqa để component scanning tìm controllers và configuration. Không mở cổng ở static initializer hay @PostConstruct của application: Spring Boot embedded server quản lý listener trong startup lifecycle.

### 5.4. PingController.java

~~~java
package com.example.portqa;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping(
        value = "/api/ping",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }
}
~~~

Endpoint **stateless, không phụ thuộc DB/external service**. Test qua RANDOM_PORT chứng minh HTTP networking thực tế; test MockMvc chứng minh route/response mà không cần socket. Cùng một controller nhưng **hai loại bằng chứng khác nhau**.

### 5.5. RemoteStatusProperties.java

~~~java
package com.example.portqa;

import java.net.URI;

import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "remote.status")
public class RemoteStatusProperties {

    @NotNull
    private URI baseUrl;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }
}
~~~

Không hard-code http://localhost:8089 làm default. Khi bật feature, test phải truyền URL thật của stub. Trong production, application.yaml/environment cung cấp base-url. Khi feature disabled, config class ở phần sau không đăng ký properties bean nên không yêu cầu URL.

**@NotNull** chỉ chứng minh có URI; trong production có thể cần kiểm scheme HTTP(S), host, absolute URI, TLS policy và credential handling. Đừng coi việc URI parse thành công là backend healthy.

### 5.6. RemoteStatusClient.java

~~~java
package com.example.portqa;

import org.springframework.web.client.RestClient;

public final class RemoteStatusClient {

    private final RestClient client;

    public RemoteStatusClient(
            RestClient.Builder builder,
            RemoteStatusProperties properties) {
        this.client = builder
            .baseUrl(properties.getBaseUrl().toString())
            .build();
    }

    public String readStatus() {
        return client.get()
            .uri("/status")
            .retrieve()
            .body(String.class);
    }
}
~~~

**RestClient** là synchronous HTTP client của Spring Framework 6.x. Test có thể dùng local stub trên port động làm downstream thật, không mock client. Không lấy cổng từ **@LocalServerPort** để gọi downstream: cổng đó thuộc **application đang được test**, không thuộc HTTP stub.

Trong production nên cấu hình client connect/read timeouts và error handling phù hợp; bài chỉ kiểm isolation/dynamic addressing. Nếu upstream trả 503, RestClient.retrieve() thường báo HTTP status exception theo mặc định; đó là runtime resilience contract khác.

### 5.7. RemoteStatusConfiguration.java

~~~java
package com.example.portqa;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "remote.status",
    name = "enabled",
    havingValue = "true")
@EnableConfigurationProperties(RemoteStatusProperties.class)
public class RemoteStatusConfiguration {

    @Bean
    RemoteStatusClient remoteStatusClient(
            RestClient.Builder builder,
            RemoteStatusProperties properties) {
        return new RemoteStatusClient(builder, properties);
    }
}
~~~

Feature mặc định **off** (matchIfMissing=false). Test ping không cần external base URL. Test downstream dùng **remote.status.enabled=true** và **remote.status.base-url** do @DynamicPropertySource khai báo trước ApplicationContext startup.

### 5.8. RemoteStatusController.java

~~~java
package com.example.portqa;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@ConditionalOnProperty(
    prefix = "remote.status",
    name = "enabled",
    havingValue = "true")
public class RemoteStatusController {

    private final RemoteStatusClient client;

    public RemoteStatusController(RemoteStatusClient client) {
        this.client = client;
    }

    @GetMapping(
        value = "/api/remote-status",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String remoteStatus() {
        return client.readStatus();
    }
}
~~~

Khi enabled=false, controller không đăng ký route và client không cần base URL. Khi enabled=true, controller gửi request tới upstream qua RestClient, sử dụng URL được bind từ properties.

## 6. RANDOM_PORT + @LocalServerPort với HTTP client thật

**src/test/java/com/example/portqa/RandomPortHttpTest.java**

~~~java
package com.example.portqa;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "remote.status.enabled=false"
    })
class RandomPortHttpTest {

    @LocalServerPort
    private int port;

    @Test
    void realHttpRequestUsesAssignedPort() throws Exception {
        assertTrue(port > 0 && port <= 65535);

        URI uri = URI.create(
            "http://127.0.0.1:" + port + "/api/ping");

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("pong", response.body());
    }

    @Test
    void disabledProxyRouteIsAbsent() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder(
            URI.create(
                "http://127.0.0.1:" + port
                + "/api/remote-status"))
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(404, response.statusCode());
    }
}
~~~

**Điểm quan trọng:**
- @SpringBootTest(RANDOM_PORT) mở **server thật**, không phải MockMvc.
- @LocalServerPort cung cấp **port đã bind**; không đọc port trong static initializer hay constructor test.
- Request URL được dựng **trong @Test method**, sau khi Spring context/server đã startup.
- **server.address=127.0.0.1** chỉ bind loopback trong môi trường test; tránh vô tình expose endpoint test trên tất cả interfaces.
- Không assert port khác 8080 hoặc nằm trong một range ephemeral cụ thể: OS port selection có thể khác theo máy.
- Không assert các test methods có port khác nhau; Spring context cache có thể reuse một server/port.
- Endpoint proxy disabled không bị inject một upstream URL không tồn tại.

**Phân biệt lifecycle:** @LocalServerPort có ý nghĩa với web server đang chạy. Trong @WebMvcTest/@SpringBootTest(MOCK), không có real server, nên không dùng @LocalServerPort làm nguồn URL.

## 7. Downstream stub cũng phải dùng port động

Nếu app nhận config để gọi một external API, chỉ chạy application trên RANDOM_PORT **chưa đủ**. Một WireMock/MockWebServer/HttpServer nằm tại port cố định như 8089 vẫn có thể tranh chấp với test khác. Trong full project này, dùng JDK **com.sun.net.httpserver.HttpServer** bind 127.0.0.1:0, khởi động trước Spring application context, rồi truyền base URL động vào app qua **@DynamicPropertySource**.

**src/test/java/com/example/portqa/RandomPortRemoteStubTest.java**

~~~java
package com.example.portqa;

import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RandomPortRemoteStubTest {

    // Stub đã start trước khi Spring cần resolve properties.
    private static final HttpServer STUB = startStub();

    @LocalServerPort
    private int appPort;

    @DynamicPropertySource
    static void remoteStatusProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "remote.status.enabled", () -> "true");
        registry.add(
            "remote.status.base-url",
            () -> "http://127.0.0.1:"
                + STUB.getAddress().getPort());
    }

    @Test
    void appProxyCallsDynamicUpstreamPort() throws Exception {
        int stubPort = STUB.getAddress().getPort();

        assertTrue(appPort > 0);
        assertTrue(stubPort > 0);

        URI appUri = URI.create(
            "http://127.0.0.1:" + appPort
            + "/api/remote-status");

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        HttpRequest request = HttpRequest.newBuilder(appUri)
            .timeout(Duration.ofSeconds(4))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("upstream-ready", response.body());
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    private static HttpServer startStub() {
        try {
            InetSocketAddress address = new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0);

            HttpServer server = HttpServer.create(address, 0);

            server.createContext("/status", exchange -> {
                byte[] bytes = "upstream-ready".getBytes(
                    StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                    "Content-Type",
                    "text/plain; charset=UTF-8");

                exchange.sendResponseHeaders(
                    200, bytes.length);

                try (OutputStream out =
                        exchange.getResponseBody()) {
                    out.write(bytes);
                }
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
~~~

### Tại sao cách trên không race?

**STUB** tự bind port 0 và giữ socket trong suốt test class. **@DynamicPropertySource** đăng ký một **Supplier** lấy đúng base URL từ STUB đã start. Spring Boot tạo RemoteStatusProperties/RemoteStatusClient khi load context và sử dụng cổng của stub thực, không phải cổng đoán.

**@LocalServerPort** là **application inbound port**; **STUB.getAddress().getPort()** là **upstream outbound destination port**. Hai cổng thuộc hai servers khác nhau. Test chỉ kết nối tới app inbound port, còn app RestClient đi tới stub outbound port. Không đảo hai chiều.

**@DirtiesContext(AFTER_CLASS)** là lựa chọn có chủ đích ở ví dụ để ngăn context có bean trỏ tới stub đã dừng bị cache/reuse trong một class khác. Không lạm dụng @DirtiesContext cho toàn bộ suite; nếu dùng test-owned reusable stub lâu sống theo shared context lifecycle, có thể giảm context recreation khi đảm bảo không có stale endpoint. **@AfterAll** dừng STUB để không rò socket/thread.

Không khẳng định appPort nhất thiết khác port của test class khác: Spring TestContext cache và OS allocation quyết định điều đó. Không kiểm “hai số ngẫu nhiên khác nhau” thay vì kiểm request thực tế hoạt động.

### Vì sao không dùng @LocalServerPort trong @DynamicPropertySource?

@DynamicPropertySource được sử dụng **khi Spring chuẩn bị tạo ApplicationContext**; @LocalServerPort chỉ sẵn có **sau khi embedded server bind thành công**. Nếu cấu hình external client cần app server port ngay trong Spring context initialization, sẽ có vấn đề vòng phụ thuộc lifecycle. Với downstream stub, resource **phải start trước context**, nên Supplier của @DynamicPropertySource là lựa chọn phù hợp.

Nếu consumer chỉ cần URL của **application under test**, tạo URL trong test method sau @LocalServerPort injection hoặc dùng test client được Boot cấu hình phù hợp. Không gán @DynamicPropertySource dựa vào một non-static @LocalServerPort field khi field chưa được inject.

## 8. Khi không cần socket: MockMvc hoặc @WebMvcTest

**src/test/java/com/example/portqa/PingControllerMvcSliceTest.java**

~~~java
package com.example.portqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PingController.class)
class PingControllerMvcSliceTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void pingRouteWorksWithoutOpeningHttpPort() throws Exception {
        mockMvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }
}
~~~

**@WebMvcTest** là MVC slice test: nó khởi servlet test infrastructure, không bind real HTTP socket. Nếu chỉ cần kiểm mapping, validation, serialization, response status, controller advice hoặc Spring MVC filter interactions, đây thường là cách **nhanh và tránh network collision hoàn toàn**.

**@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc** là lựa chọn khác nếu cần full Spring beans nhưng không cần TCP. Đừng bật RANDOM_PORT cho mọi controller test khi một MockMvc test đã đủ. Ngược lại, MockMvc không chứng minh embedded server port, TLS real socket, actual HTTP redirects/cookies qua network hay proxy configuration.

Trong project mẫu, **PingController** độc lập; @WebMvcTest(PingController.class) không cần RemoteStatusClient. Nếu một controller slice có dependencies riêng, khai báo test fixtures hoặc **@MockitoBean** đúng boundary; không thêm toàn bộ external integration chỉ để slice khởi động.

## 9. Test Java socket thuần chứng minh hai listener có thể cùng tồn tại

**src/test/java/com/example/portqa/EphemeralPortSocketTest.java**

~~~java
package com.example.portqa;

import java.net.InetAddress;
import java.net.ServerSocket;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EphemeralPortSocketTest {

    @Test
    void twoLiveSocketsOwnDifferentAssignedPorts()
            throws Exception {

        InetAddress loopback =
            InetAddress.getByName("127.0.0.1");

        try (ServerSocket first =
                new ServerSocket(0, 50, loopback);
             ServerSocket second =
                new ServerSocket(0, 50, loopback)) {

            int firstPort = first.getLocalPort();
            int secondPort = second.getLocalPort();

            assertTrue(firstPort > 0);
            assertTrue(secondPort > 0);
            assertNotEquals(firstPort, secondPort);
        }
    }
}
~~~

**Tại sao đoạn này đáng tin hơn tự tìm free port?** Cả hai socket **vẫn đang giữ listener** khi assertions diễn ra; OS không thể cấp cùng bind endpoint cho hai listeners TCP thông thường đang sống với các options mặc định. Socket được đóng qua try-with-resources kể cả khi assertion fail.

**Giới hạn:** hai ports khác nhau trong một test không có nghĩa hai test processes độc lập luôn phải dùng số khác nhau trong mọi thời điểm. Port có thể được tái sử dụng sau khi listener đóng. Test không nên đưa giá trị port vào database key hoặc snapshot rồi so sánh qua các lần chạy CI.

## 10. @DynamicPropertySource và thứ tự lifecycle

**@DynamicPropertySource** trong Spring Framework 6.2 yêu cầu **static method** nhận **DynamicPropertyRegistry**. Nó đăng ký các **Suppliers** để Spring Environment lấy dynamic values khi cần, thường cho URL/port của resource mà test tự khởi động.

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("remote.status.base-url",
        () -> "http://127.0.0.1:"
            + STUB.getAddress().getPort());
}
~~~

Trong ví dụ đầy đủ, STUB được khởi tạo và started ở static field initializer, nên Supplier có cổng hợp lệ khi context bind. Một thiết kế dễ lỗi là khởi external stub trong **@BeforeEach**, nhưng Spring ApplicationContext có thể đã được tạo **trước @BeforeEach**, nên property được resolve quá sớm. **Khởi resource trước context** bằng static lifecycle, Spring-managed @TestConfiguration bean/service connection hoặc lifecycle extension đã được chứng minh thứ tự startup.

### Tránh stale property do context cache

Spring TestContext cache ApplicationContext theo cấu hình. Nếu static stub của một test class được stop và class khác kế thừa cùng @DynamicPropertySource method nhưng dùng port mới, context cache có thể giữ base URL cũ. Các cách sửa:
- Resource sống cùng hoặc lâu hơn cached context.
- Dùng @DirtiesContext **có chọn lọc** khi endpoint/lifecycle thay đổi.
- Tách test classes với distinct configurations/context cache keys.
- Dùng Spring Boot 3.4 **@ServiceConnection** / container as bean khi phù hợp.
- Không ghi port động vào global System.setProperty hay static shared mutable field từ nhiều tests parallel.

**@DynamicPropertySource không phải công cụ để publish cổng của app RANDOM_PORT cho chính app trước khi nó khởi động**. Dùng nó để đưa cổng của **resource bên ngoài đã được start** vào ApplicationContext.

### Port selection và race trong JUnit extensions

Nếu dùng WireMockExtension, MockWebServer hoặc Testcontainers-managed resources, hãy kiểm **extension lifecycle** trước khi đăng ký dynamic property Supplier. Supplier lazy có thể giúp, nhưng nếu context được tạo trước khi extension start, lấy port khi chưa mở sẽ fail. Với resource có lifecycle do Spring quản lý, Spring Boot service connection/bean configuration có thể an toàn hơn. Không chỉ copy snippet khi thứ tự extension hooks chưa rõ.

## 11. Testcontainers: port trong container khác port trên host

Với Docker, có hai không gian địa chỉ:
- **Container port**: ví dụ PostgreSQL **5432** bên trong container.
- **Host mapped port**: Docker/Testcontainers chọn cổng host để test JVM truy cập.

Đừng hard-code **localhost:5432** trong test JVM rồi kết luận đang gọi PostgreSQL container. Khi nhiều containers cùng expose 5432, mỗi container có thể được map ra một **host port khác nhau**.

Một ví dụ minh họa, **không thuộc runnable project**:

~~~java
@Testcontainers
class PostgresMappedPortExample {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @Test
    void useMappedEndpointAfterStart() {
        assertTrue(postgres.isRunning());

        String host = postgres.getHost();
        int mappedPort =
            postgres.getMappedPort(5432);

        assertTrue(mappedPort > 0);
    }
}
~~~

Cần Testcontainers JUnit Jupiter + PostgreSQL dependencies, imports và Docker daemon. **getMappedPort(5432)** chỉ dùng **sau khi container đã start**. Trong thực tế với PostgreSQLContainer, ưu tiên **postgres.getJdbcUrl()**, getUsername()/getPassword() hoặc Spring Boot **@ServiceConnection** thay vì tự ghép JDBC URL.

Spring Boot 3.4 hỗ trợ:

~~~java
@Container
@ServiceConnection
static PostgreSQLContainer<?> db =
    new PostgreSQLContainer<>("postgres:16");
~~~

Đây là **trích đoạn minh họa** của test với @Testcontainers/@SpringBootTest và spring-boot-testcontainers. @ServiceConnection cung cấp **ConnectionDetails** có precedence so với datasource connection-related properties được hỗ trợ. Không hiểu nó như việc DB đã chạy nếu Testcontainers extension chưa start hoặc Docker không sẵn sàng. Không dùng @ServiceConnection để thay production secrets một cách vô tình trong test configuration correctness.

### Tránh fixed host port binding trong Testcontainers

Không ép mọi test container cùng bind host port 5432 hoặc 6379. Testcontainers mặc định map exposed container ports sang host ports động. Khi cần nhiều service gọi nhau trong Docker, ưu tiên **Docker network aliases/hostnames** trong cùng network thay vì đưa mọi service ra fixed host ports.

Nếu một test cố bind fixed host port, nó xung đột với local PostgreSQL, Docker process khác hoặc parallel CI worker. Chỉ dùng fixed binding khi integration requirement bắt buộc và resource được quản lý độc quyền.

## 12. WireMock và MockWebServer: giữ port động

WireMock JUnit Jupiter **@WireMockTest** mặc định có thể chạy stub trên một port ngẫu nhiên, và **WireMockRuntimeInfo** cung cấp port/baseUrl thực. Với programmatic WireMockExtension có thể cấu hình **dynamicPort()**.

Ví dụ minh họa, **không thuộc runnable project**:

~~~java
@WireMockTest
class ExternalApiStubExample {

    @Test
    void stubUsesAssignedPort(
            WireMockRuntimeInfo runtimeInfo) {

        String baseUrl = runtimeInfo.getHttpBaseUrl();
        assertNotNull(baseUrl);

        // Cấu hình client dưới test trỏ tới baseUrl.
    }
}
~~~

Đoạn trên cần WireMock JUnit Jupiter dependency và imports của org.wiremock.junit5; tên API cụ thể theo phiên bản WireMock đã khóa. Không giả định port 8080/8089. Lưu ý **@WireMockTest** vốn xử lý extension lifecycle; nếu Spring ApplicationContext cần URL stub lúc startup, phải tích hợp lifecycles đúng thứ tự (ví dụ static WireMockServer started before context + @DynamicPropertySource hoặc Spring-managed stub bean). Chỉ lấy runtimeInfo trong @Test method là **quá muộn** nếu client bean đã đọc base URL khi Spring context khởi động.

MockWebServer (OkHttp) cũng có thể start trên port 0 và cung cấp **server.url("/").toString()** khi server đã chạy. Tất cả các thư viện cần **chỉ một nguồn sự thật cho port**: runtime server API, không phải một free-port helper riêng.

## 13. Management server: cổng thứ hai thường bị bỏ sót

Nếu Spring Boot application đặt **management.server.port** khác với application server port, có thể có **hai web listeners**. Theo tài liệu Spring Boot 3.4, **@SpringBootTest(RANDOM_PORT)** cũng sử dụng một **management port ngẫu nhiên riêng** khi có cấu hình management server trên port khác.

Không dùng application **@LocalServerPort** để gọi /actuator/health trên management connector riêng. Phải đọc đúng **local management port**/management endpoint URL theo version hoặc test client config và giữ clear distinction inbound application vs management listener.

Nếu cần ví dụ với Actuator:
- thêm **spring-boot-starter-actuator**;
- cấu hình management.server.port theo test policy;
- bảo vệ endpoint/mạng loopback;
- xác minh cổng management thực thay vì giả định 9000/8081;
- chỉ assert readiness/liveness khi Actuator health groups được bật phù hợp.

**Bài runnable không mở management server riêng**, nên không có cổng phụ vô tình tranh chấp. Trong ứng dụng thật, xem cả debug/JMX/RMI port, Prometheus exporter standalone, gRPC server, embedded LDAP/FTP, Kafka broker stubs và service discovery/test proxies — chúng có thể là nguồn BindException không liên quan server.port.

## 14. Network namespaces, localhost và Docker

**127.0.0.1** trong test JVM là loopback của **network namespace nơi JVM chạy**. Nếu JVM chạy trên host mà backend nằm trong Docker container, **localhost của JVM không phải localhost của container**. Nếu hai containers cùng Docker network, mỗi container có loopback riêng.

Các trường hợp:
- Host JVM → Testcontainers DB: dùng **container.getHost() + mapped port** hoặc service connection.
- Container A → Container B cùng Docker network: dùng **network alias + container port**, không dùng host mapped port mặc định.
- CI service container → app container: cấu hình tên service/network do CI cấp.
- Kubernetes pod → service: dùng DNS/service discovery; không dùng localhost trừ khi thực sự cùng pod/network namespace.
- Server bind **0.0.0.0** có thể nhận từ nhiều interfaces; test muốn giới hạn exposure nên bind **127.0.0.1** khi phù hợp.

**Không suy cổng động bằng đọc server.port trong Environment sau khi bind.** Giá trị cấu hình 0 có thể vẫn được giữ là 0, còn port thực nằm trong WebServer và @LocalServerPort. Tương tự, container port cố định 5432 khác mapped port trên host.

## 15. Parallel tests: socket chỉ là một loại shared state

Nếu bật JUnit parallel execution hoặc Gradle maxParallelForks, các nguồn đụng nhau bao gồm:

| Tài nguyên | Tranh chấp | Chiến lược |
| --- | --- | --- |
| Embedded Spring web server | Cùng fixed 8080 | RANDOM_PORT |
| HTTP mock server | Cùng 8089 | dynamicPort/port 0 |
| Database container | Host port 5432 | Testcontainers dynamic mapping |
| Redis/Kafka test services | Fixed published ports | Mapped dynamic ports/network alias |
| Database rows | Cùng table/IDs | Unique IDs, schema-per-test/transaction isolation |
| Filesystem output | Cùng file path | @TempDir/unique temp directories |
| Static singleton/cache | Dữ liệu cross-test | Reset/immutable fixtures, avoid globals |
| Spring ApplicationContext | Cached mutable beans | Per-test data isolation, selective DirtiesContext |
| System properties | Shared JVM global | Test-scoped properties/config |
| WireMock stubs | Shared mutable expectations | Per-test server/reset/isolated instance |
| External API quota | Shared account/rate-limit | Fake/stub, controlled integration job |

**@SpringBootTest(RANDOM_PORT)** giải quyết bind conflict của app server, **không tự giải quyết database transactions**. Ví dụ HTTP client và server chạy ở threads khác; **@Transactional trên test method không rollback tự động transaction do server request tạo ra**. Nếu test ghi DB qua real HTTP, phải cleanup dữ liệu/test schema theo contract, không trông chờ test-managed transaction rollback.

### Test instance lifecycle và shared state

JUnit Jupiter mặc định tạo test instance **PER_METHOD**, nhưng static fields, Spring singleton beans và cached contexts vẫn dùng chung. Đặt @TestInstance(PER_CLASS) hoặc @Execution(CONCURRENT) mà mutate shared state thì phải tự quản thread safety.

Không dùng một global static String currentBaseUrl bị nhiều tests ghi chồng; các test classes chạy parallel có thể kết nối nhầm stub của nhau. Dùng test-scoped immutable URI, @DynamicPropertySource có đúng lifecycle hoặc DI per-context. Không đặt port/URL từ một test class vào system property rồi kỳ vọng class khác không đụng.

### Khi buộc phải dùng fixed resource

Nếu requirement cần fixed port vì protocol/hạ tầng không hỗ trợ dynamic, phải bảo đảm **exclusive ownership** qua JUnit ResourceLock, CI job isolation, unique network namespace, fork/namespace riêng hoặc một singleton test resource có lifecycle phù hợp. @ResourceLock chỉ đồng bộ **trong phạm vi JUnit execution sử dụng cơ chế đó**, không khóa các JVM/CI workers khác; đừng coi nó như OS distributed lock.

## 16. HTTP client timeouts và readiness khi dùng port động

Một cổng vừa bind không đảm bảo business endpoint sẵn sàng xử lý. Trong Spring Boot RANDOM_PORT, @LocalServerPort được inject sau khi embedded server startup; test có thể gọi HTTP trực tiếp. Với external stub/container:
- khởi resource trước khi bind properties;
- chờ **readiness condition**, không chỉ process created;
- dùng **bounded connect/request timeouts**;
- kiểm return status/body contract thay vì chỉ socket connect;
- không dùng Thread.sleep(2000) đoán rằng server đã sẵn sàng;
- đóng resource sau tests, tránh leak ports/threads.

Một network failure đáng báo:
- **BindException: Address already in use** → listener local không bind được, thường là tranh chấp port/address.
- **ConnectException: Connection refused** → client gọi host/port chưa có listener hoặc route bị từ chối.
- **SocketTimeoutException / HttpTimeoutException** → thời gian chờ vượt budget.
- **UnknownHostException** → DNS/name resolution, thường khác với bind collision.
- **SSLHandshakeException** → TLS trust/certificate/protocol, không chữa bằng RANDOM_PORT.

**Không bắt mọi exception rồi retry không giới hạn.** Nếu cố định sai URL, retry chỉ làm test lâu hơn. Debug phải phân biệt port bị chiếm, chưa start, client dùng cổng sai hay remote protocol lỗi.

### Tránh IPv4/IPv6 mismatch

localhost có thể resolve thành **::1** (IPv6) trên một máy và **127.0.0.1** (IPv4) trên máy khác. Nếu stub bind riêng 127.0.0.1 mà client gọi localhost và OS ưu tiên IPv6, test có thể fail dù port đúng. Runnable example nhất quán bind và call **127.0.0.1**. Khi cần IPv6, cấu hình address rõ và test cả hai theo requirement.

## 17. Những anti-pattern đáng tránh

| Anti-pattern | Tại sao lỗi | Thay bằng |
| --- | --- | --- |
| @SpringBootTest(DEFINED_PORT) cho mọi HTTP test | Xung đột 8080 | RANDOM_PORT |
| Đặt server.port=8080 trong test profile | Shared fixed port | Port 0 |
| “Find free port” rồi close socket | TOCTOU race | Server thật bind 0 |
| Đọc @LocalServerPort trong static setup | Chưa có server/context | Đọc sau startup |
| Assert mỗi @Test nhận port khác | Context cache reuse | Assert HTTP behavior |
| Dùng @LocalServerPort làm stub port | Nhầm app/stub roles | Stub.getAddress().getPort() |
| Mock server giữ cố định 8089 | Parallel collision | dynamicPort |
| Testcontainers bind host fixed 5432 | Collision với host Postgres | getMappedPort / @ServiceConnection |
| Lấy getMappedPort trước start | Chưa có mapped port | Start container trước |
| Hard-code localhost trong Docker container | Sai namespace | Container network alias/host mapped endpoint |
| HTTP integration mọi controller case | Slow/network overhead | MockMvc/WebMvcTest khi đủ |
| Dùng port để làm unique test ID | Port tái sử dụng/context cache | UUID/correlation ID |
| Ràng buộc port vào global System property | Parallel tests overwrite nhau | DynamicPropertySource/context config |
| @DirtiesContext cho mọi test | Chậm và che shared state | Chỉ dùng khi lifecycle yêu cầu |
| Dừng shared stub khi cached context còn dùng | Stale URL/connection refused | Align resource/context lifecycle |
| Dùng Thread.sleep chờ server | Flaky trên CI | Start lifecycle và bounded readiness |
| Port khác nhưng DB chung | Cross-test data collision | DB fixture/schema isolation |
| @Transactional HTTP test tự rollback server writes | Khác threads/transactions | Cleanup qua API/DB |
| Bắt mọi BindException rồi retry mãi | Che race/config errors | Fix port/lifecycle |
| Chỉ assert response 200 mà body không đúng | Có thể kết nối nhầm process | Assert deterministic payload |
| Bind 0.0.0.0 không cần thiết | Expose trên network của CI | Bind loopback khi có thể |

## 18. Lệnh chạy và kết quả kỳ vọng

Với Java 17 và Gradle Wrapper tương thích:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.portqa.RandomPortHttpTest
./gradlew test --tests com.example.portqa.RandomPortRemoteStubTest
./gradlew test --tests com.example.portqa.PingControllerMvcSliceTest
./gradlew test --tests com.example.portqa.EphemeralPortSocketTest
~~~

Trên Windows dùng **gradlew.bat**. Nếu chưa tạo Wrapper scripts, dùng Gradle đã cài hoặc tạo Gradle wrapper trước; build.gradle không tự bao gồm ./gradlew. Các outcomes dưới đây là **kỳ vọng theo assertions**, không phải stdout một phiên chạy thực tế.

| Test | Điều phải đúng |
| --- | --- |
| realHttpRequestUsesAssignedPort | @LocalServerPort >0, HTTP /api/ping 200 body pong |
| disabledProxyRouteIsAbsent | HTTP /api/remote-status trả 404 khi feature off |
| appProxyCallsDynamicUpstreamPort | App HTTP 200 body upstream-ready từ stub port động |
| pingRouteWorksWithoutOpeningHttpPort | MockMvc 200, body pong, không cần socket |
| twoLiveSocketsOwnDifferentAssignedPorts | Hai ServerSocket đang sống có ports hợp lệ khác nhau |

**Không in/cố định port thực trong expected output**: mỗi JVM/CI run có thể nhận con số khác. Nếu test thất bại, ghi diagnostic thực gồm appPort/stubPort và bind address ở log test, nhưng tránh đưa secret/url chứa credentials vào artifacts.

## 19. Bài tập tình huống

**Tình huống A.** Hai classes đều dùng @SpringBootTest(RANDOM_PORT), nhưng cùng một cached ApplicationContext. Có cần hai ports khác? **Không**. Context reuse nghĩa server/port có thể giống, vẫn đúng. Test data phải được cô lập riêng.

**Tình huống B.** Stub chạy trên 8089, app chạy RANDOM_PORT; suite chạy parallel vẫn fail BindException. **Stub vẫn cố định 8089**. Chuyển stub sang dynamicPort và inject URL.

**Tình huống C.** Test dùng new ServerSocket(0), lấy port rồi close trước khi start app trên port đó. Race còn không? **Có**. Đó là TOCTOU; hãy để app bind port 0 trực tiếp.

**Tình huống D.** @DynamicPropertySource supplier cần URL nhưng stub chỉ start ở @BeforeEach. Có an toàn không? **Không bảo đảm**; Spring context có thể khởi trước @BeforeEach. Khởi stub trước context.

**Tình huống E.** Docker container expose 5432, test JVM dùng localhost:5432. Đã đúng chưa? **Không**, phải lấy container.getHost()/getMappedPort(5432) hoặc JDBC URL/service connection.

**Tình huống F.** AppPort được inject qua @LocalServerPort nhưng client test dùng localhost:8080. Bug ở đâu? Test **bỏ qua actualPort**.

**Tình huống G.** RANDOM_PORT giải quyết database rows trùng ID giữa tests? **Không**, chỉ socket binding.

**Tình huống H.** MockMvc test route không cần socket mà test vẫn dùng RANDOM_PORT. Cần không? **Không**, có thể dùng @WebMvcTest hoặc MOCK + @AutoConfigureMockMvc.

**Tình huống I.** Server bind 127.0.0.1, client gọi localhost và resolve ::1; có thể refused? **Có**. Dùng address family nhất quán.

**Tình huống J.** Vì sao test không assert port thuộc range 49152–65535? **Ephemeral port range cấu hình theo OS**, không phải fixed contract của Boot.

**Tình huống K.** @DirtiesContext(AFTER_CLASS) tại stub test có ý nghĩa? **Đóng context được cấu hình tới stub mà test đã stop**, tránh reused stale endpoint. Không cần cho mọi case.

**Tình huống L.** Nếu management.server.port khác server.port thì sao? Có **hai listeners**, test phải lấy đúng management endpoint port.

**Tình huống M.** Có thể dùng port khác cho mỗi CI job nhưng vẫn dùng một Redis key không? **Có tranh chấp dữ liệu**. Cần key namespace/isolated instance.

**Tình huống N.** Một cổng vừa bind nghĩa HTTP API đã sẵn sàng mọi chức năng? **Không**. Kiểm endpoint/health thực tế.

**Tình huống O.** JUnit @ResourceLock("port8080") có khóa được máy CI khác? **Không**, chỉ đồng bộ trong phạm vi JUnit runtime nơi lock được quản lý.

## 20. Checklist QA cho test chạy song song

- Không hard-code server.port/management.port/mocked-server port trong suite trừ khi có lý do rõ.
- HTTP full integration test dùng **@SpringBootTest(RANDOM_PORT)**.
- @LocalServerPort được đọc **sau context startup**, không trong static initializer.
- Mọi request tới app dùng **actual port**, không đoán mặc định 8080.
- Khi chỉ cần MVC mapping dùng **@WebMvcTest/MockMvc** thay vì server thật.
- External HTTP stub bind port **0** và giữ listener sống trong test.
- @DynamicPropertySource lấy URL từ **stub đã khởi động**, có lifecycle/context cache đúng.
- Không dùng **findAvailablePort → close → bind**.
- Không đếm port như unique identifier của test method.
- Không nhầm app port với downstream stub port.
- Không nhầm container port với host mapped port của Docker.
- Có timeout và readiness checks, không Thread.sleep tùy tiện.
- Test addresses IPv4/IPv6 nhất quán và giới hạn loopback khi cần.
- Test resources đóng đúng lúc; tránh stale client trỏ tới server đã dừng.
- Khi bật JUnit parallel/test forks, không dùng static/global mutable endpoint URL bị ghi chồng.
- Khi phải dùng fixed resource, có exclusive test environment và resource locking đúng scope.
- Test data/database/file/Redis keys cũng được cô lập, không chỉ network ports.
- @Transactional trên test HTTP không bị hiểu nhầm là rollback server transactions.
- Không bịa actual port numbers, stdout hay test execution results chưa quan sát.
- Source code biên dịch/đặt đúng files/package/dependencies Java 17 và Boot 3.4.5.

**Kết luận:** **Cổng động là cách giao quyền chọn port cho hệ điều hành ở chính thời điểm server thật bind, rồi dùng port được cấp xuyên suốt vòng đời test.** Trong Spring Boot, sử dụng **RANDOM_PORT + @LocalServerPort** cho real HTTP tests; dùng **@WebMvcTest/MockMvc** khi không cần network; mở HTTP stubs bằng **port 0 + @DynamicPropertySource**; dùng Testcontainers **mapped ports/ServiceConnection** cho backends. Kết hợp port động với resource lifecycle, context cache và dữ liệu test isolation để bộ kiểm thử song song bền vững.

## Tài liệu chính thức

- Spring Boot 3.4 — Testing Spring Boot Applications, webEnvironment=RANDOM_PORT, LocalServerPort, transaction boundary và management port: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Testcontainers, @ServiceConnection: https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html
- Spring Framework 6.2 — @DynamicPropertySource: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework 6.2 — Spring TestContext caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- WireMock — JUnit Jupiter extension và dynamic port: https://wiremock.org/docs/junit-jupiter/
- WireMock — Java configuration/dynamicPort: https://wiremock.org/docs/configuration/
- Java 17 — ServerSocket / getLocalPort: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Java 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Testcontainers — Networking and communication: https://java.testcontainers.org/features/networking/
