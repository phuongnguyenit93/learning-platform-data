# 14.11. Khác biệt giữa trạng thái đăng nhập và trạng thái token

## 1. Bài toán: người dùng vẫn đăng nhập nhưng Orders API trả 401

Giả sử ứng dụng **Employee Portal** dùng **Spring Boot**, **Spring Security OAuth 2.0 Client** và **OpenID Connect (OIDC)**. Nhân viên đăng nhập bằng tài khoản công ty, xem được trang hồ sơ và truy cập màn hình đơn hàng. Sau một khoảng thời gian, trang Portal vẫn hiện tên người dùng, nhưng yêu cầu đến **Orders API** bị từ chối:

~~~text
Browser -> Employee Portal: GET /dashboard       -> 200 OK
Browser -> Employee Portal: GET /bff/orders       -> 502/401 tùy xử lý của Portal
Portal  -> Orders API:       Authorization: Bearer ...
Orders API -> Portal:        401 invalid_token
~~~

Ngược lại, người dùng có thể **logout khỏi Portal**, trong khi một access token vừa được cấp vẫn còn thời hạn ở Authorization Server hoặc Resource Server.

Đây không phải mâu thuẫn của OAuth 2.0. **Trạng thái đăng nhập của ứng dụng** và **trạng thái token của OAuth2 Authorized Client** là **hai vòng đời riêng**:

- **Đăng nhập** trả lời: *Request hiện tại được ứng dụng xác định là của principal nào?*
- **Token** trả lời: *Ứng dụng có credential nào để gọi tài nguyên được bảo vệ, credential đó còn dùng được không và cần cấp lại như thế nào?*

Hiểu hai trạng thái giúp tránh các sai lầm như đăng xuất người dùng ngay khi access token hết hạn, coi refresh token là session đăng nhập, hoặc giữ phiên đăng nhập vô hạn chỉ vì hệ thống có thể làm mới access token.

> Bối cảnh: Java 17+, Spring Boot 3 / Spring Security 6, ứng dụng **Servlet/Spring MVC** đăng nhập qua OIDC Authorization Code Flow. Những URL, token và thời gian là ví dụ. Phần kiến trúc cũng áp dụng cho WebFlux, nhưng kiểu repository/manager Reactive có API khác.

## 2. Phân biệt năm đối tượng thường bị gọi chung là “token”

| Đối tượng | Được giữ ở đâu? | Dùng để làm gì? | Có đồng nghĩa “đang login” không? |
|---|---|---|---|
| **HTTP session / session cookie** | Cookie định danh phiên ở browser; dữ liệu session phía server | Duy trì trạng thái phiên của Portal giữa các HTTP request | Cookie riêng nó **không đủ**; server phải có SecurityContext/Authentication hợp lệ |
| **Authentication và SecurityContext** | SecurityContextRepository, thường gắn với HTTP session trong ứng dụng web | Xác định principal và authorities đối với request đến Portal | **Có**, trong phạm vi chính sách xác thực của ứng dụng |
| **ID Token (OIDC)** | Được client OIDC nhận và xác minh; có thể nằm trong OidcUser | Chứng minh sự kiện xác thực do OP phát hành cho đúng client | **Không phải session của Portal**, không dùng thay access token |
| **Access token (OAuth 2.0)** | Trong OAuth2AuthorizedClient hoặc token store thích hợp | Ủy quyền lời gọi đến Resource Server | **Không**; token còn hiệu lực không có nghĩa có một HTTP session đang đăng nhập |
| **Refresh token** | Lưu bảo mật cùng authorized client khi được cấp | Yêu cầu Authorization Server cấp access token mới theo chính sách | **Không**; có refresh token không chứng minh browser hiện tại đã xác thực |

Trong Spring Security OAuth2 Client, một `OAuth2AuthorizedClient` thường chứa:

~~~text
OAuth2AuthorizedClient
├── ClientRegistration         (registrationId, grant, provider, ...)
├── principalName              (tên principal gắn authorized client)
├── OAuth2AccessToken
│   ├── tokenValue             (credential nhạy cảm)
│   ├── issuedAt
│   ├── expiresAt
│   └── scopes
└── OAuth2RefreshToken         (có thể null)
    ├── tokenValue             (credential nhạy cảm)
    └── issuedAt
~~~

Nó **không phải** SecurityContext; cũng không tự chứa một “flag login=true” có thể thay thế xác thực request web. Khi dùng OIDC, ID Token thường được biểu diễn qua `OidcUser` hoặc các thành phần OIDC liên quan, chứ không phải một thuộc tính chính của `OAuth2AuthorizedClient`.

## 3. Mô hình hai trạng thái độc lập

### 3.1. Trạng thái đăng nhập của Portal

Khi một request HTTP đến Portal, Spring Security thường:

1. Đọc thông tin phiên/cơ chế xác thực tương ứng.
2. Khôi phục hoặc xây dựng `SecurityContext`.
3. Xác định `Authentication`: principal, authorities và trạng thái authenticated.
4. Áp dụng authorization policy để quyết định request được truy cập route/tài nguyên nào.

Đối với OAuth2 Login trên Servlet, Authentication sau đăng nhập thường là `OAuth2AuthenticationToken`, principal có thể là `OidcUser`.

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Trạng thái này phụ thuộc **session của Portal và chính sách bảo mật ứng dụng**. Nó có thể bị kết thúc do logout, session timeout, quản trị thu hồi session, thay đổi SecurityContext hoặc chính sách xác thực lại.

### 3.2. Trạng thái token của Authorized Client

Một OAuth2 Authorized Client được xác định dựa trên **client registration** và **principal liên quan**, rồi lưu trong repository/service được cấu hình:

~~~text
ClientRegistration(company)
      +
PrincipalName(employee-0042)
      |
      v
OAuth2AuthorizedClient
      ├── access token
      └── refresh token (nếu có)
~~~

Tình trạng token phụ thuộc thời hạn, khả năng refresh, chính sách Authorization Server và sự chấp nhận của Resource Server. **Token “còn hạn” theo expiresAt không đồng nghĩa chắc chắn được Resource Server chấp nhận**: token có thể đã bị thu hồi, bị từ chối vì audience/scope, hoặc bị vô hiệu bởi chính sách server.

### 3.3. Mô hình không nên dùng

~~~java
// Không chính xác: có token không có nghĩa request browser đã login.
boolean loggedIn = authorizedClient != null;

// Không chính xác: user đã login không bảo đảm token còn hạn và dùng được.
boolean tokenValid = authentication.isAuthenticated();
~~~

Hai phép kiểm tra trên trả lời **sai câu hỏi**. Cần xác định riêng authentication state, authorized-client state, và **authorization của API đích**.

## 4. Ba lớp kiểm soát trong một yêu cầu gọi API

~~~mermaid
flowchart TD
    A["Browser yêu cầu /bff/orders"] --> B{"Portal có Authentication hợp lệ?"}
    B -->|Không| C["Redirect login hoặc 401 tùy loại endpoint"]
    B -->|Có| D{"Principal có quyền gọi chức năng này?"}
    D -->|Không| E["403 tại Portal"]
    D -->|Có| F["Tìm/authorize OAuth2AuthorizedClient"]
    F --> G{"Có access token phù hợp?"}
    G -->|Thiếu / hết hạn| H["Refresh/re-authorize nếu grant & policy cho phép"]
    H --> I{"Cấp token thành công?"}
    I -->|Không| J["Xử lý token failure hoặc yêu cầu ủy quyền lại"]
    I -->|Có| K["Gọi Orders API với Bearer token"]
    G -->|Có| K
    K --> L{"Orders API cho phép?"}
    L -->|Không| M["401/403 từ Resource Server"]
    L -->|Có| N["Trả kết quả nghiệp vụ"]
~~~

Ba quyết định khác nhau:

1. **Portal authentication**: browser/request đang thuộc principal nào?
2. **OAuth2 client authorization**: Portal có thể lấy token phù hợp để gọi API không?
3. **Resource Server authorization**: Orders API có chấp nhận token này cho resource cụ thể không?

Trả lời “Có” ở bước 1 **không tự động** bảo đảm bước 2 và bước 3 thành công. Tương tự, token vẫn còn hiệu lực ở bước 2 không có nghĩa người dùng hiện đã đăng nhập vào Portal.

## 5. Timeline: session và access token hết hạn vào những thời điểm khác nhau

Giả sử một môi trường minh họa:

~~~text
09:00  Người dùng đăng nhập Portal thành công.
       - Portal tạo SecurityContext/session.
       - Authorized Client có access token AT-1.
       - AT-1 expires_at = 09:05.
       - Refresh token RT-1 được cấp.

09:03  Người dùng xem dashboard.
       - Session còn hiệu lực.
       - AT-1 chưa tới thời điểm hết hạn.

09:07  Người dùng gọi /bff/orders.
       - Session vẫn hiệu lực.
       - AT-1 đã hết hạn.
       - AuthorizedClientManager có thể refresh AT-1 thành AT-2.
       - Browser không nhất thiết phải đăng nhập lại.

09:20  Người dùng logout khỏi Portal.
       - SecurityContext/session bị kết thúc theo cơ chế ứng dụng.
       - AT-2 hoặc RT-1 không mặc nhiên bị thu hồi tại IdP.

09:21  Browser gửi request mới tới Portal.
       - Không còn phiên đăng nhập hợp lệ.
       - Việc AT-2 còn hạn ở đâu đó không được coi là quyền đăng nhập Portal.
~~~

Những thời điểm trên chỉ là ví dụ. **Session timeout có thể dựa trên thời gian không hoạt động**, trong khi access token thường có thời hạn phát hành/hết hạn riêng. Một số hệ thống có session tuyệt đối, token rotation và chính sách thu hồi khác; không giả định luôn có một khoảng thời gian cố định.

## 6. Ma trận trạng thái: login và token có thể lệch nhau

| Phiên Portal | OAuth2 Authorized Client / token | Ý nghĩa và cách ứng xử |
|---|---|---|
| **Đã login** | Access token còn hạn theo metadata | Có thể gọi API, nhưng vẫn phải xét quyền/scope và kết quả từ Resource Server |
| **Đã login** | Access token hết hạn, có refresh token hợp lệ | Authorized-client manager có thể refresh; không nhất thiết login lại |
| **Đã login** | Access token hết hạn, không có refresh token | Có thể cần yêu cầu authorization lại; không tự kết luận session đã hết |
| **Đã login** | Không tìm thấy authorized client cho registration cần gọi | Có thể cần tạo authorization grant mới hoặc báo cần cấp quyền |
| **Đã login** | Token bị Resource Server từ chối | Có thể do revoked/invalid token, thiếu scope, sai audience hoặc lỗi đồng bộ; xử lý theo nguyên nhân |
| **Chưa login** | Token cũ còn tồn tại trong store | **Không** coi browser hiện tại là authenticated; cần cơ chế xác thực hợp lệ |
| **Chưa login** | Không còn token | Trạng thái bình thường sau logout/expiry |
| **Service-to-service, không có user login** | Có access token từ client_credentials | Được gọi API bằng danh tính dịch vụ, không tạo user session |

**Cùng một trạng thái “token không dùng được” có thể có nhiều nguyên nhân**. Access token hết hạn, thiếu scope và bị thu hồi là ba sự kiện khác nhau. Không nên biểu diễn chúng bằng một Boolean duy nhất mà không có thông tin lỗi/thời gian/thứ tự xử lý.

## 7. Spring Security lưu Authentication và Authorized Client ở đâu?

### 7.1. SecurityContext và HTTP session

Với cấu hình Servlet web login thông thường:

~~~text
Browser
  Cookie: JSESSIONID=...
      |
      v
HttpSession / SecurityContextRepository
      |
      v
SecurityContext
      |
      v
Authentication
  principal = OidcUser
  authorities = ...
  authenticated = true
~~~

Session cookie chỉ là **chỉ dấu tìm phiên**, còn Authentication được server kiểm soát theo SecurityContext. Cookie bị lộ có thể dẫn tới rủi ro chiếm phiên, nên phải dùng HTTPS, HttpOnly, SameSite và bảo vệ session store phù hợp.

### 7.2. AuthorizedClientRepository và AuthorizedClientService

Các kiểu API thường gặp trên Servlet:

~~~java
org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
~~~

**OAuth2AuthorizedClientRepository** hỗ trợ lưu/tải authorized client trong ngữ cảnh HTTP request/response và Authentication. **OAuth2AuthorizedClientService** hỗ trợ lưu/tải authorized client theo client registration ID và principal name ở cấp dịch vụ.

Ví dụ implementation thường thấy:

~~~java
HttpSessionOAuth2AuthorizedClientRepository
AuthenticatedPrincipalOAuth2AuthorizedClientRepository
InMemoryOAuth2AuthorizedClientService
JdbcOAuth2AuthorizedClientService
~~~

Cấu hình Spring Boot/Spring Security và phiên bản có thể quyết định loại repository/service thực tế. **Không mặc định mọi ứng dụng đều lưu access token trong đúng HTTP session**, hoặc mọi bản ghi authorized client sẽ tự biến mất khi session hết hạn.

| Thành phần | Mục đích | Sự kiện ảnh hưởng |
|---|---|---|
| `SecurityContextRepository` | Lưu/truy xuất Authentication | Login, logout, session timeout |
| `AuthorizationRequestRepository` | Lưu authorization request đang chờ để đối chiếu state ở callback | Authorization start/callback, session |
| `OAuth2AuthorizedClientRepository` | Lưu/truy xuất authorized client gắn với request/principal | Authorization, refresh, loại bỏ token |
| `OAuth2AuthorizedClientService` | Lưu/truy xuất authorized client theo registration và principal name | Authorization, refresh, cleanup |

**AuthorizationRequestRepository** không phải **OAuth2AuthorizedClientRepository**: cái thứ nhất giữ **request trước callback**, cái thứ hai giữ **token sau khi được cấp**.

### 7.3. Logout có xóa cả hai kho không?

Không thể trả lời chung “có” cho mọi triển khai. Logout của Portal thường vô hiệu phiên, xóa SecurityContext theo cấu hình. Nhưng **token ở Authorization Server vẫn có thể còn hiệu lực**, và bản ghi authorized client ở persistent service có thể có vòng đời riêng.

Muốn bảo đảm token bị thu hồi hoặc xóa khỏi local store, cần **thiết kế logout/token cleanup phù hợp**, không chỉ gọi `invalidateHttpSession(true)` rồi mặc định mọi credential phía IdP đã biến mất.

## 8. OAuth2AuthorizedClient và ClientRegistration khác nhau

Một `ClientRegistration` mô tả **client đã đăng ký** với IdP:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: employee-portal
            authorization-grant-type: authorization_code
            scope: [openid, profile, orders.read]
~~~

Nhưng chưa có user nào được ủy quyền chỉ vì YAML đã có registration.

`OAuth2AuthorizedClient` là **kết quả một authorization thành công** cho client/principal, chứa access token và refresh token (nếu được cấp).

~~~text
ClientRegistration
  company (cấu hình ứng dụng)
        |
        | authorization thành công với principal employee-0042
        v
OAuth2AuthorizedClient
  registrationId = company
  principalName  = employee-0042
  accessToken    = ...
  refreshToken   = ... (nếu có)
~~~

Nếu ứng dụng hỗ trợ nhiều registrations, một principal có thể có authorized client cho `company` nhưng chưa có cho `partner` hoặc `reports-api`. **Đã login qua company** không tự cấp token của mọi client registration khác.

## 9. ID Token hết hạn có làm Portal tự logout không?

Trong OIDC, **ID Token** chứng minh một sự kiện xác thực, kèm các claim như `iss`, `sub`, `aud`, `exp` và các claim khác.

Khi Spring Security hoàn tất login, ID Token được xác minh theo quy tắc OIDC. Sau đó ứng dụng có thể duy trì **SecurityContext trong một phiên**.

Vì vậy:

- Thời hạn **ID Token** thường được kiểm tra khi token được chấp nhận trong quá trình xác thực.
- Thời hạn **HTTP session** của Portal do chính sách phiên của ứng dụng kiểm soát.
- Thời hạn **access token** dùng gọi API là vòng đời thứ ba.

**Không mặc định ID Token hết hạn lúc 10:00 sẽ tự hủy SecurityContext của một phiên Portal đang tồn tại vào đúng 10:00.** Nếu hệ thống cần tái xác thực sau một khoảng thời gian hoặc khi thực hiện thao tác nhạy cảm, phải có **session/reauthentication policy** rõ ràng.

Ngược lại, cũng không nên diễn giải “session còn” thành “ID Token hoặc access token cũ vẫn nên được chấp nhận ở mọi nơi”. Mỗi loại token/cơ chế có mục đích và thời hạn riêng.

### 9.1. ID Token không dùng làm Bearer token cho Orders API

Tránh:

~~~java
// Sai mục đích: không dùng ID Token như access token gọi Resource Server.
String bearer = oidcUser.getIdToken().getTokenValue();
~~~

Đúng là sử dụng **access token** được cấp cho API/Resource Server, đúng issuer/audience/scope và theo chính sách API. ID Token có **audience của OAuth Client**, không mặc nhiên cho phép gọi Orders API.

## 10. Access token còn hạn không có nghĩa chắc chắn được chấp nhận

Một `OAuth2AccessToken` có thể cung cấp:

~~~java
OAuth2AccessToken token = authorizedClient.getAccessToken();
Instant expiresAt = token.getExpiresAt();
Set<String> scopes = token.getScopes();
~~~

`expiresAt` là thông tin thời hạn mà client biết được khi token được cấp. Dùng nó để quyết định **khi nào cần thử refresh** là hợp lý, có cân nhắc clock skew. Nhưng không thể chỉ kiểm tra thời hạn rồi khẳng định token “chắc chắn hợp lệ”.

Token có thể bị từ chối vì:

- **Revocation** hoặc policy của Authorization Server/Resource Server.
- **Audience** không phù hợp với API đích.
- **Scope** không đủ.
- Chữ ký JWT không hợp lệ, JWKS rotation hoặc dữ liệu issuer sai.
- Token chỉ có hiệu lực với resource/method nhất định.
- Account/tenant/resource authorization ở Resource Server đã thay đổi.
- Clock skew và thời gian hệ thống không đồng bộ.

Đồng thời, JWT có claim `exp` không có nghĩa Resource Server nào cũng thực hiện revocation tức thời; cơ chế thu hồi phụ thuộc dạng token và kiến trúc.

**HTTP 401 và 403 có ý nghĩa khác nhau trong đa số API**:

- **401** thường liên quan token thiếu/không hợp lệ/hết hạn hoặc authentication tới Resource Server không thành công.
- **403** thường liên quan token đã được nhận diện nhưng không đủ quyền.

Phản hồi thực tế còn phụ thuộc cấu hình API; cần xem `WWW-Authenticate`, security logs đã che dữ liệu nhạy cảm và policy Resource Server thay vì đoán nguyên nhân từ một mã lỗi duy nhất.

## 11. Refresh token không phải “đăng nhập vĩnh viễn”

Nếu Authorization Server cấp refresh token, OAuth2 Client có thể xin access token mới qua **refresh_token grant**:

~~~mermaid
sequenceDiagram
    participant Browser as Browser
    participant Portal as Employee Portal
    participant Manager as OAuth2AuthorizedClientManager
    participant IdP as Authorization Server
    participant API as Orders API

    Browser->>Portal: GET /bff/orders với session hợp lệ
    Portal->>Manager: authorize(company, principal)
    Manager->>Manager: Đọc OAuth2AuthorizedClient
    Manager->>Manager: Access token sắp/hết hạn
    Manager->>IdP: POST /token grant_type=refresh_token
    IdP-->>Manager: Access token mới (+ refresh token mới nếu rotate)
    Manager->>Manager: Cập nhật authorized client
    Manager-->>Portal: Authorized client đã làm mới
    Portal->>API: Authorization: Bearer token mới
    API-->>Portal: Dữ liệu đơn hàng
    Portal-->>Browser: Trả kết quả
~~~

Đây là luồng minh họa khi **refresh token tồn tại, grant được hỗ trợ, token manager/provider được cấu hình và request đáp ứng chính sách**. Không phải mọi token hoặc mọi provider đều cấp refresh token.

### 11.1. Khi nào refresh thực sự xảy ra?

Cần có các điều kiện phù hợp:

1. Một thành phần như `OAuth2AuthorizedClientManager` **được gọi** trong lúc ứng dụng cần authorized client.
2. Authorized-client provider có hỗ trợ `refresh_token`.
3. Authorized client có refresh token còn dùng được.
4. Token cần refresh theo logic expiry/clock skew của provider.
5. Authorization Server chấp nhận credential/grant và trả kết quả hợp lệ.

**Có refresh token trong database không làm token tự refresh khi thời gian trôi qua.** Trong phần lớn ứng dụng, việc refresh được kích hoạt khi cần authorize/gọi API hoặc bởi tác vụ đã thiết kế riêng. Nếu chỉ đọc đối tượng `OAuth2AuthorizedClient` trực tiếp từ repository, không nên kỳ vọng repository tự gọi token endpoint.

### 11.2. Refresh có thể thất bại dù session còn

Ví dụ IdP trả:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant"}
~~~

Nguyên nhân có thể là refresh token hết hiệu lực, bị thu hồi, đã dùng rồi trong cơ chế rotation, không còn được phép hoặc sai điều kiện grant.

Khi đó Portal vẫn có thể có Authentication hợp lệ theo session, nhưng **không có access token dùng được để gọi Orders API**. Ứng dụng phải xử lý theo chính sách: yêu cầu authorization lại, điều hướng qua OIDC login mới khi cần, trả trạng thái lỗi phù hợp hoặc yêu cầu người dùng thực hiện thao tác bổ sung.

**Không giải quyết mọi lỗi token bằng cách giữ session đăng nhập vô hạn.** Ngược lại, **không buộc toàn bộ người dùng logout** mỗi khi một API tạm thời lỗi hoặc một token của registration phụ hết hạn.

### 11.3. Refresh token rotation

Một số Authorization Server **rotate refresh token**: khi sử dụng RT-1, server trả AT-2 và RT-2, đồng thời RT-1 có thể không còn dùng được.

~~~text
T1: Authorized Client = AT-1 + RT-1
T2: Refresh RT-1       -> AT-2 + RT-2
T3: Lưu Authorized Client mới
T4: Refresh tiếp       -> dùng RT-2, không dùng RT-1
~~~

Nếu ứng dụng chạy nhiều replica và hai request cùng cố refresh bằng RT-1, có thể gặp đua tranh và lỗi `invalid_grant`. Cần lựa chọn cơ chế phối hợp refresh, lưu dữ liệu đồng nhất và retry phù hợp với nhà cung cấp; **không retry vô điều kiện token request dùng refresh token đã bị rotate**.

## 12. Logout khỏi Portal không mặc nhiên revoke token

Có ít nhất ba lớp “logout” cần phân biệt:

| Hành động | Kết quả chính | Điều không nên tự giả định |
|---|---|---|
| **Local logout của Portal** | Xóa/invalidates HTTP session, SecurityContext theo cấu hình | Access/refresh token ở Authorization Server chắc chắn đã bị revoke |
| **OIDC RP-Initiated Logout tại IdP** | Chuyển/điều phối logout phiên SSO ở OP nếu hỗ trợ | Tất cả access token đến mọi API bị vô hiệu tức thời |
| **Token revocation/cleanup** | Yêu cầu thu hồi token tại endpoint phù hợp và/hoặc loại token khỏi local store | Browser session của Portal tự bị xóa nếu không xử lý riêng |

Ví dụ:

~~~text
10:00  User login -> Session S1 + AccessToken AT1
10:02  User logout Portal -> S1 bị hủy
10:03  AT1 có thể vẫn còn thời hạn ở Resource Server
10:04  Request browser không có Session S1 không được xem là login
~~~

Nếu ứng dụng cần thu hồi refresh token khi logout, nên kiểm tra Authorization Server có **revocation endpoint** và chính sách token revocation hay không. Nếu cần single logout across clients, đó là bài toán OIDC logout/session management riêng, không chỉ xóa cookie của Portal.

**Logout trên Portal phải cắt quyền của phiên browser hiện tại**, dù một token trong backend store chưa hết hạn. Ngược lại, một lệnh revoke token có thể không tự hủy SecurityContext; chính sách ứng dụng cần quyết định khi nào bắt người dùng xác thực lại.

## 13. Token còn nhưng không có login: những trường hợp hợp lệ

### 13.1. Client Credentials Flow

Một tác vụ backend dùng `client_credentials` có thể lấy access token để gọi API theo danh tính dịch vụ:

~~~text
Scheduled job
  -> OAuth2AuthorizedClientManager
  -> ClientRegistration(reports-service)
  -> access token từ client_credentials
  -> Reports API
~~~

Không có browser, không có HTTP session của người dùng, không có OIDC user principal. **Access token của dịch vụ không chứng minh một người dùng đang login**.

### 13.2. Authorized client được lưu trong persistent service

Nếu deployment dùng một `OAuth2AuthorizedClientService` có lưu token theo principal name, bản ghi authorized client có thể tồn tại lâu hơn HTTP session tùy cấu hình và cleanup policy. Tuy nhiên, một browser chưa được xác thực **không thể yêu cầu Portal tùy tiện tải token của principal name do browser nhập rồi sử dụng như user đó**.

Đối với grant thay mặt người dùng, ứng dụng phải gắn việc truy xuất token với Authentication/authorization context đã được tin cậy. Không dùng `?principalName=admin` để chọn token.

### 13.3. Token ở hệ thống khác

Một access token được phát cho mobile app, service khác hoặc lần đăng nhập trước không có nghĩa Portal đang có session hợp lệ. Token có audience, client và vòng đời riêng. Không lấy sự tồn tại của token ở hệ thống khác để “khôi phục” phiên Portal mà không có cơ chế xác thực phù hợp.

## 14. Servlet: cấu hình Spring Security OAuth2 Login

### 14.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 14.2. Client registration

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
~~~

Ở production phải cấu hình HTTPS và cookie `Secure` phù hợp, ví dụ `server.servlet.session.cookie.secure=true`. `OIDC_CLIENT_SECRET` phải được cấp từ nguồn secret an toàn, không ghi vào Git, JavaScript hay tài liệu dùng chung.

`session.timeout: 30m` không đặt access token lifetime thành 30 phút. Thời hạn access token do Authorization Server và token response xác định.

### 14.3. SecurityFilterChain

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Ở đây:

- `oauth2Login()` đảm nhận login và Authentication.
- `oauth2Client()` cung cấp những tích hợp OAuth Client để quản lý việc sử dụng authorized client khi ứng dụng cần gọi API.
- Không có dòng cấu hình nào tuyên bố “session sống bao lâu thì access token sống bấy lâu”.

Nếu API của Portal cần xử lý unauthenticated request bằng **401 JSON** thay vì redirect HTML đến IdP, cần cấu hình security entry point/exception handling phù hợp từng route. Đó là khác biệt về **cách phản hồi request**, không phải thay đổi bản chất vòng đời token.

## 15. Đọc riêng trạng thái login và trạng thái token

Một công cụ chẩn đoán hữu ích là kiểm tra **hai nguồn riêng**: Authentication của request và authorized client trong repository. Ví dụ một service nội bộ chỉ kiểm tra metadata, **không gọi refresh**:

~~~java
package com.example.portal.diagnostics;

import java.time.Instant;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.stereotype.Component;

@Component
public class AuthStateInspector {

    private final OAuth2AuthorizedClientRepository authorizedClients;

    public AuthStateInspector(
        OAuth2AuthorizedClientRepository authorizedClients
    ) {
        this.authorizedClients = authorizedClients;
    }

    public AuthSnapshot inspect(
        Authentication authentication,
        HttpServletRequest request
    ) {
        boolean loggedIn = authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);

        if (!loggedIn) {
            return new AuthSnapshot(false, false, null, false);
        }

        OAuth2AuthorizedClient client =
            authorizedClients.loadAuthorizedClient(
                "company", authentication, request
            );

        if (client == null || client.getAccessToken() == null) {
            return new AuthSnapshot(true, false, null, false);
        }

        Instant expiresAt = client.getAccessToken().getExpiresAt();
        boolean pastRecordedExpiry =
            expiresAt != null && !Instant.now().isBefore(expiresAt);

        return new AuthSnapshot(
            true, true, expiresAt, pastRecordedExpiry
        );
    }

    public record AuthSnapshot(
        boolean loggedIn,
        boolean authorizedClientStored,
        Instant tokenExpiresAt,
        boolean tokenPastRecordedExpiry
    ) {}
}
~~~

Code này minh họa đọc state:

- **loggedIn** dựa trên Authentication của request.
- **authorizedClientStored** cho biết kho hiện có bản ghi cho `company` và principal.
- **tokenPastRecordedExpiry** là kết quả so với `expiresAt` tại thời điểm kiểm tra.

**Không diễn giải `authorizedClientStored=true` thành “token chắc chắn được API chấp nhận”**. Và **không diễn giải `tokenPastRecordedExpiry=true` thành “phải logout ngay”**.

Service này **không gọi `OAuth2AuthorizedClientManager.authorize(...)`** nên **không chủ động refresh token**. Nếu muốn token được cấp lại, phải qua authorized client manager/provider thích hợp.

> Mã chẩn đoán chỉ nên được dùng trong kiểm thử hoặc kênh quản trị được kiểm soát. Không công khai endpoint trả principal/session/token metadata cho mọi người và không bao giờ trả `tokenValue` hoặc refresh token ra browser để kiểm tra trạng thái.

## 16. Gọi API bằng authorized client đã được quản lý

Một endpoint Portal có thể cần gọi Orders API thay mặt người dùng. Với Spring Security OAuth2 Client trên Servlet, `@RegisteredOAuth2AuthorizedClient` là một cách nhận authorized client đã được giải quyết theo ngữ cảnh:

~~~java
package com.example.portal.web;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersController {

    private final RestClient ordersApi =
        RestClient.create("https://orders.example.test");

    @GetMapping("/bff/orders")
    public String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

Đây là ví dụ **gửi bearer token server-to-server**, không trả token về JavaScript. Trong production, URL Orders API nên được lấy từ property theo môi trường; HTTP client cần timeout/TLS/error handling, và response không nên bao gồm thông tin nhạy cảm ngoài phạm vi cần thiết.

Khi gọi qua **authorized client manager/argument resolver được cấu hình thích hợp**, Spring Security có thể thực hiện bước **re-authorize/refresh** theo provider chain khi token hết hạn. **Không tự giả định mỗi lần đọc một OAuth2AuthorizedClient từ repository đều refresh**.

### 16.1. Nếu Orders API trả 401 thì làm gì?

Không nên:

~~~java
// Sai hướng: API lỗi 401 là lập tức coi mọi phiên Portal hết hạn.
session.invalidate();
~~~

Một cách xử lý có phân loại:

1. Xác nhận **request browser vẫn authenticated ở Portal**.
2. Xác nhận token dùng gọi Orders API thuộc đúng client registration, audience và scopes.
3. Kiểm tra token có quá thời điểm expiry đã biết không; nếu có và refresh được, dùng token manager thích hợp.
4. Nếu Resource Server trả `invalid_token`, áp dụng chiến lược OAuth2 client failure handling/re-authorize hoặc yêu cầu người dùng cấp quyền lại theo khả năng.
5. Nếu lỗi là `insufficient_scope` hoặc HTTP 403 do chính sách quyền, **refresh cùng scope thường không giải quyết**; cần cấp quyền phù hợp hoặc từ chối thao tác.
6. Nếu Orders API đang lỗi 5xx/time out, không biến lỗi hạ tầng thành “logout người dùng”.

Tránh retry vô hạn và tránh **gửi token cũ lặp lại** khi Resource Server đã tuyên bố token không hợp lệ. Khi sử dụng OAuth2 client filter cho `WebClient` hoặc `RestClient`, có thể cấu hình authorized-client failure handler phù hợp phiên bản để loại dữ liệu token không hợp lệ và thử quy trình cấp lại có kiểm soát.

## 17. Cấu hình OAuth2AuthorizedClientManager cho refresh token

Đối với Servlet web request, `DefaultOAuth2AuthorizedClientManager` phối hợp:

- `ClientRegistrationRepository`: cấu hình provider/client.
- `OAuth2AuthorizedClientRepository`: lưu/tải authorized client theo request/principal.
- `OAuth2AuthorizedClientProvider`: thực thi grant `authorization_code`, `refresh_token`, ... nếu được bật.

Ví dụ tạo manager có provider cho authorization code và refresh:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClientRepository
    ) {
        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClientRepository
            );
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Ví dụ này minh họa **đăng ký provider chain** chứ không buộc mọi dự án tạo bean riêng: Spring Boot và Spring Security có thể đã cung cấp integration phù hợp. Nếu tạo bean tùy chỉnh, cần kiểm tra các thành phần gọi OAuth2 Client có **dùng đúng manager đó** và các grant khác đang cần (ví dụ `client_credentials`) có bị loại ngoài ý muốn không.

**Refresh token provider không làm thay đổi SessionCreationPolicy hoặc HTTP session timeout.** Nó chỉ giải quyết vòng đời **token**.

### 17.1. Manager dùng cho tác vụ nền khác web request

Một scheduled job hoặc message consumer không có `HttpServletRequest` thường nên dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` kết hợp `OAuth2AuthorizedClientService`, với provider grant phù hợp.

Không cố lấy `SecurityContextHolder.getContext().getAuthentication()` của một user web trong scheduled job rồi giả định đó là danh tính hợp lệ cho mọi lần chạy. Nếu tác vụ cần danh tính dịch vụ, thường dùng client credentials; nếu bắt buộc gọi thay mặt người dùng, phải có chính sách consent, storage, revocation và audit phù hợp.

## 18. Kết thúc phiên không đồng nghĩa kết thúc ủy quyền của IdP

OIDC login có ít nhất **ba loại phiên/trạng thái**:

~~~text
1) OP / IdP SSO Session
   Cookie tại login.example.test

2) Portal Web Session
   Cookie tại portal.example.test
   SecurityContext / OidcUser

3) OAuth2 Authorized Client
   Access token / Refresh token tại Portal
   Token còn dùng được hay không do AS/Resource Server quyết định
~~~

Các sự kiện:

| Sự kiện | OP SSO session | Portal session | Authorized client/token |
|---|---|---|---|
| User login Portal | Có thể được tạo/tái sử dụng | Được tạo/kích hoạt | Thường có token sau callback |
| User logout Portal | Có thể vẫn còn | Bị kết thúc theo cấu hình | Có thể còn ở store hoặc AS |
| User logout tại OP | Bị kết thúc theo chính sách OP | Không mặc nhiên bị xóa nếu Portal chưa nhận được logout notification | Không mặc nhiên bị revoke |
| Access token hết hạn | Không nhất thiết đổi | Không nhất thiết đổi | Cần refresh/re-authorize để gọi API |
| Refresh token bị revoke | Không nhất thiết đổi | Có thể vẫn tồn tại | Không làm mới được token mới |
| Portal session timeout | Có thể còn SSO | Bị kết thúc | Token có thể tồn tại tùy storage |

Nếu browser quay về Portal sau khi local session hết hạn nhưng IdP SSO session còn, quy trình OIDC authorization mới có thể diễn ra nhanh và người dùng cảm giác “không cần nhập mật khẩu”. **Đây là đăng nhập lại qua SSO**, không phải chứng cứ phiên Portal cũ vẫn còn.

### 18.1. Single Logout và Back-Channel Logout

Một số OP hỗ trợ logout thông báo tới các RP/Client theo OIDC. Nếu dùng những cơ chế đó, Portal phải cấu hình xử lý và liên kết phiên đúng chuẩn; **không tự giả định cấu hình OIDC login mặc định đã thực hiện toàn bộ single logout hoặc token revocation**.

Ngay cả khi ứng dụng nhận logout event, phải quyết định những phiên ứng dụng nào cần bị hủy và có cần xóa/revoke authorized client tương ứng hay không.

## 19. Trạng thái phân quyền có thể thay đổi dù cả session và token còn hạn

Đây là khía cạnh dễ bỏ sót khi chỉ nhìn authentication và token:

~~~text
09:00 User login, được role ORDER_MANAGER
09:05 Quản trị viên thu hồi role ORDER_MANAGER
09:10 HTTP session vẫn tồn tại
09:10 Access token vẫn chưa hết hạn
09:10 Người dùng yêu cầu xóa đơn hàng
~~~

Ứng dụng cần xác định **cơ chế cập nhật/kiểm tra authorization**:

- Nếu role/authority của Portal được lưu trong Authentication tại lúc login, quyền có thể trở nên **cũ** nếu không có chính sách cập nhật/reauthentication.
- Nếu Resource Server kiểm tra quyền bằng dữ liệu động, API có thể từ chối dù token vẫn còn hạn.
- Nếu role được đóng gói vào JWT access token, API chỉ dùng JWT claim tĩnh có thể tiếp tục chấp nhận quyền cũ cho đến khi token hết hạn, trừ khi có cơ chế revocation/kiểm tra bổ sung.
- Nếu app có tenant membership/ownership trong database, cần kiểm tra quyền tại service/resource boundary chứ không chỉ dựa trên claim `email` hay tên principal.

Do đó, **session còn + token còn hạn** chưa bảo đảm thao tác vẫn được phép. Đây là vấn đề **authorization**, tách khỏi cả hai trạng thái đang phân tích.

## 20. Nhiều authorized client trong cùng một phiên

Employee Portal có thể dùng:

~~~text
registration company       -> OIDC login và Orders API
registration reports-api   -> access token để gọi Reports API
registration partner       -> authorization với IdP đối tác
~~~

Một principal đã login qua `company` không nhất thiết có token cho `reports-api` hoặc `partner`. Thậm chí token của hai registrations có thể:

- Hết hạn vào thời điểm khác nhau.
- Có refresh token khác nhau hoặc không có refresh token.
- Có scopes và audience khác nhau.
- Bị thu hồi độc lập.
- Sử dụng client authentication method khác nhau.

Vì vậy cần quản lý token state **theo authorized client/registration**, không tạo một cờ toàn cục `userHasValidToken`.

Ví dụ:

| Registration | Login state | Token state |
|---|---|---|
| company | User đang authenticated tại Portal | Access token còn hạn |
| reports-api | User vẫn login qua company | Token chưa được cấp hoặc hết hạn |
| partner | User vẫn login qua company | Chưa có consent từ partner |

Nếu gọi Reports API thất bại do token của `reports-api`, không nhất thiết phải xóa ngay phiên company. Cần xử lý đúng luồng cấp quyền/token của reports-api.

## 21. Principal name và lưu trữ authorized client

Một số implementation lưu authorized client dựa trên:

~~~text
(clientRegistrationId, principalName)
~~~

Ví dụ:

~~~text
("company", "employee-0042")
~~~

Nếu ứng dụng thay `user-name-attribute` từ `sub` sang `email`, hoặc người dùng đổi email, principal name có thể thay đổi và authorized client cũ không còn được tìm thấy bằng khóa mới.

Hệ quả có thể là:

- Portal vẫn nhận user đăng nhập thành công nhưng không tìm thấy token cũ.
- Client phải authorize lại dù email chỉ đổi vì mục đích hồ sơ.
- Audit và authorized-client records xuất hiện nhiều principal name cho một người.

Với OIDC, ứng dụng nên duy trì danh tính ổn định theo **issuer + subject** cho dữ liệu nghiệp vụ và kiểm tra tác động tới authorized-client storage khi thay đổi principal naming. Không dùng email làm cầu nối tự động vào bản ghi token thuộc account khác.

## 22. Cookie, SameSite và reverse proxy ảnh hưởng login; không xác định token expiry

Portal chạy sau reverse proxy:

~~~text
Browser --HTTPS--> Proxy --HTTP nội bộ--> Spring Boot
    |                                  |
    | Cookie JSESSIONID                | SecurityContext / AuthorizedClient
    +-- callback từ IdP -------------->|
~~~

Nếu browser không gửi session cookie ở callback do `SameSite`, `Secure`, `Path` hoặc host sai, ứng dụng có thể **không tìm thấy authorization request ban đầu**, khiến login thất bại trước khi có authorized client.

Điều đó khác với **token expiry** sau login. Không sửa chính sách cookie để xử lý access token hết hạn; cũng không tăng access token lifetime để chữa lỗi mất session callback.

Ví dụ cấu hình production:

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Chỉ tin cậy forwarded headers từ proxy đáng tin đã lọc host/scheme/prefix, không dùng header do browser tùy ý gửi vào để xác định redirect URI. **SameSite=Lax** thường phù hợp với callback top-level GET; callback cross-site POST như `form_post` cần đánh giá riêng về cookie SameSite, Secure và CSRF.

### 22.1. Multi-instance session và authorized-client store

Nếu ứng dụng có nhiều node:

~~~text
Login bắt đầu ở node A -> authorization request/session A
Callback vào node B      -> phải truy cập được cùng dữ liệu session
Sau login lấy token ở B  -> phải tìm được authorized client phù hợp
~~~

Phải phân biệt:

- **Session store** để khôi phục SecurityContext và authorization request.
- **Authorized client storage** để tìm token của principal/registration.

Có thể dùng session persistence/affinity hoặc shared stores tùy kiến trúc. Shared token store không tự sửa session callback bị mất; shared session không tự bảo đảm refresh token rotation không gặp race condition.

## 23. Cách ứng dụng nên diễn giải các lỗi cho người dùng

Một phản hồi UX tốt dựa trên **loại thất bại**, không gộp mọi lỗi thành “Phiên đăng nhập đã hết hạn”.

| Tình huống | Thông điệp/ngữ nghĩa phù hợp |
|---|---|
| Không có Authentication/session | Yêu cầu đăng nhập Portal |
| User authenticated nhưng chưa authorize registration phụ | Yêu cầu cấp quyền/kết nối dịch vụ cần thiết |
| Access token hết hạn và refresh thành công | Tiếp tục thao tác bình thường, không làm phiền user |
| Refresh token không dùng được | Yêu cầu authorization lại hoặc xác thực lại theo chính sách |
| API trả 403 do thiếu quyền | Báo không đủ quyền, không diễn đạt là mất session |
| API tạm thời timeout/5xx | Báo dịch vụ tạm không khả dụng, có thể retry có kiểm soát |
| Portal account bị disabled | Chặn quyền truy cập theo chính sách, dù IdP login/refresh vẫn hoạt động |
| Logout local thành công | Không tiếp tục coi browser là authenticated; cleanup/revoke tùy thiết kế |

**Lưu ý API vs browser navigation:** một endpoint JSON dành cho SPA/BFF thường nên trả trạng thái HTTP có thể xử lý được thay vì vô điều kiện phát redirect HTML đến IdP. Đối với login front-channel, redirect đến IdP là hành vi hợp lý. Phân loại này thuộc thiết kế exception handling/entry point của Portal.

## 24. Quan sát và log an toàn

Khi điều tra tình huống “vẫn login nhưng API lỗi”, nên thu thập **metadata không bí mật**:

- Request có Authentication hợp lệ không?
- Client registration ID nào đang được sử dụng?
- Authorized client record có tồn tại không?
- Access token có `expiresAt` nào và có vượt thời điểm đó chưa?
- Có refresh token không? **Chỉ ghi Boolean**, không log token value.
- Token manager/provider có được gọi và refresh có thành công không?
- API trả 401, 403, 429, 5xx hay timeout?
- Lỗi OAuth2 là `invalid_grant`, `invalid_client` hay `insufficient_scope`?

**Không ghi**:

~~~text
Authorization: Bearer <real-access-token>
refresh_token=<real-refresh-token>
client_secret=<real-client-secret>
session_cookie=<real-JSESSIONID>
id_token=<real-ID-token>
authorization_code=<real-code>
~~~

Ngay cả JWT access token có payload đọc được vẫn là credential nhạy cảm. Nếu cần correlation giữa log, dùng trace ID/request ID và mã sự kiện đã được kiểm soát, tránh đưa token hoặc dữ liệu cá nhân đầy đủ vào hệ thống log/APM.

## 25. Những nhầm lẫn thường gặp

**“User đã login nên access token còn dùng được.”** Sai. Session và token có expiry/policy riêng.

**“Access token hết hạn thì phải logout ngay.”** Không nhất thiết. Có thể refresh/re-authorize trong khi session còn.

**“Có refresh token tức là user luôn login.”** Sai. Refresh token là credential cấp lại access token, không phải HTTP session và không tự xác minh browser request.

**“ID Token hết hạn thì session tự biến mất.”** Không mặc nhiên. Cần session/reauthentication policy.

**“Logout local tự động revoke mọi token ở IdP.”** Không mặc nhiên. Phải cấu hình cleanup/revocation/logout tương ứng.

**“Không tìm thấy authorized client nghĩa là không có Authentication.”** Sai. Authorized client có thể chưa tồn tại hoặc đã bị xóa cho một registration.

**“OAuth2AuthorizedClientRepository.loadAuthorizedClient tự refresh token.”** Không nên giả định. Repository chủ yếu lưu/tải; token lifecycle do manager/provider điều phối khi được gọi.

**“API trả 403 nghĩa là token hết hạn.”** Không nhất thiết. Thường là không đủ quyền hoặc resource policy từ chối.

**“Một access token dùng được cho mọi API.”** Sai. Scope/audience/resource policy quyết định token dùng cho API nào.

**“Có JWT thì token không bao giờ bị revoke.”** Sai. Khả năng/phương pháp revocation phụ thuộc server, thời hạn và kiến trúc kiểm tra token.

**“Client credentials token là login của nhân viên.”** Sai. Đó là grant cho danh tính dịch vụ, không phải một phiên OIDC của người dùng.

## 26. Bài tập tình huống

### Bài 1: access token hết hạn nhưng session còn

~~~text
Portal session timeout = 30 phút không hoạt động
Access token lifetime = 5 phút
Refresh token = được cấp

09:00 login
09:10 user mở /bff/orders
~~~

**Câu hỏi:** Có bắt buộc redirect về IdP không?

**Hướng xử lý:** Không nhất thiết. Nếu session vẫn được duy trì và refresh token còn hợp lệ, authorized-client manager có thể xin access token mới mà không yêu cầu user đăng nhập lại. Nếu refresh thất bại, cần xử lý lại authorization theo chính sách.

### Bài 2: logout rồi token vẫn còn hạn

~~~text
10:00 logout Portal
10:01 access token cũ được Resource Server chấp nhận khi gọi trực tiếp
~~~

**Câu hỏi:** Logout Portal đã thất bại?

**Hướng xử lý:** Chưa thể kết luận. Local logout hủy phiên Portal; access token đã cấp có vòng đời riêng và có thể còn hiệu lực. Nếu yêu cầu sản phẩm là revoke token khi logout, phải triển khai revocation/cleanup và kiểm tra chính sách Resource Server.

### Bài 3: session hợp lệ nhưng registration reports-api chưa có token

Portal dùng company để đăng nhập, reports-api để lấy token gọi Reports API.

**Câu hỏi:** Thiếu token của reports-api có nghĩa principal chưa xác thực không?

**Hướng xử lý:** Không. Người dùng có thể authenticated bằng company nhưng chưa authorize reports-api. Cần xử lý authorization riêng cho registration đó.

### Bài 4: token còn hạn nhưng API trả 403

Portal có access token với `orders.read`, user yêu cầu xóa đơn hàng cần `orders.write`.

**Câu hỏi:** Gửi refresh token có chắc giải quyết được không?

**Hướng xử lý:** Không. Refresh cùng scope có thể vẫn không cấp `orders.write`. Cần chính sách cấp quyền/consent đúng; nếu user không có quyền thì trả 403 phù hợp.

### Bài 5: ID Token đã hết hạn

ID Token của OIDC login có `exp` ở 09:05, Portal session còn đến 09:30 theo chính sách.

**Câu hỏi:** Có nên dùng ID Token đó như bearer để gọi Orders API lúc 09:10?

**Hướng xử lý:** Không. ID Token không phải access token cho Orders API. Việc Portal giữ session theo policy riêng cũng không thay đổi ý nghĩa `exp` của ID Token.

### Bài 6: hai replica refresh cùng lúc

Hai request vào hai node cùng dùng một refresh token `RT-1`, provider hỗ trợ refresh token rotation.

**Câu hỏi:** Rủi ro gì?

**Hướng xử lý:** Một request có thể dùng RT-1 trước, nhận RT-2, request còn lại dùng RT-1 đã bị vô hiệu và gặp `invalid_grant`. Cần xử lý concurrency/store theo chính sách AS, không retry RT-1 vô hạn.

## 27. Checklist khi thiết kế Authorized Client

| Câu hỏi | Điểm cần xác định |
|---|---|
| Portal xác thực request bằng cơ chế gì? | SecurityContext/session, OIDC login hoặc cơ chế xác thực đã cấu hình |
| Token dùng để gọi đâu? | Resource Server nào, audience, scope và principal tương ứng |
| Token được lưu ở đâu? | OAuth2AuthorizedClientRepository/Service nào, thời hạn và quyền truy cập |
| Khi nào access token được refresh? | Manager/provider nào được gọi và grant nào được hỗ trợ |
| Không có refresh token thì sao? | Cơ chế re-authorize hoặc yêu cầu người dùng cấp quyền lại |
| Refresh failure được xử lý ra sao? | Phân biệt invalid_grant, invalid_client, timeout và yêu cầu user action |
| Logout local xử lý gì? | Session/SecurityContext, local authorized client cleanup, revocation nếu cần |
| IdP SSO logout có tác động Portal không? | Cấu hình OIDC logout notification/reauth policy |
| Access token còn hạn nhưng API từ chối? | Scope, audience, revocation và quyền resource |
| Nhiều client registrations? | Token/refresh riêng, không dùng một cờ tokenValid toàn cục |
| Nhiều replica? | Session store, authorized-client store, refresh token rotation/concurrency |
| Email/principal name thay đổi? | Khóa lưu authorized client, mapping external identity và migration |
| Log có lộ token/secret không? | Chỉ ghi metadata cần thiết, che credential và dữ liệu cá nhân |
| Browser còn session nhưng quyền thay đổi? | Authorization policy/role refresh/session revalidation |

## 28. Kết luận

**Trạng thái đăng nhập** và **trạng thái token** cần được thiết kế như **hai vòng đời độc lập nhưng có liên quan**:

- **Authentication / SecurityContext / HTTP session** cho biết request hiện được Portal chấp nhận là của principal nào và quyền ứng dụng nào đang áp dụng.
- **OAuth2AuthorizedClient / access token / refresh token** cho biết client có credential để gọi Resource Server hay không và có thể refresh/re-authorize theo grant/policy nào.
- **OIDC ID Token** là dữ liệu xác thực người dùng ở bước login, không phải session cookie và cũng không phải access token cho Orders API.
- **Resource Server** tự xác minh token và áp dụng quyền tài nguyên; token chưa hết hạn không mặc nhiên đủ quyền.

Vì thế, **user có thể vẫn đăng nhập khi access token hết hạn**, và **token có thể còn hiệu lực sau khi phiên Portal kết thúc**. Không sử dụng một Boolean “loggedIn” để đại diện toàn bộ token state, cũng không dùng “tokenPresent” để xác định authentication state. Hãy kết hợp **session management**, **authorized-client management**, **refresh/revocation policy** và **resource authorization** theo đúng trách nhiệm của từng lớp. Đây là nền tảng để xây dựng OAuth2/OIDC Client ổn định, an toàn và dễ chẩn đoán trong ứng dụng Spring Security.
