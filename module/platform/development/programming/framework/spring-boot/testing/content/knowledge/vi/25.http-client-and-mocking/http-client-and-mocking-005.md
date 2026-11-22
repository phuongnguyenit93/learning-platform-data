# Kiểm tra URL, HTTP method, header, query, body và số lần gọi của HTTP client

## 1. Mục tiêu: kiểm hợp đồng của yêu cầu gửi ra ngoài

Trong ứng dụng Spring Boot, một lớp HTTP client gọi dịch vụ bên ngoài có thể trả về một đối tượng Java đúng ở unit test nhưng vẫn gửi **sai URL**, **sai HTTP method**, **thiếu header**, **thiếu query parameter**, **body JSON sai kiểu** hoặc **gọi nhiều lần hơn thiết kế**. Những lỗi này không được phát hiện nếu ta chỉ mock một phương thức nghiệp vụ kiểu `when(gateway.fetch()).thenReturn(...)`.

Để kiểm đúng **outbound HTTP request**, cần chạy code client thật nhưng thay endpoint bên ngoài bằng một công cụ giả lập có thể **quan sát yêu cầu và cung cấp phản hồi có kiểm soát**. Trong Spring Boot 3.3, một lựa chọn phù hợp cho `RestClient` hoặc `RestTemplate` là **`@RestClientTest` + `MockRestServiceServer`**. Nó chặn các lệnh HTTP do client tương ứng tạo ra, so sánh chúng với kỳ vọng và trả phản hồi giả, **không mở socket HTTP thật**.

Ví dụ ý tưởng:

~~~java
server.expect(requestTo(
        "https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Request-Id", "test-req-1"))
    .andExpect(queryParam("warehouse", "HCM"))
    .andExpect(queryParam("includeReserved", "false"))
    .andRespond(withSuccess(
        "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}",
        MediaType.APPLICATION_JSON));

StockSnapshot result = client.fetchStock(
        "SKU-1", "HCM", false, "test-req-1");

assertEquals(12, result.available());
server.verify();
~~~

Đây là đoạn trích trong lớp test có imports tương ứng; ví dụ đầy đủ và biên dịch được ở mục 6. Một kỳ vọng tốt thường kiểm tra cả **request contract** lẫn **response mapping**. Nếu chỉ `andRespond(withSuccess(...))` mà không gọi `server.verify()`, một lệnh HTTP đáng lẽ phải gửi nhưng không được gửi có thể không khiến test thất bại.

**Kết quả cần đạt sau bài học:**

1. Phân biệt **kiểm thử một HTTP client outbound** với **kiểm thử REST controller inbound** bằng MockMvc.
2. Nắm phạm vi của `@RestClientTest` và `MockRestServiceServer`, cấu hình đúng `RestClient.Builder`.
3. Kiểm tra **scheme, host, port, path và URI đầy đủ** bằng `requestTo(...)`.
4. Kiểm tra **GET/POST/PUT/PATCH/DELETE** bằng `method(HttpMethod.XXX)`.
5. Kiểm tra header bắt buộc, header không được có, Content-Type và Accept bằng request matchers.
6. Kiểm tra query parameters, boolean/number/repeated values và cách URI encoding ảnh hưởng assertions.
7. Kiểm tra body JSON **theo cấu trúc**, dùng chế độ strict khi contract không chấp nhận trường dư.
8. Kiểm tra **đúng 0, 1, N lần gọi**, thêm trường hợp thiếu lượt gọi và request ngoài dự kiến.
9. Kiểm tra thứ tự nhiều requests, phản hồi 4xx/5xx, behavior retry khi thật sự được cấu hình.
10. Dựng ví dụ hoàn chỉnh Java 17 + Spring Boot **3.3.5** + Gradle + RestClient + JUnit Jupiter.
11. Hiểu giới hạn mock request factory và khi nào chuyển sang WireMock/OkHttp MockWebServer để có HTTP network thật.
12. Tránh test brittle, bỏ sót field quan trọng, hard-code secret, và vô tình gửi request tới API thật trong CI.

**Ngữ cảnh “HTTP client và giả lập”:** Đây là test hướng **client gọi dịch vụ bên ngoài**. Chúng ta không khởi động một API controller để test `/stocks`, không kết nối database và không dùng production credentials. Mục tiêu là chứng minh code client đã **tạo đúng request** và **đọc đúng response** trong phạm vi đã chọn.

**Phiên bản mẫu:** Java 17; Spring Boot **3.3.5**; Spring Framework **6.1.x**; Gradle và JUnit Jupiter. `RestClient` có từ Spring Framework 6.1. Với Spring Boot 2.x hoặc Spring Framework 5.x, có thể dùng `RestTemplate` hoặc HTTP client khác, nhưng không sao chép nguyên API `RestClient` của bài.

## 2. Chọn đúng tầng kiểm thử

| Tầng kiểm thử | Cái gì là thật? | Cái gì được giả lập? | Có socket HTTP thật? |
|---|---|---|---|
| Unit test mock nguyên `WarehouseHttpClient` bằng Mockito | Service logic gọi gateway | Toàn bộ HTTP gateway | Không |
| Unit test tự gọi một hàm tạo URI | Java URI building logic | Không có HTTP transport | Không |
| **`@RestClientTest` + `MockRestServiceServer`** | **RestClient/RestTemplate, URI, HTTP method, headers, body serialization, response deserialization** | HTTP response và request factory | **Không** |
| **MockWebServer / WireMock** với client thật | Client, TCP/HTTP, encoding/network request thực trong test | Dịch vụ bên ngoài tại localhost:randomPort | **Có** |
| Integration với sandbox API thật | Client + external integration | Ít hoặc không | Có, phụ thuộc mạng |
| `MockMvc` / `@WebMvcTest` | Controller inbound Spring MVC | Server request/response | Không cần socket |

**Sự khác biệt quan trọng nhất:** `MockMvc` kiểm **server nhận request**, còn `MockRestServiceServer` kiểm **client gửi request**. Tên "mock server" không có nghĩa Spring Boot đã khởi động một HTTP server. Đây là request factory thay thế trong nội bộ Spring Web client.

Theo tài liệu Spring Framework, mock web server có socket thực (WireMock, MockWebServer) thường phù hợp hơn khi cần kiểm cả chi tiết I/O của HTTP transport. `MockRestServiceServer` vẫn rất hữu ích cho các test nhanh về URI, method, headers, query, body và call count, vì không cần port hay Docker.

### 2.1. Tại sao không chỉ dùng Mockito.verify(...)?

~~~java
verify(remoteGateway, times(2)).fetchStock("SKU-1", "HCM");
~~~

Đây là snippet Mockito cho **lời gọi Java method**; nó không chứng minh method thực tế gửi `GET` hay `POST`, thêm query `includeReserved=false`, có `Accept: application/json` hay serialize body thành JSON nào. Dùng Mockito khi cần kiểm lớp nghiệp vụ gọi collaborator đúng; dùng mock HTTP request layer khi cần xác nhận **HTTP contract**.

Cũng không nên mock từng method của `RestClient` fluent API bằng Mockito nếu có thể dùng `MockRestServiceServer`. Mock một chuỗi `.get().uri().header().retrieve().body()` thường tạo nhiều mocks dễ sai và chỉ kiểm implementation details, trong khi test request thực do `RestClient` sinh ra rõ ràng và bền hơn.

## 3. Những phần của một outbound HTTP request cần kiểm

Ví dụ một request:

~~~http
POST /api/reservations HTTP/1.1
Host: warehouse.example.test
Accept: application/json
Content-Type: application/json
X-Request-Id: req-100

{"sku":"SKU-1","quantity":3,"warehouse":"HCM"}
~~~

Các chiều cần kiểm có thể tách thành:

| Thành phần | Rủi ro thường gặp | Assertion chủ đạo |
|---|---|---|
| **URL** | Sai scheme/host/base path, thiếu path variable, đi nhầm environment | `requestTo("https://...")` |
| **Method** | GET bị đổi thành POST/PUT/DELETE, mất idempotency | `method(HttpMethod.GET)` |
| **Header** | Thiếu auth/correlation id, sai Accept, Content-Type | `header(...)`, `headerDoesNotExist(...)`, `content().contentTypeCompatibleWith(...)` |
| **Query** | Thiếu param, sai boolean, sai encoding, lặp/khác thứ tự | `queryParam(name, values...)`, exact URI/custom matcher |
| **Body** | JSON field thiếu/thừa, sai field name/type, payload trống | `content().json(expected, true)`, `content().string(...)` |
| **Số lần gọi** | Bỏ sót lệnh gọi, gọi thừa, retry ngoài ý muốn | `ExpectedCount.times(n)`, `server.verify()` |
| **Thứ tự** | Tạo reservation trước khi lấy stock khi nghiệp vụ yêu cầu ngược lại | Nhiều `expect(...)` theo thứ tự |
| **Response** | 404/503 không được xử lý, JSON mapping sai | `withStatus(...)`, `withSuccess(...)`, assertions |

Nên xác định **contract** trước khi viết test. Một hệ thống có thể không quan tâm thứ tự query parameters, nhưng lại yêu cầu đúng một tập key/value. Một HTTP server thường không quan tâm thứ tự object keys trong JSON. Đừng biến thứ tự không có trong contract thành điều kiện bắt buộc, khiến test hỏng khi HTTP client được nâng cấp.

### 3.1. URL phải rõ base URL và path

Nếu code cấu hình `RestClient.Builder.baseUrl("https://warehouse.example.test/api")`, expect URL cho `RestClient` trong `@RestClientTest` thường phải dùng **URI đầy đủ**. Spring Boot 3.3 docs nói rõ:
- Khi test bean dùng **RestClient.Builder**, `MockRestServiceServer` expectation phải dùng **full URI**.
- Khi bean dùng **RestTemplateBuilder.rootUri(...)**, expectation thường bỏ phần root URI theo cách customizer xử lý.
- Khi dùng RestTemplateBuilder không có rootUri, expectation vẫn dùng full URI.

Vì vậy không áp dụng máy móc `requestTo("/stocks/SKU-1")` vào RestClient đã cấu hình baseUrl rồi kỳ vọng test pass. Nếu gặp lỗi "Request URI expected ..., was ...", hãy kiểm đúng builder và URL contract, không sửa mock để che đi base path bị mất.

### 3.2. Method gắn với semantics

HTTP GET lấy dữ liệu, POST tạo tài nguyên, DELETE xóa/hủy; đây là quy ước chứ không thay thế tài liệu API cụ thể. Test cần nêu đúng `HttpMethod`:

~~~java
server.expect(requestTo("https://warehouse.example.test/api/reservations"))
    .andExpect(method(HttpMethod.POST))
    .andRespond(withSuccess(
        "{\"reservationId\":\"R-1\",\"status\":\"ACCEPTED\"}",
        MediaType.APPLICATION_JSON));
~~~

Snippet này cố ý chỉ kiểm URL/method; bản đầy đủ còn kiểm headers/body. Một request URL đúng nhưng method sai sẽ bị matcher chặn.

### 3.3. Headers: kiểm sự hiện diện, giá trị và kiểu media

`X-Request-Id`, `Authorization`, `Accept`, `Content-Type`, idempotency key hay tenant ID có thể là phần contract. Với request header thông thường:

~~~java
.andExpect(header("X-Request-Id", "req-100"))
.andExpect(header("Accept", "application/json"))
~~~

`Accept` mô tả response media types client có thể nhận; `Content-Type` mô tả định dạng request body. Đừng hoán đổi chúng. Với body JSON của POST, ta có thể dùng:

~~~java
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
~~~

`contentTypeCompatibleWith` hữu ích khi Content-Type có charset parameters và bạn không cần so raw header string tuyệt đối. Đối với header phải **vắng mặt**, Spring có `headerDoesNotExist("Authorization")`. Tuy nhiên, không khẳng định client không bao giờ được gửi Authorization nếu production contract có authentication; hãy thiết kế fixture có token giả và kiểm header thật ở tầng cần thiết.

**HTTP header names không phân biệt chữ hoa/thường** theo giao thức. Đừng tạo test chỉ dựa vào casing chính xác của "Content-Type" so với "content-type", hoặc thứ tự headers khi API không yêu cầu.

### 3.4. Query parameters: kiểm cả giá trị và tập parameters

~~~java
.andExpect(queryParam("warehouse", "HCM"))
.andExpect(queryParam("includeReserved", "false"))
~~~

`queryParam(String, String...)` có thể kiểm những giá trị được nêu mà **không tự bảo đảm không có giá trị dư** ở cùng key hoặc không có query keys khác. Nếu contract yêu cầu request URI chính xác, kết hợp với `requestTo("https://...?warehouse=HCM&includeReserved=false")` sẽ bắt các key/value dư và serialized URI khác.

Nhưng exact URI matcher cũng nhạy với **thứ tự query parameters**. Về mặt HTTP, `?a=1&b=2` và `?b=2&a=1` thường có ý nghĩa tương đương cho API không nhạy thứ tự. Khi contract chỉ yêu cầu tập parameters, hãy dùng **custom `RequestMatcher`** phân tích URI/query theo key/value thay vì hard-code nguyên query string. Khi query có repeated keys như `tag=java&tag=spring`, hãy assert **toàn bộ danh sách** nếu số lần lặp và thứ tự có ý nghĩa.

**Encoding:** Tránh nối thủ công chuỗi như `"?q=" + userInput`. Ký tự khoảng trắng, `&`, `?`, `#`, dấu tiếng Việt hoặc ký tự Unicode có thể làm URL sai hoặc thay nghĩa query. Dùng `UriBuilder.queryParam(...)` và URI variables; viết test thực tế với giá trị chứa khoảng trắng/`&` khi endpoint hỗ trợ. Cần so **decoded values** hay **raw encoding** phải theo contract cụ thể, không giả định mọi library ghi `%20` và `+` giống nhau.

### 3.5. JSON body: strict hay lenient?

`MockRestRequestMatchers.content().json(...)` parse cả expected và actual body thành JSON, nên không nhạy với whitespace hay thứ tự keys trong object. Hai chế độ:

~~~java
.andExpect(content().json(
        "{\"sku\":\"SKU-1\",\"quantity\":3,\"warehouse\":\"HCM\"}",
        true))
~~~

Trong Spring Framework 6.1, overload `json(String, boolean)` sử dụng JSONassert:
- `strict=true`: JSON có cấu trúc đúng, **không chấp nhận object properties dư**, và thứ tự elements trong array được xét.
- `strict=false` hoặc overload `json(String)`: lenient; có thể bỏ qua extra object fields, array ordering linh hoạt.
- Không so sánh JSON string literal thuần bằng `content().string(...)` trừ khi raw formatting/chữ ký payload đúng là contract.

Đừng lạm dụng lenient nếu API không cho phép field mới hoặc bảo mật yêu cầu không serialize nhầm secret. Cũng đừng dùng strict nếu API cho phép thêm optional fields và array order không có ý nghĩa. Chọn mode dựa trên hợp đồng, không vì test dễ pass hơn.

**JSON number vs string:** Trong payload, `{"quantity":3}` và `{"quantity":"3"}` khác type. `content().json` kiểm cấu trúc phù hợp; test thêm `jsonPath("$.quantity")` nếu một field có rule đặc biệt, hoặc parse body bằng ObjectMapper khi cần kiểm thứ tự/tổng hợp phức tạp.

## 4. Số lần gọi chính xác: 0, 1, N và unexpected request

**`MockRestServiceServer` không chỉ stub response.** Khi đăng ký expectation, ta còn quy định số lần gọi.

### 4.1. Đúng một lần

~~~java
server.expect(requestTo("https://warehouse.example.test/api/stocks/SKU-1"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        "{\"sku\":\"SKU-1\"}", MediaType.APPLICATION_JSON));

client.fetch(...);
server.verify();
~~~

Snippet ý tưởng, `client.fetch` cần định nghĩa trong project phù hợp. Mặc định một `expect(requestTo(...))` đòi **một request**. `ExpectedCount.once()` có thể viết tường minh.

### 4.2. Chính xác N lần

~~~java
server.expect(
        ExpectedCount.times(2),
        requestTo("https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}",
        MediaType.APPLICATION_JSON));

client.fetchStock("SKU-1", "HCM", false, "req-a");
client.fetchStock("SKU-1", "HCM", false, "req-b");

server.verify();
~~~

Đây là snippet từ logic của test hoàn chỉnh; nếu cùng expectation còn matcher header bằng một request ID cố định thì hai calls phải dùng cùng ID, hoặc tạo matcher linh hoạt/hai expectations phù hợp. Với ví dụ trên chỉ matcher URL/method nên hai request IDs khác nhau không làm expectation thất bại.

`times(2)` bảo đảm đúng 2 request khớp; **verify() phát hiện thiếu request**. Request thêm vượt số lượng có thể bị mock server ném AssertionError ngay khi client cố thực thi; đừng chờ tới verify mới kiểm mọi trường hợp.

### 4.3. Không được gọi API

Nếu nghiệp vụ từ chối một lệnh hợp lệ ở local layer, ví dụ `quantity <= 0`, nó có thể trả Optional.empty mà không gửi HTTP. Trong test, **không đăng ký expectation**, gọi method đó rồi `server.verify()`: một outbound request không mong đợi sẽ bị mock server phát hiện khi request được phát ra.

Một số API cho `ExpectedCount.never()`, nhưng việc không khai báo expectation nào trong một mock server đã reset cũng đủ để diễn đạt **không có HTTP request nào** trong phạm vi client được bind.

### 4.4. Thiếu một lượt gọi phải làm test đỏ

~~~java
server.expect(
        ExpectedCount.times(2),
        requestTo("https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
    .andRespond(withSuccess(
        "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}",
        MediaType.APPLICATION_JSON));

client.fetchStock("SKU-1", "HCM", false, "req-only-one");

assertThrows(AssertionError.class, server::verify);
~~~

Đây là một **negative test của chính cơ chế expectation**, nên `assertThrows(AssertionError.class, ...)` là expected behavior, không phải một test cố ý fail trên CI. Những test nghiệp vụ bình thường phải gọi `server.verify()` không bọc assertThrows để phát hiện thiếu request.

**Request order:** Mặc định `MockRestServiceServer` xét thứ tự khai báo của những kỳ vọng khác nhau. Khi một expectation có expected count lớn hơn 1, **lần đầu** của nó cần xuất hiện đúng thứ tự, còn các lần lặp sau đó có thể xen kẽ theo quy tắc của expectation manager. Chỉ dùng `ignoreExpectOrder(true)` nếu contract thật sự không yêu cầu thứ tự; không bật nó chỉ vì test đang báo thứ tự sai.

## 5. Cấu trúc dự án mẫu

Project mô phỏng một HTTP client gọi Warehouse API bên ngoài qua `RestClient`. Các behavior được thiết kế:

- `GET /api/stocks/{sku}?warehouse=HCM&includeReserved=false` trả JSON stock.
- `POST /api/reservations` gửi JSON gồm sku, quantity, warehouse và nhận JSON receipt.
- `DELETE /api/reservations/{id}` chỉ gửi method + header, **không có body**.
- `reserveIfPositive(...)` kiểm `quantity`; nếu số lượng không dương thì **không gửi HTTP request**.
- `RestClient` được tạo từ **Boot-provided `RestClient.Builder`** để `MockRestServiceServer` trong `@RestClientTest` chặn được outbound requests.
- Test dùng **exact URL**, HTTP method, request headers, query parameters, strict JSON body, expected call count, request order và xử lý 404.

### 5.1. Cấu trúc file

~~~text
settings.gradle
build.gradle
src/main/java/demo/httpmock/HttpMockApplication.java
src/main/java/demo/httpmock/StockSnapshot.java
src/main/java/demo/httpmock/ReservationCommand.java
src/main/java/demo/httpmock/ReservationReceipt.java
src/main/java/demo/httpmock/WarehouseHttpClient.java
src/test/java/demo/httpmock/WarehouseHttpClientTest.java
~~~

**Không cần** `application.properties` chứa URL production, không cần PostgreSQL/Testcontainers, không cần socket HTTP. Mọi expectation trong test được bind tới mock request factory, nên tên miền `warehouse.example.test` chỉ là **fixture URL**. Không có request tới DNS/host thật khi dùng cùng RestClient được builder quản lý.

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'outbound-http-client-contract-test'
~~~

### 5.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Giải thích:
- `spring-boot-starter-web` trong Spring Boot 3.3 có **Spring Web RestClient**, Spring HTTP converters và Jackson phục vụ JSON records. Dù starter-web chứa embedded servlet server, `@RestClientTest` **không khởi động HTTP server**.
- `spring-boot-starter-test` có Spring Boot Test, Spring Test `MockRestServiceServer`, JUnit Jupiter, AssertJ, JSONassert và các công cụ assertions.
- Spring Boot BOM quản lý versions tương thích; không pin thêm Spring Framework 6.1 artifact version riêng.
- Java 17 hỗ trợ records và text blocks dùng trong các test.
- Nếu ứng dụng hiện tại chỉ dùng `spring-web`/`spring-boot-starter-json` và không cần server, có thể tinh gọn dependencies riêng; ví dụ ưu tiên cấu hình rõ và dễ chạy.

### 5.4. Application class

**src/main/java/demo/httpmock/HttpMockApplication.java**

~~~java
package demo.httpmock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpMockApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpMockApplication.class, args);
    }
}
~~~

Trong `@RestClientTest`, Spring Boot tìm primary application configuration theo package hierarchy rồi chỉ nạp slice dành cho HTTP client. Không vì có `@SpringBootApplication` mà test tự khởi động mọi controller/service/repository hay kết nối API thật.

### 5.5. DTOs: records nhận và gửi JSON

**src/main/java/demo/httpmock/StockSnapshot.java**

~~~java
package demo.httpmock;

public record StockSnapshot(
        String sku,
        String warehouse,
        int available) {
}
~~~

**src/main/java/demo/httpmock/ReservationCommand.java**

~~~java
package demo.httpmock;

public record ReservationCommand(
        String sku,
        int quantity,
        String warehouse) {
}
~~~

**src/main/java/demo/httpmock/ReservationReceipt.java**

~~~java
package demo.httpmock;

public record ReservationReceipt(
        String reservationId,
        String status) {
}
~~~

Ba records là Java 17 types. Với Jackson phù hợp, response JSON fields được ánh xạ vào record components; request record được serialize thành JSON object với keys `sku`, `quantity` và `warehouse`. Test không giả định thứ tự JSON object properties khi dùng `content().json`.

Nếu API bên ngoài dùng field names khác, thêm Jackson annotations/converters trong client theo contract rồi viết test phản ánh đúng wire format. Không đổi test expected JSON theo implementation lỗi để “chạy xanh”.

### 5.6. HTTP client production code

**src/main/java/demo/httpmock/WarehouseHttpClient.java**

~~~java
package demo.httpmock;

import java.util.Optional;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class WarehouseHttpClient {

    public static final String BASE_URL =
            "https://warehouse.example.test/api";

    private final RestClient restClient;

    public WarehouseHttpClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl(BASE_URL)
                .build();
    }

    public StockSnapshot fetchStock(
            String sku,
            String warehouse,
            boolean includeReserved,
            String requestId) {

        return restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/stocks/{sku}")
                        .queryParam("warehouse", warehouse)
                        .queryParam("includeReserved", includeReserved)
                        .build(sku))
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId)
                .retrieve()
                .body(StockSnapshot.class);
    }

    public ReservationReceipt reserve(
            ReservationCommand command,
            String requestId) {

        return restClient.post()
                .uri("/reservations")
                .accept(MediaType.APPLICATION_JSON)
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId)
                .body(command)
                .retrieve()
                .body(ReservationReceipt.class);
    }

    public Optional<ReservationReceipt> reserveIfPositive(
            ReservationCommand command,
            String requestId) {

        if (command.quantity() <= 0) {
            return Optional.empty();
        }

        return Optional.ofNullable(
                reserve(command, requestId));
    }

    public void cancel(String reservationId, String requestId) {
        restClient.delete()
                .uri("/reservations/{id}", reservationId)
                .header("X-Request-Id", requestId)
                .retrieve()
                .toBodilessEntity();
    }
}
~~~

**Thiết kế có chủ đích:**

1. Constructor nhận **`RestClient.Builder` do Spring Boot cấp**, không gọi thẳng `RestClient.create()` hay `new RestTemplate()` trong constructor. Nhờ vậy Boot `@RestClientTest` có thể customizer/bind mock request factory vào client.
2. `baseUrl` là fixture cố định để người đọc dễ thấy expected URI. Trong project thực, nên inject endpoint từ `@ConfigurationProperties` và override bằng test configuration; không hard-code URL production.
3. `fetchStock` thêm path variable, hai query params, Accept header và request ID; dùng `uriBuilder` thay nối user input vào URL.
4. `reserve` là POST có body JSON, Accept và Content-Type riêng. Client không tự thêm Authorization trong ví dụ; một API cần auth sẽ phải cấu hình header/tokens giả trong tests.
5. `reserveIfPositive` là một **nhánh nghiệp vụ cục bộ** không cho gửi request khi quantity <= 0. Điều đó cho phép test **zero outbound calls** có giá trị thực tế.
6. `cancel` gửi DELETE không body và dùng `toBodilessEntity()` để **kích hoạt request/exchange** dù không cần response body. Chỉ viết `retrieve()` mà không có terminal operation sẽ không thực thi exchange theo RestClient API.
7. Không tự cấu hình retries trong client. Với 404, RestClient `retrieve()` mặc định ném exception, không tự retry; test dưới đây kiểm một request chính xác.
8. Thư viện JSON converter của Spring/Jackson xử lý records; test kiểm body đã được serialize ra HTTP request, không chỉ kiểm object trước khi gửi.

**Một lưu ý về immutability:** RestClient đã build là client dùng lại được, không nên thay builder cùng lúc từ nhiều threads rồi kỳ vọng mỗi test có cấu hình riêng. Trong ví dụ một client bean được tạo một lần; `MockRestServiceServer` test reset expectations giữa methods.

## 6. File test hoàn chỉnh: kiểm đủ sáu chiều contract

**src/test/java/demo/httpmock/WarehouseHttpClientTest.java**

~~~java
package demo.httpmock;

import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

@RestClientTest(WarehouseHttpClient.class)
class WarehouseHttpClientTest {

    @Autowired
    WarehouseHttpClient client;

    @Autowired
    MockRestServiceServer server;

    @BeforeEach
    void resetExpectations() {
        server.reset();
    }

    @Test
    void getChecksFullUrlMethodHeadersQueryAndResponse() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Request-Id", "req-1"))
            .andExpect(header(HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE))
            .andExpect(headerDoesNotExist(
                    HttpHeaders.AUTHORIZATION))
            .andExpect(queryParam("warehouse", "HCM"))
            .andExpect(queryParam("includeReserved", "false"))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-1","warehouse":"HCM","available":12}
                    """,
                    MediaType.APPLICATION_JSON));

        StockSnapshot stock = client.fetchStock(
                "SKU-1", "HCM", false, "req-1");

        assertNotNull(stock);
        assertEquals("SKU-1", stock.sku());
        assertEquals("HCM", stock.warehouse());
        assertEquals(12, stock.available());

        server.verify();
    }

    @Test
    void getWithOtherQueryValuesIsChecked() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/stocks/SKU-2?warehouse=DN&includeReserved=true"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(queryParam("warehouse", "DN"))
            .andExpect(queryParam("includeReserved", "true"))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-2","warehouse":"DN","available":0}
                    """,
                    MediaType.APPLICATION_JSON));

        StockSnapshot stock = client.fetchStock(
                "SKU-2", "DN", true, "req-2");

        assertNotNull(stock);
        assertEquals(0, stock.available());
        assertEquals("DN", stock.warehouse());
        server.verify();
    }

    @Test
    void postChecksMethodHeadersAndStrictJsonBody() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/reservations"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header("X-Request-Id", "req-3"))
            .andExpect(header(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(content().json(
                    """
                    {"sku":"SKU-1","quantity":3,"warehouse":"HCM"}
                    """,
                    true))
            .andRespond(withSuccess(
                    """
                    {"reservationId":"R-100","status":"ACCEPTED"}
                    """,
                    MediaType.APPLICATION_JSON));

        ReservationReceipt receipt = client.reserve(
                new ReservationCommand("SKU-1", 3, "HCM"),
                "req-3");

        assertNotNull(receipt);
        assertEquals("R-100", receipt.reservationId());
        assertEquals("ACCEPTED", receipt.status());
        server.verify();
    }

    @Test
    void getIsSentExactlyTwiceWhenExpected() {
        server.expect(
                times(2),
                requestTo(
                        "https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-1","warehouse":"HCM","available":12}
                    """,
                    MediaType.APPLICATION_JSON));

        StockSnapshot first = client.fetchStock(
                "SKU-1", "HCM", false, "req-4a");
        StockSnapshot second = client.fetchStock(
                "SKU-1", "HCM", false, "req-4b");

        assertEquals(12, first.available());
        assertEquals(12, second.available());
        server.verify();
    }

    @Test
    void verifyDetectsWhenSecondExpectedRequestIsMissing() {
        server.expect(
                times(2),
                requestTo(
                        "https://warehouse.example.test/api/stocks/SKU-1?warehouse=HCM&includeReserved=false"))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-1","warehouse":"HCM","available":12}
                    """,
                    MediaType.APPLICATION_JSON));

        client.fetchStock("SKU-1", "HCM", false, "req-5");

        // Đây là negative test của chính expectation engine:
        assertThrows(AssertionError.class, server::verify);
    }

    @Test
    void nonPositiveQuantitySendsNoHttpRequest() {
        // Mock server đã reset và không có expectation.
        Optional<ReservationReceipt> result =
                client.reserveIfPositive(
                        new ReservationCommand(
                                "SKU-1", 0, "HCM"),
                        "req-6");

        assertTrue(result.isEmpty());
        server.verify();
    }

    @Test
    void deleteChecksMethodHeaderAndEmptyBody() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/reservations/R-100"))
            .andExpect(method(HttpMethod.DELETE))
            .andExpect(header("X-Request-Id", "req-7"))
            .andExpect(content().string(""))
            .andRespond(withStatus(HttpStatus.NO_CONTENT));

        client.cancel("R-100", "req-7");

        server.verify();
    }

    @Test
    void notFoundRaisesHttpClientErrorWithOneRequest() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/stocks/ABSENT?warehouse=HCM&includeReserved=false"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                          {"error":"stock not found"}
                          """));

        assertThrows(
                HttpClientErrorException.NotFound.class,
                () -> client.fetchStock(
                        "ABSENT", "HCM", false, "req-8"));

        server.verify();
    }

    @Test
    void separateExpectationsCheckRequestOrder() {
        server.expect(requestTo(
                "https://warehouse.example.test/api/stocks/SKU-3?warehouse=HCM&includeReserved=false"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-3","warehouse":"HCM","available":9}
                    """,
                    MediaType.APPLICATION_JSON));

        server.expect(requestTo(
                "https://warehouse.example.test/api/reservations"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(content().json(
                    """
                    {"sku":"SKU-3","quantity":1,"warehouse":"HCM"}
                    """,
                    true))
            .andRespond(withSuccess(
                    """
                    {"reservationId":"R-103","status":"ACCEPTED"}
                    """,
                    MediaType.APPLICATION_JSON));

        StockSnapshot stock = client.fetchStock(
                "SKU-3", "HCM", false, "req-9a");
        ReservationReceipt receipt = client.reserve(
                new ReservationCommand("SKU-3", 1, "HCM"),
                "req-9b");

        assertEquals(9, stock.available());
        assertEquals("R-103", receipt.reservationId());

        server.verify();
    }
}
~~~

**Đếm đúng: 9 phương thức `@Test`**, cùng một `@BeforeEach` không phải test. Trong phương thức thứ năm, `assertThrows(AssertionError.class, server::verify)` **cố ý mong thấy lỗi xác minh** vì mới gọi một lần khi yêu cầu hai lần; phương thức JUnit vẫn PASS nếu mock server hoạt động đúng. Tất cả các test khác gọi `server.verify()` trực tiếp và chỉ PASS khi expectations đã được đáp ứng.

**Vì sao dùng `@RestClientTest(WarehouseHttpClient.class)`?** Slice chọn bean client này và cấu hình `RestClient.Builder`, JSON conversion cùng một MockRestServiceServer. Những `@Service` hay `@Repository` khác không được auto-scan vào slice. Với class production nhận builder qua constructor, mock server được gắn vào đúng client khi bean được tạo. Nếu tự tạo client ngoài context bằng `RestClient.create()` sau đó, nó có thể **không** sử dụng mock server và đi ra mạng thật.

**Vì sao `server.reset()` trong `@BeforeEach`?** Để các expectation/counters độc lập với nhau, đặc biệt vì có một negative test cố ý để lại một kỳ vọng chưa đủ hai lượt gọi. Spring Boot có test support reset cho mock server, nhưng reset tường minh trong ví dụ làm ranh giới test dễ hiểu. Không gọi reset **sau khi vừa đăng ký** expectations và trước client call, nếu không bạn sẽ xóa chính expectations cần kiểm.

### 6.1. Test 1 kiểm đủ URL, method, headers và query

`requestTo(...)` so sánh full URI và bắt sai scheme, host, `/api` prefix, path variable hoặc serialized query. `method(GET)` bảo vệ HTTP method. `header("X-Request-Id", "req-1")` bảo vệ correlation header. `Accept: application/json` được kiểm tường minh; `Authorization` được kiểm **không tồn tại** vì client ví dụ không dùng authentication. Hai `queryParam` bảo vệ ý nghĩa riêng của từng query value.

JSON phản hồi có ba thuộc tính sku/warehouse/available; client `RestClient.retrieve().body(StockSnapshot.class)` giải mã thành Java record. Nếu request match nhưng DTO mapping sai, assertion trên Java record vẫn bắt bug. Đây là lý do nên kiểm **hai chiều**: outbound request và inbound response.

### 6.2. Test 2 kiểm query values khác nhau

Một test chỉ dùng `includeReserved=false` có thể không bắt được code hard-code false. Test thứ hai dùng **true** và warehouse `DN`; cả exact URL và `queryParam` phải cho giá trị mới. Nếu client bỏ truyền boolean hoặc luôn dùng HCM, expectation sẽ fail.

Query values nên bao phủ biên nghiệp vụ: empty string, null parameter policy, repeated values, Unicode và ký tự cần encode. Tuy nhiên không thêm hàng chục test vì độ dài URL; chọn các trường hợp có rủi ro thực.

### 6.3. Test 3 kiểm POST body bằng strict JSON

`content().json(expected, true)` kiểm các field và types sau khi Jackson serialize `ReservationCommand`, không phụ thuộc whitespace hay thứ tự object keys. Nó phát hiện:
- `quantity` bị serialized thành String `"3"` thay vì number `3`;
- sai key `warehouseId` thay vì `warehouse`;
- thiếu `sku` hoặc body có property dư;
- không gửi body, hoặc gửi JSON không hợp lệ.

`content().contentTypeCompatibleWith(APPLICATION_JSON)` kiểm định dạng request. `header(HttpHeaders.ACCEPT, APPLICATION_JSON_VALUE)` kiểm loại response client muốn nhận. Phản hồi được decode thành `ReservationReceipt` với `reservationId` và `status`.

### 6.4. Test 4 và 5 kiểm chính xác số lượt gọi

Test 4 đăng ký `times(2)`, thực hiện 2 lần fetchStock rồi `server.verify()`. Nếu code chỉ gọi 1 hoặc gọi 3 lần, test không còn thoả đúng expected count. Test 5 cố tình đăng ký 2 nhưng gọi 1; `server.verify()` ném AssertionError và được **assertThrows** bắt lại. Nhờ đó người học thấy vì sao không nên chỉ dừng test sau khi nhận response giả mà quên gọi verify.

**Không ghi “times(2)” rồi suy ra có đúng hai HTTP requests khi client đang dùng một RestClient khác không được mock server bind.** Điều kiện căn bản là `MockRestServiceServer` phải chặn đúng HTTP client instance. Với Boot `@RestClientTest` và builder do Spring inject như bài mẫu, điều kiện này được đáp ứng.

### 6.5. Test 6 kiểm zero outbound calls

`reserveIfPositive` với quantity=0 trả Optional.empty trước khi đến RestClient. `MockRestServiceServer` không đăng ký expectation nào; nếu code vô tình gửi request, mock request factory sẽ báo có request không mong đợi. Nếu chỉ dùng Mockito mock của chính WarehouseHttpClient, bạn không thể chứng minh request HTTP bên dưới thật sự không phát ra.

Đây là test có ý nghĩa nghiệp vụ, không phải một test trống: nó gọi một public method chứa logic chặn HTTP, sau đó kiểm kết quả **và** không có HTTP side effects.

### 6.6. Test 7 kiểm DELETE và body rỗng

`cancel` dùng `DELETE /api/reservations/R-100`, gửi `X-Request-Id`, không gửi JSON body. Expectation `content().string("")` kiểm content bytes giải mã UTF-8 là chuỗi rỗng; response giả có HTTP 204 No Content. Client gọi `.retrieve().toBodilessEntity()` để thực sự thực thi exchange, tránh lỗi code chỉ xây request nhưng chưa gửi.

### 6.7. Test 8 kiểm 404 và không có retry ngầm

Phản hồi `withStatus(HttpStatus.NOT_FOUND)` mô phỏng HTTP status lỗi. RestClient `retrieve()` theo mặc định ném `HttpClientErrorException.NotFound`, và test assert loại exception đó. Một expectation duy nhất rồi `server.verify()` còn chứng minh code **không tự thực hiện lần GET thứ hai** trong kịch bản này.

Nếu ứng dụng cấu hình retry rõ ràng, test phải đổi sang expected attempts và những response trước/sau; không tự khẳng định mọi 404 đều phải được retry. Nhiều hệ thống chỉ retry lỗi tạm thời như 503/429, không retry 400/404.

### 6.8. Test 9 kiểm thứ tự các yêu cầu

Hai expectations được khai báo **GET stock trước, POST reservation sau**. Code thực thi đúng thứ tự và xác minh response mapping của cả hai. Khi có nghiệp vụ “phải kiểm tra tồn kho trước khi đặt chỗ”, thứ tự có thể là phần contract. Nhưng nếu hai calls độc lập và có thể chạy parallel, test không nên tự áp một thứ tự cứng; xem phần về order-independent expectations và mock web server.

## 7. Chạy test và kết quả dự kiến

Nếu dự án có **Gradle Wrapper**:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu bạn chỉ tạo `build.gradle`, `settings.gradle` và các source files trong bài mà **chưa tạo Gradle Wrapper scripts/JAR**, `./gradlew` chưa tồn tại. Dùng Gradle tương thích để tạo Wrapper hoặc tạm chạy `gradle test`. Lệnh chạy riêng test class:

~~~bash
./gradlew test --tests demo.httpmock.WarehouseHttpClientTest
~~~

Project ví dụ có **chính xác 9 JUnit Jupiter test methods**, dự kiến PASS khi các imports, dependencies và source được tạo đúng; không có `@Disabled` và không cần Docker/HTTP server. Đây là **kỳ vọng kiểm tra từ source**, không phải tuyên bố bộ test đã được thực thi trong môi trường đọc bài.

Báo cáo Gradle thường có tại:

~~~text
build/reports/tests/test/index.html
~~~

| Test method | Contract chính |
|---|---|
| `getChecksFullUrlMethodHeadersQueryAndResponse` | Full URL, GET, header, query và response |
| `getWithOtherQueryValuesIsChecked` | Không hard-code query values |
| `postChecksMethodHeadersAndStrictJsonBody` | POST, Accept, Content-Type, strict JSON body |
| `getIsSentExactlyTwiceWhenExpected` | Exactly 2 outbound calls |
| `verifyDetectsWhenSecondExpectedRequestIsMissing` | Chứng minh verify phát hiện thiếu calls |
| `nonPositiveQuantitySendsNoHttpRequest` | Zero outbound calls |
| `deleteChecksMethodHeaderAndEmptyBody` | DELETE, request header, empty body |
| `notFoundRaisesHttpClientErrorWithOneRequest` | 404 exception, exactly 1 call |
| `separateExpectationsCheckRequestOrder` | GET trước POST, hai response |

**Không tạo snapshot stdout tùy ý.** Gradle có thể ghi thêm logs của Spring context, các warnings hoặc thông tin test; kết quả xác định ở đây là **số JUnit test methods và assertions cần đạt**.

## 8. Negative tests: phát hiện từng loại sai hợp đồng

Một kỹ thuật review quan trọng là chủ động đưa một “mutation” nhỏ vào code client rồi xem test nào cần fail. Không để mutation trong production; mục đích là kiểm bộ test có thật sự nhạy với bug.

| Mutation giả định | Test cần phát hiện |
|---|---|
| Đổi `BASE_URL` từ HTTPS sang HTTP | `requestTo` full URI |
| Bỏ prefix `/api` | `requestTo` full URI |
| Đổi `.get()` thành `.post()` cho stock | `method(GET)` |
| Bỏ `X-Request-Id` | `header(...)` |
| Bỏ `.accept(APPLICATION_JSON)` | `header(Accept, ...)` |
| Bỏ `includeReserved` hoặc luôn dùng false | `queryParam`, exact URI, test query true |
| Đổi `quantity` từ int thành String qua payload mapper | `content().json(..., true)` |
| Bổ sung property không mong muốn vào JSON body | Strict JSON matcher |
| Call `fetchStock` hai lần khi contract đòi một | Extra request error / `times(1)` |
| Bỏ hẳn một request mà test cần hai | `server.verify()` phát hiện |
| Chuyển POST reservation lên trước GET stock | Order-sensitive expectations |
| Tự retry 404 không được cấu hình | One-call expectation |
| Gửi DELETE với body không rỗng | `content().string("")` |
| Không gọi terminal operation `.body()`/`.toBodilessEntity()` | `server.verify()` thấy thiếu request |

**Lưu ý:** Nếu mutation là sai ở **response handling** (ví dụ `StockSnapshot.available` luôn bị gán 0), chỉ kiểm outbound requests là chưa đủ. Các assertions trên `StockSnapshot`/`ReservationReceipt` là phần bảo vệ response mapping và business adapter.

### 8.1. Không nên biến test thành bản copy của implementation

Nếu test xây expected URL bằng **cùng một helper function** đang được code production sử dụng để tạo URL, một bug trong helper có thể làm expected và actual cùng sai, khiến test xanh giả. Trong project mẫu, expected URLs là **literal contract values** trong test, không gọi lại hàm tạo URI của client.

Tương tự, không nên serialize `ReservationCommand` bằng **cùng ObjectMapper với client** để tạo expected JSON rồi so, nếu mục tiêu là kiểm tên field/kiểu đúng theo external API contract. Một expected JSON độc lập giúp phát hiện code serializer sai.

### 8.2. Mock response không thay thế test mapping lỗi

`MockRestServiceServer` có thể mô phỏng HTTP 400/401/404/409/429/500/503 và responses khác nhau. Client nên có policy rõ cho:
- 400/422: validation errors, thường không retry.
- 401/403: auth errors, kiểm lỗi đúng; không log token.
- 404: tài nguyên không có, quyết định trả Optional.empty hay throw.
- 409: conflict/idempotency semantics.
- 429/503: có thể retry khi policy/resilience layer được cấu hình.
- malformed JSON: có thể ném `RestClientException`/message conversion exception; test behavior phù hợp.
- response body rỗng 204/202: không gọi `.body(SomeRequiredDto.class)` rồi dùng object null mà không kiểm.

Nếu app dùng Spring Retry/Resilience4j, hãy test **đúng số attempts thực** và backoff policy, không thêm `times(3)` theo trực giác. Tránh `Thread.sleep` trong test để kiểm retry; dùng test clocks/schedulers hoặc cấu hình backoff nhỏ, deterministic.

## 9. RestClient, RestTemplate và WebClient không được mock giống nhau

### 9.1. RestClient của Spring 6.1 (bài mẫu)

`RestClient` là HTTP client đồng bộ có fluent API. `MockRestServiceServer` hỗ trợ `MockRestServiceServer.bindTo(RestClient.Builder)` từ Spring Framework 6.1; Spring Boot 3.3 `@RestClientTest` auto-configure builder và mock server.

**Không khởi tạo client ngoài builder được Spring quản lý trong test** nếu định dùng auto-configured mock. Ví dụ sai về test setup:

~~~java
// Trong bean under test, tránh kiểu khởi tạo này
// nếu muốn Boot @RestClientTest bind mock server:
RestClient client = RestClient.create(
        "https://warehouse.example.test/api");
~~~

Nếu production thật sự phải dùng client được tạo thủ công, bạn có thể tự khởi tạo một builder, bind `MockRestServiceServer` vào **chính builder đó**, sau đó build client:

~~~java
RestClient.Builder builder = RestClient.builder();
MockRestServiceServer mock =
        MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder
        .baseUrl("https://warehouse.example.test/api")
        .build();
~~~

Đây là snippet wiring, không phải toàn bộ test source. Phải bảo đảm code under test **sử dụng đúng `restClient` vừa build**; chỉ tạo một mock server khác bên ngoài không làm request từ production client bị chặn.

### 9.2. RestTemplate

`RestTemplate` là HTTP client đồng bộ đời trước. Có thể dùng:

~~~java
RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server =
        MockRestServiceServer.bindTo(restTemplate).build();
~~~

Với Spring Boot `@RestClientTest` và `RestTemplateBuilder`, hãy dùng builder do Spring inject rồi build `RestTemplate` để customizer tự gắn mock. Khi builder có `rootUri(String)`, Spring Boot docs hướng dẫn thường đặt **relative URI** trong expectation; không sao chép literal full URI của RestClient nếu rootUri customizer thay đổi matching.

`RestTemplate` chưa biến mất chỉ vì `RestClient` xuất hiện, nhưng code mới trên Spring 6.1+ có thể cân nhắc RestClient cho API đồng bộ. Lựa chọn nên theo version và project conventions.

### 9.3. WebClient (reactive) và MockWebServer/WireMock

`WebClient` của Spring WebFlux là reactive. **Không dùng `@RestClientTest` + `MockRestServiceServer` như thể nó tự bind được vào WebClient**. Đối với WebClient, có thể:
- Dùng một HTTP mock server (WireMock, OkHttp MockWebServer), điều chỉnh base URL của client sang localhost:randomPort và kiểm `RecordedRequest`/server verification.
- Unit test riêng một `ExchangeFunction` được stub nếu chỉ quan tâm mapping ở WebClient API layer, nhưng việc tự mock reactive exchange có thể bỏ sót HTTP encoding/transport.
- Dùng `StepVerifier` với publisher behavior khi có asynchronous/retry/backpressure, kết hợp mock server để kiểm request thật theo chính sách của client.

**WebTestClient không phải WebClient mock:** `WebTestClient` chủ yếu để **kiểm server-side endpoint** (có thể mock hoặc live HTTP); việc nhìn tên gần giống dễ khiến test chạy sai tầng.

## 10. Khi nào cần WireMock hoặc OkHttp MockWebServer?

Theo tài liệu Spring Framework, một mock web server có socket thật có các lợi ích:
- Nhận requests qua **TCP/HTTP** như server bình thường.
- Dùng đúng HTTP client/connection pool/codec production thay vì request factory đặc biệt của `MockRestServiceServer`.
- Mô phỏng response delays, dropped connections, malformed headers/body, redirects hoặc network failures tùy tool.
- Quan sát **recorded requests** để kiểm method, path, headers, query, body và call counts.
- Phù hợp WebClient, Feign, Apache HttpClient, OkHttp hoặc các client khác ngoài Spring RestClient/RestTemplate.

### 10.1. Phác thảo MockWebServer với recorded request

Với OkHttp MockWebServer, khái niệm kiểm request như sau:

~~~java
// Snippet minh họa; cần test dependency MockWebServer và imports.
// "httpClient" ở đây là RestClient được cấu hình trỏ tới
// mockWebServer.url("/api").toString() thay vì host production.

mockWebServer.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("""
                 {"sku":"SKU-1","warehouse":"HCM","available":12}
                 """));

StockSnapshot stock = httpClient.fetchStock(
        "SKU-1", "HCM", false, "req-10");

RecordedRequest request = mockWebServer.takeRequest(
        2, TimeUnit.SECONDS);

assertNotNull(request);
assertEquals("GET", request.getMethod());
assertEquals(
        "/api/stocks/SKU-1?warehouse=HCM&includeReserved=false",
        request.getPath());
assertEquals("req-10", request.getHeader("X-Request-Id"));
~~~

Đây là **snippet ý tưởng**, không thuộc Gradle project hoàn chỉnh ở mục 5–6; cần mock server được start/shutdown và client được inject base URL động. Không gửi URL của mock server vào production config. `takeRequest(timeout, unit)` có thể trả null nếu không có request trong hạn; assertNotNull giúp test fail rõ thay vì NullPointerException.

Khi dùng MockWebServer, chính **HTTP server ghi nhận yêu cầu đã đến**. Có thể assert count bằng số recorded requests, hoặc test không có request thêm trong một khoảng thời gian xác định; với async calls nên dùng synchronization thay vì sleep ngẫu nhiên. Luôn đóng mock server bằng try/finally hoặc JUnit lifecycle hook.

### 10.2. WireMock và xác minh số lần gọi

WireMock có thể stub và verify request pattern, ví dụ ý tưởng:

~~~java
wireMockServer.stubFor(
        get(urlPathEqualTo("/api/stocks/SKU-1"))
            .withQueryParam("warehouse", equalTo("HCM"))
            .willReturn(okJson(
                "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}")));

// Sau khi gọi client, kiểm đúng 2 requests tới endpoint.
wireMockServer.verify(
        2,
        getRequestedFor(urlPathEqualTo("/api/stocks/SKU-1"))
            .withQueryParam("warehouse", equalTo("HCM")));
~~~

Snippet này cần WireMock library, static imports và client base URL được trỏ đến `wireMockServer.baseUrl()`. Nó không thuộc ví dụ Gradle runnable chính; cú pháp WireMock có thể thay đổi giữa major versions. Khi dùng JUnit 5 WireMock extension, thiết lập randomPort/extension lifecycle rõ để test không tranh port khi chạy song song.

**Điểm cốt lõi:** Dù dùng MockRestServiceServer hay mock web server, không chỉ stub response; luôn **verify request contract và call count**. Một stub chỉ trả 200 có thể làm test pass ngay cả khi client gửi sai header/query nếu stub quá rộng.

## 11. Cách kiểm URI và query mà không phụ thuộc thứ tự

Trong một API coi query parameters là một tập không thứ tự, `requestTo(fullUri)` có thể quá chặt. Dùng custom `RequestMatcher` kết hợp với helper phân tích URI:

~~~java
server.expect(request -> {
    URI uri = request.getURI();

    assertEquals("https", uri.getScheme());
    assertEquals("warehouse.example.test", uri.getHost());
    assertEquals("/api/stocks/SKU-1", uri.getPath());

    MultiValueMap<String, String> params =
            UriComponentsBuilder.fromUri(uri)
                    .build()
                    .getQueryParams();

    assertEquals(2, params.size());
    assertEquals("HCM", params.getFirst("warehouse"));
    assertEquals("false", params.getFirst("includeReserved"));
}).andExpect(method(HttpMethod.GET))
  .andRespond(withSuccess(
      "{\"sku\":\"SKU-1\",\"warehouse\":\"HCM\",\"available\":12}",
      MediaType.APPLICATION_JSON));
~~~

Snippet cần imports `java.net.URI`, `org.springframework.util.MultiValueMap`, `org.springframework.web.util.UriComponentsBuilder`, JUnit assertions và Spring Test matchers. Đây là **custom matcher** cho request trong project có server biến `server`.

**Ưu điểm:** Không nhạy thứ tự `warehouse` và `includeReserved`. **Hạn chế:** Với URI đã được encode, builder có thể giữ giá trị percent-encoded trong query params; nếu test giá trị có dấu/khoảng trắng, cần decode đúng cách theo contract/driver. Ngoài ra, `getFirst()` chỉ kiểm giá trị đầu; nếu cần chặn duplicate `warehouse=HCM&warehouse=DN`, hãy assert cả `params.get("warehouse")` là danh sách một phần tử, thay vì chỉ `getFirst`.

Nếu muốn **không có query param nào khác**, kiểm `params.keySet()` đúng tập tên hoặc `params.size() == expectedCount`. Nếu muốn bảo vệ repeated params chính xác, so cả danh sách values. Không gộp mọi query vào một `contains("warehouse=HCM")` string assertion vì nó có thể match một query khác cũng chứa substring đó.

## 12. Những lỗi kiểm thử phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Test client gọi ra mạng thật | Client tạo bằng `RestClient.create()` không qua mock-configured builder | Inject `RestClient.Builder` do Boot cấp hoặc bind đúng builder |
| `@RestClientTest` không nạp client bean | Chưa chỉ định class, sai `@Component`, dependency ngoài slice | Dùng `@RestClientTest(WarehouseHttpClient.class)` và @Import tối thiểu nếu cần |
| `MockRestServiceServer` không autowire | Thiếu starter-test/slice config hoặc custom builder không được nhận diện | Kiểm dependencies, annotation và Boot 3.3 auto-configuration |
| Expected `/path` nhưng actual `https://host/api/path` | Nhầm quy tắc RestClient Builder và RestTemplate rootUri | Với RestClient dùng full URI trong expectation |
| URL assertion fail khi chỉ đổi thứ tự query | Expected URI quá chặt | Dùng queryParam/custom matcher theo contract |
| Query value có `&` làm sai param | Nối user input thẳng vào URL | UriBuilder.queryParam, encoding test |
| `queryParam` pass dù có extra query | Matcher chỉ kiểm subset values | Exact URI hoặc custom matcher kiểm toàn bộ params |
| Header match fail do `Accept`/`Content-Type` | Nhầm ý nghĩa hai header | GET/response Accept; POST body Content-Type |
| Body JSON nhìn giống nhưng strict matcher fail | Field dư/sai type/array order | So wire contract, chọn strict/lenient có chủ đích |
| JSON raw string matcher fail vì whitespace | So bằng `content().string` quá chặt | Dùng `content().json` khi contract là JSON structure |
| Test nhận response nhưng thiếu outbound call | Không gọi `server.verify()` hoặc code không trigger terminal operation | `.body(...)`/`.toBodilessEntity()` và verify |
| `times(2)` fail dù một request đã thành công | Lần còn lại chưa diễn ra | Gọi đủ hoặc sửa requirement, không bỏ verify |
| Request thêm ném AssertionError | Extra HTTP request không có expectation | Xem retry/interceptors/calls thừa |
| Test thứ tự fail | Expected order khác actual | Chỉ ràng buộc thứ tự nếu contract có yêu cầu |
| `server.verify()` fail khi test khác chạy trước | Expectations/counters không reset | `server.reset()` trước mỗi test, không dùng shared mutable client state |
| 404 xử lý sai | RestClient `retrieve()` mặc định ném 4xx exception | Assert đúng exception hoặc cấu hình `onStatus` cho policy |
| Test không phát hiện wrong JSON field | Expected body được generate bằng cùng code serializer sai | Ghi expected JSON contract độc lập |
| Async call chưa xong mà verify | Assertion chạy trước khi request phát ra | Đồng bộ Future/Publisher, `verify(Duration)` phù hợp |
| `MockRestServiceServer` không bắt network issue | Nó không mở real socket | MockWebServer/WireMock với client thật |
| WebClient test dùng MockRestServiceServer | Không phải client được tool này bind | MockWebServer/WireMock/ExchangeFunction phù hợp |
| Mockito times(2) pass nhưng method HTTP sai | Verify collaborator Java thay vì request | Kiểm tại HTTP client boundary |
| Auth token xuất hiện trong log | In raw Authorization/PII | Token giả trong fixture, redact logs |
| Test pass trên máy, fail CI do external API | Client bị cấu hình gọi live endpoint | Isolate base URL và mock transport hoàn toàn |

### 12.1. Quy trình chẩn đoán có thể áp dụng ngay

1. **Xác định client thực**: RestClient, RestTemplate, WebClient, Feign hay Apache/OkHttp.
2. **Xác định test layer**: mock RequestFactory hay mock web server thật; cần kiểm network behavior không?
3. **Kiểm client đã được bind đúng mock chưa**: constructor có nhận builder từ Spring context không?
4. **Đặt expected URL/method độc lập** với client code.
5. **Đặt expected headers và query** theo contract, chọn exact URI hay semantic query matcher.
6. **Với request body**, chọn `content().json(..., true)` nếu field/type/array structure cố định.
7. **Đặt expected count trước khi gọi client**; gọi `verify()` sau khi work đã hoàn tất.
8. **Test cả 0, 1 và nhiều lần** khi nghiệp vụ có branch/retry/batch.
9. **Kiểm error response 4xx/5xx**, deserialization và non-retry hoặc retry policy.
10. **Chạy tests độc lập**; reset expectations và không phụ thuộc thứ tự JUnit methods.
11. **Nếu cần HTTP transport thật**, chuyển mock web server trên random port, không gọi live external API.
12. **Kiểm logs không lộ secrets** hoặc request/response chứa PII.

## 13. Bảo vệ test khỏi sự phụ thuộc quá mức vào implementation

Không phải mọi request metadata đều là một phần contract. Với một API chỉ cần `Accept: application/json`, không nên test thứ tự headers; với query không nhạy thứ tự, không nên bắt full URI string nếu client library có thể serialize lại thứ tự một cách hợp lệ. Ngược lại, một API ký HMAC trên **raw path/query/body** thì raw byte order/canonical encoding là contract và cần test **chính xác**.

Để test không quá yếu cũng không quá brittle:
- Kiểm scheme/host/path cụ thể nếu environment/route là contract.
- Kiểm HTTP method luôn, vì nó có ý nghĩa nghiệp vụ và idempotency.
- Kiểm required headers; không test incidental user-agent hoặc connection header trừ khi contract bắt buộc.
- Với query, kiểm đủ keys/values, repeated values và encoding cho input đặc biệt.
- Với body JSON, chọn strict mode nếu không được phép field dư hoặc type sai.
- Với retries, kiểm đúng số attempt theo policy của ứng dụng.
- Với request ordering, chỉ assert order nếu có dependency giữa các calls.
- Với asynchronous execution, đồng bộ completion thay vì sleep một khoảng ngẫu nhiên.
- Với tokens/secrets, dùng dummy credential và tránh snapshot raw Authorization header trong CI log.
- Với response, luôn assert mapping và error handling tương ứng, không chỉ kiểm "HTTP đã gọi".

**Đừng nhầm `MockRestServiceServer` là performance test.** Nó không đo thực tế TLS handshake, DNS resolution, connection pooling, proxy, keep-alive, socket timeout hoặc network latency. Để kiểm các điểm đó, dùng mock web server với client transport thật và metric phù hợp, hoặc integration test riêng khi cần.

## 14. Bài tập vận dụng

**Bài 1 — Sai method:** Đổi `fetchStock` từ `.get()` thành `.post()`, giữ nguyên endpoint. Test nào fail và vì sao URL đúng chưa đủ?

**Bài 2 — Header:** Thêm `X-Tenant-Id` bắt buộc, dùng fixture "tenant-a". Viết matcher kiểm header và một negative test bỏ header, không hard-code credentials production.

**Bài 3 — Query:** Thêm filter `locale=vi-VN` và repeated `tag=java&tag=spring`. Chọn exact URI, queryParamList hoặc custom matcher để kiểm đầy đủ mà không nhạy thứ tự giữa các key.

**Bài 4 — Encoding:** Gửi warehouse chứa khoảng trắng và dấu tiếng Việt. Kiểm decoded query semantics hoặc raw percent-encoding theo contract của endpoint; giải thích vì sao nối string trực tiếp không an toàn.

**Bài 5 — Body:** Thêm `customerNote` optional trong POST. Khi nào dùng strict JSON, khi nào lenient? Test JSON number 3 khác JSON string "3".

**Bài 6 — Zero calls:** Khi quantity=0, bảo đảm không có request; khi quantity=1, expect đúng một POST. Không dùng Mockito mock của cả client để thay kiểm wire contract.

**Bài 7 — Exactly two:** Giả lập một retry policy chỉ retry HTTP 503 một lần rồi thành công. Định nghĩa hai responses 503→200 và verify đúng hai requests, không dùng Thread.sleep trong test.

**Bài 8 — Unexpected request:** Cố tình gọi client lần thứ ba khi only two expected. Quan sát request factory báo unexpected extra call.

**Bài 9 — Ordered calls:** Nghiệp vụ đặt chỗ phải GET stock trước POST reserve. Thử đảo thứ tự và quan sát expectation order fail. Nếu hai calls thực sự độc lập, đề xuất thiết kế test không ràng buộc order.

**Bài 10 — 404:** Thay vì throw, sửa client để trả Optional.empty cho stock không có (qua onStatus/custom exception handling). Test status, response policy và đúng một outbound call.

**Bài 11 — WebClient:** Chuyển WarehouseHttpClient sang WebClient reactive. Vì sao MockRestServiceServer không còn là lựa chọn trực tiếp, và làm thế nào dùng MockWebServer/WireMock với random port?

**Bài 12 — Transport:** Dùng OkHttp MockWebServer để quan sát `RecordedRequest` path, headers, body và network timeout. So sánh phát hiện lỗi với `@RestClientTest` in-process.

**Bài 13 — Multiple clients:** Một service dùng hai RestClient builders trỏ tới hai upstream APIs. Thiết kế mock server binding và expectations riêng cho từng client; tránh lấy một `MockRestServiceServer` rồi nghĩ nó chặn tất cả.

**Bài 14 — Security:** Client cần OAuth bearer token. Mock token provider hoặc dùng dummy token; test header tồn tại và không xuất hiện trong logs. Phân biệt test HTTP header với test flow lấy token thật từ identity provider.

**Bài 15 — Contract review:** Chọn một API bên ngoài trong dự án thật, tạo bảng gồm URL/method/headers/query/body/count/response cho ít nhất ba kịch bản, rồi quyết định tầng test nhanh và tầng integration network cần thiết.

## 15. Tài liệu đối chiếu

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@RestClientTest`, RestClient.Builder, RestTemplateBuilder và full-vs-relative URI expectations.
- [Spring Framework 6.1 — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer` và so sánh với mock web server có HTTP network.
- [Spring Framework 6.1 — MockRestServiceServer API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): `expect`, `verify`, `reset`, `bindTo(RestClient.Builder)`.
- [Spring Framework 6.1 — MockRestRequestMatchers API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/match/MockRestRequestMatchers.html): `requestTo`, `method`, `header`, `queryParam`, `content`.
- [Spring Framework 6.1 — ContentRequestMatchers API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/match/ContentRequestMatchers.html): `json(expected, strict)`, `contentTypeCompatibleWith`, `string`.
- [Spring Framework 6.1 — ExpectedCount API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/ExpectedCount.html): `once`, `times`, `never`, `between`.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient builder, `retrieve`, `body`, `toBodilessEntity`, error handling.
- [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): hỗ trợ mock RestClient của Spring Test.
- [WireMock Documentation](https://wiremock.org/docs/): request matching, stubbing, verification và HTTP server mock.
- [OkHttp MockWebServer](https://square.github.io/okhttp/): recorded requests, scripted responses và test network client.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/): assertions, test lifecycle và `assertThrows`.

**Ghi nhớ:** Để kiểm một HTTP client, cần xác minh **request thực sự được client tạo ra**: URL, method, headers, query, body và số lần gọi. Với **Spring Boot 3.3 + RestClient/RestTemplate**, `@RestClientTest` và `MockRestServiceServer` cho phép làm việc này nhanh, không mở HTTP socket. Dùng **`requestTo` + `method` + `header` + `queryParam` + `content().json` + `ExpectedCount` + `server.verify()`**, thêm kiểm zero calls và 4xx/5xx. Khi cần transport/network behavior thật hoặc dùng WebClient, chuyển sang **WireMock/MockWebServer** và trỏ client đến random local port. Luôn thiết kế assertions theo external API contract, không sao chép implementation lỗi vào expected values.
