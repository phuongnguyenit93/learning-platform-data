# Issuer và nguồn phát hành

## Mục tiêu học tập

Trong chương **Claims** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, một trong những câu hỏi quan trọng nhất khi xử lý token là: **ai có thẩm quyền phát hành những khẳng định này, và bên nhận dựa vào bằng chứng nào để tin chúng?** Bài học đặt claim `iss` vào mối liên hệ với nguồn phát hành, khóa xác minh, OAuth 2.0/OIDC và vòng đời token.

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của `iss` (issuer) và phân biệt **giá trị claim tự khai** với **nguồn phát hành đã được xác minh**.
- Phân biệt issuer với `sub` (chủ thể), `aud` (đối tượng nhận token), `client_id` (client) và `kid` (định danh khóa).
- Mô tả cách Resource Server xác định issuer tin cậy, chọn đúng khóa/JWKS và kiểm chứng JWT access token.
- Giải thích cơ chế xác định nguồn với **opaque access token**, **OIDC ID Token**, **refresh token** và client assertion.
- Nhận diện lỗi issuer confusion, nhầm tenant, tin vào JWKS do token điều khiển và chấp nhận token của API khác.
- Thiết kế kiểm tra issuer trong hệ thống một issuer, nhiều issuer và giai đoạn chuyển đổi Authorization Server.

## 1. Nguồn phát hành là một quan hệ tin cậy

**Issuer** là thực thể nhận trách nhiệm phát hành token và các khẳng định bên trong token theo một hợp đồng giao thức. Trong OAuth 2.0, issuer thường gắn với **Authorization Server (AS)**; trong OpenID Connect (OIDC), **OpenID Provider (OP)** phát hành ID Token. **Resource Server (RS)** là API tiếp nhận access token và quyết định có chấp nhận token để truy cập tài nguyên của mình không.

Giả sử Orders API nhận token có nội dung:

```json
{
  "iss": "https://id.example.com/realms/store",
  "sub": "user-204",
  "aud": "api://orders",
  "scope": "orders:read",
  "exp": 1800000900
}
```

Đây chỉ là **payload JSON minh họa**. Từ việc đọc `iss`, ta mới biết **token đang tự khai** được phát hành bởi `https://id.example.com/realms/store`. Ta **chưa biết** payload có bị sửa đổi, có được AS này phát hành thật hay có được phép dùng tại Orders API không.

Ba câu hỏi cần trả lời theo thứ tự hợp lý:

1. **Có tin issuer này không?** AS/OP nào được cấu hình cho ứng dụng và API này, trong môi trường và tenant nào?
2. **Có bằng chứng mật mã/nguồn tin cậy không?** JWT có chữ ký/MAC hợp lệ bằng khóa gắn với issuer, hoặc opaque token được một introspection endpoint tin cậy xác nhận?
3. **Token có dùng đúng mục đích không?** `aud`, token type, thời hạn, scope, quyền và trạng thái hiện tại có phù hợp với API/tác vụ?

**Claim `iss` không tự xác thực chính nó.** Kẻ tấn công có thể tự tạo payload rồi điền tên issuer nổi tiếng. Resource Server chỉ nên tin claim sau khi kiểm chứng token bằng **tập khóa hoặc nguồn xác minh đã được gắn với issuer tin cậy** và áp dụng các điều kiện còn lại.

## 2. Claim `iss` được định nghĩa ra sao?

Theo **RFC 7519 (JWT)**, `iss` là một *registered claim name*, có ý nghĩa là **bên phát hành JWT**. Giá trị là chuỗi `StringOrURI`; trong JWT tổng quát, việc dùng claim này phụ thuộc hợp đồng ứng dụng. Vì vậy, không phải mọi chuỗi JWT bất kỳ đều bắt buộc phải có `iss`.

Khi đi vào các profile giao thức cụ thể, yêu cầu chặt hơn:

| Ngữ cảnh | Vai trò của issuer | Yêu cầu đáng chú ý |
| --- | --- | --- |
| **JWT tổng quát** (RFC 7519) | `iss` xác định thực thể phát hành token. | Claim có thể tùy chọn nếu profile ứng dụng không yêu cầu; phải hiểu ý nghĩa theo hợp đồng. |
| **JWT access token của OAuth 2.0 theo RFC 9068** | `iss` xác định Authorization Server phát hành access token. | `iss` là claim bắt buộc; RS phải kiểm tra nguồn phát hành, audience, token type, thời hạn, chữ ký và quyền theo profile. |
| **OIDC ID Token** | `iss` xác định OpenID Provider phát hành ID Token cho client. | `iss` bắt buộc, được so sánh chính xác với issuer của OP dự kiến; client kiểm tra chữ ký và `aud`, cùng `nonce`/`azp` khi áp dụng. |
| **OAuth Authorization Server Metadata** (RFC 8414) | Trường `issuer` xác định AS và làm điểm neo cho metadata. | Trong profile metadata chuẩn, issuer là URL HTTPS, không có query/fragment; giá trị trong metadata phải khớp issuer được yêu cầu. |

Trong OIDC Discovery, `issuer` là URL HTTPS dùng làm định danh OP và phải khớp với `iss` trong ID Token. **URL issuer là định danh giao thức**, không đồng nghĩa với trang đăng nhập, tên hiển thị, địa chỉ IP node, tên container hoặc địa chỉ endpoint cấp token. Một cụm nhiều node có thể dùng cùng một issuer ổn định.

### 2.1. So khớp chính xác: đừng tự “sửa” issuer

Theo quy tắc so sánh giá trị chuỗi của JWT/OIDC, bên nhận không được tùy tiện chuẩn hóa, bỏ dấu `/` cuối hoặc ghép các issuer dựa vào tên miền chung:

| Issuer được cấu hình tin cậy | `iss` trong token | Quyết định về issuer |
| --- | --- | --- |
| `https://id.example.com/realms/store` | `https://id.example.com/realms/store` | **Khớp**. Còn phải kiểm tra chữ ký và các claim khác. |
| `https://id.example.com/realms/store` | `https://id.example.com/realms/store/` | **Không khớp** vì thừa dấu `/`. |
| `https://id.example.com/realms/store` | `https://id.example.com/realms/partner` | **Không khớp** dù cùng domain. |
| `https://id.example.com/realms/store` | `http://id.example.com/realms/store` | **Không khớp** vì khác scheme. |
| `https://id.example.com/realms/store` | `https://ID.example.com/realms/store` | **Không khớp** theo so khớp chuỗi phân biệt hoa/thường. |

Điều này quan trọng đặc biệt khi các tenant hoặc môi trường cùng dùng hạ tầng Identity. Nếu production và staging có issuer khác nhau, Resource Server production không nên tin token staging chỉ vì hai issuer thuộc cùng nhà cung cấp.

## 3. Phân biệt issuer với các định danh lân cận

| Giá trị | Trả lời câu hỏi | Ví dụ | Lỗi phổ biến |
| --- | --- | --- | --- |
| `iss` | **Ai phát hành?** | `https://id.example.com/realms/store` | Tin chuỗi tự khai chưa kiểm chứng. |
| `sub` | **Token nói về chủ thể nào?** | `user-204` | Coi cùng `sub` ở hai issuer là một người. |
| `aud` | **Token dành cho bên nhận nào?** | `api://orders` | Dùng token Orders API để gọi Billing API. |
| `client_id` | **Client nào** tham gia luồng xin token? | `sales-portal` | Coi client là issuer hoặc là người dùng cuối. |
| `kid` (header JOSE) | **Khóa nào** trong bộ khóa phù hợp? | `signing-2027-a` | Coi `kid` là danh tính issuer hoặc URL tải khóa. |
| `jti` | **JWT cụ thể nào** theo định danh của nhà phát hành? | `tok-8b17` | Nghĩ rằng có `jti` là tự động ngăn replay. |
| `scope` | **Loại thao tác nào** được cấp? | `orders:read` | Coi scope là quyền đọc mọi bản ghi ở mọi tenant. |

### Cặp `(iss, sub)` và danh tính người dùng

Hai issuer có thể cùng phát hành:

```text
Issuer A: https://id.example.com/realms/store
Subject : 42

Issuer B: https://id.partner.example/oidc
Subject : 42
```

Nếu ứng dụng ghép hồ sơ chỉ bằng `sub = "42"`, hai thực thể khác nhau có thể bị nhầm thành một. Đặc biệt trong OIDC, `sub` được xác định trong **phạm vi issuer**; một nhà cung cấp cũng có thể dùng *pairwise subject identifier* khiến cùng một người có `sub` khác nhau đối với các nhóm client. Khi tạo định danh liên kết tài khoản, hãy xem **`(iss, sub)`** là cặp khóa nhận dạng cơ sở theo hợp đồng, và có quy trình kiểm chứng riêng khi cần liên kết nhiều danh tính.

Email, số điện thoại, username và tên hiển thị dễ thay đổi hoặc không duy nhất; chúng không thay thế cặp nguồn phát hành–chủ thể cho quyết định bảo mật.

## 4. Từ issuer đến bằng chứng nguồn phát hành: trust anchor

Một Resource Server không tự khám phá issuer đáng tin bằng cách nghe token nói. Người vận hành phải **khởi tạo quan hệ tin cậy** bằng cấu hình hoặc chính sách đáng tin:

```text
Orders API cấu hình:
  expected issuer : https://id.example.com/realms/store
  expected aud    : api://orders
  allowed alg     : RS256
  trusted metadata/JWKS: thông qua issuer đã cấu hình
```

AS/OP có thể công bố metadata chứa định danh `issuer`, `jwks_uri` và endpoint liên quan. Resource Server dùng **metadata được xác minh từ nguồn đã cấu hình**, kết nối HTTPS an toàn và bộ khóa thích hợp. Các khóa có thể được thay đổi theo vòng đời nhưng **issuer không nhất thiết thay đổi khi xoay khóa**.

```mermaid
flowchart TD
    A["Cấu hình issuer đáng tin<br/>+ audience/API"] --> B["Metadata đúng issuer<br/>+ JWKS được phép"]
    C["Nhận JWT access token"] --> D["Đọc header/iss làm hint<br/>(chưa tin dữ liệu)"]
    D --> E{"iss nằm trong allowlist<br/>và khớp issuer mong đợi?"}
    E -- Không --> R["Từ chối"]
    E -- Có --> F["Chọn verifier + key<br/>gắn với issuer"]
    B --> F
    F --> G{"Chữ ký, thuật toán,<br/>claims hợp lệ?"}
    G -- Không --> R
    G -- Có --> H{"aud, token kind,<br/>scope và policy đúng?"}
    H -- Không --> R
    H -- Có --> I["Xử lý request theo quyền<br/>trên resource cụ thể"]
```

Điểm tinh tế: hệ thống nhiều issuer **có thể** đọc `iss` từ JWT chưa được xác minh để **chọn cấu hình có sẵn trong allowlist**. Giá trị đọc tạm này là **gợi ý định tuyến**, chưa phải bằng chứng. Sau đó, verifier phải sử dụng **đúng bộ khóa đã liên kết với issuer được chọn** và kiểm tra lại `iss` sau xác minh. Nếu chỉ có một issuer, có thể dùng trực tiếp cấu hình cố định mà không cần cho token chọn issuer.

### 4.1. Chữ ký hợp lệ có đủ chưa?

**Chưa.** Chữ ký chỉ có ý nghĩa theo một **khóa và thuật toán được tin cậy**:

- JWT được ký bởi **khóa riêng của AS tin cậy** có thể được Resource Server xác minh bằng public key của AS, nhưng vẫn phải kiểm tra `iss`, `aud`, hạn dùng, loại token và quyền.
- JWT được kẻ tấn công ký bằng **khóa của chính họ** có thể có chữ ký toán học đúng khi dùng public key của họ, nhưng khóa đó **không phải khóa mà Orders API đã chấp thuận cho issuer dự kiến**.
- JWT từ AS khác có chữ ký hoàn toàn hợp lệ vẫn có thể bị từ chối vì issuer khác hoặc do token dành cho resource khác.

Vì vậy, điều kiện tin cậy gần với:

> **Nguồn phát hành đã xác minh** = issuer được cho phép **và** bằng chứng mật mã/đầu mối xác minh gắn với đúng issuer **và** các điều kiện sử dụng token thỏa mãn.

Không có một phép kiểm tra đơn lẻ `iss == expected` hoặc `signatureValid == true` thay thế được toàn bộ hợp đồng này.

### 4.2. Header `kid`, `alg` và nguồn khóa

Một JWT dạng JWS Compact có thể có protected header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "store-key-2027-01"
}
```

- `alg` khai báo thuật toán JWS. Verifier chỉ nhận thuật toán đã được **cấu hình cho issuer/token profile**, không tự động tin mọi thuật toán token yêu cầu; nếu API đòi token đã ký thì phải từ chối trường hợp `alg = "none"`.
- `kid` là tên lựa chọn khóa **bên trong tập khóa được tin cậy**. Hai issuer có thể cùng dùng `kid = "key-1"`; nếu cache khóa toàn hệ thống chỉ theo `kid`, có thể chọn nhầm khóa.
- Những header như `jku`, `jwk`, `x5u` có thể là dữ liệu do phía gửi token cung cấp. Không để chúng tự quyết định URL tải khóa hay bổ sung khóa tin cậy ngoài chính sách. Điều đó có thể dẫn đến tin khóa giả hoặc SSRF.
- Resource Server cần xử lý thuật toán/định dạng header đúng profile, kể cả từ chối tham số bắt buộc (critical header) mà thư viện không hỗ trợ.

Nếu AS ký bằng HMAC như `HS256`, hệ thống xác minh cũng giữ shared secret và có khả năng tạo MAC; ranh giới quản lý khóa khác với `RS256`/`ES256` sử dụng private/public key. Cấu hình thuật toán và key type phải thống nhất, tránh *algorithm confusion*.

## 5. Ví dụ luồng xác minh JWT access token

Giả sử `sales-portal` nhận access token từ AS `store` và gửi:

```http
GET /orders/101 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <jwt-access-token>
```

Token JWS compact gồm ba đoạn `header.payload.signature`, nhưng **decode Base64url chỉ để đọc**, chưa phải verify.

Một quy trình tại Orders API có thể gồm:

1. Lấy token từ vị trí được phép, thường là HTTP `Authorization: Bearer` qua HTTPS; giới hạn độ dài và từ chối định dạng sai.
2. Xác định issuer tin cậy từ cấu hình; nếu hỗ trợ nhiều issuer, chỉ dùng `iss` chưa xác minh để chọn từ danh sách issuer cho phép.
3. Chọn verifier, thuật toán và khóa từ nguồn metadata/JWKS đã liên kết với issuer đó. Không tải JWKS theo URL tự khai từ token.
4. Xác minh chữ ký của JWS và các yêu cầu cú pháp/profile. Nếu sai, từ chối.
5. Kiểm tra `iss` **khớp chính xác**, `aud` đúng Orders API, `exp`/`nbf` và các claim thời gian cần thiết, `typ`/loại token phù hợp.
6. Kiểm tra `scope = orders:read` (hoặc quyền tương đương theo hợp đồng) và chính sách trên **đơn hàng 101**: tenant, owner, nhóm phụ trách, trạng thái hiện tại.
7. Nếu cần thu hồi gần thời gian thực, áp dụng kiểm tra trạng thái/denylist/nguồn phân quyền động thay vì chỉ tin JWT chưa hết hạn.

### Pseudocode Java

Đoạn sau chỉ biểu diễn **điều kiện cần kiểm tra**, không phải API có thể sao chép của thư viện:

```java
VerifiedAccessToken authenticateOrdersRequest(String rawJwt) {
    // Thiết lập từ phía server, không lấy từ URL/issuer tự khai trong token.
    TrustedIssuer issuer = securityConfig.ordersTrustedIssuer();

    // Thư viện đã kiểm chứng xử lý key selection, alg/key-type và JWS verify.
    VerifiedJwt verified = jwtVerifier.verify(
        rawJwt,
        issuer.jwks(),
        issuer.allowedAlgorithms()
    );

    requireExactEquals(verified.issuer(), issuer.issuerId());
    requireAudience(verified.audience(), "api://orders");
    requireValidTimes(verified.notBefore(), verified.expiresAt(), clock.now());
    requireAccessTokenProfile(verified, "at+jwt");
    requireScope(verified.scopes(), "orders:read");

    return toAuthenticatedAccessToken(verified);
}

Order readOrder(String rawJwt, String orderId) {
    VerifiedAccessToken token = authenticateOrdersRequest(rawJwt);
    Order order = ordersRepository.findById(orderId);
    authorization.requireCanReadOrder(token.subject(), token.clientId(), order);
    return order;
}
```

**Lưu ý:** một ứng dụng Spring Security Resource Server có thể dùng cấu hình `issuer-uri` để định tuyến metadata/JWKS và kiểm tra issuer theo khả năng framework. Audience, phân biệt access token với ID Token, scope và quyền trên resource vẫn phải được kiểm soát theo hợp đồng. Không giả định mọi thư viện tự kiểm tra mọi thuộc tính chỉ vì đã cấu hình issuer.

## 6. Issuer trong JWT, opaque token và các token khác

**Nguồn phát hành không nhất thiết được đọc từ một claim trong chuỗi token.** Cách chứng minh nguồn phụ thuộc định dạng và mục đích:

| Token / vật mang | Nguồn phát hành được xác định thế nào? | Điểm không được nhầm |
| --- | --- | --- |
| **JWT access token (JWS)** | Đọc `iss` theo profile, xác minh chữ ký với khóa được gắn với issuer; kiểm tra thêm `aud`, token kind, thời hạn và scope. | `iss` được decode trước verify chỉ là dữ liệu chưa đáng tin. |
| **Opaque access token** | Resource Server gọi **introspection endpoint đã cấu hình tin cậy**; AS xác nhận `active` và metadata theo hợp đồng. | Không thể giả định chuỗi opaque có payload `iss`; RFC 7662 không bắt buộc trả `iss` trong mọi phản hồi. |
| **OIDC ID Token** | OIDC client/Relying Party kiểm tra `iss` và chữ ký theo OP đã chọn; `aud` phải dành cho client, kèm kiểm tra `nonce`/`azp` theo luồng. | ID Token xác thực người dùng cho client, **không thay thế** access token gọi Resource Server. |
| **Refresh token** | Thường opaque, gắn với **AS đã phát hành, client/phiên và chính sách**; AS xác minh tại token endpoint khi xin cấp token mới. | Không đưa refresh token tới API hay kỳ vọng giải mã `iss` như JWT. |
| **Client assertion** (ví dụ `private_key_jwt`) | AS kiểm chứng assertion của **OAuth client** bằng khóa client đã đăng ký; claim `iss`/`sub` thường là client ID theo profile. | Issuer của **client assertion** không nhất thiết là issuer của **access token mà AS sẽ phát hành**. |

### 6.1. Opaque token: tin endpoint introspection, không “đoán” issuer

Giả sử Orders API nhận:

```text
Authorization: Bearer Qv5OZ7rC...random-reference...
```

Đây là chuỗi opaque minh họa. API không thể đọc `iss`, `aud` hay `scope` trực tiếp từ nó. API phải dùng **đầu mối introspection được cấu hình trước** với phương thức xác thực/chính sách phù hợp. Một phản hồi minh họa của AS:

```json
{
  "active": true,
  "client_id": "sales-portal",
  "sub": "user-204",
  "aud": "api://orders",
  "scope": "orders:read",
  "exp": 1800000900
}
```

Phản hồi có thể **không chứa `iss`**. Nguồn tin cậy nằm ở **AS và endpoint introspection mà API đã tin cậy và xác thực được**. Dù `active = true`, API vẫn phải kiểm tra audience, scope, thời hạn và policy dữ liệu theo hợp đồng. Nếu phản hồi thiếu dữ kiện bắt buộc để xác định token dành cho Orders API, hệ thống cần từ chối hoặc điều chỉnh hợp đồng xác thực; **không suy đoán**.

Không nên đưa một opaque token không rõ nguồn đi thử ở mọi AS nội bộ cho đến khi có nơi nói “active”: điều đó phá vỡ việc ràng buộc token với nguồn tin cậy, làm lộ token tới nhiều nơi và gây khó kiểm soát quyền.

### 6.2. OIDC và khác biệt giữa AS, OP, chủ thể, client

Trong OIDC, OP phát hành ID Token chứa `iss` của OP và `sub` của end-user. Client phải xác định **OP dự kiến cho phiên đăng nhập** trước khi chấp nhận ID Token. Ví dụ payload:

```json
{
  "iss": "https://login.example.com",
  "sub": "user-204",
  "aud": "web-portal-client",
  "iat": 1800000000,
  "exp": 1800000300,
  "nonce": "nonce-associated-with-login-session"
}
```

Đây chỉ là payload minh họa; việc xác minh đầy đủ phụ thuộc luồng OIDC, thuật toán và profile. `aud = "web-portal-client"` có nghĩa token dành cho **client OIDC**, không phải Orders API. Orders API không được nhận ID Token làm access token ngay cả khi `iss` và chữ ký đều hợp lệ.

Nếu OAuth client liên hệ **nhiều Authorization Server**, còn có rủi ro *authorization server mix-up*: response từ AS này bị gắn nhầm vào một phiên/flow dự kiến thuộc AS khác. OAuth 2.0 Authorization Server Issuer Identification (**RFC 9207**) quy định tham số `iss` ở **authorization response** để giúp client kiểm tra AS tạo phản hồi. Đây là **một bước bảo vệ luồng OAuth**, khác với claim `iss` trong JWT; cần dùng cùng cơ chế bảo vệ phiên như `state`/PKCE và kiểm tra redirect URI theo quy tắc của luồng.

## 7. Nhiều issuer, nhiều tenant: định tuyến và cô lập

Ví dụ một API được phép phục vụ hai tenant độc lập, mỗi tenant có issuer riêng:

```yaml
trustedIssuers:
  - issuer: "https://id.example.com/realms/retail"
    expectedAudience: "api://orders"
    keySource: "metadata-from-trusted-retail-issuer"
  - issuer: "https://partner-id.example.net/oidc"
    expectedAudience: "api://partner-orders"
    keySource: "metadata-from-trusted-partner-issuer"
```

Đây là cấu hình minh họa, không phải schema framework cụ thể. Mỗi issuer có **khóa, chính sách và audience** riêng, dù hai bên tình cờ sử dụng cùng `kid` hay cùng định dạng claims.

```mermaid
flowchart TD
    A["JWT chưa xác minh"] --> B["Đọc iss chỉ làm<br/>gợi ý tra allowlist"]
    B --> C{"issuer có trong<br/>danh sách cố định?"}
    C -- Không --> X["Từ chối"]
    C -- Có --> D["Chọn issuer config<br/>và keys tương ứng"]
    D --> E["Xác minh chữ ký +<br/>kiểm tra lại iss"]
    E --> F{"aud, claims và tenant<br/>policy hợp lệ?"}
    F -- Không --> X
    F -- Có --> G["Đánh giá quyền<br/>trên tài nguyên cụ thể"]
```

Điều **không an toàn**:

```java
// SAI: dữ liệu JWT chưa xác minh tự điều khiển nơi lấy khóa.
String untrustedIssuer = parseWithoutVerification(rawJwt).getIssuer();
Jwks keys = httpClient.get(untrustedIssuer + "/keys");
if (verifySignature(rawJwt, keys)) {
    allowRequest();
}
```

Nếu attacker tự vận hành issuer và khóa, họ có thể tạo token tự ký rồi chỉ đường cho API tải khóa của họ. Tùy cách ghép URL, thiết kế này còn có thể dẫn đến SSRF. Cách đúng là **issuer allowlist + metadata/JWKS gắn với từng issuer + xác minh issuer sau verify + authorization policy**.

Đừng chỉ kiểm tra hậu tố domain như `*.example.com` để chấp nhận mọi issuer. Một môi trường staging, tenant thử nghiệm hoặc dịch vụ không liên quan có thể nằm dưới cùng domain mà **không được ủy quyền cấp token cho API production**.

### Nhiều issuer và cùng `sub`

Khóa định danh tài khoản của Resource Server nên bảo toàn nguồn:

```text
(iss=https://id.example.com/realms/retail, sub=42)  -> principal A
(iss=https://partner-id.example.net/oidc, sub=42)   -> principal B
```

Ngay cả khi token đã được verify, Resource Server vẫn phải kiểm tra **tenant/resource ownership**. Cặp `(iss, sub)` trả lời “ai theo nguồn nào”, không phải “được làm gì với mọi dữ liệu”.

## 8. Issuer ổn định, xoay khóa và chuyển đổi nguồn phát hành

### 8.1. Xoay khóa không bắt buộc đổi `iss`

Một AS có thể dùng nhiều khóa ký được công bố trong JWKS:

```text
Giai đoạn A: AS ký bằng key-01; JWKS có key-01
Giai đoạn B: JWKS có key-01 và key-02
Giai đoạn C: AS bắt đầu ký bằng key-02
Giai đoạn D: loại key-01 khi hết cửa sổ còn chấp nhận token cũ

Trong mọi giai đoạn:
iss = https://id.example.com/realms/retail
```

`kid` giúp chọn khóa trong tập khóa tin cậy; nó **không phải issuer**. Verifier nên có cache JWKS, cơ chế làm mới an toàn và giới hạn tần suất làm mới khi thấy `kid` không xác định để tránh lạm dụng mạng. Khi issuer/khóa bị xâm phạm, chính sách xử lý khẩn cấp có thể phải ngừng chấp nhận khóa/token còn hạn.

### 8.2. Đổi `iss` là thay đổi hợp đồng bảo mật

Nếu tổ chức chuyển từ `https://id-old.example.com` sang `https://identity.example.com`, dù cùng nhân viên và sản phẩm, đối với giao thức **đó là hai giá trị issuer khác nhau**. Một kế hoạch chuyển đổi có kiểm soát gồm:

1. Kiểm kê Resource Server, OAuth client, RP OIDC, metadata/JWKS, audience, redirect URI và các liên kết tài khoản dựa trên `(iss, sub)`.
2. Cấu hình issuer mới **tường minh**; nếu cần đồng thời tin issuer cũ trong cửa sổ chuyển tiếp, gắn mỗi issuer với khóa/policy riêng và đặt mốc kết thúc.
3. Chuyển việc phát hành token mới, cập nhật client/API, xử lý cache và token đang lưu hành; đánh giá refresh token/phiên cũ theo chính sách của AS.
4. Áp dụng quy trình liên kết lại danh tính nếu `(iss, sub)` đổi; không gộp người dùng chỉ dựa vào email hoặc `sub` trùng.
5. Ngừng tin issuer cũ và gỡ cấu hình/khóa/ngoại lệ khi hoàn tất chuyển đổi.

Một thay đổi **tên hiển thị** của tổ chức không nhất thiết yêu cầu đổi `iss`. Ngược lại, đổi chuỗi issuer thực tế mà không cập nhật bên nhận sẽ khiến token mới bị từ chối đúng theo cơ chế bảo mật. Không sửa nội dung `iss` trong token để “hợp thức hóa” vì thay đổi payload sẽ phá chữ ký JWS.

## 9. Issuer và giới hạn vòng đời token

Nguồn phát hành là một phần của trust model, nhưng **không bảo đảm** token còn hiệu lực hoặc không bị đánh cắp:

- **Thời hạn:** `exp`, `nbf`, `iat` giúp kiểm tra hiệu lực theo thời gian; NumericDate thường tính bằng giây Unix UTC. Bên nhận cần leeway hợp lý, tránh nới quá rộng.
- **Audience/scope:** token từ đúng issuer nhưng dành cho Billing API phải bị Orders API từ chối. `orders:read` không chứng minh người gọi được xem mọi order.
- **Thu hồi:** JWT tự chứa có thể vẫn verify thành công sau khi người dùng bị khóa hoặc token bị thu hồi nếu API không có trạng thái bổ sung. Cân nhắc TTL ngắn, kiểm tra quyền động, introspection hoặc denylist theo nhu cầu.
- **Bearer replay:** kẻ có access token bị lộ có thể sử dụng lại token còn hiệu lực, dù `iss` và chữ ký hợp lệ. Tránh ghi token vào URL/log, dùng HTTPS và lưu trữ an toàn.
- **Ràng buộc người gửi:** mTLS certificate-bound token (RFC 8705) hoặc DPoP (RFC 9449) có thể giảm khả năng sử dụng token bị sao chép nếu AS và RS triển khai kiểm tra bằng chứng sở hữu khóa xuyên suốt.
- **Refresh token:** được sử dụng với AS tại token endpoint, thường không đọc `iss` từ chuỗi; cần chính sách lưu trữ/xoay/thu hồi riêng, không gửi tới Resource Server.

Mấu chốt là **tin đúng issuer** nhưng vẫn **không cho phép vượt quyền và vượt trạng thái**. Kiểm chứng nguồn chỉ là một lớp trong quyết định authorization tổng thể.

## 10. Các lỗi bảo mật liên quan issuer

| Lỗi | Ví dụ | Cách phòng tránh |
| --- | --- | --- |
| **Tin `iss` chưa verify** | JWT tự ký khai `iss` là OP hợp lệ. | Xác minh với khóa/nguồn gắn với issuer đã cấu hình. |
| **Tin chữ ký bất kỳ** | API tải public key từ URL trong JWT rồi coi chữ ký hợp lệ là đủ. | Chỉ dùng trust anchor và JWKS từ nguồn được phép; kiểm tra issuer sau verify. |
| **Thiếu kiểm tra audience** | Token cho `api://billing` được API Orders chấp nhận. | Mỗi RS kiểm tra `aud` theo chính nó. |
| **Dùng `kid` làm danh tính toàn cục** | Retail và Partner cùng dùng `kid = key-1`. | Cache/chọn khóa theo issuer và kiểu khóa, không chỉ theo `kid`. |
| **Gộp người dùng theo `sub`** | Hai issuer cùng cấp `sub = 42`. | Ràng buộc định danh theo `(iss, sub)` và quy trình liên kết tài khoản. |
| **Dùng wildcard issuer** | Chấp nhận mọi issuer dưới `*.example.com`. | Allowlist chính xác từng issuer, theo môi trường/tenant. |
| **Chấp nhận ID Token tại API** | OIDC ID Token có chữ ký/issuer đúng bị dùng làm bearer access token. | Kiểm tra đúng token type/profile và audience của API. |
| **Không bảo vệ client đa AS khỏi mix-up** | Authorization response của AS B bị ghép vào phiên login AS A. | Ràng buộc phiên với AS dự kiến, `state`/PKCE và kiểm tra issuer response khi có RFC 9207. |
| **Đổi issuer không có kế hoạch** | Client/API vẫn so khớp issuer cũ, token issuer mới bị từ chối. | Triển khai migration và thời hạn ngừng tin issuer cũ rõ ràng. |
| **Cho rằng đúng issuer là có quyền** | Token scope đọc được dùng để xóa order hoặc xem tenant khác. | Kiểm tra scope, audience, quyền trên đối tượng và trạng thái hiện tại. |

## 11. Tình huống thực hành: Orders API và hai nguồn phát hành

Orders API production cấu hình:

```text
Trusted issuer = https://id.example.com/realms/store
Expected aud   = api://orders
Expected kind  = OAuth access token
Required scope = orders:read
```

Giả sử không có thu hồi và mọi token còn trong thời hạn, trừ khi tình huống nêu khác:

| Token hoặc kết quả xác minh | Quyết định | Lý do |
| --- | --- | --- |
| JWT từ issuer `store`, chữ ký hợp lệ theo khóa tin cậy, `aud` đúng, loại access token đúng, scope đủ; người gọi có quyền trên đơn cụ thể. | **Cho phép** theo chính sách. | Đủ ranh giới nguồn, mục đích, thời hạn và quyền. |
| JWT ghi `iss` là `store` nhưng ký bằng khóa do attacker tự sinh. | **Từ chối**. | Claim tự khai không chứng minh nguồn. |
| JWT của issuer `partner` được ký hợp lệ bằng khóa `partner`, cùng `sub`/scope. | **Từ chối**. | Issuer không nằm trong ranh giới tin cậy của API này. |
| JWT từ `store` nhưng `aud = api://billing`. | **Từ chối**. | Đúng issuer không thay thế kiểm tra audience. |
| JWT từ `store` nhưng `iss` có thêm dấu `/` cuối. | **Từ chối**. | So khớp chuỗi issuer chính xác thất bại. |
| ID Token của `store` dành cho client web, có `sub` hợp lệ. | **Từ chối tại Orders API**. | Sai mục đích token và audience. |
| Opaque token được introspection từ AS `store` tin cậy trả `active=true` nhưng không có thông tin xác định audience phù hợp. | **Chưa đủ điều kiện cho phép**. | Phải dựa vào hợp đồng introspection và policy audience/scope, không chỉ `active`. |
| Token từ `store` và scope đủ nhưng user không được truy cập đơn thuộc tenant B. | **Từ chối**. | Issuer/scope không thay quyền trên từng resource. |

**Câu hỏi tự kiểm tra**

1. Tại sao đọc `iss` trong payload sau khi Base64url-decode chưa thể kết luận token do issuer đó phát hành?
2. Vì sao phải liên kết **khóa kiểm chứng** với **issuer tin cậy** trước khi kiểm tra JWT?
3. Điểm khác nhau giữa `iss` và `aud` là gì? Token đúng issuer nhưng sai audience xử lý thế nào?
4. Cơ chế xác định nguồn phát hành opaque token khác JWT access token ở đâu?
5. Nếu hai issuer cùng có `sub="42"`, nên lưu định danh tài khoản như thế nào?
6. Vì sao xoay khóa `kid` không bắt buộc phải đổi `iss`, còn đổi URL issuer cần kế hoạch chuyển đổi?
7. Tham số `iss` ở OAuth authorization response (RFC 9207) khác claim `iss` trong JWT thế nào?

**Gợi ý trả lời:** (1) Payload chỉ là dữ liệu do bên gửi cung cấp; cần bằng chứng mật mã/đầu mối đáng tin. (2) Chữ ký chỉ có ý nghĩa khi dùng đúng khóa mà API đã ủy quyền cho issuer. (3) `iss` là nguồn phát hành, `aud` là bên nhận; sai audience thì từ chối. (4) JWT có thể xác minh chữ ký/claims, opaque cần introspection tin cậy theo hợp đồng. (5) Dùng cặp `(iss, sub)`. (6) Khóa thuộc vòng đời issuer; đổi issuer là đổi định danh giao thức. (7) Một giá trị giúp kiểm tra AS tạo authorization response, giá trị còn lại xác định issuer của JWT; chúng dùng ở hai điểm khác nhau trong flow.

## 12. Checklist triển khai

- [ ] Khai báo **đúng issuer được tin cậy** cho mỗi API, môi trường và tenant; không chấp nhận wildcard domain hoặc chuẩn hóa chuỗi tùy ý.
- [ ] Với JWT, liên kết issuer → metadata/JWKS → verifier/allowed algorithms; không để header hoặc claim chưa xác minh chọn nguồn khóa tùy ý.
- [ ] Kiểm chứng chữ ký/MAC và kiểm tra lại `iss` sau verify; xử lý `kid` trong tập khóa đúng issuer.
- [ ] Xác minh `aud`, `exp`/`nbf`, token type, scope và quyền trên từng resource instance.
- [ ] Với opaque token, gọi introspection endpoint đã tin cậy, kiểm tra `active` cùng audience/scope/chính sách cần thiết.
- [ ] Với OIDC, kiểm tra OP dự kiến, `iss`, `aud` và các điều kiện ID Token theo flow; không dùng ID Token thay access token.
- [ ] Khi có nhiều AS, ràng buộc authorization response với AS dự kiến, không ghép lẫn các flow.
- [ ] Gắn danh tính người dùng vào `(iss, sub)` theo profile; tránh liên kết tài khoản chỉ bằng email/username.
- [ ] Có quy trình xoay khóa, làm mới JWKS, chuyển issuer, xử lý token đang lưu hành và ngừng tin nguồn cũ.
- [ ] Bảo vệ token khỏi lộ/log, kiểm soát replay và thu hồi; nhớ rằng xác minh issuer không đồng nghĩa có mọi quyền.

## Tài liệu nền tảng

- **RFC 7519 — JSON Web Token (JWT):** claim `iss`, `sub`, `aud`, NumericDate và quy tắc so sánh chuỗi.
- **RFC 7515 — JSON Web Signature (JWS):** chữ ký/MAC, protected header và xác minh token.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** định danh issuer và cách công bố metadata/khóa.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** kiểm tra claims, loại token và audience của access token JWT.
- **RFC 8725 — JSON Web Token Best Current Practices:** phòng chống algorithm confusion, cross-JWT confusion và lỗi khi xử lý claims/khóa.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active` và metadata của opaque access token.
- **OpenID Connect Core 1.0 / Discovery 1.0:** `iss` của ID Token và định danh OP.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** tham số issuer trong authorization response nhằm giảm rủi ro mix-up.
- **RFC 8705 / RFC 9449:** mTLS và DPoP khi cần hạn chế việc sử dụng lại token bị sao chép.

**Ghi nhớ:** `iss` trả lời **“token tự nhận do ai phát hành?”**; quy trình xác minh mới trả lời **“mình có đủ bằng chứng để tin đúng nguồn phát hành này không?”**. Một Resource Server an toàn cần xác thực token bằng **khóa hoặc đầu mối tin cậy gắn với issuer đã cho phép**, rồi kiểm tra **audience, thời hạn, loại token, scope và quyền trên tài nguyên**. Nguồn phát hành đúng là điều kiện cần, nhưng không tự cấp mọi quyền truy cập.
