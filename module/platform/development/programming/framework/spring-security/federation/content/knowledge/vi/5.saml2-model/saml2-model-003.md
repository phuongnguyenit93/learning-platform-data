# NameID, NameIDFormat và định danh liên kết trong SAML 2.0

> **Phạm vi:** Spring Security – federation / Mô hình SAML2. Bài học giải thích cách SAML 2.0 biểu diễn danh tính người dùng bằng `NameID`, các định dạng `NameIDFormat`, cách `NameIDPolicy` yêu cầu định danh và cách Service Provider (SP) ánh xạ danh tính từ Identity Provider (IdP) sang tài khoản nội bộ. Ví dụ Java độc lập dùng Java 17; phần Spring Security dùng mô hình Servlet, Spring Boot 3.5.x và Spring Security 6.5.x.

## 1. Mục tiêu và kiến thức nền

Sau bài này, người học có thể:

1. Chỉ ra `NameID` trong `Assertion/Subject` và phân biệt nó với `Issuer`, `Attribute`, `SessionIndex`, `InResponseTo`, `Audience` và ID tài khoản trong ứng dụng.
2. Đọc chính xác URI của `persistent`, `transient`, `emailAddress`, `unspecified` và các format khác; hiểu mức độ bền vững, tính riêng tư và phạm vi áp dụng.
3. Giải thích `NameQualifier`, `SPNameQualifier`, `SPProvidedID` cùng vai trò của IdP entity ID và SP entity ID.
4. Phân biệt `NameIDPolicy` do SP gửi trong `AuthnRequest` với `NameID` thực tế IdP trả về; hiểu `Format`, `SPNameQualifier`, `AllowCreate` và lỗi `InvalidNameIDPolicy`.
5. Thiết kế phép ánh xạ `(IdP, SP, Format, qualifier, NameID) → internal_user_id`, xử lý đa IdP, account linking, JIT provisioning, thay tên, migration và offboarding.
6. Dùng Spring Security để lấy principal đã xác thực, biết giới hạn của `Saml2AuthenticatedPrincipal#getName()`, và triển khai quyền nghiệp vụ độc lập.
7. Kiểm thử ít nhất các trường hợp NameID trùng ở hai IdP, transient thay đổi, email bị tái cấp, SP entity ID thay đổi, NameIDPolicy không được hỗ trợ và Assertion không hợp lệ.

**Kiến thức trước đó:** HTTP redirect/POST và session, Spring Security `Authentication` và `SecurityFilterChain`, quan hệ IdP–SP và SAML Web Browser SSO, XML ở mức đọc được, vai trò của chữ ký số. Đây là bài về **định danh liên kết**, không thay thế kiến thức kiểm chứng chữ ký XML và điều kiện Assertion.

## 2. `NameID` trong luồng SAML Web Browser SSO

Trong SAML 2.0, IdP xác thực một principal và phát hành `Assertion` cho SP. `<saml:Subject>` mô tả principal mà các tuyên bố áp dụng tới. `<saml:NameID>` là một cách mô tả chủ thể bằng chuỗi; ngoài ra đặc tả còn cho phép `BaseID` và `EncryptedID`.

~~~text
Người dùng           SP ứng dụng                         IdP
    | GET /private       |                                 |
    |------------------->|                                 |
    |                    | tạo AuthnRequest                 |
    |<-- Redirect -------| (có thể kèm NameIDPolicy)       |
    |------------------------- SAMLRequest -------------->|
    |                    |                 xác thực người dùng
    |<--------------------- SAMLResponse ------------------|
    | POST đến ACS       |                                 |
    |------------------->|                                 |
    |                    | XÁC MINH signature, Issuer,       |
    |                    | Audience, time, Subject,         |
    |                    | Recipient, InResponseTo, replay  |
    |                    |                                 |
    |                    | đọc NameID/Attributes đã tin     |
    |                    | tra external identity link       |
    |                    | tạo Authentication + session    |
    |<-- trang đã login -|                                 |
~~~

**Thứ tự quan trọng:** Không lấy NameID từ request `SAMLResponse` do trình duyệt gửi rồi tự tra người dùng trước khi kiểm chứng. SP phải xác minh Response/Assertion bằng metadata và chứng thư của IdP đã được phê duyệt, kiểm tra đúng bên nhận, thời hạn, trạng thái giao dịch và chống phát lại. SAML response mang một NameID có vẻ “đúng” vẫn là giả mạo nếu không có chuỗi tin cậy này.

Một trích đoạn **minh họa cấu trúc**, cố ý không có chữ ký và không phải Assertion hoàn chỉnh:

~~~xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <saml:Subject>
    <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="https://idp.example.org/saml"
      SPNameQualifier="https://portal.example.org/sp">
      q7Xw9T-opaque
    </saml:NameID>
    <saml:SubjectConfirmation
      Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
        InResponseTo="_request123"
        Recipient="https://portal.example.org/login/saml2/sso/corporate"
        NotOnOrAfter="2030-01-01T10:05:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
</saml:Assertion>
~~~

Trong ví dụ, `Issuer` xác định **IdP phát hành**; `NameID` nêu **principal**; `Format` cho biết cách hiểu giá trị; các qualifier nêu phạm vi định danh; `SubjectConfirmationData` là điều kiện chấp nhận bearer assertion tại SP chứ không thuộc NameID. Giá trị và thời gian trong XML là giả định, không phải dữ liệu đăng nhập hợp lệ có thể dùng trực tiếp.

## 3. Cấu trúc `NameIDType` và những thứ không được suy diễn

Một `NameID` dựa trên `NameIDType` của SAML 2.0 Core, bao gồm text và các thuộc tính tùy chọn:

| Thành phần | Ý nghĩa thực tế | Điều cần lưu ý |
| --- | --- | --- |
| Nội dung chuỗi | Giá trị mà IdP dùng nhận diện principal trong miền tên được định nghĩa | Không nhất thiết là email, username, UUID hay mã nhân viên |
| `Format` | URI chỉ semantics của tên, ví dụ persistent hay transient | Không bảo đảm uniqueness toàn cầu hoặc quyền truy cập |
| `NameQualifier` | Miền an ninh/hành chính liên quan đến tên | Giúp phân biệt hai kho danh tính, có quy tắc riêng theo format |
| `SPNameQualifier` | Miền SP hoặc nhóm SP liên kết mà tên áp dụng | Có ích với pairwise/persistent name identifier |
| `SPProvidedID` | Định danh thay thế do SP hoặc affiliation thiết lập | Không phải trường bắt buộc và không mặc nhiên là internal user ID |

Nếu `Format` vắng mặt và không có quy định khác, mặc định mang nghĩa `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified`. SAML không tự cam kết giá trị NameID là bất biến suốt đời tài khoản: phải xem **format, hợp đồng với IdP, quy tắc namespace và vòng đời cấp phát**.

Phân biệt các trường có vẻ giống nhau:

- `<saml:Issuer>`: entity ID của hệ thống phát hành assertion, không phải người dùng.
- `<saml:NameID>` trong `Subject`: principal mà Assertion nói tới.
- `<saml:Attribute Name="email">`: một thuộc tính được tuyên bố về principal; không tự thay thế NameID.
- `<saml:Attribute Name="groups">`: nhóm/role claim tùy hợp đồng; không tự động biến thành quyền nội bộ.
- `AuthnStatement/@SessionIndex`: tham chiếu phiên xác thực phía IdP, dùng trong một số kịch bản SAML Single Logout; không phải user ID lâu dài.
- `SubjectConfirmationData/@InResponseTo`: gắn kết Assertion với AuthnRequest đã khởi tạo, không phải external subject.
- `users.id`: khóa chính do ứng dụng quản lý, nên tồn tại độc lập với việc nhà cung cấp danh tính đổi NameID.

## 4. Danh mục `NameIDFormat` chính thức

**Format phải được nhận diện bằng URI đầy đủ.** Một số format của SAML 2.0 giữ URI bắt đầu bằng `SAML:1.1`. Điều đó hợp chuẩn, không phải tự động là thông điệp SAML 1.1.

| Format | URI chính thức | Công dụng và cảnh báo |
| --- | --- | --- |
| Unspecified | `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | Không có semantics chung. Có thể là email, username, ID tùy IdP; phải có hợp đồng riêng về độ ổn định và phạm vi |
| EmailAddress | `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` | Giá trị dạng địa chỉ email; có thể đổi, được tái cấp hoặc bị trùng theo tenant |
| X509SubjectName | `urn:oasis:names:tc:SAML:1.1:nameid-format:X509SubjectName` | Tên chủ thể theo cú pháp X.509, thường gặp ở hệ thống PKI |
| WindowsDomainQualifiedName | `urn:oasis:names:tc:SAML:1.1:nameid-format:WindowsDomainQualifiedName` | Dạng `DOMAIN\\username` trong môi trường Windows/AD; tên vẫn có thể đổi |
| Kerberos | `urn:oasis:names:tc:SAML:2.0:nameid-format:kerberos` | Principal theo cú pháp `name[/instance]@REALM` |
| Entity | `urn:oasis:names:tc:SAML:2.0:nameid-format:entity` | URI nhận diện một thực thể SAML (ví dụ `Issuer` của IdP/SP), ít dùng làm subject người dùng |
| Persistent | `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` | Định danh opaque và lâu dài, thường riêng cho cặp IdP–SP hoặc SP affiliation, thích hợp để liên kết account có kiểm soát |
| Transient | `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` | Định danh opaque, tạm thời; không nên dùng làm khóa hồ sơ lâu dài |

Với `persistent` và `transient`, SAML 2.0 Core quy định giá trị định danh không quá **256 ký tự**. Giá trị persistent được thiết kế mang tính ẩn danh tương đối (pseudonymous), không bộc lộ rõ tên thật hay username, khó suy ra từ danh tính thực và có phạm vi IdP/SP. Định danh transient cũng phải được xử lý như chuỗi mờ, không “giải nghĩa” từ cách trông giống một UUID.

**Trường hợp đặc biệt:** `urn:oasis:names:tc:SAML:2.0:nameid-format:encrypted` được dành cho `NameIDPolicy/@Format` nhằm yêu cầu định danh trả về ở phần tử `EncryptedID`. Nó không phải một format cleartext thông thường giống `persistent`/`transient`. SP phải có khả năng giải mã đúng bằng private key tương ứng khi IdP gửi `EncryptedID`.

### Cách chọn format theo nhu cầu

| Bài toán | Cách quyết định |
| --- | --- |
| Cần khôi phục đúng tài khoản qua nhiều năm | Ưu tiên persistent hoặc một thuộc tính định danh ổn định đã được IdP bảo đảm; luôn ánh xạ vào user ID nội bộ |
| Muốn hạn chế theo dõi một người giữa các ứng dụng khác nhau | Sử dụng pairwise persistent ID của từng SP; không công bố chung employee ID cho mọi SP |
| Chỉ cần đăng nhập vào phiên tạm, không có hồ sơ gắn với người dùng | Transient có thể phù hợp nếu luồng thực sự không cần nhận diện lần sau |
| IdP chỉ trả emailAddress | Cần chính sách xử lý đổi email, tái cấp, xác minh ownership và tenant, tránh tự liên kết sai |
| IdP chỉ trả unspecified | Thỏa thuận riêng về ý nghĩa, uniqueness, khả năng đổi/huỷ và mối quan hệ với SP |
| Định danh bị coi là nhạy cảm trên đường qua trình duyệt | Cân nhắc EncryptedID, kênh HTTPS, chính sách lưu/log và giải mã của SP |

## 5. Persistent NameID và định danh cặp IdP–SP

Một IdP có thể cấp **hai NameID khác nhau cho cùng một người** nếu họ truy cập hai SP khác nhau. Đó là tính năng bảo vệ riêng tư, không phải lỗi ngẫu nhiên.

~~~text
IdP A: internal employee=742
     |
     +--> portal.example.org   : persistent NameID=P-AX92
     |
     +--> finance.example.org  : persistent NameID=P-BK81

IdP B: internal employee=905
     |
     +--> portal.example.org   : persistent NameID=P-AX92
~~~

Định danh cuối ở IdP B cố ý có cùng text với IdP A: hai người không mặc nhiên là một, vì **IdP khác nhau**. Hai giá trị tại hai SP của cùng IdP cũng có thể khác nhau vì **SPNameQualifier/SP entity ID khác nhau**.

Một ví dụ cụ thể:

| IdP entity ID | SP entity ID | NameID value | Nhận định |
| --- | --- | --- | --- |
| `https://idp-a.example/saml` | `https://portal.example/sp` | `G92-opaque` | Danh tính #1 |
| `https://idp-a.example/saml` | `https://finance.example/sp` | `J18-opaque` | Có thể cùng người, nhưng cần cơ chế liên kết được phép |
| `https://idp-b.example/saml` | `https://portal.example/sp` | `G92-opaque` | Danh tính #2, không trùng danh tính #1 |

Đặc tả khuyến nghị persistent ID **không công khai mối liên hệ với định danh thật**, và dùng pseudonym riêng theo bên liên kết. Không nên để persistent NameID trong URL, log dùng chung cho nhiều đối tác, bảng analytics không được kiểm soát hoặc dữ liệu gửi chéo sang SP khác.

**Persistent không phải bảo đảm vĩnh viễn.** Những thay đổi như đổi SP entity ID, IdP tenant, khôi phục user, xoá rồi tạo lại account, chuyển IdP hoặc triển khai Name Identifier Management có thể làm NameID thay đổi. Do đó, SP nên có bảng link tới `internal_user_id` và quy trình migration có xác thực. Đừng dùng raw NameID làm khóa chính cho bảng đơn hàng, thanh toán hoặc audit.

### Qualifier với persistent ID

- `NameQualifier`: nếu có, thường phải nhận diện **IdP tạo identifier** theo quy tắc persistent; đôi khi có thể lược bỏ nếu suy được từ message.
- `SPNameQualifier`: nếu có, phải nhận diện **SP hoặc SP affiliation** mà định danh được tạo cho; đôi khi có thể lược bỏ khi message chỉ dành cho đúng SP.
- `SPProvidedID`: định danh thay thế được SP/affiliation thiết lập cho principal; chỉ xử lý khi đã có hợp đồng và quy tắc quản trị.

Qualifiers có thể vắng mặt một cách hợp lệ. SP phải xác định **ngữ cảnh đã xác minh** từ registration, issuer và recipient, không gán tùy tiện qualifier dựa trên email hay chuỗi đường dẫn nội bộ. Khi broker IdP phát lại NameID qua một tầng federation, NameQualifier cũng giúp giữ thông tin nơi identifier được tạo ban đầu theo quy tắc format.

## 6. Transient NameID và giới hạn sử dụng

Transient NameID mang tính **temporary, opaque**. IdP có thể trả các giá trị khác nhau giữa những lần login của cùng người:

~~~text
Lần đăng nhập 1: transient NameID=T-q7M2
Lần đăng nhập 2: transient NameID=T-p8Z9
~~~

Nếu ứng dụng lập một hàng tài khoản mới với mỗi giá trị transient, lần đăng nhập sau có thể thành một user khác hoàn toàn. Nếu ứng dụng tìm bằng email để “sửa”, nó có thể ghép nhầm người khi email thay đổi hoặc bị tái cấp.

Các lựa chọn kiến trúc:

1. Chỉ cần xác thực cho một phiên tạm: giữ ứng dụng không có hồ sơ người dùng bền vững hoặc phân quyền theo context tạm đã được chứng thực.
2. Cần hồ sơ dài hạn: yêu cầu persistent NameID hoặc thuộc tính ổn định khác được IdP bảo đảm bằng hợp đồng, ví dụ employee identifier có namespace/tenant rõ ràng.
3. Phải liên kết với tài khoản cũ: thực hiện flow xác minh sở hữu tài khoản riêng, approval hay provisioning đáng tin; không dựa vào transient hay email chưa được xác minh.
4. Đừng coi transient là `SessionIndex`. SessionIndex là giá trị của `AuthnStatement` phục vụ điều phối phiên (ví dụ SLO); tuổi thọ, phạm vi và ý nghĩa khác NameID.

## 7. `NameIDPolicy` trong `AuthnRequest`

Trong luồng **SP-initiated SSO**, SP có thể yêu cầu IdP phát hành tên theo chính sách bằng phần tử `<samlp:NameIDPolicy>`. Đây là **yêu cầu của SP**, không phải thuộc tính hiển nhiên của mọi assertion.

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request-123"
    Version="2.0"
    IssueInstant="2030-01-01T10:00:00Z"
    Destination="https://idp.example.org/sso"
    AssertionConsumerServiceURL="https://portal.example.org/login/saml2/sso/corp">
  <saml:Issuer>https://portal.example.org/sp</saml:Issuer>
  <samlp:NameIDPolicy
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      SPNameQualifier="https://portal.example.org/sp"
      AllowCreate="true"/>
</samlp:AuthnRequest>
~~~

XML trên minh họa cấu trúc; thiếu binding và chữ ký theo chính sách IdP, và dùng thời gian giả định, nên **không phải request có thể phát hành trực tiếp**. Ý nghĩa:

| Thuộc tính | Diễn giải |
| --- | --- |
| `Format` | Đề nghị loại định danh mà SP cần; IdP phải đáp ứng theo profile/chính sách hoặc báo lỗi nếu không hỗ trợ |
| `SPNameQualifier` | Đề nghị namespace SP/affiliation cho định danh nhận được |
| `AllowCreate="true"` | SP cho phép IdP thiết lập **một identifier mới** nếu chưa có; không đồng nghĩa IdP tự cấp account ứng dụng hay role |
| `AllowCreate="false"` | SP chỉ muốn identifier đã tồn tại; chuẩn định nghĩa mặc định là false khi thuộc tính vắng mặt |
| Bỏ Format/unspecified | IdP có thể chọn format phù hợp, bị ràng buộc bởi policy khác; SP phải kiểm tra loại trả về có dùng được hay không |
| `Format="...:encrypted"` | Yêu cầu đưa subject identifier vào `EncryptedID`; SP cần private key giải mã |

Nếu IdP không hiểu hoặc không chấp nhận policy, nó có thể báo lỗi `InvalidNameIDPolicy` trong `Response`. Đặc biệt, với `persistent` và `AllowCreate=false`, một người chưa từng được cấp pairwise ID cho SP có thể bị từ chối dù credentials xác thực đúng. Thay đổi `AllowCreate` là **quyết định policy/onboarding**, không phải cách bỏ qua xác thực.

**Phân biệt format yêu cầu và format trả về:** một request hỏi persistent không đủ chứng minh NameID trong Assertion là persistent. SP phải kiểm tra **Assertion đã xác minh** và áp hợp đồng IdP–SP. Ngược lại, nếu App không gửi NameIDPolicy, IdP vẫn có thể phát persistent theo cấu hình đối tác.

### NameIDPolicy và IdP-initiated SSO

Với **IdP-initiated SSO**, không có AuthnRequest SP được tạo cho cùng một giao dịch nên SP không thể đặt NameIDPolicy ở bước đó hoặc kiểm tra `InResponseTo` như SP-initiated. SP phải có chính sách chấp nhận IdP-initiated riêng, kiểm tra issuer, audience, recipient, chữ ký, thời gian, replay và format thực tế. Nếu cần bảo đảm state/format mạnh nhất, ưu tiên SP-initiated hoặc xây cơ chế có kiểm chứng tương đương được hai phía hỗ trợ.

### NameIDFormat trong metadata

`<md:NameIDFormat>` trong SAML metadata thông báo **các format một SP/IdP hỗ trợ**, khác với `NameIDPolicy` trong AuthnRequest và `NameID/@Format` trong Assertion.

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:NameIDFormat>
    urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
  </md:NameIDFormat>
  <md:NameIDFormat>
    urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress
  </md:NameIDFormat>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.org/sso"/>
</md:IDPSSODescriptor>
~~~

Đây chỉ là **trích đoạn metadata**, chưa có `EntityDescriptor`, signing key hoặc metadata signature. Metadata công bố format được hỗ trợ, không bảo đảm IdP sẽ cấp bất kỳ format nào cho mọi user/SP. Cần thống nhất với đối tác về cấu hình cụ thể.

## 8. Mô hình dữ liệu cho định danh liên kết

Một SP nên duy trì **hai lớp định danh**:

- **External identity**: ID từ IdP đã xác minh, với đúng namespace/format và SP scope.
- **Internal user**: user ID do ứng dụng quản lý, làm khóa chính cho dữ liệu nghiệp vụ, quyền và audit.

Mô hình thực tế:

~~~text
Validated SAML Assertion
       |
       +--> trusted IdP entity ID / registration
       +--> SP entity ID / affiliation
       +--> effective NameID Format
       +--> qualifiers theo contract
       +--> exact NameID text
       |
       v
ExternalIdentityKey ----> saml_identity_link ----> app_user.id
                                  |
                                  v
                       tenant + role policy + status
~~~

Một thiết kế bảng ban đầu:

~~~sql
CREATE TABLE app_user (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE saml_identity_link (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES app_user(id),
    provider_id VARCHAR(200) NOT NULL,
    sp_entity_id VARCHAR(512) NOT NULL,
    name_id_format VARCHAR(256) NOT NULL,
    name_qualifier VARCHAR(512),
    sp_name_qualifier VARCHAR(512),
    name_id_value VARCHAR(1024) NOT NULL,
    status VARCHAR(20) NOT NULL,
    verified_at TIMESTAMP NOT NULL
);
~~~

Đây là **lược đồ minh họa**: chưa có khóa unique, index, policy cho NULL, tenant, encryption, transaction và audit production. Khi triển khai thật cần khóa duy nhất theo **canonical external identity**. `provider_id` phải ánh xạ tới IdP/entity ID được tin trong registration; không lấy giá trị này từ form đầu vào hoặc claim chưa được xác minh.

Khóa logic cần tránh nhầm là:

~~~text
(
  trustedIdpEntityId,
  trustedSpEntityIdOrAffiliation,
  effectiveNameIdFormat,
  effectiveNameQualifier,
  effectiveSpNameQualifier,
  exactNameIdValue
)
~~~

Trong hệ thống có `registrationId` được quản trị tách riêng từng cặp IdP–SP, khóa có thể gói một số ngữ cảnh vào registration. Quan trọng là ứng dụng **không chỉ dùng raw NameID value** và có quy tắc nhất quán khi qualifiers được phép vắng mặt. Không tự động `trim()`, lowercase, case-fold hay Unicode normalize giá trị opaque persistent/transient nếu hợp đồng IdP không quy định, vì hai định danh khác nhau có thể bị nhập nhằng.

**Khi có nhiều IdP hoặc tenant:** cùng `NameID="abc"` có thể là người khác nhau. Cùng IdP nhưng khác SPNameQualifier cũng không tự động cùng một identity. Nếu broker phát assertion cho nhiều tenant, xem rõ IdP nào đã tạo NameID và bên nào đang ký/đảm bảo assertion; phải dùng ngữ cảnh tin cậy có đủ bằng chứng.

## 9. Vòng đời identity link và chống chiếm tài khoản

### 9.1. Lần đăng nhập đầu và các lần tiếp theo

**Lần đầu:** Spring xác minh SAML Response; ứng dụng tạo external identity key và tìm link. Nếu không thấy, quyết định JIT provisioning theo tenant policy hoặc chuyển sang luồng xác minh/approval. Cần tạo link và user bằng transaction có unique constraint chống hai request đồng thời tạo trùng. Không tự động tìm tài khoản theo email và gắn vào account đang tồn tại.

**Lần sau:** tìm link đang hiệu lực; đối chiếu account status và tenant; tạo session của ứng dụng rồi kiểm tra authority cho tài nguyên. Không tự tạo một account thứ hai nếu ID đã liên kết. Cập nhật attributes hiển thị theo hợp đồng, nhưng tránh thay đổi khóa external identity chỉ vì email hoặc tên người dùng thay đổi.

**Đổi NameID:** IdP có thể tạo định danh mới khi đổi tenant, chuyển nhà cung cấp, thay SP entity ID, ngưng dùng cặp khóa định danh cũ hoặc thực hiện Name Identifier Management. Phải có quy trình chuyển link được kiểm chứng, ghi audit, kế hoạch rollback và xử lý session tồn tại. “Persistent” không loại bỏ nhu cầu migration.

**Offboarding:** hủy hoặc vô hiệu hóa link khi người dùng rời tổ chức hoặc đối tác hết hợp đồng; hủy quyền/sessions theo chính sách. Xóa link không có nghĩa xóa ngay dữ liệu nghiệp vụ, cần chính sách lưu giữ riêng.

### 9.2. Tại sao tự động nối theo email nguy hiểm?

Giả sử app đã có `user_id=1001`, email `an@example.org` và link tin cậy từ IdP A. IdP B phát một SAML Assertion **được ký hợp lệ bởi chính B** chứa cùng email nhưng subject thuộc người khác. Nếu app làm:

~~~text
link theo NameID chưa thấy -> tìm user theo email
-> thấy an@example.org -> gắn B vào user_id=1001
~~~

thì B có thể đăng nhập vào account của A. Chữ ký IdP B chứng minh **B đã nói điều đó**, không chứng minh B có quyền gắn một identity mới vào tài khoản thuộc IdP A.

Phương án đúng là dùng liên kết đã có; nếu chưa có, phải xác minh quyền sở hữu tài khoản (đăng nhập lại tại account cũ, quản trị viên phê duyệt có audit, hoặc provisioning IdP/HR được xác thực), giới hạn theo tenant và ghi lại toàn bộ quyết định. Email có thể được dùng làm **gợi ý** trong giao diện nếu chính sách cho phép, không làm bằng chứng duy nhất.

### 9.3. Phân quyền khác xác thực

Một NameID hợp lệ chỉ trả lời phần **ai đang đăng nhập trong miền định danh này**. Nó không tự mang `ROLE_ADMIN`, quyền xem báo cáo tài chính hoặc quyền thao tác API. Nếu IdP trả `groups` hoặc `roles` dưới dạng SAML Attributes, ứng dụng vẫn phải ánh xạ chúng theo đối tác, tenant và quyền nghiệp vụ. Account đang bị khóa thì cần từ chối hoặc giới hạn truy cập dù Assertion hợp lệ.

## 10. Java 17 độc lập: tránh gộp hai NameID giống nhau

Chương trình sau chỉ mô phỏng **bước tạo khóa liên kết sau khi đã xác minh SAML**. Nó không đọc XML, không chứng thực chữ ký và không thay thế Spring Security. Mục tiêu là thấy rõ IDP A và IDP B có thể phát cùng một NameID text cho hai account khác nhau.

**Tệp `NameIdIdentityKeyDemo.java`:**

~~~java
import java.util.HashMap;
import java.util.Map;

public class NameIdIdentityKeyDemo {
    record ExternalIdentity(
            String issuerEntityId,
            String spEntityId,
            String format,
            String nameQualifier,
            String spNameQualifier,
            String value
    ) {
        ExternalIdentity {
            if (issuerEntityId == null || issuerEntityId.isBlank()
                    || spEntityId == null || spEntityId.isBlank()
                    || format == null || format.isBlank()
                    || value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing identity context or NameID");
            }
        }
    }

    public static void main(String[] args) {
        String persistent =
                "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";

        ExternalIdentity idpA = new ExternalIdentity(
                "https://idp-a.example/saml",
                "https://portal.example/sp",
                persistent,
                "https://idp-a.example/saml",
                "https://portal.example/sp",
                "same-name-123");

        ExternalIdentity idpB = new ExternalIdentity(
                "https://idp-b.example/saml",
                "https://portal.example/sp",
                persistent,
                "https://idp-b.example/saml",
                "https://portal.example/sp",
                "same-name-123");

        Map<ExternalIdentity, Long> links = new HashMap<>();
        links.put(idpA, 1001L);
        links.put(idpB, 2002L);

        System.out.println("IdP A -> user " + links.get(idpA));
        System.out.println("IdP B -> user " + links.get(idpB));
        System.out.println("Same external identity? " + idpA.equals(idpB));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac NameIdIdentityKeyDemo.java
java NameIdIdentityKeyDemo
~~~

**Stdout chính xác:**

~~~text
IdP A -> user 1001
IdP B -> user 2002
Same external identity? false
~~~

Java `record` tạo `equals()` và `hashCode()` dựa trên toàn bộ các thành phần; khác `issuerEntityId` khiến hai identity khác nhau ngay cả khi text NameID giống hệt. Các trường qualifier được phép `null` khi absent trong message, nhưng hệ thống thật phải có quy tắc canonicalization theo hợp đồng từng IdP trước khi tạo khóa.

**Giới hạn:** `HashMap` không lưu bền vững, không có unique index/transaction, không xử lý federation broker, không tự đánh giá qualifier hay format, không làm validation. Trong production, chỉ tạo đối tượng từ **assertion đã xác minh** và registration/metadata đã được phê duyệt.

## 11. Spring Security: principal SAML và ID ứng dụng

Trong Servlet-based Spring Security 6.5.x, `Saml2Authentication` có principal kiểu `Saml2AuthenticatedPrincipal`. `principal.getName()` thường lấy **NameID value từ assertion đầu tiên** đã xác thực; `principal.getRelyingPartyRegistrationId()` cho biết registration được dùng; `principal.getAttributes()` và `getFirstAttribute("...")` trả Attributes đã ánh xạ.

**Giới hạn quan trọng:** API principal mức cao **không hứa luôn cung cấp đầy đủ `NameID/@Format`, `NameQualifier`, `SPNameQualifier`** dưới các getter riêng. Nếu domain model cần full identity key, phải tích hợp tại bước xử lý Assertion đã được kiểm chứng, qua customization/API phù hợp với phiên bản Spring Security/OpenSAML; không parse raw `SAMLResponse` do client gửi trong controller rồi tự tin XML.

### 11.1. Ví dụ Spring Boot 3.5.x, Java 17

Ví dụ dưới đây biên dịch được khi Maven có thể tải dependencies và repository liên quan; để đăng nhập thực tế cần IdP metadata thật, registration SP đúng và user thử. Đây là **ứng dụng demo có một SAML partner**, chưa làm identity linking/authorization nghiệp vụ.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>saml-nameid</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <name>Shibboleth Releases</name>
            <url>https://build.shibboleth.net/maven/releases</url>
            <snapshots><enabled>false</enabled></snapshots>
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

**`src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
~~~

`metadata-uri` là URL minh họa. Thay bằng URL được chính IdP đã được phê duyệt cung cấp. IdP phải được cấu hình SP entity ID và ACS URL của ứng dụng (có thể lấy từ metadata SP khi bật `saml2Metadata()`). Nếu IdP yêu cầu signed AuthnRequest, thêm SP signing credentials và public certificate tại IdP; không tự bỏ kiểm chứng hoặc thay IdP metadata tùy ý.

**`src/main/java/demo/SamlNameIdApplication.java`:**

~~~java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlNameIdApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlNameIdApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/")
        String home() {
            return "Open /me to start SAML login";
        }

        @GetMapping("/me")
        Map<String, String> me(
                @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
            return Map.of(
                    "registrationId", principal.getRelyingPartyRegistrationId(),
                    "nameId", principal.getName());
        }
    }
}
~~~

Chạy `mvn spring-boot:run`; vào `http://localhost:8080/` sẽ thấy đúng chuỗi **Open /me to start SAML login**. Vào `/me` hoặc `/saml2/authenticate/corporate` để khởi tạo SSO. Sau khi IdP xác thực và trả assertion hợp lệ, `/me` trả JSON gồm `registrationId` và `nameId` do IdP cấp; không có output giá trị cố định để viết sẵn. Endpoint này chỉ dùng trong môi trường học/test: production không nên trả raw NameID ra bên ngoài nếu không có yêu cầu và quyền kiểm soát rõ ràng.

Spring thực hiện xác minh SAML ở tầng filter/provider; controller nhận principal **sau khi xác thực thành công**. Nhưng tên registration nội bộ `corporate` không phải chính `Issuer` trong SAML. Để ghi identity link, cần ánh xạ registration tới đúng IdP entity ID và SP entity ID, lấy format/qualifier đã xác minh theo custom integration phù hợp, rồi tra cứu `internal_user_id` và phân quyền.

### 11.2. Nếu IdP yêu cầu NameIDPolicy persistent

Spring có `Saml2AuthenticationRequestResolver` và OpenSAML AuthnRequest customizer; tên lớp và API cụ thể phụ thuộc phiên bản Spring Security/OpenSAML (dòng 6.x và 7.x có khác biệt). Kết quả giao thức mong muốn ở phần request là:

~~~xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    AllowCreate="true"/>
~~~

Đoạn này **chỉ là phần XML cần sinh trong AuthnRequest**, không phải Java đầy đủ. Để triển khai, tra tài liệu AuthnRequest customization của đúng version, bổ sung policy qua OpenSAML object và kiểm tra SAMLRequest thực trong môi trường test. Không khẳng định Spring mặc định luôn gửi persistent policy chỉ vì `principal.getName()` trả một chuỗi có vẻ ổn định.

### 11.3. Liên kết tài khoản và cấp quyền trong Spring

Dòng xử lý đúng thường là:

~~~text
SAMLResponse
  -> SecurityFilterChain / OpenSAML validation
  -> Saml2Authentication + trusted RelyingPartyRegistration
  -> external identity (issuer, SP, NameID format, qualifiers, value)
  -> IdentityLinkRepository.findActive(...)
  -> AppUser (status + tenant)
  -> GrantedAuthority/authorization theo nghiệp vụ
~~~

Một `Attribute` chứa nhóm không tự tạo `ROLE_ADMIN`; phải có mapping group/tenant theo chính sách. Nếu external identity chưa có link, cần onboarding/JIT đã được phê duyệt hoặc từ chối/đòi xác minh thêm. Không dùng đoạn `principal.getName()` đơn lẻ làm khóa user trong kho dữ liệu.

## 12. Vận hành identity linking và đổi định danh

SAML Core mô tả **Name Identifier Management Protocol** (`ManageNameIDRequest` / `ManageNameIDResponse`) cho thay thế hoặc ngừng sử dụng name identifier khi các bên hỗ trợ. Giao thức tồn tại không có nghĩa IdP/ứng dụng Spring tự triển khai toàn bộ vòng đời; kiểm tra năng lực của đối tác và xây quy trình riêng khi cần.

| Sự kiện | Cách xử lý |
| --- | --- |
| User đổi email nhưng persistent NameID không đổi | Chỉ cập nhật thuộc tính hiển thị; giữ nguyên internal user và link |
| IdP đổi persistent NameID sau migration | Xác minh quan hệ cũ–mới theo kênh tin cậy, cập nhật link có audit |
| SP đổi entity ID hoặc affiliation | Có thể khiến IdP phát pairwise NameID khác; cần phối hợp và chạy migration trước go-live |
| Tenant chuyển IdP | Không tự xem user cũ và mới cùng người theo email; yêu cầu bằng chứng linking |
| Account bị khóa/offboarding | Vô hiệu hóa link/quyền/phiên theo policy dù IdP vẫn cấp Assertion hợp lệ |
| IdP tiếp tục phát transient NameID cho app cần hồ sơ | Thương lượng ID ổn định hoặc thiết kế session-only; không lưu transient làm khóa chính |
| Metadata báo format mới | Kiểm thử semantics, qualifier và nguồn tin cậy trước khi đổi app mapping |

**Privacy và retention:** Pairwise NameID có thể là dữ liệu nhận diện được người dùng trong phạm vi SP. Giới hạn quyền đọc log, che hoặc băm có khóa khi cần thống kê, không gửi NameID sang bên thứ ba nếu không có mục đích và quyền hợp lệ. Không đưa toàn bộ `SAMLResponse` hay assertion có attributes vào log công khai để chẩn đoán.

## 13. Ma trận QA / kiểm thử bảo mật

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| IdP A và B phát cùng text persistent NameID | Hai identity khác nhau do issuer/context khác |
| Cùng IdP phát NameID cho hai SP khác nhau | Không tự gộp nếu chưa có phương thức liên kết hợp lệ |
| Dùng transient NameID ở lần login kế tiếp | Không mặc nhiên tìm được account cũ từ text transient |
| Email thay đổi trong khi persistent không đổi | Internal user vẫn được tìm qua link bền vững |
| Email trùng nhau giữa tenant A/B | Không tự merge hoặc cấp quyền chéo tenant |
| IdP trả unspecified trong khi SP cần persistent | Xử lý mâu thuẫn theo policy, không tự đổi nhãn format |
| `AllowCreate=false` và chưa có ID phù hợp | Có thể nhận lỗi policy; không tự tạo account sai quy trình |
| `AllowCreate=true` và IdP hỗ trợ persistent | IdP có thể tạo ID mới; SP vẫn thực hiện toàn bộ SAML validation |
| Assertion có NameID quen thuộc nhưng chữ ký sai | Từ chối trước khi truy vấn/ghi identity link |
| Assertion sai `Issuer` / `AudienceRestriction` | Từ chối, không lẫn giữa các IdP/SP |
| Sai `Recipient`, `Destination`, `InResponseTo` hoặc token hết hạn | Từ chối, không lập phiên |
| Dùng lại Response/Assertion hợp lệ đã xử lý | Từ chối theo cơ chế chống replay |
| NameID dạng `EncryptedID` | SP giải mã bằng credential phù hợp rồi kiểm chứng/ánh xạ đúng |
| Link đã có nhưng internal user `DISABLED` | Không cấp quyền ứng dụng |
| Login thành công nhưng không có quyền quản trị | Endpoint admin trả 403 |
| Thay SP entity ID, IdP phát NameID khác | Migration có kiểm soát, không tạo hàng loạt account mới |
| Đăng xuất một phiên SAML | Xử lý `SessionIndex`/SLO theo giao thức, không coi là thay đổi identity |

Để kiểm thử, dùng IdP/tenant thử nghiệm và tài khoản giả. Khi xem HTTP trace hoặc SAML tracer, che NameID, email, attributes, assertion, session cookie và chứng cứ xác thực trước khi lưu/chia sẻ. Dùng validator SAML của thư viện đã chọn; không tự xác minh XML signature bằng regex hoặc so sánh text.

### Phân tích lỗi thường gặp

- **NameID thay sau mỗi login:** IdP đang phát transient, hoặc dùng identifier thuộc session. Kiểm tra `Format` thực đã xác minh, sửa hợp đồng IdP và mapping.
- **Login được nhưng account “mất”:** IdP đổi persistent NameID, SP entity ID, `NameQualifier` hoặc tenant. Đối chiếu cấu hình đối tác và lịch migration, không tự tìm theo email rồi merge.
- **`InvalidNameIDPolicy`:** `Format` không được hỗ trợ, `SPNameQualifier` sai, hoặc `AllowCreate=false` khi chưa có identifier. Kiểm tra request thực và policy tại IdP.
- **Hai người bị gộp:** app dùng raw NameID, username hoặc email làm unique key toàn cục. Xây canonical identity key có IdP/SP scope; rà soát link đã bị nhập nhằng.
- **Tài khoản người khác đăng nhập được:** auto-link theo email hoặc attribute từ IdP chưa đủ thẩm quyền. Khóa quy trình linking, audit và yêu cầu xác minh account ownership.
- **Có NameID nhưng bị 403:** xác thực thành công; lỗi ở quyền/tenant/role mapping nội bộ, không phải lỗi NameIDFormat.
- **`EncryptedID` không đọc được:** SP thiếu hoặc sai decryption private key, IdP mã hóa cho SP cert khác. Kiểm tra registration và credential, không bỏ qua mã hóa.
- **SAMLResponse có định danh nhưng bị từ chối:** có thể sai chữ ký, issuer, audience, thời hạn, recipient, correlation hoặc replay. Không tắt validator để “khắc phục”.

## 14. Bài tập và tiêu chí đạt

**Bài 1 – phân tích XML.** Từ một Assertion có `Issuer=https://idp-a`, `NameID Format=persistent`, `NameQualifier=https://idp-a`, `SPNameQualifier=https://sp-one` và text `X123`, xác định từng vai trò; giải thích vì sao IdP B cũng phát `X123` thì chưa chắc cùng người.

**Bài 2 – chọn format.** Hệ thống nhân sự cần lưu hồ sơ nhiều năm. So sánh emailAddress, transient và persistent; chọn phương án kèm cách xử lý đổi email và chuyển IdP.

**Bài 3 – NameIDPolicy.** IdP hỗ trợ persistent nhưng người mới chưa được cấp pairwise ID. SP gửi `AllowCreate=false`. Dự đoán lỗi và nêu quy trình cấp mới an toàn mà không cấp quyền app tự động.

**Bài 4 – code Java.** Biên dịch `NameIdIdentityKeyDemo.java` và xác nhận ba dòng stdout. Thay issuer của idpB thành idpA nhưng thay SP entity ID; dự đoán và giải thích kết quả `equals()`.

**Bài 5 – Spring.** Cấu hình IdP thử nghiệm vào project Spring ở mục 11, đăng nhập, xem `registrationId` và tên principal. Dùng công cụ kiểm tra Assertion **đã xác minh** để xác nhận `NameID/@Format` thực tế, không suy ra từ `getName()`.

**Bài 6 – an toàn dữ liệu.** Tạo test cho hai IdP có cùng email, một user bị offboard, một Assertion sai audience và một persistent NameID đổi sau migration. Chứng minh ứng dụng không tự nhập nhằng user và không cấp role trái phép.

**Đạt bài** khi giải thích được chính xác NameID/Format/qualifiers, khác biệt persistent–transient, ý nghĩa NameIDPolicy và AllowCreate, thiết kế khóa liên kết theo IdP–SP, tích hợp Spring sau bước xác thực và ít nhất năm trường hợp từ chối hoặc migration.

## 15. Tài liệu gốc để đối chiếu

- OASIS SAML 2.0 Core, ``2.2, 3.4.1.1, 3.6, 8.3: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authentication Responses / Saml2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Authentication Requests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SAML Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.5 – Spring Security / SAML2: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
