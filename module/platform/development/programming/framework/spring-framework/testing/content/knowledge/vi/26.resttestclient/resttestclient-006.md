# Xác nhận status, header, DTO và JSON

Khi kiểm thử một REST API, response HTTP cần được xác nhận ở nhiều lớp: status code cho biết kết quả xử lý, header mô tả response, còn body mang dữ liệu mà client sử dụng. Một response `200 OK` vẫn có thể sai nếu `Content-Type` không đúng, thiếu header quan trọng hoặc JSON không thể chuyển thành DTO mà client mong đợi.

Spring Framework 7.0 giới thiệu `RestTestClient`, một HTTP client dành cho kiểm thử ứng dụng server. Client này dùng `RestClient` để thực hiện request và bổ sung API fluent để xác nhận response. Có thể bind nó vào controller hoặc `WebApplicationContext` để kiểm thử Spring MVC bằng request/response giả lập, hoặc kết nối đến server đang chạy để thực hiện kiểm thử end-to-end.

`RestTestClient` hỗ trợ hai phong cách assertion chính: chuỗi expectation tích hợp sau `exchange()` và AssertJ integration. Trong bài học này, ta tập trung vào phong cách expectation vì nó thể hiện rõ thứ tự kiểm tra status, header và body; sau đó chuyển response thành DTO hoặc kiểu generic khi cần.

## 1. `RestTestClient` là gì và dùng khi nào?

`RestTestClient` nằm trong package `org.springframework.test.web.servlet.client`. Nó cung cấp cách gửi request HTTP và kiểm tra response cho ứng dụng Spring MVC. API tạo request gần với `RestClient`; điểm khác biệt xuất hiện sau lời gọi `exchange()`, khi `RestTestClient` cung cấp các phương thức `expectStatus()`, `expectHeader()` và `expectBody()`.

Các khái niệm chính:

| Thành phần | Vai trò |
| --- | --- |
| `RestTestClient` | Tạo request và cung cấp API xác nhận response. |
| `RestTestClient.bindToController(...)` | Kiểm thử controller được chọn bằng MockMvc, không cần server thật. |
| `RestTestClient.bindToApplicationContext(...)` | Nạp cấu hình Spring MVC từ `WebApplicationContext` và xử lý request bằng MockMvc. |
| `RestTestClient.bindToRouterFunction(...)` | Kiểm thử functional endpoint được khai báo bằng `RouterFunction`. |
| `RestTestClient.bindToServer()` | Kết nối đến HTTP server đang chạy để kiểm thử end-to-end. |
| `exchange()` | Gửi request và bắt đầu giai đoạn xác nhận response. |
| `expectStatus()`, `expectHeader()`, `expectBody()` | Xác nhận status, header và nội dung response. |

`RestTestClient` được giới thiệu trong Spring Framework 7.0. Project cần dùng Spring Test tương ứng và đồng bộ phiên bản với Spring Framework đang sử dụng. Đây là API của Spring MVC Test; nếu đang kiểm thử ứng dụng reactive WebFlux, hãy xem `WebTestClient`.

Không nhầm `RestTestClient` với `RestClient`. `RestClient` là HTTP client dùng trong ứng dụng để gọi dịch vụ bên ngoài. `RestTestClient` là công cụ kiểm thử server: nó gửi request đến ứng dụng đang được kiểm thử rồi xác nhận response mà ứng dụng trả về.

## 2. Chọn cách khởi tạo client

Trước khi viết assertion, cần xác định request sẽ được gửi đến loại server nào. Cách bind quyết định phạm vi kiểm thử và các thành phần Spring tham gia.

### Bind trực tiếp vào controller

Khi chỉ cần kiểm tra một hoặc một vài controller, có thể truyền controller instance trực tiếp:

```java
import org.springframework.test.web.servlet.client.RestTestClient;

RestTestClient client = RestTestClient
        .bindToController(new PersonController())
        .build();
```

Setup này sử dụng mock request và response của MockMvc, không khởi động HTTP server. Nó phù hợp để kiểm tra mapping, binding và response của controller được chọn. Dependency của controller và các thành phần MVC bổ sung cần được cung cấp theo cấu hình standalone tương ứng.

### Bind vào `WebApplicationContext`

Khi muốn kiểm tra controller cùng cấu hình Spring MVC đã nạp, hãy bind vào `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(WebConfig.class)
class PersonControllerContextTest {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient
                .bindToApplicationContext(context)
                .build();
    }
}
```

`@SpringJUnitConfig` nạp cấu hình Spring cho test. `bindToApplicationContext(...)` sử dụng web context đó để xử lý request bằng hạ tầng Spring MVC giả lập. Cách này phù hợp khi cần xác nhận component scan, controller, converter, controller advice, interceptor và các bean đã được cấu hình trong context.

### Bind vào `RouterFunction`

Với Spring MVC functional endpoints, có thể bind trực tiếp vào một hoặc nhiều `RouterFunction`:

```java
RestTestClient client = RestTestClient
        .bindToRouterFunction(route)
        .build();
```

Setup này cũng dùng mock request/response và không cần server đang chạy. Nó hữu ích khi ứng dụng khai báo route bằng functional style thay vì annotation controller.

### Bind vào server đang chạy

Khi cần kiểm tra request qua HTTP stack thật, kết nối đến server đang chạy:

```java
RestTestClient client = RestTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

Đây là lựa chọn cho kiểm thử end-to-end. Request đi qua HTTP client và server thực tế, vì vậy có thể kiểm tra thêm các yếu tố như cổng mạng, servlet container, filter chain và cấu hình server. Test cần khởi động server trước khi thực hiện request.

### Bind vào `MockMvc` đã tạo sẵn

Nếu project đã có `MockMvc`, có thể đưa instance đó vào:

```java
RestTestClient client = RestTestClient
        .bindTo(mockMvc)
        .build();
```

Cách này hữu ích khi `MockMvc` đã được tùy chỉnh với các builder hoặc cấu hình riêng. `RestTestClient` sử dụng MockMvc đó làm server xử lý request.

## 3. Cấu trúc request và response workflow

Request API của `RestTestClient` có phong cách gần với `RestClient`. Ta chọn HTTP method, URI, header, content type và body nếu cần; sau đó gọi `exchange()` để gửi request.

```text
RestTestClient
      |
      v
client.get() / post() / put() / delete()
      |
      v
uri(...), accept(...), header(...), body(...)
      |
      v
exchange()
      |
      v
ResponseSpec
      |
      +--> expectStatus()
      |
      +--> expectHeader()
      |
      +--> expectBody()
      |       |
      |       +--> JSON / JSONPath
      |       +--> DTO / generic type
      |       +--> empty body
      |
      v
Kết thúc assertion hoặc lấy ExchangeResult
```

Ví dụ request GET:

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectBody();
```

`accept(...)` khai báo kiểu response mà client mong muốn. `exchange()` gửi request và trả về `ResponseSpec`, từ đó ta tiếp tục kiểm tra response.

## 4. Xác nhận HTTP status

Status code thể hiện kết quả của request theo hợp đồng HTTP. `RestTestClient` cung cấp `expectStatus()` với các matcher theo nhóm và theo mã cụ thể.

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk();
```

Một số matcher thường dùng:

| Matcher | Status |
| --- | --- |
| `isOk()` | 200 OK |
| `isCreated()` | 201 Created |
| `isAccepted()` | 202 Accepted |
| `isNoContent()` | 204 No Content |
| `isBadRequest()` | 400 Bad Request |
| `isUnauthorized()` | 401 Unauthorized |
| `isForbidden()` | 403 Forbidden |
| `isNotFound()` | 404 Not Found |
| `is3xxRedirection()` | Bất kỳ status thuộc nhóm 3xx |
| `is4xxClientError()` | Bất kỳ status thuộc nhóm 4xx |
| `is5xxServerError()` | Bất kỳ status thuộc nhóm 5xx |

Khi cần một status cụ thể không có matcher riêng, dùng `isEqualTo(...)`:

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isEqualTo(200);
```

Nên chọn mức kiểm tra phù hợp với hợp đồng. Nếu API yêu cầu `201 Created` sau khi tạo tài nguyên, `isCreated()` thể hiện rõ hơn `is2xxSuccessful()`. Nếu chỉ cần xác nhận response thuộc nhóm thành công, matcher theo nhóm có thể đủ.

### Kiểm tra lỗi HTTP

Không chỉ kiểm tra happy path. Có thể xác nhận status cho tài nguyên không tồn tại:

```java
client.get()
        .uri("/api/persons/999")
        .exchange()
        .expectStatus().isNotFound();
```

Sau khi xác nhận status, có thể tiếp tục kiểm tra error body nếu API công bố JSON error response:

```java
client.get()
        .uri("/api/persons/999")
        .exchange()
        .expectStatus().isNotFound()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(ApiError.class)
        .isEqualTo(new ApiError("PERSON_NOT_FOUND", "Person 999 was not found"));
```

## 5. Xác nhận response headers

Header cung cấp metadata về response, chẳng hạn `Content-Type`, `Location`, `Cache-Control`, `ETag` hoặc header riêng của ứng dụng. Dùng `expectHeader()` sau `exchange()` để kiểm tra.

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectHeader().exists("X-Request-Id")
        .expectHeader().valueEquals("X-API-Version", "v1");
```

Các matcher thường dùng:

| Matcher | Ý nghĩa |
| --- | --- |
| `contentType(MediaType)` | So sánh `Content-Type` với giá trị cụ thể. |
| `contentTypeCompatibleWith(MediaType)` | Kiểm tra media type tương thích, cho phép khác biệt về parameter như charset. |
| `exists(name)` | Header có tồn tại. |
| `doesNotExist(name)` | Header không tồn tại. |
| `valueEquals(name, values...)` | So sánh giá trị header với giá trị mong đợi. |
| `valueEquals(name, long)` | So sánh giá trị header dạng số. |
| `valueMatches(name, pattern)` | So sánh giá trị header đầu tiên theo regular expression. |
| `location(uri)` | Kiểm tra header `Location`. |
| `contentLength(length)` | Kiểm tra `Content-Length`. |

### `contentType` và `contentTypeCompatibleWith`

Hai matcher này khác nhau ở mức so sánh:

```java
.expectHeader().contentType(MediaType.APPLICATION_JSON)
```

kiểm tra `Content-Type` bằng giá trị mong đợi. Trong khi đó:

```java
.expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
```

kiểm tra media type tương thích. Ví dụ response có thể khai báo `application/json;charset=UTF-8`; trong trường hợp không cần ràng buộc parameter, matcher compatible thường phù hợp hơn.

### Kiểm tra header Location khi tạo tài nguyên

API tạo tài nguyên thường trả về `201 Created` và `Location` trỏ đến tài nguyên mới:

```java
client.post()
        .uri("/api/persons")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new CreatePersonRequest("Lan"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().location("/api/persons/42");
```

Test xác nhận cả kết quả tạo tài nguyên và URL client có thể dùng để truy cập tài nguyên đó. Nếu ứng dụng trả absolute URI thay vì relative URI, expected value cần khớp với cấu hình thực tế.

## 6. Chuyển response body thành DTO

Khi body JSON đại diện cho một object cụ thể, dùng `expectBody(Class<T>)` để deserialize thành DTO. Sau đó có thể so sánh object với giá trị mong đợi.

DTO:

```java
public record PersonResponse(long id, String name, String status) {
}
```

Test:

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(PersonResponse.class)
        .isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"));
```

`expectBody(PersonResponse.class)` đọc body và chuyển nó thành một instance `PersonResponse`. `isEqualTo(...)` so sánh instance vừa chuyển đổi với object mong đợi. Record phù hợp với cách kiểm tra này vì record cung cấp equality theo giá trị. Với class thông thường không override `equals()`, có thể dùng `value(...)` để kiểm tra các thuộc tính.

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(PersonResponse.class)
        .value(person -> {
            assertThat(person.id()).isEqualTo(1L);
            assertThat(person.name()).isEqualTo("Lan");
            assertThat(person.status()).isEqualTo("ACTIVE");
        });
```

`value(...)` nhận một `Consumer` để thực hiện assertion tùy chỉnh trên object đã deserialize. Có thể dùng nó khi chỉ cần kiểm tra một số trường hoặc cần xác nhận quan hệ giữa các thuộc tính.

## 7. Chuyển body thành danh sách hoặc kiểu generic

Khi response là JSON array hoặc chứa kiểu generic, chỉ truyền raw class có thể làm mất thông tin kiểu phần tử. Hãy dùng overload nhận `ParameterizedTypeReference`.

Ví dụ response là danh sách người dùng:

```json
[
  {"id": 1, "name": "Lan", "status": "ACTIVE"},
  {"id": 2, "name": "Minh", "status": "INACTIVE"}
]
```

Test chuyển thành `List<PersonResponse>`:

```java
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<PersonResponse>> peopleType =
        new ParameterizedTypeReference<>() {
        };

client.get()
        .uri("/api/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody(peopleType)
        .isEqualTo(List.of(
                new PersonResponse(1L, "Lan", "ACTIVE"),
                new PersonResponse(2L, "Minh", "INACTIVE")
        ));
```

`ParameterizedTypeReference<List<PersonResponse>>` giữ thông tin generic về kiểu phần tử. Nếu dùng `List.class`, JSON mapper có thể chỉ tạo danh sách các map thay vì `PersonResponse`.

Với response generic lồng nhau, áp dụng tương tự:

```java
public record PageResponse<T>(int page, int size, List<T> content) {
}

ParameterizedTypeReference<PageResponse<PersonResponse>> pageType =
        new ParameterizedTypeReference<>() {
        };

client.get()
        .uri("/api/persons?page=0&size=2")
        .exchange()
        .expectStatus().isOk()
        .expectBody(pageType)
        .value(page -> {
            assertThat(page.page()).isZero();
            assertThat(page.size()).isEqualTo(2);
            assertThat(page.content()).hasSize(2);
            assertThat(page.content().get(0).name()).isEqualTo("Lan");
        });
```

Kiểu đích cần đầy đủ `PageResponse<PersonResponse>`, không chỉ `PageResponse.class`. Điều này cho phép mapper chuyển các phần tử `content` thành `PersonResponse`.

## 8. Kiểm tra JSON thô bằng JSONAssert và JSONPath

Không phải test nào cũng cần deserialize body thành DTO. Nếu chỉ muốn xác nhận cấu trúc JSON hoặc một vài giá trị, có thể dùng `expectBody()` không truyền kiểu đích. API này cho phép kiểm tra raw content.

### So sánh JSON

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {
                  "id": 1,
                  "name": "Lan",
                  "status": "ACTIVE"
                }
                """);
```

Matcher `.json(...)` so sánh nội dung JSON theo cấu trúc, thay vì yêu cầu chuỗi response phải giống hệt từng byte. Cần có JSONAssert trên test classpath để sử dụng JSON assertion này.

### Trích xuất giá trị bằng JSONPath

Khi chỉ quan tâm một vài trường:

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(1)
        .jsonPath("$.name").isEqualTo("Lan")
        .jsonPath("$.status").isEqualTo("ACTIVE");
```

Một số JSONPath thường gặp:

| JSONPath | Nội dung |
| --- | --- |
| `$.id` | Trường `id` ở cấp gốc. |
| `$.address.city` | Thành phố trong object `address`. |
| `$[0].name` | Tên của phần tử đầu tiên trong JSON array. |
| `$.items[1].id` | ID của phần tử thứ hai trong `items`. |
| `$.items[*].name` | Tên của tất cả phần tử trong `items`. |

JSONPath phù hợp với assertion chọn lọc. Typed conversion phù hợp khi cần xác nhận toàn bộ body có thể được đọc thành DTO hoặc generic type.

## 9. Dùng `expectAll(...)` để gom nhiều assertion

Khi gọi nhiều `expect...` liên tiếp, một assertion thất bại có thể làm chuỗi dừng trước khi các assertion sau được thực hiện. `expectAll(...)` cho phép chạy tất cả các expectation được truyền vào và tổng hợp lỗi.

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectAll(
                response -> response.expectStatus().isOk(),
                response -> response.expectHeader()
                        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                response -> response.expectHeader().exists("X-Request-Id"),
                response -> response.expectBody(PersonResponse.class)
                        .isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"))
        );
```

`expectAll(...)` tương tự soft assertions của AssertJ hoặc `assertAll(...)` trong JUnit Jupiter. Nó hữu ích khi muốn một lần chạy test cho biết nhiều điểm không khớp, thay vì phải sửa từng lỗi theo thứ tự assertion đầu tiên.

## 10. Response không có body

Một số endpoint trả `204 No Content`, hoặc trả status thành công mà không có body. Khi đó không nên cố deserialize thành DTO.

Để xác nhận body rỗng:

```java
client.delete()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
```

Nếu không cần kiểm tra nội dung response và chỉ muốn giải phóng body, có thể dùng `expectBody(Void.class)`:

```java
client.delete()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody(Void.class);
```

Tiêu thụ body là điều cần thiết trong các test có bật leak detection cho pooled buffers. Nếu không đọc hoặc giải phóng response body, công cụ phát hiện rò rỉ buffer có thể báo lỗi.

## 11. Lấy `EntityExchangeResult` để kiểm tra tùy chỉnh

Khi các matcher tích hợp chưa đủ, có thể kết thúc chuỗi expectation và lấy `EntityExchangeResult<T>`:

```java
EntityExchangeResult<PersonResponse> result = client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(PersonResponse.class)
        .returnResult();

PersonResponse person = result.getResponseBody();
HttpHeaders responseHeaders = result.getResponseHeaders();

assertThat(person).isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"));
assertThat(responseHeaders.getFirst("X-API-Version")).isEqualTo("v1");
```

`returnResult()` trả về kết quả exchange cùng body đã được chuyển đổi. Có thể lấy DTO, response headers và thông tin request/response để thực hiện assertion riêng. Với kiểu generic, overload `returnResult(ParameterizedTypeReference<T>)` giữ thông tin tham số kiểu:

```java
EntityExchangeResult<List<PersonResponse>> result = client.get()
        .uri("/api/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody(peopleType)
        .returnResult();

List<PersonResponse> people = result.getResponseBody();
assertThat(people).hasSize(2);
```

Khi cần raw content, `ResponseSpec.returnResult()` không tham số trả về `ExchangeResult` với body thô. Hãy chọn kiểu kết quả phù hợp để tránh phải deserialize lại thủ công.

## 12. Gửi request có body và xác nhận response

`RestTestClient` có API tạo request tương tự `RestClient`. Với POST, PUT hoặc PATCH, có thể khai báo content type và body object:

```java
public record CreatePersonRequest(String name) {
}

client.post()
        .uri("/api/persons")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new CreatePersonRequest("Lan"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(PersonResponse.class)
        .value(person -> {
            assertThat(person.id()).isPositive();
            assertThat(person.name()).isEqualTo("Lan");
            assertThat(person.status()).isEqualTo("ACTIVE");
        });
```

`body(...)` sử dụng message conversion để ghi object thành request body. `contentType(...)` khai báo định dạng gửi đi; `accept(...)` khai báo định dạng response mong muốn. Sau `exchange()`, ta xác nhận status, header và body giống như với GET.

Nếu cần gửi JSON string trực tiếp, có thể truyền chuỗi vào `body(...)` và đặt `contentType(MediaType.APPLICATION_JSON)`. Với DTO, truyền object thường giúp test gần với cách client thực tế sử dụng HTTP message conversion.

## 13. Kiểm thử với server đang chạy

Các setup bind vào controller hoặc application context sử dụng mock request/response. Chúng rất phù hợp cho kiểm thử MVC nhanh, nhưng không xác nhận việc mở cổng, truyền dữ liệu qua socket hoặc cấu hình servlet container thật.

Để kiểm tra end-to-end, có thể khởi động ứng dụng trên cổng ngẫu nhiên bằng Spring Boot:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PersonHttpIntegrationTest {

    @LocalServerPort
    int port;

    RestTestClient client;

    @BeforeEach
    void setUp() {
        client = RestTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void shouldReturnPersonOverHttp() {
        client.get()
                .uri("/api/persons/1")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody(PersonResponse.class)
                .isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"));
    }
}
```

Trong setup này, server phải được khởi động bởi Spring Boot trước khi request được gửi. `RestTestClient.bindToServer()` tạo HTTP client thật và `.baseUrl(...)` chỉ định địa chỉ ứng dụng. Test xác nhận response đi qua đường truyền HTTP của server đang chạy.

## 14. Phân biệt `RestTestClient`, `MockMvc` và `WebTestClient`

Các công cụ này có thể cùng được dùng để kiểm tra HTTP nhưng phục vụ những kiểu ứng dụng và cách thiết lập khác nhau:

| Công cụ | Mô hình | Khi phù hợp |
| --- | --- | --- |
| `MockMvc` | API kiểm thử servlet MVC với request/response giả lập. | Kiểm tra Spring MVC và cần các API matcher của MockMvc. |
| `RestTestClient` | Client dựa trên `RestClient`, có assertion facade; có thể bind MockMvc hoặc server thật. | Muốn dùng phong cách HTTP client nhất quán để kiểm tra status, header và body của ứng dụng server. |
| `WebTestClient` | Client kiểm thử reactive, thường dùng với WebFlux; cũng có thể kết nối một số kiểu server khác. | Kiểm thử WebFlux hoặc khi cần API reactive testing. |

`RestTestClient` không thay thế mọi khả năng của `MockMvc`. Khi bind với MockMvc, nó cung cấp góc nhìn HTTP client về response. Nếu cần assertion đặc thù của server-side MockMvc như model, handler hoặc request attribute, có thể tiếp tục dùng trực tiếp `MockMvc` và `MvcResult`.

`RestTestClient` cũng không phải công cụ giả lập server đích cho một `RestClient` outbound của ứng dụng. Khi cần kiểm tra code ứng dụng gọi HTTP service bên ngoài, hãy dùng công cụ mock server/client phù hợp như `MockRestServiceServer` hoặc một HTTP mock server.

## 15. Lỗi thường gặp khi xác nhận response

**Dùng phiên bản Spring chưa có `RestTestClient`.**

API này được giới thiệu trong Spring Framework 7.0. Nếu project dùng Spring Framework 6.x, package `org.springframework.test.web.servlet.client.RestTestClient` chưa có. Hãy kiểm tra dependency management và dùng bộ phiên bản Spring đồng bộ.

**Quên gọi `exchange()`.**

Các phương thức `expectStatus()`, `expectHeader()` và `expectBody()` thuộc response workflow sau khi request được gửi. Cần gọi `exchange()` trước khi xác nhận response.

**Kiểm tra status nhưng bỏ qua header quan trọng.**

Status thành công không đảm bảo content type hoặc location đúng. Với endpoint JSON, hãy kiểm tra `Content-Type`; với endpoint tạo tài nguyên, cân nhắc kiểm tra `Location`.

**So sánh `Content-Type` quá chặt.**

Response có thể chứa parameter như charset. Dùng `contentTypeCompatibleWith(...)` khi chỉ cần xác nhận media type tương thích; dùng `contentType(...)` khi toàn bộ giá trị header là một phần của hợp đồng.

**Deserialize collection bằng raw `List.class`.**

Raw class làm mất kiểu phần tử. Dùng `ParameterizedTypeReference<List<PersonResponse>>` để chuyển từng phần tử thành DTO đúng kiểu.

**Dùng `isEqualTo(...)` với DTO không có equality theo giá trị.**

Hai instance class thông thường có cùng dữ liệu nhưng không override `equals()` có thể vẫn bị xem là khác nhau. Dùng record, triển khai equality phù hợp hoặc dùng `value(...)`/`consumeWith(...)` để kiểm tra thuộc tính.

**Không tiêu thụ body.**

Nếu test chạy với leak detection cho pooled buffers, cần gọi `expectBody(...)`, `expectBody().isEmpty()` hoặc cách tiêu thụ body phù hợp. Không để response body bị bỏ quên.

**Nhầm mock server setup với end-to-end test.**

`bindToController(...)` và `bindToApplicationContext(...)` xử lý request bằng MockMvc, không khởi động HTTP server thật. Dùng `bindToServer()` khi cần kiểm tra mạng và server đang chạy.

## 16. Quy trình kiểm thử status, header, DTO và JSON

Một bài kiểm thử response có thể được tổ chức theo trình tự:

1. Chọn setup phù hợp: controller, application context, router function, MockMvc có sẵn hoặc server thật.
2. Tạo `RestTestClient` và cấu hình base URL hoặc default header nếu cần.
3. Tạo request với HTTP method, URI, header, content type và body phù hợp.
4. Gọi `exchange()` để gửi request.
5. Xác nhận status bằng `expectStatus()`.
6. Xác nhận content type, location và header nghiệp vụ bằng `expectHeader()`.
7. Chuyển body thành DTO bằng `expectBody(Dto.class)` hoặc generic type bằng `expectBody(ParameterizedTypeReference)`.
8. Nếu cần kiểm tra JSON thô, dùng `expectBody().json(...)` hoặc `jsonPath(...)`.
9. Dùng `expectAll(...)` khi muốn thực hiện nhiều assertion ngay cả khi một assertion thất bại.
10. Lấy `EntityExchangeResult` khi cần kiểm tra dữ liệu exchange theo cách tùy chỉnh.

Ví dụ tổng hợp:

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectAll(
                response -> response.expectStatus().isOk(),
                response -> response.expectHeader()
                        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                response -> response.expectHeader().exists("X-Request-Id"),
                response -> response.expectBody(PersonResponse.class)
                        .isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"))
        );
```

Đoạn test xác nhận đồng thời status, content type, một header riêng và DTO response. Khi một trong các điều kiện không đúng, kết quả assertion cho biết phần nào của hợp đồng HTTP đã bị vi phạm.

## Kết luận

`RestTestClient` trong Spring Framework 7.0+ cung cấp API HTTP client để kiểm thử response của ứng dụng server. Sau `exchange()`, dùng `expectStatus()` để xác nhận mã HTTP, `expectHeader()` để xác nhận metadata và `expectBody(...)` để chuyển response thành DTO hoặc generic type. Với JSON thô, `expectBody().json(...)` và `jsonPath(...)` cho phép kiểm tra cấu trúc và giá trị cụ thể.

Chọn setup theo phạm vi cần kiểm tra: bind controller hoặc application context để kiểm thử MVC bằng MockMvc, bind server để kiểm thử end-to-end. Kết hợp status, header và body giúp xác nhận hợp đồng HTTP đầy đủ hơn việc chỉ kiểm tra request có thành công hay không.

Tài liệu chính thức: [Spring Framework Reference — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html).
