# HTTPS, origin, chuyển hướng và thông tin xác thực

## 1. Bức tranh tổng thể: bốn câu hỏi phải tách biệt

Một HTTP client Java không chỉ cần biết “có kết nối được không”. Nó còn phải giải quyết:

1. **HTTPS:** request đang đi trên một kết nối TLS xác thực đúng server, mã hóa và bảo vệ tính toàn vẹn của dữ liệu tại chặng đó không?
2. **Origin:** URL hiện tại và URL đích có cùng bộ ba **scheme, host, effective port** không?
3. **Chuyển hướng (redirect):** khi nhận HTTP 3xx và `Location`, có nên tạo request mới không; method/body được giữ hay thay đổi?
4. **Thông tin xác thực (credentials):** `Authorization`, cookies, API key hoặc dữ liệu đăng nhập trong body có được phép đi đến origin mới không?

**Bài học cốt lõi:** HTTPS không tự biến một redirect cross-origin thành an toàn. Một URL mới có certificate hợp lệ vẫn có thể thuộc người nhận **không được phép** nhận token của URL ban đầu. Java `HttpClient.Redirect.NORMAL` chặn chuyển từ HTTPS sang HTTP nhưng **không phải chính sách chỉ cho cùng origin**.

Cách an toàn, dễ kiểm chứng với request nhạy cảm là **`Redirect.NEVER` → kiểm tra từng Location/URI → chỉ tạo request tiếp theo sau khi cho phép theo chính sách → cấp lại đúng credential cho đúng đích**. Việc kiểm tra không dừng ở origin: còn phải xét scheme, URL, trust boundary, request body, DNS/IP nếu URL không đáng tin và giới hạn hop.

~~~text
Java HTTP request
   |
   +--> URI + method + headers + body
   |        |
   |        +--> HTTPS/TLS xác thực server và bảo vệ đường truyền
   |
   +--> HTTP response
            |
            +-- 200 / 204: xử lý response
            +-- 401 / 403 / 407: xét authentication/authorization
            +-- 3xx + Location:
                     |
                     +--> resolve URI đích
                     +--> so origin, scheme, method, body, credentials
                     +--> kiểm tra policy và hop limit
                                |
                                +-- cấm --> dừng
                                +-- cho phép --> tạo request MỚI tới đích
~~~

Dù request được gửi tới cùng server, authentication và authorization vẫn là hai công việc riêng: **xác định ai đang gọi** và **quyết định người đó có được dùng tài nguyên**.

## 2. HTTPS và TLS bảo vệ gì?

HTTPS là HTTP được chuyển qua một kênh bảo mật TLS thích hợp. Với HTTP/1.1 và HTTP/2, đó thường là HTTP over TLS/TCP; HTTP/3 dùng QUIC với TLS tích hợp. Không nên đồng nhất mọi HTTPS với duy nhất một loại TCP socket.

Khi kết nối HTTPS chuẩn, client kiểm tra certificate chain theo trust configuration và tên server theo certificate SAN/hostname, thiết lập khóa TLS, rồi trao đổi HTTP trong kênh đã mã hóa. Các thuộc tính điển hình:

| Thuộc tính | HTTPS/TLS giúp bảo vệ | Những gì HTTPS **không** bảo đảm |
|---|---|---|
| **Confidentiality** | Che nội dung HTTP header/body khỏi người nghe lén trên chặng TLS | Không giấu nội dung với chính server, TLS proxy, log hoặc nơi lưu trữ |
| **Integrity** | Phát hiện sửa đổi trái phép trên kênh TLS | Không kiểm tra nghiệp vụ/JSON có đúng hay quyền user có hợp lệ |
| **Server authentication** | Xác minh danh tính DNS hostname bằng chứng chỉ được tin cậy | Không chứng minh user đã đăng nhập, server có quyền nhận token khác hay không |
| **Chống MITM trên kênh TLS** | Với certificate/hostname check đúng, làm khó việc chen vào nội dung traffic | Mất tác dụng nếu tin nhầm CA hoặc cố tình bỏ qua TLS verification |
| **Bảo vệ credentials in transit** | `Authorization` và `Cookie` được mã hóa trong HTTPS request | Không ngăn rò rỉ qua URL, redirect sai, code client, log, proxy đã giải mã |

Certificate của `https://b.example.test` chỉ chứng minh client đang nói chuyện với **b.example.test** theo TLS trust configuration; nó không chứng minh b.example.test có quyền nhận `Authorization` ban đầu dành cho **a.example.test**.

### 2.1. TLS termination và “mã hóa đầu cuối”

Một reverse proxy hoặc load balancer có thể kết thúc TLS rồi gửi request tới upstream khác. HTTPS bảo vệ **client → TLS terminator**; chặng proxy → backend cần bảo vệ riêng (HTTPS/mTLS/private transport và chính sách vận hành). Không có bảo đảm mặc định rằng dữ liệu ở database, disk hoặc log được mã hóa hay xóa đúng cách.

### 2.2. Đừng khắc phục SSL lỗi bằng cách bỏ kiểm tra

Nếu Java gặp `SSLHandshakeException` hoặc hostname mismatch, cần kiểm tra CA/truststore, certificate SAN, hostname, thời gian hệ thống, proxy và TLS policy. **Không** dùng trust-all certificate manager, tắt hostname verification hoặc tự động fallback sang HTTP trong production. Cách đó làm mất bảo đảm HTTPS mà hệ thống đang trông đợi.

## 3. Origin = scheme + host + effective port

Theo RFC 6454, origin của một URI HTTP(S) thường là bộ ba:

~~~text
origin = (scheme, host, effective port)

https://api.example.test:8443/v1/orders?page=1#section
          \______host____/ \port/
scheme = https
port   = 8443
origin = (https, api.example.test, 8443)
~~~

`https` mặc định dùng cổng **443**; `http` mặc định **80**. Nếu URI không ghi port, phải dùng effective port theo scheme. **Path/query/fragment không thuộc bộ ba origin**. Scheme/host được chuẩn hóa theo quy tắc URL; so sánh raw URL string là không đủ.

| URL A | URL B | Same-origin? | Giải thích |
|---|---|---|---|
| `https://api.example.test/a` | `https://api.example.test/b?x=2` | **Có** | Chỉ thay path/query |
| `https://api.example.test` | `https://api.example.test:443/v2` | **Có** | HTTPS effective port là 443 |
| `http://api.example.test` | `http://api.example.test:80/a` | **Có** | HTTP effective port là 80 |
| `https://api.example.test` | `http://api.example.test` | **Không** | Khác **scheme** |
| `https://api.example.test` | `https://api.example.test:8443` | **Không** | Khác **port** |
| `https://api.example.test` | `https://auth.example.test` | **Không** | Khác **host** |
| `https://example.test` | `https://EXAMPLE.TEST/path` | **Có**, sau chuẩn hóa | Host không phân biệt chữ hoa/thường |
| `https://example.test` | `https://sub.example.test` | **Không** | Subdomain riêng là host khác |

**Cùng địa chỉ IP không đồng nghĩa cùng origin.** Hai hostname khác nhau có thể resolve tới cùng IP (CDN, virtual host). Cùng hostname có thể đổi IP theo DNS mà vẫn là cùng origin. Kỹ thuật chống SSRF phải xét DNS/network destination **bên cạnh** origin, không dùng chúng thay nhau.

### 3.1. Origin, site và cookie scope là ba thứ khác

- **Same-origin** dựa trên scheme, host, port.
- **Same-site** trong ngữ cảnh cookie/SameSite thường dựa trên scheme và registrable domain; hai subdomain có thể cùng site mà khác origin.
- **Cookie scope** được quyết định theo Domain, Path, Secure, SameSite và chính sách user agent; cookie có thể được gửi sang origin khác nếu phù hợp cookie policy.

Vì vậy nói “cookie chỉ nằm trong same-origin” là **sai**. Cũng không được suy luận “same-site nghĩa hai subdomain có cùng quyền nhận bearer token”.

### 3.2. Origin header và CORS

Header `Origin` mô tả origin bên phát sinh request theo quy tắc browser/giao thức, có thể khác origin của URL đích. Header này có thể **không xuất hiện** trong nhiều request hoặc có các giá trị đặc biệt theo ngữ cảnh. Ví dụ:

~~~http
Origin: https://app.example.test
~~~

Trong một request tới `https://api.example.test`, đây là cross-origin. CORS quyết định liệu **JavaScript chạy trong browser** được đọc một số response cross-origin hay không; không phải authentication, không phải tường lửa backend, và **không ngăn Java `HttpClient` gọi tới host khác**. Server vẫn phải xác thực và phân quyền từng request; không tin một header Origin tự khai như bằng chứng danh tính.

`Host`, HTTP/2 `:authority`, TLS SNI và `Origin` có vai trò khác nhau. Đổi URI redirect có thể buộc client thiết lập đúng authority và TLS server name của endpoint mới; không nên copy mù các header phụ thuộc origin cũ.

## 4. Redirect 3xx hoạt động như thế nào?

Server có thể trả:

~~~http
HTTP/1.1 302 Found
Location: /v2/items
Content-Length: 0
~~~

Client **có thể** gửi request tiếp theo đến URL tại `Location` nếu policy cho phép. Redirect là một **response HTTP kèm yêu cầu điều hướng**, không phải dấu hiệu server đã nhận đủ credential tại endpoint mới.

`Location` có thể **relative** hoặc **absolute**. Với request `https://api.example.test/v1/items`:

~~~text
Location: /v2/items
  -> https://api.example.test/v2/items
     cùng origin, khác path

Location: ../status
  -> https://api.example.test/status
     cùng origin

Location: https://files.example.test/object
  -> https://files.example.test/object
     khác host/origin

Location: http://api.example.test/v2
  -> http://api.example.test/v2
     khác scheme/origin, HTTPS bị downgrade
~~~

Java `URI.resolve(...)` giải relative URI trên URI gốc, **không tự đánh giá security của URL đích**. Với input không đáng tin, ngoài `URI.resolve` cần kiểm tra scheme, host, userinfo, port, URL normalization, DNS/IP, allowlist và loop limit.

### 4.1. Không phải mọi response 3xx đều nên follow

| Status | Ý nghĩa | Method/body khi client follow |
|---|---|---|
| **301 Moved Permanently** | Địa chỉ tài nguyên đổi lâu dài | Với POST, client **có thể** đổi sang GET |
| **302 Found** | Địa chỉ tạm thời thay đổi | Với POST, client **có thể** đổi sang GET |
| **303 See Other** | Xem kết quả/tài nguyên qua URL khác | Thông thường dùng GET (hoặc HEAD phù hợp) để truy xuất đích |
| **307 Temporary Redirect** | Redirect tạm thời nhưng **giữ method** | Không được tự đổi method; body có thể cần gửi lại |
| **308 Permanent Redirect** | Redirect lâu dài và **giữ method** | Không được tự đổi method; body có thể cần gửi lại |
| **304 Not Modified** | Conditional cache | **Không** phải một redirect sang URI mới |

Các semantics này dựa trên RFC 9110. Lịch sử hành vi của 301/302 đối với POST khác 307/308. Javadoc Java 17 `HttpClient.Redirect` nói rằng khi auto redirect 301/302, **POST được đổi sang GET** trong implementation Java.

**Không tự động phát lại body chứa mật khẩu hay thông tin nhạy cảm qua 307/308** tới origin khác chỉ vì có Location. Vì method/body được giữ, redirect có thể chuyển cả form password hoặc dữ liệu bí mật sang nơi không tin cậy. RFC 9700 (OAuth 2.0 Security BCP) đặc biệt cảnh báo bẫy redirect 307 trong luồng đăng nhập, và nêu lựa chọn 303 trong trường hợp phù hợp.

### 4.2. Redirect, retry và caching không giống nhau

- **Redirect:** server chỉ định URL đích mới bằng status/Location; client phải quyết định có theo không.
- **Retry:** client gửi lại request do lỗi/timeouts/rate limit, không nhất thiết có Location.
- **304:** đáp ứng conditional request liên quan cache, không yêu cầu gửi request đến URL Location mới.

Với POST không-idempotent, cả redirect method-preserving và retry đều có thể tạo side effect lặp nếu endpoint đã xử lý một phần. Thiết kế cần idempotency key hoặc transaction semantics khi cần.

## 5. Credential không được đi theo redirect một cách mù quáng

Một HTTP request có thể chứa:

| Vị trí | Ví dụ | Rủi ro |
|---|---|---|
| `Authorization` | `Bearer access-token`, Basic auth | Token/mật khẩu bị đưa tới host khác |
| `Cookie` | `session=opaque-session-id` | Cookie được gửi sai phạm vi hoặc bị copy qua chính sách thủ công |
| Header riêng | `X-API-Key` | Auto copy custom header có thể lộ key |
| POST body | Form password hoặc JSON token | 307/308 có thể truyền lại nguyên body |
| Query/URL | `?access_token=...` | Dễ vào logs, browser history, analytics, Referer |
| `Proxy-Authorization` | Thông tin đăng nhập proxy | Không dành cho origin server |

Một **bearer token** thường trao khả năng hành động cho bên sở hữu nó; vì vậy không chuyển tiếp theo redirect khi chưa kiểm tra đích, audience, scope và chính sách. `Authorization: Basic ...` chỉ dùng Base64 cho user:password: **Base64 không phải mã hóa bảo mật**, phải dùng HTTPS và tránh log.

Chính sách hợp lý:

1. **Same-origin redirect:** có thể cân nhắc giữ credential phù hợp tài nguyên, nhưng origin giống nhau **không tự chứng minh** cùng scope/audience.
2. **Cross-origin redirect:** mặc định **không chuyển** Authorization, Cookie, API key và body nhạy cảm của origin cũ; nếu cần theo, cấp credentials **riêng** cho đích đã được allowlist.
3. **HTTPS → HTTP:** từ chối cho dữ liệu nhạy cảm. Đừng dùng fallback HTTP.
4. **Mỗi hop:** xác minh lại, không chỉ kiểm tra hop đầu.
5. **Log:** chỉ ghi status, sanitized URL, redirect count và lý do policy, **không ghi token/cookie/password**.

Hành vi Java library với header nhạy cảm có thể phụ thuộc phương thức tạo request, implementation và cấu hình cookie/authenticator; đừng dựa vào một giả định chung rằng **mọi custom credential đều được tự động gỡ đúng cách**.

## 6. Java 17 HttpClient.Redirect: NEVER, NORMAL, ALWAYS

`java.net.http.HttpClient` cho phép chọn policy:

| Policy | Java 17 Javadoc | Lưu ý bảo mật |
|---|---|---|
| `HttpClient.Redirect.NEVER` | Không auto redirect, trả response 3xx cho caller | **Dễ kiểm soát** nguồn/đích credential và method |
| `HttpClient.Redirect.NORMAL` | Auto redirect **trừ** HTTPS URL → HTTP URL | Chống downgrade trực tiếp, **không đảm bảo same-origin** |
| `HttpClient.Redirect.ALWAYS` | Auto redirect kể cả HTTPS → HTTP theo policy | Không phù hợp request chứa credential nếu không có bảo vệ bổ sung |

**Mặc định của `HttpClient.newHttpClient()` và builder khi không cấu hình followRedirects là `Redirect.NEVER`.** Java không mặc định hành xử giống browser tự follow mọi 3xx.

~~~java
HttpClient secureClient = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
~~~

Đây là **trích đoạn cấu hình**, cần import `HttpClient` và `Duration`. `Redirect.NORMAL` vẫn có thể theo từ `https://a.example.test` sang `https://b.example.test`, đều dùng HTTPS nhưng **khác origin**. `Redirect.ALWAYS` không bảo đảm giữ bí mật khi xuống HTTP. Với request nhạy cảm, **NEVER + manual validation** minh bạch hơn.

### 6.1. HTTPS downgrade, redirect HTTP→HTTPS và HSTS

HTTP request đầu tiên **không trở thành được bảo vệ hồi tố** khi server trả 301/302 chuyển sang HTTPS. Trên Internet, kẻ can thiệp có thể đọc/chỉnh HTTP hop đầu. Nếu cần HTTPS, hãy đặt URL đầu tiên là `https://` ngay từ ứng dụng.

Trong **browser**, HSTS đã được lưu/preload có thể giúp nâng cấp request trước khi gửi HTTP thật. Không mặc định Java `HttpClient` dùng HSTS cache của browser. Tương tự, `Secure` cookie và chính sách SameSite của browser không thay thế TLS trust configuration của Java.

## 7. Authentication khác authorization

### 7.1. Status HTTP phổ biến

| Status | Ý nghĩa tổng quát | Phản ứng đúng |
|---|---|---|
| **200 OK** | Request thành công theo semantics server | Parse body và kiểm tra nghiệp vụ |
| **301/302/303/307/308** | Có thể điều hướng sang URL khác | Xét Location, method/body và credential policy |
| **401 Unauthorized** | Thiếu/không hợp lệ authentication với resource; thường có `WWW-Authenticate` | Chọn credential đúng server/realm/scope |
| **403 Forbidden** | Server hiểu request nhưng từ chối cho truy cập | Xét permission/scope, không retry mật khẩu vô hạn |
| **407 Proxy Authentication Required** | Proxy yêu cầu xác thực | Dùng proxy auth, không copy sang origin server |
| **404 Not Found** | Resource không có hoặc server muốn che tồn tại | Không suy ra chắc là TLS/auth/redirect |
| **429 Too Many Requests** | Bị rate limit | Dùng backoff theo policy, không coi là redirect |

**TLS server authentication** xác định server theo certificate; **HTTP authentication** xác định người dùng/client; **authorization** quyết định được phép thực hiện thao tác nào. Ba khái niệm có thể cùng xuất hiện trong một request nhưng không thay thế nhau.

### 7.2. HttpClient Authenticator và CookieHandler

Java 17 `HttpClient.Builder.authenticator(...)` cấu hình `java.net.Authenticator` để xử lý các tình huống authentication thích hợp, ví dụ challenge HTTP `401` hoặc proxy `407`. Nó không phải cơ chế tự cấp quyền cho mọi cross-origin redirect.

`HttpClient.Builder.cookieHandler(...)` có thể cấu hình `CookieManager` hoặc CookieHandler để tự quản lý cookie theo quy tắc của handler. Java HttpClient **không phải browser**: đừng giả định mọi `SameSite`, third-party restrictions, CORS preflight, HSTS của Chrome đều được áp dụng.

~~~java
// Trích đoạn: dùng cookie jar khi ứng dụng thật sự cần session cookies.
CookieManager cookies = new CookieManager();
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

`CookieManager` là `java.net.CookieManager`. Với service-to-service API dùng bearer token, thiết kế nên tránh vô tình copy `Cookie` hay `Authorization` từ request trước vào URL đích mới. Một server vẫn phải tự xác thực user/token ở phía nhận; **CORS không phải một lớp authentication**.

## 8. Cookie và same-origin: cẩn thận các phạm vi khác nhau

Browser gửi cookie theo nhiều thuộc tính:

| Thuộc tính cookie | Vai trò |
|---|---|
| `Domain` | Host-only nếu không khai báo; Domain có thể bao gồm subdomain phù hợp |
| `Path` | Giới hạn đường dẫn gửi cookie, **không phải boundary security mạnh** |
| `Secure` | Cookie chỉ được gửi trong ngữ cảnh giao vận bảo mật theo quy tắc user agent |
| `HttpOnly` | Ngăn JavaScript thông thường lấy cookie qua `document.cookie`, nhưng browser vẫn gửi khi phù hợp |
| `SameSite=Strict` | Hạn chế cross-site requests nghiêm ngặt |
| `SameSite=Lax` | Cho phép một số top-level navigation theo tiêu chí; không chặn mọi CSRF |
| `SameSite=None; Secure` | Cho phép một số cross-site contexts tùy cấu hình browser và third-party policy |

**Cookie không được phân vùng theo đúng scheme-host-port giống same-origin policy.** Subdomain cùng registrable domain có thể khác origin nhưng vẫn nhận cookie có Domain phù hợp. Ngược lại, cookie path có thể hạn chế request ngay trong một origin. Vì vậy không thể quyết định “cứ cùng origin thì gửi mọi cookie” hoặc “khác origin chắc chắn không cookie nào được gửi”.

Với browser, CORS áp lên quyền truy cập response của JavaScript; browser vẫn có thể tự gửi một số cookie theo policy trong request cross-site. Với Java backend, phải xem cách CookieHandler cụ thể quản lý cookie và bảo vệ token.

## 9. Quy tắc cho URL/Location do bên không tin cậy quyết định

`URI.resolve` là parser/resolver, **không phải URL security validator**. Với redirect có thể bị attacker điều khiển:

- **Allowlist scheme:** chỉ `https` trong production đối với dữ liệu nhạy cảm; có ngoại lệ rõ ràng cho local test.
- **Allowlist host/port và origin:** so canonical host, effective port, trust purpose; không dùng `endsWith("example.test")` thiếu ranh giới label.
- **Không nhận userinfo trong URL** như `https://user:password@host`.
- **Không để secret trong query**; URL có thể đi qua log/history/Referrer/analytics.
- **Giới hạn redirect count**, vòng lặp URL và tổng timeout.
- **Kiểm soát method/body replay:** nhất là `307/308` và POST với side effect.
- **Đánh giá DNS và IP đích** nếu URL không tin cậy: chặn loopback, link-local, metadata IP, mạng nội bộ trái phép, DNS rebinding và đổi IP sau kiểm tra, với giải pháp tầng mạng phù hợp.
- **Không copy custom headers theo quán tính**; tạo request mới từ dữ liệu được phép.
- **Theo dõi TLS validation** ở từng HTTPS hop, không chỉ hop đầu.

Đây là vấn đề **SSRF** nếu server Java nhận URL tự do và fetch theo redirect. So sánh same-origin một mình không đủ để chống SSRF; nhưng nếu policy là **chỉ same-origin với URL khởi tạo tin cậy**, nó là một lớp giảm rủi ro phù hợp với từng API.

## 10. Quy trình follow redirect thủ công an toàn hơn

Với HTTP client tự quản lý credential:

~~~text
request ban đầu (đúng URL/scheme và token scope)
    |
    v
HttpClient.Redirect.NEVER -> response
    |
    +-- status != redirect được hỗ trợ --> xử lý status/body cuối
    |
    +-- status redirect được hỗ trợ:
            |
            +-- Location có mặt, parse URI
            +-- resolve target dựa trên URI hiện hành
            +-- validate scheme, host, effectivePort, allowlist
            +-- kiểm tra target có đổi origin không
            +-- kiểm tra method và replayable body
            +-- lọc/cấp lại credential đúng phạm vi
            +-- kiểm tra hop/deadline; gửi request mới nếu được phép
~~~

RFC 9110 khuyến cáo cẩn thận khi tự động follow các method không an toàn và xem xét loại bỏ các header nhạy cảm như `Authorization` và `Cookie` khi request chuyển hướng. Mỗi hop có thể thay đổi URL, method và header, nên không giữ nguyên mọi field. Một số header như `Host`/`Origin`/`Referer`/cache validators có ràng buộc riêng của request mới.

Với URL và token nhạy cảm, **deny by default** giúp tránh gửi secret trước khi phát hiện đích không đáng tin. Sau khi duyệt được redirect, chỉ gửi lại credential khi đúng nguyên tắc identity/scope và policy.

## 11. Ví dụ Java 17+ hoàn chỉnh chạy trên loopback

Ví dụ tạo một server HTTP nội bộ bằng module JDK `jdk.httpserver` và Java `HttpClient`; không cần Internet. Nó minh họa **redirect logic**, **không thử nghiệm TLS thực**, vì TLS cần certificate hợp lệ. Token `Bearer LOCAL_DEMO` hoàn toàn giả và chỉ truyền qua HTTP loopback trong ví dụ; **không dùng token thật qua HTTP**.

Kịch bản:

1. `/start` trả `302 Location: /final`. Client dùng `Redirect.NEVER`, tự resolve URL; vì **cùng origin**, chương trình chủ động gửi lại token giả tới `/final`.
2. `/external` trả `302 Location: https://other.example.invalid/landing`. Client phát hiện khác origin, **không thực hiện request nào tới host này**.
3. Dùng `sameOrigin(...)` so sánh scheme/host/effective port; minh họa HTTP và HTTPS cùng hostname vẫn khác origin.

Hàm `sameOrigin` trong ví dụ **chỉ minh họa HTTP(S) URI đã kiểm soát**, không có đủ canonicalization/IDN, DNS/IP checking hoặc trust policy để dùng làm bộ lọc redirect/SSRF production. Nó còn từ chối userinfo như một chính sách an toàn bổ sung; userinfo không phải thành phần của bộ ba origin.

Tạo file **`HttpOriginRedirectDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public class HttpOriginRedirectDemo {
    private static int effectivePort(URI uri) {
        if (uri.getPort() != -1) return uri.getPort();
        if ("https".equalsIgnoreCase(uri.getScheme())) return 443;
        if ("http".equalsIgnoreCase(uri.getScheme())) return 80;
        return -1;
    }

    private static boolean sameOrigin(URI a, URI b) {
        return a.getScheme() != null && b.getScheme() != null
                && a.getHost() != null && b.getHost() != null
                && a.getScheme().equalsIgnoreCase(b.getScheme())
                && a.getHost().equalsIgnoreCase(b.getHost())
                && effectivePort(a) == effectivePort(b)
                && a.getUserInfo() == null && b.getUserInfo() == null;
    }

    private static void redirect(HttpExchange exchange, String location)
            throws IOException {
        exchange.getResponseHeaders().set("Location", location);
        exchange.sendResponseHeaders(302, -1);
        exchange.close();
    }

    private static void respond(HttpExchange exchange, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.US_ASCII);
        exchange.sendResponseHeaders(200, body.length);
        try (var output = exchange.getResponseBody()) {
            output.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        AtomicBoolean receivedCredential = new AtomicBoolean(false);
        server.createContext("/start",
                ex -> redirect(ex, "/final"));
        server.createContext("/final", ex -> {
            receivedCredential.set("Bearer LOCAL_DEMO".equals(
                    ex.getRequestHeaders().getFirst("Authorization")));
            respond(ex, "OK");
        });
        server.createContext("/external",
                ex -> redirect(ex, "https://other.example.invalid/landing"));
        server.start();
        try {
            URI base = new URI("http", null, loopback.getHostAddress(),
                    server.getAddress().getPort(), "/", null, null);
            HttpClient client = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpResponse<String> first = client.send(
                    HttpRequest.newBuilder(base.resolve("start"))
                            .timeout(Duration.ofSeconds(3))
                            .header("Authorization", "Bearer LOCAL_DEMO")
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            URI next = first.uri().resolve(
                    first.headers().firstValue("Location").orElseThrow());
            boolean same = sameOrigin(first.uri(), next);
            if (first.statusCode() != 302 || !same) {
                throw new IOException("Unsafe or unexpected redirect");
            }
            HttpResponse<String> finalResponse = client.send(
                    HttpRequest.newBuilder(next)
                            .timeout(Duration.ofSeconds(3))
                            .header("Authorization", "Bearer LOCAL_DEMO")
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString());

            HttpResponse<String> external = client.send(
                    HttpRequest.newBuilder(base.resolve("external"))
                            .timeout(Duration.ofSeconds(3))
                            .header("Authorization", "Bearer LOCAL_DEMO")
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            URI other = external.uri().resolve(
                    external.headers().firstValue("Location").orElseThrow());
            boolean blocked = !sameOrigin(external.uri(), other);

            System.out.println("redirectPolicy=" + client.followRedirects());
            System.out.println("initialStatus=" + first.statusCode());
            System.out.println("sameOrigin=" + same);
            System.out.println("finalStatus=" + finalResponse.statusCode());
            System.out.println("sameOriginAuth=" + receivedCredential.get());
            System.out.println("crossOriginBlocked=" + blocked);
            System.out.println("httpsDiffersFromHttp=" + !sameOrigin(
                    URI.create("http://example.test/"),
                    URI.create("https://example.test/")));
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+ (module `jdk.httpserver`):

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpOriginRedirectDemo.java
java --add-modules jdk.httpserver HttpOriginRedirectDemo
~~~

**Stdout chính xác đã kiểm chứng trên OpenJDK 24 với `--release 17`:**

~~~text
redirectPolicy=NEVER
initialStatus=302
sameOrigin=true
finalStatus=200
sameOriginAuth=true
crossOriginBlocked=true
httpsDiffersFromHttp=true
~~~

Diễn giải kết quả:

- `redirectPolicy=NEVER`: Java không tự follow 3xx; chính chương trình xử lý Location.
- `initialStatus=302`: request `/start` trả redirect, chưa phải kết quả cuối.
- `sameOrigin=true`: target `/final` cùng scheme/host/effective port.
- `finalStatus=200`: sau kiểm tra, client gửi request mới và server trả thành công.
- `sameOriginAuth=true`: server đã nhận header chứa **token giả** ở endpoint cùng origin.
- `crossOriginBlocked=true`: URL `other.example.invalid` bị xác định khác origin nên không có `client.send` đến host ngoài; **không có yêu cầu Internet**.
- `httpsDiffersFromHttp=true`: khác scheme là khác origin.

Demo chỉ kiểm tra same-origin trước khi follow; trong production còn phải hạn chế scheme đích phải là HTTPS, allowlist host, path/scope credential, DNS/IP, redirect loop và method/body replay. Không dùng `sameOrigin` của demo như tường lửa SSRF hoàn chỉnh.

## 12. Cookie flow, OAuth redirect và token audience

Chuyển hướng khác origin đôi khi **được thiết kế có chủ đích**:

~~~text
Browser -> https://app.example.test/profile
     <- redirect tới https://login.example.test/authorize
Browser -> login.example.test
     <- redirect về callback đã đăng ký tại app.example.test
App     -> kiểm tra state + PKCE/flow rồi xử lý authorization code
~~~

Trong flow OAuth/OIDC, redirect URI cần được đăng ký/kiểm tra chính xác theo chính sách, `state` giúp liên kết request và chống CSRF, PKCE bảo vệ authorization code trong flow thích hợp, issuer/audience/scope và token validation vẫn phải thực hiện theo chuẩn. **Không gửi access token của app sang mọi URL `Location` chỉ vì đó là bước redirect trong login.**

Cookie `SameSite` có thể ảnh hưởng đến việc browser gửi session cookie khi đi qua cross-site flow, nhưng điều đó không biến CORS thành authentication. Java backend không tự áp dụng chính sách browser nếu không triển khai/configure tương ứng.

**Origin** là khái niệm URL; **audience** là đối tượng nhận token hợp lệ; **scope/permission** là quyền. Ba thứ phải xét độc lập.

## 13. Thường gặp khi debug

| Triệu chứng / khẳng định sai | Điều cần hiểu | Cách xử lý |
|---|---|---|
| “HTTPS có certificate hợp lệ nên redirect an toàn” | Certificate xác thực host mới, không cấp quyền nhận credential cũ | Allowlist và đúng token scope |
| “NORMAL chỉ follow cùng origin” | NORMAL chỉ cấm HTTPS→HTTP downgrade | NEVER/manual cho sensitive requests |
| “Cùng domain = cùng origin” | Subdomain/port/scheme có thể khác | So scheme-host-effective port |
| “Cùng IP = cùng origin” | Origin dùng hostname từ URL | Phân biệt DNS/IP khỏi URL identity |
| “Cookie chỉ gửi trong một origin” | Cookie scope khác origin, Domain có thể phủ subdomain | Đọc Domain/Path/Secure/SameSite |
| “CORS bảo vệ server khỏi Java HttpClient” | CORS là browser response-access policy | Server kiểm tra auth và quyền |
| “301/302 giữ nguyên mọi POST” | Client có thể đổi POST sang GET | Theo RFC/client semantics |
| “307/308 bỏ body khi redirect” | Phải giữ method; body có thể được phát lại | Chặn replay body nhạy cảm |
| “304 là redirect sang Location” | 304 dùng conditional cache | Không treat như 302 |
| “Chỉ xóa Authorization là đủ” | Secret còn nằm trong Cookie/custom headers/body/query | Tạo request mới theo allowlist |
| “401 giống 403” | 401 thường authentication, 403 authorization | Xử lý riêng |
| “Basic auth đã mã hóa vì Base64” | Base64 là encoding, không phải encryption | Chỉ dùng qua TLS, tránh log |
| “HTTP→HTTPS 301 khiến HTTP hop đầu an toàn” | Hop đầu HTTP vẫn có thể bị xem/sửa | Bắt đầu ngay với HTTPS |
| “URI.resolve tự chặn redirect xấu” | Resolve chỉ xây URI mới | Validate từng hop và phòng SSRF |
| “Token trong URL query an toàn vì HTTPS” | URL có thể bị log/histories/referrers | Tránh secret trong URL |

## 14. Checklist thiết kế và code review

**Trước request:** URL đầu là HTTPS khi cần bảo mật? Certificate/hostname validation không bị tắt? Token có đúng audience/scope? Timeout, proxy, CookieHandler và redirect policy có được cấu hình rõ? Có cần auto redirect thật không?

**Khi gặp 3xx:** status nào? `Location` relative hay absolute? Target có cùng scheme/host/effective port? Có HTTPS downgrade? Host/port/IP có đúng allowlist? Method/body có bị đổi hoặc replay? Có Authorization, Cookie, custom API key, query token hay POST password không? Có hop limit và tổng deadline không?

**Sau response:** Status cuối và URL thực sự xử lý là gì (ví dụ `HttpResponse.uri()`)? Có bất kỳ 401/403/407 chưa xử lý không? Cookie có đúng phạm vi? CORS có liên quan tới browser caller hay không? Log có vô tình ghi token/password/URL query nhạy cảm không?

## 15. Tự kiểm tra

**1. `https://example.test/a` và `https://example.test/b` có cùng origin không?** Có, chỉ khác path.

**2. `https://example.test` và `https://example.test:8443`?** Không, vì effective port 443 khác 8443.

**3. `http://example.test` và `https://example.test`?** Không, khác scheme.

**4. HTTPS có mặc định xác thực người dùng cuối không?** Không. TLS server authentication khác HTTP authentication.

**5. Java 17 HttpClient mặc định tự follow redirect?** Không, mặc định `Redirect.NEVER`.

**6. `Redirect.NORMAL` có chặn sang HTTPS host khác không?** Không. Nó chặn HTTPS→HTTP nhưng không có ràng buộc same-origin.

**7. POST 307 có được đổi thành GET?** Không. Redirect 307 giữ method, nên phải cẩn trọng với body.

**8. POST 302 ở Java 17 có thể thành GET khi auto follow?** Có theo implementation note Java 17.

**9. `Location: /v2` là URL tuyệt đối chưa?** Chưa; cần resolve trên URI gốc.

**10. 401 khác 403 ở đâu?** 401 thường yêu cầu xác thực hợp lệ; 403 là bị từ chối quyền truy cập.

**11. Cookie có cùng luật origin như CORS không?** Không; cookie Domain/Path/SameSite theo luật khác.

**12. Java backend có bị browser CORS chặn khi dùng HttpClient?** Không; nó tự quyết định gọi URL và cấp credentials.

**13. Khi redirect sang host khác có nên copy bearer token cũ?** Không mặc định; chỉ cấp credentials đúng đích sau policy/authorization.

**14. Nếu 307 redirect body chứa mật khẩu sang host khác thì sao?** Có nguy cơ lộ mật khẩu nếu follow; phải chặn hoặc xác minh đích/method/body chặt chẽ.

**15. Demo có kết nối tới `other.example.invalid` không?** Không. Nó chỉ resolve Location và từ chối follow cross-origin.

## 16. Tài liệu tham khảo

- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client builder, SSL context, Authenticator/CookieHandler, default redirect behavior.
- [Java SE 17 – HttpClient.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): `NEVER`, `NORMAL`, `ALWAYS` và ghi chú method POST/301/302.
- [Java SE 17 – HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request builder, headers, method, timeout.
- [Java SE 17 – HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): URI, status, headers và body.
- [Java SE 17 – URI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): URI parser, scheme/host/port, `resolve`.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server loopback demo.
- [RFC 6454 – The Web Origin Concept](https://www.rfc-editor.org/rfc/rfc6454): bộ ba scheme-host-port.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): redirects, Location, authentication và HTTP status.
- [RFC 9700 – OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): redirect với dữ liệu xác thực.
- [MDN – Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy): origin và chính sách browser.
- [MDN – Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Domain/Path/Secure/HttpOnly/SameSite.

**Ghi nhớ:** HTTPS bảo vệ **kết nối TLS**, không biến mọi redirect thành đáng tin. Origin là **scheme + host + effective port**, không chỉ hostname hoặc IP. HTTP 3xx có thể thay đổi origin, method hoặc việc gửi lại body. Credentials phải chỉ được dùng tại đúng đích và phạm vi quyền. Với Java 17, `HttpClient.Redirect.NEVER` và kiểm soát từng `Location` giúp tránh chuyển token mù quáng; `Redirect.NORMAL` chặn downgrade HTTPS→HTTP nhưng **không phải cùng-origin policy**.
