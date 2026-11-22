# Cache-Control, Expires và chính sách cho dữ liệu tĩnh hoặc dữ liệu riêng tư

> **Module:** Spring Boot - web-runtime · **Nhóm:** Cache và nén HTTP. Bài giải thích HTTP caching theo RFC 9111, so sánh cache của trình duyệt và cache dùng chung (proxy/CDN), xây chính sách cho tài nguyên tĩnh, HTML, API công khai và nội dung cá nhân. Ví dụ Java **17+**, Maven và **Spring Boot 4.1.2** sử dụng Spring MVC. Spring WebFlux áp dụng cùng giao thức HTTP nhưng có API cấu hình runtime riêng.

## Kết quả học tập

Sau bài này, bạn có thể:

1. Đọc và chọn chính xác `Cache-Control`, `Expires`, `Date`, `Age`, `ETag`, `Last-Modified` và `Vary`.
2. Phân biệt `no-cache`, `no-store`, `private`, `public`, `max-age`, `s-maxage`, `must-revalidate`, `immutable` và thời điểm cần dùng mỗi directive.
3. Thiết kế cache dài cho CSS/JS/image có version/hash **bất biến**, TTL ngắn hoặc revalidation cho file mutable/HTML và chính sách nghiêm ngặt cho dữ liệu cá nhân/nhạy cảm.
4. Hiểu thời điểm HTTP cache trả dữ liệu không hỏi server, lúc phải xác minh và cơ chế 200/304 với conditional requests.
5. Viết cấu hình Spring MVC `WebMvcConfigurer` cho hai nhóm static assets và dùng `ResponseEntity.cacheControl(...)` cho các API có mức nhạy cảm khác nhau.
6. Phân tích rủi ro lộ thông tin qua CDN, cache key/Vary, response `Authorization`, Spring Security, Service Worker và lỗi khi triển khai release.
7. Phân biệt HTTP caching với Spring `@Cacheable` và compression `gzip/br`.

## 1. HTTP cache lưu gì và ở tầng nào?

HTTP cache lưu **response representation** (headers, body và metadata liên quan) để tránh gửi lại bytes hoặc gọi origin khi bản lưu vẫn được phép sử dụng. Không phải mọi response đều được cache; chính sách phụ thuộc phương thức HTTP, status, các headers, authorization và quy định riêng của cache.

~~~text
Browser / mobile HTTP client
   |
   +-- Private HTTP cache (chỉ dành cho client/browser đó)
   |      fresh hit -> có thể không gửi request ra mạng
   |
   v
Proxy / CDN / reverse proxy: shared cache
   |      một bản response có thể phục vụ nhiều client
   |
   v
Gateway / Load Balancer
   |
   v
Spring Boot application
   |
   +-- static resource handler: CSS / JS / font / image
   +-- @Controller / @RestController: HTML / JSON
   |
   v
Service -> database
~~~

- **Private HTTP cache**: cache trình duyệt, HTTP client. Header `private` cho phép loại cache này lưu khi các điều kiện khác được đáp ứng.
- **Shared HTTP cache**: proxy/CDN có thể dùng cùng một bản response cho nhiều người. Đây là lý do phải đặc biệt cẩn thận với dữ liệu tài khoản.
- **Spring method/data cache**: `@Cacheable`, Caffeine, Redis, ORM cache nằm trong server; chúng **không** tự tuân theo `Cache-Control` của HTTP response.
- **Service Worker Cache Storage**: do code phía trình duyệt quản lý riêng, có thể tồn tại ngoài HTTP cache thông thường; `no-store` không xóa mọi dữ liệu ở các storage khác.

**Caching khác compression:** Cache-Control xác định một response có thể được lưu/tái sử dụng; `Content-Encoding: gzip`/`br` chỉ nói body đã được nén khi truyền. Hai kỹ thuật có thể dùng cùng lúc và cần `Vary: Accept-Encoding` nếu có nhiều biến thể theo encoding.

## 2. Freshness: response còn mới hay đã stale?

Một cache có thể tái sử dụng response **fresh** mà không cần hỏi server nếu chính sách cho phép. Khi vượt thời hạn freshness, response trở thành **stale**, khi đó có thể cần revalidation hoặc tải lại hoàn toàn.

Ví dụ origin trả:

~~~http
HTTP/1.1 200 OK
Date: Sun, 08 Nov 2026 01:00:00 GMT
Cache-Control: public, max-age=300
Content-Type: text/css

body { color: navy; }
~~~

`max-age=300` chỉ ra thời gian freshness tối đa 300 giây tính theo tuổi response. Nó **không** phải cam kết browser giữ file đúng 300 giây: cache có thể evict sớm, request force validation hoặc có những điều kiện khác.

Nếu CDN lưu response và trả lại sau một khoảng thời gian, nó có thể gửi:

~~~http
Age: 120
Cache-Control: public, max-age=300
~~~

`Age` là ước tính tuổi response theo quy tắc HTTP, thường thể hiện một bản được phục vụ từ cache upstream. Client không được hiểu response còn 300 giây nguyên vẹn: tuổi đã tăng.

### Thứ tự nguồn xác định freshness lifetime

Theo RFC 9111, với một response có thể lưu:

1. **Shared cache** ưu tiên `s-maxage` nếu response có directive đó.
2. Nếu không, cache dùng `max-age`.
3. Nếu không có các directive trên, `Expires` cung cấp thời điểm tuyệt đối, so với `Date`/thời điểm nhận.
4. Nếu thiếu explicit freshness, một số response có thể dùng **heuristic freshness** tùy status và quy tắc cache; thiếu header **không có nghĩa** chắc chắn không cache.

Ví dụ:

~~~http
Date: Sun, 08 Nov 2026 01:00:00 GMT
Expires: Sun, 08 Nov 2026 01:10:00 GMT
Cache-Control: public, max-age=60, s-maxage=120
~~~

Browser/private cache áp dụng `max-age=60`; shared cache ưu tiên `s-maxage=120`. Mốc Expires 10 phút **không thắng** hai directive hiện đại.

## 3. Bảng ý nghĩa các Cache-Control directive

| Directive trên response | Ý nghĩa chuẩn | Dùng khi |
| --- | --- | --- |
| `public` | Shared cache có thể lưu response nếu thỏa điều kiện khác | Static asset công khai, public API đã kiểm tra cache key |
| `private` | Shared cache **không được lưu**, private cache có thể lưu | Dữ liệu riêng nhưng ít nhạy cảm và cho phép browser cache |
| `no-store` | Cache tuân chuẩn không được lưu request/response theo phạm vi directive | Hồ sơ nhạy cảm, token, đơn hàng, thông tin thanh toán |
| `no-cache` | Có thể lưu nhưng **phải revalidate thành công** trước khi tái sử dụng | HTML entry page, resource cần xác minh phiên bản |
| `max-age=300` | Response có thể fresh đến 300 giây (nếu policy khác cho phép) | TTL browser/API rõ ràng |
| `s-maxage=60` | Shared cache dùng TTL 60 giây thay cho max-age/Expires | CDN cache public content |
| `must-revalidate` | Khi stale phải xác minh thành công, không tự dùng stale | Dữ liệu không được phục vụ phiên bản quá hạn |
| `proxy-revalidate` | Ý nghĩa revalidation tương tự nhưng áp dụng shared cache | Quy tắc cho proxy |
| `immutable` | Representation không đổi trong thời gian fresh | URL có hash/version **bất biến thật** |
| `no-transform` | Trung gian không được tự chuyển đổi nội dung theo directive | Khi cần giữ nguyên representation truyền |
| `stale-while-revalidate=30` | Một số cache có thể phục vụ stale thêm 30 giây khi revalidate | Public content chấp nhận độ trễ cập nhật |
| `stale-if-error=300` | Một số cache có thể phục vụ stale khi upstream lỗi | Nội dung công khai chịu lỗi/stale |

### 3.1. `no-cache` KHÔNG cấm lưu

~~~http
Cache-Control: no-cache
ETag: "home-v5"
~~~

Browser được phép giữ bản response. Nhưng mỗi lần muốn dùng lại, nó phải xác minh với origin. Khi có ETag, request có thể kèm:

~~~http
GET / HTTP/1.1
If-None-Match: "home-v5"
~~~

Nếu nội dung không đổi, server có thể trả **304 Not Modified** và không gửi lại body. Đây là lợi ích: **không tiết kiệm lượt round-trip**, nhưng tiết kiệm bytes của response.

### 3.2. `no-store` mới là chỉ thị không lưu

~~~http
Cache-Control: no-store
~~~

Theo tiêu chuẩn, cache không được lưu request/response để tái sử dụng. Đây là lựa chọn thận trọng cho dữ liệu chứa thông tin cá nhân nhạy cảm. Tuy nhiên, header không mã hóa đường truyền, không bảo vệ khỏi client độc hại và không xóa mọi file hoặc dữ liệu đã nằm trong localStorage, Service Worker, DOM, browser history hay ảnh chụp màn hình. HTTPS, auth và chính sách xóa dữ liệu riêng vẫn bắt buộc.

### 3.3. `max-age=0` không tương đương `no-store`

`max-age=0` khiến response stale ngay theo freshness, nhưng cache vẫn có thể **lưu** rồi dùng conditional request để revalidate. `no-cache` cũng cho phép lưu nhưng bắt revalidation. Đừng dùng `max-age=0` hoặc `no-cache` thay cho `no-store` trên token, dữ liệu tài khoản hoặc tài liệu riêng tư cần hạn chế lưu.

### 3.4. `private` không tương đương `no-store`

~~~http
Cache-Control: private, max-age=60
~~~

Shared cache không được lưu, nhưng browser của người dùng có thể giữ bản này 60 giây. Nếu một người khác sử dụng cùng thiết bị/browser profile sau khi chủ tài khoản đăng xuất, response đã lưu vẫn có thể là rủi ro. Chỉ dùng khi **business thực sự chấp nhận** lưu ở trình duyệt.

### 3.5. `public` và Authorization cần đánh giá đặc biệt

Theo RFC 9111, shared cache thông thường bị giới hạn khi request có `Authorization`, **nhưng** một số directive response explicit như `public` hoặc `s-maxage` có thể cho phép shared caching theo các điều kiện của chuẩn. Không kết luận “có Authorization thì CDN chắc chắn không lưu”. Với response chứa PII hoặc kết quả tùy theo danh tính, **không** thêm `public`/`s-maxage` tùy tiện.

Một response có `Set-Cookie` cũng không tự được bảo vệ khỏi mọi shared-cache tình huống chỉ nhờ header đó. Luôn đặt explicit cache policy và cấu hình CDN phù hợp.

## 4. Expires: thời hạn tuyệt đối theo HTTP-date

`Expires` ghi **ngày giờ** sau đó response được xem là stale:

~~~http
Date: Sun, 08 Nov 2026 01:00:00 GMT
Expires: Sun, 08 Nov 2026 01:05:00 GMT
~~~

Ở đây, response có thời điểm hết hạn 01:05 UTC; không có nghĩa resource bị xóa khỏi server vào giờ đó. Giá trị là HTTP-date (thường dạng IMF-fixdate với GMT), không phải số giây tương đối.

### Khi cả Expires và max-age xuất hiện

~~~http
Date: Sun, 08 Nov 2026 01:00:00 GMT
Expires: Sun, 08 Nov 2026 02:00:00 GMT
Cache-Control: max-age=60
~~~

Cache tuân chuẩn ưu tiên `max-age=60`, **bỏ qua Expires** khi tính freshness. Nếu có `s-maxage`, shared cache ưu tiên `s-maxage`. Do đó không thể đặt Expires một giờ rồi kỳ vọng ghi đè TTL một phút.

Với `Expires: 0` hoặc định dạng ngày không hợp lệ, cache phải hiểu như thời điểm đã qua. Đây là kỹ thuật tương thích lịch sử, **không có sức mạnh chống lưu** của `Cache-Control: no-store`.

### Expires nên dùng vào lúc nào?

- Có hệ thống cũ thực sự dựa vào Expires và cần giữ tương thích.
- Muốn minh họa hoặc vận hành cơ chế deadline tuyệt đối cho một representation, với clock được quản lý đúng.
- Cần nhớ tương quan với `Date`, `Age` và sự lệch đồng hồ giữa các hệ thống.

Trong Spring Boot hiện đại, thông thường **ưu tiên Cache-Control**. Không tạo HTTP-date bằng giờ địa phương không có GMT hoặc dựa trên đồng hồ không đáng tin.

## 5. ETag, Last-Modified, conditional requests và 304

**Freshness** trả lời “có thể dùng bản đã lưu không cần hỏi server?”. **Validation** trả lời “sau khi hỏi server, bản lưu có còn phù hợp không?”.

### 5.1. ETag

Origin trả:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=300
ETag: "catalog-v2"
Content-Type: application/json

{"version":2,"name":"Catalog"}
~~~

Sau khi hết TTL, client có thể gửi:

~~~http
GET /api/catalog HTTP/1.1
If-None-Match: "catalog-v2"
~~~

Nếu representation hiện tại vẫn là bản đó, server trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "catalog-v2"
Cache-Control: public, max-age=300
~~~

304 không chứa representation body mới; HTTP client dùng cached body phù hợp theo quy tắc. Nếu nội dung đổi, origin cần trả 200 và ETag khác.

**ETag phải đổi khi representation đổi.** Gắn hằng ETag cho nội dung database biến đổi sẽ làm cache sử dụng nội dung cũ sai. Với ETag mạnh `"..."` và yếu `W/"..."` có các semantics so sánh khác nhau; không dùng ETag làm bằng chứng xác thực người dùng hoặc làm nơi chứa token/số định danh nhạy cảm.

### 5.2. Last-Modified

Response static có thể gửi:

~~~http
Last-Modified: Sun, 08 Nov 2026 00:00:00 GMT
~~~

Client revalidate qua `If-Modified-Since`. Đây là metadata về thời gian chỉnh sửa, có thể không đủ phân biệt hai thay đổi trong cùng một giây hoặc khi hệ thống lưu trữ làm mất timestamp. ETag có thể cung cấp validator phù hợp hơn cho nhiều trường hợp.

Nếu client gửi cả `If-None-Match` và `If-Modified-Since`, điều kiện HTTP có quy tắc ưu tiên; không tùy ý trả 304 chỉ vì một trong hai trông “cũ”.

### 5.3. 304 vẫn phải tuân quyền

Với tài nguyên theo người dùng, server **vẫn phải kiểm authentication và authorization hiện tại** trước khi cân nhắc trả 304. Một ETag trùng không cho phép user B nhận quyền sử dụng cached representation của user A. HTTP cache key và phân vùng dữ liệu cần được thiết kế trước khi bật caching.

Spring MVC hỗ trợ `ResponseEntity.eTag(...)`/`lastModified(...)` và `WebRequest.checkNotModified(...)`. `ShallowEtagHeaderFilter` có thể tính hash từ body sau khi render, thường tiết kiệm băng thông nhưng không nhất thiết tránh CPU dựng response; với representation đắt tiền, tính validator từ version/metadata sớm sẽ hiệu quả hơn.

## 6. Vary và cache key: vì sao cùng URL chưa chắc cùng dữ liệu?

Cache key cơ bản có thể dựa vào method và target URI, nhưng response còn có thể thay đổi theo request headers. `Vary` chỉ ra headers phải được so khớp khi reuse bản lưu.

Ví dụ API trả lời theo ngôn ngữ:

~~~http
Cache-Control: public, max-age=60
Vary: Accept-Language
~~~

Nếu không có Vary (hoặc cache key ở CDN tương đương), CDN có thể trả response tiếng Việt cho người muốn tiếng Anh vì cùng URL.

Các tình huống khác:

- `Vary: Accept-Encoding` cho các biến thể `gzip`/`br`/không nén. Khi nén, nhớ rằng caching và compression là hai cơ chế riêng.
- `Vary: Origin` có thể cần khi CORS response thay đổi theo Origin.
- `Vary: Cookie` hoặc `Vary: Authorization` có thể làm key khó quản lý và tăng số biến thể; **không thay thế private/no-store hoặc authorization**.
- Cache rule tùy chỉnh tại CDN có thể bỏ query params, cookie hoặc headers khỏi key; đó là rủi ro lớn với response tùy người dùng.

Nếu cùng URL `/api/me` trả profile theo session/cookie, **đừng** dùng `public` chỉ vì một CDN được quảng cáo có “cache key theo cookie”. Ưu tiên no-store cho profile/PII, trừ khi hệ thống được thiết kế và đánh giá rất kỹ.

## 7. Ma trận chính sách thực tế

| Đối tượng | Cache-Control khởi điểm | Giải thích |
| --- | --- | --- |
| CSS/JS/font/image công khai có **content hash trong URL** | `public, max-age=31536000, immutable` | Có thể lưu dài, nhưng URL phải đổi khi bytes đổi |
| Static asset với path release bất biến như `/v7/site.css` | `public, max-age=31536000, immutable` | Chỉ đúng nếu v7 không bao giờ được sửa tại cùng URL |
| File tĩnh cùng URL có thể thay đổi | `no-cache` hoặc `public, max-age=60` + validator | Cần cập nhật sớm, không giữ mã cũ hàng năm |
| HTML entry page không cá nhân | `no-cache` + ETag/Last-Modified khi hữu ích | Revalidate trước reuse để nhận links tới assets mới |
| HTML theo người đăng nhập | `no-store` nếu nhạy cảm; đôi khi `private, no-cache` nếu chấp nhận | Không vào shared cache; cân nhắc logout/switch account |
| Public catalog/news API thay đổi chậm | `public, max-age=300` + ETag; có thể CDN policy riêng | Đổi hiệu năng lấy thời gian stale tối đa chấp nhận |
| User preference **không nhạy cảm** | `private, max-age=60` nếu phù hợp | Cho browser lưu; không cho CDN lưu |
| Profile, token, số dư, sức khỏe, đơn hàng | `no-store` | Tránh lưu HTTP response nhạy cảm theo chuẩn |
| Login/logout/reset password/session | `no-store` | Tránh lưu response phụ thuộc session/auth |
| File tải xuống chứa tài liệu riêng | `no-store`; kiểm auth; download headers phù hợp | Tránh public cache và hạn chế browser cache |
| Error 404/301 có thể thay đổi theo thời gian | Policy explicit, không cache dài nếu có thể đổi | Một số status được cache heuristic |
| Nội dung public chấp nhận phục vụ stale trong sự cố | TTL + stale extension có kiểm soát | Chỉ dùng khi business chấp nhận thông tin cũ |

Không có một policy duy nhất đúng cho cả site. Phân loại dựa vào **độ nhạy cảm, tính bất biến của URL, tần suất cập nhật, SLA, khả năng bị stale và cache key**.

### 7.1. Assets version/hash: tại sao phải thay URL?

Ví dụ:

~~~text
Release 1: /assets/app.83caef2.css
Release 2: /assets/app.26b197a.css
~~~

Nếu sửa CSS nhưng giữ URL `/assets/app.css` với TTL một năm, browser có thể tiếp tục dùng bản cũ. `immutable` chỉ là directive; nó **không tự đổi URL** khi file đổi. Dùng version theo nội dung hoặc release, cập nhật HTML và giữ asset cũ đến khi các HTML/browser tabs còn dùng bản cũ không bị lỗi.

HTML nên có TTL ngắn hoặc `no-cache`, để browser sớm nhận asset URL mới. Service worker, CDN, cache của SPA shell còn có quy tắc riêng cần kiểm tra.

### 7.2. Dữ liệu cá nhân: private khi nào, no-store khi nào?

`private, max-age=60` dành cho nội dung **ít nhạy cảm** mà bạn chấp nhận lưu trong browser. `no-store` phù hợp hơn với dữ liệu tài khoản/khả năng lộ thông tin cao, hoặc khi logout cần tránh dùng lại cached body.

Đừng hiểu `private` là chế độ mã hóa hay access control. User khác dùng cùng browser profile có thể gặp dữ liệu cũ; cache policy không thay thế HTTPS, session invalidation, Secure/HttpOnly/SameSite cookies và phân quyền endpoint.

## 8. Cấu hình Spring Boot: static resources và HTTP response

Spring Boot MVC thường có static locations:

~~~text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
~~~

Ví dụ file `src/main/resources/static/assets/site.css` có thể được phục vụ tại `/assets/site.css` theo mặc định, tùy `spring.mvc.static-path-pattern` và cấu hình resource handlers.

### 8.1. Dùng properties để đặt policy chung cho static resource handler

~~~properties
# Chỉ áp dụng cho default static resource handling của Boot.
spring.web.resources.cache.cachecontrol.cache-public=true
spring.web.resources.cache.cachecontrol.max-age=10m

# Ví dụ policy đơn giản theo duration:
# spring.web.resources.cache.period=600

# Cho phép dùng Last-Modified nếu resource hỗ trợ.
spring.web.resources.cache.use-last-modified=true

# Cấu hình version strategy dựa trên nội dung khi cần:
# spring.web.resources.chain.strategy.content.enabled=true
# spring.web.resources.chain.strategy.content.paths=/**
~~~

Các property `spring.web.resources.cache.*` **không tự áp TTL** cho mọi JSON response do `@RestController` tạo. Đừng đặt global cache dài cho các static resources có cả file mutable và versioned. Muốn tách policy theo URL, dùng `WebMvcConfigurer` hoặc quy tắc CDN được kiểm chứng.

Spring có `VersionResourceResolver` và `ResourceUrlProvider` để hỗ trợ URL version dựa trên content hash. Bật resolver mà vẫn hardcode URL chưa version trong HTML **không tự bảo đảm cache busting**; cần tạo/rewritten URL phù hợp hoặc build pipeline emit hashed filenames.

### 8.2. Dùng CacheControl trong controller

Đối với response động, Spring MVC có thể đặt policy ở mỗi method:

~~~java
// Minh họa trong controller có ResponseEntity và CacheControl đã import:
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(privateResult);
~~~

Với tài nguyên công khai:

~~~java
// Minh họa, representation public và TTL 5 phút:
return ResponseEntity.ok()
        .cacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5)).cachePublic())
        .eTag("\"version-123\"")
        .body(publicResult);
~~~

ETag phải lấy từ version/representation thật, không hardcode khi dữ liệu có thể đổi.

## 9. Ví dụ Java 17 chạy được: static versioned, mutable và private API

Project Spring Boot dưới đây có các endpoint:

- `GET /assets/versioned/v1/site.css`: CSS versioned, public, TTL 365 ngày, immutable.
- `GET /assets/live/site.css`: CSS cùng URL có thể đổi, no-cache.
- `GET /page`: HTML entry page, no-cache.
- `GET /api/catalog`: public JSON, max-age=300 và ETag cố định do nội dung demo cố định.
- `GET /api/demo/preference?theme=blue`: minh họa dữ liệu riêng ít nhạy cảm, private/max-age=60. **Không có auth**, chỉ là ví dụ header.
- `GET /api/demo/account`: response giả lập nhạy cảm, no-store. **Không trả dữ liệu tài khoản thực**.
- `GET /api/legacy/notice`: Expires tương đối với giờ UTC do server tạo (không đặt max-age).

### 9.1. Cấu trúc dự án

~~~text
http-cache-demo/
  pom.xml
  src/main/java/com/example/cachepolicy/
    CachePolicyApplication.java
    StaticCacheConfig.java
    CachePolicyController.java
  src/main/resources/
    application.properties
    static/assets/versioned/v1/site.css
    static/assets/live/site.css
~~~

### 9.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http-cache-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

`spring-boot-starter-webmvc` là starter MVC của Spring Boot 4.x; ứng dụng Spring Boot 3.x thường dùng `spring-boot-starter-web`. Demo không thêm Spring Security để dễ nhìn riêng header từ code, nhưng điều đó **không có nghĩa** những endpoint minh họa là an toàn để chứa dữ liệu thật.

### 9.3. CachePolicyApplication.java

~~~java
package com.example.cachepolicy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CachePolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(CachePolicyApplication.class, args);
    }
}
~~~

### 9.4. StaticCacheConfig.java

~~~java
package com.example.cachepolicy;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class StaticCacheConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/versioned/**")
                .addResourceLocations("classpath:/static/assets/versioned/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(365))
                                .cachePublic()
                                .immutable());

        registry.addResourceHandler("/assets/live/**")
                .addResourceLocations("classpath:/static/assets/live/")
                .setCacheControl(CacheControl.noCache());
    }
}
~~~

- URL `/assets/versioned/v1/site.css` trỏ tới classpath `/static/assets/versioned/v1/site.css`.
- `CacheControl.maxAge(Duration.ofDays(365))` tương đương 31.536.000 giây; `cachePublic()` cho phép shared cache; `immutable()` chỉ hợp lý nếu bytes dưới `/v1` không đổi.
- `CacheControl.noCache()` cho `live` yêu cầu cache revalidate trước reuse. Việc revalidation có thể dùng `Last-Modified` của file resource.
- Hai URL patterns không chồng nhau nên không gây tranh chấp policy.
- Đừng lưu file cá nhân ở `static/`: static resource handlers không phải nơi bảo đảm auth cho mỗi file.

### 9.5. CachePolicyController.java

~~~java
package com.example.cachepolicy;

import java.time.Duration;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CachePolicyController {

    @GetMapping("/api/catalog")
    public ResponseEntity<Map<String, String>> catalog() {
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic())
                .eTag("\"catalog-v1\"")
                .body(Map.of(
                        "version", "1",
                        "name", "HTTP cache demo"));
    }

    @GetMapping("/api/demo/preference")
    public ResponseEntity<Map<String, String>> preference(
            @RequestParam(defaultValue = "dark") String theme) {
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(60))
                                .cachePrivate())
                .body(Map.of("theme", theme));
    }

    @GetMapping("/api/demo/account")
    public ResponseEntity<Map<String, String>> account() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "notice", "No real account data is exposed"));
    }

    @GetMapping("/page")
    public ResponseEntity<String> page() {
        String html = """
                <!doctype html>
                <html lang="vi">
                <head>
                  <meta charset="utf-8">
                  <title>HTTP Cache</title>
                  <link rel="stylesheet" href="/assets/versioned/v1/site.css">
                </head>
                <body>
                  <h1>Cache policy demo</h1>
                  <p>HTML revalidate; CSS versioned được cache lâu.</p>
                </body>
                </html>
                """;

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_HTML)
                .cacheControl(CacheControl.noCache())
                .body(html);
    }

    @GetMapping("/api/legacy/notice")
    public ResponseEntity<Map<String, String>> legacyNotice() {
        String expires = DateTimeFormatter.RFC_1123_DATE_TIME.format(
                ZonedDateTime.now(ZoneOffset.UTC).plusMinutes(2));

        return ResponseEntity.ok()
                .header(HttpHeaders.EXPIRES, expires)
                .body(Map.of("notice", "Expires-only example"));
    }
}
~~~

**Các điểm quan trọng:**

- Dữ liệu catalog là hằng số nên ETag `"catalog-v1"` minh họa được validator; nếu nội dung đổi thì phải cập nhật ETag. Spring MVC có xử lý conditional request phù hợp với ETag trong `ResponseEntity`, có thể trả 304 khi client gửi `If-None-Match` đúng.
- `preference()` và `account()` không có authentication **chỉ để mô phỏng hai cache policy**. Đừng sao chép demo làm endpoint cho dữ liệu nhạy cảm thật mà bỏ kiểm tra đăng nhập và quyền.
- `page()` trả HTML body trực tiếp vì không cần template engine để minh họa header. Trong ứng dụng render Thymeleaf, cũng cần đặt policy trên response của controller/handler.
- `legacyNotice()` tạo HTTP-date GMT/UTC bằng chuẩn Java, thêm Expires mà không tự thêm Cache-Control. Header thực tế còn phụ thuộc proxy/filter/cấu hình chạy.

### 9.6. Tệp resources

**src/main/resources/application.properties**

~~~properties
server.port=8080

# Chính sách static theo URL được cấu hình trong StaticCacheConfig.
# Tránh đặt TTL public dài đồng loạt cho tất cả tài nguyên.
~~~

**src/main/resources/static/assets/versioned/v1/site.css**

~~~css
body {
    font-family: system-ui, sans-serif;
    margin: 2rem;
}
h1 {
    color: #1769aa;
}
~~~

**src/main/resources/static/assets/live/site.css**

~~~css
body {
    background-color: #f3f5f7;
}
~~~

Khi sửa nội dung versioned CSS trong production, phải thêm URL mới như `/assets/versioned/v2/site.css`; không ghi đè version 1. Trong thực tế, dùng content hash trong build pipeline giúp loại sai sót quản lý version bằng tay.

### 9.7. Chạy và kiểm tra

Trong thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác (cURL để hiển thị status và headers):

~~~bash
curl -i http://localhost:8080/assets/versioned/v1/site.css
~~~

Kỳ vọng 200, Content-Type CSS và Cache-Control có các directive:

~~~http
Cache-Control: max-age=31536000, public, immutable
~~~

Thứ tự in của các headers khác không được cố định trong bài.

~~~bash
curl -i http://localhost:8080/assets/live/site.css
~~~

Kỳ vọng 200, response chứa:

~~~http
Cache-Control: no-cache
~~~

~~~bash
curl -i http://localhost:8080/page
~~~

Kỳ vọng 200 với `Content-Type` HTML và `Cache-Control: no-cache`; HTML tham chiếu `/assets/versioned/v1/site.css`.

~~~bash
curl -i http://localhost:8080/api/catalog
~~~

Kỳ vọng 200 cùng các headers:

~~~http
Cache-Control: max-age=300, public
ETag: "catalog-v1"
Content-Type: application/json
~~~

Body JSON có hai field `version` và `name`; thứ tự key có thể thay đổi. Để thử revalidation:

~~~bash
curl -i -H 'If-None-Match: "catalog-v1"' \
  http://localhost:8080/api/catalog
~~~

Kỳ vọng **304 Not Modified** và không có representation body khi Spring MVC nhận ETag phù hợp và nội dung không đổi. Nếu có proxy/filter bổ sung, test trực tiếp với origin trước.

~~~bash
curl -i "http://localhost:8080/api/demo/preference?theme=blue"
curl -i http://localhost:8080/api/demo/account
~~~

Response của preference có directive `private, max-age=60`; account có `no-store`. Đây là minh họa cache header, **không phải** mô hình bảo vệ tài khoản hoàn chỉnh.

~~~bash
curl -i http://localhost:8080/api/legacy/notice
~~~

Kỳ vọng có `Expires` dạng HTTP-date ở khoảng **hai phút sau thời điểm xử lý request**. Ví dụ format:

~~~http
Expires: Sun, 08 Nov 2026 01:02:00 GMT
~~~

Timestamp là minh họa cú pháp, **không** cố định; chương trình tạo giá trị động theo clock của server.

Trên Windows PowerShell, dùng `curl.exe` để gọi cURL trực tiếp, ví dụ:

~~~powershell
curl.exe -i http://localhost:8080/api/catalog
curl.exe -i -H 'If-None-Match: "catalog-v1"' http://localhost:8080/api/catalog
~~~

Đóng gói ứng dụng:

~~~bash
mvn package
java -jar target/http-cache-demo-0.0.1-SNAPSHOT.jar
~~~

Vì có dependency Spring Boot, nên `javac` trần không đủ classpath; dùng Maven build.

## 10. Những trường hợp dễ nhầm ở môi trường thực tế

### 10.1. Request directive và response directive khác nhau

Client có thể gửi:

~~~http
GET /api/catalog HTTP/1.1
Cache-Control: no-cache
~~~

Nó yêu cầu cache không tái sử dụng phản hồi đã lưu khi chưa revalidate. Nó **không ra lệnh** server xóa nội dung khỏi mọi cache. Ngược lại, response `Cache-Control: no-cache` là chỉ dẫn của origin về các lần reuse tương lai.

Nút reload/hard reload hay “Disable cache” trong DevTools có thể làm browser gửi headers đặc thù hoặc bypass cache; đừng coi hành vi đó là bằng chứng duy nhất về cấu hình production.

### 10.2. 304 là tối ưu băng thông, không có body mới

304 có thể mang metadata như ETag, Cache-Control và không mang body representation mới. Browser giữ body cũ nếu cache validation thành công. Nếu endpoint có dữ liệu cá nhân, server vẫn phải kiểm user hiện tại trước khi quyết định 304. Không dùng ETag version chung để bỏ qua kiểm quyền.

### 10.3. no-cache + must-revalidate không thành no-store

`must-revalidate` có nghĩa **khi stale**, cache không được phục vụ stale mà chưa xác minh. `no-cache` yêu cầu revalidate trước reuse ngay từ đầu. Cả hai đều không tương đương `no-store`, nên không phù hợp nếu mục tiêu là “không được lưu nội dung nhạy cảm”.

### 10.4. Dùng stale extension cho public content, không cho số dư

`stale-while-revalidate` và `stale-if-error` có thể giúp CDN cung cấp response công khai trong lúc nguồn chậm hoặc lỗi. Chúng không phù hợp cho mọi dữ liệu: nếu dữ liệu tài chính, permission hoặc thông báo trạng thái đơn hàng phải mới, phải cấm sử dụng stale không kiểm soát. Tránh kết hợp directive có semantics xung đột mà không hiểu cách cache cụ thể triển khai.

### 10.5. 404/redirect cũng có thể bị cache

Một số status code được chuẩn HTTP cho phép heuristic caching. Nếu `/product/123` hôm nay chưa tồn tại và ngày mai tạo mới, CDN có thể tiếp tục trả 404 đã lưu nếu policy không rõ. Redirect permanent cũng có thể được cache; muốn đổi mapping cần tính cả cache và browser history. Đặt cache policy cho lỗi/redirect và purge khi cần.

### 10.6. HTML chứa link cũ làm hỏng cache busting

Đổi URL CSS theo hash nhưng cache HTML một năm có thể khiến browser tiếp tục tải CSS đời trước. Dùng cache dài cho asset bất biến **và cache ngắn/no-cache cho entry HTML**, đồng thời giữ lại version cũ trong một giai đoạn triển khai/rollback cần thiết.

## 11. Spring Security, CDN và Service Worker

### Spring Security có header mặc định chống cache

Khi tích hợp Spring Security, mặc định thường có:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Mục tiêu là tránh lưu nội dung người dùng trong HTTP cache theo mặc định. Spring Security có thể nhường policy cho ứng dụng nếu response đã gửi Cache-Control riêng. Đừng tắt các default security headers cho **toàn bộ site** chỉ vì muốn CSS/JS cache nhanh. Cấu hình riêng asset công khai và kiểm tra header sau toàn bộ filter chain.

### CDN/gateway có thể ghi đè TTL

Trong production:

~~~text
Spring Boot -> Nginx/Envoy/Gateway -> CDN -> Browser
~~~

CDN có thể có Edge TTL, cache key riêng, purge policy, rule bỏ query params, hoặc header khác như Surrogate-Control. Kiểm tra sự khác biệt giữa **origin response**, **gateway response**, **CDN response** và **browser network traces**; không giả định properties Spring Boot luôn là policy cuối cùng client nhận.

Đặc biệt không để CDN cache response có `Authorization`/cookie mà chưa phân loại đúng. Dữ liệu cá nhân phải được tách theo user/tenant và kiểm quyền; dùng no-store khi không chủ động thiết kế shared caching.

### Service Worker/Browser history

Service Worker do ứng dụng viết có thể lưu response trong Cache Storage, IndexedDB hoặc API lưu trữ khác. `no-store` chỉ là chính sách HTTP cache, không tự xóa các storage do ứng dụng quản lý. Khi logout hoặc đổi account, ứng dụng phải xóa state/cache nhạy cảm theo lifecycle riêng và kiểm session khi quay lại trang. Browser back-forward cache (bfcache) không đồng nghĩa HTTP cache và có hành vi phụ thuộc browser/version; không coi no-store là biện pháp xóa DOM tuyệt đối.

## 12. Quan hệ với nén HTTP

| Vấn đề | HTTP caching | HTTP compression |
| --- | --- | --- |
| Mục tiêu | Tránh phải gửi/tính lại representation | Giảm bytes truyền của một representation |
| Headers | Cache-Control, Expires, ETag, Last-Modified, Age, Vary | Accept-Encoding, Content-Encoding, Vary |
| Có thể hoạt động cùng nhau? | Có | Có |
| Sai lầm thường gặp | Shared cache lưu nhầm response riêng tư | Gửi gzip cho client không chấp nhận |
| Liên hệ | Cache key phải chọn đúng biến thể | Vary: Accept-Encoding giúp phân biệt variant |

Ví dụ:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=600
Content-Type: text/css
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Một response CSS có thể vừa gzip vừa cache. `Cache-Control: no-transform` không phải lệnh bật/tắt compression trong Spring Boot; nó hạn chế intermediary thay đổi nội dung theo định nghĩa của directive. Nếu dùng precompressed assets, phải phối hợp resource resolver và version strategy, không chỉ bật một property rồi mặc định cache đúng.

## 13. Cách kiểm thử và giám sát chính sách

Các bước kiểm tra khi triển khai:

1. Dùng `curl -i` hoặc Network panel để xem **response** Cache-Control/Expires/ETag/Vary.
2. Gọi lại endpoint với `If-None-Match` hợp lệ để kiểm 304; đổi nội dung thực và xác nhận ETag thay đổi.
3. Thử request public/anonymous, authenticated user A, authenticated user B cùng URL. Không để response riêng tư của A được CDN trả cho B.
4. Kiểm cache headers khi logout, login, session timeout, quyền thay đổi, 404, redirect, 500.
5. Kiểm giao tiếp qua proxy/CDN; so sánh cache HIT/MISS, Age, X-Cache (nếu có), cache key và edge TTL.
6. Với versioned assets, test release mới đổi URL và phiên bản cũ vẫn tải được khi còn người dùng/trình duyệt cần.
7. Khi bật compression, kiểm Vary và Content-Encoding theo Accept-Encoding; không để cache trả nhầm bytes.
8. Test browser bị giữ HTML cũ, service worker offline cache và khách hàng dùng nhiều tài khoản cùng một thiết bị.

Một số phép thử gợi ý:

~~~bash
curl -i http://localhost:8080/api/catalog
curl -i -H 'If-None-Match: "catalog-v1"' http://localhost:8080/api/catalog
curl -i http://localhost:8080/api/demo/account
curl -i http://localhost:8080/assets/versioned/v1/site.css
~~~

Trong integration test với MockMvc, có thể kiểm header `no-store`/`private` và status 304; code test sẽ cần dependency Spring MVC Test/JUnit tương thích phiên bản Boot, không thuộc ví dụ Maven tối giản ở trên. Khi response có middleware làm thay header, test ở môi trường đầy đủ, không chỉ unit test controller.

### Những metric hữu ích

- Cache HIT/MISS và tỷ lệ 304; tỷ lệ tiết kiệm băng thông.
- `Age`/TTL còn lại; số response stale được phục vụ theo chính sách.
- Latency p95/p99 ở origin và CDN; lượng requests từ CDN về origin.
- Tỷ lệ 4xx/5xx, 404 cache lặp, redirect cache sai.
- Tỷ lệ response bị gắn public/private/no-store không đúng classification.
- Số incident lộ dữ liệu giữa tenants/users hoặc stale sau logout (cần zero tolerance).

## 14. Các lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân hay gặp | Sửa |
| --- | --- | --- |
| Thay CSS nhưng người dùng vẫn thấy bản cũ | Cache dài ở URL không đổi, immutable sai | URL version/hash mới; HTML cập nhật |
| HTML mới không được nhận | Entry HTML cũng cache dài, service worker giữ cũ | no-cache/TTL nhỏ; rà soát SW/CDN |
| User B thấy dữ liệu user A | Shared cache key thiếu auth hoặc policy public sai | no-store/private đúng lớp, cấu hình CDN, test cross-user |
| no-cache mà browser vẫn có body | no-cache cho lưu và buộc revalidate | Nếu muốn không lưu, no-store |
| max-age=0 vẫn thấy request 304 | max-age=0 không cấm lưu | Đây là behavior hợp lệ; dùng no-store nếu cần |
| Expires 1 giờ nhưng TTL 60 giây | max-age ghi đè Expires | Định nghĩa policy rõ và kiểm headers |
| 304 dù dữ liệu mới đã đổi | ETag giữ nguyên hoặc validator tính sai | ETag gắn với representation/version thật |
| Có Spring Security nên file tĩnh không cache | Default response headers/filter chain can thiệp | Đặt cache policy riêng cho asset và kiểm response |
| Content language bị lẫn ở proxy | Vary/cache key thiếu Accept-Language | Vary đúng hoặc tách URL |
| CDN trả gzip sai biến thể | Key và Vary: Accept-Encoding không đúng | Cấu hình variants và test clients |
| 404 tiếp tục sau khi resource tồn tại | Negative caching/heuristic cache | TTL nhỏ/no-cache cho 404, purge đúng |
| Profile còn hiện sau logout | HTTP cache hoặc app storage/bfcache chưa xử lý | no-store, clear state, recheck session |
| Dùng private cho token nhạy cảm | Browser vẫn lưu body | Dùng no-store |
| Bật public cho auth response | Có thể mở shared-cache theo RFC | Không public cho private data, kiểm CDN key |
| Nhầm @Cacheable với HTTP caching | Server cache có hiệu lực nhưng client không thấy Cache-Control | Thiết kế hai cache độc lập |

## 15. Checklist thiết kế trước khi triển khai

- [ ] Tài nguyên thuộc loại nào: public immutable, public mutable, public API, personalized, sensitive, auth/session?
- [ ] Response có chứa token, PII, role/tenant-specific data hay chỉ là nội dung công khai?
- [ ] Với private content, có lý do business rõ ràng để browser cache thay vì no-store?
- [ ] Với static TTL dài, **URL có đổi khi bytes đổi** và không ghi đè phiên bản cũ?
- [ ] HTML entry page có thể revalidate để link đến assets mới?
- [ ] Từng response có một policy rõ, không bị security filter/proxy/CDN thay không chủ ý?
- [ ] ETag/Last-Modified phản ánh đúng representation và 304 chỉ trả sau khi kiểm quyền?
- [ ] Vary/cache key phân biệt ngôn ngữ, encoding và các điều kiện thay đổi body?
- [ ] Đã test cross-user, logout, role change, 404, redirect, CDN hit, static deploy?
- [ ] Đã phân biệt response cache với @Cacheable, server-side data cache, Service Worker và gzip?
- [ ] Có kế hoạch purge CDN, rollback asset version, observability và response header contract?

### Quy trình quyết định nhanh

~~~text
Có dữ liệu nhạy cảm, session/token/PII?
   -> no-store + HTTPS + authorization.

Không nhạy cảm nhưng response theo người?
   -> private + TTL nhỏ chỉ khi chấp nhận browser lưu;
      nếu không chắc, no-store.

Tài nguyên công khai có URL hash/version bất biến?
   -> public, max-age=31536000, immutable.

Tài nguyên công khai nhưng cùng URL có thể đổi?
   -> no-cache + validator hoặc max-age ngắn.

Public API chấp nhận stale tối đa X giây?
   -> public, max-age=X + ETag; thiết kế s-maxage nếu CDN được phép.

Chưa biết cache key hoặc độ nhạy cảm?
   -> Không bật public/long TTL trước khi xác minh.
~~~

## 16. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `no-cache` có ngăn browser lưu HTML không?

**Đáp án:** Không; cache có thể lưu nhưng phải revalidate trước khi tái sử dụng. ETag có thể làm server trả 304 không cần body.

**Câu 2.** `private, max-age=300` có phù hợp cho trang chứa token hoặc số dư không?

**Đáp án:** Không nên. Private browser cache vẫn lưu được; với nội dung nhạy cảm ưu tiên no-store và thiết kế auth/session an toàn.

**Câu 3.** Response có `Expires` 30 phút trong tương lai, `max-age=60`. TTL nào thắng?

**Đáp án:** max-age 60 giây thắng; shared cache sẽ dùng s-maxage nếu được gửi.

**Câu 4.** Vì sao chỉ bật immutable cho /app.js chưa đủ?

**Đáp án:** URL không đổi khi bytes đổi thì browser có thể giữ JS cũ. Cần hashed/versioned URL và cập nhật HTML.

**Câu 5.** Có Authorization header trong request, CDN chắc chắn không cache?

**Đáp án:** Không tuyệt đối: RFC có các trường hợp response directive cho phép shared cache, và CDN có cấu hình riêng. Không dùng public/s-maxage cho dữ liệu theo tài khoản.

**Câu 6.** max-age=0 có giống no-store không?

**Đáp án:** Không; response vẫn có thể được lưu, chỉ stale ngay. Revalidation bằng ETag/304 vẫn có ý nghĩa.

**Câu 7.** Khi JSON đổi mà ETag giữ nguyên, hậu quả gì?

**Đáp án:** Client có thể nhận 304 và sử dụng body cũ; ETag phải đổi theo version/representation thật.

**Câu 8.** Vì sao API có nhiều ngôn ngữ cần Vary?

**Đáp án:** Để cache không gửi nhầm body được tạo cho Accept-Language khác khi cùng URL.

**Câu 9.** Gzip và cache có phải cùng một cơ chế?

**Đáp án:** Không; gzip giảm bytes truyền, cache tái sử dụng response; Vary: Accept-Encoding có thể cần cho variants.

**Câu 10.** Dùng no-store đã đảm bảo dữ liệu bị xóa khỏi mọi nơi sau logout?

**Đáp án:** Không. Nó điều khiển HTTP cache tuân chuẩn, không xóa browser storage/app state hoặc thay thế authentication/HTTPS.

## 17. Tài liệu tham khảo

- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html) — Cache-Control, Expires, freshness, shared cache, conditional response.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) — HTTP-date, validators, conditional requests, status codes.
- [Spring Framework — HTTP Caching trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html) — CacheControl, ETag, Last-Modified.
- [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html) — ResourceHandlerRegistry, VersionResourceResolver, CacheControl.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — spring.web.resources.cache.*.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html) — static resources và MVC.
- [Spring Framework — CacheControl Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html) — noCache, noStore, cachePrivate, immutable.
- [Spring Security — HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) — default cache headers và tùy chỉnh.
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/) — phiên bản Spring Boot của ví dụ.

**Ghi nhớ:** Hãy phân loại dữ liệu **trước** khi chọn TTL. Với static version/hash bất biến, có thể cache rất lâu; với HTML và tài nguyên mutable, dùng TTL ngắn hoặc revalidation; với dữ liệu cá nhân ít nhạy cảm, `private` chỉ khi chấp nhận browser lưu; với dữ liệu nhạy cảm, ưu tiên `no-store`. `max-age`/`s-maxage` được ưu tiên so với `Expires`; validator giúp 304; mọi cấu hình phải được kiểm tra ở origin, proxy/CDN và trình duyệt.