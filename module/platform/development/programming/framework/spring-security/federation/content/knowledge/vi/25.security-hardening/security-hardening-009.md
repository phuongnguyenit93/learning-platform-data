# Không tự động tin chứng thư nằm trong thông điệp chưa được xác minh

> **Module:** Spring Security – federation · **Nhóm:** Gia cố an toàn. Bài Knowledge hướng dẫn thiết lập **ranh giới tin cậy (trust boundary)** khi SAML Response/Assertion, JWT/JWS/JWK, XML Signature, SAML metadata hay HTTP request chứa chứng thư X.509 hoặc khóa công khai. Quy tắc chính: **thông điệp do đối phương kiểm soát có thể mang chính khóa/chứng thư do đối phương tạo**, vì vậy “verify chữ ký bằng khóa được đính kèm và kết quả đúng” **không xác thực IdP/issuer**. Phải đối chiếu với khóa/chứng thư đã tin cậy **từ kênh độc lập** và ràng buộc vào đúng issuer, tenant, RP, loại thông điệp, thuật toán, audience và freshness. Ví dụ Java 17 có thể chạy độc lập; các đoạn Spring Security là cấu hình minh họa cần đối chiếu release đang dùng.

## 1. Tình huống tấn công: người gửi cung cấp luôn bằng chứng về chính mình

Một ứng dụng Portal SP chỉ tin IdP `https://idp.example.org/saml`. Browser gửi một `SAMLResponse` gồm Assertion có tên `admin` và `ds:Signature`. Bên trong `ds:KeyInfo` có `ds:X509Data/ds:X509Certificate`.

Giả sử lập trình viên dùng quy trình:

```text
1. Nhận SAMLResponse từ browser.
2. Đọc X509Certificate ngay bên trong SAMLResponse.
3. Lấy public key từ certificate đó.
4. Kiểm tra ds:Signature bằng public key vừa lấy.
5. Nếu Signature.verify() = true thì đăng nhập user.
```

**Lỗi:** người tấn công có thể tự tạo RSA keypair, tự cấp một chứng thư X.509 chứa public key của mình, ký một Assertion giả bằng private key tương ứng, đính kèm chứng thư vào `KeyInfo` và gửi response. Bước 4 vẫn cho kết quả **mathematically valid** vì chữ ký và public key thuộc **cùng người tấn công**.

**Bài toán cần trả lời không chỉ là “chữ ký có hợp lệ với khóa này?” mà còn là “khóa này có thực sự được IdP được phép dùng cho đúng relying party/tenant và thời điểm này hay không?”**

### 1.1. Hai phép kiểm khác nhau

| Kiểm tra | Câu hỏi | Nếu bỏ qua |
| --- | --- | --- |
| **Cryptographic signature verification** | Byte được chọn có được ký bằng private key tương ứng với public key đã chọn không? | Không biết dữ liệu có bị sửa hay không |
| **Trust establishment / key authorization** | Public key được chọn có được tin cậy **cho issuer/purpose/tenant này** bằng nguồn không do message quyết định không? | Một kẻ tự ký có thể mạo danh IdP |
| **Protocol validation** | Message signed có đúng issuer, audience, recipient, InResponseTo, status, time, replay và user context? | Message hợp chữ ký vẫn có thể bị dùng sai ngữ cảnh |
| **Application authorization** | User đã xác thực có được thực hiện thao tác cụ thể? | Signed `role=admin` không tự đồng nghĩa được quyền admin |

Có thể có cả bốn kiểm tra đều độc lập. Một payload “đã có chữ ký” không tự cho phép tin mọi claim bên trong hoặc mọi quyền do issuer đưa ra.

### 1.2. Mục tiêu học tập

Sau bài, bạn sẽ:

1. Giải thích nguồn tin cậy của public key và vì sao **embedded certificate không tự đáng tin**.
2. Phân biệt signature validity, certificate validity, chain/path trust, identity binding và authorization.
3. Hiểu `ds:KeyInfo`, `ds:X509Certificate`, `RetrievalMethod` và XML Signature Wrapping (XSW).
4. Cấu hình Spring Security SAML2 `RelyingPartyRegistration` với IdP verification credentials đến từ nguồn đã xác thực.
5. Phân biệt **SAML metadata trusted onboarding** và **chứng thư nằm trong SAMLResponse**.
6. Áp dụng cùng nguyên tắc cho JWT `kid`, `jwk`, `x5c`, `jku`, `x5u` và server-side trusted JWKS.
7. Hiểu khi nào dùng certificate pinning vs PKIX certificate path validation, TLS/mTLS và trusted reverse proxy.
8. Xử lý key rollover, issuer nhiều tenants, chain expiry/revocation, algorithm confusion, SSRF và signature wrapping.
9. Chạy demo Java 17 cho thấy **attacker-signed message verify được bằng key đính kèm nhưng bị trusted-key verifier từ chối**.
10. Thiết kế kiểm thử âm tính cho untrusted signing keys và release process.

## 2. Trust anchor phải đến từ nơi khác thông điệp đang xét

```text
UNTRUSTED SIDE
browser / HTTP client / SAMLResponse / JWT / XML KeyInfo
      |
      +-- claims issuer = "trusted-idp"
      +-- embedded cert = attacker-generated certificate
      +-- signature = signed with attacker's own private key
      |
      v
Service / Relying Party
      |
      +-- Step A: resolve preconfigured RP/issuer trust context
      |             by server-side configuration and safe routing
      +-- Step B: obtain authorized verification keys
      |             from trusted metadata / pinned cert / authenticated JWKS
      +-- Step C: cryptographically verify SIGNED bytes
      |             with authorized key, not arbitrary embedded key
      +-- Step D: validate issuer, audience, recipient,
      |             time, InResponseTo, replay, assertion semantics
      +-- Step E: map trusted identity to local authorization
      |
      v
Authenticated user (only if every required step passed)
```

Một claim trong message như `Issuer=idp.example.org` **chưa chứng minh** message do IdP thật gửi. Nó chỉ có thể là một **selector/hint** để chọn **trust configuration đã phê duyệt**, sau đó chữ ký phải hợp với authorized key thuộc configuration ấy.

### 2.1. Nguồn nào có thể thiết lập tin cậy?

- Chứng thư IdP đã được quản trị viên lấy qua **kênh đã xác thực** và lưu trong cấu hình/RelyingPartyRegistration.
- SAML metadata được nhận qua **địa chỉ IdP tin cậy**, được bảo vệ bằng TLS và quy trình onboarding; nếu policy đòi signed metadata thì **verify signature metadata bằng trust anchor đã có sẵn**, không từ metadata đó tự cấp.
- OIDC discovery `issuer` **do RP/Resource Server cấu hình trước**, metadata trả `jwks_uri` được truy cập theo chính sách HTTPS/hostname/egress và ràng buộc issuer.
- JWKS URL cố định phía server, gắn với một issuer đáng tin. Các keys lấy từ endpoint này không mặc nhiên dùng cho issuer khác.
- Local truststore/Pkix trust anchors được tổ chức quản lý, với chính sách certificate chain, identity binding, EKU/KU và revocation phù hợp.
- Trust-management service/KMS/certificate manager độc lập có audit và change approval.

**Không phải nguồn tin cậy:** một PEM bất kỳ trong SAMLResponse, raw `x5c` trong JWT header, claim `iss` chưa verify, HTTP request body `certificate`, mTLS certificate header do browser tự gửi, hoặc URL `jku` tự chọn bởi đối phương.

### 2.2. TOFU và tự động onboarding

“Trust On First Use” có thể phù hợp một số giao thức/trường hợp có kiểm soát, nhưng **không phải mặc định an toàn cho SAML IdP signing keys hay JWT issuers**. Nếu lần đầu nhận cert qua chính một login request chưa xác minh rồi tự pin, attacker có thể chiếm mối tin cậy đầu tiên.

Nếu tổ chức có quy trình tự động thêm IdP/tenants, phải có **bên quản trị phê duyệt issuer/entityID và key source**, domain ownership verification, trust-policy checks, egress controls và audit; không để bất kỳ browser POST nào thêm một trusted issuer.

## 3. X.509 certificate: bốn tầng thường bị nhầm

### 3.1. Certificate chứa public key không đồng nghĩa có trust

Một X.509 certificate thường chứa subject, issuer, public key, validity period, serial, extensions và CA signature. Có thể parse thành `X509Certificate`, gọi `getPublicKey()` để verify một signature. Việc parse thành công **không phải trust validation**.

**Một chứng thư tự ký** có thể có:

```text
Subject: CN=Corporate Identity Provider
Issuer:  CN=Corporate Identity Provider
Validity: 2026-01-01 to 2030-01-01
Public key: attacker-owned RSA key
Signature: signed by attacker's same private key
```

Các tên/validity đều có thể do attacker tự chọn. Gọi `cert.verify(cert.getPublicKey())` trên một certificate tự ký chỉ chứng minh cấu trúc cert signature phù hợp **với chính public key tự cung cấp**, không chứng minh đó là CA/IdP mà RP tin cậy.

### 3.2. Những phép kiểm có và không có ý nghĩa

| Thao tác Java/PKIX | Điều chứng minh | Điều không chứng minh |
| --- | --- | --- |
| `CertificateFactory.generateCertificate` | Input parse thành certificate | Issuer của cert đáng tin |
| `x509.checkValidity()` | Thời gian hiện tại nằm trong interval của cert | Cert thuộc IdP đã đăng ký |
| `x509.getPublicKey()` | Trích public key | Key được phép ký login Assertion |
| `x509.verify(x509.getPublicKey())` | Với cert tự ký, chữ ký cert khớp self key | Cert có trusted issuer |
| `Signature.verify(signatureBytes)` với embedded key | Chữ ký payload đúng với key đó | Key là của trusted IdP |
| `CertPathValidator` với trust anchors server-configured | Xây/kiểm chứng trust path theo PKIX và params | Payload đúng audience/issuer của app |
| Exact trusted SPKI/cert pin so với registry | Key/cert đã được phê duyệt cho đối tác theo pin policy | SAML assertion hợp lệ về protocol và replay |

PKIX chain validation còn phải xét certificate validity, name/identity binding, key usage, extended key usage, revocation nếu yêu cầu và ứng dụng certificate policy. Không coi “chain ends at **bất kỳ public CA nào**” là đủ để certificate được phép ký SAML assertion của **một IdP cụ thể**.

### 3.3. SAML certificate pinning khác TLS PKI

Trong nhiều SAML federations, IdP dùng **self-signed X.509 signing certificates** đăng trong metadata hoặc trao đổi trực tiếp với SP. SP có thể **tin một signing certificate cụ thể** được onboarding an toàn, không yêu cầu cert chaining về public browser CA. Đây là kiểu **explicit key/certificate trust**, hợp lệ nếu được quản trị và gắn với đúng IdP.

Ngược lại, chỉ áp dụng “certificate chain trust bởi hệ thống CA public” cho mọi signing cert có thể vừa **reject các IdP hợp lệ** vừa **mở cửa cho certificates không liên quan** nếu không ràng buộc khóa/subject với IdP. Phải chọn rõ trust model.

### 3.4. Truststore, certificate store và private key store

- **Truststore / approved verification credentials:** public certificates/keys được phép **verify** message từ một IdP.
- **Keystore / private keys của SP:** SP dùng **ký AuthnRequest/LogoutRequest** hoặc **giải mã EncryptedAssertion**.
- **TLS server certificate:** xác thực HTTPS origin trên network.
- **mTLS client certificate:** xác thực kết nối client trong TLS handshake khi gateway/server thật sự verify.
- **Certificate embedded in message:** dữ liệu do message cung cấp; có thể dùng làm **hint**, không tự tin cậy.

Một private key của RP **không** trở thành IdP verification credential. Và public TLS cert của `idp.example.org` **không tự mặc nhiên** là SAML signing cert của IdP trừ khi trust contract xác định như vậy.

## 4. SAML 2.0: KeyInfo chính là vùng có thể bị giả mạo

### 4.1. Một XML Signature có thể mang certificate

Ví dụ XML **không phải assertion hoàn chỉnh**, chỉ mô tả cấu trúc:

```xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <!-- CanonicalizationMethod, SignatureMethod,
         Reference URI, Transforms, DigestMethod, DigestValue -->
  </ds:SignedInfo>
  <ds:SignatureValue>BASE64_SIGNATURE</ds:SignatureValue>
  <ds:KeyInfo>
    <ds:X509Data>
      <ds:X509Certificate>BASE64_DER_CERT</ds:X509Certificate>
    </ds:X509Data>
  </ds:KeyInfo>
</ds:Signature>
```

`KeyInfo` là phương tiện cung cấp key-identification/related data. Việc XML Signature parser có thể tìm một khóa ở `KeyInfo` **không** có nghĩa khóa đã được app cho phép. W3C XML Signature Core tách thông tin khóa khỏi chính sách tin cậy của ứng dụng.

### 4.2. Kịch bản forgery từng bước

```text
Attacker:
  tạo keypair K_attacker
  tạo X509 certificate chứa public(K_attacker)
  tạo Assertion:
    Issuer = trusted IdP entityID
    NameID = admin@example.org
    Role = ADMIN
  ký Assertion bằng private(K_attacker)
  nhúng certificate trong KeyInfo
  POST SAMLResponse đến /login/saml2/sso/portal

Vulnerable SP:
  publicKey = KeyInfo.X509Certificate.publicKey
  Signature.verify(publicKey) == true
  chấp nhận admin  <-- TRUST BOUNDARY BỊ PHÁ

Hardened SP:
  registration = server-side trusted configuration
  trustedKeys = verification credentials for expected IdP
  verify signature with trustedKeys
  K_attacker không nằm trong trustedKeys => REJECT
```

Tên `Issuer` trong XML do attacker tự ghi không thể biến private key của attacker thành IdP key. Không chấp nhận key mới chỉ vì Subject DN trông giống, certificate có CN giống IdP, `KeyInfo` trùng tên file hoặc cert “còn hạn”.

### 4.3. Không dùng message để tự đăng ký trusted IdP

Sai về thiết kế:

```java
// ANTI-PATTERN — không dùng.
// X509Certificate supplied = parseCertFromSamlKeyInfo(untrustedXml);
// Signature signature = findSignature(untrustedXml);
// if (verifyWith(signature, supplied.getPublicKey())) {
//     authenticateNameId(readNameId(untrustedXml));
// }
```

Đoạn trên là pseudocode minh họa lỗi, không phải API Spring Security hoàn chỉnh. Vấn đề kép là **key do đối phương lựa chọn** và **NameID được đọc từ XML chưa ràng buộc vào đúng signed subtree**.

### 4.4. KeyInfo có thể chỉ là hint, không phải trust anchor

Một SP có thể:

1. Chọn trusted `RelyingPartyRegistration` dựa trên server-side route/state hoặc issuer candidate đã mapping.
2. Lấy **tập IdP verification credentials đã phê duyệt** từ registration.
3. Xác minh XML signature bằng một key trong tập đó.
4. Nếu `KeyInfo` có certificate/key name, chỉ dùng để **chọn ứng viên trong tập đã tin cậy**; không thêm key vào tập từ message.
5. Sau khi verify, kiểm tra key có được phép ký loại SAML document này, thời điểm này, và claims/protocol rules.
6. Xử lý session/authorization từ **assertion đã được xác minh**.

Một số SAML implementations có thể bỏ qua `KeyInfo` hoàn toàn; đây là cách tránh nhầm lẫn nếu trusted signing key đã cố định. OWASP SAML Security Cheat Sheet khuyến nghị dùng keys lưu trong local trusted source, bỏ qua KeyInfo chưa được trust.

## 5. XML Signature Wrapping: kể cả chữ ký hợp lệ vẫn có thể lấy sai Assertion

### 5.1. Hai câu hỏi độc lập

Ngay cả khi verify bằng **đúng trusted IdP key**, app vẫn có thể sai nếu XML parser/handler lấy user name từ **nút XML khác** với nút được signature bảo vệ.

```text
SAMLResponse
  Assertion[@ID="signed-1"]
    Subject/NameID = normal-user
    ds:Signature references #signed-1  [VALID]

  malicious wrapper/another node
    Subject/NameID = admin
    [NOT SIGNED]
```

Nếu code đọc `getElementsByTagName("NameID")[0]` hoặc query không gắn với verified assertion, attacker có thể lợi dụng XML Signature Wrapping (XSW). Từng thư viện có cơ chế chống XSW khác nhau; **không tự parse rồi tự nối XML Signature check với business mapper bằng DOM không kiểm soát**.

### 5.2. Quy tắc hardened SAML validation

- Dùng phiên bản OpenSAML/Spring Security được bảo trì, không tự triển khai XMLDSig bằng regex.
- Tắt DTD/external entities/XXE; giới hạn kích thước, depth và số assertions.
- Schema validation với schema **local, trusted**, nếu threat model/implementation yêu cầu; không tự tải schema từ URI untrusted.
- Chỉ chấp nhận canonicalization/signature/digest algorithms và transforms được policy hỗ trợ; tránh weak algorithm.
- Kiểm tra unique IDs; signature Reference URI trỏ đúng element được expected; không cho duplicate ID masquerade.
- Bind subject/attributes/conditions vào **assertion thực sự verified**, không chọn node theo global search.
- Xác minh cả `Response`/`Assertion` signature theo security profile, không tự chấp nhận unsigned data nằm ngoài signed subtree.
- Kiểm tra `Issuer`, `AudienceRestriction`, `Recipient`, `Destination`, `NotBefore`, `NotOnOrAfter`, `InResponseTo`, `SubjectConfirmationData` và replay.
- Không tin `NameID` hay `Role=ADMIN` trước khi mọi kiểm tra signature/protocol hoàn tất.
- Vô hiệu hóa remote retrieval qua `RetrievalMethod`/external References nếu ứng dụng không cần và kiểm soát chặt nguồn.

**Chú ý:** “verify chữ ký XML” chưa chắc đã verify **document/element mà ứng dụng thực sự dùng**. Đây là security boundary quan trọng ngang việc không tin certificate nhúng.

## 6. Spring Security SAML2: verification credentials ở registration

### 6.1. Cách định nghĩa tin cậy rõ ràng

Spring Security SAML2 service provider thiết lập **IdP verification certificates** trong `RelyingPartyRegistration.assertingPartyMetadata.verificationX509Credentials`. Các certificates này phải đến từ **quy trình onboarding đáng tin**, không tự thay bằng certificate lấy từ POST `SAMLResponse`.

Ví dụ Spring Boot YAML (cần các thành phần SAML2 application khác):

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              singlesignon:
                url: "https://idp.example.org/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:trusted-idp-signing.pem"
```

File `trusted-idp-signing.pem` được **onboarded và kiểm tra qua kênh độc lập**; không phải file user upload vào callback. Ví dụ `sign-request: false` chỉ là lựa chọn profile minh họa, không phải khuyến nghị security chung: trong production phải tuân yêu cầu ký AuthnRequest của IdP và SP.

### 6.2. Java registration fragment với trusted certificate

Theo Spring Security SAML2 reference, có thể cấu hình:

```java
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
    .Saml2X509Credential;

// Fragment: trustedCertificate là X509Certificate đã được đọc
// từ nguồn TRUSTED/PINNED, không lấy từ inbound SAMLResponse.
Saml2X509Credential verifying =
        Saml2X509Credential.verification(trustedCertificate);

RelyingPartyRegistration registration = RelyingPartyRegistration
    .withRegistrationId("corporate")
    .assertingPartyMetadata(party -> party
        .entityId("https://idp.example.org/saml")
        .singleSignOnServiceLocation("https://idp.example.org/sso")
        .verificationX509Credentials(c -> c.add(verifying)))
    .build();
```

Đây là fragment ứng dụng Spring Security, không phải Java file độc lập: cần dependency `spring-security-saml2-service-provider`, trusted certificate loading, RP entityId/ACS và full filter chain/metadata registration theo deployment. API `assertingPartyMetadata` là hình thức trong tài liệu hiện tại; các bản Spring Security cũ có tên builder/metadata methods khác, cần đối chiếu release.

**Không viết một `AuthenticationProvider` thay thế chỉ để gọi `Signature.verify(certFromKeyInfo)`.** Dùng OpenSAML provider mặc định và xác minh IdP trust credentials đã đăng ký; nếu customize, giữ nguyên toàn bộ các protocol validators.

### 6.3. Không nhầm certificate roles

| Credential trong Spring SAML2 | Dùng làm gì? |
| --- | --- |
| `assertingParty.verificationX509Credentials` | Public certs tin cậy dùng verify IdP SAML messages |
| `relyingParty.signingX509Credentials` | Private key + cert SP dùng ký AuthnRequest/SLO requests nếu cần |
| `relyingParty.decryptionX509Credentials` | SP private key dùng giải mã encrypted assertions |
| `assertingParty.encryptionX509Credentials` | Public cert của IdP dùng encrypt message outbound từ SP nếu profile yêu cầu |

Không gán **chứng thư nằm trong inbound Assertion** vào `verificationX509Credentials` trong lúc xử lý request. Đây chính là nâng dữ liệu untrusted thành trust state.

### 6.4. IdP nhiều tenants

Có thể có IdP A và IdP B đều gửi assertion đến chung ACS endpoint. Không gom tất cả certificates vào một global trust set rồi chỉ verify “ký bởi bất kỳ IdP nào”; phải ràng buộc **registration/tenant/expected issuer và audience**.

```text
tenant-A:
  issuer = https://idp-a.example.org
  trustedSigningKeys = [A1, A2]
  serviceProviderEntityId = https://portal.example.org/sp/a

tenant-B:
  issuer = https://idp-b.example.org
  trustedSigningKeys = [B1]
  serviceProviderEntityId = https://portal.example.org/sp/b
```

Nếu thông điệp claim issuer A nhưng ký bằng key B, không được accept vì B cũng là trusted IdP ở hệ thống. Tenant selector từ path/request được dùng như candidate để resolve configuration; **không dùng một string trong unverified assertion để chọn arbitrary trust root**. Với IdP-initiated SSO, cần một mapping IdP↔RP đã onboard và kiểm tra replay/recipient/audience thích hợp.

## 7. SAML metadata cũng cần bootstrap trust

### 7.1. Metadata từ đâu đến?

SAML metadata có thể chứa `EntityDescriptor`, `IDPSSODescriptor`, `KeyDescriptor use="signing"` và `ds:X509Certificate`.

Metadata **không mặc nhiên trusted** chỉ vì có `KeyDescriptor`. Trước khi dùng nó tạo `RelyingPartyRegistration`:

- Địa chỉ metadata phải thuộc IdP đã onboarding, không lấy từ `?metadataUrl=...` trong request.
- HTTPS TLS endpoint/certificate chain và DNS phải được kiểm tra; chống SSRF, redirect/host confusion.
- Nếu policy yêu cầu metadata signed: verify signature metadata bằng **metadata signing certificate/trust anchor đã có từ trước**, không bằng certificate nhúng chưa được kiểm chứng trong chính metadata.
- Kiểm tra entityID, SSO endpoints, signing roles, validUntil/cacheDuration, size, frequency và rollout procedures.
- Thay đổi signing keys trong metadata là **trust configuration change**, cần audit, alert và approval phù hợp.

### 7.2. Spring Security metadata signature verification có điều kiện

Tài liệu Spring Security về SAML metadata cung cấp `OpenSaml5AssertingPartyMetadataRepository` với `verificationCredentials`. Lưu ý quan trọng: **nếu không đưa metadata verification credentials, thành phần này không thực hiện metadata signature validation** theo tài liệu; cần tự thiết lập trust policy tương ứng.

```java
// Fragment theo Spring Security SAML2 metadata reference.
// metadataVerificationCredential đến từ trusted admin configuration,
// không lấy từ XML metadata đang cần verify.
OpenSaml5AssertingPartyMetadataRepository repository =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation("https://idp.example.org/metadata")
        .verificationCredentials(
            credentials -> credentials.add(metadataVerificationCredential))
        .build();
```

Đây là fragment mang tính định hướng, cần imports/version/dependencies phù hợp. Nếu metadata signing cert dùng cho federation khác IdP SAML Assertion signing cert, phải quản lý riêng; **không nhầm two trust anchors**.

### 7.3. Vì sao TLS metadata endpoint chưa phải tất cả?

HTTPS xác thực server origin qua Web PKI theo truststore TLS, nhưng một HTTPS endpoint bị quản trị sai hoặc IdP bị compromise vẫn có thể công bố khóa độc hại. Với high-assurance federation, metadata cần thêm signed metadata/trust registry hoặc manual approval, certificate-change alerts, pinning theo agreement và rollback controls.

Không fetch bất kỳ metadata URL nào do SAMLResponse tự cung cấp; như vậy vừa có nguy cơ **SSRF**, vừa làm đối phương chọn signing key của chính họ.

## 8. Certificate rollover: trusted old + new có thời hạn

### 8.1. Rotation hợp lệ

IdP cần đổi signing key từ `K_old` sang `K_new`. SP phải nhận keys qua **authenticated metadata/trust registry** và hỗ trợ overlap có thời hạn:

```text
T0  SP trusts K_old; IdP signs K_old
T1  IdP announces K_new through verified metadata/trust channel
T2  SP trusts [K_old, K_new] for IdP A only
T3  IdP starts signing K_new; SP accepts it
T4  Valid old messages expire, caches drained, tests pass
T5  SP retires K_old and records audit
```

**Không dùng inbound KeyInfo để tự động thêm K_new:** attacker có thể giả làm rollover request. Khi có hai keys trong trust set, vẫn giữ issuer/registration scope và accepted algorithms.

### 8.2. Compromise khác routine rotation

Nếu `K_old` bị lộ, **không giữ overlap kéo dài** chỉ để giảm 401. Cần remove compromised key, revoke affected sessions/messages nếu policy đòi hỏi, phát bản trust config mới qua channel quản trị, hạn chế replay, điều tra và chấp nhận reauthentication/gián đoạn.

Một certificate expired không nhất thiết tương đương compromised; policy SAML pinned cert thường quản lý validity tùy federation, song không bỏ qua critical trust and signature protections một cách im lặng. Quyết định expired certificate acceptance phải rõ ràng, không “auto-trust cert from message để tránh lỗi hết hạn”.

### 8.3. Key ID/KeyInfo hint trong rollover

Thông điệp có thể mang key name/id/certificate để giúp chọn một trong hai trusted keys. Hint chỉ được sử dụng để **lọc ứng viên trong trust set**:

```text
incoming KeyInfo says "new-kid"
      |
      v
Select trusted key IDs registered for IdP A
      |
      +-- If "new-kid" belongs to IdP A set: try verification
      +-- Else: reject or try policy-approved keys
      |
      X-- Never fetch/adopt arbitrary new key by this hint
```

Cùng `kid` text không nhất thiết unique qua issuer/tenant; namespace theo IdP. Nếu verification fails, không fallback sang “whatever key is embedded”.

## 9. JWT/JWS: đúng nguyên tắc với jwk, x5c và jku

JWT có thể là **signed JWS**. JOSE header do người gửi kiểm soát có thể chứa:

```json
{
  "alg": "RS256",
  "kid": "key-2026-11",
  "jwk": {
    "kty": "RSA",
    "n": "UNTRUSTED_BASE64URL_MODULUS",
    "e": "AQAB"
  }
}
```

`jwk` trong header là một public key được **nhúng trong thông điệp**. Nếu app dùng nó làm verification key và chấp nhận JWT, attacker tự ký token có `sub=admin` sẽ pass phép kiểm toán học. Nhiều JWT libraries có defaults tốt; lỗi thường do custom key resolver hoặc dynamic trust logic, không phải tự thân mọi decoder.

### 9.1. Các JOSE header parameters cần thận trọng

| Header | Ý nghĩa | Quy tắc an toàn |
| --- | --- | --- |
| `alg` | Thuật toán được message khai báo | Chỉ cho phép **server-configured acceptable algorithms**, không tin algorithm do attacker yêu cầu |
| `kid` | Key identifier | Chỉ **lookup** trong issuer-specific trusted keyset, input bị giới hạn; không đưa thẳng vào SQL/file path |
| `jwk` | JWK public key được cung cấp trong JOSE header | Không tự xem là authorized key của issuer |
| `x5c` | X.509 certificate chain dưới dạng header | Không coi chain tự đính kèm là trust anchor; validate theo trust policy |
| `jku` | URL tới JWKS | Không fetch tùy ý theo header; SSRF và key substitution |
| `x5u` | URL tới X.509 cert/cert chain | Không fetch tùy ý theo header; SSRF/key substitution |
| `crit` | Critical extensions | Reject những extension không được hiểu/hỗ trợ đúng |
| `typ` | JWT type indicator | Dùng đúng profile, tránh nhầm ID Token, access token, logout token |

RFC 8725 đặc biệt cảnh báo **algorithm confusion** (`alg=none`, RS256↔HS256), header-controlled key selection, issuer/key binding, audience validation và SSRF khi tự follow `jku`/`x5u`.

### 9.2. Phần nào của JWT được tin trước verify?

Header/payload Base64URL có thể **được parse tạm** để lấy `kid` hoặc candidate issuer/alg theo decoder architecture, nhưng **không** cho phép dùng claims làm authenticated identity hoặc mở arbitrary trust source. Chỉ sau signature verified với authorized issuer key, các claim như `iss`, `aud`, `sub`, `exp`, `nbf` mới có thể được đánh giá làm kết quả xác thực.

Đừng sử dụng raw `iss` từ token để gọi `https://{iss}/.well-known/openid-configuration` với mọi host do attacker đưa vào. Nếu multi-issuer, resolver phải chọn từ **allowlist issuer registrations** và tải discovery/JWKS theo trusted config.

### 9.3. Trusted JWKS không giống untrusted jku

Có hai URL trông gần giống nhưng trust khác nhau:

```text
Trusted configuration:
  issuer = https://idp.example.org
  jwks_uri = https://idp.example.org/.well-known/jwks.json
  approved through OIDC discovery / admin trust

Untrusted JWS header:
  jku = https://attacker.example/keys.json
  x5u = http://169.254.169.254/latest/meta-data/...
```

Chỉ server-configured `jwks_uri`/trusted discovery mới được gọi, với HTTPS, SSRF/egress restrictions và cache/rotation controls. `jku`/`x5u` từ token không nên quyết định network fetch. Dù có HTTPS tới attacker host, đó vẫn là attacker-controlled public key.

### 9.4. Chỉ tin key của đúng issuer và token purpose

Nếu system tin IdP A và IdP B, không chấp nhận token claim `iss=A` nhưng ký bởi key hợp lệ của B. RFC 8725 yêu cầu cryptographic keys phải thuộc issuer được xác nhận và `aud` đúng recipient. Đồng thời phân biệt ID Token dành cho OIDC client, access token dành cho API, logout token/SET và service-to-service token theo validation rules riêng.

**Sai:** `Signature.verify() == true` với “bất kỳ key nào trong global truststore” rồi tin mọi `sub`. **Đúng:** verify bằng **trust set của expected issuer/token type** cùng aud/alg/lifetime/nonce hoặc state requirements.

## 10. Spring Security Resource Server: khóa và issuer từ cấu hình đáng tin

### 10.1. YAML config theo issuer/JWKS đã phê duyệt

Ví dụ Spring Boot Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.org"
          jwk-set-uri: "https://idp.example.org/.well-known/jwks.json"
          audiences:
            - "portal-api"
```

`issuer-uri` giúp bind token `iss` đến issuer configured. `jwk-set-uri` do **server config** cung cấp, không lấy từ JWT header. Cấu hình đồng thời hai values có thể cho phép runtime khởi tạo không cần discovery call ngay lúc startup tùy Spring Boot/Security version. `audiences` là Spring Boot JWT resource server property ở những phiên bản hỗ trợ; với version khác phải thêm audience validator tường minh. Dù vậy cần kiểm tra TLS/JWKS source và cấu hình algorithms phù hợp.

### 10.2. Java JwtDecoder fragment: issuer + audience validation

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.core.ClaimAccessor;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.OAuth2Error;

// Fragment: URL issuer được cấp từ trusted server configuration.
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.org";
    NimbusJwtDecoder decoder = (NimbusJwtDecoder)
        JwtDecoders.fromIssuerLocation(issuer);

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = token ->
        token.getAudience().contains("portal-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
    return decoder;
}
```

Đây là **Spring Bean fragment**, không phải file chạy độc lập và không thay full `SecurityFilterChain`. Imports `ClaimAccessor` trong ví dụ có thể bỏ nếu IDE cảnh báo unused. Cần khai báo đúng Spring Security/Boot version và JWK source trust; nếu tự set validator, **đừng vô tình loại các default checks khác**. JWT validation nên gồm issuer, audience, timestamp, signature và allowed algorithm; `JwtDecoders.fromIssuerLocation` gắn discovery với issuer **do server cấu hình**.

### 10.3. Không cấu hình một decoder tùy ý theo token header

Anti-pattern:

```java
// SAI — PSEUDOCODE.
// String jku = parseUntrustedJwtHeader(token).get("jku");
// JwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jku).build();
// return decoder.decode(token);
```

Lỗi là attacker chọn JWKS URL, có thể SSRF tới internal endpoints rồi tự cấp key “hợp lệ”. Thay vào đó issuer/registration phải được server quản lý và **key source có allowlist/trust contract**.

### 10.4. Algorithm allowlist

Spring Security `NimbusJwtDecoder` hỗ trợ các builder methods để chỉ cho phép supported JWS algorithms; ví dụ `.jwsAlgorithm(SignatureAlgorithm.RS256)` tùy version. Không chấp nhận `alg=none` hay tự động đổi sang symmetric HMAC chỉ vì token header bảo vậy. RFC 8725 khuyến nghị mỗi key chỉ được dùng với đúng thuật toán và áp dụng algorithm policy độc lập với attacker input.

**Không sử dụng chữ ký hợp lệ để bỏ qua `aud`:** token ký thật nhưng dành cho application khác phải bị reject.

## 11. TLS và mTLS: chứng thư trong message khác chứng thư của handshake

### 11.1. TLS certificate từ server và header tự gửi

Khi ứng dụng gọi `https://idp.example.org/metadata`, TLS client kiểm chứng server certificate chain và hostname theo truststore. Chứng thư **của kết nối TLS** không đồng nhất với một PEM trong **HTTP response body**.

Tương tự, khi gateway nhận mTLS:

- TLS handshake verify client certificate chain/policy.
- Gateway xác định authenticated client identity.
- Gateway có thể forward identity qua internal authenticated channel tới Spring.
- Spring không được coi header `X-Client-Cert` do client internet tự gửi là bằng chứng mTLS.

Nếu edge giữ `X-Forwarded-Client-Cert`, phải strip untrusted incoming headers, xác thực connection tới backend, giới hạn hop/gateway và cấu hình trust headers theo deployment. Một self-signed certificate gửi trong JSON body không bao giờ trở thành TLS client certificate.

### 11.2. Certificate identity binding

Ngay cả khi PKIX chain valid và cert chưa hết hạn, app còn phải đối chiếu **đúng identity**: hostname cho TLS server; allowed workload/service identity, EKU/KU hoặc SPIFFE ID theo hệ thống mTLS; IdP entityID/key roles cho SAML. Không coi “được public CA cấp” là giấy phép ký assertions cho mọi IdP.

### 11.3. Tránh SSRF ở certificate retrieval

Một signature handler tự follow `ds:RetrievalMethod`, `x5u`, `jku` hoặc `URI` trong XML Reference có thể truy cập metadata endpoint nội bộ, loopback, cloud instance metadata hay URL redirect. Disable external retrieval nếu không cần; nếu cần, áp host/scheme allowlist, DNS/IP/redirect restrictions, TLS validation, egress control, size/time limits, không forward credentials/cookies.

## 12. Không trộn lẫn chứng thư của các giao thức

| Giao thức/tình huống | Nguồn tin cậy chính | Dữ liệu untrusted không tự được tin |
| --- | --- | --- |
| **SAML 2.0 browser SSO** | IdP verification credentials trong registered trust configuration hoặc verified metadata | `ds:KeyInfo`, `ds:X509Certificate`, unverified Issuer |
| **SAML metadata ingestion** | HTTPS trusted location + signed metadata trust anchor khi yêu cầu, operator approval | `KeyDescriptor` trong metadata chưa xác minh |
| **OIDC ID Token** | Issuer-configured discovery/JWKS, client_id/nonce rules | `jwk`, `x5c`, `jku`, `x5u` trong untrusted JWT |
| **OAuth2 API access token** | Trusted AS/issuer JWKS và API audience/token profile | Token header key/issuer do attacker lựa chọn |
| **mTLS service authentication** | Validated TLS peer certificate chain/identity, trusted ingress path | PEM/HTTP `X-Client-Cert` không được gateway bảo vệ |
| **Signed webhook** | Public key/HMAC secret pinned by webhook provider và payload context | Webhook key URL/header do request tự đặt |
| **CAS native back-channel logout** | CAS trusted endpoint/network/message verification theo CAS client deployment | `logoutRequest` XML chứa SAML namespace không tự có SAML signature trust |

**Các flow không thể thay thế lẫn nhau:** một SAML `KeyInfo` public key không phải OIDC JWKS registration. CAS logout XML namespace giống SAML2 không tự biến nó thành signed SAML2 SLO profile. Spring Security phải dùng protocol handler/validator đúng trường hợp.

## 13. Java 17 độc lập: chữ ký hợp lệ với khóa tự cung cấp vẫn bị từ chối

Ví dụ tạo ba RSA keypairs: IdP cũ (`trustedOld`), IdP mới được quản trị viên approve (`trustedNew`) và attacker (`attacker`). Mỗi người có thể ký một envelope với key riêng. Envelope chứa `advertisedPublicKey` — **mô hình đơn giản hóa cho public key từ X.509 `KeyInfo` hoặc JWT `jwk`**. Chương trình cố tình không tạo certificate X.509 vì JDK 17 thuần không có public API tiện dụng để tự cấp X.509 cert; vấn đề trust là tương tự.

Chương trình mô tả hai kiểu verifier:

- **Naive:** lấy key từ chính envelope rồi verify. Attacker ký giả và điền key của mình → trả `true`.
- **Hardened:** bỏ qua embedded key làm nguồn trust; chỉ verify với **public keys do trusted admin đăng ký cho expected issuer**, đồng thời kiểm tra issuer, audience và expiry. Attacker → `false`.

**Giới hạn bảo mật:** đây không phải SAML XMLDSig, JWS/JWT, PKIX, JGSS hoặc Spring Security; chỉ dùng JCA RSA signatures để làm rõ mối liên hệ giữa toán học chữ ký và trust. Chuỗi `canonical` trong demo không phải chuẩn canonicalization XML hoặc JWT signing input. Không dùng trực tiếp `Envelope`/`trustedVerify` này cho production authentication.

Lưu file `UntrustedCertificateDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Instant;
import java.util.List;

public class UntrustedCertificateDemo {

    record Envelope(
            String issuer,
            String audience,
            String subject,
            Instant expiresAt,
            PublicKey advertisedPublicKey,
            byte[] signature) {}

    static byte[] signedBytes(Envelope e) {
        String canonical = e.issuer() + "\n"
                + e.audience() + "\n"
                + e.subject() + "\n"
                + e.expiresAt().toString();
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    static KeyPair rsaKeyPair() throws GeneralSecurityException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static Envelope issue(
            KeyPair signer, String issuer, String audience,
            String subject, Instant expiresAt)
            throws GeneralSecurityException {

        Envelope unsigned = new Envelope(
                issuer, audience, subject, expiresAt,
                signer.getPublic(), new byte[0]);
        Signature signing = Signature.getInstance("SHA256withRSA");
        signing.initSign(signer.getPrivate());
        signing.update(signedBytes(unsigned));

        return new Envelope(issuer, audience, subject, expiresAt,
                signer.getPublic(), signing.sign());
    }

    static boolean verifyWith(Envelope message, PublicKey publicKey)
            throws GeneralSecurityException {
        Signature check = Signature.getInstance("SHA256withRSA");
        check.initVerify(publicKey);
        check.update(signedBytes(message));
        return check.verify(message.signature());
    }

    // SAI trong production: public key do message cung cấp.
    static boolean naiveVerify(Envelope message)
            throws GeneralSecurityException {
        return verifyWith(
                message, message.advertisedPublicKey());
    }

    // ĐÚNG về nguyên tắc trust: chỉ keys đã được cấu hình
    // cho issuer mong đợi, kiểm thêm context; không tự trust
    // advertisedPublicKey. Đây vẫn chỉ là demo.
    static boolean trustedVerify(
            Envelope message,
            String expectedIssuer,
            String expectedAudience,
            Instant now,
            List<PublicKey> authorizedKeys)
            throws GeneralSecurityException {

        if (!expectedIssuer.equals(message.issuer())
                || !expectedAudience.equals(message.audience())
                || !now.isBefore(message.expiresAt())) {
            return false;
        }

        for (PublicKey pinned : authorizedKeys) {
            if (verifyWith(message, pinned)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        KeyPair trustedOld = rsaKeyPair();
        KeyPair trustedNew = rsaKeyPair();
        KeyPair attacker = rsaKeyPair();

        String idp = "https://idp.example.org";
        String audience = "portal-sp";
        Instant now = Instant.parse("2026-11-07T00:00:00Z");
        Instant future = Instant.parse("2027-01-01T00:00:00Z");
        Instant past = Instant.parse("2026-01-01T00:00:00Z");

        Envelope valid = issue(
                trustedOld, idp, audience, "alice", future);
        Envelope forged = issue(
                attacker, idp, audience, "admin", future);
        Envelope wrongAudience = issue(
                trustedOld, idp, "another-sp", "alice", future);
        Envelope expired = issue(
                trustedOld, idp, audience, "alice", past);

        Envelope tampered = new Envelope(
                valid.issuer(), valid.audience(), "admin",
                valid.expiresAt(), valid.advertisedPublicKey(),
                valid.signature());

        List<PublicKey> originalTrust =
                List.of(trustedOld.getPublic());

        System.out.println("Trusted message with embedded key: "
                + naiveVerify(valid));
        System.out.println("Attacker self-signed message accepted naively: "
                + naiveVerify(forged));
        System.out.println("Trusted message under pinned key: "
                + trustedVerify(
                    valid, idp, audience, now, originalTrust));
        System.out.println("Attacker under pinned key rejected: "
                + !trustedVerify(
                    forged, idp, audience, now, originalTrust));
        System.out.println("Wrong audience rejected: "
                + !trustedVerify(
                    wrongAudience, idp, audience, now, originalTrust));
        System.out.println("Expired signed message rejected: "
                + !trustedVerify(
                    expired, idp, audience, now, originalTrust));
        System.out.println("Tampered subject rejected: "
                + !trustedVerify(
                    tampered, idp, audience, now, originalTrust));

        Envelope rotated = issue(
                trustedNew, idp, audience, "alice", future);
        List<PublicKey> rolloverTrust = List.of(
                trustedOld.getPublic(), trustedNew.getPublic());

        System.out.println("New authorized key during rollover: "
                + trustedVerify(
                    rotated, idp, audience, now, rolloverTrust));
        System.out.println("Old key after retirement rejected: "
                + !trustedVerify(
                    valid, idp, audience, now,
                    List.of(trustedNew.getPublic())));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac UntrustedCertificateDemo.java
java UntrustedCertificateDemo
```

Stdout **chính xác** (mỗi lần RSA keypair khác nhau nhưng kết quả boolean giống nhau):

```text
Trusted message with embedded key: true
Attacker self-signed message accepted naively: true
Trusted message under pinned key: true
Attacker under pinned key rejected: true
Wrong audience rejected: true
Expired signed message rejected: true
Tampered subject rejected: true
New authorized key during rollover: true
Old key after retirement rejected: true
```

### 13.1. Giải thích từng dòng

- `Trusted message with embedded key: true`: chữ ký do key cũ tạo hợp với public key đính kèm, nhưng **đó không phải phép kiểm trust**.
- `Attacker self-signed message accepted naively: true`: cùng một phép kiểm cũng cho attacker pass. Đây là bằng chứng trực tiếp rằng math signature success không xác thực issuer.
- `Trusted message under pinned key: true`: key trong trusted config đúng với signer IdP.
- `Attacker under pinned key rejected: true`: private key attacker không tương ứng pinned public key nên không verify.
- `Wrong audience rejected: true`: một message do IdP thật ký nhưng dành cho RP khác vẫn không hợp lệ ở Portal.
- `Expired signed message rejected: true`: chữ ký đúng không bỏ qua thời hạn.
- `Tampered subject rejected: true`: chữ ký trên `alice` không thể giữ nguyên khi đổi thành `admin`.
- `New authorized key during rollover: true`: chỉ khi new key được admin thêm vào trust set, IdP có thể ký bằng key mới.
- `Old key after retirement rejected: true`: sau khi bỏ key cũ, signature old không còn được accept.

### 13.2. Giới hạn bổ sung

- Đính kèm `PublicKey` chỉ mô phỏng certificate `KeyInfo`: X.509 thật có chain, extensions, validity, revocation và identity policy.
- `trustedVerify` kiểm issuer/audience/expiry đơn giản, không có SAML `InResponseTo`, `Recipient`, `NotBefore`, SubjectConfirmation, replay store hay browser flow.
- Không có JWT JOSE header/alg/kid, XMLDSig canonicalization/reference URI, metadata onboarding hay issuer token-type isolation.
- `authorizedKeys` là tập pinned trong test; production phải lấy từ **server-side trusted storage** và namespace per issuer/tenant.
- `SHA256withRSA` là thuật toán JCA đơn giản, không đại diện mọi XML Signature/JWS profiles.
- Không có PKIX chain validation hoặc remote certificate fetch.
- Không xuất private key hoặc tự lưu secrets lâu dài trong demo; production cần key lifecycle, KMS/HSM/secret store.
- Key rotation phải được phê duyệt và xác thực out-of-band; không lấy `advertisedPublicKey` để tạo `authorizedKeys`.

## 14. Vì sao “chứng thư hợp lệ” vẫn chưa đủ?

### 14.1. Self-signed certificate: tự chứng minh với chính mình

Một attacker có thể tạo cert còn hạn, đặt CN/Organization giống IdP, tự ký cert. Các phép kiểm `checkValidity()` và self-signature verification có thể pass, nhưng không có **trust anchor đã phê duyệt**. Nếu IdP thực sự dùng cert tự ký, SP chỉ chấp nhận khi **cert/key được pin qua onboarding**.

### 14.2. Public CA certificate không chứng minh quyền ký SAML

Một người có thể mua/nhận TLS cert cho một domain họ sở hữu; public CA chain của cert đó có thể valid. Nhưng nó không phải signing certificate được RP phê duyệt cho `https://idp.example.org/saml`. Authentication cần **issuer-key binding**, không phải “được một CA bất kỳ ký”.

### 14.3. X.509 Key Usage và Extended Key Usage

Tùy profile, phải kiểm tra certificate `KeyUsage`/`ExtendedKeyUsage`, key algorithms, validity và phù hợp với mục đích (TLS server, TLS client, SAML signing, encryption). SAML federation có thể dùng self-signed keys mà PKIX-style EKU không phải bắt buộc, nên lựa chọn kiểm tra theo **contract đã chấp nhận**, không bỏ mọi checks hay áp một public-webPKI policy sai ngữ cảnh.

### 14.4. Signature valid nhưng claims authorization vẫn sai

Một IdP có thể phát `role=ADMIN` cho user nhưng RP có policy không cho phép IdP tự quyết quyền admin. Sau khi tin cậy signer/issuer, còn phải map claims sang **local roles** theo allowlist, tenant và resource scope. Signature không biến mọi dữ liệu claim thành chính sách truy cập.

## 15. Attack tree: dấu hiệu và điểm chặn

| Tấn công | Cách kẻ tấn công lợi dụng | Phòng vệ |
| --- | --- | --- |
| **Embedded certificate substitution** | Tự ký Assertion, chèn own X509Certificate | Verify bằng IdP pinned verification credentials |
| **JWKS header substitution** | JWS chứa `jwk` của attacker | Không auto trust header JWK |
| **SSRF jku/x5u** | Header trỏ metadata/internal URL | Chỉ trusted issuer JWKS URI, egress restrictions |
| **Algorithm confusion** | `alg=none` hoặc RS256→HS256 | Server-configured algorithm allowlist/key-type binding |
| **Issuer/key confusion** | Ký bằng IdP B nhưng claim IdP A | Trust keys scoped to trusted issuer/tenant |
| **Cross-audience token** | Real IdP token dành cho RP khác | Verify `aud`, `azp`/client binding theo profile |
| **XML Signature Wrapping** | Signature trên benign Assertion nhưng app đọc forged node | Bind consumed assertion to verified signed element/ID |
| **Untrusted metadata adoption** | Metadata tự gửi chứa attacker key | Trust onboarding, signed metadata verification khi cần |
| **Key rollover hijack** | Chèn new cert vào inbound KeyInfo | Approved metadata/trust-store change only |
| **Expired/revoked cert bypass** | Thấy cert invalid, fallback embedded key | Fail closed, incident/rotation procedure |
| **mTLS header spoofing** | Client tự gửi `X-Client-Cert` | mTLS handshake verified gateway, strip incoming headers |
| **External XML Reference** | URI/KeyInfo RetrievalMethod trỏ internal service | Disable external resolver, strict URI/transforms |
| **Replay valid signed assertion** | Gửi lại assertion cũ còn key valid | InResponseTo/Recipient/time/replay cache checks |
| **Weak/legacy signature** | RSA-SHA1/MD5 or insecure key size | Approved algorithms & minimum key strength |
| **Tenant mix-up** | B dùng key của A do global trust set | Namespace per tenant/entityID/issuer |
| **Unknown kid auto-fetch** | “Không thấy kid” → fetch key from message URL | Reject until trusted JWKS refresh approved |
| **Truststore poisoning** | Admin endpoint nhận file cert từ user | Authenticated config management, review/audit |

## 16. Quy trình xử lý SAML Response an toàn

### 16.1. Sequence làm việc

```text
1. Browser POST SAMLResponse (tainted/untrusted).
2. Spring resolves RelyingPartyRegistration:
   request-associated state / approved registration / safe issuer candidate.
3. Pull trusted verifying credentials for expected IdP.
4. XML parser hardened: DTD/XXE/size/IDs/transforms constrained.
5. Verify signature over proper Response/Assertion element.
6. Confirm verifier key belongs to expected IdP.
7. Validate Issuer, Destination, InResponseTo,
   AudienceRestriction, Recipient, SubjectConfirmationData,
   clock validity, replay, status.
8. Read NameID/attributes from precisely verified Assertion.
9. Map identity to permitted local principal and authorities.
10. Create SecurityContext/session and audit success without raw XML.
```

**Không bỏ bước 6:** “Signature.verify() true” chỉ có ý nghĩa khi verify với authorized key. **Không bỏ bước 8:** nếu parser đọc một AttributeStatement ngoài signed subtree, có thể bị XSW.

### 16.2. Những kiểm tra cần cẩn thận

- **Issuer:** trùng expected entityID, không chỉ same hostname hay same organization name.
- **Audience:** assertion dành cho RP entityID hiện tại.
- **Recipient:** bearer subject confirmation chỉ định ACS hợp lệ.
- **Destination:** Response đến đúng endpoint, xử lý proxy forwarded headers đáng tin.
- **InResponseTo:** match AuthnRequest pending, có thể có IdP-initiated profile đã được phê duyệt; không bỏ check tùy tiện.
- **Lifetime:** Conditions và SubjectConfirmationData NotOnOrAfter/NotBefore với clock skew hợp lý.
- **Replay:** message/assertion IDs phải không được accept nhiều lần.
- **Signature coverage:** Response hoặc Assertion signatures phải đáp ứng profile; tiêu chí verify cụ thể do framework/version/IdP contract quyết định.
- **Decryption:** private key SP dùng decrypt khác trusted signing key IdP.
- **Multi-tenant:** chỉ một verified registration context được dùng cho cả auth và authorization.

### 16.3. Không tự viết custom DOM parser làm đường login

Một shortcut như:

```java
// ANTI-PATTERN — PHẦN MÃ MINH HỌA.
// Node node = doc.getElementsByTagName("NameID").item(0);
// String principal = node.getTextContent();
// if (isSignatureValidSomewhere(doc)) authenticate(principal);
```

dễ nhầm verified node với unverified node. Dùng Spring Security/OpenSAML provider được bảo trì, customization có mục đích rõ, tests XSW và schema validation. Không nhận signed metadata key dựa trên tên file gửi lên.

## 17. JWT verification: validation profile riêng theo token type

### 17.1. Access token không phải ID token

Một API Resource Server thường cần verify:

- Trust issuer và nguồn JWKS theo configuration.
- Signature với authorized key/allowed alg.
- `iss` chính xác, `aud` chứa API resource identifier.
- `exp`/`nbf`/`iat` khi profile yêu cầu.
- Scopes/roles theo issuer và audience, tránh `ROLE_ADMIN` từ client tự khai.
- `typ` hoặc token classification nếu có thể nhầm loại tokens.
- Replay/jti/revocation theo yêu cầu ứng dụng.

Một OIDC client xử lý ID Token còn cần `client_id` audience, `nonce` khi có, `azp` tùy trường hợp, và checks OIDC Core. Không dùng Resource Server access-token validator làm ID Token verification chung.

### 17.2. Multi-issuer JWT strategy

Một Resource Server có thể chấp nhận nhiều issuers đã duyệt. Nhưng **đừng**:

```text
unverified token.iss -> network discovery on arbitrary URL
-> auto-add all keys -> verify -> trust
```

Thay bằng:

```text
trustedIssuers:
  https://idp-a.example.org -> JWKS URL A, allowed audience A, key policies
  https://idp-b.example.org -> JWKS URL B, allowed audience B, key policies

unverified iss only selects existing entry (or REJECT)
decoder bound to that entry verifies token
audience, type, tenant, expiry validated separately
```

Trong Spring Security có issuer-based resolver như `JwtIssuerAuthenticationManagerResolver` với trusted issuer allowlist/manager repository tùy version. Chỉ đưa issuers đã onboarding vào resolver; callback không được đăng ký issuer mới vì một token tự khai.

### 17.3. JWKS refresh khi gặp kid mới

Một `kid` không tồn tại trong cached trusted JWKS có thể do **hợp pháp IdP key rotation**, nhưng không có nghĩa token được phép kéo một `jku` mới. Safe process:

1. Refresh **trusted issuer's configured JWKS endpoint** theo cache/refresh policy.
2. Giới hạn rate, timeout, response size, HTTPS/redirect/egress.
3. Verify key parameters và allowed algorithms.
4. Retain old/new authorized issuer keys trong bounded rollover.
5. Reject nếu `kid` vẫn không tồn tại hoặc signature fail.
6. Audit key lifecycle thay đổi; alert unexpected key churn.

Nếu JWKS endpoint bị compromise, cần incident/issuer key revocation; chỉ vì HTTPS từng thành công không chứng minh mọi khóa mới nên được phát hành không cần giám sát.

## 18. Checklist tạo trust source, không để attacker định nghĩa

### 18.1. Identity metadata/issuer onboarding

- [ ] Mỗi IdP/OP có owner, issuer/entityID và trusted metadata/JWKS source.
- [ ] Metadata URL/JWKS được cấp bằng admin configuration, không từ SAML Response/JWT `jku`.
- [ ] HTTPS TLS với trusted host/truststore; nếu cần signed metadata có độc lập trust anchor.
- [ ] X.509 certificate/key use được xác định rõ: signing vs encryption vs TLS.
- [ ] Multiple tenants không chia global “any cert” trust set.
- [ ] Chứng thư self-signed chỉ được chấp nhận nếu **đã pin bằng channel đáng tin**.
- [ ] PKIX chain validation khi phù hợp sử dụng trusted roots, identity binding/KU/EKU/revocation policy.
- [ ] Key change được versioned, approved, logged và có overlap/rollback plan.

### 18.2. Signature processing

- [ ] SAML XML hardened parser/DTD/XXE/size/transforms/unique ID.
- [ ] Verify đúng signed element với trusted IdP credentials, không lấy key chưa tin từ KeyInfo.
- [ ] Không dùng global DOM NameID/attributes ngoài verified Assertion.
- [ ] Verify Issuer, audience, ACS recipient/destination, time, InResponseTo và replay.
- [ ] JWT accepted algorithms server-configured, không `alg=none` hoặc algorithm confusion.
- [ ] JWT keys scoped per issuer; kid chỉ lookup, jku/x5u không tự fetch.
- [ ] Token type/issuer/audience/tenant/expiry validation đầy đủ.
- [ ] mTLS identity chỉ lấy từ TLS handshake/gateway đáng tin, không tự tin X-Client-Cert.
- [ ] Failed verification **reject**; không fallback “unsigned” hoặc embedded cert.

### 18.3. Vận hành

- [ ] Logs không chứa full SAMLResponse/JWT/KeyInfo, session tokens hoặc private keys.
- [ ] Alert khi invalid signature, unknown trusted key, unexpected kid, metadata updates, XSW attempts.
- [ ] Định nghĩa test fixtures với trusted IdP, attacker-generated self-signed key và retired key.
- [ ] Metadata/JWKS cache được quan sát, có timeout/rate limits và process rollover.
- [ ] Compromised signing key được remove theo incident response, không kéo dài grace.
- [ ] Cấu hình Spring Security/OpenSAML/Nimbus cập nhật và regression tests chạy mỗi release.

## 19. Ma trận kiểm thử âm tính

| Test case | Hành vi phải có |
| --- | --- |
| Attacker tự ký Assertion, chèn X509Certificate vào KeyInfo | **REJECT**, dù signature verify bằng embedded key |
| Message ký đúng trusted IdP key nhưng `Issuer` khác | **REJECT** |
| IdP B ký message claim issuer IdP A | **REJECT**, không tin global set |
| Message `aud` dành cho app khác | **REJECT** |
| Assertion expired nhưng signature valid | **REJECT** |
| Duplicate Assertion ID/replay valid signed response | **REJECT** |
| XML có hai Assertion, chỉ một cái signed, app đọc cái còn lại | **REJECT** và kiểm tra XSW |
| XML Reference URI trỏ đến untrusted remote resource | **REJECT** hoặc deny remote resolution |
| X509Certificate tự ký Subject CN “Trusted IdP” | **REJECT** nếu chưa pin |
| Cert chain valid tới public CA nhưng không được IdP A ủy quyền | **REJECT** |
| Metadata unsigned do attacker thay KeyDescriptor | Không tự adopt; **REJECT** khi policy yêu cầu signed metadata |
| Metadata signed bằng key nằm trong chính metadata chưa trusted | **REJECT** bootstrap tự xác nhận |
| IdP hợp pháp chuyển signing key qua verified channel | **ACCEPT** đúng tập old/new trong rollover |
| Key mới chỉ có trong inbound KeyInfo, chưa được approve | **REJECT** |
| Retired key ký Assertion mới | **REJECT** |
| Compromised old key còn trong truststore | Security incident, remove, revoke sessions/replay nếu cần |
| JWT header chứa `jwk` của attacker, payload admin | **REJECT** bằng issuer-configured JWKS |
| JWT header `jku` trỏ localhost/cloud metadata endpoint | Không fetch, **REJECT** |
| JWT `alg=none` | **REJECT** |
| JWT RS256↔HS256 confusion | **REJECT** |
| JWT `kid` cố traversal/SQL injection | Reject/sanitize; không file/key lookup tùy ý |
| JWT signed bởi key B nhưng `iss=A` | **REJECT** |
| JWT real signature nhưng wrong audience | **REJECT** |
| ID Token dùng như API access token | **REJECT** theo token profile |
| Proxy gửi `X-Client-Cert` do browser tự nhập | **REJECT** nếu không có verified gateway |
| Valid mTLS chain nhưng unexpected client identity | **REJECT** |
| Chỉ `checkValidity()` trên untrusted cert rồi cho login | Security QA **FAIL** |
| SAML encryption certificate bị nhầm làm signer key | Security QA **FAIL** nếu sai role |
| Spring tests chỉ verify signature mà không verify auth/session identity | QA incomplete; bổ sung end-to-end checks |
| Java17 demo output khác phần 13 | Content QA FAIL |

### 19.1. E2E test cho Spring Security SAML2

1. Cấu hình trusted IdP A certificate trong `RelyingPartyRegistration` từ channel admin.
2. Login qua A và xác minh signed Response/Assertion, context + local session.
3. Trong lab, tạo attacker keypair/cert, ký Assertion giả cùng `Issuer`/ACS/audience A.
4. Chèn attacker cert vào `KeyInfo`; **SP phải reject**, không tạo `Authentication`.
5. Thử signature-wrapping fixture với benign signed node và malicious unsigned node; không cho admin login.
6. Thử signed wrong audience/expired/replay/InResponseTo mismatch và IdP B issuer/key swap.
7. Rotate IdP key qua approved metadata, test old/new overlap, rồi retire old.
8. Kiểm tra logs không in raw `SAMLResponse` hoặc certificates riêng tư.
9. Lặp lại trên nhiều registrations/tenants và pods để phát hiện global trust mix-up.

### 19.2. E2E test cho JWT Resource Server

1. Config issuer và trusted JWKS URL phía server; API audience theo profile.
2. Nhận access token thật từ issuer, verify và cấp minimum scopes.
3. Tạo JWT test signed bằng attacker key, header `jwk/x5c` của attacker; reject.
4. Thêm `jku` URL tới test server/loopback; xác nhận Resource Server **không fetch** URL do header chỉ định.
5. Test `kid` lạ: chỉ refresh trusted JWKS; nếu không có key, reject.
6. Test issuer B token substituted sang API A, wrong audience, expired, alg=none.
7. Test authorized key rollover từ trusted JWKS với cache timing/old+new.
8. Quan sát unauthenticated result 401 và SecurityContext không có principal.
9. Đảm bảo auth errors không tiết lộ raw JWT/header/PII trong logs/response.

## 20. Troubleshooting và vận hành

| Triệu chứng | Có thể là gì? | Kiểm tra |
| --- | --- | --- |
| SAML invalid signature sau IdP cert rollover | SP chưa nhận trusted new cert | Metadata trust update, trusted cert versions |
| “Signature valid” nhưng app login sai user | XSW hoặc đọc unsigned claims | Signed element binding, XML IDs, OpenSAML pipeline |
| SAML có KeyInfo cert khác trusted metadata | Đúng khi attacker giả mạo hoặc IdP rotation chưa phối hợp | **Không auto-trust**; xác minh admin trust channel |
| Metadata ký hợp nhưng attacker phát | Verifier dùng cert embedded metadata | Independent metadata verification trust anchor |
| SAML wrong issuer/audience sau đa tenant | RP registration mix-up | Namespace keys per IdP/RP/tenant |
| JWT unknown kid sau legitimate rotation | Trusted JWKS cache stale | Refresh **configured JWKS**, không header jku |
| JWT with x5c tự ký pass custom code | Decoder dùng untrusted key in token | Replace custom resolver, use trusted JWKS |
| JWT with valid signature returns 401 | Wrong aud/iss/exp/type hoặc authorization | Check validators, không nới trust |
| JWT jku gây internal network requests | SSRF qua resolver | Disable header-controlled URL fetch |
| mTLS auth chấp nhận giả header | Proxy không strip incoming headers | TLS gateway identity and trusted headers config |
| Signing cert hết hạn | Pinning/PKIX policy và rotation lỗi | Approved replacement; không bypass expiry tùy tiện |
| SAML new key in metadata nhưng runtime cũ | Cache/refresh/rollout | Observe metadata cache policy, atomic config update |
| Từ chối SAML cert self-signed hợp lệ | Áp nhầm public CA PKIX với pinned SAML trust | Cấu hình đúng federation trust model |
| Chấp nhận bất kỳ cert browser CA | Thiếu IdP-key binding | Pin/metadata verify expected IdP |
| SAML encrypted assertion không giải mã được | SP private decryption credential sai | Decryption key, không phải IdP verification key |
| SAML signature valid nhưng role sai | Business authorization mapping sai | Local policy/tenant, không tin raw role |

### 20.1. Log đủ để điều tra nhưng không lộ dữ liệu

```json
{
  "event": "federation_signature_rejected",
  "protocol": "saml2",
  "registration": "corporate",
  "reason": "key_not_in_approved_trust_set",
  "candidate_key_id": "opaque-approved-or-untrusted-hint",
  "message_type": "SAMLResponse",
  "result": "rejected",
  "correlation_id": "request-internal-id"
}
```

Đây là event **minh họa**; không dùng raw cert/public key/trust anchor, message XML, NameID, JWT, session ID hoặc passwords làm metric labels/log entries. Key fingerprints nếu phải log cho vận hành chỉ dùng **approved, non-sensitive representation** và hạn chế correlation/PII theo policy; đừng in private keys.

### 20.2. Phản ứng với suspicious key substitution

Nếu nhiều messages đột nhiên mang unrecognized certificate/key:

- Giữ **fail closed**, không cập nhật truststore tự động.
- Xác minh IdP operations có thông báo rollover từ channel đã đăng ký không.
- So trusted metadata/JWKS change events, network/egress logs, tenant routing.
- Theo dõi login failures, unexpected `jku/x5u` and SSRF attempts, XSW parsing exceptions.
- Nếu ký khóa IdP thật đã compromise: thu hồi ký, revoke affected sessions/tokens khi có yêu cầu, audit, reissue qua trusted channel.
- Phân biệt availability incident với attacker forging; không “quick fix” bằng cách tin mọi embedded certificates.

## 21. Câu hỏi ôn tập

**1. Vì sao verify chữ ký bằng public key đính kèm chưa đủ để xác thực IdP?**  
Vì attacker cũng có thể tạo private/public keypair, ký message giả và đính kèm đúng public key của mình. Chữ ký sẽ hợp với key đó.

**2. Nên lấy IdP SAML signing key từ đâu?**  
Từ trusted RelyingPartyRegistration/metadata đã được onboarding và verify qua kênh độc lập; không phải inbound `KeyInfo` tự quyết định.

**3. X.509 certificate còn hạn có đồng nghĩa được tổ chức tin?**  
Không. `checkValidity` chỉ xét ngày; phải có trust anchor/issuer-role binding phù hợp.

**4. Self-signed SAML certificate có luôn bị cấm?**  
Không. Có thể hợp lệ khi pin/trust qua verified IdP metadata/admin channel. Vấn đề là nó **không tự tin cậy chỉ vì nằm trong message**.

**5. Một public CA cert có cho phép ký Assertion cho mọi IdP?**  
Không. Phải bind key/cert đến đúng IdP entityID và ký message đúng role/protocol.

**6. KeyInfo có công dụng gì khi không tự trusted?**  
Nó có thể chỉ ra key name/cert ứng viên giúp chọn một trong các trusted verification credentials đã đăng ký, hoặc có thể bỏ qua.

**7. XSW có thể xảy ra ngay cả khi signature dùng trusted key?**  
Có. Nếu app lấy attributes/NameID từ **nút XML khác** với signed/verified assertion.

**8. Vì sao không dùng `jku` của JWT để tải JWKS?**  
Attacker có thể chỉ định server của mình hoặc internal metadata endpoint, gây key substitution/SSRF.

**9. `kid` của JWT có đáng tin không?**  
Nó là untrusted selector; chỉ được lookup trong trusted issuer keyset, không được tạo key/issuer mới.

**10. JWT ký hợp lệ bởi IdP B nhưng claim `iss=A` có được accept không?**  
Không. Keys phải thuộc issuer expected và token audience/type phải match.

**11. Thêm certificate mới vào KeyInfo có nghĩa đã rotate thành công?**  
Không. Chỉ keys đã được admin/verified metadata đưa vào trust config mới được phép verify.

**12. Chứng thư mTLS trong HTTP header có thể tin không?**  
Chỉ khi header được truyền từ gateway đã xác thực TLS client, strip incoming spoofed headers và backend link trusted; không tin browser header.

**13. Signed SAML Response mà audience sai thì sao?**  
Reject. Một chữ ký đúng không có nghĩa response dành cho SP hiện tại.

**14. Có nên bỏ signature/PKIX validation khi certificate hết hạn để tránh outage?**  
Không. Điều tra trust model, phối hợp replacement theo channel approved và xử lý incident, không fail-open.

**15. SAML metadata có KeyDescriptor thì có được auto-import key từ mọi URL không?**  
Không. Metadata source phải trusted; metadata signatures nếu yêu cầu phải verify với anchor độc lập.

**16. Điều gì khác nhau giữa signer key của IdP và SP decryption key?**  
IdP signing public key dùng verify issuer SAML messages; SP private decryption key dùng giải mã encrypted assertions. Không trao đổi vai trò.

**17. Vì sao Spring Security OIDC Resource Server vẫn cần issuer và audience validator?**  
Vì signature chỉ chứng minh authorized signer; token có thể dành cho app khác, hết hạn, hoặc thuộc token type khác.

**18. Khi nhận unknown kid, nên làm gì?**  
Refresh issuer-specific configured trusted JWKS theo policy; nếu không tìm thấy authorized key hoặc signature sai thì reject, không fetch từ token-controlled URL.

## 22. Tài liệu chuẩn và nguồn chính thức

- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): khóa verify từ local trusted source, bỏ qua untrusted KeyInfo, chống XML Signature Wrapping, validation protocol.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, `assertingPartyMetadata.verificationX509Credentials`, SAML Response/Assertion signature validators.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `OpenSaml5AssertingPartyMetadataRepository.verificationCredentials`, cảnh báo không tự verify metadata signatures khi thiếu verification credentials.
- [W3C XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/): `SignedInfo`, `Reference`, `SignatureValue`, `KeyInfo` và key discovery không thay trust policy.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, issuer-key binding, audience, `jku`/`x5u` SSRF, token confusion.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JOSE header params `alg`, `kid`, `jwk`, `x5c`, `jku`, `x5u`.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): trusted JWK Set representation, key parameters.
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer/metadata location và trust binding.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `issuer-uri`, `jwk-set-uri`, `JwtDecoders.fromIssuerLocation`, algorithms và claim validators.
- [NIST SP 800-63C-4 — Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): federation trust agreements, assertions, keys and authentication assurance.
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): hardened XML parsing.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): URL-fetch allowlists và chống internal network access.
- [OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS trust anchor và mTLS deployment considerations.

**Ghi nhớ:** `X509Certificate`, `KeyInfo`, `jwk` hay `x5c` ở **thông điệp chưa được xác minh** chỉ là dữ liệu untrusted, không phải chứng thư gốc được RP/Resource Server tự động tin cậy. Chữ ký hợp với **khóa do chính attacker mang tới** vẫn có thể toán học đúng. Phải lấy authorized verification keys từ **trusted issuer registration/verified metadata/JWKS/configuration**, verify đúng signed bytes/element với key đó, rồi kiểm **issuer–audience–recipient–time–replay–tenant–token type–authorization**. Đối với rotation, chỉ thêm keys qua change process xác thực; nếu verification thất bại, **reject**, không fallback sang embedded certificate.