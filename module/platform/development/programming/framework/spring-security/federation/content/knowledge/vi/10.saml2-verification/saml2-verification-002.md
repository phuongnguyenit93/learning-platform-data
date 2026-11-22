# Xác minh chữ ký bằng khóa của đúng nhà cung cấp danh tính trong SAML 2.0

Trong SAML 2.0 federation, **Service Provider (SP/Relying Party)** không chỉ cần biết chữ ký của một SAML Response có khớp với **một public key nào đó** hay không. Nó phải chứng minh public key dùng để xác minh **thuộc đúng Identity Provider (IdP/Asserting Party) đã được cấu hình và kỳ vọng cho lần đăng nhập này**. Sau đó ứng dụng vẫn phải kiểm tra Issuer, Audience, Recipient, thời hạn, InResponseTo và quyền truy cập.

**Quy tắc cốt lõi:** Không được thử mọi khóa thuộc mọi IdP đã đăng ký rồi chấp nhận chữ ký đầu tiên hợp lệ. Cần gắn đúng bộ khóa tin cậy với một **RelyingPartyRegistration**, xác minh SAML message trong registration đó và từ chối khi issuer, bên nhận hoặc ngữ cảnh tenant không khớp.

Bài học tập trung vào luồng Web Browser SSO với **Spring Security SAML2 Login**. Ví dụ Java 17 minh họa xác minh chữ ký bằng đúng public key; phần triển khai SAML thật sử dụng Spring Security/OpenSAML, không tự xây trình phân tích XML Signature.

## 1. Vì sao chữ ký hợp lệ chưa đủ chứng minh đúng IdP?

Giả sử một Portal hỗ trợ hai IdP:

| Liên kết | Registration ID | IdP entity ID | Khóa công khai được phép |
| --- | --- | --- | --- |
| Nhân viên nội bộ | company-a | https://login-a.example.test/saml | Key-A |
| Khách hàng đối tác | company-b | https://login-b.example.test/saml | Key-B |

Một người dùng của IdP B không tự động có quyền đăng nhập vào khu vực chỉ dành cho nhân viên A. Nếu code kiểm thử Key-A rồi Key-B cho cùng một Response và cho đăng nhập khi **bất kỳ** khóa nào hợp lệ, hệ thống có thể bị **cross-IdP token substitution** hoặc nhầm tenant. Kẻ tấn công không nhất thiết phải phá mật mã; chỉ cần lợi dụng lỗi gắn danh tính IdP/khóa với ngữ cảnh sử dụng.

Một SAML login được chấp nhận khi các lớp kiểm tra cùng thành công:

1. **Registration selection:** SP xác định cặp SP–IdP nào được phép xử lý request hiện tại.
2. **Cryptographic verification:** chữ ký bảo vệ đúng Response/Assertion, kiểm tra bằng khóa đáng tin **của IdP nằm trong registration đó**.
3. **Identity binding:** Issuer của message khớp IdP entity ID đã cấu hình.
4. **Relying-party binding:** Response/Assertion dành cho đúng SP entity ID, ACS, Audience và Recipient.
5. **Time & request binding:** còn hiệu lực, không replay và đúng AuthnRequest khi có yêu cầu tương quan.
6. **Application authorization:** người dùng đã xác thực có quyền trên tenant/tài nguyên cụ thể.

**Chữ ký đúng bằng khóa của B nhưng Response tự nhận Issuer A phải bị từ chối**, dù B nằm trong một registration khác mà SP cũng hỗ trợ.

## 2. Mô hình tin cậy của khóa IdP trong Spring Security

~~~text
                   Quản trị viên/federation operator
                                |
                  Xác minh IdP metadata / cert
                                |
                 RelyingPartyRegistrationRepository
                                |
              +-----------------+------------------+
              |                                    |
          company-a                             company-b
      expected issuer A                    expected issuer B
      verify credentials A                  verify credentials B
      SP entity ID và ACS A                  SP entity ID và ACS B
              |                                    |
              +------------------+-----------------+
                                 |
                        Browser POST SAMLResponse
                                 |
                   Chọn registration phù hợp
                   dựa vào ngữ cảnh tin cậy
                                 |
                Kiểm tra chữ ký với khóa IdP đó
                                 |
                So Issuer, Audience, Recipient...
                                 |
                         PASS -> Authentication
                         FAIL -> Reject
~~~

Các khái niệm cần phân biệt:

- **registrationId** là tên nội bộ, chẳng hạn company-a; không nhất thiết bằng SAML entity ID.
- **IdP entity ID** là định danh protocol mà SP kỳ vọng ở Issuer của response/assertion.
- **verificationX509Credentials** phía asserting party chứa các certificate được cho phép để xác minh thông điệp IdP.
- **SP signing credentials** chứa private key dùng ký AuthnRequest nếu IdP yêu cầu; **không phải khóa để SP xác minh chữ ký IdP**.
- **SP decryption credentials** chứa private key giải mã EncryptedAssertion khi cần; cũng **không phải khóa xác minh chữ ký IdP**.

Repository chứa cấu hình tin cậy, không xác thực trực tiếp người dùng. Spring Security/OpenSAML dùng registration đã được giải quyết để xử lý SAMLResponse.

## 3. XML Signature thực sự kiểm tra những gì?

SAML 2.0 thường dựa trên **XML Signature (XMLDSig)**. Một chữ ký gồm SignedInfo, các Reference, DigestValue, SignatureValue và có thể có KeyInfo.

| Thành phần | Vai trò |
| --- | --- |
| SignedInfo | Cấu trúc thông tin được ký, thuật toán canonicalization và chữ ký |
| Reference URI | Chỉ định XML object được bảo vệ; thường tham chiếu ID của Response hoặc Assertion |
| Transforms, Canonicalization | Chuẩn hóa XML và biến đổi dữ liệu trước khi băm/ký |
| DigestValue | Băm dữ liệu thực sự được Reference trỏ đến |
| SignatureValue | Chữ ký số tính trên SignedInfo đã canonicalize |
| KeyInfo | Có thể mang certificate hoặc gợi ý khóa; **không tự đáng tin** |

Một mảnh cấu trúc minh họa (không phải SAMLResponse hợp lệ):

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_response-a"
    Destination="https://portal.example.test/login/saml2/sso/company-a">
  <saml:Issuer>https://login-a.example.test/saml</saml:Issuer>
  <ds:Signature>
    <ds:SignedInfo>
      <ds:Reference URI="#_response-a">
        <!-- các thuật toán và digest được lược bỏ -->
      </ds:Reference>
    </ds:SignedInfo>
    <!-- SignatureValue được lược bỏ -->
  </ds:Signature>
  <saml:Assertion ID="_assertion-a">
    <saml:Issuer>https://login-a.example.test/saml</saml:Issuer>
    <!-- Subject, Conditions, AuthnStatement được lược bỏ -->
  </saml:Assertion>
</samlp:Response>
~~~

**Không gửi mảnh XML trên để đăng nhập:** nó thiếu các trường bắt buộc, digest, signature và nội dung assertion. Ví dụ chỉ chỉ ra Reference và vị trí phần tử.

Hai phép kiểm tra độc lập bắt buộc:

- **Mật mã:** SignatureValue, Reference/digest và transforms phải hợp lệ cho đúng XML object.
- **Tin cậy:** public key được dùng phải nằm trong bộ verification credentials được phê duyệt **của IdP mà SP đang kỳ vọng**.

Kết quả cryptographic verify = true với một khóa chưa được tin cậy **không** cho phép tạo principal. Việc tìm thấy certificate trong XML không biến certificate đó thành IdP trusted key.

## 4. Phân biệt các chữ ký và hướng sử dụng khóa

| Loại chữ ký | Người ký thường gặp | Ai kiểm tra? | Khóa tin cậy dùng để kiểm tra |
| --- | --- | --- | --- |
| SAML Response signature | IdP | SP | Signing certificate công khai của **đúng IdP** |
| SAML Assertion signature | IdP | SP | Signing certificate công khai của **đúng IdP** |
| IdP metadata signature | IdP/federation operator | SP | Metadata trust anchor được cấu hình trước |
| AuthnRequest signature | SP | IdP | Signing certificate công khai của SP |
| SP metadata signature | SP/federation operator | IdP | Trust anchor phía tiêu thụ metadata |

**TLS certificate** của website IdP thường bảo vệ kết nối HTTPS; nó có thể khác certificate ký SAML. Kiểm tra HTTPS thành công không tự xác minh XML signature của SAML Response.

**EncryptedAssertion** cần SP private key để giải mã, rồi cần tiếp tục xác minh nội dung đã ký và các điều kiện liên quan. Encryption không thay chữ ký số hoặc authorization.

### Response ký, Assertion ký, hay cả hai?

Theo mô tả luồng OpenSAML của Spring Security, provider kiểm tra chữ ký Response khi có, các chữ ký Assertion khi có và từ chối trường hợp không có chữ ký phù hợp. Một cấu hình có thể dựa vào Response-signed hoặc signed assertions tùy profile; **không có quy tắc rằng mọi IdP luôn phải ký cả hai lớp**.

Tuy nhiên chính sách của tổ chức có thể nghiêm hơn:

- Yêu cầu Response phải ký.
- Yêu cầu mọi Assertion được sử dụng phải được ký.
- Yêu cầu cả hai khi triển khai nhạy cảm.
- Từ chối bất cứ chữ ký nào được trình bày mà không hợp lệ.

Khi có nhiều Assertion, ứng dụng không được lấy dữ liệu đăng nhập từ một Assertion chưa được bảo vệ/kiểm chứng. **Thư viện phải dùng đúng object thuộc phạm vi chữ ký**, tránh đọc nhầm phần tử.

## 5. Khóa được lấy từ đâu để được coi là đáng tin?

Phương án phổ biến:

1. **IdP metadata XML** được tải từ nguồn đã phê duyệt và thẩm định theo chính sách federation.
2. **Certificate pinned** được quản trị viên xác thực qua kênh độc lập rồi đưa vào cấu hình ứng dụng.
3. **Kho cấu hình nội bộ** giữ danh sách certificate được phép theo từng IdP entity ID và có audit/rotation.

Một phần metadata có thể chứa cấu trúc:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo>
      <ds:X509Data>
        <ds:X509Certificate>
          <!-- certificate Base64 của IdP được lược bỏ -->
        </ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
</md:IDPSSODescriptor>
~~~

Đây là **đoạn cấu trúc**, chưa phải metadata đầy đủ: thiếu EntityDescriptor/entityID, SSO endpoint, certificate thật.

**Nguồn tin cậy nằm ở quy trình xác minh metadata**, không nằm ở việc XML tự chứa một public key. Nếu kẻ tấn công có thể thay metadata và SP tự động tin mọi certificate mới, kẻ tấn công có thể thay trust root rồi tự ký SAMLResponse.

- Nếu dùng metadata qua HTTPS, cần xác minh URL/host và TLS từ nguồn đã được phê duyệt.
- Nếu federation yêu cầu metadata XML có chữ ký, xác minh bằng **metadata-signing trust anchor riêng** được thiết lập trước, không tự tin key nằm ngay trong metadata.
- Nếu ứng dụng lấy metadata từ cơ sở dữ liệu, quản lý quyền cập nhật, integrity, audit và thời hạn/rotation.
- Trong chính SAMLResponse, **ds:KeyInfo chỉ là dữ liệu bên gửi cung cấp**; có thể dùng để gợi ý lựa chọn khóa từ danh sách đã tin, **không được coi là trust anchor tự động**.

Nhiều certificate SAML được tin dựa trên pinning/federation metadata chứ không nhất thiết nằm trong chuỗi public WebPKI CA. Đánh giá certificate phải theo **trust policy cụ thể**, không chỉ bằng kiểm tra nó có self-signed hay không.

## 6. Chọn đúng registration trước khi xác minh

Trong SP-initiated login, một quy trình an toàn thường như sau:

~~~text
1. Browser vào /saml2/authenticate/company-a
2. SP lấy registration company-a
3. SP tạo AuthnRequest, lưu request ID + registration context
4. Browser đến IdP A, người dùng xác thực
5. IdP A trả SAMLResponse về ACS
6. SP resolve registration theo request/state đáng tin
7. Xác minh chữ ký bằng verification credentials của IdP A
8. Xác nhận issuer A, audience SP A, recipient ACS, thời gian
9. Kiểm tra InResponseTo, subject confirmation, replay
10. Thành công mới tạo Authentication và xét quyền nghiệp vụ
~~~

**Không dùng Issuer từ dữ liệu chưa xác thực để tự tải khóa mới trên Internet.** Trong vài luồng, Spring Security có thể đọc Issuer để **tìm một candidate registration trong tập đã cấu hình**, nhưng bước signature validation phải chứng minh khóa thật sự thuộc IdP của candidate đó; chỉ đọc Issuer chưa tạo trust.

**IdP-initiated SSO:** có thể không có AuthnRequest/InResponseTo tương quan. Nếu cho phép, cần chính sách explicit về registration selection, issuer, audience, recipient, replay và bảo vệ login CSRF. Đừng đơn giản bỏ toàn bộ kiểm tra request-binding để “login chạy được”.

**IdP issuer trùng giữa hai registrations:** nếu nhiều SP entity ID hoặc tenant dùng cùng một IdP, chỉ đọc Issuer không đủ để chọn duy nhất registration; cần ngữ cảnh request, audience/recipient và tenant mapping đáng tin.

## 7. Cấu hình Spring Boot: gắn certificate riêng cho từng IdP

Ví dụ **Spring Boot 3.x / Spring Security 6.x** trong application.yml:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          company-a:
            assertingparty:
              entity-id: "https://login-a.example.test/saml"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/company-a.crt"
              singlesignon:
                url: "https://login-a.example.test/sso"
                sign-request: false
          company-b:
            assertingparty:
              entity-id: "https://login-b.example.test/saml"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/company-b.crt"
              singlesignon:
                url: "https://login-b.example.test/sso"
                sign-request: false
~~~

**Ý nghĩa:**

- **company-a** và **company-b** là registration IDs của hai cặp SP–IdP.
- **assertingparty.entity-id** định nghĩa issuer IdP được kỳ vọng.
- **verification.credentials.certificate-location** chỉ tới public certificate IdP tương ứng; đây là nguồn khóa SP dùng kiểm tra chữ ký assertion/response.
- **singlesignon.url** là endpoint gửi AuthnRequest của IdP.
- **sign-request: false** chỉ có nghĩa mẫu này giả định IdP **không yêu cầu SP ký AuthnRequest**; nó **không vô hiệu hóa xác minh chữ ký của IdP khi trả SAMLResponse**.

Điều kiện hoạt động: cần dependency Spring Web/Security/SAML service provider, certificate X.509 thật ở đường dẫn resources, SP Entity ID/ACS đăng ký tại IdP và IdP hỗ trợ cấu hình đã khai báo. Domain example.test chỉ minh họa; không thể đăng nhập thật nếu chưa thay thế và thiết lập IdP. Với Spring Boot version khác, kiểm tra property namespace theo tài liệu của phiên bản đó.

Nếu IdP cung cấp metadata đã thẩm định, có thể cấu hình **assertingparty.metadata-uri** thay cho khai báo từng issuer, SSO endpoint và certificate, nhưng **metadata phải đúng IdP và có nguồn tin cậy**.

### So sánh trường hợp hợp lệ và không hợp lệ

| Tình huống | Registration dự kiến | Kết luận |
| --- | --- | --- |
| Issuer A, ký bởi A, đúng Audience/Recipient, còn hạn | company-a | Có thể đăng nhập sau mọi kiểm tra khác |
| Issuer A, ký bởi B | company-a | **Từ chối** dù B cũng là IdP đã cấu hình |
| Issuer B, ký bởi B, nhưng Response dành cho SP A | company-b | **Từ chối** vì audience/recipient không hợp lệ |
| Issuer A, ký bởi A nhưng response hết hạn | company-a | **Từ chối** vì chữ ký không thay kiểm tra thời gian |
| Issuer A, ký bởi A nhưng không có quyền tenant | company-a | Có thể xác thực danh tính, nhưng **không cấp quyền tenant** |

## 8. Cấu hình Java: RelyingPartyRegistration và verificationX509Credentials

Một cách khác là tạo bean repository bằng Java. Ví dụ bên dưới dành cho **ứng dụng Spring Boot 3.x, Spring Security 6.x, Java 17+**, dùng các certificate thật trong resources:

Tệp **src/main/java/com/example/security/SamlTrustConfig.java**:

~~~java
package com.example.security;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlTrustConfig {

    private static X509Certificate readCert(Resource resource)
            throws Exception {
        try (InputStream in = resource.getInputStream()) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }
    }

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations(
            @Value("classpath:saml/company-a.crt") Resource certA,
            @Value("classpath:saml/company-b.crt") Resource certB)
            throws Exception {

        Saml2X509Credential verifyA =
                Saml2X509Credential.verification(readCert(certA));
        Saml2X509Credential verifyB =
                Saml2X509Credential.verification(readCert(certB));

        RelyingPartyRegistration a = RelyingPartyRegistration
            .withRegistrationId("company-a")
            .assertingPartyMetadata(party -> party
                .entityId("https://login-a.example.test/saml")
                .singleSignOnServiceLocation(
                    "https://login-a.example.test/sso")
                .wantAuthnRequestsSigned(false)
                .verificationX509Credentials(c -> c.add(verifyA)))
            .build();

        RelyingPartyRegistration b = RelyingPartyRegistration
            .withRegistrationId("company-b")
            .assertingPartyMetadata(party -> party
                .entityId("https://login-b.example.test/saml")
                .singleSignOnServiceLocation(
                    "https://login-b.example.test/sso")
                .wantAuthnRequestsSigned(false)
                .verificationX509Credentials(c -> c.add(verifyB)))
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(a, b);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Mẫu này **không phải Java standalone** để chạy bằng lệnh javac/java vì cần Spring Boot, Spring Security SAML module, certificate thật và IdP đang hoạt động. Không có stdout cố định. Khi triển khai, phải cấu hình SP Entity ID, ACS, key ký AuthnRequest hoặc key giải mã assertion nếu IdP yêu cầu.

Giải thích điểm mấu chốt:

1. **CertificateFactory** chỉ phân tích tệp X.509; **không tự chứng minh** tệp đó được lấy từ đúng IdP. Kiểm soát nguồn certificate là trách nhiệm cấu hình và vận hành.
2. **Saml2X509Credential.verification** đánh dấu chứng thư dùng làm verifying credential, không phải private key ký request.
3. **company-a** chỉ nhận **verifyA** trong asserting-party metadata của A; tương tự company-b với **verifyB**.
4. **InMemoryRelyingPartyRegistrationRepository** lưu các registrations trong memory; nó **không tự tải lại** certificates khi IdP xoay khóa.
5. **saml2Login** để các thành phần Spring Security/OpenSAML giải mã và xác minh SAML đúng giao thức; không tự tạo một XMLSignatureValidator đơn giản để thay thế.

**Đây là lựa chọn thay thế cho cấu hình Boot properties**, không nên khai báo cả hai rồi giả định Spring sẽ tự hợp nhất mọi registration.

## 9. Metadata signature và Response signature là hai ranh giới tin cậy

Kẻ tấn công không cần đánh bại RSA nếu có thể khiến SP tin vào một **metadata XML giả** chứa public key mà kẻ tấn công kiểm soát. Khi đó attacker tự ký SAMLResponse bằng private key tương ứng, và phép kiểm tra signature sẽ thành công với key giả nếu SP đã nhận nó làm trusted key.

Quy trình tin cậy đúng:

~~~text
Nguồn metadata IdP được quản trị viên phê duyệt
                    |
       Kiểm tra transport/source/signature
       theo chính sách federation
                    |
        Metadata đúng entityID và còn hợp lệ
                    |
          Lấy signing KeyDescriptor
                    |
         RelyingPartyRegistration
                    |
      Verification credentials của đúng IdP
                    |
       Kiểm tra SAML Response / Assertion
~~~

- **Xác minh metadata:** trả lời “bộ khóa và endpoint này có thật sự được phép đại diện cho IdP đó không?”.
- **Xác minh Response/Assertion:** trả lời “SAML message hiện tại có được ký bằng một khóa đang được phép của IdP không, và có được phát cho đúng SP không?”.
- **Xác minh TLS:** trả lời “kênh HTTPS đến metadata/IdP endpoint có phù hợp certificate và hostname đã kiểm tra không?”.

Ba câu hỏi không thay thế nhau.

Spring Security hỗ trợ quản lý asserting-party metadata; một số phiên bản có **OpenSaml5AssertingPartyMetadataRepository** với verificationCredentials để kiểm tra XML metadata signature. **Nếu không cấu hình verification credentials theo API đó, không được tự giả định XML metadata signature được kiểm tra.** Khi metadata được tin nhờ một kênh nội bộ/HTTPS đáng tin theo policy, cần ghi nhận rõ mô hình trust. Không lấy public key từ response KeyInfo hoặc URL do người dùng cung cấp để tự xây trust.

## 10. XML Signature Wrapping: một chữ ký đúng nhưng principal sai

**XML Signature Wrapping (XSW)** lợi dụng tình huống ứng dụng xác minh chữ ký của XML object A nhưng lại đọc các thuộc tính đăng nhập từ XML object B không được ký.

Ví dụ mô tả nguyên lý, **không phải payload thực thi**:

~~~text
SAMLResponse
  Assertion A: subject = employee, có chữ ký hợp lệ
  Assertion B: subject = admin, chưa được ký
  Signature Reference: trỏ tới Assertion A

Implementation lỗi:
  verify(A) = true
  -> XPath lấy phần tử B
  -> tạo principal admin
~~~

Biện pháp phòng tránh:

- Sử dụng Spring Security/OpenSAML đã cập nhật thay vì tự viết parser chữ ký.
- Xác định chính xác XML object được Signature Reference bảo vệ, kiểm tra ID uniqueness và không chấp nhận references bất thường.
- Chỉ sử dụng subject/attributes từ **các assertions được thư viện xác minh đúng trong bối cảnh**.
- Chặn DTD, external entity expansion, XML parser attacks và transforms không được phép theo chính sách.
- Với nhiều assertions, bảo đảm mọi dữ liệu sử dụng nằm trong vùng được bảo vệ bằng chữ ký hợp lệ.
- Không chỉ tìm phần tử Assertion đầu tiên bằng XPath rồi cho rằng nó đã được xác minh vì có một SignatureValue hợp lệ ở đâu đó trong tài liệu.

**Chữ ký đúng bằng key đúng vẫn chưa đủ** nếu code sử dụng nội dung không nằm trong phạm vi chữ ký được kiểm tra.

## 11. Key rollover: có thể tin nhiều khóa nhưng chỉ của cùng IdP

Một IdP có thể công bố signing certificate hiện tại và certificate kế tiếp trong giai đoạn xoay khóa.

| Giai đoạn | Keys được phép của IdP A | Điều kiện |
| --- | --- | --- |
| Trước rotation | A-old | Khóa cũ đang hoạt động |
| Giai đoạn chuyển tiếp | A-old và A-new | Hai keys đã được xác minh theo metadata/trust policy |
| Sau rotation | A-new | Khóa cũ đã được thu hồi khỏi trust config |

**Không dùng Key-B của IdP B để chữa lỗi chữ ký của IdP A.** Dù cùng một SP quản lý hai IdP, tập keys cần ràng buộc theo asserting party.

Quy trình an toàn:

1. IdP/federation operator thông báo thay khóa qua kênh đã được quản trị phê duyệt.
2. SP lấy metadata/cert mới từ nguồn đáng tin, xác minh entityID, certificate, KeyDescriptor và metadata trust policy.
3. Thêm key mới vào đúng registration A, triển khai đồng nhất trên các instance và kiểm thử.
4. Khi IdP bắt đầu ký bằng A-new, xác minh Response/Assertion bằng key mới và vẫn kiểm tra audience/issuer/time.
5. Đến thời điểm agreed cutover, bỏ A-old sau khi xác nhận IdP không còn sử dụng.
6. Ghi audit và alert thay đổi fingerprint bất ngờ; không tự động tin KeyInfo trong SAMLResponse.

Metadata **validUntil** và ngày hết hạn X.509 certificate là các thời điểm khác nhau; không tự dùng một mốc thay cho mốc kia. Khi metadata đã hết hiệu lực theo chuẩn, cần làm mới trust material; khi chứng thư bị thu hồi khỏi trust policy, không giữ nó vô thời hạn dù app vẫn có session.

## 12. Java 17 độc lập: khóa đúng xác minh được, khóa sai thì không

Ví dụ dùng **JDK 17+** để minh họa chữ ký RSA/SHA-256 trên byte array. Nó **không phải trình kiểm tra SAML XML Signature**: phần XML canonicalization, Signature Reference, metadata/trust và assertion validation phải thực hiện bằng Spring Security/OpenSAML.

Tạo **CorrectIdpKeyDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;

public class CorrectIdpKeyDemo {
    static byte[] sign(byte[] data, KeyPair pair)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initSign(pair.getPrivate());
        s.update(data);
        return s.sign();
    }

    static boolean verify(byte[] data, byte[] signature,
                          PublicKey trusted)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initVerify(trusted);
        s.update(data);
        return s.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair idpA = generator.generateKeyPair();
        KeyPair idpB = generator.generateKeyPair();

        byte[] data = "issuer=A;subject=user123"
                .getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(data, idpA);
        byte[] modified = "issuer=A;subject=admin"
                .getBytes(StandardCharsets.UTF_8);

        System.out.println("Correct IdP key: "
                + verify(data, signature, idpA.getPublic()));
        System.out.println("Wrong IdP key: "
                + verify(data, signature, idpB.getPublic()));
        System.out.println("Modified data: "
                + verify(modified, signature, idpA.getPublic()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CorrectIdpKeyDemo.java
java CorrectIdpKeyDemo
~~~

**Stdout chính xác**:

~~~text
Correct IdP key: true
Wrong IdP key: false
Modified data: false
~~~

**Giải thích:**

- Chữ ký do IdP A tạo có thể được xác minh bằng public key A.
- Public key B không xác minh được cùng chữ ký.
- Khi sửa dữ liệu đã ký thành subject admin, phép kiểm tra thất bại kể cả dùng đúng key A.
- Bộ khóa trong ví dụ được tạo ngẫu nhiên lúc chạy và chỉ lưu trong memory; ba kết quả boolean vẫn cố định.
- Trong SAML production còn phải chứng minh **public key A thuộc đúng IdP A** qua trusted metadata/registration, rồi so issuer, audience, recipient và các điều kiện khác. Không sử dụng hàm verify này để kiểm chứng raw SAMLResponse.

## 13. Spring Security xác minh ở bước nào?

Luồng Servlet SAML2 Login điển hình:

1. **Saml2WebSsoAuthenticationFilter** nhận SAMLResponse tại ACS.
2. **Saml2AuthenticationTokenConverter** trích xuất message và giải quyết **RelyingPartyRegistration** phù hợp.
3. Authentication provider dựa trên **OpenSAML** kiểm tra signature, xử lý encrypted elements khi có, so issuer/destination và kiểm tra assertions/subject conditions theo profile.
4. Sau khi thành công, Spring tạo **Saml2Authentication** và **Saml2AuthenticatedPrincipal**.
5. **AuthorizationFilter**, method security và logic nghiệp vụ quyết định quyền thực tế.

Tài liệu Spring Security 7.x gọi **OpenSaml5AuthenticationProvider**; các bản 6.x có thể dùng provider khác theo version và dependency. Vì vậy kiểm tra docs và Javadoc theo bản đang chạy trước khi custom authentication provider.

Một SecurityFilterChain cơ bản, **không tự can thiệp signature verifier**:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .build();
}
~~~

Đây là **đoạn cấu hình trong class Spring**, không biên dịch độc lập bằng javac nếu thiếu dự án/dependencies, và không có stdout cố định.

Khi cần thay đổi:

- **Certificate trust:** cập nhật verificationX509Credentials của đúng IdP.
- **Registration selection:** cấu hình SAML token converter / registration resolver theo version, giữ nguyên ràng buộc session/request và tenant.
- **Additional assertion validation:** dùng extension points Spring Security/OpenSAML đúng phiên bản và **không vô hiệu hóa các bước kiểm chứng mặc định**.
- **Metadata refresh:** dùng cách quản trị certificate/metadata đã được tin và cập nhật repository. InMemory repository không tự polling keys.

## 14. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Message Issuer A nhưng chữ ký chỉ đúng với B | Sai trust binding hoặc giả mạo | Từ chối, không thử keys của tất cả IdP |
| Đột nhiên signature invalid sau certificate rotation | SP vẫn giữ cert cũ | Xác minh cert mới từ IdP, cập nhật đúng registration |
| Một instance login được, instance khác không | Tập keys chưa đồng bộ | Kiểm tra rollout metadata/certs ở mọi instance |
| Metadata chứa cert mới nhưng nguồn không được tin | Tấn công thay trust hoặc cấu hình yếu | Không đưa cert vào trust cho đến khi xác minh provenance |
| Response ký hợp lệ nhưng Audience sai | Message dành cho SP khác | Từ chối, so SP entityID và IdP registration |
| Signature hợp lệ nhưng hết NotOnOrAfter | Assertion quá hạn | Từ chối, kiểm tra clock skew có giới hạn |
| InResponseTo không khớp | Mất session request / correlation hoặc login injection | Xem request repository, browser session và ACS |
| SAMLResponse không có chữ ký phù hợp | IdP không ký hoặc policy lệch | Sửa IdP/SP signing configuration, không tắt signature validation |
| XML có signed assertion và unsigned assertion khác | XML Signature Wrapping hoặc multi-assertion mishandling | Không đọc assertion chưa được bảo vệ, kiểm tra thư viện |
| IdP certificate tự ký | Chưa có đủ thông tin để kết luận | Xem cert có được trust policy phê duyệt không |
| Xác thực SAML thành công nhưng nhận HTTP 403 | Không đủ role/tenant/quyền tài nguyên | Xử lý authorization riêng, không thay signature policy |

**Ghi log an toàn:** registrationId, expected IdP entityID, fingerprint SHA-256 của certificate được tin, thời gian, correlation ID và lỗi đã lọc. Không log private keys, raw assertions chứa thông tin cá nhân, SAMLResponse nguyên bản hoặc session cookies trong production.

## 15. Ma trận kiểm thử bảo mật

| Case | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| A | Issuer A, ký A, audience/recipient/time đúng | Signature pass, sau đó các điều kiện khác pass |
| B | Issuer A nhưng ký B | **Reject** |
| C | Issuer A và ký A nhưng Audience của SP khác | **Reject** |
| D | Issuer A và ký A nhưng quá hạn | **Reject** |
| E | Certificate bất kỳ từ KeyInfo, chưa thuộc trusted registration | **Reject** |
| F | Metadata chứa certificate mới từ nguồn giả | **Reject metadata**, không thay trust |
| G | IdP A đang rollover A-old/A-new đã được phê duyệt | Hai keys có thể dùng đúng trong transition |
| H | Response bị thay nội dung sau khi ký | **Reject** do signature/digest mismatch |
| I | XML Signature Wrapping làm principal lấy từ unsigned assertion | **Reject/không dùng object chưa ký** |
| J | Hai registrations cùng issuer, khác tenant/ACS | Không chọn tùy tiện; kiểm tra request context và audience |
| K | IdP-initiated không có InResponseTo | Chỉ chấp nhận nếu policy riêng cho phép và kiểm tra khác đầy đủ |
| L | SAML login hợp lệ nhưng user không có quyền tenant | **Reject ở authorization** |

Các kiểm thử nên chạy trên môi trường staging với **IdP thật hoặc test IdP**, trong đó chứng thư, metadata, SP Entity ID, ACS, binding và chính sách ký được thiết lập rõ ràng. Có thể viết unit test kiểm tra mapping registration/cert, nhưng **test mock một phương thức verify = true không thay thế được integration test SAML**.

## 16. Câu hỏi tự đánh giá

**1. Có thể lấy public key từ ds:KeyInfo của Response và tin ngay không?**  
Không. KeyInfo là nội dung do bên gửi cung cấp; phải đối chiếu với keys đã được phê duyệt của đúng asserting party.

**2. IdP B cũng được cấu hình trong Portal. Có thể dùng key B để xác minh Response tự nhận Issuer A không?**  
Không. Khóa phải thuộc đúng registration/IdP đã chọn.

**3. Chữ ký Response hợp lệ có đủ để bỏ AudienceRestriction không?**  
Không. Message có thể được ký hợp lệ nhưng phát cho SP khác.

**4. Certificate TLS của URL IdP có bắt buộc là certificate ký SAML không?**  
Không. Chúng phục vụ các mục đích khác nhau.

**5. Tại sao có thể cần nhiều keys cho cùng một IdP?**  
Để thực hiện key rollover có kiểm soát; chỉ tin các keys đã được phê duyệt trong khoảng chuyển tiếp.

**6. Tại sao metadata signature khác message signature?**  
Metadata giúp SP xác định **bộ khóa/endpoint được phép**, còn message signature xác minh **SAML Response/Assertion hiện tại**.

**7. Nếu có signature hợp lệ trên Assertion A nhưng code đọc Assertion B chưa được ký thì sao?**  
Không được chấp nhận; đó là vấn đề signed-object binding/XML Signature Wrapping.

**8. Đăng nhập qua IdP A có tự cấp quyền quản trị trong tenant A không?**  
Không. Authentication và authorization là hai lớp kiểm tra khác nhau.

## 17. Checklist triển khai production

- [ ] Mỗi registration có expected IdP entityID, SP entityID, ACS và verification credentials đúng.
- [ ] Certificates được lấy từ nguồn metadata/trust policy đã phê duyệt, không tự lấy từ KeyInfo của Response.
- [ ] Không thử keys từ tất cả IdP rồi chấp nhận kết quả đầu tiên hợp lệ.
- [ ] Dùng Spring Security/OpenSAML cập nhật, không tự viết XMLDSig verifier hoặc parser XPath cho principal.
- [ ] Kiểm tra chữ ký của Response/Assertion theo profile và policy, cùng signed-object binding.
- [ ] Kiểm tra Issuer, Audience, Destination, Recipient, InResponseTo, Conditions, SubjectConfirmation và replay.
- [ ] Phân biệt signing key của SP, verifying certificate của IdP và SP decryption key.
- [ ] Có metadata trust/expiry policy và kế hoạch cập nhật certificate/keys an toàn.
- [ ] Có quy trình rotation với overlap A-old/A-new khi được phê duyệt, không pha khóa của IdP B.
- [ ] Khi có nhiều IdP/tenant, chọn registration bằng context có kiểm chứng, không dựa vào URL do browser nhập tùy ý.
- [ ] Phòng tránh XML Signature Wrapping, duplicate XML IDs và XML parser attacks.
- [ ] Có kiểm thử signature invalid, issuer mismatch, audience mismatch, replay, multi-assertion và rotation.
- [ ] Bảo vệ dữ liệu cá nhân và private keys, không log SAMLResponse thô.
- [ ] Sau khi tạo Authentication, vẫn kiểm tra quyền role, tenant và tài nguyên cụ thể.

## 18. Kết luận

**Xác minh chữ ký SAML2 an toàn là xác minh bằng khóa của đúng IdP, trên đúng nội dung được ký, trong đúng ngữ cảnh SP–IdP.** Mối quan hệ giữa registrationId, IdP entity ID, bộ verification credentials, SAMLResponse issuer và audience phải rõ ràng, nhất là khi một ứng dụng hỗ trợ nhiều IdP/tenant.

Spring Security cung cấp cấu trúc RelyingPartyRegistration và OpenSAML để thực hiện các phép kiểm tra giao thức. Hãy dùng trust metadata đã thẩm định, cấu hình khóa theo từng asserting party, quản lý rotation và kiểm thử tình huống dùng sai IdP. **Signature hợp lệ không bao giờ thay thế kiểm tra audience, thời hạn, request correlation hoặc quyền nghiệp vụ.**

### Tài liệu chính thức

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Producing SAML AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- OASIS SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- W3C XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
