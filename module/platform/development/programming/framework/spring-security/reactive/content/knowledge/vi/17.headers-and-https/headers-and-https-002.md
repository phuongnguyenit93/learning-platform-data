# Cache-Control và hạn chế lưu đệm phản hồi chứa dữ liệu nhạy cảm

## 1. Bài toán: đã đăng xuất nhưng dữ liệu vẫn có thể tồn tại trong cache

Trong ứng dụng Spring Security Reactive chạy trên Spring WebFlux, một request thành công có thể trả về dữ liệu riêng tư như hồ sơ, số dư, lịch sử giao dịch, dữ liệu nhân sự, đơn hàng, tài liệu nội bộ, mã khôi phục tài khoản hoặc thông tin liên quan đến phiên đăng nhập. Kể cả khi Spring Security xác thực và phân quyền đúng ở thời điểm request, response có thể đi qua **browser cache, proxy, CDN hoặc các cache do ứng dụng/client tự quản lý**.

Nếu server vô tình cho phép lưu response nhạy cảm, các rủi ro gồm:

- Người khác sử dụng cùng thiết bị/browser có thể xem lại dữ liệu đã được cache sau khi người dùng đăng xuất.
- Proxy/CDN cấu hình sai có thể giữ và phát nội dung riêng cho một user tới người dùng khác.
- Dữ liệu tài khoản cũ có thể hiện ra khi chuyển user trên cùng trình duyệt.
- Thông tin trên giao diện không cập nhật sau logout, thay đổi quyền hoặc thay đổi chính sách riêng tư.
- Một response chứa token, reset-link, mã giao dịch hay dữ liệu cá nhân được lưu trên bộ nhớ đệm không cần thiết.
- Test HTTP chỉ xác minh status 200 mà bỏ qua `Cache-Control`, dẫn đến một lỗi khó phát hiện.

Trong Spring Security WebFlux, **Cache-Control là một lớp giảm rủi ro lưu trữ và tái sử dụng HTTP response**. Nó không thay cho xác thực, phân quyền, TLS, logout, chống XSS hay việc xóa dữ liệu do JavaScript lưu ở các nơi khác.

Bài này thuộc nhóm **Header và HTTPS**. Đề tài trực tiếp là **Cache-Control và hạn chế lưu đệm phản hồi chứa dữ liệu nhạy cảm**; trọng tâm là ngữ nghĩa HTTP headers, mặc định của Spring Security Reactive, cấu hình đúng trong WebFlux và kiểm thử.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích sự khác nhau giữa cache browser, cache chia sẻ, CDN, service worker và dữ liệu lưu trong ứng dụng.
2. Phân biệt chính xác `no-store`, `no-cache`, `private`, `public`, `max-age`, `must-revalidate` và các legacy headers.
3. Hiểu Spring Security Reactive mặc định gửi những header nào, khi nào ứng dụng được phép ghi đè và cách tránh tắt bảo vệ toàn cục.
4. Dùng `CacheControl.noStore()`, `ResponseEntity.cacheControl(...)` và `ServerHttpSecurity.headers(...)` trong WebFlux.
5. Bảo vệ response riêng tư nhưng vẫn cho phép cache tài nguyên **public, versioned** như CSS/JavaScript/images.
6. Chạy một dự án Java 17+ / Spring Boot / WebFlux Security và kiểm chứng bằng `curl`, `WebTestClient`.
7. Thiết kế cache policy cho 200/401/403, lỗi, file download, trình duyệt sau logout và CDN.
8. Xác định giới hạn của `no-store` và những kiểm soát khác bắt buộc đi kèm.

## 2. HTTP cache nằm ở đâu?

Một request có thể đi qua nhiều lớp:

~~~text
Browser / Mobile App
       |
       +--> Browser HTTP cache (memory/disk)
       +--> Back-forward page cache, page state, Service Worker Cache API
       +--> App state: localStorage, sessionStorage, IndexedDB, memory
       |
       v
Forward proxy / corporate gateway (nếu có)
       |
       v
CDN / reverse proxy cache
       |
       v
Spring WebFlux + Spring Security Reactive
       |
       v
Service / Database
~~~

Không phải tất cả lớp trên đều dùng `Cache-Control` giống nhau:

- **Browser HTTP cache:** thường diễn giải các chỉ thị HTTP caching cho response được phép lưu.
- **Shared cache:** reverse proxy/CDN có thể phục vụ cùng một response cho nhiều client. Nó phải tuân theo semantics `private`/`no-store` và quy tắc với Authorization, trừ khi có cấu hình hoặc hành vi vi phạm.
- **Browser back-forward cache (BFCache):** có thể giữ một trang và trạng thái render khi người dùng chuyển trang rồi bấm Back; hành vi liên quan `no-store` còn phụ thuộc phiên bản/chính sách browser, không nên hứa rằng header một mình luôn xóa giao diện.
- **Service Worker / Cache API:** code JavaScript có thể tự lưu response theo thiết kế. `Cache-Control` không phải lệnh tự động xóa mọi bản sao do ứng dụng chủ động lưu trong Cache API.
- **localStorage / sessionStorage / IndexedDB / biến memory của SPA:** không phải HTTP cache; `Cache-Control: no-store` không tự xóa dữ liệu đã ghi ở những nơi này.
- **Server-side cache** như Redis/Caffeine: điều khiển hiệu năng backend, không tự quyết định browser có lưu response không.

Vì vậy, muốn bảo vệ dữ liệu nhạy cảm, trước hết cần trả lời: **response có thể bị lưu ở lớp nào**, và lớp đó có thực sự tôn trọng HTTP caching directives không?

### 2.1. HTTP cache không phải Spring Cache

Trong Java, `@Cacheable` / `CacheManager` thường nói tới cache kết quả tính toán hoặc truy vấn **bên trong hệ thống server**. `Cache-Control` là header trên **HTTP response** để các HTTP caches biết cách lưu/tái sử dụng dữ liệu. Hai cơ chế độc lập.

Một service có thể cache dữ liệu nghiệp vụ trong Redis để tối ưu truy vấn nhưng trả `Cache-Control: no-store` ra browser; ngược lại một API không dùng Redis vẫn có thể vô tình cho phép CDN lưu response.

Đừng nhầm cache của Spring Session, cache ở database và cache của browser.

## 3. Các HTTP cache directives quan trọng theo RFC 9111

Đọc kỹ ngữ nghĩa trước khi viết cấu hình. Đây là khác biệt cốt lõi của bài.

| Response directive | Ý nghĩa đúng | Có thích hợp cho dữ liệu rất nhạy cảm? |
| --- | --- | --- |
| `no-store` | Cache tuân thủ chuẩn **không được lưu** response hoặc dùng nó để phục vụ request khác | **Có**, thường là chỉ thị cốt lõi |
| `no-cache` | Cache **có thể lưu**, nhưng phải revalidate với origin trước khi sử dụng lại | **Một mình: không đủ** nếu muốn tránh lưu trữ |
| `private` | Shared cache **không được lưu**; private cache (ví dụ browser) vẫn có thể lưu | **Một mình: không đủ** cho bí mật trên thiết bị dùng chung |
| `public` | Cho phép response được lưu trong shared cache nếu các điều kiện khác thỏa | **Không** dùng với nội dung riêng từng người |
| `max-age=0` | Response gần như lập tức stale; cache vẫn có thể lưu và revalidate | **Không** thay `no-store` |
| `max-age=3600` | Freshness lifetime tối đa 3600 giây theo semantics HTTP | Dành cho nội dung phù hợp để cache |
| `s-maxage` | Freshness lifetime dành cho **shared caches**, có thể thay thế giới hạn khác ở đó | Không cấp cho tài nguyên nhạy cảm trừ khi đã được thiết kế riêng |
| `must-revalidate` | Khi đã stale, cache phải xác thực lại trước khi tái sử dụng, không phục vụ stale tùy tiện | Chỉ là bổ trợ, không cấm lưu |
| `immutable` | Gợi ý nội dung sẽ không đổi trong thời gian freshness | Chỉ dành cho asset thật sự được version/fingerprint |
| `no-transform` | Yêu cầu intermediary không biến đổi representation | Không thay no-store/no-cache |

### 3.1. no-store — “không lưu”

Ví dụ cho trang tài khoản hoặc API dữ liệu riêng tư:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"account":"DEMO-001","balance":100}
~~~

Theo RFC 9111, `no-store` response yêu cầu cache tuân thủ chuẩn **không lưu bất kỳ phần nào của immediate request/response** và không dùng response đó để phục vụ một request khác. Nó áp dụng với cache private và shared.

Tuy nhiên, RFC cũng lưu ý `no-store` **không phải một đảm bảo tuyệt đối về bí mật**: cache độc hại hoặc lỗi có thể phớt lờ chỉ thị; đường truyền vẫn cần TLS; dữ liệu có thể đã ở memory của ứng dụng hoặc screenshot. Đây là biện pháp quan trọng, nhưng không thể thay đầy đủ privacy/security controls.

### 3.2. no-cache — “có thể lưu nhưng phải xác thực lại”

Tên `no-cache` gây hiểu nhầm. Ví dụ:

~~~http
Cache-Control: no-cache
ETag: "version-7"
~~~

Cache có thể lưu response. Trước khi dùng lại, nó cần gửi conditional request và được server xác nhận hợp lệ (ví dụ HTTP 304). Nếu không muốn bản sao dữ liệu nhạy cảm tồn tại trên disk/cache, `no-cache` **không đủ**.

Một lỗi phổ biến:

~~~http
Cache-Control: private, no-cache
~~~

Header này **chưa cấm browser lưu response**. Nó giới hạn shared cache và buộc revalidate, nhưng private cache vẫn có thể giữ bản sao. Khi yêu cầu “không lưu đệm phản hồi chứa dữ liệu nhạy cảm”, thường cần `no-store`.

### 3.3. private — ngăn shared cache, không ngăn browser cache

Ví dụ:

~~~http
Cache-Control: private, max-age=60
~~~

Nó có thể phù hợp cho **dữ liệu cá nhân ít nhạy cảm** khi đội sản phẩm đã chấp nhận browser cache trong 60 giây, đồng thời cấm proxy/CDN dùng cache chung. Nhưng không nên áp dụng cho sao kê, mã OTP, tài liệu mật hoặc hồ sơ chứa dữ liệu cực kỳ nhạy cảm nếu yêu cầu không lưu.

**Từ “private” ở đây không có nghĩa đã mã hóa.** Nó chỉ nói cache nào được phép giữ response.

### 3.4. max-age=0 không phải xóa dữ liệu khỏi cache

~~~http
Cache-Control: max-age=0, must-revalidate
~~~

Một cache có thể lưu response rồi hỏi server trước khi dùng lại. Khi đổi người dùng trên cùng thiết bị, cache có thể tiếp tục có representation lưu trên disk. Đây không phải policy tương đương `no-store`.

Tương tự, `Expires: 0` là legacy directive về freshness; nó không có ngữ nghĩa cấm lưu như `no-store`.

### 3.5. public và tài nguyên tĩnh

Với asset thực sự công khai, URL có version/fingerprint như `/assets/app.84bd2.js`, có thể cho phép:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Khi asset thay đổi, pipeline build phát **URL mới**; không thay nội dung ở cùng URL bất biến. Cách này giảm tải và độ trễ mà không khiến response chứa dữ liệu người dùng bị cache.

Không dùng `public` cho HTML dashboard theo user, JSON hồ sơ, bearer-token response, reset password hoặc file xuất báo cáo cá nhân.

## 4. Bộ header mặc định của Spring Security Reactive

Theo tài liệu Spring Security, khi tính năng security headers được bật theo mặc định, các cache-related response headers thường là:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

**Ý nghĩa từng phần:**
- `no-store`: phần quan trọng nhất cho yêu cầu không lưu response nhạy cảm.
- `no-cache`: yêu cầu revalidate nếu một cache có giữ response trong các tình huống khác.
- `max-age=0` và `must-revalidate`: làm rõ freshness/việc xác thực lại.
- `Pragma: no-cache`: legacy HTTP/1.0 compatibility; không thay thế chuẩn response `Cache-Control`.
- `Expires: 0`: legacy date/freshness indicator; không phải điều kiện chống cache đủ mạnh riêng lẻ.

Trong Spring Security WebFlux, **không cần tự thêm các header này vào từng controller** nếu security chain mặc định đã áp chúng và ứng dụng không ghi đè.

Tuy nhiên, có hai chi tiết quan trọng:

1. **Khi ứng dụng đã đặt Cache-Control riêng**, Spring Security có thể nhường quyền cho cấu hình của ứng dụng. Đây là chủ đích để asset CSS/JS/images có thể được cache. Vì vậy, nếu controller trả `public, max-age=...` trên endpoint nhạy cảm, không nên kỳ vọng security mặc định sẽ luôn sửa sai.
2. **Nếu security chain không áp dụng cho một request**, không thể mặc định kết luận những header đó đã được thêm. Với nhiều `SecurityWebFilterChain`, route nằm ngoài security matcher hoặc security headers bị tắt ở một chain, response có thể khác.

**Cần test headers thực tế** trên những route nhạy cảm thay vì chỉ nhìn code cấu hình một chain.

### 4.1. Mặc định có thể bị ghi đè vì ứng dụng chủ động đặt header

Ví dụ:

~~~java
// ResponseEntity ở controller được phép đặt Cache-Control riêng.
return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofDays(30)).cachePublic())
        .body("public-asset");
~~~

Trong WebFlux, Spring Security không áp chính sách “cấm cache mọi thứ vô điều kiện”. Tài liệu Reactive cho phép **chọn lọc đặt Cache-Control trên ServerHttpResponse** để override giá trị mặc định, đặc biệt cho static assets. Đây là điểm cân bằng giữa bảo mật và hiệu năng.

Hệ quả: **code review cần kiểm tra mọi chỗ setCacheControl/cacheControl/header("Cache-Control",...)**, không chỉ SecurityConfig.

### 4.2. Đừng tắt toàn bộ security headers chỉ vì muốn cache một asset

Anti-pattern:

~~~java
// SAI cho phần lớn ứng dụng: xóa cả nhóm default security headers.
.headers(headers -> headers.disable())
~~~

Nó có thể xóa thêm các lớp bảo vệ khác như content-type options, frame options, HSTS tùy request/config. Nếu chỉ muốn cho cache public asset, hãy đặt Cache-Control riêng cho asset đó.

Cũng không nên tắt cache-header writer toàn cục mà quên tái áp cho mọi endpoint:

~~~java
// API hợp lệ về cú pháp, nhưng có rủi ro nếu áp vô điều kiện.
.headers(headers -> headers
        .cache(cache -> cache.disable()))
~~~

Đoạn này tắt **cache-related default headers của Spring Security**, không tự ngăn mọi cache, cũng không tự thêm một policy thay thế. Trong ứng dụng browser có dữ liệu nhạy cảm, hãy giữ mặc định hoặc bảo đảm một WebFilter/controller policy phù hợp cho toàn bộ route cần bảo vệ.

**Đây là DSL WebFlux:** `ServerHttpSecurity.headers(headers -> headers.cache(...))`. Không dùng `HttpSecurity` hoặc `headers.cacheControl(...)` của Servlet khi code chạy Spring WebFlux.

## 5. Phân loại response theo độ nhạy trước khi quyết định cache policy

Không có một quy tắc phù hợp cho tất cả tài nguyên. Một ma trận ban đầu:

| Loại response | Ví dụ | Chính sách gợi ý | Lý do |
| --- | --- | --- | --- |
| Hồ sơ đang đăng nhập | `GET /api/me` | `no-store` | Có định danh và dữ liệu cá nhân |
| Số dư, sao kê, dữ liệu ngân hàng | `GET /api/statements` | `no-store` | Không để bản sao trên browser/proxy |
| Mã reset password, OTP, token exchange | `POST /api/auth/recover` | `no-store` | Dữ liệu liên quan quyền truy cập |
| Kết quả tìm kiếm nội bộ theo user | `GET /api/search/private` | `no-store` hoặc policy bảo vệ riêng đã đánh giá | Có thể tiết lộ lịch sử, tên tài liệu |
| HTML dashboard theo user | `GET /app/dashboard` | `no-store` | Tránh hiển thị nội dung cũ sau chuyển tài khoản |
| File PDF xuất riêng cho user | `GET /api/export/report.pdf` | `no-store` | Ngăn lưu/serve lại file riêng từ HTTP cache |
| Response lỗi có thông tin cá nhân | `4xx/5xx` | `no-store` | Error body cũng có thể chứa dữ liệu nhạy cảm |
| HTML trang đăng nhập, logout | `GET/POST auth routes` | `no-store` | Tránh lưu thông tin cũ, CSRF token hoặc form state |
| Catalog sản phẩm công khai | `GET /public/catalog` | `public` + `max-age` vừa phải nếu dữ liệu thật sự công khai | Tăng hiệu năng |
| JS/CSS có version/fingerprint | `/assets/app.a1b2c3.js` | `public, max-age=31536000, immutable` khi asset bất biến | Asset public được cache dài |
| Cấu hình public thay đổi thường xuyên | `/public/config.json` | `no-cache` + validators hoặc TTL ngắn | Có thể lưu nhưng cần kiểm tra version |
| API nội bộ chỉ nhận Bearer | Tùy dữ liệu | **Không mặc nhiên được phép cache** | Authorization header không tự giải quyết mọi vấn đề |

Ma trận là điểm khởi đầu để threat modeling, không phải một chuẩn áp dụng không cần xem dữ liệu. Đặc biệt, **“HTTP GET” không đồng nghĩa với “public/cacheable”**; nhiều GET chính là request trả dữ liệu nhạy cảm nhất.

### 5.1. Không chỉ HTTP 200

Một response 401 có thể chứa thông tin challenge. Response 403 có thể lộ tên tài nguyên hoặc quyền bị thiếu nếu error handling không an toàn; 404/409/422 cũng có thể mô tả dữ liệu user. Do đó cache policy cho các HTTP error responses cũng cần được cân nhắc.

Đừng chỉ thêm `no-store` vào những controller trả 200 rồi quên:
- error handler;
- authentication entry point;
- access denied handler;
- endpoint logout và token refresh;
- file download;
- Gateway/CDN-generated error pages.

Spring Security default headers giúp ở security layer, nhưng mọi response thực tế cần được test.

## 6. Một số quy tắc HTTP quan trọng ngoài Cache-Control

### 6.1. Set-Cookie không tự cấm caching

Một suy nghĩ sai là: “Response có `Set-Cookie` thì CDN đương nhiên không cache.” RFC 9111 lưu ý rằng **sự có mặt của Set-Cookie không tự cấm caching**; response có thể được cache và dùng lại nếu các điều kiện khác cho phép.

Do đó, các response gắn session cookie và dữ liệu riêng tư cần policy phù hợp, thường `Cache-Control: no-store`. Không dùng Set-Cookie như một phép thay thế.

### 6.2. Authorization header có những quy tắc riêng cho shared caches

Theo RFC 9111, một shared cache nhìn thấy request có `Authorization` thường bị hạn chế lưu/tái sử dụng response, trừ khi response có một số directive cho phép cache chia sẻ theo chuẩn. Nhưng đừng lấy quy tắc này làm lý do bỏ `no-store` trên endpoint nhạy cảm:
- HTTP client có thể dùng cookie/session thay vì Authorization header.
- Cấu hình CDN/gateway có thể override hoặc không tuân thủ.
- Response có thể được cache ở **private browser cache**.
- Developer có thể vô tình thêm `public` hoặc policy cho shared cache ở một route đã xác thực.
- API token/cookie có thể được truyền theo nhiều phương thức khác nhau qua reverse proxy.

**Phải đặt cache policy theo phân loại dữ liệu**, không suy từ việc request có một loại header xác thực.

### 6.3. Vary không thay no-store

~~~http
Vary: Authorization
Cache-Control: private, max-age=60
~~~

`Vary` khiến cache xem xét giá trị của các request headers được nêu khi chọn cached response theo semantics HTTP; nó không khiến response tự biến thành an toàn để lưu. `Vary: Cookie` cũng không bảo đảm một CDN được cấu hình sai sẽ không chia sẻ dữ liệu.

Đối với dữ liệu tuyệt đối không được lưu, dùng `no-store`. Đối với content public có biến thể theo language/encoding, `Vary` hữu ích nhưng phải xem cache key và kiểm thử thật.

### 6.4. HTTPS không tự động tắt cache

HTTPS bảo vệ tính bí mật và toàn vẹn trên đường truyền phù hợp. Browser vẫn có thể cache HTTPS responses theo HTTP caching rules; CDN có thể kết thúc TLS rồi cache phía edge. Vậy nên:

- `HTTPS` cần cho dữ liệu nhạy cảm.
- `Cache-Control: no-store` cần khi không muốn HTTP caches lưu.
- `Authentication/Authorization` cần để chỉ user có quyền đọc tài nguyên.
- Logout/session invalidation cần để thu hồi quyền trong request tương lai.

Không dùng một cơ chế để thay thế cơ chế khác.

## 7. WebFlux API để gán Cache-Control cho response

Spring Framework cung cấp:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
~~~

Các cách chính:

~~~java
// 1. Không lưu response (bảo vệ nội dung nhạy cảm).
ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(data);

// 2. Chỉ browser/private cache; KHÔNG phù hợp cho bí mật cần no-store.
ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofSeconds(60))
                .cachePrivate())
        .body(nonSensitivePersonalData);

// 3. Asset công khai, được version hóa.
ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofDays(30))
                .cachePublic())
        .body(publicAsset);
~~~

Đây là các **snippet** nằm trong method, chưa phải file Java độc lập; cần import `java.time.Duration` và các biến `data`, `nonSensitivePersonalData`, `publicAsset` tương ứng. Trong sản phẩm, không nên chọn private 60 giây chỉ vì có tên “private” nếu policy thực tế là cấm lưu dữ liệu nhạy cảm.

### 7.1. CacheControl.noStore()

~~~java
CacheControl.noStore()
~~~

Khi gắn với `ResponseEntity.cacheControl`, nó tạo giá trị cache directive tương đương:

~~~http
Cache-Control: no-store
~~~

Spring Security có thể nhường policy cache mặc định cho header ứng dụng chủ động đặt; đây là điều bình thường. Nếu chọn `noStore()` một cách tường minh, vẫn đáp ứng mục tiêu cấm HTTP cache lưu response theo chuẩn.

### 7.2. ResponseEntity trong reactive handler

Spring WebFlux cho phép handler trả:

~~~java
Mono<ResponseEntity<MyDto>>
~~~

Nghĩa là HTTP status, headers và body cùng được quyết định theo bất đồng bộ. Nếu dữ liệu được lấy từ reactive repository:

~~~java
// Snippet thuộc controller/service, thiếu repository và model class.
return repository.findById(id)
        .map(dto -> ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(dto))
        .switchIfEmpty(Mono.just(ResponseEntity.notFound().build()));
~~~

Đây chỉ là ví dụ cách compose `Mono`. Kiểu generic của hai nhánh cần được compiler suy ra thống nhất trong class thực; nếu viết một hệ thống đầy đủ cần định nghĩa DTO, repository, lỗi 404 và chính sách response lỗi riêng.

**Không dùng `block()`** trong WebFlux controller chỉ để thêm header. Compose publisher và để Spring subscribe theo lifecycle request.

### 7.3. Gán header qua ServerHttpResponse

Đối với `ServerWebExchange` hoặc functional handlers:

~~~java
// Snippet minh họa trong handler/filter.
exchange.getResponse().getHeaders()
        .setCacheControl(CacheControl.noStore());
~~~

Nếu một thành phần khác ghi đè `Cache-Control` sau đó, giá trị cuối cùng trên response thực tế có thể khác. Đó là lý do test từ HTTP boundary quan trọng hơn chỉ kiểm tra đã gọi một method.

Đừng tự ghi hai header `Cache-Control` mâu thuẫn (ví dụ `public, max-age=3600` rồi thêm `no-store` ở một nơi khác). Chính sách cần rõ nơi chịu trách nhiệm và thứ tự cuối cùng.

## 8. Dự án Java 17+ runnable: mặc định an toàn, override asset public

Demo dùng **Java 17, Spring Boot 3.5.7, Spring WebFlux và Spring Security Reactive 6.x**. Để tập trung vào Cache-Control, chúng ta dùng HTTP Basic user in-memory; tài khoản/mật khẩu là dữ liệu giả **chỉ dành cho localhost**. Không dùng `{noop}` hoặc Basic qua HTTP ở production.

Dự án thể hiện bốn loại response:

1. `GET /public/ping`: public, controller **không đặt Cache-Control** → Spring Security default headers vẫn bảo vệ.
2. `GET /api/profile/default`: có authentication, controller **không đặt Cache-Control** → mặc định Spring Security `no-store`.
3. `GET /api/profile/explicit`: có authentication, controller đặt tường minh `CacheControl.noStore()`.
4. `GET /assets/app.v1.js`: nội dung asset demo công khai, controller đặt `public, max-age=30 ngày`, override mặc định cho đúng route.
5. `GET /api/admin/statement`: chỉ ADMIN, response nhạy cảm được đặt `no-store`; reader không đủ quyền bị từ chối.

Đây là **mô phỏng asset trong controller**, không phải resource handler production. Phần sau trình bày cấu hình thực tế cho static resources fingerprinted.

### 8.1. Cấu trúc thư mục

~~~text
webflux-cache-control/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── CacheDemoController.java
    └── test/java/demo/
        └── CacheControlSecurityTest.java
~~~

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-cache-control'
~~~

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Bạn cần JDK 17+ và Gradle tương thích hoặc Gradle Wrapper của dự án. Spring Boot dependency management cung cấp bộ version Spring Framework/Security phù hợp với phiên bản Boot đã chọn. Trong sản phẩm thật cần dùng nhánh có hỗ trợ và bản vá bảo mật mới theo quy trình tổ chức.

### 8.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.5. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/assets/app.v1.js")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/admin/statement")
                                .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET,
                                "/api/profile/default",
                                "/api/profile/explicit")
                                .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}readerpass")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Các quyết định có chủ đích:**

- Spring Security vẫn quản lý **default security headers**. Chúng ta **không** gọi `headers.disable()` hoặc `headers.cache(cache -> cache.disable())`.
- Các route public có thể nhận default no-store nếu controller không đặt header riêng. `permitAll` chỉ là authorization policy; nó không biến một route thành cacheable.
- Route asset có `permitAll` nhưng còn phải được controller chỉ định cache policy public thì browser/CDN mới có cơ sở cache.
- `/api/profile/...` yêu cầu authentication, `/api/admin/statement` yêu cầu ADMIN.
- `anyExchange().denyAll()` không mở quyền những endpoint được thêm sau này.
- Không có session login/form login trong demo; dùng Basic để test 401/403 dễ hơn.
- `{noop}` là password chưa hash, không được dùng trong production. HTTP Basic phải đi qua HTTPS; Base64 chỉ là encoding.

**Không đặt Cache-Control ở SecurityConfig theo cách vô hiệu tất cả mặc định để chạy nhanh hơn.** Mục tiêu demo là cho phép từng route công khai override chính sách mà vẫn giữ các default headers khác.

### 8.6. CacheDemoController.java

`src/main/java/demo/CacheDemoController.java`:

~~~java
package demo;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class CacheDemoController {

    public record Profile(String accountId, String displayName) {
    }

    @GetMapping(path = "/public/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPing() {
        return Mono.just("pong");
    }

    @GetMapping("/api/profile/default")
    public Mono<Profile> defaultProfile() {
        return Mono.just(new Profile("DEMO-001", "Example Reader"));
    }

    @GetMapping("/api/profile/explicit")
    public Mono<ResponseEntity<Profile>> explicitProfile() {
        Profile payload = new Profile("DEMO-001", "Example Reader");
        return Mono.just(ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(payload));
    }

    @GetMapping(path = "/api/admin/statement",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> statement() {
        return Mono.just(ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body("DEMO-SENSITIVE-STATEMENT"));
    }

    @GetMapping(path = "/assets/app.v1.js",
            produces = "application/javascript")
    public Mono<ResponseEntity<String>> publicAsset() {
        return Mono.just(ResponseEntity.ok()
                .cacheControl(CacheControl
                        .maxAge(Duration.ofDays(30))
                        .cachePublic())
                .body("console.log('static-demo-v1');"));
    }
}
~~~

Đặc điểm đáng chú ý:
- `Mono<Profile>` ở route default không thêm header thủ công; Spring Security WebFilter có thể đặt default cache headers khi response được commit.
- `Mono<ResponseEntity<Profile>>` ở route explicit cho phép WebFlux quyết định body và headers trong reactive flow. `CacheControl.noStore()` là một policy rõ ràng ở controller.
- `statement` giữ `no-store` cho nội dung nhạy cảm kể cả khi API phát triển thành file xuất báo cáo thật.
- `publicAsset` đặt `public, max-age=2592000` (30 ngày). Chuỗi JS là **hằng công khai**, không chứa dữ liệu cá nhân và URL có version v1. Khi thay nội dung trong demo, nên đổi URL version để tránh cache cũ.
- Không có `block()` hay `subscribe()` thủ công.
- Đây chỉ là dữ liệu giả, không phải một ví dụ kiểm soát quyền sở hữu đối tượng/tenant. Production cần authorization theo tài nguyên ở service.

**Quan trọng:** cấu hình 30 ngày public là an toàn **chỉ vì asset này không chứa thông tin riêng tư**. Một HTML template sau khi render tên/email của user, hoặc một file JS được tạo động với token/secret, **không còn là asset public** dù đường dẫn bắt đầu bằng `/assets/`.

## 9. Chạy ví dụ với curl

Trong thư mục có `build.gradle`:

~~~bash
gradle bootRun
~~~

Nếu dự án có Wrapper, dùng `./gradlew bootRun` trên macOS/Linux hoặc `gradlew.bat bootRun` trên Windows. Server mặc định lắng nghe `http://localhost:8080`. Demo HTTP chỉ dùng trên máy cá nhân; không mở API demo lên Internet.

### 9.1. Public route nhưng vẫn có cache security default

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kết quả kỳ vọng:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
Content-Type: text/plain;charset=UTF-8

pong
~~~

Header order/case và chi tiết charset có thể khác tùy Netty/Spring version. Điểm cần so sánh là `Cache-Control` chứa `no-store` chứ không phải nguyên chuỗi response từng ký tự.

**Tại sao public route lại no-store?** Bởi `permitAll` không có nghĩa cần cache. Spring Security thêm mặc định an toàn khi ứng dụng không đặt một policy cụ thể.

### 9.2. Protected route, không credentials

~~~bash
curl -i http://localhost:8080/api/profile/default
~~~

Kỳ vọng **401 Unauthorized**, thường có `WWW-Authenticate: Basic ...`. Response lỗi này cũng nên có policy cache an toàn. Đừng dùng `curl -I` làm thay thế trực tiếp: nó gửi HEAD, trong khi security rules của demo chỉ liệt kê GET, nên HEAD có thể bị deny bởi policy riêng.

### 9.3. Protected route với Basic đúng, dùng mặc định

~~~bash
curl -i -u reader:readerpass \
  http://localhost:8080/api/profile/default
~~~

Kỳ vọng **200 OK**, body:

~~~json
{"accountId":"DEMO-001","displayName":"Example Reader"}
~~~

và `Cache-Control` chứa `no-store` dù controller không thêm. Đây là tác dụng của Spring Security default response headers.

### 9.4. Protected route với no-store explicit

~~~bash
curl -i -u reader:readerpass \
  http://localhost:8080/api/profile/explicit
~~~

Kỳ vọng `200 OK`, body profile như trên và:

~~~http
Cache-Control: no-store
~~~

**Không yêu cầu `Pragma: no-cache` và `Expires: 0` nhất định phải xuất hiện ở route này**, vì controller đã đặt Cache-Control riêng và Spring Security có thể không thêm bộ mặc định ở trường hợp đó.

### 9.5. Asset public được cache chọn lọc

~~~bash
curl -i http://localhost:8080/assets/app.v1.js
~~~

Kỳ vọng `200 OK`, body:

~~~javascript
console.log('static-demo-v1');
~~~

và header có `max-age=2592000` cùng `public`, ví dụ:

~~~http
Cache-Control: max-age=2592000, public
~~~

Đây là kết quả có chủ đích: khi asset public thực sự versioned, caching giúp giảm tải. Không disable headers của toàn ứng dụng.

### 9.6. Endpoint chỉ dành cho ADMIN

~~~bash
# Reader đã xác thực nhưng không có ROLE_ADMIN:
curl -i -u reader:readerpass \
  http://localhost:8080/api/admin/statement

# Admin có quyền:
curl -i -u admin:adminpass \
  http://localhost:8080/api/admin/statement
~~~

Kỳ vọng:
- Reader: **403 Forbidden**.
- Admin: **200 OK**, body `DEMO-SENSITIVE-STATEMENT`, `Cache-Control: no-store`.

Authorization vẫn bắt buộc dù response đã có Cache-Control tốt. `no-store` không ngăn người không có quyền gọi API; nó chỉ hướng dẫn cache không lưu response.

### 9.7. Quan sát response headers qua proxy/CDN

Nếu ứng dụng chạy sau reverse proxy/CDN, lệnh curl nên được gọi **qua public hostname** để quan sát chính xác headers sau mọi lớp trung gian. Header từ localhost/Netty không chứng minh CDN không thêm/chỉnh `Cache-Control`.

Khi kiểm tra phải ghi nhận:
- URL/method/status;
- `Cache-Control`;
- `Age` nếu có;
- `Vary`;
- các header riêng CDN như `X-Cache`/`CF-Cache-Status` nếu hệ thống dùng;
- hai lần gọi của hai tài khoản khác nhau;
- request không credentials.

Chú ý một CDN có thể cache dựa trên rule riêng ngoài HTTP headers; đó là bài toán cấu hình hạ tầng và policy bypass cache.

## 10. Kiểm thử bằng WebTestClient

Spring Security Test có cấu hình `springSecurity()` cho `WebTestClient` khi bind ApplicationContext. Kiểm tra cả **status** và **cache headers**; đây mới là regression test đúng với mục tiêu bảo mật.

`src/test/java/demo/CacheControlSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CacheControlSecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicEndpointStillHasSecureCacheDefault() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void protectedEndpointWithoutCredentialsIs401() {
        client.get().uri("/api/profile/default")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueMatches(
                        HttpHeaders.WWW_AUTHENTICATE, "Basic.*");
    }

    @Test
    void protectedProfileHasNoStoreByDefault() {
        client.get().uri("/api/profile/default")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
                .expectBody()
                .jsonPath("$.accountId").isEqualTo("DEMO-001");
    }

    @Test
    void explicitNoStoreOverridesDefaultSafely() {
        client.get().uri("/api/profile/explicit")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
                .expectBody()
                .jsonPath("$.displayName").isEqualTo("Example Reader");
    }

    @Test
    void versionedPublicAssetCanBeCached() {
        client.get().uri("/assets/app.v1.js")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*max-age=2592000.*")
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*public.*")
                .expectBody(String.class)
                .isEqualTo("console.log('static-demo-v1');");
    }

    @Test
    void readerCannotReadAdminStatement() {
        client.get().uri("/api/admin/statement")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminStatementMustNotBeStored() {
        client.get().uri("/api/admin/statement")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
                .expectBody(String.class)
                .isEqualTo("DEMO-SENSITIVE-STATEMENT");
    }

    @Test
    void invalidPasswordIsRejected() {
        client.get().uri("/api/profile/default")
                .headers(h -> h.setBasicAuth("reader", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Kỳ vọng **8 bài test** PASS khi các files/dependencies được tạo đúng như mô tả. Đây là dự đoán theo mã và tài liệu API, **không phải khẳng định bài đã được build/test thực tế**.

Một vài lưu ý:
- Các test default dùng `.valueMatches(..., ".*no-store.*")` thay vì so sánh chính xác toàn chuỗi header, vì thứ tự các directives có thể thay đổi.
- Test asset dùng giá trị Max-Age cụ thể của 30 ngày (**2.592.000 giây**).
- Test protected profile chứng minh cache policy **và** việc authentication đang hoạt động.
- Test reader bị 403 không chứng minh toàn bộ nội dung lỗi 403 đã có no-store; nếu error handler/proxy được tùy biến, bổ sung test tương ứng.
- Các test bằng `WebTestClient` không mô phỏng đầy đủ browser disk cache, BFCache, service workers hoặc CDN; cần integration/E2E test tại public endpoint.

### 10.1. Tại sao test chỉ trên GET?

GET là phương thức thường được HTTP caches xem xét. Nhưng **các response POST có chứa dữ liệu nhạy cảm vẫn cần header phù hợp**, dù tính cacheability khác GET và tùy HTTP semantics. Bài demo tối giản để phân biệt policy; sản phẩm nên kiểm tra luôn auth/reset token endpoints, file downloads và responses của các unsafe methods.

### 10.2. Khi API có lỗi 401 hoặc 403

Kiểm tra đúng nơi response được tạo:
- 401 có thể do Spring Security authentication entry point.
- 403 có thể do authorization hoặc CSRF.
- 404/409/422 có thể do WebFlux/controller advice.
- 5xx có thể do server hoặc gateway.

Đối với các response đó, phải giữ policy riêng nếu body hoặc bối cảnh có dữ liệu nhạy cảm. Một controller annotation không chắc chạy khi SecurityWebFilter từ chối trước controller, nên kiểm thử từ HTTP boundary.

## 11. Cấu hình static resources production thay vì controller demo

Trong ứng dụng thật, JS/CSS/images thường là resources tại `classpath:/static/assets/`, do WebFlux resource handler phục vụ. Ví dụ **thay thế** cho controller asset của demo, không thêm đồng thời cho cùng path:

~~~java
package demo;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class StaticAssetsConfig implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(CacheControl
                        .maxAge(Duration.ofDays(365))
                        .cachePublic());
    }
}
~~~

Đây là class hợp lệ khi có các resources thật và cùng dependency WebFlux; không phải một file cần thêm vào demo hiện tại vì route `/assets/app.v1.js` đang được controller minh họa.

**Lưu ý:**
- Trong Spring Boot WebFlux, implement `WebFluxConfigurer` thường không cần `@EnableWebFlux`; tự thêm `@EnableWebFlux` có thể thay đổi hoặc vô hiệu một số Spring Boot auto-configuration mặc định.
- Giới hạn path `/assets/**` chỉ cho nội dung công khai; không đặt template chứa dữ liệu user, file upload riêng tư hoặc JSON chứa token vào cùng thư mục.
- Với cache 365 ngày, nên dùng filenames có hash nội dung và quy trình build đổi tên khi asset thay đổi. Nếu dùng URL ổn định nhưng nội dung có thể sửa, khách hàng có thể nhận asset cũ lâu.
- Có thể dùng `ETag`/`Last-Modified` cho static resources theo WebFlux caching support, nhưng chỉ nếu việc tái sử dụng response được phép.
- Spring Security vẫn cần cho phép route asset qua authorization. Nếu `anyExchange().denyAll()` mà không có rule cho `GET /assets/**`, request có thể bị từ chối trước resource handler.

### 11.1. Một asset “có tên .js” không mặc nhiên công khai

Không cache public một script tạo động dạng:

~~~javascript
window.currentUser = {
  email: "alice@example.test",
  token: "secret-value"
};
~~~

Đây là ví dụ **KHÔNG AN TOÀN** minh họa leak; không nhúng dữ liệu người dùng hoặc token vào asset tĩnh có thể bị CDN cache. Hãy tách dữ liệu user vào API được bảo vệ và trả `no-store`.

### 11.2. ETag và Last-Modified dùng ở đâu?

Với tài nguyên công khai cho phép caching, `ETag` hoặc `Last-Modified` hỗ trợ conditional requests để trả `304 Not Modified` khi representation chưa đổi. Điều này giảm bandwidth mà vẫn giữ freshness policy.

Với nội dung nhạy cảm yêu cầu `no-store`, không thiết kế một quy trình “cache trong browser rồi gửi If-None-Match để tái sử dụng” làm cách mặc định; điều đó đi ngược mục tiêu tránh lưu bản sao. Nếu nghiệp vụ có lý do hợp lệ để sử dụng private caching cho một số dữ liệu, cần security review cho cache key, user binding, revalidation, logout và nhiều tài khoản.

## 12. CDN/reverse proxy: không chỉ nhìn header trong controller

Ứng dụng đi qua hạ tầng:

~~~text
Browser
   |
   v HTTPS
CDN / Edge Cache
   |
   v HTTPS (hoặc trusted internal hop)
API Gateway / Reverse Proxy
   |
   v
Spring WebFlux + Spring Security
~~~

Một số CDN có rule **bypass origin Cache-Control**, “cache everything”, override TTL hoặc cache theo path mà không phân biệt cookie/Authorization. Trong tình huống đó, một response đã đặt `no-store` ở backend **vẫn có nguy cơ bị xử lý sai** ở edge.

### 12.1. Chính sách vận hành cần kiểm tra

- Các route `/api/me`, `/api/account/**`, `/api/admin/**`, `/api/auth/**` phải có policy bypass CDN cache nếu chứa dữ liệu nhạy cảm.
- Nếu CDN/cache key sử dụng Host, path, query, Authorization/cookie, phải audit rằng không có dữ liệu user A được phục vụ cho user B.
- Đừng chỉ dựa vào `Vary: Cookie`; kiểm tra cả rules của CDN.
- Kiểm tra cookie/session và token endpoints riêng; `Set-Cookie` không tự cấm caching.
- Xem reverse proxy có thêm `Cache-Control: public` hay ghi đè `no-store` không.
- Với proxies có header điều khiển riêng như `Surrogate-Control`, chỉ sử dụng theo tài liệu của nhà cung cấp và policy đã được review; header này không thay `Cache-Control` chuẩn trong browser.
- Phản hồi do gateway tự tạo (401/403/5xx) có thể không đi qua Spring Security; phải bảo vệ chúng nếu có thông tin nhạy cảm.
- Khi dữ liệu nhạy cảm đã bị cache ngoài ý muốn, **chỉnh header sau đó không tự xóa bản sao trước đây**; cần purge/invalidate CDN và xử lý sự cố phù hợp.

### 12.2. Kiểm tra lặp giữa hai người dùng

Một ca security QA mạnh:

1. User A đăng nhập và gọi `GET /api/me` qua public hostname.
2. Kiểm tra response A có `no-store` và không có dấu hiệu CDN HIT.
3. User B dùng một phiên/credentials khác gọi **chính URL**.
4. Xác nhận B chỉ thấy dữ liệu của B, không thấy cached response của A.
5. User không đăng nhập gọi URL — nhận 401/redirect đúng policy, không thấy body của A/B.
6. Đăng xuất A, thử lại các URL, kiểm tra không có representation A được dùng lại.
7. Lặp lại qua mobile browser, browser shared device và các vùng edge cần thiết.

Không nên thực hiện kiểm thử này bằng dữ liệu thật của người dùng: sử dụng tài khoản test và dữ liệu tổng hợp, theo quy trình an toàn.

### 12.3. Thời hạn CDN khác browser max-age

Có thể có các directive `s-maxage` cho shared caches và `max-age` cho cache thông thường. Một policy `public, s-maxage=600` phù hợp với catalog công khai **không phù hợp** với profile riêng tư. Đừng “tối ưu CDN cache” trên một endpoint có authorization chỉ bằng việc tăng TTL.

## 13. Logout, nút Back và giới hạn của no-store

Kịch bản phổ biến: người dùng mở trang hồ sơ, đăng xuất, rồi nhấn Back. Một số UI có thể hiển thị dữ liệu cũ từ bộ nhớ hoặc trạng thái trình duyệt nếu ứng dụng không làm sạch.

`Cache-Control: no-store` trên những response chứa dữ liệu nhạy cảm là một biện pháp quan trọng nhưng có giới hạn:

- Browser có thể vẫn giữ **trạng thái render hoặc SPA component state** trong memory trong một số tình huống.
- Các browser hiện đại có thể thay đổi chính sách sử dụng BFCache đối với trang `no-store`; phải kiểm thử trên phiên bản browser được hỗ trợ.
- Dữ liệu do frontend tự ghi vào localStorage, IndexedDB hoặc Cache API không tự xóa khi server trả `no-store`.
- Một tab đang mở vẫn có thể có dữ liệu đã được tải trước logout, vì header không “điều khiển” bộ nhớ hiện tại của ứng dụng.
- Screenshot, dữ liệu copy ra clipboard, dữ liệu đã tải về và logs không thể được thu hồi bằng Cache-Control.

Một quy trình logout an toàn hơn:
1. Thực hiện server-side logout/session invalidation/token revocation phù hợp.
2. Đặt `no-store` trên các response riêng tư (bao gồm HTML chứa dữ liệu cá nhân).
3. Xóa dữ liệu nhạy cảm trong client state khi logout, chuyển tài khoản hoặc token hết hạn.
4. Tránh lưu raw tokens trong localStorage nếu threat model không cho phép; thực hiện chiến lược auth đã được đánh giá.
5. Trên navigation/back, nếu cần, **revalidate authentication** và không dựng lại view riêng tư từ persisted state.
6. Kiểm thử thực tế với Back/Forward, tab cũ, reload, network offline và multi-account scenarios.
7. Không coi việc bấm Back không hiển thị dữ liệu trong một browser là bảo đảm trên tất cả browser.

### 13.1. Clear-Site-Data có vai trò gì?

Một số browser hỗ trợ response header `Clear-Site-Data`, ví dụ:

~~~http
Clear-Site-Data: "cache"
~~~

Spring Security Reactive có hỗ trợ cấu hình header này trong một số logout flows thông qua `ClearSiteDataServerHttpHeadersWriter`. Đây là **công cụ bổ sung** để yêu cầu browser xóa những loại dữ liệu theo phạm vi/chính sách hỗ trợ, nhưng:

- Mức hỗ trợ và hành vi khác nhau giữa browser.
- Phạm vi/xóa cookies/cache/storage phải được chọn cẩn thận, tránh làm hỏng dữ liệu hợp lệ của ứng dụng khác cùng origin.
- Header này không đảm bảo xóa dữ liệu trên CDN, một client độc hại hoặc các bản sao trước đây.
- Nó không thay `Cache-Control: no-store` trên response nhạy cảm khi đang trả dữ liệu.

Không thêm `Clear-Site-Data` một cách vô điều kiện cho mọi response; nó thường dành cho các luồng như logout đã được thiết kế rõ.

### 13.2. Browser fetch cache mode khác HTTP response cache policy

Frontend có thể viết:

~~~javascript
const response = await fetch("/api/me", {
  cache: "no-store",
  credentials: "same-origin"
});
~~~

Đây là **request-side fetch cache mode** của browser, không phải một chính sách response bắt buộc cho mọi client/proxy. Hãy **vẫn** trả `Cache-Control: no-store` từ server. Một script khác hoặc HTTP client không dùng fetch option trên vẫn phải nhận đúng policy khi gọi API.

## 14. Khi nào private/no-cache thực sự là lựa chọn hợp lý?

Không phải mọi response cá nhân đều có yêu cầu cấm lưu tuyệt đối; đôi khi tổ chức chấp nhận browser cache ngắn để cải thiện trải nghiệm.

Ví dụ một trang tùy chọn giao diện ít nhạy cảm:

~~~http
Cache-Control: private, max-age=60
Vary: Accept-Language
~~~

Nó cho phép private cache lưu tối đa 60 giây, không cho shared cache lưu, với điều kiện policy đã đánh giá việc lộ dữ liệu trên thiết bị dùng chung. Nếu người dùng đổi tài khoản trong 60 giây, UI phải tránh sử dụng nhầm dữ liệu cũ; app cần xóa cache liên quan và bind dữ liệu vào session/user.

Đối với một tài nguyên public cần cập nhật thường xuyên:

~~~http
Cache-Control: no-cache
ETag: "catalog-v12"
~~~

Browser được phép lưu representation nhưng phải revalidate trước khi dùng. Đây là tối ưu tốt cho nội dung công khai, **không nên sao chép cho password reset/token/statement**.

### 14.1. Các điểm cân nhắc khi review “private cache”

Đội security/product nên trả lời:
- Nội dung có chứa PII hoặc thông tin đủ để suy ra hoạt động người dùng không?
- Thiết bị/browser có thể dùng chung hoặc kiosk không?
- Có yêu cầu pháp lý/nội bộ không được lưu cục bộ không?
- Client có nhiều tài khoản đăng nhập luân phiên không?
- Cached representation có thể được phục vụ sai user sau login/logout không?
- Response có `Set-Cookie`, token, URL ký, metadata nhạy cảm không?
- CDN/edge có chứng minh không lưu đúng policy không?
- Có ETag/304 khiến response riêng tư được tái sử dụng ngoài ý muốn không?

Nếu không trả lời được, **ưu tiên `no-store` cho dữ liệu nhạy cảm** thay vì thử private caching chỉ vì tối ưu hiệu năng.

## 15. Những lỗi phổ biến khi cấu hình Cache-Control trong WebFlux

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `no-cache` cấm lưu response | Browser vẫn có thể lưu bản sao rồi revalidate | Dùng `no-store` khi không muốn lưu |
| Nghĩ `private` nghĩa “đã bảo mật tuyệt đối” | Browser/private cache vẫn có thể lưu | Dùng `no-store` cho bí mật |
| `max-age=0` được xem như no-store | Cache có thể giữ representation stale | Phân biệt freshness với storage |
| Dùng `public, max-age` trên `/api/me` | Có nguy cơ chia sẻ dữ liệu cá nhân qua cache | Chỉ public-cache nội dung thật sự public |
| Nghĩ `Set-Cookie` tự chặn CDN cache | RFC không bảo đảm điều đó | Gửi policy Cache-Control rõ ràng |
| Nghĩ có `Authorization` là đủ bảo vệ mọi cache | Cookie auth, browser cache và CDN rules có khác biệt | Đánh giá theo độ nhạy dữ liệu |
| Tắt `headers.disable()` để cache CSS | Mất các security headers khác | Override trên asset cụ thể |
| Tắt `headers.cache(cache -> cache.disable())` toàn app | Dữ liệu nhạy cảm không còn default no-store | Giữ default hoặc thay bằng policy hoàn chỉnh |
| Nhầm `HttpSecurity` với `ServerHttpSecurity` | Áp dụng cấu hình Servlet sai vào WebFlux | Dùng API Reactive |
| Chỉ dùng `@Cacheable` backend | Browser/CDN vẫn có thể cache HTTP response | Trả HTTP Cache-Control riêng |
| Chỉ nhìn `curl 200`, không nhìn header | Không biết response có được cache không | Kiểm tra `Cache-Control` trong test |
| Dùng `curl -I` rồi so status với GET | HEAD có thể bị matcher riêng từ chối | Kiểm thử đúng HTTP method |
| Cho cache file JS chứa token/user data | Phơi bày bí mật qua CDN/browser | Tách static assets khỏi dữ liệu nhạy cảm |
| Đặt TTL 365 ngày cho asset URL không versioned | Browser dùng file cũ khi deploy | Dùng fingerprint filenames |
| Dùng `Vary: Cookie` như lớp bảo mật duy nhất | Shared cache có thể cấu hình sai | No-store + edge bypass policy |
| Tin `Cache-Control` sẽ xóa localStorage | Không tác động lưu trữ do JS quản lý | Xóa client state theo auth lifecycle |
| Không xử lý BFCache/back button | UI có thể hiện dữ liệu cũ sau logout | Kiểm thử browser và làm sạch state |
| Quên error responses/file downloads | Dữ liệu nhạy cảm ở 4xx/5xx/PDF vẫn bị cache | Áp policy ở mọi tầng có dữ liệu |
| Tin HTTPS đồng nghĩa no-cache | HTTPS response vẫn có thể được cache | TLS và Cache-Control là hai lớp riêng |
| Chỉ kiểm thử localhost, không qua CDN | Edge có thể thêm/bỏ header | Test public hostname và cache rules |

## 16. Troubleshooting: vì sao vẫn có dữ liệu sau logout?

Khi người dùng báo “đăng xuất rồi bấm Back vẫn thấy trang cũ”, lần lượt kiểm tra:

1. **Response thật có `Cache-Control` gì?** Có `no-store` trên HTML hoặc JSON chứa dữ liệu nhạy cảm không?
2. **Spring Security chain bao phủ route chưa?** Có matcher nhiều chain hoặc resource được xử lý ngoài security chain không?
3. **Có controller/handler khác set `Cache-Control: private/public` không?** Spring Security có thể nhường nếu app đã ghi header.
4. **Trang HTML là public shell hay đã chứa dữ liệu user?** Shell tĩnh có thể cache, nhưng response cá nhân không nên.
5. **Dữ liệu đến từ HTTP cache hay SPA memory/localStorage/IndexedDB?** Xem DevTools Application/Network.
6. **BFCache được browser hỗ trợ thế nào?** Thử nút Back/Forward trên các browser và phiên bản đang hỗ trợ.
7. **Logout có invalidate/revoke server session/token chưa?** Header cache không thay đổi quyền truy cập.
8. **CDN có cache HIT?** Kiểm tra request qua public URL và tài khoản test khác.
9. **Có service worker đang trả cached response không?** Audit Cache API và fetch handler.
10. **Có `ETag`/`Last-Modified`/304 cho dữ liệu riêng không?** Nếu policy là no-store, xem lại thiết kế conditional caching.
11. **Có proxy/WAF/gateway ghi đè Cache-Control không?** Quan sát cả origin lẫn edge.
12. **Ứng dụng có phát response 401/403 trước controller không?** Test default security headers ở entry point/denied handler.
13. **Mã nguồn frontend có tự lưu response vào state có persistence không?** Dọn khi logout/switch account.
14. **Có response chứa Set-Cookie và dữ liệu cá nhân nhưng thiếu no-store?** Sửa theo RFC 9111.
15. **Một bản cache cũ đã tồn tại trước khi sửa?** Có thể cần purge CDN và xử lý client theo incident policy.
16. **Response có `Age`/`Via`/vendor cache headers không?** Dùng để xác định tầng đã lưu.

### 16.1. Lưu log an toàn khi debug cache

Có thể ghi method, route template, status, cache directive và correlation ID. Không ghi nguyên response body chứa PII, Authorization header, Cookie/Set-Cookie values, session ID, access token hoặc OTP. Khi dùng log để tìm lỗi cache, mục tiêu là xác định **policy và cache hit/miss**, không tạo thêm một bản sao nhạy cảm trong log.

### 16.2. Đừng “fix” bằng cách tắt cache của toàn bộ hệ thống

Nếu CSS/JS load chậm vì default no-store, cách sửa phù hợp là:
1. Xác định chính xác namespace tài nguyên public.
2. Version/fingerprint tên file.
3. Cấu hình `Cache-Control: public, max-age=...` **chỉ** cho namespace đó.
4. Giữ `no-store` cho API/user-specific HTML.
5. Kiểm thử regression cho cả hai nhóm.

Không cần tắt tất cả security headers để phục vụ một mục tiêu performance.

## 17. Checklist thiết kế cache policy

### 17.1. API chứa dữ liệu nhạy cảm
- [ ] Các route riêng tư có `Cache-Control: no-store` ở public HTTP boundary.
- [ ] Response 401/403 và domain errors chứa dữ liệu nhạy cảm không bị cache sai.
- [ ] Tài liệu PDF/CSV/attachment riêng tư có chính sách no-store khi cần.
- [ ] Không có `public` hoặc shared-cache `s-maxage` ngoài ý muốn trên private routes.
- [ ] Response có `Set-Cookie` không dựa vào cookie header để cấm cache.
- [ ] GET, HEAD, POST, logout, login, refresh, reset token đã được đánh giá.
- [ ] Security chain áp đúng route; headers writer không bị disable ngoài ý muốn.
- [ ] Không có application code ghi đè default no-store bằng một policy rộng hơn.
- [ ] Authorization của object/tenant được kiểm tra riêng; no-store không thay quyền truy cập.

### 17.2. Static/public assets
- [ ] Asset thực sự công khai và không chứa profile/token/secret.
- [ ] Tên file có version/hash nếu dùng TTL dài.
- [ ] `Cache-Control` chỉ cho phép public cache trên nhóm asset đã phê duyệt.
- [ ] ETag/Last-Modified/304 được dùng phù hợp với resource.
- [ ] Không có URL ổn định bị gán `immutable` khi nội dung thường đổi.
- [ ] WebFlux resource handler và Spring Security authorization rules tương thích.

### 17.3. Browser, CDN và vận hành
- [ ] Public hostname và origin backend trả response headers nhất quán.
- [ ] CDN bypass cache cho route account/auth/private, không chỉ dựa vào cache key.
- [ ] Test A/B accounts không bị lẫn response.
- [ ] Kiểm tra logout, Back, Forward, reload, offline và tab đang mở.
- [ ] SPA xóa persisted private data khi logout/switch user.
- [ ] Service Worker Cache API và IndexedDB được kiểm soát.
- [ ] Không tạo logs/analytics chứa sensitive response.
- [ ] Có quy trình purge CDN/incident handling nếu đã cache sai.
- [ ] Kiểm thử browser được hỗ trợ cùng `WebTestClient` và curl.
- [ ] Không suy luận từ status 200 duy nhất rằng chính sách cache đã đúng.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `Cache-Control: no-cache` có cấm browser lưu JSON hồ sơ không?

> Không. `no-cache` cho phép cache lưu response nhưng yêu cầu revalidate trước khi dùng lại. Nếu policy là không lưu, sử dụng `no-store`.

**Câu 2.** `private, max-age=60` có phù hợp với tài liệu mật trên máy dùng chung không?

> Không nên nếu yêu cầu cấm lưu. `private` chỉ cấm shared cache, browser vẫn có thể giữ bản sao.

**Câu 3.** Tại sao `Set-Cookie` không đủ bảo vệ cache?

> Theo RFC 9111, Set-Cookie không tự ngăn HTTP caches lưu một response nếu các điều kiện khác cho phép. Cần Cache-Control thích hợp.

**Câu 4.** Spring Security Reactive thường gửi những cache headers nào theo mặc định?

> `Cache-Control: no-cache, no-store, max-age=0, must-revalidate`, cùng `Pragma: no-cache` và `Expires: 0` khi được áp dụng.

**Câu 5.** Một controller đặt `public, max-age=3600` trên `/api/me`. Spring Security mặc định có chắc chắn ghi đè về no-store không?

> Không nên trông chờ như vậy. Spring Security có thể nhường cho response đã có Cache-Control, nên code review và test bắt buộc để phát hiện chính sách không an toàn.

**Câu 6.** Trong WebFlux, dùng class nào để đặt no-store trên ResponseEntity?

> `org.springframework.http.CacheControl.noStore()` cùng `ResponseEntity.ok().cacheControl(...)`.

**Câu 7.** Tại sao không nên dùng `headers.disable()` chỉ để cache CSS?

> Nó có thể tắt những security response headers khác. Hãy override riêng Cache-Control cho static assets.

**Câu 8.** Mặc định security headers có nghĩa mọi trang public chắc chắn bị cache cấm lưu hay không?

> Nếu security chain mặc định áp dụng và không có Cache-Control riêng, header no-store có thể được thêm; nhưng không được suy từ `permitAll` hay tên path. Hãy test response thực tế.

**Câu 9.** Vì sao `@Cacheable` ở service không thay thế HTTP Cache-Control?

> @Cacheable quản lý dữ liệu trung gian phía server, còn HTTP Cache-Control hướng dẫn browser/proxy/CDN lưu response.

**Câu 10.** Logout server đã invalidate session, vậy có cần no-store nữa không?

> Có với response riêng tư, để giảm nguy cơ HTTP caches giữ nội dung cũ. Ngược lại, no-store không thay session invalidation.

**Câu 11.** `no-store` có xóa IndexedDB/localStorage của SPA không?

> Không. Đó là client-managed storage, cần cleanup riêng theo auth lifecycle.

**Câu 12.** Khi nào có thể sử dụng `public, max-age=31536000, immutable`?

> Với asset công khai thật sự bất biến dưới URL có fingerprint/version; khi thay nội dung phải phát URL mới.

**Câu 13.** Một curl GET localhost có header đúng, có đủ kết luận CDN an toàn chưa?

> Chưa. Cần gọi qua public hostname, kiểm tra edge cache rules và thử các tài khoản khác nhau.

**Câu 14.** Response từ request có Authorization header đã luôn an toàn để cache chưa?

> Không. Có quy tắc riêng với shared cache, nhưng private cache vẫn có thể lưu; cookie-based auth, CDN override và response `public` khiến cần policy dữ liệu độc lập.

**Câu 15.** `Pragma: no-cache` và `Expires: 0` thay được `Cache-Control: no-store` không?

> Không. Đây là hỗ trợ tương thích/freshness cũ, không biểu diễn đầy đủ lệnh cấm lưu chuẩn của no-store.

## 19. Tổng kết và nguyên tắc triển khai

**Cache-Control là một phần bảo mật của HTTP response, không phải chỉ là công cụ performance.** Với nội dung nhạy cảm, mục tiêu đầu tiên là giảm khả năng browser/proxy/CDN lưu và tái sử dụng representation. Trong chuẩn HTTP caching, chỉ thị quan trọng nhất là **`no-store`**; `no-cache` và `private` có ý nghĩa khác, không tương đương.

Trong Spring Security Reactive, bộ cache headers mặc định thường đã bao gồm `no-store`. Không tắt mặc định chỉ vì muốn cache CSS/JS; hãy đặt `Cache-Control` riêng cho public versioned resources bằng `CacheControl.maxAge(...).cachePublic()`. Đối với API tài khoản, sao kê, profile, token hoặc file riêng tư, có thể đặt `CacheControl.noStore()` tường minh để chính sách được thể hiện rõ ngay trong controller.

Mỗi khi sửa cache policy, cần:
1. Xác định độ nhạy của response, không chỉ HTTP method hay đường dẫn.
2. Đảm bảo Spring Security headers và application overrides không mâu thuẫn.
3. Test status **và Cache-Control** với WebTestClient/curl.
4. Test qua CDN/reverse proxy thật nếu có.
5. Test logout, nút Back và dữ liệu lưu bởi SPA/Service Worker.
6. Giữ authentication, authorization, HTTPS và client state cleanup như những lớp riêng.

### Tài liệu tham khảo chính thức

- Spring Security Reference — Security HTTP Response Headers (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
- Spring Security Reference — Default Security Headers: https://docs.spring.io/spring-security/reference/features/exploits/headers.html
- Spring Framework Reference — HTTP Caching in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/caching.html
- Spring Framework Reference — WebFlux ResponseEntity: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html
- Spring Framework Javadoc — CacheControl: https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/http/CacheControl.html
- Spring Framework Reference — WebFlux Configuration: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- RFC 9111 — HTTP Caching: https://www.rfc-editor.org/rfc/rfc9111
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
- MDN — Cache-Control: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
- MDN — Clear-Site-Data: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data