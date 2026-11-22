# 28.7. 401, 403, 429 và lỗi 5xx từ downstream hoặc provider

## 1. Bài toán: cùng là 401 hoặc 503, nhưng phải xử lý khác nhau

Giả sử **Employee Portal** được xây dựng bằng **Spring Boot 3, Spring Security 6**, sử dụng **OAuth2 Login/OIDC Client** để xác thực người dùng qua OpenID Provider, sau đó dùng access token gọi **Orders API**:

~~~text
Browser
  -> Employee Portal (OAuth2/OIDC Client, BFF)
      -> Company OpenID Provider / Authorization Server (AS)
      -> Orders API (OAuth2 Resource Server)
~~~

Trong một buổi sáng, hệ thống ghi nhận:

~~~text
08:35  Orders API -> HTTP 401 Bearer invalid_token
08:40  Orders API -> HTTP 403 Bearer insufficient_scope
08:45  Token endpoint -> HTTP 429 Retry-After: 30
08:50  Orders API -> HTTP 503 Service Unavailable
08:55  Token endpoint -> HTTP 400 invalid_grant
09:00  Portal -> Browser HTTP 401
~~~

Nếu ứng dụng dùng một quy tắc chung:

~~~text
Mọi lỗi => refresh token => retry 5 lần => logout user
~~~

thì sẽ gây nhiều vấn đề:

- **403** có thể là thiếu quyền; refresh token không tự cấp thêm scope.
- **429** là rate limit; retry lập tức làm tình hình nặng hơn.
- **503** thường là sự cố dịch vụ tạm thời; xóa authorized client không sửa được.
- **invalid_grant** có thể do refresh token bị rotate/revoke; retry cùng credential vô hạn là nguy hiểm.
- **401 từ Portal** có thể chỉ là browser chưa đăng nhập, hoàn toàn khác **401 từ Orders API**.

**Nguyên tắc bài học:** trước khi quyết định refresh, re-login, retry, xóa token hay hiển thị thông báo, phải xác định **lỗi đến từ đâu, request nào, loại credential nào và OAuth2 error semantics nào**.

> Bối cảnh: Java 17+, Spring Security OAuth2 Client với Servlet/RestClient hoặc WebClient, có ví dụ Reactor cho ứng dụng Reactive. Mọi endpoint/chuỗi token minh họa đều là giả. Không nên suy diễn toàn bộ lỗi HTTP 4xx/5xx thành lỗi đăng nhập; giữ ranh giới giữa authentication, authorization và availability.

## 2. Sơ đồ các điểm có thể thất bại

~~~mermaid
flowchart TD
    U["Browser"] --> RP["Portal / OAuth2 Client"]
    RP --> OP["OpenID Provider"]
    OP --> AUTH["Authorization endpoint /authorize"]
    OP --> TOKEN["Token endpoint /token"]
    OP --> UI["UserInfo endpoint"]
    OP --> JWKS["Discovery/JWK Set metadata"]
    RP --> STORE["Authorized Client Store"]
    RP --> API["Orders API / Resource Server"]
    API --> DB["Downstream DB / service dependencies"]
    RP --> U
~~~

Một request end-to-end có thể gồm nhiều lượt HTTP khác nhau:

1. Browser gọi Portal.
2. Portal redirect browser đến authorization endpoint.
3. Browser trả authorization code về callback.
4. Portal gọi token endpoint để đổi code hoặc refresh token.
5. Portal có thể gọi UserInfo endpoint và tải metadata/JWKS.
6. Portal tải `OAuth2AuthorizedClient` từ store.
7. Portal gửi access token sang Orders API.
8. Orders API gọi database hoặc các microservices.

**Mỗi HTTP response có bên phát, quyền tin cậy và hành động xử lý khác nhau.**

## 3. Bảng phân loại nhanh theo HTTP status và nguồn

| Status/Signal | Ở đâu | Diễn giải ban đầu | Điều không nên làm |
|---|---|---|---|
| **401 Unauthorized** | Resource Server | Access token thiếu, sai, hết hạn, bị revoke hoặc không được chấp nhận | Không logout toàn bộ user ngay |
| **401 Unauthorized** | Authorization Server token endpoint | Có thể là lỗi client authentication, thường kèm OAuth error `invalid_client` | Không coi là access token API hết hạn |
| **401 Unauthorized** | UserInfo endpoint | Access token sử dụng để gọi UserInfo bị từ chối | Không bỏ ID Token/issuer validation |
| **401 Unauthorized** | Portal → Browser | Browser chưa có authentication phù hợp hoặc phiên hết hạn | Không tự coi Orders API đã trả 401 |
| **403 Forbidden** | Resource Server | Đã xác định request nhưng không đủ quyền/scope/resource policy | Không refresh vô hạn để nâng quyền |
| **403 Forbidden** | Portal | User đăng nhập nhưng không được phép dùng chức năng | Không đổi client registration để vượt RBAC |
| **429 Too Many Requests** | AS/token endpoint | Client/IP/tenant bị rate limit | Không retry ngay, không mở token storm |
| **429 Too Many Requests** | Downstream API | API quota/concurrency/rate limit | Không xóa authorized client |
| **500 Internal Server Error** | AS/downstream | Service xử lý lỗi | Không suy token sai |
| **502 Bad Gateway** | Reverse proxy/gateway | Upstream response lỗi hoặc kết nối upstream không hợp lệ | Không refresh token theo status 502 |
| **503 Service Unavailable** | AS/downstream | Tạm thời unavailable/overload/maintenance | Không retry vô hạn |
| **504 Gateway Timeout** | Gateway | Upstream quá thời gian chờ | Không tự replay request non-idempotent |
| `invalid_grant` | AS token endpoint | Code/refresh token/grant credential không hợp lệ | Không retry lại cùng one-time credential bừa bãi |
| `invalid_scope` | AS token endpoint | Scope yêu cầu không hợp lệ/không được cấp | Không tự tăng quyền trong client |

**HTTP status chỉ là dấu hiệu đầu tiên.** Cần kết hợp:

- URL/endpoint và method.
- `WWW-Authenticate` response header nếu có.
- OAuth2 JSON `error` code từ token endpoint.
- `Retry-After` khi có.
- Authorization context và registration ID.
- Request ID/correlation ID.
- Mức độ an toàn khi retry.

## 4. Tách lỗi của Portal, Authorization Server và Resource Server

### 4.1. Portal trả 401 cho browser

Ví dụ:

~~~http
GET /api/me HTTP/1.1
Host: portal.example.test

HTTP/1.1 401 Unauthorized
~~~

Điều này có thể là:

- Browser chưa có valid session.
- Session server đã hết hạn.
- API SecurityFilterChain yêu cầu authentication.
- Request bị gửi thiếu cookie hoặc bearer credential theo policy.

Nó **không** chứng minh access token mà Portal lưu để gọi Orders API đã hết hạn.

### 4.2. Orders API trả 401 cho Portal

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <redacted>

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Portal đang authenticated với browser nhưng access token gửi sang Orders API bị từ chối. Cần xử lý **authorized-client/token context**, không mặc định xóa browser session.

### 4.3. Token endpoint trả lỗi

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test

HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant"}
~~~

Đây là lỗi xảy ra **trong quá trình xin token**, khác với việc đã có token rồi Orders API từ chối.

### 4.4. UserInfo hoặc JWK endpoint bị lỗi

Trong OIDC login, token exchange có thể thành công nhưng UserInfo/JWK fetching thất bại. Cần phân biệt protocol validation/remote dependency; không coi mọi trường hợp là lỗi downstream Orders API.

## 5. Phân biệt HTTP status và OAuth2 error code

OAuth2 token endpoint thường trả JSON theo convention:

~~~json
{
  "error": "invalid_grant",
  "error_description": "Authorization grant is invalid"
}
~~~

Trong Spring Security, lỗi được mô hình hóa bởi các loại như:

~~~java
org.springframework.security.oauth2.core.OAuth2Error
org.springframework.security.oauth2.core.OAuth2AuthorizationException
~~~

Mỗi error có thể có `errorCode`, `description` và `uri`.

**HTTP 400 không nói hết lỗi OAuth**, vì:

~~~text
400 invalid_grant
400 invalid_scope
400 unauthorized_client
400 unsupported_grant_type
~~~

đều có thể yêu cầu hành động khác nhau.

Ngược lại, một server có thể trả HTTP 500 nhưng body không phải OAuth2 error JSON; không được cố parse và giả định `invalid_grant`.

### 5.1. Một số OAuth2 token errors

| OAuth2 error | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `invalid_grant` | Code hết hạn/đã dùng, redirect URI sai, refresh token revoked/rotated | Không retry cùng credential mù; xét reauthorization |
| `invalid_client` | Client ID/secret/mTLS/private_key_jwt không hợp lệ | Kiểm tra config/secrets/rotation |
| `unauthorized_client` | Client không được phép dùng grant | Sửa policy/registration |
| `invalid_scope` | Requested scope không hợp lệ | Sửa requested scopes/consent/config |
| `unsupported_grant_type` | AS không hỗ trợ grant | Sửa grant/AS capability |
| `invalid_request` | Thiếu hoặc sai parameter | Sửa request converter/protocol |
| `temporarily_unavailable` | AS tạm thời không đáp ứng yêu cầu | Có thể retry có budget theo context |

Không nên hiển thị raw `error_description` cho người dùng nếu chứa thông tin nội bộ hoặc token/credential; message từ hệ thống ngoài là **dữ liệu không đáng tin**.

## 6. 401 từ Resource Server: hiểu đúng Bearer authentication

Resource Server có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

Các nguyên nhân có thể:

1. Access token đã hết hạn.
2. Token bị revoke hoặc không còn hợp lệ.
3. Sai issuer.
4. Sai audience/resource indicator.
5. Sai signature/algorithm/key.
6. Không gửi header Authorization.
7. Header bị proxy/interceptor xóa.
8. Token loại khác (ví dụ ID Token) bị dùng nhầm.
9. Resource Server đang thiếu configuration/keys/clock sync.

**Không phải mọi 401 đều có thể sửa bằng refresh token.**

### 6.1. WWW-Authenticate là tín hiệu quan trọng

Ví dụ RFC 6750-style:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

hoặc:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Header giúp phân biệt token invalid với thiếu quyền trong Bearer scheme. Nhưng header có thể thiếu, không đầy đủ hoặc có nhiều authentication challenges.

**Không dựa duy nhất vào việc chuỗi chứa chữ `invalid_token`** mà bỏ qua scheme, origin, status và trust context.

### 6.2. Khi nào nên loại authorized client cũ?

Nếu trusted Resource Server trả **401 Bearer invalid_token** cho token đã gửi, ứng dụng có thể:

- Đánh dấu authorized client không còn phù hợp.
- Loại cache/authorized-client entry tương ứng theo policy.
- Gọi `OAuth2AuthorizedClientManager` để cấp/refresh token mới.
- Retry **một lần có giới hạn** đối với request an toàn khi reauthorization thành công.

Tuy nhiên cần cân nhắc:

- Token có thật sự bị revoke hay API đang cấu hình sai issuer/audience?
- Một token mới có scope/audience như cũ có giải quyết không?
- Refresh token có tồn tại và còn hiệu lực không?
- Có nhiều requests đồng thời đang refresh không?

Không tự động logout browser trên 401 của một downstream API.

### 6.3. Nếu 401 không kèm Bearer invalid_token

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="internal"
~~~

Đây không phải bằng chứng OAuth2 access token invalid. Có thể request đang đi nhầm endpoint/proxy hoặc API yêu cầu authentication scheme khác.

Phải phân tích đúng downstream authentication contract.

### 6.4. Nếu token mới vẫn 401

Không loop:

~~~text
401 -> refresh -> 401 -> refresh -> 401 -> ...
~~~

Hãy dừng sau budget và kiểm tra issuer, audience, scope, clock skew, client registration, JWKS, Resource Server config và log correlation.

## 7. 403 từ Resource Server: khác biệt giữa authentication và authorization

Ví dụ:

~~~http
GET /api/admin/audit HTTP/1.1
Authorization: Bearer <valid-access-token>

HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="admin.read"
~~~

Diễn giải thường gặp: token có thể được nhận diện nhưng **không đủ scope/quyền** cho tài nguyên.

### 7.1. Access token hợp lệ không có nghĩa mọi API đều cho phép

Resource Server kiểm tra:

- Scope/authority.
- Role/tenant membership.
- Resource ownership.
- Business policy.
- Authentication assurance/step-up policy nếu có.

Một token có `orders.read` không tự có `admin.read`.

### 7.2. Tại sao refresh token không tự tăng scope?

Refresh token thường lấy token mới theo grant và các quyền đã được cấp. Nó không tự mở rộng consent hoặc authorization của user:

~~~text
Old AT: scope=orders.read
Refresh: vẫn được cấp scope=orders.read
Admin API: cần admin.read
=> 403 vẫn tồn tại
~~~

Giải pháp thường nằm ở:

- Requested scopes/IdP client permission.
- User consent/reauthorization.
- Application RBAC.
- Resource Server policy hoặc resource ownership.

Không “sửa” 403 bằng cách đổi sang một service token có quyền cao hơn mà bỏ user authorization.

### 7.3. 403 không phải lúc nào là insufficient_scope

Một API có thể trả 403 vì:

~~~text
tenant membership suspended
resource belongs to another user
business feature not licensed
IP/network policy
account or document access denied
~~~

Khi thiếu Bearer challenge, không nên tự kết luận scope sai. Xem API contract và audit logs an toàn.

### 7.4. UX của 403

Thông báo phù hợp:

~~~text
Bạn đã đăng nhập nhưng không có quyền thực hiện thao tác này.
Liên hệ quản trị viên nếu cần được cấp quyền.
~~~

Không tự bật lại login loop chỉ vì một API trả 403.

## 8. 429 Too Many Requests: rate limiting của AS và downstream

Ví dụ token endpoint:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json
~~~

Hoặc Orders API:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: Wed, 18 Nov 2026 10:30:00 GMT
~~~

`Retry-After` thường có hai dạng:

1. **Delta-seconds** — số giây cần chờ.
2. **HTTP-date** — thời điểm có thể thử lại.

**429 không chứng minh access token sai.** Nó báo server đang áp rate limit theo IP, client ID, tenant, subject, endpoint hoặc quota policy.

### 8.1. Vì sao OAuth2 Client dễ gây token storm?

Một lỗi phổ biến:

~~~text
WebClient request nào cũng gọi manager.
Authorized-client store không lưu token.
Mỗi request lại xin token mới.
Token endpoint trả 429.
Client retry ngay.
Càng nhiều requests càng nhiều 429.
~~~

Nguyên nhân có thể là:

- Không tái sử dụng `OAuth2AuthorizedClient` còn hạn.
- `principalName` thay đổi liên tục làm cache miss.
- Token expiry/skew cấu hình sai.
- Multiple pods đồng thời refresh.
- Success handler không persist token.
- Job polling quá dày hoặc retry không có jitter.

### 8.2. 429 tại AS khác 429 tại API

| Nguồn 429 | Phạm vi thường chịu quota | Hướng xử lý |
|---|---|---|
| Authorization/token endpoint | OAuth client, IP, tenant, token grants | Giảm token issuance/refresh frequency; dùng backoff |
| UserInfo endpoint | User/tenant/API quota | Reuse validated data khi hợp lệ và theo privacy policy |
| JWKS/discovery endpoint | Metadata fetch rate | Cache metadata/JWK và exponential backoff |
| Orders API | Business API requests | Limit concurrency, cache responses, respect quota |

Không xóa authorized-client token chỉ vì Orders API rate limit.

### 8.3. Retry-After là gợi ý từ phía server, không phải quyền retry vô hạn

Khi đọc `Retry-After` cần:

- Parse số giây hoặc HTTP date theo chuẩn.
- Chặn giá trị âm/không hợp lệ.
- Giới hạn tối đa theo **overall request deadline** và SLA.
- Dùng jitter để tránh mọi replicas đánh thức cùng lúc.
- Kiểm tra request có an toàn để retry không.
- Không block request threads lâu không cần thiết.

Nếu Retry-After là 1 giờ nhưng UI request deadline 5 giây, có thể trả thông báo “thử lại sau” thay vì giữ request một giờ.

## 9. 5xx từ downstream hoặc provider: availability, không phải credential semantics

Một số tình huống:

~~~text
500 Internal Server Error
502 Bad Gateway
503 Service Unavailable
504 Gateway Timeout
~~~

| Status | Thường phản ánh | Hành động ban đầu |
|---|---|---|
| 500 | Server gặp lỗi xử lý | Theo dõi, có thể retry có giới hạn nếu request an toàn |
| 502 | Gateway nhận phản hồi lỗi từ upstream | Kiểm tra proxy/upstream, retry an toàn nếu phù hợp |
| 503 | Overload/maintenance/unavailable | Respect Retry-After, backoff, circuit breaker |
| 504 | Gateway timeout | Xác định request có thể đã được xử lý hay chưa trước retry |

### 9.1. 5xx không chứng minh token hết hạn

Sai:

~~~text
Orders API returns 503
  -> remove authorized client
  -> force user login
~~~

Đúng hơn:

~~~text
Orders API returns 503
  -> classify as downstream availability issue
  -> limited safe retry / circuit breaker
  -> show temporary unavailability if needed
  -> preserve browser login and valid token
~~~

### 9.2. 502/504 có thể xuất hiện ở proxy

Khi app gọi:

~~~text
Portal -> API Gateway -> Orders Service
~~~

HTTP 504 có thể do gateway timeout, dù Orders Service đã nhận request và thậm chí đã ghi database.

Vì vậy **không tự retry POST thanh toán, tạo đơn, đổi mật khẩu** chỉ vì gateway trả 504.

### 9.3. Token endpoint 503 trong login

Khi browser callback có authorization code và Portal gửi tới token endpoint:

~~~http
POST /oauth2/token
grant_type=authorization_code
code=<one-time-code>
~~~

Nếu token endpoint hoặc kết nối lỗi/timeout, không chắc code chưa được consume. Authorization code là **one-time credential**. Retry cùng code phải dựa trên contract/idempotency và chính sách; cách an toàn thường là fail flow rồi khởi động một authorization request mới thay vì replay vô hạn.

### 9.4. Refresh token rotation và network timeout

Tương tự:

~~~text
Client sends RT1
AS accepts and rotates RT1 -> RT2
Response lost due to network timeout
Client retries RT1
AS detects reuse/invalid_grant
~~~

Không thể khẳng định RT1 còn hợp lệ chỉ vì client không nhận response. Thiết kế retry phải hiểu rotation và refresh-token family policy.

## 10. Request idempotency quyết định khả năng retry

HTTP method là dấu hiệu hữu ích nhưng chưa đủ:

| Loại request | Retry tự động | Lưu ý |
|---|---|---|
| GET đọc dữ liệu không side effects | Thường có thể | Vẫn phải có budget/rate limit |
| HEAD | Thường có thể | Không nên retry vô hạn |
| PUT idempotent theo API contract | Có thể | Cần xác nhận nghiệp vụ |
| DELETE | Có thể idempotent về trạng thái | API contract/side effects cần kiểm tra |
| POST tạo đơn/charge | Thường **không** nếu thiếu idempotency key | Timeout có thể đã ghi dữ liệu |
| Token endpoint `authorization_code` | Không retry mù | One-time code |
| Token endpoint `refresh_token` với rotation | Không retry mù | Có thể bị reuse detection |
| Client Credentials token request | Có thể thử lại có giới hạn khi transient | Tránh token storm, rate limit |

### 10.1. Idempotency key cho nghiệp vụ

API tạo resource có thể hỗ trợ:

~~~http
POST /api/orders
Idempotency-Key: stable-operation-uuid
~~~

Nếu server có đúng idempotency semantics, client có thể retry trong budget mà tránh tạo trùng. **Client tự thêm header không bảo đảm idempotency** nếu downstream không triển khai.

### 10.2. Authentication retry khác business retry

Trường hợp 401 invalid_token trước khi xử lý request có thể cho phép retry sau khi có token mới. Nhưng nếu request non-idempotent, phải biết Resource Server có thực sự từ chối request trước side effects hay không; đừng suy chung cho mọi custom middleware/proxy.

## 11. Decision tree trước khi xử lý lỗi

~~~text
HTTP operation failed
    |
    v
Which endpoint returned error?
    |
    +-- Portal to browser
    |     401 -> browser authentication/session flow
    |     403 -> Portal authorization
    |
    +-- Authorization Server / token endpoint
    |     OAuth2 error -> classify invalid_grant/client/scope...
    |     429 -> rate limit, respect backoff
    |     5xx -> transient availability, grant-safe retry policy
    |
    +-- UserInfo / Discovery / JWK Set
    |     401 -> endpoint token/config
    |     429/5xx -> metadata/userinfo dependency handling
    |
    +-- Downstream Resource Server
          401 + Bearer invalid_token?
             -> narrowly invalidate/re-authorize correct client
          403 / insufficient_scope?
             -> permissions/consent/RBAC; do not refresh loop
          429?
             -> quota, throttle, Retry-After, no token deletion
          5xx?
             -> availability/retry if idempotent; no token deletion
~~~

**Không có một global exception handler có thể tự chữa tất cả lỗi chỉ bằng HTTP status.** Handler cần biết endpoint type, request metadata và có thể cả OAuth2 error code.

## 12. Các trạng thái OAuth2AuthorizedClient cần hiểu

Một `OAuth2AuthorizedClient` liên kết:

~~~text
ClientRegistration
principalName
accessToken
refreshToken (nếu có)
~~~

Authorized-client manager có thể:

1. Tải authorized client hiện có.
2. Xem access token đã/sắp hết hạn chưa.
3. Dùng refresh token khi policy/provider cho phép.
4. Lưu authorized client mới.
5. Trả authorized client hoặc báo lỗi.

**Expiration metadata không bảo đảm Resource Server còn chấp nhận token.** Token có thể revoked hoặc sai audience.

### 12.1. Token còn hạn nhưng API trả 401

Có thể do token bị revoke, Resource Server chuyển issuer, audience sai hoặc client gửi nhầm token. Không sửa bằng tăng `expiresAt` trong store.

### 12.2. Token hết hạn nhưng browser vẫn login

Browser session/Authentication vẫn có thể hợp lệ dù access token của Orders API hết hạn. Manager có thể refresh token mà không cần yêu cầu user login lại nếu refresh grant hợp lệ.

### 12.3. Refresh token invalid không luôn logout mọi sessions

Nếu một authorized client bị `invalid_grant`, cần xử lý theo registration/principal, có thể yêu cầu reauthorization của client đó. Đừng xóa mọi client/token của user hoặc mọi tenant khi policy không yêu cầu.

## 13. Authorized-client failure handlers và phạm vi cleanup

Spring Security có extension points như:

~~~java
org.springframework.security.oauth2.client
    .OAuth2AuthorizationFailureHandler
~~~

và các integration cho OAuth2 Client HTTP requests có khả năng phản ứng với **OAuth2AuthorizationException** hoặc 401/403 theo configuration.

Mục tiêu:

~~~text
Failure of specific authorized client
  -> decide whether it is invalid
  -> remove/update that registration + principal entry
  -> do not delete unrelated authorized clients
~~~

### 13.1. 401 từ Resource Server không tự là OAuth2AuthorizationException

Một WebClient HTTP call trả 401 thường sinh:

~~~java
WebClientResponseException.Unauthorized
~~~

hoặc exception tương ứng theo client stack. Token endpoint grant failure từ provider lại có thể sinh:

~~~java
OAuth2AuthorizationException
~~~

Không giả định một manager failure handler sẽ tự động thấy tất cả downstream 401 nếu HTTP integration chưa wire đúng.

### 13.2. Chú ý success/failure persistence

Nếu custom manager thay `setAuthorizationSuccessHandler(...)` mà không lưu token mới, mọi request có thể xin token lại → token endpoint 429.

Nếu custom failure handler xóa authorized clients theo provider alias thay vì registration/principal, nó có thể làm mất tokens của nhiều OAuth clients/tenants.

### 13.3. Không gọi remove khi chỉ có 503

Lỗi availability từ Orders API không cho biết token sai. Xóa authorized client trên 503 thường chỉ gây thêm token endpoint traffic và login failures.

## 14. WWW-Authenticate: đọc đúng nhưng không tin tuyệt đối

Bearer authentication challenge có các tham số thường gặp:

~~~http
WWW-Authenticate: Bearer realm="orders", error="invalid_token",
                  error_description="The access token expired"
~~~

hoặc:

~~~http
WWW-Authenticate: Bearer realm="admin", error="insufficient_scope",
                  scope="admin.read"
~~~

Các field:

| Field | Ý nghĩa |
|---|---|
| Scheme `Bearer` | Authentication scheme liên quan OAuth Bearer |
| `realm` | Phạm vi bảo vệ tài nguyên (nếu có) |
| `error` | Bearer error code |
| `error_description` | Mô tả dành cho developer, không phải text tin cậy để hiện UI |
| `scope` | Scope được yêu cầu/tham khảo trong insufficient_scope |

### 14.1. Có thể có nhiều challenges

~~~http
WWW-Authenticate: Basic realm="legacy"
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

HTTP header parsing có quy tắc quoting/escaping; một parser đơn giản `split(",")` sẽ sai nếu quoted text chứa dấu phẩy.

Nếu cần quyết định tự động dựa trên Bearer error, dùng parser có nhận thức HTTP authentication grammar, giới hạn chiều dài header và chọn đúng challenge từ **trusted resource server**.

### 14.2. Không cho untrusted header điều khiển security policy

Một API bên ngoài không tin cậy có thể trả bất kỳ `WWW-Authenticate` header nào. Đừng để một URL do user cung cấp buộc ứng dụng xóa token của mọi tenants/chuyển login sang issuer lạ.

## 15. Retry-After: parse delta-seconds hoặc HTTP-date

Ví dụ:

~~~http
Retry-After: 20
~~~

hoặc:

~~~http
Retry-After: Wed, 18 Nov 2026 10:30:00 GMT
~~~

Một helper minh họa:

~~~java
package com.example.oauth.errors;

import java.time.Clock;
import java.time.Duration;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Optional;

public final class RetryAfterParser {
    private RetryAfterParser() {}

    public static Optional<Duration> parse(
        String header,
        Clock clock
    ) {
        if (header == null || header.isBlank()) {
            return Optional.empty();
        }

        String raw = header.trim();
        try {
            long seconds = Long.parseLong(raw);
            if (seconds < 0) {
                return Optional.empty();
            }
            return Optional.of(Duration.ofSeconds(seconds));
        } catch (NumberFormatException ignored) {
            // Có thể là HTTP-date.
        }

        try {
            ZonedDateTime date = ZonedDateTime.parse(
                raw, DateTimeFormatter.RFC_1123_DATE_TIME);
            Duration wait = Duration.between(
                clock.instant(), date.toInstant());
            return Optional.of(
                wait.isNegative() ? Duration.ZERO : wait);
        } catch (RuntimeException ignored) {
            return Optional.empty();
        }
    }
}
~~~

**Đây là helper cú pháp**, chưa áp policy. Caller phải clamp upper bound, áp overall deadline, jitter, retry budget và cancellation. Nếu server đưa Retry-After quá lớn, thường cần trả error cho user/job scheduler thay vì chờ vô hạn.

### 15.1. Không dùng Thread.sleep trong HTTP request thread để chờ hàng phút

Nếu 429 buộc chờ lâu, cân nhắc:

- Trả HTTP 429/503 thích hợp cho caller với thông báo.
- Schedule background retry qua queue/job scheduler.
- Rate limiter ở phía client.
- In-flight concurrency cap.

Với Reactor, dùng non-blocking delay/backoff, tránh `Thread.sleep()` trên event-loop.

## 16. Phân loại lỗi theo endpoint để giữ context

Một domain model có thể giúp tránh chỉ xử lý theo status:

~~~java
package com.example.oauth.errors;

public enum DependencyKind {
    AUTHORIZATION_SERVER_TOKEN,
    OIDC_USERINFO,
    OIDC_DISCOVERY_OR_JWKS,
    DOWNSTREAM_RESOURCE_SERVER,
    PORTAL_SESSION_OR_AUTHENTICATION
}
~~~

~~~java
package com.example.oauth.errors;

public enum FailureCategory {
    TOKEN_REJECTED,
    INSUFFICIENT_PERMISSION,
    CLIENT_CONFIGURATION,
    GRANT_INVALID,
    RATE_LIMITED,
    TRANSIENT_DEPENDENCY,
    PERMANENT_REQUEST_ERROR,
    UNKNOWN
}
~~~

Một result cho observability/policy:

~~~java
public record DependencyFailure(
    DependencyKind dependency,
    FailureCategory category,
    int httpStatus,
    String registrationId,
    String safeErrorCode,
    boolean retryable
) {}
~~~

Đây là **application DTO**, không phải type có sẵn của Spring. Đối với lỗi không có HTTP response (DNS failure, TLS failure, timeout), có thể dùng nullable status hoặc một field `OptionalInt` thay vì ép `httpStatus=500`.

### 16.1. Vì sao cần dependency kind?

~~~text
401 + DOWNSTREAM_RESOURCE_SERVER
  => xem Bearer token/Resource Server auth

401 + AUTHORIZATION_SERVER_TOKEN
  => xem client authentication/invalid_client

401 + PORTAL_SESSION_OR_AUTHENTICATION
  => xem browser session/login entry point
~~~

Cùng số 401, các hướng xử lý độc lập.

## 17. RestClient trên Servlet: bắt HTTP status đúng nguồn

Spring Framework 6.1+ cung cấp `RestClient`. Khi `retrieve()` gặp status 4xx/5xx, có thể nhận `RestClientResponseException` hoặc các subclass tùy trường hợp.

Ví dụ Orders API với **GET** idempotent:

~~~java
package com.example.portal.orders;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Service
public final class OrdersGateway {
    private final RestClient orders;

    public OrdersGateway(RestClient.Builder builder) {
        this.orders = builder
            .baseUrl("https://orders.example.test")
            .build();
    }

    public String getOrders(String accessToken) {
        try {
            return orders.get()
                .uri("/api/orders")
                .headers(h -> h.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);
        } catch (RestClientResponseException ex) {
            int status = ex.getStatusCode().value();

            if (status == 401) {
                // Chỉ signal: token/authentication bị API từ chối.
                throw new OrdersApiUnauthorizedException(ex);
            }
            if (status == 403) {
                throw new OrdersApiForbiddenException(ex);
            }
            if (status == 429) {
                throw new OrdersApiRateLimitedException(ex);
            }
            if (status >= 500 && status <= 599) {
                throw new OrdersApiUnavailableException(ex);
            }
            throw ex;
        }
    }
}
~~~

Các class `OrdersApiUnauthorizedException`, `OrdersApiForbiddenException`, `OrdersApiRateLimitedException` và `OrdersApiUnavailableException` là **application exception types cần tự tạo**. Ví dụ cho thấy classification theo nguồn **Orders API**, không phải xử lý OAuth2 token endpoint.

### 17.1. Không trả raw exception cho frontend

`RestClientResponseException` có thể mang response body chứa thông tin nhạy cảm hoặc text không đáng tin. Khi log/error response, chỉ đưa status, host allowlisted, safe error code, request ID và category.

### 17.2. Lấy WWW-Authenticate và Retry-After

~~~java
var headers = ex.getResponseHeaders();
String challenge = headers != null
    ? headers.getFirst("WWW-Authenticate")
    : null;
String retryAfter = headers != null
    ? headers.getFirst("Retry-After")
    : null;
~~~

Đây là fragment trong catch block. **Không log nguyên văn challenge/response body** nếu chưa redact và giới hạn độ dài; không dùng parser `split(",")` cho các Bearer challenges phức tạp.

## 18. WebClient: phân loại WebClientResponseException

Trong Spring WebFlux hoặc Servlet sử dụng WebClient:

~~~java
org.springframework.web.reactive.function.client.WebClientResponseException
~~~

`retrieve()` mặc định thường sinh một exception cho response 4xx/5xx.

~~~java
return webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class)
    .onErrorMap(
        WebClientResponseException.Unauthorized.class,
        ex -> new OrdersApiUnauthorizedException(ex))
    .onErrorMap(
        WebClientResponseException.Forbidden.class,
        ex -> new OrdersApiForbiddenException(ex))
    .onErrorMap(
        WebClientResponseException.TooManyRequests.class,
        ex -> new OrdersApiRateLimitedException(ex));
~~~

Ứng dụng cần giữ HTTP source context và thực hiện token/authorization/retry policy ở tầng phù hợp. Không chỉ `onErrorResume(e -> Mono.empty())` cho mọi lỗi, vì sẽ che sự cố và khiến caller hiểu nhầm “không có dữ liệu”.

### 18.1. Non-blocking retry cho GET khi 503/429

Ví dụ có giới hạn:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<String> result = webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(250))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(ex ->
                ex instanceof WebClientResponseException
                    .TooManyRequests
                || ex instanceof WebClientResponseException
                    .ServiceUnavailable
                || ex instanceof WebClientResponseException
                    .BadGateway
                || ex instanceof WebClientResponseException
                    .GatewayTimeout)
    );
~~~

Ở đây chỉ demo retry transient statuses cho **GET**. Production cần:

- Overall deadline/timeout và cancellation.
- `Retry-After` có ưu tiên khi hợp lệ.
- Rate limiter/circuit breaker và tránh retry storm.
- Không retry OAuth one-time grant request theo cùng logic.
- Không retry 401/403 mà chưa có cơ chế giải quyết authorization rõ.

### 18.2. Retry filter phải hẹp

Không dùng:

~~~java
.retryWhen(Retry.max(100))
~~~

cho mọi exceptions. 403, invalid_client và invalid_scope sẽ không tự biến thành success bằng retry; retry quá mức có thể gây load amplification.

### 18.3. Reactive error signal khác HTTP status

Network errors như DNS, connection reset hoặc TLS handshake failure có thể không có HTTP status. `WebClientRequestException` phản ánh lỗi request/transport, khác `WebClientResponseException` có HTTP response.

Đừng map tất cả transport exceptions thành `401` hoặc `503` mà làm mất nguồn lỗi.

## 19. OAuth2 WebClient/RestClient integration và auto token handling

Trên Servlet, Spring Security có integration:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

cho WebClient; với Spring Security 6.4+, có:

~~~java
OAuth2ClientHttpRequestInterceptor
~~~

cho RestClient.

Một integration có thể gắn đúng Bearer token được quản lý bởi `OAuth2AuthorizedClientManager` và tích hợp authorization failure handler theo phiên bản/cấu hình.

**Không giả định framework tự retry downstream 401 hoặc tự xóa token trong mọi cấu hình.** Cần kiểm tra:

1. Đã gắn filter/interceptor vào HTTP client thực sự dùng chưa?
2. ClientRegistration ID có đúng không?
3. Manager và AuthorizedClientRepository/Service có cùng storage không?
4. Authorization success/failure handlers có được cấu hình?
5. 401/403 từ Resource Server có thực sự được chuyển vào failure policy không?

### 19.1. Explicit registration selection

~~~text
Orders API -> orders-client
Admin API  -> admin-client
~~~

Không dùng default authorized client cho mọi hosts. Nếu truyền một Bearer token từ Orders sang một URL do attacker kiểm soát, có thể lộ credential ngay cả khi HTTP request thành công.

### 19.2. Login authentication khác downstream token

`oauth2Login()` xác thực browser/OIDC principal. `oauth2Client()` và manager xử lý authorized client. Một downstream API 401 không mặc nhiên có nghĩa cần xóa `SecurityContext` của browser.

## 20. Token refresh failure và reauthorization

Một sequence:

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant Portal as Portal/OAuth2 Client
    participant Store as Authorized Client Store
    participant AS as Authorization Server
    participant API as Orders API

    Browser->>Portal: GET /orders
    Portal->>Store: Load existing authorized client
    Store-->>Portal: AT1, RT1
    Portal->>API: GET /orders Bearer AT1
    API-->>Portal: 401 Bearer invalid_token
    Portal->>Store: Mark/remove specific invalid authorized client by policy
    Portal->>AS: Refresh/reauthorize if supported
    AS-->>Portal: AT2, RT2 or OAuth error
    Portal->>Store: Persist AT2/RT2 if successful
    Portal->>API: Optional one bounded retry with AT2
    API-->>Portal: 200 OK or error
    Portal-->>Browser: Response
~~~

Thực tế manager/provider chain thường kiểm tra expiry trước khi gọi API; diagram minh họa **trường hợp token bị API từ chối bất ngờ**.

### 20.1. Nếu refresh thất bại invalid_grant

Một refresh token revoked/expired/rotated có thể không thể dùng lại. Thường cần:

- Cleanup đúng authorized-client entry.
- Báo user cần authorize lại client hoặc login theo UX policy.
- Giữ những sessions/clients khác không liên quan nếu được phép.
- Không retry cùng refresh token vô hạn.

### 20.2. Nếu refresh thất bại HTTP 503

Đây là outage của Authorization Server, không chứng minh refresh token invalid. Có thể giữ record theo policy và yêu cầu thử lại sau, không xóa credential ngay.

### 20.3. Token invalid vì audience sai

Nếu refresh tạo AT mới có cùng audience sai, retry vẫn 401. Phải sửa client/AS/resource indicator configuration hoặc dùng đúng registration. **Không ép logout user để che lỗi cấu hình.**

## 21. 429 và 5xx: resilience patterns

Các biện pháp phù hợp:

| Pattern | Mục đích | Lưu ý |
|---|---|---|
| **Timeout/deadline** | Không chờ dependency vô hạn | Có cả per-call và end-to-end deadline |
| **Exponential backoff** | Giảm áp lực khi lỗi transient | Giới hạn số retries |
| **Jitter** | Tránh mọi pods retry đồng thời | Đặc biệt khi 429/503 |
| **Rate limiter** | Chủ động giữ quota | Theo client/tenant/API |
| **Bulkhead/concurrency limit** | Một dependency chậm không chiếm mọi threads | Cấu hình per dependency |
| **Circuit breaker** | Dừng gọi tạm thời khi dependency down | Không dùng như bypass auth |
| **Caching** | Giảm requests | Chỉ cache dữ liệu được phép, TTL đúng |
| **Queue/deferred retry** | Không giữ HTTP request lâu | Cần idempotency và dedup |
| **Single-flight token refresh** | Giảm refresh concurrency | Key theo registration/principal/tenant |

### 21.1. Không bật circuit breaker “fail open” cho authorization

Khi Authorization Server/Resource Server không trả lời, không được tự cho phép API nhạy cảm chỉ vì breaker mở.

~~~text
Dependency unavailable != permission granted
~~~

### 21.2. Một breaker chung cho tất cả IdPs có thể gây outage chéo

Trong multi-provider/multi-tenant app, nên đánh giá breaker/rate limiter theo **dependency identity** phù hợp thay vì một global breaker. Outage IdP A không nên tự chặn IdP B nếu chúng độc lập.

### 21.3. Caching không phải giải pháp cho mọi errors

Orders API 503 có thể được xử lý bằng stale cached read **chỉ khi** data contract, consistency, authorization và privacy policy cho phép. Không trả cached dữ liệu của user/tenant khác hoặc data nhạy cảm đã bị revoke quyền truy cập.

## 22. Rate-limit token endpoint: tránh thundering herd

Giả sử 100 pods cùng nhận AT hết hạn lúc `12:00:00`:

~~~text
12:00:00 -> 100 pods refresh cùng lúc
12:00:01 -> AS trả 429 cho một số pods
12:00:01 -> tất cả retry ngay
12:00:02 -> AS tiếp tục overload
~~~

Biện pháp:

1. Clock skew hợp lý, không quá lớn.
2. Persist authorized clients trong shared store theo kiến trúc.
3. Tránh tạo principalName ngẫu nhiên làm cache miss.
4. Lock/single-flight per authorized-client key khi cần.
5. Retry với exponential backoff và jitter.
6. Respect Retry-After và client quota.
7. Đặt concurrency budget/overall deadline.
8. Dùng token reuse theo security policy.

### 22.1. Không ghi lại refresh token cũ sau rotation

Nếu Pod A nhận RT2, Pod B có stale RT1, B không được overwrite store bằng RT1 chỉ vì hoàn tất sau. Cần optimistic concurrency/version guard phù hợp.

## 23. Browser UX và API errors: không tạo login redirect loop

Một BFF có thể có:

~~~text
Browser GET /orders
Portal calls Orders API
Orders API returns 401
~~~

Không nhất thiết redirect browser đến IdP ngay. Có thể:

- Thử lấy authorized client mới nếu policy cho phép.
- Nếu refresh token invalid, thông báo cần đăng nhập/authorize lại.
- Nếu Orders API cấu hình sai, trả lỗi dịch vụ không khả dụng và alert.

### 23.1. API clients và browser clients có entry points khác

Một JSON API route thường nên trả machine-readable 401/403 theo contract, không trả HTML login page/302 bất ngờ cho fetch nếu front-end không xử lý redirect.

Một browser page có thể redirect login. Chọn `AuthenticationEntryPoint` và access denied handling theo security chain/route.

### 23.2. Thông báo theo nguồn

| Tình huống | Thông báo thân thiện |
|---|---|
| Browser session không hợp lệ | “Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.” |
| User không có quyền | “Bạn không có quyền thực hiện thao tác này.” |
| Token cần reauthorization | “Cần cấp lại quyền truy cập dịch vụ.” |
| API rate limited | “Hệ thống đang xử lý nhiều yêu cầu. Vui lòng thử lại sau.” |
| Dependency unavailable | “Dịch vụ tạm thời không khả dụng. Vui lòng thử lại sau.” |

Không hiển thị raw access token, client ID/secret, stacktrace hoặc `error_description` có thông tin nội bộ.

## 24. Chọn HTTP status trả về browser một cách có chủ đích

Portal là một HTTP server độc lập. Downstream trả 401 **không bắt buộc** Portal phải trả 401 cho browser:

~~~text
Browser is authenticated to Portal.
Orders API rejects server-managed token.
Portal's browser authentication may still be valid.
~~~

Theo API contract, Portal có thể trả 502/503 hoặc một application error code sau khi đã hết reauthorization policy, để thể hiện **downstream dependency failure** thay vì “browser chưa đăng nhập”.

Ngược lại, nếu browser session hết hạn, trả 401/redirect login là phù hợp. Nếu user không được phép gọi resource dù đã authenticated, 403 hợp lý.

**Không map mọi downstream 401 thành browser 401**, vì frontend có thể xóa session hoặc rơi vào login loop không giải quyết được lỗi.

## 25. Observability: những thông tin cần ghi để chẩn đoán

Một log event an toàn:

~~~json
{
  "timestamp": "2026-11-16T04:30:00Z",
  "service": "employee-portal",
  "operation": "orders.read",
  "dependency": "orders-api",
  "dependencyKind": "DOWNSTREAM_RESOURCE_SERVER",
  "registrationId": "orders-client",
  "httpStatus": 401,
  "oauthErrorCode": "invalid_token",
  "attempt": 1,
  "retryScheduled": false,
  "correlationId": "req-a17"
}
~~~

Đây là **schema instrumentation minh họa**, không phải Spring Boot tự log mọi field trên.

### 25.1. Không log credentials

Không ghi:

~~~text
Authorization: Bearer <real-access-token>
Authorization: Basic <client-secret>
Cookie: JSESSIONID=<real-session>
refresh_token=<real-refresh-token>
authorization_code=<real-code>
id_token=<real-id-token>
client_secret=<real-client-secret>
~~~

Đặc biệt cẩn thận với HTTP wire logging, proxy logs, full request/response dump và exception messages. Token endpoint bodies thường chứa secrets và one-time credentials.

### 25.2. PII và high-cardinality labels

Metrics labels như full email, subject, raw user ID, URL có query, access token hoặc correlation ID gây rủi ro bảo mật và chi phí cardinality. Nên dùng:

~~~text
dependencyKind
registrationId (allowlisted)
safe error code
httpStatus
tenant tier / low-cardinality tenant group khi phù hợp
~~~

Correlation ID nên là log/tracing attribute có kiểm soát, không phải metric label high-cardinality.

## 26. Những metrics nên có

| Metric (tên ví dụ) | Diễn giải |
|---|---|
| `oauth.token.request.count` | Số lượt xin token theo grant/registration |
| `oauth.token.request.error` | Lỗi token endpoint theo OAuth code |
| `oauth.token.refresh.count` | Tần suất refresh |
| `oauth.authorized_client.cache_hit` | Có tái sử dụng token không |
| `http.client.response.status` | 401/403/429/5xx theo dependency |
| `http.client.retry.count` | Retry attempts và kết quả |
| `http.client.retry_exhausted` | Hết retry budget |
| `rate_limit.observed` | Quota hits |
| `circuit_breaker.state` | CLOSED/OPEN/HALF_OPEN theo dependency |
| `oauth.resource.invalid_token` | Resource Server từ chối Bearer |
| `oauth.resource.insufficient_scope` | Resource Server từ chối quyền |
| `idp.discovery.failure` | Metadata/JWK dependency issues |

Đây là **các metric đề xuất**, không phải tên mặc định chắc chắn có trong Micrometer/Spring Boot. Instrument theo công cụ quan sát đang dùng và tránh cardinality không kiểm soát.

### 26.1. Phân biệt error rate và retry rate

Một request có thể retry 3 lần rồi thành công. Nếu chỉ đo số **final failures** sẽ bỏ sót pressure lên IdP. Nên có metrics cho:

- Attempts.
- Retries.
- Success after retry.
- Retry exhaustion.
- Per-dependency latency.
- Queue depth/rate-limit delay.

### 26.2. Correlate login và downstream

Một browser flow có nhiều request IDs:

~~~text
browser request ID
oauth state correlation (không log raw nếu không cần)
token endpoint attempt ID
downstream request ID
distributed trace ID
~~~

Không nhét raw `state`/nonce/token vào tracing. Dùng correlation IDs được phát riêng và mapping an toàn.

## 27. Tracing ranh giới IdP và downstream

Một trace minh họa:

~~~text
HTTP GET /orders                          420 ms
  OAuth2AuthorizedClientManager            35 ms
    AuthorizedClientStore load             10 ms
    Token endpoint refresh                 22 ms
  Orders API GET /api/orders              350 ms
    HTTP 503
  Retry decision                           1 ms
  Response to browser                      ...
~~~

Nếu có nhiều external dependencies, instrumentation nên giúp thấy:

- Slow ở authorized-client storage?
- Chậm khi refresh token?
- IdP discovery/JWK fetch timeout?
- Downstream API 5xx hay timeout?
- App có retry storms?

Không đưa access token, refresh token hoặc client secret vào span attributes. Nếu ghi URLs, nên dùng route template hoặc URL đã bỏ query/secret.

### 27.1. Đừng log raw OAuth response body

AS `error_description` có thể vô tình chứa user information/client details. Chỉ log sanitized OAuth error code và một message nội bộ đã kiểm soát.

## 28. Phân biệt lỗi hạ tầng chưa có HTTP response

Không phải lỗi nào cũng có status:

~~~text
DNS resolution failure
TLS handshake/certificate failure
Connection refused/reset
Connect timeout
Read timeout
Proxy authentication failure
Connection pool exhaustion
~~~

Không map các lỗi này thành `401` hoặc `invalid_grant`. Với timeout, request có thể đã đến server và được xử lý, đặc biệt nguy hiểm cho POST/token rotation.

### 28.1. TLS errors cần sửa trust/config

Không dùng `trustAllCertificates` hay disable hostname verification để “chữa” token endpoint 5xx/timeout. TLS trust sai là vấn đề bảo mật/configuration; retry sẽ không tự sửa.

### 28.2. Proxy 407

`407 Proxy Authentication Required` là authentication của proxy, không phải resource server Bearer 401. Cần điều tra proxy credentials/network route.

## 29. OIDC discovery/JWKS failures và phân loại đúng

OIDC Provider công bố metadata như:

~~~text
issuer
authorization_endpoint
token_endpoint
jwks_uri
userinfo_endpoint
~~~

Nếu discovery/JWKS endpoint trả 429/5xx:

- Login mới có thể gặp lỗi xác minh ID Token.
- Cần kiểm tra metadata/JWK cache và key rotation policy.
- Có thể retry/backoff giới hạn cho metadata fetch.
- Không bỏ signature/issuer/audience validation vì không tải được keys.

### 29.1. Key rotation và kid chưa có

Nếu ID Token ký bằng một `kid` chưa thấy trong JWKS cache, client có thể cần refresh JWKS theo cơ chế thư viện. Nhưng nếu JWKS endpoint đang 503, **không chấp nhận ID Token chưa được xác minh**. Có thể fail closed và yêu cầu retry login khi dependency hồi phục.

### 29.2. UserInfo 401

UserInfo thường nhận access token:

~~~http
GET /userinfo
Authorization: Bearer <access-token>
~~~

Nếu UserInfo trả 401, xem token validity/audience/scope/userinfo policy và OIDC flow. Không chuyển sang tin một UserInfo JSON chưa authenticated hoặc tự tạo principal từ unverified claims.

### 29.3. Authorization endpoint errors đến qua browser

Authorization Server có thể redirect về callback với:

~~~text
?error=access_denied&state=...
~~~

Đây là **OAuth authorization response error** do OP trả qua browser, không phải HTTP 403 từ Orders API. Callback vẫn cần state/issuer/correlation validation. UX có thể giải thích user từ chối consent hoặc provider policy không cho phép.

## 30. Incident runbook: downstream 401 tăng đột biến

Khi dashboard báo Orders API 401 tăng:

1. Xác nhận **source**: Orders API hay Portal route?
2. Kiểm tra `WWW-Authenticate` scheme và Bearer error code.
3. So sánh theo registration ID/client ID (không log secrets).
4. Kiểm tra access token audience/issuer/scope/expiry và clock skew.
5. Kiểm tra thay đổi config tại Orders API hoặc IdP.
6. Xem manager có đang load đúng authorized client/refresh đúng không.
7. Xem token mới có tiếp tục 401 không.
8. Nếu nhiều tenants, xác nhận không dùng chéo token.
9. Thử rollback config thay vì cưỡng chế logout toàn bộ user.
10. Theo dõi số retries và token endpoint load.

**Nếu token mới vẫn 401, dừng refresh loop.** Cần sửa trust/audience/configuration trước.

## 31. Incident runbook: 403 tăng đột biến

1. Xác nhận user đã authenticated hay chưa.
2. Xem Resource Server `insufficient_scope` hay app-specific policy.
3. Xem requested/scopes granted và resource audience.
4. So sánh role/tenant membership, ownership/feature flags.
5. Kiểm tra deploy/policy change ở API.
6. Không tự tăng scope hoặc đổi sang privileged client.
7. Nếu cần consent mới, đưa user qua authorization flow đúng.
8. Trả 403 có ý nghĩa và không loop login.

Một 403 hàng loạt sau deploy thường là **authorization policy regression**, không nhất thiết token issue.

## 32. Incident runbook: token endpoint 429

1. Xác nhận token endpoint/registration nào bị rate limit.
2. Xem token issuance/refresh rate có tăng đột biến không.
3. Kiểm tra authorized-client store hit rate và persistence.
4. Kiểm tra principalName/registration key có bất ổn không.
5. Kiểm tra clock skew và token lifetime.
6. Kiểm tra nhiều pods refresh cùng token.
7. Giảm concurrency và retries, respect Retry-After.
8. Xem có deploy mới vô tình bỏ cache/repository hay không.
9. Nếu cần tăng quota, làm việc với IdP sau khi sửa client behavior.
10. Không xóa tất cả tokens để “reset” rate limit.

### 32.1. Token refresh on every request

Một dấu hiệu:

~~~text
Portal RPS = 100
Token endpoint RPS = 100
~~~

Nếu không có lý do grant đặc biệt, đây là dấu hiệu cần điều tra token reuse, expired metadata, storage/success handler hoặc client registration selection.

## 33. Incident runbook: 5xx/timeout

1. Xác định upstream: AS, UserInfo, JWKS, Orders API, proxy hay internal DB.
2. Xem error/latency/concurrency theo dependency.
3. Xác nhận request method và idempotency.
4. Xem `Retry-After` hoặc maintenance notice nếu có.
5. Kích hoạt bounded retry/backoff cho safe operations.
6. Dùng circuit breaker/bulkhead nếu dependency đang overload.
7. Không reset tokens/sessions vì 5xx.
8. Bảo vệ thread pools, event loops và connection pools.
9. Trả UI/API error theo contract; không che lỗi thành empty data.
10. Audit retries nếu POST đã có thể tạo side effects.

Nếu một POST timeout sau khi đến server, cần xác minh operation status hoặc idempotency key thay vì replay tùy tiện.

## 34. Kiểm thử với mock downstream HTTP server

Một integration test nên giả lập responses:

~~~text
Case A:
  GET /orders -> 401 Bearer invalid_token
  Expected: reauthorization policy scoped to current authorized client

Case B:
  GET /admin -> 403 Bearer insufficient_scope
  Expected: no refresh storm; permission error

Case C:
  GET /orders -> 429 Retry-After: 2
  Expected: rate-limit policy/backoff, no token deletion

Case D:
  GET /orders -> 503
  Expected: bounded safe retry, final unavailable if exhausted

Case E:
  POST /orders -> 504
  Expected: no blind replay without idempotency contract
~~~

Test bằng MockWebServer/WireMock hoặc một fake HTTP server phù hợp. Không gọi production IdP trong unit tests.

### 34.1. Token endpoint test cần mock OAuth error

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant"}
~~~

Test mong đợi:

- Token-response client map OAuth error code phù hợp.
- Failure handler chỉ tác động đúng registration/principal.
- Không retry cùng refresh token mù quáng.
- Không log request body chứa refresh token.

### 34.2. 429 Retry-After tests

Các giá trị:

~~~text
Retry-After: 0
Retry-After: 30
Retry-After: Wed, 18 Nov 2026 10:30:00 GMT
Retry-After: not-a-date
Retry-After: -12
~~~

Test parser và **policy clamp** riêng: không delay âm/vô hạn, overall deadline vẫn được tôn trọng.

### 34.3. Test 5xx với POST

Mock server nhận POST tạo đơn rồi trả 504. Test xác minh client **không gửi lại request** nếu không có idempotency key/contract.

## 35. Unit test classifier và retry policy

Một classifier nên cho ra kết quả:

| Input | Category | Retry |
|---|---|---|
| Downstream 401 Bearer invalid_token | TOKEN_REJECTED | Chỉ retry sau xử lý token hợp lệ, có giới hạn |
| Downstream 403 insufficient_scope | INSUFFICIENT_PERMISSION | Không |
| Downstream 429 | RATE_LIMITED | Có thể, respect Retry-After/budget |
| Downstream 503 GET | TRANSIENT_DEPENDENCY | Có thể |
| Downstream 504 POST không idempotency | TRANSIENT_DEPENDENCY | Không auto-replay |
| Token endpoint 400 invalid_grant | GRANT_INVALID | Không retry cùng credential |
| Token endpoint 401 invalid_client | CLIENT_CONFIGURATION | Không |
| JWKS 503 | TRANSIENT_DEPENDENCY | Có thể retry metadata fetch, fail closed validation |

### 35.1. Test multi-registration

~~~text
Orders authorized client = (orders-client, alice)
Admin authorized client  = (admin-client, alice)

Orders returns 401 invalid_token.

Expect:
  Only orders-client/alice entry may be invalidated.
  admin-client/alice entry remains unchanged.
~~~

### 35.2. Test multi-tenant

~~~text
ACME Orders API -> 401 invalid_token
GLOBEX Orders API -> 200 OK

Expect:
  No GLOBEX authorized-client cleanup.
  No GLOBEX secret rotation.
  No cross-tenant Bearer token reuse.
~~~

### 35.3. Test backpressure/thundering herd

Giả lập nhiều requests cùng thấy token near expiry. Xác nhận cache/single-flight hoặc refresh strategy không tạo số token endpoint calls tỷ lệ thuận vô hạn với concurrency.

## 36. Security pitfalls khi xử lý lỗi

**1. Log raw Authorization header để debug 401.** Token có thể bị đánh cắp.

**2. Hiển thị OAuth error_description thẳng ra HTML.** Có thể lộ thông tin nội bộ hoặc gây injection khi render sai.

**3. Refresh token trên mọi 403.** Không cấp quyền; gây rate limit.

**4. Retry 429 không có delay.** Có thể tạo cascading failure.

**5. Retry mọi POST sau 504.** Có thể trùng nghiệp vụ hoặc replay one-time grants.

**6. Xóa mọi authorized clients vì một invalid_grant.** Hỏng sessions/tenants khác.

**7. Dùng service token đặc quyền để tránh user 403.** Vượt chính sách phân quyền.

**8. Chấp nhận ID Token chưa verify khi JWKS 503.** Vi phạm OIDC security boundary.

**9. Không phân biệt Portal 401 và Resource Server 401.** Gây logout/login loop.

**10. Bật HTTP wire logging cả token endpoint.** Lộ client secret, code và refresh token.

**11. Tin Retry-After vô hạn, không giới hạn deadline.** Exhaust threads/resources.

**12. Nhận untrusted URL rồi đính Bearer token và follow redirect.** SSRF/exfiltration.

**13. Map mọi network failure thành invalid_token.** Xóa credential hợp lệ.

**14. Không có metrics per dependency.** Khó biết IdP hay Orders API đang lỗi.

## 37. Bài tập thực hành

### Bài 1 — Orders API 401 invalid_token

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

**Hỏi:** Có nên logout browser ngay?

**Hướng giải:** Không mặc định. Xác định authorized client và token bị API từ chối; có thể cleanup/re-authorize có giới hạn, kiểm tra issuer/audience nếu token mới vẫn 401.

### Bài 2 — Admin API 403 insufficient_scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="admin.read"
~~~

**Hỏi:** Refresh liên tục có nâng quyền không?

**Hướng giải:** Không. Xem scope/grant/consent và RBAC/resource authorization. Không dùng privileged service token để bypass.

### Bài 3 — Token endpoint 401 invalid_client

~~~json
{"error":"invalid_client"}
~~~

**Hỏi:** Cần refresh access token hay sửa cấu hình?

**Hướng giải:** Xác minh client ID/secret/mTLS/private_key_jwt/rotation và Authorization Server client policy. Retry với credential sai không giải quyết.

### Bài 4 — Orders API 429

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 20
~~~

**Hỏi:** Có nên xóa access token?

**Hướng giải:** Không. Rate limit thuộc downstream API; throttle/backoff, budget và UI phù hợp.

### Bài 5 — AS 503 trong refresh

**Hỏi:** Có chứng minh refresh token bị revoke không?

**Hướng giải:** Không. Đây là availability failure. Giữ/cleanup theo policy có cơ sở; không xóa token chỉ vì 503.

### Bài 6 — Token endpoint 400 invalid_grant

Refresh token RT1 đã rotate thành RT2 ở node khác.

**Hỏi:** Retry RT1 lần nữa?

**Hướng giải:** Không retry mù. Kiểm tra race, authorized-client version, store token generation và refresh rotation policy.

### Bài 7 — POST tạo đơn gặp 504

**Hỏi:** Retry ngay có an toàn không?

**Hướng giải:** Không tự suy an toàn; request có thể đã được xử lý. Cần operation status/idempotency contract.

### Bài 8 — Portal trả 401 nhưng Orders API vẫn hoạt động

**Hỏi:** Có nhất thiết token sai?

**Hướng giải:** Không. Browser session/authentication có thể hết hạn; khác downstream OAuth authorized client.

### Bài 9 — JWKS endpoint 503

**Hỏi:** Có thể tạm bỏ chữ ký ID Token để user login không?

**Hướng giải:** Không. Phải fail closed token verification, dùng metadata caching/retry phù hợp, alert IdP outage.

### Bài 10 — Multi-tenant cleanup

ACME Orders API 401; GLOBEX Orders API 200.

**Hỏi:** Xóa hết tokens của cùng issuer?

**Hướng giải:** Không. Cleanup đúng tenant, registration, principal và token generation nếu cần.

## 38. Checklist vận hành cho 401/403/429/5xx

| Câu hỏi | Điều cần xác nhận |
|---|---|
| HTTP response của bên nào? | Browser-facing Portal / AS / UserInfo / JWKS / Resource Server |
| Request method và endpoint? | GET/POST, token endpoint hay business API |
| Có OAuth2 error code? | invalid_grant/invalid_client/invalid_scope/... |
| Có WWW-Authenticate? | Bearer challenge, invalid_token/insufficient_scope |
| Có Retry-After? | Parse, clamp, deadline |
| Token của registration nào? | Registration+principal+tenant đúng |
| Browser session có còn hợp lệ? | Tách với downstream token |
| Access token đã hết hạn? | expiresAt, skew, actual API rejection |
| Refresh token còn hiệu lực? | Rotation/revocation/AS response |
| Issuer/audience/scopes đúng? | Resource Server validation |
| User có business permission? | RBAC/tenant/resource ownership |
| Status 429 thuộc quota nào? | AS, UserInfo, API, tenant/client/IP |
| 5xx đến từ proxy hay service? | Dependency trace/metrics |
| Request có idempotent? | Không replay POST mù quáng |
| Retry policy có giới hạn? | Attempts, deadline, jitter/backoff |
| Có circuit breaker/bulkhead? | Không fail open authorization |
| Authorized-client cleanup có phạm vi? | Không xóa toàn provider/tenant |
| Token endpoint calls có tăng bất thường? | Cache/expiry/refresh storm |
| Logging có lộ credentials? | Redact headers/bodies/query |
| Metrics phân biệt dependency? | Có |
| Tests 401/403/429/5xx? | Có, gồm negative cases |
| Incident runbook và rollback? | Có |

## 39. Tổng kết

Trong **Spring Security OAuth 2.0/OIDC Client**, cần hiểu cả **mã HTTP** lẫn **nguồn phát lỗi**. **401** từ Resource Server thường liên quan Bearer token hoặc authentication của API; **401** ở token endpoint có thể liên quan OAuth client authentication; **401** từ Portal có thể chỉ là browser session. **403** thường là authorization/scope/resource policy — refresh token không tự cấp quyền. **429** là quota/rate limit — cần `Retry-After`, throttling và bounded backoff. **5xx** thường phản ánh dependency availability — không tự xóa token hoặc logout user.

Quyết định retry phải dựa trên **idempotency, grant semantics, deadline và dependency**. Authorization code và rotating refresh token là credentials có one-time/rotation constraints, không được replay mù. Authorized-client cleanup cần đúng **registration/principal/tenant**, tránh race với refresh token mới. Resource Server còn kiểm tra issuer/audience/scopes; một token còn hạn không đảm bảo API chấp nhận nó.

Cuối cùng, observability tốt cần **per-dependency metrics, safe OAuth error codes, request correlation, retry/failure rates và tracing** nhưng không log access token, refresh token, client secret, code hoặc session cookie. Khi phân loại đúng lỗi, ứng dụng có thể giữ phiên người dùng ổn định trong một downstream outage, giảm token storms và vẫn bảo toàn các ranh giới **authentication, authorization, token lifecycle và availability**.
