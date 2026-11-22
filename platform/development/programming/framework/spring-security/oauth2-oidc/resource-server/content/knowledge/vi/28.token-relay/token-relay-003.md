# Đích nhận phải được phép và thuộc audience phù hợp

## 1. Vì sao token chuyển tiếp phải nhắm đúng đích nhận?

Trong kiến trúc nhiều service, một request có thể đi qua nhiều Resource Server. Ví dụ, người dùng gọi Orders API; Orders API cần gọi Inventory API để đọc tồn kho. Access token người dùng gửi tới Orders API có thể chỉ được cấp cho **orders-api**. Nếu Orders API chuyển nguyên token đó tới Inventory API, token có thể sai audience, sai scope hoặc vượt trust boundary của backend.

**OAuth 2.0 Token Exchange** theo RFC 8693 cho phép một OAuth client gửi security token đầu vào tới Authorization Server (AS) để xin token mới phù hợp với ngữ cảnh sử dụng khác. Client có thể chỉ rõ đích bằng tham số **audience** hoặc **resource**, đồng thời yêu cầu scope cần thiết. AS xác minh client, subject, actor và policy của resource trước khi cấp token.

```text
Browser / Mobile
    │ access token dành cho orders-api
    ▼
Orders API (Resource Server A)
    │ subject_token + target inventory-api
    ▼
Authorization Server / Security Token Service
    │ token mới dành cho inventory-api
    ▼
Inventory API (Resource Server B)
```

Điều cần bảo đảm:

1. Client chỉ yêu cầu token cho **resource đã được phép** trong cấu hình hoặc quan hệ tin cậy.
2. AS chỉ cấp token nếu client, subject và actor được phép truy cập đích đó.
3. Token mới bị giới hạn vào audience của resource đích và scope tối thiểu cần thiết.
4. Resource Server đích tự xác minh token mới và kiểm tra audience của chính nó.
5. Client gọi đúng endpoint đã cấu hình, không dùng token exchange để gửi credential tới URL tùy ý.

> **Quy tắc cốt lõi:** Tham số audience hoặc resource trong token-exchange request chỉ là yêu cầu của client. Nó không tự cấp quyền và không chứng minh token trả về đã dành cho resource đó. AS phải phê duyệt yêu cầu; Resource Server đích phải kiểm tra audience thực tế trên token nhận được.

## 2. Token exchange khác chuyển tiếp access token

```text
Cách 1 — Chuyển tiếp token đầu vào (token relay):

Client ── AT-Orders ──> Orders API ── AT-Orders ──> Inventory API

Cách 2 — Token exchange:

Client ── AT-Orders ──> Orders API
                           │
                           ├── subject_token = AT-Orders
                           ├── audience = inventory-api
                           └── scope = inventory:read
                                   │
                                   ▼
                            Authorization Server
                                   │
                                   └── AT-Inventory
                                           │
                                           ▼
                                   Inventory API
```

Trong cách thứ hai, AS cấp token mới theo policy. Token đầu ra có thể giữ subject là người dùng ban đầu, ghi nhận Orders API là actor đang hành động thay mặt người dùng, chỉ chứa scope đọc inventory thay vì toàn bộ scopes của token đầu vào, có thời hạn ngắn hơn và là JWT hoặc opaque token theo contract của AS.

Token exchange **không tự động thu hồi subject token**. RFC 8693 mô tả exchange là sự kiện một lần; quan hệ vòng đời và revocation giữa token đầu vào và đầu ra phụ thuộc implementation, profile và policy của deployment.

### 2.1. Khi nào nên dùng token exchange?

| Tình huống | Cân nhắc |
| --- | --- |
| Hai service cùng resource boundary và audience | Token relay có thể phù hợp nếu API contract cho phép. |
| Service A gọi B có audience khác | Dùng token exchange hoặc cơ chế cấp credential riêng cho B. |
| Service A gọi B thay mặt user | Exchange giúp giới hạn quyền tại B và biểu diễn subject/actor. |
| Service cần quyền riêng của chính nó | Client credentials hoặc token exchange theo actor/delegation policy. |
| Hai service thuộc trust domains khác nhau | AS trung gian xác minh token đầu vào và cấp token phù hợp trust domain đích. |

Token exchange là extension grant; không phải mọi AS đều hỗ trợ. Client cần biết grant, token types và policy đã triển khai.

## 3. Các thành phần trong RFC 8693

RFC 8693 định nghĩa Token Exchange Grant:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

Các tham số chính:

| Tham số | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| **grant_type** | Có | Token exchange grant URN. |
| **subject_token** | Có | Security token đại diện subject mà token mới được yêu cầu thay mặt. |
| **subject_token_type** | Có | Token type identifier của subject token. |
| **actor_token** | Không | Security token đại diện actor thực hiện hành động thay mặt subject. |
| **actor_token_type** | Khi có actor_token | Token type identifier của actor token. |
| **resource** | Không | URI của protected resource đích theo RFC 8707. |
| **audience** | Không | Tên logic của target service mà token mới sẽ được dùng tại đó. |
| **scope** | Không | Scopes mong muốn trong ngữ cảnh resource/audience đích. |
| **requested_token_type** | Không | Loại token mong muốn được cấp. |

Token type URI thường gặp:

```text
urn:ietf:params:oauth:token-type:access_token
urn:ietf:params:oauth:token-type:refresh_token
urn:ietf:params:oauth:token-type:id_token
urn:ietf:params:oauth:token-type:jwt
```

Phân biệt **token type** và **token format**: access token có thể được biểu diễn bằng JWT hoặc opaque string. Một JWT không tự động là access token; nó cũng có thể là ID token, client assertion hoặc security assertion khác.

### 3.1. Subject token

**subject_token** đại diện bên mà token mới được yêu cầu thay mặt. Trong luồng phổ biến:

```text
subject_token = access token của user đã được Orders API xác thực
subject_token_type = urn:ietf:params:oauth:token-type:access_token
```

AS phải xác minh subject token theo issuer, token type, chữ ký hoặc introspection state và policy phù hợp. Không chỉ decode payload rồi tin claims do client gửi.

### 3.2. Actor token

**actor_token** đại diện bên đang thực hiện hành động thay mặt subject:

```text
Subject = Alice
Actor   = Orders API service
Target  = Inventory API
```

Actor token là optional trong protocol. Nếu request có actor_token thì actor_token_type là bắt buộc. AS phải xác minh cả subject token và actor token theo token type tương ứng.

Không nhầm actor token với client authentication:

- **Client authentication** chứng minh OAuth client đang gọi Token Endpoint là client nào.
- **Actor token** mang thông tin security token về actor theo delegation model.
- **Subject token** mang thông tin về subject mà quyền được yêu cầu thay mặt.

Một request có thể cần cả client authentication và actor token; một thứ không tự thay thế thứ còn lại.

## 4. resource và audience: hai cách chỉ đích nhận

RFC 8693 cho phép client mô tả target service bằng **audience** hoặc **resource**.

### 4.1. audience: tên logic của service

**audience** là tên logic mà client và AS cùng hiểu, ví dụ:

```text
inventory-api
```

Tên này có thể là OAuth client identifier, SAML entity identifier, OIDC issuer identifier hoặc tên service được deployment quy định. Audience values phải có ý nghĩa duy nhất trong phạm vi AS để tránh nhầm kiểu định danh.

### 4.2. resource: Resource Indicator URI

**resource** theo RFC 8707 xác định protected resource bằng URI. Giá trị phải là **absolute URI**, không được chứa fragment. Ví dụ:

```text
https://inventory.example.internal/api/
```

Nên chọn URI cụ thể đủ để nhận diện API. Nếu nhiều ứng dụng nằm trên cùng host, chỉ dùng hostname có thể quá rộng.

### 4.3. resource và audience không phải scope

| Giá trị | Câu hỏi trả lời |
| --- | --- |
| **resource** | Token được yêu cầu để sử dụng tại protected resource URI nào? |
| **audience** | Token được yêu cầu cho target service logic nào? |
| **scope** | Client muốn thực hiện loại hành động nào tại resource đó? |

Ví dụ:

```text
resource = https://inventory.example.internal/api/
audience = inventory-api
scope = inventory:read
```

**scope** không nên bị lạm dụng để encode địa chỉ service. **inventory:read** nói về quyền đọc inventory, không nhất thiết xác định token sẽ được redeem tại API nào.

### 4.4. Không yêu cầu nhiều target nếu chỉ cần một

RFC 8693 mô tả rằng khi có nhiều resource/audience, client đang yêu cầu token dùng được tại tất cả target được liệt kê cùng với các scope yêu cầu. Tập quyền hiệu lực có thể được hiểu là tích Descartes giữa scopes và target services.

Ví dụ yêu cầu:

```text
audience = orders-api
audience = inventory-api
scope = read write
```

có thể rộng hơn nhiều so với:

```text
audience = inventory-api
scope = inventory:read
```

Hãy chỉ yêu cầu một target cụ thể khi một downstream call chỉ cần một service. AS có thể từ chối yêu cầu quá rộng bằng **invalid_target**.

## 5. Token request và response

Giả sử Orders API đã xác thực user bằng access token đầu vào và cần gọi Inventory API chỉ để đọc tồn kho.

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic <orders-service-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&
subject_token=<orders-access-token>&
subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&
resource=https%3A%2F%2Finventory.example.internal%2Fapi%2F&
audience=inventory-api&
scope=inventory%3Aread&
requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
```

Nếu cần actor token:

```http
actor_token=<orders-service-actor-token>&
actor_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
```

Đây là request minh họa. Client phải dùng đúng phương thức client authentication mà AS đã đăng ký (HTTP Basic, private_key_jwt, mTLS hoặc phương thức được hỗ trợ), không tự giả định mọi AS dùng client secret.

Phản hồi thành công:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<inventory-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory:read"
}
```

**issued_token_type** mô tả loại token được cấp; **token_type** mô tả cách sử dụng token. Không nhầm hai field này. AS có thể cấp JWT hoặc opaque token; client nên coi access token là opaque và dùng theo response contract.

### 5.1. Token mới phải được dùng cho đúng backend

```http
GET /api/stock/SKU-100 HTTP/1.1
Host: inventory.example.internal
Authorization: Bearer <inventory-access-token>
```

Inventory API kiểm tra:

- Chữ ký/issuer hoặc introspection state của token.
- Audience hoặc resource binding tương ứng với Inventory API.
- Thời hạn và token profile.
- Scope **inventory:read**.
- Tenant, subject, actor và policy của bản ghi được yêu cầu.

Token exchange thành công ở AS **không thay thế** bước xác minh của Resource Server đích.

## 6. Authorization Server phải phê duyệt target

Client có thể gửi:

```text
audience=payroll-admin-api
scope=payroll:write
```

nhưng điều đó không có nghĩa client được phép nhận token như vậy. AS phải áp dụng policy dựa trên ít nhất:

1. **Client identity** đã xác thực.
2. **Subject token** hợp lệ và danh tính subject.
3. **Actor token** hợp lệ nếu request có actor.
4. Client có được phép exchange subject token này không?
5. Client/actor có được phép hoạt động trên target resource không?
6. Subject có grant, consent hoặc quyền cần thiết không?
7. Scope yêu cầu có nằm trong quyền được phép tại target không?
8. Token profile, lifetime và sender constraint nếu deployment yêu cầu.

Ví dụ:

| Client | Subject | Target | Scope | Kết quả |
| --- | --- | --- | --- | --- |
| Orders service | Alice tenant A | Inventory API | inventory:read | Cho phép nếu Alice và actor được phép. |
| Orders service | Alice tenant A | Payroll API | payroll:write | Từ chối nếu client không được gọi Payroll. |
| Reports service | Alice | Inventory API | inventory:admin | Từ chối nếu scope vượt quyền được delegate. |
| Orders service | Subject token hết hạn/sai issuer | Inventory API | inventory:read | Từ chối subject token. |
| Client chưa đăng ký | Alice | Inventory API | inventory:read | Từ chối client. |

### 6.1. Token exchange không phải quyền tùy chọn audience

Không xây API nội bộ để caller tự quyết định:

```java
// NGUY HIỂM: target lấy trực tiếp từ query/header của caller.
String target = request.getParameter("audience");
return tokenExchange.exchange(subjectToken, target);
```

Nếu caller có thể yêu cầu bất kỳ audience nào, service trung gian có thể trở thành **confused deputy**: nó dùng credential mạnh của chính mình để xin token cho resource mà caller không được phép gọi.

Thay vào đó:

- Map operation nghiệp vụ sang target registration đã cấu hình.
- Chỉ cho phép tập audience/resource URI được phê duyệt.
- Kiểm tra caller có quyền thực hiện operation trước khi exchange.
- AS vẫn phải kiểm tra client, subject và target.
- Downstream service vẫn phải kiểm tra audience/scope.

## 7. Audience của token được cấp và kiểm tra ở Resource Server đích

Trong JWT access token, audience thường nằm ở claim **aud**:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "exp": 1893456000
}
```

Inventory API chỉ chấp nhận token nếu **aud** thỏa contract của nó. Nếu AS dùng resource URI làm audience trực tiếp:

```json
{
  "aud": ["https://inventory.example.internal/api/"]
}
```

AS cũng có thể map resource URI sang audience identifier khác. Client không nên giả định chuỗi resource luôn xuất hiện nguyên văn trong claim aud; cần biết mapping contract của AS.

### 7.1. Audience membership hay exact-single audience?

**Membership**: chấp nhận nếu aud chứa identifier của API:

```java
boolean intendedForApi =
        jwt.getAudience().contains("inventory-api");
```

**Exact-single**: chỉ chấp nhận khi audience list có đúng một phần tử:

```java
boolean onlyThisApi =
        jwt.getAudience().size() == 1
        && jwt.getAudience().contains("inventory-api");
```

Membership phù hợp khi token contract cho phép nhiều audience. Exact-single policy chặt hơn và hữu ích khi tổ chức muốn cấm token dùng chung nhiều resource. Chọn theo security contract và khả năng của AS.

### 7.2. Không so sánh audience bằng substring

Không làm:

```java
// SAI: inventory-api-admin cũng chứa inventory-api.
boolean allowed =
        jwt.getClaims().get("aud").toString()
                .contains("inventory-api");
```

Dùng exact membership trên danh sách audience đã được parse:

```java
boolean allowed =
        jwt.getAudience().contains("inventory-api");
```

### 7.3. Audience khác issuer

**iss** trả lời “ai phát hành token?”. **aud** trả lời “token dành cho resource nào?”. Một token có issuer đúng nhưng audience sai vẫn phải bị từ chối.

```text
iss = https://login.example.test
aud = orders-api

Inventory API:
  expected audience = inventory-api
  result = reject
```

Không dùng chung một issuer validator rồi bỏ qua audience cho các backend.

## 8. resource parameter theo RFC 8707

RFC 8707 định nghĩa resource để client chỉ rõ protected resource. Giá trị phải là absolute URI và không được có fragment. Ví dụ:

```text
resource=https://inventory.example.internal/api/
```

AS dùng resource indicator để xác định policy áp dụng cho target, giới hạn audience, chọn loại/nội dung token, áp dụng encryption hoặc sender constraint nếu deployment yêu cầu, và từ chối resource không được biết hoặc không được phép.

### 8.1. URI định danh resource không nhất thiết là URL gọi HTTP

Resource là **identifier** trong OAuth request. AS có thể map URI đó sang logical resource/audience nội bộ.

```text
OAuth resource identifier:
  https://inventory.example.internal/api/

Configured downstream base URL:
  https://inventory.service.cluster/api/
```

Mapping hai giá trị này nằm trong cấu hình được kiểm soát. Không dùng resource do caller gửi để tự tạo HTTP destination.

### 8.2. Không tạo SSRF bằng resource URI

Nếu service lấy resource URI tùy ý rồi gọi trực tiếp, caller có thể yêu cầu:

```text
resource=http://169.254.169.254/latest/meta-data/
```

Biện pháp:

- Allowlist exact resource identifiers.
- Chỉ nhận URI đã được quản trị/đăng ký.
- Kiểm soát redirects, TLS và egress.
- Tách OAuth resource identifier khỏi downstream network URL.
- Không cho path/query do user tự chọn biến thành audience mới.

## 9. Scope phải phù hợp với target

Scope mô tả loại quyền tại resource:

```text
orders-api:
  orders:read
  orders:write

inventory-api:
  inventory:read
  inventory:reserve

payroll-api:
  payroll:read
```

Một scope tên giống nhau ở hai APIs không nhất thiết có cùng semantics. Không gửi scope của Orders tới Inventory rồi coi đó là quyền tương đương.

### 9.1. Token exchange nên thu hẹp quyền

Token đầu vào:

```json
{
  "aud": ["orders-api"],
  "scope": "orders:read orders:write profile:read"
}
```

Orders API chỉ cần đọc tồn kho. Token đầu ra nên có:

```json
{
  "aud": ["inventory-api"],
  "scope": "inventory:read"
}
```

Không sao chép toàn bộ scopes đầu vào sang token mới. AS phải tính quyền được phép từ subject, actor, client, target và policy.

### 9.2. Đừng yêu cầu nhiều audiences để tiện gọi nhiều service

Nếu một workflow gọi Inventory và Billing, có thể lấy hai token:

```text
Token 1:
  aud = inventory-api
  scope = inventory:read

Token 2:
  aud = billing-api
  scope = billing:charge
```

Việc này thường giảm blast radius nếu một token bị lộ. Nếu deployment chủ động cấp token đa audience, phải hiểu chính xác resource nào chấp nhận token và scopes nào có hiệu lực ở từng nơi.

## 10. Delegation và impersonation

RFC 8693 phân biệt hai mô hình:

### 10.1. Impersonation

Actor A được cấp token mà trong context quyền được cấp, resource đích coi như đang làm việc với subject B. Identity trên token có thể tiếp tục là subject. Impersonation rất mạnh và có thể làm audit khó phân biệt actor nếu hệ thống không ghi nhận actor ở nơi khác.

### 10.2. Delegation

Actor A giữ identity riêng và hành động đại diện cho subject B. Token có thể mang cả subject và actor:

```json
{
  "iss": "https://login.example.test",
  "sub": "alice",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "act": {
    "sub": "orders-service"
  }
}
```

**act** là actor claim theo RFC 8693. Với delegation chain, act có thể lồng nhau; actor ngoài cùng là actor hiện tại, các actor lồng bên trong là lịch sử trước đó. Resource Server nên dùng top-level claims và current actor cho access control; nested actor chain mang tính thông tin lịch sử theo RFC.

### 10.3. may_act

Claim **may_act** có thể cho biết một bên được phép trở thành actor thay mặt subject. AS có thể dùng claim này khi quyết định exchange. Đây không phải claim mà client tự thêm vào để tự cấp quyền; nó phải đến từ token/nguồn đáng tin và được AS xác minh.

### 10.4. Client authentication không thay actor authorization

Client xác thực thành công bằng client secret chỉ chứng minh client identity. AS vẫn cần kiểm tra client đó có được phép exchange subject token cụ thể, dùng target resource cụ thể, xin scopes cụ thể và đóng vai actor/impersonate subject hay không.

## 11. Chuỗi service-to-service

```text
Browser
  │ AT-A (aud=frontend-api)
  ▼
Frontend API
  │ exchange AT-A → AT-B (aud=orders-api)
  ▼
Orders API
  │ exchange AT-B → AT-C (aud=inventory-api)
  ▼
Inventory API
```

Mỗi bước cần:

1. Resource Server hiện tại xác minh token nhận được.
2. Service chỉ exchange sang target đã đăng ký.
3. AS xác minh subject/actor/client và target policy.
4. Token mới chỉ có audience và scope cần thiết.
5. Downstream Resource Server xác minh token mới.

Không dùng token có audience wildcard cho cả chuỗi chỉ để giảm số lần exchange. Một service bị xâm phạm không nên có thể dùng token đó tại mọi backend.

## 12. Spring Security hỗ trợ Token Exchange từ phiên bản nào?

Spring Security cung cấp OAuth2 Client support cho token-exchange grant từ **6.3**. Đây là hỗ trợ ở phía OAuth2 Client để gọi Token Endpoint; không có nghĩa mọi AS tự động bật grant hoặc mọi Resource Server tự động chấp nhận token đầu ra.

| Stack | Provider | Token response client |
| --- | --- | --- |
| Servlet | **TokenExchangeOAuth2AuthorizedClientProvider** | **RestClientTokenExchangeTokenResponseClient** |
| Reactive/WebFlux | **TokenExchangeReactiveOAuth2AuthorizedClientProvider** | **WebClientReactiveTokenExchangeTokenResponseClient** |

Provider xử lý grant token-exchange. Subject token được resolve từ context; actor token không được resolve mặc định trong cấu hình cơ bản. Có thể cấu hình resolver bằng **setSubjectTokenResolver** và **setActorTokenResolver**.

**Lưu ý version:** API cụ thể và cơ chế tự động đăng ký provider có thể khác giữa các dòng Spring Security. Dùng dependency management của Spring Boot và Javadoc đúng version đang chạy.

## 13. Cấu hình ClientRegistration

Ví dụ Spring Boot:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-exchange:
            provider: internal-as
            client-id: orders-service
            client-secret: <secret-from-secret-manager>
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
            client-authentication-method: client_secret_basic
        provider:
          internal-as:
            token-uri: https://login.example.test/oauth2/token
```

Đây là cấu hình minh họa cho confidential service client dùng HTTP Basic. AS có thể yêu cầu private_key_jwt, mTLS hoặc cách khác; chọn theo registration đã cấp. Không commit secret vào Git.

Các target như **inventory-api** hoặc URI Inventory nên được cấu hình/allowlist ở ứng dụng. Không để caller tùy ý thay registration hoặc Token Endpoint.

## 14. Servlet: TokenExchangeOAuth2AuthorizedClientProvider

Ví dụ cấu hình manager:

```java
@Configuration
class TokenExchangeClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider =
                new TokenExchangeOAuth2AuthorizedClientProvider();

        OAuth2AuthorizedClientProvider providers =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .provider(exchangeProvider)
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(providers);
        return manager;
    }
}
```

Đây là cấu hình Servlet OAuth2 Client. Provider mặc định resolve subject token từ principal nếu principal là OAuth2Token (ví dụ JwtAuthenticationToken). Nếu subject token ở nguồn khác, cấu hình setSubjectTokenResolver. Actor token không được resolve mặc định; nếu deployment yêu cầu, cấu hình setActorTokenResolver.

## 15. Reactive/WebFlux: token exchange client

Spring Security có provider reactive từ 6.3. Khung cấu hình:

```java
@Configuration
class ReactiveTokenExchangeConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        TokenExchangeReactiveOAuth2AuthorizedClientProvider exchangeProvider =
                new TokenExchangeReactiveOAuth2AuthorizedClientProvider();

        ReactiveOAuth2AuthorizedClientProvider providers =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .provider(exchangeProvider)
                        .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(providers);
        return manager;
    }
}
```

Đây là khung manager reactive dùng ServerOAuth2AuthorizedClientRepository. Service/background flow không có ServerWebExchange có thể dùng service-backed reactive manager tương ứng. Kiểm tra đúng package/import theo version; không trộn Servlet OAuth2AuthorizedClientManager vào WebFlux.

### 15.1. Thêm audience vào token-exchange request

Có thể tùy biến WebClientReactiveTokenExchangeTokenResponseClient:

```java
@Bean
WebClientReactiveTokenExchangeTokenResponseClient tokenExchangeResponseClient() {
    WebClientReactiveTokenExchangeTokenResponseClient client =
            new WebClientReactiveTokenExchangeTokenResponseClient();

    client.addParametersConverter(grantRequest -> {
        MultiValueMap<String, String> parameters =
                new LinkedMultiValueMap<>();

        if ("inventory-exchange".equals(
                grantRequest.getClientRegistration().getRegistrationId())) {
            parameters.set(OAuth2ParameterNames.AUDIENCE,
                    "inventory-api");
        }

        return parameters;
    });

    return client;
}
```

Nếu AS yêu cầu RFC 8707 resource indicator, có thể thêm tham số resource với URI đã được phê duyệt:

```java
parameters.set(
        "resource",
        "https://inventory.example.internal/api/");
```

Chỉ gửi cả audience và resource khi AS contract quy định cách hiểu chúng. Hai tham số cùng có mặt có thể biểu thị nhiều target services, không phải lúc nào cũng là hai cách viết thay thế cho cùng một target. Nếu chỉ cần một target, thường chỉ cấu hình một tham số đã thống nhất với AS.

### 15.2. Gắn response client vào provider

```java
exchangeProvider.setAccessTokenResponseClient(
        tokenExchangeResponseClient);
```

Phần này cần được nối vào cấu hình manager ở trên.

### 15.3. Subject token và actor token trong reactive flow

Có thể cấu hình resolver:

```java
exchangeProvider.setSubjectTokenResolver(context -> {
    Object principal = context.getPrincipal().getPrincipal();

    if (principal instanceof Jwt jwt) {
        return Mono.just(jwt);
    }

    return Mono.error(new IllegalStateException(
            "No trusted subject token is available"));
});

exchangeProvider.setActorTokenResolver(context ->
        actorTokenService.currentActorToken(context));
```

actorTokenService là abstraction do ứng dụng triển khai. Không lấy actor token từ header tùy ý hoặc request body chưa xác minh. Nếu không cần actor token, không cấu hình resolver và không gửi actor token parameter.

### 15.4. Gọi downstream API

Ví dụ reactive service:

```java
public Mono<InventoryDto> getInventory(
        Authentication authentication,
        String sku) {

    OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest
                    .withClientRegistrationId("inventory-exchange")
                    .principal(authentication)
                    .build();

    return authorizedClientManager.authorize(authorizeRequest)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException(
                            "Token exchange did not produce an authorized client")))
            .flatMap(authorizedClient ->
                    webClient.get()
                            .uri(inventoryBaseUrl + "/stock/{sku}", sku)
                            .headers(headers -> headers.setBearerAuth(
                                    authorizedClient.getAccessToken()
                                            .getTokenValue()))
                            .retrieve()
                            .bodyToMono(InventoryDto.class));
}
```

authorizedClientManager, webClient, inventoryBaseUrl và InventoryDto do ứng dụng cấu hình. Token mới lấy từ registration inventory-exchange; URL downstream lấy từ cấu hình service đã duyệt.

Không làm:

```java
// SAI: lấy URL đích từ query parameter của người dùng.
.uri(request.getParameter("resource"))
```

OAuth resource identifier và URL HTTP destination phải được ràng buộc bằng configuration mapping.

## 16. Resource Server đích phải xác minh token mới

Token exchange là nhiệm vụ của OAuth2 Client; Inventory API vẫn là Resource Server độc lập. Với JWT, cấu hình cần giữ issuer và audience validation:

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(inventoryIssuer);

OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("inventory-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Token is not intended for Inventory API",
                                null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults, audience));
```

Đừng chỉ kiểm tra issuer. Token do issuer đúng phát hành nhưng có aud=orders-api không dành Inventory API.

Với opaque token, introspection response phải cung cấp thông tin resource/audience hoặc AS phải bảo đảm resource binding theo contract được xác minh. Resource Server không được suy luận rằng token active ở AS thì có thể gọi mọi API.

## 17. Multi-tenant resource và audience

Với multi-tenant API, resource identifier đôi khi cần bao gồm tenant hoặc namespace:

```text
https://api.example.test/tenants/alpha/inventory/
https://api.example.test/tenants/bravo/inventory/
```

Nếu hai URI đại diện hai security boundaries khác nhau, AS có thể cấp audience khác nhau. RFC 8707 khuyến nghị client cung cấp resource URI cụ thể nhất mà nó biết.

### 17.1. Tenant ID không phải tham số để client tự chọn

Không nhận tenant=bravo từ request rồi tự tạo resource URI Bravo. Ứng dụng phải xác minh subject có membership trong tenant, client được phép exchange cho tenant đó và AS có policy tương ứng.

### 17.2. Audience đúng vẫn chưa đủ cho object authorization

Token có aud=inventory-api và inventory:read chỉ cho biết token dành cho API và có quyền chức năng đọc theo contract. API vẫn cần xác minh user/service được phép đọc SKU hoặc warehouse thuộc tenant nào.

Audience giới hạn **resource server**, scope giới hạn **hành động**, domain policy giới hạn **đối tượng dữ liệu**.

## 18. Lỗi token exchange

RFC 8693 định nghĩa invalid_target khi AS không thể hoặc không muốn cấp token cho resource/audience được yêu cầu.

| Lỗi | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| invalid_request | Thiếu subject token/type, actor token thiếu actor type, token đầu vào sai hoặc không được chấp nhận. | Kiểm tra request/token contract. |
| invalid_target | Resource/audience không được biết, không được client phép yêu cầu hoặc không phù hợp policy. | Dừng; kiểm tra target registration và quyền. |
| invalid_scope | Scope không hợp lệ hoặc vượt quyền được cấp. | Thu hẹp scope hoặc thực hiện authorization/consent phù hợp. |
| invalid_client | Client authentication tại AS sai. | Sửa client registration/secret/certificate. |
| unauthorized_client | Client không được phép dùng token-exchange grant. | Kiểm tra AS grant policy. |
| unsupported_grant_type | AS không hỗ trợ grant hoặc cấu hình sai. | Xác nhận AS capability/version. |
| HTTP 429 | Rate limit tại AS. | Backoff theo policy. |
| HTTP 5xx/timeout | AS hoặc network unavailable. | Fail closed; phân loại dependency failure. |

### 18.1. invalid_target không nên được “sửa” bằng wildcard

Nếu AS từ chối target, không gửi nhiều audience hơn, dùng wildcard, bỏ scope để hy vọng token được cấp, chọn resource URL từ input khác của caller hoặc tắt target validation. Hãy kiểm tra client-target authorization và resource registration.

### 18.2. Không fallback sang token đầu vào

Nếu exchange thất bại vì target không được phép, không gửi lại subject token tới downstream API để “thử xem có được không”. Đó chính là ranh giới mà token exchange đang bảo vệ.

## 19. Ma trận kiểm thử: target phải được phép và audience phải khớp

### 19.1. Ma trận target/audience

| Case | Client yêu cầu | Policy AS | Token đầu ra | Kết quả |
| --- | --- | --- | --- | --- |
| TE-01 | Inventory URI, inventory:read | Client và subject được phép | aud=inventory-api | Inventory API chấp nhận. |
| TE-02 | audience=payroll-api | Orders client không được phép | Không cấp; invalid_target | Không gọi Payroll API. |
| TE-03 | Resource URI không đăng ký | Resource không được biết | invalid_target | Không gọi target lạ. |
| TE-04 | Inventory, inventory:admin | Subject chỉ có read | Từ chối hoặc giới hạn theo policy | Không cấp quyền admin. |
| TE-05 | Inventory, read | Subject token hết hạn/sai issuer | Từ chối theo AS contract | Không cấp token. |
| TE-06 | Inventory, read | Client authentication sai | invalid_client | Sửa client credentials. |
| TE-07 | Inventory | Actor không được phép đại diện subject | Từ chối | Không impersonate/delegate trái phép. |
| TE-08 | Inventory | AS trả aud=orders-api | Downstream từ chối | Không tin riêng HTTP 200 của AS. |
| TE-09 | Inventory | Token đúng audience nhưng thiếu scope | Authentication có thể pass | 403. |
| TE-10 | Inventory | Token đúng audience/scope nhưng tenant sai | Domain policy từ chối | 403/404. |

### 19.2. Ma trận Resource Server đích

| Token nhận bởi Inventory API | Issuer | Audience | Kỳ vọng |
| --- | --- | --- | --- |
| Token đúng | Trusted AS | inventory-api | Pass authentication nếu claims khác hợp lệ. |
| Token Orders | Trusted AS | orders-api | 401 invalid_token. |
| Token Payroll | Trusted AS | payroll-api | 401 invalid_token. |
| Token đa audience có Inventory | Trusted AS | [orders-api, inventory-api] | Theo membership/single-audience policy. |
| Token issuer không tin | Untrusted AS | inventory-api | 401. |
| Token chữ ký sai | Claimed issuer đúng | inventory-api | 401. |
| Token hết hạn | Trusted AS | inventory-api | 401. |
| Token đúng audience nhưng thiếu scope | Trusted AS | inventory-api | 403. |

### 19.3. Ma trận chống confused deputy

Test cần xác nhận:

1. Caller không thể thay audience bằng request header/query.
2. Caller không thể thay resource bằng URL bất kỳ.
3. Client không thể exchange subject token cho target ngoài allowlist.
4. AS từ chối client-target combination không được cấp quyền.
5. Token exchange thất bại thì downstream service không được gọi.
6. Client không fallback sang token đầu vào.
7. Downstream URL luôn đến từ cấu hình đã phê duyệt.
8. Subject/actor identity được ghi nhận theo delegation policy.

## 20. Kiểm thử Spring Security

### 20.1. Kiểm tra token request parameters

Mock Token Endpoint nên assert:

```text
grant_type = urn:ietf:params:oauth:grant-type:token-exchange
subject_token = token đầu vào đã xác minh
subject_token_type = urn:ietf:params:oauth:token-type:access_token
audience = inventory-api (nếu deployment dùng)
resource = URI đã cấu hình (nếu deployment dùng)
scope = inventory:read
client authentication = đúng registration
```

Nếu có actor token, assert cả actor_token và actor_token_type. Không ghi raw tokens hoặc client secret vào test logs.

### 20.2. Kiểm tra token response

Khi AS mock trả token mới:

- Client đọc access_token.
- Client xử lý issued_token_type và token_type.
- Client lưu expiry/metadata theo authorized-client store.
- Client gọi đúng downstream URL đã cấu hình.
- Header gửi đi chứa token đầu ra, không phải subject token.

### 20.3. Kiểm tra downstream Resource Server

Dùng JWT test có chữ ký thật hoặc opaque introspection mock:

1. aud=inventory-api và scope=inventory:read → positive.
2. aud=orders-api → reject.
3. aud=payroll-api → reject.
4. Đúng aud nhưng thiếu scope → 403.
5. Đúng aud/scope nhưng tenant sai → 403/404.
6. Sai issuer/chữ ký/hết hạn → reject.

Không dùng mockJwt() rồi kết luận audience validator đã chạy; mock principal có thể bypass decoder. Gửi signed test JWT qua filter chain khi muốn kiểm tra toàn bộ authentication.

## 21. Security considerations

### 21.1. Least privilege

Yêu cầu một target và scopes nhỏ nhất cần thiết. Token ngắn hạn, token đầu ra riêng cho resource, không cấp quyền quản trị chỉ vì service trung gian có quyền cao.

### 21.2. Client authentication tại Token Endpoint

RFC 8693 nhấn mạnh client authentication cho phép AS đánh giá client nào được phép nhận delegation/impersonation. Không bật token exchange ẩn danh nếu không có lý do và trust model được kiểm soát chặt.

### 21.3. Validate subject và actor token

AS phải xác minh token type, issuer, chữ ký/introspection state, expiry và policy cho cả subject token lẫn actor token. Không dùng sub từ payload chưa xác minh.

### 21.4. Bảo vệ token trên đường truyền

Subject token và actor token được gửi tới Token Endpoint. Dùng TLS, không log form body hoặc Authorization header, không lưu token thô trong tracing/exception.

### 21.5. Giới hạn target và scope

Không yêu cầu nhiều target chỉ để tiện. Mỗi target bổ sung mở rộng bề mặt sử dụng của token. AS nên có allowlist/resource registry và policy theo client/subject/actor.

### 21.6. Đừng tin resource như một lệnh gọi mạng

Resource indicator là định danh cho AS policy. Nó không được phép tự quyết định host mà service sẽ kết nối. Downstream destination cần cấu hình độc lập và network egress control.

### 21.7. Giữ actor trong audit

Với delegation, ghi nhận subject và actor đã xác minh. Không chỉ ghi subject nếu cần truy vết service nào thực hiện hành động. Token claims chỉ chứa lượng thông tin tối thiểu cần thiết.

### 21.8. Revocation và token lifetime

Token exchange không tự làm token đầu vào hết hạn. Token đầu ra có thể sống độc lập; nếu cần lan truyền revocation, AS/Resource Servers phải có cơ chế cụ thể như introspection, short lifetime, token family/version hoặc event propagation.

## 22. Các sai lầm thường gặp

1. **Coi audience request parameter là quyền:** audience=inventory-api chỉ là yêu cầu; AS phải phê duyệt và Resource Server phải xác minh.
2. **Dùng scope thay resource:** inventory:read nói về quyền, không tự xác định token dành API nào.
3. **Forward token ban đầu tới backend:** token đầu vào có thể chỉ dành API hiện tại.
4. **Cấp token đa audience quá rộng:** nhiều target làm tăng blast radius.
5. **Client tự chọn resource URI:** dễ tạo confused deputy/SSRF.
6. **Chỉ xác thực client mà không kiểm tra subject:** client được nhận diện không có nghĩa subject token bất kỳ đều được exchange.
7. **Nhầm client identity với actor identity:** hai khái niệm khác nhau trong delegation.
8. **Bỏ audience validator ở downstream:** AS trả token không miễn Resource Server nhiệm vụ xác minh aud.
9. **Token đầu ra có scope rộng hơn đầu vào:** không tự nâng quyền; AS phải quyết định theo policy.
10. **Bỏ qua issued_token_type:** token type và token representation có ý nghĩa khác nhau.
11. **Giả định mọi AS hỗ trợ RFC 8693:** cần xác nhận AS triển khai grant và client được phép dùng.
12. **Giả định token đầu ra luôn là JWT:** AS có thể cấp opaque token.
13. **Coi token exchange là refresh grant:** exchange đổi security token theo subject/actor/target, không chỉ gia hạn token cũ.
14. **Dùng actor quyền cao mặc định:** phải gắn actor đúng với hành động và policy.

## 23. Tình huống thực tế

### A. Orders API đọc Inventory

Orders API xác thực token người dùng có audience Orders. Nó exchange subject token sang token aud=inventory-api, scope inventory:read. Inventory API xác minh audience và scope trước khi trả tồn kho.

### B. Orders API yêu cầu Payroll

Client gửi audience=payroll-api, nhưng AS policy không cho Orders service gọi Payroll. AS trả invalid_target; ứng dụng dừng và không thử token ban đầu tại Payroll.

### C. Token đầu ra có audience sai

AS bị cấu hình lỗi và trả token aud=orders-api dù request yêu cầu Inventory. Client không nên tin chỉ vì HTTP 200; Inventory API phải từ chối token. Integration test phát hiện mismatch.

### D. Delegation từ user sang service

Alice gọi Orders API. Orders API là actor, Alice là subject. AS cấp token có subject Alice và actor Orders service, scope chỉ đọc inventory. Inventory API audit cả hai danh tính.

### E. Impersonation cho hệ thống legacy

Một hệ thống cũ chỉ hiểu user identity. AS có thể cấp token impersonation giới hạn thời gian/scope cho service. Vì impersonation mạnh, chỉ bật cho client/target đã duyệt và ghi audit.

### F. Multi-tenant resource URI

Orders API cần Inventory của tenant Alpha. Nó chỉ được chọn resource URI Alpha sau khi xác minh subject có membership. Caller không thể thay URI thành tenant Bravo bằng header.

### G. Downstream token opaque

AS cấp opaque access token thay vì JWT. Inventory API introspect token, kiểm tra active, audience/resource binding và scope. Orders API không decode token hoặc tự suy luận claims.

### H. Token exchange qua nhiều hop

Orders API nhận token từ Gateway, exchange sang Inventory. Nếu Inventory tiếp tục gọi Warehouse, nó chỉ exchange tiếp khi policy cho phép và phải giữ delegation chain phù hợp. Không tự động truyền toàn bộ scopes/actor history.

## 24. Câu hỏi tự kiểm tra

**1. Vì sao cần token exchange khi gọi backend khác?** Token đầu vào có thể chỉ dành cho API hiện tại; exchange cấp credential mới phù hợp resource đích.

**2. Grant type URI của RFC 8693 là gì?** urn:ietf:params:oauth:grant-type:token-exchange.

**3. subject_token là gì?** Token đại diện subject mà token mới được yêu cầu thay mặt.

**4. actor_token là gì?** Token đại diện actor thực hiện hành động thay mặt subject; optional, nhưng khi có phải có actor_token_type.

**5. Client authentication có thay actor token không?** Không. Nó xác định OAuth client ở Token Endpoint; actor token thể hiện actor theo delegation contract.

**6. audience và resource khác nhau thế nào?** Audience là tên logic target service; resource là URI resource indicator.

**7. scope xác định điều gì?** Hành động/quyền mong muốn tại resource, không phải nơi token được redeem.

**8. Client gửi audience=inventory-api thì AS bắt buộc cấp token không?** Không. AS phải xác minh client, subject, actor, target và scope policy; có thể trả invalid_target.

**9. Token đầu ra có luôn là JWT không?** Không; có thể là opaque token hoặc token type khác.

**10. Resource Server đích có cần kiểm tra aud không?** Có. Token mới phải dành đúng resource và vượt các kiểm tra khác.

**11. Có nên yêu cầu nhiều audiences để gọi nhiều backend không?** Chỉ khi policy chủ ý cho phép; thường nên một target cho mỗi downstream call.

**12. act là gì?** Actor claim theo RFC 8693, có thể biểu diễn actor hiện tại và delegation chain.

**13. may_act có tự cấp quyền cho client không?** Không. Nó là thông tin về actor được phép theo token/policy đã xác minh.

**14. Token exchange có tự thu hồi subject token không?** Không; quan hệ revocation phụ thuộc deployment.

**15. Spring Security hỗ trợ token-exchange client từ phiên bản nào?** Provider Servlet và reactive có từ Spring Security 6.3.

**16. Provider reactive mặc định resolve actor token không?** Không; actor token resolver cần cấu hình nếu deployment yêu cầu.

**17. Có được dùng resource URI từ query parameter để gọi downstream không?** Không. Target phải nằm trong allowlist/cấu hình, và HTTP destination phải được kiểm soát riêng.

**18. Token đầu vào có orders:write, có thể exchange sang inventory:admin không?** Chỉ nếu AS policy cho phép rõ ràng; client không thể tự nâng quyền.

**19. Vì sao token mới phải có lifetime phù hợp?** Giảm thời gian sử dụng credential nếu bị lộ và giới hạn delegated authority.

**20. Khi AS trả invalid_target, có nên fallback sang token đầu vào?** Không. Phải dừng vì target không được phép hoặc không hợp lệ.

## 25. Tài liệu tham khảo

- **RFC 8693 — OAuth 2.0 Token Exchange:** grant type, subject/actor token, resource/audience/scope, response và delegation/impersonation claims. https://www.rfc-editor.org/rfc/rfc8693
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource URI, audience restriction và invalid_target. https://www.rfc-editor.org/rfc/rfc8707
- **RFC 6749 — OAuth 2.0 Authorization Framework:** client authentication, token endpoint và access token request/response. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 7662 — OAuth 2.0 Token Introspection:** active state và metadata opaque token. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** sử dụng access token tại Resource Server. https://www.rfc-editor.org/rfc/rfc6750
- **Spring Security Reference 7.0 — Servlet OAuth2 Client Authorization Grants / Token Exchange:** https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- **Spring Security Reference 6.5 — Reactive OAuth2 Client Authorization Grants / Token Exchange:** https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html
- **Spring Security API — TokenExchangeOAuth2AuthorizedClientProvider:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/TokenExchangeOAuth2AuthorizedClientProvider.html
- **Spring Security API — TokenExchangeReactiveOAuth2AuthorizedClientProvider:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/TokenExchangeReactiveOAuth2AuthorizedClientProvider.html
- **Spring Security API — TokenExchangeGrantRequest:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/endpoint/TokenExchangeGrantRequest.html

## 26. Kết luận

Khi một service cần gọi backend khác thay mặt người dùng hoặc service khác, **token exchange** cho phép đổi subject token thành credential mới phù hợp đích nhận. Client mô tả target bằng resource URI hoặc audience logic, đồng thời yêu cầu scope tối thiểu. AS phải xác minh client, subject, actor và quyền truy cập target; Resource Server đích phải kiểm tra audience thực tế của token mới.

Spring Security hỗ trợ token-exchange grant ở OAuth2 Client từ **6.3**, cả Servlet lẫn reactive. Các provider token-exchange giúp quản lý flow, còn response clients cho phép tùy chỉnh request parameters như audience khi AS yêu cầu.

Đích nhận chỉ an toàn khi được kiểm soát qua **allowlist/resource registry**, được AS phê duyệt và được Resource Server đích xác minh. Không dùng target do caller tùy ý gửi, không cấp nhiều audiences/scopes quá rộng, không fallback sang token đầu vào khi exchange bị từ chối. Mỗi downstream call cần token đúng audience, đúng scope, đúng subject/actor và đúng tenant.
