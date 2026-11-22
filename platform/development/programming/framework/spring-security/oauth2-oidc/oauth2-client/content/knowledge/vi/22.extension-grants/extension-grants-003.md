# 22.3. Token Exchange và yêu cầu tương thích của provider

## 1. Đặt vấn đề: Tại sao cần Token Exchange?

Trong kiến trúc **Spring Security OAuth 2.0/OIDC Client**, ứng dụng có thể nhận một access token hợp lệ từ người dùng rồi cần gọi API ở miền tin cậy hoặc audience khác. Không thể mặc định access token được cấp cho Service A cũng hợp lệ tại Service B.

Ví dụ:

```text
Browser / Mobile App
   |
   | Access Token A
   | aud = gateway-api
   v
Service A / Gateway
   |
   | Muốn gọi Orders API, nơi yêu cầu aud = orders-api
   v
Authorization Server / Security Token Service (STS)
   |
   | RFC 8693 Token Exchange:
   | subject_token = Token A
   | audience = orders-api
   | scope = orders.read
   |
   v
Access Token B
   |
   | aud = orders-api, scope = orders.read
   v
Orders API
```

Nếu Service A gửi Token A thẳng cho Orders API, Resource Server kiểm tra audience đúng cách phải từ chối. Nếu Service A tự sửa payload JWT rồi ký bằng khóa không được Orders API tin cậy, đó không phải Token Exchange hợp lệ.

**OAuth 2.0 Token Exchange (RFC 8693)** định nghĩa một extension grant để OAuth2 client yêu cầu STS phát một security token mới dựa trên token đã có, tùy chính sách xác thực và ủy quyền. Đây không phải đặc tính bắt buộc của mọi OAuth2 Authorization Server hoặc OpenID Provider.

### Sau bài này, bạn có thể

1. Giải thích Token Exchange khác Authorization Code, Refresh Token và Client Credentials thế nào.
2. Nắm yêu cầu định dạng RFC 8693: subject token, actor token, token types, audience, resource và scope.
3. Phân biệt impersonation và delegation, hiểu claims `act`, `may_act`.
4. Đọc response, phân biệt `issued_token_type` với `token_type`.
5. Biết provider cần hỗ trợ chính xác những gì để Token Exchange thành công.
6. Đánh giá tính tương thích giữa RFC 8693 và các On-Behalf-Of (OBO) flows riêng của provider.
7. Cấu hình `TokenExchangeOAuth2AuthorizedClientProvider` trong Spring Security Servlet.
8. Dùng `RestClientTokenExchangeTokenResponseClient` tùy chỉnh `audience` hoặc `resource`.
9. Chọn subject token và actor token bằng resolvers phù hợp.
10. Xác định cách tích hợp tương ứng với WebFlux/reactive.
11. Thiết kế token cache, lifecycle, lỗi, kiểm thử và bảo mật đúng trust boundary.

Các URLs, tokens, issuer, scope, audience và client IDs trong bài chỉ là **minh họa**. Với provider thật, phải đối chiếu tài liệu và chính sách của **đúng phiên bản, tenant/realm và client registration**.

---

## 2. Bối cảnh microservices và luồng trao đổi token

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant A as Service A - Resource Server & OAuth2 Client
    participant STS as Authorization Server - STS
    participant B as Service B - Resource Server

    U->>A: GET /my-orders, Bearer Token A
    Note over A: Xác minh Token A: issuer, signature, aud, exp
    A->>STS: POST /token, Token Exchange, subject_token=A
    Note over STS: Xác thực client và subject token
    Note over STS: Kiểm tra target, scope, delegation policy
    STS-->>A: Token B cho orders-api
    A->>B: GET /orders, Bearer Token B
    Note over B: Xác minh Token B và authorization
    B-->>A: Orders data
    A-->>U: Response
```

**Ba ranh giới an ninh cần tách biệt:**

- **Inbound Resource Server (Service A):** kiểm chứng token được gửi tới chính A. Một token hợp lệ của issuer bất kỳ không đủ; phải xác minh audience và policy dành cho A.
- **STS:** xác định client đang yêu cầu có được phép sử dụng subject token để lấy token cho target B không. Đây là nơi thực thi chính sách Token Exchange.
- **Target Resource Server (Service B):** xác minh Token B, kiểm tra issuer, audience, expiry, scopes, actor/delegation claims nếu có và business authorization.

Token Exchange không thay thế authorization của B. HTTP 200 từ STS không chứng minh người dùng có quyền xem tất cả đơn hàng.

## 3. Token Exchange khác các grants khác

| Grant / cơ chế | Đầu vào chính | Mục đích |
|---|---|---|
| Authorization Code + PKCE | Authorization code từ browser login | Lấy token theo authorization của người dùng |
| Client Credentials | Xác thực chính client | Token đại diện cho client/service |
| Refresh Token | Refresh token được AS cấp | Lấy access token mới theo authorization đã có |
| **Token Exchange** | **Subject token**, có thể thêm actor token | Yêu cầu STS phát token mới cho target/context được policy cho phép |
| JWT Bearer Grant | JWT assertion theo profile | Authorization dựa trên assertion được AS tin cậy |

Các nhầm lẫn thường gặp:

- Token Exchange **không phải** cách refresh access token cũ bằng `refresh_token`.
- Client Credentials token không thể tự thay cho token của một người dùng.
- OIDC Login xác thực End-User cho client, không mặc nhiên cấp quyền exchange sang mọi downstream APIs.
- Token Exchange có thể đổi access token sang access token, nhưng RFC còn diễn tả những token types khác khi các thành phần hỗ trợ.

### 3.1. Khi nào không cần Token Exchange?

Nếu API B được thiết kế để chấp nhận Token A, và token đó thực sự có đúng audience, scope, issuer cùng authorization policy, Service A có thể không cần exchange. Việc thêm STS roundtrip không có lợi nếu không thay đổi security boundary.

Ngược lại, việc nhiều APIs cùng chấp nhận một token có audience quá rộng có thể làm tăng hậu quả khi token bị lộ. Thiết kế token theo từng target thường giúp giới hạn quyền.

## 4. RFC 8693 là một OAuth2 extension grant

Grant identifier chính xác:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

Token Exchange được gửi đến Token Endpoint qua HTTP POST, với form body:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.net
Authorization: Basic BASE64_CLIENT_ID_COLON_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=SUBJECT_TOKEN_A
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=orders-api
&scope=orders.read
```

Các dòng body được tách ra cho dễ đọc; request thật phải form-encode đúng chuẩn.

### 4.1. Các tham số RFC 8693

| Tham số | Yêu cầu theo RFC | Ý nghĩa |
|---|---|---|
| `grant_type` | **Required** | Giá trị URN Token Exchange chính xác |
| `subject_token` | **Required** | Token đại diện subject mà client muốn exchange |
| `subject_token_type` | **Required** | URI xác định loại token đầu vào |
| `requested_token_type` | Optional | Loại token mong muốn |
| `resource` | Optional | URI tuyệt đối của target resource |
| `audience` | Optional | Tên logic của target service |
| `scope` | Optional | Quyền muốn được cấp tại target |
| `actor_token` | Optional | Token đại diện actor muốn hành động thay subject |
| `actor_token_type` | Required **nếu có actor_token**, không được gửi nếu không có actor token | Loại actor token |

**Optional theo RFC không có nghĩa optional đối với mọi provider.** Một AS có thể bắt buộc `audience`, `resource`, scope, actor token hoặc các tham số được tài liệu hóa khác theo chính sách triển khai.

### 4.2. Client authentication khác subject token

Trong request minh họa:

```text
Authorization: Basic ...
```

chứng minh danh tính **OAuth2 client** đang gọi STS.

Còn:

```text
subject_token=Token A
```

chứng minh thông tin/authorization liên quan đến **subject**.

Cả hai đều cần xử lý:

- Client credentials hợp lệ không có nghĩa client được exchange mọi subject token.
- Subject token hợp lệ không có nghĩa ai giữ token cũng được phép gọi STS để xin token khác.
- STS có thể dùng `client_secret_basic`, mTLS, `private_key_jwt` hoặc cơ chế đăng ký khác.
- STS cần kiểm tra issuer/trust, loại token và quyền client đối với target.

Một provider cho phép exchange với token bị đánh cắp mà không ràng buộc client và policy có thể mở đường cho token laundering.

---

## 5. `subject_token` và các loại token được chấp nhận

Token đầu vào có thể là OAuth2 access token, JWT assertion, OIDC ID Token hoặc security token khác, **nhưng chỉ nếu STS thật sự hỗ trợ token type đó**.

Một số URI token types trong RFC 8693:

```text
urn:ietf:params:oauth:token-type:access_token
urn:ietf:params:oauth:token-type:refresh_token
urn:ietf:params:oauth:token-type:id_token
urn:ietf:params:oauth:token-type:jwt
urn:ietf:params:oauth:token-type:saml2
```

### 5.1. `access_token` không luôn đồng nghĩa `jwt`

- `access_token` mô tả **mục đích OAuth2**.
- `jwt` mô tả một **biểu diễn cú pháp**.
- Một OAuth2 access token có thể được mã hóa dưới dạng JWT, nhưng provider vẫn yêu cầu `subject_token_type=access_token`.
- Một JWT từ issuer khác có thể được yêu cầu với `subject_token_type=jwt`.

Không đoán token type chỉ vì token string có ba phần cách nhau bằng dấu chấm.

### 5.2. Subject token là opaque token

Một opaque access token vẫn có thể exchange được nếu STS có khả năng xác thực nó thông qua storage hoặc token introspection và policy cho phép.

Nếu STS chỉ tin JWT có signature từ một danh sách issuers, opaque token dù hợp lệ ở Resource Server A vẫn có thể bị từ chối.

### 5.3. Có được dùng ID Token làm subject token?

RFC cung cấp URI token type cho ID Token, nhưng OIDC ID Token vốn phục vụ việc client xác minh Authentication của End-User, không phải API access token.

Không lấy `OidcUser.getIdToken()` và dán vào `subject_token` trừ khi provider công bố rõ hỗ trợ **ID Token exchange** cùng trust policy tương ứng. Khi STS yêu cầu subject **access token**, phải lấy đúng access token của user/client được quản lý.

### 5.4. Token đầu vào phải còn hợp lệ

STS có thể kiểm tra:

- Signature/MAC hoặc introspection status.
- Issuer.
- Audience hoặc resource mà token được cấp.
- Expiration/not-before.
- Token type.
- Subject identity và tenant.
- Proof-of-possession/sender constraint nếu áp dụng.
- Client permission và delegation policy.

Client không thể tự bỏ validation phía STS chỉ bằng việc đưa token vào form body hợp lệ.

## 6. `resource`, `audience` và `scope`

### 6.1. `resource`

Ví dụ:

```text
resource=https://orders.example.net
```

Theo RFC, `resource` là URI tuyệt đối mô tả target resource/service. Không được chứa fragment. Provider có thể chấp nhận nhiều `resource` parameters nhưng không bắt buộc cấp token cho mọi target được yêu cầu.

### 6.2. `audience`

Ví dụ:

```text
audience=orders-api
```

Là tên logic của target service mà cả STS và client hiểu.

Có provider yêu cầu URL, có provider dùng API identifier hoặc client ID. Không có quy tắc chung rằng `audience` luôn bằng URL REST API.

### 6.3. `scope`

Ví dụ:

```text
scope=orders.read orders.export
```

Scope là chuỗi phân cách bằng dấu cách theo OAuth2, nhưng **ngữ nghĩa quyền** do target API và policy AS quy định.

### 6.4. Không yêu cầu target quá rộng

Ví dụ:

```text
audience=orders-api
audience=finance-api
scope=orders.read finance.write
```

Một yêu cầu nhiều audiences kết hợp nhiều scopes có thể khiến STS phải phát token quá rộng; RFC 8693 định nghĩa lỗi `invalid_target` để phản ánh vấn đề target.

**Nguyên tắc:** yêu cầu scopes tối thiểu và thường là token riêng cho từng Resource Server. Tham số `resource` của Token Exchange cũng không có nghĩa provider tự hỗ trợ toàn bộ cơ chế Resource Indicators của RFC 8707.

## 7. Impersonation và delegation

Hai khái niệm đều có thể xuất hiện trong Token Exchange, nhưng ý nghĩa khác nhau.

### 7.1. Impersonation

Service A yêu cầu token cho Orders API với subject Alice:

```text
Subject: Alice
Token đầu ra: quyền thể hiện Alice ở target API
```

Resource Server có thể thấy hành động như do Alice thực hiện trong phạm vi token được cấp. Chỉ hợp lệ nếu STS cho phép client A impersonate Alice.

### 7.2. Delegation

Service A hành động thay Alice **với danh tính actor riêng**:

```text
Subject = Alice
Actor = Service A
Target = Orders API
```

STS có thể phát JWT chứa actor claim:

```json
{
  "iss": "https://id.example.net",
  "sub": "alice-901",
  "aud": "orders-api",
  "scope": "orders.read",
  "act": {
    "sub": "service-a"
  }
}
```

Trong đó:

- `sub` đại diện subject.
- `act` đại diện actor.
- Resource Server có thể áp chính sách và audit dựa trên cả subject và actor.

Không phải mọi provider đều tạo `act` khi có actor token; format và policy nằm trong implementation và tài liệu STS.

### 7.3. `may_act`

`may_act` là claim có thể được STS sử dụng để xác định một actor có được phép hành động thay subject hay không.

Không được suy:

```text
Input JWT có may_act
    => mọi actor có thể exchange
```

STS vẫn phải xác minh chữ ký, trust, quyền và target. Client cũng không được tự thêm `may_act` vào JWT chưa được issuer tin cậy ký rồi đòi quyền.

### 7.4. Khi nào gửi `actor_token`?

Chỉ khi provider hỗ trợ actor token type và delegation semantics tương ứng.

Không dùng raw string như client ID hay client secret để thay một security token của actor; nếu gửi `actor_token_type=jwt` thì actor token phải thật sự là một JWT được STS chấp nhận.

---

## 8. Response của Token Exchange

Ví dụ thành công khi STS cấp một **Bearer access token**:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
```

```json
{
  "access_token": "TOKEN_FOR_ORDERS_API",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

| Trường | RFC | Ý nghĩa |
|---|---|---|
| `access_token` | Required | Token được phát hành; tên field do lịch sử OAuth2 |
| `issued_token_type` | **Required** | Loại security token được phát hành |
| `token_type` | **Required** | Cách sử dụng token, ví dụ Bearer |
| `expires_in` | Recommended | Lifetime tính bằng giây |
| `scope` | Optional nếu giống requested scope, required nếu khác | Quyền thực cấp |
| `refresh_token` | Optional | Không mặc định được cấp |

### 8.1. `issued_token_type` và `token_type` khác nhau

Ví dụ:

```text
issued_token_type = urn:ietf:params:oauth:token-type:access_token
token_type        = Bearer
```

Field đầu nói **loại token về mặt security token representation/purpose**. Field sau nói **cách sử dụng token**.

Một access token có wire format JWT vẫn có thể được khai báo bằng `issued_token_type=access_token`.

### 8.2. Không phải output token nào cũng là API Bearer token

RFC cho phép một số exchange phát security token khác OAuth access token. Khi đó `token_type` có thể là `N_A`.

Vì vậy không tự áp WebClient Bearer filter cho mọi token response. Xác minh output có thật sự là OAuth access token phù hợp để gửi tới Resource Server.

### 8.3. Refresh token là tùy chọn

STS thường cấp access token ngắn hạn cho target, không nhất thiết trả refresh token. Một output token có `expires_in=600` không mặc nhiên được refresh với `grant_type=refresh_token`.

Nếu không có refresh token, ứng dụng có thể cần Token Exchange lần nữa với subject token còn hợp lệ hoặc phải lấy subject authorization mới. Đây là quyết định lifecycle theo provider.

## 9. Token Exchange có làm token đầu vào mất hiệu lực không?

**Không mặc định.** Theo RFC 8693, nếu token type và provider không có one-time-use semantics, việc exchange không tự revoke subject token hoặc actor token.

Ví dụ:

```text
Token A còn hạn 30 phút
    |
    +-- exchange -> Token B1
    +-- exchange -> Token B2
```

Các tokens có thể còn hiệu lực đồng thời nếu policy cho phép.

Ngược lại, Token B không mặc nhiên bị thu hồi khi Token A bị revoke. STS có thể thiết kế revocation propagation, nhưng đó là tính chất triển khai, không phải guarantee chung.

Các câu hỏi lifecycle cần xác nhận:

- Token B sống tối đa bao lâu?
- Expiry của B có bị giới hạn bởi A?
- Logout và disconnect có revoke B không?
- Có thể introspect/revoke B không?
- Có cần gọi STS lại khi source token hoặc actor thay đổi?
- B có bị ràng buộc với session hoặc sender-constrained key nào không?

---

## 10. Provider phải hỗ trợ những gì?

Một provider hỗ trợ OIDC Login, OAuth2 Authorization Code, JWT hoặc Resource Server **chưa chắc** hỗ trợ RFC 8693.

Để Spring OAuth2 Client có thể Token Exchange thành công, STS cần:

1. **Token Endpoint** thực sự chấp nhận extension grant URN.
2. **Client registration** được bật grant đó.
3. **Client authentication** đúng phương thức được đăng ký.
4. **Subject token type** được chấp nhận.
5. **Source issuer/trust relationship** hợp lệ.
6. **Input token validation** hoạt động theo token format.
7. **Audience/resource** thuộc target allowlist.
8. **Scope mapping** cấp quyền đúng Resource Server.
9. **Delegation/impersonation policy** được định nghĩa.
10. **Actor token handling** nếu flow dùng actor.
11. **Response theo RFC** với các required fields.
12. **Output token issuer/audience** được target Resource Server tin cậy.
13. **Refresh/revocation/expiry policy** đủ rõ.
14. **Tenant/realm-specific permissions** được bật chính xác.
15. **TLS, key/certificate trust** và network transport phù hợp.

### 10.1. Bảng tương thích cần kiểm tra

| Câu hỏi | Cần xác minh ở đâu? | Triệu chứng khi thiếu |
|---|---|---|
| AS hỗ trợ `token-exchange` URN? | Provider docs/token endpoint | `unsupported_grant_type` |
| Client được dùng grant? | Client permissions / AS policy | `unauthorized_client` |
| Client auth method phù hợp? | Registration/provider config | `invalid_client` |
| Subject token type được nhận? | STS trust/token-type docs | `invalid_request` |
| Subject issuer được tin? | Token exchange trust/federation | Token bị từ chối |
| Audience/resource hợp lệ? | Allowed target identifiers | `invalid_target` |
| Scope hợp lệ cho target? | Scope mapping | `invalid_scope` hoặc 403 |
| Actor token được hỗ trợ? | Delegation policy | `invalid_request` |
| Có required response fields? | STS implementation | Parse error |
| Target tin issuer của B? | API JWT/introspection config | API 401 |
| Có token revocation propagation? | Provider lifecycle docs | Token B tồn tại ngoài ý muốn |
| Token B có sender constraint? | STS/API docs | API từ chối proof |
| Tenant/realm đã enable? | Tenant settings | Grant lỗi dù product có hỗ trợ |

### 10.2. Metadata và `grant_types_supported`

Authorization Server Metadata / OIDC Discovery có thể công bố `grant_types_supported`. Nếu chứa Token Exchange URN, đó là tín hiệu hữu ích, **không chứng minh** client cụ thể có quyền exchange token cho mọi target.

Nếu metadata thiếu URN, cần đối chiếu tài liệu triển khai và Token Endpoint của chính provider; không kết luận theo tên product.

**Kết luận:** phải kiểm tra cả **server capability**, **client permission**, **token trust** và **target authorization**.

## 11. RFC 8693 khác proprietary On-Behalf-Of như thế nào?

Một số Identity Providers gọi khả năng tương tự là:

- On-Behalf-Of (OBO).
- Audience exchange.
- Token swap.
- Delegation hoặc impersonation.
- Downstream access token issuance.

Nhưng tên feature **không bảo đảm tuân thủ RFC 8693**.

Ví dụ request RFC 8693:

```text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=...
subject_token_type=urn:ietf:params:oauth:token-type:access_token
audience=orders-api
```

Một vendor-specific OBO có thể dùng:

```text
grant_type=<vendor-grant>
assertion=<source-token>
requested_token_use=<vendor-value>
scope=<vendor-scope>
```

Sự khác biệt có thể nằm ở grant URN, tham số, client authentication, audience model, consent, response type và error semantics.

**Không thay tên grant trong YAML rồi mong built-in Token Exchange provider xử lý mọi proprietary OBO flow.** Nếu provider không có RFC 8693 endpoint, cần SDK hoặc extension đúng vendor contract.

### 11.1. Provider cùng hỗ trợ RFC vẫn khác policy

Ngay cả cùng RFC 8693, hai STSs có thể không giống nhau ở:

- `subject_token_type` có thể là `access_token` hoặc `jwt`.
- Bắt buộc `audience` hay `resource`.
- Có nhận opaque token qua introspection không.
- Actor token có bắt buộc không.
- Có phát output claim `act` không.
- Có support cross-issuer/cross-tenant không.
- Có phát refresh token không.
- Scope mapping và revocation propagation thế nào.

RFC mang lại cú pháp chung; **provider compatibility** vẫn phải được đánh giá ở từng deployment.

---

## 12. Spring Security hỗ trợ Token Exchange từ phiên bản nào?

Spring Security có class:

```java
org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider
```

Class xuất hiện từ **Spring Security 6.3**.

Trong Servlet stack, HTTP token response client dựa trên `RestClient`:

```java
org.springframework.security.oauth2.client.endpoint.RestClientTokenExchangeTokenResponseClient
```

xuất hiện từ **Spring Security 6.4**.

Với WebFlux/reactive:

```java
org.springframework.security.oauth2.client.TokenExchangeReactiveOAuth2AuthorizedClientProvider
org.springframework.security.oauth2.client.endpoint.WebClientReactiveTokenExchangeTokenResponseClient
```

Cấu hình auto-detection beans và API customization phụ thuộc Spring Security/Boot version. Không trộn dependencies giữa các dòng versions hoặc dùng ví dụ 7.x với một project 6.2 mà không đối chiếu API.

### 12.1. Chỉ khai báo grant type chưa đủ

Cấu hình:

```yaml
authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
```

mô tả grant của registration nhưng không bảo đảm manager mặc định đã có `TokenExchangeOAuth2AuthorizedClientProvider`.

Cần enable provider hoặc cấu hình authorized client manager tương ứng, tùy phiên bản và application auto-configuration.

## 13. Ví dụ Spring Boot: Service A vừa là Resource Server vừa là OAuth2 Client

Giả sử:

```text
Service A:
    https://service-a.example.net
    nhận JWT Token A, aud=service-a

STS:
    https://id.example.net/oauth2/token
    chấp nhận Token Exchange của client service-a-exchange

Orders API:
    https://orders.example.net
    yêu cầu aud=orders-api, scope=orders.read
```

### 13.1. Dependencies cho Spring Boot 3.x Servlet

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Spring Boot 4.x có một số starter names mới; cần dùng BOM tương thích với framework version. Không tự bỏ các security dependencies nếu Service A cần vừa validate JWT inbound vừa đổi token outbound.

### 13.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.net

      client:
        registration:
          orders-exchange:
            provider: enterprise-sts
            client-id: ${ORDERS_EXCHANGE_CLIENT_ID}
            client-secret: ${ORDERS_EXCHANGE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
            scope:
              - orders.read

        provider:
          enterprise-sts:
            token-uri: https://id.example.net/oauth2/token
```

Giải thích:

- Resource Server JWT config xác minh issuer/token inbound. Application vẫn phải kiểm soát **audience** và authorization của Service A.
- Registration `orders-exchange` là outbound OAuth2 client dùng Token Exchange Grant.
- `token-uri` là STS Token Endpoint, không phải Orders API URL.
- `scope=orders.read` là ví dụ theo target policy.
- `client-id` và `client-secret` là credentials của **exchange client**, không phải credentials của End-User.

Nếu provider yêu cầu `private_key_jwt`, mTLS hoặc phương thức khác thay secret Basic, phải cấu hình client authentication đúng hợp đồng đó.

### 13.3. Registration Token Exchange không phải OAuth2 Login

Bạn có thể có các registrations riêng:

```text
corporate-login    -> authorization_code
orders-exchange    -> token-exchange
inventory-service  -> client_credentials
```

Registration dành cho Token Exchange không tự cung cấp browser redirect hoặc OIDC UserInfo. Nó chỉ mô tả cách trao đổi token.

## 14. SecurityFilterChain xác thực token đầu vào

Service A nhận Bearer JWT từ caller:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

Đây chỉ là cấu hình cơ bản. Production cần validate audience của Service A, claims/authorities, tenant và business authorization. Không mặc định JWT được issuer ký hợp lệ thì caller có mọi quyền.

**Không tự dựng một `JwtAuthenticationToken` từ JWT chưa được verify** rồi cho nó trở thành principal đáng tin.

---

## 15. TokenExchangeOAuth2AuthorizedClientProvider

Provider chịu trách nhiệm xử lý grant Token Exchange trong `OAuth2AuthorizedClientManager`:

```java
org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider
```

Interface:

```java
OAuth2AuthorizedClientProvider
```

Nó có thể:

1. Nhận `OAuth2AuthorizationContext`.
2. Kiểm tra client registration có Token Exchange grant không.
3. Xác định authorized client hiện có và expiry.
4. Resolve subject token và optional actor token.
5. Gọi token response client tới STS.
6. Trả `OAuth2AuthorizedClient` chứa token được cấp.
7. Trả `null` nếu không hỗ trợ hoặc chưa cần reauthorize theo contract.

Lỗi Token Endpoint thường được chuyển thành OAuth2 exception, không phải tín hiệu tự chuyển sang một grant khác.

### 15.1. Provider bean

Ví dụ cho Spring Security 6.4+:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint.RestClientTokenExchangeTokenResponseClient;

@Configuration
class ExchangeProviderConfiguration {

    @Bean
    TokenExchangeOAuth2AuthorizedClientProvider tokenExchangeProvider() {
        RestClientTokenExchangeTokenResponseClient responseClient =
            new RestClientTokenExchangeTokenResponseClient();

        TokenExchangeOAuth2AuthorizedClientProvider provider =
            new TokenExchangeOAuth2AuthorizedClientProvider();

        provider.setAccessTokenResponseClient(responseClient);
        return provider;
    }
}
```

Đoạn mã là wiring rõ ràng, không bắt buộc tạo bean này nếu auto-configuration ở phiên bản đang dùng đã đáp ứng yêu cầu. Nếu app có nhiều providers/managers, chọn beans bằng qualifier.

### 15.2. Tạo manager cho Servlet

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
class ExchangeManagerConfiguration {

    @Bean("tokenExchangeManager")
    OAuth2AuthorizedClientManager tokenExchangeManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients,
            TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider) {

        OAuth2AuthorizedClientProvider providers =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .provider(exchangeProvider)
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );

        manager.setAuthorizedClientProvider(providers);
        return manager;
    }
}
```

Manager trên chỉ có Token Exchange provider. Nếu app cần Authorization Code, Refresh Token hoặc Client Credentials cho registrations khác, tạo provider chain tương ứng theo chính sách ứng dụng, không tự bật mọi grants.

**Manager/Provider chỉ thực hiện OAuth2 Client workflow; STS vẫn là bên quyết định quyền cấp token.**

## 16. Subject token mặc định trong Spring Security

Mặc định, `TokenExchangeOAuth2AuthorizedClientProvider` cố lấy subject token từ:

```java
OAuth2AuthorizationContext
    .getPrincipal()
    .getPrincipal()
```

khi principal object biểu diễn `OAuth2Token` thích hợp.

Một Spring Resource Server nhận JWT thường tạo:

```java
JwtAuthenticationToken
```

với principal là:

```java
Jwt
```

Do đó `JwtAuthenticationToken` là ví dụ phù hợp cho default resolver.

### 16.1. Gọi manager từ controller

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ExchangeController {

    private final OAuth2AuthorizedClientManager manager;

    ExchangeController(
            @Qualifier("tokenExchangeManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @GetMapping("/api/exchange-status")
    ResponseEntity<String> exchange(JwtAuthenticationToken authentication) {

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("orders-exchange")
                .principal(authentication)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            return ResponseEntity.badRequest()
                .body("No authorized client available");
        }

        // Chỉ trả metadata vô hại; không trả token value.
        return ResponseEntity.ok(
            "Authorized via " +
            client.getClientRegistration().getRegistrationId()
        );
    }
}
```

Controller này chỉ minh họa đường đi của authenticated principal vào manager. Với production, không mở một endpoint exchange tùy ý cho mọi caller; áp business authorization trước khi yêu cầu target token. Lỗi OAuth2 cần được xử lý phù hợp bằng exception handling.

### 16.2. Khi principal là OidcUser

Một ứng dụng OAuth2 Login/OIDC Client thường có:

```text
Authentication = OAuth2AuthenticationToken
Principal      = OidcUser
AuthorizedClient = registration + access token + refresh token (nếu có)
```

`OidcUser` không tự là raw OAuth2 subject token mà default resolver có thể dùng.

Nếu STS yêu cầu **OAuth access token** làm input, cần truy xuất đúng access token từ authorized client của user theo registration và principal đã được xác minh.

Không chọn ID Token chỉ vì `OidcUser.getIdToken()` dễ gọi.

### 16.3. `setSubjectTokenResolver(...)`

Spring Security hỗ trợ:

```java
provider.setSubjectTokenResolver(context -> {
    // Trả về trusted OAuth2Token hoặc null.
    return null;
});
```

Ví dụ custom resolver chỉ nhận JWT Resource Server principal:

```java
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

TokenExchangeOAuth2AuthorizedClientProvider provider =
    new TokenExchangeOAuth2AuthorizedClientProvider();

provider.setSubjectTokenResolver(context -> {
    if (context.getPrincipal() instanceof JwtAuthenticationToken auth) {
        return auth.getToken();
    }
    return null;
});
```

Đây là ví dụ giới hạn nguồn subject token, không phải cách bỏ xác minh JWT inbound. Nếu cần lấy token từ `OAuth2AuthorizedClientService`, phải kiểm tra ownership, tenant và source registration.

### 16.4. Không nhận subject token từ query parameter

Một endpoint kiểu:

```text
GET /exchange?subject_token=...&audience=...
```

không an toàn nếu backend dùng quyền client mạnh để exchange token cho bất kỳ subject/target người dùng yêu cầu.

Subject token và target phải đến từ **security/business context đã được kiểm soát**, không từ dữ liệu tùy ý của caller.

## 17. Actor token không được resolve mặc định

`TokenExchangeOAuth2AuthorizedClientProvider` có hook:

```java
setActorTokenResolver(...)
```

Nhưng **actor token không được tự resolve mặc định**.

Nếu STS yêu cầu delegation với actor:

1. Xác định actor là ai theo policy.
2. Có actor security token hợp lệ từ issuer được STS tin cậy.
3. Cấu hình resolver để đưa token đó vào grant.
4. Kiểm tra actor token type và required target/scope.
5. Kiểm tra output token chứa actor claims khi STS thực sự phát delegation token.

Không đưa client ID string vào `actor_token` rồi khai báo đó là JWT. Không tự thêm `act` vào JWT đã ký.

### 17.1. Resolver khác client authentication

Actor token không nhất thiết là client assertion dùng cho client authentication. Trong một số chính sách, client và actor liên quan, nhưng mỗi token có **vai trò giao thức khác nhau**.

Không lấy `client_secret` làm actor token hay coi HTTP Basic header thay cho authorization của actor.

---

## 18. Tùy chỉnh audience bằng RestClientTokenExchangeTokenResponseClient

STS có thể yêu cầu:

```text
audience=orders-api
```

Spring Security 6.4+ cho phép thêm tham số bằng converter:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.RestClientTokenExchangeTokenResponseClient;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

@Configuration
class ExchangeHttpConfiguration {

    @Bean
    RestClientTokenExchangeTokenResponseClient exchangeResponseClient() {
        RestClientTokenExchangeTokenResponseClient responseClient =
            new RestClientTokenExchangeTokenResponseClient();

        responseClient.addParametersConverter(grantRequest -> {
            MultiValueMap<String, String> params =
                new LinkedMultiValueMap<>();

            if ("orders-exchange".equals(
                    grantRequest.getClientRegistration()
                        .getRegistrationId())) {
                params.add(
                    OAuth2ParameterNames.AUDIENCE,
                    "orders-api"
                );
            }

            return params;
        });

        return responseClient;
    }
}
```

Gắn response client này vào provider:

```java
@Bean
TokenExchangeOAuth2AuthorizedClientProvider tokenExchangeProvider(
        RestClientTokenExchangeTokenResponseClient responseClient) {

    TokenExchangeOAuth2AuthorizedClientProvider provider =
        new TokenExchangeOAuth2AuthorizedClientProvider();

    provider.setAccessTokenResponseClient(responseClient);
    return provider;
}
```

**Lưu ý:** Đoạn bean `tokenExchangeProvider` ở đây **thay thế** bean cùng tên ở mục trước, không đặt cả hai cùng lúc không có chủ đích.

### 18.1. `addParametersConverter` phù hợp khi nào?

Khi chỉ cần **bổ sung** audience/resource hay provider extension theo registration.

Các APIs thường thấy:

| API | Ý nghĩa |
|---|---|
| `addParametersConverter(...)` | Thêm parameters vào request chuẩn |
| `setParametersConverter(...)` | Tùy chỉnh/override một số parameters theo contract |
| `setParametersCustomizer(...)` | Tùy chỉnh sâu parameters cuối cùng, gồm khả năng loại default params |

Không nên thay thế toàn bộ form body chỉ để thêm một audience. Việc vô tình xóa `grant_type`, `subject_token` hoặc `subject_token_type` làm request không còn hợp lệ.

### 18.2. Provider yêu cầu resource URI

Ví dụ:

```java
params.add("resource", "https://orders.example.net");
```

Dùng resource **được cấu hình và cho phép**, không lấy từ URL tùy ý của browser. Khi code dùng một URI từ user nhập để xin token và sau đó gửi token tới URI ấy, có thể dẫn đến SSRF/token leakage.

### 18.3. Provider yêu cầu nhiều audience

RFC cho phép nhiều values, nhưng việc cấp token sử dụng được tại nhiều audiences phụ thuộc STS policy. Thường tách token theo API để tránh scope/target quá rộng.

## 19. HTTP transport và lỗi Token Endpoint

Spring có thể dùng `RestClient` cho Token Exchange request. Các yếu tố cần tùy chỉnh:

- Connect/read/response timeout.
- Proxy.
- TLS truststore.
- Client authentication.
- Form HTTP message converters.
- OAuth2 token response JSON converters.
- OAuth2 error response handling.

`RestClientTokenExchangeTokenResponseClient.setRestClient(...)` cho phép thay HTTP transport.

Nếu tạo custom RestClient, phải giữ converters cho form và token response cùng error handler phù hợp. Không thay bằng một bare HTTP POST parser tự chế rồi bỏ qua OAuth2 errors.

### 19.1. Không tắt TLS validation

Token Exchange request chứa credentials rất nhạy cảm:

```text
subject_token
actor_token
client_secret
client_assertion
Authorization header
```

Nếu gặp PKIX/TLS failure, sửa truststore/CA/hostname/proxy. Không dùng trust-all hoặc bỏ hostname verification.

### 19.2. Retry phải theo semantics

Một timeout không chứng minh AS chưa xử lý request. Không retry vô hạn, đặc biệt nếu subject token có one-time-use semantics hoặc provider thực thi replay detection.

Phân biệt:

- `invalid_client`, `unauthorized_client`, `invalid_target`: thường không sửa bằng retry.
- HTTP 503/timeout: có thể retry có giới hạn/backoff theo provider contract.
- `invalid_request`: cần kiểm tra subject token, type và policy, không phải cứ đổi HTTP client.

---

## 20. Dùng Token B gọi Orders API

Sau khi manager trả:

```java
OAuth2AuthorizedClient authorized =
    manager.authorize(request);
```

token đầu ra được truy cập qua:

```java
authorized.getAccessToken().getTokenValue()
```

Ví dụ gọi `RestClient`:

```java
import org.springframework.web.client.RestClient;

public String fetchOrders(
        RestClient ordersRestClient,
        OAuth2AuthorizedClient authorized) {

    return ordersRestClient.get()
        .uri("/v1/orders")
        .headers(headers -> headers.setBearerAuth(
            authorized.getAccessToken().getTokenValue()
        ))
        .retrieve()
        .body(String.class);
}
```

Dành riêng `ordersRestClient` cho Orders API với `baseUrl` cố định và kiểm soát redirects. Không chuyển Token B sang API khác chỉ vì token đang còn hạn.

### 20.1. Resource Server B phải validate token

Token B phải phù hợp:

- `iss`: issuer đáng tin.
- `aud`: đúng Orders API.
- `exp`/`nbf`: còn hiệu lực.
- Signature/introspection.
- Scope và claims liên quan.
- Actor/delegation/tenant policy nếu có.

Đổi token thành công không tự cấp toàn bộ business permissions.

## 21. AuthorizedClientManager và caching Token Exchange

`OAuth2AuthorizedClientManager` có thể dùng authorized client repository/service để lưu token B sau exchange.

Khóa thường là:

```text
(clientRegistrationId, principalName)
```

Ví dụ:

```text
("orders-exchange", "alice-901")
    -> Token B
```

### 21.1. Cache key có thể chưa đủ

Token Exchange có thể phụ thuộc thêm:

- Token A được gửi làm `subject_token` (issuer, token ID, session).
- Actor token.
- Tenant.
- Target audience/resource.
- Scopes theo lần request.
- Authentication strength/consent.

Nếu cache key chỉ là `(registrationId, principalName)`, một authorized client B **còn hạn** có thể được reuse cho một request có **subject token/actor/target đã thay đổi**.

Ví dụ:

```text
T0: Alice Token A1 -> exchange -> B1, lưu theo "orders-exchange", "alice"
T1: Alice đăng nhập lại nhận Token A2 với claim/permission khác
T2: Manager thấy B1 còn hạn và có thể reuse B1
```

Nếu nghiệp vụ yêu cầu Token B luôn gắn với source token **của request hiện tại**, cache đó có thể không đúng chính sách.

### 21.2. Các lựa chọn thiết kế

- Registration riêng theo target audience/scope profile.
- Stable principal có namespace issuer/tenant.
- Custom storage key bao gồm source authorization context khi cần.
- Explicit re-authorization khi subject token thay đổi.
- Chỉ cache Token B trong phạm vi request/session nếu policy yêu cầu.
- Không lưu Token B của Alice dưới principal service chung.
- Thiết kế invalidation khi logout/revoke/disconnect.

Không xem việc provider nhận `OAuth2AuthorizedClient` còn hạn là bằng chứng Token A vẫn hợp lệ.

### 21.3. Token lifecycle không đồng bộ mặc định

RFC không bảo đảm revoke Token A tự revoke Token B. Vì vậy nếu user disconnect, STS/Resource Server hoặc application có thể cần explicit revocation/remove.

Các questions cần trả lời:

1. Token B tồn tại sau user logout không?
2. Subject token A bị revoke thì B còn dùng được không?
3. Token B có refresh token không?
4. Khi B hết hạn, có thể exchange lại A không?
5. Khi A hết hạn, phải làm authorization mới như thế nào?
6. Với multi-node, ai phối hợp tránh duplicate exchange requests?

## 22. WebFlux/reactive counterpart

Trong Spring WebFlux, dùng:

```java
TokenExchangeReactiveOAuth2AuthorizedClientProvider
WebClientReactiveTokenExchangeTokenResponseClient
```

Các contracts reactive trả `Mono<OAuth2AuthorizedClient>` thay vì `OAuth2AuthorizedClient` đồng bộ.

Ví dụ provider:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.TokenExchangeReactiveOAuth2AuthorizedClientProvider;

@Configuration
class ReactiveExchangeConfiguration {

    @Bean
    TokenExchangeReactiveOAuth2AuthorizedClientProvider exchangeProvider() {
        return new TokenExchangeReactiveOAuth2AuthorizedClientProvider();
    }
}
```

Gắn provider vào `ReactiveOAuth2AuthorizedClientManager` và reactive repositories/services phù hợp. Trong WebFlux server, manager thường dùng `ReactiveClientRegistrationRepository` và `ServerOAuth2AuthorizedClientRepository`.

### 22.1. Reactive resolver trả Mono

`setSubjectTokenResolver` và `setActorTokenResolver` của reactive provider nhận function trả `Mono<OAuth2Token>`, không phải `OAuth2Token` đồng bộ.

Không dùng `.block()` trên Reactor event loop chỉ để lấy token; kết hợp các reactive publishers.

### 22.2. SecurityContext chưa phải subject token

`ReactiveSecurityContextHolder` mang authentication theo Reactor Context, nhưng không tự làm Authentication trở thành một OAuth2Token mà STS chấp nhận. Vẫn phải chọn đúng source token, client registration và target.

---

## 23. `invalid_request`, `invalid_target` và những lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| `unsupported_grant_type` | AS không hỗ trợ/bật RFC 8693 | Kiểm tra Token Endpoint, version và tenant |
| `unauthorized_client` | Client không được phép Token Exchange | Grant/client permissions |
| `invalid_client` | Secret, mTLS hoặc JWT client assertion sai | Client authentication |
| `invalid_request` | Subject token/type thiếu, invalid hoặc policy không chấp nhận | Request body, trust, issuer, expiry |
| `invalid_target` | Audience/resource không được hỗ trợ/cho phép | Target identifiers và allowed audiences |
| `invalid_scope` | Scope không hợp lệ cho client/target | Scope mapping |
| `subject_token` không tìm thấy | Principal không phải OAuth2Token | Custom subject resolver đúng nguồn |
| Actor token không được gửi | Chưa có actor resolver | Delegation config và source actor |
| Response parse lỗi | Thiếu `issued_token_type`, sai `token_type` | RFC response contract |
| Token B thiếu audience đúng | Provider ignore/override target | Request params và STS policy |
| Orders API 401 | `iss`/`aud`/signature/expiry sai | Resource Server validation |
| Orders API 403 | Scope/role/ownership thiếu | Scope mapping và business policy |
| STS timeout | Network/proxy/TLS/AS outage | HTTP transport và retry có giới hạn |
| Token B của user khác được reuse | Cache principal/tenant sai | Storage key và authorization |
| `OAuth2AuthorizedClientManager` không có provider phù hợp | Chưa enable Token Exchange | Provider builder/bean wiring |
| Có provider nhưng vẫn lỗi | AS policy không hỗ trợ client/source/target | Interoperability contract |

### 23.1. `invalid_request` không chỉ là thiếu field

RFC 8693 cho phép `invalid_request` khi subject hoặc actor token không hợp lệ hay không được chấp nhận theo policy. Một form body có đủ required parameters vẫn có thể bị từ chối.

### 23.2. `invalid_target` khác `invalid_scope`

`invalid_target` liên quan audience/resource đích. `invalid_scope` liên quan phạm vi quyền yêu cầu.

Một scope đúng cho Orders API có thể không hợp lệ tại Billing API. Khi lỗi, kiểm tra target + scope + client permission cùng nhau.

### 23.3. STS HTTP 200 nhưng API 401

Đây có thể là khác biệt giữa issuer/audience mà STS cấp và API B đang kiểm tra. Không tiếp tục xin Token B mới vô hạn trước khi xác minh cấu hình Resource Server.

## 24. Dùng cURL để xác minh khả năng tương thích

Trước khi viết logic Spring phức tạp, có thể dùng test client kiểm tra Token Endpoint trong môi trường development:

```bash
curl --request POST "https://id.example.net/oauth2/token" \
  --user "$EXCHANGE_CLIENT_ID:$EXCHANGE_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
  --data-urlencode "subject_token=$SUBJECT_ACCESS_TOKEN" \
  --data-urlencode "subject_token_type=urn:ietf:params:oauth:token-type:access_token" \
  --data-urlencode "requested_token_type=urn:ietf:params:oauth:token-type:access_token" \
  --data-urlencode "audience=orders-api" \
  --data-urlencode "scope=orders.read"
```

Trong thực tế, command-line arguments, terminal history, process listings và CI logs có thể làm lộ credentials. Chỉ sử dụng fake tokens/test secrets trong ví dụ, hoặc chọn cơ chế truyền secrets được hạ tầng bảo vệ.

### 24.1. Kiểm tra response

- HTTP status.
- `access_token`.
- `issued_token_type` đúng.
- `token_type` sử dụng được.
- `expires_in` hợp lý.
- Scope thực cấp.
- Target API có chấp nhận token không.
- Token có bị cấp scope/audience quá rộng không.

### 24.2. Negative tests quan trọng

1. Thiếu subject token.
2. Sai subject token type.
3. Subject token expired.
4. Subject token từ issuer chưa được trust.
5. Client không có quyền Token Exchange.
6. Client xác thực sai.
7. Audience ngoài allowlist.
8. Scope không được cấp.
9. Actor token invalid.
10. Cross-tenant token không được phép.
11. Token output có audience sai.
12. Response bỏ field required.
13. Revocation hoặc logout behavior.
14. Token exchange liên tiếp/one-time-use behavior.

Đây mới là bằng chứng tương thích, không chỉ việc Spring application khởi động thành công.

## 25. Kiểm thử trong Spring Security

### 25.1. Client registration test

Kiểm tra:

```text
registrationId = orders-exchange
authorizationGrantType = urn:ietf:params:oauth:grant-type:token-exchange
tokenUri = correct STS
clientAuthenticationMethod = expected method
```

Dùng `ClientRegistrationRepository` tại unit test, không cần gọi network cho cấu hình tĩnh.

### 25.2. Subject resolver test

Tạo JWT test hoặc mock SecurityContext để bảo đảm resolver lấy đúng `OAuth2Token` từ principal đã được xác thực. Không dùng test giả tạo một JWT unverified mà khẳng định Resource Server thật đã validate signature.

### 25.3. Token HTTP request test

Mock Token Endpoint, kiểm tra:

```text
grant_type
subject_token
subject_token_type
requested_token_type nếu cần
audience/resource
scope
client authentication
```

Không ghi raw tokens vào logs; dùng fake values.

### 25.4. Response test

Mock:

```json
{
  "access_token": "fake-orders-token",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
```

Xác minh token được lưu vào đúng registration/principal và sử dụng cho API B đúng kỳ vọng.

### 25.5. Contract test với provider thật

Mock `OAuth2AuthorizedClientManager` luôn trả fake token **không chứng minh** provider có RFC 8693 compatibility.

Cần môi trường STS thử nghiệm có grant/client policy thật để xác minh:

- Source token trust.
- Target allowlist.
- Delegation/actor policy.
- Output issuer/audience.
- Token expiry/revocation.
- Vendor-specific requirements.

---

## 26. Bảo mật end-to-end

### 26.1. Ngăn confused deputy

Service A có client credentials mạnh. Nếu nó nhận audience/token từ người dùng rồi exchange tùy ý, Service A có thể biến thành một **confused deputy**.

Phòng tránh:

- Không expose endpoint cho caller tùy chọn mọi audience.
- Validate inbound authentication.
- Chỉ cho phép target đã được business policy xác định.
- Giới hạn quyền OAuth2 client ở STS.
- Không bypass user/tenant authorization.
- Audit target/registration với identifiers đã được bảo vệ.

### 26.2. Không log credentials

Tránh ghi:

```text
subject_token
actor_token
access_token
refresh_token
client_secret
client_assertion
Authorization header
ID Token raw value
```

Có thể ghi metadata:

```text
registrationId=orders-exchange
target=orders-api
event=token_exchange
result=success|invalid_target|invalid_request
latencyMs=...
```

Nếu principal information là dữ liệu cá nhân, cần pseudonymization và hạn chế high-cardinality metrics labels.

### 26.3. Không gửi Token B đến host tùy ý

Khi sử dụng token B tại Orders API, kiểm soát base URL, absolute URIs, redirects và proxy. Một token Bearer có thể bị dùng bởi bất cứ bên nào lấy được nó nếu không có sender constraint.

### 26.4. Sender-constrained tokens

Nếu STS phát mTLS-bound hoặc DPoP-bound access token, client cần gửi proof tương ứng. Một HTTP `Authorization: Bearer ...` thông thường không đáp ứng đầy đủ proof-of-possession policy.

### 26.5. Cache và lifecycle

Không giữ Token B vô hạn ở singleton field hoặc cache không có tenant/source context. Token B có thể mất hiệu lực do expiry/revocation; source token hoặc user session có thể thay đổi.

Nếu STS không hỗ trợ revocation propagation, cần mô hình TTL, logout/disconnect và token invalidation riêng phù hợp yêu cầu.

---

## 27. Các tình huống thực tế

### Tình huống A: Service A gọi Orders API

A nhận Token A có audience `service-a`, muốn gọi B có audience `orders-api`.

**Cách xử lý:** Token Exchange RFC 8693 với subject Token A, target Orders và scope tối thiểu, nếu STS/client có quyền.

### Tình huống B: Provider trả `unsupported_grant_type`

**Nguyên nhân có thể:** STS không triển khai RFC 8693 hoặc grant bị tắt trong realm/tenant.

**Cách xử lý:** kiểm tra docs và cấu hình server; không thể sửa chỉ bằng Java.

### Tình huống C: Provider yêu cầu audience

Request body thiếu `audience`.

**Cách xử lý:** dùng `addParametersConverter` để gửi audience đã được allowlist.

### Tình huống D: Provider chỉ hỗ trợ proprietary OBO

Docs yêu cầu tham số `assertion` hoặc custom grant.

**Cách xử lý:** dùng SDK/extension theo vendor; không trộn vào request RFC 8693.

### Tình huống E: Subject token là opaque

STS không introspect được.

**Cách xử lý:** cấu hình trust/introspection đúng hoặc chọn flow provider được hỗ trợ.

### Tình huống F: OIDC Login có OidcUser nhưng resolver không thấy subject token

**Cách xử lý:** lấy access token của user qua authorized client phù hợp và trusted resolver; không gửi ID Token thay thế vô điều kiện.

### Tình huống G: Actor token được yêu cầu

STS cần actor JWT được issuer tin cậy.

**Cách xử lý:** cung cấp actor resolver và permission policy; không lấy `client-id` làm actor token.

### Tình huống H: Token B cấp thành công nhưng Orders API trả 401

**Cách xử lý:** kiểm tra JWT B issuer, audience, expiry, signature và API trust; không loop Token Exchange vô hạn.

### Tình huống I: User logout nhưng Token B còn tồn tại

**Cách xử lý:** kiểm tra revoke/remove/TTL policy; logout không tự revoke mọi token ở STS.

### Tình huống J: Hai tenants có cùng subject string

**Rủi ro:** cache token B bị dùng chéo tenant.

**Cách xử lý:** namespace theo issuer/tenant và principal ổn định, enforce ownership.

### Tình huống K: Service A cần quyền ứng dụng, không phải quyền user

**Cách xử lý:** cân nhắc Client Credentials thay vì Token Exchange.

### Tình huống L: Provider cấp `issued_token_type=jwt` và `token_type=N_A`

**Cách xử lý:** xem lại output token purpose; không mặc định dùng token đó như OAuth Bearer access token.

### Tình huống M: STS từ chối đổi cross-issuer token

**Cách xử lý:** cấu hình trust/federation đã được quản trị. Không bỏ validation hoặc fake issuer để qua lỗi.

### Tình huống N: Token B được cache dù Token A đã đổi

**Cách xử lý:** gắn lifecycle/cache key với source authorization policy, hoặc chủ động exchange lại khi cần.

### Tình huống O: Client yêu cầu scopes quá rộng

**Cách xử lý:** dùng scope downscoping theo API; không bỏ business authorization tại Resource Server.

## 28. Câu hỏi tự kiểm tra

**1. Token Exchange được chuẩn hóa ở RFC nào?**  
RFC 8693.

**2. Grant URN của Token Exchange là gì?**  
`urn:ietf:params:oauth:grant-type:token-exchange`.

**3. Các tham số request bắt buộc theo RFC là gì?**  
`grant_type`, `subject_token` và `subject_token_type`; client authentication theo yêu cầu deployment.

**4. `audience`/`resource` optional có nghĩa provider không được yêu cầu không?**  
Không. Chúng optional trong RFC nhưng có thể bắt buộc theo policy STS.

**5. `actor_token_type` cần khi nào?**  
Chỉ khi có actor token; lúc đó là bắt buộc.

**6. Có thể coi ID Token OIDC như access token không?**  
Không. Chúng có mục đích khác nhau; token type phải đúng provider contract.

**7. `subject_token_type=jwt` và `access_token` luôn giống nhau?**  
Không. JWT mô tả cú pháp, access_token mô tả mục đích OAuth2.

**8. `issued_token_type` khác `token_type` thế nào?**  
Field đầu nói loại token được phát hành; field sau nói cách sử dụng token.

**9. Exchange có tự revoke Token A không?**  
Không mặc định.

**10. Exchange có luôn trả refresh token không?**  
Không.

**11. OBO của vendor có luôn là RFC 8693 không?**  
Không; cần so sánh grant/params/docs.

**12. Spring Security có built-in Token Exchange từ phiên bản nào?**  
`TokenExchangeOAuth2AuthorizedClientProvider` từ 6.3.

**13. RestClientTokenExchangeTokenResponseClient có từ phiên bản nào?**  
Spring Security 6.4.

**14. Vì sao JwtAuthenticationToken phù hợp với default subject token resolver?**  
Principal của nó thường là Jwt, một OAuth2Token được framework hiểu.

**15. OidcUser có tự là raw subject access token không?**  
Không. Có thể cần resolver lấy token đúng từ authorized client.

**16. Thêm audience vào token request bằng API gì?**  
`RestClientTokenExchangeTokenResponseClient.addParametersConverter(...)`.

**17. Khi nào STS trả `invalid_target`?**  
Khi target audience/resource không được hoặc không thể cấp theo policy.

**18. Token B được phát hành có chứng minh business authorization không?**  
Không. API B còn phải kiểm tra scopes/claims/ownership.

**19. Có thể dùng Token B của Alice cho Bob cùng registration không?**  
Không. Phải kiểm soát principal/tenant/token ownership.

**20. Khi nào nên dùng Client Credentials?**  
Khi backend cần token đại diện chính service chứ không phải delegated subject token.

---

## 29. Ghi nhớ trọng tâm

| Khái niệm | Cách nhớ |
|---|---|
| RFC 8693 | Chuẩn Token Exchange qua OAuth2 Token Endpoint |
| `grant_type` | URN extension grant, không phải `authorization_code` |
| `subject_token` | Input token đại diện subject |
| `subject_token_type` | Loại input token, required |
| `actor_token` | Optional token của actor |
| `actor_token_type` | Required khi có actor token |
| `requested_token_type` | Loại output muốn nhận |
| `resource` | Target absolute URI |
| `audience` | Target logical identifier |
| `scope` | Quyền muốn xin tại target |
| `act` | Actor claim có thể dùng khi delegation |
| `may_act` | Claim có thể giúp STS đánh giá quyền actor |
| `issued_token_type` | Required trong response RFC 8693 |
| `token_type` | Cách sử dụng token (Bearer/N_A...) |
| `invalid_target` | Target không được/không thể cấp |
| STS compatibility | Grant, client auth, subject trust, target và response |
| `TokenExchangeOAuth2AuthorizedClientProvider` | Built-in Spring Security từ 6.3 |
| `RestClientTokenExchangeTokenResponseClient` | HTTP token client từ 6.4 |
| `setSubjectTokenResolver` | Chọn trusted input token |
| `setActorTokenResolver` | Chọn actor token khi STS cho phép |
| `addParametersConverter` | Bổ sung audience/resource/extension parameters |
| `OAuth2AuthorizedClientManager` | Điều phối grant và token storage |
| Reactive counterpart | Reactive token-exchange provider + WebClient response client |
| OBO proprietary | Không mặc định tương thích RFC 8693 |
| Resource Server B | Tự kiểm tra Token B và authorization |
| Token lifecycle | Exchange không tự đồng bộ revoke/expiry với input |

### Kết luận

Token Exchange cho phép OAuth2 client **đổi một security token đầu vào thành token mới** tại STS, thường để gọi downstream API với **đúng audience và phạm vi quyền**. Nó đặc biệt hữu ích cho API gateway, BFF và microservices có nhiều Resource Servers.

Tuy nhiên, **cấu hình Spring Security không thể tạo ra hỗ trợ RFC 8693 ở phía provider**. Trước khi triển khai, hãy kiểm tra grant permission, client authentication, subject token type, issuer trust, actor/delegation policy, audience/resource/scope và output token semantics.

Với Spring Security hiện đại, `TokenExchangeOAuth2AuthorizedClientProvider` cùng `RestClientTokenExchangeTokenResponseClient` và `OAuth2AuthorizedClientManager` là điểm xuất phát phù hợp. Chỉ thêm custom resolvers/converters khi provider contract yêu cầu; luôn bảo vệ token, principal, tenant, token lifecycle và mọi API call.

**Một Token Exchange trả HTTP 200 chưa chứng minh authorization an toàn**: trust chain từ caller → Service A → STS → Service B phải được kiểm chứng toàn bộ.

## Tài liệu tham khảo chính thức

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html) — request/response, delegation, actor claims và lỗi.
- [Spring Security — Authorization Grant Support (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html) — Token Exchange và tùy chỉnh client.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/) — authorized client manager và providers.
- [Spring Security API — TokenExchangeOAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/TokenExchangeOAuth2AuthorizedClientProvider.html) — subject/actor resolvers và expiry.
- [Spring Security API — RestClientTokenExchangeTokenResponseClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/endpoint/RestClientTokenExchangeTokenResponseClient.html) — Token Exchange HTTP request customization.
- [Spring Security API — TokenExchangeGrantRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/endpoint/TokenExchangeGrantRequest.html) — grant request type.
- [Spring Security — Reactive Authorization Grants](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html) — Token Exchange trên WebFlux.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html) — security practices cho OAuth2.
