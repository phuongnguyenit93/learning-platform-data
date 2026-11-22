# Gia hạn, thu hồi chứng thư và kiểm thử lỗi xác thực mTLS

> **Chương: mTLS.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**: học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm là vòng đời chứng thư X.509 cho OAuth client authentication: **gia hạn có overlap, thu hồi khi compromise, kiểm tra trạng thái chứng thư và kiểm thử lỗi từ TLS handshake tới OAuth token endpoint**.

## 1. Phân biệt hai chứng thư trong kết nối mTLS

Trong TLS thông thường, server trình chứng thư server để client xác minh hostname và chuỗi tin cậy. Với **mutual TLS (mTLS)**, server còn yêu cầu client trình chứng thư X.509 và chứng minh đang nắm private key tương ứng ngay trong TLS handshake.

Trong OAuth có hai vị trí cần phân biệt:

- **Client certificate:** chứng thư do OAuth client trình cho Authorization Server ở token endpoint để xác thực bằng `tls_client_auth` hoặc `self_signed_tls_client_auth`.
- **Server certificate:** chứng thư của Authorization Server (hoặc reverse proxy kết thúc TLS) mà OAuth client xác minh khi kết nối tới `https://login.example.vn`.

Nếu API cũng yêu cầu mTLS, Resource Server có thể yêu cầu client certificate riêng hoặc cùng certificate theo chính sách triển khai. Với certificate-bound access token, certificate dùng ở token endpoint được ràng buộc với token và phải được trình lại khi client gọi protected resource.

Ví dụ xuyên suốt:

| Thành phần | Giá trị minh họa | Vai trò |
|---|---|---|
| Authorization Server | `https://login.example.vn` | Nhận token request và xác thực OAuth client |
| OAuth client | `billing-job` | Confidential client gọi Client Credentials grant |
| Client certificate | `CN=billing-job,OU=Integrations,O=Example` | Chứng minh danh tính client ở TLS handshake |
| CA nội bộ | `Example Integration CA` | Trust anchor cấp và ký client certificate theo PKI |
| Resource Server | `https://api.example.vn` | Xác minh access token và certificate binding nếu bật |
| Server certificate | SAN `DNS:login.example.vn` | Cho client xác minh đúng Authorization Server |

**mTLS client authentication và certificate-bound access token là hai cơ chế riêng, có thể triển khai cùng nhau hoặc độc lập.** mTLS client authentication chứng minh danh tính OAuth client với AS. Certificate-bound access token ràng buộc token đã phát với certificate để Resource Server kiểm tra possession khi client gọi API. RFC 8705 định nghĩa cả hai cơ chế.

## 2. Những lớp kiểm tra của chứng thư client

Một client certificate chỉ được chấp nhận khi vượt qua cả kiểm tra ở tầng TLS và kiểm tra danh tính OAuth client.

### 2.1. TLS handshake và xác minh X.509

TLS implementation/container thực hiện các kiểm tra mật mã và PKI, thường gồm:

1. Chứng thư nằm trong thời hạn `notBefore`–`notAfter`.
2. Chuỗi chứng thư nối được tới trust anchor mà server cho phép.
3. Chữ ký của từng certificate trong chain hợp lệ.
4. Basic Constraints, Key Usage và Extended Key Usage phù hợp vai trò client certificate.
5. Critical extensions và path constraints được xử lý đúng.
6. Chính sách revocation (CRL/OCSP hoặc cơ chế tương đương) được áp dụng nếu deployment yêu cầu.
7. Client chứng minh sở hữu private key tương ứng trong handshake.

Client certificate thường cần Extended Key Usage `clientAuth` và Key Usage phù hợp chữ ký handshake theo thuật toán được chọn. Không dùng chứng thư chỉ có `serverAuth` làm client certificate.

### 2.2. Ánh xạ certificate sang RegisteredClient

Sau handshake thành công, Spring Authorization Server xác định OAuth client từ `client_id`, rồi kiểm tra certificate nhận được có khớp cấu hình client đó không.

Với `tls_client_auth` theo PKI, RFC 8705 cho phép liên kết client với một Subject DN hoặc Subject Alternative Name đã đăng ký. Spring Authorization Server mặc định so sánh Subject DN của certificate với `RegisteredClient.getClientSettings().getX509CertificateSubjectDN()`. Nếu cần so SAN hoặc thuộc tính khác, cấu hình custom certificate verifier.

Với `self_signed_tls_client_auth`, server so certificate client nhận trong handshake với certificate được công bố trong JWK Set của client, qua `jwks_uri`/`jwkSetUrl`; certificate được biểu diễn bằng `x5c` trong JWK.

| Phương pháp | Nguồn tin cậy | Cách nhận diện client | Cách xoay certificate |
|---|---|---|---|
| `tls_client_auth` | PKI chain tới CA được tin cậy | Subject DN hoặc SAN đã đăng ký | Cấp certificate mới từ CA tin cậy; giữ identity DN/SAN phù hợp hoặc cập nhật registration |
| `self_signed_tls_client_auth` | JWK Set đã đăng ký của client | Certificate trong `x5c` khớp certificate ở handshake | Cập nhật JWK Set với certificate mới và quản lý overlap/cache |

Không được coi TLS handshake thành công là đủ để xác thực `client_id`. Một certificate hợp lệ do CA nội bộ cấp nhưng thuộc `reporting-job` không thể tự nhận danh tính `billing-job`.

## 3. Vòng đời certificate và các mốc cần quản lý

Certificate có ngày hết hạn hữu hạn. Vận hành mTLS cần quản lý từ lúc tạo key pair, cấp certificate, triển khai, theo dõi, gia hạn, thu hồi cho đến khi xóa trust cũ.

| Giai đoạn | Việc cần làm | Bằng chứng cần lưu |
|---|---|---|
| Provisioning | Tạo private key, CSR và cấp certificate từ CA hoặc self-sign theo policy | Owner, client ID, serial, issuer, SAN/subject, fingerprint |
| Enrollment | Đăng ký identity/certificate với OAuth client | Registration version, trust profile, thời điểm hiệu lực |
| Deployment | Cài certificate/private key vào keystore hoặc secret store | Phiên bản secret, node/pod đã nhận |
| Monitoring | Theo dõi ngày hết hạn, CRL/OCSP, lỗi handshake và thay đổi CA | Expiry metrics, cảnh báo, audit |
| Renewal | Cấp và triển khai certificate mới trước khi certificate cũ hết hạn | Fingerprint cũ/mới, thời điểm overlap |
| Revocation | Thu hồi certificate bị lộ, mất private key hoặc không còn được phép | Serial, lý do, thời điểm revoke, propagation |
| Retirement | Gỡ certificate cũ khỏi keystore/JWKS/trust store sau thời gian chuyển tiếp | Xác nhận không còn traffic dùng certificate cũ |

Nên có inventory theo `client_id`, issuer, serial number, SHA-256 fingerprint, subject/SAN, ngày bắt đầu/kết thúc, nơi lưu private key và người chịu trách nhiệm. Không ghi private key hoặc password keystore vào inventory/log.

### 3.1. Gia hạn trước hạn, không chờ handshake lỗi

Đặt lịch cảnh báo theo nhiều mốc, ví dụ 60/30/14/7 ngày trước khi hết hạn. Khoảng thời gian cụ thể phụ thuộc quy trình cấp certificate và thời gian rollout. Theo dõi cả certificate ở:

- Client gọi token endpoint.
- Authorization Server public endpoint/reverse proxy.
- Resource Server yêu cầu mTLS.
- CA/intermediate certificate và trust store.
- Certificate được publish trong JWK Set với `self_signed_tls_client_auth`.

Certificate hết hạn có thể khiến TLS handshake thất bại trước khi ứng dụng nhận HTTP request. Khi đó client thường chỉ thấy lỗi TLS như `certificate expired`, `bad certificate` hoặc `handshake failure`; sẽ không có OAuth JSON `invalid_client` vì request chưa tới token endpoint.

## 4. Gia hạn client certificate theo phương pháp PKI

Với `tls_client_auth`, certificate client được xác minh theo PKI chain và identity đăng ký. RFC 8705 cho phép client gia hạn bằng certificate mới từ CA tin cậy mà **không cần thay đổi dữ liệu xác thực ở AS** nếu certificate mới giữ cùng Subject DN đã đăng ký (hoặc SAN theo cấu hình triển khai).

### 4.1. Quy trình rotation có overlap

Giả sử `billing-job` đang dùng certificate `C0`, sắp hết hạn. Quy trình an toàn:

1. **Kiểm kê:** xác nhận `client_id`, Subject DN/SAN, issuer, serial, fingerprint, ngày hết hạn và tất cả nơi đang cài `C0`.
2. **Tạo key pair mới:** tạo private key mới trong secret store/keystore của client. Không tái sử dụng private key cũ chỉ để đơn giản hóa rotation.
3. **Tạo CSR:** gửi CSR tới đúng CA profile; giữ Subject DN/SAN theo identity đã đăng ký.
4. **Cấp và kiểm tra `C1`:** kiểm tra chain, SAN/DN, EKU `clientAuth`, Key Usage, validity, algorithm và fingerprint.
5. **Cài `C1` ở chế độ song song:** deploy certificate/key mới tới một nhóm instance hoặc canary. Giữ `C0` còn hiệu lực trong giai đoạn chuyển đổi.
6. **Kiểm thử token endpoint:** xác nhận `C1` xác thực đúng `billing-job`; không dùng certificate của client khác.
7. **Chuyển traffic:** chuyển toàn bộ client instance sang `C1`, quan sát lỗi TLS và OAuth authentication.
8. **Xác nhận không còn dùng `C0`:** kiểm tra telemetry theo client identity/fingerprint nếu có, không log certificate/private key nguyên văn.
9. **Thu hồi hoặc retire `C0`:** nếu rotation bình thường, thực hiện theo policy CA; nếu certificate cũ bị compromise, thu hồi khẩn cấp và xử lý token liên quan.
10. **Dọn secret cũ:** xóa key cũ khỏi runtime, secret manager và backup theo chính sách retention.

**Overlap phải có giới hạn thời gian.** Nếu certificate cũ bị nghi lộ private key, không giữ nó hoạt động để tiện chuyển đổi; ưu tiên thu hồi ngay và chấp nhận downtime/reauthorization có kiểm soát.

### 4.2. Cùng Subject DN không có nghĩa là cùng certificate

Trong PKI `tls_client_auth`, AS mặc định Spring có thể nhận diện client theo Subject DN đã đăng ký. Vì vậy certificate mới do CA tin cậy cấp, có cùng Subject DN và vượt kiểm tra chain, có thể tiếp tục xác thực cùng client.

Tuy nhiên, certificate-bound access token được ràng buộc với **thumbprint của certificate cụ thể**, không chỉ Subject DN. Nếu token `T0` có `cnf.x5t#S256` ứng với `C0`, client không thể dùng `T0` với `C1` dù cả hai certificate có cùng DN. Khi chuyển sang `C1`, cần lấy access token mới bằng certificate mới và dùng certificate mới tại Resource Server. RFC 8705 coi access token gắn certificate cũ là không dùng được sau khi client cập nhật certificate.

### 4.3. Nếu SAN thay đổi

Nếu custom verifier ánh xạ client bằng SAN (ví dụ `URI:spiffe://example/billing-job` hoặc `DNS:billing-job.internal`), certificate mới phải giữ SAN identity đúng theo registry. Nếu SAN thay đổi, cần cập nhật policy/registration có kiểm soát trước khi chuyển traffic. Không dùng wildcard SAN hoặc substring match tùy tiện.

## 5. Gia hạn self-signed certificate

Với `self_signed_tls_client_auth`, AS không dựa vào CA công khai/nội bộ để nhận diện certificate client. Spring Authorization Server dùng `ClientSettings.getJwkSetUrl()` để tải JWK Set của client và tìm certificate phù hợp với certificate nhận từ TLS handshake; certificate được thể hiện trong JWK `x5c`.

Quy trình rotation:

1. Client tạo key pair mới và certificate self-signed mới.
2. Client cập nhật JWK Set tại `jwks_uri`, thêm JWK chứa certificate `C1` (và giữ `C0` trong thời gian overlap nếu policy cho phép).
3. Đảm bảo JWK Set có public key parameters khớp certificate trong `x5c`, có `kid` ổn định cho từng key và endpoint HTTPS đáng tin.
4. Kiểm tra cache/refresh behavior của AS đối với `jwks_uri`; không giả định cập nhật JWK Set có hiệu lực tức thì trên mọi node.
5. Chuyển client instance sang `C1`, kiểm tra token endpoint và downstream resource.
6. Khi không còn cần `C0`, xóa JWK cũ khỏi set và xác nhận AS không còn chấp nhận nó.
7. Nếu `C0` bị compromise, thu hồi registration/credential theo quy trình khẩn cấp; không chờ hết cache overlap thông thường.

Ví dụ cấu hình client (Spring Authorization Server 1.5.x):

~~~java
RegisteredClient selfSignedClient = RegisteredClient
        .withId("registration-billing-job")
        .clientId("billing-job")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("invoices.read")
        .clientSettings(ClientSettings.builder()
                .jwkSetUrl("https://billing.example.vn/.well-known/mtls-jwks.json")
                .build())
        .build();
~~~

JWK Set cần có certificate trong `x5c`; ví dụ rút gọn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "billing-cert-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_KEY_MODULUS_BASE64URL",
      "e": "AQAB",
      "x5c": ["BASE64_DER_CERTIFICATE_WITHOUT_PEM_MARKERS"]
    }
  ]
}
~~~

Đây là JSON minh họa; `x5c` chứa certificate DER được mã hóa Base64 theo JWK, không phải private key. Không đăng public JWK Set nhầm với keystore chứa private key. Hạn chế truy cập và bảo vệ integrity/availability của endpoint JWK Set; nếu attacker thay được certificate list, họ có thể ảnh hưởng việc xác thực client.

## 6. Thu hồi certificate: CRL, OCSP và xử lý khẩn cấp

Gia hạn xử lý certificate sắp hết hạn; **thu hồi (revocation)** xử lý certificate không còn được tin cậy trước `notAfter`, ví dụ:

- Private key bị lộ hoặc thất lạc.
- Client instance/nhà cung cấp bị compromise.
- Certificate cấp sai subject/SAN hoặc nhầm tenant.
- Client bị dừng hợp tác hoặc không còn quyền kết nối.
- CA/intermediate bị compromise hoặc thay đổi trust policy.
- Phát hiện sử dụng certificate trái phép.

### 6.1. CRL

Certificate Revocation List (CRL) là danh sách do CA ký, chứa serial number của certificate đã bị thu hồi. TLS validator lấy CRL theo CRL Distribution Point hoặc cấu hình ngoài băng và kiểm tra serial certificate.

Ưu điểm:

- Có thể phân phối theo file/cache, phù hợp mạng nội bộ không cần gọi responder cho từng handshake.
- Có thể kiểm tra nhiều serial trong một danh sách.
- Hữu ích khi có quy trình phát hành CRL định kỳ và delta CRL.

Giới hạn:

- CRL có độ trễ từ lúc revoke tới lúc bản CRL mới được phân phối.
- CRL lớn làm tăng chi phí tải và kiểm tra.
- CRL cũ/hết hạn hoặc không truy cập được cần có policy rõ: fail closed hay soft-fail.
- CA/intermediate và client certificate có thể có CRL Distribution Point khác nhau.

### 6.2. OCSP

Online Certificate Status Protocol (OCSP) cho phép hỏi responder trạng thái của certificate theo issuer/serial. Response có thể là `good`, `revoked` hoặc `unknown`, có chữ ký và thời hạn hiệu lực.

Ưu điểm là trạng thái có thể mới hơn CRL đầy đủ. Tuy nhiên cần vận hành OCSP responder, cache, timeout, stapling (nếu nền tảng hỗ trợ) và chính sách khi responder không truy cập được.

`unknown` không đồng nghĩa `good`. Với endpoint cấp token có rủi ro cao, không nên tự động chấp nhận certificate khi không xác định được trạng thái nếu policy yêu cầu kiểm tra revocation nghiêm ngặt.

### 6.3. Revocation check là quyết định deployment

RFC 8705 cho phép kiểm tra revocation trong PKI method nhưng để deployment quyết định có kiểm tra và kiểm tra như thế nào. Do đó:

- Không giả định chỉ cấu hình `trust-store` là đã bật CRL/OCSP.
- Không giả định Spring Authorization Server tự tải CRL/OCSP và kiểm tra mọi certificate.
- Không nhầm custom `CertificateVerifier` của Spring (dùng để kiểm tra nội dung/identity certificate sau handshake) với việc xác minh chain/revocation ở TLS stack.
- Xác định thành phần chịu trách nhiệm: embedded server, reverse proxy/load balancer, Java TLS provider, PKI agent hoặc custom trust manager.
- Kiểm thử thực tế bằng certificate đã revoke và đo thời gian propagation.

Nếu dùng TLS termination ở proxy, chính proxy có thể là nơi xác minh chain/revocation. Ứng dụng phía sau phải nhận certificate metadata qua kênh nội bộ được bảo vệ, không tin header do Internet client tự gửi.

### 6.4. Quy trình thu hồi khi private key compromise

1. Xác nhận `client_id`, certificate serial/fingerprint, issuer và thời điểm compromise.
2. Đánh dấu credential bị thu hồi ở CA/PKI hoặc loại certificate khỏi JWK Set/registration tùy phương pháp.
3. Chặn certificate ở TLS ingress/trust policy và mọi Resource Server yêu cầu mTLS.
4. Ngăn client tiếp tục lấy access token/refresh token bằng certificate cũ.
5. Thu hồi authorization/access token/refresh token liên quan theo chính sách; certificate revocation **không tự động xóa mọi token đã phát** ở các hệ thống không kiểm tra revocation liên tục.
6. Nếu access token certificate-bound, bảo đảm Resource Server từ chối certificate bị revoke; nếu dùng introspection, cân nhắc thu hồi token/authorization để `active=false`.
7. Cấp certificate mới sau khi đã khắc phục nguyên nhân, cập nhật registration/JWKS, kiểm thử lại và giám sát.
8. Lưu audit, thời gian phát hiện, thời gian chặn ở AS/RS và các request bị ảnh hưởng.

## 7. Certificate-bound access token và ảnh hưởng của rotation

Khi bật certificate-bound access token, AS tính SHA-256 thumbprint của certificate client ở token endpoint và ràng buộc vào token.

Với JWT access token, RFC 8705 dùng claim:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "billing-job",
  "aud": ["invoices-api"],
  "scope": "invoices.read",
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_OF_CERTIFICATE_DER"
  }
}
~~~

`x5t#S256` là Base64URL không padding của SHA-256 trên DER encoding của certificate. Với opaque token, thông tin binding có thể được trả trong introspection response dưới `cnf.x5t#S256`.

### 7.1. Cấu hình Spring Authorization Server

Ví dụ `RegisteredClient` dùng PKI mTLS và yêu cầu access token certificate-bound:

~~~java
RegisteredClient mtlsClient = RegisteredClient
        .withId("registration-billing-job")
        .clientId("billing-job")
        .clientAuthenticationMethod(ClientAuthenticationMethod.TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("invoices.read")
        .clientSettings(ClientSettings.builder()
                .x509CertificateSubjectDN(
                        "CN=billing-job,OU=Integrations,O=Example")
                .build())
        .tokenSettings(TokenSettings.builder()
                .x509CertificateBoundAccessTokens(true)
                .build())
        .build();
~~~

`x509CertificateBoundAccessTokens(true)` bật certificate binding cho access token được cấp qua client. Cấu hình này không thay thế TLS server/client certificate setup, trust store, certificate lifecycle hoặc Resource Server verification. Cần xác nhận token thực tế chứa `cnf.x5t#S256`.

### 7.2. Resource Server phải so khớp certificate

Khi nhận request tới API:

1. Lấy access token và certificate client từ TLS implementation layer.
2. Xác minh access token (JWT signature/issuer/audience/expiry hoặc introspection).
3. Tính SHA-256 thumbprint của certificate client đang dùng.
4. So sánh với `cnf.x5t#S256` trong access token/introspection response.
5. Kiểm tra certificate chain/revocation theo policy Resource Server.
6. Nếu thumbprint không khớp, từ chối `401 invalid_token`; sau đó mới xét scope và authorization nghiệp vụ.

Không lấy certificate từ `X-Client-Cert`/`X-Forwarded-Client-Cert` do request Internet tự gửi. Nếu proxy kết thúc mTLS, phải xóa header giả từ client và chỉ proxy tin cậy được phép ghi metadata certificate; đường proxy→application cũng phải được bảo vệ và xác thực.

### 7.3. Rotation làm token cũ không còn dùng được với certificate mới

Giả sử `C0` có thumbprint `H0`, token `T0` chứa `cnf.x5t#S256=H0`. Sau khi client đổi sang `C1` có thumbprint `H1`:

- `T0 + C0`: có thể tiếp tục hợp lệ nếu certificate/token chưa hết hạn và chưa bị revoke.
- `T0 + C1`: bị từ chối vì `H1 != H0`.
- Token `T1` phát sau khi client xác thực bằng `C1`: được bind với `H1`, dùng cùng `C1` tại Resource Server.

Do đó kế hoạch rotation cần xem **token TTL, refresh token, certificate overlap và thời điểm chuyển traffic**. Nếu certificate cũ bị compromise, không giữ đường dùng `T0/C0` chỉ để tránh cấp token lại.

### 7.4. Refresh token cũng cần binding

Với confidential client dùng `tls_client_auth`, refresh token được ràng buộc gián tiếp với client ID và yêu cầu client xác thực bằng certificate khi gửi refresh request. Với public client dùng certificate-bound token, RFC 8705 khuyến nghị ràng buộc refresh token với certificate và kiểm tra binding khi refresh. Cần xác minh behavior của AS triển khai; không suy rằng `x509CertificateBoundAccessTokens(true)` tự cấu hình mọi chính sách refresh-token binding cho mọi loại client.

## 8. Cấu hình TLS trong Spring Boot

Ví dụ dưới đây minh họa embedded server giữ server certificate riêng và yêu cầu client certificate ở chế độ **optional** để nhiều OAuth client authentication methods có thể cùng tồn tại:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/etc/example/as-server.p12
    key-store-type: PKCS12
    key-store-password: ${AS_KEYSTORE_PASSWORD}
    key-alias: authorization-server
    trust-store: file:/etc/example/client-ca-trust.p12
    trust-store-type: PKCS12
    trust-store-password: ${CLIENT_CA_TRUST_PASSWORD}
    client-auth: want
    enabled-protocols:
      - TLSv1.3
      - TLSv1.2
~~~

Giải thích:

- `key-store` chứa private key và server certificate chain mà Authorization Server trình cho client.
- `trust-store` chứa CA/intermediate trust anchors cho client certificate PKI.
- `client-auth: want` yêu cầu client trình certificate nhưng cho phép TLS handshake tiếp tục nếu không có certificate. Điều này hữu ích khi AS đồng thời hỗ trợ `client_secret_basic`, `private_key_jwt`, public clients hoặc endpoint không cần mTLS.
- `client-auth: need` yêu cầu certificate ở tầng TLS cho mọi kết nối tới connector. Chỉ dùng khi toàn bộ traffic qua connector thực sự phải có certificate; nếu không, browser login, health check hoặc client authentication method khác có thể thất bại trước khi HTTP request tới Spring.
- `enabled-protocols` giới hạn TLS versions theo chính sách triển khai.

**Phân biệt hai kiểu lỗi:** với `want`, client không gửi certificate có thể hoàn tất handshake nhưng OAuth client authentication cho một `RegisteredClient` yêu cầu `tls_client_auth` sẽ thất bại (thường `invalid_client`). Với `need`, thiếu certificate làm TLS handshake bị từ chối; không có OAuth response JSON.

Không đặt password keystore trong source control. Dùng secret manager, file permission chặt, rotation và audit. Cấu hình trust store phải chứa đúng CA được phép phát hành client certificate, không import bừa certificate của mọi đối tác.

### 8.1. Cấu hình trust riêng cho client certificate

Nên tách server keystore và client CA trust store. Tránh dùng một file PKCS12 vừa chứa server private key vừa làm trust store chung nếu điều đó khiến quyền truy cập hoặc trust anchor quá rộng.

Khi CA intermediate được thay:

1. Thêm CA mới vào trust store trước thời điểm chuyển certificate.
2. Triển khai trust store tới toàn bộ AS nodes/proxies.
3. Xác minh chain mới qua canary.
4. Chuyển client certificate sang CA mới.
5. Chỉ gỡ CA cũ sau khi mọi client hợp lệ đã chuyển và không còn chain cũ cần hỗ trợ.

Đây là CA rollover; khác với gia hạn một client certificate dưới cùng CA.

## 9. Tùy chỉnh kiểm tra SAN trong Spring Authorization Server

Với `tls_client_auth`, Spring Authorization Server mặc định xác minh Subject DN theo `x509CertificateSubjectDN`. Nếu tổ chức định danh client bằng SAN URI/DNS, cần custom verifier. Cấu hình phải giữ nguyên provider mặc định và bổ sung kiểm tra identity phù hợp; không thay thế chain validation do TLS layer thực hiện.

Ví dụ cấu trúc mở rộng (Spring Authorization Server 1.5.x; `certificatePolicy` là service do ứng dụng định nghĩa):

~~~java
@Bean
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        CertificatePolicy certificatePolicy) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.clientAuthentication(clientAuthentication ->
                            clientAuthentication.authenticationProviders(providers ->
                                    providers.forEach(provider -> {
                                        if (provider instanceof
                                                X509ClientCertificateAuthenticationProvider x509) {
                                            x509.setCertificateVerifier(context ->
                                                    certificatePolicy.verify(context));
                                        }
                                    }))))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}
~~~

`CertificatePolicy.verify(context)` cần:

- Lấy `RegisteredClient` từ context đã xác thực theo `client_id`.
- Lấy certificate chain đã được TLS layer xác minh từ authentication credentials.
- Đọc SAN đúng loại (DNS, URI, email hoặc IP) theo policy; không dùng substring match.
- So khớp với identity được đăng ký/duyệt cho client.
- Từ chối nếu SAN thiếu, trùng lặp hoặc không đúng expected identity.
- Không log certificate/private key hoặc toàn bộ authentication credentials.

Đoạn code trên thể hiện extension point; implementation `CertificatePolicy` phải ném lỗi xác thực phù hợp khi không khớp và cần được kiểm thử theo đúng phiên bản Spring. Không viết parser X.509 thủ công để xác minh chain; dùng TLS/X.509 library đã được kiểm chứng.

## 10. TLS termination tại reverse proxy/load balancer

Nhiều hệ thống kết thúc TLS ở ingress/load balancer rồi chuyển HTTP nội bộ tới Spring Boot. Với mTLS, proxy nhìn thấy certificate client trong handshake, nhưng ứng dụng phía sau có thể không còn trực tiếp thấy TLS peer certificate.

Nếu AS cần certificate cho OAuth `tls_client_auth` hoặc certificate-bound access token, cần truyền metadata certificate an toàn:

1. Proxy phải xác minh client certificate/chain và revocation theo policy.
2. Proxy xóa mọi header certificate do client gửi từ Internet.
3. Proxy tự tạo header nội bộ chứa certificate/metadata đã xác minh.
4. Chỉ proxy tin cậy mới được kết nối tới application; bảo vệ proxy→application bằng mạng riêng và/hoặc mTLS.
5. Application chỉ tin metadata từ proxy đã xác thực; không nhận request direct bypass proxy.
6. Đồng bộ cách tính fingerprint và format certificate giữa proxy, AS và Resource Server.
7. Kiểm thử spoofed header, proxy failover và certificate rotation.

RFC 8705 để ngoài phạm vi chuẩn cách metadata certificate được truyền an toàn từ intermediary tới ứng dụng. Đây là trách nhiệm thiết kế của deployment. Không chỉ bật `server.forward-headers-strategy` rồi mặc định mọi header certificate là đáng tin.

## 11. Kiểm thử lỗi xác thực mTLS

Kiểm thử cần phân biệt lỗi ở **TLS handshake**, lỗi ánh xạ certificate→OAuth client và lỗi certificate-bound token tại Resource Server.

### 11.1. Dùng OpenSSL kiểm tra handshake

Lệnh minh họa kiểm tra server certificate và trình client certificate:

~~~bash
openssl s_client \
  -connect login.example.vn:443 \
  -servername login.example.vn \
  -cert billing-client.crt \
  -key billing-client.key \
  -CAfile server-ca.pem \
  -verify_return_error \
  -showcerts
~~~

Kiểm tra ngày hiệu lực, subject, issuer, SAN, EKU và fingerprint certificate client:

~~~bash
openssl x509 -in billing-client.crt -noout \
  -subject -issuer -serial -dates -ext subjectAltName \
  -ext extendedKeyUsage -fingerprint -sha256
~~~

Không đưa private key lên command output hoặc ticket. Lệnh trên chỉ kiểm tra handshake/chứng thư; nó không chứng minh `client_id` khớp RegisteredClient hoặc token đã được cấp đúng.

### 11.2. Gọi token endpoint bằng mTLS

Với client đăng ký `tls_client_auth` và Client Credentials grant:

~~~bash
curl --verbose \
  --cacert server-ca.pem \
  --cert billing-client.crt \
  --key billing-client.key \
  --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data "grant_type=client_credentials&client_id=billing-job&scope=invoices.read" \
  https://login.example.vn/oauth2/token
~~~

Dùng certificate/key giả ở môi trường test; không đưa private key hoặc secret production vào shell history. Khi thành công, response có access token. Nếu bật certificate-bound access token, kiểm tra JWT `cnf.x5t#S256` hoặc introspection `cnf` khớp fingerprint certificate đang dùng.

### 11.3. Ma trận negative tests

| STT | Tình huống | Lớp lỗi | Kết quả mong đợi |
|---|---|---|---|
| 1 | Không gửi client certificate khi connector dùng `want` | OAuth client authentication | TLS có thể thành công; token endpoint từ chối client mTLS, không cấp token |
| 2 | Không gửi certificate khi connector dùng `need` | TLS handshake | Handshake thất bại; không có OAuth JSON response |
| 3 | Certificate do CA không tin cậy cấp | TLS chain validation | Handshake bị từ chối |
| 4 | Certificate hết hạn | TLS validity | Handshake bị từ chối |
| 5 | Certificate chưa tới `notBefore` | TLS validity | Handshake bị từ chối |
| 6 | Certificate đã bị revoke và revocation check bật | TLS/PKI revocation | Handshake bị từ chối theo policy |
| 7 | OCSP responder/CRL không truy cập được | Revocation dependency | Fail-open/fail-closed đúng policy đã định; có metric/alert |
| 8 | Certificate thiếu intermediate | TLS path building | Bị từ chối nếu không dựng được chain hợp lệ |
| 9 | Certificate có EKU không gồm `clientAuth` | TLS certificate usage | Bị từ chối |
| 10 | Certificate có Subject DN khác RegisteredClient | OAuth certificate verifier | Handshake có thể thành công; OAuth client authentication thất bại (`invalid_client`) |
| 11 | Certificate đúng CA nhưng thuộc client khác | OAuth client binding | Không được mạo danh `client_id` |
| 12 | SAN sai khi dùng custom verifier | OAuth certificate verifier | Từ chối |
| 13 | Client gửi `client_id` không tồn tại | OAuth client lookup | `invalid_client` |
| 14 | Client registration yêu cầu `tls_client_auth`, nhưng gửi secret thay certificate | OAuth authentication method | Từ chối |
| 15 | Certificate mới cùng DN do CA tin cậy cấp | PKI rotation | Có thể xác thực nếu chain, validity và policy hợp lệ |
| 16 | Certificate self-signed không nằm trong client JWKS | Self-signed verifier | Từ chối certificate |
| 17 | Certificate mới đã publish nhưng AS dùng JWKS cache cũ | JWKS rotation | Kiểm tra cache/refresh; không chấp nhận ngoài policy |
| 18 | Dùng access token bound với C0 nhưng gọi API bằng C1 | Resource Server token binding | `401 invalid_token` do thumbprint mismatch |
| 19 | Token bound với C0, C0 đã revoke nhưng RS không kiểm revocation | Resource Server revocation | Test phải phát hiện gap; cấu hình RS/TLS để từ chối |
| 20 | Certificate server hết hạn hoặc hostname không khớp | Client xác minh AS | Client từ chối kết nối AS |
| 21 | TLS proxy gửi certificate header giả | Proxy trust boundary | Application từ chối request không đến từ proxy tin cậy |
| 22 | Proxy không chuyển certificate metadata | Proxy integration | OAuth client mTLS thất bại rõ ràng, không fallback âm thầm |
| 23 | Rotation giữa nhiều AS pods | Cluster consistency | Tất cả node chấp nhận đúng trust version, không có node dùng cấu hình stale |
| 24 | Certificate bị revoke trong khi client đang có access token | Token lifecycle | Ngăn lấy token mới; xử lý token cũ theo revocation/binding policy |

### 11.4. Phân biệt TLS error và OAuth error

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `handshake_failure`, `bad_certificate`, `certificate_expired` | TLS server không chấp nhận certificate hoặc chain | TLS logs, trust store, validity, EKU, CRL/OCSP |
| Kết nối thành công nhưng trả `invalid_client` | Certificate không khớp client registration hoặc thiếu certificate ở chế độ `want` | RegisteredClient, `client_id`, DN/SAN verifier |
| Token endpoint trả `unauthorized_client` | Client đã xác thực nhưng grant không được đăng ký | `authorizationGrantType` của RegisteredClient |
| Token cấp thành công nhưng API trả `401 invalid_token` | Certificate-bound token không khớp certificate tại Resource Server | `cnf.x5t#S256`, TLS peer certificate, thumbprint |
| API trả `403` | Token và binding hợp lệ nhưng scope/authorization không đủ | Scope, audience, tenant và API policy |
| Chỉ một pod lỗi | Trust store, certificate/JWKS cache hoặc proxy config không đồng nhất | Kiểm tra từng node và rollout version |

## 12. Các lỗi vận hành thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gia hạn certificate nhưng client vẫn nhận `invalid_client` | DN/SAN mới không còn khớp registration hoặc CA mới chưa được trust | Kiểm tra identity và triển khai CA trust trước |
| Certificate mới dùng được token endpoint nhưng API từ chối | Access token vẫn bind với thumbprint cũ | Lấy access token mới bằng certificate mới |
| Thu hồi certificate nhưng client vẫn lấy được token | Revocation check chưa bật hoặc node đang dùng CRL/cache cũ | Kiểm tra TLS revocation policy và propagation |
| CRL mới chưa có hiệu lực trên một pod | CRL cache/refresh không đồng nhất | Đồng bộ refresh và giám sát CRL version/nextUpdate |
| OCSP timeout gây lỗi ngẫu nhiên | Responder/network không ổn định hoặc policy soft-fail không rõ | Đặt timeout/cache/failure policy và alert |
| `need` làm health check/login hỏng | Connector bắt mọi client phải trình certificate | Dùng `want` cho connector hỗn hợp hoặc tách endpoint/connector mTLS |
| Certificate header bị spoof | App tin forwarded header từ nguồn Internet | Strip header tại edge, chỉ tin proxy xác thực |
| Self-signed rotation không nhận certificate mới | JWKS cache chưa refresh hoặc JWK `x5c` không khớp key | Kiểm tra cache, `kid`, `x5c` và public key parameters |
| Server cert mới bị client từ chối | Thiếu intermediate hoặc client chưa trust CA mới | Deploy full chain, trust overlap và test hostname |
| Token còn dùng được sau khi revoke client | RS chỉ xác minh JWT offline, không kiểm tra binding/revocation | TTL phù hợp, introspection/revocation propagation và mTLS check |

## 13. Runbook gia hạn và thu hồi

### 13.1. Gia hạn theo kế hoạch

- [ ] Xác định client, certificate serial/fingerprint, Subject DN/SAN, issuer và nơi cài.
- [ ] Tạo private key mới trong secret store/keystore, tạo CSR và nhận certificate.
- [ ] Kiểm tra chain, validity, EKU, Key Usage, SAN/DN và fingerprint.
- [ ] Nếu đổi CA, thêm trust anchor mới trước khi deploy certificate mới.
- [ ] Nếu dùng self-signed, cập nhật JWK Set `x5c` và kiểm tra cache/overlap.
- [ ] Deploy canary với certificate mới, test token endpoint và Resource Server.
- [ ] Chuyển toàn bộ traffic, quan sát lỗi theo client ID/node.
- [ ] Lấy token mới nếu access token đang bind với certificate cũ.
- [ ] Retire/revoke certificate cũ theo policy và xóa private key cũ an toàn.
- [ ] Cập nhật inventory và audit.

### 13.2. Thu hồi khẩn cấp

- [ ] Xác định certificate/serial/fingerprint và client bị ảnh hưởng.
- [ ] Revoke tại CA hoặc gỡ certificate khỏi JWK Set/registration.
- [ ] Cập nhật CRL/OCSP/trust policy và xác nhận toàn bộ ingress/AS/RS nhận trạng thái mới.
- [ ] Chặn certificate tại TLS layer; không chỉ xóa file ở một client pod.
- [ ] Ngăn refresh/token requests tiếp theo bằng credential bị compromise.
- [ ] Thu hồi token/authorization liên quan theo chính sách và kiểm tra token đã phát ở Resource Server.
- [ ] Cấp key/certificate mới qua quy trình sạch, xác minh identity và scope.
- [ ] Theo dõi request tiếp tục dùng certificate cũ và lưu audit sự cố.

## 14. Câu hỏi tự kiểm tra

1. Vì sao TLS handshake thành công chưa đủ để chứng minh certificate thuộc đúng `client_id`?
2. Khác nhau giữa `tls_client_auth` và `self_signed_tls_client_auth` là gì?
3. Với PKI mTLS, vì sao certificate mới cùng Subject DN có thể tiếp tục xác thực client mà không đổi registration?
4. Vì sao access token certificate-bound vẫn không dùng được với certificate mới dù DN giống nhau?
5. Revocation checking của PKI mTLS có tự động bật chỉ vì đã cấu hình trust store không?
6. CRL và OCSP khác nhau ở cách phân phối/truy vấn trạng thái certificate như thế nào?
7. Khi `client-auth: want`, lỗi thiếu certificate khác gì `client-auth: need`?
8. Nếu certificate bị revoke nhưng Resource Server chỉ kiểm tra `cnf.x5t#S256`, còn thiếu kiểm tra nào?
9. Vì sao certificate-bound refresh token cần được ràng buộc/kiểm tra khi refresh?
10. Khi TLS kết thúc tại reverse proxy, vì sao không được tin trực tiếp `X-Forwarded-Client-Cert` từ Internet?
11. Nếu dùng `self_signed_tls_client_auth`, `x5c` trong client JWK Set đóng vai trò gì?
12. Làm thế nào để chứng minh rotation đã hoàn tất trên toàn bộ AS pod và Resource Server?

## Tài liệu tham khảo

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): PKI/self-signed methods, certificate-bound tokens, expiration, refresh token binding, TLS termination và security considerations.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html): certificate path validation, CRL và X.509 PKI.
- [RFC 6960 — X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP)](https://www.rfc-editor.org/rfc/rfc6960.html): truy vấn trạng thái certificate qua OCSP.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication và token endpoint.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `tls_client_auth`, `self_signed_tls_client_auth`, `X509ClientCertificateAuthenticationProvider`, SAN verifier và certificate-bound access token.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `ClientSettings` và `TokenSettings`.
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): X.509 authentication và TLS container integration.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles và cấu hình TLS trong ứng dụng Spring Boot.
