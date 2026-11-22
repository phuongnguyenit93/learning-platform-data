# `@SpringBootTest(webEnvironment = MOCK)` không có nghĩa embedded server đang lắng nghe

> **Module:** Spring Boot – testing  
> **Nhóm:** `@SpringBootTest`  
> **Chủ đề:** MOCK không đồng nghĩa có embedded server đang lắng nghe  
> **Mục tiêu:** Phân biệt mock web environment và HTTP server thực; dùng `MockMvc` đúng mục đích; biết lúc nào phải chọn `RANDOM_PORT` hoặc `DEFINED_PORT`; xây được test Java 17/Spring Boot có thể chứng minh hai chế độ khác nhau.

## 1. Kết luận cốt lõi

**`@SpringBootTest` mặc định sử dụng `webEnvironment = MOCK` và không khởi động embedded HTTP server.** Spring Boot vẫn tạo `ApplicationContext`, tải các bean cần thiết, thiết lập môi trường web mô phỏng và cho phép kiểm tra request/response bằng `MockMvc`. Nhưng không có nghĩa Tomcat/Jetty/Undertow đang mở cổng TCP để trình duyệt, `curl` hay `HttpClient` bên ngoài kết nối vào.

```java
@SpringBootTest // webEnvironment = MOCK là mặc định
@AutoConfigureMockMvc
class ApplicationMockTest {
    // Dùng MockMvc kiểm thử MVC mà không mở cổng HTTP.
}
```

Trong khi đó:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApplicationRealHttpTest {
    // Spring Boot khởi động embedded HTTP server thực trên cổng ngẫu nhiên.
}
```

Hai đoạn trên là **minh họa annotation**, chưa phải class test độc lập có imports/test method. Một dự án chạy đầy đủ nằm ở phần 5.

**Phân biệt rõ bốn đối tượng:**

- **Spring ApplicationContext:** bộ chứa bean, dependency injection, configuration và lifecycle.
- **Mock web environment:** context được cấu hình để thao tác theo mô hình Servlet/WebFlux mà không cần embedded listener.
- **`MockMvc`:** bộ công cụ kiểm tra Spring MVC bằng mock request/response **trong tiến trình**, gọi vào `DispatcherServlet`/MVC infrastructure, không gửi TCP/HTTP socket ra máy chủ.
- **Embedded HTTP server:** server thật (thường là Tomcat khi dùng `spring-boot-starter-web` mặc định) mở socket và lắng nghe cổng, nhận HTTP request từ client ngoài tiến trình hoặc từ `HttpClient`/REST client.

**Bẫy thường gặp:** `mockMvc.perform(get("/api/..."))` trả `200 OK`, nhưng `curl http://localhost:8080/api/...` báo “connection refused”. Đó không phải mâu thuẫn: `MockMvc` đã xử lý request bên trong test context, trong khi test chế độ `MOCK` chưa khởi động server trên cổng 8080.

## 2. Vì sao tên `MOCK` dễ gây hiểu nhầm?

Chữ “mock” ở đây nói về **môi trường web đầu vào**, không có nghĩa:

- Spring không tạo bean thật.
- Controller/service/repository đều bị Mockito mock.
- `@SpringBootTest` chỉ thực hiện unit test.
- Bất kỳ HTTP request nào cũng sẽ đi qua server socket.
- Database, REST client hướng ra ngoài, scheduler hoặc message publisher tự động bị mock.
- `spring-boot-starter-web` có Tomcat trên classpath thì Tomcat luôn lắng nghe.

Với một ứng dụng Spring MVC thông thường, `@SpringBootTest(webEnvironment=MOCK)` có thể nạp **toàn bộ logic, configuration và bean ứng dụng**. Chỉ phần **server HTTP đang chạy** không được tạo theo kiểu `RANDOM_PORT`/`DEFINED_PORT`. Nếu một bean thực gọi API ngoài trong constructor, `@PostConstruct` hoặc ngay trong test method, nó **vẫn có thể tạo outbound network connection**.

Điều này khác hoàn toàn việc khai báo `@MockitoBean`: annotation đó thay/định nghĩa một bean cụ thể bằng Mockito mock. `@MockitoBean` không thay đổi `webEnvironment`; muốn không gọi dịch vụ ngoài cần mock/fake chính dependency bên ngoài ấy. Một test dùng `@SpringBootTest(MOCK)` nhưng repository thật nối production database vẫn nguy hiểm. Hãy cấu hình profile test, Testcontainers, fake HTTP adapter, credentials tách biệt và hạn chế quyền mạng.

### 2.1. `MockMvc` xử lý request như thế nào?

```text
                     MOCK web environment
                    @SpringBootTest(MOCK)
                              │
                              ▼
                       ApplicationContext
                              │
                              ▼
Test method → MockMvc.perform(GET /api/greet/Mai)
                              │
                              ▼
                   MockHttpServletRequest
                              │
                              ▼
                       DispatcherServlet
                              │
                              ▼
                    Controller → Service
                              │
                              ▼
                   MockHttpServletResponse
                              │
                              ▼
           .andExpect(status().isOk())
           .andExpect(content().string(...))

       KHÔNG có TCP accept()/listen() ở đây.
       KHÔNG gửi packet tới localhost:8080.
```

Điểm mạnh: nhanh hơn việc dựng server thực, kiểm tra được mapping, converters, validation/exception handling ở Spring MVC, filters nếu chúng được cấu hình, controller advice, security filter chain trong phạm vi hỗ trợ. Điểm giới hạn: không kiểm tra chính xác tất cả hành vi của servlet container thực, network, TLS, connector, compression, socket/timeout hay container error-page dispatch.

### 2.2. HTTP request thực trong `RANDOM_PORT`

```text
                      RANDOM_PORT
                 @SpringBootTest(RANDOM_PORT)
                              │
                              ▼
                        WebServer context
                              │
                  Embedded Tomcat starts
                              │
                       TCP port 49xxx
                              ▲
                              │
    Java HttpClient  ── HTTP request qua 127.0.0.1:49xxx
                              │
                              ▼
                     Servlet container
                              │
                              ▼
                 DispatcherServlet → Controller
                              │
                              ▼
                   HTTP response qua socket
                              │
                              ▼
                      Java HttpClient
```

Cổng `49xxx` chỉ là **ví dụ**, không phải cổng cố định. Spring Boot yêu cầu OS cấp một cổng còn trống và cung cấp giá trị qua `@LocalServerPort` khi ứng dụng khởi chạy ở chế độ có web server thực.

## 3. Bốn giá trị của `SpringBootTest.WebEnvironment`

| Chế độ | Tạo context | Embedded server có lắng nghe? | Client thường dùng | Khi nào nên chọn |
| --- | --- | --- | --- | --- |
| **`MOCK`** (mặc định) | Web `ApplicationContext` dạng mock nếu công nghệ web hiện diện | **Không** | `MockMvc`; hoặc client bind tới mock context tùy stack | Kiểm tra MVC/framework/application wiring mà không cần socket |
| **`RANDOM_PORT`** | Web-server `ApplicationContext` | **Có**, cổng do hệ điều hành cấp | `HttpClient`, `WebTestClient`, `TestRestTemplate` khi phù hợp | Kiểm thử HTTP thật, tích hợp servlet container, tránh đụng cổng |
| **`DEFINED_PORT`** | Web-server `ApplicationContext` | **Có**, cổng cấu hình hoặc mặc định 8080 | HTTP client tới host:port xác định | Test bắt buộc cổng đã định; khó chạy song song hơn |
| **`NONE`** | `ApplicationContext` không có web environment | **Không** | Gọi service/bean Java trực tiếp | Kiểm tra logic/bean không cần MVC/HTTP |

Các ngoại lệ cần nhớ:

- Với `MOCK`, nếu không có môi trường web trên classpath, Spring Boot có thể tạo `ApplicationContext` phi web thông thường.
- Chế độ `RANDOM_PORT` và `DEFINED_PORT` có thể là **servlet hoặc reactive** tùy dependencies và cấu hình.
- `DEFINED_PORT` mặc định lấy `server.port` của ứng dụng hoặc 8080 nếu không có cấu hình tương ứng. Mở cổng cố định có nguy cơ xung đột với process khác.
- `NONE` không có web environment dù project có dependency web; nó thích hợp khi chỉ cần các bean không-web.

### 3.1. Vì sao `server.port=0` không biến `MOCK` thành server thật?

`server.port=0` được dùng trong **chế độ có embedded server thực** để OS cấp một cổng trống. Trong `MOCK`, embedded server không được khởi động nên đơn thuần đặt `server.port=0` không tạo listener.

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "server.port=0")
@AutoConfigureMockMvc
class StillNoSocketTest {
    // "server.port=0" là property; không có embedded server thực.
}
```

Đoạn trên là minh họa cách cấu hình, chưa phải runnable test. **Không đồng nhất property `server.port` với property runtime `local.server.port`:** `server.port` biểu đạt ý định cấu hình; `local.server.port` được phát hành khi web server thực đã bind thành công trong test runtime phù hợp.

### 3.2. Vì sao `@AutoConfigureMockMvc` quan trọng?

`@SpringBootTest` tự nạp context, nhưng **không tự bảo đảm có bean `MockMvc` được cấu hình để inject**. Với Spring MVC hãy thêm `@AutoConfigureMockMvc` khi muốn sử dụng `@Autowired MockMvc`:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ControllerMockTest {
    @Autowired
    MockMvc mvc;
}
```

`@WebMvcTest(SomeController.class)` cũng **tự auto-configure `MockMvc`** và chỉ nạp web slice, không phải toàn bộ application context. Vì vậy:

- `@SpringBootTest(MOCK) + @AutoConfigureMockMvc`: context ứng dụng rộng, mock HTTP request/response.
- `@WebMvcTest`: MVC slice hẹp, mock HTTP request/response, thường dùng `@MockitoBean` cho service dependency.
- `@SpringBootTest(RANDOM_PORT)`: context rộng **và embedded HTTP server thật**.

Từ “full context” và “real HTTP server” là **hai trục khác nhau**, không được đánh đồng.

## 4. Chọn mức test theo điều muốn chứng minh

| Điều cần chứng minh | Công cụ phù hợp | Điều chưa chứng minh |
| --- | --- | --- |
| Tính toán đúng một giá trị | JUnit + Java class, không cần Spring | Spring bean wiring/MVC |
| Controller map `GET /api/...` đúng và trả đúng JSON/text | `@WebMvcTest` + `MockMvc` | Cổng mạng/Tomcat connector, service thật nếu service đã mock |
| Controller và service thật phối hợp, filter/exception handler có hiệu lực trong MVC | `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Listener/transport HTTP thật |
| Ứng dụng thực nhận request qua HTTP TCP và trả response | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Hạ tầng production như ingress/TLS/load balancer nếu không nằm trong test |
| HTTP server chạy ở cổng đã định để hệ thống phụ truy cập | `@SpringBootTest(DEFINED_PORT)` | Không bảo đảm hết xung đột cổng |
| Spring tạo bean và profile/cấu hình không-web đúng | `@SpringBootTest(NONE)` hoặc test context phù hợp | HTTP endpoint |

**Nguyên tắc:** Không dùng `MockMvc` để tuyên bố server thật đang lắng nghe. Ngược lại, không ép mọi test controller sang `RANDOM_PORT`; nhiều kiểm tra MVC có thể thực hiện nhanh hơn trong `MOCK`. Chọn **mức chi phí tương ứng với rủi ro mà test cần phát hiện**.

## 5. Ví dụ hoàn chỉnh: cùng API, hai đường chạy khác nhau

Phần này dùng **Java 17+, Spring Boot 3.5.16, Maven, JUnit Jupiter, Spring MVC**. Dự án có một API rất nhỏ, một test `MOCK`, một test `RANDOM_PORT` và một `@WebMvcTest`. Khi cấu hình đúng, có thể chạy chúng bằng `mvn test`.

### 5.1. Cấu trúc project

```text
mock-vs-http-server/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/webmode/
    │       ├── WebModeApplication.java
    │       ├── GreetingService.java
    │       └── GreetingController.java
    └── test/
        └── java/com/example/webmode/
            ├── MockEnvironmentTest.java
            ├── RealHttpServerTest.java
            └── WebMvcSliceTest.java
```

Lưu ý về tên tệp: Java yêu cầu các public types nằm trong file trùng tên. Các code blocks bên dưới biểu diễn **các tệp riêng**, không đặt nhiều `package` vào một tệp.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mock-vs-http-server</artifactId>
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

Với `spring-boot-starter-web` chuẩn ở dòng Boot 3.5, server embedded mặc định thường là Tomcat khi **có chế độ chạy server**. Dependency này ở classpath **không làm `MOCK` tự bind port**. `spring-boot-starter-test` ở `scope=test` mang các API JUnit, Spring Test/MockMvc, Mockito và AssertJ cho test.

### 5.3. Mã ứng dụng

```java
// src/main/java/com/example/webmode/WebModeApplication.java
package com.example.webmode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebModeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebModeApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/webmode/GreetingService.java
package com.example.webmode;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greeting(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Xin chào, " + name.trim() + "!";
    }
}
```

```java
// src/main/java/com/example/webmode/GreetingController.java
package com.example.webmode;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(value = "/api/greet/{name}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String greet(@PathVariable String name) {
        return service.greeting(name);
    }
}
```

API có một contract:

- `GET /api/greet/Mai` → HTTP **200**, body text **`Xin chào, Mai!`**.
- Không cần database, security, cloud secret hoặc API ngoài.
- Controller gọi service thật khi cả hai nằm trong application context; nếu slice test mock service thì chỉ kiểm tra mapping/response từ dữ liệu mock.

### 5.4. Test 1: `MOCK` vẫn xử lý request nhưng không có listener

```java
// src/test/java/com/example/webmode/MockEnvironmentTest.java
package com.example.webmode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
@AutoConfigureMockMvc
class MockEnvironmentTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @Autowired
    Environment environment;

    @Test
    void mvcWorksWithoutAListeningWebServer() throws Exception {
        mvc.perform(get("/api/greet/Mai"))
                .andExpect(status().isOk())
                .andExpect(content().string("Xin chào, Mai!"));

        // Trong project mẫu ở chế độ MOCK không có web-server context.
        assertFalse(context instanceof WebServerApplicationContext);

        // Đây là runtime property của listener, không phải server.port config.
        assertNull(environment.getProperty("local.server.port"));
    }
}
```

**Giải thích:**

- `@SpringBootTest(webEnvironment=MOCK)` tạo mock servlet web environment, không khởi động embedded server.
- `@AutoConfigureMockMvc` bổ sung `MockMvc` để kiểm thử Spring MVC trong cùng process.
- `mvc.perform(...)` đi qua MVC infrastructure và service thật của project này, vì không có Mockito override.
- `assertFalse(context instanceof WebServerApplicationContext)` diễn đạt sự khác biệt của context MOCK với web-server context trong cấu hình Servlet hiện tại.
- `assertNull(environment.getProperty("local.server.port"))` cho thấy **không có cổng listener thực được công bố** trong môi trường test mẫu.

Không dùng một kết nối `HttpClient` tới `localhost:8080` để “chứng minh MOCK không lắng nghe” bằng `assertThrows(ConnectionException...)`. Nếu có ứng dụng khác ở cổng 8080, kết nối sẽ không thất bại và test trở nên phụ thuộc môi trường. Sự khác biệt đã được xác lập qua mode và test runtime properties.

**Không nên viết:** `@LocalServerPort int port` rồi mong nó chứa port khi `MOCK` chạy. Không có HTTP listener của test để cấp giá trị. Nếu cố inject property không tồn tại, test có thể lỗi khi tạo context/test instance.

### 5.5. Test 2: `RANDOM_PORT` mở HTTP server thật

```java
// src/test/java/com/example/webmode/RealHttpServerTest.java
package com.example.webmode;

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

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {

    @LocalServerPort
    int port;

    @Test
    void sendsRealHttpRequestToAnEmbeddedListener() throws Exception {
        assertTrue(port > 0, "A real server port must be allocated");

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/greet/Mai");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("Xin chào, Mai!", response.body());
    }
}
```

**Giải thích:**

1. `RANDOM_PORT` yêu cầu Spring Boot dựng web-server context và embedded server thực, bind một TCP port do OS chọn.
2. `@LocalServerPort` nhận giá trị cổng đã mở. Nó đến từ runtime listener, không phải một số cứng như 8080.
3. `HttpClient` của JDK thực hiện kết nối HTTP tới địa chỉ loopback và nhận response qua socket.
4. Assertion kiểm tra cả **server port được cấp**, status 200 và body đúng contract.
5. Client và server chạy trong cùng test JVM nhưng là **hai đầu kết nối HTTP qua TCP** — khác với `MockMvc`, không gọi trực tiếp mock servlet request object.

**Điểm thiết thực:** Không tạo URL cố định `http://localhost:8080` cho test `RANDOM_PORT`. Port ngẫu nhiên là để tránh xung đột cổng, cho phép chạy nhiều test suite/process độc lập và giảm giả định môi trường. Không cố dự đoán port trước khi test khởi động.

### 5.6. Test 3: `@WebMvcTest` cũng không có server thực

```java
// src/test/java/com/example/webmode/WebMvcSliceTest.java
package com.example.webmode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class WebMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    GreetingService service;

    @Test
    void controllerMapsAndRendersMockServiceResponse() throws Exception {
        when(service.greeting("An")).thenReturn("Xin chào, An!");

        mvc.perform(get("/api/greet/An"))
                .andExpect(status().isOk())
                .andExpect(content().string("Xin chào, An!"));

        verify(service).greeting("An");
    }
}
```

**Phạm vi khác test 1:** `@WebMvcTest` chỉ tập trung vào một lát MVC và mock service dependency, còn `@SpringBootTest(MOCK)` test 1 nạp context ứng dụng rộng và dùng service thật. **Cả hai đều không tạo embedded server listener.** Test 3 không chứng minh service thực xử lý tên đúng vì service đã được Mockito stub; cần unit/integration test riêng cho logic đó.

### 5.7. Chạy project và hiểu số test

Yêu cầu: JDK 17+ và Maven có thể resolve các dependencies trong `pom.xml`. Từ thư mục `mock-vs-http-server`:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=MockEnvironmentTest test
mvn -Dtest=RealHttpServerTest test
mvn -Dtest=WebMvcSliceTest test
```

Với ba class test ở trên, mỗi class có **một phương thức `@Test`**, nên khi chạy `mvn test` trên project mẫu sẽ có **3 test methods** được thực thi (không tính các test khác nếu bạn tự thêm).

**Đầu ra cần xác nhận:**

- `MockEnvironmentTest`: `MockMvc` nhận response 200 và `Xin chào, Mai!`; không có `WebServerApplicationContext`; `local.server.port` chưa được cung cấp.
- `RealHttpServerTest`: Spring Boot bind port ngẫu nhiên lớn hơn 0, JDK `HttpClient` nhận response thật 200 và body `Xin chào, Mai!`.
- `WebMvcSliceTest`: Controller mapping và response từ service mock đúng, không mở server thật.

Log Maven/Spring, cổng ngẫu nhiên, thời gian chạy và thứ tự khởi tạo context khác nhau theo máy, không có stdout chính xác cố định. **Không coi việc nhìn thấy dòng “Tomcat initialized” trong log của một test khác là bằng chứng rằng `MOCK` đã mở server:** cả suite chạy nhiều test context độc lập; test `RANDOM_PORT` có thể được thực thi trước/sau trong cùng lần chạy Maven.

## 6. Những hiểu nhầm về “server running”

### 6.1. `mvn test` khác `mvn spring-boot:run`

`mvn test` khởi chạy test runner với các application context khác nhau theo annotation từng test class. Trong suite có cả `MOCK` và `RANDOM_PORT`, chỉ test cần server thật mới phải khởi động embedded listener.

`mvn spring-boot:run` là chạy **ứng dụng bình thường**. Vì project mẫu có `spring-boot-starter-web` và không có cấu hình đặc biệt, Spring Boot thường sẽ mở cổng 8080 (trừ khi bị override):

```bash
mvn spring-boot:run
```

Trong terminal khác, sau khi ứng dụng khởi động:

```bash
curl --fail http://localhost:8080/api/greet/Mai
```

Body trả về của ứng dụng mẫu là:

```text
Xin chào, Mai!
```

Nếu port 8080 đã bị chiếm, ứng dụng thường không khởi động được trên port đó; hãy chọn port khác bằng cấu hình runtime phù hợp. **Lệnh `curl` ở đây kiểm tra ứng dụng đang chạy bình thường, không chứng minh test `MOCK` có listener.**

### 6.2. Vì sao gửi request bằng `MockMvc` được dù không có cổng?

Vì `MockMvc` xây `MockHttpServletRequest` trong bộ nhớ, sau đó gọi vào `DispatcherServlet`/handler mapping/filters/controller trực tiếp theo cơ chế Spring MVC Test. Nó không mở cổng để nhận HTTP từ máy khác. Tên method `perform(get(...))` trông giống HTTP, nhưng không có giao thức TCP ở ranh giới đó.

`MockMvc` có thể chạy dưới `@WebMvcTest`, `@SpringBootTest(MOCK) + @AutoConfigureMockMvc`, hoặc cấu hình `MockMvcBuilders` thủ công. **Sự tồn tại của một bean `MockMvc` không đồng nghĩa tồn tại bean embedded servlet container đang nghe cổng.**

### 6.3. Vì sao test thấy bean `TomcatServletWebServerFactory` nhưng không có server?

Trong ứng dụng web, auto-configuration và dependencies có thể tạo bean/factory/configuration liên quan tới embedded server. Nhưng một **factory** không đồng nghĩa một **server instance đang chạy**, và một server class ở classpath không đồng nghĩa một listener đã bind port. Chỉ kết luận có server khi ứng dụng đã khởi động web-server context phù hợp và nhận được cổng thực hoặc kết nối tới listener đã biết.

### 6.4. `@LocalServerPort` có hoạt động với `MOCK` không?

Không có port listener của test `MOCK` để cung cấp. Trong `RANDOM_PORT`, Spring Boot tự cấp `local.server.port` khi web server start. Với `DEFINED_PORT`, `@LocalServerPort` cũng có thể lấy cổng thực sau khi server bind. Với `MOCK`, không nên inject hoặc assert một port giả định như 8080 để “xác nhận chạy”. Nếu đơn thuần thấy `server.port=8080` trong `Environment`, đó chỉ là **cấu hình**, chưa chứng minh listener.

### 6.5. Vì sao `MOCK` không ngăn mọi truy cập mạng?

`MOCK` chỉ nói về **web server đầu vào**. Nó không thay thế outbound HTTP clients, JDBC, Kafka producers hay SMTP connections của ứng dụng. Một bean thực có thể gọi API ngoài, và một `@Scheduled` job có thể chạy khi context được nạp.

Nếu cần bảo đảm test không chạm production: dùng profile `test`, injection với fake/mock outbound ports, test database, sandbox credentials và chính sách chặn egress. Cố gắng “chữa” bằng cách chuyển từ `RANDOM_PORT` sang `MOCK` sẽ không chặn tất cả kết nối ngoài.

## 7. `MockMvc` kiểm được gì, và không kiểm được gì?

### 7.1. Các hành vi MVC thường kiểm được

- Request mapping: path, HTTP method, query parameter, path variable.
- Data binding, conversion và validation qua MVC infrastructure.
- HTTP status, response headers, body, JSON serialization được thực hiện trong context.
- Controller advice và exception handlers thuộc Spring MVC.
- Filters nếu cấu hình áp dụng; Spring Security filter chain trong phạm vi mock MVC test.
- Phối hợp controller với service/repository **nếu các bean đó là thực và được nạp vào context**.

Ví dụ assertion:

```java
mvc.perform(get("/api/greet/Mai"))
        .andExpect(status().isOk())
        .andExpect(content().string("Xin chào, Mai!"));
```

Đây là đoạn đặt trong test có `MockMvc mvc`; không phải một chương trình Java độc lập.

### 7.2. Các đặc tính cần server thực hoặc môi trường rộng hơn

- Có socket đang `listen()` và có thể kết nối từ một client TCP.
- Cấu hình Tomcat/Jetty/Undertow connector, TLS/SSL handshake, HTTP protocol behavior.
- Network latency, client/server timeout, connection pooling, port binding.
- Compression/proxy/ingress/load-balancing behavior và header thực do hạ tầng thêm vào.
- Một số cơ chế error-page/dispatch do servlet container cung cấp (không chỉ handler exception ở MVC).
- Session cookie/redirect/forward theo hành vi container thực trong những trường hợp MockMvc mô phỏng khác.
- Behavior phụ thuộc client/server transactions chạy ở thread/process khác.

Ngay cả `RANDOM_PORT` vẫn **chưa kiểm được toàn bộ đường production** nếu ứng dụng test không đi qua proxy, ingress, CDN, firewall, TLS termination hoặc các dependent services tương ứng. Chọn test level theo phạm vi bảo vệ cụ thể.

## 8. `@WebMvcTest`, `@AutoConfigureMockMvc` và Mockito khác nhau ở đâu?

| Công cụ/annotation | Phạm vi tác dụng | Có mở port không? |
| --- | --- | --- |
| `@WebMvcTest(Controller.class)` | Spring MVC slice test, auto-configure MockMvc; service thường cần Mockito bean | Không |
| `@SpringBootTest(MOCK)` | Context ứng dụng rộng với mock web environment | Không |
| `@AutoConfigureMockMvc` | Bổ sung `MockMvc` để thao tác trong Servlet MVC test context tương thích | Không, bản thân nó không mở port |
| `@MockitoBean` | Thay/định nghĩa bean dependency dưới dạng Mockito mock | Không |
| `MockMvcBuilders.standaloneSetup(...)` | Tự xây MockMvc cho controller/handler, không cần full Spring context | Không |
| `@SpringBootTest(RANDOM_PORT)` | Context rộng với embedded HTTP server | Có |
| `@SpringBootTest(DEFINED_PORT)` | Context rộng với embedded HTTP server ở port cấu hình | Có |

Hai trường hợp thường bị lẫn:

**A.** `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` có thể nạp service thật, repository thật. Nó không phải “mock mọi thứ”; chỉ request/response Servlet được mô phỏng.

**B.** `@WebMvcTest` không tự tạo mọi service bean. Nếu controller cần service thì người viết thường thêm `@MockitoBean` hoặc `@Import` một dependency phù hợp. Nó tập trung vào controller slice và không cần server thật.

## 9. Chế độ `DEFINED_PORT` và rủi ro chạy song song

Nếu bắt buộc chạy một server trên port cấu hình, có thể dùng:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT,
    properties = "server.port=9095")
class FixedPortHttpTest {
    // Test thật cần một HTTP client và các assertions phù hợp.
}
```

Đoạn này là **mẫu annotation**, không phải test hoàn chỉnh. Chế độ `DEFINED_PORT` khởi động server thực và thường cố bind port `9095` ở ví dụ này. Nếu port bị tiến trình khác chiếm, test có thể fail. Hai test chạy song song trên cùng máy và cùng fixed port cũng dễ xung đột.

**Ưu tiên `RANDOM_PORT` cho đa số integration test HTTP:** Spring Boot/OS cấp port động và `@LocalServerPort` cung cấp port thực. Đừng gọi `Thread.sleep(...)` để đoán lúc nào server mở; `@SpringBootTest(RANDOM_PORT)` chờ Spring test context sẵn sàng trước khi thực thi test method trong quy trình chuẩn.

Với production, port thường được cấu hình rõ bởi deployment platform; đó là mục đích khác với test.

## 10. Đường chạy với WebFlux/reactive

Nếu classpath chỉ có Spring WebFlux, Spring Boot có thể xây **ReactiveWebApplicationContext** cho `MOCK`, và có thể dùng `WebTestClient` bind vào mock context/handler để kiểm thử mà không cần listener HTTP thật. Khi chọn `RANDOM_PORT`, ứng dụng reactive có embedded server chạy thật và có thể sử dụng HTTP client để gửi request tới port đó.

**Hai cách dùng `WebTestClient` khác nhau:**

- **Bind to application context/controller:** test client điều khiển request trong process, không nhất thiết mở network.
- **Bind to server URL:** test client gửi request qua HTTP tới endpoint thật.

Vì vậy sự xuất hiện của `WebTestClient` cũng không tự chứng minh server đang lắng nghe; cần xem nó được cấu hình/bind theo cách nào.

Nếu có cả Spring MVC và WebFlux trên classpath, Spring Boot thường ưu tiên Spring MVC; muốn kiểm tra ứng dụng reactive phải cấu hình `spring.main.web-application-type=reactive` đúng cách. Ví dụ chính của bài dùng Spring MVC, nên `MockMvc` và `@AutoConfigureMockMvc` là lựa chọn trực tiếp.

## 11. Transaction, rollback và dữ liệu test

Phân biệt `MOCK` và `RANDOM_PORT` cũng ảnh hưởng cách suy nghĩ về transaction test.

Spring Test có thể tự rollback transaction của test method có `@Transactional` theo cơ chế quản lý test. Nhưng:

- Trong `MOCK` dùng `MockMvc`, xử lý request diễn ra trong hạ tầng mock của test (có thể chia sẻ thread/transaction context theo cấu hình). Những thay đổi DB vẫn phải được hiểu theo cách transaction và bean được tạo.
- Trong `RANDOM_PORT`/`DEFINED_PORT`, HTTP client và embedded server chạy ở **các thread khác nhau**, nên một transaction mở ở test thread không tự bao trùm transaction trong server thread. Rollback của test method **không tự rollback** transaction mà server đã commit.
- Nếu dùng database thật/container, cần dữ liệu test, cleanup, transaction boundary và test fixture độc lập. Đừng dùng production database, đừng chỉ thêm `@Transactional` rồi kết luận an toàn.

Ví dụ một test HTTP thật gọi endpoint tạo đơn: response 201 không chứng minh dữ liệu sẽ tự được xóa sau test. Thiết kế cleanup tường minh, database test ephemeral hoặc trạng thái idempotent khi cần.

## 12. Cách chẩn đoán khi test hành xử “lạ”

| Hiện tượng | Khả năng phổ biến | Cách kiểm tra |
| --- | --- | --- |
| `MockMvc` trả 200 nhưng `curl` tới 8080 từ chối kết nối | Context `MOCK` không tạo listener | Xem `webEnvironment`; dùng `RANDOM_PORT` nếu cần HTTP thật |
| `@Autowired MockMvc` không tìm thấy bean trong `@SpringBootTest` | Chưa có `@AutoConfigureMockMvc` hoặc web stack không phù hợp | Thêm annotation đúng; phân biệt MVC với WebFlux |
| `@LocalServerPort` không giải quyết được trong test `MOCK` | Không có cổng thực | Chỉ dùng với server thực |
| Test `RANDOM_PORT` gọi port 8080 và bị lỗi | Cổng thật được cấp ngẫu nhiên | Dùng `@LocalServerPort` |
| Test `DEFINED_PORT` không khởi động | Port cố định đã chiếm | Đổi port hoặc ưu tiên `RANDOM_PORT` |
| `@WebMvcTest` báo thiếu service bean | Slice không nạp business service | Dùng `@MockitoBean`/`@Import` theo mục tiêu |
| Test `MOCK` vẫn gửi email/SQL | Outbound dependency vẫn là bean thật | Thay bằng fake/mock, cấu hình test resource và network policy |
| Test `RANDOM_PORT` để lại DB records dù `@Transactional` | Server transaction chạy riêng test thread | Cleanup/rollback tại server transaction hoặc DB test ephemeral |
| Test HTTP thật pass local, fail CI | Host/port/firewall/profile/timing khác | Kiểm tra cổng được cấp, loopback, readiness và tài nguyên test |
| Log thấy server initialized trong `mvn test` nhưng test MOCK không có cổng | Suite còn chạy test context khác (RANDOM_PORT) | Chạy tách class; đối chiếu annotation của class đang kiểm tra |

**Chiến lược debug:** Xác định **annotation và test class cụ thể**, kiểm tra test client đang gọi qua mock layer hay HTTP socket, sau đó xác nhận property runtime `local.server.port` chỉ ở nơi có server thật. Không đoán từ các dòng log chung của toàn bộ suite.

## 13. Các anti-pattern dễ làm test cho kết luận sai

### 13.1. “`@SpringBootTest` tức là server đã chạy”

Sai. Giá trị mặc định là `MOCK`. Muốn embedded server thật cần `RANDOM_PORT` hoặc `DEFINED_PORT`.

### 13.2. “Có `@AutoConfigureMockMvc` nghĩa là server đã mở”

Sai. Nó tạo/cấu hình `MockMvc`, không biến mock request thành socket.

### 13.3. “Mockito mock bean và `MOCK` là một”

Sai. `MOCK` nói về **web environment**, `@MockitoBean` nói về **bean dependency**. Bạn có thể có service thật trong MOCK; ngược lại có thể mock payment gateway ngay khi chạy HTTP server thật trên RANDOM_PORT.

### 13.4. “Trong `MOCK` có `server.port=8080` nên `curl` sẽ kết nối được”

Sai. `server.port` là một giá trị cấu hình, còn listener chỉ tồn tại nếu chế độ và runtime thực sự khởi động server. `local.server.port` đại diện cổng thực sau khi bind.

### 13.5. “MockMvc kiểm tra đủ mọi hành vi HTTP”

Không. Nó kiểm tra Spring MVC tương đối rộng nhưng không phải transport/container thật. Những trường hợp SSL/TLS, session/servlet container error pages, connector, network timeouts và proxy có thể đòi test HTTP thực.

### 13.6. “Cứ dùng `RANDOM_PORT` cho tất cả test sẽ chính xác hơn”

Không nhất thiết. Test logic thuần không cần Spring, MVC mapping thường kiểm bằng `MockMvc`, HTTP transport mới cần real listener. Tăng độ rộng context làm test tốn thời gian, phụ thuộc môi trường và khó chẩn đoán nếu không có mục tiêu rõ.

### 13.7. “Test `MOCK` chắc chắn không thể gây side effect ngoài ứng dụng”

Sai. Nó không ngăn HTTP outbound, DB writes, Kafka publish hay scheduler. Dùng credentials test-only, fake outbound adapters, container test và network constraints.

### 13.8. “Test `RANDOM_PORT` chắc chắn giống production”

Sai. Nó kiểm tra embedded server cùng JVM và HTTP endpoint, không tự thêm production load balancer, ingress, TLS termination, CDN, network ACL hay các service ngoài. Chọn E2E/staging khi cần.

## 14. Checklist trước khi review một bài test web

- [ ] Đã xác định mục tiêu: logic, MVC wiring hay HTTP listener/network thực.
- [ ] Nếu dùng `@SpringBootTest` không có tham số, biết rằng `webEnvironment = MOCK` theo mặc định.
- [ ] Với `MOCK` và Spring MVC, có `@AutoConfigureMockMvc` khi cần inject `MockMvc`.
- [ ] Không hiểu `MockMvc.perform(...)` là request đi qua TCP socket.
- [ ] Không inject `@LocalServerPort` trong test không có embedded listener.
- [ ] Nếu cần HTTP thật, dùng `RANDOM_PORT` và client gọi đúng port được cấp.
- [ ] Khi dùng `DEFINED_PORT`, đã cân nhắc xung đột cổng và parallel tests.
- [ ] Đã phân biệt `@WebMvcTest` (slice) với `@SpringBootTest(MOCK)` (context rộng).
- [ ] Đã xác minh những bean outbound nào là thật/mock, không nhầm `MOCK` với Mockito.
- [ ] Không dùng `@Transactional` của test thread như bảo đảm rollback dữ liệu từ HTTP server thread.
- [ ] Nếu cần container/network behavior, có test HTTP thực hoặc staging phù hợp.
- [ ] Test assertions đo hành vi đúng với cấp độ đã chọn, không kết luận quá phạm vi.

## 15. Tự kiểm tra

**Câu 1.** Vì sao `MockMvc` trả 200 trong `@SpringBootTest` nhưng trình duyệt không mở được `localhost:8080`?

**Đáp án:** `@SpringBootTest` mặc định là `MOCK`, Spring MVC xử lý request mock trong process và không bind HTTP port.

**Câu 2.** Muốn xác nhận Tomcat nhận request HTTP thật trên một cổng ngẫu nhiên, dùng annotation nào?

**Đáp án:** `@SpringBootTest(webEnvironment = RANDOM_PORT)`; lấy port thật bằng `@LocalServerPort` và gọi bằng HTTP client như `HttpClient`/`WebTestClient`/`TestRestTemplate` phù hợp.

**Câu 3.** Vì sao `@WebMvcTest` vẫn phù hợp khi không mở HTTP server?

**Đáp án:** Nó tập trung vào Spring MVC slice và dùng `MockMvc` để kiểm tra mapping/response/validation mà không cần container listener.

**Câu 4.** Có thể kiểm tra controller và service thật dưới `MOCK` không?

**Đáp án:** Có. `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` với service bean thật sẽ đi qua Spring MVC tới service thật; nó vẫn không kiểm tra HTTP socket.

**Câu 5.** Đặt `server.port=0` trong test `MOCK` có đảm bảo server lắng nghe không?

**Đáp án:** Không. `server.port=0` chỉ điều khiển port khi một embedded web server được khởi chạy; `MOCK` không làm việc đó.

**Câu 6.** Cách đơn giản nhất nhận biết HTTP request đang đi qua socket hay mock layer?

**Đáp án:** Xem **cách client được cấu hình**: `MockMvc.perform`/client bind-to-context xử lý nội bộ; `HttpClient` trỏ tới `http://127.0.0.1:<local.server.port>` của `RANDOM_PORT` thực hiện request qua TCP.

**Câu 7.** Test `@Transactional` gọi API thật trên `RANDOM_PORT`; test kết thúc rollback liệu có hoàn tác DB write trong server thread?

**Đáp án:** Không được mặc nhiên giả định. Transaction test thread khác transaction HTTP server thread; phải có cleanup/rollback ở transaction đúng nơi hoặc dùng DB cô lập.

**Câu 8.** Một `@SpringBootTest(MOCK)` có thể gọi Kafka production không?

**Đáp án:** Có nếu bean thực và credentials/config vẫn trỏ tới Kafka production. `MOCK` chỉ thay web server environment; phải tách outbound connections.

## 16. Tài liệu chính thức

- Spring Boot 3.5 – [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): mô tả rõ `MOCK` mặc định, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`; MockMvc và server thật.
- Spring Boot 3.5 – [`SpringBootTest.WebEnvironment` API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.WebEnvironment.html): ý nghĩa từng mode và context được tạo.
- Spring Framework 6.2 – [MockMvc Overview](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/overview.html): mock Servlet API, `DispatcherServlet` và test không cần running server.
- Spring Framework 6.2 – [MockMvc vs End-to-End Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/vs-end-to-end-integration-tests.html): giới hạn so với client/server thực.
- Spring Boot 3.5 – [Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): MVC slice, Spring Security test và các tuỳ chọn test.

**Một câu cần nhớ:** **“MOCK kiểm tra luồng web *bên trong ứng dụng*; RANDOM_PORT/DEFINED_PORT kiểm tra thêm đường HTTP *qua một server đang lắng nghe*.”** Vì thế test MockMvc pass không chứng minh Tomcat đã mở cổng, và việc mở cổng không tự chứng minh mọi phụ thuộc production được cô lập.