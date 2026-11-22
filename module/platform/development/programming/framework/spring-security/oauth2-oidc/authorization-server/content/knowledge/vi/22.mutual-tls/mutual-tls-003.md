# Ràng buộc access token với chứng thư client

> **Chương:** mTLS  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phiên bản ví dụ:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.x trên Servlet stack. Thuộc tính `TokenSettings.x509CertificateBoundAccessTokens` có từ Spring Authorization Server 1.3. Với Spring Security 7.x tích hợp Authorization Server, cần đối chiếu API theo phiên bản.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **mTLS client authentication** tại Authorization Server với **certificate-bound access token** khi truy cập Resource Server.
2. Giải thích vì sao access token gắn với chứng thư X.509 không còn là bearer token thuần túy.
3. Mô tả cách RFC 8705 sử dụng `cnf.x5t#S256` để liên kết access token với chứng thư client.
4. Phân biệt hai phương thức `tls_client_auth` (PKI) và `self_signed_tls_client_auth`.
5. Cấu hình `RegisteredClient` và `TokenSettings.x509CertificateBoundAccessTokens(true)` trong Spring Authorization Server.
6. Hiểu cách AS lấy chứng thư từ TLS handshake, xác minh client và đưa thumbprint vào access token.
7. Xây dựng kiểm tra proof-of-possession tại Resource Server: chứng thư trong TLS handshake phải khớp thumbprint trong token.
8. Xử lý TLS termination ở reverse proxy/load balancer, certificate rotation, refresh token, thu hồi chứng thư và các tình huống vận hành.
9. Viết kiểm thử cho chứng thư sai, token không có `cnf`, thumbprint mismatch, token cũ và certificate rotation.

**Nguyên tắc chính:** Client phải chứng minh mình sở hữu private key tương ứng với chứng thư đã dùng để nhận token. Khi truy cập API, client phải thiết lập kết nối mTLS bằng **chính chứng thư đó**. Resource Server so thumbprint chứng thư thực tế với `cnf.x5t#S256` trong access token. Chỉ có access token hợp lệ hoặc chỉ có một chứng thư hợp lệ đều chưa đủ.

## 2. Bài toán: access token bị đánh cắp

Trong OAuth 2.0 thông thường, Client nhận access token rồi gửi:

~~~http
GET /api/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
~~~

Với bearer token, bất kỳ bên nào lấy được chuỗi token đều có thể sử dụng token trong thời hạn và phạm vi quyền còn hiệu lực. Token có chữ ký JWT không thay đổi đặc tính này: chữ ký bảo vệ tính toàn vẹn và nguồn phát hành, nhưng không chứng minh người gửi request là client đã nhận token.

Certificate-bound access token bổ sung một bằng chứng sở hữu:

- Khi xin token, client dùng chứng thư X.509 và private key để hoàn tất mTLS với Authorization Server (AS).
- AS tính SHA-256 thumbprint của chứng thư và liên kết nó với access token.
- Khi gọi Resource Server (RS), client tiếp tục dùng private key tương ứng để hoàn tất mTLS.
- RS lấy chứng thư từ TLS layer và so thumbprint với token.
- Nếu token bị đánh cắp nhưng attacker không có private key, attacker không thể tạo kết nối mTLS phù hợp với token đó.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>AS: TLS handshake + client certificate C1
    AS->>AS: Xác minh chứng thư / client registration
    C->>AS: POST /oauth2/token + grant
    AS->>AS: Tính SHA-256 thumbprint C1
    AS-->>C: Access token + cnf.x5t#S256
    Note over C,AS: Token được ràng buộc với C1
    C->>RS: TLS handshake + chính chứng thư C1
    C->>RS: Authorization: Bearer token
    RS->>RS: Verify token + so thumbprint C1 với cnf
    RS-->>C: Chấp nhận nếu chữ ký, quyền và certificate binding đều hợp lệ
~~~

**Certificate-bound access token không mã hóa token và không giấu token khỏi người đánh cắp.** Nó làm cho token không thể được sử dụng độc lập nếu attacker không có private key của chứng thư tương ứng.

## 3. Hai cơ chế cần phân biệt

mTLS client authentication và certificate-bound access token có quan hệ gần nhau nhưng giải quyết hai câu hỏi khác nhau.

| Cơ chế | Thời điểm | Câu hỏi được trả lời |
| --- | --- | --- |
| **mTLS client authentication** | Client kết nối Token Endpoint của AS | Client nào đang gọi AS và có chứng thư hợp lệ không? |
| **Certificate-bound access token** | Client sử dụng access token tại RS | Người gửi token có sở hữu private key của chứng thư được gắn với token không? |

### 3.1. mTLS client authentication

Client trình bày chứng thư X.509 trong TLS handshake. Server xác minh chuỗi chứng thư và/hoặc đối chiếu chứng thư với thông tin đăng ký của client.

RFC 8705 đăng ký hai phương thức xác thực:

- `tls_client_auth`: phương thức PKI, chứng thư client được cấp bởi CA mà AS tin cậy.
- `self_signed_tls_client_auth`: client sử dụng chứng thư tự ký, AS đối chiếu chứng thư với JWK Set đã đăng ký cho client.

Khi mTLS được dùng làm client authentication, client thường gửi `client_id` trong body token request vì không dùng `client_secret_basic` để nhận diện client.

### 3.2. Certificate-bound access token

Sau khi xác minh chứng thư ở Token Endpoint, AS tính thumbprint của chứng thư và liên kết nó với access token. Với JWT, RFC 8705 quy định confirmation method:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "booking-worker",
  "aud": ["booking-api"],
  "scope": "booking.read",
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_THUMBPRINT_OF_CERTIFICATE"
  }
}
~~~

`cnf` là claim xác nhận (confirmation). `x5t#S256` là SHA-256 thumbprint của chứng thư X.509, mã hóa Base64URL không có dấu padding.

Giá trị trên được tính từ **DER encoding của toàn bộ chứng thư**, không phải PEM text, public key riêng lẻ, Subject DN hoặc serial number.

Với reference/opaque access token, Resource Server lấy `cnf.x5t#S256` từ Token Introspection response thay vì đọc JWT payload.

### 3.3. Certificate-bound token không phải DPoP

| Tiêu chí | mTLS certificate-bound token | DPoP |
| --- | --- | --- |
| Bằng chứng sở hữu | Chứng thư X.509 và private key qua TLS handshake | JWK và chữ ký DPoP proof ở HTTP layer |
| TLS | Bắt buộc dùng mTLS cho protected resource access | Dùng HTTPS; DPoP proof ràng buộc request |
| Binding trong token | `cnf.x5t#S256` | `cnf.jkt` |
| Thành phần xác minh | TLS layer cung cấp client certificate, RS so thumbprint | RS xác minh proof JWT, method/URI/time/nonce và JWK thumbprint |

Không thể thay `x5t#S256` bằng `jkt` hoặc dùng DPoP proof để đáp ứng mTLS certificate binding.

## 4. Cách tính certificate thumbprint

RFC 8705 xác định `x5t#S256` theo các bước:

1. Lấy chứng thư X.509 client đã được sử dụng trong TLS handshake.
2. Lấy DER encoding bằng API chứng thư.
3. Tính SHA-256 trên toàn bộ DER bytes.
4. Mã hóa digest bằng Base64URL.
5. Bỏ ký tự padding `=` ở cuối.

~~~text
certificate_der = X509Certificate.getEncoded()
digest          = SHA-256(certificate_der)
thumbprint      = BASE64URL(digest, no_padding)
~~~

Ví dụ Java:

~~~java
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Base64;

public final class CertificateThumbprints {

    private CertificateThumbprints() {
    }

    public static String x5tS256(X509Certificate certificate)
            throws Exception {

        byte[] der = certificate.getEncoded();
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(der);

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }
}
~~~

Trong ứng dụng thực tế, có thể khai báo exception cụ thể là `CertificateEncodingException` và `NoSuchAlgorithmException`. SHA-256 được Java runtime hỗ trợ; không thay bằng SHA-1.

**Không tính thumbprint trên public key:** hai chứng thư khác nhau có thể cùng public key nhưng khác issuer, subject, serial, validity hoặc extension. RFC 8705 ràng buộc với **chứng thư**, do đó hash phải được tính trên DER của certificate.

## 5. Hai phương thức mTLS client authentication

### 5.1. PKI mutual TLS — `tls_client_auth`

Với PKI method:

1. AS yêu cầu client gửi certificate trong TLS handshake.
2. TLS stack xác minh chuỗi certificate tới trust anchor được cấu hình.
3. AS xác định RegisteredClient theo client ID.
4. AS xác minh thuộc tính chứng thư với registration.
5. Nếu hợp lệ, client authentication thành công và AS có thể xử lý grant.

Trong Spring Authorization Server, mặc định certificate verifier của `X509ClientCertificateAuthenticationProvider` đối chiếu Subject Distinguished Name (DN) của chứng thư với `ClientSettings.x509CertificateSubjectDN`.

Ví dụ registration:

~~~java
RegisteredClient mtlsClient = RegisteredClient
    .withId("mtls-client-registration")
    .clientId("mtls-client")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("booking.read")
    .clientSettings(ClientSettings.builder()
        .x509CertificateSubjectDN(
            "CN=mtls-client,OU=Platform,O=Example,C=VN")
        .build())
    .tokenSettings(TokenSettings.builder()
        .x509CertificateBoundAccessTokens(true)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

Ví dụ dựa trên Spring Authorization Server 1.5.x. Cần import `RegisteredClient`, `ClientAuthenticationMethod`, `AuthorizationGrantType`, `ClientSettings`, `TokenSettings` và `Duration`. Registration phải được lưu qua `RegisteredClientRepository`; không tạo lại ID ngẫu nhiên mỗi lần khởi động nếu authorization đã lưu đang tham chiếu tới registration.

**Giới hạn của default verifier:** cấu hình `x509CertificateSubjectDN` chỉ so sánh Subject DN. Nếu policy cần SAN (DNS, URI, IP, email) hoặc thuộc tính khác, phải cấu hình custom certificate verifier. Khi tùy biến, không được bỏ xác minh chain PKI, thời hạn, key usage, EKU và các kiểm tra certificate policy cần thiết.

### 5.2. Self-signed certificate mutual TLS — `self_signed_tls_client_auth`

Phương thức này không yêu cầu client certificate được cấp bởi CA công khai/trusted PKI. Thay vào đó:

1. Client đăng ký JWK Set hoặc URL `jwks_uri` với AS.
2. JWK Set chứa certificate trong thuộc tính `x5c` của một JWK.
3. Client gửi certificate tương ứng trong TLS handshake.
4. AS so certificate nhận được với certificate đã đăng ký cho client.

Spring Authorization Server dùng `ClientSettings.jwkSetUrl` để truy xuất JWK Set của client theo cấu hình mặc định.

~~~java
RegisteredClient selfSignedMtlsClient = RegisteredClient
    .withId("self-signed-mtls-registration")
    .clientId("partner-device")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("partner.read")
    .clientSettings(ClientSettings.builder()
        .jwkSetUrl("https://partner.example.test/.well-known/jwks.json")
        .build())
    .tokenSettings(TokenSettings.builder()
        .x509CertificateBoundAccessTokens(true)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

JWK Set của client cần chứa public key tương ứng và `x5c` với certificate. Theo RFC 7517, public key biểu diễn trong JWK phải khớp public key của certificate đầu tiên trong `x5c`.

**Self-signed không có nghĩa là chấp nhận mọi chứng thư tự ký.** AS vẫn phải xác minh certificate nhận từ handshake khớp với certificate mà client đã đăng ký. Bảo vệ endpoint `jwks_uri` của client khỏi bị thay đổi trái phép; nếu attacker thay certificate trong JWK Set, họ có thể chiếm danh tính client.

### 5.3. So sánh hai phương thức

| Thuộc tính | `tls_client_auth` | `self_signed_tls_client_auth` |
| --- | --- | --- |
| Trust model | PKI/CA | Certificate được đăng ký trực tiếp |
| Xác minh chain | TLS stack xác minh tới CA tin cậy | Không dựa vào CA chain như PKI method |
| Liên kết registration | Mặc định Spring so Subject DN | Đối chiếu certificate trong client JWKS |
| Cấu hình SAS | `x509CertificateSubjectDN` | `jwkSetUrl` |
| Xoay certificate | Cấp cert mới từ CA theo policy | Cập nhật JWK Set/client registration |
| Vận hành | Quản trị CA, trust store, CRL/OCSP | Bảo vệ JWKS, quản lý certificate pinning |

RFC 8705 cảnh báo nguy cơ certificate spoofing nếu PKI method chỉ so Subject DN nhưng AS tin quá nhiều CA. Hai certificate do hai CA khác nhau cấp có thể có cùng Subject DN; vì vậy trust anchors phải được giới hạn theo chính sách.

## 6. Bật certificate-bound access token trong Spring Authorization Server

### 6.1. Cấu hình TokenSettings

Spring Authorization Server cung cấp:

~~~java
TokenSettings.builder()
    .x509CertificateBoundAccessTokens(true)
    .build();
~~~

Khi bật setting này cho RegisteredClient sử dụng `tls_client_auth` hoặc `self_signed_tls_client_auth`, AS liên kết access token với chứng thư X.509 nhận được trong client authentication.

Setting mặc định là `false`. API `x509CertificateBoundAccessTokens(boolean)` có từ Spring Authorization Server 1.3.

Ví dụ đầy đủ hơn:

~~~java
RegisteredClient mtlsWorker = RegisteredClient
    .withId("mtls-worker-id")
    .clientId("mtls-worker")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("booking.read")
    .clientSettings(ClientSettings.builder()
        .x509CertificateSubjectDN(
            "CN=mtls-worker,OU=Services,O=Example,C=VN")
        .build())
    .tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .x509CertificateBoundAccessTokens(true)
        .build())
    .build();
~~~

`SELF_CONTAINED` được chọn để access token là JWT, giúp RS kiểm tra chữ ký và claim `cnf` cục bộ. Nếu chọn `REFERENCE`, RS cần introspection để nhận trạng thái và certificate confirmation metadata.

### 6.2. Setting không tự cấu hình TLS trên server

`x509CertificateBoundAccessTokens(true)` không tự cấu hình TLS listener. Ứng dụng AS còn phải:

- Bật HTTPS.
- Cấu hình TLS stack yêu cầu/nhận client certificate.
- Cấu hình trust store/CA theo phương thức PKI nếu dùng `tls_client_auth`.
- Bảo đảm Spring Authorization Server nhận được certificate chain từ TLS layer.
- Đăng ký client đúng authentication method.
- Kiểm tra certificate verifier và token generation.

Nếu không có certificate trong handshake, AS không thể lấy thumbprint đúng để ràng buộc token.

### 6.3. Phân biệt client authentication và token binding

Có thể bật mTLS client authentication mà không bật certificate-bound access token. Khi đó chứng thư được dùng để xác thực client tại AS, nhưng access token phát hành vẫn có thể là bearer token.

RFC 8705 mô tả certificate-bound access token như một cơ chế binding riêng; có thể thiết kế biến thể cho public client. Tuy nhiên, setting tích hợp của Spring Authorization Server được mô tả cho client dùng `tls_client_auth` hoặc `self_signed_tls_client_auth`. Không giả định public client `none` tự được binding chỉ vì kết nối có certificate.

## 7. Cấu hình TLS listener ở Authorization Server

### 7.1. HTTPS và client certificate

Ví dụ cấu hình Spring Boot cho AS có cả client mTLS và các client dùng phương thức khác:

~~~yaml
server:
  ssl:
    enabled: true
    client-auth: want
    trust-store: classpath:as-client-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: ${AS_CLIENT_TRUSTSTORE_PASSWORD}
~~~

- `client-auth: want` yêu cầu client có thể trình bày certificate nhưng không bắt mọi client phải có certificate.
- `client-auth: need` bắt buộc mọi kết nối tới listener đó phải có client certificate.
- Trust store phải chứa CA phù hợp nếu dùng PKI `tls_client_auth`.
- Secret trust store phải được cấp qua secret manager/environment, không hardcode trong repository.

Nếu cùng host/port phục vụ browser login, public client và các phương thức client authentication khác, đặt `need` toàn cục có thể khiến browser hoặc client không có certificate không bắt tay TLS được. Có thể dùng `want` hoặc tách mTLS Token Endpoint/alias sang hostname hay port riêng.

### 7.2. Self-signed method cần cấu hình TLS phù hợp

Với `self_signed_tls_client_auth`, RFC 8705 thiết kế để AS xác minh certificate bằng JWK Set đã đăng ký thay vì dựa vào CA trust chain. TLS listener phải yêu cầu certificate nhưng việc xác minh certificate cần được phối hợp với cơ chế verifier của SAS. Không áp dụng cấu hình trust-all rộng khắp chỉ để làm self-signed hoạt động.

### 7.3. Reverse proxy hoặc load balancer kết thúc TLS

Nếu TLS kết thúc ở proxy:

~~~mermaid
flowchart LR
    C["Client<br/>certificate + private key"]
    LB["Load Balancer / Reverse Proxy<br/>mTLS handshake"]
    AS["Spring Authorization Server"]
    DB[("RegisteredClientRepository<br/>Authorization Store")]

    C -->|"mTLS"| LB
    LB -->|"Kết nối backend được bảo vệ<br/>+ certificate metadata đã xác minh"| AS
    AS --> DB
~~~

AS không còn trực tiếp thấy TLS handshake từ client. Metadata chứng thư phải được proxy chuyển tới backend qua một kênh tin cậy.

Các yêu cầu bắt buộc:

- Proxy phải xóa mọi header certificate do client gửi trước khi chèn metadata của chính nó.
- Backend chỉ nhận kết nối từ proxy tin cậy, tốt nhất qua mạng riêng và mTLS giữa proxy/backend.
- Không cho client truy cập trực tiếp backend để giả mạo đường đi proxy.
- Metadata phải biểu diễn certificate đã được proxy lấy từ TLS handshake, không phải chuỗi do request tùy ý cung cấp.
- Cấu hình converter/verifier phù hợp để SAS nhận được certificate chain đúng.

RFC 8705 để chi tiết truyền certificate metadata giữa proxy và ứng dụng ngoài phạm vi chuẩn. Đây là một ranh giới tin cậy phải được thiết kế và kiểm thử riêng.

## 8. Client gọi Token Endpoint bằng mTLS

Ví dụ Client Credentials:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

client_id=mtls-worker&grant_type=client_credentials&scope=booking.read
~~~

Client không gửi `client_secret_basic` khi registration dùng `tls_client_auth`. Chứng thư client được trình bày trong TLS handshake.

Dùng curl minh họa:

~~~bash
curl --cert mtls-worker.crt \
     --key mtls-worker.key \
     --cacert auth-server-ca.crt \
     --header "Content-Type: application/x-www-form-urlencoded" \
     --data "client_id=mtls-worker&grant_type=client_credentials&scope=booking.read" \
     https://auth.example.test/oauth2/token
~~~

- `--cert`: certificate của client.
- `--key`: private key tương ứng.
- `--cacert`: CA dùng để xác minh certificate của AS.
- `client_id`: xác định RegisteredClient.
- Client phải bảo vệ private key và chỉ cho workload được phép sử dụng.

Không truyền private key qua HTTP body, URL, header hoặc log. Trong production, dùng keystore/PKCS#12, HSM, KMS hoặc nền tảng quản lý key phù hợp.

### 8.1. Response có JWT access token

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "eyJ...SIGNED_JWT...",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "booking.read"
}
~~~

JWT payload có thể chứa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "mtls-worker",
  "aud": ["booking-api"],
  "scope": "booking.read",
  "iat": 1893455700,
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_OF_CERTIFICATE_DER"
  }
}
~~~

`cnf` là thông tin ràng buộc chứng thư. Giá trị thumbprint không phải private key và không thay thế chữ ký JWT. RS vẫn phải xác minh chữ ký, issuer, audience, thời hạn, scope và certificate binding.

### 8.2. Reference access token và introspection

Nếu access token có format `REFERENCE`, RS không thể đọc `cnf` từ chuỗi opaque. RS gọi Introspection Endpoint với client authentication phù hợp. Response active có thể chứa:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "mtls-worker",
  "scope": "booking.read",
  "exp": 1893456000,
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_OF_CERTIFICATE_DER"
  }
}
~~~

Theo RFC 8705, `cnf` và `x5t#S256` được đưa vào introspection response để RS so sánh với certificate thực tế. Không giả định custom metadata được trả đầy đủ nếu response handler hoặc introspection implementation đã bị tùy biến; cần test contract thật.

## 9. Resource Server phải kiểm tra proof-of-possession

### 9.1. Chữ ký JWT là chưa đủ

Một RS dùng cấu hình JWT tiêu chuẩn thường kiểm tra chữ ký, issuer, audience nếu đã cấu hình validator, thời hạn `exp`/`nbf`, scope và policy nghiệp vụ.

Những bước đó **không tự lấy certificate từ TLS request rồi so với `cnf.x5t#S256`**. Với certificate-bound token, RS phải bổ sung bước request-aware kiểm tra chứng thư thực tế.

### 9.2. Trình tự xác minh tại RS

1. TLS layer nhận certificate từ client trong mutual TLS handshake.
2. Bearer token authentication xác minh access token như thông thường.
3. RS đọc `cnf.x5t#S256` từ JWT hoặc introspection attributes.
4. RS lấy certificate leaf thực tế từ TLS layer.
5. RS tính SHA-256 trên DER certificate và Base64URL không padding.
6. RS so sánh thumbprint thực tế với thumbprint trong token.
7. Nếu thiếu certificate, thiếu `cnf` hoặc mismatch, trả HTTP 401 với `invalid_token`.
8. Nếu binding hợp lệ, tiếp tục kiểm tra scope và quyền nghiệp vụ.

~~~mermaid
flowchart TD
    REQ["Request HTTPS + Bearer token"]
    TLS["TLS layer lấy client certificate"]
    AUTH["Resource Server xác minh access token"]
    CNF{"Token có cnf.x5t#S256?"}
    CERT{"TLS request có certificate?"}
    HASH["SHA-256(DER certificate)<br/>Base64URL no padding"]
    MATCH{"Thumbprint khớp?"}
    AUTHZ["Kiểm tra scope / quyền dữ liệu"]
    OK["Cho phép request"]
    DENY["401 invalid_token"]

    REQ --> TLS --> AUTH --> CNF
    CNF -->|"Không"| DENY
    CNF -->|"Có"| CERT
    CERT -->|"Không"| DENY
    CERT -->|"Có"| HASH --> MATCH
    MATCH -->|"Không"| DENY
    MATCH -->|"Có"| AUTHZ --> OK
~~~

### 9.3. Lấy certificate từ Servlet request

Với TLS được kết thúc trực tiếp tại Servlet container, certificate chain có thể được đọc từ request attribute:

~~~java
Object value = request.getAttribute(
    "jakarta.servlet.request.X509Certificate");

if (value instanceof X509Certificate[] chain && chain.length > 0) {
    X509Certificate clientCertificate = chain[0];
}
~~~

Certificate đầu tiên trong chain là leaf certificate của client. Attribute này chỉ có khi TLS/container nhận được client certificate. Nếu proxy kết thúc TLS ở phía trước, attribute có thể không tồn tại; khi đó phải dùng cơ chế chuyển metadata từ proxy đã xác minh và bảo vệ.

### 9.4. Bộ lọc kiểm tra certificate binding

Ví dụ dưới đây minh họa một filter cho route yêu cầu certificate-bound JWT. Đây là **skeleton tích hợp**, cần điều chỉnh theo TLS container, filter chain, token format và cách xử lý lỗi của ứng dụng.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Base64;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

public final class CertificateBoundTokenFilter
        extends OncePerRequestFilter {

    private static final String CERTIFICATE_ATTRIBUTE =
        "jakarta.servlet.request.X509Certificate";

    private final AuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            reject(request, response);
            return;
        }

        Object certificateValue =
            request.getAttribute(CERTIFICATE_ATTRIBUTE);

        if (!(certificateValue instanceof X509Certificate[] chain)
                || chain.length == 0) {
            reject(request, response);
            return;
        }

        Map<String, Object> confirmation =
            jwtAuth.getToken().getClaimAsMap("cnf");

        Object expectedValue = confirmation == null
            ? null
            : confirmation.get("x5t#S256");

        if (!(expectedValue instanceof String expectedThumbprint)) {
            reject(request, response);
            return;
        }

        try {
            String actualThumbprint = x5tS256(chain[0]);

            boolean matches = MessageDigest.isEqual(
                expectedThumbprint.getBytes(StandardCharsets.US_ASCII),
                actualThumbprint.getBytes(StandardCharsets.US_ASCII));

            if (!matches) {
                reject(request, response);
                return;
            }
        }
        catch (GeneralSecurityException ex) {
            reject(request, response);
            return;
        }

        filterChain.doFilter(request, response);
    }

    private static String x5tS256(X509Certificate certificate)
            throws GeneralSecurityException {

        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(certificate.getEncoded());

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }

    private void reject(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException, ServletException {

        SecurityContextHolder.clearContext();

        this.entryPoint.commence(
            request,
            response,
            new OAuth2AuthenticationException(
                new OAuth2Error("invalid_token")));
    }
}
~~~

Filter trên:

- Chỉ chấp nhận `JwtAuthenticationToken` và access token có `cnf.x5t#S256`.
- Lấy leaf certificate từ Servlet attribute.
- Tính thumbprint theo DER certificate.
- Dùng `MessageDigest.isEqual` để so sánh.
- Trả Bearer challenge `invalid_token` nếu không hợp lệ.

Nếu RS sử dụng opaque token, principal thường là `BearerTokenAuthentication`. Khi đó lấy `cnf` từ token attributes do introspection trả về, thay cho `JwtAuthenticationToken.getToken().getClaimAsMap("cnf")`. Không bỏ qua bước so thumbprint chỉ vì token là opaque.

### 9.5. Đăng ký filter cho route mTLS

Ví dụ filter chain riêng:

~~~java
@Bean
SecurityFilterChain mtlsApiSecurity(
        HttpSecurity http,
        CertificateBoundTokenFilter certificateBoundTokenFilter)
        throws Exception {

    http
        .securityMatcher("/api/mtls/**")
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer -> resourceServer
            .jwt(Customizer.withDefaults()))
        .addFilterAfter(
            certificateBoundTokenFilter,
            BearerTokenAuthenticationFilter.class);

    return http.build();
}
~~~

Đây là filter chain minh họa cho endpoint yêu cầu mTLS-bound token. Cần có một chain khác nếu API thông thường vẫn chấp nhận bearer token không ràng buộc certificate. TLS listener/gateway của route `/api/mtls/**` phải yêu cầu client certificate để request attribute có dữ liệu.

Không để một route yêu cầu mTLS nhưng vô tình rơi vào chain chỉ xác minh JWT thông thường. Nếu token không có `cnf` mà route vẫn chấp nhận, attacker có thể dùng bearer token đánh cắp như trước.

## 10. Client gọi Resource Server bằng đúng certificate

Sau khi nhận access token, client phải sử dụng cùng certificate và private key đã trình bày với AS:

~~~http
GET /api/mtls/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
~~~

Ví dụ curl:

~~~bash
curl --cert mtls-worker.crt \
     --key mtls-worker.key \
     --cacert resource-server-ca.crt \
     --header "Authorization: Bearer $ACCESS_TOKEN" \
     https://api.example.test/api/mtls/bookings
~~~

Nếu client chỉ gửi `Authorization: Bearer` mà không có client certificate, TLS handshake có thể bị từ chối hoặc ứng dụng trả `401 invalid_token` tùy cấu hình listener. Nếu client gửi một certificate khác, thumbprint không khớp và request phải bị từ chối.

### 10.1. Access token không thể chuyển sang máy khác độc lập

| Tình huống | Kết quả |
| --- | --- |
| Token + đúng private key/certificate | Có thể xác minh, nếu token và quyền còn hợp lệ |
| Token bị đánh cắp, không có private key | Không hoàn tất mTLS với certificate tương ứng |
| Token + certificate khác | Thumbprint mismatch, 401 |
| Certificate đúng nhưng token hết hạn | Token validation thất bại |
| Certificate đúng, token đúng nhưng scope thiếu | Authorization thất bại |
| Certificate hết hạn hoặc bị thu hồi | TLS/PKI policy hoặc kiểm tra certificate status phải từ chối theo policy |

Certificate-bound token giảm rủi ro token theft, nhưng không bảo vệ khi attacker chiếm được cả private key hoặc kiểm soát workload có quyền sử dụng key.

## 11. Refresh token và certificate binding

RFC 8705 phân biệt access token binding với refresh token:

- Access token có thể chứa `cnf.x5t#S256` trực tiếp hoặc qua introspection.
- Refresh token vốn được OAuth 2.0 ràng buộc với client.
- Với confidential client dùng `tls_client_auth` hoặc `self_signed_tls_client_auth`, client phải tiếp tục xác thực tại Token Endpoint khi dùng refresh token.
- Vì xác thực client được thực hiện bằng certificate, refresh token được ràng buộc **gián tiếp** với client/certificate authentication.
- Không mặc định refresh token có claim `cnf.x5t#S256` giống access token.

Khi client refresh access token, hãy kết nối Token Endpoint bằng certificate được đăng ký và sử dụng cho client authentication. AS kiểm tra client và cấp access token mới theo policy; token mới được ràng buộc với certificate được dùng trong request đó.

### 11.1. Vì sao không thể chỉ dùng refresh token bị đánh cắp?

Attacker có refresh token nhưng không có private key/chứng thư client sẽ không thể hoàn tất mTLS client authentication tại Token Endpoint. Tuy nhiên, nếu attacker lấy được cả refresh token và private key, cơ chế mTLS không còn ngăn được họ.

Do đó vẫn cần bảo vệ refresh token, private key, secret store, quyền truy cập process và audit log.

## 12. Certificate rotation và vòng đời token

### 12.1. Certificate thay đổi thì access token cũ ra sao?

Access token được ràng buộc với thumbprint của certificate cụ thể. Khi client thay certificate:

- Certificate mới có thumbprint khác, kể cả khi Subject DN không đổi.
- Access token cũ vẫn chứa thumbprint certificate cũ.
- Request tới RS bằng certificate mới không khớp token cũ.
- Client cần xin access token mới bằng certificate mới.

RFC 8705 xem access token gắn với certificate cũ là không còn dùng được khi client cập nhật certificate, và client có thể xin token mới rồi retry request.

### 12.2. Kế hoạch xoay certificate

1. Tạo certificate/key pair mới trong kho khóa an toàn.
2. Đăng ký certificate mới theo PKI policy hoặc cập nhật client JWKS nếu dùng self-signed method.
3. Bảo đảm AS nhận certificate mới và xác thực đúng client.
4. Kiểm thử token mới chứa thumbprint mới.
5. Chuyển client sang certificate mới và xin token mới.
6. RS nhận certificate mới và so sánh với thumbprint mới trong token.
7. Giữ certificate cũ trong khoảng chuyển tiếp nếu cần cho token cũ còn hiệu lực.
8. Sau khi token cũ hết hạn hoặc bị revoke, loại bỏ certificate cũ khỏi trust/registration theo policy.

Nếu dùng PKI method và default verifier chỉ so Subject DN, một certificate mới cùng Subject DN có thể được chấp nhận khi chain được cấp bởi CA tin cậy. Tuy vậy, **thumbprint vẫn thay đổi** nên access token cũ không tự dùng được với certificate mới.

### 12.3. Emergency rotation khi private key bị lộ

Khi nghi ngờ private key bị compromise:

- Thu hồi certificate theo PKI/CA process hoặc xóa certificate khỏi client JWKS.
- Ngăn AS tiếp tục chấp nhận certificate cũ.
- Ngăn RS chấp nhận thumbprint cũ qua denylist/authorization policy nếu cần phản ứng tức thì.
- Revoke refresh token/authorization liên quan.
- Cấp certificate mới và token mới.
- Theo dõi các request có thumbprint cũ và điều tra audit.
- Không chờ access token hết hạn nếu có bằng chứng key bị chiếm dụng.

Chỉ gỡ certificate khỏi trust store không tự đảm bảo mọi RS đang chạy đã nhận thay đổi, đặc biệt nếu TLS kết thúc ở nhiều proxy hoặc có cache/connection pool. Cần quy trình triển khai đồng bộ.

## 13. TLS termination, proxy và ranh giới tin cậy

### 13.1. Vì sao proxy có thể làm sai certificate binding?

Giả sử client kết nối mTLS tới load balancer, sau đó load balancer gọi backend AS/RS qua HTTP hoặc TLS một chiều. Backend không trực tiếp quan sát TLS handshake của client. Nếu backend chỉ tin header `X-Client-Cert` bất kỳ, attacker có thể gửi header giả để mạo danh certificate.

### 13.2. Cấu hình an toàn

- Chỉ proxy tin cậy được phép truyền certificate metadata.
- Proxy xóa header do client cung cấp trước khi tạo header nội bộ.
- Backend chỉ cho phép kết nối từ proxy qua private network/firewall và nên có mTLS giữa proxy/backend.
- Proxy xác minh client certificate theo policy trước khi chuyển metadata.
- Metadata phải có encoding/format chuẩn và backend phải parse certificate chặt chẽ.
- Không expose backend trực tiếp ra internet.
- Có test rằng header giả từ client bị xóa và không được dùng làm identity.

~~~mermaid
flowchart TD
    ATTACKER["Client gửi header certificate giả"]
    LB["Trusted Load Balancer"]
    BACK["Backend AS / RS"]

    ATTACKER -->|"TLS mTLS + forged header"| LB
    LB -->|"Xóa header client tự gửi"| LB
    LB -->|"Thêm certificate metadata đã xác minh<br/>qua kênh backend tin cậy"| BACK
    ATTACKER -.->|"Không được truy cập trực tiếp"| BACK
~~~

Nếu có thể, TLS pass-through hoặc TLS termination trực tiếp tại AS/RS giúp giảm số thành phần phải tin cậy khi chuyển certificate metadata. Nếu phải terminate tại proxy, coi proxy là một phần của security boundary.

## 14. Certificate validation và các giới hạn

### 14.1. PKI validation

Với `tls_client_auth`, cần xác minh:

- Chain tới CA trust anchor đã được phê duyệt.
- Certificate còn hiệu lực theo thời gian.
- Key Usage/Extended Key Usage phù hợp client authentication.
- Subject DN hoặc SAN khớp client registration.
- Chính sách CRL/OCSP/revocation nếu hệ thống yêu cầu.
- CA có issuance policy đáp ứng yêu cầu bảo mật.

Chỉ so sánh Subject DN mà không giới hạn trust anchor có thể tạo rủi ro spoofing: CA khác được trust có thể cấp certificate có cùng DN.

### 14.2. Self-signed validation

Với `self_signed_tls_client_auth`:

- Client certificate phải khớp certificate được đăng ký trong JWKS.
- JWK `x5c` phải chứa certificate đúng và public key JWK phải tương ứng.
- JWKS URI phải được bảo vệ khỏi thay đổi trái phép.
- Có quy trình rotation và thu hồi certificate.
- Không chấp nhận certificate chỉ vì nó self-signed và TLS handshake có thể hoàn tất.

### 14.3. Certificate-bound proof không thay thế mọi kiểm tra PKI

Ở RS, mục đích của RFC 8705 là xác minh client đang chứng minh sở hữu private key tương ứng với certificate đã gắn trong token. RFC nêu rằng RS không nhất thiết phải xây lại trust chain PKI như AS; tuy nhiên triển khai có thể có thêm policy certificate validity/revocation.

Điều quan trọng là RS phải lấy certificate từ TLS layer tin cậy và so thumbprint với token. Nếu chỉ lấy Subject DN từ header hoặc từ certificate chưa xác minh, proof-of-possession bị suy yếu.

### 14.4. Certificate hết hạn không tự sửa token claims

`exp` của access token và `notAfter` của certificate là hai thời hạn khác nhau. Hệ thống cần quyết định:

- TLS layer có từ chối certificate hết hạn không.
- AS có kiểm tra validity/revocation khi cấp token không.
- RS có kiểm tra certificate validity/revocation hay chỉ dùng thumbprint như proof-of-possession.
- Khi certificate bị revoke, cách ngăn access token cũ tiếp tục được dùng.

Không giả định access token sẽ tự hết hạn đúng lúc certificate hết hạn. Nếu cần chặn ngay, phải có cơ chế revocation/denylist hoặc policy kiểm tra trạng thái certificate.

## 15. Cấu hình Spring Authorization Server: các extension point

### 15.1. Client authentication filter và provider

Spring Authorization Server có các thành phần mặc định:

- `X509ClientCertificateAuthenticationConverter`: lấy certificate chain từ HTTP request/TLS layer và tạo client authentication request.
- `X509ClientCertificateAuthenticationProvider`: xác minh client certificate cho `tls_client_auth` hoặc `self_signed_tls_client_auth`.
- `OAuth2ClientAuthenticationFilter`: xử lý client authentication và đặt kết quả đã xác thực vào SecurityContext.

Không tự viết converter đọc `X-Client-Cert` từ request nếu chưa thiết lập proxy trust model. Nếu TLS terminate tại Servlet container, ưu tiên dùng cơ chế X.509 mặc định.

### 15.2. Tùy biến verifier cho SAN

Spring Authorization Server cho phép đặt custom certificate verifier trên `X509ClientCertificateAuthenticationProvider`. Điều này hữu ích nếu registration policy cần SAN thay cho Subject DN.

Mô hình cấu hình:

~~~java
authorizationServerConfigurer.clientAuthentication(clientAuthentication ->
    clientAuthentication.authenticationProviders(providers ->
        providers.forEach(provider -> {
            if (provider instanceof
                    X509ClientCertificateAuthenticationProvider x509Provider) {

                x509Provider.setCertificateVerifier(context -> {
                    OAuth2ClientAuthenticationToken clientAuthentication =
                        context.getAuthentication();

                    RegisteredClient registeredClient =
                        context.getRegisteredClient();

                    X509Certificate[] chain =
                        (X509Certificate[]) clientAuthentication.getCredentials();

                    X509Certificate certificate = chain[0];

                    // Kiểm tra SAN / thuộc tính certificate theo policy.
                    // Nếu không hợp lệ, ném OAuth2AuthenticationException.
                });
            }
        })
    )
);
~~~

Đây là khung tùy biến. Khi đặt verifier mới, ứng dụng chịu trách nhiệm triển khai đầy đủ logic kiểm tra thuộc tính certificate mong muốn. Không để TODO/logic bỏ trống trong production. Nếu chỉ cần Subject DN theo mặc định, không cần override verifier.

### 15.3. Kiểm tra API theo phiên bản

`X509ClientCertificateAuthenticationProvider` và setting certificate-bound token có thay đổi theo nhánh thư viện. Trong Spring Authorization Server 1.5.x, các lớp/API nêu trên có sẵn; nếu dùng phiên bản cũ hơn, kiểm tra Javadoc/release notes thay vì giả định method tồn tại.

## 16. Kiểm thử certificate-bound access token

### 16.1. Ma trận kiểm thử tại Authorization Server

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Client certificate hợp lệ | Chain hợp lệ, DN/SAN đúng registration | Client authentication thành công |
| Certificate từ CA không tin cậy | PKI method, trust chain sai | TLS/client authentication thất bại |
| Subject DN sai | Certificate hợp lệ nhưng DN không khớp | Từ chối client |
| SAN sai | Custom verifier yêu cầu SAN cụ thể | Từ chối client |
| Self-signed certificate đăng ký đúng | JWKS chứa x5c tương ứng | Client authentication thành công |
| Self-signed certificate chưa đăng ký | Không có cert match trong JWKS | Từ chối client |
| Client không gửi certificate | Registration yêu cầu mTLS | Không thể xác thực client |
| Bound token setting bật | mTLS client hợp lệ | Access token có certificate confirmation |
| Bound token setting tắt | Client mTLS nhưng policy không bật binding | Token theo cấu hình không có binding |
| Client không được grant | Certificate đúng nhưng grant không đăng ký | Từ chối grant |
| Certificate hết hạn/revoked | Theo PKI policy | Từ chối theo chính sách xác minh |

### 16.2. Ma trận kiểm thử tại Resource Server

| Ca kiểm thử | Token | Certificate ở TLS handshake | Kết quả |
| --- | --- | --- | --- |
| Đúng certificate | cnf có thumbprint C1 | C1 | Có thể chấp nhận |
| Sai certificate | cnf có C1 | C2 | 401 `invalid_token` |
| Không có certificate | cnf có C1 | Không có | Từ chối |
| Token không có cnf trên route mTLS | Không có confirmation | C1 | Từ chối |
| Token bị sửa | Chữ ký sai | C1 | Từ chối trước hoặc trong JWT validation |
| Token hết hạn | exp đã qua | C1 | Từ chối |
| Audience sai | aud không dành cho RS | C1 | Từ chối |
| Scope thiếu | Token hợp lệ và C1 đúng | C1 | 403 theo authorization policy |
| Token opaque active | Introspection cnf=C1 | C1 | Có thể chấp nhận |
| Token opaque inactive | active=false | C1 | Từ chối |
| Certificate rotation | Token cũ cnf=C1 | C2 | Từ chối token cũ |
| Certificate bị thu hồi | cnf=C1 | C1 nhưng cert bị revoke | Từ chối theo revocation policy |

### 16.3. Test thumbprint độc lập

Tạo certificate fixture có thể kiểm soát và xác minh:

1. `certificate.getEncoded()` trả DER bytes.
2. Digest là SHA-256.
3. Base64URL không padding.
4. Kết quả khớp `x5t#S256` trong JWT fixture.
5. Hash PEM text hoặc public key riêng cho ra giá trị khác.

Không dùng certificate thật hoặc private key production trong test.

### 16.4. Test TLS end-to-end

Unit test filter chỉ chứng minh logic so sánh. Cần integration test với HTTPS listener thật hoặc test server hỗ trợ client certificate:

- Request không certificate.
- Request certificate C1 và token cnf C1.
- Request certificate C2 và token cnf C1.
- Token JWT hợp lệ nhưng thiếu cnf.
- Token JWT sai chữ ký.
- Request qua reverse proxy với certificate metadata tin cậy.
- Request qua proxy với header certificate giả do client tự gửi.
- Client certificate bị thay đổi giữa Token Endpoint và Resource Server.

Test end-to-end phải chứng minh certificate đến từ TLS layer, không phải chỉ set request attribute bằng tay rồi kết luận mTLS hoạt động.

## 17. Vận hành và quan sát

### 17.1. Theo dõi chỉ số

| Metric | Mục tiêu |
| --- | --- |
| TLS client-auth handshake success/failure | Phát hiện lỗi certificate/trust store |
| OAuth2 client authentication failures theo method | Phân biệt lỗi mTLS với secret/basic |
| Bound token issuance count | Biết bao nhiêu token có certificate binding |
| Missing/mismatch cnf count tại RS | Phát hiện client dùng sai certificate hoặc token |
| Certificate expiry window | Cảnh báo certificate sắp hết hạn |
| CRL/OCSP lookup failures | Phát hiện lỗi revocation infrastructure |
| Token refresh failures sau certificate rotation | Phát hiện client chưa đổi certificate/token |
| Proxy certificate metadata validation failures | Phát hiện cấu hình proxy hoặc header spoofing |

Không log private key, access token, refresh token hoặc toàn bộ certificate chain nếu không cần. Có thể log thumbprint đã được kiểm soát ở mức audit, nhưng cần cân nhắc privacy và cardinality.

### 17.2. Những dấu hiệu cần cảnh báo

- Tỷ lệ `invalid_token` tăng sau khi đổi certificate.
- Client authentication thất bại hàng loạt sau khi cập nhật trust store.
- Certificate mới được phát nhưng JWKS self-signed chưa cập nhật.
- Một client ID đột ngột sử dụng nhiều certificate không nằm trong rotation plan.
- Token có `cnf` nhưng RS không nhận được certificate attribute.
- Proxy forwarding header xuất hiện từ nguồn không tin cậy.
- Nhiều request dùng cùng token nhưng thumbprint khác nhau.

### 17.3. Runbook khi client không gọi được API sau khi đổi certificate

1. Kiểm tra certificate mà client thực sự gửi tới RS trong TLS handshake.
2. Đọc `cnf.x5t#S256` từ token đã được xác minh.
3. Tính thumbprint từ DER certificate ở RS.
4. So sánh hai giá trị.
5. Nếu khác, xác định token được cấp bằng certificate nào.
6. Client dùng certificate mới để xin token mới tại AS.
7. Nếu certificate mới chưa được AS đăng ký/trust, sửa registration/CA/JWKS.
8. Xác minh proxy không làm mất hoặc ghi đè certificate metadata.
9. Kiểm tra lại scope, audience và expiry sau khi binding đã khớp.

Không khắc phục bằng cách bỏ filter certificate-binding hoặc chấp nhận mọi thumbprint.

## 18. Các lỗi thiết kế cần tránh

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Nghĩ HTTPS là mTLS | Không có client certificate authentication | Cấu hình TLS yêu cầu/nhận client cert |
| Nghĩ mTLS client authentication tự động bind token | Access token vẫn có thể là bearer | Bật `x509CertificateBoundAccessTokens(true)` |
| Chỉ xác minh chữ ký JWT tại RS | Token bị đánh cắp vẫn dùng được | So `cnf.x5t#S256` với TLS client cert |
| Hash PEM hoặc public key | Thumbprint không đúng RFC | Hash DER certificate bằng SHA-256 |
| Dùng Subject DN làm thumbprint | Nhiều certificate có thể cùng DN | Dùng `x5t#S256` |
| Tin header certificate do client gửi | Certificate spoofing | Lấy từ TLS layer hoặc proxy tin cậy |
| Không bảo vệ reverse proxy | Attacker bypass proxy và giả metadata | Network isolation, mTLS backend, strip client headers |
| Dùng `client-auth: need` cho mọi endpoint | Browser/client không có cert không bắt tay được | Tách listener hoặc dùng `want` khi cần |
| Tin mọi self-signed certificate | Client giả mạo | So certificate với client JWKS đã đăng ký |
| PKI trust quá rộng | Certificate spoofing cùng Subject DN | Giới hạn trust anchors và kiểm tra SAN/DN |
| Xoay cert nhưng tiếp tục dùng access token cũ | Thumbprint mismatch | Xin access token mới bằng cert mới |
| Coi refresh token có cùng claim cnf như access token | Nhầm cơ chế binding | Refresh token gắn với client và client auth theo RFC 8705 |
| Không kiểm tra revocation | Cert bị thu hồi vẫn có thể dùng theo policy lỏng | CRL/OCSP/denylist hoặc cơ chế online |
| Chỉ unit test thumbprint | Không chứng minh TLS thực sự cung cấp cert | Test HTTPS/mTLS end-to-end |
| Filter mTLS không áp cho mọi route cần bảo vệ | Có đường API chấp nhận bearer token thường | Phân vùng security matcher và filter chain |
| Bỏ qua audience/scope khi cnf đúng | Client đúng cert nhưng vẫn có thể truy cập sai API | Kiểm tra token và quyền đầy đủ |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** mTLS client authentication và certificate-bound access token khác nhau thế nào?

**Đáp án:** mTLS client authentication xác thực client khi gọi AS. Certificate-bound access token ràng buộc access token với certificate để RS kiểm tra client đang sở hữu private key tương ứng khi gọi API.

**Câu 2.** `cnf.x5t#S256` được tính từ dữ liệu nào?

**Đáp án:** SHA-256 trên DER encoding của toàn bộ X.509 certificate, mã hóa Base64URL và bỏ padding.

**Câu 3.** JWT có chữ ký hợp lệ nhưng certificate ở TLS handshake khác thumbprint trong cnf thì RS xử lý thế nào?

**Đáp án:** Từ chối request với HTTP 401 và `invalid_token` theo RFC 8705.

**Câu 4.** `tls_client_auth` và `self_signed_tls_client_auth` khác nhau ở đâu?

**Đáp án:** PKI method xác minh chain tới CA tin cậy và liên kết client bằng thuộc tính certificate; self-signed method đối chiếu certificate trong client JWKS đã đăng ký.

**Câu 5.** `TokenSettings.x509CertificateBoundAccessTokens(true)` có tự cấu hình TLS listener không?

**Đáp án:** Không. Listener phải được cấu hình để nhận client certificate và AS phải xác minh certificate/client registration.

**Câu 6.** Client có thể dùng access token cũ sau khi thay certificate mới không?

**Đáp án:** Không trên RS thực thi certificate binding, vì thumbprint trong token gắn với certificate cũ. Client cần xin token mới bằng certificate mới.

**Câu 7.** Resource Server có thể chỉ tin header `X-Client-Cert` từ internet không?

**Đáp án:** Không. Certificate metadata phải đến từ TLS layer hoặc proxy tin cậy đã xóa header client tự gửi và truyền metadata qua kênh backend được bảo vệ.

**Câu 8.** Refresh token có nhất thiết chứa `cnf.x5t#S256` không?

**Đáp án:** Không. Theo RFC 8705, refresh token của confidential client được ràng buộc gián tiếp qua client ID và yêu cầu xác thực client bằng mTLS khi trình bày refresh token.

**Câu 9.** Vì sao chỉ test custom filter với mock request attribute chưa đủ?

**Đáp án:** Vì test đó chưa chứng minh TLS handshake thực sự yêu cầu và cung cấp certificate, proxy forwarding an toàn hoặc client sở hữu private key tương ứng.

## 20. Checklist production

- [ ] Client được đăng ký đúng `TLS_CLIENT_AUTH` hoặc `SELF_SIGNED_TLS_CLIENT_AUTH`.
- [ ] PKI trust anchors được giới hạn và quản lý vòng đời.
- [ ] `x509CertificateSubjectDN` hoặc client JWKS/x5c được cấu hình đúng.
- [ ] `TokenSettings.x509CertificateBoundAccessTokens(true)` được bật cho client cần binding.
- [ ] TLS listener yêu cầu/nhận client certificate đúng cách.
- [ ] Không vô tình bắt browser và client thường dùng certificate nếu không cần.
- [ ] Token JWT có `cnf.x5t#S256`; opaque token introspection trả `cnf`.
- [ ] Resource Server lấy certificate từ TLS layer tin cậy.
- [ ] Resource Server tính SHA-256 trên DER certificate và so thumbprint.
- [ ] Missing certificate, missing cnf và mismatch đều bị từ chối.
- [ ] Route yêu cầu mTLS không bị chain khác bỏ qua filter binding.
- [ ] Nếu TLS terminate ở proxy, metadata được chuyển qua trust channel và header spoof bị chặn.
- [ ] Client dùng cùng certificate tại Token Endpoint và Resource Server.
- [ ] Certificate rotation có kế hoạch xin token mới và retire token/cert cũ.
- [ ] Refresh token vẫn yêu cầu client authentication phù hợp.
- [ ] Có chính sách certificate expiry, CRL/OCSP, revocation và compromise response.
- [ ] Có integration test HTTPS/mTLS thực tế và test proxy boundary.
- [ ] Không log private key, access token, refresh token hoặc dữ liệu certificate không cần thiết.

## 21. Tài liệu tham khảo và kết luận

Tài liệu chuẩn và tài liệu framework:

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8705, Section 2 — Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705#section-2)
- [RFC 8705, Section 3 — Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705#section-3)
- [RFC 8705, Section 6 — Implementation Considerations](https://www.rfc-editor.org/rfc/rfc8705#section-6)
- [RFC 8705, Section 7 — Security Considerations](https://www.rfc-editor.org/rfc/rfc8705#section-7)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — TokenSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html)
- [Spring Authorization Server — X509ClientCertificateAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/X509ClientCertificateAuthenticationProvider.html)
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)

**Kết luận:** Certificate-bound access token bổ sung proof-of-possession cho OAuth 2.0: AS ràng buộc token với SHA-256 thumbprint của client certificate, còn RS xác minh certificate trong TLS handshake khớp `cnf.x5t#S256`. Spring Authorization Server hỗ trợ cấu hình này qua `TokenSettings.x509CertificateBoundAccessTokens(true)` cùng mTLS client authentication. Triển khai chỉ hoàn chỉnh khi cả ba lớp hoạt động đúng: AS xác minh client certificate, token mang binding chính xác, và RS thực sự kiểm tra certificate khi nhận request. Quản lý proxy trust, certificate rotation, refresh token và revocation là phần không thể tách rời khi đưa mTLS-bound token vào production.

