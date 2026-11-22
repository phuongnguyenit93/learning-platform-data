# RFC 9068, typ at+jwt và hồ sơ JWT access token

Trong **OAuth 2.0**, `access token` là credential cho phép client gọi **Resource Server**. OAuth 2.0 không bắt buộc access token phải là JWT: Authorization Server có thể phát hành chuỗi **opaque** hoặc định dạng khác. Khi các hệ thống chọn **JWT access token**, việc “có chữ ký hợp lệ” vẫn chưa tạo ra một **hợp đồng tương thích** giữa Authorization Server và Resource Server: những bên khác nhau có thể đặt tên claim, khai báo đối tượng nhận và phân biệt loại token theo các quy ước không giống nhau.

**RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens** (10/2021) định nghĩa một hồ sơ chuẩn để phát hành và xác minh **OAuth 2.0 JWT access token**. Điểm nhận diện quan trọng là JOSE header `typ: "at+jwt"` (hoặc `"application/at+jwt"`). Hồ sơ cũng quy định các claim bắt buộc, cách dùng `aud` với tài nguyên đích, và các bước kiểm tra ở Resource Server.

Trong bài này, giả sử:

- **Authorization Server (AS):** `https://login.example.com`.
- **OAuth Client:** `web-orders` hoặc `inventory-worker`.
- **Resource Server (RS):** Orders API, có resource identifier `https://api.example.com/orders`.
- **Quyền nghiệp vụ minh họa:** `orders.read` và `orders.write`.

Các hostname, client ID và phạm vi quyền chỉ là dữ liệu ví dụ; hệ thống thực phải dùng giá trị đăng ký thống nhất giữa AS và RS.

## 1. “Hồ sơ JWT access token” giải quyết vấn đề nào?

Một JWT là nơi chứa tập JSON claims; một access token là credential được cấp trong giao thức OAuth. Hai khái niệm không đồng nhất:

| Khái niệm | Ý nghĩa |
|---|---|
| **JWT (RFC 7519)** | Cách biểu diễn claims có thể được ký theo JWS hoặc mã hóa theo JWE. |
| **OAuth access token** | Credential dùng để truy cập tài nguyên, bất kể định dạng bên trong. |
| **RFC 9068 JWT access token** | Access token **dạng JWT** tuân thủ một hồ sơ chuẩn gồm `typ`, claims, audience, chữ ký và quy tắc xác minh. |
| **OIDC ID token** | JWT dành cho **client** xác minh kết quả đăng nhập; không phải credential gọi Orders API. |
| **Opaque access token** | Credential mà client không dựa vào cấu trúc bên trong; RS thường xác minh qua cơ chế introspection phù hợp. |

Không nên lấy “token có ba đoạn `header.payload.signature`” làm đủ để kết luận đó là access token. Một **ID token** cũng có thể có ba đoạn và được ký bằng khóa của cùng issuer. Nếu Resource Server chấp nhận mọi JWT có chữ ký hợp lệ, nó có thể vô tình nhận token được cấp cho mục đích khác. Đây là rủi ro **cross-JWT confusion**.

RFC 9068 giảm nhầm lẫn bằng hai lớp thông tin độc lập:

1. **Loại token:** `typ` tuyên bố đây là access token theo hồ sơ `at+jwt`.
2. **Đích nhận và hợp đồng claims:** `aud` chỉ đến Resource Server được phép nhận, đi kèm các trường chuẩn `iss`, `exp`, `sub`, `client_id`, `iat`, `jti` và các thông tin ủy quyền phù hợp.

> **Lưu ý phạm vi:** RFC 9068 không buộc mọi OAuth Authorization Server trên thế giới phát hành JWT, không định nghĩa toàn bộ quy tắc phân quyền của một API và không thay thế các yêu cầu bảo mật của OAuth 2.0, JWT/JWS hoặc ứng dụng.

### 1.1. Những từ khóa chuẩn tắc trong RFC

Các từ `MUST`, `MUST NOT`, `SHOULD`, `MAY` có ý nghĩa riêng theo RFC 2119/8174:

- **MUST / REQUIRED:** điều kiện bắt buộc khi tuyên bố tuân thủ.
- **MUST NOT:** điều bị cấm khi tuân thủ.
- **SHOULD / RECOMMENDED:** khuyến nghị mạnh; ngoại lệ cần được hiểu và đánh giá.
- **MAY / OPTIONAL:** tùy chọn có thể áp dụng.

Nhờ vậy, không được biến khuyến nghị “nên dùng chữ ký bất đối xứng” thành yêu cầu “bắt buộc dùng RSA”, cũng không được coi `scope` là claim bắt buộc của mọi token trong hồ sơ khi RFC chỉ quy định điều kiện cụ thể cho nó.

## 2. `typ: at+jwt` — khai báo loại token trong JOSE Header

### 2.1. Header chuẩn

Một RFC 9068 access token được ký bằng JWS có thể có protected header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-signing-key-01"
}
```

- `alg` là thuật toán ký, ví dụ `RS256`. **Chữ ký là bắt buộc**; `alg=none` bị cấm trong hồ sơ.
- `typ` biểu thị **token type**. RFC 9068 đăng ký media type `application/at+jwt`, yêu cầu token mang type này ở header và **khuyến nghị dạng viết gọn `at+jwt`**.
- `kid` là key identifier tùy chọn để chọn khóa trong bộ khóa đã tin cậy. Nó **không** tự tạo sự tin cậy và cũng không cho phép token quyết định nguồn JWKS tùy ý.

**Resource Server tuân thủ RFC 9068 phải chấp nhận giá trị `typ` là `at+jwt` hoặc `application/at+jwt` và từ chối giá trị khác.** Để tránh rủi ro tương thích, ví dụ trong bài dùng dạng viết gọn chuẩn hóa bằng chữ thường `at+jwt`.

Hai thông tin dễ bị nhầm với `typ`:

| Trường | Xuất hiện ở đâu? | Giá trị ví dụ | Ý nghĩa |
|---|---|---|---|
| JOSE `typ` | Header bên trong JWT/JWS | `at+jwt` | Đây là JWT access token theo RFC 9068. |
| OAuth `token_type` | JSON phản hồi **token endpoint** | `Bearer` | Client trình token theo cơ chế bearer (`Authorization: Bearer ...`). |
| HTTP `Content-Type` | Header của HTTP response/request | `application/json` | Media type của **HTTP body**, không thay `typ` trong JWT. |
| JOSE `cty` | Header tùy chọn, nhất là nested JWT | `JWT` | Kiểu nội dung bên trong khi cần, không thay `typ`. |

Ví dụ phản hồi token endpoint có thể là:

```json
{
  "access_token": "eyJ...eyJ...SIGNATURE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
```

Ở đây `token_type=Bearer` **không chứng minh** JWT bên trong có `typ=at+jwt`; phải xác minh JOSE header của access token.

### 2.2. Có phải `typ` là bằng chứng đủ để tin token?

Không. Kẻ tấn công có thể tạo một JWT bất kỳ với header `{"typ":"at+jwt"}`. Trước khi tin các claims, Resource Server vẫn phải xác minh:

- Chữ ký bằng khóa của issuer đã đăng ký, với thuật toán nằm trong danh sách cho phép.
- `iss` bằng chính xác issuer cấu hình.
- `aud` thực sự chứa resource identifier mà API chấp nhận.
- Thời hạn (`exp`, `nbf` nếu có), cấu trúc claims và chính sách quyền.
- Các điều kiện khác do hợp đồng hệ thống yêu cầu, chẳng hạn loại grant, `client_id` được phép, quyền tenant và quyền trên dữ liệu cụ thể.

Nói cách khác: **`typ` phân loại, chữ ký xác minh tính toàn vẹn/nguồn khóa, `aud` và claims quyết định token có đúng đối tượng và có thể được dùng hay không.**

## 3. Cấu trúc của JWT access token theo RFC 9068

JWS Compact Serialization thường có ba đoạn:

```text
BASE64URL(protected-header).BASE64URL(claims).BASE64URL(signature)
```

JWT ký thông thường **không mã hóa claims**, vì Base64URL chỉ là encoding. Ai có bearer token có thể decode header và payload, dù không thể sửa chúng mà vẫn giữ chữ ký hợp lệ. Nếu cần che claims, các bên có thể dùng JWE theo thỏa thuận; phần giải mã và xác minh cần được xử lý đúng.

Một claims set **minh họa** để gọi Orders API:

```json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "exp": 2000000300,
  "iat": 2000000000,
  "jti": "token-b8b7e663-3f1a-4e24",
  "client_id": "web-orders",
  "scope": "orders.read"
}
```

Các Unix timestamps chỉ để minh họa, không phải token có thể sử dụng ngoài đời. Chuỗi trên cũng **chưa phải JWT có chữ ký**; đó là JSON payload sẽ được issuer mã hóa và ký.

### 3.1. Bảy claims bắt buộc

RFC 9068 quy định **bảy claim REQUIRED** dưới đây, với ý nghĩa được định nghĩa bởi các RFC liên quan:

| Claim | Bắt buộc? | Ý nghĩa và lưu ý khi triển khai |
|---|---|---|
| `iss` | **Có** | Issuer identifier, thường là URL của Authorization Server. Resource Server phải đối chiếu **chính xác** với issuer đã cấu hình. |
| `exp` | **Có** | Thời điểm JWT hết hiệu lực (`NumericDate`). Resource Server không dùng token sau hạn, chỉ cho phép clock skew nhỏ theo chính sách. |
| `aud` | **Có** | Resource indicator / audience mà token nhắm đến. API phải tìm thấy **định danh của chính mình** trong claim này. |
| `sub` | **Có** | Subject của token; ý nghĩa khác nhau tùy grant có người dùng hay chỉ có client. |
| `client_id` | **Có** | Client ID của OAuth client được cấp token. Không đồng nghĩa với `aud` và không mặc định là danh tính của người dùng. |
| `iat` | **Có** | Thời điểm token được phát hành (`NumericDate`). |
| `jti` | **Có** | ID của JWT; có ích trong ghi nhận sự kiện, nhận diện token và thiết kế xử lý phát lại/thu hồi khi có cơ chế bổ sung. |

**`NumericDate`** là số giây tính từ Unix epoch, không phải ngày giờ dạng chuỗi tùy ý. Trong một JWT, `exp`, `iat` có thể là số; kiểu và ý nghĩa phải tuân theo JWT specification.

**`jti` không tự chống replay.** Nếu Resource Server chỉ xác minh chữ ký và thời hạn mà không theo dõi/đánh giá replay, cùng một bearer token còn hiệu lực vẫn có thể được trình nhiều lần. `jti` là định danh để dùng trong cơ chế khác khi cần, không phải “công tắc” tự động chống đánh cắp token.

### 3.2. `sub` không phải lúc nào cũng là người dùng

Hồ sơ yêu cầu `sub` hiện diện, nhưng **không** quy định rằng đó luôn là “ID của người đang đăng nhập”:

| Grant / tình huống | Đối tượng liên quan | Hướng biểu diễn `sub` theo RFC |
|---|---|---|
| `authorization_code` có Resource Owner | Người dùng trải qua luồng cấp quyền | `sub` **SHOULD** tương ứng định danh người dùng tại issuer. |
| `client_credentials` không có Resource Owner | Ứng dụng / service tự xin token | `sub` **SHOULD** tương ứng định danh ứng dụng mà issuer dùng để đại diện cho client. |
| Các grant / token exchange khác | Tùy mô hình chủ thể và quyền | Xác định rõ chủ thể theo hợp đồng của issuer và RS. |

Nếu một RS xử lý token `client_credentials` như phiên người dùng và lấy `sub` để phân quyền tài khoản cá nhân, có thể xuất hiện **sub confusion**. AS cũng cần ngăn client tự chọn `client_id` trùng với định danh người dùng có đặc quyền để tránh làm RS nhầm lẫn khi `sub` lấy từ `client_id`.

Quy tắc thiết kế:

- Không chỉ dựa vào `sub` để nhận biết grant có Resource Owner hay không.
- Phân biệt `sub`, `client_id` và loại quyền được cấp.
- Xác định chính sách kiểm tra quyền phù hợp cho machine-to-machine và user-delegated token.
- Nếu RS gán subject vào dữ liệu nội bộ, cân nhắc cặp `(iss, sub)` và ngữ cảnh danh tính/grant, tránh đồng nhất subject từ các issuer khác nhau.

## 4. Các claims tùy chọn và claims ủy quyền

### 4.1. `scope` được khuyến nghị khi đã yêu cầu scope

`scope` **không nằm trong bảy claims REQUIRED vô điều kiện**. RFC 9068 nói rằng nếu authorization request chứa `scope`, JWT access token được cấp **SHOULD** chứa claim `scope` tương ứng.

Ví dụ:

```json
{
  "scope": "orders.read orders.write"
}
```

Các scope trong chuỗi `scope` được phân cách bằng dấu cách. Trong hệ thống Spring Security, `scope` thường được chuyển thành các authority như `SCOPE_orders.read`, nhưng **ánh xạ scope → endpoint** là chính sách của Resource Server, không phải tác dụng tự động của RFC 9068.

Một yêu cầu then chốt: **mọi scope trong token phải có ý nghĩa đối với các resource được nêu trong `aud`**. Không nên phát hành token gộp một nhóm scope có nghĩa không rõ ràng ở nhiều API.

Ví dụ:

| `aud` | `scope` | Cách đánh giá |
|---|---|---|
| `orders-api` | `orders.read` | Phù hợp nếu Orders API định nghĩa quyền này. |
| `inventory-api` | `inventory.read` | Phù hợp nếu Inventory API định nghĩa quyền này. |
| `orders-api` | `inventory.write` | Có khả năng sai hợp đồng; AS không nên phát hành quyền không có nghĩa ở Orders API. |
| `orders-api` và `inventory-api` | `read` | **Mơ hồ** nếu không rõ `read` áp vào API nào; cần quy tắc rõ hoặc tách token. |

### 4.2. Claim thông tin xác thực người dùng

Khi grant liên quan Resource Owner, AS **MAY** đưa thêm:

- `auth_time`: thời điểm người dùng được xác thực.
- `acr`: authentication context class reference.
- `amr`: authentication methods references.

Những claim này giúp truyền tải ngữ cảnh xác thực nếu RS có nhu cầu nghiệp vụ, nhưng **không phải claims bắt buộc** của mọi RFC 9068 JWT access token. Giá trị được xác định từ ngữ cảnh xác thực phù hợp, không do client tự gửi rồi mặc nhiên được tin.

### 4.3. Claims về nhóm, vai trò và entitlements

RFC 9068 gợi ý một hệ tên claim chung nếu AS cần đưa thuộc tính ủy quyền ngoài scope:

| Claim | Dùng để biểu diễn | Ghi chú |
|---|---|---|
| `groups` | Nhóm mà chủ thể tham gia | Nên thống nhất cấu trúc/kiểu dữ liệu theo hồ sơ SCIM phù hợp. |
| `roles` | Các vai trò liên quan tài nguyên | Không có một tập tên role chuẩn áp dụng cho mọi sản phẩm. |
| `entitlements` | Quyền lợi hoặc đặc quyền cụ thể | Cần thỏa thuận nghĩa và audience giữa AS/RS. |

Các tên này lấy cảm hứng từ mô hình SCIM theo RFC 7643; chúng **không tạo cơ chế tự động phân quyền** trong Spring Security. Nếu issuer dùng `roles`, ứng dụng phải quyết định những role nào hợp lệ, phân biệt issuer/tenant/audience, và ánh xạ chúng thành authorities hoặc chính sách nghiệp vụ.

### 4.4. Dữ liệu cá nhân và riêng tư

Một JWT ký kiểu JWS **có thể bị đọc claims** bởi bất kỳ ai nắm token. Không đưa email, số điện thoại, dữ liệu nhân sự, thông tin nghiệp vụ nhạy cảm hoặc secret vào token chỉ vì JWT đã được ký.

RFC 9068 còn nhấn mạnh **OAuth Client không được dựa vào việc đọc nội dung access token** để xây logic ứng dụng; nội dung là hợp đồng giữa **AS và RS** và có thể đổi sang opaque token. Nếu web app cần biết hồ sơ người dùng, hãy dùng cơ chế OIDC phù hợp hoặc API được phân quyền. Tránh đưa đầy đủ hồ sơ vào access token chỉ để tiện đọc ở frontend.

## 5. `aud`: hợp đồng Resource Server được phép nhận

`aud` trả lời câu hỏi **“token này được phát hành cho tài nguyên nào?”**, còn `client_id` trả lời **“OAuth client nào nhận được token?”**. Hai giá trị có thể hoàn toàn khác nhau:

```json
{
  "aud": "https://api.example.com/orders",
  "client_id": "web-orders"
}
```

Trong trường hợp này:

- `web-orders` là client.
- `https://api.example.com/orders` là Resource Server identifier.
- Một token được cấp cho client `web-orders` vẫn phải bị từ chối ở Inventory API nếu `aud` không chứa identifier của Inventory API.

### 5.1. Resource Indicators theo RFC 8707

Client có thể dùng tham số `resource` theo **RFC 8707** để nói rõ đích nhận. Ví dụ Authorization Code Flow minh họa:

```http
GET /authorize?response_type=code&
  client_id=web-orders&
  redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
  state=RANDOM_STATE&
  code_challenge=PKCE_CHALLENGE&
  code_challenge_method=S256&
  scope=orders.read&
  resource=https%3A%2F%2Fapi.example.com%2Forders HTTP/1.1
Host: login.example.com
```

Client thực tế phải tuân theo toàn bộ yêu cầu của flow: callback đăng ký, `state`, PKCE, chính sách client và kiểm soát phiên. Ví dụ tập trung vào `resource` nên không diễn giải chi tiết các bước đăng nhập.

Theo RFC 9068:

1. **Có `resource`:** `aud` của JWT access token được cấp **SHOULD** mang cùng resource indicator mà client yêu cầu.
2. **Không có `resource`:** AS **MUST** chọn một **default resource indicator** cho `aud`. Nếu có `scope`, AS **SHOULD** dùng nó để suy ra resource mặc định.
3. **Scope trỏ nhiều resource mặc định và không thể làm rõ:** AS **SHOULD** từ chối yêu cầu bằng `invalid_scope` thay vì phát hành quyền mơ hồ.
4. **Nhiều resource indicators:** AS phải cân nhắc mối liên hệ giữa từng scope và từng resource; **không phát hành access token với quyền cấp không thể diễn giải rõ**.

Thực tế, tách access token theo audience thường làm ranh giới quyền và kiểm toán dễ hiểu hơn. Nếu hợp đồng cho phép nhiều audience, mỗi Resource Server vẫn chỉ được sử dụng token khi `aud` chứa định danh của mình và các scope/claim thực sự áp dụng cho tài nguyên đó.

### 5.2. Vì sao cần namespace audience khác nhau?

RFC 9068 yêu cầu AS dùng **định danh `aud` khác nhau cho các resource riêng biệt do cùng issuer phát hành token**, để giảm nguy cơ API này nhận nhầm token của API khác. Không nên cấu hình mọi API cùng audience chung như `"all-apis"` chỉ để tiện xác minh, nếu các API thực sự có ranh giới quyền khác nhau.

Một URL resource identifier thường hữu ích vì mang namespace rõ ràng, nhưng `aud` là **định danh đã thỏa thuận**, không nhất thiết là URL endpoint đang chạy hay địa chỉ gọi API thực tế. Resource Server phải đối chiếu giá trị exact theo hợp đồng, không đoán audience từ Host header hoặc tự ý biến đổi chuỗi.

## 6. Luồng end-to-end theo RFC 9068

```mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth Client
    participant AS as Authorization Server
    participant RS as Orders API / Resource Server
    Client->>AS: Authorization Request (scope, resource=Orders API)
    AS-->>Client: Authorization code sau khi flow hoàn tất
    Client->>AS: POST /token (code + PKCE verifier; xác thực client khi cần)
    AS->>AS: Quyết định quyền, scope, aud, sub, client_id
    AS->>AS: Phát hành JWS với typ=at+jwt và required claims
    AS-->>Client: access_token, token_type=Bearer, expires_in
    Client->>RS: GET /api/orders, Authorization: Bearer access_token
    RS->>RS: Xác minh typ, ký, iss, aud, exp và hợp đồng claims
    RS->>RS: Kiểm tra scope/authority và quyền nghiệp vụ
    alt Token hợp lệ, được phép
        RS-->>Client: 200 + dữ liệu được phép
    else Token không hợp lệ hoặc thiếu quyền
        RS-->>Client: 401 invalid_token hoặc 403 insufficient_scope
    end
```

Hồ sơ cũng áp dụng cho access token được cấp từ **`client_credentials`** hoặc grant khác; Authorization Code chỉ là một ví dụ để thấy mối quan hệ giữa client, AS và RS. **Refresh token** để xin token mới ở AS và **ID token** cho OIDC client vẫn mang mục đích khác.

## 7. Resource Server phải xác minh những gì?

Điều kiện quan trọng nhất để tránh token confusion là **kiểm tra loại token `typ` cùng audience `aud`, không chỉ chữ ký**.

### 7.1. Quy trình xác minh ở Resource Server

Theo phần 4 của RFC 9068, RS nhận JWT access token cần thực hiện các kiểm tra sau:

| Bước | Điều kiện | Hành vi khi thất bại |
|---|---|---|
| **1. Token type** | `typ` là `at+jwt` hoặc `application/at+jwt`. | Từ chối; không nhận ID token hoặc JWT sai hồ sơ. |
| **2. Nếu token được mã hóa** | Giải mã với khóa/thuật toán đã thỏa thuận; khi đã thỏa thuận yêu cầu mã hóa, token không mã hóa **SHOULD** bị từ chối. | Từ chối khi không thể giải mã hoặc không đạt chính sách. |
| **3. Issuer** | `iss` phải **khớp chính xác** định danh issuer tin cậy. | Từ chối token từ issuer không phù hợp. |
| **4. Audience** | `aud` phải chứa identifier mà Resource Server mong đợi cho chính nó. | Từ chối token cấp cho API khác. |
| **5. Chữ ký** | Xác minh JWS theo RFC 7515 bằng khóa AS cung cấp; từ chối `alg=none`. | Từ chối token bị sửa hoặc ký bằng khóa/thuật toán không được tin. |
| **6. Hết hạn** | Thời gian hiện tại phải trước `exp`; chỉ cho phép độ lệch đồng hồ nhỏ khi cần. | Từ chối token đã hết hạn. |
| **7. Ủy quyền** | Xét `scope`, roles/entitlements nếu có và thông tin nghiệp vụ có liên quan. | Từ chối thao tác thiếu quyền. |

Hồ sơ còn quy định **sự hiện diện** của `sub`, `client_id`, `iat` và `jti`. Việc kiểm tra định dạng, ràng buộc thời gian và điều kiện tùy ứng dụng cần tuân theo hợp đồng. Ví dụ, nếu `iat` trong tương lai bất thường hoặc `client_id` không được phép dùng API, hệ thống có thể đặt quy tắc từ chối bổ sung.

**Quy tắc khóa và thuật toán:**

- AS và RS hỗ trợ RFC 9068 **MUST hỗ trợ `RS256`** trong bộ thuật toán chữ ký hỗ trợ. Điều này **không** có nghĩa mọi token phải được ký bằng `RS256`; thuật toán khác vẫn có thể được dùng theo hợp đồng.
- Ký bất đối xứng (ví dụ `RS256`, `ES256`) được **khuyến nghị** vì RS chỉ cần public key để kiểm tra. Không để header `alg` tự ý mở rộng danh sách thuật toán được phép.
- Có thể dùng OAuth Authorization Server Metadata (RFC 8414) hoặc OIDC Discovery để biết `issuer` và `jwks_uri`. Những nguồn này phải được cấu hình/tin cậy trước; không tải khóa từ URL tùy ý do token tự khai.
- Không xem việc dùng khóa khác nhau cho ID token và access token là đủ để chống token confusion: chính RS cần kiểm tra `typ` và `aud`.

### 7.2. 401, 403 và phân biệt lỗi

Khi token thiếu, sai chữ ký, sai `typ`, sai issuer/audience hoặc hết hạn, RS thường trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Khi token **được xác thực hợp lệ** nhưng thiếu `orders.read`, RS thường trả `403 Forbidden`; tùy cơ chế có thể kèm `insufficient_scope`. Mã lỗi OAuth Bearer tuân theo RFC 6750 và cấu hình thực tế; không cần trả chi tiết khóa, claims, token hoặc lý do nội bộ cho client.

Không sửa lỗi `401` bằng cách thử **ID token** hoặc **refresh token** trên API. Nếu access token hết hạn và client được cấp refresh token hợp lệ, client phải xin **access token mới ở token endpoint**.

## 8. Cấu hình Spring Security Resource Server để thực thi RFC 9068

### 8.1. Spring mặc định có xác minh `typ: at+jwt` không?

Cấu hình Spring Boot quen thuộc:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
```

giúp tạo bộ giải mã/xác minh JWT của issuer. Tuy nhiên, **không nên mặc nhiên kết luận chỉ có `issuer-uri` là toàn bộ hợp đồng RFC 9068**. Resource Server còn phải buộc dùng token type `at+jwt`, audience đúng và các claim tương ứng.

Spring Security cung cấp **`JwtValidators.createAtJwtValidator()`** cho cấu hình xác minh JWT access token theo RFC 9068. API này có trong những bản Spring Security gần đây (ví dụ 6.5; kiểm tra phiên bản thư viện dự án). Cách cấu hình dưới đây mô tả một **Resource Server Spring MVC với Spring Security 6.5**.

**Dependencies** theo Spring Boot/Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Starter Resource Server kéo theo các thành phần cần để decode/validate JWT từ Spring Security OAuth2 Resource Server + JOSE. Dự án phải dùng phiên bản Spring Boot tương thích phiên bản Spring Security đã chọn.

### 8.2. Khai báo `JwtDecoder` với RFC 9068 validator

Ví dụ chỉ cho phép client minh họa `web-orders` truy cập Orders API. Nếu API thực tế phục vụ nhiều client, chính sách `client_id` cần được thiết kế lại theo danh sách/quyền của hệ thống, không ép mọi token thuộc một client.

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class AccessTokenDecoderConfig {

    private static final String ISSUER = "https://login.example.com";
    private static final String AUDIENCE = "https://api.example.com/orders";
    private static final String CLIENT_ID = "web-orders";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER)
                    .validateTypes(false)
                    .build();

        decoder.setJwtValidator(
            JwtValidators.createAtJwtValidator()
                .issuer(ISSUER)
                .audience(AUDIENCE)
                .clientId(CLIENT_ID)
                .build()
        );

        return decoder;
    }
}
```

**Giải thích hai chi tiết dễ nhầm:**

- `.validateTypes(false)` **không có nghĩa bỏ kiểm tra type**. Nó giao việc xác minh `typ` từ lớp xử lý type mặc định của Nimbus sang **`JwtValidators.createAtJwtValidator()`**, để chấp nhận đúng type `at+jwt`/`application/at+jwt` theo RFC 9068. Nếu tắt kiểm tra type mà **không thêm validator tương ứng**, hệ thống có thể bỏ mất ranh giới token type.
- `.clientId(CLIENT_ID)` trong ví dụ là **điều kiện riêng** của Orders API chỉ nhận token cấp cho client `web-orders`. RFC 9068 yêu cầu claim `client_id` hiện diện, nhưng không yêu cầu mọi RS chỉ nhận duy nhất một client ID. Với nhiều OAuth clients, nên áp dụng chính sách cho phép phù hợp với quyền của chúng.

`JwtValidators.createAtJwtValidator()` là cơ chế thuận tiện của Spring, nhưng người triển khai vẫn phải thiết kế **scope/authority và quyền dữ liệu**. Nếu issuer đưa claim tùy chỉnh hoặc có hợp đồng chặt hơn (ví dụ giới hạn tenant, loại ứng dụng, grant), bổ sung validator/authorization policy tương ứng.

**Lưu ý về phiên bản:** hướng dẫn `validateTypes(false)` là cách thể hiện nhất quán trong tài liệu Spring Security 6.5; cách kiểm tra type mặc định có thể thay đổi theo phiên bản. Khi nâng cấp, xem tài liệu phiên bản đang dùng và không thay đổi cơ chế kiểm tra type mà không bảo đảm `at+jwt` vẫn được kiểm tra.

### 8.3. Bảo vệ endpoint theo scope

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain ordersSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Spring Security thường ánh xạ `scope` dạng chuỗi phân cách dấu cách (hoặc `scp` theo hỗ trợ mặc định) thành authority có tiền tố `SCOPE_`:

```text
JWT claim:   "scope": "orders.read orders.write"
Authorities: SCOPE_orders.read, SCOPE_orders.write
```

Nếu Authorization Server sử dụng `roles` hoặc `entitlements` với cấu trúc riêng, cấu hình `JwtAuthenticationConverter` hoặc giải pháp mapping quyền tương ứng. **RFC 9068 không biến `roles` thành `ROLE_*` trong Spring một cách tự động**. Mọi API thực tế vẫn phải thực thi kiểm tra quyền sở hữu đơn hàng, tenant và trạng thái dữ liệu.

Nếu backend kết hợp nhiều cơ chế xác thực (cookie, web login, bearer), cấu hình filter chains và CSRF cần dựa vào đường đi thực tế; ví dụ ở đây mô tả API dùng bearer token.

### 8.4. Có phải bật `audiences` trong YAML nữa không?

Nếu Resource Server **chỉ** sử dụng cấu hình chung, các phiên bản Spring Boot hỗ trợ `spring.security.oauth2.resourceserver.jwt.audiences` có thể kiểm tra audience qua thuộc tính:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - https://api.example.com/orders
```

Nhưng **chỉ bật audience** vẫn chưa tương đương hợp đồng RFC 9068, vì còn `typ` và các claims khác. Khi đã cung cấp `JwtDecoder` bean tùy chỉnh như mục 8.2, các điều kiện cần được đặt trong validator của decoder đó; không dựa vào việc Spring Boot tự ghép thêm mọi thuộc tính `jwt.*` vào custom bean.

### 8.5. Resource Server nhận JWE hoặc opaque token thì sao?

- **JWE:** RFC 9068 cho phép JWT access token được mã hóa. Khi AS/RS đã thỏa thuận mã hóa, RS phải có khả năng giải mã bằng khóa/thuật toán phù hợp và tiếp tục xác minh phần JWT đã ký. Cấu hình `oauth2ResourceServer().jwt()` phổ thông **không tự bảo đảm** hỗ trợ JWE; cần tích hợp decoder phù hợp.
- **Opaque token:** không có JOSE header `typ` để đọc theo JWS. Resource Server thường dùng `opaqueToken()`/introspection và kiểm tra metadata/quyền thích hợp. **Không áp dụng trình xác minh RFC 9068 lên một token opaque**.
- **JWT không theo RFC 9068:** có thể dùng được với validator khác nếu hợp đồng legacy cho phép, nhưng **không tuyên bố** token tuân thủ RFC 9068 khi thiếu `typ` hoặc các required claims.

## 9. Cấp JWT access token ở Authorization Server

### 9.1. Những gì AS phải thống nhất với RS

Hợp đồng giữa Authorization Server và Orders API nên nêu rõ:

| Thành phần | Ví dụ / điều kiện |
|---|---|
| Issuer | `https://login.example.com`, chính xác theo metadata và `iss`. |
| Token format | JWT ký, profile RFC 9068. |
| JOSE type | `typ: at+jwt`. |
| Signature | Thuật toán được phép, nguồn public keys/JWKS, rotation và xử lý khóa cũ. |
| Audience | `https://api.example.com/orders`. |
| Required claims | `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, `jti`. |
| Scope vocabulary | `orders.read`, `orders.write`; mapping endpoint và đối tượng quyền. |
| Client/grant policy | OAuth clients được cấp token, loại grants, các ràng buộc tenant và subject. |
| Lifetime & revocation | Thời hạn token, clock skew, xử lý thay đổi quyền và sự cố khóa/token. |
| Privacy | Claims tối thiểu; dữ liệu cá nhân nào được phép xuất hiện. |

### 9.2. Ví dụ về customizer trong Spring Authorization Server

Nếu tổ chức vận hành **Spring Authorization Server**, có thể tùy chỉnh JOSE header và claims trong hook `OAuth2TokenCustomizer<JwtEncodingContext>`. Đoạn mã dưới đây minh họa **một phần** hợp đồng; không phải cấu hình Authorization Server đầy đủ:

```java
package com.example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration
public class AccessTokenCustomizerConfig {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer() {
        return context -> {
            if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                context.getJwsHeader().type("at+jwt");

                // audience phải dựa trên resource được cấp phép,
                // không lấy tùy tiện từ input chưa được AS xác minh.
                context.getClaims().audience(
                    java.util.List.of("https://api.example.com/orders")
                );
                context.getClaims().claim(
                    "client_id",
                    context.getRegisteredClient().getClientId()
                );
            }
        };
    }
}
```

**Điều kiện áp dụng:** ví dụ giả định Authorization Server này **chỉ phát hành JWT access token hướng tới Orders API** ở đoạn xử lý tương ứng. Trong thực tế nhiều resource/audience, **không hardcode** cùng `aud` cho mọi client và mọi grant. Phải xác định audience dựa trên resource/scope được phép và chính sách AS, đồng thời bảo đảm `sub`, `iss`, `exp`, `iat`, `jti` có mặt và đúng nghĩa. Đăng ký customizer đúng vào generator JWT theo cấu hình Spring Authorization Server đang sử dụng.

Nếu AS còn phát hành ID token OIDC, **chỉ áp dụng `typ=at+jwt` cho access token**. Không ép ID token cùng type, vì ID token dành cho OIDC Client và có quy tắc riêng.

## 10. Các tình huống dễ sai hợp đồng

### 10.1. Token có `typ: JWT` nhưng chữ ký và audience đúng

```json
{
  "alg": "RS256",
  "typ": "JWT"
}
```

Resource Server **tuân thủ RFC 9068 phải từ chối** vì `typ` không phải `at+jwt` / `application/at+jwt`. Đây là bước ngăn một loại JWT khác bị dùng như access token. Không sửa ở API bằng cách vô hiệu hóa kiểm tra type; nếu AS có yêu cầu phát hành token theo RFC 9068, cần sửa hợp đồng **tại nơi phát hành**.

### 10.2. ID token bị gửi đến Orders API

ID token có `aud=web-orders` và có thể được ký bởi cùng issuer. Đổi header hoặc đọc được `sub` **không** làm nó trở thành quyền `orders.read`. API yêu cầu `typ` đúng, `aud` đúng và quyền đúng.

### 10.3. Access token cấp cho Inventory API

Token:

```json
{
  "typ": "at+jwt",
  "aud": "https://api.example.com/inventory",
  "scope": "inventory.read"
}
```

Dù token có chữ ký đúng và còn hạn, Orders API phải từ chối do `aud` không chứa identifier Orders API. Không suy luận “đều cùng issuer nên cùng dùng được”.

### 10.4. JWT access token thiếu `jti` hoặc `client_id`

Token có thể vẫn là JWT hợp lệ theo RFC 7519, và một decoder JWT chung có thể xác minh chữ ký thành công. Tuy nhiên nó **không đầy đủ hồ sơ RFC 9068** vì thiếu required claim. Kiểm tra bằng validator RFC 9068 và yêu cầu AS phát hành đúng, thay vì coi mọi JWT hợp lệ như token tuân thủ profile.

### 10.5. `client_credentials` dùng `sub` giống người dùng đặc quyền

Nếu một AS cho client tự chọn `client_id` rồi sao chép giá trị đó vào `sub`, RS có thể nhầm token máy với một user có quyền cao. Cần kiểm soát đăng ký client ID, mô hình subject, grant/authority và phân quyền ở API; không lấy `sub` đơn lẻ làm bằng chứng về quyền của một người dùng.

### 10.6. JWT hợp lệ nhưng scope mơ hồ

Token cùng lúc có `aud=[orders-api, inventory-api]` với `scope=read`, nhưng hai API dùng `read` với nghĩa khác nhau. AS phải tránh phát hành quyền không thể liên kết rõ với từng resource; RS cũng cần quy tắc phân tích phạm vi quyền cho mình và không cấp quyền từ những scope không rõ nguồn/đích.

## 11. Ma trận tình huống xác minh mẫu

Giả sử Orders API chỉ nhận issuer `https://login.example.com`, audience `https://api.example.com/orders`, token theo RFC 9068 và endpoint `GET /api/orders/42` yêu cầu `orders.read`.

| Tình huống | Trạng thái nhận định |
|---|---|
| `typ=at+jwt`; chữ ký hợp lệ; required claims hợp lệ; `aud` đúng; `scope=orders.read` | Có thể qua lớp token/scope; tiếp tục kiểm tra quyền xem đơn hàng số 42. |
| `typ=JWT` dù chữ ký hợp lệ | **401** / `invalid_token` do token type sai. |
| `typ=at+jwt` nhưng signature sai | **401** / `invalid_token`. |
| `iss` khác issuer cấu hình | **401** / `invalid_token`. |
| `aud=inventory-api` | **401** / `invalid_token`. |
| `exp` đã qua | **401** / `invalid_token`. |
| Thiếu `client_id` hoặc `jti` trong token tuyên bố RFC 9068 | Token không đáp ứng profile; phải từ chối theo validator profile. |
| Token hợp lệ nhưng `scope` không có `orders.read` | **403** / thiếu quyền, có thể `insufficient_scope`. |
| Token hợp lệ, scope đủ, nhưng chủ thể không sở hữu đơn hàng | API phải từ chối theo **chính sách nghiệp vụ** (thường `403` hoặc `404` tùy thiết kế). |

Khi kiểm tra lỗi, đừng ghi nguyên access token vào log. Những dữ kiện hữu ích hơn gồm endpoint, request ID, loại lỗi tổng quát, issuer/audience kỳ vọng và kết quả phân quyền đã giảm nhạy cảm.

## 12. Quy tắc thiết kế để triển khai thống nhất

1. **Chỉ nhận đúng profile đã thỏa thuận.** Nếu API yêu cầu RFC 9068, kiểm tra `typ` và required claims bằng validator phù hợp, không chỉ decode JWT.
2. **Audience là ranh giới giữa API.** Mỗi RS cần identifier rõ ràng; reject token sai `aud`.
3. **Đừng nhầm `client_id` với `sub`.** Đặc biệt trong `client_credentials`, subject có thể là máy/ứng dụng; chính sách user-delegated và machine-to-machine khác nhau.
4. **Scope phải có nghĩa với audience.** Từ chối quyền mơ hồ, không ánh xạ role hoặc scope tùy tiện.
5. **Xác minh chữ ký với khóa đáng tin.** Cố định issuer, giới hạn thuật toán, không chấp nhận `none`, quản lý JWKS/rotation.
6. **Phân biệt access token với ID token.** Cùng ký bằng một issuer không có nghĩa chúng hoán đổi cho nhau.
7. **JWT được ký không giấu claims.** Giảm dữ liệu riêng tư; JWE hoặc opaque token khi nhu cầu bảo mật dữ liệu yêu cầu.
8. **Client coi access token là opaque.** Đừng cho logic giao diện phụ thuộc vào việc tự đọc `scope`, `roles` hoặc `sub` từ access token.
9. **Chọn validator theo phiên bản Spring thực tế.** `JwtValidators.createAtJwtValidator()` phục vụ profile; `oauth2ResourceServer().jwt()` là tích hợp xác minh bearer JWT, còn quyền endpoint cần cấu hình riêng.
10. **Không nhầm việc tuân thủ profile với việc đã an toàn toàn bộ hệ thống.** RFC 9068 quy định định dạng và xác minh; ứng dụng còn cần kiểm soát tài nguyên, tenant, luồng token, thu hồi, chống đánh cắp và vận hành khóa.

## 13. Tài liệu chuẩn để tra cứu

- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): chuẩn chính, đặc biệt `2` (header/claims), `3` (request/resource), `4` (validation), `5–6` (security/privacy).
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): định dạng claims, `iss`, `sub`, `aud`, `exp`, `iat`, `jti`.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS header, chữ ký và kiểm tra tính toàn vẹn.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): tham số `resource` để làm rõ resource đích.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): bảo vệ trước thuật toán sai, token confusion và xác minh JWT.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách gửi bearer token và xử lý lỗi.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình JWT decoder và mục “Configuring RFC 9068 Validation”.
- [Spring Authorization Server — Core Model / Token Customizer](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): cách tùy chỉnh header/claims khi AS tạo JWT.

Khi xây hợp đồng giữa Authorization Server và Resource Server, hãy mô tả đồng thời **token type `typ`, nguồn phát hành `iss`, đích nhận `aud`, nhóm claim bắt buộc và quyền `scope`**. RFC 9068 giúp các hệ thống hiểu thống nhất rằng token đó là **OAuth access token đúng mục đích**, còn Spring Security là nơi thực thi việc xác minh và chính sách truy cập của API.
