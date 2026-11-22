# WWW-Authenticate cho HTTP Basic và Bearer trong Spring Security

## 1. Bài toán: vì sao API trả 401 mà client không biết phải đăng nhập theo cách nào?

Một API Java được bảo vệ có thể nhận yêu cầu mà **không có credential**, có credential sai, hoặc có credential hợp lệ nhưng **thiếu quyền**. Chỉ trả JSON `{"error":"unauthorized"}` không giải thích rõ **cơ chế xác thực mà HTTP client phải sử dụng**. HTTP có một giao thức *challenge–response* qua header:

- Server trả **`WWW-Authenticate`** trong **HTTP response** để thông báo một hay nhiều **authentication scheme** áp dụng cho tài nguyên.
- Client có thể thử lại với **`Authorization`** trong **HTTP request**, cung cấp credential theo đúng scheme.
- `401 Unauthorized` nói rằng chưa có **credential hợp lệ** cho tài nguyên; `403 Forbidden` thường nói credential được công nhận nhưng **không có quyền** thực hiện hành động.
- `Basic` và `Bearer` có **cú pháp, vòng đời credential, xử lý lỗi, threat model khác nhau**. Không dùng chúng thay thế cho nhau.

Ví dụ khi gọi endpoint cần HTTP Basic:

~~~http
GET /basic/report HTTP/1.1
Host: api.example.org

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Legacy Lab"
~~~

Với một endpoint OAuth 2.0 Resource Server:

~~~http
GET /bearer/report HTTP/1.1
Host: api.example.org

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="Report API"
~~~

**Mục tiêu học tập:**
1. Đọc, tạo và kiểm thử header `WWW-Authenticate` đúng theo HTTP semantics.
2. Phân biệt **challenge** ở response với **credential** ở request, và `WWW-Authenticate` với `Proxy-Authenticate`.
3. Hiểu Basic `realm`, Base64, `charset="UTF-8"`, browser credential prompt và HTTPS.
4. Hiểu Bearer `realm`, `error`, `error_description`, `error_uri`, `scope`; phân biệt `invalid_request`, `invalid_token` và `insufficient_scope`.
5. Ánh xạ **401/403** vào Spring Security `AuthenticationEntryPoint` và `AccessDeniedHandler`.
6. Cấu hình Spring Boot Java 17+ hai filter chain tách biệt cho Basic và Bearer, quan sát kết quả và viết MockMvc tests.
7. Tránh các lỗi production như mất header do handler/proxy, trả 401 sai trường hợp, lộ token trong log và quảng bá nhầm auth scheme.

## 2. Hợp đồng HTTP: WWW-Authenticate là lời mời xác thực

Theo [RFC 9110, `11.3 và `11.6.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-11.6.1):

- Server trả `401` **phải** gửi ít nhất một challenge có thể áp dụng qua `WWW-Authenticate`.
- Header có thể xuất hiện trên status khác khi việc dùng credential khác có thể giúp truy cập; **không** có nghĩa mọi `403` đều phải chứa challenge.
- Một response có thể chứa **nhiều challenge**, nằm trên nhiều header field hoặc trong danh sách theo cú pháp HTTP. Client chọn scheme mà nó hiểu và có thể đáp ứng.
- `407 Proxy Authentication Required` sử dụng `Proxy-Authenticate`, không phải `WWW-Authenticate`; client gửi `Proxy-Authorization` tới proxy, không gửi như credential của origin server.

Cú pháp khái quát:

~~~text
WWW-Authenticate: <auth-scheme> [challenge-data]
Authorization: <auth-scheme> <credentials>
~~~

Trong HTTP, **request** và **response** khác nhau. Không viết `WWW-Authenticate` vào request rồi chờ server xác thực. Không dùng `Authorization: Bearer ...` như một response challenge. Một client biết sẵn chính sách endpoint có thể **gửi Authorization trước** khi nhận `401` (preemptive authentication); vẫn phải tuân theo scheme và bảo vệ credential.

### 2.1. Bảng so sánh ba header thường bị lẫn

| Header | Chiều | Ý nghĩa | Đi kèm |
| --- | --- | --- | --- |
| `WWW-Authenticate` | Response từ **origin server** | Thách thức client dùng scheme phù hợp với tài nguyên | Chủ yếu `401`; đôi khi status khác |
| `Authorization` | Request tới **origin server** | Credential mà client tự cung cấp | `Basic ...`, `Bearer ...` hoặc scheme khác |
| `Proxy-Authenticate` | Response từ **proxy** | Proxy yêu cầu xác thực trước khi chuyển tiếp | `407` |
| `Proxy-Authorization` | Request tới **proxy** | Credential dành cho proxy | Sau challenge `407` hoặc gửi trước |

Ví dụ:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="Corporate Proxy"
~~~

Đây không phải server API từ chối access token; đây là proxy yêu cầu xác thực của **chính proxy**. Client gửi `Proxy-Authorization` tới proxy được tin, không chuyển mật khẩu proxy cho API origin.

### 2.2. Challenge có thể có nhiều tham số

Một Basic challenge:

~~~http
WWW-Authenticate: Basic realm="Legacy Lab", charset="UTF-8"
~~~

Một Bearer challenge:

~~~http
WWW-Authenticate: Bearer realm="Report API", error="invalid_token"
~~~

Dấu phẩy ở đây có thể ngăn **các auth-param của cùng một challenge**, không nhất thiết đánh dấu một challenge mới. HTTP cũng cho phép gửi nhiều challenges. Vì vậy:
- **Không parse** `WWW-Authenticate` bằng cách chia chuỗi `split(",")` rồi coi mọi mảnh là một scheme.
- Giá trị trong dấu ngoặc kép có thể có ký tự thoát và dấu phẩy; parser cần tuân theo cú pháp HTTP.
- Không giả định có đúng một header field hoặc một challenge; dùng HTTP library phù hợp.

Ví dụ response có nhiều scheme:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Legacy"
WWW-Authenticate: Bearer realm="Report API"
~~~

Về mặt HTTP có thể cung cấp nhiều lựa chọn. Nhưng **không tự bật cả hai trong Spring chỉ vì một endpoint có thể trả nhiều header**; phải thiết kế và kiểm thử chính sách thực tế, thứ tự filter, tương tác browser prompt và cách mỗi scheme xác thực/authorize.

## 3. Status 401 và 403: đã xác thực hay chưa?

| Tình huống | HTTP status thường phù hợp | `WWW-Authenticate` |
| --- | --- | --- |
| Tài nguyên bảo vệ, request không có credential | **401** | **Có**, ví dụ `Basic realm="..."` hoặc `Bearer` |
| Basic password sai hoặc không giải mã được thành credential hợp lệ | **401** | Challenge Basic theo policy |
| Bearer access token expired/revoked/invalid signature/audience | **401** | Bearer kèm `error="invalid_token"` khi phù hợp |
| Bearer token hợp lệ, thiếu scope mà endpoint yêu cầu | **403** | Có thể có Bearer `error="insufficient_scope"` |
| Basic user hợp lệ, role không đủ | **403** | Không bắt buộc challenge; trả 401 có thể làm client nhập lại password vô ích |
| Request Bearer sai định dạng, nhiều phương thức truyền token | Thường **400** theo RFC 6750 `invalid_request` | Bearer challenge/error khi phù hợp |
| Resource được che giấu theo chính sách, tránh xác nhận sự tồn tại | Có thể **404** | Không để lộ chi tiết không cần thiết |
| Lỗi CSRF token trên unsafe request | Thường **403** | Không mặc nhiên là Basic/Bearer token invalid |
| Rate limiting hoặc sự cố upstream | `429` hoặc `5xx` theo nguyên nhân | Không quảng bá auth lại nếu lỗi không phải credential |

**Cảnh báo về tên mã HTTP:** `401 Unauthorized` thực chất mô tả *thiếu hoặc sai authentication credentials*. Nó không phải nghĩa tiếng Việt “đã đăng nhập nhưng không được phép”, thường thuộc `403`. Đừng để tên mã dẫn tới xử lý ngược.

Nếu resource server nhận token **đúng chữ ký nhưng sai `aud`/`iss`**, đây vẫn là **token không hợp lệ cho resource hiện tại**, thường `401 invalid_token`, không phải `403 insufficient_scope`. Kiểm tra scope chỉ sau khi token đã được xác minh hợp lệ cho API.

## 4. HTTP Basic: WWW-Authenticate: Basic realm="..."

[**RFC 7617**](https://www.rfc-editor.org/rfc/rfc7617.html) định nghĩa HTTP Basic Authentication.

**Challenge:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Documents"
~~~

**Credential trong request kế tiếp:**

~~~http
GET /documents/private HTTP/1.1
Host: api.example.org
Authorization: Basic dGVzdDoxMjM=
~~~

Chuỗi `dGVzdDoxMjM=` là Base64 của chuỗi ASCII `test:123`. **Base64 chỉ là mã hóa biểu diễn, không phải encryption**. Bất kỳ ai đọc được header này có thể giải mã username/password. Vì vậy **luôn dùng HTTPS** và không lưu header credential trong logs/traces.

### 4.1. `realm` trong Basic là gì?

`realm` là tham số **bắt buộc** của challenge Basic; nó đặt tên **protection space** trong phạm vi origin để client biết nhóm tài nguyên dùng credential nào. Ví dụ:

~~~http
WWW-Authenticate: Basic realm="Internal Reports"
~~~

Nội dung realm có thể xuất hiện trong browser native login dialog hoặc credential cache. Không đặt password, thông tin nhạy cảm, ID tenant bí mật hoặc dữ liệu cá nhân vào tên realm. Cùng một tên realm không tự bảo đảm mọi URL/host có cùng quyền; client cần kiểm tra **origin, scheme, TLS và phạm vi bảo vệ**.

Đổi realm có thể làm browser/HTTP client coi resource là một protection space khác và yêu cầu credential lại. Đừng thay realm tùy tiện ở mỗi request; cấu hình ổn định và tránh dùng user input để tạo realm.

### 4.2. UTF-8 trong Basic challenge

RFC 7617 cho phép:

~~~http
WWW-Authenticate: Basic realm="Documents", charset="UTF-8"
~~~

`charset="UTF-8"` thể hiện server mong chờ cách xử lý Unicode/UTF-8 phù hợp (cùng NFC normalization theo RFC 7617). Tham số `charset` nằm trong **challenge**, **không** đặt `charset` vào `Authorization` credential theo một cú pháp Basic riêng. Với username/password Unicode, client và server cần đồng ý xử lý encoding. Nếu không thông báo `charset`, cách mã hóa mặc định lịch sử không được xác định hoàn toàn, có thể gặp khác biệt tương thích.

### 4.3. Basic và trình duyệt

Khi browser gặp `401` kèm `WWW-Authenticate: Basic ...`, nó có thể mở giao diện native yêu cầu username/password, hoặc sử dụng credential đã lưu. Với HTTP clients như `curl`, code có thể tự retry. **Đừng trông chờ browser luôn bật dialog**:
- `fetch`/XHR trong frontend có xử lý riêng; Spring Security có cơ chế tránh một số browser dialog đối với AJAX request, tùy version và header.
- Proxy, API gateway, CORS và custom authentication entry point có thể thay đổi header.
- Form login truyền thống sử dụng HTML/cookie/session; nó **không** đồng nghĩa với HTTP Basic mặc dù đều yêu cầu username/password.

HTTP Basic gửi lại credential trên mỗi request nếu client dùng scheme đó; nên tránh dùng nó cho trải nghiệm browser hiện đại và các dịch vụ có mức nhạy cảm cao khi có phương thức mạnh hơn. Bật MFA, bảo vệ password storage, rate limit, TLS và policy account theo yêu cầu.

## 5. OAuth 2.0 Bearer: WWW-Authenticate: Bearer

Theo [**RFC 6750, `3**](https://www.rfc-editor.org/rfc/rfc6750#section-3), Bearer challenge dùng scheme `Bearer` và có thể chứa các auth-param. Trong mô hình OAuth:

- **Authorization Server** cấp access token cho client.
- **Client** gửi access token qua `Authorization: Bearer <access_token>` tới **Resource Server**.
- **Resource Server** xác minh token theo contract issuer, lifetime, audience và scope/authority, rồi quyết định truy cập.
- Nếu không có token hợp lệ, RS phản hồi theo cơ chế HTTP Bearer challenge.

Ví dụ request:

~~~http
GET /reports/42 HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...opaque-or-jwt...
~~~

**Token trong ví dụ chỉ là ký hiệu minh họa.** Access token **không bắt buộc là JWT**; có thể là chuỗi opaque được kiểm tra bằng introspection. `Bearer` nói cách trình credential, không nói token được ký theo thuật toán nào.

### 5.1. Không có token: 401 và không tiết lộ thêm lỗi

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="Report API"
~~~

Khi request **không có bất kỳ authentication information nào**, RFC 6750 khuyến nghị **không** thêm `error` hoặc mô tả lỗi. Chỉ cho client biết tài nguyên dùng Bearer là đủ. Không trả `invalid_token` khi thực tế client chưa gửi token.

Một số Spring Resource Server để header chỉ là `WWW-Authenticate: Bearer`, không có `realm`. Điều đó bình thường: **realm là optional** cho Bearer. Không viết test bắt buộc phải có `realm="..."` nếu chưa cấu hình.

### 5.2. Token không hợp lệ: invalid_token

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="Report API",
                  error="invalid_token"
~~~

`invalid_token` dùng khi token hết hạn, bị thu hồi, bị giả mạo, không đúng định dạng, không có hiệu lực với API hoặc không hợp lệ theo policy. RFC 6750 mô tả status thường là **401**. Client có thể xin token mới từ Authorization Server và retry theo policy, nhưng **không được retry vô hạn** khi token không hợp lệ hoặc thiếu quyền.

Có thể có:

~~~http
WWW-Authenticate: Bearer realm="Report API",
                  error="invalid_token",
                  error_description="The access token expired"
~~~

**Chỉ là ví dụ giao thức**. Production không nên tiết lộ chi tiết nhạy cảm như nguyên token, key ID nội bộ, thuật toán/tên certificate, introspection response, stack trace hay nguyên nhân kiểm tra JWT cụ thể. Error description không phải kênh debug dành cho attacker; log nội bộ có request ID và thông tin đã che phù hợp.

### 5.3. Token hợp lệ nhưng thiếu scope: insufficient_scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="Report API",
                  error="insufficient_scope",
                  scope="reports.write"
~~~

`insufficient_scope` nghĩa token có thể hợp lệ về authentication nhưng thiếu đặc quyền cần thiết để truy cập tài nguyên. RFC 6750 khuyến nghị **403** và **cho phép** thêm `scope` mô tả scope cần thiết. `scope` chứa một danh sách scope **cách nhau bằng dấu cách**; các scope là giá trị **case-sensitive** và phụ thuộc chính sách resource server.

Có thể header chỉ chứa:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

nếu server không muốn/cần công khai scope cụ thể. **Đừng gửi một token có scope khác vào API rồi nghĩ có thể sửa lỗi 403 bằng cách refresh cùng grant**: cần client được cấp quyền đúng, có consent/authorization policy phù hợp và phải bảo đảm quyền nghiệp vụ của resource.

### 5.4. Token request không hợp lệ: invalid_request

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

RFC 6750 khuyến nghị 400 cho `invalid_request` như thiếu tham số bắt buộc, tham số trùng, dạng truyền không hợp lệ hoặc client thử truyền access token qua **nhiều phương thức cùng lúc**. Mỗi framework/decoder có thể có behavior cụ thể; test theo contract của API và RFC.

Không dùng `invalid_request` như mã mặc định khi JWT ký sai: nếu credential được nhận diện nhưng **token invalid**, phần lớn tình huống thuộc `invalid_token`.

## 6. Bảng các trường Bearer challenge

| Trường | Bắt buộc? | Ý nghĩa | Lưu ý |
| --- | --- | --- | --- |
| `Bearer` | Scheme | Chỉ cho client cách gửi access token | Không cần `realm` để scheme hợp lệ |
| `realm` | Optional | Phạm vi tài nguyên được bảo vệ | Không gắn dữ liệu bí mật |
| `error` | Optional | Mã chuẩn `invalid_request` / `invalid_token` / `insufficient_scope` | Không gửi lỗi nếu thiếu hẳn auth information theo khuyến nghị RFC |
| `error_description` | Optional | Mô tả ngắn có thể giúp client | Không bao giờ trả token, secret, stack trace |
| `error_uri` | Optional | URI tới tài liệu hướng dẫn lỗi | Dùng URL cố định, không kèm credential/query nhạy cảm |
| `scope` | Optional | Scope cần có theo policy; thường trong `insufficient_scope` | Cách nhau dấu cách, case-sensitive; có thể không cần công khai |
| Extension auth-param | Theo contract | Dữ liệu mở rộng do server định nghĩa | Không đặt tùy ý nội dung không được RFC cho phép |

**Cẩn thận dấu ngoặc kép:** realm, description và danh sách scope thường dùng quoted-string. Không nối raw user input vào `WWW-Authenticate`; dùng builder/exception handler chuẩn, escape đúng ký tự theo RFC. Không thêm CR/LF từ request param để tránh response header injection.

## 7. 401, 403 và Bearer error: ma trận quyết định

| Tình huống tại Resource Server | HTTP | Header minh họa |
| --- | --- | --- |
| Không có `Authorization` | 401 | `WWW-Authenticate: Bearer` |
| Header scheme không phù hợp, không có Bearer hợp lệ | 401 hoặc 400 tùy nguyên nhân | Challenge Bearer không tiết lộ thêm |
| Bearer token expired | 401 | `Bearer error="invalid_token"` |
| Bearer JWT invalid signature/issuer/audience | 401 | `Bearer error="invalid_token"` |
| Opaque token bị revoke hoặc introspection báo inactive | 401 | `Bearer error="invalid_token"` |
| Bearer token hợp lệ có `reports.read`, endpoint yêu cầu `reports.write` | 403 | `Bearer error="insufficient_scope"` khi handler có chứng cứ |
| Malformed multiple methods for token | Thường 400 | `Bearer error="invalid_request"` |
| Bearer token hợp lệ, object thuộc tenant khác | 403 hoặc 404 theo policy | Không bắt buộc tiết lộ scope/owner |
| Basic user hợp lệ nhưng role không đủ | 403 | Không mặc định cần Basic challenge |
| Basic password sai | 401 | `Basic realm="..."` |

**Một nuance của Spring Security:** `BearerTokenAccessDeniedHandler` chỉ sinh `insufficient_scope` khi nó có thể xác định request đã có một OAuth2 `Authentication` hợp lệ. Nếu không chứng minh được, handler có thể chỉ phát scheme `Bearer`. Đừng assert `insufficient_scope` trên mọi `403` không phân biệt principal.

### 7.1. Đừng trộn authorization của token với HTTP auth challenge

Một access token có `SCOPE_reports.read` không bảo đảm chủ thể được đọc **bản ghi bất kỳ** trong API. Resource Server còn kiểm tra tenant, ownership, RBAC/ABAC, chính sách domain. Nếu principal không được xem bản ghi 42 mặc dù scope đúng, đây là authorization failure nghiệp vụ. Không bắt buộc phải trả `scope="reports.read"` vì token đã có scope này.

Ngược lại, token dành cho API A được gửi tới API B **không** là “thiếu role nghiệp vụ” mà là token không hợp lệ cho audience của B; cần từ chối trước khi authorization vào object.

## 8. Spring Security đặt WWW-Authenticate ở đâu?

Spring Security Servlet có các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `SecurityFilterChain` / `FilterChainProxy` | Chọn đúng tập filter cho endpoint |
| `AuthorizationFilter` | Kiểm tra quyền của request; có thể sinh `AccessDeniedException` |
| `ExceptionTranslationFilter` | Chuyển authentication/authorization exception thành entry point hoặc denied handler phù hợp |
| `AuthenticationEntryPoint` | Bắt đầu quá trình authentication cho client; với Basic/Bearer thường tạo `401` + challenge |
| `AccessDeniedHandler` | Xử lý authenticated principal bị thiếu quyền; thường `403` |
| `BasicAuthenticationFilter` | Đọc `Authorization: Basic ...`, tạo auth request cho username/password |
| `BearerTokenAuthenticationFilter` | Đọc `Authorization: Bearer ...`, tạo auth request cho token |
| `BasicAuthenticationEntryPoint` | Có thể gửi `WWW-Authenticate: Basic realm="..."` |
| `BearerTokenAuthenticationEntryPoint` | Sinh Bearer challenge và error params theo `BearerTokenError` |
| `BearerTokenAccessDeniedHandler` | Xử lý access denied theo RFC 6750, gồm `insufficient_scope` khi thích hợp |

Dòng xử lý khái quát:

~~~text
HTTP request
    |
    v
FilterChainProxy chọn SecurityFilterChain
    |
    +-- Có Authorization Basic? --> BasicAuthenticationFilter
    |
    +-- Có Authorization Bearer? -> BearerTokenAuthenticationFilter
    |
    v
AuthenticationManager / Provider / token verifier
    |
    +-- Không có credential / credential invalid
    |      -> AuthenticationEntryPoint
    |      -> 401 + WWW-Authenticate
    |
    +-- Authentication hợp lệ
           |
           v
      AuthorizationFilter kiểm tra role/scope/policy
           |
           +-- Đủ quyền -> controller -> 200/2xx
           |
           +-- Thiếu quyền -> AccessDeniedHandler
                                      -> 403; có thể có Bearer challenge
~~~

Đây là sơ đồ **logic**, không phải mô tả mọi thứ tự lọc chính xác. Với authentication failure ở Basic/Bearer, filter có thể gọi entry point trực tiếp; với request không có credential, `ExceptionTranslationFilter` xử lý exception authorization. Thứ tự thực tế còn phụ thuộc cách cấu hình filter chain và framework version.

**Không tự thay entry point bằng JSON handler chỉ gửi `401` nhưng quên `WWW-Authenticate`.** Theo RFC 9110, origin server trả 401 phải có challenge. Nếu giao diện SPA muốn JSON và không muốn browser Basic dialog, cần thiết kế đúng frontend/API contract **và** chính sách HTTP authentication, không phá tuân thủ mà không nhận biết.

### 8.1. Spring Security và AJAX Basic

Tài liệu Spring Security 6.5 có lưu ý: hỗ trợ Basic mặc định có cách xử lý request kiểu AJAX nhằm tránh browser hiện native Basic login dialog; việc phát `WWW-Authenticate` và response body có thể thay đổi theo header xác định XMLHttpRequest/configuration.

Do đó, khi kiểm thử challenge Basic:
- Dùng client HTTP thuần hoặc `MockMvc` request **không** mô phỏng AJAX header nếu muốn kiểm tra challenge mặc định.
- Nếu cần custom JSON error cho SPA, kiểm tra tương tác `AuthenticationEntryPoint` ở filter chain thực.
- Không kết luận rằng mọi response thiếu challenge đều do proxy; hãy xem entrypoint và điều kiện request của phiên bản đang chạy.

Đây là **ngoại lệ implementation** cần biết; không phải lý do coi quy tắc 401 của RFC 9110 là không còn giá trị. Nếu một API bắt buộc tuân thủ chuẩn, hãy cung cấp challenge thích hợp qua custom entrypoint cho các path/clients đó.

## 9. Ví dụ hoàn chỉnh Java 17+: hai endpoint Basic và Bearer có challenge riêng

Mục tiêu của lab: **không cần Authorization Server thật hoặc JWT signing infrastructure** nhưng vẫn quan sát được Spring Security Basic + OAuth2 Resource Server Bearer challenge. Một `OpaqueTokenIntrospector` **mô phỏng** hai token cố định, giúp kiểm tra HTTP status và header. **Chỉ dùng trên localhost để học, tuyệt đối không dùng dạng introspector chấp nhận token cố định này ở production.**

Lab dựa trên Java 17, Spring Boot **3.3.12**, Spring Security Servlet và Spring Test. API có:
- `GET /basic/report`: Basic user/password đúng trả `200`.
- `GET /basic/admin`: Basic user `reader` không có `ROLE_ADMIN` nên trả `403`.
- `GET /bearer/read`: Bearer token cần `SCOPE_reports.read`.
- `GET /bearer/write`: Bearer token cần `SCOPE_reports.write`.

### 9.1. Tạo project Gradle

~~~text
auth-challenge-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/challenge/
    │   ├── ChallengeApplication.java
    │   ├── SecurityConfig.java
    │   └── ProtectedController.java
    └── test/java/demo/challenge/
        └── ChallengeSecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'auth-challenge-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Có thể tạo Gradle Wrapper theo môi trường, hoặc chạy `gradle test`/`gradle bootRun` nếu máy đã cài Gradle tương thích. Đây là một **ứng dụng Servlet**, không dùng WebFlux.

### 9.2. Entry point ứng dụng

`src/main/java/demo/challenge/ChallengeApplication.java`:

~~~java
package demo.challenge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChallengeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChallengeApplication.class, args);
    }
}
~~~

### 9.3. Hai SecurityFilterChain tách biệt

`src/main/java/demo/challenge/SecurityConfig.java`:

~~~java
package demo.challenge;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("lab-password-123"))
                        .roles("USER")
                        .build());
    }

    // /bearer/** chỉ chấp nhận OAuth2 Bearer do Resource Server xử lý.
    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/bearer/**")
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/bearer/read")
                            .hasAuthority("SCOPE_reports.read")
                        .requestMatchers("/bearer/write")
                            .hasAuthority("SCOPE_reports.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }

    // /basic/** chỉ dùng HTTP Basic với realm riêng.
    @Bean
    @Order(2)
    SecurityFilterChain basicApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/basic/**")
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/basic/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(basic -> basic.realmName("Legacy Lab"))
                .build();
    }

    // Không vô tình mở các URL ngoài hai vùng demo.
    @Bean
    @Order(3)
    SecurityFilterChain otherPaths(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/error").permitAll()
                        .anyRequest().denyAll())
                .build();
    }

    // Chỉ dành cho local lab: KHÔNG có OAuth Authorization Server thật!
    // Token cố định không có issuer/audience/expiry/revocation thật.
    @Bean
    OpaqueTokenIntrospector labTokenIntrospector() {
        return token -> {
            if ("lab-read-token".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                        "report-client",
                        Map.of("sub", "report-client", "scope", "reports.read"),
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_reports.read")));
            }
            if ("lab-write-token".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                        "report-writer",
                        Map.of("sub", "report-writer", "scope", "reports.write"),
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_reports.write")));
            }
            throw new BadOpaqueTokenException("Invalid lab access token");
        };
    }
}
~~~

**Cách đọc:**
1. `@Order(1)` chọn Bearer chain cho `/bearer/**`; `@Order(2)` chọn Basic chain cho `/basic/**`; cuối cùng default chain từ chối các route không được khai báo (ngoại trừ `/error` để phục vụ xử lý lỗi).
2. `httpBasic(basic -> basic.realmName("Legacy Lab"))` cấu hình Basic challenge với realm ổn định.
3. `oauth2ResourceServer(...opaqueToken(...))` dùng `BearerTokenAuthenticationFilter`, `BearerTokenAuthenticationEntryPoint` và denied handler thích hợp.
4. `OpaqueTokenIntrospector` là **điểm xác thực access token opaque**. Trong lab nó giả lập token bằng hai chuỗi cố định để tạo principal/authority. **Không đánh đồng** với introspection thật: code cố ý bỏ qua signature, issuer, audience, expiry, user revocation, mTLS và các điều kiện production.
5. `STATELESS` cho phép mỗi request xác thực riêng; việc không có session **không** làm `WWW-Authenticate` mất ý nghĩa.
6. Chúng ta **không tắt CSRF toàn ứng dụng**. Các endpoint mẫu đều là `GET` read-only; nếu sau này thêm POST/PUT/DELETE, phải đánh giá CSRF theo credential browser tự gửi, nhất là Basic, cookie hay session.
7. `User.withUsername("reader")` có `ROLE_USER`, không có `ROLE_ADMIN`. Vì vậy `/basic/admin` với password đúng nhận `403`, khác `401` do password sai.
8. `scope` của lab map sang authority có tiền tố `SCOPE_`. Hệ thống production phải lấy scopes từ token/AS đã xác thực, không tin JSON do caller tự gửi.

**Không triển khai mô hình lab-token trên server công khai.** Tất cả token/password trong bài là giá trị giả phục vụ học tập; không dùng lại làm credential của dự án thật.

### 9.4. Controller chỉ trả nội dung khi filter đã xác thực/phân quyền

`src/main/java/demo/challenge/ProtectedController.java`:

~~~java
package demo.challenge;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProtectedController {

    @GetMapping("/basic/report")
    public Map<String, String> basicReport(Principal principal) {
        return Map.of(
                "subject", principal.getName(),
                "result", "basic: READY");
    }

    @GetMapping("/basic/admin")
    public Map<String, String> basicAdmin(Principal principal) {
        return Map.of(
                "subject", principal.getName(),
                "result", "basic-admin: READY");
    }

    @GetMapping("/bearer/read")
    public Map<String, String> bearerRead(Principal principal) {
        return Map.of(
                "subject", principal.getName(),
                "result", "bearer-read: READY");
    }

    @GetMapping("/bearer/write")
    public Map<String, String> bearerWrite(Principal principal) {
        return Map.of(
                "subject", principal.getName(),
                "result", "bearer-write: READY");
    }
}
~~~

Controller **không tự sinh header** `WWW-Authenticate`. Khi request thiếu/sai credential, filter/entry point xử lý trước controller. Khi đã authenticated nhưng thiếu scope, authorization filter/denied handler từ chối trước method, và không cần controller ném exception thủ công.

### 9.5. Test các challenge bằng MockMvc

`src/test/java/demo/challenge/ChallengeSecurityTest.java`:

~~~java
package demo.challenge;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ChallengeSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void missingBasicCredentialsGetsBasicChallenge() throws Exception {
        mvc.perform(get("/basic/report"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Basic ")))
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("realm=\"Legacy Lab\"")));
    }

    @Test
    void wrongBasicPasswordGets401() throws Exception {
        mvc.perform(get("/basic/report")
                        .with(httpBasic("reader", "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Basic ")));
    }

    @Test
    void validBasicPasswordGets200() throws Exception {
        mvc.perform(get("/basic/report")
                        .with(httpBasic("reader", "lab-password-123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("reader"))
                .andExpect(jsonPath("$.result").value("basic: READY"));
    }

    @Test
    void basicUserWithInsufficientRoleGets403() throws Exception {
        mvc.perform(get("/basic/admin")
                        .with(httpBasic("reader", "lab-password-123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingBearerGetsBearerChallengeWithoutError() throws Exception {
        mvc.perform(get("/bearer/read"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Bearer")))
                .andExpect(header().string(
                        "WWW-Authenticate",
                        org.hamcrest.Matchers.not(containsString("invalid_token"))));
    }

    @Test
    void invalidBearerGetsInvalidTokenChallenge() throws Exception {
        mvc.perform(get("/bearer/read")
                        .header("Authorization", "Bearer not-valid-lab-token"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("invalid_token")));
    }

    @Test
    void bearerWithReadScopeGets200() throws Exception {
        mvc.perform(get("/bearer/read")
                        .header("Authorization", "Bearer lab-read-token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("report-client"))
                .andExpect(jsonPath("$.result").value("bearer-read: READY"));
    }

    @Test
    void bearerValidButScopeInsufficientGets403() throws Exception {
        mvc.perform(get("/bearer/write")
                        .header("Authorization", "Bearer lab-read-token"))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("insufficient_scope")));
    }

    @Test
    void bearerWithWriteScopeGets200() throws Exception {
        mvc.perform(get("/bearer/write")
                        .header("Authorization", "Bearer lab-write-token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("report-writer"))
                .andExpect(jsonPath("$.result").value("bearer-write: READY"));
    }

    @Test
    void schemesAreNotInterchangeable() throws Exception {
        mvc.perform(get("/bearer/read")
                        .with(httpBasic("reader", "lab-password-123")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Bearer")));

        mvc.perform(get("/basic/report")
                        .header("Authorization", "Bearer lab-read-token"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", startsWith("Basic ")));
    }
}
~~~

**Kỳ vọng:** 10 test pass khi dependencies/version đúng. Nội dung assertions là trọng tâm:
- Thiếu Basic credential → **401 + Basic challenge**.
- Password sai → **401**, không phải 403.
- Basic đúng nhưng thiếu role → **403**.
- Bearer thiếu token → **401 + Bearer**, thường không kèm `error`.
- Bearer token không hợp lệ → **401 + invalid_token**.
- Bearer token hợp lệ thiếu scope → **403 + insufficient_scope**.
- Hai scheme trên hai chain tách biệt **không dùng credential thay nhau**.

**Về test 403 Bearer:** handler chuẩn có thể phát `insufficient_scope` khi `OAuth2Authentication` đã có và access denied do thiếu authority; nếu bạn thay `AccessDeniedHandler` hoặc viết custom `Authentication` không theo mô hình OAuth2, header có thể khác. Test phải được điều chỉnh **theo contract đã chọn**, không xóa security để “qua test”.

Chạy test:

~~~bash
gradle test

# Nếu project có Gradle Wrapper:
./gradlew test

# Windows:
# gradlew.bat test
~~~

Không đưa output Gradle giả làm kết quả đã chạy; ví dụ chưa được biên dịch/thực thi trong tài liệu này. Với project và dependency khớp, kỳ vọng các assertion thể hiện behavior Spring Security. Khi gặp failure, xem stack trace/test runner, không tắt `WWW-Authenticate` hoặc rút gọn security matcher chỉ để pass.

## 10. Gọi API bằng curl và quan sát response header

Sau khi chạy local:

~~~bash
gradle bootRun
~~~

Mở terminal khác:

~~~bash
# Không có credential Basic:
curl -i http://localhost:8080/basic/report

# Có password demo (chỉ dùng localhost, không dùng với secret thật):
curl -i -u 'reader:lab-password-123' \
  http://localhost:8080/basic/report

# Thiếu Bearer:
curl -i http://localhost:8080/bearer/read

# Bearer sai:
curl -i -H 'Authorization: Bearer invalid-lab-token' \
  http://localhost:8080/bearer/read

# Bearer hợp lệ, đúng read scope:
curl -i -H 'Authorization: Bearer lab-read-token' \
  http://localhost:8080/bearer/read

# Bearer hợp lệ nhưng thiếu reports.write:
curl -i -H 'Authorization: Bearer lab-read-token' \
  http://localhost:8080/bearer/write

# Bearer có write scope:
curl -i -H 'Authorization: Bearer lab-write-token' \
  http://localhost:8080/bearer/write
~~~

`-i` hiển thị **HTTP response status và headers**, giúp quan sát `WWW-Authenticate`. Không dùng `curl -v` hoặc lệnh `-u` chứa **mật khẩu thật trong shell history**, process arguments hay logs. Trong production, API luôn được bảo vệ bằng HTTPS.

| Request | Status mong đợi | Nhìn gì trong response? |
| --- | --- | --- |
| `/basic/report` không credential | 401 | `WWW-Authenticate: Basic realm="Legacy Lab"` |
| `/basic/report` với password đúng | 200 | JSON `result=basic: READY` |
| `/basic/admin` với user `reader` | 403 | Không còn là lỗi password |
| `/bearer/read` thiếu token | 401 | `WWW-Authenticate: Bearer` |
| `/bearer/read` token giả | 401 | `error="invalid_token"` |
| `/bearer/write` có read token | 403 | `error="insufficient_scope"` |
| `/bearer/write` có write token | 200 | JSON `result=bearer-write: READY` |

**Tránh hiểu nhầm:** các chuỗi `lab-read-token` và `lab-write-token` **không có chữ ký, không được AS cấp và không phải OAuth access token thật**. Chỉ custom introspector trong lab chấp nhận chúng để minh họa behavior HTTP; không sử dụng ở production.

## 11. Java 17 độc lập: tự đọc scheme từ response (không gửi secret)

Đoạn client sau không gửi `Authorization`. Nó gọi hai endpoint local để quan sát HTTP 401 challenge, in status và **tên scheme**. Tạo file `ChallengeClient.java` trong thư mục riêng:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;

public class ChallengeClient {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        for (String path : List.of("/basic/report", "/bearer/read")) {
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://localhost:8080" + path))
                    .GET()
                    .build();

            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding());

            String challenge = response.headers()
                    .firstValue("WWW-Authenticate")
                    .orElse("(missing)");

            // Chỉ để in scheme trong lab: không phải HTTP challenge parser.
            String scheme = challenge.split(" ", 2)[0];

            System.out.println(path + " status: "
                    + response.statusCode());
            System.out.println("Challenge scheme: " + scheme);
        }
    }
}
~~~

Khi ứng dụng lab mục 9 đang chạy và request không mang credential, stdout kỳ vọng:

~~~text
/basic/report status: 401
Challenge scheme: Basic
/bearer/read status: 401
Challenge scheme: Bearer
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac ChallengeClient.java
java ChallengeClient
~~~

**Giới hạn ví dụ:** `split(" ", 2)` trong đoạn client chỉ **lấy nhãn đầu tiên** từ một challenge đơn giản mà chúng ta biết trước; **không phải parser chuẩn RFC 9110** cho nhiều challenge/quoted params. Nếu server trả nhiều challenges, ứng dụng phải dùng HTTP parser phù hợp; không copy đoạn này để quyết định credential của production HTTP client.

Ứng dụng `HttpClient` được dùng qua `newHttpClient()` bình thường, không dùng `try-with-resources` cho Java 17 vì `HttpClient` của JDK 17 chưa triển khai `AutoCloseable`. HTTPS/TLS, timeout, retry policy và bảo vệ credential cần được cấu hình riêng cho production.

## 12. Đổi sang Resource Server thật: JWT hoặc opaque introspection

Custom introspector `labTokenIntrospector()` chỉ có chức năng **giả lập**. Khi dùng OAuth2 thực sự:

### 12.1. JWT access token

Ứng dụng Resource Server thường dùng:

~~~java
// Mảnh cấu hình Spring Security Servlet; không phải class độc lập.
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Ví dụ `application.yml` có AS/OP cung cấp issuer metadata:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/training
~~~

Production phải kiểm tra thêm **audience** dành cho API, thuật toán và trust policy phù hợp; chỉ có `issuer-uri` không có nghĩa mọi kiểm tra authorization audience/tenant tự đúng. Chữ ký JWT, issuer, expiry và claim/authority mapping cần kiểm thử bằng token được cấp thực sự hoặc token test ký bởi key lab hợp lệ.

Không hardcode JWKS endpoint do browser gửi, không cho attacker thay issuer bằng HTTP header để bypass token verification.

### 12.2. Opaque access token/introspection thật

Thay bean lab bằng `OpaqueTokenIntrospector` gọi endpoint introspection của AS được tin:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.org/oauth2/introspect
          client-id: reports-api
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Khi chạy thật, cần **loại bỏ bean lab custom introspector** nếu muốn Boot auto-config kết nối tới endpoint. Nếu vẫn giữ bean đó, property trên có thể không có hiệu lực như bạn nghĩ. `INTROSPECTION_CLIENT_SECRET` là bí mật dành cho resource server gọi introspection, **không phải password của end user**. Bảo vệ nó bằng secret manager/HTTPS; không log token/introspection credentials.

Khi token bị revoked hoặc inactive, resource server nên trả `401` và Bearer challenge phù hợp. Khi token active nhưng scope không đủ, trả `403`; cả hai phải được kiểm thử. Không xem `active=true` là đủ nếu token thiếu audience/resource binding mà policy yêu cầu.

### 12.3. Basic không phải OAuth client authentication

OAuth AS có thể yêu cầu confidential client xác thực bằng HTTP Basic ở **token endpoint**, ví dụ `client_id:client_secret`. Đó là một quan hệ Basic khác với user/password trên resource server. Không dùng `WWW-Authenticate: Basic` từ một API để suy ra nó là OAuth Authorization Server. Từng endpoint cần mô tả rõ scheme, principal, credentials và quyền.

## 13. Tùy chỉnh JSON lỗi vẫn phải tôn trọng header

Trong REST API, client thường muốn JSON body chuẩn hóa, ví dụ:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication required"
}
~~~

**Body JSON và `WWW-Authenticate` không loại trừ nhau**: body giúp người đọc lỗi, header giúp HTTP client chọn scheme. Khi dùng custom entry point, tránh:

~~~java
// Mảnh minh họa LỖI (đừng dùng): thiếu WWW-Authenticate trong 401.
response.setStatus(401);
response.getWriter().write("{\"error\":\"unauthorized\"}");
~~~

Nếu cần body JSON, nên **delegate** cho `BasicAuthenticationEntryPoint`/`BearerTokenAuthenticationEntryPoint` hoặc cấu hình một implementation đáp ứng đúng challenge/status, sau đó ghi body **nếu response chưa commit và protocol cho phép**. Không gọi thêm `sendError()` sau khi đã ghi body/headers bừa bãi vì container error handling có thể thay response.

Đối với Bearer, framework có thể phát `WWW-Authenticate` với parameters tùy `BearerTokenError`; hãy giữ header này. Một middleware/exception handler chung không nên ghi đè mọi `AuthenticationException` thành `401` không có challenge.

**Chú ý thông tin lỗi:** response không nên lộ password, token nguyên văn, private key, JWT claim nhạy cảm, introspection payload, tên bảng/stack trace. Có thể trả `requestId` và mã lỗi chung, đồng thời log internal cause theo policy (đã redacted).

## 14. Gateway/proxy: header có thể bị mất hoặc bị thay đổi

Nếu có CDN/WAF/API Gateway/Ingress:
- Xác minh `Authorization` **đến đúng service**. Một số proxy có thể strip/override header này theo cấu hình authentication của chính proxy.
- `WWW-Authenticate` ở response phải tới HTTP client nguyên vẹn; RFC 9110 nêu proxy **không được tùy tiện sửa** field này khi forward response.
- Phân biệt `401` do **API origin** với `407` do **proxy**; dùng response headers, trace ID và log an toàn để tìm nơi từ chối.
- Không cho client internet tự chèn header “đã xác thực” như `X-Authenticated-User` rồi backend tin nó mà không có trust boundary.
- Với SSO/browser, custom SPA có thể không muốn Basic native dialog; cấu hình behavior theo từng endpoint, không quảng bá Basic challenge trên mọi lỗi route khi app thực sự chỉ dùng cookie/form login.
- Nếu gateway thực hiện auth trước và backend có auth khác, quyết định scheme/realm/error/403 policy thống nhất giữa hai lớp. Không để một request trả `Basic` từ gateway và `Bearer` từ backend tùy may rủi.

### 14.1. Các lỗi cache và bảo mật headers

Auth responses chứa thông tin quyền riêng:
- `Cache-Control: no-store` phù hợp cho responses nhạy cảm; kiểm tra không cache response `401/403` sai theo user/credential.
- Không nhúng token vào URL query/fragment; `Authorization` header giúp giảm rò rỉ qua URL, nhưng vẫn có thể bị log ở gateway nếu bật ghi toàn bộ header.
- Dùng HTTPS/TLS, giới hạn redirect cross-origin và không forward credential tới hostname lạ.
- Dùng các định dạng log cho `status`, `route`, `scheme`, `requestId` và nguyên nhân lỗi phân loại, không cần log full `Authorization`.
- Khi token hết hạn, client có thể lấy token mới từ AS theo policy; đừng retry tự động mọi 401 vô hạn hoặc đổi sang Basic password như fallback không được phê duyệt.

## 15. Troubleshooting: gặp status khác kỳ vọng

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `401` nhưng không có `WWW-Authenticate` | Custom entry point/handler; AJAX-specific Basic behavior; proxy strip; response bị commit | Kiểm tra network response và entrypoint thực tế |
| `302` về `/login` thay vì `401` | Form login/default entry point đang hoạt động ở chain | Kiểm tra `SecurityFilterChain` matcher, `formLogin` và request media |
| `401 Basic` khi tưởng API dùng Bearer | Chọn nhầm chain, gateway quảng bá Basic | Kiểm tra `@Order` và `securityMatcher` |
| `401 Bearer invalid_token` khi JWT parse được | Sai issuer, signature, expiry, audience hoặc token revocation | Kiểm tra token validation, không chỉ decode JWT |
| `403 Bearer insufficient_scope` | Token active nhưng thiếu `SCOPE_*` đúng mapping | Kiểm tra scopes/authorities và authorization policy |
| `403` dù password Basic đúng | User đã authenticated nhưng thiếu role/permission; hoặc CSRF với unsafe request | Kiểm tra exception category, không tự đổi thành 401 |
| `400 Bearer invalid_request` | Header lỗi cú pháp/duplicate, token ở nhiều nơi | Kiểm tra `DefaultBearerTokenResolver` và client |
| `401` sau refresh token | Client dùng refresh token như Bearer access token; token mới không hợp lệ | Chỉ gửi **access token** tới resource server |
| `WWW-Authenticate` parse lỗi trên client | Nhiều challenge, commas trong params, quoted-string | Dùng RFC-compliant library, không split ngây thơ |
| Browser hiện password popup không mong muốn | Basic challenge tới browser page/XHR | Tách API/browser auth hoặc custom entry point hợp lệ |
| Login thành công nhưng API vẫn 403 | Authentication và authorization là hai bước khác nhau | Kiểm tra quyền, scope, tenant, policy |
| Proxy trả 407 | Proxy yêu cầu credential | Kiểm tra `Proxy-Authenticate`, không sửa code API |
| Error handler trả cùng JSON 401 cho mọi thứ | Handler ghi đè status/header | Giữ riêng authentication và access-denied paths |

## 16. Ma trận kiểm thử production nên bổ sung

Bên cạnh MockMvc lab ở mục 9, production cần kiểm chứng:

1. **Không credential:** đúng status, đúng scheme, không lộ `invalid_token` vô lý khi chưa có token.
2. **Basic sai/đúng:** password sai → 401; password đúng → 200 hoặc 403 theo role; realm ổn định.
3. **Bearer invalid:** sai issuer, hết hạn, bị revoke, signature invalid, wrong audience → không vào controller.
4. **Bearer insufficient scope:** token hợp lệ có scope A nhưng không có B → 403; scope hiện trong challenge chỉ khi policy cho phép.
5. **Object-level denial:** token có scope đủ nhưng không sở hữu object → 403/404 theo policy, không tiết lộ dữ liệu.
6. **Multiple/unknown schemes:** xử lý client không hiểu scheme, multiple challenges và headers; không có auth fallback sai.
7. **Header forwarding:** edge/CDN/gateway không làm rơi `WWW-Authenticate`, không nhầm origin/proxy headers.
8. **Correlation:** log không chứa `Authorization` raw, password, token, session cookie; status và request ID đủ để debug.
9. **Rate limiting:** Basic brute-force/throttle; Bearer invalid request flood; tránh khác biệt timing/log cho identity enumeration.
10. **Browser behavior:** Basic dialog, XHR, form login, cookie session và CSRF là các flow khác nhau.
11. **TLS:** không gửi Basic password hoặc bearer token qua HTTP công khai; không tự follow redirect cross-host kèm Authorization.
12. **Session/CSRF:** nếu Basic được browser gửi tự động vào unsafe endpoint, vẫn đánh giá CSRF; `WWW-Authenticate` không phải cơ chế chống CSRF.
13. **Authorization Server vs Resource Server:** token-endpoint lỗi OAuth khác với Bearer challenge của protected API; không trộn `invalid_client` với `invalid_token`.
14. **Account lifecycle:** tài khoản bị khóa/disabled không được “sửa” chỉ bằng đổi từ 403 sang 401; response không lộ trạng thái quá chi tiết.
15. **Dependency update:** kiểm thử lại HTTP headers khi nâng Spring Security, thay entrypoint/filter, hoặc đổi proxy.

### 16.1. Khi nào cần response JSON riêng cho mỗi cơ chế?

Nếu API phục vụ các client khác nhau, body có thể có dạng Problem Details theo RFC 9457, nhưng header cần thể hiện đúng challenge. Có thể quy định:
- Basic 401: `WWW-Authenticate: Basic realm="Legacy Lab"` + JSON error ngắn.
- Bearer 401 không token: `WWW-Authenticate: Bearer`.
- Bearer 401 token invalid: `WWW-Authenticate: Bearer error="invalid_token"`.
- Bearer 403 thiếu quyền: `WWW-Authenticate: Bearer error="insufficient_scope"` khi khả thi.
- Basic authenticated thiếu quyền: `403`, **không** tự hiện password prompt nếu nhập lại password cũng không làm tăng quyền.

Tài liệu API contract cần có ví dụ status, headers và body. Không chỉ ghi “thất bại sẽ trả 401” vì điều đó giấu toàn bộ khác biệt giữa thiếu credential và thiếu privilege.

## 17. Những sai lầm thường gặp

1. **“`WWW-Authenticate` là header request.”** Sai; đây là **response challenge**. Request thường có `Authorization`.
2. **“Mọi lỗi xác thực hay phân quyền đều trả 403.”** Sai; thiếu/sai credential thường 401, thiếu quyền thường 403.
3. **“401 không cần header vì JSON đã mô tả lỗi.”** Sai theo RFC 9110; cần challenge.
4. **“Một `Bearer` token bắt buộc là JWT.”** Sai; bearer token có thể opaque.
5. **“Token expired nên trả `insufficient_scope`.”** Sai; token invalid thường 401/`invalid_token`.
6. **“Token hợp lệ thiếu scope nên bắt user đăng nhập Basic.”** Sai; cần quyền/token hợp lệ theo OAuth policy, không tự downgrade scheme.
7. **“Basic dùng Base64 nên password đã mã hóa an toàn.”** Sai; Base64 dễ decode; HTTPS là bắt buộc.
8. **“`realm` có thể chứa bí mật để phân biệt khách hàng.”** Sai; realm là thông tin có thể hiển thị công khai.
9. **“HTTP Basic và form login cùng một cơ chế.”** Sai; form login thường dùng HTML/cookie/session, không nhất thiết challenge Basic.
10. **“Có `Authorization: Bearer` thì mọi API Spring tự xác minh token.”** Sai; cần Resource Server/validator và issuer/audience/scope configuration.
11. **“`403` lúc nào cũng phải có `WWW-Authenticate`.”** Sai; có thể nhưng không phải quy tắc bắt buộc tổng quát.
12. **“`scope` là danh sách dấu phẩy.”** Sai trong Bearer challenge; thường các scope được cách nhau bằng dấu cách trong một quoted string.
13. **“Một challenge có dấu phẩy là nhiều scheme.”** Sai; dấu phẩy còn là dấu ngăn params, cần parser.
14. **“Có thể log `Authorization` để điều tra 401.”** Sai; log credential tạo nguy cơ lộ/chiếm quyền.
15. **“Proxy 407 là server API trả 401.”** Sai; `Proxy-Authenticate` là luồng riêng.
16. **“Đổi 403 thành 401 để browser yêu cầu password lại là sửa lỗi.”** Sai; nếu đã authenticated thiếu quyền, password cũ không giải quyết.
17. **“Request thiếu token có `invalid_token` mặc định.”** RFC 6750 khuyến nghị không gửi error code khi không có authentication info.
18. **“Đã có scope thì được truy cập mọi bản ghi.”** Sai; tenant/ownership và quyền nghiệp vụ vẫn phải áp dụng.
19. **“HTTP Basic không có CSRF vì không có cookie.”** Có thể sai nếu browser cache và tự gửi Basic credentials tới unsafe endpoint; cần threat model.
20. **“Đã viết test 200 là đủ.”** Sai; phải test 400/401/403, header challenge, invalid/scope, proxy/browser behavior.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** API nhận GET không có `Authorization`, trả `401` nhưng không có `WWW-Authenticate`. Điều gì sai?  
**Đáp án:** Theo HTTP authentication semantics, 401 phải có ít nhất một challenge áp dụng cho tài nguyên.

**Câu 2.** Header `WWW-Authenticate: Basic realm="Finance"` có gửi password cho client không?  
**Không.** Nó chỉ thông báo scheme/realm. Password nếu có nằm trong request `Authorization: Basic ...`, và vẫn cần TLS.

**Câu 3.** Client gửi access token đã hết hạn. Resource server nên dùng Bearer error nào?  
**`invalid_token`**, thường với status 401, không phải insufficient_scope.

**Câu 4.** Token đã xác minh hợp lệ và có `reports.read` nhưng endpoint cần `reports.write`. Status nào?  
**403**, có thể kèm `Bearer error="insufficient_scope", scope="reports.write"`.

**Câu 5.** Basic password đúng nhưng user `reader` gọi endpoint chỉ cho `ADMIN`. Có nên trả 401?  
**Thường không.** User đã authenticated; thiếu role nên 403.

**Câu 6.** Response `407 Proxy Authentication Required` dùng `WWW-Authenticate`?  
**Không.** Proxy dùng `Proxy-Authenticate`; client dùng `Proxy-Authorization`.

**Câu 7.** `WWW-Authenticate: Bearer` không có realm là không hợp lệ?  
**Không.** `realm` tùy chọn cho Bearer; Basic challenge cần realm.

**Câu 8.** Có nên dùng `String.split(",")` để parse tất cả Bearer challenges?  
**Không.** Dấu phẩy phân tách params hoặc challenges, và quoted-string có quy tắc riêng.

**Câu 9.** Một Bearer token là JWT, phần payload decode được nhưng signature sai. Đó là `insufficient_scope`?  
**Không.** Token không được xác thực nên thuộc `invalid_token`.

**Câu 10.** API đặt key bí mật ở URL vì muốn khỏi thêm `Authorization`. Đây là thiết kế nên làm?  
**Không.** Credential trong URL dễ lộ qua log/history/proxy; dùng header đúng contract trên HTTPS.

### Checklist khi thiết kế API authentication responses

- [ ] Mọi origin-server 401 có `WWW-Authenticate` với ít nhất một challenge phù hợp.
- [ ] `Authorization` request dùng đúng scheme; Basic và Bearer không trộn lẫn.
- [ ] Basic `realm` rõ ràng, ổn định, không chứa dữ liệu nhạy cảm.
- [ ] Bearer no-token 401 không tiết lộ lỗi thừa; invalid_token 401; insufficient_scope 403.
- [ ] Chọn status 400/401/403 theo nguyên nhân chứ không dùng một mã chung.
- [ ] AuthenticationEntryPoint và AccessDeniedHandler tách đúng trách nhiệm.
- [ ] Custom JSON handler giữ status và header challenge.
- [ ] SecurityFilterChain matcher/priority chính xác; không kích hoạt Basic popup ở Bearer-only API.
- [ ] JWT/opaque token được xác minh thật theo trust, lifetime, audience và scope; không dùng lab introspector production.
- [ ] HTTPS, không log password/token/Authorization; kiểm tra proxy không strip challenge.
- [ ] Test thiếu/sai/đúng credential, thiếu quyền và nhiều challenge.
- [ ] Authorization nghiệp vụ và CSRF ở browser credential được đánh giá riêng.

## 19. Tài liệu tham khảo chính thức

- [RFC 9110 — HTTP Semantics `11.3, `11.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-11.6.1): `WWW-Authenticate`, `Authorization`, `401`/`403` và phân biệt `407`.
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617.html): Basic, realm, Base64, Unicode và `charset="UTF-8"`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer challenge, `invalid_request`, `invalid_token`, `insufficient_scope`.
- [Spring Security 6.5 — Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): `BasicAuthenticationFilter`, `BasicAuthenticationEntryPoint`, special AJAX behavior.
- [Spring Security 6.5 — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/): `BearerTokenAuthenticationFilter` và Bearer challenge.
- [Spring Security 6.5 — Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, auth mapping và introspection.
- [Spring Security 6.5 — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): error-to-header behavior.
- [Spring Security 6.5 — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html): xử lý `403` và `insufficient_scope`.
- [Spring Security Test — MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/): test xác thực và status/challenge.

**Kết luận:** `WWW-Authenticate` là **lời thách thức của server**, còn `Authorization` là **credential client cung cấp**. HTTP Basic dùng `Basic realm="..."` với username/password Base64 phải bảo vệ bằng HTTPS; OAuth Resource Server dùng `Bearer` với lỗi `invalid_token` hoặc `insufficient_scope` theo nguyên nhân. Đảm bảo **401 có challenge đúng**, **403 phản ánh thiếu quyền**, đồng thời dùng đúng Spring Security entry point và access-denied handler để không làm hỏng hợp đồng HTTP.