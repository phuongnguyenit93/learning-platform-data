# @AutoConfigureWebTestClient và điều kiện hỗ trợ của ứng dụng trong Spring Boot

## 1. Mục tiêu và vấn đề thực tế

Trong test Spring Boot, đôi khi bạn viết:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class GreetingTest {
    @Autowired WebTestClient client;
}
```

nhưng nhận lỗi kiểu `No qualifying bean of type 'WebTestClient'` hoặc `UnsatisfiedDependencyException`. Nguyên nhân không nhất thiết là thiếu một annotation: **WebTestClient được auto-configure khác nhau tùy loại ứng dụng (WebFlux/MVC), test web environment (mock/server thật) và dependency trên classpath**.

Bài này giúp bạn phân biệt bốn điều thường bị trộn lẫn:

1. **`WebTestClient` là API client kiểm thử**: nó có thể gửi request đến server HTTP thật hoặc đến hạ tầng xử lý request giả lập trong JVM; tên có chữ “Web” không có nghĩa ứng dụng phải chạy WebFlux server trong mọi chế độ.
2. **`@AutoConfigureWebTestClient` trong Spring Boot 3.5 dành cho mock binding tới ứng dụng WebFlux**: tạo client được nối trực tiếp tới Spring WebFlux `ApplicationContext` mà không cần mở HTTP port.
3. **Ứng dụng Spring MVC cũng có thể được kiểm bằng WebTestClient**, nhưng ở mock mode phải đi qua MockMvc integration, không suy luận rằng đặt riêng `@AutoConfigureWebTestClient` là đủ.
4. **`@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động server thật**: với các dependency phù hợp, `WebTestClient` có thể kết nối qua HTTP tới local server bằng relative URI; đây là phép kiểm khác mock binding.

Kết quả học tập:
- Nhận biết chính xác điều kiện khiến `@AutoConfigureWebTestClient` có tác dụng.
- Phân biệt `WebEnvironment.MOCK`, `RANDOM_PORT`, `DEFINED_PORT` và `NONE`.
- Lựa chọn `@WebFluxTest`, `@SpringBootTest + @AutoConfigureWebTestClient`, `@SpringBootTest(RANDOM_PORT)` hoặc `@AutoConfigureMockMvc` theo hệ thống đang kiểm.
- Tạo Maven project **Java 17+ / Spring Boot 3.5.16** có các bài test chạy được cho WebFlux mock, WebFlux slice, server HTTP thật và manual binding.
- Chẩn đoán vì sao client không được inject, request nhận 404/401, server không chạy hoặc test không kiểm được behavior thấp tầng của container.
- Tránh “đổi MVC thành reactive” chỉ để test dùng WebTestClient.

**Giới hạn phiên bản:** Import trong bài dùng **Spring Boot 3.5.x** và Spring Framework 6.2.x. Spring Boot 4.x đã tổ chức lại một số package/module test; phải tra tài liệu đúng version trước khi copy import từ bài 3.5.

## 2. Hai chế độ thực thi của WebTestClient

### 2.1. Mock binding — không đi qua network socket

Luồng logic của một WebFlux mock test:

```text
JUnit @Test
    |
    v
WebTestClient
    |
    v
Mock HTTP request/response exchange (trong JVM)
    |
    v
Spring WebFlux WebHandler / WebFilter chain
    |
    v
@RestController hoặc RouterFunction
    |
    v
Service, Repository... nếu được đưa vào context test
```

Không có server đang listen trên `localhost:<port>`, nên không nên kiểm `@LocalServerPort` hoặc gọi cURL đến một port “ảo”. Mock test thường khởi động nhanh hơn vì không chạy embedded HTTP server; nó kiểm routing, binding, serialization, response status/body, WebFlux filters/handlers có mặt trong test context.

Nhưng mock binding **không** kiểm trực tiếp network stack, TLS handshake, connection pool của client thật, Netty/Tomcat container behavior, reverse proxy, network timeouts hay hành vi hạ tầng triển khai.

### 2.2. Real-server binding — request HTTP thật

Khi test dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot khởi động embedded server trên một port được cấp tự động:

```text
JUnit @Test
    |
    v
WebTestClient (real HTTP client)
    |
    v
http://localhost:<random-port>
    |
    v
Embedded server (Reactor Netty hoặc servlet container)
    |
    v
Web request pipeline của ứng dụng
    |
    v
Controller/Handler -> Services...
```

Chế độ này phù hợp khi cần quan sát hành vi ở ranh giới HTTP thật: server codec/content negotiation, filters, cookies, network-related behavior hoặc integration nhiều tầng. Nó vẫn chạy trong test JVM hoặc môi trường local tương ứng, nên không tự thay thế kiểm thử deployment qua load balancer, gateway, firewall, real TLS certificates và config production.

**Điểm quan trọng:** cùng API `client.get().uri(...).exchange()` nhưng mức độ bằng chứng khác nhau. Cách client được **bind** quyết định test có đi qua server thật hay không.

## 3. Chính xác `@AutoConfigureWebTestClient` làm gì?

Trong Spring Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;
```

Theo Javadoc Spring Boot 3.5, `@AutoConfigureWebTestClient` cho phép client được **bound trực tiếp vào application**, sử dụng mock requests/responses, **không dựa vào HTTP server**; **mock setup này chỉ được hỗ trợ với ứng dụng WebFlux** ở phiên bản đó.

Ví dụ chuẩn:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class FullReactiveContextTest {
    @Autowired WebTestClient client;
}
```

Để annotation có ý nghĩa:
- Test phải chạy với **Spring TestContext**, ví dụ `@SpringBootTest`. Đặt annotation trên test Mockito thuần Java không tạo Spring context.
- Trên test classpath có loại `WebTestClient` và các dependency cần thiết, đặc biệt **`spring-webflux`**. Dùng `spring-boot-starter-webflux` là cách đơn giản để có reactive application và client.
- Ứng dụng được Boot phát hiện/configure ở **reactive web application type**, có Spring WebFlux handler infrastructure để client bind vào.
- Với test mock, không cần embedded server được bật, không bắt buộc Reactor Netty port đang listen.
- Nếu target handler có collaborator bị thiếu, context vẫn có thể fail dù WebTestClient auto-configure đúng; phải xử lý dependency của controller/service.
- Các bean điều kiện, profile, security configuration và auto-configurations vẫn quyết định endpoint có tồn tại và response ra sao.

### 3.1. Annotation không phải “bật WebFlux server”

Chỉ thêm `@AutoConfigureWebTestClient` vào test của project Spring MVC **không đổi MVC thành WebFlux**. Thêm thư viện `spring-webflux` vào classpath cũng **không bắt buộc** Boot chuyển sang reactive web type nếu Spring MVC vẫn có mặt. Spring Boot ưu tiên MVC khi cả hai stack được tìm thấy.

Với Boot 3.5, nếu bạn muốn test reactive application khi cả MVC và WebFlux libraries cùng có mặt, có thể cấu hình tường minh:

```java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
@AutoConfigureWebTestClient
class ExplicitReactiveTest {
    // ...
}
```

Đây là **mẫu minh họa** cho project thật có cấu hình WebFlux đầy đủ; không tự động khiến bất kỳ MVC controller nào hoạt động như WebFlux endpoint. Nếu ứng dụng vốn là MVC, không nên đổi web application type chỉ vì muốn dùng một test client.

### 3.2. Thuộc tính timeout

`@AutoConfigureWebTestClient` trong Boot 3.5 có thuộc tính `timeout` để đặt client timeout:

```java
@SpringBootTest
@AutoConfigureWebTestClient(timeout = "PT5S")
class ReactiveTimeoutTest {
    @Autowired WebTestClient client;
}
```

Giá trị như `PT5S` là ISO-8601 Duration hợp lệ. Annotation ánh xạ cấu hình dưới prefix `spring.test.webtestclient`; có thể đặt property tương ứng theo tài liệu/version:

```properties
spring.test.webtestclient.timeout=5s
```

Đây là thời gian chờ ở phía client/test exchange, **không phải** chỉ số xác minh latency production hay lệnh tăng server timeout. Đừng tăng timeout bừa bãi để che deadlock, blocked event-loop, request không bao giờ hoàn tất hoặc thiếu mock response.

## 4. Điều kiện hỗ trợ: ma trận chọn công cụ

| Kiểu ứng dụng | Test configuration | `WebTestClient` nên lấy từ đâu? | HTTP server thật? | Ý nghĩa |
| --- | --- | --- | --- | --- |
| WebFlux, chỉ `spring-boot-starter-webflux` | `@WebFluxTest(Controller.class)` | Slice tự cấu hình `WebTestClient` | Không | WebFlux controller/filter slice |
| WebFlux | `@SpringBootTest` + `@AutoConfigureWebTestClient` | Spring Boot bind tới reactive ApplicationContext | Không | Full reactive context, mock request |
| WebFlux | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Boot hỗ trợ inject client cho running server khi có spring-webflux | Có | HTTP end-to-end trong app test |
| Spring MVC | `@WebMvcTest` hoặc `@SpringBootTest` + `@AutoConfigureMockMvc` | `MockMvc`; có thể dùng WebTestClient được nối vào MockMvc nếu `spring-webflux` có mặt | Không | MVC handler/filter layer |
| Spring MVC | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | `TestRestTemplate` hoặc `WebTestClient` khi đủ client dependency | Có | HTTP thật qua servlet container |
| Non-web app | `@SpringBootTest(webEnvironment=NONE)` | Không tự có web server/binding của web application | Không | Unit/config/service, không endpoint HTTP |
| WebFlux controller không cần cả Boot context | `WebTestClient.bindToController(controller)` | Tạo client thủ công | Không | Setup nhẹ, scope chỉ controller/config đưa vào |
| HTTP service bên ngoài đã chạy | `WebTestClient.bindToServer().baseUrl(...)` | Client tự tạo và kết nối URL rõ ràng | Có (bên ngoài) | Contract smoke/API test |

**Không nhầm:** `@WebFluxTest` đã gồm WebTestClient auto-configuration phù hợp với slice; không phải lúc nào cũng cần ghi lại `@AutoConfigureWebTestClient`. Nếu cần chỉnh timeout, có thể dùng annotation đó trên slice tùy cấu hình đang hỗ trợ.

### 4.1. `WebEnvironment` của `@SpringBootTest`

| Giá trị | Điều Spring Boot làm | Hệ quả với client |
| --- | --- | --- |
| `MOCK` (mặc định) | Dựng mock servlet web context nếu có servlet; reactive web context nếu chỉ có WebFlux; non-web context nếu không có web stack | WebFlux mock client cần đúng auto-config; MVC dùng MockMvc integration |
| `RANDOM_PORT` | Khởi động embedded web server và đặt `server.port=0` để chọn port có sẵn | HTTP thật; `@LocalServerPort` có giá trị khi server chạy |
| `DEFINED_PORT` | Khởi động server, không đặt `server.port=0` | Có nguy cơ port cố định bị chiếm; không khuyến nghị cho test chạy song song |
| `NONE` | Không tạo web application context | Không mong đợi bean WebTestClient cho endpoint web |

Trong `RANDOM_PORT`, **không hard-code 8080** vì port sẽ được chọn ngẫu nhiên. Client Boot inject thường được cấu hình để relative paths trỏ đến server đã mở; nếu tự tạo client bằng `bindToServer()`, hãy dùng `@LocalServerPort` để xây base URL.

### 4.2. Khi dự án có cả spring-webmvc và spring-webflux

`spring-boot-starter-web` làm MVC/servlet được phát hiện. `spring-boot-starter-webflux` cung cấp WebFlux và WebTestClient trên classpath. Nếu **cả hai** cùng có, Boot thường chọn **Spring MVC** cho server app. WebTestClient là thư viện client và test API; sự hiện diện của nó không chứng minh reactive server.

Ví dụ dự án MVC thêm `spring-webflux` để dùng `WebClient` thì:
- Ứng dụng production vẫn có thể là MVC.
- `@SpringBootTest` mặc định tạo mock servlet context.
- `@AutoConfigureWebTestClient` một mình **không phải giải pháp** autowire mock WebTestClient theo đường WebFlux reactive app.
- Hãy dùng `@AutoConfigureMockMvc`, rồi `MockMvc` hoặc WebTestClient backed by MockMvc theo hướng dẫn Spring Boot; hoặc chạy server thật với `RANDOM_PORT`.

Không đưa hai starter production vào mọi app để “chắc chắn có test client”: việc thêm starter có thể kéo theo auto-configuration và behavior không mong muốn. Cân nhắc dependency scope trong dự án thực tế.

## 5. WebFlux: `@WebFluxTest` khác `@SpringBootTest + @AutoConfigureWebTestClient`

### 5.1. `@WebFluxTest` là web slice

```java
@WebFluxTest(controllers = GreetingController.class)
class GreetingControllerSliceTest {
    @Autowired WebTestClient client;
    @MockitoBean GreetingService service;
}
```

Spring Boot tập trung vào WebFlux components: controller, exception handler, message codecs, WebFlux configuration liên quan. Không tự scan mọi `@Service`, `@Repository` hay toàn ứng dụng. Vì thế, nếu controller cần `GreetingService`, hãy sử dụng `@MockitoBean` hoặc `@Import` bean cần test. Nếu không cung cấp collaborator, lỗi `UnsatisfiedDependencyException` là lỗi setup slice, không phải “client không hỗ trợ WebFlux”.

**Cần tách trách nhiệm:** WebFlux slice kiểm route/request/response/filter/serialization mà không cần full service/database. Nếu logic service quan trọng, kiểm bằng unit test và integration test riêng.

### 5.2. `@SpringBootTest + @AutoConfigureWebTestClient` tải full context

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class GreetingFullContextTest {
    @Autowired WebTestClient client;
}
```

Full context tải `@SpringBootApplication` và các bean production (trừ override/test profile). Nó có thể kéo theo database, messaging, configs, scheduled tasks tùy app. Client vẫn **mock-bound** tới WebFlux application và không mở HTTP port. Đừng kết luận vì “full context” nên đây là test network thật.

Nếu cần kiểm behavior thuộc embedded server, dùng `RANDOM_PORT`, không dựa vào `MOCK`.

### 5.3. `WebTestClient` không tự làm business method reactive

Giả sử controller trả `Mono<GreetingView>` thì WebFlux xử lý publisher; controller trả một object thường thì WebFlux cũng có cơ chế chuyển thành response. Việc test dùng WebTestClient **không xác nhận** domain layer đang non-blocking. Service gọi JDBC blocking trên event loop có thể vẫn cho kết quả đúng trong test, nhưng gây vấn đề hiệu năng khi tải cao. Kiểm vấn đề đó bằng thiết kế phù hợp, metrics/load test và event-loop blocking detection khi có yêu cầu.

## 6. Maven project hoàn chỉnh: WebFlux mock và HTTP thật

Project này **chỉ dùng Spring WebFlux starter**, nên không bị MVC giành ưu tiên web application type. Tất cả lớp test mặc định đều hướng tới PASS. Chúng chạy cùng endpoint nhưng kiểm các tầng khác nhau.

### 6.1. Cấu trúc file

```text
webtestclient-lab/
├── pom.xml
├── src/main/java/com/example/webtestlab/
│   ├── WebTestClientLabApplication.java
│   ├── GreetingView.java
│   ├── GreetingService.java
│   └── GreetingController.java
└── src/test/java/com/example/webtestlab/
    ├── GreetingWebFluxSliceTest.java
    ├── GreetingMockContextTest.java
    ├── GreetingRandomPortTest.java
    └── GreetingStandaloneClientTest.java
```

Mỗi file Java có `package com.example.webtestlab;`. Maven dùng mặc định `src/main/java` và `src/test/java`. Các class test kết thúc `Test` nên được Surefire phát hiện.

### 6.2. `pom.xml`

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
  <artifactId>webtestclient-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
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

Vì `spring-boot-starter-webflux` chứa `spring-webflux` và reactive runtime, cả server WebFlux và lớp `WebTestClient` có mặt. `spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito, Spring Test và test auto-configuration tương ứng.

**Không thêm `spring-boot-starter-web` vào project này** nếu muốn giữ rõ một web application type reactive. Nếu cần thử hai starter cùng lúc, làm bài tập riêng với `spring.main.web-application-type=reactive` và kiểm context thực tế, tránh “gói chung” rồi tin loại server theo tên dependency.

### 6.3. Main application

`src/main/java/com/example/webtestlab/WebTestClientLabApplication.java`:

```java
package com.example.webtestlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebTestClientLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebTestClientLabApplication.class, args);
    }
}
```

### 6.4. Response record

`src/main/java/com/example/webtestlab/GreetingView.java`:

```java
package com.example.webtestlab;

public record GreetingView(String message, String source) {}
```

Java record được Spring JSON codec serialize thành object gồm `message` và `source`.

### 6.5. Service thật

`src/main/java/com/example/webtestlab/GreetingService.java`:

```java
package com.example.webtestlab;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public GreetingView greet(String name) {
        return new GreetingView("Chào " + name, "service");
    }
}
```

Logic có chủ đích đơn giản để phân biệt test có dùng **service thật** hay đã mock collaborator. Không cần database hay external API.

### 6.6. Controller WebFlux

`src/main/java/com/example/webtestlab/GreetingController.java`:

```java
package com.example.webtestlab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/greetings")
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    public Mono<GreetingView> greet(@PathVariable String name) {
        return Mono.fromSupplier(() -> greetingService.greet(name));
    }
}
```

Khi request `GET /greetings/An`, body từ service thật sẽ tương ứng JSON:

```json
{"message":"Chào An","source":"service"}
```

Serialization có thể thay đổi thứ tự các property trong JSON. Do đó test ở phần sau kiểm các field bằng `jsonPath` thay vì so raw string chứa JSON theo thứ tự cố định.

### 6.7. Test #1: WebFlux controller slice

`src/test/java/com/example/webtestlab/GreetingWebFluxSliceTest.java`:

```java
package com.example.webtestlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(controllers = GreetingController.class)
class GreetingWebFluxSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    GreetingService greetingService;

    @Test
    void testsControllerWithMockedCollaborator() {
        when(greetingService.greet("An"))
                .thenReturn(new GreetingView("Giả lập An", "mock"));

        client.get()
                .uri("/greetings/An")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Giả lập An")
                .jsonPath("$.source").isEqualTo("mock");

        verify(greetingService).greet("An");
    }
}
```

Ở slice này, controller thật và Spring WebFlux handler infrastructure chạy; `GreetingService` được cung cấp bằng mock bean. Điều test chứng minh:
- Path variable `An` được bind đúng.
- Controller gọi service với tham số đúng.
- Response JSON có các field đúng.
- Request **không** đi qua embedded HTTP server.

Nó **không** chứng minh code `GreetingService.greet` thật trả đúng message vì service đã bị mock. Việc `@WebFluxTest` tự cấu hình WebTestClient là một trong những khác biệt với `@SpringBootTest` mặc định.

### 6.8. Test #2: Full reactive context nhưng vẫn mock HTTP

`src/test/java/com/example/webtestlab/GreetingMockContextTest.java`:

```java
package com.example.webtestlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient(timeout = "PT5S")
class GreetingMockContextTest {

    @Autowired
    WebTestClient client;

    @Test
    void sendsMockRequestToRealSpringComponents() {
        client.get()
                .uri("/greetings/An")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Chào An")
                .jsonPath("$.source").isEqualTo("service");
    }

    @Test
    void unknownPathReturns404() {
        client.get()
                .uri("/does-not-exist")
                .exchange()
                .expectStatus().isNotFound();
    }
}
```

`@SpringBootTest(MOCK)` tạo reactive ApplicationContext có controller/service thật. `@AutoConfigureWebTestClient` đăng ký client gắn với context WebFlux. Hai test kiểm response mà **không cần chạy server trên port thực**. Không sử dụng `@LocalServerPort` trong lớp này.

### 6.9. Test #3: Server thật trên random port

`src/test/java/com/example/webtestlab/GreetingRandomPortTest.java`:

```java
package com.example.webtestlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingRandomPortTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient client;

    @Test
    void usesRealHttpServer() {
        assertThat(port).isPositive();

        client.get()
                .uri("/greetings/An")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Chào An")
                .jsonPath("$.source").isEqualTo("service");
    }
}
```

Với `spring-webflux` sẵn trên classpath, Spring Boot 3.5 hỗ trợ auto-configure WebTestClient hướng tới running server khi dùng `RANDOM_PORT`. Client Boot inject có thể dùng relative URI; bạn không cần cố định `http://localhost:8080`.

Đối với app chỉ dùng servlet và không có WebFlux client classpath, có thể dùng `TestRestTemplate`. Điều quan trọng không phải “reactive hay servlet” khi **request thực là HTTP**; lựa chọn client phụ thuộc thư viện test và cơ chế auto-configuration có mặt.

**Khác biệt transaction:** khi client gọi server qua HTTP thật, xử lý request thường nằm ở thread/reactive pipeline phía server tách với test method. `@Transactional` trên test method không tự bảo đảm transaction của server-side request sẽ rollback cùng test. Cần cleanup/fixture/database isolation thích hợp nếu test ghi dữ liệu.

### 6.10. Test #4: Manual WebTestClient binding không cần Spring TestContext

`src/test/java/com/example/webtestlab/GreetingStandaloneClientTest.java`:

```java
package com.example.webtestlab;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class GreetingStandaloneClientTest {

    @Test
    void bindsToControllerWithoutBootContext() {
        GreetingController controller =
                new GreetingController(new GreetingService());

        WebTestClient client = WebTestClient
                .bindToController(controller)
                .build();

        client.get()
                .uri("/greetings/An")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Chào An");
    }
}
```

`bindToController` tạo setup tương ứng WebFlux handler layer dựa trên controller đã cung cấp, không scan toàn application. Đây là test nhẹ khi không cần Boot configuration, security/custom filters của app. Nếu app phụ thuộc config WebFlux riêng, standalone test có thể không đại diện đầy đủ; dùng `@WebFluxTest`/full context để kiểm những khác biệt đó.

### 6.11. Chạy và kết quả mong đợi

Tại thư mục `webtestclient-lab`:

```bash
mvn -q clean test
mvn -q -Dtest=GreetingWebFluxSliceTest test
mvn -q -Dtest=GreetingMockContextTest test
mvn -q -Dtest=GreetingRandomPortTest test
mvn -q -Dtest=GreetingStandaloneClientTest test
```

Bốn lớp được thiết kế PASS trên Java 17+ với dependency/version đã chọn. Khi thành công, Maven trả exit code `0`; không cam kết stdout/log cố định vì thời gian khởi động, port ngẫu nhiên và test logging thay đổi theo môi trường.

| Test | Spring context | Client binding | Server thật? | Giá trị chính |
| --- | --- | --- | --- | --- |
| `GreetingWebFluxSliceTest` | WebFlux slice | Mock WebFlux exchange | Không | `message="Giả lập An"` |
| `GreetingMockContextTest` | Full reactive app | Mock WebFlux exchange | Không | `message="Chào An"` |
| `GreetingRandomPortTest` | Full reactive app | HTTP tới random port | Có | `message="Chào An"` |
| `GreetingStandaloneClientTest` | Không Boot context | WebFlux controller standalone | Không | `message="Chào An"` |

Bạn cũng có thể chạy app thật:

```bash
mvn spring-boot:run
```

Và từ terminal khác:

```bash
curl "http://localhost:8080/greetings/An"
```

Nếu không có config ngoài can thiệp, response JSON biểu thị `message="Chào An"` và `source="service"`. Đây là kiểm chạy app, không phải một trong các mock tests.

## 7. Nếu ứng dụng dùng Spring MVC thì sao?

### 7.1. Sự phân biệt gây nhầm nhiều nhất

Spring Boot 3.5 Javadoc của `@AutoConfigureWebTestClient` nói rằng mock-bound WebTestClient được hỗ trợ cho **WebFlux applications**. Nhưng Spring Framework `WebTestClient` có thể kiểm **Spring MVC** bằng cách nối vào `MockMvc`.

Vì thế hai phát biểu sau **cùng đúng**:
- “`@AutoConfigureWebTestClient` đơn lẻ không phải cách bật mock WebTestClient cho một servlet MVC application ở Boot 3.5.”
- “Có thể dùng WebTestClient để kiểm Spring MVC mà không khởi động HTTP server, thông qua `MockMvcWebTestClient`/`@AutoConfigureMockMvc`.”

Nếu ứng dụng MVC, lựa chọn dễ nhất là `@WebMvcTest` hoặc `@SpringBootTest + @AutoConfigureMockMvc`, sau đó inject `MockMvc` để kiểm:

```java
@SpringBootTest
@AutoConfigureMockMvc
class MvcTest {
    @Autowired MockMvc mvc;
}
```

Các đoạn trong mục này là **mẫu tích hợp**, không được thêm nguyên xi vào project WebFlux ở mục 6 vì cần MVC dependency/controller khác.

### 7.2. Dùng WebTestClient trực tiếp qua MockMvc

Spring Framework 6.2 cung cấp:

```java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
```

Trong test MVC có `WebApplicationContext`:

```java
@Autowired
WebApplicationContext context;

WebTestClient client;

@BeforeEach
void setup() {
    client = MockMvcWebTestClient
            .bindToApplicationContext(context)
            .build();
}
```

Đây là **đoạn minh họa nằm trong class test MVC**; cần imports `@Autowired`, `@BeforeEach`, `WebApplicationContext` và `WebTestClient`, đồng thời test phải load MVC web context. Lời gọi `client.get().uri(...).exchange()` sẽ được MockMvc xử lý **trong JVM**, không phải kết nối mạng.

Một lựa chọn khác là `MockMvcWebTestClient.bindToController(new SomeMvcController(...)).build()` khi muốn standalone MVC controller. Cả hai đều là **MockMvc-backed**, không phải WebFlux WebHandler binding.

### 7.3. Spring Boot hỗ trợ autowire WebTestClient qua @AutoConfigureMockMvc

Theo tài liệu Boot 3.5, khi có Spring WebFlux trên test classpath, `@AutoConfigureMockMvc` có thể cung cấp `WebTestClient` kết nối tới MockMvc cho ứng dụng MVC:

```java
@SpringBootTest
@AutoConfigureMockMvc
class MvcWebTestClientTest {
    @Autowired WebTestClient client;
    // ...
}
```

Điều kiện là các module cần thiết (đặc biệt `spring-webflux` để có WebTestClient/WebClient API) phải tồn tại; chỉ có `spring-boot-starter-web` và `spring-boot-starter-test` thì **không nên tự khẳng định** field WebTestClient chắc chắn có.

Nếu không muốn thêm WebFlux dependency chỉ để có test DSL, dùng `MockMvc` trực tiếp là đơn giản và đúng mục tiêu. Nếu bạn cần kiểm HTTP thật của MVC application, `RANDOM_PORT` kết hợp `TestRestTemplate` cũng phù hợp.

### 7.4. Maven dependency cho MVC mock WebTestClient

Một hướng phù hợp nếu thật sự muốn WebTestClient API trong dự án MVC:

```xml
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
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webflux</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Đây là đoạn **dependencies cho một Maven project MVC đã có Spring Boot parent/BOM**, không phải `pom.xml` độc lập. `spring-webflux` trong test scope cung cấp API client, không có nghĩa production chuyển thành WebFlux. Đôi khi cần client connector phù hợp theo cấu hình dependency thực tế; nếu auto-configuration không tạo client, dùng `MockMvc` hoặc manual MockMvcWebTestClient và kiểm dependency tree.

**Không** đặt đồng thời `@WebMvcTest` và `@WebFluxTest` lên cùng lớp để cố bật cả hai slice. Nếu phải kiểm giao điểm behavior, chọn một slice và import cấu hình cần thiết, hoặc full integration test với app type cụ thể.

## 8. Các cách bind thủ công trong Spring Framework

Các API có thể dùng trực tiếp, độc lập với việc Boot tạo bean `WebTestClient`:

| API | Server setup | Ứng dụng |
| --- | --- | --- |
| `WebTestClient.bindToController(controller)` | WebFlux controller mock setup | WebFlux |
| `WebTestClient.bindToApplicationContext(context)` | WebFlux WebHandler từ context | WebFlux |
| `WebTestClient.bindToRouterFunction(route)` | WebFlux functional routing mock setup | WebFlux functional endpoints |
| `MockMvcWebTestClient.bindToController(controller)` | Standalone MockMvc request handling | Spring MVC |
| `MockMvcWebTestClient.bindToApplicationContext(webContext)` | MockMvc từ MVC WebApplicationContext | Spring MVC |
| `WebTestClient.bindToServer().baseUrl(url)` | HTTP client thật | WebFlux/MVC hay bất kỳ HTTP server |

Ví dụ explicit real server:

```java
// Minh họa: dùng trong test có @LocalServerPort int port
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:" + port)
        .build();
```

Nếu dùng Boot-injected WebTestClient trong `RANDOM_PORT`, thường không cần tự xây URL. Nhưng manual binding hữu ích để gọi **remote service**, server bên thứ ba hoặc test đang chạy ngoài Spring TestContext. Cẩn trọng việc phát HTTP tới môi trường thật: không gửi request ghi dữ liệu vào production khi chạy test tự động.

### 8.1. Tại sao không dùng `WebTestClient.bindToApplicationContext` cho MVC?

Đó là API binding qua WebFlux WebHandler. Với MVC, dùng `MockMvcWebTestClient.bindToApplicationContext(WebApplicationContext)`. Hai loại context có handler/filter pipelines khác nhau; chỉ vì cùng tên `ApplicationContext` không có nghĩa binding API dùng thay thế qua lại được.

### 8.2. WebTestClient interface không chứng minh HTTP được gửi thật

Một test có thể:

```java
client.get().uri("/greetings/An")
        .exchange()
        .expectStatus().isOk();
```

trông như “gửi HTTP”, nhưng `exchange()` trong mock binding xử lý request trực tiếp trong JVM. Nếu cần xác nhận port đang mở, dùng `RANDOM_PORT` và `@LocalServerPort`; nếu cần xác nhận contract qua network, dùng server-bound client. Cũng nên phân biệt WebTestClient vs WebClient: WebClient là runtime HTTP client API; WebTestClient thêm assertion DSL cho test.

## 9. Lỗi thường gặp: nhận diện theo triệu chứng

### 9.1. `No qualifying bean of type WebTestClient`

Nguyên nhân phổ biến:
- Dùng `@SpringBootTest` mặc định `MOCK` nhưng quên `@AutoConfigureWebTestClient` ở **ứng dụng WebFlux**.
- Dùng Spring MVC test mà chỉ thêm `@AutoConfigureWebTestClient`, không dùng `@AutoConfigureMockMvc` hoặc MockMvcWebTestClient.
- Thiếu `spring-webflux` trên test classpath.
- Test webEnvironment là `NONE`, không có web handler infrastructure.
- Cấu hình reactive bị MVC chiếm ưu tiên vì có hai web stacks, hoặc context không phải WebFlux.
- Annotation import từ phiên bản Spring Boot khác package/module.

Cách kiểm:
1. Mở `pom.xml`/dependency graph: có `spring-webflux` và các test modules không?
2. Xác định Spring web application type bằng dependencies và context runtime.
3. Xác định test đang `MOCK` hay `RANDOM_PORT`.
4. Với WebFlux mock, thêm đúng `@AutoConfigureWebTestClient` và kiểm `@SpringBootTest` hoặc `@WebFluxTest`.
5. Với MVC mock, dùng `@AutoConfigureMockMvc`/`MockMvc`, hoặc manual `MockMvcWebTestClient`.
6. Với real-server, bảo đảm server thực sự khởi động và client được cấu hình tới port đúng.

Đừng giải quyết bằng cách tạo bean WebTestClient giả không có server binding rồi chỉ assert client không null: bạn cần **một client có server setup đúng**.

### 9.2. `Failed to load ApplicationContext` trước khi test body chạy

Đây thường là lỗi Spring bean/config, không phải lỗi của HTTP request trong `WebTestClient.exchange()`. Xem chuỗi `Caused by`:
- Slice thiếu service vì component scan bị giới hạn → dùng `@MockitoBean` collaborator.
- Full context thiếu database/secret/config để tạo bean → test profile/Testcontainers/fake outbound infrastructure.
- Multiple beans ambiguous hoặc typo qualifier → sửa bean wiring.
- Framework không tìm được WebFlux/MVC classes phù hợp → sửa classpath.

Nếu Spring TestContext failure threshold báo skip repeated attempt, tìm **lần load context đầu tiên** fail trong process; đừng tăng threshold để che root cause.

### 9.3. WebTestClient inject được nhưng `404 Not Found`

Có client bean không đảm bảo route tồn tại:
- `@WebFluxTest` chỉ quét controller được chọn; functional `RouterFunction` có thể không được tự phát hiện trong slice.
- Controller nằm ngoài package scan hoặc chỉ được register theo profile khác.
- `@RequestMapping`/`@GetMapping` path khác với URI test.
- `@SpringBootTest` properties làm thay đổi context path/base path hoặc filters.

Kiểm endpoint mapping trong context, URI thực và slice scan; đừng vội đổi client binding khi lỗi là route.

### 9.4. Response `401 Unauthorized` hoặc `403 Forbidden`

Security đang bật và request test thiếu authentication/CSRF hoặc policy deny. Với WebFlux dùng Spring Security reactive test support (ví dụ `mockUser()` và `SecurityMockServerConfigurers` khi dependency phù hợp), hoặc sử dụng request với token/header hợp lệ theo contract. Không tắt tất cả security filters chỉ để assert 200 nếu mục tiêu test bao gồm security behavior.

WebFlux security và Servlet security dùng hai filter chains khác nhau; đừng dùng `MockMvc` security post processors cho WebFlux một cách máy móc.

### 9.5. Timeout khi `exchange()` hoặc expect body

Có thể do:
- Reactive publisher không kết thúc (`Flux.never()`, long-lived SSE).
- Code block event loop hoặc deadlock.
- Mock chưa stub đúng kiểu `Mono/Flux` (trả `null` hoặc không phát).
- HTTP server thật không chạy/khởi động chậm, network timeout.
- Client timeout quá thấp so với behavior hợp lệ.

Đừng coi việc tăng `@AutoConfigureWebTestClient(timeout = "...")` là sửa lỗi căn bản. Với streaming SSE, dùng `returnResult(...)` và `StepVerifier` để assert số event cần thiết thay vì chờ body vô hạn hoàn tất.

### 9.6. `Connection refused` trong mock test

Một mock-bound WebTestClient đúng nghĩa **không** gửi request đến localhost socket. Nếu thấy `Connection refused`, kiểm xem client đã bị tạo bằng `bindToServer()` hoặc base URL ngoài, trong khi không có server; hoặc một service/adapter bên dưới đang gọi external HTTP dependency. Tìm stack trace để xác định connection bị từ **client test** hay code ứng dụng.

### 9.7. Port random không trùng 8080

`RANDOM_PORT` sử dụng `server.port=0`. Nếu test tự tạo WebTestClient tới `localhost:8080`, nó có thể gọi nhầm một service khác hoặc bị từ chối. Dùng client Boot inject hoặc `@LocalServerPort` + base URL trong manual client.

### 9.8. HTTP test pass nhưng production vẫn lỗi container behavior

Mock WebFlux/MockMvc không đi qua embedded server/network. Nếu lỗi liên quan real compression, HTTP/2, TLS, reverse proxy headers, servlet error pages hoặc container-specific behavior, cần server-bound test và cấu hình môi trường tương ứng. Mock test vẫn hữu ích để xác nhận route/handler nhanh và cô lập.

### 9.9. Thêm WebFlux dependency nhưng ứng dụng vẫn MVC

Đây là behavior theo Spring Boot web application type selection, không phải bug. Khi MVC và WebFlux cùng xuất hiện, MVC thường được chọn. Xác nhận bằng web context/condition report; không suy luận từ việc class `WebTestClient` import thành công.

### 9.10. Test có `@AutoConfigureWebTestClient` nhưng chỉ là Mockito unit

`@AutoConfigureWebTestClient` do Spring Boot test auto-configuration xử lý. Một lớp chỉ có `@ExtendWith(MockitoExtension.class)` mà không có Spring TestContext sẽ không tự tạo Spring bean. Với test nhẹ muốn dùng WebTestClient, tạo thủ công bằng `bindToController`/`bindToApplicationContext` theo setup thực tế.

## 10. Phạm vi kiểm chứng: không đánh đồng Mock / Slice / Full / HTTP

| Phép kiểm | Kết luận có thể rút ra | Điều chưa được chứng minh |
| --- | --- | --- |
| WebFlux standalone binding | Route/controller với config mặc định và collaborator do test tạo | Auto-config/security/custom bean graph thực |
| `@WebFluxTest` | WebFlux handler, codecs, filters và controller trong slice | Service/DB của app không được import |
| Full context WebFlux + mock client | Controller/service/bean wiring thực trong ApplicationContext và WebFlux request pipeline | Embedded HTTP server/network/tầng triển khai |
| `RANDOM_PORT` + WebTestClient | Embedded HTTP server xử lý request end-to-end, app context | Gateway/ingress, production TLS/network policy và hạ tầng ngoài nếu đã mock |
| MVC `MockMvc`/`MockMvcWebTestClient` | MVC dispatcher, handlers, filters trong mock servlet environment | Servlet container internals và HTTP thật |
| Live remote `bindToServer` | Contract của endpoint đang phục vụ HTTP thật | Internal implementation, trừ khi có observability bổ sung |

**Lựa chọn theo rủi ro, không theo “annotation nhiều hơn”:**
- Chỉ kiểm logic service → JUnit/Mockito unit test.
- Kiểm reactive controller binding/JSON → `@WebFluxTest`.
- Kiểm Spring bean wiring và reactive handler chain → `@SpringBootTest(MOCK) + @AutoConfigureWebTestClient`.
- Kiểm HTTP server thật → `@SpringBootTest(RANDOM_PORT)`.
- Ứng dụng servlet MVC → ưu tiên `@AutoConfigureMockMvc`/`MockMvc`; dùng MockMvc-backed WebTestClient khi cần cùng DSL.
- Kiểm hệ thống deployed → HTTP test đến URL triển khai có phân quyền và dữ liệu kiểm thử riêng.

## 11. Khác biệt transaction, external services và trạng thái test

### 11.1. Transaction khi test gọi server thật

Với `@SpringBootTest(RANDOM_PORT)`, việc test method chạy trong một transaction **không** có nghĩa request qua HTTP trên server dùng transaction đó. Server-side work có thể chạy thread/pipeline khác và tự commit. Để làm integration test ổn định, dùng database container/schema test, cleanup theo ID do test tạo, rollback phù hợp hoặc cách isolate dữ liệu. Không giả định mỗi request tự rollback vì test có `@Transactional`.

### 11.2. Reactive stream không nhất thiết kết thúc

`WebTestClient.expectBody(...)` phù hợp response hữu hạn như JSON. Với SSE hoặc streaming Flux vô hạn, dùng API `returnResult` để lấy `Flux` và kiểm các event bằng reactor-test `StepVerifier` với `thenCancel`. `WebTestClient` không tự bảo đảm streaming test đã kiểm đúng backpressure hoặc shutdown; cần yêu cầu riêng nếu ứng dụng dựa vào chúng.

### 11.3. Mock downstream khác mock server

Ngay cả trong HTTP server-bound test, bạn có thể `@MockitoBean` external gateway để không gửi email/payment thật. Tuy nhiên test lúc ấy chứng minh request đi tới app server thật và business logic/handlers còn lại hoạt động, **không** chứng minh external gateway thực. Nếu integration thực tới adapter quan trọng, dùng WireMock/mock server/Testcontainers ở boundary network có kiểm soát.

### 11.4. Context cache và annotation khác nhau

Spring TestContext cache phân biệt nhiều cấu hình: active profiles, context customizers, bean overrides, properties, webEnvironment. Vì vậy `@WebFluxTest`, `@SpringBootTest(MOCK)` và `@SpringBootTest(RANDOM_PORT)` có thể load các context khác nhau; không đánh giá thời gian suite chỉ từ số test methods. Nhất quán cấu hình khi test có cùng mục tiêu nhưng không ép mọi test thành full context.

### 11.5. Web environment không quyết định security coverage tuyệt đối

Mock WebFlux client có thể chạy qua `WebFilter`/`SecurityWebFilterChain` nếu chúng nằm trong context. Nhưng slice có thể không import custom security bean của application theo mặc định; khi security là contract cần kiểm, import config cần thiết hoặc dùng full context. Real-server test cũng cần gửi auth credentials/CSRF phù hợp, không tự bỏ qua security.

## 12. Checklist chẩn đoán trước khi sửa test

- [ ] Ứng dụng là **WebFlux**, **MVC/Servlet** hay **non-web** theo runtime/config, không chỉ theo tên dependency?
- [ ] Có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` không? Nếu có, Boot đang chọn MVC hay reactive?
- [ ] Trên test classpath có `spring-webflux` và các thư viện client/codec cần dùng?
- [ ] Annotation `@AutoConfigureWebTestClient` import đúng package của Spring Boot đang sử dụng?
- [ ] Với WebFlux mock, đã dùng `@WebFluxTest` hoặc `@SpringBootTest + @AutoConfigureWebTestClient`?
- [ ] Với MVC mock, đã dùng `@AutoConfigureMockMvc`/`MockMvcWebTestClient` thay vì chỉ `@AutoConfigureWebTestClient`?
- [ ] `@SpringBootTest` đang `MOCK` hay `RANDOM_PORT`? Tôi có đang giả định có network server khi không có không?
- [ ] Khi dùng `RANDOM_PORT`, client có trỏ vào port thực (`@LocalServerPort` hoặc Boot-injected client) không?
- [ ] WebFlux slice có thiếu bean collaborator của controller không? `@MockitoBean` đã chọn đúng bean/type?
- [ ] Lỗi là context load, thiếu client bean, HTTP status assertion, exception nghiệp vụ hay connection timeout?
- [ ] Security filters/CSRF/token có được setup đúng theo contract?
- [ ] Streaming response có hoàn tất? Tôi có đang chờ vô hạn một Flux/SSE?
- [ ] Test có gọi external service hoặc tạo dữ liệu ngoài transaction rollback của test không?
- [ ] Nếu cần kiểm container/TLS/HTTP thật, đã chọn server-bound test thay vì mock binding?
- [ ] Có dùng đúng source/version tài liệu cho Spring Boot 3.5/4.x không?

**Kết luận:** Trong Spring Boot 3.5, `@AutoConfigureWebTestClient` là cách cấu hình **WebTestClient mock-bound cho WebFlux application**. Nó không biến một Spring MVC application thành reactive và không tự khởi động server. Với MVC mock, dùng `MockMvc`/`@AutoConfigureMockMvc` hoặc MockMvc-backed WebTestClient; với HTTP thật, dùng `@SpringBootTest(RANDOM_PORT)` và client có dependency/config phù hợp. Luôn xác định **app type × webEnvironment × binding** trước khi chọn annotation.

## 13. Câu hỏi ôn tập

1. Một project chỉ có `spring-boot-starter-web`, `@SpringBootTest` và `@AutoConfigureWebTestClient`. Vì sao `@Autowired WebTestClient` có thể fail? Nên dùng công cụ nào để kiểm controller servlet?
2. Project có cả MVC và WebFlux starters. Vì sao chỉ thêm `spring-webflux` không chắc Boot chạy reactive? Cấu hình nào có thể yêu cầu reactive khi project thật sự hỗ trợ?
3. `@WebFluxTest` có cần thêm `@AutoConfigureWebTestClient` để có client bean không? Nếu controller cần `GreetingService`, tại sao slice có thể không tìm thấy service?
4. Giữa `GreetingMockContextTest` và `GreetingRandomPortTest`, test nào mở HTTP port thật? Vì sao `@LocalServerPort` chỉ có ý nghĩa với running server?
5. Với Spring MVC nhưng muốn chung WebTestClient DSL, dùng `MockMvcWebTestClient.bindToApplicationContext` hay `WebTestClient.bindToApplicationContext`? Giải thích lý do.
6. Nếu mock WebFlux test trả HTTP 200, nó có chứng minh TLS, reverse proxy và container error page không? Tại sao?
7. Một WebFlux `Flux.never()` làm `expectBody` timeout. Đây có chắc là bug của `@AutoConfigureWebTestClient` không? Nên kiểm streaming response bằng công cụ gì?
8. `RANDOM_PORT` test dùng client thủ công hard-code `localhost:8080` và nhận connection refused. Sửa bằng cách nào?
9. Một test `@WebFluxTest` trả 401 thay vì 200. Khi nào nên bổ sung authentication test, khi nào nên sửa security config?
10. Làm sao phân biệt “WebTestClient có trên classpath” với “WebTestClient bean đã được Spring Boot auto-configure và bind đúng server setup”?

## 14. Nguồn chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications (mock environment, WebFlux, random port): https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5.16 Javadoc — `@AutoConfigureWebTestClient` (WebFlux mock binding, timeout): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/AutoConfigureWebTestClient.html
- Spring Boot 3.5.16 Javadoc — `@WebFluxTest`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html
- Spring Boot 3.5.16 Javadoc — `SpringBootTest.WebEnvironment`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.WebEnvironment.html
- Spring Framework 6.2 — WebTestClient setup (WebFlux, MockMvc, live server): https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
- Spring Framework 6.2 — MockMvc setup options: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html
- Spring Boot team explanation of MVC vs WebFlux mock WebTestClient selection: https://github.com/spring-projects/spring-boot/issues/40622
