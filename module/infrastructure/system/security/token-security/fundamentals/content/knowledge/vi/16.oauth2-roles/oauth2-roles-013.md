# Metadata endpoint

Giả sử ứng dụng `orders-web` muốn dùng OAuth 2.0/OpenID Connect (OIDC) với máy chủ danh tính có **issuer** là `https://id.example.test`. Ứng dụng phải biết gửi người dùng tới đâu để đăng nhập, đổi authorization code ở đâu và lấy khóa công khai nào để kiểm tra ID token. Trong khi đó, API `orders-api` cần xác minh access token nhưng **không được tự tin một khóa hay issuer tùy ý do token khai báo**.

**Metadata endpoint** giải quyết phần **khám phá thông tin cấu hình**: một tài liệu JSON công bố các endpoint và khả năng của authorization server (AS) hoặc OpenID Provider (OP). Nó **không cấp quyền cho người dùng, không cấp access token và không tự xác thực JWT**. Phải bắt đầu từ issuer tin cậy, lấy metadata qua kết nối được bảo vệ, đối chiếu issuer, rồi thực hiện đúng quy tắc riêng của từng giao thức.

Bài thuộc chương **OAuth2 roles** trong module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Nội dung tập trung vào vai trò của client, AS, resource server khi dùng **RFC 8414** và **OIDC Discovery**, phân biệt metadata với JWKS/introspection/revocation, liên hệ JWT–opaque token, issuer–audience–scope, caching/key rotation, triển khai Spring Security và các tình huống bảo mật.

## 1. Metadata endpoint phục vụ những vai trò nào?

Trong OAuth 2.0, cần phân biệt bốn vai trò:

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| **Resource owner** | Chủ thể nắm quyền với tài nguyên và tham gia cấp quyền theo grant/chính sách. | Người dùng sở hữu đơn hàng. |
| **Client** | Xin quyền truy cập và dùng access token để gọi resource server. | Ứng dụng `orders-web` hoặc mobile app. |
| **Authorization server (AS)** | Xử lý grant, cấp access/refresh token, công bố metadata, JWKS và dịch vụ liên quan. | `https://id.example.test`. |
| **Resource server (RS)** | Xác minh access token, kiểm tra scope/audience và quyền trên tài nguyên. | `orders-api`. |

Với OIDC, **OpenID Provider (OP)** hỗ trợ lớp đăng nhập danh tính trên OAuth 2.0 và **Relying Party (RP)** là client dùng ID token. Một OP thường cũng là authorization server nhưng **ID token** và **access token** có mục đích khác nhau.

```mermaid
flowchart TD
    U[Resource Owner] --> C[OAuth Client / OIDC RP]
    C -->|Khám phá cấu hình từ issuer tin cậy| M[AS/OP Metadata Endpoint]
    M -->|Authorization, token, JWKS URIs| C
    C -->|Authorization Code + PKCE| AS[Authorization Server / OP]
    AS -->|Access token, ID token khi OIDC| C
    C -->|Bearer access token| RS[Resource Server]
    RS -->|JWKS hoặc introspection từ AS tin cậy| AS
    RS -->|Kiểm tra quyền đối tượng| DATA[(Protected resource)]
```

**AS/OP là bên công bố metadata**; OAuth/OIDC client dùng nó để khám phá luồng xác thực, còn RS có thể dùng metadata và JWKS để kiểm tra access token theo profile. Metadata được tải/cached lúc cần, không có yêu cầu RS phải gọi lại metadata cho mỗi HTTP request.

## 2. Định nghĩa metadata endpoint và hai chuẩn phổ biến

**OAuth 2.0 Authorization Server Metadata (RFC 8414)** định nghĩa tài liệu metadata JSON của AS. Với issuer không có path:

```text
Issuer:
https://id.example.test

OAuth AS metadata:
https://id.example.test/.well-known/oauth-authorization-server
```

**OpenID Connect Discovery 1.0** định nghĩa OP configuration document:

```text
OIDC provider configuration:
https://id.example.test/.well-known/openid-configuration
```

Cả hai đều là **well-known endpoints** giúp tìm cấu hình, nhưng không có nghĩa tài liệu và các trường bắt buộc giống hệt nhau.

| Tiêu chí | RFC 8414 | OIDC Discovery |
|---|---|---|
| Trọng tâm | Khả năng và endpoint của OAuth authorization server. | Cấu hình OpenID Provider cho đăng nhập OIDC. |
| Well-known path phổ biến | `/.well-known/oauth-authorization-server` | `/.well-known/openid-configuration` |
| Thông tin điển hình | `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, grant/response capabilities. | Các trường tương tự cùng `userinfo_endpoint`, `subject_types_supported`, `id_token_signing_alg_values_supported`. |
| Bên tiêu thụ | OAuth client, RS và công cụ tích hợp. | OIDC relying party và thành phần xử lý profile OIDC. |
| Có tự cấp quyền? | Không. | Không. |

Tùy nhà cung cấp, một issuer có thể hỗ trợ cả hai well-known locations; không tự giả định mọi AS đều hỗ trợ OIDC. Nếu API chỉ dùng opaque access token, metadata không nhất thiết thay được một hợp đồng introspection đã triển khai.

## 3. Ví dụ phản hồi RFC 8414

Yêu cầu HTTP:

```http
GET /.well-known/oauth-authorization-server HTTP/1.1
Host: id.example.test
Accept: application/json
```

Tài liệu trả về minh họa:

```json
{
  "issuer": "https://id.example.test",
  "authorization_endpoint": "https://id.example.test/oauth2/authorize",
  "token_endpoint": "https://id.example.test/oauth2/token",
  "jwks_uri": "https://id.example.test/oauth2/jwks",
  "response_types_supported": ["code"],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ],
  "code_challenge_methods_supported": ["S256"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "scopes_supported": ["orders.read", "orders.write"],
  "introspection_endpoint": "https://id.example.test/oauth2/introspect",
  "revocation_endpoint": "https://id.example.test/oauth2/revoke"
}
```

Đây là **cấu hình minh họa** cho một AS giả định. AS thật có thể hỗ trợ grant types, scope, PKCE methods hoặc endpoints khác. Một số trường là optional theo profile; không được đoán endpoint mới khi metadata không công bố mà chưa có hợp đồng cấu hình.

**`response_types_supported`, `grant_types_supported`, `scopes_supported` mô tả khả năng của AS**, không phải những thứ mọi client có quyền sử dụng. Client `orders-web` không được tự xin `client_credentials` hoặc mọi scope chỉ vì metadata cho biết AS có hỗ trợ.

## 4. Ví dụ OIDC Discovery

Một OpenID Provider có thể trả:

```json
{
  "issuer": "https://id.example.test",
  "authorization_endpoint": "https://id.example.test/oauth2/authorize",
  "token_endpoint": "https://id.example.test/oauth2/token",
  "jwks_uri": "https://id.example.test/oauth2/jwks",
  "userinfo_endpoint": "https://id.example.test/oidc/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email", "orders.read"],
  "claims_supported": ["sub", "iss", "aud", "exp", "iat", "email"]
}
```

Ở đây, `userinfo_endpoint` là endpoint trả thông tin người dùng theo access token và chính sách OIDC, **khác với metadata endpoint**. `claims_supported` mô tả claims OP có thể hỗ trợ, **không bảo đảm từng token hoặc response đều chứa tất cả claims**.

Với OIDC, client xác minh **ID token** theo `iss`, `aud` là client ID, chữ ký, thời gian và những điều kiện `nonce`/`azp` khi áp dụng. API nghiệp vụ chỉ chấp nhận **access token đúng audience**, không dùng ID token thay thế dù do cùng OP ký.

## 5. Issuer có path và cách ghép well-known URI

Khi issuer là `https://id.example.test`, hai URL well-known dễ nhớ. Nhưng issuer có thể chứa path theo tenant:

```text
https://id.example.test/tenant-a
```

Theo quy tắc URI của **RFC 8414**, well-known path được chèn giữa host và path của issuer. Ví dụ:

```text
https://id.example.test/.well-known/oauth-authorization-server/tenant-a
```

Theo quy tắc thông dụng của **OIDC Discovery**, hậu tố well-known được nối sau issuer path:

```text
https://id.example.test/tenant-a/.well-known/openid-configuration
```

Hai dạng này **không nên bị tráo đổi**. Một thư viện discovery nên xây URL theo chuẩn/profile mà nó hỗ trợ. Với multi-tenant issuer, phải xác minh `issuer` trong JSON nhận được **khớp chính xác issuer đã được cấu hình**, tránh token của tenant này bị gán nguồn tin cậy của tenant khác.

Không xây issuer tin cậy từ query parameter hoặc header do client tùy ý gửi để rồi tự fetch các URL đó.

## 6. Các metadata fields quan trọng

| Trường | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| `issuer` | Định danh AS/OP. | Exact match với issuer tin cậy; kiểm tra `iss` của token sau validation. |
| `authorization_endpoint` | Nơi client bắt đầu authorization flow. | Redirect URI, `state`, PKCE và mix-up defense vẫn bắt buộc. |
| `token_endpoint` | Nơi client đổi code/refresh token/grant. | Không gửi secret hoặc authorization code tới host chưa tin. |
| `jwks_uri` | URI công bố public JWK keys. | Không phải private keys; khóa phải thuộc issuer và thuật toán cho phép. |
| `response_types_supported` | Response types AS có khả năng hỗ trợ. | Không mặc định client nào cũng được dùng. |
| `grant_types_supported` | Các OAuth grants AS hỗ trợ. | Khả năng AS khác quyền client được cấp. |
| `code_challenge_methods_supported` | Các PKCE methods AS hỗ trợ. | Ưu tiên S256 khi dùng Authorization Code + PKCE. |
| `token_endpoint_auth_methods_supported` | Cách client có thể xác thực với token endpoint. | Browser/mobile public clients không thể bảo vệ client secret như backend. |
| `scopes_supported` | Các scopes AS công bố hỗ trợ. | Không phải scope token hiện tại đã được cấp. |
| `introspection_endpoint` | Nơi kiểm tra token theo RFC 7662 khi AS hỗ trợ. | Cần xác thực và ủy quyền resource server. |
| `revocation_endpoint` | Nơi client có thể yêu cầu revoke token. | Không mặc định vô hiệu tức thì mọi JWT access token đã cấp. |
| `registration_endpoint` | Đăng ký client động khi AS cho phép. | Không tự động đăng ký và nhận secret nếu chưa có chính sách. |
| `userinfo_endpoint` (OIDC) | Trả claims về user. | Khác metadata, khác resource API nghiệp vụ. |
| `claims_supported` (OIDC) | Claims OP có thể cung cấp. | Không phải tập claims đã được cấp cho từng người. |
| `subject_types_supported` (OIDC) | Các loại subject identifier. | Không phải OAuth roles của người dùng. |
| `id_token_signing_alg_values_supported` (OIDC) | Thuật toán ID token mà OP hỗ trợ. | Không mặc định đủ làm allowlist của JWT access token. |

Ngoài ra, tùy chuẩn mở rộng có thể có metadata về PAR, request objects, mTLS aliases hoặc chính sách bảo mật. Ứng dụng chỉ nên dùng trường mà nó hiểu đầy đủ ngữ nghĩa và cách xác minh.

### Supported không có nghĩa đã được cấp

Ví dụ metadata nêu:

```json
{
  "scopes_supported": [
    "orders.read",
    "orders.approve",
    "payments.charge"
  ]
}
```

Không được suy rằng:

- Client `orders-web` đã được cấp `payments.charge`.
- User `user-123` có role `ORDER_MANAGER`.
- Access token hiện tại chứa `orders.approve`.
- API `orders-api` có thể bỏ kiểm tra tenant, owner hoặc hạn mức.
- Mọi user sẽ nhận refresh token chỉ vì AS hỗ trợ grant `refresh_token`.

Phải kiểm tra **token và grant thực tế**, không ra quyết định authorization dựa trên danh sách capabilities.

## 7. Metadata endpoint khác những endpoint còn lại

Một tài liệu metadata có thể chứa các URL, nhưng **bản thân tài liệu không phải** các dịch vụ đó.

| Endpoint | Mục đích | Thông lệ truy cập |
|---|---|---|
| AS metadata / OIDC discovery | Công bố cấu hình JSON. | Thường có thể đọc công khai qua HTTPS. |
| JWKS URI | Công bố public keys. | Thường công khai; phải giới hạn trust anchor. |
| Authorization endpoint | Tương tác ủy quyền người dùng. | Browser redirect; xác thực/consent theo AS. |
| Token endpoint | Phát access/refresh/ID tokens theo grant. | Client/grant validation, xác thực client khi cần, TLS. |
| Introspection endpoint | Tra `active` và metadata token. | RS/caller có quyền, không mở cho mọi người tra token. |
| Revocation endpoint | Yêu cầu AS thu hồi token. | Client được định danh/xác thực phù hợp, TLS. |
| UserInfo endpoint | Trả claims OIDC. | Access token phù hợp và chính sách claims. |

**JWKS có public keys** nhưng tuyệt đối không được công bố private key, refresh token hoặc client secret trong metadata. Việc biết URL `introspection_endpoint` không khiến client vô danh có quyền xem metadata của mọi access token.

## 8. Chuỗi tin cậy của một OAuth/OIDC client

Client được cấu hình trước:

```text
trustedIssuer = "https://id.example.test"
```

Sau đó mới khám phá metadata:

1. Tạo well-known URL theo đúng RFC 8414 hoặc OIDC Discovery.
2. Kết nối HTTPS, kiểm tra TLS, giới hạn timeout, redirect, kích thước JSON và host theo trust policy.
3. Parse metadata và đối chiếu `issuer` trong response với `trustedIssuer`.
4. Trích xuất endpoint và capabilities cần thiết.
5. Thực hiện Authorization Code + PKCE với `state`, redirect URI đã đăng ký và các biện pháp chống mix-up.
6. Nếu OIDC, xác minh ID token với các khóa/claims theo profile OP.
7. Dùng **access token** dành cho audience resource server khi gọi business API.

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth/OIDC Client
    participant M as AS/OP Metadata
    participant AS as Authorization Server
    participant API as Orders Resource Server
    C->>C: Cấu hình trustedIssuer
    C->>M: GET well-known metadata qua HTTPS
    M-->>C: issuer, endpoints, jwks_uri, capabilities
    C->>C: So khớp issuer và xác định endpoints tin cậy
    C->>AS: Authorization request với PKCE/state
    AS-->>C: Authorization code
    C->>AS: POST token endpoint + code_verifier
    AS-->>C: Access token, ID token khi OIDC
    C->>API: Bearer access token
    API->>API: Issuer, audience, type, time, scope và resource policy
    API-->>C: PERMIT hoặc DENY
```

Metadata **không phải một lời bảo đảm token được chấp nhận**. Resource server vẫn phải thực hiện validation riêng.

## 9. Resource server dùng JWKS từ metadata để xác minh JWT

RS tin issuer `https://id.example.test`. Một AS có thể công bố:

```json
{
  "issuer": "https://id.example.test",
  "jwks_uri": "https://id.example.test/oauth2/jwks"
}
```

Ví dụ public JWKS rút gọn:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "EXAMPLE_MODULUS_NOT_A_REAL_KEY",
      "e": "AQAB"
    }
  ]
}
```

`n`/`e` là các phần public của RSA key; dữ liệu trên **không phải khóa dùng được**. JWKS không được chứa private signing key material.

Một JWT access token theo profile có thể có:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410900
}
```

**Payload này chỉ là ví dụ**, chưa phải JWT được ký. Validation tại RS cần kiểm tra:

- **Trust anchor:** issuer nằm trong allowlist, khóa chỉ lấy từ nguồn gắn với issuer đó.
- **JOSE:** chữ ký mật mã, thuật toán allowlist, key type/use, `kid` đúng tập khóa.
- **Claims:** `iss`, `exp`, `nbf` nếu có, token type/profile theo RFC 9068 khi áp dụng.
- **Audience:** `aud` dành cho resource server đang nhận, không phải API khác.
- **Scope:** scope thực sự được cấp cho access token, không lấy từ `scopes_supported`.
- **Object authorization:** owner/tenant/role/quyền nghiệp vụ sau validation.

```mermaid
flowchart TD
    T[Nhận access token] --> I{Issuer thuộc allowlist?}
    I -- Không --> D[401 / Reject token]
    I -- Có --> J[JWKS từ metadata issuer tin cậy]
    J --> S{Signature, alg, key hợp lệ?}
    S -- Không --> D
    S -- Có --> C{Token type, iss, time hợp lệ?}
    C -- Không --> D
    C -- Có --> A{Audience đúng API này?}
    A -- Không --> D
    A -- Có --> P{Scope đủ cho endpoint?}
    P -- Không --> F[403 / Deny action]
    P -- Có --> R{Owner, tenant, policy cho phép?}
    R -- Không --> F
    R -- Có --> OK[Cho phép]
```

**Đừng tin `kid` hoặc `jku` tùy ý trong JWT.** `kid` chỉ giúp chọn khóa đã nằm trong JWKS tin cậy; `jku`/`x5u` trong header không được tự động dùng để tải nguồn khóa mới do caller chỉ định. Một `kid` có thể trùng giữa nhiều issuers; phải ràng buộc key cache với issuer và algorithm/profile.

## 10. Opaque token: metadata chỉ nơi introspection, không tự xác thực

Với **opaque access token**, RS không thể tự lấy claims từ chuỗi token. Nếu AS công bố `introspection_endpoint`, RS có quyền có thể gọi theo RFC 7662:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic RS_CREDENTIAL_PLACEHOLDER

token=OPAQUE_ACCESS_TOKEN_PLACEHOLDER&token_type_hint=access_token
```

Ví dụ kết quả:

```json
{
  "active": true,
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410900
}
```

**HTTP 200 không chứng minh token active.** AS cũng có thể trả `{"active": false}`. RS cần tin endpoint introspection đã cấu hình, xác thực caller, dùng TLS, kiểm tra `active` và metadata cần thiết (audience, scope, token type, expiry khi áp dụng) rồi phân quyền cấp đối tượng.

Một số trường ngoài `active` trong introspection là tùy chọn theo RFC; khi thiếu căn cứ bắt buộc, RS **không được tự suy ra quyền**. Việc metadata công bố introspection URL không làm URL đó công khai cho bên không có quyền.

## 11. AS metadata khác Protected Resource Metadata

Ngoài RFC 8414, **RFC 9728** định nghĩa **OAuth 2.0 Protected Resource Metadata** do **resource server** công bố. Hai loại metadata không đồng nhất.

| Điểm khác biệt | AS Metadata — RFC 8414 | Protected Resource Metadata — RFC 9728 |
|---|---|---|
| Bên công bố | Authorization server. | Protected resource/resource server. |
| Định danh chính | `issuer`. | `resource` identifier. |
| Mục đích | Endpoint và khả năng của AS. | Thông tin tài nguyên, AS có thể dùng và phạm vi của resource. |
| Ví dụ trường | `authorization_endpoint`, `token_endpoint`, `jwks_uri`. | `resource`, `authorization_servers`, `scopes_supported` khi được hỗ trợ. |
| Tự cấp trust cho token? | Không. | Không. |

Ví dụ resource metadata:

```json
{
  "resource": "https://api.example.test/orders",
  "authorization_servers": ["https://id.example.test"],
  "scopes_supported": ["orders.read", "orders.write"]
}
```

Đây là **metadata minh họa** của API đơn hàng, không phải tài liệu issuer của AS. Client chỉ được tin những AS phù hợp chính sách/hợp đồng ứng dụng; không gửi code, refresh token hay client secret đến một AS chỉ vì một resource URL tùy ý gợi ý.

Resource Indicators (RFC 8707) cho phép client nêu resource dự định nhận token khi AS hỗ trợ. Tuy nhiên, RS vẫn phải xác minh **`aud` của access token được phát hành thực tế**.

## 12. Role, scope và audience không được suy từ metadata

Một OP có thể công bố:

```json
{
  "claims_supported": ["sub", "email", "roles"],
  "scopes_supported": ["openid", "orders.read", "orders.approve"]
}
```

Không thể từ JSON này kết luận user có role `ORDER_MANAGER` hay token hiện tại có `orders.approve`. Đây là **capabilities**, không phải một quyết định cấp quyền.

| Thuộc tính | Nguồn đúng để quyết định | Lỗi cần tránh |
|---|---|---|
| Issuer của token | Token đã xác minh và trust anchor cấu hình. | Tin mọi issuer có metadata endpoint HTTPS. |
| Audience access token | Claim `aud` hoặc introspection metadata đã tin. | Lấy `client_id` hay endpoint URL thay `aud`. |
| Scope được cấp | Claim `scope`/`scp` theo profile hoặc introspection. | Dùng danh sách `scopes_supported` của issuer. |
| Role/permission | Claims đã được xác minh và chính sách nguồn role tin cậy. | Coi `claims_supported` là role của người dùng. |
| Quyền tài nguyên | Policy RS, owner, tenant, trạng thái bản ghi. | Chỉ kiểm token valid là cho mọi dữ liệu. |
| ID token audience | Client ID theo OIDC validation. | Gửi ID token tới API thay access token. |

**OAuth scopes khác application roles.** Role `ORDER_MANAGER` có thể được ánh xạ thành authority của Spring Security nếu issuer và claim schema đáng tin, nhưng không tự hình thành từ metadata. Một access token có scope đọc vẫn cần phân quyền từng bản ghi.

## 13. Bảo vệ quá trình discovery khỏi SSRF và mix-up

Metadata là **dữ liệu truy xuất qua mạng**; phải xử lý như đầu vào ngoài trust boundary.

| Sai lầm | Rủi ro | Hướng phòng tránh |
|---|---|---|
| Backend tải discovery từ `issuer` do request cung cấp tùy ý. | SSRF, truy cập IP nội bộ, nhận AS giả. | Issuer allowlist, không để user chọn trust anchor. |
| Không so khớp `issuer` metadata với issuer đã biết. | Nhầm AS/tenant và authorization-server mix-up. | Exact issuer validation theo profile. |
| Gửi client secret/code tới `token_endpoint` không tin cậy. | Lộ secret/code. | Endpoint thuộc hợp đồng issuer và policy redirect/host. |
| JWT header `jku` điều khiển JWKS fetch. | Key substitution, SSRF. | Chỉ dùng nguồn khóa từ issuer cấu hình. |
| Redirect discovery/JWKS tới HTTP hoặc mạng riêng. | Downgrade, SSRF và metadata poisoning. | HTTPS, hạn chế redirect/host/IP, giới hạn timeout. |
| Không giới hạn kích thước JSON/JWKS. | DoS qua response lớn hoặc nested JSON. | Content-size/depth/time limits, parser an toàn. |
| Trộn key sets của nhiều issuers. | `kid` trùng dẫn tới chọn nhầm khóa. | Namespace cache theo issuer/alg/profile. |
| Lỗi fetch JWKS thì cho phép token chưa xác minh. | Bypass validation. | Fail closed hoặc dùng cache đã xác minh còn hợp lệ. |

**HTTPS bảo vệ đường truyền, không tự cấp trust cho issuer.** Một attacker cũng có thể vận hành domain HTTPS hợp lệ. Trust đến từ **cấu hình cho phép và kiểm tra issuer**, không chỉ việc TLS handshake thành công.

Với client dùng nhiều AS, cần ràng buộc authorization response với issuer đã chọn ở đầu flow, xử lý `state`, PKCE, redirect URI và cơ chế chống mix-up (ví dụ issuer identification theo RFC 9207 khi phù hợp). Discovery không tự giải quyết nhầm AS.

## 14. Metadata/JWKS caching và key rotation

AS có thể xoay signing key trong khi `jwks_uri` giữ nguyên:

```text
T0: AS công bố public key K1, ký token với kid=K1.
T1: AS công bố thêm public key K2 trong JWKS.
T2: AS bắt đầu phát hành token mới với kid=K2.
T3: RS gặp K2 chưa có trong cache; refresh JWKS từ nguồn tin.
T4: K1 được giữ đủ thời gian cho token cũ theo chính sách.
T5: Khi token K1 hết hiệu lực, AS có thể loại K1.
```

Cách vận hành an toàn:

1. Cache metadata và JWKS theo cache headers hoặc chính sách được xác định, tránh fetch lại mỗi request.
2. Khi `kid` lạ, refresh JWKS **có giới hạn tần suất** để chống DoS bằng token giả với nhiều `kid` khác nhau.
3. Không bỏ xác minh chữ ký khi JWKS tạm timeout; có thể dùng cache đã được xác minh còn hợp lệ khi policy cho phép.
4. Khi issuer, token endpoint hoặc JWKS URI thay đổi, xem đó là **thay đổi security configuration** cần quản trị và kiểm thử.
5. Loại bỏ khóa bị lộ theo incident-response plan; việc bỏ khóa có thể khiến nhiều token cũ bị từ chối.
6. Theo dõi cache age, refresh errors và metadata mismatch mà không log secrets.

**Cache JWKS không phải cache introspection.** JWT signature có thể vẫn hợp lệ sau khi refresh token/grant bị revoke; nếu RS muốn biết access token hiện tại có bị thu hồi, phải có denylist/introspection hoặc kiểm tra trạng thái khác. Cache introspection `active=true` có thể kéo dài độ trễ phát hiện revoke.

## 15. Ví dụ Spring Security Resource Server: issuer discovery

Một ứng dụng Spring Boot resource server có thể cấu hình issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://id.example.test"
```

Framework có thể khám phá provider configuration/JWKS từ issuer tin cậy. **Chỉ có `issuer-uri` không có nghĩa mọi kiểm tra audience và access-token profile riêng của API đã được cấu hình**.

Ví dụ Spring Security 6.x với audience validator:

```java
@Configuration
@EnableMethodSecurity
public class OrdersResourceServerConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://id.example.test";
        String audience = "orders-api";

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audValidator = jwt -> {
            boolean correct = jwt.getAudience() != null
                    && jwt.getAudience().contains(audience);

            return correct
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token", "Invalid audience", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard, audValidator));

        return decoder;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(requests -> requests
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll()
        );

        http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

Đây là ví dụ có lược `import` và các thành phần triển khai. **Ứng dụng thật cần kiểm tra thêm JWT access-token profile/type, thuật toán cho phép, giới hạn thời gian, JWKS cache, quyền tenant/owner và cấu hình HTTP security phù hợp.** Không đưa issuer đọc từ token chưa xác minh hoặc query người dùng vào `withIssuerLocation`.

Spring Security thường ánh xạ `scope`/`scp` sang `GrantedAuthority` có tiền tố `SCOPE_`; đó là quy ước framework. Metadata `scopes_supported` **không tự tạo** authority `SCOPE_orders.read` cho principal.

## 16. Ví dụ Spring OAuth2 client: provider discovery

Một backend web application có thể khai báo provider issuer trong Spring Boot:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-login:
            provider: orders-idp
            client-id: "OIDC_CLIENT_ID_FROM_ENV"
            client-secret: "OIDC_CLIENT_SECRET_FROM_ENV"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          orders-idp:
            issuer-uri: "https://id.example.test"
```

`OIDC_CLIENT_ID_FROM_ENV` và `OIDC_CLIENT_SECRET_FROM_ENV` **là placeholders**, không phải lời khuyên hardcode secret trong cấu hình được commit. Trong sản phẩm, sử dụng biến môi trường/secret manager và phân quyền truy cập phù hợp.

Đây là ví dụ **confidential web client**, không phải công thức copy cho SPA/mobile. SPA/mobile thường là public clients: dùng Authorization Code + PKCE, không nhúng secret vào JavaScript hoặc APK/IPA và không coi issuer discovery là lý do bỏ kiểm tra callback/state.

Một client framework có thể dùng metadata để tìm authorization/token/JWKS endpoints, nhưng còn phải xác minh ID token đúng profile và xây dựng authenticated session/refresh token lifecycle an toàn.

## 17. Khi metadata thiếu hoặc hạ tầng không sẵn sàng

Không phải mọi OAuth server đều công bố tất cả optional fields. Trường hợp legacy, ứng dụng có thể phải cấu hình endpoints thủ công theo hợp đồng, nhưng không tự đoán và không nới trust policy.

| Tình huống | Cách xử lý |
|---|---|
| Không thể tải metadata tại startup. | Báo lỗi initialization/configuration hoặc có fallback cache đã xác minh theo thiết kế, **không** tự chấp nhận token. |
| Metadata trả `issuer` khác cấu hình. | Từ chối metadata, cảnh báo mismatch. |
| Thiếu `jwks_uri` nhưng RS cần xác minh JWT. | Chỉ sử dụng key source khác nếu có hợp đồng tin cậy; không tin bất kỳ JWT nào. |
| Thiếu `introspection_endpoint` khi RS nhận opaque token. | Phải có nguồn trạng thái khác đáng tin; nếu không, không thể validation an toàn. |
| Endpoint token bị đổi host. | Xem như thay đổi cấu hình nhạy cảm, xác minh trước khi gửi code/secret/refresh token. |
| JWKS timeout hoặc `kid` mới. | Refresh/rate-limit/cache theo policy; không bỏ signature validation. |
| Token đúng nguồn nhưng sai audience. | HTTP `401` tại API đang nhận. |
| Token đúng nguồn/audience nhưng thiếu scope. | HTTP `403` theo Bearer policy khi phù hợp. |
| Token đủ scope nhưng tài nguyên khác tenant. | Từ chối theo policy, có thể dùng `403` hoặc `404`. |

**Đừng đồng nhất lỗi discovery với lỗi authorization của từng người dùng.** Discovery có thể được thực hiện trong quá trình khởi động; sai metadata là lỗi cấu hình/trust anchor, không phải bằng chứng người dùng đã làm sai.

## 18. Ma trận kiểm thử metadata endpoint

Giả sử client/RS tin issuer `https://id.example.test` và API `orders-api` yêu cầu scope `orders.read`.

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| M01 | RFC 8414 metadata trả JSON hợp lệ, `issuer` khớp cấu hình. | Cho tiêu thụ các fields được hỗ trợ. |
| M02 | OIDC Discovery có các trường OP bắt buộc theo profile. | RP khám phá và tiếp tục kiểm tra OIDC token. |
| M03 | Metadata JSON malformed, sai Content-Type theo policy hoặc quá lớn. | Từ chối/ghi lỗi, không crash hoặc bypass. |
| M04 | `issuer` metadata thiếu hoặc không khớp issuer tin cậy. | Từ chối. |
| M05 | Issuer có path, well-known URL ghép sai RFC. | Test bắt lỗi URL. |
| M06 | User gửi issuer lạ qua query request. | Không tải issuer ngoài allowlist. |
| M07 | Metadata/JWKS redirect sang HTTP hoặc host không tin cậy. | Chặn hoặc xử lý theo trust policy nghiêm ngặt. |
| M08 | JWT có `jku` trỏ JWKS attacker. | Không tự tải từ token header. |
| M09 | Hai issuers có cùng `kid`. | Không nhầm khóa; namespace theo issuer. |
| M10 | JWKS rotation thêm `kid` mới. | Làm mới từ nguồn tin cậy với rate limit. |
| M11 | Metadata có `orders.approve` trong `scopes_supported` nhưng token không có. | Endpoint approve vẫn từ chối `403`. |
| M12 | Metadata nói hỗ trợ `refresh_token` nhưng client chưa có grant. | Không tự cấp refresh token. |
| M13 | OIDC ID token `aud=orders-web` gửi tới `orders-api`. | RS từ chối sai loại/audience. |
| M14 | Access JWT đúng chữ ký, `aud=payments-api`. | Orders API từ chối. |
| M15 | Access token đúng aud/scope, user khác tenant. | Từ chối cấp đối tượng. |
| M16 | Introspection endpoint tồn tại nhưng RS chưa được cấp credential. | Không tra cứu trái phép; không tự tin token. |
| M17 | Introspection HTTP 200, `active=false`. | RS từ chối. |
| M18 | Revocation HTTP 200 nhưng RS chỉ xác minh JWT tại chỗ. | Không khẳng định access JWT bị thu hồi ngay. |
| M19 | Token endpoint trả `invalid_grant` dù discovery hợp lệ. | Client xử lý grant lỗi, không coi metadata là thành công. |
| M20 | Discovery/JWKS timeout, cache cũ còn hợp lệ. | Theo policy cache/fail closed, không bỏ validation. |
| M21 | Multi-AS authorization response thuộc issuer khác request ban đầu. | Chặn mix-up. |
| M22 | Protected resource metadata đề xuất AS ngoài trust policy. | Client không mặc định tin AS. |
| M23 | Spring chỉ cấu hình issuer mà thiếu audience validator. | Integration test phát hiện. |
| M24 | `claims_supported` có `roles` nhưng user không có role. | Không tự gán quyền. |
| M25 | Token JWT bị lấy cắp nhưng đúng chữ ký/aud/scope. | Bearer RS có thể chấp nhận; nêu giới hạn và lớp bảo vệ bổ sung. |
| M26 | Discovery/tracing ghi raw access token hoặc client secret. | Redaction/security test thất bại. |
| M27 | AS đổi `token_endpoint` sang domain khác. | Kiểm soát thay đổi trust configuration. |
| M28 | API thêm route nhưng chưa cấu hình authorization. | Default deny; metadata không mở route. |

**Unit tests** có thể xác minh parse JSON, so khớp issuer/URL và validator logic. **Integration tests** cần AS/JWKS thử nghiệm với khóa riêng của môi trường test, JWT thật được ký để thử signature, issuer, audience, type và rotation; opaque token dùng mock introspection được bảo vệ. Dùng Spring Security test `jwt()` hoặc principal giả **không chứng minh chữ ký JWT đã được decoder xác minh**.

## 19. Tình huống thực hành

### A. HTTPS issuer giả

Backend nhận `/login?issuer=https://attacker.example.test`, tự tải OIDC discovery của URL đó và gửi authorization code/client secret đến endpoint AS chỉ ra.

**Kết luận:** HTTPS và JSON hợp lệ **chưa đủ**. Backend phải pin/allowlist issuer, đối chiếu `issuer` trong metadata và không gửi credential tới endpoint do caller tự chọn.

### B. Supported scope bị hiểu là scope đã cấp

Metadata liệt kê `orders.read` và `orders.approve`, nhưng access token chỉ có `orders.read`.

**Kết luận:** API phải từ chối thao tác phê duyệt nếu yêu cầu `orders.approve`. Metadata không cấp scope cho người dùng.

### C. Chữ ký JWT đúng nhưng audience sai

JWT ký bằng private key của AS tin cậy, RS lấy public key đúng từ `jwks_uri`, nhưng `aud=payments-api`.

**Kết luận:** `orders-api` phải từ chối token. Chữ ký chỉ chứng minh nguồn/toàn vẹn, không chứng minh token dành cho API này.

### D. OP trả ID token chứa role

ID token có `aud=orders-web` và `roles=["ORDER_MANAGER"]`. Client gửi token đó tới API để phê duyệt đơn hàng.

**Kết luận:** RS không chấp nhận ID token làm access token. Client xác minh ID token theo OIDC; API chỉ dùng access token phù hợp và kiểm tra quyền riêng.

### E. JWKS timeout khi rotate key

AS bắt đầu ký bằng K2 nhưng RS chỉ cache K1. JWKS endpoint timeout.

**Kết luận:** Không decode token rồi tin scope khi chưa xác minh chữ ký. RS có thể retry/cache theo policy nhưng không bỏ validation.

### F. Revoke refresh token, JWT vẫn còn hạn

Client revoke refresh token qua AS, RS chỉ dùng JWKS để xác minh access JWT cũ.

**Kết luận:** JWKS/metadata không cung cấp trạng thái thu hồi của từng JWT. Nếu cần chặn trước `exp`, dùng denylist/introspection hoặc cơ chế trạng thái đã được thiết kế.

### Tự đánh giá

1. Metadata endpoint do ai công bố và ai dùng trong từng vai trò OAuth 2.0?
2. RFC 8414 và OIDC Discovery khác nhau ở well-known path và field nào?
3. Issuer có path ảnh hưởng việc tạo well-known URL ra sao?
4. Vì sao `scopes_supported` không phải scope của access token?
5. `jwks_uri` khác `kid` trong JWT header thế nào?
6. Vì sao không tải JWKS theo `jku` tùy ý của token?
7. AS metadata và protected resource metadata khác gì?
8. Vì sao API phải kiểm `aud` kể cả khi signature đúng?
9. OIDC ID token dùng ở đâu, khác access token thế nào?
10. Vì sao cache JWKS không đồng nghĩa cache trạng thái revoke?
11. Client multi-AS cần làm gì để tránh authorization server mix-up?
12. Làm sao test được security của discovery khi gặp issuer giả hoặc metadata timeout?

## 20. Ghi nhớ

- **Metadata endpoint khám phá cấu hình AS/OP**, không cấp token, không cấp role và không cho phép bỏ authorization.
- **RFC 8414** cung cấp OAuth AS metadata; **OIDC Discovery** cung cấp OP configuration. Khi issuer có path, phải ghép well-known URI theo đúng chuẩn.
- **Tin issuer trước, tải metadata sau**. So khớp `issuer` với cấu hình, kiểm soát URL/redirect/TLS, tránh SSRF và mix-up.
- **JWKS chứa public keys**, không chứa private signing keys; metadata/JWKS không thay xác minh chữ ký, thuật toán, thời hạn, token type, `iss` và `aud`.
- **`scopes_supported` và `claims_supported` chỉ biểu diễn khả năng**, không phải quyền thực tế của token hoặc user.
- **Resource server phải xác minh access token**: JWT qua JOSE/JWKS theo profile, opaque token qua introspection/nguồn trạng thái tin cậy, sau đó kiểm tra scope và quyền trên đối tượng.
- **Protected Resource Metadata** mô tả resource server, không đồng nghĩa metadata của AS.
- **Key rotation, metadata cache, lỗi mạng và revoke** đòi hỏi chính sách vận hành rõ; không tự cho qua khi không xác minh được.
- **Metadata không ngăn bearer token bị đánh cắp hoặc phát lại**. Giới hạn audience/scope, thời hạn, bảo vệ token và sender constraint khi phù hợp vẫn cần thiết.

### Tài liệu chuẩn tham khảo

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer, endpoints, well-known URI và metadata fields.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OP configuration và discovery.
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728): metadata của protected resource.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): các vai trò OAuth, grants, token.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): chống mix-up issuer.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519) và [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): khóa và JWT validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token issuer, audience, type và claims.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) và [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): trạng thái và thu hồi token.
- [RFC 8707 — OAuth 2.0 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707): resource identifier và audience.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo mật authorization flow/token và giảm replay.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) và [OAuth 2.0 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): issuer discovery và JWT/OAuth client integration.
