# Saml2X509Credential: phân biệt signing, verification, encryption và decryption trong Spring Security SAML 2.0

## 1. Bài toán: một chứng thư X.509 nhưng bốn vai trò khác nhau

Trong liên kết đăng nhập SAML 2.0, **Service Provider (SP/Relying Party)** và **Identity Provider (IdP/Asserting Party)** trao đổi thông điệp qua trình duyệt. Hai bên không nên tin một XML `SAMLResponse` chỉ vì nó được Base64-decode thành công: SP cần xác minh chữ ký và các điều kiện SAML. Khi một bên yêu cầu mã hóa, phía nhận phải sở hữu khóa giải mã đúng. Vì vậy cấu hình **khóa riêng, khóa công khai, chứng thư và vai trò của từng credential** là nền tảng của federation.

Spring Security cung cấp lớp:

~~~java
org.springframework.security.saml2.core.Saml2X509Credential
~~~

Lớp này giữ **`X509Certificate` công khai**, **`PrivateKey` nếu vai trò yêu cầu** và các **kiểu sử dụng (credential types)**. Bốn vai trò:

- **`SIGNING`:** dùng khóa riêng của bên gửi để **ký** dữ liệu/thông điệp.
- **`VERIFICATION`:** dùng chứng thư/khóa công khai đáng tin của bên gửi để **kiểm tra** chữ ký.
- **`ENCRYPTION`:** dùng khóa công khai của **bên nhận** để **mã hóa** dữ liệu chỉ bên nhận dự kiến đọc được.
- **`DECRYPTION`:** dùng khóa riêng của **bên nhận** để **giải mã** dữ liệu đã được mã hóa tương ứng.

Cùng là X.509 nhưng **ai sở hữu private key**, **chữ ký hay mã hóa**, **truyền theo chiều nào** và **đặt vào bên nào của `RelyingPartyRegistration`** hoàn toàn khác nhau. Nhầm credential sẽ gây lỗi đăng nhập, không thể giải mã assertion hoặc nghiêm trọng hơn là tạo trust sai.

### Kết quả học tập

Sau bài học, người đọc có thể:

1. Vẽ đúng bốn vai trò trên luồng SP ↔ IdP, phân biệt tính **toàn vẹn/xác thực** với **bí mật**.
2. Khởi tạo `Saml2X509Credential.signing/verification/encryption/decryption` đúng đầu vào.
3. Hiểu mục đích của `signingX509Credentials`, `decryptionX509Credentials` phía SP và `verificationX509Credentials` phía IdP trong `RelyingPartyRegistration`.
4. Dùng Spring Boot YAML hoặc Java để cấu hình khóa/chứng thư, biết rõ thông số nào phải có tại mỗi bên.
5. Đọc metadata SAML `KeyDescriptor use="signing"` và `use="encryption"` mà không nhầm private/public.
6. Xác định lúc cần ký AuthnRequest, xác minh Response/Assertion, IdP mã hóa Assertion và SP giải mã.
7. Xử lý chứng thư đổi khóa (rollover), nhiều khóa cùng tồn tại, key mismatch, cấu hình trust sai và vấn đề tải private key.
8. Viết/đọc được một chương trình **Java 17 độc lập** mô phỏng ký, xác minh, mã hóa và giải mã ở mức mật mã cơ bản, không nhầm nó với một SAML provider.

Các ví dụ Spring hướng đến **Spring Boot 3.x / Spring Security 6.x, Java 17+, Servlet/MVC**. Với Spring Security 7.x, khái niệm vai trò giữ nguyên nhưng một số API/cơ chế OpenSAML có thể thay đổi; cần tra tài liệu theo **phiên bản đang chạy**.

## 2. Khái niệm mật mã cơ bản cần nắm

### Public key, private key, X.509 certificate

**Private key (khóa riêng)** chỉ bên sở hữu dùng, không chia sẻ cho IdP/đối tác hoặc đưa lên website. **Public key (khóa công khai)** có thể cung cấp cho bên kia để kiểm tra chữ ký hoặc mã hóa thông điệp gửi tới bên sở hữu khóa riêng. **X.509 certificate** chứa public key và thông tin chứng thư ở định dạng chuẩn; một chứng thư **không chứa private key**.

Đối với SAML, certificate thường được phân phối trong **metadata đã được tin cậy**, qua tệp đã thẩm định hoặc cấu hình SP/IdP. Không được xem mọi certificate xuất hiện trong XML của một người gửi chưa được xác minh là đáng tin. **Trust đến từ quan hệ federation và metadata được xác minh**, không phải từ việc “file có đuôi .crt”.

Hai mục tiêu khác nhau:

| Thuộc tính cần bảo vệ | Chữ ký số | Mã hóa |
| --- | --- | --- |
| Ai đã phát thông điệp? | Có thể xác minh **theo khóa đáng tin** | Không tự chứng minh nguồn phát |
| Thông điệp bị thay đổi? | Phát hiện sửa dữ liệu trong phạm vi đã ký | Không thay thế kiểm tra chữ ký/issuer |
| Người không có khóa đọc được không? | Chữ ký **không che giấu** nội dung | Mã hóa được thiết kế để bảo vệ tính bí mật |
| Khóa của bên nào quan trọng? | **Khóa riêng người ký**, public key của người xác minh | **Public key người nhận**, khóa riêng người nhận |

Trong Web Browser SSO, **TLS/HTTPS** còn bảo vệ kênh truyền qua browser; TLS không thay cho chữ ký SAML, còn chữ ký SAML không làm XML bí mật.

### Key pair và chứng thư không tự “ghép” với nhau

Hai file `sp-signing.key` và `sp-signing.crt` phải thuộc **cùng một cặp khóa**. Chỉ vì cùng tên file không có nghĩa chúng khớp. Với RSA, bạn có thể so public modulus tương ứng bằng công cụ chuyên dụng hoặc thử ký/xác minh trong môi trường kiểm thử. Nếu private key A đi với certificate B, cấu hình có thể tải thành công nhưng phía IdP kiểm tra chữ ký thất bại.

Một hệ thống có thể có:
- Khóa/chứng thư riêng để ký.
- Khóa/chứng thư riêng để giải mã.
- Một key pair dùng cho cả ký và giải mã nếu chính sách cho phép, tuy nhiên nên cân nhắc **tách mục đích, vòng đời và quyền**.

Không nhầm **private key của SP** với **public certificate của IdP**. Một file certificate của IdP chỉ dùng cho verification không cần và không nên đi kèm private key IdP tại SP.

## 3. Ma trận bốn vai trò: ai giữ gì?

Trong một luồng SP-initiated SSO thông thường:

| Vai trò | Thao tác | Thực thể thực hiện | Vật liệu cần tại thực thể | Dùng làm gì? |
| --- | --- | --- | --- | --- |
| `SIGNING` | SP ký `AuthnRequest` | **SP** | **SP private key** + SP public certificate | IdP xác minh AuthnRequest do SP gửi khi policy yêu cầu |
| `VERIFICATION` | SP kiểm tra `SAMLResponse/Assertion` | **SP** | **IdP public X.509 certificate** được tin cậy | Xác nhận chữ ký và tính toàn vẹn thông điệp IdP |
| `ENCRYPTION` | IdP mã hóa Assertion gửi cho SP | **IdP** | **SP public X.509 certificate** | Chỉ SP dự kiến có thể giải mã Assertion |
| `DECRYPTION` | SP giải mã EncryptedAssertion | **SP** | **SP private key** + SP certificate tương ứng | Lấy Assertion cần kiểm tra và xác thực |

Trong chiều ngược khác, ví dụ SP phải mã hóa một thông điệp gửi IdP, **SP dùng public encryption certificate của IdP**; **IdP dùng private decryption key của chính nó**. Bởi vậy không được nói “encryption luôn là IdP” hoặc “verification luôn là SP”: **vai trò phụ thuộc bên gửi/bên nhận và loại thông điệp**. Bảng trên mô tả use case Web Browser SSO phổ biến.

### Quy tắc đối xứng dễ nhớ

~~~text
      BÊN PHÁT THÔNG ĐIỆP ĐƯỢC KÝ             BÊN NHẬN
      private key ký ----------------------> public certificate kiểm tra
                 SIGNING                           VERIFICATION

      BÊN PHÁT THÔNG ĐIỆP ĐƯỢC MÃ HÓA         BÊN NHẬN
      public certificate của người nhận ---> private key người nhận giải mã
                 ENCRYPTION                       DECRYPTION
~~~

Không phải private key luôn nằm bên gửi. **Ký** là private key của **người ký**; **giải mã** là private key của **người nhận**. Đây là điểm phân biệt trọng tâm.

## 4. Saml2X509Credential chứa gì?

Trong Spring Security, kiểu `Saml2X509Credential` có những phần dữ liệu chính:

- `X509Certificate certificate` (bắt buộc trong các factory thông dụng).
- `PrivateKey privateKey` khi credential dùng để SIGNING hoặc DECRYPTION.
- Tập `Saml2X509CredentialType`: `SIGNING`, `VERIFICATION`, `ENCRYPTION`, `DECRYPTION`.

Bốn factory tĩnh thể hiện ý định lập trình:

~~~java
Saml2X509Credential signing =
        Saml2X509Credential.signing(spSigningPrivateKey, spSigningCertificate);

Saml2X509Credential verification =
        Saml2X509Credential.verification(idpSigningCertificate);

Saml2X509Credential encryption =
        Saml2X509Credential.encryption(idpEncryptionCertificate);

Saml2X509Credential decryption =
        Saml2X509Credential.decryption(spDecryptionPrivateKey, spDecryptionCertificate);
~~~

**Đây là đoạn mã minh họa**, các biến kiểu `PrivateKey` và `X509Certificate` phải được tải/khởi tạo thực tế và class được import từ `org.springframework.security.saml2.core.Saml2X509Credential`. Không thể biên dịch đoạn này độc lập khi chưa khai báo biến/không có Spring Security dependency.

Ý nghĩa:

- Factory `signing(privateKey, certificate)` yêu cầu private key thuộc key pair của SP, credential sử dụng tại SP.
- `verification(certificate)` **chỉ cần public certificate** của đối tác mà ta tin để xác minh chữ ký.
- `encryption(certificate)` **chỉ cần public certificate** của bên dự kiến nhận thông điệp mã hóa.
- `decryption(privateKey, certificate)` yêu cầu private key của bên nhận và certificate tương ứng.

Một `Saml2X509Credential` có thể mang **nhiều kiểu sử dụng** nếu dùng các constructor phù hợp. API hiện đại có constructor cho certificate-only với `VERIFICATION/ENCRYPTION` hoặc privateKey + certificate với `SIGNING/DECRYPTION`. Tuy nhiên **khả năng gắn nhiều vai trò không đồng nghĩa nên tái sử dụng cùng một khóa trong production**. Một số chính sách/thuật toán và KeyUsage X.509 có thể giới hạn cách dùng.

Lớp credential là **vật chứa khóa và ý định sử dụng**; bản thân nó không tự định nghĩa toàn bộ SAML trust policy, không tự xác minh metadata, không tự mã hóa Assertion và không thay OpenSAML provider.

## 5. Nơi đặt credential trong RelyingPartyRegistration

Spring Security mô hình hóa một quan hệ SP–IdP bằng `RelyingPartyRegistration`:

- **Phần Relying Party (RP/SP):** entity ID, Assertion Consumer Service (ACS), SP signing credentials, SP decryption credentials.
- **Phần Asserting Party (AP/IdP):** IdP entity ID, SingleSignOnService endpoint/binding, **IdP verification credentials** để SP tin chữ ký từ IdP, và những certificate phục vụ trường hợp SP cần mã hóa cho IdP.

Ví dụ builder cho một SP registration, bỏ qua khai báo biến:

~~~java
RelyingPartyRegistration registration = RelyingPartyRegistration
        .withRegistrationId("corp")
        .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
        .assertionConsumerServiceLocation(
                "{baseUrl}/login/saml2/sso/{registrationId}")
        .signingX509Credentials(c -> c.add(spSigningCredential))
        .decryptionX509Credentials(c -> c.add(spDecryptionCredential))
        .assertingPartyMetadata(party -> party
                .entityId("https://idp.example.org/issuer")
                .singleSignOnServiceLocation("https://idp.example.org/saml/sso")
                .verificationX509Credentials(c -> c.add(idpVerificationCredential))
        )
        .build();
~~~

**Đây chỉ là mảnh cấu hình**, các biến credential chưa được định nghĩa trong đoạn ngắn; phần bên dưới có lớp Java hoàn chỉnh hơn.

Từng dòng có vai trò:

1. `withRegistrationId("corp")`: tên cục bộ để tìm một liên kết IdP, **không tự đồng nghĩa với entity ID**.
2. `entityId(... )`: issuer/định danh SP được gửi trong AuthnRequest và đăng ký với IdP.
3. `assertionConsumerServiceLocation(... )`: nơi SP nhận Response từ browser.
4. `signingX509Credentials`: **SP có private key** để ký AuthnRequest và các thông điệp SP phát khi cần.
5. `decryptionX509Credentials`: **SP có private key** để giải mã dữ liệu IdP mã hóa gửi tới SP.
6. `assertingPartyMetadata(...).verificationX509Credentials`: **SP tin public signing certificate của IdP** để kiểm tra SAML Response/Assertion.
7. IdP còn có thể cung cấp certificate cho **encryption ở chiều gửi đến IdP** trong các use case cần thiết; không đưa SP signing certificate vào danh sách verification của IdP.

**Quan trọng:** SP **không cần private key của IdP** để xác minh chữ ký IdP. Nếu ai đó yêu cầu nhập IdP private key vào SP, đó là dấu hiệu sai nghiêm trọng về phân chia quyền.

## 6. Mapping giữa thao tác và metadata XML

Metadata SAML 2.0 thường phân phối **public certificate**, không phân phối private key.

Đối với **IdP metadata**, bạn có thể thấy:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
      <ds:X509Data>
        <ds:X509Certificate>BASE64_DER_IDP_PUBLIC_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.org/saml/sso"/>
</md:IDPSSODescriptor>
~~~

Đây là **trích đoạn XML giải thích cấu trúc**, không phải metadata IdP hợp lệ đầy đủ: chứng thư được thay bằng text giả và thiếu `EntityDescriptor`/issuer và những thành phần deployment-specific. Nó không thể dùng để đăng nhập.

Đối với **SP metadata** có thể có:

~~~xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    AuthnRequestsSigned="true">
  <md:KeyDescriptor use="signing">
    <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
      <ds:X509Data>
        <ds:X509Certificate>BASE64_DER_SP_SIGNING_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
  <md:KeyDescriptor use="encryption">
    <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
      <ds:X509Data>
        <ds:X509Certificate>BASE64_DER_SP_DECRYPT_CERT</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </md:KeyDescriptor>
</md:SPSSODescriptor>
~~~

Đọc cẩn thận:

- `use="signing"` trong **metadata IdP**: SP dùng certificate này để **verification**.
- `use="signing"` trong **metadata SP**: IdP dùng certificate này để **verification** của thông điệp SP ký.
- `use="encryption"` trong **metadata SP**: IdP dùng public cert này để **encryption**, SP dùng private key tương ứng để **decryption**.
- `use="encryption"` trong **metadata IdP**: một thực thể gửi message cho IdP có thể dùng public cert đó để **encryption**, IdP giải mã bằng private key của nó.
- Nếu `KeyDescriptor@use` bị **bỏ trống**, SAML metadata quy định khóa có thể dùng cho cả ký và mã hóa theo ngữ cảnh; phải xem hợp đồng federation, algorithm, implementation và chính sách tin cậy, không suy đoán tùy tiện.

**Metadata được tải từ đâu và có đáng tin không là một quyết định riêng.** Nếu kẻ tấn công thay toàn bộ IdP metadata, họ có thể cung cấp một public key của chính mình và làm SP tin chữ ký sai nguồn. TLS URL hợp lệ không tự chứng minh IdP entity ID/certificate đúng đối tác. Cần xác minh nguồn metadata, chữ ký metadata/trust anchor theo chính sách và quản lý thay đổi.

### Chữ ký metadata khác chữ ký message

Một metadata XML có thể được **ký để bảo vệ cấu hình**. Chữ ký đó khác với signature của SAML `AuthnRequest`, `Response` hoặc `Assertion`. Không dùng chứng thư *tự khai báo trong metadata chưa tin* để tự chứng minh metadata đáng tin. Trust anchor cho metadata signature cần có nguồn độc lập.

## 7. Khi nào thật sự cần từng credential?

### 7.1 Signing — ký AuthnRequest từ SP

SP có thể ký `AuthnRequest` để IdP xác minh SP là nguồn hợp lệ và request chưa bị sửa. Điều này đặc biệt quan trọng với request chứa yêu cầu nhạy cảm, chẳng hạn `ForceAuthn`, `RequestedAuthnContext` hoặc ACS/issuer.

Luồng:

~~~text
SP private signing key
    -> Spring/OpenSAML tạo chữ ký trên AuthnRequest
    -> browser vận chuyển request
    -> IdP kiểm tra chữ ký với SP public signing certificate
~~~

- Trong **HTTP-Redirect binding**, chữ ký theo binding thường nằm ở query parameters `SigAlg` và `Signature`, ký chuỗi query được định dạng theo chuẩn.
- Trong **HTTP-POST AuthnRequest**, nếu request được ký, có thể dùng **XML Signature** bên trong XML.
- `Saml2X509Credential.signing(privateKey, cert)` không tự bật yêu cầu ký cho mọi IdP; còn phải đối chiếu metadata/IdP policy (`WantAuthnRequestsSigned`) và cách Spring Security cấu hình.
- Không ký bằng IdP private key tại SP; SP không được sở hữu khóa riêng của IdP.
- Không tắt việc kiểm tra chữ ký phía IdP để “làm cho login chạy”, nếu IdP bắt buộc signed AuthnRequest.

### 7.2 Verification — SP kiểm tra Response/Assertion do IdP ký

Đây thường là **credential tối thiểu bắt buộc** để SP tin kết quả đăng nhập SAML. Spring Security dùng IdP public verification certificate **được cấu hình từ metadata tin cậy** hoặc file đã xác nhận.

~~~text
IdP private signing key
    -> IdP ký Response hoặc Assertion
    -> browser POST SAMLResponse tới SP ACS
    -> SP xác minh với IdP public verification certificate
    -> kiểm tra tiếp issuer, audience, time, subject, InResponseTo...
~~~

- Chữ ký số không tự chứng minh user được phép truy cập mọi route. Sau khi xác minh XML, SP còn phải kiểm tra đầy đủ điều kiện SAML và **authorization nghiệp vụ**.
- Theo SAML profile và Spring Security provider, Response hoặc Assertion cần được ký theo chính sách tương ứng; không giả định mọi deployment đều phải ký **cả hai**.
- Đối chiếu đúng khóa của **IdP được phê duyệt**; một certificate có public key hợp lệ từ một IdP khác không thay thế được.
- Khi IdP đổi key, phải cập nhật metadata/verification credentials đúng kế hoạch; không chấp nhận mọi certificate xuất hiện trong Response.
- `verification(certificate)` dùng **public cert**, không có `IdP private key`.

### 7.3 Encryption — IdP mã hóa Assertion gửi cho SP

Khi IdP cần che giấu assertion/attributes khỏi những bên không có private key của SP, IdP có thể mã hóa nội dung để SP giải mã. IdP cần **SP public encryption certificate** (thường từ SP metadata), không cần SP private key.

~~~text
SP công bố public encryption cert
    -> IdP dùng cert đó mã hóa XML SAML dữ liệu cho SP
    -> browser vận chuyển EncryptedAssertion / EncryptedID
    -> SP dùng private decryption key tương ứng để giải mã
~~~

- Đừng nhầm **IdP mã hóa bằng SP public key** với việc **SP dùng `Saml2X509Credential.encryption(idpCert)`**. Factory `encryption(idpCert)` trên SP mô tả trường hợp **SP cần mã hóa cho IdP**; với **IdP mã hóa cho SP**, credential `encryption(spCert)` về mặt hành động thuộc phía **IdP**, còn SP đăng ký **decryption(spKey, spCert)**.
- Encryption thường là mã hóa lai (hybrid): khóa phiên đối xứng để mã hóa nội dung, được bao bọc bằng cơ chế khóa công khai. Ví dụ Java RSA thô ở phần thực hành **không đại diện cho XML Encryption thật**.
- Chọn thuật toán theo khả năng hai bên và policy; không hạ cấp xuống thuật toán cũ chỉ để giải mã thành công.
- Mã hóa bảo vệ bí mật; **không loại bỏ yêu cầu xác minh chữ ký và trust**.

### 7.4 Decryption — SP dùng private key giải mã

Khi nhận `EncryptedAssertion`, `EncryptedID` hoặc `EncryptedAttribute`, Spring Security/OpenSAML có thể dùng **decryption credentials** của SP trong `RelyingPartyRegistration`.

- Nếu SP thiếu decryption key, IdP có thể tạo message hợp lệ nhưng SP **không đọc được nội dung**. Đó là lỗi decryption tại SP, không đồng nghĩa IdP báo `AuthnFailed`.
- Key và certificate SP phải khớp, IdP phải mã hóa cho đúng public certificate.
- Khi đổi decryption key, **không xóa key cũ quá sớm** nếu vẫn có message/in-flight assertion mã hóa bằng cert cũ. Lập kế hoạch overlap và retirement.
- Decryption khác verification; giải mã ra XML không làm assertion đó trở nên đáng tin.
- Provider OpenSAML có những bước xác minh chữ ký và giải mã theo thứ tự an toàn; tùy vị trí chữ ký (Response/Assertion), **giải mã nội dung trước khi xác minh chữ ký thích hợp có thể phá cấu trúc đã ký**. Đừng tự giải mã rồi sửa XML và đưa qua validation như message nguyên bản.

## 8. Java Spring Security: tải certificate công khai chuẩn X.509

Đoạn helper sau sử dụng Java Standard Library và Spring `Resource` để đọc certificate X.509. Tệp nằm trong classpath của một **dự án Spring Boot có dependency Spring Security SAML**:

~~~java
package com.example.federation;

import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.core.io.Resource;
import org.springframework.security.saml2.core.Saml2X509Credential;

public final class SamlCertificateLoader {

    private SamlCertificateLoader() {
    }

    public static X509Certificate readCertificate(Resource resource)
            throws Exception {
        try (InputStream input = resource.getInputStream()) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509")
                    .generateCertificate(input);
        }
    }

    public static Saml2X509Credential idpVerificationCredential(
            Resource resource) throws Exception {
        return Saml2X509Credential.verification(
                readCertificate(resource));
    }

    public static Saml2X509Credential recipientEncryptionCredential(
            Resource resource) throws Exception {
        return Saml2X509Credential.encryption(
                readCertificate(resource));
    }
}
~~~

Đây là **helper**, không phải Java `main()` độc lập. Nó cần các JAR Spring và một file certificate thật ở nơi `Resource` trỏ đến. Dự án dùng Spring Boot 3.x/Java 17+ phải đặt package dưới vùng component scan khi cần gọi từ config. Không có stdout cố định.

Một file PEM X.509 public thường có dạng:

~~~text
-----BEGIN CERTIFICATE-----
...base64 DER content from the trusted partner...
-----END CERTIFICATE-----
~~~

Dấu `...` chỉ minh họa, **không phải chứng thư hợp lệ**. Dùng **cert IdP do kênh đáng tin cung cấp**, không copy một ví dụ từ Internet vào trust store.

`CertificateFactory` phân tích certificate, không thực hiện đầy đủ việc xác nhận “certificate này thuộc đúng IdP”. Trong cấu hình SAML, public signing key thường được pin/nhận từ metadata đã phê duyệt; kiểm tra thời hạn certificate, chain PKIX, key usage và metadata validity cần theo **chính sách sản phẩm/federation**. Đừng nhầm nó với xác thực CA/TLS của HTTPS endpoint.

## 9. Java Spring Security: tải khóa riêng PKCS#8

Khóa riêng phải được bảo vệ. Với RSA key ở định dạng PKCS#8 **không mã hóa** được Spring Security converter hỗ trợ, có thể dùng `RsaKeyConverters.pkcs8()`. Tệp nên được mount trong secret store với quyền truy cập tối thiểu và chỉ cấp cho JVM khi chạy.

~~~java
package com.example.federation;

import java.io.InputStream;
import java.security.interfaces.RSAPrivateKey;

import org.springframework.core.io.Resource;
import org.springframework.security.converter.RsaKeyConverters;

public final class SamlPrivateKeyLoader {

    private SamlPrivateKeyLoader() {
    }

    public static RSAPrivateKey readRsaPrivateKey(Resource resource)
            throws Exception {
        try (InputStream input = resource.getInputStream()) {
            return RsaKeyConverters.pkcs8().convert(input);
        }
    }
}
~~~

**Đây là helper trong dự án Spring**, không phải chương trình Java 17 độc lập. Converter này làm việc với RSA PKCS#8 theo contract API; nếu dùng EC/HSM/KeyStore/PKCS#11, cần cơ chế đọc key tương ứng và cấu hình Spring/OpenSAML phù hợp, không ép mọi khóa vào `RSAPrivateKey`.

### Phân biệt vài định dạng file

| Nội dung file | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| PEM public certificate | `BEGIN CERTIFICATE` | Đọc bằng `CertificateFactory("X.509")` |
| PEM private key PKCS#8 | `BEGIN PRIVATE KEY` | Đọc/giải mã bằng converter phù hợp, bảo vệ file |
| PEM RSA private key PKCS#1 | `BEGIN RSA PRIVATE KEY` | Không mặc nhiên dùng thẳng converter PKCS#8; chuyển định dạng hoặc dùng thư viện phù hợp |
| PEM private key đã mã hóa | `BEGIN ENCRYPTED PRIVATE KEY` | Cần giải mã thông qua secret/password và thư viện an toàn, không log passphrase |
| KeyStore/PKCS#12 | File `.p12`/`.pfx` | Dùng `KeyStore` hoặc tích hợp secret manager/HSM phù hợp; không xem như file PEM trực tiếp |

**Không in private key, không đưa file private key vào Google Sheet hay Git repository.** Kể cả mật khẩu để đọc encrypted PEM cũng là secret; lấy từ secret manager, tránh ghi vào `application.yml` công khai.

## 10. Cấu hình Spring Boot YAML bằng đường dẫn credentials

Spring Boot có thể tạo `RelyingPartyRegistrationRepository` từ các thuộc tính `spring.security.saml2.relyingparty.registration.*`. Trong cấu hình dưới đây:

- **IdP verification certificate** dùng để SP kiểm tra chữ ký Response/Assertion.
- **SP signing private key và cert** để ký AuthnRequest khi IdP bắt buộc.
- **SP decryption private key và cert** để giải mã assertion mà IdP mã hóa cho SP.

Ví dụ `src/main/resources/application.yml` trong một dự án đã có Spring Security SAML:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/corp"
            acs:
              location: "https://app.example.org/login/saml2/sso/corp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing.key"
                  certificate-location: "file:/run/secrets/saml/sp-signing.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-decryption.key"
                  certificate-location: "file:/run/secrets/saml/sp-decryption.crt"
            assertingparty:
              entity-id: "https://idp.example.org/issuer"
              singlesignon:
                url: "https://idp.example.org/saml/sso"
                binding: REDIRECT
                sign-request: true
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-signing.crt"
~~~

**Điều kiện:** Đây là **mẫu cấu hình định hướng cho dòng Spring Boot/Spring Security hỗ trợ các property tương ứng**, không phải một hệ thống chạy được với file giả. Phải cung cấp metadata, public SP URL/ACS và các file thật. `entity-id`/`acs.location` phải trùng với registration đã tạo ở IdP. Một số phiên bản Boot tự phát hiện entity ID và ACS theo template; nếu hardcode phải thay theo môi trường.

Giải thích các nhóm:
- `registration.corp.signing.credentials`: private key/cert thuộc **SP**.
- `registration.corp.decryption.credentials`: private key/cert thuộc **SP** (có thể là key pair khác signing).
- `registration.corp.assertingparty.verification.credentials`: public cert của **IdP**.
- `assertingparty.singlesignon.sign-request: true`: minh họa IdP yêu cầu signed request; **không tự bật** nếu hợp đồng IdP quy định khác và không nên đặt để né lỗi ngược lại.
- Trong use case **SP cần mã hóa cho IdP**, công khai IdP encryption cert thuộc metadata của IdP hoặc cấu hình API, **không phải một decryption private key của SP**.

Nếu IdP có **metadata XML đã được phê duyệt**, một lựa chọn đơn giản hơn là dùng `assertingparty.metadata-uri`; Spring sẽ lấy public certificate/SSO endpoint từ metadata. Với một số môi trường, các property manual và metadata-uri có precedence/merge behavior theo phiên bản; **chọn một nguồn cấu hình rõ ràng**, không trộn credentials mâu thuẫn.

### File secret ở container

Các đường `file:/run/secrets/saml/...</BT> trỏ đến **filesystem JVM/container** và phải có quyền đọc tương thích; chúng không phải đường local trên laptop của developer. Các public certificate `.crt` có thể là classpath artifact được quản lý; private key production nên do runtime secret mount/HSM cung cấp, không đóng gói vào executable JAR.

### Khi không cần tất cả bốn vai trò

Một SP chỉ đăng nhập thông thường **có thể cần IdP verification credential** và chưa cần SP signing/decryption nếu:
- IdP chấp nhận AuthnRequest không ký;
- IdP gửi assertion không mã hóa;
- profile/policy không yêu cầu thông điệp SP ký ở những bước khác.

Ngược lại, khi IdP đòi signed AuthnRequest hoặc encrypted assertion, phải bổ sung đúng credential. Không thêm private keys không cần thiết chỉ để “có đủ bốn vai trò”.

## 11. Bean Java hoàn chỉnh hơn: đăng ký đúng ba loại credential tại SP

Ví dụ sau mô tả **một registration thủ công** cho Spring Boot Servlet khi muốn kiểm soát việc tải file. Nó sử dụng hai helper ở trên và cùng các file/URL như ví dụ YAML. **Không sử dụng đồng thời bean này và Boot YAML registration cùng ID mà không hiểu auto-configuration**.

Tệp `src/main/java/com/example/federation/SamlRelyingPartyConfig.java`:

~~~java
package com.example.federation;

import java.security.cert.X509Certificate;
import java.security.interfaces.RSAPrivateKey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;

@Configuration
public class SamlRelyingPartyConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository()
            throws Exception {

        X509Certificate idpSigningCert =
                SamlCertificateLoader.readCertificate(
                        new ClassPathResource("saml/idp-signing.crt"));

        X509Certificate spSignCert =
                SamlCertificateLoader.readCertificate(
                        new FileSystemResource("/run/secrets/saml/sp-signing.crt"));
        RSAPrivateKey spSignPrivate =
                SamlPrivateKeyLoader.readRsaPrivateKey(
                        new FileSystemResource("/run/secrets/saml/sp-signing.key"));

        X509Certificate spDecryptCert =
                SamlCertificateLoader.readCertificate(
                        new FileSystemResource("/run/secrets/saml/sp-decryption.crt"));
        RSAPrivateKey spDecryptPrivate =
                SamlPrivateKeyLoader.readRsaPrivateKey(
                        new FileSystemResource("/run/secrets/saml/sp-decryption.key"));

        Saml2X509Credential spSigning =
                Saml2X509Credential.signing(spSignPrivate, spSignCert);
        Saml2X509Credential spDecryption =
                Saml2X509Credential.decryption(spDecryptPrivate, spDecryptCert);
        Saml2X509Credential idpVerification =
                Saml2X509Credential.verification(idpSigningCert);

        RelyingPartyRegistration registration =
                RelyingPartyRegistration.withRegistrationId("corp")
                        .entityId("https://app.example.org/saml2/service-provider-metadata/corp")
                        .assertionConsumerServiceLocation(
                                "https://app.example.org/login/saml2/sso/corp")
                        .signingX509Credentials(c -> c.add(spSigning))
                        .decryptionX509Credentials(c -> c.add(spDecryption))
                        .assertingPartyMetadata(party -> party
                                .entityId("https://idp.example.org/issuer")
                                .singleSignOnServiceLocation(
                                        "https://idp.example.org/saml/sso")
                                .wantAuthnRequestsSigned(true)
                                .verificationX509Credentials(
                                        c -> c.add(idpVerification)))
                        .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

**Điều kiện biên dịch/chạy:** bạn cần ba file Java cùng package `com.example.federation` (hai helper ở mục 8–9 và config ở đây), Java 17, Spring Security SAML module, Spring Boot Web/Security và OpenSAML transitive dependencies theo BOM; các file certificate/PKCS#8 key **thật** phải tồn tại. Lớp này là Spring `@Configuration`, **không có `main()` độc lập**; nó chỉ được Spring Boot khởi tạo khi app startup. Không có stdout cụ thể.

Chú ý:
1. `ClassPathResource` phù hợp với public certificate quản lý cùng build.
2. `FileSystemResource` dùng secret mount để không đóng gói private key vào JAR.
3. `InMemoryRelyingPartyRegistrationRepository` giữ snapshot credentials lúc startup. Khi file bị thay, **không giả định bean sẽ tự reload**.
4. `wantAuthnRequestsSigned(true)` mô tả policy IdP trong registration; IdP thực phải tương ứng với cấu hình đã phê duyệt.
5. Hai private keys có thể khác nhau, phù hợp nguyên tắc tách quyền và vòng đời. Chúng phải khớp **cert của chính role đó**.
6. `verificationX509Credentials` nằm trong `assertingPartyMetadata`, không đặt IdP verification certificate vào danh sách SP signing.
7. Một ứng dụng có thể có nhiều registration cho nhiều IdP; mỗi registration phải xác định đúng IdP entity ID/cert/SSO endpoint, tránh dùng lẫn trust giữa tenants.
8. Nếu dự án Spring Security version cũ dùng `assertingPartyDetails` thay `assertingPartyMetadata`, hãy dùng **đúng API của phiên bản**, không trộn method mới/cũ.

### Một SecurityFilterChain tối thiểu

Tệp `src/main/java/com/example/federation/SamlSecurityConfig.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

Với `saml2Login`, Spring xử lý AuthnRequest và nhận SAMLResponse ở ACS; với `saml2Metadata`, ứng dụng có thể công bố **SP metadata** để IdP biết entity ID, ACS và public certificates. Không phải mọi chứng thư public trong metadata đều tự đảm bảo IdP sử dụng đúng role: hai phía còn phải thống nhất metadata và chính sách.

## 12. Dependency và vị trí mã trong dự án

Khi dự án đã có Spring Boot dependency management/BOM, đoạn Gradle Groovy DSL tương đương:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**Đây là snippet chèn vào `build.gradle` hiện có**, không phải build hoàn chỉnh: plugin Boot, Java toolchain và version phụ thuộc dự án. Nếu tổ chức quản lý repositories từ `settings.gradle` hoặc Maven mirror, đặt repository Shibboleth releases ở nơi chính sách yêu cầu. Không override OpenSAML 4/5 ngẫu nhiên.

Trong Maven dự án đã import BOM Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
~~~

Chèn trong `<dependencies>` của POM hợp lệ; các starter Spring Web/Security cần có như dự án yêu cầu. Các file key/cert không thể thay bằng hostname giả: cấu hình còn cần IdP metadata thực, client registration tại IdP và endpoint public có thể được browser truy cập.

### Vì sao không tự thêm OpenSAML version mới?

Spring Security SAML SP sử dụng OpenSAML để parse, xác minh chữ ký và giải mã XML. Version OpenSAML phải tương thích với Spring Security đang chạy. Lỗi `NoClassDefFoundError`, `NoSuchMethodError` hoặc thiếu module có thể đến từ trộn các version. Không “chữa” bằng cách loại thư viện kiểm tra chữ ký khỏi classpath.

## 13. Encryption credential trong SP: dùng trong trường hợp nào?

Một câu hỏi hay gây nhầm: **SP có cần khai báo `Saml2X509Credential.encryption(idpCertificate)` không?**

Không phải trong **luồng SP nhận encrypted assertion từ IdP**. Với chiều nhận:
- IdP dùng **SP public encryption cert** để mã hóa.
- SP dùng **SP private decryption key** để giải mã.
- Spring SP cần `decryptionX509Credentials` của **Relying Party**, không phải thêm IdP encryption credential nhằm giải mã Assertion.

Factory **`encryption(idpCertificate)`** có ý nghĩa khi **một thành phần phía SP phát một thông điệp cần mã hóa cho IdP**. Tùy protocol và API, bạn đưa certificate IdP đúng role vào cấu hình metadata/asserting party có hỗ trợ encryption, hoặc thư viện xử lý message. Đừng giả định Spring Security Web Browser SSO mặc định tự tạo encrypted AuthnRequest chỉ vì có factory này.

Ví dụ mảnh Java:

~~~java
X509Certificate idpEncryptionCert = SamlCertificateLoader.readCertificate(
        new ClassPathResource("saml/idp-encryption.crt"));

Saml2X509Credential forEncryptingToIdp =
        Saml2X509Credential.encryption(idpEncryptionCert);
~~~

**Đây là mảnh code làm rõ hướng sử dụng**, không phải đầy đủ cấu hình SAML encryption. Muốn thực sự phát encrypted message, còn cần protocol, endpoint, thư viện, thuật toán và policy phù hợp. Không áp dụng mảnh này thay `spDecryption` trong ví dụ trước.

## 14. Phân biệt ký XML và mã hóa XML

### Ký SAML

SAML Response/Assertion có thể mang `<ds:Signature>` với các reference, digest, transforms và algorithm. Bên xác minh cần kiểm tra XML signature **trong đúng context**, chống XML Signature Wrapping và đảm bảo chính đối tượng được dùng làm principal là đối tượng được bảo vệ/kiểm tra.

Cách tiếp cận an toàn: để **Spring Security/OpenSAML authentication provider** làm việc đó. Đừng Base64-decode XML, tìm email bằng XPath rồi tự tạo session mà chưa kiểm tra chữ ký, issuer, audience, điều kiện thời gian và request correlation.

### Mã hóa SAML

SAML có thể chứa:
- `<saml:EncryptedAssertion>`: bao bọc assertion được mã hóa.
- `<saml:EncryptedID>`: định danh được mã hóa.
- `<saml:EncryptedAttribute>`: attribute được mã hóa.

Cơ chế XML Encryption thường có `EncryptedData` và `EncryptedKey` thể hiện dữ liệu/khóa phiên được mã hóa. Bên nhận cần private key tương ứng với public certificate bên gửi đã dùng.

**Thứ tự thao tác có ý nghĩa:** nếu assertion chứa XML Signature, giải mã trước/sau ở vị trí không phù hợp có thể làm invalid chữ ký. Spring Security OpenSAML provider phân biệt giải mã các phần tử cấp Response và các phần tử bên trong Assertion. Chỉ tùy chỉnh decrypter khi có lý do rõ ràng và kiểm thử signature validation đầy đủ.

### Ba lỗi giả định phổ biến

1. “Mã hóa Assertion rồi thì không cần ký.” — Sai; encryption nhằm bí mật, không tự đủ chứng minh nguồn/điều kiện của Assertion.
2. “Ký SAMLResponse rồi thì mọi người không đọc được NameID.” — Sai; signed XML vẫn có thể đọc được nếu không mã hóa.
3. “Certificate trong `KeyInfo` là bằng chứng đáng tin vì nó nằm trong Response.” — Sai; cần trust anchor/metadata IdP độc lập.

## 15. Java 17 độc lập: ký/xác minh và mã hóa/giải mã với RSA

Để phân biệt bốn hành động mà **không cần IdP/Spring**, đây là chương trình Java 17 chạy được với JDK. Nó tạo **hai cặp khóa RSA tạm trong bộ nhớ**, một cặp tượng trưng cho IdP và một cặp cho SP. Nó cho thấy:
- IdP ký bằng private key, SP dùng public key IdP xác minh.
- SP có thể kiểm tra dữ liệu bị sửa không còn chữ ký hợp lệ.
- Bên gửi mã hóa cho SP bằng public key SP; SP dùng private key SP giải mã.
- Encryption không thay verification.

**Giới hạn bắt buộc:** mã là **mô phỏng mật mã ở mức byte**, không tạo X.509 certificate, không dùng SAML XML Signature/EncryptedAssertion, không xây metadata, không xác minh issuer hay tạo login thực. Không dùng đoạn này để thay Spring Security/OpenSAML trong sản phẩm.

Tệp **`SamlKeyRolesDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.Arrays;
import javax.crypto.Cipher;

public final class SamlKeyRolesDemo {

    static KeyPair newRsaKeyPair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static byte[] sign(byte[] data, KeyPair signer) throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(signer.getPrivate());
        signature.update(data);
        return signature.sign();
    }

    static boolean verify(byte[] data, byte[] signed, KeyPair signer)
            throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initVerify(signer.getPublic());
        signature.update(data);
        return signature.verify(signed);
    }

    static byte[] encryptForRecipient(byte[] plaintext, KeyPair recipient)
            throws Exception {
        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        cipher.init(Cipher.ENCRYPT_MODE, recipient.getPublic());
        return cipher.doFinal(plaintext);
    }

    static byte[] decryptAtRecipient(byte[] ciphertext, KeyPair recipient)
            throws Exception {
        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        cipher.init(Cipher.DECRYPT_MODE, recipient.getPrivate());
        return cipher.doFinal(ciphertext);
    }

    public static void main(String[] args) throws Exception {
        KeyPair idp = newRsaKeyPair();
        KeyPair sp = newRsaKeyPair();

        byte[] message = "saml-demo".getBytes(StandardCharsets.UTF_8);
        byte[] signed = sign(message, idp);

        System.out.println("IdP signature valid: "
                + verify(message, signed, idp));

        byte[] modified = "saml-tampered"
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("Tampered signature valid: "
                + verify(modified, signed, idp));

        byte[] encrypted = encryptForRecipient(message, sp);
        byte[] decrypted = decryptAtRecipient(encrypted, sp);
        System.out.println("Ciphertext differs: "
                + !Arrays.equals(message, encrypted));
        System.out.println("SP decrypted original: "
                + Arrays.equals(message, decrypted));
    }
}
~~~

Biên dịch/chạy bằng Java 17+:

~~~bash
javac SamlKeyRolesDemo.java
java SamlKeyRolesDemo
~~~

**Stdout chính xác** (key/ciphertext random nhưng chương trình chỉ in Boolean):

~~~text
IdP signature valid: true
Tampered signature valid: false
Ciphertext differs: true
SP decrypted original: true
~~~

Giải thích kết quả:
- Dòng đầu: cùng public key thuộc cặp IdP kiểm tra được chữ ký private IdP.
- Dòng hai: sửa byte message làm chữ ký không còn xác minh được.
- Dòng ba: ciphertext không có cùng bytes plaintext; không phải chứng cứ đã xác thực người gửi.
- Dòng bốn: private key của SP giải mã được ciphertext đã mã hóa bằng public key của SP.

**Cảnh báo kỹ thuật:** RSA-OAEP thuần chỉ mã hóa được dữ liệu nhỏ tùy kích thước khóa; **SAML XML Encryption thật dùng mô hình lai và XML structures**. Không dùng `RSA/ECB/OAEPWithSHA-256AndMGF1Padding` ở đây làm một lựa chọn thuật toán production tự động; bên IdP/SP phải thống nhất XML Encryption algorithms theo policy và khả năng framework. Tên transformation Java không có nghĩa mode ECB thực sự được dùng cho RSA.

## 16. SAML metadata: ai phải nhận được public certificate nào?

Quan hệ tin cậy cần thông tin **đúng chiều**:

| Bên được cấp certificate | Certificate thuộc về ai? | Tại sao cần? |
| --- | --- | --- |
| SP nhận metadata IdP | **IdP signing cert (public)** | SP xác minh Response/Assertion do IdP ký |
| IdP nhận metadata SP | **SP signing cert (public)** | IdP xác minh AuthnRequest SP ký |
| IdP nhận metadata SP | **SP encryption cert (public)** | IdP mã hóa assertion gửi SP |
| SP nhận metadata IdP khi mã hóa message cho IdP | **IdP encryption cert (public)** | SP mã hóa dữ liệu gửi IdP |
| SP private key storage | **SP signing/decryption keys** | SP ký/giải mã — không gửi cho IdP |
| IdP private key storage | **IdP signing/decryption keys** | IdP ký/giải mã — không gửi cho SP |

Trên thực tế, việc ký AuthnRequest tùy IdP policy/metadata. Ví dụ IdP có `WantAuthnRequestsSigned="true"`, khi ấy SP cần signing credential đúng; một số IdP có thể cho phép request unsigned theo hợp đồng và profile. Đối với **IdP signed Response**, SP phải có trust tới đúng certificate theo policy; không vì signer certificate xuất hiện trong XML mà tự tin.

**Điểm cần nhớ:** public certificate có thể công bố qua metadata; private key luôn ở phía sở hữu. Việc “dùng chung key” có nghĩa người sở hữu một key pair dùng cho nhiều thao tác, không có nghĩa chia sẻ private key giữa SP và IdP.

## 17. Key rotation: giữ đăng nhập hoạt động mà không mất trust

Chứng thư có thời hạn và khóa có thể phải thay do chính sách, thuật toán, sự cố hoặc rollover. Spring Security cho phép cấu hình **nhiều credential trong collection** theo role, nhưng cách chọn khóa để ký/giải mã/xác minh phụ thuộc version/provider/metadata, nên **không đảm bảo chỉ thêm một entry là đã hoàn tất rotation**.

### Rotation chứng thư ký của IdP (SP verification)

1. IdP công bố public signing certificate mới qua kênh **được xác minh**.
2. SP cập nhật danh sách **IdP verification credentials** để tin cả khóa cũ và mới trong khoảng chuyển tiếp nếu policy cho phép.
3. Kiểm thử nhận response ký bằng key cũ và mới; kiểm tra issuer/metadata và các validation khác.
4. Theo dõi audit/metric signature failures; không cho phép chứng thư của IdP khác lọt vào trust.
5. Khi IdP ngừng dùng key cũ, loại key cũ theo lịch và kiểm thử.
6. Nếu metadata là snapshot lúc startup, restart/reload repository có kiểm chứng; **không mặc định file/URL đổi thì bean InMemory tự làm mới**.

### Rotation khóa ký của SP (IdP verification)

1. Tạo **SP signing key pair mới** tại secret manager/HSM, không xuất private key cho IdP.
2. Công bố **public signing certificate mới** ở SP metadata hoặc kênh đăng ký chính thức.
3. Chờ IdP chấp nhận cả cert cũ/mới (nếu nền tảng hỗ trợ) và xác nhận kế hoạch cutover.
4. Chỉ sau đó SP mới chuyển signing key chủ động; khi nhiều signing credentials có mặt, phải kiểm tra **key nào Spring thực sự dùng để ký**.
5. Thu hồi/loại bỏ key cũ khi không còn giao dịch cần xác minh; điều chỉnh metadata và monitoring.

### Rotation khóa giải mã của SP (IdP encryption)

1. Công bố SP **public encryption certificate mới**, IdP phải biết trước.
2. Giữ **cả private decryption key cũ lẫn mới** trong thời gian IdP có thể mã hóa bằng một trong hai public cert, nếu sản phẩm hỗ trợ.
3. Kiểm thử encrypted assertions cho mỗi cert phù hợp, xác định thuật toán/KeyInfo.
4. Theo dõi decryption failures ở SP trước khi loại old key.
5. Không phá giải mã bằng cách tùy tiện bật plaintext assertion nếu chính sách yêu cầu encryption.

**Thời điểm và vòng đời metadata** quan trọng hơn thao tác tạo file mới. Trong hệ multi-node, tất cả pod phải có version credentials nhất quán theo cutover; nếu một pod dùng old key và pod khác chỉ có new key, login có thể lỗi không ổn định.

## 18. HSM, keystore và bí mật khóa riêng

**Tệp PEM private key trên đĩa** là cách dễ minh họa nhưng không luôn là cách phù hợp cho production.

Các lựa chọn:
- **KeyStore PKCS#12/JKS**: quản lý khóa/cert theo alias, password và lifecycle; có thể tải qua Java `KeyStore`.
- **HSM/PKCS#11**: giữ private key non-exportable, dùng provider crypto phù hợp nếu Spring/OpenSAML có thể thao tác qua interface `PrivateKey` hoặc strategy tùy chỉnh.
- **Secret manager**: cấp file hoặc key material theo thời điểm khởi tạo, với IAM/audit/rotation và TLS phù hợp.
- **Kubernetes Secret hoặc Docker secret mount**: giảm nguy cơ đóng key trong image, nhưng vẫn cần RBAC, encryption at rest, mount permission và logging an toàn.
- **Java `PrivateKey` object**: không đồng nghĩa key không thể bị trích xuất khỏi memory; các biện pháp hạ tầng và phân quyền vẫn quan trọng.

### Quy tắc vận hành tối thiểu

1. Private key chỉ cấp quyền đọc cho tiến trình cần ký/giải mã.
2. Không commit private key hoặc passphrase vào mã nguồn, log, ticket hoặc tài liệu chia sẻ.
3. Hạn chế metadata source, đường secret mount, quyền sửa cấu hình và quyền phát hành certificate.
4. Ghi nhận fingerprint/public certificate version để audit, nhưng không in private key.
5. Có hướng phục hồi/revocation/cutover nếu private key bị lộ.
6. Chọn thuật toán được IdP/SP hỗ trợ và đáp ứng chính sách bảo mật; tránh signature algorithm yếu.
7. Kiểm tra TLS riêng với SAML trust: mTLS/HTTPS certificate không tự thay SAML signing certificate dù đôi khi có thể trùng key pair.
8. Không chuyển key qua kênh không bảo mật hoặc dùng data URI để nhét secret vào query.

## 19. Các lỗi phổ biến và hướng kiểm tra

| Biểu hiện | Lớp lỗi | Cách xử lý |
| --- | --- | --- |
| `InvalidKeySpecException` | Private key format | Xem PKCS#1/PKCS#8, key encrypted hay không, provider/algorithm; không log nội dung key |
| `InvalidKeyException` | Key object không phù hợp thuật toán | Kiểm tra RSA/EC, signature/encryption algorithm, key đã được load đúng |
| `CertificateException` khi parse | File không phải X.509 certificate hoặc sai encoding | Đọc đúng PEM/DER certificate, kiểm tra nguồn và file được cấp |
| `FileNotFoundException` | Đường key/cert sai trong container/classpath | Kiểm tra mount, resource path, permission, không dùng đường host khi chạy trong pod |
| Signed AuthnRequest bị IdP từ chối | SP signing key/cert hoặc IdP trust không khớp | So SP metadata, private/cert pair, key IdP đang tin, algorithm/binding |
| IdP báo request không ký | SP chưa cấu hình signing, IdP bắt buộc signed request | Bổ sung SP signing credential và policy đúng; không tắt IdP signature check |
| Spring SP báo invalid signature khi Response | IdP verification credential cũ/sai, XML bị sửa | So issuer, IdP signing cert đã tin cậy, metadata rollover, OpenSAML provider |
| SP báo issuer/audience mismatch | Federation metadata/application config | Kiểm tra IdP entity ID, SP entity ID, ACS; không “chữa” bằng thêm mọi certificate |
| SP không giải mã được EncryptedAssertion | Thiếu/wrong SP private decryption key, key rotation hoặc algorithm | Kiểm tra SP cert IdP đã dùng, key tương ứng, thuật toán và provider |
| SP giải mã được nhưng vẫn login fail | Signature/issuer/audience/time/subject/correlation không hợp lệ | **Decryption không đồng nghĩa Authentication**; giữ validation đầy đủ |
| Assertion mã hóa gửi nhầm certificate | IdP dùng SP public cert cũ/sai | So SP encryption metadata, key rollover và IdP config |
| Certificate mới đã thay trong file nhưng app còn cert cũ | InMemory registration không reload | Restart/refresh có kiểm soát và xác nhận effective registration |
| Không tìm thấy SP registration | ACS path/registration ID sai | So `/login/saml2/sso/corp` và config, không sửa credential tùy tiện |
| Spring startup pass nhưng login fail | Keys load được nhưng trust/wire khác | Kiểm tra metadata, signature, issuer, request actual và logs |
| KeyUsage X.509 không phù hợp | Certificate được cấp cho mục đích không đúng | Xác nhận profile/KeyUsage, tạo cert/key phù hợp policy |
| SSL handshake tới IdP lỗi | TLS CA/hostname trust | Xử lý truststore HTTPS, **khác** SAML signing verification certificate |
| Có private key IdP trong SP repo | Rò rỉ trust boundary | Cách ly secret, điều tra sự cố và rotation; SP chỉ cần public cert IdP |

### Lỗi kỹ thuật không phải bằng chứng tuyệt đối

Cùng thông báo `invalid signature` có thể do wrong key, cert rotation, metadata sai, XML không tương thích, algorithm/canonicalization hoặc message bị sửa. Không tuyên bố nguyên nhân chỉ dựa vào một string log. Cần so request/response đã được redact, metadata đã tin và credential fingerprint/public key.

## 20. Quy trình chẩn đoán theo luồng

~~~mermaid
flowchart TD
    A[Đăng nhập SAML thất bại] --> B{SP tạo AuthnRequest?}
    B -- Không --> C[Kiểm tra registration, dependency, filter]
    B -- Có --> D{IdP chấp nhận request?}
    D -- Không --> E[SP signing, IdP public trust, request binding/policy]
    D -- Có --> F{Browser POST SAMLResponse về ACS?}
    F -- Không --> G[IdP/network/cookie/ACS]
    F -- Có --> H{Có EncryptedAssertion/ID/Attribute?}
    H -- Có --> I[SP decryption private key và algorithm]
    H -- Không --> J[Kiểm tra XML Signature]
    I --> J
    J --> K{Signature và trust có hợp lệ?}
    K -- Không --> L[IdP verification cert/metadata và signature policy]
    K -- Có --> M[Issuer, audience, destination, time, InResponseTo]
    M --> N{Đủ điều kiện?}
    N -- Không --> O[Từ chối SAML authentication]
    N -- Có --> P[Tạo Authentication rồi kiểm tra authorization]
~~~

Sơ đồ minh họa các nhánh chẩn đoán, **không ấn định thứ tự từng phép giải mã/xác minh nội bộ** trong mọi phiên bản OpenSAML. Một Assertion có thể vừa được mã hóa vừa được ký; vị trí chữ ký và element có thể ảnh hưởng thứ tự kiểm tra. Để framework xử lý theo contract an toàn.

## 21. Kiểm thử tích hợp trên môi trường SAML test

### Test A — IdP verification certificate

1. Đăng ký SP và IdP metadata đúng đối tác trên môi trường test.
2. Đặt đúng public signing cert IdP vào SP verification credentials.
3. Đăng nhập bằng SAMLResponse đã ký hợp lệ; kỳ vọng Spring xác minh rồi tạo `Authentication`.
4. Với một IdP test có key khác **không nằm trong trust** hoặc môi trường cố ý dùng test metadata sai, xác nhận SP từ chối.
5. Không thử thêm cert không tin để “được PASS”; mục tiêu là chứng minh trust boundary hoạt động.

### Test B — Signed AuthnRequest

1. IdP yêu cầu AuthnRequest được ký, đã nhập SP signing certificate công khai.
2. SP tạo request bằng SP private key tương ứng.
3. Quan sát IdP nhận, xác minh request và tiếp tục login.
4. Thử cấu hình SP signing key/cert không khớp trong môi trường test an toàn; IdP phải từ chối request không hợp lệ theo policy.
5. Với Redirect binding, xem query Signature/SigAlg; với POST, xem XML Signature theo giao thức/IdP version.

### Test C — Encrypted assertion

1. Cung cấp SP public encryption certificate cho IdP.
2. IdP cấu hình mã hóa Assertion cho SP và gửi response.
3. SP có private decryption key đúng; Spring giải mã rồi xác minh SAML/issuer/audience/time.
4. Tạm loại bỏ test decryption key khỏi registration trong **môi trường lab** và kỳ vọng login thất bại khi response được mã hóa.
5. Khôi phục test key rồi xác minh lại; không chuyển production sang plaintext chỉ để né lỗi.

### Test D — Key rotation

1. Cho IdP phát public signing key mới cùng khóa cũ trong metadata/trust overlap (nếu policy).
2. SP tạm tin hai key, test assertion ký bằng mỗi key.
3. Thay key chủ động và xác nhận ứng dụng đã reload registration ở mọi replica.
4. Loại key cũ theo lịch sau khi chứng minh không còn dùng.
5. Lặp quy trình riêng cho SP signing key và SP decryption key (thời điểm cutover **khác nhau**).

### Test E — SSL trust và SAML trust

1. Một HTTPS metadata URL có TLS certificate hợp lệ nhưng XML issuer/key bị thay bằng đối tác không được duyệt: SP **không nên cập nhật trust** chỉ dựa vào HTTP 200.
2. Một IdP SAML signing certificate public đúng nhưng TLS certificate endpoint hết hạn: lỗi TLS cần xử lý riêng, không thay IdP verification key bằng TLS CA.
3. Ghi rõ trust source và phiên bản metadata trước khi kết luận.

## 22. Kiểm tra file, certificate và key bằng công cụ vận hành

Trong môi trường được phép, một số lệnh OpenSSL hỗ trợ kiểm tra public certificate/key **mà không in private key**:

~~~bash
openssl x509 -in sp-signing.crt -noout -subject -issuer -dates -fingerprint -sha256
openssl x509 -in idp-signing.crt -noout -subject -issuer -dates -fingerprint -sha256
openssl pkey -in sp-signing.key -pubout -out sp-signing-public.pem
openssl x509 -in sp-signing.crt -pubkey -noout -out sp-cert-public.pem
~~~

**Chỉ chạy trên tệp mà bạn có quyền xử lý** và trong môi trường bảo mật; hai file public tạm được tạo ra có thể so bằng các công cụ diff/hash thích hợp. Tên file và output khác nhau theo certificate thật nên không có stdout cố định. `openssl pkey` có thể cần passphrase nếu key được mã hóa. Không dùng `-text` trên private key hoặc xuất key tới log chung; tránh để command history chứa passphrase.

### Fingerprint có phải trust anchor không?

Fingerprint SHA-256 của certificate là **dấu nhận diện** để đối chiếu với giá trị đã xác nhận **qua kênh độc lập**. Chỉ vì chương trình tự tính fingerprint của certificate vừa tải chưa tin không tạo thành sự tin cậy. Việc đối chiếu phải có expected fingerprint/metadata signing key được phê duyệt trước.

### Kiểm tra certificate đã hết hạn

X.509 có `notBefore/notAfter`, nhưng mức độ kiểm tra CA/PKIX và validity của SAML signing cert tùy sản phẩm/cấu hình federation. Một SAML trust binding có thể được quản lý qua metadata và không đồng nhất với TLS certificate validation; **không suy mọi certificate hết hạn chắc chắn gây cùng một exception**. Theo chính sách bảo mật tổ chức, thay/cập nhật chứng thư đúng lịch và kiểm thử end-to-end.

## 23. Xử lý multi-IdP và multi-tenant

Khi một SP tích hợp với nhiều IdP, `RelyingPartyRegistrationRepository` có thể chứa nhiều registration:

~~~text
registrationId = corp-a
  assertingParty.entityId = https://idp-a.example.org/issuer
  verificationCerts = [IdP-A signing certs]
  spSigningKey = tenant A key (theo policy)
  spDecryptionKey = tenant A key (theo policy)

registrationId = corp-b
  assertingParty.entityId = https://idp-b.example.org/issuer
  verificationCerts = [IdP-B signing certs]
  spSigningKey = tenant B key (theo policy)
  spDecryptionKey = tenant B key (theo policy)
~~~

SP có thể chọn dùng chung một số khóa SP theo hạ tầng, nhưng phải **phân quyền và ràng buộc trust theo đúng IdP**. Nếu response từ IdP B bị dùng để xác thực user ở tenant A, ngoài chữ ký, `Issuer`, `Audience`, `Recipient`, `InResponseTo` và registration cần khớp.

**Đừng tạo “global verification list” gồm mọi certificate của mọi IdP mà không ràng buộc issuer/registration**. Một public key hợp lệ của đối tác B không nên cho phép giả mạo vai trò của đối tác A. Tương tự, không trộn decryption private keys giữa tenants khi phân cách pháp lý/chính sách yêu cầu.

## 24. Khi hệ thống dùng cùng key cho nhiều vai trò

Spring Security cho phép một credential có nhiều intended usages trong các constructor phù hợp. Tài liệu nêu ví dụ cùng key pair có thể dùng để ký và giải mã, và cùng public key có thể phục vụ verification/encryption.

Tuy nhiên nên cân nhắc:

- Một private key bị lộ sẽ ảnh hưởng **cả chữ ký lẫn giải mã** nếu dùng chung.
- Việc quay vòng signing key sẽ kéo theo thay decryption key và có thể khiến assertion còn đang dùng key cũ không giải mã được.
- Chứng thư có thể có `KeyUsage` hoặc policy cấm một số cách dùng.
- Thuật toán: key signing ECDSA không đương nhiên tương thích với cơ chế RSA encryption theo policy.
- Tách key giúp quản lý quyền, audit, HSM slot và rotation rõ ràng hơn.

**Quy tắc thực hành:** chỉ reuse khi IdP/SP hỗ trợ và có lý do vận hành rõ; ưu tiên tách roles khi thiết kế hệ thống mới có yêu cầu bảo mật cao. Không thay một credential `verification` bằng `encryption` chỉ vì cả hai có cùng certificate file.

## 25. Chú ý những chi tiết ít hiển nhiên

### 25.1 Certificate không giống truststore TLS

Java `cacerts` hoặc TLS truststore dùng để xác minh HTTPS endpoint metadata. IdP SAML signing certificate dùng để xác minh chữ ký của SAML message theo federation trust. Hai loại **có thể là những chứng thư khác nhau**, và việc import IdP cert vào TLS truststore không tự cấu hình `verificationX509Credentials` trong Spring Security.

### 25.2 Đổi cert không nhất thiết đổi entity ID

IdP có thể giữ nguyên `entityID` và thay public signing certificate. Cập nhật trust credentials theo quy trình; không tạo registration mới hoặc thay issuer nếu không có lý do. Tương tự SP entity ID vẫn có thể giữ nguyên khi rotate signing/decryption keys.

### 25.3 Encrypt trước/Verify sau không phải quy tắc bất biến

Các message có thể ký trước khi mã hóa hoặc mã hóa một phần; chính xác thứ tự validation/decryption phụ thuộc vị trí signature và đối tượng. Spring Security OpenSAML provider có chiến lược cho response elements và assertion elements; tự can thiệp sai có thể làm hỏng signature validation.

### 25.4 Ký AuthnRequest không thay chữ ký Assertion

Chữ ký SP trên request giúp **IdP** kiểm tra request đến từ SP. Chữ ký **IdP trên response/assertion** giúp **SP** tin kết quả xác thực. Hai chữ ký thuộc **hai chiều/đối tượng khác nhau**. Không lấy signed AuthnRequest để chứng minh user đăng nhập hợp lệ.

### 25.5 Certificate chain không thay thế issuer/audience

Dù certificate có chain hợp lệ, SP phải đảm bảo issuer, audience và conditions của message đúng registration. **SAML key trust không chỉ là kiểm tra PKIX certificate chain**.

### 25.6 Chỉ dùng secret “đang hoạt động”

Đưa nhiều private keys vào cấu hình mà không có kế hoạch chọn và nghỉ key có thể tăng bề mặt tấn công. Mỗi key nên có owner, role, createdAt, activation/retirement schedule, source và audit.

## 26. Bài tập kèm đáp án

**Bài 1.** SP cần xác minh chữ ký một SAMLResponse do IdP gửi. SP cần private key của IdP hay public certificate nào?

**Đáp án:** SP cần **IdP public signing certificate đã được tin** dưới `Saml2X509Credential.verification(idpCert)`, gắn vào `assertingPartyMetadata(...).verificationX509Credentials`. Không cần private key IdP.

**Bài 2.** IdP bắt buộc signed AuthnRequest. Vật liệu khóa nằm ở đâu?

**Đáp án:** SP giữ **SP private signing key** và certificate khớp; cấu hình `Saml2X509Credential.signing(spKey, spCert)` phía Relying Party. IdP nhận SP public signing cert để verification.

**Bài 3.** IdP gửi EncryptedAssertion cho SP, nhưng SP chỉ có `Saml2X509Credential.encryption(spCert)`. Đã đủ để giải mã chưa?

**Đáp án:** chưa. SP cần **private decryption key** phù hợp với SP public certificate đã được IdP dùng; cấu hình `Saml2X509Credential.decryption(spKey, spCert)` trong RP decryption credentials.

**Bài 4.** Một đội phát triển dùng `Saml2X509Credential.decryption(idpPrivateKey, idpCert)` ở SP để “giải mã assertion”. Việc này sai ở đâu?

**Đáp án:** IdP không nên đưa private key cho SP. IdP phải mã hóa cho **public cert của SP**, SP giải mã với **private key SP**.

**Bài 5.** Login fail invalid signature sau khi IdP thông báo cert rollover. Các bước đúng?

**Đáp án:** xác minh metadata/cert mới qua nguồn tin cậy, cấu hình trusted verification credentials gồm key được phép trong overlap, kiểm tra issuer, signature, repository refresh và các replica; không tắt verification.

**Bài 6.** Assertion mã hóa đã được giải mã thành XML plaintext. Có thể tự tạo authenticated user chưa?

**Đáp án:** không. Cần Spring Security/OpenSAML kiểm tra signature, issuer, audience, recipient/destination, thời gian, subject confirmation và request correlation/replay.

**Bài 7.** Dòng `KeyDescriptor use="encryption"` nằm trong SP metadata. Ai dùng public cert đó và ai giữ private key?

**Đáp án:** IdP dùng **SP public encryption cert** để mã hóa assertion gửi SP; SP giữ **private decryption key**.

**Bài 8.** SP dùng một key pair cho signing và decryption. Có nên mặc nhiên khuyến nghị cách này cho mọi hệ thống?

**Đáp án:** không. API có thể hỗ trợ reuse, nhưng separation of duties, algorithm/KeyUsage, giới hạn ảnh hưởng khi lộ key và kế hoạch rotation là lý do thường nên tách.

**Bài 9.** Certificate vừa tải từ HTTPS IdP metadata có thể tự động được tin vì website có TLS hợp lệ?

**Đáp án:** không. TLS chứng minh kết nối tới host theo truststore; cần xác minh endpoint/issuer/certificate/metadata policy chính xác với đối tác, metadata signature nếu quy định.

**Bài 10.** Đội cấu hình `assertingparty.verification.credentials` bằng SP certificate. Điều gì sẽ xảy ra?

**Đáp án:** nếu IdP ký bằng khóa khác, SP verification thất bại; về logic đây là trust sai nguồn. Sửa thành **IdP public signing certificate** được phê duyệt, không bỏ chữ ký.

**Bài 11.** Có thể dùng cùng private key của IdP để ký AuthnRequest tại SP nhằm qua policy IdP?

**Đáp án:** không. SP ký bằng **private key SP**; IdP dùng SP public cert để kiểm tra. Chia sẻ IdP private key phá ranh giới sở hữu và là sự cố bảo mật.

**Bài 12.** Browser Network thấy HTTPS POST tới ACS thành công nhưng Spring báo cannot decrypt assertion. Đây là lỗi TLS hay SAML?

**Đáp án:** phần HTTPS có thể thành công; lỗi nằm ở **SAML XML decryption**, cần kiểm tra SP private key/certificate/algorithm, metadata và key rollover.

**Bài 13.** SAMLResponse ký bằng key của IdP B gửi đến registration IdP A. SP có thể chấp nhận chỉ vì cert B hợp lệ trong một nơi nào đó trên hệ thống không?

**Đáp án:** không. Registration, issuer, verification credentials và audience/recipient phải ràng buộc đúng đối tác; không dùng chung trust toàn cục một cách tùy tiện.

**Bài 14.** Tại sao cùng một certificate public có thể dùng verification/encryption ở một số API nhưng không đủ cho signing/decryption?

**Đáp án:** verification/encryption chỉ cần **public key**, trong khi signing/decryption phải dùng **private key** tương ứng của bên sở hữu.

## 27. Checklist cấu hình và vận hành

- [ ] Đã xác định chính xác SP/IdP, message cần ký/giải mã và hướng truyền.
- [ ] Cấu hình `signingX509Credentials` bằng **SP private signing key + SP cert** khi IdP yêu cầu signed request.
- [ ] Cấu hình `assertingPartyMetadata.verificationX509Credentials` bằng **IdP public signing certificate đã được tin**.
- [ ] Cấu hình `decryptionX509Credentials` bằng **SP private decryption key + cert** nếu nhận encrypted assertions.
- [ ] Nếu cần SP mã hóa cho IdP, có **IdP public encryption certificate** và protocol/binding hỗ trợ; không dùng IdP private key.
- [ ] Public certificate và private key mỗi role thực sự khớp một cặp, algorithm/KeyUsage hợp lệ theo policy.
- [ ] Nguồn metadata và certificate được xác nhận độc lập, có audit và kiểm tra signature/trust nếu áp dụng.
- [ ] SP metadata được công bố đúng public entity ID, ACS, SP signing/encryption certificates cho IdP.
- [ ] Đường file secret là đường runtime/container, quyền đọc tối thiểu, không nằm trong source control hoặc log.
- [ ] Không trộn Spring Security/OpenSAML versions; class/method API theo dependency hiện có.
- [ ] Có kế hoạch **rotation overlap** cho IdP verification, SP signing và SP decryption, theo trình tự phù hợp.
- [ ] Nếu dùng InMemory registration, thay file certificate không tự refresh; có restart/refresh được kiểm thử.
- [ ] Test được signed AuthnRequest và IdP verification, encrypted assertion/decryption, key mismatch và cert rollover.
- [ ] Không bỏ kiểm tra chữ ký, issuer, audience, time, recipient/destination, InResponseTo hoặc replay để né lỗi.
- [ ] Không hiển thị/log raw assertion, private keys, session cookies và thông tin cá nhân.

## 28. Tổng kết

**Chữ ký là của bên gửi, mã hóa nhằm cho bên nhận:** bên gửi dùng **private key** để ký, bên nhận dùng **public cert của bên gửi** để xác minh; bên gửi dùng **public cert của bên nhận** để mã hóa, bên nhận dùng **private key của mình** để giải mã.

Trong Spring Security SP, credential cốt lõi thường là **IdP verification cert**, **SP signing key/cert** nếu IdP yêu cầu signed AuthnRequest và **SP decryption key/cert** nếu IdP gửi encrypted assertion. Factory `encryption(certificate)` chỉ có nghĩa khi đang **mã hóa cho chủ thể sở hữu private key của certificate đó**; không thể thay cho decryption trên SP.

### Tài liệu đối chiếu

- Spring Security — SAML 2.0 Login Overview, RelyingPartyRegistration và Credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — `Saml2X509Credential` API (bốn factory và credential types): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Security — Authenticating SAML Responses, decryption providers và thứ tự validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 API — `Saml2X509CredentialType`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/saml2/core/Saml2X509Credential.Saml2X509CredentialType.html
- Spring Boot — SAML 2.0 Security properties and auto-configuration: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- OASIS — SAML V2.0 Metadata Specification, `KeyDescriptor` và KeyInfo: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- W3C — XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
- W3C — XML Encryption Syntax and Processing 1.1: https://www.w3.org/TR/xmlenc-core1/
