# Lập kiểm thử hồi quy cho token, header, cookie và hành trình đăng nhập

Trong chương **Nâng cấp và tương thích** thuộc **SPRING_SECURITY_HTTP_PROTECTION**, một thay đổi phiên bản Spring Security, Spring Boot, browser hoặc cấu hình proxy có thể khiến ứng dụng vẫn build thành công nhưng mất một phần bảo vệ HTTP. Ví dụ, người dùng đăng nhập được nhưng CSRF token không được gửi trong request tiếp theo; CSP bị gateway ghi đè; cookie phiên mất thuộc tính `Secure`; hoặc logout chỉ xóa giao diện trong khi phiên phía máy chủ vẫn hoạt động.

Bài học hướng dẫn cách thiết kế **bộ kiểm thử hồi quy bảo mật có thể lặp lại** cho token, HTTP response headers, cookie và toàn bộ hành trình xác thực. Nội dung áp dụng cho cả Spring MVC/Servlet và Spring WebFlux/Reactive, bao gồm CSRF, CORS, CSP, HSTS, HTTP firewall, session và tương tác với CDN, reverse proxy, API gateway. Mục đích là phát hiện **thay đổi hành vi gây mất bảo vệ hoặc làm hỏng tính năng** trước khi đưa bản nâng cấp vào sản xuất.

Sau bài học, người học có thể:

1. Lập ma trận test từ tài sản bảo vệ, rủi ro, điểm kiểm soát đến kết quả mong đợi và bằng chứng quan sát.
2. Tách bài test token thành CSRF, session ID, OAuth2/OIDC `state`/`nonce`/PKCE, access/refresh token và remember-me tùy thiết kế.
3. Đo security headers và cookie attributes ở ứng dụng lẫn browser thật; hiểu khác biệt giữa HTTP-only, same-origin, same-site và cross-site.
4. Dùng `MockMvc`, `WebTestClient` và browser automation để kiểm thử đăng nhập, đăng xuất, lỗi xác thực, đổi phiên, các request bị từ chối và đường đi qua proxy.
5. Xây dựng tiêu chí đạt, kiểm soát dữ liệu thử, phân loại lỗi và quy trình chạy lại phù hợp trước/sau nâng cấp.

## 1. Vì sao kiểm thử chức năng đăng nhập thành công là chưa đủ?

Giả sử một ứng dụng quản trị vừa nâng Spring Security và đổi TLS termination sang gateway. Nhóm QA kiểm tra `POST /login` trả `302`, trang chính mở được, sau đó kết luận đạt. Nhưng các lỗi dưới đây vẫn có thể tồn tại:

- `POST /transfer` thiếu CSRF token lại được chấp nhận vì cấu hình matcher mới loại trừ sai path.
- Cookie `JSESSIONID` bị gateway sửa mất `Secure` hoặc `SameSite`, trong khi test MockMvc không đi qua gateway.
- `Strict-Transport-Security` biến mất ở public URL do backend không nhận diện request từ proxy là HTTPS.
- CORS trả thêm hai header `Access-Control-Allow-Origin`; backend thấy HTTP 200 nhưng browser từ chối response.
- Bản ghi `/api/me` của người A được CDN cache rồi trả cho người B.
- Logout làm browser chuyển trang nhưng phiên cũ vẫn gọi được API bảo vệ.
- OAuth2 callback hợp lệ bị từ chối vì `state` cookie sai thuộc tính, hoặc callback có `state` giả mạo lại lọt qua kiểm tra.
- Frontend gửi access token đã hết hạn nhưng backend trả nhầm dữ liệu vì gateway cache hoặc xác thực sai tuyến.

Những lỗi này xảy ra ở **nhiều ranh giới**. Vì vậy, test cần quan sát trạng thái trước, trong và sau hành trình xác thực, thay vì chỉ kiểm tra status code của một endpoint.

~~~mermaid
flowchart LR
    A["Nâng cấp thư viện / cấu hình"] --> B["Unit + component tests"]
    B --> C["MockMvc / WebTestClient"]
    C --> D["Triển khai qua gateway và HTTPS"]
    D --> E["Browser E2E"]
    E --> F["Kiểm tra log, metric, bằng chứng"]
    F --> G{"Đạt hợp đồng bảo mật?"}
    G -->|Có| H["Phát hành có kiểm soát"]
    G -->|Không| I["Sửa đúng tầng và chạy lại"]
    I --> B
~~~

## 2. Bắt đầu bằng hợp đồng bảo mật có thể kiểm thử

**Hợp đồng bảo mật** mô tả ứng dụng phải cho phép điều gì, từ chối điều gì và trả tín hiệu nào. Trước khi nâng cấp, ghi lại hành vi đang được kỳ vọng của phiên bản hiện tại, phân biệt cấu hình mong muốn với hành vi đang lỗi.

Ví dụ với ứng dụng có form login và session cookie:

| ID | Tài sản/quy tắc | Tình huống | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|---|
| AUTH-01 | Trang cần xác thực | Anonymous gọi `GET /account` | Bị chuyển tới login hoặc nhận `401` theo loại client | Status, `Location`, không có dữ liệu cá nhân |
| AUTH-02 | Form login | Đăng nhập bằng tài khoản thử hợp lệ | Tạo authenticated context và điều hướng đúng | Trạng thái auth, cookie, URL |
| AUTH-03 | Sai mật khẩu | Nhập mật khẩu không hợp lệ | Không tạo authenticated session; lỗi không tiết lộ bí mật | Status/redirect, không truy cập được API |
| CSRF-01 | Request thay đổi trạng thái | `POST /profile` thiếu CSRF token | Bị từ chối theo chính sách | Thường `403`; không có side effect |
| CSRF-02 | Token giả | `POST /profile` có CSRF token không hợp lệ | Bị từ chối, không đổi dữ liệu | Status và dữ liệu trước/sau |
| CSRF-03 | Token đúng | User hợp lệ gửi POST với token hợp lệ | Chỉ được xử lý khi đồng thời có quyền | Status, dữ liệu thay đổi hợp lệ |
| SESS-01 | Session fixation | Login sau khi có session anonymous | Session ID được đổi/rotation theo chính sách | So sánh ID trước/sau, phiên cũ không còn cấp quyền |
| SESS-02 | Logout | Logout có CSRF hợp lệ | Context/session bị xóa hoặc invalidated; token cũ bị vô hiệu theo thiết kế | Request tiếp theo không có quyền |
| HDR-01 | Chống cache | Response chứa dữ liệu riêng | Có `Cache-Control: no-store` hoặc chính sách an toàn tương đương | Header tại public URL, CDN cache status |
| HDR-02 | HSTS | HTTPS public response | Có chính sách HSTS đã phê duyệt | Header HTTPS cuối cùng |
| HDR-03 | Chặn sniffing | HTTP response qua filter chain | `X-Content-Type-Options: nosniff` | Header response |
| COOKIE-01 | Cookie session | Browser nhận cookie phiên | `Secure`, `HttpOnly`, `SameSite`, `Domain` và `Path` đúng hợp đồng | `Set-Cookie` và cookie jar của browser |
| CORS-01 | Preflight | Origin được phép gọi API | CORS headers phù hợp, không yêu cầu cookie trên OPTIONS | HTTP response và browser thực thi |
| CORS-02 | Origin lạ | Origin không được duyệt | Không được cấp quyền đọc response qua browser | Headers và browser result |
| FW-01 | HTTP firewall | Path encoding bất thường | Bị chặn hoặc xử lý thống nhất, không bypass rule | Status, log reject, không side effect |

Ma trận **phải được điều chỉnh theo kiến trúc**. Với API chỉ dùng Bearer token stateless, không nên giữ nguyên giả định “mọi POST đều cần CSRF token” nếu credential không được browser tự gửi và CSRF được xử lý theo mô hình khác. Với ứng dụng OIDC, bổ sung state, PKCE, nonce, IdP session và logout liên kết. Với ứng dụng SAML, thay test OIDC bằng relay state, assertion, ACS và logout của giao thức tương ứng.

### 2.1. Chọn test theo rủi ro thay vì đếm dòng test

Để một trường hợp được đưa vào suite hồi quy, ghi tối thiểu:

~~~yaml
id: CSRF-02
risk: "Thao tác đổi dữ liệu được chấp nhận với CSRF token giả"
precondition: "Người dùng thử có phiên xác thực hợp lệ"
request: "POST /api/profile với CSRF token không hợp lệ"
expected: "Bị từ chối và profile không thay đổi"
levels: ["MockMvc hoặc WebTestClient", "browser smoke"]
evidence: ["HTTP status", "dữ liệu sau request", "trace ID"]
owner: "Nhóm backend/security"
~~~

Đây là **mẫu minh họa một test case**, không phải file metadata của module. Giá trị kỳ vọng đủ cụ thể để khi test fail biết đó là **regression hay chủ đích đổi chính sách**.

## 3. Lập ma trận token: nhiều token, nhiều vòng đời

Từ `token` không chỉ có một nghĩa. Hành trình xác thực có thể dùng đồng thời nhiều loại:

| Token hoặc định danh | Nguồn và vai trò | Kiểm thử quan trọng |
|---|---|---|
| **CSRF token** | Ràng buộc unsafe request với cơ chế chống CSRF | Thiếu, giả, đúng; token sau login/logout; xử lý token ở cookie/header/body |
| **Session ID** | Cookie tham chiếu phiên xác thực phía server | Rotation khi đăng nhập; session timeout; logout; session cũ bị vô hiệu |
| **Access token** | Cấp quyền truy cập API theo scope/claim | Chữ ký, issuer, audience, hết hạn, scope, token sai định dạng; không lộ thông tin |
| **Refresh token** | Cấp lại access token theo chính sách authorization server | Rotation/reuse detection nếu hệ thống hỗ trợ; revoke sau logout; hết hạn |
| **OAuth2 `state`** | Gắn callback vào phiên yêu cầu ủy quyền được khởi tạo trước | State thiếu, sai, replay, đa tab; không chấp nhận callback tùy ý |
| **PKCE code verifier/challenge** | Gắn authorization code với client khởi tạo luồng | Verifier đúng/sai, code hết hạn/đã dùng; test ở authorization server khi thuộc phạm vi |
| **OIDC `nonce`** | Gắn ID token với request xác thực, chống replay theo thiết kế OIDC | Nonce khớp và không khớp; ID token có claim hợp lệ |
| **Remember-me token** | Duy trì đăng nhập theo thời gian dài hơn session thường | Khôi phục đúng quyền; xóa/revoke khi logout; kiểm soát lifetime |
| **Token xác minh email/reset password** | Cho phép thao tác một lần, giới hạn thời gian | Hết hạn, dùng lại, token sai, tài khoản khác, reset làm vô hiệu phiên nếu chính sách yêu cầu |

Không tạo thêm test cho loại token **không tồn tại** trong ứng dụng. Đầu tiên vẽ sơ đồ cấp phát, nơi lưu, nơi xác minh và vòng đời từng token, sau đó chọn các điểm chuyển trạng thái có rủi ro.

### 3.1. Luồng CSRF trong ứng dụng session/cookie

Ví dụ ứng dụng có xác thực session:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security
    B->>S: GET /form
    S-->>B: Trang + CSRF token theo cấu hình
    B->>S: POST /profile + Cookie session + CSRF token
    S->>S: Kiểm tra session, CSRF và quyền
    alt Token hợp lệ, user có quyền
        S-->>B: 200 hoặc redirect + dữ liệu mới
    else Token thiếu/sai hoặc user thiếu quyền
        S-->>B: 403 hoặc response lỗi đã cấu hình
    end
~~~

Các biến thể cần test:

- **Thiếu token:** unsafe request bị từ chối, không thực hiện thay đổi trạng thái.
- **Token sai:** thử giá trị khác với token phiên hiện tại; bị từ chối.
- **Token đúng nhưng anonymous:** vẫn không thể truy cập tài nguyên cần authentication.
- **Token đúng nhưng thiếu role:** vẫn bị chặn bởi authorization/method security.
- **Sau login/logout:** token cũ có thể bị xóa/đổi theo cách Spring Security và `CsrfTokenRepository` đang dùng; client cần lấy token hợp lệ mới. Không hard-code giả định “token luôn đổi mỗi request”.
- **SPA:** nếu dùng cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN`, test cả tên cookie/header, chế độ request handler, token được expose đúng thời điểm và bất kỳ cơ chế masking nào. Nhiều thay đổi Spring Security liên quan deferred token và BREACH protection khiến client SPA cần tích hợp rõ ràng.

**Ranh giới:** `SameSite` của cookie là lớp hỗ trợ giảm CSRF nhưng **không thay** CSRF token khi mô hình ứng dụng yêu cầu; CORS cũng không phải CSRF protection.

### 3.2. JWT và refresh token

Ví dụ bảng negative test cho resource server dùng Bearer JWT:

| Test | Đầu vào | Kỳ vọng |
|---|---|---|
| JWT-01 | Không có `Authorization` | `401` hoặc lỗi unauthenticated theo contract; không trả dữ liệu |
| JWT-02 | `Bearer` token bị thay đổi một byte | Bị từ chối; không chấp nhận chữ ký không hợp lệ |
| JWT-03 | Token `exp` đã qua | Bị từ chối với độ lệch đồng hồ (clock skew) đã cấu hình |
| JWT-04 | `iss`/`aud` sai | Bị từ chối **nếu** resource server đã khai báo policy issuer/audience tương ứng |
| JWT-05 | Token hợp lệ, thiếu scope bắt buộc | Bị từ chối bởi authorization; thường `403` |
| JWT-06 | Token đúng scope | Được truy cập đúng tài nguyên thuộc quyền |
| REF-01 | Refresh token cũ sau rotation | Bị từ chối nếu hệ thống thực hiện refresh token rotation |
| REF-02 | Refresh token đã thu hồi sau logout | Không cấp access token mới |
| REF-03 | Replay refresh token đã dùng | Được phát hiện và áp dụng chính sách xử lý reuse nếu đã thiết kế |
| REF-04 | Access token vừa được refresh | Token mới phù hợp issuer, audience, TTL, scope, user và client |

Một access JWT đã phát hành có thể còn hiệu lực cho đến khi hết `exp` nếu hệ thống **không có cơ chế thu hồi sớm**; không viết test đòi access token lập tức bị từ chối sau logout trừ khi kiến trúc đã quy định denylist/introspection/short TTL hoặc kiểm soát tương đương. Phân biệt **logout ở browser**, **revoke refresh token**, **end-session tại IdP** và **vô hiệu access token trên resource server**.

Để test hết hạn, ưu tiên fake clock hoặc issuer thử nghiệm với lifetime ngắn, không dùng lệnh chờ thời gian dài. Token, key pair và tài khoản thử phải tách khỏi hệ thống thật.

## 4. Ma trận hồi quy cho security headers

Spring Security mặc định hỗ trợ nhiều response headers, nhưng chỉ đo tại origin có thể bỏ sót việc CDN/proxy/gateway sửa, thêm hoặc xóa. Browser quyết định hành vi theo **response cuối cùng**.

| Header | Điều kiện cần test | Kỳ vọng cốt lõi | Nguy cơ sau nâng cấp |
|---|---|---|---|
| `Cache-Control` | HTML/API cá nhân, login, logout, response lỗi có dữ liệu riêng | `no-store` hoặc chính sách phù hợp; CDN bypass | Tài khoản A nhận dữ liệu B do shared cache |
| `Pragma` / `Expires` | Môi trường còn client/cache legacy | Khớp chính sách cache | Proxy ghi đè chỉ thị từ app |
| `Strict-Transport-Security` | HTTPS public URL, HTTP redirect và proxy TLS termination | HSTS trên HTTPS theo policy; không giả định tồn tại trên HTTP | Backend không thấy secure request hoặc edge bỏ header |
| `Content-Security-Policy` | HTML, iframe, JavaScript, CDN, nonce/hash | Chính sách thống nhất cho phép tài nguyên hợp lệ và chặn script trái policy | CSP trùng/ghi đè; nonce bị cache |
| `Content-Security-Policy-Report-Only` | Giai đoạn chuyển CSP | Thu báo cáo mà không chặn | Nhầm Report-Only với enforcement |
| `X-Content-Type-Options` | Script, style, JSON và response khác | `nosniff` nếu đó là contract | MIME sniffing không được kiểm soát |
| `X-Frame-Options` / `frame-ancestors` | Trang nhạy cảm, embed hợp lệ | Chống clickjacking theo yêu cầu; iframe hợp lệ vẫn chạy | Gateway thêm `DENY` trong khi ứng dụng cần embed |
| `Referrer-Policy` | Redirect giữa origin, URL có dữ liệu nhạy cảm | Không tiết lộ dữ liệu ngoài chính sách | Policy edge thay đổi |
| `Clear-Site-Data` | Logout trên HTTPS, theo browser support | Chỉ phát có chủ đích; các nhóm storage/cookie được dọn theo thiết kế | Xóa dữ liệu ngoài dự kiến hoặc không tác động đúng origin |
| `X-XSS-Protection` | Nâng cấp từ cấu hình cũ | Thường `0` theo mặc định Spring Security hiện đại | Scanner cũ buộc bật `1; mode=block` không còn phù hợp |

**Giá trị mẫu của Spring Security mặc định** có thể gồm:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
~~~

Ở request HTTPS được nhận diện đúng, mặc định Spring Security còn phát HSTS. **Không mặc định có CSP phù hợp cho toàn bộ ứng dụng**; dự án cần tự đặt policy CSP.

### 4.1. Kiểm tra header trên ba điểm đo

1. **Application test:** MockMvc/WebTestClient xác minh filter chain đã phát header mong đợi.
2. **Origin integration:** gọi API qua kết nối ứng dụng/ingress thử nghiệm, quan sát header sau container và framework.
3. **Browser public URL:** đi qua TLS, CDN, proxy, gateway; kiểm tra header thực, cookie jar và CSP enforcement.

Một response `200` không có header thích hợp có thể vẫn là regression. Ngược lại, việc test chỉ thấy chuỗi `Content-Security-Policy` không chứng minh script trái policy thực sự bị browser chặn.

### 4.2. HSTS qua reverse proxy

Nếu TLS được kết thúc tại proxy, Spring có thể nhận kết nối nội bộ HTTP. HSTS writer cần nhận diện request là secure khi chính sách đặt tại Spring. Bài test sau nâng cấp cần kiểm tra:

- URL public là HTTPS, redirect không trỏ `http://internal-host:8080`;
- `Strict-Transport-Security` có ở response HTTPS công khai đúng theo policy;
- `Forwarded`/`X-Forwarded-Proto` chỉ được tin sau proxy đáng tin và bị chuẩn hóa;
- Không tự động bật `includeSubDomains`/`preload` ngoài phạm vi subdomain đã kiểm soát.

Không đặt HSTS trên response HTTP rồi kỳ vọng browser ghi nhớ header đó.

### 4.3. CSP có nonce và cache

Khi policy dùng nonce, mỗi response HTML cần nonce mới, nonce trong CSP header phải khớp với các script được phép. Test không nên assert **một nonce cụ thể cố định**. Nên kiểm:

- header có directive và nonce đúng định dạng;
- script hợp lệ có nonce trùng với header của **chính response đó**;
- hai response độc lập không tái sử dụng nonce nếu thiết kế yêu cầu ngẫu nhiên mới;
- shared CDN cache không phát lại cùng HTML/nonce được tạo cho user khác;
- browser chặn script inline trái chính sách và báo vi phạm đúng kỳ vọng.

## 5. Ma trận cookie: cặp thuộc tính phải được quan sát trong browser

Ví dụ cookie session muốn giới hạn tại chính host:

~~~http
Set-Cookie: __Host-session=example-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Tên và giá trị là minh họa; không đưa session ID thật vào tài liệu hoặc log.

| Thuộc tính | Kiểm thử | Lưu ý tương thích |
|---|---|---|
| `Secure` | Cookie auth chỉ được gửi qua HTTPS theo browser | Localhost là ngoại lệ ở một số browser; test sản phẩm trên HTTPS thật |
| `HttpOnly` | Script frontend không thể đọc cookie; browser vẫn gửi cookie trong request phù hợp | `document.cookie` **không phải cách kiểm tra trực tiếp** HttpOnly; dùng browser cookie API/DevTools |
| `SameSite=Strict` | Cookie không gửi trong nhiều navigation/request cross-site | Có thể ảnh hưởng redirect/SSO và login flow |
| `SameSite=Lax` | Cookie được gửi ở top-level safe navigation phù hợp; cross-site POST thường không | Browser có thể có chế độ Lax-by-default, cần test đúng version |
| `SameSite=None` | Khi cần cookie trong request cross-site, cookie được gửi theo chính sách | Phải có `Secure`; browser có thể chặn third-party cookie |
| `Domain` | Host-only cookie không tự chia sẻ subdomain; Domain cookie chia sẻ theo phạm vi cho phép | `Domain=example.com` có thể ảnh hưởng `app.example.com`, `shop.example.com` |
| `Path` | Cookie chỉ được gửi ở path thuộc phạm vi | `Path` không phải ranh giới bảo mật thay cho authorization |
| `Max-Age`/`Expires` | Hết hạn và xóa cookie đúng, ưu tiên `Max-Age` nếu cả hai có mặt | Đồng hồ browser/server có thể chênh; kiểm thử thời gian có kiểm soát |
| `__Host-` prefix | `Secure`, `Path=/`, không có `Domain` | Browser có hỗ trợ prefix sẽ từ chối cookie vi phạm |
| `Partitioned` (nếu dùng) | Cookie phân vùng theo top-level site như thiết kế | Yêu cầu `Secure`; support phụ thuộc browser |

**Phân biệt các khái niệm:**

- **Origin** là `scheme + host + port`; `https://app.example.com` và `https://api.example.com` khác origin.
- **Site** cho SameSite dựa trên scheme và registered domain theo mô hình schemeful same-site; hai subdomain cùng `example.com` có thể same-site nhưng vẫn **cross-origin**.
- **Cross-origin request** có thể cần CORS kể cả khi same-site; ngược lại, SameSite quyết định điều kiện cookie được gửi.
- `credentials: 'include'` trong Fetch và CORS `Access-Control-Allow-Credentials: true` ảnh hưởng request có credential; không tự vượt chính sách third-party cookie của browser.

Test cookie **không chỉ assert chuỗi `Set-Cookie`**. Có thể browser không nhận cookie do Domain/Secure/SameSite hoặc chính sách third-party không hợp lệ dù header xuất hiện trong response. Với cross-origin Fetch, frontend JavaScript cũng **không được đọc `Set-Cookie` trực tiếp** bằng `response.headers.get("set-cookie")`.

## 6. Lập kịch bản hành trình đăng nhập theo trạng thái

### 6.1. Form login với Servlet session

~~~mermaid
stateDiagram-v2
    [*] --> Anonymous
    Anonymous --> LoginForm: GET /login
    LoginForm --> Authenticated: POST /login + CSRF + mật khẩu đúng
    LoginForm --> LoginForm: Mật khẩu sai / account locked
    Authenticated --> Authorized: Truy cập tài nguyên có quyền
    Authenticated --> Forbidden: Thiếu quyền
    Authenticated --> LoggedOut: POST /logout + CSRF
    Authenticated --> Expired: Idle/absolute timeout
    LoggedOut --> LoginForm: Truy cập tài nguyên bảo vệ
    Expired --> LoginForm: Truy cập tài nguyên bảo vệ
~~~

Mỗi chuyển trạng thái cần xác minh **trạng thái ở server, cookie ở browser và quyền truy cập ở request tiếp theo**.

| Chuyển trạng thái | Kịch bản tích cực | Kịch bản tiêu cực |
|---|---|---|
| Anonymous → Login | Form có CSRF theo cấu hình, redirect public hợp lệ | Redirect loop, form không có token, cookie login sai |
| Login → Authenticated | Username/password đúng, session ID rotation | Password sai nhưng lại có quyền; session ID cố định bị giữ nguyên |
| Authenticated → Authorized | Role đúng, quyền theo tài nguyên | User A đọc tài nguyên riêng của B |
| Authenticated → Logout | Session bị hủy, security context mất, browser về trang login | Logout chỉ xóa UI nhưng session cũ vẫn hoạt động |
| Authenticated → Timeout | Token/session hết hiệu lực, trình duyệt được yêu cầu đăng nhập lại | Backend tiếp tục chấp nhận session hết hạn |
| Session mới → Multi-tab | Hai tab nhìn thấy trạng thái đồng bộ theo thiết kế | Tab cũ thao tác thành công sau logout từ tab khác |
| Login → Privilege elevation | Session được đổi/được kiểm soát phù hợp | Quyền cũ còn lại trong session hoặc token sai scope |

**Session fixation protection:** với Servlet container hiện đại, Spring Security thường dùng cơ chế đổi session ID khi authentication thành công. Test phải kiểm soát có session trước login rồi xác minh ID được đổi theo contract; nếu ứng dụng stateless thì không tạo test áp dụng `JSESSIONID` một cách máy móc.

### 6.2. OAuth2 Login/OIDC

Với OIDC, test toàn bộ luồng:

1. Khởi tạo login tại ứng dụng; kiểm tra redirect sang IdP và các tham số hợp lệ (`client_id`, `redirect_uri`, `response_type`, `scope`, `state`, PKCE khi dùng).
2. IdP thử nghiệm xác thực user và redirect callback với `code` và `state` đúng.
3. Spring Security kiểm tra trạng thái request trước đó, thực hiện token exchange, xử lý ID token với `iss`, `aud`, `exp`, `nonce` (nếu áp dụng), tạo session/context.
4. Người dùng vào tài nguyên bảo vệ; quyền và account mapping đúng.
5. Thử callback `state` sai/thiếu hoặc code đã dùng, nonce sai, token issuer/audience sai — **không tạo phiên authenticated**.
6. Logout: phân biệt application logout và đăng xuất phiên IdP nếu sản phẩm yêu cầu RP-initiated logout; sau redirect/callback phải đúng external HTTPS host.

Không dùng authorization code và token thật của môi trường sản xuất trong suite CI. IdP giả lập/authorization server test giúp kiểm soát đồng hồ, claim, timeout và lỗi.

### 6.3. SPA + API, refresh token và nhiều tab

Nếu frontend ở `https://app.example.com` còn API ở `https://api.example.com`:

- Test **preflight OPTIONS** cho request có header không đơn giản; preflight phải được xử lý trước authentication và không đòi cookie đăng nhập như request thật.
- Test request thật với credential chính xác; CORS hợp lệ **không thay authorization/CSRF**.
- Khi access token hết hạn, frontend thực hiện refresh hoặc chuyển login theo thiết kế; không lặp refresh vô hạn.
- Hai request đồng thời cùng gặp `401` cần được điều phối nếu sử dụng refresh rotation, tránh sử dụng lại refresh token cũ gây khóa phiên.
- Sau logout ở một tab, tab còn lại không được dùng phiên đã hủy để gọi API, dù giao diện có thể chưa chuyển tức thì.
- `Clear-Site-Data: "storage"` chỉ tác động origin của response theo khả năng browser; response từ API không mặc định xóa localStorage của frontend khác origin.
- Với OAuth2/OIDC, callback cross-site có thể cần cookie SameSite phù hợp với **kiểu navigation và request method**; không tự đặt `SameSite=None` cho mọi cookie.

## 7. Thiết kế cấu trúc kiểm thử nhiều tầng

| Tầng | Công cụ ví dụ | Test tốt nhất | Không thể kết luận từ tầng này |
|---|---|---|---|
| Unit/contract | JUnit, AssertJ, clock giả, test token verifier | Parse JWT, validate claim, quy tắc quyền, mã hóa cookie config | Browser có gửi cookie hoặc CDN có sửa header không |
| Security filter integration | `MockMvc` + `spring-security-test` (Servlet) | CSRF, login/logout, filter chain, auth/authorization, headers | Cookie jar/SameSite browser, TLS edge, CDN cache |
| Reactive filter integration | `WebTestClient` + `spring-security-test` (WebFlux) | Reactive CSRF, authentication, authorization, headers | Browser enforcement, reverse proxy |
| Service integration | Testcontainers/IdP test, repository/session store giả lập | Refresh token rotation, session persistence, multi-node semantics | Cache/CDN và trình duyệt thật nếu chưa đi qua edge |
| Browser E2E | Playwright/Selenium trên HTTPS | Cookie attributes được chấp nhận, redirect, login journey, CORS, CSP, multi-tab | Token bên trong IdP nếu không có test server và observability |
| Pre-production smoke | Public URL qua CDN/gateway, browser + HTTP client | HSTS, CORS, cache bypass, host/forwarded, logout end-to-end | Không thay thế test đầy đủ theo role/rule trong source |

Ưu tiên nhiều test nhanh ở filter/contract level, một số browser tests bao phủ hành trình quan trọng và các smoke tests qua ingress. Đừng đưa mọi biến thể vào E2E khiến test chậm, khó truy lỗi; cũng đừng bỏ E2E vì MockMvc đã xanh.

## 8. Ví dụ kiểm thử Servlet bằng MockMvc

### 8.1. Test CSRF hợp lệ, thiếu và giả

Đoạn minh họa dùng Spring Boot 3.x và Spring Security 6.x với `spring-security-test`; Spring Security 7.x giữ ý tưởng test tương tự, nhưng package auto-configuration của Spring Boot có thể khác theo phiên bản. Ví dụ **giả định** ứng dụng có endpoint `POST /api/profile` yêu cầu authentication + CSRF; khi hợp lệ controller xử lý request thành công.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCsrfRegressionTest {

    @Autowired MockMvc mvc;

    @Test
    void missingCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/profile").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/profile")
                .with(user("alice"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfPassesSecurityLayer() throws Exception {
        mvc.perform(post("/api/profile")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Các assertion mô tả contract của một endpoint thử nghiệm **trả 2xx khi request hợp lệ**. Nếu API trả `204`, `302`, cần body JSON hoặc authority cụ thể, hãy sửa assertion theo contract. Thêm kiểm tra **không thay đổi dữ liệu** sau request bị từ chối; chỉ assert `403` chưa đủ nếu bug vẫn gây side effect.

Nếu client gửi CSRF token bằng HTTP header:

~~~java
mvc.perform(post("/api/profile")
        .with(user("alice"))
        .with(csrf().asHeader()))
    .andExpect(status().is2xxSuccessful());
~~~

### 8.2. Test form login và trạng thái đăng nhập

`spring-security-test` có `formLogin()`, tạo request login với CSRF token hợp lệ:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;

@Test
void validCredentialsAuthenticate() throws Exception {
    mvc.perform(formLogin().user("alice").password("test-secret"))
        .andExpect(authenticated().withUsername("alice"));
}

@Test
void invalidCredentialsDoNotAuthenticate() throws Exception {
    mvc.perform(formLogin().user("alice").password("invalid-secret"))
        .andExpect(unauthenticated());
}
~~~

Để các test này chạy, môi trường test phải có user `alice` cùng password test hợp lệ và form login được bật. Không dùng tài khoản thật hoặc mật khẩu production. Một response 302 không đủ để chứng minh authenticated context đúng, vì login thất bại cũng thường redirect.

### 8.3. Kiểm tra security headers với HTTPS mô phỏng

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

@Test
void secureResponseKeepsRequiredHeaders() throws Exception {
    mvc.perform(get("/login").secure(true))
        .andExpect(header().string("X-Content-Type-Options", "nosniff"))
        .andExpect(header().exists("Strict-Transport-Security"))
        .andExpect(header().string("X-XSS-Protection", "0"));
}
~~~

Các assertion trên giả định dự án dùng **mặc định tương ứng** và request HTTPS đi qua Spring Security filter chain. Nếu ứng dụng cố ý tùy chỉnh HSTS, X-XSS-Protection hoặc CSP, assert theo **policy được duyệt** thay vì ép mọi dự án dùng một bộ header. Test với `.secure(true)` xác minh phía ứng dụng xem request là HTTPS; **không thay thế** test HSTS từ public URL sau proxy.

### 8.4. Test session sau logout

Hành trình logout cần kiểm tra cả trước và sau, dùng **cùng cookie/session** từ một request đăng nhập thật trong test. Ví dụ khung ý tưởng:

~~~java
// Pseudocode diễn đạt các bước; triển khai với session từ
// MvcResult của login hợp lệ và request tiếp theo cùng HttpSession.
MvcResult loggedIn = mvc.perform(formLogin()
        .user("alice").password("test-secret"))
    .andExpect(authenticated())
    .andReturn();

// Lấy session thực từ request login trong môi trường test.
MockHttpSession session =
    (MockHttpSession) loggedIn.getRequest().getSession(false);

// Gửi POST /logout với session đó và CSRF token hợp lệ.
mvc.perform(post("/logout").session(session).with(csrf()))
    .andExpect(status().is3xxRedirection());

// Gọi tài nguyên bảo vệ với session cũ sau logout.
// Kết quả phải không còn được xử lý như người dùng đã xác thực.
~~~

Đoạn mã này là **khung minh họa**; cần bổ sung imports và assert request sau logout theo entry point của dự án (`302` hoặc `401`), xử lý nếu cookie/session được lưu khác. Nếu login không tạo session do cấu hình stateless, không dùng mẫu này. Để kiểm tra session fixation, tạo session trước login và so sánh ID trước/sau hoặc sự kiện session ID change trong môi trường Servlet được cấu hình.

## 9. Ví dụ kiểm thử Reactive/WebFlux bằng WebTestClient

Reactive dùng `WebTestClient` và các test configurer khác với Servlet. Có thể tạo client bind vào ApplicationContext với `springSecurity()`, hoặc dùng test context đã cấu hình Spring Security phù hợp.

Giả định dự án WebFlux có endpoint `POST /api/profile` với CSRF bật và user `alice` có quyền. Ví dụ dưới đây bind trực tiếp `WebTestClient` vào `ApplicationContext`, áp dụng `springSecurity()` để các test configurer tác động lên filter chain trong test:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ReactiveCsrfRegressionTest {

    @Autowired ApplicationContext context;
    WebTestClient securityClient;

    @BeforeEach
    void setup() {
        securityClient = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void missingCsrfIsRejected() {
        securityClient.mutateWith(mockUser("alice"))
            .post().uri("/api/profile")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validCsrfPassesFilter() {
        securityClient.mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/api/profile")
            .exchange()
            .expectStatus().is2xxSuccessful();
    }
}
~~~

**Chọn đúng kiểu bind:** `mockUser` và `csrf` mô phỏng security context/token khi `WebTestClient` bind vào application context. Nếu test qua mạng HTTP thật ở `RANDOM_PORT`, dùng login/token/cookie thử **thật** thay vì trông chờ `mockUser()` đi qua HTTP socket. Với dự án chứa cả Servlet và Reactive, phải bảo đảm test context đang chọn WebFlux. Cơ chế test cho Reactive cũng khác `with(csrf())` của MockMvc.

Để kiểm tra header đơn giản, WebTestClient có thể assert:

~~~java
securityClient.get().uri("/login")
    .exchange()
    .expectHeader().valueEquals("X-Content-Type-Options", "nosniff");
~~~

Tương tự, với nhiều filter chain cần test từng route tương ứng để tránh chỉ quan sát default chain.

## 10. Test CORS preflight và browser cross-origin

CORS là nguồn regression thường gặp khi nâng Spring Security hoặc thay gateway. Preflight từ browser **không bao gồm session cookie như request thật**, vì vậy CORS cần được xử lý trước xác thực ở hệ thống dùng cấu hình Spring Security CORS.

Request thử:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Response được phép ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Mức status có thể là `200` hoặc `204` tùy handler, nhưng bộ CORS headers phải hợp lệ. Test cần xác minh:

- Origin được phép: preflight thành công, request thật vẫn được kiểm tra auth/CSRF/authorization.
- Origin không được phép: **không được trả CORS headers cho phép đọc**; HTTP status cụ thể phụ thuộc policy.
- Khi dùng credentials, `Access-Control-Allow-Origin` phải là origin cụ thể; không dùng `*` với `Access-Control-Allow-Credentials: true`.
- Không xuất hiện hai giá trị `Access-Control-Allow-Origin` do gateway và Spring cùng phát.
- `Vary` và CDN cache key xét đến `Origin`/`Access-Control-Request-Method`/`Access-Control-Request-Headers` khi response thay đổi theo chúng.
- Browser thật có thể chặn cookie do SameSite/third-party policy ngay cả khi CORS preflight thành công.

Ví dụ MockMvc cho API có Spring sở hữu CORS:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;

mvc.perform(options("/api/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
                "content-type,x-csrf-token"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin", "https://app.example.com"));
~~~

Đoạn này giả định CORS được định nghĩa cho path và phương thức; status 200 phù hợp với một implementation cụ thể. Nếu gateway trả lời preflight tại edge, test **bên ngoài gateway** mới là nguồn đúng để kiểm chứng kết quả cuối.

## 11. Browser E2E: kiểm tra thứ MockMvc không thấy

Ví dụ Playwright dùng **TypeScript** dưới đây minh họa hợp đồng form login, cookie và logout. Các selector, tên cookie, route phải chỉnh theo giao diện thật; dữ liệu thử được cấp qua environment của CI.

~~~typescript
import { test, expect } from "@playwright/test";

test("đăng nhập, cookie phiên và logout", async ({ page, context }) => {
  await page.goto("https://app.example.com/login");
  await page.getByLabel("Username").fill("alice-test");
  await page.getByLabel("Password").fill("secret-for-test-only");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/account|dashboard/);

  // API quản lý cookie của Playwright xem được thuộc tính HttpOnly,
  // trong khi document.cookie cố ý không đọc được cookie này.
  const cookies = await context.cookies();
  const session = cookies.find((c) => c.name === "JSESSIONID");
  expect(session).toBeDefined();
  expect(session?.secure).toBe(true);
  expect(session?.httpOnly).toBe(true);

  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("https://app.example.com/account");
  await expect(page).toHaveURL(/login/);
});
~~~

Đây là test minh họa **cho kiến trúc session cookie có form login và redirect**. Nếu ứng dụng dùng Bearer-only SPA, session cookie không tồn tại; thay assertion bằng kiểm thử token/refresh đúng thiết kế. Nếu logout chuyển sang trang xác nhận hoặc API trả `401`, cần điều chỉnh assertion tương ứng. Tránh dùng URL `example.com` hoặc mật khẩu cố định trong môi trường thật; chọn test domain/tài khoản riêng.

### 11.1. Bổ sung test cho hai tab

1. Tạo browser context đã đăng nhập, mở tab A và B.
2. Tab B thực hiện một request có quyền để chứng minh session hiện hành.
3. Tab A logout thành công.
4. Tab B gửi **request mới** tới endpoint yêu cầu authentication.
5. Backend phải từ chối theo hợp đồng, ngay cả khi tab B còn hiển thị dữ liệu cũ; frontend nên cập nhật giao diện theo cơ chế đồng bộ tab đã thiết kế.

Đừng kiểm tra duy nhất việc “tab B đã tự chuyển trang hay chưa”. Điều quyết định quyền là **server không tiếp tục chấp nhận phiên đã bị hủy**.

### 11.2. Kiểm tra cookie đã được browser chấp nhận

Dùng `context.cookies()` hoặc browser DevTools để xem `secure`, `httpOnly`, `sameSite`, `domain`, `path`, `expires`. Không dùng `document.cookie` để khẳng định cookie `HttpOnly` không được tạo: thuộc tính đó cố ý ẩn cookie khỏi JavaScript.

Test với HTTPS public URL và các browser được tổ chức hỗ trợ, đặc biệt khi có cross-site SSO hoặc third-party cookies. Môi trường localhost có các ngoại lệ Secure, vì vậy không đại diện đầy đủ cho production.

## 12. Kiểm thử tích hợp với CDN, proxy, gateway và session store

Một filter test xanh ở origin không chứng minh public URL đang được bảo vệ. Test triển khai cần kiểm tra đường đi và các tầng chịu trách nhiệm:

| Ranh giới | Tình huống | Bằng chứng cần thu |
|---|---|---|
| Browser → Edge TLS | HTTP redirect và HTTPS HSTS | Location dùng host công khai, HSTS đúng policy |
| Edge → Gateway | Forwarded host/proto/IP | Redirect OAuth đúng external origin; không tin header client giả |
| Gateway → Spring | Authentication, CSRF, CORS, path rewrite | Request thật đi qua đúng filter chain, không bypass matcher |
| Spring → CDN cache | Dữ liệu người dùng, cookie, CSRF token | CDN bypass shared cache, response có no-store |
| Load balancer → nhiều instance | Session đăng nhập, logout, session timeout | Không mất phiên giữa node khi cần; phiên bị revoke không hoạt động lại |
| Browser → SSO IdP | Callback, state/PKCE, cookie SameSite | Luồng hợp lệ thành công, state/nonce giả bị từ chối |

### 12.1. Lệnh quan sát header công khai

~~~bash
# GET với response headers công khai; không dùng -I nếu endpoint xử lý HEAD khác GET.
curl -sS -D - -o /dev/null https://app.example.com/login

# Không tự theo redirect để quan sát Location gốc.
curl -sS -D - -o /dev/null --max-redirs 0 https://app.example.com/account

# Preflight CORS: kiểm tra chính policy ở public URL.
curl -sS -i -X OPTIONS https://api.example.com/api/orders \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

`curl` **không tự thi hành SameSite, HttpOnly, CSP, HSTS hoặc CORS như browser**; nó chỉ giúp quan sát request/response. Không chạy `curl -I /logout` để chứng minh logout, vì hành trình logout thường yêu cầu POST kèm CSRF token.

### 12.2. Kiểm thử dữ liệu riêng tư có bị CDN cache chung không?

Dùng hai tài khoản thử Alice/Bob:

1. Alice gọi `GET /api/me`; lưu body và cache status.
2. Bob gọi cùng path với phiên khác; xác minh **chỉ thấy dữ liệu Bob**.
3. Gọi lặp lại khi cache đã ấm. Không chỉ test response đầu tiên.
4. Kiểm tra `Cache-Control: no-store` và rule CDN bypass cho path dữ liệu xác thực.
5. Lặp lại với response `401`, `403`, token hết hạn và route có query/path parameters.

Không cố giải quyết cache riêng tư bằng cache key chứa raw access token hoặc full cookie nếu chưa có thiết kế kiểm soát chặt. Những giá trị đó là bí mật và không được xuất ra log.

### 12.3. Path encoding và HTTP firewall

Test các URL bất thường với dữ liệu giả và quyền hạn thích hợp:

~~~text
/api/admin%2Fusers
/api//admin/users
/api/admin;mode=test/users
/api/%2e%2e/admin
~~~

Ở Servlet, `StrictHttpFirewall` mặc định từ chối nhiều biến thể path/HTTP method không an toàn. Test nhằm xác nhận **gateway và application không bất đồng cách normalize URL**, chứ không phải cố ép mọi encoded URL đều trả cùng status. Kỳ vọng quan trọng: không route vòng qua authentication/authorization, không phát sinh side effect.

## 13. Chẩn đoán regression bằng bằng chứng theo tầng

| Triệu chứng sau nâng cấp | Nguyên nhân thường gặp | Điều cần xác minh trước khi sửa |
|---|---|---|
| Form login POST trả `403` | CSRF token bị thiếu, mới tạo nhưng chưa được gửi, cookie/header sai | Token repository/handler, form và network request |
| Login thành công nhưng request sau thành anonymous | Cookie không được chấp nhận, SameSite/Domain/Path, session store | `Set-Cookie`, cookie jar, session ID và backend logs |
| OAuth callback trả lỗi state | State cookie/session bị mất, redirect URI/host thay đổi, nhiều tab | State đã tạo, cookie path/same-site, forwarded headers |
| Refresh gọi lặp vô hạn | Token hết hạn, request concurrency, refresh rotation hoặc interceptor | Request timeline và trạng thái refresh token trên server |
| Response mất HSTS | Proxy TLS termination hoặc writer bị vô hiệu hóa | HTTPS public header và cách Spring nhận diện secure request |
| CSP chặn JavaScript hợp lệ | Nonce/hash không khớp, CDN cache HTML, CSP trùng | Console CSP violation và headers từ origin/edge |
| `OPTIONS` CORS trả `401/403` | Preflight bị auth filter/gateway chặn | Có cookie trên preflight không, thứ tự CORS/auth |
| Browser báo nhiều giá trị CORS | Edge và Spring cùng phát `Access-Control-Allow-Origin` | Toàn bộ headers public response |
| Logout xong session vẫn dùng được | Chỉ xóa cookie/UI, chưa invalidate server session/revoke token | Request API sau logout với định danh cũ trong test environment |
| MockMvc pass, browser fail | SameSite, third-party cookie, CORS enforcement, CSP, CDN | Browser network, storage, console và trace ID |
| Một số node làm mất session | Chưa dùng shared session hoặc sticky session không đảm bảo | Session persistence và routing tới từng node |

Khi điều tra, giữ **trace/request ID** xuyên edge, gateway và Spring. Ghi tên sự kiện (`LOGIN_SUCCESS`, `CSRF_DENIED`, `TOKEN_EXPIRED`, `SESSION_INVALIDATED`), thời gian, path đã chuẩn hóa, tầng ra quyết định và loại policy. **Không ghi raw Authorization header, password, CSRF token, refresh token, session cookie hay ID token**. Nếu phải đối chiếu session, dùng mã tương quan được tạo riêng, không công khai bí mật.

## 14. Tổ chức pipeline và tiêu chí phát hành

Một suite có giá trị cần **quy tắc chạy và xử lý thất bại rõ ràng**:

| Thời điểm | Bộ test | Điều kiện dừng |
|---|---|---|
| Mỗi PR thay auth/security | Unit contract + MockMvc/WebTestClient | CSRF, authorization, headers hoặc login unit fail |
| Mỗi build bản release | Integration với session store, JWT issuer/IdP giả, browser E2E chính | Login/logout/refresh/callback sai contract |
| Trước và sau thay CDN/gateway | Public URL smoke, CORS, cookie, HSTS, cache leak | Sai security header, login loop, private cache hit |
| Khi nâng major Spring/Boot/browser | Ma trận phiên bản + negative scenarios và test proxy | Thay đổi token/session/cookie behavior ngoài dự tính |
| Sau deploy | Synthetic journey dùng account riêng + metric/log | Tăng bất thường auth failure/CSRF/CORS, lỗi người dùng thực |

**Thực hành giảm flaky tests:**

- Dùng account và dữ liệu riêng cho từng test, tự dọn; tránh phụ thuộc thứ tự chạy.
- Fake clock cho expiry/revocation thay vì `Thread.sleep`.
- Không dùng test chỉ assert “status khác 500”; kiểm tra quyền, body, side effect, headers và session state theo từng contract.
- Với redirect, kiểm tra đúng external scheme, host, path và các tham số cần thiết; tránh assert toàn bộ URI động nếu có `state`/nonce.
- Với cookie, kiểm tra thuộc tính và sự chấp nhận trên browser; không so sánh session ID cố định.
- Tách các test cần server thật khỏi các test có thể mô phỏng SecurityContext, tránh giả định `mockUser()` có thể xác thực qua network.
- Chỉ chấp nhận bỏ qua test khi có lý do được ghi nhận và người sở hữu chính sách duyệt; một test bảo mật bị tắt có thể che regression thật.

### 14.1. Lưu bằng chứng phục vụ code review và điều tra

Mỗi lần nâng cấp nên có:

1. Ma trận test versioned ghi tình huống, expected, tầng chạy và owner.
2. Kết quả test gồm revision, Spring/Spring Boot/browser version, môi trường, thời gian và commit cấu hình CDN/gateway.
3. Một số mẫu response headers đã loại bỏ bí mật; trace ID của các lỗi.
4. Báo cáo thay đổi policy dự kiến, đặc biệt CSRF, CORS, CSP, HSTS, cookie, session và OAuth/OIDC.
5. Các lỗ hổng còn tồn tại/ngoại lệ được ghi rõ điều kiện chấp nhận và kế hoạch xử lý.

## 15. Bài tập: thiết kế regression suite cho hệ thống ba origin

**Bối cảnh:** frontend React ở `https://portal.example.com`, API Spring Security ở `https://api.example.com` và IdP ở `https://login.identity.example`. API cho phép xác thực bằng session cookie sau OIDC login; có CSRF cho request sửa dữ liệu. CDN cache static assets; gateway kết thúc TLS; backend chạy hai instance. Sắp nâng Spring Boot và đổi policy CORS tại gateway.

Tại lần smoke test đầu tiên, đăng nhập OIDC thành công. Tuy nhiên, POST cập nhật hồ sơ đôi khi trả `403`; refresh trang làm mất session ở một số request; browser thấy hai header CORS; đội QA còn phát hiện thiếu HSTS ở một số response.

**Yêu cầu:**

1. Đề xuất tối thiểu **12 regression cases** gồm cả positive và negative; chia các nhóm token, header, cookie, journey.
2. Mỗi test mô tả precondition, action, expected, tầng thực thi và bằng chứng.
3. Chỉ ra test nào phải đi qua public URL, test nào có thể làm bằng MockMvc/WebTestClient.
4. Nếu phải chọn ba kiểm thử được chạy ngay trước khi tăng traffic, hãy giải thích thứ tự ưu tiên.

**Gợi ý đáp án:**

| Nhóm | Case bắt buộc | Kết quả/ý nghĩa |
|---|---|---|
| Token | CSRF đúng | Authenticated POST có token hợp lệ thành công |
| Token | CSRF thiếu/sai | POST bị chặn và dữ liệu không đổi |
| Token | OAuth `state` đúng và sai | Chỉ callback khớp yêu cầu login mới tạo session |
| Token | Callback code replay | Không cấp phiên mới khi code đã dùng |
| Header | CORS origin được phép | Preflight thành công và không có header trùng |
| Header | CORS origin lạ | Browser không có quyền đọc response |
| Header | HSTS trên HTTPS | Public response mang policy đã duyệt |
| Header | Cache private API | `/api/me` không bị shared cache |
| Cookie | `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` | Browser chấp nhận cookie theo mục đích |
| Cookie | Session fixation | Session ID đổi khi login nếu dùng Servlet session strategy |
| Journey | Đăng nhập + load balance giữa hai node | Session được giữ đúng, API trả thông tin của user hiện tại |
| Journey | Logout + request dùng phiên cũ | API từ chối sau logout |
| Journey | Mở hai tab rồi logout một tab | Server từ chối request mới bằng session đã hủy |
| Journey | OAuth redirect từ public URL | Callback dùng HTTPS, host đúng, không lộ host nội bộ |

Ba ưu tiên khi mở rộng traffic: **(1)** form/OIDC login và session qua hai instance, vì lỗi ảnh hưởng người dùng ngay; **(2)** POST có CSRF hợp lệ và thiếu/sai, vì phải phát hiện cả lỗi chức năng lẫn bypass bảo mật; **(3)** preflight CORS và HSTS qua public URL, vì thay đổi gateway có thể làm lệch hành vi dù test tại origin vẫn xanh. Nếu CDN vừa đổi chính sách cache, bổ sung kiểm tra hai user `/api/me` thành **release blocker** theo mức rủi ro rò dữ liệu.

## 16. Những nguyên tắc cần nhớ

- Kiểm thử hồi quy bảo mật phải có cả **đường đi hợp lệ** lẫn **đường đi bị từ chối**, và xác minh không có side effect trái phép.
- Token được đánh giá theo **nơi tạo, nơi lưu, nơi xác minh và vòng đời**; session ID, CSRF, OAuth state, nonce, JWT và refresh token không cùng một hợp đồng.
- Chỉ test HTTP header ở MockMvc/WebTestClient là chưa đủ: cookie, CORS, CSP và HSTS còn phải được xác minh trên **browser qua HTTPS công khai**.
- Phân biệt **same-site**, **same-origin**, CORS và SameSite; đừng sửa CSRF bằng cách tắt CSRF hoặc cho phép CORS `*` tràn lan.
- Logout an toàn đòi xử lý trạng thái xác thực **phía server**; xóa cookie/UI hoặc `Clear-Site-Data` là lớp bổ sung.
- Suite cần liên kết được các quyết định ở Spring Security, frontend, proxy, gateway, CDN và IdP, với bằng chứng truy vết và người chịu trách nhiệm.

## Tài liệu tham khảo

- [Spring Security — Testing with CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): sử dụng `csrf()`, `asHeader()` và `useInvalidToken()` trong MockMvc.
- [Spring Security — Testing Form Based Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): helper `formLogin()` và kiểm thử authenticated/unauthenticated.
- [Spring Security — Testing CSRF (Reactive)](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): sử dụng `WebTestClient` với `csrf()`.
- [Spring Security — Testing Authentication (Reactive)](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `springSecurity()`, `mockUser()` và kiểm thử WebFlux.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): các header mặc định và HSTS trên HTTPS.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session fixation, rotation, lưu security context, logout.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) và [OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): kiểm thử đúng loại auth.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path` và cookie prefixes.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, credentials, `Vary` và browser enforcement.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, thời hạn, logout, logging và cache.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF token, SameSite và các ranh giới kiểm soát.
- [Playwright — Authentication](https://playwright.dev/docs/auth) và [BrowserContext cookies](https://playwright.dev/docs/api/class-browsercontext#browser-context-cookies): browser automation và kiểm tra cookie của context.

