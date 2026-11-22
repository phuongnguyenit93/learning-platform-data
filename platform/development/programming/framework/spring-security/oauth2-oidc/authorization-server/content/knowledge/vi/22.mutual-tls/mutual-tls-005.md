# Thiết lập truststore, chuỗi chứng thư và chính sách chấp nhận chứng thư

## 1. Mục tiêu và tình huống thực tế

Trong chương **mTLS** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này tập trung vào việc cấu hình truststore, xác minh chuỗi chứng thư X.509 và quyết định chứng thư client nào được phép dùng để xác thực OAuth 2.0. Đây là một phần của mục tiêu **thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot**.

Giả sử một hệ thống có các dịch vụ backend như Orders Worker, Billing Worker và Reporting Service. Thay vì chia sẻ client secret giữa nhiều môi trường, mỗi workload được cấp một chứng thư client do CA nội bộ phát hành. Khi workload gọi Token Endpoint, TLS handshake yêu cầu client trình chứng thư và chứng minh đang giữ private key tương ứng. Authorization Server xác minh chuỗi chứng thư đi tới CA tin cậy, sau đó đối chiếu danh tính chứng thư với client đã đăng ký.

Một chứng thư được CA tin cậy ký **chưa đồng nghĩa** nó được phép đại diện cho mọi OAuth client. Cần đồng thời kiểm tra:

1. Chứng thư có chuỗi hợp lệ tới trust anchor được cấu hình.
2. Chứng thư còn trong thời hạn, đúng mục đích sử dụng và thỏa chính sách PKI.
3. Danh tính trong Subject DN hoặc Subject Alternative Name khớp client_id đã đăng ký.
4. Client được phép dùng phương thức TLS client authentication và grant đang yêu cầu.
5. Nếu bật certificate-bound Access Token, Resource Server kiểm tra chứng thư khi client trình token.

Sau bài này, bạn có thể:

- Phân biệt keystore, truststore, CA root, intermediate CA và leaf/client certificate.
- Cấu hình TLS client authentication ở Spring Boot và hiểu các chế độ none, want, need.
- Xác minh chuỗi chứng thư theo PKIX và hiểu vai trò của trust anchor.
- Đăng ký client bằng tls_client_auth hoặc self_signed_tls_client_auth trong Spring Authorization Server.
- Áp dụng chính sách Subject DN, SAN, EKU, thời hạn và thu hồi chứng thư.
- Xử lý TLS termination tại reverse proxy, xoay chứng thư và kiểm thử lỗi xác thực.

**Phạm vi phiên bản:** ví dụ Spring Authorization Server tập trung vào dòng 1.5.x và Spring Boot 3.x. Các thuộc tính server.ssl.* minh họa cho embedded Servlet server. Nếu TLS được kết thúc tại ingress, load balancer hoặc service mesh, cấu hình chứng thư và truststore phải đặt tại điểm thực hiện TLS handshake thực tế.

## 2. mTLS diễn ra ở tầng nào?

TLS thông thường xác thực máy chủ với client. Với **mutual TLS (mTLS)**, máy chủ cũng yêu cầu client trình X.509 certificate và chứng minh quyền sở hữu private key tương ứng trong TLS handshake. Việc này xảy ra **trước khi HTTP request tới Spring Security filter chain**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant TLS as TLS Server / Servlet Container
    participant AS as Spring Authorization Server
    C->>TLS: TLS ClientHello
    TLS-->>C: Server Certificate + CertificateRequest
    C->>TLS: Client Certificate chain + CertificateVerify
    TLS->>TLS: Kiểm tra chữ ký, chuỗi và trust anchor
    TLS-->>C: TLS handshake hoàn tất hoặc bị từ chối
    C->>AS: POST /oauth2/token + client_id
    AS->>AS: X509ClientCertificateAuthenticationProvider
    AS->>AS: Đối chiếu chứng thư với RegisteredClient
    AS-->>C: Token response hoặc invalid_client
~~~

Có hai lớp kiểm tra khác nhau:

- **TLS/PKIX validation:** xác minh chứng thư được CA tin cậy ký, chuỗi chứng thư hợp lệ và client thực sự giữ private key.
- **OAuth client identity validation:** Spring Authorization Server xác định client_id, rồi so sánh chứng thư đã nhận với danh tính chứng thư được cấu hình cho RegisteredClient.

Nếu TLS handshake thất bại, ứng dụng có thể không nhận được HTTP request để trả OAuth2 JSON error. Nếu handshake thành công nhưng chứng thư không khớp client_id, OAuth layer có thể trả lỗi xác thực client, thường là invalid_client.

## 3. Keystore và truststore khác nhau như thế nào?

Hai loại kho thường bị nhầm vì đều có thể là file JKS hoặc PKCS12.

| Thành phần | Chứa gì? | Được dùng bởi ai? | Mục đích |
| --- | --- | --- | --- |
| **Server keystore** | Server certificate, private key và có thể có certificate chain | Authorization Server | Chứng minh danh tính máy chủ với client |
| **Client CA truststore** | CA certificate được tin cậy làm trust anchor | TLS server/container | Xác minh client certificate chain |
| **Client keystore** | Client certificate, private key và chain | OAuth2 client | Chứng minh danh tính client và possession private key |
| **Client truststore** | CA/certificate dùng để tin server certificate | OAuth2 client | Xác minh Authorization Server khi client kết nối |

Trong một Authorization Server nhận mTLS:

- Keystore chứa chứng thư máy chủ và private key của máy chủ.
- Truststore chứa CA mà máy chủ chấp nhận để xác minh chứng thư client.
- Client có keystore riêng chứa chứng thư client và private key.
- Client cũng có thể có truststore riêng để xác minh chứng thư máy chủ.

**Đừng nhầm truststore phía client với truststore phía server.** Truststore của client giúp client tin máy chủ; truststore của server giúp server tin CA phát hành chứng thư client.

### 3.1. Trust anchor là gì?

Trong PKI, một certificate path thường có dạng:

~~~text
Client leaf certificate
        |
        v
Intermediate CA certificate
        |
        v
Root CA certificate  <--- trust anchor trong truststore
~~~

Leaf certificate được cấp cho workload. Intermediate CA ký leaf certificate. Root CA thường là điểm tin cậy đã được cài trong truststore. Trong TLS handshake, client thường gửi leaf certificate cùng các intermediate cần thiết; root certificate thường không cần gửi vì server đã có trust anchor.

Truststore không phải danh sách tất cả client certificate đã đăng ký. Nó chủ yếu xác định **CA hoặc certificate nào được tin để xây dựng đường dẫn chứng thư**. Việc leaf certificate thuộc client_id nào vẫn cần bước xác minh danh tính ở OAuth layer.

### 3.2. Tin root CA hay tin trực tiếp leaf certificate?

Với PKI mTLS, mô hình phổ biến là tin một hoặc một số CA nội bộ đã được quản trị. Khi client được cấp lại leaf certificate mới từ cùng CA và giữ danh tính phù hợp, server có thể tiếp tục xác minh chuỗi mà không phải import từng leaf certificate vào truststore.

Import trực tiếp leaf certificate vào truststore có thể tạo kiểu pinning theo certificate cụ thể, nhưng làm quy trình xoay chứng thư và mở rộng client phức tạp hơn. Chỉ chọn mô hình đó khi có chủ đích rõ ràng và hiểu cách TLS provider xây dựng trust path.

## 4. Chuỗi chứng thư X.509 và kiểm tra PKIX

Một chứng thư client hợp lệ không chỉ cần chữ ký của CA. Server phải kiểm tra đường dẫn chứng thư và các điều kiện sử dụng.

| Kiểm tra | Ý nghĩa | Ví dụ lỗi |
| --- | --- | --- |
| Chain signatures | Mỗi certificate được issuer kế tiếp ký hợp lệ | Leaf ký bởi CA không nằm trong chuỗi |
| Trust anchor | Chuỗi kết thúc ở CA/certificate được truststore tin | Root CA chưa được import |
| Validity | Thời điểm hiện tại nằm trong Not Before/Not After | Certificate hết hạn hoặc chưa có hiệu lực |
| Basic Constraints | CA certificate được phép làm CA; leaf không tự nhận vai trò CA | Intermediate có CA=false |
| Key Usage | Key được phép dùng cho mục đích cần thiết | Thiếu digitalSignature khi TLS cần chữ ký |
| Extended Key Usage | Mục đích client authentication được cho phép khi policy yêu cầu | Chỉ có serverAuth, không có clientAuth |
| Name Constraints / Policy | Tuân theo giới hạn tên và chính sách của CA | SAN nằm ngoài namespace được cấp |
| Revocation | Kiểm tra CRL/OCSP nếu deployment yêu cầu | Certificate đã bị thu hồi |

Với client certificate dùng cho TLS client authentication, cần kiểm tra EKU phù hợp với **TLS Web Client Authentication** khi chứng thư/profile có EKU. TLS stack và PKIX provider chịu trách nhiệm xác minh chain, chữ ký, thời hạn và các extension theo cấu hình. OAuth verifier bổ sung việc đối chiếu danh tính client.

**Không tự viết thuật toán xác minh X.509.** Dùng TLS stack và thư viện PKIX đã được kiểm thử. RFC 8705 cũng khuyến nghị dùng implementation X.509 đã được kiểm chứng thay vì tự viết xử lý certificate chain, DN parsing hoặc revocation.

## 5. Tạo truststore cho CA nội bộ

Giả sử PKI team cung cấp:

- partner-root-ca.pem: chứng thư CA gốc đã được xác minh qua kênh quản trị.
- partner-intermediate-ca.pem: intermediate CA (thường client sẽ gửi trong chain).
- client-leaf.pem và client-key.pem: chứng thư và private key của một OAuth client.

Chỉ import CA certificate sau khi xác minh fingerprint qua kênh tin cậy. Không import một certificate chỉ vì nó được đính kèm trong email hoặc lấy từ request TLS.

### 5.1. Tạo PKCS12 truststore và import CA

Ví dụ dùng keytool:

~~~bash
keytool -importcert \
  -alias partner-root-ca \
  -file partner-root-ca.pem \
  -keystore oauth-client-ca-truststore.p12 \
  -storetype PKCS12
~~~

keytool sẽ hỏi mật khẩu truststore tương tác. Trong CI/CD hoặc production, cung cấp secret qua secret manager hoặc cơ chế bảo mật của nền tảng; không commit mật khẩu hoặc truststore chứa dữ liệu nội bộ vào repository công khai.

Kiểm tra nội dung:

~~~bash
keytool -list -v \
  -keystore oauth-client-ca-truststore.p12 \
  -storetype PKCS12
~~~

Kết quả cần xác nhận alias, loại entry và subject/issuer của CA. Truststore thường có entry loại trustedCertEntry cho CA certificate; nó không cần private key của CA.

### 5.2. Kiểm tra chuỗi trước khi đưa vào server

Có thể dùng OpenSSL để kiểm tra một chain test:

~~~bash
openssl verify \
  -CAfile partner-root-ca.pem \
  -untrusted partner-intermediate-ca.pem \
  client-leaf.pem
~~~

Lệnh minh họa kiểm tra chain tới CA được chỉ định. Nó không thay thế việc kiểm tra EKU, SAN, chính sách client_id hoặc cấu hình TLS thực tế của ứng dụng.

### 5.3. Không đưa private key CA vào truststore

Truststore chỉ cần CA certificate công khai làm trust anchor. Private key của Root CA/Intermediate CA phải được giữ trong HSM hoặc hạ tầng PKI có kiểm soát. Nếu private key CA bị lộ, kẻ tấn công có thể phát hành chứng thư giả được tin bởi các hệ thống đã cài CA đó.

## 6. Cấu hình mTLS ở Spring Boot

Spring Boot embedded server cần:

1. Keystore chứa certificate/private key của Authorization Server.
2. Truststore chứa CA được phép phát hành client certificate.
3. Chế độ yêu cầu client certificate phù hợp với các endpoint được phục vụ.

Ví dụ cấu hình YAML cho Spring Boot 3.x:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/auth-server.p12
    key-store-type: PKCS12
    key-store-password: __AUTH_SERVER_KEYSTORE_PASSWORD_FROM_SECRET_STORE__
    key-alias: auth-server
    trust-store: file:/run/secrets/oauth-client-ca-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: __OAUTH_CLIENT_TRUSTSTORE_PASSWORD_FROM_SECRET_STORE__
    client-auth: want
~~~

Trong ví dụ:

- key-store là identity của **server**.
- trust-store là trust anchors để kiểm tra **client certificate chain**.
- client-auth: want yêu cầu client trình certificate nếu có, nhưng cho phép TLS handshake tiếp tục nếu client không gửi certificate.
- Spring Authorization Server sẽ tiếp tục áp dụng client authentication method cho từng RegisteredClient.

Không đặt mật khẩu thật trực tiếp trong application.yml được commit vào Git. Dùng biến môi trường, Kubernetes Secret, Vault, cloud secret manager hoặc secret injection phù hợp.

### 6.1. none, want và need

| Giá trị | Hành vi TLS | Trường hợp sử dụng |
| --- | --- | --- |
| none | Không yêu cầu client certificate | Endpoint không dùng mTLS |
| want | Yêu cầu certificate nhưng vẫn cho handshake tiếp tục nếu client không gửi | Một host/port phục vụ cả browser/public client và mTLS client |
| need | Bắt buộc client certificate trong TLS handshake | Endpoint/port chỉ dành cho kết nối mTLS |

Nếu Authorization Server phục vụ cả browser login, authorization endpoint, public client và confidential client dùng mTLS trên cùng một listener, cấu hình need có thể làm browser/client không có certificate không kết nối được. RFC 8705 mô tả trường hợp hỗ trợ mTLS song song với phương thức client authentication khác nên để handshake có thể tiếp tục khi không có certificate; want là một lựa chọn thường gặp cho embedded server.

Với môi trường yêu cầu mọi request đều mTLS, có thể dùng listener hoặc hostname/port chuyên biệt với need. Khi đó cần thiết kế rõ endpoint discovery, redirect, reverse proxy và client routing.

### 6.2. Truststore không tự quyết định OAuth client nào được đăng nhập

Khi client certificate được CA tin cậy ký, TLS handshake có thể thành công. Nhưng nếu client_id không tồn tại, không đăng ký TLS_CLIENT_AUTH hoặc certificate identity không khớp, OAuth client authentication vẫn phải thất bại.

Đây là lý do không nên dùng truststore như danh sách cấp quyền. Truststore thiết lập **vùng CA được tin cậy**; RegisteredClient và certificate verifier thiết lập **client identity được chấp nhận**.

## 7. Đăng ký client với tls_client_auth

RFC 8705 định nghĩa hai phương thức mTLS OAuth client authentication:

- **tls_client_auth:** PKI method; server xác minh certificate chain tới trust anchor, sau đó đối chiếu một Subject DN hoặc SAN đã đăng ký.
- **self_signed_tls_client_auth:** client dùng self-signed certificate; server đối chiếu certificate nhận được với certificate trong JWKS/JWK Set của client, không dựa trên CA chain theo cách PKI.

Với PKI method, ví dụ Spring Authorization Server:

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

RegisteredClient mtlsClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-worker")
        .clientAuthenticationMethod(ClientAuthenticationMethod.TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .x509CertificateSubjectDN(
                        "CN=orders-worker,OU=Workloads,O=Example,C=VN")
                .build())
        .tokenSettings(TokenSettings.builder()
                .x509CertificateBoundAccessTokens(true)
                .build())
        .build();
~~~

Đây là registration minh họa. Trong production, RegisteredClient phải được lưu trong repository bền vững với ID ổn định. Subject DN phải khớp certificate do PKI cấp theo quy tắc so sánh DN phù hợp; không nên so sánh chuỗi DN bằng cách tự cắt chuỗi tùy tiện.

Các thành phần quan trọng:

- TLS_CLIENT_AUTH yêu cầu client authentication bằng mTLS PKI.
- x509CertificateSubjectDN cấu hình Subject DN dự kiến của client certificate.
- x509CertificateBoundAccessTokens(true) yêu cầu Access Token được ràng buộc với certificate theo RFC 8705.
- CLIENT_CREDENTIALS là grant minh họa cho workload; các grant khác phải được cấp theo policy riêng.

### 7.1. client_id vẫn phải có trong Token Request

RFC 8705 yêu cầu request dùng TLS client authentication phải có client_id. Ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=orders-worker&
scope=orders.read
~~~

Certificate không thay thế client_id. Server dùng client_id để tìm RegisteredClient, rồi kiểm tra certificate được trình trong TLS handshake có khớp với client đó không.

## 8. Chính sách chấp nhận Subject DN và SAN

Sau khi TLS handshake hoàn tất, Spring Authorization Server dùng X509ClientCertificateAuthenticationProvider cho hai phương thức:

- ClientAuthenticationMethod.TLS_CLIENT_AUTH.
- ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH.

Với PKI mTLS, certificate verifier mặc định của Spring Authorization Server kiểm tra Subject Distinguished Name của certificate với RegisteredClient.getClientSettings().getX509CertificateSubjectDN().

### 8.1. Subject DN

Ví dụ DN:

~~~text
CN=orders-worker,OU=Workloads,O=Example,C=VN
~~~

DN có thể có nhiều cách biểu diễn tương đương về mặt cấu trúc. Không nên tự so sánh bằng cách split dấu phẩy hoặc so chuỗi đã tự chuẩn hóa. Dùng cơ chế so sánh X.500/DN có quy tắc rõ ràng và nhất quán với cách đăng ký certificate subject.

DN cũng không phải bí mật. Nếu DN quá chung như CN=service hoặc OU=backend, nhiều client có thể trùng danh tính. PKI cần cấp subject/SAN đủ phân biệt và có quy trình không cho hai client khác nhau dùng chung identity.

### 8.2. Subject Alternative Name

SAN thường phù hợp hơn cho workload identity:

| Loại SAN | Ví dụ | Mục đích |
| --- | --- | --- |
| dNSName | orders-worker.prod.example.internal | Định danh workload bằng DNS name |
| uniformResourceIdentifier | spiffe://example.internal/ns/orders/sa/worker | Định danh workload theo URI |
| iPAddress | 10.20.4.15 | Định danh địa chỉ IP nếu kiến trúc cần |
| rfc822Name | workload@example.internal | Định danh dạng email nếu profile sử dụng |

RFC 8705 quy định PKI method đăng ký đúng một giá trị subject name cho client, có thể là Subject DN hoặc một SAN type được hỗ trợ. Spring Authorization Server mặc định tập trung vào Subject DN; nếu muốn kiểm tra SAN, cần cấu hình custom Certificate Verifier.

### 8.3. Tùy chỉnh Certificate Verifier để kiểm tra SAN

Spring Authorization Server cho phép thay Certificate Verifier của X509ClientCertificateAuthenticationProvider. Ví dụ dưới đây minh họa kiểm tra URI SAN từ một registry server-side:

~~~java
import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.authentication.X509ClientCertificateAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

Consumer<List<AuthenticationProvider>> configureSanVerifier(
        Map<String, String> expectedUriSanByClientId) {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof X509ClientCertificateAuthenticationProvider x509Provider) {
            Consumer<OAuth2ClientAuthenticationContext> verifier = context -> {
                OAuth2ClientAuthenticationToken authentication =
                        context.getAuthentication();
                RegisteredClient registeredClient = context.getRegisteredClient();
                X509Certificate[] chain =
                        (X509Certificate[]) authentication.getCredentials();

                if (chain == null || chain.length == 0) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
                }

                String expectedUriSan =
                        expectedUriSanByClientId.get(registeredClient.getClientId());
                if (expectedUriSan == null) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
                }

                try {
                    X509Certificate leaf = chain[0];
                    Collection<List<?>> sans = leaf.getSubjectAlternativeNames();
                    boolean matched = sans != null && sans.stream().anyMatch(san ->
                            san.size() >= 2
                            && Integer.valueOf(6).equals(san.get(0))
                            && expectedUriSan.equals(san.get(1)));

                    if (!matched) {
                        throw new OAuth2AuthenticationException(
                                new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
                    }
                } catch (CertificateParsingException ex) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT), ex);
                }
            };

            x509Provider.setCertificateVerifier(verifier);
        }
    });
}
~~~

Đăng ký helper này trong cấu hình client authentication của Authorization Server, bên trong SecurityFilterChain:

~~~java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, authorizationServer ->
        authorizationServer.clientAuthentication(clientAuthentication ->
            clientAuthentication.authenticationProviders(
                    configureSanVerifier(expectedUriSanByClientId))));
~~~

Đây là phần ghép vào cấu hình SecurityFilterChain hiện có; ứng dụng vẫn phải gọi http.build() và cấu hình các bean/repository cần thiết.

Đây là đoạn minh họa cho URI SAN (GeneralName type 6), không phải một lớp cấu hình hoàn chỉnh. Trong ứng dụng thật:

- expectedUriSanByClientId phải đến từ cấu hình quản trị đáng tin, không từ HTTP request.
- Chain đã được TLS stack xác minh trước khi Certificate Verifier thực hiện đối chiếu danh tính.
- Cần kiểm thử SAN trùng lặp, thiếu SAN, sai loại SAN, certificate chain rỗng và certificate không đúng client.
- Nếu dùng DNS SAN, GeneralName type là 2; IP SAN là 7. Cần so sánh đúng kiểu và quy tắc của từng loại.
- Không được thay thế PKIX chain validation bằng một phép so sánh SAN.

### 8.4. Client certificate có nhiều SAN

Một certificate có thể chứa nhiều SAN. Chính sách phải chỉ rõ **một SAN nào đại diện cho client_id** và xác minh đúng loại SAN. Không chấp nhận certificate chỉ vì một trong nhiều SAN khớp với một chuỗi chung như example.internal.

## 9. Self-signed TLS client authentication

Không phải hệ thống nào cũng có PKI nội bộ. RFC 8705 có phương thức self_signed_tls_client_auth dành cho client tự ký certificate.

Trong phương thức này:

1. Client đăng ký certificate công khai hoặc JWK Set URL với Authorization Server.
2. Certificate được biểu diễn trong JWK Set thông qua thuộc tính x5c.
3. Client trình certificate trong TLS handshake và chứng minh đang giữ private key.
4. Spring Authorization Server so sánh certificate nhận được với certificate đã đăng ký trong JWK Set.
5. Không thực hiện CA chain validation theo PKI method; identity được xác minh bằng certificate đã đăng ký cho client.

Ví dụ cấu hình client:

~~~java
RegisteredClient selfSignedClient = RegisteredClient.withId("self-signed-client-id")
        .clientId("edge-agent-01")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("telemetry.write")
        .clientSettings(ClientSettings.builder()
                .jwkSetUrl("https://registry.example.com/clients/edge-agent-01/jwks")
                .build())
        .build();
~~~

Đây là ví dụ cấu hình, endpoint JWKS phải được bảo vệ và quản trị. Self-signed method không có nghĩa chấp nhận bất kỳ self-signed certificate nào. Server chỉ chấp nhận certificate khớp với certificate được đăng ký cho đúng client.

Với phương thức này, TLS stack phải được cấu hình để không yêu cầu certificate chain đi tới CA tin cậy như PKI method; việc xác minh certificate được thực hiện bằng cách so khớp với certificate đã đăng ký trong JWKS. Vì vậy, không thể đơn giản dùng cùng cấu hình truststore PKI ở mục 6 rồi mong một self-signed certificate chưa được CA ký vượt qua TLS handshake. Nếu một hệ thống cần đồng thời PKI và self-signed client authentication, hãy thiết kế listener/endpoint hoặc TLS policy riêng cho từng trust model và kiểm thử kỹ đường đi xác thực. Không mở một listener chấp nhận mọi certificate nếu OAuth provider không thực hiện đối chiếu certificate/JWKS bắt buộc.

**Không trộn hai mô hình:**

| PKI TLS client auth | Self-signed TLS client auth |
| --- | --- |
| Trust CA chain bằng truststore | So khớp certificate với JWK Set/x5c đã đăng ký |
| TLS_CLIENT_AUTH | SELF_SIGNED_TLS_CLIENT_AUTH |
| Subject DN/SAN theo client registration | Certificate fingerprint/key material theo JWKS |
| Phù hợp PKI tập trung, CA nội bộ | Phù hợp client có certificate riêng, không duy trì PKI chung |

## 10. Certificate-bound Access Token

mTLS client authentication và certificate-bound Access Token là hai cơ chế **khác nhau nhưng có thể kết hợp**:

- Client authentication xác minh client tại Authorization Server.
- Certificate-bound token ràng buộc Access Token với certificate để Resource Server yêu cầu đúng certificate khi sử dụng token.

Với JWT Access Token, RFC 8705 định nghĩa confirmation claim:

~~~json
{
  "cnf": {
    "x5t#S256": "bwcK0esc3ACC3DB2Y5_lESsXE8o9ltc05O89jdN-dg2"
  }
}
~~~

x5t#S256 là Base64URL không padding của SHA-256 hash trên **DER encoding của X.509 certificate**. Đây không phải JWK thumbprint cnf.jkt của DPoP.

Spring Authorization Server hỗ trợ bật certificate-bound Access Token qua:

~~~java
TokenSettings.builder()
        .x509CertificateBoundAccessTokens(true)
        .build();
~~~

Khi client dùng TLS client authentication tại Token Endpoint, Authorization Server có thể lấy certificate đã xác thực, tính thumbprint và gắn vào token. Với JWT, claim cnf chứa x5t#S256. Với opaque token, binding có thể được cung cấp qua Token Introspection Response.

### 10.1. Resource Server phải kiểm tra certificate nào?

Khi client gọi protected resource, nó phải dùng **cùng certificate** đã được ràng buộc với Access Token. Resource Server lấy client certificate từ TLS layer, tính SHA-256 thumbprint của DER certificate và so sánh với cnf.x5t#S256 trong token hoặc introspection response.

Nếu thumbprint khác, Resource Server từ chối request bằng HTTP 401 và invalid_token theo RFC 8705. Chỉ kiểm tra chữ ký JWT và exp là chưa đủ cho certificate-bound token.

### 10.2. Trust chain tại Resource Server

Trong mô hình certificate-bound token của RFC 8705, Resource Server cần xác minh certificate được trình trên TLS connection là certificate đã gắn với Access Token. RFC không bắt buộc Resource Server phải xác minh lại CA trust chain theo cùng cách Authorization Server đã xác thực client; mục đích ở đây là proof-of-possession bằng certificate đã được token binding chỉ định.

Deployment có thể có chính sách PKI riêng và tiếp tục kiểm tra trust chain tại Resource Server. Điều quan trọng là không bỏ bước **so sánh thumbprint certificate với token binding**. TLS server vẫn phải yêu cầu certificate ở handshake nếu endpoint cần mTLS.

### 10.3. Certificate đổi thì token cũ ra sao?

Access Token gắn với certificate A sẽ không khớp certificate B sau khi client xoay khóa/chứng thư. Client cần xin token mới theo flow được phép với certificate B. Không sửa claim cnf trong token cũ và không chấp nhận certificate mới chỉ vì client_id giống nhau.

## 11. TLS termination tại reverse proxy hoặc load balancer

Trong production, TLS có thể kết thúc ở ingress, load balancer, API gateway hoặc service mesh thay vì JVM Spring Boot. Khi đó:

~~~mermaid
flowchart LR
    C["OAuth Client + client certificate"] -->|"mTLS"| P["Ingress / Reverse Proxy"]
    P -->|"TLS nội bộ + metadata certificate được bảo vệ"| AS["Spring Authorization Server"]
    AS --> F["Spring Security client authentication"]
~~~

Proxy là thành phần thực hiện TLS handshake và phải xác minh certificate chain, nếu dùng PKI method. Nó có thể truyền certificate metadata tới ứng dụng bằng header hoặc request attribute nội bộ.

### 11.1. Rủi ro giả mạo header certificate

Nếu ứng dụng tin header như X-Client-Cert hoặc X-SSL-CERT từ mọi request, client có thể tự gửi header giả để mạo danh certificate. Một reverse proxy an toàn cần:

1. Xóa header certificate do client gửi từ bên ngoài.
2. Tự lấy certificate từ TLS handshake đã xác minh.
3. Ghi đè header bằng giá trị do proxy tạo.
4. Chỉ cho phép backend nhận kết nối từ proxy tin cậy.
5. Bảo vệ kết nối proxy → backend và ngăn truy cập trực tiếp bypass proxy.
6. Định dạng/encoding certificate phải có hợp đồng rõ ràng; tránh parser không nhất quán.

RFC 8705 để việc truyền metadata certificate an toàn giữa TLS terminator và application server ngoài phạm vi chuẩn. Vì vậy đây là trách nhiệm kiến trúc của deployment, không thể giả định framework tự bảo vệ header.

### 11.2. Giữ đúng ranh giới tin cậy

Nếu TLS termination ở proxy nhưng ứng dụng cần certificate chain để xác thực OAuth client, phải dùng cơ chế tích hợp được kiểm soát để đưa certificate đã xác minh vào servlet request/TLS metadata. Không đơn giản bật forward headers hoặc tin header từ Internet.

## 12. Revocation, expiry và xoay chứng thư

### 12.1. Certificate expiry

TLS stack kiểm tra thời hạn certificate trong quá trình path validation. Một certificate hết hạn thường không thể hoàn tất PKI mTLS handshake. Với certificate-bound Access Token, token còn bị ràng buộc với đúng certificate; đổi certificate làm thumbprint không khớp.

### 12.2. Certificate revocation

PKI mTLS có thể kiểm tra trạng thái thu hồi qua CRL hoặc OCSP. Tuy nhiên, **không được giả định chỉ import CA vào truststore là tự động bật mọi hình thức revocation checking**. Cần cấu hình và kiểm thử chính sách revocation ở TLS provider/container hoặc điểm TLS termination.

RFC 8705 để quyết định có kiểm tra certificate revocation hay không cho deployment. Với workload quan trọng, cần xác định:

- CRL/OCSP source và cách cập nhật.
- Hành vi khi responder không truy cập được: fail-open hay fail-closed.
- Cache lifetime và độ trễ thu hồi.
- Cách vận hành khi CA/OCSP/CRL gặp sự cố.
- Quy trình revoke certificate bị lộ và vô hiệu hóa token liên quan.

### 12.3. Xoay certificate không gián đoạn

Một kế hoạch rotation PKI có thể gồm:

1. Cấp certificate mới từ CA được tin cậy.
2. Đảm bảo subject DN hoặc SAN mới khớp registration hoặc cập nhật registration theo quy trình có kiểm soát.
3. Cho client triển khai certificate mới và private key tương ứng.
4. Kiểm thử TLS handshake và OAuth client authentication bằng certificate mới.
5. Phát hành token mới; nếu certificate-bound token bật, token mới gắn với thumbprint mới.
6. Thu hồi hoặc ngừng chấp nhận certificate cũ sau thời gian chuyển tiếp.
7. Xóa CA/certificate cũ khỏi truststore khi không còn client hợp lệ phụ thuộc.

Nếu cần overlap, truststore có thể tạm thời tin cả CA cũ và mới, nhưng chính sách client identity vẫn phải phân biệt rõ certificate nào được phép cho từng client_id. Không để overlap biến thành quyền chấp nhận certificate của mọi workload.

### 12.4. Tách biệt CA theo môi trường

Không nên dùng cùng CA/client certificate cho dev, staging và production nếu có thể tránh. Tách trust anchors giúp giảm ảnh hưởng khi một môi trường test bị xâm phạm. Một certificate staging không nên được chấp nhận tại Authorization Server production.

## 13. Kiểm thử mTLS

Kiểm thử phải bao gồm cả TLS handshake, OAuth client authentication và certificate-bound token ở Resource Server.

### 13.1. Dùng curl với client certificate

Ví dụ PEM:

~~~bash
curl --verbose \
  --cacert auth-server-ca.pem \
  --cert orders-worker.pem \
  --key orders-worker.key \
  --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=orders-worker" \
  --data-urlencode "scope=orders.read" \
  https://auth.example.com:8443/oauth2/token
~~~

--cacert giúp curl xác minh **server certificate**. --cert và --key cung cấp **client certificate/private key** để mTLS. Không nhầm hai chiều trust này.

Nếu dùng PKCS12, curl hỗ trợ cấu hình certificate type tương ứng, nhưng cần kiểm tra bản curl/OpenSSL đang sử dụng và cách truyền password an toàn. Không ghi private key password hoặc client private key vào log.

### 13.2. Kiểm tra TLS handshake

~~~bash
openssl s_client \
  -connect auth.example.com:8443 \
  -servername auth.example.com \
  -cert orders-worker.pem \
  -key orders-worker.key \
  -CAfile auth-server-ca.pem \
  -showcerts
~~~

Lệnh này giúp quan sát handshake và certificate chain. Nó không chứng minh Spring Authorization Server đã ánh xạ đúng client_id hoặc scope; cần gọi Token Endpoint sau đó.

### 13.3. Ma trận kiểm thử

| # | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Client certificate hợp lệ, chain tới root CA trong truststore, DN/SAN đúng client_id | TLS thành công; OAuth client authentication thành công |
| 2 | Không gửi client certificate với client dùng tls_client_auth | TLS có thể tiếp tục nếu client-auth=want; Token Endpoint từ chối client |
| 3 | Certificate do CA không tin cậy ký | PKIX handshake thất bại hoặc request bị từ chối trước OAuth |
| 4 | Certificate chain thiếu intermediate và server không thể xây path | Handshake thất bại |
| 5 | Certificate hết hạn hoặc chưa tới Not Before | Handshake thất bại |
| 6 | Certificate sai EKU/key usage theo policy | Bị từ chối |
| 7 | Chain hợp lệ nhưng Subject DN không khớp RegisteredClient | OAuth authentication trả invalid_client |
| 8 | DN khớp nhưng client_id không tồn tại | OAuth authentication trả invalid_client |
| 9 | Certificate có SAN đúng nhưng verifier chỉ kiểm tra DN | Từ chối; cấu hình SAN verifier nếu policy yêu cầu SAN |
| 10 | Certificate bị thu hồi và revocation checking được bật | Bị từ chối theo chính sách CRL/OCSP |
| 11 | Client dùng self-signed certificate không có trong JWKS | OAuth client authentication thất bại |
| 12 | Certificate-bound token được trình với certificate khác | Resource Server trả 401 invalid_token |
| 13 | Token đúng certificate nhưng sai audience/scope | Resource Server từ chối theo authorization policy |
| 14 | Proxy nhận header certificate do client tự gửi | Proxy phải xóa và ghi đè header; backend không tin giá trị giả |
| 15 | Client xoay certificate nhưng tiếp tục dùng token cũ | Token không khớp thumbprint mới |
| 16 | Backend bị truy cập trực tiếp, bypass proxy | Kết nối bị chặn bởi network policy |

### 13.4. Kiểm tra truststore

Ngoài việc xem truststore bằng keytool, nên test:

- CA root được mong đợi có mặt.
- CA không liên quan không được thêm ngoài ý muốn.
- Certificate mới được cấp từ CA được tin cậy có thể xây chain.
- Certificate từ CA bị loại bỏ bị từ chối sau khi truststore reload/restart theo cách triển khai.
- Các node trong cluster dùng cùng truststore version và chính sách.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| TLS handshake báo unknown_ca | Root/intermediate CA không nằm trong trust path | Kiểm tra truststore và chain client gửi |
| unable to find valid certification path | Thiếu CA, chain sai hoặc truststore không được nạp | keytool -list, kiểm tra cấu hình server.ssl |
| handshake_failure khi client không gửi cert | server.ssl.client-auth=need | Xem endpoint có cần cho client không có certificate truy cập hay không |
| TLS thành công nhưng invalid_client | client_id sai, DN/SAN không khớp hoặc RegisteredClient chưa cho TLS auth | Kiểm tra client registration và certificate verifier |
| Certificate hết hạn | NotAfter đã qua | Cấp và triển khai certificate mới |
| Certificate đúng DN nhưng bị từ chối | EKU, SAN, key usage, revocation hoặc policy khác không hợp lệ | Kiểm tra extension và server TLS logs |
| Self-signed client bị từ chối | Certificate không khớp JWKS/x5c đã đăng ký | Kiểm tra jwkSetUrl, x5c và public key |
| Token response không có cnf.x5t#S256 | Certificate-bound token chưa bật hoặc không có mTLS cert trong token request | Kiểm tra TLS client auth và TokenSettings |
| Resource Server từ chối token mới | Certificate trình ở API khác certificate dùng lúc xin token | Kiểm tra client cert và thumbprint |
| Một node chấp nhận, node khác từ chối | Truststore/registration/CA version không đồng bộ | Kiểm tra rollout và cấu hình cluster |
| Proxy mTLS thành công nhưng app không thấy certificate | Certificate metadata không được chuyển tiếp an toàn | Kiểm tra integration giữa proxy và servlet container |

Không bật debug TLS lâu dài ở production nếu log có thể tiết lộ thông tin chứng thư, handshake hoặc metadata nội bộ. Dùng thời gian ngắn, giới hạn quyền truy cập và tắt sau khi điều tra.

## 15. Checklist chính sách chấp nhận chứng thư

1. **Trust anchor:** chỉ CA đã được phê duyệt mới nằm trong truststore.
2. **Certificate path:** xác minh chain, chữ ký, thời hạn và extension bằng TLS/PKIX implementation.
3. **Client identity:** đối chiếu chính xác client_id với Subject DN hoặc một SAN được chọn.
4. **Key usage/EKU:** certificate được phép dùng cho TLS client authentication.
5. **Revocation:** xác định rõ CRL/OCSP, cache, timeout và hành vi khi responder lỗi.
6. **Client registration:** chỉ RegisteredClient được phép dùng TLS_CLIENT_AUTH hoặc SELF_SIGNED_TLS_CLIENT_AUTH.
7. **Client certificate:** private key được bảo vệ; certificate có vòng đời, rotation và incident procedure.
8. **TLS policy:** dùng TLS version/cipher policy phù hợp; không dùng cấu hình TLS cũ chỉ để tương thích client không còn được hỗ trợ.
9. **Endpoint topology:** chọn want/need và host/port phù hợp; không vô tình chặn browser/public client.
10. **Reverse proxy:** xóa header giả, xác minh certificate ở proxy và bảo vệ proxy-to-app channel.
11. **Certificate-bound token:** nếu bật, Resource Server xác minh x5t#S256 với certificate trên TLS connection.
12. **Cluster consistency:** truststore, client registry, revocation data và certificate verifier đồng bộ.
13. **Audit:** ghi client_id, certificate fingerprint, issuer/subject, kết quả validation và correlation ID; không log private key.
14. **Negative tests:** CA lạ, DN/SAN sai, hết hạn, bị thu hồi, thiếu certificate và certificate-bound mismatch đều được từ chối.

## 16. Bài tập và câu hỏi tự đánh giá

**Bài tập A — Phân biệt kho khóa.** Server có certificate auth-server.p12 và truststore oauth-client-ca.p12. Hãy giải thích file nào chứng minh danh tính server, file nào quyết định CA được phép ký client certificate.

**Bài tập B — Chuỗi chứng thư.** Client gửi leaf và intermediate certificate; truststore có root CA. Mô tả cách TLS server xây dựng path và vì sao client không cần gửi root certificate.

**Bài tập C — want và need.** Authorization Server phục vụ browser login và workload mTLS trên cùng hostname. Chọn client-auth mode và giải thích khi nào nên tách listener/hostname.

**Bài tập D — DN/SAN.** Hai client có cùng CA nhưng SAN URI khác nhau. Thiết kế mapping client_id → SAN và test certificate của client A không thể đăng nhập dưới client_id của B.

**Bài tập E — Self-signed.** Một workload dùng self-signed certificate. Giải thích vì sao TLS_CLIENT_AUTH PKI và SELF_SIGNED_TLS_CLIENT_AUTH có quy trình tin cậy khác nhau.

**Bài tập F — Certificate-bound token.** Token có cnf.x5t#S256 của certificate A. Client xoay sang certificate B nhưng vẫn dùng token cũ. Giải thích kết quả ở Resource Server.

**Câu hỏi ôn tập:**

1. Keystore và truststore khác nhau như thế nào?
2. Trust anchor là gì? Vì sao truststore thường chứa CA certificate thay vì private key?
3. Chuỗi leaf → intermediate → root được xác minh ở tầng nào?
4. Truststore hợp lệ có tự động cấp quyền OAuth client cho mọi certificate từ CA đó không?
5. TLS_CLIENT_AUTH khác SELF_SIGNED_TLS_CLIENT_AUTH ở điểm nào?
6. Vì sao RFC 8705 yêu cầu client_id trong request dùng mTLS client authentication?
7. Spring Authorization Server mặc định đối chiếu thuộc tính nào cho PKI mTLS?
8. Khi nào cần custom Certificate Verifier để kiểm tra SAN?
9. server.ssl.client-auth=want khác need ra sao?
10. Vì sao không thể tin header certificate từ request bên ngoài khi TLS termination tại proxy?
11. cnf.x5t#S256 được tính từ dữ liệu nào?
12. Certificate-bound Access Token khác DPoP-bound Access Token như thế nào?
13. Vì sao cần chính sách CRL/OCSP rõ ràng thay vì chỉ import CA vào truststore?
14. Khi client xoay certificate, cần xử lý token cũ và registration như thế nào?

## 17. Tài liệu tham khảo

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [Spring Authorization Server — Configuration Model: Mutual-TLS Client Authentication](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot — SSL Configuration](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Java keytool Documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)

**Ghi nhớ:** Truststore quyết định **CA/certificate path nào được tin ở tầng TLS**. Sau đó Spring Authorization Server còn phải xác minh **certificate đó thuộc client_id nào và có được RegisteredClient cho phép hay không**. PKI mTLS dùng chain trust và Subject DN/SAN; self-signed mTLS dùng certificate đã đăng ký qua JWKS/x5c. Nếu bật certificate-bound Access Token, Resource Server phải so sánh cnf.x5t#S256 với certificate thực tế trên TLS connection. Chỉ khi các lớp này được cấu hình và kiểm thử cùng nhau, mTLS mới tạo thành một ranh giới tin cậy có thể vận hành an toàn.
