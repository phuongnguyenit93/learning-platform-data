# TLS và certificate validation

## 1. Vì sao xác minh chứng chỉ là một phần của bảo mật token?

Trong module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, access token và refresh token là credential có thể cấp quyền xác thực hoặc ủy quyền trong OAuth 2.0/OpenID Connect (OIDC). Một bearer access token có thể là JWT hoặc opaque, nhưng điểm chung quan trọng là: **bên sở hữu token có thể trình token để truy cập trong phạm vi và thời hạn được cấp**, nếu token không bị ràng buộc với người gửi.

Giả sử ứng dụng `sales-dashboard` gửi:

~~~http
GET /v1/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Nếu kết nối đến `orders.example.test` bị kẻ tấn công đứng giữa (*man-in-the-middle*, MITM) giả mạo, bearer token có thể bị đánh cắp **trước khi resource server kiểm tra bất kỳ claim nào**. Nếu ứng dụng có HTTPS nhưng **không xác minh chứng chỉ máy chủ đúng cách**, kẻ tấn công có thể đưa một chứng chỉ không đáng tin rồi chặn hoặc sửa traffic. Chỉ việc mã hóa đường truyền chưa đủ: client còn phải biết **đang mã hóa với đúng máy chủ**.

Trong chương **Token transport**, bài **TLS và certificate validation** tập trung vào:

1. TLS bảo vệ dữ liệu nào và điều gì TLS **không** giải quyết.
2. Kiểm tra chuỗi chứng chỉ theo trust anchor, hostname/SAN, hiệu lực thời gian, mục đích sử dụng và trạng thái thu hồi.
3. Cách bảo vệ các kết nối **client → authorization server**, **client → resource server**, **resource server → introspection/JWKS**, và các hop qua gateway/service mesh.
4. Phân biệt **HTTPS server authentication** với **mutual TLS (mTLS)** và access token ràng buộc chứng chỉ theo RFC 8705.
5. Cấu hình Java/Spring Security an toàn, tránh `trust-all` và vô hiệu hostname verification.
6. Vận hành certificate rotation, kiểm thử âm và xử lý sự cố mà không mở lỗ hổng token theft/replay.

> **Nguyên tắc:** Dùng TLS đúng phiên bản/cấu hình, xác minh danh tính peer bằng certificate validation và hostname verification, chỉ gửi token tới endpoint đã tin cậy. Sau TLS, **vẫn phải xác minh access token và phân quyền tại API**.

## 2. Ba mục tiêu của TLS trong hệ thống dùng token

TLS (Transport Layer Security) bảo vệ một kết nối giữa các endpoint được thiết lập đúng cách.

| Thuộc tính | TLS hỗ trợ gì? | Nếu thiếu hoặc triển khai sai |
| --- | --- | --- |
| **Confidentiality** (bí mật) | Mã hóa access token, refresh token, client secret, authorization code và response trong quá trình truyền | Kẻ quan sát mạng có thể đọc credential |
| **Integrity** (toàn vẹn) | Phát hiện thay đổi trái phép trong nội dung TLS records | Request/response có thể bị chèn hoặc sửa |
| **Peer authentication** (xác thực peer) | Client có thể xác minh chứng chỉ server; mTLS cho server xác minh cả chứng chỉ client | Attacker có thể giả endpoint token/introspection/API |
| **Fresh session keys** | Handshake hiện đại tạo khóa phiên cho kết nối | Giảm an toàn của phiên nếu dùng thiết lập lỗi thời |

TLS **không tự**:

- Kiểm tra `iss`, `aud`, `exp`, `nbf`, scope, chữ ký JWS, trạng thái opaque token hay quyền truy cập đơn hàng.
- Ngăn XSS lấy token từ browser, log ghi nguyên `Authorization` hoặc backend bị chiếm quyền.
- Làm cho bearer token không thể phát lại **sau khi đã bị đánh cắp ở endpoint**.
- Chứng minh end-user Alice là ai, trừ khi ứng dụng có cơ chế xác thực/ủy quyền phù hợp; chứng chỉ TLS của máy chủ chỉ xác thực peer/endpoint, không phải OAuth principal của người dùng.
- Tự bảo vệ traffic **sau điểm TLS termination** nếu proxy truyền HTTP plaintext đến backend.

### 2.1. Phân biệt TLS, JWT signature và token binding

Ba lớp bảo vệ trả lời ba câu hỏi khác nhau:

~~~text
TLS server authentication:
    Tôi đang nói chuyện với đúng auth.example.test / orders.example.test không?

JWT signature + claims validation:
    Token có do issuer tin cậy cấp, không bị sửa,
    còn hạn và dành cho orders-api không?

Sender-constrained token (DPoP hoặc mTLS-bound):
    Người gửi có chứng minh sở hữu khóa/chứng chỉ
    mà access token được ràng buộc không?
~~~

**JWT ký số hợp lệ không thay TLS**: JWT vẫn có thể bị chặn đọc trong đường truyền plaintext hoặc một TLS connection giả endpoint nếu client bỏ qua xác minh chứng chỉ. **TLS đúng không thay JWT validation**: token sai audience, hết hạn hoặc bị revoke phải tiếp tục bị từ chối.

### 2.2. Đường đi của một token trong kiến trúc thực tế

~~~mermaid
flowchart LR
    B["Browser / Mobile Client"] -->|"HTTPS + cert validation"| AS["Authorization Server"]
    B -->|"HTTPS + cert validation"| GW["API Gateway"]
    GW -->|"TLS/mTLS nội bộ theo policy"| RS["orders-api"]
    RS -->|"HTTPS + cert validation"| INT["Introspection endpoint"]
    RS -->|"HTTPS + cert validation"| JWKS["Trusted JWKS endpoint"]
    RS -->|"TLS/mTLS nội bộ nếu dùng"| DB["Backend service"]
~~~

Mỗi mũi tên là **một kết nối cần được đánh giá riêng**. Client xác minh cert của gateway không chứng minh gateway đã bảo vệ kết nối của nó đến `orders-api`. Tương tự, RS tải JWKS qua TLS đúng không chứng minh **chính các khóa trong JWKS** thuộc issuer được phép nếu URL JWKS là do JWT chưa xác minh chỉ định.

## 3. TLS handshake và certificate validation diễn ra ở đâu?

Khi client kết nối tới `https://auth.example.test/oauth2/token`, thư viện TLS thường:

1. Phân giải endpoint và thiết lập TCP (hoặc cơ chế transport được hỗ trợ như QUIC với HTTP/3).
2. Thương lượng TLS version/cipher suite cùng những tham số handshake cần thiết.
3. Nhận chứng chỉ server và tài liệu liên quan đến chuỗi tin cậy.
4. **Xác minh chứng chỉ theo trust configuration**: chain, trust anchor, tên máy chủ, thời gian, key usage/EKU, thuật toán và chính sách revocation nếu được bật.
5. Xác minh server chứng minh quyền sở hữu private key tương ứng trong handshake.
6. Chỉ sau khi handshake thành công, trao đổi HTTP request/response có chứa credential.

Ví dụ một luồng OAuth token request:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant S as auth.example.test
    C->>S: TLS ClientHello (SNI: auth.example.test)
    S-->>C: TLS handshake + certificate chain
    C->>C: Validate trust chain, SAN hostname, dates, policy
    alt Cert hợp lệ
        C->>S: Hoàn thành handshake an toàn
        C->>S: POST /oauth2/token (credential trong TLS)
        S-->>C: Access token / refresh token trong TLS
    else Cert không hợp lệ
        C--xS: Dừng kết nối, KHÔNG gửi credential
    end
~~~

Các chi tiết handshake TLS 1.2 và TLS 1.3 khác nhau; sơ đồ mô tả ranh giới bảo mật chứ không phải transcript chính xác từng bản tin. SNI (*Server Name Indication*) giúp server chọn chứng chỉ khi hosting nhiều tên miền, nhưng **SNI không phải kết quả xác minh hostname**. Client vẫn phải đối chiếu chứng chỉ nhận được với danh tính endpoint đã yêu cầu.

## 4. Certificate chain và trust anchors

Một chứng chỉ TLS server thường được CA (*Certificate Authority*) cấp; phía client xác minh đường tin cậy bằng chuẩn PKIX tới **trust anchor** mà hệ thống đã phê duyệt.

Ví dụ chain:

~~~text
Trust anchor: Company Root CA (nằm trong truststore được phép)
             ↓
Intermediate CA: Company Issuing CA
             ↓
Leaf certificate: auth.example.test
~~~

Khi xác minh, cần phân biệt:

| Thành phần | Vai trò | Điều cần tránh |
| --- | --- | --- |
| **Leaf certificate** | Xác định danh tính server và public key | Tin bất kỳ leaf self-signed do peer gửi |
| **Intermediate CA** | Chứng nhận leaf, nối đến trust anchor | Bỏ qua chain validation hoặc cho intermediate tùy ý làm root |
| **Root/trust anchor** | Nguồn tin cậy cấu hình ở client | Lấy CA root từ chính server không đáng tin rồi tự thêm vào truststore |
| **Truststore** | Tập CA/chứng chỉ mà ứng dụng tin | Dùng chung truststore quá rộng cho mọi hệ thống nhạy cảm mà không kiểm soát |

Một TLS peer có thể gửi chain thiếu intermediate; nhiều client sẽ thất bại nếu không dựng được chuỗi từ nguồn sẵn có. Đây là lỗi cần sửa ở **server certificate deployment** (cung cấp đủ intermediates) hoặc trust configuration đã được xác minh, không phải lý do tắt certificate verification.

### 4.1. Public CA và private enterprise CA

- Với endpoint công khai có chứng chỉ do public CA đáng tin cấp, Java có thể dùng **default truststore** đi kèm runtime/OS theo cấu hình.
- Với endpoint nội bộ dùng **private CA**, chỉ thêm đúng enterprise trust anchor đã được quản trị vào truststore cần thiết.
- Với môi trường dev/test, có thể dùng CA test **chỉ tin ở môi trường test**; không nhập test CA hoặc bypass TLS sang production.
- Nếu cần tin cả public CA và internal CA, thiết kế truststore có chủ đích; đừng ghi đè `cacerts` toàn hệ thống một cách không kiểm soát.

**Certificate pinning** có thể được dùng khi threat model yêu cầu, nhưng không phải thay thế phổ quát cho PKIX/hostname validation. Pinning sai dễ làm ứng dụng mất kết nối khi rotation; pin theo SPKI/public key cần kế hoạch backup pins, thay khóa và phân phối cấu hình an toàn. Đừng pin một leaf certificate duy nhất trong ứng dụng mobile mà không thiết kế vòng đời thay thế.

### 4.2. Trust anchor khác signing key của JWT

Trong hệ thống OAuth:

- **TLS truststore** dùng để tin certificate authority/peer TLS khi kết nối đến `https://auth.example.test`.
- **JWKS** của issuer chứa public keys mà resource server dùng để xác minh JWS của **JWT access token**.

Không được nhầm hai loại khóa. Một HTTPS endpoint có cert hợp lệ do CA công khai cấp **không có nghĩa** JWKS ở endpoint đó được phép xác minh token của mọi issuer. Ngược lại, JWT ký đúng với `kid` đã tin **không làm hợp lệ một TLS connection sai hostname**. Nguồn JWKS phải được thiết lập từ issuer/metadata tin cậy; không fetch `jku` chưa tin từ JWT để tự xây trust store.

## 5. Kiểm tra hostname: SAN quan trọng hơn CN

Client cần xác minh server certificate phù hợp **tên máy chủ của URL mà nó dự kiến kết nối**. Với chứng chỉ HTTPS hiện đại, hostname được mô tả trong extension **Subject Alternative Name (SAN)**, chẳng hạn:

~~~text
X509v3 Subject Alternative Name:
    DNS:auth.example.test
    DNS:login.example.test
~~~

Các điểm cần nhớ:

1. `https://auth.example.test` cần chứng chỉ có `DNS:auth.example.test` hoặc một SAN wildcard phù hợp quy tắc hostname verifier.
2. `https://api.example.test` **không được** chấp nhận chứng chỉ chỉ dành cho `auth.example.test`, dù cả hai thuộc cùng công ty.
3. Nếu kết nối bằng IP literal như `https://192.0.2.10`, việc xác minh cần SAN loại **IP address** thích hợp; một `DNS:192.0.2.10` không thể mặc nhiên được coi tương đương.
4. `CN` (Common Name) là cơ chế cũ cho identity; đừng dựa vào CN fallback như một chính sách bảo mật hiện đại khi SAN không có.
5. Wildcard như `*.example.test` không tự bao phủ `example.test` hoặc mọi cấp subdomain; phải theo quy tắc matching của thư viện, không tự xây matcher bằng `endsWith()`.

Ví dụ:

| URL client gọi | SAN trên leaf certificate | Kỳ vọng |
| --- | --- | --- |
| `https://auth.example.test` | `DNS:auth.example.test` | Khớp hostname (còn phải qua các kiểm tra khác) |
| `https://orders.example.test` | `DNS:auth.example.test` | Từ chối |
| `https://a.example.test` | `DNS:*.example.test` | Có thể khớp một nhãn theo quy tắc verifier |
| `https://deep.a.example.test` | `DNS:*.example.test` | Không khớp wildcard một nhãn |
| `https://192.0.2.10` | `DNS:auth.example.test` | Không khớp IP |
| `https://192.0.2.10` | `IP:192.0.2.10` | Có thể khớp IP, còn phải xác minh chain |

Nếu server trả cert sai vì không có SNI hoặc reverse proxy cấu hình nhầm, **sửa cert/SNI/hostname**. Không tắt hostname verifier, không “tạm” chuyển sang HTTP để token endpoint hoạt động.

### 5.1. URL nguồn phải cố định và được phê duyệt

Không chỉ kiểm tra cert cuối cùng: OAuth client/RS cần biết nó đang gọi **đúng endpoint** trước khi mở kết nối. Ví dụ:

~~~text
Token endpoint:        https://auth.example.test/oauth2/token
Revocation endpoint:   https://auth.example.test/oauth2/revoke
Introspection:         https://auth.example.test/oauth2/introspect
JWKS URI:              https://auth.example.test/oauth2/jwks
Resource API:          https://orders.example.test/
~~~

Đây là endpoint minh họa. Trong thực tế, cấu hình cần lấy từ **trusted issuer metadata/administrative configuration** và được kiểm tra nhất quán, không dùng URL do request hoặc JWT chưa xác minh tùy ý đưa vào. Kể cả HTTPS + cert hợp lệ, một URL do attacker kiểm soát như `https://attacker.example.test/collect` có thể có chứng chỉ hợp lệ **cho chính tên attacker** và vẫn thu thập token nếu ứng dụng gửi credential tới đó.

## 6. Thời hạn, thuật toán, EKU và revocation của chứng chỉ

Certificate validation không chỉ là kiểm tra tên miền:

| Kiểm tra | Mục đích | Khi thất bại |
| --- | --- | --- |
| **Validity period** (`notBefore`/`notAfter`) | Chứng chỉ chưa bắt đầu hoặc đã hết hạn? | Từ chối |
| **Signature/path validation** | Chain có chữ ký đúng và dẫn đến trust anchor hợp lệ? | Từ chối |
| **Basic Constraints** | Certificate có được dùng làm CA nếu là CA? | Từ chối chain sai vai trò |
| **Key Usage / Extended Key Usage** | Leaf phù hợp mục đích TLS server/client authentication? | Từ chối theo chính sách PKIX/TLS |
| **Algorithms/key strength** | Chữ ký/key/cipher tuân theo policy hiện đại? | Từ chối cấu hình yếu/cấm |
| **Name constraints/policy** | Chain có tuân ràng buộc tên/CA khi áp dụng? | Từ chối |
| **Certificate revocation** | Certificate bị CA thu hồi trước `notAfter`? | Áp chính sách CRL/OCSP và fail-mode đã thiết kế |

### 6.1. Hết hạn cert khác hết hạn token

Server certificate hết hạn không làm `exp` của JWT tự đổi; ngược lại JWT hết hạn không làm TLS certificate sai. Chúng là hai vòng đời riêng:

~~~text
TLS certificate notAfter: kiểm soát khả năng xác thực endpoint TLS
JWT exp:                 kiểm soát thời hạn chấp nhận JWT
Refresh token expiry:    kiểm soát khả năng xin access token mới
Client secret expiry:    kiểm soát xác thực OAuth client
~~~

Nếu cert của AS hết hạn, OAuth client **phải ngừng gửi credential qua kết nối không xác minh được**, dù hoạt động cấp token bị gián đoạn. Nếu cert của resource API hợp lệ nhưng JWT quá hạn, API vẫn phải từ chối JWT.

### 6.2. CRL, OCSP và giới hạn của revocation checking

Certificate revocation có thể được triển khai qua CRL, OCSP hoặc OCSP stapling theo khả năng của PKI, TLS stack và chính sách tổ chức. Tuy nhiên:

- **Không mặc định mọi JVM/browser kiểm tra revocation theo cùng cách**. Cấu hình, cache, network và fail-open/fail-closed khác nhau.
- OCSP/CRL responder có thể không truy cập được; phải xác định chính sách phù hợp với threat model và yêu cầu sẵn sàng.
- Stapling có thể giúp server gửi thông tin trạng thái phù hợp, nhưng client phải **thực sự kiểm tra** theo policy; việc server gửi dữ liệu không tự đảm bảo an toàn.
- Cert bị thu hồi không đồng nghĩa toàn bộ bearer tokens đã bị revoke ở AS; đó là những hệ thống trạng thái khác nhau.

Đối với kênh nhạy cảm như token endpoint, chính sách certificate revocation có thể chặt hơn các kết nối thông thường, nhưng phải đo tác động vận hành. Không viết một `TrustManager` tự chế bỏ qua mọi lỗi chỉ vì OCSP/CRL gây timeout.

## 7. TLS version, cipher suite và 0-RTT replay

Không nên dựa vào TLS 1.0/1.1 hoặc các cipher suite cũ để vận chuyển bearer tokens. Khi thiết kế mới, **ưu tiên TLS 1.3** và cho phép **TLS 1.2 với cipher suite hiện đại** nếu cần tương thích, theo chính sách an toàn của nền tảng và tổ chức.

| Thuộc tính | Cách tiếp cận |
| --- | --- |
| TLS version | Bật TLS 1.3; chỉ hỗ trợ TLS 1.2 khi có nhu cầu; tắt các phiên bản lỗi thời |
| Cipher suite | Ưu tiên AEAD, forward secrecy theo cấu hình TLS stack hiện đại; loại bỏ suite yếu và thuật toán cấm |
| Certificate key/signature | RSA/ECDSA và kích thước/thuật toán phù hợp chính sách PKI, tránh key/signature không đủ mạnh |
| Handshake errors | Từ chối kết nối khi không đàm phán được chính sách; không fallback sang HTTP |
| Session resumption | Có thể sử dụng theo TLS stack, nhưng không bỏ qua yêu cầu xác minh danh tính/endpoint |
| TLS 1.3 early data (0-RTT) | **Không xử lý token/grant-changing requests từ early data có thể bị replay** nếu không có cơ chế an toàn chống replay |

### 7.1. Vì sao 0-RTT đáng chú ý với token endpoint?

TLS 1.3 có khả năng gửi **early data (0-RTT)** trong một số tình huống session resumption, giúp giảm độ trễ nhưng dữ liệu này có những rủi ro **replay ở tầng ứng dụng** theo RFC 8446 và RFC 8470. Một kẻ tấn công có thể khiến một early-data request được xử lý nhiều lần trong những điều kiện nhất định.

Đối với:

- `POST /oauth2/token` đổi authorization code hoặc refresh token.
- `POST /oauth2/revoke` thay đổi trạng thái grant/token.
- Endpoint cấp token, token exchange hoặc thao tác có hiệu ứng bảo mật khác.

...phải cấu hình **không nhận/không xử lý early data thiếu bảo đảm chống replay**; server/proxy có thể từ chối early data và yêu cầu client gửi lại sau full handshake theo quy tắc giao thức. Với một số request đọc trạng thái, cũng nên phân tích rò rỉ/side effects riêng, không mặc định “GET luôn an toàn”.

**TLS 1.3 không tự làm mọi request idempotent.** Authorization code vẫn single-use, refresh token rotation vẫn phải atomic, và AS phải bảo vệ replay **cả khi không có 0-RTT**. Việc chặn 0-RTT giúp loại bỏ một đường replay bổ sung, không thay thế logic grant.

### 7.2. HTTP/2, HTTP/3 và stream multiplexing

HTTP/2/HTTP/3 có thể truyền nhiều request trên một kết nối bảo mật, nhưng mỗi HTTP request vẫn cần authorization riêng. Đừng cho rằng chỉ vì connection đã TLS-authenticated mà toàn bộ request trong connection có cùng OAuth user/scope. Gateway dùng connection pooling hay HTTP/2 multiplexing phải phân biệt bearer token và principal theo **request**, không chỉ theo socket.

## 8. TLS termination ở reverse proxy, API Gateway và service mesh

Trong production, HTTPS thường được kết thúc ở ingress/reverse proxy, sau đó traffic đi vào service nội bộ:

~~~mermaid
flowchart LR
    C["OAuth Client"] -->|"HTTPS; verify api.example.test"| G["Ingress / Gateway"]
    G -->|"mTLS hoặc TLS nội bộ"| S["orders-api"]
    S -->|"mTLS hoặc TLS nội bộ"| D["Domain backend"]
    G -.->|"Nếu dùng HTTP nội bộ: rủi ro plaintext"| R["Chỉ chấp nhận qua mạng cô lập nếu threat model cho phép"]
~~~

Khi gateway giải mã HTTPS, request bên trong (kể cả `Authorization` header) có thể tồn tại plaintext **trong bộ nhớ gateway**. Nếu gateway kết nối tiếp tới backend qua HTTP plaintext, token có thể bị quan sát trong mạng nội bộ hoặc sidecar/host bị xâm nhập.

### 8.1. End-to-end TLS hay hop-by-hop TLS?

Hai phương án thường gặp:

1. **TLS passthrough:** gateway chuyển TLS traffic mà không giải mã, backend trực tiếp xác thực server certificate/hoàn tất TLS; gateway hạn chế quan sát HTTP headers.
2. **TLS termination + re-encryption:** gateway kết thúc TLS từ client rồi **thiết lập kết nối TLS/mTLS mới** đến backend, với chính sách trust và hostname/service identity riêng cho hop đó.

Trong cả hai, mỗi hop đều có **trust boundary riêng**. Không được hiểu “người dùng thấy ổ khóa trên browser” là “mọi đoạn giữa gateway, service, database và AS đều được mã hóa”.

### 8.2. Khi dùng service mesh mTLS

Service mesh có thể:

- Cấp workload identities và chứng chỉ ngắn hạn cho các service.
- Thực hiện mTLS giữa sidecars/proxies.
- Xác thực workload peer và áp chính sách east–west traffic.

Tuy nhiên, ứng dụng vẫn cần phân quyền OAuth token theo `iss`, `aud`, `scope`, user/tenant/ACL khi thích hợp. **Workload mTLS chứng minh service identity**; nó không tự đại diện cho quyền của Alice trong access token. Mesh policy cũng không tự ngăn một service có quyền mạng sử dụng token sai audience.

Nếu sidecar kết thúc mTLS trước ứng dụng và chuyển identity qua header nội bộ, header đó phải được tạo bởi thành phần tin cậy, không thể bị client bên ngoài giả mạo. Không dựa vào `X-Client-Cert` hoặc `X-User` do request client tự gửi để cấp quyền.

### 8.3. Forwarded headers và spoofing

Sau TLS termination, backend có thể thấy `http://internal-service` dù client ngoài dùng HTTPS. Một số framework sử dụng `Forwarded` hoặc `X-Forwarded-Proto` để dựng URL, redirect, callback OAuth và quyết định Secure cookie.

Nguy hiểm xảy ra khi client tự gửi:

~~~http
X-Forwarded-Proto: http
X-Forwarded-Host: attacker.example.test
~~~

rồi backend tin ngay. Gateway phải **loại bỏ/ghi đè các forwarding headers do client không tin gửi**, backend chỉ tin một proxy chain allowlist. Với OAuth/OIDC, `redirect_uri` phải được xác minh theo giá trị đã đăng ký chặt chẽ tại AS, không lắp ghép từ header không đáng tin.

### 8.4. Không log bearer header ở điểm terminate TLS

Gateway và APM thường log URL, headers, body và lỗi. Vì TLS đã được giải mã tại gateway nên token có thể rơi vào logs:

~~~text
UNSAFE: Authorization: Bearer eyJhbGciOi...
UNSAFE: POST /oauth2/token body=refresh_token=...
~~~

Hệ thống cần redact `Authorization`, `Cookie`, `Set-Cookie`, `client_secret`, `code`, `code_verifier`, `access_token`, `refresh_token`, client assertion và credential khác ở **mọi** hop. TLS không bảo vệ token sau khi phần mềm đã ghi nó vào log.

## 9. OAuth endpoints: bảo vệ những kết nối nào?

| Kết nối | Credential/dữ liệu nhạy cảm | Yêu cầu chính |
| --- | --- | --- |
| Browser/client → **authorization endpoint** | Authorization code, session cookie, state, PKCE challenge, user login | HTTPS và origin/redirect validation; bảo vệ cookie/session |
| Client → **token endpoint** | Authorization code, PKCE verifier, client credentials, refresh token; token response | TLS + cert validation bắt buộc, endpoint tin cậy, không log body |
| Client → **resource server** | Bearer access token, business data | HTTPS, đúng host, JWT/introspection + audience/scope/ACL |
| RS → **JWKS endpoint** | Public keys để verify JWT | HTTPS + cert validation; issuer/JWKS source pinning; cache/rotation |
| RS → **introspection endpoint** | Access token cần introspect và RS client credentials | HTTPS + cert validation, xác thực RS, fail closed |
| Client → **revocation endpoint** | Refresh/access token và client authentication | HTTPS + cert validation; không rò token qua URL/log |
| RP ↔ **OIDC provider** | Discovery, authorization response, ID token, logout notification | Trust metadata, HTTPS, token/signature/issuer/audience checks riêng |
| AS ↔ **storage/HSM/KMS** | Grant/token state, signing operations, secret material | Kênh bảo vệ và identity theo kiến trúc; không lộ private key |

### 9.1. Token endpoint có chứng chỉ đúng nhưng URL sai vẫn nguy hiểm

Ví dụ ứng dụng lấy token URL từ input người dùng:

~~~text
Configured destination = userInput.tokenEndpoint
User supplies           = https://lookalike-auth.example/collect
TLS cert                = valid for lookalike-auth.example
~~~

TLS có thể **hoàn toàn hợp lệ cho hostname của attacker**, nhưng ứng dụng vẫn gửi refresh token hoặc client secret **tới endpoint sai**. Cần pin danh sách AS/token endpoints đã phê duyệt theo issuer/tenant/client registration; không làm SSRF và không cho attacker quyết định đích nhận token.

Điều tương tự áp dụng cho `jku`/`x5u` trong JOSE header chưa xác minh: một HTTPS URL có chứng chỉ hợp lệ **không chứng minh** khóa ở URL đó được ủy quyền xác minh token của issuer mà resource server tin cậy.

### 9.2. Redirect và HTTP downgrade

Khi gửi `Authorization: Bearer ...`, client **không nên tự động chuyển credential qua redirect đến host khác**. Dù thư viện HTTP có quy tắc loại bỏ `Authorization` khi cross-origin redirect, ứng dụng vẫn nên cấu hình redirect policy rõ:

- Không chấp nhận chuyển từ HTTPS sang HTTP rồi gửi token.
- Không chuyển bearer token, refresh token hoặc client secret sang origin/host chưa được tin cậy.
- Token endpoint thường nên sử dụng URL cố định, **không tự follow redirect** tới nơi khác khi gửi credential.
- Nếu hệ thống đổi hostname, cập nhật metadata/endpoint và trust configuration có kiểm soát thay vì dựa vào redirect mang credential.

Đừng đặt access token trong query string để “tránh mất Authorization header” khi redirect. URL có thể bị ghi ở browser history, reverse proxy, analytics, Referrer và nhiều nơi khác.

### 9.3. HSTS, Secure cookies và trình duyệt

**HTTP Strict Transport Security (HSTS)** giúp browser ghi nhớ chỉ dùng HTTPS cho origin được cấu hình sau khi nhận header từ nguồn an toàn; HSTS **không tự thay thế certificate validation** và không làm các Java HTTP clients tự có chính sách tương đương browser.

Với browser session/cookie:

- Dùng `Secure` để cookie không được gửi qua HTTP.
- Dùng `HttpOnly` khi cookie không cần đọc bằng JavaScript.
- Đặt `SameSite` và CSRF defense phù hợp vì cookie có thể được gửi tự động.
- Hạn chế XSS, token trong browser storage và CORS sai cấu hình.

**Cookie session là một credential khác bearer token trong header**, dù đều có thể bị đánh cắp. Việc chuyển sang cookie không giải quyết mọi vấn đề nếu ứng dụng bỏ CSRF, session expiry và quyền trên tài nguyên.

## 10. Server-authenticated TLS và mutual TLS không giống nhau

Trong HTTPS thông thường, **client xác minh chứng chỉ của server**. Trong **mutual TLS (mTLS)**, server còn yêu cầu và xác minh **chứng chỉ của client**, có thể dùng làm cơ sở nhận diện workload hoặc client.

~~~mermaid
flowchart LR
    A["OAuth Client"] -->|"Server-auth TLS: client verify server certificate"| B["Authorization/Resource Server"]
    C["OAuth Client có private key + cert"] -->|"mTLS: hai bên verify cert peer"| D["Authorization/Resource Server"]
    D --> E["Token binding/policy phải kiểm tra riêng"]
~~~

| Kiểu | Server được xác thực? | Client được xác thực bằng cert? | Token tự được sender-constrained? |
| --- | --- | --- | --- |
| TLS thông thường | Có, nếu client kiểm tra cert đúng | Không bắt buộc | **Không** |
| mTLS giữa client và AS | Có | Có, nếu AS validate client cert | **Chưa chắc**; phải xem profile/binding cấp token |
| mTLS giữa client và RS | Có | Có, nếu RS validate client cert | **Chưa chắc**; cần kiểm tra access token ↔ cert binding |
| mTLS service mesh | Có peer identity giữa workloads nếu cấu hình đúng | Có tại mesh/proxy | Không tự ràng buộc OAuth token với cert của end-user/client |

### 10.1. mTLS client authentication ở token endpoint

RFC 8705 mô tả các cách dùng mutual TLS cho OAuth 2.0, bao gồm cơ chế xác thực client và access token ràng buộc chứng chỉ. Khi AS dùng mTLS client authentication, AS phải xác minh chứng chỉ client theo phương thức/profile đã đăng ký (PKI-based hoặc self-signed client certificate method theo RFC), cùng client identity và policy.

Chỉ “client gửi một certificate” không đủ: server phải chứng minh handshake mTLS tương ứng private key, xác minh chain hoặc certificate identifier đã đăng ký và xác định đúng OAuth client. **Đừng** tin giá trị `client_cert` trong request body/header tùy ý thay vì chứng chỉ TLS peer được xác minh ở trust boundary.

### 10.2. Certificate-bound access token theo RFC 8705

AS có thể cấp access token ràng buộc với certificate của client. Với JWT access token, profile có thể biểu diễn binding ở claim `cnf`:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "service-inventory",
  "aud": ["inventory-api"],
  "scope": "inventory.read",
  "exp": 1795400300,
  "cnf": {
    "x5t#S256": "<base64url-encoded-certificate-thumbprint>"
  }
}
~~~

`x5t#S256` trong ví dụ là thumbprint SHA-256 của DER-encoded client certificate được biểu diễn Base64url theo profile; đây **không phải** giá trị tùy ý do client gửi trong header.

Khi RS nhận access token certificate-bound:

1. Xác minh access token JWT hoặc opaque introspection từ issuer/AS tin cậy; kiểm tra `aud`, `exp`, scope và quyền.
2. Xác minh mTLS connection và **client certificate thực sự được trình** trên kết nối được tin.
3. Tính certificate thumbprint/đọc binding metadata theo profile và so khớp với `cnf` của access token.
4. Từ chối nếu token hợp lệ nhưng client gửi request không có certificate hoặc certificate **khác** với token đã ràng buộc.

Token này không thể bị phát lại chỉ bằng cách sao chép chuỗi bearer token nếu attacker không có private key/certificate phù hợp. Tuy nhiên, **token còn cần TTL và audience đúng**; client hợp lệ sở hữu key không được dùng token dành cho API A tại API B.

### 10.3. Trường hợp TLS termination gây mất binding

Nếu ingress terminates mTLS, backend không trực tiếp thấy certificate peer. Một số kiến trúc truyền identity/certificate fingerprint qua header nội bộ, nhưng chỉ được tin khi:

- Ingress đã **xác minh mTLS client certificate**, không chỉ nhận PEM tự khai.
- Header do ingress tạo và **ghi đè** mọi header cùng tên từ client.
- Kết nối ingress → backend có authentication/integrity (ví dụ mTLS), backend chỉ tin ingress được phê duyệt.
- Backend có cách kiểm tra rằng certificate identity được truyền thuộc **đúng request và đúng token binding**.

Không cho một HTTP client bên ngoài tự gửi:

~~~http
X-Client-Cert-Thumbprint: <arbitrary-value>
~~~

rồi dùng header đó để “thỏa mãn” `cnf`. Đây là lỗi trust boundary rất nghiêm trọng.

### 10.4. So sánh với DPoP

DPoP (RFC 9449) dùng proof ký ở lớp HTTP để chứng minh sở hữu private key được ràng buộc vào access token. **DPoP không yêu cầu mTLS** nhưng vẫn yêu cầu TLS server authentication khi gửi token đến AS/RS và xác minh `htu`, `htm`, `iat`, `jti`/nonce, `ath`, key binding theo profile.

| Cơ chế | Ràng buộc token với | Vị trí proof | Phụ thuộc đặc biệt |
| --- | --- | --- | --- |
| Bearer token thông thường | Không ràng buộc người gửi | Chỉ trình token | Token lộ có thể bị sao chép/phát lại |
| mTLS certificate-bound | Chứng chỉ client/private key | TLS handshake | TLS termination và cert binding phải khớp |
| DPoP-bound token | Public key của DPoP proof | DPoP HTTP header/JWS proof | RS/AS phải verify replay protection và request binding |

TLS, mTLS và DPoP không nên bị trộn thành “bật HTTPS là đã proof-of-possession”. HTTPS có cert server đúng **chỉ là điều kiện nền** để vận chuyển credential an toàn.

## 11. Java/Spring: sử dụng certificate validation an toàn

Trong Java, nhiều ứng dụng dùng JVM truststore và TLS implementation mặc định để xác minh HTTPS server. Cách tiếp cận an toàn là **giữ mặc định xác minh**, cấu hình trust anchors và endpoint hợp lệ, rồi bổ sung đúng chính sách mTLS nếu cần. **Không tự viết `X509TrustManager` chấp nhận mọi chứng chỉ hoặc `HostnameVerifier` luôn trả `true`.**

### 11.1. Java HttpClient: kết nối HTTPS với truststore mặc định

Ví dụ Java 17+ tải JWKS từ endpoint đã được quản trị:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class TrustedJwksClient {

    public static String fetchJwks() throws Exception {
        URI jwksUri =
                URI.create("https://auth.example.test/oauth2/jwks");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(jwksUri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Trusted JWKS endpoint is unavailable");
        }
        return response.body();
    }
}
~~~

**Điểm an toàn của ví dụ:**

- URL `https://auth.example.test/oauth2/jwks` được cấu hình cố định, **không** lấy từ `jku` trong JWT chưa xác minh.
- `java.net.http.HttpClient` sử dụng TLS/HTTPS certificate validation mặc định của runtime, bao gồm kiểm tra danh tính endpoint ở chế độ chuẩn, miễn là ứng dụng không thay thế bằng cấu hình TLS không an toàn.
- Tắt tự follow redirect để một response từ endpoint tin cậy không tự điều hướng sang URL khác.
- Có connect/request timeout để tránh giữ request vô hạn.

**Tải JWKS qua HTTPS đúng chưa đủ:** Resource server vẫn phải ràng buộc JWKS với đúng issuer và policy thuật toán, cache/rotation, `kid`, signature validation, `iss`, `aud`, `exp` và scope. Trên thực tế, nên dùng JWT/JWK decoder được framework hỗ trợ thay vì tự triển khai verifier JWS.

### 11.2. Spring Security Resource Server dùng issuer tin cậy

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Khi dùng `issuer-uri`, Spring Security có thể dùng issuer metadata để tìm JWKS theo cơ chế framework hỗ trợ. Kết nối discovery/JWKS là **TLS client** và phải xác minh chứng chỉ server. Nếu AS dùng private CA, ứng dụng cần cấu hình truststore thích hợp thay vì cài `trust-all`.

**Lưu ý:** Cấu hình issuer không tự bảo đảm audience. Resource server còn phải kiểm tra `aud` dự kiến của API, thời gian, scope và quyền nghiệp vụ. Trong hệ thống nhiều issuer, chỉ cho phép các issuer đã được đăng ký/kiểm soát; không dùng `iss` chưa xác minh để tự gọi một URL chưa được cấp quyền.

### 11.3. Spring RestClient với JDK HttpClient được cấu hình chặt

Ví dụ dùng Spring Framework 6.1+:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

public final class OrdersApiClientFactory {

    public static RestClient create() {
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        JdkClientHttpRequestFactory requestFactory =
                new JdkClientHttpRequestFactory(httpClient);

        return RestClient.builder()
                .baseUrl("https://orders.example.test")
                .requestFactory(requestFactory)
                .build();
    }
}
~~~

Khi sử dụng:

~~~java
String response = ordersClient.get()
        .uri("/v1/orders")
        .headers(h -> h.setBearerAuth(validatedAccessToken))
        .retrieve()
        .body(String.class);
~~~

Biến `validatedAccessToken` là credential được token manager lấy và giữ an toàn, **không phải chuỗi hardcode**; client phải bảo đảm token dành cho `orders-api` và đúng scope. Do `setBearerAuth` gửi token trên request, tuyệt đối không để caller thay `baseUrl` thành host tùy ý hoặc tùy tiện gửi token qua cross-origin redirect. Cần kiểm tra phiên bản Spring và HTTP client cụ thể; một số factory/framework có chính sách timeout/redirect khác nhau.

### 11.4. Truststore tùy chỉnh cho private CA

Với nội bộ sử dụng enterprise CA, có thể tạo truststore PKCS#12 chỉ chứa CA mà ứng dụng được phép tin. Java minh họa:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class EnterpriseTls {

    public static SSLContext create(
            Path truststorePath,
            char[] truststorePassword) throws Exception {

        KeyStore trustedCAs = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(truststorePath)) {
            trustedCAs.load(in, truststorePassword);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustedCAs);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);
        return context;
    }
}
~~~

Khi cấu hình:

~~~java
SSLContext context = EnterpriseTls.create(
        Path.of("/secure/config/company-truststore.p12"),
        truststorePasswordFromSecretManager);

HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
~~~

Đây là **server-auth TLS client** với truststore riêng. Không có code nào bỏ qua trust chain. Hostname verification vẫn phải được duy trì bởi HTTPS client: **đừng** dùng system property tắt endpoint identification hoặc `SSLParameters` vô hiệu hóa hostname verification. Các đường dẫn, mật khẩu và CA được dùng trong ví dụ phải được cấp phát từ cấu hình/secret manager bảo vệ.

**Một chi tiết vận hành quan trọng:** Khi truyền một truststore riêng vào `TrustManagerFactory`, tập CA tin cậy có thể **chỉ** bao gồm CA trong truststore đó thay vì tự kết hợp default public CAs. Nếu ứng dụng cũng phải gọi endpoint public, hãy thiết kế rõ các truststores/HTTP clients theo từng nhóm endpoint, không thêm mọi CA vào một kho tin quá rộng.

### 11.5. Thêm client certificate cho mTLS (không tắt server verification)

mTLS client vừa cần **client private key + certificate chain** để trình cho server, vừa cần **truststore** để xác minh server. Ví dụ:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class MutualTlsFactory {

    public static SSLContext create(
            Path clientIdentityP12,
            char[] clientKeyPassword,
            Path serverTruststoreP12,
            char[] truststorePassword) throws Exception {

        KeyStore clientIdentity = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(clientIdentityP12)) {
            clientIdentity.load(in, clientKeyPassword);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(clientIdentity, clientKeyPassword);

        KeyStore trustedServers = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(serverTruststoreP12)) {
            trustedServers.load(in, truststorePassword);
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustedServers);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
                kmf.getKeyManagers(),
                tmf.getTrustManagers(),
                null);
        return context;
    }
}
~~~

Sử dụng `SSLContext` này với một HTTPS client có hostname verification chuẩn. Private key/certificate phải do PKI/workload identity được quản lý và không commit vào repository. Mật khẩu private key/truststore được lấy từ secret manager hoặc giải pháp tương đương; giới hạn quyền đọc các file PKCS#12.

Nếu mTLS client cert được cấp lại trong khi token còn hạn, **certificate-bound access token có thể cần được cấp lại** vì thumbprint ràng buộc với cert cũ. Việc rotation chứng chỉ cần được phối hợp với token refresh/re-issuance; không cho phép verifier bỏ so `cnf` chỉ vì cert đã đổi.

### 11.6. Anti-pattern cần loại bỏ trong code review

~~~java
// KHÔNG TRIỂN KHAI: minh họa sai về mặt bảo mật
HostnameVerifier unsafe = (hostname, session) -> true;
// Hoặc X509TrustManager mà checkServerTrusted(...) để trống.
// Hoặc đặt global property để bỏ HTTPS hostname verification.
~~~

Đây là **mẫu cần tìm và loại bỏ**, không phải code hướng dẫn sử dụng. Cả “trust all certificates” lẫn “accept any hostname” đều vô hiệu hóa một phần cốt lõi của TLS authentication. Nếu cert test self-signed gây lỗi, phải đưa CA test hợp lệ vào truststore **chỉ của môi trường test** và triển khai cert đúng SAN, không thêm ngoại lệ “tạm thời” rồi để lại production.

## 12. Kiểm tra kết nối bằng công cụ mà không làm lộ token

Công cụ dòng lệnh giúp chẩn đoán chain, SAN và TLS handshake trước khi thử gửi credential. Dùng endpoint thử nghiệm, không in bearer token thật vào terminal history hoặc support ticket.

### 12.1. OpenSSL kiểm tra hostname và chain

~~~bash
openssl s_client \
  -connect auth.example.test:443 \
  -servername auth.example.test \
  -verify_hostname auth.example.test \
  -verify_return_error
~~~

Nếu sử dụng private CA, thêm CA bundle đáng tin đã được cấp:

~~~bash
openssl s_client \
  -connect auth.example.test:443 \
  -servername auth.example.test \
  -verify_hostname auth.example.test \
  -verify_return_error \
  -CAfile company-root-ca.pem
~~~

Lưu ý: `openssl s_client` nếu không dùng tùy chọn xác minh đúng có thể thiết lập kết nối **dù certificate validation lỗi** để phục vụ debug. Vì vậy “kết nối được” không đồng nghĩa cert hợp lệ. Cần kiểm tra kết quả verification, SAN, chain và kiểm thử lại bằng **runtime Java thực tế** vì OpenSSL và JSSE có thể sử dụng truststores/chính sách khác nhau.

### 12.2. curl xác minh endpoint với CA phù hợp

~~~bash
curl --cacert company-root-ca.pem \
  --fail-with-body \
  --max-time 10 \
  https://auth.example.test/.well-known/openid-configuration
~~~

Chỉ sử dụng URL discovery nếu nó thuộc issuer đã được phê duyệt. Không dùng `curl -k`/`--insecure` để đưa client secret, RT hoặc access token qua kết nối có certificate validation bị tắt. Nếu `curl` chạy được nhưng Java không chạy được, kiểm tra CA store, hostname verification, proxy, SNI, TLS versions và môi trường deployment, **không lập tức kết luận Java bị lỗi bảo mật**.

### 12.3. Kiểm tra truststore mà không xuất private key

~~~bash
keytool -list -v \
  -storetype PKCS12 \
  -keystore company-truststore.p12
~~~

`keytool` có thể yêu cầu mật khẩu. Không đặt mật khẩu trực tiếp trong lệnh có thể bị lưu history hoặc process list. Khi kiểm tra leaf certificate, có thể xem SAN, validity và issuer mà không xuất secret; private key vẫn phải được bảo vệ.

### 12.4. Kết quả cần được kiểm tra

1. Chứng chỉ còn trong khoảng `notBefore`–`notAfter` và chain về đúng trust anchor.
2. SAN chứa đúng hostname của **URL mà ứng dụng gọi**.
3. Client đã thương lượng TLS version/cipher theo policy.
4. Không có HTTP downgrade hoặc redirect bất ngờ tới host khác.
5. Proxy/backend chain được bảo vệ theo thiết kế, không chỉ hop ngoài.
6. Không có raw token trong command history, log hay diagnostic output.

## 13. Vận hành certificate rotation và sự cố PKI

Certificate và CA có vòng đời độc lập với OAuth access/refresh token. Một hệ thống phát hành JWT có thể dùng cùng AS nhiều năm nhưng TLS leaf certificate được thay mỗi vài tháng theo chính sách PKI.

### 13.1. Kế hoạch rotation bình thường

1. Theo dõi `notAfter` và cảnh báo sớm trước khi chứng chỉ hết hạn; dùng hệ thống inventory cho AS, JWKS, introspection, revocation, gateway, service mesh.
2. Cấp chứng chỉ mới với **SAN, EKU, chain và thuật toán phù hợp** cho từng endpoint.
3. Nếu thay intermediate/root CA, phân phối trust anchor mới **qua kênh quản trị đáng tin** trước khi chuyển server sang chain mới, nếu policy cho phép giai đoạn overlap.
4. Triển khai cert/chain và private key mới an toàn; tránh ghi private key trong log, artifacts hoặc image layer.
5. Kiểm thử certificate validation từ **các client thực tế** (Java runtime, service mesh, mobile, proxy) trước và sau cutover.
6. Thu hồi/loại bỏ cert và trust anchor cũ theo kế hoạch; không giữ CA cũ vô hạn để “tránh lỗi”.

### 13.2. Root CA compromise khác leaf certificate hết hạn

Nếu leaf cert hết hạn thông thường, cần gia hạn/triển khai cert mới. Nếu **private key của leaf hoặc CA bị lộ**, có thể cần revoke cert, rotate key, cập nhật truststore, kiểm tra logs và khởi động incident response. Trong thời gian bị nghi MITM, cần cân nhắc **credential đã có thể bị lộ**, bao gồm RT, client secret và bearer AT; rotation/revocation credential phải được xử lý riêng, vì sửa TLS cert **không xóa bản sao token attacker đã lấy được**.

Nếu CA nội bộ bị compromise, việc chỉ cấp lại leaf bằng **chính CA đó** có thể không đủ; phải xem xét trust anchors và độ tin cậy toàn chuỗi. Thay CA cũng có thể ảnh hưởng mTLS workloads và TLS-bound tokens, cần phối hợp AS, RS, service mesh và client.

### 13.3. Không “fail open” khi cert hết hạn

Khi AS certificate hết hạn hoặc hostname không khớp, client nên **dừng gửi token/secret** và ghi cảnh báo vận hành không chứa credential. Không áp ngoại lệ `trust-all` cho một môi trường production bị lỗi để “chạy tạm”. Nếu cần duy trì dịch vụ, dùng một endpoint/certificate dự phòng đã được phê duyệt từ trước, với trust/issuer/redirect policy tương ứng.

### 13.4. Observability an toàn

Nên theo dõi:

- Ngày hết hạn, issuer CA, fingerprint của cert public (không phải private key), chain health và hostname coverage.
- Tỷ lệ TLS handshake failure, unknown CA, expired certificate, name mismatch, protocol/cipher negotiation failures.
- Số lần TLS/mTLS client-auth failure theo workload/service, không đưa raw token vào metrics labels.
- Tỷ lệ lỗi fetch trusted JWKS, introspection timeout và token endpoint failure, phân biệt lỗi TLS với lỗi token invalid.
- Độ sẵn sàng của cert rotation automation, secret delivery và truststore reload.

Khi lỗi xác minh cert, log một **mã nguyên nhân không nhạy cảm** cùng endpoint id/correlation id. Không log full HTTP headers, RT, token response, client private key hay password truststore để tìm lỗi.

## 14. Chẩn đoán đúng lớp lỗi: TLS khác OAuth token validation

Khi request gọi `orders-api` hoặc `/oauth2/token` thất bại, phải biết request đã đi qua TLS handshake chưa. Không phải lỗi nào cũng là `401 invalid_token`.

| Triệu chứng | Lớp lỗi thường gặp | Cách khắc phục đúng |
| --- | --- | --- |
| `SSLHandshakeException: PKIX path building failed` | Không dựng được chain tới CA tin cậy | Kiểm tra cert chain, intermediate và truststore đúng môi trường |
| `No subject alternative DNS name matching ...` | Certificate SAN không khớp hostname | Cấp/deploy cert đúng SAN, kiểm tra URL/SNI |
| Certificate expired / not yet valid | Chứng chỉ ngoài khoảng hiệu lực, hoặc đồng hồ sai | Gia hạn cert và đồng bộ clock; không tắt validation |
| Handshake không tìm được protocol/cipher chung | TLS policy/version/cipher mismatch | Cấu hình TLS 1.2/1.3 phù hợp ở hai phía |
| mTLS client certificate required/unknown | Server yêu cầu client certificate nhưng client không có/cert không tin | Kiểm tra client identity, certificate chain, EKU và AS registration |
| HTTP `401` với `invalid_token` | HTTP request đã tới RS, access token không hợp lệ | Kiểm tra issuer, audience, signature/introspection, expiry, profile |
| HTTP `403` với `insufficient_scope` | Token có thể hợp lệ nhưng thiếu quyền | Xin quyền hợp lệ hoặc sửa policy, không tắt TLS |
| HTTP `429` hoặc `5xx` tại token endpoint | Quota hoặc lỗi AS/proxy sau/ngoài TLS | Theo retry policy/grant, không retry mù quáng credential single-use |
| JWKS fetch lỗi | Không tải được khóa từ endpoint tin cậy | Kiểm tra truststore, hostname, network và JWKS cache/rotation |
| Introspection timeout/TLS failure | RS không xác minh được opaque token | Fail closed, không dùng `active:true` mặc định |

### 14.1. “Cert của chúng tôi đúng” có thể chưa đủ

Nếu người vận hành mở `https://auth.example.test` trên laptop và browser hiển thị kết nối an toàn, chưa chắc Java Pod ở production cũng tin endpoint:

- Laptop và Pod có thể sử dụng **khác truststore**.
- Pod có thể có runtime Java cũ, thiếu intermediate/private root hoặc dùng DNS/proxy khác.
- Load balancer có thể phân phối đến **một node** chưa triển khai cert mới.
- URL Java dùng IP hoặc alias khác hostname browser đã kiểm tra.
- mTLS ingress/server có thể yêu cầu client certificate trong khi browser chỉ kiểm tra server certificate.

Hãy kiểm thử từ **đúng môi trường và HTTP/TLS client library**. Không chấp nhận cách xử lý “fix nhanh” là `TrustManager` trống hoặc bật global trust-all.

### 14.2. Không biến lỗi TLS thành một đường fallback không an toàn

Lỗi kiểm tra certificate không được khiến ứng dụng tự:

1. Thử lại URL `http://...` cùng token/secret.
2. Chuyển credential sang host khác do server redirect không được phê duyệt.
3. Tải CA certificate từ URL vừa thất bại rồi thêm vào truststore.
4. Bỏ hostname verification cho riêng endpoint “vừa gặp sự cố”.
5. Coi opaque token `active:true` hoặc JWT hợp lệ chỉ vì không thể gọi JWKS/introspection.

**Fail closed** nghĩa là không cấp quyền khi thiếu bằng chứng xác thực đáng tin. Hệ thống có thể trả lỗi vận hành phù hợp thay vì 401 khi không truy cập được AS, nhưng không được coi sự cố TLS là xác thực thành công.

## 15. Bộ kiểm thử âm và kiểm thử tích hợp cho TLS/certificate

Thiết lập môi trường test với CA và cert riêng. Mỗi ca nên quan sát **kết quả handshake, số lần credential được gửi, các HTTP requests đã đến backend và trạng thái token**, không chỉ kiểm tra exception type. Tuyệt đối không thử tắt TLS verification trên production để mô phỏng attacker.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T01 | HTTPS endpoint với chain, SAN và thời hạn hợp lệ | Kết nối thành công, HTTP request tiếp tục |
| T02 | Leaf cert self-signed không có trong truststore | TLS client từ chối trước khi gửi token |
| T03 | Intermediate CA không được dựng/thiếu và client không có | TLS client từ chối; sửa chain thay vì trust-all |
| T04 | Root CA không được phép | Từ chối, không tự thêm CA do server cung cấp |
| T05 | Cert chỉ có `DNS:auth.example.test` nhưng URL là `orders.example.test` | Từ chối hostname mismatch |
| T06 | URL dùng IP, cert chỉ có DNS SAN | Từ chối khi không có IP SAN đúng |
| T07 | Wildcard `*.example.test` được dùng cho `deep.api.example.test` | Từ chối theo hostname verifier |
| T08 | Chứng chỉ đã hết hạn `notAfter` | TLS handshake/certificate validation thất bại |
| T09 | Chứng chỉ chưa tới `notBefore` | Từ chối |
| T10 | Cert có EKU/key usage không hợp mục đích server auth | Từ chối theo PKIX/TLS policy |
| T11 | Chain dùng algorithm/key yếu bị policy cấm | Từ chối |
| T12 | Cert đã bị revoke, revocation checking bật và có dữ liệu đáng tin | Từ chối theo revocation policy |
| T13 | OCSP/CRL responder lỗi | Kết quả đúng fail-mode được thiết kế; không trust-all |
| T14 | TLS version/cipher không giao nhau | Kết nối thất bại, không fallback HTTP |
| T15 | Proxy trả cert sai do SNI hoặc một backend chưa rotate | Phát hiện theo hostname/chain, không gửi credential |
| T16 | `POST /oauth2/token` bị gửi qua HTTP hoặc HTTPS downgrade | Client/chính sách chặn, không phát RT/client secret |
| T17 | Token endpoint trả 302 sang host lạ | Không tự gửi token/credential sang host lạ |
| T18 | JWKS URL lấy từ `jku` attacker nhưng có TLS cert hợp lệ | Không fetch vì nguồn khóa chưa được trust |
| T19 | OAuth metadata `token_endpoint` do issuer chưa được phê duyệt quảng bá | Không tự tin URL; từ chối theo trust policy |
| T20 | TLS ở gateway tốt nhưng hop gateway → backend là HTTP trái policy | Phát hiện vi phạm cấu hình/kiểm thử nội bộ |
| T21 | Client giả `X-Forwarded-Proto` hoặc `X-Client-Cert` | Ingress loại bỏ/ghi đè; backend không cấp quyền theo header giả |
| T22 | mTLS client thiếu certificate khi endpoint bắt buộc | Từ chối client authentication |
| T23 | mTLS client dùng cert không thuộc CA/identity được cho phép | Từ chối |
| T24 | mTLS cert hợp lệ nhưng access token `cnf` bind cert khác | RS từ chối token |
| T25 | Client sở hữu cert đúng nhưng token `aud` là API khác | RS từ chối theo audience |
| T26 | DPoP token/proof hợp lệ về ký nhưng HTTPS server certificate giả | Client vẫn từ chối TLS peer, không gửi credential |
| T27 | TLS 1.3 early-data request có thể thay đổi grant tại `/token` | Endpoint không xử lý early data replayable trái policy |
| T28 | Gateway có `Authorization` header logging bật nhầm | Redaction kiểm thử đảm bảo không lộ token |
| T29 | Private CA mới được deploy đúng truststore trước đổi leaf | Kết nối vẫn hợp lệ qua giai đoạn rotation đã định |
| T30 | Private CA cũ bị loại bỏ theo policy | Certificate/chain không còn được tin thì bị từ chối |
| T31 | AS cert mới, JWT signing key cũ vẫn hợp lệ và token còn hạn | Không nhầm TLS cert rotation với JWT token/key revocation |
| T32 | Introspection TLS lỗi | RS không cấp quyền cho opaque token chưa xác minh |

### 15.1. Kiểm thử âm phải có kiểm thử dương song hành

Nếu mọi request đều thất bại vì DNS hoặc route lỗi, trường hợp “cert sai hostname bị từ chối” chưa chứng minh hostname verification đang hoạt động. Để test đúng:

1. Một cert chain **hợp lệ, đúng SAN** phải kết nối thành công.
2. Cùng chain/issuer nhưng **sai SAN** phải bị từ chối.
3. Cùng SAN nhưng CA **không nằm trong truststore** phải bị từ chối.
4. Sau khi thêm CA đúng qua cấu hình tin cậy, request phù hợp thành công **mà không tắt verification**.
5. Client nhận response phải kiểm tra đúng issuer/token profile/scope/audience ở lớp OAuth; TLS thành công không đồng nghĩa token đúng.

Sử dụng mock AS/RS/cert của test harness để tạo tình huống khác nhau, không tạo mạng MITM thực tế với credential production. Với kiểm thử mTLS binding, cấp cert cho client A và client B; dùng access token bind A với kết nối trình cert B để xác nhận từ chối.

### 15.2. Kiểm tra đủ các hop

Trong hệ thống có ingress, gateway, mesh sidecar và nhiều API, kiểm thử:

- Client → gateway: cert của hostname public.
- Gateway → backend: certificate identity nội bộ, trust anchors và re-encryption.
- Resource server → AS: TLS khi fetch discovery/JWKS/introspection.
- AS → HSM/KMS/database: kết nối theo policy infrastructure.
- Native app/mobile → AS: truststore/PKI và xử lý cert rotation phù hợp nền tảng.

Nếu chỉ kiểm thử bằng browser từ laptop, không đủ để xác nhận TLS của **các kết nối machine-to-machine** đã bảo vệ RT và client secrets.

## 16. Bốn tình huống phân tích

### Tình huống A: Dev tắt certificate verification để gọi AS nội bộ

Ứng dụng Java gọi `https://auth.internal.example.test/oauth2/token` và nhận lỗi `PKIX path building failed` vì CA nội bộ chưa được cài vào truststore container. Một developer thêm `TrustManager` chấp nhận mọi cert rồi triển khai lên staging, sau đó production.

**Vấn đề:** Ai có thể chiếm DNS/proxy hoặc đứng giữa có thể giả endpoint và lấy client secret/RT, dù request vẫn bắt đầu bằng `https://`.

**Cách xử lý:** Cấp cert có SAN đúng hostname, triển khai đầy đủ chain, phân phối private CA trust anchor theo quy trình quản trị, xác minh bằng Java runtime thực tế. Xóa trust-all code và thêm negative test cert không tin cậy/sai SAN.

### Tình huống B: Gateway có HTTPS nhưng backend thấy token qua HTTP

Người dùng gọi `https://orders.example.test`. Gateway kết thúc TLS và chuyển HTTP plaintext qua mạng Pod tới `orders-service`. Một thành phần trong mạng nội bộ có khả năng đọc traffic và lấy `Authorization: Bearer ...`, sau đó thử phát lại token.

**Vấn đề:** TLS chỉ bảo vệ hop client–gateway. Ranh giới mạng nội bộ có thể không đủ an toàn theo threat model.

**Cách xử lý:** Dùng TLS/mTLS giữa gateway và backend hoặc giải pháp bảo vệ tương đương được chứng minh; quản lý workload identity, chặn spoofed forwarding headers; vẫn kiểm tra issuer/audience/scope/ACL, TTL và thu hồi tại RS.

### Tình huống C: HTTPS endpoint hợp lệ nhưng do kẻ tấn công kiểm soát

Một JWT chưa được verify chứa `jku=https://attacker.example.test/jwks.json`. Resource server tải JWKS từ đó vì endpoint HTTPS có cert hợp lệ rồi dùng key attacker để “xác minh” token.

**Vấn đề:** Certificate validation xác thực đúng **attacker.example.test**, chứ không cấp thẩm quyền cho attacker ký token của `https://auth.example.test`. Đây là **trust source confusion** chứ không phải lỗi TLS.

**Cách xử lý:** Ràng buộc JWKS với issuer đã được phê duyệt, lấy metadata từ kênh tin cậy, từ chối URL tùy ý từ token. Sau khi verify chữ ký, vẫn kiểm tra `iss`, `aud`, `exp` và quyền.

### Tình huống D: mTLS cert đã rotate nhưng token còn bind cert cũ

Service `inventory-worker` có access token chứa `cnf.x5t#S256` của client certificate cũ. PKI rotate chứng chỉ và private key; service tiếp tục sử dụng access token cũ, trình cert mới đến `inventory-api`.

**Vấn đề:** TLS handshake có thể hợp lệ với cert mới nhưng token binding không khớp; RS phải từ chối token cũ. Nếu bỏ kiểm tra `cnf` để “khôi phục service”, sender constraint bị vô hiệu.

**Cách xử lý:** Phối hợp certificate rotation với access-token reissuance, cache key theo binding identity, đợi cert cũ/ngữ cảnh cũ hết hạn đúng policy hoặc thu hồi thích hợp, bảo đảm không tự động mở lại bearer semantics khi cert đổi.

## 17. Checklist triển khai và câu hỏi tự kiểm tra

### 17.1. Checklist trước production

1. **Endpoint pinning:** AS, token/introspection/revocation, JWKS và API endpoints được lấy từ cấu hình/issuer tin cậy, không từ input chưa xác thực?
2. **HTTPS ở mọi hop:** Credential được bảo vệ client → gateway → service → AS, gồm kết nối nội bộ theo threat model?
3. **TLS policy:** Đã chọn TLS 1.3/1.2 hiện đại, cipher/key phù hợp và ngăn downgrade sang HTTP?
4. **Trust anchors:** Runtime Java/client sử dụng public/private CA đã phê duyệt, có phân tách dev/test/prod?
5. **Certificate validation:** Có kiểm tra chain, SAN hostname, validity, EKU/key usage, thuật toán và revocation theo policy?
6. **Không có bypass:** Codebase/config không chứa `trust-all`, `HostnameVerifier=true`, `curl -k` trong luồng production, hoặc flag tắt certificate validation?
7. **Proxy/service mesh:** TLS termination/re-encryption và forwarding headers được quản trị, header client giả bị loại bỏ?
8. **OAuth token policy:** TLS thành công vẫn phải xác minh JWT/JWKS hoặc opaque introspection, issuer, audience, scope, expiry và ACL?
9. **mTLS binding:** Nếu dùng certificate-bound access token, AS/RS có xác minh cert và `cnf`, kể cả khi ingress terminate mTLS?
10. **Redirect/0-RTT:** Không chuyển credential qua cross-host redirect/HTTP downgrade; token-changing requests không xử lý replayable early data?
11. **Rotation và sự cố:** Có cảnh báo cert hết hạn, overlap trust anchor có kiểm soát, kế hoạch xử lý key/CA compromise và token đã có thể bị lộ?
12. **Kiểm thử/quan sát:** Có test cert sai SAN/CA/hết hạn, gateway backend, AS/JWKS/introspection, mTLS mismatch và token redaction?

### 17.2. Câu hỏi tự kiểm tra

**1. HTTPS kết nối thành công nhưng client không kiểm tra hostname. Token có an toàn trên đường truyền không?**

Chưa đủ bảo đảm. Một cert hợp lệ cho **tên khác** có thể bị dùng trong kết nối sai nếu hostname verification bị tắt; client phải xác minh certificate chain **và** đúng hostname/SAN.

**2. JWT đã được ký đúng thì có thể gửi access token qua HTTP không?**

Không. Chữ ký bảo vệ tính toàn vẹn/chủ thể phát hành, không che token khỏi kẻ đọc được mạng. Bearer token bị sao chép có thể bị phát lại trong khoảng hiệu lực.

**3. JWKS URL dùng HTTPS và cert hợp lệ thì có được tin mọi public key trong đó không?**

Không. JWKS phải thuộc **issuer được phê duyệt** và trust configuration được thiết lập an toàn. HTTPS chỉ xác thực endpoint đích, không cho phép URL do attacker chọn trở thành nguồn ký JWT được tin.

**4. API Gateway có HTTPS, nhưng gửi Authorization header qua HTTP đến backend. Có thể khẳng định token luôn được bảo vệ không?**

Không. Đây là bảo vệ theo từng hop. Phải đánh giá và bảo vệ hop nội bộ phù hợp bằng TLS/mTLS hoặc cơ chế tương đương.

**5. mTLS client certificate hợp lệ có đủ cho phép client dùng mọi access token không?**

Không. Với certificate-bound token, RS phải kiểm tra token `cnf` khớp certificate thực tế, đồng thời xác minh issuer, audience, thời hạn, scope và quyền nghiệp vụ.

**6. Server đổi TLS certificate có làm mọi JWT do server phát hành lập tức mất hiệu lực không?**

Không. TLS certificate và JWT signing keys/claims có vòng đời khác nhau. JWT hết hiệu lực theo `exp`/revocation/trust policy riêng.

**7. TLS 1.3 0-RTT có an toàn mặc định cho POST đổi refresh token không?**

Không. Early data có nguy cơ replay; token-changing endpoints phải có chính sách không xử lý dữ liệu replayable hoặc bảo vệ chặt theo giao thức, ngoài logic single-use/rotation bình thường.

**8. AS có private CA nhưng ứng dụng Java báo PKIX path failure. Phương án đúng là gì?**

Xác minh chain, SAN, CA và cấu hình truststore riêng đã được quản trị; không tạo `X509TrustManager` bỏ qua validation.

## Tài liệu chuẩn tham khảo

- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3 và các thuộc tính handshake/early data.
- [RFC 9325 — Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325): phiên bản, cipher và chính sách sử dụng TLS an toàn.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): PKIX certification path và kiểm tra chứng chỉ/CRL.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): xác minh danh tính service, SAN và quy tắc hostname matching hiện đại.
- [RFC 8470 — Using Early Data in HTTP](https://www.rfc-editor.org/rfc/rfc8470): xử lý replay risk khi dùng TLS early data với HTTP.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS/client/RS và yêu cầu bảo vệ token endpoint/credentials.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token transport, nguy cơ token disclosure và TLS.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): security BCP trong OAuth 2.0.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS client auth và certificate thumbprint `cnf`.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens qua DPoP.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh JWT và trạng thái opaque token.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): `SSLContext`, truststore/keystore và TLS trong Java.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình issuer/JWKS và JWT validation.

**Điểm cần nhớ:** **TLS bảo vệ đường truyền, certificate validation xác minh endpoint mà ứng dụng đang nói chuyện**, còn JWT/introspection kiểm tra token và authorization quyết định quyền truy cập. Một hệ thống có HTTPS nhưng chấp nhận mọi chứng chỉ, bỏ hostname verification, tải JWKS từ URL chưa tin hoặc bỏ bảo vệ hop nội bộ vẫn có thể để lộ bearer/refresh token. Thiết kế an toàn cần **TLS đúng chuẩn + chain/SAN validation + nguồn endpoint/JWKS đáng tin + kiểm tra token/claims + quản lý secret và certificate rotation**, và khi sử dụng mTLS-bound token, phải kiểm tra ràng buộc giữa token với **chứng chỉ client thực tế** trên kết nối đã xác minh.
