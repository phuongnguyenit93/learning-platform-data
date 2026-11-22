# `@LocalServerPort`, management port và địa chỉ gọi trong test Spring Boot

## Mục tiêu

Trong test tích hợp Spring Boot, việc viết URL cố định như `http://localhost:8080/api/orders` có thể khiến bài test chạy được trên máy cá nhân nhưng lỗi trong CI: cổng đang bị chiếm, cấu hình cổng khác hoặc nhiều tiến trình test khởi chạy song song. Vấn đề còn dễ nhầm hơn khi ứng dụng có **Spring Boot Actuator**: endpoint nghiệp vụ và endpoint quản trị có thể chạy **trên hai HTTP server/port khác nhau**.

Annotation `@LocalServerPort` giúp test lấy **cổng HTTP thực tế của ứng dụng sau khi server đã khởi động**. Nếu có management server riêng, `@LocalManagementPort` dùng để lấy **cổng quản trị thực tế**. Từ port, hostname, scheme và đường dẫn, test tạo **địa chỉ gọi chính xác** cho từng loại endpoint.

Sau bài này, bạn có thể:

- Phân biệt `@SpringBootTest` với `MOCK`, `RANDOM_PORT`, `DEFINED_PORT` và `NONE`.
- Biết lúc nào `@LocalServerPort` có giá trị và tại sao `server.port=0` **khác** cổng đang lắng nghe.
- Phân biệt `server.port`, `local.server.port`, `management.server.port` và `local.management.port`.
- Cấu hình Spring Boot Actuator trên **cùng cổng** hoặc **cổng riêng** và gọi đúng `/actuator/health` trên địa chỉ phù hợp.
- Viết integration test Java 17, JUnit Jupiter và Spring Boot với cổng ngẫu nhiên, gọi HTTP thật và kiểm cả status lẫn JSON body.
- Xử lý các trường hợp đổi context path, management base path, bind address, SSL/HTTPS và security.
- Phân tích lỗi `Connection refused`, 404, 401/403, port 0 hoặc bean injection không thành công.
- Chọn `MockMvc`, `TestRestTemplate`, `WebTestClient` hay Java `HttpClient` theo phạm vi test.

Bài viết dùng ví dụ **Spring Boot 3.3.x, Servlet MVC, Java 17**; chi tiết package import và API client có thể khác trong những dòng Spring Boot mới hơn. Ví dụ được trình bày như project độc lập có thể tạo file và chạy bằng Gradle Wrapper.

## 1. Vì sao phải phân biệt cổng cấu hình và cổng thực tế?

Giả sử test ghi:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("http://localhost:8080/api/greeting"))
        .GET()
        .build();
~~~

Đây là snippet minh họa Java, chưa chứa class/imports đầy đủ. Nó **giả định** ứng dụng test đang lắng nghe ở cổng 8080. Giả định có thể sai khi:

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` yêu cầu hệ điều hành chọn cổng còn trống;
- dự án có `server.port` khác;
- một ứng dụng khác đã chiếm cổng 8080;
- nhiều test hoặc module chạy song song;
- test chạy trong container, địa chỉ `localhost` trỏ về container client thay vì server mong muốn;
- server chỉ bind vào một network interface cụ thể.

Với `RANDOM_PORT`, cấu hình thường có ý nghĩa tương đương `server.port=0`: **số 0 là yêu cầu tìm cổng trống**, không phải địa chỉ để client kết nối. Khi embedded server lắng nghe thành công, có một **port thực tế** (ví dụ 51237, mỗi lần chạy có thể khác). Test lấy port ấy rồi tạo URL.

~~~text
@SpringBootTest(webEnvironment = RANDOM_PORT)
         |
         v
Boot yêu cầu embedded server bind port 0
         |
         v
OS cấp cổng còn trống, ví dụ 51237
         |
         v
Spring công bố local.server.port = 51237
         |
         v
@LocalServerPort int port  --> 51237
         |
         v
Client gọi http://127.0.0.1:51237/api/greeting
~~~

Ví dụ số 51237 **chỉ mang tính minh họa**, không phải output dự đoán cố định. Bài test đúng không nên `assertEquals(51237, port)`. Test nên kiểm port > 0 và gửi HTTP tới port được inject.

## 2. Các chế độ `webEnvironment` của `@SpringBootTest`

`@SpringBootTest` tải Spring Boot application context, nhưng **không phải chế độ nào cũng bật server thật**.

| Chế độ | Có server HTTP thật? | Dùng để kiểm | `@LocalServerPort` |
| --- | --- | --- | --- |
| `MOCK` (mặc định) | Không | Bean wiring, MVC MockMvc, nhiều kiểm thử cấu hình | Thông thường không có runtime server port |
| `RANDOM_PORT` | Có, chọn cổng khả dụng | HTTP end-to-end qua mạng loopback, codec, servlet container | Có, khi server web thực sự khởi tạo |
| `DEFINED_PORT` | Có, dùng cổng từ cấu hình hoặc mặc định | Test có yêu cầu cổng cụ thể, rất dễ xung đột | Có thể lấy cổng đã chạy; thường không cần nếu đã biết, nhưng kiểm cấu hình quan trọng |
| `NONE` | Không | Bối cảnh không cần web environment | Không có web-server port |

`MOCK` cho phép dùng `@AutoConfigureMockMvc` với Servlet MVC mà không mở TCP port. Nó có thể nhanh và ít chịu ảnh hưởng mạng hơn. `RANDOM_PORT` kiểm **thực sự một request HTTP** đi qua embedded server; phù hợp khi cần xác minh HTTP serialization, filter, status, headers, cookie, port routing hoặc hành vi của servlet container. `DEFINED_PORT` có thể gây xung đột nếu cùng máy có dịch vụ khác, nên **ưu tiên RANDOM_PORT cho integration test**.

Ví dụ annotation đúng:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpIntegrationTest {

    @LocalServerPort
    int port;

    // @Test với một HTTP client thật...
}
~~~

Đây là snippet; file chạy được ở mục 5. Chỉ đặt `@LocalServerPort` lên một JUnit test class **không bootstrap server** không làm server tự bật. Trước khi dùng annotation, phải chọn môi trường web có listener đang chạy.

### `@LocalServerPort` là gì?

Spring Boot 3.3 khai báo annotation tại:

~~~java
import org.springframework.boot.test.web.server.LocalServerPort;
~~~

Nó là cách viết thuận tiện tương đương việc dùng `@Value("${local.server.port}")` để tiêm property runtime. Property `local.server.port` được công bố **sau khi embedded server khởi động và phát sự kiện khởi tạo**, không phải giá trị cấu hình ban đầu. Vì vậy:

- **`server.port`**: cổng được yêu cầu từ config; `0` có nghĩa chọn cổng ngẫu nhiên.
- **`local.server.port`**: cổng thực tế sau khi server bắt đầu lắng nghe.
- **`@LocalServerPort`**: lấy `local.server.port` vào field/parameter test theo hỗ trợ của Boot Test.

Đừng đưa `@LocalServerPort` vào constructor bean production rồi giả định property luôn có sẵn trong giai đoạn bean khởi tạo. Test instance được Spring TestContext chuẩn bị sau quá trình khởi tạo server; bean production có thể được tạo quá sớm để thấy giá trị runtime này.

## 3. Management port: Actuator dùng chung hay chạy riêng?

**Spring Boot Actuator** cung cấp các endpoint quản lý/vận hành, ví dụ `/actuator/health` và `/actuator/info`. Chúng **không phải cùng một thứ** với controller nghiệp vụ như `/api/greeting`.

Mặc định, khi ứng dụng dùng Actuator HTTP và không cấu hình cổng quản trị riêng, các endpoint quản lý thường được phục vụ trên **cùng port với ứng dụng** (với các điều kiện exposure và security phù hợp). Ví dụ:

~~~text
http://127.0.0.1:<application-port>/api/greeting
http://127.0.0.1:<application-port>/actuator/health
~~~

Trong trường hợp này, việc tạo URL tới Actuator bằng **application port** là hợp lý, và không nên giả định property `local.management.port` của server riêng luôn tồn tại.

Khi khai báo `management.server.port` khác cổng ứng dụng, Spring Boot có thể tạo **management web server/context riêng**:

~~~text
                       Spring Boot test process
                                |
                 +--------------+------------------+
                 |                                 |
       Application HTTP server             Management HTTP server
       server.port = 0                     management.server.port = 0
       local.server.port = 51237           local.management.port = 53241
                 |                                 |
      /api/greeting                          /actuator/health
                 |                                 |
       @LocalServerPort                  @LocalManagementPort
                 |                                 |
       http://127.0.0.1:51237/...         http://127.0.0.1:53241/...
~~~

Hai port mẫu 51237 và 53241 chỉ để minh họa sự khác biệt. **Không hardcode chúng**.

### Bốn property cần nhớ

| Property/annotation | Ý nghĩa | Khi nào dùng? |
| --- | --- | --- |
| `server.port` | Cổng mà application server được yêu cầu bind; `0` chọn cổng trống | Cấu hình ứng dụng |
| `local.server.port` / `@LocalServerPort` | Cổng ứng dụng thực tế đã bind | Test HTTP trên app server |
| `management.server.port` | Cổng quản trị được yêu cầu; vắng mặt thường dùng chung app port; `0` yêu cầu cổng ngẫu nhiên riêng khi management server có cấu hình riêng | Cấu hình Actuator |
| `local.management.port` / `@LocalManagementPort` | Cổng management web server thực tế được công bố khi có server riêng | Test endpoint Actuator trên management server |

Trong Spring Boot 3.3, import `@LocalManagementPort` là:

~~~java
import org.springframework.boot.test.web.server.LocalManagementPort;
~~~

Nó được thiết kế để tiêm cổng HTTP management tại runtime, tương đương `@Value("${local.management.port}")` khi property được server quản trị công bố.

**Điểm khác biệt thiết yếu:** `management.server.port=0` là một **cấu hình đầu vào**, còn `@LocalManagementPort` là **kết quả cổng được cấp sau khi khởi chạy**. Không bao giờ dùng chuỗi `http://localhost:0/actuator/health` để gọi Actuator.

### `RANDOM_PORT` ảnh hưởng tới management port thế nào?

Trong Spring Boot 3.3, khi `@SpringBootTest(webEnvironment = RANDOM_PORT)` tải ứng dụng có **management server khác port ứng dụng**, Boot cũng xử lý để management server sử dụng một port ngẫu nhiên phục vụ kiểm thử. Tuy nhiên, để bài học rõ ràng và độc lập với các thay đổi giữa phiên bản, ví dụ đặt **`management.server.port=0` tường minh**. Cách đó nêu chính xác mục tiêu: cổng management riêng, do hệ điều hành cấp.

**Không suy ra** rằng cổng quản trị cũng là `@LocalServerPort`, hoặc rằng `@LocalManagementPort` luôn có giá trị khi Actuator chưa được thêm vào classpath, chưa có management HTTP server, hay cổng quản trị đang dùng chung server ứng dụng.

## 4. Địa chỉ URL bao gồm nhiều phần hơn port

Một URL dùng trong test thường có dạng:

~~~text
<scheme>://<host>:<port><context-prefix><endpoint-path>?<query>
~~~

Ví dụ:

~~~text
http://127.0.0.1:51237/api/greeting
http://127.0.0.1:53241/actuator/health
~~~

**Port đúng nhưng URL vẫn có thể sai** nếu host, protocol hoặc path không phù hợp:

- **Scheme:** `http` nếu server không bật TLS; phải dùng `https` nếu bật SSL.
- **Host:** `127.0.0.1` là loopback IPv4; phù hợp khi test client và embedded server chạy trong cùng network namespace và server bind địa chỉ tương thích. `localhost` có thể phân giải thành IPv4 hoặc IPv6 tùy hệ thống.
- **Port:** lấy từ `@LocalServerPort`/`@LocalManagementPort`, không sao chép cổng ví dụ.
- **Ứng dụng Servlet MVC:** `server.servlet.context-path=/shop` làm URL controller `/api/greeting` thành `/shop/api/greeting`.
- **Actuator base path:** mặc định `management.endpoints.web.base-path=/actuator`, có thể đổi thành `/manage`.
- **Management server base path:** nếu Actuator chạy trên cổng riêng, `management.endpoints.web.base-path` được xác định tương đối với `management.server.base-path` (nếu có cấu hình).

Khi management server dùng chung cổng ứng dụng Servlet, endpoint Actuator thường chịu ảnh hưởng của `server.servlet.context-path`. Khi quản trị dùng cổng riêng, đừng tự động ghép nguyên `server.servlet.context-path` vào management URL: đường dẫn dựa trên **cấu hình management context**, không nhất thiết là context path ứng dụng.

### Ba kịch bản đường dẫn cần phân biệt

| Kịch bản | Application URL | Health URL |
| --- | --- | --- |
| Mặc định, Actuator cùng port | `http://127.0.0.1:APP/api/greeting` | `http://127.0.0.1:APP/actuator/health` |
| Management port riêng, base path mặc định | `http://127.0.0.1:APP/api/greeting` | `http://127.0.0.1:MGMT/actuator/health` |
| App `server.servlet.context-path=/shop`, management riêng, `management.endpoints.web.base-path=/ops` | `http://127.0.0.1:APP/shop/api/greeting` | `http://127.0.0.1:MGMT/ops/health` (khi không đổi thêm `management.server.base-path`) |

`APP` và `MGMT` là ký hiệu, không phải tên biến môi trường. Chúng đại diện cho giá trị port thực tế được Spring inject.

## 5. Project Java 17 + Spring Boot 3.3 đầy đủ: test cả hai port

Đây là một ví dụ **có thể chạy được** với Servlet MVC và Spring Boot Actuator, không cần cơ sở dữ liệu hoặc hệ thống bên ngoài. Có hai integration test class:

1. `ApplicationPortHttpTest` kiểm HTTP thật trên **application port ngẫu nhiên**.
2. `SeparateManagementPortHttpTest` thêm `management.server.port=0`, kiểm **hai port khác nhau**, gọi controller trên application port và gọi health trên management port.

Dùng **Java 17 `HttpClient`** để người học thấy rõ URL được xây từ port. Không cần `WebTestClient`/RestAssured chỉ để thực hiện ví dụ này.

### 5.1. Cấu trúc file

~~~text
port-management-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   ├── DemoApplication.java
    │   └── GreetingController.java
    └── test/java/com/example/testing/
        ├── ApplicationPortHttpTest.java
        └── SeparateManagementPortHttpTest.java
~~~

Các file Wrapper cần được tạo bởi Gradle phù hợp hoặc có sẵn trong repository. Không chép tay `gradle-wrapper.jar` dưới dạng văn bản.

**`settings.gradle`**

~~~groovy
rootProject.name = 'port-management-demo'
~~~

**`build.gradle`** (Groovy DSL; ví dụ dùng Java 17 và Spring Boot 3.3.5):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích dependency:

- `spring-boot-starter-web` tạo môi trường Servlet MVC và web server nhúng, đồng thời có Jackson JSON support theo starter của phiên bản này.
- `spring-boot-starter-actuator` cung cấp các endpoint quản trị, trong đó có health.
- `spring-boot-starter-test` có Spring TestContext, JUnit Jupiter và các công cụ kiểm thử thông dụng.
- `junit-platform-launcher` là runtime launcher phục vụ Gradle chạy Jupiter.
- `useJUnitPlatform()` bảo đảm test task sử dụng JUnit Platform.
- Nếu dùng Gradle/Boot phiên bản khác, phải kiểm lại compatibility. Đừng trộn dependency của Boot 3.3 với annotation/API từ Boot 4 nếu chưa xác nhận.

### 5.2. Ứng dụng HTTP thật

**`src/main/java/com/example/testing/DemoApplication.java`**

~~~java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/testing/GreetingController.java`**

~~~java
package com.example.testing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/greeting")
    public GreetingResponse greeting() {
        return new GreetingResponse("xin-chao", 1);
    }

    public record GreetingResponse(String message, int version) {
    }
}
~~~

Controller có một endpoint ổn định:

~~~http
GET /api/greeting HTTP/1.1
Host: 127.0.0.1:<application-port>
~~~

Với Jackson JSON serialization, body dự kiến có các giá trị:

~~~json
{
  "message": "xin-chao",
  "version": 1
}
~~~

Thứ tự các property trong JSON object không phải yêu cầu ở đây; test sẽ parse bằng `ObjectMapper` rồi kiểm giá trị từng field. Nội dung đơn giản giúp thấy rõ vấn đề của **địa chỉ/cổng** thay vì bị phân tán bởi database hay nghiệp vụ phức tạp.

### 5.3. Test application port với `@LocalServerPort`

**`src/test/java/com/example/testing/ApplicationPortHttpTest.java`**

~~~java
package com.example.testing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApplicationPortHttpTest {

    @LocalServerPort
    private int applicationPort;

    @Autowired
    private ObjectMapper mapper;

    private final HttpClient client = HttpClient.newHttpClient();

    private String appUrl(String path) {
        return "http://127.0.0.1:" + applicationPort + path;
    }

    @Test
    void injectedApplicationPortIsARealPort() {
        assertTrue(applicationPort > 0);
        assertTrue(applicationPort <= 65535);
    }

    @Test
    void applicationEndpointRespondsOverRealHttp() throws Exception {
        URI uri = URI.create(appUrl("/api/greeting"));
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("xin-chao", body.path("message").asText());
        assertEquals(1, body.path("version").asInt());
    }
}
~~~

**Vì sao test này không dùng 8080?** `applicationPort` chỉ có giá trị thực sau khi Spring Boot test context và web server đã khởi tạo. Vì vậy `appUrl` dùng đúng port được Spring inject. Test cần client và server chạy trong **cùng môi trường mạng cục bộ** để `127.0.0.1` trỏ đúng server.

**Vì sao dùng `@Autowired ObjectMapper`?** Đây là Jackson mapper của ứng dụng Boot, giúp parse JSON mà không so văn bản thuần. Nếu response có thay đổi thứ tự key hoặc whitespace nhưng vẫn đúng dữ liệu, test không fail vô ích.

**Vì sao cần `timeout`?** Request có timeout giúp test không kẹt vô thời hạn khi server không phản hồi; timeout kết nối và timeout response là các khái niệm khác nhau, và trong hệ thống có I/O chậm phải chọn giới hạn phù hợp. Giá trị 5 giây là ví dụ, không phải SLA.

Class này có **2 lượt test JUnit**, dự kiến pass nếu project khởi động và endpoint hoạt động đúng.

### 5.4. Test management port riêng với `@LocalManagementPort`

**`src/test/java/com/example/testing/SeparateManagementPortHttpTest.java`**

~~~java
package com.example.testing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "management.server.port=0",
                "management.endpoints.web.exposure.include=health"
        })
class SeparateManagementPortHttpTest {

    @LocalServerPort
    private int applicationPort;

    @LocalManagementPort
    private int managementPort;

    @Autowired
    private ObjectMapper mapper;

    private final HttpClient client = HttpClient.newHttpClient();

    private String appUrl(String path) {
        return "http://127.0.0.1:" + applicationPort + path;
    }

    private String managementUrl(String path) {
        return "http://127.0.0.1:" + managementPort + path;
    }

    private HttpResponse<String> get(String url) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(url))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void applicationAndManagementHaveDifferentRuntimePorts() {
        assertTrue(applicationPort > 0);
        assertTrue(managementPort > 0);
        assertNotEquals(applicationPort, managementPort);
    }

    @Test
    void applicationEndpointUsesApplicationPort() throws Exception {
        HttpResponse<String> response =
                get(appUrl("/api/greeting"));

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("xin-chao", body.path("message").asText());
        assertEquals(1, body.path("version").asInt());
    }

    @Test
    void actuatorHealthUsesManagementPort() throws Exception {
        HttpResponse<String> response =
                get(managementUrl("/actuator/health"));

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("UP", body.path("status").asText());
    }
}
~~~

Class này có **3 lượt test**. Với Spring Boot 3.3.x, `RANDOM_PORT` và `management.server.port=0` khiến app server và management server dùng những port OS cấp thực tế, không phải cổng 0. Hai server cùng bind trên địa chỉ loopback tương thích sẽ không thể dùng đồng thời cùng một TCP port; `assertNotEquals` phản ánh yêu cầu cấu hình **tách cổng**.

**Lưu ý:** Annotation `@LocalManagementPort` chỉ có ý nghĩa khi một management HTTP server đã thực sự khởi tạo và công bố `local.management.port`. Nếu bỏ starter Actuator hoặc cấu hình tắt HTTP management endpoints/server, không nên mặc định injection vẫn hoạt động. Khi Actuator dùng chung port với app, dùng application port để gọi health, không bắt buộc phải inject management port riêng.

### 5.5. Tại sao response health trả `"UP"`?

Trong project demo không có database, external queue hay health contributor đang báo lỗi, health aggregate thông thường là `UP` và HTTP status 200. Nếu thêm database/Redis/custom `HealthIndicator`, endpoint có thể trả `DOWN` hoặc `OUT_OF_SERVICE` với status code khác theo cấu hình. Test nên assert kết quả **phù hợp với fixture và hạ tầng đã chuẩn bị**, không hardcode `UP` cho mọi môi trường.

Spring Boot Actuator cũng có exposure/security policy. Với starter demo **không** khai báo Spring Security và health endpoint được expose, HTTP GET trên management port trả health JSON. Trong ứng dụng thật có security, proxy hoặc health group, status có thể là 401/403 nếu thiếu quyền hoặc endpoint không được expose; **không tắt bảo mật** chỉ vì test mong status 200 mà chưa xét hợp đồng.

### 5.6. Chạy hai test class

Tại thư mục gốc có Gradle Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng một class:

~~~bash
./gradlew test --tests 'com.example.testing.SeparateManagementPortHttpTest'
~~~

Trong bộ ví dụ có **2 + 3 = 5 method `@Test`**, mỗi method một invocation. Kỳ vọng **5 test pass** khi server và các dependency của bản demo hoạt động đúng. Không có `System.out.println` trong mã test, nên không có stdout nghiệp vụ cố định; Gradle có thể in `BUILD SUCCESSFUL` và báo cáo tại:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.testing.ApplicationPortHttpTest.xml
    └── TEST-com.example.testing.SeparateManagementPortHttpTest.xml
~~~

Báo cáo XML/HTML mới phản ánh số test thực chạy. `UP-TO-DATE` hoặc `FROM-CACHE` nghĩa task có thể tái sử dụng kết quả; khi chẩn đoán có thể dùng `./gradlew test --rerun-tasks`.

Nếu project chưa có Wrapper, cần một Gradle đã cài và tương thích để bootstrap, chẳng hạn `gradle wrapper --gradle-version 8.8 --distribution-type bin` với demo Boot 3.3.x/Java 17. Sau đó lưu `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties` và `gradle-wrapper.jar` vào repository theo quy định. Trong codebase thật, **dùng đúng Wrapper đã có**, không tùy tiện nâng phiên bản chỉ vì bài ví dụ.

## 6. Khi Actuator dùng cùng port ứng dụng

Nếu **không** đặt `management.server.port` khác ứng dụng và có Actuator, health URL thông thường dùng chính app port:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SharedPortExampleTest {

    @LocalServerPort
    int port;

    @Test
    void healthWouldUseApplicationPort() {
        String url = "http://127.0.0.1:" + port
                + "/actuator/health";
        // Dùng HTTP client thật để gửi GET và assert response.
    }
}
~~~

Đây là **snippet minh họa đường dẫn**, không phải một test có đủ assert; chỉ coi project ở mục 5 là code runnable hoàn chỉnh. Với cấu hình mặc định và Actuator dependency, URL này phục vụ health trên app port.

Trong codebase thật có `server.servlet.context-path`, `management.endpoints.web.base-path` hoặc security tùy biến, phải ghép URL theo những cấu hình ấy. Tránh hardcode `/actuator/health` như hợp đồng không thể thay đổi.

### `@LocalManagementPort` có luôn bằng `@LocalServerPort` không?

**Không nên giả định.** Cả tên lẫn property được thiết kế cho hai vai trò khác nhau. Khi server management **tách riêng**, chúng phản ánh các port khác nhau. Khi Actuator **dùng chung** server ứng dụng, cách xác minh ổn định nhất là tạo URL quản trị từ **application port** (nếu endpoint được expose), thay vì bắt buộc injection `local.management.port` của một server riêng không tồn tại.

Mục tiêu chính của `@LocalManagementPort` không phải “một alias cho cổng chính” mà là hỗ trợ phát hiện **runtime management port** trong bối cảnh server quản trị riêng được cấp cổng.

## 7. Dùng `TestRestTemplate`, `WebTestClient` hay Java `HttpClient`?

Không bắt buộc phải tự xây mọi URL nếu client hỗ trợ base URI từ Spring Boot. Tuy nhiên, khi có management port riêng, cần hiểu client đó **đang trỏ vào server nào**.

### 7.1. `TestRestTemplate` trong Spring Boot 3.3

Với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, Spring Boot có hỗ trợ autowire `TestRestTemplate` được cấu hình tiện lợi để gọi application server bằng đường dẫn tương đối.

~~~java
@Autowired
TestRestTemplate rest;

@Test
void applicationRoute() {
    ResponseEntity<String> response =
            rest.getForEntity("/api/greeting", String.class);
    assertEquals(HttpStatus.OK, response.getStatusCode());
}
~~~

Snippet giả sử đã có class test, imports JUnit/Spring Web và Spring TestRestTemplate. Trong Boot 3.3, import `org.springframework.boot.test.web.client.TestRestTemplate`; nó không phải `RestTemplate` thông thường.

Khi gọi **management server khác port**, đừng tự động mong `rest.getForEntity("/actuator/health", ...)` chuyển sang management port; client mặc định của running-server test thường gắn với **application root URI**. Có thể truyền URL tuyệt đối có port quản trị:

~~~java
String healthUrl = "http://127.0.0.1:"
        + managementPort + "/actuator/health";
ResponseEntity<String> response =
        rest.getForEntity(healthUrl, String.class);
~~~

Đây là phần code minh họa trong test có `managementPort` đã inject. Với Spring Security, SSL hoặc auth phức tạp, chọn client/configuration phù hợp với hợp đồng thay vì kỳ vọng `TestRestTemplate` tự xử lý mọi trường hợp.

### 7.2. `WebTestClient`

`WebTestClient` có API fluent kiểm HTTP response và body. Spring Boot 3.3 có thể cấu hình client gắn với running server để dùng URI tương đối trong test phù hợp; **Spring WebFlux cần có trên test classpath** để sử dụng loại client này trong nhiều cấu hình Boot 3.x. Không thêm cả WebFlux chỉ để test port nếu Java `HttpClient` đã đáp ứng.

Ví dụ ý tưởng:

~~~java
webTestClient.get().uri("/api/greeting")
        .exchange()
        .expectStatus().isOk();
~~~

Snippet giả sử đã inject/configure `webTestClient` trong test, không phải class chạy độc lập. Nếu bạn muốn gọi management server riêng, cần **base URL đúng của management port** hoặc dùng absolute URI được client chấp nhận; đừng coi mọi URI tương đối là tự chọn cổng quản trị.

### 7.3. Java 17 `HttpClient`

`java.net.http.HttpClient` thuộc JDK, có lợi điểm không phụ thuộc một HTTP client test library nữa và làm rõ từng phần của URL:

~~~java
URI uri = URI.create(
        "http://127.0.0.1:" + applicationPort + "/api/greeting");

HttpRequest request = HttpRequest.newBuilder(uri)
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Đây là snippet từ ví dụ đầy đủ ở mục 5. Nó phù hợp để học cách xây URL/port, nhưng với dự án có auth/session/headers phức tạp, một client test được cấu hình chuyên dụng có thể làm test ngắn và dễ đọc hơn.

### 7.4. RestAssured và state toàn cục

Nếu dùng RestAssured, ưu tiên chỉ định port **cho từng request**:

~~~java
given()
    .port(applicationPort)
.when()
    .get("/api/greeting")
.then()
    .statusCode(200);
~~~

Snippet yêu cầu RestAssured dependency và static imports, không thuộc project runnable của bài. Tránh lạm dụng `RestAssured.port = applicationPort` như một **biến static toàn cục** trong test chạy song song, vì một class test khác có thể đổi port và gây lỗi giao thoa. Khi test management endpoint, chỉ định `.port(managementPort)` hoặc base URI riêng cho request tương ứng.

## 8. Tạo địa chỉ đúng khi đổi context path và base path

Một lỗi phổ biến: port được inject chính xác nhưng test GET tới **sai path**. Hãy tách rõ phần cấu hình của server ứng dụng và management server.

### 8.1. `server.servlet.context-path`

Với Servlet MVC:

~~~properties
server.servlet.context-path=/shop
~~~

Một controller mapping `@GetMapping("/api/greeting")` sẽ được phục vụ qua `/shop/api/greeting`, không còn `/api/greeting`.

Vì vậy test cần ghép:

~~~java
String appUrl = "http://127.0.0.1:" + applicationPort
        + "/shop/api/greeting";
~~~

Nếu context path là một property được thiết lập riêng cho profile test, nên centralize việc tạo base URL hoặc đọc cấu hình từ test context khi hợp lý, tránh ghi lặp path trong hàng chục test.

### 8.2. `management.endpoints.web.base-path`

Actuator mặc định đặt endpoint dưới `/actuator`. Có thể đổi:

~~~properties
management.endpoints.web.base-path=/manage
~~~

Khi đó health endpoint thường là `/manage/health` (tùy management server base path và security). Nếu management server tách port, dùng:

~~~java
String healthUrl = "http://127.0.0.1:" + managementPort
        + "/manage/health";
~~~

### 8.3. `management.server.base-path` và management server riêng

Khi một management server riêng được cấu hình, có thể đặt thêm `management.server.base-path`. Theo quy tắc Spring Boot 3.3, `management.endpoints.web.base-path` tương đối với management server base path này. Ví dụ nếu `management.server.base-path=/internal` và `management.endpoints.web.base-path=/actuator`, đường dẫn quản trị dự kiến là `/internal/actuator/health`.

**Đừng áp dụng nhầm `server.servlet.context-path` của application server** cho management server riêng. Điều này thường gây 404 dù management port đã đúng.

### 8.4. `management.server.address` và bind interface

Có thể đặt management server chỉ lắng nghe loopback:

~~~properties
management.server.port=8081
management.server.address=127.0.0.1
~~~

Điều này phù hợp một số deployment chỉ cho phép quản trị nội bộ. Trong Boot, cấu hình management address khác với application address **chỉ được hỗ trợ khi management port khác application port**. Nếu chạy test trong container khác network namespace, `127.0.0.1` của client không trỏ về container server; cần hostname và routing nội bộ thực tế.

**Cổng không chứa hostname.** `@LocalServerPort` và `@LocalManagementPort` chỉ cung cấp số port; địa chỉ/host là một quyết định riêng dựa trên cách server bind và vị trí client.

### 8.5. HTTP và HTTPS

Nếu application bật `server.ssl.*`, client phải dùng `https://` và tin cậy certificate đúng cách. Với management port riêng, `management.server.ssl.*` có thể khác `server.ssl.*`, nên **hai server có thể sử dụng hai scheme khác nhau**.

Không khắc phục một lỗi chứng chỉ bằng cách vô hiệu hóa TLS validation bừa bãi trong production test. Dùng truststore/test certificate được kiểm soát hoặc HTTP nội bộ chỉ trong phạm vi test phù hợp với mục tiêu. Test phải nêu rõ đang kiểm TLS hay chỉ kiểm logic của endpoint.

## 9. Test bắt đúng endpoint nhưng sai server

Nếu management port khác app port, một request tới:

~~~text
http://127.0.0.1:<application-port>/actuator/health
~~~

có thể nhận 404, 401/403 hoặc đi qua một route/proxy khác thay vì đúng management endpoint. Nếu test kỳ vọng health ở cổng quản trị, phải dùng:

~~~text
http://127.0.0.1:<management-port>/actuator/health
~~~

Đừng kết luận 404 tự động có nghĩa Actuator dependency bị thiếu; trước tiên kiểm **đúng cổng, đúng path, đúng exposure**. Tương tự, gửi `/api/greeting` tới management port thường không đúng vì controller nghiệp vụ được phục vụ trên application server.

### Cần xác minh những điều gì?

| Kiểm thử | Kiểm tra gì? | Không chứng minh được gì? |
| --- | --- | --- |
| `applicationPort > 0` | Spring đã công bố cổng số hợp lệ | Endpoint HTTP chắc chắn đáp ứng đúng |
| GET app endpoint trên application port | HTTP routing/controller/serialization thực sự hoạt động | Management server hoạt động |
| `managementPort > 0` | Runtime management port được công bố | Health endpoint được expose và khỏe mạnh |
| `applicationPort != managementPort` | Hai server được cấu hình tách cổng trong demo | Mọi firewall/proxy production đã đúng |
| GET `/actuator/health` trên management port | Đúng route/port và health phản hồi | Tất cả dependency bên ngoài production đều khỏe trong môi trường khác |
| Kiểm 401/403 có chủ đích | Chính sách auth/authorization có tác dụng | Endpoint không hề tồn tại |

Kiểm cả **status code và body** giúp test bắt lỗi tốt hơn chỉ kiểm “kết nối thành công”. Tuy nhiên phải viết expected theo đặc tả thật: trong một ứng dụng có health contributor báo `DOWN`, 503 có thể phản ánh lỗi hạ tầng chứ không phải lỗi mapping port.

## 10. `@Transactional` với `RANDOM_PORT` không rollback như nhiều người tưởng

Khi `@SpringBootTest(webEnvironment=RANDOM_PORT)` khởi động server HTTP thật, request do HTTP client phát ra thường chạy trên **server thread**, tách khỏi test method thread. Nếu test được gắn `@Transactional`, việc rollback **transaction của test method** sau khi kết thúc không tự rollback transaction đã commit ở server thread.

Ví dụ ý tưởng:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {
    // Một request HTTP POST có thể commit dữ liệu trên server thread.
    // Rollback của transaction test thread không tự hoàn tác commit đó.
}
~~~

Đây là snippet cảnh báo, không thuộc project runnable ở mục 5. Nếu test HTTP tạo dữ liệu, cần **cơ chế cleanup/fixture riêng**: xóa dữ liệu theo ID, reset database/container giữa test hoặc dùng strategy cô lập state phù hợp. Không kết luận “test annotation có `@Transactional` nên database luôn sạch”.

Bài ví dụ dùng GET không thay state để giữ test có thể chạy nhiều lần mà không phụ thuộc thứ tự.

## 11. Vì sao có thể không cần server thật?

Không phải mọi test Spring Boot đều nên dùng `RANDOM_PORT`. Nếu chỉ kiểm controller trả JSON đúng hoặc validation và exception handler, `@WebMvcTest`/`MockMvc` có thể đủ mà không mở socket:

~~~java
@WebMvcTest(GreetingController.class)
class GreetingControllerMvcTest {
    // @Autowired MockMvc...
    // mockMvc.perform(get("/api/greeting"))...
}
~~~

Đây là snippet minh họa; cần imports và test methods nếu tạo project hoàn chỉnh. Với `MockMvc`, không có cổng TCP thật nên không cần `@LocalServerPort`. Kiểm trực tiếp controller/service thuần còn có thể chỉ cần JUnit + constructor injection.

Dùng `RANDOM_PORT` khi mục tiêu yêu cầu:

- Kiểm request đi qua web server nhúng thật (Tomcat/Jetty/Undertow/Netty theo stack).
- Xác minh routing, HTTP headers, cookie, request-size, redirect hoặc behavior phụ thuộc container.
- Kiểm cổng ứng dụng và Actuator, URL thực tế hoặc quản lý port.
- Test luồng nhiều tầng bằng HTTP client, gần cách client thật tương tác.
- Kiểm các tác dụng liên quan proxy/TLS/network khi fixture đáp ứng mục tiêu.

Nếu mục tiêu chỉ là một phép tính đơn giản, mở hai embedded server và dùng HTTP client sẽ chậm và có nhiều điểm lỗi không liên quan.

## 12. Những lỗi thường gặp khi test server port

| Triệu chứng | Nguyên nhân thường gặp | Cách giải quyết |
| --- | --- | --- |
| `@LocalServerPort` không inject được | Test dùng `MOCK`/`NONE`, server chưa khởi động hoặc annotation sai package | Dùng `RANDOM_PORT` cho real HTTP, import đúng Boot 3.3 package |
| Port được đọc bằng `server.port` vẫn là 0 | Đang đọc cấu hình yêu cầu port, không phải port đã bind | Dùng `@LocalServerPort` / `local.server.port` |
| `Connection refused` tới `localhost:8080` | Server dùng random port hoặc không chạy | Lấy runtime port; kiểm server/context startup |
| `Connection refused` tới cổng đúng nhưng host sai | Server bind interface khác hoặc client ở container khác | Kiểm address/network namespace, hostname/routing |
| `@LocalManagementPort` thiếu giá trị | Không có management HTTP server riêng hoặc property runtime chưa tồn tại | Kiểm Actuator starter và management server configuration; dùng app port nếu chung |
| Health trả 404 trên application port | Management chạy ở cổng khác hoặc base path khác | Dùng management port và management path thực tế |
| Health trả 401/403 | Spring Security/management authorization áp dụng | Dùng test credentials phù hợp, không tắt security tùy tiện |
| Health trả 503 hoặc `DOWN` | Health contributor có trạng thái không khỏe | Kiểm fixture/hạ tầng và health groups trước khi sửa path |
| `Address already in use` | `DEFINED_PORT` hoặc management fixed port trùng tiến trình khác | Dùng `RANDOM_PORT`/`management.server.port=0` trong integration test |
| Test lỗi ngẫu nhiên khi chạy song song | Dùng global RestAssured port, static base URL hay state ngoài test | Giữ port/base URL theo instance/request, tránh static mutable state |
| Actuator endpoint không xuất hiện | Thiếu actuator starter, endpoint chưa expose, bị disable hoặc path khác | Kiểm dependency + management endpoint exposure/config |
| Test pass local nhưng fail CI | Hostname, bind address, timeout, container routing, port policy | Dùng địa chỉ phù hợp môi trường chạy và timeout hữu hạn |
| SSL handshake error | Gọi HTTPS bằng HTTP, sai certificate/truststore | Chọn đúng scheme và cấu hình trust test an toàn |
| Status đúng nhưng response sai JSON | Chỉ assert HTTP 200 | Parse/assert các field body quan trọng |
| Test rollback không dọn dữ liệu | HTTP request chạy trong transaction khác test thread | Dùng cleanup/fixture thích hợp |

### Phân biệt 404 và Connection refused

**Connection refused** thường là lỗi tầng TCP: không có listener nhận kết nối ở host/port đó hoặc kết nối bị từ chối. Nó khác với **HTTP 404**, nghĩa là client đã kết nối được tới một HTTP server và server trả “không tìm thấy route/resource”. Vì thế:

- Nếu **Connection refused**: kiểm listener, port, bind address và scheme/network.
- Nếu **404**: kiểm server nào nhận request, path/context-path/management base path và endpoint mapping.
- Nếu **401/403**: kiểm authentication/authorization trước, không mặc định sai port.
- Nếu **503 từ health**: có thể route đúng nhưng hệ thống hoặc health contributor chưa khỏe.

Phân tích theo tầng giúp tránh sửa sai: thêm `@LocalServerPort` sẽ không giải quyết một health endpoint không được expose; bật exposure không giải quyết một kết nối tới host không có server.

## 13. Dùng cấu hình management an toàn trong test

Một bộ cấu hình test rõ ràng có thể là:

~~~properties
# Các giá trị minh họa cho môi trường test local
server.port=0
management.server.port=0
management.endpoints.web.exposure.include=health,info
~~~

Khi dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)`, không nhất thiết cần thêm `server.port=0` thủ công vì annotation đã yêu cầu cổng ngẫu nhiên. Ví dụ class management ở mục 5.4 khai báo `management.server.port=0` ngay trong `properties` để test độc lập và rõ intent.

**Không đưa `management.endpoints.web.exposure.include=*` vào production chỉ để test cho tiện.** Một số Actuator endpoints có thể tiết lộ môi trường, metrics hoặc thao tác quản lý nhạy cảm. Chỉ expose những endpoint cần thiết, có authentication/authorization và network policy phù hợp.

### `management.server.port=-1` nghĩa là gì?

Trong Spring Boot, cấu hình:

~~~properties
management.server.port=-1
~~~

được dùng để **tắt management HTTP endpoints/server** trong những cấu hình phù hợp. Khi đó không thể kỳ vọng một URL management hoạt động hoặc `@LocalManagementPort` luôn có giá trị. Nếu test chỉ cần nghiệp vụ HTTP, việc tắt management có thể làm giảm phần phụ thuộc; nếu test mục tiêu là health/Actuator, phải bật management HTTP.

### Cổng quản trị riêng không phải ranh giới bảo mật duy nhất

Dù Actuator ở port riêng, một network policy hoặc proxy vẫn có thể làm nó truy cập được từ nơi không mong muốn. Test cổng ở local chỉ chứng minh **cấu hình ứng dụng trong môi trường test**, không thay thế kiểm security và deployment routing thực tế.

## 14. Luyện tập

**Bài A — chỉ application port:** Chạy `ApplicationPortHttpTest` nhiều lần. Ghi nhận port có thể khác, nhưng cả hai test vẫn pass. Giải thích vì sao `server.port=0` không thể dùng trực tiếp làm URL client.

**Bài B — hai cổng riêng:** Chạy `SeparateManagementPortHttpTest`, so sánh runtime application/management port và gửi GET tới hai URL tương ứng. Đổi nhầm port trong `managementUrl` sang `applicationPort` để quan sát behavior khác. Hoàn nguyên code sau khi kiểm.

**Bài C — thay base path:** Thêm `management.endpoints.web.base-path=/manage` vào test class management; sửa đường dẫn health thành `/manage/health`. Dự đoán request tới `/actuator/health` trên management port sẽ có kết quả không như mong đợi, trong khi request đúng path được chấp nhận.

**Bài D — context path ứng dụng:** Thêm property `server.servlet.context-path=/shop` cho test. Sửa `appUrl("/api/greeting")` thành `appUrl("/shop/api/greeting")`. Giải thích vì sao management URL ở cổng riêng không nhất thiết có tiền tố `/shop`.

**Bài E — mô phỏng cổng trùng:** Thử `DEFINED_PORT` với một fixed port đã bị tiến trình khác chiếm trong môi trường thử nghiệm riêng. Quan sát lỗi bind address và chuyển về `RANDOM_PORT`. Không giết một tiến trình production chỉ để “giải phóng” cổng cho test.

**Bài F — quản trị có bảo mật:** Nếu ứng dụng có Spring Security, thêm một test health hợp đồng yêu cầu 401 cho anonymous hoặc 200 cho user được cấp quyền, tùy cấu hình. Không mặc định health luôn 200 khi có authentication.

**Bài G — bảo vệ transaction:** Thêm một POST tạo entity trong môi trường test DB. Kiểm rằng rollback của test method không tự dọn dữ liệu do HTTP server thread đã commit; đề xuất fixture/cleanup độc lập.

## 15. Checklist trước khi hoàn thành test có port

- [ ] Tôi cần **HTTP server thật** hay chỉ cần MockMvc/unit test?
- [ ] Annotation `@SpringBootTest(webEnvironment=RANDOM_PORT)` được áp dụng đúng khi cần real HTTP?
- [ ] Tôi import `org.springframework.boot.test.web.server.LocalServerPort` đúng với Spring Boot 3.3?
- [ ] Tôi dùng **`local.server.port` thực tế**, không dùng giá trị cấu hình `server.port=0`?
- [ ] Nếu Actuator có server riêng, tôi có `spring-boot-starter-actuator`, `management.server.port` và `@LocalManagementPort` đúng không?
- [ ] Management server có thực sự chạy riêng hay dùng chung port? Không tự ép hai port phải khác khi config không yêu cầu?
- [ ] URL client đã có đúng **scheme, host, port, context path, endpoint path**?
- [ ] Test client chạy trong cùng network namespace với server nếu dùng loopback `127.0.0.1`?
- [ ] Có security/TLS/exposure/base-path làm thay đổi kết quả health không?
- [ ] Các test chạy song song có tránh global static port/base URL mutable không?
- [ ] Tôi có assert status **và** nội dung/hợp đồng cần thiết, không chỉ kiểm connection?
- [ ] Các test HTTP có state/transaction được cleanup đúng cách không?
- [ ] Gradle report xác nhận test được chạy (không nhầm với task UP-TO-DATE)?
- [ ] Những cổng ví dụ 8080, 51237, 53241 chỉ là minh họa, không bị hardcode vào kết quả test?

## 16. Tài liệu tham khảo chính thức

Các đường dẫn dưới đây giúp đối chiếu với **dòng Spring Boot 3.3** của project mẫu; khi dự án sử dụng phiên bản khác, hãy đọc đúng reference/Javadoc theo phiên bản đang dùng.

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): các chế độ `webEnvironment`, random port và HTTP client dành cho test.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.port=0`, cách khám phá runtime port và `@LocalServerPort`.
- [Spring Boot 3.3 — Actuator REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html): quy ước URL management endpoints.
- [Spring Boot 3.3 — LocalManagementPort API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html): annotation cho management HTTP port.
- [Spring Boot 3.3 — LocalServerPort API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalServerPort.html): annotation cho application HTTP port.

**Ghi nhớ:** `@LocalServerPort` lấy cổng **ứng dụng** được gán sau khi server thật khởi động. `@LocalManagementPort` lấy cổng **quản trị** khi có management web server riêng. `server.port=0` và `management.server.port=0` chỉ yêu cầu chọn cổng, không phải cổng để client kết nối. Luôn tạo URL từ **runtime port + đúng host/scheme/path**, xác định Actuator dùng chung hay khác port, và kiểm response qua một HTTP client thật khi mục tiêu là HTTP integration test.
