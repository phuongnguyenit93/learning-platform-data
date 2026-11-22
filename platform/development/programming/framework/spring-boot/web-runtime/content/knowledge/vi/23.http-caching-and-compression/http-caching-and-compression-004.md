# Phản hồi 304 Not Modified và tránh gửi lại nội dung không đổi trong Spring Boot

## 1. Tình huống và kết luận quan trọng

Giả sử browser tải một tài liệu 250 KB từ Spring Boot. Người dùng quay lại trang sau vài phút nhưng nội dung tài liệu chưa đổi. Nếu server cứ trả `200 OK` kèm toàn bộ 250 KB, ứng dụng tốn băng thông và thời gian truyền không cần thiết.

HTTP cung cấp **conditional requests** (yêu cầu có điều kiện). Sau lần tải đầu tiên, client/cache ghi nhớ nội dung và **validator** mà server trả về — thường là `ETag` hoặc `Last-Modified`. Khi cần xác nhận bản đã lưu còn hợp lệ, client gửi một request kèm `If-None-Match` hoặc `If-Modified-Since`. Nếu đại diện nội dung (representation) được chọn không đổi, server phản hồi:

```http
HTTP/1.1 304 Not Modified
ETag: "report-v7"
Cache-Control: no-cache
Date: Sun, 08 Nov 2026 01:00:00 GMT
```

**`304 Not Modified` không chứa response body**. Client/cache tiếp tục dùng bản nội dung `200` đã lưu và cập nhật thông tin cache theo metadata của `304`. Server không phải gửi lại các bytes của tài liệu. Tuy vậy **vẫn có một HTTP round trip** để xác nhận. Muốn tránh cả round trip khi tài nguyên còn mới, cần cấu hình thời hạn tươi (freshness) bằng `Cache-Control` phù hợp.

Mục tiêu bài học:

- Hiểu **`200`, cache hit không cần network, `304` và `412`** khác nhau.
- Sử dụng `ETag`/`If-None-Match` và `Last-Modified`/`If-Modified-Since` đúng chuẩn.
- Biết thứ tự ưu tiên khi request mang **cả hai validator**.
- Áp dụng trong Spring MVC, WebFlux, static resources và endpoint API.
- Tránh tính lại nội dung đắt đỏ chỉ để cuối cùng trả `304`.
- Kiểm thử bằng Java 17+, Spring Boot và `curl`, đồng thời biết các bẫy về cache riêng tư, nén HTTP và `Vary`.

**Một hiểu lầm cần loại bỏ:** `304` không có nghĩa “server không cần làm gì”. Server vẫn nhận request, xác định representation hiện tại, kiểm tra điều kiện và trả metadata. Mức tiết kiệm CPU/phép truy vấn tùy cách tính validator: kiểm tra bằng version sẵn có có thể rất rẻ; tính ETag bằng cách render toàn bộ HTML rồi hash chỉ tiết kiệm băng thông.

## 2. Phân biệt cache tươi, revalidation và tải nội dung mới

Một vòng đời điển hình:

```text
Lần 1
Browser                            Spring Boot
  | GET /api/report                   |
  |---------------------------------->|
  | 200 OK                            |
  | ETag: "report-v7"                 |
  | Cache-Control: no-cache           |
  | Body: ... dữ liệu ...             |
  |<----------------------------------|
  | Lưu body + ETag                    |

Lần 2 (cần xác nhận)
  | GET /api/report                   |
  | If-None-Match: "report-v7"        |
  |---------------------------------->|
  | so sánh ETag                       |
  | 304 Not Modified                  |
  | ETag: "report-v7"                 |
  | KHÔNG có body                     |
  |<----------------------------------|
  | Dùng lại body đã lưu               |

Lần 3 (dữ liệu thay đổi)
  | GET /api/report                   |
  | If-None-Match: "report-v7"        |
  |---------------------------------->|
  | representation đã là version 8    |
  | 200 OK                            |
  | ETag: "report-v8"                 |
  | Body: ... dữ liệu mới ...         |
  |<----------------------------------|
  | Thay body + validator trong cache  |
```

Nếu response đầu tiên có `Cache-Control: max-age=300` và bộ nhớ đệm đánh giá response vẫn **fresh**, browser/cache thường có thể dùng bản đã lưu trong 300 giây **không hỏi server**, tùy các điều kiện HTTP caching. Khi hết hạn, `ETag` giúp xác nhận lại và nhận `304` nếu dữ liệu không đổi.

| Trạng thái | Có request tới server? | Status trên network (thường gặp) | Có gửi lại body? | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Cache còn fresh, có thể reuse | Không | Không có response mới từ origin | Không | Tái sử dụng cache trực tiếp |
| Cache cần xác nhận, nội dung không đổi | Có | `304 Not Modified` | Không | Dùng body `200` đã lưu |
| Cache cần xác nhận, nội dung đã đổi | Có | `200 OK` | Có | Cập nhật nội dung và validator |
| Không có body cũ phù hợp trong cache | Có | Thường `200 OK` | Có | Cần nội dung đầy đủ |
| Điều kiện ghi dữ liệu không thỏa | Có | `412 Precondition Failed` | Không thực hiện thao tác theo điều kiện | Bảo vệ cập nhật dữ liệu, không phải cache hit |

Browser DevTools đôi khi hiển thị “from memory cache”, “from disk cache”, hoặc biểu diễn response nội bộ như `200` dù có network validation `304`. Khi điều tra, phân biệt **status ở network** với **nội dung cuối cùng browser sử dụng**.

## 3. `ETag` là gì? Vì sao thích hợp để kiểm tra thay đổi?

`ETag` (entity tag) là một validator do server gán cho **một representation được chọn**. Header ví dụ:

```http
ETag: "product-42-v9"
```

Client dùng giá trị đó ở request sau:

```http
If-None-Match: "product-42-v9"
```

Server so sánh với ETag hiện tại. Với `GET`/`HEAD`, nếu điều kiện `If-None-Match` **không thỏa** vì đã có representation trùng tag, server có thể trả `304` theo quy tắc HTTP. Nếu tag không khớp, server xử lý request thông thường, có thể trả `200` và representation mới.

**ETag không nhất thiết là hash.** Nó có thể được dựng từ số phiên bản bản ghi, content hash, phiên bản file build hoặc revision ID, miễn có ý nghĩa nhất quán đối với representation và không làm lộ thông tin cần giữ kín. Đừng gán ETag chỉ dựa vào thời gian hiện tại ở mỗi request — nếu tag luôn đổi thì browser sẽ không nhận `304`.

### Strong và weak ETag

- **Strong ETag**, ví dụ `"sha256-abc"`: đại diện cho một representation với tính tương đương byte đủ chặt theo HTTP.
- **Weak ETag**, ví dụ `W/"article-17"`: cho phép nhận diện nội dung **tương đương về mặt ngữ nghĩa** dù bytes có thể khác.
- `If-None-Match` dùng **weak comparison** khi kiểm tra `GET`/`HEAD`; vì vậy có thể so khớp tag weak phù hợp.
- `If-Match` cho optimistic concurrency của request sửa dữ liệu dùng **strong comparison**; một weak ETag không phải thay thế tùy tiện.
- Với range requests/`If-Range`, strong validators có những yêu cầu riêng; không nên dùng weak ETag để khẳng định hai bản gzip/plain là tương đương byte.

Ví dụ:

```http
ETag: "rev-18"
ETag: W/"semantic-rev-18"
```

Hai dòng trên là **hai ví dụ độc lập**, không phải hai `ETag` headers được khuyên gửi cùng lúc trong một response.

### ETag gắn với representation, không chỉ một database row

Nếu endpoint trả dữ liệu khác theo ngôn ngữ, định dạng JSON, phân quyền, user hoặc content encoding, **validator phải phản ánh đúng representation mà client có thể lưu**. Ví dụ tài liệu tiếng Việt khác tiếng Anh không nên dùng một strong ETag chung khi bytes khác nhau. Có thể dùng version gắn với variant; cần phối hợp `Vary` để cache chọn đúng bản.

ETag từ version ID giúp kiểm tra nhanh mà không phải tạo lại body:

```text
read metadata: resourceId=42, version=9
request If-None-Match: "product-42-v9"
=> match -> 304 (bỏ qua truy vấn/render phần body đắt đỏ)
```

Nếu chỉ có `SHA-256(renderEntireResponse())`, server vẫn phải dựng nội dung rồi mới so ETag; `304` khi đó chủ yếu tiết kiệm **network**, không bảo đảm tiết kiệm CPU.

### `If-None-Match` có thể chứa nhiều tag hoặc dấu `*`

```http
If-None-Match: "v7", "v8", W/"v9"
```

Client/cache có thể gửi danh sách tag của các representation đã lưu. `If-None-Match: *` mang nghĩa “điều kiện không thỏa nếu tài nguyên hiện có”; với `GET` của tài nguyên tồn tại, nó có thể dẫn tới `304`, nhưng với `PUT` tạo resource theo điều kiện “chỉ tạo nếu chưa tồn tại”, điều kiện không thỏa dẫn tới `412`. Không chỉ so sánh nguyên chuỗi header với một tag khi tự triển khai xử lý HTTP; hãy dùng API framework.

## 4. `Last-Modified` và `If-Modified-Since`

`Last-Modified` là HTTP-date (GMT), ví dụ:

```http
Last-Modified: Mon, 01 Jan 2024 00:00:00 GMT
```

Sau đó client có thể gửi:

```http
If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT
```

Nếu selected representation không mới hơn thời điểm được nêu, server có thể đáp `304` (khi request `GET`/`HEAD` và không có `If-None-Match`). Khi dữ liệu mới hơn, server trả nội dung hiện tại như `200`.

**Độ chính xác:** HTTP-date có độ phân giải giây. Một resource có thể sửa **hai lần trong cùng một giây**, khiến Last-Modified không đủ phân biệt; đồng hồ giữa hệ thống hoặc cách quản lý timestamp cũng có thể gây sai lệch. Với dữ liệu thay đổi nhanh, một ETag từ version sequence hoặc content digest thường đáng tin hơn.

Nếu server chỉ có timestamp “lần cuối truy cập” thay vì **lần cuối nội dung thay đổi**, không nên dùng nó làm Last-Modified. Nếu tạo representation riêng theo user, timestamp global của bảng dữ liệu không đủ biểu diễn thay đổi quyền xem hoặc bản thân phần hiển thị.

### Khi request có cả hai điều kiện

Theo HTTP Semantics (RFC 9110), **`If-None-Match` có ưu tiên hơn `If-Modified-Since`**. Server phải bỏ qua `If-Modified-Since` nếu request có `If-None-Match`.

Ví dụ hiện tại là ETag `"v8"`, nhưng client gửi:

```http
If-None-Match: "v7"
If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT
```

Nếu ETag không khớp, **không được trả `304` chỉ vì thời gian Last-Modified thỏa điều kiện cũ**. Server phải xét ETag theo thứ tự ưu tiên, tránh khiến client tiếp tục dùng một bản cache đã khác.

Các trường hợp cần nhớ:

| Request | Validator hiện tại | Kết quả dự kiến |
| --- | --- | --- |
| `If-None-Match: "v8"` | `ETag: "v8"` | `304` cho conditional GET/HEAD |
| `If-None-Match: "v7"` | `ETag: "v8"` | Thường `200` và body mới |
| Chỉ `If-Modified-Since` bằng hoặc muộn hơn thời điểm sửa | Last-Modified phù hợp | `304` |
| `If-None-Match` sai **và** `If-Modified-Since` thỏa | ETag hiện tại không khớp | Không dùng điều kiện ngày để trả 304 |
| Request `GET` đầu tiên không có validators | Có nội dung | Thường `200` kèm body/validators |

## 5. `304 Not Modified` có gì và không có gì?

`304` xác nhận một response đã lưu còn dùng được theo điều kiện HTTP. **Không phải một body mới**. Không gửi JSON `{"message":"not modified"}`, HTML hay một dòng text trong response `304`. Nếu ứng dụng cần trả một thông báo “dữ liệu chưa thay đổi” có body cho client không có cache, đó là một **ngữ nghĩa ứng dụng khác**, không nên dùng sai status 304.

Theo RFC 9110, response `304` phải kèm các metadata liên quan mà một response `200` tương ứng sẽ có, khi áp dụng, như `Date`, `ETag`, `Vary`, `Cache-Control`, `Expires`, `Content-Location`. `Last-Modified` cũng có thể hữu ích theo ngữ cảnh. `304` **không chứa message body hay trailers**.

```http
HTTP/1.1 304 Not Modified
Date: Sun, 08 Nov 2026 01:00:00 GMT
ETag: "report-v7"
Cache-Control: private, max-age=0, must-revalidate
Vary: Accept-Encoding
```

Đây là ví dụ header, không phải output cứng của project ở mục 8; thời gian `Date` và tập header thật phụ thuộc server/cấu hình.

### Ai sử dụng lại body cũ?

Browser hoặc một HTTP cache trung gian lấy body của response `200` đã lưu. Nó có thể cập nhật metadata của bản lưu từ response `304`, rồi phục vụ client bằng body cũ phù hợp. **Server không gửi body cũ qua `304`**.

Nếu một HTTP client tự viết không lưu body/metadata trước đó, nhận `304` sẽ không có dữ liệu để hiển thị. Client phải quản lý cache riêng hoặc gửi unconditional `GET` để lấy body. Không coi `304` là “một `200` rỗng”.

### `304` có phải redirect?

Nó thuộc nhóm status 3xx nhưng **không phải redirect sang URL khác**, không yêu cầu `Location` và không bảo client tải một đường dẫn mới. Nó hướng client/cache tiếp tục sử dụng representation đã lưu.

### Có áp dụng `304` cho `POST`, `PUT`, `DELETE`?

Quy tắc conditional requests cho `If-None-Match`: nếu điều kiện **không thỏa**, với `GET` hoặc `HEAD` có thể trả **`304`**, còn với các phương thức khác có thể dùng **`412 Precondition Failed`**. `If-Match` thường dùng cho optimistic concurrency khi sửa dữ liệu, không phải để tải cache. Không tự xử lý `PUT` bằng `304` để thông báo “dữ liệu không đổi”.

`HEAD` vốn không có body, nên conditional HEAD thường kém giá trị tiết kiệm băng thông hơn conditional GET, nhưng tuân theo semantics HTTP.

## 6. Freshness và revalidation: `Cache-Control` không phải ETag

`Cache-Control` mô tả chính sách lưu trữ và sử dụng cache. `ETag` và `Last-Modified` chỉ giúp **kiểm tra xem bản đã lưu còn hợp lệ không**. Hai nhóm bổ sung cho nhau.

| Directive | Tác dụng thường gặp | Có cần network request khi dùng lại? |
| --- | --- | --- |
| `Cache-Control: max-age=600` | Cho phép dùng bản fresh trong 600 giây nếu các điều kiện cache thỏa | Không trong thời gian fresh |
| `Cache-Control: no-cache` | **Có thể lưu**, nhưng phải xác nhận với origin trước khi reuse | Thường có revalidation |
| `Cache-Control: no-store` | Không cho cache lưu response | Không dựa vào bản lưu; `304` thường không mang lợi ích |
| `Cache-Control: private` | Cache riêng như browser có thể lưu; shared CDN/proxy không được lưu dưới dạng shared | Tùy freshness; hữu ích cho nội dung cá nhân |
| `Cache-Control: public` | Có thể cho phép shared cache lưu theo điều kiện HTTP | Tùy freshness và các ràng buộc khác |
| `must-revalidate` | Khi đã stale, không được tự ý dùng lại nếu không validate theo các ngoại lệ chuẩn | Cần xác nhận trước khi reuse stale |
| `immutable` | Chỉ dẫn rằng representation trong thời gian fresh dự kiến không đổi | Giảm revalidation không cần thiết khi dùng đúng |

**Bẫy số 1:** `no-cache` không đồng nghĩa “không lưu”. Nó yêu cầu xác nhận lại trước khi reuse; với ETag, kết quả thường là `304` khi dữ liệu không đổi.

**Bẫy số 2:** một response `no-store` không phải lúc nào cũng tối ưu cho tài nguyên tĩnh. Nếu nội dung công khai có thể cache, dùng versioned filename/hash + `max-age` sẽ hiệu quả hơn.

**Bẫy số 3:** `max-age` **không có nghĩa** “sau thời gian đó browser bắt buộc tải lại toàn bộ body”. Khi hết fresh, client có thể dùng conditional request để nhận `304`, giữ body cũ và cập nhật metadata.

### Mẫu chính sách thực dụng

- **File tĩnh fingerprinted** như `/assets/app.8a2bf.js`: thường dùng `Cache-Control: public, max-age=31536000, immutable` nếu URL đó thực sự bất biến mỗi khi deploy.
- **HTML có thể thay đổi**: cân nhắc `no-cache` và ETag/Last-Modified để cache xác nhận phiên bản mới.
- **API chung không nhạy cảm**: chọn `public`/`private` và `max-age` vừa phải theo tần suất cập nhật; ETag giúp xác nhận lại.
- **Trang/API chứa dữ liệu theo người dùng**: cân nhắc `private, no-cache` nếu nội dung phù hợp để browser lưu nhưng bắt buộc revalidate; với dữ liệu bí mật không nên lưu, dùng `no-store`.
- **Dữ liệu xác thực/ủy quyền nhạy cảm**: không chỉ dùng ETag hay `Vary` để “bảo vệ”; phải có kiểm tra quyền và cache policy tránh chia sẻ dữ liệu giữa người dùng.

Chọn chính sách từ yêu cầu nghiệp vụ và threat model; **không áp một `max-age` rất dài cho toàn bộ API** chỉ để tăng cache hit.

## 7. Spring Boot và cơ chế conditional request

Spring Framework đã cung cấp API hỗ trợ ETag/Last-Modified cho cả Servlet MVC và reactive WebFlux.

### 7.1. Spring MVC với `ResponseEntity`

Ví dụ snippet trong một `@RestController`:

```java
@GetMapping("/books/{id}")
public ResponseEntity<BookDto> book(@PathVariable long id) {
    BookDto dto = bookService.read(id);
    return ResponseEntity.ok()
            .eTag("\"book-42-v5\"")
            .cacheControl(CacheControl.noCache())
            .body(dto);
}
```

Đây là **snippet minh họa**, `BookDto` và `bookService` do ứng dụng cung cấp. Spring MVC có thể tự xét conditional request khi xử lý `ResponseEntity` có `ETag`/`Last-Modified`, trả `304` và không ghi body nếu validator khớp.

Lưu ý: ở ví dụ trên, `bookService.read(...)` **đã chạy trước khi Spring kiểm tra ResponseEntity**. Đây là cách đơn giản, giảm băng thông nhưng chưa chắc tiết kiệm truy vấn/serialize. Khi việc tạo nội dung tốn tài nguyên, nên **tách lấy metadata phiên bản khỏi lấy body** và kiểm tra sớm như mục 7.2.

### 7.2. Spring MVC với `WebRequest.checkNotModified` để rẽ nhánh sớm

`WebRequest` cung cấp các overload:

```java
request.checkNotModified(String etag);
request.checkNotModified(long lastModifiedTimestamp);
request.checkNotModified(String etag, long lastModifiedTimestamp);
```

Đoạn trên là **chữ ký API minh họa**, không phải một class Java độc lập. Kiểu `lastModifiedTimestamp` là số mili-giây từ Unix epoch. Với conditional `GET`/`HEAD`, Spring kiểm tra các preconditions và thiết lập trạng thái HTTP, điển hình `304`, khi không cần truyền nội dung.

Mẫu điều khiển:

```java
@GetMapping("/reports/{id}")
public String report(@PathVariable long id, WebRequest request) {
    String eTag = reportRepository.readCheapVersion(id);
    if (request.checkNotModified(eTag)) {
        return null;   // Spring đã đánh dấu request not modified.
    }

    return expensiveReportRenderer.render(id);
}
```

Đây là **snippet giả định** `reportRepository` và `expensiveReportRenderer` được cung cấp; muốn biên dịch cần imports và class chứa phương thức. Điểm kỹ thuật: `readCheapVersion` phải thật sự rẻ và phản ánh mọi thay đổi ảnh hưởng body. Nếu `render` tùy chỉnh theo locale/user, version cũng phải phản ánh các biến thể tương ứng.

Ở `@RestController`, trả `null` sau `checkNotModified` cho phép Spring xử lý response `304` đã được thiết lập. Nếu viết `@Controller` trả view name, Spring cũng có mẫu trả `null` khi `checkNotModified` là `true`. Không tự phát một response `200` rỗng thay cho `304`.

### 7.3. Spring WebFlux

Trong WebFlux, API tương ứng nằm trên `ServerWebExchange`:

```java
@GetMapping("/reactive/report")
public Mono<String> report(ServerWebExchange exchange) {
    String etag = "\"report-v7\"";
    if (exchange.checkNotModified(etag)) {
        return Mono.empty();
    }
    return expensiveReactiveReport();
}
```

Đây là **snippet WebFlux**, không phải chương trình độc lập; `expensiveReactiveReport()` trả `Mono<String>`. `checkNotModified` được gọi trước khi tạo/subscribe công việc tốn kém. Nếu version phải đọc từ repository reactive, hãy làm việc đó trong pipeline và chỉ tạo phần render sau khi kiểm tra; đừng dùng `.block()` trên event loop.

WebFlux cũng hỗ trợ `ResponseEntity` với `eTag`/`lastModified`. Việc nhận/xử lý `304` có cùng ý nghĩa HTTP, nhưng các lớp runtime khác Servlet MVC. Không mang nguyên code `HttpServletResponse`/`WebRequest` của MVC sang WebFlux.

### 7.4. Tệp tĩnh

Spring MVC `ResourceHttpRequestHandler` và WebFlux `ResourceWebHandler` có hỗ trợ conditional requests cho static resources; thông tin `Last-Modified` có thể được suy ra từ `Resource#lastModified()`. Spring Boot phục vụ tài nguyên ở các classpath locations thông thường và bạn có thể cấu hình `Cache-Control` cho các file tĩnh.

Với file CSS/JS/images, cách tốt thường là **đặt tên file theo content hash** rồi dùng cache dài, tránh request thừa. `304` vẫn hữu ích cho HTML hoặc tệp có URL ổn định và phải kiểm tra cập nhật.

## 8. Ví dụ Spring Boot MVC chạy được với Java 17+

Ví dụ gồm ba endpoint:

- `GET /api/report`: tạo `ETag` từ version; gọi `WebRequest.checkNotModified` **trước khi render body**.
- `POST /api/report/revise`: tăng version giả lập nội dung được cập nhật.
- `GET /api/static-info`: dùng `ResponseEntity` với cả `ETag` và `Last-Modified` để quan sát Spring tự xử lý 304.

Chọn **Spring Boot 3.5.0** để POM dùng một phiên bản đã phát hành; ví dụ phục vụ mục đích học tập, không phải dự án production đã cấu hình authentication/CSRF. Đối với dự án thật, dùng bản vá đang được duy trì phù hợp chính sách của tổ chức.

### 8.1. Cấu trúc project

```text
conditional-http-demo/
├── pom.xml
└── src/main/java/com/example/httpcache/
    └── ConditionalHttpApplication.java
```

### 8.2. `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>conditional-http-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Maven starter web mang Spring MVC và embedded Tomcat mặc định. Không cần tự thêm `ShallowEtagHeaderFilter` để thực hiện các conditional requests trong ví dụ này.

### 8.3. Java source đầy đủ

Tệp `src/main/java/com/example/httpcache/ConditionalHttpApplication.java`:

```java
package com.example.httpcache;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

@SpringBootApplication
public class ConditionalHttpApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConditionalHttpApplication.class, args);
    }
}

@RestController
class CacheDemoController {

    private final AtomicInteger revision = new AtomicInteger(1);

    // Mô phỏng tra cứu version rẻ, trước bước render body.
    @GetMapping(value = "/api/report",
            produces = "text/plain;charset=UTF-8")
    public String report(WebRequest request,
                         HttpServletResponse response) {

        int version = revision.get();
        String etag = "\"report-v" + version + "\"";

        // no-cache: được lưu nhưng phải revalidate trước khi reuse.
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache");

        if (request.checkNotModified(etag)) {
            return null;  // 304, không tạo và không gửi report body.
        }

        // Chỉ dựng nội dung sau khi validator KHÔNG trùng.
        return "Report revision " + version + "\n";
    }

    // Chỉ để test local: POST làm thay đổi version của tài nguyên.
    @PostMapping(value = "/api/report/revise",
            produces = "text/plain;charset=UTF-8")
    public String revise() {
        int version = revision.incrementAndGet();
        return "Now revision " + version + "\n";
    }

    // ResponseEntity cho Spring tự xét ETag + Last-Modified.
    @GetMapping(value = "/api/static-info",
            produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> staticInfo() {
        long modifiedAt = Instant.parse(
                "2024-01-01T00:00:00Z").toEpochMilli();

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .eTag("\"static-v1\"")
                .lastModified(modifiedAt)
                .contentType(MediaType.TEXT_PLAIN)
                .body("Static information v1\n");
    }
}
```

**Vì sao mã này chạy được?**

1. Có một class `public` đúng tên file; controller package-private cùng package vẫn được component scan.
2. `AtomicInteger` biểu diễn version thay đổi an toàn giữa các request trong **một JVM**. Đây không phải version store production; nhiều instance sẽ cần shared DB/version thật.
3. String ETag chứa dấu nháy kép đúng định dạng `"report-v1"`. `WebRequest.checkNotModified` nhận ETag và để Spring so sánh với `If-None-Match`.
4. `no-cache` cho phép browser lưu response để dùng ETag nhưng **yêu cầu revalidate**.
5. `POST` tăng version để demo chuyển từ `304` sang `200`. Không có thao tác ghi dữ liệu thật; hệ thống production cần bảo vệ cập nhật bằng auth, CSRF và quyền truy cập.
6. `/api/static-info` dùng body cố định và thời điểm sửa cố định, nên có thể dùng cả `ETag` và `Last-Modified`. Trường hợp này giúp học cơ chế mà không bị clock drift.
7. `ResponseEntity` có ETag/Last-Modified được Spring MVC kiểm tra khi trả HTTP; vì body cố định đã được tạo ở controller, ví dụ này chủ yếu thể hiện **giảm truyền body**.

**Giới hạn rõ ràng:** Khi request xử lý ở nhiều instance, `AtomicInteger` tại mỗi instance có thể khác nhau; muốn ETag đúng, phải lấy version được đồng bộ với dữ liệu business. Đừng sử dụng demo này làm cơ chế cache production mà không sửa dữ liệu/transaction.

### 8.4. Chạy ứng dụng

Tại thư mục `conditional-http-demo`, cần JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Mở terminal thứ hai. Thứ tự các lệnh dưới đây giả định ứng dụng vừa khởi động, version ban đầu bằng 1 và cổng 8080 còn trống.

**Bước A — lần tải đầu không có điều kiện:**

```bash
curl -i http://localhost:8080/api/report
```

Phần response quan trọng:

```http
HTTP/1.1 200
ETag: "report-v1"
Cache-Control: no-cache

Report revision 1
```

Đây là **ví dụ phần header/body cần quan sát**, không phải toàn bộ raw output của Tomcat: protocol/version formatting, `Date`, `Content-Type` và header khác có thể xuất hiện. Body chính xác là `Report revision 1` kèm ký tự newline.

**Bước B — gửi ETag của bản đã lưu:**

```bash
curl -i -H 'If-None-Match: "report-v1"' \
  http://localhost:8080/api/report
```

HTTP status kỳ vọng **`304 Not Modified`**, có ETag tương ứng và **không có response body**. `curl -i` vẫn in HTTP headers.

**Bước C — thay đổi nội dung bằng endpoint demo:**

```bash
curl -s -X POST http://localhost:8080/api/report/revise
```

Body chính xác:

```text
Now revision 2
```

Sau đó thử lại ETag cũ:

```bash
curl -i -H 'If-None-Match: "report-v1"' \
  http://localhost:8080/api/report
```

Vì version hiện tại là 2, kỳ vọng **`200 OK`**, header `ETag: "report-v2"` và body:

```text
Report revision 2
```

Cuối cùng thử validator mới:

```bash
curl -i -H 'If-None-Match: "report-v2"' \
  http://localhost:8080/api/report
```

Kỳ vọng **`304`** và không có body.

**Bước D — kiểm tra `Last-Modified` tại tài nguyên cố định:**

```bash
curl -i http://localhost:8080/api/static-info
```

Response `200` có `ETag: "static-v1"`, `Last-Modified: Mon, 01 Jan 2024 00:00:00 GMT` và body `Static information v1`.

Gửi request chỉ dùng ngày sửa:

```bash
curl -i \
  -H 'If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT' \
  http://localhost:8080/api/static-info
```

Kỳ vọng `304 Not Modified` không có body.

Gửi cả hai validator nhưng **ETag không khớp**:

```bash
curl -i \
  -H 'If-None-Match: "static-v0"' \
  -H 'If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT' \
  http://localhost:8080/api/static-info
```

Kỳ vọng **`200`** và body hiện tại, vì `If-None-Match` được ưu tiên, không dùng ngày cũ để trả `304`.

### 8.5. Lưu ý khi chạy lệnh

- Các lệnh shell trên dùng Bash/Linux/macOS. Trên Windows PowerShell, dùng `curl.exe` và đặt mỗi lệnh trên một dòng (hoặc dùng cú pháp nối dòng của PowerShell).
- Dùng dấu nháy phù hợp shell khi truyền `If-None-Match`, vì dấu nháy kép **là một phần của ETag**, không phải chỉ cú pháp trình bày.
- `curl` không có cache tự động như browser; các lệnh gửi điều kiện thủ công minh họa protocol, không chứng minh browser sẽ luôn gửi request `304`.
- Nếu đã gọi `/api/report/revise` nhiều lần, số version tiếp theo khác 2; khởi động lại demo để có dữ liệu ban đầu.
- Nếu cổng 8080 bị chiếm, chạy project với `--server.port=8081` thông qua Spring Boot/Maven args và đổi URL tương ứng.
- Có thể build file chạy độc lập bằng `mvn clean package` và `java -jar target/conditional-http-demo-1.0.0.jar`.

## 9. Vì sao kiểm tra ETag trước khi tạo body giúp giảm CPU?

Có hai chiến lược phổ biến:

### 9.1. Shallow ETag: hash toàn bộ response rồi mới so

Spring MVC cung cấp `ShallowEtagHeaderFilter`. Bộ lọc có thể cache response content trong bộ nhớ, tạo ETag (thường bằng hash nội dung), so với `If-None-Match` và trả `304` khi trùng.

```text
Đọc database -> render JSON/HTML -> serialize -> tính hash
    -> so ETag -> 304 nếu trùng -> không gửi BODY
```

**Lợi:** thêm ETag tương đối thuận tiện, tiết kiệm băng thông. **Hạn chế:** công việc truy vấn/render/serialize vẫn diễn ra; có thể tốn bộ nhớ để giữ response, đặc biệt với response lớn/streaming. Không được hứa “làm ETag là CPU giảm” khi dùng shallow ETag.

### 9.2. Early check: tra metadata trước khi tạo body

```text
Đọc version/lastModified từ metadata (rẻ)
    -> so If-None-Match/If-Modified-Since
       -> trùng: 304, DỪNG
       -> khác: truy vấn nặng -> render/serialize -> 200 + body
```

Đây là hướng nên ưu tiên khi API lớn, báo cáo phức tạp hoặc tài nguyên tốn CPU. Để early check đúng:

- Metadata phải đổi **mỗi khi** nội dung hoặc quyền xem ảnh hưởng representation thay đổi.
- Kiểm tra quyền truy cập như bình thường **trước khi** trả metadata/cache response; không tiết lộ tồn tại/version của resource không được phép xem.
- Nếu resource có nhiều variants theo locale/encoding/user, validator phải phân biệt chúng đúng cách.
- Nếu dữ liệu đổi trong khoảng từ lúc đọc version đến lúc render, cần chiến lược transaction/snapshot nhất quán, không gắn ETag cũ lên body mới.
- Không tự gọi một `HEAD`/`GET` tốn kém để “kiểm tra ETag rẻ” nếu việc tính version vốn cần làm toàn bộ truy vấn; hãy đo thực tế.

Với static resources có content hash trong tên file, cách hiệu quả nhất thường là cache tươi dài hạn, **khỏi phải gửi request revalidation**.

## 10. `Vary` và nén HTTP: quan hệ với ETag/304

Một URL có thể tạo ra nhiều **representations** theo header request:

- `Accept-Encoding: gzip` -> response có `Content-Encoding: gzip`.
- `Accept-Encoding: br` -> response nén Brotli nếu server hỗ trợ.
- Không yêu cầu nén -> response identity/không nén.
- `Accept-Language: vi`/`en` -> có thể là hai body khác nhau.
- `Accept: application/json`/`text/html` -> content negotiation khác.

Để cache lưu/chọn đúng variant, server gửi `Vary` phù hợp, ví dụ:

```http
Vary: Accept-Encoding
```

hoặc nếu response phụ thuộc cả ngôn ngữ:

```http
Vary: Accept-Encoding, Accept-Language
```

**`Vary` không làm biến URL thành nhiều URL khác nhau**, nhưng hướng dẫn cache đưa các request headers đó vào logic chọn representation. Thiếu `Vary` có thể khiến cache gửi nhầm gzip/plain, nhầm ngôn ngữ hoặc nội dung không phù hợp; một `304` tưởng đúng có thể cập nhật nhầm variant đã lưu.

### Strong ETag với gzip và identity

Một **strong ETag** gắn với byte-level representation. Bản nén gzip và bản không nén có bytes khác nhau, vì thế **không nên tái sử dụng cùng một strong ETag** cho cả hai encoded representations. Có thể:

- Dùng strong ETag **khác nhau** cho từng content coding/variant;
- Dùng weak ETag với semantics nhất quán khi muốn nhận diện cùng nội dung logic, nếu phù hợp luật HTTP;
- Để framework/proxy/CDN quản lý ETag đúng thứ tự nén, kiểm tra thực tế header cho mỗi variant.

Không giả định bất cứ `ETag` nào cũng là checksum của body plaintext. Nếu proxy thay đổi compression hoặc re-encode response, cần bảo đảm validators và `Vary` vẫn chính xác.

### 304 không phải gzip “kích thước zero”

`304` **không có body**, nên không thể nói nó là “response body được nén thành 0 byte”. Nén `gzip`/`br` làm nhỏ body khi **cần gửi** (ví dụ `200`). Revalidation `304` tránh gửi body hoàn toàn. Hai kỹ thuật bổ sung nhau:

1. Cache còn fresh: không có request tới origin.
2. Cache stale + validator match: request nhỏ, `304` không body.
3. Resource đổi: `200` và có thể nén body, cập nhật ETag/metadata.

**Đo băng thông ở nhiều tầng**: proxy CDN có thể trả `304` mà Spring Boot origin không thấy request; hoặc browser trả cache local mà network panel hiển thị theo quy ước riêng.

## 11. Static resources trong Spring Boot: 304 hoặc asset fingerprinting?

Spring Boot tự cấu hình static resource handling khi có web starter phù hợp. Các resource như CSS, JS, ảnh trong `classpath:/static/` và vị trí đã cấu hình có thể được Spring phục vụ qua `ResourceHttpRequestHandler` (MVC) hoặc `ResourceWebHandler` (WebFlux).

Tùy resource và cấu hình, handler có thể dùng `Last-Modified` của tệp để xử lý `If-Modified-Since`. Có thể thiết lập cache policy trong Spring MVC:

```java
@Configuration
class AssetCacheConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(7)).cachePublic());
    }
}
```

Đây là **snippet cấu hình MVC**, chưa phải class đầy đủ vì cần các imports Spring và `Duration`. Đặt class trong package được quét của app, không thêm `@EnableWebMvc` nếu chỉ muốn bổ sung resource mapping.

Nếu asset có URL không đổi nhưng nội dung thay đổi trong thời gian `max-age=7d`, browser có thể giữ bản cũ mà không gửi request cho đến khi hết hạn. Vì vậy nên:

- Dùng **fingerprint/content hash** trong URL để nâng phiên bản mỗi lần nội dung đổi; ví dụ `/assets/app.4bf21.css`.
- Dùng `Cache-Control` thời hạn dài cho URL **bất biến**.
- Đối với HTML entry point hoặc config có thể đổi, chọn `no-cache`/thời hạn ngắn và validators phù hợp.
- Không gắn `public, max-age=31536000, immutable` cho response chứa nội dung người dùng hoặc tài nguyên có thể sửa mà URL không đổi.

### 304 và version resolver khác nhau

`VersionResourceResolver` có thể hỗ trợ content-based versioning và tạo/resolve URL đã fingerprint khi được cấu hình đúng. Bật resolver đơn thuần **không tự thay mọi chuỗi URL hardcode trong HTML tĩnh**; template/resource URL provider hoặc build pipeline cũng phải tạo URL phù hợp.

Nếu file đã có version/hash trong path, trình duyệt fresh-cache thường không hỏi server, nên `304` ít xuất hiện hơn. Đây **không phải lỗi**; đó có thể là cache hiệu quả hơn.

## 12. ETag và dữ liệu tùy người dùng: bảo mật, phân quyền và invalidation

Một cache validator không phải cơ chế xác thực. Giả sử `GET /api/profile` khác body theo người đăng nhập:

- Không phát `Cache-Control: public` nếu có khả năng shared cache phát response của user A cho user B.
- Dùng `private` hoặc `no-store` theo độ nhạy; nếu dùng browser private cache, phải xét logout, tài khoản đổi và dữ liệu nhạy cảm còn lưu trên máy dùng chung.
- ETag phải thể hiện representation theo user và quyền, không chỉ `"profile-v1"` chung cho mọi người.
- Server **vẫn kiểm tra authentication và authorization**, kể cả client gửi `If-None-Match`; không nên trả `304` cho resource mà client không có quyền truy cập.
- `Vary: Cookie` hoặc `Vary: Authorization` không tự bảo đảm một endpoint được phép cache công khai và không thay thế `private`/`no-store`.
- Nếu role/quyền thay đổi nhưng data row version không đổi, resource cá nhân hóa có thể đã khác. Validator phải xét đủ trạng thái ảnh hưởng nội dung.

### Invalidation: dữ liệu đổi phải đổi validator

Một ETag sai gây lỗi nguy hiểm: server trả `304` trong khi body mới **đã khác**, khiến client dùng lại dữ liệu cũ. Những nguồn thay đổi có thể bao gồm:

- Update bản ghi business, tính toán lại một thành phần trong báo cáo.
- Template thay đổi, layout/locale/format khác.
- Quyền xem hoặc dữ liệu được phép hiển thị thay đổi.
- Tài liệu phụ thuộc dữ liệu của nhiều bảng, cần composite revision.
- Nén hoặc content negotiation chọn một representation khác.

Đừng chỉ tăng `version` của một bản ghi mà bỏ qua các phụ thuộc làm thay đổi body. Với endpoint dynamic nhiều thành phần, có thể dùng snapshot version/timestamp chung hoặc hash dựa trên dữ liệu đủ đầy; cân nhắc chi phí tính validator và tính nhất quán giữa reads.

## 13. Kiểm tra tự động với MockMvc

Có thể thêm dependency test sau vào `pom.xml` trong mục 8 (đoạn đặt trong `<dependencies>`, không phải một POM độc lập):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Test Java sau là **class hoàn chỉnh bổ sung** ở `src/test/java/com/example/httpcache/CacheControllerTest.java`:

```java
package com.example.httpcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CacheControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void matchingEtagReturns304WithoutBody() throws Exception {
        mvc.perform(get("/api/report")
                        .header(HttpHeaders.IF_NONE_MATCH, "\"report-v1\""))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void nonMatchingEtagReturns200WithBody() throws Exception {
        mvc.perform(get("/api/report")
                        .header(HttpHeaders.IF_NONE_MATCH, "\"report-v0\""))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ETAG, "\"report-v1\""))
                .andExpect(content().string("Report revision 1\n"));
    }

    @Test
    void lastModifiedCanReturn304() throws Exception {
        mvc.perform(get("/api/static-info")
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                "Mon, 01 Jan 2024 00:00:00 GMT"))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }
}
```

Chạy:

```bash
mvn test
```

Các tests trên dùng context mới với version ban đầu 1 và không có test nào gọi endpoint `revise`. Vì `AtomicInteger` dùng singleton bean trong test context, nếu thêm test đổi version, phải reset dữ liệu giữa các test hoặc thiết kế fixture độc lập để tránh phụ thuộc vào thứ tự chạy.

Nếu Java/Spring Boot version dùng khác, hãy đối chiếu test auto-configuration annotation phù hợp. Test kiểm tra body rỗng khi `304`, không chỉ kiểm tra status.

### Ma trận test HTTP nên có

| Case | Header request | Trạng thái kỳ vọng |
| --- | --- | --- |
| GET không có validator | Không có `If-*` | `200` + body |
| GET với ETag trùng | `If-None-Match` trùng | `304` không body |
| GET với ETag cũ | `If-None-Match` khác | `200` + ETag mới/body |
| GET với `If-Modified-Since` phù hợp | Không có `If-None-Match` | `304` |
| Cả hai và ETag không trùng | `If-None-Match` sai, date “chưa đổi” | `200`; ETag ưu tiên |
| Resource missing | GET URL không tồn tại | `404`, không giả vờ `304` |
| User không có quyền | Header giống bản của user khác | `401`/`403` phù hợp, không lộ cache |
| Asset có `Vary` | Đổi `Accept-Encoding`/`Accept-Language` | Chọn body/validator variant đúng |
| Cache `no-store` | Response nhạy cảm | Client không dựa vào body lưu |
| Cache vẫn fresh | `max-age` còn hiệu lực | Cache có thể không liên hệ origin |

## 14. Quan sát hiệu năng thật

Sau khi bật 304, hãy đo thay vì mặc định kết luận thành công:

1. **Bandwidth:** bytes từ origin đến client/CDN và tỷ lệ `200`/`304`.
2. **Latency:** p50/p95/p99, bao gồm round trip network; `304` vẫn có request và có thể phải chờ backend.
3. **CPU và DB:** chi phí tính validator so với query/render body. Nếu dùng `ShallowEtagHeaderFilter`, CPU có thể gần như không giảm.
4. **Memory:** kích thước cache phía client/CDN và buffering phía server khi hash nội dung.
5. **Fresh-hit ratio:** tỉ lệ request tránh hoàn toàn origin nhờ `Cache-Control`; chỉ đếm `304` không cho biết cache tối ưu.
6. **Correctness:** số lần body lẽ ra đổi nhưng server trả 304; đây là lỗi nghiêm trọng do validator/variant sai.
7. **Security:** rà soát response có dữ liệu cá nhân bị shared cache lưu hoặc user cũ tái sử dụng sau logout.
8. **Nén:** kiểm tra `Content-Encoding`, `Vary`, validator strong/weak trên cả gzip và identity variants.

Với CDN/reverse proxy, status do Spring Boot ghi log có thể khác status browser nhìn thấy, vì cache trung gian có thể xử lý request. Cần quan sát từng lớp và phân biệt `304` do origin phát với cache hit không tới origin.

**Đừng đưa session ID, token và dữ liệu nhạy cảm vào ETag.** ETag có thể hiển thị trong response/header/log/CDN và có nguy cơ trở thành identifier theo dõi nếu thiết kế không cẩn thận.

## 15. Các lỗi hay gặp và cách sửa

| Lỗi/triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Browser luôn tải lại body `200` | Không có validator hoặc ETag thay đổi mỗi lần | Phát ETag/Last-Modified ổn định theo representation, kiểm tra response |
| Browser không gửi `If-None-Match` | Cache không lưu, `no-store`, response không cacheable hoặc cache còn fresh | Kiểm tra `Cache-Control`, storage, request và DevTools |
| `304` có body JSON | Ứng dụng tự tạo response sai semantics | Để framework trả 304 không body; không viết body cho status 304 |
| Có `304` nhưng trang vẫn chậm | Server vẫn render/query nặng để tính ETag | Early check bằng metadata/version rẻ |
| Dùng timestamp hiện tại làm Last-Modified | Giá trị luôn thay đổi không liên quan nội dung | Lấy thời điểm cập nhật thật |
| Dữ liệu thay đổi hai lần cùng giây nhưng vẫn `304` | Last-Modified quá thô | Dùng ETag/version phân biệt mỗi lần thay đổi |
| Client gửi cả hai validator và server vẫn ưu tiên ngày | Triển khai sai RFC 9110 | Ưu tiên `If-None-Match`; nên dùng Spring API |
| Gzip và identity dùng chung strong ETag | Bytes của encoded representation khác nhau | Tạo tag theo variant/encoding hoặc weak validator phù hợp |
| Trả nội dung sai ngôn ngữ | Thiếu `Vary: Accept-Language` hoặc validator phân variant | Sửa `Vary` và ETag theo representation |
| User A nhận body cũ của user B | Shared cache cá nhân hóa sai | `private`/`no-store`, auth checks và validator phù hợp |
| Cố dùng `304` khi client không có body cũ | Client tự viết không quản lý cache | Cho client lưu bản 200 trước hoặc GET không điều kiện |
| `ResponseEntity` 304 nhưng DB vẫn bị query | Body được tạo trước framework check | Dùng `WebRequest.checkNotModified` sớm |
| Cache lâu một năm nhưng sửa file cùng URL | Fresh cache không revalidate ngay | Đổi URL fingerprint khi content thay đổi |
| Dùng `If-None-Match` trên PUT để cập nhật phiên bản cũ | Nhầm điều kiện tải cache với optimistic locking | Dùng `If-Match`/`If-Unmodified-Since` phù hợp, xử lý `412` |
| Hành vi browser khác `curl` | `curl` không tự quản lý browser cache | Dùng DevTools, request headers và cache storage để kiểm tra |

### Một quy trình debug nhanh

1. Gọi endpoint bằng `curl -i` không có `If-*`: xác nhận `200` có body, ETag/Last-Modified, Cache-Control và Vary đúng.
2. Gọi lại với `If-None-Match` chính xác như header nhận được: xác nhận `304`, **không body**.
3. Gọi lại với tag không khớp: phải có body mới hoặc phản hồi bình thường theo trạng thái tài nguyên.
4. Nếu hỗ trợ ngày, thử `If-Modified-Since` và trường hợp có đồng thời hai validator.
5. Thay đổi dữ liệu thật, kiểm tra version/ETag đổi; kiểm tra quyền và các biến thể locale/encoding.
6. Vào DevTools → Network: phân biệt memory/disk cache, 304 network và body 200; kiểm tra proxy/CDN.
7. Đo CPU/DB và network; nếu chỉ tiết kiệm bytes mà server vẫn chậm, chuyển sang early validation hoặc asset fingerprinting.

## 16. Câu hỏi tự đánh giá

1. **`304` có gửi lại tài liệu để browser cập nhật không?** Không. `304` không có body; cache dùng lại tài liệu đã lưu.
2. **`304` có nghĩa request không đến server không?** Không. Nó thường là kết quả một conditional request. Cache fresh có thể dùng lại mà không liên hệ server.
3. **`Cache-Control: no-cache` có cấm lưu response không?** Không. Nó yêu cầu revalidate trước khi tái sử dụng.
4. **`Cache-Control: no-store` khác `no-cache` như thế nào?** `no-store` cấm lưu response trong cache; `no-cache` có thể lưu nhưng phải xác nhận lại.
5. **ETag có bắt buộc là hash SHA-256 không?** Không. Nó là validator của representation; version ổn định/có ý nghĩa cũng có thể dùng.
6. **Vì sao Last-Modified không luôn đủ?** Độ phân giải giây và timestamp có thể không phân biệt các lần sửa sát nhau.
7. **Nếu request mang cả If-None-Match và If-Modified-Since thì dùng cái nào?** Ưu tiên `If-None-Match`, bỏ qua `If-Modified-Since`.
8. **`ShallowEtagHeaderFilter` tiết kiệm được gì?** Chủ yếu băng thông; response vẫn phải được tính trước khi hash.
9. **Vì sao không dùng cùng strong ETag cho gzip và uncompressed?** Hai representations có bytes khác nhau; cần validator đúng với selected representation và `Vary`.
10. **Trang HTML có dữ liệu user có nên `public, max-age=31536000`?** Không. Cần tránh shared cache và xem xét `private`/`no-store`.
11. **Khi nào `304` không còn lợi ích lớn?** Khi asset fingerprinted vẫn fresh trong cache, request thường không cần gửi tới origin.
12. **API trả `304` nhưng client chưa bao giờ lưu `200` thì sao?** Client không có body để dùng lại; phải tải nội dung bằng unconditional GET.
13. **Khi sửa data, chỉ đổi body mà không đổi ETag thì sao?** Có thể gây `304` sai, khiến client tiếp tục dùng bản cũ; đây là lỗi invalidation.
14. **Lệnh `curl -H 'If-None-Match: "v1"'` tự chứng minh browser sẽ cache không?** Không. Nó chỉ kiểm thử server phản hồi với một header request cụ thể.

## 17. Checklist triển khai production

- [ ] Tài nguyên là public hay personalized? Có được browser/shared cache lưu không?
- [ ] Chọn `Cache-Control` đúng: freshness, private/public, no-cache/no-store.
- [ ] Nếu cần revalidation, phát `ETag` ổn định theo **representation**; thêm `Last-Modified` nếu có dữ liệu phù hợp.
- [ ] Ưu tiên early check validator trước query/render đắt đỏ.
- [ ] Nếu ETag tính từ version dữ liệu, đảm bảo version phản ánh mọi thay đổi nội dung và quyền truy cập.
- [ ] Với JSON/HTML nhiều variants, cấu hình `Vary` và validators đúng theo content negotiation/encoding.
- [ ] Với static file fingerprinted, dùng cache fresh dài hạn khi URL thực sự bất biến.
- [ ] Conditional GET khớp phải trả `304` không body; ETag cũ trả `200`/body hiện tại.
- [ ] `If-None-Match` được ưu tiên hơn `If-Modified-Since` khi cả hai cùng có.
- [ ] Phân biệt semantics `If-Match`/`412` cho request thay đổi dữ liệu.
- [ ] Kiểm tra authentication/authorization trước khi quyết định trả 304 cho nội dung hạn chế.
- [ ] Test trên browser, `curl`, proxy/CDN và nhiều instances; không chỉ đơn vị test một controller.
- [ ] Đo network bytes **và** thời gian DB/CPU, không nhầm 304 với hiệu năng end-to-end.
- [ ] Khi thay đổi chính sách cache, đánh giá hệ quả với bản cache cũ đã phát ra từ các release trước.

## 18. Tài liệu chính thức

- [RFC 9110 — HTTP Semantics, điều kiện If-None-Match/If-Modified-Since và 304](https://www.rfc-editor.org/rfc/rfc9110.html).
- [RFC 9111 — HTTP Caching, freshness, revalidation, cập nhật response đã lưu](https://www.rfc-editor.org/rfc/rfc9111.html).
- [Spring Framework — Spring MVC HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html).
- [Spring Framework — Spring WebFlux HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html).
- [Spring Framework — Static Resources trong MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html).
- [Spring Framework — Shallow ETag filter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [MDN — 304 Not Modified](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304).
- [MDN — ETag](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/ETag).
- [MDN — HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching).

**Kết luận:** `304 Not Modified` là cách **xác nhận bản đã cache còn đúng mà không chuyển lại body**. Muốn áp dụng hiệu quả trong Spring Boot, kết hợp **`Cache-Control` quyết định khi nào cần request**, **`ETag`/`Last-Modified` nhận diện representation**, **`If-None-Match`/`If-Modified-Since` để revalidate**, và **early check trong controller** khi cần giảm CPU/DB. Đừng quên `Vary`, nén HTTP, authorization và quản lý cache theo người dùng.