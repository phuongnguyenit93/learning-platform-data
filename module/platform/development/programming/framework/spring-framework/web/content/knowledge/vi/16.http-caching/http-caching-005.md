# ShallowEtagHeaderFilter, chi phí tạo phản hồi và giới hạn tối ưu trong Spring MVC

## 1. Bài toán: một HTTP 304 có thực sự tiết kiệm CPU?

Một ứng dụng Spring MVC có endpoint `GET /api/reports/summary`. Controller đọc dữ liệu từ DB, gọi thêm dịch vụ khác, tạo DTO rồi Jackson serialize thành JSON dài 500 KiB. Phần lớn dữ liệu không đổi. Nếu client đã có body, nó gửi `If-None-Match` để hỏi liệu representation có thay đổi hay không. Server trả `304 Not Modified`, không gửi lại 500 KiB.

Điểm dễ nhầm: **nếu dùng `ShallowEtagHeaderFilter`, controller thường vẫn chạy, DB vẫn được truy vấn, DTO vẫn được tính và response body vẫn được render vào buffer**. Filter chỉ có thể tính ETag sau khi có response bytes; vì vậy nó chủ yếu **giảm băng thông**, chứ **không tránh được CPU/query/render**.

Mục tiêu bài học:

- Hiểu cơ chế HTTP `ETag`, `If-None-Match`, `304`, `Cache-Control`, strong/weak validators và các biến thể representation.
- Theo dõi từng bước của `ShallowEtagHeaderFilter`: bọc response, cache body, tính MD5, so ETag, chọn 200/304.
- Phân biệt **băng thông** với **CPU, DB I/O, serialization, bộ nhớ và GC**.
- Hiểu giới hạn mặc định theo method/status/`no-store`, vấn đề streaming/async và `disableContentCaching`.
- Sử dụng `WebRequest.checkNotModified(...)` với validator biết sớm để **không tạo body** khi client đã có bản mới.
- Thiết kế ứng dụng Spring Boot 3/Java 17 có các endpoint shallow, early ETag, no-store, streaming, cùng MockMvc tests kiểm tra đúng cả status lẫn số lần handler đã chạy.

**Phạm vi:** Spring MVC Servlet stack, Spring Framework 6.x và Spring Boot 3.x. Spring WebFlux dùng các abstraction reactive khác; không mang Servlet filter này sang WebFlux.

## 2. HTTP conditional GET và ETag

### 2.1. Request đầu tiên

Client chưa có response:

```http
GET /api/reports/summary HTTP/1.1
Host: localhost:8080

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-cache
ETag: "report-v15"

{"status":"ready","total":42}
```

`ETag` là một **validator cho representation của resource**, ở đây giả sử là revision `report-v15`. Client lưu body và validator nếu chính sách HTTP caching cho phép.

### 2.2. Revalidation

Client hỏi tiếp:

```http
GET /api/reports/summary HTTP/1.1
If-None-Match: "report-v15"

HTTP/1.1 304 Not Modified
ETag: "report-v15"
Cache-Control: no-cache
```

Khi validator khớp, response 304 **không mang representation body mới**. Client dùng bản đã cache theo HTTP semantics. Header ETag trong các ví dụ là mẫu minh họa; với `ShallowEtagHeaderFilter`, tag do Spring tính từ bytes chứ không phải revision literal.

| Khái niệm | Vai trò |
| --- | --- |
| `ETag` | Validator server gửi kèm representation |
| `If-None-Match` | Client muốn server kiểm tra xem cache có còn phù hợp |
| `304 Not Modified` | Không cần tải lại body qua mạng |
| `Cache-Control: no-cache` | Cache có thể lưu nhưng phải revalidate trước khi reuse |
| `Cache-Control: no-store` | Không lưu response vào HTTP cache |
| `Cache-Control: private` | Cho phép cache riêng nhưng không lưu tại shared cache |
| `Last-Modified` | Validator theo thời điểm sửa đổi khi dữ liệu có hỗ trợ |
| `If-Modified-Since` | Conditional GET dựa trên timestamp |
| `Vary` | Các request headers làm response có những biến thể khác nhau |
| `If-Match` | Precondition khác, thường dùng chống ghi đè khi PUT/PATCH |

**Không dùng `If-None-Match` và `If-Match` lẫn lộn.** `If-None-Match` thường để revalidate GET; `If-Match` là precondition quan trọng cho cập nhật khi cần optimistic concurrency. `ShallowEtagHeaderFilter` không xử lý cập nhật DB, không thay thế version/transaction và không triển khai điều kiện `If-Match`.

### 2.3. Strong và weak ETag

```http
ETag: "report-v15"
ETag: W/"report-v15"
```

- **Strong validator:** bảo đảm tính tương đương representation theo strong validation semantics của HTTP. Phù hợp với trường hợp cần byte-exact và `If-Match` nếu được tạo đúng.
- **Weak validator:** ký hiệu `W/`, thể hiện tương đương đủ cho cache revalidation nhưng không dùng như strong validator.
- Với conditional GET, `If-None-Match` áp dụng **weak comparison**; với `If-Match` phải **strong comparison**.
- ETag không phải access token, chữ ký số, MAC hay cơ chế authentication. Không lấy nội dung tag làm credential.

`ShallowEtagHeaderFilter#setWriteWeakETag(true)` cho phép ghi weak ETag. Trong demo sẽ bật tính năng này, vì chỉ quan tâm revalidation. Đừng xem MD5 tag dưới dạng strong mặc định là lời hứa rằng compression/representation variants của toàn hệ thống đã được giải quyết.

### 2.4. ETag thuộc representation, không chỉ thuộc entity trong DB

Nếu cùng URL trả JSON khác theo `Accept-Language`, user role, query parameter hoặc media type, các representation có thể khác nhau. Server phải xác định ETag tương ứng với variant thực sự và cung cấp cache metadata phù hợp:

```http
Cache-Control: private, no-cache
Vary: Accept-Language
```

Với dữ liệu cá nhân, không gửi `Cache-Control: public` một cách tùy tiện. 304 không tự thực hiện authorization: mỗi request vẫn phải được xác thực/phân quyền phù hợp để không trả nhầm thông tin có tính riêng tư.

## 3. ShallowEtagHeaderFilter hoạt động như thế nào?

`org.springframework.web.filter.ShallowEtagHeaderFilter` kế thừa `OncePerRequestFilter`. Thay vì biết trước version từ repository, filter cần **body đã render** để tạo digest.

```text
Client GET /api/reports/summary
    │
    ▼
ShallowEtagHeaderFilter
    ├── chuẩn bị ContentCachingResponseWrapper
    │
    ▼
filterChain.doFilter(request, wrappedResponse)
    │
    ├── DispatcherServlet chọn controller
    ├── truy vấn DB / gọi service / phân quyền
    ├── tạo domain model / DTO
    ├── render template hoặc Jackson serialize
    └── ghi TOÀN BỘ bytes vào response wrapper
    │
    ▼
Filter lấy body bytes
    ├── kiểm tra response có eligible không
    ├── băm MD5 bytes, tạo ETag
    ├── so với request If-None-Match
    │     ├── khớp → 304, không phát body mới
    │     └── khác → ghi ETag và copy body cho client
    └── kết thúc lượt xử lý
```

**Không nhầm với server-side response cache.** Filter không lưu response đã dựng từ request trước để phục vụ request sau mà không chạy controller. Nó tính lại tag bằng cách tạo lại body trên request đang xử lý.

### 3.1. Ý tưởng thuật toán, không phải source đầy đủ

```java
// PSEUDOCODE, không dùng thay framework.
ContentCachingResponseWrapper wrapper =
        new ContentCachingResponseWrapper(response);

chain.doFilter(request, wrapper);   // Controller đã làm xong!

byte[] bytes = wrapper.getContentAsByteArray();
String etag = md5AsHttpEtag(bytes);

if (ifNoneMatchMatches(request, etag)) {
    response.setStatus(304);
    // Không gửi body đã tính.
} else {
    response.setHeader("ETag", etag);
    wrapper.copyBodyToResponse();
}
```

Mã thật của Spring xử lý thêm các điều kiện trạng thái HTTP, ETag đã có, async lifecycle, response commit, header và stream. Đoạn trên giúp hiểu **thứ tự tính toán**, không phải bản cài đặt đủ điều kiện an toàn.

### 3.2. Mức độ “once per request”

Filter này kế thừa `OncePerRequestFilter` nhưng có xử lý đặc biệt cho async. Không diễn giải `OncePerRequestFilter` thành “chỉ một lần duy nhất bất kể dispatch/thread”. Một HTTP request có thể có initial `REQUEST` dispatch và subsequent `ASYNC` dispatch. Khi được container map đúng types, ShallowEtagHeaderFilter có thể tham gia giai đoạn cuối để tính ETag khi response đã hoàn thành.

### 3.3. Filter tính MD5 để làm gì?

Spring dùng **MD5 digest của response content** làm cơ sở tạo ETag. Mục đích là so sánh nội dung cache, **không** dùng MD5 như chứng cứ chống sửa đổi trước attacker. MD5 có các điểm yếu mật mã đã biết; nếu cần integrity bảo mật, dùng cơ chế chuyên dụng như TLS/chữ ký hoặc SRI trong ngữ cảnh thích hợp.

Nếu bytes đổi dù chỉ một chút, digest thường đổi. Vì vậy các field như request timestamp, random ID, trace ID hay thứ tự serialize không ổn định sẽ làm tỷ lệ hit thấp dù thông tin nghiệp vụ tưởng như không đổi.

## 4. Các điều kiện mặc định để phát shallow ETag

Javadoc Spring 6.x nêu các yếu tố trong `isEligibleForEtag(...)`:

1. Response chưa **committed**.
2. Response status thuộc **2xx**.
3. Request method là **GET**.
4. `Cache-Control` không chứa `no-store` (hoặc không có header).

| Request/response | Có eligible mặc định? | Lý do |
| --- | --- | --- |
| GET 200, không Cache-Control | Có thể | Method/status phù hợp |
| GET 200, `Cache-Control: no-cache` | Có thể | no-cache cho phép lưu với revalidation |
| GET 200, `Cache-Control: no-store` | Không | Chính sách không lưu |
| GET 404 | Không | Không phải 2xx |
| GET 500 | Không | Không phải 2xx |
| POST 201 | Không | Chỉ GET theo default |
| PUT/PATCH/DELETE | Không | Không triển khai conditional write |
| HEAD | Không theo GET-only eligibility mặc định | HEAD có semantics response riêng |
| GET nhưng response committed | Không | Không thể tự sửa headers/status đúng lúc |

**Quan trọng:** nếu response không đủ điều kiện *tạo ETag*, điều đó không có nghĩa mọi wrapper và thao tác ghi body đều không được tạo. Để thực sự tránh buffering cho một route lớn/streaming, nên **loại trừ từ khi đăng ký filter** hoặc gọi API disable caching trước khi ghi.

Có thể override `isEligibleForEtag(...)` trong subclass khi thật sự cần custom policy, nhưng đa số trường hợp nên giữ default và thiết kế endpoint/cache policy rõ ràng.

## 5. Chi phí thật sự: network, CPU, heap và GC

### 5.1. Mô hình chi phí

Gọi:

- `R`: thời gian query DB, gọi remote service, xử lý domain, render/serialize body.
- `H(B)`: chi phí hash response body dài B bytes.
- `M(B)`: chi phí buffer/copy/heap/GC khi giữ B bytes.
- `N(B)`: chi phí truyền B bytes qua network.

```text
GET 200 không có shallow filter:
  server ≈ R
  network ≈ N(B)

GET 200 với shallow:
  server ≈ R + H(B) + M(B)
  network ≈ N(B)

GET 304 với shallow:
  server ≈ R + H(B) + M(B)
  network ≈ lượng headers nhỏ

GET 304 với version/ETag check sớm:
  server ≈ đọc metadata/version rẻ
  network ≈ lượng headers nhỏ
```

Các phép cộng là **mô hình tư duy**, không phải công thức benchmark chính xác cho mọi môi trường. Chi phí nội bộ có thể được tối ưu khác nhau theo Servlet stack/allocator.

### 5.2. Ví dụ bằng số, không phải benchmark

| Công đoạn | GET 200 không filter | Shallow GET 304 | Early GET 304 |
| --- | ---: | ---: | ---: |
| Đọc version | 2 ms | 2 ms | 2 ms |
| Query data | 60 ms | 60 ms | 0 ms |
| Dựng DTO | 30 ms | 30 ms | 0 ms |
| JSON serialize | 20 ms | 20 ms | 0 ms |
| Hash/wrapper | 0 ms | 5 ms | 0 ms |
| Body qua mạng | 600 KiB | 0 KiB | 0 KiB |
| Backend work tổng cộng | 112 ms | 117 ms | 2 ms |

Các số chỉ minh họa để so sánh; không khẳng định rằng 304 shallow luôn chậm hơn 200 bởi độ trễ đo được còn gồm mạng/TLS/proxy/caching. Điều khẳng định được là **render và truy vấn không tự biến mất**.

### 5.3. Bộ nhớ

Nếu wrapper phải giữ 5 MiB response mỗi request, 100 request đồng thời có thể cần khoảng 500 MiB cho **một lớp body bytes**, chưa tính buffers khác, object Java và copy. Kích thước thực tế có thể lớn hơn nhiều. Vì vậy:

- Kiểm tra p95/p99 body size và concurrent requests, không chỉ average.
- Đo allocation rate/GC pauses, heap và RSS.
- Kiểm tra async/streaming endpoints trước khi map filter vào `/**`.
- Đặt thời hạn timeout phù hợp cho các request nặng.
- Không bật shallow cho file tải lớn chỉ vì muốn “HTTP caching chuẩn”.

### 5.4. Khi nào ETag không ổn định?

Body có thể chứa:

```json
{
  "report": "same-result",
  "generatedAt": "2026-10-21T10:01:00Z",
  "nonce": "random-each-request"
}
```

Lần GET sau khác `generatedAt` hoặc `nonce`, nên body hash khác và client lại nhận 200. Nếu những field này không có giá trị nghiệp vụ cần thiết, cân nhắc bỏ chúng khỏi cacheable representation hoặc thay bằng metadata độc lập. Không được làm sai dữ liệu chỉ để giữ hash bằng nhau.

## 6. no-cache, no-store, private và fresh cache

ETag là validator; `Cache-Control` là chính sách storage/freshness:

| Header | Ý nghĩa thực tế |
| --- | --- |
| `no-cache` | Cache có thể lưu nhưng phải revalidate trước khi reuse |
| `no-store` | Cache không được lưu response |
| `private` | Cho cache riêng, không cho shared cache lưu |
| `public, max-age=300` | Cache có thể reuse khi còn fresh 300 giây |
| `max-age=31536000, immutable` | Hữu ích cho URL asset có hash/version bất biến |
| `Vary: Accept-Language` | Những representation ngôn ngữ khác nhau có cache keys phù hợp |
| `Vary: Accept-Encoding` | Phân biệt gzip/br/identity variants theo HTTP semantics |

Một **fresh cache hit ở browser/CDN** có thể giúp request hoàn toàn không tới backend, từ đó tiết kiệm CPU. Một **revalidation gửi tới server và được shallow filter trả 304** vẫn có query/render. Đây là hai tầng tối ưu khác nhau.

Đối với dữ liệu user-specific, luôn cân nhắc `Cache-Control: private` hoặc `no-store`, session/authorization, cookies và shared caches. ETag không thay authentication. Nếu nội dung chứa dữ liệu nhạy cảm cần cấm lưu trữ, hãy ưu tiên `no-store` thay vì cố tạo ETag.

## 7. Strong validator và biến thể HTTP representation

Nếu server hoặc proxy nén body thành gzip/brotli, các encoded representations khác nhau có thể khác về bytes. HTTP strong validator cần đại diện nhất quán cho representation tương ứng; không gắn cùng strong validator cho những variants không tương đương strong một cách vô điều kiện.

Với shallow filter:

- ETag dựa trên bytes được wrapper quan sát tại vị trí filter trong chain.
- Compression có thể xảy ra ở Servlet/filter/proxy và thay đổi representation coding.
- Weak ETag thường phù hợp hơn cho cache revalidation khi hai representations được xem là tương đương về nghĩa, nhưng vẫn cần HTTP semantics và Vary đúng.
- Có proxy/CDN có thể thêm/xóa/sửa ETag; kiểm tra actual response ở nơi client kết nối.
- ETag không chứa “security proof”; không dùng nó làm token phân quyền hoặc checksum chống attacker.

Để tránh lỗi:

1. Dùng `Vary: Accept-Encoding` khi các encoded variants phụ thuộc header này.
2. Kiểm tra ETag response thực sau reverse proxy/CDN.
3. Dùng content-versioned filenames cho assets nếu là frontend static.
4. Test trên browser thật và với một số content encodings.
5. Tránh trộn hai cơ chế cùng tự gắn ETag cho một response nếu chưa hiểu chúng phối hợp.

## 8. Streaming và long responses: khi nào phải tắt shallow caching?

Một response streaming muốn gửi bytes **ngay khi dữ liệu có**, không chờ tạo toàn bộ body. Buffer của shallow filter đi ngược mục tiêu đó.

Các tình huống nên loại trừ:

- `StreamingResponseBody` dùng tải file lớn.
- Server-Sent Events (SSE; `text/event-stream`).
- Download video/audio/range requests.
- CSV xuất hàng triệu dòng hoặc zip export tạo liên tục.
- Response không có điểm kết thúc nhanh.
- Endpoint có dữ liệu nhạy cảm được đánh dấu `Cache-Control: no-store`.

Spring hỗ trợ:

```java
ShallowEtagHeaderFilter.disableContentCaching(request);
```

**Phải gọi trước khi bắt đầu ghi bytes vào response.** API này yêu cầu Servlet request đang đi qua filter; nó điều khiển response caching wrapper của filter. Nó không biến endpoint thành một cơ chế streaming vô hạn có backpressure; bạn vẫn cần thiết kế stream/thread/timeout riêng.

Ví dụ:

```java
@GetMapping("/reports/stream")
public void stream(HttpServletRequest request,
                   HttpServletResponse response) throws IOException {

    ShallowEtagHeaderFilter.disableContentCaching(request);

    response.setContentType("text/plain;charset=UTF-8");
    response.getWriter().write("chunk-one\n");
    response.getWriter().flush();
    response.getWriter().write("chunk-two\n");
    response.getWriter().flush();
}
```

*Đoạn minh họa đặt trong @RestController với import HttpServletRequest, HttpServletResponse và IOException. Ví dụ project đầy đủ ở mục 10.*

Khi hoàn toàn biết trước endpoint nào phải stream, có thể chỉ đăng ký ShallowEtagHeaderFilter cho một URL prefix hẹp **không gồm streaming**. Điều này tránh tạo wrapper ở request vốn không cần xử lý ETag.

### 8.1. Async và DispatcherType.ASYNC

`ShallowEtagHeaderFilter` kế thừa `OncePerRequestFilter` và override `shouldNotFilterAsyncDispatch()` để **không bỏ qua** lượt ASYNC theo mặc định của riêng filter. Mục đích là trì hoãn ETag tới lúc response async hoàn thành.

Nhưng có hai lớp:

1. Servlet container phải **map filter với `DispatcherType.ASYNC`**.
2. Filter nội bộ phải cho phép tham gia lượt ASYNC.

Ví dụ:

```java
registration.setDispatcherTypes(EnumSet.of(
    DispatcherType.REQUEST,
    DispatcherType.ASYNC));
registration.setAsyncSupported(true);
```

Nếu container không map ASYNC, chỉ xem return false của `shouldNotFilterAsyncDispatch` không đủ. Khi một controller trả `Callable` hoặc `DeferredResult`, lượt REQUEST có thể kết thúc khi response chưa hoàn tất; filter cần đúng lifecycle để tính ETag cuối cùng.

### 8.2. Error dispatch và response đã committed

Default eligibility yêu cầu status 2xx và response chưa committed. Khi controller lỗi, response 4xx/5xx thường không được shallow ETag. Khi Servlet đã commit body/header, không thể cứ đổi status thành 304.

Việc lắp nhiều filters như response compression, security, logging và shallow caching yêu cầu kiểm thử order/wrappers. Đừng đăng ký cùng một filter qua `@Component` và `FilterRegistrationBean` một cách ngẫu nhiên.

## 9. Giải pháp mạnh hơn: ETag biết sớm từ version/metadata

Nếu một resource có revision hoặc `lastModified` mà bạn đọc được rẻ, hãy so validator **trước** khi truy vấn đầy đủ.

```text
GET /reports/cheap, If-None-Match: "report-v42"
    │
    ├─ Đọc revision = 42 (rẻ)
    ├─ tạo ETag = "report-v42"
    ├─ WebRequest.checkNotModified(etag)
    │      ├─ true: 304, return sớm
    │      └─ false: tiếp tục
    ├─ Truy vấn dữ liệu lớn
    ├─ Dựng report DTO
    └─ Serialize JSON 200
```

Spring MVC cung cấp `WebRequest.checkNotModified(...)`:

```java
@GetMapping("/reports/cheap")
public Map<String, String> cheap(WebRequest request) {
    String etag = "\"report-v42\"";  // từ revision thật
    if (request.checkNotModified(etag)) {
        return null;                 // không tạo body khi khớp
    }
    return expensiveService.generateReport();
}
```

*Đoạn minh họa (không phải class chạy độc lập); ví dụ hoàn chỉnh bên dưới dùng counter để chứng minh skip.*

Điều kiện tiên quyết: validator phải **thay đổi khi bất kỳ thành phần nào ảnh hưởng representation đổi**. Nếu chỉ lấy version của bảng A nhưng response còn phụ thuộc B, locale, permission hoặc external service, 304 có thể sai và client giữ thông tin lỗi thời. Cần đồng bộ version/snapshot và phân biệt variant.

### 9.1. Không nhầm với optimistic concurrency

`ShallowEtagHeaderFilter` không xử lý `If-Match` cho PUT/PATCH. Nếu client gửi:

```http
PUT /api/reports/7 HTTP/1.1
If-Match: "v42"
Content-Type: application/json

{"title":"Changed"}
```

Thì server phải kiểm tra version/validator **trong transaction hoặc conditional update nguyên tử**. Nếu version sai, trả status phù hợp như 412. Dùng JPA `@Version`, database CAS hoặc optimistic locking đúng cách; shallow ETag của GET không tự bảo vệ data khỏi lost update.

## 10. Demo Spring Boot 3 + Java 17

Dự án làm nổi bật sự khác nhau giữa hai câu hỏi:

- Client nhận bao nhiêu bytes từ server sau revalidation?
- Controller/backend đã tạo response bao nhiêu lần?

Các endpoint:

| Endpoint | Mục đích |
| --- | --- |
| `GET /reports/shallow` | Tạo cùng JSON mỗi lần, shallow filter tính weak ETag |
| `GET /reports/cheap` | Validator version `"report-v1"` biết sớm |
| `GET /reports/no-store` | Chính sách không lưu, không phát shallow ETag mới |
| `GET /reports/stream` | Tắt buffering trước write |
| `GET /metrics` | Counter minh họa mức công việc đã thực hiện |

Dùng Spring Boot **3.3.13**, Java 17+, Maven. Không có database để giữ ví dụ tập trung vào HTTP semantics; trong production, thay counters và version literal bằng nguồn dữ liệu thực.

### 10.1. Cấu trúc

```text
shallow-etag-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── ShallowEtagDemoApplication.java
    │   └── ReportController.java
    └── test/java/example/
        └── EtagBehaviorTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>shallow-etag-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
```

### 10.3. ShallowEtagDemoApplication.java

```java
package example;

import java.util.EnumSet;
import java.util.List;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.web.filter.ShallowEtagHeaderFilter;

@SpringBootApplication
public class ShallowEtagDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShallowEtagDemoApplication.class, args);
    }

    @Bean
    FilterRegistrationBean<ShallowEtagHeaderFilter> etagFilter() {
        ShallowEtagHeaderFilter filter = new ShallowEtagHeaderFilter();
        filter.setWriteWeakETag(true);

        FilterRegistrationBean<ShallowEtagHeaderFilter> registration =
                new FilterRegistrationBean<>(filter);

        registration.setName("shallowEtagFilter");

        // Chỉ áp dụng cho nhóm endpoints đã biết.
        // /reports/cheap dùng version ETag từ domain: không được băm lại.
        registration.setUrlPatterns(List.of(
                "/reports/shallow",
                "/reports/no-store",
                "/reports/stream"));

        registration.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC));
        registration.setAsyncSupported(true);
        registration.setOrder(Ordered.LOWEST_PRECEDENCE - 10);
        return registration;
    }
}
```

**Giải thích cấu hình:**

- `FilterRegistrationBean` là cơ chế Spring Boot đăng ký Servlet Filter với URL patterns.
- `setWriteWeakETag(true)` ghi weak tags cho revalidation, không dùng cho conditional writes.
- `/reports/cheap` không nằm trong filter mapping vì đã có early ETag từ controller.
- ASYNC support được khai báo minh bạch nếu sau này có handler async.
- Không gắn thêm `@Component` cho ShallowEtagHeaderFilter để tránh đăng ký trùng.
- Filter order ảnh hưởng đến các wrappers/security/compression filters khác; cần kiểm thử môi trường triển khai nếu có thêm chúng.

### 10.4. ReportController.java

```java
package example;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.filter.ShallowEtagHeaderFilter;

@RestController
public class ReportController {

    private final AtomicInteger shallowRenderCount = new AtomicInteger();
    private final AtomicInteger cheapRenderCount = new AtomicInteger();

    @GetMapping("/reports/shallow")
    public ResponseEntity<Map<String, String>> shallow() {
        shallowRenderCount.incrementAndGet();

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .body(Map.of("message", "unchanged-report"));
    }

    @GetMapping("/reports/no-store")
    public ResponseEntity<Map<String, String>> noStore() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("message", "sensitive-demo"));
    }

    @GetMapping("/reports/cheap")
    public Map<String, String> cheap(WebRequest request) {
        // Thực tế đọc revision từ metadata trước khi dựng body.
        String etag = "\"report-v1\"";
        if (request.checkNotModified(etag)) {
            return null; // Không tăng counter; không render body
        }

        cheapRenderCount.incrementAndGet();
        return Map.of("message", "unchanged-report");
    }

    @GetMapping("/reports/stream")
    public void stream(HttpServletRequest request,
                       HttpServletResponse response) throws IOException {
        ShallowEtagHeaderFilter.disableContentCaching(request);
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("chunk-one\n");
        response.getWriter().flush();
        response.getWriter().write("chunk-two\n");
        response.getWriter().flush();
    }

    @GetMapping("/metrics")
    public Map<String, Integer> metrics() {
        return Map.of(
                "shallowRenderCount", shallowRenderCount.get(),
                "cheapRenderCount", cheapRenderCount.get());
    }

    public int shallowRenders() {
        return shallowRenderCount.get();
    }

    public int cheapRenders() {
        return cheapRenderCount.get();
    }
}
```

Trong `shallow()`, counter tăng **trước** khi controller trả Map và Jackson tạo body; filter quyết định 304 **sau** quá trình đó. Với `cheap()`, `WebRequest.checkNotModified` chạy trước counter, nên request revalidation trùng có thể return ngay.

`CacheControl.noCache()` không chặn 304; khác với `CacheControl.noStore()`. Endpoint stream gọi `disableContentCaching` trước mọi write để tránh giữ toàn body cho hash.

`/metrics` chỉ phục vụ việc học; trên hệ thống thật, không nên mở tùy ý các counters hoặc thông tin vận hành có thể lộ cấu trúc backend.

### 10.5. Chạy bằng Maven

Trong thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Lần đầu:

```bash
curl -i http://localhost:8080/reports/shallow
```

Kỳ vọng body:

```json
{"message":"unchanged-report"}
```

Response có header `Cache-Control: no-cache` và weak ETag dạng `W/"0..."`. Giá trị hash phụ thuộc bytes thực tế; **đừng tự bịa hoặc hardcode hash**.

Lấy ETag thực và revalidate:

```bash
curl -sS -D headers.txt -o body.json \
  http://localhost:8080/reports/shallow

ETAG=$(grep -i '^ETag:' headers.txt \
  | head -1 | cut -d' ' -f2 | tr -d '\r')

curl -i -H "If-None-Match: $ETAG" \
  http://localhost:8080/reports/shallow

curl -sS http://localhost:8080/metrics
```

Khi hai GET đầu đều xử lý được, response lần hai thường 304, không có body; `shallowRenderCount` đã tăng hai lần. Đó là bằng chứng filter **không bỏ qua controller**.

So sánh:

```bash
curl -i http://localhost:8080/reports/cheap

curl -i -H 'If-None-Match: "report-v1"' \
  http://localhost:8080/reports/cheap

curl -sS http://localhost:8080/metrics
```

Lần revalidate trùng trả 304; `cheapRenderCount` không tăng vì early check đã skip tạo body. Với server đang có nhiều traffic, số counter tuyệt đối có thể khác; quan sát mức tăng khi gọi từng request.

`curl` ở trên dùng cú pháp nối dòng của shell POSIX. Trên Windows PowerShell dùng `curl.exe` và cú pháp biến tương ứng.

### 10.6. no-store và streaming

```bash
curl -i http://localhost:8080/reports/no-store
curl -i http://localhost:8080/reports/stream
```

Với `no-store`, response không nên có ETag mới do shallow filter tạo. Với stream, response là text:

```text
chunk-one
chunk-two
```

Không kết luận “đã tối ưu streaming” chỉ bằng cURL thấy hai dòng: phải đo time-to-first-byte và áp dụng HTTP integration tests nếu streaming thực là yêu cầu trọng yếu.

## 11. Kiểm thử bằng MockMvc

MockMvc không chạy network/TLS/CDN/Servlet container đầy đủ. Để xác nhận hành vi filter, test này **gắn filter trực tiếp** vào MockMvc thay vì giả định MockMvc thực thi mọi cấu hình `FilterRegistrationBean` như embedded Tomcat. Controller instance mới cho mỗi test giúp assertions về counters ổn định.

File `src/test/java/example/EtagBehaviorTest.java`:

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.filter.ShallowEtagHeaderFilter;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class EtagBehaviorTest {

    private ReportController controller;
    private MockMvc filteredMvc;
    private MockMvc plainMvc;

    @BeforeEach
    void setup() {
        controller = new ReportController();
        ShallowEtagHeaderFilter filter = new ShallowEtagHeaderFilter();
        filter.setWriteWeakETag(true);

        filteredMvc = MockMvcBuilders.standaloneSetup(controller)
                .addFilters(filter)
                .build();

        // Controller with early version ETag has no shallow filter.
        plainMvc = MockMvcBuilders.standaloneSetup(controller).build();
    }

    @Test
    void firstGetHasBodyAndWeakEtag() throws Exception {
        MvcResult result = filteredMvc.perform(get("/reports/shallow"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-cache"))
            .andExpect(jsonPath("$.message").value("unchanged-report"))
            .andReturn();

        String etag = result.getResponse().getHeader(HttpHeaders.ETAG);
        assertNotNull(etag);
        assertTrue(etag.startsWith("W/\""));
        assertEquals(1, controller.shallowRenders());
    }

    @Test
    void shallow304StillExecutesControllerTwice() throws Exception {
        MvcResult first = filteredMvc.perform(get("/reports/shallow"))
            .andExpect(status().isOk())
            .andReturn();

        String etag = first.getResponse().getHeader(HttpHeaders.ETAG);
        assertNotNull(etag);

        filteredMvc.perform(get("/reports/shallow")
                    .header(HttpHeaders.IF_NONE_MATCH, etag))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));

        // 304, nhưng backend đã tạo body hai lượt.
        assertEquals(2, controller.shallowRenders());
    }

    @Test
    void unknownValidatorReturnsFull200Response() throws Exception {
        filteredMvc.perform(get("/reports/shallow")
                    .header(HttpHeaders.IF_NONE_MATCH, "\"other\""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("unchanged-report"));

        assertEquals(1, controller.shallowRenders());
    }

    @Test
    void noStoreDoesNotProduceShallowEtag() throws Exception {
        filteredMvc.perform(get("/reports/no-store"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(header().doesNotExist(HttpHeaders.ETAG))
            .andExpect(jsonPath("$.message").value("sensitive-demo"));
    }

    @Test
    void earlyValidatorSkipsSecondRendering() throws Exception {
        plainMvc.perform(get("/reports/cheap"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ETAG, "\"report-v1\""))
            .andExpect(jsonPath("$.message").value("unchanged-report"));

        assertEquals(1, controller.cheapRenders());

        plainMvc.perform(get("/reports/cheap")
                    .header(HttpHeaders.IF_NONE_MATCH, "\"report-v1\""))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));

        // Controller còn xử lý conditional request,
        // nhưng phần tạo payload đã bị bỏ qua.
        assertEquals(1, controller.cheapRenders());
    }

    @Test
    void noValidatorMeansRenderAgain() throws Exception {
        plainMvc.perform(get("/reports/cheap"))
            .andExpect(status().isOk());
        plainMvc.perform(get("/reports/cheap"))
            .andExpect(status().isOk());
        assertEquals(2, controller.cheapRenders());
    }

    @Test
    void streamCanBypassContentCaching() throws Exception {
        filteredMvc.perform(get("/reports/stream"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(HttpHeaders.ETAG))
            .andExpect(content().string(
                    containsString("chunk-one\nchunk-two\n")));
    }

    @Test
    void identicalBodiesHaveSameGeneratedEtag() throws Exception {
        MvcResult one = filteredMvc.perform(get("/reports/shallow"))
            .andExpect(status().isOk())
            .andReturn();
        MvcResult two = filteredMvc.perform(get("/reports/shallow"))
            .andExpect(status().isOk())
            .andReturn();

        assertEquals(
                one.getResponse().getHeader(HttpHeaders.ETAG),
                two.getResponse().getHeader(HttpHeaders.ETAG));
        assertEquals(2, controller.shallowRenders());
    }
}
```

**Điểm quan trọng nhất của tests:** `shallow304StillExecutesControllerTwice` phải chứng minh **304 và counter=2**. Chỉ assert status 304 chưa hề chứng minh giảm công việc server.

Test `earlyValidatorSkipsSecondRendering` chứng minh ngược lại: 304 sau `checkNotModified` nhưng counter tạo body không tăng. Nếu yêu cầu ẩn về async/streaming, hãy kiểm thử thêm trên embedded Servlet container thật vì MockMvc không mô phỏng đầy đủ network buffering hoặc callback lifecycle.

### 11.1. Độ tin cậy và giới hạn của unit/integration tests

- `MockMvcBuilders.standaloneSetup` kiểm thử MVC request pipeline và filter đã gắn thủ công.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` kiểm thử Servlet registration/actual HTTP request trong embedded container.
- Browser hoặc test qua reverse proxy xác minh caching/CORS/TLS/content encoding/cookies.
- Load test đo CPU/DB/GC/latency của workload thật.
- Không dựa vào một microbenchmark MD5 để suy ra hiệu quả của toàn ứng dụng.

## 12. Khi nào nên dùng ShallowEtagHeaderFilter?

| Loại endpoint | Đánh giá | Lý do |
| --- | --- | --- |
| JSON nhỏ, tạo rẻ, ít đổi | Có thể phù hợp | Revalidation giảm băng thông đơn giản |
| HTML nhỏ, không có version rẻ | Có thể phù hợp | Ít công cấu hình, có ETag từ body |
| Dashboard với DB/service calls rất nặng | Không đủ để giảm backend work | Vẫn chạy toàn bộ xử lý |
| API có row version/updatedAt rẻ | Ưu tiên early ETag | Có thể trả 304 trước query/render |
| File CSS/JS đã có hashed filename | Ưu tiên CDN/static resource cache | Phù hợp tầng tài nguyên tĩnh |
| Export vài trăm MiB | Tránh shallow | Body buffering gây memory/latency |
| SSE/streaming | Tránh hoặc disable buffering | Cần flush ngay, không chờ body hoàn chỉnh |
| Dữ liệu user riêng tư cần no-store | Thường không phù hợp | Policy không lưu cache |
| API GET với body timestamp mới mỗi lượt | Hiệu quả thấp | ETag luôn thay đổi |
| PUT/PATCH có If-Match | Không đúng công cụ | Cần version/transaction/concurrency |
| GET qua proxy nén và CDN | Phải kiểm thử representation variants | ETag/Vary/encoding có thể tương tác |

**Không có “bật filter càng rộng càng tốt”.** Với các endpoint có đặc tính rất khác nhau, nên đăng ký URL patterns chọn lọc hoặc có một chính sách loại trừ đã kiểm thử.

## 13. Lỗi phổ biến

| Hiểu nhầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| “304 nghĩa controller không chạy” | Tính sai CPU/DB savings | Với shallow, body đã render mới được so |
| “Filter giữ body cũ trong RAM giữa requests” | Sai kiến trúc, không có server cache | Phân biệt wrapper theo request với response cache |
| “MD5 là chữ ký bảo mật” | Sai threat model | Chỉ dùng MD5 ETag làm cache validator |
| “Weak ETag dùng làm If-Match” | Vi phạm strong comparison | Conditional write cần strong validator riêng |
| “no-cache bằng no-store” | Sai cache policy | no-cache đòi revalidate; no-store cấm lưu |
| “Tắt cache khi response đã gửi xong vẫn giúp stream” | Quá muộn | `disableContentCaching` trước write |
| “Shallow ETag tối ưu download 1 GiB” | Heap/GC/TTFB xấu | Tách streaming/download khỏi filter |
| “set async flag đủ” | Thiếu Servlet dispatcher mapping | Đăng ký cả REQUEST/ASYNC, asyncSupported |
| “CORS/ETag bảo vệ dữ liệu user” | Có thể rò shared cache | Authentication, authorization, private/no-store |
| “Response body cùng nghĩa luôn có cùng bytes” | ETag biến đổi liên tục | Ổn định serialization/fields/variants |
| “Một ETag strong dùng chung gzip/identity vô điều kiện” | Sai representation semantics | Vary/validator đúng từng variant |
| “Filter tự xử lý If-Match PUT” | Lost update | Optimistic locking và If-Match riêng |
| “Bật filter chắc giảm 50% latency” | Không xét render/bandwidth bottleneck | Benchmark p95 CPU/network/GC |
| “Các route cần privacy vẫn nên cache public” | Shared cache có thể rò dữ liệu | Chọn cache policy cẩn thận |
| “Đặt filter cả @Component và RegistrationBean” | Trùng đăng ký khó debug | Một cách registration rõ |
| “304 body có JSON rỗng cần parse” | Client error | Xử lý 304 theo cache/HTTP client |

## 14. Checklist đo lường và tối ưu

Trước khi quyết định bật shallow ETag:

1. Đếm tỷ lệ request có `If-None-Match` và tỷ lệ trả 304.
2. So sánh body bytes truyền và egress trước/sau.
3. Đo p50/p95/p99 latency, CPU và DB query count **trên cả requests 200 và 304**.
4. Đo body size p95/p99, peak heap, allocation rate và GC pause khi concurrency cao.
5. Xác nhận client/browser có thật sự gửi conditional GET và HTTP caches hoạt động như mong muốn.
6. Nếu bottleneck là CPU/DB, ưu tiên lấy version sớm/early ETag hoặc server-side caching.
7. Nếu bottleneck là bandwidth cho assets, dùng content-hashed static filenames, max-age/CDN.
8. Nếu body lớn/streaming, loại trừ khỏi shallow filter, kiểm tra flush và timeout.
9. Nếu response theo locale/authorization/encoding, kiểm tra `Vary`, `private`, `no-store` và role checks.
10. Kiểm tra gzip/proxy interactions, async dispatch, ETag header cuối cùng.
11. Dùng MockMvc cho logic và HTTP integration tests cho network/container.
12. Không dùng 304 như “bằng chứng” hệ thống đã giảm tải backend nếu chưa có metrics.

## 15. Câu hỏi ôn tập

**1.** `ShallowEtagHeaderFilter` tính ETag trước hay sau controller?  
**Đáp án:** Sau khi response body đã được tạo.

**2.** Khi ETag trùng, filter trả status gì?  
**Đáp án:** 304 Not Modified cho conditional GET phù hợp.

**3.** 304 shallow có bỏ qua SQL query không?  
**Đáp án:** Không. Query có thể đã thực hiện đầy đủ.

**4.** Lợi ích chính của shallow 304 là gì?  
**Đáp án:** Giảm bytes body truyền qua mạng.

**5.** Filter sử dụng hash gì để tạo ETag từ bytes?  
**Đáp án:** MD5 theo implementation Spring 6.x.

**6.** Mục đích `setWriteWeakETag(true)`?  
**Đáp án:** Sinh weak ETag dạng `W/"..."`.

**7.** Có nên dùng weak shallow ETag trong `If-Match` không?  
**Đáp án:** Không; cần strong comparison và concurrency control riêng.

**8.** `Cache-Control: no-store` có eligible shallow ETag mặc định không?  
**Đáp án:** Không.

**9.** `Cache-Control: no-cache` có cấm lưu response không?  
**Đáp án:** Không, nó đòi revalidation trước reuse.

**10.** Nếu body 20 MiB, giữ toàn body trong filter có tác hại gì?  
**Đáp án:** Tăng memory/GC và trì hoãn bytes được flush.

**11.** Làm sao stream mà không bị shallow buffer?  
**Đáp án:** Không đăng ký filter cho route hoặc gọi `disableContentCaching(request)` trước write.

**12.** Vì sao cần `DispatcherType.ASYNC`?  
**Đáp án:** Cho phép filter tham gia dispatch kết thúc async và tạo ETag lúc đúng.

**13.** Có version metadata rẻ thì nên làm gì?  
**Đáp án:** `WebRequest.checkNotModified(etag)` trước phần render đắt đỏ.

**14.** Nếu version không đổi nhưng body thay, early 304 có đúng không?  
**Đáp án:** Không; cần validator phản ánh toàn bộ representation.

**15.** HTTP `If-None-Match` và `If-Match` cùng mục đích không?  
**Đáp án:** Không; revalidation và write preconditions khác nhau.

**16.** Vì sao timestamp/random field giảm tỷ lệ 304?  
**Đáp án:** Body bytes luôn đổi, kéo ETag hash đổi.

**17.** CDN cache hit không gửi request backend có giảm server CPU không?  
**Đáp án:** Có thể, nhưng đó là lợi ích tầng cache, không phải filter tự tránh handler.

**18.** Đo metric nào để chứng minh tối ưu thực sự?  
**Đáp án:** CPU/DB/GC/latency cùng bytes egress và tỷ lệ 304.

**19.** ETag có thay authentication hay authorization không?  
**Đáp án:** Không. Validator không quyết định quyền truy cập.

**20.** Status 304 có JSON body mới không?  
**Đáp án:** Không có representation body mới.

## 16. Tài liệu chính thức

- [Spring Framework 6.2 — Shallow ETag Filter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): buffer body, MD5, 304 và giới hạn CPU, mapping ASYNC.
- [Spring Framework 6.2 — ShallowEtagHeaderFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html): `setWriteWeakETag`, eligibility, `disableContentCaching`.
- [Spring Framework 6.2 — HTTP Caching](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-caching.html): conditional GET, `WebRequest.checkNotModified` và ETag/Last-Modified.
- [Spring MVC — Async Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Servlet MVC async request lifecycle.
- [Spring Boot 3.3 — Servlet Filters](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): FilterRegistrationBean.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ETag validators, 304, HTTP conditional requests.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): Cache-Control, freshness/revalidation và cache storage.
- [Spring Framework — MVC Test](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): MockMvc testing.

**Kết luận:** `ShallowEtagHeaderFilter` cần **toàn bộ body** trước khi tính ETag. 304 của nó giúp tiết kiệm băng thông, **không làm biến mất truy vấn, serialize và render đã chạy**. Với dữ liệu có revision rẻ, early conditional GET mới giúp backend bỏ qua công việc nặng. Với streaming, body lớn, dữ liệu riêng tư hoặc nhiều variants, cần chính sách caching phù hợp và kiểm chứng bằng số liệu thực tế.
