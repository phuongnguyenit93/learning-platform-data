# Kiểm tra status, header, cookie và nội dung JSON bằng WebTestClient trong Spring WebFlux

Trong ứng dụng Spring WebFlux, một endpoint trả về đúng dữ liệu chưa đủ để được xem là đúng hợp đồng API. Response còn phải mang HTTP status phù hợp, Content-Type chính xác, các header có ý nghĩa như Location hoặc ETag, cookie với thuộc tính bảo mật cần thiết, và cấu trúc JSON mà client thực sự mong đợi. Ví dụ, POST tạo tài nguyên trả HTTP 200 thay vì 201, cookie thiếu HttpOnly, hoặc JSON thiếu một field bắt buộc đều là lỗi hợp đồng dù controller không ném exception.

**WebTestClient** là API kiểm thử HTTP của Spring dành cho cả ứng dụng reactive và những ứng dụng có thể kiểm thử qua server. Nó xây request tương tự WebClient, nhưng sau exchange() cung cấp DSL chuyên cho assertion: expectStatus(), expectHeader(), expectCookie(), expectBody(), jsonPath() và các cách decode body.

Bài học thuộc nhóm **Kiểm thử WebFlux** của module Spring Framework - reactive. Trọng tâm là phân biệt các loại assertion, chọn mức kiểm thử thích hợp, kiểm tra đúng những điều quan trọng và xây một bộ ví dụ Java 17+ / Spring Boot 3.3.5 có thể chạy bằng Maven.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt HTTP status, response header, Set-Cookie và JSON body.
- Tạo request GET/POST/PUT/DELETE bằng WebTestClient và gọi exchange().
- Kiểm tra chính xác status 200, 201, 204, 400, 404, 405 và 415.
- Kiểm tra Content-Type, Location, ETag, Cache-Control và custom header.
- Dùng HeaderAssertions.exists(), doesNotExist(), valueEquals(), valueMatches().
- Phân biệt response cookie với cookie gửi trong request.
- Dùng CookieAssertions kiểm tra name, value, path, Max-Age, HttpOnly, Secure và SameSite.
- So sánh JSON bằng json() ở chế độ lenient hoặc strict.
- Dùng JSONPath để kiểm tra field, array, kiểu dữ liệu và giá trị lồng nhau.
- Decode body bằng expectBody(Class) và expectBodyList(Class).
- Phân biệt empty body, missing field, null value và status lỗi.
- Chọn @WebFluxTest cho controller slice hoặc @SpringBootTest để kiểm tra HTTP tích hợp.
- Sử dụng expectAll và consumeWith khi assertion tích hợp sẵn chưa đủ.
- Tránh flakiness do thứ tự JSON object, thời gian hiện tại, ID ngẫu nhiên và cookie bảo mật.
- Viết project mẫu và kiểm thử request/response có thể chạy được trên Java 17+.

## 2. HTTP response có những phần nào cần kiểm tra?

Một HTTP response thường có:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/products/p-new
X-Request-Id: req-123
Set-Cookie: demo_pref=enabled; Path=/api; Max-Age=900; Secure; HttpOnly; SameSite=Lax

{"id":"p-new","name":"Notebook","price":700,"available":true,"tags":["new"]}
~~~

Các lớp kiểm thử tương ứng:

| Thành phần | Câu hỏi | API WebTestClient |
| --- | --- | --- |
| Status line | API tạo mới thành công hay thất bại? | expectStatus() |
| Content-Type | Response có phải JSON không? | expectHeader().contentTypeCompatibleWith(...) |
| Location | URL tài nguyên mới nằm ở đâu? | expectHeader().location(...) |
| Custom header | Correlation ID có được trả không? | expectHeader().valueEquals(...) |
| Set-Cookie | Cookie có đúng thuộc tính an toàn? | expectCookie() |
| JSON object | ID, tên, giá, cờ boolean có đúng? | expectBody().jsonPath(...) |
| JSON toàn bộ | Contract body có đúng tập field và kiểu? | expectBody().json(..., true) |
| DTO đã decode | Có thể deserialize thành Java record? | expectBody(Product.class) |
| Không có body | HTTP 204 có thực sự rỗng không? | expectBody().isEmpty() |

Đừng chỉ kiểm tra HTTP 200 rồi cho rằng toàn bộ response hợp lệ. Một regression có thể thay đổi header hoặc body mà status vẫn không đổi.

## 3. Luồng API của WebTestClient

Luồng viết test thường là:

~~~text
WebTestClient
    |
    +-- get() / post() / put() / delete()
    |       |
    |       +-- uri(...)
    |       +-- accept(...) / contentType(...)
    |       +-- headers(...) / cookie(...) / bodyValue(...)
    |
    +-- exchange()
            |
            +-- expectStatus()
            +-- expectHeader()
            +-- expectCookie()
            +-- expectBody()
                    |
                    +-- json(...)
                    +-- jsonPath(...)
                    +-- isEmpty()
            +-- expectBody(Product.class)
            +-- expectBodyList(Product.class)
~~~

Ví dụ:

~~~java
client.get()
    .uri("/api/products/p1")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader()
        .valueEquals("X-Catalog-Version", "v1")
    .expectBody()
        .jsonPath("$.id").isEqualTo("p1")
        .jsonPath("$.name").isEqualTo("Keyboard");
~~~

Trước exchange(), API giống cách tạo request của WebClient. Sau exchange(), WebTestClient không còn cung cấp một Mono<ResponseEntity<...>> để bạn tự subscribe, mà cung cấp ResponseSpec để khai báo assertion. WebTestClient tự thực hiện exchange và kiểm tra các tín hiệu liên quan.

### Assertion nằm ở tầng nào?

- expectStatus() kiểm tra status code của HTTP response.
- expectHeader() kiểm tra HTTP headers, không đọc JSON body.
- expectCookie() đọc response cookies, bao gồm các thuộc tính từ Set-Cookie.
- expectBody() đọc body, có thể so sánh JSON hoặc decode thành DTO.
- returnResult(...) cho phép tiếp tục xử lý response, đặc biệt với stream.

## 4. Ba cách bind WebTestClient

Có ba nhóm tình huống thường gặp.

### Bind trực tiếp vào controller

~~~java
WebTestClient client = WebTestClient
    .bindToController(new CatalogController(new CatalogService()))
    .build();
~~~

Không cần mở cổng TCP thật. Phù hợp khi muốn kiểm tra handler, mapping, codec và WebFlux infrastructure tối thiểu với phạm vi được tạo cho test. Không đồng nghĩa với kiểm tra toàn bộ auto-configuration, filter chain hoặc reverse proxy của production.

### Bind vào ApplicationContext

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .build();
~~~

Test dùng WebApplicationContext hiện có và các bean đã được cấu hình. Spring Boot thường cung cấp WebTestClient tự động khi dùng @WebFluxTest.

### Bind vào server đang chạy

~~~java
WebTestClient client = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080")
    .build();
~~~

Có thể kiểm tra HTTP trao đổi qua socket thật. Khi chạy @SpringBootTest(webEnvironment = RANDOM_PORT) cùng @AutoConfigureWebTestClient, Spring Boot có thể inject WebTestClient đã hướng tới embedded test server.

Ba cách trên có mức độ cô lập khác nhau. Với yêu cầu kiểm tra contract status/header/cookie/JSON của controller, @WebFluxTest thường nhanh và đủ sâu. Với HTTP security filters, codec configuration, network behavior hoặc server integration, cần thêm @SpringBootTest hoặc end-to-end test.

## 5. Kiểm tra HTTP status

WebTestClient hỗ trợ các shortcut rõ nghĩa:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk();
~~~

~~~java
client.post().uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateProduct("Notebook", 700))
    .exchange()
    .expectStatus().isCreated();
~~~

~~~java
client.get().uri("/api/products/missing")
    .exchange()
    .expectStatus().isNotFound();
~~~

~~~java
client.get().uri("/api/diagnostics/empty")
    .exchange()
    .expectStatus().isNoContent();
~~~

~~~java
client.post().uri("/api/products")
    .contentType(MediaType.TEXT_PLAIN)
    .bodyValue("not-json")
    .exchange()
    .expectStatus().isEqualTo(415);
~~~

Các HTTP status thường có ý nghĩa:

| Status | Ngữ cảnh | Kỳ vọng test |
| --- | --- | --- |
| 200 OK | GET thành công | isOk() |
| 201 Created | POST tạo tài nguyên | isCreated() |
| 204 No Content | Thành công, không body | isNoContent() kết hợp isEmpty() |
| 400 Bad Request | Input không hợp lệ | isBadRequest() |
| 401 Unauthorized | Chưa có authentication hợp lệ | isUnauthorized() |
| 403 Forbidden | Đã xác thực nhưng không có quyền | isForbidden() |
| 404 Not Found | Không tìm thấy resource | isNotFound() |
| 405 Method Not Allowed | Method không có mapping | isEqualTo(405) |
| 415 Unsupported Media Type | Content-Type request không được hỗ trợ | isEqualTo(415) |
| 500 Internal Server Error | Lỗi chưa xử lý của server | is5xxServerError() |

Không chỉ dùng is2xxSuccessful() khi hợp đồng yêu cầu chính xác 201 hoặc 204. is2xxSuccessful() cho phép mọi status trong nhóm 2xx nên có thể bỏ sót một regression.

### Kiểm tra chuỗi lỗi đúng tầng

Nếu POST body sai nhưng server trả 500, đừng sửa test cho khớp 500. Xác định liệu lỗi input nên được ánh xạ thành 400, 422 hay một status khác theo API contract, rồi sửa server hoặc test tương ứng.

## 6. HeaderAssertions: các cách kiểm tra header

Lấy ví dụ GET /api/products/p1 trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "catalog-p1-v1"
Cache-Control: no-store
X-Catalog-Version: v1
~~~

Các assertion quan trọng:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader()
        .valueEquals(HttpHeaders.ETAG, "\"catalog-p1-v1\"")
    .expectHeader()
        .cacheControl(CacheControl.noStore())
    .expectHeader()
        .valueEquals("X-Catalog-Version", "v1");
~~~

### contentType và contentTypeCompatibleWith

- contentType(MediaType.APPLICATION_JSON): kiểm tra giá trị Content-Type theo kỳ vọng tương ứng; thích hợp khi định dạng phải chính xác.
- contentTypeCompatibleWith(MediaType.APPLICATION_JSON): kiểm tra loại media tương thích; hữu ích khi server thêm tham số charset hoặc có kiểu JSON media type tương thích.

Không nên lạm dụng compatibleWith nếu hợp đồng yêu cầu một media type cụ thể. Ngược lại, không nên bắt byte-for-byte header có tham số không quan trọng khi client chỉ cần biết nội dung là JSON.

### exists và doesNotExist

~~~java
.expectHeader().exists("X-Catalog-Version")
.expectHeader().doesNotExist("X-Legacy-Flag");
~~~

exists chỉ kiểm tra có header; nó không chứng minh header có giá trị hợp lệ. Với correlation ID hoặc token format, kiểm tra regex hoặc consumer.

### valueEquals và valueMatches

~~~java
.expectHeader().valueEquals("X-Catalog-Version", "v1")
.expectHeader().valueMatches("X-Request-Id", "req-[0-9]{3}");
~~~

valueMatches dùng regular expression. Nó hữu ích cho ID động có định dạng cố định. Tránh regex quá rộng như .* vì nó hầu như không kiểm tra giá trị.

### Location, ETag và Cache-Control

~~~java
.expectHeader().location("/api/products/p-new")
~~~

Location phù hợp với status 201 khi API tạo resource. ETag giúp cache/concurrency control. Cache-Control thể hiện cache policy. Để test đáng tin, hãy xác định những header nào thuộc public contract, thay vì assert toàn bộ headers do server/proxy thêm.

## 7. Cookie: phân biệt request và response

Cookie đi theo hai hướng:

~~~http
GET /api/profile HTTP/1.1
Cookie: language=vi
~~~

Đây là **request cookie** client gửi lên server.

~~~http
HTTP/1.1 200 OK
Set-Cookie: demo_pref=enabled; Path=/api; Max-Age=900; Secure; HttpOnly; SameSite=Lax
~~~

Đây là **response cookie** server muốn trình duyệt lưu.

Trong WebTestClient:

- cookie("language", "vi") đặt Cookie trong request.
- expectCookie() kiểm tra cookie trong response.
- expectHeader().valueMatches(HttpHeaders.SET_COOKIE, ...) kiểm tra raw Set-Cookie header nếu cần.
- CookieAssertions giúp kiểm tra thuộc tính đã parse thay vì so khớp raw string có thứ tự thuộc tính thay đổi.

Ví dụ gửi request cookie:

~~~java
client.get()
    .uri("/api/profile")
    .cookie("language", "vi")
    .exchange();
~~~

Đoạn code trên không tự khẳng định rằng server đã trả response cookie. Muốn kiểm tra Set-Cookie phải có expectCookie().

## 8. CookieAssertions: giá trị và thuộc tính bảo mật

Với response cookie:

~~~http
Set-Cookie: demo_pref=enabled; Path=/api; Max-Age=900; Secure; HttpOnly; SameSite=Lax
~~~

WebTestClient hỗ trợ:

~~~java
client.get().uri("/api/diagnostics/cookie")
    .exchange()
    .expectStatus().isOk()
    .expectCookie().exists("demo_pref")
    .expectCookie().valueEquals("demo_pref", "enabled")
    .expectCookie().path("demo_pref", "/api")
    .expectCookie().maxAge(
        "demo_pref", Duration.ofMinutes(15))
    .expectCookie().secure("demo_pref", true)
    .expectCookie().httpOnly("demo_pref", true)
    .expectCookie().sameSite("demo_pref", "Lax");
~~~

Ý nghĩa:

| Cookie assertion | Kiểm tra |
| --- | --- |
| exists(name) | Cookie có trong response |
| doesNotExist(name) | Cookie không có trong response |
| valueEquals(name, value) | Giá trị cookie |
| path(name, path) | Thuộc tính Path |
| maxAge(name, Duration) | Thuộc tính Max-Age |
| secure(name, boolean) | Có/không có Secure |
| httpOnly(name, boolean) | Có/không có HttpOnly |
| sameSite(name, value) | Thuộc tính SameSite |
| domain(name, expected) | Thuộc tính Domain |

### Bảo mật và giới hạn của test

Cookie HttpOnly giúp JavaScript không đọc cookie đó qua document.cookie; Secure yêu cầu browser chỉ gửi qua kết nối phù hợp với chính sách HTTPS; SameSite giúp điều tiết gửi cookie trong tình huống cross-site. Các flag **không thay thế authentication, authorization, CSRF protection hoặc session management đúng cách**.

WebTestClient có thể xác minh server phát các thuộc tính cookie, nhưng bản thân nó không chứng minh mọi browser sẽ lưu hoặc gửi cookie. Nếu response có Secure qua một test HTTP mock, assertion vẫn có thể thành công; browser production cần được kiểm thử qua HTTPS và theo cookie policy thật.

Đừng viết test của security cookie chỉ kiểm tra exists(). Một regression xóa HttpOnly vẫn có thể qua kiểm tra này. Khi thuộc tính là hợp đồng bảo mật, kiểm tra trực tiếp từng thuộc tính.

### Raw Set-Cookie

Có thể kiểm tra header raw:

~~~java
.expectHeader().valueMatches(
    HttpHeaders.SET_COOKIE,
    "demo_pref=enabled;.*");
~~~

Tuy nhiên, assert một chuỗi Set-Cookie đầy đủ theo đúng thứ tự Path, Max-Age, Expires, Secure, HttpOnly và SameSite dễ giòn vì thứ tự attribute hoặc định dạng Expires có thể khác. Ưu tiên CookieAssertions cho semantic checks.

## 9. JSON body: ba chiến lược assertion

Giả sử API trả:

~~~json
{
  "id": "p1",
  "name": "Keyboard",
  "price": 1200,
  "available": true,
  "tags": ["input", "office"]
}
~~~

Ba chiến lược chính:

1. **So sánh cấu trúc JSON** khi muốn đối chiếu object hoặc toàn bộ response.
2. **JSONPath** khi chỉ muốn kiểm tra vài field/nested values quan trọng.
3. **Decode sang DTO** khi client khác cũng dùng cùng Java model và cần kiểm tra object.

Không phải mọi test đều phải kiểm tra cả ba. Chọn cách rõ nhất cho hành vi được bảo vệ.

### Kiểm tra một phần JSON

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json("{\"id\":\"p1\",\"name\":\"Keyboard\"}");
~~~

Trong Spring Framework 6.1, json(String) sử dụng JSON comparison kiểu lenient, cho phép object thực tế có thêm field và array không bắt buộc giữ đúng thứ tự trong nhiều trường hợp. Nó không phải so khớp chuỗi byte JSON.

### Strict JSON comparison

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json(
        "{\"id\":\"p1\",\"name\":\"Keyboard\","
        + "\"price\":1200,\"available\":true,"
        + "\"tags\":[\"input\",\"office\"]}",
        true);
~~~

Trong Spring Framework 6.1, json(expected, true) kiểm tra JSON **strict**: không cho field thừa và yêu cầu array ordering đúng theo kỳ vọng. Thứ tự các key của JSON object không mang ý nghĩa; JSONAssert so sánh cấu trúc chứ không yêu cầu thứ tự byte.

Từ Spring 6.2 có overload dùng JsonCompareMode, nên khi học code của các version khác nhau phải xem đúng Javadoc của Spring Framework đang dùng.

### Khi nào strict có thể quá chặt?

Nếu API cho phép thêm field tương thích ngược, strict JSON sẽ fail khi thêm một field mới dù client vẫn hoạt động. Dùng JSONPath hoặc lenient khi chỉ bảo vệ vài field cốt lõi. Dùng strict khi schema là hợp đồng đóng, ví dụ một response phục vụ ký số hoặc một contract cần ngăn field bất ngờ.

## 10. JSONPath: kiểm tra field và array chính xác

JSONPath truy xuất các vị trí trong JSON response:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo("p1")
    .jsonPath("$.price").isEqualTo(1200)
    .jsonPath("$.available").isEqualTo(true)
    .jsonPath("$.tags[0]").isEqualTo("input");
~~~

Một số selector thông dụng:

| JSONPath | Ý nghĩa |
| --- | --- |
| $ | Toàn bộ root |
| $.id | Field id của object root |
| $.customer.name | Field lồng nhau |
| $.tags[0] | Phần tử đầu trong array tags |
| $[0].id | Field id của phần tử đầu nếu root là array |
| $.items[*].id | Danh sách ID của mọi item |
| $.metadata.traceId | Field traceId trong object metadata |

Nếu response là array:

~~~json
[
  {"id":"p1","name":"Keyboard"},
  {"id":"p2","name":"Mouse"}
]
~~~

Test:

~~~java
client.get().uri("/api/products")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$").isArray()
    .jsonPath("$[0].id").isEqualTo("p1")
    .jsonPath("$[1].name").isEqualTo("Mouse");
~~~

Các assertion chuyên biệt như exists(), doesNotExist(), isArray(), isMap(), isNumber(), isBoolean(), isNotEmpty() giúp thể hiện loại dữ liệu. Chọn kiểu phù hợp với dữ liệu thực tế.

### Null và missing field không giống nhau

~~~json
{"nickname": null}
~~~

khác với:

~~~json
{}
~~~

Nếu API có quy định field bắt buộc dù value null, hãy kiểm tra schema/JSONPath theo cách phân biệt rõ. Một số helper tồn tại-check có semantics coi null là không có giá trị; nên tham khảo Javadoc chính xác và dùng structural JSON comparison hoặc decode body khi distinction này là cốt lõi.

### JSON number và Java number

JSON chỉ có kiểu number; khi JSONPath decode qua thư viện Java, một số number có thể thành Integer, Long hoặc BigDecimal tùy dạng dữ liệu. Nếu assertion fail do kiểu số, hãy kiểm tra giá trị và kiểu decode thay vì chuyển toàn bộ expectation thành String.

## 11. Decode JSON body thành Java record hoặc DTO

Nếu API trả Product và bạn muốn so sánh model ở mức Java:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody(Product.class)
    .consumeWith(result -> {
        Product product = result.getResponseBody();

        assertNotNull(product);
        assertEquals("p1", product.id());
        assertEquals(1200, product.price());
    });
~~~

Đây là test hai bước: WebTestClient decode JSON thành Product qua configured codecs; sau đó assertion kiểm tra object.

Với response là array:

~~~java
client.get().uri("/api/products")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(Product.class)
    .hasSize(2)
    .contains(
        new Product(
            "p1", "Keyboard", 1200, true,
            List.of("input", "office")));
~~~

Java record tự có equals/hashCode dựa trên field, nên contains() so sánh nội dung record. Nếu DTO là class thông thường không override equals(), contains() có thể không so sánh như bạn tưởng. Khi đó dùng consumeWith và AssertJ/JUnit để kiểm tra các field.

### Generic response

Đối với response như ApiPage<Product>, có thể dùng expectBody(new ParameterizedTypeReference<ApiPage<Product>>() {}) để giữ generic type. Không dùng raw ApiPage.class khi decoder cần biết kiểu phần tử của collection.

### Không overfit DTO của chính server

Trong contract test hướng tới consumer độc lập, decode bằng đúng DTO nội bộ của server có thể bỏ sót incompatibility với consumer khác phiên bản. Hãy kết hợp structural JSON assertions ở boundary với các integration/consumer-contract tests khi cần tương thích giữa microservices.

## 12. Empty body và status không có nội dung

HTTP 204 No Content không có response body. Assertion phù hợp:

~~~java
client.get().uri("/api/diagnostics/empty")
    .exchange()
    .expectStatus().isNoContent()
    .expectHeader().doesNotExist(HttpHeaders.CONTENT_TYPE)
    .expectBody().isEmpty();
~~~

Đừng kiểm tra JSONPath khi endpoint có contract body rỗng. Một HTTP status 204 kèm JSON body là mâu thuẫn hợp đồng.

Với status lỗi không có body:

~~~java
client.get().uri("/api/products/missing")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody().isEmpty();
~~~

Nếu API theo RFC 9457 trả ProblemDetail JSON khi 404, kỳ vọng trên phải được thay bằng content type và JSON schema của ProblemDetail. Không có một “đúng chung” cho body của mọi 404; cần dựa vào contract của chính endpoint.

### HTTP HEAD

HEAD cũng không trả response body, nhưng header và status phải phản ánh GET tương ứng theo giao thức. Nếu API hỗ trợ HEAD, hãy kiểm tra status/headers độc lập, không mặc định rằng GET và HEAD luôn cùng body assertion.

## 13. Kiểm tra request input để hiểu response

Các assertion response sẽ có ý nghĩa hơn khi request được tạo đúng.

### GET với Accept

~~~java
client.get()
    .uri("/api/products/p1")
    .accept(MediaType.APPLICATION_JSON)
    .exchange();
~~~

Accept nói rằng client chấp nhận JSON response; nó khác Content-Type mô tả request body gửi lên.

### POST JSON

~~~java
client.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateProduct("Notebook", 700))
    .exchange();
~~~

WebTestClient sử dụng codec để serialize CreateProduct thành JSON. Nếu quên Content-Type và endpoint khai báo consumes application/json, test có thể nhận 415 tùy request/codec configuration.

### Custom request header

~~~java
client.get()
    .uri("/api/products/p1")
    .header("X-Correlation-Id", "test-001")
    .exchange();
~~~

Header gửi **trong request** không mặc nhiên trở thành response header. Nếu server không có logic phản chiếu hoặc tạo response header tương ứng, expectHeader() không thể tự thấy nó.

### Request cookie

~~~java
client.get()
    .uri("/api/diagnostics/cookie")
    .cookie("locale", "vi")
    .exchange();
~~~

Request cookie không chứng minh response cookie tồn tại; cần expectCookie sau exchange. Điều này giúp phân biệt hai hướng lưu chuyển dữ liệu.

## 14. @WebFluxTest và @SpringBootTest: chọn mức kiểm thử

Với Spring Boot WebFlux, hai kiểu kiểm thử phổ biến:

| Kiểu | Phạm vi | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| @WebFluxTest(CatalogController.class) | WebFlux MVC-like controller slice, codecs, mapping, advice | Nhanh, cô lập, lỗi dễ truy vết | Không load toàn bộ service/repository/filter ngoài slice |
| @SpringBootTest + @AutoConfigureWebTestClient | ApplicationContext lớn hơn; có thể chạy embedded server | Kiểm tra auto-configuration, beans và HTTP integration | Chậm hơn, cần kiểm soát dependencies |
| WebTestClient.bindToController | Controller được tạo trực tiếp | Rất nhanh, không cần Boot context | Có thể thiếu infrastructure và filter production |
| WebTestClient.bindToServer | HTTP tới server hiện hữu | Kiểm tra qua network thật | Phụ thuộc môi trường/port/server |

### Slice test và dependencies

Nếu CatalogController inject CatalogService, một @WebFluxTest không tự mang mọi @Service vào context. Có thể dùng @MockBean để stub service theo mục tiêu test hoặc @Import(CatalogService.class) nếu service đơn giản, không có side effect. Trong project bên dưới, service bất biến và xác định nên dùng @Import để kiểm tra data/serialization thật.

### Integration test

Với RANDOM_PORT, embedded server mở cổng ngẫu nhiên; @AutoConfigureWebTestClient tạo client phù hợp để test. Không hardcode port 8080 trong integration test. Các test thực sự cần database/external service phải dùng test fixture và môi trường cô lập, không gọi production endpoint.

### Kiểm tra Security

Nếu có Spring Security, @WebFluxTest có thể load các security filters tùy cấu hình và tạo 401/403 trước controller. Hãy xác định rõ đang kiểm thử contract anonymous hay authenticated, dùng spring-security-test và WebTestClientMutator phù hợp. Không tắt toàn bộ security trong test nếu mục tiêu là kiểm tra authorization và cookie session.

## 15. Dự án thực hành Java 17+ Spring Boot WebFlux

Ứng dụng demo trả dữ liệu catalog cố định để các test có kết quả xác định, không cần database. Nó có:

- GET /api/products: trả array gồm hai sản phẩm.
- GET /api/products/{id}: trả 200 + Content-Type, ETag, Cache-Control và X-Catalog-Version; trả 404 nếu không có ID.
- POST /api/products: kiểm tra input, trả 201 + Location + X-Request-Id + JSON Product; trả 400 + JSON error nếu name trống hoặc price âm.
- GET /api/diagnostics/cookie: trả response cookie demo_pref có Secure, HttpOnly, SameSite, Path, Max-Age.
- GET /api/diagnostics/empty: trả 204 và không có body.

Lưu ý: POST trong demo chỉ **mô phỏng phản hồi tạo tài nguyên**, không lưu vào database. ID p-new cố định để test dễ đọc; ứng dụng production cần lưu thật, sinh ID phù hợp và xử lý idempotency/concurrency. Cookie demo_pref chỉ biểu diễn preference, **không phải access token hoặc session authentication**.

### Cấu trúc project

~~~text
webflux-response-contract-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── CatalogApiModels.java
    │   ├── CatalogService.java
    │   └── CatalogController.java
    └── test/java/com/example/catalog/
        ├── CatalogControllerTest.java
        └── CatalogHttpIntegrationTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-response-contract-demo</artifactId>
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
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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
~~~

spring-boot-starter-test cung cấp JUnit Jupiter, AssertJ, JsonPath và JSONAssert cần cho những assertion trong bài. Reactor Test được khai báo riêng cho những test streaming sử dụng StepVerifier về sau. Không cần thêm Spring MVC starter; nếu thêm đồng thời spring-boot-starter-web không có chủ đích, Spring Boot có thể chọn servlet stack thay vì WebFlux.

### CatalogApplication.java

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### CatalogApiModels.java

~~~java
package com.example.catalog;

import java.util.List;

public final class CatalogApiModels {

    private CatalogApiModels() {
    }

    public record Product(
            String id,
            String name,
            int price,
            boolean available,
            List<String> tags) {
    }

    public record CreateProduct(
            String name,
            int price) {
    }

    public record ApiError(
            String code,
            String message) {
    }

    public record CookieInfo(
            boolean enabled) {
    }
}
~~~

Các nested records là public static theo ngôn ngữ Java và Jackson có thể sử dụng chúng làm DTO. Product.price là int để ví dụ đơn giản; trong ứng dụng tài chính, dùng BigDecimal và đơn vị tiền tệ rõ ràng để tránh sai số/ngữ nghĩa.

### CatalogService.java

~~~java
package com.example.catalog;

import java.util.List;

import org.springframework.stereotype.Service;

import com.example.catalog.CatalogApiModels.Product;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogService {

    private static final List<Product> PRODUCTS = List.of(
        new Product(
            "p1", "Keyboard", 1200, true,
            List.of("input", "office")),
        new Product(
            "p2", "Mouse", 450, false,
            List.of("input"))
    );

    public Flux<Product> all() {
        return Flux.fromIterable(PRODUCTS);
    }

    public Mono<Product> findById(String id) {
        return all()
            .filter(product -> product.id().equals(id))
            .next();
    }
}
~~~

Dữ liệu bất biến giúp các test không phụ thuộc lẫn nhau. Ở production, có thể thay CatalogService bằng repository reactive; cần kiểm soát dữ liệu test và không dựa vào database dùng chung.

### CatalogController.java

~~~java
package com.example.catalog;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.catalog.CatalogApiModels.ApiError;
import com.example.catalog.CatalogApiModels.CookieInfo;
import com.example.catalog.CatalogApiModels.CreateProduct;
import com.example.catalog.CatalogApiModels.Product;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class CatalogController {

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/products",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Product> all() {
        return service.all();
    }

    @GetMapping(
        path = "/products/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Product>> byId(
            @PathVariable String id) {

        return service.findById(id)
            .map(product -> ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Catalog-Version", "v1")
                .eTag("\"catalog-" + id + "-v1\"")
                .cacheControl(CacheControl.noStore())
                .body(product))
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @PostMapping(
        path = "/products",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Product>> create(
            @RequestBody Mono<CreateProduct> request) {

        return request.map(input -> {
            if (input.name() == null
                    || input.name().isBlank()) {
                throw new IllegalArgumentException(
                    "name must not be blank");
            }
            if (input.price() < 0) {
                throw new IllegalArgumentException(
                    "price must not be negative");
            }

            Product created = new Product(
                "p-new",
                input.name(),
                input.price(),
                true,
                List.of("new"));

            return ResponseEntity
                .created(URI.create("/api/products/p-new"))
                .header("X-Request-Id", "req-123")
                .contentType(MediaType.APPLICATION_JSON)
                .body(created);
        });
    }

    @GetMapping(
        path = "/diagnostics/cookie",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CookieInfo> demoCookie() {
        ResponseCookie cookie = ResponseCookie
            .from("demo_pref", "enabled")
            .path("/api")
            .maxAge(Duration.ofMinutes(15))
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .build();

        return ResponseEntity.ok()
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .header("X-Request-Id", "req-123")
            .contentType(MediaType.APPLICATION_JSON)
            .body(new CookieInfo(true));
    }

    @GetMapping("/diagnostics/empty")
    public ResponseEntity<Void> empty() {
        return ResponseEntity.noContent().build();
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> invalidInput(
            IllegalArgumentException error) {

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .contentType(MediaType.APPLICATION_JSON)
            .body(new ApiError(
                "INVALID_INPUT", error.getMessage()));
    }
}
~~~

Giải thích các quyết định kiểm thử:

1. Dữ liệu sản phẩm cố định và có thứ tự xác định.
2. GET /products/p1 phát JSON cùng headers do endpoint chủ động tạo.
3. GET không tìm thấy trả ResponseEntity.notFound(), không có JSON body.
4. POST trả 201 và Location, kèm header X-Request-Id.
5. POST name trống phát IllegalArgumentException được @ExceptionHandler chuyển thành status 400 và ApiError JSON.
6. POST text/plain bị từ chối bởi consumes application/json, thường trả 415.
7. Cookie được tạo bằng ResponseCookie, không phải tự ghép thuộc tính raw bằng tay.
8. Secure/HttpOnly/SameSite được kiểm thử nhưng demo_pref không chứa credential nhạy cảm.
9. Endpoint 204 trả ResponseEntity<Void> không có body.
10. Không có background work hoặc source biến động, giúp test ít flakiness.

## 16. Controller slice tests với @WebFluxTest

Test class dưới đây dùng @WebFluxTest(CatalogController.class) và @Import(CatalogService.class) để đưa service bất biến vào context. WebTestClient được Spring Boot inject. Không chạy embedded HTTP server thật trong slice test.

### CatalogControllerTest.java

~~~java
package com.example.catalog;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import com.example.catalog.CatalogApiModels.CreateProduct;
import com.example.catalog.CatalogApiModels.Product;

@WebFluxTest(CatalogController.class)
@Import(CatalogService.class)
class CatalogControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void getProductChecksStatusAndImportantHeaders() {
        client.get()
            .uri("/api/products/p1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectHeader()
                .valueEquals(
                    "X-Catalog-Version", "v1")
            .expectHeader()
                .valueEquals(
                    HttpHeaders.ETAG,
                    "\"catalog-p1-v1\"")
            .expectHeader()
                .cacheControl(CacheControl.noStore());
    }

    @Test
    void getProductChecksJsonPathValuesAndTypes() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("p1")
            .jsonPath("$.name").isEqualTo("Keyboard")
            .jsonPath("$.price").isEqualTo(1200)
            .jsonPath("$.available").isEqualTo(true)
            .jsonPath("$.tags").isArray()
            .jsonPath("$.tags[0]").isEqualTo("input");
    }

    @Test
    void getProductChecksStrictJsonDocument() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json(
                "{\"id\":\"p1\","
                + "\"name\":\"Keyboard\","
                + "\"price\":1200,"
                + "\"available\":true,"
                + "\"tags\":[\"input\",\"office\"]}",
                true);
    }

    @Test
    void listChecksJsonArrayPaths() {
        client.get().uri("/api/products")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$").isArray()
            .jsonPath("$[0].id").isEqualTo("p1")
            .jsonPath("$[1].id").isEqualTo("p2")
            .jsonPath("$[1].available").isEqualTo(false);
    }

    @Test
    void listCanBeDecodedIntoTypedJavaRecords() {
        client.get().uri("/api/products")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Product.class)
            .hasSize(2)
            .contains(new Product(
                "p1", "Keyboard", 1200, true,
                List.of("input", "office")));
    }

    @Test
    void missingProductReturns404AndEmptyBody() {
        client.get().uri("/api/products/unknown")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody().isEmpty();
    }

    @Test
    void createReturns201LocationHeaderAndProduct() {
        client.post().uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateProduct("Notebook", 700))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .location("/api/products/p-new")
            .expectHeader()
                .valueMatches(
                    "X-Request-Id", "req-[0-9]{3}")
            .expectBody(Product.class)
            .consumeWith(result -> {
                Product created = result.getResponseBody();

                assertNotNull(created);
                assertEquals("p-new", created.id());
                assertEquals("Notebook", created.name());
                assertEquals(700, created.price());
            });
    }

    @Test
    void invalidInputReturns400AndErrorJson() {
        client.post().uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateProduct("", -1))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .json(
                "{\"code\":\"INVALID_INPUT\","
                + "\"message\":\"name must not be blank\"}",
                true);
    }

    @Test
    void unsupportedRequestMediaTypeReturns415() {
        client.post().uri("/api/products")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("raw-text")
            .exchange()
            .expectStatus().isEqualTo(415);
    }

    @Test
    void unsupportedHttpMethodReturns405() {
        client.put().uri("/api/products/p1")
            .exchange()
            .expectStatus().isEqualTo(405);
    }

    @Test
    void responseCookieHasRequiredAttributes() {
        client.get().uri("/api/diagnostics/cookie")
            .exchange()
            .expectStatus().isOk()
            .expectCookie().exists("demo_pref")
            .expectCookie().valueEquals(
                "demo_pref", "enabled")
            .expectCookie().path("demo_pref", "/api")
            .expectCookie().maxAge(
                "demo_pref", Duration.ofMinutes(15))
            .expectCookie().httpOnly("demo_pref", true)
            .expectCookie().secure("demo_pref", true)
            .expectCookie().sameSite("demo_pref", "Lax");
    }

    @Test
    void rawSetCookieAndCustomHeaderCanBeChecked() {
        client.get().uri("/api/diagnostics/cookie")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .valueMatches(
                    HttpHeaders.SET_COOKIE,
                    "demo_pref=enabled;.*")
            .expectHeader()
                .valueEquals("X-Request-Id", "req-123")
            .expectBody()
                .jsonPath("$.enabled").isEqualTo(true);
    }

    @Test
    void ordinaryProductResponseHasNoDemoCookie() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectStatus().isOk()
            .expectCookie().doesNotExist("demo_pref")
            .expectHeader()
                .doesNotExist(HttpHeaders.SET_COOKIE);
    }

    @Test
    void noContentResponseHas204AndNoBody() {
        client.get().uri("/api/diagnostics/empty")
            .exchange()
            .expectStatus().isNoContent()
            .expectHeader()
                .doesNotExist(HttpHeaders.CONTENT_TYPE)
            .expectBody().isEmpty();
    }

    @Test
    void expectAllCanReportSeveralFailuresAtOnce() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectAll(
                spec -> spec.expectStatus().isOk(),
                spec -> spec.expectHeader()
                    .valueEquals("X-Catalog-Version", "v1"),
                spec -> spec.expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
            .expectBody()
            .jsonPath("$.id").isEqualTo("p1");
    }

    @Test
    void rawBodyCanBeConsumedWhenCustomAssertionIsNeeded() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .consumeWith(result -> {
                byte[] bytes = result.getResponseBody();

                assertNotNull(bytes);
                String json = new String(
                    bytes, StandardCharsets.UTF_8);
                assertTrue(json.contains("\"Keyboard\""));
            });
    }
}
~~~

### Đọc test theo nhóm

- Tests 1–3: GET status, các header quan trọng, JSONPath và strict JSON.
- Tests 4–5: danh sách JSON array qua JSONPath và typed body list.
- Test 6: 404 phải có body rỗng theo hợp đồng.
- Test 7: POST có 201, Location, custom header và DTO đúng.
- Test 8: lỗi input thành 400 + JSON error schema.
- Tests 9–10: 415 và 405 là regression checks cho request contract.
- Tests 11–13: cookie value, Path, Max-Age, Secure, HttpOnly, SameSite; raw header và sự vắng mặt của cookie ở endpoint khác.
- Test 14: response 204 không có Content-Type/body.
- Test 15: expectAll để nhóm assertion cùng một exchange.
- Test 16: consumeWith khi cần một assertion tùy biến trên raw response bytes.

Một số test cố ý kết hợp status, header và body trong cùng exchange để bảo vệ nhiều phần của **một HTTP response**. Không nên tách thành nhiều request riêng nếu việc phát response có side effect hoặc dữ liệu biến động.

## 17. Kiểm thử HTTP tích hợp qua embedded server

Slice test kiểm tra WebFlux handler trong context thu gọn. Thêm một integration test để xác nhận ứng dụng thực sự chạy embedded server, encode JSON và phát cookie qua HTTP.

### CatalogHttpIntegrationTest.java

~~~java
package com.example.catalog;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CatalogHttpIntegrationTest {

    @Autowired
    private WebTestClient client;

    @Test
    void productContractWorksOverEmbeddedHttpServer() {
        client.get().uri("/api/products/p1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Catalog-Version", "v1")
            .expectBody()
            .jsonPath("$.id").isEqualTo("p1");
    }

    @Test
    void cookieIsSerializedWithSecurityAttributes() {
        client.get().uri("/api/diagnostics/cookie")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists(HttpHeaders.SET_COOKIE)
            .expectCookie().exists("demo_pref")
            .expectCookie().httpOnly("demo_pref", true)
            .expectCookie().secure("demo_pref", true)
            .expectCookie().sameSite("demo_pref", "Lax")
            .expectCookie().maxAge(
                "demo_pref", Duration.ofMinutes(15));
    }
}
~~~

Sự khác biệt quan trọng: RANDOM_PORT mở socket HTTP thật trong test, nhưng test này vẫn không phải browser end-to-end. WebTestClient kiểm tra HTTP response và cookie attributes; nó không mô phỏng đầy đủ chính sách cookie của Chrome/Safari, CORS, proxy, TLS termination hoặc CDN.

Nếu cần kiểm thử security filter hoặc authentication, bổ sung các ca 401, 403, CSRF, cookie session, bearer token theo security configuration thực của ứng dụng.

## 18. Chạy Maven và kiểm tra kết quả

Yêu cầu môi trường: Java 17+, Maven 3.8+ và khả năng tải dependencies Maven. Đặt các file đúng package com.example.catalog như cấu trúc dự án.

### Chạy tests

~~~bash
java -version
mvn -version
mvn -q clean test
~~~

Có 16 test method trong CatalogControllerTest và 2 test method trong CatalogHttpIntegrationTest, tổng cộng 18 test. Nếu tất cả thành công, Maven hoàn tất với exit code 0.

Để xem báo cáo dễ đọc hơn:

~~~bash
mvn test
~~~

Kết quả cuối thông thường có dạng:

~~~text
Tests run: 16, Failures: 0, Errors: 0, Skipped: 0
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **minh họa output kỳ vọng**, không phải kết quả Maven đã được thực thi trong quá trình soạn bài. Thứ tự các dòng và log phụ thuộc phiên bản Maven Surefire, hệ điều hành và test configuration.

### Chạy ứng dụng

~~~bash
mvn spring-boot:run
~~~

Mặc định ứng dụng lắng nghe http://localhost:8080 nếu không có cấu hình port khác.

### Kiểm tra GET

~~~bash
curl -i "http://localhost:8080/api/products/p1" \
  -H "Accept: application/json"
~~~

Status và dữ liệu mong đợi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Catalog-Version: v1
ETag: "catalog-p1-v1"
Cache-Control: no-store
~~~

~~~json
{"id":"p1","name":"Keyboard","price":1200,"available":true,"tags":["input","office"]}
~~~

Một số header kỹ thuật như Date, Content-Length hoặc Transfer-Encoding tùy server. Không viết test yêu cầu tất cả các header kỹ thuật phải xuất hiện theo đúng một thứ tự.

### Kiểm tra POST

~~~bash
curl -i -X POST "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook","price":700}'
~~~

Status mong đợi: 201 Created; Location /api/products/p-new; X-Request-Id req-123. Body mong đợi:

~~~json
{"id":"p-new","name":"Notebook","price":700,"available":true,"tags":["new"]}
~~~

### Kiểm tra response cookie

~~~bash
curl -i "http://localhost:8080/api/diagnostics/cookie"
~~~

Header Set-Cookie mong đợi có các thuộc tính sau, nhưng thứ tự và định dạng Expires có thể thay đổi:

~~~text
demo_pref=enabled
Path=/api
Max-Age=900
Secure
HttpOnly
SameSite=Lax
~~~

Cookie này không có tác dụng authentication. Với browser, cần HTTPS để kiểm tra hành vi gửi cookie có Secure.

## 19. Assertion nào nên chọn cho từng loại hợp đồng?

| Yêu cầu | Assertion nên ưu tiên | Không nên chỉ dùng |
| --- | --- | --- |
| POST phải trả 201 | expectStatus().isCreated() | is2xxSuccessful() |
| Response là JSON | contentTypeCompatibleWith(APPLICATION_JSON) | exists(Content-Type) |
| Location chính xác | expectHeader().location(...) | exists(Location) |
| ETag đúng | valueEquals(ETag, ...) | exists(ETag) |
| X-Request-Id có format | valueMatches(...) | exists(...) |
| Cookie có HttpOnly | expectCookie().httpOnly(name, true) | exists(name) |
| Cookie có Secure | expectCookie().secure(name, true) | valueEquals(name, value) |
| Cookie không được xuất hiện | expectCookie().doesNotExist(name) | Bỏ kiểm tra |
| JSON chỉ cần field ID | jsonPath("$.id").isEqualTo(...) | Strict toàn document |
| JSON schema đóng | json(expected, true) | Chỉ check một field |
| Array có n phần tử | expectBodyList(...).hasSize(n) | exists("$") |
| Empty body | expectBody().isEmpty() | Chỉ status 204 |
| Error JSON có code | jsonPath("$.code").isEqualTo(...) | Chỉ 400 |
| Business model deserialize | expectBody(Product.class) | So sánh chuỗi raw |

Một bộ test tốt không nhất thiết nhiều assertion nhất; nó nên bảo vệ những thuộc tính dễ gây lỗi và có ý nghĩa với consumer.

## 20. Kiểm tra JSON lỗi và ProblemDetail

Một lỗi có thể được trả về theo schema riêng:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "name must not be blank"
}
~~~

Khi đó:

~~~java
client.post().uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateProduct("", 100))
    .exchange()
    .expectStatus().isBadRequest()
    .expectBody()
    .jsonPath("$.code").isEqualTo("INVALID_INPUT")
    .jsonPath("$.message").isEqualTo("name must not be blank");
~~~

Nếu ứng dụng dùng ProblemDetail/RFC 9457, response có thể là application/problem+json và body gồm type, title, status, detail, instance. Test theo cấu trúc mà API thật đã cam kết:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Invalid input"
}
~~~

Đừng copy test ProblemDetail vào demo mặc định mà không có error handling tương ứng; response của CatalogController hiện dùng ApiError riêng.

### Negative test giúp phát hiện thay đổi ngoài ý muốn

Không chỉ test đường thành công. Những lỗi phổ biến có thể không xuất hiện trong happy path:

- Request body không hợp lệ.
- Content-Type không hỗ trợ.
- Resource không tồn tại.
- Method không được mapping.
- Response thiếu một header đã cam kết.
- Cookie bị mất HttpOnly/SameSite.
- JSON field đổi tên hoặc đổi kiểu.

Đặt test theo hợp đồng mong muốn chứ không theo hành vi lỗi hiện tại nếu hành vi đó không đúng.

## 21. Khi nào dùng consumeWith, returnResult và StepVerifier?

### consumeWith

Dùng khi assertion DSL thiếu điều bạn cần:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody(Product.class)
    .consumeWith(result -> {
        Product value = result.getResponseBody();
        assertNotNull(value);
        assertEquals("Keyboard", value.name());
    });
~~~

consumeWith cung cấp ExchangeResult cho assertion tùy chỉnh và có thể quan sát status/headers tùy overload, nhưng đừng lặp lại nhiều assertion đã có cách diễn đạt trực tiếp trong WebTestClient nếu không cần.

### returnResult

Khi muốn lấy EntityExchangeResult sau kiểm tra:

~~~java
EntityExchangeResult<Product> result = client.get()
    .uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody(Product.class)
    .returnResult();

Product product = result.getResponseBody();
assertNotNull(product);
~~~

Đối với SSE hoặc NDJSON streaming, nên dùng returnResult(Event.class) để lấy FluxExchangeResult và StepVerifier tiêu thụ stream. Không dùng expectBodyList() để chờ một stream vô hạn hoàn tất.

### Ví dụ stream có giới hạn

~~~java
FluxExchangeResult<Event> result = client.get()
    .uri("/api/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(Event.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(3)
    .thenCancel()
    .verify();
~~~

Đây là **fragment minh họa** cho một API /api/events và Event class sẽ phải được định nghĩa ở project có streaming endpoint. Nó không nằm trong CatalogController demo, nên không phải một test độc lập của project trên. Hãy dùng StepVerifier khi kiểm tra event timing, backpressure, cancellation hoặc publisher chưa tự hoàn tất.

## 22. Những lỗi phổ biến và cách khắc phục

1. **Chỉ kiểm tra status 200.** JSON/header có thể sai; thêm assertion theo contract quan trọng.
2. **Dùng is2xxSuccessful khi yêu cầu đúng 201.** Một response 200 không bị phát hiện; dùng isCreated().
3. **Bắt buộc Content-Type bằng raw string khi charset không quan trọng.** Dùng contentTypeCompatibleWith nếu đó là contract.
4. **Chỉ kiểm tra header exists.** Nó không phát hiện giá trị sai; dùng valueEquals/valueMatches.
5. **Dùng regex .*.** Regex quá rộng không kiểm tra format thực; yêu cầu prefix/pattern hợp đồng.
6. **Nhầm Cookie request với Set-Cookie response.** cookie(...) và expectCookie(...) có ý nghĩa khác nhau.
7. **Chỉ kiểm tra cookie value mà bỏ thuộc tính bảo mật.** Dùng httpOnly/secure/sameSite/path/maxAge.
8. **So khớp Set-Cookie nguyên chuỗi.** Thứ tự/Expires có thể thay đổi; ưu tiên CookieAssertions.
9. **Hiểu Secure cookie sẽ hoạt động đầy đủ qua HTTP test.** Test chỉ xác minh header; kiểm tra behavior browser qua HTTPS riêng.
10. **So sánh JSON bằng String.equals.** Whitespace và thứ tự key làm test giòn; dùng json()/JSONPath.
11. **Dùng strict JSON cho API có field mở rộng.** Thêm field hợp lệ khiến test fail; cân nhắc lenient hoặc JSONPath.
12. **Dùng lenient JSON cho contract đóng.** Field thừa có thể lọt; dùng strict khi cần.
13. **Dùng isEqualTo("1200") cho JSON number.** Kiểu dữ liệu không đúng; assert number hoặc target DTO.
14. **Giả định missing field giống null field.** Dùng assertion thể hiện rõ khác biệt schema.
15. **Dùng expectBodyList cho infinite SSE.** Test sẽ chờ completion không bao giờ đến; dùng returnResult + StepVerifier.
16. **Quên bodyValue cho POST.** Endpoint có @RequestBody có thể fail với input rỗng.
17. **Quên Content-Type trên POST.** Có thể trả 415; cấu hình contentType(APPLICATION_JSON).
18. **Không @Import hoặc mock dependency ở @WebFluxTest.** Controller không tạo được bean và test không chạy; khai báo dependencies rõ.
19. **Chạy @SpringBootTest với port cứng.** Dễ đụng port CI; dùng RANDOM_PORT.
20. **Dùng dữ liệu mutable dùng chung giữa test.** Order-dependent failures; dùng fixture bất biến hoặc reset state.
21. **Tắt Spring Security trong test cần authorization.** Test có thể 200 giả khi production trả 401/403; dùng đúng security config.
22. **Hardcode timestamp hoặc UUID không được khống chế.** Giảm flakiness bằng injected clock/ID generator hoặc kiểm tra pattern.
23. **Chỉ kiểm tra 404 status khi API có error schema.** Consumer có thể cần code/message; assert đúng JSON lỗi.
24. **Không phân biệt 204 và 200 với body rỗng.** Kiểm tra cả status lẫn isEmpty.
25. **Dùng DTO server để thay mọi consumer-contract test.** Có thể bỏ sót tương thích phiên bản giữa các service.
26. **Viết test cho header của proxy nhưng chạy slice không có proxy.** Chọn đúng layer test; tách server behavior và deployment infrastructure.
27. **Gọi API production trong integration test.** Dễ thay đổi dữ liệu thật; dùng embedded test server và fixture riêng.
28. **Không kiểm tra test names và lỗi có ý nghĩa.** Tên test nên nói lên contract; tránh tên chung như test1.

## 23. Checklist kiểm thử response WebFlux

Trước khi hoàn tất một API, hãy kiểm tra:

- Route và HTTP method có khớp contract không?
- Request có Accept và Content-Type đúng không?
- Status thành công có đúng 200/201/204 theo nghiệp vụ không?
- Với 201, có Location nếu contract yêu cầu không?
- Với 204, body có thật sự rỗng không?
- Với GET, Content-Type có đúng application/json hoặc media type cam kết không?
- ETag, Cache-Control, correlation ID có được trả đúng và ổn định không?
- Những header không được xuất hiện có thực sự vắng mặt không?
- Cookie response có đúng name và value không?
- Path, Domain, Max-Age, SameSite, Secure, HttpOnly có được kiểm tra khi cần không?
- Test có phân biệt request cookie với Set-Cookie response không?
- JSON body có đúng field bắt buộc và type không?
- Field null và field bị thiếu có được xử lý theo contract không?
- JSON array có đúng kích thước và thứ tự khi thứ tự quan trọng không?
- Strict/lenient JSON compare được chọn có chủ đích không?
- Có test error status và JSON schema cho input không hợp lệ không?
- 404, 405, 415 và các điều kiện lỗi khác có được bao phủ không?
- @WebFluxTest đã import/mock dependencies cần thiết chưa?
- Khi kiểm tra mạng/filters thật, có @SpringBootTest với RANDOM_PORT không?
- Test fixture có bất biến, deterministic và không phụ thuộc thứ tự chạy không?
- Có test WebSocket/SSE/NDJSON riêng nếu endpoint streaming không?
- Những assertion cần browser/CDN/TLS có được kiểm thử ở môi trường thích hợp không?

## 24. Bài tập tự kiểm tra

**Câu 1.** API WebTestClient nào kiểm tra HTTP status?  
**Đáp án:** expectStatus(), ví dụ isOk(), isCreated() hoặc isNotFound().

**Câu 2.** is2xxSuccessful() khác isCreated() như thế nào?  
**Đáp án:** is2xxSuccessful cho mọi status 2xx; isCreated chỉ đúng 201.

**Câu 3.** contentTypeCompatibleWith dùng khi nào?  
**Đáp án:** Khi cần xác nhận response có media type tương thích, không bắt đúng mọi tham số header.

**Câu 4.** valueMatches khác exists ở đâu?  
**Đáp án:** exists chỉ xác nhận header có mặt; valueMatches còn kiểm tra regex của giá trị header.

**Câu 5.** cookie("language", "vi") có kiểm tra Set-Cookie response không?  
**Đáp án:** Không; nó gửi Cookie trong request. Dùng expectCookie để kiểm tra response.

**Câu 6.** Làm sao kiểm tra HttpOnly?  
**Đáp án:** expectCookie().httpOnly(cookieName, true).

**Câu 7.** Làm sao kiểm tra Secure và SameSite?  
**Đáp án:** expectCookie().secure(name, true) và sameSite(name, "Lax") hoặc giá trị hợp đồng.

**Câu 8.** JSONPath "$[0].id" lấy gì?  
**Đáp án:** Giá trị id của phần tử đầu nếu JSON root là array.

**Câu 9.** json(expected, true) trong Spring Framework 6.1 có ý nghĩa gì?  
**Đáp án:** So sánh strict JSON, không cho field thừa và yêu cầu array ordering.

**Câu 10.** Nếu chỉ muốn kiểm tra $.id, nên chọn gì?  
**Đáp án:** expectBody().jsonPath("$.id").isEqualTo(...).

**Câu 11.** Có thể decode JSON thành Java record trong WebTestClient không?  
**Đáp án:** Có, bằng expectBody(RecordType.class), rồi assert các field.

**Câu 12.** @WebFluxTest có tự import tất cả @Service không?  
**Đáp án:** Không. Dùng @MockBean hoặc @Import cho dependency phù hợp.

**Câu 13.** Khi nào cần @SpringBootTest(webEnvironment=RANDOM_PORT)?  
**Đáp án:** Khi muốn kiểm thử application context lớn hơn và HTTP qua embedded server thật.

**Câu 14.** Vì sao 204 nên đi cùng expectBody().isEmpty()?  
**Đáp án:** Để bảo vệ cả status lẫn điều kiện không có body.

**Câu 15.** Vì sao không nên assert raw Set-Cookie toàn chuỗi?  
**Đáp án:** Thứ tự và định dạng một số attribute có thể thay đổi dù semantics giống nhau.

**Câu 16.** WebTestClient có mô phỏng đầy đủ cookie policy của browser không?  
**Đáp án:** Không. Nó kiểm tra HTTP response; browser behavior cần test riêng qua môi trường phù hợp.

## 25. Ghi nhớ

Kiểm thử WebFlux response cần xác minh bốn mặt của hợp đồng: **HTTP status, response headers, response cookies và JSON body**. WebTestClient cung cấp DSL tương ứng: expectStatus(), expectHeader(), expectCookie() và expectBody(). Đừng chỉ kiểm tra status khi header, cookie hoặc body ảnh hưởng trực tiếp tới consumer.

Với header, ưu tiên semantic checks như contentTypeCompatibleWith, location, cacheControl, valueEquals hoặc valueMatches. Với cookie, phân biệt request cookie và Set-Cookie response, rồi kiểm tra Path, Max-Age, HttpOnly, Secure và SameSite khi có ý nghĩa bảo mật. Với JSON, dùng JSONPath cho vài field, json() lenient cho contract mở, json(..., true) strict cho contract đóng, hoặc expectBody(Class)/expectBodyList(Class) để kiểm tra object đã decode.

Chọn @WebFluxTest cho controller slice nhanh, @SpringBootTest với RANDOM_PORT khi cần HTTP integration thật. Giữ fixture ổn định, không phụ thuộc thời gian/ID ngẫu nhiên và bao phủ cả error cases. Trường hợp streaming như SSE, dùng returnResult và StepVerifier thay vì đợi toàn bộ stream thành body hữu hạn.

### Tài liệu tham khảo

- Spring Framework, [WebTestClient — Binding and Assertions](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- Spring Framework 6.1 Javadoc, [WebTestClient](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html).
- Spring Framework 6.1 Javadoc, [HeaderAssertions](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/HeaderAssertions.html).
- Spring Framework 6.1 Javadoc, [CookieAssertions](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/CookieAssertions.html).
- Spring Framework 6.1 Javadoc, [JsonPathAssertions](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/JsonPathAssertions.html).
- Spring Framework 6.1 Javadoc, [WebTestClient.BodyContentSpec](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.BodyContentSpec.html).
- Spring Boot 3.3, [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/docs/3.3.5/reference/html/features.html#features.testing).
- Spring Boot, [AutoConfigureWebTestClient](https://docs.spring.io/spring-boot/docs/3.3.5/api/org/springframework/boot/test/autoconfigure/web/reactive/AutoConfigureWebTestClient.html).
