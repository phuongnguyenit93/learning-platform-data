# Discovery (Khám phá cấu hình OpenID Provider)

> **Chương:** OpenID Connect  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Hiểu cách OIDC client khám phá metadata của OpenID Provider (OP), tìm endpoint và khóa công khai để tích hợp đúng giao thức; thiết lập nguồn tin cậy, kiểm tra issuer, cache metadata/JWKS và xử lý xoay khóa, lỗi mạng, multi-tenant cùng các rủi ro SSRF.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích OpenID Provider Discovery giải quyết vấn đề gì trong tích hợp OpenID Connect.
2. Phân biệt discovery metadata với authorization request, token response, UserInfo, dynamic client registration và OAuth authorization-server metadata.
3. Nhận diện các trường quan trọng như issuer, authorization endpoint, token endpoint, JWKS URI, response types, subject types và thuật toán ký ID token.
4. Mô tả cách OIDC client lấy discovery document và khóa công khai từ JWKS endpoint.
5. Thiết lập trust anchor cho issuer, kiểm tra issuer chính xác và tránh tin metadata từ nguồn không được phép.
6. Thiết kế cache, refresh metadata/JWKS, xử lý unknown kid và xoay khóa ký mà không tạo khoảng thời gian chấp nhận khóa không tin cậy.
7. Phòng chống SSRF, open redirect, issuer confusion, key confusion và các lỗi cấu hình trong môi trường nhiều tenant.
8. Viết kịch bản kiểm thử discovery, endpoint, chữ ký, issuer, audience, key rotation và sự cố khả dụng.

## 1. Discovery trong OpenID Connect là gì?

**OpenID Provider Discovery** là cơ chế để một OIDC client tìm metadata cấu hình của một OpenID Provider (OP), bao gồm các endpoint, khả năng giao thức và địa chỉ bộ khóa công khai mà client cần để giao tiếp và xác minh kết quả xác thực.

Thay vì tự đoán URL của authorization endpoint, token endpoint hoặc JWKS endpoint, client lấy một tài liệu metadata từ một địa chỉ well-known được xây dựng từ **issuer identifier**. Tài liệu này mô tả cách OP hoạt động và những tính năng mà OP hỗ trợ.

Ví dụ, một tổ chức dùng OP tại issuer:

~~~text
https://login.example.edu
~~~

OIDC client có thể truy vấn discovery document tại:

~~~text
https://login.example.edu/.well-known/openid-configuration
~~~

Nếu issuer có path, well-known path được gắn theo quy tắc của OIDC Discovery vào issuer đó. Ví dụ issuer https://login.example.edu/tenant-a có discovery URI dạng https://login.example.edu/tenant-a/.well-known/openid-configuration.

Discovery giúp client tích hợp theo metadata được công bố, giảm cấu hình endpoint thủ công và hỗ trợ thay đổi khóa hoặc endpoint có kiểm soát. Tuy nhiên, metadata chỉ có giá trị khi client đã xác định đúng issuer và tin cậy nguồn cung cấp.

**Discovery không phải là xác thực người dùng.** Tải được metadata không có nghĩa người dùng đã đăng nhập, tài khoản tồn tại hoặc client đã được phép sử dụng OP. Discovery cũng không tự đăng ký client và không cấp access token.

## 2. Discovery nằm ở đâu trong kiến trúc OIDC?

Các thành phần liên quan:

| Thành phần | Vai trò trong discovery |
| --- | --- |
| **OIDC Client / Relying Party (RP)** | Biết issuer cần tích hợp, lấy metadata và dùng endpoint/khóa theo chính sách. |
| **OpenID Provider (OP)** | Công bố metadata và JWKS, vận hành authorization/token/UserInfo endpoints. |
| **Discovery document** | Tài liệu JSON mô tả issuer, endpoint và khả năng giao thức. |
| **JWKS endpoint** | Cung cấp tập public key mà client có thể dùng để xác minh chữ ký token. |
| **Browser** | Tham gia redirect trong authorization flow; không phải nguồn tin cậy cho metadata hoặc kết quả xác minh. |
| **Configuration/trust store** | Nguồn xác định issuer nào được phép dùng, tenant nào gắn với issuer nào và policy nào áp dụng. |

~~~mermaid
flowchart TD
    C["OIDC Client / RP"] --> T["Trust configuration\nIssuer được phép"]
    T --> D["GET issuer/.well-known/\nopenid-configuration"]
    D --> M["Discovery metadata"]
    M --> A["Authorization endpoint"]
    M --> E["Token endpoint"]
    M --> U["UserInfo endpoint"]
    M --> J["JWKS URI"]
    J --> K["Public signing keys"]
    C --> A
    C --> E
    C --> U
    K --> V["Xác minh chữ ký ID token"]
    V --> I["Kiểm tra issuer, audience,\nnonce, thời hạn và policy"]
~~~

Discovery thường được thực hiện khi khởi tạo cấu hình provider hoặc khi metadata cần được làm mới. Client không nên tải discovery document và JWKS không kiểm soát trong mỗi request API; cần cache và refresh theo chính sách.

### Discovery và authentication flow là hai giai đoạn khác nhau

1. **Discovery/configuration:** client tìm hiểu OP hỗ trợ endpoint và khả năng nào.
2. **Authorization/authentication:** client tạo authorization request, browser chuyển tới OP, người dùng xác thực và client nhận kết quả.
3. **Token validation:** client xác minh ID token theo issuer, khóa, audience, nonce và các điều kiện OIDC.

Không được bỏ qua bước xác minh ID token chỉ vì endpoint và khóa được tìm thấy qua discovery.

## 3. Discovery URI và issuer identifier

Issuer là định danh của OP và là một phần cốt lõi của trust relationship.

Ví dụ:

~~~text
Issuer:
https://id.example.org

Discovery URI:
https://id.example.org/.well-known/openid-configuration
~~~

Với issuer có path:

~~~text
Issuer:
https://id.example.org/realms/learning

Discovery URI:
https://id.example.org/realms/learning/.well-known/openid-configuration
~~~

### Các nguyên tắc quan trọng

- Dùng HTTPS trong triển khai production.
- Issuer phải đến từ cấu hình đáng tin cậy, tenant registry hoặc quy trình discovery được tổ chức phê duyệt.
- Không lấy một URL tùy ý từ query parameter hoặc request body rồi để server gọi URL đó.
- Không tự ý bỏ path, đổi scheme, bỏ port hoặc chuẩn hóa issuer theo cách làm hai issuer khác nhau trở thành một.
- So sánh giá trị issuer trong metadata và claim iss của ID token theo yêu cầu chính xác của OIDC; không chỉ so sánh hostname.
- Không suy ra issuer chỉ từ email domain nếu tổ chức chưa định nghĩa cơ chế xác định provider đáng tin cậy.

Ví dụ, hai issuer sau là hai định danh khác nhau:

~~~text
https://id.example.org/tenant-a
https://id.example.org/tenant-b
~~~

Dù cùng hostname, chúng có thể đại diện cho hai tenant và hai vùng danh tính độc lập.

### Issuer không phải endpoint

Issuer identifier xác định OP. Authorization endpoint, token endpoint và JWKS URI là các URL dịch vụ được metadata công bố. Client phải giữ cả hai khái niệm riêng: issuer dùng để xác định nguồn phát hành; endpoint dùng để thực hiện giao thức.

## 4. Discovery document chứa những gì?

Discovery document là JSON metadata. Ví dụ rút gọn:

~~~json
{
  "issuer": "https://id.example.org",
  "authorization_endpoint": "https://id.example.org/authorize",
  "token_endpoint": "https://id.example.org/token",
  "userinfo_endpoint": "https://id.example.org/userinfo",
  "jwks_uri": "https://id.example.org/.well-known/jwks.json",
  "response_types_supported": [
    "code"
  ],
  "subject_types_supported": [
    "public"
  ],
  "id_token_signing_alg_values_supported": [
    "RS256"
  ],
  "scopes_supported": [
    "openid",
    "profile",
    "email"
  ],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": [
    "S256"
  ]
}
~~~

Đây là ví dụ minh họa, không phải metadata bắt buộc phải giống hệt ở mọi OP. Một số trường là bắt buộc theo OIDC Discovery; một số trường là tùy chọn hoặc phụ thuộc khả năng provider. Client cần đọc đặc tả và profile mà mình triển khai thay vì giả định mọi trường luôn có mặt.

### Các trường thường gặp

| Trường | Ý nghĩa | Cách client sử dụng |
| --- | --- | --- |
| **issuer** | Định danh OP. | So khớp với issuer đã cấu hình và claim iss trong ID token. |
| **authorization_endpoint** | Endpoint bắt đầu authorization flow. | Dùng để tạo URL chuyển browser tới OP. |
| **token_endpoint** | Endpoint đổi authorization code hoặc grant thành token. | Gọi từ backend/client phù hợp, với PKCE và client authentication theo loại client. |
| **userinfo_endpoint** | Endpoint lấy claims về người dùng bằng access token. | Chỉ gọi khi cần và xác minh response theo OIDC. |
| **jwks_uri** | URL công bố JSON Web Key Set. | Lấy public key để xác minh chữ ký ID token. |
| **response_types_supported** | Response type OP hỗ trợ. | Chọn flow phù hợp; ưu tiên Authorization Code Flow theo thực hành hiện đại. |
| **subject_types_supported** | Các kiểu subject identifier. | Hiểu định danh public hoặc pairwise mà RP nhận được. |
| **id_token_signing_alg_values_supported** | Thuật toán ký ID token được công bố. | Chọn thuật toán nằm trong policy cho phép. |
| **scopes_supported** | Scope OP hỗ trợ nếu được công bố. | Chọn scope cần thiết; openid là scope cốt lõi của OIDC. |
| **token_endpoint_auth_methods_supported** | Phương thức xác thực client tại token endpoint. | Cấu hình đúng loại client và phương thức đã đăng ký. |
| **end_session_endpoint** | Endpoint logout của OP nếu được hỗ trợ. | Dùng theo RP-initiated logout profile và policy. |

### Metadata là mô tả khả năng, không phải lệnh phải bật mọi tính năng

Nếu metadata công bố nhiều response type hoặc thuật toán, client vẫn chỉ nên sử dụng phần giao nhau giữa khả năng provider và policy bảo mật của ứng dụng. Không tự động chọn thuật toán yếu hơn chỉ vì OP công bố nó.

## 5. Phân biệt OIDC Discovery với các cơ chế metadata khác

Các cơ chế liên quan có tên gần giống nhau nhưng phục vụ đối tượng khác nhau.

| Cơ chế | Mô tả | Dùng cho |
| --- | --- | --- |
| **OpenID Provider Configuration** | Metadata OIDC tại well-known URI. | OIDC RP khám phá OP và khả năng xác thực. |
| **OAuth 2.0 Authorization Server Metadata** | Metadata theo RFC 8414 cho authorization server. | OAuth client/resource ecosystem khám phá endpoint và khả năng AS. |
| **OAuth Protected Resource Metadata** | Metadata theo RFC 9728 mô tả protected resource. | Client/resource ecosystem khám phá cách tương tác với resource server. |
| **JWKS** | Tập khóa JSON, thường tại URI được metadata tham chiếu. | Xác minh chữ ký hoặc sử dụng khóa theo giao thức. |
| **Dynamic Client Registration** | Giao thức đăng ký client tại OP nếu được hỗ trợ. | Tạo/cập nhật client registration; không phải discovery. |
| **UserInfo** | Endpoint trả claims về subject đã xác thực khi có access token hợp lệ. | Lấy thông tin người dùng; không phải metadata. |

OIDC Discovery và OAuth Authorization Server Metadata có nhiều trường tương tự nhưng URI well-known và ngữ nghĩa tiêu chuẩn không hoàn toàn giống nhau. Một client cần biết mình đang triển khai giao thức nào và dùng đúng discovery convention.

### Discovery không phải dynamic registration

Discovery cho biết provider có endpoint và tính năng gì. Dynamic Client Registration, nếu được bật, là quy trình tạo client registration. Biết registration endpoint không có nghĩa bất kỳ ai cũng được phép đăng ký client; OP có thể yêu cầu access token, software statement, phê duyệt hoặc chính sách khác.

## 6. JWKS: khám phá khóa công khai để xác minh token

Discovery document thường công bố jwks_uri. Client dùng URI đó để lấy **JSON Web Key Set (JWKS)** — một tập các public key được biểu diễn theo JSON Web Key format.

Ví dụ rút gọn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "signing-key-2026-02",
      "alg": "RS256",
      "n": "base64url-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Các trường thường gặp:

- **kty:** loại khóa, ví dụ RSA hoặc EC.
- **use:** mục đích sử dụng, thường là sig cho ký.
- **kid:** key identifier để chọn khóa phù hợp.
- **alg:** thuật toán gắn với khóa nếu được công bố.
- **n, e:** tham số public key của RSA.
- **crv, x, y:** tham số public key của một số đường cong elliptic.

JWKS dùng để xác minh chữ ký, không phải nơi lấy private signing key. Client không được yêu cầu hoặc lưu private key của OP.

### Chọn khóa đúng

Khi xác minh ID token:

1. Đọc header đã parse nhưng chưa tin cậy của JWT để lấy kid và thuật toán được khai báo.
2. Chỉ chấp nhận thuật toán nằm trong allowlist của client và profile.
3. Tìm key trong JWKS đã lấy từ jwks_uri tin cậy.
4. Kiểm tra loại khóa, mục đích sử dụng và thuật toán tương thích.
5. Xác minh chữ ký.
6. Kiểm tra issuer, audience, thời hạn, nonce và các claim OIDC khác.

kid chỉ là gợi ý chọn khóa, không tự chứng minh khóa đáng tin. Không lấy URL jku hoặc x5u tùy ý từ JWT header để tải khóa. Nguồn khóa phải gắn với issuer đã tin cậy và metadata được xác minh.

## 7. Luồng discovery và xác minh ID token

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as OIDC RP
    participant OP as OpenID Provider
    participant JWKS as JWKS endpoint
    participant Browser
    RP->>RP: Chọn issuer từ trust configuration
    RP->>OP: GET /.well-known/openid-configuration
    OP-->>RP: Discovery metadata JSON
    RP->>RP: Kiểm tra issuer và endpoint policy
    RP->>JWKS: GET jwks_uri từ metadata
    JWKS-->>RP: JWKS public keys
    RP->>RP: Cache metadata và key theo issuer
    RP->>Browser: Redirect tới authorization_endpoint
    Browser->>OP: Authorization request + state + nonce + PKCE
    OP-->>Browser: Redirect callback với code và state
    Browser->>RP: Callback
    RP->>OP: Token request với code và PKCE verifier
    OP-->>RP: ID token
    RP->>RP: Chọn key theo kid và xác minh chữ ký
    RP->>RP: Kiểm tra iss, aud, exp, nonce và policy
    RP->>RP: Tạo local session mới
~~~

Thực tế client có thể lấy JWKS lần đầu khi cần xác minh token, thay vì ngay lập tức lúc tải discovery. Điều quan trọng là JWKS phải đến từ URI được lấy qua metadata của issuer đã tin cậy, và cache/refresh có chính sách rõ.

### Discovery không thay thế các kiểm tra OIDC

Ngay cả khi chữ ký ID token hợp lệ với một khóa từ JWKS, RP vẫn phải kiểm tra:

- iss khớp chính xác issuer đã cấu hình.
- aud chứa client ID của RP; xử lý azp khi profile yêu cầu.
- exp còn hiệu lực và iat hợp lý.
- nonce khớp giá trị RP đã lưu cho transaction.
- auth_time, acr, amr nếu chính sách xác thực yêu cầu.
- Các quy tắc về sub, c_hash, at_hash hoặc claim khác nếu flow/profile áp dụng.

Discovery chỉ giúp tìm thông tin cần thiết để giao tiếp và xác minh; quyết định chấp nhận đăng nhập vẫn dựa trên toàn bộ validation.

## 8. Thiết lập trust anchor và kiểm tra issuer

Một lỗi nguy hiểm là coi discovery document là đáng tin chỉ vì server trả về JSON hợp lệ. Attacker có thể dựng một endpoint discovery giả, công bố khóa do họ kiểm soát và phát ID token giả.

### Trust anchor là gì?

Trust anchor là cơ sở tin cậy ban đầu để client quyết định issuer nào được phép dùng. Có thể là:

- Issuer được cấu hình tĩnh bởi tổ chức.
- Danh mục tenant/provider đã được quản trị viên phê duyệt.
- Domain federation được xác minh qua quy trình tin cậy.
- Một cơ chế discovery danh tính có xác thực rõ ràng và policy allowlist.

Không để người dùng chưa xác thực tự nhập một URL issuer bất kỳ rồi backend tự fetch metadata và tin kết quả.

### Các kiểm tra cần thực hiện

- Discovery URL dùng HTTPS và TLS certificate được xác minh.
- issuer trong metadata khớp chính xác issuer được yêu cầu.
- ID token claim iss khớp issuer đã thiết lập trust.
- Endpoint URL hợp lệ theo policy và dùng TLS trong production.
- Redirect khi fetch metadata/JWKS được giới hạn và kiểm tra.
- Metadata được parse với giới hạn kích thước, thời gian và cấu trúc.
- Không tin trường endpoint hoặc khóa chỉ vì nó xuất hiện trong một response không được xác thực.

Một issuer khác nhau dù chỉ ở path vẫn có thể đại diện cho tenant khác. Không bỏ path hoặc dùng so sánh hostname-only để xác minh issuer.

## 9. SSRF và discovery động

Nếu backend cho phép người dùng hoặc tenant khai báo issuer URL, server sẽ thực hiện HTTP request tới URL đó để lấy discovery metadata và JWKS. Đây là bề mặt có thể bị lạm dụng thành **Server-Side Request Forgery (SSRF)**.

Attacker có thể thử khiến server truy cập:

- Loopback hoặc địa chỉ private trong mạng nội bộ.
- Cloud metadata endpoint.
- Dịch vụ quản trị chỉ mở trong mạng nội bộ.
- Host nội bộ thông qua DNS hoặc redirect.
- Địa chỉ IPv6 hoặc biểu diễn IP bất thường.
- Endpoint khác sau khi DNS record thay đổi.

### Kiểm soát SSRF

1. Ưu tiên issuer nằm trong allowlist hoặc tenant registry được quản trị.
2. Chỉ cho phép scheme HTTPS trong môi trường production.
3. Áp egress policy để backend chỉ truy cập mạng/provider được phép.
4. Chặn loopback, private, link-local, multicast và địa chỉ dành riêng theo policy; kiểm tra cả IPv4, IPv6 và hostname sau DNS resolution.
5. Giới hạn redirect hoặc tắt redirect; nếu cho phép, kiểm tra lại đích sau mỗi lần chuyển hướng.
6. Đặt timeout kết nối/đọc, giới hạn kích thước response và số lần retry.
7. Không gửi cookie, bearer token, client secret hoặc header nội bộ khi fetch metadata/JWKS.
8. Chống DNS rebinding bằng kiểm soát egress ở lớp kết nối/proxy, không chỉ kiểm tra hostname một lần.
9. Ghi audit issuer được thêm, ai phê duyệt và thời điểm metadata thay đổi.

Nếu sản phẩm cần hỗ trợ nhiều OP bên ngoài, hãy thiết kế quy trình onboard provider rõ ràng và tách việc xác minh issuer khỏi request đăng nhập thông thường. Không dùng URL do browser gửi để trực tiếp tạo một trust relationship mới.

## 10. Cache metadata và JWKS

Tải discovery document và JWKS ở mỗi lần đăng nhập hoặc mỗi request sẽ làm tăng độ trễ, tạo dependency mạng và khiến OP có thể bị gọi quá nhiều. Cache là cần thiết nhưng phải có chính sách.

### Cache theo issuer

- Cache metadata theo issuer đã xác minh, không dùng một cache key chung cho mọi tenant.
- Cache JWKS theo JWKS URI gắn với issuer.
- Tôn trọng HTTP cache headers như Cache-Control, ETag và Last-Modified nếu thư viện hỗ trợ.
- Có TTL tối đa nội bộ để giới hạn thời gian giữ metadata cũ.
- Làm mới có kiểm soát khi hết hạn hoặc khi gặp key chưa biết.
- Gộp các lần refresh đồng thời để tránh một đợt token có kid mới gây nhiều request giống nhau.
- Không để metadata do một tenant cung cấp ghi đè cache của tenant khác.

### Khi OP tạm thời không khả dụng

Client có thể tiếp tục dùng metadata/JWKS đã cache trong một khoảng stale-if-error được policy cho phép, nếu dữ liệu vẫn được xem là tin cậy và chưa có tín hiệu compromise. Tuy nhiên:

- Không tự động chấp nhận một key mới không xác minh được.
- Không kéo dài cache vô thời hạn.
- Không fail-open nếu metadata hoặc chữ ký không thể được kiểm tra.
- Có ngưỡng thời gian và mức rủi ro khác nhau cho login thông thường và thao tác nhạy cảm.
- Theo dõi lỗi fetch, cache age và tình trạng refresh.

Cache cải thiện khả năng chịu lỗi, nhưng metadata cũ có thể không phản ánh endpoint hoặc khóa vừa bị thu hồi. Cần cân bằng availability và khả năng thu hồi trust.

## 11. Xoay vòng signing key và xử lý kid chưa biết

OP có thể xoay signing key theo lịch hoặc khi có sự cố. Discovery document thường giữ nguyên jwks_uri, trong khi nội dung JWKS thay đổi theo thời gian.

### Quy trình xoay khóa an toàn

1. OP tạo khóa ký mới và công bố public key mới trong JWKS.
2. OP duy trì khóa cũ trong JWKS trong khoảng chuyển tiếp phù hợp.
3. OP bắt đầu ký token mới bằng khóa mới, với kid tương ứng.
4. RP nhận token có kid mới, refresh JWKS theo cơ chế có kiểm soát.
5. RP xác minh token bằng public key mới sau khi kiểm tra key type, use, alg và chữ ký.
6. Sau khi token cũ hết hạn và thời gian clock skew/rollover đã qua, OP có thể loại khóa cũ khỏi JWKS.
7. RP tiếp tục cache/refresh theo policy.

### Khi gặp unknown kid

- Không đoán khóa từ một issuer khác.
- Refresh JWKS một lần theo cơ chế coalescing/cooldown.
- Tìm lại kid trong JWKS mới.
- Nếu vẫn không có khóa phù hợp, từ chối token.
- Không tắt xác minh chữ ký và không chấp nhận token chỉ vì OP đang lỗi.
- Giới hạn tần suất refresh để attacker không thể gửi hàng nghìn JWT với kid ngẫu nhiên và buộc client gọi JWKS liên tục.

Không dùng kid như đường dẫn file, tên bảng hoặc biểu thức truy vấn không được kiểm soát. Xử lý kid như một giá trị dữ liệu không tin cậy.

## 12. Multi-tenant và nhiều issuer

Một ứng dụng SaaS có thể hỗ trợ nhiều tổ chức, mỗi tổ chức có OP/issuer riêng. Khi đó discovery và xác minh phải được gắn với tenant.

~~~mermaid
flowchart TD
    R["Login request"] --> L["Xác định tenant theo cấu hình đáng tin"]
    L --> I{"Issuer có được tenant cho phép?"}
    I -->|"Không"| D["Từ chối hoặc yêu cầu onboarding"]
    I -->|"Có"| C["Lấy discovery theo issuer"]
    C --> M["Cache metadata/JWKS theo issuer"]
    M --> V["Xác minh ID token"]
    V --> Q{"iss khớp issuer của tenant?"}
    Q -->|"Không"| X["Từ chối"]
    Q -->|"Có"| S["Ánh xạ identity bằng issuer + sub"]
    S --> A["Tạo session trong đúng tenant"]
~~~

### Quy tắc multi-tenant

- Xác định tenant từ domain/route hoặc cấu hình đã kiểm chứng; không chỉ tin tenant ID trong form.
- Mỗi tenant có danh sách issuer được phép và client registration phù hợp.
- Cache metadata và JWKS theo issuer/tenant.
- Identity key nên dùng cặp issuer + subject; không chỉ dùng sub hoặc email.
- Không chấp nhận ID token của tenant A trong transaction tenant B.
- Kiểm tra audience đúng client ID của RP trong tenant tương ứng.
- Tách scope, role mapping, callback và policy logout theo tenant.
- Khi tenant bị gỡ hoặc issuer thay đổi, có quy trình thu hồi trust và local session.

Cùng một giá trị sub có thể xuất hiện ở nhiều issuer mà không đại diện cùng một danh tính. Cũng có thể cùng email xuất hiện ở hai tenant; điều đó không đủ để tự động gộp tài khoản.

## 13. Những lỗi bảo mật thường gặp

| Lỗi | Tác động | Biện pháp |
| --- | --- | --- |
| Tin issuer do request chưa xác thực cung cấp | Attacker chọn OP giả và phát token giả. | Trust anchor, allowlist và onboarding provider. |
| Chỉ so sánh hostname của issuer | Tenant/path khác nhau bị coi là cùng issuer. | So khớp issuer chính xác theo OIDC. |
| Tải JWKS từ URL trong JWT header | SSRF hoặc attacker điều khiển khóa xác minh. | Dùng jwks_uri từ metadata tin cậy; bỏ qua URL tùy ý trong token. |
| Chấp nhận mọi thuật toán metadata công bố | Thuật toán yếu hoặc không tương thích policy được bật. | Allowlist thuật toán và key type. |
| Cache JWKS không giới hạn | Khóa cũ hoặc đã bị thu hồi tiếp tục được dùng. | TTL, refresh, stale policy và incident procedure. |
| Không hỗ trợ key rotation | Token ký bằng khóa mới bị từ chối. | Refresh unknown kid có giới hạn và overlap khóa. |
| Refresh JWKS cho mọi unknown kid | DoS/traffic amplification tới OP. | Cooldown, request coalescing và rate limit. |
| Tin endpoint từ metadata bất kỳ | SSRF hoặc gửi request tới host độc hại. | Trust issuer, egress controls, HTTPS và endpoint validation. |
| Redirect không kiểm tra khi fetch metadata | Request bị chuyển tới địa chỉ nội bộ hoặc host không tin cậy. | Tắt/giới hạn redirect và xác minh lại đích. |
| Dùng chung cache giữa các issuer | Key/metadata tenant này bị áp sang tenant khác. | Cache namespace theo issuer chính xác. |
| Coi discovery là xác thực | Client tạo phiên dù chưa xác minh ID token. | Thực hiện đầy đủ OIDC authentication và token validation. |
| Dùng metadata để tự động đăng ký client | Tạo client không được phê duyệt. | Tách discovery khỏi dynamic client registration. |

## 14. Ví dụ triển khai cho nền tảng học tập

Giả sử Learning Platform cho phép các trường đại học đăng nhập bằng IdP riêng. Mỗi trường có issuer đã được quản trị viên xác minh và gắn với một tenant.

### 14.1 Onboard một issuer

1. Quản trị viên tenant cung cấp issuer identifier qua quy trình onboarding.
2. Hệ thống kiểm tra issuer thuộc danh sách domain/provider được phép và xác minh quyền quản trị.
3. Backend lấy discovery document qua HTTPS với timeout, response-size limit và egress policy.
4. Backend kiểm tra issuer trong document khớp chính xác issuer đã yêu cầu.
5. Backend kiểm tra endpoint, thuật toán, response type và các khả năng tối thiểu mà ứng dụng cần.
6. Hệ thống lưu metadata đã kiểm chứng cùng thời điểm, version, cache policy và người phê duyệt.
7. Hệ thống lấy JWKS khi cần, kiểm tra key phù hợp và cache theo issuer.
8. RP đăng ký client/callback theo quy trình quản trị của OP; discovery không tự tạo client registration.

### 14.2 Người học đăng nhập

1. Người học chọn trường hoặc truy cập tenant đã được xác định.
2. Ứng dụng lấy issuer từ tenant registry.
3. RP dùng metadata đã cache hoặc refresh theo policy để tìm authorization endpoint.
4. RP tạo state, nonce và PKCE verifier, rồi chuyển browser tới OP.
5. OP xác thực người học và trả authorization code.
6. RP đổi code tại token endpoint được discovery công bố.
7. RP lấy kid từ ID token, chọn public key từ JWKS cache; nếu unknown kid, refresh có giới hạn.
8. RP xác minh chữ ký, issuer, audience, nonce, thời hạn và các claim theo OIDC.
9. RP ánh xạ danh tính bằng issuer + subject và kiểm tra tài khoản thuộc đúng tenant.
10. RP xoay session ID và tạo local session với quyền do Learning Platform quyết định.

### 14.3 Khi OP thay khóa

Nếu OP công bố khóa mới, RP refresh JWKS theo policy và xác minh token bằng khóa mới sau khi kiểm tra. Nếu OP bị nghi lộ signing key, quản trị viên có thể phải tạm dừng issuer, thu hồi trust, kết thúc local session liên quan và điều tra token đã phát hành. Cache không được giữ khóa bị compromise vô thời hạn chỉ để duy trì đăng nhập.

## 15. Kiểm thử discovery và JWKS

| Kịch bản | Hành vi kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Discovery document hợp lệ | Tải metadata từ issuer được cấu hình. | Parse thành công và issuer khớp chính xác. |
| Metadata có issuer khác | Thay trường issuer trong response. | Client từ chối metadata. |
| Discovery qua HTTP | Cấu hình issuer production dùng HTTP. | Từ chối theo policy HTTPS. |
| Thiếu trường cần thiết | Bỏ metadata bắt buộc theo profile đang dùng. | Client từ chối hoặc đánh dấu provider không tương thích. |
| Endpoint không hợp lệ | Metadata trỏ token/JWKS tới scheme hoặc host bị policy cấm. | Không sử dụng endpoint; ghi lỗi cấu hình. |
| Redirect tới mạng nội bộ | Metadata URL redirect tới loopback/private address. | Fetcher chặn đích và không truy cập mạng nội bộ. |
| Response quá lớn hoặc treo | Trả metadata vượt giới hạn hoặc không hoàn tất. | Timeout/size limit; không làm cạn tài nguyên. |
| JWKS hợp lệ | Cung cấp key tương thích với thuật toán allowlist. | Xác minh token thành công nếu các claim khác hợp lệ. |
| Unknown kid | Token dùng kid mới chưa có trong cache. | Refresh JWKS có giới hạn; xác minh nếu key mới hợp lệ. |
| Unknown kid không tồn tại | Refresh xong vẫn không có key. | Từ chối token. |
| JWKS có key không phù hợp | Key type/use/alg không tương thích. | Không chọn key đó. |
| Key rotation | OP công bố key mới, ký token mới. | RP cập nhật cache và xác minh theo quy trình. |
| Cache của hai tenant | Hai issuer có kid giống nhau nhưng public key khác. | Không dùng nhầm key giữa tenant. |
| DNS rebinding/SSRF | Host đổi sang địa chỉ private sau kiểm tra ban đầu. | Egress control ngăn truy cập đích nội bộ. |
| OP outage | Discovery/JWKS endpoint tạm thời không khả dụng. | Áp stale policy có giới hạn; không chấp nhận key chưa xác minh. |
| Token sai issuer | ID token ký đúng bằng key nhưng iss không khớp tenant. | RP từ chối. |
| Token sai audience | ID token không dành cho client hiện tại. | RP từ chối. |
| Discovery endpoint bị thay đổi | Metadata mới thay authorization/token/JWKS endpoint. | Áp policy refresh, audit và phê duyệt nếu thay đổi vượt trust policy. |

## 16. Checklist triển khai

- [ ] Issuer đến từ trust configuration hoặc quy trình onboarding được kiểm soát.
- [ ] Discovery URI được xây dựng đúng từ issuer identifier theo OIDC Discovery.
- [ ] Production chỉ dùng HTTPS và xác minh TLS.
- [ ] Metadata issuer khớp chính xác issuer được yêu cầu.
- [ ] Các endpoint được kiểm tra theo policy; không tải URL tùy ý từ request hoặc token header.
- [ ] Metadata và JWKS được cache theo issuer/tenant.
- [ ] Có TTL, refresh, cooldown, request coalescing và stale-if-error policy.
- [ ] Unknown kid chỉ kích hoạt refresh có giới hạn; không bỏ qua xác minh chữ ký.
- [ ] Thuật toán và key type nằm trong allowlist; kiểm tra use/alg/kid phù hợp.
- [ ] Có quy trình key rollover, key compromise và thu hồi trust.
- [ ] Có SSRF protection, egress control, redirect policy, timeout và response-size limit.
- [ ] Multi-tenant dùng issuer + subject, audience và cache riêng.
- [ ] Discovery được phân biệt với dynamic client registration, UserInfo và OAuth metadata.
- [ ] Sau discovery vẫn xác minh ID token đầy đủ: chữ ký, iss, aud, exp, nonce và policy.
- [ ] Có monitoring cho metadata age, JWKS refresh, unknown kid, lỗi TLS và provider outage.
- [ ] Có test cho metadata sai, endpoint độc hại, key rotation, issuer mismatch và outage.

## 17. Tự kiểm tra

**Câu 1.** OIDC Discovery giải quyết vấn đề gì?

**Đáp án:** Nó cho RP biết metadata của OP như issuer, authorization endpoint, token endpoint, JWKS URI và khả năng giao thức để client tích hợp theo cấu hình được công bố.

**Câu 2.** Tải được discovery document có nghĩa người dùng đã đăng nhập không?

**Đáp án:** Không. Discovery chỉ là khám phá cấu hình provider. Người dùng vẫn phải đi qua authorization/authentication flow và RP phải xác minh ID token.

**Câu 3.** Vì sao issuer trong metadata và claim iss cần khớp chính xác?

**Đáp án:** Issuer là định danh nguồn phát hành. So khớp hostname-only hoặc bỏ path có thể làm token từ tenant/provider khác được chấp nhận nhầm.

**Câu 4.** JWKS được dùng để làm gì?

**Đáp án:** JWKS công bố các JSON Web Key, thường là public key, để RP chọn khóa và xác minh chữ ký ID token theo issuer đã tin cậy.

**Câu 5.** Nếu JWT header chứa jku trỏ tới URL của attacker, RP có nên tải khóa từ đó không?

**Đáp án:** Không. RP phải dùng JWKS URI lấy từ discovery metadata của issuer được cấu hình tin cậy, không lấy nguồn khóa tùy ý từ token chưa xác minh.

**Câu 6.** Vì sao không nên refresh JWKS liên tục mỗi khi gặp kid lạ?

**Đáp án:** Attacker có thể gửi nhiều token với kid ngẫu nhiên để gây traffic và DoS. Chỉ refresh có giới hạn, coalesce request và từ chối nếu key vẫn không tồn tại.

**Câu 7.** Discovery và dynamic client registration khác nhau thế nào?

**Đáp án:** Discovery đọc metadata để biết provider hỗ trợ endpoint/tính năng nào. Dynamic client registration tạo hoặc cập nhật client registration và cần authorization riêng.

**Câu 8.** Rủi ro SSRF xuất hiện ở đâu trong discovery?

**Đáp án:** Backend có thể fetch issuer URL do người dùng cung cấp. Attacker có thể khiến server truy cập loopback, mạng private hoặc cloud metadata endpoint; cần allowlist, egress controls, DNS/redirect validation và giới hạn request.

**Câu 9.** Khi OP xoay signing key, RP nên xử lý thế nào?

**Đáp án:** OP công bố public key mới và có khoảng overlap phù hợp. RP refresh JWKS có giới hạn khi cần, chọn key theo kid và kiểm tra key/algorithm; không tắt chữ ký khi key chưa được tìm thấy.

**Câu 10.** Trong hệ multi-tenant, có thể cache JWKS chỉ theo kid không?

**Đáp án:** Không. Kid có thể trùng giữa các issuer. Cache và identity phải gắn với issuer/tenant; account identity thường dựa trên cặp issuer + subject.

## Ghi nhớ

**Discovery** giúp OIDC client tìm metadata của OpenID Provider và địa chỉ JWKS để biết cách khởi tạo flow, gọi endpoint và xác minh chữ ký. Nguồn tin cậy bắt đầu từ issuer đã được cấu hình hoặc onboarding; client phải so khớp issuer chính xác, kiểm tra endpoint và chỉ dùng public key lấy từ JWKS URI gắn với issuer đó.

Metadata/JWKS cần được cache theo issuer, refresh có giới hạn, hỗ trợ key rotation và xử lý outage theo policy. Không tin URL tùy ý từ request hoặc JWT header, không để discovery trở thành SSRF, không dùng chung cache giữa tenant và không nhầm discovery với xác thực hay dynamic registration. **Discovery cung cấp cấu hình để thiết lập trust; RP vẫn phải xác minh đầy đủ từng ID token và quyết định quyền truy cập theo chính sách của ứng dụng.**
