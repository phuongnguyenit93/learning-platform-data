# Credential rotation trong giao tiếp service-to-service

> **Chương:** Service to service  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Vòng đời token bảo mật, JWT, opaque token, access token, refresh token, OAuth 2.0/OIDC, claims, scope, audience, lưu trữ, thu hồi và chống đánh cắp hoặc phát lại credential.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **credential rotation** và lý do một hệ thống service-to-service cần thay khóa/secret mà vẫn duy trì dịch vụ.
2. Phân biệt rotation của **OAuth client secret, API key, khóa ký JWT, private_key_jwt, chứng chỉ mTLS, access token và refresh token**.
3. Thiết kế quy trình cấp mới, phân phối, chuyển đổi, quan sát và thu hồi phiên bản cũ theo thời gian cụ thể.
4. Kiểm tra **issuer, audience, scope, claims, thời hạn** và chính sách resource server sau rotation.
5. Phân tích trường hợp credential bị lộ, xử lý token còn tồn tại và chống sử dụng lại token đã bị đánh cắp.
6. Áp dụng các nguyên tắc với Java/Spring Boot, secret manager, nhiều replica và hạ tầng proxy/service mesh.

## 1. Credential rotation là gì?

**Credential** là bằng chứng được dùng để xác thực một bên hoặc thiết lập một quan hệ tin cậy. Nó có thể là một chuỗi bí mật, private key, chứng chỉ, hoặc credential tạm thời như access token. **Credential rotation** là quá trình đưa credential mới vào sử dụng và kết thúc việc sử dụng credential cũ theo chính sách.

Ví dụ, Payment Service dùng **client ID + client secret** để lấy **access token** từ Authorization Server qua OAuth 2.0 **client_credentials grant**, rồi gọi Orders API. Nếu client secret bị lộ trong log hoặc cấu hình, người có secret có thể thử xin access token. Rotation thay v1 bằng v2 giúp giới hạn thời gian secret cũ còn sử dụng được.

~~~mermaid
flowchart LR
    S["Secret Manager<br/>client secret v1 → v2"] --> P["Payment Service"]
    P -->|"OAuth client authentication<br/>client_credentials"| AS["Authorization Server"]
    AS -->|"Access token: aud=orders-api"| P
    P -->|"Bearer access token"| O["Orders API"]
    O --> V["Token validation<br/>Scope + resource authorization"]
~~~

Một yêu cầu quan trọng: thay **client secret** không đồng nghĩa đã thay **access token** đang lưu trong cache, và thay **khóa ký JWT** lại là một nghiệp vụ khác. Do đó phải xác định rõ **credential nào đang được xoay**, **ai phát hành**, **ai sử dụng**, **ai xác minh** và **khi nào phiên bản cũ hết hiệu lực**.

### Mục đích của rotation

- Giảm thời gian một secret/key có thể bị lạm dụng nếu bị sao chép hoặc đánh cắp.
- Tự động làm mới credential ngắn hạn và tránh sự cố hết hạn bất ngờ.
- Thay khóa/chứng chỉ khi thay chính sách mật mã, môi trường hoặc CA.
- Thay thế credential của workload sau thay đổi quyền, chuyển service account hoặc xử lý sự cố.
- Đảm bảo mô hình zero-trust giữa các service vẫn xác thực đúng danh tính từng workload.

Rotation là một phần của vòng đời credential; nó không thể thay thế quyền tối thiểu, quản lý secret, kiểm tra token và phân quyền tại resource server.

## 2. Phân biệt các loại credential và cách rotation

| Đối tượng | Ai phát hành/giữ? | Bên xác minh | Cách thay đổi thường gặp |
|---|---|---|---|
| **OAuth client secret** | Authorization Server quản lý; OAuth client giữ bí mật | Token endpoint | Cấp secret mới, đổi client đang sử dụng, vô hiệu hóa secret cũ |
| **API key** | API provider/gateway cấp; service gọi API lưu key | API gateway hoặc backend | Tạo key mới, chuyển request, revoke key cũ |
| **private_key_jwt** | OAuth client giữ private key, đăng ký public key | Authorization Server | Đăng ký public key v2, ký assertion bằng private key v2, loại key v1 |
| **Khóa ký JWT access token** | Authorization Server giữ private key | Resource server tin public key/JWKS | Công bố public key mới, ký bằng key mới, giữ key kiểm tra cũ đến hết token hợp lệ |
| **Chứng chỉ mTLS + private key** | PKI cấp; workload giữ private key | TLS peer | Cấp chứng chỉ/key mới, cập nhật trust, mở lại kết nối, loại chứng chỉ cũ |
| **CA/trust anchor** | PKI operator | Client/server TLS hoặc token validator | Phân phối trust bundle mới trước, thay cert, loại CA cũ sau |
| **JWT access token** | Authorization Server | Resource server xác minh chữ ký và claims | Token mới được phát hành và token cũ tự hết hạn hoặc bị vô hiệu theo chính sách |
| **Opaque access token** | Authorization Server | Resource server introspection | Kiểm tra active/metadata; token mới cấp theo lifecycle |
| **Refresh token** nếu có | Authorization Server | Token endpoint | Có thể dùng refresh-token rotation: dùng token hiện tại để lấy token kế tiếp, token cũ bị vô hiệu |
| **Database/broker password** | Database/broker hoặc secret controller | Database/broker | Cấp password mới, làm mới connection pool, thu hồi password cũ |

**Điểm cần nhớ:**

- **Access token** mang quyền được cấp tới API; API phải kiểm tra issuer, audience, scope, thời hạn và chính sách nghiệp vụ.
- **Client secret** dùng để xác thực OAuth client khi xin token, không phải token gọi Orders API.
- **JWT signing private key** thuộc bên phát hành token; backend chỉ nên cần public key tin cậy.
- **Refresh token** không được dùng trực tiếp làm credential gọi resource API. **Client credentials grant** thường không phát refresh token vì client có thể tự xác thực để xin access token mới.
- **Chứng chỉ mTLS** xác thực peer của kết nối; không tự xác nhận quyền của người dùng hoặc quyền trên một đơn hàng.

## 3. Mô hình trust và các bên liên quan

Ví dụ mô hình giao tiếp:

~~~mermaid
flowchart TD
    PKI["PKI / CA<br/>Chứng chỉ workload"] --> P["Payment Service"]
    PKI --> O["Orders API"]
    SM["Secret Manager<br/>credential version"] --> P
    P -->|"mTLS + OAuth client credential"| AS["Authorization Server"]
    AS -->|"Access token JWT hoặc opaque"| P
    P -->|"mTLS + Bearer token"| O
    O -->|"JWKS hoặc introspection"| AS
    O --> POL["Authorization policy<br/>scope/tenant/order"]
~~~

Phân biệt các điểm xác thực:

1. **TLS/mTLS:** xác định đối tác kết nối qua chuỗi chứng chỉ và private-key proof.
2. **OAuth client authentication:** xác định client được phép yêu cầu token, ví dụ bằng secret, private_key_jwt hoặc mTLS client authentication.
3. **Access token validation:** API kiểm tra token đúng issuer, đúng API audience, chưa hết hạn, có quyền phù hợp.
4. **Resource authorization:** dù token có scope hợp lệ, ứng dụng vẫn phải quyết định caller được thao tác trên đối tượng, tenant và trạng thái nghiệp vụ cụ thể hay không.

Rotation phải giữ nhất quán các ranh giới trên. Ví dụ Payment Service đổi chứng chỉ mTLS nhưng access token bị ràng buộc với chứng chỉ cũ; TLS kết nối thành công vẫn có thể khiến token bị từ chối vì sai binding.

## 4. Vòng đời chuẩn: tạo → phân phối → chuyển → thu hồi

~~~mermaid
flowchart LR
    A["1. Lập inventory<br/>v1 đang được dùng ở đâu?"] --> B["2. Tạo v2<br/>lưu ở secret manager"]
    B --> C["3. Kích hoạt v2<br/>vẫn chấp nhận v1 nếu hỗ trợ"]
    C --> D["4. Canary / rollout<br/>kiểm tra token và API"]
    D --> E["5. Quan sát<br/>xác minh mọi replica dùng v2"]
    E --> F["6. Revoke v1<br/>negative test + audit"]
~~~

### Những ràng buộc kỹ thuật

- **Inventory:** liệt kê production/staging, replica, cronjob, worker, service account, connection pool, DR/failover và tích hợp đối tác.
- **Quyền tối thiểu:** credential v2 chỉ được cấp những scope, role, audience cần thiết; không nhân tiện mở rộng quyền.
- **Versioning:** lưu credential theo version ID hoặc alias có kiểm soát, bảo vệ từng version bằng ACL và audit.
- **Overlap:** nhiều provider cho phép v1 và v2 cùng hợp lệ một thời gian; một số chỉ cho một secret. Phải kiểm tra khả năng thực tế trước khi chọn kế hoạch.
- **Atomic switch:** khi thay client ID, secret và endpoint cùng lúc, một request phải dùng một snapshot cấu hình nhất quán.
- **Observability:** đo lỗi token issuance, TLS handshake, 401/403, token/JWKS validation, các replica và phiên bản credential đang dùng.
- **Rollback:** chỉ quay lại v1 nếu v1 còn hợp lệ và chưa bị nghi lộ. Sau khi v1 bị thu hồi, cần phương án phát credential mới nếu xảy ra lỗi.

### Đồng hồ chuyển đổi

Có thể mô tả tiến trình bằng:

- **T_create:** thời điểm tạo credential v2.
- **T_accept:** issuer/API bắt đầu chấp nhận v2.
- **T_switch:** workload chuyển request sang v2.
- **T_revoke:** issuer/API ngừng chấp nhận v1.
- **T_exp:** thời điểm token/certificate cuối cùng liên quan đến v1 hết hiệu lực.

Với một credential hỗ trợ chồng lấn, trình tự thường là **T_create ≤ T_accept ≤ T_switch ≤ T_revoke**. Nhưng **T_exp** của access token, JWT hoặc session TLS có thể nằm sau T_revoke của client secret. Cần tính riêng vòng đời từng đối tượng.

## 5. Rotation của OAuth client secret trong client_credentials

Giả định Payment Service có các replica **A, B, C**, dùng OAuth client **payment-service** để gọi **orders-api**.

### Bước 1: Chuẩn bị trước khi tạo secret

Xác định client ID, grant type, token endpoint, phương thức client authentication (ví dụ **client_secret_basic**), scope, audience, môi trường. Kiểm tra Authorization Server có cho phép **nhiều secret đang hợp lệ** cho cùng client không và có cung cấp version/audit đáng tin cậy không.

Với hệ thống có nhiều nhóm workload, phải tính cả batch job ít chạy, tác vụ chạy thủ công, service dự phòng và các bản triển khai chưa được rollout. Chỉ nhìn traffic hiện tại không chứng minh mọi instance đã đổi secret.

### Bước 2: Cấp v2 và giữ v1 trong cửa sổ overlap

Nếu provider hỗ trợ, tạo secret v2, lưu vào hệ thống quản lý secret, cho phép cả v1/v2 dùng để xác thực OAuth client tạm thời. Không gửi secret qua email/chat, không hardcode vào Git, manifest hoặc issue tracker.

~~~mermaid
sequenceDiagram
    autonumber
    participant Op as Operator
    participant AS as Authorization Server
    participant SM as Secret Manager
    participant P as Payment Service
    participant O as Orders API

    Op->>AS: Tạo v2, tạm giữ v1 hợp lệ
    Op->>SM: Lưu v2 với quyền truy cập giới hạn
    SM-->>P: Phân phối v2
    P->>AS: client_credentials, xác thực bằng v2
    AS-->>P: access token cho orders-api
    P->>O: API call dùng access token mới
    O-->>P: Kết quả hợp lệ
    Op->>Op: Xác nhận mọi replica dùng v2
    Op->>AS: Vô hiệu hóa v1
    P->>AS: Token request mới bằng v2
    AS-->>P: Thành công
~~~

### Bước 3: Canary và rolling update

Cho replica A nạp v2, gọi token endpoint để lấy token mới, dùng token đó gọi Orders API; kiểm tra **audience/scope/exp** và hành vi authorization. Sau khi canary đạt yêu cầu, rollout B và C.

Nếu service chỉ đọc biến môi trường lúc startup, cần rolling restart. Nếu secret provider hỗ trợ reload động, kiểm tra token request sau reload để chắc chắn **credential đang dùng đã đổi**.

### Bước 4: Thu hồi v1

Trước khi thu hồi, phải kiểm tra tất cả replica, worker, scheduled job, instance DR và phần mềm bên thứ ba liên quan đã nạp v2. Sau khi disable v1, thử cấp token bằng v1 và xác nhận thất bại; đồng thời v2 vẫn phải cấp token và gọi API được.

### Nhà cung cấp không hỗ trợ hai client secret đồng thời

Không được giả định có overlap. Có thể phối hợp cutover tại một thời điểm được kiểm soát hoặc tạo **client registration mới** với quyền tương ứng rồi chuyển dần. Tuy nhiên, client registration mới có thể thay đổi **client_id**, subject, policy, audit và permission mapping; phải kiểm thử các ràng buộc downstream trước khi rollout.

Nếu buộc phải thay secret tại một thời điểm, cần đánh giá khả năng lỗi token issuance ngắn hạn, retry có giới hạn, pre-warmed token cache và hướng khôi phục. Không sử dụng token cache để che giấu việc ứng dụng chưa thực sự xác thực được bằng v2.

### Client secret đổi nhưng access token cũ vẫn còn?

**Có thể còn.** Access token có vòng đời độc lập:

- Với **JWT access token**, resource server có thể chỉ kiểm tra chữ ký và các claim như **iss**, **aud**, **exp**, **nbf**, **scope**; token đã phát hành có thể tiếp tục hợp lệ tới lúc hết hạn.
- Với **opaque access token**, API có thể introspect trạng thái **active**, nhưng việc khóa client secret có vô hiệu hóa token đã phát hành hay không phụ thuộc Authorization Server.
- Với token **sender-constrained**, ngoài token validity còn phải kiểm tra bằng chứng sở hữu khóa/chứng chỉ.

Nếu secret v1 **bị lộ**, cần đánh giá các token đã được phát hành và dùng cơ chế thu hồi/denylist/introspection hoặc thay policy khi mức độ rủi ro yêu cầu. Chỉ đổi secret không đảm bảo xóa mọi quyền truy cập đang tồn tại.

## 6. Rotation của khóa ký JWT và JWKS

Authorization Server ký JWT bằng **private signing key**. API resource server xác minh bằng **public key** tương ứng lấy từ key set tin cậy, thường là **JWKS**.

JWT header có thể chứa **kid**:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "jwt-signing-2026-v2"
}
~~~

**kid** chỉ giúp chọn khóa trong bộ khóa của issuer đã tin cậy. Resource server phải cấu hình rõ issuer, tập thuật toán cho phép, audience; không lấy thuật toán/key URL tự khai trong JWT để chấp nhận khóa không được tin cậy.

### Trình tự chuyển khóa ký không gián đoạn

1. Tạo cặp key v2, giữ private key ở KMS/HSM hoặc kho được phép.
2. **Công bố public key v2** qua JWKS cùng public key v1.
3. Cho verifier làm mới JWKS hoặc đợi cache có khả năng tra v2; kiểm tra không còn lỗi **unknown kid**.
4. Chuyển issuer sang ký JWT mới bằng private key v2 và **kid=v2**.
5. Tiếp tục giữ public key v1 để các access token được ký bằng v1 còn hạn có thể được xác minh.
6. Sau khi token v1 cuối cùng hết hạn và các verifier đồng bộ, loại public key v1 theo chính sách.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant J as JWKS
    participant RS as Resource Server
    AS->>J: Publish v1 public key + v2 public key
    RS->>J: Refresh/observe v2
    AS->>AS: Start signing new JWT with private key v2
    AS-->>RS: JWT kid=v2
    RS->>RS: Validate token with trusted v2 public key
    Note over AS,RS: Giữ v1 public key cho JWT v1 chưa hết hạn
    AS->>J: Remove public key v1 khi an toàn
~~~

Thời gian giữ v1 phải tính theo **access token maximum lifetime**, thời điểm token cuối cùng ký bằng v1, clock skew cho phép, việc phân phối và cache của verifier. Ví dụ TTL 15 phút không có nghĩa được bỏ public key v1 chỉ 15 phút sau khi tạo v2; thời điểm tính phải gắn với **token cuối cùng được phát hành bằng v1**.

### Khi private signing key bị compromise

Nếu private key v1 bị đánh cắp, kẻ tấn công có thể tạo JWT giả mà verifier vẫn xác nhận chữ ký hợp lệ. Trong trường hợp này, giữ v1 chỉ để tránh gián đoạn là rủi ro lớn. Cần xem xét loại bỏ v1 khỏi tập trusted keys ngay, buộc verifier refresh cache, thay key và xử lý token đang dùng, chấp nhận khả năng các phiên hợp lệ ký bằng v1 bị gián đoạn.

**Phân biệt:** đổi signing key của Authorization Server **không phải** đổi client secret của một OAuth client. Hai loại key có owner và phạm vi ảnh hưởng khác nhau.

## 7. Rotation của private_key_jwt

Với phương thức **private_key_jwt** trong OAuth 2.0, client gửi một **client assertion JWT** ký bằng private key để chứng minh danh tính tại token endpoint. Authorization Server xác minh bằng public key đã đăng ký.

Quy trình điển hình:

1. Client tạo key pair v2, không xuất private key vào log hoặc file công khai.
2. Đăng ký public key v2 ở Authorization Server; nếu hỗ trợ, giữ public key v1 trong cửa sổ overlap.
3. Client phát assertion mới ký bằng private key v2; kiểm tra **iss, sub, aud, exp, jti** đúng yêu cầu của token endpoint.
4. Gọi token endpoint để xác nhận assertion mới được chấp nhận.
5. Đảm bảo tất cả replica chuyển sang ký bằng v2 rồi loại public key v1.

Client assertion phải có **thời hạn ngắn** và cơ chế giảm phát lại phù hợp. Không chuyển tiếp assertion qua log, message queue hoặc API khác. Nếu provider không hỗ trợ nhiều key, dùng kế hoạch cutover đồng bộ hoặc đăng ký client mới khi phù hợp.

## 8. Rotation chứng chỉ mTLS, trust bundle và token binding

mTLS xác thực **hai phía của kết nối** bằng chứng chỉ và bằng chứng sở hữu khóa riêng. Một workload có thể có chứng chỉ với danh tính SAN (ví dụ URI SAN kiểu SPIFFE ID), trust bundle và cơ chế gia hạn tự động.

### Quy trình thay certificate

1. Xác thực workload đang xin chứng chỉ mới; cấp key/cert v2 với SAN, thời hạn, Extended Key Usage phù hợp.
2. Nếu thay CA, phân phối **trust anchor mới** đến peer trước khi chuyển sang cert do CA mới cấp.
3. Service reload TLS material hoặc mở kết nối mới bằng v2; với connection pool/gRPC channel dài hạn cần chủ động xem xét kết nối cũ.
4. Peer xác minh chain, SAN, mục đích sử dụng chứng chỉ và **workload authorization policy**.
5. Sau khi xác nhận mọi kết nối mới sử dụng v2, vô hiệu hóa cert v1 và cập nhật trust bundle khi thích hợp.

**Lưu ý:** File keystore/certificate được thay trên disk không đảm bảo JVM, proxy hay service mesh đang sử dụng nội dung mới. TLS context có thể đã được nạp lúc startup. Phải kiểm tra cơ chế reload theo phiên bản framework và có rolling restart khi cần.

### Certificate-bound access token

OAuth 2.0 có cơ chế **certificate-bound access token** (RFC 8705). Token có thể chứa thông tin ràng buộc:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "payment-service",
  "aud": "orders-api",
  "scope": "orders.capture",
  "cnf": {
    "x5t#S256": "<sha256-thumbprint-client-certificate-v1>"
  }
}
~~~

Đây là nội dung JSON minh họa; JWT thực tế cần được ký và kiểm tra đầy đủ.

Khi Payment Service thay **client certificate v1 → v2** mà vẫn dùng access token bị ràng buộc với **certificate v1**, resource server phải từ chối vì dấu vân tay **cnf.x5t#S256** không khớp chứng chỉ trên kết nối mTLS hiện tại.

Giải pháp là **cấp access token mới ràng buộc với v2** rồi gọi API trên kết nối dùng cert v2. Không tắt kiểm tra **cnf** để làm rotation “thành công”, vì sẽ làm giảm khả năng chống sử dụng lại token bị đánh cắp.

### TLS termination tại gateway/service mesh

Nếu gateway terminate mTLS rồi chuyển ngữ cảnh danh tính tới backend qua header, backend chỉ nên tin header do gateway đáng tin tạo **sau khi xác thực client certificate**. Gateway phải loại mọi header cùng tên do client gửi; đoạn gateway → backend phải được bảo vệ và backend không thể bị bypass bằng đường mạng khác. Tin **X-Client-Cert** hoặc **X-Service-Name** do Internet client tự gửi là lỗi giả mạo danh tính.

## 9. Refresh token rotation khác gì vòng đời access token?

Trong giao tiếp service-to-service thuần **client_credentials**, client thường nhận access token và tự xác thực lại khi cần token mới. Không nên tự giả định có refresh token.

Nếu một backend giữ refresh token trong luồng đại diện người dùng hoặc OAuth grant khác, Authorization Server có thể sử dụng **refresh-token rotation**:

1. Client gửi refresh token hiện tại.
2. Authorization Server xác minh, phát access token mới và **refresh token mới**.
3. Refresh token cũ bị vô hiệu hóa sau khi sử dụng.
4. Client lưu refresh token mới **bền vững và atomically**.
5. Nếu refresh token cũ bị dùng lại, Authorization Server có thể phát hiện **reuse** và áp dụng chính sách khóa token family/phiên.

Hai replica cùng dùng refresh token v1 có thể gây race: một replica nhận v2, replica khác dùng lại v1 và kích hoạt reuse detection. Cần **single-flight/lock theo phiên**, lưu token mới atomically và xử lý lỗi mạng khi token endpoint đã đổi token nhưng response bị mất.

### Không đồng nhất các khái niệm

- Lấy access token mới vì token cũ gần hết hạn là **access token renewal**.
- Đổi OAuth client secret là **client credential rotation**.
- Phát refresh token kế tiếp và vô hiệu token trước là **refresh-token rotation**.
- Đổi private signing key/JWKS là **issuer signing key rotation**.

Các hoạt động có thể xảy ra gần nhau nhưng phải được giám sát và kiểm thử theo cơ chế riêng.

## 10. Cấu hình Spring Boot và điểm cần chú ý

Ví dụ Payment Service đăng ký OAuth 2.0 client dùng **client_credentials**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-client:
            provider: internal-idp
            client-id: payment-service
            client-secret: ${ORDERS_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: orders.capture
        provider:
          internal-idp:
            token-uri: https://auth.internal.example/oauth2/token
~~~

Tại runtime, **ORDERS_OAUTH_CLIENT_SECRET** nên được cung cấp qua hệ thống quản lý secret có RBAC, audit và cơ chế đưa secret vào ứng dụng an toàn. Không ghi giá trị thật vào YAML, Git, Dockerfile, CI log hoặc exception.

**Điểm then chốt khi rotation:** cập nhật secret trong hệ thống quản lý **không mặc định** làm một tiến trình Java/Spring Boot đang chạy nạp lại giá trị. Nếu secret được đưa vào biến môi trường lúc khởi động, phải thực hiện **rolling restart** hoặc cơ chế refresh config đã được triển khai và kiểm chứng. Sau reload, chủ động tạo **token request mới** để xác nhận v2 thật sự được sử dụng; token đang cache có thể vẫn gọi API được bằng access token cũ và che giấu lỗi client secret.

### Tách việc đọc secret khỏi business logic

~~~java
// Minh họa hợp đồng kiến trúc, không phải OAuth client hoàn chỉnh.
public interface ClientCredentialProvider {
    ClientCredentialSnapshot current();
}

public record ClientCredentialSnapshot(
        String clientId,
        char[] clientSecret,
        String versionId
) {}

// Luồng ở lớp token client:
// 1. Đọc một snapshot nhất quán từ provider.
// 2. Gửi token request qua TLS và OAuth library đáng tin cậy.
// 3. Xác minh token response, cache theo expires_in với biên an toàn.
// 4. Khi versionId thay đổi, xin token mới bằng snapshot mới.
// 5. Redact secret, Authorization header và access token khỏi log.
// 6. Theo dõi lỗi invalid_client và token issuance theo version ID.
~~~

Đoạn trên thể hiện trách nhiệm kiến trúc. Trong thực tế nên dùng Spring Security OAuth2 Client phù hợp phiên bản dự án và cách quản lý credential runtime đã được thử nghiệm. Kiểu **char[]** không tự xóa hết bản sao bí mật khỏi heap hay log của thư viện; cần bảo vệ process, crash dump, file swap và quyền truy cập secret.

### Ba replica chuyển đổi như thế nào?

| Giai đoạn | Replica A | Replica B | Replica C | Issuer chấp nhận |
|---|---|---|---|---|
| Trước rotation | v1 | v1 | v1 | v1 |
| Đã cấp v2 | v1 | v1 | v1 | v1 + v2 |
| Canary | v2 | v1 | v1 | v1 + v2 |
| Rolling update | v2 | v2 | v2 | v1 + v2 |
| Thu hồi | v2 | v2 | v2 | Chỉ v2 |

Đặc biệt chú ý **scheduled jobs, worker ít chạy, DR/failover** có thể không lộ lỗi cho tới khi cần xin token mới. Phải chủ động kiểm tra token issuance cho các nhóm workload đó.

## 11. Runbook rotation có thể áp dụng

### Giai đoạn A — Preflight

1. Chỉ rõ credential v1, owner, issuer/provider, scope, audience, thời hạn, nơi lưu và các hệ thống phụ thuộc.
2. Xác định provider có chấp nhận hai version đồng thời không; nếu không, thiết kế cutover/parallel registration.
3. Chọn thời gian chuyển đổi, canary, rollback, chỉ số theo dõi và ngưỡng dừng rollout.
4. Lấy baseline tỷ lệ token endpoint error, API 401/403, TLS handshake failure và tình trạng instance.
5. Đảm bảo có negative test và không ghi secret vào công cụ vận hành.

### Giai đoạn B — Tạo v2

1. Cấp credential mới qua hệ thống được phê duyệt.
2. Lưu v2 vào secret manager, kiểm soát ACL và audit.
3. Cấu hình bên xác minh chấp nhận v2; với JWT signing key, xuất bản **public key v2** trước.
4. Chạy smoke test canary: OAuth client authentication, access token có **aud/scope/exp** đúng; mTLS xác minh peer/SAN đúng.

### Giai đoạn C — Chuyển traffic

1. Chuyển một phần instance sang v2, chủ động xin token hoặc mở mTLS connection mới.
2. Theo dõi invalid_client, unknown kid, 401/403, TLS error và latency.
3. Mở rộng rollout đến mọi instance/batch/DR.
4. Xác minh không còn workload cần thiết sử dụng v1.
5. Với JWT và certificate-bound token, tính thêm thời hạn token, JWKS cache, connection lifetime và binding.

### Giai đoạn D — Kết thúc

1. Vô hiệu hóa v1 khi đáp ứng điều kiện chuyển đổi và chính sách an toàn.
2. Thử v1 thất bại, v2 hoạt động; xác nhận API vẫn phân quyền đúng.
3. Xóa bản sao v1 ở nơi lưu, cập nhật metadata/audit và lịch rotation tiếp theo.
4. Ghi nhận sự cố hoặc thiếu sót trong inventory nếu có.

**Rollback:** Trước khi revoke v1, có thể trở lại v1 nếu còn hợp lệ và không bị compromise. Sau revoke, rollback thường phải cấp mới credential được phép. Nếu credential cũ bị lộ, không phục hồi v1 chỉ để tiện khôi phục tính sẵn sàng.

## 12. Credential rotation định kỳ và xử lý credential bị lộ

| Nội dung | Rotation định kỳ | Nghi credential đã bị đánh cắp |
|---|---|---|
| Mục tiêu | Giảm tuổi credential và bảo đảm lifecycle | Chặn ngay quyền của kẻ tấn công |
| Overlap | Có thể chấp nhận ngắn hạn để tránh gián đoạn | Thu hẹp tối đa, đôi khi vô hiệu ngay |
| Access token cũ | Có thể còn tới exp theo policy | Đánh giá revoke/introspection/denylist hoặc thay policy |
| Signing key JWT cũ | Giữ public key kiểm tra đến khi token v1 hết hạn | Có thể buộc verifier không tin key cũ ngay |
| mTLS cert cũ | Rotate có kế hoạch theo trust/connection | Cắt quyền, thu hồi cert hoặc khóa danh tính/đường kết nối |
| Kiểm tra bổ sung | Canary, rollout, độ sẵn sàng | Audit log, phạm vi lộ, token issuance, khóa khác cùng bị ảnh hưởng |

Ví dụ client secret v1 lộ trong CI log: tạo v2 và thu hồi v1 chưa đủ nếu kẻ tấn công vẫn có quyền đọc CI log hoặc secret manager. Phải khắc phục **nguồn lộ** và đánh giá các access token đã cấp trước đó. Nếu private signing key của Authorization Server bị lộ, chỉ thay OAuth client secret sẽ không ngăn được việc tạo JWT giả.

## 13. Monitoring và chẩn đoán lỗi

| Triệu chứng | Nguyên nhân cần điều tra |
|---|---|
| Token endpoint báo **invalid_client** | Secret v1 đã hết hiệu lực, ID/secret không khớp, private_key_jwt sai key/audience |
| API báo **401** | Access token invalid/hết hạn, sai issuer/audience, bị thu hồi, sai chữ ký |
| API báo **403** | Caller xác thực được nhưng thiếu scope/role hoặc vi phạm resource authorization |
| **unknown kid** | JWKS verifier chưa biết public key mới hoặc cấu hình issuer/key sai |
| **signature verification failed** | Sai signing key, issuer hoặc token bị sửa |
| **TLS handshake failed** | Thiếu client certificate, sai CA/SAN/EKU, cert hết hạn, private key không khớp |
| mTLS thành công nhưng token bị từ chối | Có thể token bound với cert khác, sai audience hoặc scope |
| Secret store đã cập nhật nhưng app vẫn lỗi | JVM/process chưa reload config, replica hoặc job bị bỏ sót |
| Thay refresh token gây lỗi reuse | Hai replica refresh đồng thời hoặc client lưu refresh token mới thất bại |

Không thể suy nguyên nhân chỉ từ HTTP status. TLS handshake failure có thể xảy ra **trước HTTP**, nên không phải lúc nào cũng có 401/403. Dùng trace ID, deployment version, thời điểm rotation và các sự kiện không chứa bí mật để xác minh.

### Những lỗi vận hành phổ biến

- Tạo secret v2 nhưng **không xác nhận ứng dụng đã nạp và dùng v2**.
- Xóa client secret v1 trước khi cronjob/DR chuyển đổi.
- Ký JWT bằng key v2 trước khi verifier cập nhật JWKS.
- Xóa public key v1 khi vẫn còn JWT ký bằng v1 hợp lệ.
- Thay chứng chỉ nhưng connection pool tiếp tục dùng TLS session cũ.
- Thay mTLS cert nhưng tiếp tục gửi certificate-bound token gắn với cert trước đó.
- Bật logging HTTP headers ở token endpoint, vô tình ghi client secret hoặc access token.
- Tắt hostname/certificate verification hoặc token-binding check để “chữa” lỗi rotation.
- Không phân biệt credential đã bị lộ với credential chỉ đến kỳ thay.

## 14. Các tình huống thực hành

### Tình huống A — Secret đổi nhưng chỉ có một số replica lỗi

Payment Service có 12 replica. v2 đã lưu ở secret manager nhưng chỉ 8 replica được restart. Khi v1 bị thu hồi, 4 replica cũ gửi token request bằng v1 và nhận **invalid_client**. Trong vài phút đầu API vẫn có response thành công do token cũ còn cache.

**Phân tích:** Lỗi nằm ở rollout và kiểm tra version trên từng instance. Giải pháp là xác minh việc nạp v2, thực hiện rolling update đầy đủ, ép kiểm thử token issuance và chỉ revoke sau khi xác nhận cả scheduled jobs/DR.

### Tình huống B — JWT hợp lệ lại bị từ chối sau đổi khóa

Authorization Server bắt đầu ký bằng v2 nhưng một số resource server vẫn cache JWKS chỉ chứa v1. Token có **kid=v2** gặp lỗi **unknown kid**.

**Phân tích:** Cần công bố public key v2 sớm, chờ verifier đồng bộ hoặc hỗ trợ refresh key đáng tin cậy trước khi bắt đầu ký. Không bỏ qua xác minh JWT.

### Tình huống C — mTLS cert mới, token cũ

Payment Service dùng chứng chỉ v2 thành công khi TLS handshake nhưng vẫn có bearer access token với **cnf.x5t#S256** của cert v1. Order Service từ chối.

**Phân tích:** Phải cấp token mới ràng buộc với cert v2 rồi dùng trên kết nối cùng cert v2. Mismatch này là cơ chế bảo vệ đúng thiết kế.

### Tình huống D — Client secret lộ nhưng JWT vẫn gọi được API

Client secret v1 đã bị vô hiệu hóa. Tuy nhiên, một access token JWT ký đúng, chưa hết hạn và đã phát hành trước đó vẫn được API offline validator chấp nhận.

**Phân tích:** Client credential rotation và token revocation độc lập. Cần chính sách token lifetime, denylist/introspection hoặc cơ chế sender-constrained và phản ứng sự cố tương ứng.

## 15. Kiểm thử trước khi báo hoàn tất

| Kịch bản kiểm thử | Kết quả mong đợi |
|---|---|
| v2 xin access token đúng token endpoint | Thành công với quyền, audience và expiry được cấp |
| v1 xin token mới **sau revoke** | Bị từ chối |
| Secret sai hoặc client assertion ký bằng key không đăng ký | Không thể xác thực OAuth client |
| Access token sai issuer/audience/exp | Resource server từ chối |
| JWT mới có **kid=v2** | Tất cả verifier mục tiêu xác minh được |
| JWT v1 còn hạn trong overlap định kỳ | Được kiểm tra theo policy đã định |
| Cert mTLS v2 có SAN chính xác | TLS handshake thành công |
| Chứng chỉ từ CA không tin hoặc hostname không khớp | TLS client/server validation từ chối |
| Client có chứng chỉ hợp lệ nhưng không đủ quyền | Authorization từ chối, không chỉ dựa vào TLS |
| Token bound với cert v1 được gửi cùng cert v2 | Từ chối do **cnf** không khớp |
| Replica ít traffic, batch job, DR | Chủ động xin token mới/kết nối mới bằng v2 thành công |
| Refresh token cũ được dùng lại sau rotation | Áp dụng reuse detection và policy đã định |
| Logging/tracing khi có lỗi | Không chứa client secret, private key, bearer/refresh token |
| Rollback/cutover khi một replica restart giữa chừng | Dùng credential hợp lệ theo phiên bản nhất quán |

### Checklist cuối cùng

- Đã phân biệt client secret, API key, signing key, mTLS cert, access token và refresh token chưa?
- Credential v2 có đúng **scope**, **audience**, danh tính workload, SAN và thời hạn không?
- Tất cả replica, worker, job ít chạy và failover đã được kiểm thử với v2?
- Với JWT: public key mới đã đến verifier trước khi ký mới, và key cũ còn được giữ đủ lâu để token hợp lệ hết hạn?
- Với certificate-bound token: đã cấp token phù hợp certificate mới?
- Với refresh-token rotation: có đồng bộ việc refresh và lưu token mới atomically?
- Đã thử v1 thất bại sau revoke và v2 vẫn hoạt động?
- Quy trình ứng phó credential bị lộ có đánh giá token đã phát hành, audit và nguồn rò rỉ?
- Metric và log có phục vụ điều tra mà không vô tình tiết lộ credential?

## 16. Tổng kết

**Credential rotation** trong service-to-service là quy trình phối hợp giữa **bên phát hành**, **workload sử dụng** và **bên xác minh**, gồm cấp credential mới, phân phối an toàn, chuyển đổi có giám sát, rồi thu hồi phiên bản cũ. Thời gian chồng lấn và hành vi thu hồi phụ thuộc từng loại credential.

OAuth client secret xác thực client để xin token; signing key của JWT xác nhận token do issuer phát hành; access token mang quyền tới resource API; refresh token, nếu được cấp, có cơ chế rotation và reuse detection riêng; mTLS certificate xác thực peer của kết nối. Không nên đồng nhất chúng hoặc cho rằng thay một secret đã vô hiệu hóa mọi access token.

Rotation chỉ hoàn tất khi **mọi phụ thuộc đã thực sự dùng credential mới**, **credential cũ bị vô hiệu hóa theo đúng chính sách**, và hệ thống vẫn kiểm tra đầy đủ **claims, issuer, audience, scope, workload identity, authorization và khả năng chống sử dụng lại token bị đánh cắp**.
