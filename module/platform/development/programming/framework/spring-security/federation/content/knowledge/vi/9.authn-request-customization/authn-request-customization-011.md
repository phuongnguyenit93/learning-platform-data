# Kiểm chứng thông điệp phát đi bằng metadata và chính sách của IdP

## 1. Mục tiêu và ranh giới bài học

Trong **SAML 2.0 Web Browser SSO**, ứng dụng Spring Security đóng vai trò **Service Provider (SP, Relying Party)** và tạo **AuthnRequest** để yêu cầu **Identity Provider (IdP, Asserting Party)** xác thực người dùng. Một yêu cầu có XML hợp lệ vẫn có thể bị IdP từ chối vì gửi sai SSO endpoint, sai Binding, không có chữ ký bắt buộc, thuật toán ký không được chấp nhận, Issuer/ACS chưa được đăng ký hoặc yêu cầu ForceAuthn/NameIDPolicy vượt chính sách.

Đề bài **“Kiểm chứng thông điệp phát đi bằng metadata và chính sách của IdP”** có hai lớp kiểm tra cần phân biệt:

1. **SP kiểm tra trước khi phát (outbound preflight/contract check):** AuthnRequest mà Spring sắp tạo và gửi có phù hợp **IdP metadata đã được tin cậy** và **hợp đồng cấu hình giữa SP–IdP** không?
2. **IdP kiểm chứng khi nhận (inbound verification ở phía IdP):** URL/Binding/message/chữ ký/cert/Issuer/ACS/timestamp/các yêu cầu mở rộng có tuân thủ chính sách hiện hành của IdP không? **Chỉ IdP mới xác nhận được bước này thực sự đạt.**

Không được đánh đồng “SP thấy metadata phù hợp” với “IdP đã chấp nhận AuthnRequest”. Metadata mô tả **năng lực/cấu hình công bố**, còn IdP có thể có **policy bổ sung** theo đối tác, tenant, môi trường và phiên bản sản phẩm. Kết quả cuối cùng phải được xác nhận bằng **luồng SSO thực tế trong môi trường thử nghiệm** cùng log/telemetry an toàn ở cả hai phía.

**Phạm vi:** Spring Security Servlet SAML 2.0 Service Provider, Java 17+, ví dụ Spring Boot 3.3.5/Spring Security 6.x; không triển khai IdP và không tùy biến response validator. Mọi ví dụ chứa domain example.org là mô phỏng, không phải endpoint thật.

### Những điều cần trả lời sau bài học

- AuthnRequest được so với **EntityDescriptor/IDPSSODescriptor/SPSSODescriptor** như thế nào?
- Phân biệt **SSO URL, HTTP binding, Destination, Issuer, ACS URL, ProtocolBinding** và **registrationId**.
- Khi **WantAuthnRequestsSigned=true**, Spring cần **private key SP** và **certificate đã được IdP tin cậy** ra sao?
- Vì sao chữ ký **HTTP-Redirect query** khác chữ ký **HTTP-POST XML**?
- Cấu hình Spring Security thế nào để tạo AuthnRequest đúng hợp đồng?
- Kiểm thử positive/negative case để phát hiện yêu cầu sai trước khi đưa hệ thống vào production.

## 2. Luồng AuthnRequest và vị trí kiểm chứng

Sơ đồ đơn giản cho SP-initiated SSO:

~~~text
[Browser]               [Spring Security SP]                       [IdP]
   | GET /private                |                                    |
   |--------------------------->|                                    |
   |                            | chọn RelyingPartyRegistration      |
   |                            | đọc asserting-party metadata      |
   |                            | tạo AuthnRequest                   |
   |                            | ký/serialize/encode theo Binding  |
   |                            | lưu AuthnRequest để correlation   |
   |<------ Redirect hoặc POST form ---------------------------------|
   |-------------------------- SAMLRequest ------------------------->|
   |                            |                                    | kiểm tra:
   |                            |                                    | - SSO endpoint/Binding
   |                            |                                    | - Issuer & SP registration
   |                            |                                    | - chữ ký SP và certificate
   |                            |                                    | - ACS, Destination, thời gian
   |                            |                                    | - ForceAuthn/NameIDPolicy...
   |                            |                                    |
   |<------------------------ trang login / MFA / SSO ----------------|
   |------------------------- đăng nhập ở IdP ---------------------->|
   |<------------------------ SAMLResponse --------------------------|
   | POST SAMLResponse          |                                    |
   |--------------------------->| xác minh Response/Assertion        |
   |<---------------------------| tạo Authentication nếu hợp lệ       |
~~~

**Saml2WebSsoAuthenticationRequestFilter** và một **Saml2AuthenticationRequestResolver** (trong Spring Security 6.x có **OpenSaml4AuthenticationRequestResolver**) phối hợp tạo AuthnRequest tại endpoint thường là **/saml2/authenticate/{registrationId}**. RelyingPartyRegistration cung cấp địa chỉ SSO, giao thức, EntityID, ACS và credential. Khi gửi, request context thường được lưu bằng **Saml2AuthenticationRequestRepository** để callback về sau có thể kiểm tra **InResponseTo**.

Việc tạo/ký AuthnRequest là **đường đi ra IdP**; việc nhận/kiểm SAMLResponse ở ACS là **đường trở lại SP**, có validator khác. Đề bài này tập trung đường **đi**, nhưng vẫn cần lưu ID request đúng để xác minh đường **về**.

### Hai hướng kiểm chứng độc lập

| Lớp | Chủ thể | Nguồn dữ liệu | Câu hỏi |
| --- | --- | --- | --- |
| **Trước khi phát** | SP/đội phát triển | IdP metadata, IdP onboarding policy, SP registration | Có gửi đúng định danh/endpoint/binding và dùng khóa/thuật toán hợp lệ không? |
| **Khi nhận** | IdP | Metadata và cấu hình SP đã đăng ký, key trust, IdP policy | Request có đúng SP được phép, chữ ký hợp lệ, timestamp/ACS/policy phù hợp không? |
| **Khi trả Response** | SP | IdP verification credential, AuthnRequest đã lưu và SAML profile | SAMLResponse/Assertion có được phát từ IdP đáng tin, đúng yêu cầu/đúng SP không? |

Một hệ thống có thể pass bước một nhưng fail bước hai do cấu hình IdP chưa đồng bộ hoặc chính sách riêng không thể suy ra từ metadata XML.

## 3. Metadata IdP: cần đọc đúng những gì?

Metadata IdP thường là một tài liệu XML chứa **EntityDescriptor** với **IDPSSODescriptor**. Phải xác thực nguồn tài liệu và chọn **đúng entityID/role**. Các thông tin liên quan trực tiếp tới AuthnRequest:

| Trường metadata | Nghĩa đối với yêu cầu phát đi | Cách dùng |
| --- | --- | --- |
| **EntityDescriptor.entityID** | Định danh logic **IdP**; cần phân biệt với URL tải metadata. | Đối chiếu asserting party ID, issuer của Response sau này; không nhầm với Issuer của AuthnRequest. |
| **IDPSSODescriptor.protocolSupportEnumeration** | IdP role hỗ trợ giao thức SAML2. | Tìm **urn:oasis:names:tc:SAML:2.0:protocol**. |
| **SingleSignOnService.Binding** | IdP nhận AuthnRequest qua binding nào: HTTP-Redirect, HTTP-POST... | Chọn một binding cả Spring và IdP đều hỗ trợ. |
| **SingleSignOnService.Location** | Endpoint **của IdP** nơi SP gửi yêu cầu. | Dùng làm đích gửi và thông thường là **AuthnRequest.Destination**. |
| **WantAuthnRequestsSigned** | IdP công bố mong muốn/yêu cầu AuthnRequest có chữ ký. | Nếu true, SP phải có signing credential và IdP phải tin certificate SP; nếu không có thuộc tính, giá trị mặc định theo metadata là false nhưng policy thực tế cần kiểm tra. |
| **NameIDFormat** | Những định dạng NameID IdP công bố hỗ trợ. | Cân nhắc khi tùy biến **NameIDPolicy.Format**; không mặc định yêu cầu emailAddress. |
| **KeyDescriptor use=signing** | Public certificate để **SP kiểm chứng bản tin IdP ký**. | Không nhầm với **private key của SP dùng ký AuthnRequest**. |
| **Extensions / SigningMethod (nếu có)** | Có thể công bố thuật toán ký được hỗ trợ/ưu tiên, tùy metadata profile. | Đàm phán thuật toán với IdP và cấu hình Spring, không đoán SHA1 cho tương thích. |
| **validUntil / cacheDuration** | Hạn hiệu lực và caching metadata. | Không sử dụng cấu hình đã hết hiệu lực; có quy trình refresh và rotation. |
| **SingleLogoutService** | Endpoint SAML logout. | Không phải endpoint nhận AuthnRequest; không chọn nhầm làm SSO Location. |

**Không có mọi policy trong metadata.** IdP có thể yêu cầu SP entityID chính xác, allowlist ACS URL, relay state rules, thuật toán ký cụ thể, MaximumAuthenticationAge, MFA/conditional access, RequestedAuthnContext, tenant restrictions hay loại binding riêng. Những yêu cầu đó phải lấy từ **hướng dẫn/admin của IdP** và kiểm thử thật.

### XML minh họa metadata IdP

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml/metadata"
    validUntil="2030-01-01T00:00:00Z">

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAuthnRequestsSigned="true">

    <md:NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </md:NameIDFormat>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso/redirect"/>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/sso/post"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Chỉ để học cấu trúc**, không phải metadata để import production; IDPSSODescriptor không có KeyDescriptor signing trong mẫu vì certificate thực tế chưa được cung cấp. Phải dùng metadata đúng từ IdP tin cậy và chứng chỉ hoàn chỉnh để SSO thực sự hoạt động.

**Giải nghĩa:** IdP hỗ trợ **hai SSO endpoints khác binding**, yêu cầu AuthnRequest được ký, công bố khả năng NameID persistent. Nếu SP chọn HTTP-Redirect, Destination nên khớp **/saml/sso/redirect** và chữ ký phải được tạo theo Redirect binding, **không phải XML ds:Signature trong payload để thay thế**.

## 4. Metadata SP và chính sách phía IdP

IdP không chỉ đọc metadata của chính nó. IdP còn cần **SP metadata/registration** để biết ai được phép yêu cầu đăng nhập và nên trả Response về đâu.

SP metadata có **EntityDescriptor với SPSSODescriptor**, gồm:

- **SP entityID:** định danh SP; thường xuất hiện ở **AuthnRequest.Issuer**.
- **AssertionConsumerService (ACS):** URL/id/binding mà IdP được phép gửi SAMLResponse; được SP công bố và IdP allowlist.
- **SP KeyDescriptor use=signing:** public certificate **SP** để IdP xác minh signed AuthnRequest.
- **SP KeyDescriptor use=encryption:** certificate dùng nếu IdP cần mã hóa Assertion gửi SP; không dùng để mặc nhiên xác minh chữ ký AuthnRequest.
- **AuthnRequestsSigned:** SP công bố nó ký AuthnRequest khi chính sách/credential thực tế tương ứng.
- **WantAssertionsSigned:** phía SP mong đợi loại chữ ký trên Assertion/Response; khác với WantAuthnRequestsSigned của IdP.

**Không đảo khóa:**

| Việc | Ai ký / giữ private key? | Ai kiểm tra / giữ public key? |
| --- | --- | --- |
| SP tạo **signed AuthnRequest** | **SP** giữ private signing key. | **IdP** kiểm bằng public signing certificate của SP đã được đăng ký. |
| IdP tạo **signed SAMLResponse/Assertion** | **IdP** giữ private signing key. | **SP** kiểm bằng public verification certificate của IdP đã được tin cậy. |
| IdP mã hóa Assertion cho SP | IdP dùng **public encryption key SP**. | SP dùng **private decryption key SP**. |
| Federation/đối tác ký metadata | Nhà cung cấp metadata/federation giữ private metadata-signing key. | Bên nhận tin certificate của signer theo trust anchor được phê duyệt. |

**Có public certificate trong XML chưa đủ tạo trust.** IdP phải nhận certificate SP qua quy trình onboarding được tin cậy; SP cũng phải lấy metadata IdP từ nguồn tin cậy. Cần có key rollover, expiry monitoring và chính sách thuật toán.

### Tương tác giữa hai flag ký

| IdP WantAuthnRequestsSigned | SP AuthnRequestsSigned | Điều cần xác nhận |
| --- | --- | --- |
| true | true | SP có private key hợp lệ, IdP biết public certificate, chữ ký đúng binding và thuật toán. |
| true | false | **Bất đồng cấu hình**; IdP thường từ chối unsigned AuthnRequest. |
| false hoặc không có | true | Thường có thể được chấp nhận nếu IdP tin khóa/cho phép signed request; xác minh policy cụ thể. |
| false hoặc không có | false | Có thể gửi unsigned nếu IdP policy cho phép. Đây **không** là bằng chứng IdP luôn chấp nhận. |

**WantAuthnRequestsSigned=false không có nghĩa cấm request đã ký**. Nó chỉ diễn tả IdP không công bố yêu cầu bắt buộc ở trường này; chính sách IdP riêng vẫn có thể khác. Ngược lại, **AuthnRequestsSigned=true** không thể chỉ là một chuỗi trong metadata nếu Spring không ký thật.

## 5. Các trường AuthnRequest phải đối chiếu

Mẫu XML để nhìn cấu trúc, **không có chữ ký** và một số thành phần tùy chọn đã được lược bỏ:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req_12345"
    Version="2.0"
    IssueInstant="2026-11-07T09:00:00Z"
    Destination="https://idp.example.org/saml/sso/redirect"
    AssertionConsumerServiceURL="https://app.example.com/login/saml2/sso/corp"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">

  <saml:Issuer>
    https://app.example.com/saml2/service-provider-metadata/corp
  </saml:Issuer>

  <samlp:NameIDPolicy
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      AllowCreate="true"/>
</samlp:AuthnRequest>
~~~

**Chưa phải bản tin SAML đầy đủ/đã ký.** Để đăng nhập, Spring/IdP phải dùng đúng metadata, certificate và profile; giá trị ở đây minh họa, không được dùng làm lời khuyên đặt một ID/timestamp cố định.

### Bảng đối chiếu từng trường

| AuthnRequest field | Nguồn đúng để so | Quy tắc/ý nghĩa |
| --- | --- | --- |
| **ID** | SP generator, request repository. | Độc nhất/khó đoán trong phạm vi cần thiết; dùng cho InResponseTo khi IdP trả Response. |
| **Version="2.0"** | SAML 2.0 protocol. | Không được dùng phiên bản khác một cách tùy tiện. |
| **IssueInstant** | Đồng hồ SP và skew IdP cho phép. | UTC/timestamp hợp lệ, tránh request quá cũ hoặc từ tương lai quá xa; đồng bộ NTP. |
| **Destination** | **SingleSignOnService.Location** đã chọn từ IDPSSODescriptor. | Thường phải đúng SSO endpoint nhận request; không dùng ACS hoặc metadata download URL. |
| **Issuer** | **SP EntityDescriptor.entityID** mà IdP đã đăng ký. | **Không phải IdP entityID**, cũng không phải login username hoặc registrationId. |
| **AssertionConsumerServiceURL** | **SP AssertionConsumerService Location** đã được IdP cho phép. | URL HTTPS public; phải khớp môi trường/tenant/registration. |
| **AssertionConsumerServiceIndex** | **index** ACS trong SP metadata được IdP tin cậy. | Dùng khi yêu cầu IdP chọn ACS theo index; không tự đặt index khác metadata. |
| **ProtocolBinding** | Binding SP mong đợi **Response tại ACS**, nếu được chỉ định. | **Không phải** binding dùng gửi AuthnRequest đi IdP. |
| **ForceAuthn** | Chính sách IdP và yêu cầu xác thực mới. | true yêu cầu IdP xác thực lại theo profile; thực tế phải kiểm chứng IdP có hỗ trợ và thỏa yêu cầu nghiệp vụ không. |
| **IsPassive** | IdP policy cho passive SSO. | true yêu cầu IdP không tương tác với user; có thể trả thất bại nếu cần prompt/MFA. |
| **NameIDPolicy.Format** | IDPSSODescriptor.NameIDFormat và thỏa thuận đối tác. | Không đòi format mà IdP không hỗ trợ; không coi emailNameID là user ID bất biến. |
| **RequestedAuthnContext** | Các authn context/class mà IdP hỗ trợ/cấp được. | Không “bật MFA” chỉ nhờ một chuỗi tùy tiện; IdP quyết định xác thực. |
| **Scoping** | Hợp đồng IdP/IdP proxy nếu dùng. | Có thể ảnh hưởng proxying/federation chain; cần kiểm thử riêng. |

**Quan trọng:** AuthnRequest.**ProtocolBinding** mô tả **binding cho SAMLResponse về ACS** (ví dụ HTTP-POST), không có nghĩa AuthnRequest phải được gửi bằng HTTP-POST. Một luồng phổ biến và hoàn toàn hợp lệ là **AuthnRequest đi bằng HTTP-Redirect**, **Response về bằng HTTP-POST**.

### ACS Index và ACS URL

Nếu dùng **AssertionConsumerServiceIndex**, IdP tra cứu endpoint từ **SPSSODescriptor** theo index. Nếu dùng **AssertionConsumerServiceURL** (và ProtocolBinding khi phù hợp), yêu cầu phải khớp endpoint đã được IdP allowlist. Theo các quy tắc SAML AuthnRequest, **không kết hợp tùy tiện ACS index và ACS URL/ProtocolBinding trong cùng request**; xem profile và implementation tương ứng. Metadata SP là nguồn để IdP kiểm được ACS hợp lệ, chứ không phải một URL browser tự chọn.

## 6. HTTP-Redirect và HTTP-POST: hai cách phát request, hai cách ký

Cùng một AuthnRequest XML có thể được mang qua **HTTP-Redirect** hoặc **HTTP-POST**, nhưng **cách đóng gói và chữ ký khác nhau**.

### 6.1. HTTP-Redirect binding

Với Redirect, SP thường:

1. Tạo AuthnRequest XML, có thể có các field đã tùy chỉnh.
2. DEFLATE theo yêu cầu binding, sau đó Base64 và URL-encode thành giá trị **SAMLRequest**.
3. Nếu cần ký: xây dữ liệu canonical theo quy tắc binding trên các cặp tham số URL-encoded theo thứ tự **SAMLRequest**, **RelayState nếu có**, **SigAlg**.
4. Ký chuỗi bytes đó bằng **private key SP**, URL-encode giá trị Base64 của chữ ký trong **Signature**.
5. Trả **HTTP 302** dẫn browser tới **IdP SingleSignOnService.Location** với query params tương ứng.

Ví dụ dạng URL (chỉ minh họa, không có chữ ký thật):

~~~text
https://idp.example.org/saml/sso/redirect
  ?SAMLRequest=<URL_ENCODED_DEFLATED_BASE64_AUTHNREQUEST>
  &RelayState=<URL_ENCODED_STATE>
  &SigAlg=<URL_ENCODED_SIGNATURE_ALGORITHM_URI>
  &Signature=<URL_ENCODED_BASE64_SIGNATURE>
~~~

**Không** copy ví dụ URL rồi xem là SAMLRequest hợp lệ. Trong Redirect binding, **chữ ký bảo vệ chuỗi query được quy định**, không phải cứ tìm **ds:Signature bên trong XML**. Khi xác minh, IdP phải dựa vào **giá trị URL-encoded nhận được** và đúng thứ tự ký; việc giải mã rồi URL-encode lại một cách khác có thể làm sai chữ ký.

**RelayState** (nếu có) nằm trong dữ liệu được ký theo quy tắc Redirect binding. Không coi RelayState là AuthnRequest.ID; không biến RelayState thành open redirect hoặc khóa bí mật dùng lại vô hạn. SAML Redirect có giới hạn URL từ proxy/browser; tùy số lượng trường và policy, IdP có thể yêu cầu chuyển sang POST.

### 6.2. HTTP-POST binding

Với POST, SP thường nhúng Base64 AuthnRequest XML vào form HTML auto-submit, gửi tới **IdP SingleSignOnService** có binding HTTP-POST.

~~~html
<form method="post" action="https://idp.example.org/saml/sso/post">
  <input type="hidden" name="SAMLRequest"
         value="BASE64_XML_PLACEHOLDER"/>
  <input type="hidden" name="RelayState"
         value="OPAQUE_STATE_PLACEHOLDER"/>
</form>
~~~

Đây là **form minh họa**, không phải một yêu cầu hợp lệ. Khi SAML XML cần ký theo POST binding phổ biến, chữ ký nằm trong **ds:Signature XML** (theo XML Digital Signature profile), khác **Signature query param** của Redirect. Một số profile đặc biệt như **HTTP-POST SimpleSign** có quy tắc riêng; **không áp dụng nhầm** sang HTTP-POST XML Signature mặc định.

### Bảng đối chiếu

| Đặc điểm | Redirect AuthnRequest | POST AuthnRequest |
| --- | --- | --- |
| HTTP | Browser **GET** tới IdP SSO endpoint. | Browser **POST** form tới IdP SSO endpoint. |
| Cấu hình IdP | SingleSignOnService Binding=HTTP-Redirect. | SingleSignOnService Binding=HTTP-POST. |
| Tham số SAMLRequest | DEFLATE + Base64 + URL encoding. | Base64 XML trong form field. |
| Chữ ký phổ biến | Query **SigAlg + Signature** bảo vệ SAMLRequest và RelayState (nếu có). | **ds:Signature** trong XML, theo binding/profile. |
| Điểm cần QA | Query URL-encoding, chữ ký raw query, đúng URL, không vô tình drop SigAlg/Signature. | XML signature/canonicalization, đúng endpoint/action, submit và session. |
| Lỗi hay gặp | IdP đòi signed Redirect nhưng request chỉ có unsigned SAMLRequest. | IdP đòi POST XML signature nhưng SP chỉ tạo Redirect signature. |

**Không nên tự implement DEFLATE/signature/XMLSig bằng vài dòng code ứng dụng**. Spring Security/OpenSAML đã có cơ chế binding và signing; khi debug, phân tích dữ liệu ở sandbox và đối chiếu policy, không bỏ xác minh chữ ký.

## 7. Chữ ký AuthnRequest và thuật toán: cần đủ ba điều kiện

Một AuthnRequest được IdP chấp nhận khi yêu cầu ký thường cần đồng thời:

1. **SP ký thật** bằng private key tương ứng với public certificate đã đăng ký ở IdP.
2. **Chữ ký đặt đúng chỗ theo binding** (Redirect query signature hoặc POST XML Signature) và bảo vệ đúng dữ liệu.
3. **Thuật toán được IdP cho phép** (thường RSA-SHA256 hoặc thuật toán hiện đại theo hợp đồng), kèm chuỗi certificate và rotation phù hợp.

Nếu thiếu bất kỳ điều kiện nào, XML AuthnRequest có thể “đúng field” nhưng bị IdP từ chối vì **InvalidSignature**, **SignatureRequired**, **UntrustedRelyingParty**, **UnsupportedAlgorithm** hoặc thông báo nhà cung cấp tương ứng.

### RSA-SHA256 và thuật toán khác

Spring Security mặc định lựa chọn thuật toán ký phù hợp (tài liệu mô tả **rsa-sha256** là mặc định thông thường). IdP có thể công bố signing algorithms qua metadata extension hoặc yêu cầu thuật toán qua hợp đồng. Không chuyển về **RSA-SHA1/DSA-SHA1** chỉ để “cho tương thích” nếu policy bảo mật cấm; các thuật toán yếu phải được loại trừ theo yêu cầu an toàn hiện hành.

Nếu ứng dụng cần thuật toán khác, với phiên bản Spring Security phù hợp, có thể cấu hình danh sách **assertingPartyMetadata.signingAlgorithms(...)** hoặc dùng metadata đã phê duyệt chứa SigningMethod. Phải kiểm thử binding/algorithm thực tế tại IdP. **Metadata có thể chỉ công bố preference, không bảo đảm mọi key/algorithm dùng được trong mọi binding.**

### Certificate và private key

- **SP private key:** phải lưu an toàn trong secret manager/keystore/KMS/HSM tương thích kiến trúc, tránh commit vào mã nguồn, container image hay Google Sheet.
- **SP public signing certificate:** gửi cho IdP qua onboarding, có thể công bố trong SPSSODescriptor KeyDescriptor use=signing.
- **IdP public verification certificate:** SP dùng để kiểm SAMLResponse/Assertion; **không dùng để ký AuthnRequest**.
- **Rollover:** IdP cần trust certificate SP mới trước khi SP chuyển sang key mới; cần giai đoạn chồng lấn và rollback hợp lệ.
- **Thuật toán/chữ ký:** không đủ chỉ có file .crt; private key phải khớp public key và thuật toán/định dạng Spring hỗ trợ.

**Không dùng chứng chỉ TLS của reverse proxy làm SP signing credential chỉ vì hostname trùng.** Certificate TLS và certificate ký SAML có nhiệm vụ khác; có thể trùng trong một số hạ tầng nhưng phải được thiết kế/thỏa thuận chứ không suy ra.

## 8. Spring Security lấy metadata để phát AuthnRequest như thế nào?

Ở ứng dụng Servlet, **spring-security-saml2-service-provider** dùng **RelyingPartyRegistration**. Registration gồm cả thông tin SP và IdP:

| Field | Thuộc phía nào? | Tác động lên outbound AuthnRequest |
| --- | --- | --- |
| **registrationId** | Khóa định danh cấu hình của SP ứng dụng. | Chọn đối tác tại /saml2/authenticate/{registrationId}. |
| **entityId** | SP | Điền **AuthnRequest.Issuer**. |
| **assertionConsumerServiceLocation** | SP | Điền **AssertionConsumerServiceURL** và phục vụ đối chiếu IdP allowlist. |
| **signingX509Credentials** | SP | Chứa private key/public certificate cho việc **ký AuthnRequest** nếu cần. |
| **assertingPartyMetadata.entityId** | IdP | Định danh IdP; không chèn thay SP Issuer. |
| **assertingPartyMetadata.singleSignOnServiceLocation** | IdP | Chọn endpoint gửi và thường điền **AuthnRequest.Destination**. |
| **assertingPartyMetadata.singleSignOnServiceBinding** | IdP | Binding SP dùng khi gửi yêu cầu: REDIRECT hoặc POST theo hỗ trợ thực tế. |
| **assertingPartyMetadata.wantAuthnRequestsSigned** | IdP | Cho biết yêu cầu ký; Spring dùng để quyết định cách phát theo cấu hình/phiên bản. |
| **assertingPartyMetadata.signingAlgorithms** | IdP | Ảnh hưởng lựa chọn thuật toán ký khi thông tin này được sử dụng. |
| **assertingPartyMetadata.verificationX509Credentials** | IdP | Dùng kiểm phản hồi IdP sau này, không phải để SP ký yêu cầu. |

**RelyingPartyRegistrationRepository** chứa các registration được phép. Nó không phải kho người dùng và không phát hành Assertion. Đăng nhập SAML của Spring Security là tích hợp **Service Provider**, còn IdP vẫn cần được triển khai/vận hành riêng.

### Vì sao cần đọc metadata IdP từ nguồn tin cậy?

Nếu attacker có thể thay URL metadata IdP theo ý họ, họ có thể tác động endpoint Destination, Issuer và certificate trong registration. Vì vậy:

- Chỉ nạp metadata IdP từ URL/tệp được tổ chức phê duyệt;
- Dùng HTTPS và trust phù hợp; nếu policy yêu cầu **ký metadata**, phải xác minh chữ ký với **metadata trust anchor** đã được biết trước;
- Không cho browser quyết định metadata URL, signing key hoặc SSO endpoint;
- Kiểm tra **entityID**, **role IDPSSODescriptor**, **SingleSignOnService**, **validUntil/cacheDuration**, certificate rotation;
- Kiểm tra thay đổi metadata theo quy trình, không tự động chấp nhận unknown IdP làm đối tác.

**Parse XML thành công không đồng nghĩa metadata đã được xác thực chữ ký.** Một số Spring Security phiên bản mới có API riêng để quản lý signed metadata/refresh; không nên sao chép API Spring Security 7 vào Boot 3.x nếu chưa đối chiếu.

## 9. Cấu hình mẫu Spring Boot 3.3.5 / Java 17: signed AuthnRequest

Ví dụ minh họa một ứng dụng **SP** tích hợp một IdP yêu cầu AuthnRequest được ký. Mẫu này chỉ hoạt động khi có **IdP metadata thật**, **SP private key/certificate thật**, IdP đã đăng ký SP entityID và ACS đúng.

### 9.1. Maven

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
    <artifactId>outbound-authnrequest-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
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

### 9.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-saml-signing-private.pem"
                  certificate-location: "file:/run/secrets/sp-saml-signing-public.crt"
            assertingparty:
              metadata-uri: "${SAML_IDP_METADATA_URI}"

server:
  port: 8080
~~~

**corp** là registrationId. **SAML_IDP_METADATA_URI** là URL IdP metadata thật được phê duyệt. Đường **/run/secrets/** chỉ minh họa mô hình mount secret; phải thay bằng đường thực theo hệ điều hành/container. Spring Boot đọc **SP signing private key + matching public X.509 certificate**, không phải IdP verification certificate.

**Lưu ý:** khi IdP metadata đặt **WantAuthnRequestsSigned=true**, signing credentials phải sẵn sàng và IdP phải có **public certificate SP** đã đăng ký. Nếu bạn dùng metadata có WantAuthnRequestsSigned=false nhưng tổ chức vẫn yêu cầu ký theo policy, cần đồng bộ IdP registration/chính sách và cấu hình Spring; không chỉ đổi một flag cục bộ rồi xem như IdP đã chấp nhận.

Nếu IdP chỉ cho phép **HTTP-POST AuthnRequest**, registration phải chọn **SingleSignOnService.Binding=POST** từ metadata/đàm phán. Không tùy ý tạo một URL POST bằng cách đổi path từ endpoint Redirect.

### 9.3. Application class

**src/main/java/com/example/outbound/OutboundApplication.java**

~~~java
package com.example.outbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OutboundApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboundApplication.class, args);
    }
}
~~~

### 9.4. SecurityFilterChain

**src/main/java/com/example/outbound/SecurityConfig.java**

~~~java
package com.example.outbound;

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

**Giải thích:** Spring Security sử dụng registration được cấu hình, sinh AuthnRequest tại **/saml2/authenticate/corp**, xử lý Response tại ACS thường là **/login/saml2/sso/corp**, và xuất metadata SP tại **/saml2/metadata/corp**.

### 9.5. Controller đơn giản

**src/main/java/com/example/outbound/DemoController.java**

~~~java
package com.example.outbound;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Outbound AuthnRequest SP ready";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
        return "NameID=" + user.getName();
    }
}
~~~

Chạy tại thư mục chứa pom.xml sau khi đã có IdP metadata và signing files thật:

~~~bash
mvn spring-boot:run
~~~

Kết quả có thể kiểm chứng:

- **GET http://localhost:8080/** trả chính xác **Outbound AuthnRequest SP ready** nếu ứng dụng khởi động thành công.
- **GET http://localhost:8080/saml2/metadata/corp** xuất **SPSSODescriptor** từ registration corp. Kiểm tra **SP entityID, ACS và KeyDescriptor signing** đúng; không nhầm đây là IdP metadata.
- **GET http://localhost:8080/saml2/authenticate/corp** bắt đầu AuthnRequest đi tới IdP SSO endpoint. Redirect hay POST phụ thuộc cấu hình IdP binding.
- **GET http://localhost:8080/me** nếu chưa đăng nhập thì bắt đầu SAML flow; chỉ khi IdP chấp nhận request và Spring kiểm chứng Response hợp lệ mới trả **NameID=<giá trị IdP cấp>**. Không có NameID/response cố định.

**Không có IdP metadata và private key thật thì ví dụ không tự đăng nhập thành công**. Đó là giới hạn mong đợi của một SP, không phải lý do bỏ signature verification.

## 10. Tùy chỉnh AuthnRequest và kiểm chứng lại sau mỗi thay đổi

Spring Security 6.x cho phép tùy biến OpenSAML AuthnRequest bằng **OpenSaml4AuthenticationRequestResolver**. Ví dụ, IdP có thể cho phép/đòi **ForceAuthn=true** trong những tình huống bảo mật cao.

Đây là **bean bổ sung** trong cùng ứng dụng Spring Boot 3.3.5 ở trên; không phải Java class chạy độc lập bằng javac:

**src/main/java/com/example/outbound/RequestCustomizationConfig.java**

~~~java
package com.example.outbound;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;

@Configuration
public class RequestCustomizationConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        var registrationResolver =
                new DefaultRelyingPartyRegistrationResolver(registrations);
        var resolver =
                new OpenSaml4AuthenticationRequestResolver(registrationResolver);

        resolver.setAuthnRequestCustomizer(context ->
                context.getAuthnRequest().setForceAuthn(true));

        return resolver;
    }
}
~~~

**Giải thích:** Bean này cung cấp resolver để Spring Security tạo **AuthnRequest có ForceAuthn=true**. Framework vẫn quản lý signing/Binding/registration theo cấu hình; **ForceAuthn không phải chữ ký** và không tự bảo đảm IdP sẽ thực thi MFA. Nếu tùy biến Issuer, Destination hoặc ACS, phải đối chiếu metadata và IdP allowlist; nếu tùy biến trường XML **sau khi ký**, chữ ký có thể mất hiệu lực. Trình tự an toàn là **tùy chỉnh thông điệp trước khi framework ký**, không tự sửa URL/form output bằng filter muộn.

**Quan trọng về phiên bản:** Spring Security 6.x dùng OpenSaml4AuthenticationRequestResolver trong nhiều phiên bản; các tài liệu mới hơn có thể dùng **OpenSaml5AuthenticationRequestResolver**. Phải đối chiếu class/import với phiên bản Spring Security thực tế. Ví dụ này hướng vào **Boot 3.3.5/Security 6.x**, không chuyển nguyên xi sang Spring Security 7.x.

### Các trường tùy biến và rủi ro

| Thay đổi AuthnRequest | Trường/phần tử | Kiểm chứng thêm |
| --- | --- | --- |
| Yêu cầu đăng nhập lại | ForceAuthn=true | IdP có chấp nhận và hiểu đúng policy? Có tương thích IsPassive? |
| Chặn giao diện login | IsPassive=true | IdP có thể trả lỗi NoPassive nếu cần tương tác. |
| Chọn NameID | NameIDPolicy.Format/AllowCreate | IdP hỗ trợ format? Có thỏa thuận định danh ổn định? |
| Đòi authn context | RequestedAuthnContext | IdP hỗ trợ lớp/cơ chế tương ứng? Không đồng nghĩa tự bật MFA. |
| Đổi Destination | AuthnRequest.Destination | Có khớp IdP SingleSignOnService Location được chọn? |
| Đổi Issuer | AuthnRequest.Issuer | Có khớp SP entityID mà IdP đã đăng ký? |
| Đổi ACS | AssertionConsumerServiceURL / Index | Có nằm trong SP metadata và IdP allowlist? |
| Đổi Redirect/POST | Asserting party SSO binding | Đúng SSO endpoint và vị trí chữ ký theo Binding? |
| Đổi SigAlg | Signing algorithm của registration | IdP có tin/cho phép thuật toán? SP key có tương thích không? |

**Không cho user cuối quyết định trực tiếp Destination, Issuer, ACS, signing key hoặc thuật toán** qua query parameter. Đây là các giá trị tin cậy được quản lý bởi cấu hình đối tác.

## 11. Quy trình kiểm chứng outbound có thể vận hành được

Một bài kiểm thử không nên kết luận “hợp lệ” chỉ vì browser được redirect. Thực hiện theo thứ tự:

### A. Đóng băng hợp đồng đối tác

1. Lưu **IdP entityID**, metadata URL tin cậy/phiên bản metadata và checksum/phiên bản theo chính sách.
2. Chọn **SingleSignOnService** đúng Binding và Location; không suy từ tên trang login.
3. Chốt **WantAuthnRequestsSigned**, signing algorithm, SP certificate fingerprint (nếu thỏa thuận) và IdP policy có bắt signed requests không.
4. Chốt **SP entityID, ACS URL/binding/index**, metadata SP đã giao cho IdP, NameIDFormat và custom parameters.
5. Ghi lại chính sách riêng: ForceAuthn, IsPassive, RequestedAuthnContext, RelayState, skew, maximum request age, tenant/account restrictions.
6. Chốt môi trường **dev/test/prod**: mỗi môi trường có thể có entityID, ACS, key và SSO endpoint khác nhau.

### B. Kiểm tra cấu hình Spring trước khi gửi

1. Xác minh **RelyingPartyRegistrationRepository** có registrationId hợp lệ và không vô tình gán IdP khác.
2. Đối chiếu **SP entityId** và **assertionConsumerServiceLocation** đã resolve, đặc biệt sau proxy.
3. Đối chiếu **as­serting party entityId**, SSO URL, Binding và WantAuthnRequestsSigned được nạp từ metadata/policy.
4. Xác minh **signingX509Credentials** có private key SP và public cert khớp, file quyền hạn an toàn; IdP đã trust cert.
5. Xác minh thuật toán ký được cho phép; loại thuật toán yếu/không tương thích theo chính sách.
6. Ghi nhận **AuthnRequest.ID**, registrationId và timestamp trong hệ thống correlation an toàn (không log private key, secret hay raw assertion).

### C. Quan sát AuthnRequest thực tế trong sandbox

1. Mở **/saml2/authenticate/corp** từ browser sandbox chưa đăng nhập.
2. Nếu Redirect, quan sát HTTP **302 Location** tới IdP SSO URL; kiểm tra có **SAMLRequest**, và khi bắt buộc ký phải có **SigAlg** + **Signature** (RelayState tùy dùng).
3. Nếu POST, quan sát form auto-submit, **action URL**, **SAMLRequest** và chữ ký XML khi cần.
4. Dùng công cụ SAML protocol chuyên dụng trong **môi trường test** để xem XML đã decode, đúng Version/IssueInstant/ID/Issuer/Destination/ACS/ProtocolBinding và các trường tùy biến.
5. Kiểm **chữ ký bằng public certificate SP đã IdP phê duyệt** theo thuật toán và binding. Không xác minh bằng cert tùy ý lấy từ chính request chưa tin cậy.
6. So timestamp UTC và skew; kiểm proxy host/scheme/port; không dùng localhost làm ACS production.

**Lưu ý về bảo mật:** devtools/HTTP traces có thể chứa thông tin đăng nhập, RelayState và SAMLResponse. Chỉ lưu bằng chứng đã làm sạch, giới hạn truy cập, không chia sẻ raw production payload qua chat/ticket.

### D. Xác nhận IdP tiếp nhận

Một AuthnRequest thật có thể bị IdP từ chối dù ký đúng nếu SP chưa đăng ký, ACS không nằm allowlist hoặc policy ForceAuthn/NameIDFormat không hợp lệ. Dùng log IdP/sandbox để xác nhận:

- Đã đi vào đúng **SSO endpoint và binding**;
- **SP issuer** được nhận diện;
- **Chữ ký** xác thực thành công bằng key SP đã trust;
- **ACS** được cho phép, request ID và IssueInstant hợp lệ;
- Policy NameID/AuthnContext/ForceAuthn/IsPassive được chấp nhận;
- Nếu người dùng được xác thực, IdP phát Response về **đúng ACS** và SP xác minh được Response/InResponseTo.

Nếu IdP trả lỗi, phải phân biệt **request bị từ chối ở IdP** với **Response về SP bị SP từ chối**. Hai lỗi nằm ở hai hướng và cần phương pháp chẩn đoán khác nhau.

## 12. Java 17 độc lập: audit hợp đồng metadata và AuthnRequest

Để hiểu nguyên tắc đối chiếu **metadata IdP và message sắp gửi**, ví dụ dưới dùng **Java chuẩn JDK 17** để parse một metadata XML tĩnh được viết ngay trong mã, tìm một **IDPSSODescriptor**, kiểm **WantAuthnRequestsSigned**, một **SingleSignOnService** và so với cấu hình SP mô phỏng.

**Giới hạn bắt buộc:** đây **chỉ là kiểm tra các trường cấu hình**, không làm XML signature verification, trust-bootstrap, XSD/profile validation, DEFLATE, Base64, certificate chain, ACS allowlist tại IdP hay xác minh phản hồi. **Không đưa nó vào production thay Spring Security/OpenSAML**, và không kết luận IdP đã chấp nhận request khi chương trình in PASS.

**OutboundContractDemo.java**

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class OutboundContractDemo {
    private static final String MD =
            "urn:oasis:names:tc:SAML:2.0:metadata";
    private static final String REDIRECT =
            "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect";

    public static void main(String[] args) throws Exception {
        String metadata = """
                <md:EntityDescriptor
                  xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                  entityID="https://idp.example.org/metadata">
                  <md:IDPSSODescriptor
                    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
                    WantAuthnRequestsSigned="true">
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
                new InputSource(new StringReader(metadata)));
        Element entity = document.getDocumentElement();
        NodeList roles = entity.getElementsByTagNameNS(
                MD, "IDPSSODescriptor");
        Element idpRole = (Element) roles.item(0);
        Element sso = (Element) idpRole.getElementsByTagNameNS(
                MD, "SingleSignOnService").item(0);

        String configuredIdp = "https://idp.example.org/metadata";
        String outgoingDestination = "https://idp.example.org/sso";
        boolean spHasSigningKey = true;
        boolean requestActuallySigned = true;
        boolean wantSigned = Boolean.parseBoolean(
                idpRole.getAttribute("WantAuthnRequestsSigned"));

        boolean issuerMatches = configuredIdp.equals(
                entity.getAttribute("entityID"));
        boolean bindingMatches = REDIRECT.equals(sso.getAttribute("Binding"));
        boolean destinationMatches = outgoingDestination.equals(
                sso.getAttribute("Location"));
        boolean signingPolicyMatches = !wantSigned
                || (spHasSigningKey && requestActuallySigned);

        boolean pass = issuerMatches && bindingMatches
                && destinationMatches && signingPolicyMatches;

        System.out.println("IdP entity matched: " + issuerMatches);
        System.out.println("Redirect binding matched: " + bindingMatches);
        System.out.println("Destination matched: " + destinationMatches);
        System.out.println("Signed request required: " + wantSigned);
        System.out.println("Signing policy matched: " + signingPolicyMatches);
        System.out.println("Outbound contract: " + (pass ? "PASS" : "FAIL"));

        boolean wrongDestination = "https://other.example.org/sso"
                .equals(sso.getAttribute("Location"));
        System.out.println("Wrong destination accepted: " + wrongDestination);
    }
}
~~~

Biên dịch và chạy trong thư mục có file:

~~~bash
javac OutboundContractDemo.java
java OutboundContractDemo
~~~

**stdout chính xác:**

~~~text
IdP entity matched: true
Redirect binding matched: true
Destination matched: true
Signed request required: true
Signing policy matched: true
Outbound contract: PASS
Wrong destination accepted: false
~~~

**Giải thích:** “Outbound contract: PASS” chỉ nói các trường tĩnh của bản mô phỏng **nhất quán về mặt logic**. Chương trình **không tạo chữ ký thật** (biến requestActuallySigned là giả định), không biết chính sách IdP ngoài metadata, không có SP issuer/ACS trong input và không có HTTP transport. **Trong sản phẩm thật, chỉ IdP xác minh được chữ ký AuthnRequest, và Spring/OpenSAML mới xử lý giao thức SAML.**

Nếu thay outgoingDestination thành **https://other.example.org/sso**, phép đối chiếu Destination phải thất bại. Nếu muốnSigned=true nhưng spHasSigningKey=false hoặc requestActuallySigned=false, signingPolicyMatches=false. Những điều kiện phủ định này phải trở thành **test case** khi triển khai thực.

## 13. Bộ kiểm thử dương tính/âm tính

Để kiểm từng điều kiện riêng lẻ, dùng **IdP/SP sandbox** với metadata/key test đã được phê duyệt. Khi muốn kiểm signature mismatch, tạo request **đúng binding** và ký bằng khóa test tương ứng; đừng sửa URL query ký xong rồi dùng lỗi tổng quát để kết luận chính xác nguyên nhân.

| # | Kịch bản outbound AuthnRequest | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Chọn SSO Location/Binding đúng metadata, SP issuer và ACS đúng, signed request theo policy, timestamp hợp lệ | IdP có thể **chấp nhận request** và tiếp tục login. |
| 2 | IDPSSODescriptor WantAuthnRequestsSigned=true, SP gửi unsigned request | **Từ chối** do thiếu chữ ký. |
| 3 | Signed Redirect có SAMLRequest nhưng thiếu SigAlg/Signature | **Từ chối** khi IdP bắt signed request. |
| 4 | Signed POST nhưng IdP đang chờ chữ ký Redirect query cho endpoint Redirect | **Từ chối** do binding/signature placement mismatch. |
| 5 | SP dùng private key không tương ứng certificate IdP đã đăng ký | **Từ chối** invalid/untrusted signature. |
| 6 | SP chọn thuật toán ký IdP policy cấm | **Từ chối** unsupported/weak algorithm. |
| 7 | AuthnRequest.Destination là SP ACS thay vì IdP SSO Location | **Từ chối** Destination/endpoint mismatch. |
| 8 | Gửi Redirect AuthnRequest đến SSO endpoint chỉ khai POST | **Từ chối** binding mismatch. |
| 9 | AuthnRequest.Issuer là IdP entityID thay vì SP entityID | **Từ chối** unknown/invalid SP. |
| 10 | SP issuer đúng nhưng chưa đăng ký tại IdP | IdP thường **từ chối unknown SP**. |
| 11 | SP issuer hợp lệ, ACS URL trỏ sang tenant/application khác | **Từ chối** ACS không nằm trong allowlist. |
| 12 | ACS dùng http://internal thay HTTPS public URL | **Từ chối** nếu IdP không cho phép; cần sửa proxy/config. |
| 13 | AssertionConsumerServiceIndex không tồn tại trong SP metadata IdP tin cậy | **Từ chối** hoặc lỗi ACS index. |
| 14 | ProtocolBinding chỉ HTTP-Artifact nhưng SP/IdP chỉ triển khai HTTP-POST Response | **Từ chối** binding yêu cầu không hỗ trợ. |
| 15 | IssueInstant quá cũ/tương lai theo chính sách IdP | **Từ chối** hoặc báo request validity error. |
| 16 | Trùng AuthnRequest.ID đã dùng trước đó | **Từ chối** theo chính sách replay/duplicate ID. |
| 17 | NameIDPolicy.Format không được IdP hỗ trợ | **Từ chối** hoặc status policy/format error theo IdP. |
| 18 | IsPassive=true nhưng IdP cần login/MFA tương tác | IdP có thể trả **NoPassive**; không ép IdP hiển thị form trái policy. |
| 19 | ForceAuthn=true nhưng IdP không hỗ trợ/chính sách khác | Phải xác minh cách IdP thực thi; không tự khẳng định đã xác thực lại. |
| 20 | Request hợp lệ, nhưng Response bị từ chối tại SP do invalid audience/recipient | Phân biệt **outbound thành công** với **inbound Response validation thất bại**. |
| 21 | Hai registration khác IdP, request dùng signing cert của registration còn lại | **Từ chối** bởi IdP không tin cert/issuer cho đối tác này. |
| 22 | IdP metadata mới đã đổi SSO endpoint/cert policy nhưng SP dùng cấu hình cũ | Có thể **từ chối**; cần refresh metadata/trust có kiểm soát. |
| 23 | Query Redirect bị reverse proxy sửa URL encoding sau khi ký | **Từ chối** invalid query signature. |
| 24 | Signed AuthnRequest dùng RelayState điều hướng sang domain không được phép | Ứng dụng phải phòng **open redirect/state injection**; kiểm thử end-to-end. |

**Test âm tính đạt** khi IdP/SP từ chối một cách có chủ đích và không cấp phiên trái chính sách. Không “sửa lỗi” bằng cách xóa toàn bộ yêu cầu chữ ký, mở wildcard ACS hoặc chấp nhận mọi issuer.

### Các phép kiểm chứng không nên làm với production payload

- Không dán SAMLRequest/SAMLResponse thật lên website decoder công cộng.
- Không gửi private key qua chat/ticket hoặc tải private key lên công cụ thử nghiệm bên ngoài.
- Không log raw SAMLResponse, cookie phiên, NameID/Attributes nhạy cảm hay toàn bộ signed query chứa state.
- Không để debug endpoint tạo unsigned AuthnRequest tồn tại trong production mà không có policy rõ ràng.
- Không tự tăng clock skew hàng giờ để qua lỗi IssueInstant.

## 14. Bảng lỗi và cách khoanh vùng

| Dấu hiệu | Nhánh kiểm tra đầu tiên | Hướng khắc phục |
| --- | --- | --- |
| IdP báo **SignatureRequired/Unsigned AuthnRequest** | WantAuthnRequestsSigned, policy ký và actual wire signature. | Cấu hình SP signing private key/certificate, xác nhận IdP trust và binding. |
| IdP báo **InvalidSignature** | Certificate SP, algorithm, Redirect query encoding/POST XML Signature. | So khóa, cert, signing mode và proxy; không tắt verification. |
| IdP báo **Unknown SP / Invalid Issuer** | AuthnRequest.Issuer và SP entityID registered. | Đồng bộ SP entityID trong IdP onboarding và metadata SP. |
| IdP báo **Invalid Destination** | IdP SingleSignOnService Location, AuthnRequest.Destination. | Chọn đúng endpoint theo binding, không nhầm ACS URL. |
| IdP báo **Invalid ACS / Reply URL mismatch** | ACS URL/index và SP metadata. | Sửa IdP allowlist, public HTTPS URL, path và reverse proxy. |
| IdP báo **Unsupported Binding** | HTTP-Redirect/POST request binding, ProtocolBinding của Response. | Phân biệt hai hướng binding và chọn cấu hình được IdP công bố. |
| IdP báo **Unsupported NameIDFormat** | NameIDPolicy.Format và IDPSSODescriptor.NameIDFormat. | Thống nhất format với IdP, không ép emailAddress nếu chưa được hỗ trợ. |
| IdP báo **NoPassive** | IsPassive=true và login/MFA cần tương tác. | Thay đổi nhu cầu passive hoặc UX, không buộc IdP vi phạm policy. |
| IdP yêu cầu fresh authentication | ForceAuthn, IdP session/MFA policy. | Kiểm thử lại ở IdP; ForceAuthn không tự đảm bảo MFA. |
| Request có URL **http://internal:8080** trong production | BaseUrl/forwarded headers/ACS/entityID. | Sửa reverse proxy và metadata trước khi ký/gửi request. |
| Signed Redirect valid ở local nhưng fail qua LB | URL encoding/query normalization, proxy rewriting. | Quan sát request ở ranh giới cuối và không sửa signed query sau signing. |
| Chứng chỉ SP mới được dùng nhưng IdP vẫn tin khóa cũ | SP signing credential rotation và IdP certificate enrollment. | Rollout có overlap, thông báo IdP trước khi switch private key. |
| IdP đã chấp nhận request nhưng Spring vẫn không login | Response issuer/signature/audience/recipient/InResponseTo. | Debug chiều **IdP → SP**, không chỉ nhìn outbound AuthnRequest. |

**Không kết luận “Spring lỗi” chỉ từ status SAML chung.** Cần đối chiếu trạng thái và thời điểm: có HTTP redirect/form gửi chưa, IdP có nhận không, lỗi nằm ở bước kiểm ký request hay bước xử lý Response, và đúng registrationId hay chưa.

## 15. Checklist triển khai production

**Nguồn tin cậy và onboarding**

- Metadata IdP phải từ nguồn có xác minh, đúng entityID và IDPSSODescriptor.
- Có thỏa thuận kiểm chữ ký metadata nếu cần, refresh/rotation đúng validUntil/cacheDuration.
- IdP có SP entityID/ACS allowlist, public signing certificate của SP và thuật toán được phép.

**Thông điệp phát đi**

- RegistrationId lựa chọn đúng IdP; không cho user điều khiển trực tiếp metadata URL.
- SSO Location và Binding lấy từ cấu hình IdP đã tin cậy; AuthnRequest.Destination đúng.
- AuthnRequest.Issuer là SP entityID; ACS URL/index khớp SP metadata đã đăng ký.
- ProtocolBinding diễn tả Response tại ACS, không nhầm với outbound HTTP binding.
- WantAuthnRequestsSigned và SP signing credential nhất quán; khi ký phải đúng binding/chữ ký/thuật toán.
- IssueInstant/ID/ForceAuthn/IsPassive/NameIDPolicy/RequestedAuthnContext theo hợp đồng; không tự tạo giá trị cố định/không hợp lệ.

**Vận hành bảo mật**

- Private key SP không nằm trong mã nguồn, logs, Docker image hay tài liệu chia sẻ; có quản lý quyền và rotation.
- HTTPS public URL, forwarded headers an toàn và NTP nhất quán.
- AuthnRequest được lưu đúng browser context để **Response.InResponseTo** được kiểm chứng sau này.
- Hỗ trợ multiple IdPs/tenants theo allowlist; không dùng issuer chưa xác thực để tự tin tạo trust.
- Kiểm cả positive/negative flows trong sandbox, ghi nhận lỗi kỹ thuật đã làm sạch.
- Giữ validation SAMLResponse/Assertion bật đầy đủ: signature, issuer, audience, destination, recipient, time và replay.

## 16. Câu hỏi ôn tập

**Câu 1.** IdP có WantAuthnRequestsSigned=true. Spring chỉ tải được metadata và gửi Redirect không có SigAlg/Signature. Điều kiện đã đạt chưa?  
**Đáp án:** **Chưa.** Metadata chỉ mô tả policy; SP phải ký bằng private key tương ứng certificate IdP tin cậy, theo đúng Redirect binding và thuật toán.

**Câu 2.** AuthnRequest.Issuer phải bằng IdP entityID hay SP entityID?  
**Đáp án:** **SP entityID** mà IdP đăng ký. Đó là SP phát yêu cầu; IdP entityID là danh tính của bên nhận và sau này phát Response.

**Câu 3.** AuthnRequest đi bằng HTTP-Redirect nhưng ProtocolBinding=HTTP-POST. Có mâu thuẫn không?  
**Đáp án:** **Không.** Outbound request sử dụng Redirect; ProtocolBinding yêu cầu IdP trả **Response qua HTTP-POST tới ACS**.

**Câu 4.** IdP KeyDescriptor use=signing là khóa SP cần để ký AuthnRequest?  
**Đáp án:** **Không.** SP ký bằng **private key SP**. KeyDescriptor signing của IdP dùng để SP xác minh thông điệp IdP ký; IdP kiểm AuthnRequest bằng **public certificate SP** đã đăng ký.

**Câu 5.** Browser được chuyển tới trang đăng nhập IdP, liệu AuthnRequest chắc chắn được IdP chấp nhận?  
**Đáp án:** **Không.** Được điều hướng chỉ chứng minh request đã gửi; IdP vẫn kiểm issuer, signature, ACS, binding, policy và có thể từ chối.

**Câu 6.** Sau khi bật ForceAuthn=true, có được kết luận user đã xác thực lại bằng MFA?  
**Đáp án:** **Không.** ForceAuthn là yêu cầu giao thức; hành vi thực tế phụ thuộc policy/khả năng IdP và phải kiểm chứng Response/AuthnContext/IdP audit tương ứng.

**Câu 7.** IdP ký Response thành công nhưng AuthnRequest của SP ban đầu gửi tới sai Destination. Có sửa bằng cách tắt kiểm Destination ở SP không?  
**Đáp án:** **Không.** Destination của AuthnRequest cần khớp SSO endpoint của IdP; Destination/Recipient của Response lại cần khớp ACS. Phải sửa đúng chiều, không bỏ xác minh.

## 17. Tài liệu chuẩn

1. [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): filter/resolver, AuthnRequest repository, signing credentials, binding và customization. **Chú ý tài liệu latest có thể là 7.x; đối chiếu phiên bản 6.x cho Boot 3.3.5.**
2. [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, signing credentials, issuer, ACS, OpenSAML và mối quan hệ SP/IdP.
3. [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): đọc IDPSSODescriptor và xuất SPSSODescriptor để IdP đăng ký.
4. [Spring Boot 3.3 – Spring Security, SAML Relying Party](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): YAML properties cho SP signing private-key-location, certificate-location và asserting party.
5. [Spring Security 6.x – OpenSaml4AuthenticationRequestResolver API](https://docs.spring.io/spring-security/site/docs/6.2.x/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html): cách customize AuthnRequest trong họ 6.x.
6. [OASIS SAML 2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): IDPSSODescriptor, SPSSODescriptor, SingleSignOnService, WantAuthnRequestsSigned và KeyDescriptor.
7. [OASIS SAML 2.0 Bindings Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-Redirect query signature/DEFLATE và HTTP-POST binding.
8. [Microsoft Learn – SAML request must be signed](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/error-code-aadsts76021-request-not-signed): ví dụ tình huống IdP từ chối request ký sai vị trí giữa Redirect và POST.

**Nguyên tắc kết thúc:** kiểm chứng AuthnRequest phát đi là **đối chiếu metadata đáng tin + hợp đồng IdP + đúng chữ ký/binding + thử nghiệm IdP thật**. **SP tự tạo được một AuthnRequest không có nghĩa IdP sẽ chấp nhận nó**. Giữ nhất quán Issuer (SP entityID), Destination (IdP SSO endpoint), ACS (SP callback), chính sách ký và request correlation để bảo toàn an toàn toàn bộ SAML login.
