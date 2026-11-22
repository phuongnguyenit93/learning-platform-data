# Spring WebFlux: Gửi request và kiểm tra status, header, body bằng WebTestClient

## 1. Mục tiêu của bài kiểm thử HTTP reactive

Khi một API Spring WebFlux nhận `GET /api/widgets/W-1` hay `POST /api/widgets/echo`, bài kiểm thử cần chứng minh **hợp đồng HTTP**: request được gửi đúng method, URI, headers và payload; response trả đúng **status**, **headers** và **body**. Việc một service trả đúng `Mono<Widget>` chưa đủ để chứng minh router/controller, codec JSON, content negotiation hoặc HTTP error mapping đúng.

Công cụ trung tâm của Spring là **`WebTestClient`** (package `org.springframework.test.web.reactive.server`). Nó có cách viết request giống `WebClient` nhưng bổ sung DSL chuyên kiểm thử response:

~~~java
webTestClient.get()
        .uri("/api/widgets/W-1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo("W-1");
~~~

Đoạn trên là **mã minh họa trong một test đã có `WebTestClient`, import `MediaType` và API phù hợp**; chưa phải chương trình độc lập. Nó biểu diễn dòng chảy **request → exchange → assertions**, không biến nội dung HTTP thành unit test thuần Java.

Kết thúc bài, bạn sẽ biết:

- Chọn **mock WebFlux server**, **application context** hay **HTTP server thật** để kiểm API.
- Gửi `GET`/`POST`, path variable, query params, `Accept`, `Content-Type`, request header và body JSON.
- Assert status `200/400/404/415`; assert header có/không, giá trị chính xác và kiểu nội dung.
- Assert JSON bằng `jsonPath`, object typed bằng `expectBody(Class)`, list bằng `expectBodyList(Class)`, body trống bằng `isEmpty()`.
- Phân biệt kiểm phản hồi HTTP với kiểm `Mono`/`Flux` bằng `StepVerifier`, và biết giới hạn với stream không kết thúc.
- Viết bộ ví dụ Java 17+/Spring Boot 3.5.x gồm `@WebFluxTest` với service mock và `@SpringBootTest(RANDOM_PORT)` với HTTP server thật.

## 2. WebTestClient hoạt động ở đâu trong stack?

`WebTestClient` là **test client**, không phải `WebClient` production được đổi tên. Nó dùng request-building API quen thuộc rồi kiểm `ExchangeResult` bằng assertion DSL của Spring Test. Có thể gắn nó vào **mock server** hoặc một **server đang nghe TCP**.

~~~text
JUnit Jupiter @Test
       |
       v
WebTestClient.get()/post()/...
       |
       v
ExchangeFunction / request + body encoder
       |
       +---- Mock binding --------------+
       |                                 |
       |     WebFlux Handler/Router/Controller
       |     codecs, filters, advice...
       |     không cần mở TCP port
       |
       +---- Live server binding -------+
                                         |
                                         v
                             HTTP client gửi qua TCP
                                         |
                                         v
                             Embedded server Netty/Tomcat...
                                         |
                                         v
                              WebFlux Handler/Controller
       |
       v
.exchange()
       |
       v
ResponseSpec
   .expectStatus()
   .expectHeader()
   .expectBody()/expectBodyList()
~~~

Ở chế độ mock, pipeline của web framework vẫn có thể được kiểm — mapping, validation, JSON serialization, một số filters — nhưng **không chứng minh** TCP listener, TLS, proxy, web server port hoặc đường truyền thực. Ở chế độ live, HTTP server và client chạy thật, thường có chi phí khởi động lớn hơn.

### Ba cách bind WebTestClient

| Cách thiết lập | Phạm vi | Server thật? | Khi phù hợp |
| --- | --- | --- | --- |
| `WebTestClient.bindToController(controller).build()` | Controller cụ thể với WebFlux infrastructure phù hợp | Không | Test nhanh một controller, thường không cần Spring Boot context |
| `WebTestClient.bindToApplicationContext(context).build()` | WebFlux context đã tạo, qua mock request/response | Không | Kiểm web configuration/filter/controller trong context |
| `WebTestClient.bindToServer().baseUrl("http://localhost:...").build()` | HTTP server đang chạy | **Có** | Kiểm HTTP thật, server behavior, contract ngoài tiến trình |

Trong Spring Boot:

- `@WebFluxTest(WidgetController.class)` **tự auto-configure `WebTestClient`** cho WebFlux slice; thường không cần gọi `bindToController` thủ công.
- `@SpringBootTest` có thể dùng `@AutoConfigureWebTestClient` để bind test client với ứng dụng WebFlux **trong môi trường mock**, không cần server thật.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` chạy embedded HTTP server; Boot có thể inject `WebTestClient` đã trỏ tới cổng thật, với relative URI. Đây là đường đi cần khi muốn chứng minh hành vi qua HTTP.

**Không nhầm `@WebFluxTest` với `@WebMvcTest`:** chúng chọn web stack khác nhau. `WebTestClient` cũng có thể test một Spring MVC server qua binding thích hợp, nhưng bài này tập trung **Spring WebFlux**.

## 3. Cấu trúc chuẩn của một test request

Mẫu giao diện đọc từ trái qua phải:

~~~text
webTestClient
  .get() / .post() / .put() / .delete()
  .uri(...)
  .header(...) / .headers(...)
  .accept(...) / .contentType(...)
  .bodyValue(...) / .body(...)
  .exchange()                 <- gửi và lấy phản hồi
  .expectStatus()...          <- HTTP status
  .expectHeader()...          <- response headers
  .expectBody()...            <- JSONPath / raw body
~~~

**Điểm chuyển tiếp là `exchange()`**: trước đó xây request, sau đó kiểm response. Nếu quên `exchange()`, request chưa được thực hiện như mong đợi. Không gọi `expectBody` trên một `WebClient.ResponseSpec` production: đó là API khác.

### 3.1 Method và URI

~~~java
// GET một resource theo ID.
client.get()
      .uri("/api/widgets/{id}", "W-1")
      .exchange();

// GET có query parameter.
client.get()
      .uri(builder -> builder
              .path("/api/widgets")
              .queryParam("limit", 20)
              .build())
      .exchange();

// DELETE resource.
client.delete()
      .uri("/api/widgets/{id}", "W-2")
      .exchange();
~~~

Các đoạn trên là **minh họa cú pháp trong test có biến `client` là `WebTestClient`**. Chúng chỉ cho thấy cách dựng request, chưa có assertions. Chỉ gọi endpoint thực sự có trong ứng dụng đang kiểm; ví dụ hoàn chỉnh ở mục 8 sẽ dùng GET/POST đã triển khai.

URI template `/api/widgets/{id}` giúp gắn biến vào path đúng cách, tránh tự nối các chuỗi chứa ký tự đặc biệt. Với query, dùng `uri(builder -> ...)` để encode đúng và dễ thêm tham số. Cân nhắc trường hợp path variable rỗng, ký tự Unicode hoặc dấu gạch chéo: nếu có ràng buộc, kiểm API ở dạng đã encode phù hợp.

### 3.2 Request header, Accept và Content-Type

~~~java
client.post()
      .uri("/api/widgets/echo")
      .header("X-Trace-Id", "trace-42")
      .contentType(MediaType.APPLICATION_JSON)
      .accept(MediaType.APPLICATION_JSON)
      .bodyValue(new EchoRequest("xin chào"))
      .exchange();
~~~

**`Accept`** mô tả media types mà client muốn **nhận về**. **`Content-Type` của request** mô tả media type của body **gửi lên**. Chúng là hai header có ý nghĩa khác nhau.

- `GET` không có body thường chỉ cần `accept(...)`, không cần ép `contentType(...)`.
- `POST` có JSON nên nên đặt `contentType(MediaType.APPLICATION_JSON)` và `bodyValue(requestDto)`.
- Response `Content-Type` nên được kiểm ở `expectHeader()`, không suy ra từ request `Accept`.
- `header("X-Trace-Id", "...")` có thể được controller/filter dùng như một phần contract; test nên xem phản hồi có echo hoặc propagate đúng khi yêu cầu.
- Không gửi token/password thật vào log hay test fixtures; nếu dùng auth, test token giả hoặc security test support phù hợp.

### 3.3 Gửi object, Publisher, form và raw string

`bodyValue(dto)` thường thuận tiện nhất cho request JSON thông thường. Với nguồn reactive:

~~~java
client.post()
      .uri("/api/widgets/echo")
      .contentType(MediaType.APPLICATION_JSON)
      .body(Mono.just(new EchoRequest("hello")), EchoRequest.class)
      .exchange();
~~~

Đây là **mẫu minh họa**, cần `reactor.core.publisher.Mono` và `EchoRequest` từ ứng dụng. `body(Publisher, Class)` hữu ích khi input đã là `Mono`/`Flux`. Đối với DTO đơn, `bodyValue(...)` dễ đọc hơn.

Đừng dùng `Flux` vô hạn làm request body trong test không có giới hạn; nó có thể khiến request không kết thúc hoặc phải được xử lý như một streaming protocol. Với form/multipart, dùng media type và body inserter phù hợp thay vì tự xây JSON tùy tiện.

## 4. Kiểm HTTP status: assert chính xác thay vì chỉ nói “không lỗi”

Sau `exchange()`, các kiểm tra phổ biến:

~~~java
.expectStatus().isOk()             // HTTP 200
.expectStatus().isCreated()        // HTTP 201
.expectStatus().isNoContent()      // HTTP 204
.expectStatus().isBadRequest()     // HTTP 400
.expectStatus().isUnauthorized()   // HTTP 401
.expectStatus().isForbidden()      // HTTP 403
.expectStatus().isNotFound()       // HTTP 404
.expectStatus().isEqualTo(415)     // HTTP 415
~~~

Đây là **danh sách các lựa chọn thay thế**, không phải một chuỗi assertions áp dụng đồng thời lên một response. Phương thức `isEqualTo(int)` cũng dùng được với các mã cụ thể chưa có shortcut phù hợp.

Đặt status theo hợp đồng:

| Kịch bản | Status thường đúng | Assertion |
| --- | --- | --- |
| Đọc một widget tồn tại | 200 OK | `isOk()` |
| Tạo tài nguyên mới thành công | 201 Created, thường có `Location` | `isCreated()` |
| Lệnh thành công và không trả body | 204 No Content | `isNoContent()` và `expectBody().isEmpty()` |
| Payload không hợp lệ | 400 Bad Request hoặc 422 theo contract | `isBadRequest()` hoặc `isEqualTo(422)` |
| Chưa xác thực | 401 Unauthorized | `isUnauthorized()` |
| Đã xác thực nhưng không có quyền | 403 Forbidden | `isForbidden()` |
| ID không tồn tại | 404 Not Found | `isNotFound()` |
| Request media type không được hỗ trợ | 415 Unsupported Media Type | `isEqualTo(415)` |
| Client yêu cầu response media type không thể tạo | 406 Not Acceptable | `isEqualTo(406)` |
| Lỗi máy chủ chưa xử lý | 500 Internal Server Error | `is5xxServerError()` hoặc mã cụ thể |

Các mã **phụ thuộc contract của ứng dụng**, không phải mọi POST đều tạo 201 hoặc mọi validation đều dùng 400. Không sửa status test thành 200 chỉ vì controller dùng `ResponseEntity.ok()` khi đặc tả yêu cầu 201.

**`is2xxSuccessful()`**, `is4xxClientError()` hay `is5xxServerError()` thuận tiện cho kiểm nhóm, nhưng khi một API cần phân biệt 400 với 404, assertion **đúng mã** mang giá trị hơn. Một bài test trả 404 không được coi là PASS chỉ vì “nó là lỗi 4xx”.

## 5. Kiểm response headers

`expectHeader()` trả về các assertion chuyên biệt cho response headers:

~~~java
client.get()
      .uri("/api/widgets/W-1")
      .exchange()
      .expectStatus().isOk()
      .expectHeader().exists("X-Trace-Id")
      .expectHeader().valueEquals("X-Trace-Id", "trace-42")
      .expectHeader().contentTypeCompatibleWith(
              MediaType.APPLICATION_JSON);
~~~

Đây là **đoạn minh họa** giả định controller trả `X-Trace-Id: trace-42`. Ví dụ hoàn chỉnh ở mục 8 sẽ gửi request header tương ứng.

Các kiểu assert nên phân biệt:

- `exists("X-Trace-Id")`: chỉ đảm bảo có header, **không chứng minh giá trị đúng**.
- `valueEquals("X-Trace-Id", "trace-42")`: kiểm giá trị mong muốn, phù hợp correlation ID, custom header.
- `contentType(MediaType.APPLICATION_JSON)`: cần đúng media type theo cách so sánh của API.
- `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)`: phù hợp khi các tham số như charset có thể khác mà media type vẫn tương thích.
- `location("/api/widgets/W-3")` hoặc `valueEquals("Location", "...")`: hữu ích với response 201.
- Các header kiểm cache, CORS, ETag, retry-after, security… chỉ nên được assert nếu là một phần contract.

Tên HTTP headers **không phân biệt chữ hoa/thường** theo giao thức. Đừng viết assertions phụ thuộc thứ tự header hoặc toàn bộ tập headers nếu server/framework có thể bổ sung header hợp lệ. Với cookie có thuộc tính `HttpOnly`, `Secure`, `SameSite`, hãy kiểm contract liên quan thay vì chỉ sự hiện diện.

**Lưu ý về `Location`:** 201 Created thường có header chứa URI của tài nguyên vừa tạo. Một POST chỉ echo lại payload mà **không tạo resource** nên thường nên trả 200, không gắn 201 để “có thêm test status”. Ví dụ ở mục 8 cố ý trả 200 cho echo.

## 6. Kiểm body: JSONPath, typed object, list và body trống

### 6.1 JSONPath khi chỉ một vài trường cần quan tâm

~~~java
client.get()
      .uri("/api/widgets/W-1")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .jsonPath("$.id").isEqualTo("W-1")
      .jsonPath("$.name").isEqualTo("Bút");
~~~

`$` là root của JSON. `$.id` chọn trường `id`; `$.items[0].id` chọn trường `id` trong phần tử thứ nhất của array `items`. JSONPath hữu ích khi test chỉ quan tâm một vài field công khai, không muốn cố định thứ tự thuộc tính hay whitespace.

Nếu muốn khẳng định field có/không có, dùng các assertions như `exists()`, `doesNotExist()` theo API JSONPath. Với giá trị số, chú ý JSON number decoding có thể dùng kiểu Integer/Long/Double; nên chọn assertion phù hợp kiểu hoặc đọc vào DTO nếu logic chuyển kiểu quan trọng.

### 6.2 So sánh toàn bộ JSON khi contract yêu cầu

~~~java
client.get()
      .uri("/api/widgets/W-1")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .json("{\"id\":\"W-1\",\"name\":\"Bút\"}");
~~~

`json(...)` dùng cơ chế so sánh JSON có ngữ nghĩa, khác so sánh hai chuỗi raw có thứ tự field/whitespace khác. Chỉ dùng khi dữ liệu thực sự ổn định và bạn muốn kiểm cả cấu trúc quan trọng. Nếu field mới hợp lệ được thêm vào response, mức strictness của JSON comparison quyết định test có fail hay không; chọn mode phù hợp với contract.

### 6.3 Decode về kiểu Java

~~~java
WidgetResponse actual = client.get()
        .uri("/api/widgets/W-1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(WidgetResponse.class)
        .returnResult()
        .getResponseBody();

assertEquals(new WidgetResponse("W-1", "Bút"), actual);
~~~

Đoạn này là **mã minh họa trong test có import `WidgetResponse` và JUnit assertEquals**. `expectBody(Class<T>)` decode response bằng codecs của test client. Khi record có `equals` theo dữ liệu, so sánh object rõ ràng hơn JSONPath nếu cần toàn bộ DTO.

Một cách khác:

~~~java
client.get().uri("/api/widgets/W-1")
      .exchange()
      .expectBody(WidgetResponse.class)
      .isEqualTo(new WidgetResponse("W-1", "Bút"));
~~~

Với type generic như `List<ApiEnvelope<WidgetResponse>>`, dùng overload `ParameterizedTypeReference<T>` phù hợp thay vì mong JVM giữ toàn bộ generic type qua `Class<T>`.

### 6.4 Decode danh sách hữu hạn

~~~java
client.get()
      .uri("/api/widgets")
      .exchange()
      .expectStatus().isOk()
      .expectBodyList(WidgetResponse.class)
      .hasSize(2)
      .contains(new WidgetResponse("W-1", "Bút"));
~~~

Đoạn này hợp lý nếu API trả JSON array **hữu hạn**. `expectBodyList` phải thu thập body để decode; không nên dùng cho một `Flux`/SSE stream **vô hạn**.

### 6.5 Body trống

~~~java
client.delete()
      .uri("/api/widgets/W-2")
      .exchange()
      .expectStatus().isNoContent()
      .expectBody().isEmpty();
~~~

Đây là **minh họa cho một endpoint DELETE có contract 204**, không phải endpoint đã triển khai trong ví dụ mục 8. Kiểm `isEmpty()` giúp phát hiện controller vô tình serialize một object/body dù hợp đồng quy định không có nội dung.

### 6.6 Custom assertions khi DSL chưa đủ

~~~java
client.get().uri("/api/widgets/W-1")
      .exchange()
      .expectStatus().isOk()
      .expectBody(WidgetResponse.class)
      .consumeWith(result -> {
          WidgetResponse body = result.getResponseBody();
          assertNotNull(body);
          assertTrue(body.id().startsWith("W-"));
      });
~~~

Đây là **đoạn minh họa** (cần `assertNotNull`, `assertTrue`). `consumeWith` mở quyền viết assertions tùy chỉnh; không cần cố nhét mọi rule vào một expression JSONPath phức tạp. Có thể dùng `returnResult()` và assert ngoài chuỗi DSL như ví dụ 6.3.

## 7. Các mức kiểm thử WebFlux và tác động tới kết quả

Một `WebTestClient` assertion giống nhau có thể chạy trong các môi trường khác nhau, nhưng **bằng chứng khác nhau**:

| Môi trường | Khởi động gì? | Điều chứng minh | Không tự chứng minh |
| --- | --- | --- | --- |
| `bindToController(...)` | WebFlux handler infrastructure cho controller đã cấp | Mapping và xử lý controller theo cấu hình mock | Spring Boot app wiring, server, hạ tầng |
| `@WebFluxTest(WidgetController.class)` | WebFlux slice, codecs, controller, filters/advice được chọn | Request/response ở web layer, dependency được mock/import | Service/repository thật, TCP |
| `@SpringBootTest + @AutoConfigureWebTestClient` với mock environment | Nhiều bean ứng dụng hơn, WebTestClient bind mock | Context wiring và web behavior không qua TCP | Server port, TLS/network |
| `@SpringBootTest(RANDOM_PORT)` | Full context và HTTP server thật | HTTP request/response qua loopback và server | Database production, reverse proxy, auth production nếu chưa cấu hình |

Trong `@WebFluxTest`, một `@Service` phụ thuộc của controller thường bị lọc ra. Dùng **`@MockitoBean`** (Spring Framework 6.2+/Spring Boot 3.4+) để cấp mock **ngay trong ApplicationContext**; `@Mock` thuần Mockito không tự tạo bean trong Spring context.

Nếu logic service là mục tiêu, kiểm riêng bằng JUnit/Mockito với `Mono`/`Flux` và `StepVerifier`. Nếu lỗi nằm ở codec, routing hoặc HTTP status, dùng WebTestClient. Nếu cần kiểm HTTP transport/server, dùng RANDOM_PORT. Không mặc định dùng full-context cho mọi nhánh service.

### Ví dụ khác nhau về cùng request

- `@WebFluxTest` mock `WidgetService.findById("W-1")` trả `Mono.just(...)`. Test chứng minh controller chọn status/header/body đúng khi service trả dữ liệu.
- `@SpringBootTest(RANDOM_PORT)` dùng `InMemoryWidgetService` thật để trả widget; test kiểm cả wiring + server HTTP loopback.
- Một integration test database sẽ cần repository/DB thật nếu mục tiêu là query hoặc transaction. Không phải vì WebTestClient trả 200 mà SQL đã được kiểm.

## 8. Ví dụ đầy đủ: Spring Boot 3.5.x + Java 17 + WebFlux + WebTestClient

Bài thực hành cung cấp **production code** trong `src/main/java` và **hai test classes** trong `src/test/java`. Nó sử dụng `spring-boot-starter-webflux`, `spring-boot-starter-test`, JUnit Jupiter và Mockito. Không cần database, Docker hoặc dịch vụ mạng ngoài. Một lớp test chỉ dùng mock WebFlux server; lớp kia khởi động HTTP server nội bộ trên random port.

Phạm vi API:

| Method/URI | Hành vi | Status | Body |
| --- | --- | --- | --- |
| `GET /api/widgets/W-1` | Trả widget tồn tại | 200 | `{"id":"W-1","name":"Bút"}` |
| `GET /api/widgets/not-found` | Không có widget | 404 | Rỗng |
| `GET /api/widgets` | Liệt kê widget | 200 | JSON array hai phần tử |
| `GET /api/widgets/ping` | Ping dạng text | 200 | `pong` |
| `POST /api/widgets/echo` với message hợp lệ | Trim text rồi echo | 200 | JSON message + length |
| `POST /api/widgets/echo` với message blank | Từ chối | 400 | Rỗng |
| `POST /api/widgets/echo` với text/plain | Sai media type | 415 | Body lỗi tùy cơ chế xử lý |

### 8.1 Cây thư mục

~~~text
src/
  main/
    java/example/webflux/
      WebFluxDemoApplication.java
      Widget.java
      WidgetResponse.java
      EchoRequest.java
      EchoResponse.java
      WidgetService.java
      InMemoryWidgetService.java
      WidgetController.java
  test/
    java/example/webflux/
      WidgetControllerSliceTest.java
      WidgetHttpIntegrationTest.java
~~~

**Tất cả file** dùng package `example.webflux`. Giữ test cùng package hierarchy với root `@SpringBootApplication` để Spring Boot tìm được cấu hình chính. Java records cần Java 17+.

### 8.2 WebFluxDemoApplication.java

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` cho phép Spring scan `@RestController` và `@Service`. Dự án chỉ nên dùng `spring-boot-starter-webflux` cho ví dụ này; nếu đồng thời thêm `spring-boot-starter-web` (MVC), Boot thường ưu tiên MVC web application type khi không cấu hình khác.

### 8.3 Widget.java

~~~java
package example.webflux;

public record Widget(String id, String name) {
}
~~~

### 8.4 WidgetResponse.java

~~~java
package example.webflux;

public record WidgetResponse(String id, String name) {
}
~~~

`WidgetResponse` là HTTP response DTO, tách khỏi domain record `Widget`. Jackson encode thành JSON có `id` và `name`, không yêu cầu mock record.

### 8.5 EchoRequest.java

~~~java
package example.webflux;

public record EchoRequest(String message) {
}
~~~

### 8.6 EchoResponse.java

~~~java
package example.webflux;

public record EchoResponse(String message, int length) {
}
~~~

Với message sau trim là `"xin chào"`, `String.length()` trả **8 ký tự UTF-16 code units** trong trường hợp này. Đây không phải quy tắc đếm grapheme Unicode cho mọi ngôn ngữ; payload thực tế có thể dùng emoji/surrogate pairs. Trong bài thực hành, giá trị 8 là xác định.

### 8.7 WidgetService.java

~~~java
package example.webflux;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface WidgetService {
    Mono<Widget> findById(String id);
    Flux<Widget> list();
}
~~~

Interface trả `Mono` cho tối đa một widget và `Flux` cho danh sách. Đây là boundary giúp `@WebFluxTest` thay service bằng Mockito mock mà controller vẫn chạy thật.

### 8.8 InMemoryWidgetService.java

~~~java
package example.webflux;

import java.util.List;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InMemoryWidgetService implements WidgetService {

    private static final List<Widget> DATA = List.of(
            new Widget("W-1", "Bút"),
            new Widget("W-2", "Sổ"));

    @Override
    public Mono<Widget> findById(String id) {
        return Flux.fromIterable(DATA)
                .filter(widget -> widget.id().equals(id))
                .next();
    }

    @Override
    public Flux<Widget> list() {
        return Flux.fromIterable(DATA);
    }
}
~~~

Service production chạy thật khi dùng `@SpringBootTest(RANDOM_PORT)`. Nó dùng dữ liệu in-memory **bất biến**, nên hai test HTTP có thể đọc mà không phụ thuộc thứ tự hoặc cần cleanup database. Đây không phải ví dụ Reactive Repository thực hay bằng chứng non-blocking I/O với database.

### 8.9 WidgetController.java

~~~java
package example.webflux;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/widgets")
public class WidgetController {

    private final WidgetService service;

    public WidgetController(WidgetService service) {
        this.service = service;
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<WidgetResponse>> findById(
            @PathVariable("id") String id,
            @RequestHeader(name = "X-Trace-Id",
                    defaultValue = "missing") String traceId) {

        return service.findById(id)
                .map(widget -> ResponseEntity.ok()
                        .header("X-Trace-Id", traceId)
                        .body(new WidgetResponse(
                                widget.id(), widget.name())))
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<WidgetResponse> list() {
        return service.list()
                .map(widget -> new WidgetResponse(
                        widget.id(), widget.name()));
    }

    @GetMapping(path = "/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<EchoResponse>> echo(
            @RequestBody Mono<EchoRequest> requestBody) {

        return requestBody.map(request -> {
            if (request.message() == null
                    || request.message().isBlank()) {
                return ResponseEntity.badRequest()
                        .<EchoResponse>build();
            }

            String value = request.message().trim();
            return ResponseEntity.ok()
                    .header("X-Handler", "echo")
                    .body(new EchoResponse(value, value.length()));
        });
    }
}
~~~

Cơ chế:

- `findById` nhận path variable và request header; khi service trả widget, response 200 có `X-Trace-Id` và JSON DTO; khi `Mono.empty()`, trả 404 không body.
- `list` map từng domain `Widget` thành `WidgetResponse`, Spring WebFlux serialize thành JSON array khi Flux hoàn tất.
- `ping` trả text/plain, giúp minh họa body không phải JSON.
- `echo` nhận request body dưới dạng `Mono<EchoRequest>`, trim message, trả 200 + `X-Handler` + JSON; message rỗng/trắng trả 400. `consumes` giới hạn request content type, dẫn đến 415 khi client gửi `text/plain`.
- Không gọi `block()`, `subscribe()` thủ công trong controller. WebFlux quản lý subscription cho response publisher khi xử lý request.

**Lưu ý về error body:** framework hoặc một `@ControllerAdvice` toàn ứng dụng có thể tạo JSON error response cho status 400/415. Khi contract chỉ yêu cầu **status**, không assert error body phải rỗng trừ khi đã chủ động thiết kế controller làm vậy.

### 8.10 Slice test — WidgetControllerSliceTest.java

~~~java
package example.webflux;

import java.util.Optional;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(WidgetController.class)
@DisplayName("WebFlux slice: status, headers, body")
class WidgetControllerSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    WidgetService service;

    @Test
    @DisplayName("GET tìm thấy: 200, X-Trace-Id và JSON")
    void getFoundWidget() {
        when(service.findById("W-1"))
                .thenReturn(Mono.just(new Widget("W-1", "Bút")));

        client.get()
                .uri("/api/widgets/{id}", "W-1")
                .header("X-Trace-Id", "slice-42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Trace-Id", "slice-42")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("W-1")
                .jsonPath("$.name").isEqualTo("Bút");

        verify(service).findById("W-1");
    }

    @Test
    @DisplayName("GET không tìm thấy: 404 và body trống")
    void getMissingWidget() {
        when(service.findById("missing"))
                .thenReturn(Mono.empty());

        client.get()
                .uri("/api/widgets/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody().isEmpty();

        verify(service).findById("missing");
    }

    @Test
    @DisplayName("GET danh sách: decode typed JSON array")
    void getWidgetList() {
        when(service.list()).thenReturn(Flux.just(
                new Widget("W-1", "Bút"),
                new Widget("W-2", "Sổ")));

        client.get()
                .uri("/api/widgets")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBodyList(WidgetResponse.class)
                .hasSize(2)
                .contains(
                        new WidgetResponse("W-1", "Bút"),
                        new WidgetResponse("W-2", "Sổ"));

        verify(service).list();
    }

    @Test
    @DisplayName("POST JSON: 200, custom response header, typed body")
    void echoValidJson() {
        EchoResponse actual = client.post()
                .uri("/api/widgets/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest("  xin chào  "))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Handler", "echo")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody(EchoResponse.class)
                .returnResult()
                .getResponseBody();

        assertEquals(new EchoResponse("xin chào", 8), actual);
    }

    @Test
    @DisplayName("POST blank message: 400 và body rỗng")
    void echoRejectsBlankMessage() {
        client.post()
                .uri("/api/widgets/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest("   "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody().isEmpty();
    }

    @Test
    @DisplayName("POST text/plain: 415 vì consumes JSON")
    void echoRejectsUnsupportedMediaType() {
        client.post()
                .uri("/api/widgets/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("not-json")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    @DisplayName("GET ping: 200, text/plain, String body")
    void pingReturnsPlainText() {
        client.get()
                .uri("/api/widgets/ping")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN)
                .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

**Có 7 phương thức `@Test`**. `@WebFluxTest` tạo WebFlux slice và auto-configure `WebTestClient`, không mở cổng TCP. `@MockitoBean` tạo mock `WidgetService` trong Spring test context, vì regular `@Service InMemoryWidgetService` không thuộc slice; nếu chỉ dùng `@Mock` của Mockito ở field, controller có thể vẫn thiếu bean.

Các assertions được chia theo mục đích:

1. `getFoundWidget`: gửi request header, kiểm status 200, response header echo đúng giá trị và hai field JSON; verify service nhận đúng ID.
2. `getMissingWidget`: service trả `Mono.empty()`, controller phải phát 404 mà không có body.
3. `getWidgetList`: mock trả `Flux` hữu hạn, WebTestClient decode về `List<WidgetResponse>`, kiểm size và nội dung.
4. `echoValidJson`: kiểm request DTO được serialize, server decode, normalize và encode typed response; kiểm cả `X-Handler`.
5. `echoRejectsBlankMessage`: input trống không được coi là thành công; kiểm status 400 và body rỗng do controller trả `ResponseEntity.badRequest().build()`.
6. `echoRejectsUnsupportedMediaType`: request body text/plain không phù hợp `consumes=application/json`, chỉ assert 415 để không phụ thuộc định dạng error body mặc định.
7. `pingReturnsPlainText`: chứng minh response có thể là text/plain thay vì JSON, và dùng `expectBody(String.class)`.

**Điểm QA:** import `java.util.Optional` trong class trên không cần thiết và có thể bỏ khi áp dụng vào project; import dư không làm Java fail compilation, nhưng nên giữ code gọn. Các phương thức mock chỉ stub khi đường đi thật sự gọi service, không setup thừa ở `@BeforeEach`.

### 8.11 HTTP integration test — WidgetHttpIntegrationTest.java

~~~java
package example.webflux;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DisplayName("WebFlux HTTP thật trên random port")
class WidgetHttpIntegrationTest {

    @Autowired
    WebTestClient client;

    @LocalServerPort
    int port;

    @Test
    @DisplayName("GET qua server thật: status, header, JSON")
    void liveServerGetWorks() {
        assertTrue(port > 0);

        client.get()
                .uri("/api/widgets/W-1")
                .header("X-Trace-Id", "wire-7")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Trace-Id", "wire-7")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("W-1")
                .jsonPath("$.name").isEqualTo("Bút");
    }

    @Test
    @DisplayName("POST qua HTTP thật: JSON round-trip")
    void liveServerPostWorks() {
        client.post()
                .uri("/api/widgets/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest(" hello "))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Handler", "echo")
                .expectBody(EchoResponse.class)
                .isEqualTo(new EchoResponse("hello", 5));
    }
}
~~~

**Có 2 phương thức `@Test`**. Trong Spring Boot 3.5.x, với `RANDOM_PORT` và WebFlux trong classpath, Boot cung cấp `WebTestClient` đã được cấu hình tới running server và hỗ trợ URI tương đối. Port là giá trị do hệ điều hành chọn, không cố định 8080. `@LocalServerPort` giúp xác minh server đã bind port thực.

Trong test HTTP thật, `InMemoryWidgetService` **chạy thật** qua controller, không mock. Tuy nhiên nó chỉ chứa list cố định, không kiểm database hay network service bên ngoài.

**Không đánh đồng hai kiểu test:** `@AutoConfigureWebTestClient` dùng cho WebTestClient bound trực tiếp vào ứng dụng mock ở các context phù hợp; `RANDOM_PORT` tạo embedded server thật. Khi cần chắc chắn test qua TCP, kiểm mode server và cấu hình client; không chỉ nhìn thấy `WebTestClient` đã được inject.

### 8.12 Gradle: dependencies và lệnh chạy

Trong dự án **Spring Boot 3.5.x** đã có Gradle plugin, dependency management và Java 17 toolchain, đoạn `build.gradle` cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn cấu hình**, không phải build file hoàn chỉnh; nếu muốn dùng `StepVerifier` trong bài test publisher riêng, có thể thêm `testImplementation 'io.projectreactor:reactor-test'` nếu starter/project chưa cung cấp dependency đó.

Chạy bằng Gradle wrapper ở project root:

~~~bash
./gradlew test --tests example.webflux.WidgetControllerSliceTest --tests example.webflux.WidgetHttpIntegrationTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.webflux.WidgetControllerSliceTest --tests example.webflux.WidgetHttpIntegrationTest
~~~

**Kết quả dự kiến** trong môi trường đúng dependencies và WebFlux: **9 phương thức JUnit Jupiter PASS** (7 ở slice, 2 ở HTTP integration). Các test không tự in stdout; Gradle/IDE có thể hiển thị tổng số và `BUILD SUCCESSFUL`, còn port ngẫu nhiên và startup logs không cố định. Không cần Testcontainers hoặc DB.

Nếu project đã có cả `spring-boot-starter-web` và WebFlux, Spring Boot thường ưu tiên servlet MVC. Để học đúng reactive stack, **không thêm MVC starter** trong project mini này, hoặc cấu hình `spring.main.web-application-type=reactive` khi có lý do cụ thể và dependencies phù hợp.

## 9. Kỹ thuật assertions nâng cao: giữ contract rõ và giảm test giòn

### 9.1 Kiểm status, header, body trong cùng một flow

Viết chuỗi assertions gần request giúp người đọc thấy **đúng hợp đồng của một endpoint**:

~~~java
client.get().uri("/api/widgets/W-1")
      .header("X-Trace-Id", "t-1")
      .exchange()
      .expectStatus().isOk()
      .expectHeader().valueEquals("X-Trace-Id", "t-1")
      .expectBody()
      .jsonPath("$.id").isEqualTo("W-1");
~~~

Nếu nhiều assertions độc lập cần chạy cùng lúc để thấy nhiều lỗi trong một response, `WebTestClient.ResponseSpec.expectAll(...)` được Spring Framework hỗ trợ:

~~~java
client.get().uri("/api/widgets/W-1")
      .exchange()
      .expectAll(
          spec -> spec.expectStatus().isOk(),
          spec -> spec.expectHeader()
                      .contentTypeCompatibleWith(
                              MediaType.APPLICATION_JSON));
~~~

Đây là **minh họa cú pháp**; endpoint có service thật/mock phù hợp trước khi request. `expectAll` giúp thu thập nhiều assertion failures; không dùng nó để thay logic sắp xếp test hoặc bỏ kiểm body.

### 9.2 Không assert raw JSON string trừ khi whitespace/order là contract

Chuỗi JSON có thể khác thứ tự fields nhưng nghĩa không đổi. `jsonPath`, `json(...)` hoặc typed body thường bền hơn:

~~~java
.expectBody()
.jsonPath("$.id").isEqualTo("W-1")
.jsonPath("$.name").isEqualTo("Bút");
~~~

Nếu API có rule “field `secret` không bao giờ xuất hiện”, thêm `jsonPath("$.secret").doesNotExist()` vào test phù hợp, thay vì chỉ kiểm hai trường hợp lệ.

Nếu response có timestamps, UUID hay random values, không khẳng định chúng bằng một literal không kiểm soát. Tiêm `Clock`/`IdGenerator` hoặc kiểm format/range và phần giá trị ổn định theo contract.

### 9.3 Kiểm header Location khi tạo tài nguyên

Với API tạo resource thật:

~~~java
client.post().uri("/api/widgets")
      .contentType(MediaType.APPLICATION_JSON)
      .bodyValue(new CreateWidgetRequest("Bút"))
      .exchange()
      .expectStatus().isCreated()
      .expectHeader().exists("Location");
~~~

Đây là **minh họa cho API khác**, vì project mini ở mục 8 chỉ có POST echo. `CreateWidgetRequest` và endpoint `POST /api/widgets` phải được ứng dụng định nghĩa mới chạy được. Trong test production, nên assert thêm giá trị Location hợp lệ, ID trong body, và khi đọc lại resource vừa tạo thì trả trạng thái tương ứng.

### 9.4 Kiểm response cookies và cache

Khi hợp đồng liên quan cookie bảo mật, ETag hoặc Cache-Control, hãy assert đúng field và thuộc tính thay vì chỉ status 200. Ví dụ kiểm header custom:

~~~java
client.get().uri("/api/widgets/W-1")
      .header("X-Trace-Id", "t-2")
      .exchange()
      .expectHeader().valueEquals("X-Trace-Id", "t-2");
~~~

Đối với cookie, tránh log session secret. Đừng assert mọi header do Netty/codec tạo vì một bản cập nhật framework hợp lệ có thể thêm headers hoặc thay thứ tự mà không vi phạm API.

## 10. Flux streaming và SSE: đừng đợi một response vô hạn kết thúc

`expectBodyList(WidgetResponse.class)` và `expectBody()` phù hợp cho **body hữu hạn**. Nếu API trả `Flux` vô hạn hoặc SSE `text/event-stream`, việc cố thu thập toàn bộ vào list có thể **chờ mãi**, hết timeout hoặc tốn bộ nhớ.

Với streaming response, dùng `returnResult(SomeType.class)` để nhận `Flux<T>` và `StepVerifier` để kiểm các sự kiện đầu và hủy subscription khi đủ:

~~~java
Flux<WidgetResponse> events = client.get()
        .uri("/api/widgets/stream")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(WidgetResponse.class)
        .getResponseBody();

StepVerifier.create(events.take(2))
        .expectNext(
                new WidgetResponse("W-1", "Bút"),
                new WidgetResponse("W-2", "Sổ"))
        .verifyComplete();
~~~

**Đây là minh họa riêng**, không chạy với project mục 8 vì project không khai báo `/api/widgets/stream`. Muốn dùng cần thêm endpoint SSE thật, import `Flux`/`StepVerifier` và dependency `reactor-test`. `take(2)` giúp chỉ tiêu thụ hai phần tử rồi cancel upstream, thay vì chờ stream vô hạn tự hoàn tất.

**Kiểm backpressure và thời gian** là mối quan tâm bổ sung:

- `WebTestClient` kiểm contract HTTP; `StepVerifier` kiểm thứ tự item, completion/error của publisher.
- Để kiểm timeout/delay của operator, dùng `StepVerifier.withVirtualTime(...)` khi logic hỗ trợ virtual scheduler, tránh `Thread.sleep`.
- Với streaming qua server thật, buffering/proxy/flush có thể làm hành vi khác mock binding. Nếu contract SSE quan trọng, có ít nhất một integration test qua TCP.
- Đừng tự gọi `block()` trên Netty event-loop trong controller để “đơn giản hóa” test; điều đó có thể phá non-blocking model.

## 11. Error handling: kiểm cả lỗi, nhưng không phụ thuộc nội dung lỗi mặc định

WebFlux có nhiều nguồn lỗi:

1. Không tìm thấy resource: controller có thể trả `ResponseEntity.notFound()`, như ví dụ.
2. Payload sai dạng: codec có thể ném lỗi decode, framework chọn 400.
3. Media type request không hỗ trợ: `consumes` mapping có thể dẫn tới 415.
4. Response `Accept` không tương thích: có thể trả 406.
5. Bean/service lỗi: có thể được `@RestControllerAdvice` xử lý theo contract hoặc rơi về 500.
6. Thiếu quyền: Spring Security WebFlux filters có thể trả 401/403.

**Không thể mặc định khẳng định mọi lỗi có body giống nhau**. Spring Boot error handler, Problem Details (`application/problem+json`), custom `@RestControllerAdvice`, locale và version framework có thể làm error body khác. Nếu API có error schema chính thức, hãy tạo typed DTO hoặc JSONPath assertions cho `code`, `message`, correlation ID và `Content-Type` theo contract. Nếu chỉ kiểm điều kiện từ chối, status assertion có thể đủ.

Ví dụ pattern khi contract có JSON lỗi:

~~~java
client.post().uri("/api/orders")
      .contentType(MediaType.APPLICATION_JSON)
      .bodyValue(new OrderRequest(""))
      .exchange()
      .expectStatus().isBadRequest()
      .expectBody()
      .jsonPath("$.code").isEqualTo("INVALID_ORDER");
~~~

Đây là **minh họa** cho API có `OrderRequest`/`/api/orders`/custom error mapping, không phải response mặc định của mini project. Không sao chép assertion này vào một controller chưa định nghĩa error DTO.

Với `@WebFluxTest`, các `@ControllerAdvice` thuộc web layer có thể được chọn; nếu advice production bị lọc hoặc không được tự nạp, import cấu hình cần thiết rồi kiểm error contract thật. Không mock chính mapper lỗi khi mục tiêu là kiểm nó.

## 12. Spring Security, authentication và CSRF trong WebFlux test

Khi ứng dụng dùng Spring Security reactive, `@WebFluxTest` hoặc full-context WebFlux test có thể áp dụng security filters. Một request đang mong 200 có thể trả **401/403** bởi thiếu authentication hoặc CSRF; không nên giải quyết bằng cách tắt tất cả filters mà không hiểu phạm vi.

Đối với kiểm thử security:

- Dùng `spring-security-test` thích hợp với reactive WebTestClient.
- Dùng `SecurityMockServerConfigurers.mockUser()` hoặc các test configurers phù hợp cho identity/authorities.
- Với những method cần CSRF, dùng `csrf()` test configurer khi policy yêu cầu.
- Assert 401/403, response headers và error body phù hợp với security contract.

Ví dụ cú pháp (không độc lập, dự án phải có Spring Security và test dependency):

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

WebTestClient authorizedClient = client.mutateWith(
        mockUser("tester").roles("READER"));

authorizedClient.get()
        .uri("/api/widgets/W-1")
        .exchange()
        .expectStatus().isOk();
~~~

Một test cần role `ADMIN` mà chỉ cấp `READER` có thể đúng hợp đồng khi nhận 403. Đừng cố sửa `@MockitoBean` cho service vì filter security từ chối request **trước khi controller gọi service**.

## 13. Timeout và tính ổn định của WebTestClient

WebTestClient có giới hạn thời gian chờ response. Với test server thật, thời lượng phụ thuộc startup, CI load, thread scheduling và I/O. Đừng dùng timeout sát mức vài ms để chứng minh latency production.

Cách cấu hình thủ công khi gắn live server:

~~~java
WebTestClient live = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8080")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
~~~

Đây là **mã minh họa**; phải có server đang chạy thật trên port 8080 và import `java.time.Duration`. Với `@SpringBootTest(RANDOM_PORT)`, **không hardcode 8080**: dùng injected Boot client hoặc `@LocalServerPort`.

Khi test thất bại timeout:

1. Kiểm server có bind cổng thật và controller có phản hồi không.
2. Kiểm `Mono`/`Flux` có completion hoặc stream cố ý kéo dài.
3. Kiểm có lời gọi blocking trên event loop hay deadlock không.
4. Kiểm external dependency thực sự có deadline ở HTTP client/DB driver, thay vì chỉ tăng timeout của test.
5. Nếu phản hồi từ mock service là `Mono.never()`, client sẽ chờ mãi đến timeout; một test business error nên stub một publisher xác định như `Mono.error(...)`.
6. Tránh dùng ``Thread.sleep`, random delay hoặc shared mutable state để chờ một event. Dùng `StepVerifier`, virtual time hoặc tín hiệu synchronization khi kiểm reactive publisher.

Chỉnh timeout ở đúng tầng: timeout của WebTestClient là **thời hạn quan sát test HTTP response**, không tự hủy an toàn mọi tác vụ downstream hoặc rollback side effects.

## 14. Các lỗi thường gặp khi gửi request và kiểm phản hồi

**Lỗi 1 — Quên `exchange()`.**  
Đã dựng request nhưng chưa kích hoạt exchange và nhận `ResponseSpec`, nên không có response để assert.

**Lỗi 2 — Nhầm request Content-Type với Accept.**  
`Content-Type` của POST cho biết body gửi đi là JSON; `Accept` mong JSON trả về. Nếu `consumes` không khớp, server có thể trả 415; nếu response media type không đáp ứng Accept, có thể trả 406.

**Lỗi 3 — Chỉ assert `is2xxSuccessful()`.**  
Bạn có thể bỏ sót khác biệt 200, 201 hoặc 204 vốn là contract chính. Dùng assertion status cụ thể.

**Lỗi 4 — Chỉ kiểm header tồn tại.**  
`exists("X-Trace-Id")` không chứng minh server echo đúng trace ID của request. Dùng `valueEquals` khi giá trị là contract.

**Lỗi 5 — So sánh JSON raw string quá cứng.**  
Thứ tự fields hoặc whitespace có thể khác nhưng JSON vẫn tương đương. Dùng JSONPath, typed object, hoặc JSON comparison phù hợp.

**Lỗi 6 — Assert error body framework phải rỗng.**  
Boot có thể thêm JSON error/Problem Details. Chỉ assert `isEmpty()` nếu chính controller/contract xác định body rỗng.

**Lỗi 7 — Mock chính controller.**  
Test không còn kiểm mapping/codec/controller thật. Giữ controller thật trong `@WebFluxTest`, chỉ mock collaborator như `WidgetService`.

**Lỗi 8 — Chỉ dùng Mockito `@Mock` nhưng controller vẫn thiếu bean.**  
`@Mock` không tự đăng ký với Spring context. Dùng `@MockitoBean` trong Boot 3.4+/Framework 6.2 hoặc bean test config.

**Lỗi 9 — Nghĩ `@WebFluxTest` đã chạy Netty/TCP server.**  
Đó là mock web environment. Muốn kiểm HTTP server thật, dùng `@SpringBootTest(RANDOM_PORT)` hoặc `bindToServer` đúng endpoint.

**Lỗi 10 — Dùng `expectBodyList` cho SSE/Flux không kết thúc.**  
Body collector chờ completion; thay bằng `returnResult` và `StepVerifier` có giới hạn sự kiện, hủy subscription.

**Lỗi 11 — Dùng `block()` ở controller reactive.**  
Dù test có thể PASS trong điều kiện nhỏ, blocking trên event loop làm mất mô hình non-blocking và có thể gây throughput thấp/deadlock trong runtime.

**Lỗi 12 — Cài cả Spring MVC và WebFlux rồi nghĩ Boot sẽ chọn WebFlux.**  
Khi hai web stacks có trên classpath, Spring MVC thường được ưu tiên. Đối chiếu cấu hình web application type và dependencies.

**Lỗi 13 — Response 401/403 bị xem là thiếu bean.**  
Security filter có thể chặn trước controller. Dùng Spring Security Test, identity/role/CSRF theo yêu cầu, không tắt filters vô cớ.

**Lỗi 14 — Không kiểm producer code mà chỉ stub kết quả mong muốn.**  
Một test slice với service mock chứng minh controller contract, không chứng minh service/database thật. Bổ sung unit/integration tests tại đúng tầng.

**Lỗi 15 — Dùng cố định random port 8080 trong integration test.**  
`RANDOM_PORT` chọn port khả dụng. Dùng injected WebTestClient với relative URI hoặc `@LocalServerPort`.

**Lỗi 16 — Quên cleanup state khi server test ghi dữ liệu.**  
Với server HTTP thật, handler chạy khác test thread; transaction rollback của test method không tự bao phủ transaction của server. Dùng test database cô lập và cleanup phù hợp.

## 15. Quy trình xây một WebFlux API test hiệu quả

Giả sử hợp đồng là “GET widget theo ID trả 200 + JSON nếu tồn tại, 404 nếu không có; request trace ID được echo”:

1. **Viết contract công khai**: URI, method, request headers, media types, status, response schema.
2. **Chọn phạm vi**: chỉ controller → `@WebFluxTest`; controller + server HTTP thật → `@SpringBootTest(RANDOM_PORT)`.
3. **Chuẩn bị collaborator**: `@MockitoBean` với `Mono.just(...)`/`Mono.empty()`, hoặc service thật khi test integration.
4. **Dựng request**: `get()`, `uri(...)`, `header(...)`, `accept(...)`.
5. **Kích hoạt `exchange()`** và assert status trước để lỗi dễ hiểu.
6. **Assert headers**: custom trace, Content-Type, Location/cache/security khi thuộc contract.
7. **Assert body**: JSONPath cho field quan trọng, typed DTO cho toàn object, list cho Flux hữu hạn, isEmpty cho body thật sự trống.
8. **Kiểm nhánh lỗi**: not found, malformed JSON, media type không hỗ trợ, unauthorized/forbidden theo contract.
9. **Kiểm streaming riêng**: không collect vô hạn; dùng StepVerifier và giới hạn số sự kiện.
10. **Đảm bảo lặp lại được**: dữ liệu cố định, không phụ thuộc current time, random port tĩnh hoặc network production.
11. **Đối chiếu với test ở tầng khác**: service logic và database/HTTP downstream phải có test phù hợp, không suy từ mock controller test.
12. **Chạy trên CI**: kiểm startup, codec modules, Spring Boot version, response timeout và profile phù hợp.

### Checklist trước khi commit

- [ ] Đã nêu rõ request method, URI/path/query, `Accept` và `Content-Type`.
- [ ] Có `exchange()` trước khi gọi `expect...`.
- [ ] Assert **mã HTTP cụ thể** quan trọng cho contract, không chỉ bất kỳ 2xx.
- [ ] Response headers có `valueEquals` khi phải đúng giá trị; Content-Type kiểm theo media type phù hợp.
- [ ] Body dùng JSONPath, typed DTO hoặc list đúng loại; body trống được xác minh khi contract yêu cầu.
- [ ] Error path có assertions cho 400, 404, 415 hoặc status/format tương ứng.
- [ ] Trong `@WebFluxTest`, controller thật, collaborator dùng `@MockitoBean` hoặc test bean phù hợp.
- [ ] Không nhầm mock binding với HTTP network test.
- [ ] Với `RANDOM_PORT`, không hardcode 8080, dùng client/port thực đã inject.
- [ ] Không dùng `expectBodyList` cho stream vô hạn; có chiến lược cancel/timeout.
- [ ] Spring Security, CSRF và error advice được kiểm đúng nếu thuộc phạm vi.
- [ ] Không dùng blocking call trong reactive controller.
- [ ] Không tiết lộ credential/secret trong test logs, headers hay payloads.
- [ ] Test HTTP thật có fixture cô lập và cleanup rõ với side effects.
- [ ] Có test riêng cho service, repository, transaction hoặc downstream protocol nếu đó mới là nguồn rủi ro.

**Ghi nhớ:** `WebTestClient` mô tả trọn một phép thử HTTP bằng **request builder → `exchange()` → `expectStatus()` / `expectHeader()` / `expectBody()`**. Với `@WebFluxTest`, bạn kiểm web contract nhanh mà không mở server; với `@SpringBootTest(RANDOM_PORT)`, bạn kiểm chính HTTP transport của ứng dụng. Chọn kiểu body assertion theo dạng response, và chỉ xác nhận những điều test environment thực sự chứng minh.

### Tài liệu tham khảo chính thức

- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind-to-controller/context/server, request building, status/headers/body assertions, JSON, typed response.
- [Spring Framework — WebTestClient API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html): DSL `exchange()`/`expectStatus()`/`expectHeader()`/`expectBody()`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@MockitoBean`, `@SpringBootTest(RANDOM_PORT)` và auto-configured test clients.
- [Spring Boot 3.5 API — @WebFluxTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html): WebFlux test slice và WebTestClient.
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): request mappings, content negotiation, response bodies.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time và kiểm reactive publisher.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): mock users, CSRF và WebTestClient security configurers.
