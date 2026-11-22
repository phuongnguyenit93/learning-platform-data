# 17.8. `invalid_grant`, token bị thu hồi và yêu cầu đăng nhập lại

Trong **Spring Security OAuth 2.0/OIDC Client**, `refresh_token` giúp ứng dụng xin access token mới tại Token Endpoint mà không cần đưa người dùng qua màn hình đăng nhập mỗi lần access token hết hạn. Nhưng refresh token không phải một quyền truy cập vĩnh viễn. Nó có thể hết hạn, bị thu hồi, đã được thay thế bởi token mới sau rotation, không còn gắn với Client hợp lệ, hoặc bị Authorization Server từ chối vì lý do chính sách.

Một tình huống điển hình:

```text
Người dùng đã kết nối ứng dụng với nhà cung cấp OIDC.
Ứng dụng lưu OAuth2AuthorizedClient có access token và refresh token.
Access token hết hạn.
Spring Security gọi Token Endpoint với grant_type=refresh_token.
Authorization Server trả HTTP 400, error=invalid_grant.
```

**Ứng dụng cần xử lý thế nào?** Không nên lặp lại request refresh vô hạn; cũng không nên tự động dùng token người dùng khác, xóa toàn bộ dữ liệu tài khoản hoặc coi mọi lỗi 401 từ API là lỗi `invalid_grant`. Tùy ngữ cảnh, cần loại bỏ authorized client không còn hợp lệ, giữ trạng thái kết nối là **cần cấp quyền lại**, và khởi động một **Authorization Code/OIDC Login mới** có sự tham gia của người dùng khi cần.

Bài học phân tích ý nghĩa chuẩn của `invalid_grant`, phân biệt revocation/expiration/rotation, cách Spring Security xử lý lỗi refresh, những lỗi dễ nhầm ở Resource Server, cách thiết kế UX reauthorization và chiến lược vận hành an toàn trong ứng dụng Servlet lẫn tác vụ nền.

## 1. Refresh token ở đâu trong OAuth 2.0/OIDC Login?

Với Authorization Code Flow, trình duyệt được chuyển tới OpenID Provider (OP), sau đó quay về Client cùng authorization code. Spring đổi code tại Token Endpoint, nhận access token và có thể nhận refresh token.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as Spring Security OAuth2 Client
    participant AS as Authorization Server
    participant API as Resource Server

    U->>B: Bắt đầu đăng nhập/kết nối
    B->>C: GET /oauth2/authorization/company
    C-->>B: 302 tới Authorization Endpoint
    B->>AS: Đăng nhập và đồng ý cấp quyền nếu cần
    AS-->>B: Redirect về callback?code=...&state=...
    B->>C: GET /login/oauth2/code/company
    C->>AS: POST /token grant_type=authorization_code
    AS-->>C: access_token + id_token + refresh_token?
    C->>C: Xác minh OIDC và lưu authorized client
    C->>API: Authorization: Bearer access_token
    API-->>C: 200 OK
    Note over C: Sau một khoảng thời gian, access token gần/hết hạn
    C->>AS: POST /token grant_type=refresh_token
    alt Refresh thành công
        AS-->>C: access_token mới (+ refresh_token mới?)
        C->>C: Cập nhật authorized client
        C->>API: Gọi API bằng access token mới
    else Refresh không hợp lệ
        AS-->>C: HTTP 400 error=invalid_grant
        C->>C: Dừng dùng refresh token lỗi, xử lý state
        C-->>B: Đề nghị kết nối/đăng nhập lại khi thích hợp
    end
```

Các thuật ngữ cần tách rõ:

| Thuật ngữ | Ý nghĩa | Kết luận không được tự suy ra |
|---|---|---|
| **Access token** | Credential gọi API/Resource Server | Token chưa hết `expiresAt` không chắc chắn chưa bị thu hồi |
| **Refresh token** | Credential xin access token mới tại Token Endpoint | Có refresh token không bảo đảm nó còn hợp lệ |
| **ID Token** | JWT xác minh danh tính trong OIDC | Không dùng thay access token cho API |
| **HTTP session** | Trạng thái đăng nhập tại ứng dụng Spring MVC | Session còn không bảo đảm access/refresh token dùng được |
| **`OAuth2AuthorizedClient`** | Registration + principal + access token/refresh token đã cấp | Có object trong database không bảo đảm Token Endpoint chấp nhận refresh |
| **Reauthorization** | Người dùng đi qua flow cấp quyền mới khi cần | Không nhất thiết đòi nhập password nếu IdP vẫn có session hợp lệ |

Một ứng dụng có thể vẫn coi người dùng **đã đăng nhập vào website** trong khi kết nối tới API bên ngoài cần **cấp quyền lại**. Đây là hai trạng thái cần thiết kế riêng.

## 2. Hiểu đúng `invalid_grant` theo OAuth 2.0

Theo **RFC 6749, Section 5.2**, `invalid_grant` là mã lỗi Token Endpoint báo rằng authorization grant hoặc refresh token được cung cấp không hợp lệ, đã hết hạn, bị thu hồi, không khớp Redirect URI khi áp dụng hoặc được cấp cho Client khác.

Ví dụ phản hồi:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant",
  "error_description": "Refresh token is invalid or expired"
}
```

`error_description` chỉ là mô tả tùy chọn do nhà cung cấp trả. Có provider trả chi tiết hơn, có provider chỉ trả `invalid_grant`. Đừng tự phụ thuộc vào nội dung câu mô tả để quyết định an toàn.

### 2.1. `invalid_grant` không đồng nghĩa duy nhất “token bị thu hồi”

Những nguyên nhân thường gặp khi sử dụng `grant_type=refresh_token`:

1. Refresh token đã **hết hạn tuyệt đối**.
2. Refresh token có **idle timeout**, lâu không dùng nên mất hiệu lực.
3. Người dùng **thu hồi consent** hoặc ngắt kết nối ứng dụng tại IdP.
4. Quản trị viên/nhà cung cấp **thu hồi token hoặc phiên liên quan**.
5. Refresh token đã được **xoay vòng (rotation)** và token cũ không còn được chấp nhận.
6. Một request refresh song song đã dùng token cũ trước đó, làm request còn lại bị từ chối.
7. Refresh token được cấp cho **Client khác** hoặc environment khác.
8. Token được lưu/cập nhật sai, cắt chuỗi, dùng phiên bản cũ từ cache/backup.
9. Client đã đổi chính sách/registration, khiến refresh token không còn phù hợp với Client hiện tại.
10. Provider giới hạn thời gian, phiên hoặc chính sách bảo mật riêng.

**Không thể xác định nguyên nhân chính xác chỉ từ mã `invalid_grant`.** Muốn biết do revocation, rotation hay hết hạn phải kiểm tra ngữ cảnh, audit của Authorization Server (khi có), token lifecycle và các lần refresh trước đó.

### 2.2. Cùng mã lỗi còn xuất hiện khi đổi authorization code

`invalid_grant` **không chỉ dành cho refresh token**. Token Endpoint có thể trả lỗi này ở bước `grant_type=authorization_code` nếu:

- Code đã hết hạn.
- Code đã được sử dụng.
- Redirect URI không khớp yêu cầu ban đầu.
- PKCE `code_verifier` không hợp lệ.
- Code bị thu hồi hoặc không thuộc Client hiện tại.

Do đó bước đầu tiên khi debug phải là hỏi: **request đến Token Endpoint đang dùng `authorization_code` hay `refresh_token`?**

| Grant đang xử lý | `invalid_grant` thường liên quan | Phản ứng |
|---|---|---|
| `authorization_code` | Code/PKCE/Redirect URI/callback không hợp lệ | Chẩn đoán flow login; có thể bắt đầu lại flow, không tự thao tác refresh token |
| `refresh_token` | Refresh token expired/revoked/rotated/wrong Client | Loại trạng thái refresh lỗi; yêu cầu reauthorization khi cần |
| Grant mở rộng | Dữ liệu grant đặc thù của provider | Theo chuẩn và hợp đồng của grant đó |

Không áp một handler “logout tất cả người dùng” cho mọi `invalid_grant` bất kể grant và nguồn lỗi.

## 3. Phân biệt ba nhóm lỗi: Token Endpoint, Resource Server và OIDC Login

Một lỗi thường gây mất thời gian là gom tất cả HTTP 401/403 và `invalid_grant` thành “refresh token bị hỏng”.

### 3.1. Lỗi refresh tại Token Endpoint

Ví dụ:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic EXAMPLE_CLIENT_AUTH

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
```

Phản hồi:

```json
{
  "error": "invalid_grant"
}
```

Điều này nói Token Endpoint **không chấp nhận credential refresh**. Gọi lại bằng đúng refresh token ấy thường không thể sửa vấn đề và có thể kích hoạt chính sách chống reuse.

### 3.2. Lỗi 401 tại Resource Server khi dùng access token

Ví dụ:

```http
GET /api/events HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

Phản hồi:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Đây là lỗi **API không chấp nhận access token**. Nguyên nhân có thể là hết hạn, thu hồi, chữ ký/issuer/audience không đúng hoặc sai cấu hình token. Client có thể cần lấy token mới hoặc sửa registration; **chưa thể khẳng định refresh token đã bị thu hồi**.

### 3.3. Lỗi 403 do thiếu quyền

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Token có thể hợp lệ nhưng thiếu scope/quyền cần thiết. Làm mới token theo **cùng scope cũ** thường không tạo thêm quyền. Có thể cần yêu cầu quyền bổ sung/consent mới hoặc thay cấu hình quyền tại Authorization Server.

### 3.4. Bảng so sánh

| Nguồn | Dạng lỗi | Ý nghĩa chính | Hướng xử lý |
|---|---|---|---|
| Token Endpoint | `400 invalid_grant` khi refresh | Refresh credential không còn được chấp nhận | Không lặp bằng token cũ; dọn authorized client và reauthorize khi cần |
| Token Endpoint | `401/400 invalid_client` | Xác thực Client thất bại | Kiểm tra Client ID/secret/authentication method; không bắt mọi user đăng nhập lại |
| Token Endpoint | `400 invalid_scope` | Scope yêu cầu không hợp lệ | Sửa scope/consent/configuration |
| Resource Server | `401 invalid_token` | Access token không được API chấp nhận | Xem expiry, revocation, audience; cơ chế token refresh nếu thích hợp |
| Resource Server | `403 insufficient_scope` | Thiếu quyền API | Xin quyền đúng hoặc từ chối thao tác |
| OAuth2 Login callback | `invalid_grant` khi đổi code | Code/PKCE/Redirect URI/Client mismatch | Xem flow authorization code |
| Spring MVC | HTTP 401/302 từ ứng dụng | Có thể chưa có session hoặc entry point yêu cầu login | Phân biệt ứng dụng không authenticated và provider token failure |

**Nguyên tắc:** Phân loại lỗi theo endpoint, grant và lớp gọi trước khi quyết định xóa token hay yêu cầu người dùng đăng nhập lại.

## 4. Khi nào access token hết hạn sẽ dẫn đến refresh?

Trong Spring Security, `OAuth2AuthorizedClient` chứa `OAuth2AccessToken` và có thể chứa `OAuth2RefreshToken`. Khi một `OAuth2AuthorizedClientManager` được cấu hình với `refreshToken()`, provider có thể làm mới access token khi nó đã hoặc gần hết hạn theo chính sách.

```text
OAuth2AuthorizedClient
  ├── ClientRegistration
  ├── principalName
  ├── OAuth2AccessToken
  │    ├── tokenValue
  │    ├── issuedAt
  │    ├── expiresAt
  │    └── scopes
  └── OAuth2RefreshToken? (nullable)
```

Các tình huống:

| Token state | Provider có thể làm gì? |
|---|---|
| Access token còn phù hợp | Trả lại authorized client đang có |
| Access token gần hết hạn, refresh token hợp lệ | Gọi refresh grant và lưu access token mới |
| Access token đã hết hạn, không có refresh token | Không thể refresh bằng grant này; cần luồng khác |
| Refresh token đã bị thu hồi | Token Endpoint trả `invalid_grant` hoặc lỗi provider tương ứng |
| ClientRegistration dùng `client_credentials` | Thường xin access token mới bằng client credentials, không cần refresh token |
| Không có authorized client được lưu | Background manager không tự tạo user consent hoặc authorization code tương tác |

**Có `refreshToken()` trong provider builder không làm Authorization Server tự cấp refresh token.** Nhà cung cấp quyết định cấp token nào theo Client registration, grant, consent, scope và policy.

### 4.1. `expires_in` là của access token, không phải bảo hành refresh token

Token response:

```json
{
  "access_token": "ACCESS_1",
  "token_type": "Bearer",
  "expires_in": 1800,
  "refresh_token": "REFRESH_1",
  "scope": "openid profile calendar.read"
}
```

`expires_in=1800` mô tả thời gian sống access token. Nó **không nói refresh token cũng sống 1.800 giây**. Refresh token có thể có thời gian sống, idle timeout hoặc chính sách thu hồi riêng, đôi khi không được mô tả trực tiếp trong response theo chuẩn OAuth2 cơ bản.

### 4.2. Access token còn hạn vẫn có thể bị thu hồi

Resource Server có thể dựa vào introspection, danh sách thu hồi hoặc chính sách riêng. Vì vậy một token có `getExpiresAt()` ở tương lai không bảo đảm nó sẽ được API chấp nhận.

Ngược lại, access token đã hết hạn không tự động có nghĩa refresh token cũng hết hạn. Client cần dùng đúng cơ chế refresh và xử lý lỗi tại Token Endpoint.

## 5. Vì sao refresh token bị thu hồi?

### 5.1. Thu hồi bởi người dùng

Người dùng có thể mở phần “Connected apps” tại IdP và chọn ngắt quyền của ứng dụng. Authorization Server có thể thu hồi refresh token hoặc toàn bộ authorization grant theo chính sách.

Kết quả: ứng dụng vẫn có record `OAuth2AuthorizedClient` trong database, nhưng Token Endpoint **không còn chấp nhận** refresh token đã lưu.

### 5.2. Thu hồi bởi quản trị viên hoặc chính sách bảo mật

Một tổ chức có thể thu hồi session/token khi:

- Người dùng nghỉ việc hoặc bị disable.
- Có dấu hiệu token bị lộ.
- Đổi cấu hình bảo mật, reset credential hoặc thực hiện phản ứng sự cố.
- Client application không còn được phép truy cập tài nguyên.
- Chính sách bắt buộc người dùng cấp lại consent.

Không mặc định rằng một thao tác cụ thể tại IdP sẽ thu hồi **mọi loại** token ở **mọi provider**. Hành vi phụ thuộc kiến trúc issuer, refresh token family, session và API.

### 5.3. Timeout hoặc hết hạn refresh token

Nhiều provider đặt:

- **Absolute lifetime:** sau một mốc thời gian nhất định token không còn dùng được.
- **Idle lifetime:** token mất hiệu lực nếu không được dùng trong một khoảng thời gian.
- **Session-bound lifetime:** token phụ thuộc tuổi hoặc trạng thái OP session theo chính sách.
- **Policy-driven lifetime:** khác nhau theo Client, user, loại grant hoặc mức rủi ro.

Ngay cả ứng dụng hoạt động bình thường cũng có thể phải yêu cầu người dùng kết nối lại khi một trong các giới hạn đến hạn.

### 5.4. Rotation khiến token cũ không còn hợp lệ

Refresh token rotation là cơ chế cấp **refresh token mới** khi dùng token cũ; Authorization Server có thể vô hiệu hóa token cũ, và nếu thấy token cũ bị sử dụng lại, có thể coi là dấu hiệu đánh cắp.

```text
T0: Client giữ RT-1
T1: Client gửi RT-1 với grant_type=refresh_token
T2: AS trả AT-2 và RT-2
T3: Client lưu RT-2, không tiếp tục dùng RT-1
T4: Client gửi lại RT-1 -> invalid_grant / phát hiện reuse
```

Theo RFC 6749, nếu Server phát hành refresh token mới, Client **phải bỏ token cũ và thay bằng token mới**. Không lưu token mới chỉ trong một biến cục bộ rồi để database tiếp tục chứa token cũ.

## 6. Refresh token rotation và race condition

Đây là một nguyên nhân phổ biến của `invalid_grant` trong hệ thống nhiều request, nhiều worker hoặc nhiều instance.

### 6.1. Hai request cùng dùng một refresh token

```mermaid
sequenceDiagram
    autonumber
    participant A as Request/Pod A
    participant B as Request/Pod B
    participant DB as Authorized Client Store
    participant AS as Authorization Server

    A->>DB: Đọc authorized client với RT-1
    B->>DB: Đọc authorized client với RT-1
    A->>AS: POST refresh_token=RT-1
    AS-->>A: AT-2 và RT-2
    A->>DB: Lưu AT-2, RT-2
    B->>AS: POST refresh_token=RT-1
    AS-->>B: 400 invalid_grant
    Note over B,AS: RT-1 đã dùng hoặc bị vô hiệu hóa
```

Tình huống còn nghiêm trọng hơn nếu provider coi **reuse** là dấu hiệu token bị đánh cắp và thu hồi cả **token family**, bao gồm RT-2 vừa cấp. Khi đó request A tưởng thành công nhưng lần refresh tiếp theo vẫn thất bại.

### 6.2. Không chỉ là vấn đề của scheduler

Race có thể xảy ra khi:

- Hai HTTP requests cùng gọi API bằng access token sắp hết hạn.
- Hai pod dùng một `OAuth2AuthorizedClientService` chung.
- Một web request và một background job cùng làm mới token của user.
- Một worker retry refresh sau timeout dù request trước có thể đã hoàn tất tại AS.
- Database bị ghi đè bởi cache/transaction đến muộn chứa refresh token cũ.
- Nhiều thiết bị chia sẻ cùng refresh token không đúng mô hình Client.

### 6.3. Cách giảm rủi ro

Tùy hệ thống, có thể dùng:

1. **Single-flight refresh** theo khóa `(clientRegistrationId, principalName)` trong một process.
2. **Distributed lock** hoặc coordination khi nhiều instance dùng chung refresh token.
3. **Optimistic locking/compare-and-swap** trong kho lưu để tránh dữ liệu mới bị bản cũ ghi đè.
4. **Cập nhật access token và refresh token cùng một transaction** khi persistence cho phép.
5. **Reload authorized client từ storage** trước khi kết luận kết nối không còn hợp lệ sau một lỗi có thể do race.
6. **Idempotent job design** để việc thử lại thao tác nghiệp vụ không tạo side effect trùng.
7. **Rate limiting/backoff có giới hạn** cho lỗi tạm thời; không retry vô hạn `invalid_grant`.

`JdbcOAuth2AuthorizedClientService` cho phép lưu chung token nhưng **không tự đảm bảo** chỉ có một instance gửi refresh request. Nếu provider bật rotation nghiêm ngặt, cần thiết kế thêm cơ chế đồng bộ.

### 6.4. Cẩn thận khi retry sau timeout

Giả sử Client gửi refresh RT-1, Authorization Server xử lý thành công và cấp RT-2, nhưng response bị mất vì timeout. Client vẫn chỉ biết RT-1.

Nếu Client retry RT-1 ngay:

- Provider có thể từ chối vì RT-1 đã được dùng.
- Provider có thể thu hồi token family theo chính sách reuse detection.

Vì vậy retry refresh token là thao tác cần đánh giá kỹ theo đặc tính provider. Không xem refresh grant như một HTTP GET idempotent. Nếu không thể khôi phục trạng thái token mới một cách an toàn, có thể phải yêu cầu người dùng cấp quyền lại.

## 7. `invalid_grant` trong Spring Security được phát hiện ở đâu?

Spring Security OAuth2 Client có các thành phần:

| Thành phần | Vai trò |
|---|---|
| `OAuth2AuthorizedClientManager` | Điều phối việc cấp/tái cấp authorized client |
| `OAuth2AuthorizedClientProvider` | Thực hiện grant, gồm `refresh_token` |
| `OAuth2AuthorizedClientService` | Lưu/tra/xóa authorized client ngoài Servlet request |
| `OAuth2AuthorizedClientRepository` | Lưu/tra authorized client trong ngữ cảnh Servlet request |
| `DefaultOAuth2AuthorizedClientManager` | Manager cho web/Servlet request |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Manager cho service tier, scheduler, worker |
| `OAuth2AuthorizationFailureHandler` | Xử lý thất bại authorization theo chính sách |
| `OAuth2AuthorizationSuccessHandler` | Xử lý thành công, thường cập nhật authorized client |
| `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` | Thành phần loại bỏ authorized client theo lỗi được xác định |

Khi token refresh bị từ chối, Spring có thể ném `OAuth2AuthorizationException` với một `OAuth2Error` chứa mã lỗi:

```java
try {
    OAuth2AuthorizedClient client = manager.authorize(request);
    // Sử dụng authorized client nếu có, kiểm tra null khi cần.
} catch (OAuth2AuthorizationException ex) {
    String errorCode = ex.getError().getErrorCode();

    if ("invalid_grant".equals(errorCode)) {
        // Refresh grant không còn hợp lệ hoặc grant bị từ chối.
    }
}
```

Ví dụ là một đoạn xử lý khái niệm; `manager` và `request` phải được khởi tạo qua cấu hình thích hợp. Tránh log nguyên exception nếu stack trace hoặc request logging đi kèm có thể chứa credential nhạy cảm.

### 7.1. Hành vi mặc định của `DefaultOAuth2AuthorizedClientManager`

Theo Javadoc Spring Security, khi authorization thất bại do `invalid_grant`, manager cho Servlet request **mặc định loại bỏ authorized client đã lưu** khỏi `OAuth2AuthorizedClientRepository`.

Đây là phản ứng hợp lý: không nên tiếp tục đưa refresh token được biết là đã bị từ chối vào các lần gọi tiếp theo.

Hành vi này có thể thay đổi nếu ứng dụng tự cấu hình `setAuthorizationFailureHandler(...)`. Khi đó bạn **phải bảo đảm** custom handler không vô tình bỏ thao tác cleanup cần thiết.

### 7.2. Hành vi mặc định của `AuthorizedClientServiceOAuth2AuthorizedClientManager`

Với service-tier manager dành cho scheduled job hoặc worker, mặc định khi `invalid_grant` xuất hiện, authorized client trước đó được **loại bỏ khỏi `OAuth2AuthorizedClientService`**.

Nếu một job user-delegated phụ thuộc kết nối này, việc xóa authorized client là một bước kỹ thuật; ứng dụng còn cần **đánh dấu kết nối nghiệp vụ là cần cấp quyền lại** và hướng người dùng thực hiện flow tương tác khi họ trở lại.

### 7.3. Không nên tự xóa toàn bộ session vì refresh thất bại

Khi refresh token bị từ chối, có ít nhất hai kiểu trạng thái:

```text
Spring Security login session:
  User đã đăng nhập vào website của bạn.

External API connection:
  User đã cấp quyền truy cập API của nhà cung cấp.
  Kết nối này có thể bị RECONNECT_REQUIRED.
```

Nếu ứng dụng là portal có backend session, thất bại khi refresh token cho Calendar API không nhất thiết phải logout người dùng khỏi toàn bộ website. Mục tiêu đúng thường là ngắt quyền sử dụng **kết nối Calendar** và yêu cầu người dùng cấp quyền lại cho kết nối ấy.

Ngược lại, nếu sản phẩm yêu cầu phiên ứng dụng chỉ hợp lệ khi token OIDC provider còn sử dụng được, có thể chọn chính sách buộc xác thực lại. Đây là quyết định bảo mật/sản phẩm cần được mô tả rõ, không phải mặc định của mọi OAuth2 Client.

## 8. Cấu hình manager có Refresh Token Provider

### 8.1. Cấu hình cho Servlet HTTP request

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class WebOAuth2ClientConfiguration {

    @Bean("webAuthorizedClientManager")
    OAuth2AuthorizedClientManager webAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Ở đây:

- `.authorizationCode()` hỗ trợ flow browser ở ngữ cảnh phù hợp.
- `.refreshToken()` cho manager khả năng làm mới access token nếu đã có refresh token.
- Repository lưu authorized client trong ngữ cảnh web theo thiết kế của ứng dụng.
- Mặc định manager xử lý `invalid_grant` và loại bỏ authorized client lỗi khỏi repository, nếu không bị custom handler thay thế.

**Không** kết luận rằng mọi OIDC Login chắc chắn có refresh token chỉ vì provider builder chứa `refreshToken()`.

### 8.2. Cấu hình cho tác vụ ngoài HTTP request

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class BackgroundOAuth2ClientConfiguration {

    @Bean("offlineAuthorizedClientManager")
    OAuth2AuthorizedClientManager offlineAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Ví dụ dùng `refreshToken()` vì tác vụ nền giả định **đã có authorized client của user**, được cấp qua flow tương tác và lưu đúng service/principal. Không có authorized client hoặc refresh token, background manager không thể tự hiển thị consent screen và xin authorization code mới.

Một service-to-service job dùng `client_credentials` có thể cấu hình thêm `.clientCredentials()`, nhưng đó là **flow khác**, không phải cách sửa lỗi refresh token của user.

### 8.3. Lưu ý dùng chung storage

Nếu web login dùng `OAuth2AuthorizedClientRepository` nhưng background worker tra `OAuth2AuthorizedClientService` khác, worker có thể không thấy authorized client đã cấp cho user.

Muốn job tiếp tục dùng quyền user, cần thiết kế nhất quán:

- `registrationId` phải đúng.
- `principalName` phải đúng user đã cấp quyền.
- Authorized client phải được lưu trong storage mà background manager truy cập được.
- Refresh token phải thực sự được cấp bởi provider và còn hợp lệ.
- Người dùng phải đồng ý quyền offline/long-lived theo chính sách provider.
- App kiểm tra user/tenant ownership trước khi cho một worker đọc token.

**Đừng sao chép refresh token thủ công sang bảng nghiệp vụ chưa bảo vệ** chỉ để tác vụ nền thấy được credential.

## 9. Phát hiện lỗi refresh trong service nghiệp vụ

Một service nên phân loại token lỗi và trả về **trạng thái nghiệp vụ ổn định**, thay vì để lỗi OAuth2 thô xuất hiện trên UI.

Giả sử ứng dụng có hệ thống kết nối Calendar API. Một record đã được xác minh lưu:

```text
internal_account_id = account-42
client_registration_id = calendar
authorized_client_principal_name = user-oidc-782
connection_status = CONNECTED
```

Một worker nền có thể sử dụng đúng authorized client của người dùng:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.stereotype.Service;

@Service
public class CalendarAuthorizationService {

    private final OAuth2AuthorizedClientManager manager;
    private final ConnectionStatusService statusService;

    public CalendarAuthorizationService(
            @Qualifier("offlineAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager,
            ConnectionStatusService statusService) {

        this.manager = manager;
        this.statusService = statusService;
    }

    public OAuth2AuthorizedClient requireAuthorizedClient(
            TrustedCalendarConnection connection) {

        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
            .withClientRegistrationId(connection.registrationId())
            .principal(connection.authorizedClientPrincipalName())
            .build();

        try {
            OAuth2AuthorizedClient client = manager.authorize(request);

            if (client == null) {
                statusService.requireReconnect(connection.id());
                throw new ReconnectRequiredException();
            }

            // Provider có thể không hỗ trợ refresh và trả token hiện tại.
            // Chỉ dùng access token nếu còn phù hợp với tác vụ/API.
            if (client.getAccessToken().getExpiresAt() != null
                    && !java.time.Instant.now()
                        .isBefore(client.getAccessToken().getExpiresAt())) {

                statusService.requireReconnect(connection.id());
                throw new ReconnectRequiredException();
            }

            return client;
        } catch (OAuth2AuthorizationException ex) {
            String code = ex.getError().getErrorCode();

            if ("invalid_grant".equals(code)) {
                // Default failure handler của manager thường đã
                // xóa authorized client lỗi khỏi service.
                statusService.requireReconnect(connection.id());
                throw new ReconnectRequiredException();
            }

            // Không biến mọi lỗi mạng/cấu hình thành yêu cầu reconnect.
            throw ex;
        }
    }

    public interface ConnectionStatusService {
        void requireReconnect(String trustedConnectionId);
    }

    public record TrustedCalendarConnection(
            String id,
            String registrationId,
            String authorizedClientPrincipalName) {}

    public static final class ReconnectRequiredException
            extends RuntimeException {}
}
```

Đây là **mẫu cấu trúc ứng dụng**, không phải một module có thể chạy ngay: repository của `TrustedCalendarConnection`, security checks, lưu trạng thái và HTTP client cần triển khai riêng.

Điểm cần nhớ:

1. `connection` phải đến từ record **đã được xác minh ownership** của user/account hoặc job, không từ tham số tùy ý trong queue.
2. Không in exception kèm token request/response.
3. `invalid_grant` do manager ném được phân loại là kết nối cần reauthorization.
4. Lỗi tạm thời `5xx`/timeout không nhất thiết yêu cầu người dùng reconnect ngay.
5. Với refresh token rotation, cần chiến lược chống race; ví dụ trên không tự triển khai distributed lock.
6. Khi không có authorized client, manager không tự tạo user consent; ứng dụng phải bắt đầu flow tương tác sau đó.

### 9.1. Vì sao vẫn phải kiểm tra access token đã hết hạn?

Với `refreshToken()` provider, nếu không có refresh token khả dụng, manager có thể không thực hiện reauthorization; tùy context nó có thể trả lại authorized client cũ. Nếu caller thấy client khác `null` rồi lập tức gọi API bằng token đã hết hạn, kết quả có thể là 401.

Để minh họa failure state, ví dụ trên kiểm tra `expiresAt` khi cần. Trong hệ thống production, nên để provider/HTTP integration xử lý clock skew và token lifecycle đúng version; tránh tự xây bộ refresh song song chỉ dựa vào `Instant.now()`.

### 9.2. Không lộ token qua response API

API phản hồi frontend có thể chỉ cần:

```json
{
  "connection": "calendar",
  "status": "RECONNECT_REQUIRED",
  "action": "REAUTHORIZE"
}
```

Không trả:

```json
{
  "refresh_token": "EXAMPLE_SECRET",
  "access_token": "EXAMPLE_SECRET",
  "oauth2_error_description": "RAW_PROVIDER_RESPONSE"
}
```

Thông tin lỗi của provider có thể chứa dữ liệu nhạy cảm hoặc cấu trúc không dành cho người dùng cuối. Chỉ công bố mã nghiệp vụ đủ để UI hiển thị bước tiếp theo.

## 10. Dọn authorized client lỗi và giữ thông tin nghiệp vụ

Khi refresh `invalid_grant`, nên phân biệt:

- **Authorized client credential state:** chứa access token, refresh token và metadata; có thể phải xóa để tránh reuse.
- **Business connection state:** record rằng user đã kết nối provider nào, ngày kết nối, quyền dự kiến và có cần reauthorize không; có thể giữ để hướng UI.
- **Internal account:** dữ liệu người dùng nội bộ; không được xóa chỉ vì refresh token thất bại.

Ví dụ trạng thái:

```text
CONNECTED
  -> access token gần hết hạn -> REFRESHING
  -> refresh thành công       -> CONNECTED
  -> invalid_grant            -> RECONNECT_REQUIRED
  -> user reauthorizes        -> CONNECTED
  -> user disconnects         -> DISCONNECTED
```

```mermaid
stateDiagram-v2
    [*] --> CONNECTED: User hoàn tất OAuth2/OIDC consent
    CONNECTED --> REFRESHING: Access token cần refresh
    REFRESHING --> CONNECTED: Token mới hợp lệ
    REFRESHING --> RECONNECT_REQUIRED: invalid_grant
    CONNECTED --> RECONNECT_REQUIRED: Provider revoked / policy requires new consent
    RECONNECT_REQUIRED --> AUTHORIZING: User bắt đầu flow tương tác
    AUTHORIZING --> CONNECTED: Callback hợp lệ, lưu token mới
    AUTHORIZING --> RECONNECT_REQUIRED: User hủy / callback thất bại
    CONNECTED --> DISCONNECTED: User chủ động ngắt kết nối
    RECONNECT_REQUIRED --> DISCONNECTED: User chủ động ngắt kết nối
```

### 10.1. Khi xóa authorized client cần lưu ý gì?

`OAuth2AuthorizedClientService` cho phép xóa theo `registrationId` và `principalName`:

```java
authorizedClientService.removeAuthorizedClient(
    "calendar",
    trustedUserPrincipalName
);
```

**Chỉ xóa đúng authorized client lỗi.** Không gọi một hàm “clear toàn bộ OAuth2 clients” nếu chỉ một Calendar connection bị thu hồi.

Nếu manager đang dùng failure handler mặc định, lỗi `invalid_grant` đã kích hoạt cleanup theo cơ chế quản lý. Không nên tạo một bước manual remove thứ hai không cần thiết, nhất là khi có race và một worker khác vừa lưu refresh token mới. Với hệ thống concurrent, thao tác delete nên được điều phối và cân nhắc version của record.

### 10.2. Không đổi principal name để “né” invalid_grant

Một cách xử lý sai:

```java
// SAI: tạo principal mới để tránh record refresh token bị từ chối.
.principal("user-782-" + java.util.UUID.randomUUID())
```

Đổi principal chỉ làm manager tra một khóa khác trong storage. Nó **không tự cấp lại quyền người dùng** và có thể làm phát sinh nhiều record sai hoặc dùng nhầm access token theo Client khác.

### 10.3. Không chuyển sang Client Credentials khi bị từ chối refresh của user

Nếu user đã cấp `calendar.read` theo authorization code và refresh bị từ chối, không tự chuyển sang token `client_credentials` để tiếp tục đọc lịch cá nhân. Quyền ứng dụng và quyền người dùng có trust boundary khác nhau. Nếu API hỗ trợ service-level access, đó phải là một thiết kế/ủy quyền riêng.

## 11. Yêu cầu đăng nhập lại hay cấp quyền lại?

Cụm “đăng nhập lại” trong UX OAuth2 có thể chỉ ít nhất ba hành động:

| Hành động | Mục tiêu | Khi nào phù hợp |
|---|---|---|
| **Re-login vào ứng dụng** | Thiết lập lại `SecurityContext`/session của portal | Session người dùng đã hết hạn hoặc policy yêu cầu |
| **Reauthorize external connection** | Cấp lại access/refresh token cho Client ở provider | Refresh token của kết nối bị thu hồi/hết hạn |
| **Reauthenticate tại IdP** | Yêu cầu người dùng xác thực lại tại nhà cung cấp | Tác vụ nhạy cảm hoặc provider policy yêu cầu phiên mới |

Ba việc này **không hoàn toàn tương đương**.

Ví dụ người dùng đang ở trang dashboard của ứng dụng Spring, session local còn hoạt động nhưng kết nối Microsoft Calendar báo `RECONNECT_REQUIRED`. Hành vi hợp lý thường là hiển thị nút **“Kết nối lại tài khoản Microsoft”**, không logout toàn bộ portal.

### 11.1. OIDC session của provider có thể còn hoạt động

Khi người dùng được đưa tới Authorization Endpoint lần nữa, IdP có thể đã có session SSO và cấp authorization code mới **mà không hiển thị màn hình nhập mật khẩu**. Đó vẫn là một flow reauthorization mới với `state`/PKCE và callback.

Nếu yêu cầu sản phẩm là người dùng phải **thực sự xác thực lại**, có thể dùng những tham số OIDC như `prompt=login` hoặc `max_age` theo hỗ trợ của provider và kiểm tra `auth_time` khi cần. Không mặc định mọi IdP tuân thủ các hint tùy chọn y hệt nhau.

### 11.2. `offline_access` không đảm bảo có refresh token vĩnh viễn

Một số OIDC Provider dùng scope `offline_access` và điều kiện consent để cấp refresh token. Tuy nhiên:

- Không phải mọi provider đều chấp nhận `offline_access`.
- Có thể cần cấu hình Client hoặc prompt/consent riêng.
- Provider có thể áp dụng idle timeout/absolute lifetime.
- Người dùng hoặc quản trị viên có thể revoke bất cứ lúc nào.
- Rotation/reuse detection vẫn áp dụng.
- Refresh token không được xem là quyền vĩnh viễn sau khi người dùng rời tổ chức.

Do đó hệ thống **phải luôn có đường thoát RECONNECT_REQUIRED**, kể cả khi `offline_access` đã được cấp.

## 12. Thiết kế UX reauthorization an toàn

Một trang kết nối có thể hiển thị:

```text
Kết nối Calendar cần được xác nhận lại.

Quyền truy cập trước đây đã hết hiệu lực hoặc bị thu hồi.
Các dữ liệu đã đồng bộ trong ứng dụng vẫn được giữ theo chính sách.
[ Kết nối lại ]
```

Nút “Kết nối lại” khởi động **một authorization flow mới từ backend**, không dùng lại refresh token hỏng.

Ví dụ link initiation mặc định của Spring Security:

```html
<a href="/oauth2/authorization/calendar">
    Kết nối lại Calendar
</a>
```

Đường dẫn `/oauth2/authorization/calendar` chỉ minh họa registration ID `calendar`. Trong sản phẩm có nhiều provider, UI cần dùng danh sách registration IDs do server cho phép, không xây URL từ issuer bất kỳ do user gửi.

### 12.1. Flow đầy đủ của nút “Kết nối lại”

1. User đã xác thực trong ứng dụng và có quyền quản lý kết nối tương ứng.
2. Backend kiểm tra record đang `RECONNECT_REQUIRED` hoặc cho phép cấp lại theo policy.
3. Với kết nối external account hiện có, backend tạo **pending-reauthorization context** ngắn hạn ràng buộc account/connection/session.
4. Spring bắt đầu authorization request mới, sinh `state`, PKCE/nonce khi áp dụng.
5. Trình duyệt tới Authorization Endpoint; người dùng xác thực/consent theo yêu cầu.
6. Provider trả code về callback; Spring xử lý và xác minh code, state, ID Token (nếu OIDC).
7. Backend kiểm tra external identity mới có đúng **account connection** mà user đang cấp lại hay không.
8. Authorized client mới được lưu, refresh token mới được quản lý đúng.
9. Pending context hết hiệu lực; connection chuyển lại `CONNECTED`.
10. Tác vụ nền có thể được tiếp tục theo policy và quyền mới.

**Không tự thay `state` bằng accountId/return URL nhạy cảm**, hoặc nhận một external identity khác rồi gán vào kết nối cũ chỉ vì email trùng. Với OIDC, dùng cặp `(iss, sub)` đã xác minh; với OAuth2 không OIDC, dùng ID ổn định được provider công bố theo hợp đồng.

### 12.2. Xử lý người dùng đăng nhập IdP bằng tài khoản khác

Một lỗi nguy hiểm: người dùng bấm kết nối lại cho `connection_id=42` thuộc tài khoản Alice, nhưng tại IdP họ chọn Bob. Nếu backend ghi token Bob vào record của Alice mà không kiểm tra, có thể gây rò dữ liệu hoặc trộn danh tính.

Trước khi thay authorized client, cần xác định:

- Có cho phép đổi external account gắn với kết nối này không?
- Nếu không, subject/provider user ID mới có khớp danh tính cũ không?
- Nếu có thay account, người dùng có được thông báo và xác nhận rõ không?
- Token mới có đúng tenant, scope, audience và ClientRegistration không?
- Pending-reauthorization context có thuộc đúng internal account đang đăng nhập không?

**Không dùng email làm bằng chứng duy nhất** để quyết định hai external identities là một người.

### 12.3. Tránh open redirect

Không nhận trực tiếp:

```text
/login?returnTo=https://evil.example.test
```

rồi redirect người dùng tới URL này sau khi hoàn tất OAuth2. Nên dùng saved request của Spring hoặc mapping các route nội bộ theo allowlist. Nếu ứng dụng phải dùng external frontend URL, chỉ sử dụng URL từ cấu hình server tin cậy.

## 13. Tránh vòng lặp đăng nhập vô hạn

Một failure mode thường gặp:

```text
GET /dashboard
  -> Client gọi API, refresh token invalid_grant
  -> redirect /oauth2/authorization/company
  -> login/callback thành công
  -> redirect /dashboard
  -> Client lại dùng authorized client lỗi/không được lưu
  -> redirect /oauth2/authorization/company
  -> ...
```

### 13.1. Nguyên nhân

- Refresh token cũ chưa được xóa hoặc cache chưa cập nhật.
- Sau callback authorized client mới không được lưu đúng repository/service.
- Principal name khi lưu token khác principal name khi đọc.
- User chưa consent scope/offline access nên không có refresh token.
- Connection policy vẫn đánh dấu `RECONNECT_REQUIRED` dù callback thành công.
- Callback cấp token cho registration/tenant khác.
- Ứng dụng tự chuyển hướng vào authorization flow **ngay trong mọi request API** và không có điểm dừng.
- Một error handler nhầm HTTP 403 là “cần đăng nhập lại”.

### 13.2. Cách phòng tránh

1. Giữ trạng thái reauthorization riêng, có TTL và giới hạn số lần thử.
2. Nếu refresh lỗi, **trả trạng thái nghiệp vụ** thay vì redirect tự động trong mọi request nền/API.
3. Chỉ bắt đầu flow tương tác khi người dùng click nút hoặc theo quy tắc có kiểm soát.
4. Sau callback, xác nhận authorized client mới tồn tại dưới đúng registration/principal và đủ quyền.
5. Nếu scope không được cấp, hiển thị lỗi rõ thay vì quay lại vòng login.
6. Nếu provider từ chối consent, không retry liên tục.
7. Dùng correlation ID và trạng thái flow để debug nhưng không log `state`/token thô.

Với SPA gọi API JSON, thường nên trả HTTP status và một mã như `RECONNECT_REQUIRED` để frontend hiển thị nút. Không tự động biến mọi fetch thất bại thành redirect tới trang IdP rồi nhận HTML trong XHR.

## 14. Spring HTTP client: lỗi 401/403 từ Resource Server

Một vấn đề tinh tế: manager xử lý lỗi **lúc xin token**, nhưng API có thể báo lỗi **sau khi token đã được dùng**.

### 14.1. Dùng `RestClient` và `OAuth2ClientHttpRequestInterceptor`

Trong các phiên bản Spring Security hỗ trợ, `OAuth2ClientHttpRequestInterceptor` tích hợp `OAuth2AuthorizedClientManager` và có khả năng chuyển lỗi 401/403 từ Resource Server tới `OAuth2AuthorizationFailureHandler`.

Có thể cấu hình một failure handler theo `OAuth2AuthorizedClientService`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Bean
RestClient apiRestClient(
        OAuth2AuthorizedClientManager authorizedClientManager,
        OAuth2AuthorizedClientService authorizedClientService) {

    var interceptor =
        new OAuth2ClientHttpRequestInterceptor(authorizedClientManager);

    interceptor.setAuthorizationFailureHandler(
        OAuth2ClientHttpRequestInterceptor.authorizationFailureHandler(
            authorizedClientService
        )
    );

    return RestClient.builder()
        .requestInterceptor(interceptor)
        .build();
}
```

Đây là **ví dụ về API failure handling**, không phải cấu hình đầy đủ để xác định registration/principal cho mọi request. Với background job, phải cấu hình resolvers hoặc request attributes phù hợp với phiên bản và service manager dùng; không để interceptor phụ thuộc vào principal của một web request ngẫu nhiên.

### 14.2. Handler có xóa trên mọi 401/403 không?

Không nên diễn giải rằng cứ HTTP 401/403 là toàn bộ authorized client đều bị xóa. `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` căn cứ vào OAuth2 error code được chuyển tới; hành vi chính xác phụ thuộc integration và phiên bản.

Ví dụ Resource Server trả `invalid_token` có thể khiến client không nên dùng lại access token cũ. Với `insufficient_scope`, vấn đề thường là quyền; việc xóa mọi refresh token có thể làm mất một kết nối user hợp lệ mà không giải quyết được thiếu scope.

Với user-delegated refresh token, hãy đặc biệt thận trọng khi cấu hình auto-remove sau API 401: **xóa cả authorized client có thể làm mất refresh token vẫn còn hợp lệ**. Cần xác định chiến lược chính xác theo loại lỗi, version, consent và workflow reauthorization của sản phẩm.

### 14.3. `WebClient` cũng có cơ chế failure handler

Khi dùng `ServletOAuth2AuthorizedClientExchangeFilterFunction`, Spring Security có thể chuyển lỗi 401/403 tới authorization failure handler. Nhưng constructor dùng manager và constructor dùng repository có thể có **default failure handling khác nhau** ở các phiên bản.

Không khẳng định mọi WebClient tự xóa authorized client chỉ vì nhận 401. Cần xem cách cấu hình thực tế, nếu cần thì cung cấp `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` phù hợp.

### 14.4. Tự set Bearer header thì sao?

Nếu code tự lấy token từ manager rồi gọi API:

```java
restClient.get()
    .uri("/api/events")
    .headers(h -> h.setBearerAuth(accessToken))
    .retrieve()
    .body(String.class);
```

thì lỗi API không tự đi qua `OAuth2AuthorizedClientManager` như lỗi refresh token. Bạn cần xử lý response/exception tại tầng HTTP client và quyết định có invalidate token, retry một lần hay dừng kết nối, tùy nguyên nhân.

**Không retry vô hạn** trên 401/403; không gửi token sang URL ngoài allowlist, kể cả khi HTTP client tự follow redirect.

## 15. Quy tắc retry và backoff theo loại lỗi

Không phải lỗi nào cũng phù hợp để retry.

| Loại lỗi | Retry tự động? | Lý do |
|---|---|---|
| `invalid_grant` khi refresh | **Không** retry cùng token không kiểm soát | Token có thể đã bị revoke/rotated; reuse detection |
| `invalid_client` | Không cho tới khi sửa cấu hình | Client credentials sai/không được chấp nhận |
| `invalid_scope` | Không trước khi sửa quyền yêu cầu | Lỗi policy/consent |
| HTTP 429 từ Token Endpoint | Có thể, với `Retry-After` và giới hạn | Rate limit, tránh dồn tải |
| HTTP 5xx tạm thời | Có thể, có backoff và giới hạn | Lỗi server; với refresh rotation phải cân nhắc request trước có thể đã thành công |
| Network timeout khi refresh | **Rất thận trọng** | Không biết token cũ đã bị tiêu thụ hay chưa |
| API 401 `invalid_token` | Có thể reacquire/retry giới hạn theo policy | Không chắc lỗi refresh; cần chẩn đoán |
| API 403 `insufficient_scope` | Không retry cùng scope | Quyền không đủ |
| Browser authorization bị người dùng hủy | Không tự lặp vô hạn | Cần tôn trọng quyết định người dùng |

### 15.1. Exponential backoff không giải quyết token đã bị revoke

Backoff hữu ích với lỗi mạng/tải, nhưng nếu refresh token đã bị thu hồi, chờ 1, 2, 4, 8 phút rồi gửi lại **cùng refresh token** vẫn không biến token thành hợp lệ.

Hệ thống nên chuyển sang `RECONNECT_REQUIRED`, ngừng scheduled sync liên quan và thông báo khi người dùng có thể xử lý, tránh gửi hàng nghìn request refresh thất bại.

### 15.2. Idempotency của tác vụ nghiệp vụ khác với retry token

Ví dụ job gửi hóa đơn gọi API sau khi lấy token mới. Nếu API timeout, việc gọi lại có thể tạo hóa đơn trùng. Đây là vấn đề nghiệp vụ riêng cần idempotency key hoặc logic kiểm soát giao dịch. Không nên coi việc giải quyết refresh token là đủ để mọi retry downstream trở nên an toàn.

## 16. Revoke token có chủ đích theo RFC 7009

Ngoài trường hợp token bị thu hồi bên ngoài, ứng dụng đôi khi chủ động ngắt kết nối hoặc thu hồi token khi người dùng chọn “Disconnect”.

**RFC 7009 — Token Revocation** định nghĩa endpoint cho Client gửi token để yêu cầu thu hồi. Ví dụ form request đã đơn giản hóa:

```http
POST /oauth2/revoke HTTP/1.1
Host: login.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH
Content-Type: application/x-www-form-urlencoded

token=EXAMPLE_REFRESH_TOKEN&token_type_hint=refresh_token
```

Nhà cung cấp có thể yêu cầu Client authentication và endpoint/cú pháp riêng phù hợp tiêu chuẩn.

### 16.1. Revocation response không phải bằng chứng token từng hợp lệ

Theo RFC 7009, endpoint có thể trả HTTP 200 ngay cả khi token đã không hợp lệ; hành vi này giúp tránh lộ trạng thái token qua response.

Khi người dùng chọn ngắt kết nối, nên:

1. Xác minh user có quyền quản lý kết nối.
2. Nếu provider hỗ trợ revocation, yêu cầu thu hồi credential phù hợp.
3. Xóa authorized client và trạng thái phiên/token lưu phía ứng dụng theo policy.
4. Đánh dấu business connection là `DISCONNECTED`.
5. Ghi audit event không chứa token.
6. Điều phối job/queue để dừng thao tác tiếp tục dùng kết nối đó.

**Logout khỏi HTTP session và revoke refresh token không phải một thao tác giống nhau.** OIDC RP-Initiated Logout cũng là cơ chế khác, liên quan đến phiên ở OP.

### 16.2. Thu hồi refresh token có thể ảnh hưởng access token khác nhau

Một số provider thu hồi cả grant/token family, một số có hành vi cụ thể cho access token. Không giả định mọi access token đã cấp đều lập tức không dùng được khi một refresh token bị revoke; điều đó tùy token format, Resource Server validation và chính sách provider.

Nếu hệ thống yêu cầu chặn truy cập tức thời, phải thiết kế từ phía Authorization Server/Resource Server (revocation/introspection/session control) chứ không chỉ xóa record ở Spring Client.

## 17. Quản lý trạng thái trên nhiều instance

Một hệ thống production thường có nhiều pod:

```text
Pod A: HTTP callback / user session
Pod B: Scheduled Sync Job
Pod C: Queue Consumer
Shared Database: authorized clients + connection state
Authorization Server: refresh token rotation
```

Những tình huống cần giải quyết:

- Pod A vừa lưu refresh token mới, Pod B còn giữ cache cũ.
- Pod B refresh lỗi vì rotation, nhưng Pod C đã thành công trước đó.
- Pod A user ngắt kết nối, Pod B vẫn đang xử lý message cũ.
- Hai worker cùng tự động chuyển business state sang `RECONNECT_REQUIRED`, làm mất trạng thái thành công của worker khác.
- Backup/restore khôi phục refresh token đã dùng rồi gây reuse detection.

### 17.1. Lưu token bền vững và cập nhật nguyên tử

`InMemoryOAuth2AuthorizedClientService` không chia sẻ token giữa các instance và mất khi restart. `JdbcOAuth2AuthorizedClientService` cho phép lưu bền vững nhưng **không tự giải quyết mọi race**.

Với refresh token rotation nghiêm ngặt, có thể thiết kế:

```text
Lock key: registrationId + principalName
    -> re-read latest authorized client
    -> nếu token vẫn cần refresh, gọi AS một lần
    -> ghi access + refresh token mới an toàn
    -> release lock
```

Nếu không sử dụng lock, cần optimistic locking có version để tránh cập nhật stale state. Mô hình lựa chọn phụ thuộc provider và tần suất tác vụ. Không sử dụng một lock global cho mọi user nếu điều đó tạo bottleneck không cần thiết.

### 17.2. Khi nhận `invalid_grant` do race, có nên mark reconnect ngay?

Trong hệ thống có concurrency, một worker có thể nhận `invalid_grant` vì token cũ đã được worker khác dùng hợp lệ. Tuy nhiên, provider có thể thu hồi cả token family sau reuse; không thể an toàn giả định token mới chắc chắn còn hợp lệ.

Một chiến lược là:

1. Ghi nhận sự kiện refresh conflict, không log token.
2. Kiểm tra version và trạng thái authorized client mới nhất từ kho đáng tin.
3. Nếu thấy token đã được một worker khác cập nhật, đánh giá chính sách provider và khả năng token family còn hợp lệ.
4. Không xóa bản token mới theo thao tác cleanup đến muộn.
5. Nếu không chắc, chuyển trạng thái sang cần reauthorization và thông báo thay vì retry vô hạn.
6. Phòng ngừa lần sau bằng coordination.

**Điểm quan trọng:** cleanup mặc định của Spring manager là hữu ích nhưng không thay thế thiết kế concurrency toàn cluster. Nếu override handler để thêm version-aware cleanup, cần thực hiện đúng hợp đồng của thư viện và không vô tình bỏ các kiểm tra cần thiết.

### 17.3. Multi-tenant và per-user isolation

Một `OAuth2AuthorizedClientService` thường tra token theo `(clientRegistrationId, principalName)`. Vì vậy:

- Không dùng một principal name chung cho nhiều người dùng khác nhau.
- Không cho message từ tenant A chỉ định principal của tenant B.
- Nên liên kết principal tới internal account/connection được xác minh.
- Token cấp cho Resource Server A không tự dùng được cho Resource Server B.
- Khi ngắt một connection, chỉ xóa token theo đúng registration và principal.
- Nếu một provider hỗ trợ nhiều tenants/issuers, phải bảo vệ sự nhất quán issuer/ClientRegistration.

## 18. Khi nào yêu cầu người dùng đăng nhập lại toàn bộ?

Không nên mặc định mọi `invalid_grant` buộc logout toàn bộ ứng dụng. Một số policy có thể yêu cầu:

### 18.1. Ứng dụng phụ thuộc trực tiếp vào OP session

Nếu sản phẩm quy định người dùng chỉ có quyền sử dụng portal khi phiên tại OP vẫn hợp lệ, token revocation có thể kéo theo yêu cầu reauthentication theo chính sách. Tuy nhiên, cần phân biệt việc OP session hết hạn với refresh token bị từ chối — không có quy tắc OAuth2 nói hai việc luôn xảy ra cùng lúc.

### 18.2. Kết nối API bên ngoài chỉ là chức năng phụ

Nếu user đang login vào portal và một Calendar API connection hết hạn, UX thường nên:

- Giữ session portal.
- Tạm dừng tính năng đồng bộ Calendar.
- Hiển thị `RECONNECT_REQUIRED`.
- Mở flow kết nối lại khi user chọn.
- Không xóa dữ liệu nội bộ ngoài phạm vi connection.

### 18.3. Sự kiện bảo mật nghiêm trọng

Khi có bằng chứng token bị đánh cắp hoặc refresh token reuse dẫn đến thu hồi token family, tổ chức có thể chọn:

- Vô hiệu hóa kết nối ngay.
- Thu hồi các credential liên quan.
- Đánh dấu tài khoản cần xác thực lại bằng yếu tố mạnh.
- Cảnh báo người dùng theo policy.
- Kiểm tra audit và dấu hiệu truy cập bất thường.

Đây là response plan cho sự cố bảo mật, cần dựa trên tín hiệu tin cậy chứ không chỉ mọi HTTP 400.

## 19. Thiết kế trạng thái nghiệp vụ cho kết nối OAuth2

Một schema tham khảo:

```sql
CREATE TABLE oauth_connection (
    id UUID PRIMARY KEY,
    internal_account_id UUID NOT NULL,
    registration_id VARCHAR(128) NOT NULL,
    principal_name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL,
    last_success_at TIMESTAMP WITH TIME ZONE,
    reconnect_required_at TIMESTAMP WITH TIME ZONE,
    failure_code VARCHAR(80),
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_oauth_connection_status
      CHECK (status IN (
        'CONNECTED',
        'RECONNECT_REQUIRED',
        'DISCONNECTED'
      ))
);
```

Ý nghĩa:

- `internal_account_id` liên kết tới chủ tài khoản nghiệp vụ đã được xác minh.
- `registration_id` và `principal_name` chỉ tới authorized client đúng kho lưu.
- `status` cho UI/job biết có nên tiếp tục dùng connection không.
- `failure_code` chỉ chứa mã lỗi đã lọc, không phải raw HTTP response.
- `version` hỗ trợ optimistic concurrency nếu ứng dụng triển khai.
- Token thật được lưu trong `OAuth2AuthorizedClientService` hoặc kho riêng bảo mật, không nhét vào cột plaintext của bảng nghiệp vụ.

Một kết nối có thể được hiển thị với metadata nhưng token đã bị xóa khi `RECONNECT_REQUIRED`. Đây là trạng thái hợp lệ.

### 19.1. Audit tối thiểu

Những sự kiện có ích:

```text
CONNECTION_AUTHORIZED
TOKEN_REFRESH_SUCCEEDED
TOKEN_REFRESH_FAILED_INVALID_GRANT
CONNECTION_RECONNECT_REQUIRED
CONNECTION_REAUTHORIZED
CONNECTION_DISCONNECTED
```

Không cần lưu access token/refresh token, authorization code hay raw ID Token trong audit. Với user/tenant identifiers, áp dụng chính sách giới hạn truy cập phù hợp.

## 20. Quy trình chẩn đoán `invalid_grant` theo từng bước

Khi phát hiện lỗi, hãy điều tra **có thứ tự**:

1. **Xác định nơi lỗi:** Token Endpoint hay downstream API?
2. **Xem `grant_type`:** `refresh_token` hay `authorization_code`?
3. **Ghi nhận mã lỗi OAuth2:** `invalid_grant`, `invalid_client`, `invalid_scope`... không log token.
4. **Kiểm tra registration ID và môi trường:** Có nhầm staging/prod/tenant hoặc Client ID không?
5. **Xem thời điểm lần refresh thành công cuối cùng:** Có refresh token rotation không?
6. **Xem concurrency:** Có nhiều pod/request refresh cùng authorized client không?
7. **Kiểm tra storage:** Token mới có được lưu không, có dữ liệu stale trong cache không?
8. **Kiểm tra audit nhà cung cấp nếu được phép:** Revocation, user consent, session timeout, policy change?
9. **Phân biệt lỗi tạm thời với credential invalid:** `invalid_grant` không nên retry cùng token; timeout/5xx cần chính sách riêng.
10. **Xem cleanup mặc định của Spring:** Manager đang dùng service hay repository, custom failure handler có ghi đè không?
11. **Đánh giá trạng thái tài khoản:** Portal session còn hợp lệ? External connection có cần reauthorize?
12. **Chuẩn bị UX reconnect an toàn:** đúng provider, đúng account, đúng permission và bảo vệ account linking.
13. **Quan sát sau kết nối lại:** Authorized client mới có token hợp lệ, scope đủ và job chạy lại đúng không?

### 20.1. Ví dụ log an toàn

```text
event=oauth_refresh_failed
registrationId=calendar
principalCategory=user
grantType=refresh_token
errorCode=invalid_grant
connectionStatus=RECONNECT_REQUIRED
correlationId=8f6e... (mã nội bộ ngẫu nhiên)
```

Không log:

```text
refresh_token
access_token
id_token
Authorization: Basic/Bearer
OAuth2 authorization code
raw token response hoặc error_description chưa được lọc
session cookie
```

Mã lỗi và correlation ID thường đủ để điều tra bằng telemetry mà không phơi lộ credential.

### 20.2. Log ở mức DEBUG có đủ an toàn không?

Ngay cả khi bật `org.springframework.security=DEBUG`, hạ tầng HTTP client/proxy/APM có thể thu token request/response nếu cấu hình logging quá rộng. Phải đánh giá toàn bộ pipeline; không gửi HAR, trace hoặc exception dump có token thật lên hệ thống hỗ trợ không phù hợp.

## 21. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Refresh Token Endpoint trả `invalid_grant` | Token expired/revoked/rotated/wrong Client | Dừng reuse, cleanup state, yêu cầu reauthorization khi cần |
| Refresh thành công một lần, lần sau lập tức lỗi | Token mới chưa được lưu hoặc worker dùng RT cũ | Kiểm tra rotation và persistence |
| Chỉ lỗi khi chạy nhiều pod | Concurrent refresh/reuse detection | Single-flight, lock, optimistic locking |
| Token cũ vẫn được dùng sau refresh | Cache stale hoặc update thất bại | Reload storage, điều phối cập nhật |
| HTTP API trả 401 dù access token còn hạn | Revocation/audience/issuer/API policy | Kiểm tra Resource Server, không tự kết luận refresh invalid |
| API trả 403 `insufficient_scope` | Token thiếu quyền | Xử lý consent/scope, không refresh vô hạn |
| `invalid_client` ở Token Endpoint | Secret hoặc auth method sai | Sửa cấu hình Client |
| `invalid_grant` ở login callback | Authorization code/PKCE/Redirect URI lỗi | Debug OAuth2 Login, không đánh đồng refresh failure |
| User đang login portal nhưng Calendar reconnect | HTTP session và external token lifecycle khác nhau | Giữ session theo policy, reconnect đúng connection |
| Reconnect xong vẫn lỗi | Lưu nhầm principal/registration hoặc thiếu scope | Kiểm tra storage, user identity, granted scopes |
| Vòng lặp redirect login | Không cập nhật state, auto-redirect mọi API call | Giới hạn retry, explicit UI reconnect |
| Không có refresh token | AS không cấp offline access, policy/consent | Kiểm tra registration và phương thức cấp quyền |
| Sau revocation local, API vẫn dùng được token cũ | Client xóa storage không tự chặn Resource Server | Cần AS revocation/resource validation phù hợp |
| Background worker không thể tự reconnect | Flow cần user agent/consent | Đánh dấu RECONNECT_REQUIRED và thông báo user |
| Custom failure handler không xóa token hỏng | Đã thay default cleanup của manager | Bảo toàn behavior cần thiết hoặc cấu hình handler tương ứng |
| API failure handler xóa refresh token còn hợp lệ | Chính sách auto-remove quá rộng | Phân loại 401/403, giữ token lifecycle theo yêu cầu |
| Đổi principalName để né lỗi | Sai mapping authorized client | Dùng principal ổn định, đúng user/tenant |
| Dùng token Client Credentials thay user | Trộn trust boundary | Tách service permission và user consent |

## 22. Bộ tình huống thực hành

### Bài tập 1: Phân biệt lỗi

Client gọi Token Endpoint:

```http
POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_RT
```

Server trả:

```json
{"error":"invalid_grant"}
```

**Câu hỏi:** có thể khẳng định refresh token bị admin thu hồi không?

**Gợi ý đáp án:** không. Có thể expired, revoked, rotated hoặc sai Client. Điều quan trọng trước mắt là không lặp lại bằng token cũ vô hạn, xử lý authorized client lỗi và tìm nguyên nhân nếu cần.

### Bài tập 2: Không được nhầm 401 với `invalid_grant`

Resource Server trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

**Gợi ý đáp án:** đây là lỗi khi dùng access token tại API. Có thể token expired, revoked, sai audience hoặc nguyên nhân khác. Không kết luận refresh token hỏng nếu chưa có token refresh attempt thất bại.

### Bài tập 3: Hai pod cùng refresh

Pod A dùng RT-1 thành công, nhận RT-2. Pod B vừa gửi RT-1 và nhận `invalid_grant`.

**Gợi ý đáp án:** có race condition với rotation. Cần coordination và lưu token mới nhất; kiểm tra policy reuse detection có làm RT-2 bị thu hồi không. Không retry RT-1 liên tục.

### Bài tập 4: Session còn nhưng kết nối lỗi

Người dùng vẫn mở portal bình thường, nhưng Google Calendar connection cần reconnect.

**Gợi ý đáp án:** hiển thị trạng thái `RECONNECT_REQUIRED` cho Calendar. Không tự logout mọi chức năng của portal nếu chính sách không yêu cầu.

### Bài tập 5: Không có refresh token trong response

Token response:

```json
{
  "access_token": "EXAMPLE_AT",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "openid profile"
}
```

**Gợi ý đáp án:** không thể tự dùng refresh grant từ response này. Cần xem provider có cấp refresh token cho flow/consent không; khi access token hết hạn, có thể phải thực hiện authorization flow lại.

### Bài tập 6: Xóa token sau lỗi

`DefaultOAuth2AuthorizedClientManager` được cấu hình custom failure handler chỉ in log; từ đó job refresh gửi lại token cũ liên tục.

**Gợi ý đáp án:** custom handler có thể đã thay hành vi cleanup mặc định khi `invalid_grant`. Cần cấu hình handler thực hiện việc loại bỏ authorized client lỗi đúng repository và kiểm soát retry. Không log raw token.

### Bài tập 7: Reconnect bằng tài khoản khác

Người dùng đang reconnect external account của Alice nhưng tại IdP chọn Bob.

**Gợi ý đáp án:** không tự thay external identity cũ bằng Bob. Phải đối chiếu identity của callback với connection đang được cấp lại; nếu muốn đổi tài khoản, yêu cầu xác nhận và flow riêng.

### Bài tập 8: 403 khi scope không đủ

Calendar API đòi `calendar.write` nhưng token chỉ có `calendar.read`, API trả 403.

**Gợi ý đáp án:** xin lại token với cùng quyền đọc không giải quyết. Cần xác định người dùng có muốn/có thể cấp quyền ghi, cập nhật scope/consent theo provider và tuân chính sách tối thiểu.

### Bài tập 9: Retry sau timeout

Refresh request RT-1 bị timeout, Client không biết AS có cấp RT-2 chưa.

**Gợi ý đáp án:** không coi retry RT-1 là luôn an toàn. Với rotation, AS có thể đã tiêu thụ RT-1. Cần chiến lược retry/coordination theo nhà cung cấp; nếu mất trạng thái mới, có thể phải reauthorize.

### Bài tập 10: Xóa local token và revocation

Ứng dụng xóa `OAuth2AuthorizedClient` khỏi database khi người dùng chọn Disconnect.

**Gợi ý đáp án:** việc này ngăn ứng dụng sử dụng lại token đã lưu, nhưng **không tự đảm bảo Authorization Server hoặc Resource Server đã revoke credential**. Nếu yêu cầu ngắt quyền tại provider, dùng cơ chế revocation được hỗ trợ và xử lý vòng đời liên quan.

## 23. Những nguyên tắc quan trọng nhất

- **`invalid_grant` ở Token Endpoint là mã lỗi chung**, không phải bằng chứng duy nhất của token bị thu hồi.
- **Refresh token có thể hết hạn, bị thu hồi hoặc bị thay thế sau rotation**; không xem nó là credential vĩnh viễn.
- **Không retry vô hạn bằng refresh token đã bị từ chối**, đặc biệt khi provider có reuse detection.
- **Phân biệt Token Endpoint `invalid_grant` với Resource Server 401/403**; chúng có nguồn và cách xử lý khác nhau.
- **Spring Security manager có cleanup mặc định cho `invalid_grant`**, nhưng nếu đổi failure handler, phải giữ logic xóa state cần thiết.
- **Chỉ xóa đúng authorized client lỗi**; không xóa toàn bộ HTTP session, tài khoản nội bộ hay mọi kết nối nếu không có policy rõ.
- **HTTP session vẫn có thể hợp lệ** dù một external API connection cần reauthorization.
- **Reauthorization cần flow authorization mới**, thường có người dùng tương tác; background worker không tự tạo consent.
- **Kiểm tra danh tính ở callback khi reconnect** để tránh đổi nhầm external account hoặc lỗ hổng account linking.
- **Race condition khi rotation là rủi ro bảo mật**, không chỉ lỗi hiệu năng; cần lưu token mới và đồng bộ nhiều worker.
- **Revocation ở Authorization Server khác xóa token local**; xem RFC 7009 và chính sách provider.
- **Hạn chế log token, code, cookie và error payload nhạy cảm**. Ưu tiên mã lỗi và trạng thái kết nối.
- **Không thay user-delegated token bằng client credentials** để né lỗi hoặc bỏ qua consent.
- **Có UX và trạng thái `RECONNECT_REQUIRED`** để người dùng chủ động khôi phục kết nối khi cần.

## 24. Tài liệu tham khảo

1. [RFC 6749 — OAuth 2.0, Section 5.2](https://www.rfc-editor.org/rfc/rfc6749#section-5.2): token error response và `invalid_grant`.
2. [RFC 6749 — Section 6: Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): refresh grant, validation và thay refresh token mới.
3. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `invalid_token`, `insufficient_scope` và HTTP status của Resource Server.
4. [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): chủ động thu hồi token và phản hồi revocation endpoint.
5. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): an toàn refresh token, rotation/replay detection và Client protection.
6. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): authorization code, token endpoint, `offline_access` và các yêu cầu OIDC.
7. [Spring Security Reference — Servlet OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): cách quản lý OAuth2 Client và grant.
8. [Spring Security Reference — Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): tích hợp RestClient/WebClient và failure handling.
9. [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): xóa authorized client mặc định khi `invalid_grant`.
10. [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): service manager và failure handling ngoài Servlet request.
11. [Spring Security API — RemoveAuthorizedClientOAuth2AuthorizationFailureHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientOAuth2AuthorizationFailureHandler.html): chính sách xóa authorized client theo OAuth2 error.
12. [Spring Security API — OAuth2ClientHttpRequestInterceptor](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/client/OAuth2ClientHttpRequestInterceptor.html): chuyển lỗi 401/403 API tới authorization failure handler khi được cấu hình.

## 25. Tổng kết

**`invalid_grant` trong Refresh Token Grant là tín hiệu rằng Authorization Server không chấp nhận credential refresh hiện tại**. Nó có thể xuất phát từ token hết hạn, bị thu hồi, đã rotation, thuộc Client khác hoặc một chính sách của nhà cung cấp; vì thế mã lỗi không đủ để kết luận duy nhất nguyên nhân.

Trong **Spring Security OAuth2/OIDC Client**, cách xử lý vững chắc là dùng `OAuth2AuthorizedClientManager` và provider đúng grant, giữ hành vi cleanup khi refresh thất bại, ngăn reuse/race của refresh token, và quản lý trạng thái kết nối riêng với trạng thái đăng nhập website. Khi quyền user không còn có thể refresh, hãy đưa kết nối về **`RECONNECT_REQUIRED`** rồi cho người dùng thực hiện một **Authorization Code/OIDC flow mới** có kiểm chứng đúng Client, identity và consent. Những nguyên tắc đó giúp tránh vòng lặp refresh, giảm nguy cơ token replay và giữ trải nghiệm ứng dụng nhất quán ngay cả khi quyền từ nhà cung cấp bị thu hồi.
