# Không mã hóa thay cho authorization

Một dịch vụ **Payments API** nhận access token dạng **JWE**. Dịch vụ giải mã thành công, nhìn thấy `sub=user-42`, `scope=orders:read` và lập tức cho phép gọi `POST /payments/transfer`. Người triển khai giải thích: “Token đã được mã hóa bằng khóa của Payments API; ai không có khóa thì không tạo được token, nên không cần kiểm quyền thêm”.

Lập luận đó sai ở hai lớp. Thứ nhất, **khả năng giải mã** không chứng minh token được **Authorization Server tin cậy phát hành**: trong một số kiểu JWE, bất kỳ ai có **public encryption key** của người nhận cũng có thể tạo một ciphertext hợp lệ; AEAD authentication tag chỉ xác nhận tính toàn vẹn theo khóa/ngữ cảnh mã hóa, không tự tạo ra chữ ký của issuer. Thứ hai, **một token được phát hành hợp lệ** vẫn có thể **không dành cho Payments API**, không có `payments:write`, đã hết hạn/thu hồi hoặc thuộc người dùng không sở hữu tài khoản nguồn.

**Không mã hóa thay cho authorization** là nguyên tắc giữ rạch ròi ba câu hỏi:

1. **Confidentiality:** Ai được đọc nội dung token? → Mã hóa JWE và kiểm soát khóa giải mã.
2. **Authenticity và token validity:** Token có đúng từ issuer được tin, đúng mục đích, audience, thời gian và trạng thái không? → Chữ ký JWS hoặc cơ chế xác thực nguồn tương đương được profile định nghĩa, cùng các kiểm tra claims/state.
3. **Authorization:** Chủ thể và client có được thực hiện **hành động cụ thể lên tài nguyên cụ thể** ngay lúc này không? → Scope, policy, tenant, ownership, roles/attributes và business rules của Resource Server.

Ba câu hỏi có liên quan nhưng **không câu nào tự động thay thế hai câu còn lại**.

Bài thuộc chương **Token encryption** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối mã hóa token với mô hình tin cậy, JWT/opaque token, access/refresh/ID token, OAuth 2.0/OIDC, scope, audience, claims, phát hành, xác minh, lưu trữ, thu hồi và ngăn token bị đánh cắp hoặc phát lại.

Sau bài, bạn có thể giải thích chính xác JWE bảo vệ gì, thiết kế luồng **decrypt → verify provenance → validate token → evaluate authorization**, tránh nhầm JWE và JWS, thiết lập chính sách API theo tài nguyên, áp dụng sender-constrained token khi cần, cũng như kiểm thử các ca token mã hóa hợp lệ nhưng **không đủ quyền**.

## 1. Một token giải mã được vẫn có thể là yêu cầu trái phép

Giả sử hệ thống bán hàng phát một JWT access token chứa:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "client_id": "sales-web",
  "exp": 1795400900
}
~~~

Đây là **payload minh họa**, chưa phải token có chữ ký hay ciphertext thực. Authorization Server có thể ký và mã hóa token để **Orders API** đọc được. Một lỗi triển khai tại **Payments API** có thể chỉ kiểm rằng lớp JWE được giải mã bằng key chung, rồi nhận quyền **chuyển tiền** dù:

- `aud=orders-api` không dành cho Payments API.
- `scope=orders:read` không cấp `payments:write`.
- Không có phép kiểm account ownership hoặc limit chuyển tiền.
- `exp` có thể đã qua, hoặc grant đã bị thu hồi.
- Token có thể là **ID token** chứ không phải access token, nếu handler không phân biệt profile.

Một ví dụ quyền truy cập sai khác: access token được AS phát hợp lệ, dành cho Payments API và có `payments:read`, nhưng user-42 chỉ được xem tài khoản **A**. Nếu API chỉ kiểm `scope` rồi trả dữ liệu tài khoản **B**, đó là **Broken Object Level Authorization (BOLA/IDOR)**. Mã hóa token **không sửa được lỗi** này.

**Thông điệp chính:** JWE hạn chế ai đọc **claims**; Resource Server vẫn phải chứng minh yêu cầu là **đúng chủ thể, đúng client, đúng tài nguyên, đúng hành động, đúng thời điểm**.

## 2. Phân biệt bốn lớp bảo vệ

| Lớp | Câu hỏi | Công cụ thường gặp | Nếu thiếu |
|---|---|---|---|
| **Transport security** | Dữ liệu có được bảo vệ khi truyền giữa hai endpoint? | TLS/HTTPS, xác minh certificate | Token bị nghe lén hoặc thay đổi trên đường |
| **Confidentiality at token layer** | Ai đọc được claims nhạy cảm trong token ngoài đường truyền? | JWE, key management | JWT payload có thể bị đọc bởi nơi cầm token |
| **Cryptographic integrity / issuer authenticity** | Token có bị sửa và có đến từ nguồn phát hành được tin? | JWS signature, hoặc xác thực nguồn theo profile | Token giả/claim tự khai được nhận |
| **Authorization / lifecycle** | Token có đủ quyền ngay lúc request tới không? | Issuer/audience/type/time validation, scopes, ABAC/RBAC, consent, revocation | Token hợp lệ vẫn được dùng sai mục đích hoặc vượt quyền |

**TLS không thay JWE:** HTTPS bảo vệ trên từng chặng kết nối, nhưng token có thể nằm trong log, browser storage, queue, cache hoặc qua nhiều service sau khi TLS termination. JWE có thể giúp hạn chế việc đọc claims khi token được lưu/chuyển tiếp.

**JWE không thay TLS:** JWE không bảo vệ mọi HTTP header, URL, cookie, endpoint identity hoặc metadata request; bearer token bị lộ vẫn có thể bị phát lại dù ciphertext không đọc được.

**JWS không mã hóa payload:** Một JWT compact được ký kiểu JWS thường có **header.payload.signature** đều Base64URL-encoded, không phải ciphertext. Ai có token có thể đọc payload nhưng không được phép sửa mà vẫn giữ chữ ký hợp lệ.

**JWE không thay JWS khi cần issuer signature:** Tính toàn vẹn AEAD cho biết dữ liệu không bị thay đổi ngoài ý muốn trong một ciphertext được xác minh theo khóa nhận; với mã hóa khóa công khai phía người nhận, **người có public key có thể tạo ciphertext mới**. Nguồn phát hành phải được kiểm bằng cơ chế riêng.

## 3. JWE có năm phần, JWS thường có ba phần

Một **JWS Compact Serialization** phổ biến:

~~~text
BASE64URL(protected_header) .
BASE64URL(payload) .
BASE64URL(signature)
~~~

Một **JWE Compact Serialization** có **năm** phần:

~~~text
BASE64URL(protected_header) .
BASE64URL(encrypted_key) .
BASE64URL(iv) .
BASE64URL(ciphertext) .
BASE64URL(authentication_tag)
~~~

Khi dùng `alg=dir`, phần **encrypted_key** có thể rỗng theo JWE. Đếm dấu chấm chỉ giúp **phân loại cú pháp bước đầu**, không chứng minh token hợp lệ hoặc được phép truy cập.

### Header JWE minh họa

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "payments-encryption-2026-11",
  "cty": "JWT"
}
~~~

Trong đó:

- `alg`: thuật toán **quản lý/bao gói khóa mã hóa nội dung** (ví dụ RSA-OAEP-256 hoặc ECDH-ES tùy profile).
- `enc`: thuật toán **mã hóa nội dung có xác thực** (ví dụ A256GCM).
- `kid`: gợi ý chọn key đã đăng ký đúng recipient/issuer/key purpose; không phải quyền dùng một key bất kỳ.
- `cty=JWT`: có thể chỉ ra plaintext là một JWT lồng bên trong, tùy profile; **không tự bảo đảm nội dung bên trong được ký**.

**JWE protected header là dữ liệu được xác thực cùng ciphertext** trong cơ chế JWE đúng chuẩn, nhưng trước khi hoàn tất giải mã/xác thực, ứng dụng không được coi các field ấy là đáng tin. Dù tag hợp lệ, header vẫn không thay chính sách **allowed alg/enc, recipient, token profile và issuer**.

### JWT, JWS và JWE không đồng nghĩa

| Tình huống | Có confidentiality? | Có issuer signature? | Đủ điều kiện cấp quyền API? |
|---|---|---|---|
| JWS JWT ký bởi AS | Không che payload | Có nếu key/alg/issuer được tin và verify đúng | **Chưa**; phải kiểm claims/policy |
| JWE chứa JSON claims chưa ký | Có cho recipient được chọn | **Không mặc định** | **Không** |
| JWE bọc một JWS do AS ký | Có | Có **sau khi verify JWS bên trong** | **Chưa**; còn policy |
| Opaque token tra introspection | Không phải claims có thể tự đọc từ chuỗi | Tùy mô hình AS; thường không có JWS client-side | **Chưa**; phải kiểm active/aud/scope/policy |

**Không nhìn thấy claims vì bị mã hóa** không khiến claims đúng hoặc quyền rộng hơn.

## 4. Confidentiality, integrity và authenticity không được gom làm một

JWE thường dùng **Authenticated Encryption with Associated Data (AEAD)**. Với cấu hình đúng, authentication tag giúp phát hiện ciphertext và protected header/AAD bị thay đổi trái phép.

Tuy nhiên, **“authentication” trong AEAD không luôn là xác thực danh tính của Authorization Server**:

1. Nếu người nhận công bố **public encryption key**, bất kỳ ai biết public key có thể tạo JWE được mã hóa cho người nhận. Người nhận giải mã thành công **không chứng minh ai đã mã hóa**.
2. Nếu người phát và người nhận cùng biết **symmetric encryption key** theo một profile có bảo vệ thích hợp, tính hợp lệ của tag có thể chứng minh ciphertext được tạo bởi **bên có key**. Nhưng điều đó không tự chứng minh một **issuer duy nhất** nếu nhiều services cùng giữ key; không có non-repudiation.
3. Nếu encrypt-then-transport nhưng **không ký**, một endpoint tùy ý có public key người nhận có thể gửi claims tự khai đã mã hóa. Token vẫn “decryptable” nhưng không đáng tin làm access token.
4. Ngay cả khi AS là nguồn thực, **authorization của request** còn phụ thuộc resource/actions/tenant/grant/current policy.

~~~mermaid
flowchart TD
    A["JWE decrypt + tag validation succeeds"] --> B{"Inner issuer authenticity verified?"}
    B -->|Không| X["Reject; decryption is not issuer proof"]
    B -->|Có| C{"Token claims & purpose valid?"}
    C -->|Không| X
    C -->|Có| D{"Audience/scope/client binding match?"}
    D -->|Không| X
    D -->|Có| E{"Current resource/tenant policy allows action?"}
    E -->|Không| X
    E -->|Có| F["Allow"]
~~~

**Không lấy “đã decrypt thành công” làm tương đương “đã verify chữ ký”.** Nếu hệ thống chọn một profile sử dụng encryption-only với symmetric key làm cơ sở tin cậy, phải nêu rõ **các bên biết key, nguồn được phép phát token, giới hạn key purpose** và chứng minh contract ấy; không được mặc định công dụng đó trong OAuth/OIDC.

## 5. Những gì được bảo vệ và không được bảo vệ khi token mã hóa

Giả sử một access token JWE chứa:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "payments-api",
  "scope": "payments:read",
  "tenant_id": "tenant-a",
  "exp": 1795400900
}
~~~

**JWE che claims khỏi bên không có decryption key**, giúp giảm lộ subject/tenant/metadata khi ciphertext bị nhìn thấy. Nhưng:

| Nguy cơ | Mã hóa giúp gì? | Cần thêm gì? |
|---|---|---|
| Bên thứ ba đọc claims từ JWT bị chặn | Che nội dung claims | Key management và data minimization |
| Attacker sửa ciphertext | AEAD tag phát hiện sửa đổi | Allowed algorithms, đúng recipient key và error handling |
| Attacker tạo một JWE mới bằng public key RS | **Không ngăn được** việc tự mã hóa ciphertext | Issuer authenticity/JWS hoặc profile sender authentication |
| Attacker lấy nguyên bearer JWE còn hạn | **Không ngăn replay** token nguyên dạng | TTL, sender constraint, audience/scope, revoke |
| Token có scope đọc nhưng API cần quyền ghi | **Không giải quyết** | Authorization policy |
| Token có audience dành cho API khác | **Không giải quyết** | Kiểm `aud` |
| User bị gỡ khỏi tenant | **Không phát hiện tự động** | Current tenant membership/ABAC và revocation policy |
| Private decryption key lộ | Confidentiality bị ảnh hưởng | Key custody, rotation, incident response |
| Token bị ghi vào access log | Claims có thể vẫn bị che nhưng ciphertext là bearer credential | Không log token, hạn chế retention |

**Ciphertext vẫn là credential.** Mã hóa claims không khiến một token an toàn để công khai trong URL, analytics, browser history, chat, screenshot, Redis key hoặc error response.

## 6. OAuth 2.0: ai cấp quyền, ai bảo vệ tài nguyên?

Các vai trò cơ bản:

~~~mermaid
sequenceDiagram
    participant U as Resource Owner
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>AS: Xác thực/đồng ý quyền theo flow
    C->>AS: Grant + client authentication/PKCE theo policy
    AS->>AS: Đánh giá grant, client, scope, audience
    AS-->>C: Access token (có thể JWE)
    C->>RS: Bearer access token + request tài nguyên
    RS->>RS: Decrypt, verify provenance, validate token
    RS->>RS: Scope + current object/tenant authorization
    RS-->>C: Allow hoặc reject
~~~

- **Authorization Server (AS)**: phát token theo grant/client/user policy, chọn claims, lifetime, audience và protection profile.
- **Resource Server (RS)**: xác minh token theo issuer, kiểm token được dùng đúng API và quyết định **request cụ thể**.
- **Client**: trình token để gọi resource; không được tự quyết định quyền bằng cách mã hóa một payload.
- **Resource Owner/User**: có thể cấp consent cho phạm vi truy cập; consent không mặc định cấp quyền tới mọi resource object.

**Bên sở hữu decryption key không tự trở thành issuer.** Payments API có private key giải mã JWE chỉ để đọc nội dung dành cho mình; **nó không được tùy ý tự phát access token của AS**.

### Scope không phải lệnh cho phép mọi đối tượng

Giả sử scope `payments:read` nghĩa là client được hỏi Payments API về tài nguyên thuộc quyền. Nó không có nghĩa:

~~~text
payments:read  =>  đọc mọi giao dịch của tất cả người dùng
~~~

Đúng hơn:

~~~text
token is valid AND aud permits payments-api
AND scope includes payments:read
AND user/client can access requested account/transaction
AND current business policy permits request
~~~

Một JWT được mã hóa rất tốt nhưng chỉ kiểm scope vẫn có thể mắc **BOLA, horizontal/vertical privilege escalation**.

## 7. Thứ tự xử lý: decrypt → verify provenance → validate claims → authorize

Với profile yêu cầu JWT **vừa ký vừa mã hóa**, một lựa chọn thường gặp là **JWS bên trong JWE** (ký rồi mã hóa).

~~~text
Authorization Server:
  claims
    -> tạo JWS / ký bằng AS private signing key
    -> mã hóa JWS thành JWE cho Payments API public encryption key
    -> phát encrypted access token

Payments API:
  JWE decrypt với private decryption key của recipient
    -> nhận inner JWS
    -> JWS verify bằng AS public signing key từ trust store/JWKS
    -> kiểm iss/aud/exp/nbf/token type/scope
    -> kiểm account/tenant/ownership/current policy
    -> allow hoặc reject
~~~

### Cần phân biệt hai key sets

| Key | Ai nắm private/secret? | Dùng để làm gì? |
|---|---|---|
| **AS signing private key** | AS/KMS signing service | Ký JWS để Resource Server xác minh nguồn phát |
| **AS signing public key** | RS có thể lấy từ trusted JWKS | Verify chữ ký của AS; **không giải mã** |
| **RS recipient decryption private key** | Payments API/key service được phép | Giải mã JWE gửi cho Payments API |
| **RS recipient encryption public key** | AS có thể nhận qua trusted registration | Mã hóa JWE cho Payments API |
| **Symmetric content-encryption key (CEK)** | Được tạo/quản lý theo JWE `alg`/`enc` | Mã hóa nội dung; không mặc định đại diện issuer |

**Không dùng một key cho mọi mục đích** chỉ để giảm số file cấu hình. Signing, encryption, DPoP sender proof và mTLS client authentication là các trust domains khác nhau.

### JWS-only, JWE-only và nested JWT

Không có quy tắc rằng *mọi* access token đều phải dùng JWE hoặc mọi hệ thống phải dùng nested JWT. Thiết kế do **token profile và hợp đồng AS–RS** quyết định:

- **JWS-only JWT** thường đủ khi claims không nhạy cảm, cần integrity/authenticity và muốn RS verify offline.
- **JWE** hữu ích khi claims cần confidentiality cho một recipient và kiến trúc hỗ trợ phân phối encryption key.
- **Nested JWS-in-JWE** hữu ích khi vừa cần confidentiality vừa cần issuer signature.
- **Opaque token + introspection** có thể tránh việc phân phối tự chứa các claims và giúp AS kiểm trạng thái tập trung; cũng cần chống rò token và kiểm quyền.

**Không làm nested JWT theo phỏng đoán.** JOSE/JWT libraries phải thực thi đúng profile, các lớp header/claims, allowed algorithms và lỗi giải mã/xác minh.

## 8. JWT access token, ID token và refresh token không hoán đổi

| Loại | Đối tượng dùng chính | Điều phải hiểu khi mã hóa |
|---|---|---|
| **Access token (AT)** | Resource Server xác minh, client trình để truy cập API | JWE không thay kiểm `aud`, `scope`, `exp`, type và resource policy |
| **Refresh token (RT)** | Authorization Server token endpoint | Không được dùng làm Bearer access token; cần client/grant binding, rotation/revoke |
| **OIDC ID token** | Relying Party/client xác nhận authentication result | Kể cả encrypted ID token cũng không là API access token |
| **Authorization code** | Token endpoint đổi token qua client/redirect/PKCE binding | Không chấp nhận làm bearer token; code ngắn hạn/single-use |
| **Opaque access token** | RS gọi AS introspection hoặc trusted state service | Không cần là JWE; AS quản lý active/claims theo policy |
| **DPoP proof JWT** | Chứng minh sender nắm key khi dùng bound AT | Không phải access token và không cấp quyền tự thân |

Một **encrypted ID token** có thể chứa `sub` và `aud=shop-web-client`, được RP giải mã/verify hợp lệ. Nếu API Payments dùng nó như Bearer vì “giải mã được”, đó là **token substitution/confusion**: audience/token purpose sai ngay cả khi issuer đúng.

**Không cho phép kiểm token type chỉ bằng “có năm phần JWE”**. Định dạng mã hóa không phân biệt access/ID/refresh token theo ngữ nghĩa. Cần profile định rõ outer/inner headers, claims và nơi token được phép dùng.

## 9. Audience và recipient encryption key là hai ràng buộc khác nhau

Một JWE được mã hóa bằng public key của **Payments API** có thể giải mã ở Payments API. Nhưng liệu `aud` có đúng là **payments-api** không? Câu trả lời phải đến từ **claims đáng tin và AS–RS contract**, không phải từ việc đã dùng một public key.

Ví dụ:

~~~text
JWE recipient key = payments-api encryption key
inner JWT aud = orders-api
inner JWT scope = orders:read

Decrypt = OK
Issuer JWS signature = OK (giả sử do AS ký)
Audience = WRONG
Decision = REJECT
~~~

Điều này cũng áp dụng cho **multiple Resource Servers dùng chung decryption key**. Nếu một khóa giải mã được chia sẻ giữa Payments và Orders, nó không chứng minh token dành cho cả hai.

### Tenant/context isolation

Khi có nhiều tenants/issuers:

1. Xác định trusted issuer/profile **từ cấu hình**, không tự discover URL trong token chưa được xác minh.
2. Chọn decryption key theo **recipient/tenant registration** đã được quản trị, không theo một `kid` global.
3. Sau decrypt, xác minh issuer signature và `iss` theo allowlist.
4. Kiểm `aud` và token purpose.
5. Kiểm **tenant membership và quyền object** theo policy hiện hành.
6. Không cache kết quả authorize giữa tenants/objects chỉ vì cùng encrypted token.

**Được giải mã trong một tenant không phải quyền truy cập tenant ấy**. Một token hợp lệ nhưng dành cho account khác phải bị từ chối.

## 10. Claims có thể bị giả nếu chỉ tin plaintext giải mã

Đặc biệt với JWE dùng **public-key encryption**, attacker có thể biết public key và mã hóa JSON tùy ý cho recipient:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "admin-user",
  "aud": "payments-api",
  "scope": "payments:write",
  "exp": 1895400900
}
~~~

Nếu ứng dụng coi plaintext này là **issuer-signed access token** chỉ vì AEAD tag hợp lệ, nó có thể nhận **claims giả hoàn toàn**. `iss` trong payload do attacker tự viết **không chứng minh issuer**.

### Mã hóa khóa công khai không chứng minh ai đã mã hóa

~~~mermaid
sequenceDiagram
    participant X as Attacker
    participant K as Public encryption key of Payments
    participant RS as Payments API
    X->>K: Lấy public key được công bố/đăng ký
    X->>X: Tạo claims giả admin/scope cao
    X->>X: Encrypt thành JWE hợp cú pháp và AEAD
    X->>RS: Gửi JWE tùy tạo
    RS->>RS: Decrypt & verify AEAD tag OK
    alt Chỉ tin plaintext
        RS-->>X: Nguy cơ cấp quyền trái phép
    else Kiểm issuer signature / trusted origin rồi policy
        RS-->>X: Reject vì không chứng minh nguồn AS
    end
~~~

Đây là **minh họa lỗi verifier** khi nhận JWE-only như credential không có issuer authentication. Nó không nói JWE bị “phá mã”: thuật toán có thể hoạt động hoàn toàn đúng; **sai ở mô hình tin cậy ứng dụng**.

### Claims cần đến từ đâu?

- Từ **JWT JWS đã verify với signing key thuộc issuer tin cậy** (khi profile yêu cầu signed token).
- Hoặc từ **nguồn trạng thái/thông tin AS được xác thực**, ví dụ introspection response thuộc caller/issuer đúng.
- Hoặc từ **một encryption-only protocol có cơ chế source authentication/binding khác được xác định rõ**; không mặc định trong general OAuth access-token processing.

**Không lấy quyền từ raw JSON chỉ vì parse được và nằm trong JWE**.

## 11. Scope, role và claims không thay authorization của từng object

**Scope** thường mô tả phạm vi mà OAuth client được phép yêu cầu từ một Resource Server. Nó không luôn đại diện quyền chi tiết của user đối với từng đối tượng nghiệp vụ.

Ví dụ một token được AS phát hành và bảo vệ đúng bằng JWS-in-JWE:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "client_id": "finance-bff",
  "aud": "payments-api",
  "scope": "payments:read payments:write",
  "tenant_id": "tenant-a",
  "exp": 1795400900
}
~~~

Client gọi:

~~~http
POST /accounts/account-B/transfers HTTP/1.1
Host: payments.example.org
Authorization: Bearer <encrypted-access-token>
Content-Type: application/json

{"to_account":"account-C","amount":500}
~~~

Giả sử **account-B thuộc tenant-B**, trong khi token chỉ thuộc **tenant-A**. Dù decryption, issuer signature, `exp`, `aud` và scope đều hợp lệ, Payments API phải **từ chối** vì quyền sở hữu hoặc tenant boundary không hợp lệ.

### Một quyết định authorization đầy đủ

\[
\text{ALLOW} =
\text{ValidToken}
\land \text{CorrectAudience}
\land \text{RequiredScope}
\land \text{CurrentSubjectPolicy}
\land \text{ObjectAccess}
\land \text{BusinessConstraints}
\]

Trong đó **ValidToken** bao gồm đúng nguồn/tính toàn vẹn, token purpose, thời gian và trạng thái theo profile; **ObjectAccess** và **BusinessConstraints** được đánh giá theo dữ liệu nghiệp vụ hiện hành.

| Điều kiện | Ví dụ | Nguồn quyết định |
|---|---|---|
| Token purpose | Access token, không phải ID token | AS–RS profile |
| Issuer | `https://auth.example.org` nằm allowlist | Trusted AS config |
| Audience | `payments-api` | Resource Server contract |
| Scope | `payments:write` | Claims đã xác minh, policy mapping |
| Subject/client | User-42, finance-bff có quyền dùng API | Token claims + current policy |
| Tenant membership | User-42 còn thuộc tenant-A? | Identity/tenant authority đáng tin |
| Object ownership | Account-B có thuộc tenant-A/user được ủy quyền không? | Database nghiệp vụ |
| Business constraints | Hạn mức, trạng thái tài khoản, dual approval | Rules engine/transaction state |

### RBAC/ABAC và claim bị cũ

JWT tự chứa có thể mang **roles** hoặc **groups** tại thời điểm phát hành. Nếu admin gỡ vai trò **treasurer** sau đó, JWE vẫn giải mã bình thường, chữ ký vẫn hợp lệ và claims vẫn giữ role cũ đến khi hết hạn hoặc có cơ chế thu hồi. Với thao tác quan trọng, hãy kiểm **current authorization policy**, grant epoch/denylist hoặc dùng token lifetime ngắn và freshness SLO được phê duyệt.

**Mã hóa giúp che role/group claims khỏi bên không có key; nó không làm thông tin ấy tự cập nhật.**

## 12. Expiration, not-before và revocation vẫn phải được kiểm

Một token được mã hóa đúng bằng JWE không mất hiệu lực khi nội dung đã cũ; RS vẫn phải chủ động kiểm:

- **`exp`**: không chấp nhận token đã hết hạn.
- **`nbf`** nếu hiện diện và áp dụng: không dùng trước thời điểm cho phép.
- **`iat`** và thời gian sống hợp lý theo profile/risk policy khi cần.
- **Grant/client/user status**: token còn được phép theo AS/RS policy hay đã bị vô hiệu?
- **`jti` / token identifier**: dùng cho denylist/replay detection khi kiến trúc yêu cầu, không tự mặc định mọi JWT phải lưu `jti`.
- **Issuer/audience/type/scope**: vẫn bắt buộc dù decryption thành công.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: JWE access token
    RS->>RS: Decrypt + verify inner issuer signature
    RS->>RS: Claims exp/nbf/aud/scope đạt
    RS->>RS: Kiểm current policy/denied grants nếu yêu cầu
    RS-->>C: Allow khi đủ quyền
    Note over AS: AS revoke token hoặc grant
    C->>RS: Phát lại cùng JWE
    RS->>RS: Crypto layer vẫn có thể đúng
    RS->>RS: Revocation/current policy phải chặn
    RS-->>C: Reject theo revocation policy
~~~

**Revoke không làm ciphertext tự thay đổi.** Khi AS thu hồi một refresh token, nó có thể chặn việc xin token mới; access token đã phát có thể còn hợp lệ tùy policy. Với JWT offline verification, RS có thể không biết revoke sớm nếu không có trạng thái cập nhật.

### RFC 7009 và RFC 7662

- **RFC 7009 (Token Revocation):** client yêu cầu AS thu hồi token; không phải endpoint giải mã JWE.
- **RFC 7662 (Token Introspection):** RS/caller đủ quyền hỏi AS về token state/metadata; `active=true/false` không thay quyền trên tài nguyên.
- **JWE:** che nội dung token đối với bên không có decryption key; không tự lưu revoke state.

Nếu RS cache kết quả `active=true` quá lâu, token đã revoke vẫn có thể được dùng trong cửa sổ stale. **Encrypt/decrypt không làm cache trở nên mới hơn**. Với API nhạy cảm cần giới hạn TTL, invalidation và/hoặc nguồn trạng thái tươi theo freshness SLO.

## 13. Mã hóa bearer token không chống đánh cắp hoặc replay

Bearer token được chấp nhận theo nguyên tắc **ai trình token hợp lệ có thể thử sử dụng**. Kẻ tấn công có bản sao **JWE ciphertext nguyên vẹn** thường **không cần giải mã** để gửi lại token.

~~~text
Attacker tìm được JWE bearer token T trong log.

T là ciphertext, attacker không thấy sub/scope/tenant.

Nhưng:
  attacker -> POST API
  Authorization: Bearer T

RS tự giải mã T và kiểm quyền cho subject ghi trong T.
Nếu T còn hợp lệ và không sender-constrained:
  attacker có thể được xem là người giữ token hợp lệ.
~~~

Điểm mấu chốt:

| Phòng vệ | Bảo vệ được gì? | Không bảo vệ được gì? |
|---|---|---|
| JWE | Giảm lộ claims trong token | Không ngăn gửi lại nguyên ciphertext |
| TLS | Bảo vệ trên đường truyền đã xác thực | Không ngăn token rò từ log/client storage |
| Short-lived AT | Giảm thời gian sử dụng nếu bị lộ | Không ngăn attacker dùng trước `exp` |
| Narrow audience/scope | Giới hạn API/hành động có thể dùng | Không ngăn dùng trong phạm vi đã cấp |
| DPoP/mTLS sender-constrained AT | Đòi proof/kênh possession theo profile | Cần AS/RS kiểm `cnf` và proof chính xác |
| Revocation/denylist/introspection | Ngăn token tiếp tục sau thay đổi state nếu triển khai đúng | Không tự bảo đảm zero-latency tại mọi RS |
| Secure storage/redaction | Giảm rủi ro token bị đánh cắp | Không thay token validation/authorization |

### Sender-constrained tokens

Với DPoP, một access token có thể ràng buộc với JWK thumbprint của client; RS kiểm **DPoP proof** cho method/URI/token, timestamp, nonce/`jti` theo profile. Với mTLS-bound token, RS kiểm certificate binding.

**Key của DPoP sender khác key AS ký JWT và khác key RS giải mã JWE**. Không bỏ sender proof chỉ vì đã giải mã token; proof cần thực sự gắn với **request hiện tại**.

**Đừng lưu bearer JWE trong logs hoặc analytics** với lý do “không ai đọc được claims”: chính chuỗi ciphertext có thể là credential đủ để gọi API.

## 14. Key management: encryption key, signing key và quyền sử dụng

Một kiến trúc signed-then-encrypted JWT có ít nhất hai vòng đời khóa độc lập:

~~~text
Authorization Server / Signing Service:
  AS private signing key -> ký inner JWS
  AS public signing key  -> trusted issuer JWKS cho RS verify

Payments API / Recipient:
  Payments public encryption key -> AS dùng để mã hóa outer JWE
  Payments private decryption key -> RS/KMS dùng để giải mã
~~~

**Không tự chuyển AS signing JWKS thành recipient encryption JWKS.** Cả hai có thể dùng định dạng JWK/JWKS với `use=sig` hoặc `use=enc`, nhưng nguồn trust, owner, purpose, quyền truy cập và quy trình rotation khác nhau.

| Khóa | Cần giữ bí mật? | Hành động được phép | Nếu bị lộ |
|---|---|---|---|
| AS signing private key | **Có** | Ký token theo issuance policy | Attacker có thể giả mạo token AS |
| AS signing public key | Không | Verify issuer signature | Không đủ để ký token |
| RS decryption private key | **Có** | Giải mã token dành cho RS | Claims đã/đang mã hóa cho key này có nguy cơ bị đọc; cần đánh giá thời gian và phạm vi |
| RS encryption public key | Không | Mã hóa token cho RS | **Không tự chứng minh sender là AS** |
| Symmetric encryption key/CEK | **Có** | Mã hóa/giải mã theo JWE profile | Mất confidentiality, có thể mất authenticity trong mô hình symmetric |
| DPoP sender private key | **Có ở client** | Ký proof of possession | Attacker có thể bắt chước sender nếu cũng có token |

### Least privilege và KMS/HSM

- Chỉ AS token issuer được phép **ký** JWT; không đưa signing private key cho mọi RS.
- Chỉ RS/người nhận hợp lệ được phép **giải mã** token dành cho mình; phân quyền key theo environment/tenant.
- AS dùng public encryption key đã được đăng ký/cho phép của đúng RS, không lấy tùy ý từ HTTP request của client.
- KMS/HSM có thể giúp kiểm soát key custody, audit và hạn chế export, nhưng **quyền gọi decrypt** phải được giới hạn. Một service có quyền decrypt không tự có quyền **authorize API request**.
- Không dùng **cùng key material** cho encryption, HMAC JWT, cache HMAC fingerprint và DPoP trong một ứng dụng chỉ vì tiện quản trị.

### Rotation của recipient encryption key

~~~text
Phase A: RS có private key D1, AS biết public E1.
Phase B: RS chuẩn bị D2, công bố E2 qua trusted registration.
Phase C: AS bắt đầu mã hóa JWE mới cho E2; RS giữ D1+D2
         đủ để giải mã token hợp lệ đã phát trước đó.
Phase D: Sau khi mọi JWE cũ cần hỗ trợ hết hạn/không còn dùng,
         RS ngừng tin D1 và hủy/lưu trữ theo policy.
~~~

**Khi khóa giải mã bị xâm phạm**, có thể cần **ngừng dùng D1 sớm và phát lại token**, không đợi overlap theo lịch. Nếu ciphertext JWE cũ đã bị thu thập và private key bị lộ về sau, khả năng giải mã dữ liệu lịch sử phụ thuộc vào thuật toán/protocol, CEK/key agreement và cách key được bảo vệ; không tự tuyên bố mọi JWE sử dụng PFS.

## 15. Thuật toán JWE: chỉ cho phép profile đã kiểm soát

JOSE/JWE phân biệt:

- **`alg`**: quản lý hoặc trao đổi khóa cho content-encryption key.
- **`enc`**: thuật toán mã hóa nội dung và kiểm tính toàn vẹn.
- **`kid`**: key ID của **recipient encryption key** trong ngữ cảnh JWE (không phải tự động là issuer signing key).

Ví dụ policy minh họa:

~~~yaml
acceptedEncryptedTokenProfile:
  expectedIssuer: "https://auth.example.org"
  expectedAudience: "payments-api"
  tokenPurpose: "oauth_access_token"
  outerJwe:
    acceptedKeyManagementAlgorithms: ["RSA-OAEP-256"]
    acceptedContentEncryptionAlgorithms: ["A256GCM"]
    decryptionKeyOwner: "payments-api"
  innerJws:
    required: true
    acceptedSignatureAlgorithms: ["RS256"]
    signingKeySource: "trusted-issuer-jwks"
  rejectUnknownIssuer: true
  rejectUntrustedKeyUrls: true
  rejectUnsecuredJwt: true
~~~

**Đây là policy giả định**, không phải profile mặc định của OAuth hoặc một thư viện cụ thể. Một hệ thống có thể dùng ECDH-ES và các content algorithms khác nếu được hỗ trợ và thẩm định. Không cho token header tự quyết định algorithm nào được dùng.

### Những lỗi cần tránh

1. **Không cho `alg=none`** trong luồng cần chữ ký issuer ở inner JWS.
2. Không chấp nhận **RSA1_5** chỉ để tương thích cũ nếu policy hiện đại không cho phép; ưu tiên cấu hình chống các padding-oracle risks.
3. Không tùy tiện nhận `dir` với symmetric key “mượn” từ một hệ thống khác khi contract yêu cầu public-key encryption.
4. Không bật `zip`/compression cho token chứa secret kết hợp dữ liệu attacker chọn nếu chưa đánh giá side channel/kích thước; chặn decompression bombs.
5. Không bỏ qua kiểm **IV uniqueness/non-reuse** theo algorithm nếu chính ứng dụng tự thực hiện encryption; dùng JOSE/AEAD library sinh IV/CEK đúng cách.
6. Không dùng JWE header `jku`, `jwk`, `x5u` chưa tin làm nguồn khóa trực tiếp.
7. Không dùng encryption key để verify chữ ký JWS chỉ vì trùng `kid`.
8. Không tự viết AES-GCM tag checking hoặc padding logic; dùng thư viện mật mã được duy trì.

**Đúng crypto algorithm chưa đủ**: phải xác minh nội dung theo profile, issuer và quyền API.

## 16. Lưu trữ, vận chuyển và logging: ciphertext không phải dữ liệu vô hại

Token JWE vẫn là **bearer credential** trong nhiều thiết kế. Kể cả claims không thể đọc, **token string** và **key material** cần chính sách lưu trữ rõ:

| Nơi token có thể xuất hiện | Sai lầm thường gặp | Hướng an toàn |
|---|---|---|
| HTTP access log | Log nguyên `Authorization` | Redact header trước khi log |
| APM/tracing | Thu thập full request/response body chứa token | Sanitize nhạy cảm, allowlist fields |
| Browser URL | `?token=<JWE>` | Không truyền AT/RT trong URL |
| SPA storage | Lưu RT/AT dài hạn không tính tới XSS | Chọn BFF hoặc cơ chế storage/rotation phù hợp |
| Redis key | Dùng raw token làm cache key | HMAC fingerprint có namespace issuer/RS |
| Message broker | Đưa nguyên AT vào payload tồn tại lâu | Hạn chế truyền credential; dùng audience-bound token/identity context đúng profile |
| Error response | Trả plaintext claims khi decrypt lỗi | Trả lỗi tổng quát, không lộ secret |
| KMS audit | Ghi nguyên ciphertext/CEK hoặc decrypt output | Audit key ID, actor, action, reason, không raw sensitive data |

### TLS vẫn bắt buộc

Mã hóa token không thay việc **xác thực đúng máy chủ** và bảo vệ request qua TLS. Một attacker có thể thay request method/path/body hoặc ghi nhận JWE từ kết nối không bảo vệ. Nếu signature/PoP không gắn token với method/path, attacker có thể dùng lại nguyên bearer token để gọi chức năng khác trong phạm vi được cấp.

### Data minimization

Nếu API chỉ cần `sub`, `aud`, `scope` và thời hạn, đừng đưa số giấy tờ, địa chỉ, thông tin ngân hàng hay dữ liệu sức khỏe vào token rồi biện minh “đã JWE nên an toàn”. Các RS có decryption key, admin/operator có quyền decrypt hoặc bản sao ciphertext lịch sử vẫn là nguồn rủi ro. **Không thu thập/nhúng dữ liệu nhạy cảm là bảo vệ mạnh hơn so với chỉ mã hóa rồi phát tán rộng**.

## 17. Xử lý lỗi giải mã và xác minh theo nguyên tắc fail closed

Một Resource Server có thể gặp:

- Ciphertext JWE sai định dạng, thiếu segment hoặc vượt giới hạn kích thước.
- Protected header đòi `alg` hoặc `enc` không được phép.
- Key `kid` không thuộc recipient đã đăng ký.
- AEAD tag không hợp lệ, giải mã thất bại.
- Inner JWS không có hoặc chữ ký không hợp lệ.
- Issuer, audience, expiry, token type hoặc scope sai.
- Chính sách object/tenant không cho phép.
- KMS/decryption service tạm lỗi.

**Không trường hợp nào được chuyển thành Allow**. Phân biệt **token invalid** với **hạ tầng chưa thể xác minh token** để chọn response HTTP phù hợp; nhưng cả hai đều **không thực hiện thao tác được bảo vệ**.

~~~mermaid
flowchart TD
    A["Nhận encrypted access token"] --> B{"Profile/format/header hợp lệ?"}
    B -->|Không| X["Reject - token invalid"]
    B -->|Có| C{"KMS/key khả dụng và được phép?"}
    C -->|Không| Y["Fail closed - dependency error"]
    C -->|Có| D{"JWE decrypt + AEAD verify?"}
    D -->|Không| X
    D -->|Có| E{"Inner issuer signature/provenance valid?"}
    E -->|Không| X
    E -->|Có| F{"Time, type, iss, aud, scope valid?"}
    F -->|Không| X
    F -->|Có| G{"Current resource authorization allows?"}
    G -->|Không| Z["Reject - insufficient rights"]
    G -->|Có| H["Allow"]
~~~

### Cẩn thận với error oracle

Không công khai các câu như **“IV đúng nhưng tag sai ở byte 7”**, **“khóa giải mã nào đang hoạt động”**, **“decrypt OK, user-42 thuộc tenant-B”** cho caller chưa được xác thực. Một số lỗi cần phân biệt nội bộ để vận hành, nhưng public error body nên tiết lộ tối thiểu và không chứa raw token, plaintext claims hoặc key identifiers nhạy cảm.

**Không tạo fallback kiểu “nếu không decrypt được thì thử parse token như JWT plaintext và tin claims”** trừ khi hệ thống có nhiều token profiles được cấu hình rõ, mỗi profile có validation pipeline độc lập và không downgrade trust.

## 18. HTTP: encrypted token hợp lệ nhưng không đủ quyền

### Trường hợp scope thiếu

~~~http
POST /payments/transfer HTTP/1.1
Host: payments.example.org
Authorization: Bearer <encrypted-jwe-access-token>
Content-Type: application/json

{"from":"account-A","to":"account-B","amount":500}
~~~

Sau khi giải mã và verify issuer signature, Resource Server nhận:

~~~json
{
  "aud": "payments-api",
  "scope": "payments:read",
  "sub": "user-42"
}
~~~

**Không được cho phép** thao tác cần `payments:write`. Theo chính sách OAuth Bearer (RFC 6750), lỗi thiếu scope có thể được phản hồi bằng **403 Forbidden** và challenge `insufficient_scope` khi phù hợp:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="payments:write"
Cache-Control: no-store
~~~

Ví dụ header minh họa; không đưa vào error response thông tin tài khoản, plaintext JWT hay key secrets.

### Trường hợp không chứng minh được issuer

Một JWE do attacker tự tạo bằng public encryption key nhưng **không có inner JWS hợp lệ** phải bị từ chối ở validation. Tùy framework, một API có thể phản hồi:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

**Không trả 403 sau khi bỏ qua issuer signature** chỉ vì scope được tự khai là đủ: token đó chưa hợp lệ để vào bước authorization.

### Trường hợp token hợp lệ nhưng sai account

Nếu `scope=payments:write` đúng nhưng user-42 không có quyền trên account-B, API phải từ chối theo **resource-level authorization policy**, thường **403** hoặc **404** khi ẩn tồn tại tài nguyên là một phần của chính sách. Không để một encryption claim/recipient key thay phép kiểm ownership.

## 19. Java: minh họa pipeline decrypt, verify, authorize

Ví dụ Java dưới đây là **pseudocode kiến trúc**, không phải một JOSE implementation có thể copy vào production. Các interface được giả định do ứng dụng/framework cung cấp:

~~~java
public final class ProtectedPaymentsAuthorization {
    private final TrustedIssuerRegistry issuers;
    private final TrustedRecipientKeyStore decryptionKeys;
    private final JoseVerifier jose;
    private final CurrentPolicyService policy;
    private final Clock clock;

    public AuthorizationDecision authorize(
            String compactJwe,
            PaymentOperation operation,
            RequestContext request
    ) {
        // Không decode payload rồi tin claims.
        // Cấu hình issuer/recipient đến từ trusted deployment context.
        TrustedTokenProfile profile =
                issuers.profileFor(request.apiId(), request.tenantContext());

        if (!profile.acceptsJweInput(compactJwe)) {
            return AuthorizationDecision.rejectInvalidToken();
        }

        RecipientKey recipient = decryptionKeys.forConfiguredRecipient(
                profile.recipientId()
        );
        // verify nested JWE/JWS phải kiểm alg/enc/kid, AEAD tag,
        // inner JWS signature bằng issuer signing key được pin.
        VerifiedJwt claims = jose.decryptAndVerifySignedJwt(
                compactJwe, recipient, profile.allowedJoseAlgorithms(),
                profile.trustedIssuerSigningKeys()
        );
        if (claims == null || !claims.isAccessToken()
                || !claims.issuerEquals(profile.issuer())
                || !claims.audienceContains("payments-api")
                || !claims.isWithinTimeWindow(clock.instant())
                || !claims.hasScope(operation.requiredScope())) {
            return AuthorizationDecision.rejectInvalidOrInsufficient();
        }

        // Bước này mới là authorization của hành động cụ thể.
        if (!policy.canPerform(
                claims.subject(),
                claims.clientId(),
                request.tenantContext(),
                operation.accountId(),
                operation.action(),
                operation.amount())) {
            return AuthorizationDecision.deny();
        }
        return AuthorizationDecision.allow();
    }
}
~~~

**Các interface ở đây không tồn tại sẵn**; đây là thứ tự logic. Implementer cần dùng JOSE library có hỗ trợ JWE/JWS được duy trì, xử lý exception bằng fail closed, cấu hình `SecurityFilterChain`/middleware, authn/authorization context, issuer và recipient key registration thực tế.

### Bất biến cần kiểm khi code review

1. `claims` chỉ được khởi tạo **sau khi cả JWE authentication/decryption và inner issuer signature verification thành công** theo profile.
2. Không để `request.tenantContext()` từ input chưa tin quyết định arbitrary issuer/recipient key. Trust mapping phải được phê duyệt; tenant trong token cần được kiểm và ràng buộc lại.
3. `hasScope` không thay `policy.canPerform`.
4. Việc KMS lỗi, thiếu key, parsing lỗi hoặc issuer unknown phải **từ chối**, không dùng plaintext fallback.
5. Nếu token là sender-constrained, cần kiểm **DPoP/mTLS proof** cho request; ví dụ chưa triển khai phần đó.
6. Nếu API yêu cầu revoke freshness, `isWithinTimeWindow` không thay kiểm grant/revocation state.
7. Không đưa token hay decrypted claims ra log trong exception handler.

**Cần giữ authorization tại Resource Server** ngay cả khi phía AS đã kiểm grant lúc phát hành token. Quyền trên account, hạn mức, tenant membership và trạng thái tài nguyên có thể thay đổi sau khi token được phát.

## 20. Java: ví dụ policy-level tách scope khỏi quyền đối tượng

Một policy đơn giản:

~~~java
public interface PaymentAccessPolicy {
    boolean canWriteAccount(
            String subjectId,
            String clientId,
            String tenantId,
            String accountId,
            long transferAmountMinorUnits
    );
}

public final class TransferAuthorization {
    private final PaymentAccessPolicy currentPolicy;

    public TransferAuthorization(PaymentAccessPolicy currentPolicy) {
        this.currentPolicy = currentPolicy;
    }

    public boolean mayTransfer(
            VerifiedJwtToken token,
            String requestedTenantId,
            String sourceAccount,
            long amountMinorUnits
    ) {
        if (!token.isValidAccessTokenFor("payments-api")
                || !token.hasScope("payments:write")) {
            return false;
        }
        return currentPolicy.canWriteAccount(
                token.subject(),
                token.clientId(),
                requestedTenantId,
                sourceAccount,
                amountMinorUnits
        );
    }
}
~~~

`VerifiedJwtToken` là loại giá trị **chỉ được tạo sau trusted cryptographic/token validation**; không tạo từ JSON decode chưa verify. Ví dụ `PaymentAccessPolicy` cần kiểm tenant membership, ownership, trạng thái tài khoản và hạn mức bằng dữ liệu nghiệp vụ đáng tin, có transaction/locking khi thao tác thay đổi tài sản.

**Dùng `amountMinorUnits` (ví dụ cents) thay vì số thực cho tiền** là chi tiết minh họa nhằm tránh lỗi biểu diễn; nó không liên quan trực tiếp tới JWE nhưng cho thấy authorization thực tế phụ thuộc **amount**, đối tượng, thời gian và dữ liệu nghiệp vụ chứ không chỉ các claims token.

## 21. Spring Security: đừng nhầm hỗ trợ JWS JWT với hỗ trợ nested JWE

Các framework như Spring Security Resource Server thường có sẵn cơ chế xác minh **signed JWT access token** bằng public keys từ issuer JWKS và sau đó ánh xạ claims thành authorities. Nhưng điều này **không đồng nghĩa** một `JwtDecoder` cấu hình cho JWS tự động hỗ trợ **JWE compact serialization** hoặc nested JWE/JWS.

### Phân biệt adapter đúng

~~~text
JWS-only token:
  Bearer JWT
    -> trusted JwtDecoder / JWS verification
    -> claims validators
    -> authorization manager / policy

JWE containing signed JWT:
  Bearer JWE
    -> custom JWE processor / JOSE library configured for recipient
    -> decryption + authenticated tag validation
    -> trusted inner JWS verifier
    -> JWT claims/profile validators
    -> authorization manager / policy
~~~

Một lỗi thường gặp là **“vì Spring có JWT support nên cứ Base64URL decode đoạn JWE rồi map claims thành authorities”**. Với JWE, ciphertext không phải JSON claims có thể tin, còn inner JWS cần được xác minh sau decrypt. Phải dùng **adapter/profile được bảo trì**, không tự bypass signature khi framework mặc định không hiểu JWE.

### Mapping claims thành authorities không phải final authorization

Giả sử sau khi token đã được xác minh đầy đủ, framework ánh xạ `scope=payments:write` thành authority `SCOPE_payments:write`. Một rule:

~~~java
// Minh họa Spring Security method security.
@PreAuthorize("hasAuthority('SCOPE_payments:write')")
public void transfer(TransferRequest request) {
    paymentService.transfer(request);
}
~~~

Rule này **chỉ kiểm quyền chức năng**. Nó chưa chứng minh:

- Subject sở hữu **sourceAccount**.
- Request thuộc đúng tenant.
- Amount nằm trong hạn mức và có đủ approval.
- Tài khoản không bị khóa/đóng.
- Dữ liệu user/role hiện hành vẫn cho phép sau khi token phát.

Cần kiểm chính sách **tại service/authorization manager** với authenticated principal, tenant, account ID và context nghiệp vụ, trước khi commit giao dịch. Đừng ủy quyền cho client chỉ định `canTransfer=true` trong payload.

### Không nhận tự do claims thành role

~~~text
Nguy hiểm:
  any token claim "role":"ADMIN"
  -> authority ROLE_ADMIN
  -> allow privileged operations

Đúng:
  verified token issuer/type/audience
  -> mapping scope/role theo AS–RS contract
  -> current authorization policy nếu cần
  -> object-level checks
~~~

Một role claim từ issuer khác hoặc token ID có audience khác không được dùng để cấp quyền API dù thư viện decode/decrypt thành công.

## 22. Gateway, BFF và microservices: ranh giới decrypt không phải ranh giới cấp quyền

Trong kiến trúc phân tán, gateway có thể giải mã JWE trước rồi gửi thông tin user qua các services nội bộ. Điều này giảm nhu cầu cấp private decryption key cho mỗi service, nhưng tạo ranh giới tin cậy mới.

~~~mermaid
flowchart LR
    C["OAuth Client"] -->|Bearer JWE| G["API Gateway: decrypt + verify"]
    G -->|trusted auth context| O["Orders Service"]
    G -->|trusted auth context| P["Payments Service"]
    O --> A["Order policy + ownership"]
    P --> B["Payment policy + limits"]
~~~

### Vấn đề nếu chỉ gửi header tự khai

~~~http
X-User-Id: user-42
X-Scope: payments:write
X-Tenant-Id: tenant-a
~~~

Nếu Payments Service tin các header này **trong mọi request** mà không bảo đảm chúng chỉ do gateway đáng tin tạo, client có thể bypass gateway hoặc spoof header rồi leo quyền.

Các biện pháp:

1. Gateway phải **xóa/ghi đè header identity** đến từ client, không chuyển tiếp nguyên `X-User-Id`.
2. Backend chỉ nhận identity context qua **kết nối/giao thức nội bộ đã xác thực** như mTLS và trusted network identity; không coi “ở mạng private” là bảo đảm duy nhất.
3. Có thể dùng một **short-lived internal signed assertion** riêng với audience và purpose rõ, nhưng chính assertion này cũng phải được service verify/authorize.
4. Mỗi service **vẫn kiểm object-level authorization**, không trao quyền xem mọi order/payment chỉ vì gateway đã decrypt token.
5. Nếu một service cần token để gọi service khác, dùng token exchange/delegation hoặc audience-bound token theo profile; **không tự chuyển tiếp cùng bearer token sang mọi API**.

**Gateway authentication kết thúc tại một trust boundary; authorization của tài nguyên vẫn thuộc service thực thi nghiệp vụ**. Mã hóa JWE ở edge không tự phân phối quyền đúng tới từng microservice.

### Không đưa plaintext claims vào queue tùy tiện

Giải mã token ở gateway rồi đưa toàn bộ plaintext claims vào Kafka/queue có thể phá mục đích confidentiality ban đầu. Nếu worker cần identity context, chỉ truyền **thông tin tối thiểu đã được xác thực** và gắn đúng job/tenant/action; dùng envelope encryption/ACL/retention nếu có dữ liệu nhạy cảm. Không truyền raw bearer token trừ khi hợp đồng ủy quyền yêu cầu và các bên được phép sở hữu credential ấy.

## 23. Caching: tối ưu decrypt không được cache Allow vô hạn

Giải mã JWE và verify JWS có thể tốn CPU và KMS round trips. Một ứng dụng có thể muốn cache kết quả xác minh:

~~~text
cache[HMAC(cacheKeySecret, encryptedToken)] = {
  verifiedIssuer: "https://auth.example.org",
  subject: "user-42",
  audience: "payments-api",
  scope: ["payments:read"],
  exp: ...
}
~~~

**Cache này giữ token evidence đã kiểm**, không nên giữ quyết định **“user-42 được chuyển tiền từ account-B”** như một flag chung cho mọi requests.

### Rủi ro của positive cache

| Loại cache | Có thể cache gì? | Giới hạn quan trọng |
|---|---|---|
| Decryption key handle / KMS metadata | Key IDs, trust config theo policy | Rotation, emergency compromise và quyền dùng key |
| Verified JWT metadata | Claims từ token đã decrypt/verify | Không vượt `exp`, issuer/audience/type binding và revocation freshness |
| Introspection `active=true` | Trạng thái AS tại một thời điểm | Hard TTL ngắn theo policy, invalidate khi revoke, không sliding |
| Authorization decision | Quyền trên action/object/tenant cụ thể | Chỉ khi key bao đủ context và có policy invalidation phù hợp |
| User role/group membership | Tình trạng membership hiện hành | Cache theo freshness SLO riêng, không coi JWT encryption giải quyết |

Một token bị revoke không tự “bị hỏng ciphertext”. Nếu cache vẫn trả **verified=true** và bỏ kiểm trạng thái thu hồi, token có thể bị dùng lại. Các hệ thống cần:

- **Fixed TTL** cho positive token status khi cache.
- Kiểm `exp` mỗi request, không dùng data cũ quá hạn.
- Tách cache key theo issuer, RS audience, token purpose và token fingerprint HMAC.
- Không cache `allow` chung theo subject/scope cho nhiều objects.
- Khi key compromise, phải có cách **invalidate cached key trust/verified token evidence**, không tiếp tục dùng dữ liệu được verify bằng signing key đã distrust.
- KMS outage không tạo fallback sang **trust any claims** hoặc một key khác ngoài policy.

### Pre-decrypted token caching

Nếu lưu plaintext claims trong shared Redis, tổ chức đã tạo thêm nơi chứa dữ liệu mà JWE vốn muốn che khỏi hạ tầng trung gian. Xem xét **memory cache trong ranh giới tin cậy**, TTL/ACL, mã hóa ở rest và data minimization. **Mã hóa token trên đường không bảo đảm những claims sau decrypt tiếp tục bí mật nếu app ghi chúng ra log/cache**.

## 24. Khi signing key hoặc decryption key bị xâm phạm

Hai loại sự cố có hậu quả khác nhau và không nên ứng cứu cùng một checklist.

### A. AS private signing key bị lộ

Kẻ tấn công có thể tạo **inner JWS hợp lệ theo key cũ**. Nếu public encryption key của Payments API cũng được công bố, attacker có thể bọc inner JWS giả trong JWE. Lúc ấy **cả hai lớp crypto đều kiểm thành công** cho tới khi signing key mất trust.

Hướng ứng cứu:

- Ngừng phát token bằng key bị lộ, tạo signing key mới trong KMS/HSM.
- Đẩy **distrust/deny key ID** tới mọi verifier, kể cả nơi cache JWKS.
- Phân tích token lineage và thu hồi grant/AT/RT theo threat model.
- Đánh giá các API có khả năng bị lạm dụng, audit request và quyền thay đổi.
- Không tuyên bố “đã rotate khóa ký” khi Resource Servers vẫn tin key cũ.

### B. RS private decryption key bị lộ

Kẻ tấn công có thể giải mã các JWE dành cho key đó nếu có ciphertext và thuật toán/profile cho phép. Nhưng **biết decryption private key không nhất thiết cho phép ký inner JWS của AS**.

Hướng ứng cứu:

- Vô hiệu/rotate recipient key, cập nhật public encryption key ở trusted AS registration.
- Đảm bảo AS **không tiếp tục mã hóa** token mới bằng public key tương ứng private key đã lộ.
- Đánh giá dữ liệu riêng tư của **ciphertexts đã thu thập** và retention rủi ro.
- Thay đổi/thu hồi tokens theo policy nếu confidentiality breach có thể dẫn tới token theft/replay hoặc khả năng tấn công khác.
- Rà quyền KMS decrypt, access logs, backups và plaintext caches.

| Sự cố | Mất confidentiality? | Mất issuer authenticity? | Hành động trọng tâm |
|---|---|---|---|
| RS decryption private key lộ | **Có nguy cơ** | Không tự mất nếu AS signing key còn an toàn | Rotate encryption key, đánh giá dữ liệu lộ |
| AS signing private key lộ | Không nhất thiết lộ ciphertext | **Có** đối với signing key bị lộ | Emergency key distrust, phát lại credential |
| Shared symmetric JWE key lộ | Có | Có thể mất khả năng gắn người gửi nếu cùng secret dùng xác thực | Rotate và cô lập các bên biết key |
| Raw JWE bearer token lộ | Claims có thể còn được che | Chữ ký có thể vẫn hợp lệ | Thu hồi token, chặn replay theo policy |
| JWT `aud` sai nhưng crypto đúng | Không phải key incident | Không phải key incident | Sửa validation/authorization ở RS |

**Không dùng key rotation để thay kiểm tài nguyên.** Một Payments API thiếu object authorization vẫn có thể cho user hợp lệ chuyển tiền từ tài khoản sai sau khi mọi key đã được rotate hoàn hảo.

## 25. Năm tình huống vận hành thường gặp

### Tình huống A — Token mã hóa dành cho Orders bị gửi sang Payments

Orders API và Payments API cùng dùng một **decryption key cũ** vì lịch sử triển khai. Token có `aud=orders-api`, `scope=orders:read`, được ký bởi AS hợp lệ và mã hóa cho key chung. Payments API giải mã thành công. **Quyết định:** phải từ chối vì **audience và scope sai**; cần tách recipient keys theo ranh giới bảo mật khi khả thi.

### Tình huống B — User có scope nhưng không sở hữu đối tượng

Access token của user-42 có `payments:write`, còn account-B thuộc user-99. Dù JWE và JWS đều hợp lệ, **chuyển tiền phải bị từ chối**. Kiểm chứng với nguồn dữ liệu accounts và policy, không tin `account_id` caller tự nhập là do token cấp.

### Tình huống C — Attacker có public encryption key

Attacker tạo JWE chứa claims `role=admin` bằng public key của RS. Decryption thành công, nhưng **không có inner JWS được AS ký**. Pipeline đúng từ chối trước khi mapping role thành authority. **Không cần giả định AES-GCM bị phá**; đây là lỗi dùng encryption thay authentication.

### Tình huống D — Attacker giữ nguyên JWE còn hạn

Token bị copy từ HTTP access log. Attacker không đọc được claims nhưng có thể gửi `Authorization: Bearer <token>` nguyên vẹn. Hệ thống chỉ ngăn nếu token đã hết hạn, bị revoke, audience/scope không phù hợp, hoặc sender proof bắt buộc mà attacker không có. **Không dựa vào ciphertext để chống replay**.

### Tình huống E — Đổi quyền trong khi token chưa hết hạn

User-42 bị gỡ quyền `payments:write` lúc 10:02 nhưng JWT có `exp=10:30`. JWE/JWS vẫn đúng. Nếu RS chỉ dùng scope cũ, có thể cho thao tác ngoài quyền hiện hành. Hệ thống phải xác định SLO về cập nhật quyền, ví dụ kiểm membership/policy mỗi request, grant epoch, introspection hoặc access token lifetime ngắn. **Ciphertext không tự thay đổi sau khi admin gỡ quyền**.

## 26. Nên dùng JWE, JWS-only hay opaque token?

Không phải mọi trường hợp đều cần mã hóa access token ở lớp JOSE. Hãy chọn theo **threat model**, độ nhạy claims, ranh giới giữa AS/RS, khả năng quản lý khóa và yêu cầu revoke.

| Phương án | Lợi thế | Giới hạn | Nên cân nhắc khi |
|---|---|---|---|
| **JWS-only JWT access token** | RS verify offline; giảm network introspection; không cần recipient decryption key | Claims đọc được; revoke sớm cần cơ chế bổ sung | Claims tối thiểu, không nhạy cảm; nhiều RS cần verify |
| **JWS-in-JWE access token** | Giữ issuer signature và che claims khỏi nơi không có key giải mã | Thêm key management, parsing, KMS cost, rotation và profile complexity | Claims cần confidentiality cả khi token được chuyển/lưu |
| **JWE-only theo profile nguồn đáng tin đặc biệt** | Có confidentiality, có thể dùng symmetric-source authentication trong kiến trúc cụ thể | **Không mặc định chứng minh AS phát token**; public-key encryption không xác thực sender | Chỉ khi profile quy định rõ issuer authentication/binding và được security review |
| **Opaque access token + introspection** | RS không cần mang claims tự chứa; AS có thể kiểm trạng thái tập trung | Thêm AS dependency, phải bảo vệ introspection/caching | Cần kiểm trạng thái và metadata tại AS, không muốn public token claims |
| **Reference token + secure server-side session** | Giữ dữ liệu/credential trong hạ tầng được kiểm soát | Session/storage/availability/authorization vẫn là trách nhiệm của server | BFF/server-based ứng dụng phù hợp |

### Bốn câu hỏi quyết định

1. **Claims có cần đưa vào token không?** Nếu không, chọn data minimization hoặc opaque reference.
2. **Ai thực sự cần đọc claims?** Mã hóa cho đúng recipient, tránh chia sẻ private decryption key quá rộng.
3. **Bằng chứng issuer nào cần có?** Signed JWT/AS introspection/source authentication theo profile; không coi decryption là đủ.
4. **Ai quyết định quyền của request?** Resource Server với dữ liệu hiện hành, dù chọn token format nào.

**Không nên chọn JWE chỉ để “làm token an toàn hơn” mà chưa biết sẽ phân phối key ra sao và authorization được kiểm ở đâu.** Mã hóa tăng confidentiality; nó không tự tăng độ chi tiết hoặc độ mới của quyết định phân quyền.

## 27. Ma trận kiểm thử: ciphertext đúng nhưng quyền sai

Ma trận nên chạy với **token/test keys do AS test phát**, **JOSE library thực**, **Resource Server test** và **database quyền test**. Kiểm cả kết quả crypto/token validity lẫn API authorization; chỉ assert “decrypt OK” là chưa đủ.

| ID | Nhóm | Trường hợp | Kết quả mong đợi |
|---|---|---|---|
| **S01** | JWE | JWE đúng recipient key và `alg/enc` được duyệt | Giải mã/AEAD tag hợp lệ |
| **S02** | Nested | JWE chứa JWS do trusted AS ký | Inner JWS verify thành công |
| **S03** | Token | Issuer, audience, exp, type và scope đều hợp lệ | Qua lớp token validation |
| **S04** | Authorization | User có scope và sở hữu đúng account | Cho phép theo current policy |
| **S05** | Tenant | User có quyền account thuộc tenant được yêu cầu | Cho phép nếu mọi điều kiện khác hợp lệ |
| **S06** | Rotation | Recipient key mới đã đăng ký; RS còn giữ key cũ hợp lệ | Giải mã cả token mới/cũ theo overlap policy |
| **S07** | Key separation | JWE dùng RS encryption key, inner JWS dùng AS signing key | Đúng hai miền trust độc lập |
| **S08** | Sender constraint | AT ràng buộc DPoP/mTLS, proof hợp lệ cho request | Tiếp tục authorize theo claims và policy |
| **F01** | JWE | Ciphertext bị sửa một byte | AEAD/decrypt fail; từ chối |
| **F02** | JWE | Authentication tag bị sửa | Reject, không xuất plaintext |
| **F03** | JWE | `alg` không nằm allowlist | Reject, không fallback |
| **F04** | JWE | `enc` không được phê duyệt | Reject |
| **F05** | JWE | Header yêu cầu `RSA1_5` nhưng profile chỉ cho `RSA-OAEP-256` | Reject |
| **F06** | JWE | Header `kid` trỏ khóa khác recipient/trust context | Reject |
| **F07** | JWE | JWE quá dài/giải nén mở rộng quá lớn | Parser bảo vệ CPU/memory |
| **F08** | Provenance | Attacker dùng public encryption key tạo JWE với `role=admin`, không có JWS AS | Reject issuer authentication |
| **F09** | Provenance | JWE hợp lệ nhưng inner JWS signature giả | Reject |
| **F10** | Provenance | Inner JWS ký bởi issuer khác | Reject theo exact trusted issuer |
| **F11** | Provenance | Inner JWS `alg=none` | Reject nếu signed-token profile |
| **F12** | Provenance | Inner JWT signature hợp lệ với key của client thay AS | Reject wrong signing authority |
| **F13** | Provenance | Header `jku` chỉ đến domain attacker | Không tải/tin key tùy ý |
| **F14** | Provenance | Outer JWE `cty=JWT` nhưng plaintext là JSON claims không ký | Reject nếu profile yêu cầu JWS |
| **F15** | Claims | Token còn hợp lệ về crypto nhưng `aud=orders-api` tại Payments API | Reject |
| **F16** | Claims | Token `iss` khác expected issuer | Reject |
| **F17** | Claims | Token đã quá `exp` | Reject |
| **F18** | Claims | `nbf` nằm trong tương lai ngoài leeway | Reject |
| **F19** | Purpose | Encrypted OIDC ID token gửi làm Bearer API | Reject |
| **F20** | Purpose | Refresh token gửi làm Bearer API | Reject |
| **F21** | Purpose | Authorization code/DPoP proof dùng thay access token | Reject |
| **F22** | Scope | Token `payments:read` gọi endpoint `payments:write` | Reject insufficient scope |
| **F23** | Object | User có `payments:write` nhưng tài khoản thuộc user khác | Reject BOLA |
| **F24** | Tenant | User-42 không còn là thành viên tenant-B | Reject dù token chứa tenant/role cũ |
| **F25** | Role | Token tự chứa `role=admin` nhưng current policy đã gỡ quyền | Reject theo freshness/policy bắt buộc |
| **F26** | Business | Tài khoản đã bị khóa hoặc vượt hạn mức | Reject dù token crypto hợp lệ |
| **F27** | Business | Giao dịch cần dual approval nhưng chỉ một approval | Reject |
| **F28** | Revocation | Access token bị revoke nhưng ciphertext và chữ ký còn hợp lệ | Reject theo revocation mechanism được yêu cầu |
| **F29** | Revocation | Refresh token bị revoke nhưng AT chưa bị AS revoke | Không tự suy AT inactive; tuân AS/RS policy và SLO |
| **F30** | Replay | Attacker gửi lại cùng bearer JWE còn hạn | Test chứng minh JWE đơn lẻ không chặn replay |
| **F31** | DPoP | AT DPoP-bound nhưng không có proof | Reject |
| **F32** | DPoP | Proof sai method/URI/token hash hoặc `jti` replay | Reject theo profile |
| **F33** | mTLS | mTLS-bound AT nhưng certificate không khớp `cnf` | Reject |
| **F34** | Key | RS cố dùng AS signing key để decrypt JWE | Reject key purpose mismatch |
| **F35** | Key | RS private decryption key bị revoke/retired | Không dùng key ngoài policy |
| **F36** | Key | AS ký bằng compromised signing key đã bị distrust | Reject dù cached JWKS còn key |
| **F37** | Multi-issuer | Hai issuers có cùng `kid`, RS chọn key sai | Reject, tách issuer namespace |
| **F38** | Multi-tenant | JWE giải mã ở key chung nhưng `aud` và tenant không phù hợp | Reject |
| **F39** | Gateway | Client tự gửi `X-User-Id` hoặc `X-Scope` | Gateway/RS không tin header chưa xác thực |
| **F40** | Microservice | Gateway kiểm token rồi backend bỏ ownership check | Test phát hiện BOLA, backend phải từ chối |
| **F41** | Storage | Raw JWE được ghi vào access logs | Test phát hiện credential leakage |
| **F42** | Storage | Plaintext claims sau decrypt bị ghi vào shared cache không bảo vệ | Test phát hiện privacy/control issue |
| **F43** | Availability | KMS tạm lỗi, decryption không hoàn tất | Fail closed, không trả Allow |
| **F44** | Error oracle | Public response in `sub`, key ID, plaintext khi decrypt fail | Không tiết lộ secret/metadata |
| **F45** | Fallback | JWE decrypt fail nhưng app parse JSON chưa verify và nhận | Test bắt lỗi fail-open nghiêm trọng |
| **F46** | Cache | Verified token cache hết TTL/exp nhưng app tiếp tục sử dụng | Reject/token revalidate theo policy |
| **F47** | Cache | Policy thay đổi nhưng `allow` cached theo user/scope không có resource ID | Reject hoặc invalidate theo current policy |
| **F48** | Cache | Introspection active cache còn stale sau AS revoke | Không vượt revocation freshness SLO |
| **F49** | Logging | Exception từ JOSE library in nguyên ciphertext/tag/plaintext | Redact và kiểm quyền audit |
| **F50** | Parsing | JWE nested có lớp/encoding không đúng profile | Reject, không chấp nhận biểu diễn mơ hồ |
| **F51** | Issuance | AS cho client tự chỉ định `scope=admin` rồi ký/mã hóa không policy | Issuance phải kiểm grant/consent/client và resource binding |
| **F52** | Data minimization | Access token chứa PII không cần thiết dù encrypted | Security/privacy review phát hiện và loại bỏ |

**Khi kiểm thử thất bại, phân loại rõ lỗi ở bước nào**: transport, decryption, issuer provenance, token claims, scope, resource authorization, revocation hoặc operational key state. Không sửa vấn đề **authorization** bằng cách nới thuật toán JWE hay thêm một lớp mã hóa.

## 28. Bốn bài integration test thực hành

### Test A — JWE giả do attacker mã hóa bằng public key

~~~text
Given:
  Payments API chỉ chấp nhận JWS-in-JWE từ issuer được pin.
  Attacker biết public encryption key của Payments API.
When:
  Attacker mã hóa JSON:
    {"sub":"admin","aud":"payments-api","scope":"payments:write"}
  tạo JWE hợp lệ về mặt encryption/AEAD nhưng thiếu inner JWS AS.
Then:
  Payments API có thể decrypt ciphertext hợp lệ.
  Inner provenance validation thất bại.
  API từ chối, không tạo payment, không tạo principal ADMIN.
  Public error không lộ key/claims.
~~~

**Mục tiêu:** chứng minh **decryption success khác issuer authentication**. Đây là test quan trọng nhất để ngăn hiểu nhầm JWE thay chữ ký/nguồn phát hành.

### Test B — Token được phát hợp lệ nhưng sai tenant/account

~~~text
Given:
  AS phát JWS-in-JWE AT1 cho user-42:
    iss=trusted AS
    aud=payments-api
    scope=payments:write
    tenant_id=tenant-a
  Account B thuộc tenant-b.
When:
  User dùng AT1 yêu cầu transfer từ Account B.
Then:
  Decrypt JWE thành công.
  Verify issuer JWS/claims thành công.
  Required scope có thể hợp lệ.
  Current policy từ chối vì tenant/ownership sai.
  Không có chuyển tiền, không side effect giao dịch.
~~~

**Mục tiêu:** chứng minh **issuer token validity khác object-level authorization**. Cần thực thi bên trong service/transaction, không chỉ ở gateway.

### Test C — Token đã bị revoke nhưng JWE không đổi

~~~text
Given:
  AT1 là bearer JWS-in-JWE đang active.
  RS sử dụng introspection hoặc denylist/grant epoch theo policy.
When:
  t0: AS revoke chính AT1.
  t1: Client/attacker gửi lại ciphertext AT1 nguyên vẹn.
Then:
  JWE decrypt/inner JWS signature có thể vẫn đúng.
  RS từ chối AT1 khi trạng thái revoke đã được nhận biết
  trong giới hạn freshness SLO của hệ thống.
  Không dùng cached allow vô hạn do crypto verification success.
~~~

**Mục tiêu:** chứng minh **encryption không phải revocation hay replay prevention**. Nếu hệ thống JWT offline không hỗ trợ early revocation, test phải ghi nhận **giới hạn thật**, không giả vờ có SLO tức thời.

### Test D — Sự cố khóa giải mã và fallback

~~~text
Given:
  Payments API cần private key D1 trong trusted KMS để decrypt.
When:
  KMS trả unavailable hoặc D1 bị disabled.
Then:
  Token validation không thể hoàn tất.
  API fail closed / trả dependency error phù hợp.
  Không fallback sang JSON parse, JWT unsecured hoặc key của tenant khác.
  Không thực hiện payment side effect.
  Logs chỉ ghi reason code/correlation ID, không plaintext.
~~~

**Mục tiêu:** xác minh availability issue không trở thành đường **bỏ qua mã hóa/xác minh/authorization**.

## 29. Checklist triển khai: không mã hóa thay cho authorization

1. **Định nghĩa mục tiêu:** Có biết vì sao cần JWE thay vì JWS-only hoặc opaque token?
2. **Data minimization:** Claims nhạy cảm có thật sự cần nằm trong token?
3. **Trusted issuer:** Resource Server có issuer allowlist; không tự discover từ token chưa verify?
4. **Recipient key:** Public encryption key lấy từ trusted RS/client registration, không từ user-supplied URL?
5. **Key separation:** Signing key, decryption key và sender proof key có purpose/owners riêng?
6. **JWE algorithms:** Chỉ chấp nhận `alg`/`enc`/recipient được phê duyệt và dùng JOSE/AEAD library?
7. **Authenticated ciphertext:** Có kiểm JWE tag và protected header trước khi tin plaintext?
8. **Issuer provenance:** Với signed-token profile, có verify **inner JWS AS signature** bằng trusted key không?
9. **Nested profile:** Có kiểm đúng số lớp JWE/JWS, `typ`/`cty`, đúng cấu trúc và không downgrade?
10. **Token purpose:** Có phân biệt AT, RT, ID token, authorization code và DPoP proof?
11. **Issuer/audience:** Có kiểm exact trusted `iss` và expected resource `aud`?
12. **Validity:** Có kiểm `exp`, `nbf`, time policy và key/grant state khi cần?
13. **Scope:** Có kiểm scope theo HTTP action/API operation?
14. **Subject policy:** Có kiểm account/tenant/role hiện hành khi rủi ro yêu cầu?
15. **Object-level authorization:** Có kiểm quyền trên **resource ID thực** và không tin object ID caller tự khai?
16. **Business constraints:** Có kiểm limit, trạng thái tài khoản, approval và transaction consistency?
17. **Replay:** Có nhận ra bearer JWE bị copy vẫn có thể được phát lại? Cần DPoP/mTLS khi phù hợp?
18. **Revocation:** Có cơ chế early revocation/freshness SLO khi token bị thu hồi?
19. **Caching:** Có tách verified token cache, active status cache và object policy cache; không cache Allow vô hạn?
20. **Key rotation:** Có plan publish/register recipient keys, overlap và emergency distrust?
21. **KMS:** Quyền gọi decrypt/sign giới hạn theo issuer/tenant/workload; có audit/incident response?
22. **Transport:** TLS đúng certificate, không dùng JWE làm lý do bỏ HTTPS?
23. **Storage:** Không log raw JWE/Authorization header, không dùng token làm URL/Redis key?
24. **Plaintext lifecycle:** Claims sau decrypt có access control, retention và redaction?
25. **Error handling:** Invalid token/KMS failure đều fail closed, không fallback sang unsecured parsing?
26. **Gateway:** Identity headers được authenticated/overwritten; backend vẫn kiểm resource policy?
27. **Monitoring:** Có metric decrypt failures, signature failures, insufficient scope, policy denials, revoke lag?
28. **Testing:** Có ciphertext tự tạo, JWS thiếu, wrong aud/scope, BOLA, replay, expired/revoked, wrong key và outage tests?

## 30. Câu hỏi tự đánh giá

**1. JWE giải mã thành công có chứng minh token do Authorization Server phát không?** Không mặc định. Với public-key encryption, bất kỳ ai có public key của recipient có thể tạo ciphertext; cần issuer authenticity theo profile, thường là inner JWS được verify.

**2. Nếu ciphertext có AEAD tag hợp lệ thì có đủ tin `role=admin` không?** Không. AEAD bảo vệ nội dung mã hóa theo khóa/ngữ cảnh, nhưng không tự chứng minh claim đó được AS cấp theo grant và policy.

**3. Mã hóa có thay chữ ký số không?** Không. Encryption và signature có mục đích khác nhau. Với signed-then-encrypted JWT, phải decrypt outer JWE và verify inner JWS.

**4. JWS-only JWT có che claims không?** Không. Payload JWS compact thường chỉ Base64URL-encoded, người giữ token có thể đọc.

**5. Có nhất thiết mọi token đều dùng JWE không?** Không. Chọn JWS-only, JWS-in-JWE hoặc opaque + introspection theo threat model, dữ liệu và trust architecture.

**6. Vì sao JWE mã hóa cho Payments API vẫn phải kiểm `aud`?** Recipient encryption key không phải authorization audience. Một token có thể decrypt được ở recipient nhưng claims không dành cho API đó.

**7. Token có `scope=payments:write` có cho sửa mọi account không?** Không. Cần ownership, tenant, current policy, hạn mức và business constraints.

**8. Token đã bị revoke thì ciphertext JWE thay đổi không?** Không. Crypto có thể vẫn hợp lệ; RS cần cơ chế nhận biết revoke theo SLO.

**9. Attacker có bản sao JWE Bearer token cần biết private key để gọi API không?** Không. Nếu token vẫn hợp lệ và không sender-constrained, họ có thể gửi lại nguyên ciphertext.

**10. DPoP/mTLS bảo vệ gì khác JWE?** Chúng có thể ràng buộc access token với **sender key/certificate**, hạn chế replay bởi người chỉ giữ token. RS phải kiểm proof/binding theo profile.

**11. ID token được mã hóa có dùng làm access token không?** Không. ID token dành cho RP theo OIDC, khác mục đích/audience với access token của RS.

**12. Có thể dùng AS signing private key tại Payments API để giải mã JWE không?** Không nên trộn trust/key purposes. AS ký bằng signing key; Payments API giải mã bằng recipient decryption key được quản lý riêng.

**13. Khi KMS không truy cập được có được bỏ decrypt rồi tin claims không?** Không. Nếu không có bằng chứng token hợp lệ, phải fail closed và xử lý dependency error.

**14. Nếu gateway đã decrypt và verify token, backend có được bỏ object authorization không?** Không. Gateway có thể xác thực identity; service vẫn chịu trách nhiệm quyền tài nguyên/hành động, và phải tin context qua kênh đã xác thực.

**15. Nếu signing private key bị lộ, JWE còn bảo vệ API không?** Attacker có thể ký inner JWS giả và mã hóa cho RS bằng public key; phải emergency distrust signing key, không coi JWE là lớp thay signature trust.

**16. Một private decryption key bị lộ có nghĩa issuer signature tự bị giả không?** Không nhất thiết. Nhưng confidentiality của tokens dành cho recipient bị đe dọa; cần rotation/đánh giá token và dữ liệu.

**17. Tại sao không đưa nhiều PII vào encrypted token?** Vì token được sao chép/giải mã tại các bên được phép, và rủi ro retention/key compromise tồn tại. Data minimization giảm hậu quả ngay từ thiết kế.

**18. Kiểm thử quan trọng nhất cho nguyên tắc bài là gì?** Dùng một JWE **decrypt OK nhưng không có issuer signature hợp lệ** và một JWE/JWS hợp lệ nhưng **sai scope, audience hoặc object ownership**; tất cả phải bị từ chối.

## 31. Tài liệu chuẩn và tổng kết

Để thiết kế theo profile thật, đối chiếu:

- **RFC 7516 — JSON Web Encryption (JWE):** cấu trúc JWE, protected header, key management và authenticated encryption.
- **RFC 7515 — JSON Web Signature (JWS):** chữ ký/MAC của nội dung.
- **RFC 7517 — JSON Web Key (JWK):** public/private JWK, key purpose và JWKS distribution.
- **RFC 7518 — JSON Web Algorithms (JWA):** `alg`, `enc`, key type, encryption/signing algorithms.
- **RFC 7519 — JSON Web Token (JWT):** claims và nested JWT processing khi áp dụng.
- **RFC 8725 — JWT Best Current Practices:** chống algorithm confusion, token substitution và cross-JWT confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** validation và token type requirements cho access-token profile khi sử dụng.
- **RFC 6749 — OAuth 2.0:** AS/RS/client, scope và authorization grants.
- **RFC 6750 — Bearer Token Usage:** bearer tokens và HTTP error semantics.
- **RFC 7009 — Token Revocation** và **RFC 7662 — Token Introspection:** thu hồi/trạng thái active, khác với mã hóa.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)** và **RFC 8705 — Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** sender constraint khi phù hợp.
- **OWASP API Security Top 10:** Broken Object Level Authorization và các lỗi API authorization phổ biến.

Không phải mọi Authorization Server, Resource Server hay JOSE library đều hỗ trợ cùng cấu hình **nested JWE/JWS, algorithm, recipient encryption key registration và token profile**. Hãy kiểm phiên bản thư viện, thuộc tính profile và các đường lỗi trong môi trường thật; không tự suy từ một JWE sample rằng mọi token có cùng semantics.

**Ghi nhớ:** **Mã hóa JWE bảo vệ bí mật của nội dung token; nó không cấp quyền, không chứng minh nguồn phát hành trong mọi mô hình và không ngăn bearer token bị phát lại.** Resource Server phải **giải mã và xác thực ciphertext**, **xác minh issuer provenance theo token profile**, **kiểm token type, issuer, audience, thời gian, scope và revocation**, rồi **đánh giá authorization của chính user/client đối với tài nguyên và hành động hiện tại**. Một request được **decrypt thành công** vẫn phải bị **từ chối** nếu thiếu quyền. Đó là ranh giới bảo mật cốt lõi của bài **“Không mã hóa thay cho authorization”**.
