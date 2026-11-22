# Kiểm thử HTTP đồng bộ bằng API dành cho assertion

`RestTestClient` là HTTP client dành cho kiểm thử ứng dụng server trong Spring Framework. Nó dùng `RestClient` để tạo và gửi request, đồng thời cung cấp API assertion cho response. Cách viết test gần với việc gọi REST API thật: tạo request, gọi `exchange()`, rồi kiểm tra status, header và body bằng các expectation có sẵn.

Điểm nổi bật của `RestTestClient` là API đồng bộ. Test không cần làm việc với `Mono`, `Flux` hoặc thao tác reactive để đọc response. Client có thể kết nối tới server đang chạy để kiểm thử end-to-end, hoặc bind vào Spring MVC thông qua MockMvc để kiểm thử controller mà không mở cổng HTTP.

`RestTestClient` được giới thiệu trong Spring Framework 7.0. Nếu dự án dùng Spring Framework 6.x hoặc Spring Boot 3.x, API này chưa có sẵn; khi đó tiếp tục dùng `MockMvc`, `WebTestClient` hoặc `RestClient` theo loại ứng dụng và mục tiêu test. Với Spring Boot 4.x dựa trên Spring Framework 7.x, có thể dùng `RestTestClient` từ dependency kiểm thử Spring.

## 1. Luồng request và assertion

API có hai phần rõ ràng. Trước `exchange()`, cách tạo request tương tự `RestClient`. Sau `exchange()`, `RestTestClient` trả về response specification để kiểm tra kết quả.

```text
RestTestClient
    |
    v
HTTP method + URI + headers + body
    |
    v
exchange()
    |
    v
ResponseSpec
    |
    +--> expectStatus()
    +--> expectHeader()
    +--> expectBody()
    +--> expectAll()
    |
    v
Test pass / assertion failure
```

Một test điển hình:

```java
client.get()
        .uri("/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectBody(Person.class)
        .consumeWith(result ->
                assertThat(result.getResponseBody())
                        .isEqualTo(new Person(1L, "Jane")));
```

Các expectation làm cho ý định của test dễ đọc: endpoint phải trả `200`, response phải là JSON và body phải biểu diễn đúng người cần tìm. Nếu một expectation thất bại, test báo lỗi tại bước assertion tương ứng.

## 2. Tạo RestTestClient và chọn phạm vi kiểm thử

Trước khi tạo client, cần chọn nơi request sẽ được gửi đến. `RestTestClient` có nhiều cách bind để phù hợp với phạm vi test.

| Cách bind | Request được xử lý ở đâu | Khi nên dùng |
|---|---|---|
| `bindToController(...)` | Controller được cung cấp, qua mock request/response | Test một hoặc vài controller cụ thể |
| `bindToApplicationContext(context)` | Spring MVC infrastructure và cấu hình đã nạp trong `WebApplicationContext` | Test controller cùng advice, converter, interceptor, filter và cấu hình MVC |
| `bindToRouterFunction(router)` | Functional endpoint `RouterFunction` được cung cấp | Test route và handler theo phong cách functional của Spring MVC |
| `bindToServer()` | Server HTTP đang chạy | Test end-to-end qua HTTP thật |

### Bind trực tiếp vào controller

Đây là cách ngắn nhất khi test chỉ cần một controller và các thành phần mà controller sử dụng. Không cần khởi động server thật:

```java
import org.springframework.test.web.servlet.client.RestTestClient;

RestTestClient client = RestTestClient
        .bindToController(new PersonController())
        .build();
```

Controller có thể là một đối tượng được tạo trực tiếp trong test. Nếu controller cần dependency, hãy truyền dependency test vào constructor hoặc dùng cách bind vào application context khi muốn Spring quản lý việc tạo bean và wiring.

### Bind vào application context

Khi cần kiểm tra cấu hình MVC đầy đủ, bind vào `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(WebConfig.class)
class PersonControllerTests {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient
                .bindToApplicationContext(context)
                .build();
    }
}
```

`WebConfig` là cấu hình Spring MVC của ứng dụng hoặc cấu hình test. Cách này đưa các thành phần đã đăng ký trong context vào luồng xử lý mock request/response, chẳng hạn controller, `@ControllerAdvice`, message converter và interceptor.

### Bind vào functional router

Với functional endpoint của Spring MVC, có thể bind trực tiếp vào `RouterFunction`:

```java
RestTestClient client = RestTestClient
        .bindToRouterFunction(personRoutes)
        .build();
```

Đây là cách kiểm thử request predicate và handler của router bằng mock request/response. Nếu cần cấu hình MVC ở cấp application context, dùng `bindToApplicationContext(...)` để kiểm thử ở phạm vi rộng hơn.

### Bind vào server đang chạy

Khi cần kiểm tra toàn bộ đường HTTP thực tế, tạo client kết nối tới server:

```java
RestTestClient client = RestTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

Trong test tự khởi động server, base URL thường được lấy từ cổng ngẫu nhiên do test framework cấp. Khi đó test đi qua HTTP client và server connector thực tế. Nó có thể phát hiện lỗi về port, HTTP transport, TLS hoặc cấu hình server mà mock setup không bao phủ.

## 3. Ví dụ hoàn chỉnh với bindToController

Giả sử API trả về thông tin một người:

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

Test dùng JUnit Jupiter và `RestTestClient`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;

import static org.assertj.core.api.Assertions.assertThat;

class PersonControllerTests {

    private RestTestClient client;

    @BeforeEach
    void setUp() {
        client = RestTestClient
                .bindToController(new PersonController())
                .build();
    }

    @Test
    void returnsPersonAsJson() {
        client.get()
                .uri("/persons/{id}", 1)
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody(Person.class)
                .consumeWith(result ->
                        assertThat(result.getResponseBody())
                                .isEqualTo(new Person(1L, "Jane")));
    }
}
```

`bindToController(...)` tạo mock MVC setup cho controller được cung cấp. Test gọi endpoint bằng URI template, yêu cầu JSON và giải mã response body thành `Person`. `consumeWith(...)` cho phép dùng AssertJ hoặc assertion tùy chỉnh khi expectation có sẵn chưa diễn đạt đủ điều cần kiểm tra.

Trong ví dụ này controller không có dependency. Nếu controller cần service, có thể tạo service giả rồi truyền vào constructor của controller. Nếu muốn kiểm tra dependency injection và cấu hình bean thật, dùng `bindToApplicationContext(...)`.

## 4. Tạo request bằng API đồng bộ

Các phương thức tạo request của `RestTestClient` tương tự `RestClient`. Có thể chọn HTTP method, URI, query parameter, header, content type và body.

```java
record CreatePersonRequest(String name) {
}

client.post()
        .uri("/persons")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Source", "integration-test")
        .body(new CreatePersonRequest("Ada"))
        .exchange()
        .expectStatus().isCreated();
```

Một số thành phần thường dùng:

| Thành phần | Vai trò |
|---|---|
| `get()`, `post()`, `put()`, `patch()`, `delete()` | Chọn HTTP method |
| `uri(...)` | Đặt path, URI template hoặc URI builder |
| `accept(...)` | Khai báo media type client muốn nhận |
| `contentType(...)` | Khai báo media type của request body |
| `header(...)`, `headers(...)` | Thêm header cho request |
| `body(object)` | Gửi object để message converter serialize |
| `exchange()` | Thực hiện request và chuyển sang response assertion |

`Content-Type` và `Accept` có ý nghĩa khác nhau. `Content-Type` nói body đang gửi có định dạng gì; `Accept` nói client muốn nhận response ở định dạng nào. Test JSON thường đặt cả hai khi gửi JSON và mong nhận JSON.

Với query parameter hoặc path variable, dùng URI template hoặc builder thay vì nối chuỗi thủ công:

```java
client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/persons")
                .queryParam("name", "Ada Lovelace")
                .queryParam("active", true)
                .build())
        .exchange()
        .expectStatus().isOk();
```

URI builder chịu trách nhiệm mã hóa các ký tự cần thiết. Điều này giúp test gửi đúng giá trị có dấu cách, Unicode hoặc ký tự đặc biệt.

## 5. Assertion cho status và header

Sau `exchange()`, có thể kiểm tra status bằng các matcher có sẵn:

```java
client.get()
        .uri("/persons/999")
        .exchange()
        .expectStatus().isNotFound();
```

Các assertion thường gặp gồm `isOk()`, `isCreated()`, `isAccepted()`, `isNoContent()`, `isBadRequest()`, `isUnauthorized()`, `isForbidden()`, `isNotFound()` và `is5xxServerError()`. Với status đặc biệt, có thể dùng matcher nhận mã status hoặc predicate tương ứng của API.

Header cũng có thể được kiểm tra trực tiếp:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectHeader().exists("ETag")
        .expectHeader().valueEquals("X-Api-Version", "v1");
```

Nếu chỉ cần kiểm tra media type tương thích, dùng `contentTypeCompatibleWith(...)`. Cách này hữu ích khi response có tham số như `charset` mà vẫn cùng loại media type.

Có thể gom nhiều expectation bằng `expectAll(...)`:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectAll(
                spec -> spec.expectStatus().isOk(),
                spec -> spec.expectHeader()
                        .contentType(MediaType.APPLICATION_JSON),
                spec -> spec.expectHeader().exists("ETag"));
```

Các expectation trong `expectAll(...)` được đánh giá như soft assertions, nên test có thể báo nhiều lỗi trong cùng một lần chạy thay vì dừng ở assertion đầu tiên.

## 6. Assertion cho response body

`RestTestClient` cung cấp nhiều cách đọc body tùy loại response.

### Decode thành một object

Khi response biểu diễn một object:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .consumeWith(result -> {
            Person person = result.getResponseBody();
            assertThat(person).isNotNull();
            assertThat(person.name()).isEqualTo("Jane");
        });
```

`expectBody(Person.class)` dùng message converter để decode response body. Sau đó có thể assertion object bằng AssertJ hoặc logic riêng.

### Kiểm tra JSON bằng JSONPath

Nếu chỉ cần kiểm tra một vài field, không cần deserialize toàn bộ object:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(1)
        .jsonPath("$.name").isEqualTo("Jane");
```

`expectBody()` không có kiểu đích cho phép kiểm tra raw JSON bằng JSONPath hoặc so sánh JSON. Với `.json(...)`, cần có JSONassert trên classpath. JSONPath cũng cần thư viện hỗ trợ tương ứng trong test dependencies.

### So sánh toàn bộ JSON

Khi cấu trúc JSON là hợp đồng cần xác nhận:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {
                  "id": 1,
                  "name": "Jane"
                }
                """);
```

So sánh JSON phù hợp khi các field, kiểu dữ liệu và cấu trúc body đều quan trọng. Nếu chỉ một field là mục tiêu của test, JSONPath thường làm test ít phụ thuộc vào thay đổi không liên quan.

### Response không có body

Với `204 No Content` hoặc endpoint không trả nội dung:

```java
client.delete()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
```

Nếu không cần assertion nội dung nhưng vẫn muốn giải phóng response body, có thể dùng `.expectBody(Void.class)`. Việc tiêu thụ response body quan trọng khi bật leak detection cho pooled buffers; bỏ qua việc đọc body có thể làm công cụ phát hiện buffer chưa được giải phóng.

## 7. Kiểm tra body có generic type

Khi response là collection hoặc kiểu generic lồng nhau, `Class<T>` không thể biểu diễn đầy đủ type parameter. Dùng `ParameterizedTypeReference`:

```java
import org.springframework.core.ParameterizedTypeReference;

List<Person> people = client.get()
        .uri("/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody(new ParameterizedTypeReference<List<Person>>() {
        })
        .returnResult()
        .getResponseBody();

assertThat(people)
        .extracting(Person::name)
        .containsExactly("Jane", "Jason");
```

`ParameterizedTypeReference` giữ thông tin generic tại runtime để message converter biết cần decode JSON thành `List<Person>`. Nếu chỉ dùng `List.class`, phần tử có thể được decode thành map thay vì `Person`.

## 8. Lấy kết quả response để assertion tùy chỉnh

Khi built-in assertion chưa đủ, có thể lấy `EntityExchangeResult`:

```java
import org.springframework.test.web.servlet.client.EntityExchangeResult;

EntityExchangeResult<Person> result = client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .returnResult();

Person person = result.getResponseBody();
assertThat(person).isEqualTo(new Person(1L, "Jane"));
assertThat(result.getResponseHeaders().getFirst("ETag")).isNotBlank();
```

Kết quả chứa response body đã decode, response headers và metadata của exchange. Có thể dùng nó khi cần assertion phức tạp hoặc truyền kết quả sang helper dùng chung.

## 9. Dùng AssertJ integration

Ngoài expectation chain, `RestTestClient` hỗ trợ tích hợp với AssertJ thông qua `RestTestClientResponse`. Lớp này bọc response specification hoặc exchange result để assertion theo phong cách AssertJ:

```java
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.test.web.servlet.client.RestTestClientResponse;

import static org.assertj.core.api.Assertions.assertThat;

RestTestClient.ResponseSpec spec = client.get()
        .uri("/persons/1")
        .exchange();

RestTestClientResponse response = RestTestClientResponse.from(spec);

assertThat(response).hasStatusOk();
assertThat(response).hasContentTypeCompatibleWith(
        MediaType.APPLICATION_JSON);
```

Cách này hữu ích khi nhóm test đã quen với AssertJ hoặc muốn tạo assertion helper có thể tái sử dụng. Nếu chỉ cần kiểm tra status, header và JSON field đơn giản, built-in expectation chain thường dễ đọc hơn.

Có thể lấy `ExchangeResult` trước rồi bọc bằng `RestTestClientResponse.from(result)` để kết hợp hai phong cách. Không cần dùng cả hai cách trong một test nếu điều đó không giúp assertion rõ hơn.

## 10. Cấu hình client dùng chung

Sau khi chọn binding, có thể cấu hình thêm các thuộc tính phía client như base URL, default header hoặc client filter:

```java
RestTestClient client = RestTestClient
        .bindToController(new PersonController())
        .baseUrl("/api")
        .defaultHeader("X-Client", "test-suite")
        .build();
```

Khi đó test có thể gọi `.uri("/persons/1")` và header mặc định được thêm vào request. Có thể cấu hình client filter để ghi log hoặc thêm metadata cho request test. Những cấu hình này thuộc phía client; chúng không thay thế filter hoặc interceptor thuộc server application.

Không nên đặt dữ liệu thay đổi theo từng test vào default header của một client dùng chung. Nếu test chạy song song và mỗi test cần một user hoặc tenant khác, hãy đặt header trên request tương ứng:

```java
client.get()
        .uri("/persons/1")
        .header("X-Tenant-Id", "tenant-a")
        .exchange()
        .expectStatus().isOk();
```

## 11. Chọn giữa mock setup và server thật

`RestTestClient` dùng được cho cả mock request/response lẫn HTTP end-to-end. Hai phạm vi này cho bằng chứng khác nhau.

| Đặc điểm | Bind controller/context/router | Bind server |
|---|---|---|
| Mở cổng HTTP | Không | Có, server đã chạy |
| Tốc độ | Thường nhanh hơn | Chậm hơn do HTTP transport và server lifecycle |
| Kiểm tra routing và MVC handler | Có | Có |
| Kiểm tra server connector, TLS, port | Không | Có |
| Kiểm tra proxy/network deployment | Không | Chỉ khi test đi qua hạ tầng đó |
| Phù hợp cho nhiều test API nhỏ | Có | Có thể tốn tài nguyên hơn |

Một test bind vào controller có thể chứng minh controller trả đúng status và JSON. Nó không chứng minh server thật đã bật đúng TLS hoặc reverse proxy chuyển tiếp header đúng. Khi cần xác nhận các yếu tố đó, hãy bổ sung test với server thật.

Nếu dùng Spring Boot test với server port ngẫu nhiên, có thể cấu hình `RestTestClient` từ base URL được test framework cung cấp. Test cần bảo đảm server đã sẵn sàng trước khi gửi request và đóng tài nguyên sau khi kết thúc.

## 12. Phân biệt RestTestClient, RestClient, MockMvc và WebTestClient

Các API có tên gần nhau nhưng phục vụ mục tiêu khác nhau:

| API | Vai trò chính | Cách kiểm tra |
|---|---|---|
| `RestClient` | HTTP client đồng bộ cho ứng dụng | Gọi `retrieve()` hoặc `exchange()` và xử lý response trong code ứng dụng |
| `RestTestClient` | HTTP test client đồng bộ | Gửi request rồi dùng expectation/assertion để xác nhận response |
| `MockMvc` | API kiểm thử Spring MVC ở mức servlet mock | `perform(...)`, `andExpect(...)`, `andReturn()` |
| `WebTestClient` | Test client với API fluent hỗ trợ WebFlux và các kiểu bind của nó | `exchange()` và expectation; có thể làm việc với publisher/reactive stream |

`RestTestClient` được thiết kế như biến thể đồng bộ của trải nghiệm `WebTestClient`, và dùng `RestClient` ở phía gửi request. Nếu test tập trung vào Spring MVC và muốn API request/response quen thuộc của REST client đồng bộ, `RestTestClient` là lựa chọn phù hợp. Nếu ứng dụng là WebFlux và cần kiểm tra reactive behavior hoặc streaming, `WebTestClient` thường phù hợp hơn.

`MockMvc` vẫn hữu ích khi cần API đặc thù của servlet testing, như kiểm tra session, flash attributes, request dispatch hoặc các chi tiết servlet. `RestTestClient` có thể bind qua MockMvc nhưng cung cấp facade kiểu HTTP client và assertion khác.

## 13. Phiên bản và dependency

`RestTestClient` được thêm trong Spring Framework 7.0. API nằm trong package:

```java
import org.springframework.test.web.servlet.client.RestTestClient;
```

Nó thuộc module `spring-test`, thường đã có trong test classpath khi dùng Spring Boot test starter. Với cấu hình dependency thủ công, cần thêm `spring-test` ở test scope và các dependency hỗ trợ test tương ứng như JUnit Jupiter, AssertJ, JSONassert hoặc JSONPath nếu dùng các assertion đó.

Ví dụ Gradle tối thiểu cho test classpath:

```groovy
dependencies {
    testImplementation "org.springframework:spring-test"
    testImplementation "org.junit.jupiter:junit-jupiter"
    testImplementation "org.assertj:assertj-core"
}
```

Trong dự án Spring Boot, nên để Spring Boot dependency management quản lý phiên bản Spring Framework và test dependencies thay vì tự chọn một phiên bản `spring-test` khác với phần còn lại của framework.

Nếu IDE không tìm thấy `RestTestClient`, hãy kiểm tra Spring Framework version và test classpath trước khi kiểm tra import. Thêm import không thể làm API xuất hiện trong Spring Framework 6.x.

## 14. Các lỗi thường gặp khi viết test

| Cách làm | Vấn đề | Cách làm phù hợp hơn |
|---|---|---|
| Dùng `RestTestClient` với Spring Framework 6.x | API chỉ có từ Framework 7.0 | Kiểm tra phiên bản hoặc dùng API test có sẵn của phiên bản đó |
| Nhầm `RestTestClient` với `RestClient` | `RestClient` không cung cấp expectation facade dành cho test | Dùng `RestTestClient` trong test source |
| Dùng `bodyValue(...)` như WebClient | API request theo `RestClient` dùng `.body(object)` | Dùng `.body(request)` |
| Bind vào controller nhưng kỳ vọng toàn bộ application context được nạp | Binding controller chỉ tạo mock setup cho controller đã cung cấp | Bind vào `WebApplicationContext` nếu cần cấu hình MVC đầy đủ |
| Chỉ kiểm tra status | Không xác nhận representation mà client nhận | Kiểm tra cả content type và body quan trọng |
| So sánh toàn bộ JSON khi chỉ cần một field | Test dễ hỏng do thay đổi field không liên quan | Dùng JSONPath cho field mục tiêu |
| Dùng `List.class` cho JSON collection | Mất thông tin kiểu phần tử generic | Dùng `ParameterizedTypeReference<List<T>>` |
| Không tiêu thụ response body | Có thể gây cảnh báo pooled buffer khi leak detection bật | Dùng `expectBody()` hoặc `expectBody(Void.class)` |
| Dùng mock setup để kết luận TLS/server connector đúng | Không có HTTP server thật trong test | Bổ sung test bind tới server đang chạy |

## 15. Quy trình viết một test HTTP đồng bộ

1. Xác định API thuộc Spring MVC và phiên bản framework có hỗ trợ `RestTestClient`.
2. Chọn phạm vi: controller, application context, functional router hay server thật.
3. Tạo client một lần cho fixture test và cấu hình base URL/header mặc định nếu cần.
4. Tạo request bằng HTTP method, URI, header, content type và body như client thực.
5. Gọi `exchange()` để thực hiện request.
6. Kiểm tra status và header bằng expectation phù hợp.
7. Decode body thành object, kiểm tra JSONPath, so sánh JSON hoặc lấy `EntityExchangeResult` tùy nhu cầu.
8. Dùng `expectAll(...)` khi muốn báo nhiều lỗi expectation trong cùng một test.
9. Tiêu thụ response body và đóng tài nguyên của server thật nếu test tự quản lý server.
10. Bổ sung test end-to-end khi cần xác nhận HTTP transport, TLS hoặc cấu hình hạ tầng.

## 16. Tài liệu tham khảo

- [Spring Framework Reference — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html): binding modes, request workflow, built-in assertions và AssertJ integration.
- [Spring Framework Javadoc — `RestTestClient`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/client/RestTestClient.html): API client đồng bộ dành cho kiểm thử server.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): giới thiệu RestTestClient như biến thể đồng bộ của WebTestClient.
- [Spring Framework Reference — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): API HTTP client đồng bộ mà RestTestClient sử dụng để thực hiện request.

`RestTestClient` giúp kiểm thử HTTP theo cách đồng bộ và giàu assertion: request được tạo bằng API kiểu `RestClient`, còn response được xác nhận bằng expectation chain hoặc AssertJ. Hãy chọn đúng binding theo phạm vi cần kiểm tra, tiêu thụ body sau exchange và dùng server thật khi cần bằng chứng về HTTP transport hoặc hạ tầng triển khai.
