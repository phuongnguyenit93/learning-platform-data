# ResponseEntity, mã trạng thái, header và phản hồi không có nội dung trong Spring Boot

## Mục tiêu học tập

Khi một HTTP endpoint được gọi, kết quả trả về không chỉ là dữ liệu JSON. **HTTP response** bao gồm **status code**, **response headers** và, khi giao thức cho phép, **response body**. Trong Spring MVC và Spring WebFlux, **ResponseEntity<T>** là cách diễn đạt rõ cả ba phần đó từ controller.

Sau bài này, bạn có thể:

- Phân biệt thành phần status, headers, body và cách chúng được tạo qua ResponseEntity.
- Chọn status chính xác cho GET, POST, PUT/PATCH, DELETE và lỗi thường gặp.
- Dùng các builder ok(), created(), accepted(), noContent(), notFound(), badRequest(), status(), header(), location() và build()/body().
- Hiểu khác biệt **204 No Content**, **200 OK với body rỗng**, **202 Accepted**, **HEAD** và **304 Not Modified**.
- Đặt Location, Content-Type, Cache-Control, ETag, Retry-After hoặc header ứng dụng một cách có chủ đích.
- Trả ResponseEntity<Void> cho trường hợp chỉ cần status/headers.
- Xử lý status phụ thuộc dữ liệu trong WebFlux với Mono<ResponseEntity<T>>.
- Viết và kiểm thử controller Java 17+ bằng MockMvc hoặc WebTestClient; nhận diện lỗi content negotiation, response committed và response body không hợp lệ.

## 1. Response HTTP là hợp đồng giữa server và client

Một response HTTP minh họa:

~~~http
HTTP/1.1 201 Created
Location: /api/items/7
Content-Type: application/json
Cache-Control: no-store

{"id":7,"name":"Notebook"}
~~~

Các phần quan trọng:

| Phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Status code | 201 Created | Kết quả của request theo ngữ nghĩa HTTP. |
| Header | Location: /api/items/7 | Metadata/điều khiển liên quan response hoặc tài nguyên. |
| Header | Content-Type: application/json | Media type của body nếu response có biểu diễn dạng JSON. |
| Header | Cache-Control: no-store | Chỉ thị liên quan lưu trữ response trong cache. |
| Body | JSON của item mới | Dữ liệu/biểu diễn mà client nhận khi status và method cho phép. |

Một response vẫn có thể hợp lệ nếu không có body. Ngược lại, body JSON có nội dung “error” nhưng status 200 có thể khiến client, gateway và hệ thống monitoring ghi nhận request là thành công. **Không dùng body để thay thế cho status code**.

Ví dụ lỗi:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type":"about:blank","title":"Not Found","status":404}
~~~

Body lỗi ở đây chỉ là ví dụ về biểu diễn có cấu trúc; ứng dụng không bắt buộc trả đúng định dạng này ở mọi 404. Điều quan trọng là status 404 phản ánh tài nguyên không được tìm thấy.

## 2. ResponseEntity<T> là gì?

**org.springframework.http.ResponseEntity<T>** là kiểu của Spring Framework biểu diễn HTTP status, headers và một body kiểu T. Nó kế thừa **HttpEntity<T>**, bổ sung thông tin status của response.

So sánh:

| Kiểu trả về của controller | Status | Headers | Body |
|---|---|---|---|
| Một object/record với @RestController | Framework chọn mặc định, thường là 200 khi xử lý thành công | Framework thiết lập theo content negotiation/codec | Object được serialize nếu phù hợp |
| String với @RestController | Thường 200 | Content-Type tùy cấu hình converter | String, không phải view name |
| @ResponseStatus trên handler | Status do annotation quy định | Vẫn có thể do framework/handler tạo | Phụ thuộc kiểu trả về |
| HttpEntity<T> | Thường theo mặc định hoặc điều khiển từ nơi khác | Có | Có |
| ResponseEntity<T> | Được controller quyết định trực tiếp | Được controller thêm hoặc chỉnh | Có thể có |
| ResponseEntity<Void> | Được controller quyết định | Có thể có | Không chứa đối tượng body |

Trong @Controller không có @ResponseBody, việc trả String có thể biểu thị **tên view**; ResponseEntity được nhận diện là kiểu return value riêng. Với @RestController, Spring áp dụng ngữ nghĩa @ResponseBody cho các method, nhưng ResponseEntity vẫn hữu ích vì có thể chỉ rõ status và header.

ResponseEntity cũng **không tự serialize JSON**. Spring MVC dùng HttpMessageConverter; WebFlux dùng HttpMessageWriter/codec thích hợp dựa trên classpath, Content-Type, Accept và Java type.

### Cú pháp cơ bản

~~~java
ResponseEntity<String> ok =
    ResponseEntity.ok("ready");

ResponseEntity<String> accepted =
    ResponseEntity.status(HttpStatus.ACCEPTED)
        .body("job queued");

ResponseEntity<Void> noContent =
    ResponseEntity.noContent().build();

ResponseEntity<Void> notFound =
    ResponseEntity.notFound().build();
~~~

Các đoạn trên minh họa việc tạo response object, không phải các controller method độc lập; cần import ResponseEntity và HttpStatus.

- **body(value)**: tạo ResponseEntity có body.
- **build()**: tạo ResponseEntity không có body object; nên dùng cho status chỉ cần metadata.
- **ResponseEntity.ok(body)**: cách ngắn gọn cho 200 và body.
- **ResponseEntity.status(...).body(...)**: khi status không phải trường hợp builder tiện lợi hoặc cần kết hợp nhiều tùy chỉnh.

## 3. Status code thường dùng trong REST API

### Nhóm 2xx: request thành công

| Status | Ý nghĩa | Tình huống thường gặp |
|---|---|---|
| 200 OK | Request thành công; response có thể chứa biểu diễn tài nguyên hoặc kết quả | GET lấy object, POST xử lý và trả kết quả, PUT trả object đã cập nhật |
| 201 Created | Request tạo ra một hoặc nhiều tài nguyên mới | POST tạo item; nên cung cấp Location khi xác định được URI tài nguyên |
| 202 Accepted | Đã chấp nhận request để xử lý nhưng việc xử lý chưa hoàn tất | Gửi tác vụ vào queue, trả job id/status endpoint |
| 204 No Content | Request hoàn tất thành công và không có response content | DELETE thành công, PUT/PATCH thành công không cần trả object |
| 205 Reset Content | Server yêu cầu client reset giao diện nhập liệu; không có response content | Trường hợp UI đặc biệt, hiếm dùng trong REST thông thường |
| 206 Partial Content | Server trả một phần biểu diễn theo range request hợp lệ | Tải tài nguyên theo byte range |

**200 không phải thay thế mặc định cho mọi thao tác thành công.** Một endpoint tạo tài nguyên nên cân nhắc 201; thao tác bất đồng bộ chưa hoàn thành có thể là 202; cập nhật/xóa không trả body thường chọn 204.

### Nhóm 3xx: redirect hoặc conditional caching

| Status | Ý nghĩa |
|---|---|
| 301 Moved Permanently | Resource được chuyển URI lâu dài theo semantics HTTP. |
| 302 Found | Redirect tạm thời với các quy tắc method có lịch sử tương thích riêng. |
| 303 See Other | Chỉ client lấy tài nguyên khác bằng GET, thường hữu ích sau POST. |
| 304 Not Modified | Kết quả đánh giá conditional GET/HEAD cho thấy có thể dùng biểu diễn cache đã có, nên không truyền body. |
| 307 Temporary Redirect | Redirect tạm thời, giữ method của request. |
| 308 Permanent Redirect | Redirect lâu dài, giữ method của request. |

**201 Created với Location** không phải redirect 3xx. Client có thể dùng Location để biết URI tài nguyên mới; server không yêu cầu tự động chuyển request theo cơ chế redirect.

### Nhóm 4xx: request không thể hoàn thành theo hợp đồng client

| Status | Ý nghĩa thường gặp |
|---|---|
| 400 Bad Request | Request sai định dạng, tham số hoặc dữ liệu không hợp lệ theo cách được server coi là lỗi request. |
| 401 Unauthorized | Cần xác thực hợp lệ; trong HTTP authentication thường đi kèm WWW-Authenticate phù hợp. |
| 403 Forbidden | Server hiểu request nhưng không cho phép thao tác. |
| 404 Not Found | Không tìm thấy tài nguyên hoặc không muốn tiết lộ sự tồn tại, theo ngữ cảnh. |
| 405 Method Not Allowed | Path có handler nhưng method không được hỗ trợ; response cần Allow theo HTTP semantics. |
| 409 Conflict | Trạng thái tài nguyên hiện tại xung đột với yêu cầu cập nhật/tạo. |
| 412 Precondition Failed | Điều kiện If-Match/If-Unmodified-Since không được đáp ứng. |
| 415 Unsupported Media Type | Media type của request không phù hợp với endpoint/reader. |
| 422 Unprocessable Content | Nội dung đúng cú pháp nhưng không thể xử lý theo ngữ nghĩa, khi contract lựa chọn status này. |
| 429 Too Many Requests | Vượt giới hạn tần suất; có thể kèm Retry-After. |

Không chọn status chỉ theo loại exception Java. Cần xem **hợp đồng API** và nguyên nhân nghiệp vụ. Ví dụ khi item không tồn tại là 404, còn khi item tồn tại nhưng bị sửa bởi phiên bản khác có thể là 409 hoặc 412, tùy cách dùng optimistic locking/conditional request.

### Nhóm 5xx: lỗi phía server hoặc downstream

500 Internal Server Error dùng cho lỗi không lường trước ở server; 502 Bad Gateway, 503 Service Unavailable và 504 Gateway Timeout thường xuất hiện tại proxy/gateway hoặc thành phần làm trung gian. Đừng tự biến mọi lỗi downstream thành 400 chỉ để “trả lỗi client”; cần giữ ý nghĩa và không lộ thông tin nhạy cảm.

## 4. Những factory/builder của ResponseEntity cần biết

| API | Kết quả | Ghi nhớ |
|---|---|---|
| ResponseEntity.ok(body) | 200 và body | Nhanh cho GET thành công. |
| ResponseEntity.ok().body(body) | 200 và body | Có thể chèn headers trước body(). |
| ResponseEntity.created(uri).body(body) | 201, Location và body | Đúng ngữ nghĩa tạo tài nguyên. |
| ResponseEntity.created(uri).build() | 201, Location, không body | Hợp lệ khi đã tạo nhưng không cần trả biểu diễn. |
| ResponseEntity.accepted().build() | 202, không body | Job mới được nhận xử lý; nên có thông tin theo dõi nếu cần. |
| ResponseEntity.noContent().build() | 204, không body | Trường hợp thành công không trả nội dung. |
| ResponseEntity.notFound().build() | 404, không body | Tài nguyên không tồn tại và API không cần body lỗi. |
| ResponseEntity.badRequest().build() | 400, không body | Request không hợp lệ, không trả chi tiết. |
| ResponseEntity.status(HttpStatus.CONFLICT).body(error) | 409 và body | Lỗi nghiệp vụ cần biểu diễn có cấu trúc. |
| ResponseEntity.ok().header("X-Trace-Id", id).body(body) | 200, header riêng, body | Dùng metadata ở response header. |
| ResponseEntity.status(code).build() | Status tùy chọn, không body | Cần hiểu HTTP semantics của code. |

Các builder có thể được kết hợp:

~~~java
ResponseEntity<String> response = ResponseEntity
    .ok()
    .header("X-Source", "catalog")
    .cacheControl(CacheControl.noStore())
    .body("ok");
~~~

Cần import **org.springframework.http.CacheControl** và **org.springframework.http.ResponseEntity** cho ví dụ.

### Không nhầm body() và build()

~~~java
ResponseEntity<String> a = ResponseEntity.ok("hello");
// Status 200, body "hello"

ResponseEntity<Void> b = ResponseEntity.ok().build();
// Status 200, không có body object

ResponseEntity<Void> c = ResponseEntity.noContent().build();
// Status 204, không có response content
~~~

Hai trường hợp cuối **không đồng nghĩa**: 200 mô tả thành công với response có thể có nội dung độ dài 0, còn 204 xác nhận không có thêm nội dung cần gửi và bị ràng buộc bởi semantics HTTP khác.

## 5. 204 No Content: response thành công không chứa body

Theo RFC 9110, **204 No Content** có nghĩa server đã hoàn thành request thành công và **không có response content**. Response kết thúc tại phần headers; nó không được mang body hay trailer. Vì vậy:

~~~http
HTTP/1.1 204 No Content
ETag: "item-v2"

~~~

Ví dụ chỉ minh họa headers; các header như Date có thể được server tự thêm. Không tự thêm một dòng JSON, một String rỗng được serialize hoặc byte payload dưới status 204.

Cách trả 204 trong Spring Boot:

~~~java
@DeleteMapping("/api/items/{id}")
public ResponseEntity<Void> delete(@PathVariable long id) {
    service.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

Đây là method minh họa cần đặt trong @RestController và có service thực tế. **Chỉ trả 204 khi nghiệp vụ đã thực hiện như hợp đồng**; nếu service báo không tồn tại hoặc không có quyền, chọn status tương ứng.

### 204 khác response body rỗng thế nào?

| Trường hợp | Có thể có response content? | Ý nghĩa |
|---|---|---|
| 200 OK với body rỗng | Có thể là content dài 0 | Request thành công theo nghĩa 200. |
| 204 No Content | Không | Request thành công nhưng server không gửi content. |
| 205 Reset Content | Không | Client nên reset một document/input view. |
| 304 Not Modified | Không | Client có thể tái sử dụng cached representation sau conditional request. |
| HEAD response | Không | Chỉ headers như của GET tương ứng, không có content. |

Không trả 204 cho “đang xử lý chưa xong” chỉ vì chưa có dữ liệu để trả; khi đó 202 Accepted có thể phản ánh đúng hơn.

Không tự thiết lập **Content-Length: 0** trên 204. RFC 9110 quy định các giới hạn riêng với header này ở response 204; để HTTP server/framework xử lý framing. Khi dùng ResponseEntity.noContent().build(), tránh can thiệp trực tiếp vào bytes hoặc HTTP framing.

### 204 trong Spring WebFlux

Với Mono<Void> trong reactive controller, pipeline có thể hoàn tất mà không phát giá trị. Điều đó **không phải quy tắc tự động chuyển status sang 204**. Hãy chọn status rõ ràng:

~~~java
@DeleteMapping("/api/items/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
    return service.deleteById(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

Đây là minh họa với service.deleteById(id) trả Publisher biểu thị thao tác xóa; nếu muốn 404 cho id không tồn tại, service cần cung cấp thông tin hoặc phát một lỗi được xử lý tương ứng. Không tự giả định Mono.empty() có nghĩa “không tìm thấy”.

## 6. 201 Created và header Location

Khi POST tạo mới tài nguyên, nên trả **201 Created** và, nếu xác định được URI, cung cấp **Location**.

Ví dụ:

~~~java
@PostMapping("/api/items")
public ResponseEntity<Item> create(@RequestBody CreateItemRequest request) {
    Item created = service.create(request);

    URI location = URI.create("/api/items/" + created.id());

    return ResponseEntity.created(location).body(created);
}
~~~

URI trong ví dụ là **relative URI reference**. HTTP Location cho phép URI reference tương đối theo RFC 9110; nếu API contract yêu cầu absolute URL, cần xây URL từ request/gateway configuration phù hợp, đặc biệt khi ứng dụng đứng sau reverse proxy.

Không ghép host công khai bằng cách hardcode server.port hoặc lấy nguyên Host header không qua xác thực/trusted proxy. Những hệ thống chạy sau ingress có thể có scheme, host và port public khác hoàn toàn backend.

Dùng created(location).build() nếu server muốn gửi 201 và Location nhưng không có body. Dùng created(location).body(created) nếu muốn gửi representation mới nhất của item.

### 201 và 202 không giống nhau

- **201 Created**: thao tác tạo tài nguyên đã hoàn tất theo hợp đồng.
- **202 Accepted**: request đã được nhận nhưng xử lý chưa hoàn tất; response nên cung cấp thông tin theo dõi công việc nếu cần.

Ví dụ gửi job xử lý bất đồng bộ:

~~~java
@PostMapping("/api/reports")
public ResponseEntity<JobReceipt> submit(@RequestBody ReportRequest request) {
    JobReceipt receipt = queue.submit(request);
    return ResponseEntity.accepted()
        .header("Location", "/api/jobs/" + receipt.id())
        .body(receipt);
}
~~~

Đây là minh họa dùng service queue và DTO đã được định nghĩa trong ứng dụng thực tế. Nếu dùng 202, không được khẳng định báo cáo đã chạy xong khi mới chỉ đưa vào queue.

## 7. 404 Not Found và Optional: chọn status theo dữ liệu

Một route tồn tại không bảo đảm dữ liệu bên dưới tồn tại. Khi tìm item theo ID:

~~~java
@GetMapping("/api/items/{id}")
public ResponseEntity<Item> findOne(@PathVariable long id) {
    return repository.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

Ví dụ trên giả sử repository.findById(id) trả **Optional<Item>**. Nếu tìm được, 200 + JSON body. Nếu không, 404 + no body.

Spring Framework cũng hỗ trợ tạo ResponseEntity từ Optional trong các phiên bản có factory tương ứng, nhưng cách viết map/orElseGet ở trên giúp thể hiện rõ hai nhánh và có thể tùy chỉnh header/body lỗi.

Không mặc định xem:

- Optional.empty() là HTTP 404 nếu controller chưa chuyển đổi nó thành status thích hợp.
- Một null trả về từ controller là HTTP 204.
- HTTP 404 phải luôn có JSON body hoặc không bao giờ có body.

Cả 404 với body lỗi có cấu trúc và 404 không body đều có thể hợp lệ; quan trọng là thống nhất API contract.

## 8. ResponseEntity<Void>, Void, void và kiểu phản hồi rỗng

### ResponseEntity<Void>

Dùng khi bạn chỉ cần status và headers:

~~~java
@PutMapping("/api/items/{id}")
public ResponseEntity<Void> update(
        @PathVariable long id,
        @RequestBody UpdateItemRequest request) {

    service.update(id, request);

    return ResponseEntity.noContent().build();
}
~~~

**Void** là kiểu generic thể hiện “không có object body”, giúp người đọc và compiler hiểu contract.

### Một method void với @ResponseStatus

Có thể trả 204 bằng:

~~~java
@DeleteMapping("/api/items/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
    service.delete(id);
}
~~~

Cách này phù hợp khi status luôn cố định và lỗi được xử lý qua exception handler. Khi status, headers hoặc body khác nhau tùy kết quả, ResponseEntity thường trực quan hơn.

### Trả về null không phải giải pháp thiết kế

Dùng return null ở controller không thể hiện rõ HTTP semantics và có thể phụ thuộc return value handler/framework. Nếu endpoint không có body, hãy trả ResponseEntity.noContent().build() hoặc dùng @ResponseStatus(HttpStatus.NO_CONTENT) có chủ đích.

### Mã trạng thái lỗi không có body

Bạn cũng có thể trả:

~~~java
return ResponseEntity.badRequest().build();
~~~

Điều đó khác với 204: đây là status **400**, không phải một lần xử lý thành công. Không dùng “body rỗng” làm tiêu chí phân biệt thành công và thất bại.

## 9. Thiết lập response headers đúng cách

ResponseEntity cho phép thêm headers bằng builder:

~~~java
ResponseEntity<String> response = ResponseEntity
    .ok()
    .header("X-Trace-Id", "req-123")
    .header("X-Source", "web-runtime")
    .body("done");
~~~

Hoặc tạo HttpHeaders rồi dùng headers(...):

~~~java
HttpHeaders headers = new HttpHeaders();
headers.set("X-Trace-Id", "req-123");

ResponseEntity<String> response =
    ResponseEntity.ok().headers(headers).body("done");
~~~

Cần import HttpHeaders và ResponseEntity.

### Header phổ biến

| Header | Công dụng | Lưu ý |
|---|---|---|
| Content-Type | Media type của body | Nên để HTTP message converter/codec quyết định khi có thể. |
| Location | URI tham chiếu tài nguyên mới hoặc redirect | Dùng đúng ngữ nghĩa 201/3xx; có thể relative reference. |
| Cache-Control | Chính sách cache | no-store thường phù hợp với dữ liệu không được phép lưu. |
| ETag | Validator của representation | Phối hợp conditional requests để tránh tải lại hoặc chống lost update. |
| Last-Modified | Thời điểm sửa đổi resource | Dùng khi có nguồn thời gian đáng tin cậy. |
| Vary | Cho cache biết request headers nào làm thay đổi representation | Ví dụ Vary: Accept-Language khi response khác ngôn ngữ. |
| Retry-After | Gợi ý thời điểm/độ trễ thử lại | Có thể dùng với 429/503; không thay thế rate-limit policy. |
| WWW-Authenticate | Thông tin challenge xác thực HTTP | Quan trọng cho một số response 401. |
| Content-Disposition | Cách gợi ý download/tên file | Phải xử lý an toàn filename từ input. |
| Allow | Danh sách method được hỗ trợ khi liên quan tới 405 | Thường do framework quản lý theo route. |

**Không nên tự đặt Content-Length** khi dùng JSON serialization, compression, transfer encoding hay streaming; kích thước thực tế có thể chỉ được biết ở thời điểm ghi. Để framework/server kiểm soát framing.

### Header đặc biệt và an toàn

- Đừng phản chiếu header do client gửi vào Location/Content-Disposition mà không validate.
- Không đưa access token, session cookie hoặc dữ liệu cá nhân vào header trace hay log.
- Không tự tạo CORS policy bằng vài response headers rời rạc nếu ứng dụng đã có Spring Security/CORS config; các preflight request có cơ chế riêng.
- Không dùng status 200 cùng header thông báo lỗi và kỳ vọng HTTP client tự hiểu đây là lỗi.

## 10. Cache-Control, ETag và 304 Not Modified

Caching có thể giảm băng thông và latency khi client đã có representation phù hợp. Hai khái niệm quan trọng:

- **Cache-Control** hướng dẫn chính sách cache.
- **ETag** là validator của một representation; client có thể gửi **If-None-Match** để kiểm tra tài nguyên đã đổi hay chưa.

Một response GET có ETag:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "item-7-v3"
Cache-Control: private, max-age=60

{"id":7,"name":"Notebook"}
~~~

Lần tiếp theo client có thể gửi:

~~~http
GET /api/items/7 HTTP/1.1
If-None-Match: "item-7-v3"
~~~

Khi điều kiện phù hợp theo HTTP cache validation, server có thể phản hồi **304 Not Modified** với headers phù hợp và **không truyền body**. Client sử dụng representation đã cache.

**304 không có nghĩa tài nguyên đã được cập nhật thành công.** Nó có ý nghĩa trong conditional request, chủ yếu GET/HEAD. Không trả 304 để thay cho 204 trong một DELETE/PUT thành công.

Ví dụ ResponseEntity 200 với ETag:

~~~java
ResponseEntity<Item> response = ResponseEntity
    .ok()
    .eTag("\"item-7-v3\"")
    .cacheControl(CacheControl.maxAge(Duration.ofSeconds(60)))
    .body(item);
~~~

Trong Java cần imports **java.time.Duration** và **org.springframework.http.CacheControl**. Spring MVC và WebFlux có hỗ trợ HTTP conditional request ở các điểm thích hợp; để có 304 đúng, cần kiểm tra điều kiện và lifecycle của framework đang dùng, không được trả 304 chỉ vì có ETag.

### If-Match và 412 Precondition Failed

Khi cập nhật với optimistic concurrency, client có thể gửi If-Match để chỉ cho phép ghi nếu ETag hiện tại khớp. Nếu điều kiện không thỏa, **412 Precondition Failed** thường là status phù hợp. Đó là một mục đích khác với If-None-Match dùng để giảm tải GET.

Không dùng ETag giả như một ID không thay đổi qua các lần sửa nếu mục tiêu là kiểm tra version của representation. ETag cần phản ánh phiên bản dữ liệu hoặc representation theo chiến lược của API.

## 11. Ví dụ Spring Boot MVC hoàn chỉnh, Java 17+

Ví dụ chạy được với **Spring Boot 3.x, Java 17+**, dependency **spring-boot-starter-web** và JSON support do starter cung cấp. Với Spring Boot 4.x, starter MVC thích hợp có thể có tên **spring-boot-starter-webmvc**; chọn theo major version thực tế.

Để tập trung vào ResponseEntity, dữ liệu được lưu trong ConcurrentHashMap trong bộ nhớ. Đây không phải persistence layer sản xuất.

### 11.1. Application class

File: src/main/java/com/example/responses/ResponseApplication.java

~~~java
package com.example.responses;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResponseApplication.class, args);
    }
}
~~~

### 11.2. Model

File: src/main/java/com/example/responses/Item.java

~~~java
package com.example.responses;

public record Item(long id, String name) {
}
~~~

File: src/main/java/com/example/responses/CreateItemRequest.java

~~~java
package com.example.responses;

public record CreateItemRequest(String name) {
}
~~~

### 11.3. Controller trả nhiều status

File: src/main/java/com/example/responses/ItemController.java

~~~java
package com.example.responses;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final Map<Long, Item> items = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    @PostMapping
    public ResponseEntity<Item> create(
            @RequestBody CreateItemRequest request) {

        if (request.name() == null || request.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = sequence.incrementAndGet();
        Item created = new Item(id, request.name().trim());
        items.put(id, created);

        URI location = URI.create("/api/items/" + id);

        return ResponseEntity
            .created(location)
            .body(created);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Item> get(@PathVariable long id) {
        Item found = items.get(id);

        if (found == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity
            .ok()
            .header("X-Source", "in-memory-demo")
            .body(found);
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(
            @PathVariable long id,
            @RequestBody CreateItemRequest request) {

        if (!items.containsKey(id)) {
            return ResponseEntity.notFound().build();
        }
        if (request.name() == null || request.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        items.put(id, new Item(id, request.name().trim()));

        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        Item removed = items.remove(id);

        if (removed == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.noContent().build();
    }

    @GetMapping("/ping")
    public ResponseEntity<Void> ping() {
        return ResponseEntity
            .status(HttpStatus.OK)
            .header("X-Health", "ready")
            .build();
    }
}
~~~

Controller thể hiện các trường hợp:

- POST body hợp lệ: **201 Created**, **Location: /api/items/{id}**, JSON body của item mới.
- POST body có name rỗng/null: **400 Bad Request**, không body trong ví dụ.
- GET item tồn tại: **200 OK**, header X-Source, JSON body.
- GET item không tồn tại: **404 Not Found**, không body.
- PUT item tồn tại: **204 No Content**, không body.
- PUT item không tồn tại: **404 Not Found**.
- DELETE item tồn tại: **204 No Content**.
- DELETE item không tồn tại: **404 Not Found**.
- GET /api/items/ping: **200 OK**, header X-Health, không body — để phân biệt với 204.

Ứng dụng này có một logic ghi cập nhật không atomic giữa containsKey và put, chỉ phù hợp minh họa. Trong dự án thực tế, hãy dùng transaction và optimistic locking khi concurrency có thể gây xung đột.

### 11.4. Gọi API và kiểm tra response

Chạy Maven Wrapper từ root project:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows với Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Tạo tài nguyên:

~~~bash
curl -i -X POST http://localhost:8080/api/items -H "Content-Type: application/json" -d '{"name":"Notebook"}'
~~~

Với ứng dụng mới khởi động, item đầu tiên có id 1. Response dự kiến có status 201, header **Location: /api/items/1** và JSON tương đương:

~~~json
{"id":1,"name":"Notebook"}
~~~

Đọc item:

~~~bash
curl -i http://localhost:8080/api/items/1
~~~

Response dự kiến 200 cùng header X-Source: in-memory-demo và JSON body của item.

Cập nhật item:

~~~bash
curl -i -X PUT http://localhost:8080/api/items/1 -H "Content-Type: application/json" -d '{"name":"Updated Notebook"}'
~~~

Response dự kiến 204, **không có response body**.

Xóa item:

~~~bash
curl -i -X DELETE http://localhost:8080/api/items/1
~~~

Lần xóa đầu 204; khi xóa lại hoặc GET /api/items/1 sau khi xóa, response là 404 theo logic controller.

So sánh 200 rỗng:

~~~bash
curl -i http://localhost:8080/api/items/ping
~~~

Status 200 và header X-Health: ready, không có body object. Không cần đổi nó thành 204 nếu hợp đồng endpoint muốn diễn đạt status 200.

**Không so sánh nguyên văn toàn bộ các response headers** trong ví dụ vì Date, Server, transfer/caching headers hoặc thông tin từ proxy có thể khác giữa runtime/phiên bản.

## 12. Kiểm thử MVC với MockMvc

Trong Spring Boot 3.x, thêm **spring-boot-starter-test** ở test scope nếu chưa có, rồi dùng MockMvc để kiểm tra status, headers và body. Ví dụ bên dưới kiểm tra đường đi POST → GET → PUT → DELETE trong **một phương thức test**, vì ứng dụng demo dùng in-memory state bắt đầu rỗng.

File: src/test/java/com/example/responses/ItemControllerTest.java

~~~java
package com.example.responses;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void statusHeadersAndEmptyResponses() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string("Location", "/api/items/1"))
            .andExpect(jsonPath("$.id").value(1));

        mvc.perform(get("/api/items/1"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Source", "in-memory-demo"))
            .andExpect(jsonPath("$.name").value("Notebook"));

        mvc.perform(put("/api/items/1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Updated Notebook\"}"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));

        mvc.perform(delete("/api/items/1"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));

        mvc.perform(get("/api/items/1"))
            .andExpect(status().isNotFound());
    }
}
~~~

Kiểm thử trên giả định context Spring Boot được tạo một lần và không có test khác sinh item trước đó. Trong dự án có nhiều test chạy song song hoặc cùng context, không nên hardcode id 1: đọc ID từ Location/JSON và dùng id thực tế, hoặc reset state đúng cách.

Có thể kiểm tra body rỗng cho 200 riêng:

~~~java
mvc.perform(get("/api/items/ping"))
    .andExpect(status().isOk())
    .andExpect(header().string("X-Health", "ready"))
    .andExpect(content().string(""));
~~~

Như vậy test xác minh rõ **200 với content rỗng** khác **204 không cho content**. Spring Boot 4.x có các thay đổi package test auto-configuration; dùng import tương ứng với BOM/major version của ứng dụng.

## 13. ResponseEntity trong Spring WebFlux

Spring WebFlux cũng sử dụng ResponseEntity, nhưng cho phép status/headers/body được xác định ở những thời điểm khác nhau vì các publisher có thể bất đồng bộ.

Các kiểu trả về phổ biến:

| Kiểu | Status và headers được xác định khi nào? | Body |
|---|---|---|
| ResponseEntity<T> | Ngay khi controller trả entity | Object T được xử lý bởi codec |
| ResponseEntity<Mono<T>> | Entity đã có status/headers, body được phát sau | 0 hoặc 1 value bất đồng bộ |
| ResponseEntity<Flux<T>> | Status/headers đã có trước, body có thể stream sau | Nhiều value |
| Mono<ResponseEntity<T>> | Sau khi Mono phát entity | Status/headers/body phụ thuộc kết quả async |
| Mono<ResponseEntity<Flux<T>>> | Entity được phát async; Flux body stream tiếp sau | Dùng cho trường hợp nâng cao |

### Chọn status theo kết quả asynchronous

Ví dụ service dùng repository reactive:

~~~java
@GetMapping("/api/items/{id}")
public Mono<ResponseEntity<Item>> get(@PathVariable long id) {
    return repository.findById(id)
        .map(item -> ResponseEntity.ok(item))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Đây là method minh họa bên trong WebFlux @RestController; repository.findById trả Mono<Item>.

- Khi Mono phát Item, endpoint trả 200 và body.
- Khi Mono hoàn tất empty, endpoint trả 404 và không có body.

**Quan trọng:** Nếu thay bằng ResponseEntity.ok(repository.findById(id)), status 200 được quyết định **ngay**, trước khi biết Publisher có dữ liệu hay không. Mono body rỗng không tự động biến 200 thành 404. Muốn status thay đổi dựa trên kết quả async, thường nên trả **Mono<ResponseEntity<T>>**.

### Xóa không có body trong reactive service

Giả sử service.deleteById(id) trả Mono<Void> và nghiệp vụ quy định việc xóa đã hoàn tất thành công khi Mono hoàn tất bình thường:

~~~java
@DeleteMapping("/api/items/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
    return service.deleteById(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

Đây là ví dụ về hợp đồng **success => 204**. Nếu muốn 404 khi id không tồn tại, cần để service phân biệt kết quả: trả boolean hoặc phát lỗi tương ứng, rồi map sang ResponseEntity.notFound().build(). Mono<Void> hoàn tất rỗng không cung cấp đủ thông tin để tự suy ra 404.

### Status và response committed khi streaming

Khi ResponseEntity<Flux<T>> cung cấp body streaming, server có thể gửi headers/status trước khi stream kết thúc. Nếu stream lỗi sau khi response đã committed, framework không thể luôn thay status từ 200 thành 500 hoặc gửi một JSON error mới.

Với server-sent events hoặc NDJSON, cần thiết kế cách báo lỗi theo giao thức streaming hoặc đóng kết nối hợp lý, thay vì dựa vào việc đổi HTTP status ở cuối stream.

### Kiểm thử WebFlux với WebTestClient

Một phép kiểm tra minh họa:

~~~java
webTestClient.get()
    .uri("/api/items/7")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody().isEmpty();
~~~

Trong test khác, khi repository đã có item:

~~~java
webTestClient.get()
    .uri("/api/items/7")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    )
    .expectBody()
    .jsonPath("$.id").isEqualTo(7);
~~~

Hai đoạn này cần WebTestClient, MediaType, mock/test fixture phù hợp; chúng là ví dụ phương thức test chứ không phải file độc lập. Cũng có thể dùng WebTestClient để kiểm tra status 204 và không body với expectBody().isEmpty().

## 14. Content-Type, Accept và content negotiation

Khi controller trả body, framework chọn converter/codec theo kiểu Java, **Accept** mà client gửi, **produces** của mapping và các media type có thể viết.

Ví dụ controller:

~~~java
@GetMapping(
    path = "/api/items/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<Item> get(@PathVariable long id) {
    // ...
}
~~~

Đoạn code trên chỉ minh họa annotation; không chạy độc lập vì method body bị lược để tập trung vào produces. Nếu client chỉ chấp nhận XML nhưng endpoint/codec không thể cung cấp XML, ứng dụng có thể trả 406 Not Acceptable.

**Content-Type** mô tả body request mà client gửi. Một POST consumes application/json nhưng client gửi text/plain có thể trả 415 Unsupported Media Type.

Khi response không có body, đừng tự thiết lập Content-Type: application/json chỉ vì controller nằm trong REST API. Status 204 không gửi representation body để client decode; cố gắng serialize một object dưới 204 là thiết kế mâu thuẫn.

Các header do framework tạo có thể phụ thuộc vào Spring MVC/WebFlux, Jackson, message converter, codec và cấu hình content negotiation. Hãy test status/media type/body theo **hợp đồng**, không test mọi header phụ mặc định.

## 15. Error response: dùng status, không chỉ field trong JSON

Một mẫu sai:

~~~java
return ResponseEntity.ok(
    Map.of("success", false, "error", "Not found")
);
~~~

Đoạn này trả **HTTP 200**, dù body báo lỗi. Với client HTTP chung, 200 thường được coi là response thành công.

Một mẫu rõ ngữ nghĩa hơn:

~~~java
return ResponseEntity
    .status(HttpStatus.NOT_FOUND)
    .body(Map.of(
        "code", "ITEM_NOT_FOUND",
        "message", "Item not found"
    ));
~~~

Đây là đoạn minh họa dùng Map và HttpStatus. Để duy trì API thống nhất, có thể tạo một DTO lỗi hoặc dùng **ProblemDetail** theo chuẩn RFC 9457 và API của Spring Framework 6+. Đừng tạo các body lỗi tùy tiện khác format ở từng controller.

Trong dự án có nhiều endpoint, xử lý lỗi tập trung thường tiện hơn:

- **@RestControllerAdvice** và **@ExceptionHandler** cho lỗi nghiệp vụ.
- **ResponseStatusException** trong MVC/WebFlux khi cần phát status trong reactive chain hoặc service adapter.
- Error-handling infrastructure do Spring Boot cung cấp, với chính sách che giấu thông tin nhạy cảm.

Chọn 401/403 theo security semantics, 404 cho tài nguyên không tồn tại, 409 cho conflict, 500 khi lỗi server. Không catch Throwable rồi trả 200, và không expose stacktrace trong response production.

## 16. Lỗi thường gặp khi dùng ResponseEntity

### Trả JSON dưới status 204

Status 204 không được chứa response content. Dùng noContent().build() chứ không cố gửi body JSON rỗng hay thông báo thành công.

### Trả 200 cho request tạo resource nhưng contract yêu cầu 201

Client có thể phụ thuộc Location và status để lấy resource mới. Dùng created(location) khi hành động tạo đã hoàn tất, nếu đúng thiết kế API.

### Dùng 202 cho job đã hoàn tất ngay lập tức

202 diễn đạt accepted và xử lý chưa hoàn tất. Nếu tạo thành công và tài nguyên đã tồn tại, 201 hoặc 200 có thể thích hợp hơn.

### Nhầm response body empty với 404 trong WebFlux

Mono.empty() chỉ là completion không có value; nó không tự nói rằng resource không tồn tại. Dùng switchIfEmpty/map/defaultIfEmpty và trả Mono<ResponseEntity<T>> hoặc lỗi HTTP phù hợp.

### Lạm dụng new ResponseEntity<>(...)

Constructor của ResponseEntity vẫn có chỗ dùng, nhưng builder như ok(), created(), noContent() và status() thường dễ đọc, giảm nguy cơ truyền sai status/header/body.

### Gửi Location không khớp route thực

Ví dụ resource nằm dưới /api/items/{id} nhưng server đặt Location thành /items/{id}. Client sẽ theo đường dẫn sai. Với context path/gateway prefix, cần xây URI theo public routing contract, không chỉ concat hostname nội bộ.

### Tự đặt Content-Length ở response có JSON/streaming

Framework có thể nén, encode hoặc stream khác kích thước bạn tưởng. Không tự đặt Content-Length nếu không thực sự làm chủ representation và framing.

### Tưởng 304 là một phản hồi DELETE thành công

304 dành cho conditional retrieval/caching. DELETE/PUT thành công không có body thường dùng 204.

### Dùng HEAD nhưng kỳ vọng JSON body

HEAD trả headers, không có response content. Nếu cần JSON, gọi GET theo API contract.

### Ghi status sau khi response đã committed

Khi headers/body đã gửi, không thể bảo đảm sửa status. Trong WebFlux streaming, phải phân biệt lỗi trước commit và lỗi sau commit.

### Không test nhánh 404/409/400

Một happy-path test 200 chưa đủ. Trước khi deploy, kiểm tra mỗi nhóm status được dùng, media type, body rỗng, Location, caching, lỗi validation, retry và bảo mật.

### Gắn dữ liệu người dùng thô vào response headers

Header values có quy tắc định dạng và có thể được đưa vào redirect/caching/log. Validate dữ liệu, tránh CR/LF injection và không lộ token hoặc thông tin nhạy cảm.

## 17. Checklist thiết kế API

Khi thêm một endpoint mới, hãy trả lời:

1. HTTP method nào phù hợp: GET, POST, PUT, PATCH hay DELETE?
2. Tài nguyên đã được tạo/chỉnh sửa/xóa thành công chưa hay mới nhận xử lý?
3. Status thành công là 200, 201, 202 hay 204? Có thực sự cần body không?
4. Nếu tạo resource, có Location đúng URI tài nguyên không?
5. Nếu không tìm thấy, response 404 có cần ProblemDetail/body lỗi thống nhất không?
6. Nếu có cạnh tranh cập nhật, có dùng ETag/If-Match và 412 không?
7. Content-Type/Accept có khớp converter/codec thực tế không?
8. Response có cần Cache-Control, ETag, Vary, Retry-After hoặc trace header không?
9. Có proxy/gateway thay host, scheme, port, prefix không?
10. Nếu trả Flux streaming, header/status có thể commit trước khi stream xong không?
11. Kiểm thử có xác nhận response body **thực sự rỗng** khi trả 204 không?
12. Test có bao phủ status của cả nhánh lỗi và an toàn header không?

Một API tốt không nhất thiết dùng tất cả các loại status/header, nhưng mỗi loại đã chọn phải có ý nghĩa nhất quán, có tài liệu và được kiểm thử.

## 18. Câu hỏi tự kiểm tra

**Câu 1:** ResponseEntity<T> có những thành phần nào mà object thông thường không điều khiển rõ bằng kiểu trả về?  
**Câu 2:** POST đã tạo item mới, muốn trả Location và JSON body: chọn builder nào?  
**Câu 3:** DELETE thành công không có body: chọn 200 hay 204?  
**Câu 4:** 200 với body zero-length có giống 204 không?  
**Câu 5:** HEAD và 304 có được gửi response body không?  
**Câu 6:** WebFlux repository.findById trả Mono.empty(), ResponseEntity.ok(mono) có tự chuyển thành 404 không?  
**Câu 7:** Khác biệt giữa ResponseEntity<Mono<Item>> và Mono<ResponseEntity<Item>> là gì?  
**Câu 8:** Header nào nên đưa URI tài nguyên mới sau POST 201?  
**Câu 9:** Header nào liên quan đến kiểm tra cache bằng If-None-Match?  
**Câu 10:** Vì sao không nên tự đặt Content-Length khi ghi JSON/Flux?  
**Câu 11:** Với optimistic concurrency, If-Match không phù hợp có thể dẫn tới status nào?  
**Câu 12:** Khi một Flux đã truyền một phần body rồi lỗi, có thể đổi HTTP status đã gửi không?

### Đáp án

1. Status, response headers và body một cách có chủ đích.
2. ResponseEntity.created(location).body(created).
3. Thường 204 No Content khi contract quy định thành công không trả nội dung.
4. Không; 204 cấm content và thể hiện semantics riêng.
5. Không; HEAD và 304 không có response content.
6. Không; status của ResponseEntity đã là 200. Cần map dữ liệu sang Mono<ResponseEntity<Item>> hoặc xử lý missing rõ ràng.
7. Kiểu đầu có status/headers ngay, body bất đồng bộ; kiểu sau cho phép xác định status/headers theo kết quả bất đồng bộ.
8. Location.
9. ETag.
10. Codec/compression/streaming có thể quyết định bytes lúc ghi; đặt sai framing gây lỗi cho client.
11. 412 Precondition Failed.
12. Không thể rút lại headers đã commit; xử lý lỗi streaming bằng cơ chế phù hợp.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework — ResponseEntity trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): xử lý status, headers và body trong Servlet MVC.
- [Spring Framework — ResponseEntity trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): các kiểu ResponseEntity<Publisher> và Publisher<ResponseEntity>.
- [Spring Framework — ResponseEntity API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html): builder, các factory method và getters.
- [Spring Framework — HttpHeaders API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpHeaders.html): header API và giá trị liên quan.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse và exception handling.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử status, headers và response content.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP trong WebFlux.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ý nghĩa status 200/201/202/204/205/304, HEAD, Location, ETag và điều kiện không có response content.
