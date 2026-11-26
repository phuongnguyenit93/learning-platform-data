# Xác minh đích redirect và dữ liệu saved request

## Mục tiêu và phạm vi

Người dùng mở một trang cần đăng nhập, bị chuyển tới form login, đăng nhập thành công và muốn quay lại trang ban đầu. Đây là một trải nghiệm phổ biến của ứng dụng Spring Security. Tuy nhiên, đường đi này kéo theo **hai loại dữ liệu dễ bị nhầm là đáng tin**: đích redirect sau xác thực và **saved request** được lưu trước xác thực.

Một ứng dụng có thể xác thực đúng mật khẩu, chống CSRF và bảo vệ session nhưng vẫn tạo **open redirect** nếu cho phép tham số returnUrl, Referer hoặc một URL được ghi vào session quyết định đích điều hướng mà không kiểm tra. Lỗi nghiêm trọng hơn xuất hiện nếu URL chứa mã xác thực, token, dữ liệu cá nhân hoặc có thể bị điều khiển qua Host/Forwarded headers ở reverse proxy.

Bài thuộc chương **Đăng nhập và đăng xuất** trong module **SPRING_SECURITY_HTTP_PROTECTION**. Mục tiêu của module là cấu hình các lớp bảo vệ HTTP và trình duyệt trong Spring Security — CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và session — cho cả **Servlet** và **Reactive**, đồng thời chẩn đoán các xung đột khi triển khai.

Sau khi học, bạn có thể:

1. Diễn giải **ExceptionTranslationFilter, AuthenticationEntryPoint, RequestCache, SavedRequestAwareAuthenticationSuccessHandler** và **RequestCacheAwareFilter** trong Servlet.
2. Phân biệt **URL được lưu, response redirect và request browser thực sự phát sau redirect**; nhận biết vì sao POST/body không được tự động phát lại.
3. Xác định những trường trong saved request có thể bắt nguồn từ **client chưa xác thực**.
4. Chống **open redirect, URL parsing bypass, Host header poisoning, query-string leakage và login CSRF**.
5. Thiết kế **allowlist đích điều hướng** với origin cố định, path rõ ràng, query có kiểm soát và fallback an toàn.
6. Cấu hình **HttpSessionRequestCache**, request matcher và login success handler trong Spring Security Servlet.
7. Hiểu cơ chế tương đương **ServerRequestCache/WebSessionServerRequestCache** và redirect success handler trong WebFlux.
8. Phân biệt saved request sau login với **OAuth2/OIDC state, authorization request repository, redirect_uri và post-logout redirect**.
9. Viết kiểm thử MockMvc, WebTestClient và browser test cho ranh giới redirect/session/CSRF/proxy.
10. Chẩn đoán trường hợp login xong về nhầm trang, redirect ra website lạ, mất query, vòng lặp login, 403 hoặc URL nội bộ bị lộ.

## 1. Vấn đề thực tế: login xong quay về đâu?

Một ứng dụng có URL bảo vệ:

~~~text
https://accounts.example.com/app/orders
~~~

Người chưa đăng nhập truy cập URL này. Spring Security có thể chuyển người đó tới trang login rồi đưa họ quay lại sau xác thực:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security
    participant R as Session / RequestCache

    B->>S: GET /app/orders (chưa đăng nhập)
    S->>R: Lưu request cần xác thực
    S-->>B: 302 Location: /login
    B->>S: GET /login
    S-->>B: HTML form + CSRF token
    B->>S: POST /login + credential + CSRF token
    S->>S: Authentication thành công
    S->>R: Đọc saved request
    S-->>B: 302 Location: /app/orders
    B->>S: GET /app/orders
    S->>S: Kiểm tra session và authorization
    S-->>B: Nội dung chỉ khi user có quyền
~~~

Đó là **hành vi điều hướng sau login**, không phải một cơ chế cấp quyền mới. URL /app/orders vẫn phải được Spring Security và tầng nghiệp vụ kiểm tra quyền sau khi redirect.

### 1.1. Nếu đích redirect do attacker kiểm soát?

Giả sử ứng dụng tự thêm:

~~~http
POST /login HTTP/1.1
Host: accounts.example.com
Content-Type: application/x-www-form-urlencoded

username=learner&password=...&returnTo=https%3A%2F%2Foutside.test%2Fsignin
~~~

Nếu thành công rồi trả:

~~~http
HTTP/1.1 302 Found
Location: https://outside.test/signin
~~~

thì người dùng có thể được điều hướng ra website bên ngoài ngay sau khi đăng nhập. Đây là một dạng **open redirect** nếu ứng dụng không có chính sách cho phép đích đó.

Rủi ro có thể gồm phishing dưới tên miền uy tín, làm người dùng hiểu nhầm bước xác thực, hoặc hỗ trợ những chuỗi tấn công khác. **Open redirect không tự chứng minh cookie HttpOnly của ứng dụng bị gửi sang outside.test**: browser chỉ gửi cookie theo Domain/Path/SameSite/Secure. Tuy nhiên, nếu URL, Referer hoặc query mang thông tin nhạy cảm, redirect vẫn có thể gây lộ dữ liệu trong một số luồng.

### 1.2. Saved request không phải “quyền quay lại bất kỳ nơi nào”

**Saved request** là bản mô tả request người dùng muốn thực hiện trước khi bị yêu cầu xác thực. Nó được lưu nhằm khôi phục trải nghiệm điều hướng, **không phải xác nhận URL hoặc các tham số đó an toàn**.

Nguyên tắc trung tâm:

> **Dữ liệu được đưa vào session sau khi nhận từ client vẫn cần được kiểm tra theo ranh giới tin cậy ban đầu.** “Nằm trong session” không tự biến một URL do client ảnh hưởng thành URL đáng tin.

### 1.3. Hai câu hỏi độc lập

- **Được điều hướng tới đích này không?** Xác minh origin, path, scheme, query, business context và mục đích sau login.
- **Được xem tài nguyên tại đích đó không?** Authorization vẫn phải được kiểm tra trên request GET mới, không dựa vào việc login success handler đã redirect.

Một user được phép đăng nhập nhưng không có quyền xem đơn hàng của người khác **phải nhận 403/404 theo policy** tại /app/orders/{id}, dù URL nằm trong saved request của chính session đó.

## 2. Saved request trong Spring Security Servlet hoạt động ra sao?

### 2.1. Các thành phần cần nhận diện

| Thành phần | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| **ExceptionTranslationFilter** | Chuyển tình huống cần authentication/access denied thành quy trình entry point phù hợp. | AuthenticationManager hoặc authorization policy. |
| **AuthenticationEntryPoint** | Khởi động luồng xác thực, thường redirect đến /login khi request từ browser chưa xác thực. | Login success handler. |
| **RequestCache** | Lưu, tìm, bỏ request được ghi nhớ theo cơ chế đã chọn. | Cache HTTP response hoặc CDN. |
| **HttpSessionRequestCache** | Một implementation RequestCache lưu saved request trong HttpSession. | Session authentication state. |
| **SavedRequest / DefaultSavedRequest** | Mô tả request cũ và URL redirect được hình thành từ request đó. | Request đã được browser gửi lại. |
| **SavedRequestAwareAuthenticationSuccessHandler** | Sau login thành công, có thể chọn URL từ saved request để redirect. | Trình thực thi POST/body cũ. |
| **SimpleUrlAuthenticationSuccessHandler** | Điều hướng theo default target, tham số target hoặc Referer khi được cấu hình. | Bộ xác minh URL đích tự động cho mọi nguồn dữ liệu. |
| **RequestCacheAwareFilter** | Có thể nhận diện request quay lại và cung cấp wrapper với thông tin cached theo cấu hình. | Replay engine cho mọi HTTP method. |
| **RedirectStrategy** | Thực hiện redirect HTTP. | URL allowlist/authorization. |
| **SecurityContextRepository** | Lưu thông tin Authentication sau khi login. | Kho saved request hoặc token CSRF. |

Spring Security có thể tự lắp ráp các thành phần này qua DSL; không nên vừa thay một thành phần rồi mặc nhiên cho rằng các thành phần còn lại đã dùng đúng cấu hình mới.

### 2.2. Luồng Servlet theo từng bước

~~~text
1. GET /app/orders
   ├─ Chưa có authenticated principal
   └─ Access policy yêu cầu login

2. ExceptionTranslationFilter
   ├─ Có thể gọi RequestCache.saveRequest(...)
   └─ AuthenticationEntryPoint trả redirect /login

3. HttpSessionRequestCache
   └─ Lưu DefaultSavedRequest theo session

4. POST /login
   ├─ CsrfFilter xác minh CSRF token (nếu bật)
   ├─ Authentication filter / AuthenticationManager
   └─ Authentication success handler chạy khi đăng nhập thành công

5. SavedRequestAwareAuthenticationSuccessHandler
   ├─ Đọc saved request
   ├─ Nếu có điều kiện override/default target thì theo cấu hình
   └─ Nếu chọn saved request, gửi HTTP redirect tới URL lưu

6. Browser theo Location
   └─ Phát GET mới tới đích, mang cookie nếu được phép

7. Security filters + resource authorization
   └─ Kiểm tra quyền đối với request mới
~~~

**Chi tiết có thể khác theo phiên bản, matcher, filter chain và authentication mechanism.** Ví dụ access denied của một user đã authenticated không nhất thiết được đưa về login bằng cùng cách với anonymous. Một API thường nên trả **401/403**, không redirect HTML login như browser navigation.

### 2.3. SavedRequest thường chứa gì?

Tùy implementation/phiên bản, request đã lưu có thể chứa:

- URL đầy đủ hoặc các thành phần **scheme, host, port, request URI, query string**.
- HTTP method.
- Một số request parameters và metadata/header liên quan.
- Thông tin Servlet path/context path.
- Locale/cookie/headers được capture bởi implementation.

Một **DefaultSavedRequest** không chỉ là chuỗi path bất biến. Điều nguy hiểm là các trường được snapshot **từ request của client trước xác thực**, nên có thể bị ảnh hưởng bởi query string, Host, Forwarded headers, route và cookie/header policy.

**Không dùng saved request như object đã được kiểm chứng danh tính, quyền, sự đồng ý hoặc tính toàn vẹn nghiệp vụ.**

### 2.4. Saved request không phát lại POST body

Ví dụ user đang điền biểu mẫu thanh toán nhưng session hết hạn:

~~~http
POST /checkout HTTP/1.1
Content-Type: application/json

{"orderId":123,"confirm":true}
~~~

Nếu request này bị yêu cầu login, **không nên kỳ vọng SavedRequestAwareAuthenticationSuccessHandler sẽ tự gửi lại POST JSON sau login**. Redirect HTTP thông thường dẫn browser đến một URL, thường thông qua GET khi đi theo redirect login success. Server không tự tái tạo một mutation có thể gây thanh toán hai lần.

Cách làm an toàn hơn:

1. Giữ **bản nháp** theo quy trình được thiết kế, không lưu credential hoặc secret trong saved request.
2. Sau login, redirect đến trang **xem lại /checkout/review** bằng GET.
3. Tái kiểm tra **authorization**, giá/giỏ hàng, CSRF token và session mới.
4. Yêu cầu **người dùng xác nhận lại** mutation bằng POST với CSRF token hợp lệ.
5. Với thanh toán/đặt đơn, dùng **idempotency key** hoặc bảo vệ giao dịch khỏi xử lý lặp.

Ngay cả khi một request wrapper có thể khôi phục một số parameters cho request GET trùng khớp, điều đó **không biến request cache thành hàng đợi lệnh nghiệp vụ**.

### 2.5. Browser fragment không nằm trong HTTP request

URL:

~~~text
https://accounts.example.com/app/orders#tab=history
~~~

Phần sau ký tự **#** là fragment thường do browser quản lý, **không được gửi trong HTTP request-target** tới server. Server-side RequestCache vì thế không thể đáng tin cậy lưu fragment từ request ban đầu chỉ bằng HTTP request mà nó nhận.

Nếu SPA cần giữ route fragment, dùng state/navigation do frontend kiểm soát với allowlist và cơ chế chống tampering/collision phù hợp; đừng giả định fragment đã nằm trong DefaultSavedRequest.

## 3. Một nguồn dữ liệu không tin cậy có thể đi qua nhiều bước

### 3.1. Trust boundary của URL nguồn

~~~mermaid
flowchart LR
    U["Untrusted request: Host/path/query"] --> C["SavedRequest trong HttpSession"]
    C --> H["Authentication success handler"]
    H --> R["Location header"]
    R --> B["Browser navigation"]
    P["Trusted config: origin/path allowlist"] --> V{"Validate destination"}
    C --> V
    V -->|Allowed| H
    V -->|Denied| F["Fixed safe fallback"]
    F --> R
~~~

Điều quan trọng không phải chỉ là **đường dẫn đang ở đâu** mà là **ai có thể ảnh hưởng đến giá trị đó**. Session có thể bảo vệ nó khỏi việc user trực tiếp sửa trên một request khác, nhưng nguồn gốc ban đầu vẫn là client request.

### 3.2. Phân loại nguồn thường gặp

| Nguồn của đích redirect | Mức tin cậy mặc định | Vấn đề chính |
| --- | --- | --- |
| **Giá trị cố định từ cấu hình server** | Tương đối tin cậy nếu cấu hình được kiểm soát. | Sai origin/deploy env hoặc đường dẫn không còn hợp lệ. |
| **SavedRequest.getRedirectUrl()** | **Cần validate** theo chính sách. | Nguồn URL được hình thành từ request trước auth. |
| **returnTo / next / redirect_url query param** | **Untrusted**. | Open redirect, query injection, external schemes. |
| **targetUrlParameter của success handler** | **Untrusted** nếu lấy trực tiếp từ request. | Có thể được ưu tiên hơn saved request theo cấu hình. |
| **Referer header** | **Untrusted**. | Có thể thiếu, bị thay đổi hoặc giả bằng nonbrowser client. |
| **Host / X-Forwarded-Host / Forwarded** | Chỉ tin sau trusted proxy/host validation. | Host header poisoning, dựng absolute URL sai. |
| **Tenant slug / workspace ID từ URL** | Dữ liệu nghiệp vụ cần xác minh. | Điều hướng tới tenant khác hoặc tạo link gây nhầm. |
| **OAuth2 redirect_uri / state** | Theo quy tắc giao thức/registration riêng. | Không thể lấy một URL login callback tùy ý thay registered redirect URI. |
| **Fragment hoặc state SPA trong browser** | Untrusted cho quyết định bảo mật server. | Client-controlled navigation, XSS/URL parsing. |

### 3.3. Tính “internal” của URL không đủ

Một URL **cùng origin** vẫn có thể không được phép dùng làm đích sau login:

~~~text
/app/orders               → trang người dùng thông thường
/admin/users              → trang quản trị; phải authz riêng
/logout                   → không nên là đích redirect tùy ý
/login                    → có thể tạo vòng lặp login
/oauth2/authorization/... → có thể khởi động luồng SSO mới
/actuator/...             → không phải trang giao diện người dùng
/api/delete?confirm=true  → action-bearing URL nguy hiểm nếu server xử lý GET sai
~~~

Allowlist cần xét **mục đích điều hướng**, không chỉ kiểm tra rằng hostname khớp. Authorization vẫn là rào chắn riêng; hạn chế redirect giúp giảm bề mặt gây nhầm lẫn, loop và chuỗi tấn công.

## 4. Các cách open redirect và làm sai đích saved request

### 4.1. Redirect tới URL tuyệt đối khác origin

~~~text
?returnTo=https://outside.test/phishing
~~~

Nếu backend chuyển nguyên chuỗi này thành Location, user rời khỏi domain sau login.

**Phòng vệ:** không đưa input trực tiếp vào Location. Dùng route cố định hoặc validate **scheme+host+port+path** với cấu hình trusted.

### 4.2. URL bắt đầu bằng hai dấu gạch chéo

~~~text
?returnTo=//outside.test/signin
~~~

Chuỗi bắt đầu **//** có thể là **network-path reference**: browser hiểu host là outside.test và lấy scheme từ trang hiện tại. Chỉ kiểm tra “bắt đầu bằng /” **không đủ** để kết luận redirect là internal.

### 4.3. Backslash, percent encoding và nhiều lớp decoding

Ví dụ nguy hiểm nếu validation và redirect library hiểu URL khác nhau:

~~~text
/\outside.test
/%2f%2foutside.test
/%5coutside.test
/%252f%252foutside.test
/app/%2e%2e/admin
~~~

Không khẳng định mọi payload trên đều được browser/server cụ thể chấp nhận. Ý nghĩa là **các tầng URL parser, proxy, HTTP firewall và browser có thể diễn giải/chuẩn hóa khác nhau**. Một validator tự viết kiểu substring hoặc startsWith dễ bỏ sót.

Phòng vệ ưu tiên:

- **Route ID/enum cố định** thay vì URL tùy ý.
- URI parser chuẩn kết hợp **allowlist chính xác**.
- Chỉ dùng path an toàn có định dạng canonical đã xác định.
- Không giải mã nhiều lần hoặc nối chuỗi rồi validate ở một dạng và redirect bằng dạng khác.
- Kiểm thử thực tế trên browser/proxy/runtime dùng trong production.

### 4.4. Host header poisoning trong saved request

Một request có header Host bị kiểm soát tại một tầng cấu hình sai:

~~~http
GET /app/orders HTTP/1.1
Host: outside.test
~~~

Nếu server dựng absolute saved URL từ host mà nó nhận, bản ghi có thể chứa:

~~~text
http://outside.test/app/orders
~~~

Sau khi login, success handler có thể đưa URL này vào Location nếu không có kiểm tra đích và ranh giới proxy.

Một trường hợp khác: client giả **X-Forwarded-Host** hoặc **Forwarded: host=...**. Nếu backend tin forwarded headers không do proxy đáng tin tạo, URL được tính ra có thể mang domain của attacker.

**Không dùng request.getServerName() hoặc giá trị Host của request chưa xác minh làm allowlist nguồn**. Chọn **public origin từ cấu hình triển khai** và giới hạn Host/Forwarded ở edge.

### 4.5. Tham số targetUrlParameter

Một success handler được tùy chỉnh như sau có thể tạo rủi ro:

~~~java
SavedRequestAwareAuthenticationSuccessHandler handler =
        new SavedRequestAwareAuthenticationSuccessHandler();
handler.setTargetUrlParameter("returnTo");
~~~

Đây **chưa phải cấu hình an toàn nếu request.getParameter("returnTo") do client quyết định**. Tùy logic handler, targetUrlParameter có thể được ưu tiên khi có giá trị. Không tự coi việc setter do Spring Security cung cấp là bằng chứng URL đã được allowlist.

### 4.6. Dùng Referer như URL quay về

Trong một số login handler, developer bật:

~~~java
handler.setUseReferer(true);
~~~

**Referer không phải nguồn xác thực đích**. Browser có thể không gửi Referer do Referrer-Policy, có thể thay đổi bởi luồng chuyển trang, và HTTP client ngoài browser có thể tự đặt header. Nếu dùng để cải thiện UX, phải qua **cùng đích allowlist**; với kịch bản nhạy cảm nên không dùng Referer để chọn redirect sau login.

### 4.7. URL/query mang token nhạy cảm

URL đã được saved có thể chứa:

~~~text
/app/activate?token=secret
/callback?code=oauth-code&state=...
/password/reset?token=secret
/app/report?apiKey=secret
~~~

Nếu những URL này đi qua login success, browser history, Location, logs, analytics, trace hoặc referrer policy có thể giữ lại bí mật. **Không nên cache/copy một cách rộng các login callbacks, reset links, authorization code hoặc credential-bearing queries.**

Ưu tiên tránh secrets trong URL khi có thể; với các flow buộc dùng token trong URL, áp dụng thời hạn/mục đích/chống replay, bảo vệ Referrer-Policy, log scrubbing và **không sao chép sang mục đích redirect khác**.

### 4.8. URL nội bộ không đồng nghĩa quyền truy cập hợp lệ

Giả sử request được lưu là **GET /admin/users**. User đăng nhập thành công nhưng không có vai trò admin. Spring Security **vẫn phải từ chối trang quản trị** sau redirect theo authorization rules.

Success handler không được coi sự tồn tại của saved request hoặc authentication thành công là quyền nâng cấp truy cập.

## 5. Chính sách đích redirect trước khi viết code

Không có một regular expression đơn lẻ thay thế việc định nghĩa **đích nào thực sự được phép**. Chính sách an toàn cần tách **source policy**, **URL validation**, **business constraints** và **fallback**.

### 5.1. Ưu tiên route ID thay vì URL tùy ý

Nếu ứng dụng chỉ cần quay về ba trang, đừng nhận một chuỗi URL tự do:

~~~text
postLoginTarget=home
postLoginTarget=orders
postLoginTarget=profile
~~~

Server ánh xạ:

| ID đã biết | Đích cố định do server kiểm soát |
| --- | --- |
| **home** | /app |
| **orders** | /app/orders |
| **profile** | /app/profile |
| Thiếu hoặc không hợp lệ | /app |

Client chỉ được chọn từ một tập hữu hạn, không đưa URL trực tiếp vào Location. Route sau redirect vẫn cần **authorization**; ID "orders" không phải quyền đọc mọi đơn hàng.

### 5.2. Khi cần URI: kiểm tra từng thành phần

Đối với URL tuyệt đối:

1. Parse bằng **URI parser**, không nối chuỗi hay chỉ dùng contains/startsWith.
2. Chỉ cho phép scheme cần thiết, thường **https** trong production.
3. So sánh **host chính xác với allowlist từ cấu hình server**, không lấy expected host từ request Host.
4. Kiểm tra **port**, userinfo, opaque URI, fragment và scheme nguy hiểm như javascript:, data:, file:.
5. Chỉ cho phép **path canonical và có mục đích điều hướng**.
6. Bỏ query hoặc allowlist key/value, giới hạn chiều dài và số tham số.
7. Không validate một dạng URI rồi redirect dạng khác sau decoding/normalization.
8. Chỉ chuyển Location thành **URL/path an toàn do server dựng lại**.
9. Nếu không đạt bất cứ kiểm tra nào, dùng **fallback cố định**.
10. Khi mở rộng nhiều origin, allowlist phải đến từ **trusted configuration** và từng destination có quyền sử dụng rõ ràng.

Đối với path tương đối, **không mặc định chấp nhận mọi chuỗi bắt đầu bằng /**. Phải xét network-path reference dạng //host, backslash, control characters, encoding, context path và sự khác nhau giữa URI parsers.

### 5.3. Origin đáng tin từ cấu hình triển khai

~~~yaml
app:
  public-origin: https://accounts.example.com
  post-login:
    default-path: /app
    allowed-paths:
      - /app
      - /app/orders
      - /app/profile
~~~

Đây là **YAML minh họa application config**, Spring Security không tự đọc các fields này. Ứng dụng phải bind/validate chúng nếu dùng.

**Không dùng request.getServerName() để hình thành trusted origin allowlist.** Host có thể bị ảnh hưởng bởi request hoặc proxy. Staging và production cần **cấu hình public origin tách biệt**, không đổi thành tin mọi host cho tiện kiểm thử.

### 5.4. Query string cần hợp đồng riêng

Nếu cần quay lại trang tìm kiếm:

~~~text
/app/orders?status=pending&page=2
~~~

có thể chỉ chấp nhận **status** thuộc tập hữu hạn và **page** là số nguyên trong phạm vi. Bỏ key lạ, chuẩn hóa rồi encode lại bằng URI builder. Không copy token, code, session ID, apiKey hoặc redirect_uri từ query cũ.

Nếu cần giữ trạng thái phức tạp, cân nhắc **opaque navigation-state ID** gắn với session và TTL thay vì URL chứa mọi dữ liệu. Với ứng dụng bảo mật cao, chỉ cho phép **path không query** là lựa chọn đơn giản nhất.

### 5.5. Method và session là hai tiêu chí chính sách

Chỉ lưu **GET tới các trang hiển thị** theo policy. Không lưu POST/PUT/PATCH/DELETE rồi tự phát lại request sau login. GET phải tuân thủ HTTP safe-method semantics; một GET có side effect nghiệp vụ cũng cần sửa.

Saved request gắn với vòng đời session/cache, có thể mất khi cookie bị chặn, session hết hạn, đổi session ID/strategy, logout, Spring Session eviction hoặc nhiều tab cùng lưu. **Không có saved request là tình huống bình thường**, cần fallback.

### 5.6. Cùng origin không phải lúc nào cũng được phép

~~~text
/app/orders               → trang giao diện phù hợp
/admin/users              → quyền admin riêng, không nên tự chọn là target
/logout                   → không phải đích bất kỳ
/login                    → có nguy cơ redirect loop
/oauth2/authorization/x   → khởi động login flow mới
/actuator/...             → không phải navigation target
~~~

Một đích trùng hostname với ứng dụng vẫn có thể sai về mục đích hoặc dẫn tới hành vi ngoài dự kiến. Allowlist path và authorization phải được đánh giá độc lập.

## 6. Servlet: RequestCache và success handler có hai chiến lược

**Chiến lược A** bỏ tính năng quay lại URL trước login, luôn chuyển tới route cố định. **Chiến lược B** giữ saved request nhưng chỉ lưu những route đã chọn và xác minh URL trước redirect.

Không ghép cả hai cấu hình thành nhiều SecurityFilterChain trùng matcher; hãy chọn một phương án cho ứng dụng.

### 6.1. Phương án A — luôn tới /app

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class FixedSuccessServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .defaultSuccessUrl("/app", true)
                        .permitAll())
                .csrf(Customizer.withDefaults())
                .requestCache(cache -> cache.disable())
                .build();
    }
}
~~~

- **defaultSuccessUrl("/app", true)** chọn đích cố định kể cả khi có saved request.
- **requestCache disable** loại bỏ nhu cầu lưu URL gốc phục vụ login.
- POST /login vẫn cần CSRF token với cấu hình đang bật; permitAll chỉ ảnh hưởng authorization.
- Nếu dùng **loginPage("/login")**, ứng dụng cung cấp GET /login cùng template/token hợp lệ.
- URL /app sau redirect vẫn phải kiểm tra quyền theo SecurityFilterChain.
- Cấu hình không tự loại bỏ open redirect tại các controller khác, ví dụ /go?next=... .

### 6.2. Phương án B — chỉ lưu GET vào route cố định

~~~java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Configuration
class RestrictedSavedRequestConfiguration {

    private static final Set<String> RETURNABLE_PATHS =
            Set.of("/app", "/app/orders", "/app/profile");

    @Bean
    RequestCache restrictedRequestCache() {
        HttpSessionRequestCache cache = new HttpSessionRequestCache();

        cache.setRequestMatcher(request -> {
            if (!"GET".equals(request.getMethod())) {
                return false;
            }

            String contextPath = request.getContextPath();
            String requestUri = request.getRequestURI();

            if (!requestUri.startsWith(contextPath)) {
                return false;
            }

            String path = requestUri.substring(contextPath.length());

            return RETURNABLE_PATHS.contains(path)
                    && request.getQueryString() == null;
        });

        return cache;
    }
}
~~~

Policy này chỉ lưu ba GET routes không có query. Không nhận wildcard /app/** vì có thể chứa các đường không muốn dùng làm redirect. Tầng HTTP firewall/proxy phải thống nhất về URL normalization. Nếu muốn deep links có query/order ID, cần một policy có type/allowlist và kiểm thử riêng.

Lưu request có thể tạo **anonymous HttpSession**. Đừng cấu hình không cho tạo session nếu ứng dụng cần saved request trước login mà chưa có session; thay vào đó đánh giá chi phí session, TTL và giới hạn lạm dụng ở edge.

### 6.3. Nối RequestCache vào HttpSecurity

~~~java
// Trong cấu hình SecurityFilterChain sử dụng bean đã tạo:
http.requestCache(cache -> cache.requestCache(restrictedRequestCache));
~~~

Nếu sử dụng custom success handler, phải đưa **cùng instance RequestCache** vào handler. Chỉ cấu hình cache hẹp chưa phải xác minh toàn diện saved URL trước khi phát Location, bởi các thành phần host/scheme có thể chịu ảnh hưởng proxy cấu hình sai.

### 6.4. SavedRequestAwareAuthenticationSuccessHandler

~~~java
import org.springframework.security.web.authentication
        .SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.RequestCache;

SavedRequestAwareAuthenticationSuccessHandler handler =
        new SavedRequestAwareAuthenticationSuccessHandler();

handler.setRequestCache(restrictedRequestCache);
handler.setDefaultTargetUrl("/app");
~~~

Handler có thể chọn **saved.getRedirectUrl()** khi có saved request và không có cấu hình khác ưu tiên. **defaultTargetUrl** chỉ là fallback, không đồng nghĩa “bỏ qua saved request”.

Muốn luôn về fixed route:

~~~java
handler.setAlwaysUseDefaultTargetUrl(true);
~~~

### 6.5. targetUrlParameter và Referer có thể bị điều khiển

~~~java
// KHÔNG bật các lựa chọn này khi chưa có chính sách validate.
handler.setTargetUrlParameter("next");
handler.setUseReferer(true);
~~~

Một query parameter **next** được client gửi tới POST /login có thể được ưu tiên so với saved request tùy success handler. Referer có thể thiếu do Referrer-Policy, hoặc bị giả trong HTTP client ngoài browser. Không coi các setter của Spring Security là URL sanitizer.

### 6.6. Spring Security 6 và tham số continue

Một số cấu hình/phiên bản Spring Security 6 dùng cơ chế **matching-request parameter** (thường tên **continue**) để tránh truy cập saved request trong session ở mọi request.

Phân biệt:

- **continue** có thể là dấu hiệu để RequestCacheAwareFilter kiểm tra một saved request đang chờ, **không phải URL đích được allowlist**.
- **SavedRequest.getRedirectUrl()** là URL mà success handler có thể chọn.
- **setMatchingRequestParameterName** không đồng nghĩa với **setTargetUrlParameter**.
- Khi custom redirect/matcher/cache, cần kiểm thử save → login → redirect → cleanup theo **phiên bản Spring Security thực tế**. Không tự nối ?continue hoặc nhầm nó với một security token.

## 7. Servlet: success handler chỉ redirect tới saved request đã xác minh

Mẫu dưới đây giữ UX quay về trang cũ nhưng **chỉ cho ba path nội bộ được duyệt**. URL được đọc từ RequestCache, kiểm tra origin và path, rồi **chuyển thành path cố định do server kiểm soát**.

### 7.1. VerifiedSavedRequestSuccessHandler

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Set;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.WebAttributes;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.RequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;

public final class VerifiedSavedRequestSuccessHandler
        implements AuthenticationSuccessHandler {

    private static final String PUBLIC_HOST = "accounts.example.com";
    private static final String DEFAULT_PATH = "/app";
    private static final Set<String> ALLOWED_PATHS =
            Set.of("/app", "/app/orders", "/app/profile");

    private final RequestCache requestCache;

    public VerifiedSavedRequestSuccessHandler(RequestCache requestCache) {
        this.requestCache = requestCache;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        SavedRequest saved = requestCache.getRequest(request, response);

        // Không tái dùng request cũ cho lần đăng nhập tiếp theo.
        requestCache.removeRequest(request, response);

        HttpSession session = request.getSession(false);
        if (session != null) {
            session.removeAttribute(
                    WebAttributes.AUTHENTICATION_EXCEPTION);
        }

        String safePath = selectSafePath(saved);

        // Chuyển POST /login thành điều hướng GET tới trang đích.
        response.setStatus(HttpServletResponse.SC_SEE_OTHER);
        response.setHeader("Cache-Control", "no-store");

        // Chỉ path literal, không còn query hoặc URL chưa được xác minh.
        response.setHeader(
                "Location", request.getContextPath() + safePath);
    }

    private String selectSafePath(SavedRequest saved) {
        if (saved == null || saved.getRedirectUrl() == null) {
            return DEFAULT_PATH;
        }

        try {
            URI uri = new URI(saved.getRedirectUrl());

            if (!"https".equalsIgnoreCase(uri.getScheme())) {
                return DEFAULT_PATH;
            }
            if (!PUBLIC_HOST.equalsIgnoreCase(uri.getHost())
                    || uri.getPort() != -1
                    || uri.getRawUserInfo() != null
                    || uri.getRawQuery() != null
                    || uri.getRawFragment() != null) {
                return DEFAULT_PATH;
            }

            String path = uri.getRawPath();

            return ALLOWED_PATHS.contains(path)
                    ? path
                    : DEFAULT_PATH;

        } catch (URISyntaxException | IllegalArgumentException ex) {
            return DEFAULT_PATH;
        }
    }
}
~~~

Ví dụ cố ý chỉ cho **HTTPS accounts.example.com ở port mặc định**, không chấp nhận URL có query/fragment/userinfo hoặc path được encoded bất thường. Nếu staging dùng localhost/port khác, phải chuyển sang **trusted configuration per environment**, không thay bằng Host header của request.

**Lưu ý**: Response được tạo dưới dạng 303 và path từ allowlist, không chuyển thẳng saved URI thành Location. Điều này giảm rủi ro open redirect nhưng **không thay authorization** ở route sau login.

### 7.2. Gắn handler vào cùng RequestCache

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.RequestCache;

@Configuration
class VerifiedReturnToServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RequestCache restrictedRequestCache)
            throws Exception {

        VerifiedSavedRequestSuccessHandler handler =
                new VerifiedSavedRequestSuccessHandler(
                        restrictedRequestCache);

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/public/**")
                            .permitAll()
                        .anyRequest().authenticated())
                .requestCache(cache -> cache
                        .requestCache(restrictedRequestCache))
                .formLogin(form -> form
                        .loginPage("/login")
                        .successHandler(handler)
                        .permitAll())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Cần bean RequestCache từ mục 6.2 và GET /login/AuthenticationProvider hợp lệ. Đây là **phương án thay thế** fixed target mục 6.1, không khai báo hai chain trùng matcher trong cùng ứng dụng.

### 7.3. 303 khác 307/308

**303 See Other** sau POST login hướng user agent đến một retrieval request, thường **GET**. **302** là phương án redirect phổ biến của formLogin; browser thường chuyển từ POST sang GET.

**307 Temporary Redirect** và **308 Permanent Redirect** giữ method/body theo semantics. Chúng thường **không phù hợp** khi mục tiêu sau POST login là dashboard, đặc biệt nếu Location có thể bị tác động từ dữ liệu không tin cậy: body chứa credential có thể bị gửi tới đích không mong muốn.

### 7.4. Chủ động xóa saved request và lỗi auth cũ

Success handler trên chỉ dùng cached URL để quyết định **literal path**, nên sau khi đọc nó sẽ gọi removeRequest. Điều này giảm stale navigation ở lần login tiếp theo và không cần RequestCacheAwareFilter khôi phục saved parameters cho request mới.

Với success handler mặc định, RequestCacheAwareFilter có thể tiếp tục làm việc với saved request khi browser quay lại URL khớp theo cơ chế cache. **Hai chiến lược cleanup khác nhau cần test rõ**, không vừa yêu cầu khôi phục parameters vừa xóa cache ngay theo một cách vô tình.

Xóa saved request **không đồng nghĩa xóa HttpSession**. Session còn chứa authentication, CSRF hoặc dữ liệu nghiệp vụ theo vòng đời riêng.

### 7.5. Deep link tới /app/orders/123

Nếu sản phẩm cần quay về một order cụ thể:

- Validate **order ID** theo định dạng UUID/number có độ dài giới hạn.
- Dựng URI bằng **server-side route builder** từ các thành phần đã chuẩn hóa.
- Không chấp nhận arbitrary path/query hoặc URL ngoài chỉ vì route bắt đầu bằng /app.
- GET route mới vẫn phải kiểm tra user có quyền xem order đó.
- Khi user chuyển account hoặc tenant, không suy quyền từ saved URL thuộc session trước.
- Nếu order không còn, trả 404/403 theo policy hoặc hướng user về trang an toàn.

Nếu không cần deep link, đừng mở rộng allowlist chỉ để giảm số click.

## 8. Hạn chế dữ liệu ngay từ thời điểm lưu saved request

Kiểm tra Location ở success handler là cần thiết, nhưng một RequestCache quá rộng vẫn có thể **giữ URL hoặc metadata nhạy cảm trong HttpSession**.

### 8.1. Các loại request thường không nên lưu

- POST/PUT/PATCH/DELETE thay đổi trạng thái.
- **/login, /logout, /csrf**, authentication endpoints kỹ thuật.
- OAuth2/OIDC callback có **code/state**, hoặc URL chứa token.
- Reset password, invitation, magic-link, email verification chứa secret.
- API endpoints do SPA gọi bằng fetch và mong đợi JSON 401/403.
- Upload, request body nhạy cảm, tác vụ giao dịch và các thao tác không thể replay.
- WebSocket/SSE/long-polling hoặc những URL không có ý nghĩa browser navigation.
- Đường dẫn tự do do client cung cấp mà không có policy.

Ưu tiên **top-level GET navigation tới route đã duyệt**. Accept: text/html hoặc Sec-Fetch-* chỉ là tín hiệu hỗ trợ, không phải bằng chứng xác thực với HTTP client ngoài browser.

### 8.2. Chi phí anonymous session

Lưu một GET protected có thể tạo **anonymous HttpSession**, làm tăng chi phí Spring Session/Redis khi bị tự động truy cập hàng loạt.

Cần đánh giá:

1. Session TTL và memory/capacity.
2. RequestMatcher thật hẹp.
3. Rate limit riêng cho các protected navigation entry points khi cần.
4. Không giữ nhiều saved requests tùy ý hoặc chứa request body.
5. Theo dõi session creation, eviction, request-cache hit/miss.
6. Không log raw Cookie/Authorization/secret query.
7. Fallback khi session không còn hợp lệ.

**RequestCache không phải rate limiter**; chống lạm dụng lưu lượng cần lớp riêng ở edge/application.

### 8.3. Nhiều tab có thể ghi đè saved request

~~~text
Tab A: GET /app/orders     → saved request A
Tab B: GET /app/profile    → saved request B
Tab A: POST /login         → có thể quay về B thay vì A
~~~

Tùy cache implementation, một session có thể giữ một saved request nổi bật, và tab sau ghi đè tab trước. Đây là vấn đề **UX/state collision**, không phải bằng chứng được nâng quyền.

Nếu cần nhiều concurrent flows:

- Gắn **navigation intent ID** ngắn hạn với session và TTL.
- Lưu route ID/path đã allowlist, không arbitrary URL.
- Không dùng intent ID làm quyền truy cập tài nguyên.
- Có fallback khi intent hết hạn hoặc không thuộc session.
- Test account switch, multi-tab, login/logout lặp lại.

### 8.4. Session fixation và cache lifecycle

Sau login, session ID có thể được đổi để chống session fixation. Việc saved request còn hay mất phụ thuộc session strategy và cách lưu; không khẳng định mọi implementation luôn preserve cache attributes.

Logout thường invalidate session nếu chính sách yêu cầu. Saved request của phiên cũ không nên còn quyết định đích sau khi user đăng nhập bằng tài khoản khác.

Với **Spring Session/Redis**, kiểm tra session consistency và TTL nhiều instance. **Saved request mất** không chứng minh credential sai; success handler chỉ cần fallback an toàn.

### 8.5. Saved request không thay CSRF hay idempotency

Nếu user đang thực hiện POST /checkout, lưu request rồi replay mutation sau login có thể gây giao dịch lặp hoặc dùng CSRF token cũ. Nên quay về **GET /checkout/review**, xác minh dữ liệu/quyền/token mới và để user POST xác nhận lần nữa.

Sau auth change, CSRF token cũ có thể được Spring Security dọn; client phải lấy token hợp lệ từ repository mới. **Saved request không phải token CSRF, không phải bằng chứng đồng ý thực hiện giao dịch và không phải authorization grant.**

## 9. Reactive/WebFlux: ServerRequestCache và redirect sau authentication

Trong **WebFlux**, Spring Security dùng **SecurityWebFilterChain**, **ServerHttpSecurity**, **ServerRequestCache**, **WebSession** và **ServerAuthenticationSuccessHandler**. Trust boundary không đổi: saved destination có thể bắt nguồn từ request của client chưa xác thực.

### 9.1. So sánh Servlet và Reactive

| Servlet | Reactive/WebFlux | Vai trò |
| --- | --- | --- |
| HttpSecurity / SecurityFilterChain | ServerHttpSecurity / SecurityWebFilterChain | Cấu hình bảo vệ HTTP. |
| HttpSessionRequestCache | WebSessionServerRequestCache | Lưu request/URI theo session. |
| RequestCache | ServerRequestCache | Quản lý saved requests. |
| AuthenticationSuccessHandler | ServerAuthenticationSuccessHandler | Tạo response khi login thành công. |
| SavedRequestAwareAuthenticationSuccessHandler | RedirectServerAuthenticationSuccessHandler với ServerRequestCache phù hợp | Điều hướng tới saved URI hoặc fallback. |
| HttpSession | WebSession | Session state theo stack. |
| RedirectStrategy | ServerRedirectStrategy | Thực hiện HTTP redirect. |
| CsrfFilter | CsrfWebFilter | Bảo vệ unsafe request. |

Không mang HttpServletRequest, HttpSession hoặc OncePerRequestFilter vào WebFlux. Không gọi block() hoặc subscribe() thủ công trong reactive authentication success handler.

### 9.2. Cấu hình WebFlux không dùng saved request

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

@Configuration
@EnableWebFluxSecurity
class FixedRedirectReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        ServerAuthenticationSuccessHandler fixedSuccess =
                (webFilterExchange, authentication) -> {
                    var response =
                            webFilterExchange.getExchange().getResponse();

                    response.setStatusCode(HttpStatus.SEE_OTHER);
                    response.getHeaders().setLocation(URI.create("/app"));
                    return response.setComplete();
                };

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/login", "/public/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(form -> form
                        .authenticationSuccessHandler(fixedSuccess))
                .csrf(Customizer.withDefaults())
                .requestCache(cache -> cache.disable())
                .build();
    }
}
~~~

Ví dụ dùng **URI literal /app** trong success response và không cần lưu saved request. Sau redirect, authentication và authorization vẫn được kiểm tra cho route /app. Cần có authentication manager/login page phù hợp, và đối chiếu cú pháp DSL theo phiên bản Spring Security được dùng.

### 9.3. Khi cần lưu saved URI trong WebSession

Spring Security Reactive có **WebSessionServerRequestCache**, kết hợp với **RedirectServerAuthenticationSuccessHandler**:

~~~java
import org.springframework.security.web.server.authentication
        .RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.savedrequest
        .WebSessionServerRequestCache;

WebSessionServerRequestCache savedCache =
        new WebSessionServerRequestCache();

RedirectServerAuthenticationSuccessHandler success =
        new RedirectServerAuthenticationSuccessHandler();

success.setRequestCache(savedCache);

// Minh họa cấu hình cùng instance:
// http.requestCache(cache -> cache.requestCache(savedCache));
// http.formLogin(form -> form.authenticationSuccessHandler(success));
~~~

**Đây không phải ví dụ allowlist an toàn đầy đủ.** Nếu RedirectServerAuthenticationSuccessHandler chọn URI từ ServerRequestCache, policy phải xác minh scheme, host, port, path, query và fallback trước khi cho phép URI đó xuất hiện trong Location.

Một custom ServerAuthenticationSuccessHandler có thể dùng **ServerRequestCache.getRedirectUri(exchange)**, xử lý Mono<URI> rồi chuyển tới một **URI mới từ allowlist** qua ServerRedirectStrategy. Khi hiện thực cần quản lý cache cleanup/lifecycle theo phiên bản và không cho URL client đi thẳng vào redirect.

### 9.4. Pseudocode validation Reactive

~~~text
onAuthenticationSuccess(exchange):
    savedUriMono = requestCache.getRedirectUri(exchange)

    return savedUriMono
        → nếu có: validateUri(savedUri, publicOrigin, allowedPaths)
        → nếu không hợp lệ hoặc thiếu: URI /app
        → chỉ dùng URI/path được server dựng lại
        → quản lý cached request theo cơ chế repository
        → redirectStrategy.sendRedirect(exchange, safeUri)
        → hoàn tất Mono<Void>
~~~

Đây là **mô tả luồng**, không phải Java biên dịch. Không gọi subscribe() trong handler để gửi một redirect tách khỏi reactive pipeline; cần compose publisher và xử lý lỗi/cancellation theo API framework.

### 9.5. Reactive saved request và WebSession lifecycle

- WebSession có thể hết hạn, bị thay hoặc bị invalidate sau logout.
- Một tab có thể ghi đè navigation state của tab khác.
- Request được cache không tự được xác thực/quyền hóa.
- Không tự replay POST/body đã gửi trước login.
- Cần query/path allowlist cả khi saved URI nằm trong WebSession.
- Spring Session Reactive hoặc nhiều instances yêu cầu session storage đúng.
- Nếu proxy tính scheme/host sai, phải sửa trusted forwarding và public-origin config thay vì nới wildcard host.

## 10. SPA, REST API và browser navigation không giống nhau

Một SPA thường gọi POST /login bằng fetch. Khi backend trả 302 tới /app, **fetch có thể theo redirect ở tầng network**, nhưng **không làm browser chuyển document** như form submission.

### 10.1. Bẫy 302 → final 200

~~~text
fetch POST /login
    → 302 Location: /app
    → fetch tự theo redirect
    → GET /app nhận HTML 200
    → SPA nhìn response.ok = true
    → Router vẫn đang ở /login
~~~

Nếu redirect tới origin khác, CORS có thể từ chối cho JavaScript đọc response dù server đã xử lý authentication. Không kết luận từ fetch error rằng session chưa được tạo; xác minh principal ở endpoint hợp lệ.

### 10.2. Hợp đồng SPA dễ kiểm soát

| Endpoint | Contract minh họa | Vai trò |
| --- | --- | --- |
| GET /csrf | Token JSON, no-store. | Lấy token cho session hiện tại. |
| POST /login | 204/JSON thành công, 401 lỗi credential. | Thay đổi authentication, không trả arbitrary redirect. |
| GET /api/me | Principal đã đăng nhập. | Xác minh danh tính/tenant sau login. |
| GET /api/navigation | Route ID đã allowlist, nếu cần. | Gợi ý navigation, không cấp quyền. |
| POST /logout | 204 hoặc hợp đồng đã định. | Session/token cleanup, frontend tự điều hướng. |

Sau login, frontend nên xác minh **GET /api/me**, lấy CSRF token mới nếu token trước login đã bị dọn, rồi chọn **route ID** đã biết. Không dùng một trường nextUrl tự do từ response để gán window.location.

### 10.3. Frontend kiểm soát route ID

~~~javascript
const routeMap = Object.freeze({
  home: "/app",
  orders: "/app/orders",
  profile: "/app/profile"
});

function safeRoute(id) {
  return typeof id === "string"
      && Object.prototype.hasOwnProperty.call(routeMap, id)
    ? routeMap[id]
    : routeMap.home;
}

async function afterLogin(loginResponse) {
  if (!loginResponse.ok) {
    throw new Error("Đăng nhập chưa được xác nhận");
  }

  const meResponse = await fetch("/api/me", {
    credentials: "include",
    cache: "no-store"
  });
  if (!meResponse.ok) {
    throw new Error("Không xác minh được phiên đăng nhập");
  }

  updatePrincipalState(await meResponse.json());
  await fetchNewCsrfToken();

  // targetId được tạo/kiểm tra theo contract ứng dụng.
  navigateTo(safeRoute(getTargetId()));
}
~~~

Các hàm **updatePrincipalState, fetchNewCsrfToken, getTargetId, navigateTo** là hàm ứng dụng tự triển khai. Khi cần quay về /app/orders/123, nên validate order ID theo format, rồi để **GET route sau login** kiểm tra quyền thật.

### 10.4. Mở deep link rồi login trên SPA

~~~text
GET /app/orders/123
  → SPA nhận biết cần login
  → Lưu route intent tạm thời theo tab, có validation
  → POST /login + CSRF token hợp lệ
  → GET /api/me xác minh principal
  → GET /csrf lấy token mới
  → Kiểm tra route intent còn phù hợp và cùng origin
  → SPA router chuyển tới /app/orders/123
  → Backend kiểm tra user có quyền xem order 123
~~~

Intent trong sessionStorage là dữ liệu client, **không phải authorization grant**. Nó có thể stale sau account switch, bị sửa bởi script trong origin hoặc bị mất khi đóng tab; thiết kế phải có fallback và không tin client state.

### 10.5. redirect: manual không phải cách vượt CORS

Với fetch cross-origin, redirect: manual có thể cho **opaqueredirect** khiến JavaScript không đọc được Location theo mong muốn. Không sửa bằng cách phản chiếu Origin hoặc tắt credential safeguards.

Với SPA, **204 hoặc JSON route ID đã kiểm soát** thường rõ ràng hơn. Với HTML form login truyền thống, 302/303 redirect vẫn phù hợp nếu target được xác minh.

## 11. Proxy, firewall, CORS, CSP và HSTS quanh redirect

### 11.1. Reverse proxy có thể dựng sai scheme/host

~~~text
Browser -- HTTPS accounts.example.com --> Gateway
Gateway -- HTTP nội bộ --> Spring
~~~

Nếu backend chỉ thấy http://internal:8080, saved URL có thể sai origin/scheme. Nếu backend tin **Forwarded/X-Forwarded-Host** từ client không qua trusted proxy chain, attacker có thể làm sai Host và redirect URI.

Cần cả hai:

1. **Trusted proxy configuration**: gateway xóa/ghi đè forwarded headers từ client; network boundary không cho bypass edge khi backend dựa vào đó.
2. **Configured public-origin allowlist**: validate saved URI với host/scheme/port cố định, không lấy expected host từ request.
3. **URL normalization nhất quán** giữa gateway, servlet container, WebFlux và firewall.
4. **Kiểm thử qua đúng proxy thật**, không chỉ localhost.
5. **Redirect fallback** an toàn nếu saved URL mang internal host hoặc không đạt validation.

### 11.2. CORS không chặn top-level redirect

Một backend có allowlist CORS chặt vẫn có thể trả:

~~~http
Location: https://outside.test/phishing
~~~

Top-level browser navigation có semantics khác với fetch reading. **Không dùng CORS như bộ xác minh Location**. Ngược lại, fetch qua SPA có thể báo CORS error do redirect tới host lạ, dù authentication đã xảy ra.

### 11.3. CSP giúp giảm bề mặt, không thay validator

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; form-action 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'
~~~

**form-action** giới hạn đích form trên HTML document; **connect-src** giới hạn fetch/XHR; **frame-ancestors** giảm clickjacking. Chúng **không phải URL allowlist phía server**, cũng không nên được xem là bảo đảm chặn mọi redirect được phát sau login.

Policy phải đặt **trên HTML document** cần được bảo vệ, không chỉ JSON API khác origin.

### 11.4. HSTS, cookie flags và Referrer-Policy

~~~http
Strict-Transport-Security: max-age=31536000
Referrer-Policy: strict-origin-when-cross-origin
Set-Cookie: __Host-APPSESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **HSTS** giúp browser dùng HTTPS cho host đã biết policy, không xác minh Location.
- **Secure/HttpOnly/SameSite** bảo vệ cookie theo các khía cạnh khác nhau, không ngăn navigation tới outside.test.
- **Referrer-Policy** giới hạn dữ liệu Referer trong những tình huống điều hướng; với trang có secret trong URL, cân nhắc no-referrer và tránh copy token vào redirect.
- **Cache-Control: no-store** cho response login/CSRF nhạy cảm giảm lưu trữ không mong muốn, không thay origin validation.

Không bật HSTS includeSubDomains khi chưa kiểm kê hỗ trợ HTTPS của các subdomain. Cookie của accounts.example.com **không tự động được gửi tới outside.test**, nhưng open redirect vẫn có thể hỗ trợ phishing hoặc rò secret do URL/query/referrer không phù hợp.

### 11.5. HTTP firewall và URL canonicalization

Nếu gateway hiểu /app/orders nhưng Servlet/URI parser lại hiểu một request được encode thành //outside.test hoặc /admin, validator có thể bị bypass. Cần thống nhất normalization của encoded separators, backslash, path traversal, context path và HTTP methods.

**Đừng nới StrictHttpFirewall vô điều kiện** chỉ để một saved URL hoạt động. Sửa đúng route policy và proxy parsing, đồng thời kiểm thử những request nguy hiểm bị chặn trước authentication.

## 12. OAuth2/OIDC và logout redirect không phải một loại

### 12.1. Saved request khác OAuth2 state

~~~text
User GET /app/orders
  → RequestCache có thể lưu destination cho sau login

OAuth2/OIDC login được khởi tạo
  → AuthorizationRequestRepository lưu authorization request/state
  → Provider xác thực user
  → Callback xác minh code/state/PKCE/nonce theo giao thức

Authentication thành công
  → Success redirect có thể quay về saved request nếu hợp lệ
~~~

**RequestCache** giúp UX quay về tài nguyên ban đầu; **OAuth2 state** ràng buộc callback với authorization request. Chúng không thay nhau. PKCE/nonce/issuer/audience validation cũng không bị thay bởi một URL trong session.

### 12.2. redirect_uri của OAuth2 phải được kiểm soát riêng

**redirect_uri** là callback đã định nghĩa theo client registration/provider policy. Không lấy returnTo/next/SavedRequest.getRedirectUrl từ user rồi gán làm OAuth2 redirect_uri để nhận authorization code.

Callback có **code và state** trong query không nên bị ghi vào saved request dùng cho post-login UX hoặc được phản chiếu sang một URL ngoài.

### 12.3. FormLogin handler không bao trùm mọi SSO success handler

Ứng dụng có thể dùng formLogin, oauth2Login, SAML, remember-me hoặc MFA completion; mỗi flow có success handler/callback khác nhau. Chỉ harden formLogin.successHandler **không chứng minh OAuth2/OIDC/SSO redirect đã an toàn**.

Nên có **dịch vụ chọn safe destination chung**, dùng config allowlist/fallback, sau đó tích hợp tại từng auth flow phù hợp. Nhưng mỗi giao thức vẫn cần xác minh state/PKCE/nonce/signature/correlation đúng cách.

### 12.4. Logout redirect là hợp đồng khác

Local logout có thể trả redirect về trang signed-out, hoặc đi qua IdP để thực hiện OIDC RP-Initiated Logout. **post_logout_redirect_uri** theo provider registration không được lấy tự do từ:

~~~text
/logout?returnTo=https://outside.test
~~~

Không biến returnTo thành đích sau logout ở IdP ngoài allowlist. Local app session có thể đã kết thúc dù IdP SSO session còn; phải nói rõ phạm vi.

### 12.5. Login CSRF và open redirect có thể kết hợp

POST /login dựa vào cookie/session vẫn cần CSRF protection; OAuth2 callback vẫn cần state/PKCE/nonce; success redirect cần origin/path validation; resource API cần authorization. **Mỗi lớp giải quyết một rủi ro khác nhau** và không được thay thế bằng một saved request.

## 13. Kiểm thử MockMvc: lưu request, xác minh đích và kiểm tra quyền

Các bài test quan trọng phải sử dụng **cùng HttpSession xuyên qua request được lưu và POST login**. Chỉ gọi POST /login với with(csrf()) mà không có protected GET trước đó không chứng minh saved request được xử lý đúng.

### 13.1. Ma trận expected behavior

| Kịch bản | Kỳ vọng | Điều phải chứng minh |
| --- | --- | --- |
| GET /app/orders trước login ở HTTPS public host. | Sau login tới /app/orders. | Route hợp lệ được lưu và chọn. |
| GET /app/profile trước login. | Sau login tới /app/profile. | Cache/handler nhất quán. |
| Không có saved request. | Tới /app. | Fallback. |
| Host = outside.test. | Bị edge chặn hoặc về /app. | Không redirect ngoài allowlist. |
| Scheme HTTP khi policy chỉ HTTPS. | Về /app. | Không hạ cấp. |
| GET /app/orders?token=secret. | Về /app. | Matcher không lưu query. |
| GET /admin/users. | Về /app. | Route không nằm trong navigation allowlist. |
| POST nghiệp vụ trước login. | Không replay POST. | Không khôi phục mutation/body. |
| Login có next=//outside.test. | Không ảnh hưởng Location. | Không tin targetUrlParameter. |
| Referer: https://outside.test. | Không ảnh hưởng Location. | Không tin header. |
| Browser logout rồi login mới. | Không dùng intent của session cũ. | Cleanup cache. |
| Tab A/B lưu hai routes. | Không redirect ngoài allowlist. | Multi-tab collision không thành bypass. |
| Route đã được lưu nhưng user thiếu quyền. | GET sau redirect vẫn bị từ chối. | Authorization tách khỏi navigation. |
| Proxy/Host tạo internal URL. | Fallback hoặc sửa trusted forwarding. | Không đưa internal host vào Location. |

### 13.2. Test với cùng anonymous session

Ví dụ giả định sử dụng **VerifiedReturnToServletSecurityConfig** và **RestrictedSavedRequestConfiguration** ở mục 6–7, một user test **learner/test-secret** tồn tại, các route /app/** yêu cầu Authentication và success handler trả **303**.

~~~java
import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SavedRedirectMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void approvedSavedRequestRedirectsAfterLogin()
            throws Exception {

        MvcResult first = mvc.perform(get(URI.create(
                "https://accounts.example.com/app/orders")))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                first.getRequest().getSession(false);

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "learner")
                .param("password", "test-secret"))
            .andExpect(status().isSeeOther())
            .andExpect(header().string(
                    "Location", "/app/orders"));
    }

    @Test
    void loginWithoutSavedRequestFallsBack()
            throws Exception {

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "test-secret"))
            .andExpect(status().isSeeOther())
            .andExpect(header().string("Location", "/app"));
    }
}
~~~

**Điều kiện:** Dự án test thực phải có AuthenticationProvider/fixture tương ứng. Request đầu tiên phải tạo saved request trong HttpSession; nếu cấu hình không tạo session, assertion và test harness cần sửa chứ không tự coi null là cache thành công. **with(csrf())** giúp request vượt CSRF layer, không mô phỏng trọn browser cookie lifecycle hay việc rotate CSRF token sau login.

### 13.3. Host khác được chặn hoặc fallback

Trong môi trường test nơi application nhận request với Host khác:

~~~java
MvcResult first = mvc.perform(get(URI.create(
        "https://outside.test/app/orders")))
    .andExpect(status().is3xxRedirection())
    .andReturn();

MockHttpSession session = (MockHttpSession)
        first.getRequest().getSession(false);

mvc.perform(post("/login")
        .session(session)
        .with(csrf())
        .param("username", "learner")
        .param("password", "test-secret"))
    .andExpect(status().isSeeOther())
    .andExpect(header().string("Location", "/app"));
~~~

Test này chứng minh **fallback của custom handler**. Trong production, **Host validation tại edge** nên chặn request outside.test trước khi RequestCache tạo entry; nếu vậy test integration tại edge kỳ vọng **reject sớm** chứ không cố ép vào form login.

### 13.4. Test query được loại bỏ

Policy RequestMatcher ở mục 6.2 yêu cầu getQueryString() == null:

~~~java
MvcResult first = mvc.perform(get(URI.create(
        "https://accounts.example.com/app/orders?token=secret")))
    .andExpect(status().is3xxRedirection())
    .andReturn();

// Tiếp tục POST /login với anonymous session hợp lệ từ test harness.
// Expected Location: /app, không được có token=secret.
~~~

Nếu request không được cache và cũng không tạo session, test cần cấp anonymous session/CSRF token đúng theo form login của ứng dụng. **Đừng nhầm null session với thất bại của handler**: đây là một trong những trường hợp fallback được thiết kế.

### 13.5. POST không được phát lại

~~~java
mvc.perform(post("/app/orders")
        .contentType("application/json")
        .content("{\"confirm\":true}"))
    .andExpect(status().isForbidden());
~~~

Khi CSRF bật và token thiếu, test này thường bị **CsrfFilter từ chối trước RequestCache**; nó chưa chứng minh RequestMatcher không lưu POST. Cần thêm unit test RequestMatcher hoặc integration test POST có CSRF token hợp lệ rồi kiểm tra saved state không được dùng cho auto replay.

Đối với một giao dịch như thanh toán, chỉ cho **GET /checkout/review** sau login, và bắt người dùng xác nhận một **POST mới với CSRF token hiện hành** và idempotency protection.

### 13.6. Redirect success không cấp quyền

Sau khi redirect tới /app/orders/{id}, test cần gửi **GET mới mang session authenticated** và xác nhận AuthorizationFilter/controller vẫn kiểm tra quyền. Nếu user không có quyền với order 123, response có thể là 403/404 theo policy dù saved URL đã hợp lệ về navigation.

Thử thêm case session hết hạn, logout, account switch và multi-tab để phát hiện stale cache. Không log session ID/CSRF token thật.

## 14. WebTestClient và kiểm thử trình duyệt qua proxy

### 14.1. WebFlux fixed success test

Giả sử WebFlux app dùng **fixed success URI /app** từ mục 9.2, form login có fixture user hợp lệ:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;

// Đoạn test sau cần WebTestClient đã bind ứng dụng.
webTestClient
    .mutateWith(csrf())
    .post().uri("/login")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData(
            "username", "learner")
            .with("password", "test-secret"))
    .exchange()
    .expectStatus().isSeeOther()
    .expectHeader().valueEquals("Location", "/app");
~~~

Đoạn code giả định login success handler trả **303**, không phải redirect mặc định; test không chứng minh WebSession cache, cookie hoặc proxy logic.

### 14.2. Kiểm thử WebFlux saved request thực

~~~text
GET /app/orders chưa đăng nhập
  → WebSessionServerRequestCache lưu request/URI

POST /login có CSRF + credential hợp lệ cùng WebSession
  → Authentication thành công
  → Custom saved URI validator chọn path /app/orders

GET /app/orders với cookie authenticated
  → Authorization kiểm tra quyền thực
~~~

Test thêm saved URI host ngoài, query chứa secret, token cũ, WebSession expiration, nhiều tab và reverse proxy. **mockUser()** cho từng request không thay integration test qua form login thực và cookie jar.

### 14.3. Browser DevTools: kiểm tra redirect chain

Trong **Network → Preserve log**:

1. Mở protected GET route trong browser profile test sạch.
2. Kiểm tra redirect tới login và session cookie được tạo theo policy.
3. POST /login với CSRF token hợp lệ.
4. Xem status **302/303** và **Location** chính xác.
5. Quan sát browser theo redirect bằng một **GET mới**, không phát lại POST credential.
6. Xác minh GET route cuối vẫn yêu cầu authz.
7. Thử returnTo, Referer và Host giả trong môi trường được phép.
8. Kiểm tra không có token/code/PII trong Location hoặc Referer.
9. Mở nhiều tab để phát hiện saved request collision.
10. Thử session expiry/logout/login lại và xác minh fallback/cleanup.

Với SPA, quan sát fetch response và router riêng; network-level redirect **không tự điều hướng document**. Nếu cookie bị chặn do SameSite/Secure/Path/Domain, có thể xuất hiện loop login ngay cả khi URL allowlist đúng.

### 14.4. OPTIONS không phải saved navigation

~~~bash
curl -i -X OPTIONS "https://api.example.com/login" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

CORS preflight thường không mang session cookie và không nên được lưu để redirect sau login. curl không thực thi browser SOP/CORS/SameSite/CSP và có thể tự khai Host/Origin/Forwarded, nên cần browser test thực cho journey navigation.

### 14.5. Kiểm thử Host/Forwarded qua edge

Trong staging có quyền kiểm thử:

- Host không thuộc public host allowlist bị chặn tại gateway.
- Forwarded/X-Forwarded-Host client tự khai không làm thay Location.
- Backend dựng đúng HTTPS public scheme hoặc fallback.
- Context path/prefix rewriting không tạo double slash/network-path URL.
- HSTS/CSP/Referrer-Policy còn đúng khi qua proxy.
- URL mã hóa bất thường bị HTTP firewall từ chối.
- Không có open redirect tại login, logout, /go?next hoặc SSO callbacks.

Nếu edge chặn trước Spring, **đó là kết quả phòng vệ tốt**. Không thay gateway để “cho test chạy tới handler” trong production.

## 15. Chẩn đoán saved request và redirect sau login

| Triệu chứng | Lớp cần kiểm tra | Cách sửa |
| --- | --- | --- |
| Login xong luôn về /app. | RequestCache disabled, matcher không lưu, session mất. | Kiểm tra policy và fallback. |
| Location dẫn tới outside.test. | next/Referer/Host/Forwarded hoặc saved URI không validate. | Origin/path allowlist, trusted proxy. |
| Location bắt đầu //host. | Chỉ dùng startsWith("/") để xác minh. | Route literal/URI parsing chuẩn. |
| Saved URL dùng HTTP/internal host. | Forwarded headers hoặc proxy scheme sai. | Trusted forwarding, configured public origin. |
| Query chứa code/token trong Location. | Cache query nhạy cảm, raw URL được copy. | Bỏ sensitive paths/query, scrub logs. |
| Redirect loop /login. | Auth path được lưu, session cookie không gửi, chain sai. | Exclude login, kiểm tra cookie/session. |
| POST cũ không được replay. | RequestCache chỉ hỗ trợ navigation. | GET review + POST xác nhận mới. |
| Redirect tới trang admin nhưng bị 403. | Principal không có quyền. | Giữ authorization, không nới quyền. |
| Redirect 307 làm POST tới dashboard. | Sai redirect status semantics. | 303/302 theo POST/Redirect/GET. |
| GET saved URL không được nhớ. | RequestMatcher chỉ lưu path khác, query khác. | Kiểm tra method/path/query. |
| Saved request mất sau login. | Session lifecycle/fixation/TTL. | Fallback và test session strategy. |
| Tới trang của tab khác. | Saved-request collision nhiều tab. | Flow-scoped intent hoặc fallback. |
| GET /csrf 401 trước login. | CSRF endpoint bị authorization chặn. | Cho anonymous lấy token theo policy. |
| POST /login 403. | CSRF token thiếu/sai. | Xác minh token/session, không tắt CSRF. |
| Login POST 302 nhưng SPA không chuyển route. | Fetch không làm top-level navigation. | 204/JSON route ID. |
| SPA báo CORS sau redirect. | Actual response/redirect host thiếu CORS. | Kiểm tra network, API contract. |
| OAuth2 login về sai trang. | Success handler của OAuth2 khác formLogin. | Apply chung URL policy đúng flow. |
| OAuth2 callback mất state. | Nhầm RequestCache với authorization request store. | Xác minh state/PKCE/nonce riêng. |
| Logout ở app nhưng IdP vẫn có session. | Local logout khác IdP logout. | OIDC logout theo provider policy. |
| Lưu saved request tạo nhiều session. | Cache matcher quá rộng hoặc bot traffic. | Hẹp routes, TTL, rate limiting. |
| Proxy và Spring hiểu path khác. | Normalization/HTTP firewall mismatch. | Chuẩn hóa đồng nhất, test encoding. |
| Saved request hợp lệ nhưng GET sau login 404. | Tài nguyên đã bị xóa hoặc route thay đổi. | Xử lý 404/fallback UX, không bypass authz. |
| Saved URL của user cũ dùng với account mới. | Stale session/intents sau switch. | Cleanup, xác minh principal và resource. |

### 15.1. Trình tự điều tra

1. Ghi nhận **method/path/query/origin** của request trước login.
2. Kiểm tra RequestCache có lưu vào **đúng session** không.
3. Xác minh CSRF token và cookie được gửi khi POST /login.
4. Xác định handler nào thực sự chạy: formLogin, OAuth2, SSO hay custom.
5. Tìm **nguồn đích**: default, saved request, next parameter hoặc Referer.
6. So với public-origin/path allowlist độc lập Host.
7. Kiểm tra status/Location và **HTTP method của request browser tiếp theo**.
8. Đảm bảo cached request được consume/clear đúng.
9. Gửi GET cuối với session authenticated để xác minh authorization.
10. Với SPA, phân biệt fetch redirect và router.
11. Với SSO, kiểm tra callback/state và post-logout redirect registration riêng.
12. Với proxy, kiểm tra CORS/CSP/HSTS/firewall, sửa đúng tầng mà không tắt CSRF.

## 16. Bài tập tình huống: phân loại trusted redirect và saved request

### Tình huống A — Login thành công rồi bị đưa ra website lạ

User mở form login với next=https://outside.test/signin. Sau khi nhập password hợp lệ, backend trả 302 Location trỏ tới URL trên. Có vấn đề gì?

**Đáp án:** Có nguy cơ **open redirect** vì một URL do client cung cấp điều khiển Location. Dùng fixed safe route hoặc route ID/path allowlist; không trả nguyên next. Đây không tự chứng minh cookie HttpOnly của ứng dụng bị gửi ra outside.test, nhưng có nguy cơ phishing và các chuỗi tấn công khác.

### Tình huống B — URL bắt đầu bằng dấu gạch chéo

Developer chỉ kiểm tra next.startsWith("/"). Attacker gửi //outside.test/login. Đó có phải internal path không?

**Đáp án:** Không chắc; **//outside.test** có thể được browser diễn giải thành network-path reference tới một hostname khác. Không chỉ kiểm tra startsWith("/"). Ưu tiên exact-route allowlist hoặc chuẩn hóa và parse URI theo policy.

### Tình huống C — Host prefix đánh lừa

Validator cho phép bất kỳ host nào startsWith("accounts.example.com"). URL https://accounts.example.com.outside.test/phish được chấp nhận. Tại sao?

**Đáp án:** So sánh tiền tố hostname sai. Phải parse URI và so **host chính xác**, scheme/port phù hợp, không so chuỗi URL bắt đầu bằng trusted hostname.

### Tình huống D — HTTP 307 sau POST login

POST /login thành công, server trả 307 Location: https://outside.test/continue do cấu hình sai. Rủi ro hơn 303 ở đâu?

**Đáp án:** 307 theo HTTP semantics giữ **method và body** khi theo redirect. Request credential POST có thể bị chuyển sang đích ngoài nếu client tuân thủ. Với login POST → trang GET, dùng 303 (hoặc 302 theo contract hiện có) và luôn validate đích.

### Tình huống E — Saved request nằm trong HttpSession nên đáng tin?

Attacker tác động tới URL GET ban đầu, Spring ghi vào HttpSession, sau login success handler dùng lại nguyên saved URI. Developer nói session làm URL đáng tin. Đúng không?

**Đáp án:** Không. Session chỉ là nơi lưu, **không thay nguồn gốc dữ liệu**. URL có thể bắt nguồn từ Host/path/query do client ảnh hưởng; cần validate trước Location.

### Tình huống F — Host header poisoning

Một gateway chuyển Host từ HTTP client vào backend không kiểm soát. SavedRequest chứa https://outside.test/app/orders. Hướng phòng vệ?

**Đáp án:** Validate Host ở edge, làm sạch Forwarded/X-Forwarded-Host theo trusted proxy chain và so saved URI với public-origin config. Không lấy request.getServerName làm trusted allowlist.

### Tình huống G — Reverse proxy đổi HTTPS thành HTTP nội bộ

Browser mở HTTPS accounts.example.com nhưng Spring nhìn thấy http://internal:8080. Validator production reject saved URI và user luôn về /app. Có nên cho phép tất cả HTTP hosts?

**Đáp án:** Không. Sửa **trusted forwarded scheme/host configuration** và public-origin mapping. Fallback /app là một phòng vệ hợp lý khi saved URI sai; không nới arbitrary host để chữa lỗi proxy.

### Tình huống H — Tham số next được ưu tiên hơn saved request

Spring handler đã có RequestCache hẹp, nhưng developer bật setTargetUrlParameter("next") và không validate. Attacker gửi next ngoài origin. RequestCache matcher có cứu được không?

**Đáp án:** Không đủ. Target URL parameter có thể là nguồn khác được handler ưu tiên. Phải bỏ tham số tự do hoặc dùng route ID/validator chung cho mọi nguồn.

### Tình huống I — Dùng Referer để quay lại trang

Handler dùng Referer làm URL thành công. Referer bị thiếu hoặc bị một HTTP client giả. Có thể coi Referer là proof-of-origin không?

**Đáp án:** Không. Referer có thể bị policy cắt hoặc không gửi; nonbrowser client có thể giả. Nếu dùng cho UX phải validate, tốt hơn dùng saved navigation intent đã kiểm soát.

### Tình huống J — Query mang reset token

User mở /password/reset?token=secret, bị đưa tới login, saved request lưu cả query rồi redirect sau login. Nguy cơ gì?

**Đáp án:** Token có thể bị lưu hoặc phản chiếu vào Location, history, logs, analytics và referrer. Loại secret-bearing paths/query khỏi RequestCache; các token recovery có vòng đời/mục đích riêng.

### Tình huống K — Không tự phát lại POST /checkout

User POST /checkout khi session đã hết, login xong browser đi tới GET /checkout/review, không thực hiện giao dịch. Đó có phải RequestCache hỏng?

**Đáp án:** Không. Đây là cách an toàn: saved request không phải transaction replay engine. User xem lại dữ liệu rồi gửi **POST mới** với CSRF token, quyền và idempotency.

### Tình huống L — GET trước login chứa side effect

Một hệ thống dùng GET /api/pay?confirm=true để thực hiện thanh toán. SavedRequestAware handler redirect GET đó sau login. Vấn đề nằm ở đâu?

**Đáp án:** HTTP method sai semantics: **GET phải safe**. Sửa endpoint để mutation dùng POST/unsafe method cùng CSRF/authorization; không chỉ cố vá RequestCache.

### Tình huống M — Saved route là /admin/users

Một user thường chưa login truy cập /admin/users, đăng nhập thành công, handler redirect về /admin/users rồi nhận 403. Có phải bug cần cấp quyền admin không?

**Đáp án:** Không. Saved URL không tạo quyền; authorization vẫn phải từ chối. Có thể chọn fallback do route không nằm trong navigation allowlist để UX tốt hơn, nhưng **không nới quyền**.

### Tình huống N — Default target và always-use-default

Handler được setDefaultTargetUrl("/app"), nhưng sau login vẫn về saved /app/orders. Developer cho rằng setDefaultTargetUrl bắt buộc luôn về /app. Đúng không?

**Đáp án:** Không. Default target thường là **fallback**. Muốn bỏ saved request, dùng **alwaysUseDefaultTargetUrl=true** hoặc phương án request cache disabled, và kiểm thử với chính handler/DSL version.

### Tình huống O — Saved request không tồn tại

User mở trực tiếp /login và đăng nhập thành công; cache không có request trước đó. App trả 500 vì getRequest trả null. Thiết kế đúng không?

**Đáp án:** Không. **Không có saved request là hợp lệ**; luôn có route fallback như /app, không dereference null.

### Tình huống P — Hai tab cùng browser

Tab A mở /app/orders, tab B mở /app/profile, rồi tab A login và được đưa tới profile. Có chứng minh account bị chiếm không?

**Đáp án:** Không. Có thể là **saved-request collision** trong cùng session. Cần kiểm thử UI, xác định chính sách cache; nếu cần từng tab, dùng intent ID ngắn hạn có validation, không nhầm với quyền truy cập.

### Tình huống Q — Session hết hạn khi nhập password

Saved request được lưu trong HttpSession nhưng session timeout trước khi POST /login. Sau login chỉ còn fallback /app. Có nên cố lấy đích cũ từ cookie tùy ý?

**Đáp án:** Không mặc định. Cần safe fallback; nếu thiết kế state client, phải allowlist và ràng buộc TTL/session/flow phù hợp. Không dùng cookie chứa raw external URL làm bằng chứng tin cậy.

### Tình huống R — Spring Security 6 continue parameter

Developer thấy query ?continue và coi value là trang phải redirect. Có đúng nghĩa của matching-request parameter không?

**Đáp án:** Không. Một số cấu hình dùng continue như **tín hiệu kiểm tra saved request** nhằm tối ưu session access; nó không phải authorization token hoặc targetUrlParameter. Kiểm tra cơ chế theo phiên bản thay vì cho nó quyết định URL.

### Tình huống S — SPA fetch theo 302 nhưng router vẫn ở login

POST /login bằng fetch, server redirect 302 tới /app, response cuối 200 HTML. SPA không tự đổi route. Có cần tắt CORS để router chạy?

**Đáp án:** Không. **Fetch redirect không tự điều hướng top-level document**. Thiết kế API trả 204/JSON và SPA tự navigate tới route ID hợp lệ sau khi xác minh principal, không sửa bằng cách tắt CORS.

### Tình huống T — OIDC state là route quay về?

Team lấy OAuth2 state làm chuỗi URL returnTo và dùng nó trực tiếp sau callback. Đây có đúng chức năng state không?

**Đáp án:** Không. **state** là cơ chế tương quan bảo mật của authorization request; return route là UX navigation riêng. Không dùng state thay saved-request validation, cũng không biến OAuth2 state thành untrusted external URL.

### Tình huống U — OAuth2 redirect_uri lấy từ query next

Ứng dụng cho caller đặt redirect_uri của OAuth2 login bằng query next. Có thể dẫn tới callback ngoài danh sách đã đăng ký không?

**Đáp án:** Có nguy cơ nghiêm trọng. **redirect_uri** cần theo registration/provider policy; không dùng next/SavedRequest từ client để nhận authorization code. Validation của OAuth2 flow độc lập với allowlist post-login navigation.

### Tình huống V — OIDC post_logout_redirect_uri

Sau logout local, app lấy returnTo tùy ý từ query để gửi sang IdP làm post_logout_redirect_uri. Có hợp lệ không?

**Đáp án:** Không nên. Đích sau IdP logout phải thuộc các URI cho phép/đã đăng ký theo provider policy; không nhận arbitrary URL. Local app session và IdP session là các phạm vi khác nhau.

### Tình huống W — WebFlux dùng HttpSessionRequestCache

Một Reactive app cố inject HttpSessionRequestCache và Servlet AuthenticationSuccessHandler vào SecurityWebFilterChain. Có vấn đề?

**Đáp án:** Sai stack. Dùng **ServerRequestCache/WebSessionServerRequestCache**, ServerAuthenticationSuccessHandler và reactive Mono pipeline. Không block event loop hoặc trộn Servlet APIs.

### Tình huống X — Fragment không xuất hiện trong saved request

User mở /app/orders#details rồi login; server không phục hồi #details. Có phải session bị mất?

**Đáp án:** Không chắc. Browser **không gửi URL fragment trong HTTP request**. Nếu SPA cần giữ fragment/route state, phải thiết kế client-side navigation intent có validation và fallback.

### Tình huống Y — URI chứa percent-encoded traversal

URL được đưa vào saved cache là /app/%2e%2e/admin hoặc có double encoding. Validator chỉ xem chuỗi bắt đầu bằng /app. Có đủ an toàn không?

**Đáp án:** Không. Các tầng browser, proxy, URI parser và firewall có thể normalize khác nhau. Dùng **exact paths hoặc typed route builder**, đồng nhất decoding/canonicalization và giữ HTTP firewall, không chuyển raw URL thẳng sang Location.

### Tình huống Z — GET saved request nhưng user thiếu quyền sau login

Saved request hợp lệ về scheme/host/path, user đã đăng nhập đúng nhưng quyền đã bị thu hồi trước khi request mới được gửi. Server nên làm gì?

**Đáp án:** **Authorization luôn kiểm tra ở request mới**. Trả 403/404 theo policy hoặc một UX fallback được kiểm soát; không cấp quyền chỉ vì saved request được ghi khi user còn anonymous.

## 17. Checklist triển khai an toàn

### 17.1. Phân loại nguồn redirect

- [ ] Liệt kê tất cả endpoint tạo **Location** sau login, logout, account linking, SSO và khôi phục.
- [ ] Biết đích được chọn từ **fixed route, saved request, targetUrlParameter, Referer hay next/returnTo**.
- [ ] Không dùng trực tiếp giá trị **query, header hoặc cookie do client khai** làm Location.
- [ ] Public origin đến từ **trusted application configuration**.
- [ ] Không lấy request.getServerName() hoặc X-Forwarded-Host chưa tin cậy để tạo allowlist.
- [ ] Mọi authentication success handler có đích redirect đều dùng policy tương ứng.
- [ ] Không chỉ kiểm tra formLogin nếu ứng dụng còn OAuth2/OIDC/SAML/SSO hoặc MFA.
- [ ] Ưu tiên **route ID/enum** thay vì URL tự do khi yêu cầu UX cho phép.
- [ ] Có **fallback cố định** khi saved request thiếu, hết hạn hoặc không an toàn.
- [ ] Route được chọn để điều hướng không thay thế authorization.

### 17.2. Xác minh URL và canonicalization

- [ ] Parse URI bằng parser chuẩn và đánh giá **scheme, host, port, userinfo**.
- [ ] Production yêu cầu HTTPS theo public-origin policy.
- [ ] So sánh hostname **chính xác**, không startsWith trên chuỗi URL.
- [ ] Reject network-path reference dạng **//outside.test**.
- [ ] Reject scheme nguy hiểm, opaque URI và fragment ngoài chính sách.
- [ ] Chỉ cho phép **exact paths** hoặc typed route builder có kiểm chứng.
- [ ] Tránh encoded slash/backslash, path traversal và double decoding.
- [ ] Proxy, firewall, server và redirect writer dùng chính sách normalization nhất quán.
- [ ] Nếu cần query, allowlist tên/tham số, giá trị, độ dài và encode lại.
- [ ] Không copy token, authorization code, password-reset secret, session ID hoặc apiKey vào URL.
- [ ] Không validate một biểu diễn URI rồi redirect nguyên biểu diễn raw khác.
- [ ] Chỉ đưa **URI/path mới do server dựng từ dữ liệu đã duyệt** vào Location.

### 17.3. Servlet RequestCache và success handler

- [ ] SecurityFilterChain xử lý đúng protected GET, GET /login và POST /login.
- [ ] Nếu sản phẩm không cần return URL, dùng fixed success path và tắt request cache phù hợp.
- [ ] Nếu cần saved request, dùng **HttpSessionRequestCache** có RequestMatcher hẹp.
- [ ] Chỉ lưu **GET trang hiển thị**, không lưu POST/PUT/PATCH/DELETE cho navigation.
- [ ] Không lưu auth callbacks, reset links và sensitive query.
- [ ] RequestCache bean trong chain và success handler là **cùng instance**.
- [ ] SavedRequest.getRedirectUrl được validate **ngay trước redirect**.
- [ ] Hiểu defaultTargetUrl là fallback và alwaysUseDefaultTargetUrl có thể bỏ saved request.
- [ ] targetUrlParameter/Referer không override policy bằng dữ liệu client.
- [ ] Matching request parameter **continue** không bị dùng như returnTo.
- [ ] Saved request được consume/clear theo đúng lifecycle.
- [ ] Không xóa toàn bộ session chỉ để dọn cached URL.
- [ ] Redirect sau POST login dùng 302/303 theo contract, tránh 307/308 gửi lại credential body.
- [ ] Authorization cho route sau redirect vẫn được kiểm tra.

### 17.4. Reactive/WebFlux

- [ ] Dùng **ServerHttpSecurity/SecurityWebFilterChain**, không trộn Servlet classes.
- [ ] Biết ứng dụng dùng ServerRequestCache nào và nơi WebSession lưu state.
- [ ] Fixed URI là giải pháp mặc định khi không cần saved navigation.
- [ ] Saved URI từ WebSessionServerRequestCache được xác minh trước Location.
- [ ] ServerAuthenticationSuccessHandler dùng **Mono pipeline**, không block hoặc subscribe thủ công.
- [ ] Kiểm thử redirect strategy, cache cleanup và session expiration trên đúng framework version.
- [ ] OAuth2/SSO reactive success path cũng tuân theo allowlist.
- [ ] Cookie WebSession và trusted forwarding được kiểm tra qua gateway.
- [ ] WebTestClient có test session continuity nếu sản phẩm dùng saved request.

### 17.5. Session, CSRF, dữ liệu và quyền

- [ ] Saved request không được coi là Authentication, CSRF token hay authorization grant.
- [ ] Không tự phát lại POST body/mutation sau khi user login.
- [ ] Login POST có CSRF token hợp lệ khi dùng cookie/session.
- [ ] Client lấy token CSRF phù hợp session mới sau authentication change.
- [ ] Session fixation/session ID rotation và cache lifecycle đã được kiểm thử.
- [ ] Session expiry/eviction tạo fallback, không trả 500 hoặc điều hướng sai.
- [ ] Logout dọn session/saved state theo chính sách; không dùng target của account trước.
- [ ] Multi-tab không tạo redirect ra ngoài allowlist hoặc quyền cross-account.
- [ ] Route sau redirect vẫn kiểm tra resource ownership và tenant authorization.
- [ ] Với thanh toán/đặt đơn, dùng GET review rồi POST xác nhận mới + idempotency.
- [ ] RequestCache không tạo anonymous sessions không giới hạn; có timeout và chống abuse.
- [ ] Không ghi toàn bộ saved request, Cookie, Authorization hoặc secret URL vào logs.

### 17.6. OAuth2/OIDC, SSO và logout

- [ ] Phân biệt **RequestCache** với **AuthorizationRequestRepository/state**.
- [ ] OAuth2 redirect_uri theo client registration/provider policy, không nhận arbitrary next.
- [ ] State/PKCE/nonce/issuer/audience validation không bị bỏ qua vì custom redirect.
- [ ] OAuth2 login success handler được review riêng với form login.
- [ ] SAML/SSO/MFA/account-linking redirects được xem xét khi dùng.
- [ ] OIDC post_logout_redirect_uri thuộc allowlist/registered URIs của provider.
- [ ] Không lấy logout returnTo do client đặt làm IdP redirect tự do.
- [ ] OAuth2 callback chứa code/state không được cache làm trang return-to.
- [ ] Local logout khác IdP logout; UX không tuyên bố quá phạm vi thực thi.
- [ ] Account switch không tái dùng intent thuộc principal hoặc tenant cũ mà bỏ kiểm tra quyền.

### 17.7. Proxy, browser và headers

- [ ] Edge xác minh Host/SNI và chỉ nhận public hosts đã cấu hình.
- [ ] Forwarded/X-Forwarded-Host/Proto được làm sạch tại **trusted proxy boundary**.
- [ ] Backend không bị client bypass edge trong khi dựa vào forwarded policy.
- [ ] Saved Location không chuyển sang HTTP hoặc host nội bộ.
- [ ] Context path, encoded path và proxy rewriting không làm lệch canonicalization.
- [ ] HTTP firewall vẫn chặn URL/method bất thường.
- [ ] CORS không bị dùng thay redirect allowlist.
- [ ] CSP form-action/connect-src được đặt trên HTML frontend phù hợp.
- [ ] HSTS và session-cookie Secure/HttpOnly/SameSite hoạt động trên HTTPS.
- [ ] Referrer-Policy giảm tiết lộ URL query nhạy cảm qua điều hướng.
- [ ] Cache-Control phù hợp cho login/CSRF/error responses.
- [ ] Network DevTools cho thấy đúng Location, redirect status và GET tiếp theo.

### 17.8. Kiểm thử hồi quy

- [ ] Saved GET hợp lệ quay lại đúng route sau login.
- [ ] Không có saved request thì về default safe target.
- [ ] Host/scheme/port ngoài allowlist bị từ chối hoặc fallback.
- [ ] Network-path URL, host prefix, backslash, percent encoding, traversal bị loại.
- [ ] targetUrlParameter và Referer không thể override chính sách.
- [ ] Secret query không xuất hiện trong Location, referrer hoặc logs.
- [ ] POST không được replay tự động sau login.
- [ ] Authorization ở GET sau redirect vẫn hoạt động.
- [ ] POST /login thiếu/sai CSRF không bị xem là login thành công.
- [ ] Session expiry và logout không để stale target sang lần login sau.
- [ ] Multi-tab và account switch không gây cross-account authorization bypass.
- [ ] MockMvc test thực giữ cùng session qua save → login → redirect.
- [ ] WebTestClient kiểm tra redirect fixed path và WebSession khi cần.
- [ ] Browser test phân biệt fetch redirect với document navigation.
- [ ] Proxy integration test Host/Forwarded/CORS/CSP/HSTS/firewall.
- [ ] OAuth2/OIDC callback/redirect URI và logout URI được kiểm tra độc lập.
- [ ] Test chỉ dùng tài khoản/môi trường được phép, không lộ credential thật.

## 18. Ghi nhớ

1. **Saved request là dữ liệu hỗ trợ UX**, không tự trở nên đáng tin chỉ vì nằm trong HttpSession/WebSession.
2. Trên Servlet, những thành phần chính là **ExceptionTranslationFilter, AuthenticationEntryPoint, HttpSessionRequestCache, SavedRequestAwareAuthenticationSuccessHandler và RequestCacheAwareFilter**.
3. Redirect sau login **không tự phát lại POST body hoặc giao dịch**. Nên quay về GET review, rồi user chủ động POST mới với CSRF/idempotency.
4. Các nguồn như **next/returnTo, targetUrlParameter, Referer, Host, Forwarded và saved URI** cần validation nếu ảnh hưởng tới Location.
5. **Fixed route** ít rủi ro nhất khi không cần deep link. Nếu cần deep link, dùng typed route/allowlist origin-path-query và fallback.
6. **//outside.test, host-prefix, encoded path và double decoding** chứng minh vì sao startsWith trên URL string không đủ.
7. **defaultTargetUrl** khác **alwaysUseDefaultTargetUrl**; tham số **continue** của RequestCache không phải đích redirect hoặc token bảo mật.
8. Servlet nên lưu **GET navigation phù hợp** và custom success handler dựng lại **literal safe path** rồi cleanup cache.
9. WebFlux dùng **ServerRequestCache, WebSessionServerRequestCache và ServerAuthenticationSuccessHandler** theo reactive pipeline, không trộn Servlet APIs.
10. Với SPA, **fetch redirect không tự thay document**. Contract 204/JSON route ID cùng navigation client được kiểm soát thường rõ hơn.
11. **CSRF, session fixation, OAuth2 state/PKCE/nonce, authorization và logout** là các lớp bảo vệ độc lập với URL allowlist.
12. **CORS, CSP, HSTS, HttpOnly, SameSite và HTTP firewall** không thay validation đích redirect; Host/Forwarded cần trusted proxy chain.
13. **Test cốt lõi**: saved GET hợp lệ quay về đúng trang, URI độc hại bị loại, POST không replay, stale state được clear, tài nguyên cuối vẫn kiểm tra quyền.

## Tài liệu tham khảo định hướng

Đối chiếu **Spring Security Reference/Javadoc theo phiên bản thực tế**, đặc biệt API RequestCache, URI matching và success handlers:

- [Spring Security Reference — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — Servlet Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Reactive Web Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security Reference — Reactive Form Login](https://docs.spring.io/spring-security/reference/reactive/authentication/passwords/form.html)
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security Javadoc — SavedRequestAwareAuthenticationSuccessHandler](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)

**Nguyên tắc kết thúc bài:** Chỉ tin một đích điều hướng khi **nguồn của nó được hiểu rõ, URI đã được xác minh bằng chính sách độc lập, Location chứa giá trị an toàn do server dựng lại và tài nguyên đích vẫn chịu authorization**.






