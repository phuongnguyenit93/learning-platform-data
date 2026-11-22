# Chuyển tiếp token hiện có khác với lấy token mới hoặc làm mới token

Trong một hệ thống OAuth 2.0 có gateway, backend-for-frontend (BFF) hoặc nhiều microservices, một request thường đi qua nhiều thành phần trước khi tới API cuối. Khi Orders API cần gọi Inventory API hoặc gateway chuyển request tới downstream service, ứng dụng phải quyết định **dùng access token hiện có, yêu cầu Authorization Server cấp token mới, hay làm mới token đã hết hạn**.

Ba hành động này có mục đích và ngữ nghĩa khác nhau:

- **Chuyển tiếp token (token relay):** gửi tiếp chính access token đã nhận được. Giá trị token không đổi; downstream nhận cùng credential và cùng các claims, audience, scope, thời hạn, token binding.
- **Lấy token mới (obtain/acquire a new token):** yêu cầu Authorization Server cấp một access token mới theo một grant hoặc một quy trình ủy quyền. Token mới có thể đại diện cho client/service hoặc một user tùy grant.
- **Làm mới token (refresh):** dùng refresh token để yêu cầu access token thay thế khi access token hiện tại sắp hết hạn/hết hạn, theo quyền và policy đã được cấp trước đó.

Ngoài ba cách trên còn có **OAuth 2.0 Token Exchange**: dùng một token hiện có làm subject/actor input để Authorization Server phát hành một token khác dành cho downstream resource hoặc delegation context. Token exchange không phải token relay và cũng không phải refresh grant.

Điểm quan trọng nhất: **relay giữ nguyên danh tính và phạm vi của token đang có; obtain/refresh/exchange tạo ra hoặc trả về một access token khác theo quyết định của Authorization Server**. Chọn sai cơ chế có thể làm mất user context, gửi token sai audience, mở rộng quyền ngoài ý muốn hoặc biến một lời gọi service-to-service thành hành động dưới danh tính người dùng.

Bài học thuộc chương **Chuyển tiếp token** trong module **Spring Security OAuth 2.0 OIDC Resource Server**. Nội dung giải thích luồng request, cách phân biệt các grant, lựa chọn giữa relay và token mới, cách dùng Spring Security/Spring Cloud Gateway, cùng các rủi ro và cách kiểm thử.

> Dữ liệu token, issuer, key và client ID trong ví dụ đều là giả lập. Mục tiêu là hiểu rõ ranh giới giữa credential hiện có và credential mới do Authorization Server phát hành.

## 1. Một request đi qua nhiều dịch vụ

Giả sử người dùng đăng nhập vào Shop Web, gọi Orders API và Orders API cần truy vấn Inventory API:

~~~text
Browser / Shop Web
        |
        | access token T-user
        v
API Gateway
        |
        | token relay?
        v
Orders API
        |
        | gọi downstream Inventory API
        v
Inventory API
~~~

Ở mỗi chặng, thành phần trung gian có thể:

1. **Relay** token đã nhận.
2. **Dùng token riêng của service** để gọi downstream.
3. **Làm mới** access token nếu đang có refresh token hợp lệ.
4. **Exchange** token đầu vào thành token mới có audience/scope/actor phù hợp.

Không có một lựa chọn đúng cho mọi hệ thống. Cần xem **ai là chủ thể của hành động**, **downstream cần tin ai**, **token dành cho resource nào** và **Authorization Server hỗ trợ grant nào**.

### 1.1. Ví dụ relay token hiện có

Browser gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: shop.example.test
Authorization: Bearer eyJ...T_USER
~~~

Gateway chuyển nguyên access token tới Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.internal
Authorization: Bearer eyJ...T_USER
~~~

Giá trị sau scheme trong hai request là **cùng một chuỗi token**. Gateway không đổi subject, scope, audience, issuer, expiry hay chữ ký. Gateway chỉ chuyển tiếp credential theo policy.

### 1.2. Ví dụ lấy token mới bằng client credentials

Orders API gọi Authorization Server với danh tính service:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CLIENT_CREDENTIALS>

grant_type=client_credentials&scope=inventory.read
~~~

Authorization Server trả token mới dành cho Inventory API:

~~~json
{
  "access_token": "<NEW_SERVICE_ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

Đây là **token mới**. Token thường đại diện cho Orders service/client, không tự động giữ danh tính người dùng đã gọi Orders API.

### 1.3. Ví dụ refresh token

Client có access token T1 và refresh token R:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<REFRESH_TOKEN_R>&
client_id=shop-bff
~~~

Authorization Server có thể trả access token T2 mới và refresh token R2 nếu áp dụng rotation. T2 là credential mới; nó có thể giữ authorization grant tương ứng với R, nhưng không được giả định rằng mọi claim, audience, scope hoặc binding sẽ giống hệt T1.

## 2. Phân biệt bốn hành động

| Hành động | Input chính | Kết quả | Danh tính thường được đại diện | Token có đổi không? |
|---|---|---|---|---|
| **Relay** | Access token hiện có | Gửi cùng token tới downstream | Chủ thể/caller trong token ban đầu | **Không** |
| **Obtain token mới** | Authorization code, client credentials hoặc grant khác | Access token mới | User hoặc service tùy grant | **Có** |
| **Refresh** | Refresh token | Access token thay thế | Authorization grant đã được cấp | **Có** |
| **Token exchange** | Subject token và có thể actor token | Access token mới theo target resource/delegation | Subject/actor theo policy exchange | **Có** |

### 2.1. Relay là hành động ở tầng HTTP

Relay thường chỉ có nghĩa: lấy token hiện có từ SecurityContext/session/authorized client và gắn vào request downstream. Nó không yêu cầu Authorization Server cấp lại token.

~~~text
incoming access token
       |
       v
extract token
       |
       v
Authorization: Bearer <same token>
       |
       v
downstream API
~~~

Nếu token hết hạn hoặc sai audience, relay vẫn gửi chính token đó; downstream có thể từ chối. Relay không tự làm token mới, không sửa claims và không bổ sung quyền.

### 2.2. Obtain token mới là một quyết định cấp quyền

Client yêu cầu Authorization Server cấp token theo một grant được phép. AS kiểm tra client authentication, grant, consent, user context, scopes, resource/audience và policy. Việc token được cấp không chỉ là sao chép một credential sẵn có.

### 2.3. Refresh duy trì một grant đã cấp

Refresh token được dùng tại token endpoint để yêu cầu access token thay thế. Nó không phải access token để gọi Resource Server. Refresh thường không có nghĩa là “nâng quyền” hoặc “đổi sang API khác tùy ý”; AS vẫn kiểm soát scope/resource và có thể yêu cầu user re-authenticate hoặc consent lại.

### 2.4. Token exchange tạo token theo delegation/resource khác

Token Exchange (RFC 8693) cho phép một client gửi subject token, có thể kèm actor token, và yêu cầu token phù hợp với audience/resource hoặc delegation context mới. Đây là cách có thể dùng khi Orders API cần gọi Inventory API **với ngữ cảnh user đã được ủy quyền**, nhưng token đầu vào không được cấp cho Inventory API.

Token exchange chỉ dùng được nếu Authorization Server hỗ trợ và policy cho phép. Không giả định mọi OAuth provider đều triển khai RFC 8693 hoặc có cùng semantics.

## 3. Câu hỏi quyết định: downstream cần tin ai?

Trước khi viết code, hãy xác định downstream cần nhìn thấy danh tính nào.

### 3.1. Downstream cần hành động dưới danh tính người dùng

Ví dụ user Alice gọi:

~~~text
GET /api/orders/42
~~~

Orders API cần gọi Pricing API và Pricing API cần kiểm tra quyền của Alice. Có thể:

- Relay access token của Alice nếu token được phát hành cho cả Orders/Pricing hoặc resource contract cho phép Pricing nhận nó.
- Exchange token của Alice sang access token dành cho Pricing API, giữ subject Alice và có actor Orders API nếu policy cần delegation.

Nếu relay token có audience chỉ dành cho Orders API, Pricing API đúng ra phải từ chối. Không sửa Pricing API để chấp nhận token không dành cho nó.

### 3.2. Downstream cần danh tính service

Ví dụ Orders API cần lấy thông tin tồn kho để tính toán nội bộ. Inventory API chỉ cần biết caller là Orders service:

~~~text
Orders service
    -- client credentials -->
Authorization Server
    -- service token aud=inventory-api -->
Orders service
    -- Authorization: Bearer <service token> -->
Inventory API
~~~

Đây là obtain token theo Client Credentials, không relay token người dùng. Audit log của Inventory API sẽ phản ánh service client; nếu cần lưu user context, Orders API có thể truyền một business correlation/actor context đã được tin cậy theo thiết kế riêng, nhưng không giả mạo claims xác thực.

### 3.3. Downstream cần cả user và service context

Một service có thể cần chứng minh:

- **Subject:** user Alice là người khởi tạo hành động.
- **Actor:** Orders API đang thực hiện lời gọi downstream thay Alice.
- **Audience:** token dành cho Inventory API.
- **Scope:** chỉ có quyền đọc tồn kho.

Token exchange là một cơ chế phù hợp nếu Authorization Server hỗ trợ subject/actor delegation. Chỉ relay token hiện tại có thể không thể hiện được actor chain hoặc audience đúng.

### 3.4. Không nên quyết định chỉ dựa trên “token còn hạn”

Một token còn hạn có thể:

- Dành cho API khác.
- Thiếu scope downstream.
- Được cấp cho client không được phép gọi downstream.
- Bị ràng buộc với DPoP key hoặc mTLS certificate mà downstream request không đáp ứng.
- Không mang actor/delegation context cần thiết.

Vì vậy, “token chưa hết hạn” không phải lý do đủ để relay.

## 4. Audience và scope quyết định token có thể relay tới đâu

Giả sử access token hiện tại:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "alice",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

Token được cấp cho Orders API và chỉ có scope đọc đơn hàng. Orders API chuyển nguyên token tới Inventory API:

~~~http
GET /internal/stock/sku-123 HTTP/1.1
Host: inventory.internal
Authorization: Bearer <SAME_ORDERS_TOKEN>
~~~

Inventory API kiểm tra `aud` và thấy token dành cho Orders API. Nó nên từ chối token này, dù chữ ký và issuer đúng. Nếu Inventory API bỏ audience check chỉ vì request đến từ mạng nội bộ, ranh giới resource bị yếu đi.

### 4.1. Relay không thể tự thêm audience

Gateway hoặc Orders API không thể sửa payload JWT:

~~~text
decode token
change aud from orders-api to inventory-api
encode token
~~~

Nếu token là JWS, sửa claims làm chữ ký không hợp lệ. Nếu token là opaque, client thậm chí không thể biết claims bên trong. Chỉ Authorization Server hoặc một cơ chế phát hành token được tin cậy mới tạo token có audience mới.

### 4.2. Relay không thể tự thêm scope

Nếu token chỉ có `orders.read`, việc thêm `inventory.read` vào header hoặc request context không làm Authorization Server cấp quyền đó. Scope phải được cấp trong access token/authorization context và Resource Server phải xác minh.

### 4.3. Token nhiều audience

Nếu token có:

~~~json
{
  "aud": [
    "https://api.example.test/orders",
    "https://api.example.test/inventory"
  ],
  "scope": "orders.read inventory.read"
}
~~~

thì relay tới Inventory API có thể hợp lệ nếu issuer chủ động phát hành token đa resource và policy cho phép. Tuy nhiên token bị lộ có phạm vi replay lớn hơn; nhiều hệ thống chọn token riêng từng resource hoặc token exchange để thu hẹp quyền.

### 4.4. Relay chỉ giữ nguyên quyền, không giảm quyền

Một token có `orders.read orders.write admin` vẫn mang các scopes đó khi relay. Gateway không thể “gỡ” `admin` khỏi token mà vẫn giữ chữ ký. Nếu downstream cần quyền hẹp hơn, hãy yêu cầu token mới với scope tối thiểu qua token exchange hoặc một grant phù hợp.

## 5. Sơ đồ lựa chọn cơ chế

~~~mermaid
flowchart TD
    A["Có access token hiện tại"] --> B{"Downstream có thể và được phép nhận chính token này?"}
    B -->|Có| C["Relay cùng access token"]
    B -->|Không| D{"Downstream cần danh tính user/delegation?"}
    D -->|Có| E{"AS hỗ trợ Token Exchange / OBO?"}
    E -->|Có| F["Exchange token cho downstream resource"]
    E -->|Không| G["Thiết kế lại grant/delegation hoặc yêu cầu user flow phù hợp"]
    D -->|Không, chỉ cần service identity| H["Lấy service token mới bằng Client Credentials"]
    C --> I["Downstream vẫn xác minh aud, scope, expiry, binding"]
    F --> I
    H --> I
~~~

**Refresh** là một nhánh khác: nếu access token cần dùng cho cùng authorization context đã hết hạn/sắp hết hạn và client có refresh token hợp lệ, dùng refresh flow để lấy access token thay thế. Refresh không phải cách mặc định để đổi audience hoặc biến user token thành service token.

## 19. Quy tắc vận hành và thiết kế token relay

### 19.1. Xác định token owner và downstream resource

Trước khi relay, ghi rõ:

~~~text
Token owner / subject:
    user, service, workload, or delegated subject

Current resource audience:
    API that accepted the inbound token

Downstream resource:
    API that will receive the outbound request

Required downstream scopes:
    minimum operations required

Token binding:
    Bearer, DPoP, mTLS, or provider-specific
~~~

Nếu token hiện tại không được phát hành cho downstream resource hoặc không đáp ứng token binding, không relay. Chọn token exchange, client credentials hoặc grant khác theo danh tính downstream cần.

### 19.2. Giữ user context có chủ đích

Khi downstream phải áp quyền theo user, cần một trong hai:

- Token inbound đã được issuer phát hành cho downstream và chứa đúng quyền/delegation context; hoặc
- Một token mới được AS cấp theo token exchange/OBO, giữ subject và biểu diễn actor theo policy.

Không lấy user ID từ request body rồi gắn vào header để giả lập user context. Nếu dùng service token, downstream phải hiểu caller là service; attribution người dùng cần một cơ chế riêng được xác thực và audit.

### 19.3. Dùng service token cho background work

Scheduled job, message consumer và asynchronous worker thường không có SecurityContext của request người dùng. Không cố relay token user đã lưu từ request trước. Dùng workload/service identity với client credentials hoặc cơ chế workload identity phù hợp, scopes tối thiểu và audience đúng resource.

Nếu công việc được khởi tạo bởi user và phải duy trì delegation, lưu một task authorization record an toàn hoặc dùng delegation/token-exchange flow có thời hạn; không giữ access token user như một credential lâu dài cho job.

### 19.4. Cache token theo đúng identity

Authorized-client storage/cache cần phân biệt ít nhất:

- Client registration.
- Principal/service identity.
- Tenant/issuer khi multi-tenant.
- Resource/audience hoặc token context nếu provider hỗ trợ nhiều resource.

Không dùng một key cache chung cho mọi user khi token mang quyền user-specific. Không trả token Alice cho request Bob chỉ vì cả hai dùng cùng client registration.

### 19.5. Token relay và logout/revocation

Relay không kiểm tra revocation độc lập. Với JWT self-contained, downstream có thể chấp nhận token đến khi hết hạn nếu không có introspection/denylist/short-lived-token strategy. Với opaque token, introspection có thể phản ánh trạng thái active/revoked theo policy.

Logout ở frontend không tự bảo đảm mọi access token đã relay tới microservices lập tức mất hiệu lực. Thiết kế thời hạn access token, refresh token, revocation, session invalidation và downstream cache theo yêu cầu bảo mật.

### 19.6. Không giữ token lâu hơn cần thiết

Chỉ lưu access/refresh token trong authorized-client store theo vòng đời cần thiết, bảo vệ encryption-at-rest và access control. Không copy token vào custom database, distributed cache hoặc message payload nếu không có nhu cầu và security design cụ thể.

### 19.7. Token relay trong message-driven systems

Đẩy nguyên Bearer token vào Kafka/RabbitMQ message có thể khiến credential lan rộng tới broker, dead-letter queue, tracing và consumer logs. Thường nên truyền business identity/correlation theo một contract nội bộ được bảo vệ, hoặc dùng workload identity ở consumer. Nếu thật sự cần delegation theo user, dùng một cơ chế token delegation có thời hạn và scope hẹp; không mặc định message là nơi an toàn để lưu token.

## 20. Ví dụ so sánh request thực tế

### 20.1. Relay: token không đổi

~~~http
# Request inbound
GET /api/orders/42 HTTP/1.1
Authorization: Bearer T1

# Request outbound
GET /internal/orders/42 HTTP/1.1
Authorization: Bearer T1
~~~

Không có token endpoint request. Nếu downstream không chấp nhận T1, relay không thể tự sửa lỗi.

### 20.2. Client Credentials: token mới của service

~~~http
# Orders service obtains a service token
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CREDENTIALS>

grant_type=client_credentials&scope=inventory.read

# Orders service calls Inventory API
GET /api/stock/sku-123 HTTP/1.1
Authorization: Bearer T_SERVICE
~~~

T_SERVICE là token do AS cấp cho Orders service. Nó không phải T1 của user.

### 20.3. Refresh: access token thay thế trong cùng grant

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=R1

# AS response
{
  "access_token": "T2",
  "refresh_token": "R2",
  "token_type": "Bearer",
  "expires_in": 300
}
~~~

T2 thay thế access token cũ theo grant và policy của AS. Client phải lưu R2 nếu refresh token rotation được áp dụng.

### 20.4. Token exchange: token mới cho resource khác

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CREDENTIALS>

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=T_USER_ORDERS&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=inventory-api&
scope=inventory.read
~~~

AS có thể trả T_INVENTORY với resource audience và delegation context mới nếu client, subject token và policy được phép. Đây không phải hành vi mặc định của mọi issuer.

## 21. Checklist chọn cơ chế trước khi triển khai

### 21.1. Chọn relay khi

- [ ] Downstream được phép nhận chính token inbound.
- [ ] Audience/resource binding phù hợp downstream.
- [ ] Token có đủ scopes nhưng không mang quyền quá rộng.
- [ ] Subject/actor context trong token đúng điều downstream cần.
- [ ] Token binding (Bearer/DPoP/mTLS) có thể được duy trì ở outbound request.
- [ ] Outbound host được allowlist và Authorization không bị forward qua redirect.
- [ ] Downstream vẫn tự xác minh token.
- [ ] Logging/tracing/proxy redacts credential.

### 21.2. Chọn client credentials khi

- [ ] Downstream chỉ cần biết service/workload caller.
- [ ] Không cần user-specific delegation trong token.
- [ ] Service có client registration/credential được bảo vệ.
- [ ] AS cấp audience và scopes tối thiểu cho downstream.
- [ ] Authorized-client manager/cache được phân vùng theo service identity.

### 21.3. Chọn refresh khi

- [ ] Client có refresh token hợp lệ thuộc đúng authorized client.
- [ ] Access token cần thay thế trong authorization grant đã cấp.
- [ ] Refresh provider được cấu hình trong authorized-client manager.
- [ ] Refresh token rotation/concurrency được xử lý an toàn.
- [ ] Không kỳ vọng refresh tự thêm scope hoặc đổi audience ngoài policy AS.

### 21.4. Chọn token exchange/OBO khi

- [ ] Downstream cần user/delegation context.
- [ ] Token inbound không dành cho downstream resource hoặc cần scope khác.
- [ ] Authorization Server hỗ trợ RFC 8693/OBO hoặc extension tương đương.
- [ ] Subject token và actor/client được phép exchange theo policy.
- [ ] Target audience/resource và scopes được yêu cầu tối thiểu.
- [ ] Downstream xác minh subject/actor và token mới.

### 21.5. Kiểm thử và vận hành

- [ ] Relay test chứng minh downstream nhận đúng nguyên token T1.
- [ ] Relay test chứng minh không gọi token endpoint/không tự refresh.
- [ ] Refresh test chứng minh token endpoint nhận refresh grant và trả T2.
- [ ] Client credentials test chứng minh downstream nhận service identity.
- [ ] Exchange test chứng minh subject/actor/audience/scope đúng contract.
- [ ] Wrong-audience và insufficient-scope cases được kiểm tra riêng.
- [ ] DPoP/mTLS-bound token có test sender constraint.
- [ ] Refresh token rotation và concurrent refresh được kiểm thử.
- [ ] Redirect/SSRF/header leakage được ngăn chặn.
- [ ] 401/403 được phân loại, không refresh hoặc fallback vô hạn.
- [ ] Metrics không dùng raw token, subject hoặc refresh token làm label.

## 22. Kết luận

Ba thao tác thường bị gọi chung là “chuyển token” thực chất khác nhau:

~~~text
TOKEN RELAY
    access token T1 → gửi tiếp T1
    không gọi token endpoint
    không đổi subject/audience/scope/expiry

OBTAIN A NEW TOKEN
    grant/client authentication → Authorization Server
    → access token mới theo identity và resource được cấp

REFRESH
    refresh token R1 → Authorization Server
    → access token thay thế T2 trong grant đã có

TOKEN EXCHANGE
    subject token (+ actor token) → Authorization Server
    → access token mới cho resource/delegation context khác
~~~

Trong Spring Security, `ServletBearerExchangeFilterFunction` và `ServerBearerExchangeFilterFunction` hỗ trợ relay Bearer token hiện có; `TokenRelay` của Spring Cloud Gateway chuyển tiếp access token từ OAuth2 authorized client; `OAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientManager` quản lý việc authorize và refresh theo grant/provider; token exchange cần support từ Authorization Server và integration phù hợp.

**Hãy chọn theo danh tính và resource downstream cần xác minh.** Nếu downstream được phép nhận cùng token, relay là đủ. Nếu chỉ cần service identity, lấy service token. Nếu access token cần thay thế trong cùng grant, refresh. Nếu cần token mới cho resource khác nhưng vẫn giữ user delegation, dùng token exchange/OBO khi được hỗ trợ. Không sửa token, thêm scope bằng header, bỏ audience check hoặc fallback sang service privilege để làm request thành công.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security — Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security — Servlet OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Cloud Gateway — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html)
- [Spring Security — ServletBearerExchangeFilterFunction Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServletBearerExchangeFilterFunction.html)
- [Spring Security — ServerBearerExchangeFilterFunction Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServerBearerExchangeFilterFunction.html)
- [Microsoft identity platform — OAuth 2.0 On-Behalf-Of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)

## 14. Bảo mật khi relay access token

Relay làm cho credential của một principal đi qua thêm nhiều process và network hops. Mỗi hop mới đều có thể trở thành điểm rò rỉ hoặc bị lạm dụng.

### 14.1. Chỉ relay tới downstream đã được tin cậy

Không dùng một WebClient tự động gắn Authorization header để gọi URL tùy ý:

~~~java
// PHẢN VÍ DỤ: URL đến từ dữ liệu do người dùng kiểm soát.
webClient.get()
    .uri(userSuppliedUrl)
    .retrieve();
~~~

Nếu filter relay token được gắn trên client này, người dùng có thể tìm cách khiến token được gửi tới host ngoài dự kiến. Đây là nguy cơ credential exfiltration/SSRF kết hợp.

Nên:

- Dùng base URL cố định cho từng downstream client.
- Allowlist scheme/host/port/path phù hợp.
- Không chuyển Authorization qua redirect sang origin khác.
- Không dùng một client global có bearer relay filter cho arbitrary external URLs.
- Tách WebClient theo trust boundary và credential policy.

### 14.2. Không log Authorization header

Access token là bearer credential. Không log:

~~~text
Authorization: Bearer eyJ...
Authorization: DPoP eyJ...
refresh_token=...
~~~

Kiểm tra access logs, reverse proxy, tracing, HTTP wiretap, exception messages và CI output. Redact header trước khi lưu. Cũng không ghi refresh token vào log vì nó có thể tồn tại lâu và dùng để xin access token mới.

### 14.3. Giới hạn số lần relay và phạm vi dịch vụ

Một token user được relay qua nhiều service có thể tăng phạm vi hậu quả nếu token bị lộ. Chỉ relay tới service thực sự cần user context. Nếu downstream chỉ cần một thao tác nội bộ, token service có scope hẹp thường dễ giới hạn hơn.

### 14.4. Không tin header identity tự tạo

Nếu Orders API relay token tới Inventory API, Inventory API phải xác minh token theo trust policy của nó. Không thay bằng:

~~~http
X-User-Id: alice
X-Roles: admin
~~~

Các header identity tự khai từ upstream chỉ có thể được dùng trong một trust boundary nội bộ có xác thực service-to-service, header stripping và policy rõ ràng. Chúng không thay thế token verification ở một Resource Server độc lập.

### 14.5. Token relay không giảm quyền

Token có nhiều scopes sẽ giữ nguyên các scopes đó. Gateway không thể sửa JWT để xóa quyền. Nếu downstream chỉ cần `inventory.read`, hãy dùng token mới có scope tối thiểu thay vì relay một user token chứa quyền rộng hơn.

### 14.6. Không forward mọi inbound header

Một gateway thường chỉ cần chuyển một tập header đã định nghĩa. Không copy toàn bộ request headers sang downstream, đặc biệt các header proxy, cookie, host, authorization hoặc identity không cần thiết. Đặt rõ policy header allowlist và xử lý duplicate Authorization headers.

### 14.7. Không dùng một user token trong background job

Background job không còn nằm trong request/security context của user. Không lưu access token Alice rồi dùng lại sau nhiều giờ để chạy batch công việc không có sự ủy quyền mới. Hãy dùng service identity hoặc một cơ chế delegation/task authorization có thời hạn và scope rõ ràng.

## 15. Xử lý 401/403: đừng refresh hoặc relay theo phản xạ

HTTP status có thể giúp chẩn đoán, nhưng không phải mọi lỗi đều được giải quyết bằng refresh.

| Downstream response | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| 401 expired token | Access token hết hạn | Nếu có authorized client/refresh token, manager có thể refresh theo policy |
| 401 invalid signature/issuer | Token không được tin cậy | Sửa issuer/key/config; refresh có thể không giải quyết |
| 401 wrong audience | Token dành cho resource khác | Obtain/exchange token cho đúng audience |
| 401 missing/invalid DPoP proof | Sender constraint không được đáp ứng | Tạo proof đúng hoặc lấy token phù hợp; không fallback Bearer |
| 403 insufficient scope | Token hợp lệ nhưng thiếu quyền | Yêu cầu grant/scope phù hợp hoặc từ chối; refresh không tự thêm quyền |
| 403 tenant/owner policy | Quyền nghiệp vụ không cho phép | Xử lý authorization, không refresh vô hạn |
| 5xx/timeout | Downstream/upstream lỗi | Retry theo idempotency/backoff; không tự xin token mới mỗi lần |

### 15.1. Không refresh vô hạn khi nhận 401

Một client có thể thử refresh một lần khi token hết hạn nếu có refresh token và manager hỗ trợ. Nhưng nếu response 401 do sai audience, sai issuer hoặc token revoked, lặp lại refresh có thể không giải quyết nguyên nhân và tạo tải lên Authorization Server.

Không nên:

~~~text
while downstream returns 401:
    refresh token
    retry request
~~~

Hãy phân loại lỗi, giới hạn retry, và không lặp lại request nghiệp vụ không idempotent nếu chưa có idempotency strategy.

### 15.2. 403 không phải tín hiệu refresh

403 thường nói principal đã xác thực nhưng thiếu quyền hoặc bị policy từ chối. Refresh token không tự tăng scope. Nếu quyền cần được cấp thêm, phải có authorization/consent/admin process thích hợp.

### 15.3. Relay lỗi không được tự chuyển sang service token

Nếu user token relay tới downstream bị 403, tự động fallback sang service token có thể làm request của user được thực hiện bằng quyền rộng hơn của service. Đây là **privilege escalation/confused deputy**. Fallback chỉ được thiết kế nếu nghiệp vụ xác định rõ thao tác nào có thể chạy dưới service identity và audit phải ghi nhận đúng actor.

## 16. Kiểm thử: chứng minh relay, refresh và obtain là ba đường khác nhau

Test nên quan sát cả **token endpoint** và **downstream request**, không chỉ assert downstream trả 200.

### 16.1. Test relay giữ nguyên token

Fixture:

~~~text
Inbound access token = T1
Downstream mock server captures Authorization header
Token endpoint mock server records requests
~~~

Kịch bản:

1. Gửi request vào application với `Authorization: Bearer T1`.
2. Application gọi downstream qua bearer relay filter.
3. Mock downstream ghi lại Authorization header.
4. Assert giá trị token downstream nhận đúng là T1.
5. Assert token endpoint không bị gọi.

Kết quả mong đợi:

~~~text
downstream Authorization = "Bearer " + T1
token endpoint calls = 0
~~~

Đây là bằng chứng relay **không lấy token mới hoặc refresh**.

### 16.2. Test relay không tự refresh token hết hạn

Tạo token T1 đã hết hạn theo test clock, gửi request qua bearer relay filter và cho downstream mock trả 401:

~~~text
Inbound T1 expired
    → relay filter forwards T1
    → downstream returns 401
    → token endpoint call count remains 0
~~~

Test này xác nhận filter relay chỉ forward credential. Nếu application muốn refresh, phải dùng OAuth2 Client manager và test riêng đường đó.

### 16.3. Test refresh provider

Tạo authorized client có:

~~~text
access token  = T1 (expired)
refresh token = R1
registration = shop-bff
principal = alice
~~~

Mock token endpoint nhận `grant_type=refresh_token` và `refresh_token=R1`, trả T2 (và R2 nếu rotation). Sau đó assert:

- Manager gửi đúng refresh grant.
- Downstream nhận T2, không phải T1.
- Authorized client storage được cập nhật token mới/refresh token mới theo manager.
- Refresh token cũ không bị dùng lại sau rotation.

### 16.4. Test client credentials

Khi authorized client registration là `inventory-service`:

- Mock token endpoint nhận `grant_type=client_credentials`.
- AS trả service token T-service có audience Inventory API.
- Downstream nhận T-service.
- Subject/client identity phản ánh service, không giả định là Alice.
- Token được reuse đến khi cần authorize lại theo expiry/provider policy.

### 16.5. Test token exchange

Nếu AS hỗ trợ RFC 8693/OBO, mock token endpoint xác nhận request có subject token đúng, actor/client authentication đúng, target audience/resource đúng và scope yêu cầu hợp lệ. Assert token mới được gửi downstream và subject/actor context phù hợp contract.

Không dùng một mock trả T2 bất kể request để kết luận exchange policy được bảo vệ; test cần xác nhận các tham số request và negative cases.

### 16.6. Ma trận hồi quy

| Case | Input | Cơ chế | Điều cần assert |
|---|---|---|---|
| T-01 | Inbound token T1 hợp lệ, audience phù hợp | Relay | Downstream nhận đúng T1; không gọi token endpoint |
| T-02 | Inbound T1 hết hạn | Relay filter | Vẫn forward T1; downstream từ chối; không tự refresh |
| T-03 | Authorized client có T1 expired + R1 | OAuth2 client manager | Refresh grant trả T2; downstream nhận T2 |
| T-04 | Không có authorized client, service registration hợp lệ | Client credentials | Token endpoint phát service token mới |
| T-05 | User token audience Orders, downstream Inventory | Relay | Inventory từ chối sai audience |
| T-06 | User token audience Orders, cần Inventory context | Token exchange/OBO | AS phát token mới cho Inventory theo delegation policy |
| T-07 | Token thiếu scope downstream | Relay | Downstream 403; không tự thêm scope |
| T-08 | DPoP-bound token | Relay có DPoP support | Proof mới cho downstream URI/method |
| T-09 | mTLS-bound token | Relay qua proxy | Certificate binding được duy trì hoặc request bị từ chối |
| T-10 | Redirect sang host ngoài allowlist | Relay | Không forward Authorization token sang host khác |
| T-11 | Downstream 403 | Error handling | Không refresh/fallback service token ngoài policy |
| T-12 | Hai request cùng refresh token rotation | Refresh | Không dùng refresh token cũ đồng thời gây race/reuse |

### 16.7. Không dùng test helper để nhầm lẫn relay với authentication

Nếu dùng `mockJwt()` hoặc `@WithMockUser`, test có thể kiểm tra authorization/controller nhưng không chứng minh request inbound thực sự mang access token nào để relay. Với relay integration test, tạo request có Bearer token thật hoặc một authenticated test context có access token rõ ràng và kiểm tra chính header downstream.

## 17. Ví dụ kiến trúc hoàn chỉnh: BFF gọi hai downstream APIs

Giả sử BFF có hai downstream:

| Downstream | Cần danh tính | Audience | Cơ chế |
|---|---|---|---|
| Orders API | User Alice | `orders-api` | Relay user token nếu token đã dành cho Orders |
| Inventory API | Orders service | `inventory-api` | Client credentials |
| Pricing API | Alice, nhưng token inbound chỉ dành cho Orders | `pricing-api` | Token exchange/OBO nếu AS hỗ trợ |

Flow:

~~~mermaid
flowchart TD
    U["Alice / Browser"] --> BFF["Shop BFF"]
    BFF -->|"T-user, aud=orders-api"| O["Orders API"]
    O -->|"Service token, aud=inventory-api"| I["Inventory API"]
    O -->|"Subject token + actor Orders"| AS["Authorization Server"]
    AS -->|"T-pricing, aud=pricing-api"| O
    O -->|"T-pricing"| P["Pricing API"]
~~~

### 17.1. Orders API không dùng một WebClient cho tất cả

Có thể tách:

~~~text
userRelayWebClient:
    forwards current inbound user bearer token
    allowed host = orders downstream

inventoryServiceWebClient:
    OAuth2AuthorizedClientManager
    registration = inventory-service
    grant = client_credentials

pricingDelegationClient:
    token exchange/OBO provider integration
    subject token = current user token
    audience = pricing-api
    scope = pricing.read
~~~

Mỗi client có một credential policy rõ. Không để một filter tự động relay token trên mọi outbound request.

### 17.2. Audit phải giữ đúng actor

Khi Inventory API nhận service token, audit nên ghi Orders service là caller; nếu cần user attribution, ghi business correlation/actor context đã được thiết kế. Khi Pricing API nhận token exchange có subject Alice và actor Orders service, audit có thể phân biệt user và middle-tier service theo claims/profile tin cậy.

Không ghi “Alice gọi trực tiếp Inventory” nếu Inventory chỉ xác thực service identity. Cũng không ghi “Orders service là user” nếu token exchange bảo toàn subject và actor riêng.

### 17.3. Downstream vẫn là Resource Server độc lập

Mỗi API phải tự xác minh issuer, signature/introspection, audience, expiry, scope và token binding phù hợp. Mạng nội bộ hoặc gateway đã xác thực không tự làm access token trở nên hợp lệ cho mọi downstream.

## 18. Chẩn đoán khi relay hoặc token acquisition lỗi

| Triệu chứng | Khả năng | Cách xử lý |
|---|---|---|
| Downstream không nhận Authorization | SecurityContext không có access token, filter chưa gắn hoặc context bị mất | Kiểm tra authentication type, filter registration và execution context |
| Downstream nhận token nhưng 401 | Expired, wrong issuer/audience, signature/key hoặc token binding sai | Xác định lý do ở Resource Server; relay không sửa token |
| Downstream trả 403 | Token hợp lệ nhưng thiếu scope/role hoặc domain permission | Kiểm tra grant/authorization; không tự thêm scope |
| Relay filter không gọi token endpoint | Hành vi bình thường | Relay chỉ forward token hiện có |
| OAuth2 client manager trả null/authorization failure | Registration, provider, client credentials hoặc repository sai | Kiểm tra registration/secret/token endpoint và manager provider |
| Refresh trả invalid_grant | Refresh token hết hạn/revoked/đã rotation hoặc client mismatch | Xử lý re-auth/recovery theo policy; không retry R1 vô hạn |
| Service token có subject/client khác kỳ vọng | Đang dùng client credentials | Downstream nhận service identity; dùng exchange/OBO nếu cần user delegation |
| Token mới vẫn sai audience | Client registration/resource request chưa yêu cầu đúng resource | Cấu hình API/resource identifier và issuer policy |
| Downstream nhận user token ở service route | Dùng relay filter hoặc TokenRelay trên route không phù hợp | Tách service OAuth2 client và relay policy |
| Hai request đồng thời refresh cùng token | Race khi refresh rotation | Điều phối refresh theo authorized-client key và cập nhật storage atomic |
| Token bị gửi sang host khác | Redirect/URL động/client dùng chung filter | Allowlist host, chặn cross-origin credential forwarding |
| DPoP downstream từ chối proof | Proof inbound được reuse hoặc htu/htm không khớp | Tạo proof mới cho downstream request bằng key bind với token |

### 18.1. Downstream 401 có thể do sai audience, không phải hết hạn

Không refresh chỉ vì thấy 401. Kiểm tra error challenge/response và Resource Server logs/metrics. Nếu token có audience Orders nhưng gọi Inventory, refresh cùng grant có thể vẫn trả audience Orders; cần token exchange hoặc client/resource request khác được AS hỗ trợ.

### 18.2. Authorized client manager không phải token broker không giới hạn

Manager chỉ có thể dùng các registration, grant provider và credential mà ứng dụng đã cấu hình. Nó không tự quyết định rằng một user token có thể đổi thành token của mọi resource. Phải khai báo resource/scopes, provider extension và delegation policy rõ ràng.

## 6. Chuyển tiếp access token hiện có trong Spring Security

Spring Security có các thành phần hỗ trợ relay Bearer token từ SecurityContext hiện tại sang một lời gọi bằng `WebClient`. Cách này phù hợp khi downstream được phép nhận **chính access token đang xác thực request inbound**.

### 6.1. Servlet: `ServletBearerExchangeFilterFunction`

Với ứng dụng Servlet/Spring MVC, có thể cấu hình `WebClient`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class DownstreamWebClientConfiguration {

    @Bean
    WebClient downstreamWebClient() {
        return WebClient.builder()
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
~~~

Khi có một authenticated request trong Servlet SecurityContext và Authentication chứa Bearer access token phù hợp, filter có thể thêm token đó vào header Authorization của request WebClient.

Ví dụ gọi downstream:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
class OrdersInventoryClient {

    private final WebClient downstreamWebClient;

    OrdersInventoryClient(WebClient downstreamWebClient) {
        this.downstreamWebClient = downstreamWebClient;
    }

    InventoryItem getStock(String sku) {
        return downstreamWebClient.get()
            .uri("https://inventory.internal/api/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryItem.class)
            .block();
    }
}
~~~

Ví dụ dùng `block()` chỉ để minh họa cách gọi từ ứng dụng Servlet đồng bộ. Không dùng blocking call trong WebFlux event loop. Cũng cần bảo đảm WebClient chỉ gọi host downstream đã được cấu hình tin cậy; filter có thể đưa credential vào request nên không dùng một client global tùy tiện cho URL do người dùng kiểm soát.

### 6.2. WebFlux: `ServerBearerExchangeFilterFunction`

Với ứng dụng WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveDownstreamWebClientConfiguration {

    @Bean
    WebClient downstreamWebClient() {
        return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
    }
}
~~~

Khi gọi trong reactive security context:

~~~java
Mono<InventoryItem> getStock(String sku) {
    return downstreamWebClient.get()
        .uri("https://inventory.internal/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryItem.class);
}
~~~

Filter này lấy access token từ context reactive hiện hành và chuyển tiếp nó dưới dạng Bearer token theo cơ chế của Spring Security. Không tự chuyển một access token Bearer thành token có audience khác.

### 6.3. Relay filter không làm mới access token

`ServletBearerExchangeFilterFunction` và `ServerBearerExchangeFilterFunction` có mục đích **forward Bearer token hiện tại**. Chúng không phải OAuth2 authorized-client manager và không tự gọi token endpoint để refresh token khi access token hết hạn.

Do đó:

~~~text
Inbound token T1 còn hạn:
    relay → downstream nhận T1

Inbound token T1 hết hạn:
    relay → downstream vẫn nhận T1
    downstream từ chối nếu token expired
~~~

Nếu muốn lấy token mới/refresh, phải dùng OAuth2 Client và authorized-client manager phù hợp. Không kỳ vọng chỉ thêm bearer exchange filter là có refresh behavior.

### 6.4. Khi nào relay filter không tìm thấy token?

Nếu không có authenticated principal chứa OAuth2 access token trong SecurityContext, filter không thể tự tạo credential. Các trường hợp:

- Request inbound không có Bearer token.
- Authentication là một loại khác, chẳng hạn session/user authentication không có access token liên kết.
- SecurityContext không được truyền đúng qua thread/reactive context.
- Lời gọi chạy ở background job không có request user context.

Khi đó cần chọn một grant/service identity hoặc authorized client phù hợp, không tự tạo một chuỗi Authorization header giả.

## 7. Spring Cloud Gateway: TokenRelay GatewayFilter

Spring Cloud Gateway có `TokenRelay` GatewayFilter Factory để chuyển tiếp access token từ OAuth2 authorized client của user tới downstream route. Đây là cơ chế relay ở tầng gateway.

Ví dụ cấu hình route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: http://orders-service:8080
          predicates:
            - Path=/api/orders/**
          filters:
            - TokenRelay=
~~~

Trong mô hình OAuth2 Login, gateway có thể lấy access token của người dùng đã đăng nhập và gắn nó vào request gửi tới Orders service. Gateway cần được cấu hình OAuth2 Client và lưu trữ authorized client/session theo hướng dẫn của đúng phiên bản Spring Cloud Gateway.

### 7.1. TokenRelay làm gì?

~~~text
Browser
  Authorization: Bearer <user access token>
       |
       v
Gateway authenticates user / has OAuth2AuthorizedClient
       |
       v
TokenRelay filter obtains existing authorized client's access token
       |
       v
Downstream request:
  Authorization: Bearer <relayed access token>
~~~

Tên filter là TokenRelay vì nó **chuyển tiếp access token đã được authorized client giữ**. Gateway không sửa audience/scope hoặc ký lại token.

### 7.2. Có và không có clientRegistrationId

TokenRelay có thể được cấu hình để dùng authorized client gắn với user hiện tại hoặc một registration được chỉ định, tùy API/version và flow. Khi chỉ định client registration, cần hiểu token được lấy từ OAuth2 Client registration nào và user principal nào:

~~~yaml
filters:
  - TokenRelay=inventory-client
~~~

Ví dụ này chỉ là cấu trúc minh họa cho một registration tên `inventory-client`. Nó không có nghĩa token user hiện tại tự động được exchange cho Inventory API. Hành vi chính xác phụ thuộc cách gateway tích hợp `OAuth2AuthorizedClientManager` và registration/provider.

### 7.3. TokenRelay không thay thế audience design

Nếu gateway relay access token có:

~~~text
aud = gateway-api
~~~

tới Orders API, Orders API có thể từ chối. Cấu hình TokenRelay không tự yêu cầu issuer phát token có audience Orders. Client/issuer phải cấp token phù hợp với downstream resource hoặc gateway phải dùng một cơ chế lấy token khác.

### 7.4. Route-specific relay và trust boundary

Không nên gắn TokenRelay vào mọi route một cách vô điều kiện. Chỉ relay tới downstream host được tin cậy, có policy nhận token, audience phù hợp và bảo vệ logging. Route tới public website hoặc URL do user điều khiển tuyệt đối không nên nhận Authorization header tự động.

### 7.5. Lưu trữ OAuth2 authorized client

Gateway cần giữ authorized client access token theo principal/registration. Với session-based OAuth2 Login, session/cookie và authorized-client repository phải được bảo vệ; logout, session invalidation, token expiry và refresh lifecycle phải được xử lý đúng. TokenRelay không phải kho lưu token độc lập; nó dựa vào authorized client mà OAuth2 Client đã quản lý.

## 8. Lấy token mới bằng OAuth2 Client trong Spring

Khi downstream cần một service token hoặc một authorized client khác với token inbound, dùng **OAuth2 Client** thay vì relay. Spring Security cung cấp `OAuth2AuthorizedClientManager` cho Servlet và `ReactiveOAuth2AuthorizedClientManager` cho WebFlux để quản lý authorized client, bao gồm lấy/refresh access token theo provider đã cấu hình.

### 8.1. Khai báo client registration cho service

Ví dụ application YAML cho một client credentials registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: shop-issuer
            client-id: orders-service
            client-secret: ${ORDERS_SERVICE_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          shop-issuer:
            token-uri: https://login.example.test/oauth2/token
~~~

Đây là cấu hình minh họa; các thuộc tính provider/discovery và authentication method cần theo Authorization Server thực tế. Client secret phải đến từ secret manager/environment được bảo vệ, không commit vào repository.

### 8.2. Servlet: cấu hình authorized-client manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

@Configuration
class OAuth2ClientManagerConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .refreshToken()
                .authorizationCode()
                .build();

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Provider chỉ bật những grant cần thiết. `clientCredentials()` cho phép manager lấy service token; `refreshToken()` cho phép refresh một authorized client user khi có refresh token hợp lệ; `authorizationCode()` tham gia authorization code lifecycle. Với request web hiện hành, có thể dùng `DefaultOAuth2AuthorizedClientManager` cùng `OAuth2AuthorizedClientRepository`; lựa chọn manager phụ thuộc execution context.

### 8.3. Dùng manager để lấy service token

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
class InventoryServiceTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    InventoryServiceTokenProvider(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String accessToken(String servicePrincipalName) {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-service")
                .principal(servicePrincipalName)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null) {
            throw new IllegalStateException(
                "Could not authorize inventory-service client");
        }
        return client.getAccessToken().getTokenValue();
    }
}
~~~

Với client credentials, `principal` thường là một service principal ổn định dùng để lưu authorized client; không phải user hiện tại. Nếu nhiều tenant/service identity khác nhau, chọn principal/cache key có phạm vi phù hợp để không chia sẻ token sai identity.

### 8.4. Token mới theo client credentials đại diện cho service

Khi dùng registration `inventory-service`, downstream thường nhận token mang client/service identity của Orders service. Nếu cần downstream biết user Alice là người khởi tạo, không tự chèn `sub=alice` vào token. Dùng token exchange/OBO nếu issuer hỗ trợ hoặc thiết kế audit/delegation context đã được tin cậy.

## 9. OAuth2AuthorizedClientManager và refresh token

Authorized-client manager có thể quyết định lấy token mới hoặc refresh token tùy registration, authorized client hiện có và các provider được bật. Đây là **token acquisition lifecycle**, không phải relay thô.

### 9.1. Refresh provider cần refresh token

Với authorization code flow, authorized client có thể lưu:

~~~text
OAuth2AuthorizedClient:
    access token  = T1
    refresh token = R1
    registration  = shop-bff
    principal     = alice
~~~

Khi access token sắp hết hạn và manager được cấu hình `refreshToken()`, manager có thể gọi token endpoint bằng R1 để nhận T2 (và có thể R2). Chi tiết thời điểm refresh phụ thuộc provider implementation, clock skew và token lifecycle.

### 9.2. Refresh không phải cách tạo service identity

Nếu token hiện tại là user token của Alice, refresh thường tiếp tục authorization grant gắn với Alice/client. Nó không tự biến thành token của Orders service. Để có service identity, dùng client credentials hoặc grant phù hợp.

### 9.3. Refresh không phải cách đổi audience tùy ý

Refresh grant thường tiếp tục authorization grant đã được cấp; AS có thể cho phép scope hẹp hơn hoặc resource parameter theo policy/provider, nhưng client không được giả định có thể đổi bất kỳ audience nào bằng cách thêm một tham số. Nếu cần token cho resource khác, kiểm tra provider support và cân nhắc token exchange/authorization mới.

### 9.4. Rotation và concurrency

Một số Authorization Servers áp dụng refresh token rotation: mỗi lần dùng R1 sẽ trả R2 và vô hiệu hóa R1. Nếu hai request song song cùng refresh R1, một request có thể thành công, request còn lại bị từ chối hoặc bị xem là reuse. Client cần:

- Dùng authorized-client manager/storage để điều phối token lifecycle.
- Tránh nhiều luồng refresh cùng một authorized client đồng thời.
- Cập nhật refresh token mới một cách atomic.
- Xử lý invalid_grant/reuse theo policy, có thể cần re-authentication.
- Không tự retry vô hạn bằng refresh token cũ.

### 9.5. Relay filter và OAuth2 client filter có hành vi khác nhau

| Thành phần | Mục tiêu | Gọi token endpoint? | Có thể refresh? |
|---|---|---:|---:|
| `ServletBearerExchangeFilterFunction` | Relay Bearer token trong Servlet context | Không | Không |
| `ServerBearerExchangeFilterFunction` | Relay Bearer token trong reactive context | Không | Không |
| `TokenRelay` GatewayFilter | Relay authorized client's access token tới route | Không tự đổi audience; lifecycle phụ thuộc authorized-client integration | Không nên giả định; kiểm tra manager/version |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | Lấy authorized client/token cho WebClient Servlet | Có thể | Có nếu manager/provider bật refresh |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Lấy authorized client/token cho WebClient reactive | Có thể | Có nếu reactive manager/provider bật refresh |

Điểm cần nhớ: tên “OAuth2 client filter” không có nghĩa nó luôn refresh mọi token. Hành vi phụ thuộc authorized-client manager, registration, grant, refresh token availability và provider.

## 10. OAuth2 Client WebClient: obtain/refresh thay vì relay thô

Khi ứng dụng cần **authorized client token** thay vì access token inbound, dùng OAuth2 Client filter với manager.

### 10.1. Servlet: `ServletOAuth2AuthorizedClientExchangeFilterFunction`

Có thể gắn authorized-client manager vào WebClient filter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class OAuth2WebClientConfiguration {

    @Bean
    WebClient inventoryOAuth2WebClient(
            OAuth2AuthorizedClientManager authorizedClientManager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

Khi gọi downstream với client registration:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<InventoryItem> stock(String sku) {
    return inventoryOAuth2WebClient.get()
        .uri("https://inventory.internal/api/stock/{sku}", sku)
        .attributes(clientRegistrationId("inventory-service"))
        .retrieve()
        .bodyToMono(InventoryItem.class);
}
~~~

Đây là mẫu dùng một authorized client registration tên `inventory-service`. Filter/manager có thể authorize client theo registration, lấy access token hoặc refresh token theo provider đã cấu hình. Token sẽ là credential của registration đó, không nhất thiết là token inbound của Alice.

### 10.2. User authorized client và service authorized client

Nếu downstream phải nhận access token của user hiện tại, manager cần được gọi với đúng user principal/authorized client và registration phù hợp. Không đổi sang `inventory-service` client credentials rồi kỳ vọng downstream vẫn thấy `sub=alice`.

Ngược lại, nếu downstream chỉ cần service identity, không nên relay user token chỉ để tiện. Dùng registration client credentials với scopes tối thiểu.

### 10.3. Reactive: `ServerOAuth2AuthorizedClientExchangeFilterFunction`

Trong WebFlux, dùng reactive manager và filter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveOAuth2WebClientConfiguration {

    @Bean
    WebClient inventoryOAuth2WebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .filter(oauth2)
            .build();
    }
}
~~~

Khi gọi:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<InventoryItem> stock(String sku) {
    return inventoryOAuth2WebClient.get()
        .uri("https://inventory.internal/api/stock/{sku}", sku)
        .attributes(clientRegistrationId("inventory-service"))
        .retrieve()
        .bodyToMono(InventoryItem.class);
}
~~~

Tên overload/constructor và static helper có thể thay đổi theo Spring Security version. Dùng Javadoc/reference đúng dependency đang khóa. Điểm kiến trúc không đổi: reactive manager quyết định authorized client, filter gắn access token phù hợp; đây không phải sao chép nguyên chuỗi token inbound một cách vô điều kiện.

### 10.4. Reactive manager với provider

Ví dụ cấu hình provider hỗ trợ client credentials và refresh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
class ReactiveAuthorizedClientConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .refreshToken()
                .authorizationCode()
                .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Provider phải phản ánh các grant ứng dụng thật sự dùng. Background worker hoặc service-to-service không có ServerWebExchange/user session có thể cần một manager/repository phù hợp service context thay vì `DefaultReactiveOAuth2AuthorizedClientManager` gắn với web request.

### 10.5. Chọn đúng filter cho đúng mục đích

~~~text
Need exactly the inbound bearer token?
    → ServletBearerExchangeFilterFunction
    → ServerBearerExchangeFilterFunction

Need a registered OAuth2 client token, service identity,
authorization-code authorized client, or managed refresh?
    → OAuth2AuthorizedClientManager + OAuth2 client WebClient filter

Need a token for a different audience while retaining user delegation?
    → OAuth2 Token Exchange / provider-specific OBO flow
~~~

Đừng đặt hai filter cùng ghi Authorization header lên một WebClient rồi hy vọng thứ tự xử lý tạo đúng identity. Mỗi client nên có mục đích và credential policy rõ ràng.

## 11. Token Exchange và On-Behalf-Of

Khi Orders API nhận access token của Alice dành cho Orders, nhưng Inventory API cần một token mới dành cho Inventory và vẫn cần user context, relay không giải quyết được audience mismatch. Một lựa chọn là **token exchange**.

### 11.1. RFC 8693: subject token và actor token

Token Exchange mô tả một token endpoint request có thể chứa:

- `subject_token`: token đại diện cho subject đang được ủy quyền.
- `subject_token_type`: loại token đầu vào.
- `actor_token` (tùy chọn): token đại diện actor đang thực hiện exchange.
- `actor_token_type` (tùy chọn).
- `requested_token_type` (tùy chọn).
- `audience`/`resource` hoặc scope theo extension/policy được hỗ trợ.

Request minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CLIENT_CREDENTIALS>

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=<ALICE_ORDERS_ACCESS_TOKEN>&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
requested_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=https%3A%2F%2Fapi.example.test%2Finventory&
scope=inventory.read
~~~

AS xác minh client Orders service có quyền exchange subject token đó và phát hành token mới theo policy. Token mới có thể giữ subject Alice, nhưng audience là Inventory API và scopes được thu hẹp phù hợp.

Các tham số resource/audience, actor token và quyền delegation cần theo RFC/provider contract. Không phải mọi Authorization Server đều chấp nhận chính xác bộ tham số trên.

### 11.2. Subject và actor không đồng nhất

~~~text
sub = alice
act.sub = orders-service
aud = inventory-api
scope = inventory.read
~~~

Payload trên chỉ minh họa ý tưởng. Subject là user được ủy quyền; actor là service đang hành động thay user. Cấu trúc claims cụ thể phải theo token profile và cách AS phát hành. Downstream cần kiểm tra cả delegation policy khi có actor context, không chỉ đọc `sub`.

### 11.3. On-Behalf-Of (OBO) là tên flow theo provider

Một số provider gọi luồng exchange/delegation là **On-Behalf-Of**. Ví dụ trong Microsoft identity platform, một middle-tier API có thể đổi access token nhận được thành access token dành cho downstream API trong ngữ cảnh user. OBO là provider-specific flow/API contract, không nên mặc định mọi IdP có cùng request format hay token claims.

### 11.4. Token exchange khác refresh

| Tiêu chí | Refresh grant | Token exchange |
|---|---|---|
| Input | Refresh token | Subject token, có thể actor token |
| Mục tiêu | Cấp access token thay thế trong grant đã có | Cấp token mới theo subject/actor/resource delegation |
| Đổi audience | Không mặc định; tùy AS grant/policy | Có thể yêu cầu audience/resource mới nếu AS cho phép |
| Đổi actor | Không phải mục tiêu thông thường | Có thể thể hiện actor/delegation |
| Có thể thu hẹp scope | Theo refresh policy | Theo exchange policy |
| Dùng khi | Access token cũ sắp hết hạn | Downstream cần token khác phù hợp resource/delegation |

### 11.5. Nếu AS không hỗ trợ token exchange?

Không giả lập exchange bằng cách:

- Decode token inbound và tự tạo JWT mới.
- Copy `sub`, `scope` hoặc `aud` vào một token tự ký mà downstream tin.
- Thêm header custom nói “on behalf of Alice” mà downstream coi là authentication.

Thay vào đó, chọn một grant/kiến trúc được issuer hỗ trợ: client credentials cho service identity, authorization flow riêng, API composition hoặc một cơ chế delegation đã được thiết kế và xác thực. Nếu downstream bắt buộc user context mà không có cách ủy quyền tin cậy, cần thay đổi contract giữa các service.

## 12. Client Credentials, Authorization Code và refresh trong từng tình huống

### 12.1. Client Credentials

Dùng khi một confidential client gọi API bằng **danh tính ứng dụng/service**. Client xác thực với AS, nhận access token cho resource và scopes được cấp. Không có user session tự động gắn vào token.

Ví dụ:

~~~text
orders-service
    → client_id=orders-service
    → grant_type=client_credentials
    → scope=inventory.read
    → token aud=inventory-api
~~~

Ưu điểm: đơn giản cho background/service tasks; không phải relay user token. Hạn chế: downstream không có user identity đáng tin trong token, nên không phù hợp nếu phải thực thi user-specific authorization trừ khi có một mô hình delegation khác.

### 12.2. Authorization Code

Dùng khi cần user authorization qua browser/interactive login. Client đổi authorization code (và PKCE verifier với public clients) lấy access token, có thể kèm refresh token theo policy. Đây là **lấy token theo authorization grant**, không phải relay.

Một BFF có thể giữ authorized client của Alice và relay token nếu downstream được phép nhận chính token đó; hoặc dùng token exchange/OBO để lấy token dành cho downstream.

### 12.3. Refresh Token Grant

Dùng refresh token do AS cấp để lấy access token mới trong authorization grant đã được cấp. Client phải bảo vệ refresh token chặt hơn access token vì refresh token có thể tồn tại lâu hơn và dùng để xin access token tiếp.

### 12.4. Token Exchange

Dùng khi service có một subject token hiện tại nhưng cần token mới cho resource khác hoặc actor context khác, với điều kiện AS hỗ trợ. Không phải một grant mà mọi Spring Security deployment tự động có sẵn.

### 12.5. Quy tắc lựa chọn ngắn gọn

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Downstream được phép nhận cùng access token | Relay |
| Downstream chỉ cần service identity | Client Credentials |
| Access token sắp hết hạn, cùng grant | Refresh |
| Cần token cho resource khác nhưng giữ user delegation | Token Exchange/OBO nếu được hỗ trợ |
| Chưa có user grant, cần user consent/login | Authorization Code + PKCE |
| Background job không có user context | Client Credentials hoặc service-specific grant |

## 13. DPoP và mTLS-bound tokens khi relay

Relay token không phải lúc nào cũng chỉ là copy một chuỗi vào Authorization header. Nếu token bị ràng buộc với key/certificate, downstream request phải đáp ứng sender constraint tương ứng.

### 13.1. DPoP-bound access token

Với DPoP, access token gắn với public key thumbprint và request cần:

~~~http
Authorization: DPoP <DPoP_BOUND_ACCESS_TOKEN>
DPoP: <NEW_PROOF_FOR_THIS_DOWNSTREAM_REQUEST>
~~~

Chuyển tiếp **chỉ access token** là không đủ. Proof của request inbound cũng thường không thể relay nguyên vẹn tới downstream vì `htm`/`htu` khác; `ath` có thể giống nếu token giống nhưng proof phải được ký cho method/URI downstream. Thành phần thực hiện relay cần sở hữu private key tương ứng và tạo proof mới, hoặc dùng token exchange để có binding phù hợp.

### 13.2. mTLS certificate-bound token

Nếu access token gắn với thumbprint của client certificate, downstream cần thấy client certificate/private key tương ứng trong TLS handshake hoặc một kiến trúc proxy delegation được tin cậy. Chỉ copy access token qua HTTP không duy trì certificate binding.

### 13.3. Không làm mất sender constraint để tiện relay

Không chuyển DPoP/mTLS token sang Bearer scheme hoặc bỏ proof/certificate để tránh lỗi. Nếu downstream không thể đáp ứng binding hiện tại, dùng token mới phù hợp resource/connection hoặc thiết kế lại trust boundary.
# Chuyển tiếp token hiện có khác với lấy token mới hoặc làm mới token

Trong một hệ thống OAuth 2.0 có gateway, backend-for-frontend (BFF) hoặc nhiều microservices, một request thường đi qua nhiều thành phần trước khi tới API cuối. Khi Orders API cần gọi Inventory API hoặc gateway chuyển request tới downstream service, ứng dụng phải quyết định **dùng access token hiện có, yêu cầu Authorization Server cấp token mới, hay làm mới token đã hết hạn**.

Ba hành động này có mục đích và ngữ nghĩa khác nhau:

- **Chuyển tiếp token (token relay):** gửi tiếp chính access token đã nhận được. Giá trị token không đổi; downstream nhận cùng credential và cùng các claims, audience, scope, thời hạn, token binding.
- **Lấy token mới (obtain/acquire a new token):** yêu cầu Authorization Server cấp một access token mới theo một grant hoặc một quy trình ủy quyền. Token mới có thể đại diện cho client/service hoặc một user tùy grant.
- **Làm mới token (refresh):** dùng refresh token để yêu cầu access token thay thế khi access token hiện tại sắp hết hạn/hết hạn, theo quyền và policy đã được cấp trước đó.

Ngoài ba cách trên còn có **OAuth 2.0 Token Exchange**: dùng một token hiện có làm subject/actor input để Authorization Server phát hành một token khác dành cho downstream resource hoặc delegation context. Token exchange không phải token relay và cũng không phải refresh grant.

Điểm quan trọng nhất: **relay giữ nguyên danh tính và phạm vi của token đang có; obtain/refresh/exchange tạo ra hoặc trả về một access token khác theo quyết định của Authorization Server**. Chọn sai cơ chế có thể làm mất user context, gửi token sai audience, mở rộng quyền ngoài ý muốn hoặc biến một lời gọi service-to-service thành hành động dưới danh tính người dùng.

Bài học thuộc chương **Chuyển tiếp token** trong module **Spring Security OAuth 2.0 OIDC Resource Server**. Nội dung giải thích luồng request, cách phân biệt các grant, lựa chọn giữa relay và token mới, cách dùng Spring Security/Spring Cloud Gateway, cùng các rủi ro và cách kiểm thử.

> Dữ liệu token, issuer, key và client IDs trong ví dụ đều là giả lập. Mục tiêu là hiểu rõ ranh giới giữa credential hiện có và credential mới do Authorization Server phát hành.

## 1. Một request đi qua nhiều dịch vụ

Giả sử người dùng đăng nhập vào Shop Web, gọi Orders API và Orders API cần truy vấn Inventory API:

~~~text
Browser / Shop Web
        |
        | access token T-user
        v
API Gateway
        |
        | token relay?
        v
Orders API
        |
        | gọi downstream Inventory API
        v
Inventory API
~~~

Ở mỗi chặng, thành phần trung gian có thể:

1. **Relay** token đã nhận.
2. **Dùng token riêng của service** để gọi downstream.
3. **Làm mới** access token nếu đang có refresh token hợp lệ.
4. **Exchange** token đầu vào thành token mới có audience/scope/actor phù hợp.

Không có một lựa chọn đúng cho mọi hệ thống. Cần xem **ai là chủ thể của hành động**, **downstream cần tin ai**, **token dành cho resource nào** và **Authorization Server hỗ trợ grant nào**.

### 1.1. Ví dụ relay token hiện có

Browser gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: shop.example.test
Authorization: Bearer eyJ...T_USER
~~~

Gateway chuyển nguyên access token tới Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.internal
Authorization: Bearer eyJ...T_USER
~~~

Giá trị sau scheme trong hai request là **cùng một chuỗi token**. Gateway không đổi subject, scope, audience, issuer, expiry hay chữ ký. Gateway chỉ chuyển tiếp credential theo policy.

### 1.2. Ví dụ lấy token mới bằng client credentials

Orders API gọi Authorization Server với danh tính service:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CLIENT_CREDENTIALS>

grant_type=client_credentials&scope=inventory.read
~~~

Authorization Server trả token mới dành cho Inventory API:

~~~json
{
  "access_token": "<NEW_SERVICE_ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

Đây là **token mới**. Token thường đại diện cho Orders service/client, không tự động giữ danh tính người dùng đã gọi Orders API.

### 1.3. Ví dụ refresh token

Client có access token T1 và refresh token R:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<REFRESH_TOKEN_R>&
client_id=shop-bff
~~~

Authorization Server có thể trả access token T2 mới và refresh token R2 nếu áp dụng rotation. T2 là credential mới; nó có thể giữ authorization grant tương ứng với R, nhưng không được giả định rằng mọi claim, audience, scope hoặc binding sẽ giống hệt T1.

## 2. Phân biệt bốn hành động

| Hành động | Input chính | Kết quả | Danh tính thường được đại diện | Token có đổi không? |
|---|---|---|---|---|
| **Relay** | Access token hiện có | Gửi cùng token tới downstream | Chủ thể/caller trong token ban đầu | **Không** |
| **Obtain token mới** | Authorization code, client credentials hoặc grant khác | Access token mới | User hoặc service tùy grant | **Có** |
| **Refresh** | Refresh token | Access token thay thế | Authorization grant đã được cấp | **Có** |
| **Token exchange** | Subject token và có thể actor token | Access token mới theo target resource/delegation | Subject/actor theo policy exchange | **Có** |

### 2.1. Relay là hành động ở tầng HTTP

Relay thường chỉ có nghĩa: lấy token hiện có từ SecurityContext/session/authorized client và gắn vào request downstream. Nó không yêu cầu Authorization Server cấp lại token.

~~~text
incoming access token
       |
       v
extract token
       |
       v
Authorization: Bearer <same token>
       |
       v
downstream API
~~~

Nếu token hết hạn hoặc sai audience, relay vẫn gửi chính token đó; downstream có thể từ chối. Relay không tự làm token mới, không sửa claims và không bổ sung quyền.

### 2.2. Obtain token mới là một quyết định cấp quyền

Client yêu cầu Authorization Server cấp token theo một grant được phép. AS kiểm tra client authentication, grant, consent, user context, scopes, resource/audience và policy. Việc token được cấp không chỉ là sao chép một credential sẵn có.

### 2.3. Refresh duy trì một grant đã cấp

Refresh token được dùng tại token endpoint để yêu cầu access token thay thế. Nó không phải access token để gọi Resource Server. Refresh thường không có nghĩa là “nâng quyền” hoặc “đổi sang API khác tùy ý”; AS vẫn kiểm soát scope/resource và có thể yêu cầu user re-authenticate hoặc consent lại.

### 2.4. Token exchange tạo token theo delegation/resource khác

Token Exchange (RFC 8693) cho phép một client gửi subject token, có thể kèm actor token, và yêu cầu token phù hợp với audience/resource hoặc delegation context mới. Đây là cách có thể dùng khi Orders API cần gọi Inventory API **với ngữ cảnh user đã được ủy quyền**, nhưng token đầu vào không được cấp cho Inventory API.

Token exchange chỉ dùng được nếu Authorization Server hỗ trợ và policy cho phép. Không giả định mọi OAuth provider đều triển khai RFC 8693 hoặc có cùng semantics.

## 3. Câu hỏi quyết định: downstream cần tin ai?

Trước khi viết code, hãy xác định downstream cần nhìn thấy danh tính nào.

### 3.1. Downstream cần hành động dưới danh tính người dùng

Ví dụ user Alice gọi:

~~~text
GET /api/orders/42
~~~

Orders API cần gọi Pricing API và Pricing API cần kiểm tra quyền của Alice. Có thể:

- Relay access token của Alice nếu token được phát hành cho cả Orders/Pricing hoặc resource contract cho phép Pricing nhận nó.
- Exchange token của Alice sang access token dành cho Pricing API, giữ subject Alice và có actor Orders API nếu policy cần delegation.

Nếu relay token có audience chỉ dành cho Orders API, Pricing API đúng ra phải từ chối. Không sửa Pricing API để chấp nhận token không dành cho nó.

### 3.2. Downstream cần danh tính service

Ví dụ Orders API cần lấy thông tin tồn kho để tính toán nội bộ. Inventory API chỉ cần biết caller là Orders service:

~~~text
Orders service
    -- client credentials -->
Authorization Server
    -- service token aud=inventory-api -->
Orders service
    -- Authorization: Bearer <service token> -->
Inventory API
~~~

Đây là obtain token theo Client Credentials, không relay token người dùng. Audit log của Inventory API sẽ phản ánh service client; nếu cần lưu user context, Orders API có thể truyền một business correlation/actor context đã được tin cậy theo thiết kế riêng, nhưng không giả mạo claims xác thực.

### 3.3. Downstream cần cả user và service context

Một service có thể cần chứng minh:

- **Subject:** user Alice là người khởi tạo hành động.
- **Actor:** Orders API đang thực hiện lời gọi downstream thay Alice.
- **Audience:** token dành cho Inventory API.
- **Scope:** chỉ có quyền đọc tồn kho.

Token exchange là một cơ chế phù hợp nếu Authorization Server hỗ trợ subject/actor delegation. Chỉ relay token hiện tại có thể không thể hiện được actor chain hoặc audience đúng.

### 3.4. Không nên quyết định chỉ dựa trên “token còn hạn”

Một token còn hạn có thể:

- Dành cho API khác.
- Thiếu scope downstream.
- Được cấp cho client không được phép gọi downstream.
- Bị ràng buộc với DPoP key hoặc mTLS certificate mà downstream request không đáp ứng.
- Không mang actor/delegation context cần thiết.

Vì vậy, “token chưa hết hạn” không phải lý do đủ để relay.

## 4. Audience và scope quyết định token có thể relay tới đâu

Giả sử access token hiện tại:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "alice",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

Token được cấp cho Orders API và chỉ có scope đọc đơn hàng. Orders API chuyển nguyên token tới Inventory API:

~~~http
GET /internal/stock/sku-123 HTTP/1.1
Host: inventory.internal
Authorization: Bearer <SAME_ORDERS_TOKEN>
~~~

Inventory API kiểm tra `aud` và thấy token dành cho Orders API. Nó nên từ chối token này, dù chữ ký và issuer đúng. Nếu Inventory API bỏ audience check chỉ vì request đến từ mạng nội bộ, ranh giới resource bị yếu đi.

### 4.1. Relay không thể tự thêm audience

Gateway hoặc Orders API không thể sửa payload JWT:

~~~text
decode token
change aud from orders-api to inventory-api
encode token
~~~

Nếu token là JWS, sửa claims làm chữ ký không hợp lệ. Nếu token là opaque, client thậm chí không thể biết claims bên trong. Chỉ Authorization Server hoặc một cơ chế phát hành token được tin cậy mới tạo token có audience mới.

### 4.2. Relay không thể tự thêm scope

Nếu token chỉ có `orders.read`, việc thêm `inventory.read` vào header hoặc request context không làm Authorization Server cấp quyền đó. Scope phải được cấp trong access token/authorization context và Resource Server phải xác minh.

### 4.3. Token nhiều audience

Nếu token có:

~~~json
{
  "aud": [
    "https://api.example.test/orders",
    "https://api.example.test/inventory"
  ],
  "scope": "orders.read inventory.read"
}
~~~

thì relay tới Inventory API có thể hợp lệ nếu issuer chủ động phát hành token đa resource và policy cho phép. Tuy nhiên token bị lộ có phạm vi replay lớn hơn; nhiều hệ thống chọn token riêng từng resource hoặc token exchange để thu hẹp quyền.

### 4.4. Relay chỉ giữ nguyên quyền, không giảm quyền

Một token có `orders.read orders.write admin` vẫn mang các scopes đó khi relay. Gateway không thể “gỡ” `admin` khỏi token mà vẫn giữ chữ ký. Nếu downstream cần quyền hẹp hơn, hãy yêu cầu token mới với scope tối thiểu qua token exchange hoặc một grant phù hợp.

## 5. Sơ đồ lựa chọn cơ chế

~~~mermaid
flowchart TD
    A["Có access token hiện tại"] --> B{"Downstream có thể và được phép nhận chính token này?"}
    B -->|Có| C["Relay cùng access token"]
    B -->|Không| D{"Downstream cần danh tính user/delegation?"}
    D -->|Có| E{"AS hỗ trợ Token Exchange / OBO?"}
    E -->|Có| F["Exchange token cho downstream resource"]
    E -->|Không| G["Thiết kế lại grant/delegation hoặc yêu cầu user flow phù hợp"]
    D -->|Không, chỉ cần service identity| H["Lấy service token mới bằng Client Credentials"]
    C --> I["Downstream vẫn xác minh aud, scope, expiry, binding"]
    F --> I
    H --> I
~~~

**Refresh** là một nhánh khác: nếu access token cần dùng cho cùng authorization context đã hết hạn/sắp hết hạn và client có refresh token hợp lệ, dùng refresh flow để lấy access token thay thế. Refresh không phải cách mặc định để đổi audience hoặc biến user token thành service token.
