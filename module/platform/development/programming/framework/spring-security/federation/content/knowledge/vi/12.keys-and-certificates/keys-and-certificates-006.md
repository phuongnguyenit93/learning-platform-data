# Chính sách hết hạn, thu hồi chứng thư và giới hạn kiểm tra mặc định

> **Module:** Spring Security – federation · **Chủ đề cha:** Khóa và chứng thư. Bài học giải thích cách đánh giá hạn sử dụng và trạng thái thu hồi của chứng thư X.509 khi triển khai SAML 2.0 Single Sign-On với Spring Security, ranh giới giữa trust theo metadata/khóa công khai với PKIX/CRL/OCSP, cũng như những điều **không nên giả định** về các bước kiểm tra mặc định.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **chứng thư X.509 dùng ký SAML**, **chứng thư ký SAML metadata**, **chứng thư TLS/HTTPS** và **khóa SP dùng ký/giải mã**.
2. Giải thích **kiểm tra chữ ký số**, **tin cậy khóa**, **thời hạn X.509 (notBefore/notAfter)**, **thu hồi chứng thư (CRL/OCSP)**, **hạn của metadata** và **hạn của Assertion** là các phép kiểm tra **khác nhau**.
3. Hiểu mô hình SAML metadata-based / explicit-key trust, trong đó việc khóa xuất hiện trong metadata đã được chấp nhận có thể quyết định trust mà không nhất thiết làm PKIX chain validation.
4. Biết vì sao không nên tuyên bố một cách chung chung rằng Spring Security mặc định kiểm tra hết hạn/thu hồi chứng thư SAML; kiểm tra thực tế phải theo phiên bản, cấu hình và trust engine.
5. Thiết kế chính sách certificate expiry/revocation và quá trình rollover bao gồm các giai đoạn A → A+B → B, nguồn metadata tin cậy, hạn làm mới và hành động khi có compromise.
6. Đọc các trường `KeyDescriptor`, `X509Certificate`, `validUntil`, `cacheDuration`, `Conditions.NotOnOrAfter`; không dùng một mốc thời gian thay thế mốc khác.
7. Chạy một tiện ích Java 17 đọc chứng thư thực, in hạn hiệu lực/fingerprint và **nói rõ các kiểm tra nó không làm**.
8. Tích hợp cảnh báo sức khỏe chứng thư với Spring Security SAML2 ở mức quan sát, đồng thời tách **policy chấp nhận đăng nhập** khỏi monitor.
9. Tạo bộ test chứng minh hệ thống hành xử đúng khi cert sắp hết hạn, hết hạn, bị thu hồi, thay khóa, metadata quá cũ hoặc IdP bị xâm phạm.

## 2. Tình huống: chứng thư đã “expired” nhưng SSO vẫn đăng nhập được

Giả sử ứng dụng Orders Portal là Service Provider (SP). IdP đối tác phát SAML Response có chữ ký bằng private key của họ. SP lưu public certificate của IdP để xác minh chữ ký.

Ở thời điểm kiểm tra:

~~~text
Chứng thư IdP Signing A
  Subject:       CN=Partner A SAML Signing
  notBefore:     2024-01-01T00:00:00Z
  notAfter:      2026-06-01T00:00:00Z
  Public key:    key-A

IdP Response lúc: 2026-11-07T04:00:00Z
Signature bằng private key-A: đúng về mặt mật mã
SP verification key: key-A vẫn nằm trong registration tin cậy
~~~

Nếu chỉ gọi một hàm **kiểm tra chữ ký** với key-A, chữ ký **có thể vẫn hợp lệ về mặt mật mã** dù mốc X.509 `notAfter` đã qua. Vì hạn chứng thư là **quy tắc trust/policy**, không phải một tính chất khiến công thức xác minh chữ ký công khai tự ngừng hoạt động.

Nhưng điều đó **không tự có nghĩa** cấu hình production nên tiếp tục tin A vô hạn. Việc cho phép hay từ chối phải xuất phát từ **mô hình tin cậy đã chọn**, chính sách rủi ro, nguồn metadata/khóa được duyệt và tình trạng compromise. Trên một cấu hình PKIX có kiểm tra thời hạn, cùng certificate có thể bị từ chối.

**Câu hỏi đúng không phải** “chứng thư hết hạn có đăng nhập được không?” một cách tuyệt đối. **Câu hỏi đúng là**: “SP của chúng ta chấp nhận khóa nào làm trust anchor tại thời điểm nào, bằng nguồn/phương pháp nào, và đã cài/test những điều kiện hết hạn và thu hồi nào?”

## 3. Phân biệt năm loại kiểm tra và thời hạn

| Kiểm tra | Câu hỏi | Thứ được kiểm tra | Có thay thế nhau không? |
| --- | --- | --- | --- |
| **XML Signature verification** | Bytes/XML object đã ký còn nguyên vẹn, chữ ký toán học đúng với public key? | Signature value, digest/reference/transforms trên Response/Assertion/metadata. | Không chứng minh cert còn hạn hoặc chưa bị thu hồi. |
| **Key trust** | Public key/certificate đó có thuộc IdP đang được SP tin? | Pinned verification credentials, SAML metadata đã chấp nhận hoặc PKIX path. | Không chỉ nhìn cert trong XML do request mang tới. |
| **X.509 validity** | Certificate đang trong khoảng `notBefore`–`notAfter`? | Trường thời hạn chứng thư X.509. | Không thay việc xác minh SAML signature hay metadata. |
| **Revocation check** | Chứng thư đã bị CA thu hồi chưa? | CRL, OCSP hoặc policy thu hồi tương ứng. | Không tự xảy ra chỉ vì kiểm tra `notAfter`. |
| **SAML protocol/metadata validity** | Assertion/confirmation và metadata còn đúng hiệu lực? | `Conditions.NotOnOrAfter`, `SubjectConfirmationData.NotOnOrAfter`, metadata `validUntil`/`cacheDuration`. | Không phụ thuộc duy nhất vào cert notAfter. |

Ngoài ra, **SP session/cookie timeout** là một chính sách khác. Một Assertion đã được chấp nhận lúc đăng nhập có thể dùng để tạo session SP; việc local user bị thu hồi quyền phải được xử lý bởi ứng dụng/session policy, không đợi chứng thư hết hạn.

### 3.1. Minh họa bốn đồng hồ khác nhau

~~~text
Chứng thư IdP X.509:
  notBefore ---------------------------- notAfter

Metadata IdP:
  retrievedAt --- cacheDuration --- nextRefresh ... validUntil

SAML Assertion:
  Conditions.NotBefore ---- Conditions.NotOnOrAfter

Bearer SubjectConfirmation:
  issuedAt -------- SubjectConfirmationData.NotOnOrAfter

Phiên SP:
  loginAt ------------------------------ sessionExpiry
~~~

Các khoảng này không cần bằng nhau. Một `Assertion.NotOnOrAfter` chỉ cách hiện tại 3 phút không có nghĩa chứng thư IdP phải hết hạn sau 3 phút. Ngược lại, `notAfter` của cert không quyết định thời hạn dùng `SAMLResponse`.

## 4. Có những loại chứng thư nào trong một tích hợp SAML2?

### 4.1. Chứng thư IdP dùng ký Response/Assertion

- **IdP** giữ private key, phát Response/Assertion được ký.
- **SP** có một hay nhiều certificate/public key của IdP được tin theo metadata hoặc cấu hình thủ công.
- Trong Spring Boot, nhánh thường là `spring.security.saml2.relyingparty.registration.<id>.assertingparty.verification.credentials`.
- Chứng thư dùng để gắn **một public key với một trust relationship**; đừng mặc định nó là một TLS server certificate có chuỗi CA công khai.
- Nếu XML Response có phần `<ds:KeyInfo>` chứa certificate nào đó, **đó không tự là trust anchor**. SP phải đối chiếu với cấu hình IdP được tin.

### 4.2. Chứng thư SP dùng ký AuthnRequest/SLO

- **SP** giữ private key; IdP dùng public key/certificate SP đã đăng ký để xác minh thông điệp.
- Cấu hình Boot thường ở `registration.<id>.signing.credentials` với `private-key-location` và `certificate-location`.
- Đối tác IdP có thể đòi cert còn hạn theo policy riêng; “SP vẫn ký toán học được” không đảm bảo IdP chấp nhận.
- Một lỗi ở cert **SP signing** có thể làm IdP từ chối **AuthnRequest**, khác hẳn lỗi SP xác minh **SAMLResponse**.

### 4.3. Chứng thư SP dùng giải mã Assertion

- IdP mã hóa assertion/identifier cho public key của SP.
- SP giữ private key giải mã, ở `registration.<id>.decryption.credentials`.
- **Giải mã thành công không thay thế chữ ký số** và việc có cert hết hạn không tự định nghĩa thành công/thất bại của thao tác giải mã.
- Khi rotation phải đồng bộ public cert được IdP dùng mã hóa và private key SP còn sẵn để giải mã response đang bay.

### 4.4. Chứng thư ký metadata

- Metadata được ký bằng một khóa tin cậy theo hợp đồng cộng đồng hoặc đối tác.
- **Metadata signing trust** có thể khác với **Assertion/Response signing trust**.
- Một tệp metadata chưa qua xác minh không được tự dùng `KeyDescriptor` bên trong để **tự phê duyệt certificate mới của chính tệp đó**.
- Khi triển khai metadata signature verification, trust anchor phải được thiết lập bằng một kênh độc lập/đã duyệt.

### 4.5. Chứng thư HTTPS/TLS

- Dùng để xác thực đầu cuối kết nối HTTPS khi SP tải metadata hoặc browser truy cập SP/IdP.
- Có thể sử dụng PKIX chain/trust store của Java, kiểm tra hostname/validity/revocation tùy JSSE/provider/cấu hình.
- **TLS server certificate không mặc nhiên là SAML signing certificate**. Chúng có thể khác key pair, khác thời hạn, khác cách rotation và khác nhóm vận hành.
- Đừng thay verification cert IdP bằng chứng thư TLS chỉ vì hostname trên URL metadata giống tên IdP.

## 5. Hai mô hình trust phổ biến và ý nghĩa của expiry

### 5.1. Explicit-key / metadata-based trust

Trong nhiều federation SAML2, SP xem các khóa ký trong **metadata đã được chấp nhận từ nguồn tin cậy** là các khóa được phép xác minh SAML message. Mục tiêu là xác minh một public key cụ thể được IdP công bố, không nhất thiết phải tạo một PKIX chain lên CA công khai.

~~~text
Trusted IdP metadata đã kiểm chứng:
   EntityDescriptor entityID = IdP A
       IDPSSODescriptor
          KeyDescriptor use="signing"
              ds:X509Certificate chứa public key A
          KeyDescriptor use="signing"
              ds:X509Certificate chứa public key B
                    |
                    v
           SP trusted verification keys [A, B]
                    |
              SAML Response signature
                    |
              Verify bằng key phù hợp
~~~

Trong mô hình này, profile metadata của OASIS tập trung vào **key comparison** và tính hợp lệ/nguồn của **metadata**. Vì vậy không thể tự suy rằng `certificate.checkValidity()`, CRL hoặc OCSP luôn được gọi trên signing cert. Một X.509 certificate có thể được dùng như **vật chứa public key**, khác chức năng PKIX leaf certificate trong TLS.

**Không đánh đồng** “expiry chưa được thực thi mặc định” với “expiry không quan trọng”: tổ chức vẫn có thể đặt chính sách riêng phải cảnh báo hoặc chặn cert quá hạn, nhất là đối tác/tài liệu compliance yêu cầu. Cần kiểm chứng xem policy đó có được cài **trong đúng luồng xác thực** hay chỉ có monitor.

### 5.2. PKIX trust / certificate path validation

Với PKIX, SP xác minh đường dẫn chứng thư tới trust anchor được thiết lập trước, gồm chữ ký các chứng thư, thời hạn, key usage/policy, và khi đã cấu hình thì kiểm tra thu hồi:

~~~text
Trusted Root CA
    |
Intermediate CA (nếu có)
    |
IdP Leaf Signing Certificate
    |
CertPath building/validation
    + possible CRL/OCSP
    |
SAML XML Signature verification
~~~

PKIX là **một mô hình trust có thể chọn**, không phải mặc định của mọi triển khai SAML. Để dùng, phải có trust anchors đúng, quy tắc đường dẫn chứng thư, hỗ trợ revocation và policy xử lý trạng thái UNKNOWN.

Ngay cả trong PKIX, không nên coi việc chỉ tạo `CertificateFactory` hoặc gọi `X509Certificate.checkValidity()` là “đã kiểm tra toàn bộ chuỗi và OCSP”. Phải dùng `CertPathValidator` hoặc trust engine thích hợp với **PKIXParameters**, trust anchors và cấu hình revocation rõ ràng; đối tượng trust anchor trong PKIX thường được xử lý khác leaf cert.

### 5.3. So sánh trực tiếp

| Khía cạnh | Explicit-key/metadata trust | PKIX chain trust |
| --- | --- | --- |
| Trust anchor | Metadata đã xác minh/pinned IdP key. | Root/intermediate CA và cert path được chấp nhận. |
| Hạn X.509 leaf cert | Có thể **không dùng** làm quyết định runtime. | Thường thuộc certificate path validation theo thời điểm. |
| CRL/OCSP | Không mặc nhiên có; điều khiển bằng metadata/key removal hoặc policy riêng. | Có thể kiểm tra khi được bật và có dữ liệu/đường dẫn phù hợp. |
| Thu hồi khi key compromise | Gỡ key khỏi metadata/trust registry, refresh tất cả consumers, ngắt session nếu cần. | Thu hồi qua CA/CRL/OCSP **và** thay trust/config theo quy trình. |
| Rollover | Công bố A+B trong metadata rồi bỏ A khi hoàn thành. | Cập nhật chain/cert và phối hợp trust/validity. |
| Rủi ro nếu nhầm | Cho rằng CA revoke đã tự chặn một key vẫn pinned. | Cho rằng cert được pin là đủ dù cần PKIX validation. |

Từng SP/IdP sản phẩm có thể áp policy bổ sung; vì vậy **test** mới chứng minh behavior runtime của deployment.

## 6. Metadata: nơi nhiều triển khai SAML2 “thu hồi khóa”

### 6.1. Ví dụ hai khóa ký trong giai đoạn rollover

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.partner-a.example/saml"
    validUntil="2030-05-01T12:00:00Z"
    cacheDuration="PT30M">
    <md:IDPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:KeyDescriptor use="signing">
            <ds:KeyInfo>
                <ds:X509Data>
                    <ds:X509Certificate>BASE64_DER_CERT_A</ds:X509Certificate>
                </ds:X509Data>
            </ds:KeyInfo>
        </md:KeyDescriptor>
        <md:KeyDescriptor use="signing">
            <ds:KeyInfo>
                <ds:X509Data>
                    <ds:X509Certificate>BASE64_DER_CERT_B</ds:X509Certificate>
                </ds:X509Data>
            </ds:KeyInfo>
        </md:KeyDescriptor>
        <md:SingleSignOnService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="https://idp.partner-a.example/sso"/>
    </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

`BASE64_DER_CERT_A` và `BASE64_DER_CERT_B` là **placeholder cấu trúc**; XML trên không có cert hợp lệ và không có metadata signature. **Không triển khai** ví dụ này thành một metadata IdP thực.

Trong quá trình tải metadata thật, phải:

1. Chỉ nhận metadata từ **nguồn và issuer đã đăng ký**, không từ URL do browser gửi.
2. Xác minh signature metadata nếu trust contract yêu cầu; thiết lập trust anchor độc lập.
3. Kiểm tra `entityID`, role `IDPSSODescriptor`, endpoints, KeyDescriptor usage, chứng thư và các điều kiện liên quan.
4. Áp `validUntil` và chính sách `cacheDuration`; có hạn vận hành tối đa nếu không có các trường này.
5. Chỉ sau đó mới publish một `RelyingPartyRegistration`/credential set mới.
6. Nếu tải/parsing/validation fail, giữ bản last-known-good **chỉ trong hạn còn được phép**, kèm alert. Không giữ stale forever.

### 6.2. Phân biệt `validUntil` và `cacheDuration`

- **`validUntil`**: mốc mà metadata được xem là còn hợp lệ tới trước mốc đó theo profile/chính sách. Không coi đây là `notAfter` của mỗi cert trong tài liệu.
- **`cacheDuration`**: gợi ý khoảng thời gian nên giữ cache trước khi làm mới. Nó không tự động tạo cache/scheduler trong mọi ứng dụng.
- **`notAfter`**: thuộc về từng chứng thư X.509, có thể độc lập với hai trường metadata.
- **`Assertion.Conditions.NotOnOrAfter`**: hạn sử dụng Assertion SAML để xác thực.
- **`SubjectConfirmationData.NotOnOrAfter`**: hạn trình bearer assertion tới SP, thường ngắn.
- **Session timeout**: hiệu lực cookie/session do SP quyết định.

Một metadata mới còn `validUntil` không chứng minh cert bên trong chưa hết `notAfter`. Một cert chưa hết `notAfter` cũng không cho phép SP tiếp tục dùng metadata đã bị thay thế/bị xâm phạm.

### 6.3. Rollover chuẩn: A → A+B → B

~~~text
T0:  Metadata chứa key A        IdP ký bằng A
T1:  Metadata chứa key A + B    SP refresh, chấp nhận cả hai theo policy
T2:  IdP chuyển ký sang B       New response xác minh bằng B
T3:  Hết overlap / in-flight    IdP xóa A khỏi metadata
T4:  SP refresh đầy đủ          SP ngừng tin A khi policy yêu cầu
~~~

Quan trọng: **công bố public key B trước khi IdP dùng private key B** để SP có thời gian refresh. Sau khi chắc không còn response đang bay dùng A, xóa A theo quy trình đã duyệt. Không tự kéo dài overlap vô hạn.

Nếu A **bị compromise**, đây **không** còn là rotation bình thường: ưu tiên loại bỏ A tức thì khỏi trust registry/metadata đã xác minh, thông báo đối tác và kiểm tra các phiên đã tạo bằng A. Đừng giữ A để login khỏi gián đoạn.

### 6.4. OASIS Metadata Interoperability Profile và revocation

OASIS Metadata Interoperability Profile nêu rằng khóa **bị compromise phải được loại khỏi metadata**; phía phát metadata không được dựa vào người tiêu thụ sẽ tra CRL/OCSP để phát hiện. Điều này đặc biệt quan trọng với federation explicit-key trust: một key vẫn còn trong metadata hoặc repository cũ **có thể tiếp tục được tin** dù CA đã đưa certificate vào CRL.

Vì vậy quy trình thu hồi phải bao gồm **distribute new metadata/trusted key set**, refresh và xác minh rằng **mọi SP instance đều thôi tin khóa cũ**. Cần xác định max stale window, health metrics và kênh khẩn cấp khi metadata feed gặp sự cố.

## 7. CRL, OCSP và ý nghĩa “revoked”

### 7.1. Certificate Revocation List (CRL)

CRL là danh sách chứng thư bị CA thu hồi; CRL được ký bởi CA, có thời gian `thisUpdate`/`nextUpdate` và có thể được truy cập qua extension `CRL Distribution Points`. Trong mô hình PKIX với revocation checking, client phải biết cách tải/cache/kiểm tra danh sách từ CA phù hợp.

Giới hạn:

- Không phải tất cả SAML signing cert đều được CA công khai phát hành; nhiều cert là self-signed/được trao đổi trực tiếp.
- Không phải cert nào cũng có CRL Distribution Points.
- Chứng thư **không xuất hiện** trong một CRL bị hết hạn hoặc không thể xác minh **không chứng minh trạng thái tốt**.
- CRL revocation chỉ có tác dụng nếu runtime thực sự kiểm tra nó trong trust path phù hợp.
- Một federation dùng explicit-key pinning có thể không dùng CRL để quyết định trust; khi đó phải remove key khỏi metadata/registration.

### 7.2. Online Certificate Status Protocol (OCSP)

OCSP hỏi trạng thái của một certificate tại responder và nhận một phản hồi được ký. Các trạng thái điển hình gồm **good**, **revoked**, **unknown**; “good” trong giao thức không phải bảo đảm khóa riêng chưa bị lộ, chỉ phản ánh trạng thái mà responder biết theo phạm vi quy định.

Các vấn đề:

- OCSP responder có thể chậm/không truy cập được; phải chọn rõ **fail-open/fail-closed** theo risk.
- HTTP status 200 từ OCSP server **không đủ**; cần xác minh OCSP response signature, thời hạn và issuer.
- OCSP stapling của HTTPS là chủ đề khác; đừng suy rằng Java TLS config tự áp vào SAML signature validator.
- Một certificate self-signed dùng làm public-key container có thể không có OCSP AIA và không thuộc một PKI có responder.
- Một chứng thư CA đã revoke nhưng SP vẫn accept theo metadata key pinning **không chứng minh** rằng OCSP checking đã được thực thi.

### 7.3. Ba trạng thái phải phân biệt

~~~text
VALIDITY:
  BEFORE_VALIDITY | WITHIN_VALIDITY | AFTER_VALIDITY

REVOCATION:
  GOOD | REVOKED | UNKNOWN_OR_UNAVAILABLE | NOT_CHECKED

TRUSTED_KEY:
  IN_TRUSTED_REGISTRATION | REMOVED_FROM_TRUST | UNTRUSTED
~~~

Khi phân tích lỗi, không dùng một cờ `certificateValid=true` để gộp cả ba loại trạng thái. Một cert trong khoảng notBefore/notAfter vẫn có thể bị revoke. Một cert expired có thể vẫn xuất hiện trong trusted metadata. Một key đúng toán học nhưng không nằm trong trusted registration phải bị từ chối.

### 7.4. Chính sách khi không có nguồn revocation

- **PKIX cần CRL/OCSP:** nếu nguồn status không truy cập được, policy phải quyết định có từ chối hay không. Đối với luồng nhạy cảm, cân nhắc fail-closed và cảnh báo vận hành.
- **Explicit-key SAML trust:** nguồn chân lý thường là trusted metadata và quá trình phê duyệt/loại khóa; không giả vờ đã kiểm tra CRL/OCSP khi chưa có cơ chế đó.
- **Compromised key:** loại bỏ key ngay theo hợp đồng, buộc metadata refresh/rollout, cách ly các phiên/đường xử lý có thể bị ảnh hưởng.
- **Metadata không refresh được:** theo dõi tuổi và hạn hiệu lực; hết cửa sổ cho phép phải fail closed theo chính sách đã thiết kế, không dùng stale vô hạn.

## 8. Spring Security SAML2 mặc định kiểm tra những gì?

### 8.1. Luồng Spring Security Servlet

~~~text
Browser POST SAMLResponse
    |
    v
Saml2WebSsoAuthenticationFilter
    |
    v
Saml2AuthenticationToken + trusted RelyingPartyRegistration
    |
    v
OpenSAML AuthenticationProvider
    |
    +-- Verify signature bằng trusted IdP credentials
    +-- Kiểm tra Issuer/Destination/Status theo profile
    +-- Kiểm tra Assertion/Subject/Conditions/Audience
    +-- Decrypt nếu có và đã được cấu hình
    |
    v
Saml2Authentication / Saml2AuthenticatedPrincipal
    |
    v
Local authorization thuộc SP
~~~

Tên class provider chính xác thay đổi theo dòng Spring Security/OpenSAML; ở **Spring Security 6.3** thường dùng OpenSAML 4, còn bản mới sử dụng OpenSAML 5. Phải dựa vào dependency tree và Javadoc đúng version. Sơ đồ này là **các nhiệm vụ xác thực SAML**, không phải cam kết rằng mọi cert sẽ luôn được PKIX/CRL/OCSP kiểm tra tự động.

### 8.2. Ba điều không nên mặc định suy đoán

**Không suy đoán 1: “Đã thêm cert vào YAML thì Spring kiểm tra CA và OCSP”.**  
`Saml2X509Credential.verification` cung cấp chứng thư để kiểm tra chữ ký trong quan hệ tin cậy với IdP. Nó không tự là lệnh bắt buộc phải chạy `CertPathValidator`, `checkValidity`, CRL và OCSP trên mọi request.

**Không suy đoán 2: “Certificate hết hạn đồng nghĩa Spring chắc chắn chặn login”.**  
Trong một deployment explicit-key trust, expired certificate có thể vẫn là public key được pin tin cậy; chữ ký toán học có thể tiếp tục xác minh. Trong PKIX-based trust hoặc policy kiểm tra riêng, có thể bị chặn. **Đừng đưa ra lời khẳng định tuyệt đối nếu chưa test version/config cụ thể.**

**Không suy đoán 3: “Spring đã kiểm tra CRL/OCSP vì HTTPS kết nối metadata hoạt động”.**  
HTTPS/TLS path validation và việc xác minh chữ ký XML SAML sử dụng **hai luồng trust khác nhau**. Một kênh HTTPS hợp lệ không tự làm signing cert trong metadata trở thành “not revoked” hoặc chứng minh XML metadata đã được ký.

### 8.3. Bảng phạm vi mặc định và trách nhiệm bổ sung

| Kiểm tra | Spring Security/OpenSAML SAML login | Cần chính sách/thiết lập bổ sung |
| --- | --- | --- |
| SAML Response/Assertion XML signatures | Có bộ xử lý/validator dựa trên verification credentials của trusted registration. | Chọn đúng IdP, metadata/cert trusted, signed-object selection, policy thuật toán. |
| SAML Issuer/Recipient/Audience/time/request correlation | Có validator theo profile, tùy version và customization. | Test trường hợp sai và clock skew; không tự tắt để vượt qua lỗi tích hợp. |
| X.509 `notBefore/notAfter` của IdP signing cert | **Không được giả định** luôn là điều kiện chấp nhận. | Đặt policy rõ, triển khai kiểm tra/gate theo trust model nếu cần. |
| CRL/OCSP cho IdP signing cert | **Không được giả định** bật tự động. | PKIX/revocation engine phù hợp hoặc quản lý key removal qua metadata theo federation policy. |
| Metadata XML signature | Phụ thuộc metadata loader/trust config; **không phải cứ có metadata URI là chắc đã verify signature XML**. | Cấu hình signer trust anchor nếu bắt buộc; kiểm tra thực tế. |
| Metadata `validUntil`/`cacheDuration` | Phụ thuộc cách tải/caching/resolver. | Thiết kế refresh/expiry-aware, không dùng snapshot stale vô hạn. |
| Chứng thư SP signing/decryption đã sắp hết hạn | Thư viện có thể vẫn sử dụng key pair; đối tác có policy khác. | Monitor, lên lịch thay cert, đăng metadata SP và phối hợp IdP. |
| Local user/tenant permissions | Không tự suy ra từ cert hoặc assertion. | Application authorization, ownership check, session revocation. |

Trong dòng Spring Security mới, tài liệu `Authenticating SAML Responses` mô tả các extension points để tùy biến response/assertion validators. **Không thay thế toàn bộ validator bằng một lambda chỉ kiểm tra cert expiry**: làm vậy có thể vô tình bỏ kiểm tra signature/issuer/conditions. Nếu bổ sung policy hãy **ghép/ủy quyền cho validator mặc định** theo API đúng phiên bản, và viết test regression cho toàn bộ checks.

## 9. Cấu hình Spring Boot: khóa dùng để xác minh khác khóa ký của SP

### 9.1. Dùng IdP metadata

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_METADATA_URI}
~~~

`PARTNER_A_METADATA_URI` phải đến từ một nguồn được quản trị tin cậy. Metadata có thể mô tả nhiều chứng thư để rollover. Nạp metadata ở startup **không đồng nghĩa tự refresh trong mọi phiên bản**; cần hiểu repository/resolver/caching thực tế.

### 9.2. Khai báo verification cert thủ công

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            entity-id: "https://orders.example/saml2/sp/partner-a"
            acs:
              location: "https://orders.example/login/saml2/sso/partner-a"
              binding: POST
            assertingparty:
              entity-id: "https://idp.partner-a.example/saml"
              sso-url: "https://idp.partner-a.example/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:certs/idp-a-signing.crt"
                  - certificate-location: "classpath:certs/idp-b-signing.crt"
~~~

Đây là ví dụ **minh họa cấu trúc Spring Boot 3.3**; các file chứng thư phải tồn tại và được xác nhận thật, URL phải đổi thành hệ thống thực. Hai certificate đại diện **hai khóa IdP có thể được tin trong giai đoạn overlap**, không có nghĩa hệ thống tự kiểm tra danh sách thu hồi.

Đặc biệt:

- `assertingparty.verification.credentials` là các **public cert tin cậy của IdP**.
- `signing.credentials` là **private key/certificate của SP** để ký outbound SAML.
- `decryption.credentials` là **private key/certificate của SP** để giải mã inbound assertion nếu IdP mã hóa.
- Đừng nạp một certificate từ `<ds:KeyInfo>` do attacker đưa vào response rồi xem nó là verification credential được phép.

### 9.3. Khi chuyển IdP certificate A sang B

Nếu cấu hình file thủ công, phải cập nhật file/registration/bean và **bảo đảm tất cả instances nhận phiên bản mới**. Nếu chạy từ metadata, phải xác minh hệ thống thực sự refresh và công bố bản trusted mới; không tự suy metadata file đổi là repository trong RAM sẽ đổi theo.

## 10. Java 17 thực hành: đọc validity của certificate một cách trung thực

Một thao tác học tập hữu ích là viết chương trình JDK 17 đọc certificate công khai (PEM hoặc DER) và báo **các thông tin có thể xác định trực tiếp**.

Chương trình này **chỉ** đọc X.509 certificate, kiểm tra `notBefore/notAfter` và tính SHA-256 fingerprint. Nó **không**:
- xác minh SAML XML signature,
- xác minh X.509 certification path hoặc certificate authority,
- truy vấn CRL/OCSP,
- kiểm tra metadata trust hoặc local permissions.

### 10.1. Tệp `CertificateValidityInspector.java`

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Date;
import java.util.HexFormat;

public class CertificateValidityInspector {

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            System.err.println(
                "Usage: java CertificateValidityInspector <cert-file> [ISO-8601-instant]");
            System.exit(2);
        }

        Instant at = args.length == 2
            ? Instant.parse(args[1])
            : Instant.now();

        X509Certificate cert;
        try (InputStream in =
                 Files.newInputStream(Path.of(args[0]))) {
            CertificateFactory factory =
                CertificateFactory.getInstance("X.509");
            cert = (X509Certificate) factory.generateCertificate(in);
        }

        String validity;
        try {
            cert.checkValidity(Date.from(at));
            validity = "WITHIN_VALIDITY";
        }
        catch (CertificateExpiredException ex) {
            validity = "EXPIRED";
        }
        catch (CertificateNotYetValidException ex) {
            validity = "NOT_YET_VALID";
        }

        byte[] fingerprint = MessageDigest.getInstance("SHA-256")
            .digest(cert.getEncoded());

        System.out.println("at=" + at);
        System.out.println("subject=" +
            cert.getSubjectX500Principal().getName());
        System.out.println("issuer=" +
            cert.getIssuerX500Principal().getName());
        System.out.println("notBefore=" +
            cert.getNotBefore().toInstant());
        System.out.println("notAfter=" +
            cert.getNotAfter().toInstant());
        System.out.println("sha256=" +
            HexFormat.of().formatHex(fingerprint));
        System.out.println("validity=" + validity);

        // Những kết luận tuyệt đối KHÔNG do checkValidity() cung cấp:
        System.out.println("samlSignature=NOT_CHECKED");
        System.out.println("pkixPath=NOT_CHECKED");
        System.out.println("revocation=NOT_CHECKED");
        System.out.println("samlMetadataTrust=NOT_CHECKED");
    }
}
~~~

### 10.2. Biên dịch và chạy

Chuẩn bị file chứng thư **công khai** thực tế `idp-signing.pem` (không dùng private key):

~~~bash
javac --release 17 CertificateValidityInspector.java
java CertificateValidityInspector idp-signing.pem
~~~

Có thể kiểm tra tại một thời điểm cố định:

~~~bash
java CertificateValidityInspector idp-signing.pem 2030-05-01T10:00:00Z
~~~

Kết quả các dòng `subject`, `issuer`, `sha256`, `notBefore`, `notAfter` và `validity` phụ thuộc vào file/thời điểm truyền vào. **Không có stdout cố định** cho một chứng thư chưa được cung cấp. Tuy nhiên bốn dòng cuối của mọi lượt chạy thành công là **chính xác**:

~~~text
samlSignature=NOT_CHECKED
pkixPath=NOT_CHECKED
revocation=NOT_CHECKED
samlMetadataTrust=NOT_CHECKED
~~~

Giải thích:

- `CertificateFactory` parse chứng thư, không tự xác lập trust với IdP.
- `X509Certificate.checkValidity(Date)` chỉ kiểm tra **khoảng thời gian** tại tham số `at`. Nó không xác minh certificate chain hoặc CRL/OCSP.
- `MessageDigest SHA-256` tính fingerprint public certificate phục vụ inventory/đối chiếu với đối tác. Nó **không** chứng minh certificate đáng tin.
- `HexFormat` thuộc JDK 17; nếu dùng JDK cũ hơn phải thay cách hiển thị hex.
- Nếu certificate là self-signed, điều đó **không tự làm nó đáng tin hoặc không đáng tin** trong mọi mô hình; đánh giá theo trust registry/metadata và hợp đồng.
- Đừng thay đoạn kiểm tra SAML của Spring Security bằng chương trình này.

### 10.3. Dùng `keytool` kiểm tra nhanh mà không viết Java

~~~bash
keytool -printcert -file idp-signing.pem
~~~

`keytool -printcert` giúp nhìn issuer, subject, fingerprint, validity và một số extensions của certificate. **Đây là hoạt động inspection**, không phải bằng chứng hệ thống SAML đang thực thi revocation checking. Kết quả “NotAfter” là một mốc cảnh báo vận hành, còn việc **khóa có nằm trong metadata được tin** hay không phải được kiểm tra riêng.

## 11. Spring Boot 3.3/Spring Security 6.3: monitor chứng thư mà không đánh tráo authn policy

Để tránh cert bất ngờ hết hạn, có thể thêm **monitor** vào SP. Code dưới đây nhắm **Java 17, Spring Boot 3.3.x, Spring Security 6.3.x**. Nó đọc verification credentials từ `RelyingPartyRegistrationRepository` theo một `registrationId` xác định và ghi log cảnh báo.

### 11.1. Gradle dependencies và cấu trúc

~~~text
saml-cert-health/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samlcert/
    │   ├── SamlCertHealthApplication.java
    │   ├── SecurityConfig.java
    │   └── SamlCertificateMonitor.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-cert-health'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Cấu hình `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_METADATA_URI}

app:
  saml:
    cert-monitor-interval-ms: 3600000
    cert-warning-days: 30
~~~

`PARTNER_A_METADATA_URI` cần là nguồn metadata IdP **thật và được tin cậy**. Ví dụ này sẽ không tạo IdP, tài khoản hay chứng thư tự động.

### 11.2. Main application

`src/main/java/com/example/samlcert/SamlCertHealthApplication.java`:

~~~java
package com.example.samlcert;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class SamlCertHealthApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlCertHealthApplication.class, args);
    }
}
~~~

### 11.3. Bật SAML2 Login

`src/main/java/com/example/samlcert/SecurityConfig.java`:

~~~java
package com.example.samlcert;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Mã này dùng bộ xử lý SAML2 mặc định và không thêm endpoint debug. `authenticated()` chỉ kiểm tra người dùng đã đăng nhập, **chưa** thực hiện authorization nghiệp vụ. Ứng dụng thật phải kiểm tra local permission và tenant khi truy cập resource.

### 11.4. Monitor có thể biên dịch

`src/main/java/com/example/samlcert/SamlCertificateMonitor.java`:

~~~java
package com.example.samlcert;

import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Component;

@Component
public final class SamlCertificateMonitor {

    private static final Logger log =
        LoggerFactory.getLogger(SamlCertificateMonitor.class);

    private final RelyingPartyRegistrationRepository registrations;
    private final int warningDays;

    public SamlCertificateMonitor(
            RelyingPartyRegistrationRepository registrations,
            @Value("${app.saml.cert-warning-days:30}")
                int warningDays) {
        this.registrations = registrations;
        this.warningDays = warningDays;
    }

    @Scheduled(
        fixedDelayString =
            "${app.saml.cert-monitor-interval-ms:3600000}"
    )
    public void inspect() {
        RelyingPartyRegistration registration =
            registrations.findByRegistrationId("partner-a");

        if (registration == null) {
            log.error("SAML certificate monitor: registration missing");
            return;
        }

        Instant now = Instant.now();
        Date checkedAt = Date.from(now);
        var credentials = registration.getAssertingPartyDetails()
            .getVerificationX509Credentials();

        if (credentials.isEmpty()) {
            log.error("SAML certificate monitor: no verification keys");
            return;
        }

        for (Saml2X509Credential credential : credentials) {
            X509Certificate cert = credential.getCertificate();
            try {
                cert.checkValidity(checkedAt);
                long daysLeft = ChronoUnit.DAYS.between(
                    now, cert.getNotAfter().toInstant());
                if (daysLeft <= warningDays) {
                    log.warn(
                        "IdP signing cert near expiry: registration={}, daysLeft={}",
                        registration.getRegistrationId(), daysLeft);
                }
            }
            catch (CertificateExpiredException ex) {
                log.error(
                    "IdP signing cert after X.509 notAfter; registration={}",
                    registration.getRegistrationId());
            }
            catch (CertificateNotYetValidException ex) {
                log.error(
                    "IdP signing cert before X.509 notBefore; registration={}",
                    registration.getRegistrationId());
            }
        }
    }
}
~~~

**Tác dụng thật sự:**

- `@EnableScheduling` bật scheduling; `@Scheduled` sẽ kiểm tra định kỳ các verification certificate mà repository **đang giữ**.
- `getAssertingPartyDetails().getVerificationX509Credentials()` lấy certificate IdP đã có trong một registration.
- Monitor gọi `checkValidity` để **quan sát** notBefore/notAfter và ghi cảnh báo. Nó **không** kiểm tra CRL/OCSP hoặc xác minh bất kỳ SAMLResponse nào.
- `warningDays=30` là giá trị policy minh họa, không phải mặc định bắt buộc theo SAML.
- Không ghi private key, raw assertion, NameID hoặc dữ liệu người dùng vào log.
- Nếu metadata loader không refresh, monitor sẽ chỉ đọc **certificate cũ trong RAM**; cần cơ chế refresh/rollover riêng.
- Nếu doanh nghiệp quyết định **chặn login** bằng expiry check, phải cài gate đúng luồng trust/verification với regression tests; **không giả vờ rằng log ERROR ở monitor đã chặn SSO**.

### 11.5. Chạy demo

Với Java 17+, Gradle wrapper tương thích và metadata IdP thật:

~~~bash
./gradlew bootRun
~~~

Đường đăng nhập SP-initiated mặc định thường là `/saml2/authenticate/partner-a`, ACS mặc định thường là `/login/saml2/sso/partner-a`. Khi kiểm thử, SP entity ID và ACS phải được đăng ký đúng tại IdP.

**Không có stdout cố định** cho scheduler: log phụ thuộc thời điểm chạy, số certificates và dữ liệu metadata. Đừng coi ứng dụng boot thành công là bằng chứng CRL/OCSP đã được kiểm tra.

## 12. Cài policy hết hạn và thu hồi mà không phá vỡ SAML validator

Khi có yêu cầu kiểm toán “reject expired/revoked signing certificates”, làm rõ điều đó áp dụng vào **loại certificate và trust model nào**:

1. **IdP signing cert được pin qua metadata:** Có muốn ràng buộc `notAfter` không, hay áp riêng key-acceptance lifetime từ trusted metadata? Trường hợp expired do kỹ thuật nhưng key chưa compromise có chính sách chấp nhận tạm không?
2. **IdP PKIX-signed leaf certificate:** Có trust anchors chính xác và revocation source đáng tin không? Cần OCSP/CRL, điều gì xảy ra khi responder offline?
3. **Metadata signing certificate:** Có bị revoke/expired chưa, và metadata được phát qua kênh tin cậy nào? Việc chấp nhận metadata mới có cần dual approval không?
4. **SP signing/decryption certificates:** IdP có reject cert expired không? Làm thế nào publish cert mới, giữ private key cũ cho in-flight decryption mà không tin credential bị compromise?
5. **TLS certificates:** được JSSE/HTTPS client xử lý riêng; không dùng chúng để chứng minh signing cert status.

### 12.1. Kiến trúc chặn login (khái niệm)

~~~text
Trusted metadata / out-of-band approved keys
              |
        Fetch and verify source
              |
    Validate issuer, metadata expiry
              |
     Apply certificate acceptance policy
       - key allowed for IdP role?
       - X.509 validity required?
       - revocation check required?
       - key explicitly compromised?
              |
       +------+------+ 
       |             |
      PASS          FAIL/UNKNOWN per policy
       |             |
Publish trusted    Reject candidate /
registration       alert / stop new trust
       |
Spring Security normal SAML validator
       |
Only valid SAML Response becomes Authentication
~~~

**Phải giữ nguyên kiểm tra SAML** sau khi policy được áp vào certificate: chữ ký đúng phần tử, issuer, audience, recipient, InResponseTo, Conditions và replay. Tránh viết một `AuthenticationManager` mới chỉ gọi `checkValidity` rồi cho login.

### 12.2. Đừng tự tạo trust chỉ từ chứng thư trong XML

Một attacker có thể tự tạo key pair, tự ký SAML Assertion và nhúng public certificate vào `ds:KeyInfo`. Nếu SP tin certificate đó chỉ vì chữ ký toán học khớp, SP đã mất ranh giới IdP tin cậy.

Đúng là **chứng thư IdP phải đến từ nguồn đáng tin cậy đã định danh trước**: signed metadata/trust registry/certificate pin được quản trị, hoặc PKIX chain tới trust anchor được phê duyệt theo policy. Công thức “signature valid with provided key” khác với “signature valid with **trusted IdP key**”.

### 12.3. Xử lý cert expired nhưng vẫn ở metadata

Có ít nhất hai chính sách hợp lý tùy hợp đồng:

- **Metadata-key-trust policy:** Key còn nằm trong metadata đã được xác minh, chưa bị gỡ vì compromise; SP có thể quyết định tiếp tục dùng key dù X.509 notAfter đã qua, kèm cảnh báo/đề nghị rollover. Quyết định phải được ghi rõ và có giới hạn.
- **Strict-X.509-validity policy:** SP yêu cầu cert còn trong notBefore/notAfter mới được đưa vào tập verification keys, kể cả metadata vẫn công bố nó. Phải có rotation overlap trước expiry, và có kế hoạch khắc phục nếu cert IdP hết hạn mà chưa phát key mới.

Không có một đáp án “SAML luôn bắt buộc PKIX” cho mọi federation. Nếu tài liệu compliance **bắt buộc strict validity**, không thể giải quyết bằng việc đổi thông điệp giải thích; phải implement/test rõ.

### 12.4. Xử lý revocation UNKNOWN

Nếu đã chọn PKIX/CRL/OCSP và bắt buộc trạng thái GOOD, runtime phải có đường xử lý cho `UNKNOWN`, `TRY_LATER`, responder timeout, stale CRL và signature OCSP sai. “Không tra được” **không phải** “GOOD”. Với hệ thống nhạy cảm, policy fail-closed cần được thử để bảo đảm không tạo session khi status không thể xác minh.

Tuy nhiên, **đừng gọi CRL/OCSP mỗi request SSO nếu sẽ gây timeout hàng loạt** mà chưa thiết kế caching, timeouts, circuit breaker và hậu quả privacy. Có thể kiểm tra tại control plane để quyết định trusted key set và giới hạn hiệu lực theo policy; cần phối hợp với security team về mô hình chính xác.

## 13. Sự cố mất khóa, compromise và phản ứng khẩn cấp

Một khóa ký bị lộ khác hoàn toàn một cert quá ngày hết hạn. Với **private signing key compromise**, attacker có thể tạo chữ ký hợp lệ bằng key được SP đang tin. Nếu SP vẫn pin/public key trong registration, chữ ký giả **có thể xác minh toán học đúng**.

Quy trình incident tối thiểu:

1. **Phân loại sự cố:** cert expired bình thường hay private key suspected/confirmed compromise? Không gộp tất cả vào “cert issue”.
2. **Kích hoạt kênh liên hệ IdP/SP:** xác minh danh tính đối tác, dùng out-of-band channel được duyệt cho hành động khẩn.
3. **Ngừng tin key A bị compromise:** gỡ khỏi trusted metadata/registration, invalidate caches và phân phối tới mọi node. Không đợi `notAfter`.
4. **IdP phát key B mới:** public cert được đăng ký qua nguồn có bằng chứng trust độc lập; không lấy từ một bản metadata không xác minh.
5. **Thực thi chính sách phiên:** đánh giá vô hiệu các session được tạo trong khoảng bị ảnh hưởng, logout/step-up và điều tra audit; loại key chỉ chặn **những xác thực mới**, không tự xóa phiên SP cũ.
6. **Giám sát:** metadata version/hash, các fingerprints được tin tại từng node, failed signature, trust-change events, cảnh báo stale.
7. **Rollback có kiểm soát:** chỉ khi có bằng chứng khóa cũ không compromise; không đưa A trở lại để “khôi phục dịch vụ” nếu private key có nguy cơ lộ.
8. **Hậu kiểm:** ghi timeline, nguyên nhân, vai trò approval, bài học và tự động hóa kiểm tra rotation.

Trong mô hình explicit key trust, **CA revocation một mình** không chứng minh SP đã thôi tin key A. Phải xác nhận bằng thực nghiệm SAML Response ký bằng A không còn được chấp nhận trên từng SP node.

## 14. Ma trận QA: điều gì cần kiểm thử?

| ID | Tình huống | Kỳ vọng / điểm cần chứng minh |
| --- | --- | --- |
| C01 | Response ký bằng IdP key A được tin, assertion còn hạn. | Login chỉ thành công nếu signature và toàn bộ SAML conditions đúng. |
| C02 | Response ký bằng key không ở trusted registration. | Từ chối, dù chữ ký tự khớp với cert nhúng trong XML. |
| C03 | IdP cert A `notAfter` đã qua, key A vẫn pinned. | **Đo hành vi thực**; so với policy explicit-key hoặc strict validity, không đoán từ library. |
| C04 | IdP cert chưa tới `notBefore`. | Monitor phát hiện; nếu policy strict, không accept key trước hạn. |
| C05 | Cert trong hạn nhưng bị PKIX revocation. | Nếu PKIX revocation được yêu cầu, bị từ chối; nếu metadata trust, phải gỡ key theo incident policy. |
| C06 | OCSP timeout/unknown hoặc CRL hết hạn. | Xử lý đúng fail-closed/fail-open đã duyệt và phát alert, không gọi UNKNOWN là GOOD. |
| C07 | Metadata ký hợp lệ và A+B khi rollover. | SP chấp nhận A/B trong overlap được phê duyệt, đủ các kiểm tra SAML. |
| C08 | Sau khi IdP ngừng A, metadata chỉ có B và SP đã refresh. | A không còn trusted; B hoạt động. |
| C09 | Key A được xác nhận compromise. | Gỡ A tức thì, cache/node cập nhật, test Response ký A bị từ chối. |
| C10 | Metadata XML signature sai hoặc issuer khác. | Không publish trusted registration mới; alert. |
| C11 | Metadata vượt `validUntil` hoặc cache stale quá policy. | Không dùng stale vô hạn để tin key cũ. |
| C12 | Assertion `Conditions.NotOnOrAfter` đã qua nhưng cert còn hạn. | Từ chối Assertion; cert validity không gia hạn nó. |
| C13 | SubjectConfirmationData đã hết hạn nhưng metadata còn hạn. | Từ chối bearer confirmation không hợp lệ. |
| C14 | SP cert ký AuthnRequest bị IdP từ chối do policy. | Xác định lỗi phía outbound signing, không gỡ kiểm tra IdP response. |
| C15 | SP decryption key B chưa được IdP cập nhật. | EncryptedAssertion có thể lỗi giải mã; phối hợp public/private key rollout. |
| C16 | TLS metadata thành công nhưng metadata chưa verify trust theo policy. | HTTPS không thay XML metadata signature/trust approval. |
| C17 | IdP cung cấp cert self-signed theo hợp đồng explicit-key. | Kiểm tra đúng pinned key/metadata policy, không giả định CA bắt buộc. |
| C18 | Hai IdP có cert/issuer khác nhau nhưng cùng NameID value. | Không tráo trust anchors/tenant; authorization SP độc lập. |
| C19 | Monitor báo cert expired nhưng SSO vẫn thành công. | Nhận ra monitor không là login gate; soát effective policy. |
| C20 | Người dùng đã đăng nhập, sau đó SP gỡ trusted cert bị compromise. | Đánh giá invalidation/session revocation; không coi key removal là logout tự động. |

### 14.1. Kiểm chứng mà không tấn công production

Dùng **IdP test** và bộ cert test trong môi trường biệt lập. Chuẩn bị:

- Cert A hợp lệ, A-expired, A-not-yet-valid và B để thực hiện rotation.
- Signed metadata V1 (chỉ A), V2 (A+B), V3 (chỉ B) bởi metadata signer test được pin.
- Metadata giả mạo/đổi issuer, quá hạn hoặc signature sai.
- Responses ký bằng A/B/cert attacker có cùng Format/NameID thử nghiệm nhưng các điều kiện SAML khác nhau.
- CRL/OCSP mock/test responder nếu mô hình PKIX yêu cầu; không giả vờ một test cert self-signed có CA revocation source nếu không có.

Kiểm thử phải xác nhận **bằng hành vi request thật** hoặc provider integration tests; chỉ quan sát log “loaded certificate” không chứng minh một certificate được chấp nhận hay bị từ chối.

### 14.2. Phân tích nguyên nhân trước khi thay cấu hình

Nếu login lỗi sau rotation, hỏi theo thứ tự:

1. Kết nối metadata có hoạt động? Có proxy/TLS lỗi không?
2. Metadata mới đã được xác minh và publish chưa? Các node đã đồng bộ chưa?
3. Certificate nào được IdP thực sự dùng ký Response/Assertion?
4. SP đang tin fingerprints nào, theo registration/issuer nào?
5. SAML Status, Issuer, Destination/Recipient, Audience, Conditions và InResponseTo có hợp lệ không?
6. Có policy X.509 strict validity/PKIX/revocation được custom không?
7. Nếu Authentication thành công nhưng API 403, kiểm tra **local permission** thay vì chứng thư.

Không giải quyết bằng cách tắt chữ ký, bỏ issuer, tăng clock skew vô hạn hoặc chấp nhận mọi public key trong Response.

## 15. Những ngộ nhận phổ biến

| Nhận định sai | Cách hiểu chính xác |
| --- | --- |
| “Certificate expired thì chắc chắn SAML signature sai toán học.” | Chữ ký toán học và X.509 validity là hai phép kiểm tra khác nhau. |
| “Certificate trong hạn thì không thể bị thu hồi.” | CRL/OCSP hoặc key removal có thể thu hồi trước `notAfter`. |
| “Đặt metadata-uri nghĩa là metadata tự refresh mãi.” | Phụ thuộc repository/resolver/caching và cấu hình thực tế. |
| “HTTPS metadata hoạt động nghĩa là SAML signing cert không bị revoke.” | TLS và SAML trust tách biệt. |
| “CA đã revoke cert, SP pinned cert sẽ tự ngừng tin.” | Không nhất thiết; explicit-key trust thường cần metadata/trust removal. |
| “Có `<ds:X509Certificate>` trong Response là certificate tin cậy.” | Certificate do người gửi cung cấp không thể tự là trust anchor. |
| “`X509Certificate.checkValidity` kiểm tra toàn bộ CRL/OCSP.” | Phương thức này kiểm tra **notBefore/notAfter**. |
| “`validUntil` của metadata là `notAfter` của cert.” | Hạn metadata khác hạn X.509. |
| “`cacheDuration` khiến ứng dụng tự fetch theo lịch.” | Nó là thông tin caching; cơ chế làm mới phải được triển khai/kiểm chứng. |
| “Log WARN certificate expired nghĩa là đã khóa SSO.” | Monitor không làm thay đổi authentication pipeline. |
| “SP đã bỏ key compromised thì các phiên cũ tự hết.” | Session SP/authorization cần chiến lược xử lý riêng. |
| “Spring SAML Extension cũ và SAML2 Login hiện đại có cùng defaults.” | Khác codebase, trust engines và APIs; đừng trộn tài liệu. |
| “Rollover an toàn là thay A bằng B trong một bước.” | Thường cần overlap A+B, nhưng key compromise lại đòi remove khẩn. |
| “Xác minh SAML thành công nghĩa là local admin.” | Authentication và authorization là hai lớp độc lập. |

## 16. Checklist đưa vào production

- [ ] Có inventory IdP/SP signing và decryption certificates theo issuer/registration, fingerprint, owner và thời hạn.
- [ ] Biết **trust model** của từng đối tác: explicit-key/metadata hay PKIX, không dùng tên certificate để đoán.
- [ ] Signature verifier dùng **key đã được tin cậy**; không tin KeyInfo do browser gửi.
- [ ] Có policy rõ: có bắt buộc X.509 validity không, kiểm tra tại đâu, failure behavior thế nào?
- [ ] Có policy riêng về CRL/OCSP hoặc metadata key removal; trạng thái UNKNOWN không bị gọi nhầm GOOD.
- [ ] Metadata đến từ nguồn được duyệt, được xác minh chữ ký khi profile yêu cầu, có expiry/cache/refresh policy.
- [ ] Certificate rollover có overlap, staging, kiểm thử response bằng A và B, kế hoạch xóa A.
- [ ] Key compromise có runbook remove trust nhanh, truyền thông với IdP, đồng bộ mọi node, xem xét session revocation.
- [ ] SP signing/decryption credentials được giữ trong secret manager, không commit private keys vào Git.
- [ ] Có monitor `notBefore/notAfter`, gần hết hạn, tuổi metadata, last successful refresh và fingerprints đang active.
- [ ] Monitor được phân biệt rõ với **runtime enforcement**; có kiểm thử thực sự từ chối certificate trái policy.
- [ ] Chứng thư TLS, signing metadata, signing Assertion và decryption được quản lý riêng theo nhiệm vụ.
- [ ] Không coi cert valid là thay thế `Conditions`, `SubjectConfirmationData`, Audience, Recipient, InResponseTo, replay checks.
- [ ] Có bộ test C01–C20 hoặc tương đương chạy trước và sau rotation.
- [ ] Không log private key, raw SAMLResponse, NameID hay assertion nhạy cảm.
- [ ] Local authorization/tenant isolation vẫn được thực thi kể cả khi SAML authentication hợp lệ.
- [ ] Khi nâng Spring Security/OpenSAML, kiểm tra Javadoc/baseline theo version thực và chạy lại regression tests.

## Ghi nhớ

> **Chữ ký hợp lệ ≠ chứng thư còn hạn ≠ chứng thư chưa bị thu hồi ≠ public key được tin.** Trong SAML2 federation, các khóa ký có thể được tin theo **metadata/explicit key** thay vì PKIX; thời hạn X.509 và CRL/OCSP vì thế **không được mặc định giả định** là các cổng kiểm tra đã có. Hãy dùng trust source được duyệt, vận hành metadata/rotation/revocation, kiểm tra chính sách đã thực thi trên từng Spring Security deployment và giữ authorization của ứng dụng ở một lớp riêng.

### Tài liệu tham khảo

- [OASIS — SAML V2.0 Metadata Interoperability Profile, 2019](https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop-os.html): key trust theo metadata, key rollover và yêu cầu loại khóa bị compromise; không dựa vào CRL/OCSP ở consumer.
- [OASIS — Metadata for SAML V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `KeyDescriptor`, `validUntil`, `cacheDuration`.
- [OASIS — SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): hạn của Assertion/SubjectConfirmation và các ràng buộc giao thức.
- [RFC 5280 — X.509 PKI and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): `notBefore`, `notAfter`, certificate path và CRL.
- [RFC 6960 — Online Certificate Status Protocol](https://www.rfc-editor.org/rfc/rfc6960): trạng thái OCSP và cơ chế kiểm chứng phản hồi.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, verifying credentials và xác thực SAML.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): signature validation và extension points.
- [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): metadata trust, signature verification và metadata repository.
- [Spring Boot 3.3 — Security/SAML2](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): cấu hình SAML2 relying party.
- [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): rủi ro certificate revocation, key compromise và các biện pháp phòng vệ.
