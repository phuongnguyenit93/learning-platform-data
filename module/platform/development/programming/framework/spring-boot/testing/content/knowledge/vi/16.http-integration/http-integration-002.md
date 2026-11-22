# TestRestTemplate, WebTestClient và RestTestClient theo dòng phiên bản Spring Boot

## 1. Tại sao cùng một bài HTTP integration test lại có nhiều client?

Khi kiểm thử một Spring Boot REST API, ta thường muốn **khởi động ứng dụng trên một cổng thật, gửi HTTP request và kiểm tra response từ phía người dùng**. Nhưng theo phiên bản Spring Boot và Spring Framework, API test client được cung cấp, package import và cơ chế auto-configuration khác nhau. Code test hợp lệ ở Spring Boot 3.5 có thể không biên dịch hoặc không inject được bean khi nâng lên Boot 4.

Ba cái tên cần phân biệt:

- **`TestRestTemplate`**: tiện ích test dựa trên `RestTemplate`, cung cấp lời gọi HTTP đồng bộ, trả `ResponseEntity` để kiểm tra status/body. Thường được dùng trong integration test Spring Boot 3.x; vẫn có thể dùng ở Boot 4 nếu cấu hình đúng module và annotation.
- **`WebTestClient`**: API test dạng fluent, có nguồn gốc từ Spring WebFlux nhưng **có thể test HTTP server thật và mock WebFlux context**; một số thiết lập còn hỗ trợ Spring MVC thông qua MockMvc. Thường dùng để assert `expectStatus`, `expectHeader` và `expectBody`.
- **`RestTestClient`**: API mới từ **Spring Framework 7 / Spring Boot 4**, bọc `RestClient`, dùng các expectation fluent tương tự WebTestClient nhưng hướng tới **HTTP client đồng bộ / Spring MVC**; hỗ trợ cả server thật lẫn các cách bind vào MockMvc không mở cổng.

Bài này giải quyết câu hỏi: **dùng client nào, thêm dependency gì, import ra sao, chọn cấu hình server nào và bằng chứng của test đến đâu**. Các ví dụ là Java 17+, nhưng **không trộn code của hai dòng phiên bản vào cùng một cấu hình build**.

> Phạm vi phiên bản: phần Boot 3 dùng Spring Boot **3.5.x / Spring Framework 6.x**; phần Boot 4 dùng **4.0.x / Spring Framework 7.x**. Tên module, package và hành vi chính được đối chiếu với tài liệu chính thức. Với dự án chạy dòng mới hơn, hãy kiểm tra đúng tài liệu của **phiên bản đang khóa trong build**, không đoán theo IDE autocomplete hay bài hướng dẫn của dòng cũ.

## 2. Đầu tiên phải chọn đúng kiểu @SpringBootTest

Không phải `@SpringBootTest` nào cũng có HTTP listener thật.

| `webEnvironment` | Context được nạp | Có embedded HTTP server thật? | Kiểu test client phù hợp |
|---|---|---|---|
| `MOCK` (mặc định) | Web context giả lập khi có web stack trên classpath | **Không** | `MockMvc` cho MVC, `WebTestClient` bind-to-context cho WebFlux, `RestTestClient` bind MockMvc ở Framework 7 |
| `RANDOM_PORT` | Web application context với server ở cổng ngẫu nhiên | **Có** | Cả ba client có thể gọi HTTP thật khi được cung cấp và cấu hình đúng phiên bản |
| `DEFINED_PORT` | Web context với server ở cổng đã cấu hình | **Có** | Client HTTP thật; chú ý cổng xung đột khi test song song |
| `NONE` | Context không có web environment | **Không** | Không phù hợp để tự động gọi HTTP endpoint của ứng dụng |

**Khuyến nghị khi mục tiêu là HTTP integration:** dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` để hệ điều hành chọn cổng còn trống, giảm xung đột giữa các máy và CI jobs. Các client được Boot cấu hình cho live server thường **tự giải quyết base URL**, nên request tới `"/api/ping"` không cần ghép `localhost:8080` bằng tay.

Nếu dùng `MOCK`, một response 200 vẫn có giá trị cho controller/binding/JSON/filter trong context đã nạp, nhưng **không chứng minh socket thật, TCP, container server, TLS hoặc proxy phía trước hoạt động**. Đổi `MOCK` thành `RANDOM_PORT` không chỉ là thay tốc độ: đó là thay **ranh giới kiểm chứng**.

Một chú ý về transaction: khi server thật xử lý request trên thread riêng, `@Transactional` đặt ở phương thức test **không tự rollback dữ liệu do HTTP server đã commit**. Test ghi dữ liệu phải có chiến lược fixture/cleanup độc lập.

## 3. Ma trận phiên bản và lựa chọn client

| Tiêu chí | Boot 3.5 / Framework 6.x | Boot 4.0 / Framework 7.x |
|---|---|---|
| `TestRestTemplate` | `org.springframework.boot.test.web.client.TestRestTemplate` | Chuyển sang `org.springframework.boot.resttestclient.TestRestTemplate` |
| Bật TestRestTemplate trong `@SpringBootTest(RANDOM_PORT)` | Được Boot cung cấp theo cấu hình test thông thường khi dependency phù hợp | Cần **`@AutoConfigureTestRestTemplate`** và module liên quan |
| `WebTestClient` | `org.springframework.test.web.reactive.server.WebTestClient`; cần `spring-webflux` trên classpath | **Vẫn cùng package Spring Test**, nhưng cần bật **`@AutoConfigureWebTestClient`** khi muốn inject qua Boot test context và có module test tương ứng |
| `RestTestClient` | **Chưa có** trong Spring Framework 6.x | `org.springframework.test.web.servlet.client.RestTestClient` |
| Bật RestTestClient trong Boot context | Không áp dụng | **`@AutoConfigureRestTestClient`** từ `org.springframework.boot.resttestclient.autoconfigure` |
| Server thật với URL tương đối | TestRestTemplate/WebTestClient khi Boot auto-config phù hợp | RestTestClient/WebTestClient/TestRestTemplate khi **đã** bật auto-config tương ứng |
| Mock Spring MVC | `MockMvc`, hoặc WebTestClient qua MockMvc bridge | `MockMvc`, thêm RestTestClient có chế độ bind MockMvc |
| Mock Spring WebFlux | WebTestClient | WebTestClient |
| API fluent built-in assertions | WebTestClient | WebTestClient **và** RestTestClient |

**Điểm chuyển đổi then chốt:** Spring Boot 4 chia các phần test/client thành module chuyên biệt; không thể mặc định `spring-boot-starter-test` một mình mang mọi công cụ hoặc bean giống Boot 3.5. Cần kiểm tra dependency tree và annotation auto-config.

Tránh một nhầm lẫn tên gọi: `RestClient` là HTTP client production đồng bộ, `RestTestClient` là **test facade** bọc `RestClient`; `RestTemplate` là HTTP client production cũ, `TestRestTemplate` là tiện ích test dựa trên nó. Không dùng `RestClient` trong code rồi kỳ vọng có sẵn `expectStatus()` — phương thức đó thuộc API kiểm thử.

## 4. Ví dụ ứng dụng chung cho hai dòng phiên bản

Để so sánh công bằng, cả ba test clients sẽ gọi **cùng một ứng dụng nhỏ**. Code production sau dùng các annotation HTTP/Web phổ biến trong cả Boot 3.5 và Boot 4.0; đặt trong một project có **một** phiên bản Boot nhất quán.

Ứng dụng có ba hành vi có thể kiểm chứng:
1. `GET /api/echo/Ada` trả `200 OK`, header `X-Echo: yes` và text `Hello, Ada`.
2. `GET /api/echo/missing` trả `404 Not Found` với body `ECHO_NOT_FOUND`. Mục tiêu là kiểm tra response lỗi, không giả định client sẽ throw.
3. `POST /api/echo` nhận JSON `{"name":"Neo"}`, trả `201 Created` và text `Created: Neo`.

Các endpoint cố ý **không ghi database** để tập trung vào lựa chọn client và HTTP boundary. Sau khi hiểu cơ chế, có thể bổ sung repository/transaction/security integration test.

### 4.1. Application class

Tệp `src/main/java/com/example/httpit/HttpItApplication.java`:

```java
package com.example.httpit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpItApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpItApplication.class, args);
    }
}
```

Tệp đặt ở package cha của controller để component scan nhận ra `@RestController`.

### 4.2. Request record

Tệp `src/main/java/com/example/httpit/EchoRequest.java`:

```java
package com.example.httpit;

public record EchoRequest(String name) {}
```

Record Java 17 có constructor và accessor `name()`. Trong một dự án Boot được cấu hình JSON converter/codec phù hợp (ví dụ Jackson), JSON object có trường `name` được deserialize thành record này.

### 4.3. REST controller

Tệp `src/main/java/com/example/httpit/EchoController.java`:

```java
package com.example.httpit;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/echo")
public class EchoController {

    @GetMapping("/{name}")
    public ResponseEntity<String> greet(
            @PathVariable("name") String name) {

        if ("missing".equals(name)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body("ECHO_NOT_FOUND");
        }

        return ResponseEntity.ok()
                .header("X-Echo", "yes")
                .body("Hello, " + name);
    }

    @PostMapping
    public ResponseEntity<String> create(
            @RequestBody EchoRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body("Created: " + request.name());
    }
}
```

Controller dùng response text để output có thể được so sánh **chính xác** mà không phụ thuộc thứ tự trường JSON. POST vẫn kiểm tra được quá trình JSON request-body deserialization qua record. Ứng dụng demo **không thêm Spring Security** để GET/POST có thể gọi không cần credential/CSRF; nếu dự án thật có security, phải cung cấp authentication/CSRF theo security rules của nó.

Không có stdout nghiệp vụ cố định trong controller. Các con số 200, 201, 404 và text body là **hợp đồng được assert trong test**, không phải một bản log ứng dụng.

## 5. Cấu hình và test trên Spring Boot 3.5: TestRestTemplate

### 5.1. Dependencies trên Boot 3.5

Ví dụ một dự án đã cấu hình Spring Boot 3.5.x plugin, Java 17, dependency management và Maven Central, phần dependencies Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây **không phải toàn bộ** `build.gradle`: Boot plugin/toolchain/repository phải được cấu hình trong dự án. Với Boot 3.5, `spring-boot-starter-test` cung cấp các thành phần JUnit/Boot test thông thường; `TestRestTemplate` thuộc `spring-boot-test` và thường sẵn sàng cho test `RANDOM_PORT` khi classpath tương thích.

### 5.2. TestRestTemplate: full Java/JUnit test

Tệp `src/test/java/com/example/httpit/Boot35TestRestTemplateTest.java`:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class Boot35TestRestTemplateTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void returns200WithBodyAndHeader() {
        ResponseEntity<String> response = rest.getForEntity(
                "/api/echo/Ada", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Hello, Ada", response.getBody());
        assertEquals(
                "yes", response.getHeaders().getFirst("X-Echo"));
    }

    @Test
    void returns404AsResponseInsteadOfThrowing() {
        ResponseEntity<String> response = rest.getForEntity(
                "/api/echo/missing", String.class);

        assertEquals(
                HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals("ECHO_NOT_FOUND", response.getBody());
    }

    @Test
    void postSerializesRequestAndReturns201() {
        ResponseEntity<String> response = rest.postForEntity(
                "/api/echo",
                new EchoRequest("Neo"),
                String.class);

        assertEquals(
                HttpStatus.CREATED, response.getStatusCode());
        assertEquals("Created: Neo", response.getBody());
    }
}
```

### 5.3. Vì sao test này có giá trị?

- `@SpringBootTest(RANDOM_PORT)` khởi động **embedded server thật**; `TestRestTemplate` do Boot cung cấp với root URL thích hợp có thể gọi đường dẫn tương đối, không cần hard-code `8080`.
- Client dựa trên `RestTemplate`, thực hiện request **đồng bộ**; test nhận `ResponseEntity<String>` gồm status, headers và body.
- **`TestRestTemplate` fault-tolerant theo nghĩa test-friendly** đối với 4xx/5xx: không mặc nhiên ném một response-status exception như `RestTemplate` thông thường ở đường xử lý mặc định; test kiểm tra response lỗi bằng `getStatusCode()`. Đừng nhầm điều này với khả năng bỏ qua lỗi mạng: connection refused, timeout hoặc serialization bug vẫn có thể khiến request thất bại.
- POST kiểm chứng JSON request được client serialize và server deserialize. Nếu hệ thống thực tế có authentication, filter, validation hay format JSON khác, phải bổ sung test phù hợp.
- Bài test không liên quan database hoặc asynchronous processing; response 201 ở đây chỉ có nghĩa code controller đã tạo response mong đợi.

**Một lựa chọn tự tạo client:** có thể khởi tạo `TestRestTemplate` thủ công hoặc dùng underlying `RestTemplate`, nhưng khi đó cần tự cấu hình base URL, authentication, interceptors... Nếu Boot có sẵn client cho `RANDOM_PORT`, inject trực tiếp thường đơn giản và ít lỗi hơn.

## 6. Spring Boot 3.5: WebTestClient cho server thật

`WebTestClient` là API test có kiểu viết fluent `client.get().uri(...).exchange().expectStatus()...`. Tuy xuất phát từ WebFlux, nó **không chỉ test reactive server**: có thể kết nối live HTTP server của một ứng dụng MVC khi có các dependency test thích hợp.

### 6.1. Dependency bổ sung

Nếu project Boot 3.5 ở mục 5 dùng MVC nhưng muốn chạy WebTestClient, bổ sung dependency test cho Spring WebFlux/client stack:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Chỉ thêm WebFlux ở test scope trong ví dụ MVC để sử dụng client; nếu project có cả MVC và WebFlux trên runtime classpath, Spring Boot thông thường ưu tiên **MVC** khi tự xác định loại web application. Một ứng dụng WebFlux thật thì dùng `spring-boot-starter-webflux` ở implementation, không cần thêm `starter-web` cho mục tiêu này.

### 6.2. WebTestClient trên Boot 3.5

Tệp `src/test/java/com/example/httpit/Boot35WebTestClientTest.java`:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class Boot35WebTestClientTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsLiveServerWithFluentAssertions() {
        client.get()
                .uri("/api/echo/Ada")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Echo", "yes")
                .expectBody(String.class).isEqualTo("Hello, Ada");
    }

    @Test
    void handles404AsTestExpectation() {
        client.get()
                .uri("/api/echo/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody(String.class).isEqualTo("ECHO_NOT_FOUND");
    }

    @Test
    void sendsJsonAndChecks201() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest("Neo"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(String.class).isEqualTo("Created: Neo");
    }
}
```

Đây là **một lựa chọn thay thế** cho lớp test TestRestTemplate, không cần chạy cả hai để chứng minh cùng một hợp đồng HTTP nếu không có mục đích so sánh. API assertions tương tự nhưng cơ chế client khác nhau:

- `exchange()` thực hiện request theo cấu hình của `WebTestClient`, sau đó `expectStatus`/`expectBody` xác minh response.
- `WebTestClient` không buộc controller phải trả `Mono` hoặc `Flux`; nó là test HTTP client, có thể gọi MVC server.
- Khi server cần phát nhiều phần tử (SSE/streaming) hoặc một response reactive, `WebTestClient` đặc biệt hữu ích vì có API tiêu thụ body stream và tích hợp Reactor Test.
- Boot 3.5 có cơ chế thuận tiện để autowire `WebTestClient` vào `@SpringBootTest(RANDOM_PORT)` khi `spring-webflux` nằm trên classpath. Trong mock WebFlux environment, có thể dùng `@AutoConfigureWebTestClient`; **đừng suy ra có live server chỉ vì inject được WebTestClient**.

Nếu không cần WebFlux/client stack chỉ để kiểm tra status/body trên MVC HTTP API, TestRestTemplate có ít dependency hơn trong một dự án Boot 3.5 thuần Servlet.

## 7. Spring Framework 7 / Boot 4: RestTestClient xuất hiện

`RestTestClient` được thêm vào **Spring Framework 7** như một test client dựa trên `RestClient`. Nó có API thực hiện request của `RestClient` tới `exchange()`, rồi cung cấp fluent assertions sau đó:

```java
client.get()
        .uri("/api/echo/Ada")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("Hello, Ada");
```

Đây là cú pháp minh họa bên trong test có `client`; lớp test hoàn chỉnh nằm ở mục 8.

**Hai chế độ quan trọng:**
- **HTTP server thật**: `RestTestClient.bindToServer().baseUrl("http://localhost:<port>").build()`, hoặc Boot auto-configure client cho `RANDOM_PORT`.
- **Mock Spring MVC**: `RestTestClient.bindToController(...)` hoặc `bindToApplicationContext(...)` sử dụng MockMvc hạ tầng bên dưới, **không cần mở TCP listener**.

`RestTestClient` không phải một cái tên thay thế đơn thuần cho `WebTestClient`. Điểm mạnh của nó là dùng phong cách **imperative `RestClient`** và hỗ trợ trực tiếp mock MVC trong Spring Framework 7. WebTestClient vẫn hữu ích và được hỗ trợ trong ứng dụng WebFlux/streaming và cả các trường hợp kiểm thử MVC khi đã cấu hình bridge thích hợp.

**Cảnh báo phiên bản:** `org.springframework.test.web.servlet.client.RestTestClient` **không tồn tại trong Framework 6.x**. Nếu IDE báo cannot resolve `RestTestClient` trong dự án Boot 3.x, đây là mismatch phiên bản chứ không phải do thiếu import bí ẩn trong `spring-boot-starter-test`. Đừng cố thêm tùy tiện `spring-test:7.x` vào một ứng dụng Spring Boot 3.x đang dùng Spring 6.x; làm như vậy phá vỡ BOM/dependency alignment.

## 8. Ví dụ Java 17+ đầy đủ: Boot 4.0 với @AutoConfigureRestTestClient

### 8.1. Module và dependency của Boot 4

Ở Spring Boot 4, nhiều web/test clients tách thành module. Ví dụ Gradle **cho project Boot 4.0.x** đã khai báo Spring Boot plugin, Java 17+, repositories và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-restclient'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-resttestclient'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Cặp `spring-boot-starter-restclient` (client đồng bộ) và `spring-boot-resttestclient` (hạ tầng test) được khai báo **tường minh** để không dựa vào các transitive dependencies tình cờ. Nếu project đang dùng starters/test modules khác tương đương theo BOM, có thể đã nhận những module đó gián tiếp; **kiểm tra dependency tree thay vì thêm trùng không cần thiết**.

Các artifact và cơ chế auto-config này áp dụng cho **Boot 4.x**, không copy nguyên vào Boot 3.5 (vốn dùng `spring-boot-starter-web`). `@SpringBootTest` cùng `@AutoConfigureRestTestClient` không làm mọi thứ tự xuất hiện nếu classpath thiếu module tương ứng.

### 8.2. RestTestClient trên HTTP server thật

Tệp `src/test/java/com/example/httpit/Boot40RestTestClientTest.java`:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureRestTestClient
class Boot40RestTestClientTest {

    @Autowired
    RestTestClient client;

    @Test
    void checksRealHttpSuccess() {
        client.get()
                .uri("/api/echo/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Echo", "yes")
                .expectBody(String.class).isEqualTo("Hello, Ada");
    }

    @Test
    void checksRealHttpNotFound() {
        client.get()
                .uri("/api/echo/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody(String.class).isEqualTo("ECHO_NOT_FOUND");
    }

    @Test
    void postsJsonThroughRealServer() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new EchoRequest("Neo"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(String.class).isEqualTo("Created: Neo");
    }
}
```

Điểm thay đổi so với Boot 3.5:
- Import **`RestTestClient` từ Spring Test MVC package** `org.springframework.test.web.servlet.client`, **không** phải `org.springframework.test.web.reactive.server`.
- `@AutoConfigureRestTestClient` từ Boot `org.springframework.boot.resttestclient.autoconfigure` là annotation dùng để tạo bean client trong test context.
- `@SpringBootTest(RANDOM_PORT)` bảo đảm gọi qua HTTP server thật. Client do Boot tạo hiểu base URL cổng được cấp; path tương đối dùng như trong ví dụ.
- Client có request body method `body(...)` theo phong cách `RestClient`, khác `bodyValue(...)` của `WebTestClient`.
- `expectStatus`, `expectHeader`, `expectBody` xác minh response. Đây là **test facade**; nếu dùng `RestClient` sản phẩm trực tiếp, nó không tự có chuỗi fluent expectations như vậy.

Lớp test trên dùng **tệp production cùng package** trong mục 4. Không cần viết service hoặc repository cho ví dụ này. Với dependencies/version đúng và web application khởi động được, ba test được thiết kế để đạt; phải chạy thực tế để có bằng chứng PASS.

### 8.3. RestTestClient với MockMvc mà không mở server

Trong Spring Framework 7, có thể kiểm tra controller MVC bằng `RestTestClient` mà không có listening socket:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.client.RestTestClient;

class RestTestClientMockControllerTest {

    private final RestTestClient client =
            RestTestClient.bindToController(new EchoController())
                    .build();

    @Test
    void mockMvcStyleRequestWithoutRealHttpPort() {
        client.get()
                .uri("/api/echo/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Hello, Ada");
    }
}
```

Đây là **lớp test đầy đủ**, nhưng chỉ kiểm tra controller thuần và cơ chế MVC mock setup của `bindToController`. Nó **không** chạy mọi bean/filter/security/advice mà ứng dụng thực có trừ khi cấu hình thêm đúng thành phần. Nếu muốn Spring MVC context của ứng dụng, có thể dùng `RestTestClient.bindToApplicationContext(WebApplicationContext)`; nếu muốn HTTP socket thật, dùng `bindToServer()` hoặc Boot auto-configure khi `RANDOM_PORT`.

**Đừng nói rằng cả ba cách bind đều là integration HTTP thật.** Tên client không quyết định mức độ integration; **cách bind và cấu hình server** mới quyết định.

## 9. Boot 4 vẫn dùng TestRestTemplate được, nhưng phải đổi package và bật bean

Một ứng dụng đang có nhiều test Boot 3.x dựa trên `TestRestTemplate` không nhất thiết phải chuyển tất cả sang `RestTestClient` ngay lập tức. Nhưng khi lên Boot 4:

1. Đổi import từ `org.springframework.boot.test.web.client.TestRestTemplate` sang `org.springframework.boot.resttestclient.TestRestTemplate`.
2. Bật auto-config bằng **`@AutoConfigureTestRestTemplate`** trong những `@SpringBootTest` cần inject nó.
3. Bảo đảm classpath chứa **`spring-boot-resttestclient`** và **`spring-boot-restclient`** / starter phù hợp.
4. Giữ `RANDOM_PORT` nếu test phải thực sự đi qua HTTP server.

Ví dụ lớp Boot 4.0 đầy đủ:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.resttestclient.TestRestTemplate;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureTestRestTemplate;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureTestRestTemplate
class Boot40LegacyTemplateTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void keepsStatusDrivenAssertions() {
        ResponseEntity<String> response =
                rest.getForEntity(
                        "/api/echo/missing", String.class);

        assertEquals(
                HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals("ECHO_NOT_FOUND", response.getBody());
    }
}
```

Đoạn này cần cùng Boot 4 dependencies ở mục 8 và code production mục 4. `TestRestTemplate` vẫn có đặc tính thuận tiện để kiểm tra HTTP 4xx/5xx qua `ResponseEntity` thay vì coi status lỗi là exception theo mặc định.

**Thay đổi chính là phân tách module và việc bật bean tường minh**, không phải việc API `getForEntity` đổi thành một tên hoàn toàn mới.

Nếu dự án Boot 4 cũng dùng `RestClient.Builder` trong mã production, thư viện `spring-boot-restclient` nên có mặt trên **main runtime classpath**; không chỉ thêm nó ở test scope rồi bất ngờ thấy bean được tạo trong test nhưng thiếu trong production.

## 10. WebTestClient trên Boot 4: vẫn có, nhưng phải auto-configure rõ

`WebTestClient` không bị thay thế hay xóa bởi `RestTestClient`. Nó tiếp tục phù hợp với:
- Spring WebFlux annotated controller và functional endpoints.
- Streaming responses, server-sent events (SSE), backpressure/cancellation trong trường hợp kiểm thử phù hợp.
- Live HTTP server của MVC hoặc WebFlux, khi HTTP client stack được thiết lập.
- Mock WebFlux context khi muốn test nhanh mà không mở server.

Điểm cần sửa từ nhiều ví dụ Boot 3.x: trong **Boot 4**, khi muốn **inject** `WebTestClient` vào một `@SpringBootTest`, hãy thêm **`@AutoConfigureWebTestClient`**, đồng thời đưa test module có annotation và dependencies WebFlux client phù hợp lên classpath.

Ví dụ import của **Boot 4.x**:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class Boot40WebTestClientTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsRunningHttpServer() {
        client.get()
                .uri("/api/echo/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Hello, Ada");
    }
}
```

Trong ứng dụng MVC Boot 4, phần dependencies test cần bao gồm **`spring-boot-webflux-test`** (cung cấp support/annotation) và WebFlux/client runtime như `spring-webflux` cùng Reactor Netty HTTP client hoặc starter phù hợp. Một cách rõ ràng cho dự án minh họa là thêm:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-webflux-test'
testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Giữ `implementation 'org.springframework.boot:spring-boot-starter-webmvc'` nếu đây là ứng dụng Servlet. Chỉ thêm WebFlux ở **test scope** để chạy client, không có nghĩa bạn phải chuyển toàn bộ server MVC sang WebFlux. Nếu ứng dụng thật là WebFlux, starter WebFlux thuộc implementation, và test module tương ứng là test dependency.

**Cần phân biệt package theo version:**
- Boot 3.5: `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`.
- Boot 4.0: `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient`.
- Cả hai dùng `org.springframework.test.web.reactive.server.WebTestClient` cho class test client.

Việc đổi annotation import nhưng vẫn dùng cùng tên `WebTestClient` là tình huống phổ biến khi IDE báo `cannot resolve symbol` sau migration.

## 11. Phân biệt mock test, server test và external-client test

**Trường hợp A: muốn kiểm tra HTTP contract ở controller mà không mở server.**

- Boot 3 MVC: `@WebMvcTest` + `MockMvc`; cũng có thể dùng WebTestClient gắn MockMvc nếu đã cấu hình bridge.
- Boot 3/4 WebFlux: `@WebFluxTest` + `WebTestClient` bind-to-context.
- Spring Framework 7 MVC: `RestTestClient.bindToController(...)` hoặc `bindToApplicationContext(...)`, hay `MockMvc` như trước.

Kết quả chứng minh mapping, converter, validation, JSON, controller advice, filter **được thực sự đăng ký vào test setup**. Không chứng minh TCP/embedded server hoặc toàn bộ security/proxy/config production.

**Trường hợp B: muốn kiểm tra end-to-end HTTP server của ứng dụng.**

- `@SpringBootTest(RANDOM_PORT)` + client test có base URL được gắn với cổng thực.
- Assert status, headers, content type, body và error schema; bổ sung authentication/CSRF/cookies khi API có security.
- Với service/repository thật, có thể test nhiều tầng; với bean mock, chỉ chứng minh các tầng **còn hoạt động thật** trong context.

Kết quả chứng minh HTTP request đi qua server thật; chưa tự chứng minh database production, load balancer, TLS terminate, external gateway hoặc cloud network.

**Trường hợp C: muốn test ứng dụng gọi một HTTP API bên ngoài.**

Dùng `@RestClientTest` + `MockRestServiceServer`, WebClient testing support, mock HTTP server hoặc contract test phù hợp. Đó là **client-side integration test của outbound HTTP**, khác với ba test clients đang dùng để **gọi endpoint của chính ứng dụng**. Không nhầm `@RestClientTest` (slice cho outbound RestClient) với `RestTestClient` (client để kiểm tra server endpoint).

## 12. So sánh API request và assertion

| Nhiệm vụ | TestRestTemplate | WebTestClient | RestTestClient |
|---|---|---|---|
| GET | `getForEntity(path, String.class)` | `get().uri(path).exchange()` | `get().uri(path).exchange()` |
| Kiểm tra status | `assertEquals(OK, response.getStatusCode())` | `expectStatus().isOk()` | `expectStatus().isOk()` |
| Kiểm tra body text | `assertEquals("...", response.getBody())` | `expectBody(String.class).isEqualTo("...")` | `expectBody(String.class).isEqualTo("...")` |
| Header | `response.getHeaders().getFirst(...)` | `expectHeader().valueEquals(...)` | `expectHeader().valueEquals(...)` |
| POST object | `postForEntity(path, body, String.class)` | `post().uri(...).bodyValue(body).exchange()` | `post().uri(...).body(body).exchange()` |
| 4xx/5xx | Lấy `ResponseEntity` để assert | Expectation theo status | Expectation theo status |
| Mock MVC không mở server | Không phải mục tiêu chính | Có thể thông qua MockMvc bridge | Có `bindToController` / `bindToApplicationContext` trên Framework 7 |
| Mock WebFlux không mở server | Không | **Có** | Không phải API chính cho mock reactive context |
| Streaming/reactive body assertions | Thủ công hơn | Mạnh, có thể tích hợp Reactor Test | Hướng tới request/response kiểu imperative |

Không nên nói một client “nhanh hơn” về tuyệt đối chỉ dựa trên tên: thời gian lớn thường đến từ **loại context**, có mở server thật không, dependency hạ tầng, database/test fixtures và số lượng context cache. Fluent assertions cải thiện cách viết và đọc test nhưng không tự tăng độ bao phủ.

### 12.1. Kiểm tra status 4xx không giống lỗi vận chuyển

Một `GET /missing` trả 404 là **response HTTP hợp lệ** để test assert; còn host không resolve được, connection refused, TLS handshake lỗi, timeout hay codec deserialize lỗi có thể làm test thất bại **trước bước assertion body/status**.

Với `TestRestTemplate`, behavior “fault tolerant” có nghĩa 4xx/5xx không tự ném như error handler mặc định của `RestTemplate`, **không có nghĩa** client bỏ qua mọi lỗi. Với `RestTestClient` và `WebTestClient`, `expectStatus().isNotFound()` phải thật sự khớp status; đừng chuyển mọi response lỗi thành “test đã thành công”.

### 12.2. Test JSON thay vì chỉ text

Với endpoint trả JSON object, WebTestClient và RestTestClient có thể kiểm tra kiểu dữ liệu/body và có API assertion theo nội dung; khi dùng JSON path hãy kiểm tra API đang áp dụng trong version cụ thể. TestRestTemplate có thể deserialize về DTO:

```java
ResponseEntity<MyResponse> response =
        rest.getForEntity("/api/resource/1", MyResponse.class);
assertEquals(1L, response.getBody().id());
```

Đây là **minh họa trong test có `rest` và `MyResponse` định nghĩa sẵn**, không thuộc chương trình đầy đủ ở mục 4. Đừng khẳng định JSON field ordering là ổn định; kiểm tra field, semantic value, error code và content type mà hợp đồng public yêu cầu.

### 12.3. Authentication, headers và cookies

- `TestRestTemplate` có API hỗ trợ Basic Authentication và cách tùy chỉnh underlying `RestTemplate`; khi test có user/role, kiểm tra status thực và không in secret trong log.
- `WebTestClient` và `RestTestClient` cung cấp request headers/cookies và client configuration; hãy dùng đúng methods phiên bản tương ứng.
- Token JWT/OAuth2, CSRF, redirects, session cookies và Spring Security filters chỉ được kiểm chứng khi **filter/security configuration thật** nằm trong đường gọi.
- Cả ba có thể bỏ qua một phần proxy/TLS production nếu chỉ chạy loopback HTTP; nếu bảo mật đường truyền là rủi ro, cần test riêng có TLS/gateway phù hợp.

## 13. Chạy test theo từng dòng phiên bản

Từ root của **dự án Boot 3.5**, chỉ chạy các lớp được biên soạn cho Boot 3.5:

```bash
./gradlew test --tests "com.example.httpit.Boot35TestRestTemplateTest"
./gradlew test --tests "com.example.httpit.Boot35WebTestClientTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.httpit.Boot35TestRestTemplateTest"
.\gradlew.bat test --tests "com.example.httpit.Boot35WebTestClientTest"
```

Từ root của **dự án Boot 4.0**, chỉ chạy những lớp thuộc Boot 4:

```bash
./gradlew test --tests "com.example.httpit.Boot40RestTestClientTest"
./gradlew test --tests "com.example.httpit.Boot40LegacyTemplateTest"
./gradlew test --tests "com.example.httpit.Boot40WebTestClientTest"
./gradlew test --tests "com.example.httpit.RestTestClientMockControllerTest"
```

Maven wrapper (ví dụ một lớp):

```bash
./mvnw -Dtest=Boot40RestTestClientTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=Boot40RestTestClientTest test
```

Những lệnh trên giả định đã có build wrapper, plugin, Java 17+ và dependency đúng. Với multi-module Gradle/Maven, cần chạy đúng module. Các class Boot 3 và Boot 4 **không được biên dịch cùng một source set** vì chúng có import/annotation khác nhau.

**Không có stdout cố định** từ những test mẫu. Nếu chạy qua Gradle `test`, thường xem `build/reports/tests/test/index.html`; Maven Surefire thường ở `target/surefire-reports/`. Chỉ kết luận PASS khi test thực sự được khám phá, thực thi và assertion đạt; kiểm tra tình huống test bị skip, build cache hoặc thiếu dependency.

## 14. Checklist migration từ Boot 3.5 lên Boot 4.0

1. **Xem phiên bản thực trong build/BOM**, không suy đoán từ classpath. Boot 3.x dùng Spring Framework 6.x, Boot 4.x dùng Framework 7.x.
2. Nếu `TestRestTemplate` không compile, đổi package sang `org.springframework.boot.resttestclient` và khai báo module `spring-boot-resttestclient`.
3. Nếu Boot 4 test không inject được `TestRestTemplate`, thêm `@AutoConfigureTestRestTemplate`; kiểm tra module `spring-boot-restclient` cũng có mặt.
4. Nếu muốn chuyển sang `RestTestClient`, dùng `@AutoConfigureRestTestClient`, import `org.springframework.test.web.servlet.client.RestTestClient`, và chuyển assertion kiểu `ResponseEntity` sang fluent expectation.
5. Nếu muốn tiếp tục `WebTestClient`, giữ import `org.springframework.test.web.reactive.server.WebTestClient` nhưng dùng `@AutoConfigureWebTestClient` **đúng package Boot 4**, và thêm phần test WebFlux client cần thiết.
6. Kiểm tra lại `@SpringBootTest(webEnvironment = RANDOM_PORT)`: nếu bị đổi về mặc định `MOCK`, test không còn chứng minh HTTP server thật.
7. Phân biệt annotation auto-config và module test của **Boot 3** với **Boot 4**; đừng trộn import `org.springframework.boot.test.autoconfigure.*` của dòng cũ vào dự án mới.
8. Kiểm tra client có thực sự dùng base URL cổng ngẫu nhiên không; không hard-code `8080`, không gửi request sang instance khác trên máy.
9. Với ứng dụng có cả MVC và WebFlux, xác định loại web context thực sự được chọn; mặc định MVC thường thắng khi cả hai stack cùng hiện diện.
10. Với test ghi DB qua HTTP server thật, thiết kế fixture/cleanup đã commit và không phụ thuộc rollback của test thread.
11. Kiểm tra server-side filters, authentication, CORS/CSRF, JSON mapping và error payload; client thay đổi không có nghĩa hợp đồng API được giữ nguyên.
12. Chạy lại các lớp test đúng dòng version và đọc report thực tế trước khi xóa code cũ.

## 15. Lỗi thường gặp và cách xử lý

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Hành động cụ thể |
|---|---|---|
| `Cannot resolve RestTestClient` trên Boot 3 | Framework 6.x không có lớp mới | Giữ WebTestClient/TestRestTemplate hoặc nâng **đồng bộ** Boot/Framework |
| `Cannot resolve TestRestTemplate` sau nâng Boot 4 | Package đã chuyển, module chưa được khai báo | Import từ `org.springframework.boot.resttestclient`; thêm module test |
| `NoSuchBeanDefinitionException: TestRestTemplate` trong Boot 4 | Không còn được tự tạo chỉ nhờ `@SpringBootTest` | Thêm `@AutoConfigureTestRestTemplate` và dependencies |
| `NoSuchBeanDefinitionException: RestTestClient` | Chưa `@AutoConfigureRestTestClient` hoặc thiếu module | Thêm annotation, kiểm tra dependency tree |
| `NoSuchBeanDefinitionException: WebTestClient` khi nâng Boot 4 | Chưa bật auto-config mới hoặc thiếu spring-webflux/test module | `@AutoConfigureWebTestClient` đúng package + dependencies |
| `cannot find AutoConfigureWebTestClient` | Copy package import từ Boot 3 sang Boot 4 | Đổi sang `org.springframework.boot.webtestclient.autoconfigure` |
| Client gọi `localhost:8080` rồi thất bại | Server `RANDOM_PORT` đang nghe cổng khác | Dùng autoconfigured client hoặc `@LocalServerPort` để tạo base URL |
| Test mock xanh nhưng live HTTP fail | Mock không đi qua server socket hoặc filter/container thật | Bổ sung `@SpringBootTest(RANDOM_PORT)` |
| HTTP 404 làm test throw thay vì assert | Dùng `RestTemplate` thường hoặc error handler riêng | Kiểm tra loại client; dùng ResponseEntity/TestRestTemplate hoặc test client expectations |
| API `.bodyValue` không tồn tại trên RestTestClient | Trộn WebTestClient request API với RestClient request API | Dùng `.body(...)` trong RestTestClient |
| Test compile nhưng application không có RestClient.Builder | Phần RestClient auto-config bị tách khỏi web starter trong Boot 4 | Thêm module/starter restclient trên runtime chính nếu production cần |
| Test chạy 200 nhưng không kiểm chứng JSON | Chỉ assert status, bỏ qua contract body | Assert headers/body/fields/errors cần thiết |
| Test dùng `@Transactional` nhưng để lại DB rows | Request HTTP server có transaction độc lập | Cleanup ngoài transaction test, database fixture isolation |
| Security test tự bỏ filter rồi tuyên bố 401/403 đúng | Security stack chưa nằm trong đường gọi | Test với filters/security thật và credentials phù hợp |
| Startup fail vì cả MVC/WebFlux dependencies | Auto-detection ứng dụng chọn stack khác mong đợi | Chọn đúng starter và web application type |
| Test chậm/flaky không rõ nguyên nhân | Server startup, port conflict, network, DB fixture hoặc context reuse | Dùng RANDOM_PORT, context cache có kiểm soát, fixture độc lập |

## 16. Chọn client theo tình huống thực tế

Nếu đang làm **Boot 3.5 MVC REST API** và chỉ cần gửi HTTP thật, assert status/body: **`TestRestTemplate`** là lựa chọn thực dụng. Nếu muốn fluent assertions, streaming hoặc đã dùng Reactor tooling: **`WebTestClient`** là lựa chọn tốt khi classpath cho phép.

Nếu đang chuyển lên **Boot 4.x** và ứng dụng là **MVC với Spring Framework 7**, ưu tiên xem xét **`RestTestClient`** cho HTTP integration test đồng bộ hoặc test controller qua MockMvc. Nó không buộc mang theo một mô hình WebFlux server chỉ để có API assertions.

Nếu ứng dụng dùng **WebFlux/Reactive Streams**, **`WebTestClient`** vẫn là lựa chọn tự nhiên cho mock WebFlux context, HTTP integration và một số kịch bản streaming. Nếu muốn giữ những bài TestRestTemplate cũ trên Boot 4, vẫn có đường migration rõ ràng, nhưng cần cập nhật package/module/annotation.

**Quyết định cuối cùng dựa trên ba thứ:** *Spring Boot/Framework version*, *web stack và môi trường mock hay server thật*, *hợp đồng HTTP cần bảo vệ*. Chọn client theo ba điều này sẽ giúp test dễ hiểu, không phụ thuộc vào import của bản hướng dẫn khác và không nhầm test MVC slice với HTTP integration qua socket.

## 17. Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `RANDOM_PORT`, `TestRestTemplate`, `WebTestClient`, mock/live environments.
- [Spring Boot 4.0 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html): `@AutoConfigureRestTestClient`, `@AutoConfigureWebTestClient`, `@AutoConfigureTestRestTemplate` và module/package mới.
- [Spring Boot 4.0 – Test Utilities](https://docs.spring.io/spring-boot/4.0/reference/testing/test-utilities.html): tính chất `TestRestTemplate` và phạm vi của `RestTestClient`.
- [Spring Framework – RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html): cách bind vào controller, application context, router function và HTTP server.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): điểm đổi package/module/test auto-configuration khi nâng phiên bản.

**Kết luận:** Ba test clients không phải ba tên thay thế hoàn toàn cho nhau. `TestRestTemplate` dùng HTTP đồng bộ và `ResponseEntity`; `WebTestClient` cung cấp fluent assertions cho WebFlux và HTTP server phù hợp; `RestTestClient` là lựa chọn mới của Framework 7 cho imperative HTTP testing và mock Spring MVC. Khi chuyển từ Boot 3.5 sang 4.x, điều quan trọng nhất không chỉ là đổi tên client mà còn **đổi đúng package, dependencies, auto-configuration annotation và ranh giới test**; sau đó chạy test qua server thật khi mục tiêu yêu cầu HTTP integration.