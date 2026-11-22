# Bổ sung chữ ký AuthnRequest, assertion mã hóa và xác minh đúng bên tiếp nhận

**Khi hoàn thiện tích hợp SAML2 SSO trong Spring Security, “đăng nhập được” chưa đủ.** Ứng dụng Service Provider (SP/Relying Party) cần gửi `AuthnRequest` được ký khi đối tác IdP yêu cầu, nhận `EncryptedAssertion` mà chỉ SP có private key phù hợp mới giải mã được, rồi kiểm tra chặt **Response Destination**, **SubjectConfirmationData Recipient**, **AudienceRestriction**, **InResponseTo**, issuer, chữ ký, thời hạn và chống phát lại. Nếu một trong các ràng buộc sai, **không được tạo Authentication**, kể cả khi assertion giải mã thành công hoặc chữ ký từ một IdP khác vẫn hợp lệ.

Bài thuộc **Spring Security – federation → Thực hành tổng hợp**. Nội dung xây dựng một kịch bản với hai bên giả lập: IdP `urn:corp:idp` và SP `urn:portal:sp:corp` ở `https://portal.example.test`. Các ví dụ mô tả Spring Boot/Spring Security SAML2 Service Provider dựa trên OpenSAML, mẫu YAML, định dạng SAML, kiểm thử âm tính, vòng đời khóa, vận hành và chương trình Java 17 độc lập minh họa chữ ký, mã hóa AEAD và các điều kiện tiếp nhận.

**Ba ranh giới không thể đánh đồng:**

1. **SP ký AuthnRequest** bằng *SP private signing key* để IdP xác minh request thực sự đến từ SP đã đăng ký. Đây không phải chữ ký trên SAML Response.
2. **IdP mã hóa Assertion** bằng *SP public encryption certificate*; SP dùng *SP private decryption key* mở nội dung. Mã hóa bảo vệ bí mật, **không tự chứng minh IdP đáng tin**.
3. **SP xác minh nội dung sau khi giải mã và chữ ký đúng IdP**, gồm `Destination`, `Recipient` và `AudienceRestriction` trỏ đúng bên tiếp nhận, cùng request correlation và replay protection.

Tất cả tên miền, khóa, user và chứng chỉ bên dưới là **dữ liệu lab**. Không ghi private keys, SAMLResponse, session cookies hoặc user attributes thật vào tài liệu/chats/logs.

## 1. Mục tiêu thực hành

Sau khi hoàn thành, kỹ sư có thể:

- Giải thích bên nào **ký**, bên nào **xác minh**, bên nào **mã hóa** và bên nào **giải mã** trong Web Browser SSO.
- Cấu hình riêng `signing.credentials`, `decryption.credentials` và `assertingparty.verification.credentials` cho Spring Boot SAML2.
- Phát và kiểm tra `AuthnRequest` signed với HTTP-Redirect hoặc HTTP-POST binding đúng cách.
- Cung cấp **SP metadata** để IdP dùng đúng SP signing và encryption certificates.
- Nhận `EncryptedAssertion` qua ACS và giải mã theo private key của registration được chọn.
- Kiểm chứng signed SAML Response/Assertion bằng **IdP verification certificate**, không bằng SP certificate.
- Xác minh `Response.Destination`, `SubjectConfirmationData.Recipient`, `Conditions.AudienceRestriction` và `InResponseTo` đúng.
- Phân biệt signed-and-encrypted assertion với encryption-only, XML signature wrapping và endpoint mismatch.
- Chạy smoke tests, cross-IdP/tenant tests, negative security tests và key rotation tests.
- Hiểu chỗ demo Java 17 có thể hỗ trợ tư duy nhưng **không thay thế OpenSAML cryptographic validation**.

## 2. Bộ thông số lab cố định

| Thuộc tính | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `registrationId` | `corp` | Khóa nội bộ Spring cho trust profile |
| SP entityID | `urn:portal:sp:corp` | Audience được kỳ vọng |
| SP base URL | `https://portal.example.test` | Public HTTPS origin |
| SP ACS | `https://portal.example.test/login/saml2/sso/corp` | Endpoint xử lý SAML Response |
| IdP entityID | `urn:corp:idp` | Asserting party/Response Issuer tin cậy |
| IdP SSO URL | `https://idp.corp.test/saml/sso` | Điểm nhận AuthnRequest |
| HTTP request binding | Redirect (ví dụ) | Browser đưa SAMLRequest đến IdP |
| HTTP response binding | POST | Browser POST SAMLResponse tới ACS |
| AuthnRequest ID | `_req901` | ID request duy nhất |
| RelayState | `R-901` | Opaque transaction reference |
| SP signing cert | `sp-sign.crt` | Public cert để IdP verify AuthnRequest |
| SP signing private key | `sp-sign.key` | SP ký AuthnRequest |
| SP encryption cert | `sp-enc.crt` | Public cert để IdP encrypt Assertion |
| SP decryption private key | `sp-enc.key` | SP decrypt Assertion |
| IdP signing cert | `idp-sign.crt` | SP verify signed Response/Assertion |
| NameID | `alice@corp.test` | Chỉ lấy sau trusted validation |
| Expected tenant | `north` | Application authorization sau SAML |

**Không mặc định `registrationId` bằng IdP entityID hoặc tenant ID.** Trong thực tế, cùng một SP có thể dùng nhiều registrations; mỗi registration phải nêu exact IdP, ACS, SP entityID và credentials.

## 3. Bốn loại khóa và hướng sử dụng

| Loại khóa/chứng chỉ | Private key do ai giữ? | Public key/cert do ai tin? | Công dụng |
| --- | --- | --- | --- |
| **SP signing** | SP | IdP | IdP kiểm chữ ký AuthnRequest, LogoutRequest theo policy |
| **SP encryption/decryption** | SP | IdP | IdP mã hóa Assertion, SP mở |
| **IdP signing** | IdP | SP | SP kiểm chữ ký Response/Assertion |
| **TLS HTTPS** | Server tương ứng | Browser/HTTP client | Bảo mật kênh vận chuyển; không thay XML signature |

Có thể dùng cùng một key pair cho signing và encryption ở một số deployments, nhưng **nên tách vai trò** khi IAM/security policy và interoperability hỗ trợ: rotation, quyền truy cập và blast radius rõ hơn.

**Sai lầm thường gặp:** cấu hình `idp-sign.crt` trong `decryption.credentials`, hoặc cung cấp `sp-enc.crt` làm chứng chỉ xác minh IdP. Chúng là những trust relationships khác nhau; không chuyển đổi chức năng chỉ vì đều là file X.509.

## 4. Sơ đồ enhanced SAML Web SSO

~~~text
 Browser                Spring Security SP                     Corp IdP
    |                           |                                  |
    | GET /saml2/authenticate/corp                                |
    |-------------------------->|                                  |
    |                    Generate ID=_req901                       |
    |                    Sign AuthnRequest with SP signing key      |
    |                    Save pending ID + RelayState + session     |
    |<----- Redirect SAMLRequest + RelayState + SigAlg + Signature|
    |------------------------------------------------------------->|
    |                                              Verify SP request
    |                                              Authenticate user
    |                                              Sign Assertion/Response
    |                                              Encrypt Assertion to
    |                                                SP encryption cert
    |<---------------------------- Browser HTML POST form ----------|
    | POST ACS: SAMLResponse + RelayState                          |
    |-------------------------->|                                  |
    |                    Resolve trusted registration               |
    |                    Verify signed SAML with IdP cert            |
    |                    Decrypt EncryptedAssertion using SP key     |
    |                    Verify signatures per profile              |
    |                    Check Issuer, Destination, Recipient        |
    |                    Check Audience, InResponseTo, time, replay  |
    |                    Map verified subject + tenant permissions  |
    |<-------------------- Local session or security error --------|
~~~

**Thứ tự kiểm chữ ký/giải mã tùy profile và vị trí chữ ký**: một Response ký bên ngoài có thể được kiểm trước khi giải mã EncryptedAssertion, trong khi Assertion được ký rồi mã hóa cần **giải mã Assertion trước khi xác minh chữ ký bên trong**. Spring/OpenSAML phân biệt các decryption strategies để giữ tính toàn vẹn XML signature.

## 5. AuthnRequest cần ký trong trường hợp nào?

SAML Web Browser SSO không buộc mọi IdP chấp nhận/đòi hỏi cùng một cách ký AuthnRequest. Metadata của IdP có thể chỉ rõ **`WantAuthnRequestsSigned`**, hoặc policy integration yêu cầu ký request. Nếu cần ký:
- SP có **private signing key** và matching X.509 certificate.
- IdP đăng ký **SP public signing certificate**.
- SP ký request theo đúng **binding** (HTTP Redirect query signature hoặc XML signature trong POST).
- IdP verify signature và trust **SP entityID** trước khi xử lý yêu cầu.
- Thuật toán signature và certificate lifecycle phải được hai bên thống nhất.

**Không cho rằng đặt `WantAuthnRequestsSigned=false` tại SP là một cách bỏ qua IdP policy**. Nếu IdP đòi ký, request unsigned phải bị IdP từ chối. Điều kiện này khác với **IdP ký SAML Response/Assertion** khi trả về.

Spring Security tài liệu hiện hành nêu `Saml2WebSsoAuthenticationRequestFilter` sẽ tạo request, ký/serialize theo registration và hỗ trợ signed Redirect requests khi có `signingX509Credentials`. Trường hợp không cần ký phải được cấu hình phù hợp IdP metadata và contract của hai bên.

## 6. HTTP-Redirect signature: chữ ký trên query string

Một URL minh họa, **không phải URL chứa chữ ký có thể verify ngay**:

~~~http
GET /saml/sso?SAMLRequest=ENCODED_DEFLATED_REQUEST&RelayState=R-901&SigAlg=RSA_SHA256_URI&Signature=ENCODED_SIGNATURE HTTP/1.1
Host: idp.corp.test
~~~

Với SAML HTTP-Redirect binding:
1. SP tạo XML `AuthnRequest` có `ID`, `IssueInstant`, `Issuer`, `Destination`, `AssertionConsumerServiceURL`.
2. Deflate/encode và URL-encode `SAMLRequest` theo binding.
3. Nếu có RelayState, đưa giá trị đã encode vào đúng vị trí.
4. Thêm `SigAlg` theo thuật toán đã cho phép.
5. Ký **chính xác chuỗi query được chuẩn hóa theo binding**, thường theo thứ tự `SAMLRequest=...&RelayState=...&SigAlg=...` khi RelayState có mặt.
6. Đưa chữ ký đã encode vào `Signature` query parameter.
7. IdP tạo lại signed input theo specification rồi verify bằng SP signing certificate đã trust.

**Không ký XML rồi mong IdP xác minh như HTTP-Redirect signature**, và không tự parse/re-encode các query parameters bằng cách làm mất nguyên định dạng signature. Chỉ dùng binding implementation của Spring/OpenSAML, không tự ráp URL bằng string concatenation.

**RelayState** thuộc signed input trong Redirect signature khi có tham số này và binding dùng signature. Tuy nhiên nó không đồng nghĩa một authenticated session ở browser.

## 7. HTTP-POST AuthnRequest và XML signature

Nếu IdP yêu cầu AuthnRequest gửi bằng POST, SAMLRequest là một XML document được encode để browser submit; chữ ký request thường xuất hiện như một **XML Signature** trong XML message theo profile/binding.

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req901"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.corp.test/saml/sso"
    AssertionConsumerServiceURL="https://portal.example.test/login/saml2/sso/corp">
    <saml:Issuer>urn:portal:sp:corp</saml:Issuer>
    <!-- Signed XML has a namespace-aware ds:Signature element
         at the profile-defined position. Omitted for readability. -->
</samlp:AuthnRequest>
~~~

**XML trên chỉ minh họa cấu trúc, là unsigned fixture**, không được đưa vào test khẳng định signature đúng. Trong SAML XML Signature, thứ tự phần tử và canonicalization/ID reference có ý nghĩa. Dùng OpenSAML/Spring để phát message signed đúng binding thay vì chèn `<ds:Signature>` thủ công.

**Không bỏ qua TLS** chỉ vì có XML signature: browser cookies, endpoints và metadata vẫn cần bảo vệ truyền dẫn.

## 8. Tạo credentials riêng cho SP signing và decryption

Trong lab có thể tạo key pairs bằng công cụ PKI/secret management được phê duyệt. Ví dụ OpenSSL **chỉ cho staging/test**, không chứa secrets thật:

~~~bash
# SP signing private key (RSA key pair for compatibility lab)
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out sp-sign.key

# Self-signed certificate chỉ phục vụ trao đổi test metadata
openssl req -new -x509 -sha256 -days 30 \
  -key sp-sign.key -out sp-sign.crt \
  -subj "/CN=portal-signing-lab"

# SP decryption key pair độc lập
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out sp-enc.key
openssl req -new -x509 -sha256 -days 30 \
  -key sp-enc.key -out sp-enc.crt \
  -subj "/CN=portal-encryption-lab"

# Chỉ kiểm danh tính/certificate metadata, không in private key
openssl x509 -in sp-sign.crt -noout -subject -fingerprint -sha256
openssl x509 -in sp-enc.crt -noout -subject -fingerprint -sha256
~~~

Trong production:
- Dùng CA/PKI/HSM/KMS/secret vault theo policy; self-signed cert nếu federation policy cho phép phải được **pin/trust out-of-band**, không tự tin qua Internet.
- Private keys ở secret mount, không commit vào Git hoặc image; service process có quyền đọc tối thiểu.
- SP publishing metadata chỉ chứa **public certificate**; IdP không được nhận `sp-sign.key` hay `sp-enc.key`.
- Kiểm thuật toán signing/encryption và key length theo cả hai sản phẩm, tránh legacy algorithms yếu.
- Ghi inventory issuer/SP entityID, certificate fingerprint, key lifecycle, rotation owner và deployment version.

## 9. Trao đổi thông tin với IdP đúng chiều

Gửi cho IdP admin đã xác thực:
- SP entityID exact `urn:portal:sp:corp`.
- SP ACS URL và HTTP POST binding.
- SP public **signing certificate** để kiểm AuthnRequest.
- SP public **encryption certificate** để mã hóa Assertion.
- SP metadata URL hoặc XML metadata từ Spring.
- IdP cần yêu cầu signed AuthnRequest không, loại binding nào, allowed signature algorithms.
- IdP có **sign Response, sign Assertion, hay cả hai**; encryption policy.
- IdP issuer/entityID, signing certificate/metadata URI được xác minh độc lập.
- Allowed NameID format, attributes, assertion lifetime, forced reauthentication và relaystate policy.

**Không gửi** private keys, raw SAMLResponse của người dùng, session cookie hoặc user password. Nếu IdP không có hỗ trợ mã hóa Assertion hoặc chỉ hỗ trợ thuật toán đã bị cấm, phải sửa interoperability/contract chứ không lặng lẽ nới security policy.

## 10. SP nhận những chứng cứ nào từ IdP?

Bản ghi SAML Response có thể ở dạng:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
    ID="_resp901"
    InResponseTo="_req901"
    Destination="https://portal.example.test/login/saml2/sso/corp"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:15Z">
    <saml:Issuer>urn:corp:idp</saml:Issuer>
    <samlp:Status>
      <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
    <saml:EncryptedAssertion>
      <!-- xenc:EncryptedData / xenc:EncryptedKey from IdP -->
    </saml:EncryptedAssertion>
</samlp:Response>
~~~

**Cấu trúc chỉ có tính minh họa**, không có ciphertext/chữ ký và không phải SAMLResponse valid. Một Response thật có thể được IdP ký ở mức Response hoặc ký Assertion bên trong EncryptedAssertion theo policy; **SP phải kiểm chữ ký hợp lệ theo cấu hình và không chấp nhận unsigned dữ liệu danh tính**.

Đừng giả `<EncryptedAssertion>` tự có `NameID`/`AudienceRestriction` đọc được trước khi giải mã. Không log decrypted assertion/PII nếu không có nhu cầu và quyền.

## 11. Assertion mã hóa: confidentiality, không phải authentication

Một Assertion có thể chứa:
- `NameID` hoặc `EncryptedID`, dùng định danh người dùng.
- `AuthnStatement` và `AuthnInstant`.
- `AttributeStatement` như department/groups.
- `Conditions` gồm time và `AudienceRestriction`.
- `SubjectConfirmationData`, gồm `Recipient`, `InResponseTo`, `NotOnOrAfter`.

IdP có thể mã hóa phần assertion bằng **content-encryption key đối xứng**, rồi bảo vệ content key bằng **SP public encryption key** theo XML Encryption; SP dùng corresponding private key để mở và kiểm integrity theo profile.

**Chú ý về thuật toán:** XML Encryption hỗ trợ nhiều phương thức và version; không nên giả mọi IdP đều hỗ trợ AES-GCM/RSA-OAEP cùng cấu hình. Chọn tổ hợp hiện đại, được tổ chức chấp thuận và thử interop thực tế. Tránh downgrade sang RSA1_5/legacy CBC/weak algorithms chỉ để “làm qua lỗi”.

**Nếu encrypted assertion giải mã được nhưng chữ ký sai, phải reject.** Nếu signature đúng nhưng Recipient/Audience sai, cũng phải reject.

## 12. Spring Boot SAML2 cấu hình đầy đủ ba loại credentials

Ví dụ **Spring Boot 3.x/4.x có dependency `spring-security-saml2-service-provider`**, properties tương ứng phải xác nhận với phiên bản BOM triển khai:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:portal:sp:corp"
            acs:
              location: "https://portal.example.test/login/saml2/sso/corp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-sign.key"
                  certificate-location: "file:/run/secrets/saml/sp-sign.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-enc.key"
                  certificate-location: "file:/run/secrets/saml/sp-enc.crt"
            assertingparty:
              entity-id: "urn:corp:idp"
              singlesignon:
                url: "https://idp.corp.test/saml/sso"
                sign-request: true
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml-trust/idp-sign.crt"
~~~

**Diễn giải:**
- `signing.credentials`: private key/cert của **SP**, để sign AuthnRequest; IdP cần biết public cert.
- `decryption.credentials`: private key/cert của **SP**, để decrypt encrypted Assertions; IdP cần public cert.
- `assertingparty.verification.credentials`: public signing cert của **IdP**, để SP verify Response/Assertion.
- `assertingparty.singlesignon.sign-request: true`: yêu cầu Spring phát request có ký phù hợp cấu hình IdP.
- `entity-id` SP khác `assertingparty.entity-id` của IdP.
- `acs.location` phải khớp public HTTPS URL, không phải URL internal pod.
- `registrationId=corp` là khóa nội bộ; không tự là trusted entityID.

**Lưu ý version:** tên API/property đã thay đổi qua Spring Boot/Security releases. **Không sao chép một snippet từ Spring Security 5.x và kết luận tương thích Spring Security 7.x**; dùng BOM và kiểm Spring Boot configuration metadata/Javadoc tương ứng. Đừng trộn `identityprovider` properties cũ với `assertingparty` khi dùng release mới.

## 13. Khai báo dependency và SecurityFilterChain

Thêm dependency phù hợp vào Maven project Spring Boot:

~~~xml
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
~~~

OpenSAML artifacts có thể cần Shibboleth repository theo hướng dẫn Spring Security cho BOM đang sử dụng. Không tự hardcode mix các OpenSAML generations và Spring Security dependency versions.

Một `SecurityFilterChain` cơ bản:

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/admin/**").hasAuthority("ROLE_ADMIN")
                .anyRequest().authenticated())
            .saml2Login(withDefaults())
            .saml2Metadata(withDefaults());
        return http.build();
    }
}
~~~

**Đây là class project-level, không biên dịch độc lập bằng JDK thuần.** Nó phụ thuộc Spring/SAML, trusted registrations và metadata. Endpoint `/admin/**` chỉ là ví dụ; `ROLE_ADMIN` cần mapping server-side và object-level authorization, không lấy tùy tiện từ Assertion.

**Quan trọng:** khi tự thay `SecurityFilterChain`, phải giữ các SAML filters/ACS matcher và bảo vệ login endpoints đúng framework. Không tắt CSRF toàn hệ chỉ vì IdP cần POST ACS; đánh giá và cấu hình theo Spring Security SAML2 profile, không cho các business POST routes bỏ CSRF.

## 14. Metadata SP xuất bản và kiểm ngoài băng

Khi bật `saml2Metadata(withDefaults())`, Spring Security có thể cung cấp SP metadata qua:

~~~text
https://portal.example.test/saml2/metadata/corp
https://portal.example.test/saml2/service-provider-metadata/corp
~~~

Kiểm metadata có:
- SP `entityID=urn:portal:sp:corp`.
- `SPSSODescriptor` và `AssertionConsumerService` đúng public ACS/binding.
- `KeyDescriptor use="signing"` với **SP signing certificate**.
- `KeyDescriptor use="encryption"` với **SP encryption certificate** nếu metadata phát hành đủ.
- `AuthnRequestsSigned` phù hợp policy.
- No private keys.
- Chỉ các endpoints công khai được phê duyệt; không leak internal host/HTTP port.

**Không xem việc metadata truy cập được là bằng chứng nó đáng tin.** IdP admin phải xác minh nguồn/certificate fingerprints/ownership ngoài băng. Khi rotate SP encryption certificate, phải đồng bộ metadata với IdP trước khi IdP bắt đầu encrypt bằng cert mới hoặc có overlap decryption keys được phê duyệt.

## 15. IdP metadata khác SP metadata

Bảng phân biệt:

| IdP metadata | SP metadata |
| --- | --- |
| `IDPSSODescriptor` | `SPSSODescriptor` |
| IdP entityID | SP entityID |
| IdP SSO service endpoint | SP ACS endpoint |
| IdP signing verification certificates | SP request-signing certificates |
| IdP binding/signature requirements | SP declaration signed AuthnRequests |
| IdP logout endpoints | SP logout endpoints |
| Có thể có encryption info dành cho IdP | SP encryption certificates dành cho IdP |

**Không đăng ký certificate nào cũng như “trusted key chung”.** Mỗi key gắn purpose, entityID, registration, thuật toán và owner. Nếu có hai IdPs `corp` và `partner`, không xác minh Assertion Corp bằng cert Partner chỉ vì cùng `kid`/CN.

## 16. Dùng API Java RelyingPartyRegistration khi cần

Trong Spring Security Java DSL, các concept:
- `RelyingPartyRegistration.withRegistrationId("corp")`.
- `entityId("urn:portal:sp:corp")`.
- `assertionConsumerServiceLocation("https://portal.example.test/login/saml2/sso/corp")`.
- `signingX509Credentials(...)` với `Saml2X509Credential.signing(spPrivateKey,spCert)`.
- `decryptionX509Credentials(...)` với `Saml2X509Credential.decryption(spPrivateKey,spCert)`.
- `assertingPartyMetadata(...)` với `entityId("urn:corp:idp")`, `singleSignOnServiceLocation(...)`, `verificationX509Credentials(...)` và `wantAuthnRequestsSigned(true)`.
- `InMemoryRelyingPartyRegistrationRepository` hoặc repository động có trusted metadata.

Ví dụ **fragment**, các credential objects được lấy từ secret store/certificate store đã kiểm:

~~~java
RelyingPartyRegistration rp =
    RelyingPartyRegistration.withRegistrationId("corp")
        .entityId("urn:portal:sp:corp")
        .assertionConsumerServiceLocation(
            "https://portal.example.test/login/saml2/sso/corp")
        .signingX509Credentials(keys ->
            keys.add(spRequestSigningCredential))
        .decryptionX509Credentials(keys ->
            keys.add(spAssertionDecryptionCredential))
        .assertingPartyMetadata(party -> party
            .entityId("urn:corp:idp")
            .singleSignOnServiceLocation(
                "https://idp.corp.test/saml/sso")
            .wantAuthnRequestsSigned(true)
            .verificationX509Credentials(keys ->
                keys.add(corpIdpVerificationCredential)))
        .build();
~~~

**Không runnable độc lập**: cần Spring Security SAML types, `Saml2X509Credential` được tạo từ đúng keys và X509 certs, imports và @Configuration. Cách này giúp tách **SP signing/decryption** với **IdP verification** nhưng vẫn cần policy validators.

**Không đưa URI metadata do browser chỉ định trực tiếp vào fromMetadataLocation** rồi auto-trust. IdP metadata source phải được phê duyệt; signing key rotation cần change control.

## 17. Kiểm AuthnRequest được ký thực sự

Đừng chỉ xem property `sign-request: true`. Kiểm artifact trên đường đi:

1. GET `/saml2/authenticate/corp` (khởi tạo session).
2. Spring tạo `AuthnRequest.ID` unique và lưu request để đối chiếu `InResponseTo`.
3. HTTP Redirect Location tới IdP chứa `SAMLRequest`, có thể có `RelayState`; nếu ký Redirect phải có `SigAlg` và `Signature`.
4. Dùng IdP test tin đúng **SP signing certificate** để verify query signature; modified SAMLRequest/RelayState phải fail.
5. Nếu dùng POST request binding, kiểm XML Signature trên AuthnRequest bằng IdP validation library.
6. SP `Issuer` đúng entityID; `Destination` đúng IdP SSO URL.
7. `AssertionConsumerServiceURL` đúng HTTPS ACS đã đăng ký.
8. IdP không chấp nhận unsigned request khi policy yêu cầu signed.
9. Không còn request cũ được sử dụng lại sau callback; test replay/expiry.
10. Không log raw SAMLRequest/RelayState ngoài test environment có quyền.

**Đừng dùng tool “base64 decode” đơn giản cho Redirect request rồi thấy XML không có `ds:Signature` mà kết luận request chưa ký.** Chữ ký Redirect binding thường nằm ở **query parameters** chứ không nằm trong XML.

## 18. Mã hóa EncryptedAssertion cần kiểm điều gì?

**Phía IdP phải làm:**
- Dùng đúng **SP public encryption certificate** từ approved SP metadata.
- Chọn XML Encryption algorithms theo interoperability và security policy.
- Sign Assertion hoặc Response theo contract **được RP thực sự kiểm**.
- Bảo toàn Response Destination/Assertion Recipient/Audience/InResponseTo.
- Không gửi Attributes nhạy cảm ngoài assertion nếu policy đòi confidentiality.

**Phía SP phải làm:**
- Chọn đúng `RelyingPartyRegistration`.
- Load matching **SP decryption private key** và cert.
- Decrypt EncryptedAssertion, EncryptedAttribute hoặc EncryptedID bằng OpenSAML/Spring strategy.
- Verify SAML signature(s) hợp lệ, key thuộc đúng IdP registration.
- Xác minh tất cả protocol constraints; không nhận assertion chỉ vì decryption pass.
- Ngăn XML attacks, oversized payloads, replay, decrypt-oracle diagnostics.
- Không log plaintext NameID/attributes sau decryption.

**Nếu IdP dùng certificate cũ sau rotation:** SP có thể phải tạm giữ decryption credentials cũ theo approved overlap để giải mã assertions đang transit; nhưng **compromised key** phải xử lý theo incident protocol, không giữ vô hạn.

## 19. Encryption vs XML Signature vs TLS

| Bảo vệ | Đối tượng | Nguy cơ được giảm | Không thay thế |
| --- | --- | --- | --- |
| AuthnRequest signature | SP → IdP message | Request forgery/tamper theo binding | Assertion signature |
| Response/Assertion signature | IdP → SP assertion/response | SAML claim forgery/alteration | Recipient/Audience/Replay |
| Assertion encryption | Nội dung identity attributes | Lộ NameID/attributes trên chặng trung gian | Xác thực IdP và authorization |
| TLS HTTPS | HTTP endpoints/browser transit | MitM/credential/cookie leakage | XML signature trong SAML |
| Replay cache + InResponseTo | Transaction/session | Replay/login fixation | Cryptographic validation |
| SP/IdP entityID + audience/recipient | Protocol context | Token/assertion dành sai bên | Local tenant permissions |

**Mật mã chỉ giải quyết một phần:** signed assertion hợp lệ của IdP A **không được dùng** tại tenant/registration chỉ tin IdP B, và EncryptedAssertion dành cho SP A **không được chấp nhận** tại SP B dù có shared keys.

## 20. Response.Destination: endpoint nào được nhận?

Ví dụ đúng:

~~~xml
<samlp:Response
  Destination="https://portal.example.test/login/saml2/sso/corp"
  InResponseTo="_req901">
  <!-- Signed or encrypted content according to agreed profile -->
</samlp:Response>
~~~

`Destination` là URL đích mà IdP gửi Response tới. SP cần so với URL ACS được cấu hình/hợp lệ theo registration và binding. Không chỉ kiểm hostname gần đúng hoặc prefix.

**Các negative cases:**
- Response được phát cho `https://other.example.test/login/saml2/sso/corp`.
- Đúng host nhưng sai registration path `/partner`.
- Scheme HTTP thay vì HTTPS.
- Port/proxy/public origin sai.
- IdP response có `Destination` trống khi profile yêu cầu.
- Response gửi tới endpoint A nhưng `Destination` ghi endpoint B.

**Chú ý proxy:** Spring deployment sau load balancer có thể nhìn `http://app:8080` nội bộ. Phải cấu hình trusted forwarded headers/ForwardedHeaderFilter hoặc proxy configuration tương ứng, **không chấp nhận tùy ý Host/X-Forwarded-Host do client gửi** để “sửa” Destination mismatch.

## 21. SubjectConfirmationData.Recipient: ai được xác nhận là người nhận?

Trong Assertion, bearer `SubjectConfirmationData` thường có `Recipient` là URL ACS:

~~~xml
<saml:SubjectConfirmation Method=
    "urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
      InResponseTo="_req901"
      Recipient="https://portal.example.test/login/saml2/sso/corp"
      NotOnOrAfter="2026-11-07T03:05:15Z"/>
</saml:SubjectConfirmation>
~~~

`Recipient` **không phải một email recipient**; nó xác định endpoint nhận bearer assertion. Nếu Recipient là ACS của app khác, SP phải từ chối.

**Không gộp Destination và Recipient thành một check:** Destination nằm ở Response, Recipient nằm trong SubjectConfirmationData; cả hai cần đúng theo profile/validation strategy.

Một Assertion có thể có nhiều SubjectConfirmations. Provider phải đánh giá theo semantics của profile, **không lấy đại trường đầu tiên rồi bỏ qua security constraints**.

## 22. AudienceRestriction: assertion dành cho SP entityID nào?

Ví dụ:

~~~xml
<saml:Conditions
    NotBefore="2026-11-07T02:59:15Z"
    NotOnOrAfter="2026-11-07T03:05:15Z">
  <saml:AudienceRestriction>
    <saml:Audience>urn:portal:sp:corp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

**Audience** thông thường là **SP entityID**, không nhất thiết là ACS URL. Một identity assertion signed bởi Corp nhưng `Audience=urn:other:sp` không thể được Portal dùng.

Đánh giá SAML Conditions theo specification khi có nhiều `AudienceRestriction`, không triển khai một phép “contains bất kỳ một audience nào thì pass” nếu các restriction blocks có semantics bổ sung. Giao cho OpenSAML provider đúng release rồi thêm application validator chứ không tự thay bằng string search XML.

**Cẩn thận với nhiều registrations:** nếu `corp` và `partner` dùng hai SP entityIDs, không dùng một global `trustedAudiences={"all"}`. Audience mapping phải thuộc registration.

## 23. InResponseTo và AuthnRequest correlation

Với **SP-initiated SSO**, SP phát AuthnRequest có `ID=_req901` và lưu pending giao dịch vào repository. Response phải tham chiếu ID đó:

~~~text
Pending:
  session/browser context = S-31
  registrationId          = corp
  AuthnRequest ID         = _req901
  RelayState              = R-901
  expected ACS            = https://portal.example.test/login/saml2/sso/corp
  TTL                     = short, bounded

SAML Response:
  Response.InResponseTo   = _req901
  SubjectConfirmationData.InResponseTo = _req901
  RelayState              = R-901
~~~

**Kiểm:** request còn pending, thuộc đúng session/context, chưa expired/consumed, registration đúng, response và subject confirmation khớp. Nếu một tab phát request B rồi ghi đè A tùy repository, response A không được “tha” vì signature hợp lệ.

**IdP-initiated/unsolicited SAML** không có AuthnRequest để correlate. Chỉ nhận nếu policy đã được phê duyệt riêng, có kiểm signature/issuer/recipient/audience/time/replay/login-CSRF. Không dùng unsolicited mode làm fallback để vượt lỗi pending session.

## 24. RelayState và login CSRF

`RelayState` là binding parameter thường chứa opaque handle cho request/return URL, không phải identity credential. OASIS SAML HTTP Redirect/POST bindings đặt giới hạn 80 byte theo profile. Trong Redirect binding ký request, RelayState có thể nằm trong signed query; trong POST binding, XML signature không mặc định ký form field RelayState.

Test:
- RelayState đúng value đã phát.
- Thay một byte → deny/missing pending.
- Dùng RelayState của flow B với Response A → deny.
- Bỏ RelayState → fail closed nếu repository phụ thuộc nó.
- Dùng raw RelayState làm external redirect URL → chặn open redirect.
- Session cookie không được gửi ở cross-site POST (SameSite/Domain/Path) → không tự nhận login.

**Security trade-off:** Spring mặc định lưu AuthnRequest trong `HttpSessionSaml2AuthenticationRequestRepository`, đem lại natural browser-session binding. Cache repository keyed theo RelayState giúp có nhiều pending requests/cross-site scenarios trong một số versions, nhưng **không tự chứng minh callback thuộc browser khởi tạo**, làm tăng login fixation risk nếu thiếu ràng buộc bổ sung.

## 25. Thời gian, replay và SubjectConfirmation

Ngoài crypto và recipient, phải kiểm:
- `IssueInstant` hợp lệ theo policy.
- `Conditions.NotBefore` và `NotOnOrAfter`, clock skew có giới hạn.
- `SubjectConfirmationData.NotOnOrAfter` cho bearer confirmation.
- `AuthnInstant`, `SessionNotOnOrAfter`, `SessionIndex` theo use case.
- `Response.ID` và `Assertion.ID` chưa bị replay.
- `InResponseTo` đúng pending request.
- Recipient/Audience khớp đúng registration và current public ACS.
- Đúng IdP entityID và signing credentials.
- Session cookie/relay binding không bị thay.
- Local account active, tenant membership và role mapping sau authentication.

**Không nới clock skew rất lớn chỉ để giải quyết NTP drift**. Trường hợp signed Assertion bị replay trong TTL vẫn là replay, không phải valid login mới.

## 26. Spring: đường nhận Response và decryption

Tại ACS, Spring Security:
1. `Saml2WebSsoAuthenticationFilter` nhận SAMLResponse (thường POST).
2. `Saml2AuthenticationTokenConverter` resolve trusted `RelyingPartyRegistration` và pending request.
3. `OpenSaml5AuthenticationProvider` (theo Spring Security 7.x reference) xử lý decryption/validation, dựa trên IdP verification credentials và SP decryption credentials.
4. Nếu có EncryptedAssertion/EncryptedAttribute/EncryptedID, decryption strategies trong provider xử lý theo vị trí.
5. OpenSAML kiểm signature/issuer/conditions/confirmation theo policy/version.
6. Response thành `Saml2Authentication` với verified principal/attributes.
7. Application authorities/tenant policy bổ sung sau SAML validation.
8. Failure phải không tạo SecurityContext authenticated.

**Phiên bản cũ:** Spring Security 6.x có thể dùng `OpenSaml4AuthenticationProvider` hoặc APIs khác; không áp dụng names mới nếu BOM chưa hỗ trợ. Tài liệu Spring phân biệt **Response elements decrypter** (EncryptedAssertion) và **Assertion elements decrypter** (EncryptedAttribute/EncryptedID) vì thao tác decryption có thể ảnh hưởng XML signature integrity.

## 27. Vì sao không nên tự giải mã trước khi verify signature một cách tùy tiện?

Một Response có thể:
- Được **IdP ký tại Response**, còn EncryptedAssertion nằm bên trong.
- Chứa **Assertion đã ký rồi mã hóa**, Response không ký ngoài.
- Có cả signed Response và signed Assertion.
- Mã hóa chỉ Attribute/NameID bên trong một Assertion có XML Signature.

Nếu tự viết handler:
1. Parse XML không có bảo vệ và tìm phần tử EncryptedAssertion.
2. Decrypt mọi nested elements ngay lập tức.
3. Verify chữ ký tại node khác.
4. Lấy NameID từ một unsigned XML element.

...có thể gây **XML Signature Wrapping** hoặc thay đổi canonicalization của signed XML. Với signed assertion containing EncryptedAttribute, Spring docs nhấn mạnh **không decrypt encrypted Assertion elements trước khi verify signature nếu thao tác đó phá chữ ký**.

**Giải pháp:** dùng provider OpenSAML chuẩn, giữ đúng thứ tự validation/decryption theo profile, chỉ mở rộng hook khi thực sự cần và phải có signed negative fixtures. Không dùng regex/XML DOM tự chế để tạo Authentication.

## 28. Một ca sai “decrypt được” nhưng wrong recipient

Giả sử một IdP phát encrypted assertion cho `urn:portal:sp:corp`. Cùng một private decryption key bị reuse ở một SP khác khiến ứng dụng B mở được ciphertext. Nhưng `Recipient` là:

~~~text
https://portal.example.test/login/saml2/sso/corp
~~~

Trong khi B đang chạy ở:

~~~text
https://billing.example.test/login/saml2/sso/billing
~~~

**B phải reject** vì bearer assertion được phát cho Portal ACS, kể cả khi decrypt và verify signature thành công. Kiểm `AudienceRestriction` của B (ví dụ `urn:billing:sp`) sẽ thêm một lớp độc lập.

Điều này chống **confused deputy / assertion substitution**. Shared key không tự cho phép dùng assertion ở nhiều SPs.

## 29. Multi-IdP và multi-tenant: key isolation

Ví dụ:

| Registration | Trusted IdP | SP entityID | ACS | Tenant policy |
| --- | --- | --- | --- | --- |
| `corp` | `urn:corp:idp` | `urn:portal:sp:corp` | `/login/saml2/sso/corp` | North |
| `partner` | `urn:partner:idp` | `urn:portal:sp:partner` | `/login/saml2/sso/partner` | South |

**Không chọn đúng registration chỉ bằng XML Issuer chưa verify và coi đó là bằng chứng trust.** XML Issuer trước verification có thể là candidate hint; Spring resolver phải chọn trong repository đã duyệt, rồi OpenSAML verify bằng đúng IdP keys và recipient/audience.

Một IdP có thể phục vụ nhiều tenants hoặc một tenant dùng nhiều IdPs; mapping thực tế có thể n–n, nhưng **tenant access là application authorization**, không tự suy ra từ registration path hoặc Assertion group name.

**Không tự link hai NameID/email trùng giữa Corp/Partner**; namespace external identity phải gồm verified IdP entityID và stable subject.

## 30. Reverse proxy, URL rewriting và ACS mismatch

Một lỗi thực tế:

~~~text
Public URL:
  https://portal.example.test/login/saml2/sso/corp

Ingress -> internal backend:
  http://spring-app-01:8080/login/saml2/sso/corp

IdP Destination/Recipient:
  https://portal.example.test/login/saml2/sso/corp
~~~

Nếu Spring tự tính base URL từ internal request hoặc tin forwarded headers do attacker sửa, dễ sinh `Destination`/`Recipient` sai hoặc open redirect.

Biện pháp:
- Khai báo exact public ACS và SP entityID trong trusted registration.
- Proxy thiết lập Forwarded/X-Forwarded-* sau khi **xóa header do client gửi**.
- Chỉ trust forwarded headers từ gateway đã phê duyệt, whitelist public hosts.
- Bật HTTPS end-to-end hoặc approved TLS termination, bảo vệ session cookie.
- Không chuyển toàn bộ validation sang `request.getServerName()` không kiểm soát.
- Test localhost/staging/prod domain riêng, certs/metadata từng environment.
- Nếu IdP dùng ACS URL cũ, cập nhật approved metadata/partner config, không tự tạo wildcard recipient.
- Không đổi ACS path chỉ ở Spring Filter mà quên thay metadata/IdP.
- Kiểm query parameters và RelayState qua URL encoding/proxy không bị thay.

**Đừng sửa bằng cách bỏ Destination/Recipient validation**. Lỗi URL là integration configuration, không phải điều kiện SAML đáng nới.

## 31. Lưu ý về X.509 certificate validity và trust

SAML signing certificates thường được dùng làm **pinned verification credentials** trong federation, khác mô hình TLS PKIX trust. Theo vendor/profile, một cert tự ký có thể được tin nếu được đăng ký chính xác qua metadata/trust process, nhưng không được **auto-trust cert bất kỳ trong SAMLResponse**.

Kiểm:
- Certificate thuộc **đúng IdP entityID/registration**.
- Key type/length và signature algorithm phù hợp policy.
- Cert/key rotation có owner, overlap window và removal của old keys.
- Metadata từ nguồn tin cậy, có integrity và bản ghi fingerprint.
- SP signing cert có private key tương ứng ở secret store.
- SP decryption private key khớp encryption cert IdP đang dùng.
- Không mượn private keys của IdP để decrypt SP Assertions.
- Không bật legacy crypto vì incompatibility chưa được giải quyết.
- Khi private key lộ, xử lý incident response riêng, không coi rotation bình thường.

**TLS certificate expiry** và **SAML verification certificate trust** có thể có lifecycle khác; không gom mọi lỗi thành “certificate expired”.

## 32. Rotation cho SP signing key và SP encryption key

**SP signing key rotation:**
1. Tạo signing key pair mới trong secret store.
2. Đăng ký public signing cert mới với IdP ngoài băng/metadata.
3. Kiểm IdP có cho phép overlap keys và signed AuthnRequests từ key mới.
4. Chuyển Spring signing credential theo canary.
5. Test IdP accept new signed requests, từ chối unsigned/wrong signer.
6. Remove old key khi an toàn, ghi audit.

**SP encryption key rotation:**
1. Tạo private/public encryption key pair mới.
2. Bảo đảm SP có thể decrypt bằng key mới trước khi IdP bắt đầu encrypt mới.
3. Publish SP metadata mới, phối hợp IdP switch encryption cert.
4. Nếu có inflight encrypted assertions dùng cert cũ, duy trì old decryption credential chỉ trong approved overlap.
5. Test old/new encrypted responses theo real OpenSAML flow.
6. Remove old key đúng policy; nếu key đã compromise, xem xét từ chối old assertions và force reauthentication.

**IdP signing key rotation:** SP cập nhật `assertingparty.verification.credentials` từ trusted source; nếu key nghi lộ, **không giữ old key trusted** chỉ để tránh outage.

## 33. Những tình huống cấu hình tưởng đúng nhưng nguy hiểm

| Cấu hình/lỗi | Vì sao nguy hiểm | Kết quả mong đợi |
| --- | --- | --- |
| IdP muốn signed request nhưng SP thiếu signing key | Login fail hoặc IdP policy bypass | IdP reject/setting lỗi rõ |
| SP ký bằng wrong account/key | IdP không tin request signer | Reject |
| Redirect signature dùng sai canonical query | Signature mismatch | Reject |
| POST request XML unsigned nhưng IdP yêu cầu signed | Không chứng minh SP identity | Reject |
| IdP encrypt bằng cert cũ SP đã xóa private key | Không decrypt được | Fail closed |
| SP gắn IdP public cert vào decryption config | Không có matching private key | Fail closed |
| SP dùng signing cert như IdP verification cert | Sai bên ký | Reject |
| IdP gửi encrypted nhưng unsigned assertion/response | Confidentiality không tạo authenticity | Reject theo signature policy |
| IdP signature valid nhưng sai Recipient | Assertion dành SP khác | Reject |
| IdP signature valid nhưng sai Audience | Assertion dành SP khác | Reject |
| RelayState đúng nhưng InResponseTo sai | Response không thuộc request | Reject |
| XML Signature Wrapping | Đọc unsigned subject/roles | Reject |
| Same NameID từ IdPs khác nhau | Identity collision | Separate namespaces |
| Trùng SP encryption private key ở nhiều tenants | Blast radius tăng | Tách keys/policy |
| Host/X-Forwarded-Host spoof | ACS validation/routing sai | Reject untrusted headers |
| Clock skew quá rộng | Replay window tăng | Giới hạn theo policy |
| Không có assertion replay cache | Một signed assertion bị dùng lại | Reject repeats |

## 34. Kịch bản integration test theo từng lớp

**Lớp 1 — cấu hình registration:**
- Verify `corp` có SP signing credential, decryption credential và Corp IdP verification credential đúng purposes.
- Metadata SP công bố hai public certs và ACS/entityID đúng.
- Missing key file/invalid PEM → startup hoặc authentication failure có kiểm soát, không fallback insecure.

**Lớp 2 — AuthnRequest signing:**
- Capture Redirect Location/POST request từ SP.
- IdP test verify đúng signature; tamper request/RelayState → reject.
- Kiểm signature algorithm allowlist và `Issuer/Destination/ACS`.

**Lớp 3 — encrypted signed assertion:**
- IdP test phát EncryptedAssertion dùng SP public encryption cert.
- SP decrypt bằng private key và verify signed Response/Assertion của Corp.
- Wrong private key, wrong algorithm, unsigned claim, corrupted ciphertext → deny.

**Lớp 4 — protocol recipient and correlation:**
- Destination/Recipient/Audience/Issuer/InResponseTo đúng → pass.
- Thay riêng từng field bằng giá trị sai, ký lại bằng test IdP key hợp lệ để chứng minh **validation logic**, không chỉ chứng minh signature tamper.
- Expired Conditions, replay Assertion ID, missing pending request → deny.

**Lớp 5 — business authorization:**
- NameID verified→local account đúng, roles/tenant mapped server-side.
- Same email từ Partner IdP không tự liên kết Corp account.
- Signed Assertion có group admin nhưng thiếu authorized mapping → không có `ROLE_ADMIN`.

## 35. Tạo signed/encrypted test fixtures đúng cách

**Không sửa một SAMLResponse signed ở text editor rồi đòi nó pass signature**, vì việc sửa XML sẽ làm chữ ký sai trước khi test đến Recipient/Audience. Thay vào đó, với IdP test sở hữu test signer key:
1. Tạo AuthnRequest mới cho session test.
2. Chọn variant cho test (Recipient sai, Audience sai, InResponseTo sai, issuer sai...).
3. Build Assertion/Response theo variant.
4. Sign bằng **đúng IdP test signing key** sau khi đặt các trường.
5. Encrypt Assertion dùng **SP test encryption certificate**.
6. POST đến ACS với cookies/RelayState phù hợp.
7. Assert failure category và rằng **không có authenticated SecurityContext**.
8. Re-run happy path với cùng signer/decryption settings và correct recipient để chứng minh khác biệt.
9. Test duplicate/replay IDs và different registrations/tenants bằng fresh sessions.
10. Không dùng keys, assertions, NameID thật của production.

Đối với invalid signature test, cố tình thay bytes **sau khi ký** hoặc dùng wrong signer. Đối với recipient validation test, giữ crypto signature hợp lệ nhưng Recipient sai. Nếu không tách các ca này, test có thể PASS vì failed signature chứ **chưa kiểm recipient**.

## 36. Browser E2E: signed request và encrypted response

Một browser E2E test đáng tin cần:
- Browser session mới, không có Spring session cũ.
- SP GET /saml2/authenticate/corp tạo AuthnRequest ký.
- IdP test được cấu hình trust SP signing cert và sign+encrypt response.
- Callback HTTP POST tới ACS public URL.
- Browser gửi session cookie cần cho pending AuthnRequest; kiểm SameSite/Secure/Domain/Path nếu có.
- SP xác minh signature, decrypt Assertion, kiểm recipient/audience.
- Xác nhận verified principal và local `GrantedAuthority`.
- Check logout/reauthentication, replay, session fixation.
- Check malformed/oversized XML/invalid binding and redirect errors.
- Test nhiều browsers/proxy routes/IdP accounts/tenants nếu có.
- Không đánh giá success chỉ bằng 302 (error handler cũng redirect).
- Không chia sẻ HAR có raw signed assertion/cookie/trust secrets ra ngoài test security team.

**Không tắt CSRF toàn ứng dụng để xử lý POST ACS**, cũng không tắt signature check để “làm test pass”. Dùng integration support chuẩn của Spring Security và OpenSAML.

## 37. Java 17 runnable: thực hành chữ ký, bảo mật ciphertext và recipient policy

Để hiểu ba ranh giới trong một chương trình chạy được, ví dụ sau dùng **JCA/JCE của JDK 17**:

- RSA/SHA256 ký và verify một **chuỗi minh họa** tương tự Redirect signed input.
- AES-GCM mã hóa/decrypt dữ liệu giả lập; integrity tag phát hiện thay AAD.
- Các checks policy exact Issuer, Destination, Recipient, Audience, InResponseTo, Conditions và replay.

**Giới hạn quan trọng:** chương trình **không phát SAML XML Signature/Redirect binding thật**, không dùng XML Encryption hay certificate validation của SAML, không dùng RSA-OAEP wrap AES key cho IdP→SP. **AES key có sẵn trong cùng chương trình**, khác key-transport thực tế. Các boolean signature/decryption trong policy model phải là kết quả *sau* khi OpenSAML provider đã xác minh. **Không sao chép chương trình làm Spring AuthenticationProvider**.

Tạo file **SamlSigningEncryptionRecipientDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SamlSigningEncryptionRecipientDemo {

    static final String SP = "urn:portal:sp:corp";
    static final String IDP = "urn:corp:idp";
    static final String ACS =
            "https://portal.example.test/login/saml2/sso/corp";
    static final String REQUEST_ID = "_req901";

    record Evidence(boolean signatureValid, boolean decrypted,
                    String issuer, String destination, String recipient,
                    String audience, String inResponseTo,
                    boolean timeValid, boolean unused) {}

    static byte[] bytes(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    static byte[] sign(PrivateKey key, String data)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initSign(key);
        s.update(bytes(data));
        return s.sign();
    }

    static boolean verify(PublicKey key, String data, byte[] signed)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initVerify(key);
        s.update(bytes(data));
        return s.verify(signed);
    }

    static byte[] encrypt(SecretKey key, byte[] iv, String plain, String aad)
            throws GeneralSecurityException {
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        c.updateAAD(bytes(aad));
        return c.doFinal(bytes(plain));
    }

    static String decrypt(SecretKey key, byte[] iv, byte[] cipher, String aad)
            throws GeneralSecurityException {
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        c.updateAAD(bytes(aad));
        return new String(c.doFinal(cipher), StandardCharsets.UTF_8);
    }

    static String validate(Evidence e) {
        if (!e.signatureValid()) {
            return "DENY_IDP_SIGNATURE";
        }
        if (!e.decrypted()) {
            return "DENY_DECRYPTION";
        }
        if (!IDP.equals(e.issuer())) {
            return "DENY_ISSUER";
        }
        if (!ACS.equals(e.destination())) {
            return "DENY_DESTINATION";
        }
        if (!ACS.equals(e.recipient())) {
            return "DENY_RECIPIENT";
        }
        if (!SP.equals(e.audience())) {
            return "DENY_AUDIENCE";
        }
        if (!REQUEST_ID.equals(e.inResponseTo())) {
            return "DENY_IN_RESPONSE_TO";
        }
        if (!e.timeValid()) {
            return "DENY_CONDITIONS";
        }
        if (!e.unused()) {
            return "DENY_REPLAY";
        }
        return "PASS_PROTOCOL_GATES";
    }

    static Evidence evidence(boolean sign, boolean decrypted,
            String issuer, String destination, String recipient,
            String audience, String requestId, boolean time, boolean unused) {
        return new Evidence(sign, decrypted, issuer, destination,
                            recipient, audience, requestId, time, unused);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair signingPair = generator.generateKeyPair();

        String redirectInput =
                "SAMLRequest=encoded&RelayState=R-901&SigAlg=rsa-sha256";
        byte[] signed = sign(signingPair.getPrivate(), redirectInput);
        System.out.println("SP AuthnRequest signature: "
                + verify(signingPair.getPublic(), redirectInput, signed));
        System.out.println("Changed RelayState signature: "
                + verify(signingPair.getPublic(),
                        "SAMLRequest=encoded&RelayState=R-X&SigAlg=rsa-sha256",
                        signed));

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(128);
        SecretKey aes = keyGenerator.generateKey();
        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        String plaintext = "NameID=alice|aud=urn:portal:sp:corp";
        byte[] ciphertext = encrypt(aes, iv, plaintext, SP);
        System.out.println("Encrypted assertion demo: "
                + plaintext.equals(decrypt(aes, iv, ciphertext, SP)));

        try {
            decrypt(aes, iv, ciphertext, "urn:other:sp");
            System.out.println("Wrong encryption context: UNEXPECTED_ACCEPT");
        } catch (GeneralSecurityException rejected) {
            System.out.println("Wrong encryption context: DENY_GCM_AUTH");
        }

        Evidence good = evidence(true, true, IDP, ACS, ACS,
                                 SP, REQUEST_ID, true, true);
        System.out.println("Protocol valid: " + validate(good));
        System.out.println("Missing IdP signature: " + validate(evidence(
                false, true, IDP, ACS, ACS, SP, REQUEST_ID, true, true)));
        System.out.println("Cannot decrypt: " + validate(evidence(
                true, false, IDP, ACS, ACS, SP, REQUEST_ID, true, true)));
        System.out.println("Wrong Issuer: " + validate(evidence(
                true, true, "urn:partner:idp", ACS, ACS,
                SP, REQUEST_ID, true, true)));
        System.out.println("Wrong Destination: " + validate(evidence(
                true, true, IDP, "https://other.test/acs", ACS,
                SP, REQUEST_ID, true, true)));
        System.out.println("Wrong Recipient: " + validate(evidence(
                true, true, IDP, ACS, "https://other.test/acs",
                SP, REQUEST_ID, true, true)));
        System.out.println("Wrong Audience: " + validate(evidence(
                true, true, IDP, ACS, ACS,
                "urn:other:sp", REQUEST_ID, true, true)));
        System.out.println("Wrong InResponseTo: " + validate(evidence(
                true, true, IDP, ACS, ACS,
                SP, "_req-other", true, true)));
        System.out.println("Expired Assertion: " + validate(evidence(
                true, true, IDP, ACS, ACS,
                SP, REQUEST_ID, false, true)));
        System.out.println("Replayed Assertion: " + validate(evidence(
                true, true, IDP, ACS, ACS,
                SP, REQUEST_ID, true, false)));
    }
}
~~~

Chạy với **JDK 17 trở lên**:

~~~bash
javac SamlSigningEncryptionRecipientDemo.java
java SamlSigningEncryptionRecipientDemo
~~~

**Stdout chính xác:** RSA/AES keys và GCM IV được tạo ngẫu nhiên mỗi lần, nhưng chương trình **không in key/ciphertext**, chỉ in các phép kiểm boolean và decision cố định.

~~~text
SP AuthnRequest signature: true
Changed RelayState signature: false
Encrypted assertion demo: true
Wrong encryption context: DENY_GCM_AUTH
Protocol valid: PASS_PROTOCOL_GATES
Missing IdP signature: DENY_IDP_SIGNATURE
Cannot decrypt: DENY_DECRYPTION
Wrong Issuer: DENY_ISSUER
Wrong Destination: DENY_DESTINATION
Wrong Recipient: DENY_RECIPIENT
Wrong Audience: DENY_AUDIENCE
Wrong InResponseTo: DENY_IN_RESPONSE_TO
Expired Assertion: DENY_CONDITIONS
Replayed Assertion: DENY_REPLAY
~~~

**Vì sao chạy đúng:** `Signature` verify kiểm cùng bytes và public key; đổi RelayState làm bytes không còn giống, nên trả `false`. AES-GCM dùng key, IV và AAD nhất quán nên decrypt đúng; đổi AAD làm authentication tag invalid và exception được phân loại. Policy model kiểm **từng ràng buộc tách biệt**. Đây **chỉ là minh họa các thuộc tính bảo mật**, không phải sản phẩm SAML protocol stack.

## 38. Kiểm thử chương trình Java và các bẫy khi áp dụng

Nếu sửa `SP`, `ACS` hoặc `REQUEST_ID` trong demo, cần sửa fixtures phù hợp; nếu không sẽ thấy `DENY_AUDIENCE`, `DENY_RECIPIENT` hoặc `DENY_IN_RESPONSE_TO`. Điều này giúp thấy validator cần **expected values được server cấu hình**, không lấy từ chính assertion mà attacker có thể điều khiển.

**Không đưa `boolean signatureValid` hoặc `boolean decrypted` thành tham số nhận từ browser.** Trong ứng dụng thật, chúng chỉ được tạo bởi OpenSAML khi kiểm signature/cert/decrypt bằng trusted registration. Mô hình JCA cũng không xử lý:
- XML ID reference và canonicalization.
- XML signature wrapping.
- RSA-OAEP content key transport.
- SAML NameID/subject confirmation semantics.
- IdP signature placement/profile.
- Clock skew và distributed replay cache.
- Session/RelayState/IdP-initiated flow security.
- Binding-specific encodings.

Vì vậy bài Java **phục vụ hiểu cơ chế, không phục vụ xác thực SAML trong production**.

## 39. Bảng lỗi chẩn đoán theo tầng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| IdP báo unsigned request | SP chưa có signing private key hoặc sign-request false | Cấu hình signing, kiểm IdP policy |
| IdP báo invalid AuthnRequest signature | Sai SP signing cert, encoding, SigAlg | Kiểm binding, registered cert và signature |
| IdP báo unknown SP entityID | Issuer/metadata không đăng ký | Đồng bộ SP metadata |
| IdP gửi plain Assertion | IdP encryption policy chưa bật | Cấu hình encryption với SP cert, test |
| SP báo cannot decrypt EncryptedAssertion | Sai private key, cert rollover hoặc thuật toán | So SP decryption credential với IdP encryption cert |
| Decryption success nhưng login fail | Wrong signature/issuer/recipient/audience/time | Xem validation category |
| Invalid Signature/Checksum | IdP signing cert thay hoặc XML bị sửa | Kiểm trust metadata/key rotation |
| Signature verify với key Partner nhưng flow Corp | Registration confusion | Key isolation/strict issuer |
| `Destination` mismatch | ACS URL khác public origin, reverse proxy | Sửa ACS/forwarded headers/IdP metadata |
| `Recipient` mismatch | SubjectConfirmationData gửi SP khác | IdP sửa recipient hoặc reject |
| `AudienceRestriction` mismatch | SP entityID sai | Sửa exact audience, không wildcard |
| `InResponseTo` mismatch | Missing/overwritten pending AuthnRequest | Kiểm session/repository/RelayState |
| Callback không có HTTP session | SameSite/cookie TTL/load balancer | Test browser/Session store |
| Expired assertion | IdP/SP clock drift, Conditions TTL | Sync NTP, kiểm policy |
| Replayed assertion | Assertion ID/Response ID hoặc AuthnRequest reused | Reject, inspect replay cache |
| `ROLE_ADMIN` bị cấp nhầm | Attribute-to-authority mapping sai | Chặn privileged roles theo allowlist |
| Login pass qua HTTP 302 nhưng anonymous | Failure handler redirect | Assert Authentication/subject |
| Không lấy được user NameID sau encrypted assertion | Decryption/NameID format/Attribute handling | Kiểm decrypted signed assertion và profile |

**Không debug bằng cách print private key, raw assertion hoặc cookie.** Dùng correlation ID, hash request/response IDs, cert fingerprint, registrationId, failure category và test data.

## 40. Ma trận QA bảo mật — request signing và encryption

| # | Ca kiểm thử | Kết quả |
| --- | --- | --- |
| 01 | Signed Redirect AuthnRequest, đúng SP cert | IdP chấp nhận |
| 02 | Unsigned request khi IdP yêu cầu ký | IdP từ chối |
| 03 | Redirect signature ký với wrong SP key | IdP từ chối |
| 04 | Thay SAMLRequest bytes sau khi ký | Verify thất bại |
| 05 | Thay RelayState trong signed query | Verify thất bại |
| 06 | Thay SigAlg sau khi ký | Verify thất bại |
| 07 | Redirect signature canonicalization sai | Verify thất bại |
| 08 | POST binding nhưng chỉ có Redirect SigAlg | Không được coi là signed XML |
| 09 | Valid signed POST XML AuthnRequest | IdP chấp nhận theo policy |
| 10 | SP Issuer sai entityID | IdP từ chối |
| 11 | AuthnRequest Destination sai IdP endpoint | IdP từ chối |
| 12 | AuthnRequest ACS sai | IdP từ chối hoặc policy error |
| 13 | IdP encrypt bằng SP public encryption cert | SP decrypt được |
| 14 | IdP encrypt bằng cert của SP khác | SP từ chối/cannot decrypt |
| 15 | SP chỉ có public cert, thiếu decryption private key | Cannot decrypt |
| 16 | SP key rotation nhưng IdP vẫn dùng old cert ngoài overlap | Reject/controlled failure |
| 17 | EncryptedAssertion ciphertext bị sửa | Decrypt/integrity fail |
| 18 | Decrypted assertion nhưng unsigned | Reject theo signature policy |
| 19 | Signed Assertion sai IdP certificate | Reject |
| 20 | Valid signed+encrypted Assertion | Có thể pass khi protocol checks đúng |

## 41. Ma trận QA bảo mật — bên nhận, replay và tenant

| # | Ca kiểm thử | Kết quả |
| --- | --- | --- |
| 21 | Response Destination đúng ACS | Pass check |
| 22 | Destination trỏ SP khác | Reject |
| 23 | Destination dùng http thay vì HTTPS public | Reject |
| 24 | Destination đúng host nhưng sai registrationId | Reject |
| 25 | SubjectConfirmationData Recipient đúng | Pass check |
| 26 | Recipient trỏ ACS của app khác | Reject |
| 27 | Recipient đúng nhưng Audience sai | Reject |
| 28 | AudienceRestriction có SP entityID đúng | Pass |
| 29 | Audience chỉ chứa ACS URL thay vì SP entityID | Reject theo profile |
| 30 | Audience thuộc Partner SP khi flow Corp | Reject |
| 31 | InResponseTo khớp AuthnRequest pending | Pass check |
| 32 | InResponseTo trỏ request B | Reject |
| 33 | Response InResponseTo khớp nhưng SubjectConfirmationData sai | Reject |
| 34 | Missing pending AuthnRequest trong SP-initiated | Fail closed |
| 35 | Missing RelayState khi repository cần nó | Reject |
| 36 | Replay Assertion ID sau success | Reject |
| 37 | Response/Assertion NotOnOrAfter expired | Reject |
| 38 | Signed by Corp, XML issuer khai Partner | Reject |
| 39 | Signed assertion valid nhưng wrong NameID linking | Không auto-account-link |
| 40 | User verified không thuộc tenant North | 403 |
| 41 | User verified nhưng group admin không thuộc allowlist | Không cấp admin |
| 42 | Callback qua untrusted Host/X-Forwarded-Host | Không thay expected recipient |
| 43 | Assertion signature wrapping | Không dùng unsigned subject |
| 44 | XML malformed/oversized/XXE | Controlled rejection |
| 45 | Decryption succeeds nhưng IdP signing cert bị thu hồi | Reject |
| 46 | SP encryption private key lộ | Incident response/rotate/revoke |
| 47 | Hai tabs login khác request IDs | Không ghép sai InResponseTo |
| 48 | IdP-initiated SAML khi policy cấm | Reject |
| 49 | Same NameID từ hai IdPs | Không gộp identity |
| 50 | Multi-node replay concurrent POST | At-most-once policy |

**Tất cả negative tests phải assert không tạo authenticated session**. Với wrong Recipient/Audience, fixture phải được **IdP test ký lại hợp lệ**, nếu không chỉ đang test signature failure.

## 42. Runbook triển khai theo thứ tự

### Giai đoạn A — Chuẩn bị

1. Chốt Spring Boot/Security BOM, OpenSAML generation, IdP product/version.
2. Tạo test key pairs/certificates riêng cho SP signing và encryption.
3. Xác minh IdP signing certificate và metadata qua approved channel.
4. Chốt SP entityID, IdP entityID, SSO URL, ACS public HTTPS URL.
5. Chốt Redirect/POST request binding, signature requirements và algorithms.
6. Chốt IdP Response vs Assertion signature policy.
7. Chốt encrypted assertion/attribute policy và supported XML Encryption algorithms.
8. Chốt clock skew/replay/RelayState/session policy.
9. Tạo dedicated test IdP users, test tenant, SP local accounts và role mappings.
10. Xác nhận secret store, private key file permissions và key rotation owners.

### Giai đoạn B — Cấu hình

1. Cập nhật Spring signing/decryption/verification credentials theo đúng purpose.
2. Đặt `sign-request: true` khi IdP yêu cầu signed AuthnRequests.
3. Publish SP metadata, kiểm signing/encryption certificates không có private key.
4. IdP đăng ký SP metadata, bật sign+encrypt Response/Assertion theo contract.
5. Kiểm đúng `RelyingPartyRegistration` và URL mapping.
6. Bật Spring/OpenSAML validation mặc định, thêm profile-specific controls qua documented APIs.
7. Kiểm trusted proxy headers và public ACS.
8. Giữ session/RelayState correlation, CSRF policy và replay cache.
9. Kiểm mapping verified NameID/groups thành local roles/tenant permissions.
10. Bật safe logs/metrics, không log SAMLResponse.

### Giai đoạn C — QA và canary

1. Login happy path signed AuthnRequest + signed EncryptedAssertion.
2. Tamper Redirect signature/RelayState.
3. Wrong SP encryption private key.
4. Wrong IdP signing certificate/issuer.
5. Wrong Destination, Recipient, Audience và InResponseTo **từng trường một**.
6. Test expired/replayed Assertion.
7. Test browser cross-site POST cookies, session loss, two tabs, multi-node.
8. Test wrong IdP/tenant/account linking và role escalation.
9. Test signing/decryption key rollover, metadata cache và old-key removal.
10. Canary theo tenant/IdP, đo failure categories; rollout khi security owner duyệt.

### Giai đoạn D — Vận hành

1. Theo dõi cert fingerprints, expiration, private key access và configuration drift.
2. Theo dõi mismatch Destination/Recipient/Audience/InResponseTo, không hạ validation để giảm error.
3. Giữ account/tenant authorization server-side.
4. Đặt lịch rotation và staged tests với IdP.
5. Khi IdP signer hoặc SP decryption key lộ, kích hoạt incident runbook, quarantine trust/revoke sessions.
6. Review metadata fetch/renew và cache invalidation.
7. Bảo vệ session cookies, KMS/secret vault và TLS proxy.
8. Kiểm lại E2E negative matrix sau mọi thay đổi IdP, DNS, load balancer, cert hoặc Spring Security upgrade.
9. Giữ fail-closed trên missing credentials hoặc invalid SAML response.
10. Cập nhật tài liệu interoperability cho mọi registration riêng biệt.

## 43. Observability có chọn lọc

Gợi ý metrics tự instrument:

| Metric | Ý nghĩa |
| --- | --- |
| `saml_authnrequest_signed_total` | Request signing thành công theo registration |
| `saml_authnrequest_signature_error_total` | Signing key/algorithm errors |
| `saml_encrypted_assertion_total` | SAML encrypted assertions được xử lý |
| `saml_decryption_failed_total` | Wrong key/ciphertext/policy |
| `saml_idp_signature_failed_total` | Signature/trust key mismatch |
| `saml_destination_mismatch_total` | Response gửi sai ACS |
| `saml_recipient_mismatch_total` | SubjectConfirmationData sai |
| `saml_audience_mismatch_total` | Assertion dành sai SP |
| `saml_inresponseto_mismatch_total` | Request correlation sai |
| `saml_replay_rejected_total` | Response/Assertion replay |
| `saml_tenant_denied_total` | Authentication pass nhưng authorization deny |
| `saml_key_rotation_drift_total` | Nodes/IdP metadata lệch |
| `saml_authentication_success_total` | Authentication thành công theo approved source |

**Không tự cho rằng Spring có sẵn các metric names trên.** Logs nên dùng correlation ID, registrationId, policy/certificate fingerprint, mã lỗi và node; không đưa raw SAMLResponse, NameID/PII, decrypted assertion, private keys, session ID hoặc RelayState nhạy cảm vào logs. Hạn chế cardinality và bảo vệ audit access.

## 44. Câu hỏi tự đánh giá

**1. Ai ký AuthnRequest?**  
SP/Relying Party, bằng SP private signing key; IdP xác minh bằng SP public signing cert.

**2. Ai mã hóa Assertion?**  
IdP dùng SP public encryption certificate; SP giải mã bằng corresponding private key.

**3. Ai ký SAML Response/Assertion?**  
IdP theo profile; SP xác minh bằng trusted IdP verification credentials.

**4. SP giải mã assertion thành công thì authentication đã đủ chưa?**  
Chưa; cần signature/issuer/recipient/audience/time/InResponseTo/replay và local authorization.

**5. Destination là gì?**  
URL đích nhận SAML Response, thường là public ACS.

**6. Recipient khác AudienceRestriction thế nào?**  
Recipient là endpoint ACS trong SubjectConfirmationData; AudienceRestriction nhận diện SP entityID trong Conditions.

**7. InResponseTo dùng để làm gì?**  
Liên kết Response/SubjectConfirmation với AuthnRequest đã lưu trong SP-initiated flow.

**8. Redirect binding signature có luôn nằm trong XML không?**  
Không. Nó thường là query parameters SigAlg/Signature bên ngoài XML.

**9. POST binding AuthnRequest có thể sử dụng chữ ký gì?**  
XML Signature theo protocol/binding profile.

**10. Có nên dùng cùng certificate cho SP signing và IdP verification không?**  
Không. Đó là hai trust directions khác nhau.

**11. Vì sao không sửa sai Recipient bằng cách tắt validator?**  
Vì có thể chấp nhận assertion được cấp cho một SP khác, gây confused deputy/account takeover.

**12. Tại sao reverse proxy dễ gây mismatch?**  
Backend có thể thấy internal HTTP host/port khác public HTTPS ACS, hoặc forwarded headers bị spoof.

**13. Vì sao không thể test Audience bằng cách thay XML sau khi IdP đã ký?**  
Vì chữ ký sẽ sai; test phải build giá trị Audience sai trước khi IdP test ký và encrypt.

**14. SAML signed assertion đã hết hạn có thể dùng lại không?**  
Không. Conditions, SubjectConfirmationData time và replay guard vẫn phải đạt.

**15. Demo Java 17 trong bài có phải SAML implementation không?**  
Không. Nó minh họa JCA signature/AES-GCM và policy gates; Spring/OpenSAML phải xác minh SAML thực.

## 45. Checklist QA cuối cùng

- [ ] AuthnRequest được ký đúng binding và đúng SP signing key.
- [ ] IdP đã trust SP signing certificate và yêu cầu signed request như policy.
- [ ] SP signing private key bảo mật và không xuất hiện trong metadata.
- [ ] IdP sử dụng đúng SP public encryption certificate cho Assertion.
- [ ] SP có đúng decryption private key; XML Encryption algorithms được phê duyệt.
- [ ] IdP ký Response/Assertion đúng policy, SP verify bằng IdP verification credentials.
- [ ] Không dùng encryption-only thay authentication signature.
- [ ] Không lẫn signing, decryption và IdP verification keys.
- [ ] Spring SAML2 registrationId, SP entityID, IdP entityID và ACS chính xác.
- [ ] Destination, Recipient, AudienceRestriction được validate độc lập.
- [ ] Response/SubjectConfirmationData InResponseTo khớp pending AuthnRequest.
- [ ] RelayState và browser session binding được bảo vệ.
- [ ] Conditions timestamps, clock skew và replay validation được enforce.
- [ ] XML Signature Wrapping, XXE, oversized XML và malformed SAML bị reject.
- [ ] Reverse proxy trusted forwarding, HTTPS public ACS và cookie policies đúng.
- [ ] Mỗi IdP/tenant có proper registration/keys/source identity namespace.
- [ ] NameID/attributes chỉ được dùng sau full protocol validation.
- [ ] Group/GrantedAuthority và tenant/object permissions do app kiểm.
- [ ] Key rotation và compromised-key removal được diễn tập.
- [ ] Test suites có signed fixtures cho wrong Recipient/Audience/InResponseTo.
- [ ] Positive tests chứng minh cả authentication và đúng local account.
- [ ] Negative tests chứng minh không tạo SecurityContext authenticated.
- [ ] Không log raw SAML assertions, keys hoặc session cookies.
- [ ] Có monitoring mismatch/decryption/signature/replay và canary rollback.
- [ ] Đã đối chiếu API/properties với Spring Boot/Security BOM thật.

## 46. Kết luận

Để mở rộng bài thực hành SAML2 SSO từ “đăng nhập chạy được” sang “đăng nhập được ràng buộc đúng trust context”, hãy ghi nhớ:

**SP ký AuthnRequest → IdP xác minh request → IdP ký và mã hóa Assertion cho SP → SP verify đúng IdP, giải mã bằng SP private key → kiểm chính xác Destination + Recipient + AudienceRestriction + InResponseTo + thời hạn + replay → xác định verified principal → application authorization.**

**Chữ ký chứng minh nguồn/toàn vẹn theo trust**, **mã hóa bảo vệ bí mật**, còn **Destination/Recipient/AudienceRestriction/InResponseTo chứng minh assertion dành cho đúng bên và đúng giao dịch**. Không một lớp riêng lẻ nào thay thế những lớp khác.

Spring Security hỗ trợ ký AuthnRequest qua `Saml2WebSsoAuthenticationRequestFilter`/registration signing credentials và giải mã `EncryptedAssertion` qua `OpenSaml5AuthenticationProvider`/SP decryption credentials, nhưng **cấu hình đúng IdP signing cert, metadata, SP entityID, ACS URL và kiểm thử bảo mật vẫn là trách nhiệm của đội triển khai**. Khi sai bên nhận hoặc sai chữ ký, **fail closed**, không lùi về cách bỏ validator.

### Tài liệu tham khảo chính thức

- Spring Security — SAML2 Login Overview, RelyingPartyRegistration, signing/decryption credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Producing AuthnRequests, signed Redirect/POST, signing keys: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating Responses, decryption and protocol validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML2 Metadata publishing and trust: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot — SAML2 relyingparty signing/decryption/verification properties: https://docs.spring.io/spring-boot/reference/security/saml2.html
- Spring Security — SAML2 Login sample and dependencies: https://docs.spring.io/spring-security/reference/servlet/saml2/login/
- OASIS SAML V2.0 Technical Overview: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
- OASIS SAML V2.0 Bindings: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS SAML V2.0 Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML V2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- W3C XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
- W3C XML Encryption Syntax and Processing 1.1: https://www.w3.org/TR/xmlenc-core1/
- OWASP — SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
