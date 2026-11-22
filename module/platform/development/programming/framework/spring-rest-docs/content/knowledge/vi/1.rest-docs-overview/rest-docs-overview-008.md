# Kiến thức HTTP, REST, JSON, kiểm thử và build cần chuẩn bị

## Mục tiêu học tập

Trước khi thực hành Spring REST Docs, người học cần có nền tảng đủ để đọc một HTTP exchange, hiểu cấu trúc tài nguyên REST, nhận biết JSON request/response, viết kiểm thử có assertion và chạy được quy trình build. Sau bài này, bạn có thể:

- Phân tích method, URI, status code, header và body của một HTTP request/response.
- Hiểu các nguyên tắc REST thường gặp: resource, representation, statelessness, idempotency, cache và content negotiation.
- Đọc và mô tả JSON, gồm object, array, kiểu dữ liệu, field lồng nhau, giá trị tùy chọn và `null`.
- Viết HTTP test cơ bản với JUnit và công cụ phù hợp như MockMvc, WebTestClient hoặc REST Assured.
- Hiểu vai trò của assertion, fixture, test isolation, test data và các tình huống thành công/thất bại.
- Nhận biết các đầu vào cần có của quá trình build: dependency, plugin, task, output directory và thứ tự chạy test trước khi sinh tài liệu.

## 1. Bản đồ kiến thức cần chuẩn bị

Spring REST Docs nằm ở điểm giao giữa kiểm thử HTTP và biên soạn tài liệu. Người học không cần phải là chuyên gia mạng máy tính, nhưng cần hiểu request/response để biết snippet đang ghi lại điều gì và assertion nào có ý nghĩa.

| Nền tảng | Cần biết gì? | Được sử dụng ở phần nào của REST Docs? |
| --- | --- | --- |
| HTTP | Method, URI, status, header, body, media type | Đọc và ghi snippet request/response |
| REST | Resource, URI, method semantics, statelessness, idempotency | Hiểu hợp đồng và ví dụ API |
| JSON | Object, array, field path, kiểu dữ liệu, null, nested data | Viết request/response field descriptor |
| Java và Spring | Controller, DTO, serialization, exception handling | Hiểu ứng dụng được test đang xử lý request |
| Kiểm thử | JUnit, assertion, fixture, test isolation | Viết documentation test có thể lặp lại |
| Build | Dependency, plugin, task, output directory, CI | Tự động sinh và render tài liệu |
| Tài liệu kỹ thuật | Heading, bảng, code block, AsciiDoc/Markdown | Kết hợp snippet với giải thích cho người dùng API |

Không cần học tất cả lý thuyết trước khi bắt đầu một bài thực hành nhỏ. Hãy hiểu request/response trước, sau đó viết một test HTTP thành công, sinh một snippet, rồi mở rộng sang parameter, header, payload và tình huống lỗi.

## 2. Nền tảng HTTP

HTTP là giao thức trao đổi request/response giữa client và server. Khi đọc tài liệu REST API, trước hết hãy nhận biết bốn phần: **request line, request headers, request body** và các phần tương ứng của response.

### 2.1. Một HTTP request gồm những gì?

Ví dụ client yêu cầu thông tin đơn hàng:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>
```

- `GET` là method.
- `/api/orders/42` là request target/path.
- `Host` xác định host đích trong HTTP/1.1.
- `Accept` cho server biết client ưu tiên loại representation nào.
- `Authorization` mang thông tin xác thực theo cơ chế được API quy định.
- Request không có body trong ví dụ này; các method khác có thể có body.

Request tạo đơn hàng có thể là:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":7,"quantity":2}
```

`Content-Type` mô tả định dạng của body được gửi lên; `Accept` mô tả loại response client có thể nhận. Không nên nhầm hai header này.

### 2.2. Một HTTP response gồm những gì?

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/43

{"id":43,"status":"CREATED"}
```

- `201 Created` là status line, biểu thị tài nguyên mới được tạo theo ngữ nghĩa của HTTP.
- `Content-Type` mô tả media type của response body.
- `Location` thường chỉ URI liên quan đến tài nguyên được tạo trong tình huống này.
- Dòng trống phân cách header với body.
- JSON bên dưới là representation mà client đọc.

Trong Spring REST Docs, các thành phần này có thể được thể hiện qua snippet như `http-request`, `http-response`, `request-headers` và `response-headers`.

### 2.3. Method và tính chất cần hiểu

| Method | Ý nghĩa thường gặp | Đặc điểm cần chú ý |
| --- | --- | --- |
| `GET` | Lấy representation của resource | Safe; không nên dùng để yêu cầu thay đổi trạng thái nghiệp vụ |
| `POST` | Gửi dữ liệu để xử lý hoặc tạo tài nguyên dưới một collection | Không mặc định idempotent |
| `PUT` | Tạo/thay thế representation tại URI mục tiêu theo hợp đồng | Được định nghĩa là idempotent |
| `PATCH` | Áp dụng cập nhật một phần | Tính idempotent phụ thuộc semantics và cách thiết kế |
| `DELETE` | Yêu cầu xóa resource | Được định nghĩa là idempotent theo semantics HTTP, dù response giữa các lần gọi có thể khác |

**Safe** nghĩa là method được định nghĩa không yêu cầu thay đổi trạng thái của resource; **idempotent** nghĩa là thực hiện lặp lại cùng request có hiệu ứng dự kiến tương đương một lần thực hiện. Đây là semantics của method, không phải lời hứa rằng mọi endpoint được triển khai đều không có side effect ngoài ý muốn.

Khi tài liệu hóa, phải mô tả method thực tế và hành vi được API cam kết. Không kết luận `POST` luôn tạo dữ liệu mới hoặc mọi thao tác `PUT` đều thay thế toàn bộ object nếu hợp đồng cụ thể không định nghĩa như vậy.

### 2.4. Status code và cách phân nhóm

| Nhóm | Ý nghĩa khái quát | Ví dụ |
| --- | --- | --- |
| `1xx` | Thông tin/tạm thời | `100 Continue` |
| `2xx` | Request được tiếp nhận hoặc xử lý thành công | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| `3xx` | Điều hướng hoặc xử lý cache | `301 Moved Permanently`, `304 Not Modified` |
| `4xx` | Request/client không thể được xử lý như gửi | `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `429 Too Many Requests` |
| `5xx` | Lỗi phía server hoặc thành phần trung gian | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` |

Không chỉ ghi status thành công. Người sử dụng API cần biết các trường hợp lỗi có ý nghĩa, response body lỗi, khả năng retry và hành động khắc phục nếu API có quy định. Ví dụ `401` và `403` không đồng nghĩa: `401` liên quan đến xác thực cần thiết, còn `403` thể hiện request bị từ chối về quyền truy cập trong ngữ cảnh HTTP.

### 2.5. Header, media type và content negotiation

Header mang metadata về request/response. Một số header thường gặp:

| Header | Hướng | Mục đích |
| --- | --- | --- |
| `Accept` | Request | Loại representation client muốn nhận |
| `Content-Type` | Request/Response | Media type của body đang gửi/nhận |
| `Authorization` | Request | Thông tin xác thực theo scheme |
| `Location` | Response | URI liên quan đến tài nguyên hoặc đích được chỉ định |
| `Cache-Control` | Request/Response | Chỉ thị về cache |
| `ETag` | Response | Validator cho representation |
| `If-Match` | Request | Điều kiện cập nhật dựa trên validator |

Ví dụ `Accept: application/json` thể hiện client muốn JSON. Nếu server hỗ trợ nhiều định dạng, cơ chế content negotiation có thể ảnh hưởng response; test cần gửi header thích hợp để ghi lại đúng tình huống. Không đưa token thật hoặc cookie nhạy cảm vào snippet được phát hành.

## 3. Nền tảng REST

REST là tập hợp các ràng buộc kiến trúc cho hệ thống phân tán. Một API được gọi là RESTful không chỉ vì nó dùng JSON hoặc URL có dấu gạch chéo.

Những khái niệm hữu ích khi đọc API docs:

- **Resource:** khái niệm hoặc đối tượng được hệ thống quản lý, ví dụ đơn hàng hoặc khách hàng.
- **URI:** định danh resource, ví dụ `/api/orders/42`.
- **Representation:** dữ liệu biểu diễn resource tại một thời điểm, ví dụ JSON chứa `id`, `status`.
- **Statelessness:** mỗi request chứa đủ ngữ cảnh cần thiết để server xử lý; server không phụ thuộc ngầm vào session client giữa các request như một điều kiện của giao thức ứng dụng.
- **Cacheability:** response có thể chỉ ra liệu representation có được cache và trong điều kiện nào.
- **Uniform interface:** client tương tác qua giao diện thống nhất dựa trên resource, representation, method và semantics.
- **Layered system:** client không nhất thiết biết mọi tầng trung gian xử lý request.

### 3.1. Resource và URI

URI thường đặt tên resource, còn method biểu thị thao tác:

| URI | Method | Ý nghĩa minh họa |
| --- | --- | --- |
| `/api/orders` | `GET` | Liệt kê/tìm các đơn hàng theo quy tắc API |
| `/api/orders` | `POST` | Tạo đơn hàng mới |
| `/api/orders/42` | `GET` | Lấy đơn hàng mã 42 |
| `/api/orders/42` | `PUT` | Thay representation tại resource theo hợp đồng |
| `/api/orders/42` | `DELETE` | Yêu cầu xóa đơn hàng |

Path parameter và query parameter có vai trò khác nhau:

- Path `/api/orders/42` định danh một đơn hàng.
- Query `/api/orders?page=0&size=20` biểu thị tiêu chí truy vấn/phân trang theo cách thiết kế API.

REST Docs có thể tạo snippet `path-parameters` và `query-parameters` khi test khai báo descriptor cho các tham số đó.

### 3.2. Statelessness, xác thực và retry

Statelessness không có nghĩa API không cần xác thực. Một request có thể mang bearer token trong `Authorization`; server xác minh request độc lập dựa trên credential và chính sách hiện tại.

Retry cần được thiết kế cẩn thận. Method có semantics idempotent không loại bỏ mọi rủi ro từ timeout, xử lý bất đồng bộ hoặc lỗi mạng. Nếu API hỗ trợ `Idempotency-Key`, tài liệu cần nêu cách gửi, phạm vi hiệu lực và hành vi khi cùng key được gửi lặp lại. Không tự giả định mọi endpoint `POST` đều an toàn khi retry.

### 3.3. Cache và validator

Một số API dùng `Cache-Control`, `ETag`, `Last-Modified`, `If-None-Match` hoặc `If-Modified-Since` để hỗ trợ cache và conditional request. Khi những hành vi này thuộc hợp đồng, nên có test và snippet tương ứng cho header/status, thay vì chỉ ghi ví dụ JSON.

## 4. Nền tảng JSON

JSON là định dạng văn bản dùng để biểu diễn dữ liệu có cấu trúc. Trong REST API, nó thường xuất hiện ở request body và response body với media type `application/json`.

### 4.1. Các kiểu dữ liệu cơ bản

```json
{
  "id": 42,
  "name": "Notebook",
  "active": true,
  "discount": null,
  "tags": ["office", "stationery"],
  "price": {
    "amount": 59000,
    "currency": "VND"
  }
}
```

| Cú pháp | Kiểu JSON | Lưu ý |
| --- | --- | --- |
| `42` | Number | JSON không phân biệt riêng int/long/decimal; quy tắc chính xác phụ thuộc schema và client |
| `"Notebook"` | String | Chuỗi đặt trong dấu nháy kép |
| `true`, `false` | Boolean | Không đặt trong dấu nháy |
| `null` | Null | Giá trị rỗng có chủ đích, khác việc không có field |
| `[]` | Array | Danh sách giá trị, có thể rỗng |
| `{}` | Object | Tập hợp các field key/value |

Các lỗi cú pháp phổ biến: dùng dấu nháy đơn, thiếu dấu phẩy/ngoặc, viết `NaN`, comment trực tiếp trong JSON hoặc dùng dấu phẩy cuối cùng sau phần tử cuối. Ví dụ bên dưới không phải JSON hợp lệ:

```text
{'id': 42,}
```

### 4.2. Field lồng nhau và path trong REST Docs

Với JSON:

```json
{
  "orderId": "ord-42",
  "total": {
    "amount": 199000,
    "currency": "VND"
  },
  "items": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
```

Các descriptor tương ứng thường dùng:

| JSON path | Mô tả |
| --- | --- |
| `orderId` | Mã đơn hàng |
| `total` | Thông tin tổng tiền |
| `total.amount` | Giá trị số tiền |
| `total.currency` | Mã tiền tệ |
| `items` | Danh sách dòng đơn hàng |
| `items[].sku` | Mã sản phẩm trong một dòng |
| `items[].quantity` | Số lượng trong một dòng |

Đối với object lồng nhau, cần khai báo object cha khi chế độ descriptor yêu cầu mô tả đầy đủ cấu trúc; với array object, `[]` biểu thị phần tử của mảng. Cách khai báo chính xác phải phù hợp payload thực tế và API REST Docs đang dùng.

### 4.3. Phân biệt thiếu field, null và giá trị mặc định

Ba trường hợp dưới đây khác nhau:

```json
{"name": "Lan"}
```

```json
{"name": "Lan", "nickname": null}
```

```json
{"name": "Lan", "nickname": ""}
```

- **Field bị thiếu:** client không nhận được key `nickname`.
- **Field là null:** key có mặt nhưng không chứa giá trị.
- **Field là chuỗi rỗng:** key có mặt và value là `""`.

Hợp đồng phải nói rõ trường nào bắt buộc, có thể vắng mặt, nullable, có giá trị mặc định hay có thể là chuỗi rỗng. Đừng kết luận `optional()` trong REST Docs tương đương với nullable trong schema: `optional()` liên quan việc field có thể không xuất hiện trong payload test được mô tả, còn `null` là một giá trị cần được xem xét theo contract.

## 5. Kiến thức Java và Spring cần có

Để đọc documentation test, người học nên nhận biết:

- **Controller:** nơi tiếp nhận request và định tuyến đến xử lý ứng dụng.
- **DTO/record:** kiểu dữ liệu dùng để nhận hoặc trả thông tin API; không nhất thiết là entity database.
- **Binding:** cách Spring chuyển path/query parameter hoặc request body thành tham số Java.
- **Serialization/deserialization:** chuyển object Java thành representation HTTP và ngược lại, thường thông qua Jackson trong ứng dụng Spring Boot.
- **Validation:** kiểm tra đầu vào, ví dụ `@Valid`, constraint annotation và xử lý lỗi tương ứng.
- **Exception handling:** cách exception được chuyển thành status và error body, thường thông qua `@ExceptionHandler` hoặc `@ControllerAdvice`.
- **Filter/security:** các lớp có thể từ chối request trước khi controller thực thi.

Ví dụ một DTO:

```java
public record CreateOrderRequest(
        @NotNull Long customerId,
        @NotEmpty List<OrderItemRequest> items
) {}

public record OrderItemRequest(
        @NotBlank String sku,
        @Positive int quantity
) {}
```

DTO và annotation giúp hiểu schema dự kiến, nhưng HTTP test mới xác nhận cách ứng dụng thực sự phản hồi với dữ liệu hợp lệ/không hợp lệ ở tầng đang kiểm tra. Ví dụ, response lỗi validation có status và cấu trúc JSON nào còn phụ thuộc cấu hình exception handler.

## 6. Nền tảng kiểm thử tự động

Spring REST Docs không tự tìm và chạy mọi request. Bạn cần có một bài kiểm thử HTTP chủ động mô phỏng một kịch bản.

### 6.1. Unit test, MVC test và integration test

| Loại test | Phạm vi điển hình | Khi dùng |
| --- | --- | --- |
| Unit test | Một class/logic với dependency được thay bằng mock/fake | Xác minh quy tắc nhỏ, tính toán, validation nghiệp vụ |
| MVC/WebFlux test | Hạ tầng web và controller trong môi trường test | Xác minh mapping, binding, HTTP response và sinh snippet |
| Integration test | Nhiều thành phần ứng dụng hoạt động cùng nhau | Xác minh wiring, serialization, database/security hoặc tích hợp cần thiết |
| End-to-end test | Đường đi rộng qua ứng dụng/server và có thể cả dependency ngoài | Kiểm chứng hành vi gần với trải nghiệm client hơn, nhưng thường tốn thời gian |

Không có một tầng test phù hợp với mọi cam kết. Nếu tài liệu mô tả lỗi security do filter tạo ra, bài test phải đưa security filter vào phạm vi. Một MockMvc `standaloneSetup` tối giản có thể không bao gồm các cấu hình đó.

### 6.2. Assertion và test có thể lặp lại

Assertion là điều kiện mà test đòi hỏi phải đúng. Ví dụ:

```java
mockMvc.perform(get("/api/orders/{id}", 42))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"));
```

Test này kiểm tra ba điều: status, mã đơn hàng và trạng thái. Chỉ gọi endpoint mà không assert gì không chứng minh hợp đồng. Chỉ kiểm tra status `200` cũng chưa đủ nếu client phụ thuộc vào trường JSON.

Test nên **repeatable** (có thể chạy lại cho kết quả xác định) và **isolated** (không phụ thuộc ngầm vào thứ tự test hoặc dữ liệu do một test khác tạo ra). Để đạt điều đó:

- Tạo fixture rõ ràng, dữ liệu giả không nhạy cảm.
- Cố định clock hoặc dữ liệu có timestamp nếu cần.
- Không phụ thuộc vào API bên ngoài không ổn định trong test tạo snippet.
- Dọn hoặc rollback dữ liệu sau test theo thiết kế test.
- Kiểm tra cả kết quả khi không có dữ liệu và khi dữ liệu sai.

### 6.3. Documentation test cần thêm descriptor

Một REST Docs test ngoài assertion còn cần chỉ định cấu trúc muốn công bố:

```java
document("orders-get",
    pathParameters(
        parameterWithName("id").description("Mã đơn hàng")
    ),
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("status").description("Trạng thái đơn hàng")
    )
)
```

Tên snippet `orders-get` trở thành phần của đường dẫn output. Descriptor không thay assertion về giá trị nghiệp vụ: mô tả `status` là “Trạng thái đơn hàng” không chứng minh giá trị `PAID` được áp dụng đúng.

## 7. Các test client sẽ gặp trong Spring REST Docs

| Công cụ | Phù hợp thường gặp | Cần chuẩn bị |
| --- | --- | --- |
| **MockMvc** | Spring MVC/Servlet | Spring MVC Test, JUnit, REST Docs MockMvc integration |
| **WebTestClient** | Spring WebFlux/reactive hoặc cấu hình test được hỗ trợ | WebTestClient, context/handler/server phù hợp, REST Docs WebTestClient integration |
| **REST Assured** | HTTP integration test gửi request đến server đang chạy | Server/port/fixture, REST Assured, REST Docs REST Assured integration |

Chọn công cụ dựa vào stack và phạm vi bằng chứng cần có:

- MVC controller test có thể bắt đầu bằng MockMvc.
- WebFlux reactive handler thường dùng WebTestClient.
- Cần kiểm tra request qua HTTP server thực trong integration test, REST Assured có thể phù hợp; WebTestClient cũng có thể kết nối server ở chế độ phù hợp.

Không cần dùng cả ba trong cùng dự án. Cấu hình test quyết định ứng dụng có chạy qua converter, security filter, exception handler hay server thật hay không.

## 8. Kiến thức build cần chuẩn bị

Build là quy trình biên dịch, kiểm thử và tạo artifact. Với Spring REST Docs, phần quan trọng là **test sinh snippet trước, bước biên soạn tài liệu đọc snippet sau**.

### 8.1. Những khái niệm build cơ bản

| Khái niệm | Ý nghĩa |
| --- | --- |
| Dependency | Thư viện mà source/test cần sử dụng, ví dụ `spring-restdocs-mockmvc` |
| Plugin | Mở rộng các task/capability của build tool, ví dụ Asciidoctor plugin |
| Task/phase | Đơn vị công việc hoặc giai đoạn trong build |
| Output directory | Thư mục chứa kết quả trung gian/artifact, ví dụ `build/generated-snippets` |
| Task dependency | Quan hệ buộc task này chạy sau task khác |
| CI | Hệ thống tự động build/test/render khi có commit hoặc pull request |

### 8.2. Vì sao thứ tự test rồi render quan trọng?

```text
HTTP documentation tests
        |
        v
build/generated-snippets/
        |
        v
Asciidoctor / Markdown renderer
        |
        v
HTML tài liệu API
```

Nếu Asciidoctor chạy trước khi snippet được tạo, lệnh include có thể không tìm thấy file. Nếu renderer sử dụng snippet cũ từ lần build trước, trang có thể lỗi thời dù code hiện tại đã thay đổi.

Một cấu hình Gradle minh họa:

```groovy
configurations {
    asciidoctorExt
}

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

def snippetsDir = file("$buildDir/generated-snippets")

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    configurations 'asciidoctorExt'
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
}
```

Đây là phần nối task để minh họa, chưa phải `build.gradle` hoàn chỉnh. Dự án cần khai báo plugin, version dependency tương thích, JUnit/Spring Test và cấu hình `snippets` attribute trong task Asciidoctor. Nếu dùng WebTestClient hoặc REST Assured, dependency REST Docs integration sẽ tương ứng với test client đó.

Với Gradle, sau khi cấu hình đầy đủ có thể chạy:

```bash
./gradlew clean test asciidoctor
```

Trên Windows:

```bat
gradlew.bat clean test asciidoctor
```

Với Maven, cũng cần phối hợp test sinh snippet và plugin Asciidoctor render tài liệu trong thứ tự phù hợp. Không mặc định đường dẫn output hay cấu hình Maven giống Gradle; cần đọc đúng cấu hình dự án.

### 8.3. CI và chất lượng artifact

CI có thể chạy:

1. Compile source và test.
2. Chạy HTTP documentation tests.
3. Xác nhận snippet của các tình huống bắt buộc được tạo.
4. Render tài liệu.
5. Kiểm tra lỗi include/output và lưu HTML artifact.
6. Phát hành tài liệu cùng version/commit của API.

Build sạch giúp tránh output cũ; dữ liệu test giả giúp ngăn lộ thông tin nhạy cảm; kiểm tra include giúp ngăn xuất bản trang thiếu snippet. Không phải mọi cấu hình renderer đều mặc định coi include bị thiếu là lỗi, nên cần xác minh bằng build thực tế.

## 9. Kiến thức AsciiDoc, Markdown và biên soạn

Snippet sinh tự động là mảnh tài liệu. Người viết cần biết cách tổ chức heading, bảng, đoạn giải thích và code block để hoàn thành trang có thể đọc.

AsciiDoc thường dùng directive:

```asciidoc
== HTTP response
include::{snippets}/orders-get/http-response.adoc[]
```

Thuộc tính `{snippets}` cần trỏ đúng thư mục output. Asciidoctor xử lý `include::...[]` và kết xuất trang; nó không thực hiện HTTP test.

Markdown có thể dùng nếu cấu hình template snippet phù hợp và hệ thống biên soạn hỗ trợ ghép nội dung. Markdown chuẩn không có cú pháp include của Asciidoctor. Không nên đổi đuôi `.adoc` thành `.md` mà không thay cách sinh và ghép file.

Trong phần văn bản do con người viết, hãy mô tả:

- Mục đích endpoint và lúc nào nên gọi.
- Điều kiện xác thực/phân quyền.
- Ngữ nghĩa field, enum, đơn vị và giá trị mặc định.
- Cách xử lý lỗi, retry, pagination hoặc idempotency nếu API cam kết.
- Phiên bản API và ghi chú tương thích.

## 10. Lộ trình học đề xuất

Người học có thể tự kiểm tra tiến độ theo các bước:

| Bước | Nội dung thực hành | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Đọc một HTTP request/response | Xác định method, URI, header, status, body |
| 2 | Đọc JSON object/array lồng nhau | Viết được JSON path cho field cần mô tả |
| 3 | Viết một test với JUnit và MockMvc | Gửi request, assert status và response |
| 4 | Thêm Spring REST Docs descriptor | Sinh snippet request/response/field |
| 5 | Viết một trang AsciiDoc có include | Render thành HTML có lời giải thích và snippet |
| 6 | Tạo test cho một tình huống lỗi | Tài liệu có ví dụ cho nhánh thất bại quan trọng |
| 7 | Chạy build từ workspace sạch | Test và render hoạt động đúng thứ tự |
| 8 | Đưa vào CI | Mỗi thay đổi liên quan được kiểm tra tự động |

### Các lỗi nền tảng cần khắc phục trước khi đi tiếp

| Dấu hiệu | Kiến thức cần ôn |
| --- | --- |
| Nhầm `Accept` với `Content-Type` | HTTP header và content negotiation |
| Không phân biệt `201` với `202` | HTTP semantics và status code |
| Không biết mô tả `items[].sku` | JSON array, object và field path |
| Chỉ assert status mà bỏ qua body | Thiết kế test và assertion theo hợp đồng |
| Không hiểu vì sao snippet không được tạo | JUnit lifecycle, REST Docs configuration và test output |
| Asciidoctor không tìm thấy file include | Build task ordering và output directory |
| Tài liệu có token hoặc dữ liệu thật | Test fixture, bảo mật và quản lý artifact |

## 11. Bài tập tự kiểm tra

Giả sử ứng dụng có endpoint `POST /api/orders`, request:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":7,"items":[{"sku":"BOOK-01","quantity":2}]}
```

Response:

```http
HTTP/1.1 201 Created
Location: /api/orders/43
Content-Type: application/json

{"id":43,"status":"CREATED"}
```

Hãy trả lời:

1. Method, path, media type, request fields và status thành công là gì?
2. Những header nào cần descriptor nếu muốn tài liệu hóa request và response?
3. Viết các assertion cần thiết để xác nhận status, `Location`, `id` và `status`.
4. Chọn `requestFields(...)` và `responseFields(...)` để mô tả các field JSON.
5. Đề xuất thêm ít nhất hai tình huống lỗi mà client cần biết; không tự đoán status nếu chưa có hợp đồng.
6. Cho biết task nào cần chạy trước Asciidoctor và tại sao.

**Câu hỏi mở rộng:** Test hiện tại trả status `201` và body đúng. Điều này có chứng minh request không thể tạo đơn trùng khi client retry không? Không. Muốn có cam kết đó phải xác định semantics/idempotency và viết test kiểm tra tình huống lặp lại.

## Kết luận

Để học Spring REST Docs hiệu quả, cần hiểu **HTTP và REST** để đọc contract, **JSON** để mô tả payload, **Java/Spring** để biết request đi qua ứng dụng ra sao, **JUnit và assertion** để viết test lặp lại được, và **build/Asciidoctor/CI** để sinh và phát hành tài liệu. Các nền tảng này giúp phân biệt request/response thực thi với lời giải thích nghiệp vụ. Spring REST Docs kết nối HTTP test bằng MockMvc, WebTestClient hoặc REST Assured với descriptor và snippet; Asciidoctor/Markdown hoàn thiện trang. Tài liệu đáng tin không chỉ có ví dụ đúng cú pháp mà còn phải được kiểm thử ở đúng phạm vi, có đủ tình huống quan trọng và được tạo từ đúng phiên bản API.
