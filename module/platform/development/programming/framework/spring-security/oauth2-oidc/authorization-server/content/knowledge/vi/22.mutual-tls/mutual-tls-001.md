# Xác thực client bằng chứng thư X.509

## 1. Bối cảnh và mục tiêu

Trong **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** xây dựng bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, confidential client phải chứng minh danh tính khi gọi Token Endpoint. Cách phổ biến là dùng client secret hoặc JWT assertion được ký bằng private key. Với **mutual TLS (mTLS)**, client chứng minh quyền sở hữu private key tương ứng với chứng thư số **X.509** ngay trong TLS handshake. Authorization Server xác minh chứng thư và ràng buộc nó với một OAuth client đã đăng ký.

Ví dụ xuyên suốt: dịch vụ <code>orders-worker</code> gọi <code>https://auth.example.com/oauth2/token</code> để đổi Client Credentials grant lấy access token. Thay vì gửi <code>client_secret</code>, dịch vụ thiết lập TLS bằng client certificate do CA nội bộ cấp. Authorization Server kiểm tra chuỗi chứng thư, xác định client từ <code>client_id</code>, sau đó đối chiếu subject DN hoặc thuộc tính chứng thư đã đăng ký. Khi cần chống đánh cắp access token, Authorization Server còn có thể ràng buộc token với chính chứng thư đó; Orders API yêu cầu client trình cùng chứng thư khi gọi API.

Sau bài học, bạn có thể:

1. Giải thích TLS client authentication khác OAuth client authentication ở lớp giao thức như thế nào.
2. Phân biệt hai phương thức RFC 8705: <code>tls_client_auth</code> dựa trên PKI và <code>self_signed_tls_client_auth</code> dựa trên chứng thư tự ký đã đăng ký.
3. Cấu hình trust store, client certificate và TLS listener để hỗ trợ mTLS trong Spring Boot.
4. Đăng ký client bằng <code>ClientAuthenticationMethod.TLS_CLIENT_AUTH</code> hoặc <code>SELF_SIGNED_TLS_CLIENT_AUTH</code>.
5. Hiểu vai trò của <code>X509ClientCertificateAuthenticationProvider</code>, certificate verifier và <code>RegisteredClient</code>.
6. Tùy chỉnh xác minh Subject Alternative Name (SAN) mà vẫn bảo toàn liên kết certificate với client.
7. Bật certificate-bound access token và hiểu claim <code>cnf.x5t#S256</code>.
8. Xây dựng kiểm tra proof-of-possession ở Resource Server.
9. Thiết kế certificate rotation, revocation, TLS termination qua reverse proxy và kiểm thử vận hành.

**Phạm vi phiên bản:** Ví dụ dùng Spring Authorization Server 1.5.x, Spring Security 6.x và Servlet stack. <code>X509ClientCertificateAuthenticationProvider</code> được hỗ trợ từ Spring Authorization Server 1.3. Các bản Spring Security mới tích hợp Authorization Server có thể thay package hoặc API; đối chiếu version đang chạy. Các cấu hình TLS của máy chủ/ingress là một phần riêng của hạ tầng, không được tạo ra chỉ bằng Java DSL của Authorization Server.

## 2. mTLS là gì?

### 2.1. TLS một chiều và mutual TLS

Trong HTTPS thông thường, server trình chứng thư TLS để client xác minh mình đang kết nối tới đúng máy chủ. Với mTLS, server còn yêu cầu client trình chứng thư X.509 và chứng minh quyền sở hữu private key tương ứng trong quá trình bắt tay TLS.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant S as Authorization Server
    C->>S: ClientHello
    S-->>C: ServerHello + server certificate
    C->>S: Xác minh server certificate
    S-->>C: CertificateRequest (yêu cầu client certificate)
    C->>S: Client certificate chain
    C->>S: CertificateVerify (chứng minh có private key)
    C->>S: Finished
    S->>S: Kiểm tra TLS client certificate theo trust policy
    S-->>C: TLS handshake hoàn tất
    C->>S: HTTP request bên trong TLS
~~~

Sơ đồ giản lược TLS 1.2/1.3. Trình tự thông điệp thực tế phụ thuộc phiên bản TLS và handshake mode. Điểm cốt lõi là chứng thư được trình ở **lớp TLS**, trước khi HTTP request tới Token Endpoint được xử lý. Server không chỉ nhận một chuỗi certificate do client tự gửi trong form; TLS stack kiểm tra bằng chứng sở hữu private key thông qua handshake.

### 2.2. Vì sao mTLS phù hợp cho OAuth client?

- Client không phải gửi shared secret trong từng request.
- Private key có thể nằm trong keystore, HSM hoặc thiết bị bảo vệ khóa; ứng dụng chỉ yêu cầu thao tác ký trong TLS handshake.
- Chứng thư có thời hạn, issuer, subject, SAN, key usage và chuỗi CA để quản lý danh tính.
- Authorization Server có thể ánh xạ chứng thư tới đúng <code>client_id</code>.
- Khi kết hợp certificate-bound access token, Resource Server có thể yêu cầu cùng chứng thư để ngăn bên khác dùng token bị đánh cắp.

mTLS thường phù hợp với service-to-service, workload trong môi trường doanh nghiệp, API đối tác hoặc hệ thống có PKI. Với ứng dụng trình duyệt người dùng thông thường, yêu cầu certificate toàn cục có thể làm trình duyệt hiện hộp thoại chọn chứng thư và gây trải nghiệm không mong muốn.

### 2.3. Hai lớp xác minh phải phân biệt

| Lớp | Câu hỏi | Thành phần thực hiện |
| --- | --- | --- |
| TLS client authentication | Client có chứng minh quyền sở hữu private key và trình certificate được TLS server chấp nhận không? | TLS stack, trust store, certificate path validation. |
| OAuth client authentication | Certificate vừa nhận có được đăng ký cho đúng <code>client_id</code> đang yêu cầu token không? | Spring Authorization Server, <code>X509ClientCertificateAuthenticationProvider</code>, certificate verifier. |

TLS handshake thành công **chưa đủ** để kết luận đó là <code>orders-worker</code>. Một certificate có thể hợp lệ trong PKI nhưng thuộc client khác. Authorization Server vẫn phải ràng buộc chứng thư với client đã đăng ký. RFC 8705 yêu cầu request mTLS phải có <code>client_id</code>; server dùng ID đó tìm cấu hình client rồi đối chiếu chứng thư.

## 3. Hai phương thức mTLS trong RFC 8705

RFC 8705 định nghĩa hai cách dùng X.509 certificate làm OAuth client credential:

| Phương thức | Mã <code>client_authentication_method</code> | Cách xác minh |
| --- | --- | --- |
| PKI Mutual-TLS | <code>tls_client_auth</code> | TLS server xác minh certificate chain tới CA tin cậy; Authorization Server đối chiếu Subject DN hoặc SAN với danh tính client đã đăng ký. |
| Self-Signed Certificate Mutual-TLS | <code>self_signed_tls_client_auth</code> | Không dựa vào CA công khai để xác minh chain; Authorization Server đối chiếu certificate trình trong handshake với certificate/JWK đã đăng ký cho client, thường qua JWKS có <code>x5c</code>. |

### 3.1. PKI Mutual-TLS: <code>tls_client_auth</code>

Đây là phương thức phù hợp khi tổ chức có CA nội bộ hoặc PKI được quản lý:

1. CA tin cậy cấp client certificate cho <code>orders-worker</code>.
2. Client cài certificate và private key vào keystore/HSM.
3. TLS listener của Authorization Server yêu cầu client certificate và tin cậy CA phát hành.
4. TLS stack xác minh chain, thời hạn, chữ ký, key usage và các điều kiện PKI được cấu hình.
5. Spring Authorization Server nhận certificate chain sau handshake.
6. Provider xác định client bằng <code>client_id</code> và mặc định so Subject Distinguished Name (DN) của certificate với <code>ClientSettings.x509CertificateSubjectDN</code>.

RFC 8705 cho phép liên kết theo một giá trị Subject DN hoặc một giá trị SAN. Trong Spring Authorization Server 1.5.x, verifier mặc định của <code>tls_client_auth</code> dùng Subject DN. Nếu muốn dùng SAN DNS/URI/IP/email, cần cấu hình certificate verifier tùy chỉnh.

### 3.2. Self-Signed Certificate Mutual-TLS: <code>self_signed_tls_client_auth</code>

Phương thức này hữu ích khi không muốn vận hành CA cho từng client. Client đăng ký public certificate của mình với Authorization Server, trực tiếp hoặc qua JWKS URI:

1. Client tạo cặp khóa và self-signed X.509 certificate.
2. Client đăng ký certificate trong JWK Set; JWK tương ứng chứa certificate trong trường <code>x5c</code>.
3. RegisteredClient lưu <code>jwkSetUrl</code> trỏ tới JWKS của client (hoặc cấu hình JWK Set theo cơ chế quản lý client).
4. Khi TLS handshake, client trình đúng certificate và chứng minh sở hữu private key.
5. Spring Authorization Server lấy JWK Set đã đăng ký, tìm certificate khớp với certificate vừa trình.

Trong phương thức này, server không xác minh chuỗi certificate tới CA công khai. Trust được hình thành từ việc **certificate đã được đăng ký cho client cụ thể** và TLS handshake chứng minh quyền sở hữu private key. Việc đăng ký/chấp nhận JWKS URI phải được quản lý chặt chẽ; không để client tùy ý trỏ tới URL nội bộ hoặc endpoint có thể gây SSRF.

### 3.3. Chọn phương thức nào?

| Tiêu chí | PKI | Self-signed |
| --- | --- | --- |
| Hạ tầng CA | Cần CA/trust anchors được quản lý. | Không cần CA chung cho client. |
| Xác minh chain | Có. | Không dựa vào CA chain; xác minh certificate khớp đăng ký. |
| Ràng buộc client | Subject DN hoặc SAN đã đăng ký. | Certificate/JWK đã đăng ký, thường qua <code>x5c</code>. |
| Gia hạn certificate | Có thể cấp certificate mới cùng subject từ CA tin cậy, theo chính sách. | Cập nhật certificate trong JWK Set/JWKS URI và đồng bộ cache. |
| Vận hành | Quản trị CA, trust store, CRL/OCSP và vòng đời chứng thư. | Quản trị đăng ký certificate, JWKS URI, rotation và bảo vệ private key client. |

Không chọn self-signed chỉ để bỏ qua kiểm tra certificate. Phương thức này thay mô hình tin cậy CA bằng mô hình đăng ký/pinning certificate theo client; vẫn phải kiểm tra certificate đúng client và có private key tương ứng.

## 4. Certificate X.509 và các thuộc tính cần kiểm tra

### 4.1. Subject Distinguished Name

Subject DN mô tả chủ thể của certificate, ví dụ:

~~~text
CN=orders-worker,OU=Platform,O=Example Corp,C=VN
~~~

Trong ví dụ PKI mặc định của Spring Authorization Server, giá trị DN kỳ vọng được lưu ở:

~~~java
ClientSettings.builder()
    .x509CertificateSubjectDN(
        "CN=orders-worker,OU=Platform,O=Example Corp,C=VN")
    .build();
~~~

DN là định danh được biểu diễn theo cú pháp phân biệt tên X.500/X.509. Không so chuỗi DN bằng một quy tắc tự chế hoặc giả định mọi CA serialize DN theo đúng một thứ tự. Khi có yêu cầu liên thông nhiều CA, phải thống nhất cách chuẩn hóa và so sánh DN theo quy tắc phù hợp.

### 4.2. Subject Alternative Name (SAN)

SAN có thể chứa một hoặc nhiều định danh:

| Loại SAN | Ví dụ | Tình huống |
| --- | --- | --- |
| <code>dNSName</code> | <code>orders-worker.internal.example.com</code> | Định danh workload/service theo DNS. |
| <code>uniformResourceIdentifier</code> | <code>spiffe://example.org/ns/prod/sa/orders-worker</code> | Định danh workload theo URI/SPIFFE. |
| <code>iPAddress</code> | <code>10.20.4.15</code> | Định danh theo địa chỉ IP trong môi trường có quản lý IP ổn định. |
| <code>rfc822Name</code> | <code>orders-worker@example.com</code> | Định danh dạng email khi policy yêu cầu. |

RFC 8705 yêu cầu liên kết một giá trị subject name được chọn cho client. Nếu dùng SAN, cần xác định chính xác loại SAN và giá trị mong đợi; không chấp nhận bất kỳ SAN nào chỉ vì certificate có một SAN hợp lệ.

### 4.3. Certificate path và key usage

Với PKI, TLS stack nên kiểm tra tối thiểu:

- Certificate chưa hết hạn và chưa có hiệu lực sai thời điểm.
- Chuỗi certificate kết thúc ở trust anchor được phê duyệt.
- Chữ ký trên certificate chain hợp lệ.
- Basic Constraints và path length phù hợp với vai trò CA/leaf.
- Extended Key Usage phù hợp client authentication (thường là <code>clientAuth</code>).
- Key Usage phù hợp với thao tác ký/chứng minh sở hữu key theo thuật toán.
- Certificate revocation status được kiểm tra theo chính sách CRL/OCSP hoặc cơ chế quản lý PKI tương ứng.

Không chỉ dựa vào Subject DN để xác thực certificate. Một CA tin cậy rộng có thể cấp một certificate khác có cùng subject; RFC 8705 khuyến nghị giới hạn trust anchors vào các CA có chính sách cấp phát phù hợp yêu cầu bảo mật.

## 5. Cấu hình TLS listener trong Spring Boot

Spring Authorization Server xử lý OAuth client authentication sau khi TLS handshake hoàn tất. Cấu hình TLS được đặt ở embedded server, load balancer hoặc ingress.

### 5.1. Yêu cầu client certificate ở TLS layer

Ví dụ cấu hình PKI cho Spring Boot:

~~~properties
# Server certificate: client phải xác minh được Authorization Server.
server.ssl.enabled=true
server.ssl.key-store=classpath:auth-server.p12
server.ssl.key-store-password=${AS_TLS_KEYSTORE_PASSWORD}
server.ssl.key-store-type=PKCS12

# Trust store chứa CA được phép cấp client certificate.
server.ssl.trust-store=classpath:oauth-client-ca.p12
server.ssl.trust-store-password=${CLIENT_CA_TRUSTSTORE_PASSWORD}
server.ssl.trust-store-type=PKCS12

# Yêu cầu certificate nhưng cho phép handshake tiếp tục nếu client không gửi.
server.ssl.client-auth=want
~~~

Các giá trị mật khẩu là biến cấu hình lấy từ secret manager, không phải giá trị literal để commit vào Git. Trust store phải chỉ chứa CA phù hợp cho OAuth client authentication; không đưa một tập CA rộng không cần thiết vào đó.

Các chế độ thường gặp:

| <code>server.ssl.client-auth</code> | Hành vi |
| --- | --- |
| <code>none</code> | Không yêu cầu client certificate. |
| <code>want</code> | Yêu cầu client certificate nhưng cho phép client không gửi và tiếp tục handshake. |
| <code>need</code> | Bắt buộc client certificate để hoàn tất handshake. |

Nếu Authorization Server đồng thời phục vụ browser login, authorization endpoint và client thông thường, <code>want</code> thường phù hợp hơn việc bắt buộc certificate trên mọi request. Với endpoint mTLS riêng, có thể dùng listener/hostname/port riêng và chính sách TLS bắt buộc certificate.

### 5.2. Tránh bắt trình duyệt người dùng phải chọn certificate

Nếu TLS server yêu cầu client certificate trên cùng hostname phục vụ login, trình duyệt có thể hiển thị hộp thoại chọn certificate cho người dùng. RFC 8705 cho phép tách các endpoint mTLS bằng hostname/port riêng và công bố <code>mtls_endpoint_aliases</code> trong metadata. Client dùng mTLS chọn alias token/introspection/revocation phù hợp; browser authorization endpoint vẫn dùng hostname thông thường.

Spring Authorization Server cung cấp endpoint path qua <code>AuthorizationServerSettings</code>, nhưng việc tách hostname, TLS connector, routing và công bố alias metadata là trách nhiệm cấu hình triển khai. Không giả định chỉ bật <code>ClientAuthenticationMethod.TLS_CLIENT_AUTH</code> là tự tạo một TLS listener riêng.

### 5.3. TLS termination ở reverse proxy/load balancer

Trong môi trường Kubernetes/cloud, TLS có thể kết thúc tại ingress hoặc load balancer trước khi request tới Spring Boot. Khi đó:

- Proxy phải yêu cầu và xác minh client certificate theo policy.
- Proxy phải xóa mọi header certificate do client gửi từ Internet trước khi tự ghi metadata đã xác minh.
- Kênh proxy → ứng dụng phải được bảo vệ, ưu tiên mTLS nội bộ và network policy.
- Ứng dụng chỉ tin metadata từ proxy được xác thực; không chấp nhận request đi thẳng từ mạng không tin cậy.
- Cơ chế chuyển certificate chain phải giữ đúng định dạng và danh tính; kiểm thử cách container/Spring nhận certificate.

Spring Authorization Server mặc định lấy client certificate từ TLS request context của Servlet. Nếu proxy chỉ thêm một header như <code>X-Forwarded-Client-Cert</code>, cần adapter đáng tin cậy để chuyển dữ liệu vào đúng request attribute/flow; không được đọc header tùy ý do caller có thể giả mạo. RFC 8705 không chuẩn hóa cơ chế chuyển certificate metadata giữa proxy và ứng dụng.

## 6. Đăng ký client dùng tls_client_auth

### 6.1. RegisteredClient

Ví dụ confidential client dùng Client Credentials:

~~~java
RegisteredClient ordersWorker = RegisteredClient
    .withId("orders-worker-record-001")
    .clientId("orders-worker")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .scope("orders.write")
    .clientSettings(ClientSettings.builder()
        .x509CertificateSubjectDN(
            "CN=orders-worker,OU=Platform,O=Example Corp,C=VN")
        .build())
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

Ví dụ lược bỏ repository và các bean hạ tầng. <code>RegisteredClient.id</code> là ID nội bộ của bản ghi; <code>clientId</code> là định danh OAuth mà client gửi. Phương thức xác thực phải khớp certificate mapping đã đăng ký. Khi dùng PKI default verifier, <code>x509CertificateSubjectDN</code> là giá trị DN mong đợi.

### 6.2. HTTP request tại Token Endpoint

Client dùng certificate và private key trong TLS handshake, sau đó gửi OAuth request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=orders-worker&scope=orders.read
~~~

Request mTLS bắt buộc có <code>client_id</code>. Client không gửi <code>client_secret</code> để thay thế cho certificate authentication. Server xác định client từ ID rồi xác minh certificate của handshake có thuộc client đó không.

Ví dụ gọi bằng curl:

~~~bash
curl --request POST \
  --url https://auth.example.com/oauth2/token \
  --cert ./orders-worker.crt \
  --key ./orders-worker.key \
  --cacert ./auth-server-ca.pem \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'client_id=orders-worker' \
  --data-urlencode 'scope=orders.read'
~~~

<code>--cert</code>/<code>--key</code> dùng certificate và private key phía client; <code>--cacert</code> dùng CA để client xác minh certificate của Authorization Server. Không dùng <code>-k</code>/<code>--insecure</code> trong kiểm thử bảo mật vì nó tắt xác minh server certificate.

### 6.3. Provider mặc định xử lý ra sao?

Spring Authorization Server cấu hình <code>OAuth2ClientAuthenticationFilter</code> với một <code>AuthenticationManager</code> chứa các provider mặc định, trong đó có <code>X509ClientCertificateAuthenticationProvider</code>. Provider này nhận certificate chain từ TLS request, tìm RegisteredClient theo <code>client_id</code>, rồi xác minh certificate theo phương thức đã đăng ký.

Với <code>tls_client_auth</code>, verifier mặc định kiểm tra Subject DN của certificate so với <code>RegisteredClient.getClientSettings().getX509CertificateSubjectDN()</code>. Nếu certificate không có hoặc không khớp client, client authentication thất bại với OAuth error <code>invalid_client</code>.

Không cần tự viết filter đọc certificate và tự đánh dấu client đã authenticated. Dùng cơ chế client authentication của Authorization Server để giữ đúng thứ tự kiểm tra và kết quả OAuth.

## 7. Đăng ký client dùng self_signed_tls_client_auth

### 7.1. ClientSettings với JWKS URI

Ví dụ:

~~~java
RegisteredClient partner = RegisteredClient
    .withId("partner-record-001")
    .clientId("partner-service")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("partner.data.read")
    .clientSettings(ClientSettings.builder()
        .jwkSetUrl(
            "https://keys.partner.example.com/oauth-client.jwks")
        .build())
    .build();
~~~

JWK Set tại URL đã đăng ký phải chứa public certificate của client trong trường <code>x5c</code> của một JWK phù hợp. Phần tử certificate đầu tiên trong <code>x5c</code> phải khớp public key được biểu diễn bởi các tham số JWK. Spring Authorization Server dùng JWK Set này để đối chiếu certificate được trình trong TLS handshake.

### 7.2. Bảo vệ JWKS URI của client

JWKS URI là một nguồn dữ liệu xác định danh tính client, nên cần:

- HTTPS và hostname đã được kiểm soát.
- Allow-list domain hoặc policy đăng ký URI; tránh server-side request forgery (SSRF).
- Không cho redirect sang IP/private network hoặc host không tin cậy.
- Cache và cập nhật theo quy tắc rõ ràng, có xử lý lỗi/timeout.
- Không đưa private key vào JWK Set; chỉ công bố certificate/public key.
- Kiểm toán thay đổi certificate/JWKS URI và quy trình phê duyệt.

Không dùng <code>jwkSetUrl</code> tùy ý do client gửi trong request token. Đây là cấu hình đã được đăng ký cho client trong Authorization Server.

### 7.3. So sánh với PKI

Với self-signed method, server không kiểm tra certificate chain qua CA trust store như PKI method; thay vào đó certificate phải khớp certificate đã đăng ký. Nếu tùy chỉnh certificate verifier, phải giữ cả cơ chế đối chiếu certificate/JWK cần thiết. Không áp dụng một SAN verifier tự viết rồi vô tình bỏ mất kiểm tra pinning certificate mặc định của self-signed method.

## 8. Tùy chỉnh certificate verifier trong Spring Authorization Server

### 8.1. Khi nào cần custom verifier?

PKI default verifier so sánh Subject DN. Nếu tổ chức dùng SAN DNS hoặc URI để định danh workload, có thể cấu hình <code>X509ClientCertificateAuthenticationProvider.setCertificateVerifier(...)</code>.

Provider có thể được tùy chỉnh qua <code>clientAuthentication(...).authenticationProviders(...)</code>. API này cho phép truy cập danh sách provider mặc định; tìm đúng <code>X509ClientCertificateAuthenticationProvider</code> rồi đặt verifier.

### 8.2. Ví dụ xác minh DNS SAN

Giả sử ứng dụng có một policy service đáng tin cậy để lấy DNS SAN kỳ vọng theo registered client record ID:

~~~java
public interface ClientCertificatePolicy {
    String expectedDnsSan(String registeredClientId);
}
~~~

Đây là abstraction do ứng dụng tự xây; không phải API Spring. Cấu hình verifier:

~~~java
private Consumer<List<AuthenticationProvider>>
        configureDnsSanCertificateVerifier(
            ClientCertificatePolicy certificatePolicy) {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof
                X509ClientCertificateAuthenticationProvider x509Provider) {

            x509Provider.setCertificateVerifier(context -> {
                OAuth2ClientAuthenticationToken authentication =
                    context.getAuthentication();
                RegisteredClient registeredClient =
                    context.getRegisteredClient();

                Object credentials = authentication.getCredentials();
                if (!(credentials instanceof X509Certificate[] chain)
                        || chain.length == 0) {
                    throw new OAuth2AuthenticationException(
                        OAuth2ErrorCodes.INVALID_CLIENT);
                }

                X509Certificate leafCertificate = chain[0];
                String expectedDns = certificatePolicy.expectedDnsSan(
                    registeredClient.getId());
                if (expectedDns == null || expectedDns.isBlank()) {
                    throw new OAuth2AuthenticationException(
                        OAuth2ErrorCodes.INVALID_CLIENT);
                }

                try {
                    Collection<List<?>> subjectAltNames =
                        leafCertificate.getSubjectAlternativeNames();

                    boolean matched = subjectAltNames != null
                        && subjectAltNames.stream().anyMatch(entry ->
                            entry.size() >= 2
                            && Integer.valueOf(2).equals(entry.get(0))
                            && expectedDns.equalsIgnoreCase(
                                String.valueOf(entry.get(1))));

                    if (!matched) {
                        throw new OAuth2AuthenticationException(
                            OAuth2ErrorCodes.INVALID_CLIENT);
                    }
                } catch (CertificateParsingException ex) {
                    throw new OAuth2AuthenticationException(
                        new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT), ex);
                }
            });
        }
    });
}
~~~

Trong cấu trúc SAN của Java, type <code>2</code> đại diện <code>dNSName</code>. Ví dụ trên so khớp chính xác DNS SAN với giá trị lấy từ policy tin cậy; không dùng wildcard hoặc suffix matching tùy tiện. Nếu cần URI SAN, loại SAN là <code>6</code>; phải so khớp URI theo quy tắc/namespace đã thống nhất.

**Điểm quan trọng:** <code>setCertificateVerifier()</code> thay verifier của provider. Khi dùng custom verifier cho PKI, bạn chịu trách nhiệm kiểm tra certificate mapping (ở ví dụ là SAN DNS); chain validation đã được TLS stack thực hiện theo trust store. Nếu dùng custom verifier cho <code>SELF_SIGNED_TLS_CLIENT_AUTH</code>, phải tự bảo toàn cả logic đối chiếu certificate với JWK Set đăng ký; ví dụ trên chỉ minh họa PKI SAN, không được áp dụng nguyên xi cho self-signed.

### 8.3. Gắn verifier vào SecurityFilterChain

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        ClientCertificatePolicy certificatePolicy) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .clientAuthentication(clientAuthentication ->
                clientAuthentication.authenticationProviders(
                    configureDnsSanCertificateVerifier(
                        certificatePolicy))));

    return http.build();
}
~~~

Đây là khung cấu hình cho chain Authorization Server; ứng dụng còn cần RegisteredClientRepository, AuthorizationServerSettings, authorization service, token generator, user authentication và các bean phù hợp. Trong production, nếu client có cả DN và SAN policy, định nghĩa rõ điều kiện chấp nhận; không vô tình cho phép một certificate khớp một trong nhiều định danh quá rộng.

## 9. mTLS client authentication và certificate-bound access token

Hai cơ chế này thường đi cùng nhau nhưng có mục đích khác nhau:

| Cơ chế | Chứng minh điều gì? | Diễn ra ở đâu? |
| --- | --- | --- |
| mTLS client authentication | Client đang gọi Authorization Server sở hữu private key của certificate đã đăng ký cho client. | TLS connection tới Token Endpoint (và các endpoint yêu cầu client authentication). |
| Certificate-bound access token | Bên gọi Resource Server đang sở hữu private key của đúng certificate gắn với access token. | TLS connection tới API/Resource Server. |

Một client có thể xác thực mTLS ở Token Endpoint nhưng vẫn nhận **bearer access token** nếu không bật token binding. Nếu token bị đánh cắp, bên khác có thể dùng token đó trong khi token còn hiệu lực. Certificate-bound token bổ sung proof-of-possession: phải trình cùng certificate/private key khi gọi API.

### 9.1. Bật binding trong RegisteredClient

~~~java
RegisteredClient mtlsClient = RegisteredClient
    .withId("mtls-client-record-001")
    .clientId("mtls-client")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .x509CertificateSubjectDN(
            "CN=mtls-client,OU=Platform,O=Example Corp,C=VN")
        .build())
    .tokenSettings(TokenSettings.builder()
        .x509CertificateBoundAccessTokens(true)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

<code>TokenSettings.x509CertificateBoundAccessTokens(true)</code> bật việc ràng buộc access token với client certificate trong luồng mTLS được hỗ trợ. Với JWT access token, Spring Authorization Server đưa thumbprint vào claim <code>cnf</code>:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["https://orders-api.example.com"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "base64url-sha256-thumbprint-of-certificate"
  }
}
~~~

Giá trị thumbprint là SHA-256 của **DER encoding** của certificate, được Base64URL encode và bỏ dấu padding <code>=</code>. Đây không phải hash của PEM text hoặc private key.

### 9.2. Với reference/opaque access token

Nếu access token là opaque/reference token, thumbprint có thể được cung cấp trong Token Introspection response dưới claim <code>cnf</code>:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "mtls-client",
  "cnf": {
    "x5t#S256": "base64url-sha256-thumbprint-of-certificate"
  }
}
~~~

Resource Server so sánh thumbprint trong introspection response với certificate nhận từ TLS connection tới API. Nếu không trùng, phải từ chối request bằng <code>401 invalid_token</code>.

### 9.3. Client phải dùng cùng certificate ở Resource Server

Quy trình:

1. Client trình certificate C1 khi gọi Token Endpoint và nhận certificate-bound access token.
2. Access token chứa <code>cnf.x5t#S256</code> là thumbprint của C1.
3. Client gọi Orders API qua mTLS và trình đúng C1.
4. Resource Server lấy certificate từ TLS layer, tính thumbprint và so với claim <code>cnf</code>.
5. Nếu trùng, tiếp tục kiểm tra issuer, audience, expiry, scope và policy API.
6. Nếu không trùng hoặc không có certificate, trả <code>401 invalid_token</code>.

Nếu client đổi certificate, access token đã ràng buộc với certificate cũ không tự chuyển sang certificate mới. Client cần lấy token mới theo chính sách và dùng certificate mới. Với confidential client, refresh request cũng phải xác thực client theo certificate hiện hành.

## 10. Resource Server kiểm tra certificate-bound token

### 10.1. Công thức thumbprint

RFC 8705 định nghĩa:

~~~text
x5t#S256 = BASE64URL_NOPAD(SHA-256(DER(certificate)))
~~~

Hàm Java:

~~~java
static String certificateThumbprint(X509Certificate certificate) {
    try {
        byte[] der = certificate.getEncoded();
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(der);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    } catch (CertificateEncodingException
            | NoSuchAlgorithmException ex) {
        throw new IllegalStateException(
            "Cannot calculate certificate thumbprint", ex);
    }
}
~~~

### 10.2. Logic kiểm tra tại API

Resource Server phải lấy certificate **từ TLS layer** của request hiện tại, không lấy từ một header do caller tự khai. Với Servlet container, certificate chain thường có thể đọc qua request attribute <code>jakarta.servlet.request.X509Certificate</code> khi TLS được kết thúc tại container.

Logic kiểm tra cốt lõi:

~~~java
boolean certificateMatches(
        Jwt jwt, X509Certificate[] clientCertificateChain) {

    if (clientCertificateChain == null
            || clientCertificateChain.length == 0) {
        return false;
    }

    Map<String, Object> confirmation = jwt.getClaim("cnf");
    if (confirmation == null) {
        return false;
    }

    Object expectedValue = confirmation.get("x5t#S256");
    if (!(expectedValue instanceof String expectedThumbprint)) {
        return false;
    }

    String actualThumbprint =
        certificateThumbprint(clientCertificateChain[0]);

    return MessageDigest.isEqual(
        expectedThumbprint.getBytes(StandardCharsets.US_ASCII),
        actualThumbprint.getBytes(StandardCharsets.US_ASCII));
}
~~~

Đây là helper minh họa; cần gọi sau khi JWT đã được decoder xác minh chữ ký và các claims chuẩn. Trong Servlet application, có thể đặt một filter sau <code>BearerTokenAuthenticationFilter</code> để lấy <code>JwtAuthenticationToken</code>, đọc peer certificate và từ chối nếu helper trả <code>false</code>. Nếu dùng opaque token, đọc <code>cnf</code> từ introspection result thay vì JWT.

**Không chỉ kiểm tra certificate ở Token Endpoint.** Resource Server phải tự xác minh proof-of-possession trên kết nối API. Cũng không giả định <code>oauth2ResourceServer().jwt()</code> tự động so sánh claim <code>cnf.x5t#S256</code> với TLS certificate; cần cấu hình/triển khai kiểm tra tương ứng cho phiên bản và kiến trúc của bạn.

### 10.3. Không dùng header certificate không đáng tin

Nếu TLS kết thúc tại ingress/proxy, Servlet container có thể không nhìn thấy peer certificate trực tiếp. Khi đó, cần một cơ chế chuyển tiếp certificate metadata được bảo vệ:

- Chỉ nhận từ proxy/ingress có danh tính xác thực.
- Proxy xóa header certificate do Internet client gửi trước khi ghi giá trị đã xác minh.
- Proxy → Resource Server dùng kênh nội bộ được bảo vệ, tốt nhất có mTLS.
- Resource Server không được truy cập trực tiếp từ mạng ngoài nếu tin header do proxy thêm.
- Kiểm thử rằng client không thể giả mạo header như <code>X-Forwarded-Client-Cert</code> hoặc <code>X-SSL-CERT</code>.

## 11. Certificate rotation và revocation

### 11.1. Rotation PKI

Với <code>tls_client_auth</code>, nếu Authorization Server ràng buộc theo Subject DN, CA có thể cấp certificate mới cùng DN cho client. Tuy vậy cần:

1. Cấp certificate mới và cài private key vào workload.
2. Xác minh chain, SAN/DN, EKU và key usage.
3. Triển khai certificate mới tới client.
4. Chuyển traffic sang certificate mới.
5. Thu hồi certificate cũ theo CRL/OCSP hoặc quy trình PKI.
6. Theo dõi các request vẫn dùng certificate cũ và kết thúc thời gian overlap.

Nếu chỉ so Subject DN, certificate cũ và mới cùng DN có thể đều được chấp nhận trong thời gian overlap. Điều đó hữu ích cho rotation nhưng cần thu hồi certificate cũ nếu private key cũ bị lộ.

### 11.2. Rotation self-signed

Với <code>self_signed_tls_client_auth</code>, certificate mới phải được đăng ký trong JWK Set/JWKS URI của client. Khi thay certificate:

- Công bố JWK có <code>x5c</code> của certificate mới.
- Chờ cache/replica theo policy nhận dữ liệu mới.
- Triển khai certificate mới cho client.
- Xác minh handshake và mapping với certificate mới.
- Gỡ certificate cũ sau cửa sổ chuyển tiếp hoặc ngay khi compromise.

Không tái sử dụng <code>kid</code> cho certificate/public key khác. Bảo vệ JWKS URI vì đây là nguồn tin cậy cho danh tính client.

### 11.3. Certificate revocation

Certificate có thể bị thu hồi trước hạn do private key bị lộ, thiết bị mất, workload bị chiếm hoặc nhân sự/đối tác ngừng được phép truy cập. Với PKI, có thể dùng CRL hoặc OCSP tùy TLS stack và chính sách triển khai. Không mặc định mọi embedded server tự bật revocation checking chỉ vì trust store được cấu hình.

Với self-signed, cần gỡ certificate khỏi danh sách/JWKS đã đăng ký và bảo đảm cache được cập nhật. Nếu certificate đã được dùng để cấp certificate-bound access token, Resource Server cũng cần xử lý token đang gắn với certificate đó; thu hồi certificate ở Authorization Server không nhất thiết làm JWT offline đã cấp tự mất hiệu lực ngay.

### 11.4. Certificate-bound access token và vòng đời token

Certificate-bound access token không còn dùng được với certificate mới nếu thumbprint khác. Điều này giúp giới hạn rủi ro token bị đánh cắp nhưng có thể ảnh hưởng client khi rotation:

- Chọn access token TTL phù hợp để giảm cửa sổ ảnh hưởng.
- Thực hiện certificate rotation có overlap được kiểm soát.
- Cấp token mới bằng certificate mới.
- Với refresh token, confidential client phải xác thực lại bằng client certificate theo method đã đăng ký.
- Nếu certificate cũ bị compromise, ưu tiên revoke ngay và chấp nhận buộc client lấy token mới.

## 12. TLS và mTLS security controls

### 12.1. Chọn trust anchors hẹp

Với PKI method, chỉ tin các CA có quy trình cấp certificate đáp ứng yêu cầu. Nếu tin toàn bộ public CA hoặc một enterprise root quá rộng, attacker có thể xin certificate khác có cùng Subject DN/SAN. Hạn chế trust anchors và định danh certificate theo policy cụ thể của client.

### 12.2. Phiên bản TLS và cấu hình mật mã

Ưu tiên TLS 1.2 hoặc TLS 1.3 theo baseline bảo mật hiện hành, tắt phiên bản/cipher yếu, xác minh server certificate ở client và bảo vệ private key của cả hai bên. Không dùng self-signed client certificate làm lý do bỏ qua việc client xác minh server certificate.

### 12.3. Không dùng chung một certificate cho nhiều client tùy tiện

Nếu nhiều service dùng cùng certificate/private key, việc thu hồi hoặc điều tra trở nên khó khăn và compromise một workload ảnh hưởng toàn bộ nhóm. Cấp certificate theo workload/client hoặc theo nhóm có ranh giới quyền rõ ràng; định danh SAN/DN phải gắn với client registration tương ứng.

### 12.4. Chống downgrade phương thức xác thực

Một client được đăng ký <code>tls_client_auth</code> phải thực hiện đúng mTLS. Không cho phép client gửi <code>client_secret</code> hoặc đổi sang <code>client_secret_basic</code> để vượt qua certificate mismatch. Phương thức xác thực được quyết định từ RegisteredClient và policy server, không do client tự chọn trong từng request.

### 12.5. Bảo vệ private key client

Client certificate chỉ là public credential; **private key** mới chứng minh quyền sở hữu. Bảo vệ private key bằng keystore/HSM/TPM hoặc secret manager, giới hạn quyền truy cập, tránh xuất file PEM không mã hóa, không log key và có quy trình rotation/incident khi workload bị chiếm.

## 13. Kiểm thử mTLS end-to-end

### 13.1. Ma trận kiểm thử OAuth client authentication

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Certificate hợp lệ, chain tin cậy, DN đúng client | Client authentication thành công. |
| Không gửi certificate với client dùng <code>tls_client_auth</code> | <code>invalid_client</code>; không cấp token. |
| Certificate hợp lệ nhưng DN/SAN không khớp client | <code>invalid_client</code>. |
| Certificate của client A dùng với <code>client_id</code> client B | Bị từ chối; không dùng chéo certificate. |
| Certificate hết hạn | TLS handshake/client authentication thất bại. |
| Certificate chain không tới trust anchor | TLS handshake thất bại. |
| Certificate bị revoke và revocation checking được cấu hình | Bị từ chối theo CRL/OCSP policy. |
| Client bỏ <code>client_id</code> trong request mTLS | Bị từ chối theo RFC 8705. |
| Client gửi sai secret cùng method TLS | Không được dùng secret để downgrade/bỏ qua certificate. |
| SAN có DNS đúng nhưng URI sai | Chỉ chấp nhận theo loại SAN đã đăng ký; không dùng SAN bất kỳ. |
| Self-signed certificate nằm trong JWKS đăng ký | Thành công khi certificate khớp và proof-of-possession hợp lệ. |
| Self-signed certificate không có trong JWKS | Bị từ chối. |
| JWKS URI timeout/không tin cậy | Không xác thực client theo cache/dữ liệu chưa được phép ngoài policy. |

### 13.2. Ma trận certificate-bound access token

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Access token được cấp qua mTLS với binding bật | JWT có <code>cnf.x5t#S256</code> hoặc introspection trả claim tương ứng. |
| Client gọi API bằng đúng certificate đã dùng ở token endpoint | Vượt qua certificate binding nếu chữ ký/claims/scope hợp lệ. |
| Token bị đánh cắp nhưng dùng từ client không có private key tương ứng | Bị từ chối. |
| Token dùng với certificate khác | HTTP 401 <code>invalid_token</code>. |
| Token thiếu <code>cnf</code> trên endpoint bắt buộc mTLS-bound | Bị từ chối theo policy endpoint. |
| Certificate bị thay sau khi token cấp | Token cũ không khớp certificate mới; cần lấy token mới. |
| Opaque token introspection có <code>cnf</code> | Resource Server so thumbprint từ response với peer certificate. |
| JWT chữ ký hợp lệ nhưng audience sai | Resource Server vẫn từ chối. |
| Proxy thêm certificate header không đáng tin | Bị loại bỏ/từ chối; không dùng header giả để xác thực. |

### 13.3. Integration test với MockMvc và TLS thật

MockMvc hữu ích để test controller/provider logic, nhưng nó không tự mô phỏng một TLS handshake mTLS thực tế. Để chứng minh toàn bộ luồng:

1. Tạo test CA và cấp certificate cho <code>orders-worker</code>.
2. Cấu hình embedded server hoặc test proxy yêu cầu client certificate.
3. Gửi HTTP request thật tới token endpoint bằng certificate/private key.
4. Kiểm tra request thiếu certificate và certificate sai client đều bị từ chối.
5. Kiểm tra token response có scope đúng và binding claim nếu bật.
6. Gọi Resource Server qua mTLS với certificate đúng rồi certificate khác.
7. Kiểm tra HTTP 401 khi thumbprint không trùng.
8. Thực hiện rotation certificate và kiểm tra hành vi trong cửa sổ chuyển tiếp.

Với custom SAN verifier, tạo certificate test có SAN đúng/sai, nhiều SAN, SAN sai type và certificate chain không hợp lệ. Với self-signed, kiểm tra JWKS <code>x5c</code> match và không match.

### 13.4. Kiểm thử reverse proxy

Nếu TLS termination tại ingress:

- Gửi một header giả <code>X-Forwarded-Client-Cert</code> từ bên ngoài và xác nhận proxy xóa nó.
- Xác nhận proxy ghi certificate metadata đã xác minh.
- Gửi request trực tiếp tới backend và xác nhận bị chặn.
- Thay certificate của proxy→backend và xác nhận backend từ chối.
- Kiểm tra đúng leaf certificate được chuyển, không nhầm CA/intermediate với client leaf.
- Kiểm tra thumbprint ở Resource Server được tính từ cùng certificate đã trình trong handshake.

## 14. Lỗi thường gặp và cách chẩn đoán

### Lỗi 1: Đã cấu hình RegisteredClient nhưng handshake không yêu cầu certificate

**Triệu chứng:** Provider không nhận được certificate hoặc request bị <code>invalid_client</code>.

**Nguyên nhân:** TLS listener chưa bật client authentication, trust store sai hoặc ingress không yêu cầu certificate.

**Cách xử lý:** Kiểm tra TLS handshake, client-auth mode, trust anchors và request certificate attribute tại Servlet container.

### Lỗi 2: Handshake thành công nhưng OAuth client vẫn bị từ chối

**Triệu chứng:** TLS connection được thiết lập nhưng token endpoint trả <code>invalid_client</code>.

**Nguyên nhân:** <code>client_id</code> không tồn tại, certificate không khớp Subject DN/SAN hoặc method đăng ký khác certificate method đang dùng.

**Cách xử lý:** Kiểm tra RegisteredClient, authentication method, subject DN và certificate chain thực tế.

### Lỗi 3: Subject DN hiển thị giống nhau nhưng vẫn mismatch

**Triệu chứng:** DN trong log nhìn giống cấu hình nhưng verifier từ chối.

**Nguyên nhân:** Khác cách serialize/normalize DN, thứ tự RDN, escaping hoặc ký tự Unicode.

**Cách xử lý:** Chuẩn hóa và so sánh theo quy tắc DN đã thống nhất; nếu dùng SAN, triển khai verifier rõ ràng theo đúng loại SAN.

### Lỗi 4: Custom verifier làm self-signed client không hoạt động

**Triệu chứng:** Client dùng self-signed certificate hợp lệ trước đó nhưng bị từ chối sau khi cấu hình custom verifier.

**Nguyên nhân:** <code>setCertificateVerifier()</code> đã thay verifier mặc định vốn đối chiếu certificate với JWK Set.

**Cách xử lý:** Chỉ dùng verifier custom cho phương thức phù hợp hoặc triển khai đầy đủ cả logic certificate/JWKS matching cho self-signed.

### Lỗi 5: Browser login hiện hộp thoại chọn certificate

**Triệu chứng:** Người dùng mở trang login và trình duyệt hỏi chọn client certificate.

**Nguyên nhân:** TLS listener bắt buộc certificate trên cùng hostname/port của authorization endpoint.

**Cách xử lý:** Dùng client-auth optional hoặc tách mTLS endpoint alias/hostname/port theo RFC 8705.

### Lỗi 6: Resource Server nhận JWT nhưng token bị đánh cắp vẫn dùng được

**Triệu chứng:** Client khác dùng bearer token thành công dù token được cấp qua mTLS.

**Nguyên nhân:** Chỉ bật client authentication tại Token Endpoint, chưa bật certificate-bound access token hoặc Resource Server chưa kiểm tra <code>cnf.x5t#S256</code>.

**Cách xử lý:** Bật token binding, yêu cầu mTLS ở API và so thumbprint peer certificate.

### Lỗi 7: Certificate mới hoạt động tại Token Endpoint nhưng không dùng được token cũ

**Triệu chứng:** Sau rotation, API trả <code>invalid_token</code>.

**Nguyên nhân:** Access token được ràng buộc với thumbprint certificate cũ.

**Cách xử lý:** Lấy access token mới bằng certificate mới; không sửa thumbprint trong token đã ký.

### Lỗi 8: Proxy chuyển certificate bằng header nhưng có thể giả mạo

**Triệu chứng:** Caller tự gửi header certificate và backend chấp nhận.

**Nguyên nhân:** Backend tin header từ mọi nguồn hoặc proxy không xóa header do client gửi.

**Cách xử lý:** Chỉ tin proxy xác thực, strip inbound header, bảo vệ proxy→backend và không mở đường truy cập trực tiếp.

## 15. Checklist production

| Hạng mục | Câu hỏi cần xác nhận |
| --- | --- |
| Client registration | Đúng client ID, auth method, Subject DN/SAN hoặc JWKS URI? |
| TLS listener | Có yêu cầu client cert đúng endpoint và đúng chế độ want/need? |
| Trust anchors | Chỉ tin CA cần thiết? Có kiểm tra chain, EKU, key usage và validity? |
| Revocation | Có CRL/OCSP hoặc cơ chế thu hồi certificate phù hợp? |
| Certificate mapping | DN/SAN/JWK certificate khớp đúng một client, không dùng chéo? |
| Self-signed JWKS | URI tin cậy, HTTPS, chống SSRF, cache và rotation được kiểm soát? |
| Private key | Nằm trong keystore/HSM/TPM, không log/export trái phép? |
| Token binding | Có cần bật <code>x509CertificateBoundAccessTokens</code>? |
| Resource Server | Yêu cầu cùng certificate và so <code>cnf.x5t#S256</code>? |
| TLS termination | Proxy metadata được xác thực và header spoofing bị ngăn chặn? |
| Endpoint alias | Có tách mTLS endpoint khỏi browser authorization endpoint khi cần? |
| Rotation | Có overlap, revoke certificate cũ và cấp token mới? |
| Audit | Có log client ID, certificate serial/thumbprint, issuer, thời điểm và kết quả mà không lộ private key? |
| Testing | Có TLS integration test, negative cases, rotation và proxy tests? |

## 16. Bài tập thực hành

Một hệ thống doanh nghiệp có Authorization Server tại <code>https://auth.example.com</code> và hai service <code>orders-worker</code>, <code>billing-worker</code>. Cả hai dùng Client Credentials, nhưng chỉ Orders được phép truy cập Orders API. Công ty có CA nội bộ, ingress kết thúc TLS và Resource Server yêu cầu certificate-bound access token.

1. Thiết kế certificate profile cho hai workload, gồm Subject DN hoặc SAN, EKU, Key Usage và TTL.
2. Đăng ký hai <code>RegisteredClient</code> với <code>ClientAuthenticationMethod.TLS_CLIENT_AUTH</code> và DN khác nhau.
3. Cấu hình trust store/ingress yêu cầu client certificate; giải thích khi nào dùng <code>want</code> và khi nào dùng <code>need</code>.
4. Gửi token request có <code>client_id</code> và certificate, không gửi client secret; kiểm tra client A không thể dùng certificate client B.
5. Viết custom certificate verifier theo DNS SAN và giải thích vì sao verifier custom phải tự thực hiện mapping.
6. Bật <code>TokenSettings.x509CertificateBoundAccessTokens(true)</code>, kiểm tra JWT có <code>cnf.x5t#S256</code>.
7. Viết Resource Server filter/helper so thumbprint của certificate thực với claim <code>cnf</code>.
8. Chứng minh token bị đánh cắp không dùng được từ một client không có private key tương ứng.
9. Thực hiện certificate rotation, thu hồi certificate cũ và xác định access token cũ phải được xử lý thế nào.
10. Kiểm thử ingress loại bỏ header giả, chỉ chuyển certificate metadata đã xác minh và bảo vệ kênh tới backend.

**Tiêu chí đạt:** Chứng minh được **TLS handshake xác nhận quyền sở hữu private key**, **Authorization Server ràng buộc certificate với đúng RegisteredClient**, và nếu bật certificate-bound token thì **Resource Server xác minh cùng certificate trước khi cho truy cập API**.

## 17. Tài liệu đối chiếu

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): PKI/self-signed methods, client certificate binding, <code>cnf.x5t#S256</code>, endpoint aliases, TLS termination và security considerations.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate path validation, extension, CRL và PKI.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn Subject DN.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): quy tắc so sánh DN.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Set và trường <code>x5c</code>.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): cung cấp metadata và trạng thái opaque access token.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): client authentication, mTLS verifier, self-signed certificate và certificate-bound access token.
- [Spring Authorization Server — X509ClientCertificateAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/X509ClientCertificateAuthenticationProvider.html): provider xác thực certificate và <code>setCertificateVerifier</code>.
- [Spring Authorization Server — ClientSettings.Builder API](https://docs.spring.io/spring-authorization-server/docs/1.5.0/api/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.Builder.html): <code>x509CertificateSubjectDN</code> và client settings.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): <code>server.ssl.client-auth</code>, key store và trust store.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT ở Resource Server.
