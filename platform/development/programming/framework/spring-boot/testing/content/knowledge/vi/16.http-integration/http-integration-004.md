# Kiểm tra hợp đồng status, header, JSON và thông báo lỗi

Một HTTP integration test có giá trị không chỉ xác nhận rằng endpoint trả về `200 OK`. API có thể trả đúng mã trạng thái nhưng sai `Content-Type`, thiếu `Cache-Control`, làm mất correlation ID, đổi tên JSON field, tính sai tiền hoặc vô tình gửi stack trace trong thông báo lỗi. Ngược lại, body JSON có thể đúng trong một unit test nhưng request thật lại lỗi do route, HTTP message converter, servlet filter, cấu hình server hoặc exception handler.

**Hợp đồng HTTP (HTTP contract)** là tập hành vi mà client có quyền trông đợi từ endpoint: **method + path + input**, mã trạng thái, header, representation/body, thông báo lỗi và một số quy tắc vận hành (cache, authentication, idempotency, pagination...). Bài này hướng dẫn kiểm các mặt quan trọng bằng test có assertion rõ ràng, đồng thời chỉ ra giới hạn của từng cấp test.

Ví dụ chính sử dụng **Java 17+, Spring Boot 3.5.x, Spring MVC, JUnit Jupiter 5, Jackson và `TestRestTemplate`** với `@SpringBootTest(webEnvironment = RANDOM_PORT)` để gọi server HTTP thật trên localhost. Chúng ta giữ controller và service thật, không kết nối database hoặc dịch vụ production. Với Spring Boot 4.x/Spring Framework 7.x, một số package và auto-configuration liên quan REST test client đã đổi; cần theo tài liệu đúng version, không sao chép import từ nhánh 3.5 một cách máy móc.

## 1. Mục tiêu học tập

Sau bài, bạn sẽ có thể:

- Xây **ma trận HTTP contract** gồm method, path, status, header, JSON shape và error response.
- Phân biệt `@WebMvcTest`, full `@SpringBootTest` + `MockMvc` và full `@SpringBootTest(RANDOM_PORT)`.
- Chọn `TestRestTemplate`, `WebTestClient` hoặc `MockMvc` theo mục tiêu kiểm thử, không nhầm mock transport với HTTP server thật.
- Kiểm đúng `200`, `201`, `204`, `400`, `401`, `403`, `404`, `405`, `409`, `415` và `5xx` khi contract có những nhánh này.
- Kiểm `Content-Type`, `Accept`, `Location`, `Cache-Control`, correlation header, security headers và header nhiều giá trị khi cần.
- Parse JSON bằng Jackson `JsonNode` để kiểm type, key, nested object, mảng, dữ liệu Unicode, giá trị `null` và trường vắng mặt.
- Thiết kế error contract ổn định không làm lộ exception internals, stack trace hoặc thông tin nhạy cảm.
- Viết cả **positive tests** và **negative tests** cho tham số sai, JSON malformed và unsupported media type.
- Giữ test độc lập, xác định; đọc log, status, headers, body đúng tầng khi một assertion thất bại.

## 2. Một response HTTP gồm những gì?

Xét phản hồi minh họa khi xin báo giá:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
X-Request-Id: req-100

{
  "sku": "BOOK",
  "quantity": 2,
  "subtotalVnd": 240000,
  "discountVnd": 24000,
  "totalVnd": 216000
}
```

Một test chỉ kiểm `status == 200` không bắt được các lỗi:

- JSON thiếu `discountVnd` hoặc tên field bị đổi thành `discount`.
- `totalVnd` sai do giảm giá sai.
- HTTP body là text `"OK"`, không phải JSON.
- `Cache-Control` bị bỏ, khiến thông tin nhạy cảm có thể bị cache ở chỗ không phù hợp.
- `X-Request-Id` không được trả về, làm khó đối chiếu request với log.
- API bổ sung field `internalToken` hoặc `passwordHash` không được phép công khai.

Ngược lại, chỉ kiểm body mà bỏ status cũng sai: API có thể trả JSON chứa giá trị đúng nhưng status `500` hoặc `206` không phù hợp. **Hợp đồng gồm các lớp dữ liệu độc lập; cần assertion ở từng lớp được yêu cầu.**

Bảng phân loại:

| Lớp contract | Câu hỏi | Công cụ assertion điển hình |
|---|---|---|
| Request | Method/path/query/header/body đúng không? | Test gửi request cụ thể, verify domain effect khi cần |
| Status | Kết quả thành công hay thất bại theo quy tắc? | `getStatusCode().value()` |
| Representation | Trả JSON đúng media type và structure? | `Content-Type` + Jackson `JsonNode` |
| Header | Cache, location, correlation, retry, cookie đúng? | `getHeaders()` |
| Error | Mã lỗi public, thông điệp, path và không lộ bí mật đúng? | Assert JSON error + status |
| State/side effect | Có lưu dữ liệu, phát event, charge tiền, rollback không? | DB/repository/test double/adapter test tùy phạm vi |
| Transport/runtime | Socket, embedded server, serialization thực có hoạt động? | `RANDOM_PORT` và HTTP client |

## 3. Viết HTTP contract trước khi viết test

Đừng bắt đầu bằng một chuỗi `andExpect(...)` rồi đoán nên assert gì. Hãy mô tả kết quả quan sát được ở cấp endpoint.

Trong bài này, ta có một API báo giá:

| Kịch bản | Request | Status | Header/body quan trọng |
|---|---|---|---|
| Báo giá hợp lệ | `GET /api/quotes/BOOK?quantity=2&member=true` | 200 | JSON số tiền đúng; `Cache-Control: no-store`; echo `X-Request-Id` |
| Dùng giá trị mặc định | `GET /api/quotes/BOOK` | 200 | `quantity=1`, `member=false`, tổng tiền 120000 |
| JSON input hợp lệ | `POST /api/quotes` + JSON body | 200 | Trả phép tính theo input; không tuyên bố đã tạo resource |
| SKU không biết | `GET /api/quotes/MISSING` | 404 | JSON lỗi `SKU_NOT_FOUND`, message công khai |
| Số lượng không hợp lệ | `GET ...?quantity=0` | 400 | JSON lỗi `INVALID_ARGUMENT` |
| Query sai kiểu | `GET ...?quantity=abc` | 400 | JSON lỗi `INVALID_PARAMETER` |
| JSON syntax lỗi | `POST /api/quotes` + body sai | 400 | JSON lỗi `MALFORMED_JSON` |
| Sai Content-Type | `POST /api/quotes` với `text/plain` | 415 | JSON lỗi `UNSUPPORTED_MEDIA_TYPE` |

Quy ước trong ví dụ: vì `POST /api/quotes` chỉ **tính toán và trả một báo giá**, không persist tài nguyên mới, nó trả `200 OK`. **Không đặt `201 Created` chỉ vì HTTP method là POST**. Nếu một endpoint thật tạo đơn hàng/tài nguyên, `201` và `Location` mới thường phù hợp.

Một ma trận test nên có cả **đường đi thành công, validation lỗi, not found và lỗi hạ tầng quan trọng**. Số case phụ thuộc rủi ro hệ thống; không cần làm tất cả status code cho một API không có những nhánh ấy.

## 4. HTTP integration test có nhiều độ sâu

Trong Spring Boot, các test web có những ranh giới khác nhau:

| Hình thức | Context | HTTP server TCP thật? | Thường phù hợp để |
|---|---|---|---|
| JUnit unit test controller với mock collaborator | Không cần Spring | Không | Logic điều phối controller nếu rất nhỏ |
| `@WebMvcTest(Controller.class)` + `MockMvc` | MVC slice | Không | Mapping, argument binding, JSON, advice/filter thuộc slice |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Full Boot context | Không | Wiring, nhiều bean thật, MVC chain không qua socket |
| `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate` | Full Boot context | **Có** | HTTP request/response qua embedded server và nhiều bean thật |
| `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` | Full Boot context | **Có** | Fluent HTTP assertions, đặc biệt hữu ích khi có webflux test dependency |
| Staging/system E2E | Server/infra ngoài test JVM | Có, qua mạng tương ứng | Gateway, TLS, auth provider, DB/broker thật theo môi trường |

**`RANDOM_PORT` không tự biến thành E2E toàn bộ hệ sinh thái**. Nếu service dùng fake repository, mock payment gateway hoặc local cache, HTTP integration test chỉ bảo vệ đường đã chạy trên các collaborator ấy. Muốn chứng minh query DB, migration, retry hoặc broker thật, cần test adapter/integration tương ứng.

### 4.1. Vì sao chọn `TestRestTemplate` cho ví dụ?

Spring Boot 3.5 cung cấp `TestRestTemplate` khi dùng `@SpringBootTest` có embedded server; nó được auto-configure để gọi đúng cổng ngẫu nhiên và có đặc tính **không tự ném exception cho HTTP 4xx/5xx** như một `RestTemplate` mặc định. Test có thể nhận nguyên `ResponseEntity`, kiểm status, header và body lỗi.

`TestRestTemplate` không phải là `RestTemplate` subclass. Với test khác, bạn cũng có thể dùng `WebTestClient` hoặc HTTP client của dự án, miễn **biết nó đang gọi server thật hay mock environment**.

### 4.2. Vì sao không dùng `DEFINED_PORT`?

`DEFINED_PORT` mở cổng do cấu hình chọn, dễ đụng ứng dụng khác trên developer machine hoặc CI. `RANDOM_PORT` chọn cổng khả dụng cho mỗi application context và thường là lựa chọn an toàn hơn. Nếu ứng dụng có management port tách riêng, hãy kiểm cả cổng management khi mục tiêu liên quan tới actuator; không suy ra rằng test client gọi application port sẽ kiểm luôn management endpoint.

## 5. Khái niệm status: đừng coi mọi lỗi là 500

Nhóm status có ý nghĩa:

| Status | Ý nghĩa tiêu biểu | Assertion nên quan tâm |
|---|---|---|
| 200 OK | Request xử lý thành công và trả representation | Body đúng, Content-Type đúng |
| 201 Created | Đã tạo resource mới | `Location` chỉ resource mới nếu contract quy định |
| 202 Accepted | Đã nhận việc bất đồng bộ, chưa khẳng định hoàn tất | Job ID/status URL hoặc thông tin theo dõi |
| 204 No Content | Thành công, **không có response body** | Status và body rỗng |
| 304 Not Modified | Conditional request không cần trả representation | `ETag`/Last-Modified theo conditional caching, không body |
| 400 Bad Request | Input không hợp lệ hoặc không parse được | Error code/message công khai |
| 401 Unauthorized | Chưa xác thực hợp lệ | Auth challenge/header tùy scheme |
| 403 Forbidden | Đã xác thực nhưng không được phép, hoặc policy từ chối | Không lộ tài nguyên/permission nhạy cảm |
| 404 Not Found | Resource không tồn tại hoặc bị che theo policy | Error shape nhất quán nếu có body |
| 405 Method Not Allowed | Method không hỗ trợ trên resource | `Allow` header phù hợp |
| 409 Conflict | Xung đột trạng thái hay version | Conflict code/ETag/version khi cần |
| 415 Unsupported Media Type | Request body Content-Type không được hỗ trợ | Client biết cách sửa request |
| 422 Unprocessable Content | Cú pháp hợp lệ nhưng dữ liệu không xử lý được theo contract chọn | Error details có cấu trúc |
| 429 Too Many Requests | Bị giới hạn request | `Retry-After` hoặc rate-limit headers nếu contract có |
| 500 Internal Server Error | Lỗi bất ngờ ở server | Payload generic, không lộ internals |
| 503 Service Unavailable | Hệ thống/dep tạm không phục vụ | `Retry-After` khi có ý nghĩa, không ngụy trang thành 200 |

**Status chính xác thuộc hợp đồng API.** Một domain có thể chọn 400 cho validation, domain khác dùng 422; quan trọng là nhất quán, được tài liệu hóa và client xử lý được. Với `401`/`403`, hành vi thực còn phụ thuộc security chain, authentication scheme và chính sách tránh resource enumeration.

### 5.1. 204, 304 và body

- `204 No Content`: response thành công **không mang body**; test không nên ép JSONPath trên body rỗng.
- `304 Not Modified`: phản hồi conditional request **không chứa representation body**, nhưng metadata caching quan trọng.
- `HEAD`: về mặt ngữ nghĩa trả headers tương đương GET tương ứng nhưng không trả response content; test có thể kiểm headers và body rỗng.

Nếu test chỉ đòi “bất kỳ 2xx nào”, nó có thể bỏ qua việc API vô tình đổi từ 200 có JSON sang 204 rỗng. Hãy assert chính xác status khi client contract yêu cầu.

## 6. HTTP headers là dữ liệu contract, không phải trang trí

Headers có ý nghĩa riêng:

| Header | Request hay response | Cần kiểm điều gì? |
|---|---|---|
| `Content-Type` | Cả hai | Kiểu representation; response JSON đúng media type |
| `Accept` | Request | Kiểu representation client mong muốn; có thể dẫn tới 406 |
| `Location` | Response | URI của resource mới sau 201/redirect khi contract quy định |
| `Cache-Control` | Response | `no-store`/`private`/`max-age` đúng dữ liệu và policy |
| `ETag` / `If-None-Match` | Response / Request | Conditional caching hoặc concurrency; 304/412 nếu dùng |
| `X-Request-Id` hoặc `traceparent` | Cả hai theo quy ước | Correlation có mặt, hợp lệ và được forward nếu contract |
| `Authorization` | Request | Chỉ kiểm ở test security phù hợp; không log token |
| `WWW-Authenticate` | Response | Challenge khi 401 theo scheme thực tế |
| `Retry-After` | Response | Thời điểm/delay retry cho 429/503 nếu cung cấp |
| `Set-Cookie` / `Cookie` | Response / Request | Thuộc tính HttpOnly, Secure, SameSite, domain/path khi liên quan |
| `Vary` | Response | Cache variant theo Accept-Encoding/Origin hoặc header phù hợp |
| `Allow` | Response | Các method khả dụng khi 405 |
| `Content-Disposition` | Response | Download filename/type khi xuất file |

**Header names không phân biệt chữ hoa/thường theo HTTP.** Tránh assertion yêu cầu phải chính xác kiểu viết `Content-Type` thay vì `content-type` trong raw bytes. Dùng `HttpHeaders` của Spring để lấy value.

Đối với `Content-Type`, câu hỏi thường là **tính tương thích media type**: `application/json;charset=UTF-8` và `application/json` cùng thuộc JSON family. So string tuyệt đối có thể giòn. Dùng:

```java
// Snippet dùng trong JUnit test đã có ResponseEntity<String> response.
MediaType actual = response.getHeaders().getContentType();
assertNotNull(actual);
assertTrue(MediaType.APPLICATION_JSON.isCompatibleWith(actual));
```

Nếu contract bắt buộc versioned media type như `application/vnd.company.v1+json`, hãy kiểm rõ version và parameter quan trọng; đừng dùng matcher quá rộng.

### 6.1. Cache-Control: tại sao `no-store` khác `no-cache`?

`no-store` yêu cầu cache không lưu response/request theo semantics cache; `no-cache` **không có nghĩa “không được lưu”** mà yêu cầu tái xác thực trước khi dùng lại response. Đối với dữ liệu nhạy cảm, chọn policy theo threat model và HTTP caching semantics; một test nên assert directive thực sự yêu cầu, không chỉ assert “có header”.

Ví dụ Spring MVC:

```java
ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(quote);
```

Đây là snippet; `quote` chưa khai báo. Test có thể kiểm `response.getHeaders().getCacheControl().contains("no-store")`. Không dùng `Thread.sleep` hoặc kiểm thời gian cache bằng suy đoán để chứng minh policy; header contract và cache integration là hai cấp khác nhau.

### 6.2. Correlation ID có giúp test an toàn không?

Một hệ thống có thể nhận `X-Request-Id` và trả lại để correlation. Tuy nhiên **không được xem header do client gửi là trusted identity**. Trong production, cần validate độ dài/ký tự, có thể tự tạo ID và chuẩn hóa logging để tránh log injection hoặc thông tin giả. Ví dụ này chỉ echo một ID ASCII cố định nhằm hướng dẫn assertion; không minh họa một hệ thống tracing hoàn chỉnh.

## 7. Kiểm JSON: hình dạng, kiểu và ý nghĩa

Giả sử body:

```json
{
  "sku": "BOOK",
  "quantity": 2,
  "subtotalVnd": 240000,
  "discountVnd": 24000,
  "totalVnd": 216000
}
```

Các câu hỏi kiểm chứng:

1. Body có phải JSON hợp lệ, không phải HTML fallback?
2. Root là object hay array?
3. Field trọng tâm có tồn tại và đúng **kiểu** không?
4. Giá trị đúng không, đặc biệt với số tiền và status?
5. Có field nhạy cảm, data debug, secret hoặc stack trace nào không?
6. Mảng có phần tử đúng và thứ tự đúng theo contract không?
7. Nếu field tùy chọn, nó **vắng mặt, explicit null hay rỗng** theo quy ước?

### 7.1. Jackson `JsonNode` cho HTTP integration test

Một cách đơn giản:

```java
JsonNode root = objectMapper.readTree(response.getBody());

assertTrue(root.isObject());
assertEquals("BOOK", root.required("sku").asText());
assertEquals(2, root.required("quantity").intValue());
assertEquals(216_000L, root.required("totalVnd").longValue());
assertFalse(root.has("internalToken"));
```

Đây là snippet: biến `objectMapper`/`response` và JUnit imports sẽ được định nghĩa ở test hoàn chỉnh phần 14. `JsonNode.required("field")` giúp fail khi field thiếu; tuy nhiên nó không luôn thay được kiểm type. Khi contract quan trọng, kết hợp `isTextual()`, `isIntegralNumber()` hoặc `isArray()`.

### 7.2. JSON numbers không phải Java types

JSON có một dạng number, còn Jackson có thể biểu diễn thành `Integer`, `Long`, `BigDecimal` hoặc kiểu khác. Với số tiền của ví dụ, ta dùng **số nguyên VND (long)**, không dùng double để tránh sai số nhị phân.

Đừng viết assert `json string` bằng một chuỗi có khoảng trắng cố định khi chỉ cần semantic equality. Field order trong object JSON thường không là hợp đồng; phần tử array **có thứ tự** và cần kiểm khi API quy định.

### 7.3. Missing, null, empty không giống nhau

```json
{
  "note": null,
  "displayName": "",
  "items": []
}
```

- `note` tồn tại với giá trị `null`.
- `displayName` tồn tại với chuỗi rỗng.
- `items` tồn tại với array rỗng.
- `internalTrace` không xuất hiện.

Với Jackson:

```java
assertTrue(root.has("note"));
assertTrue(root.get("note").isNull());
assertEquals("", root.required("displayName").asText());
assertTrue(root.required("items").isArray());
assertEquals(0, root.required("items").size());
assertFalse(root.has("internalTrace"));
```

Đây là snippet minh họa. Đừng dùng riêng `root.path("note").asText()` để suy luận null vs missing: `path` trả một node đại diện cho missing, và việc chuyển về text có thể che khác biệt.

### 7.4. JSONPath và JSONassert

Trong `MockMvc`, có thể viết:

```java
mockMvc.perform(get("/api/quotes/BOOK")
                .param("quantity", "2")
                .param("member", "true"))
        .andExpectAll(
                status().isOk(),
                header().string("Cache-Control", "no-store"),
                jsonPath("$.sku").value("BOOK"),
                jsonPath("$.totalVnd").value(216_000));
```

Đây là snippet chỉ hợp lệ bên trong một test có `mockMvc` và static imports. Cùng một hợp đồng có thể được xác minh bằng `TestRestTemplate` + Jackson khi dùng real server. `content().json(expected, JsonCompareMode.STRICT)` so sánh cấu trúc chặt chẽ hơn; `LENIENT` cho phép một số khác biệt như extra fields. Chọn mức chặt tùy contract và rủi ro dữ liệu lộ.

**Lưu ý:** đừng trộn các API matcher của `MockMvc` vào `TestRestTemplate`; `TestRestTemplate` trả `ResponseEntity`, không có `andExpect(...)`. Hai client có cách viết assertion khác nhau.

## 8. Error contract: thông báo lỗi phải dành cho client

Lỗi HTTP không nên chỉ là text do exception `toString()` sinh ra. Một error DTO ổn định giúp client hiểu được **loại lỗi**, cung cấp thông điệp công khai và giữ internal details trong server log được bảo vệ.

Ví dụ:

```json
{
  "code": "INVALID_ARGUMENT",
  "message": "quantity must be positive",
  "path": "/api/quotes/BOOK"
}
```

Trong ví dụ này:

- `code` là **machine-readable code** ổn định cho client.
- `message` là thông điệp có thể hiển thị/ghi nhận ở mức phù hợp; không chứa stack trace, SQL query hoặc credential.
- `path` giúp xác định endpoint gây lỗi; không nên sao chép thông tin nhạy cảm từ query/body vào error.
- HTTP status phải đúng với loại lỗi; không trả `200` rồi nhét `success:false` nếu contract dùng HTTP semantics chuẩn.
- `Content-Type` phải phù hợp với JSON body.
- `Cache-Control` và correlation header vẫn nên được kiểm trên error response khi policy yêu cầu.

**Vì sao tránh assert toàn bộ exception message?** Message nội bộ của Spring/Jackson có thể chứa tên class, vị trí parse, giá trị input và thay đổi khi nâng version. Public error message nên do ứng dụng định nghĩa, **không trả thẳng `ex.getMessage()` của parse exception** nếu nó có thể lộ internals.

### 8.1. Problem Details là lựa chọn khác

Spring Framework hỗ trợ `ProblemDetail` theo chuẩn Problem Details for HTTP APIs (RFC 9457). Một API có thể trả:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "quantity must be positive"
}
```

`application/problem+json` là media type dành cho Problem Details. Một API dùng `ProblemDetail` không nên bị test sai bằng cách ép mọi error phải có `application/json` hoặc field `code` của ví dụ custom. Chọn **một error contract rõ ràng** phù hợp dự án, rồi kiểm nó nhất quán.

Nếu hỗ trợ localization, public `message` có thể khác theo `Accept-Language`. Khi đó có thể assert code ổn định và những message quan trọng theo từng locale đã được quy định, thay vì assert tùy tiện một chuỗi mặc định.

## 9. Validation và ba lớp lỗi khác nhau

Cần phân biệt:

1. **Binding/format lỗi:** JSON malformed, tham số query không đổi được sang int, media type không được hỗ trợ. Spring MVC có thể phát exception **trước khi vào controller method**.
2. **Domain validation lỗi:** quantity không dương, SKU rỗng, nghiệp vụ từ chối hành động. Controller/service thật ném lỗi thuộc domain.
3. **State/conflict/infrastructure lỗi:** resource đã thay đổi version, gateway tạm không sẵn sàng, DB lỗi. Chúng thường cần status riêng như 409, 503 hoặc generic 500; không nên ngụy trang tất cả thành 400.

Vì vậy, một `@ExceptionHandler(IllegalArgumentException.class)` **không tự bao phủ** `HttpMessageNotReadableException` hay `HttpMediaTypeNotSupportedException`. Muốn đảm bảo error JSON đồng nhất, cần handler rõ cho những lỗi framework mà API muốn chuẩn hóa, hoặc dùng một cách tích hợp `ResponseEntityExceptionHandler`/`ProblemDetail` có chủ đích.

Tránh global handler bắt `Exception.class` rồi luôn trả `400`: nó che bug server, làm metric sai, có thể biến security exception thành lỗi input và khiến client hành động không đúng.

## 10. Status và thông điệp lỗi: kiểm điều gì để không giòn?

Đối với một case 404:

```http
HTTP/1.1 404 Not Found
Content-Type: application/json
Cache-Control: no-store
X-Request-Id: req-404

{
  "code": "SKU_NOT_FOUND",
  "message": "Unknown SKU: MISSING",
  "path": "/api/quotes/MISSING"
}
```

Các assertion phù hợp:

- Status **chính xác `404`**.
- `Content-Type` tương thích `application/json`.
- `Cache-Control` chứa `no-store` nếu đó là policy của API.
- `X-Request-Id` khớp request ID theo thiết kế demo.
- JSON có `code` bằng `SKU_NOT_FOUND`.
- `message` là thông điệp công khai đã định nghĩa; test quan trọng có thể assert đúng string.
- `path` là đường dẫn, không tự chứa query sensitive hoặc secret.
- Không có `stackTrace`, `exception`, `sql` hoặc `debugToken`.
- Không có tác dụng phụ ngoài ý muốn (nếu endpoint có hạ tầng thật, kiểm ở test thích hợp).

Đừng assert **thứ tự JSON keys**, số lượng khoảng trắng hoặc casing của tên header khi contract không đòi điều đó. Nếu `message` được phép thay đổi copywriting, giữ `code` làm contract máy và kiểm tính chất message (không rỗng, không chứa sensitive details) ở cấp phù hợp.

## 11. Mô hình ví dụ runnable: báo giá không dùng tài nguyên ngoài

Để tập trung vào hợp đồng HTTP, ứng dụng có:

- Product `BOOK` giá 120.000 VND và `PEN` giá 20.000 VND.
- Hội viên giảm 10% tạm tính, phép chia nguyên làm tròn xuống.
- Quantity phải lớn hơn 0.
- SKU lạ trả 404, quantity sai trả 400.
- `GET` dùng query params; `POST` nhận JSON body, cả hai chỉ trả báo giá, không persist.
- Response 200 chứa `Cache-Control: no-store` và `X-Request-Id`.
- Error body ổn định qua `@RestControllerAdvice` cho domain error, malformed JSON, sai query type và unsupported Content-Type.
- JUnit integration test gọi server thật qua `TestRestTemplate`.

Tất cả component chạy thật trong ví dụ: Spring MVC controller, service tính tiền, HTTP message converter, global advice. **Không mock `QuoteService`** vì bài học cần chứng minh cả contract HTTP và phép tính dữ liệu mẫu. Không có DB, payment, broker hoặc external network nên test không gây side effect ngoài localhost.

### 11.1. Cây thư mục

```text
src/main/java/com/example/httpcontract/
    HttpContractApplication.java
    QuoteCommand.java
    QuoteView.java
    ApiError.java
    QuoteNotFoundException.java
    QuoteService.java
    QuoteController.java
    QuoteExceptionAdvice.java

src/test/java/com/example/httpcontract/
    QuoteHttpContractIntegrationTest.java
    QuoteMockMvcIntegrationTest.java
```

Tất cả file Java khai báo `package com.example.httpcontract;`. Project dùng Java 17+ và Spring Boot 3.5.x với `spring-boot-starter-web` / `spring-boot-starter-test`. Không thêm `spring-boot-starter-webflux` chỉ để chạy ví dụ này.

## 12. Application, DTO và exception

**`src/main/java/com/example/httpcontract/HttpContractApplication.java`**

```java
package com.example.httpcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpContractApplication.class, args);
    }
}
```

**`src/main/java/com/example/httpcontract/QuoteCommand.java`**

```java
package com.example.httpcontract;

public record QuoteCommand(
        String sku,
        int quantity,
        boolean member) {
}
```

**`src/main/java/com/example/httpcontract/QuoteView.java`**

```java
package com.example.httpcontract;

public record QuoteView(
        String sku,
        int quantity,
        long subtotalVnd,
        long discountVnd,
        long totalVnd) {
}
```

**`src/main/java/com/example/httpcontract/ApiError.java`**

```java
package com.example.httpcontract;

public record ApiError(
        String code,
        String message,
        String path) {
}
```

**`src/main/java/com/example/httpcontract/QuoteNotFoundException.java`**

```java
package com.example.httpcontract;

public final class QuoteNotFoundException
        extends RuntimeException {

    public QuoteNotFoundException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

Các `record` là dữ liệu immutable đơn giản được Jackson serialize theo tên component. Nếu app thật sử dụng `@JsonProperty`, naming strategy, custom serializer hoặc API versioning, tên field trong test phải theo **contract public**, không theo assumption từ class name.

### 12.1. Không đưa entity JPA trực tiếp ra response

Trong hệ thống có DB, nên tách DTO response khỏi entity/persistence model để tránh expose internal identifiers/fields, lazy-loading exceptions và schema phụ thuộc implementation. Ví dụ dùng records chuyên dành cho API nhằm minh bạch dữ liệu có quyền xuất hiện trong JSON.

## 13. Service thật: tính toán và báo lỗi domain

**`src/main/java/com/example/httpcontract/QuoteService.java`**

```java
package com.example.httpcontract;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    public QuoteView quote(
            String sku, int quantity, boolean member) {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        long unitPrice = switch (sku) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 20_000L;
            default -> throw new QuoteNotFoundException(sku);
        };

        long subtotal = Math.multiplyExact(unitPrice, quantity);
        long discount = member ? subtotal / 10L : 0L;
        long total = Math.subtractExact(subtotal, discount);

        return new QuoteView(
                sku, quantity, subtotal, discount, total);
    }
}
```

Giải thích:

- Service kiểm input trước khi tính tiền.
- SKU lạ có **exception riêng** để map thành 404 thay vì biến thành generic 500.
- `quantity <= 0` thành 400 nhờ error advice.
- `Math.multiplyExact` phát hiện overflow thay vì âm thầm cuốn vòng; demo chưa định nghĩa một public error code riêng cho overflow. Với production, nên có giới hạn quantity và money type hợp lệ, đồng thời mapping overflow thành lỗi thích hợp.
- Không dùng `double` cho số tiền. Các con số trong bài dùng **VND nguyên** với quy tắc giảm giá làm tròn xuống đơn giản cho mục đích học tập.

Vì `QuoteService` chạy thật trong HTTP integration test, một lỗi giảm giá sẽ làm test JSON total đỏ. Nếu chỉ mock service để trả `QuoteView`, sẽ không có bảo đảm này.

## 14. Controller: status 200 và các header ổn định

**`src/main/java/com/example/httpcontract/QuoteController.java`**

```java
package com.example.httpcontract;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public ResponseEntity<QuoteView> get(
            @PathVariable String sku,
            @RequestParam(defaultValue = "1") int quantity,
            @RequestParam(defaultValue = "false") boolean member,
            @RequestHeader(
                    name = "X-Request-Id",
                    defaultValue = "unknown") String requestId) {

        return success(
                service.quote(sku, quantity, member), requestId);
    }

    @PostMapping
    public ResponseEntity<QuoteView> post(
            @RequestBody QuoteCommand command,
            @RequestHeader(
                    name = "X-Request-Id",
                    defaultValue = "unknown") String requestId) {

        return success(service.quote(
                command.sku(),
                command.quantity(),
                command.member()), requestId);
    }

    private static ResponseEntity<QuoteView> success(
            QuoteView view, String requestId) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header("X-Request-Id", requestId)
                .body(view);
    }
}
```

**Các lựa chọn có chủ đích:**

- `GET /api/quotes/BOOK` mặc định `quantity=1`, `member=false`.
- `POST /api/quotes` nhận JSON qua `@RequestBody`; không tạo/persist resource, nên **200** là đúng thiết kế demo.
- Cả hai trả `Cache-Control: no-store` và một header correlation minh họa.
- `ResponseEntity<QuoteView>` để Spring MVC chọn HTTP message converter (Jackson) trả JSON.
- Không cố đặt `Content-Type` bằng chuỗi raw nếu converter đã tạo JSON đúng; error handler sẽ đặt rõ media type.
- Demo không validate `X-Request-Id` từ client; production cần quy tắc tin cậy riêng cho tracing ID.

**Không trộn business logic vào controller:** phép giảm giá nằm trong service. Controller thực hiện HTTP binding, ủy quyền và cấu trúc response.

## 15. Error advice: 400, 404, 415 và JSON công khai

**`src/main/java/com/example/httpcontract/QuoteExceptionAdvice.java`**

```java
package com.example.httpcontract;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class QuoteExceptionAdvice {

    @ExceptionHandler(QuoteNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            QuoteNotFoundException failure,
            HttpServletRequest request) {

        return error(HttpStatus.NOT_FOUND,
                "SKU_NOT_FOUND", failure.getMessage(), request);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> invalidArgument(
            IllegalArgumentException failure,
            HttpServletRequest request) {

        return error(HttpStatus.BAD_REQUEST,
                "INVALID_ARGUMENT", failure.getMessage(), request);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> invalidParameter(
            MethodArgumentTypeMismatchException failure,
            HttpServletRequest request) {

        return error(HttpStatus.BAD_REQUEST,
                "INVALID_PARAMETER",
                "Query parameter has invalid type", request);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> malformedJson(
            HttpMessageNotReadableException failure,
            HttpServletRequest request) {

        return error(HttpStatus.BAD_REQUEST,
                "MALFORMED_JSON",
                "Request body is not valid JSON", request);
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiError> unsupportedType(
            HttpMediaTypeNotSupportedException failure,
            HttpServletRequest request) {

        return error(HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED_MEDIA_TYPE",
                "Request Content-Type is not supported", request);
    }

    private static ResponseEntity<ApiError> error(
            HttpStatus status,
            String code,
            String message,
            HttpServletRequest request) {

        String requestId = request.getHeader("X-Request-Id");
        if (requestId == null || requestId.isBlank()) {
            requestId = "unknown";
        }

        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_JSON)
                .cacheControl(CacheControl.noStore())
                .header("X-Request-Id", requestId)
                .body(new ApiError(
                        code, message, request.getRequestURI()));
    }
}
```

### 15.1. Vì sao có nhiều handler?

- `QuoteNotFoundException` đến từ nghiệp vụ khi SKU không tồn tại → 404.
- `IllegalArgumentException` đến từ validation đơn giản trong service → 400.
- `MethodArgumentTypeMismatchException` có thể xảy ra **trước khi service được gọi** khi query `quantity=abc` không parse được sang int → 400.
- `HttpMessageNotReadableException` có thể xuất hiện khi body JSON sai cú pháp hoặc không đọc được thành record → 400.
- `HttpMediaTypeNotSupportedException` xuất hiện khi POST có request body với media type không hỗ trợ, ví dụ `text/plain` thay vì JSON → 415.

**Không công khai message của parsing exception**; ta trả chuỗi ổn định `"Request body is not valid JSON"`. Một malformed payload có thể chứa dữ liệu nhạy cảm, nên log/error public không nên echo nguyên payload.

### 15.2. Giới hạn của advice

Đây là ví dụ tối giản, không triển khai mọi nhánh framework error. Ví dụ:

- Security 401/403 có thể được tạo **trước controller** bởi Spring Security filter chain.
- JSON trả về cho 406, 405 hoặc một số validation exception có thể do default framework handling.
- Server 500 bất ngờ thường nên dùng error response generic, nhưng không nên bắt bừa `Exception.class` rồi đổi thành 400.
- Runtime production cần logging/trace ID chuẩn, localization, policy ẩn internal details và loại bỏ dữ liệu nhạy cảm trong log.
- Với Spring Framework 6.x, có thể chuẩn hóa bằng `ProblemDetail` hoặc `ResponseEntityExceptionHandler`; chọn một schema nhất quán ở cấp API.

Ví dụ này **cố ý không có backend fail hoặc security dependency**; không giả vờ đã kiểm các trường hợp ấy.

## 16. Real HTTP integration test bằng `TestRestTemplate`

Đây là bài test trung tâm. Nó gọi **embedded server thật** trên cổng ngẫu nhiên, không mock service. Assertions kiểm status, header, JSON và thông báo lỗi có tính ổn định.

**`src/test/java/com/example/httpcontract/QuoteHttpContractIntegrationTest.java`**

```java
package com.example.httpcontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = HttpContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QuoteHttpContractIntegrationTest {

    @LocalServerPort
    int serverPort;

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ObjectMapper mapper;

    private ResponseEntity<String> get(
            String url, String requestId) {

        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Request-Id", requestId);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        return rest.exchange(url, HttpMethod.GET,
                new HttpEntity<Void>(headers), String.class);
    }

    private JsonNode body(ResponseEntity<String> response)
            throws Exception {
        assertNotNull(response.getBody());
        return mapper.readTree(response.getBody());
    }

    private void assertJsonHeaders(
            ResponseEntity<String> response, String requestId) {

        MediaType type = response.getHeaders().getContentType();

        assertAll("HTTP representation headers",
                () -> assertNotNull(type),
                () -> assertTrue(type != null
                        && MediaType.APPLICATION_JSON.isCompatibleWith(type)),
                () -> assertTrue(response.getHeaders()
                        .getCacheControl().contains("no-store")),
                () -> assertEquals(requestId,
                        response.getHeaders()
                                .getFirst("X-Request-Id")));
    }

    @Test
    void getReturns200HeadersAndCorrectJson() throws Exception {
        ResponseEntity<String> response = get(
                "/api/quotes/BOOK?quantity=2&member=true",
                "req-get-1");
        JsonNode json = body(response);

        assertAll("GET quote contract",
                () -> assertTrue(serverPort > 0),
                () -> assertEquals(200,
                        response.getStatusCode().value()),
                () -> assertEquals("BOOK",
                        json.required("sku").asText()),
                () -> assertEquals(2,
                        json.required("quantity").intValue()),
                () -> assertEquals(240_000L,
                        json.required("subtotalVnd").longValue()),
                () -> assertEquals(24_000L,
                        json.required("discountVnd").longValue()),
                () -> assertEquals(216_000L,
                        json.required("totalVnd").longValue()),
                () -> assertTrue(
                        json.required("totalVnd").isIntegralNumber()),
                () -> assertFalse(json.has("internalToken")));

        assertJsonHeaders(response, "req-get-1");
    }

    @Test
    void defaultQueryParametersAreApplied() throws Exception {
        ResponseEntity<String> response =
                get("/api/quotes/BOOK", "req-default-1");

        assertEquals(200, response.getStatusCode().value());
        JsonNode json = body(response);
        assertEquals(1, json.required("quantity").intValue());
        assertEquals(120_000L,
                json.required("subtotalVnd").longValue());
        assertEquals(0L,
                json.required("discountVnd").longValue());
        assertEquals(120_000L,
                json.required("totalVnd").longValue());
        assertJsonHeaders(response, "req-default-1");
    }

    @Test
    void postParsesJsonRequestAndReturns200() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        headers.set("X-Request-Id", "req-post-1");

        QuoteCommand command =
                new QuoteCommand("PEN", 3, true);
        HttpEntity<QuoteCommand> request =
                new HttpEntity<>(command, headers);

        ResponseEntity<String> response =
                rest.exchange("/api/quotes",
                        HttpMethod.POST, request, String.class);

        assertEquals(200, response.getStatusCode().value());
        JsonNode json = body(response);

        assertAll("POST body binding and quote",
                () -> assertEquals("PEN",
                        json.required("sku").asText()),
                () -> assertEquals(3,
                        json.required("quantity").intValue()),
                () -> assertEquals(60_000L,
                        json.required("subtotalVnd").longValue()),
                () -> assertEquals(6_000L,
                        json.required("discountVnd").longValue()),
                () -> assertEquals(54_000L,
                        json.required("totalVnd").longValue()));

        assertJsonHeaders(response, "req-post-1");
    }

    @Test
    void unknownSkuReturns404WithSafePublicError()
            throws Exception {

        ResponseEntity<String> response =
                get("/api/quotes/MISSING", "req-not-found");
        JsonNode json = body(response);

        assertEquals(404, response.getStatusCode().value());
        assertEquals("SKU_NOT_FOUND",
                json.required("code").asText());
        assertEquals("Unknown SKU: MISSING",
                json.required("message").asText());
        assertEquals("/api/quotes/MISSING",
                json.required("path").asText());
        assertFalse(json.has("stackTrace"));
        assertFalse(json.has("exception"));
        assertFalse(json.has("sql"));

        assertJsonHeaders(response, "req-not-found");
    }

    @Test
    void invalidQuantityReturns400Not500() throws Exception {
        ResponseEntity<String> response =
                get("/api/quotes/BOOK?quantity=0",
                        "req-invalid-quantity");

        assertEquals(400, response.getStatusCode().value());
        JsonNode json = body(response);

        assertEquals("INVALID_ARGUMENT",
                json.required("code").asText());
        assertEquals("quantity must be positive",
                json.required("message").asText());

        assertJsonHeaders(response, "req-invalid-quantity");
    }

    @Test
    void wrongQueryTypeReturnsStable400() throws Exception {
        ResponseEntity<String> response =
                get("/api/quotes/BOOK?quantity=abc",
                        "req-invalid-type");

        assertEquals(400, response.getStatusCode().value());
        JsonNode json = body(response);

        assertEquals("INVALID_PARAMETER",
                json.required("code").asText());
        assertEquals("Query parameter has invalid type",
                json.required("message").asText());
        assertFalse(json.has("stackTrace"));

        assertJsonHeaders(response, "req-invalid-type");
    }

    @Test
    void malformedJsonBodyReturnsSafe400() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Request-Id", "req-bad-json");

        HttpEntity<String> request =
                new HttpEntity<>("{not-json}", headers);

        ResponseEntity<String> response =
                rest.exchange("/api/quotes", HttpMethod.POST,
                        request, String.class);

        assertEquals(400, response.getStatusCode().value());
        JsonNode json = body(response);

        assertEquals("MALFORMED_JSON",
                json.required("code").asText());
        assertEquals("Request body is not valid JSON",
                json.required("message").asText());
        assertFalse(json.has("exception"));
        assertFalse(json.has("stackTrace"));

        assertJsonHeaders(response, "req-bad-json");
    }

    @Test
    void unsupportedContentTypeReturns415() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.TEXT_PLAIN);
        headers.set("X-Request-Id", "req-bad-media");

        HttpEntity<String> request =
                new HttpEntity<>("sku=BOOK", headers);

        ResponseEntity<String> response =
                rest.exchange("/api/quotes", HttpMethod.POST,
                        request, String.class);

        assertEquals(415, response.getStatusCode().value());
        JsonNode json = body(response);

        assertEquals("UNSUPPORTED_MEDIA_TYPE",
                json.required("code").asText());
        assertEquals("Request Content-Type is not supported",
                json.required("message").asText());

        assertJsonHeaders(response, "req-bad-media");
    }
}
```

### 16.1. Tại sao `HttpEntity` và `ResponseEntity` quan trọng?

`HttpEntity` mang **request body và request headers**. `ResponseEntity` cung cấp đồng thời status, headers và body. Test có thể kiểm:

- Method/path/query/request body đã đi qua HTTP server thật.
- Jackson deserialize JSON vào `QuoteCommand`.
- Service tính toán đúng số tiền và Spring MVC serialize `QuoteView`.
- Exception advice tạo status và error body đã định nghĩa.
- Header response có giá trị đúng.

`TestRestTemplate` không coi 4xx/5xx là một exception ở client theo mặc định: nó cho phép đọc `response.getStatusCode()` và `response.getBody()` để kiểm chính xác negative contract.

### 16.2. Tại sao đọc JSON bằng Jackson thay vì so cả chuỗi?

Response có thể thay whitespace hoặc field order mà không đổi semantics. `JsonNode` giúp kiểm giá trị theo key. Dùng `required` cho field bắt buộc và `has`/`hasNonNull` để phân biệt các loại presence.

Ví dụ test kiểm `totalVnd=216000` như một số nguyên, nhưng không đòi JSON được in cùng indent với ví dụ tài liệu. Đó là assertion **ít giòn** mà vẫn bắt bug nghiệp vụ.

### 16.3. Lưu ý về `assertJsonHeaders`

Helper này chỉ dùng cho response có **JSON body** và contract yêu cầu `no-store` + correlation ID. Không gọi helper cho `204 No Content` hoặc những endpoint trả file; mỗi representation có header policy riêng.

### 16.4. Không dùng HTTP test để dựa vào test order

Các method trên không sửa database, không dùng counter singleton và không phụ thuộc nhau. Khi có resource creation thật, tránh một test tạo resource `41` rồi test khác giả định resource đó đã tồn tại chỉ vì tên test được sắp xếp. Hãy tạo fixture độc lập hoặc setup/teardown phù hợp.

## 17. Full Boot context dùng `MockMvc`: rẻ hơn network thật

Nếu muốn chạy controller, service và advice thật nhưng không cần mở TCP port, có thể dùng `@SpringBootTest` với mock web environment và `@AutoConfigureMockMvc`.

**`src/test/java/com/example/httpcontract/QuoteMockMvcIntegrationTest.java`**

```java
package com.example.httpcontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = HttpContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class QuoteMockMvcIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void testsFullSpringContextWithoutSocket() throws Exception {
        mvc.perform(get("/api/quotes/BOOK")
                        .param("quantity", "2")
                        .param("member", "true")
                        .header("X-Request-Id", "req-mock"))
                .andExpectAll(
                        status().isOk(),
                        header().string("X-Request-Id", "req-mock"),
                        header().string("Cache-Control", "no-store"),
                        content().contentTypeCompatibleWith(
                                "application/json"),
                        jsonPath("$.sku").value("BOOK"),
                        jsonPath("$.totalVnd").value(216_000));
    }
}
```

Trong test này, **service thật vẫn chạy** vì ta nạp full Boot context và không mock `QuoteService`. `MockMvc` đi qua MVC pipeline nhưng **không kiểm socket/server runtime**. Đây là một điểm cân bằng tốt khi bộ test có nhiều trường hợp HTTP contract nhỏ mà transport thực không phải rủi ro cần kiểm mỗi lần.

**Khác với `@WebMvcTest`:** `@WebMvcTest` mặc định không scan `@Service`, nên thường cần `@MockitoBean` ở controller boundary; test xanh không bảo vệ service thật. Phân biệt rõ **slice vs full context** và **mock transport vs real server** — đó là hai trục độc lập.

## 18. Những nhánh cần bổ sung khi ứng dụng thật có state

Ví dụ không persist dữ liệu nên tránh làm bài phức tạp. Với API CRUD thực, cần thêm hợp đồng cho tạo/cập nhật/xóa.

### 18.1. POST tạo resource: `201` + `Location`

Response minh họa:

```http
HTTP/1.1 201 Created
Location: /api/orders/41
Content-Type: application/json

{"id":41,"status":"NEW"}
```

Controller khi tạo thành công thường có thể dùng:

```java
// Snippet: order là object đã thực sự được lưu.
URI location = URI.create("/api/orders/" + order.id());

return ResponseEntity.created(location).body(order);
```

Đây là **mã minh họa không độc lập**, khác với POST báo giá ở phần 14. Test cần assert status 201, `Location` và **GET lại resource vừa tạo được** nếu đó là hợp đồng read-after-write; không chỉ assert URI do test tự tạo.

### 18.2. PUT/PATCH và optimistic locking

Nếu API hỗ trợ `ETag` / `If-Match`, test nên có các case:

- Cập nhật với version hợp lệ thành công và trả ETag mới theo quy ước.
- Version cũ bị từ chối bằng `412 Precondition Failed` hoặc `409 Conflict` tùy contract.
- Không có `If-Match` khi endpoint yêu cầu precondition có thể thành `428 Precondition Required`.

Không đặt `ETag` vô nghĩa chỉ để có nhiều header assertion. Nó liên quan đến **điều kiện cập nhật, cache và concurrency semantics**.

### 18.3. DELETE thành công với `204`

`204` không có body; test đúng:

```java
// Snippet với MockMvc trong test DELETE đã cấu hình.
mvc.perform(delete("/api/orders/{id}", 41L))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Snippet cần static import và controller DELETE thật. Không ép JSON body vào 204 chỉ để “làm response đồng nhất”.

### 18.4. Pagination và sorting

Một endpoint `GET /api/orders?page=1&size=5` có thể phải trả JSON `items`, `total`, `page` và `size` cùng order. Nếu backend dùng DB nhưng test chỉ mock trả sẵn danh sách, nó không bảo vệ ORDER BY, count query hoặc page boundary; cần test service/repository thật khi yêu cầu.

## 19. Authorization, authentication và error privacy

Đối với API có Spring Security, status contract cần bao gồm:

- **401** khi chưa có authentication hoặc token không hợp lệ; có thể cần `WWW-Authenticate` header theo scheme.
- **403** khi principal không có quyền; không lộ vai trò/permission nội bộ ngoài contract.
- **404** có thể được dùng thay 403 để tránh xác nhận sự tồn tại của resource trong một số threat models.
- **429** khi rate-limit nếu policy có, với những header giới hạn/retry được định nghĩa.
- Session/cookie attributes hoặc CORS response headers khi client browser cần.

Một test controller dùng `@WithMockUser` có thể kiểm authorization trong mock environment nhưng **không tự chứng minh JWT signature, issuer, audience hay security filter tại deployment**. Cần test integration với Spring Security config và token fixture phù hợp.

**Không disable security globally chỉ để test trả 200.** Nếu ví dụ ở đây không thêm `spring-boot-starter-security`, các status 401/403 không thuộc chương trình runnable; chúng là yêu cầu mở rộng khi sản phẩm có authentication.

### 19.1. Kiểm thông báo lỗi không rò rỉ dữ liệu

Error JSON không nên chứa:

- Raw SQL query/connection string có credential.
- JVM stack trace hoặc tên class implementation nội bộ nếu không thuộc public contract.
- Full access token, refresh token, private keys, passwords.
- Raw body chứa thông tin riêng tư hoặc định danh nhạy cảm không cần thiết.
- Nội dung exception message đến từ thư viện bên thứ ba chưa được sanitize.

Các assertion `assertFalse(json.has("stackTrace"))` là một tầng bảo vệ, **không thay** threat modeling, security review và kiểm response của tất cả error handler. Error message cũng có thể rò rỉ trong field khác hoặc header khác; cần giới hạn response schema.

## 20. Content negotiation, charset và localization

Client gửi `Accept` để nói muốn representation nào; client gửi `Content-Type` để nói body request có loại nào.

| Tình huống | Ý nghĩa HTTP | Status có thể mong đợi |
|---|---|---|
| `Accept: application/json` | Client chấp nhận JSON | 200 với JSON khi endpoint hỗ trợ |
| `Accept: application/xml` nhưng endpoint chỉ hỗ trợ JSON | Không có representation đáp ứng | 406 |
| `Content-Type: application/json` và body JSON hợp lệ | JSON có thể deserialize | 200/201 tùy contract |
| `Content-Type: text/plain` cho endpoint chỉ nhận JSON DTO | Media type không hỗ trợ | 415 |
| `Content-Type: application/json` nhưng body sai cú pháp | Không parse được JSON | 400 |
| `Content-Type: application/problem+json` response | Problem Details response | Media type theo error contract |

Bài runnable cố ý kiểm **415** khi POST JSON DTO nhưng content type text/plain; và **400** khi content type hợp lệ nhưng JSON malformed. Hai lỗi này **không đồng nghĩa**.

### 20.1. Content-Type không phải lúc nào cũng có

Response 204, 304 hoặc một số empty-body responses có thể không cần `Content-Type`. Không đặt một helper “mọi response phải application/json” trên toàn bộ suite. Chỉ assert header khi response body thực sự theo representation ấy hoặc contract có yêu cầu riêng.

### 20.2. Charset và Unicode

UTF-8 là lựa chọn thường dùng cho JSON. Jackson có thể biểu diễn cùng một chuỗi Unicode qua ký tự trực tiếp hoặc escape theo JSON rules. Nếu API chỉ cần **semantic string equality**, parse JSON rồi assert giá trị thay vì so raw JSON bytes. Nếu endpoint dùng chữ ký số trên payload, test cần quan tâm đúng **byte serialization và canonicalization**, một yêu cầu khác.

### 20.3. Localization của error message

Nếu API trả lỗi theo `Accept-Language: vi` hoặc `en`, hãy có test chọn locale và assert public code ổn định, message tương ứng ngôn ngữ đã quy định. Không phụ thuộc default locale của máy dev/CI; cấu hình test locale rõ nếu yêu cầu.

## 21. ETag, cache và conditional requests

Cache headers và các response có điều kiện cần test ở cấp HTTP khi API thật sự hỗ trợ.

Ví dụ:

```http
GET /api/products/41
If-None-Match: "v7"
```

Nếu resource vẫn có ETag `"v7"`, server có thể trả:

```http
HTTP/1.1 304 Not Modified
ETag: "v7"
```

và không có body representation. Nếu đã thay đổi thành `"v8"`, server trả `200` với body mới và ETag mới. Test không nên assert chỉ rằng “có ETag”; phải kiểm **sự chuyển trạng thái theo conditional headers**.

Với update có `If-Match`, semantics khác với `If-None-Match`. Không dùng tên ETag trong test mà implementation không thực sự phát hoặc so sánh version.

**Lưu ý:** ví dụ báo giá đặt `Cache-Control: no-store` nhằm hướng dẫn policy; nó **không triển khai ETag**. Đừng thêm test 304 vào ví dụ runnable rồi yêu cầu pass.

## 22. Hợp đồng lỗi khi downstream hoặc DB không khả dụng

Đối với ứng dụng thật có external API hoặc DB, cần thiết kế các case:

1. Timeout downstream → error public hoặc response fallback theo contract; client không thấy stack trace.
2. Remote 429/503 → retry/backoff đúng policy, có idempotency và giới hạn.
3. Circuit breaker open → phản hồi thông báo rõ tình trạng dịch vụ, thường 503 hoặc fallback đã quy định.
4. Database constraint/conflict → 409 hoặc lỗi nghiệp vụ phù hợp, không ném raw SQL lên HTTP.
5. Unexpected exception → 500 generic, correlation ID để điều tra.
6. Partial failure → có quy tắc rõ về data consistency và khả năng retry; đừng trả 200 nếu nghiệp vụ chưa thành công mà contract không cho phép.

Những test này **không nhất thiết phải gọi external service thật**. Có thể mock đúng **outbound port** để ép timeout/exception và kiểm error mapping ở application boundary. Nhưng để chứng minh HTTP client thực sự map status, deserialize body hoặc thực hiện retry đúng khi có socket, cần adapter integration test với mock HTTP server.

Chọn test double theo ranh giới: **không mock controller/service đang được kiểm**, chỉ mock/fake những thành phần ngoài phạm vi. Nếu test trả JSON lỗi do chính mock controller sinh ra, nó không bảo vệ global exception handler thật.

## 23. Transaction và tài nguyên ngoài trong real HTTP test

Một cạm bẫy quan trọng của `@SpringBootTest(RANDOM_PORT)` là **client test và server request chạy ở các thread/transaction khác nhau**. `@Transactional` trên JUnit test method **không đảm bảo** rollback mọi write do server HTTP request tạo. Điều này khác với nhiều repository test cùng thread/context.

Với API thật có database:

- Dùng database/schema test riêng và quyền truy cập giới hạn.
- Mỗi test tạo fixture với ID riêng, không phụ thuộc thứ tự chạy.
- Cleanup sau test hoặc reset DB bằng công cụ phù hợp; cân nhắc Testcontainers.
- Không dùng tài khoản/endpoint production.
- Kiểm side effects sau HTTP request, không chỉ body 201.
- Nếu có async job, message hoặc outbox, cần chờ theo điều kiện với timeout và assert kết quả cuối, không `Thread.sleep` tùy tiện.
- Một test random-port không tự chứng minh atomicity giữa DB commit và payment gateway; cần test failure mode riêng.

**Đừng đánh đổi isolation lấy một kết quả xanh nhất thời** bằng cách cố định test order hoặc xóa hết dữ liệu chung trên một DB không dành cho test.

## 24. Bảo trì test: assertion mạnh nhưng không giòn

### 24.1. Assertion quá yếu

```java
// Phản ví dụ: chỉ kiểm status.
assertEquals(200, response.getStatusCode().value());
```

Nó bỏ qua Content-Type, header, JSON shape và dữ liệu. Nếu endpoint trả 200 cùng body `{"error":"failed"}`, test vẫn xanh.

### 24.2. Assertion quá chặt với chi tiết không thuộc contract

```java
// Phản ví dụ: phụ thuộc whitespace và thứ tự field JSON.
assertEquals(
        "{\"sku\":\"BOOK\",\"quantity\":2,\"totalVnd\":216000}",
        response.getBody());
```

Đây là snippet Java cú pháp minh họa, không nên sao chép khi mục tiêu chỉ là semantic JSON. Trình serializer đổi order của key hoặc thêm một field public hợp lệ cũng có thể khiến test gãy.

### 24.3. Khóa đúng contract

Bảo vệ ít nhất:

- Status code cụ thể, không chỉ `is2xxSuccessful` nếu client cần phân biệt.
- Content type compatible, không cần exact string khi charset hợp lệ khác.
- Những header có ý nghĩa: cache, location, correlation, retry.
- Field JSON quan trọng cùng kiểu và giá trị; absence của field nhạy cảm.
- Error code public, message theo quy ước, không lộ internals.
- Side effects khi API thật sự thay đổi state.

### 24.4. Không dùng quá nhiều snapshot không có chủ đích

Snapshot toàn response hữu ích khi muốn bảo vệ schema cứng và review thay đổi có kiểm soát. Nhưng một snapshot quá lớn có thể khiến người review chỉ “approve update” mà không thấy bug. Với API phát triển, một tập assertion trọng tâm kết hợp schema/contract tests thường dễ duy trì hơn.

## 25. Đọc nguyên nhân khi HTTP integration test đỏ

Một quy trình debug theo lớp:

**Bước 1 — Request có thật được gửi không?** Kiểm HTTP method, path, port, query, headers, body và encoding. Với `RANDOM_PORT`, kiểm cổng được inject; không hard-code 8080.

**Bước 2 — Server có khởi động không?** Nếu `Failed to load ApplicationContext`, đọc root cause của bean, property, profile hoặc auto-config. Nếu socket connection refused, phân biệt lỗi bootstrap và URL/port.

**Bước 3 — Status nào thực sự trả?** 400 vs 404 vs 415 có nguyên nhân khác nhau; 500 cần server log và trace ID, không sửa expected cho khớp nếu contract bị phá.

**Bước 4 — Content-Type có đúng không?** Body HTML error page có thể khiến Jackson parse fail, nhưng nguyên nhân gốc là status hoặc error pipeline không được chuẩn hóa.

**Bước 5 — Body là JSON hợp lệ và đúng shape không?** Parse `JsonNode`; in debug có kiểm soát những field không nhạy cảm. Không dump raw token hoặc payload khách hàng lên CI.

**Bước 6 — Header nào thiếu?** Kiểm response.getHeaders(); phân biệt header do controller, advice, filter, gateway và server tạo ra.

**Bước 7 — Các bean nào là mock/fake/real?** Nếu tính tiền sai, xác nhận service thật chạy. Nếu test chỉ mock service, không dùng kết quả này để kết luận về domain policy.

**Bước 8 — Có shared state không?** Test run riêng pass nhưng chạy suite fail thường liên quan DB/bean state, context caching, time hoặc test order.

**Bước 9 — Có đổi framework version không?** Security defaults, error response shape, Jackson serializer và client auto-config có thể thay; cập nhật test theo contract đã quyết định chứ không tự động chấp nhận mọi thay đổi.

### 25.1. Bảng triệu chứng và hành động

| Triệu chứng | Khả năng | Hành động kiểm tra |
|---|---|---|
| GET trả 404 thay vì 200 | Sai route, path param, resource không có | Xem mapping và URI |
| POST trả 415 | Sai request `Content-Type` | Đặt `application/json` khi gửi DTO |
| POST trả 400 dù JSON nhìn “đúng” | JSON syntax/type/conversion/validation | Xem response error code và server root cause |
| GET trả 406 | `Accept` không được hỗ trợ | Kiểm media type/negotiation |
| 401/403 bất ngờ | Security filter hoặc fixture auth | Kiểm principal/token/CSRF theo policy |
| Server trả HTML thay vì JSON lỗi | Error pipeline/default handler chưa chuẩn hóa | Kiểm Content-Type và exception advice |
| Header correlation ID thiếu trên lỗi | Advice/filter chỉ thêm trên success | Thêm vào error response path và test negative case |
| Cache-Control khác kỳ vọng | Controller/filter/gateway đang ghi đè | Xem từng tầng tạo headers |
| JSON sai tổng tiền | Service/policy hoặc serialization mapping | Chạy unit test domain và full integration test |
| TestRestTemplate ném lỗi vì client/network | Server chưa start, URL/port sai, timeout kết nối | Đọc startup log, không nhầm với response 4xx |
| Runtime suite chậm | Quá nhiều full context/port/server start | Giữ vài real HTTP tests quan trọng, đẩy case rẻ về slice/unit |
| Test sau fail vì dữ liệu từ test trước | Shared DB/clock/singleton | Fixture riêng, cleanup, tránh order assumption |

## 26. Mở rộng: kiểm hợp đồng bằng Spring Cloud Contract hoặc OpenAPI

Khi có nhiều client/server và API evolution, test thủ công ở từng endpoint có thể chưa đủ. Có thể kết hợp:

- **OpenAPI/schema validation:** xác minh response JSON shape, required fields và status theo đặc tả công khai. Một OpenAPI file chỉ là tài liệu nếu không có test bảo vệ implementation.
- **Consumer-driven contract tests:** kiểm provider đáp ứng những kỳ vọng cụ thể của consumer, hữu ích khi service giao tiếp độc lập.
- **Spring Cloud Contract:** xây contract dựa trên DSL/fixtures và verify provider theo workflow phù hợp.
- **Integration tests thực tế:** vẫn cần để bắt bean wiring, security/filter, serialization và nghiệp vụ mà contract stub không chứng minh.
- **E2E nhỏ nhưng có ý nghĩa:** chọn vài luồng giá trị cao xuyên qua các boundary quan trọng.

Không nên thay tất cả HTTP tests bằng schema validation. Schema có thể đúng khi số tiền/authorization sai. Ngược lại, vài HTTP happy paths không tự bảo vệ compatibility cho mọi client. **Kết hợp cấp độ kiểm thử theo rủi ro.**

## 27. Gradle và cách chạy ví dụ

Dự án cần Java 17+, Spring Boot **3.5.x**, Spring MVC, Jackson và JUnit Jupiter 5. Trong project Gradle đã cấu hình **Spring Boot plugin/BOM, repositories và toolchain/version tương ứng**, thêm dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn bổ sung** cho `build.gradle` hiện có, không phải file build độc lập vì chưa có plugins và repositories. Với Boot 3.5, `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, Jackson/test facilities thông dụng.

Chạy từ thư mục có Gradle wrapper:

```bash
./gradlew test --tests com.example.httpcontract.QuoteHttpContractIntegrationTest --tests com.example.httpcontract.QuoteMockMvcIntegrationTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.httpcontract.QuoteHttpContractIntegrationTest --tests com.example.httpcontract.QuoteMockMvcIntegrationTest
```

Nếu là multi-project, thay `test` bằng task của module thực tế như `:your-module:test` khi module có tên đó. Chép đúng 10 file Java ở cây thư mục mục 11, đặt đúng package và dependency. **Những đoạn có nhãn snippet/phản ví dụ ở các mục khác không phải class độc lập để compile**.

### 27.1. Kết quả kỳ vọng

- `QuoteHttpContractIntegrationTest` có **8 phương thức test**: GET success, GET default, POST JSON success, 404, 400 quantity, 400 query conversion, 400 JSON malformed, 415 unsupported media type.
- `QuoteMockMvcIntegrationTest` có **1 phương thức test**: full Boot context với mock web transport kiểm 200, header và JSON.
- Tổng có **9 phương thức JUnit test**. Với project và dependency đúng, test dự kiến pass và Gradle báo `BUILD SUCCESSFUL`.
- HTTP random port và startup logs có thể khác giữa lần chạy; **không có stdout nghiệp vụ cố định** để đối chiếu. `@LocalServerPort` chỉ cần lớn hơn 0.
- Đây là **kết quả kỳ vọng từ mã ví dụ được rà soát**, không phải tuyên bố đã chạy build trên workspace/repository cụ thể.

Gradle test report thường tại `build/reports/tests/test/index.html` và XML tại `build/test-results/test/`, tính từ build directory của module.

### 27.2. Nếu dự án dùng Spring Boot 4.x

Các package/client auto-configuration đã được sắp xếp lại ở Boot 4, vì vậy cần xem phiên bản cụ thể trước khi sao chép `TestRestTemplate`, `@AutoConfigureMockMvc` hoặc các test starters. Mục tiêu và hợp đồng HTTP (status, headers, JSON, public errors) không đổi; **imports và auto-configuration** là phần phải chọn theo version.

## 28. Bài tập thực hành

### Bài A — thiết kế assertion cho 201 Created

Endpoint `POST /api/orders` thật sự tạo đơn và trả `201` với `Location: /api/orders/41`, body `{"id":41,"status":"NEW"}`. Hãy viết danh sách assertion đủ để bảo vệ cả status, Location, content type, JSON và GET lại resource. Nếu `Location` trỏ tới resource không tồn tại, test nào phát hiện?

**Gợi ý:** không chỉ kiểm header; thực hiện GET resource sau tạo với fixture/DB cô lập nếu hợp đồng cho phép read-after-write.

### Bài B — phân biệt 400 và 415

Với `POST /api/quotes`:

1. Header `Content-Type: application/json`, body `{not-json}`.
2. Header `Content-Type: text/plain`, body `sku=BOOK`.

Trường hợp nào là 400, trường hợp nào là 415? Vì sao không gộp cả hai thành `INVALID_ARGUMENT`?

**Đáp án định hướng:** (1) JSON không parse được → 400, code `MALFORMED_JSON`; (2) media type không được hỗ trợ → 415, code `UNSUPPORTED_MEDIA_TYPE`. Đây là hai nguyên nhân riêng, client có hành động sửa khác nhau.

### Bài C — header không có trên đường lỗi

GET hợp lệ trả `X-Request-Id`, GET SKU sai trả 404 nhưng không có correlation header. Test thành công hiện có có phát hiện không?

**Đáp án:** Không. Phải assert header trên **negative response**. Bài runnable làm việc này qua `assertJsonHeaders(...)` cho 404/400/415.

### Bài D — đúng JSON nhưng sai status

Một endpoint thay vì trả 201 lại trả 200 cùng JSON mới tạo. Test chỉ `assertEquals(body)` có phát hiện không? Hãy thêm assertion status, `Location` và GET sau tạo nếu cần.

### Bài E — không lộ message nội bộ

Một `HttpMessageNotReadableException` của Jackson chứa vị trí parse và tên class. Vì sao không gửi `ex.getMessage()` thẳng vào HTTP response? Hãy thiết kế error code/message công khai và kiểm `stackTrace` vắng mặt.

### Bài F — JSON null hay missing?

Response A:

```json
{"note": null}
```

Response B:

```json
{}
```

Trong Jackson `JsonNode`, làm thế nào xác định `note` tồn tại nhưng null ở A, và vắng hoàn toàn ở B?

**Đáp án:** `root.has("note")` + `root.get("note").isNull()` cho A; `!root.has("note")` cho B. Không dùng một `asText()` để kết luận cả hai.

### Bài G — so sánh MockMvc và real HTTP

`@SpringBootTest` + `@AutoConfigureMockMvc` kiểm status/headers/JSON đúng. Có thể từ đó khẳng định embedded server mở cổng và TCP request routing đúng không?

**Đáp án:** Không. `MockMvc` dùng mock request/response trong process. Nếu cần transport thật, thêm `RANDOM_PORT` + HTTP client.

### Bài H — transaction rollback

`@SpringBootTest(RANDOM_PORT)` gửi POST tạo đơn vào DB; test method gắn `@Transactional` và mong server write rollback tự động khi JUnit method kết thúc. Giải thích sai lầm và đề xuất chiến lược test data isolation.

**Đáp án:** HTTP client và server xử lý trong transaction/thread khác. Tạo isolated DB/schema/fixture, cleanup, test transaction boundary thật và không dùng production DB.

### Bài I — test bảo mật theo hợp đồng

Một endpoint yêu cầu token. Hãy thiết kế case không token, token sai, token không đủ quyền, token hợp lệ. Mỗi case phải có status, header và body công khai thế nào? Lưu ý 401 có thể có `WWW-Authenticate`, 403 không được lộ tài nguyên nội bộ; phải kiểm Spring Security filter chain đúng scope.

## 29. Checklist trước khi chốt HTTP integration test

- [ ] Tôi xác định **API contract** gồm method, path, input, status, header, JSON và error response.
- [ ] Tôi chọn test depth đúng: slice, full MockMvc, real HTTP server hoặc E2E.
- [ ] Nếu nói “real HTTP”, test thực sự gọi `RANDOM_PORT` qua client HTTP.
- [ ] Tôi không mock chính controller/service mà bài test tuyên bố kiểm chứng.
- [ ] Tôi assert **status cụ thể**, không chỉ “không có exception”.
- [ ] `Content-Type` đúng media type; không so raw header string cứng nhắc khi có charset hợp lệ.
- [ ] `Cache-Control`, `Location`, `X-Request-Id` và các header khác được kiểm khi thuộc contract.
- [ ] JSON được parse để assert value/type/field presence; không phụ thuộc thứ tự object key hoặc whitespace.
- [ ] Mảng, nested data, số tiền, Unicode và date-time có assertion theo ý nghĩa khi liên quan.
- [ ] Error 400, 404, 415 có **public code/message** chính xác, không rò rỉ stack trace, SQL hoặc secret.
- [ ] Trường hợp input sai kiểu và JSON malformed được kiểm riêng với domain validation.
- [ ] Tôi phân biệt 201/202/204/304 với 200 và không ép JSON body vào response rỗng.
- [ ] Security 401/403 và rate-limit 429 được kiểm với fixture đúng nếu ứng dụng có các nhánh ấy.
- [ ] CORS, cookie, ETag, caching và error localization được kiểm theo hợp đồng thực tế, không thêm theo thói quen.
- [ ] Transaction, DB fixture, external API và async side effects có chiến lược test/cleanup riêng.
- [ ] Test chạy độc lập, không dựa thứ tự, clock ngẫu nhiên hoặc cổng 8080 cố định.
- [ ] Một test xanh có ý nghĩa: nếu giá trị nghiệp vụ hoặc HTTP response contract sai, ít nhất một assertion sẽ đỏ.
- [ ] Test result được đọc cả **status, headers và body** để chẩn đoán, không “sửa” expected theo lỗi hiện tại khi chưa xác nhận contract.

**Kết luận:** Kiểm thử hợp đồng HTTP tích hợp là kiểm tra **hành vi mà client quan sát được** qua status, headers, JSON và thông báo lỗi. `@SpringBootTest(RANDOM_PORT)` giúp xác minh đường đi qua server thật; `TestRestTemplate` giúp thu nguyên `ResponseEntity` kể cả response 4xx/5xx; Jackson hoặc JSON assertions giúp kiểm nội dung ở mức semantic. Một bài test bền vững phải bắt được sai lệch quan trọng mà không phụ thuộc whitespace, JSON key order, chi tiết exception internals hoặc test order. Khi cần bảo đảm thêm database, security, external API hay transaction, hãy bổ sung test ở ranh giới tương ứng thay vì tuyên bố một HTTP happy-path đã kiểm toàn bộ hệ thống.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications, `RANDOM_PORT`, `TestRestTemplate`, transactions: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — TestRestTemplate API và behavior 4xx/5xx: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html
- Spring Framework — MockMvc HTTP status/header/JSON testing: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Framework — ResponseEntity: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html
- Spring Framework — Error Responses / ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- RFC 9110 — HTTP Semantics (status and headers): https://www.rfc-editor.org/rfc/rfc9110
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
