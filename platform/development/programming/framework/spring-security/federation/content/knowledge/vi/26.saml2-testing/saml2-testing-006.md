# Kiểm thử chữ ký sai, issuer sai và khóa không được tin cậy

**Module:** Spring Security – federation  
**Nhóm kiến thức:** Kiểm thử SAML2  
**Phạm vi:** SAML 2.0 Web Browser SSO, HTTP-POST tới ACS, Spring Boot 3.x, Spring Security 6.5.x, OpenSAML 4/5 theo phiên bản, Java 17+. Nội dung gồm kiểm thử âm có kiểm soát, cấu hình trust của Relying Party, ví dụ Java 17 chạy độc lập và khung kiểm thử tích hợp với MockMvc.

## 1. Mục tiêu học tập và chuẩn thành công

Sau bài này, bạn phải phân biệt và kiểm thử được **ba loại thất bại khác nhau**:

1. **Chữ ký sai:** XML hoặc SignatureValue bị sửa sau khi IdP ký, Reference/Digest không còn khớp, hoặc signature algorithm/transform không đạt chính sách. Một chữ ký hiện diện trong XML không đủ; quá trình kiểm tra mật mã trên **đúng phần tử được ký** phải thành công.
2. **Issuer sai:** XML được ký **hợp lệ bằng khóa tin cậy** nhưng Issuer của Response/Assertion không đúng Identity Provider được đăng ký cho luồng đó. Test này phải **cố ý tái ký** payload với khóa test tin cậy sau khi đổi Issuer, để tách rõ lỗi Issuer khỏi lỗi chữ ký.
3. **Khóa không được tin cậy:** XML được ký hợp lệ bằng khóa B do test kiểm soát, nhưng Service Provider (SP) chỉ cấu hình tin IdP signing key A. Ngay cả khi KeyInfo trong XML đính kèm public certificate B, SP **không được tự nâng B thành trust anchor**.

Điều kiện **PASS** của toàn bộ bài test không chỉ là “endpoint trả HTTP 400/401”. Một hệ thống SAML có thể trả 302 về trang login cho mọi lỗi. Để kết luận kiểm thử đúng, cần **positive control**: một Response hợp lệ do trusted IdP ký phải thực sự tạo được Authentication; sau đó từng negative case phải **không tạo Authentication, không lưu SecurityContext phiên mới, không cấp role và không truy cập tài nguyên bảo vệ**.

**Không dùng cùng một fixture sai cho mọi test.** Ví dụ XML expired, sai Audience hoặc thiếu InResponseTo có thể làm cả ba test trả lỗi mà không hề chứng minh signature/issuer/trust validation được thực thi.

## 2. Dữ liệu, thành phần và ba lớp kiểm tra khác nhau

Trong luồng SAML:

~~~text
Browser POST /login/saml2/sso/corp-idp
    SAMLResponse = Base64(XML)
              |
              v
Saml2WebSsoAuthenticationFilter
    -> Saml2AuthenticationTokenConverter
    -> RelyingPartyRegistration: corp-idp
              |
              v
OpenSAML authentication provider
    [A] XML parsing, signature/reference validation
    [B] trusted verification credential / issuer policy
    [C] Destination/Audience/Conditions/InResponseTo/Subject
              |
              v
Saml2Authentication / local authorization
    -> SecurityContext / authenticated session
~~~

Tên provider phụ thuộc phiên bản và dependencies: **OpenSaml4AuthenticationProvider** hoặc **OpenSaml5AuthenticationProvider**. Dòng Spring Security 6.5 có các APIs hỗ trợ OpenSAML 5; không viết test dựa trên giả định mọi Spring Boot 3 đều tự động chọn cùng một provider.

### Ba danh tính cần phân biệt

| Giá trị | Ví dụ | Được kiểm tra ở đâu? |
| --- | --- | --- |
| **IdP issuer/entity ID** | https://idp.example.test/metadata | Phải đúng asserting party đã đăng ký |
| **SP entity ID/Audience** | https://sp.example.test/metadata | AudienceRestriction/recipient policy của SP |
| **Signing key/certificate IdP** | cert A từ kênh onboarding tin cậy | Public key dùng kiểm tra XMLDSig |
| **ACS/Destination** | https://sp.example.test/login/saml2/sso/corp-idp | Đích tiếp nhận Response, cấu hình đúng |
| **Registration ID** | corp-idp | Chọn RelyingPartyRegistration của cặp SP–IdP |
| **NameID/Subject** | alice@example.test | Chỉ được tin sau SAML validation và local mapping |

**Issuer không phải Audience.** Nếu XML có Issuer “IdP đúng” nhưng Audience là một SP khác, đó là lỗi Audience chứ không phải kiểm thử Issuer. Nếu certificate B không được tin nhưng XML cũng sai Issuer, không thể dùng lỗi cuối cùng để chứng minh chính xác ranh giới nào đã chặn.

### SAML Response/Assertion có thể được ký khác nhau

Tùy IdP và policy, **Response** có thể được ký, **Assertion** có thể được ký, hoặc cả hai. Trong SAML Browser SSO, các quy tắc về phạm vi chữ ký và xác thực Assertion phụ thuộc profile, framework và IdP contract. Test phải xác định rõ **đối tượng có chữ ký**, phần tử được Signature Reference trỏ tới và Assertion được phép sử dụng sau xác minh.

Một Response đã ký bao trùm Assertion bên trong có thể cho phép kiểm tra integrity của Assertion theo profile. Một Assertion được ký riêng phải được xác minh bằng trusted IdP credentials. **Không có nghĩa mọi phần tử XML có cùng tên nhưng không nằm trong signed scope đều đáng tin.**

## 3. XMLDSig kiểm tra cái gì?

Chữ ký XML thường có:

- **SignedInfo**: CanonicalizationMethod, SignatureMethod, Reference.
- **Reference URI="#id"**: trỏ đúng Response hoặc Assertion có ID đã đăng ký.
- **Transforms**: ví dụ enveloped signature và canonicalization, không được tự thêm transforms nguy hiểm.
- **DigestMethod/DigestValue**: xác minh nội dung được tham chiếu không bị sửa.
- **SignatureValue**: giá trị signature của canonicalized SignedInfo với private key IdP.
- **KeyInfo/X509Data** (nếu có): thông tin về khóa mà tài liệu tự khai. **KeyInfo không phải trust anchor**.

~~~text
<samlp:Response ID="_resp123">
    <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>
    <ds:Signature>
        <ds:SignedInfo>
            <ds:Reference URI="#_resp123">
                ... digest/transforms ...
            </ds:Reference>
        </ds:SignedInfo>
        ... SignatureValue ...
        ... optional KeyInfo ...
    </ds:Signature>
    <saml:Assertion ID="_assert123">
        ... Subject, Conditions, AuthnStatement ...
    </saml:Assertion>
</samlp:Response>
~~~

**Đây là sơ đồ XML, không phải fixture có chữ ký hợp lệ.** Các phần rút gọn không dùng để test trực tiếp. Fixture thật phải có XML namespaces, IDs, timestamps, ACS, Conditions, signatures và SAML binding chuẩn, được tạo bởi một IdP test hoặc OpenSAML fixture factory.

Để kết luận “signature verified”, validator phải kiểm tra đúng Signature/Reference/Digest **trên đúng node được sử dụng**. Chữ ký hợp lệ của Assertion A không biến Assertion B khác thành an toàn. Đó là lý do các regression test nên có **XML Signature Wrapping**, duplicate IDs và unsigned sibling Assertion.

### Certificate trong KeyInfo có thể là lời tự khai

Nếu attacker tự tạo key pair B, ký Response bằng B rồi chèn certificate B vào KeyInfo, chữ ký có thể **tự nhất quán về mặt mật mã** khi dùng B để verify. Nhưng nếu IdP đã đăng ký chỉ dùng key A, **SP phải reject**. Không được lấy public key/certificate từ response rồi mặc định tin nó như IdP credential.

**Quy tắc:** Chọn verification credentials từ **RelyingPartyRegistration/metadata đã được tin theo chính sách**; không tạo trust anchor từ untrusted XML hoặc HTTP request.

## 4. Chuẩn bị phòng kiểm thử: baseline trước, negative sau

Một bộ fixtures tốt cần có:

- **IdP test có private key A**, chứng chỉ public A đã được SP tin cậy qua cấu hình out-of-band.
- **Private key B** được tạo riêng, **không** thuộc trust store của SP.
- Một **SP registration** với registrationId=corp-idp, IdP EntityID đúng, ACS/public URL đúng và key A.
- Đồng hồ hợp lý: IssueInstant/NotBefore/NotOnOrAfter mới cho mỗi test; không dùng assertion hết hạn.
- **Audience/Recipient/Destination** hợp lệ; SAML Status Success; NameID của test user đã được local app cho phép.
- Với **SP-initiated SSO**, tạo AuthnRequest thật và đảm bảo InResponseTo trỏ tới request ID còn được lưu trong cùng session. Nếu dùng IdP-initiated SSO thì phải theo policy cho unsolicited response; không tự giả định mọi cấu hình cho phép.
- Unique Response ID/Assertion ID mỗi lần; không dùng lại fixture gây replay failure.
- Chọn rõ chữ ký trên Response, Assertion hoặc cả hai theo production contract.
- Chuẩn bị **positive baseline fixture** và các negative fixtures dẫn xuất **từ cùng baseline hợp lệ**.

**Định danh ví dụ xuyên suốt:**

~~~text
registrationId:     corp-idp
IdP entityID:       https://idp.example.test/metadata
IdP login URL:      https://idp.example.test/sso
SP entityID:        https://sp.example.test/metadata
ACS:                https://sp.example.test/login/saml2/sso/corp-idp
trusted key:        idp-signing-A.pem
untrusted key:      other-idp-B.pem
subject:            alice@example.test
~~~

Các domain **example.test** dành cho tài liệu và test, không phải dịch vụ tồn tại. Key files ở ví dụ là **certificate công khai** phục vụ xác minh. Các private keys A/B chỉ đặt trong test IdP/fixture generator có quản lý, **không bao giờ cấp private key IdP cho SP production**.

### Positive control phải chứng minh điều gì?

Gửi một Response hợp lệ tới ACS qua cùng flow/session; đảm bảo:

1. XML decode và parsing hoàn tất.
2. Signature trên đúng node được verify bằng trusted cert A.
3. Issuer trùng IdP EntityID đã đăng ký.
4. Audience, Recipient, Destination, thời gian, InResponseTo và SubjectConfirmation đúng.
5. User principal được tạo từ Assertion đã validate.
6. Spring Security sinh Authentication, SecurityContext được lưu theo cơ chế session của app.
7. Follow-up GET endpoint bảo vệ với session đó có quyền theo local authorization.

Nếu baseline không thành công, **dừng đánh giá negative tests**. Mọi ca “unauthenticated” sau đó đều có thể là false positive do thiếu fixtures hoặc sai cấu hình.

## 5. Ca A: chữ ký sai (invalid signature)

**Đích test:** chứng minh SP không chấp nhận XML bị can thiệp hoặc SignatureValue/DigestValue không hợp lệ.

Một test cô lập:

1. Tạo Response hợp lệ cho đúng IdP/ACS/Audience/Subject, có valid XMLDSig của A.
2. Sau khi ký, **đổi một giá trị nằm bên trong signed Reference**, chẳng hạn NameID từ alice@example.test thành admin@example.test, **không ký lại**.
3. Giữ Issuer, certificate A, thời gian, Destination, InResponseTo và các thuộc tính còn lại đúng.
4. Gửi qua ACS với request/session tương ứng.
5. Kỳ vọng **authentication bị từ chối**; logs/metrics nội bộ ghi nguyên nhân signature/digest mismatch đã sanitize; **không có session xác thực**.

Một nhánh kiểm thử khác: thay một byte của **SignatureValue** sau ký; XML vẫn parse được nhưng signature cryptographic verification phải fail. Không chỉ gửi XML bị lỗi syntax: lỗi parser không chứng minh signature validator có hoạt động.

### Chú ý canonicalization

XMLDSig canonicalizes XML. Thay đổi một số dạng whitespace/serialization không nhất thiết làm dữ liệu được canonicalized khác đi; ngược lại, thêm namespace hoặc đổi whitespace text node có thể thay đổi digest tùy scope. Vì vậy nên **đổi nội dung NameID/AttributeValue/Conditions nằm chắc chắn trong signed Reference** để tạo negative chắc chắn. Kiểm tra fixture factory không âm thầm ký lại sau khi mutate.

### Không kiểm tra chữ ký bằng cách tìm sự tồn tại của tag

~~~java
// Anti-pattern: chỉ tìm xem XML có thẻ Signature.
boolean isSigned = xml.contains("<ds:Signature>");
~~~

**Đây là anti-pattern, không dùng trong production.** Attacker tự chèn Signature tag bất kỳ. Spring/OpenSAML phải thực hiện digest/signature/trust validation trên đúng element. Không parse SAMLResponse bằng DOM tự viết rồi tạo Authentication dựa vào boolean này.

### Expected result

Không có Saml2Authentication thành công, không có authenticated SecurityContext mới, không có quyền vào /private. HTTP response có thể là 302/400/401 tùy failure handler và UX. **Đừng assert hardcode HTTP 403 nếu app chủ ý redirect về /login?error**.

## 6. Ca B: Issuer sai nhưng chữ ký đúng

**Đích test:** chứng minh SP **ràng buộc một signature đúng với đúng IdP Identity/registration**, không chỉ kiểm tra cryptographic signature.

Các bước tạo fixture độc lập:

1. Bắt đầu từ baseline valid Response.
2. Đổi **Response Issuer** từ https://idp.example.test/metadata sang https://other-idp.example.test/metadata.
3. Nếu Assertion có Issuer, sửa tương ứng theo scenario để tránh hai issuers mâu thuẫn ngoài chủ đích.
4. **Ký lại Response/Assertion sau khi đổi Issuer bằng trusted private key A**.
5. Giữ đúng Audience, Destination, Recipient, timestamps, request correlation và test subject.
6. Confirm offline cryptographic signature trên altered document **vẫn verify thành công bằng A**.
7. Gửi qua ACS và khẳng định **Spring/SAML issuer validator reject** vì Issuer không khớp asserting party của corp-idp.

**Vì sao phải ký lại?** Nếu đổi Issuer trong phần được ký nhưng không ký lại, bạn tạo **invalid signature**. Test có thể bị chặn ở bước chữ ký, khiến nhóm Issuer validation chưa từng được thử.

### Chính xác về Issuer

- **IdP Issuer** là một string EntityID, không chỉ hostname hay TLS certificate subject.
- So sánh theo semantics của IdP entity ID được cấu hình; tránh tự normalize URL bằng cách bỏ slash, đổi chữ hoa/thường hoặc cắt query tùy ý nếu framework không làm vậy.
- **Response Issuer và Assertion Issuer** có thể được validate ở các giai đoạn khác nhau; test nên có biến thể cả hai.
- Với nhiều RelyingPartyRegistrations, có thể cần chọn registration qua **registrationId/previous AuthnRequest state** để test wrong Issuer trong đúng context. Nếu resolver cố tìm registration theo Issuer trong XML, một wrong Issuer có thể dẫn tới **registration not found** trước issuer validation — đó là ca khác. Dùng ACS có registrationId xác định và session/request state phù hợp để cô lập điều muốn đo.
- **Signed-by-trusted-key** nhưng wrong Issuer phải reject vì IdP identity không tương ứng. Ngược lại, Issuer đúng nhưng signature không trust cũng phải reject.

### Negative variants

| Test | Chữ ký | Issuer | Kỳ vọng |
| --- | --- | --- | --- |
| Baseline | A hợp lệ | đúng | Accept nếu mọi policy khác đúng |
| Wrong Response Issuer, ký lại A | A hợp lệ | Response sai | Reject |
| Wrong Assertion Issuer, ký lại A | A hợp lệ | Assertion sai | Reject theo SAML policy |
| Issuer khác một dấu /, ký lại A | A hợp lệ | khác configured EntityID | Reject nếu không bằng exact ID đã cấu hình |
| Issuer rỗng hoặc thiếu | A hợp lệ nếu protocol cho test ký payload | không đủ | Reject |
| Issuer đúng, Audience sai, ký lại A | A hợp lệ | đúng | Reject vì Audience, **không gán nhầm thành Issuer** |

**Không sửa registration để tự động tin Issuer mà test đã đổi.** Mục tiêu là chứng minh cấu hình IdP đã phê duyệt không bị thay thế bởi dữ liệu từ Response.

## 7. Ca C: khóa ký không được tin cậy (untrusted verification credential)

**Đích test:** chứng minh SP chỉ tin **IdP signing certificate A** được cấu hình, không tin cert B được gửi kèm trong XML.

Quy trình:

1. Tạo một Response SAML hợp lệ về mặt cấu trúc, Issuer **đúng**, Audience/Recipient/Destination đúng và timestamps hợp lệ.
2. Ký Response/Assertion bằng **private key B**, hoàn thiện DigestValue và SignatureValue đúng theo XMLDSig.
3. Có thể gắn **X509Certificate B** trong ds:KeyInfo để thử riêng lỗ hổng tự tin KeyInfo.
4. SP registration **vẫn chỉ có verification credential A**, không thêm B.
5. Offline verify bằng public key B phải thành công; bằng public key A phải thất bại.
6. Gửi Response B tới ACS; kỳ vọng **unauthenticated**, không có session hoặc quyền truy cập được cấp.
7. Kiểm tra logs chỉ nêu validation/trust failure có kiểm soát, không in SAMLResponse hoặc secret.

**Nguy cơ cao nhất:** Code thử verify bằng A thất bại rồi **rơi về public certificate bất kỳ từ KeyInfo**. Cách fallback đó biến attacker thành IdP tự ký, cho phép giả mạo bất kỳ subject nào.

### Khác nhau giữa chứng chỉ TLS, IdP signing và SP signing

| Credential | Vị trí | Dùng làm gì? |
| --- | --- | --- |
| HTTPS/TLS certificate của IdP | HTTP client/browser kết nối tới IdP | Xác thực hostname/transport TLS |
| **IdP SAML signing X.509 certificate** | Asserting party verification credentials trong SP | Verify XMLDSig của IdP |
| SP signing private key/certificate | Relying party signing credentials | Ký AuthnRequest/LogoutRequest nếu policy yêu cầu |
| SP decryption private key | Relying party decryption credentials | Giải mã EncryptedAssertion/attributes |
| Cert B xuất hiện trong KeyInfo | Untrusted SAMLResponse | Chỉ là key material do message khai; **không tự đáng tin** |

**Một HTTPS connection hợp lệ tới IdP không làm XML Signature của cert B trở thành trusted.** Tương tự, certificate có subject name giống IdP hoặc chưa hết hạn **không đủ** nếu không thuộc trust set được phê duyệt.

### Trường hợp key rotation

Trong thời gian IdP rotate signing key, SP có thể **tạm thời tin A và B** nếu B đã được xác minh/đăng ký out-of-band theo change control. Tests cần có cả:

- **Trước rollout:** A được chấp nhận, B phải bị từ chối.
- **Trong cửa sổ overlap đã phê duyệt:** A và B được chấp nhận nếu issuer/policy khác hợp lệ.
- **Sau khi thu hồi A:** A bị từ chối, B được chấp nhận.
- **Key C không được đăng ký:** luôn bị từ chối.
- **Metadata mới tự xuất hiện B mà chưa qua trust policy:** không tự động cập nhật trust chỉ vì XML/URL chứa B.

Không dùng một untrusted SAMLResponse để “học” signing key mới. Trust anchors xuất phát từ IdP onboarding hoặc metadata đã được kiểm chứng bằng quy trình tin cậy.

## 8. Cấu hình Spring Security 6.5 để có baseline đáng tin

Spring Security dùng **RelyingPartyRegistration** để gắn IdP entity ID, SSO endpoint, SP entity ID, ACS URL và certificates cần verify.

Ví dụ config **có dependencies bên dưới và file certificate public test đã được chuẩn bị**:

**src/main/java/com/example/saml/SamlSecurityConfig.java**

~~~java
package com.example.saml;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    private X509Certificate trustedIdpCert() throws Exception {
        // Public certificate A được phân phối từ trusted IdP
        // onboarding/test CA, không lấy từ SAMLResponse KeyInfo.
        try (InputStream stream =
                new ClassPathResource(
                    "saml/trusted-idp-signing-A.pem")
                        .getInputStream()) {

            CertificateFactory factory =
                CertificateFactory.getInstance("X.509");
            return (X509Certificate)
                factory.generateCertificate(stream);
        }
    }

    @Bean
    RelyingPartyRegistrationRepository relyingParties()
            throws Exception {

        Saml2X509Credential idpVerifyA =
            Saml2X509Credential.verification(trustedIdpCert());

        RelyingPartyRegistration corp =
            RelyingPartyRegistration
                .withRegistrationId("corp-idp")
                .entityId("https://sp.example.test/metadata")
                .assertionConsumerServiceLocation(
                    "https://sp.example.test/login/saml2/sso/corp-idp")
                .assertingPartyMetadata(party -> party
                    .entityId("https://idp.example.test/metadata")
                    .singleSignOnServiceLocation(
                        "https://idp.example.test/sso")
                    .wantAuthnRequestsSigned(false)
                    .verificationX509Credentials(
                        certs -> certs.add(idpVerifyA)))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Điều kiện chạy:** Có Spring Boot 3/Spring Security 6.5 tương thích; đã cung cấp tệp **saml/trusted-idp-signing-A.pem** là public X.509 certificate của IdP test; issuer, SP entity ID/ACS, IdP SSO và browser external HTTPS routing trùng các giá trị cấu hình. Đây là **mẫu tích hợp**, không khẳng định có thể login vào domain example.test hay có cert fixture thật nếu chưa tạo.

### Dependencies Maven

Trong Maven Spring Boot project với BOM tương thích Spring Security 6.5:

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
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

**Lưu ý phiên bản:** OpenSAML dependencies có thể cần repository/bản được hỗ trợ theo BOM Spring Security hiện tại; kiểm tra dependency tree và tài liệu phiên bản đang chạy. Không trộn OpenSAML 2 hoặc thư viện SAML Extension cũ với Spring Security 6.5.

### Những property quan trọng ở registration

- **.withRegistrationId("corp-idp")**: định danh liên kết SP–IdP trong ứng dụng.
- **.entityId(...)** top-level: SP EntityID, được dùng làm Audience của assertion tùy policy.
- **.assertionConsumerServiceLocation(...)**: public ACS URL; browser POST vào đây.
- **.assertingPartyMetadata(...).entityId(...)**: **IdP EntityID expected**; là nền tảng Issuer check.
- **.singleSignOnServiceLocation(...)**: IdP endpoint nhận AuthnRequest.
- **.wantAuthnRequestsSigned(false)**: ví dụ test IdP không yêu cầu SP ký AuthnRequest; **không làm yếu việc verify SAMLResponse**.
- **.verificationX509Credentials(certs -> certs.add(idpVerifyA))**: trusted certificate để verify chữ ký IdP. Chỉ thêm A trong negative untrusted key test.

**Không nhầm** .verificationX509Credentials với SP .signingX509Credentials. Một cái là **trust public key của IdP**; cái kia là **SP private signing key** cho AuthnRequest theo contract. Thêm B vào verificationX509Credentials “để hết lỗi test” sẽ làm ca untrusted trở thành positive và phá mục tiêu kiểm thử.

## 9. Quy trình tạo fixtures có nguyên nhân lỗi rõ ràng

Bộ fixture nên được tạo từ **test IdP hoặc OpenSAML XMLDSig signer** bằng keys do test kiểm soát. Không sửa XML đã ký một cách ngẫu nhiên rồi gọi đó là kiểm thử đúng nhóm.

Định nghĩa các fixture files:

~~~text
src/test/resources/saml/fixtures/
  baseline-valid.xml
  signature-tampered.xml
  issuer-wrong-resigned-A.xml
  untrusted-signed-B.xml
  audience-wrong-resigned-A.xml
  response-signed-only.xml
  assertion-signed-only.xml
~~~

**Đây là danh sách cấu trúc tài nguyên cần tạo**, không khẳng định các file đã tồn tại. Muốn chạy integration tests phải tạo XML thực từ fixture factory/IdP test với IDs, thời gian, ACS, RelayState/InResponseTo phù hợp theo từng run.

### Thuật toán fixture factory (pseudocode)

~~~text
Setup:
  trusted key pair A; untrusted key pair B
  SP trusts A only
  issuer = https://idp.example.test/metadata
  audience = https://sp.example.test/metadata
  acs = https://sp.example.test/login/saml2/sso/corp-idp
  now = fixed clock/test clock synchronized with SP

baseline:
  create correct Response/Assertion and unique IDs
  set issuer, audience, destination, recipient, time
  if SP-initiated: correlate InResponseTo with saved AuthnRequest
  sign configured Response and/or Assertion with private key A
  verify signed XML offline; send to ACS; expect authenticated

signature-tampered:
  copy baseline signed XML
  change a text value inside signed Reference after signing
  do NOT sign again
  verify offline signature fails; expect unauthenticated

issuer-wrong-resigned-A:
  copy pre-sign baseline XML
  set wrong Response Issuer, and Assertion Issuer if tested
  sign with private key A AFTER the change
  verify offline signature with A succeeds
  SP still configured expected issuer; expect unauthenticated

untrusted-signed-B:
  copy pre-sign baseline XML with correct issuer/audience
  sign with private key B
  optionally embed certificate B in KeyInfo
  verify offline with B succeeds
  SP still trusts A only; expect unauthenticated

audience-wrong-resigned-A:
  copy pre-sign baseline, set wrong Audience
  sign with A; ensure cryptographic signature passes
  expect unauthenticated because Audience fails
~~~

**Kỹ thuật quan trọng:** Với Response và Assertion cùng được ký, cần tái ký theo **đúng thứ tự và phạm vi** để mọi chữ ký ngoài kiểm thử chính đều còn hợp lệ. Ví dụ sửa Assertion rồi ký lại Assertion có thể thay đổi nội dung Response đã ký; khi đó Response signature cần được ký sau cùng. Trước khi gửi mỗi fixture, kiểm tra offline các chữ ký có mục tiêu hợp lệ; không để test “Issuer sai” bị chặn sớm vì một signature khác cũng sai.

### SAMLResponse POST binding

Thông thường ứng dụng nhận XML bytes được **Base64** khi browser POST:

~~~http
POST /login/saml2/sso/corp-idp HTTP/1.1
Content-Type: application/x-www-form-urlencoded

SAMLResponse=BASE64_OF_TEST_XML
~~~

Đây là mô tả cấu trúc HTTP, **BASE64_OF_TEST_XML là nhãn minh họa**, không phải XML signature fixture hợp lệ. Với MockMvc, truyền param **SAMLResponse** như code ở mục sau; framework sẽ decode/unmarshal và chạy đúng authentication provider.

**Không gửi raw XML trực tiếp làm application/xml** tới ACS thông thường rồi ngạc nhiên vì parser không nhận; đó là sai binding, không phải proof signature validation.

## 10. MockMvc integration-test skeleton: thực sự đi qua ACS

Một test đáng tin phải đi qua **Saml2WebSsoAuthenticationFilter**, không gọi trực tiếp helper boolean giả lập, và phải dùng security config có **trusted cert A**.

Mẫu JUnit 5/MockMvc dưới đây minh họa cấu trúc test với **fixture files đã được tạo hợp lệ**. Nó **không tự tạo SAML fixtures**, vì XMLDSig, IdP keys, thời gian, Request ID và signed element cần được fixture factory/IdP test thiết lập cẩn thận.

**src/test/java/com/example/saml/SamlNegativeAuthenticationIT.java**

~~~java
package com.example.saml;

import java.io.InputStream;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;

@SpringBootTest
@AutoConfigureMockMvc
class SamlNegativeAuthenticationIT {

    @Autowired
    MockMvc mvc;

    private String base64Fixture(String filename) throws Exception {
        try (InputStream in = new ClassPathResource(
                "saml/fixtures/" + filename).getInputStream()) {
            byte[] xml = in.readAllBytes();
            return Base64.getEncoder().encodeToString(xml);
        }
    }

    @Test
    void baselineValidResponseAuthenticates() throws Exception {
        mvc.perform(post("/login/saml2/sso/corp-idp")
                .param("SAMLResponse",
                    base64Fixture("baseline-valid.xml")))
            .andExpect(authenticated());
    }

    @Test
    void tamperedSignatureNeverAuthenticates() throws Exception {
        mvc.perform(post("/login/saml2/sso/corp-idp")
                .param("SAMLResponse",
                    base64Fixture("signature-tampered.xml")))
            .andExpect(unauthenticated());
    }

    @Test
    void wrongIssuerWithValidSignatureNeverAuthenticates()
            throws Exception {
        mvc.perform(post("/login/saml2/sso/corp-idp")
                .param("SAMLResponse",
                    base64Fixture("issuer-wrong-resigned-A.xml")))
            .andExpect(unauthenticated());
    }

    @Test
    void untrustedSigningKeyNeverAuthenticates()
            throws Exception {
        mvc.perform(post("/login/saml2/sso/corp-idp")
                .param("SAMLResponse",
                    base64Fixture("untrusted-signed-B.xml")))
            .andExpect(unauthenticated());
    }
}
~~~

**Giới hạn quan trọng của skeleton:**

- **Fixture-dependent**, không phải test hoàn chỉnh chạy độc lập chỉ bằng copy; fixture files phải tồn tại, còn hiệu lực và đúng cấu hình SP.
- Nếu ứng dụng dùng **SP-initiated SSO** và yêu cầu InResponseTo, phải thực hiện **GET /saml2/authenticate/corp-idp** để tạo AuthnRequest mới, lấy request ID, giữ MockHttpSession và sinh fixture tương ứng cho cùng session. Không dùng XML InResponseTo cũ và bỏ qua baseline failure.
- Nếu app cho phép unsolicited/IdP-initiated Response theo policy, fixture phải tuân policy ấy; **không nên nới InResponseTo validation trong production chỉ để test dễ hơn**.
- **SAMLResponse binding** thông thường đi qua một POST ACS. CSRF exemptions của SAML flow do framework config quản lý; test phải có filter chain đúng, không tự disable toàn bộ CSRF để chữa sai endpoint.
- **authenticated()/unauthenticated()** là Spring Security MockMvc result matchers. Tùy security context persistence và failure handler, nên thêm test follow-up GET protected endpoint với session để chứng minh không có quyền truy cập.
- Chỉ assert **unauthenticated()** không đủ phân biệt ba nguyên nhân. Song song cần fixture QA/offline verification và sanitized error diagnostics/metrics; không assert nguyên văn exception message cố định theo OpenSAML version.
- Test chạy trong test environment có SAML registration và IdP cert A; không đưa IdP production private key vào test suite.

### Kiểm tra session không được sinh quyền sau failure

Trong integration harness, mỗi negative test nên chạy với **session sạch**. Sau ACS failure, dùng session result cùng cookie để GET tài nguyên bảo vệ, xác nhận chưa có authenticated user. Không dùng session đã login từ baseline cho negative tests; nếu session đã authenticated trước đó, một failure mới không nhất thiết xóa quyền cũ theo mọi cấu hình, làm test khó diễn giải.

### HTTP status không phải bằng chứng đầy đủ

| Kết quả HTTP | Có thể xảy ra khi | Nên assert thêm |
| --- | --- | --- |
| 302 về trang login/error | failure handler redirect | Không tạo Authentication mới |
| 401 | API/browser policy yêu cầu login | Unauthenticated + no authorization |
| 400 | malformed/invalid SAML message | Nếu muốn test chữ ký, cần chứng minh XML structure còn hợp lệ |
| 403 | AccessDenied/local policy | Xác định đã bị từ chối ở SAML validation hay local role |
| 200 | Public error page | Không suy ra login thành công |
| 500 | Parser/certificate/config runtime failure | Không coi như PASS an ninh; phải sửa baseline/fixture/config |

**Một test nhận 500 vẫn “không có Authentication” nhưng có thể cho thấy lỗi vận hành**, không phải validator đã chặn tấn công theo chính sách. Tách lỗi dữ liệu, lỗi trust và lỗi cấu hình để debug.

## 11. Java 17 chạy độc lập: kiểm tra chữ ký, Issuer và trust tách biệt

Chương trình này dùng **JDK 17 java.security.Signature** với RSA-2048/SHA-256, **không cần Spring, OpenSAML, IdP, network hay certificate files**. Nó thể hiện đúng logic phân tách:

- Chữ ký bị thay đổi sau ký → không verify bằng public key A.
- Issuer sai nhưng **được ký lại bằng A** → cryptography pass, issuer policy fail.
- Payload đúng và được ký bằng private key B → verify bằng trusted public key A fail.
- Audience sai nhưng ký bằng A → audience policy fail.

**Đây không phải XMLDSig/SAML implementation.** Chương trình ký một chuỗi test có ba trường được canonicalize đơn giản; production không được thay OpenSAML bằng cách tự ghép chuỗi issuer/nameId hay dùng SHA256withRSA trên raw XML bytes. XMLDSig còn có canonicalization, namespaces, Reference URI, digest/transforms, signed-element selection và SAML profile validation.

**Tệp: SamlSignatureNegativeCases.java**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public final class SamlSignatureNegativeCases {
    record Claims(String issuer, String audience, String subject) {
        byte[] testBytes() {
            return (issuer + "\n" + audience + "\n" + subject)
                .getBytes(StandardCharsets.UTF_8);
        }
    }

    enum Verdict {
        ACCEPTED,
        REJECTED_SIGNATURE_OR_TRUST,
        REJECTED_ISSUER,
        REJECTED_AUDIENCE
    }

    static byte[] sign(Claims claims, PrivateKey key)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(claims.testBytes());
        return signer.sign();
    }

    static Verdict verifyPolicy(Claims claims, byte[] signature,
            PublicKey trustedIdpKey, String expectedIssuer,
            String expectedAudience) throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(trustedIdpKey);
        verifier.update(claims.testBytes());
        if (!verifier.verify(signature)) {
            return Verdict.REJECTED_SIGNATURE_OR_TRUST;
        }
        if (!expectedIssuer.equals(claims.issuer())) {
            return Verdict.REJECTED_ISSUER;
        }
        if (!expectedAudience.equals(claims.audience())) {
            return Verdict.REJECTED_AUDIENCE;
        }
        return Verdict.ACCEPTED;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair trusted = generator.generateKeyPair();
        KeyPair outsider = generator.generateKeyPair();

        String issuer = "https://idp.example.test/metadata";
        String audience = "https://sp.example.test/metadata";
        Claims correct = new Claims(issuer, audience, "alice");
        byte[] correctSignature = sign(correct, trusted.getPrivate());

        Claims changedSubject = new Claims(issuer, audience, "admin");
        Claims wrongIssuer = new Claims(
            "https://other-idp.example.test", audience, "alice");
        Claims wrongAudience = new Claims(
            issuer, "https://other-sp.example.test", "alice");

        System.out.println("baseline=" + verifyPolicy(correct,
            correctSignature, trusted.getPublic(), issuer, audience));
        System.out.println("tampered=" + verifyPolicy(changedSubject,
            correctSignature, trusted.getPublic(), issuer, audience));
        System.out.println("wrongIssuer=" + verifyPolicy(wrongIssuer,
            sign(wrongIssuer, trusted.getPrivate()),
            trusted.getPublic(), issuer, audience));
        System.out.println("unknownKey=" + verifyPolicy(correct,
            sign(correct, outsider.getPrivate()),
            trusted.getPublic(), issuer, audience));
        System.out.println("wrongAudience=" + verifyPolicy(wrongAudience,
            sign(wrongAudience, trusted.getPrivate()),
            trusted.getPublic(), issuer, audience));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SamlSignatureNegativeCases.java
java SamlSignatureNegativeCases
~~~

**Stdout chính xác (đã kiểm tra với JDK trong môi trường thực thi):**

~~~text
baseline=ACCEPTED
tampered=REJECTED_SIGNATURE_OR_TRUST
wrongIssuer=REJECTED_ISSUER
unknownKey=REJECTED_SIGNATURE_OR_TRUST
wrongAudience=REJECTED_AUDIENCE
~~~

### Vì sao “wrong signature” và “unknown key” có cùng mã từ chối?

Từ góc nhìn verifier chỉ có **trusted public key A**, hai trường hợp đều có thể làm **Signature.verify() == false**:

- Payload đã bị sửa nhưng chữ ký vẫn của A.
- Payload không bị sửa và có chữ ký hợp lệ của **B**, nhưng SP không tin B.

Không thể chỉ nhìn **một giá trị boolean verify(A)=false** để phân biệt chính xác nguyên nhân. Test harness biết nguồn fixture: “tampered” hay “B-signed”; app production chỉ cần **fail closed**, ghi metric phù hợp mà không tiết lộ quá nhiều chi tiết cho attacker.

**Nếu attacker cung cấp KeyInfo B** và verifier dùng B để kiểm tra, phép thử toán học có thể trả true — nhưng **trust verification vẫn phải reject B**. Code standalone cố ý **chỉ dùng trustedIdpKey truyền bởi SP**, tuyệt đối không lấy public key từ payload.

### Bảo vệ thêm cho code thật

Mẫu ký chuỗi test **không kiểm tra** XML Signature Reference, uniqueness của XML IDs, signed node, certificate chain policy, binding Destination/Recipient, times hoặc replay. Chúng nằm trong SAML authentication provider. Không dùng ví dụ này để xác thực user thật, vì nó thiếu các lớp bảo vệ bắt buộc.

## 12. Kiểm thử untrusted key trong metadata và key rotation

Đừng chỉ test XML Response có KeyInfo B. **Metadata IdP** cũng có thể mang KeyDescriptor chứa B. Nếu SP cấu hình tải metadata tự động, cần phân biệt:

1. **Metadata đã được xác minh/trusted** theo onboarding hoặc metadata signature trust.
2. **Signing certificate trong metadata được dùng để verify SAMLResponses** sau khi metadata trust được chấp thuận.
3. **Key được nhúng vào SAMLResponse** chỉ là dữ liệu do message phát ra, không tự mở rộng trust set.

**Một điểm dễ nhầm:** Một số **metadata repository** chỉ xác minh metadata signature khi đã cấu hình **verification credentials** cho repository; nếu không cấu hình, repository có thể parse metadata mà không kiểm chữ ký metadata. Đừng suy “đã dùng HTTPS fetch” đồng nghĩa với metadata XML có trusted signing key update theo chính sách.

### Rotation matrix

| Giai đoạn | Key A | Key B | Key C | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Trước rotation | Trusted | Untrusted | Untrusted | Chỉ Response do A ký được accept |
| Overlap được phê duyệt | Trusted | Trusted | Untrusted | A/B accept nếu Issuer/Audience/Conditions hợp lệ |
| Sau rotation | Untrusted | Trusted | Untrusted | A reject, B accept |
| Metadata B chưa được xác thực | Trusted | Chưa duyệt | Untrusted | Không tự accept B |
| Key bị thu hồi theo incident | Revoked | Theo chính sách | Untrusted | Không accept key revoked |

**Test gắn với policy, không gắn với chuỗi certificate subject giống nhau.** Certificate B có thể có cùng Subject DN với A nhưng public key khác. Ngay cả certificate còn trong thời hạn cũng không tự là trusted IdP credential.

### Tạo fingerprints cho kiểm kê

Quản trị dùng SHA-256 certificate fingerprint/subject/public key metadata để audit trust changes, không log full private keys và không phát tán key material. Fingerprint là **identifier hỗ trợ so sánh**, không tự chứng minh certificate đáng tin nếu ban đầu lấy từ nguồn không đáng tin.

## 13. Các biến thể cần có trong test suite

| # | Ca kiểm thử | Chữ ký/Issuer/Trust | Kết quả đúng |
| --- | --- | --- | --- |
| 1 | Baseline Response hợp lệ | A, Issuer đúng, trust A | **Accept** nếu mọi checks khác đúng |
| 2 | Sửa NameID sau khi ký | Signature digest invalid | Reject |
| 3 | Sửa SignatureValue bytes | Crypto signature invalid | Reject |
| 4 | Sửa DigestValue | Reference digest/signature inconsistent | Reject |
| 5 | Thay payload nhưng giữ signature | Tampered signed data | Reject |
| 6 | Signed Response nhưng Reference URI trỏ ID không tồn tại | Invalid reference | Reject |
| 7 | Signed Response với duplicate XML IDs | ID ambiguity/Signature Wrapping | Reject |
| 8 | Signed Assertion A + unsigned Assertion B “admin” | Wrong node selection | Không bao giờ authenticate bằng B |
| 9 | Response Issuer sai, ký lại A | Valid crypto, wrong issuer | Reject Issuer |
| 10 | Assertion Issuer sai, ký lại A | Valid crypto, wrong issuer | Reject theo policy |
| 11 | Issuer khác một dấu slash, ký lại A | Different EntityID | Reject nếu không chính xác |
| 12 | Không có Issuer bắt buộc | Missing IdP identity | Reject |
| 13 | Key B ký, Issuer đúng | Valid with B, B untrusted | Reject |
| 14 | Key B ký, có KeyInfo B | Self-consistent untrusted key | Reject |
| 15 | Key B ký, không có KeyInfo | B untrusted | Reject |
| 16 | SP tự thêm KeyInfo B làm trust | Sai test harness/policy | Fail code review |
| 17 | Certificate B cùng Subject với A | Different public key | Reject nếu B chưa trusted |
| 18 | A signing key đã bị revoke | Trust set loại A | Reject |
| 19 | A+B rotation overlap | Cả hai được phê duyệt | Accept cả hai theo policy |
| 20 | Key C trong overlap A+B | C chưa được trust | Reject |
| 21 | Issuer đúng, Audience sai, ký A | Valid crypto, wrong Audience | Reject |
| 22 | Destination khác ACS, ký A | Valid crypto, wrong Destination | Reject |
| 23 | Recipient sai, ký A | Invalid SubjectConfirmation | Reject |
| 24 | NotOnOrAfter đã qua, ký A | Expired assertion | Reject |
| 25 | NotBefore ở tương lai, ký A | Not-yet-valid | Reject |
| 26 | InResponseTo không khớp, ký A | Request correlation failure | Reject |
| 27 | Replay cùng Response ID, ký A | Replay | Reject theo policy |
| 28 | Unsigned Response và Assertion ngoài policy | No acceptable signature | Reject |
| 29 | XML malformed/XXE | Parser reject | Không được coi là chữ ký sai |
| 30 | SHA-1 hoặc forbidden algorithm | Crypto policy disallows | Reject |
| 31 | Issuer hợp lệ của IdP tenant khác | Wrong registration/tenant binding | Reject |
| 32 | Key cùng IdP nhưng metadata chưa qua trust | Unknown trust anchor | Reject |
| 33 | Multiple registrations with same cert | Issuer/registration binding | Chỉ đúng IdP+SP contract mới accept |
| 34 | Valid SAML, local account disabled | SAML valid nhưng app policy fail | Không cấp business access |
| 35 | Invalid fixture trả 500 | Runtime/config exception | Cần sửa, **không** cho QA pass |
| 36 | SAML failure + old authenticated session | Tách test sessions | Không suy kết quả mới từ session cũ |

**Các bài test 9, 13 và 21** cho thấy phải **tái ký sau mutation** khi muốn kiểm tra semantic trust checks riêng với cryptographic integrity. Nếu tất cả fixtures được mutate mà không tái ký, bạn chỉ đang test cùng một điều “signature invalid”.

## 14. Những lỗi khiến negative tests báo PASS giả

### 14.1. Baseline chưa bao giờ login thành công

Nếu XML thiếu InResponseTo, đã hết hạn hoặc IdP cert không đúng, cả ba negative tests đều unauthenticated, kể cả khi app đã lỡ tắt issuer/trust verification. Bởi vậy baseline phải được assert authenticated trước; nên cùng một test harness generate fixtures theo thời gian hiện tại.

### 14.2. Test chỉ assert status code

Một redirect 302 hoặc 403 không chứng minh signature validation. Lỗi có thể do CSRF, route không khớp, missing RelyingPartyRegistration, XML malformed hoặc exception, không liên quan nội dung cần test.

### 14.3. Test sửa Issuer nhưng không ký lại

Nếu Issuer nằm trong signed Response/Assertion, XMLDSig digest sai ngay; test chưa chạm logic Issuer. Phải re-sign bằng A và offline verify với A để chứng minh signature còn hợp lệ.

### 14.4. Test dùng certificate B nhưng cũng thêm B vào SP trust list

Khi đăng ký B trong verificationX509Credentials của SP, B **đã trở thành trusted credential**, nên B-signed Response có thể được accept nếu mọi điều kiện khác đúng. Không thể gọi đó là untrusted-key rejection test.

### 14.5. Test tin public key trong SAML KeyInfo

KeyInfo nằm trong XML message chưa được tin. Dùng KeyInfo như trust root tương đương chấp nhận chữ ký tự ký của attacker. Public key có thể giúp chọn/định vị credential **trong tập đã được tin**, không được tự phát sinh trust.

### 14.6. Test dùng một account production có quyền admin

Không dùng production IdP signing private key hoặc thông tin người dùng thật để tạo fixtures âm. Sử dụng test IdP, keys không tồn tại ở production, subject/tenant giả và isolated test environment.

### 14.7. Test không kiểm tra đúng signed element

Một XML có SignedInfo hợp lệ trên phần tử A nhưng code lấy subject từ B là lỗi **XML Signature Wrapping**. Validator phải xác minh Reference URI/ID và ứng dụng dùng đúng object đã validate. Không chỉ gọi getElementsByTagName("Assertion") để lấy phần tử đầu tiên.

### 14.8. Test khóa/Issuer nhưng bỏ qua audience/recipient

Một IdP có thể dùng cùng certificate ký cho nhiều SPs. Dù Issuer và key đúng, Assertion dành cho SP khác **không được accept**. Kiểm AudienceRestriction, Recipient và Destination để ngăn cross-service assertion replay.

## 15. Kiểm tra bằng logging và metrics mà không lộ assertion

**Nên quan sát:**

- Security filter đã chọn đúng ACS/registrationId.
- Response parsed/unmarshalled thành công hay malformed.
- Signature cryptographic failure, mismatch về trusted signing credential, issuer mismatch, audience/recipient/time failure, replay hoặc request correlation failure.
- IdP/tenant registration ID và certificate fingerprint **đã được xác minh từ nguồn tin cậy**, không tin untrusted KeyInfo.
- Test request correlation ID; session authentication success/failure; protected resource access decision.
- Counts lỗi theo category, version/cấu hình provider và metadata key rotation window.

**Không nên log:**

- Raw SAMLResponse/Base64, Assertion XML, NameID/attributes nhạy cảm.
- Private key của IdP/SP, keystore password, session cookies, RelayState chứa secret.
- Full malformed XML lỗi do attacker gửi.
- Một “verified issuer” lấy từ XML trước khi Issuer được validator chấp nhận.

**Client error:** trả thông báo chung như **“SAML authentication failed”**. Chi tiết “unknown signing key” hoặc “wrong issuer” có thể ở structured server logs đã sanitize, phù hợp privacy/abuse policy; không cung cấp cho attacker thông tin hữu ích để dò cấu hình.

### Khi nào cần investigate thay vì tăng retry?

Không retry cùng assertion/Response khi validation fail. Với SAML, replay protection, InResponseTo và NotOnOrAfter có giới hạn thời gian; lặp callback cũ có thể gây replay. Đầu tiên kiểm tra fixture mới, đồng hồ, trust cert, Issuer, Audience, proxy Host/Proto và request/session correlation.

## 16. Bộ quy tắc QA cho một lần kiểm thử đầy đủ

Một suite nên thể hiện hai loại assertions:

**A. Không có bypass:**

- Không có authenticated SecurityContext mới.
- Không có Saml2Authentication mới.
- Không có phiên được nâng quyền.
- Không có local account tự động tạo hoặc role bị thêm trái policy.
- Không truy cập được endpoint bảo vệ khi chỉ dùng negative Response.
- Gateway/ACS không redirect tới destination attacker-controlled.
- Trạng thái lỗi không tiết lộ thông tin nhạy cảm.

**B. Chứng minh đúng nhánh validation:**

- Baseline tương đương thành công.
- **Tampered signature**: XML có cấu trúc hợp lệ, Issuer đúng, trusted A nhưng crypto verify fail.
- **Wrong Issuer**: offline signature bằng A thành công, issuer policy mới là thứ khác.
- **Untrusted key**: offline signature bằng B thành công, trust list SP chỉ có A; key B không được tự tin từ KeyInfo.
- Không có lỗi phụ như expired assertion, wrong Audience, missing InResponseTo, invalid ACS.
- Test assertion chính xác trên Response hoặc Assertion theo contract IdP.
- Fixture generation có unique IDs và thời gian hợp lệ, chạy lặp lại không bị stale/replay.

**Khi đổi thư viện:** Spring Security/OpenSAML/IdP có thể thay exception codes và thứ tự validators. Đừng assert một error message quá cụ thể rồi phá test vì version; nên dựa vào outcome/hard safety invariants và structured diagnostic categories được ứng dụng kiểm soát.

## 17. Quy trình vận hành CI/staging

1. **Tạo test IdP keys** A và B trong môi trường riêng. Giữ private keys ở fixture signer/test secrets; cấp cho SP **chỉ certificate A**.
2. Chốt IdP entity ID, SP entity ID, ACS URL, registrationId, signed element type và policy InResponseTo/clock.
3. Build **positive control fixture** mới, verify offline, chạy qua ACS và assert authenticated + protected GET.
4. Tạo negative signature fixture bằng cách sửa **sau ký**, giữ mọi field khác hợp lệ.
5. Tạo wrong Issuer fixture bằng cách đổi Issuer **trước khi ký lại bằng A**, offline verify valid.
6. Tạo untrusted key fixture bằng B, Issuer vẫn đúng, KeyInfo B có/không theo các biến thể, SP trust chỉ A.
7. Submit mỗi fixture qua ACS với **fresh session/request** tương ứng và assert unauthenticated.
8. Mở rộng matrix cho Audience/Recipient/NotBefore/NotOnOrAfter/InResponseTo/replay/wrapping.
9. Thu thập sanitized metrics, không lưu raw Assertion/cert private keys vào CI reports.
10. Tạo báo cáo phân biệt test setup/fixture error và actual security regression.
11. Trước key rotation, dùng CI verify trust window được phê duyệt (A→A+B→B) và unknown C luôn reject.
12. Chạy suite sau các thay đổi metadata, OpenSAML, Spring Security, SAML signing algorithms, reverse proxy, IdP issuer/ACS hay truststore.

### Ví dụ kết quả QA mong muốn

~~~text
baseline valid, signed by A:       ACCEPT
tampered signature, Issuer valid:  REJECT
wrong Issuer, re-signed by A:      REJECT
correct Issuer, signed by B:       REJECT
wrong Audience, re-signed by A:    REJECT
unknown signing key C:            REJECT
session after invalid Response:    NO NEW AUTHENTICATION
protected resource after failure:  NOT AUTHORIZED
~~~

Đây là **expected assertions**, không phải kết quả của một server SAML thật đã chạy. Chương trình Java 17 ở mục 11 có stdout xác định riêng; còn kết quả integration phụ thuộc fixture generator, IdP test và cấu hình Spring Security thực tế.

## 18. Checklist production

- [ ] Spring Security dùng **Saml2WebSsoAuthenticationFilter/OpenSAML provider** cho ACS, không tự tạo Authentication từ Base64/XML.
- [ ] Mỗi **RelyingPartyRegistration** có expected IdP EntityID và SP EntityID rõ ràng.
- [ ] **verificationX509Credentials** chỉ gồm certificates IdP được onboarding/trust theo chính sách.
- [ ] **KeyInfo trong Response không tự nâng certificate thành trusted signing credential**.
- [ ] Đã xác định Response và/hoặc Assertion nào được ký, phạm vi Reference URI và XMLDSig transforms theo profile.
- [ ] Test **invalid signature** bằng fixture cấu trúc đúng nhưng chữ ký/digest sai.
- [ ] Test **wrong Issuer** được ký lại bằng trusted A để cô lập lỗi Issuer.
- [ ] Test **untrusted key B** có XMLDSig hợp lệ bằng B nhưng SP chỉ trust A.
- [ ] Positive baseline authenticated **trước** khi chấm negative cases.
- [ ] Kiểm SAMLResponse binding, ACS URL, registrationId, timestamps, Audience/Recipient/Destination/InResponseTo/SubjectConfirmation.
- [ ] XML parser hardened chống XXE và XML signature wrapping/duplicate ID.
- [ ] Chỉ sử dụng signed Assertion đã được provider validate; không chọn unsigned sibling.
- [ ] Local user disabled/tenant/resource authorization tiếp tục chặn sau khi SAML hợp lệ.
- [ ] Test có session sạch, Response/Assertion IDs mới, không reuse stale fixtures.
- [ ] Negative tests không được tính PASS chỉ vì HTTP 500 hoặc baseline sai cấu hình.
- [ ] Có cơ chế certificate rotation A→A+B→B với approvals, thời hạn và revoke.
- [ ] Metadata key update không tự trusted nếu chưa qua provenance/signature policy.
- [ ] Kết quả test/metrics được redaction, không in raw SAMLResponse, NameID hoặc private signing key.
- [ ] Test suite chạy lại sau nâng Spring Security/OpenSAML/IdP key hoặc proxy/callback config.

**Kết luận:** Ba bài kiểm thử **chữ ký sai, Issuer sai và khóa không được tin** chứng minh ba ranh giới khác nhau: **integrity của nội dung**, **identity của IdP**, và **nguồn tin cậy của khóa ký**. Test tốt phải giữ hai ranh giới còn lại hợp lệ khi cố tình phá một ranh giới, xác nhận baseline thành công và kiểm tra rằng **không có Authentication mới hay quyền truy cập được cấp**. Trong Spring Security, dùng RelyingPartyRegistration/OpenSAML để quản lý trust; không xây verifier bằng cách lấy public key từ KeyInfo hoặc tự parse unsigned Assertion.

## 19. Nguồn tham khảo chính thức

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): Saml2WebSsoAuthenticationFilter, RelyingPartyRegistration, SAML authentication pipeline.
- [Spring Security – Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): OpenSAML 4/5 providers, Response/Assertion validators, Issuer/Destination.
- [Spring Security – RelyingPartyRegistration API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html): registration, entityId, asserting party metadata.
- [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): metadata trust và verification credentials.
- [Spring Security – MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html): authenticated() và unauthenticated().
- [OWASP – SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): XML signature, issuer/audience, trusted keys, wrapping, replay và X.509 policy.
- [Oracle JDK 17 – java.security.Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): SHA256withRSA, initSign/initVerify và kiểm tra chữ ký.
- [W3C XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/): SignedInfo, Reference, digest, SignatureValue và KeyInfo.
- [OASIS SAML V2.0 Specifications](https://docs.oasis-open.org/security/saml/v2.0/): SAML Core, Bindings, Profiles và Metadata.
