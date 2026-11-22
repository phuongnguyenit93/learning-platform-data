# `@SpringBootTest.webEnvironment`: `MOCK`, `NONE`, `RANDOM_PORT` và `DEFINED_PORT`

`@SpringBootTest` cho phép JUnit Jupiter tạo `ApplicationContext` thông qua Spring Boot `SpringApplication` để kiểm thử ứng dụng với dependency injection, cấu hình và bean thực. Tuy nhiên, **khởi tạo Spring context không đồng nghĩa mở HTTP server**. Thuộc tính `webEnvironment` xác định test có môi trường web mô phỏng, không có web, hay khởi động server embedded với một cổng HTTP thật.

Chọn sai mode có thể khiến test gọi nhầm server ngoài, kiểm `MockMvc` nhưng tưởng đã kiểm đường mạng, inject `@LocalServerPort` vào context không có cổng, hoặc tin rằng `@Transactional` rollback được mọi thay đổi do HTTP server thật gây ra. Bài này phân tích cơ chế, cách chọn mode theo phạm vi chứng minh, một dự án ví dụ **Java 17 + Spring Boot 3.5 + JUnit Jupiter** chạy được, và các lỗi thường gặp khi đưa test lên CI.

## 1. So sánh tổng quan

Enum `org.springframework.boot.test.context.SpringBootTest.WebEnvironment` gồm bốn lựa chọn:

| Mode | Context | Embedded HTTP server | Port TCP | Cách test phổ biến |
|---|---|---|---|---|
| **`MOCK`** — **mặc định** | Web application context mô phỏng khi có web stack; fallback non-web nếu thiếu | **Không** | **Không** | `MockMvc` + `@AutoConfigureMockMvc` (Servlet MVC), WebTestClient mock phù hợp |
| **`NONE`** | ApplicationContext với `WebApplicationType.NONE` | **Không** | **Không** | Kiểm bean, service, cấu hình không cần HTTP |
| **`RANDOM_PORT`** | WebServerApplicationContext | **Có** | **Có**, hệ điều hành cấp ngẫu nhiên qua `server.port=0` | `@LocalServerPort` + HTTP client thật |
| **`DEFINED_PORT`** | WebServerApplicationContext | **Có** | **Có**, theo `server.port` hoặc mặc định **8080** | HTTP client thật, kiểm cấu hình cổng |

Cú pháp:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;

@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
class ExampleSpringTest {
    // @Test methods trong file thật.
}
```

Đây chỉ là khung annotation, không phải test độc lập. Không truyền `webEnvironment` thì mặc định **`MOCK`**, không khởi động server thật. `@SpringBootTest` đã tích hợp `SpringExtension` của JUnit Jupiter nên thường không cần `@ExtendWith(SpringExtension.class)` riêng.

Hai trục lựa chọn cần nhớ: **có hay không có hạ tầng web**, và **có hay không có socket HTTP thật**. `MOCK` không phải `NONE`; `RANDOM_PORT` và `DEFINED_PORT` đều có server thật nhưng khác cách lấy port.

## 2. `MOCK`: kiểm MVC request trong tiến trình, không qua mạng

Trong ứng dụng Spring MVC, `MOCK` tạo web context với mock servlet environment; server Tomcat/Jetty/Undertow không bind HTTP socket. Để có `MockMvc` do Spring Boot cấu hình, kết hợp:

```java
@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
@AutoConfigureMockMvc
class MvcCheckTest {
    @Autowired
    MockMvc mvc;
}
```

Đây là snippet cấu trúc trong một test class có imports đúng; không có phương thức kiểm thử độc lập. Trong **Spring Boot 3.5**, `@AutoConfigureMockMvc` import từ `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`.

`MockMvc` mô phỏng HTTP request qua `DispatcherServlet` và các thành phần MVC/filter của Spring context, có thể test:

- Controller mapping, path/query parameters, binding, validation và exception handler.
- HTTP status, headers, body, JSON conversion và filter/security chain đã nạp.
- Phối hợp giữa controller và bean thật trong context, theo dependency của test.

`MockMvc` **không kiểm tra** cổng TCP, container startup, socket timeout, TLS termination hay networking deployment. **`MOCK` cũng không tự tạo `MockMvc` bean** trong mọi trường hợp; cần `@AutoConfigureMockMvc` khi muốn inject trong ví dụ Servlet. Nếu classpath không có web application type phù hợp, `MOCK` có thể trở thành context không web.

Đừng gọi `http://localhost:8080` qua JDK HttpClient từ một test MOCK rồi tin rằng request đi vào context đang được kiểm. Nó có thể đi tới một tiến trình hoàn toàn khác.

## 3. `NONE`: vẫn nạp Spring bean nhưng tắt môi trường web

`NONE` dùng `SpringApplication` với `WebApplicationType.NONE`. Những bean độc lập web như service, configuration, properties và các auto-configuration không yêu cầu HTTP vẫn có thể được nạp; không có servlet/reactive web environment phục vụ request.

Ví dụ khung:

```java
@SpringBootTest(webEnvironment = WebEnvironment.NONE)
class ServiceContextTest {
    @Autowired
    SomeService service;
}
```

`SomeService` là kiểu giả định và snippet trên chưa có `@Test`; mẫu hoàn chỉnh ở phần 6.

Lựa chọn NONE khi muốn xác minh Spring Boot startup, DI/configuration cho batch, message consumer hay backend service không cần HTTP. Lưu ý `NONE` **không tự thu nhỏ component scan**: một class `@RestController` vẫn có thể được tạo như bean nếu scan thấy, nhưng không có HTTP dispatcher/server để đưa request vào nó. Những bean đòi servlet-specific infrastructure có thể làm non-web context không khởi tạo được.

Nếu chỉ kiểm hàm thuần Java, không cần sử dụng `@SpringBootTest(NONE)`: JUnit + `new Service(...)` thường nhẹ hơn.

## 4. `RANDOM_PORT`: HTTP server thật với port động

`RANDOM_PORT` cấu hình `server.port=0`, để server embedded chọn một cổng còn trống khi mở socket. Test cần lấy cổng **thực tế sau khi khởi động**:

```java
import org.springframework.boot.test.web.server.LocalServerPort;

@LocalServerPort
private int port;
```

Snippet này thuộc một test class chạy server thật; không phải chương trình độc lập. `port` thường được dùng để tạo URI `http://127.0.0.1:` + port + `/hello`.

RANDOM_PORT là lựa chọn mặc định nên cân nhắc khi cần kiểm HTTP thật trong CI vì ít va chạm với ứng dụng khác so với port 8080 cố định. Tuy nhiên:

- Port được chọn **khi server/context khởi động**, không nhất thiết đổi trước mỗi method. Context cache có thể giữ cùng port cho nhiều test.
- Random port chỉ giải quyết việc **bind cổng HTTP**; không cô lập database, file, broker hoặc trạng thái singleton.
- Nếu server quản trị được cấu hình trên port riêng, khi test RANDOM_PORT nó có thể nhận một random port **khác** với cổng ứng dụng.
- `@LocalServerPort` không hoạt động như mong đợi trong `MOCK`/`NONE` vì các mode đó không có server thật công bố `local.server.port`.

## 5. `DEFINED_PORT`: server thật, sử dụng cổng cấu hình

`DEFINED_PORT` cũng mở server HTTP thật, nhưng **không tự ép `server.port=0`**. Nếu không có cấu hình khác, Spring Boot thường dùng **8080**; nếu đặt `server.port=19081`, server cố lắng nghe tại 19081:

```java
@SpringBootTest(
        webEnvironment = WebEnvironment.DEFINED_PORT,
        properties = "server.port=19081")
class FixedPortTest {
    // HTTP request tới server trên 19081.
}
```

Khung này chưa có test method. Trong test hoàn chỉnh nên xác nhận cổng thực tế bằng `@LocalServerPort` thay vì chỉ suy đoán từ tên mode.

**Quan trọng:** DEFINED_PORT không cấm cổng ngẫu nhiên. Vì nó **không tự ghi đè** `server.port`, nếu application configuration đã chủ ý đặt `server.port=0`, server có thể vẫn nhận random port. Tên enum nói lên cách test dùng cấu hình port sẵn có, không phải cam kết cổng nhất định luôn cố định.

Port định nghĩa sẵn dễ xung đột trên CI hoặc máy developer: nếu có process khác đang chiếm 19081, context sẽ fail vì bind socket. Với phần lớn HTTP integration tests, dùng RANDOM_PORT thuận lợi hơn; chọn DEFINED_PORT khi thật sự cần kiểm điều kiện cổng định sẵn.

## 6. Dự án ví dụ đầy đủ: một endpoint, bốn test class

Mục tiêu: Spring MVC endpoint `GET /hello` trả **`Hello, test!`**. `MOCK` gọi endpoint trong process qua MockMvc; `NONE` kiểm bean mà không khởi động HTTP; `RANDOM_PORT` và `DEFINED_PORT` gọi server thật qua JDK `HttpClient`. Dùng **Spring Boot 3.5.0** với Java 17 để imports có ngữ cảnh phiên bản rõ ràng. Mã không yêu cầu DB hay Spring Security.

```text
boot-web-env/
├── pom.xml
├── src/main/java/com/example/web/
│   ├── DemoApplication.java
│   ├── GreetingService.java
│   └── GreetingController.java
└── src/test/java/com/example/web/
    ├── MockModeTest.java
    ├── NoneModeTest.java
    ├── RandomPortModeTest.java
    └── DefinedPortModeTest.java
```

### 6.1. `pom.xml`

File Maven hoàn chỉnh:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>boot-web-env</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven parent quản lý các dependency Spring/JUnit tương thích. Starter web đưa Spring MVC và embedded servlet container vào classpath. Starter test cung cấp JUnit Jupiter, Spring TestContext và MockMvc theo Spring Boot 3.5. Khi áp dụng vào dự án thực, chọn bản vá Boot 3.5 đã được phê duyệt.

### 6.2. Source code ứng dụng

File **`src/main/java/com/example/web/DemoApplication.java`**:

```java
package com.example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File **`src/main/java/com/example/web/GreetingService.java`**:

```java
package com.example.web;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String message() {
        return "Hello, test!";
    }
}
```

File **`src/main/java/com/example/web/GreetingController.java`**:

```java
package com.example.web;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return service.message();
    }
}
```

`@RestController` đưa chuỗi trả về vào HTTP response body; nhờ `produces = TEXT_PLAIN_VALUE`, kết quả rõ ràng là text. Các class nằm trong package `com.example.web`, cho phép `@SpringBootApplication` tự tìm service/controller trong ví dụ.

### 6.3. Test MOCK

File **`src/test/java/com/example/web/MockModeTest.java`**:

```java
package com.example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
@AutoConfigureMockMvc
class MockModeTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void servesHelloUsingMockMvcWithoutTcp() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, test!"));
    }
}
```

Test dùng **MVC request mô phỏng** trong context. Nó xác nhận Spring MVC mapping và response, không chứng minh embedded server đã mở một socket.

### 6.4. Test NONE

File **`src/test/java/com/example/web/NoneModeTest.java`**:

```java
package com.example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.context.ApplicationContext;
import org.springframework.web.context.WebApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(webEnvironment = WebEnvironment.NONE)
class NoneModeTest {
    @Autowired
    private ApplicationContext context;

    @Autowired
    private GreetingService service;

    @Test
    void loadsServiceWithoutServletWebContext() {
        assertFalse(context instanceof WebApplicationContext);
        assertEquals("Hello, test!", service.message());
    }
}
```

Kết quả mong đợi: Spring bean được inject bình thường, context không phải Servlet WebApplicationContext và **không có HTTP request**.

### 6.5. Test RANDOM_PORT

File **`src/test/java/com/example/web/RandomPortModeTest.java`**:

```java
package com.example.web;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class RandomPortModeTest {
    @LocalServerPort
    private int port;

    @Test
    void servesHelloOverRealHttpOnRandomPort() throws Exception {
        assertTrue(port > 0);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/hello"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        assertEquals(200, response.statusCode());
        assertEquals("Hello, test!", response.body());
    }
}
```

Server thực khởi động trước method test, `@LocalServerPort` nhận port do hệ điều hành cấp. JDK `HttpClient` gửi request HTTP thật, do đó test kiểm cả kết nối loopback tới server embedded.

### 6.6. Test DEFINED_PORT

File **`src/test/java/com/example/web/DefinedPortModeTest.java`**:

```java
package com.example.web;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = WebEnvironment.DEFINED_PORT,
        properties = "server.port=19081")
class DefinedPortModeTest {
    @LocalServerPort
    private int port;

    @Test
    void servesHelloOverRealHttpOnConfiguredPort() throws Exception {
        assertEquals(19081, port);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/hello"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        assertEquals(200, response.statusCode());
        assertEquals("Hello, test!", response.body());
    }
}
```

Khác với RANDOM_PORT, test này chủ động yêu cầu **19081**. Nếu port bị chiếm, test có thể thất bại ngay khi tạo context. Không nên chạy nhiều phiên bản của test này đồng thời trên cùng host.

### 6.7. Chạy và kết quả mong đợi

Tại thư mục có `pom.xml`, nếu đã cài Maven:

```bash
mvn test
```

Nếu dự án có Maven Wrapper:

```bash
./mvnw test
```

Hoặc chạy riêng từng lớp:

```bash
./mvnw -Dtest=MockModeTest test
./mvnw -Dtest=NoneModeTest test
./mvnw -Dtest=RandomPortModeTest test
./mvnw -Dtest=DefinedPortModeTest test
```

Windows dùng `mvnw.cmd` nếu có wrapper. Với đúng bốn class ví dụ, kỳ vọng **4 test PASS, 0 FAIL** nếu **cổng 19081 đang trống**, JVM có quyền mở loopback TCP và dependency được tải đầy đủ. Không có stdout nghiệp vụ cố định; Maven Surefire hiển thị báo cáo theo phiên bản. Nếu môi trường không cho mở socket, hai bài MOCK/NONE có thể chạy trong khi bài RANDOM_PORT/DEFINED_PORT không chạy được.

## 7. Client nào phù hợp với mode nào?

| Công cụ | Sử dụng socket thật? | Phạm vi sử dụng |
|---|---|---|
| `MockMvc` | **Không** | Spring MVC MOCK hoặc `@WebMvcTest` |
| `java.net.http.HttpClient` | **Có**, nếu gọi URL TCP thật | RANDOM_PORT/DEFINED_PORT |
| `TestRestTemplate` | **Có** | Test embedded HTTP server trong các bản Boot có helper/auto-config phù hợp |
| `WebTestClient` | **Tùy binding** — mock/in-process hoặc server thật | WebFlux và các trường hợp HTTP phù hợp |
| `@LocalServerPort` | Không phải client; cung cấp port đang lắng nghe | Các test có embedded server thật |

Lưu ý phiên bản: Spring Boot 3.5 có `TestRestTemplate` và các helper tương ứng trong test tooling. **Spring Boot 4.0+** điều chỉnh việc chia module và auto-configuration cho client test; cần kiểm imports/dependencies/version thay vì giả định `TestRestTemplate` hoặc `@AutoConfigureMockMvc` có cùng package giữa mọi dòng. Vì vậy ví dụ HTTP server thật dùng **JDK 17 HttpClient** để tránh phụ thuộc thay đổi này.

Không chạy request đến `localhost:8080` từ một bài MOCK: việc request thành công có thể chỉ nghĩa là một **process khác** đang nghe trên port đó. Chỉ dùng URL/port do test server thực cung cấp.

## 8. Servlet MVC và WebFlux là một chiều cấu hình khác

Cả RANDOM_PORT và DEFINED_PORT đều hỗ trợ ngữ cảnh Servlet/Reactive khi web stack phù hợp. Spring Boot phát hiện từ dependency: có Spring MVC thường chọn servlet; chỉ có WebFlux chọn reactive; cả hai cùng có mặt thì MVC thường ưu tiên.

Nếu muốn kiểm WebFlux khi cả MVC và WebFlux đều trên classpath, có thể chủ động cấu hình:

```java
@SpringBootTest(
        webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = "spring.main.web-application-type=reactive")
class ReactiveTestConfigExample {
    // Đây là snippet, cần WebFlux dependency và @Test cụ thể.
}
```

`@AutoConfigureMockMvc` dùng cho **Servlet MVC**, không phải mọi loại WebFlux test. Một `WebTestClient` có thể bind tới mock reactive context hoặc HTTP server thật tùy cách cấu hình. Hãy phân biệt **web environment** và **web stack** để biết chính xác test đang chứng minh điều gì.

## 9. Cẩn trọng với `@Transactional` và HTTP server thật

Giả sử test thêm `@Transactional` và gửi request `POST /orders` tới server thật trong RANDOM_PORT:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {
    // Gửi HTTP thật để tạo order ở server thread.
}
```

Đoạn này minh họa rủi ro, không phải file chạy độc lập. Trong REAL HTTP mode, **client test và server xử lý request nằm ở các thread/transaction khác nhau**. Test-managed transaction có thể được rollback sau test, nhưng **giao dịch server-side đã commit không tự được rollback** theo transaction của test thread.

Vì thế đừng cho rằng test POST/PUT tạo dữ liệu sẽ tự dọn chỉ nhờ annotation `@Transactional`. Cần test database riêng, fixture độc lập, cleanup/transaction có chủ đích; với timeout, retry hoặc ghi nhiều lần cần kiểm idempotency đúng cấp. `@DirtiesContext` không phải phương án đảm bảo xóa dữ liệu DB đã commit: nó đóng/bỏ Spring context khỏi cache, không hoàn tác mọi side effect.

Trong MOCK/MockMvc đồng bộ, một số mã có thể chạy cùng thread và transaction context với test, nhưng xử lý bất đồng bộ, event, executor hay các thread khác vẫn cần quản lý transaction riêng. Không áp dụng một quy tắc rollback cho tất cả mode và tác vụ.

## 10. Context cache, hiệu năng và CI

Spring TestContext cache `ApplicationContext` theo cấu hình. Các test có cùng context config có thể dùng lại bean và server; thay đổi `webEnvironment`, active profiles, properties, test mock bean hay `@DirtiesContext` có thể làm phát sinh context khác và tăng thời gian khởi động.

- RANDOM_PORT không hứa **mỗi method một port mới**. Context đã cache có thể dùng cùng port xuyên nhiều method/class.
- DEFINED_PORT dễ gây bind collision khi nhiều context/CI job cùng dùng port 19081.
- `@DirtiesContext` có thể khiến server bị đóng và khởi động lại, làm test chậm và đổi port ở RANDOM_PORT.
- `@TestInstance(PER_METHOD)` chỉ tạo object test mới, **không** đồng nghĩa tạo ApplicationContext mới.
- RANDOM_PORT không tự cô lập database hoặc broker: dữ liệu và trạng thái dùng chung vẫn cần chiến lược cleanup.

Chọn mode nhẹ nhất còn chứng minh đúng ranh giới: JUnit thuần cho logic độc lập, `@WebMvcTest` cho web slice, MOCK khi cần context Spring Boot rộng nhưng không cần socket, RANDOM_PORT khi cần HTTP thật.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `MockMvc` không inject được | Chỉ có MOCK mà thiếu `@AutoConfigureMockMvc`, hoặc không phải MVC | Cấu hình MockMvc đúng version và web stack |
| `@LocalServerPort` không resolve | Không có embedded server trong MOCK/NONE | Dùng RANDOM_PORT/DEFINED_PORT nếu cần HTTP thật |
| Test MOCK gọi localhost rồi “pass” | Gọi nhầm ứng dụng ngoài test | Dùng MockMvc thay vì HTTP client thật |
| DEFINED_PORT báo port in use | Có process/context khác đang nghe trên port đó | Giải phóng port hoặc đổi RANDOM_PORT |
| RANDOM_PORT request trả 404 | Sai URI, context path, mapping hoặc web stack | Kiểm port thực, endpoint và route |
| NONE thiếu servlet bean | Context được tạo không web | Chọn MOCK hoặc web server mode nếu cần web |
| MOCK pass nhưng production HTTP lỗi | Chưa test socket, server config hoặc proxy | Bổ sung server thật/integration/deployment test |
| DB còn dữ liệu sau HTTP test | Server transaction khác transaction của test | Dọn dữ liệu hoặc rollback có chủ đích tại server |
| CI chạy chậm do nhiều context | Nhiều mode/profiles, lạm dụng `@DirtiesContext` | Chỉ nạp context phù hợp, tối ưu cache |
| Test reactive thực tế chạy MVC | Spring MVC thường ưu tiên khi cả hai trên classpath | Kiểm web-application-type và dependency |

## 12. Checklist chọn mode

- [ ] Tôi xác định được test cần **bean non-web**, **web mock**, hay **server thật**.
- [ ] Tôi biết MOCK là mặc định của `@SpringBootTest`.
- [ ] Tôi không hiểu nhầm MOCK là HTTP server, hoặc NONE là MOCK.
- [ ] Nếu dùng MockMvc, tôi đã bật auto-configuration thích hợp.
- [ ] Nếu dùng RANDOM_PORT, tôi lấy port thực từ `@LocalServerPort`, không hardcode 8080.
- [ ] Nếu dùng DEFINED_PORT, tôi kiểm port cấu hình, port bận và test song song.
- [ ] HTTP client/mock client được gắn vào **đúng** server/context.
- [ ] Tôi phân biệt MVC/Servlet và WebFlux/Reactive.
- [ ] Tôi kiểm tra thay đổi client-helper theo version Boot đang dùng.
- [ ] Với DB và server thật, tôi không dựa duy nhất vào `@Transactional` test để cleanup.
- [ ] Tôi hiểu context cache và `@DirtiesContext` ảnh hưởng port, hiệu năng và trạng thái chung.
- [ ] Tôi chạy test bằng build tool, đọc assertion thay vì suy luận từ việc ứng dụng chỉ start thành công.

**Ghi nhớ:** **MOCK** = web context mô phỏng **không socket**; **NONE** = Spring context **không web**; **RANDOM_PORT** = server HTTP thật với **port ngẫu nhiên**; **DEFINED_PORT** = server HTTP thật theo **port cấu hình**. Chọn theo phạm vi cần chứng minh, không chọn chỉ vì mode nghe có vẻ “mạnh hơn”.

### Nguồn tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — WebEnvironment Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.WebEnvironment.html)
- [Spring Boot 4.0 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html)
