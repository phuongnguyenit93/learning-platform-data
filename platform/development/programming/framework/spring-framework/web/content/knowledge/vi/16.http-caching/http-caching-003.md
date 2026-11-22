# If-None-Match, If-Modified-Since và phản hồi 304 trong Spring MVC

## 1. Mục tiêu

Một trang web hoặc REST client có thể đã tải bản JSON, ảnh, tài liệu hoặc HTML của một URL. Nếu tài nguyên **chưa đổi**, tải lại toàn bộ bytes là lãng phí băng thông. HTTP giải quyết việc này bằng **conditional requests**: server cung cấp **validator** (`ETag`, `Last-Modified`); lần sau client gửi điều kiện (`If-None-Match`, `If-Modified-Since`); server kiểm tra phiên bản hiện hành và có thể trả **304 Not Modified**, không gửi lại response content.

Bài học này giải thích đầy đủ cơ chế HTTP và cách Spring MVC 6.x thực hiện. Học xong, bạn có thể:

- Phân biệt **cache freshness** (`Cache-Control`) với **revalidation** (`If-None-Match`/`If-Modified-Since`).
- Hiểu `ETag` mạnh/yếu, `Last-Modified`, định dạng HTTP-date và độ chính xác thời gian.
- Xác định đúng thứ tự ưu tiên khi **cả hai điều kiện** xuất hiện; xử lý `If-None-Match: *`, nhiều tag, tag không khớp và thời gian cũ/mới.
- Giải thích **304 khác 200 và 204**, 304 không có message body, và vì sao cache vẫn có thể hiển thị response 200 đã lưu.
- Dùng `ResponseEntity.eTag(...).lastModified(...).cacheControl(...)` và `WebRequest.checkNotModified(...)` trong Spring MVC.
- Kiểm thử các tổ hợp bằng **MockMvc**, gọi `curl` để xem cả status/header/body, nhận diện cache proxy/CDN/CORS.
- Tránh các lỗi nguy hiểm khi cache dữ liệu có authentication, nhiều language/content encodings, khi file đổi và khi dùng `ShallowEtagHeaderFilter`.

**Phạm vi:** HTTP/1.1, HTTP/2 semantics theo **RFC 9110 và RFC 9111**; Java 17+, **Spring Boot 3.x / Spring Framework 6.x / Spring MVC Servlet stack**. Không nhầm với HTTP caching trong WebFlux hoặc cache nội bộ `@Cacheable`.

## 2. Luồng HTTP cache revalidation: 200 trước, 304 sau

### 2.1. Lần truy cập đầu tiên

Giả sử client gửi:

~~~http
GET /api/books/7 HTTP/1.1
Host: example.com
Accept: application/json
~~~

Server trả representation hiện hành cùng validator:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=300
ETag: "book-7-v3"
Last-Modified: Wed, 15 Jan 2025 10:30:00 GMT

{"id":7,"title":"HTTP caching","version":3}
~~~

Trong ví dụ, `ETag` là chuỗi trong **dấu nháy kép** theo cú pháp entity tag; `Last-Modified` là **HTTP-date theo GMT**. `Cache-Control: private, max-age=300` cho phép private cache như browser coi representation tươi trong khoảng năm phút, nhưng không cho shared cache dùng cho nhiều người. Thời gian thực tế còn tùy response/request directives và quy tắc HTTP caching.

Client lưu **body JSON + metadata cache** nếu các điều kiện lưu trữ cho phép.

### 2.2. Khi cache cần kiểm tra lại

Sau khi response hết độ tươi (hoặc client yêu cầu revalidate), client có thể gửi:

~~~http
GET /api/books/7 HTTP/1.1
Host: example.com
If-None-Match: "book-7-v3"
If-Modified-Since: Wed, 15 Jan 2025 10:30:00 GMT
~~~

Nếu phiên bản vẫn là `"book-7-v3"`, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "book-7-v3"
Last-Modified: Wed, 15 Jan 2025 10:30:00 GMT
Cache-Control: private, max-age=300

~~~

**Không có body mới.** Client/cache dùng lại **body đã lưu từ 200 trước đó**, đồng thời cập nhật những metadata mà HTTP cho phép từ response 304. 304 **không** có nghĩa resource rỗng, không phải mã lỗi và không phải hành động sửa đổi thất bại.

Nếu resource đã thay đổi, ví dụ version 4, server trả **200 OK**, ETag mới và body mới:

~~~http
HTTP/1.1 200 OK
ETag: "book-7-v4"
Content-Type: application/json

{"id":7,"title":"HTTP caching - revised","version":4}
~~~

Các message ở trên là mô phỏng tối thiểu; server/proxy thực tế có thể thêm `Date`, `Vary` và headers khác.

### 2.3. Sơ đồ quyết định

~~~text
Client có cache representation?
     |
     +-- Chưa -> GET thường -> 200 + body + validators (nếu có)
     |
     +-- Có và còn fresh -> có thể dùng cache, không gửi request
     |
     +-- Cần revalidate -> GET + If-None-Match / If-Modified-Since
                                    |
                                    +-- Validator khớp -> 304, không body
                                    |                      |
                                    |                      +-- tái sử dụng body cũ
                                    |
                                    +-- Resource đã đổi -> 200 + body mới
~~~

Có thể request buộc server hoặc cache kiểm tra lại dù bản cached chưa thật sự hết hạn (ví dụ reload/khác cache directives). Ngược lại, nếu cache còn fresh thì **không nhất thiết có request network** để thấy 304.

## 3. ETag là gì: phiên bản của representation, không phải token bảo mật

**ETag (entity tag)** là validator cho một **selected representation** của resource. Nó có dạng:

~~~http
ETag: "book-7-v3"
~~~

hoặc weak ETag:

~~~http
ETag: W/"book-7-v3"
~~~

- **Strong ETag** (`"abc"`) có ý nghĩa so sánh mạnh, phù hợp khi cần bảo đảm representation data là đồng nhất theo yêu cầu HTTP.
- **Weak ETag** (`W/"abc"`) chỉ báo tương đương về ngữ nghĩa trong phạm vi đã định; có thể không tương đương từng byte.
- **`If-None-Match` dùng phép so sánh weak** theo RFC 9110: weak/strong tags có opaque value tương ứng có thể được coi là khớp cho việc revalidate GET/HEAD.
- **`If-Match` dùng strong comparison** (thường cho optimistic concurrency khi update), không tự mang semantics giống `If-None-Match`.
- ETag phải đúng với **representation** trả về. Nếu cùng URL có các biến thể khác nhau theo `Accept-Language`, `Accept-Encoding`, content negotiation, quyền người dùng hoặc query parameters, chiến lược ETag cần phản ánh biến thể và dùng `Vary` phù hợp.

ETag **không phải** chữ ký điện tử, access token, checksum bảo mật hay bằng chứng người dùng được phép đọc resource. Không truyền một secret vào ETag, không sử dụng giá trị ETag làm authorization.

### 3.1. Nên tạo ETag thế nào?

Một số lựa chọn:

1. **Version đã lưu** ở database (ví dụ `bookId=7, version=3`), nếu version thay đổi mỗi lần nội dung representation thay đổi.
2. **Hash content** của representation sau khi serialize, nếu cần một validator gắn với bytes thật; tính hash trên mỗi request có thể tốn CPU.
3. **Version của asset build** hoặc object-storage version ID, phù hợp với static assets/immutable documents.

Ví dụ minh họa version-based:

~~~java
String etag = "\"book-" + book.id() + "-v" + book.version() + "\"";
~~~

Đây là **một dòng code minh họa**, giả sử `book` là DTO có `id()` và `version()`. ETag version-based chỉ đúng nếu **mọi thay đổi ảnh hưởng representation làm version đổi**. Nếu cùng version nhưng JSON biến đổi theo user/locale/format, dùng chung tag mạnh có thể sai; cần phân biệt các representation variants.

### 3.2. Weak ETag khi nào?

Nếu giao diện HTML có một số byte thay đổi (ví dụ định dạng whitespace) nhưng vẫn được ứng dụng coi là tương đương về nội dung, weak ETag có thể biểu diễn ý đó. Tuy nhiên weak ETag **không** phù hợp ở các tình huống cần byte-exact validator như `If-Range` với strong validator.

Không nên đổi tất cả strong tags thành weak tags chỉ để “giảm rủi ro” mà không hiểu ý nghĩa dữ liệu. Chọn kiểu validator tương ứng với consistency contract.

## 4. If-None-Match: các cách gửi và cách đánh giá

Ví dụ client đã có ETag:

~~~http
If-None-Match: "book-7-v3"
~~~

Một request có thể gửi nhiều giá trị:

~~~http
If-None-Match: "book-7-v1", "book-7-v2", "book-7-v3"
~~~

Nếu **một** tag khớp entity tag hiện hành theo weak comparison, điều kiện `If-None-Match` là **false** (tức client bảo “tôi không muốn representation có tag này”). Với GET/HEAD, server trả **304 Not Modified** khi tiền điều kiện không thỏa. Nếu không tag nào khớp, server thực hiện GET/HEAD và trả representation mới, thường 200.

Ví dụ wildcard:

~~~http
If-None-Match: *
~~~

`*` có ý nghĩa khác danh sách literal tags: điều kiện thất bại khi resource có một **current representation**, bất kể tag nào. Với GET/HEAD của resource tồn tại, xử lý chuẩn có thể trả 304; với resource không tồn tại, không tự biến thành 304. **Không gửi wildcard trộn với các tag** trong cùng field — cú pháp đó không hợp lệ.

### 4.1. GET/HEAD khác PUT/POST/DELETE

`If-None-Match` **không** chỉ phục vụ caching. Ví dụ client dùng `If-None-Match: *` trên một request tạo tài nguyên để yêu cầu “chỉ tạo nếu chưa có representation”. Nếu điều kiện thất bại ở một **unsafe method**, server phải trả **412 Precondition Failed** chứ **không** phải 304.

| Method khi `If-None-Match` điều kiện false | Response chuẩn khi đánh giá precondition |
| --- | --- |
| GET | 304 Not Modified |
| HEAD | 304 Not Modified |
| PUT | 412 Precondition Failed |
| POST | 412 Precondition Failed |
| DELETE | 412 Precondition Failed |

Bảng nói về precondition được đánh giá và thất bại trong quy tắc RFC 9110, **không** có nghĩa Spring MVC sẽ tự xử lý mọi điều kiện concurrency của mọi endpoint khi bạn chỉ gắn ETag cho GET. Với các thao tác cập nhật, cần thiết kế transaction/version/If-Match hoặc conditional write rõ ràng.

### 4.2. So sánh weak khác strong

Ví dụ current ETag mạnh `"v3"`. Khi GET gửi:

~~~http
If-None-Match: W/"v3"
~~~

điều kiện `If-None-Match` có thể vẫn được xem là **khớp**, và server trả 304. Trong khi `If-Match: W/"v3"` không vượt qua strong comparison đối với `"v3"`.

Không tự cắt chuỗi `W/` hay dấu quote để so bằng `String.equals`. HTTP định nghĩa rõ cú pháp danh sách entity-tag và so sánh, framework hỗ trợ parsing; nếu triển khai custom, cần dùng parser/logic phù hợp.

## 5. If-Modified-Since: so sánh thời gian sửa đổi

`Last-Modified` trong response cho biết mốc thời gian resource representation được sửa đổi lần cuối:

~~~http
Last-Modified: Wed, 15 Jan 2025 10:30:00 GMT
~~~

Client có thể gửi:

~~~http
If-Modified-Since: Wed, 15 Jan 2025 10:30:00 GMT
~~~

Nếu thời điểm sửa đổi hiện hành **không sau** (earlier hoặc equal) thời điểm client cung cấp, server có thể trả 304 cho GET/HEAD. Nếu resource mới hơn mốc đó, server trả 200 và body mới.

**Mốc thời gian phải theo chuẩn HTTP-date**, không phải chuỗi tùy ý như `2025-01-15T10:30:00` trong request header. Ví dụ ISO-8601 có ích trong JSON, nhưng không thay định dạng HTTP-date của `If-Modified-Since`.

Các điểm tinh tế:

- HTTP-date của `Last-Modified` về thực tế có **độ phân giải theo giây**. Nếu resource đổi hai lần trong một giây, timestamp có thể không nhận diện thay đổi đủ tốt.
- Đồng hồ của các node/server hoặc metadata nguồn có thể khác nhau; không gán timestamp hiện tại cho một resource không hề đổi, nếu mục tiêu là revalidation ổn định.
- Theo RFC 9110, server phải **bỏ qua `If-Modified-Since`** nếu request có `If-None-Match`, hoặc field không phải một HTTP-date hợp lệ, có nhiều thành phần không hợp lệ, hoặc method khác GET/HEAD.
- Giá trị `Last-Modified` đáng tin cậy thường lấy từ metadata tài nguyên/storage, không nên tính `Instant.now()` trên mọi GET.
- Với một resource đang thay đổi mạnh, strong ETag thường chính xác hơn mốc second-granularity, nhưng phải được tạo đúng theo representation.

### 5.1. Ví dụ timeline

| Last-Modified hiện hành | If-Modified-Since | Kết quả GET thường gặp |
| --- | --- | --- |
| 10:30:00 GMT | 10:30:00 GMT | 304 |
| 10:30:00 GMT | 10:31:00 GMT | 304 nếu precondition được đánh giá hợp lệ |
| 10:30:01 GMT | 10:30:00 GMT | 200, body mới |
| 10:30:00 GMT | Giá trị không hợp lệ | Bỏ qua field, xử lý GET bình thường |

Bảng chỉ xét `If-Modified-Since` **khi không có If-None-Match** và resource hiện hành tồn tại. Các preconditions khác, cache status, permission và resource availability vẫn có thể ảnh hưởng kết quả.

## 6. Quy tắc ưu tiên: If-None-Match thắng If-Modified-Since

Đây là điểm dễ sai nhất khi triển khai caching:

> **Khi một request có cả `If-None-Match` và `If-Modified-Since`, bên nhận phải bỏ qua `If-Modified-Since`; ưu tiên đánh giá `If-None-Match`.**

Giả sử ETag hiện hành là `"v4"`, Last-Modified hiện hành là `Wed, 15 Jan 2025 10:30:00 GMT`.

**Trường hợp A: tag khớp, thời gian không khớp hoặc quá cũ**

~~~http
If-None-Match: "v4"
If-Modified-Since: Tue, 14 Jan 2025 00:00:00 GMT
~~~

Vì tag khớp, GET có thể **304** dù timestamp trong request là cũ. Không cố đánh giá theo điều kiện AND.

**Trường hợp B: tag không khớp nhưng thời gian đã đủ mới**

~~~http
If-None-Match: "v3"
If-Modified-Since: Thu, 16 Jan 2025 00:00:00 GMT
~~~

Vì `If-None-Match` không khớp current tag, server nên trả **200 với representation mới**, dù nếu chỉ xét thời gian thì tưởng có thể trả 304.

**Trường hợp C: không có ETag condition, thời gian khớp**

~~~http
If-Modified-Since: Wed, 15 Jan 2025 10:30:00 GMT
~~~

GET có thể **304** theo điều kiện thời gian, vì không có `If-None-Match` để ưu tiên.

| If-None-Match | If-Modified-Since | Validator hiện hành | Kết quả GET điển hình |
| --- | --- | --- | --- |
| Không gửi | Không gửi | Có ETag/time | 200 + body |
| Khớp ETag | Không gửi | Tag chưa đổi | 304 |
| Không khớp ETag | Không gửi | Tag đã đổi | 200 + body mới |
| Không gửi | Ngày bằng hoặc mới hơn | Resource chưa sửa sau ngày | 304 |
| Không gửi | Ngày cũ | Resource sửa sau ngày | 200 |
| **Khớp** | Ngày cũ | Tag chưa đổi | **304** |
| **Không khớp** | Ngày mới | Tag đã đổi | **200** |
| `*` | Bất kỳ | Resource hiện hữu | 304 |
| Giá trị không hợp lệ | Ngày hợp lệ | Tùy HTTP parsing | Không tự chọn 304; kiểm tra thực tế |

Dòng cuối nhắc rằng code production không nên “tự sửa” header chứa lỗi hoặc tùy tiện coi một invalid ETag là match; dựa trên implementation tuân chuẩn và kiểm thử response.

## 7. 304 Not Modified có body hay Content-Length không?

**304 không có message content**. Do đó API không được gửi JSON DTO, text `null` hay file bytes kèm status 304. Khác biệt:

| Status | Ý nghĩa | Body |
| --- | --- | --- |
| 200 OK | Trả representation hiện hành | Có thể chứa JSON/file/etc. |
| 204 No Content | Request thành công, không có response content | Không có body |
| 304 Not Modified | Conditional GET/HEAD xác nhận cache có thể dùng representation cũ | Không có body mới |
| 404 Not Found | Resource không hiện hữu hoặc không tiết lộ sự tồn tại | Có thể có error body |
| 412 Precondition Failed | Precondition áp dụng cho thao tác không thỏa | Có thể có body lỗi |

Một response 304 nên mang metadata liên quan đến cached representation theo HTTP rules, đặc biệt:
- `Date` khi phù hợp;
- `ETag` và/hoặc `Last-Modified` nếu tương ứng;
- `Cache-Control`, `Expires`, `Vary`, `Content-Location` nếu đã được gửi trong response 200 tương ứng và cần cập nhật.

**Điểm thường bị khẳng định sai:** RFC 9110 cho phép `Content-Length` xuất hiện ở response 304 **chỉ khi** giá trị đó chính xác bằng chiều dài content đáng lẽ được gửi trong một response 200 tương ứng. Vì thế không nên viết test “304 bắt buộc không có header Content-Length”; phải kiểm tra **body thực tế rỗng** và metadata đúng.

Với status 304, browser/cache có thể tái tạo response ứng dụng từ body cache và cập nhật metadata. Trong DevTools, bạn có thể thấy `200 (from disk cache)` hoặc nhiều biểu diễn UI khác dù có hoạt động revalidation 304 trên mạng; cần xem đúng request/response ở Network panel.

## 8. `Cache-Control`: quyết định khi nào phải revalidate

`ETag`/`Last-Modified` là **validators**; còn `Cache-Control` thường quyết định một response có được lưu, được tái sử dụng và khi nào phải kiểm tra lại.

| Directive | Ý nghĩa thực tế |
| --- | --- |
| `max-age=300` | Có thể coi response fresh trong tối đa 300 giây theo caching rules |
| `private` | Cho phép cache riêng; cấm shared cache lưu response theo directive này |
| `public` | Cho phép shared cache lưu trong những điều kiện phù hợp |
| `no-cache` | **Có thể lưu**, nhưng phải xác thực lại trước khi tái sử dụng |
| `no-store` | Không lưu response theo chỉ dẫn này; dùng cho dữ liệu nhạy cảm cần chính sách chặt |
| `must-revalidate` | Khi stale, cache không được tái sử dụng mà không xác thực theo quy tắc |
| `immutable` | Gợi ý representation không đổi trong thời gian fresh, thích hợp tài nguyên có URL versioned |

**`no-cache` không đồng nghĩa `no-store`.** Đây là sự khác biệt quan trọng: `no-cache` là “lưu được nhưng revalidate trước khi dùng”, `no-store` là “không lưu”.

Ví dụ Spring:

~~~java
CacheControl cc = CacheControl.maxAge(Duration.ofMinutes(5))
        .cachePrivate();
~~~

Đoạn trên là biểu thức minh họa trong Java code có import `org.springframework.http.CacheControl` và `java.time.Duration`. Nó tạo policy phù hợp khi **người dùng riêng lẻ** có thể lưu cache trong khoảng năm phút. Với dữ liệu cực kỳ nhạy cảm như secrets/token, `CacheControl.noStore()` thường đáng cân nhắc hơn.

Dù có ETag, nếu client vẫn coi cached response là fresh thì **không cần gửi GET revalidation**; chưa thấy 304 không chứng minh cache không hoạt động.

## 9. Spring MVC tự kiểm tra conditional headers khi trả ResponseEntity

Spring MVC 6.x hỗ trợ kết hợp `ResponseEntity` với `ETag`, `Last-Modified` và `Cache-Control`:

~~~java
@GetMapping("/books/{id}")
public ResponseEntity<Book> getBook(@PathVariable long id) {
    Book book = service.findById(id);
    if (book == null) {
        return ResponseEntity.notFound().build();
    }

    return ResponseEntity.ok()
            .eTag(book.etag())
            .lastModified(book.lastModified())
            .cacheControl(CacheControl.maxAge(Duration.ofMinutes(5))
                    .cachePrivate())
            .body(book);
}
~~~

**Đây là ví dụ rút gọn bên trong controller**, chưa độc lập: cần service và DTO Book với method `etag()`, `lastModified()`. Spring MVC sẽ đối chiếu conditional request headers với validators mà `ResponseEntity` cung cấp và có thể đáp 304 khi phù hợp.

Với response mới:
- Client gửi GET thường → 200 + JSON + `ETag` + `Last-Modified` + `Cache-Control`.
- Client gửi `If-None-Match` trùng current ETag → 304 và **không serialize JSON body**.
- Client gửi `If-Modified-Since` bằng/mới hơn lastModified, không có `If-None-Match` → 304.
- Nếu validator thay đổi → 200 + body mới.

**Lưu ý hiệu năng:** trong ví dụ, `service.findById(id)` được gọi **trước** khi Spring xử lý `ResponseEntity`, nên 304 có thể giảm serialization và băng thông nhưng chưa chắc giảm DB lookup. Khi có version/lastModified metadata rẻ, chủ động kiểm tra trước công đoạn xây body nặng bằng `WebRequest.checkNotModified`.

### 9.1. Cách Spring chuẩn hóa ETag

`ResponseEntity.BodyBuilder.eTag(String)` hỗ trợ đưa giá trị entity tag vào header (chuỗi không quote có thể được API quote phù hợp). Để tránh nhầm, ví dụ bài này cung cấp ETag đã có quote đúng chuẩn là `"\"book-7-v3\""`.

Không ghép `ETag` bằng request input thiếu kiểm soát, không đặt text `W/` sai cấu trúc, và không dùng một tag chung cho các representation không tương đương.

## 10. Spring MVC `WebRequest.checkNotModified`: short-circuit từ controller

Spring MVC hỗ trợ method `WebRequest.checkNotModified(...)`:

~~~java
@GetMapping("/reports/{id}")
public String showReport(
        @PathVariable long id,
        WebRequest request,
        Model model) {

    ReportMetadata info = reportService.findMetadata(id);
    if (info == null) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }

    if (request.checkNotModified(
            info.etag(), info.lastModified().toEpochMilli())) {
        return null;
    }

    ReportDto report = reportService.buildExpensiveReport(id);
    model.addAttribute("report", report);
    return "reports/detail";
}
~~~

**Đây là method minh họa cho HTML `@Controller`**, không phải ứng dụng độc lập; cần `reportService`, `ReportMetadata`, `ReportDto` và template `reports/detail`. Các kiểu cần import: `org.springframework.web.context.request.WebRequest`, `Model`, `HttpStatus`, `ResponseStatusException`, annotation MVC.

Cơ chế:

1. Server lấy **metadata rẻ** (ETag/lastModified) từ storage hoặc DB version.
2. `checkNotModified(etag, lastModifiedMillis)` đánh giá preconditions và thiết lập status/validator headers khi phù hợp.
3. Nếu method trả **true**, điều kiện cho phép kết thúc sớm: controller `return null` vì response đã được xử lý (thường **304 cho GET/HEAD**), không dựng expensive DTO hoặc template.
4. Nếu **false**, tiếp tục xây model và render representation mới.

Spring hỗ trợ overload theo ETag, lastModified hoặc cả hai. Với các update methods, precondition không thỏa có thể dẫn tới **412** thay vì 304; tránh áp dụng máy móc GET handler cho PUT.

**Kiểm tra authorization trước khi shortcut**: nếu dùng dữ liệu riêng tư, việc trả 304 cho một caller không được phép truy cập cũng có thể tiết lộ sự tồn tại/phiên bản tài nguyên.

## 11. Ví dụ hoàn chỉnh Spring Boot 3.x + Java 17

Ví dụ cung cấp endpoint:

- `GET /api/books/7` → trả JSON với `ETag` mạnh cố định, `Last-Modified` cố định, `Cache-Control` private 5 phút.
- `GET /api/books/99` → trả 404; không biến missing resource thành 304.
- Test GET không điều kiện, GET với ETag trùng/khác, IMS trùng/cũ, cả hai cùng xuất hiện, wildcard, HEAD và response 304 không có body.

Project xây bằng Maven, **Java 17+**, Spring Boot **3.x**, dependencies **Spring Web** (`spring-boot-starter-web`) và **Spring Boot Starter Test** (`spring-boot-starter-test`). Package: `com.example.demo`.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/BookCacheController.java
src/test/java/com/example/demo/BookCacheControllerTest.java
~~~

### 11.1. `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.2. `BookCacheController.java`

~~~java
package com.example.demo;

import java.time.Duration;
import java.time.Instant;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookCacheController {

    // UTC; độ chính xác theo giây để phù hợp HTTP-date.
    private static final Instant LAST_MODIFIED =
            Instant.parse("2025-01-15T10:30:00Z");

    // ETag đã có cặp dấu nháy kép theo RFC 9110.
    private static final String ETAG = "\"book-7-v3\"";

    @GetMapping("/{id}")
    public ResponseEntity<Book> find(@PathVariable long id) {
        if (id != 7L) {
            return ResponseEntity.notFound().build();
        }

        Book book = new Book(7L, "HTTP caching", 3);

        return ResponseEntity.ok()
                .eTag(ETAG)
                .lastModified(LAST_MODIFIED)
                .cacheControl(CacheControl.maxAge(Duration.ofMinutes(5))
                        .cachePrivate())
                .body(book);
    }

    public record Book(long id, String title, int version) {}
}
~~~

**Tại sao bài thực hành dùng giá trị cố định?** Để test không bị thời gian chạy hoặc database bên ngoài chi phối. Trong production, ETag và Last-Modified phải xuất phát từ dữ liệu/version thực; không nên copy nguyên `2025-01-15` và `v3` cho mọi resource hoặc giữ chúng sau khi nội dung thực thay đổi.

Một `GET /api/books/7` bình thường trả:

~~~json
{"id":7,"title":"HTTP caching","version":3}
~~~

với status 200, header ETag và Last-Modified như ví dụ ở đầu bài. Việc JSON field order cụ thể có thể tùy serializer/config; test dùng `jsonPath` thay vì so chuỗi JSON nguyên văn.

### 11.3. `BookCacheControllerTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookCacheController.class)
class BookCacheControllerTest {

    private static final String ETAG = "\"book-7-v3\"";
    private static final String LAST_MODIFIED =
            "Wed, 15 Jan 2025 10:30:00 GMT";

    @Autowired
    MockMvc mockMvc;

    @Test
    void firstGetReturnsRepresentationAndValidators() throws Exception {
        mockMvc.perform(get("/api/books/7"))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ETAG, ETAG))
                .andExpect(header().string(
                        HttpHeaders.LAST_MODIFIED, LAST_MODIFIED))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "max-age=300, private"))
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.version").value(3));
    }

    @Test
    void matchingEtagReturns304WithoutBody() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, ETAG))
                .andExpect(status().isNotModified())
                .andExpect(header().string(HttpHeaders.ETAG, ETAG))
                .andExpect(content().string(""));
    }

    @Test
    void weakClientTagMatchesForIfNoneMatch() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH,
                                "W/\"book-7-v3\""))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void mismatchingEtagReturns200AndBody() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, "\"book-7-v2\""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(3));
    }

    @Test
    void unchangedLastModifiedReturns304() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                LAST_MODIFIED))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void olderIfModifiedSinceReturns200() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                "Tue, 14 Jan 2025 00:00:00 GMT"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("HTTP caching"));
    }

    @Test
    void etagWinsEvenWhenIfModifiedSinceIsOld() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, ETAG)
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                "Tue, 14 Jan 2025 00:00:00 GMT"))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void differentEtagWinsOverNewerTimestamp() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, "\"book-7-v2\"")
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                "Thu, 16 Jan 2025 00:00:00 GMT"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(3));
    }

    @Test
    void wildcardIsNotModifiedForExistingResource() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, "*"))
                .andExpect(status().isNotModified());
    }

    @Test
    void missingResourceNeverBecomes304() throws Exception {
        mockMvc.perform(get("/api/books/99")
                        .header(HttpHeaders.IF_NONE_MATCH, "*"))
                .andExpect(status().isNotFound());
    }

    @Test
    void headWithMatchingEtagHasNoBody() throws Exception {
        mockMvc.perform(head("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, ETAG))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }
}
~~~

Các test trên được thiết kế cho **Spring MVC 6.x với `@WebMvcTest`**. Chúng khẳng định:
- 200 trả JSON có ETag/time/Cache-Control;
- 304 không có response content;
- `If-None-Match` ưu tiên hơn `If-Modified-Since` trong cả hai hướng bất đồng;
- weak matching khi dùng `If-None-Match`;
- wildcard chỉ có ý nghĩa khi resource tồn tại;
- request HEAD cũng có thể dùng validator mà không trả body.

Chạy:

~~~bash
./mvnw test
~~~

Trên Windows dùng `mvnw.cmd test`; nếu không có Maven wrapper và Maven đã được cài, chạy `mvn test`.

**Giới hạn của MockMvc:** nó kiểm tra kết quả từ MVC handler/controller/test slice, **không mô phỏng toàn bộ cache browser, CDN, gateway hoặc network compression**. Test end-to-end trên cổng HTTP thật có ý nghĩa khi ứng dụng nằm sau reverse proxy hoặc thay đổi content encoding, authorization, personalization.

## 12. Thử trực tiếp bằng curl

Chạy ứng dụng:

~~~bash
./mvnw spring-boot:run
~~~

### 12.1. Nhận 200 cùng validator

~~~bash
curl -i http://localhost:8080/api/books/7
~~~

Kết quả có **ETag: "book-7-v3"**, `Last-Modified: Wed, 15 Jan 2025 10:30:00 GMT`, `Cache-Control: max-age=300, private`, và JSON body.

### 12.2. Gửi ETag đúng để nhận 304

~~~bash
curl -i   -H 'If-None-Match: "book-7-v3"'   http://localhost:8080/api/books/7
~~~

Status kỳ vọng **304 Not Modified**, không có body mới. Terminal có thể vẫn in headers; đừng đọc nhầm việc `curl -i` hiển thị header thành response body.

### 12.3. ETag cũ → nhận 200

~~~bash
curl -i   -H 'If-None-Match: "book-7-v2"'   http://localhost:8080/api/books/7
~~~

Status kỳ vọng **200 OK** và JSON representation hiện hành (version 3).

### 12.4. Dùng If-Modified-Since

~~~bash
curl -i   -H 'If-Modified-Since: Wed, 15 Jan 2025 10:30:00 GMT'   http://localhost:8080/api/books/7
~~~

Status kỳ vọng **304**. Với mốc ngày cũ hơn 14 January 2025, response kỳ vọng **200**.

### 12.5. Thử ưu tiên giữa hai validator

~~~bash
curl -i   -H 'If-None-Match: "book-7-v2"'   -H 'If-Modified-Since: Thu, 16 Jan 2025 00:00:00 GMT'   http://localhost:8080/api/books/7
~~~

Dù timestamp client đưa ra nằm sau thời gian sửa đổi, **ETag không khớp** nên `If-None-Match` được ưu tiên và GET trả 200 theo semantics chuẩn.

Lệnh dùng `\` là cú pháp nối dòng cho shell Linux/macOS/Git Bash. Trên Windows PowerShell, dùng `curl.exe` và cú pháp quoting phù hợp; `curl` có thể là alias trong một số môi trường PowerShell.

**Quan trọng:** curl không tự duy trì browser cache như trình duyệt. Các ví dụ chủ động đặt header điều kiện để kiểm tra origin server. Browser có thể không gửi request khi cache còn fresh, nên “tôi không thấy 304” không phải bằng chứng validator không hoạt động.

## 13. ShallowEtagHeaderFilter: vì sao không phải tối ưu CPU?

Spring MVC có `org.springframework.web.filter.ShallowEtagHeaderFilter`, có thể tính ETag từ **response content được tạo ra** và so với `If-None-Match`. Filter này thường:
1. Để controller và view/serializer render body.
2. Buffer/capture nội dung response.
3. Tính hash nội dung rồi so ETag.
4. Nếu khớp, trả 304 và không gửi lại body qua mạng.

Ưu điểm: thêm ETag cho một số endpoint mà không cần tự quản lý version ở controller.

**Giới hạn lớn:** response phải được **tạo ra** để hash, nên filter chủ yếu tiết kiệm **băng thông**, **không** giảm CPU/DB/serialization một cách căn bản; với response lớn còn có chi phí buffer memory. Theo tài liệu Spring, filter dùng MD5 để tạo shallow ETag, có tùy chọn `writeWeakETag`. Đừng coi MD5 của filter như primitive bảo mật để xác minh chữ ký file.

Minh họa đăng ký filter trong Spring Boot 3.x:

~~~java
@Configuration
public class EtagFilterConfig {

    @Bean
    public FilterRegistrationBean<ShallowEtagHeaderFilter> etagFilter() {
        FilterRegistrationBean<ShallowEtagHeaderFilter> registration =
                new FilterRegistrationBean<>(
                        new ShallowEtagHeaderFilter());

        registration.addUrlPatterns("/pages/*");
        registration.setDispatcherTypes(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC);
        registration.setOrder(10);
        return registration;
    }
}
~~~

**Đây là class minh họa bổ sung**, không thuộc project thực hành ở phần 11. Cần import `@Configuration`, `@Bean`, `FilterRegistrationBean` từ Spring Boot, `ShallowEtagHeaderFilter` từ Spring Web và `jakarta.servlet.DispatcherType`. Nếu dùng filter với async, việc đăng ký `DispatcherType.ASYNC` giúp filter tham gia cuối luồng async dispatch theo tài liệu. Một số streaming scenarios cần tránh content caching wrapper; Spring cung cấp `ShallowEtagHeaderFilter.disableContentCaching(request)` trước khi ghi output nếu cần.

**Không nên bật filter cho mọi endpoint** khi đã có ETag do controller cung cấp, khi response lớn/streaming, hoặc khi dữ liệu nhạy cảm có chính sách `no-store` mà bạn chưa kiểm tra rõ tác động. Với API có DB version và dữ liệu lớn, check validator sớm trong controller thường tiết kiệm tài nguyên hơn.

## 14. Static resources, files và versioned assets

Các tài nguyên tĩnh (CSS/JS/images) có thể được Spring MVC phục vụ qua `ResourceHttpRequestHandler`. Spring hỗ trợ `Last-Modified` dựa trên resource metadata, `Cache-Control`, và cơ chế resource chain/versioned URLs. Với URL như:

~~~text
/static/app.a1b2c3.js
~~~

nếu hash nằm trong **tên asset URL** và file bất biến, có thể dùng cache TTL dài; thay đổi file đồng nghĩa URL mới. Đây là một phương án khác với việc revalidate thường xuyên mỗi request.

Với file do người dùng upload, API download có thể chọn ETag theo object storage version hoặc hash/metadata đáng tin. Tuy nhiên:
- `Content-Type`, `Content-Encoding`, `Content-Disposition` và biến thể response phải nhất quán.
- Kiểm tra quyền truy cập **trước** khi cho biết resource có thay đổi hay không.
- Với tài liệu private, không đưa ra CDN/shared cache nếu không có authorization-aware caching phù hợp.
- Khi hỗ trợ HTTP Range, `If-Range` có semantics riêng và thường cần strong validator; không đánh đồng `If-Range` với `If-None-Match`.

## 15. ETag/Last-Modified vs @Cacheable (Spring Cache)

Hai cách cache khác nhau:

| Khái niệm | HTTP conditional cache | Spring `@Cacheable` |
| --- | --- | --- |
| Nơi có thể cache | Browser, proxy/CDN, HTTP client | Cache abstraction ở server (in-memory, Redis...) |
| Cơ chế kiểm tra | ETag, Last-Modified, request validators, 304 | Cache key, hit/miss/eviction do ứng dụng định nghĩa |
| 304 | Có khi client revalidate GET/HEAD | Bản thân `@Cacheable` không trả 304 |
| Cache TTL | `Cache-Control` và HTTP semantics | Cấu hình cache provider/TTL |
| Mục tiêu | Giảm truyền representation HTTP | Giảm tính toán/DB hoặc truy xuất server |
| Quyền truy cập | Cần HTTP cache/privacy/authorization rules | Cache key phải bao gồm dimensions liên quan quyền/user |

Một endpoint có thể dùng **cả hai**: service đọc dữ liệu từ `@Cacheable` trên server, controller tạo ETag để browser dùng revalidation. Hai hệ thống không thay thế nhau; cache server sai key theo tenant/user có thể rò rỉ dữ liệu dù HTTP headers trông đúng.

## 16. Dữ liệu riêng tư, Vary và nhiều representation

### 16.1. Dữ liệu cá nhân và shared caches

Một response API có cookie session và dữ liệu cá nhân không được tùy tiện đặt:

~~~http
Cache-Control: public, max-age=86400
~~~

Đó là một ví dụ **không nên áp dụng cho dữ liệu riêng tư** nếu shared cache/CDN có thể phục vụ giữa các user. Thường cần `private` và TTL phù hợp, hoặc `no-store` cho dữ liệu cực nhạy cảm. **304 không có body không có nghĩa không thể lộ dữ liệu**: cached body cũ có thể vẫn bị dùng lại nếu cache key/phân quyền sai.

### 16.2. Vary header cho representation variants

Nếu API trả nội dung theo ngôn ngữ:

~~~http
Vary: Accept-Language
ETag: "book-7-vi-v3"
~~~

Bản tiếng Anh có thể có tag khác:

~~~http
Vary: Accept-Language
ETag: "book-7-en-v3"
~~~

Với gzip/br hoặc JSON/XML khác nhau, cần xét `Accept-Encoding`, `Accept` và các biến thể representation tương ứng. `Vary` hướng dẫn cache tính request header vào matching key; không thay thế kiểm tra quyền truy cập. Cache cần dùng đúng representation variant trước khi so validator.

Một ETag duy nhất cho các response có bytes khác nhau có thể gây 304 sai. Với strong tags, đừng gán cùng strong tag cho bytes khác nhau sau content coding khi chúng được xem là các selected representations riêng.

### 16.3. CORS và ETag trong frontend

Trong CORS, `ETag` không nằm trong danh sách tất cả response headers mà JavaScript có thể đọc mặc định. Nếu frontend ở một origin khác cần đọc `ETag` để tự lưu/revalidate, server có thể cần:

~~~http
Access-Control-Expose-Headers: ETag
~~~

Nhưng không đồng nghĩa có quyền đọc ETag là có quyền đọc response body/private data. Cần `Access-Control-Allow-Origin`, credentials và authorization đúng; ETag không là access token.

Khi browser tự quản lý HTTP cache, JavaScript có thể không cần đọc thủ công ETag. Không tự đưa If-None-Match cho mọi request nếu không hiểu cache semantics/Fetch CORS và validators.

## 17. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Luôn 200, không có 304 | Client không gửi conditional headers hoặc cache còn fresh | Kiểm tra Network request headers, thử curl có If-None-Match |
| Luôn 200 dù ETag “có vẻ” giống | ETag khác dấu quote/weak tag/variant, content thay đổi | So header thực tế, kiểm tra logic sinh tag |
| Luôn 304 dù nội dung đổi | Version/Last-Modified không tăng khi representation đổi | Sửa chiến lược validator, cập nhật metadata atomic |
| 304 xuất hiện nhưng UI vẫn có JSON | Browser/cache dùng lại 200 body đã lưu | Đây là hành vi đúng của revalidation |
| Code gửi body với 304 | Đặt status 304 thủ công và vẫn serialize DTO | Dùng framework conditional handling, không viết body 304 |
| Cả hai điều kiện cho kết quả không đúng | Đánh giá IMS dù có INM hoặc áp dụng AND | Ưu tiên If-None-Match theo RFC 9110 |
| So thời gian sai | Dùng millisecond vs HTTP second, timezone, ISO string | HTTP-date GMT, UTC, second granularity |
| Dữ liệu private bị cache ở CDN | Dùng `public`/max-age hoặc cache key không theo user | Dùng private/no-store, config shared cache chính xác |
| ETag lọt qua nhiều tenant | Tag và cache key không phản ánh quyền/representation | Thiết kế validator/authorization theo selected representation |
| Shallow filter không cải thiện CPU | Filter vẫn render trước khi hash | Check version metadata sớm trong controller |
| Range/download sai với ETag yếu | Nhầm If-Range với If-None-Match | Dùng strong validators cho byte-range khi phù hợp |
| Header ETag JavaScript không đọc được | CORS chưa expose ETag | `Access-Control-Expose-Headers: ETag` và policy đúng |
| Header Last-Modified tương lai | Đồng hồ metadata/server sai | Đồng bộ metadata/clock, tránh future timestamp |
| Test body 304 không rỗng | Tự trả `ResponseEntity.status(304).body(...)` | Dùng response entity validator API hoặc checkNotModified |

## 18. Câu hỏi kiểm tra

**1. `If-None-Match` và `If-Modified-Since` cùng có mặt, server ưu tiên cái nào?**

`If-None-Match`. Server phải bỏ qua `If-Modified-Since` khi có `If-None-Match`.

**2. ETag hiện hành là `"v4"`, client gửi `If-None-Match: "v3"` và ngày sửa đổi tương lai. GET trả gì?**

Thông thường **200 với body hiện hành** vì ETag không khớp; không trả 304 dựa trên IMS tương lai.

**3. `If-None-Match: *` với GET resource tồn tại có tác dụng gì?**

Điều kiện thất bại vì có current representation, GET/HEAD có thể trả **304** theo HTTP precondition semantics.

**4. Nếu `If-None-Match` thất bại trên PUT thì có trả 304 không?**

Không. Khi precondition được đánh giá và không thỏa đối với unsafe methods, thường phải trả **412 Precondition Failed**.

**5. Response 304 có body JSON không?**

Không. 304 không có message content. Cache dùng lại representation đã lưu, cập nhật metadata tương ứng.

**6. `no-cache` có nghĩa tuyệt đối không lưu data không?**

Không. Nó cho phép lưu nhưng yêu cầu revalidation trước reuse. `no-store` mới chỉ thị không lưu.

**7. Tại sao `ShallowEtagHeaderFilter` chưa chắc làm DB/CPU nhanh hơn?**

Vì filter vẫn cần response body được tạo để hash; lợi ích thường nằm ở băng thông, không loại bỏ chi phí tính body.

**8. Có cần xác thực user trước khi trả 304?**

Có đối với tài nguyên riêng tư. 304 không có body nhưng vẫn liên quan resource và cached body/metadata; authorization phải áp dụng nhất quán.

## 19. Checklist triển khai production

1. Xác định selected representation của từng URL (ngôn ngữ, encoding, user quyền, version).
2. Sinh ETag ổn định và thay đổi khi representation thực sự thay đổi; strong/weak dùng đúng semantics.
3. Cung cấp Last-Modified từ metadata thật với độ chính xác phù hợp, không gán `Instant.now()` tùy tiện.
4. Kết hợp `Cache-Control` theo chính sách lưu trữ/freshness: `private`, `no-store`, TTL phù hợp.
5. Với Spring MVC, ưu tiên `ResponseEntity.eTag/lastModified/cacheControl`; dùng `WebRequest.checkNotModified` để shortcut trước xử lý nặng nếu metadata rẻ.
6. Đảm bảo **If-None-Match ưu tiên If-Modified-Since** và xử lý `If-None-Match: *` đúng.
7. 304 không có body mới; không assert sai rằng 304 tuyệt đối không được có Content-Length header.
8. Với tài nguyên riêng tư, kiểm tra authorization trước khi dùng validator; không đưa dữ liệu cá nhân vào shared cache.
9. Kiểm thử 200, 304, 404, ETag match/mismatch, IMS equal/old và hai điều kiện đồng thời; HEAD nếu endpoint hỗ trợ.
10. Với CDN/proxy, kiểm tra `Vary`, compression, ETag rewrite, caching policy và response của từng tầng.
11. Không bật `ShallowEtagHeaderFilter` cho response streaming/file lớn một cách không cân nhắc chi phí buffer.
12. Phân biệt browser cache, `@Cacheable`, và application state; đừng gọi 304 là “server cache hit” nếu việc tính representation vẫn xảy ra.

## Nguồn chính thức

- [Spring Framework 6.2 — HTTP Caching (MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-caching.html)
- [Spring Framework 6.2 — Filters / Shallow ETag](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html)
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework 6.2 — WebRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/WebRequest.html)
- [Spring Framework 6.2 — CacheControl Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/CacheControl.html)
- [RFC 9110 — HTTP Semantics, Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [MDN — Conditional Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests)
- [MDN — 304 Not Modified](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304)
