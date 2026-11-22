# Kiểm thử management endpoint trên port riêng trong Spring Boot

Spring Boot Actuator cung cấp các management endpoint như **health**, **info**, **metrics**, **loggers** và **mappings** để giám sát, chẩn đoán và vận hành. Theo mặc định, các endpoint được expose qua HTTP dùng **chung cổng với application server**. Khi cấu hình **management.server.port** khác **server.port**, Spring Boot mở một management web server/context trên cổng riêng.

Một bài **HTTP integration test** đúng trọng tâm phải chứng minh hơn việc có property trong Environment: **hai listener thực sự khởi động, hai cổng khác nhau, application endpoint đáp ứng trên cổng chính, Actuator endpoint đáp ứng trên cổng quản trị, và endpoint không được expose hoặc được gọi nhầm cổng không vô tình hoạt động**.

Bài này dùng **Java 17, Spring Boot 3.4.5, Gradle, JUnit Jupiter, Spring MVC, Spring Boot Actuator**. Code test sử dụng **@SpringBootTest(webEnvironment = RANDOM_PORT)**, **@LocalServerPort**, **@LocalManagementPort** và Java 17 **HttpClient** để gửi request HTTP thực. Đây là kiểm thử **hai socket thực**, khác với MockMvc. Những khác biệt theo Spring Boot 4.x hoặc security deployment được phân biệt rõ, không suy luận từ phiên bản 3.4 sang tất cả phiên bản.

## 1. Kiến trúc: hai port, hai mục đích

Ví dụ cấu hình main server là 8080 và management server là 8081:

~~~text
                    Một tiến trình Spring Boot
                              |
                  +-----------+-----------+
                  |                       |
                  v                       v
           Main server/context      Management server/context
                 :8080                    :8081
                  |                       |
          GET /api/hello           GET /actuator/health
          HTTP 200, JSON           HTTP 200, status UP
                  |                       |
    GET /actuator/health          GET /api/hello
          thường 404                 thường 404
~~~

**Không phải hai JVM độc lập:** đây vẫn là một ứng dụng Spring Boot, nhưng management listener có HTTP connector/web context khác main server. Các resource và bean nội bộ có thể có quan hệ parent/child theo Boot; ý nghĩa của port riêng là **cô lập đường phục vụ HTTP**, không phải tách toàn bộ lỗi nghiệp vụ.

**Không nhầm hai port với hai path.** Nếu chỉ cấu hình management.endpoints.web.base-path=/manage mà không đặt management.server.port khác main port, Actuator vẫn có thể phục vụ tại **/manage/health trên chính cổng ứng dụng**. Khi dùng management port riêng và base path mặc định, địa chỉ thông thường là **http://host:managementPort/actuator/health**.

**Response 404 ở sai cổng** trong bài mẫu là hợp đồng của cấu hình tối giản không thêm Spring Security hoặc custom routes. Ở ứng dụng thực có security filter, reverse proxy hoặc controller riêng, sai cổng có thể trả 401, 403, redirect hay status khác. Chỉ assert 404 khi bạn có cơ sở về routing và security của môi trường cần test.

## 2. Những property quyết định management HTTP

| Property | Chức năng | Giá trị ví dụ |
| --- | --- | --- |
| **server.port** | Cổng cấu hình của web server chính | 8080 |
| **management.server.port** | Cổng quản trị; nếu khác main sẽ có listener riêng | 8081 |
| **management.server.address** | Địa chỉ management server bind; cần port riêng để dùng address khác | 127.0.0.1 |
| **management.server.base-path** | Base path trên management server riêng | /ops |
| **management.endpoints.web.base-path** | Prefix của Actuator web endpoints, mặc định /actuator | /actuator |
| **management.endpoints.web.exposure.include** | Các endpoint IDs được expose qua HTTP | health,info |
| **management.endpoints.web.exposure.exclude** | Endpoint IDs bị loại; exclude thắng include | beans,env |
| **management.endpoint.health.show-details** | Quy tắc hiển thị nội dung health chi tiết | never |
| **management.info.env.enabled** | Đưa info.* properties vào InfoEndpoint khi bật contributor | true |
| **management.server.port=-1** | Tắt HTTP management endpoints | -1 |

Một endpoint có thể **tồn tại trong context** nhưng chưa được expose qua HTTP. Ngược lại, exposure không thay thế authentication/authorization. Với Actuator, mặc định HTTP exposure giới hạn (thường chỉ health); không bật wildcard **include=*** một cách tùy tiện, đặc biệt với env, heapdump, configprops hoặc loggers.

### Giá trị property và cổng thực tế là hai thứ khác nhau

Khi bạn đặt **management.server.port=8081**, con số 8081 thể hiện cấu hình yêu cầu; trong bài test **RANDOM_PORT**, Spring Boot có thể ghi đè để cấp một cổng ngẫu nhiên khác. Vì vậy test cần dùng:

- **@LocalServerPort** trong package **org.springframework.boot.test.web.server** để lấy **local.server.port**, tức port main server đã bind thật.
- **@LocalManagementPort** cùng package để lấy **local.management.port**, tức port management server đã bind thật khi có listener riêng.
- Annotation **@Value** đọc key **management.server.port** chỉ cho biết property/config, không phải cách đáng tin cậy để tạo URL tới runtime random management port.

Tài liệu Spring Boot 3.4 nêu rõ: **@SpringBootTest(webEnvironment = RANDOM_PORT)** cũng cho management server một **random port riêng** khi cấu hình ứng dụng sử dụng một management port khác port chính. Ví dụ sẽ khai báo **8080 và 8081** trong application.yml, sau đó lấy port runtime bằng annotation. Không chỉ đặt **server.port=0** và **management.server.port=0** rồi giả định hai listener được tạo độc lập theo mọi phiên bản.

## 3. Chọn đúng mức test

| Loại test | Có real listener HTTP? | Có chứng minh management port riêng? |
| --- | --- | --- |
| Unit test đọc Environment | Không | Không |
| MockMvc trong web slice | Không | Không |
| @SpringBootTest mặc định MOCK | Không | Không |
| @SpringBootTest với @AutoConfigureMockMvc | Không có network socket phục vụ MockMvc | Không |
| @SpringBootTest với webEnvironment=RANDOM_PORT | Có, port do OS cấp | **Có**, nếu thực hiện request tới cả hai port |
| @SpringBootTest với webEnvironment=DEFINED_PORT | Có, dùng port cấu hình/default | Có, nhưng dễ xung đột cổng trong CI |

**MockMvc** hữu ích khi muốn kiểm tra Spring MVC mapping/filter/serialization mà không cần server thực. Nhưng đề bài yêu cầu **port riêng**, nên một test xanh chỉ với MockMvc không chứng minh management socket, bind address, deployment routing hoặc TCP connection.

Một bài test có giá trị cần **positive assertions** (API chính, management health/info đều hoạt động) và **negative assertions** (đường sai cổng, endpoint chưa expose không hoạt động) theo hợp đồng. Đừng chỉ assert rằng hai property có giá trị khác nhau.

## 4. Dự án có thể chạy: Spring Boot 3.4.5 + Actuator

Hợp đồng cụ thể của ví dụ:

1. Main server cấu hình 8080, GET **/api/hello** trả status 200 và JSON có **message=hello**.
2. Management server cấu hình 8081, bind **127.0.0.1**, chỉ expose **health** và **info**.
3. GET **/actuator/health** trên management port trả 200, JSON có **status=UP** khi các health contributors mặc định khỏe mạnh.
4. GET **/actuator/info** trên management port trả 200 và property **app.name=dual-port-demo**.
5. GET **/actuator/health** trên main port và GET **/api/hello** trên management port trả 404 trong cấu hình demo.
6. GET **/actuator/env** trên management port trả 404 vì không được expose.
7. Trong **@SpringBootTest(RANDOM_PORT)**, tất cả URL được tạo từ cổng thực tế, **không dùng hard-coded 8080/8081**.
8. Một test thứ hai thay **management.endpoints.web.base-path** để xác minh đường dẫn mới ở đúng management listener.

Ứng dụng demo không có DB, broker, remote client hoặc Spring Security để health/output có giá trị kỳ vọng ổn định. Ở dự án thực có dependencies, health có thể DOWN/OUT_OF_SERVICE và được ánh xạ sang HTTP 503; không hard-code UP cho những hệ thống có chủ đích chấp nhận degraded state.

### 4.1. Cây thư mục

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/managementports/DualPortApplication.java
src/main/java/com/example/managementports/HelloController.java
src/test/java/com/example/managementports/ManagementPortHttpTest.java
src/test/java/com/example/managementports/ManagementBasePathHttpTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-dual-management-port'
~~~

**build.gradle**

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter-web** có embedded Servlet container và JSON support (Jackson). **spring-boot-starter-actuator** cung cấp các management endpoints/auto-configuration. **spring-boot-starter-test** cung cấp JUnit Jupiter và Spring test support. Java **HttpClient** là API có sẵn trong Java 17, không cần thêm test HTTP client dependency.

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info
  info:
    env:
      enabled: true
  endpoint:
    health:
      show-details: never

info:
  app:
    name: dual-port-demo
~~~

Khi chạy bootRun, app và management listener dùng port cấu hình 8080/8081; management chỉ bind loopback. Khi test RANDOM_PORT, Boot khởi động các embedded servers theo random-port semantics và **LocalPort annotations** phản ánh port đã được cấp thật.

Cấu hình **show-details: never** giảm dữ liệu health bị lộ. **include: health,info** là allowlist HTTP exposure, không thay thế security và network policy. **management.info.env.enabled=true** cho phép dữ liệu info.* xuất hiện trong InfoEndpoint. Vì ví dụ không thêm Spring Security, test có thể gọi endpoint được expose mà không cần token; trong hệ thống thực, cần kiểm tra chính sách authorization riêng.

### 4.2. Application và controller chính

**src/main/java/com/example/managementports/DualPortApplication.java**

~~~java
package com.example.managementports;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualPortApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualPortApplication.class, args);
    }
}
~~~

**src/main/java/com/example/managementports/HelloController.java**

~~~java
package com.example.managementports;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/api/hello")
    public Message hello() {
        return new Message("hello");
    }

    public record Message(String message) {
    }
}
~~~

Controller này tạo một endpoint nghiệp vụ nhỏ, đủ để chứng minh **main server** thực sự trả HTTP 200/JSON. Vì chỉ được đăng ký ở main application web context, nó **không được kỳ vọng xuất hiện trên management port** của ví dụ. Jackson trong Spring MVC tự serialize record Message.

## 5. Real HTTP integration test với hai cổng

**src/test/java/com/example/managementports/ManagementPortHttpTest.java**

~~~java
package com.example.managementports;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class ManagementPortHttpTest {
    @LocalServerPort
    private int applicationPort;

    @LocalManagementPort
    private int managementPort;

    @Autowired
    private ObjectMapper mapper;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private HttpResponse<String> get(int port, String path)
            throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + path);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    private JsonNode json(HttpResponse<String> response)
            throws Exception {
        return mapper.readTree(response.body());
    }

    @Test
    void allocatesDifferentRuntimePorts() {
        assertTrue(applicationPort > 0);
        assertTrue(managementPort > 0);
        assertNotEquals(applicationPort, managementPort);
    }

    @Test
    void mainApiWorksOnApplicationPort() throws Exception {
        HttpResponse<String> response =
                get(applicationPort, "/api/hello");

        assertEquals(200, response.statusCode());
        assertEquals("hello",
                json(response).path("message").asText());
    }

    @Test
    void actuatorHealthWorksOnManagementPort()
            throws Exception {
        HttpResponse<String> response =
                get(managementPort, "/actuator/health");

        assertEquals(200, response.statusCode());
        assertEquals("UP",
                json(response).path("status").asText());
    }

    @Test
    void actuatorInfoWorksOnManagementPort()
            throws Exception {
        HttpResponse<String> response =
                get(managementPort, "/actuator/info");

        assertEquals(200, response.statusCode());
        assertEquals("dual-port-demo",
                json(response).path("app")
                        .path("name").asText());
    }

    @Test
    void wrongPortDoesNotServeTheOtherRoute()
            throws Exception {
        HttpResponse<String> mainActuator =
                get(applicationPort, "/actuator/health");
        HttpResponse<String> managementApi =
                get(managementPort, "/api/hello");

        assertEquals(404, mainActuator.statusCode());
        assertEquals(404, managementApi.statusCode());
    }

    @Test
    void environmentEndpointIsNotExposed()
            throws Exception {
        HttpResponse<String> response =
                get(managementPort, "/actuator/env");

        assertEquals(404, response.statusCode());
    }
}
~~~

### Đọc assertion theo mức bằng chứng

**allocatesDifferentRuntimePorts** kiểm tra **hai giá trị thực sau startup**, không so sánh đơn thuần YAML 8080/8081. Nếu management server không mở riêng, @LocalManagementPort có thể không có giá trị để inject và test sẽ fail sớm: đây là tín hiệu tốt vì đề bài yêu cầu port riêng.

**mainApiWorksOnApplicationPort** kiểm tra main HTTP listener, route controller và JSON serialization. Nếu port mở nhưng route lỗi, test vẫn fail. Điều này bổ sung bằng chứng cho phép kiểm cổng.

**actuatorHealthWorksOnManagementPort** kiểm tra management listener, actuator endpoint exposure và health body. Với cấu hình tối giản không có dependency ngoài hỏng, kỳ vọng health=UP là phù hợp; không nâng kết luận đó thành khẳng định cả production readiness luôn UP.

**actuatorInfoWorksOnManagementPort** kiểm tra cả HTTP exposure của info lẫn cấu hình info contributor đọc property app.name. Nếu bỏ **management.info.env.enabled=true**, endpoint có thể vẫn trả 200 nhưng body không có app.name; test sẽ bắt được sai khác.

**wrongPortDoesNotServeTheOtherRoute** xác nhận routing cách ly hai chiều. Với demo không có Spring Security/custom mapping, status 404 là mong đợi. Nếu triển khai security yêu cầu auth, 401/403 cần test riêng và không suy diễn từ cùng fixture này.

**environmentEndpointIsNotExposed** xác nhận endpoint nhạy cảm env không được expose qua HTTP trong allowlist. Nếu config đổi include sang wildcard, test này báo đỏ thay vì lặng lẽ mở thêm một API quản trị.

### Vì sao dùng URI tuyệt đối đến đúng management port?

Một số test client trong Spring Boot khi chạy RANDOM_PORT được cấu hình base URL là **main application port**. Nếu gọi relative URL **/actuator/health** mà không chọn management base URI, bạn có thể vô tình gửi tới main port và kết luận Actuator hỏng. HttpClient ở ví dụ luôn dùng host 127.0.0.1, một **port explicit** và một **path explicit**.

Có thể thay HttpClient bằng TestRestTemplate hoặc WebTestClient khi phù hợp version, nhưng vẫn phải chắc chắn quản lý **hai base URLs riêng**, không tái sử dụng root URI main cho management endpoint.

## 6. Bài test thứ hai: management base path khác mặc định

Management endpoint URI gồm các thành phần phải hiểu tách biệt:

- **management.server.base-path**: base path của management server khi dùng port riêng.
- **management.endpoints.web.base-path**: prefix của các web actuator endpoints, mặc định /actuator.
- **management.endpoints.web.path-mapping.<id>**: có thể đổi path của một endpoint cụ thể.
- **server.servlet.context-path**: context path chính của application servlet; không mặc nhiên áp cho management server riêng.

Nếu đổi **management.endpoints.web.base-path=/manage**, health thường chuyển từ **/actuator/health** sang **/manage/health** trên management port. Ví dụ dưới đây kiểm chứng trực tiếp bằng một context test khác. Hai test class có cấu hình khác nhau nên Spring TestContext có thể cache hai context/server riêng.

**src/test/java/com/example/managementports/ManagementBasePathHttpTest.java**

~~~java
package com.example.managementports;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

@SpringBootTest(
        webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = "management.endpoints.web.base-path=/manage")
class ManagementBasePathHttpTest {
    @LocalServerPort
    private int applicationPort;

    @LocalManagementPort
    private int managementPort;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private int getStatus(int port, String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());
        return response.statusCode();
    }

    @Test
    void newManagementPathDoesNotChangeMainApi()
            throws Exception {
        assertNotEquals(applicationPort, managementPort);

        assertEquals(200,
                getStatus(managementPort, "/manage/health"));
        assertEquals(404,
                getStatus(managementPort, "/actuator/health"));
        assertEquals(200,
                getStatus(applicationPort, "/api/hello"));
        assertEquals(404,
                getStatus(applicationPort, "/manage/health"));
    }
}
~~~

**Điểm dễ sai:** không thể đổi Environment property giữa hai JUnit test methods rồi chờ management MVC mappings đã tạo lúc startup tự động đổi theo. Dùng **@SpringBootTest(properties=...)** để cấu hình **trước lúc context khởi tạo**, rồi kiểm tra URL sau khi listener được bind. Khi một test cần base path khác, đó là **một context configuration khác**, không chỉ một assertion khác.

Nếu đồng thời đặt **management.server.base-path=/ops** và **management.endpoints.web.base-path=/actuator**, theo cơ chế servlet management port riêng, đường health dự kiến là **/ops/actuator/health**. Đừng lấy context path của main app ghép nhầm vào URL management. Phải xác nhận behavior của web stack và Boot version ứng dụng.

## 7. Lệnh chạy, response kỳ vọng và giới hạn

Cài/chuẩn bị Gradle Wrapper tương thích với Java 17 và Spring Boot 3.4.x, sau đó chạy ở thư mục project:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.managementports.ManagementPortHttpTest
./gradlew test --tests com.example.managementports.ManagementBasePathHttpTest
~~~

Trên Windows dùng **gradlew.bat** thay cho **./gradlew**. Với code/dependencies/cấu hình trong bài, các test được **thiết kế để PASS**. Đây là **kết quả kỳ vọng từ logic ví dụ**, không phải log build thực tế đã quan sát; cổng random do OS cấp nên không liệt kê một cặp port cố định cho kết quả test.

Khi chạy app bằng lệnh:

~~~bash
./gradlew bootRun
~~~

Với YAML chưa bị override, cổng được cấu hình là **8080** và **8081**. Từ cùng máy có thể tự gọi:

~~~bash
curl -i http://127.0.0.1:8080/api/hello
curl -i http://127.0.0.1:8081/actuator/health
curl -i http://127.0.0.1:8081/actuator/info
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8081/api/hello
curl -i http://127.0.0.1:8081/actuator/env
~~~

| URL khi bootRun theo YAML | Status dự kiến | Ý nghĩa |
| --- | --- | --- |
| 8080/api/hello | 200 | Main MVC endpoint |
| 8081/actuator/health | 200 | Management health, JSON status UP |
| 8081/actuator/info | 200 | Info contributor app.name |
| 8080/actuator/health | 404 | Management endpoint không ở main port |
| 8081/api/hello | 404 | Main API không được map ở management context |
| 8081/actuator/env | 404 | Endpoint env không expose |

Nếu một port cố định đã bị chiếm, bootRun có thể bị **BindException**; đó không phải lỗi nội dung test HTTP. RANDOM_PORT giúp test được phân bổ port trống, không phải tự dò một port trống rồi đóng socket và hy vọng không ai dùng nó.

## 8. MockMvc, TestRestTemplate và lỗi trỏ nhầm cổng

Có ba cách dễ khiến test kết luận sai:

**(1) Chỉ đọc property cấu hình.** Một assertion cho thấy Environment có management.server.port=8081 không chứng minh server thật sự nghe ở đó. Dùng runtime @LocalManagementPort và HTTP GET.

**(2) Dùng MockMvc như bằng chứng về socket.** MockMvc mô phỏng servlet request/dispatch. Kể cả được autowire trong @SpringBootTest với @AutoConfigureMockMvc, request không đi qua hai TCP listener khác nhau. Nó có thể kiểm tra handler trong context phù hợp, nhưng không phải phép thử của network port isolation.

**(3) Dùng test client đã gắn base URL của main server.** Relative path /actuator/health khi management port riêng có thể dẫn tới main port và nhận 404. Phải tạo URL bằng managementPort thực tế; với client khác, dùng base URI/absolute URL được cấu hình rõ ràng.

**Không dùng @LocalManagementPort vô điều kiện.** Khi management không cấu hình port riêng hoặc HTTP management bị tắt, local.management.port có thể không tồn tại. Đây là annotation dành cho test real server với management listener được cấp port. Nếu mục tiêu chuyển sang test Actuator chung main port, dùng @LocalServerPort và thay assertion tương ứng.

## 9. Security, endpoint exposure và status 401/403

Tách port chỉ tạo một **đường truy cập riêng**; nó không tự là authentication, authorization hay firewall. Trong ứng dụng thật:

- **management.endpoints.web.exposure.include** xác định endpoint nào có thể được expose qua HTTP. Hãy dùng allowlist, tránh wildcard công khai.
- **management.endpoint.<id>.access** và chính sách truy cập của Boot version có thể hạn chế quyền của endpoint, khác với HTTP exposure.
- **Spring Security** có thể buộc xác thực hoặc role cho Actuator; nếu project định nghĩa custom SecurityFilterChain, auto-config mặc định có thể back off và bạn phải thiết kế rule cho cả main/management context.
- **management.server.address=127.0.0.1** giới hạn listener ở loopback theo cấu hình mạng local, nhưng không chứng minh môi trường triển khai không publish qua proxy, port forwarding hoặc sidecar.
- Port management thường cần internal network policy, TLS và giới hạn ai có thể gọi /env, /beans, /heapdump, /loggers nếu chúng được bật cho vận hành.

Trong demo **không** thêm spring-boot-starter-security nên 200/404 là fixture có chủ đích. Khi bổ sung security, test nên tách **exposure test** (endpoint có được đăng ký HTTP không), **access test** (user/token nào được xem) và **network test** (địa chỉ nào kết nối được). Đừng đổi expected status thành 200 chỉ để test xanh, cũng đừng tuyên bố 404 luôn là hợp đồng cho mọi ứng dụng bảo mật.

## 10. Health quản trị UP chưa chắc main server sẵn sàng

Khi management server dùng một HTTP listener và web infrastructure riêng, nó có thể trả **health UP** dù **main listener** bị nghẽn, hết thread pool hoặc không nhận request ứng dụng. Vì vậy test nên kiểm tra **main API** cùng management health, như ở phần 5.

Với hệ thống vận hành Kubernetes, Spring Boot hỗ trợ **liveness/readiness health groups** và tùy chọn expose đường kiểm tra trên main server:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Khi hỗ trợ và cấu hình tương ứng, các health groups có thể được expose thêm trên main port tại **/livez** và **/readyz**. Health group cũng hỗ trợ additional-path dùng prefix **server:** hoặc **management:**. Điều này không làm cho /actuator/health tự xuất hiện trên main trong mọi trường hợp, nhưng nó chứng minh phát biểu "mọi health URL đều chỉ ở management port" có thể sai nếu có **additional paths có chủ đích**.

Liveness và readiness có contract khác nhau: không nên cho liveness phụ thuộc DB ngoài nếu một outage tạm thời sẽ gây restart loop. Nếu dùng readiness trên main port để xác nhận khả năng phục vụ traffic, test phải đánh giá nó theo health indicators/lifecycle thực tế, không coi một status UP đơn lẻ là đủ cho mọi tải.

## 11. Các biến thể cấu hình và điều cần đổi trong test

| Cấu hình | Behavior chính | Cách viết test |
| --- | --- | --- |
| Không đặt management.server.port | Actuator dùng main port | Lấy @LocalServerPort, không đòi local.management.port riêng |
| management.server.port bằng server.port | Không tách listener chỉ do cùng giá trị | Không assert hai port khác nhau |
| management.server.port khác server.port | Management có listener riêng khi auto-config thỏa điều kiện | @LocalManagementPort, HTTP tới hai port |
| management.server.port=-1 | Tắt HTTP management endpoints | Không cố inject cổng quản trị hoặc gọi health HTTP |
| management.endpoints.web.base-path=/manage | Thay prefix web endpoints | GET /manage/health trên management port |
| management.server.base-path=/ops | Thay base path riêng của management server | Xác minh path management tổng hợp thực tế |
| expose include=health | Info không được expose nếu không có override khác | /actuator/info thường 404 |
| Có Spring Security | Endpoint có thể trả 401/403 nếu chưa được phép | Kiểm tra với/không có credentials, đúng role |
| Probes additional paths bật | Có thêm path health trên main port | Điều chỉnh negative tests theo whitelist path thật |

Chỉ dùng một cấu hình rõ ràng cho mỗi test context. Nếu @SpringBootTest(properties=...) override YAML, kết luận chỉ áp dụng cho **test context đã override**, không tự chứng minh production config giống hệt. Khi test runtime có biến môi trường hoặc profile khác, cần xác định thứ tự ưu tiên property.

## 12. CI, caching, concurrent tests và cleanup

Spring TestContext cache ApplicationContext giữa những test có cấu hình tương đương. Vì vậy:

- Hai class dùng cấu hình giống nhau có thể chia sẻ embedded servers/ports trong cùng JVM test.
- Class thay base path bằng @SpringBootTest(properties=...) có merged configuration khác và có thể dựng server/context riêng.
- RANDOM_PORT giúp tránh đụng port cố định khi nhiều test/process chạy song song.
- Không tạo static final URL trước khi server startup; lúc đó @LocalPort fields chưa có giá trị.
- Không đổi System.setProperty("management.server.port", ...) giữa các test rồi mong context đã cache tự khởi động listener ở port mới.
- Nếu dùng @DirtiesContext, context bị đóng và có thể cần khởi động web servers lại, tăng thời gian chạy.
- Nếu có database, @Transactional trên JUnit method không bảo đảm rollback transaction trên server thread khi real HTTP request đi qua embedded server. Phải cleanup dữ liệu phù hợp.
- Timeout kết nối/read response của HttpClient giúp CI không chờ vô hạn, nhưng timeout không chứng minh business service SLA của production.
- Khi dùng DEFINED_PORT, nhiều suites cùng cố bind 8080/8081 có thể thất bại. Ưu tiên RANDOM_PORT.

## 13. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| @LocalManagementPort không inject được | Không có management listener riêng hoặc không có real HTTP server | Kiểm tra actuator dependency, config port khác main và webEnvironment |
| applicationPort == managementPort | Chưa tách listener theo cấu hình/phiên bản | Xác nhận management.server.port khác main |
| GET /actuator/health trên main trả 404 | Gọi sai port khi management đã tách | Chuyển sang managementPort |
| Gọi cổng cấu hình 8081 trong RANDOM_PORT nhưng refused | Runtime management port đã được cấp ngẫu nhiên | Dùng @LocalManagementPort |
| /actuator/health trên management trả 503 | Health indicator báo DOWN/OUT_OF_SERVICE | Kiểm tra dependencies và health body |
| /actuator/info trả 200 nhưng body rỗng | Không bật info env contributor hoặc không có info.* | Bật management.info.env.enabled và kiểm tra mapping |
| /actuator/info trả 404 | Chưa expose info | Kiểm tra exposure allowlist |
| /actuator/health trả 401 hoặc 403 | Spring Security/chính sách access chặn | Test xác thực/phân quyền đúng policy |
| /actuator/env trả 200 bất ngờ | Wildcard exposure hoặc config override | Thu hẹp include/exclude và security |
| /manage/health không tìm thấy | Path và port tính sai, chưa override trước startup | Test management base path đúng config |
| Main API xuất hiện ở management port | App tự đăng ký route/custom config hoặc không thực sự tách port | Kiểm tra routing/server contexts |
| Test MockMvc xanh nhưng management socket lỗi | Không có TCP request trong MockMvc | Chuyển sang real HTTP RANDOM_PORT test |
| BootRun bind port thất bại | Port 8080/8081 bị chiếm hoặc bind address không hợp lệ | Kiểm tra network interface/port, dùng random cho test |
| Management health UP nhưng main traffic hỏng | Hai HTTP contexts có khả năng lỗi khác nhau | Thử main API, readiness/liveness path trên main nếu phù hợp |
| Test xanh riêng, fail khi chạy suite | Fixed port, context cache, global property/state bị dùng chung | RANDOM_PORT, giảm shared mutation, tách test config |

## 14. Bài tập phản chứng

**A.** Application config main=8080, management=8081. Test RANDOM_PORT cố gọi http://localhost:8081/actuator/health rồi fail. Kết luận Actuator sai chưa? **Chưa**. Phải lấy local.management.port thực tế và gọi cổng ấy.

**B.** Chỉ có assert management.server.port khác server.port trong Environment. Đã kiểm thử management HTTP listener chưa? **Chưa**. Property không chứng minh socket mở hoặc route hoạt động.

**C.** @WebMvcTest có MockMvc và test GET /actuator/health xanh. Có đủ chứng minh hai port riêng không? **Không**. MockMvc không đi qua hai listener TCP.

**D.** GET /api/hello trên main port và /actuator/health trên management đều trả 200. Đã chứng minh route không xuất hiện sai cổng chưa? **Chưa**. Cần negative assertions cho đường ngược lại.

**E.** Chuyển management.endpoints.web.base-path từ /actuator sang /manage mà không restart test context. Endpoint đã cập nhật ngay chưa? **Không có bảo đảm.** Cấu hình route được áp dụng lúc dựng context; dùng test context được khởi tạo với property tương ứng.

**F.** Management health UP trong khi main thread pool hết khả năng xử lý HTTP request. Hai trạng thái có mâu thuẫn không? **Không**. Một management listener khỏe không chắc main server nhận được traffic.

**G.** Thêm Spring Security và GET /actuator/info trả 401. Có nên sửa test để mong 200 mà không thêm authentication không? **Không**. Test phải phản ánh chính sách access mong muốn.

**H.** management.server.address=127.0.0.1 và test trên cùng host thành công. Có chứng minh port không thể truy cập từ Internet sau deployment không? **Không đầy đủ**. Còn phụ thuộc network namespace, gateway, proxy và firewall.

### Checklist review

- Đã thêm spring-boot-starter-actuator và web server starter?
- management.server.port thực sự khác server.port trong cấu hình mục tiêu?
- Test dùng @SpringBootTest(webEnvironment=RANDOM_PORT) hay có lý do chọn DEFINED_PORT?
- Có lấy đúng @LocalServerPort và @LocalManagementPort sau server startup?
- Có assert hai runtime ports dương và khác nhau?
- Có HTTP GET đúng cổng của main API và management health/info?
- Có assert response body/status, không chỉ port đã bind?
- Có negative assertions cho wrong-port routes và endpoint không expose?
- Có cân nhắc security 401/403, auth và không expose endpoints nhạy cảm?
- Management base path, Actuator base path, main servlet context path có được tính đúng?
- Health UP trên management có bổ sung bằng chứng main port/readiness khi yêu cầu không?
- Không hard-code port random, không dựa vào context cache hoặc System properties mutable?
- Có hiểu @Transactional của JUnit test không rollback server-side HTTP transactions?
- Kết luận có giới hạn đúng theo môi trường demo và Spring Boot version?

**Kết luận:** Kiểm thử management endpoint trên port riêng là **real HTTP integration test cho hai listener**, không chỉ kiểm tra annotation hay property. Cấu hình management.server.port khác server.port; chạy RANDOM_PORT để tránh xung đột CI; lấy actual ports bằng @LocalServerPort và @LocalManagementPort; gửi HTTP request vào từng cổng; assert **positive paths, wrong-port paths, exposure, body và status**. Khi ứng dụng dùng security, custom paths, probes hay network isolation, hãy thêm assertions theo chính sách thật, không suy rộng kết quả health đơn giản sang toàn bộ production.

## Tài liệu chính thức

- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Monitoring and Management Over HTTP: https://docs.spring.io/spring-boot/3.4/reference/actuator/monitoring.html
- Spring Boot 3.4 — Actuator Endpoints và Health Probes: https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html
- Spring Boot 3.4 — LocalManagementPort API: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html
- Spring Boot 3.4 — LocalServerPort API: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/web/server/LocalServerPort.html
