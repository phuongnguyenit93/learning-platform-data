# Identity attribute — Thuộc tính danh tính

> **Chương:** Identity  
> **Chủ đề:** Identity attribute

**Identity attribute** (thuộc tính danh tính) là một dữ liệu mô tả một **chủ thể** (*subject/principal*) trong hệ thống định danh: tên hiển thị, địa chỉ email, số điện thoại, mã nhân viên, đơn vị công tác, trạng thái tài khoản, phương thức xác thực đã đăng ký hoặc thuộc tính của một thiết bị/dịch vụ. Thuộc tính có thể do chủ thể tự khai, do hệ thống cấp, được xác minh bởi một bên có thẩm quyền hoặc được suy ra từ dữ liệu khác. **Không phải mọi thuộc tính đều đúng, bất biến, duy nhất hay đáng tin như nhau.**

Trong hệ thống authentication, hiểu đúng thuộc tính danh tính giúp trả lời: “Đang xác thực **chủ thể nào**?”, “Email này đã được xác minh tới đâu?”, “Có thể tin thuộc tính do Identity Provider (IdP) trả về không?”, “Thuộc tính có đủ để cấp quyền không?”, “Điều gì xảy ra khi số điện thoại đổi chủ hoặc người dùng chuyển tổ chức?”. Bài này xây dựng mô hình dữ liệu và ranh giới tin cậy để sử dụng identity attribute an toàn cùng credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **identity**, **identifier**, **attribute**, **credential**, **claim** và **authorization**.
2. Phân loại thuộc tính theo ý nghĩa, độ ổn định, nguồn cấp, độ nhạy cảm và mức xác minh.
3. Mô hình hóa thuộc tính bằng **giá trị + nguồn + trạng thái xác minh + thời điểm + phạm vi**.
4. Thiết kế vòng đời thêm, đọc, sửa, xác minh, thu hồi và xóa thuộc tính.
5. Nhận diện rủi ro giả mạo thuộc tính, chiếm tài khoản, nhầm tenant, email tái cấp, claim cũ và liên kết nhầm tài khoản.
6. Sử dụng thuộc tính an toàn trong đăng nhập, SSO, token, kiểm tra quyền và khôi phục tài khoản.

## 2. Danh tính không đồng nghĩa với một trường dữ liệu

**Identity** là tập thông tin và quan hệ dùng để nhận biết một chủ thể trong một ngữ cảnh. Chủ thể có thể là người, tài khoản dịch vụ, ứng dụng, thiết bị hoặc workload. **Identifier** là giá trị dùng để tham chiếu tới chủ thể trong một phạm vi nhất định. **Identity attribute** mô tả những đặc điểm của chủ thể.

Ví dụ, hồ sơ người học có thể gồm:

| Trường | Vai trò | Điểm cần lưu ý |
| --- | --- | --- |
| **user_id = usr_8f2** | Định danh nội bộ do nền tảng cấp | Nên ổn định, không tái sử dụng; chỉ duy nhất trong phạm vi thiết kế |
| **display_name = Minh Anh** | Thuộc tính trình bày | Có thể trùng, đổi hoặc tự khai; không dùng làm khóa tài khoản |
| **email = minhanh@example.org** | Thuộc tính liên hệ, đôi khi dùng để đăng nhập | Có thể đổi chủ; phải tách khỏi định danh nội bộ |
| **email_verified = true** | Trạng thái xác minh email | Chỉ phản ánh quy trình xác minh vào một thời điểm |
| **school_id = school-72** | Quan hệ với tổ chức | Nguồn cấp phải đáng tin, có phạm vi và hiệu lực |
| **role = teacher** | Thuộc tính có thể dùng để phân quyền | Không tin giá trị client gửi; vẫn kiểm tra quyền ở API |
| **account_status = active** | Trạng thái tài khoản | Do thành phần quản lý danh tính cập nhật |

Một người có thể có nhiều tài khoản ở các hệ thống; một tài khoản có thể có nhiều email, credential và phiên; hai tài khoản có thể cùng tên hoặc từng dùng một email ở những thời điểm khác nhau. **Một email không luôn tương ứng duy nhất với một người hay một tài khoản.**

### 2.1. Sáu khái niệm cần tách

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Identity** | Chủ thể được hệ thống biểu diễn thế nào? | Hồ sơ người học trong tenant của trường |
| **Identifier** | Tham chiếu chính xác subject nào? | Internal user ID, cặp issuer + subject của IdP |
| **Attribute** | Subject có đặc điểm nào? | Email, phòng ban, trạng thái |
| **Credential / authenticator** | Subject chứng minh quyền kiểm soát danh tính bằng gì? | Mật khẩu, passkey, khóa riêng, TOTP |
| **Claim / assertion** | Một bên đang khẳng định điều gì về subject? | Email đã được xác minh theo tuyên bố của IdP |
| **Authorization** | Subject được làm gì với tài nguyên này? | Chấm bài trong lớp được phân công |

Một **claim** thường là cách chuyển thuộc tính giữa các hệ thống; nó chỉ đáng tin sau khi kiểm chứng bên phát hành, cách phát hành, phạm vi và **thẩm quyền đối với thuộc tính cụ thể**. **Authentication** kiểm tra bằng chứng kiểm soát danh tính; nó **không tự động** chứng minh mọi thuộc tính hồ sơ đúng và không cấp mọi quyền.

## 3. Phân loại identity attribute

Một thuộc tính có thể thuộc nhiều nhóm cùng lúc. Phân loại giúp xác định ai được cập nhật, mức xác minh và cách sử dụng.

### 3.1. Theo chức năng

| Nhóm | Ví dụ | Ứng dụng |
| --- | --- | --- |
| **Định danh** | Internal user ID, subject IdP, employee ID | Liên kết bản ghi và ánh xạ tài khoản |
| **Mô tả** | Tên hiển thị, ảnh đại diện, ngôn ngữ | Cá nhân hóa giao diện |
| **Liên hệ** | Email, điện thoại, địa chỉ | Thông báo, liên lạc, khôi phục |
| **Quan hệ/tổ chức** | Tenant, đơn vị, lớp học | Xác định phạm vi chính sách |
| **Trạng thái** | Active, suspended, deprovisioned | Giới hạn đăng nhập và thao tác |
| **Bảo mật/xác thực** | MFA đã đăng ký, lần xác thực lại gần nhất | Step-up và thay đổi credential |
| **Quyền/tư cách** | Vai trò, nhóm, entitlement | Đầu vào quyết định phân quyền |
| **Thiết bị/workload** | Device ID, service account, certificate subject | Danh tính thiết bị/dịch vụ |

### 3.2. Theo nguồn gốc và mức tin cậy

- **Self-asserted:** do người dùng khai, ví dụ tên hiển thị hoặc email chưa xác minh. Phù hợp hiển thị, không đủ cho quyết định quan trọng.
- **System-issued:** do hệ thống cấp/quản lý, ví dụ internal user ID, trạng thái tài khoản.
- **Verified:** đã đi qua quy trình kiểm tra **một thuộc tính cụ thể**; ví dụ quyền kiểm soát hộp thư tại lúc xác minh email.
- **Federated:** IdP, HR hoặc hệ thống đối tác chuyển tới qua OIDC/SAML/SCIM hoặc cơ chế tích hợp khác; cần xác minh nguồn và quyền hạn của nguồn.
- **Derived:** giá trị suy ra từ dữ liệu khác, ví dụ “đủ tuổi” từ ngày sinh; phải hiểu dữ liệu nguồn, công thức, thời điểm.

Thuộc tính “đã xác minh” không có nghĩa được bảo đảm tuyệt đối. Để diễn giải nó cần biết **ai xác minh, xác minh điều gì, bằng cách nào, khi nào và cho mục đích gì**. Một giá trị do người dùng gõ vào và cùng giá trị do HR có thẩm quyền cấp mang độ tin cậy khác nhau.

### 3.3. Theo độ ổn định và tính duy nhất

| Thuộc tính | Đặc tính thực tế | Có phù hợp làm khóa tài khoản lâu dài? |
| --- | --- | --- |
| Internal opaque ID | Thiết kế bất biến, không tái sử dụng | **Có**, trong phạm vi hệ thống cấp |
| Cặp issuer + subject của IdP | Định danh trong phạm vi issuer và chính sách subject | **Có**, nếu có hợp đồng ổn định/không tái cấp rõ ràng |
| Email | Có thể thay đổi, chia sẻ, thu hồi hoặc tái cấp | **Không** |
| Số điện thoại | Có thể chuyển mạng, đổi hoặc tái cấp | **Không** |
| Tên hiển thị | Dễ trùng, dễ thay đổi | **Không** |
| Mã nhân viên | Có thể tái sử dụng tùy tổ chức | Chỉ khi chính sách định danh bảo đảm |
| IP, user-agent | Dễ đổi, dùng chung, có thể bị giả mạo một phần | **Không**; chỉ là tín hiệu bối cảnh |

OIDC có thể cấp **pairwise subject identifier** khác nhau theo client/sector. Không được mặc định hai subject khác nhau luôn là hai người khác nhau, hoặc hai subject trùng nhau từ hai issuer là cùng một người. Khi liên kết tài khoản, thông thường phải dùng cặp **issuer + subject**, thêm tenant khi kiến trúc cần.

## 4. Mô hình hóa thuộc tính như một khẳng định có ngữ cảnh

Hệ thống nhỏ có thể lưu email, phone, name trực tiếp trong hồ sơ. Nhưng nếu thuộc tính được dùng cho đăng nhập, recovery, kiểm soát quyền hoặc audit, chỉ lưu chuỗi và boolean thường không đủ.

### 4.1. Mô hình dữ liệu minh họa

~~~json
{
  "subject_id": "usr_8f2",
  "tenant_id": "tenant_school_72",
  "attribute": "email",
  "value": "minhanh@example.org",
  "source": {
    "type": "self_asserted",
    "id": "user_profile"
  },
  "verification": {
    "status": "verified",
    "method": "email_link",
    "verified_at": "2026-05-10T09:00:00Z"
  },
  "updated_at": "2026-05-10T09:00:00Z",
  "purpose": ["notification", "account_recovery"]
}
~~~

Đây là **mô hình minh họa**, không phải định dạng chuẩn của một giao thức. Trường verification chỉ cho biết đã kiểm tra **quyền kiểm soát địa chỉ email**; không chứng minh tên pháp lý, quyền sở hữu tài khoản tổ chức hay mức xác thực MFA. Trường purpose diễn đạt các mục đích hệ thống cho phép sử dụng theo chính sách; không phải bằng chứng tự động.

Hệ thống lớn có thể thêm: thời hạn hiệu lực, phiên bản, thời gian quan sát, mã giao dịch xác minh, tác nhân cập nhật, nguồn authoritative, chính sách lưu trữ và lịch sử thu hồi. Không nhất thiết chứa tất cả ở cùng một bảng.

### 4.2. Năm chiều phải kiểm tra trước khi dùng

1. **Value:** giá trị hiện tại là gì, đúng kiểu/định dạng không?
2. **Provenance:** nguồn nào cung cấp, có quyền xác nhận loại dữ liệu này không?
3. **Verification:** đã chứng minh điều gì, vào thời điểm nào?
4. **Scope:** thuộc tính thuộc subject, issuer, tenant, hệ thống và nghiệp vụ nào?
5. **Freshness:** dữ liệu còn hiệu lực, đủ mới cho quyết định hiện tại không?

Ví dụ: IdP của trường trả **department = IT** có thể dùng để hiển thị phòng ban. Nhưng nếu IdP đó không có trách nhiệm cấp quyền **quản trị nền tảng**, ứng dụng không nên suy ra role admin. Ngay cả khi phòng ban đúng hôm qua, nhân viên có thể đã chuyển công tác hôm nay.

## 5. Vòng đời đăng ký và xác minh thuộc tính

Theo dõi một thuộc tính email:

~~~mermaid
stateDiagram-v2
    [*] --> Unverified: Người dùng khai báo
    Unverified --> Pending: Gửi thử thách xác minh
    Pending --> Verified: Chứng minh kiểm soát email
    Pending --> Unverified: Hết hạn hoặc hủy
    Verified --> ChangePending: Yêu cầu đổi email
    ChangePending --> Verified: Xác minh địa chỉ mới
    ChangePending --> Verified: Hủy đổi, giữ email cũ
    Verified --> Invalidated: Thu hồi/không còn tin cậy
    Invalidated --> Pending: Xác minh lại
~~~

Sơ đồ mô tả **trạng thái của thuộc tính**, khác với trạng thái tài khoản và phiên. Một tài khoản có thể hoạt động với email chưa xác minh nếu chính sách cho phép, nhưng không nên dùng email ấy làm kênh khôi phục tin cậy.

Luồng đăng ký điển hình:

1. Cấp **internal subject ID** ổn định, tách khỏi email và số điện thoại.
2. Nhận thuộc tính từ client; kiểm tra kiểu, độ dài, encoding và các ràng buộc nghiệp vụ.
3. Ghi nguồn tự khai và trạng thái **unverified** nếu chưa chứng minh.
4. Tạo thử thách ngẫu nhiên một lần, thời hạn ngắn, gắn với **tài khoản + giá trị thuộc tính cụ thể + mục đích verify_email**.
5. Sau khi thử thách được hoàn tất, server kiểm tra hiệu lực, chưa sử dụng và khớp giá trị hiện tại rồi cập nhật trạng thái/verified_at.
6. Ghi sự kiện bảo mật, tránh log token hoặc link xác minh; khi đổi email, **không chuyển nguyên trạng thái verified cũ** sang email mới.

Hai nhận định cần phân biệt:

- “Người này kiểm soát email A tại lúc xác minh” — có thể được hỗ trợ bằng quy trình email verification.
- “Người này là nhân viên Trường A và được quản trị lớp học” — cần nguồn tổ chức có thẩm quyền và kiểm tra quyền riêng.

### 5.1. Identity proofing khác xác minh email

Khi nghiệp vụ cần danh tính pháp lý hoặc tư cách tổ chức, kiểm tra email chưa đủ. **Identity proofing** có thể kiểm chứng giấy tờ, dữ liệu của tổ chức hoặc các bằng chứng theo chính sách và quy định áp dụng. Kết quả phải ghi rõ **thuộc tính nào** đã kiểm chứng, nguồn, cách kiểm chứng, thời điểm và giới hạn. Không gom tất cả vào nhãn “verified = true” rồi mặc định ngày sinh, tư cách nhân viên, quyền thanh toán và credential đều đáng tin như nhau.

## 6. Khóa định danh và liên kết danh tính

Một lỗi phổ biến là **đồng nhất tài khoản bằng một thuộc tính có thể thay đổi**. Lỗi này dễ gây *account mis-linking* trong SSO, social login hoặc chức năng gộp tài khoản.

Ưu tiên thiết kế:

- Dùng **user_id nội bộ** làm khóa bền vững; không dùng email làm primary key của user.
- Với OIDC, lưu **issuer + sub**, thêm tenant/phạm vi khi cần; không dùng riêng sub làm khóa toàn cục.
- Định nghĩa quan hệ riêng **external identity → internal user ID**; một user có thể liên kết nhiều IdP.
- Không tự động gộp hai tài khoản chỉ vì email giống nhau, kể cả khi hai phía đều khai **email_verified = true**.
- Có chính sách khi IdP đổi issuer, thay cách cấp subject, người dùng chuyển tenant hoặc rời tổ chức.

Ví dụ mapping:

~~~text
Internal user: usr_8f2
Linked identity A:
    issuer: https://idp.school-a.example
    subject: 73cf...
    tenant: school-a
Linked identity B:
    issuer: https://accounts.partner.example
    subject: a842...
    tenant: partner-program
~~~

Không suy diễn hai identity link cùng thuộc một người chỉ vì email trùng. Quy trình liên kết an toàn bắt đầu từ **phiên nội bộ đủ tin cậy**, yêu cầu xác thực lại khi phù hợp, thực hiện luồng xác thực với IdP mới, kiểm tra assertion và xác nhận thay đổi. Thêm/xóa một identity link là hành động bảo mật vì làm thay đổi đường truy cập vào tài khoản.

### 6.1. Email và điện thoại có thể đổi chủ

**Email** có thể đổi tên, chuyển sở hữu tên miền, bị thu hồi, chia sẻ hoặc tái cấp. Quy tắc viết hoa/chữ thường, Unicode, alias, dấu chấm và hậu tố +tag phụ thuộc nhà cung cấp. Không tự ý áp dụng quy tắc “bỏ dấu chấm” hay “bỏ phần sau dấu +” cho mọi miền. Quy tắc chuẩn hóa tìm kiếm phải được thiết kế riêng và không làm mất nghĩa của giá trị gốc.

**Điện thoại** có thể chuyển mạng, SIM swap hoặc tái cấp. OTP nhận được hôm nay chỉ là bằng chứng kiểm soát kênh tại thời điểm này, không xác nhận vĩnh viễn chủ tài khoản từ nhiều năm trước.

**Tên hiển thị** có thể trùng hoặc chứa ký tự Unicode giống nhau về hình dạng. Giao diện quản trị cần hiển thị thêm internal ID, tenant hoặc thông tin xác minh khác để tránh phê duyệt nhầm người.

## 7. Claim trong OIDC, SAML và token

Với Single Sign-On (SSO), Relying Party (RP) nhận các **claim/assertion** từ bên phát hành. Đây là khẳng định có cấu trúc; phải kiểm tra giao thức và thẩm quyền của nguồn trước khi sử dụng.

### 7.1. ID token minh họa

~~~json
{
  "iss": "https://login.school-a.example",
  "sub": "idp-subject-417",
  "aud": "learning-web-client",
  "exp": 1790000300,
  "iat": 1790000000,
  "email": "teacher@example.org",
  "email_verified": true,
  "name": "Giảng viên A"
}
~~~

Payload JSON này chỉ để minh họa, **không phải bằng chứng token đã được xác thực**. RP phải kiểm tra chữ ký, issuer được tin, audience là client hợp lệ, hạn và các điều kiện OIDC của luồng (nonce khi cần). Với Authorization Code, cần bảo vệ callback bằng state, PKCE và redirect URI chính xác. Các claim email/name vẫn là dữ liệu mà IdP khẳng định, cần hợp đồng rõ trước khi sử dụng cho nghiệp vụ quan trọng.

| Claim | Ý nghĩa | Kiểm tra/sử dụng an toàn |
| --- | --- | --- |
| **iss** | Nhà phát hành | Phải khớp issuer tin cậy |
| **sub** | Định danh chủ thể ở issuer | Ánh xạ cùng iss và phạm vi phù hợp |
| **aud** | Người nhận token | RP phải thuộc audience được cho phép |
| **exp / iat** | Hạn/phát hành token | Kiểm tra thời gian, không nhầm với thời điểm xác minh email |
| **email** | Email do IdP khai | Thuộc tính liên hệ theo chính sách |
| **email_verified** | Khẳng định việc IdP đã xác minh email | Không chứng minh danh tính pháp lý hay vai trò |
| **name** | Tên hiển thị | Không làm khóa định danh hay căn cứ cấp quyền |

Access token OAuth 2.0 dành cho **resource server** trong phạm vi audience/scope phù hợp; không dùng access token như ID token để suy ra đăng nhập của client. Ngược lại, API không được dùng ID token làm access token. Một JWT có chữ ký hợp lệ vẫn có thể chứa claim không đủ mới hoặc issuer không có thẩm quyền về role. **Tính đúng về chữ ký không tự chứng minh mọi nội dung đúng cho mọi nghiệp vụ.**

### 7.2. Ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Credential"| I["IdP"]
    I -->|"ID token / assertion"| R["Relying Party"]
    R -->|"Kiểm tra issuer, chữ ký, audience..."| M["Identity mapping"]
    M -->|"Issuer + subject + tenant"| D[("Hồ sơ nội bộ")]
    D -->|"Thuộc tính có nguồn"| A["Authorization Policy"]
    C["Client tự gửi role / email"] -.->|"Chưa tin cậy"| R
~~~

RP phải biết IdP được phép xác nhận những thuộc tính nào. Không lấy role, tenant_id hoặc email_verified do client gửi rồi ghi thẳng vào kho danh tính. Không tự cấp membership của tenant B chỉ vì IdP của tenant A phát claim có tên tương tự.

### 7.3. Claim có thể cũ dù token còn hạn

IdP cấp JWT lúc 08:55 với role admin; lúc 09:00 người dùng bị thu hồi quyền. Nếu JWT có hạn tới 10:00 và API chỉ đọc claim, người đó có thể tiếp tục thao tác. Đây là **vấn đề độ mới của thuộc tính**, không nhất thiết là lỗi chữ ký.

Các lựa chọn khắc phục: giảm TTL, truy vấn quyền hiện tại cho thao tác nhạy cảm, dùng introspection/revocation, kiểm tra phiên bản quyền trong kho dữ liệu hoặc nhận sự kiện deprovisioning để vô hiệu hóa phiên/token. Cần chọn dựa vào yêu cầu độ trễ hiệu lực và mức rủi ro.

## 8. Thuộc tính trong quá trình xác thực credential

Identity attribute thường có ba vai trò:

1. **Chọn tài khoản:** người dùng nhập email/username, server tìm internal user ID rồi kiểm tra credential thuộc subject đó. Tên đăng nhập **chưa phải bằng chứng** xác thực.
2. **Mô tả phương thức xác thực:** trạng thái đăng ký MFA/passkey, thời điểm xác thực lại, trạng thái thiết bị được tin cậy. Những thuộc tính này cần quản lý bởi dịch vụ xác thực.
3. **Tín hiệu bối cảnh:** IP, thiết bị, vị trí gần đúng, lịch sử thay đổi credential hỗ trợ đánh giá rủi ro/step-up. Không coi tín hiệu này là bằng chứng danh tính tuyệt đối.

### 8.1. Với passkey và WebAuthn

Khi đăng ký passkey, hệ thống ánh xạ **credential ID + public key → internal subject ID**. Khi xác thực, server gửi challenge mới, kiểm tra RP ID/origin, challenge, chữ ký và cờ xác thực người dùng theo chính sách. Thành công chứng minh việc sử dụng khóa riêng tương ứng với credential đã đăng ký trong bối cảnh đó.

Email/tên hiển thị có thể giúp chọn tài khoản, nhưng không thay được ánh xạ credential tới subject. Đổi email không được tự chuyển passkey sang tài khoản khác. Thêm hoặc xóa passkey cần xác thực lại thích hợp vì thay đổi ai có thể kiểm soát tài khoản.

### 8.2. Với chứng chỉ và workload identity

Chứng chỉ X.509 có thể chứa thuộc tính nhận diện trong Subject/SAN, ví dụ DNS name hoặc URI workload. mTLS kiểm tra chứng chỉ và bằng chứng sở hữu khóa riêng; sau đó ánh xạ định danh kỳ vọng sang workload và áp chính sách quyền.

Một giá trị CN nhìn giống tên service không đủ để cấp quyền nếu chuỗi tin cậy, SAN, mục đích sử dụng, thời hạn hoặc chính sách phát hành không hợp lệ. Không tin bất kỳ CA nào theo mặc định. Khi workload đổi tên hoặc bị dừng, cần cập nhật thuộc tính ánh xạ và thu hồi credential liên quan.

### 8.3. Với MFA và kênh khôi phục

Trạng thái **phone_verified = true** chỉ phản ánh quy trình kiểm tra số điện thoại theo chính sách; không đồng nghĩa chủ thể hiện giữ một authenticator MFA chống phishing. Email vừa thay và xác minh cũng không nhất thiết đủ để đặt lại toàn bộ credential. Kênh recovery thường là **đường truy cập thay thế** vào tài khoản; việc đổi nó nên được bảo vệ bằng step-up, cảnh báo và giới hạn rủi ro phù hợp.

## 9. Thuộc tính và authorization

**Attribute-Based Access Control (ABAC)** là mô hình quyết định dựa trên thuộc tính của subject, tài nguyên, hành động và môi trường. Đây là cách **dùng** identity attribute cho phân quyền, khác với authentication.

~~~text
Permit(
  subject = usr_417,
  action = "grade_submission",
  resource = submission_99
) iff
  account.status == ACTIVE
  and membership.tenant_id == resource.tenant_id
  and membership.role == TEACHER
  and resource.course_id in subject.assigned_course_ids
~~~

Giá trị membership/role/course phải tới từ nguồn **có thẩm quyền**, không từ request body của client. Một giảng viên xác thực thành công và có role teacher vẫn chỉ được chấm các lớp **đã phân công**.

### 9.1. Tách ba lớp thuộc tính

| Lớp | Ví dụ | Cách quản lý |
| --- | --- | --- |
| **Identity attribute bền vững** | Tên, email, linked IdP, trạng thái tài khoản | Lưu với nguồn/trạng thái và vòng đời |
| **Session/authentication context** | auth_time, phương thức vừa dùng, mức bảo đảm, session ID | Gắn thời điểm xác thực và vòng đời phiên |
| **Dynamic authorization context** | Vai trò hiện tại, membership, quyền với lớp học | Theo policy hiện thời và thời hạn hiệu lực |

Nếu giảng viên bị gỡ khỏi lớp, không nên chờ họ đăng xuất mới áp dụng quyền nếu nghiệp vụ đòi hỏi hiệu lực ngay. Đưa role vào token dài hạn tạo đánh đổi giữa hiệu năng và độ mới; phải có chiến lược rõ.

### 9.2. Chống nhầm tenant

Trong SaaS đa tenant, tenant_id là ranh giới cô lập dữ liệu. Yêu cầu xem dữ liệu trường B không được hợp lệ chỉ vì người dùng đã đăng nhập thành công tại trường A. Policy phải kiểm tra quan hệ **subject – tenant – resource**. Không gán admin chỉ vì đuôi email của người dùng trùng tên miền tổ chức.

## 10. Vòng đời cập nhật, thu hồi và xóa thuộc tính

~~~mermaid
flowchart TD
    A["Thu thập / nhận thuộc tính"] --> B["Kiểm tra kiểu và phạm vi"]
    B --> C["Gắn nguồn / trạng thái xác minh"]
    C --> D["Lưu với quyền đọc phù hợp"]
    D --> E{"Thay đổi / hết hiệu lực?"}
    E -->|"Không"| F["Sử dụng theo chính sách"]
    F --> E
    E -->|"Có"| G["Kiểm tra quyền thay đổi"]
    G --> H["Xác minh lại khi cần"]
    H --> I["Tăng phiên bản, audit, đồng bộ"]
    I --> D
    E -->|"Thu hồi/xóa"| J["Vô hiệu hóa hoặc xóa theo chính sách"]
~~~

### 10.1. Ma trận quyền cập nhật

| Thuộc tính | Ai đề nghị thay? | Ai xác nhận? | Bảo vệ cần có |
| --- | --- | --- | --- |
| Tên hiển thị | Người dùng | Ứng dụng theo policy | Validation, encoding đầu ra |
| Email liên hệ | Người dùng/quản trị hợp lệ | Quy trình verify email | Xác minh giá trị mới, thông báo |
| Email recovery | Người dùng có phiên tin cậy | Authentication/recovery service | Step-up, cảnh báo kênh cũ |
| Phòng ban | HR/quản trị tổ chức | Nguồn tổ chức có thẩm quyền | Đồng bộ, xử lý role bị ảnh hưởng |
| Role admin | Người có quyền cấp vai trò | Role/policy management service | Phân quyền, audit, phê duyệt phù hợp |
| Trạng thái khóa tài khoản | Security service/quản trị hợp lệ | Identity service | Người dùng không được tự mở khóa |
| Internal user ID | Hệ thống khi tạo tài khoản | Identity service | Bất biến, không tái sử dụng |

### 10.2. Thay email là một giao dịch nhiều bước

Giả sử người dùng đổi email A sang B:

1. Kiểm tra phiên và yêu cầu xác thực lại nếu email dùng cho login/recovery.
2. Tạo yêu cầu pending gắn internal user ID; **không cập nhật B thành verified trước khi chứng minh**.
3. Gửi thử thách tới B, có thể thông báo A; chống lạm dụng gửi thư.
4. Sau khi hợp lệ, cập nhật B theo transaction, tăng phiên bản thuộc tính, ghi verified_at mới.
5. Vô hiệu thử thách cũ, kiểm tra ảnh hưởng đến recovery/session, đồng bộ các hệ thống sử dụng.

Nếu B đã thuộc tài khoản khác, không tự động hợp nhất tài khoản. Thiết kế thông báo lỗi cũng cần tránh tạo công cụ dò email tồn tại (*user enumeration*).

### 10.3. Xung đột nhiều nguồn

Người dùng có thể sửa tên hiển thị trong ứng dụng, còn IdP gửi tên pháp lý khác. Cần quy tắc **source of truth theo từng thuộc tính**: tên hiển thị do người dùng quản lý, phòng ban do HR quản lý, quyền quản trị do bộ phận phân quyền quản lý. Không nên áp dụng “nguồn cập nhật sau cùng luôn thắng” cho role, membership hoặc account status. Khi nhận sự kiện đồng bộ không theo thứ tự, cần version/timestamp/tính hiệu lực để tránh sự kiện cũ ghi đè trạng thái mới.

## 11. Rủi ro bảo mật khi dùng identity attribute

| Rủi ro | Ví dụ | Phòng ngừa |
| --- | --- | --- |
| **Giả mạo trường từ client** | Request gửi role admin hoặc email_verified true | Allowlist field được sửa, kiểm tra quyền phía server |
| **Liên kết nhầm** | Tự gộp SSO account vì email trùng | Ánh xạ issuer + subject, liên kết có xác thực lại |
| **Thuộc tính cũ** | Người nghỉ việc còn role trong JWT | Deprovisioning, TTL, kiểm tra hiện thời/thu hồi |
| **Tái cấp email/điện thoại** | Chủ mới nhận mã recovery của chủ cũ | Không dùng liên hệ làm identity bất biến; recovery đa lớp |
| **Nhầm tenant** | Role từ trường A thành quyền ở trường B | Gắn tenant và scope vào mapping/policy |
| **Mass assignment** | Profile API cho sửa account_status | Schema đầu vào riêng, reject field cấm |
| **Lộ dữ liệu** | JWT chứa ngày sinh, địa chỉ rồi bị log | Tối thiểu claim, bảo vệ token và log |
| **Tạo identity giả** | Bot tự khai email người khác để xin quyền | Xác minh ownership, chống lạm dụng đăng ký |
| **Unicode/confusable** | Tên giống quản trị viên gây phê duyệt nhầm | Hiển thị thêm định danh/tenant đáng tin |
| **Nhầm assurance** | Email verified bị coi là MFA hoặc proofing pháp lý | Ghi rõ bằng chứng, phạm vi, thời điểm |

### 11.1. Tình huống email bị tái cấp

Một học viên dùng email công ty đăng ký khóa học. Họ rời công ty, email được cấp lại cho nhân viên mới. Nếu ứng dụng xem “ai hiện kiểm soát email” là “chủ sở hữu vĩnh viễn của tài khoản”, nhân viên mới có thể dùng “Quên mật khẩu” để truy cập dữ liệu học viên cũ.

Các lớp phòng vệ: dùng user ID ổn định; không gộp bằng email; đánh giá kênh recovery theo rủi ro; bảo vệ đổi credential bằng xác thực lại; với tài khoản đặc quyền, dùng phương thức chống phishing và khôi phục tương xứng; đồng bộ deprovisioning khi tổ chức kết thúc tư cách thành viên.

### 11.2. Tình huống role đã bị thu hồi

Quản trị viên bị gỡ quyền lúc 09:00, trong khi JWT cấp lúc 08:55 có claim role admin và hạn đến 10:00. API chỉ kiểm tra chữ ký và exp nên tiếp tục cho phép thao tác. Lỗi thuộc về **freshness và thực thi quyền hiện thời**; chữ ký có thể vẫn đúng. Cần thiết kế quyền có thể thay đổi trong phiên thông qua cập nhật trạng thái, token ngắn hạn, introspection/revocation hoặc policy check ở API, tùy mức rủi ro.

## 12. Quyền riêng tư và chất lượng dữ liệu thuộc tính

Identity attribute thường là dữ liệu cá nhân, có thể liên kết tới một người, hoặc chứa thông tin nhạy cảm. Nguyên tắc **thu thập tối thiểu, dùng đúng mục đích, phân quyền, bảo vệ lưu trữ và xóa theo chính sách** phải được thực hiện từ đầu.

- **Data minimization:** chỉ thu thập trường thật sự cần. Nếu chỉ cần điều kiện “đủ tuổi”, cân nhắc lưu kết quả xác minh điều kiện thay vì toàn bộ ngày sinh khi phù hợp.
- **Purpose limitation:** email thông báo không mặc nhiên dùng cho đăng nhập, quảng cáo hoặc khôi phục.
- **Access control:** profile API chỉ trả trường client cần; kiểm tra quyền với subject và tài nguyên, chống IDOR/BOLA.
- **Storage protection:** TLS khi truyền, bảo vệ dữ liệu lưu/backup, quản lý khóa và phân quyền đọc dữ liệu nhạy cảm.
- **Audit without secrets:** log actor, thuộc tính thay đổi, thời điểm, nguồn và kết quả; tránh log OTP, password, link verification, session ID và token nguyên dạng.
- **Retention/deletion:** xác định thời hạn lưu dữ liệu theo mục đích/quy định; phân biệt hồ sơ, audit và bản sao phân tích.
- **Minimize claims:** không đưa toàn bộ hồ sơ vào JWT/cookie/URL; nội dung JWT được ký thường vẫn có thể đọc được.

### 12.1. Chất lượng và toàn vẹn dữ liệu

Trường phải có kiểu, độ dài, tập giá trị và encoding rõ ràng. Chuẩn hóa tìm kiếm không được biến hai giá trị khác nhau thành cùng một identity ngoài chính sách cho phép. Kiểm tra đầu vào, dùng truy vấn tham số hóa và encode đầu ra phù hợp chống injection/XSS. Tránh cắt identifier hoặc ép kiểu làm mất thông tin phân biệt.

Các thay đổi bảo mật cần transaction/optimistic concurrency hoặc cơ chế tương đương, tránh hai thao tác đồng thời ghi đè nhau. Sử dụng phiên bản thuộc tính để phát hiện client hoặc sự kiện đồng bộ đang dùng dữ liệu cũ.

## 13. Thiết kế API cập nhật thuộc tính an toàn

Giả sử frontend gọi:

~~~http
PATCH /api/me/profile
Content-Type: application/json

{
  "display_name": "Minh Anh",
  "email_verified": true,
  "role": "admin"
}
~~~

Endpoint này chỉ nên chấp nhận các thuộc tính hồ sơ người dùng được phép sửa, ví dụ display_name. Phải từ chối những trường nhạy cảm do client đưa vào, tránh **mass assignment**. Không dùng user_id do request body tự khai để quyết định sửa bản ghi nào ở endpoint /me; phải lấy subject từ phiên đã xác thực.

Pseudocode:

~~~text
update_my_profile(authenticated_session, request):
    subject_id = authenticated_session.subject_id
    validate_session_and_account_status(authenticated_session)

    allowed_fields = {"display_name", "preferred_language"}
    reject_unknown_or_forbidden_fields(request.body, allowed_fields)
    validate_field_types_limits_and_encoding(request.body)

    save_profile_attributes(
        subject_id = subject_id,
        values = request.body,
        source = "self_asserted",
        actor = subject_id
    )
    audit_event("profile_updated", subject_id, changed_field_names_only)
~~~

API quản trị sửa subject khác phải kiểm tra quyền của **actor với subject đích và tenant tương ứng**. Các thao tác đổi email khôi phục, thêm MFA, gỡ IdP, đổi role, mở khóa tài khoản cần **endpoint và quy trình riêng**, thường kèm xác thực lại hoặc phê duyệt theo rủi ro.

## 14. Ví dụ xuyên suốt: nền tảng học tập đa tenant

Một nền tảng có học viên, giảng viên, quản trị viên thuộc nhiều trường. Mỗi người dùng có internal user ID; trường quản lý membership; người dùng có thể đăng nhập bằng passkey, mật khẩu + MFA hoặc IdP liên kết.

### 14.1. Ba bản ghi khác vai trò

~~~text
Identity:
  user_id: usr_417
  account_status: ACTIVE

Contact attribute:
  user_id: usr_417
  name: email
  value: teacher@example.org
  source: self_asserted
  verified_at: 2026-05-10T09:00:00Z

Tenant membership:
  user_id: usr_417
  tenant_id: school-a
  role: TEACHER
  assigned_courses: [course-101]
  source: school-a-provisioning
  effective_from: 2026-05-01T00:00:00Z
~~~

Đổi email không làm đổi user_id, nên lịch sử học tập và chấm bài không bị mất liên kết. Khi giáo viên rời trường A, membership A bị gỡ; tài khoản có thể vẫn tồn tại nếu họ còn học ở trường B, nhưng quyền ở trường A phải bị từ chối.

### 14.2. Các tình huống sử dụng

| Tình huống | Kiểm tra cần thiết | Kết quả |
| --- | --- | --- |
| Giáo viên dùng passkey chấm bài ở course-101 | Credential thuộc usr_417; tài khoản active; membership school-a có nguồn đúng; được phân công lớp | Cho phép nếu policy thỏa |
| Cùng giáo viên chấm course-202 của school-b | Xác thực thành công nhưng thiếu membership/assignment school-b | Từ chối |
| Người lạ nhập email giảng viên tại login | Email chỉ là identifier đầu vào | Không cấp phiên nếu chưa chứng minh credential |
| Chủ mới email cũ dùng SSO | Issuer + subject không khớp linked identity của usr_417 | Không tự liên kết |
| Trường A thu hồi quyền TEACHER | Membership authoritative thay đổi | Quyền API phản ánh theo chính sách freshness |

### 14.3. Nguồn có thẩm quyền theo thuộc tính

| Thuộc tính | Nguồn có thẩm quyền đề xuất | Có thể tự cấp quyền? |
| --- | --- | --- |
| Tên hiển thị | Người dùng | Không |
| Email đã xác minh | Dịch vụ xác minh email, theo phạm vi kiểm soát email | Không |
| Trạng thái tài khoản | Identity service | Dùng theo policy |
| Membership trường | Provisioning đã được trường ủy quyền | Đầu vào, còn cần kiểm tra scope/tài nguyên |
| Course assignment | Hệ thống quản lý lớp | Đầu vào quyền với lớp cụ thể |
| Role admin | Quy trình phân quyền/phê duyệt | Cần đúng tenant và action |
| Thời điểm MFA/passkey gần nhất | Authentication service | Phục vụ step-up |

## 15. Checklist thiết kế và kiểm thử

Trước khi thêm hoặc sử dụng một identity attribute, hãy trả lời:

1. **Ý nghĩa:** dữ liệu mô tả điều gì? Có nhầm với credential/permission không?
2. **Phạm vi:** unique ở user, tenant, issuer hay tổ chức nào? Có thể tái cấp không?
3. **Nguồn:** ai cấp, sửa, xác minh, thu hồi? Có xung đột nhiều nguồn không?
4. **Bằng chứng:** verified nghĩa gì, cần method, verified_at và thời hạn không?
5. **Độ mới:** thay đổi quyền có cần hiệu lực ngay? Token và cache sống bao lâu?
6. **Ranh giới:** client có thể khai không? IdP có được xác minh và đúng thẩm quyền không?
7. **Phân quyền:** API kiểm tra resource, action, tenant và role ở server chứ?
8. **Vòng đời:** đổi, xác minh lại, deprovisioning, recovery và xóa thế nào?
9. **Riêng tư:** trường nhạy cảm không, ai được đọc, cần có trong token/log không?
10. **Thử nghiệm:** đã kiểm tra email trùng/tái cấp, sai issuer, stale role, mass assignment, đổi tenant, cập nhật đồng thời chưa?

## 16. Bài tập vận dụng

**Tình huống:** Ứng dụng dùng email làm khóa chính bảng users. Khi nhận ID token của IdP bất kỳ có email_verified true, ứng dụng gộp với tài khoản cùng email và cấp role từ claim role. Khi người dùng đổi email, ứng dụng đổi luôn khóa chính. JWT có hạn 24 giờ chứa toàn bộ hồ sơ và danh sách quyền.

**Yêu cầu:**

1. Kể ít nhất **năm rủi ro** identity attribute trong thiết kế.
2. Thiết kế lại bảng identity, email và external identity mapping sao cho đổi email không làm mất liên kết.
3. Đề xuất nguồn có thẩm quyền cho email, membership, role; nêu bước xác minh trước khi cấp quyền.
4. Chọn cơ chế giải quyết role cũ trong JWT khi cần thu hồi quyền gần như tức thời.
5. Viết test cho: email tái cấp, role giả mạo, hai issuer trùng subject, cross-tenant access, cập nhật profile kèm is_admin true.

**Gợi ý tự đối chiếu:** internal user ID phải ổn định; liên kết SSO bằng issuer + subject; email_verified không chứng minh cùng tài khoản; role cần nguồn tin cậy và tenant đúng; access token phải đúng audience và độ mới; client không được tự sửa trạng thái bảo mật.

## 17. Ghi nhớ

- **Identity attribute** là khẳng định về một chủ thể, luôn có **nguồn, phạm vi, thời điểm và giới hạn tin cậy**.
- **Identifier** ổn định giúp giữ các quan hệ dữ liệu bền vững; email, số điện thoại và tên hiển thị không nên làm khóa danh tính dài hạn.
- **Claim** được ký hợp lệ chỉ thể hiện issuer đưa ra một khẳng định; bên nhận còn phải biết issuer có thẩm quyền đối với **thuộc tính cụ thể** hay không.
- **Authentication** chứng minh kiểm soát credential; **authorization** quyết định hành động theo quyền và ngữ cảnh hiện thời. Hai quá trình liên quan nhưng không thay thế nhau.
- **Vòng đời thuộc tính** ảnh hưởng trực tiếp tới đăng nhập, SSO, MFA, passkey, token, phiên, khôi phục tài khoản và deprovisioning. Cần bảo vệ cả việc **thay đổi** lẫn **tiêu thụ** dữ liệu này.

Khi hệ thống xem mỗi thuộc tính là một khẳng định có nguồn gốc và giới hạn, thay vì một chuỗi dữ liệu mặc nhiên đáng tin, luồng xác thực, liên kết tài khoản và phân quyền sẽ chống chịu tốt hơn với thay đổi danh tính và các kiểu tấn công thực tế.
