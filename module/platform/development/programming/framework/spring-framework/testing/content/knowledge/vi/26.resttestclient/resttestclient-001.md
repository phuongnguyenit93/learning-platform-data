# RestTestClient từ Spring Framework 7 và quan hệ với RestClient

## 1. RestTestClient giải quyết nhu cầu gì?

Spring Framework 7.0 bổ sung `RestTestClient`, một HTTP client dành cho kiểm thử ứng dụng server. API này dùng `RestClient` ở bên dưới để gửi request, đồng thời cung cấp các matcher để xác nhận status, header và body của response.

Điểm đáng chú ý là `RestTestClient` có thể chạy theo hai cách:

- Gửi request HTTP đến một server đang chạy để kiểm thử end-to-end.
- Dùng hạ tầng `MockMvc` để kiểm thử Spring MVC mà không cần khởi động server thật.

Nhờ đó, người đã quen với cách tạo request của `RestClient` có thể dùng gần như cùng cách viết để kiểm thử endpoint. Phần khác biệt chính nằm sau lời gọi `exchange()`: `RestTestClient` chuyển sang chuỗi assertion dành cho test.

`RestTestClient` thuộc Spring Test và có từ Spring Framework 7.0. Nó không có trong Spring Framework 6.x, kể cả khi dự án đã dùng `RestClient` từ Spring Framework 6.1. Vì vậy, trước khi sử dụng cần xác nhận phiên bản Spring Framework của dự án.

## 2. Quan hệ giữa RestClient và RestTestClient

`RestClient` là HTTP client đồng bộ dùng trong ứng dụng để gọi một REST API khác. Nó cung cấp API fluent để thiết lập request, gửi request và đọc response. `RestTestClient` cũng thực hiện request theo mô hình đồng bộ, nhưng mục tiêu là kiểm thử một ứng dụng server và xác nhận response bằng các assertion.

Spring mô tả hai API có cùng cách chuẩn bị request cho đến lời gọi `exchange()`. Sau điểm đó, cách xử lý response khác nhau:

| Nội dung | `RestClient` | `RestTestClient` |
|---|---|---|
| Mục đích | Gọi HTTP API từ mã ứng dụng | Gửi HTTP request để kiểm thử server và xác nhận response |
| Nền tảng | HTTP client đồng bộ của Spring | Dùng `RestClient` để thực hiện request, bổ sung facade kiểm thử |
| Chuẩn bị request | Method, URI, header, cookie, body, content type | Có cùng phong cách chuẩn bị request đến `exchange()` |
| Xử lý response | `retrieve()`, đọc body hoặc chuyển thành `ResponseEntity`; cũng có thể dùng callback `exchange(...)` | `exchange()` trả về response specification để gọi `expectStatus()`, `expectHeader()`, `expectBody()` và các matcher khác |
| Hạ tầng kiểm thử | Thường kết hợp mock web server hoặc `MockRestServiceServer` khi kiểm thử mã gọi API ngoài | Có thể bind vào controller, application context, router function hoặc server đang chạy |
| Nơi sử dụng | Mã ứng dụng và adapter gọi dịch vụ | Test source, thường dùng với JUnit |

Có thể hình dung `RestTestClient` như một lớp kiểm thử đặt trên cách gửi request của `RestClient`. Nó không thay thế `RestClient` trong mã nghiệp vụ và cũng không phải một biến thể reactive của `WebClient`.

Ví dụ `RestClient` được dùng trong ứng dụng:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://inventory.example.test")
                .build();
    }

    InventoryItem findItem(long id) {
        return restClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

Đây là mã ứng dụng gọi một hệ thống khác. Test cho `InventoryGateway` cần giả lập response từ hệ thống inventory, thường bằng `MockRestServiceServer`, MockWebServer hoặc WireMock. `RestTestClient` chủ yếu được dùng theo chiều ngược lại: gửi request vào endpoint của ứng dụng server để kiểm tra hành vi endpoint đó.

## 3. Phiên bản và dependency

`RestTestClient` được cung cấp trong artifact `spring-test`, với package:

```java
import org.springframework.test.web.servlet.client.RestTestClient;
```

Với Gradle và Spring Framework BOM hoặc dependency management đã quản lý phiên bản:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
}
```

Nếu dự án dùng Spring Boot, dependency `spring-boot-starter-test` thường đã đưa `spring-test` vào test classpath. Tuy nhiên, phải dùng phiên bản Spring Framework 7.0 trở lên để có `RestTestClient`; chỉ thêm `spring-test` 6.x không làm API này xuất hiện.

Các kiểu bind mock của `RestTestClient` dựa trên Spring MVC và MockMvc. Vì vậy, khi dùng `bindToController`, `bindToApplicationContext` hoặc `bindToRouterFunction`, test cần có các thành phần Spring MVC tương ứng trên classpath. Để gửi request đến server đang chạy bằng `bindToServer`, client sử dụng hạ tầng HTTP client đồng bộ.

## 4. Chọn cách bind phù hợp

Trước khi tạo client, cần xác định test muốn đi qua hạ tầng nào. `RestTestClient` cung cấp các cách bind chính sau:

| Cách bind | Khi nên dùng | Đặc điểm |
|---|---|---|
| `bindToController(...)` | Kiểm thử một hoặc vài controller cụ thể | Dùng mock request/response, không cần server; thích hợp khi controller có ít phụ thuộc hoặc có thể cung cấp phụ thuộc trong test. |
| `bindToApplicationContext(...)` | Kiểm thử cấu hình Spring MVC và nhiều thành phần cùng tham gia xử lý request | Dùng `WebApplicationContext`, controller, MVC infrastructure và cấu hình đã nạp. |
| `bindToRouterFunction(...)` | Kiểm thử functional endpoint theo mô hình router function của Spring MVC | Dùng mock request/response để gọi route function. |
| `bindToServer()` | Kiểm thử qua HTTP với ứng dụng đang chạy | Cần server có thể truy cập; phù hợp với kiểm thử tích hợp hoặc end-to-end. |

### Bind trực tiếp vào controller

Đây là cách ngắn nhất để kiểm thử một controller độc lập:

```java
RestTestClient client = RestTestClient
        .bindToController(new PersonController())
        .build();
```

`bindToController(...)` tạo môi trường MockMvc cho controller được cung cấp. Không có TCP connection đến một server thật. Nếu controller cần service, repository hoặc bean khác, hãy cung cấp chúng qua constructor hoặc dùng `bindToApplicationContext(...)` để Spring tạo và inject dependency.

### Bind vào WebApplicationContext

Khi cần kiểm thử cấu hình MVC, interceptor, controller advice, filter được tích hợp hoặc nhiều controller, hãy bind vào `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(WebConfig.class)
class PersonContextTests {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient.bindToApplicationContext(context).build();
    }
}
```

`WebConfig` là cấu hình ứng dụng cung cấp controller và hạ tầng MVC cho test. Spring Test nạp cấu hình và đưa `WebApplicationContext` vào phương thức setup. Request sau đó được xử lý qua MockMvc với cấu hình đã nạp.

### Bind vào router function

Với functional endpoint trên Servlet stack, có thể bind trực tiếp vào `RouterFunction`:

```java
import org.springframework.web.servlet.function.RouterFunction;

RouterFunction<?> routes = ...;

RestTestClient client = RestTestClient
        .bindToRouterFunction(routes)
        .build();
```

`routes` là router function của ứng dụng. Cách này hữu ích khi endpoint được khai báo bằng `RouterFunctions.route(...)` thay vì `@RestController`.

### Bind vào server đang chạy

Khi cần xác nhận cả HTTP server, cấu hình runtime, filter và network path, dùng `bindToServer()`:

```java
RestTestClient client = RestTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

Ở chế độ này, server phải được khởi động trước khi test gửi request. Base URL cần chứa đúng host và port của server hiện tại. Trong test dùng port ngẫu nhiên, hãy lấy port do môi trường test cấp thay vì ghi cứng `8080`.

## 5. Viết test với request API quen thuộc

Ví dụ sau dùng controller đơn giản trả về một `Person`:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

record Person(long id, String name) {
}

@RestController
class PersonController {

    @GetMapping("/persons/{id}")
    Person findById(@PathVariable long id) {
        return new Person(id, "Jane");
    }
}
```

Test có thể gửi request và xác nhận response như sau:

```java
import static org.springframework.http.MediaType.APPLICATION_JSON;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.client.RestTestClient;

import static org.springframework.test.web.servlet.client.RestTestClient.bindToController;

class PersonControllerTests {

    private final RestTestClient client = bindToController(new PersonController()).build();

    @Test
    void returnsPersonAsJson() {
        client.get()
                .uri("/persons/{id}", 7)
                .accept(APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON)
                .expectBody(Person.class)
                .isEqualTo(new Person(7, "Jane"));
    }
}
```

Request được chuẩn bị bằng `get()`, `uri(...)` và `accept(...)` theo cùng phong cách của `RestClient`. Sau `exchange()`, test dùng các assertion của `RestTestClient` để xác nhận status, content type và object đã giải mã từ response body. Với ví dụ JSON này, Jackson cần có trên classpath để Spring MVC chuyển đổi object thành JSON.

## 6. Các kiểu assertion trên response

Sau `exchange()`, `RestTestClient` cung cấp một chuỗi expectation để test diễn đạt hợp đồng HTTP.

### Kiểm tra status và header

```java
client.get()
        .uri("/persons/7")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON);
```

Các matcher status có thể xác nhận mã cụ thể hoặc nhóm trạng thái như `is2xxSuccessful()`, `is4xxClientError()` và `is5xxServerError()`. Header matcher có thể xác nhận content type, giá trị header, cache control và các thuộc tính response khác.

### Kiểm tra nhiều điều kiện bằng `expectAll`

Chuỗi matcher thông thường dừng ngay tại assertion đầu tiên thất bại. Khi muốn thu thập nhiều lỗi trong cùng một response, dùng `expectAll(...)`:

```java
client.get().uri("/persons/7")
        .exchange()
        .expectAll(
                response -> response.expectStatus().isOk(),
                response -> response.expectHeader()
                        .contentTypeCompatibleWith(APPLICATION_JSON),
                response -> response.expectHeader().exists("X-Correlation-Id")
        );
```

`expectAll(...)` áp dụng tất cả expectation được truyền vào, kể cả khi một expectation đã ném lỗi. Nếu có nhiều lỗi, chúng được tổng hợp trong `AssertionError` với các exception chi tiết được đính kèm. Cách này tương tự soft assertion hoặc `assertAll()` của JUnit Jupiter.

### Đọc body thành object

Khi response có một object, dùng `expectBody(Class<T>)`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

client.get().uri("/persons/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .value(person -> {
            assertEquals(7L, person.id());
            assertEquals("Jane", person.name());
        });
```

`BodySpec` hỗ trợ các cách như `isEqualTo(...)`, `value(...)`, `consumeWith(...)` và `returnResult()`. Khi body là kiểu generic, ví dụ `List<Person>`, dùng overload nhận `ParameterizedTypeReference` để giữ thông tin generic khi giải mã.

### Kiểm tra raw JSON và JSONPath

Khi muốn xác nhận JSON trực tiếp mà không tạo DTO, dùng `expectBody()`:

```java
client.get().uri("/persons/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {"id": 7, "name": "Jane"}
                """);
```

Có thể kiểm tra một phần body bằng JSONPath:

```java
client.get().uri("/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$[0].name").isEqualTo("Jane")
        .jsonPath("$[1].name").isEqualTo("Jason");
```

Các assertion JSON cần thư viện so sánh JSON phù hợp trên test classpath, chẳng hạn JSONassert hoặc JsonUnit. Khi test có bật leak detection cho pooled buffers, cần tiêu thụ response body bằng `expectBody(...)` hoặc một thao tác tương ứng; chỉ kiểm tra status rồi bỏ body có thể khiến báo cáo phát hiện buffer chưa được giải phóng.

### Response không có body

Nếu endpoint trả `204 No Content` hoặc một response không có nội dung, xác nhận body rỗng:

```java
client.delete().uri("/persons/7")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
```

Nếu không cần kiểm tra body nhưng vẫn cần tiêu thụ response, có thể dùng `expectBody(Void.class)`.

## 7. Dùng AssertJ với RestTestClient

Ngoài matcher tích hợp, Spring cung cấp `RestTestClientResponse` để dùng AssertJ. Có thể chuyển `ResponseSpec` hoặc `ExchangeResult` sang assertion object:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.test.web.servlet.client.assertj.RestTestClientResponse;

RestTestClient.ResponseSpec spec = client.get()
        .uri("/persons/7")
        .exchange();

RestTestClientResponse response = RestTestClientResponse.from(spec);

assertThat(response).hasStatusOk();
assertThat(response).hasContentTypeCompatibleWith(APPLICATION_JSON);
```

AssertJ phù hợp khi test đã dùng phong cách assertion đó ở các phần khác hoặc cần biểu đạt điều kiện response bằng một API assertion thống nhất. Matcher tích hợp của `RestTestClient` thường đủ cho các điều kiện HTTP phổ biến.

## 8. Phân biệt RestTestClient, MockMvc và WebTestClient

Ba công cụ đều có thể tham gia kiểm thử web, nhưng có API và phạm vi khác nhau:

| Công cụ | Cách tương tác | Phù hợp khi |
|---|---|---|
| `MockMvc` | API mô phỏng Servlet request/response, cho phép gọi và kiểm tra MVC trực tiếp | Test cần điều khiển chi tiết thành phần MVC, request builder, session, flash attribute hoặc kết quả dispatch. |
| `RestTestClient` | API HTTP đồng bộ dựa trên `RestClient`, có thể dùng MockMvc hoặc server thật | Test muốn viết request theo phong cách `RestClient` và kiểm tra response bằng fluent assertions. |
| `WebTestClient` | API client reactive dựa trên WebClient, hỗ trợ WebFlux và một số kịch bản MVC | Test WebFlux, reactive endpoint, streaming hoặc cần mô hình request/response reactive. |

`RestTestClient` sử dụng MockMvc cho các kiểu bind mock, nên phạm vi mock của nó tập trung vào Spring MVC trên Servlet stack. Nếu cần mock WebFlux handler hoặc kiểm thử reactive stream trực tiếp, `WebTestClient` là lựa chọn phù hợp hơn. Với server đang chạy và HTTP thật, `RestTestClient` có thể gửi request đến endpoint mà không cần mock MVC.

`RestTestClient` cũng không thay thế `MockRestServiceServer`. Hai công cụ kiểm thử hai phía khác nhau:

- `RestTestClient`: gửi request vào ứng dụng server và kiểm tra response mà ứng dụng trả về.
- `MockRestServiceServer`: giả lập server bên ngoài mà một `RestClient` hoặc `RestTemplate` trong ứng dụng đang gọi đến.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy class `RestTestClient` | Dự án đang dùng Spring Framework 6.x hoặc thiếu `spring-test`. | Dùng Spring Framework 7.0+ và thêm `spring-test` vào test classpath. |
| Import nhầm `WebTestClient` | Dùng package reactive `org.springframework.test.web.reactive.server` thay cho `RestTestClient`. | Import `org.springframework.test.web.servlet.client.RestTestClient`. |
| `bindToController` không tạo được bean phụ thuộc | Controller được tạo trực tiếp nhưng service hoặc dependency chưa được cung cấp. | Cung cấp dependency khi tạo controller hoặc bind vào `WebApplicationContext`. |
| Test gọi nhầm server hoặc port | Dùng `bindToServer()` với base URL sai, hoặc tưởng rằng mock binding cần server chạy. | Chọn đúng kiểu bind và kiểm tra địa chỉ/port khi dùng server thật. |
| Response body không giải mã được | Media type, message converter hoặc thư viện JSON không phù hợp. | Kiểm tra `Accept`, `Content-Type`, Jackson và message converter của MVC. |
| Assertion body không chạy hoặc thiếu dữ liệu | Test chưa gọi `expectBody(...)` hoặc không tiêu thụ response body trong môi trường leak detection. | Tiêu thụ body bằng `expectBody`, `expectBody(Void.class)` hoặc API tương ứng. |
| Dùng RestTestClient để kiểm thử outbound RestClient | Nhầm mục tiêu kiểm thử server với mục tiêu kiểm thử HTTP client của ứng dụng. | Dùng `MockRestServiceServer`, MockWebServer hoặc WireMock để giả lập dịch vụ đích. |

## 10. Quy trình lựa chọn và sử dụng

Khi bắt đầu một test với `RestTestClient`, có thể xác định theo thứ tự:

1. Kiểm tra dự án dùng Spring Framework 7.0+ và có `spring-test` trên test classpath.
2. Xác định endpoint thuộc Spring MVC và chọn controller, application context, router function hay server đang chạy làm đích bind.
3. Tạo `RestTestClient` một lần trong fixture hoặc setup phù hợp, cấu hình base URL, default header và client option nếu cần.
4. Viết request bằng các method quen thuộc như `get()`, `post()`, `uri(...)`, `accept(...)`, `contentType(...)` và `body(...)`.
5. Sau `exchange()`, xác nhận status, header và body bằng matcher tích hợp hoặc AssertJ.
6. Với response có body, tiêu thụ body để giải mã và kiểm tra dữ liệu; với response rỗng, xác nhận `isEmpty()` hoặc dùng `Void.class`.
7. Nếu test thực hiện request đến hệ thống ngoài, tách bài toán đó ra và dùng mock HTTP server phù hợp để kiểm thử mã gọi dịch vụ.

## 11. Kết luận

`RestTestClient` từ Spring Framework 7.0 là client kiểm thử đồng bộ, dùng `RestClient` để thực hiện HTTP request và bổ sung API assertion cho response. Nó có thể kiểm thử Spring MVC qua MockMvc mà không cần server hoặc gửi request đến server thật qua `bindToServer()`. `RestClient` vẫn là lựa chọn cho mã ứng dụng gọi API bên ngoài; `RestTestClient` dành cho test endpoint của ứng dụng. Khi hiểu rõ ranh giới này, có thể tái sử dụng phong cách request của `RestClient` mà vẫn có các assertion HTTP rõ ràng trong test.

## Tài liệu tham khảo

- [Spring Framework Reference — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html)
- [Spring Framework Reference — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework Javadoc — package `org.springframework.test.web.servlet.client`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/client/package-summary.html)
