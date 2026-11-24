# OIDC discovery: tìm cấu hình OpenID Provider an toàn trong IAM lifecycle

**OIDC discovery** là cơ chế cho phép một **Relying Party (RP)** — ứng dụng sử dụng OpenID Connect (OIDC) — lấy và hiểu **metadata do OpenID Provider (OP)** công bố, thay vì phải cấu hình thủ công từng endpoint và khả năng hỗ trợ. Metadata thường được cung cấp dưới dạng JSON qua địa chỉ `/.well-known/openid-configuration` được hình thành từ **issuer**. Từ đó, RP biết nơi bắt đầu luồng xác thực, nơi đổi authorization code lấy token, nơi nhận khóa công khai để kiểm chứng chữ ký và những tính năng OP công bố.

Ví dụ: công ty có IdP với **issuer** là `https://login.example.invalid/workforce`. RP được cấu hình tin cậy issuer này, truy vấn metadata OIDC ở `https://login.example.invalid/workforce/.well-known/openid-configuration`, kiểm tra trường `issuer` có khớp chính xác không, rồi dùng các endpoint phù hợp. Khi IdP xoay vòng khóa ký, metadata chỉ dẫn tới **JWKS URI**, nơi RP tải bộ khóa công khai hiện hành để kiểm chứng ID token. Tuy nhiên, **tải metadata thành công không tự động có nghĩa mọi URL hoặc token trả về đều đáng tin**.

Bài học thuộc chương **OAuth và OIDC** của module **quản lý vòng đời danh tính IAM** theo mô hình **Joiner–Mover–Leaver (JML)**. Trọng tâm là cơ chế discovery, **ranh giới tin cậy**, **kiểm chứng issuer/khóa/token**, vận hành nhiều IdP/tenant, cùng việc kết nối **IdP, SSO, SCIM, RBAC/ABAC**, tài khoản dịch vụ, kiểm toán và kiểm soát quyền truy cập tồn dư. Mục tiêu không chỉ là “biết URL well-known”, mà là **biết khi nào có thể dùng thông tin tìm được và khi nào bắt buộc phải từ chối**.

> **Luận điểm nền tảng:** Discovery cung cấp **thông tin cấu hình về một OP đã được chọn theo chính sách**; nó không tự xác minh danh tính người dùng, không tự đăng ký client, không tạo account ở ứng dụng và không chứng minh người dùng được phép truy cập tài nguyên.

## 1. Những khái niệm phải tách biệt

| Khái niệm | Trách nhiệm | Không nên nhầm với |
| --- | --- | --- |
| **OpenID Provider (OP)** | Dịch vụ xác thực người dùng và cung cấp kết quả định danh OIDC. | Ứng dụng sử dụng OIDC. |
| **Issuer (`iss`)** | Định danh của OP, dùng để kiểm chứng nơi đã phát hành ID token. | Tên hiển thị hoặc email domain của công ty. |
| **Relying Party (RP)** | Ứng dụng OIDC yêu cầu và kiểm chứng kết quả xác thực. | Resource server bất kỳ chỉ xác minh access token. |
| **OIDC Provider Discovery** | Lấy metadata của OP tại well-known URL dựa trên issuer. | Tìm kiếm tùy ý mọi IdP trên Internet. |
| **Issuer discovery / WebFinger** | Có thể giúp tìm issuer từ một thông tin đầu vào trong những mô hình cho phép. | Bằng chứng người khai thông tin là chủ account đó. |
| **Home realm/IdP discovery** | Quyết định người dùng/tenant được định tuyến tới IdP nào. | Metadata discovery sau khi đã chọn issuer. |
| **OIDC client registration** | Đăng ký client, redirect URI, phương thức xác thực client và chính sách. | Tự động diễn ra chỉ vì có metadata. |
| **JWKS** | JSON Web Key Set, tập khóa công khai OP công bố cho chức năng phù hợp. | Secret của người dùng, mã nhân viên hay access token. |
| **SCIM provisioning** | Tạo/cập nhật/vô hiệu hóa User/Group ở hệ thống đích khi được hỗ trợ. | OIDC login hoặc OIDC discovery. |
| **Authorization (RBAC/ABAC)** | Quyết định chủ thể đã được xác thực có được làm gì trên tài nguyên. | Kiểm tra chữ ký ID token. |

### 1.1. OIDC và OAuth 2.0 khác nhau ở đâu?

**OAuth 2.0** chủ yếu là khuôn khổ ủy quyền: client lấy quyền truy cập tài nguyên thông qua authorization server theo một grant phù hợp. **OIDC** bổ sung lớp định danh trên OAuth 2.0: RP yêu cầu scope `openid`, nhận và kiểm chứng **ID token** theo quy tắc OIDC, có thể dùng thêm UserInfo nếu được hỗ trợ.

**OIDC discovery** mô tả **metadata của OpenID Provider**. Một **OAuth 2.0 Authorization Server** cũng có thể công bố metadata theo **RFC 8414**. Hai tài liệu và các quy tắc tạo well-known URI có quan hệ nhưng **không được tự coi là đồng nhất**, đặc biệt khi issuer chứa path; xem phần 3.

### 1.2. Địa chỉ issuer là danh tính của OP

Issuer có thể là một URL HTTPS với path, ví dụ `https://login.example.invalid/workforce`. Một sản phẩm nhiều tenant có thể công bố issuer khác nhau cho từng tenant. Trong OIDC, RP phải kiểm tra **issuer trong metadata** đúng bằng issuer đã được xác định, và **`iss` trong ID token** phải đúng với issuer RP đang tin cậy cho giao dịch.

Không nên rút gọn issuer thành hostname hoặc so khớp gần đúng. Hai issuer sau không tự động giống nhau:

~~~text
https://login.example.invalid/tenant-a
https://login.example.invalid/tenant-b
~~~

Ngay cả khi cùng hostname và cùng OP software, chúng có thể đại diện **hai ranh giới danh tính khác nhau**. Tránh chấp nhận token từ tenant B chỉ vì khóa ký hoặc tên miền trông giống tenant A.

## 2. Luồng discovery từ issuer tới phiên đăng nhập

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as Ứng dụng / RP
    participant REG as Tenant / Issuer Registry
    participant OP as OpenID Provider
    participant JWKS as JWKS Endpoint
    participant USER as Trình duyệt người dùng
    RP->>REG: Chọn issuer đã được cho phép cho tenant
    REG-->>RP: https://login.example.invalid/workforce
    RP->>OP: GET issuer + /.well-known/openid-configuration
    OP-->>RP: JSON Provider Metadata
    RP->>RP: Kiểm tra issuer chính xác, endpoint và khả năng
    RP->>JWKS: GET jwks_uri khi cần
    JWKS-->>RP: Public JSON Web Keys
    RP->>RP: Chọn thuật toán/key theo policy
    USER->>RP: Bắt đầu đăng nhập
    RP-->>USER: Redirect tới authorization_endpoint với state + PKCE
    USER->>OP: Xác thực, MFA, consent/policy theo luồng
    OP-->>USER: Callback với authorization code + state
    USER->>RP: Trả callback
    RP->>OP: Token request hợp lệ + code_verifier
    OP-->>RP: ID token và các token tùy luồng
    RP->>RP: Kiểm tra chữ ký, iss, aud, exp, nonce khi cần
    RP->>RP: Liên kết identity/account, kiểm tra vòng đời và quyền
~~~

Các điểm kiểm tra trong sơ đồ thuộc **nhiều giai đoạn**: chọn OP; tải/kiểm tra cấu hình; xác thực; kiểm chứng ID token; rồi mới liên kết account và phân quyền. **Không bỏ qua bước kiểm chứng token** vì đã thấy metadata lấy qua HTTPS.

### 2.1. Các trách nhiệm ở mỗi lớp

1. **Identity/tenant registry:** quyết định issuer nào được phép dùng cho ứng dụng/đơn vị. Đây là **quyết định tin cậy**.
2. **Discovery client:** lấy metadata đúng issuer và kiểm tra cấu hình đã công bố. Đây là **khám phá khả năng**.
3. **OIDC client:** tạo authorization request và hoàn tất luồng, chống CSRF/replay theo profile. Đây là **thực hiện xác thực**.
4. **Token verifier:** kiểm tra ID token từ OP đã tin cậy theo policy. Đây là **xác minh bằng chứng định danh**.
5. **IAM/ứng dụng:** liên kết subject với account, kiểm tra trạng thái JML và quyền theo RBAC/ABAC. Đây là **quản trị vòng đời và phân quyền**.
6. **Kiểm toán/đối soát:** chứng minh quyết định cấp/thu hồi quyền đã được phản ánh tại các hệ thống đích.

Nếu một lớp bị lỗi, không nên chữa bằng cách bỏ kiểm tra ở lớp khác.

## 3. Well-known URL: cách tạo địa chỉ OIDC discovery

Trong **OpenID Connect Discovery 1.0**, metadata được truy cập từ issuer bằng cách **nối hậu tố `/.well-known/openid-configuration` vào đường dẫn issuer** theo quy tắc của đặc tả.

| Issuer đã được chấp thuận | URL OIDC discovery |
| --- | --- |
| `https://id.example.invalid` | `https://id.example.invalid/.well-known/openid-configuration` |
| `https://id.example.invalid/workforce` | `https://id.example.invalid/workforce/.well-known/openid-configuration` |
| `https://id.example.invalid/tenant-a` | `https://id.example.invalid/tenant-a/.well-known/openid-configuration` |

**Lưu ý:** Các URL trên là **ví dụ minh họa**, không phải endpoint đang tồn tại. Không đoán issuer chỉ từ mẫu URL, hostname hoặc email domain; chọn issuer có thẩm quyền trước, rồi mới xây URL discovery.

### 3.1. Không nhầm quy tắc OIDC Discovery với RFC 8414

**OAuth 2.0 Authorization Server Metadata (RFC 8414)** dùng một mẫu well-known khác. Đặc biệt khi issuer có path, vị trí hậu tố well-known trong URL OAuth metadata **có thể khác** cách OIDC Discovery 1.0 đặt `openid-configuration`.

Ví dụ với issuer `https://id.example.invalid/workforce`:

~~~text
OIDC Discovery 1.0:
https://id.example.invalid/workforce/.well-known/openid-configuration

RFC 8414 OAuth Authorization Server Metadata:
https://id.example.invalid/.well-known/oauth-authorization-server/workforce
~~~

**Không tráo hai địa chỉ chỉ vì chúng đều là well-known metadata.** Một OP có thể cung cấp nhiều endpoint metadata theo khả năng, nhưng RP phải chọn **cơ chế và địa chỉ** đúng với giao thức/client đang dùng, kiểm tra issuer và không chấp nhận metadata của tenant sai.

### 3.2. Yêu cầu cơ bản khi tải metadata

- Dùng **HTTPS/TLS** theo mô hình tin cậy phù hợp, không cho phép HTTP không bảo vệ cho issuer OIDC thông thường.
- Giới hạn nguồn tải theo **issuer được cấu hình hoặc chọn từ tenant registry tin cậy**.
- Kiểm tra URL, host, redirect và chính sách truy cập mạng để tránh **Server-Side Request Forgery (SSRF)** từ input người dùng.
- Kiểm tra HTTP response, kiểu dữ liệu JSON, giới hạn kích thước/thời gian, lỗi parse và trường bắt buộc.
- Không chấp nhận metadata `issuer` khác issuer yêu cầu, kể cả khác tenant/path, scheme hoặc hostname.
- Không giả định mọi endpoint phải nằm cùng hostname; nếu OP công bố endpoint khác host, cần kiểm tra theo hợp đồng tin cậy và policy bảo mật của tổ chức.
- Có giới hạn cache, xử lý outage và quan sát sự thay đổi metadata.

**Đặc biệt với multi-tenant:** Không nên cho người dùng nhập `issuer=https://arbitrary.example/` rồi để backend tự truy vấn, coi bất kỳ JSON nào trả về là nguồn tin cậy. Thao tác đó có thể tạo cả **SSRF** lẫn **issuer mix-up/token confusion**.

## 4. Provider metadata gồm những gì?

Một tài liệu OIDC Discovery chứa các trường quy định bởi OpenID Connect Discovery 1.0, cùng thuộc tính tùy chọn hoặc extension của nhà cung cấp. RP cần xác định rõ trường nào **bắt buộc cho profile đang hỗ trợ**, trường nào dùng cho tính năng tùy chọn.

### 4.1. Những trường đặc biệt quan trọng

| Trường metadata | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| `issuer` | Định danh OP. | **Khớp chính xác** issuer RP đã chấp thuận; ID token `iss` cũng phải khớp. |
| `authorization_endpoint` | Nơi browser gửi authorization request. | URL hợp lệ, phù hợp HTTPS và policy trust. |
| `token_endpoint` | Nơi client đổi authorization code hoặc thực hiện grant được hỗ trợ. | Cần cho Authorization Code; kiểm tra client authentication và TLS. |
| `jwks_uri` | Địa chỉ bộ khóa JSON Web Key công khai. | Nguồn tin cậy, quản lý cache/rotation; chỉ dùng khóa phù hợp. |
| `response_types_supported` | Các `response_type` mà OP công bố. | Có `code` nếu RP dùng Authorization Code flow. |
| `subject_types_supported` | Các loại subject identifier hỗ trợ, như public/pairwise. | Hiểu thay đổi `sub` theo client/sector khi pairwise. |
| `id_token_signing_alg_values_supported` | Các thuật toán ký ID token OP hỗ trợ. | Giao với **allowlist thuật toán** của RP; không tự chấp nhận `none`. |
| `scopes_supported` | Những scope OP công bố hỗ trợ. | Chỉ là thông tin khả năng; không chứng minh client đã được cấp scope. |
| `claims_supported` | Những claim OP công bố có thể cung cấp. | Không bảo đảm mọi claim luôn có hoặc được trả cho mọi user. |
| `userinfo_endpoint` | Endpoint lấy claim về user khi tính năng được hỗ trợ. | Quyền scope/token phù hợp, đối chiếu `sub` theo yêu cầu OIDC. |
| `token_endpoint_auth_methods_supported` | Cách client xác thực tới token endpoint. | Dùng phương thức client đã đăng ký/được cho phép. |
| `code_challenge_methods_supported` | Các phương pháp PKCE OP công bố khi hỗ trợ metadata này. | Nếu dùng PKCE, ưu tiên `S256` theo profile bảo mật phù hợp. |
| `acr_values_supported` | Những giá trị Authentication Context Class có thể hỗ trợ. | Ngữ nghĩa do OP/policy định nghĩa; không coi chuỗi là bảo đảm nếu chưa đánh giá. |
| `end_session_endpoint` | Một endpoint logout có thể được công bố theo extension. | Không mặc định mọi OP hỗ trợ logout liên kết cùng cách. |

**Lưu ý về tính bắt buộc:** các trường như `issuer`, `authorization_endpoint`, `jwks_uri`, `response_types_supported`, `subject_types_supported`, `id_token_signing_alg_values_supported` là cốt lõi theo OIDC Discovery; yêu cầu với `token_endpoint` phụ thuộc luồng được hỗ trợ, và với **Authorization Code** chắc chắn phải có token endpoint dùng được. Không tự xem mọi trường trong bảng đều bắt buộc ở mọi provider hoặc mọi giao thức.

### 4.2. Ví dụ JSON metadata tối giản cho Authorization Code

~~~json
{
  "issuer": "https://login.example.invalid/workforce",
  "authorization_endpoint": "https://login.example.invalid/workforce/oauth2/authorize",
  "token_endpoint": "https://login.example.invalid/workforce/oauth2/token",
  "jwks_uri": "https://login.example.invalid/workforce/keys",
  "userinfo_endpoint": "https://login.example.invalid/workforce/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "claims_supported": ["sub", "iss", "aud", "exp", "iat", "name", "email"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "private_key_jwt"],
  "code_challenge_methods_supported": ["S256"]
}
~~~

Đây là **ví dụ giáo dục**, không phải metadata được lấy từ một IdP thực tế. Một provider có thể công bố nhiều thuật toán, grant, response type, endpoint, loại subject và extension khác. RP phải đánh giá **sự tương thích giữa metadata, client registration và security policy**, không chọn “phương thức yếu nhất để dễ đăng nhập”.

### 4.3. Metadata mô tả khả năng, không cấp quyền

- OP công bố `scopes_supported` chứa `email` **không có nghĩa** mọi RP được truy xuất email của mọi người.
- OP công bố `userinfo_endpoint` **không có nghĩa** user có quyền tới mọi API.
- OP công bố `response_types_supported` chứa `code` **không có nghĩa** client đã được đăng ký redirect URI đúng.
- OP công bố `claims_supported` chứa `groups` (nếu là extension) **không có nghĩa** mọi role ở ứng dụng tự được cấp qua claim.
- Có `jwks_uri` **không có nghĩa** mọi JWT sử dụng khóa tìm được đều có issuer/audience hợp lệ.

**Discovery ≠ registration ≠ authentication ≠ authorization.** Đây là cách phân biệt quan trọng nhất để tránh ứng dụng cấu hình “chạy được” nhưng thiếu kiểm soát.

## 5. JWKS URI và kiểm chứng chữ ký ID token

### 5.1. JWKS là gì?

**JSON Web Key Set (JWKS)** là tài liệu có thể chứa một hoặc nhiều JWK. Với OP ký ID token bằng thuật toán bất đối xứng, RP thường tải các **khóa công khai** từ `jwks_uri` và dùng chúng để kiểm tra chữ ký. Những thuộc tính JWK thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `kid` | Key ID, giúp chọn khóa phù hợp trong một key set; không phải định danh issuer. |
| `kty` | Loại khóa như RSA hoặc EC. |
| `use` | Mục đích sử dụng khóa, nếu được công bố (ví dụ `sig`). |
| `alg` | Thuật toán sử dụng dự kiến, nếu được công bố. |
| `n`, `e` | Thành phần khóa RSA công khai trong JWK phù hợp. |
| `crv`, `x`, `y` | Thành phần khóa EC công khai trong JWK phù hợp. |

Ví dụ JWKS **rút gọn để giải thích cấu trúc** (khóa không có kích thước hợp lệ, không dùng kiểm chứng thật):

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "illustrative-modulus-not-a-real-key",
      "e": "AQAB"
    }
  ]
}
~~~

**Không chép mẫu này vào production**. Hệ thống thực cần khóa hợp lệ do OP cung cấp, xác minh TLS/trust, tương thích thuật toán và cập nhật khi có rotation. Private key của OP **không** được công bố ở JWKS.

### 5.2. Chọn khóa đúng chưa đủ để chấp nhận token

Khi RP nhận ID token, cần kiểm tra theo OIDC Core và profile đang dùng, bao gồm ít nhất:

1. Token thuộc **loại dự kiến** (ID token) và được xử lý trong đúng luồng/đối tượng.
2. Chữ ký được xác minh bằng khóa có **nguồn gốc gắn với issuer đã tin cậy** và thuật toán được phép.
3. `iss` của token **khớp chính xác** issuer RP chọn cho giao dịch.
4. `aud` chứa **client ID** của RP; khi có nhiều audience, kiểm tra các quy tắc liên quan như `azp` khi áp dụng.
5. `exp` chưa hết hiệu lực; các trường thời gian khác như `iat` và `auth_time` được kiểm tra khi profile/chính sách yêu cầu.
6. `nonce` khớp nếu RP đã gửi nonce và profile yêu cầu kiểm chứng.
7. Subject `sub` được liên kết với đúng application account/identity theo nguồn dữ liệu có thẩm quyền.

**Lưu ý:** `kid` chỉ giúp tìm khóa trong một JWKS. Nếu hai issuer tình cờ có `kid` giống nhau, **không được lấy khóa của issuer khác**. Không tải một địa chỉ `jku`, `x5u` hoặc bất kỳ key URL nào từ JWT header do phía không tin cậy tự đưa ra, trừ khi có thiết kế và allowlist được kiểm soát nghiêm ngặt.

### 5.3. Khả năng xoay vòng khóa (key rotation)

OP có thể thêm khóa ký mới trước khi sử dụng, tiếp tục duy trì khóa cũ trong giai đoạn token cũ còn hiệu lực, rồi gỡ khóa cũ theo chính sách. RP cần:

- Cache JWKS có thời hạn, tránh fetch mỗi request gây tăng tải hoặc tạo đường DoS.
- Làm mới có kiểm soát khi xuất hiện `kid` chưa biết, có giới hạn tốc độ và tránh đồng thời fetch ồ ạt.
- Giữ ràng buộc **issuer → metadata → jwks_uri → JWKS** khi refresh.
- Không chấp nhận token thiếu chữ ký hợp lệ khi JWKS endpoint lỗi.
- Theo dõi trường hợp metadata/JWKS đổi bất thường, certificate/trust lỗi hoặc tất cả token bắt đầu bị từ chối.
- Kiểm thử rotation với **giai đoạn chồng lấn khóa** và cache thực tế của RP.

**Không nên khắc phục lỗi “unknown kid” bằng cách tắt kiểm tra chữ ký**. Cần điều tra JWKS URI, key ID, cache, issuer, thời gian rotation và kế hoạch phân phối khóa giữa OP và RP.

## 6. Khởi tạo OIDC Authorization Code sau discovery

Khi metadata và client configuration đã hợp lệ, RP có thể bắt đầu luồng OIDC qua `authorization_endpoint`. Với ứng dụng hiện đại, thông thường sử dụng **Authorization Code flow** và **PKCE** theo cấu hình bảo mật áp dụng.

~~~mermaid
flowchart TD
    A["Issuer/tenant được cấu hình tin cậy"] --> B["Tải và kiểm tra OIDC metadata"]
    B --> C["Kiểm tra authorization/token/JWKS và thuật toán cho phép"]
    C --> D["RP tạo state, nonce khi cần, PKCE challenge"]
    D --> E["Browser tới authorization_endpoint"]
    E --> F["IdP: account, MFA, conditional access"]
    F --> G["Redirect về redirect_uri đăng ký kèm code/state"]
    G --> H{"State và phiên ban đầu hợp lệ?"}
    H -->|Không| DENY["Từ chối, ghi audit"]
    H -->|Có| I["Đổi code tại token_endpoint + code_verifier"]
    I --> J{"ID token validation thành công?"}
    J -->|Không| DENY
    J -->|Có| K["Liên kết iss + sub tới identity/account"]
    K --> L["Kiểm tra JML state và RBAC/ABAC"]
    L --> M["Tạo session/cho truy cập theo quyền"]
~~~

### 6.1. Ví dụ request logic

~~~text
GET https://login.example.invalid/workforce/oauth2/authorize
  ?response_type=code
  &client_id=finance-portal
  &redirect_uri=https%3A%2F%2Ffinance.example.invalid%2Foidc%2Fcallback
  &scope=openid%20profile
  &state=<random-state-bound-to-login-transaction>
  &nonce=<nonce-for-id-token-binding>
  &code_challenge=<derived-from-code-verifier>
  &code_challenge_method=S256
~~~

Đây là minh họa tham số, **không phải URL chạy được**. RP phải quản lý `state`, `nonce` và `code_verifier` theo đúng phiên và profile; token endpoint/client authentication và redirect URI phải khớp dữ liệu **client đã đăng ký**. Endpoint discovery **không tạo ra client ID, client secret hoặc redirect URI thay cho tổ chức**.

### 6.2. Phân biệt từng loại token

| Đối tượng | Mục đích | Cảnh báo |
| --- | --- | --- |
| **ID token** | RP nhận kết quả định danh của OP. | Không dùng như access token gọi API; kiểm chứng theo OIDC. |
| **Access token** | Client gọi resource server theo scope/quyền được cấp. | Có thể là JWT hoặc opaque tùy triển khai; không áp dụng máy móc quy tắc ID token cho mọi access token. |
| **Refresh token** | Xin token mới theo grant/chính sách và điều kiện bảo vệ. | Có vòng đời và chính sách revocation riêng. |
| **RP session cookie** | Duy trì phiên ứng dụng sau login. | Có thể tồn tại sau khi nhóm/role thay đổi nếu không được đánh giá lại. |
| **SCIM provisioning token** | Connector quản trị User/Group tại target theo API bảo vệ. | Là credential kỹ thuật riêng, không phải ID token của nhân viên. |

Discovery không xác nhận liệu một access token dành cho API khác có thể sử dụng ở đây. **Resource server** phải áp dụng kiểm chứng token và authorization phù hợp với loại token/API, audience và issuer nó chấp nhận.

## 7. Hai bước discovery: chọn issuer và lấy metadata

Trong thực tế, người dùng thường nghe “OIDC discovery” cho hai vấn đề khác nhau:

### 7.1. Provider Configuration Discovery

RP **đã biết issuer** hoặc chọn issuer từ danh mục đáng tin. Nó dùng `/.well-known/openid-configuration` để biết các endpoint, thuật toán và khả năng. Đây là trọng tâm triển khai cho hầu hết ứng dụng doanh nghiệp: **Issuer đã tin cậy trước, metadata được tải sau.**

### 7.2. Issuer Discovery qua WebFinger trong mô hình hỗ trợ

OIDC Discovery cũng mô tả một cơ chế sử dụng **WebFinger** để tìm issuer từ một thông tin người dùng như `acct:an@example.invalid` khi mô hình, IdP và policy cho phép. Ví dụ response mô tả cấu trúc khái niệm:

~~~json
{
  "subject": "acct:an@example.invalid",
  "links": [
    {
      "rel": "http://openid.net/specs/connect/1.0/issuer",
      "href": "https://login.example.invalid/workforce"
    }
  ]
}
~~~

**WebFinger không phải bằng chứng người nhập identifier sở hữu account**, cũng không có nghĩa RP có thể tin mọi URL issuer được phát hiện. Việc chọn issuer phải được ràng buộc bởi **tenant allowlist, verified domain mapping, chính sách đối tác và giới hạn truy cập mạng**. Nếu nguồn discovery bị điều khiển bởi người ngoài hoặc trả một issuer lạ, không tự động chuyển sang trust issuer đó.

### 7.3. Home realm discovery và multi-tenant registry

Trong một hệ thống phục vụ nhiều doanh nghiệp, quá trình thường như sau:

~~~text
1. Xác định tenant được phép (ví dụ tenant ID từ cấu hình ứng dụng).
2. Chọn issuer đã đăng ký cho tenant đó.
3. Tải metadata OIDC của issuer.
4. Kiểm tra metadata.issuer === issuer đã chọn.
5. Dùng endpoints/keys tương ứng với issuer.
6. Tạo login transaction bound với tenant + issuer + client ID.
7. Khi callback: kiểm chứng state, iss, aud và client context.
8. Chỉ sau đó liên kết (iss, sub) với target account.
~~~

**Domain email được nhập trên màn hình đăng nhập là tín hiệu định tuyến, không phải tín hiệu xác thực.** Trong B2B/đa tenant, cần quy trình xác minh domain và quan hệ tổ chức; không tự coi bất kỳ email domain nào là một OP hợp lệ.

## 8. Issuer và subject: liên kết người dùng an toàn

### 8.1. Dùng `(iss, sub)` thay vì chỉ email

Trong OIDC, `sub` xác định subject **trong phạm vi issuer**. Một ứng dụng nên lưu account correlation với cặp **`(iss, sub)`** (hoặc ánh xạ tương đương có cùng ranh giới), không chỉ dựa trên email, họ tên hoặc mã nhân viên.

Ví dụ:

| Thông tin | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `iss` | `https://login.example.invalid/workforce` | OP/tenant đã xác thực. |
| `sub` | `sub-A8192` | Subject do OP định nghĩa trong phạm vi issuer. |
| IAM identity ID | `person-2048` | Bản ghi identity nội bộ của IAM/IGA. |
| Employee identifier | `004281` | Khóa nhân sự theo HRIS và phạm vi xác định. |
| Application account ID | `finance-user-882` | Account đích của Finance Portal. |
| SCIM User.id | `scim-user-342` | ID tài nguyên do SCIM service provider cấp. |

Các trường này có thể liên kết tới cùng một nhân viên nhưng **không tự đồng nghĩa**. Email có thể thay đổi; employee identifier có thể khác giữa lần tái tuyển hoặc pháp nhân; `sub` có thể khác khi người dùng tương tác với các RP khác nhau nếu provider sử dụng **pairwise subject**.

### 8.2. Public subject và pairwise subject

- **Public subject:** OP có thể sử dụng cùng `sub` cho một người ở những client thuộc cấu hình phù hợp.
- **Pairwise subject:** OP tạo các `sub` khác nhau theo cơ chế/sector của RP để giảm khả năng liên kết hoạt động người dùng giữa các RP.

Metadata `subject_types_supported` cho biết OP có khả năng hỗ trợ loại nào; **không xác định duy nhất `sub` sẽ có giá trị gì** cho một user cụ thể. Khi thay đổi client registration, issuer, sector hoặc chính sách pairwise, cần đánh giá tác động tới account linking trước khi triển khai.

**Không tự merge** hai subject chỉ vì cùng email. Nếu cần liên kết person-level xuyên ứng dụng, IAM phải dùng nguồn có thẩm quyền và bước kiểm chứng có kiểm soát, giữ audit trail.

## 9. OIDC discovery trong Joiner–Mover–Leaver

### 9.1. Joiner: OP đã phát hiện nhưng account có thể chưa tồn tại

Khi HRIS tạo hồ sơ người mới, IAM thực hiện proofing/enrollment và account provisioning theo policy. **Discovery có thể hoạt động hoàn hảo**, nhưng login vẫn lỗi vì:

- IdP account chưa được tạo hoặc chưa active.
- Người dùng chưa hoàn tất MFA.
- SSO client/redirect URI chưa được cấu hình đúng.
- Ứng dụng chưa nhận SCIM/API provisioning User.
- `(iss, sub)` chưa được ánh xạ tới account đích.
- Entitlement của ứng dụng chưa được phê duyệt.

Vì vậy, trong Joiner cần kiểm tra **metadata/trust**, **login flow**, **account binding** và **quyền** như các phần tách biệt. Không dùng cách tắt token validation hoặc tự gán role để khắc phục lỗi “user not found”.

### 9.2. Mover: issuer có thể giữ nguyên, entitlement thay đổi

Người chuyển từ Operations sang Finance thường vẫn có cùng OP và issuer, nhưng role/department/group ở HR/IdP/ứng dụng thay đổi:

1. HRIS gửi Mover event có hiệu lực.
2. IAM tính **desired access** theo RBAC/ABAC, assignment và ngoại lệ.
3. Provisioning/SCIM cập nhật nhóm/role ở ứng dụng.
4. RP tiếp tục dùng discovery của **issuer cũ** nếu danh tính không đổi OP.
5. Ứng dụng phải rà soát quyền truy cập cũ và session/token còn hiệu lực.

**OIDC discovery không “tự phát hiện người dùng đã đổi vai trò”.** Nó chỉ cập nhật metadata của OP. Việc cập nhật quyền cần dữ liệu nghiệp vụ, event JML, provisioning, policy evaluation và reconciliation.

### 9.3. Leaver: discovery vẫn thành công dù account bị khóa

Sau khi HR xác nhận Leaver, IdP có thể tiếp tục phục vụ cùng URL metadata và JWKS cho các khách hàng khác. Điều này **hoàn toàn bình thường**. RP không được diễn giải `openid-configuration` trả HTTP 200 là tài khoản của một nhân viên nghỉ việc vẫn được phép đăng nhập.

Quy trình Leaver cần:
- Disable/chặn account IdP đúng thời điểm.
- Thu hồi group/entitlement và account tại ứng dụng đích theo chính sách.
- Đánh giá local login, session, access/refresh token, API key, credential riêng.
- Kiểm chứng trạng thái thực tế ở target; không chỉ nhìn login denial tại IdP.
- Lưu bằng chứng và remediation owner cho target còn quyền tồn dư.

**Từ chối đăng nhập người đã nghỉ việc là kết quả mong đợi**, nhưng cần tiếp tục đóng những đường truy cập tồn dư.

### 9.4. Rehire và chuyển issuer

Nếu người dùng được tái tuyển, IAM phải xác minh person/employment history và quyết định có tái sử dụng account hay tạo account mới theo policy. Một trường hợp phức tạp hơn là **chuyển IdP/issuer** khi công ty hợp nhất hoặc chuyển tenant.

**Đổi issuer có thể làm thay đổi `(iss, sub)`**, ngay cả với cùng một người. Không tự ánh xạ subject mới với account cũ bằng email. Cần một kế hoạch migration có:
- Mapping từ nguồn nhân sự/identity đã xác minh.
- Quy tắc cấp mới và thu hồi account/subject ở OP cũ.
- Duy trì lịch sử audit và account bindings.
- Cập nhật client registration, redirect URI/trust/issuer và metadata cho RP.
- Kiểm tra session/token của issuer cũ còn hiệu lực theo chính sách.
- Đối soát entitlement, không khôi phục quyền không còn căn cứ.

## 10. IdP, SSO, SCIM, RBAC/ABAC và discovery phối hợp thế nào?

~~~mermaid
flowchart LR
    HR["HRIS/Contractor source"] --> IAM["IAM/IGA: JML + policies"]
    IAM --> IDP["IdP/OP: accounts, AuthN, MFA"]
    IAM --> SCIM["SCIM/API/manual provisioning"]
    SCIM --> APP["Application accounts, groups, roles"]
    RP["Ứng dụng / RP"] --> META["OIDC discovery metadata"]
    META --> IDP
    RP --> JWKS["jwks_uri + trusted public keys"]
    JWKS --> IDP
    RP --> LOGIN["OIDC AuthN flow"]
    LOGIN --> IDP
    LOGIN --> APP
    APP --> AUTHZ["Authorization: RBAC/ABAC"]
    AUTHZ --> AUDIT["Readback, access review, audit"]
    AUDIT --> IAM
~~~

Sơ đồ là khái niệm, không phải mô tả định tuyến mạng chính xác. Các giao tiếp có thể dùng nhiều connector, client và tenant riêng biệt.

| Phần | Giải quyết | Không giải quyết |
| --- | --- | --- |
| **OIDC Discovery** | OP công bố issuer, endpoint, algorithm và key location. | Không cấp quyền nghiệp vụ và không khóa Leaver. |
| **OIDC Authentication** | OP xác thực; RP kiểm chứng ID token/đăng nhập. | Không đảm bảo đã provision User ở mọi ứng dụng. |
| **SSO** | Người dùng dùng phiên xác thực tập trung ở các ứng dụng liên kết. | Không tự thu hồi session, token hoặc credential local ở mọi đích. |
| **SCIM** | Quản lý tài nguyên User/Group theo provider capability. | Không thay thế token validation hoặc chứng minh identity proofing. |
| **RBAC/ABAC** | Quyết định có cho phép hành động/tài nguyên theo role/thuộc tính/ngữ cảnh. | Không thay thế xác thực danh tính. |
| **Access review/reconciliation** | Kiểm tra quyền còn hợp lệ và trạng thái thực tế khớp policy. | Không tự sửa trust/metadata nếu chưa có quy trình thay đổi. |

### 10.1. Tài khoản dịch vụ và workload

Một **workload identity/service account** có thể dùng OAuth 2.0 client credentials, private key JWT, mTLS hoặc cơ chế workload federation; đó **không mặc nhiên là luồng xác thực người dùng OIDC với ID token**. Authorization server có thể công bố OAuth metadata, nhưng không vì thế kết luận mỗi service account có `sub` người dùng hoặc cần SSO portal.

Với non-human identity:
- Có workload owner, mục đích, quyền, secret/certificate và trust binding rõ ràng.
- Chọn đúng authorization server/issuer và audience theo hợp đồng API.
- Kiểm chứng access token đúng loại và chính sách resource server.
- Quản lý rotation/revocation và deprovisioning theo vòng đời workload.
- Khi nhân viên owner Mover/Leaver, bàn giao ownership và thu hồi khả năng quản trị cá nhân; không tự xóa credential workload đang cần cho dịch vụ.

## 11. Bảo mật discovery: những lỗi nguy hiểm dễ bị bỏ sót

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **SSRF từ issuer URL tùy ý** | Backend fetch metadata từ URL do người dùng cung cấp, có thể trỏ vào mạng nội bộ. | Issuer allowlist/tenant registry, kiểm soát mạng và redirect, giới hạn host/scheme. |
| **Issuer mix-up** | RP lấy metadata/token từ tenant khác nhưng chấp nhận như issuer mong đợi. | So khớp chính xác issuer metadata và ID token `iss`, bind login transaction với tenant. |
| **Algorithm confusion** | RP chấp nhận thuật toán do token tự khai hoặc `none` trái policy. | Allowlist algorithm, xác minh JWS đúng key type/policy, không tùy tiện hạ bảo đảm. |
| **JWKS trust confusion** | Dùng `kid` mà không ràng buộc issuer, hoặc tải `jku` từ JWT header. | Mỗi issuer có tập khóa tin cậy riêng, chỉ tải từ JWKS URI đã được kiểm soát. |
| **Untrusted metadata redirect** | Well-known endpoint chuyển hướng tới nơi chưa được đánh giá. | Kiểm soát redirect/TLS/domain, không để đổi trust âm thầm. |
| **Cấu hình endpoint bị thay đổi** | OP hoặc thiết lập bị can thiệp, metadata trỏ tới token endpoint lạ. | Giám sát thay đổi, owner approval, policy đối với endpoint khác miền. |
| **Stale JWKS/cache** | Rotation khóa khiến RP từ chối token mới hoặc giữ khóa cũ quá lâu. | TTL/refresh có giới hạn, overlap rotation, fallback an toàn. |
| **Account linking bằng email** | RP tự hợp nhất tài khoản có cùng email từ issuer khác. | Bind bằng `(iss, sub)`; identity linking theo nguồn xác minh. |
| **Metadata bị lạm dụng như cấp quyền** | RP thấy scope/claim hỗ trợ rồi tự cấp role. | Phân biệt metadata, client grants và RBAC/ABAC ở ứng dụng. |
| **Không xử lý outage an toàn** | Khi endpoint lỗi, app bỏ chữ ký/issuer validation để duy trì login. | Fail-safe, last-known-good có thời hạn/phạm vi khi được phê duyệt; không fail-open. |
| **Secret/token trong debug log** | Ghi toàn bộ OAuth response/header/credential. | Log reason code/correlation ID, redaction và retention thích hợp. |

### 11.1. “Có HTTPS” không đủ bảo đảm tin cậy

HTTPS giúp bảo vệ kênh và xác minh danh tính máy chủ theo cấu hình TLS, nhưng **bất kỳ website nào có HTTPS hợp lệ cũng có thể công bố JSON**. RP chỉ nên tin metadata khi issuer **đã được chính sách cho phép** và metadata đáp ứng yêu cầu kiểm tra.

Nếu ứng dụng hỗ trợ nhiều tổ chức, sử dụng tenant registry hoặc cơ chế discovery có kiểm soát; không bật chế độ “nhận mọi issuer với cert hợp lệ”.

### 11.2. Không dùng metadata để thay đổi client trust tự động vô hạn

OIDC discovery có thể tự động hóa **phát hiện endpoints** hoặc **xoay vòng khóa công khai**. Nhưng thay đổi root issuer, client registration, redirect URI hoặc chính sách thuật toán có thể cần quản trị/phê duyệt theo mức độ rủi ro. Việc OP công bố một thuật toán mới không có nghĩa RP phải lập tức chấp nhận nó.

## 12. Cache, outage và rotation: vận hành discovery bền vững

### 12.1. Metadata cache và JWKS cache là hai phần khác nhau

| Cache | Nội dung | Lý do tồn tại | Rủi ro |
| --- | --- | --- | --- |
| **Provider metadata cache** | Issuer, endpoint URL, khả năng, thuật toán công bố. | Tránh gọi well-known ở mọi login và giảm phụ thuộc mạng. | Metadata cũ khiến redirect/token endpoint sai khi cấu hình thay đổi. |
| **JWKS cache** | Khóa công khai của OP. | Kiểm chứng token nhanh và giảm tải JWKS endpoint. | Unknown `kid` trong rotation hoặc chấp nhận khóa không còn theo chính sách. |
| **Session/token cache** | Phiên và thông tin token theo kiến trúc. | Duy trì đăng nhập, hiệu năng. | Session có thể sống sau thay đổi role/Leaver nếu không có revocation policy. |

**Không trộn logic:** refresh JWKS có thể giải quyết unknown `kid`, nhưng không sửa account chưa provision; làm mới metadata có thể phát hiện endpoint mới, nhưng không tự khóa session người nghỉ việc.

### 12.2. Khi provider metadata không khả dụng

Hệ thống có thể gặp timeout, lỗi TLS/DNS, 5xx hoặc JSON bị hỏng. Cách phản ứng tùy chính sách và mức độ rủi ro:

1. **Không thay issuer** sang một provider lạ để tiếp tục login.
2. **Không tắt chữ ký, audience hoặc issuer validation**.
3. Nếu thiết kế cho phép, dùng **last-known-good metadata/JWKS** đã được xác minh trong **phạm vi và thời hạn kiểm soát**, không vô hạn.
4. Nếu thiếu thông tin tin cậy cần thiết, **từ chối luồng mới an toàn** hoặc hiển thị lỗi dịch vụ, tránh cho phép đăng nhập “không xác thực”.
5. Cảnh báo operator, ghi correlation ID, kiểm tra dependency và certificate/network.
6. Sau khi phục hồi, refresh có kiểm soát, kiểm tra thay đổi và chạy smoke test phù hợp.

Mục tiêu là cân bằng **availability** với **security assurance**, không để outage biến thành đường bypass token validation.

### 12.3. Khi provider xoay vòng signing key

Ví dụ trình tự đáng mong đợi:

~~~text
T0  OP công bố khóa K_old trong JWKS và dùng ký ID token.
T1  OP thêm K_new vào JWKS (giữ K_old trong giai đoạn chồng lấn).
T2  OP bắt đầu ký ID token mới bằng K_new.
T3  RP gặp kid mới -> refresh JWKS có kiểm soát -> xác minh bằng K_new.
T4  Token cũ còn hiệu lực có thể tiếp tục xác minh với K_old theo policy.
T5  Sau giai đoạn phù hợp, OP loại K_old và RP làm mới cache.
~~~

Đây là **kịch bản tham khảo**, không phải lịch rotation bắt buộc của mọi provider. Nếu OP loại K_old quá sớm hoặc RP cache K_old quá lâu, việc xác thực có thể gặp gián đoạn. Cần phối hợp cấu hình TTL, thời lượng token, quy trình thay đổi và quan sát `kid`/verification error.

## 13. Pseudocode triển khai RP discovery an toàn

Pseudocode dưới đây mô tả cách **khởi tạo cấu hình** và **kiểm chứng ID token**; không phải mã production hoặc lời khuyên tự viết crypto library. Trong thực tế, nên dùng thư viện OIDC đã được kiểm thử và duy trì.

~~~text
function initializeTrustedProvider(tenantId):
    issuer = trustedTenantRegistry.lookupIssuer(tenantId)
    require issuer is configured and HTTPS
    require issuer has no query or fragment

    discoveryUri = oidcDiscoveryUriForIssuer(issuer)
    metadata = fetchJsonWithLimitsAndTrustedNetworkPolicy(discoveryUri)
    require metadata.issuer == issuer

    require validHttpsEndpoint(metadata.authorization_endpoint)
    require validHttpsEndpoint(metadata.token_endpoint)
    require validHttpsEndpoint(metadata.jwks_uri)
    require "code" in metadata.response_types_supported

    allowedAlgorithms = intersection(
        metadata.id_token_signing_alg_values_supported,
        applicationSecurityPolicy.allowedIdTokenAlgorithms
    )
    require allowedAlgorithms is not empty

    keys = loadJwksFromTrustedUri(metadata.jwks_uri)
    cacheProviderBoundToIssuer(tenantId, issuer, metadata, keys, allowedAlgorithms)
    return READY

function validateIdToken(tenantId, originalLoginTransaction, idToken):
    provider = loadTrustedProvider(tenantId)
    require originalLoginTransaction.issuer == provider.issuer
    require originalLoginTransaction.clientId == configuredClientId(tenantId)

    verifiedToken = oidcLibrary.verifySignatureAndClaims(
        idToken,
        allowedAlgorithms = provider.allowedAlgorithms,
        trustedKeys = provider.jwks,
        expectedIssuer = provider.issuer,
        expectedAudience = configuredClientId(tenantId),
        expectedNonce = originalLoginTransaction.nonceIfUsed,
        timePolicy = applicationSecurityPolicy.tokenTimeChecks
    )
    require verifiedToken is valid
    require verifiedToken.subject is present

    binding = lookupAccountByIssuerAndSub(provider.issuer, verifiedToken.sub)
    require binding is verified and belongsToExpectedTenant(tenantId)
    require currentLifecycleStateAllowsAccess(binding.identity)

    return establishApplicationSessionSubjectToAuthorization(binding)
~~~

Các bước production còn cần: lưu `state`/PKCE an toàn; xác thực client tại token endpoint theo profile; kiểm tra `azp`, `auth_time` và các claim khác khi phù hợp; chống replay; quản lý cache/key rotation/concurrency; xử lý lỗi về network; phân quyền từng request; bảo vệ session. **Không dùng một hàm tự so chữ ký minh họa để thay OIDC library chuẩn**.

### 13.1. Tập hợp bất biến cần duy trì

- **Trust invariant:** `metadata.issuer === configuredIssuer`.
- **Token invariant:** `token.iss === configuredIssuer` và `token.aud` dành cho client đang xử lý.
- **Key invariant:** khóa xác minh thuộc **provider đã tin cậy** và thuật toán được RP cho phép.
- **Account invariant:** `(iss, sub)` ánh xạ đến đúng target identity/account đã được xác minh.
- **Lifecycle invariant:** trạng thái nhân sự/account và thời điểm hiệu lực cho phép truy cập hiện tại.
- **Authorization invariant:** quyền với tài nguyên được kiểm tra riêng, không chỉ dựa trên login success.

## 14. Troubleshooting: đọc lỗi đúng lớp

| Dấu hiệu | Nguyên nhân khả dĩ | Kiểm tra đúng hướng |
| --- | --- | --- |
| `404` khi gọi well-known | Dùng sai path, provider không hỗ trợ OIDC Discovery ở URL đó, issuer sai. | So sánh issuer đã đăng ký, quy tắc tạo URL và tài liệu cấu hình OP. |
| Metadata có `issuer` khác | Chọn nhầm tenant/path, redirect hoặc trust config sai. | Từ chối; xác minh tenant registry và issuer, không “chấp nhận gần đúng”. |
| Metadata parse lỗi | Response HTML/proxy, JSON hỏng, service đang lỗi. | HTTP status, content type, proxy/routing, giới hạn parse và log. |
| Thiếu `authorization_endpoint`/`jwks_uri` | Metadata không đúng profile hoặc provider công bố thiếu. | Kiểm tra hợp đồng OIDC và cấu hình nguồn, không bịa URL. |
| Không có `code` trong response types | Provider/profile không hỗ trợ flow đang dùng. | Đánh giá khả năng và chọn phương án được phép, không tắt bảo vệ. |
| `unknown kid` | Key rotation, JWKS cache cũ hoặc dùng sai issuer. | Refresh có giới hạn, kiểm tra `jwks_uri` và signing key. |
| `invalid signature` | Sai khóa, sai thuật toán, token không từ OP mong đợi. | Kiểm chứng đúng issuer/key, không bỏ signature validation. |
| `invalid issuer` | ID token thuộc tenant khác hoặc OP đã đổi issuer. | Chặn token, điều tra registry/migration và thay đổi trust. |
| `invalid audience` | Token dành cho client khác. | Kiểm tra client ID và luồng, không tái dùng ID token của ứng dụng khác. |
| `state/nonce mismatch` | Callback không gắn với login transaction, session/cookie lỗi hoặc tấn công. | Kiểm tra state, nonce, cookie/session, không bỏ anti-CSRF. |
| IdP login thành công, ứng dụng báo user not found | Account chưa provision, sai `(iss,sub)` mapping, SCIM lỗi. | IAM identity binding, target account, provisioning readback. |
| OIDC login thành công nhưng API 403 | Thiếu scope/entitlement hoặc RBAC/ABAC từ chối. | Điều tra AuthZ ở resource server; không reset credential. |
| Leaver vẫn mở được app qua session cũ | App session/token chưa thu hồi hoặc local account còn. | Deprovisioning ở target, session/credential review, reconciliation. |

### 14.1. Cách điều tra theo correlation ID

Một luồng đăng nhập có thể đi qua RP → tenant registry → discovery cache → authorization endpoint → token endpoint → JWKS → account mapping → AuthZ. Nên lưu **request/correlation ID, issuerRef, clientId, metadata version/refresh time, `kid`, outcome và target account ID**, nhưng không ghi access token, refresh token, client secret, private key hoặc full ID token vào log.

Một correlation ID **không tự động được mọi hệ thống chia sẻ**; khi cần, vận hành phải nối event qua request ID, timestamp, client ID và account/identity reference theo chính sách bảo vệ dữ liệu.

## 15. Kiểm toán, giám sát và trách nhiệm giải trình

### 15.1. Bằng chứng cần lưu

| Sự kiện | Nội dung audit phù hợp | Câu hỏi được giải đáp |
| --- | --- | --- |
| **Issuer được đăng ký/thay đổi** | Tenant, issuer trước/sau, owner, approval, thời điểm. | Ai cho phép RP tin một IdP? |
| **Discovery fetch/cache update** | IssuerRef, well-known URL, status, metadata fingerprint/version, thời gian. | RP đang dựa vào cấu hình nào? |
| **Endpoint/algorithm change** | Giá trị trước/sau được kiểm soát, policy outcome, reviewer. | Vì sao RP đổi nguồn token/JWKS hoặc khả năng ký? |
| **JWKS refresh/rotation** | IssuerRef, `kid`, kết quả tải/kiểm chứng, cache state. | Token lỗi vì key rotation hay vì trust? |
| **OIDC login outcome** | Correlation ID, client, issuer, category lý do, subject ref khi có. | Luồng có hoàn tất AuthN/validation không? |
| **Account binding** | IAM identity ID, `(iss,sub)`, target account ID, nguồn xác minh. | Ai đang truy cập account nào? |
| **JML change and readback** | HR event, effective time, SCIM/API job, actual entitlement. | Vai trò/quan hệ thay đổi đã được phản ánh ở target chưa? |

**Bảo vệ log:** metadata/JWKS công khai không biến mọi trace OAuth thành thông tin công khai. Token, secret, mã khôi phục, giấy tờ identity proofing và dữ liệu riêng tư không nên đưa nguyên bản vào log. Retention và quyền truy cập log cần tuân theo chính sách áp dụng.

### 15.2. Một số chỉ số vận hành

| Chỉ số | Gợi ý định nghĩa | Không nên suy luận |
| --- | --- | --- |
| **Discovery success rate** | Lượt fetch metadata hợp lệ ÷ tổng fetch trong phạm vi. | Không bằng tỷ lệ login success. |
| **Issuer mismatch count** | Số lần metadata/token issuer không khớp cấu hình tin cậy. | Không phải mọi mismatch đều là attack; có thể cấu hình sai nhưng luôn cần xem xét. |
| **JWKS refresh failure** | Tỷ lệ refresh JWKS lỗi hoặc quá hạn. | Không cho phép bỏ signature validation khi tăng cao. |
| **Unknown-kid recovery time** | Thời gian từ phát hiện key mới đến lúc RP kiểm chứng thành công theo policy. | Không có nghĩa token của issuer khác sẽ được chấp nhận. |
| **Federation login error rate** | Lỗi token/callback/config ÷ luồng OIDC trong phạm vi. | Không gộp AuthZ 403 với AuthN failure. |
| **Provisioning-related login failure** | Login đã xác thực nhưng app account/mapping chưa sẵn sàng. | Sửa bằng reset mật khẩu không giải quyết SCIM lỗi. |
| **JML residual-access closure** | Các đường truy cập phải chặn đã được xác minh bị chặn đúng hạn. | Metadata vẫn hoạt động không có nghĩa Leaver vẫn được phép. |
| **Unreviewed issuer change** | Thay đổi trust/endpoint/algorithm thiếu owner hoặc approval theo policy. | Không chỉ là lỗi vận hành; có thể là rủi ro trust boundary. |

## 16. Tình huống xuyên suốt: hai tenant và một lần đổi vai trò

**Bối cảnh:** Công ty vận hành Finance Portal và một IdP đa tenant:
- **Tenant A** dùng issuer `https://login.example.invalid/tenant-a`.
- **Tenant B** dùng issuer `https://login.example.invalid/tenant-b`.
- Finance Portal hỗ trợ OIDC Authorization Code, PKCE, IdP SSO và nhận thông tin account từ IAM/SCIM.
- Nhân viên **Mai** thuộc Tenant A, IAM identity `person-2048`, target account `finance-user-882`.

### 16.1. Joiner: login đã đúng issuer nhưng thiếu account

1. IAM chọn issuer Tenant A từ cấu hình nhân sự/tenant registry.
2. RP tải `/tenant-a/.well-known/openid-configuration`, kiểm tra `issuer` và tải JWKS.
3. Mai xác thực qua IdP và hoàn tất MFA.
4. RP kiểm chứng ID token với `iss=.../tenant-a`, audience và chữ ký đúng.
5. Finance Portal vẫn báo **“user not provisioned”** do một tác vụ SCIM tạo User chưa thành công.

**Chẩn đoán:** OIDC discovery và AuthN hoạt động; lỗi nằm ở **SCIM/account binding**. IAM cần sửa provisioning, xác nhận User tại target và quyền được duyệt. Không tắt chữ ký, không đổi issuer sang B và không tự cấp role ngoài chính sách.

### 16.2. Mover: đổi vai trò nhưng issuer không đổi

Mai chuyển từ kế toán tổng hợp sang kiểm toán. Tenant A và OP không thay đổi, vì vậy **OIDC discovery metadata không nhất thiết đổi**. Tuy nhiên:
- IAM phải gỡ entitlement kế toán cũ.
- Cấp quyền kiểm toán mới theo RBAC/ABAC và phê duyệt/SoD.
- Reconciliation phải tìm quyền trực tiếp còn tồn dư ở ứng dụng.
- Session/token đã phát hành cần được đánh giá theo chính sách khi vai trò nhạy cảm thay đổi.

Nếu Mai vẫn dùng bookmark để vào báo cáo kế toán cũ, đó là vấn đề **authorization và residual access**, không phải lỗi discovery.

### 16.3. Leaver: OP vẫn công bố metadata

Mai nghỉ việc, IdP account bị disable. URL `openid-configuration` Tenant A vẫn truy cập được vì phục vụ **toàn tenant**. Từ điều này không thể suy ra tài khoản của Mai còn active. IAM phải:
1. Chặn AuthN đúng thời điểm.
2. Deprovision app group/role và local account.
3. Kiểm tra session, token và đường API khác.
4. Readback actual state, lưu bằng chứng và owner của lỗi còn lại.

### 16.4. Sự cố sai issuer trong multi-tenant

Sau một bản thay đổi, RP tải metadata Tenant B nhưng login transaction vẫn được gắn Tenant A. Nếu RP chỉ kiểm tra hostname và chấp nhận token `iss=.../tenant-b`, một user ở Tenant B có thể bị **liên kết sai trust/account** với Tenant A.

Kiểm soát bắt buộc:
- Bind **tenant → issuer → metadata → key set**.
- Từ chối metadata issuer không khớp.
- Kiểm tra ID token `iss`, `aud`, chữ ký và request context.
- Liên kết subject bằng **`(iss,sub)`**, không dùng email làm căn cứ duy nhất.
- Ghi audit cấu hình, triển khai và sự kiện mismatch.

### 16.5. Một event audit minh họa

~~~json
{
  "eventId": "oidc-discovery-audit-901",
  "timestamp": "2026-11-23T09:45:00+07:00",
  "tenant": "tenant-a",
  "issuerExpected": "https://login.example.invalid/tenant-a",
  "discovery": {
    "uri": "https://login.example.invalid/tenant-a/.well-known/openid-configuration",
    "httpResult": 200,
    "issuerObserved": "https://login.example.invalid/tenant-a",
    "validation": "PASSED",
    "jwksRefresh": "PASSED"
  },
  "relyingParty": {
    "clientId": "finance-portal",
    "policyRef": "oidc-rp-security-v4"
  },
  "lifecycleContext": {
    "identityRef": "person-2048",
    "accountBindingRef": "finance-user-882"
  },
  "verification": {
    "status": "CONFIGURATION_TRUST_VERIFIED",
    "applicationEntitlementState": "CHECKED_SEPARATELY"
  }
}
~~~

Đây là **schema minh họa**. Một sự kiện cấu hình discovery thành công không đồng nghĩa một login cụ thể đã thành công hoặc tài khoản có đủ quyền. Trong audit thực tế, nên tách **metadata verification** khỏi **authentication event** và **entitlement reconciliation**.

## 17. Các sai lầm phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tự đoán issuer từ hostname/email. | Chọn sai OP/tenant, truy cập nhầm trust boundary. | Tenant registry và verified issuer. |
| Fetch well-known ở URL tùy ý từ input client. | SSRF hoặc nhận metadata của bên không tin cậy. | Allowlist issuer, kiểm soát request và redirects. |
| Nhầm OIDC path rule với RFC 8414. | 404 hoặc lấy metadata khác profile. | Tạo URI theo đúng đặc tả dùng và issuer path. |
| Chỉ kiểm tra HTTPS, bỏ so khớp `issuer`. | Có thể chấp nhận metadata của provider/tenant khác. | Exact issuer validation. |
| Dùng khóa JWKS của issuer khác vì cùng `kid`. | Chấp nhận hoặc từ chối token sai. | Ràng buộc JWKS theo issuer, kiểm tra alg/key. |
| Chấp nhận bất kỳ `alg` token tự khai. | Nguy cơ algorithm confusion hoặc hạ chính sách. | Explicit allowlist, signature verification đúng profile. |
| Gặp unknown `kid` liền bỏ validation. | Mở nguy cơ chấp nhận token giả. | Refresh JWKS an toàn, điều tra rotation. |
| Coi `claims_supported` là quyền/claim luôn được cấp. | Mapping quyền sai hoặc lộ dữ liệu. | Phân biệt metadata, scope, consent, RBAC/ABAC. |
| Coi WebFinger response là bằng chứng danh tính. | Liên kết account sai người hoặc trust issuer tùy ý. | Discovery có kiểm soát, identity proofing và mapping được xác minh. |
| Ánh xạ account bằng email thay vì `(iss,sub)`. | Account takeover/mismatch khi đổi email hoặc issuer. | Trusted subject binding và audit. |
| Coi discovery thành công là Leaver đã bị khóa. | Không phát hiện session/local token còn hiệu lực. | JML deprovisioning và readback target riêng. |
| Coi OIDC metadata là công cụ tạo SCIM account. | User login nhưng app báo not provisioned. | Triển khai provisioning đúng và reconcile. |
| Service account dùng ID token của người làm credential API. | Sai loại token, phá vỡ workload lifecycle. | OAuth/workload identity flow và permission riêng. |

## 18. Checklist triển khai và câu hỏi thực hành

### 18.1. Checklist trước khi đưa một RP vào production

- [ ] Issuer được chọn từ **nguồn cấu hình/tenant registry tin cậy**, không từ URL tùy ý.
- [ ] URL `/.well-known/openid-configuration` được tạo theo **OIDC Discovery 1.0** và issuer path thực tế.
- [ ] Metadata tải bằng HTTPS với giới hạn network/size/timeout; xử lý redirect an toàn.
- [ ] `metadata.issuer` được so **chính xác** với issuer đã cho phép.
- [ ] `authorization_endpoint`, `token_endpoint`, `jwks_uri` và các trường cần cho flow được kiểm tra.
- [ ] `response_types_supported` có kiểu RP dùng; thuật toán nằm trong policy allowlist.
- [ ] JWKS được tải/cached riêng theo issuer, hỗ trợ key rotation có kiểm soát.
- [ ] RP kiểm chứng ID token: signature, issuer, audience, thời gian, nonce/azp khi áp dụng.
- [ ] Authorization Code flow có state/PKCE và client registration/redirect URI phù hợp.
- [ ] Không coi discovery, client registration, SCIM provisioning và RBAC/ABAC là một việc.
- [ ] Liên kết application account với **`(iss,sub)`** hoặc mapping đã xác minh cùng ngữ nghĩa.
- [ ] Hỗ trợ nhiều issuer/tenant không gây mix-up hoặc tin token sai tổ chức.
- [ ] Có chính sách cache/last-known-good/outage không bỏ kiểm tra token.
- [ ] Joiner tạo/liên kết account đúng lúc; Mover gỡ quyền cũ; Leaver chặn access paths cần thiết.
- [ ] Audit có owner, issuer, phiên bản cấu hình/khóa, correlation và outcome; không log secret/full token.
- [ ] Đã kiểm thử key rotation, mismatch issuer, invalid signature/audience, SCIM failure và Leaver session.

### 18.2. Tình huống A — Well-known URL của issuer có path

RP tin issuer `https://id.example.invalid/office`, nhưng operator cấu hình metadata URL `https://id.example.invalid/.well-known/openid-configuration/office`. Hãy xác định vì sao có thể sai với OIDC Discovery 1.0, viết lại địa chỉ đúng, phân biệt quy tắc RFC 8414 và mô tả cách xác minh `issuer` trong JSON.

### 18.3. Tình huống B — Multi-tenant issuer mix-up

Ứng dụng phục vụ Tenant A và B. Cả hai OP đều dùng hostname `login.example.invalid` nhưng issuer path khác nhau. Có được chấp nhận ID token của B cho login request thuộc A nếu chữ ký kiểm chứng được và email trùng không? Hãy mô tả các bất biến **issuer, audience, key set và `(iss,sub)`**.

### 18.4. Tình huống C — Key rotation gây lỗi đăng nhập

IdP vừa chuyển sang `kid` mới. RP báo “unknown key ID”. Hãy trình bày quy trình kiểm tra JWKS, cache TTL, issuer, alg policy, retry có giới hạn và cách tránh DoS/không bỏ signature validation.

### 18.5. Tình huống D — OIDC login thành công nhưng thiếu tài khoản ứng dụng

Nhân viên Joiner hoàn tất MFA, RP xác minh ID token thành công, nhưng Finance Portal báo “user not found”. Vì sao sửa URL well-known không giải quyết được? Hãy xác định dữ liệu IAM identity, `(iss,sub)` mapping, SCIM task và quyền cần đọc lại.

### 18.6. Tình huống E — Leaver và token còn sống

IdP khóa account của nhân viên nghỉ việc, nhưng một API còn chấp nhận access token phát hành trước đó. Hãy phân biệt **OIDC discovery/JWKS** với **token authorization/enforcement**, xác định cách đánh giá session/token revocation và bằng chứng hoàn tất offboarding.

### 18.7. Tình huống F — WebFinger từ email tự khai

Một client nhận email `user@unknown.example.invalid`, tra WebFinger thấy một issuer chưa đăng ký và muốn tự động tin cậy provider đó. Phân tích rủi ro SSRF, issuer trust, account linking và thiết kế một policy chọn OP an toàn.

**Điểm cần ghi nhớ:** **OIDC discovery cho RP biết OP đã được chọn công bố cấu hình gì**, thông qua metadata `/.well-known/openid-configuration` và liên kết tới JWKS. Bảo mật đến từ **chọn issuer có thẩm quyền, kiểm tra chính xác metadata/ID token, ràng buộc issuer–key–client–subject, quản lý cache/rotation và từ chối cấu hình không đáng tin**. Trong vòng đời IAM, discovery phối hợp nhưng **không thay thế** identity proofing, SSO AuthN, SCIM account provisioning, RBAC/ABAC, rà soát và thu hồi quyền theo Joiner–Mover–Leaver.

