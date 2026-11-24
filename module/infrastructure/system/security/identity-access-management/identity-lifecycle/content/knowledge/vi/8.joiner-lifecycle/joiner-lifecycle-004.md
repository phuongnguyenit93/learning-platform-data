# Tạo account trong Joiner lifecycle: từ danh tính đã xác minh đến tài khoản sẵn sàng sử dụng

**Tạo account (account creation/provisioning)** là bước thiết lập tài khoản của một **chủ thể đã có căn cứ hợp lệ** trong hệ thống quản lý danh tính, nhà cung cấp danh tính (IdP) và các ứng dụng mà chủ thể cần sử dụng. Đây là mắt xích quan trọng của **Joiner lifecycle**: chuyển dữ liệu danh tính và điều kiện tham gia tổ chức thành các tài khoản có thể quản trị, sau đó liên kết với quyền truy cập đúng vai trò, đúng thời điểm.

Trong **Identity and Access Management (IAM)**, “tạo account thành công” không chỉ là tạo được một hàng trong cơ sở dữ liệu. Quy trình còn phải xác định **đúng người**, **đúng quan hệ làm việc**, **định danh duy nhất**, **đúng hệ thống đích**, **đúng trạng thái kích hoạt**, **quyền phù hợp** và **có bằng chứng tài khoản đã được tạo ở nơi cần thiết**.

Bài học thuộc chương **Joiner lifecycle** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, nơi quá trình gia nhập được đặt trong toàn bộ vòng đời **Joiner–Mover–Leaver**: xác minh danh tính, tạo và kích hoạt tài khoản, cấp quyền, rà soát khi đổi vai trò rồi thu hồi quyền khi quan hệ hợp lệ kết thúc. Các cơ chế **IdP, SSO, SCIM, RBAC/ABAC**, kiểm toán và quản trị danh tính máy sẽ được kết nối với bước tạo tài khoản để tránh tài khoản mồ côi và quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **danh tính**, **account**, **authenticator**, **vai trò/quyền** và **phiên truy cập**.
2. Xác định điều kiện cần có trước khi tạo tài khoản cho nhân viên, nhà thầu và đối tác.
3. Thiết kế quy trình tạo tài khoản theo nguồn dữ liệu có thẩm quyền, định danh ổn định, trạng thái hiệu lực và quyền sở hữu rõ ràng.
4. Giải thích vai trò của **IdP/SSO**, **SCIM/API**, **RBAC/ABAC** và ứng dụng đích trong quy trình onboarding.
5. Phòng tránh lỗi tạo trùng tài khoản, liên kết nhầm người, kích hoạt sớm, tự cấp quyền quá rộng và cấp phát thất bại một phần.
6. Xác minh được **tài khoản đã tồn tại, có trạng thái đúng và sẵn sàng cho nhiệm vụ hợp lệ**; lưu dấu vết phục vụ Mover/Leaver.

## 2. Account không đồng nghĩa với Identity

Một người có thể có một **hồ sơ danh tính** nhưng nhiều **account** trong các hệ thống. Ví dụ, nhân viên Minh có hồ sơ `personId=P-1024`, một account tại IdP, một account ở CRM, một account trong hệ thống quản lý mã nguồn và một account ở cổng đào tạo.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Identity (danh tính)** | Đại diện cho chủ thể và thông tin xác định chủ thể đó | `personId=P-1024`, loại employee, trạng thái active |
| **Engagement (quan hệ/nhiệm vụ)** | Căn cứ làm việc và thời hạn truy cập | Nhân viên phòng Sales từ ngày 01/03 |
| **Account (tài khoản)** | Bản ghi do IdP hay ứng dụng quản lý để chủ thể sử dụng dịch vụ | `idpUserId=ID-88`, `crmUserId=CRM-503` |
| **Authenticator (phương tiện xác thực)** | Bằng chứng người dùng kiểm soát tài khoản khi đăng nhập | Passkey, khóa bảo mật, ứng dụng MFA |
| **Role/entitlement (quyền)** | Hành động và phạm vi tài nguyên được cho phép | `crm.customer.read.region_south` |
| **Session/token** | Trạng thái và thông tin dùng trong những lần truy cập | Phiên SSO, access token của ứng dụng |

Điểm khác biệt cần ghi nhớ:

- **Đã xác minh danh tính** chưa có nghĩa là đã tạo account trong mọi ứng dụng.
- **Đã tạo account** chưa có nghĩa là account được phép hoạt động ngay.
- **Đăng nhập SSO thành công** chưa có nghĩa là đã có đúng quyền nghiệp vụ.
- **Đã gán quyền** chưa chắc ứng dụng nhận thay đổi, hoặc phiên cũ đã cập nhật.
- **Đã vô hiệu hóa IdP** chưa chắc mọi account cục bộ, phiên và token của ứng dụng đã hết hiệu lực.

Vì vậy, IAM cần quản lý cả **liên kết identity → account → entitlement** để biết mỗi account thuộc ai, có căn cứ gì, và phải xử lý thế nào khi người đó trở thành Mover hoặc Leaver.

## 3. Khi nào được tạo account?

Điều kiện cấp phát tài khoản phải bắt nguồn từ một **nguồn có thẩm quyền (authoritative source)** và chính sách của tổ chức, thay vì chỉ từ một yêu cầu email không được kiểm chứng.

Ví dụ các nguồn:

| Nhóm chủ thể | Nguồn dữ liệu thường gặp | Điều kiện cần xác nhận |
|---|---|---|
| **Employee** | Hệ thống HR và quy trình onboarding chính thức | Hồ sơ được duyệt, ngày bắt đầu, trạng thái, phòng ban/vị trí |
| **Contractor** | Hệ thống quản lý hợp đồng/nhà thầu (VMS), sponsor | Đúng cá nhân, engagement đã duyệt, sponsor, thời hạn, dự án |
| **Partner user** | Quy trình đối tác và người bảo trợ | Quan hệ hợp tác, đối tượng được cấp, phạm vi chia sẻ |
| **Service account** | Danh mục dịch vụ, yêu cầu kỹ thuật và owner | Ứng dụng, môi trường, chủ sở hữu kỹ thuật, mục đích và thời hạn |

**Identity proofing** giúp xây dựng cơ sở tin cậy về con người trước khi gắn danh tính với account. **Thông tin HR/hợp đồng** giúp xác định người đó có được tham gia và cần quyền gì. Hai loại căn cứ liên quan nhưng không thay thế nhau.

Cần phân biệt hai mốc:

1. **Mốc chuẩn bị (pre-provisioning):** Hệ thống có thể tạo bản ghi account hoặc chuẩn bị cấu hình trước ngày bắt đầu nếu chính sách cho phép.
2. **Mốc kích hoạt (effective access):** Chỉ tại thời điểm đủ điều kiện, người dùng mới được phép đăng nhập hoặc truy cập tài nguyên công việc theo phạm vi đã xác định.

Ví dụ, HR cung cấp dữ liệu một tuần trước ngày nhận việc. IAM có thể chuẩn bị account ở trạng thái **inactive** để tránh chậm trễ ngày đầu; nhưng không nên vô tình tạo lối đăng nhập hoặc cấp quyền production trước mốc cho phép.

## 4. Dữ liệu đầu vào cần thiết để tạo account

Quy trình phải biết **ai**, **vì sao**, **ở đâu**, **khi nào** và **ai chịu trách nhiệm**. Không nhất thiết sao chép mọi thông tin nhân sự vào từng ứng dụng.

| Thuộc tính | Ví dụ minh họa | Công dụng |
|---|---|---|
| Định danh cá nhân ổn định | `personId=P-1024` | Liên kết các tài khoản thuộc cùng một người |
| Loại chủ thể | `employee`, `contractor` | Áp quy trình/kiểm soát phù hợp |
| Trạng thái engagement | `approved`, `active`, `ended` | Quyết định account có được kích hoạt không |
| Mốc hiệu lực | `startAt`, `endAt` (nếu áp dụng) | Kích hoạt và thu hồi đúng lúc |
| Tên hiển thị | Nguyễn Minh | Hiển thị cho người dùng, hỗ trợ tìm kiếm |
| Định danh đăng nhập | `userName` hoặc tên đăng nhập được cấp | Duy nhất trong phạm vi IdP/ứng dụng |
| Email liên hệ hợp lệ | Địa chỉ đã xác minh hoặc được cấp bởi tổ chức | Thông báo và liên lạc theo quy trình |
| Bộ phận, vai trò, dự án | Sales; dự án A | Đầu vào tính quyền RBAC/ABAC |
| Quản lý hoặc sponsor | `managerId=M-17` | Phê duyệt, rà soát và xử lý ngoại lệ |
| Ứng dụng cần sử dụng | CRM, email, repository | Xác định đích provisioning |
| Nguồn và phiên bản biến cố | HR event và thời điểm/phiên bản | Xử lý cập nhật trễ và khả năng truy vết |

**Chỉ thu thập và chia sẻ tối thiểu:** CRM có thể cần mã nhân viên, tên hiển thị, vai trò và bộ phận; không cần ảnh giấy tờ tùy thân hoặc toàn bộ hồ sơ HR. IAM phải phân quyền truy cập vào dữ liệu đầu vào và hạn chế xuất thông tin nhạy cảm sang ứng dụng khác.

### 4.1. Định danh ổn định quan trọng hơn email

Email, tên hiển thị và phòng ban **có thể thay đổi**. Không nên dùng email làm khóa nhận dạng người duy nhất cho toàn bộ vòng đời, vì email có thể đổi tên, bị tái sử dụng theo chính sách hoặc tồn tại nhiều alias.

Nên phân biệt:

- **ID identity nội bộ:** Khóa ổn định đại diện cho chủ thể.
- **ID account tại IdP:** Định danh do IdP cấp cho bản ghi account.
- **ID account tại ứng dụng:** Định danh cục bộ mà ứng dụng trả về.
- **Tên đăng nhập/email:** Thuộc tính có thể thay đổi và có quy tắc duy nhất riêng.
- **External correlation ID:** Trường dùng để ánh xạ identity và account qua hệ thống, chẳng hạn `externalId` nếu hệ thống SCIM hỗ trợ.

Sơ đồ ánh xạ ví dụ:

~~~text
personId=P-1024
    |
    +-- IdP:  idpAccountId=ID-88
    |
    +-- CRM:  scimId=CRM-503
    |
    +-- Git:  appAccountId=GIT-209

Tài khoản có thể đổi email hoặc tên hiển thị,
nhưng các ánh xạ được quản lý bằng định danh ổn định.
~~~

Đừng tự liên kết một account có cùng tên hoặc email với identity đang onboarding khi chưa có căn cứ đủ tin cậy. Nếu phát hiện trùng hoặc xung đột, cần quy trình **đối soát và xác minh**, tránh cấp nhầm quyền cho account của người khác.

## 5. Luồng tạo account trong Joiner lifecycle

Một quy trình cấp phát có kiểm soát gồm nhiều điểm quyết định, không chỉ một lệnh API “create user”.

~~~mermaid
flowchart TD
    H["HR / VMS / nguồn có thẩm quyền<br/>Sự kiện Joiner đã được duyệt"] --> V{"Danh tính và engagement<br/>đủ điều kiện?"}
    V -->|Không| X["Giữ chờ / xử lý sai lệch<br/>không kích hoạt quyền"]
    V -->|Có| I["Tạo hoặc liên kết<br/>identity nội bộ ổn định"]
    I --> C{"Đã có account phù hợp?"}
    C -->|Có, liên kết đã xác minh| U["Cập nhật đúng account<br/>theo trạng thái mong muốn"]
    C -->|Chưa| N["Tạo account tại IdP"]
    C -->|Xung đột/không chắc chắn| Q["Dừng cấp tự động<br/>chuyển đối soát"]
    N --> A["Thiết lập trạng thái,<br/>xác thực và nhóm nền tảng"]
    U --> A
    A --> P["Provision tới ứng dụng<br/>SCIM / API / quy trình thay thế"]
    P --> R["Readback từng đích<br/>account + status + entitlement"]
    R --> S{"Kết quả đúng trạng thái<br/>và mốc hiệu lực?"}
    S -->|Có| D["Đánh dấu readiness<br/>và thông báo sử dụng"]
    S -->|Chưa| E["Ghi lỗi, xử lý và đối soát<br/>không báo hoàn tất"]
    E --> P
    D --> L["Rà soát, Mover và Leaver<br/>trong vòng đời tiếp theo"]
~~~

### Bước 1 — Nhận và kiểm tra biến cố Joiner

Ví dụ HR gửi sự kiện nhân viên được phê duyệt với ngày bắt đầu. IAM kiểm tra:

- Sự kiện thực sự đến từ nguồn được tin cậy hay không.
- Hồ sơ đã đạt điều kiện identity proofing và không bị xung đột.
- Ngày bắt đầu, trạng thái và chính sách kích hoạt có phù hợp.
- Các trường bắt buộc cho việc tạo account có đủ và nhất quán.
- Nếu là contractor, sponsor và ngày kết thúc có hợp lệ.

Thiếu dữ liệu cần thiết nên dẫn tới **pending/exception**, thay vì tự điền vai trò, email hoặc ngày hết hạn một cách phỏng đoán.

### Bước 2 — Phân giải danh tính và tránh account trùng

Trước lệnh CREATE, hệ thống cần kiểm tra identity đã tồn tại hoặc từng hoạt động trước đó chưa:

- Có bản ghi identity với ID ổn định tương ứng không?
- Có account đích đã được liên kết chắc chắn với identity này không?
- Người đó từng là Leaver rồi gia nhập lại (**rejoiner**) hay là một người hoàn toàn mới?
- Account hiện có đang active, disabled, locked hay thuộc một chủ thể khác?
- Có xung đột do email/tên đăng nhập trùng hoặc mapping mất đồng bộ không?

**Không tạo bản sao** chỉ vì sự kiện Joiner được gửi lại. **Không kích hoạt lại quyền cũ** chỉ vì tìm thấy account trước đây: cần đánh giá điều kiện hiện tại và tính lại gói quyền mong muốn.

### Bước 3 — Tạo hoặc cập nhật account ở IdP

IdP thường là nơi quản lý tài khoản xác thực, chính sách MFA, nhóm và mối liên kết đến các ứng dụng tin cậy. Tùy kiến trúc, account có thể được tạo bằng API, kết nối HR, bộ máy IAM hoặc thao tác quản trị có kiểm soát.

Một số việc phải giải quyết:

- Tên đăng nhập duy nhất, quy tắc đặt tên và xung đột.
- Trạng thái `disabled` hoặc `staged` trước khi đủ điều kiện kích hoạt.
- Nhóm/thuộc tính nền tảng dùng cho SSO hoặc chính sách truy cập.
- Cách đăng ký phương thức xác thực an toàn khi người dùng bắt đầu.
- Ghi lại **ID account thật** mà IdP trả về.

Đừng ghi mật khẩu ban đầu dạng plaintext trong log, ticket hoặc email. Ưu tiên cơ chế kích hoạt an toàn, đăng ký authenticator phù hợp và không yêu cầu chia sẻ mã OTP.

### Bước 4 — Provision account đến ứng dụng đích

Một số ứng dụng nhận account qua **SCIM**; một số dùng API riêng, kết nối thư mục hoặc quy trình thủ công có theo dõi. Cần phân loại khả năng của từng ứng dụng:

| Kiểu ứng dụng | Cách tài khoản được thiết lập | Điều cần xác minh |
|---|---|---|
| Ứng dụng có SCIM | Đồng bộ user/group từ IAM hoặc IdP | Account tạo đúng, `active` đúng, nhóm/quyền được hỗ trợ đúng |
| Ứng dụng có API quản trị riêng | Gọi API tạo/sửa user và quyền | ID đích, status, role và lỗi trả về |
| Ứng dụng chỉ hỗ trợ **JIT provisioning** | Tạo account khi đăng nhập lần đầu bằng SSO, nếu được cấu hình | Quy tắc điều kiện tạo, mapping, quyền mặc định và chặn truy cập sớm |
| Ứng dụng legacy/manual | Tạo bởi quản trị viên qua quy trình có ticket/nhật ký | Người thực hiện, ngày hiệu lực, quyền và kết quả đối soát |
| Ứng dụng không cần account cục bộ | Dùng thông tin liên kết danh tính theo cách thiết kế | Kiểm tra quyền thực thi và phiên/trạng thái truy cập |

**SSO không phải công cụ tự tạo account cho mọi ứng dụng.** SSO giải quyết xác thực liên kết; provisioning là nhiệm vụ riêng. JIT provisioning có thể làm account chỉ tồn tại sau lần đăng nhập đầu tiên, nhưng vẫn cần kiểm soát ai được phép tạo, khi nào và được gán quyền gì.

### Bước 5 — Xác minh trước khi tuyên bố sẵn sàng

Sau khi lệnh tạo thành công, IAM nên **đọc lại** trạng thái ứng dụng. Cần xác minh:

1. Account tồn tại và được liên kết với đúng identity.
2. Account ở đúng trạng thái active/inactive tại mốc hiện hành.
3. Nhóm/role và entitlement hiệu dụng đúng phạm vi nhiệm vụ.
4. Không có nhóm hoặc quyền mặc định quá rộng so với chính sách.
5. Nếu ứng dụng yêu cầu đăng nhập hoặc kích hoạt lần đầu, tình trạng đó được phân biệt với kết quả tạo account.
6. Các hệ thống bắt buộc đã hoàn tất hoặc lỗi được ghi nhận và chuyển đúng owner.

Thông báo cho người dùng phải phân biệt **đã tạo account**, **đang chờ cấp quyền** và **sẵn sàng sử dụng**. Việc gửi lệnh thành công chỉ chứng minh yêu cầu đã được chấp nhận ở một bước, chưa chứng minh end-to-end readiness.

## 6. SCIM hỗ trợ tạo account như thế nào?

**System for Cross-domain Identity Management (SCIM)** là bộ chuẩn cho biểu diễn và quản lý người dùng/nhóm qua các hệ thống. Với ứng dụng hỗ trợ, bộ máy provisioning có thể tạo hoặc cập nhật người dùng và nhóm qua API theo khả năng cụ thể của ứng dụng.

Ví dụ payload **minh họa** cho một SCIM User. Các giá trị sau chỉ là dữ liệu giả; hành vi nhận field và provisioning phải kiểm tra theo sản phẩm đích.

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "externalId": "P-1024",
  "userName": "minh.nguyen@example.test",
  "name": {
    "givenName": "Minh",
    "familyName": "Nguyen"
  },
  "displayName": "Nguyen Minh",
  "emails": [
    {
      "value": "minh.nguyen@example.test",
      "type": "work",
      "primary": true
    }
  ],
  "active": false
}
~~~

Trong ví dụ, `externalId` giúp hệ thống gửi giữ quan hệ ánh xạ theo quy ước đã thống nhất, còn **`id` của resource do hệ thống nhận cung cấp** sau khi tạo. Trường `active=false` mô tả ý định giữ account chưa hoạt động, nhưng ý nghĩa thực thi, khả năng sửa trạng thái, xử lý nhóm và việc thu hồi phiên **phụ thuộc ứng dụng và cấu hình**.

Một chu trình kỹ thuật có thể gồm:

1. Xác định account đã có qua mapping đáng tin cậy hoặc cơ chế tra cứu được hỗ trợ.
2. Gửi yêu cầu CREATE nếu thực sự cần tạo mới.
3. Lưu account ID trả về và quan hệ identity–target account.
4. Đồng bộ thuộc tính và nhóm/role phù hợp phạm vi hỗ trợ.
5. Đọc lại đối tượng để xác nhận status, liên kết và thuộc tính thiết yếu.
6. Theo dõi lỗi, retry có giới hạn, đối soát thay đổi và xử lý xung đột một cách an toàn.

**Không giả định mọi SCIM implementation đều giống nhau.** Có ứng dụng không hỗ trợ đầy đủ cập nhật nhóm, vô hiệu hóa hoặc xóa; có ứng dụng giữ session/token riêng. Vì vậy, cần kiểm chứng **khả năng provisioning và deprovisioning của từng đích** ngay từ lúc tích hợp.

## 7. Vai trò của RBAC và ABAC sau khi account được tạo

Một account mới thường chưa có đủ quyền nghiệp vụ. IAM cần tính **tập quyền mong muốn** dựa trên thông tin đã xác nhận:

- **RBAC (Role-Based Access Control):** Gán quyền thông qua vai trò công việc, ví dụ `sales_rep` hoặc `finance_analyst`.
- **ABAC (Attribute-Based Access Control):** Áp các điều kiện như bộ phận, dự án, khu vực dữ liệu, môi trường, trạng thái làm việc, thời gian hiệu lực và ngữ cảnh truy cập.
- **SoD (Separation of Duties):** Ngăn tổ hợp quyền xung đột như vừa tạo vừa tự phê duyệt giao dịch.
- **JIT/đặc quyền tạm thời:** Chỉ cấp quyền nhạy cảm trong cửa sổ và điều kiện được duyệt khi phù hợp.

| Trường hợp | Account có thể tồn tại? | Quyền nên có |
|---|---|---|
| Hồ sơ Joiner được duyệt nhưng chưa tới ngày bắt đầu | Có thể chuẩn bị theo chính sách | Chưa cho phép truy cập công việc nếu chưa tới mốc |
| Nhân viên Sales ngày đầu | Có | Quyền cơ bản và CRM theo khu vực/nhiệm vụ |
| Nhân viên chưa được duyệt quyền export toàn công ty | Có | Không tự có quyền export dữ liệu rộng |
| Nhà thầu dự án A đến ngày kết thúc hợp đồng | Có trong thời hạn hợp lệ | Quyền tài nguyên dự án A, có hạn rõ ràng |
| Nhân viên chuyển sang vai trò mới | Account có thể giữ nguyên | Tính lại quyền mới và thu hồi quyền cũ |
| Nhân viên đã rời tổ chức | Hồ sơ có thể được lưu theo chính sách | Đường truy cập cần thu hồi phải hết hiệu lực |

**Account creation** và **entitlement provisioning** có thể là các bước trong cùng workflow, nhưng phải có trạng thái và bằng chứng riêng. Việc gắn một người vào nhóm `all-users` không đủ để biết mọi quyền thực tế của nhóm đó có phù hợp với cá nhân này hay không.

### Ví dụ tính quyền mong muốn

~~~python
# Pseudocode minh họa, không phải chính sách sẵn dùng.
def desired_access(identity, engagement, now):
    if identity.proofing_status != "approved":
        return set()

    if engagement.status != "active":
        return set()

    if now < engagement.start_at:
        return set()

    if engagement.end_at is not None and now >= engagement.end_at:
        return set()

    if engagement.role == "sales_rep":
        return {
            ("crm", "customer.read", engagement.region),
            ("crm", "customer.update", engagement.region)
        }

    if engagement.role == "finance_analyst":
        return {
            ("finance", "invoice.read", engagement.approved_scope)
        }

    return set()
~~~

Đây là **mã giả biểu diễn nguyên tắc tính quyền**. Hệ thống thật cần xử lý nhiều engagement hợp lệ, gói quyền bổ sung, SoD, phân loại dữ liệu, sai lệch trạng thái, quyền kế thừa và các trường hợp tạm ngừng. **Quyền quyết định tại API/ứng dụng** vẫn phải kiểm tra điều kiện hiện hành; chỉ ẩn nút giao diện không phải kiểm soát đủ mạnh.

## 8. Tránh tạo account trùng và sai liên kết

Một trong các lỗi phổ biến là một sự kiện onboarding chạy hai lần, dẫn đến hai account cùng đại diện cho một người nhưng có quyền không nhất quán. Nguy hiểm hơn là **gắn nhầm account cũ của người khác** vào một identity mới vì trùng email hoặc tên.

### 8.1. Tính lặp an toàn (idempotency)

Một workflow nên bảo đảm cùng sự kiện hợp lệ được xử lý lại **không tạo thêm account hoặc quyền dư thừa**. Có thể dựa vào ID nguồn, bản ghi tương quan identity–target, khóa idempotency hoặc khả năng tra cứu/tìm account mà ứng dụng hỗ trợ.

~~~text
Sự kiện Joiner E-1001, personId=P-1024

Lần 1:
  identity P-1024 -> tạo account IdP ID-88
  identity P-1024 -> tạo account CRM CRM-503
  lưu mapping và readback

Lần 2 (sự kiện bị gửi lại):
  thấy E-1001 đã xử lý hoặc mapping còn hợp lệ
  xác minh/cập nhật trạng thái mong muốn nếu cần
  KHÔNG tạo ID-89 hoặc CRM-504 chỉ vì nhận lại sự kiện
~~~

Nếu API trả về xung đột, không nên tự kết luận account cùng username là đúng người. Cần đối chiếu nguồn và mapping đáng tin cậy trước khi tiếp tục.

### 8.2. Cập nhật trễ hoặc sai thứ tự

Ví dụ, sự kiện **Leaver** được phát sau nhưng lại đến IAM trước một sự kiện **Joiner** đã bị lưu trong hàng đợi. Nếu IAM xử lý vô điều kiện, một sự kiện cũ có thể kích hoạt lại account đã thu hồi.

Nên có **trạng thái hiện hành tại nguồn có thẩm quyền**, phiên bản hoặc timestamp đáng tin cậy của biến cố và quy tắc đối chiếu trước khi kích hoạt. Khi dữ liệu mâu thuẫn, workflow nên dừng/đưa vào xử lý ngoại lệ thay vì quyết định tùy tiện.

### 8.3. Rejoiner

Một người đã nghỉ việc rồi trở lại có thể vẫn có hồ sơ identity và account cũ ở trạng thái vô hiệu hóa. Có thể **khôi phục** một account nếu chính sách và hệ thống hỗ trợ, nhưng phải:

- Xác minh lại căn cứ quan hệ làm việc và identity đúng người.
- Kiểm tra account cũ có còn thuộc cùng chủ thể và có thể tái sử dụng an toàn.
- Tính quyền mới; không khôi phục mặc định mọi nhóm/role cũ.
- Đánh giá phương thức xác thực, token, recovery và thông tin liên hệ.
- Đọc lại trạng thái ứng dụng sau quá trình kích hoạt.

## 9. Trạng thái account và mô hình kích hoạt

Nên tách **trạng thái quan hệ nghiệp vụ** khỏi **trạng thái kỹ thuật của account**. Một ví dụ thiết kế:

| Trạng thái | Ý nghĩa | Điều kiện chuyển đi |
|---|---|---|
| `PENDING_SOURCE` | Thiếu dữ liệu/căn cứ được duyệt | Nguồn xác nhận tính hợp lệ |
| `STAGED` | Account đã được chuẩn bị, chưa mở truy cập | Đạt mốc kích hoạt và điều kiện bảo mật |
| `PROVISIONING` | Đang cấp phát vào IdP/ứng dụng | Kết quả đọc lại hoặc lỗi được ghi nhận |
| `READY` | Các đích bắt buộc đã có account/quyền phù hợp | Kích hoạt sử dụng theo chính sách |
| `ACTIVE` | Được phép sử dụng và vẫn đáp ứng điều kiện | Mover, suspend, Leaver hoặc hết hiệu lực |
| `SUSPENDED` | Đình chỉ theo yêu cầu nghiệp vụ/bảo mật | Xử lý căn cứ mở lại hoặc thu hồi |
| `DEPROVISIONING` | Đang thu hồi quyền/tài khoản | Đối soát kết quả từng hệ thống |
| `DISABLED` | Account đã bị vô hiệu hóa theo phạm vi áp dụng | Chỉ có thể mở lại qua quy trình hợp lệ |
| `ERROR` | Một hay nhiều đích bị lỗi | Retry/khắc phục có kiểm soát |

Đây là **mô hình nghiệp vụ tham khảo**, không phải bộ trạng thái chuẩn SCIM hay IdP nào. Các ứng dụng có thể chỉ hỗ trợ enabled/disabled hoặc active/inactive; IAM cần ánh xạ trạng thái giữa hệ thống và mô tả rõ trạng thái tổng hợp.

### Quy tắc quan trọng

**READY không nhất thiết đồng nghĩa ACTIVE.** Một account có thể đã được provision và kiểm chứng từ trước ngày làm việc nhưng vẫn chưa được phép đăng nhập. Ngược lại, account tại IdP có thể active trong khi ứng dụng bắt buộc chưa được tạo, khiến onboarding **chưa hoàn tất**.

Cũng không nên coi một account `disabled` là “đã xóa mọi quyền”. Khi chuyển sang Leaver, cần đánh giá từng ứng dụng, nhóm, quyền trực tiếp, phiên và token riêng.

## 10. Xử lý lỗi, retry, rollback và trạng thái một phần

Quy trình Joiner thường đi qua nhiều hệ thống, nên **không có bảo đảm giao dịch nguyên tử trên toàn bộ IdP và các ứng dụng**. Ví dụ:

~~~text
HR Joiner:         APPROVED
Identity record:   CREATED
IdP account:       CREATED
Email application: CREATED
CRM account:       FAILED (SCIM timeout)
Repository:        PENDING

Kết quả tổng: PARTIALLY_PROVISIONED
Không được báo "Onboarding completed".
~~~

### 10.1. Xử lý lỗi có kiểm soát

- Phân biệt **lỗi tạm thời** (timeout, dịch vụ tạm gián đoạn) với **lỗi dữ liệu/xung đột** (thiếu trường, username trùng, mapping mâu thuẫn).
- Ghi lại **ID sự kiện, identity, ứng dụng đích, mã tương quan, bước xử lý và trạng thái hiện tại**, không ghi credential hoặc giấy tờ nhạy cảm.
- Chỉ retry theo cơ chế có tính lặp an toàn; kiểm tra xem yêu cầu trước đã tạo account dù phản hồi bị timeout hay chưa.
- Với lỗi không thể tự khắc phục, chuyển người sở hữu ứng dụng/nhóm IAM xử lý và hiển thị trạng thái phù hợp cho helpdesk.
- Sau khi sửa lỗi, **đọc lại account và quyền** thay vì chỉ căn cứ vào HTTP status của lệnh gửi.

### 10.2. Có phải rollback mọi account nếu một đích lỗi?

Không có một đáp án chung. Rollback hoặc giữ account ở trạng thái không hoạt động phụ thuộc vào:

- Chính sách an toàn khi onboarding một phần.
- Phụ thuộc giữa các ứng dụng và điều kiện cho phép làm việc.
- Khả năng thu hồi/hủy account ở từng đích.
- Rủi ro xóa account đã tồn tại hợp lệ trước đó.
- Yêu cầu lưu giữ và chứng cứ kiểm toán.

**Không xóa bừa một account chỉ để “trả hệ thống về nguyên trạng”.** Nếu tài khoản đã được liên kết với identity từ trước hoặc phục vụ engagement khác, xóa có thể gây hỏng dữ liệu. Nên định nghĩa hành động bù trừ theo **ownership và sự kiện đã thực hiện**, rồi xác minh riêng.

## 11. Bảo mật và dữ liệu cá nhân khi tạo account

Account creation là điểm nhạy cảm vì sai một ánh xạ có thể mở quyền cho nhầm người. Những kiểm soát thực tế bao gồm:

| Rủi ro | Ví dụ | Hướng kiểm soát |
|---|---|---|
| Tạo account cho người chưa đủ điều kiện | Chưa xác minh hoặc chưa có quyết định gia nhập | Cổng kiểm tra proofing và nguồn có thẩm quyền |
| Account trùng hoặc linked sai | Hai người cùng tên bị dùng chung account | Định danh ổn định, đối soát xung đột, không ghép theo email thuần túy |
| Kích hoạt sớm | Nhà thầu vào production trước ngày hợp đồng | `startAt`, trạng thái inactive, kiểm soát hiệu lực ở ứng dụng |
| Cấp quá rộng | Mọi Joiner mặc định vào nhóm admin | RBAC/ABAC, vai trò chuẩn tối thiểu, review ngoại lệ |
| Lộ credential ban đầu | Mật khẩu gửi qua email/ticket | Kích hoạt bảo vệ, authenticator và MFA phù hợp |
| Tấn công kênh provisioning | Token SCIM/API có quyền quản trị bị lộ | Bảo vệ secret, giới hạn quyền, luân chuyển và logging |
| Thiếu truy vết | Không biết ai duyệt, khi nào account được tạo | Audit theo identity, event, chính sách và target |
| Sai lệch sau provisioning | IAM báo thành công nhưng ứng dụng chưa tạo | Readback và reconciliation thường xuyên |
| Dữ liệu vượt mục đích | Sao chép ảnh giấy tờ vào mọi app | Tối thiểu hóa thuộc tính, phân quyền và thời hạn lưu |

Đối với endpoint tạo account, cần giới hạn quyền của **provisioning service** trên từng ứng dụng, bảo vệ kết nối và thông tin xác thực, kiểm soát các thao tác có quyền cao. Người vận hành không nên dùng account dùng chung không thể truy vết để xử lý mọi trường hợp lỗi.

## 12. Khác biệt khi tạo service account

**Service account / workload identity** là danh tính máy, có vòng đời khác với tài khoản nhân viên nhưng vẫn chịu các nguyên tắc IAM: căn cứ hợp lệ, owner, quyền tối thiểu, thời hạn và khả năng thu hồi.

| Khía cạnh | Account cho con người | Service account |
|---|---|---|
| Chủ thể | Cá nhân đã được xác minh | Ứng dụng, workload, tác vụ tự động |
| Nguồn có thẩm quyền | HR, hợp đồng, sponsor | Danh mục dịch vụ, hệ thống triển khai, owner kỹ thuật |
| Cơ chế xác thực | SSO, passkey, MFA tùy chính sách | Workload identity, certificate, token máy hoặc cơ chế nền tảng |
| Vòng đời | Joiner–Mover–Leaver của cá nhân | Tạo dịch vụ, triển khai, thay ownership, ngừng dịch vụ |
| Quyền | Theo vai trò và nhiệm vụ con người | Theo API, tài nguyên, môi trường và phạm vi tác vụ |
| Thu hồi | Khi quan hệ hoặc nhiệm vụ kết thúc | Khi workload dừng, thay kiến trúc hoặc credential không còn an toàn |

Ví dụ, một nhân viên mới vào nhóm DevOps cần quyền vận hành hệ thống CI/CD. Điều đó **không có nghĩa nhân viên phải dùng trực tiếp secret của service account**. Danh tính máy nên có owner và quy trình quản lý credential riêng. Nếu nhà thầu biết secret khi tham gia dự án, sự kiện Leaver có thể yêu cầu xoay vòng hoặc thu hồi credential liên quan.

Tạo service account cũng cần tránh quyền cloud admin mặc định, token không hết hạn khi không cần và account không có owner sau khi nhóm dự án giải thể.

## 13. Tình huống thực hành: nhân viên Sales gia nhập

**Bối cảnh:** Lan bắt đầu làm việc tại bộ phận Sales từ ngày 01/06. HR đã duyệt hồ sơ, kết quả xác minh danh tính hợp lệ. Lan cần email và CRM với quyền chỉ đọc/cập nhật khách hàng khu vực miền Nam, nhưng chưa cần xuất toàn bộ khách hàng.

### 13.1. Luồng đúng kỳ vọng

1. Hệ thống HR phát biến cố Joiner chứa định danh ổn định, thời điểm hiệu lực, bộ phận và người quản lý.
2. IAM xác minh dữ liệu, giải quyết khả năng identity/account đã tồn tại và tạo hồ sơ hoặc liên kết phù hợp.
3. IdP được provision account cho Lan. Nếu chuẩn bị trước ngày 01/06, trạng thái phải bảo đảm chưa mở quyền công việc khi chưa đến hạn.
4. IAM áp vai trò `sales_rep` và phạm vi `region=south`, không mặc định cấp vai trò `sales_admin`.
5. Các ứng dụng Email và CRM nhận yêu cầu SCIM/API hoặc luồng tích hợp được phê duyệt.
6. IAM đọc lại account, trạng thái và quyền ở cả hai đích; ghi nhận các lỗi nếu có.
7. Đến mốc có hiệu lực, Lan đăng ký phương thức đăng nhập an toàn, truy cập qua SSO và được ứng dụng kiểm tra quyền khi thao tác.
8. Nếu CRM chưa provision thành công, hệ thống thể hiện trạng thái **đang chờ/lỗi** cho đúng ứng dụng và có kênh hỗ trợ; không tuyên bố onboarding hoàn tất.
9. Khi Lan chuyển sang Finance, IAM tính lại quyền Sales và Finance; khi Lan nghỉ việc, mọi account/quyền phải được thu hồi và đối soát theo Leaver.

### 13.2. Trường hợp sai và hậu quả

| Sai sót | Hậu quả có thể xảy ra | Cách xử lý |
|---|---|---|
| Dùng email là khóa duy nhất và phát hiện một account cũ cùng email | Liên kết nhầm người hoặc chuyển giao quyền trái phép | Xác minh identity/account ID và nguồn cấp |
| Mặc định tất cả nhân viên có quyền CRM admin | Cấp quyền vượt nhu cầu | Vai trò nền tảng tối thiểu, cấp mở rộng có kiểm soát |
| Tạo account CRM thất bại nhưng IAM vẫn báo DONE | Người mới không làm việc được, đội hỗ trợ khó tìm lỗi | Theo dõi từng target và readback |
| Kích hoạt trước ngày làm việc | Mở truy cập quá sớm | Tách pre-provisioning và mốc hiệu lực |
| Lần retry tạo thêm CRM account | Trùng account, khó offboarding | Correlation mapping và idempotency |
| Khi chuyển bộ phận chỉ thêm quyền | Tích lũy quyền cũ | Reconciliation toàn bộ entitlement |

## 14. Kiểm toán và đo lường chất lượng account creation

Đối với mỗi sự kiện Joiner, có thể cần ghi nhận:

- ID sự kiện, thời điểm, loại biến cố và nguồn phát hành.
- Identity ổn định, engagement và chính sách xác nhận đủ điều kiện.
- Quyết định tạo mới hay liên kết account có sẵn, lý do và ai phê duyệt ngoại lệ.
- Danh sách target, ID account trả về, trạng thái và quyền mong muốn.
- Kết quả gọi API/SCIM và **kết quả readback**.
- Thời gian hoàn tất, lỗi, retry, người khắc phục và trạng thái cuối.
- Liên kết về sau với các sự kiện Mover/Leaver để kiểm toán quyền tồn dư.

**Chú ý bảo mật nhật ký:** Những thông tin này phải được bảo vệ; không lưu mật khẩu, secret, session token, dữ liệu giấy tờ định danh thô hoặc thông tin nhạy cảm không cần thiết trong log.

Một số chỉ số:

| Chỉ số | Ý nghĩa | Bẫy đo lường |
|---|---|---|
| **Day-one readiness** | Tỷ lệ Joiner có đủ ứng dụng bắt buộc khi bắt đầu | Chỉ đo account IdP đã tạo là chưa đủ |
| **Time to provision** | Thời gian từ mốc được phép cấp đến khi target hoàn tất | Cần tách chờ phê duyệt, chờ đồng bộ, chờ người dùng kích hoạt |
| **Provisioning success rate** | Tỷ lệ target được tạo/cập nhật và readback đúng | HTTP 2xx không luôn đồng nghĩa end-to-end thành công |
| **Partial failure rate** | Tỷ lệ quy trình có ít nhất một target lỗi | Không gộp thành “onboarding thành công” |
| **Duplicate/conflict rate** | Tỷ lệ sự kiện gặp trùng mapping/account | Phân tích nguyên nhân, tránh sửa bằng auto-merge |
| **Least-privilege conformance** | Tỷ lệ quyền hiệu dụng khớp quyền được phê duyệt | Cần kiểm tra nhóm kế thừa/quyền trực tiếp |
| **Orphan-account discovery** | Account không có owner/identity/engagement hợp lệ | Cần kết hợp quy trình rà soát Mover/Leaver |

Không có SLA chung cho mọi doanh nghiệp. Mốc nội bộ cần xét mức rủi ro, ứng dụng bắt buộc, khả năng tự động hóa và trách nhiệm vận hành. Điều cốt lõi là **đo kết quả quyền sử dụng thực tế**, không chỉ đếm số lệnh CREATE.

## 15. Các câu hỏi kỹ thuật cần giải trước khi triển khai

**Câu 1: Có nên tạo account vào thời điểm HR nhập nhân viên mới?**

Có thể *pre-provision* nếu nguồn đã có thẩm quyền và chính sách cho phép, nhưng phải kiểm soát **thời điểm có hiệu lực**. Tạo bản ghi trước và mở quyền trước là hai hành động khác nhau.

**Câu 2: Nếu người dùng đã có account ở ứng dụng, có nên tái sử dụng?**

Chỉ khi đã liên kết chắc chắn account đó với identity đúng người và chính sách cho phép. Cần rà soát quyền, trạng thái, authenticator và engagement hiện hành; không tự nhận diện bằng tên/email giống nhau.

**Câu 3: IdP và SSO có tự tạo mọi account ứng dụng không?**

Không. Tùy ứng dụng dùng SCIM/API, JIT provisioning hoặc vận hành thủ công. SSO chủ yếu giải quyết liên kết xác thực; provisioning phải được thiết kế và kiểm chứng riêng.

**Câu 4: Một target lỗi, IAM có thể hiển thị “Hoàn tất” không?**

Không nên nếu target đó là phần bắt buộc của onboarding. Trạng thái phải phản ánh lỗi một phần, có chủ sở hữu và bước khắc phục. Có thể ghi rõ ứng dụng đã sẵn sàng và ứng dụng còn chờ.

**Câu 5: Account đã tạo có mặc nhiên được cấp quyền đúng không?**

Không. Quyền phải được tính và áp theo RBAC/ABAC, phạm vi nhiệm vụ, thời gian, SoD và ngoại lệ được duyệt. Ứng dụng còn phải kiểm tra quyền ở tầng nghiệp vụ.

**Câu 6: Tạo account ảnh hưởng gì tới Leaver?**

Nếu Joiner không lưu mapping **identity–account–target**, Leaver dễ bỏ sót account cục bộ, nhóm và token. Thiết kế ngay từ đầu phải cho phép liệt kê và thu hồi mọi quyền gắn với một identity/engagement.

## 16. Bài tập tự kiểm tra

### Tình huống A — Joiner bị gửi sự kiện hai lần

HR gửi hai lần cùng một biến cố tạo account cho An. Lần đầu IdP đã tạo account nhưng phản hồi đến IAM bị timeout. Lần thứ hai IAM chuẩn bị gọi CREATE thêm lần nữa.

**Bạn sẽ làm gì?**

Gợi ý: Kiểm tra mapping và trạng thái thực tế ở IdP, dùng ID sự kiện và định danh ổn định để bảo đảm lặp an toàn. Nếu chưa rõ account thuộc ai, dừng và đối soát; không tạo account thứ hai ngay chỉ vì timeout.

### Tình huống B — Có IdP nhưng không có CRM

Bình đăng nhập SSO thành công nhưng CRM báo “User not found”. Helpdesk yêu cầu Bình đổi mật khẩu.

**Vấn đề có thể ở đâu?**

Gợi ý: Phân biệt xác thực tại IdP với provisioning đến CRM. Kiểm tra kết quả SCIM/API, account mapping, trạng thái và yêu cầu JIT provisioning nếu có; việc đổi mật khẩu thường không xử lý đúng lỗi thiếu account.

### Tình huống C — Nhà thầu được chuẩn bị account sớm

Contractor C được chuẩn bị account bảy ngày trước khi hợp đồng bắt đầu. Tài khoản có nhóm cho phép truy cập tài liệu dự án ngay khi tạo.

**Điều gì cần thay đổi?**

Gợi ý: Tách account sẵn sàng về kỹ thuật khỏi quyền hiệu lực. Giữ account/chính sách ở trạng thái chưa truy cập cho tới mốc hợp lệ, đồng thời kiểm tra quyền thực tế trong ứng dụng và quyền qua chia sẻ trực tiếp.

### Tình huống D — Rejoiner và quyền cũ

Một nhân viên cũ trở lại sau một năm. Account của họ vẫn tồn tại ở trạng thái disabled, có các nhóm thuộc bộ phận cũ.

**Có nên kích hoạt lại tất cả?**

Gợi ý: Không tự phục hồi toàn bộ quyền. Cần xác minh đúng cá nhân, engagement mới, điều kiện reactivation, đánh giá authenticator, tính quyền theo vai trò mới và kiểm tra lại target.

## 17. Checklist thực hiện tạo account cho Joiner

- [ ] **Nguồn hợp lệ:** Biến cố Joiner đến từ HR/VMS hoặc nguồn được công nhận, có ngày hiệu lực và trạng thái được duyệt.
- [ ] **Identity:** Danh tính đã được xác minh ở mức phù hợp, có khóa ổn định; account cũ/trùng đã được xử lý an toàn.
- [ ] **Engagement:** Quan hệ làm việc, sponsor/manager, vị trí/dự án và mốc bắt đầu/kết thúc được xác định.
- [ ] **Tài khoản đích:** Danh sách ứng dụng bắt buộc và phương thức tạo account đã rõ (SCIM/API/JIT/manual).
- [ ] **Trạng thái:** Pre-provisioning và activation được tách biệt; chưa đến mốc thì chưa có quyền sử dụng trái chính sách.
- [ ] **Quyền:** RBAC/ABAC/SoD và nguyên tắc quyền tối thiểu áp dụng trên đúng tài nguyên, phạm vi và thời gian.
- [ ] **Authenticator:** Người dùng có cách kích hoạt tài khoản, đăng ký MFA/passkey và khôi phục an toàn; không lộ credential.
- [ ] **Mapping:** Lưu được quan hệ identity → account ID ở từng ứng dụng, không chỉ email/tên hiển thị.
- [ ] **Idempotency:** Event trùng hoặc timeout không tự tạo account mới; lỗi xung đột được xử lý có kiểm soát.
- [ ] **Readback:** Account, trạng thái và entitlement thực tế được xác nhận trên từng target bắt buộc.
- [ ] **Audit:** Có nguồn, ID sự kiện, quyết định, target, thời điểm, kết quả và người xử lý ngoại lệ.
- [ ] **Readiness:** Người dùng và helpdesk biết ứng dụng nào đã sẵn sàng, ứng dụng nào đang chờ.
- [ ] **Vòng đời:** Mover có thể tính lại quyền; Leaver có thể tìm và thu hồi mọi account/phiên/token liên quan.
- [ ] **Danh tính máy:** Service account có quy trình, owner, credential và quyền riêng, không dùng làm account dùng chung cho nhân viên.

**Ghi nhớ:** Trong **Joiner lifecycle**, tạo account là **quy trình có kiểm soát từ identity và engagement hợp lệ đến account sẵn sàng sử dụng ở từng hệ thống**. Chất lượng được đánh giá bằng **đúng người, đúng account, đúng thời gian, đúng quyền, kết quả đọc lại và khả năng quản trị xuyên suốt Joiner–Mover–Leaver**. Thiết kế tốt ngay từ lúc tạo account giúp IdP/SSO/SCIM và RBAC/ABAC phối hợp chính xác, thuận lợi cho kiểm toán và giảm tài khoản mồ côi, quyền truy cập tồn dư về sau.
