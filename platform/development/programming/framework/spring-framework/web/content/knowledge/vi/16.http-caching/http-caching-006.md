# Vary, nội dung cá nhân hóa và tránh lưu nhầm dữ liệu riêng tư trong HTTP Cache

## 1. Bài toán: cùng URL, hai người dùng, hai kết quả

Một API Spring MVC có endpoint `GET /api/me`. Khi Alice đăng nhập, server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"user":"alice","displayName":"Alice"}
~~~

Bob gọi **cùng URL** nhưng kết quả phải là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"user":"bob","displayName":"Bob"}
~~~

Nếu cache chia sẻ ở CDN, reverse proxy hoặc HTTP intermediary chỉ lưu theo URL rồi vô tình dùng lại response của Alice cho Bob, đó là **rò rỉ dữ liệu xuyên người dùng**. Lỗi này không nhất thiết nằm trong controller, vì controller có thể chưa hề nhận request của Bob: cache ở phía trước đã tự trả kết quả.

Trong HTTP, `Vary` và `Cache-Control` có trách nhiệm khác nhau:

- **`Vary`** nói representation thay đổi theo những **request header** nào; cache phải xét chúng khi quyết định một response đã lưu có dùng lại được không.
- **`Cache-Control: private`** nói response chỉ được lưu ở cache riêng của client, **không** được lưu ở shared cache.
- **`Cache-Control: no-store`** yêu cầu các cache tuân thủ HTTP **không lưu** response/request liên quan.
- **Authentication/authorization** phải kiểm ai đang gọi và họ được phép xem dữ liệu gì; cache directives **không thay** việc kiểm quyền.

**Điểm cốt lõi:** không sửa lỗi rò rỉ dữ liệu riêng tư bằng cách thêm `Vary: Cookie` rồi tiếp tục cho CDN cache nội dung cá nhân hóa không kiểm soát. Với dữ liệu nhạy cảm, đặt chính sách **không lưu** hoặc **chỉ lưu riêng tư** trước, sau đó mới tối ưu cache khi có bằng chứng an toàn.

### Kết quả cần đạt

Sau bài, bạn sẽ:
1. Phân biệt private cache (browser) với shared cache (proxy/CDN).
2. Hiểu cache key, `Vary`, `Cache-Control` và quan hệ với `Accept-Language`, `Accept-Encoding`, `Origin`.
3. Biết tại sao `Cookie`, `Authorization` và `Set-Cookie` không tự bảo đảm rằng response luôn chỉ được dùng cho đúng user.
4. Chọn `no-store`, `private`, `no-cache`, `max-age`, `s-maxage`, `public` phù hợp.
5. Tạo Spring MVC controller dùng `ResponseEntity` và `CacheControl` để trả chính sách rõ ràng.
6. Kiểm thử hai users, ngôn ngữ và headers với MockMvc, sau đó kiểm thử CDN/reverse proxy thật khi triển khai.
7. Tránh việc ETag, response 304, service worker, browser history hoặc cache của ứng dụng làm lộ dữ liệu dù HTTP header đã đúng.

Bài sử dụng Java 17+, Spring Boot 3.x / Spring Framework 6.x. Ví dụ cụ thể dùng Spring Boot 3.3.5, Spring MVC Servlet stack và Spring Security HTTP Basic. Quy tắc HTTP dựa trên **RFC 9111**, không phải một tính năng riêng của Spring.

## 2. Bốn lớp cache thường thấy

~~~text
Browser của Alice
   |
   +-- Browser HTTP cache / memory cache (private)
   |
   +-- Service worker / Cache Storage nếu ứng dụng có triển khai
   |
   v
CDN / reverse proxy / API gateway (shared hoặc managed cache)
   |
   v
Spring MVC application
   |
   +-- Cache dữ liệu ứng dụng (ví dụ @Cacheable/Redis)
   |
   v
Database / service khác
~~~

### 2.1. Browser HTTP cache

Đây thường là **private cache** gắn với một client. Theo HTTP caching semantics, nó có thể giữ response `Cache-Control: private`. Nhưng máy tính dùng chung, browser profile dùng chung hoặc trạng thái sau logout vẫn tạo rủi ro: `private` không có nghĩa dữ liệu **không còn tồn tại trong thiết bị người dùng**.

### 2.2. Shared cache

CDN, proxy hoặc reverse proxy dùng chung tài nguyên cho nhiều client. Đây là nơi reuse response giúp tiết kiệm nhiều chi phí nhưng đồng thời nguy hiểm nếu cache key không phản ánh khác biệt theo người dùng.

Ví dụ:
- Một ảnh logo giống nhau cho mọi người: shared cache là ứng viên hợp lý.
- API `/api/me` phản ánh user hiện tại: không nên vô tình lưu chung.
- Bản tin public có ngôn ngữ tiếng Việt/tiếng Anh: có thể shared-cache theo `Accept-Language` nếu được thiết kế đúng.
- Báo cáo nội bộ tùy quyền: nên `private` hoặc `no-store` tùy tính nhạy cảm và policy.

### 2.3. Cache của Spring/service không phải HTTP cache

`@Cacheable` (Spring Cache abstraction) lưu **giá trị method** theo cache key trong JVM/Redis/...; nó **không tự phát `Cache-Control`, không tự hiểu `Vary` và không tự tách dữ liệu theo principal**.

Nếu service dùng:

~~~java
// SAI khi kết quả khác nhau theo người dùng mà key chỉ có "summary":
@Cacheable(cacheNames = "reports", key = "'summary'")
public Report summaryForCurrentUser() { ... }
~~~

Fragment minh họa sai, không phải code runnable của ứng dụng phía dưới. Khi Alice gọi trước, cache method có thể trả lại báo cáo của Alice cho Bob **ngay trong backend** dù HTTP response có `Cache-Control: no-store`. Cần cache key có user/tenant/permission scope đúng, authorization trước khi trả hoặc chủ động không cache. HTTP cache headers không sửa lỗi cache nội bộ.

### 2.4. Service worker, frontend stores và managed CDN có logic riêng

JavaScript `Cache API`, `localStorage`, state stores, service worker offline caches, client-side GraphQL caches và CDN rules tùy chỉnh không nhất thiết tuân thủ cùng quyết định lưu như HTTP browser cache. Cần thiết kế **tất cả** các tầng có thể lưu dữ liệu. Không chỉ thêm `no-store` phía backend rồi cho rằng mọi bản sao đã tồn tại ở service worker hoặc local storage tự xóa.

## 3. Cache key mặc định và tại sao URL chưa đủ

Một HTTP cache thông thường xét ít nhất request method và target URI, điều kiện storage của status/header, độ tươi của response và các header được chỉ định trong `Vary`.

~~~text
Primary key (khái niệm): target URI + request method liên quan
Secondary selection: những request header được response cũ liệt kê trong Vary
+ cache policy/status/freshness/revalidation
~~~

Đây là mô hình đọc hiểu, không phải bản mô tả đầy đủ mọi cache implementation. Một CDN có thể tùy biến key theo host, query, cookie, header, device, URL rewrite và custom VCL/rules.

### 3.1. Khác query string có thể khác tài nguyên

~~~text
GET /api/products?category=java
GET /api/products?category=spring
~~~

Đây là hai target URI khác nhau theo thông lệ HTTP. Tuy nhiên **managed CDN có thể được cấu hình bỏ qua query params** hoặc chỉ cho phép một số param trong cache key. Nếu `category` ảnh hưởng response nhưng CDN loại nó khỏi key, user có thể nhận dữ liệu sai.

### 3.2. Đăng nhập bằng cookie và URL giống nhau

~~~http
GET /api/me HTTP/1.1
Cookie: SESSION=alice-session-id
~~~

~~~http
GET /api/me HTTP/1.1
Cookie: SESSION=bob-session-id
~~~

Nếu cache key không phân biệt hoặc **không được phép lưu private content**, hai requests vẫn có cùng URL. Vì vậy cần định nghĩa rõ policy lưu. Cookie gắn với request **không tự khiến cache biết response phải riêng tư**.

### 3.3. Trường `Authorization` có bảo vệ trong RFC 9111, nhưng đừng dựa quá mức

RFC 9111 đặt rào chắn cho shared caches khi **request chứa Authorization**: không được sử dụng lại response đã cache để đáp ứng request khác, trừ khi response có directive cho phép dùng trong shared cache (ví dụ `public`, `s-maxage` hoặc `must-revalidate` trong điều kiện tương ứng).

Điều quan trọng:
- Rào chắn riêng của `Authorization` **không tự áp dụng tương tự cho `Cookie`**.
- Bạn có thể **vô tình vượt rào chắn** nếu trả `Cache-Control: public` hoặc `s-maxage` trên endpoint có Bearer/Basic mà body cá nhân hóa.
- Không assume mọi cache/CDN cấu hình tùy biến vẫn trung thành với các semantics mặc định.
- Một `Authorization: Bearer ...` header là credential; không để token xuất hiện trong logs, cache key công khai, URL hoặc metrics labels.

**Quy tắc an toàn:** với endpoint có dữ liệu cá nhân theo principal, trả `no-store` hoặc `private` có chủ đích ngay cả khi request dùng Authorization. Đừng chỉ trông cậy vào một ngoại lệ của RFC mà một lần refactor policy có thể làm thay đổi.

## 4. `Vary` thực sự làm gì?

HTTP response có thể nêu:

~~~http
Vary: Accept-Language
~~~

Nghĩa là nội dung thay đổi theo `Accept-Language` của request. Cache muốn tái sử dụng response đã lưu phải xét liệu các header được liệt kê trong `Vary` ở request hiện tại có phù hợp với request gốc hay không, theo quy tắc HTTP.

Ví dụ:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: vi-VN
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60
Vary: Accept-Language
Content-Type: application/json

{"language":"vi","message":"Xin chào"}
~~~

Cùng URL nhưng request khác:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: en-US
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60
Vary: Accept-Language
Content-Type: application/json

{"language":"en","message":"Hello"}
~~~

Hai representations này là **nội dung công khai**; vì thế có thể cho shared cache lưu theo `Accept-Language`. `Vary` không nhất thiết biến hai chuỗi header thành hai entries tách biệt trong mọi CDN, nhưng cache tuân thủ HTTP phải bảo đảm chỉ reuse khi matching rule thỏa.

### 4.1. `Vary` KHÔNG cấm cache lưu dữ liệu

~~~http
Vary: Cookie
Cache-Control: public, max-age=600
~~~

Mẫu trên **không an toàn làm mặc định cho nội dung /api/me**. Nó yêu cầu so khớp cookie khi reuse, nhưng vẫn cho phép shared cache lưu các bản personalized. Cookie có thể bao gồm dữ liệu theo session, thay đổi theo thời gian và có cardinality cực lớn. Một cấu hình CDN/custom cache-key có thể bỏ qua cookie hoặc normalize sai, gây rò rỉ.

Để cấm shared cache lưu **toàn bộ response**, chọn:

~~~http
Cache-Control: private, no-cache
~~~

Nếu không muốn lưu ở cache nào, chọn:

~~~http
Cache-Control: no-store
~~~

`Vary` chỉ phân biệt biến thể **khi có lưu hợp lệ**, không phải security boundary cho người dùng.

### 4.2. Những header thường gặp trong `Vary`

| Header được liệt kê | Khi nào có ích | Rủi ro/cân nhắc |
| --- | --- | --- |
| `Accept-Language` | Trang/dữ liệu public được bản địa hóa | Nhiều biến thể language tags; có thể normalize để giảm cache fragmentation |
| `Accept-Encoding` | gzip, br, identity khác bytes | Server/proxy thường tự bổ sung; không loại bỏ tùy tiện |
| `Accept` | API có JSON/XML hoặc representation formats khác | Tránh lưu JSON rồi trả cho client chỉ chấp nhận XML |
| `Origin` | CORS phản hồi allow-origin khác nhau theo request | Cần chống cache dùng sai CORS header; **không phải phân vùng theo user** |
| `User-Agent` | Nội dung thực sự khác theo thiết bị/UA | Header quá nhiều biến thể, hiệu quả cache thấp |
| `Cookie` | Có biến thể public phụ thuộc cookie vô hại, thật sự được thiết kế để lưu | Cardinality rất cao, nguy cơ private data, thường nên bypass thay vì Vary |
| `Authorization` | Nội dung cố tình được tách theo credential với policy đặc biệt | Không nên dùng như lựa chọn đầu tiên cho personalized response |

Một server có thể phát:

~~~http
Vary: Accept-Encoding, Accept-Language
~~~

Danh sách tên header không phân biệt hoa thường. Không tạo `Vary` vô cớ với hàng chục request headers; hiệu suất cache giảm và việc quản lý CDN phức tạp.

### 4.3. `Vary: *`

`Vary: *` có nghĩa cache **không thể xác nhận** một stored response thích hợp để reuse cho request tiếp theo bằng so sánh các header đã biết; theo HTTP caching, một response có `Vary: *` không được chọn để dùng lại như một response match thông thường.

Đây **không** là lệnh xóa dữ liệu đã lưu và không thay thế `Cache-Control: no-store`. Nếu mục tiêu là không lưu nội dung nhạy cảm, dùng `no-store` trực tiếp.

### 4.4. `Vary: Origin` trong CORS

Nếu server trả `Access-Control-Allow-Origin` tương ứng với origin được phép:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

thì response header phụ thuộc `Origin`. `Vary: Origin` giúp shared cache không tái sử dụng CORS response cho origin khác không phù hợp. Với preflight, thường thấy các biến thể dựa thêm vào `Access-Control-Request-Method` và `Access-Control-Request-Headers`.

Nhưng:
- CORS chỉ kiểm browser JavaScript có được **đọc** cross-origin response không.
- CORS không chứng minh user có quyền truy cập dữ liệu.
- `Vary: Origin` không chia người dùng nếu Alice và Bob dùng **cùng frontend origin**.
- CORS không thay `Cache-Control: private/no-store`, authentication, authorization hoặc CSRF.

Vì thế đừng cho rằng chỉ cần CORS allowlist + `Vary: Origin` là đủ bảo vệ `GET /api/me` khỏi shared caching.

## 5. `Cache-Control`: mỗi directive mang ý nghĩa gì?

| Directive | Cache nào có thể lưu? | Điều quan trọng |
| --- | --- | --- |
| `no-store` | Cache tuân thủ phải không lưu request/response tương ứng | Dùng cho dữ liệu nhạy cảm, token, giao dịch |
| `private` | Private cache có thể lưu, shared cache không được lưu toàn bộ | Phù hợp user-specific data có thể lưu trong browser |
| `no-cache` | Có thể lưu, nhưng phải revalidate thành công trước khi reuse | **Không** phải synonym của `no-store` |
| `max-age=60` | Cho phép freshness 60 giây khi cache đáp ứng mọi điều kiện | Không tự đồng nghĩa `public` hoặc bảo đảm safe cho shared |
| `s-maxage=120` | Đặt freshness cho shared caches, ưu tiên so với max-age ở shared | Có thể làm response có Authorization **được share** nếu cho phép |
| `public` | Cho phép shared cache lưu nếu các điều kiện khác cho phép | Nguy hiểm nếu bật nhầm cho personalized content |
| `must-revalidate` | Khi response stale, không được tự reuse nếu chưa revalidate như quy định | Có tương tác đáng chú ý với Authorization/shared caching |
| `immutable` | Cho biết content ít đổi trong thời gian fresh | Dùng cho asset fingerprinted, không phải user profile |
| `stale-while-revalidate` | Cho phép serve stale theo khoảng đề nghị nếu cache hỗ trợ | Cần đánh giá freshness/privacy cho dữ liệu user |
| `no-transform` | Yêu cầu intermediary không chỉnh biểu diễn | Không làm response private |

**Lưu ý:** thời gian cache là quyết định HTTP của cache tuân thủ. CDN có dashboard rules, edge functions, custom keys và surrogate directives riêng; cần kiểm tra policy triển khai thực tế. Không khẳng định một header luôn thắng mọi rule sản phẩm cache mà không thử.

### 5.1. `no-cache` vs `no-store`

Hai response:

~~~http
Cache-Control: no-cache
~~~

~~~http
Cache-Control: no-store
~~~

không tương đương. Với `no-cache`, cache **vẫn có thể lưu bytes** và dùng lại khi server xác nhận còn hợp lệ qua conditional request như `If-None-Match`/`If-Modified-Since`. Với `no-store`, cache tuân thủ phải không lưu response/request đó. Nếu có thông tin y tế, mã OTP, thông tin thanh toán hoặc dữ liệu nhạy cảm không nên được giữ ở cache, `no-store` thường là lựa chọn rõ ràng.

### 5.2. `private` vs `no-store`

~~~http
Cache-Control: private, max-age=30
~~~

cho phép **browser HTTP cache** giữ data trong 30 giây, nhưng cấm shared cache lưu response. Phù hợp khi trải nghiệm được hưởng lợi từ cache ngắn hạn và dữ liệu có mức nhạy cảm chấp nhận được.

~~~http
Cache-Control: no-store
~~~

yêu cầu không lưu ở private hoặc shared cache, phù hợp hơn với dữ liệu thật sự nhạy cảm. `private` không bảo vệ nếu attacker đang sử dụng **cùng browser profile** hoặc truy cập storage của thiết bị đã bị chiếm quyền.

### 5.3. `no-store` không thể xóa quá khứ

Nếu một CDN/browser **đã lưu nhầm** phiên bản cũ của response trước khi ứng dụng bổ sung `no-store`, header mới không tự xóa tất cả entries cũ ngay lập tức. Cần purge CDN keys, version URL khi cần, vô hiệu hóa policy cache lỗi, kiểm headers đúng và đánh giá liệu dữ liệu đã bị lộ.

Một managed cache có thể được cấu hình tùy chỉnh bỏ qua standard headers. Chỉ thêm `no-store` ở origin mà không sửa rule “cache everything” tại CDN là một giải pháp chưa đủ.

### 5.4. Không dựa vào `Pragma: no-cache` để sửa lỗi mới

`Pragma: no-cache` là cơ chế tương thích lịch sử của HTTP/1.0 ở request. Với response hiện đại, `Cache-Control` là giao diện rõ hơn và phải là nguồn chính. Tránh một bộ header mâu thuẫn kiểu “public, max-age một năm” nhưng đồng thời “no-store” mà không hiểu cache sẽ diễn giải ra sao.

## 6. Cookie, `Set-Cookie` và session: những giả định nguy hiểm

### 6.1. `Cookie` trong request không có nghĩa response tự private

Một request:

~~~http
GET /api/me HTTP/1.1
Cookie: SESSION=opaque-session-id
~~~

chỉ nói browser đang gửi cookie. Shared cache thường có rules tùy sản phẩm về cookie, nhưng **RFC HTTP caching không biến mọi request có Cookie thành “private” bằng phép màu**. Nếu response trả nội dung riêng, hãy phát `Cache-Control: private` hoặc `no-store` tùy mục tiêu và kiểm policy CDN.

### 6.2. `Set-Cookie` không phải lệnh cấm caching

Một response có:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session=opaque-id; HttpOnly; Secure; SameSite=Lax
~~~

không vì thế được bảo đảm shared caches sẽ không lưu mọi phần khác. Có các policy/proxy tùy biến xử lý `Set-Cookie`, nhưng bạn phải **chủ động** phân loại dữ liệu và khai báo Cache-Control. Nếu CDN lưu response kèm Set-Cookie của user A rồi phát cho user B, đây có thể là sự cố nghiêm trọng về session.

**Không dùng “có Set-Cookie nên CDN chắc chắn bypass” làm cơ sở an toàn.** Kiểm cấu hình cache product, response headers, test nhiều sessions và production logs có kiểm soát.

### 6.3. Cookie session khác bearer token

- Cookie session: browser có thể tự gửi theo domain/path/SameSite/Secure; HTTP caching không tự biết attribute nào phản ánh quyền.
- Bearer token: thường gửi trong `Authorization`, theo quy tắc RFC 9111 có hạn chế shared cache; vẫn có thể vô tình mở lại shared caching bằng directives.
- JWT không làm response tự an toàn để cache: dữ liệu trả ra vẫn có thể cá nhân hóa hoặc chứa nội dung chỉ một principal được phép xem.

### 6.4. Logout không tự xóa mọi cache

Khi logout:
- Server có thể invalidate session/refresh token và clear cookie.
- Browser HTTP cache có thể còn entries `private` nếu không được dọn/không hết hạn.
- Service worker hoặc application state có thể còn dữ liệu.
- Shared CDN đã cache sai có thể vẫn tiếp tục trả data nếu không purge.
- Browser back/forward cache và history snapshots có semantics riêng với HTTP caching.

Một hệ thống cần không lộ nội dung sau logout trên máy dùng chung có thể chọn `no-store` cho các trang/response nhạy cảm, dọn state frontend và dùng cơ chế cache/service worker phù hợp. `Cache-Control: no-store` không phải bảo đảm tuyệt đối xóa mọi bản sao; cần test browser và threat model thực tế.

## 7. Bảng chọn chính sách theo loại nội dung

| Loại tài nguyên | Policy gợi ý | Giải thích |
| --- | --- | --- |
| JS/CSS fingerprinted, nội dung tĩnh công khai | `public, max-age=31536000, immutable` | URL đổi khi nội dung đổi |
| Danh mục sản phẩm công khai, cùng dữ liệu mọi người | `public, max-age=60` | Shared cache có ích |
| Bản dịch công khai theo `Accept-Language` | `public, max-age=60` + `Vary: Accept-Language` | Cache chọn đúng biến thể |
| Trang dashboard user, dữ liệu ít nhạy, được phép lưu trên thiết bị riêng | `private, max-age=20` | Không lưu ở shared cache; cần đánh giá sau logout |
| Profile cá nhân, thông tin tài khoản | `no-store` hoặc `private, no-cache` tùy chính sách bảo mật | Phải cân nhắc việc còn bản sao trên browser |
| Mã OTP, token, thông tin thanh toán/nhạy cảm | `no-store` | Tránh lưu lại ở các HTTP caches tuân thủ |
| API báo cáo tùy role/tenant | `no-store` nếu chưa có chiến lược cache đúng quyền | Không lấy “URL giống nhau” làm cache key an toàn |
| Response lỗi 401/403 liên quan principal | Thường `no-store` | Tránh tái sử dụng error body mang dữ liệu cá nhân |
| Download file riêng tư | Thường `private` hoặc `no-store` theo độ nhạy | CDN và Content-Disposition cần được kiểm soát |

Đây là **khuyến nghị thiết kế**, không phải bảng header bắt buộc RFC cho mọi tài nguyên. Một ứng dụng có business requirements cụ thể có thể chọn chính sách khác sau khi chứng minh dữ liệu được phân vùng và cache implementation tuân thủ.

## 8. Mối quan hệ giữa `Vary`, `ETag` và `304 Not Modified`

Một response public có thể sử dụng ETag để tiết kiệm bandwidth:

~~~http
HTTP/1.1 200 OK
ETag: "greeting-vi-v1"
Vary: Accept-Language
Cache-Control: public, max-age=60
Content-Type: application/json

{"language":"vi","message":"Xin chào"}
~~~

Khi response stale, client/cache có thể gửi:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: vi-VN
If-None-Match: "greeting-vi-v1"
~~~

Server trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "greeting-vi-v1"
Vary: Accept-Language
Cache-Control: public, max-age=60
~~~

Cache có thể reuse body đã lưu đúng biến thể theo quy tắc HTTP. `304` không có body resource, nhưng vẫn có ý nghĩa metadata; việc kết hợp 304 với stored response phải tuân theo quy tắc update/selection của RFC 9111.

### 8.1. Validator cũng phải gắn với representation đúng

Nếu một endpoint thay đổi theo user hoặc language, **không dùng một ETag global duy nhất** cho mọi representation khi điều đó làm server đánh giá 304 sai. Ví dụ hash chỉ theo số bản ghi mà không tính user permission có thể dẫn đến phản hồi sai hoặc khiến client biết trạng thái không nên biết.

Với private/sensitive endpoint cần `no-store`, thường không cần ETag để cache reuse. Một ETag **không tự làm dữ liệu an toàn**: nó chỉ giúp xác định phiên bản và revalidation khi có quyền.

### 8.2. `ShallowEtagHeaderFilter` không kiểm soát cache privacy

Spring MVC có `ShallowEtagHeaderFilter` để tạo ETag từ bytes response đã render, hỗ trợ một số luồng conditional requests. Bộ lọc này không quyết định response nào nên public/private và có thể cần buffer response, gây chi phí tài nguyên. Nó không thay `Cache-Control` và không sửa rủi ro CDN lưu nhầm dữ liệu personalized.

Với nội dung riêng tư, vẫn cần authorization chính xác và `no-store/private`. Với dữ liệu lớn hoặc dynamic, ETag dựa trên phiên bản tài nguyên mà không render body trước có thể hiệu quả hơn, nhưng cần đảm bảo validator đúng representation/permission.

## 9. Spring MVC: `ResponseEntity` và `CacheControl`

Spring Framework cung cấp `org.springframework.http.CacheControl` để xây Cache-Control mà không ghép chuỗi thủ công:

~~~java
CacheControl.noStore();
CacheControl.noCache();
CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic();
CacheControl.maxAge(Duration.ofSeconds(20)).cachePrivate();
~~~

Đây là các Java expressions minh họa; cần imports `java.time.Duration` và `org.springframework.http.CacheControl` khi dùng trong file thực. Tương ứng các headers:
- `no-store`
- `no-cache`
- `max-age=60, public`
- `max-age=20, private`

Controller có thể trả:

~~~java
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(new Profile("alice"));
~~~

Đây là fragment giả định có record `Profile`, không tự biên dịch riêng. `ResponseEntity.BodyBuilder.cacheControl(...)` ghi Cache-Control response header; status, body, type và other headers do MVC xử lý. Trả một Java DTO không mặc định chứng minh nó an toàn để shared cache.

### 9.1. Đừng nhầm `@Cacheable` với `CacheControl`

| API | Tầng | Vai trò |
| --- | --- | --- |
| `@Cacheable` | Spring Cache abstraction (service/method) | Cache kết quả method trong store của ứng dụng |
| `CacheControl` | Spring Web HTTP response | Tạo `Cache-Control` header |
| `ResponseEntity` | Spring MVC | Status, headers và response body |
| `ShallowEtagHeaderFilter` | Spring Web filter | Tạo/kiểm validator HTTP cho body đã render |
| `WebContentInterceptor` | Spring MVC | Thiết lập cache policy theo URL patterns |
| CDN cache rule | Infrastructure | Lưu/serve HTTP response tại edge/proxy |

Cùng từ “cache” nhưng **different scopes and keys**. Có thể cache method tại backend mà response HTTP luôn `no-store`, hoặc không cache method nhưng browser vẫn cache HTTP. Hãy xác định tầng nào đang giữ data khi debug.

## 10. Ví dụ hoàn chỉnh: Spring Boot 3.3.5 + Security + caching headers

Ứng dụng demo cung cấp ba endpoints:
1. `GET /api/public/greeting` — **public**, tiếng Việt/Anh theo locale, cho phép shared cache 60 giây và có `Vary: Accept-Language`.
2. `GET /api/me/profile` — **bắt buộc xác thực**, mỗi user có body khác nhau, trả `Cache-Control: no-store`.
3. `GET /api/me/preview` — **bắt buộc xác thực**, dữ liệu demo ít nhạy hơn, cho phép **private browser cache** tối đa 20 giây nhưng cấm shared cache.

Không có database, không có CDN. HTTP Basic ở đây chỉ dùng để phân biệt Alice và Bob một cách dễ kiểm thử, **không phải cơ chế dành riêng cho mọi API thực tế**. Backend xác định identity từ `Principal` đã xác thực; client không được tự đưa `user` trong query để đổi quyền.

~~~text
http-cache-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/httpcache/
    │   ├── HttpCacheApplication.java
    │   ├── security/SecurityConfig.java
    │   └── web/CacheDemoController.java
    └── test/java/com/example/httpcache/
        └── CacheDemoIntegrationTest.java
~~~

### 10.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'http-cache-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` có Servlet MVC và Jackson. `spring-boot-starter-security` thêm filter chain/auth. `spring-security-test` cung cấp `httpBasic(...)` để test request qua SecurityFilterChain. Ví dụ Java 17 và Gradle wrapper tương thích.

### 10.2. Main application

`src/main/java/com/example/httpcache/HttpCacheApplication.java`:

~~~java
package com.example.httpcache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpCacheApplication.class, args);
    }
}
~~~

### 10.3. Spring Security: xác thực bằng HTTP Basic

`src/main/java/com/example/httpcache/security/SecurityConfig.java`:

~~~java
package com.example.httpcache.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/me/**").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-local-demo"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-local-demo"))
                        .roles("USER")
                        .build());
    }
}
~~~

Ghi chú:
- `/api/public/**` không cần authentication; `/api/me/**` bắt buộc authenticated principal.
- `SessionCreationPolicy.STATELESS` tránh dùng session HTTP cho SecurityContext ở demo Basic, giúp test tách user rõ ràng. Nó **không ngăn code khác tạo HttpSession**; còn tùy ứng dụng.
- Cấu hình không gọi `csrf().disable()`; GET không thuộc các unsafe methods thường yêu cầu CSRF token, nên demo không cần thay CSRF policy.
- Username/password in-memory chỉ dành cho bài học local; production dùng identity provider/secret management và HTTPS.
- `Authorization` trong HTTP Basic phải giữ kín tương đương password; base64 không phải encryption. Khi dùng curl với `-u` trên mạng thật, phải dùng TLS.
- Security mặc định có thể phát cache-related response headers bảo vệ tài nguyên. Trong ví dụ, controller đặt `Cache-Control` tường minh cho từng endpoint; kiểm response cuối sau toàn bộ filter chain thay vì đoán Spring Security hoặc MVC “tự thắng”.

### 10.4. Controller: public `Vary`, private `no-store`

`src/main/java/com/example/httpcache/web/CacheDemoController.java`:

~~~java
package com.example.httpcache.web;

import java.security.Principal;
import java.time.Duration;
import java.util.Locale;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class CacheDemoController {

    public record Greeting(String language, String message) {}
    public record Profile(String username, String displayName) {}
    public record Preview(String username, String label) {}

    @GetMapping("/public/greeting")
    public ResponseEntity<Greeting> greeting(Locale locale) {
        String language = "vi".equals(locale.getLanguage()) ? "vi" : "en";
        String message = "vi".equals(language) ? "Xin chào" : "Hello";

        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(60))
                                .cachePublic())
                .header(HttpHeaders.VARY, HttpHeaders.ACCEPT_LANGUAGE)
                .body(new Greeting(language, message));
    }

    @GetMapping("/me/profile")
    public ResponseEntity<Profile> profile(Principal principal) {
        String username = principal.getName();
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new Profile(username, "Profile for " + username));
    }

    @GetMapping("/me/preview")
    public ResponseEntity<Preview> preview(Principal principal) {
        String username = principal.getName();
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(20))
                                .cachePrivate())
                .body(new Preview(username, "Private preview"));
    }
}
~~~

**Vì sao code này bảo vệ được những trường hợp cụ thể?**
1. Public greeting không chứa user-specific data và trả đúng locale variant. `Vary: Accept-Language` làm rõ yếu tố thay đổi content.
2. Profile lấy username từ `Principal` đã được Security xác thực; không tin một `?user=alice` hoặc cookie được client khai báo như business identity.
3. Response profile có `no-store`, yêu cầu HTTP caches tuân thủ không lưu body cá nhân.
4. Preview có `private`, shared cache không được lưu; browser HTTP cache được lưu ngắn hạn theo policy. **Không dùng preview pattern cho dữ liệu có quy định không được lưu trên thiết bị**.
5. Không đặt `Vary: Cookie` lên endpoints `/me` như một cách thay `no-store/private`.
6. Không lưu raw password/token/session ID trong JSON. Cache-Control không bảo vệ được những thông tin đã lộ trong response body hoặc logs.
7. Một proxy/CDN có thể vẫn sai nếu được cấu hình bỏ qua headers; cần test tại deployment thật.

### 10.5. Kết quả HTTP dự kiến

Public Vietnamese:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: vi-VN,vi;q=0.9
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: max-age=60, public
Vary: Accept-Language
Content-Type: application/json

{"language":"vi","message":"Xin chào"}
~~~

Public English:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: en-US,en;q=0.9
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: max-age=60, public
Vary: Accept-Language
Content-Type: application/json

{"language":"en","message":"Hello"}
~~~

Alice profile:

~~~http
GET /api/me/profile HTTP/1.1
Authorization: Basic <alice-credential>
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"username":"alice","displayName":"Profile for alice"}
~~~

Bob profile:

~~~http
GET /api/me/profile HTTP/1.1
Authorization: Basic <bob-credential>
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"username":"bob","displayName":"Profile for bob"}
~~~

`<alice-credential>` và `<bob-credential>` là placeholder minh họa trên HTTP wire, không phải giá trị để copy vào lệnh thực; curl ở phần sau sẽ tạo Basic header từ username/password demo.

## 11. MockMvc: chứng minh đúng headers và không lẫn user

`src/test/java/com/example/httpcache/CacheDemoIntegrationTest.java`:

~~~java
package com.example.httpcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CacheDemoIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicVietnameseVariantDeclaresVary() throws Exception {
        mvc.perform(get("/api/public/greeting")
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN,vi;q=0.9"))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL,
                        "max-age=60, public"))
                .andExpect(header().string(HttpHeaders.VARY,
                        containsString(HttpHeaders.ACCEPT_LANGUAGE)))
                .andExpect(jsonPath("$.language").value("vi"))
                .andExpect(jsonPath("$.message").value("Xin chào"));
    }

    @Test
    void publicEnglishVariantHasDifferentBody() throws Exception {
        mvc.perform(get("/api/public/greeting")
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "en-US"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("en"))
                .andExpect(jsonPath("$.message").value("Hello"));
    }

    @Test
    void protectedProfileNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceProfileIsNeverHttpCached() throws Exception {
        mvc.perform(get("/api/me/profile")
                        .with(httpBasic("alice", "alice-local-demo")))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.displayName")
                        .value("Profile for alice"));
    }

    @Test
    void bobNeverReceivesAlicesBody() throws Exception {
        mvc.perform(get("/api/me/profile")
                        .with(httpBasic("alice", "alice-local-demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/me/profile")
                        .with(httpBasic("bob", "bob-local-demo")))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(jsonPath("$.username").value("bob"))
                .andExpect(jsonPath("$.displayName")
                        .value("Profile for bob"));
    }

    @Test
    void privatePreviewIsNotMarkedPublic() throws Exception {
        mvc.perform(get("/api/me/preview")
                        .with(httpBasic("alice", "alice-local-demo")))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL,
                        "max-age=20, private"))
                .andExpect(jsonPath("$.username").value("alice"));
    }
}
~~~

Chạy bằng Gradle wrapper của project:

~~~bash
./gradlew test
~~~

Test kiểm:
- Public endpoint thực sự có `Vary: Accept-Language` và Cache-Control public.
- Hai locale nhận hai JSON bodies tương ứng.
- Route private cần xác thực.
- Alice và Bob nhận response **riêng khi đi tới origin Spring app**.
- Cả hai response profile đều có `no-store`.
- Preview nhận `private` thay vì `public`.

**Giới hạn quan trọng:** MockMvc **không đóng vai CDN HTTP cache**. Test "bobNeverReceivesAlicesBody" chỉ chứng minh controller/Security không dùng nhầm principal trong app; nó **không chứng minh CDN đã được cấu hình bypass/no-store đúng**. Cần test qua reverse proxy/CDN thật hoặc một caching proxy integration test, với cache hit/miss/age headers có kiểm soát.

Test cũng không nên dựa vào thứ tự tất cả response headers; kiểm những directives và values có ý nghĩa. Khi application security configuration thay đổi, hãy xác minh Cache-Control cuối cùng sau filters.

## 12. Chạy HTTP và quan sát bằng curl

Trong project có Java 17 và Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

### 12.1. Public resource với hai ngôn ngữ

~~~bash
curl -i 'http://localhost:8080/api/public/greeting' \
  -H 'Accept-Language: vi-VN,vi;q=0.9'

curl -i 'http://localhost:8080/api/public/greeting' \
  -H 'Accept-Language: en-US'
~~~

Quan sát:
- Hai responses có `Cache-Control: max-age=60, public`.
- Có `Vary: Accept-Language`.
- Body hiển thị ngôn ngữ `vi` hoặc `en` đúng request.

**curl không phải HTTP cache theo mặc định**: việc gọi hai URL liên tiếp không tự chứng minh shared cache tách variant. Nó chỉ xác minh origin tạo response khác nhau đúng headers.

### 12.2. Profile cá nhân không lưu HTTP

~~~bash
curl -i -u alice:alice-local-demo \
  'http://localhost:8080/api/me/profile'

curl -i -u bob:bob-local-demo \
  'http://localhost:8080/api/me/profile'
~~~

Dự kiến Alice nhận `"username":"alice"`, Bob nhận `"username":"bob"`. Cả hai có `Cache-Control: no-store`. Không nên thấy `public` hoặc `s-maxage` trong policy của endpoint này.

Với request thiếu credentials:

~~~bash
curl -i 'http://localhost:8080/api/me/profile'
~~~

Dự kiến `401 Unauthorized` do Spring Security. Status không phải bằng chứng CDN an toàn; cần kiểm các response lỗi/auth paths không bị cached nhầm.

### 12.3. Preview chỉ lưu ở private cache

~~~bash
curl -i -u alice:alice-local-demo \
  'http://localhost:8080/api/me/preview'
~~~

Dự kiến:

~~~http
Cache-Control: max-age=20, private
~~~

Dù private cache có thể lưu trong khoảng ngắn, **đây không phải phương án cho dữ liệu phải biến mất hoàn toàn sau logout**. Khi muốn cấm lưu, đổi policy thành `no-store` và bổ sung test.

### 12.4. Nếu muốn chứng minh CDN có rò rỉ không

Đặt ứng dụng sau một **staging** CDN/proxy có cấu hình giống production, tạo hai account thử nghiệm không chứa thông tin thật và kiểm:
1. Alice gửi GET profile qua chính CDN hostname, xác nhận body Alice và `no-store`.
2. Bob gửi GET cùng URL, body phải là Bob, không phải Alice.
3. Thử đổi thứ tự Bob trước rồi Alice, lặp lại sau cache warm.
4. Kiểm các header cache quan sát như `Age`, `Via`, `X-Cache`, `CF-Cache-Status` hoặc header đặc thù nhà cung cấp **nếu thực sự có**. Không tự suy đoán Hit/Miss khi provider không cấp dữ liệu.
5. Thử 401/403/404/500 error responses của endpoint private; bảo đảm chúng cũng không vô tình tiết lộ thông tin hoặc bị lưu chung.
6. Thử với cookie-based session nếu ứng dụng thật dùng cookie thay HTTP Basic.
7. Thử deployment rule “cache everything”, Edge/Worker functions và query normalization.
8. Nếu phát hiện rò rỉ, tắt rule cache lỗi, purge data và xử lý như security incident; không chỉ thay một header rồi kết luận đã hết rủi ro.

Không đưa raw session cookies, token hoặc account thật vào test logs/public tickets.

## 13. Cấu hình CDN: bypass ở biên cần tương thích origin

Một chiến lược an toàn cho API hỗn hợp là:

~~~text
/api/public/**   -> ứng viên shared cache; allowlist TTL/method/query/header
/api/me/**       -> bypass shared cache; origin cũng trả no-store/private
/admin/**        -> bypass trừ khi có kiến trúc cache theo tenant/permission rất rõ
/static/**       -> public immutable khi URL fingerprinted
~~~

Đây là **sơ đồ policy**, không phải cú pháp config của bất kỳ CDN cụ thể nào. Mỗi nhà cung cấp có naming/rules khác nhau.

### 13.1. Bypass theo đường dẫn không thay authorization

Ngay cả khi CDN bypass `/api/me/**`, backend vẫn phải xác thực user và kiểm quyền tài nguyên. Một attacker có thể gọi origin trực tiếp nếu network cho phép; policy CDN không thay security ở application/service.

### 13.2. Không chỉ bypass khi có `Cookie`

Một API riêng tư có thể xác thực bằng `Authorization` thay cookie. Nếu rule CDN chỉ bypass khi có Cookie, Bearer endpoint có thể bị cache. Ngược lại, một public page vẫn có analytics cookie; chỉ vì có Cookie không phải lúc nào phải tắt shared cache nếu content thực sự công khai, nhưng cần thiết kế và kiểm.

### 13.3. Custom cache key và query params

Nếu backend đáp ứng `GET /reports?id=1` và `GET /reports?id=2` khác nhau, CDN không được loại `id` khỏi key. Nếu resource còn phụ thuộc locale/device headers, cần áp dụng `Vary` hoặc cache key policy đúng. Nếu resource phụ thuộc role/tenant, **không dùng một key dựa trên một header do client tự gửi** khi chưa có bước xác thực/ủy quyền đáng tin.

### 13.4. Cache purge sau khi phát hiện sai sót

Nếu dữ liệu người dùng đã được lưu ở shared cache:
- Tạm bypass endpoint nhạy cảm và ngăn tạo entries mới.
- Purge theo cache keys/tags/path đúng provider, bao gồm variants và vùng edge liên quan.
- Kiểm lại response headers và actual cache rules.
- Rà logs/audit theo quy trình an ninh và đánh giá phạm vi/ảnh hưởng.
- Có thể cần rotate/revoke session/credentials nếu chúng cũng bị lộ.
- Kiểm service workers/frontend stores và clients bị ảnh hưởng khi cần.

`no-store` mới chỉ ngăn cache tuân thủ tạo/giữ response tương lai theo policy, **không bảo đảm xóa bản sao cũ hoặc data đã bị người dùng khác nhìn thấy**.

## 14. Xử lý `Vary` với locale, compression và API format

### 14.1. Accept-Language

Nếu trang trả content theo `Accept-Language`, có `Vary: Accept-Language`. Tuy nhiên giá trị header có nhiều tổ hợp như `vi-VN,vi;q=0.9,en;q=0.5` nên shared cache có thể có quá nhiều variants.

Tối ưu có chủ đích:
- Chọn vài locale mà sản phẩm hỗ trợ, có fallback rõ.
- Có thể chuyển public translated resource thành URL tường minh `/vi/articles/123`, `/en/articles/123` nếu phù hợp.
- Chỉ thêm `Vary` khi response thực sự khác theo header.
- Nếu response cá nhân hóa theo user preference lưu server, `Vary: Accept-Language` **không tự phản ánh user preference**; cần `private`/`no-store` trước.

### 14.2. Accept-Encoding

Compression khác nhau theo `Accept-Encoding: gzip` hoặc `br` thường cần `Vary: Accept-Encoding` để cache không trả representation/encoding không phù hợp. Spring Boot/Tomcat/reverse proxy có thể thêm header compression khác nhau; không loại `Vary: Accept-Encoding` do server/proxy tạo chỉ vì controller tự thêm một `Vary` khác.

### 14.3. Accept

API có thể trả JSON hay XML tùy `Accept` và message converters. Nếu bytes/type khác, `Vary: Accept` thường là cần thiết trong response cacheable. Nếu API chỉ luôn JSON và không có alternate representations, thêm `Vary: Accept` có thể không mang lợi ích rõ ràng nhưng tăng variants.

### 14.4. Origin

Với CORS policy cho origin khác nhau, `Vary: Origin` giúp chọn response có `Access-Control-Allow-Origin` phù hợp. **Không tự kết luận response public vì CORS allow-Origin hợp lệ**. Nếu body phụ thuộc vào user cùng frontend origin, Vary: Origin không phân tách họ.

## 15. Security defaults, error responses và điều kiện thực tế

### 15.1. Spring Security cache headers mặc định

Spring Security Servlet thường phát các security response headers, trong đó có cache-related headers để giảm rủi ro cache dữ liệu nhạy cảm trong cấu hình mặc định. Một số response mặc định có dạng:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Đây là **ví dụ thường gặp**, không phải header bắt buộc của mọi Spring Boot/Security project. Security headers writer có thể không ghi đè một Cache-Control do ứng dụng đã đặt. Trong demo, public endpoint khai báo `max-age=60, public`, private endpoint khai báo `no-store`; bạn phải **kiểm response cuối cùng qua MockMvc và HTTP**.

Đừng vô hiệu hóa tất cả security headers để cache một trang public. Hãy đặt cache policy chủ đích cho endpoint thực sự an toàn, giữ bảo vệ các routes còn lại.

### 15.2. Error response cũng có thể chứa private data

Một error JSON có thể phản chiếu email, tenant, user ID, rejected values, resource names hoặc internal diagnostics. Vì thế 400/401/403/404/500 của private routes cần policy riêng và không đưa dữ liệu nhạy cảm vào shared cache. Không assume status 4xx/5xx luôn không cacheable theo mọi tình huống: điều kiện cache của từng status, headers và managed CDN có thể khác nhau.

CORS 403 response và 401 authentication challenge thường được tạo trước controller; `@RestControllerAdvice` không nhất thiết xử lý những responses đó. Cần kiểm filter/exception handler layer và edge policy thay vì chỉ nhìn các return từ controller.

### 15.3. Conditional requests và phân quyền

Nếu một private endpoint dùng ETag:
- Authentication/authorization vẫn phải được áp dụng cho request revalidation.
- ETag phải thuộc đúng representation mà user được phép thấy.
- Không trả 304 cho một user khác chỉ vì `If-None-Match` trùng một ID global.
- Với nội dung rất nhạy cảm, `no-store` thường đơn giản và an toàn hơn caching/revalidation.

Một stale entry còn trong CDN do cấu hình sai có thể bỏ qua origin auth check hoàn toàn; đó là lý do cache rules cần được review như **một phần security architecture**, không chỉ hiệu năng.

## 16. Những nhầm lẫn nguy hiểm thường gặp

| Nhầm lẫn hoặc lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Thêm `Vary: Cookie` và đánh dấu `public` cho `/api/me` | Shared cache có thể lưu dữ liệu theo phiên, rủi ro leak | `no-store` hoặc `private`, bypass CDN |
| Cho rằng request có Cookie tự no-cache | Proxy lưu response cá nhân nếu policy cho phép | Đặt Cache-Control rõ, test edge |
| Cho rằng `Set-Cookie` chắc chắn cấm CDN caching | Cache có thể lưu response/cookie theo rule | Phân loại data, bypass và kiểm CDN config |
| Hiểu `no-cache` là không lưu | Bytes cá nhân có thể nằm trong browser cache | Dùng `no-store` khi thực sự cấm lưu |
| Cho `public` trên endpoint dùng Authorization | Có thể mở shared caching theo RFC | Chỉ public khi body không phụ thuộc principal |
| Tin `Vary: Origin` là phân quyền người dùng | Hai user cùng origin vẫn dùng chung variant | AuthZ + no-store/private cho personalized data |
| Không vary theo Accept-Language | Cache trả sai ngôn ngữ | Thêm `Vary: Accept-Language` |
| Không vary theo Accept-Encoding | Cache trả content encoding không hợp client | Để compression layer phát Vary đúng |
| CDN bỏ query parameter ảnh hưởng nội dung | Response cho query khác bị trộn | Kiểm cache key và URL rules |
| Cache `@Cacheable` thiếu user/tenant | Backend trả data người trước cho người sau | Scope method cache key theo quyền hoặc bỏ cache |
| Security default no-store bị vô tình override | Private response có TTL shared cache | Test headers sau toàn bộ filter chain |
| Logout nhưng trình duyệt còn dashboard | `private` vẫn cho local cache | Cân nhắc `no-store` và xóa app state |
| Mới thêm no-store rồi nghĩ cache cũ biến mất | Stale CDN entries còn | Purge, kiểm cache status, đánh giá incident |
| ETag giống nhau giữa user dù body khác | 304 có thể đánh giá sai và leak metadata | Validator theo representation, auth trước conditional |
| MockMvc 2 user pass nên tin CDN an toàn | MockMvc không mô phỏng shared cache | Test staging qua CDN với 2 sessions |
| CDN cache 401/403 chứa private details | Lộ error/context | Policy lỗi không share, safe detail |
| CORS cho phép origin nên bỏ auth | Site khác vẫn có thể đọc dữ liệu nếu quyền thiếu | Giữ authentication/authorization |
| Thấy `Age` tăng mà route đáng lẽ no-store | Edge cache sai policy hoặc stale response | Kiểm CDN rule, purge và incident triage |

## 17. Quy trình kiểm thử tránh lộ dữ liệu xuyên người dùng

1. Liệt kê endpoint trả nội dung personalized (user, role, tenant, session, AB variant) và mọi cache layer có thể xử lý.
2. Ghi rõ HTTP policy cho từng route: public/private/no-store, `Vary` có ý nghĩa gì, TTL và auth requirement.
3. Ở unit/MockMvc, assert Cache-Control/Vary và body đúng với Alice/Bob; đừng chỉ assert 200.
4. Ở integration qua CDN, gửi cùng URL bằng hai credentials/cookies khác nhau, đổi thứ tự, warm cache rồi lặp.
5. Kiểm headers `Age`/`Via`/cache-status của provider nếu có; test cách CDN xử lý Authorization, Cookie, Set-Cookie và query params.
6. Kiểm cả 200, 304, redirects, 401, 403, 404, 500 và file downloads nếu ứng dụng có.
7. Thử locale/encoding/CORS Origin variants, bảo đảm không reuse representation sai.
8. Kiểm Spring Cache/Redis keys và dữ liệu service: một HTTP no-store vẫn có thể che một bug backend cache.
9. Kiểm browser sau logout, Back/Forward, service worker và app state theo yêu cầu privacy của sản phẩm.
10. Trong production, giám sát bất thường cache hit của private paths, xuất hiện `public`/`s-maxage` không chủ đích, CDN rules mới và security regressions.
11. Chạy test trước/sau thay đổi CDN, SecurityFilterChain, Spring MVC caching/interceptors, gateways và chuyển dịch user/session model.
12. Nếu phát hiện rò rỉ, xử lý như security incident: containment, purge, rotation khi cần, audit và xác minh phục hồi.

### Câu hỏi tự kiểm tra

**1.** `Vary: Accept-Language` có ngăn một CDN lưu response không?

**Trả lời:** Không. Nó yêu cầu xem xét giá trị Accept-Language khi chọn response đã lưu để reuse; có thể dùng cùng với một cache policy cho phép lưu.

**2.** `Vary: Cookie` có an toàn mặc định cho `/api/me` không?

**Trả lời:** Không. Cookie có độ biến thiên lớn và `Vary` không cấm shared cache lưu; nên đặt `private` hoặc `no-store`.

**3.** Dữ liệu cá nhân có thể lưu browser nhưng không được CDN lưu thì chọn gì?

**Trả lời:** `Cache-Control: private`, có thể kết hợp TTL hoặc revalidation tùy chính sách.

**4.** Muốn mọi HTTP cache tuân thủ không lưu profile nhạy cảm?

**Trả lời:** `Cache-Control: no-store`. Vẫn cần xử lý CDN custom rules, cache cũ, service workers và cache nội bộ.

**5.** `Cache-Control: no-cache` nghĩa là cache không giữ bản copy?

**Trả lời:** Không. Cache có thể lưu nhưng phải revalidate trước reuse.

**6.** Vì sao `public`/`s-maxage` phải cẩn thận khi request có Authorization?

**Trả lời:** Những directives này có thể cho phép shared caching của response vốn được request bằng Authorization theo RFC 9111. Nếu body personalized, có nguy cơ lộ dữ liệu.

**7.** Vì sao MockMvc test hai users chưa chứng minh không leak qua CDN?

**Trả lời:** MockMvc chạy qua Spring application, không mô phỏng CDN key/rule/hit/miss. Phải test staging proxy thực hoặc integration cache tương đương.

**8.** CORS `Vary: Origin` có thay authorization theo principal không?

**Trả lời:** Không. Origin của frontend có thể giống nhau cho mọi người dùng; authorization phải dựa trên identity/quyền và server-side policy.

**9.** `@Cacheable` có tự tôn trọng `Cache-Control: no-store` không?

**Trả lời:** Không. Nó dùng method cache ở ứng dụng, cần cache key riêng đúng user/tenant hoặc không cache.

## 18. Tài liệu chính thức để tra cứu

- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): storage, shared caches, Vary matching, revalidation, Cache-Control, Authorization.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): request/response fields, content negotiation, conditional requests và status.
- [MDN — HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): private/shared caches, Vary, no-store/no-cache và tình huống cá nhân hóa.
- [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): private/public/max-age/s-maxage/must-revalidate.
- [MDN — Vary](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary): cache selection theo request header.
- [Spring Framework — HTTP Caching trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): CacheControl, controller ETag/Last-Modified, static resources, ETag filter.
- [Spring Framework — CacheControl Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/http/CacheControl.html): builders `noStore`, `noCache`, `maxAge`, `cachePrivate`, `cachePublic`.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): mặc định bảo vệ, cache control, cấu hình security headers.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS policy và các response headers có `Vary: Origin`.
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable` ở service layer, khác HTTP caching.

**Ghi nhớ:** `Vary` giúp cache chọn đúng **biến thể** của một tài nguyên có thể cache; `Cache-Control` quyết định response có được **lưu và tái sử dụng** ở private/shared caches hay không; security xác định **ai được xem** nội dung. Nếu dữ liệu phụ thuộc user/tenant/session, ưu tiên `no-store` hoặc `private`, xác minh cả Spring và CDN, và tuyệt đối không coi `Vary: Cookie` hoặc `Vary: Origin` là một phép thay thế cho phân quyền và bảo vệ dữ liệu riêng tư.
