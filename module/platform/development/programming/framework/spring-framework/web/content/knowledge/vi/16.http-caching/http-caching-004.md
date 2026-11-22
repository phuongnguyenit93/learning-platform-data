# Spring MVC — WebRequest.checkNotModified và cấu hình cache trên ResponseEntity

## 1. Mục tiêu

Một trang tin, tài liệu, ảnh đại diện hoặc endpoint JSON thường được gọi lại nhiều lần dù nội dung chưa thay đổi. Nếu lần nào server cũng gửi toàn bộ response body, hệ thống lãng phí băng thông, thời gian truyền và công sức serialize dữ liệu. HTTP caching cung cấp hai cơ chế bổ sung:

1. **Freshness caching:** server gửi `Cache-Control` để browser/proxy biết một phản hồi có thể được tái sử dụng mà chưa cần gọi server trong bao lâu.
2. **Conditional request / revalidation:** client gửi validator đã nhận trước đó, như `If-None-Match` hoặc `If-Modified-Since`; nếu representation chưa thay đổi, server trả **304 Not Modified**, thường không có response body.

Spring MVC hỗ trợ cả hai theo hai con đường quan trọng:

- `WebRequest.checkNotModified(...)`: controller **chủ động kiểm tra điều kiện sớm**, có thể ngừng xử lý trước phần tạo view/body tốn kém.
- `ResponseEntity`: controller cấu hình `Cache-Control`, `ETag` và `Last-Modified` trên builder; Spring MVC **có hỗ trợ tự xử lý conditional GET/HEAD** dựa trên validators của response.

Mục tiêu bài học:

- Hiểu `ETag`, `Last-Modified`, `If-None-Match`, `If-Modified-Since`, `If-Match`, `If-Unmodified-Since` và status **200/304/412**.
- Phân biệt `Cache-Control: no-cache` với `no-store`, `private` với `public`, `max-age` với revalidation.
- Sử dụng đúng ba overload `checkNotModified(long)`, `checkNotModified(String)` và `checkNotModified(String,long)`.
- Tạo `ResponseEntity.ok().cacheControl(...).eTag(...).lastModified(...).body(...)` và biết lúc nào Spring MVC có thể đổi phản hồi thành 304.
- Biết ranh giới tối ưu hiệu năng: kiểm tra metadata sớm trước khi render view khác với tạo cả DTO/body rồi mới để framework kiểm tra.
- Tránh lỗi cache dữ liệu người dùng, ETag sai khi biểu diễn thay đổi, header Vary thiếu, timestamp không ổn định và việc trả body trong 304.
- Chạy ví dụ Maven/Java 17/Spring Boot 3.5.0 có cả HTML view và REST JSON, kiểm thử MockMvc qua nhiều conditional requests.

**Phạm vi:** Spring Framework 6.2, **Spring MVC Servlet stack**. Chương trình học là ứng dụng minh họa cache HTTP; muốn triển khai production phải xem xét proxy/CDN, authentication, ETag của từng representation và cache policy dữ liệu nhạy cảm.

## 2. HTTP cache là một giao thức, không phải một Map trong Java

HTTP caching không giống `@Cacheable` của Spring Cache.

| Cơ chế | Ai giữ nội dung? | Đối tượng được tối ưu | Ví dụ |
| --- | --- | --- | --- |
| HTTP browser cache | Browser hoặc HTTP cache phía client | Băng thông, độ trễ tải lại | `Cache-Control`, `ETag` |
| Shared HTTP cache | CDN, gateway hoặc reverse proxy | Giảm số request tới origin | `public, max-age, s-maxage` |
| Spring Cache `@Cacheable` | Application/cache provider (Caffeine, Redis…) | Tránh tính toán/query service lặp lại | `@Cacheable("articles")` |
| Database query optimization | DB engine | Query latency/load | Index, execution plan |

Một endpoint có thể sử dụng cả Spring Cache và HTTP Cache, nhưng **hai lifecycle độc lập**. `@Cacheable` không tự phát `ETag`, và `ResponseEntity.cacheControl(...)` không tự đưa một Java object vào Redis.

### 2.1. HTTP cache có hai giai đoạn

~~~text
GET /api/articles/42
  -> HTTP 200 OK
     Cache-Control: private, no-cache
     ETag: "article-42-v7"
     Last-Modified: Thu, 01 Jan 2026 10:00:00 GMT
     Body: {"id":42,"title":"HTTP caching","version":7}

Client lưu representation + validators.

Lần GET sau:
  GET /api/articles/42
  If-None-Match: "article-42-v7"

Nếu nội dung chưa thay đổi:
  <- HTTP 304 Not Modified
     ETag: "article-42-v7"
     (không gửi lại representation body)

Browser tái sử dụng representation đã lưu.
~~~

Trong ví dụ `no-cache` vẫn **cho phép lưu**, nhưng yêu cầu kiểm tra với server trước khi tái sử dụng. Do đó cặp `no-cache + ETag` rất phù hợp để luyện tập conditional requests.

Nếu server gửi `Cache-Control: max-age=300` cho response có thể cache, client được phép sử dụng representation tươi trong khoảng freshness window theo quy tắc HTTP mà **không nhất thiết gọi server**. Muốn quan sát 304 bằng browser cần chờ stale, yêu cầu revalidation, hoặc chủ động gửi conditional headers.

## 3. Vai trò của Cache-Control trong cấu hình response

**Cache-Control** quy định điều kiện **lưu, freshness và tái sử dụng** response; ETag và Last-Modified chỉ cho biết **cách revalidate** một representation đã lưu. Đó là hai câu hỏi khác nhau: một response có ETag chưa chắc được phép cache, và một response còn fresh có thể được dùng lại mà không gửi conditional GET.

Chọn chính sách trước khi viết controller: dữ liệu public có thể dùng max-age; dữ liệu riêng tư chỉ phù hợp private cache nếu mức nhạy cảm cho phép; response bí mật thường nên no-store. **no-cache** vẫn cho phép lưu nhưng buộc revalidate trước khi tái sử dụng, khác hẳn **no-store**. **private** không thay thế authentication/authorization hay chính sách cache key tại CDN.

Khi endpoint trả các biến thể theo header/locale/user, phải kiểm tra Vary, quyền truy cập và ETag ứng với selected representation. Đừng đặt public chỉ vì muốn tăng tốc; chính sách caching dữ liệu cá nhân cần được kiểm thử riêng.

### 3.1. Spring CacheControl API

Spring cung cấp `org.springframework.http.CacheControl`:

~~~java
CacheControl.noCache();                            // no-cache
CacheControl.noStore();                            // no-store
CacheControl.noCache().cachePrivate();             // no-cache, private
CacheControl.maxAge(Duration.ofMinutes(5));        // max-age=300
CacheControl.maxAge(Duration.ofHours(1))
        .cachePublic().mustRevalidate();           // max-age=3600, must-revalidate, public
~~~

Import `java.time.Duration`. Thứ tự directives thực tế có thể thay đổi; kiểm tra ý nghĩa chứ không cố phụ thuộc vị trí chuỗi khi không cần. `CacheControl#cachePrivate()` và `#cachePublic()` là lựa chọn **ngữ nghĩa HTTP**, không kiểm tra quyền của user.

## 4. ETag: validator ổn định cho selected representation

ETag là định danh phiên bản representation do server cấp, ví dụ **"article-42-v7"**. Strong tag và weak tag (tiền tố W/) có semantics so sánh khác nhau: If-None-Match cho GET/HEAD dùng weak comparison, còn If-Match cho thao tác cập nhật cần strong comparison. ETag **không phải token xác thực**, không tự xác minh quyền đọc dữ liệu.

Trong triển khai ResponseEntity, ETag có thể bắt nguồn từ version DB hoặc hash payload nếu mọi thay đổi có ý nghĩa với representation đều làm validator thay đổi. Cùng URL có JSON ngôn ngữ/encoding khác nhau thì một strong ETag chung có thể không đúng; hãy thiết kế các biến thể cùng Vary chính xác. Hash cả body cho mỗi request có thể tốn CPU; nếu có metadata phiên bản, mục 6 cho thấy cách short-circuit sớm bằng WebRequest.checkNotModified.

### 4.2. Không lấy timestamp hiện tại làm ETag

Sai:

~~~java
String etag = "\"" + System.currentTimeMillis() + "\"";
~~~

Mỗi request sinh ETag mới → client không bao giờ revalidate thành công dù nội dung không đổi. Dùng version/hash hoặc metadata **ổn định đến khi content thật thay đổi**.

Tương tự, nếu ETag dựa trên id đơn thuần mà body cập nhật, client có thể giữ phiên bản cũ vì ETag không đổi. Validator phải gắn với phiên bản representation, không phải chỉ là resource identity.

### 4.3. If-None-Match và ưu tiên điều kiện

Nếu client gửi:

~~~http
If-None-Match: "article-42-v7"
If-Modified-Since: Thu, 01 Jan 2026 10:00:00 GMT
~~~

HTTP semantics quy định `If-None-Match` được ưu tiên cho việc quyết định not-modified; không nên để `If-Modified-Since` làm điều kiện **OR** độc lập khi ETag không khớp.

Các cách sử dụng khác:

~~~http
If-None-Match: *
~~~

thường có nghĩa request cần điều kiện không có representation hiện tại, hữu ích cho conditional create/update APIs theo semantics riêng. Đừng xem `*` như một tag thường.

So sánh với `If-Match`: header đó phục vụ optimistic concurrency, cần strong validator matching theo chuẩn cho cập nhật tài nguyên; không cùng mục tiêu "GET lại nhẹ hơn" của `If-None-Match`.

## 5. Last-Modified và If-Modified-Since

Server có thể phát:

~~~http
Last-Modified: Thu, 01 Jan 2026 10:00:00 GMT
~~~

Client lần sau gửi:

~~~http
If-Modified-Since: Thu, 01 Jan 2026 10:00:00 GMT
~~~

Nếu representation chưa bị sửa sau thời điểm này, server có thể trả 304. `Last-Modified` là thời gian cập nhật **của representation/resource**, không phải lúc server nhận request.

### 5.1. Tính chính xác và giới hạn timestamp

HTTP-date có độ phân giải **giây**. Java `Instant` chứa nano giây, DB `updated_at` có thể chính xác tới milli/nano. Nếu tài nguyên bị sửa **hai lần trong cùng một giây**, chỉ dùng Last-Modified có thể không phân biệt hai phiên bản như ETag.

Khuyến nghị:

- Dùng timestamp tồn tại thật, không tự gán `Instant.now()` ở mỗi GET.
- Ưu tiên ETag ổn định khi cần versioning chính xác hơn.
- Có thể gửi **cả ETag và Last-Modified**; khi cả hai conditional headers tồn tại, ETag có độ ưu tiên phù hợp theo chuẩn.
- Không phát timestamp nằm ở tương lai tùy tiện; clock skew có thể ảnh hưởng caching.
- Chỉ gửi Last-Modified của nội dung được đại diện, không lấy giờ khởi động ứng dụng làm giá trị chung cho tất cả resources.

### 5.2. Last-Modified trong Java Spring

`ResponseEntity.HeadersBuilder` hỗ trợ:

~~~java
.lastModified(instant)
.lastModified(zonedDateTime)
.lastModified(epochMillis)
~~~

Trong đó `instant` là `java.time.Instant`; `epochMillis` là `long` milliseconds từ Unix epoch. Nên dùng `Instant`/`ZonedDateTime` để tránh nhầm đơn vị giữa seconds và milliseconds.

Khi dùng `WebRequest.checkNotModified(long)`, tham số **là millis**, ví dụ:

~~~java
long lastModifiedMillis = article.updatedAt().toEpochMilli();
if (webRequest.checkNotModified(lastModifiedMillis)) {
    return null;
}
~~~

Đây là fragment của một handler view MVC; ví dụ chạy đầy đủ ở mục 10.

## 6. WebRequest.checkNotModified: kiểm tra điều kiện sớm

Import:

~~~java
import org.springframework.web.context.request.WebRequest;
~~~

Ba overload chính:

| Phương thức | Validator được kiểm | Sử dụng |
| --- | --- | --- |
| `checkNotModified(long lastModifiedTimestamp)` | Last-Modified | Khi có timestamp đáng tin |
| `checkNotModified(String eTag)` | ETag | Khi có validator phù hợp |
| `checkNotModified(String eTag, long lastModifiedTimestamp)` | Cả ETag và Last-Modified | Khi muốn công bố cả hai validators |

Giá trị trả về:

- **`true`:** request không cần xử lý nội dung tiếp theo theo điều kiện hiện tại; với GET/HEAD phù hợp Spring chuẩn bị response **304 Not Modified**, còn với các phương thức/điều kiện không an toàn có thể là **412 Precondition Failed**.
- **`false`:** request cần được xử lý bình thường. Bạn có thể chuẩn bị model/view hoặc tiếp tục logic ứng dụng.

`WebRequest.checkNotModified(...)` còn có thể thiết lập ETag/Last-Modified headers và HTTP status trên servlet response trong ngữ cảnh MVC. Bạn không phải viết một chuỗi so ETag thủ công cho conditional GET thông thường.

### 6.1. Ví dụ view handler

~~~java
@GetMapping("/articles/{id}/page")
public String articlePage(
        @PathVariable long id,
        WebRequest request,
        Model model) {

    Article article = store.find(id);
    if (request.checkNotModified(
            article.etag(), article.updatedAt().toEpochMilli())) {
        return null; // MVC đã xử lý kết quả conditional request.
    }

    model.addAttribute("article", article);
    return "article-detail";
}
~~~

Đây là fragment trong `@Controller` có view template, model/service phù hợp. Nếu không thay đổi, Spring có thể bỏ qua bước dựng model/render view và trả 304. Đường 200 vẫn render HTML bình thường.

**Lợi ích:** khi chỉ cần lấy metadata nhẹ từ DB để biết version/timestamp, có thể check sớm rồi **không query toàn bộ graph, không render view/JSON body** nếu client đã có representation. Trong fragment này, `store.find(id)` đang lấy cả article; tối ưu lớn nhất đạt được nếu ứng dụng production tách query nhẹ lấy metadata và query nặng tải nội dung.

### 6.2. Không dùng WebRequest để thay mọi điều kiện nghiệp vụ

`checkNotModified` hoạt động với HTTP conditional headers theo contract của Spring, **không tự bảo đảm optimistic locking ở database**. Với PUT/PATCH/DELETE, vẫn cần kiểm tra quyền, entity version và thực hiện thay đổi atomically trong transaction để tránh race.

Nếu controller đọc version, kiểm `If-Match`, sau đó một request khác cập nhật DB trước khi mình ghi, kiểm HTTP trước đó không giải quyết race. Cần kiểm version ngay trong SQL update hoặc optimistic locking (ví dụ JPA `@Version`) và map conflict đúng.

### 6.3. GET, HEAD và unsafe methods

- GET/HEAD có `If-None-Match` khớp → thường 304, **không có response representation body**.
- PUT/POST/DELETE có điều kiện precondition thất bại → có thể 412. Đừng biến 304 thành kết quả cập nhật.
- `If-Match` thường được dùng với **strong comparison** cho optimistic concurrency.
- `If-Unmodified-Since` là một precondition dựa trên timestamp; yếu hơn strong ETag khi có hai thay đổi trong cùng một giây.
- `304` không phải mã báo resource được cập nhật thành công; nó chỉ cho biết client có thể tái sử dụng representation đã lưu.

## 7. ResponseEntity: cache headers và conditional handling tự động

Trong REST controller trả `ResponseEntity<T>`, Spring có builder rất tiện:

~~~java
@GetMapping("/api/articles/{id}")
public ResponseEntity<ArticleDto> article(@PathVariable long id) {
    Article article = store.find(id);
    ArticleDto dto = new ArticleDto(
            article.id(), article.title(), article.body(), article.version());

    return ResponseEntity.ok()
            .cacheControl(CacheControl.noCache().cachePrivate())
            .eTag(article.etag())
            .lastModified(article.updatedAt())
            .body(dto);
}
~~~

Trong Spring MVC 6.2, việc trả `ResponseEntity` có ETag/Last-Modified giúp framework **xử lý conditional response** cho GET/HEAD: khi validator khớp, client có thể nhận 304 và không có body; không cần bạn tự viết:

~~~java
if (request.getHeader("If-None-Match").equals(etag)) {
    return ResponseEntity.status(304).build();
}
~~~

Phản ví dụ tự so thủ công còn thiếu xử lý weak/strong tags, list validators, wildcard, precedence và malformed headers. Hãy dùng API của Spring/HTTP semantics.

**Giới hạn tối ưu:** với `ResponseEntity` như trên, controller **đã thực thi `store.find` và xây `dto` trước khi framework quyết định gửi 304**. Vẫn tiết kiệm **serialization/network body**, nhưng có thể chưa tiết kiệm toàn bộ truy vấn/tính toán để dựng DTO. Nếu body rất tốn kém, dùng `WebRequest.checkNotModified` sớm tại handler hoặc kiến trúc metadata query trước.

### 7.1. Các builder methods

| Builder | Header HTTP | Lưu ý |
| --- | --- | --- |
| `.cacheControl(CacheControl.noCache())` | `Cache-Control: no-cache` | Cache phải revalidate |
| `.cacheControl(CacheControl.noStore())` | `Cache-Control: no-store` | Không nên lưu bản sao |
| `.cacheControl(CacheControl.maxAge(Duration.ofMinutes(5)))` | `Cache-Control: max-age=300` | Cho phép freshness |
| `.eTag("article-42-v7")` | `ETag: "article-42-v7"` | Spring hỗ trợ thêm dấu quote |
| `.eTag("W/\"article-v7\"")` | `ETag: W/"article-v7"` | Weak validator theo cú pháp |
| `.lastModified(Instant)` | `Last-Modified: <HTTP-date>` | Là thời điểm cập nhật thực |
| `.varyBy(HttpHeaders.ACCEPT_LANGUAGE)` | `Vary: Accept-Language` | Khi response phụ thuộc ngôn ngữ |
| `.body(dto)` | Representation JSON được serialize | Không có nghĩa là luôn gửi body nếu 304 |
| `.build()` | ResponseEntity không body | Ví dụ `noContent()` hoặc `notFound()` |

Nếu response còn khác theo `Accept-Encoding`, `Accept-Language`, `Origin` hoặc các request headers khác, cần đảm bảo **Vary/validator đúng theo biểu diễn**. Không thêm Vary tùy tiện nếu response không thay đổi theo header đó; làm vậy tăng số cache variants không cần thiết.

### 7.2. Khi nào chủ động kiểm tra WebRequest thay vì chỉ dùng ResponseEntity?

Chọn `ResponseEntity` thuần khi:

- DTO được dựng rẻ hoặc dữ liệu đã có sẵn.
- Bạn ưu tiên code ngắn, cache policy ngay trong API response.
- Tiết kiệm payload/serialization là lợi ích chính.

Chọn `WebRequest.checkNotModified` sớm khi:

- Metadata version/lastModified có thể query rẻ hơn nội dung đầy đủ.
- Render view hoặc chuẩn bị representation tốn tài nguyên.
- Bạn cần kiểm tra điều kiện trước khi gọi service nặng và có thiết kế dữ liệu hỗ trợ.

**Tránh kiểm tra hai lần không cần thiết:** nếu bạn dùng `WebRequest.checkNotModified` đã xử lý 304, đừng thêm tầng tự so ETag thủ công rồi vẫn để MVC auto-conditional một cách khó kiểm soát. Chọn một flow rõ, kiểm thử cả response headers.

## 8. 304 Not Modified: response không có body

Ví dụ request:

~~~http
GET /api/articles/42 HTTP/1.1
If-None-Match: "article-42-v7"
~~~

Nếu current ETag khớp:

~~~http
HTTP/1.1 304 Not Modified
ETag: "article-42-v7"
Cache-Control: private, no-cache
Last-Modified: Thu, 01 Jan 2026 10:00:00 GMT
~~~

**Không có JSON body** `{"message":"not modified"}` trong 304. Client phải có representation đã lưu để dùng lại; 304 chỉ thông báo có thể tái sử dụng representation đó theo cache semantics.

Đừng tự biến 304 thành 200 body rỗng. Cũng không nên cho một REST client cố parse JSON từ 304 như thể luôn nhận 200:

~~~javascript
const response = await fetch("/api/articles/42", {
  headers: {"If-None-Match": '"article-42-v7"'}
});

if (response.status === 304) {
  // Dùng representation mà client đã lưu trong cache ứng dụng.
} else if (response.ok) {
  const article = await response.json();
}
~~~

Với browser-managed HTTP cache, browser có thể tự quản lý revalidation và trình bày một response thích hợp cho script; ví dụ JavaScript trên là **cơ chế tự quản lý validator ở client**, không phải mô tả bắt buộc của mọi browser cache implementation.

### 8.1. Headers trên 304

304 cần duy trì metadata cache có liên quan như `ETag`, `Last-Modified`, `Cache-Control`, `Vary` theo HTTP semantics và cấu hình thực tế. Nếu response 304 không có cache policy như bản 200 hoặc `Vary` thay đổi thiếu nhất quán, shared caches/clients có thể xử lý không như mong đợi.

Spring MVC giúp xây các headers khi dùng validators, nhưng với custom filters/proxy và conditional handling thủ công cần kiểm thử. Không thêm `Content-Type: application/json` rồi cố gửi JSON body trong 304.

### 8.2. 304 không có nghĩa chỉ cần HTTP status

304 không làm server “biết” client đang giữ payload nào. Nó dựa trên validators của **selected representation** đúng resource URL (và biến thể Vary). Nếu bạn đổi định dạng, ngôn ngữ hoặc quyền xem mà vẫn dùng ETag cũ, client có thể tái sử dụng representation không phù hợp.

### 8.3. HEAD

HEAD giống GET về ngữ nghĩa truy xuất nhưng không gửi body. Cache validators cũng có thể áp dụng. Nên kiểm thử HEAD nếu API hỗ trợ, nhưng đừng giả định mọi custom streaming/filter đều đúng nếu chưa test.

## 9. Quyết định cache policy theo mức nhạy cảm

| Endpoint | Ví dụ policy gợi ý | Lý do |
| --- | --- | --- |
| File JS/CSS có content-hash trong URL | `public, max-age=31536000, immutable` | URL đổi khi bytes đổi |
| Catalog public ít thay đổi | `public, max-age=60` + ETag | CDN/client được cache trong thời gian ngắn |
| Article public cập nhật thường xuyên | `public, no-cache` + ETag | Cho phép lưu nhưng luôn revalidate |
| Dashboard cá nhân | `private, no-cache` nếu chính sách cho phép lưu | Không để shared cache giữ nội dung per-user |
| Response nhạy cảm chứa token/thông tin bí mật | `no-store` | Giảm rủi ro lưu response |
| Stream sự kiện, một số status mutation | Cần đánh giá riêng; thường không cache như resource GET | HTTP semantics khác |
| Kết quả POST tạo tài nguyên | Thường không mặc định cho shared cache; trả 201 + Location | Client có thể GET resource sau |

Đây là **gợi ý thiết kế**, không phải luật cứng. Với dữ liệu riêng tư, một số chính sách bảo mật yêu cầu `no-store` thay vì `private, no-cache`. `private` không bảo vệ khỏi XSS, máy khách bị truy cập trái phép hay lộ dữ liệu trên chính browser.

### 9.1. Cache nội dung có Authorization hoặc Cookie

Nếu GET phụ thuộc user/session:

- Không đánh dấu `public` chỉ vì URL giống nhau cho mọi user.
- Có thể dùng `private` để shared caches không lưu, hoặc `no-store` nếu dữ liệu không được lưu tại client.
- Server vẫn phải kiểm tra authentication/authorization trên mỗi request thực sự đến backend; 304 không phải bypass quyền.
- Nếu representation khác nhau theo ngôn ngữ/encoding, dùng `Vary` và validators đúng biến thể. **Không dùng `Vary: Cookie` như một giải pháp bảo mật toàn diện** — cache policy và authorization mới là trọng tâm.
- Đảm bảo khi user logout/chuyển account, cơ chế cache không khiến data cũ bị trình bày không phù hợp với policy.

### 9.2. CDN và shared cache

Khi có CDN, kiểm tra `s-maxage`, `public/private`, proxy cache key, `Vary`, authentication headers và invalidation. Một reverse proxy có thể phục vụ GET mà request không tới Spring controller khi cache còn fresh. Đó là lý do logs backend không nhất thiết ghi nhận mọi lần user tải trang.

## 10. Dự án chạy được: WebRequest + ResponseEntity

Dự án Spring Boot 3.5.0/Java 17 sử dụng **một article version 7** với timestamp cố định `2026-01-01T10:00:00Z` để minh họa validator ổn định. Hai endpoint:

- `GET /articles/42/page` trả HTML qua Thymeleaf và kiểm tra sớm bằng `WebRequest.checkNotModified(...)`.
- `GET /api/articles/42` trả JSON `ResponseEntity` chứa `Cache-Control/ETag/Last-Modified` và để Spring MVC xử lý conditional GET.
- `GET /api/private-example` minh họa `CacheControl.noStore()` (không có thông tin nhạy cảm thật).

Ứng dụng không có database, không có authentication. Đây là demo deterministic để phân biệt rõ 200/304, không phải bộ thiết kế production cho cache dữ liệu người dùng.

### 10.1. Cấu trúc

~~~text
http-cache-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/HttpCacheApplication.java
    │   └── resources/templates/article-detail.html
    └── test/java/demo/HttpCacheTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>http-cache-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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
~~~

### 10.3. HttpCacheApplication.java

Toàn bộ Java dưới đây nằm trong **một file** `src/main/java/demo/HttpCacheApplication.java`. Chỉ class khởi động `HttpCacheApplication` là public top-level class; các record và controller package-private.

~~~java
package demo;

import java.time.Instant;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Service;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class HttpCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpCacheApplication.class, args);
    }
}

record Article(
        long id,
        String title,
        String body,
        long version,
        Instant updatedAt) {

    String etag() {
        // Version ổn định: chỉ đổi khi selected representation đổi.
        return "article-" + id + "-v" + version;
    }
}

record ArticleDto(
        long id,
        String title,
        String body,
        long version) {
}

@Service
class ArticleStore {
    private final Article article = new Article(
            42L,
            "HTTP caching",
            "ETag giúp kiểm tra representation có thay đổi hay chưa.",
            7L,
            Instant.parse("2026-01-01T10:00:00Z"));

    Article find(long id) {
        if (id != article.id()) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Article not found");
        }
        return article;
    }
}

@Controller
class ArticlePageController {
    private final ArticleStore store;

    ArticlePageController(ArticleStore store) {
        this.store = store;
    }

    @GetMapping("/articles/{id}/page")
    String page(
            @PathVariable long id,
            WebRequest request,
            Model model,
            HttpServletResponse response) {

        Article article = store.find(id);

        // Đặt cache policy trước khi có thể kết thúc bằng 304.
        response.setHeader(
                HttpHeaders.CACHE_CONTROL, "private, no-cache");

        // WebRequest tự kiểm conditional headers và thiết lập status.
        if (request.checkNotModified(
                article.etag(),
                article.updatedAt().toEpochMilli())) {
            return null; // Không render template khi validator khớp.
        }

        model.addAttribute("article", article);
        return "article-detail";
    }
}

@RestController
class ArticleRestController {
    private final ArticleStore store;

    ArticleRestController(ArticleStore store) {
        this.store = store;
    }

    @GetMapping("/api/articles/{id}")
    ResponseEntity<ArticleDto> getArticle(@PathVariable long id) {
        Article article = store.find(id);

        ArticleDto dto = new ArticleDto(
                article.id(),
                article.title(),
                article.body(),
                article.version());

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache().cachePrivate())
                .eTag(article.etag())
                .lastModified(article.updatedAt())
                .body(dto);
    }

    @GetMapping("/api/private-example")
    ResponseEntity<Map<String, String>> privateExample() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("message", "Demo no-store"));
    }
}
~~~

**Tại sao ví dụ đúng trọng tâm:**

- Giá trị ETag `article-42-v7` được Spring chuẩn hóa thành HTTP header `ETag: "article-42-v7"`.
- Timestamp cố định được Spring đưa thành HTTP-date, không lấy `Instant.now()` mỗi request.
- Controller view kiểm tra trước khi render; HTML template **không chạy** nếu request đủ điều kiện trả 304.
- REST controller trả `ResponseEntity` chứa cả validator và cache policy. Spring MVC có cơ chế kiểm tra điều kiện khi xử lý response, nên client có thể nhận 304 không body dù controller đã tạo DTO.
- `private, no-cache` minh họa browser/private cache có thể lưu rồi revalidate; không dùng cho secrets cần no-store.
- Không có endpoint cập nhật article, vì vậy validator cố định suốt lần chạy. Production phải thay version/timestamp **atomically** khi representation đổi.

### 10.4. article-detail.html

Lưu vào `src/main/resources/templates/article-detail.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Article Detail</title>
</head>
<body>
    <h1 th:text="${article.title}">Article title</h1>
    <p th:text="${article.body}">Article content</p>
    <small>
        Version:
        <span th:text="${article.version}">0</span>
    </small>
</body>
</html>
~~~

Thymeleaf `th:text` HTML-escapes nội dung; tránh `th:utext` với dữ liệu không được sanitize. HTML view này chỉ dùng data công khai giả lập. Cache policy cho trang per-user thật phải được review trước khi áp dụng.

### 10.5. Chạy ứng dụng

Ở thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Lấy JSON và xem headers:

~~~bash
curl -i 'http://localhost:8080/api/articles/42'
~~~

Response có dạng:

~~~http
HTTP/1.1 200
ETag: "article-42-v7"
Last-Modified: Thu, 01 Jan 2026 10:00:00 GMT
Cache-Control: no-cache, private
Content-Type: application/json

{"id":42,"title":"HTTP caching","body":"ETag giúp kiểm tra representation có thay đổi hay chưa.","version":7}
~~~

Thứ tự headers/directives có thể khác; response JSON hiển thị chỉ là representation tương đương của code. Nếu một converter/custom config làm khác byte ordering, xem ETag strong/weak và representation consistency.

### 10.6. Conditional GET qua ETag

~~~bash
curl -i 'http://localhost:8080/api/articles/42' \
  -H 'If-None-Match: "article-42-v7"'
~~~

Nếu validator khớp, HTTP response là **304**, không có JSON body. Đường view tương tự:

~~~bash
curl -i 'http://localhost:8080/articles/42/page' \
  -H 'If-None-Match: "article-42-v7"'
~~~

`WebRequest.checkNotModified(...)` trả true và view không cần được render.

### 10.7. Conditional GET qua Last-Modified

~~~bash
curl -i 'http://localhost:8080/api/articles/42' \
  -H 'If-Modified-Since: Thu, 01 Jan 2026 10:00:00 GMT'
~~~

Với representation/timestamp cố định của demo, client có thể nhận HTTP **304**. Để kiểm tra API REST với ETag **không khớp**:

~~~bash
curl -i 'http://localhost:8080/api/articles/42' \
  -H 'If-None-Match: "article-42-v1"'
~~~

Server nên trả **200** + body, ETag hiện tại `"article-42-v7"`. Khi gửi cả hai conditional headers, lưu ý precedence: ETag không khớp thì không được dùng If-Modified-Since riêng lẻ để ép 304.

### 10.8. Một client theo dõi ETag bằng JavaScript

Ví dụ này là client tự giữ validator:

~~~javascript
let cachedArticle = null;
let previousEtag = null;

async function loadArticle() {
  const headers = {};
  if (previousEtag) {
    headers["If-None-Match"] = previousEtag;
  }

  const response = await fetch("/api/articles/42", {
    headers,
    cache: "no-store" // Chỉ trong ví dụ để tránh browser-managed cache che flow.
  });

  if (response.status === 304) {
    return cachedArticle;
  }
  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  const data = await response.json();
  cachedArticle = data;
  previousEtag = response.headers.get("ETag");
  return data;
}
~~~

Đây là ví dụ quan sát *application-managed validator*. `cache: "no-store"` ở Fetch ảnh hưởng tới browser-managed HTTP cache, không có nghĩa server tự thay `Cache-Control` của response. Trong ứng dụng thực, chọn **một cache strategy thống nhất** và tránh phối hợp request cache mode theo cách không kiểm soát; behavior có thể phụ thuộc browser Fetch implementation. Với frontend cross-origin, muốn JavaScript đọc `ETag` response header còn cần CORS `Access-Control-Expose-Headers: ETag`, và custom request header `If-None-Match` có thể phát sinh preflight.

## 11. MockMvc tests: so response và validators thật

Tạo file `src/test/java/demo/HttpCacheTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class HttpCacheTest {
    @Autowired
    MockMvc mvc;

    @Test
    void jsonFirstGetReturnsCacheMetadataAndBody() throws Exception {
        mvc.perform(get("/api/articles/42"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ETAG, "\"article-42-v7\""))
            .andExpect(header().exists(HttpHeaders.LAST_MODIFIED))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-cache")))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("private")))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void jsonConditionalGetByEtagReturns304WithoutBody()
            throws Exception {
        mvc.perform(get("/api/articles/42")
                .header(HttpHeaders.IF_NONE_MATCH, "\"article-42-v7\""))
            .andExpect(status().isNotModified())
            .andExpect(header().string(
                    HttpHeaders.ETAG, "\"article-42-v7\""))
            .andExpect(content().string(""));
    }

    @Test
    void jsonConditionalGetByLastModifiedReturns304()
            throws Exception {
        MvcResult first = mvc.perform(get("/api/articles/42"))
            .andExpect(status().isOk())
            .andReturn();

        String lastModified = first.getResponse()
                .getHeader(HttpHeaders.LAST_MODIFIED);
        assertNotNull(lastModified);

        mvc.perform(get("/api/articles/42")
                .header(HttpHeaders.IF_MODIFIED_SINCE, lastModified))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void changedEtagRequiresBody() throws Exception {
        mvc.perform(get("/api/articles/42")
                .header(HttpHeaders.IF_NONE_MATCH, "\"article-42-v6\""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void ifNoneMatchTakesPrecedenceOverIfModifiedSince()
            throws Exception {
        MvcResult first = mvc.perform(get("/api/articles/42"))
            .andReturn();
        String date = first.getResponse()
                .getHeader(HttpHeaders.LAST_MODIFIED);
        assertNotNull(date);

        mvc.perform(get("/api/articles/42")
                .header(HttpHeaders.IF_NONE_MATCH, "\"article-42-v6\"")
                .header(HttpHeaders.IF_MODIFIED_SINCE, date))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void htmlPageUsesWebRequestCheckNotModified() throws Exception {
        mvc.perform(get("/articles/42/page"))
            .andExpect(status().isOk())
            .andExpect(view().name("article-detail"))
            .andExpect(content().string(containsString("HTTP caching")));

        mvc.perform(get("/articles/42/page")
                .header(HttpHeaders.IF_NONE_MATCH, "\"article-42-v7\""))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void privateExampleForbidsCacheStorage() throws Exception {
        mvc.perform(get("/api/private-example"))
            .andExpect(status().isOk())
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(jsonPath("$.message").value("Demo no-store"));
    }

    @Test
    void missingResourceIs404() throws Exception {
        mvc.perform(get("/api/articles/999"))
            .andExpect(status().isNotFound());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Test quan trọng:**

1. GET thường trả 200, ETag, Last-Modified, Cache-Control và JSON.
2. Conditional ETag khớp trả 304 không body.
3. If-Modified-Since khớp có thể trả 304.
4. ETag cũ trả 200; If-None-Match không khớp phải được ưu tiên so với If-Modified-Since.
5. View handler của `WebRequest` trả 304 mà không render HTML.
6. Endpoint nhạy cảm giả định minh họa no-store.

Các tests trên chạy ở MockMvc, không kiểm tra CDN, reverse proxy, caches ngoài tiến trình hoặc behavior của browser-managed cache. Với production cần integration/e2e tests cho caching semantics ở hạ tầng thật.

## 12. Điều kiện cập nhật: If-Match và 412 Precondition Failed

Bài học chủ yếu về conditional GET, nhưng cần phân biệt rõ cơ chế **optimistic concurrency** cho write requests.

Giả sử client đọc:

~~~http
GET /api/articles/42
ETag: "article-42-v7"
~~~

Sau đó muốn cập nhật đúng phiên bản đã đọc:

~~~http
PUT /api/articles/42
If-Match: "article-42-v7"
Content-Type: application/json

{"title":"New title"}
~~~

Nếu server hiện đang ở version 8, điều kiện `If-Match` version 7 không đúng, HTTP **412 Precondition Failed** phù hợp. Điều này khác 304 của GET: ở đây mục tiêu là **ngăn ghi đè phiên bản mới**.

### 12.1. Không tự so ETag và update rời rạc

Sai về concurrency:

~~~text
SELECT version FROM article WHERE id=42;  -- trả v7
IF-MATCH == v7? yes
... một request khác sửa article thành v8 ...
UPDATE article SET title='...' WHERE id=42; -- ghi đè mất dữ liệu mới
~~~

Cần thao tác atomically, ví dụ:

~~~sql
UPDATE article
SET title = :newTitle, version = version + 1
WHERE id = :id AND version = :expectedVersion
~~~

Kiểm số row affected để biết có conflict/precondition failure. Với JPA, `@Version` và transaction có thể hỗ trợ optimistic locking, nhưng mapping status 409/412 phải theo contract của API. HTTP If-Match dùng **strong comparison**, weak ETag không phù hợp làm điều kiện mạnh.

### 12.2. WebRequest.checkNotModified có dùng cho POST/PUT/DELETE không?

Spring `WebRequest.checkNotModified` có các xử lý conditional request bao gồm unsafe methods, và khi precondition thất bại có thể đặt 412 thay vì 304. Tuy nhiên nó **không thực hiện database update atomically**, không thay authentication, authorization, validation, transaction và optimistic concurrency control.

Để bảo đảm đúng contract với tất cả HTTP precondition headers và race conditions, xem RFC 9110 cùng Spring WebRequest implementation của phiên bản sử dụng và kiểm thử PUT/PATCH/DELETE riêng. Không copy ví dụ GET rồi áp dụng máy móc cho payment/update operations.

## 13. Các bẫy quan trọng khi triển khai

### 13.1. checkNotModified sau khi đã tốn hết công xử lý

~~~java
ArticleDto dto = veryExpensiveGraphMapping();
if (webRequest.checkNotModified(etag)) {
    return null;
}
~~~

Vẫn tiết kiệm body/network nhưng đã tốn công tính DTO. Nếu khả thi, query version/lastModified trước, check, rồi mới gọi phần nặng. Đừng query DB **hai lần** mà không đánh giá trade-off, transaction consistency và dữ liệu race.

### 13.2. Không cập nhật ETag khi nội dung đổi

Nếu `article.title` đổi mà `article.version` không đổi, client có thể nhận 304 sai và hiển thị nội dung cũ. Gắn validator với một version được tăng atomically khi selected representation thay đổi, hoặc hash chuẩn hóa của bytes.

### 13.3. Dùng Last-Modified = Instant.now() mỗi GET

Client không bao giờ thấy "not modified" vì server tự tuyên bố resource vừa thay đổi mỗi lần. Dùng timestamp tồn tại từ source-of-truth, và cẩn thận độ phân giải giây.

### 13.4. Dùng no-cache như một lệnh “không lưu dữ liệu”

`no-cache` cho phép cache lưu nhưng buộc revalidate; nếu mục tiêu là ngăn lưu nội dung nhạy cảm hãy cân nhắc `no-store`. `private` chỉ ngăn shared cache, không cấm browser cache.

### 13.5. Public caching cho dữ liệu mỗi người

~~~http
Cache-Control: public, max-age=3600
~~~

trên response chứa hồ sơ cá nhân có thể dẫn đến shared cache giữ/trả dữ liệu nhạy cảm. Không kỳ vọng authentication middleware tự điều chỉnh mọi cache semantics theo mong muốn; cấu hình rõ theo resource và proxy.

### 13.6. ETag không phụ thuộc Vary/variant

Nếu body khác theo `Accept-Language`, cần có cache key/`Vary: Accept-Language` và validator phù hợp từng representation. Nếu content encoded gzip khác identity encoding, strong ETag cần phù hợp từng octet representation (hoặc thiết kế weak validator theo contract). Không dùng cùng strong ETag mù quáng.

### 13.7. 304 có JSON body

304 không được gửi body của selected representation. Không tạo response `304 + {"cached":true}` như một API success JSON thông thường.

### 13.8. Tự parse If-None-Match bằng equals một chuỗi

Client có thể gửi nhiều ETags, weak tags, wildcard và các điều kiện kết hợp. Ưu tiên Spring WebRequest/ResponseEntity và HTTP libraries thay vì tự viết parser đơn giản.

### 13.9. CORS che mất ETag cho frontend

Một JS frontend khác origin có thể đọc JSON nhưng không đọc `ETag` response header trừ khi server expose nó qua:

~~~http
Access-Control-Expose-Headers: ETag
~~~

Và nếu frontend tự gửi request header `If-None-Match`, CORS preflight có thể xảy ra, cần allowed headers phù hợp. CORS/credentialed response rules vẫn áp dụng; không mở wildcard bừa để sửa lỗi caching.

### 13.10. Cache ở CDN có thể trả dữ liệu cũ dù backend đã đổi

Nếu CDN còn giữ response fresh, request có thể không tới Spring. Cần versioned URLs, phù hợp `max-age/s-maxage` và invalidation policy nếu ứng dụng yêu cầu cập nhật tức thời. ETag không buộc CDN liên hệ backend khi cache vẫn fresh theo directives.

### 13.11. Lỗi 404 và 500

HTTP caching có quy tắc cho status khác 200; không mặc định tất cả lỗi đều no-store hay đều cache. Nếu muốn cache 404 ngắn hạn, quyết định rõ; với lỗi chứa dữ liệu cá nhân hoặc stacktrace cần chính sách chặn lưu. Cache headers có thể bị proxy/gateway thay thế, nên kiểm thử response thực tế.

### 13.12. HEAD khác GET nhưng không được trả body

HEAD có thể dùng validators/cache metadata. Trong custom filters/interceptors hoặc streaming responses, phải bảo đảm không gửi content body trái HTTP semantics.

## 14. Checklist code review

Trước khi merge một endpoint hỗ trợ HTTP cache, trả lời được:

- **Resource/representation:** URL này biểu diễn dữ liệu gì? Có biến thể theo user, locale, compression, format hoặc auth không?
- **ETag correctness:** ETag ổn định giữa hai lần GET giống nhau, đổi khi representation đổi? Strong hay weak? Có collision không?
- **Last-Modified correctness:** Timestamp từ nguồn dữ liệu thật, đúng đơn vị millis cho WebRequest và format HTTP-date trong response? Có nhiều updates/giây không?
- **Cache-Control:** Chọn `no-store`, `private,no-cache`, `public,max-age` hay `immutable` theo mức nhạy cảm? Có CDN/shared caches không?
- **Conditional handling:** Khi validator khớp có 304 **không body** không? Khi không khớp trả 200 body mới không? If-None-Match có ưu tiên đúng không?
- **Response metadata:** 304 giữ metadata ETag/Last-Modified/Cache-Control/Vary phù hợp không?
- **Performance:** check trước phần tốn kém nếu có thể; ResponseEntity auto 304 nhưng DTO có thể đã tạo rồi.
- **Auth:** Kiểm authentication/authorization theo mọi request và tài nguyên; shared caches không làm rò per-user data.
- **Concurrency:** Write requests dùng If-Match hoặc @Version/atomic update khi cần; 412/409 mapping theo contract.
- **Edge cases:** HEAD, weak tags, wildcard, malformed conditional headers, clock skew, second precision, CORS, gateway cache.
- **Tests:** Tối thiểu GET 200, ETag/Last-Modified, GET 304, không khớp 200, Vary/Cache-Control, no-store cho dữ liệu nhạy cảm và HTTP integration nếu có CDN.

## 15. Bài tập thực hành

**Bài 1 — Giải thích trạng thái:** Client GET `/books/1` nhận ETag `"book-v4"`. Lần sau gửi `If-None-Match: "book-v4"`. Hãy vẽ HTTP 200/304 flow và cho biết 304 có body không.

**Bài 2 — No-cache vs no-store:** Một endpoint thông tin công khai cần revalidation mỗi lượt xem; một endpoint trả token reset password không được lưu. Chọn CacheControl directive phù hợp và giải thích.

**Bài 3 — WebRequest:** Tạo method nhận `WebRequest`, `Model`, `article.version` và `article.updatedAt`. Dùng `checkNotModified(String,long)` để trả sớm nếu GET not modified.

**Bài 4 — ResponseEntity:** Viết controller trả `ResponseEntity<BookDto>` với `CacheControl.maxAge(Duration.ofMinutes(2)).cachePublic()`, ETag từ hash/version và Last-Modified từ DB.

**Bài 5 — Ưu tiên điều kiện:** Client gửi ETag cũ và If-Modified-Since bằng timestamp mới nhất. Phản hồi phải là 200 hay 304 nếu ETag không khớp? Giải thích precedence.

**Bài 6 — Per-user representation:** Một response `/api/me` phụ thuộc cookie session. Có nên cho public CDN cache không? Chọn `private/no-cache` hoặc `no-store` theo mức nhạy cảm, phân tích quyền truy cập.

**Bài 7 — Concurrency:** Hai clients cùng đọc version 7. Client A PUT cập nhật lên version 8. Client B PUT với `If-Match: "v7"`. Status nào phù hợp và tại sao kiểm update/version phải atomic?

**Bài 8 — ETag variant:** API trả JSON khác theo `Accept-Language`. Thiết kế Vary và ETag cho vi-VN/en-US. Hệ quả nếu hai representations có cùng strong ETag dù khác bytes?

**Bài 9 — MockMvc:** Viết test assert ETag, Last-Modified, 304 không body, no-store endpoint và conditional GET với validator không khớp.

**Bài 10 — CDN:** Một bài báo public có `Cache-Control: public, max-age=300`, backend đổi nội dung sau 10 giây. Vì sao user có thể vẫn xem bản cũ trong 5 phút? Khi nào nên dùng no-cache/short max-age/versioned URL?

## 16. Ghi nhớ

- **HTTP cache** giảm network latency; khác với `@Cacheable` của Spring Cache.
- **`Cache-Control`** quy định freshness/storage/revalidation. `no-cache` có thể lưu nhưng phải revalidate; `no-store` nhằm ngăn lưu.
- **`ETag`** là validator cho representation; **`Last-Modified`** là thời điểm cập nhật. ETag có thể chính xác hơn timestamp giây.
- **`If-None-Match` / `If-Modified-Since`** cho conditional GET/HEAD: khi điều kiện phù hợp, **304 Not Modified không body**.
- **`WebRequest.checkNotModified(...)`** cho phép controller kiểm tra sớm và bỏ render/tính toán nếu validator khớp.
- **`ResponseEntity.cacheControl(...).eTag(...).lastModified(...)`** tạo cache headers và để Spring MVC hỗ trợ conditional response, nhưng controller có thể đã dựng DTO trước.
- **`private/public/no-store`** phải chọn theo dữ liệu và shared caches; caching không thay authentication/authorization.
- **Write preconditions** như `If-Match` cùng update atomic giúp chống lost updates; đừng nhầm với 304 cho GET.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — HTTP Caching (Servlet MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-caching.html).
- [Spring Framework 6.2 — WebRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/WebRequest.html): overload `checkNotModified`.
- [Spring Framework 6.2 — ServletWebRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html): status, ETag và Last-Modified.
- [Spring Framework 6.2 — ResponseEntity.HeadersBuilder](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.HeadersBuilder.html): `eTag`, `lastModified`, `cacheControl`, `varyBy`.
- [Spring Framework 6.2 — CacheControl API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/CacheControl.html).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): conditional requests, 304/412, validators, If-Match và If-None-Match.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): Cache-Control directives, freshness, stored responses và shared caches.
- [MDN — HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): browser, proxy và revalidation.
