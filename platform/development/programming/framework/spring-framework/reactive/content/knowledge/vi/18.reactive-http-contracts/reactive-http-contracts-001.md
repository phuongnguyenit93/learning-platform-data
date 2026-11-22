# Status, header, cookie và content type trong Spring WebFlux

## 1. Mục tiêu: xây dựng đúng hợp đồng HTTP response

Một endpoint không chỉ trả về dữ liệu. Nó còn phải thông báo cho client biết request đã được xử lý ra sao, dữ liệu được biểu diễn theo định dạng nào, có thể cache hay không, và browser cần lưu cookie nào.

Một HTTP response thường gồm ba phần:

1. **Status line:** phiên bản HTTP, status code và reason phrase (ví dụ 201 Created).
2. **Headers:** metadata như Content-Type, Location, Cache-Control, Set-Cookie, ETag.
3. **Body:** dữ liệu trả về, có thể là JSON, text, file, event stream hoặc không có body.

Trong Spring WebFlux, controller có thể mô tả cả ba phần qua **ResponseEntity**, hoặc trả dữ liệu bằng **@ResponseBody/@RestController** để Spring chọn message writer và ghi body. Với các luồng bất đồng bộ, status/header và body có thể được tạo ở những thời điểm khác nhau, vì vậy cần chọn đúng kiểu return value.

Bài này tập trung vào:

- Chọn status code theo ý nghĩa nghiệp vụ và HTTP.
- Thiết lập response headers, Location, Cache-Control, ETag và Content-Disposition.
- Tạo, cập nhật và xóa cookie qua Set-Cookie.
- Hiểu Content-Type, Accept, consumes, produces và content negotiation.
- Trả body đồng bộ, Mono, Flux và streaming response.
- Kiểm thử hợp đồng HTTP bằng WebTestClient mà không block event-loop.

## 2. Cấu trúc và vòng đời của response

Ví dụ response:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/items/42
X-Request-Id: req-42
Cache-Control: no-store

{"id":"42","name":"Reactive"}
```

Status cho biết resource mới được tạo. Location chỉ nơi client có thể truy cập resource đó. Content-Type mô tả định dạng body. Cache-Control quy định response có được lưu cache hay không.

WebFlux ghi response thông qua các thành phần như **HttpMessageWriter** và server response abstraction. Với controller annotated:

- **@RestController** là tổ hợp của @Controller và @ResponseBody.
- Giá trị method return được framework chuyển thành body nếu return type được hỗ trợ.
- **ResponseEntity** cho phép controller điều khiển status, headers và body.
- Reactor Mono/Flux có thể biểu diễn dữ liệu đến bất đồng bộ.
- Server có thể commit response khi bắt đầu ghi body. Sau thời điểm commit, status và headers không thể thay đổi như trước.

Đối với JSON, Spring thường chọn Jackson encoder/writer khi dependency phù hợp có mặt. Với text, byte array, resource hoặc SSE, writer tương ứng được chọn theo kiểu body và media type.

**Nguyên tắc quan trọng:** hoàn tất việc chọn status và headers trước khi body bắt đầu được ghi. Điều này đặc biệt quan trọng với Flux dài hoặc stream không kết thúc.

## 3. Chọn status code theo ý nghĩa của request

Status code thuộc các nhóm 1xx, 2xx, 3xx, 4xx và 5xx. API nên sử dụng một bộ status nhất quán để client có thể quyết định retry, hiển thị lỗi hoặc điều hướng.

### 3.1. Các status thành công thường dùng

| Status | Tên | Khi nào dùng | Body |
| --- | --- | --- | --- |
| 200 | OK | Request thành công và có kết quả | Thường có |
| 201 | Created | Đã tạo resource mới | Thường có representation; nên có Location |
| 202 | Accepted | Đã nhận công việc để xử lý sau, chưa khẳng định hoàn tất | Có thể có thông tin job |
| 204 | No Content | Đã xử lý thành công nhưng không cần trả representation | Không có |
| 206 | Partial Content | Trả một phần representation theo Range request | Theo quy tắc range |

Ví dụ:

- GET một item tồn tại: 200.
- POST tạo item mới: 201, thường kèm Location.
- POST đưa tác vụ vào hàng đợi: 202, có thể kèm URL kiểm tra trạng thái.
- DELETE thành công mà không cần trả dữ liệu: 204.
- Client gửi Range và server hỗ trợ byte ranges: có thể trả 206.

Không dùng 202 chỉ vì method trả Mono. 202 diễn tả **công việc nghiệp vụ chưa hoàn tất khi response được gửi**, chứ không phải “server xử lý bất đồng bộ”.

### 3.2. Các status lỗi phía client

| Status | Tình huống thường gặp |
| --- | --- |
| 400 Bad Request | Request sai cú pháp, thiếu input bắt buộc hoặc không chuyển đổi được |
| 401 Unauthorized | Chưa xác thực; thường cần WWW-Authenticate theo cơ chế auth |
| 403 Forbidden | Đã xác thực nhưng không được phép |
| 404 Not Found | Resource không tồn tại hoặc không được công khai |
| 405 Method Not Allowed | URL tồn tại nhưng HTTP method không được hỗ trợ; response nên có Allow |
| 406 Not Acceptable | Server không thể tạo representation tương thích với Accept |
| 409 Conflict | Xung đột với trạng thái hiện tại, ví dụ tạo bản ghi trùng |
| 412 Precondition Failed | Điều kiện request như If-Match không đạt |
| 413 Content Too Large | Request body vượt giới hạn |
| 415 Unsupported Media Type | Content-Type request không được endpoint hỗ trợ |
| 422 Unprocessable Content | Cú pháp request hợp lệ nhưng nội dung không thể xử lý theo contract API, nếu API chọn dùng status này |
| 429 Too Many Requests | Vượt rate limit; có thể kèm Retry-After |

### 3.3. Các status phía server và status đặc biệt

- **500 Internal Server Error:** lỗi không mong đợi trong ứng dụng.
- **502 Bad Gateway:** gateway/proxy nhận phản hồi không hợp lệ từ upstream.
- **503 Service Unavailable:** dịch vụ tạm thời không sẵn sàng; có thể kèm Retry-After.
- **504 Gateway Timeout:** gateway không nhận phản hồi kịp từ upstream.
- **304 Not Modified:** conditional GET/HEAD cho biết representation chưa thay đổi; response không có body.
- **301/302/303/307/308:** chuyển hướng; cần hiểu khác biệt về method và tính lâu dài.

Không trả 200 cho mọi tình huống rồi đưa mã lỗi vào JSON. Điều đó làm mất ý nghĩa HTTP, khiến cache, proxy, client retry và monitoring hiểu sai.

### 3.4. 201 Created và Location

Khi tạo resource, response nên chỉ rõ URL của resource mới:

```java
URI location = URI.create("/api/items/42");

return ResponseEntity.created(location)
        .body(new ItemResponse("42", "Reactive"));
```

Response có status 201, header Location và body JSON. URI có thể là URI tham chiếu tương đối; ứng dụng cũng có thể tạo absolute URI dựa trên cấu hình public base URL đáng tin cậy. Không tự dựng URL từ forwarded headers không được tin cậy.

### 3.5. 202 Accepted không phải 201

Giả sử endpoint nhận yêu cầu xuất báo cáo, sau đó worker mới thực hiện:

```java
return ResponseEntity.accepted()
        .location(URI.create("/api/jobs/job-42"))
        .body(new JobAccepted("job-42", "QUEUED"));
```

202 nói rằng yêu cầu đã được nhận để xử lý, không đảm bảo tác vụ sẽ thành công. Client có thể gọi URL job để kiểm tra trạng thái. Khi công việc hoàn tất và resource kết quả được tạo, endpoint khác mới có thể trả 200 hoặc 201 tùy contract.

### 3.6. 204 No Content không có body

```java
@DeleteMapping("/api/items/{id}")
public Mono<ResponseEntity<Void>> delete(
        @PathVariable String id) {

    return itemService.delete(id)
            .thenReturn(ResponseEntity.noContent().build());
}
```

Đây là đoạn minh họa, giả định itemService.delete trả Mono<Void>. Response 204 không được kèm body. Nếu client cần biết resource đã xóa hay kết quả nào khác, hãy chọn một response có body thay vì cố gắng ghi dữ liệu sau 204.

## 4. ResponseEntity: cách trực tiếp để điều khiển status, headers và body

**ResponseEntity<T>** bao bọc status code, headers và body. Đây là lựa chọn dễ đọc khi endpoint cần tùy chỉnh hợp đồng response.

### 4.1. ResponseEntity đồng bộ

```java
@GetMapping("/health")
public ResponseEntity<String> health() {
    return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .header("X-Service-Version", "1.0")
            .body("UP");
}
```

Trong @RestController, String là body được ghi ra response. Nó không phải tên view như trong một @Controller dùng view resolution.

### 4.2. Mono<ResponseEntity<T>> khi status phụ thuộc kết quả async

```java
@GetMapping("/api/items/{id}")
public Mono<ResponseEntity<ItemResponse>> find(
        @PathVariable String id) {

    return itemService.findById(id)
            .map(item -> ResponseEntity.ok()
                    .header("X-Request-Id", "req-42")
                    .body(toResponse(item)))
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Ở đây status phụ thuộc kết quả của publisher: có item thì 200; không có item thì 404. Controller trả publisher để WebFlux quản lý; không cần block hoặc tự subscribe.

### 4.3. Các hình dạng reactive khác nhau

Spring WebFlux hỗ trợ nhiều cách kết hợp ResponseEntity và reactive types:

| Return type | Status/headers được biết khi nào? | Body được biết khi nào? |
| --- | --- | --- |
| ResponseEntity<T> | Ngay khi method return | Ngay |
| Mono<ResponseEntity<T>> | Khi Mono phát ResponseEntity | Cùng lúc với ResponseEntity |
| ResponseEntity<Mono<T>> | Ngay khi method return | Sau đó, khi Mono phát dữ liệu |
| ResponseEntity<Flux<T>> | Ngay khi method return | Sau đó, khi Flux phát dữ liệu |
| Mono<ResponseEntity<Flux<T>>> | Khi Mono phát ResponseEntity | Flux body tiếp tục phát sau đó |

Chọn theo nhu cầu:

- Dùng **Mono<ResponseEntity<T>>** khi cần đọc dữ liệu bất đồng bộ rồi quyết định status/header/body.
- Dùng **ResponseEntity<Flux<T>>** khi status/header có thể xác định ngay nhưng body là stream.
- Dùng **Mono<ResponseEntity<Flux<T>>>** khi metadata response cũng cần được lấy bất đồng bộ trước khi bắt đầu stream.
- Không lồng Mono/Flux nhiều tầng chỉ vì “reactive hơn”; chọn cấu trúc đơn giản nhất thể hiện đúng lifecycle.

Ví dụ ResponseEntity<Flux<T>>:

```java
@GetMapping(value = "/api/numbers",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public ResponseEntity<Flux<ServerSentEvent<Integer>>> numbers() {
    Flux<ServerSentEvent<Integer>> body = Flux.range(1, 5)
            .map(value -> ServerSentEvent.builder(value)
                    .event("number")
                    .build());

    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
}
```

Status 200 và Cache-Control được xác định ngay; body được ghi khi Flux phát event.

### 4.4. Khi nào dùng @ResponseStatus?

Nếu status cố định, có thể dùng annotation:

```java
@PostMapping("/api/notifications")
@ResponseStatus(HttpStatus.CREATED)
public Mono<NotificationResponse> create(
        @RequestBody NotificationRequest request) {

    return notificationService.create(request);
}
```

@ResponseStatus phù hợp cho status tĩnh. Nếu status hoặc headers thay đổi theo kết quả, dùng ResponseEntity. Tránh khai báo status cố định ở annotation rồi đồng thời cố thay đổi status bằng nhiều cơ chế khác nhau mà không có lý do rõ ràng.

## 5. Thêm và đọc response headers

### 5.1. Header là metadata của response

Một số header thường gặp:

| Header | Ý nghĩa |
| --- | --- |
| Content-Type | Media type của response body |
| Content-Length | Kích thước body theo byte, nếu biết |
| Location | URL của resource mới hoặc đích chuyển hướng |
| Cache-Control | Chính sách cache |
| ETag | Validator của representation |
| Last-Modified | Thời điểm representation được sửa |
| Vary | Header request ảnh hưởng đến lựa chọn representation/cache key |
| Content-Disposition | Hiển thị inline hay tải file đính kèm |
| Content-Language | Ngôn ngữ của representation |
| Retry-After | Thời gian client nên chờ trước khi thử lại |
| WWW-Authenticate | Thử thách xác thực |
| Allow | HTTP methods được hỗ trợ cho resource |
| X-Request-Id | Correlation ID theo quy ước ứng dụng |

Một số header là chuẩn HTTP, một số là quy ước nội bộ. Với header tùy chỉnh, nên dùng tên có namespace phù hợp và ghi rõ contract cho client.

### 5.2. Thiết lập header bằng ResponseEntity

```java
return ResponseEntity.ok()
        .header("X-Request-Id", requestId)
        .header("X-Api-Version", "v1")
        .contentType(MediaType.APPLICATION_JSON)
        .body(response);
```

Có thể thêm nhiều giá trị cho cùng một header. Cần hiểu header đó có cho phép nhiều field values hay không; không phải header nào cũng có thể nối bằng dấu phẩy một cách tùy ý.

### 5.3. Dùng HttpHeaders khi cần nhiều thao tác

```java
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.set("X-Request-Id", "req-42");
headers.setCacheControl(CacheControl.noStore());

return ResponseEntity
        .status(HttpStatus.OK)
        .headers(headers)
        .body(response);
```

HttpHeaders cung cấp các helper cho header phổ biến, giảm lỗi chính tả và xử lý giá trị. Trong code cần thêm nhiều Set-Cookie, dùng add thay vì set để giữ từng header riêng.

### 5.4. Không tự đặt Content-Length cho stream

Với body nhỏ, framework/server thường có thể xác định kích thước hoặc chọn cơ chế truyền phù hợp. Với Flux, SSE hoặc stream không biết trước độ dài, đừng tự đặt Content-Length nếu không tính chính xác số byte. Một giá trị sai có thể làm client đọc thiếu dữ liệu hoặc chờ mãi.

Không giả định mọi response đều dùng chunked transfer encoding; cách truyền phụ thuộc HTTP version và server connector. Hãy để server quản lý framing nếu ứng dụng không có yêu cầu đặc biệt.

### 5.5. Content-Disposition cho file download

Khi trả file, có thể yêu cầu browser tải xuống với tên gợi ý:

```java
ContentDisposition disposition = ContentDisposition.attachment()
        .filename("report.csv", StandardCharsets.UTF_8)
        .build();

return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType("text/csv"))
        .header(HttpHeaders.CONTENT_DISPOSITION,
                disposition.toString())
        .body(csvBytes);
```

Tên file nên được tạo hoặc kiểm tra từ dữ liệu đáng tin cậy. Không nối trực tiếp một tên file tùy ý từ client vào header; cần tránh ký tự điều khiển và header injection. Với file lớn, cân nhắc trả Resource hoặc stream thay vì giữ toàn bộ byte array trong heap.

## 6. Thiết lập và quản lý cookies trong response

### 6.1. Cookie được gửi bằng Set-Cookie

Khi server muốn browser lưu cookie, response sử dụng header **Set-Cookie**:

```http
HTTP/1.1 200 OK
Set-Cookie: theme=dark; Path=/; Max-Age=86400; SameSite=Lax
Content-Type: text/plain

Preference saved
```

Client gửi lại cookie trong request Cookie header ở những request phù hợp với domain, path, expiry và policy của browser. Request Cookie header chỉ mang cặp name/value; các thuộc tính như Secure, HttpOnly và SameSite là chính sách được server đặt qua Set-Cookie, không phải metadata browser gửi lại.

### 6.2. Dùng ResponseCookie

Spring cung cấp **ResponseCookie** để tạo Set-Cookie có cấu trúc:

```java
ResponseCookie sessionCookie = ResponseCookie
        .from("session", "opaque-session-id")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofHours(8))
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, sessionCookie.toString())
        .contentType(MediaType.TEXT_PLAIN)
        .body("Session cookie issued");
```

ResponseCookie giúp biểu diễn các thuộc tính cookie rõ ràng và tạo chuỗi header hợp lệ. Ví dụ dùng giá trị session giả để minh họa; ứng dụng thật phải dùng session identifier ngẫu nhiên, khó đoán, được quản lý phía server và không log giá trị.

### 6.3. Các thuộc tính cookie quan trọng

| Attribute | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Path | Giới hạn path mà browser gửi cookie | Path=/ áp dụng rộng trong host |
| Domain | Host/domain nhận cookie | Không mở rộng domain nếu không cần |
| Max-Age | Thời gian sống tính bằng giây | 0 hoặc giá trị âm có thể dùng để xóa tùy API |
| Expires | Thời điểm hết hạn | Max-Age thường được ưu tiên khi cùng xuất hiện |
| Secure | Chỉ gửi qua kết nối an toàn theo browser | Production nên dùng HTTPS |
| HttpOnly | JavaScript phía browser không đọc cookie qua API thông thường | Server vẫn đọc được cookie |
| SameSite | Kiểm soát một số trường hợp gửi cookie cross-site | Lax, Strict hoặc None |
| Partitioned | Cookie partitioned trong browser hỗ trợ | Chỉ dùng khi có yêu cầu tương thích cụ thể |

Nếu SameSite=None, browser hiện đại thường yêu cầu Secure. Hãy kiểm tra hành vi browser mục tiêu và chính sách domain/subdomain.

### 6.4. Tạo nhiều cookie trong cùng response

Mỗi cookie nên được gửi bằng một Set-Cookie header riêng. **Không nối nhiều cookie thành một chuỗi phân tách dấu phẩy**, vì Set-Cookie có quy tắc riêng và Expires có thể chứa dấu phẩy.

```java
ResponseCookie session = ResponseCookie.from(
                "session", "opaque-session-id")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofHours(8))
        .build();

ResponseCookie theme = ResponseCookie.from("theme", "dark")
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofDays(30))
        .build();

return ResponseEntity.ok()
        .headers(headers -> {
            headers.add(HttpHeaders.SET_COOKIE, session.toString());
            headers.add(HttpHeaders.SET_COOKIE, theme.toString());
        })
        .body("Cookies issued");
```

Dùng headers.add cho từng cookie. Nếu dùng headers.set nhiều lần cùng key, giá trị trước có thể bị thay thế.

### 6.5. Xóa cookie

Để browser xóa cookie, gửi Set-Cookie cùng tên và phạm vi Path/Domain tương ứng, đặt Max-Age về 0:

```java
ResponseCookie expired = ResponseCookie.from("session", "")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ZERO)
        .build();

return ResponseEntity.noContent()
        .header(HttpHeaders.SET_COOKIE, expired.toString())
        .build();
```

Nếu cookie ban đầu được tạo với Path hoặc Domain cụ thể, phải gửi cookie hết hạn với phạm vi phù hợp. Chỉ gửi cùng tên nhưng Path/Domain khác có thể tạo một cookie khác mà không xóa cookie cũ.

Xóa cookie ở browser cũng không thay thế việc thu hồi session phía server. Khi logout, server cần vô hiệu hóa session/token theo contract bảo mật, rồi gửi cookie hết hạn.

### 6.6. Bảo mật cookie session

Với cookie dùng để xác thực:

- Dùng Secure trên HTTPS.
- Dùng HttpOnly để giảm nguy cơ JavaScript đọc session identifier.
- Chọn SameSite theo luồng đăng nhập và nhu cầu cross-site.
- Đặt Path/Domain ở phạm vi nhỏ nhất cần thiết.
- Dùng Max-Age/Expires phù hợp với session policy.
- Xoay vòng session ID khi đăng nhập hoặc thay đổi đặc quyền.
- Bảo vệ các thao tác thay đổi trạng thái bằng CSRF defense phù hợp.
- Không ghi session cookie vào log, telemetry hoặc error response.

SameSite là một lớp bảo vệ, không phải giải pháp CSRF duy nhất cho mọi kiến trúc. Nếu xác thực dựa vào cookie tự động được browser gửi, cần đánh giá CSRF, CORS và luồng cross-site riêng.

## 7. Content-Type, Accept và content negotiation

Ba khái niệm thường bị nhầm:

- **Content-Type của request:** body client đang gửi có định dạng nào.
- **Accept của request:** client muốn nhận response ở định dạng nào.
- **Content-Type của response:** server thực tế đã trả body theo định dạng nào.

Ví dụ:

```http
POST /api/items HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Reactive"}
```

Client gửi JSON và mong nhận JSON. Server có thể chọn handler/encoder phù hợp hoặc từ chối nếu endpoint không hỗ trợ media type đó.

### 7.1. consumes: kiểm tra media type của request body

```java
@PostMapping(
        path = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<ItemResponse> create(
        @RequestBody Mono<CreateItemRequest> request) {
    // ...
}
```

Thuộc tính consumes giới hạn Content-Type request được chấp nhận. Nếu client gửi text/plain trong khi endpoint chỉ consumes application/json, Spring thường trả 415 Unsupported Media Type.

consumes phù hợp khi endpoint có contract body rõ ràng. Không khai báo consumes quá rộng nếu controller chỉ hiểu một định dạng.

### 7.2. produces: chọn media type của response

```java
@GetMapping(
        path = "/api/items/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<ItemResponse> find(@PathVariable String id) {
    // ...
}
```

produces khai báo representation mà handler có thể tạo. Spring đối chiếu với Accept header của client. Nếu client chỉ chấp nhận text/plain trong khi endpoint chỉ produces application/json, mapping không phù hợp và thường trả 406 Not Acceptable.

Có thể khai báo nhiều media type nếu endpoint thực sự hỗ trợ nhiều representation:

```java
@GetMapping(
        path = "/api/export",
        produces = {
                MediaType.APPLICATION_JSON_VALUE,
                MediaType.TEXT_PLAIN_VALUE
        })
public Mono<?> export() {
    // ...
}
```

Nếu cùng URL có nhiều handler khác nhau theo media type, Spring có thể chọn handler phù hợp với Accept. Cần test rõ từng biến thể để tránh một endpoint vô tình trả định dạng không được client yêu cầu.

### 7.3. Accept có thể chứa nhiều media types và quality values

Client có thể gửi:

```http
Accept: application/json, text/plain;q=0.8, */*;q=0.1
```

q là quality factor biểu thị mức ưu tiên. Content negotiation xem xét media types mà client chấp nhận và những media types mà server có thể ghi. Wildcard như */* cho phép nhiều kiểu. Không nên tự parse Accept bằng cách split chuỗi; dùng cơ chế của Spring và MediaType.

### 7.4. Content-Type của response

Khi cần chỉ định rõ:

```java
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(response);
```

Nếu controller dùng @RestController và body là object, message writer thường chọn media type phù hợp dựa trên Accept và codec có sẵn. ResponseEntity.contentType cho phép khai báo rõ hơn. Tránh gán Content-Type JSON cho body là plain text hoặc bytes không phải JSON.

### 7.5. Các lỗi 406 và 415 khác nhau

| Status | Nguyên nhân | Header liên quan |
| --- | --- | --- |
| 406 Not Acceptable | Server không có response representation phù hợp với Accept | Accept |
| 415 Unsupported Media Type | Server không hỗ trợ định dạng request body được gửi | Content-Type |
| 400 Bad Request | Body sai cú pháp hoặc input không bind/convert được | Có thể liên quan body/query/header |

Ví dụ:

- POST JSON nhưng endpoint chỉ consumes text/plain: 415.
- GET endpoint produces JSON nhưng client gửi Accept text/plain: 406.
- POST JSON bị thiếu dấu ngoặc hoặc sai kiểu field: thường 400.

Đừng xử lý 406/415 bằng cách đổi response Content-Type tùy tiện; phải sửa mapping hoặc request contract.

## 8. Các media types phổ biến trong WebFlux

| Media type | Trường hợp sử dụng |
| --- | --- |
| application/json | JSON object/array |
| application/problem+json | HTTP Problem Details |
| text/plain | Text đơn giản |
| text/html | HTML |
| text/csv | CSV |
| application/octet-stream | Binary data chung |
| application/pdf | PDF |
| multipart/form-data | Upload nhiều phần |
| text/event-stream | Server-Sent Events |
| application/x-www-form-urlencoded | Form URL encoded |

Spring dùng codec/message writer để encode body. Nếu media type hoặc kiểu object không được hỗ trợ bởi writer đã cấu hình, response có thể lỗi khi ghi. Với định dạng riêng, có thể đăng ký custom encoder/writer qua WebFlux configuration.

**JSON không tự động có nghĩa là streaming.** Một Flux object có thể được xử lý như collection JSON tùy media type và writer. Nếu cần gửi event liên tục, hãy khai báo media type streaming như text/event-stream và dùng kiểu body phù hợp.

## 9. Streaming response và thời điểm commit

### 9.1. Server-Sent Events

Ví dụ endpoint SSE:

```java
@GetMapping(
        value = "/api/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> ServerSentEvent.<String>builder()
                    .id(Long.toString(sequence))
                    .event("heartbeat")
                    .data("tick-" + sequence)
                    .build());
}
```

Browser/client nhận event theo thời gian. Mỗi event có thể chứa id, event name và data. Với stream vô hạn, server không chờ toàn bộ Flux hoàn tất rồi mới trả body.

### 9.2. Headers phải được đặt trước khi stream ghi dữ liệu

Khi response đã bắt đầu được gửi:

- Status đã commit.
- Headers đã commit.
- Không thể đổi Content-Type hoặc Set-Cookie sau đó.
- Nếu Flux lỗi giữa stream, server không thể thay response đã gửi bằng một JSON lỗi HTTP mới.
- Client có thể nhận một stream bị ngắt hoặc lỗi ở tầng giao thức.

Vì vậy hãy xác định status, content type, cache policy, CORS và cookie trước khi phát phần tử đầu tiên. Với SSE, nếu cần thông báo lỗi ở mức ứng dụng sau khi stream bắt đầu, hãy thiết kế một event/error protocol riêng và bảo đảm client hiểu nó.

### 9.3. Không block để chờ stream hoàn tất

Không dùng collectList().block() trong controller chỉ để tạo một response. Nếu API cần một JSON array hữu hạn, có thể return Flux<T> và để framework ghi theo contract của media type; nếu cần tính toán toàn bộ danh sách để quyết định status/header, compose bằng collectList() trong reactive chain rồi trả Mono<ResponseEntity<List<T>>>.

Ví dụ:

```java
return itemService.findAll()
        .collectList()
        .map(items -> ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(items));
```

collectList giữ các phần tử trong bộ nhớ, vì vậy chỉ dùng khi tập kết quả có giới hạn hợp lý. Với hàng triệu dòng hoặc dữ liệu dài, streaming có thể phù hợp hơn.

## 10. HTTP caching: Cache-Control, ETag và Last-Modified

### 10.1. Cache-Control

Cache-Control hướng dẫn browser/proxy có thể lưu response trong bao lâu và trong phạm vi nào:

```java
return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(30, TimeUnit.SECONDS)
                .cachePrivate())
        .body(response);
```

Một số chỉ thị phổ biến:

- public: cache chia sẻ có thể lưu response nếu các điều kiện khác cho phép.
- private: chỉ cache riêng của user/browser.
- no-cache: có thể lưu nhưng cần revalidate trước khi dùng lại.
- no-store: không lưu response.
- max-age: thời gian freshness tính bằng giây.
- must-revalidate: khi stale phải revalidate trước khi dùng.

Với response chứa thông tin cá nhân hoặc session, không bật public cache chỉ để tăng hiệu năng. Chọn policy theo tính nhạy cảm và khả năng chia sẻ dữ liệu.

### 10.2. ETag

ETag là validator của representation. Khi nội dung không thay đổi, client có thể gửi If-None-Match và server trả 304 Not Modified không có body.

```java
@GetMapping("/api/books/{id}")
public ResponseEntity<BookResponse> book(
        @PathVariable String id) {

    BookResponse book = bookService.find(id);
    return ResponseEntity.ok()
            .cacheControl(CacheControl.maxAge(30, TimeUnit.SECONDS)
                    .cachePrivate())
            .eTag(book.version())
            .body(book);
}
```

Đây là ví dụ đồng bộ để minh họa ResponseEntity và caching. Trong ứng dụng reactive, nếu bookService trả Mono<BookResponse>, có thể map kết quả sang ResponseEntity tương ứng. Spring hỗ trợ so sánh ETag/Last-Modified với conditional request headers và có thể trả 304 khi representation chưa thay đổi.

ETag cần đại diện đúng version của representation. Nếu nội dung khác nhau theo ngôn ngữ, user hoặc content negotiation, cache key và Vary/header cần được thiết kế đúng. Không dùng cùng một ETag cho hai representation khác nhau.

### 10.3. Last-Modified và conditional request

Last-Modified biểu diễn thời điểm resource thay đổi. Client có thể gửi If-Modified-Since; nếu resource không thay đổi kể từ thời điểm đó, server trả 304.

Với GET/HEAD, conditional request thường giúp tiết kiệm bandwidth. Với các thao tác thay đổi resource, If-Match/If-Unmodified-Since có thể được dùng để tránh ghi đè cập nhật mới hơn; khi precondition không đạt, 412 Precondition Failed là status phù hợp.

Không tự trả 304 nếu chưa kiểm tra validator. Response 304 không có representation body và thường giữ các metadata cache cần thiết.

## 11. Tự ghi response bằng ServerHttpResponse

Trong phần lớn controller, ResponseEntity dễ đọc và an toàn hơn. Khi cần kiểm soát thấp hơn, có thể nhận ServerHttpResponse:

```java
@GetMapping("/api/raw")
public Mono<Void> raw(ServerHttpResponse response) {
    response.setStatusCode(HttpStatus.ACCEPTED);
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
    response.getHeaders().set("X-Mode", "reactive");

    byte[] bytes = "queued".getBytes(StandardCharsets.UTF_8);
    DataBuffer buffer = response.bufferFactory().wrap(bytes);

    return response.writeWith(Mono.just(buffer));
}
```

Đây là ví dụ mức thấp cần import ServerHttpResponse, DataBuffer, StandardCharsets và Reactor Mono. Controller tự thiết lập status/header rồi trả Mono<Void> biểu diễn việc ghi body hoàn tất.

Khi dùng API này:

- Thiết lập status và headers trước khi gọi writeWith.
- Không gọi subscribe thủ công.
- Không giữ DataBuffer sau khi giao cho framework/server.
- Với buffer được cấp phát trực tiếp hoặc pooled, tuân thủ quy tắc ownership/release của DataBuffer.
- Nếu chỉ cần status/header/body thông thường, ưu tiên ResponseEntity.

Không dùng cả ResponseEntity và ghi trực tiếp response trên cùng một request nếu hai cơ chế tranh quyền điều khiển response. Chọn một cách làm chủ đạo.

## 12. Content-Type, header và cookie trong một controller hoàn chỉnh

Ví dụ dưới đây dùng Java 17+ và Spring Boot 3.x với spring-boot-starter-webflux. Controller không cần database để minh họa hợp đồng HTTP; các response được tạo trong bộ nhớ.

### 12.1. Cấu trúc dự án

```text
http-contract-demo/
  src/
    main/
      java/demo/
        HttpContractApplication.java
        HttpContractController.java
    test/
      java/demo/
        HttpContractControllerTest.java
  build.gradle
```

Dependency chính:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Dự án cần Spring Boot Gradle plugin và dependency management tương thích. Để BOM quản lý phiên bản Spring Framework, Reactor, Jackson và test support.

### 12.2. Application class

Tệp src/main/java/demo/HttpContractApplication.java:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpContractApplication.class, args);
    }
}
```

### 12.3. DTO

Tệp src/main/java/demo/CreateItemRequest.java:

```java
package demo;

public record CreateItemRequest(String name) {
}
```

Tệp src/main/java/demo/ItemResponse.java:

```java
package demo;

public record ItemResponse(String id, String name) {
}
```

### 12.4. Controller

Tệp src/main/java/demo/HttpContractController.java:

```java
package demo;

import java.net.URI;
import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class HttpContractController {

    @GetMapping(
            value = "/api/items/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemResponse>> find(
            @PathVariable String id) {

        ItemResponse item = new ItemResponse(id, "Reactive item");

        return Mono.just(ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "req-42")
                .body(item));
    }

    @PostMapping(
            value = "/api/items",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemResponse>> create(
            @RequestBody Mono<CreateItemRequest> request) {

        return request
                .map(body -> new ItemResponse("42", body.name()))
                .map(item -> ResponseEntity
                        .created(URI.create("/api/items/" + item.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(item));
    }

    @DeleteMapping("/api/items/{id}")
    public Mono<ResponseEntity<Void>> delete(
            @PathVariable String id) {

        return Mono.just(ResponseEntity.noContent().build());
    }

    @GetMapping("/api/session")
    public ResponseEntity<String> issueSessionCookie() {
        ResponseCookie cookie = ResponseCookie
                .from("session", "demo-session-id")
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax")
                .path("/")
                .maxAge(Duration.ofHours(8))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .contentType(MediaType.TEXT_PLAIN)
                .body("Session cookie issued");
    }

    @GetMapping(
            value = "/api/plain",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> plain() {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("Hello WebFlux");
    }

    @GetMapping(
            value = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(sequence -> ServerSentEvent.<String>builder()
                        .id(Long.toString(sequence))
                        .event("heartbeat")
                        .data("tick-" + sequence)
                        .build());
    }

    @GetMapping("/api/cache")
    public ResponseEntity<ItemResponse> cached() {
        ItemResponse item = new ItemResponse("42", "Cached item");

        return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(
                        30, java.util.concurrent.TimeUnit.SECONDS)
                        .cachePrivate())
                .eTag("v1")
                .body(item);
    }

    @GetMapping("/api/accepted")
    public ResponseEntity<String> accepted() {
        return ResponseEntity.accepted()
                .location(URI.create("/api/jobs/job-42"))
                .body("Job queued");
    }
}
```

Controller thể hiện:

- GET item: 200, JSON, custom response header.
- POST item: nhận body JSON bất đồng bộ và trả 201 cùng Location.
- DELETE: 204 không body.
- Session endpoint: Set-Cookie với HttpOnly, Secure, SameSite và Max-Age.
- Plain endpoint: chỉ produces text/plain.
- Events: SSE stream với text/event-stream.
- Cache endpoint: Cache-Control và ETag.
- Accepted endpoint: 202 cùng Location cho job.

Cookie trong ví dụ chỉ là giá trị demo. Production phải tạo session ID an toàn, xác thực session phía server và chỉ bật Secure trên HTTPS.

### 12.5. Chạy ứng dụng

```bash
./gradlew bootRun
```

Gọi GET JSON:

```bash
curl -i -H "Accept: application/json"   http://localhost:8080/api/items/42
```

Các header quan trọng:

```text
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: req-42
```

Gọi POST tạo resource:

```bash
curl -i -X POST http://localhost:8080/api/items   -H "Content-Type: application/json"   -H "Accept: application/json"   -d '{"name":"Reactive"}'
```

Response có status 201 và Location /api/items/42; body chứa id và name.

Gọi DELETE:

```bash
curl -i -X DELETE http://localhost:8080/api/items/42
```

Response status 204, không có body.

Nhận cookie:

```bash
curl -i http://localhost:8080/api/session
```

Response có Set-Cookie bắt đầu bằng session=demo-session-id và các thuộc tính Secure, HttpOnly, SameSite=Lax, Path và Max-Age.

Gọi SSE:

```bash
curl -N http://localhost:8080/api/events
```

Client nhận event heartbeat mỗi giây. Dừng client bằng Ctrl+C; subscription phía server có thể được cancel khi disconnect được phát hiện.

## 13. Kiểm thử hợp đồng HTTP bằng WebTestClient

Test nên xác nhận cả status, headers, cookies, body và media type. Không chỉ kiểm tra body JSON.

Tệp src/test/java/demo/HttpContractControllerTest.java:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(HttpContractController.class)
class HttpContractControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void getReturnsJsonStatusAndCustomHeader() {
        client.get()
                .uri("/api/items/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectHeader()
                    .valueEquals("X-Request-Id", "req-42")
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.name").isEqualTo("Reactive item");
    }

    @Test
    void createReturns201AndLocation() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItemRequest("Reactive"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader()
                    .valueEquals(HttpHeaders.LOCATION, "/api/items/42")
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.name").isEqualTo("Reactive");
    }

    @Test
    void deleteReturns204WithoutBody() {
        client.delete()
                .uri("/api/items/42")
                .exchange()
                .expectStatus().isNoContent()
                .expectBody().isEmpty();
    }

    @Test
    void responseCookieHasSecurityAttributes() {
        client.get()
                .uri("/api/session")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueMatches(HttpHeaders.SET_COOKIE, ".*HttpOnly.*")
                .expectHeader()
                    .valueMatches(HttpHeaders.SET_COOKIE, ".*Secure.*")
                .expectHeader()
                    .valueMatches(HttpHeaders.SET_COOKIE, ".*SameSite=Lax.*");
    }

    @Test
    void plainEndpointNegotiatesTextOnly() {
        client.get()
                .uri("/api/plain")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
                .expectBody(String.class)
                .isEqualTo("Hello WebFlux");
    }

    @Test
    void unacceptableMediaTypeReturns406() {
        client.get()
                .uri("/api/plain")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isEqualTo(406);
    }

    @Test
    void unsupportedRequestContentTypeReturns415() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("name=Reactive")
                .exchange()
                .expectStatus().isEqualTo(415);
    }
}
```

Chạy test:

```bash
./gradlew test
```

Dependency spring-boot-starter-test cung cấp JUnit Jupiter và WebTestClient support. Test này dùng WebFlux test slice, không cần mở cổng HTTP thật. Nếu dự án có Spring Security, cần cấu hình test security phù hợp để status 401/403 không che mất kết quả kiểm thử controller.

## 14. Các lỗi phổ biến khi xây dựng HTTP response

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Trả 200 cho mọi kết quả | Client và monitoring không phân biệt thành công/lỗi | Chọn status theo HTTP và nghiệp vụ |
| Tạo resource nhưng không có Location | Client khó tìm resource mới | Trả 201 cùng Location phù hợp |
| Trả body cho 204/304 | Vi phạm semantics của status không body | Dùng response không body |
| Dùng 202 cho mọi publisher | Nhầm async execution với accepted job | Chỉ dùng 202 khi xử lý nghiệp vụ còn chờ |
| Gọi block để biết kết quả trước khi trả ResponseEntity | Chặn event-loop | Dùng Mono<ResponseEntity<T>> |
| Gọi subscribe trong controller | Tách công việc khỏi HTTP lifecycle | Return Mono/Flux để WebFlux quản lý |
| Set Content-Type sai với body | Client decode sai hoặc lỗi writer | Chọn MediaType đúng với representation |
| Nhầm Accept với Content-Type | Dùng sai 406/415 | Accept là định dạng muốn nhận; Content-Type là định dạng body gửi |
| Không khai báo produces/consumes rõ ràng | Mapping có thể nhận/trả ngoài contract | Khai báo media type khi endpoint có giới hạn |
| Nối nhiều Set-Cookie bằng dấu phẩy | Cookie header có thể bị parse sai | Add từng Set-Cookie header riêng |
| Dùng SameSite=None nhưng thiếu Secure | Browser có thể từ chối cookie | Cấu hình Secure khi dùng None |
| Chỉ xóa cookie phía browser | Session phía server vẫn có thể còn hiệu lực | Thu hồi session phía server và gửi cookie hết hạn |
| Đặt header sau khi stream đã bắt đầu | Response đã commit, không sửa được | Chuẩn bị status/header trước phần tử đầu tiên |
| Tự đặt Content-Length cho Flux | Kích thước sai, client chờ hoặc cắt body | Để server quản lý framing cho stream |
| Cache dữ liệu riêng tư bằng public | Có thể lộ dữ liệu giữa người dùng | Chọn private/no-store phù hợp |
| Dùng ETag giống nhau cho representation khác nhau | Cache trả nội dung sai | ETag phải phản ánh representation/version thực |
| Ghi log session cookie/Authorization | Rò credential | Redact hoặc bỏ hoàn toàn giá trị nhạy cảm |
| Tự parse Accept/Set-Cookie bằng split đơn giản | Xử lý sai grammar header | Dùng MediaType, HttpHeaders và ResponseCookie |
| Dùng ServerHttpResponse và ResponseEntity cùng lúc | Hai cơ chế có thể tranh quyền điều khiển response | Chọn một cách ghi response cho mỗi handler |

## 15. Quy trình thiết kế response contract

Khi thêm endpoint, hãy trả lời theo thứ tự:

1. **Request thành công có nghĩa gì?** Resource đã tạo, chỉ nhận job, cập nhật xong hay không có nội dung trả về?
2. **Status code nào đúng?** 200, 201, 202, 204 hay một status khác?
3. **Client cần biết URL nào?** Nếu tạo resource hoặc job, cân nhắc Location.
4. **Representation là gì?** JSON, text, file, SSE hay binary?
5. **Accept/Content-Type có ràng buộc gì?** Khai báo produces/consumes nếu endpoint chỉ hỗ trợ một số media type.
6. **Header nào cần thiết?** Cache-Control, ETag, Content-Language, Vary, Retry-After, Content-Disposition?
7. **Có cookie không?** Xác định Path, Domain, Max-Age, Secure, HttpOnly, SameSite và logout behavior.
8. **Body là một giá trị hay stream?** Chọn T, Mono<T>, Flux<T> và ResponseEntity tương ứng.
9. **Response có thể commit trước khi stream kết thúc không?** Chuẩn bị status/header trước khi phát dữ liệu.
10. **Có blocking I/O không?** Dùng reactive client/driver hoặc cô lập legacy blocking; không block event-loop.
11. **Test toàn bộ HTTP contract:** status, headers, cookie, content type, body, 406/415 và no-content behavior.
12. **Kiểm tra bảo mật/cache:** không cache nhầm dữ liệu riêng tư, không log secret và không tin forwarded headers không đáng tin.

## 16. Tài liệu tham khảo chính thức

- [Spring Framework – ResponseEntity trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): điều khiển status, headers và body; các hình dạng ResponseEntity kết hợp Mono/Flux.
- [Spring Framework – @ResponseBody trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): HttpMessageWriter, body serialization và reactive return types.
- [Spring Framework – Return Types của WebFlux Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): các kiểu return value và streaming behavior.
- [Spring Framework – HTTP Caching trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html): Cache-Control, ETag, Last-Modified và conditional requests.
- [Spring Framework – ResponseCookie Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html): tạo cookie response với các thuộc tính bảo mật và thời hạn.
- [Spring Framework – RequestMapping Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html): consumes/produces và điều kiện mapping theo media type.
- [Spring Framework – WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): cấu hình HTTP message codecs và writer.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status codes, representation metadata, content negotiation và HTTP headers.
- [RFC 6265 – HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cookie và Set-Cookie semantics.

## 17. Ghi nhớ

Một response WebFlux có ba phần phải được thiết kế cùng nhau: **status nói request được xử lý ra sao; headers mô tả metadata và chính sách; Content-Type cho biết body được biểu diễn thế nào**.

Dùng ResponseEntity khi cần điều khiển status/header/body, và chọn đúng dạng reactive return type để quyết định metadata được biết trước hay sau khi xử lý bất đồng bộ. Dùng ResponseCookie để tạo Set-Cookie, thêm mỗi cookie thành một header riêng và bảo vệ session bằng Secure, HttpOnly, SameSite, Path và thời hạn phù hợp. Dùng consumes cho Content-Type của request, produces để ràng buộc representation theo Accept, và kiểm tra rõ 406/415. Với SSE hoặc Flux dài, hoàn tất status/header trước khi stream commit; không block hoặc tự subscribe trong controller. Kiểm thử status, header, cookie và media type như một phần của API contract, không chỉ kiểm tra JSON body.
