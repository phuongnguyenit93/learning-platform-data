# Phân biệt nhận diện khóa tin cậy từ metadata với xác minh chuỗi PKI

## 1. Bài toán thực tế trong Spring Security SAML2

Khi ứng dụng **Spring Security** là **Service Provider (SP/Relying Party)** và nhận **SAMLResponse** từ **Identity Provider (IdP/Asserting Party)**, SP phải xác minh chữ ký số bằng một khóa công khai mà SP **được phép tin**. Câu hỏi khó không chỉ là “chữ ký có đúng về mặt toán học không?”, mà còn là:

- **Khóa công khai nào** được phép dùng để xác minh bản tin của **IdP cụ thể**?
- Khóa ấy lấy từ **metadata SAML đã được xác thực/chấp nhận** hay từ một **chứng chỉ xây được chuỗi lên Certificate Authority (CA)**?
- **X.509Certificate** trong metadata có luôn phải còn hạn, có tên chủ thể giống hostname, có Extended Key Usage cho TLS và được CA công cộng ký không?
- **Chữ ký trên metadata**, **chữ ký trên SAML Response/Assertion**, **TLS HTTPS**, **PKIX certification path** và **public-key pinning** có cùng ý nghĩa không?
- Nếu IdP xoay khóa, đổi chứng thư nhưng giữ public key, hoặc đổi CA, SP có nên chấp nhận bản tin mới không?

**Ý chính:** trong nhiều federation SAML, **chứng chỉ trong SAML metadata là một phương tiện chuyên chở public key của đối tác**, và **quyết định tin khóa** xuất phát từ **metadata đã được chấp nhận**. Điều này khác với **PKIX path validation** (xây và kiểm chuỗi chứng thư X.509 từ leaf đến CA trust anchor). Không nên coi hai mô hình là tương đương hay áp đặt một mô hình lên mô hình kia một cách vô thức.

Theo **OASIS SAML V2.0 Metadata Interoperability Profile 1.0 (24-10-2019)**, khi đã chấp nhận một metadata instance theo profile, bên tiêu thụ **dựa vào khóa của các KeyDescriptor thuộc đúng role**; profile yêu cầu **không áp dụng thêm kiểm tra X.509 path/revocation/OCSP cho các khóa ấy trong quyết định runtime**. Đây là quy tắc **của profile cụ thể**, không phải tuyên bố rằng PKIX vô dụng hoặc mọi sản phẩm/tổ chức SAML đều bắt buộc chọn cùng trust model. Hệ thống sử dụng **trust policy dựa trên PKIX** cho metadata exchange, TLS hoặc một cơ chế federation khác phải xác định đúng nơi và đúng điều kiện áp dụng.

### Học xong phải giải thích được

1. **EntityDescriptor/IDPSSODescriptor/KeyDescriptor** liên kết public key với IdP entityID thế nào.
2. Sự khác nhau giữa **public key**, **X.509 certificate**, **certificate fingerprint**, **SPKI fingerprint**, **certificate chain**, **PKIX trust anchor** và **SAML signature**.
3. Điều gì làm **metadata đáng tin** trước khi SP có thể tin public key chứa trong đó.
4. Tại sao **IdP SAML signing certificate tự ký** vẫn có thể được dùng hợp lệ trong mô hình metadata trust.
5. Tại sao **certificate hợp lệ PKIX của một IdP lạ** không đủ để đăng nhập SP.
6. Cách cấu hình **Spring Security SAML2 SP** với metadata/certificate, kiểm thử xoay khóa và chẩn đoán lỗi mà không tắt xác minh chữ ký.

Bài tập dùng **Java 17+**, ví dụ **Spring Boot 3.3.5 / Spring Security 6.x**. Mọi domain example.org và dữ liệu khóa mô phỏng chỉ dành cho học tập.

## 2. Trước hết: chữ ký đúng khác “khóa được tin cậy”

Một sơ đồ quyết định hợp lý:

~~~text
Browser đưa SAMLResponse vào SP ACS
           |
           v
  Chọn RelyingPartyRegistration
  (đúng SP/IdP theo cấu hình và ngữ cảnh)
           |
           v
  Lấy public verification key của IdP đã được PHÊ DUYỆT
  qua trusted metadata hoặc cấu hình tĩnh tương ứng
           |
           v
  Kiểm chứng XML Signature với khóa đó
           |
           +-- Sai -> FAIL, không tạo Authentication
           |
           v
  Kiểm issuer, audience, destination, Recipient,
  thời gian, InResponseTo, profile, replay...
           |
           +-- Sai -> FAIL
           |
           v
  Saml2Authentication hợp lệ -> local session/authorization
~~~

**Chữ ký đúng về mật mã** nghĩa là các byte được ký khớp với chữ ký khi kiểm bằng **một public key cụ thể**. Điều đó **chưa đủ chứng minh** public key ấy được quyền đại diện cho IdP mà SP đang đăng nhập.

Ví dụ: attacker tạo cặp RSA riêng và ký một Assertion giả. **Signature.verify()** sẽ trả true nếu kiểm bằng public key của attacker. Nhưng SP không được coi đó là IdP Corp nếu **public key attacker không được IdP Corp công bố qua trust channel đã được chấp nhận**.

Chiều ngược lại, ngay cả khi chữ ký được kiểm bằng đúng khóa IdP đã tin cậy, Response vẫn có thể bị từ chối vì **issuer, AudienceRestriction, Destination, SubjectConfirmationData.Recipient, InResponseTo, NotOnOrAfter** hoặc quy tắc nghiệp vụ không hợp lệ.

### Bốn vai trò an ninh khác nhau

| Lớp | Đối tượng | Câu hỏi nó trả lời |
| --- | --- | --- |
| **SAML metadata trust** | Metadata XML được nhận, xác minh nguồn/chữ ký và chấp nhận theo policy. | Đối tác nào, role nào, public key nào được phép sử dụng? |
| **XML Digital Signature** | Chữ ký trên Response, Assertion, AuthnRequest hoặc metadata. | Bản tin không bị sửa và được ký bằng private key tương ứng public key nào? |
| **PKIX certificate path** | Chuỗi X.509 leaf → intermediate → CA trust anchor. | Chứng thư được một CA tin cậy chứng nhận theo chính sách PKIX không? |
| **TLS/HTTPS** | Kết nối giữa trình duyệt, SP, IdP hoặc khi tải metadata. | Kênh đến hostname/certificate hợp lệ có được bảo vệ và xác thực theo TLS policy không? |

**Không được lấy một lớp thay thế mọi lớp còn lại.**

## 3. Metadata mô tả khóa của IdP ở vị trí nào?

Trong metadata IdP, **EntityDescriptor.entityID** định danh thực thể; **IDPSSODescriptor** mô tả vai trò IdP; **KeyDescriptor** chứa thông tin khóa công khai cho mục đích ký hoặc mã hóa.

~~~text
md:EntityDescriptor entityID="https://idp.example.org/saml"
  └── md:IDPSSODescriptor
        ├── md:KeyDescriptor use="signing"
        │     └── ds:KeyInfo
        │           └── ds:X509Data
        │                 └── ds:X509Certificate
        ├── md:KeyDescriptor use="signing"       (nếu đang rotation)
        └── md:SingleSignOnService
~~~

Ví dụ XML học tập:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/saml">

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>
            PUBLIC_X509_CERTIFICATE_BASE64_FROM_TRUSTED_IDP
          </ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Đây chỉ là fragment minh họa:** giá trị certificate là mô tả, không phải Base64 DER X.509 hợp lệ. Không import fragment như metadata thật. **SP không bao giờ nhận private key của IdP**; SP dùng public key để xác minh bản tin IdP đã ký.

### KeyDescriptor và trường use

| Vị trí / mục đích | Cách hiểu đúng |
| --- | --- |
| **IDPSSODescriptor → KeyDescriptor use="signing"** | Public key của **IdP** dùng để SP kiểm chữ ký của Response/Assertion/Logout message IdP phát hành theo hợp đồng. |
| **IDPSSODescriptor → KeyDescriptor use="encryption"** | Thông tin khóa cho mục đích mã hóa liên quan role IdP, không mặc nhiên là khóa ký Assertion. |
| **SPSSODescriptor → KeyDescriptor use="signing"** | Public key của **SP**, để IdP kiểm chữ ký AuthnRequest/Logout message SP gửi. |
| **SPSSODescriptor → KeyDescriptor use="encryption"** | Public key của **SP**, để IdP mã hóa dữ liệu mà SP sẽ giải mã bằng private key SP. |
| **KeyDescriptor không có use** | Trong SAML metadata, không được tự coi là chỉ encryption hoặc chỉ signing; xem ý nghĩa mặc định theo đặc tả/profile và policy triển khai. |

Role rất quan trọng. **Không lấy certificate từ SPSSODescriptor để xác minh Assertion IdP**, không lấy certificate từ website HTTPS IdP theo thói quen và không chọn khóa bất kỳ chỉ vì cùng CA.

Trong SAML metadata, **ds:KeyInfo** có thể chứa **ds:X509Certificate** hoặc **ds:KeyValue**. Cả hai có thể biểu diễn **public key**. OASIS Metadata Interoperability Profile nhấn mạnh trường hợp dùng X509Certificate như **vỏ chứa khóa**, không phải mặc định yêu cầu phải chứng minh một CA chain đối với cert đó.

## 4. “Nhận diện khóa tin cậy từ metadata” là gì?

Một hệ thống triển khai **metadata-based trust** thực hiện hai pha khác nhau.

### Pha A: chấp nhận metadata một cách an toàn

Trước tiên phải xác định metadata do **đúng đối tác/federation operator** phát hành và được phép áp dụng. Tùy thiết kế, nguồn có thể được đảm bảo bằng:

- **Metadata XML Signature**: kiểm chữ ký bằng **metadata signing key/trust anchor được cấu hình từ trước, ngoài băng**.
- **HTTPS + origin được phê duyệt**, cùng kiểm soát quyền quản trị/cấp phát; mức độ đủ hay chưa tùy threat model.
- **File metadata qua quy trình change-management an toàn**, so fingerprint, ký phê duyệt hoặc cung cấp qua kênh có xác thực.
- **Federation aggregator đã được tin**, có signature chain và chính sách lọc entity/role/trust phù hợp.

Ngay cả khi metadata có **ds:Signature**, không thể lấy một certificate tự khai báo trong chính XML đó rồi bảo rằng **tài liệu tự chứng minh mình đáng tin**. Phải có **trust anchor được cấu hình độc lập**, xác minh signed bytes/reference, chống XML Signature Wrapping, kiểm entityID mong đợi và thời gian.

Metadata có thể có **validUntil** và **cacheDuration**. Phải theo policy refresh, chống replay một bản metadata cũ chứa khóa đã bị loại bỏ, và không dùng cache vô thời hạn để che sự cố.

### Pha B: dùng khóa sau khi metadata được chấp nhận

Sau khi bên tiêu thụ **đã chấp nhận** metadata và chọn đúng:

~~~text
EntityDescriptor.entityID = IdP Corp
  -> IDPSSODescriptor hỗ trợ SAML2
      -> KeyDescriptor use=signing
          -> public key K1, K2
~~~

thì **K1/K2** là các khóa verification ứng viên **được ủy quyền cho IdP Corp ở vai trò ký**, theo phiên bản metadata/policy đã chấp nhận. Lúc runtime, SP kiểm XML Signature bằng các khóa ấy, rồi kiểm toàn bộ ràng buộc SAML.

**Không phải** thuật toán: tải metadata từ URL do browser đưa vào → lấy bất kỳ certificate nào trong đó → tự coi issuer đáng tin → cho login.

### Khi nào có hai khóa cùng lúc?

IdP rotation có thể công bố **KeyDescriptor use=signing cho K1 (cũ)** và **K2 (mới)** trong thời gian chuyển tiếp. Khi metadata mới đã được phê duyệt, SP có thể xác minh chữ ký dùng một trong các key được role cho phép; tuy nhiên vẫn phải kiểm issuer/response validity và policy signing algorithms.

Lịch rotation được phê duyệt thường:

1. IdP tạo khóa K2, giữ private key an toàn.
2. IdP công bố K1 và K2 trong metadata mới.
3. SP nhận/kiểm nguồn và chấp nhận metadata mới; theo dõi readiness.
4. IdP chuyển ký message bằng K2.
5. Sau thời gian chồng lấn, IdP loại K1 ra metadata.
6. SP refresh, ngừng chấp nhận K1 đúng chính sách; không giữ K1 vô hạn.

**KeyDescriptor đa khóa không phải là chain X.509 gồm leaf/intermediate/root.** Mỗi KeyDescriptor thường mô tả một khóa có thể dùng, không mặc nhiên là “bước tiếp theo của CA chain”.

## 5. PKIX path validation là gì?

**PKIX** (theo **RFC 5280**, Java có **CertPathValidator/PKIXParameters**) dùng tập quy tắc để xác minh **đường chứng nhận X.509**:

~~~text
Leaf certificate (Subject = service)
   signed by Intermediate CA
        |
        v
Intermediate CA certificate
   signed by Root CA
        |
        v
Trust Anchor / Root CA đã cài trong trust store
~~~

Một phép kiểm PKIX có thể gồm:

1. Xây **certification path** từ leaf lên một **trust anchor** được tin.
2. Kiểm **chữ ký của từng certificate** trong đường và constraints cho CA.
3. Kiểm **notBefore/notAfter** của chứng thư theo validation time.
4. Kiểm **Basic Constraints**, **KeyUsage**, **path length** và các critical extensions có liên quan.
5. Kiểm **certificate policy/name constraints**, Extended Key Usage nếu trường hợp sử dụng yêu cầu.
6. Kiểm trạng thái thu hồi **CRL/OCSP** nếu chính sách triển khai yêu cầu và cơ chế revocation được bật/cấu hình đúng.
7. Sau khi có chain hợp lệ, vẫn phải xác minh **ràng buộc danh tính**: certificate đại diện cho hostname/service/entity nào trong ngữ cảnh?

**PKIX path hợp lệ không xác nhận tự động “đây là IdP Corp được SP cho phép”.** Một CA công cộng có thể cấp certificate hoàn toàn hợp lệ cho attacker.example.org; điều đó không biến attacker thành **https://idp.corp.example.org/entity**. Phải có chính sách mapping issuer/entityID, role và đối tác.

### Trường hợp TLS HTTPS

Khi SP tải metadata từ **https://idp.example.org/metadata**, HTTPS client thường thực hiện PKIX/TLS chain verification của **server certificate**, và xác minh hostname theo TLS policy. Điều này bảo vệ kết nối HTTP đến nguồn metadata.

**TLS certificate của hostname idp.example.org không nhất thiết là SAML signing certificate của IdP**. IdP có thể dùng một public CA cert cho TLS, một private/self-signed X.509 chứa khóa ký SAML và một khóa thứ ba để ký metadata.

### Trường hợp PKIX để tin metadata

Một federation có thể dùng **CA/PKIX** để xác minh **chứng thư của metadata signer** hoặc bảo vệ kênh tải metadata, tùy quy trình. Đây là PKIX **trong bước chấp nhận metadata**, không nhất thiết là PKIX trên **KeyDescriptor signing** mỗi khi xác minh SAMLResponse.

Cần phân biệt:

~~~text
PKIX/TLS chứng minh nguồn metadata là endpoint được phép
               |
               v
Xác minh metadata XML Signature khi policy yêu cầu
               |
               v
CHẤP NHẬN metadata của đúng IdP/entity/role
               |
               v
Lấy public key IdP signing được ủy quyền
               |
               v
Xác minh SAMLResponse/Assertion XML Signature
               |
               v
Kiểm issuer, audience, thời gian, subject confirmation...
~~~

Nếu doanh nghiệp chọn **PKIX-based signature trust** ngoài Metadata Interoperability Profile, phải thiết kế validator và name/entity binding cụ thể. Không được mặc nhiên suy ra rằng Spring Security SAML2 SP đã kiểm PKIX path/revocation cho mọi KeyDescriptor.

## 6. Đối chiếu hai mô hình: metadata trust và PKIX

| Tiêu chí | **Metadata-based trust** | **PKIX trust model** |
| --- | --- | --- |
| **Nguồn tin cậy** | Metadata đã được phê duyệt, đúng entityID/role, có trust trong quá trình phân phối. | CA trust anchors + certification path và chính sách certificate. |
| **Đối tượng kiểm** | Public key dùng ký/ mã hóa được công bố cho entity/role cụ thể. | Certificate leaf/intermediate và chain tới CA. |
| **Xác nhận khóa của IdP Corp** | Key nằm trong **KeyDescriptor signing của đúng IDPSSODescriptor** trong metadata đã tin. | Chain hợp lệ **cộng thêm** ánh xạ khóa/certificate đúng IdP Corp. |
| **Certificate tự ký** | Có thể phù hợp nếu khóa nằm trong metadata đã chấp nhận. | Thường không tạo path tới external CA; chỉ hợp lệ nếu được cấu hình làm trust anchor/trust theo policy. |
| **Certificate hết notAfter** | Theo Metadata IOP, thông tin đó không được dùng để bác bỏ key đã chấp nhận khi xử lý runtime; cần rotation/metadata lifecycle có quản trị. | Thường làm path validation thất bại với thời điểm hiện tại (ngoại trừ chi tiết trust-anchor/policy). |
| **CA chain và certificate issuer** | Không phải căn cứ runtime trong Metadata IOP. | Thành phần cốt lõi của path validation. |
| **CRL/OCSP** | Theo Metadata IOP, không kiểm online/offline revocation của role keys; thay bằng cập nhật/loại key khỏi metadata. | Có thể là thành phần bắt buộc của cert revocation policy. |
| **Khóa mới** | Chấp nhận khi metadata đã được trust và thêm KeyDescriptor hợp lệ. | Phải chain tới CA tin cậy và được gắn đúng danh tính theo policy. |
| **Điểm dễ sai** | Tin metadata chưa được xác minh hoặc cache metadata cũ vô hạn. | Tin mọi leaf cert do CA cấp mà không ràng buộc IdP entityID/role. |
| **Spring Security SP mặc định** | Thường cấu hình verification credentials được nạp từ IdP metadata hoặc cert được chỉ định. | **Không tự khẳng định** có PKIX path/revocation cho SAML signing cert; phải kiểm implementation/config. |

### Vì sao cùng certificate lại có hai kết luận khác nhau?

Giả sử **cert S** là X.509 **self-signed**, notAfter đã qua, nhưng chứa public key K được IdP Corp công bố trong metadata đã được xác minh và chưa bị thay thế:

- Theo **OASIS Metadata Interoperability Profile**, khi metadata đã chấp nhận, SP có thể dùng **K để xác minh chữ ký SAML** và **không thêm PKIX/date/OCSP check cho key runtime**. Đây là quy tắc interoperability của profile, **không có nghĩa nên bỏ quản lý certificate lifecycle**: các chứng thư hết hạn cần được thay thế theo vận hành.
- Với **PKIX path validation** đến corporate CA riêng, certificate self-signed/expired này có thể **không xây được chain hợp lệ** và bị từ chối. Đây là cơ chế tin cậy khác, không tự tương đương.

Ngược lại, cert T có chain hợp lệ đến một public CA và chưa hết hạn, nhưng **không nằm trong IdP Corp metadata đã được tin**:

- PKIX có thể xác minh T là một leaf cert hợp lệ cho tên nào đó.
- **SP vẫn không được dùng T để tin Assertion tự nhận là Corp**, nếu không có binding tin cậy giữa T và IdP Corp trong mô hình SAML đang triển khai.

## 7. Quy tắc đặc biệt của OASIS Metadata Interoperability Profile

**SAML V2.0 Metadata Interoperability Profile Version 1.0** (OASIS Standard, 2019) mô tả một mô hình trust dựa trên **metadata acceptance**:

1. Metadata được phân phối và chấp nhận qua một **cơ chế có xác thực/ quản trị**. Profile không định nghĩa cụ thể phải dùng HTTPS, XML Signature hay phương pháp phê duyệt nào; đó là tiền đề vận hành.
2. **KeyDescriptor** thuộc từng role là nguồn chỉ định những khóa mà entity/role được phép sử dụng.
3. Với **ds:X509Certificate**, theo profile, certificate chủ yếu dùng để **truyền public key**; không dựa vào certificate Subject, Issuer, validity hay EKU trong quyết định runtime của role key.
4. Sau khi chấp nhận metadata, consumer **không bổ sung X.509 path validation, CRL hoặc OCSP check** vào thời điểm chấp nhận/chạy các role keys. **Đây là nghĩa vụ nếu triển khai đúng profile này**, không phải quy tắc “mọi ứng dụng PKIX đều phải tắt revocation”.
5. Khóa bị compromise phải được **loại khỏi metadata**, metadata được **refresh** theo chính sách; validUntil giúp chống metadata cũ bị phát lại. **cacheDuration một mình không phải chống replay đủ mạnh**.

Một hiểu lầm là “SAML không cần xác thực chứng chỉ, vậy cứ tải metadata bất kỳ”. Sai: nếu tin metadata chưa được xác minh, attacker có thể **thay KeyDescriptor và tự cấp trust**, khiến chữ ký giả được xác minh bằng khóa của attacker. **Trust tại bước nhập metadata trở nên quan trọng hơn**, không kém.

Một hiểu lầm khác là “không PKIX thì certificate hết hạn cứ dùng mãi mãi”. Sai: dù profile không dùng **notAfter** để reject runtime role key, tổ chức vẫn phải bảo vệ lifecycle khóa, key compromise, thuật toán, độ dài khóa, metadata validity và kiểm tra rotation. Phải phân biệt **quy tắc profile runtime** và **chính sách vận hành/key hygiene**.

### Khi nào vẫn dùng PKIX?

- **TLS HTTPS** khi tải metadata hoặc trao đổi SOAP/back-channel: có TLS trust, hostname validation và policy riêng.
- **Xác minh metadata signer**: có thể dùng key pinning hoặc PKIX với trust anchors và binding phù hợp; quyết định trước khi chấp nhận metadata.
- **Federation khác không áp dụng Metadata IOP**: có thể dùng PKIX message-signature trust nếu tất cả bên thống nhất và triển khai đúng mapping issuer/role; điều này không phải hành vi được suy ra tự động từ KeyDescriptor.
- **Nội bộ tổ chức có CA riêng**: PKIX có thể là một lớp trong quy trình onboarding, nhưng vẫn cần SAML-specific entityID/role trust.

Không gán chính sách **CRL/OCSP** của TLS sang tất cả **SAML signing certificates** nếu stack đang tuân Metadata IOP; cũng không tắt CRL/OCSP của TLS chỉ vì SAML metadata dùng mô hình public-key trust.

## 8. Chứng chỉ X.509, public key và fingerprint khác nhau thế nào?

Một X.509 certificate chứa nhiều trường:

~~~text
X.509 Certificate
  - Subject
  - Issuer
  - Serial Number
  - notBefore / notAfter
  - SubjectPublicKeyInfo (SPKI) -> PUBLIC KEY
  - Signature Algorithm / Certificate Signature
  - KeyUsage / ExtendedKeyUsage / SAN / BasicConstraints ...
~~~

**Certificate fingerprint** thường là SHA-256 trên **toàn bộ byte DER encoded certificate**. **SPKI fingerprint** là SHA-256 trên **DER SubjectPublicKeyInfo**, tức phần đại diện khóa công khai. Hai fingerprint **khác nhau** và có ý nghĩa so khớp khác nhau.

| Thao tác | Đối tượng được so | Điều khẳng định được |
| --- | --- | --- |
| **Exact certificate pin** | SHA-256 trên toàn bộ DER certificate. | Certificate giống byte-for-byte certificate đã phê duyệt. |
| **Public key/SPKI pin** | SHA-256 trên encoded SubjectPublicKeyInfo. | Public key giống nhau dù certificate được cấp lại với trường/serial/expiry khác. |
| **PKIX validation** | Chain X.509 tới CA trust anchor. | Path và policies hợp lệ, chưa chứng minh binding với SAML issuer nếu thiếu bước riêng. |
| **XML Signature verification** | Signed XML bytes + signature + public key candidate. | Signed content phù hợp với private key tương ứng. |
| **SAML trust decision** | Metadata acceptance, entityID/role, verification key, profile policies. | Chỉ chấp nhận bản tin do đúng đối tác phát và dành cho đúng SP. |

**Không so MD5/SHA-1 certificate fingerprint để quyết định trust mới**. Ưu tiên **SHA-256** khi ghi fingerprint kiểm toán; bản thân thuật toán chữ ký SAML và key size còn phải theo policy hiện hành.

### Cùng public key, khác certificate

IdP có thể được cấp **cert B mới** với serial, validity, issuer khác cert A nhưng giữ **cùng public key**:

- **Certificate fingerprint A ≠ B**, nên exact-certificate pin sẽ phát hiện khác.
- **SPKI fingerprint A = B**, nên public-key pin vẫn khớp.
- Theo metadata IOP, việc tin key liên quan **public key** đã chấp nhận trong metadata, nhưng vận hành cần kiểm cert rollover đúng policy; không lấy key so khớp làm lý do bỏ qua metadata expiry/compromise.
- PKIX path của cert A/B có thể có kết quả khác vì issuer/validity/CA khác, dù public key giống hệt.

Ngược lại, hai certificate có cùng Subject như “CN=Corporate IdP” **không chứng minh** chúng có cùng key hoặc cùng quan hệ tin cậy. Chỉ so subject name là quá yếu.

## 9. Không được tin ds:KeyInfo từ SAMLResponse một cách vòng tròn

XML Signature bên trong SAMLResponse/Assertion có thể chứa **ds:KeyInfo**, đôi khi chứa certificate do bên gửi tự đính kèm.

**Quy tắc an toàn:**

- **KeyInfo từ bản tin chưa được xác minh** có thể là **gợi ý để tìm khóa**, không phải nguồn cho phép runtime tự “thêm trusted certificate”.
- SP phải ràng buộc key candidate với **IdP đã đăng ký / RelyingPartyRegistration / metadata được phê duyệt**.
- Sau khi tìm được key tin cậy, SP mới xác minh cryptographic signature và điều kiện SAML.
- Không làm: lấy cert từ Assertion.KeyInfo → thử verify thấy true → coi issuer bất kỳ là đối tác đáng tin.
- Nếu message không chứa KeyInfo hoặc khác certificate ở metadata nhưng cùng public key, chính sách định danh khóa và thư viện có thể vẫn tìm được key; đừng mặc định phải so chuỗi Base64 certificate y hệt nếu trust model là public key.

Ví dụ tấn công tư duy:

~~~text
Kẻ tấn công:
  tạo RSA keypair A
  tạo Assertion Issuer="https://corp-idp.example.org"
  ký Assertion bằng private A
  nhúng public cert A vào ds:KeyInfo

SP bị lỗi:
  verify bằng cert A lấy ngay từ message -> true
  cho login mà không so với trusted IdP metadata -> BỊ GIẢ MẠO

SP đúng:
  lookup Corp IdP đã đăng ký
  lấy K1/K2 từ trusted metadata của Corp IdP
  chữ ký bằng A không khớp -> REJECT
~~~

**Một chữ ký đúng với khóa không được ủy quyền = phản hồi không tin cậy.**

## 10. Ký metadata và ký Assertion: hai tài sản khác nhau

Có ít nhất ba loại khóa thường xuất hiện:

1. **IdP SAML signing key:** ký Assertion/Response do IdP phát hành; SP kiểm bằng KeyDescriptor signing của IdP.
2. **SP SAML signing key:** ký AuthnRequest/LogoutRequest do SP phát; IdP kiểm bằng KeyDescriptor signing của SP.
3. **Metadata signer key:** ký tệp metadata hoặc federation aggregate; SP/IdP kiểm theo trust anchor của **nguồn metadata**.

Metadata signer có thể là **federation operator**, không phải IdP. Đừng lấy **certificate ký Assertion** thay mặc định cho **certificate ký metadata**, và đừng lấy certificate của HTTPS server làm metadata signer nếu không có hợp đồng.

### Chữ ký metadata không có nghĩa mọi khóa trong metadata là hợp lệ mãi mãi

Metadata cần:

- Đúng **entityID/role** và nguồn phân phối đã được phê duyệt.
- **Chữ ký metadata hợp lệ** khi chính sách yêu cầu, bằng credential đã được biết trước.
- **validUntil** chưa qua, cache/refresh phù hợp; kiểm tra rollback/replay metadata cũ.
- Không có khóa/role bất thường, endpoint SSO/ACS lạ hoặc thay đổi ngoài lịch chuyển khóa.
- Giám sát thay đổi key với trạng thái **approved/pending/revoked** của tổ chức.
- Loại ngay khóa bị compromise khỏi metadata, xuất metadata mới và cập nhật các bên; không chỉ đợi expiry của X.509 certificate.

Một metadata file **vẫn được ký hợp lệ bằng một signer được tin cậy** nhưng **đã hết validUntil** không thể mặc định dùng mãi. Tình huống này khác với certificate “notAfter” của một **role key** trong metadata IOP.

### Tại sao HTTPS chưa đủ nếu dùng metadata federation aggregate?

HTTPS bảo vệ kết nối tới host mà client yêu cầu. Nhưng metadata aggregate có thể được lưu qua nhiều nguồn/mirror, đi qua CDN/proxy, hoặc chứa hàng trăm entity. Chữ ký metadata bằng key của federation operator và chính sách entity filtering giúp phân biệt “nội dung được một nguồn federation phê duyệt” với “XML vừa tải từ một server HTTPS”. Mô hình chính xác phụ thuộc tổ chức.

## 11. Spring Security SP: verification credentials nằm ở đâu?

Với **Spring Security Servlet**, **RelyingPartyRegistration** liên kết SP với IdP; phần **asserting party metadata** chứa **IdP entityID, SSO URL và verification X.509 credentials**.

~~~text
RelyingPartyRegistration(registrationId="corp")
  SP:
    entityId = https://app.example.com/saml2/service-provider-metadata/corp
    ACS = https://app.example.com/login/saml2/sso/corp
    signing credentials = private key/cert của SP (nếu cần)
  IdP:
    entityId = https://idp.example.org/saml
    SSO URL = https://idp.example.org/sso
    verification X509 credentials = public cert(s) của IdP
~~~

Khi nhận Response, OpenSAML provider dùng verification credentials của đối tác đã đăng ký để kiểm chữ ký theo chính sách. **Việc đăng ký một Saml2X509Credential.verification(cert)** là khai báo **certificate tin cậy cho mục đích xác minh bản tin SAML**; **không tự động là yêu cầu thực hiện CertPathValidator PKIX** trên certificate đó.

### Cách A: đọc metadata IdP qua URL được phê duyệt

Ví dụ **Spring Boot 3.3.5, Java 17**:

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>saml-key-trust-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
        </repository>
    </repositories>
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
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
~~~

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "${SAML_IDP_METADATA_URI}"

server:
  port: 8080
~~~

**SAML_IDP_METADATA_URI** phải là metadata URL IdP thật, đã được phê duyệt. Cấu hình này để Spring Boot đọc metadata và thiết lập registration. **Không được suy ra từ việc đọc metadata thành công rằng XML Signature của metadata đã được xác minh**, hay rằng certificate được kiểm chuỗi PKIX; việc xác minh metadata signature/refresh cần cơ chế và cấu hình phù hợp phiên bản/framework.

Một số tính năng mới, ví dụ **OpenSaml5AssertingPartyMetadataRepository** và metadata signature verifier, thuộc Spring Security mới hơn. **Không sao chép import/API của Spring Security 7.x vào dự án Boot 3.3.5** mà chưa xác nhận tương thích.

### Cách B: chỉ định certificate IdP tin cậy bằng cấu hình tĩnh

Nếu tổ chức quản lý IdP signing cert qua **quy trình onboarding có phê duyệt** và không tải metadata tự động, có thể dùng cấu hình sau **thay thế**, không trộn vô tội vạ với metadata-uri ở trên.

**src/main/resources/application.yml (phương án thay thế)**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/corp-idp-signing.crt"
              singlesignon:
                url: "https://idp.example.org/sso"

server:
  port: 8080
~~~

**corp-idp-signing.crt** phải là public X.509 certificate của IdP **được thu nhận/xác minh ngoài băng** (không tải từ input browser). Đường file là ví dụ cấu hình, không có file thực. Khi cert rotation, phải cập nhật cấu hình tĩnh và triển khai có kiểm soát; tránh giữ cert cũ bị compromise.

**Cách A và B** đều là phương pháp lấy **verification credentials đã tin cậy** cho Spring. **Không mô tả chúng như một PKIX path validator**. Nếu doanh nghiệp bắt buộc kiểm chuỗi PKIX ở lớp nào đó, cần cấu hình và kiểm thử lớp đó riêng.

### Application và SecurityFilterChain

**src/main/java/com/example/samltrust/SamlTrustApplication.java**

~~~java
package com.example.samltrust;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlTrustApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlTrustApplication.class, args);
    }
}
~~~

**src/main/java/com/example/samltrust/SecurityConfig.java**

~~~java
package com.example.samltrust;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**src/main/java/com/example/samltrust/ProfileController.java**

~~~java
package com.example.samltrust;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/")
    public String home() {
        return "SAML key trust SP ready";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return "NameID=" + principal.getName();
    }
}
~~~

Các điều kiện để chạy trọn SSO:

- Có **IdP thực và metadata/cert IdP tin cậy**;
- SP entityID và ACS đã được IdP đăng ký chính xác, URL công khai HTTPS trong production;
- IdP ký Response hoặc Assertion theo yêu cầu, SP kiểm đúng signing key;
- Nếu IdP đòi SP ký AuthnRequest, thêm signing credentials SP và công bố public certificate SP;
- Nếu dùng encrypted Assertion, bổ sung private decryption key SP;
- Không có lỗi issuer, audience, destination, time, InResponseTo, Recipient và replay.

Chạy:

~~~bash
mvn spring-boot:run
~~~

**Kết quả có thể kiểm tra, không cần IdP để hiểu endpoint công khai:**

- **GET http://localhost:8080/** trả chính xác **SAML key trust SP ready** nếu ứng dụng khởi động thành công.
- **GET http://localhost:8080/saml2/metadata/corp** xuất metadata **SPSSODescriptor** theo registration corp.
- **GET http://localhost:8080/saml2/authenticate/corp** gửi browser tới IdP SSO endpoint nếu metadata/cấu hình IdP hợp lệ.
- **GET http://localhost:8080/me** cần SAML login; sau Response/Assertion hợp lệ, body có dạng **NameID=<giá trị IdP phát hành>**, không dự đoán được trước.

Spring Security đã cấu hình verification credentials **không đồng nghĩa PKIX path validation cho SAML key đã diễn ra**. Việc thực sự hoàn tất login phải dựa vào kết quả xác minh chữ ký và các điều kiện SAML với IdP thật.

## 12. Java 17 độc lập: kiểm public key được ủy quyền và chữ ký

Ví dụ Java dưới đây dùng hoàn toàn **JDK 17**, không cần Spring hoặc IdP, để minh họa khác biệt giữa:

1. **Public key đã được chấp nhận ngoài băng**, tương tự K1 trong metadata của IdP đã tin;
2. **Public key khác do bên lạ đưa vào**;
3. **Chữ ký đúng/không đúng** với từng key.

Chương trình **tạo khóa RSA thử nghiệm trong bộ nhớ**, ký một thông điệp văn bản và kiểm chứng bằng các public key. Nó **không phải SAML XML Signature validator**, không parse metadata XML, không kiểm PKIX, không dùng private key production. Việc sinh khóa random không làm thay đổi stdout boolean nêu dưới.

**KeyTrustDemo.java**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.Signature;

public class KeyTrustDemo {
    static byte[] spkiHash(PublicKey key) throws Exception {
        return MessageDigest.getInstance("SHA-256")
                .digest(key.getEncoded());
    }

    static boolean verify(PublicKey key, byte[] data, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair trustedIdp = generator.generateKeyPair();
        KeyPair untrusted = generator.generateKeyPair();

        byte[] data = "test-message".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(trustedIdp.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        // Mô phỏng public key của IdP lấy từ metadata đã phê duyệt.
        PublicKey enrolledKey = trustedIdp.getPublic();

        boolean sameKey = MessageDigest.isEqual(
                spkiHash(enrolledKey), spkiHash(trustedIdp.getPublic()));
        boolean otherKey = MessageDigest.isEqual(
                spkiHash(enrolledKey), spkiHash(untrusted.getPublic()));
        boolean validTrusted = verify(enrolledKey, data, signature);
        boolean validOther = verify(untrusted.getPublic(), data, signature);
        boolean altered = verify(enrolledKey,
                "altered-message".getBytes(StandardCharsets.UTF_8),
                signature);

        System.out.println("trusted key match: " + sameKey);
        System.out.println("untrusted key match: " + otherKey);
        System.out.println("signature with trusted key: " + validTrusted);
        System.out.println("signature with other key: " + validOther);
        System.out.println("signature after alteration: " + altered);
        System.out.println("PKIX validation performed: false");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac KeyTrustDemo.java
java KeyTrustDemo
~~~

**stdout chính xác:**

~~~text
trusted key match: true
untrusted key match: false
signature with trusted key: true
signature with other key: false
signature after alteration: false
PKIX validation performed: false
~~~

Giải thích:

- **trusted key match=true:** SPKI fingerprint khớp public key đã được chấp nhận trong mô phỏng. Trong SAML thật, **điều kiện chấp nhận khóa phụ thuộc metadata/role/issuer trust**, không chỉ so hash.
- **untrusted key match=false:** một public key RSA khác không thay được khóa đã được IdP Corp cho phép.
- **signature with trusted key=true:** chữ ký số hợp lệ **với khóa đó và bytes đó**. Chưa chứng minh Response đúng audience, thời gian hoặc issuer.
- **signature with other key=false:** chữ ký không kiểm được bằng khóa lạ.
- **signature after alteration=false:** thay dữ liệu có chữ ký làm kiểm chứng thất bại.
- **PKIX validation performed=false:** không có X.509 certificate/chain, CA store, CRL hay OCSP; chương trình cố ý chỉ trình diễn **key trust và signature**.

**SHA-256 trên key.getEncoded() trong chương trình là fingerprint của encoded SPKI**, không phải SHA-256 của toàn bộ X.509 DER certificate. **Signature.getInstance("SHA256withRSA")** kiểm chữ ký của byte string đơn giản; SAML XML Signature còn có XML canonicalization, Reference, transforms, enveloped signature và rủi ro wrapping, nên **không thể thay XMLSig verifier của OpenSAML bằng hàm verify() này**.

## 13. PKIX trong Java: ranh giới của ví dụ đối chiếu

Để hiểu **PKIX thực sự** cần những đầu vào khác với chương trình KeyTrustDemo:

- **Leaf X.509 certificate** của đối tượng đang được kiểm.
- **Intermediate certificates** nếu có, đúng thứ tự hoặc cơ chế path builder.
- **TrustAnchor** (thường root CA certificate được quản trị).
- **PKIXParameters**, chính sách validation date/constraints/revocation.
- Một chính sách **gắn danh tính certificate đã được xác thực với SAML entityID hoặc hostname cụ thể**, nếu cần.

Java cung cấp **CertificateFactory**, **CertPathValidator**, **PKIXParameters**, **TrustAnchor** và **CertPathBuilder**. Ví dụ mảnh mã mô tả hướng API:

~~~java
// MẢNH MÃ MINH HỌA API, KHÔNG CHẠY ĐỘC LẬP:
// rootCa, leaf, intermediate là X509Certificate đã tải từ nguồn đúng.
// Chain phải đúng profile; trust anchor và revocation tùy chính sách.

CertificateFactory factory = CertificateFactory.getInstance("X.509");
CertPath path = factory.generateCertPath(
        java.util.List.of(leaf, intermediate));
PKIXParameters params = new PKIXParameters(
        java.util.Set.of(new TrustAnchor(rootCa, null)));

// Cần cấu hình CRL/OCSP và kiểm key usage/name policy phù hợp
// thay vì tùy tiện tắt revocation để làm bài test pass.
CertPathValidator.getInstance("PKIX").validate(path, params);
~~~

**Đây không phải tệp Java compile độc lập**: phải cung cấp import và chứng chỉ hợp lệ thực trước khi chạy. Không có stdout cố định vì kết quả phụ thuộc certificate chain, thời gian, policy và thông tin revocation. Mảnh mã dùng **PKIX certification path** để so sánh khái niệm, **không đề xuất chèn PKIX vào mỗi lần kiểm role key nếu triển khai OASIS Metadata Interoperability Profile**.

### PKIX pass vẫn chưa phải SAML login pass

Ngay cả khi leaf cert xây được chain tới CA, còn phải kiểm rằng:

- Public key được phép đại diện cho **đúng SAML entityID/registration**;
- Có chữ ký SAML hợp lệ với key ấy;
- SAML issuer, audience, destination, recipient, time, InResponseTo, replay và profile đều hợp lệ;
- Người dùng có quyền truy cập ứng dụng theo authorization nội bộ.

Trong TLS, còn phải kiểm certificate phù hợp hostname theo TLS stack. Không suy từ **Subject CN trong leaf** rằng nó là **SAML issuer** nếu chưa có hợp đồng binding độc lập.

## 14. Key rotation, expiry, compromise và cách xử lý an toàn

### Trường hợp A: IdP thay certificate nhưng giữ public key

- **X.509 cert fingerprint đổi** do serial/issuer/validity đổi.
- **SPKI fingerprint giữ nguyên** nếu public key thực sự không đổi.
- Nếu trust policy tin **public key từ metadata**, key có thể vẫn được nhận diện đúng; phải kiểm metadata có được chấp nhận đúng phiên bản và tuân lịch rotation.
- Không coi “cùng public key” là đủ nếu metadata mới từ nguồn không đáng tin hoặc metadata cũ đã bị thay thế.

### Trường hợp B: IdP tạo cặp khóa mới

- SPKI fingerprint đổi.
- IdP công bố key cũ và mới trong **trusted metadata** trong giai đoạn chồng lấn, hoặc trao đổi certificate tĩnh theo quy trình.
- SP refresh metadata/trust trước khi IdP bắt đầu ký bằng khóa mới.
- Sau khi IdP loại khóa cũ, SP phải ngừng chấp nhận nó theo policy.

### Trường hợp C: certificate self-signed hoặc hết hạn

- **Metadata IOP:** certificate có thể là bao bọc public key; việc self-signed/expired không tự làm runtime signature validation thất bại nếu metadata đã được chấp nhận và key đúng. Nhưng đừng coi đó là tình trạng vận hành khỏe mạnh: cần rotation, monitoring và kiểm yêu cầu của các sản phẩm tích hợp.
- **PKIX:** self-signed không chain đến CA thông thường và expired leaf có thể fail path validation; cần chính sách trust anchor/validation date riêng.
- **TLS:** server certificate hết hạn hoặc hostname mismatch có thể làm HTTPS handshake fail, bất kể SAML signing key khác vẫn đúng.

### Trường hợp D: private key IdP bị lộ

Đây là sự kiện bảo mật nghiêm trọng:

1. IdP ngừng dùng khóa bị lộ.
2. Phát hành metadata đã ký/được tin cậy mới, **loại compromised public key** khỏi role.
3. Thông báo các SP, đẩy refresh gấp, kiểm cache/stale instances.
4. Hạn chế và xem xét các phiên đã tạo trước đó theo incident response policy.
5. Không chỉ đợi CRL/OCSP của certificate bởi Metadata IOP không dựa vào chúng cho runtime key acceptance.

### Trường hợp E: metadata hết validUntil

Metadata đã hết hạn **không được tiếp tục tin vô hạn** chỉ vì các signing cert vẫn còn hạn. Cần chính sách **fail closed hoặc dùng cache còn trong cửa sổ được cấp phép**, giám sát và khôi phục nguồn metadata. **validUntil metadata** khác **notAfter certificate** và khác **Assertion Conditions.NotOnOrAfter**.

## 15. Kiểm thử bảo mật và kết quả mong đợi

Sử dụng **IdP/SP sandbox**, signed SAMLResponse thật từ IdP test và metadata được tạo/đăng ký qua kênh tin cậy. Nếu tự sửa XML SAMLResponse đã ký, chữ ký hỏng có thể khiến test không phân biệt được lỗi trust key và lỗi issuer/audience.

| # | Tình huống | Kết quả cần kiểm tra |
| --- | --- | --- |
| 1 | Metadata IdP Corp đã xác minh; Assertion ký bằng key signing đang công bố | Có thể xác minh chữ ký và tiếp tục kiểm SAML profile. |
| 2 | Assertion ký bằng khóa attacker nhưng tự nhúng cert attacker vào KeyInfo | **Từ chối**; không tự trust key từ message. |
| 3 | Assertion ký bằng key của IdP Partner nhưng Issuer giả IdP Corp | **Từ chối** theo registration/issuer/trust. |
| 4 | IdP signing certificate tự ký, key nằm trong trusted metadata theo Metadata IOP | Có thể dùng key; không yêu cầu CA path cho role key theo profile. |
| 5 | IdP role certificate hết notAfter nhưng key còn trong accepted metadata theo Metadata IOP | **Không dùng PKIX expiry để tự reject role key theo profile**; vẫn vận hành rotation đúng. |
| 6 | Certificate PKIX hợp lệ của site lạ, không trong IdP Corp metadata | **Không tin** như SAML signing key của Corp. |
| 7 | Certificate có cùng Subject CN nhưng public key khác | **Không đồng nhất khóa** bằng CN. |
| 8 | Cert cấp lại khác DER nhưng cùng SPKI public key | Phân biệt **cert fingerprint** và **public-key identity**; policy quyết định. |
| 9 | Metadata bị sửa KeyDescriptor sau khi ký | Metadata signature phải **fail**, không nhập key lạ. |
| 10 | Metadata ký bằng khóa tự nằm trong chính tài liệu, chưa có trust anchor độc lập | **Không tự cấp trust** cho metadata. |
| 11 | Metadata aggregation có nhiều entity | Chỉ lấy **đúng entityID, IDPSSODescriptor, signing role keys**. |
| 12 | KeyDescriptor use=encryption bị chọn làm signing verifier | **Không chọn sai mục đích khóa**. |
| 13 | IdP metadata công bố signing keys K1 và K2 giai đoạn rotation | Cả hai có thể được dùng đúng policy khi metadata đã chấp nhận. |
| 14 | K1 đã loại khỏi metadata mới nhưng SP vẫn dùng cache cũ quá hạn | **Lỗi stale trust**, cần refresh/expiry/incident handling. |
| 15 | IdP đổi key nhưng SP chưa refresh | **Từ chối chữ ký mới** cho tới khi trust cập nhật hợp lệ; không bỏ verification. |
| 16 | HTTPS metadata URL có TLS cert hết hạn | Fetch có thể **fail TLS**, dù role signing cert riêng còn hợp lệ. |
| 17 | Metadata signer certificate có chain PKIX đúng nhưng XML Signature sai | **Không chấp nhận metadata**. |
| 18 | Metadata signature hợp lệ nhưng EntityDescriptor.entityID sai | **Không gán nhầm đối tác**; từ chối hoặc báo cấu hình không phù hợp. |
| 19 | PKIX leaf chain pass nhưng Assertion Audience sai | **Từ chối SAMLResponse**; PKIX không thay audience validation. |
| 20 | Assertion ký đúng IdP key nhưng Recipient/Destination trỏ SP khác | **Từ chối** SAML profile. |
| 21 | Ký đúng IdP key nhưng Response quá hạn | **Từ chối** expiry/conditions. |
| 22 | Certificate bị compromise và removed khỏi metadata được chấp nhận | SP phải ngừng tin key cũ theo refresh policy. |
| 23 | Metadata có validUntil quá hạn | **Không tiếp tục dùng vô thời hạn**; thực thi expiry policy. |
| 24 | App cấu hình certificate trong Saml2X509Credential.verification | Điều đó khai báo SAML verification key, **không chứng minh đã chạy PKIX path**. |

**Negative test thành công** là hệ thống **từ chối đúng trust hoặc profile violation**. Không “sửa” bằng cách bật allow-all certs, bỏ signature verification, tin KeyInfo từ response hoặc chấp nhận mọi issuer.

## 16. Chẩn đoán lỗi: bắt đầu ở tầng nào?

| Hiện tượng | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| **Signature validation failed** | IdP ký bằng key không nằm trong accepted metadata/verification credentials, hoặc XML bị sửa. | So IdP registration, actual signing key, rotation và signature policy. |
| **Unknown issuer / mismatched issuer** | Assertion/Response Issuer không khớp IdP entityID được đăng ký. | Sửa đối tác/metadata, không chỉ tin key vì PKIX pass. |
| **Cert path does not validate / unable to find trust anchor** | Có thành phần PKIX/TLS hoặc validator đặc biệt kiểm chain, không phù hợp trust store/policy. | Xác định chính xác tầng TLS/metadata signer/role key trước khi xử lý. |
| **SAML cert expired** | Product/policy có thể áp đặt expiry check khác với Metadata IOP. | Xem profile đang triển khai, version và contract; lên lịch đổi key, không tắt TLS expiry. |
| **Metadata download TLS handshake fail** | HTTPS certificate hostname/chain/validity hoặc proxy. | Kiểm TLS truststore/hostname/CA riêng, không đổi SAML signing key một cách mù quáng. |
| **Metadata signature invalid** | Nội dung bị sửa, signer chưa được tin hoặc transform sai. | Xác minh metadata trust anchor và signed reference trước khi nạp khóa SAML. |
| **IdP rotation, login đột ngột lỗi** | SP chưa tải metadata mới hoặc vẫn dùng cert cũ. | Kiểm KeyDescriptor cũ/mới, cache/validUntil, refresh và overlap. |
| **Dùng certificate của website IdP để verify Response và thất bại** | TLS cert khác SAML signing cert. | Lấy signing cert từ IdP metadata đã được phê duyệt. |
| **Nhiều cert trong metadata bị nhầm là CA chain** | Mỗi KeyDescriptor là một key, không phải chuỗi chứng thư. | Dùng đúng keys của đúng role, không build chain từ các KeyDescriptor. |
| **Vẫn login bằng khóa đã bị thu hồi khỏi metadata** | Cache stale, refresh hoặc policy key removal lỗi. | Tăng tốc refresh, điều tra session và incident procedure. |
| **Chữ ký hợp lệ nhưng SAML login fail** | Audience, Destination, Recipient, InResponseTo, time hoặc logout/profile khác sai. | Debug SAML assertion conditions, không quy mọi lỗi cho certificate. |

**Không log private keys, full SAMLResponse, raw Assertions, session cookies hoặc thông tin cá nhân trong ticket công khai.** Có thể log có kiểm soát: registrationId, IdP entityID đã xác minh, hash/fingerprint dạng SHA-256 của **certificate công khai**, ID request được ẩn danh và loại lỗi. Khi lưu fingerprint cần ghi rõ **certificate SHA-256** hay **SPKI SHA-256**, tránh khiến người kiểm tra so hai thứ khác nhau.

## 17. Checklist chọn mô hình tin cậy

**Trước khi triển khai:**

1. Xác định tổ chức dùng **OASIS Metadata Interoperability Profile**, PKIX-based trust khác, hay một dạng kết hợp có phân tầng; ghi rõ trong thiết kế.
2. Xác định **metadata source/aggregator** được phê duyệt, trust anchor của metadata signer hoặc cơ chế xác thực nguồn; không chấp nhận URL tùy ý từ browser.
3. Chọn đúng **IdP entityID/IDPSSODescriptor/KeyDescriptor use=signing**.
4. Đăng ký **SP entityID/ACS** đúng, tách SP signing certificate và IdP verification certificate.
5. Đảm bảo Spring Security **RelyingPartyRegistration** chứa verification credentials của đúng IdP; không thử keys của mọi tenant để tìm “cái khớp”.
6. Đảm bảo metadata signature validation nếu policy yêu cầu, **không nhầm** với SAML message signature validation.
7. Xác định **validUntil/cacheDuration**, refresh cadence, rollback/replay protection và emergency key removal.
8. Lập kế hoạch **rotation**: thêm key mới, xác minh readiness, cutover, loại key cũ; kiểm certificate lifecycle và thuật toán.
9. Nếu dùng PKIX ở tầng nào, xác định CA anchors, name binding, certificate constraints và revocation policy của **chính tầng đó**; đừng gộp với metadata-based role key trust một cách tùy tiện.
10. Giữ **HTTPS/TLS hostname verification** cho metadata fetch và giao tiếp mạng, dù signing key SAML được tin qua metadata.
11. Kiểm thử tối thiểu các case: valid key, unknown key, self-signed key, expired cert, metadata signature fail, rotation hai khóa, stale metadata, wrong issuer, wrong audience, wrong ACS.
12. Theo dõi phiên bản Spring Security/OpenSAML thực tế; không khẳng định Spring Security mặc định có PKIX/OCSP cho SAML signing keys nếu chưa xác minh code/config của phiên bản đó.

## 18. Câu hỏi ôn tập và đáp án

**Câu 1.** Một IdP ký Assertion bằng certificate tự ký. SP đã tải metadata IdP qua nguồn đáng tin và KeyDescriptor signing công bố đúng public key. Theo OASIS Metadata IOP, SP có phải chứng minh cert chain tới public CA mới chấp nhận chữ ký?  
**Đáp án:** **Không**. Theo profile, sau khi chấp nhận metadata, runtime trust dựa vào key được ủy quyền bởi role metadata, không PKIX path validation. Nhưng signature và mọi điều kiện SAML vẫn phải được xác minh, metadata phải còn được chấp nhận theo policy.

**Câu 2.** Một chứng chỉ ký SAML của attacker có chain hợp lệ tới public CA. Nó đủ chứng minh attacker là IdP Corp chưa?  
**Đáp án:** **Chưa**. PKIX chain không tự ràng buộc certificate với SAML entityID Corp. SP chỉ tin đúng IdP issuer/role/verification credentials đã phê duyệt.

**Câu 3.** IdP đổi certificate DER nhưng giữ public key. Cert fingerprint SHA-256 giống nhau không? SPKI fingerprint có thể giống nhau không?  
**Đáp án:** Certificate fingerprint thường **khác** vì byte DER khác; SPKI fingerprint có thể **giống** nếu public key không đổi. Cần nêu rõ đối tượng được pin/so.

**Câu 4.** Tại sao không dùng certificate nhúng trong ds:KeyInfo của Response làm trust anchor?  
**Đáp án:** Vì message chưa được xác minh có thể do attacker tự ký và tự nhúng cert của mình. Key phải được liên kết với IdP đã được tin qua metadata/configuration trước, rồi mới verify.

**Câu 5.** Metadata đã ký hợp lệ và chứa key K1, nhưng hết validUntil từ lâu. Có được tiếp tục tin K1 mãi không?  
**Đáp án:** **Không**. Metadata lifecycle/refresh/expiry policy vẫn bắt buộc; vấn đề metadata expired khác certificate key expiry ở Metadata IOP.

**Câu 6.** TLS server certificate của idp.example.org hết hạn, trong khi SAML signing certificate còn được tin. SP có thể tải metadata qua HTTPS không?  
**Đáp án:** HTTPS handshake có thể thất bại do TLS validation. Không được bỏ TLS verification chỉ vì trust của SAML key là cơ chế khác.

**Câu 7.** Có hai KeyDescriptor use=signing trong IdP metadata. Đó là chuỗi leaf → CA intermediate?  
**Đáp án:** **Không**. Chúng thường biểu diễn các **signing keys độc lập** của một role, có thể do rotation. CA certificate path là cấu trúc PKIX khác.

**Câu 8.** App dùng Saml2X509Credential.verification(idpCert), vậy Spring Security chắc chắn đã kiểm CRL/OCSP và CA chain cho idpCert?  
**Đáp án:** **Không được suy ra**. Đây là cách khai báo verification credential cho SAML. Muốn biết PKIX/revocation có chạy không phải kiểm đúng provider/version và policy. OASIS Metadata IOP còn yêu cầu không áp PKIX runtime cho role keys đã chấp nhận.

**Câu 9.** Có thể tắt XML Signature validation vì IdP metadata được tải qua HTTPS hợp lệ?  
**Đáp án:** **Không**. Metadata source trust và SAML message signature là hai lớp khác nhau; chữ ký Assertion/Response theo policy vẫn phải được kiểm.

## 19. Nguồn tham khảo

1. [OASIS — SAML V2.0 Metadata Interoperability Profile Version 1.0, OASIS Standard 24 October 2019](https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop-os.html) — đặc biệt **2.3 Metadata Exchange and Acceptance**, **2.5.1 Key Representation**, **2.6.1 Key Processing**, **2.7 Security Considerations**; phân biệt acceptance/role-key trust và PKIX.
2. [OASIS — SAML 2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) — EntityDescriptor, IDPSSODescriptor, SPSSODescriptor, KeyDescriptor, validUntil/cacheDuration.
3. [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) — XML Signature, Issuer, Assertion Conditions và key-bearing constructs.
4. [IETF RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280) — PKIX certification path, constraints, validity và revocation.
5. [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — RelyingPartyRegistration, asserting party verificationX509Credentials, Saml2X509Credential và SAML validation.
6. [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — đọc metadata IdP, xuất metadata SP; ở các version mới có repository refresh/metadata signature verification, cần xem đúng API version.
7. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) — signature verification, issuer/audience/destination validation và customization.
8. [Oracle Java Security — CertPathValidator và PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html) — API path validation của JDK; khác với Saml2X509Credential.
9. [Shibboleth — Keys and Certificates](https://docs.shib.ncsu.edu/docs/configure/keys.html) — ví dụ thực tế public SAML signing cert được công bố trong metadata, private key ở chủ sở hữu.

**Tóm tắt một câu:** **PKIX kiểm chuỗi certificate tới CA theo chính sách; SAML metadata trust ủy quyền public key cho một entity/role qua metadata đã được chấp nhận.** Theo OASIS Metadata Interoperability Profile, việc xác minh SAML message bằng role key được tin **không cần và không được gắn thêm PKIX/CRL/OCSP runtime**, trong khi **metadata exchange, metadata signature, TLS, key rotation và mọi kiểm tra SAML issuer/audience/time vẫn phải an toàn**.
