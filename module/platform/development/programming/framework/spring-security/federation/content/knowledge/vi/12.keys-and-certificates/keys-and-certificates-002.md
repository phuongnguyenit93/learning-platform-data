# Phân biệt chứng thư ký SAML với chứng thư HTTPS trong Spring Security Federation

> **Chủ đề:** Spring Security – federation. **Nhóm:** Khóa và chứng thư. Bài này giải thích sự khác nhau giữa **chứng thư dùng để ký/xác minh thông điệp SAML 2.0** và **chứng thư dùng trong kết nối HTTPS/TLS**, đặc biệt khi ứng dụng Spring Security đóng vai trò **Service Provider (SP)** liên kết với **Identity Provider (IdP)**. Mục tiêu là tránh nhầm khóa, mô hình tin cậy, cấu hình và quy trình luân phiên chứng thư.

## 1. Kết luận quan trọng trước khi bắt đầu

**Cùng là tệp X.509, nhưng chức năng và cách tin cậy không giống nhau.**

- **Chứng thư HTTPS/TLS** gắn public key với **tên máy chủ** trong kết nối HTTPS (ví dụ `login.example.org` hay `portal.example.org`). Trình duyệt/HTTP client kiểm TLS handshake, hostname (DNS SAN), đường chứng thư tới CA/trust anchor, hiệu lực và các chính sách TLS liên quan. Private key TLS ở phía **máy chủ endpoint HTTPS** hoặc bộ phận TLS termination như load balancer/reverse proxy.
- **Chứng thư ký SAML** được SP đăng ký là **verification credential của IdP** để xác minh chữ ký XML trên **SAML Response/Assertion**. Private signing key ở **IdP**; SP giữ public verification certificate. Trust thường đến từ **SAML metadata đã được đối chiếu đáng tin hoặc cấu hình pin/key rõ ràng**, không mặc nhiên dựa vào danh sách CA tin cậy của trình duyệt.
- **Chứng thư SP ký AuthnRequest** là một cặp khác: SP giữ private key để ký **AuthnRequest/LogoutRequest** khi chính sách IdP yêu cầu; IdP đăng ký public signing certificate của SP.
- **Chứng thư SP mã hóa** là vai trò thứ tư: IdP dùng public encryption certificate của SP để mã hóa Assertion; SP dùng private decryption key tương ứng để giải mã. **Mã hóa ≠ chữ ký ≠ HTTPS.**

**Ví dụ thực tế:** Truy cập `https://login.example.org/metadata` qua HTTPS hợp lệ **không chứng minh** SAML Response sau đó có chữ ký đáng tin. Ngược lại, một SAML Response có chữ ký IdP hợp lệ **không chứng minh** trang `https://login.example.org` có TLS certificate còn hạn hay đúng hostname. Hai bước phải được kiểm tra **độc lập** và đều cần thiết theo ngữ cảnh.

## 2. Năm cặp khóa/chứng thư có thể cùng tồn tại

Xét một hệ thống có portal ứng dụng Spring MVC/Spring Security và IdP bên ngoài.

| Vai trò | Ai giữ private key? | Ai cần public certificate/key? | Bảo vệ cái gì? |
|---|---|---|---|
| **TLS server cert của SP** | SP, ingress hoặc load balancer quản lý HTTPS | Browser/HTTP client kết nối SP | Kênh HTTPS tới ACS, trang app, metadata SP |
| **TLS server cert của IdP** | IdP hoặc proxy trước IdP | Browser, SP HTTP client lấy metadata/introspection khi cần | Kênh HTTPS tới trang đăng nhập, SSO endpoint, metadata IdP |
| **IdP SAML signing cert** | **IdP** giữ private signing key | **SP** tin public cert IdP | Chữ ký XML của SAML Response/Assertion/Logout theo hợp đồng |
| **SP SAML signing cert** | **SP** giữ private signing key | **IdP** tin public cert SP | Chữ ký `AuthnRequest`, `LogoutRequest`... do SP phát nếu áp dụng |
| **SP SAML encryption cert** | **SP** giữ private decryption key | **IdP** dùng public cert SP để mã hóa | Bí mật Assertion/NameID/Attributes khi mã hóa SAML |

Một sản phẩm có thể sử dụng cùng một keypair cho nhiều vai trò vì giới hạn interop, nhưng **không nên suy ra đó là điều bắt buộc**. Tách khóa theo chức năng thường giúp giảm blast radius, quản lý rotation, phân quyền và điều tra sự cố; OWASP khuyến nghị tách signing và encryption trong SAML. Với production, dùng key usage/EKU và policy phù hợp; không dùng lại private key TLS cho SAML chỉ để đỡ tạo thêm file.

### 2.1. Luồng trực quan

~~~text
                         TLS server certificate (IdP)
Browser  ─── HTTPS ────────────────────────────────> IdP
  |                                                 |
  |              IdP SAML private signing key       |
  |              ký Response / Assertion            |
  |                                                 |
  | <───────── SAMLResponse (qua trình duyệt) ───────+
  |
  |             TLS server certificate (SP)
  └──── HTTPS POST SAMLResponse ──────────────────> Spring Security SP
                                                   |
                                                   | Verify XML signature
                                                   | bằng IdP PUBLIC SAML
                                                   | signing certificate
                                                   |
                                                   | Kiểm Issuer, Audience,
                                                   | Destination, Recipient,
                                                   | Time, InResponseTo, Replay
                                                   v
                                               Authentication
~~~

**Nhận xét:** Có ít nhất hai TLS handshake khác nhau và một phép kiểm chữ ký XML riêng. HTTPS chỉ bảo vệ từng kênh TLS; **trình duyệt là bên mang SAMLResponse** và không được coi là trusted IdP. Một form HTTP POST đi qua TLS có thể chứa payload giả do người gửi tạo; chữ ký XML cùng trust/validation SAML mới quyết định có nhận danh tính hay không.

## 3. Chứng thư X.509 là một “vỏ chứa” khóa công khai

Chứng thư X.509 thường có:

- **Subject** và **Issuer** (Distinguished Name): mô tả chủ thể và bên phát hành chứng thư.
- **Public Key** và thuật toán: RSA, EC... tùy khả năng phần mềm và policy.
- **Serial Number**: số sê-ri do issuer cấp.
- **Validity**: `notBefore`, `notAfter`.
- **X.509 extensions**: `Subject Alternative Name (SAN)`, `Key Usage (KU)`, `Extended Key Usage (EKU)`, `Basic Constraints`, `Authority Key Identifier`, `Subject Key Identifier`...
- **Certificate Signature**: chữ ký của CA/issuer trên **nội dung chứng thư**, khác với chữ ký SAML XML.

Hai lớp chữ ký rất hay bị nhầm:

| Chữ ký | Ai tạo? | Đang ký thứ gì? | Ai kiểm và bằng key nào? |
|---|---|---|---|
| **Chữ ký của X.509 certificate** | CA hoặc chính chủ thể khi self-signed | Cấu trúc TBSCertificate | TLS/PKIX validator hoặc bên tiêu thụ chứng thư theo trust policy |
| **Chữ ký XML của SAML Response/Assertion** | IdP bằng SAML private signing key | `ds:SignedInfo` liên kết với Response/Assertion XML qua Reference/digest | SP bằng **IdP SAML verification public key** đã tin cậy |

Một chứng thư IdP **self-signed** có thể hoàn toàn phù hợp nếu SP đã tin cậy public certificate đó qua federation metadata/trao đổi khóa có xác thực. Self-signed SAML cert **không mặc định là lỗi**. Nhưng chứng thư TLS self-signed chưa có CA/trust anchor trong browser/HTTP client thường bị cảnh báo hoặc kết nối thất bại. Đây là khác biệt **mô hình tin cậy**, không phải khác biệt cú pháp tệp.

Chứng thư X.509 và private key liên quan có thể lưu dạng:

- `.pem` / `.crt` / `.cer`: có thể chứa public X.509 certificate theo PEM hoặc DER; phần đuôi **không bảo đảm** định dạng.
- `.key`: thường private key nhưng không thể suy ra chắc chắn chỉ từ tên file.
- `.p12` / `.pfx`: kho PKCS#12 có thể chứa private key, certificate chain, trust material và mật khẩu.
- Java `KeyStore` / `TrustStore`: được dùng rộng rãi trong TLS. Một store không tự nói khóa bên trong được cấp cho SAML signing hay TLS server; **cấu hình và chính sách sử dụng** mới quyết định.

**Nguyên tắc bảo vệ:** Public certificate có thể chia sẻ theo quy trình metadata; **private key không bao giờ đưa vào metadata, commit, gửi cho đối tác hay log**. Tập tin ghi `BEGIN CERTIFICATE` không chứa private key; tập tin ghi `BEGIN PRIVATE KEY` hoặc tương đương chứa dữ liệu phải bảo vệ.

## 4. HTTPS/TLS xác minh điều gì?

### 4.1. Khi trình duyệt vào trang IdP

Giả sử browser mở `https://login.example.org/`.

TLS client thường cần kiểm:

1. Tên DNS mong đợi `login.example.org` phải được bảo vệ bởi **Subject Alternative Name (SAN)** phù hợp. Không đánh đồng `CN` với DNS SAN trong cơ chế hostname verification hiện đại.
2. Certificate chain dẫn tới **trust anchor phù hợp**, thường public root CA thuộc browser/OS trust store, hoặc private CA đã được quản trị chấp nhận.
3. Certificate validity/notBefore/notAfter và các yêu cầu PKIX, key usage/EKU, thuật toán, revocation/CT nếu nền tảng/chính sách áp dụng.
4. TLS handshake chứng minh server có quyền sử dụng **private key tương ứng** với public key trong certificate đã được chấp nhận; phiên tạo khóa đối xứng để bảo vệ dữ liệu trao đổi.
5. Phiên bản giao thức và bộ mã hóa TLS được phép (ưu tiên TLS 1.3, cấu hình TLS 1.2 an toàn khi cần tương thích; không bật TLS cũ yếu vì interop legacy).

Nếu TLS kiểm thất bại, browser nên từ chối hoặc cảnh báo kết nối. Việc SP sở hữu certificate SAML ký đúng **không sửa được** lỗi TLS của endpoint IdP hay ACS.

### 4.2. TLS bảo vệ kết nối, không định danh SAML issuer

Chứng thư TLS với SAN `login.example.org` chứng minh endpoint HTTPS đang được client kết nối có quyền dùng chứng thư cho hostname theo trust model. Nó **không tự khẳng định**:

- `saml:Issuer` của Assertion là một IdP đã được SP cấu hình.
- Public key của TLS cert là **IdP SAML signing key**.
- Assertion được IdP ký, còn hiệu lực và có Audience đúng SP.
- Người dùng được phép vào ứng dụng hoặc có role admin.
- Metadata tải từ URL đó được phép **tự thay thế tất cả trusted IdP credentials** mà không qua một chính sách trust/rotation.

Khi dùng HTTPS tải IdP metadata, TLS giúp chống MITM trên kết nối đến **đúng metadata URL đã tin cậy**. Nhưng ứng dụng vẫn phải có **quy tắc chọn issuer/entityID/registration**, nguồn metadata được quản trị và kế hoạch thay khóa để không tùy tiện tin một signing key khác.

### 4.3. HTTPS của SP có thể nằm ở ingress

Ví dụ:

~~~text
Browser --HTTPS--> Ingress / Load Balancer --HTTP nội bộ--> Spring Boot
                      |
                      +-- TLS certificate, private key
                          và SNI hostname ở ingress
~~~

Trong cấu hình TLS termination này, **Spring Boot không nhất thiết có TLS private key hoặc `server.ssl.*`**. Ingress giữ TLS keypair. Ứng dụng Spring vẫn phải có **IdP SAML verification credential** cho `SAMLResponse` và có thể giữ **SP SAML signing/decryption keys**. Không có gì mâu thuẫn nếu máy Spring chỉ nghe HTTP trong mạng nội bộ đã bảo vệ, trong khi ACS **công khai** là `https://portal.example.org/login/saml2/sso/corporate`.

Với TLS termination, phải kiểm trusted forwarded headers, scheme/host/port bên ngoài, cookie `Secure` và `Destination/Recipient` của SAML. Không cho client gửi header `X-Forwarded-Proto` giả rồi khiến Spring xây metadata/ACS sai.

## 5. Chứng thư ký SAML xác minh điều gì?

### 5.1. Một chữ ký SAML là XML Digital Signature

IdP ký `samlp:Response` hoặc `saml:Assertion` theo SAML Web Browser SSO profile và hợp đồng federation. XMLDSig điển hình:

~~~xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:CanonicalizationMethod Algorithm="..."/>
    <ds:SignatureMethod Algorithm="..."/>
    <ds:Reference URI="#_saml_assertion_id">
      <ds:Transforms>...</ds:Transforms>
      <ds:DigestMethod Algorithm="..."/>
      <ds:DigestValue>...</ds:DigestValue>
    </ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
  <ds:KeyInfo>...</ds:KeyInfo>
</ds:Signature>
~~~

Đây là **khung cấu trúc**, không phải chữ ký hợp lệ chạy được; không dùng giá trị dấu ba chấm trong thông điệp thực. Trên dữ liệu thật, validator phải:

1. Parse XML an toàn, chống XXE/schema confusion/duplicate ID.
2. Chọn **đúng Response/Assertion thực sự sẽ dùng** để tạo Authentication.
3. Resolve `ds:Reference` và transforms được phép, xác minh digest và signature cho đúng node.
4. Lấy public verification key **từ RelyingPartyRegistration/IdP metadata tin cậy**, không tự tin khóa trong `KeyInfo` do browser gửi.
5. Kiểm policy vị trí chữ ký: Response ký hợp lệ bao phủ Assertion được dùng, hoặc Assertion được ký hợp lệ; chữ ký có mặt nhưng sai phải fail.
6. Kiểm các semantic SAML: Issuer, Audience, Destination, Recipient, Conditions, NotBefore, NotOnOrAfter, InResponseTo, replay, principal/role policy.

Chữ ký SAML chứng minh **tính toàn vẹn và nguồn ký đáng tin của vùng XML được ký**, **không giấu** NameID/email/groups. Để bảo mật nội dung assertion cho SP cần `EncryptedAssertion` đúng chính sách, bên cạnh TLS.

### 5.2. Public signing cert đến từ metadata nào?

Trong SAML 2.0 metadata, phía **IdP** có thể công bố signing certificate trong `IDPSSODescriptor/KeyDescriptor use="signing"`. SP dùng public certificate đó để kiểm chữ ký SAML nhận vào.

Mẫu **lược giản để đọc cấu trúc**, không phải metadata thực và không có X.509 base64 hoàn chỉnh:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/entity">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_CERT_DATA</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://login.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Lưu ý:** `entityID` của IdP có thể là URI không mở qua HTTP; `SingleSignOnService.Location` là URL giao thức IdP; TLS certificate ở hostname `login.example.org` có thể có Subject/SAN hoàn toàn khác SAML entityID. Không cố dùng certificate SAN để suy ra SAML issuer.

Trong metadata, `KeyDescriptor use="signing"` có nghĩa **public signing material thuộc bên công bố metadata**. Ở **IdP metadata**, SP xác minh chữ ký của IdP; ở **SP metadata**, IdP xác minh chữ ký của SP. `use="encryption"` là vai trò khác; khi không có thuộc tính `use`, ý nghĩa/khả năng sử dụng cần đọc theo tiêu chuẩn metadata và chính sách interop, không mặc định là TLS.

### 5.3. Chữ ký Response khác chữ ký Assertion

Có thể gặp:

| Tình huống | Điều kiện ký | Điều SP phải làm |
|---|---|---|
| Response ký, Assertion không ký | Chữ ký Response **bao phủ đúng Assertion bên trong** | Verify Response signature bằng IdP key, validate Assertion conditions |
| Assertion ký, Response không ký | Mỗi Assertion được dùng **có chữ ký đúng** theo profile/policy | Verify Assertion signature và validate Response/request context |
| Cả hai ký | Có hai chữ ký ở hai phạm vi | Verify cả hai khi có; reject chữ ký sai |
| Không ký Response lẫn Assertion | Không đủ tính toàn vẹn/xác thực cho Browser SSO POST | Từ chối |
| Signed Response nhưng converter đọc Assertion ngoài vùng ký | Nguy cơ XML Signature Wrapping | Từ chối: signature valid nhưng used data không được bảo vệ |

Đừng tự viết XML parser để tìm thẻ `NameID` rồi gắn `ROLE_ADMIN`. Spring Security/OpenSAML được dùng để gắn việc kiểm signature với **đúng Assertion được sử dụng**.

## 6. Mô hình tin cậy: CA/hostname so với federation registration

| Câu hỏi | HTTPS/TLS certificate | SAML signing certificate |
|---|---|---|
| Đang xác minh cái gì? | Server TLS hiện đang cung cấp kết nối HTTPS | Chữ ký trên Response/Assertion/Request XML |
| Định danh đích chủ yếu | DNS hostname/IP được kiểm qua SAN | IdP/SP `entityID`, `Issuer`, Audience và trusted registration |
| Khóa riêng ở đâu? | Server/ingress nhận TLS | IdP ký SAML; SP ký request nếu được yêu cầu |
| Public key được tin thế nào? | Trust store/CA chain, hostname verification và chính sách TLS | Metadata SAML đáng tin, explicit verification credential hoặc policy federation đã xác minh |
| Self-signed có thể dùng không? | Chỉ khi client được cấu hình trust riêng; public browser thường báo lỗi | Thường có thể nếu trust public cert/metadata được thiết lập an toàn |
| Dùng certificate ở đâu? | TLS handshake | XML Signature validation |
| Kiểm với SAN hay entityID? | SAN phù hợp hostname kết nối | EntityID/Issuer/Audience qua SAML semantic; cert lấy từ trust registration |
| Cấu hình Spring phổ biến | `server.ssl.*` / `spring.ssl.bundle.*` / ingress | `spring.security.saml2.relyingparty.registration.*.assertingparty.verification.credentials` |
| Quản lý rotation | ACME/CA/ingress/SSL bundle, browser trust | IdP metadata/cert rollover, SP trust updates và partner coordination |
| Nếu fail | HTTPS handshake, cert chain, hostname, TLS protocol | `Signature validation failed`, issuer/registration mismatch, wrong signing key |

**Phân biệt tinh tế:** Một chứng thư SAML là X.509 có chữ ký CA/self-signed và có thể mang KU/EKU/thời hạn. Tuy nhiên nhiều framework federation dùng **explicit public key trust** thay vì xác minh PKIX chain như WebPKI; kiểm KU, EKU, hạn và revocation phụ thuộc phần mềm/chính sách cụ thể. Không khẳng định "Spring luôn kiểm mọi hạn X.509" hoặc "SAML cert tự hết hạn thì mọi SP đều dừng" nếu chưa kiểm implementation. Chủ sở hữu hệ thống vẫn phải lập lịch rotate theo **certificate validity, cryptoperiod và policy**.

Tương tự, không khẳng định "SAML signing cert phải do public CA cấp"; một certificate self-signed được tin cậy trực tiếp qua kênh đã xác thực có thể phù hợp, khác hẳn tiêu chuẩn tin cậy HTTPS của browser công khai.

## 7. Ba ranh giới tin cậy khi tải IdP metadata qua HTTPS

Đây là tình huống thường gây nhầm nhiều nhất.

~~~text
[1] SP kết nối https://idp.example.org/metadata
       -> TLS client kiểm certificate SAN + CA/trust

[2] SP parse IdP metadata đã tải
       -> Kiểm URL nguồn, IdP entityID/registration,
          metadata trust policy / metadata signature nếu áp dụng
       -> Trích IdP SAML signing public cert theo đúng role

[3] Browser mang SAMLResponse tới ACS
       -> SP kiểm XMLDSig bằng IdP signing cert đã tin
       -> SP kiểm Audience, Recipient, Issuer, time, request,
          conditions/replay rồi mới tạo Authentication
~~~

Cả ba bước khác nhau:

1. **TLS transport trust** bảo vệ kết nối metadata.
2. **Metadata/federation trust** quyết định liệu nội dung metadata và chứng thư signing có thuộc đúng IdP được SP cho phép hay không.
3. **SAML message trust** xác minh Response/Assertion với trusted signing material và semantic validation.

Một metadata URL hợp lệ HTTPS nhưng bị **trỏ nhầm tenant IdP** vẫn có thể cung cấp khóa của bên khác. Nếu SP chấp nhận thay mọi certificate chỉ dựa trên URL do người dùng gửi, có nguy cơ **trust substitution**. Vì vậy URL metadata và issuer phải được cấu hình/duyệt; nếu metadata có chữ ký, chỉ verify bằng **metadata trust anchor đã biết**.

**Ví dụ sự cố:** IdP thay TLS cert của `idp.example.org` mà public CA vẫn hợp lệ. SP có thể tiếp tục đăng nhập SAML **không cần thay SAML verification credential**, nếu IdP vẫn ký bằng cùng SAML key. Ngược lại, IdP thay **SAML signing key** nhưng TLS certificate của website IdP vẫn y nguyên: HTTPS vẫn hoạt động, nhưng SP dùng signing cert cũ sẽ từ chối SAMLResponse.

## 8. Cấu hình trong Spring Boot: phần nào thuộc HTTPS, phần nào thuộc SAML?

### 8.1. HTTPS kết thúc trực tiếp tại Spring Boot

Với Spring Boot hiện đại, có thể cấu hình **SSL bundle** chứa server TLS cert + private key (minh họa, đường dẫn phải tồn tại và được bảo vệ):

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        portal-tls:
          keystore:
            certificate: "file:/run/secrets/tls/portal-fullchain.pem"
            private-key: "file:/run/secrets/tls/portal-key.pem"
server:
  ssl:
    bundle: "portal-tls"
~~~

Đây là **cấu hình HTTPS của embedded web server**; certificate phải hợp lệ cho public hostname được client truy cập và chain/trust/algorithm phải đúng. Nếu TLS kết thúc ở ingress, **thường cấu hình keypair TLS tại ingress**, không phải ở Spring Boot. Tùy phiên bản Spring Boot, cũng có thể dùng `server.ssl.key-store` và `server.ssl.key-store-password` với PKCS#12.

**Không nhầm:** Việc cung cấp `server.ssl.bundle=portal-tls` **không** khiến Spring Security tin chữ ký SAML của IdP; chỉ tác động đến kênh TLS máy chủ web.

### 8.2. SAML verification, signing và decryption riêng

Ví dụ cho ứng dụng Spring Security Servlet với IdP đã được xác nhận trust. Đây là một cấu hình **minh họa** các vai trò khóa khác nhau, không có private key thật:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://portal.example.org/saml2/service-provider-metadata/corporate"
            acs:
              location: "https://portal.example.org/login/saml2/sso/corporate"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing-key.pem"
                  certificate-location: "file:/run/secrets/saml/sp-signing-cert.pem"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-decrypt-key.pem"
                  certificate-location: "file:/run/secrets/saml/sp-decrypt-cert.pem"
            assertingparty:
              entity-id: "https://idp.example.org/entity"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                sign-request: true
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/idp-signing-cert.pem"
~~~

**Đọc từng nhánh:**

- `assertingparty.verification.credentials` chứa **public IdP SAML signing certificate**, dùng verify chữ ký XML nhận về. **Không chứa IdP private key**.
- `signing.credentials` chứa **SP private key + SP certificate** để ký request/logout khi IdP yêu cầu. IdP phải được cấp public signing cert tương ứng.
- `decryption.credentials` chứa **SP private key + SP certificate** để giải mã EncryptedAssertion. IdP mã hóa bằng SP public encryption cert.
- `assertingparty.entity-id` và `singlesignon.url` không phải tên certificate TLS; chúng xác định **IdP issuer và endpoint SSO**.
- `entity-id` và `acs.location` là identity/endpoint của SP; HTTPS scheme trong ACS không làm ACS cert trở thành SAML verification cert.

**Tương thích phiên bản:** Các property trên phản ánh cấu trúc phổ biến trong Spring Boot 3.x/nhánh tương ứng. Khi dùng Spring Boot 4/Spring Security 7, cần đối chiếu `Saml2RelyingPartyProperties`, API và tên trường của bản đang khóa; không copy YAML nếu một property đã đổi hoặc bị loại bỏ. Với IdP có metadata URL đáng tin, có thể nạp issuer/SSO/signing cert bằng `assertingparty.metadata-uri` thay vì nhập tay, đồng thời cấu hình SP private keys độc lập.

Cần **hợp nhất** hai nhóm YAML TLS và SAML ở các nhánh phù hợp trong cùng tệp nếu cả hai dùng một ứng dụng; đoạn trên là hai khối độc lập để giải thích. Tránh tạo hai nút `spring:` trùng nhau trong cùng YAML mà parser chỉ giữ một trong hai.

### 8.3. Java Spring Security SecurityFilterChain

Tệp `src/main/java/com/example/portal/PortalSecurityApplication.java` cho một **project Spring Boot Servlet** (dependency web, security, SAML2 service provider):

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PortalSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortalSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SP ready";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Authenticated";
    }
}
~~~

Code là class Java có cú pháp đủ imports, **không chạy bằng `javac` thuần** vì cần Spring Boot/Security classpath và IdP đã đăng ký SP. Trong project Maven có Maven Wrapper và phụ thuộc tương thích:

~~~bash
./mvnw spring-boot:run
~~~

Khi ứng dụng/SSL bundle/IdP đều đã được cấu hình và server chạy, `GET /` trả body `SP ready`. `GET /private` đòi hỏi SAML login hợp lệ mới trả `Authenticated`. Bài không cam kết stdout hoặc redirect URL cụ thể vì phụ thuộc IdP/tenant, binding, mạng và cookie/session.

### 8.4. Maven dependencies cho SAML

Đoạn sau thuộc `<dependencies>` của một Spring Boot project có parent/BOM; **không phải pom.xml đầy đủ**:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

Nếu OpenSAML repository hoặc phiên bản dependency có yêu cầu riêng, theo hướng dẫn Spring Security tương ứng. Không trộn Spring Security 6 với tài liệu cấu hình dành cho 7 mà không kiểm biên dịch và test tích hợp.

## 9. Cách Spring Security biểu diễn các mục đích credential

Spring Security cung cấp `Saml2X509Credential` với các **credential types**. Những factory methods có ý nghĩa:

| Factory / API | Đầu vào | Vai trò |
|---|---|---|
| `Saml2X509Credential.verification(X509Certificate)` | Public certificate | Kiểm chữ ký SAML bên khác |
| `Saml2X509Credential.signing(PrivateKey, X509Certificate)` | Private key + certificate | Ký SAML do bên mình phát |
| `Saml2X509Credential.decryption(PrivateKey, X509Certificate)` | Private key + certificate | Giải mã nội dung SAML gửi cho mình |
| `Saml2X509Credential.encryption(X509Certificate)` | Public certificate | Mã hóa nội dung gửi tới bên khác theo role |
| `getCertificate()` | Public X509Certificate | Lấy public cert |
| `getPrivateKey()` | Có thể null | Chỉ có với vai trò cần private key |
| `getCredentialTypes()` | Tập kiểu credential | Kiểm vai trò verification, signing, decryption hoặc encryption |

Điều cần nắm là **vai trò credential được khai báo tường minh**. Cùng dùng `X509Certificate` trong Java không biến một verification credential của IdP thành certificate TLS máy chủ. `Saml2X509Credential` là API của **SAML**, không phải cấu hình SSLContext của HTTP server.

Trong `RelyingPartyRegistration`, IdP verification credentials thuộc **asserting party**; signing/decryption credentials thuộc **relying party**. Đối với một request SAMLResponse gửi vào ACS, Spring Security/OpenSAML dùng credentials từ đúng registration để xác minh chữ ký của IdP. Nếu SP liên kết nhiều IdP, không dùng một danh sách cert tổng hợp cho mọi tenant mà bỏ issuer/entityID trust binding.

### 9.1. Vì sao KeyInfo không đủ để chọn trusted cert?

XML Signature có thể chứa `ds:KeyInfo` hoặc `ds:X509Certificate`. Nhưng nếu browser tự gửi payload, attacker cũng có thể gửi **chứng thư của attacker** và ký XML bằng private key riêng. Về mặt toán học, chữ ký có thể verify với public key ấy; **không có nghĩa SP tin signer**.

SP phải lấy trusted certificate theo **registration/metadata đáng tin** đã được admin xác nhận. Chấp nhận certificate do payload đưa ra mà không kiểm trust là lỗi xác thực nghiêm trọng.

## 10. So sánh các lớp bảo mật trong từng sự cố

| Hiện tượng | TLS/HTTPS | SAML signature/trust | Chẩn đoán |
|---|---|---|---|
| Browser báo certificate hostname mismatch | **FAIL** | Có thể vẫn có SAML key hợp lệ | Sửa TLS SAN/hostname/ingress, không đổi IdP SAML cert bừa |
| Browser báo cert CA không tin cậy | **FAIL** | Không liên quan trực tiếp | Cấu hình certificate chain và trust anchor TLS |
| HTTPS IdP bình thường nhưng SP báo `Invalid Signature` | **PASS** | **FAIL** | Kiểm IdP signing cert, metadata rotation và XMLDSig |
| IdP đổi TLS cert nhưng giữ SAML signing key | Có thể vẫn PASS với cert mới đúng hostname | Thông thường vẫn PASS | Không phải đổi SAML cert vì TLS cert thay |
| IdP đổi SAML signing cert nhưng giữ TLS cert | TLS vẫn PASS | SP có thể FAIL nếu chưa trust key mới | Cập nhật SAML metadata/trusted signing keys trước rollover |
| ACS HTTPS hợp lệ nhưng SAML Audience sai | PASS | Signature có thể PASS | **FAIL SAML semantic**, sửa SP entityID/Audience |
| SAML Response ký đúng nhưng hết hạn | TLS có thể PASS | Crypto signature PASS, conditions FAIL | Không chấp nhận login |
| SAML Response chứa cert mới trong KeyInfo | Không quyết định | Chưa trusted | Không auto trust cert do client đưa |
| TLS bị terminate ở ingress | Browser ↔ ingress PASS | App vẫn phải verify SAML | SAML credentials không nằm trong TLS bundle |
| `EncryptedAssertion` không giải mã được | TLS có thể PASS | Encryption/decryption key mismatch | Kiểm SP decryption key và IdP public encryption cert |
| SAML ký bằng cert self-signed được SP pin an toàn | Không liên quan TLS WebPKI | Có thể PASS | Self-signed SAML cert không tự là lỗi |
| IdP metadata HTTPS ổn nhưng trỏ nhầm issuer | TLS PASS | Federation trust/issuer FAIL | So entityID và registration, không chỉ URL |

**Kỹ thuật debug:** Xác định thất bại xảy ra ở **TLS handshake**, **lấy metadata**, **xác minh SAML XML Signature**, **SAML conditions** hay **application authorization**. Các lỗi thuộc năm lớp khác nhau; thay chứng thư TLS không thể sửa lỗi `AudienceRestriction`.

## 11. Chứng thư ký SAML và chứng thư mã hóa: không đánh đồng

Với SAML signing:

~~~text
IdP private signing key --ký--> Response/Assertion XML
                    SP --dùng IdP public verification cert--> kiểm
~~~

Với SAML encryption:

~~~text
IdP --dùng SP public encryption cert--> EncryptedAssertion
                    SP --dùng SP private decryption key--> giải mã
~~~

Chứng thư mã hóa được sử dụng vì mục đích **confidentiality**; chứng thư ký dùng cho **authenticity/integrity** của tài liệu XML. Mã hóa thành công **không chứng minh** IdP phát Assertion; phải kiểm chữ ký và điều kiện theo profile. Tất cả quá trình trên vẫn dùng HTTPS để vận chuyển.

SAML metadata có thể dùng `KeyDescriptor use="signing"` và `use="encryption"` theo entity, còn TLS cert xuất hiện trong TLS handshake của hostname. Một tệp `sp-encryption.crt` được IdP dùng để mã hóa cho SP **không phải** IdP verification cert và không phải TLS cert của ACS.

## 12. Thời hạn chứng thư và nguyên tắc rotation khác nhau

### 12.1. Rotation HTTPS/TLS

Ví dụ chứng thư TLS endpoint IdP sắp hết hạn:

1. IdP quản trị TLS cert/chain mới với SAN đúng hostname, policy TLS phù hợp.
2. Cập nhật cert và private key ở web server hoặc ingress/load balancer; kiểm SNI, chain, cipher suites và handshake.
3. Đảm bảo clients tin CA chain mới; đo các lỗi handshake từ browser và SP fetch metadata.
4. Có thể tự động hóa bằng ACME/cert manager hoặc Spring Boot reloadable SSL bundle nếu runtime/framework hỗ trợ.
5. Không cần đổi IdP SAML signing key chỉ vì TLS cert đã đổi, trừ khi tổ chức có chủ đích dùng chung khóa (cần đánh giá rủi ro).

TLS cert rotation có phạm vi **kết nối đến hostname**. Khi có nhiều host/subdomain, phải kiểm đúng SNI, SAN và toàn bộ endpoint liên quan.

### 12.2. Rotation IdP SAML signing credential

IdP đổi signing key thì tất cả SP tin IdP đó phải chuẩn bị:

1. Tạo SAML keypair mới trong hệ thống IdP/HSM; giữ private key kín.
2. Công bố **public signing certificate mới** bằng metadata hoặc kênh đã xác minh.
3. Nếu hỗ trợ, SP trust đồng thời **old + new** signing certificates trong giai đoạn overlap; ghi nhận issuer/registration và fingerprint.
4. Kiểm test SAML Response ký bằng key mới trong môi trường được phép, cả Response/Assertion signatures.
5. Khi các SP đã sẵn sàng, IdP chuyển sang ký bằng key mới.
6. Giám sát `Signature validation failed`, request/login failures; chỉ gỡ key cũ sau khi rotation được xác nhận xong và không còn bản tin hợp lệ phụ thuộc nó.

**Điểm quan trọng:** TLS vẫn có thể hoàn toàn bình thường trong thời gian SAML key rollover thất bại. Thời hạn/cơ chế public CA certificate lifecycle **không** tự cập nhật trust của SP cho SAML signing key.

### 12.3. Rotation SP signing credential

Nếu SP ký `AuthnRequest`:

1. Tạo SP signing keypair mới.
2. Đăng public cert mới tại IdP hoặc cập nhật SP metadata để IdP có thể tin nó.
3. Kiểm IdP có cơ chế overlap cũ/mới; không chuyển private key SP sớm nếu IdP chưa chấp nhận.
4. Chuyển SP ký request bằng key mới, test luồng SSO và logout nếu cùng credential.
5. Gỡ public cert cũ ở IdP sau khi hoàn tất và hết cửa sổ chuyển đổi.

Không nhầm đây là đổi TLS cert của `portal.example.org`; TLS cert có thể giữ nguyên.

### 12.4. Rotation SP decryption credential

Nếu IdP mã hóa Assertion cho SP:

1. SP tạo decryption keypair mới và giữ private key, backup/DR an toàn.
2. Công bố public encryption certificate mới cho IdP; xác nhận thuật toán/profile tương thích.
3. Tùy thư viện, SP có thể cần giữ nhiều private decryption keys trong giai đoạn nhận assertions đã mã hóa với cert cũ.
4. IdP chuyển sang mã hóa bằng cert mới theo lịch; SP xác nhận giải mã, kiểm signature/conditions hoàn chỉnh.
5. Chỉ retire private key cũ khi toàn bộ thông điệp hợp lệ trong cửa sổ chuyển đổi đã được xử lý.

**Không** thay SP decryption cert bằng cert TLS trong IdP console trừ khi **chủ đích thiết kế** dùng một keypair được phép dùng ở cả hai vai trò; thông thường đây là một nhầm lẫn vận hành.

### 12.5. Quy tắc chung khi theo dõi hạn

Cần theo dõi song song **ba lịch**:
- Hạn dùng và chính sách CA của **TLS certificate**.
- Hạn dùng/cryptoperiod của **SAML signing keys/certs** cả IdP và SP.
- Hạn dùng/cryptoperiod của **SAML encryption/decryption keys/certs**.

Một chứng thư có `NotAfter` còn xa nhưng private key đã bị nghi lộ hoặc thuật toán không đạt policy vẫn phải rotate. Ngược lại, việc gia hạn chứng thư bằng **cùng public/private key** không đồng nghĩa đã đổi private key; threat model và cryptoperiod phải được quản trị riêng.

## 13. Kiểm tra chứng thư thực tế bằng OpenSSL, keytool và curl

Phần này giúp **xác định đang cầm file gì và dùng ở đâu**, không thay thế certificate-path validator hoặc SAML security provider.

### 13.1. Xem thông tin public X.509 certificate

~~~bash
openssl x509 -in idp-saml-signing.crt -noout -subject -issuer -serial -dates -fingerprint -sha256
~~~

Lệnh đọc file cert PEM, hiển thị Subject, Issuer, serial, dates và SHA-256 fingerprint. **Output phụ thuộc certificate thực**, không có stdout cố định. Lưu fingerprint trong biên bản federation; đây là cách nhận diện một cert cụ thể, không phải bằng chứng IdP trust nếu không có kênh xác minh độc lập.

### 13.2. Xem SAN/KU/EKU để đánh giá mục đích

~~~bash
openssl x509 -in portal-tls.crt -noout -text
~~~

Tìm các mục `X509v3 Subject Alternative Name`, `X509v3 Key Usage`, `X509v3 Extended Key Usage`, validity và public key algorithm. TLS server certificate thông thường cần hostname trong SAN, EKU serverAuth nếu extension xuất hiện. SAML signing certificate thường được quản lý theo metadata/trust federation; nếu chính sách IdP/SP kiểm KU/EKU, phải cấp phù hợp (ví dụ digitalSignature và EKU thích hợp nếu yêu cầu).

**Đừng suy ra duy nhất từ CN/filename:** Một certificate không có SAN phù hợp **không nên** được chấp nhận làm certificate TLS public cho hostname. Nhưng thiếu DNS SAN trong SAML signing certificate không tự là lỗi SAML nếu federation trust policy không yêu cầu hostname đó.

### 13.3. Kiểm TLS certificate đang được server trình bày

~~~bash
openssl s_client -connect login.example.org:443 \
  -servername login.example.org \
  -verify_hostname login.example.org \
  -verify_return_error
~~~

Tham số `-servername` gửi SNI cho đúng vhost; `-verify_hostname` yêu cầu đối chiếu hostname. Chạy trong môi trường/phiên bản OpenSSL hỗ trợ các tùy chọn và chain/trust store phù hợp. Lệnh này kiểm **TLS endpoint**, không kiểm SAML XML signature. Các dòng `Verify return code`/certificate chain phụ thuộc server thật, không có output mẫu cố định.

Lệnh đơn giản khác để kiểm trình duyệt/HTTP client tới URL:

~~~bash
curl -vI https://login.example.org/
~~~

Curl hiển thị thông tin TLS/HTTP theo môi trường; HTTP status 200/302/404 của đường dẫn cụ thể **không tự quyết định** SAML login hoạt động. Tránh `curl -k`/`--insecure` trong kiểm tra production vì vô hiệu hóa xác minh TLS và che giấu lỗi certificate.

### 13.4. Xem PKCS#12/Java keystore

~~~bash
keytool -list -v -storetype PKCS12 -keystore portal-tls.p12
~~~

Java `keytool` có thể yêu cầu mật khẩu qua prompt; không ghi mật khẩu trong command line/log/chat. Lệnh giúp đọc subject, alias, chain, fingerprints và độ dài khóa. Kiểm alias có private key cần thiết cho TLS, nhưng **không được dùng alias đó như SAML signing credential** trừ khi role/key đã được cấu hình và duyệt rõ ràng.

### 13.5. Đối chiếu public key giữa private key và certificate

Có thể lấy fingerprint SHA-256 của SubjectPublicKeyInfo (SPKI) từ certificate:

~~~bash
openssl x509 -in sp-signing.crt -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256
~~~

Với private key:

~~~bash
openssl pkey -in sp-signing.key -pubout -outform DER \
  | openssl dgst -sha256
~~~

Hai digest SPKI **phải trùng nhau** nếu public/private key là cặp tương ứng và định dạng được OpenSSL giải mã đúng. Lệnh này chỉ chứng minh **keypair consistency**, không chứng minh được certificate đáng tin theo SAML metadata hoặc TLS hostname/CA trust.

**Cảnh báo:** Không in private key, không lưu trong shell history qua `-passin pass:secret`; với HSM/PKCS#11 dùng lệnh/API của nhà cung cấp và kiểm soát secret store.

## 14. Java 17 độc lập: quan sát X.509 nhưng không tự xác minh trust

Chương trình dưới đây đọc một tệp X.509 certificate ở dạng PEM/DER bằng Java standard library, hiển thị thông tin phục vụ **kiểm kê chứng thư**. Nó **không** kết luận một cert đáng tin cho TLS hay SAML, vì những điều đó cần trust store/hostname hoặc trusted IdP registration.

Tệp `CertificateInspector.java`:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.HexFormat;

public class CertificateInspector {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CertificateInspector <certificate.pem>");
            System.exit(2);
        }

        Path certificateFile = Path.of(args[0]);
        X509Certificate cert;

        try (InputStream input = Files.newInputStream(certificateFile)) {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            cert = (X509Certificate) factory.generateCertificate(input);
        }

        byte[] fingerprint = MessageDigest.getInstance("SHA-256")
                .digest(cert.getEncoded());

        System.out.println("Subject: " + cert.getSubjectX500Principal());
        System.out.println("Issuer: " + cert.getIssuerX500Principal());
        System.out.println("NotBefore: " + cert.getNotBefore());
        System.out.println("NotAfter: " + cert.getNotAfter());
        System.out.println("PublicKey: " + cert.getPublicKey().getAlgorithm());
        System.out.println("FingerprintSHA256: "
                + HexFormat.of().withUpperCase().formatHex(fingerprint));
    }
}
~~~

Biên dịch bằng **JDK 17 trở lên**:

~~~bash
javac CertificateInspector.java
java CertificateInspector idp-saml-signing.crt
java CertificateInspector portal-tls.crt
~~~

Chương trình **biên dịch độc lập** (Java 17 có `HexFormat`) và chạy khi cung cấp file X.509 thật. Các dòng Subject, Issuer, NotBefore/NotAfter, PublicKey và SHA-256 fingerprint sẽ khác theo input, nên **không có stdout cố định**. Chương trình chỉ kiểm kê, không gọi `cert.checkValidity()` để từ chối hay thực hiện PKIX chain; kể cả nếu có `checkValidity()`, nó cũng không tự kiểm hostname, CA chain, issuer federation hay XML Signature.

**Không dùng chương trình này làm SAML validator**: nó không đọc Response/Assertion, không tính XMLDSig Reference/digest, không kiểm IdP metadata trust, replay hoặc SAML conditions.

### 14.1. Bài tập quyết định role bằng Java 17, stdout cố định

Tệp `CertificateRoleDecisionDemo.java` mô phỏng logic tổ chức: một file cert được duyệt cho TLS **không mặc nhiên** được duyệt làm SAML signing cert.

~~~java
public class CertificateRoleDecisionDemo {

    record CertificateApproval(
            String label,
            boolean tlsHostnameAndCaTrusted,
            boolean pinnedAsIdpSamlSigner) {
    }

    public static void main(String[] args) {
        CertificateApproval tls = new CertificateApproval(
                "IdP TLS", true, false);
        CertificateApproval saml = new CertificateApproval(
                "IdP SAML signing", false, true);

        System.out.println("TLS can serve HTTPS: "
                + tls.tlsHostnameAndCaTrusted());
        System.out.println("TLS can verify SAML: "
                + tls.pinnedAsIdpSamlSigner());
        System.out.println("SAML key can verify SAML: "
                + saml.pinnedAsIdpSamlSigner());
        System.out.println("SAML key can serve public HTTPS: "
                + saml.tlsHostnameAndCaTrusted());
    }
}
~~~

Chạy:

~~~bash
javac CertificateRoleDecisionDemo.java
java CertificateRoleDecisionDemo
~~~

**Stdout chính xác:**

~~~text
TLS can serve HTTPS: true
TLS can verify SAML: false
SAML key can verify SAML: true
SAML key can serve public HTTPS: false
~~~

**Giải thích:** Giá trị boolean là **quyết định trust đã được giả định** để học hai vai trò, không phải kết quả mà chương trình kiểm chứng được từ certificate. Nếu ai cũng có thể set `pinnedAsIdpSamlSigner=true` từ input chưa xác thực, bài tập không còn an toàn. Trong production, Spring Security phải thực hiện trust từ `RelyingPartyRegistration` và signature validation; TLS dùng certificate path/hostname validation của TLS stack.

## 15. KeyUsage, EKU, algorithm và hạn dùng: giống nhau và khác nhau

### 15.1. Key Usage / Extended Key Usage

**TLS server certificates** thường được cấp theo profile CA/Browser Forum và WebPKI, có SAN đúng hostname, EKU serverAuth và KU/thuật toán thích hợp. Chứng thư riêng cho **SAML XML signing** nên có policy phân định vai trò digital signature; không nhất thiết cần DNS SAN/serverAuth nếu nó không dùng làm TLS server cert. Chính sách KU/EKU của SAML phụ thuộc IdP/SP software và quy định tổ chức.

**Không dùng "certificate có KU digitalSignature" như bằng chứng trust**: bất cứ ai cũng có thể tạo chứng thư self-signed mang extension ấy. Cần xác định certificate **được IdP nào phát công bố và SP đã tin qua kênh nào**.

### 15.2. Thuật toán chữ ký certificate khác thuật toán ký XML

Có hai lựa chọn thuật toán khác nhau:

- **Certificate's signature algorithm:** ví dụ CA ký chứng thư X.509 bằng SHA-256 with RSA.
- **XMLDSig SignatureMethod/DigestMethod:** ví dụ IdP ký SAML Assertion với thuật toán XML Signature tương ứng. Các URIs trong XML quyết định cách verify digest/signature trên SAML, không suy từ certificate issuer signature.

Không giả định một cert có signature SHA-256 đồng nghĩa XML Signature đã dùng SHA-256. SP phải áp dụng **algorithm allowlist** cho XMLDSig, chống thuật toán cũ như RSA-SHA1/SHA1 digest theo chính sách bảo mật. Chọn RSA 2048+/SHA-256 hoặc mạnh hơn và thuật toán EC nếu cả IdP/SP hỗ trợ; khả năng tương thích sản phẩm phải được kiểm trước khi đổi thuật toán.

### 15.3. Cert validity không thay thế kiểm SAML time

Một X.509 cert có `NotAfter` còn hạn **không có nghĩa** SAML Assertion chưa hết hạn. SAML dùng `Conditions.NotBefore/NotOnOrAfter`, `SubjectConfirmationData.NotOnOrAfter` và những ràng buộc profile riêng. Ngược lại, một Assertion chưa hết hạn nhưng signing cert không còn được SP tin hoặc chính sách key sử dụng đã hết vẫn phải bị từ chối theo trust/security policy.

Không kéo dài SAML assertion validity chỉ vì chứng thư signing còn hạn 3 năm. Độ dài phiên web, điều kiện assertion, signing key lifecycle và TLS handshake lifetime là bốn thời gian **khác nhau**.

## 16. Một ca triển khai: IdP metadata HTTPS OK nhưng login SAML FAIL

**Hiện trạng giả định:**

- SP: `https://portal.example.org`, Spring Boot Servlet với `saml2Login`.
- IdP: `https://login.example.org` và metadata tại `https://login.example.org/metadata`.
- HTTP client của SP tải metadata thành công qua HTTPS; trình duyệt mở IdP không cảnh báo TLS.
- Browser hoàn tất MFA nhưng SP trả lỗi signature validation.

**Không nên làm:** Thay TLS certificate tại ingress của SP hoặc tắt validation chữ ký SAML, vì không có dữ kiện đó là nguyên nhân.

**Quy trình đúng:**

1. Lấy bản ghi lỗi ở tầng SAML provider: Response signature hay Assertion signature không hợp lệ?
2. Xác minh `RelyingPartyRegistration` đang resolve đúng `registrationId` và IdP entityID/Issuer.
3. Kiểm certificate public IdP signing trong metadata đã được SP tin: fingerprint, rollover mới/cũ, đúng tenant, không nhầm với TLS cert của `login.example.org`.
4. Kiểm XMLDSig signer, SignatureMethod/DigestMethod/Reference và việc Response/Assertion đã bị biến đổi khi qua proxy/browser không.
5. Kiểm nếu ký đúng nhưng bị từ chối ở **Audience, Recipient, Destination, time, InResponseTo hoặc replay**; log phân biệt lỗi mật mã với lỗi semantic.
6. Nếu IdP vừa rotate SAML signing key, cập nhật metadata/credentials có xác minh và thử key mới trong môi trường phù hợp.
7. Chạy lại positive/negative tests với test IdP và browser; đảm bảo không chấp nhận cert do payload KeyInfo tự mang.

**Kết luận:** TLS PASS chỉ nói HTTPS endpoint hoạt động; SAML signature FAIL chỉ ra federation trust hoặc XML signature không qua. Hai vấn đề không đồng nhất.

## 17. Một ca ngược lại: SAML key đúng nhưng HTTPS lỗi

Giả sử SP vẫn có IdP signing cert hợp lệ theo trust registry, nhưng trình duyệt bị cảnh báo:

~~~text
ERR_CERT_COMMON_NAME_INVALID
hoặc lỗi hostname mismatch / unknown CA
~~~

Những lỗi đó thường thuộc **TLS hostname verification/CA chain**, không thuộc Response signing credential. Không thể dùng SAML metadata để chứng minh browser phải tin TLS server cert.

Hướng xử lý:

1. Kiểm hostname public, DNS, SNI và cert chain mà ingress/IdP đang xuất.
2. So SAN với hostname browser/HTTP client truy cập; nếu là private CA thì phân phối trust anchor theo chính sách.
3. Kiểm hiệu lực cert, OCSP/revocation/CT và cấu hình TLS nếu nền tảng yêu cầu.
4. Với ứng dụng lấy metadata bằng HTTP client Java, kiểm JVM truststore hoặc SSL bundle của **client HTTP đang dùng**; không tự set `trustAll`.
5. Sau khi TLS được sửa, **SAML signature/trust vẫn phải kiểm riêng** trước khi đăng nhập.

**Cẩn trọng:** HTTPS của SP và HTTPS của IdP là hai đầu khác nhau. Chứng thư TLS của SP hết hạn sẽ ảnh hưởng ACS/portal truy cập bằng browser; TLS của IdP hết hạn ảnh hưởng trang SSO và có thể ảnh hưởng fetch metadata. Cả hai vẫn khác signing cert của SAML.

## 18. Checklist bảo mật cho code review và vận hành

### 18.1. HTTPS/TLS checklist

- [ ] DNS/SAN khớp hostname thật ở browser/HTTP client, kể cả SNI và ingress routing.
- [ ] Certificate chain và trust anchor hợp lệ; không bỏ hostname validation hoặc dùng `trust-all`.
- [ ] TLS 1.3/1.2 an toàn, ciphers được phép; private key ở TLS termination được bảo vệ.
- [ ] Giám sát `notAfter`, gia hạn tự động khi phù hợp, rollout và rollback cert có kiểm soát.
- [ ] Metadata URL của IdP được lấy qua HTTPS đúng hostname, đúng nguồn đã phê duyệt.
- [ ] Nếu reverse proxy terminate TLS, external ACS/metadata URL vẫn là HTTPS và forwarded headers được tin cậy đúng.
- [ ] Không dùng `curl -k` hoặc tắt JVM certificate validation để "khắc phục" lỗi prod.

### 18.2. SAML signing checklist

- [ ] SP đã cấu hình **IdP verification public certificate** theo đúng IdP entityID/registration.
- [ ] Trusted signing cert được lấy từ metadata/kênh phê duyệt, không từ `KeyInfo` chưa tin cậy.
- [ ] XML Signature bảo vệ **chính Response/Assertion được dùng**, chống duplicate ID và XML Signature Wrapping.
- [ ] Chữ ký XML có algorithm/digest đáp ứng policy, không cho phép thuật toán yếu.
- [ ] Có kiểm SAML issuer, audience, recipient, destination, thời hạn, `InResponseTo` khi áp dụng, và replay.
- [ ] Không nhầm Response-signed với Assertion-signed; theo profile/policy phải xác thực đầy đủ.
- [ ] Nếu SP ký `AuthnRequest`, IdP có **SP public signing cert** đúng cặp private key SP.
- [ ] Nếu IdP mã hóa Assertion, IdP có **SP public encryption cert** và SP có **matching decryption private key**.
- [ ] Có kế hoạch luân phiên key/cert, overlap trust, tài liệu fingerprint và sự đồng ý hai bên.
- [ ] Không log SAML Response thô, attributes/PII hay private keys vào log public.

### 18.3. Bảng kiểm ai làm gì

| Việc | Người phụ trách thường gặp | Bằng chứng nghiệm thu |
|---|---|---|
| Gia hạn TLS cert IdP | IdP infrastructure/web team | HTTPS browser/s_client đúng SAN/CA |
| Gia hạn TLS cert SP | App/infrastructure/ingress team | ACS/portal HTTPS đúng hostname |
| Rotate IdP SAML signing key | IdP security/federation team | SP verify Response/Assertion bằng cert mới |
| Cập nhật trusted IdP cert ở SP | App/Spring Security team | IdP entityID + fingerprint + login test |
| Rotate SP SAML signing key | App security team và IdP admin | IdP verify AuthnRequest mới |
| Rotate SP encryption key | App security team và IdP admin | EncryptedAssertion decrypt thành công |
| Thay SAML metadata URL | Hai bên xét trust/tenant | Metadata đúng issuer/cert, SAML login thành công |
| Update Java truststore HTTPS | SP infrastructure/client HTTP team | Metadata HTTPS fetch OK, không `trustAll` |

## 19. Kiểm thử: các kết quả phải độc lập

| Test | Tình huống | Kỳ vọng |
|---|---|---|
| T1 | TLS cert IdP hợp lệ, SAML signing cert đúng | HTTPS PASS; SAML có thể PASS khi conditions đúng |
| T2 | TLS cert IdP hợp lệ, IdP SAML signing cert sai | HTTPS PASS; SAML **FAIL** |
| T3 | TLS cert IdP sai hostname, SAML signing key đúng | HTTPS client **FAIL**; không được bypass TLS |
| T4 | SP ingress thay TLS keypair, IdP signing key giữ nguyên | HTTPS vẫn PASS nếu config đúng; SAML trust thường không đổi |
| T5 | IdP rotate SAML key, SP chưa trust public key mới | HTTPS có thể PASS; SAML **FAIL** |
| T6 | IdP signing cert self-signed đã được SP tin xác thực | SAML signature có thể PASS, không đòi public WebPKI CA |
| T7 | Browser gửi XMLDSig cùng attacker certificate trong KeyInfo | SAML **FAIL** vì certificate không trusted |
| T8 | SAML Response signature đúng, Assertion sai Audience | SAML **FAIL** vì semantic validation |
| T9 | EncryptedAssertion dùng SP public cert sai cặp | SP **FAIL decryption** dù HTTPS/signature có thể đúng |
| T10 | SP AuthnRequest cần ký nhưng IdP chưa nhận SP public cert | IdP **FAIL request signature** |
| T11 | TLS và SAML đều PASS nhưng user thiếu quyền business | App **403** cho tài nguyên hạn chế |
| T12 | Cập nhật SAML cert mới ở SP, TLS cert không đổi | HTTPS độc lập; SAML PASS sau trusted rollover |

Đừng chỉ test **đường thành công**. Phải chủ động dùng test IdP/cert sai, lỗi hostname, wrong issuer, untrusted certificate, expired assertion, replay, altered XML và signing-key rotation. Mục đích là chứng minh mỗi lớp bảo vệ **fail closed đúng trách nhiệm**, thay vì một lớp vô tình "che" lỗi của lớp khác.

## 20. Câu hỏi ôn tập

1. **SAML signing certificate có bắt buộc trùng TLS certificate của IdP không?** Không. Đây là hai vai trò/trust khác nhau; thường nên tách keypair.
2. **SAML cert self-signed có mặc nhiên không đáng tin?** Không. Nếu public key đã được SP tin qua metadata/kênh federation có xác thực, nó có thể được dùng để verify SAML XML signature.
3. **Browser truy cập HTTPS IdP bình thường đã đủ để SP tin `SAMLResponse` chưa?** Chưa. SP còn phải kiểm XML Signature bằng trusted IdP signing key và đầy đủ SAML conditions.
4. **Khi IdP đổi TLS certificate, SP có phải đổi SAML verification cert không?** Không mặc nhiên; chỉ cần cập nhật SAML trust nếu signing key/metadata trust thực sự thay đổi.
5. **Khi IdP đổi SAML signing certificate nhưng TLS không đổi, có thể gây login lỗi không?** Có. SP giữ trusted cert cũ sẽ không verify được signature mới.
6. **SP signing cert dùng để làm gì?** IdP verify chữ ký request SAML do SP phát, không phải để browser kiểm HTTPS.
7. **SP encryption cert dùng để làm gì?** IdP mã hóa assertion bằng SP public key, SP giải mã bằng private decryption key.
8. **Có thể dùng cert nằm trong `ds:KeyInfo` làm trust ngay không?** Không. Cần credential từ IdP registration/metadata đã xác thực.
9. **`server.ssl.bundle` có làm Spring Security tự tin IdP SAML signing cert không?** Không. Nó cấu hình TLS server, không phải SAML verification credentials.
10. **IdP entityID có phải DNS SAN của TLS cert không?** Không. EntityID là định danh logic trong SAML, có thể là URI/URN.
11. **Tại sao kiểm SHA-256 fingerprint chứng thư không đủ?** Fingerprint chỉ nhận diện bytes cert. Cần biết fingerprint đó được xác minh từ nguồn nào và thuộc vai trò/issuer nào.
12. **TLS certificate còn hạn có nghĩa Assertion còn hạn không?** Không. Assertion có thời hạn `Conditions/SubjectConfirmationData` riêng.
13. **Lỗi `Signature validation failed` nên sửa certificate nào trước?** Kiểm SAML IdP signing verification credentials/issuer/trust trước; chỉ xét TLS nếu có lỗi handshake/fetch metadata thực tế.
14. **TLS ở ingress thì Spring có thể không có `server.ssl.*` không?** Có. Nhưng vẫn phải verify SAML bằng IdP verification cert riêng.
15. **Một cặp khóa có thể dùng cho hai mục đích?** Kỹ thuật đôi khi có thể, nhưng chính sách bảo mật/interop thường ưu tiên tách; không được tự suy ra từ certificate cùng định dạng.

## 21. Tài liệu chính thức và hướng dẫn đáng tin cậy

- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML2 Metadata/registration: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security JavaDoc – Saml2X509Credential và credential types: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Boot – SSL Bundles/HTTPS: https://docs.spring.io/spring-boot/reference/features/ssl.html
- Spring Boot – SAML Relying Party properties: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- OWASP – SAML Security Cheat Sheet, X.509 Certificate Considerations: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- OWASP – Transport Layer Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html
- OASIS SAML 2.0 Metadata Specification: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Core (XML Signature and Conditions): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- RFC 5280 – X.509 Public Key Infrastructure: https://www.rfc-editor.org/rfc/rfc5280
- RFC 6125 / RFC 9525 – TLS Service Identity and name checking: https://www.rfc-editor.org/rfc/rfc9525

**Tổng kết:** Chứng thư HTTPS xác thực **endpoint/kênh truyền** theo DNS/CA/trust store; chứng thư ký SAML xác thực **chữ ký thông điệp XML của một IdP/SP đã được đăng ký tin cậy** theo metadata/verification credentials. Mã hóa SAML có thêm cặp khóa riêng. Trong Spring Security, cấu hình `server.ssl.*` (hoặc ingress) **không thay** `RelyingPartyRegistration.assertingParty.verificationCredentials`. Để federation an toàn, hãy kiểm độc lập TLS, metadata trust, chữ ký SAML, điều kiện Assertion và authorization; lập kế hoạch key rotation cho từng vai trò.
