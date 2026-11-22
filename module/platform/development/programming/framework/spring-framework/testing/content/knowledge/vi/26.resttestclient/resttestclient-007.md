# Tích hợp assertion theo kiểu AssertJ

`RestTestClient` cung cấp một cách gửi HTTP request và kiểm tra response theo kiểu đồng bộ. Sau khi gọi `exchange()`, có thể dùng các assertion tích hợp sẵn của client hoặc chuyển response sang AssertJ. Cách thứ hai hữu ích khi muốn viết assertion theo dạng `assertThat(...)`, tận dụng các phép kiểm tra quen thuộc của AssertJ và kết hợp chúng với kiểm tra status, header, cookie, content type và body.

Điểm vào chính của tích hợp này là `RestTestClientResponse`. Interface này triển khai `AssertProvider<RestTestClientResponseAssert>`, vì vậy AssertJ có thể tự lấy assertion chuyên biệt khi gọi `assertThat(response)`. Assertion chuyên biệt cho phép kiểm tra HTTP response, sau đó chuyển sang assertion của AssertJ cho chuỗi, byte array, JSON, headers và cookies.

Tích hợp AssertJ của `RestTestClient` được giới thiệu trong Spring Framework 7.0. Các ví dụ dưới đây dùng API Spring Framework 7.0 trở lên.

### Dependency cần có

Các API kiểm thử nằm trong `spring-test`; AssertJ cần có trên test classpath để dùng `assertThat(...)`:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.assertj</groupId>
    <artifactId>assertj-core</artifactId>
    <scope>test</scope>
</dependency>
```

Hãy để Spring Boot dependency management hoặc Spring Framework BOM quản lý version để các module Spring cùng dòng tương thích. Nếu dùng so sánh JSON hoặc các assertion JSON chuyên biệt, thêm thư viện JSON assertion mà phiên bản Spring đang dùng hỗ trợ; tài liệu Spring 7.0 minh họa JSONAssert, còn tài liệu 7.1 hỗ trợ JSONUnit hoặc JSONAssert.

## Chuẩn bị RestTestClient

`RestTestClient` nằm trong package `org.springframework.test.web.servlet.client`. Nó có thể kiểm thử controller bằng mock servlet request/response, nạp toàn bộ `WebApplicationContext`, kiểm thử functional endpoint qua router function hoặc kết nối đến server đang chạy.

Ví dụ khởi tạo với `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(WebConfig.class)
class PersonApiTest {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient.bindToApplicationContext(context).build();
    }
}
```

Nếu chỉ muốn kiểm thử một hoặc một vài controller, có thể dùng `RestTestClient.bindToController(...)`. Nếu cần kiểm thử qua HTTP thật, dùng `RestTestClient.bindToServer()` và cấu hình base URL của server đang chạy. Cách bind quyết định request đi qua mock MVC infrastructure hay qua mạng đến server thật; API assertion sau `exchange()` vẫn có cùng mục tiêu kiểm tra response.

`RestTestClient` có API gửi request tương tự `RestClient` cho đến lời gọi `exchange()`. Có thể thiết lập URI, path variable, query parameter, header, content type, accept, cookie và request body trước khi thực thi.

## Hai phong cách kiểm tra response

Sau `exchange()`, có hai phong cách chính:

| Phong cách | Cách viết | Phù hợp khi |
|---|---|---|
| Built-in assertions | `expectStatus()`, `expectHeader()`, `expectBody()` | Muốn giữ toàn bộ kiểm tra trong một chuỗi của RestTestClient |
| AssertJ integration | `RestTestClientResponse.from(...)` rồi `assertThat(...)` | Muốn dùng các assertion theo phong cách AssertJ hoặc kết hợp assertion tùy biến |

Built-in assertions có thể viết như sau:

```java
client.get().uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectBody();
```

AssertJ integration chuyển kết quả exchange thành `RestTestClientResponse`, sau đó dùng `assertThat`:

```java
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.test.web.servlet.client.assertj.RestTestClientResponse;

import static org.assertj.core.api.Assertions.assertThat;

RestTestClient.ResponseSpec spec = client.get()
        .uri("/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange();

RestTestClientResponse response = RestTestClientResponse.from(spec);

assertThat(response).hasStatusOk();
assertThat(response).hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

`RestTestClientResponse.from(ResponseSpec)` là điểm chuyển đổi trực tiếp từ response spec sang đối tượng có thể dùng với AssertJ. Vì `RestTestClientResponse` là `AssertProvider`, không cần gọi thủ công `response.assertThat()`; `assertThat(response)` tự chọn `RestTestClientResponseAssert`.

## Tạo response assertion từ ExchangeResult

Nếu muốn dùng built-in workflow trước rồi mới chuyển sang AssertJ, có thể lấy `ExchangeResult` bằng `returnResult()`:

```java
import org.springframework.test.web.servlet.client.ExchangeResult;

ExchangeResult result = client.get()
        .uri("/persons/1")
        .exchange()
        .returnResult();

RestTestClientResponse response = RestTestClientResponse.from(result);

assertThat(response).hasStatusOk();
assertThat(response).hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

Hai đường đi có mục đích khác nhau:

- `from(ResponseSpec)` chuyển trực tiếp kết quả sau `exchange()` sang AssertJ.
- `from(ExchangeResult)` hữu ích khi test đã dùng `returnResult()` để lấy kết quả exchange hoặc cần giữ `ExchangeResult` cho các bước kiểm tra khác.

Đối tượng `RestTestClientResponse` cũng cung cấp `getExchangeResult()` để lấy kết quả exchange nền. Nhờ vậy có thể kết hợp assertion cấp cao với việc đọc request/response metadata mà `ExchangeResult` lưu lại.

## Kiểm tra status HTTP

`RestTestClientResponseAssert` có các phương thức kiểm tra status theo mã cụ thể hoặc theo nhóm:

```java
assertThat(response).hasStatusOk();
assertThat(response).hasStatus(201);
assertThat(response).hasStatus(HttpStatus.CREATED);
assertThat(response).hasStatus2xxSuccessful();
assertThat(response).hasStatus3xxRedirection();
assertThat(response).hasStatus4xxClientError();
assertThat(response).hasStatus5xxServerError();
```

Chọn assertion cụ thể khi status là một phần của API contract. Ví dụ, endpoint tạo tài nguyên thường nên được kiểm tra với `201 Created`, thay vì chỉ xác nhận status thuộc nhóm 2xx. Assertion theo nhóm hữu ích khi nhiều mã thành công khác nhau đều được chấp nhận trong một tình huống.

Có thể gắn mô tả cho assertion để thông báo thất bại dễ đọc hơn:

```java
assertThat(response)
        .as("creating a person should return Created")
        .hasStatus(HttpStatus.CREATED);
```

Các phương thức này trả về assertion cùng kiểu, vì vậy có thể nối nhiều kiểm tra trên một response:

```java
assertThat(response)
        .hasStatus(HttpStatus.CREATED)
        .containsHeader(HttpHeaders.LOCATION)
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

## Kiểm tra headers và Content-Type

Assertion response cung cấp các cách kiểm tra header ở mức trực tiếp:

```java
assertThat(response)
        .containsHeader(HttpHeaders.ETAG)
        .hasHeader(HttpHeaders.CACHE_CONTROL, "no-store")
        .doesNotContainHeader("X-Internal-Debug");
```

`containsHeader(name)` kiểm tra header có tồn tại. `hasHeader(name, value)` kiểm tra giá trị chính của header. Nếu cần kiểm tra danh sách giá trị hoặc nhiều header cùng lúc, dùng `headers()` để nhận `HttpHeadersAssert`, một map assertion theo kiểu AssertJ:

```java
assertThat(response)
        .headers()
        .containsKey(HttpHeaders.ETAG)
        .containsKey(HttpHeaders.CACHE_CONTROL)
        .doesNotContainKey("X-Internal-Debug");
```

Với `Content-Type`, cần phân biệt so sánh chính xác và so sánh tương thích:

```java
assertThat(response).hasContentType(MediaType.APPLICATION_JSON);

assertThat(response)
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

`hasContentType(...)` kiểm tra giá trị content type bằng với giá trị mong đợi. `hasContentTypeCompatibleWith(...)` kiểm tra hai media type có tương thích, ví dụ response là `application/json` và mong đợi là `application/*`. Nếu charset hoặc parameter của media type là một phần của hợp đồng, hãy kiểm tra cụ thể thay vì chỉ dùng compatibility.

Cũng có thể đi sâu vào `MediaTypeAssert`:

```java
assertThat(response)
        .contentType()
        .isCompatibleWith(MediaType.APPLICATION_JSON);
```

## Kiểm tra cookies

`cookies()` trả về `CookieMapAssert`, cho phép kiểm tra cookie như một map có key là tên cookie. Ngoài các phép kiểm tra map của AssertJ, Spring cung cấp assertion riêng cho thuộc tính cookie:

```java
assertThat(response)
        .cookies()
        .containsCookie("SESSION")
        .hasPath("SESSION", "/")
        .isHttpOnly("SESSION", true)
        .isSecure("SESSION", true);
```

Các phương thức có thể dùng gồm:

| Assertion | Ý nghĩa |
|---|---|
| `containsCookie("SESSION")` | Có cookie với tên đã cho |
| `doesNotContainCookie("legacy")` | Không có cookie với tên đã cho |
| `hasValue("theme", "dark")` | Cookie có đúng giá trị |
| `hasPath("SESSION", "/")` | Cookie có đúng path |
| `hasDomain("SESSION", "example.test")` | Cookie có đúng domain |
| `hasMaxAge("remember", Duration.ofDays(30))` | Cookie có đúng thời hạn |
| `isHttpOnly("SESSION", true)` | Kiểm tra cờ HttpOnly |
| `isSecure("SESSION", true)` | Kiểm tra cờ Secure |
| `hasCookieSatisfying("name", consumer)` | Kiểm tra cookie bằng assertion tùy biến |

Ví dụ với assertion tùy biến:

```java
assertThat(response)
        .cookies()
        .hasCookieSatisfying("SESSION", cookie -> {
            assertThat(cookie.getValue()).isNotBlank();
            assertThat(cookie.getPath()).isEqualTo("/");
            assertThat(cookie.isHttpOnly()).isTrue();
            assertThat(cookie.getSecure()).isTrue();
        });
```

Đừng giả định mọi cookie đều cần `Secure` hoặc cùng `Max-Age`; hãy assert theo chính sách cookie của ứng dụng và môi trường test. Với cookie session, `HttpOnly` và `Secure` thường là các thuộc tính bảo mật quan trọng cần xác nhận khi ứng dụng được cấu hình để bật chúng.

## Kiểm tra response body dưới dạng text hoặc byte array

`bodyText()` chuyển body thành chuỗi và trả về `AbstractStringAssert` của AssertJ. Vì vậy có thể dùng mọi phép kiểm tra chuỗi quen thuộc:

```java
assertThat(response)
        .bodyText()
        .isEqualTo("Hello, Jane")
        .contains("Jane")
        .doesNotContain("stacktrace");
```

Nếu chỉ muốn kiểm tra bằng nhau, có thể dùng `hasBodyTextEqualTo(...)` trực tiếp trên response assertion:

```java
assertThat(response).hasBodyTextEqualTo("Hello, Jane");
```

`body()` trả về byte array assertion. Dùng nó khi cần xác nhận body rỗng, byte content hoặc nội dung nhị phân:

```java
assertThat(response).body().isNotEmpty();

assertThat(response).body().isEqualTo(expectedBytes);
```

Đối với response không có nội dung, có thể kiểm tra byte array rỗng:

```java
assertThat(response)
        .hasStatus(HttpStatus.NO_CONTENT)
        .body()
        .isEmpty();
```

Nếu body được encode bằng charset cụ thể, `bodyText()` là cách thuận tiện để kiểm tra chuỗi đã decode. Nếu hợp đồng yêu cầu byte chính xác, dùng `body()` và so sánh byte array.

## Kiểm tra JSON bằng bodyJson()

`bodyJson()` trả về assertion chuyên biệt cho JSON. Nó hỗ trợ so sánh JSON và trích xuất giá trị theo JSONPath, sau đó chuyển sang kiểu assertion phù hợp:

```java
assertThat(response)
        .bodyJson()
        .extractingPath("$.name")
        .asString()
        .isEqualTo("Jane");
```

Có thể kiểm tra nhiều field theo đường dẫn:

```java
assertThat(response)
        .bodyJson()
        .extractingPath("$.id")
        .asNumber()
        .isEqualTo(42);

assertThat(response)
        .bodyJson()
        .extractingPath("$.active")
        .asBoolean()
        .isTrue();
```

JSON assertion cũng có thể kiểm tra sự tồn tại hoặc vắng mặt của path:

```java
assertThat(response)
        .bodyJson()
        .hasPath("$.customer.email")
        .doesNotHavePath("$.internalSecret");
```

Khi toàn bộ JSON response là hợp đồng cần bảo vệ, có thể so sánh với JSON mẫu:

```java
assertThat(response)
        .bodyJson()
        .isStrictlyEqualTo("""
                {
                  "id": 42,
                  "name": "Jane",
                  "active": true
                }
                """);
```

Nếu JSON mẫu được lưu thành file test resource, có thể dùng `withResourceLoadClass(...)` để xác định package chứa file:

```java
assertThat(response)
        .bodyJson()
        .withResourceLoadClass(PersonControllerTest.class)
        .isStrictlyEqualTo("person-created.json");
```

So sánh JSON giúp xác nhận nhiều field trong một lần assertion. JSONPath phù hợp khi chỉ cần kiểm tra một vài field hoặc khi response chứa giá trị động không nên đưa vào fixture. Với response có timestamp hoặc ID sinh tự động, hãy trích xuất field ổn định hoặc cố định dữ liệu test trước khi so sánh toàn bộ JSON.

## Kiểm tra body tùy biến bằng AssertJ

Nếu body có thể decode thành một DTO, có thể dùng built-in body workflow rồi chạy AssertJ trong `consumeWith(...)`:

```java
client.get().uri("/persons/{id}", 42L)
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .consumeWith(result -> {
            Person person = result.getResponseBody();
            assertThat(person).isNotNull();
            assertThat(person.getId()).isEqualTo(42L);
            assertThat(person.getName()).isEqualTo("Jane");
        });
```

Cách này hữu ích khi muốn dùng object đã deserialize để kiểm tra quy tắc nghiệp vụ hoặc recursive comparison của AssertJ. Built-in `expectBody(Person.class)` đảm nhiệm việc decode, còn AssertJ kiểm tra object.

Nếu muốn lấy object ra ngoài chuỗi expectation, gọi `returnResult()`:

```java
EntityExchangeResult<Person> result = client.get()
        .uri("/persons/{id}", 42L)
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .returnResult();

Person person = result.getResponseBody();
assertThat(person)
        .isNotNull()
        .extracting(Person::getName)
        .isEqualTo("Jane");
```

Với body có generic type như `List<Person>`, dùng overload nhận `ParameterizedTypeReference` để giữ thông tin kiểu generic:

```java
ParameterizedTypeReference<List<Person>> personListType =
        new ParameterizedTypeReference<>() {};

EntityExchangeResult<List<Person>> result = client.get()
        .uri("/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody(personListType)
        .returnResult();

assertThat(result.getResponseBody())
        .extracting(Person::getName)
        .containsExactly("Jane", "Jason");
```

Đừng dùng `Person.class` để decode `List<Person>`; do type erasure, kiểu phần tử generic có thể bị mất. `ParameterizedTypeReference` giữ lại thông tin kiểu cần thiết cho message converter.

## Kết hợp AssertJ với kết quả ExchangeResult

`RestTestClientResponse` có thể lấy `ExchangeResult` nền:

```java
ExchangeResult exchangeResult = response.getExchangeResult();

assertThat(exchangeResult.getResponseHeaders())
        .containsKey(HttpHeaders.ETAG);
assertThat(exchangeResult.getResponseBodyContent())
        .isNotEmpty();
```

Đây là lựa chọn khi cần truy cập metadata không có assertion chuyên biệt. Nên ưu tiên `headers()`, `cookies()`, `bodyText()` hoặc `bodyJson()` khi chúng đáp ứng nhu cầu, vì chúng diễn đạt trực tiếp ý định của test. Dùng `ExchangeResult` cho các kiểm tra đặc thù như request headers, URI, thời gian thực hiện hoặc dữ liệu response thô.

## Tổ chức assertion thành helper dùng lại

Nếu nhiều test cần xác nhận cùng một phần response contract, có thể tạo helper nhận `RestTestClientResponse`:

```java
static void assertJsonResponse(RestTestClientResponse response) {
    assertThat(response)
            .hasStatusOk()
            .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);

    assertThat(response)
            .bodyJson()
            .hasPath("$.id")
            .hasPath("$.status");
}
```

Test gọi helper sau khi thực hiện request:

```java
RestTestClientResponse response = RestTestClientResponse.from(
        client.get().uri("/api/orders/{id}", 42L).exchange());

assertJsonResponse(response);
assertThat(response)
        .bodyJson()
        .extractingPath("$.status")
        .asString()
        .isEqualTo("PAID");
```

Helper nên gom các điều kiện chung có ý nghĩa trong API contract, chẳng hạn status thành công và media type. Để các assertion riêng của từng test ở gần test đó; nếu helper biết quá nhiều về dữ liệu nghiệp vụ, nó có thể che khuất hành vi mà test cần mô tả.

## Khi nào dùng AssertJ và khi nào dùng built-in assertions?

Built-in assertions của RestTestClient phù hợp khi muốn kiểm tra response ngay trong fluent workflow:

```java
client.get().uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectBody(Person.class)
        .consumeWith(result -> {
            Person person = result.getResponseBody();
            assertThat(person).isNotNull();
            assertThat(person.getName()).isEqualTo("Jane");
        });
```

AssertJ integration phù hợp khi muốn tách response ra thành một đối tượng và dùng nhiều assertion độc lập:

```java
RestTestClientResponse response = RestTestClientResponse.from(
        client.get().uri("/persons/1").exchange());

assertThat(response).hasStatusOk();
assertThat(response).contentType()
        .isCompatibleWith(MediaType.APPLICATION_JSON);
assertThat(response).bodyJson()
        .extractingPath("$.name")
        .asString()
        .isEqualTo("Jane");
```

`expectAll(...)` của built-in API cho phép nhiều expectation chạy ngay cả khi một expectation thất bại. Đây là cách gom lỗi tương tự soft assertions, nhưng nó vẫn là cơ chế của RestTestClient. Nếu dùng AssertJ integration, có thể dùng các khả năng của AssertJ như `SoftAssertions` khi cần thu thập nhiều lỗi assertion trong cùng một test; hãy giữ một response đã thực thi để tránh gửi cùng request nhiều lần.

## Lưu ý khi kiểm tra response body

Nếu test cần đọc response body, hãy tiêu thụ body bằng `body()`, `bodyText()`, `bodyJson()`, `expectBody(...)` hoặc `returnResult()` phù hợp. Việc bỏ qua body hoàn toàn có thể gây cảnh báo buffer leak trong các cấu hình kiểm tra pooled buffer. Khi endpoint không có body, xác nhận status rồi dùng body assertion để kiểm tra rỗng hoặc `expectBody().isEmpty()` trong built-in workflow.

Không dùng `bodyJson()` cho response không phải JSON hoặc body trống. Dùng `bodyText()` cho văn bản, `body()` cho byte content và `bodyJson()` cho JSON. Chọn assertion phù hợp với media type và hợp đồng response.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy `RestTestClient` | Đang dùng Spring Framework cũ hơn 7.0 hoặc thiếu `spring-test` phù hợp | Dùng Spring Framework 7.0 trở lên và dependency test tương ứng |
| `assertThat(response)` không có assertion HTTP | Đối tượng truyền vào không phải `RestTestClientResponse` hoặc thiếu AssertJ | Dùng `RestTestClientResponse.from(...)` và thêm AssertJ vào test classpath |
| Không tạo được response wrapper | Truyền nhầm request spec thay vì `ResponseSpec` hoặc `ExchangeResult` | Gọi `exchange()` trước rồi truyền kết quả vào `from(...)` |
| `hasContentType` thất bại nhưng response vẫn là JSON | So sánh chính xác cả media type parameter | Dùng `hasContentTypeCompatibleWith(...)` nếu chỉ cần kiểm tra compatibility |
| `bodyJson()` không parse được | Body không phải JSON hợp lệ hoặc thiếu JSON assertion dependency theo version | Kiểm tra body, Content-Type và dependency JSON assertion |
| Body assertion trả dữ liệu rỗng ngoài dự kiến | Response chưa được tiêu thụ đúng cách hoặc endpoint thực sự không trả body | Kiểm tra status và dùng đúng body API để đọc/tiêu thụ response |
| Generic response bị decode thành kiểu không mong muốn | Dùng `Class<T>` cho collection generic | Dùng `ParameterizedTypeReference<T>` |
| Assertion helper gửi request lặp lại | Helper tự thực hiện request thay vì nhận response đã exchange | Tạo `RestTestClientResponse` một lần rồi truyền vào helper |

## Chọn assertion theo mục tiêu

| Mục tiêu | Assertion |
|---|---|
| Kiểm tra HTTP status | `hasStatusOk()`, `hasStatus(...)`, `hasStatus2xxSuccessful()` |
| Kiểm tra Content-Type | `hasContentType(...)`, `hasContentTypeCompatibleWith(...)`, `contentType()` |
| Kiểm tra header | `containsHeader(...)`, `hasHeader(...)`, `headers()` |
| Kiểm tra cookie | `cookies().containsCookie(...)`, `hasValue(...)`, `isHttpOnly(...)`, `isSecure(...)` |
| Kiểm tra text body | `bodyText()` hoặc `hasBodyTextEqualTo(...)` |
| Kiểm tra byte body | `body()` |
| So sánh JSON | `bodyJson().isStrictlyEqualTo(...)` hoặc `isLenientlyEqualTo(...)` |
| Đọc một JSON field | `bodyJson().extractingPath(...).asString()` |
| Kiểm tra DTO đã decode | `expectBody(Person.class).consumeWith(...)` rồi AssertJ |
| Kiểm tra collection generic | `expectBody(ParameterizedTypeReference<T>)` rồi AssertJ |

Tích hợp AssertJ cho `RestTestClient` giúp chuyển từ chuỗi expectation của HTTP test sang các assertion giàu biểu đạt của AssertJ. Dùng `RestTestClientResponse.from(...)` để tạo điểm vào, kiểm tra status và metadata của HTTP response, sau đó chọn `bodyText()`, `bodyJson()` hoặc `body()` theo kiểu nội dung. Khi cần assertion trên DTO đã deserialize, dùng `expectBody(...)` và áp dụng AssertJ trong callback hoặc trên kết quả trả về. Cách tổ chức này giữ cho test mô tả rõ hợp đồng HTTP mà vẫn tận dụng được khả năng so sánh object và dữ liệu của AssertJ.
