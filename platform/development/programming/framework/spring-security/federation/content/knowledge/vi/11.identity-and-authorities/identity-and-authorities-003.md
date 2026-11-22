# Định danh bền vững, định danh tạm thời và tác động đến liên kết tài khoản

> **Module:** Spring Security – federation · **Chủ đề cha:** Danh tính và quyền. Bài học phân tích SAML 2.0 `NameID` ở định dạng **persistent** và **transient**, vì sao lựa chọn định danh tác động trực tiếp đến khả năng nhận diện người dùng qua nhiều lần SSO, và cách xây dựng **account linking** an toàn trong Service Provider (SP).

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **xác thực thành công ở Identity Provider (IdP)**, **định danh được IdP khẳng định**, **liên kết với local account** và **quyền truy cập do ứng dụng quyết định**.
2. Giải thích ngữ nghĩa SAML 2.0 của `persistent NameID` và `transient NameID`: độ ổn định, phạm vi IdP–SP, quyền riêng tư và vòng đời.
3. So sánh các định dạng liên quan `emailAddress` và `unspecified` mà không đánh đồng “trông ổn định” với “được cam kết bền vững”.
4. Xây một khóa liên kết ngoài có phạm vi, tránh ghép sai khi hai IdP phát cùng chuỗi NameID, người dùng đổi email hoặc SP đổi registration ID.
5. Thiết kế workflow cho **tài khoản chưa liên kết**, **phê duyệt lần đầu**, **đổi NameID**, **thu hồi quyền** và **migration giữa IdP**.
6. Kiểm tra quyền trên **đúng tài nguyên và tenant**, không cho định danh hợp lệ tự biến thành quyền quản trị.
7. Chạy một ví dụ **Java 17 không phụ thuộc thư viện ngoài** chứng minh persistent có thể map ổn định, transient không được map bền vững, và scope/permission ngăn truy cập chéo.
8. Hiểu vị trí của `Saml2AuthenticatedPrincipal` trong Spring Security 6.x và giới hạn của `getName()` khi cần kiểm tra NameID Format/qualifiers.

## 2. Đặt đúng bốn khái niệm trước khi thiết kế

Giả sử IdP đối tác đã xác thực nhân viên An, gửi một SAML Assertion hợp lệ tới Orders Portal. Có bốn câu hỏi khác nhau:

| Câu hỏi | Bên chịu trách nhiệm chính | Dữ liệu/điều kiện thường dùng |
| --- | --- | --- |
| **Ai đã xác thực người dùng?** | IdP và lớp xác minh SAML ở SP. | IdP `Issuer`, chữ ký, response/assertion, binding, thời hạn, audience, recipient, `InResponseTo`. |
| **Subject được IdP biểu diễn bằng ID nào?** | IdP phát `Subject/NameID`; SP đọc đúng định dạng và phạm vi. | `NameID.Value`, `Format`, `NameQualifier`, `SPNameQualifier`. |
| **Định danh ngoài đó gắn với local account nào?** | Ứng dụng SP và quy trình quản trị liên kết. | Bản ghi `external_identity → local_user_id` đã phê duyệt; trạng thái active/revoked. |
| **Local user được làm gì với tài nguyên này?** | Authorization layer của ứng dụng SP. | Local permission, tenant, resource ownership, trạng thái account và policy theo request. |

**Xác thực SAML hợp lệ không đồng nghĩa có liên kết tài khoản**, và **liên kết tài khoản hợp lệ không đồng nghĩa có mọi permission**.

Chẳng hạn IdP xác thực nhân viên của Partner A, nhưng tài khoản nội bộ chưa được cấp quyền xem đơn hàng. Ứng dụng có thể cho người dùng vào màn hình “đang chờ phê duyệt”, đồng thời từ chối API xem đơn hàng. Một đối tác không có quyền chỉ vì tự tuyên bố thuộc nhóm tên `admin`.

## 3. SAML2 NameID nằm ở đâu?

Trong Web Browser SSO, SP thường gửi `AuthnRequest` và IdP trả `Response` chứa `Assertion`. Định danh người dùng thường nằm ở:

~~~text
<samlp:Response>                SAML protocol
  <saml:Assertion>              lời khẳng định của IdP
    <saml:Issuer>...</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="...">VALUE</saml:NameID>
      <saml:SubjectConfirmation>...</saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

`NameID` là một **định danh chủ thể theo ngữ nghĩa do IdP khẳng định**. Nó **không tự là email, local user ID, password, session cookie hoặc role của ứng dụng**. Cùng chuỗi hiển thị có thể chỉ những người khác nhau nếu issuer/namespace khác nhau.

Ví dụ hai NameID:

~~~xml
<!-- Persistent: mô phỏng một subject có thể dùng lặp lại theo hợp đồng -->
<saml:NameID
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    NameQualifier="https://idp.partner-a.example/saml"
    SPNameQualifier="https://orders.example/saml2/sp/partner-a">
    p-7b91e
</saml:NameID>
~~~

~~~xml
<!-- Transient: mô phỏng một subject tạm thời của một lượt SSO -->
<saml:NameID
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:transient">
    tmp-6e41
</saml:NameID>
~~~

Đây chỉ là **mảnh XML minh họa, không chứa chữ ký**; không được dùng riêng chúng để chứng minh đăng nhập. Chỉ đọc NameID từ **Assertion mà provider SAML đã thực sự xác minh**, sau khi các điều kiện protocol/trust qua kiểm tra.

### 3.1. Những thành phần của khóa định danh

- **Issuer / IdP entity ID:** ai khẳng định định danh? IdP A có thể phát cùng value với IdP B.
- **NameID.Format:** ý nghĩa của value; chuỗi giống nhau ở `persistent` và `transient` không tương đương.
- **NameID.Value:** dữ liệu nhận diện trong phạm vi quy định; đối với persistent/transient thường nên coi là một opaque string, không giải mã ý nghĩa chủ quan.
- **NameQualifier:** namespace bên tạo/đặt tên định danh nếu có; thường liên quan IdP.
- **SPNameQualifier:** định danh có thể bị giới hạn cho SP hoặc SP affiliation nào.
- **SP entity ID / registration context:** cặp quan hệ tin cậy mà assertion dành cho. Registration ID của Spring hữu ích để chọn cấu hình nhưng **không nên là thành phần khóa bền vững duy nhất**, vì ứng dụng có thể đổi tên registration mà vẫn giữ cùng SP entity ID.
- **Tenant:** scope nghiệp vụ đã được phê duyệt ở SP; không tự lấy từ query parameter người dùng gửi.

Với qualifiers vắng mặt, phải có **quy tắc chuẩn hóa rõ trong hợp đồng**. Không tự ý coi vắng mặt tương đương một giá trị nào đó nếu điều này có thể nhập nhằng hai định danh.

## 4. Persistent NameID: bền vững nhưng không phải ID toàn cầu

URI chuẩn:

~~~text
urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
~~~

Theo SAML2, định dạng persistent dùng identifier có ý nghĩa **bền vững và thường mang tính giả danh (pseudonymous)** trong quan hệ liên kết, giúp SP nhận ra cùng một principal qua các lần SSO **nếu liên kết được duy trì**. Identifier này thường được tạo cho **một cặp IdP–SP hoặc SP affiliation**, không mặc nhiên được sử dụng chung ở mọi website.

### 4.1. Vì sao bền vững có ích cho account linking?

Một nhân viên Partner A có local account `user_104`, permission `ORDER_READ` và lịch sử thao tác ở Orders Portal. IdP phát persistent NameID `p-7b91e` trong lần SSO đầu; SP lưu một liên kết đã được phê duyệt:

~~~text
(issuer=A, sp=Orders, format=persistent, nameId=p-7b91e)
    → local_user_id=user_104
~~~

Ở lần đăng nhập sau, nếu IdP vẫn phát cùng định danh theo hợp đồng, SP có thể tìm được `user_104` mà không cần dựa vào email, họ tên hay nhóm của IdP. Khi người dùng đổi email hoặc đổi tên, identity link **không nhất thiết đổi**.

### 4.2. Persistent có thể là pairwise

~~~text
Cùng người dùng trong IdP A:
  SP Orders  → persistent value "p-orders-7b91e"
  SP Payroll → persistent value "p-pay-0fa22"

Một người ở IdP B:
  SP Orders  → persistent value "p-orders-7b91e"
~~~

Dù cùng người ở IdP A, hai SP có thể nhận **hai pseudonym khác nhau**; dù chuỗi giống nhau giữa IdP A và B, đó có thể là **hai người khác nhau**. Thiết kế này có tác dụng hạn chế liên kết dữ liệu ngoài ý muốn giữa các dịch vụ.

**Persistent không đồng nghĩa “ID vĩnh viễn tuyệt đối”.** Khi IdP xóa liên kết, tenant được tách, SP entity ID đổi, IdP migration hoặc chính sách định danh thay đổi, value có thể đổi/hết hiệu lực. Vì vậy cần một quy trình xử lý thay đổi có chứng cứ, chứ không có giả định code rằng value không bao giờ thay.

### 4.3. Không biến persistent pseudonym thành PII phổ biến

Một opaque identifier thường tốt hơn email/username nếu mục tiêu chỉ là khóa liên kết, vì nó hạn chế việc lộ danh tính đời thực. Nhưng một pseudonym bền vững vẫn là dữ liệu có thể dùng theo dõi trong phạm vi SP, do đó:

- Không ghi raw NameID vào log công khai, URL query, telemetry không kiểm soát hoặc công cụ hỗ trợ bên ngoài.
- Không gửi một persistent identifier đã dành riêng cho SP A sang SP B khi không có thỏa thuận liên kết/affiliation.
- Hạn chế số người truy cập bảng `external_identity` và audit mọi thay đổi link.
- Tránh nhét email, số nhân viên hoặc thông tin cá nhân trực tiếp vào format `persistent` nếu thỏa thuận yêu cầu pseudonymous opaque value.

## 5. Transient NameID: định danh tạm, không dùng làm khóa account lâu dài

URI chuẩn:

~~~text
urn:oasis:names:tc:SAML:2.0:nameid-format:transient
~~~

SAML 2.0 mô tả transient identifier là giá trị **opaque và tạm thời**; nó được thiết kế cho trường hợp không cần thiết lập một liên kết danh tính dài hạn giữa IdP và SP. Qua các phiên/lượt SSO, cùng một người có thể nhận các giá trị khác nhau. Không xây `external_identity` durable chỉ bằng transient value.

~~~text
Ngày 1: IdP A xác thực An → transient NameID = T-6e41
Ngày 2: IdP A xác thực An → transient NameID = T-942c

T-6e41 != T-942c
Không đủ bằng chứng để SP suy ra đây là cùng local user.
~~~

**Không đồng nhất transient NameID với session ID của SP**: IdP có thể phát một identifier tạm theo SSO; sau khi xác thực, SP tạo session cookie riêng, có timeout và quy tắc logout riêng. Một transient identifier không phải token bearer được phép dùng để gọi API ngoài ý muốn.

### 5.1. Trường hợp transient phù hợp

- Ứng dụng chỉ cần biết phiên đã được một IdP tin cậy xác thực, không cần duy trì danh tính cá nhân qua các lần đăng nhập.
- Tài nguyên dùng **policy theo nhóm/thuộc tính hợp đồng** và ngữ cảnh hiện tại, không cần persistent local user hay hồ sơ riêng (vẫn phải giới hạn tenant và quyền).
- Dịch vụ chỉ cần phiên ngắn; tránh ghi identifier tạm như primary key user trong database.
- Mô hình đề cao quyền riêng tư, không muốn SP tự liên kết hoạt động của cùng một người qua nhiều lần SSO.

Transient **không tự bảo đảm tính ẩn danh tuyệt đối**: AttributeStatement có thể vẫn chứa email/employee ID; địa chỉ IP, cookie SP hoặc telemetry cũng có thể cho phép nhận diện. Quyền riêng tư là tính chất của **toàn bộ dữ liệu và vận hành**, không chỉ URI NameID.

### 5.2. Khi transient không phù hợp

- Portal có đơn hàng, lịch sử giao dịch, hạn mức duyệt, audit quy trách nhiệm từng nhân viên.
- Nghiệp vụ cần nhớ người dùng qua nhiều ngày hoặc định danh user khi thu hồi tài khoản.
- Phải liên kết vào bảng local account đang có quyền/công việc dở dang.
- Muốn cấp `APP_ADMIN`, `APP_APPROVE_PAYMENT` hoặc quyền nhạy cảm dựa vào lịch sử local account.

Nếu IdP chỉ cấp transient nhưng ứng dụng cần local account bền vững, có hai hướng được quản trị:

1. Đàm phán dùng **persistent NameID** hoặc một identifier khác đã được chứng minh ổn định, duy nhất trong phạm vi.
2. Sử dụng một **Attribute ổn định đã được IdP bảo đảm và xác minh** cùng issuer/namespace để account linking; không tự chọn email chỉ vì có sẵn, và không gắn quyền vào transient NameID.

Không có cơ chế thứ ba an toàn là “ghép theo tên hiển thị gần giống nhất”.

## 6. Persistent, transient, emailAddress và unspecified: đối chiếu đúng

| Format | URI | Lời hứa có thể dựa vào | Rủi ro nếu dùng làm account key |
| --- | --- | --- | --- |
| **persistent** | `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` | Định danh bền vững trong scope được định nghĩa. | Quên issuer/SP scope, không xử lý migration/termination. |
| **transient** | `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` | Opaque, tạm thời, dùng trong ngữ cảnh ngắn hạn. | Tạo user mới mỗi lần SSO hoặc nhầm user do suy diễn. |
| **emailAddress** | `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` | Dạng email, **không** được chuẩn này hứa là immutable ID. | Email đổi/reuse, ghép nhầm tài khoản. |
| **unspecified** | `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | Ngữ nghĩa được xác định ngoài URI. | Giả định value là object ID bền vững khi thực tế là username. |

Lưu ý hai URI `emailAddress` và `unspecified` dùng namespace **SAML:1.1** ngay cả trong SAML2; không tự sửa thành `SAML:2.0`.

### 6.1. Email đã được xác minh có đủ không?

Không, ít nhất là **chưa đủ để tự động liên kết một tài khoản có quyền nhạy cảm**. Địa chỉ `alex@partner.example` có thể bị đổi hoặc tái cấp cho nhân viên khác. Nếu SP sử dụng email làm khóa, người mới có email tái sử dụng có thể bị map vào local account của người trước.

Một email được IdP khẳng định trong Assertion đã ký chứng minh **IdP đã đưa ra khẳng định ấy**; nó không tự biến email thành identifier bất biến và không cho phép SP bỏ quy trình phê duyệt liên kết.

### 6.2. Unspecified có thể ổn định, nhưng phải có hợp đồng

Một đối tác dùng `unspecified` với value `object-8f42` có thể đang phát directory immutable object ID. Đối tác khác dùng `unspecified` với value là username tái sử dụng. SP không thể phân biệt nếu chỉ đọc `Format`; phải biết **nguồn, lifecycle và uniqueness scope** của value, được chứng minh bằng test/văn bản.

### 6.3. So sánh với OIDC `sub`, không đánh đồng

OIDC thường dùng cặp `(iss, sub)` để nhận dạng subject; một IdP có thể phát **pairwise subject** theo client/sector. Đây là mô hình tương tự về **scope** nhưng không phải cùng trường và không thể đổi tên `SAML NameID` thành `OIDC sub` mà không xác định giao thức/chính sách. Khi một hệ thống hỗ trợ cả SAML và OIDC, không ghép tài khoản xuyên protocol bằng trùng chuỗi identifier.

## 7. Luồng liên kết tài khoản an toàn theo từng bước

### 7.1. Kiến trúc

~~~text
Browser → IdP tin cậy → Signed SAML Response
                          |
                          v
                 SP verify protocol
         signature, issuer, audience, ACS,
        InResponseTo, expiry, subject, replay
                          |
                          v
              Đọc verified identity
           format + value + qualifiers
                          |
             Có ID bền vững hợp đồng?
               /                   \
             Có                     Không
              |                       |
   Lookup external identity      Không auto-link
              |                  theo transient
        Đã có link?                   |
          /    \                  Guest/PENDING/
        Có      Chưa             reject theo policy
        |         |
  Check ACTIVE  Provisioning/
  tenant        approval
        |         |
        v         v
    Local account hợp lệ?
              |
              v
    Tải local permissions + tenant
              |
              v
    Authorization theo action/resource
~~~

Bước **verify SAML** phải diễn ra trước mọi quyết định tin identifier. Không tự decode Base64 `SAMLResponse` trong Controller rồi dùng một XPath riêng; có thể tiêu thụ phần tử khác với nội dung đã được chữ ký xác minh (**XML Signature Wrapping**).

### 7.2. Đề xuất các trạng thái liên kết

| Trạng thái | Ý nghĩa | Quyền thường được phép |
| --- | --- | --- |
| `UNLINKED` | Subject hợp lệ nhưng chưa có bản ghi external identity. | Không có quyền nghiệp vụ; có thể vào màn hình hướng dẫn/provisioning. |
| `PENDING` | Đã yêu cầu link hoặc provision, chưa được chấp nhận. | Chỉ các bước onboarding rất hẹp. |
| `ACTIVE` | External identity gắn với một local user theo chính sách đã phê duyệt. | Quyền do local account/tenant và resource policy quyết định. |
| `SUSPENDED` | Tạm ngừng do rủi ro, user nghỉ việc hoặc thiếu dữ liệu. | Từ chối hành động nghiệp vụ. |
| `REVOKED` | Link không còn đáng tin hoặc đã chấm dứt. | Không dùng lại link; cần approval mới nếu lập liên kết khác. |

**Lưu ý:** “Được IdP xác thực” là sự kiện authentication, không phải trạng thái `ACTIVE` của local account. Một user đã bị disable trong SP vẫn có thể có tài khoản IdP hoạt động và nhận assertion hợp lệ.

### 7.3. First login / Just-in-Time provisioning

Khi gặp subject chưa từng thấy:

1. Kiểm tra Issuer/Signature/Audience/Recipient/Conditions/SubjectConfirmation/Correlation hợp lệ.
2. Phân loại identifier: persistent phù hợp hợp đồng hay transient/email/unspecified cần policy riêng?
3. Tra một external key **đúng namespace**, không tìm đại bằng email.
4. Nếu không có link, tạo yêu cầu `PENDING` hoặc từ chối. Nếu hệ thống hỗ trợ tự động tạo local account, quyền mặc định phải tối thiểu, với tenant được chứng minh.
5. Nếu người dùng đề nghị **gắn vào tài khoản local đã có**, yêu cầu bằng chứng kiểm soát tài khoản local và external identity, áp MFA/approval khi cần; không “claim account” chỉ bằng email trùng.
6. Viết liên kết trong transaction có unique constraint, chống race giữa hai lần callback đồng thời.
7. Cấp permissions **tại SP** từ nguồn quản trị có kiểm soát; không dùng trực tiếp external group `admin` làm `ROLE_ADMIN`.
8. Ghi audit có kiểm soát: ai phê duyệt, lúc nào, issuer/SP scope nào và lý do.

### 7.4. Account linking không phải account creation

- **Linking:** ánh xạ một external identity đã được IdP khẳng định tới **local account đã tồn tại**.
- **Provisioning:** tạo local account mới dựa theo chính sách, có thể đồng bộ từ SCIM/IdP directory hoặc JIT.
- **Authentication:** xác nhận một subject tại thời điểm đăng nhập.
- **Authorization:** cho phép hoặc từ chối một hành động lên tài nguyên.

Một định danh persistent giúp linking ổn định hơn, nhưng **không tự tạo local account** hoặc gán quyền. Một định danh transient vẫn có thể dùng để đăng nhập vào **một phiên không gắn người lâu dài**, nếu chính sách SP cho phép.

## 8. Khóa liên kết: cần scope gì để tránh nhập nhằng?

### 8.1. Khóa logic

Một phương án điển hình trong SAML2:

~~~text
ExternalIdentityKey =
    (idp_entity_id,
     stable_sp_scope,
     name_id_format,
     name_qualifier,
     sp_name_qualifier,
     name_id_value)
~~~

Trong từng deployment, một số qualifier có thể không được IdP gửi. Khi ấy hợp đồng cần xác định cách biểu diễn **vắng mặt** và điều kiện chấp nhận, nhưng **không** tự xóa tất cả scope để còn mỗi `name_id_value`.

- `idp_entity_id` lấy từ trust configuration và issuer đã xác minh.
- `stable_sp_scope` thường là **SP entity ID**, không nên chỉ là registration ID có thể đổi tên trong Spring.
- `name_id_format` dùng URI chính xác, không tên viết tắt tùy ý.
- `name_qualifier` / `sp_name_qualifier` bảo toàn ranh giới namespace khi có.
- `name_id_value` là chuỗi opaque, không tùy tiện lowercase, trim hoặc decode theo suy đoán.

**Không dùng `registrationId` đơn độc để chứng minh identity:** đó là khóa nội bộ cấu hình một cặp RP–IdP. Nếu đổi `partner-a` thành `supplier-a` nhưng không đổi issuer/SP entity ID/subject, có thể vẫn là cùng external identity. Ngược lại, tái sử dụng cùng registration ID cho IdP khác phải được xử lý như **thay đổi quan hệ tin cậy**, không tự ghép user.

### 8.2. Mô hình dữ liệu khuyến nghị

~~~sql
-- Ví dụ kiến trúc PostgreSQL. Không phải migration tự chạy trong demo Java.
CREATE TABLE local_user (
    id             BIGINT PRIMARY KEY,
    tenant_id      VARCHAR(100) NOT NULL,
    status         VARCHAR(20) NOT NULL
                   CHECK (status IN ('ACTIVE','SUSPENDED','DISABLED'))
);

CREATE TABLE external_identity (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_user_id     BIGINT REFERENCES local_user(id),
    idp_entity_id     TEXT NOT NULL,
    sp_scope          TEXT NOT NULL,
    name_id_format    TEXT NOT NULL,
    name_qualifier    TEXT NOT NULL DEFAULT '',
    sp_name_qualifier TEXT NOT NULL DEFAULT '',
    name_id_value     TEXT NOT NULL,
    status            VARCHAR(20) NOT NULL
                      CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','REVOKED')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (idp_entity_id, sp_scope, name_id_format,
            name_qualifier, sp_name_qualifier, name_id_value)
);

CREATE TABLE local_permission (
    local_user_id BIGINT NOT NULL REFERENCES local_user(id),
    permission    VARCHAR(100) NOT NULL,
    PRIMARY KEY (local_user_id, permission)
);
~~~

Trong ví dụ schema, chuỗi rỗng `''` biểu diễn qualifier **không được cung cấp**. Chỉ dùng quy ước ấy nếu hợp đồng/phân tích dữ liệu chứng minh không gây nhập nhằng với một giá trị thực. Trong production cần xem xét ràng buộc `local_user_id IS NOT NULL` khi `status=ACTIVE`, foreign keys, index, trạng thái link, audit table, encryption/tokenization và quy trình xóa dữ liệu. **Không phải database nào cũng xử lý `NULL` trong unique constraint giống nhau**; cách biểu diễn khóa phải được thiết kế chủ động.

### 8.3. Những trường tuyệt đối không tự dùng để ghép quyền

- `email` hoặc `emailAddress` không có lifecycle contract;
- tên hiển thị, họ tên, ảnh đại diện;
- `groups=["admin"]` ở IdP với ngữ nghĩa nhóm bên ngoài;
- transient NameID và session identifier;
- `tenantId` hoặc `partnerId` do client gửi trong query/body;
- một claim chưa xác minh hoặc một XML element không nằm trong phạm vi chữ ký được xác thực.

## 9. Các tình huống thay đổi và cách xử lý liên kết

### 9.1. Người dùng đổi email

**Đúng:** nếu persistent ID/issuer/SP scope không đổi, giữ local link và cập nhật email chỉ như thuộc tính hồ sơ theo chính sách.  
**Sai:** vì email đổi nên tạo local user mới hoặc gán quyền từ user cũ bằng so sánh tên hiển thị.

### 9.2. IdP chuyển từ persistent sang transient

Đây là **thay đổi hợp đồng định danh**, không phải một thay đổi text vô hại. SP không thể giữ mapping dài hạn chỉ bằng transient. Cần tạm dừng linking tự động, tìm identifier ổn định thay thế, test với đối tác và triển khai migration có phê duyệt. Đừng nâng transient lên “persistent” bằng cách đổi nhãn Format tại SP.

### 9.3. IdP thay đổi persistent NameID trong migration

Có thể xảy ra khi chuyển tenant, directory, entity ID, SP affiliation hoặc chính sách pairwise. Không ghép NameID mới tới local account cũ chỉ vì email giống nhau. Quy trình an toàn:

1. Đóng băng snapshot mapping cũ, xác định IdP cũ và mới.
2. Nhận ánh xạ old→new từ kênh quản trị đã được tin cậy và chứng minh nguồn.
3. Kiểm tra 1–1, không trùng nhiều người, không lẫn tenant.
4. Yêu cầu approval và proof-of-control cho account nhạy cảm.
5. Thực hiện transaction, audit, có rollback; không “nối tạm” hai tài khoản admin không kiểm soát.
6. Kiểm thử session còn hiệu lực, deprovision, thu hồi quyền, cutoff date và xử lý user vắng mặt.
7. Sau migration, xóa fallback nguy hiểm theo email/username hoặc NameID cũ theo chính sách.

### 9.4. Hai IdP cùng phát `p-7b91e`

~~~text
(IdP A, SP Orders, persistent, p-7b91e) → local_user_A
(IdP B, SP Orders, persistent, p-7b91e) → local_user_B
~~~

Chúng là **hai external identities**. Kể cả cùng email, không được tự gộp local account khi thiếu bằng chứng kiểm soát cả hai identity và approval.

### 9.5. Đổi Spring `registrationId`

Nếu chỉ đổi tên khóa cấu hình nhưng IdP entity ID, SP entity ID, NameID và qualifier vẫn giữ, không nhất thiết đổi identity link. Nếu dùng registration ID làm khóa duy nhất, hệ thống dễ tạo hàng nghìn “user mới” sau một lần đổi tên config. Bởi vậy lưu **stable trust identifiers** trong bảng identity link, dùng registration ID như thông tin bổ trợ.

### 9.6. Người dùng nghỉ việc hoặc bị khóa

IdP có thể disable account nhưng phiên SP vẫn tồn tại. Cần kết hợp sync provisioning/deprovision, local user state, session invalidation và kiểm tra quyền tại thời điểm thao tác nhạy cảm. **Persistent NameID vẫn là cùng chuỗi** không chứng minh local user còn được phép truy cập.

## 10. Định danh ảnh hưởng authorization thế nào?

Một sơ đồ ra quyết định cho API đọc đơn hàng:

~~~text
ALLOW_READ_ORDER(subject, order) =
    validated_saml_assertion(subject)
    AND trusted_issuer_and_scope(subject)
    AND linked_local_account(subject).status == ACTIVE
    AND linked_local_account.permissions CONTAINS "APP_ORDER_READ"
    AND linked_local_account.tenant_id == order.owner_tenant_id
    AND any_business_specific_checks_pass
~~~

Một external identity có thể map ổn định tới `user_104` nhưng `user_104` vẫn **không được phép** đọc đơn hàng của Partner B. Kiểm tra ở backend/service/repository, không chỉ ẩn nút trên giao diện.

| Định danh và liên kết | Local permission | Tài nguyên | Kết quả |
| --- | --- | --- | --- |
| Persistent hợp lệ, link tới active user A | `APP_ORDER_READ` | Order thuộc A | **ALLOW** |
| Persistent hợp lệ, link tới active user A | `APP_ORDER_READ` | Order thuộc B | **DENY** |
| Persistent hợp lệ, link tới active user A | Không có `APP_ORDER_READ` | Order thuộc A | **DENY** |
| Persistent hợp lệ, link tới disabled user | Bất kỳ | Bất kỳ | **DENY** |
| Persistent hợp lệ nhưng chưa link | Claim `groups=admin` bên IdP | Bất kỳ | **DENY** |
| Transient SSO hợp lệ, không có durable link | Không có local quyền | Bất kỳ protected order | **DENY** |
| Issuer/signature/audience không hợp lệ | Bất kỳ | Bất kỳ | **REJECT AUTHENTICATION** |

Trong Servlet web, “chưa xác thực” thường khiến filter chuyển sang login; “đã xác thực nhưng thiếu quyền” thường dẫn tới **403 Forbidden**. Hành vi HTTP cụ thể tùy entry point/API setup. Không dùng lỗi 403 do quyền local để biện minh cho việc bỏ xác minh SAML.

### 10.1. Transient vẫn có thể phục vụ một dịch vụ không cần local user

Ví dụ một trang đọc tài liệu công khai chỉ cho phép đối tác đã xác thực truy cập, không lưu hồ sơ từng cá nhân. Sau khi validate SAML, SP có thể tạo **session ngắn** với quyền cực hẹp được định nghĩa cho một nhóm người dùng/đối tác, không cần ghi NameID transient vào bảng local account.

Nếu nghiệp vụ cần track audit theo cá nhân hoặc cấp quyền theo ownership, transient **không đủ** và phải có định danh ổn định đã được phê duyệt. Tránh gộp “anonymous guest được xác thực” với local user mang quyền cao.

## 11. Ví dụ Java 17 chạy độc lập: kiểm tra liên kết và phạm vi quyền

Để thấy rõ hệ quả, ví dụ sau mô phỏng **sau bước SAML verification**: dữ liệu `ExternalKey` được giả định là đã đến từ Assertion mà một bộ xác minh SAML đáng tin cậy đã kiểm tra. Chương trình **không** parse XML, verify signature hoặc tạo IdP. Nó chỉ trình bày **chính sách liên kết local account và authorization**.

### 11.1. File duy nhất `IdentityLinkDemo.java`

~~~java
import java.util.Map;
import java.util.Set;

public class IdentityLinkDemo {

    static final String PERSISTENT =
        "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";
    static final String TRANSIENT =
        "urn:oasis:names:tc:SAML:2.0:nameid-format:transient";
    static final String EMAIL =
        "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress";

    static final String IDP_A = "https://idp-a.example/saml";
    static final String IDP_B = "https://idp-b.example/saml";
    static final String SP = "https://orders.example/saml2/sp";

    // Đây là key SAU KHI SAML provider đã xác minh source và scope.
    // Empty qualifier chỉ là quy ước mô phỏng trong ví dụ.
    record ExternalKey(
        String issuer,
        String spScope,
        String format,
        String value,
        String nameQualifier,
        String spNameQualifier) {
    }

    record LocalUser(
        String id,
        String tenantId,
        boolean active,
        Set<String> permissions) {
    }

    static ExternalKey identity(
            String issuer, String format, String value) {
        return new ExternalKey(
            issuer, SP, format, value, issuer, SP);
    }

    static boolean canReadOrder(
            ExternalKey identity,
            String orderTenant,
            Map<ExternalKey, LocalUser> approvedLinks) {

        // Trust/scope check: không tin issuer hoặc SP tùy ý.
        if (!Set.of(IDP_A, IDP_B).contains(identity.issuer())) {
            return false;
        }
        if (!SP.equals(identity.spScope())) {
            return false;
        }

        // Chính sách demo chỉ cho durable link bằng persistent.
        if (!PERSISTENT.equals(identity.format())) {
            return false;
        }

        LocalUser account = approvedLinks.get(identity);

        // Identity chưa link, user bị khóa hoặc quyền sai => deny.
        return account != null
            && account.active()
            && account.permissions().contains("APP_ORDER_READ")
            && account.tenantId().equals(orderTenant);
    }

    public static void main(String[] args) {
        ExternalKey a = identity(IDP_A, PERSISTENT, "p-7b91e");
        ExternalKey b = identity(IDP_B, PERSISTENT, "p-7b91e");
        ExternalKey disabled =
            identity(IDP_A, PERSISTENT, "p-disabled");

        Map<ExternalKey, LocalUser> links = Map.of(
            a, new LocalUser(
                "u-A", "tenant-A", true, Set.of("APP_ORDER_READ")),
            b, new LocalUser(
                "u-B", "tenant-B", true, Set.of("APP_ORDER_READ")),
            disabled, new LocalUser(
                "u-C", "tenant-A", false, Set.of("APP_ORDER_READ"))
        );

        // Hai issuer dùng cùng value, nhưng key vẫn khác nhau.
        System.out.println("A / own tenant: " +
            canReadOrder(a, "tenant-A", links));
        System.out.println("A / other tenant: " +
            canReadOrder(a, "tenant-B", links));
        System.out.println("B / own tenant: " +
            canReadOrder(b, "tenant-B", links));
        System.out.println("B / A tenant: " +
            canReadOrder(b, "tenant-A", links));

        ExternalKey transientId =
            identity(IDP_A, TRANSIENT, "temporary-001");
        System.out.println("transient / A: " +
            canReadOrder(transientId, "tenant-A", links));

        ExternalKey emailId =
            identity(IDP_A, EMAIL, "an@partner-a.example");
        System.out.println("email / A: " +
            canReadOrder(emailId, "tenant-A", links));

        System.out.println("disabled / A: " +
            canReadOrder(disabled, "tenant-A", links));

        // Một external key persistent giống hệt được gặp lại.
        ExternalKey aAgain = identity(IDP_A, PERSISTENT, "p-7b91e");
        System.out.println("A repeat SSO: " +
            canReadOrder(aAgain, "tenant-A", links));
    }
}
~~~

### 11.2. Biên dịch và chạy

Không cần Spring, Gradle hoặc thư viện ngoài. Dùng JDK 17 hoặc cao hơn:

~~~bash
javac --release 17 IdentityLinkDemo.java
java IdentityLinkDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
A / own tenant: true
A / other tenant: false
B / own tenant: true
B / A tenant: false
transient / A: false
email / A: false
disabled / A: false
A repeat SSO: true
~~~

Giải thích từng dòng:

1. A có persistent link `u-A` đang active, quyền đọc và đúng tenant A → true.
2. A có permission nhưng tài nguyên thuộc B → false.
3. B có **cùng NameID value** với A, nhưng issuer khác; B được link riêng với `u-B`, đúng tenant B → true.
4. B không thể đọc tài nguyên tenant A → false.
5. Transient NameID không có durable link và bị policy demo loại khỏi liên kết lâu dài → false.
6. EmailAddress không phải format được dùng để duyệt durable link trong demo → false, kể cả email có thể trông hợp lệ.
7. Local user bị disable → false.
8. Cùng key persistent lặp lại cho phép tra cùng `u-A` → true.

**Giới hạn có chủ đích:** đây là mô hình **sau khi đã xác minh SAML**, trong memory, với danh sách issuer và map link được phê duyệt **cố định**. Nó không phải SP production, không có database, transaction, certificate, session/cookie, parser, SAML signature hoặc cấp phát user. Không lấy dữ liệu HTTP chưa xác minh để tạo `ExternalKey` rồi kỳ vọng method `canReadOrder` thay thế SAML verification.

### 11.3. Điều cần bổ sung khi chuyển sang production

- Map chuyển thành table `external_identity` có transaction, unique composite key, audit và quy trình approval.
- Trust list từ `RelyingPartyRegistrationRepository` được cấu hình, không phải các literal URL bất kỳ.
- Kiểm tra format và qualifiers trong **Assertion đã được xác minh**; chỉ `getName()` không đủ để biết format.
- Tài khoản và permissions từ database; kiểm tra quyền trên từng resource/request, hỗ trợ thu hồi và cache invalidation.
- Khi SAML principal hoặc local account không đủ thông tin, trả trạng thái **UNLINKED/PENDING/DENIED**, không đoán từ email.
- Dùng optimistic locking/unique constraint để chống hai callback tạo liên kết cạnh tranh.
- Cân nhắc mã hóa/hashing có secret cho chỉ mục identity nếu yêu cầu giảm rủi ro rò rỉ, đồng thời giữ khả năng truy vấn và rotation; đừng ghi persistent ID thô lên log.

## 12. Áp dụng trong Spring Security SAML2 Login

### 12.1. Ranh giới của Spring Security

Một Spring Boot Servlet SP thường có:

~~~text
IdP metadata ──> RelyingPartyRegistration
                     |
HTTP SAMLResponse --> SAML processing filter/provider
                     |
              Validation thành công
                     |
              Saml2Authentication
                     |
              Saml2AuthenticatedPrincipal
                     |
           Local identity linking service
                     |
            User status + local roles
                     |
           Service/resource authorization
~~~

`spring-security-saml2-service-provider` cung cấp SAML login, còn business application thiết kế external identity link. Trong các nhánh Spring Security 6.x, principal `Saml2AuthenticatedPrincipal` hỗ trợ `getName()` và `getRelyingPartyRegistrationId()`, cùng các Attribute do IdP phát hành.

**Quan trọng:** `principal.getName()` thường là NameID value, **không phải toàn bộ NameID XML**; chỉ từ một chuỗi này không thể chắc Format/NameQualifier/SPNameQualifier. `getRelyingPartyRegistrationId()` chỉ cho biết registration nội bộ, không thay thế kiểm tra issuer/SP scope. Nếu cần phân biệt persistent và transient, lấy thông tin từ **Assertion đã được provider xác minh**, qua extension point/response converter tương ứng với Spring Security và OpenSAML version thực tế.

### 12.2. Cấu hình SP tối giản để thấy lớp xác thực

Ví dụ **Spring Boot 3.3.x / Spring Security 6.x**, có IdP metadata thật. `application.yml`:

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

`SecurityConfig.java`, đặt trong một Spring Boot ứng dụng Servlet đã có Spring Security SAML2 dependency:

~~~java
package com.example.federated;

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
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

Đoạn này chỉ bật **SAML authentication** và kiểm tra “có authentication”; nó **chưa** giới hạn API nhạy cảm theo local permission. Để tránh hiểu nhầm, trên production cần thêm service-level authorization như `@PreAuthorize`/business policy, và liên kết external identity với local account **trước khi cấp quyền**.

Một `Controller` để quan sát hai thuộc tính cơ bản sau xác thực:

~~~java
package com.example.federated;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    @GetMapping("/")
    public String home() {
        return "Visit /me for SAML sign-in";
    }

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of(
            "nameIdValue", principal.getName(),
            "registrationId", principal.getRelyingPartyRegistrationId()
        );
    }
}
~~~

Mẫu Controller này **không** trả Format hay qualifiers. Không dùng nó làm bằng chứng rằng NameID là persistent. Trong production, cũng nên loại bỏ hoặc giới hạn endpoint debug này vì identifier có tính nhạy cảm.

Để thực thi policy phân biệt persistent/transient sau xác thực, cần extension point làm việc với assertion đã được validated (hoặc thiết kế một trusted identity adapter có contract phù hợp) để tạo `ExternalKey` như mục 11. **Không tự parse lại raw SAMLResponse bên cạnh Spring Security**; có nguy cơ đọc sai phần tử XML so với phần tử được xác minh chữ ký.

### 12.3. Nếu dùng Spring Security 7.x

API liên quan SAML authentication/principal có thay đổi giữa các bản, đặc biệt khi dùng OpenSAML 5 và các representation assertion mới. **Tra Javadoc/migration guide đúng phiên bản runtime** trước khi copy code 6.x. Nguyên tắc không thay đổi: validation SAML trước, external identity link sau, local authorization cuối.

### 12.4. NameIDPolicy chỉ là yêu cầu, không phải kết quả

SP có thể yêu cầu IdP phát persistent trong `AuthnRequest`:

~~~xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"/>
~~~

IdP có thể không hỗ trợ, hoặc có policy lựa chọn khác. Trước khi mapping durable link, phải kiểm tra **NameID Format thực nhận** và thử ít nhất hai lần login cùng subject. Việc gửi request có URI persistent **không** tự khiến một transient subject ổn định.

## 13. Kiểm thử bắt buộc trước khi cấp quyền thực

### 13.1. Ma trận kiểm thử

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| I01 | Persistent NameID giữ nguyên giữa hai phiên SSO của cùng user, đúng issuer/SP scope. | Cùng external link dẫn tới cùng local user. |
| I02 | Transient NameID thay giữa hai lần SSO. | Không tạo durable link từ transient value. |
| I03 | Hai IdP phát cùng persistent value. | Hai external identities khác nhau; không nhầm local account. |
| I04 | Cùng IdP nhưng hai SP nhận pairwise persistent value khác. | Không suy đoán là cùng user hay cố hợp nhất giữa SP. |
| I05 | Người dùng đổi email, persistent ID không đổi. | Vẫn tìm đúng local user; cập nhật email như hồ sơ. |
| I06 | Email cũ được cấp lại cho người khác. | Không chiếm được local account thông qua email matching. |
| I07 | IdP trả `Format=unspecified` nhưng hợp đồng chưa chứng minh ổn định. | Không tự tạo privileged durable link. |
| I08 | Persistent ID đổi khi IdP migration. | Đưa vào quy trình old→new được chứng minh và phê duyệt. |
| I09 | User SAML hợp lệ nhưng chưa có external link. | UNLINKED/PENDING; không được truy cập API nghiệp vụ. |
| I10 | User được link nhưng local account disabled. | Từ chối quyền, dù IdP vẫn xác thực. |
| I11 | User A có `APP_ORDER_READ`, order thuộc B. | DENY do tenant/ownership. |
| I12 | Claim bên IdP là `groups=admin` nhưng local không có quyền. | DENY chức năng admin. |
| I13 | Hai callback tạo link cùng external identity đồng thời. | Chỉ một liên kết được commit hoặc báo conflict có kiểm soát. |
| I14 | Assertion sai chữ ký, issuer, audience, recipient hoặc hết hạn. | REJECT trước khi account linking. |
| I15 | SP đổi tên Spring registration ID, issuer/SP entity ID vẫn giữ. | Không phá link do lưu stable scope. |
| I16 | External link bị REVOKED hoặc local permission bị thu hồi khi phiên còn sống. | Policy/session invalidation ngăn hành động nhạy cảm kịp thời. |
| I17 | IdP chỉ gửi transient nhưng SP cần audit từng người dài hạn. | Yêu cầu subject ổn định khác/đàm phán IdP, không bịa mapping. |
| I18 | Một NameID có qualifier khác với scope được duyệt. | Không tự đồng nhất hai identity; xử lý theo contract. |

### 13.2. Cách test thực tế

1. Tạo **IdP test** đã đăng ký SP đúng entity ID và ACS, có signing certificate tin cậy.
2. Tạo hai user IdP khác nhau và hai tenants ở SP; thử login nhiều lần với từng người.
3. Với IdP hỗ trợ persistent, xác nhận NameID value/Format/qualifiers theo môi trường test; thay đổi email rồi kiểm tra link vẫn đúng.
4. Với transient, thực hiện nhiều lần SSO và xác nhận SP không dùng value tạm làm `local_user_id` lâu dài.
5. Gửi hai IdP/registrations có cùng chuỗi NameID value để kiểm tra composite-key scoping.
6. Thử user chưa có link, disabled user, account bị revoke, thiếu permission và order tenant khác.
7. Thử quy trình migration với một mapping old→new có phê duyệt và một mapping nhập nhằng; mapping nhập nhằng phải fail closed.
8. Kiểm tra log không chứa private key, raw XML, SAMLResponse hoặc persistent NameID thô ngoài policy.
9. Dùng tools thích hợp để kiểm tra **Assertion thật đã được provider xác minh**; không đăng tải response từ người dùng thật lên website debug không tin cậy.

**Tiêu chí hoàn thành:** học viên giải thích được vì sao cùng một người có thể có transient value khác nhau, vì sao hai người từ hai IdP có thể có persistent value giống nhau, và vì sao một persistent link hợp lệ vẫn không cho phép đọc tài nguyên tenant khác.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| “NameID có `Format=persistent` thì dùng mỗi value làm primary key toàn cầu.” | Không có tính duy nhất toàn cục giữa IdP/SP. | Dùng composite key có issuer/SP scope/qualifiers. |
| “Transient chỉ là persistent ngắn hơn nên vẫn lưu mãi.” | Semantics tạm thời, không bảo đảm lặp lại. | Dùng ephemeral session hoặc identifier khác ổn định. |
| Ghép local user bằng email từ IdP. | Email có thể thay đổi/tái sử dụng. | Link có phê duyệt theo identifier được cam kết. |
| Tin `groups=admin` bên IdP là `ROLE_ADMIN`. | Namespace/quyền của IdP không mặc định là quyền nghiệp vụ SP. | Mapping local least privilege. |
| Chỉ cần chứng thực SAML hợp lệ là có quyền xem mọi tài nguyên. | Authentication ≠ authorization. | Kiểm tra local account, tenant và resource ownership. |
| Xóa email/viết thường tất cả NameID rồi so sánh. | Opaque identifier có thể phân biệt hoa/thường, ký tự và namespace. | Bảo toàn value, chỉ chuẩn hóa theo contract. |
| Khi NameID đổi, tự link theo tên hiển thị. | Dễ chiếm nhầm tài khoản hoặc cấp lại quyền. | Migration old→new có nguồn, approval và audit. |
| Bỏ issuer vì registration ID đã đủ. | Registration ID có thể đổi/tái sử dụng, không chứng minh trust nguồn. | Lưu issuer/SP entity ID ổn định. |
| Chỉ xem `principal.getName()` để đoán Format. | Chuỗi tên không bao gồm đủ XML NameID metadata. | Đọc verified Assertion theo API version-specific. |
| Decode raw XML bằng XPath rồi dùng giá trị làm authority. | Có thể đọc phần tử không được chữ ký bảo vệ. | Dùng thư viện SAML chuẩn và conversion/validation an toàn. |
| Tự động cấp quyền cho subject mới chỉ vì IdP đăng nhập được. | Bất kỳ nhân viên đối tác có thể chiếm quyền nghiệp vụ. | UNLINKED/PENDING, approval và policy cấp quyền. |
| Giữ local user active sau khi đối tác đã disable. | Phiên SP hoặc cache quyền cũ có thể sống tiếp. | Đồng bộ revoke, session invalidation, kiểm tra lại khi cần. |
| Cho phép client chọn `partnerId`/issuer để lookup quyền. | User có thể đổi tham số và vượt tenant. | Tenant và issuer lấy từ trusted identity link. |
| Log raw NameID toàn hệ thống. | Persistent pseudonym có thể cho phép theo dõi người dùng. | Bảo vệ identity data, log tối thiểu và giới hạn retention. |

## 15. Checklist thiết kế trước production

- [ ] Đã xác nhận format URI NameID thực tế (`persistent`, `transient` hoặc format khác).
- [ ] Với persistent, IdP cam kết uniqueness/stability **theo issuer và SP scope**, có quy trình deprovision/migration.
- [ ] Với transient, ứng dụng không lưu value làm durable user key.
- [ ] External identity key lưu đúng issuer, SP scope, format, qualifiers và value; không chỉ email/NameID đơn thuần.
- [ ] Có unique constraint, transaction, race-condition handling và audit cho account linking.
- [ ] Local account mới không mặc định có permission nhạy cảm.
- [ ] Nguồn tenant và permissions do SP quản lý hoặc trust contract quy định; không lấy trực tiếp từ query string.
- [ ] Response/Assertion được xác minh chữ ký, issuer, audience, recipient, InResponseTo, thời hạn, replay trước khi link.
- [ ] Không tự parse raw response bên ngoài provider để lấy một NameID khác nội dung đã xác minh.
- [ ] Có trạng thái UNLINKED/PENDING/ACTIVE/SUSPENDED/REVOKED và quy trình phê duyệt.
- [ ] Có quy trình đổi issuer/SP entity ID/NameID để không âm thầm tạo hoặc merge account đặc quyền.
- [ ] Khi revoke account hoặc permission, các phiên đã đăng nhập cũng chịu chính sách thu hồi.
- [ ] Resource-level authorization kiểm tra tenant và ownership ở backend.
- [ ] Có kiểm thử I01–I18 hoặc test tương đương, bao gồm nhiều IdP và thay đổi email.
- [ ] Log, telemetry và lưu trữ NameID tuân thủ privacy/security policy.
- [ ] Spring Security/OpenSAML API được đối chiếu với phiên bản runtime khi triển khai converter/validator thực sự.

## Ghi nhớ

> **Persistent NameID** giúp SP liên kết một subject theo thời gian **trong đúng phạm vi IdP–SP đã thỏa thuận**; **transient NameID** phù hợp những phiên không cần nhận diện bền vững và **không thể được xem là khóa account lâu dài**. Trong mọi trường hợp, **verified identity → approved local link → local permission → resource authorization** là bốn bước tách biệt.

### Tài liệu chính thức

- [OASIS — SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf), phần `Name Identifier Formats` (persistent và transient).
- [OASIS — SAML V2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html), mục **4.4.2**, **5.4.2–5.4.5** về Federation, persistent/transient pseudonym và termination.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html), conversion/validation, principal và vai trò của local authorization.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html), registration, IdP metadata, filters và ACS.
- [Spring Security 6.5 — Saml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html), thuộc tính và registration ID.
- [Microsoft Entra ID — Customize SAML token claims](https://learn.microsoft.com/entra/identity-platform/saml-claims-customization), ví dụ lựa chọn NameID Format tại IdP và các đặc thù triển khai.
