# Vary: Origin và tránh cache nhầm chính sách CORS

## 1. Bài toán: cùng một REST API phục vụ nhiều origin

Một hệ thống có REST API tại `https://api.example.test` và hai ứng dụng trình duyệt:

- `https://shop.example.test`: trang bán hàng.
- `https://admin.example.test`: trang quản trị.

Cả hai được cho phép gọi API. API dùng allowlist và trả `Access-Control-Allow-Origin` (ACAO) bằng đúng origin đã được chấp nhận. Ví dụ hai lượt truy cập cùng URL `GET /api/catalog`:

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.test
Origin: https://shop.example.test

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://shop.example.test
Content-Type: application/json
Cache-Control: public, max-age=60

{"items":[{"id":"sku-1","name":"Sách Java"}]}
~~~

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.test
Origin: https://admin.example.test

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://admin.example.test
Content-Type: application/json
Cache-Control: public, max-age=60

{"items":[{"id":"sku-1","name":"Sách Java"}]}
~~~

Dù nội dung JSON giống hệt, **header ACAO phụ thuộc `Origin` của request**. Một CDN hoặc shared cache lưu phản hồi đầu tiên chỉ theo đường dẫn `/api/catalog` có thể trả nhầm `Access-Control-Allow-Origin: https://shop.example.test` cho request từ trang admin. Trình duyệt admin so sánh ACAO với `Origin: https://admin.example.test`, thấy không khớp và chặn JavaScript đọc phản hồi. Lỗi thực tế có thể biểu hiện thành *CORS error lúc có, lúc không*, phụ thuộc lượt truy cập nào đã làm ấm cache.

**Cách diễn đạt yêu cầu với HTTP cache:** Khi server tạo biến thể phản hồi dựa trên header request `Origin`, phải gửi **`Vary: Origin`** và bảo đảm CDN/reverse proxy thật sự tách cache theo `Origin`, hoặc không cache phản hồi đó ở shared cache.

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://shop.example.test
Vary: Origin
Cache-Control: public, max-age=60
Content-Type: application/json

{"items":[{"id":"sku-1","name":"Sách Java"}]}
~~~

Bài học tập trung vào **chính sách CORS và cache** trong thiết kế REST API: ý nghĩa của `Vary`, luồng preflight, các lớp cache của browser/CDN, cấu hình Java/Spring Security, kiểm thử HTTP và những rủi ro bảo mật đi kèm. Kiến thức hữu ích khi triển khai phân trang, ETag/cache, API gateway và xác thực/phân quyền cho ứng dụng web.

## 2. CORS thực sự kiểm soát điều gì?

**Cross-Origin Resource Sharing (CORS)** là cơ chế HTTP để trình duyệt quyết định có cho mã JavaScript từ một **origin** đọc phản hồi của origin khác hay không. Origin gồm **scheme + host + port**; `https://shop.example.test` khác `http://shop.example.test`, khác `https://shop.example.test:8443` và khác `https://admin.example.test`.

Ví dụ, trang tại `https://shop.example.test` gọi:

~~~javascript
const response = await fetch("https://api.example.test/api/catalog");
if (!response.ok) throw new Error("API failed");
const catalog = await response.json();
console.log(catalog.items);
~~~

Browser gửi `Origin: https://shop.example.test` cho cross-origin fetch. Sau khi nhận phản hồi, browser so sánh origin của mã đang chạy với chính sách CORS server trả về. Thiếu ACAO phù hợp có thể khiến `fetch` thất bại ở góc nhìn JavaScript dù server đã thực sự nhận request và trả HTTP 200. DevTools có thể hiển thị response/error khác với những gì code JS được đọc.

**CORS không phải cơ chế xác thực hoặc phân quyền trên server:**

- Một client như `curl`, backend Java, hoặc HTTP client tự viết có thể gửi tùy ý header `Origin`; CORS không ngăn client ngoài trình duyệt truy cập endpoint.
- Server vẫn phải kiểm access token, scope, tenant/owner và quyền trên từng resource.
- CORS không thay CSRF protection, SameSite cookie, rate limit hay ngăn XSS.
- “Origin được phép gọi API” chỉ nghĩa JavaScript của origin đó có thể đọc phản hồi nếu những điều kiện Fetch khác đều đáp ứng; nó **không** đồng nghĩa mọi người dùng của origin được phép đọc dữ liệu.

### 2.1. Một số header CORS quan trọng

| Header | Bên gửi | Ý nghĩa |
|---|---|---|
| `Origin` | Browser | Origin đã khởi phát request; đầu vào để server đánh giá allowlist |
| `Access-Control-Allow-Origin` | Server | Một origin cụ thể hoặc `*` trong trường hợp được phép |
| `Access-Control-Allow-Credentials` | Server | Giá trị `true` để browser cho phép truy cập phản hồi với credentials mode `include` khi các điều kiện khác hợp lệ |
| `Access-Control-Allow-Methods` | Server, trong preflight | Những phương thức được phép với preflight cụ thể |
| `Access-Control-Allow-Headers` | Server, trong preflight | Những tên request header được phép |
| `Access-Control-Max-Age` | Server, trong preflight | Thời gian browser được cache kết quả preflight, có giới hạn theo trình duyệt |
| `Access-Control-Expose-Headers` | Server | Những response header bổ sung JavaScript được đọc, ví dụ `ETag` |
| `Access-Control-Request-Method` | Browser, trong preflight | Phương thức của actual request dự định gửi |
| `Access-Control-Request-Headers` | Browser, trong preflight | Danh sách tên header không thuộc danh sách CORS-safelisted dự định gửi |
| `Vary` | Server | Báo cho HTTP cache biết những request header ảnh hưởng đến cách chọn representation/response |

Điểm cần nhớ: `Access-Control-Allow-Origin` **không nhận danh sách origin phân tách bằng dấu phẩy**. Nếu cho phép hai origin cụ thể, server chọn **một** giá trị khớp `Origin` hiện tại và thường đặt `Vary: Origin`. Không tạo `Access-Control-Allow-Origin: https://shop.example.test, https://admin.example.test`.

## 3. `Vary: Origin` hoạt động ra sao?

Theo semantics HTTP, header `Vary` thông báo các trường của **request** đã ảnh hưởng đến việc chọn hoặc tạo phản hồi. Cache lưu phản hồi có `Vary: Origin` phải xét giá trị `Origin` của request gốc và request mới trước khi tái sử dụng phản hồi. Nói đơn giản:

~~~text
Khóa tìm cache thực tế (mô hình khái niệm):
  method + URL + các chiều lựa chọn phản hồi do Vary quy định

Nếu response có Vary: Origin:
  GET /api/catalog + Origin=https://shop.example.test
  khác
  GET /api/catalog + Origin=https://admin.example.test
  khác
  GET /api/catalog + không có header Origin
~~~

Đây là mô hình giải thích, không phải định dạng khóa chính xác của mọi proxy/CDN. HTTP cache còn tuân theo các điều kiện như `Cache-Control`, `Authorization`, freshness, và quy tắc của từng sản phẩm. `Vary: Origin` không ra lệnh bắt buộc phải cache; nó quy định **khi một phản hồi đã được cache, cần so khớp request như thế nào**.

### 3.1. Phản hồi không có `Vary: Origin`: cache có thể dùng sai biến thể

~~~mermaid
sequenceDiagram
    participant A as Browser Shop
    participant E as CDN/cache
    participant S as REST API
    A->>E: GET /api/catalog, Origin=shop
    E->>S: Cache MISS, Origin=shop
    S-->>E: 200, ACAO=shop, thiếu Vary
    E-->>A: 200, ACAO=shop
    participant B as Browser Admin
    B->>E: GET /api/catalog, Origin=admin
    Note over E: Cache HIT theo URL, quên Origin
    E-->>B: 200, ACAO=shop
    Note over B: CORS check thất bại, JS không đọc được
~~~

Tình huống này thường gây **lỗi tính sẵn sàng/đúng chức năng**. Chỉ riêng việc trả ACAO của Shop cho Admin **không tự động cấp quyền đọc** cho origin Admin: browser vẫn yêu cầu ACAO phải khớp origin hiện tại (hoặc wildcard hợp lệ với credentials mode phù hợp). Rủi ro tiết lộ dữ liệu phát sinh khi kết hợp các lỗi khác, ví dụ chính sách allowlist sai, proxy tự ý sửa header, cache trộn response riêng của người dùng, hoặc phản hồi bí mật bị đánh dấu public.

### 3.2. Phản hồi có `Vary: Origin`: cache tách biến thể

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.test
Origin: https://shop.example.test

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://shop.example.test
Vary: Origin
Cache-Control: public, max-age=60
~~~

Sau đó:

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.test
Origin: https://admin.example.test

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://admin.example.test
Vary: Origin
Cache-Control: public, max-age=60
~~~

Hai phản hồi được coi là hai biến thể cho cùng URL. Khi request Shop quay lại trong thời gian hợp lệ, cache có thể dùng biến thể Shop; tương tự Admin dùng biến thể Admin. Nếu request mới có `Origin: https://attacker.example` mà không thuộc allowlist, cache không được mặc nhiên tái sử dụng biến thể Shop/Admin như một phản hồi cùng khóa.

### 3.3. Khi nào cần hoặc không cần `Vary: Origin`?

| Cấu hình server | ACAO có phụ thuộc Origin không? | Chính sách cache |
|---|---|---|
| API public luôn trả `Access-Control-Allow-Origin: *`, không dùng credentials | Không | Không cần `Vary: Origin` **chỉ vì CORS**; vẫn xét Vary khác nếu representation thay đổi |
| API luôn trả ACAO là một origin cố định, mọi response giống nhau | Không | Không cần Vary Origin nếu thực sự không có biến thể theo Origin |
| API có allowlist nhiều origin và phản chiếu đúng origin được phép | Có | **`Vary: Origin`**; kiểm tra CDN tuân thủ |
| API chỉ phát ACAO khi Origin thuộc allowlist, bỏ header với origin khác | Có | Vary Origin **cả ở phản hồi bị từ chối/no-origin theo thiết kế**, nếu các phản hồi này có thể được cache |
| API dùng nội dung tùy theo người dùng/tenant và thêm ACAO | Có thể | Cần cả Vary Origin và **bảo vệ cache dữ liệu riêng** (`private`/`no-store`, hoặc cache key/policy riêng), không chỉ Vary |

Nếu server luôn áp dụng `Cache-Control: no-store` và các cache tuân thủ, phản hồi không được lưu, nên vấn đề nhầm biến thể từ cache không xảy ra. Dù vậy, `Vary` vẫn là mô tả đúng khi header chính sách phụ thuộc Origin, và hữu ích nếu caching được bật trong tương lai. Cần nhớ cache tùy biến ở edge có thể bỏ qua các header HTTP nếu cấu hình không đúng.

### 3.4. Giữ nguyên các giá trị `Vary` đã tồn tại

Nếu API đã dùng gzip/encoding hoặc negotiation, có thể trả:

~~~http
Vary: Accept-Encoding, Accept-Language, Origin
~~~

**Không ghi đè** `Vary: Accept-Encoding` thành chỉ `Vary: Origin` vì làm mất chiều phân biệt representation. Có thể phát nhiều trường `Vary` theo cú pháp HTTP, nhưng ở proxy nên hợp nhất/append nhất quán để quan sát và xử lý. Header name không phân biệt hoa thường. `Vary: Origin` là về **header request**, không phải `Access-Control-Allow-Origin` của response.

## 4. CORS actual request, preflight và các bộ nhớ đệm khác nhau

### 4.1. Request không cần preflight

Một GET đơn giản, không có request header ngoài tập được CORS cho phép sẵn và không vượt các điều kiện khác, có thể không phát preflight:

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.test
Origin: https://shop.example.test

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://shop.example.test
Vary: Origin
Content-Type: application/json
Cache-Control: public, max-age=60

{"items":[]}
~~~

Browser quyết định JavaScript có đọc phản hồi hay không dựa vào ACAO và credentials mode. Với public body dùng chung, shared cache có thể lưu theo policy đã thiết kế. Với phản hồi riêng của tài khoản/tenant, phải xử lý caching thận trọng ở mục 6.

### 4.2. Request yêu cầu preflight

Ví dụ JavaScript dự định gọi `GET /api/orders` với `Authorization` header. Browser thường gửi preflight OPTIONS, thông báo phương thức và tên header muốn sử dụng:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Server cho phép request này thì phản hồi preflight có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://shop.example.test
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
Content-Length: 0
~~~

Browser kiểm tra preflight rồi mới gửi actual GET mang access token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Origin: https://shop.example.test
Authorization: Bearer example-access-token

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://shop.example.test
Vary: Origin
Cache-Control: private, no-store
Content-Type: application/json

{"orders":[{"id":"ord-101"}]}
~~~

Vì phản hồi OPTIONS thay đổi theo cả **Origin**, **Access-Control-Request-Method** và **Access-Control-Request-Headers**, khi xây HTTP/edge cache cho loại phản hồi này phải xét ba chiều đó. Ví dụ cùng `OPTIONS /api/orders` nhưng một request hỏi `GET + authorization` và request khác hỏi `DELETE + x-admin-key` phải được quyết định chính sách độc lập; không tái sử dụng kết quả preflight của request thứ nhất để chấp thuận request thứ hai.

**Hai loại cache không được đánh đồng:**

1. **Browser CORS-preflight cache**: bộ nhớ đệm chuyên biệt do Fetch điều khiển; `Access-Control-Max-Age: 600` hướng dẫn thời gian có thể tái sử dụng kết quả preflight (trình duyệt có giới hạn riêng). Nó khác HTTP cache thường và không lưu nội dung GET.
2. **HTTP cache/CDN**: hoạt động theo caching semantics cho HTTP response. `Vary` quyết định so khớp biến thể đã lưu. Response OPTIONS **không cacheable trong HTTP cache thông thường theo semantics chuẩn**; nếu một CDN/edge cấu hình cache OPTIONS theo cơ chế tùy chỉnh, phải thiết kế key và chính sách riêng với cả ba request header trên, hoặc bỏ qua cache OPTIONS.

`Access-Control-Max-Age` **không** cho phép CDN cache JSON trong 600 giây, và `Cache-Control: public, max-age=600` trên GET **không** nói browser có thể bỏ qua preflight. Đây là hai quyết định khác nhau.

### 4.3. Không dùng preflight làm cơ chế bảo vệ API

Preflight có thể được xử lý trước authentication bởi CORS filter để browser biết liệu request có được gửi. Preflight không có nghĩa token đã được xác minh, và không nên dựa vào token có trong actual request để quyết định trả preflight của một request chưa mang token. Actual request phải qua Spring Security Resource Server và tầng authorization, bất kể browser có gửi OPTIONS trước hay không.

Một client ngoài browser có thể gọi thẳng POST/PATCH mà không gửi preflight. API vẫn phải kiểm scope/role/ownership, CSRF khi dùng cookie, validate body, idempotency và các ràng buộc nghiệp vụ.

## 5. Cache key nào mới đủ?

### 5.1. Cache biến thể CORS

Với endpoint công khai có cùng body cho mọi người nhưng ACAO động, giả sử server cho phép Shop và Admin:

| Request | Biến thể cần được xét | Kết quả mong đợi |
|---|---|---|
| `GET /api/catalog`, `Origin: shop` | `URL + Origin=shop` | ACAO đúng Shop |
| `GET /api/catalog`, `Origin: admin` | `URL + Origin=admin` | ACAO đúng Admin |
| `GET /api/catalog`, Origin không được phép | `URL + Origin=other` | Không được phát ACAO cho origin không hợp lệ; có thể trả 403 theo CORS processor |
| `GET /api/catalog`, không có Origin | `URL + Origin=absent` | Không tự động ghép với biến thể Shop/Admin |

Bảng là mô hình cache key khái niệm; proxy thực tế có thể tính khóa từ URL, header, host, encoding và policy khác. Nếu CDN được cấu hình **custom cache key** và bỏ qua `Vary`, chỉ thêm header không giải quyết lỗi. Phải cấu hình CDN cho phép forward `Origin`, phân biệt cache key theo Origin đã chuẩn hóa hoặc disable cache ở route cần thiết. Không tự tạo ACAO ở edge từ một request Origin bất kỳ: chỉ phản chiếu origin **sau khi kiểm allowlist**.

### 5.2. Cache nội dung riêng theo user hoặc tenant

**`Vary: Origin` không bảo vệ nội dung phụ thuộc Authorization hoặc Cookie.** Hai người dùng cùng truy cập từ `https://shop.example.test` có **cùng Origin**, nhưng không được nhận cùng dữ liệu đơn hàng.

Ví dụ response dữ liệu riêng:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://shop.example.test
Vary: Origin
Cache-Control: private, no-store
Content-Type: application/json

{"orders":[{"id":"ord-alice-101"}]}
~~~

Dùng `Cache-Control: no-store` cho dữ liệu nhạy cảm cần tránh mọi lưu trữ HTTP cache; `private` ngăn shared cache lưu nhưng vẫn có thể cho phép browser cache nếu không có `no-store`. Dù HTTP có quy tắc đặc biệt đối với response request mang `Authorization`, không dựa vào việc mọi CDN custom, gateway hoặc code cache đều xử lý đúng. **Không đánh dấu `public` cho response cá nhân** khi chưa có thiết kế phân vùng cache và bảo vệ nội dung rõ ràng.

Nếu bắt buộc cache dữ liệu quyền riêng tại ứng dụng/Redis, key và kiểm tra quyền cần bao gồm tenant, actor hoặc phân đoạn quyền, tham số query, version policy, cũng như invalidation khi membership đổi. Những khóa này là **cơ chế cache nghiệp vụ**, khác với `Vary: Origin` của HTTP. Tránh đưa access token nguyên văn vào cache key/log.

### 5.3. ETag, 304 và biến thể

Nếu endpoint dùng ETag/`If-None-Match`, cần giữ `Vary` nhất quán giữa phản hồi `200 OK` và `304 Not Modified` trong cache policy tương ứng. Một intermediary không được bỏ thông tin Vary làm các biến thể Origin bị nhập lại khi revalidation. Đối với dữ liệu cá nhân, ETag phải phù hợp representation của từng người dùng/tenant, đồng thời không bỏ rào cản authorization khi trả 304.

### 5.4. CORS và CDN: chọn chiến lược

Có ba cách triển khai hợp lý, tùy endpoint:

- **Không cache shared:** API tài khoản, thông tin cá nhân, dữ liệu tenant. Bật `no-store`; vẫn trả CORS chính xác.
- **Cache public theo Origin:** Response public giống nhau về body nhưng ACAO chọn theo allowlist. Trả `Vary: Origin` và cấu hình CDN tôn trọng/khớp Origin.
- **CORS header tại edge:** Edge cache một body public không phụ thuộc origin, sau đó xác minh Origin theo allowlist và thêm ACAO hợp lệ trên **mỗi response**. Cách này giảm số biến thể nhưng phải được thiết kế, kiểm thử và giám sát chặt để không phản chiếu Origin tùy tiện. Nếu edge dựa trên header động của upstream, tránh chồng hai lớp CORS khiến response trùng ACAO hoặc trái nhau.

Không gắn bất kỳ giải pháp nào với tuyên bố “đặt `Vary: Origin` là bảo mật hoàn chỉnh”. Nó giải quyết **một chiều cache variation**.

## 6. Thiết kế allowlist và credentials an toàn

### 6.1. Exact origin và dấu `*`

Cho phép `https://shop.example.test` và `https://admin.example.test` bằng exact match. Không so khớp dạng `endsWith("example.test")` vì các tên giả mạo như `notexample.test` có thể lọt; không dùng `contains("trusted")`. Với nhiều subdomain, dùng pattern có phạm vi rõ, cân nhắc quyền kiểm soát subdomain và nguy cơ subdomain takeover. Scheme và port phải được xét chính xác.

Origin đặc biệt `null` có thể xuất hiện từ sandbox, `file:` hoặc ngữ cảnh opaque origin. Không cho phép `Origin: null` một cách mặc định vì có thể tạo đường truy cập bất ngờ. Không trả `Access-Control-Allow-Origin: <Origin bất kỳ>` cho mọi request, đặc biệt với cookie.

`Access-Control-Allow-Origin: *` có thể phù hợp với tài nguyên **công khai, không dùng credentials** và không cần giới hạn origin. Với request có credentials mode `include`, browser không chấp nhận wildcard `*` cho ACAO; server phải trả một origin cụ thể và `Access-Control-Allow-Credentials: true` nếu muốn client đọc phản hồi. ACAO không thể là danh sách nhiều origin.

### 6.2. Credentialed request không tự an toàn vì CORS

Nếu frontend dùng:

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
  credentials: "include"
});
~~~

thì cookie chỉ thực sự được gửi khi các chính sách browser/cookie tương ứng cho phép (`SameSite`, `Secure`, domain, các hạn chế third-party cookie). Server cần ACAO là **origin cụ thể**, `Access-Control-Allow-Credentials: true` và `Vary: Origin` nếu allowlist động.

CORS kiểm soát **quyền đọc response của JavaScript**; request có side effect vẫn có thể đến server tùy loại request và tình huống browser. Với cookie session, dùng token/biện pháp CSRF phù hợp, SameSite và kiểm tra Origin/Referer cho các thao tác nhạy cảm theo thiết kế. `Access-Control-Allow-Credentials: true` không thay thế bảo vệ CSRF. Với bearer API, access token vẫn phải xác minh; quyền `orders.read` không thay thế phân quyền đối tượng/tenant.

### 6.3. Header cho JavaScript đọc response

Nếu frontend cần đọc `ETag` hoặc `X-Request-Id` từ cross-origin response, cấu hình:

~~~http
Access-Control-Expose-Headers: ETag, X-Request-Id
~~~

Header này khác `Access-Control-Allow-Headers`: **Expose-Headers** là response header JavaScript muốn đọc, còn **Allow-Headers** là request header browser muốn gửi. `Authorization` thường cần có trong `Access-Control-Allow-Headers` của preflight khi frontend gửi bearer token.

## 7. Triển khai bằng Java/Spring Boot

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Security 6.x. REST API nhận Bearer access token qua header cho endpoint riêng, còn `/api/catalog` là endpoint public được phép cache. Các dependency điển hình: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-boot-starter-test`, `spring-security-test`.

### 7.1. CORS nên chạy trước xác thực

Spring Security cần xử lý preflight trước khi các filter yêu cầu access token, vì preflight không giống actual request đã xác thực. Sử dụng `CorsConfigurationSource` và `http.cors(...)`:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ApiSecurity {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://shop.example.test",
            "https://admin.example.test"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-Request-Id"
        ));
        cors.setExposedHeaders(List.of("ETag", "X-Request-Id"));

        // Ví dụ dùng bearer token và không dùng cookie cross-origin.
        cors.setAllowCredentials(false);
        cors.setMaxAge(600L);  // Browser preflight cache, đơn vị giây.

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            // Chỉ phù hợp API stateless dựa vào Bearer header,
            // không dùng browser cookie làm credential xác thực.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(s ->
                s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/catalog").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Cấu hình JWT Resource Server trong ứng dụng thật còn cần issuer và audience của API:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test
~~~

Spring Resource Server với issuer kiểm tra các điều kiện JWT cơ bản theo cấu hình; **cần thêm validator audience** yêu cầu token dành cho API hiện tại (ví dụ `aud=shop-api`). Không chấp nhận ID token OIDC có `aud` dành cho web client. Một ví dụ validator độc lập:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience() != null && jwt.getAudience().contains("shop-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));
~~~

Đưa validator này vào `JwtDecoder` đang dùng cùng `JwtValidators.createDefaultWithIssuer(...)` để không làm mất các validator mặc định. Mẫu security phía trên tập trung vào CORS/caching, không tự tuyên bố Spring đã kiểm tenant/ownership chỉ nhờ scope.

**CORS trong Spring:** Khi cấu hình `CorsConfiguration` qua hệ thống CORS của Spring, processor mặc định thường bổ sung `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers` cho các response nó xử lý. Cần **quan sát response thực tế ở cả ứng dụng lẫn sau CDN/proxy**, vì gateway, filter riêng hoặc cache có thể ghi đè/loại bỏ header. Đừng thêm một filter thủ công phản chiếu Origin vô điều kiện hoặc ghi đè `Vary` đã có.

### 7.2. Endpoint public được phép cache

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {
    @GetMapping("/api/catalog")
    ResponseEntity<Map<String, Object>> catalog() {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.maxAge(
                java.time.Duration.ofSeconds(60)).cachePublic())
            .body(Map.of("items", List.of(
                Map.of("id", "sku-1", "name", "Sách Java")
            )));
    }
}
~~~

Body catalog **công khai, không thay đổi theo user, cookie, tenant hoặc token** trong ví dụ. Vì ACAO thay đổi theo allowed Origin, response phải có `Vary: Origin` nếu cache shared. Trường hợp body còn phụ thuộc `Accept-Language`, `Accept-Encoding`, version hoặc filter, cache policy và `Vary`/key phải tính đủ các chiều liên quan.

### 7.3. Endpoint riêng tư: CORS đúng nhưng không cache chung

Một API đơn hàng trả dữ liệu theo access token và quyền thực tế cần thiết lập:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    @GetMapping("/api/orders")
    ResponseEntity<String> myOrders() {
        // Minh họa header cache; dữ liệu phải lấy theo principal
        // đã xác minh, tenant và object-level authorization.
        String authorizedJson = "{\"orders\":[]}";
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(authorizedJson);
    }
}
~~~

Mã controller chỉ minh họa cache header; **không đại diện logic nghiệp vụ đầy đủ**. Endpoint thực tế cần kiểm principal, tenant, owner/role rồi mới truy vấn. Với dữ liệu riêng, ưu tiên `no-store` khi phù hợp thay vì công khai cache, kể cả khi đã có `Vary: Origin`.

### 7.4. Khi dùng cookie cross-origin

Nếu ứng dụng cần cookie session và cross-origin `credentials: "include"`, có thể đặt `cors.setAllowCredentials(true)` **chỉ** với danh sách origin cụ thể được tin cậy; không đặt `allowedOrigins("*")`. Đồng thời thay cấu hình stateless/no-CSRF của ví dụ bằng chính sách session, SameSite/Secure cookie và chống CSRF phù hợp. Cấu hình cross-origin credentialed **không nên được ghép nguyên xi** với `csrf.disable()` chỉ dành cho bearer stateless.

Cần thử cả actual response và preflight với credentialed mode, vì chỉ phản hồi ACAO đúng mà thiếu `Access-Control-Allow-Credentials: true` thì browser vẫn chặn JavaScript truy cập response khi credentials mode là `include`.

## 8. Debug HTTP bằng curl và DevTools

Để nhìn thấy response sau server và edge, dùng lệnh `curl` giả lập Origin. Curl không thực thi CORS như browser, nên kết quả dùng để **kiểm tra header**, không kết luận JavaScript chắc chắn đọc được.

~~~bash
curl -i 'https://api.example.test/api/catalog' \
  -H 'Origin: https://shop.example.test'

curl -i 'https://api.example.test/api/catalog' \
  -H 'Origin: https://admin.example.test'

curl -i 'https://api.example.test/api/catalog' \
  -H 'Origin: https://unknown.example.test'
~~~

Kỳ vọng: hai origin trong allowlist nhận ACAO đúng origin của mình; origin ngoài allowlist bị từ chối hoặc không nhận ACAO (tùy CORS processor), **không** nhận `Access-Control-Allow-Origin: *` ngoài chính sách. Với response có thể cache, quan sát `Vary: Origin`. Dùng công cụ Network/Headers trong DevTools để so sánh `Origin`, ACAO, `Vary`, `Cache-Control` và `Age`/cache-status do CDN trả.

Thử preflight:

~~~bash
curl -i -X OPTIONS 'https://api.example.test/api/orders' \
  -H 'Origin: https://shop.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Thử header hoặc method bị cấm:

~~~bash
curl -i -X OPTIONS 'https://api.example.test/api/orders' \
  -H 'Origin: https://shop.example.test' \
  -H 'Access-Control-Request-Method: DELETE' \
  -H 'Access-Control-Request-Headers: x-admin-secret'
~~~

Request thứ hai phải không được cấp phép preflight theo cấu hình mẫu. Việc Spring có thể trả 403 cho preflight không hợp lệ là hành vi của processor; HTTP contract thực tế cần kiểm theo cấu hình và phiên bản framework.

**Quy trình chẩn đoán lỗi “lúc được lúc không”:**

1. Đối chiếu từng request có/không có `Origin`, origin được phép, `credentials` mode và preflight có hợp lệ hay không.
2. So sánh response **trực tiếp từ origin server** với response **qua CDN**; quan sát ACAO, `Vary`, `Age`, cache hit/miss và tên rule edge.
3. Lặp thứ tự **Shop → Admin** rồi **Admin → Shop**, lần lượt làm ấm/xóa cache trên môi trường test. Nếu lỗi phụ thuộc thứ tự, nghi ngờ cache trộn biến thể Origin.
4. Với OPTIONS, so sánh `Access-Control-Request-Method` và `Access-Control-Request-Headers`; phân biệt preflight cache của browser với caching tại proxy.
5. Với dữ liệu người dùng, xác minh cache policy riêng biệt, tránh cache shared dù CORS header đúng.

Không cần tắt CORS hoặc mở allowlist `*` để “chữa nhanh”; như vậy có thể tạo rủi ro khác và che mất lỗi cache.

## 9. Kiểm thử tự động Spring MVC/Security

### 9.1. Kiểm tra hai origin hợp lệ và Vary

Dùng `spring-boot-starter-test` và `spring-security-test`. Ví dụ tích hợp với cấu hình ở mục 7:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CorsCachePolicyTest {
    @Autowired MockMvc mvc;

    static final String SHOP = "https://shop.example.test";
    static final String ADMIN = "https://admin.example.test";

    @Test
    void eachAllowedOriginGetsItsOwnCorsVariant() throws Exception {
        for (String origin : new String[] { SHOP, ADMIN }) {
            mvc.perform(get("/api/catalog")
                    .header("Origin", origin))
                .andExpect(status().isOk())
                .andExpect(header().string(
                    "Access-Control-Allow-Origin", origin))
                .andExpect(result -> assertThat(String.join(
                    ",", result.getResponse().getHeaders("Vary")))
                    .contains("Origin"));
        }
    }

    @Test
    void noOriginDoesNotGetAnArbitraryAllowedOrigin() throws Exception {
        mvc.perform(get("/api/catalog"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
    }

    @Test
    void unknownOriginIsNotAllowed() throws Exception {
        mvc.perform(get("/api/catalog")
                .header("Origin", "https://unknown.example.test"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
    }

    @Test
    void validPreflightHasAllVariationHeaders() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", SHOP)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", SHOP))
            .andExpect(header().string(
                "Access-Control-Allow-Methods", containsString("GET")))
            .andExpect(header().string(
                "Access-Control-Allow-Headers", containsString("authorization")))
            .andExpect(result -> {
                String vary = String.join(
                    ",", result.getResponse().getHeaders("Vary"));
                assertThat(vary).contains(
                    "Origin",
                    "Access-Control-Request-Method",
                    "Access-Control-Request-Headers");
            });
    }

    @Test
    void forbiddenPreflightHeaderIsRejected() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", SHOP)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "x-admin-secret"))
            .andExpect(status().isForbidden());
    }
}
~~~

Các kiểm thử trên kiểm response tại tầng **Spring app**, chưa chứng minh CDN tôn trọng `Vary`. Nếu môi trường có nhiều header `Vary` riêng lẻ hoặc gateway hợp nhất giá trị, dùng assertion gộp/tách chuẩn hóa các field thay vì phụ thuộc vào một chuỗi duy nhất. `MockMvc` cũng không mô phỏng toàn bộ logic Fetch, preflight cache của browser hoặc HTTP cache của CDN; cần test tích hợp end-to-end tương ứng.

### 9.2. Kiểm tra cache với hai origin theo thứ tự đảo nhau

Trên staging với CDN hoặc proxy cache thật:

1. Xóa/tạo namespace cache thử nghiệm.
2. Gọi GET public với `Origin: shop` để tạo cache entry; gọi cùng URL với `Origin: admin`; xác minh ACAO lần 2 là Admin.
3. Lặp lại theo thứ tự **Admin → Shop**; xác minh ACAO lần 2 là Shop.
4. Gọi cùng URL không có Origin và với Origin ngoài allowlist; không được nhận ACAO không phù hợp.
5. Gọi lại từng origin để xác minh cache hit vẫn giữ ACAO đúng; xem `Age` hoặc cache-status nếu CDN có hỗ trợ.
6. Đổi method và requested headers trong OPTIONS nếu edge có custom preflight caching; chứng minh một preflight được phép không làm một tổ hợp khác được phép.
7. Với endpoint private, đăng nhập user khác nhưng cùng Origin; không có dữ liệu/ETag/response riêng bị tái sử dụng giữa hai principal.

Ví dụ ma trận:

| Route | Origin | Request | Kỳ vọng |
|---|---|---|---|
| `GET /api/catalog` | Shop | Actual GET | ACAO Shop, Vary Origin, body public |
| `GET /api/catalog` | Admin | Actual GET | ACAO Admin, Vary Origin, body public |
| `GET /api/catalog` | Origin bị cấm | Actual GET | Không có ACAO cấp phép; từ chối theo processor |
| `GET /api/catalog` | Không Origin | Actual GET | Không vô tình phản chiếu Shop/Admin |
| `OPTIONS /api/orders` | Shop | GET + authorization | Preflight hợp lệ, có Vary ba chiều |
| `OPTIONS /api/orders` | Shop | DELETE + x-admin-secret | Không được chấp nhận theo policy |
| `GET /api/orders` | Shop, user A | Có access token A | Nội dung user A, không shared-cache |
| `GET /api/orders` | Shop, user B | Có access token B | Nội dung user B, không nhận body A |
| `GET /api/catalog` | Shop sau Admin | Cache HIT | ACAO Shop vẫn chính xác |
| `GET /api/catalog` | Admin sau Shop | Cache HIT | ACAO Admin vẫn chính xác |

### 9.3. Kiểm thử negative security

Bổ sung kiểm thử chặn `Origin: https://shop.example.test.attacker.test`, `http://shop.example.test`, port lạ, và `Origin: null` nếu không được allowlist. Kiểm tra CORS filter trước authentication để preflight hợp lệ không bị trả 401 sai vì thiếu bearer token. Kiểm tra actual GET riêng vẫn yêu cầu access token hợp lệ, scope và quyền tài nguyên; nếu token sai, server trả 401/403 dù CORS hợp lệ. Nếu dùng cookie session và `credentials: include`, kiểm CSRF cho POST/PATCH và cookie flags thực tế.

Một test quan trọng khác: endpoint có middleware thêm `Vary: Accept-Encoding` hoặc `Vary: Accept-Language` phải giữ cả `Origin`; edge không được ghi đè `Vary` khi nén hoặc chuyển đổi nội dung. Với `304 Not Modified`, kiểm Vary vẫn nhất quán.

## 10. Tình huống thực hành

### Bài tập 1: giải thích lỗi phụ thuộc thứ tự cache

CDN lưu `GET /api/catalog` theo URL, cache 10 phút. Khi Shop gọi đầu tiên, Admin gặp CORS error; khi Admin gọi đầu tiên, Shop gặp CORS error. Server phản chiếu đúng origin trong allowlist.

Yêu cầu: vẽ sequence giải thích nguyên nhân, đề xuất `Vary: Origin` và các thay đổi CDN tương ứng, nêu cách chứng minh qua hai thứ tự làm ấm cache. Giải thích vì sao trường hợp này thường gây lỗi chức năng và không tự động cho phép origin trái phép đọc response.

**Tiêu chí đạt:** Chỉ ra response header được cache sai; kiểm việc CDN forward và match Origin thay vì chỉ kiểm source code server.

### Bài tập 2: phân loại ba loại cache

Một developer có các header:

~~~http
Access-Control-Max-Age: 3600
Cache-Control: public, max-age=60
Vary: Origin
~~~

Yêu cầu: giải thích 3600 và 60 giây liên quan tới loại cache nào; browser có thể bỏ preflight trong điều kiện gì, và CDN có thể cache GET trong điều kiện gì; nếu GET chứa dữ liệu user thì phải thay cache policy ra sao.

**Tiêu chí đạt:** Không nhầm browser preflight cache với HTTP cache/CDN; không dùng `Vary: Origin` làm hàng rào giữa user A và user B.

### Bài tập 3: sửa cấu hình Spring có lỗi

Cấu hình sai:

~~~java
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of("*"));
~~~

Yêu cầu: sửa theo allowlist hai origin Shop/Admin, xử lý bearer Authorization preflight, dùng `http.cors(...)`, giải thích credentialed mode và tránh tắt CSRF nếu API dùng cookie session. Thêm test cho Origin giả `shop.example.test.attacker.test`.

**Tiêu chí đạt:** Không wildcard ACAO khi credentials mode include; preflight hợp lệ trước authentication, actual request vẫn được bảo vệ.

### Bài tập 4: preflight sai biến thể

Edge tự cache OPTIONS theo URL. Client A preflight `GET + authorization` thành công; client B preflight `DELETE + x-admin-secret` lại được trả cùng response đã cache. Hãy chỉ ra những chiều cần tách, header Vary tương ứng và lý do tốt nhất có thể là **không cache OPTIONS ở edge**.

**Tiêu chí đạt:** Phân biệt Origin, Access-Control-Request-Method, Access-Control-Request-Headers; không cho kết luận rằng preflight được phép tương đương được phép thao tác nghiệp vụ.

### Bài tập 5: cache dữ liệu tenant

Hai người dùng trong cùng Shop origin có token hợp lệ với tenant A và B. Một Redis cache lưu `GET /api/orders?page=1` chỉ theo URL và có `Vary: Origin` tại REST layer.

Yêu cầu: phân tích vì sao vẫn lộ dữ liệu; đề xuất `no-store` cho HTTP response và thiết kế cache nghiệp vụ an toàn nếu cần (tenant, principal/role, filter, invalidation, quyền trên bản ghi). Viết test gọi A rồi B trong cùng Origin.

**Tiêu chí đạt:** Chặn tái sử dụng body riêng, không nhầm CORS với authorization hoặc cache dữ liệu.

## 11. Checklist triển khai và tài liệu chuẩn

Trước khi bật CDN cho REST API có CORS động, hãy trả lời:

- Allowlist origin có exact match theo scheme, host và port không? Có từ chối Origin `null`/origin giả theo chính sách?
- ACAO trả về là đúng **một** origin được phép hay wildcard chỉ với tài nguyên thực sự public, không credentialed?
- Nếu phản hồi thay đổi theo Origin, đã có `Vary: Origin` trên tất cả biến thể được cache, kể cả 304/không Origin/denied Origin khi thích hợp?
- Với preflight, `Access-Control-Request-Method` và `Access-Control-Request-Headers` đã được xét trong policy; edge có tránh cache OPTIONS tùy tiện?
- CDN có forward Origin và tôn trọng Vary, hay đã thiết lập cache key/edge rule riêng được kiểm thử?
- `Cache-Control` của body public/private đã phù hợp, không dùng Vary Origin để phân tách người dùng/tenant?
- Spring Security có xử lý CORS trước auth; actual request vẫn kiểm access token, scope, CSRF khi dùng cookie, quyền trên tài nguyên?
- Các trường Vary cũ như Accept-Encoding có được giữ nguyên; các response 200/304 có chính sách nhất quán?
- Bộ kiểm thử có thực hiện Shop → Admin và Admin → Shop qua **proxy thật**, và một origin bất hợp lệ?

Tài liệu đối chiếu:

- **RFC 9110 — HTTP Semantics, Vary:** https://www.rfc-editor.org/rfc/rfc9110 (mục 12.5.5).
- **RFC 9111 — HTTP Caching:** https://www.rfc-editor.org/rfc/rfc9111
- **WHATWG Fetch — CORS protocol và CORS-preflight cache:** https://fetch.spec.whatwg.org/
- **MDN — Vary HTTP header:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary
- **MDN — CORS:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- **Spring Security — CORS:** https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- **Spring Framework — CORS:** https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html

**Ghi nhớ:** `Vary: Origin` cho cache biết **các phản hồi CORS là biến thể theo request Origin**; bản thân CORS quyết định browser được đọc response hay không; cache HTTP/CDN quyết định có tái sử dụng response hay không; còn authentication/authorization quyết định caller có quyền với resource hay không. Muốn REST API hoạt động đúng và an toàn, phải thiết kế và kiểm thử cả bốn lớp này.
