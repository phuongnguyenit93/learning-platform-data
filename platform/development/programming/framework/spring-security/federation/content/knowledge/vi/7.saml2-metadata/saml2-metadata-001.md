# EntityDescriptor, IDPSSODescriptor và SPSSODescriptor trong SAML 2.0 Metadata

## 1. Vai trò của SAML 2.0 Metadata

Trong một hệ thống **SAML 2.0 federation**, Service Provider (SP) và Identity Provider (IdP) cần biết trước đối tác nào được tin cậy, endpoint nào nhận bản tin, binding nào được hỗ trợ, chứng chỉ công khai nào dùng để xác minh chữ ký và quy tắc nào áp dụng cho đăng nhập/đăng xuất.

**Metadata SAML 2.0** là tài liệu XML tiêu chuẩn công bố những dữ kiện kỹ thuật này để các bên cấu hình quan hệ tin cậy. Metadata thường được trao đổi khi onboarding đối tác, cập nhật cấu hình, xoay khóa, triển khai SSO/SLO hoặc chẩn đoán sự cố. **Metadata không phải SAMLResponse, không phải Assertion, không phải phiên đăng nhập và không chứa mật khẩu người dùng.**

Ba phần tử trọng tâm:

- **EntityDescriptor:** mô tả **một thực thể (entity)**, có định danh **entityID** và một hay nhiều vai trò.
- **IDPSSODescriptor:** mô tả **vai trò IdP** trong SSO: các **SingleSignOnService**, khóa ký, NameID formats và yêu cầu ký AuthnRequest.
- **SPSSODescriptor:** mô tả **vai trò SP**: các **AssertionConsumerService (ACS)**, yêu cầu ký Assertion, thông tin ký AuthnRequest hoặc giải mã SAML Assertion.

Trong **Spring Security Servlet**, ứng dụng tích hợp **spring-security-saml2-service-provider** đóng vai trò **SP/Relying Party**: ứng dụng **đọc metadata IdP** để biết IdP và **xuất metadata SP** để IdP đăng ký ứng dụng. Việc xuất SPSSODescriptor **không tự biến Spring Security thành SAML IdP**.

Bài học dùng quy tắc OASIS SAML 2.0 và mô hình Spring Boot 3.x/Spring Security 6.x, Java 17+. Mục tiêu là hiểu đúng metadata và cách vận hành thực tế, không xây một XML parser tự cấp quyền xác thực.

## 2. Namespace, cấu trúc và cách nhận diện vai trò

Namespace SAML metadata chính thức:

~~~text
urn:oasis:names:tc:SAML:2.0:metadata
~~~

Ví dụ khai báo namespace:

~~~xml
xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
~~~

Prefix **md** là quy ước trong ví dụ; XML dùng prefix khác hoặc default namespace vẫn là cùng phần tử nếu namespace URI không đổi.

Cây cấu trúc dễ nhớ:

~~~text
md:EntitiesDescriptor                       (tùy chọn: nhóm nhiều entity)
  └── md:EntityDescriptor entityID="..."
        ├── ds:Signature                    (nếu metadata được ký)
        ├── md:Extensions                   (tùy chọn)
        ├── md:IDPSSODescriptor             (nếu đóng vai trò IdP)
        │     ├── md:KeyDescriptor*
        │     ├── md:SingleLogoutService*
        │     ├── md:NameIDFormat*
        │     └── md:SingleSignOnService+
        ├── md:SPSSODescriptor              (nếu đóng vai trò SP)
        │     ├── md:KeyDescriptor*
        │     ├── md:SingleLogoutService*
        │     ├── md:NameIDFormat*
        │     ├── md:AssertionConsumerService+
        │     └── md:AttributeConsumingService*
        ├── md:Organization?
        └── md:ContactPerson*
~~~

Trong sơ đồ, **+** là ít nhất một, **\*** là 0 hoặc nhiều, **?** là tùy chọn. Đó là sơ đồ khái niệm; thứ tự XML thực tế phải theo SAML Metadata XSD. Một EntityDescriptor có thể chứa nhiều role descriptors (IdP, SP, AttributeAuthority...) và mỗi role có cấu hình riêng.

**EntitiesDescriptor** khác EntityDescriptor: EntitiesDescriptor là **tập hợp nhiều entity**, thường dùng cho metadata của một federation. Nếu tải một aggregate, phải chọn **đúng entityID và đúng role**; không lấy EntityDescriptor đầu tiên một cách tùy tiện.

### Metadata khác bản tin trong từng lần login

| Khái niệm | Nó mô tả gì? | Lúc nào được sử dụng? |
| --- | --- | --- |
| **EntityDescriptor/role descriptors** | Danh tính kỹ thuật, endpoint, certificate, capability của đối tác. | Onboarding, cấu hình trust, metadata refresh, rollover. |
| **AuthnRequest** | SP yêu cầu IdP xác thực một user. | Một phiên đăng nhập SP-initiated. |
| **SAML Response/Assertion** | IdP phản hồi kết quả xác thực/subject, cần SP xác minh. | Một phiên đăng nhập cụ thể. |
| **LogoutRequest/LogoutResponse** | Bản tin Single Logout khi các bên hỗ trợ. | Luồng logout federation. |

**Chữ ký metadata và chữ ký SAMLResponse là hai việc khác nhau**. Dù metadata đã được tin cậy, mọi SAMLResponse/Assertion vẫn phải được kiểm tra chữ ký, issuer, audience, destination, subject confirmation, InResponseTo và thời gian theo profile.

## 3. EntityDescriptor: danh tính của một SAML entity

Dạng minh họa:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml/metadata"
    validUntil="2030-01-01T00:00:00Z"
    cacheDuration="PT8H">
  <!-- Bên trong phải có role descriptor thật, ví dụ IDPSSODescriptor -->
</md:EntityDescriptor>
~~~

Đoạn này chỉ minh họa thuộc tính, **chưa phải metadata đầy đủ** vì role descriptor đã được lược bỏ.

| Thuộc tính / phần tử | Vai trò | Lưu ý |
| --- | --- | --- |
| **entityID** | Bắt buộc; định danh logic của entity. | Thường là URI/URL nhưng **không nhất thiết là URL tải metadata**. |
| **ID** | Tùy chọn; XML ID có thể phục vụ tham chiếu ds:Signature. | Không phải AuthnRequest.ID hay session ID. |
| **validUntil** | Tùy chọn; thời hạn metadata hợp lệ. | Không phải thời hạn token hoặc session. |
| **cacheDuration** | Tùy chọn; thời gian cache gợi ý, dạng XML duration. | Không phải thời gian user đăng nhập SSO. |
| **ds:Signature** | Tùy chọn; chữ ký bảo vệ nội dung metadata. | Chỉ có chữ ký không có nghĩa đã xác minh tin cậy. |
| **Organization** | Tùy chọn; thông tin đơn vị vận hành. | Không thay thế entityID để nhận diện đối tác. |
| **ContactPerson** | Tùy chọn; liên hệ kỹ thuật/hỗ trợ. | Không dùng email làm trust anchor. |

**entityID là định danh logic**, nên có thể khác vị trí tải metadata và endpoint của SAML flow. Ví dụ hợp lệ khi cấu hình SP:

~~~text
SP entityID:
  https://sp.example.com/saml2/service-provider-metadata/corp

SP metadata URL:
  https://sp.example.com/saml2/metadata/corp

SP ACS URL:
  https://sp.example.com/login/saml2/sso/corp
~~~

Ba giá trị có thể cùng hostname nhưng khác đường dẫn; không tự sửa cho giống nhau. **AuthnRequest.Issuer thường là SP entityID**, **Assertion Audience thường chứa SP entityID**, còn **SAMLResponse đi tới ACS URL**.

### Một entity có thể vừa là IdP vừa là SP?

Có thể. Identity broker/gateway có thể vừa nhận SAML từ IdP bên ngoài (vai trò SP ở upstream) vừa phát SAML cho ứng dụng khác (vai trò IdP ở downstream). Metadata của một entity có thể công bố cả IDPSSODescriptor lẫn SPSSODescriptor, nếu hệ thống thực sự hỗ trợ cả hai. **Không được gộp vai trò:** endpoint và khóa của mỗi role phục vụ chức năng khác nhau.

### Aggregate metadata với EntitiesDescriptor

~~~xml
<md:EntitiesDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Name="ExampleFederation">
  <md:EntityDescriptor entityID="https://idp-a.example.org/metadata">
    <!-- IDPSSODescriptor của IdP A -->
  </md:EntityDescriptor>
  <md:EntityDescriptor entityID="https://idp-b.example.org/metadata">
    <!-- IDPSSODescriptor của IdP B -->
  </md:EntityDescriptor>
</md:EntitiesDescriptor>
~~~

Ví dụ này là **sơ đồ cấu trúc có lược bỏ role descriptors**, không phải tài liệu đem import thật. Một tập metadata nhiều IdP cần cách chọn **entityID và role** rõ ràng, nguồn trust rõ ràng và xử lý cache/expiry của cả aggregate lẫn entity.

## 4. IDPSSODescriptor: metadata của Identity Provider

IDPSSODescriptor là role descriptor mô tả **IdP cung cấp dịch vụ đăng nhập SAML 2.0**. SP đọc role này để biết **IdP entityID, các SSO endpoint, binding và khóa xác minh chữ ký**, đồng thời hiểu IdP có yêu cầu SP ký AuthnRequest hay không.

| Trường trong IDPSSODescriptor | Ý nghĩa |
| --- | --- |
| **protocolSupportEnumeration** | Bắt buộc cho role descriptor; chứa URI giao thức. SAML2 dùng **urn:oasis:names:tc:SAML:2.0:protocol**. |
| **WantAuthnRequestsSigned** | Tùy chọn; true khi IdP yêu cầu AuthnRequest từ SP phải ký. Theo đặc tả, nếu không có thì mặc định false ở metadata; policy vận hành IdP vẫn cần xác nhận. |
| **KeyDescriptor use="signing"** | Public certificate/key của IdP để SP xác minh chữ ký Response, Assertion, Logout message theo chính sách. |
| **SingleSignOnService** | **Bắt buộc ít nhất một**. Endpoint **thuộc IdP** nhận AuthnRequest, với Binding và Location. |
| **SingleLogoutService** | Tùy chọn. Endpoint IdP hỗ trợ SAML Single Logout nếu tích hợp SLO. |
| **NameIDFormat** | Tùy chọn. Định dạng NameID như persistent, transient, emailAddress. |
| **ArtifactResolutionService** | Tùy chọn cho profile dùng SAML Artifact/giải quyết artifact, không cần trong HTTP Redirect/POST phổ biến. |

### XML mẫu IDPSSODescriptor

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/saml/metadata"
    validUntil="2030-01-01T00:00:00Z">

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="true">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>
            REPLACE_WITH_REAL_BASE64_X509_PUBLIC_CERTIFICATE
          </ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/logout"/>

    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </md:NameIDFormat>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso"/>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Chỉ là mẫu giải thích XML.** Chuỗi REPLACE_WITH_REAL_BASE64_X509_PUBLIC_CERTIFICATE **không phải certificate hợp lệ** và domain example.org là ví dụ; không dùng metadata này để xác thực thật.

Đọc ví dụ:

1. **EntityDescriptor.entityID** xác định **IdP issuer**. Đó là định danh IdP, không nhất thiết phải là trang HTML đăng nhập.
2. **WantAuthnRequestsSigned=true** cho biết **SP phải ký AuthnRequest** theo policy. SP cần signing private key, và IdP cần public certificate SP để xác minh.
3. **KeyDescriptor use=signing** công bố public key/certificate **IdP**; SP dùng để xác minh thông điệp do IdP ký. Không được nhầm với chứng chỉ HTTPS của website IdP nếu không có hợp đồng trust.
4. **SingleSignOnService HTTP-Redirect** là một lựa chọn điểm vào đăng nhập IdP. Một IdP có thể công bố nhiều binding; SP chọn binding tương thích.
5. **SingleLogoutService** là điểm vào SLO của IdP; chỉ khai báo endpoint không tự bật tính năng logout liên ứng dụng.
6. **NameIDFormat=persistent** biểu thị IdP công bố định dạng NameID; không cho phép suy ra NameID là email hoặc userId bất biến trong mọi hệ thống.

**Đặc biệt:** IdP metadata có thể chứa **nhiều KeyDescriptor** trong thời gian rotation. Không tự chọn certificate theo thứ tự trong XML; dùng trust policy và metadata update đã được xác minh.

## 5. SPSSODescriptor: metadata của Service Provider

SPSSODescriptor mô tả những gì **ứng dụng SP** công bố cho IdP. Quan trọng nhất là **SP entityID** và **AssertionConsumerService URL**, nơi IdP POST SAMLResponse. Spring Security Servlet xuất metadata dạng này khi bật **saml2Metadata()**.

| Trường trong SPSSODescriptor | Ý nghĩa |
| --- | --- |
| **protocolSupportEnumeration** | Giao thức SAML 2.0 mà SP hỗ trợ; không phải URI binding. |
| **AuthnRequestsSigned** | Tùy chọn; true khi SP công bố AuthnRequest có chữ ký. Phải có signing credentials và thiết lập thực sự phù hợp. |
| **WantAssertionsSigned** | Tùy chọn; thể hiện SP mong muốn Assertion được ký. Không thay thế việc SP thực hiện signature validation. |
| **KeyDescriptor use="signing"** | Public certificate của SP để **IdP kiểm tra** chữ ký AuthnRequest/Logout message SP tạo. |
| **KeyDescriptor use="encryption"** | Public certificate của SP để **IdP mã hóa** Assertion gửi cho SP; SP giữ private key giải mã. |
| **AssertionConsumerService** | **Bắt buộc ít nhất một**, với **Binding, Location, index**; có thể chỉ định **isDefault**. |
| **SingleLogoutService** | Tùy chọn; endpoint SP hỗ trợ giao thức SLO. |
| **NameIDFormat** | Tùy chọn; mô tả định dạng NameID SP hỗ trợ/mong đợi. |
| **AttributeConsumingService** | Tùy chọn; mô tả dịch vụ và các thuộc tính SP cần (RequestedAttribute), như email, group. |

### XML mẫu SPSSODescriptor

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://sp.example.com/saml2/service-provider-metadata/corp"
    validUntil="2030-01-01T00:00:00Z">

  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      AuthnRequestsSigned="false"
      WantAssertionsSigned="true">

    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </md:NameIDFormat>

    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://sp.example.com/login/saml2/sso/corp"
        index="0"
        isDefault="true"/>

    <md:AttributeConsumingService index="0" isDefault="true">
      <md:ServiceName xml:lang="vi">Ung dung noi bo</md:ServiceName>
      <md:RequestedAttribute Name="email" isRequired="false"/>
    </md:AttributeConsumingService>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

Mẫu này **không có certificate** vì SP chưa dùng signing hoặc encryption keys, cũng không có chữ ký metadata. Nó là hình minh họa cấu trúc; XML thực do Spring Security sinh có thể khác mà vẫn đúng chuẩn.

Giải thích:

- **entityID** thuộc EntityDescriptor, là **SP issuer** cho AuthnRequest và thường là **Audience** mà IdP đưa vào Assertion.
- **AssertionConsumerService.Location** là **địa chỉ HTTP của SP** nhận SAMLResponse, khác entityID dù cùng host. Ví dụ ASP của Spring Security thường có path **/login/saml2/sso/{registrationId}**.
- **index** là số nguyên để phân biệt các ACS được công bố. Nó **không phải registrationId**, không phải NameID hay ID request. **isDefault** tùy chọn giúp xác định ACS mặc định theo quy tắc metadata.
- **AuthnRequestsSigned=false** trong ví dụ thể hiện SP chưa ký AuthnRequest; nếu IdP đặt WantAuthnRequestsSigned=true, cần cấu hình signing credentials và đổi policy đồng bộ.
- **WantAssertionsSigned=true** yêu cầu IdP ký Assertion theo hợp đồng; không đồng nghĩa Assertion được mã hóa.
- **AttributeConsumingService** mô tả mong muốn thuộc tính, **không tự thực thi phân quyền ứng dụng**.

Nếu SP công bố KeyDescriptor use=encryption thì IdP có thể mã hóa Assertion cho SP bằng public certificate; **chỉ SP giữ private key giải mã**. Nếu SP công bố use=signing, IdP dùng public cert để xác minh AuthnRequest được SP ký; **chỉ SP giữ private key ký**. use là thuộc tính tùy chọn và chính sách phải xác định mục đích khóa; không đồng nhất certificate IdP và certificate SP.

### Metadata role nào chứa endpoint nào?

| Endpoint | Nơi công bố | Ai sở hữu | Mục đích |
| --- | --- | --- | --- |
| **SingleSignOnService** | **IDPSSODescriptor** | IdP | Nhận SAML AuthnRequest từ SP. |
| **AssertionConsumerService** | **SPSSODescriptor** | SP | Nhận SAMLResponse từ IdP. |
| **SingleLogoutService** | Cả hai role có thể công bố | Từng phía | Nhận bản tin SLO phù hợp binding. |
| **ArtifactResolutionService** | Role có hỗ trợ Artifact | Phía có dịch vụ resolution | Trao đổi artifact để lấy bản tin SAML. |

Không nhầm metadata endpoint của IdP với SSO endpoint và cũng không nhầm metadata endpoint của SP với ACS. Metadata là nơi **công bố cấu hình**; SSO/ACS là nơi **nhận bản tin login**.

## 6. Bảng đối chiếu ba descriptor

| Câu hỏi | EntityDescriptor | IDPSSODescriptor | SPSSODescriptor |
| --- | --- | --- | --- |
| **Vai trò?** | Khung mô tả entity. | IdP SSO. | SP SSO. |
| **Định danh?** | entityID bắt buộc. | Dùng entityID của cha. | Dùng entityID của cha. |
| **Endpoint bắt buộc?** | Không chỉ ra một endpoint SSO cụ thể. | Ít nhất một SingleSignOnService. | Ít nhất một AssertionConsumerService. |
| **Chứng chỉ nào?** | Có thể được ký metadata bằng ds:Signature. | Public cert/KeyDescriptor của IdP. | Public cert/KeyDescriptor của SP. |
| **Chính sách ký?** | Metadata signature nếu có. | WantAuthnRequestsSigned. | AuthnRequestsSigned, WantAssertionsSigned. |
| **Thông tin logout?** | Có thể có role con. | SingleLogoutService tùy chọn. | SingleLogoutService tùy chọn. |
| **Giá trị Spring dùng?** | EntityID/định danh đối tác. | SSO endpoint, verification credentials IdP. | SP ACS/entityId/credentials để xuất metadata. |

Phép kiểm tra nhanh: nếu XML chỉ có **IDPSSODescriptor** và SingleSignOnService, nó là metadata **IdP**. Nếu chỉ có **SPSSODescriptor** và AssertionConsumerService, nó là metadata **SP**. Nếu có cả hai, đối tác công bố **cả hai vai trò**. Nếu XML bắt đầu bằng **EntitiesDescriptor**, cần tìm EntityDescriptor con tương ứng.

## 7. Protocol URI, binding URI và HTTP URL không phải một

| Chuỗi | Ý nghĩa |
| --- | --- |
| **urn:oasis:names:tc:SAML:2.0:protocol** | URI của giao thức SAML2 trong **protocolSupportEnumeration**. |
| **urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect** | Cách truyền thông điệp qua Redirect binding. |
| **urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST** | Cách truyền thông điệp bằng form POST binding. |
| **urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Artifact** | Binding dùng artifact khi các bên triển khai resolution. |
| **https://idp.example.org/saml/sso** | HTTP **Location** của IdP SingleSignOnService. |
| **https://sp.example.com/login/saml2/sso/corp** | HTTP **Location** của SP AssertionConsumerService. |

**protocolSupportEnumeration** trả lời “hỗ trợ giao thức nào”; **Binding** trả lời “truyền bản tin bằng cách nào”; **Location** trả lời “địa chỉ nhận ở đâu”. Không đặt URI HTTP-POST binding vào protocolSupportEnumeration hay lấy URI giao thức làm Location.

### Liên hệ với Response.Destination, SubjectConfirmationData.Recipient và Audience

Khi IdP gửi Assertion cho SP:

- **Response.Destination** thường là **ACS của SP**.
- **SubjectConfirmationData.Recipient** của bearer confirmation thường là **ACS nhận Assertion**.
- **Conditions.AudienceRestriction / Audience** thường là **SP entityID**.
- **Response/Assertion.Issuer** là IdP entityID theo thỏa thuận.
- **AuthnRequest.Issuer** là SP entityID.

Vì vậy, đừng tùy ý ép **SP entityID phải giống ACS URL**. Metadata khai báo đúng hai giá trị khác nhau là bình thường.

## 8. Thiết lập tin cậy bằng metadata

Một quy trình SAML SP–IdP đầy đủ thường gồm:

1. **IdP admin xuất metadata IdP**: EntityDescriptor + IDPSSODescriptor, entityID, SingleSignOnService, KeyDescriptor signing, binding và chính sách.
2. **SP admin xác minh nguồn metadata**, tải/đăng ký theo quy trình tin cậy; chọn đúng entityID/role nếu metadata chứa nhiều entities.
3. **Spring Security tạo RelyingPartyRegistration**: IdP verification credentials, IdP SSO URL, SP entityID và ACS; bổ sung signing/decryption credentials nếu cần.
4. **SP xuất metadata SP**: EntityDescriptor + SPSSODescriptor, entityID, ACS Binding/Location, public cert của SP khi có.
5. **IdP admin đăng ký SP** với đúng entityID, ACS và public cert SP; đồng bộ AuthnRequestsSigned/WantAuthnRequestsSigned và các chính sách.
6. **Kiểm thử SP-initiated SSO**: Spring gửi AuthnRequest đến IdP SingleSignOnService; IdP gửi SAMLResponse đến SP AssertionConsumerService; Spring kiểm tra chữ ký, issuer, audience, destination, subject confirmation, thời gian và request correlation.
7. **Kiểm thử vận hành**: logout, rotation cert, cache metadata, URL public, nhiều IdP, sự cố fetch metadata và quyền ứng dụng.

~~~text
   CẤU HÌNH TRUST
   IdP -- IDPSSODescriptor ------------> Spring SP
   SP  -- SPSSODescriptor -------------> IdP

   LUỒNG SSO
   Browser -> Spring SP -> IdP SingleSignOnService
   Browser <- IdP SAMLResponse
   Browser -> Spring SP AssertionConsumerService
   Spring SP -> validate Response/Assertion -> local Authentication
~~~

### Những khóa nào được dùng?

| Khóa | Private key được giữ ở đâu? | Public certificate dùng ở đâu? |
| --- | --- | --- |
| **IdP signing** | IdP. | SP xác minh Response/Assertion/Logout do IdP ký. |
| **SP signing** | SP. | IdP xác minh AuthnRequest/Logout do SP ký. |
| **SP decryption** | SP. | IdP mã hóa Assertion gửi cho SP; SP giải mã. |
| **Metadata signing** | Bên phát hành metadata hoặc federation operator. | Bên tiêu thụ xác minh metadata bằng trust anchor đã cấu hình trước. |

KeyDescriptor công bố **public certificate**, không công bố private key. **Metadata ký số** và **SAMLResponse ký số** có thể dùng các khóa khác nhau; không đánh đồng certificate trong XML với CA của HTTPS. Chứng chỉ trong metadata chưa được tin cậy **không tự xác minh được chính metadata ấy**, vì người tấn công có thể thay cả dữ liệu và chứng chỉ.

### Metadata validity và caching

**validUntil** là mốc hết hạn metadata; **cacheDuration** là gợi ý khoảng cache. Chúng **không** quyết định thời gian sống của Session tại SP/IdP hay Assertion.NotOnOrAfter. Tùy metadata provider và chính sách, cache/refresh có thể áp dụng hạn nhỏ hơn và xử lý aggregate.

Nếu IdP xoay khóa ký, metadata có thể công bố **nhiều chứng chỉ signing** trong giai đoạn chuyển tiếp. SP phải có quy trình cập nhật trust hợp lệ, cảnh báo cert expiry và kiểm thử, không “lấy certificate đầu tiên” hoặc tắt signature validation khi gặp lỗi. Khi metadata URL bị lỗi, chính sách hệ thống quyết định dùng cache còn hợp lệ hay fail closed; không nên tự dùng metadata đã hết hạn vô thời hạn.

### Rủi ro khi tải metadata

- Không cho người dùng cuối tùy ý cung cấp metadata URL/host để backend fetch; cần phòng **SSRF**, nguồn giả mạo và cấu hình trust sai.
- Không chấp nhận role hoặc entityID bất kỳ chỉ vì metadata XML có chữ ký của **khóa do chính file đó tự khai báo**.
- XML nên được parse bằng thư viện SAML được duy trì, tắt DTD/external entity theo chính sách, phòng XML signature wrapping và sử dụng schema/profile validation.
- Nếu metadata được ký, phải xác minh bằng **trusted signer** hoặc nguồn tin cậy độc lập và kiểm tra phạm vi signature.
- Không sao chép certificate thử nghiệm, placeholder hoặc private key vào Google Sheets/ticket hệ thống thật.

## 9. Spring Security Servlet: đọc IdP metadata và xuất SP metadata

### 9.1. RelyingPartyRegistration không phải XML EntityDescriptor

Trong Spring Security, **RelyingPartyRegistration** biểu diễn **một quan hệ giữa SP và asserting party (IdP)**, gồm:

- **SP side:** SP entityId, ACS location, credentials ký AuthnRequest và credentials giải mã, cấu hình logout.
- **IdP side:** IdP entityId/issuer, SSO location, binding, IdP verification certificates, logout location.
- **registrationId:** tên kỹ thuật trong Spring, ví dụ **corp**, dùng để lựa chọn cấu hình đối tác; **không đồng nghĩa** XML entityID.

Một ứng dụng có thể có nhiều RelyingPartyRegistration. Khi tải metadata IdP dạng federation aggregate, phải chọn đúng IdP entityID; RelyingPartyRegistration không phải người dùng và không phải IDPSSODescriptor mà Spring tự phát hành.

### 9.2. Ví dụ Spring Boot 3.3.5 + Java 17

Đây là **ứng dụng SP thực sự**, có thể chạy khi đã đăng ký với **IdP thật**, cung cấp metadata URI và khớp trust/ACS/entityID. Nó **không tạo IdP**.

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
    <artifactId>saml-metadata-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
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
              metadata-uri: ${SAML_IDP_METADATA_URI}

server:
  port: 8080
~~~

**SAML_IDP_METADATA_URI** phải là URL metadata IdP được tổ chức phê duyệt. Metadata URL mẫu **https://idp.example.org/saml/metadata** chỉ là ví dụ, không được kỳ vọng truy cập được. Nếu IdP yêu cầu signed AuthnRequests, SP phải cấu hình signing private key/public certificate tương ứng; YAML tối giản chưa có.

**src/main/java/com/example/metadata/SamlMetadataApplication.java**

~~~java
package com.example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlMetadataApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlMetadataApplication.class, args);
    }
}
~~~

**src/main/java/com/example/metadata/SecurityConfig.java**

~~~java
package com.example.metadata;

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
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**src/main/java/com/example/metadata/DemoController.java**

~~~java
package com.example.metadata;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/")
    public String home() {
        return "SAML metadata SP demo";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
        return "NameID=" + user.getName();
    }
}
~~~

Đặt biến **SAML_IDP_METADATA_URI** bằng IdP metadata URL hợp lệ, cấu hình tin cậy và đăng ký SP ở IdP, sau đó chạy trong thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Các kết quả được xác định:

- **GET http://localhost:8080/** trả đúng văn bản **SAML metadata SP demo**.
- **GET http://localhost:8080/saml2/metadata/corp** xuất **SP metadata XML** từ registration **corp**, thường chứa EntityDescriptor + SPSSODescriptor + AssertionConsumerService. Spring cũng hỗ trợ các đường metadata như **/saml2/metadata** và **/saml2/service-provider-metadata/corp** theo cấu hình.
- **GET http://localhost:8080/saml2/authenticate/corp** khởi động SP-initiated SSO tới IdP SingleSignOnService.
- **GET http://localhost:8080/me** khi chưa có session yêu cầu SAML login; sau khi IdP phát Response hợp lệ tới ACS, body có dạng **NameID=<giá trị IdP cấp>**; không thể khẳng định subject cố định.

**Không thể chạy trọn SSO với metadata giả**, vì bạn cần IdP thật, signing trust, ACS và SP entityID khớp. Bài học chỉ yêu cầu ứng dụng **SP**; Spring Security saml2Login/saml2Metadata không cung cấp user store, MFA, đăng nhập tập trung hay IDPSSODescriptor như một SAML IdP.

### 9.3. SP entityID và ACS mặc định

Với Spring Security 6, mẫu phổ biến:

~~~text
SP entityID:
  {baseUrl}/saml2/service-provider-metadata/{registrationId}

SP ACS:
  {baseUrl}/login/saml2/sso/{registrationId}
~~~

Ví dụ registrationId = corp. Nếu chạy sau proxy, **baseUrl phải là URL HTTPS công khai** được IdP nhìn thấy. Lỗi phổ biến: SP tự xuất metadata với **http://internal:8080** thay vì **https://sp.example.com**, khiến IdP từ chối ACS/Recipient/Destination. Giải pháp là chỉnh forwarded headers/host/proxy và cấu hình entityID/ACS đúng; không tắt validation.

### 9.4. Spring Security version caveat

Các API **RelyingPartyRegistrations**, **RelyingPartyRegistration**, **saml2Metadata()** và cách mapping metadata phụ thuộc phiên bản. Spring Security 7.x bổ sung các API mới cho AssertingPartyMetadataRepository, signature verification/refresh của IdP metadata; không tự sao chép import và constructor từ 7.x vào dự án Boot 3.x/Security 6.x nếu chưa đối chiếu dependency. Việc **đọc được metadata** không tự động chứng minh metadata đã được ký và được xác minh tin cậy theo chính sách.

## 10. Java 17 độc lập: đọc role trong XML mà không tự xác thực SAML

Ví dụ Java thuần bên dưới chỉ nhận diện **EntityDescriptor, IDPSSODescriptor, SPSSODescriptor và SSO/ACS endpoint** trong **một XML mẫu**. Đây **không phải SAML trust validator**: không chứng minh chữ ký, schema, chứng chỉ, metadata source, entityID authenticity hoặc profile security. Không dùng nó thay Spring Security/OpenSAML.

**MetadataReaderDemo.java**

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.xml.sax.InputSource;

public class MetadataReaderDemo {
    private static final String NS =
            "urn:oasis:names:tc:SAML:2.0:metadata";

    public static void main(String[] args) throws Exception {
        String xml = """
                <md:EntityDescriptor
                  xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                  entityID="https://idp.example.org/metadata">
                  <md:IDPSSODescriptor
                    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
                    <md:SingleSignOnService
                      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                      Location="https://idp.example.org/sso"/>
                  </md:IDPSSODescriptor>
                </md:EntityDescriptor>
                """;

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        Document document = factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
        Element root = document.getDocumentElement();

        System.out.println("entityID=" + root.getAttribute("entityID"));
        System.out.println("IdP=" + root
                .getElementsByTagNameNS(NS, "IDPSSODescriptor").getLength());
        System.out.println("SP=" + root
                .getElementsByTagNameNS(NS, "SPSSODescriptor").getLength());
        System.out.println("SSO=" + root
                .getElementsByTagNameNS(NS, "SingleSignOnService").getLength());
        System.out.println("ACS=" + root
                .getElementsByTagNameNS(NS, "AssertionConsumerService").getLength());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac MetadataReaderDemo.java
java MetadataReaderDemo
~~~

**stdout chính xác:**

~~~text
entityID=https://idp.example.org/metadata
IdP=1
SP=0
SSO=1
ACS=0
~~~

XML ví dụ có **một role IdP, không có role SP**, nên số đếm là 1/0/1/0. Hàm getElementsByTagNameNS tìm tất cả phần tử mang namespace và local name trong subtree; nếu XML là **EntitiesDescriptor aggregate**, phải xác định entity cụ thể trước khi đếm. Việc cấm DOCTYPE/external DTD trong ví dụ giúp minh họa parser thận trọng nhưng **không thay việc xác minh metadata trust**.

## 11. Các bài kiểm tra thực tế với metadata

| Trường hợp | Kết quả/điều cần kiểm tra |
| --- | --- |
| IdP metadata có đúng EntityDescriptor nhưng **không có IDPSSODescriptor** | Không thể tự xem đó là IdP SSO metadata phù hợp với Spring SP. |
| IdP metadata không có SingleSignOnService | Sai khả năng/role bắt buộc cho Web Browser SSO; cần IdP sửa. |
| SP metadata không có AssertionConsumerService | Không mô tả đủ SP SSO role; cần kiểm tra cấu hình xuất metadata. |
| EntityID của SP khác IdP registration | IdP có thể từ chối AuthnRequest hoặc Response audience sai. |
| ACS của SP khác URL đã allowlist ở IdP | IdP có thể từ chối Reply URL, hoặc SP từ chối Recipient/Destination. |
| SP metadata khai AuthnRequestsSigned=false nhưng IdP yêu cầu signed request | Phải bật signing ở SP và trao đổi public certificate. |
| SP metadata khai WantAssertionsSigned=true nhưng Response/Assertion không được ký theo policy | SP không được hạ trust validation để nhận đăng nhập. |
| Chứng chỉ signing IdP đổi | Refresh metadata/key rollover theo trust, kiểm tra kỳ hạn và overlap. |
| Metadata signed nhưng chưa xác minh signer | Chưa đủ để tin metadata; cần trust anchor riêng. |
| Federation aggregate có nhiều EntityDescriptor | Chọn đúng entityID và IDPSSODescriptor/SPSSODescriptor. |
| User đăng nhập được nhưng không có quyền /admin | SAML metadata không cấp business role; kiểm tra authorities/authorization của SP. |
| Logout A không kéo theo logout B | Cần phân biệt local session, IdP session và SLO; SingleLogoutService chỉ là cấu hình capability. |

### Quy trình kiểm tra nhanh khi tích hợp SP

1. Đọc metadata IdP từ nguồn do IdP admin xác nhận, xem **EntityDescriptor.entityID** và **IDPSSODescriptor**.
2. Đối chiếu **SingleSignOnService Location/Binding**, signing certificates và **WantAuthnRequestsSigned**.
3. Lấy SP metadata từ **/saml2/metadata/corp**, kiểm tra **SPSSODescriptor**, SP entityID và **AssertionConsumerService Location/Binding/index**.
4. Gửi IdP admin SP entityID, ACS HTTPS, cert SP nếu có và yêu cầu NameID/attributes nếu cần.
5. Kiểm thử luồng AuthnRequest/Response thật trong sandbox, kiểm tra chữ ký, thời gian, InResponseTo, Recipient, Destination và Audience.
6. Kiểm thử với proxy/cluster và với certificate rotation, metadata expiry và logout policy.

Không thêm tùy tiện Redirect/ACS endpoint trong metadata nếu ứng dụng **không thực sự phục vụ endpoint đó**. Metadata và cấu hình runtime phải mô tả **cùng một thực tế**.

## 12. Nhầm lẫn phổ biến cần tránh

1. **“EntityDescriptor chính là IdP.”** Không đúng; nó là khung entity. Chỉ vai trò IDPSSODescriptor cho biết entity công bố năng lực SAML IdP SSO.
2. **“Metadata URL và entityID là một.”** Không bắt buộc; một giá trị là nơi tải tài liệu, một giá trị là định danh logic.
3. **“SingleSignOnService thuộc SP.”** Không; đó là endpoint IdP nhận AuthnRequest. SP có AssertionConsumerService.
4. **“ACS và entityID phải cùng URL.”** Không; ACS là đích HTTP, entityID là định danh dùng trong issuer/audience.
5. **“Metadata có X509Certificate thì chắc chắn tin được.”** Không; nguồn metadata và trust anchor phải được xác minh.
6. **“Có SPSSODescriptor trong Spring thì app trở thành IdP.”** Không; Spring Security saml2Metadata() chủ yếu xuất SP metadata.
7. **“Muốn nhận encrypted Assertion chỉ cần có signing certificate IdP.”** Không; SP cần decryption key và IdP cần public encryption cert SP.
8. **“KeyDescriptor use=signing luôn là khóa ký của SP.”** Phụ thuộc role: trong IDPSSODescriptor là khóa IdP, trong SPSSODescriptor là khóa SP.
9. **“SingleLogoutService có mặt thì logout khắp hệ thống tự hoạt động.”** Không; cần cấu hình SLO, ký/verify và hỗ trợ của cả hai bên.
10. **“validUntil = thời hạn SSO session.”** Không; validUntil là kỳ hạn **metadata**.
11. **“protocolSupportEnumeration có thể thay HTTP-POST binding.”** Không; đó là protocol URI, binding là thuộc tính của endpoint.
12. **“Import XML thành công là trust đã được kiểm chứng.”** Không; parse thành công không đồng nghĩa kiểm chứng signature metadata và issuer đã được phê duyệt.

## 13. Câu hỏi tự kiểm tra

**1. XML có EntityDescriptor và IDPSSODescriptor/SingleSignOnService. Đây là metadata gì?**  
Là metadata cho entity công bố vai trò **IdP SSO**. SP dùng nó để tìm IdP entityID, SSO endpoint, certificate và policy.

**2. XML có EntityDescriptor và SPSSODescriptor/AssertionConsumerService. Đây là metadata gì?**  
Là metadata **SP SSO**, dùng cho IdP đăng ký entityID, ACS, signing/encryption public keys và các lựa chọn khác.

**3. SP entityID = https://sp.example.org/saml/metadata, ACS = https://sp.example.org/login/saml2/sso/corp. Hai URL có mâu thuẫn không?**  
Không. EntityID là định danh; ACS là địa chỉ nhận Response. Audience/Issuer và Recipient/Destination được kiểm tra theo các vai trò tương ứng.

**4. IdP metadata yêu cầu WantAuthnRequestsSigned=true; Spring SP chỉ bật saml2Login() thì đủ chưa?**  
Chưa. SP phải có signing private key phù hợp, IdP có public certificate SP và luồng thực sự ký AuthnRequest theo binding/policy.

**5. IdP vừa đổi signing cert, SP bắt đầu báo chữ ký không hợp lệ; có nên tắt verification?**  
Không. Cần cập nhật metadata/trust theo quy trình key rotation, kiểm tra certificate cũ/mới và lập kế hoạch overlap.

**6. Nếu có cả IDPSSODescriptor và SPSSODescriptor trong cùng EntityDescriptor, đây là metadata bị lỗi?**  
Không nhất thiết. Entity có thể đảm nhiệm nhiều vai trò; hệ thống tiêu thụ phải chọn role đúng.

**7. Spring Security xuất /saml2/metadata/corp nhưng không có IDPSSODescriptor. Đây có phải bug?**  
Không. Ứng dụng Spring ở cấu hình saml2Login là **Service Provider**; nó xuất SPSSODescriptor. IdP là hệ thống khác.

## 14. Nguồn tham khảo

- [OASIS – Metadata for the OASIS Security Assertion Markup Language (SAML) V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): đặc tả EntityDescriptor, IDPSSODescriptor, SPSSODescriptor, KeyDescriptor, endpoint và schema.
- [OASIS – SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): bối cảnh sử dụng metadata trong Web Browser SSO.
- [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): đọc IdP metadata và xuất SP metadata bằng **saml2Metadata()**.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, SP entityID/ACS và các filter SAML2.
- [SAML Metadata XML Schema](https://github.com/keycloak/keycloak/blob/main/saml-core/src/main/resources/schema/saml/v2/saml-schema-metadata-2.0.xsd): cấu trúc XML, thuộc tính và thứ tự các phần tử.

**Ghi nhớ:** **EntityDescriptor xác định một entity**, **IDPSSODescriptor công bố SSO endpoint/chứng chỉ/chính sách của IdP**, **SPSSODescriptor công bố ACS/chứng chỉ/chính sách của SP**. Phân biệt đúng ba lớp này giúp cấu hình trust, triển khai Spring Security SAML2 và chẩn đoán sự cố federation mà không phải bỏ qua các kiểm tra bảo mật.
