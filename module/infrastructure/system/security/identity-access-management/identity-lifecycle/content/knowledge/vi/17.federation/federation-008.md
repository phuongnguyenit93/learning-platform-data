# Federation mapping trong IAM: ánh xạ danh tính, thuộc tính và quyền giữa các miền tin cậy

> **Chương:** Federation  
> **Bài:** Federation mapping  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Bối cảnh:** Quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản và cấp quyền đến điều chỉnh, thu hồi; kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

## 1. Federation mapping là gì và vì sao quan trọng?

Khi một nhân viên đăng nhập ứng dụng nội bộ, ứng dụng có thể trực tiếp quản lý tài khoản người dùng. Nhưng trong tổ chức có nhiều dịch vụ SaaS hoặc hợp tác với đối tác, ứng dụng thường **tin cậy một Identity Provider (IdP) bên ngoài** để xác thực người dùng. Cách kết nối này được gọi là *identity federation* (liên kết định danh giữa các miền tin cậy).

**Federation mapping** là quá trình có kiểm soát để chuyển đổi **định danh, thuộc tính và ngữ cảnh xác thực được xác minh** từ hệ thống phát hành danh tính sang mô hình danh tính và phân quyền của ứng dụng nhận.

Một cách giản lược:

~~~text
IdP phát hành bằng chứng danh tính đã được xác minh
                 |
                 v
   Xác thực issuer, chữ ký, audience, thời hạn
                 |
                 v
   Ánh xạ identity + thuộc tính + ngữ cảnh
                 |
                 v
    Liên kết account/role/policy tại ứng dụng
                 |
                 v
         Kiểm tra quyền trên tài nguyên
~~~

Ví dụ, nhân viên An thuộc bộ phận hỗ trợ khách hàng tại Hà Nội. IdP của doanh nghiệp xác thực An và cung cấp một định danh ổn định cùng những thuộc tính được phép chia sẻ. SaaS CRM cần ánh xạ:

- **Ai đang đăng nhập?** Định danh từ IdP liên kết với account CRM nào?
- **Được làm gì?** Thuộc tính hoặc group được ánh xạ đến role `crm.support-agent` như thế nào?
- **Trên dữ liệu nào?** Quyền theo chi nhánh Hà Nội được thực thi tại CRM ra sao?
- **Thay đổi có lan truyền không?** Khi An chuyển chi nhánh hoặc nghỉ việc, điều gì khiến account và quyền tại CRM được cập nhật/thu hồi?

Nếu mapping sai, một danh tính có thể bị liên kết nhầm với tài khoản của người khác, một group bình thường có thể biến thành role quản trị hoặc quyền cũ có thể tồn tại sau Mover/Leaver.

**Kết luận ban đầu:** Federation giúp ứng dụng **tin kết quả xác thực từ IdP**, nhưng mapping quyết định cách ứng dụng **diễn giải dữ liệu nhận được**. Mapping không đúng có thể tạo ra lỗ hổng phân quyền dù thông điệp SAML/OIDC có chữ ký hợp lệ.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Identity Provider (IdP)** | Xác thực chủ thể và phát hành kết quả xác thực/khẳng định danh tính theo giao thức | IdP của doanh nghiệp |
| **Service Provider (SP)** | Ứng dụng nhận assertion SAML và thiết lập phiên theo quan hệ tin cậy | SaaS quản lý dự án |
| **Relying Party (RP) / OIDC Client** | Ứng dụng sử dụng kết quả xác thực OIDC | Portal nội bộ dùng OIDC |
| **Issuer** | Định danh nguồn phát hành assertion/token, có thể biểu diễn như `iss` trong OIDC | `https://login.example.org/tenant-a` |
| **Subject** | Chủ thể được định danh trong bằng chứng, ví dụ `sub` trong OIDC hoặc NameID SAML | `u-79ac12` |
| **Claim / Attribute** | Thông tin về chủ thể hoặc ngữ cảnh, do bên phát hành cung cấp | Department, group ID, auth context |
| **Account linking / correlation** | Liên kết identity liên kết với account tại ứng dụng đích | `(issuer, subject) → crm_user_id` |
| **Role mapping** | Chuyển thuộc tính/group đã tin cậy thành vai trò/quyền tại ứng dụng | Group nguồn A → `crm.viewer` |
| **JIT provisioning** | Tạo/đăng ký account khi người dùng đăng nhập lần đầu theo chính sách | User mới vào CRM sau lần SSO đầu |
| **SCIM provisioning** | Đồng bộ vòng đời User/Group và membership qua API nếu đích hỗ trợ | Tạo, cập nhật, vô hiệu hóa account CRM |
| **Authorization** | Quyết định cho phép hành động trên tài nguyên | Được xem hồ sơ khách hàng số 42 hay không |

**Federation mapping không đồng nghĩa SCIM mapping.** Federation thường diễn ra khi hệ thống nhận một kết quả xác thực hoặc token. SCIM phục vụ provisioning tài khoản/nhóm qua kênh quản trị, có thể chạy độc lập với phiên đăng nhập. Cả hai cần dùng **cùng nguyên tắc liên kết danh tính**, nhưng trạng thái account, role và thời gian cập nhật có thể khác nhau.

### 2.1. Chủ thể khác tài nguyên

Trong một lần đăng nhập, **subject** có thể là nhân viên, đối tác hoặc tài khoản khách. Trong một lần gọi API không có người dùng, subject/client có thể là **application principal hoặc workload identity**. Cần nhận diện loại chủ thể trước khi ánh xạ quyền: role của người dùng không nên tự được trao cho client máy với máy.

### 2.2. Xác thực thành công không tự động là có quyền

Một IdP xác thực đúng An chỉ chứng minh rằng An đã hoàn thành quy trình xác thực được chấp nhận. CRM vẫn phải kiểm tra:

1. IdP có được tin cậy cho ứng dụng này không?
2. Danh tính liên kết với account CRM nào và account có active không?
3. An có role/entitlement hợp lệ không?
4. Tài nguyên đang truy cập có nằm đúng chi nhánh, tenant và phạm vi được phép không?

## 3. Bốn lớp mapping quan trọng

Có thể phân loại federation mapping thành bốn lớp để tránh trộn lẫn trách nhiệm.

| Lớp | Đầu vào tin cậy | Kết quả | Rủi ro nếu làm sai |
|---|---|---|---|
| **1. Trust mapping** | Issuer, khóa ký, metadata, audience, client/SP config | Chấp nhận hay từ chối nguồn assertion/token | Tin một IdP giả hoặc assertion gửi sai ứng dụng |
| **2. Identity mapping** | Issuer + subject định danh ổn định; liên kết đã duyệt | Account tại ứng dụng đích | Đăng nhập nhầm tài khoản, account takeover |
| **3. Attribute mapping** | Claims, thuộc tính từ nguồn có thẩm quyền | Department, tenant, region, trạng thái, dữ liệu hồ sơ | Thuộc tính sai hoặc lỗi thời làm cấp sai quyền |
| **4. Entitlement mapping** | Group ID, role, policy và approval | Role/permission/scope trong SP/RP | Privilege escalation, SoD conflict, quyền tồn dư |

Ngoài bốn lớp, còn **session/authentication-context mapping**: ứng dụng diễn giải thời điểm, phương thức hoặc mức bảo đảm xác thực để yêu cầu bước xác thực bổ sung (*step-up*) cho hành động nhạy cảm. Đây không phải quyền nghiệp vụ mà là **điều kiện của một quyết định truy cập**.

### 3.1. Chọn hệ thống nào là nguồn có thẩm quyền?

Một claim xuất hiện trong token **không đủ** để chứng minh IdP là nguồn phù hợp cho thuộc tính đó. Ví dụ:

- HRIS có thể là nguồn cho trạng thái nhân viên, phòng ban và ngày kết thúc.
- IdP phát hành danh tính/nhóm sau khi lấy dữ liệu và áp dụng chính sách của tổ chức.
- Chủ tài nguyên phê duyệt quyền xuất dữ liệu khách hàng nhạy cảm.
- Ứng dụng đích có thể sở hữu dữ liệu phân quyền theo hồ sơ, tenant hoặc giao dịch.

Do đó, mapping cần tài liệu hóa cả **nguồn gốc thuộc tính**, **quy tắc biến đổi** và **thẩm quyền cho phép sử dụng thuộc tính để cấp quyền**.

## 4. Trust mapping: trước khi tin claim, phải xác minh thông điệp

Một lỗi nghiêm trọng là đọc claim trước rồi gán role, nhưng không xác thực đầy đủ token/assertion hoặc không ràng buộc với nguồn được phê duyệt.

### 4.1. Các kiểm tra nền tảng với OIDC

Tùy flow/giao thức, RP cần kiểm tra theo cấu hình chính thức:

- **Issuer (`iss`)** là issuer đã được đăng ký, không chỉ có domain trông giống.
- **Chữ ký và thuật toán** hợp lệ với khóa tin cậy của issuer; không nhận khóa/thuật toán tùy tiện từ dữ liệu không được tin.
- **Audience (`aud`)** phù hợp client nhận ID token.
- **Thời hạn (`exp`, `iat`, các điều kiện liên quan)** theo policy.
- **Nonce** khi flow yêu cầu, để liên kết kết quả xác thực với yêu cầu đã khởi tạo.
- **State và PKCE** trong luồng Authorization Code phù hợp để giảm rủi ro CSRF/mã ủy quyền bị lạm dụng.
- **Auth context** nếu ứng dụng cần kiểm tra phương thức hoặc độ mới xác thực.
- Chính sách về **tenant** và issuer được phép; không chấp nhận tenant bất kỳ chỉ vì cùng nhà cung cấp.

Đối với API, **access token** phải được xác minh theo hợp đồng của authorization server và audience của chính API; không dùng ID token của web client như một API access token.

### 4.2. Các kiểm tra nền tảng với SAML

Với SAML, SP cần kiểm tra đúng loại message/assertion và hợp đồng tin cậy, như:

- Chữ ký số và cấu hình khóa chứng thực của IdP; bảo đảm phần dữ liệu được tiêu thụ chính là phần đã được xác minh.
- Issuer và đối tượng nhận: `AudienceRestriction`, `Destination`, `Recipient` theo profile.
- Thời hạn/điều kiện: `NotBefore`, `NotOnOrAfter` và độ lệch đồng hồ cho phép.
- `InResponseTo` cho flow yêu cầu–phản hồi và các biện pháp chống replay thích hợp.
- Subject confirmation và cấu hình endpoint/chứng chỉ phù hợp.
- Mã hóa assertion nếu cần để đáp ứng yêu cầu bảo mật dữ liệu, đồng thời không coi mã hóa là thay thế kiểm tra chữ ký.

SAML có nhiều profile và cách cấu hình; hệ thống phải tuân thủ thông số và thư viện đáng tin của profile đang dùng. **Không xây parser XML hoặc logic chấp nhận assertion tùy tiện chỉ dựa trên một trường NameID.**

## 5. Identity mapping: liên kết đúng một chủ thể với đúng một account

Đây là lớp có ảnh hưởng trực tiếp đến nguy cơ **chiếm tài khoản do liên kết sai** (*account linking takeover*).

### 5.1. Dùng khóa định danh ổn định có namespace

Với OIDC, cách biểu diễn nền tảng là cặp:

~~~text
Federated subject key = (trusted_issuer, subject)
Ví dụ:
  issuer  = https://login.example.org/tenant-a
  subject = 7a4b9c21

Ứng dụng liên kết cặp trên với:
  localAccountId = crm-user-2048
~~~

**Không dùng riêng `sub` mà bỏ qua issuer.** Hai issuer có thể cùng phát hành subject `123`, nhưng đó là hai danh tính khác nhau. Ngược lại, cùng một người có thể có các subject khác nhau giữa nhiều issuer hoặc RP.

Trong OIDC, `sub` được định danh trong phạm vi issuer và phải phù hợp mô hình subject của issuer. Một số issuer dùng **pairwise subject** khác nhau theo relying party, nên không được mặc định hai client nhìn thấy cùng `sub` cho một người.

Với SAML, mapping có thể dùng **persistent NameID**, issuer và NameID format hoặc một thuộc tính ổn định đã được thỏa thuận. NameID dạng transient không thích hợp làm khóa liên kết tài khoản tồn tại lâu dài.

### 5.2. Vì sao không tự động ghép theo email?

Email có thể đổi tên miền, đổi khi nhân viên kết hôn, được tái cấp cho người khác hoặc chưa được xác minh tại nguồn bên ngoài. Nếu ứng dụng tự liên kết chỉ vì email bên ngoài trùng email nội bộ, một người có thể chiếm account khác.

Ví dụ:

~~~text
Local account:
  email = alex@company.example
  role  = admin

External assertion từ issuer không đáng tin:
  email = alex@company.example
  email_verified = true

Nếu hệ thống bỏ qua issuer/trust và tự link theo email:
  RỦI RO: người bên ngoài đăng nhập vào local admin account
~~~

`email_verified=true` có ý nghĩa trong ngữ cảnh của **issuer đã xác minh** và quy tắc của issuer, không phải bằng chứng toàn cục rằng tài khoản bên ngoài có quyền sở hữu account nội bộ. Đặc biệt trong federation đa tenant, email không phải khóa liên kết an toàn duy nhất.

**Nguyên tắc an toàn:** dùng ID ổn định có namespace; liên kết lần đầu theo quy trình onboarding/phê duyệt có căn cứ, không tự động hợp nhất tài khoản nhạy cảm từ một trường trùng tên.

### 5.3. Account linking lifecycle

Một liên kết identity–account có thể trải qua:

1. `UNLINKED`: chưa có quan hệ với ứng dụng.
2. `PENDING_VERIFICATION`: ứng dụng/IAM đang xác minh đủ điều kiện liên kết.
3. `LINKED`: đã lưu cặp issuer+subject ↔ local account ID.
4. `SUSPENDED`: có rủi ro hoặc trạng thái không còn hợp lệ.
5. `RELINK_REQUIRED`: đổi issuer/tenant/định danh đòi bằng chứng chuyển đổi.
6. `UNLINKED_REVOKED`: liên kết bị thu hồi theo quy trình, tài khoản/phiên được xử lý riêng.

Đây là trạng thái **minh họa**; hệ thống thật có thể dùng enum khác. Việc un-link một định danh không đồng nghĩa xóa toàn bộ dữ liệu của account nếu còn yêu cầu lưu trữ, chuyển giao hoặc kiểm toán.

## 6. Attribute mapping trong OIDC

Một ID token OIDC có thể chứa claims chuẩn và claims mở rộng theo hợp đồng giữa IdP và RP. Ví dụ giả lập:

~~~json
{
  "iss": "https://login.example.org/tenant-a",
  "sub": "7a4b9c21",
  "aud": "crm-web-client",
  "iat": 1795400000,
  "exp": 1795400300,
  "email": "an@company.example",
  "email_verified": true,
  "name": "Nguyen An",
  "department": "customer-support",
  "region": "HN",
  "groups": ["grp-crm-users", "grp-crm-support-hn"],
  "acr": "corp-mfa",
  "auth_time": 1795399980
}
~~~

Đây là **payload minh họa**, không phải token thực hoặc bộ claims có mặt ở mọi IdP. Việc thêm thuộc tính `department`, `region`, `groups` cần cấu hình/nguồn dữ liệu phù hợp. Thời gian là số kiểu Unix timestamp minh họa.

Một mapping có thể được mô tả:

| Claim nguồn đã xác minh | Thuộc tính đích | Quy tắc chuyển đổi | Khi thiếu hoặc không hợp lệ |
|---|---|---|---|
| `iss` + `sub` | `federatedIdentityKey` | Kết hợp theo namespace, so với danh sách issuer tin cậy | Từ chối liên kết/đăng nhập |
| `email` | `contactEmail` | Lưu dưới dạng thông tin liên hệ nếu policy cho phép | Không dùng làm khóa liên kết duy nhất |
| `name` | `displayName` | Chuẩn hóa hiển thị, xử lý độ dài/ký tự | Dùng tên hiển thị mặc định, không cấp quyền |
| `department` | `departmentCode` | Chỉ nhận giá trị theo danh mục hợp lệ | Không suy luận mặc định thành quyền cao |
| `region` | `dataRegion` | Ánh xạ mã vùng theo bảng có owner | Không mở rộng thành tất cả region |
| `groups[]` | `externalGroupIds[]` | Chỉ nhận group ID có mapping rõ | Không tự cấp role lạ |
| `acr`, `auth_time` | `authenticationContext` | Diễn giải theo hợp đồng của issuer | Yêu cầu step-up hoặc từ chối hành động nhạy cảm |

**Điểm rất quan trọng:** người dùng có thể tự chỉnh một trường hồ sơ ở hệ thống nguồn nhưng điều đó không có nghĩa trường này được phép quyết định role. Nguồn `department` để cấp quyền phải được kiểm soát bởi cơ chế quản trị có thẩm quyền.

### 6.1. Chuẩn hóa dữ liệu nhưng giữ nguyên định danh ổn định

Có thể chuẩn hóa tên hiển thị, mã chi nhánh hoặc ngôn ngữ sử dụng cho thuận tiện. Tuy nhiên không nên:

- Đổi dạng `sub` bằng cách bỏ số 0 đầu, thay chữ hoa–chữ thường tùy tiện hoặc biến đổi dẫn đến va chạm ID.
- Gộp subject từ các issuer khác nhau chỉ vì ID ngắn giống nhau.
- Tự chuyển `region` không nhận biết thành `ALL`.
- Biến giá trị group không có mapping thành `admin`.

Hãy phân biệt **thuộc tính hiển thị** với **khóa nhận diện và nguồn phân quyền**. Chỉ biến đổi khóa định danh khi có hợp đồng và kiểm thử rõ ràng với nhà cung cấp.

### 6.2. Claim về group có thể không đầy đủ

Một số IdP giới hạn số group được nhúng trong token hoặc dùng cơ chế báo cần truy vấn group qua API. Vì vậy không nên giả định mảng `groups` luôn có đầy đủ membership. Nếu ứng dụng cần effective groups:

1. Kiểm tra khả năng và hợp đồng của IdP.
2. Chỉ sử dụng API tin cậy và quyền được cấp phù hợp khi cần tra cứu bổ sung.
3. Cân nhắc membership trực tiếp, nhóm lồng nhau và chu kỳ cập nhật.
4. Xử lý trạng thái thiếu/không chắc chắn an toàn theo chính sách.

Không tự xem một claim trống là “không có quyền” trong mọi bài toán vận hành, nhưng đối với **cấp quyền nhạy cảm**, không được tự suy diễn thành “có quyền”; phải biểu đạt trạng thái chưa xác định và áp dụng quyết định bảo mật phù hợp.

## 7. Attribute mapping trong SAML

SAML sử dụng assertion chứa những thông tin về subject, điều kiện và các Attribute do IdP gửi cho SP theo hợp đồng. Một ví dụ rút gọn về **ý nghĩa dữ liệu**:

~~~xml
<saml:AttributeStatement xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="department">
    <saml:AttributeValue>customer-support</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="region">
    <saml:AttributeValue>HN</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="groupId">
    <saml:AttributeValue>grp-crm-support-hn</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

Đoạn XML chỉ minh họa AttributeStatement, **không phải assertion SAML hoàn chỉnh có chữ ký**. Không sử dụng đoạn XML riêng này làm đầu vào xác thực hoặc một thông điệp hợp lệ.

### 7.1. Khác nhau giữa NameID và Attribute

- **NameID:** thể hiện subject identifier trong ngữ cảnh NameID format, issuer và profile. Định danh transient/persistent có tính chất khác nhau.
- **Attribute:** dữ liệu bổ sung như department hoặc group, có thể thay đổi và có nhiều giá trị.
- **AuthenticationStatement/Context:** cung cấp thông tin về sự kiện và ngữ cảnh xác thực theo mô hình SAML.

Không nên dùng `displayName` hoặc `department` làm khóa account lâu dài. Một subject có thể đổi phòng ban nhiều lần nhưng vẫn phải giữ đúng liên kết account.

### 7.2. Lỗi thường gặp: sửa tên attribute phá mapping

IdP trước đây phát `Department`, sau nâng cấp phát `department`. Nếu SP đối chiếu tên chính xác, mapping có thể mất dữ liệu. Giải pháp là hợp đồng mapping được version, kiểm thử và rollout; **không tùy tiện nhận mọi alias** nếu alias có thể dẫn đến đọc nhầm một thuộc tính chưa được duyệt.

## 8. Role và group mapping: từ thuộc tính đến quyền nghiệp vụ

Đây là điểm dễ biến một quyết định xác thực thành cấp quyền quá rộng.

### 8.1. RBAC theo mapping rõ ràng

Ví dụ CRM dùng role `crm.viewer`, `crm.support-agent`, `crm.export-approver`. Bảng mapping:

| Group ID từ IdP | Role tại CRM | Phạm vi | Phê duyệt |
|---|---|---|---|
| `grp-crm-users` | Quyền sử dụng account CRM cơ sở | Không tự cấp quyền đọc dữ liệu | Chính sách onboarding |
| `grp-crm-support-hn` | `crm.support-agent` | Chi nhánh Hà Nội | Chủ ứng dụng/chủ dữ liệu xác định |
| `grp-crm-support-dn` | `crm.support-agent` | Chi nhánh Đà Nẵng | Chủ ứng dụng/chủ dữ liệu xác định |
| `grp-crm-export-approved` | `crm.export-approver` | Dữ liệu được duyệt và hạn sử dụng | Phê duyệt quyền nhạy cảm |

**Không map theo từ khóa** như `groupName.includes("admin")` hoặc tự cấp role khi thấy bất kỳ group tên `administrators`. Group có thể trùng tên giữa tenant và có ý nghĩa khác nhau. Nên dùng **ID group ổn định và issuer/tenant đã được tin cậy**, cùng bảng mapping có owner.

### 8.2. ABAC bổ sung điều kiện theo dữ liệu

Ngay cả khi group `grp-crm-support-hn` cấp role `crm.support-agent`, API cần kiểm tra hồ sơ khách hàng thực tế thuộc Hà Nội.

Ví dụ:

~~~text
ALLOW nếu:
  principal.accountStatus == ACTIVE
  AND principal.hasRole("crm.support-agent")
  AND principal.region == customer.region
  AND action IN ["customer.read", "customer.update"]
  AND customer.classification != "restricted"

Nếu không thỏa: DENY
~~~

Đây là pseudocode mô tả chính sách. `principal.region` phải được lấy từ nguồn tin cậy theo hợp đồng mapping, `customer.region` lấy từ dữ liệu nghiệp vụ được bảo vệ; **không dùng thông tin region do browser tự khai báo để ra quyết định**.

### 8.3. Quyền qua nhiều nguồn

Một người có thể nhận role CRM từ group federation, SCIM provisioning, local admin hoặc direct assignment. Khi gỡ một group nguồn, local grant vẫn có thể giữ quyền. IAM cần xác định **entitlement provenance**: mỗi quyền đã được cấp qua con đường nào, hiện có hợp lệ không và thao tác thu hồi phải gửi đến đâu.

### 8.4. Tách role quản trị với role người dùng

Quyền quản trị IdP, quản trị federation connection và quyền nghiệp vụ trong CRM là ba nhóm khác nhau. Một người có `crm.support-agent` **không** mặc nhiên được sửa SAML certificate, OIDC client configuration hoặc mapping policy. Đối với mapping quản trị, có thể cần phê duyệt, PAM/JIT, xác thực mạnh và kiểm toán thay đổi.

## 9. Federation mapping với SCIM và JIT provisioning

Có hai cách thường gặp để ứng dụng đích có account đúng lúc.

### 9.1. SCIM provisioning trước khi đăng nhập

Hệ thống IAM dựa trên nguồn nhân sự, group và approval để gửi lệnh tạo account cho SaaS. SCIM có thể đồng bộ User, Group và membership theo khả năng provider.

Ưu điểm: account có thể sẵn sàng trước ngày làm việc; trạng thái Leaver có thể được cập nhật ngay khi có sự kiện, không phụ thuộc lần đăng nhập tiếp theo.

Cần duy trì mapping nhất quán giữa:

| Trường trong mô hình IAM | Trường/thực thể SCIM đích | Chức năng |
|---|---|---|
| Identity ID nguồn | `externalId` theo hợp đồng tích hợp | Liên kết ngược với nguồn quản trị |
| Account ID đích | `id` do SCIM provider cấp | Định danh đối tượng ở ứng dụng đích |
| Tên/email | `userName`, `emails` nếu phù hợp | Đăng nhập/hiển thị theo sản phẩm |
| Trạng thái vòng đời | `active` nếu provider hỗ trợ đúng ngữ nghĩa | Điều chỉnh khả năng sử dụng tài khoản |
| Group membership | `Groups` / `members` | Điều phối membership theo phạm vi hỗ trợ |

`externalId` có ý nghĩa do **client provisioning** cung cấp và quản lý theo thỏa thuận; nó không mặc nhiên là `sub` của OIDC. `id` do SCIM provider gán không nhất thiết trùng `localAccountId` trong ứng dụng khác.

### 9.2. JIT provisioning khi SSO lần đầu

Một số SP/RP cho phép **Just-In-Time (JIT) provisioning**: khi một assertion hợp lệ của chủ thể chưa có account đến, ứng dụng có thể tạo account.

Điều kiện cần cân nhắc:

- Chỉ issuer/tenant được phê duyệt mới được tạo user.
- Định danh được ánh xạ an toàn; không tự link theo email chưa đủ bằng chứng.
- Có chính sách quyết định ai được phép JIT vào ứng dụng.
- Role mặc định là **quyền tối thiểu**, không phải admin.
- Có cơ chế deprovision độc lập cho người không còn đăng nhập; không dựa vào “lần login cuối” để tự xóa.
- Xử lý account trùng, migration và owner của dữ liệu.
- Sau khi tạo, ghi account ID đích và correlation để đối soát.

**JIT account creation không thay thế vòng đời Leaver.** Nếu một user không bao giờ đăng nhập lại, ứng dụng vẫn phải có cách vô hiệu hóa account khi hợp đồng hoặc việc làm đã kết thúc.

### 9.3. Khi SCIM và JIT cùng tồn tại

Có thể xảy ra đua trạng thái: SCIM tạo account trước, JIT nhìn chưa thấy và tạo bản thứ hai; hoặc JIT gắn account không đúng người trước khi SCIM đồng bộ. Nên định nghĩa rõ **nguồn quản lý account**, ID linking, quy tắc tránh trùng và thứ tự thay đổi. Chỉ một kênh có quyền tự động cấp role nhạy cảm nếu chưa có cơ chế hòa giải đáng tin.

## 10. Mapping ngữ cảnh xác thực cho MFA và step-up

Federation có thể mang thông tin về sự kiện xác thực để ứng dụng quyết định có yêu cầu thêm MFA hoặc tái xác thực.

Trong OIDC, một số triển khai có thể dùng:

- `auth_time`: lần xác thực user diễn ra khi nào.
- `acr`: lớp/ngữ cảnh xác thực do issuer định nghĩa.
- `amr`: tham chiếu phương thức xác thực đã thực hiện, theo hợp đồng issuer.

Trong SAML, các phần tử liên quan Authentication Context và AuthenticationStatement có thể cung cấp dữ liệu phục vụ chính sách của SP.

**Không có phép so sánh phổ quát “`acr=2` nghĩa là MFA mạnh” cho mọi IdP.** Cần có bảng mapping **issuer-specific** do owner bảo mật phê duyệt.

Ví dụ:

| Ngữ cảnh được IdP xác minh | Cách diễn giải theo hợp đồng nội bộ | Quyết định có thể áp dụng |
|---|---|---|
| Đăng nhập mới bằng phương thức cơ sở | Phù hợp chức năng ít nhạy cảm | Cho xem tin tức nội bộ |
| Đã dùng phương thức đáp ứng policy `crm-standard` | Đủ yêu cầu CRM thông thường | Cân nhắc cho xem hồ sơ nếu user có role |
| Đã dùng phương thức chống phishing và còn đủ mới | Phù hợp chính sách nhạy cảm hơn | Xét tiếp role/SoD trước khi duyệt |
| Claim thiếu hoặc không ánh xạ được | Chưa có bằng chứng assurance theo policy | Step-up hoặc từ chối theo rủi ro |

MFA/step-up là **điều kiện xác thực**, không tạo quyền kinh doanh. Người vượt qua MFA vẫn có thể không được phép xuất dữ liệu khách hàng nếu không có `crm.export-approver`.

## 11. Joiner–Mover–Leaver trong Federation mapping

Federation mapping không nên là cấu hình “làm một lần rồi để mãi”. Quan hệ liên kết danh tính, role, attribute và trust cũng có vòng đời.

### 11.1. Joiner: tạo liên kết định danh ban đầu

Khi Lan gia nhập tổ chức:

1. HRIS hoặc nguồn có thẩm quyền xác minh danh tính và ngày hiệu lực.
2. IdP tạo account và cung cấp một **subject ID ổn định** phù hợp chính sách.
3. IAM xác định Lan cần các ứng dụng nào; chủ ứng dụng duyệt role nhạy cảm.
4. SP/RP nhận federation assertion/token qua kết nối đã được cấu hình trust.
5. Hệ thống liên kết `(issuer, subject)` với account đích đã được chuẩn bị qua SCIM hoặc tạo JIT hợp lệ.
6. Mapping attributes và group/role được tính theo policy và thời điểm hiệu lực.
7. Readback account, membership và chức năng thực tế; không chỉ nhìn màn hình login thành công.
8. Ghi event ID, mapping policy version và kết quả đối soát.

**Lỗi Joiner:** user mới có cùng email với người đã nghỉ và ứng dụng tự link vào account cũ còn nhiều quyền. Cách phòng tránh là liên kết theo ID ổn định, xử lý tái sử dụng email và yêu cầu quy trình xác minh khi migration.

### 11.2. Mover: đổi thuộc tính và quyền, giữ đúng identity

Lan chuyển từ Hà Nội sang Đà Nẵng. Subject ID thông thường vẫn giữ nguyên nếu không thay miền/issuer; thuộc tính `region` và group/role cần đổi:

~~~text
Trước:
  subject   = (issuer-A, sub-Lan)
  region    = HN
  app role  = crm.support-agent@HN

Sau:
  subject   = (issuer-A, sub-Lan)  [giữ liên kết]
  region    = DN
  app role  = crm.support-agent@DN

Phải thu hồi:
  crm.support-agent@HN
~~~

Nếu ứng dụng chỉ thêm role mới, Lan có thể truy cập cả hai chi nhánh. Đây là **quyền truy cập tồn dư**. Cần đối soát group trực tiếp, nhóm lồng nhau, role local, SCIM mapping và các session/token có thuộc tính cũ.

Không nên đổi account link chỉ vì thuộc tính email, display name hoặc department thay đổi. Những thuộc tính này là **dữ liệu có thể cập nhật**, không phải bằng chứng người khác đã trở thành chủ tài khoản.

### 11.3. Leaver: ngừng trust đối với một subject cụ thể

Khi Lan nghỉ:

- IdP chặn đăng nhập mới tại thời điểm hợp lệ.
- IAM/SCIM/API vô hiệu hóa account đích và thu hồi quyền/group theo chính sách.
- SP/RP xử lý session cũ, token, local login và credential độc lập theo khả năng.
- Mapping liên kết danh tính được lưu/đánh dấu theo chính sách kiểm toán; không nên tự tái kích hoạt từ assertion trễ.
- Đối soát rằng quyền nhạy cảm tại tài nguyên không còn hiệu lực.
- Nếu Lan sở hữu ứng dụng/workload, chuyển giao owner của principal còn cần hoạt động và thu hồi quyền cá nhân riêng.

**Xóa federated link chưa chắc chặn được một session đã phát hành**, và vô hiệu hóa tại IdP chưa chắc gỡ quyền local ở tất cả ứng dụng. Leaver cần kiểm soát cả authentication, authorization và credential.

## 12. Mapping trong tổ chức nhiều IdP hoặc B2B federation

Khi doanh nghiệp A cho nhân viên của đối tác B vào một portal chung, ranh giới tin cậy cần rõ ràng.

~~~mermaid
flowchart LR
    B[Nhân viên đối tác B] --> IDPB[IdP đối tác B]
    IDPB -->|Assertion/token theo kết nối đã duyệt| RP[Partner Portal của A]
    R[Registry issuer / policy / account linking] --> RP
    RP --> MAP[Mapping thuộc tính và role]
    MAP --> AUTHZ[Authorization theo tenant và tài nguyên]
    AUTHZ --> DATA[(Dữ liệu thuộc phạm vi được chia sẻ)]
~~~

### 12.1. Ràng buộc theo issuer/tenant

Không nên dùng chính sách “bất kỳ ai thuộc nhà cung cấp IdP X đều vào được portal A”. Cần xác định **tenant cụ thể hoặc nguồn issuer đáng tin**, audience chính xác, nhóm người dùng được phép và quá trình phê duyệt.

Một group ID có ý nghĩa ở tenant A không mặc nhiên có cùng ý nghĩa ở tenant B. Nếu đối tác tự quản lý group `admins`, ứng dụng nội bộ A không được tự map nó thành quyền quản trị trong A.

### 12.2. Entitlement cho đối tác là quyền nội bộ được phê duyệt

Ví dụ, IdP B xác nhận nhân viên B đang ở group `partner-sales`. Doanh nghiệp A nên dùng policy riêng quyết định người đó được vào mục nào trong partner portal, thay vì tin đối tác được tự quyết mọi role nội bộ.

Một bảng có thể chỉ cho phép:

- Issuer B thuộc danh sách đối tác đã ký hợp đồng.
- Subject B đã được mời/cho phép vào portal, liên kết với đối tượng partner được phê duyệt.
- Chỉ role `partner.quote-reader` với tài nguyên gắn `partnerId=B`.
- Quyền xuất dữ liệu hoặc thay đổi hợp đồng phải duyệt riêng bên A.

### 12.3. Khi đối tác kết thúc hợp đồng

Bên A cần **Leaver của quan hệ hợp tác**: ngừng issuer trust hoặc rút quyền theo đối tác, vô hiệu hóa account/guest, chấm dứt phiên/token, thu hồi API grant và đối soát dữ liệu được chia sẻ. Không nên chỉ chờ IdP B tự khóa nhân viên của họ.

## 13. Quy trình mapping end-to-end

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant RP as Ứng dụng / RP
    participant I as IdP
    participant M as Federation mapping service
    participant D as Account & entitlement store
    participant A as Resource API
    U->>RP: Yêu cầu đăng nhập
    RP->>I: Bắt đầu flow federation
    I->>U: Xác thực theo chính sách
    I-->>RP: Kết quả theo SAML/OIDC
    RP->>RP: Kiểm tra chữ ký/issuer/audience/thời hạn/flow
    RP->>M: Claims/assertion đã xác minh
    M->>M: Kiểm tra issuer policy + chuẩn hóa dữ liệu
    M->>D: Tra account bằng định danh ổn định
    D-->>M: Account, trạng thái, entitlements
    M-->>RP: Principal nội bộ + auth context tin cậy
    RP->>A: Request kèm cơ chế access phù hợp
    A->>A: Kiểm tra role, tenant, policy, resource
    A-->>RP: ALLOW hoặc DENY
~~~

Sơ đồ là mô hình logic, không quy định RP phải gọi một dịch vụ mapping độc lập hoặc chuyển claims sang API qua một kênh tùy tiện. Một ứng dụng có thể tích hợp mapping ngay trong bộ xử lý SAML/OIDC. **API không nên tin một header client tự khai báo `role=admin`**; identity và auth context cần đến từ trust boundary được bảo vệ.

## 14. Ví dụ thiết kế policy mapping cho CRM

### 14.1. Yêu cầu

Công ty có hai tenant/issuer:

- `issuer-corp`: IdP nội bộ cho nhân viên.
- `issuer-partner`: IdP được phê duyệt cho đối tác.

Ứng dụng CRM cần:

- Nhân viên hỗ trợ ở Hà Nội: xem/sửa ticket tại Hà Nội.
- Nhân viên hỗ trợ ở Đà Nẵng: xem/sửa ticket tại Đà Nẵng.
- Đối tác: chỉ xem báo cáo đã được chia sẻ cho partner của mình.
- Không gán quyền admin từ group do đối tác tự đặt tên.
- Không tự liên kết account theo email chưa đủ xác minh.
- Người nghỉ việc/đối tác ngừng hợp tác không được giữ quyền.

### 14.2. Cấu hình minh họa (không phụ thuộc sản phẩm)

~~~yaml
federationPolicyVersion: "2026-11-v1"
trustedIssuers:
  - id: issuer-corp
    issuer: "https://login.corp.example/tenant-001"
    subjects: "issuer-plus-sub"
    jitProvisioning: "approved-users-only"
    defaultRole: "none"
    groupMappings:
      - sourceGroupId: "grp-support-hn"
        targetRole: "crm.support-agent"
        targetRegion: "HN"
      - sourceGroupId: "grp-support-dn"
        targetRole: "crm.support-agent"
        targetRegion: "DN"
  - id: issuer-partner
    issuer: "https://login.partner.example/tenant-802"
    subjects: "issuer-plus-sub"
    jitProvisioning: "invited-subjects-only"
    defaultRole: "none"
    approvedRoleMappings:
      - sourceGroupId: "grp-partner-read"
        targetRole: "crm.partner-reader"
        scopeFrom: "approved-partner-assignment"
onMissingSubject: "DENY"
onUnknownGroup: "NO_ROLE"
onUnverifiedAccountLink: "DENY"
onInactiveIdentity: "DENY"
onInsufficientAuthentication: "STEP_UP_OR_DENY"
audit:
  recordPolicyVersion: true
  requireTargetReadbackForPrivilegeChanges: true
~~~

Mẫu YAML trên chỉ diễn đạt thiết kế và **không phải schema chính thức** của IdP/SP nào. Dù có cùng tên `sourceGroupId` giữa các issuer, ý nghĩa phải được **namespace theo issuer/tenant**.

### 14.3. Pseudocode ánh xạ và phân quyền

~~~text
function resolveFederatedPrincipal(tokenOrAssertion):
    proof = validateUsingConfiguredProtocolAndTrust(tokenOrAssertion)

    if not proof.valid:
        return DENY

    issuer = findExplicitlyTrustedIssuer(proof.issuer)
    if issuer is NONE:
        return DENY

    key = (issuer.id, proof.stableSubject)
    account = lookupLocalAccountByFederatedKey(key)

    if account is NONE:
        if not approvedJitPolicyAllows(issuer, proof):
            return DENY
        account = createMinimalAccountAfterLinkingChecks(key)

    if account.status != ACTIVE:
        return DENY

    roles = resolveOnlyApprovedRoleMappings(
        issuer.id,
        proof.trustedGroupIds,
        account.approvals,
        currentPolicyVersion
    )

    return TrustedPrincipal(
        accountId = account.id,
        issuerId = issuer.id,
        roles = roles,
        authenticationContext = validateAuthContext(proof)
    )

function authorizeReadCustomer(principal, customer):
    if not principal.roles.canReadCustomer:
        return DENY

    if customer.tenantId != principal.allowedTenantId:
        return DENY

    if customer.region not in principal.allowedRegions:
        return DENY

    return ALLOW
~~~

Đây là **pseudocode giải thích thứ tự kiểm soát**, không phải một thư viện có thể dùng trực tiếp. Trong hệ thống thực, `validateUsingConfiguredProtocolAndTrust` phải tuân thủ giao thức và profile cụ thể; `createMinimalAccountAfterLinkingChecks` phải giải quyết va chạm, xác minh owner và chống tạo trùng; `roles` không được lấy trực tiếp từ dữ liệu client tự khai.

## 15. Rủi ro bảo mật và lỗi mapping thường gặp

| Lỗi | Biểu hiện | Hậu quả | Kiểm soát |
|---|---|---|---|
| **Sai issuer** | Nhận token từ tenant không được phê duyệt | Người ngoài đăng nhập như nội bộ | Allowlist issuer/tenant và xác minh chữ ký, audience |
| **Ghép theo email** | Liên kết local account chỉ bằng email trùng | Account takeover khi email tái sử dụng | Khóa ổn định (issuer, subject), workflow linking có xác minh |
| **Sai audience** | Token dành cho ứng dụng khác được chấp nhận | Token substitution / cross-app access | Kiểm tra audience chính xác |
| **Bỏ kiểm tra chữ ký** | Parser đọc claim từ input tùy ý | Tự khai group hoặc admin | Dùng thư viện giao thức đáng tin, fail closed |
| **Group tên chung** | Group `admin` bất kỳ → role admin | Privilege escalation | Map theo issuer+group ID, phê duyệt riêng quyền cao |
| **Mất thuộc tính** | `region` vắng nhưng app tự cho `ALL` | Mở rộng quyền dữ liệu | Không tự cấp quyền khi claim thiếu |
| **SCIM và JIT lệch ID** | Một người có hai account tại SaaS | Thu hồi sai account hoặc quyền tồn dư | Correlation ID, stable linking và reconciliation |
| **Group membership lỗi thời** | Mover đã đổi phòng ban nhưng token vẫn chứa role cũ | Truy cập chi nhánh cũ | Token/session policy, đồng bộ và kiểm tra quyền ở API |
| **Claim bị cắt/truncated** | IdP không gửi toàn bộ groups | Thiếu quyền hoặc đánh giá sai | Theo hợp đồng claim overage và API tin cậy |
| **Migration issuer thiếu kế hoạch** | Đổi `iss`/`sub` làm mất liên kết cũ | Mất account hoặc link nhầm | Migration có phê duyệt, bảng ánh xạ, kiểm chứng |
| **Tin user-supplied metadata** | Client tự gửi `role` hoặc `tenant` | Bypass authorization | Chỉ đọc nguồn đã xác minh/nguồn chính sách tin cậy |
| **Quên Leaver phía SP** | IdP khóa user nhưng SaaS còn session | Quyền truy cập tồn dư | SCIM/API deprovision, revoke session, readback |

### 15.1. Chống đặc quyền leo thang qua mapping

Quyền quản trị thường yêu cầu xác minh sự cần thiết và phê duyệt riêng. Một chính sách **default deny/no role** với issuer chưa được đăng ký, group không ánh xạ hoặc account chưa liên kết an toàn sẽ an toàn hơn việc tự gán một role rộng để “người dùng không bị lỗi”.

Nếu mapping thất bại do dữ liệu thiếu, nên trả trạng thái cần xử lý thay vì cấp tạm quyền admin.

### 15.2. Phòng lỗi do dữ liệu chuyển qua nhiều miền tin cậy

Một thuộc tính có thể đi từ HRIS → IdP → assertion → ứng dụng → cache/API. Mỗi nơi có thể có độ trễ. Nên xác định:

- Ai có quyền tạo/sửa thuộc tính gốc?
- Thuộc tính được làm mới khi nào?
- App có tự lưu role tại local DB không?
- Khi Leaver, kênh nào chặn quyền nếu phiên cũ vẫn còn?
- Với quyền cao, có thể buộc kiểm tra lại account/entitlement gần thời gian yêu cầu không?

### 15.3. Chú ý privacy và giảm dữ liệu chia sẻ

Không nên phát mọi thuộc tính nhân sự, ngày sinh hoặc thông tin nhạy cảm cho mọi RP chỉ vì IdP có sẵn dữ liệu. Chỉ gửi claims cần cho đăng nhập và chức năng được phê duyệt, theo hợp đồng, mục đích và yêu cầu bảo vệ dữ liệu.

## 16. Thay đổi mapping và migration an toàn

Mapping có thể thay đổi khi doanh nghiệp:

- Chuyển sang IdP mới hoặc đổi tenant.
- Đổi hệ thống HRIS, mã phòng ban hoặc nguồn group.
- Thay ứng dụng SaaS hoặc nâng cấp connector SCIM.
- Tái cấu trúc tổ chức, đổi chi nhánh hoặc ghép hai công ty.
- Đổi SAML attribute name hoặc OIDC claim format.
- Tách quyền quản trị ra khỏi nhóm người dùng rộng.

### 16.1. Chu trình thay đổi

1. **Phân tích hợp đồng hiện tại:** issuer, audience, subject format, attribute sources, role mapping và danh sách ứng dụng chịu tác động.
2. **Liệt kê tài khoản liên kết:** xác định mapping đang dùng, quyền cấp trực tiếp và nhóm lồng nhau.
3. **Đánh giá rủi ro:** account collision, đổi issuer/sub, quyền admin, tenant isolation và token còn hiệu lực.
4. **Thiết kế mapping mới:** phiên bản rõ ràng, owner và người phê duyệt; xác định hành vi khi claim thiếu.
5. **Thử nghiệm ở môi trường phù hợp:** dùng tài khoản mẫu, cả tình huống hợp lệ lẫn tấn công/điều kiện xấu.
6. **Triển khai có kiểm soát:** canary, giám sát tỷ lệ lỗi, tùy hệ thống có giai đoạn tương thích hẹp được phê duyệt.
7. **Readback và đối soát:** xác minh liên kết account, role/permissions, session và hành vi tại API đích.
8. **Thu hồi trust cũ:** không giữ issuer, signing key, role mapping hoặc connector không còn cần.
9. **Lưu audit:** quyết định, thời điểm, policy version và bằng chứng migration.

Không có lý do để cho phép **hai issuer cùng tự cấp quyền quản trị** vô thời hạn chỉ để tránh rủi ro chuyển đổi. Giai đoạn chồng lấn phải có thời hạn và đối soát.

### 16.2. Key rotation khác account migration

Khi IdP thay **khóa ký token/assertion**, issuer/subject có thể giữ nguyên. Đây là thay đổi **trust material**, không mặc nhiên cần gắn lại toàn bộ account. Nếu triển khai metadata/JWKS rollover, phải xác minh các khóa hợp lệ theo nguồn tin cậy và kế hoạch khóa cũ hết hiệu lực.

Nếu issuer hoặc subject format thực sự thay đổi, mới cần đánh giá **identity relinking/migration** với bằng chứng riêng. Không tự tạo một user mới hoặc gộp account chỉ vì khóa ký đã đổi.

## 17. Kiểm toán và đối soát Federation mapping

Một hệ thống IAM cần có khả năng trả lời **“vì sao danh tính này được liên kết và có quyền ở ứng dụng kia?”**.

### 17.1. Bản ghi hữu ích nên chứa

- Định danh trust connection và **issuer ID** đã được chấp nhận.
- Subject ID được liên kết hoặc ID nội bộ đã được che/giảm dữ liệu theo chính sách.
- Local account ID và trạng thái account tại SP/RP.
- Mapping policy version, các rule đã khớp, nhóm/thuộc tính nguồn được dùng.
- Quyền/role được gán, phạm vi tài nguyên và người phê duyệt.
- Kết quả validate giao thức, authentication context và bước step-up nếu cần.
- Thời điểm áp dụng, correlation ID, trạng thái provisioning và readback.
- JML event, thao tác revoke/unlink và các phiên/token cần xử lý.
- Ngoại lệ, thời hạn và người chịu trách nhiệm.

Không lưu nguyên ID token, SAML assertion, access token, private key, secret hoặc thông tin nhân sự dư thừa vào log chỉ để giúp debug mapping.

### 17.2. Ví dụ audit record

~~~json
{
  "eventId": "fed-map-2026-0008",
  "trustConnectionId": "corp-idp-crm",
  "issuerId": "issuer-corp",
  "federatedSubjectRef": "subject-ref-79ac",
  "targetAccountId": "crm-user-2048",
  "mappingPolicyVersion": "2026-11-v1",
  "eventType": "ENTITLEMENT_RECALCULATED",
  "roleBefore": ["crm.support-agent@HN"],
  "roleAfter": ["crm.support-agent@DN"],
  "reason": "MOVER_REGION_CHANGE",
  "executionStatus": "SUCCESS",
  "targetVerification": "PENDING_READBACK",
  "correlationId": "IAM-MOVER-0108"
}
~~~

Đây là schema minh họa. `executionStatus=SUCCESS` **không được tự suy ra** `targetVerification=CONFIRMED` nếu chưa có bằng chứng quyền thực tế tại CRM đã đổi.

### 17.3. Các chỉ số theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| Số account không liên kết được với subject có thẩm quyền | Rủi ro account mồ côi hoặc sai mapping |
| Số lần login bị chặn do issuer/audience/subject sai | Tín hiệu lỗi cấu hình hoặc tấn công |
| Tỷ lệ role mapping có owner và phiên bản chính sách | Mức độ quản trị và khả năng truy vết |
| Số role nhạy cảm được cấp qua mapping không có approval | Nguy cơ cấp quyền quá rộng |
| Tỷ lệ JML được đối soát tại SP/RP | Mức thực thi thay đổi/thu hồi quyền thực tế |
| Thời gian từ Mover/Leaver đến khi quyền đích được xác minh | Độ trễ quyền tồn dư |
| Số link trùng account hoặc account trùng subject | Nguy cơ sai liên kết |
| Số trust connection và mapping không còn owner/mục đích | Bề mặt tấn công tồn dư |

Chỉ số phải có định nghĩa về mẫu số, phạm vi ứng dụng và giới hạn dữ liệu. Chỉ có số lần SSO thành công không chứng minh hệ thống mapping đã an toàn.

## 18. Kịch bản kiểm thử và chẩn đoán lỗi

### 18.1. Bộ tình huống cần kiểm thử

| Tình huống | Kỳ vọng |
|---|---|
| Token/assertion hợp lệ, subject đã liên kết và account active | Đăng nhập theo quyền được phê duyệt |
| Token có chữ ký hợp lệ nhưng từ issuer lạ | Từ chối |
| Token đúng issuer nhưng sai audience | Từ chối |
| Subject khác nhưng email trùng một account admin hiện có | Không tự link vào admin; yêu cầu quy trình hợp lệ |
| Group không nằm trong mapping | Không tự cấp role từ group lạ |
| Group đối tác có tên `admin` | Không map thành quyền admin nội bộ |
| Claim region thiếu/sai định dạng | Không cấp quyền trên mọi region |
| Mover đổi region HN → DN | Gỡ HN, cấp DN, kiểm tra quyền tại resource API |
| Leaver vô hiệu hóa account | Ngăn login mới, xử lý session/token/quyền theo policy |
| SCIM tạo account trước JIT | Không tạo bản ghi trùng |
| Migration đổi issuer/sub có phê duyệt | Liên kết đúng account, không gộp nhầm |
| Token cũ sau khi role bị gỡ | API thực thi theo chính sách thu hồi/giới hạn phiên |
| Nhóm lồng nhau hoặc token thiếu groups | Xử lý đúng theo hợp đồng nguồn, không suy đoán quyền |
| Authentication context không đạt yêu cầu | Step-up hoặc DENY cho hành động nhạy cảm |
| Application principal dùng token app-only | Không tự diễn giải là user có quyền |

### 18.2. Chẩn đoán đăng nhập thành công nhưng thiếu quyền

Khi người dùng đăng nhập SSO được nhưng không truy cập được CRM:

1. Xác minh subject đã link với account đích nào.
2. Xác minh account có active, đúng tenant và thuộc phạm vi ứng dụng.
3. Xác minh các group/attributes được phát có đúng theo hợp đồng không.
4. Kiểm tra mapping policy version và role có được cấp đúng không.
5. Kiểm tra SCIM/role local/direct grant và trạng thái đích.
6. Kiểm tra resource-level policy, không chỉ trang giao diện.
7. Kiểm tra token/session có đang giữ claim cũ hay không.
8. Ghi nguyên nhân bằng ID/correlation, tránh log token thô.

### 18.3. Chẩn đoán người đã nghỉ vẫn truy cập được

Không chỉ xem kết quả IdP. Cần xác định liệu user còn:

- Account tại SP/RP đang active hoặc local password.
- Session, access token hoặc refresh token còn hiệu lực.
- Role/direct grant qua kênh không do federation quản lý.
- Service account/API key từng được cá nhân đó sở hữu.
- Liên kết federation/JIT có thể kích hoạt lại account dù Leaver đã chặn.

Từng đường cần được thu hồi/kiểm chứng, ghi tình trạng `PARTIAL` hoặc `ESCALATED` nếu chưa thể kết thúc.

## 19. Các hiểu lầm phổ biến

**“SAML/OIDC có chữ ký hợp lệ thì user được phép vào mọi tính năng.”** Sai. Chữ ký giúp xác minh nguồn/thông điệp theo chính sách, còn authorization là quyết định riêng.

**“Email giống nhau nghĩa là cùng một identity.”** Sai. Email có thể đổi/tái sử dụng; cần issuer+subject và quy trình linking đáng tin.

**“Tên group `admins` ở đối tác tương đương admin nội bộ.”** Sai. Role mapping phải giới hạn issuer/tenant, ID nhóm và phê duyệt.

**“SCIM đã tạo account nên không cần federation linking.”** Sai. Account ID đích và subject từ assertion cần tương quan an toàn; tránh tạo trùng hoặc chiếm tài khoản.

**“JIT login giúp tự động xử lý Leaver.”** Sai. User không còn đăng nhập có thể vẫn giữ account và phiên; cần deprovisioning có sự kiện.

**“Đổi issuer thì có thể tự lấy email để nối lại account.”** Nguy hiểm. Migration identity cần proof, mapping và kiểm thử chống liên kết nhầm.

**“MFA được IdP xác nhận thì API không cần RBAC/ABAC.”** Sai. MFA là điều kiện authentication; quyền trên tài nguyên vẫn phải kiểm tra.

**“Gỡ group IdP là đủ để chắc quyền đã biến mất ở SaaS.”** Chưa chắc. Quyền local và token/session có thể còn; phải đối soát effective access.

**“Quyền đối tác có thể để họ tự quyết bằng claim tự đặt.”** Không nên. Doanh nghiệp nhận chịu trách nhiệm giới hạn tài nguyên và quyền trong miền của mình.

## 20. Tình huống luyện tập

### Tình huống A: một người, hai subject

Cùng nhân viên Mai, nhưng ứng dụng quản lý dự án và CRM thấy hai `sub` khác nhau từ cùng IdP do cấu hình pairwise subjects. Quản trị viên muốn ép chúng giống nhau.

**Phân tích:** Không nên tự sửa các giá trị `sub` hoặc gộp bằng email. Thiết kế account linking riêng theo issuer+subject của từng RP; dùng ID doanh nghiệp có thẩm quyền và quy trình mapping được phê duyệt nếu cần đối soát cross-app.

### Tình huống B: group đối tác làm admin

IdP đối tác gửi claim `groups=["admin"]`. Ứng dụng đang có rule `if group == "admin" → superadmin`.

**Phân tích:** Đây là privilege escalation qua mapping. Chặn rule, dùng issuer-scoped group ID và mapping được owner phê duyệt; role quản trị nội bộ không được cấp từ một group ngoài không có căn cứ.

### Tình huống C: email tái sử dụng

Nhân viên cũ nghỉ việc, email `sales1@company.example` được cấp lại cho người mới. SaaS tự tìm account bằng email và cho người mới đăng nhập vào tài khoản cũ.

**Phân tích:** Đây là account-linking takeover/rò rỉ dữ liệu tiềm tàng. Dùng subject ổn định, tránh tự link theo email; vô hiệu hóa liên kết cũ theo Leaver và tạo account/link mới đúng chủ thể.

### Tình huống D: Mover còn quyền khu vực cũ

An chuyển từ Hà Nội sang Đà Nẵng. OIDC claim region mới là `DN`, nhưng SaaS vẫn có role `crm.support-agent@HN`.

**Phân tích:** Federation claim đã thay đổi nhưng provisioning/role local chưa đồng bộ hoặc session còn trạng thái cũ. Cần thu hồi quyền HN và kiểm tra API chặn dữ liệu HN; nếu có cửa sổ bàn giao thì phải có approval và thời hạn.

### Tình huống E: ID token bị dùng gọi API

Một lập trình viên dùng ID token cấp cho web client để gọi Resource API vì “token có chữ ký của IdP”.

**Phân tích:** API phải yêu cầu access token có audience/scope/role thích hợp. ID token không mặc nhiên là token ủy quyền API.

### Tình huống F: Leaver của đối tác

Đối tác ngừng hợp đồng, nhưng account guest ở portal A vẫn active dù IdP B đã khóa một nhân viên.

**Phân tích:** Bên A cần xử lý Leaver theo quan hệ hợp tác, thu hồi trust/guest account và quyền, kiểm tra phiên/token và API grants; không chỉ dựa vào IdP B.

## 21. Checklist thiết kế Federation mapping

Trước khi đưa một trust connection và mapping vào production, cần trả lời:

1. **Trust boundary:** IdP/issuer/tenant nào được chấp nhận, cho ứng dụng/client nào và trong thời hạn nào?
2. **Protocol validation:** token/assertion có được kiểm tra chữ ký, issuer, audience, thời hạn và ràng buộc flow đúng cách?
3. **Subject key:** account linking có dùng ID ổn định kèm namespace issuer không?
4. **Account linking:** JIT/SCIM có chống account trùng và không tự link chỉ bằng email không?
5. **Nguồn thuộc tính:** department/region/group có xuất phát từ nguồn có thẩm quyền và được kiểm soát không?
6. **Mapping rule:** bảng chuyển claim/group ID → role/scope có owner, version và approval?
7. **Default behavior:** claim thiếu, group lạ hoặc issuer không hợp lệ có được xử lý an toàn không?
8. **RBAC/ABAC:** API có kiểm tra quyền ở mức tài nguyên, tenant, hành động và SoD không?
9. **Authentication context:** IdP có cung cấp thông tin đủ tin cậy cho MFA/step-up, và ứng dụng có hiểu đúng theo hợp đồng không?
10. **SCIM/JIT:** provisioning account/role theo cơ chế nào, có nguồn quản lý rõ và readback trạng thái không?
11. **Joiner:** user mới có account liên kết đúng, quyền tối thiểu và đủ điều kiện theo ngày hiệu lực?
12. **Mover:** thuộc tính/group mới được cập nhật, quyền cũ không còn hợp lệ được thu hồi?
13. **Leaver:** account, role, local login, token/session và trust liên quan có được xử lý/kiểm chứng?
14. **Multiple IdPs/B2B:** không cho đối tác tự map claim tùy ý thành đặc quyền nội bộ?
15. **Workload:** application-only principal có mapping khác user delegated và không nhận nhầm user role?
16. **Migration:** issuer/sub, cert/key, claim names thay đổi có kế hoạch, test và rollback an toàn?
17. **Audit:** có truy được trust source, mapping version, link, grant/revoke, approval và kết quả đích?
18. **Giảm dữ liệu:** chỉ truyền các thuộc tính thật sự cần, không log token/assertion thô?
19. **Kiểm thử:** có negative tests về issuer lạ, audience sai, email trùng, claim thiếu, group giả?
20. **Readback:** trạng thái quyền hiệu lực thực tế đã được xác minh, không chỉ kết luận từ SSO thành công?

---

**Ghi nhớ:** **Federation mapping** là cầu nối giữa **bằng chứng danh tính từ một miền tin cậy** và **identity/account, thuộc tính, role và policy tại ứng dụng nhận**. Thiết kế an toàn phải kiểm tra giao thức trước khi tin claim, liên kết subject ổn định theo issuer, chỉ ánh xạ quyền qua policy có thẩm quyền và bảo vệ mặc định khi dữ liệu thiếu hoặc sai. Khi phối hợp với IdP, SSO, SCIM, RBAC/ABAC và quy trình **Joiner–Mover–Leaver**, IAM vừa hỗ trợ đăng nhập liên kết thuận tiện vừa phát hiện và thu hồi **quyền truy cập tồn dư** sau thay đổi vai trò hoặc chấm dứt quan hệ.
