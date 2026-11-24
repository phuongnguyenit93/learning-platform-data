# Digital identity – mô hình danh tính số trong IAM lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **digital identity (danh tính số)** là gì và tại sao danh tính số không đồng nhất với tài khoản, tên đăng nhập, phương thức xác thực hoặc quyền truy cập.
- Nhận diện các thành phần của một mô hình danh tính số: **chủ thể, định danh, thuộc tính, mối quan hệ, trạng thái vòng đời, tài khoản liên kết và bằng chứng kiểm toán**.
- Phân biệt danh tính của nhân viên, nhà thầu, đối tác với danh tính phi con người như ứng dụng, dịch vụ và workload.
- Mô tả danh tính số đi qua các sự kiện **Joiner–Mover–Leaver (JML)**, đồng bộ qua **IdP, SSO, SCIM**, rồi trở thành đầu vào cho **RBAC/ABAC**.
- Thiết kế nguyên tắc liên kết tài khoản, quản trị thuộc tính, xác minh danh tính, thu hồi quyền và kiểm soát dữ liệu để giảm tài khoản mồ côi và quyền truy cập tồn dư.

## 1. Digital identity là gì?

**Digital identity** là tập hợp thông tin và mối quan hệ được một hệ thống sử dụng để **nhận biết, phân biệt và mô tả một chủ thể trong một ngữ cảnh số**. Chủ thể có thể là con người, ứng dụng, dịch vụ, thiết bị hoặc workload. Một danh tính số thường có **định danh**, **thuộc tính**, **liên kết với nguồn có thẩm quyền**, **trạng thái**, và quan hệ với tài khoản, phương thức xác thực hoặc hệ thống đích.

Ví dụ, một nhân viên có một bản ghi nhân sự trong hệ thống HRIS, một danh tính trong Identity Provider (IdP), tài khoản thư điện tử, tài khoản trên nền tảng quản lý mã nguồn và nhiều quyền tại các ứng dụng. Các bản ghi này có thể cùng tham chiếu đến **một chủ thể** nhưng không phải là cùng một đối tượng kỹ thuật.

Digital identity **không nhất thiết là “căn cước số” mang tính pháp lý**. Trong IAM của doanh nghiệp, đó có thể là một bản ghi danh tính được tổ chức công nhận cho mục đích quản trị truy cập. Việc một hệ thống tin vào danh tính đó phụ thuộc **nguồn phát hành, cách xác minh, thời điểm, phạm vi sử dụng và chính sách tin cậy**.

Một người cũng có thể có nhiều danh tính số độc lập theo ngữ cảnh: danh tính nhân viên, danh tính khách hàng ở dịch vụ ngoài và danh tính tại một tổ chức đối tác. Không nên mặc định có một định danh toàn cầu dùng được cho mọi nơi.

### 1.1. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Bản chất | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Subject (chủ thể)** | Người hoặc thực thể đang được đại diện | Nhân viên Lan, dịch vụ tổng hợp báo cáo | Có thể tồn tại ngoài hệ thống số |
| **Digital identity** | Mô hình nhận biết chủ thể trong một ngữ cảnh | Hồ sơ danh tính nội bộ của Lan | Có thể gắn nhiều tài khoản và thuộc tính |
| **Identifier (định danh)** | Giá trị dùng phân biệt/tham chiếu một danh tính trong phạm vi quy định | identityId = id-48372 | Cần rõ tính duy nhất và phạm vi sử dụng |
| **Attribute (thuộc tính)** | Dữ liệu mô tả chủ thể hoặc quan hệ hiện tại | Department = Finance; workerType = Contractor | Có nguồn, thời điểm hiệu lực và độ tin cậy |
| **Account (tài khoản)** | Bản ghi mà ứng dụng/hệ thống cho phép sử dụng tài nguyên | Tài khoản Git, CRM, VPN | Một danh tính có thể có nhiều account |
| **Principal** | Thực thể được hệ thống nhận biết để xác thực/thực thi chính sách | User principal, service principal | Có thể là đối tượng bảo mật trong một hệ thống riêng |
| **Authenticator / credential** | Phương tiện hoặc bằng chứng hỗ trợ xác thực | Passkey, chứng chỉ, mật khẩu, private key | Không nên lưu bí mật trong hồ sơ thuộc tính |
| **Session/token** | Trạng thái hoặc chứng cứ truy cập đã được thiết lập/phát hành | Phiên web, access token | Có vòng đời riêng; có thể còn tồn tại sau thay đổi danh tính |
| **Role/entitlement** | Vai trò hoặc quyền cụ thể được cấp | Read invoices, Repo maintainer | Là kết quả phân quyền, không phải danh tính |

**Quy tắc trọng tâm:** “Ai là chủ thể?” khác với “chủ thể chứng minh mình là ai?”, “có tài khoản nào?” và “được phép làm gì?”. Tách bạch bốn câu hỏi giúp tránh cấp nhầm quyền và thu hồi thiếu.

## 2. Cấu trúc một mô hình danh tính số

Một mô hình IAM hữu ích phải đủ dữ liệu để trả lời: danh tính thuộc về ai, do ai xác nhận, đang ở trạng thái nào, đã liên kết với tài khoản nào và thay đổi gì cần xảy ra khi thông tin nguồn thay đổi.

### 2.1. Sáu nhóm thông tin thiết yếu

| Nhóm | Trường tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| **Định danh nội bộ** | identityId, identityType | Khóa tham chiếu ổn định; phân biệt human và workload |
| **Thuộc tính mô tả** | displayName, department, organization, workerType | Phục vụ điều phối, xác định đối tượng, quản trị quyền |
| **Nguồn và bằng chứng** | authoritativeSource, sourceRecordId, verifiedAt | Ghi nguồn tạo và mức độ kiểm chứng phù hợp |
| **Trạng thái vòng đời** | lifecycleStatus, effectiveFrom, effectiveUntil | Quyết định khi nào kích hoạt, cập nhật, khóa hoặc đóng danh tính |
| **Quan hệ và sở hữu** | managerId, sponsorId, serviceOwnerId, accountLinks | Cho phép phê duyệt, bàn giao, liên kết tài khoản |
| **Truy vết thay đổi** | version, lastSyncedAt, correlationId | Hỗ trợ đồng bộ, chống sự kiện cũ và kiểm toán |

Ví dụ bản ghi danh tính rút gọn dưới đây là **mô hình minh họa**, không phải schema SCIM, OIDC hay khuôn mẫu bắt buộc:

~~~yaml
identityId: "id-48372"
identityType: "HUMAN"
source:
  system: "HRIS"
  sourceRecordId: "worker-8721"
  lastVerifiedAt: "2026-11-20T10:00:00+07:00"
attributes:
  displayName: "Nguyen A"
  department: "Finance"
  workerType: "EMPLOYEE"
  managerIdentityId: "id-12008"
lifecycle:
  status: "ACTIVE"
  effectiveFrom: "2026-11-18T08:00:00+07:00"
  effectiveUntil: null
  version: 12
accountLinks:
  - system: "Enterprise-IdP"
    accountId: "00u-example-42"
  - system: "Expense-App"
    accountId: "exp-user-1941"
audit:
  lastCorrelationId: "jml-event-9f18"
~~~

Lưu ý thiết kế:

- **identityId** nên là khóa bền vững trong phạm vi doanh nghiệp; không nên lấy email, họ tên hoặc phòng ban làm khóa vì các giá trị đó có thể đổi.
- **sourceRecordId** dùng liên kết với nguồn có thẩm quyền; chính sách xử lý hợp nhất/tách hồ sơ phải được xác định.
- **accountLinks** ghi quan hệ danh tính–tài khoản theo từng hệ thống. Chỉ lưu thông tin tham chiếu cần thiết, không nhúng mật khẩu, khóa bí mật hoặc token.
- **lifecycle.status** phản ánh trạng thái danh tính trong mô hình, không tự chứng minh tất cả tài khoản đích đã được vô hiệu hóa.
- Thuộc tính nhạy cảm chỉ được lưu khi cần cho mục đích hợp lệ, với quyền đọc và thời hạn lưu giữ thích hợp.

### 2.2. Định danh ổn định, định danh hiển thị và định danh liên kết

Ba loại định danh thường có vòng đời khác nhau:

1. **Khóa danh tính nội bộ:** ổn định trong phạm vi hệ thống quản trị; các sự kiện JML và audit dùng để đối chiếu.
2. **Định danh con người dễ đọc:** email, username, họ tên hiển thị; có thể đổi khi đổi tên, phòng ban hoặc tên miền.
3. **Định danh riêng của ứng dụng:** userId, accountId, subject identifier ở IdP/ứng dụng; không nhất thiết trùng nhau.

Ví dụ, người dùng chuyển email từ **a@company.example** sang **a@new-company.example**. Nếu email là khóa chính của hệ thống cấp quyền, một thay đổi hiển thị có thể bị hiểu thành “người cũ đã nghỉ, người mới gia nhập”, sinh tài khoản trùng hoặc bỏ sót tài khoản cũ. Khóa bất biến và bảng liên kết sẽ giúp phân biệt **thay đổi thuộc tính** với **thay đổi chủ thể**.

**Tính bất biến phải gắn với quy tắc cấp phát:** khóa không được tái sử dụng cho chủ thể khác. Khi tái tuyển dụng (rehire), cần chính sách quyết định liên kết hay tạo danh tính mới, dựa trên bằng chứng và yêu cầu tổ chức; không nối hai hồ sơ chỉ vì chúng có cùng tên.

### 2.3. Quan hệ là một phần của identity model

Một danh tính có thể có nhiều quan hệ với tổ chức và tài nguyên:

- **belongsTo / employedBy:** thuộc đơn vị hay loại lao động nào.
- **reportsTo / sponsoredBy:** ai quản lý hoặc bảo lãnh truy cập.
- **owns:** ai chịu trách nhiệm với tài khoản dịch vụ/workload.
- **linkedTo:** tài khoản ứng dụng nào đại diện danh tính.
- **memberOf / hasRole:** tham gia nhóm hoặc giữ vai trò nào.
- **delegatedBy:** quyền được ủy quyền tạm thời từ ai và hết hạn khi nào.

Quan hệ có **thời gian hiệu lực**. Người quản lý dự án cũ có thể từng phê duyệt quyền, nhưng khi dự án đóng, quan hệ đó không còn lý do tồn tại. Vì vậy, một mô hình danh tính chỉ lưu tên và email là thiếu dữ liệu cho quản lý vòng đời.

## 3. Danh tính con người và phi con người

Danh tính số không chỉ dành cho nhân viên. Mô hình quản trị cần phân biệt các lớp chủ thể vì nguồn tạo, xác minh và điều kiện kết thúc khác nhau.

| Loại | Nguồn xác nhận phổ biến | Cách thiết lập vòng đời | Rủi ro cần chú ý |
| --- | --- | --- | --- |
| **Nhân viên** | HRIS và quy trình nhân sự | Tuyển dụng, đổi vị trí, nghỉ việc | Quyền cũ không thu hồi khi Mover/Leaver |
| **Nhà thầu/đối tác** | Hợp đồng, sponsor, hệ thống vendor | Ngày bắt đầu/kết thúc, gia hạn, thay sponsor | Tài khoản còn mở sau hết hạn |
| **Khách mời bên ngoài** | Thư mời và xác nhận của sponsor | Mời, kích hoạt, hết hạn, thu hồi | Không có owner hoặc hết hạn rõ ràng |
| **Service/workload identity** | Hệ thống hạ tầng, CI/CD, quản lý dịch vụ | Tạo workload, triển khai, rotate, giải thể | Token/secret lâu dài, quyền rộng |
| **Thiết bị** | Đăng ký tài sản, hệ thống quản lý thiết bị | Enroll, thay chủ, mất thiết bị, retire | Thiết bị không còn được quản lý nhưng vẫn được tin cậy |

Trong mô hình, **human identity** có thể dùng nguồn nhân sự; **non-human identity (NHI)** cần nguồn khác như service registry hoặc inventory hạ tầng. Không nên gắn tài khoản dịch vụ với mã nhân viên của người tạo ra như thể người ấy là chủ sở hữu vĩnh viễn.

Một nhân viên có thể vừa có tài khoản người dùng bình thường vừa có tài khoản quản trị riêng phục vụ nhiệm vụ đặc quyền. Hai tài khoản này nên được **liên kết cùng chủ thể**, đồng thời duy trì chính sách xác thực và phân quyền riêng. Khi nhân viên nghỉ, cả hai đều thuộc phạm vi thu hồi.

## 4. Danh tính số vận hành trong kiến trúc IAM như thế nào?

### 4.1. Từ nguồn dữ liệu tới quyền tại ứng dụng

~~~mermaid
flowchart LR
  A["HRIS / hợp đồng / service registry"] -->|"Nguồn sự kiện và thuộc tính"| B["Identity registry / IGA"]
  B -->|"Lifecycle, người quản lý, role"| C["IdP / Directory"]
  C -->|"SSO: SAML hoặc OIDC"| D["Ứng dụng / relying party"]
  B -->|"Provision / deprovision: SCIM hoặc API"| D
  B -->|"Policy, nhóm, quyền"| E["Ứng dụng / cloud / hạ tầng"]
  D -->|"Tài khoản và quyền thực tế"| F["Reconciliation"]
  E -->|"Trạng thái thực tế"| F
  F --> B
  B --> G["Audit / SIEM"]
  C --> G
  D --> G
  E --> G
~~~

Mỗi thành phần giải quyết một phần riêng:

- **Nguồn có thẩm quyền (authoritative source):** xác nhận các sự kiện và thuộc tính thuộc trách nhiệm của nguồn đó. Ví dụ HRIS có thể là nguồn về trạng thái làm việc; hệ thống quản lý dịch vụ là nguồn về owner workload.
- **Identity registry / Identity Governance and Administration (IGA):** hợp nhất tham chiếu, lưu mô hình danh tính, điều phối workflow Joiner–Mover–Leaver, cấp/thu hồi quyền và rà soát.
- **Identity Provider (IdP):** quản lý định danh, phương thức xác thực và phát hành tín hiệu/claim xác thực cho ứng dụng.
- **SSO:** hỗ trợ đăng nhập vào nhiều ứng dụng qua quan hệ tin cậy với IdP, thường dùng các giao thức như OIDC hoặc SAML.
- **SCIM/API provisioning:** tạo, sửa, vô hiệu hóa tài khoản và có thể cập nhật nhóm ở hệ thống đích tùy khả năng ứng dụng.
- **Ứng dụng/cloud:** nơi quyết định hoặc thực thi quyền truy cập cuối cùng.
- **Đối soát (reconciliation):** kiểm tra trạng thái thực tế có khớp trạng thái mong muốn; phát hiện sai lệch và lỗi đồng bộ.

**Không có thành phần đơn lẻ nào bảo đảm toàn bộ vòng đời danh tính.** SSO không tự động cấp đúng quyền, và vô hiệu hóa tại IdP không mặc định hủy mọi phiên hoặc token đã tồn tại ở ứng dụng đích.

### 4.2. Xác thực và phân quyền phụ thuộc danh tính theo cách khác nhau

**Authentication** kiểm tra bằng chứng đăng nhập; **authorization** quyết định hành động nào được phép. Hai bước cùng có thể sử dụng thuộc tính danh tính nhưng có tiêu chí riêng.

Ví dụ, một ứng dụng nhận ID token hợp lệ từ IdP cho nhân viên A. Token có thể chứng minh danh tính đã được xác thực theo quan hệ tin cậy, nhưng ứng dụng vẫn phải kiểm tra A có được **xem hóa đơn của phòng ban X** hay không. Câu trả lời có thể đến từ role, policy ABAC, điều kiện tài nguyên hoặc quyền trong ứng dụng.

Khi xử lý token, ứng dụng cần kiểm tra các yếu tố phù hợp với giao thức như **chữ ký hoặc cách xác minh được hỗ trợ, issuer, audience, hạn sử dụng** và điều kiện phiên. Claim như email hoặc tên nhóm là thông tin theo phạm vi thời điểm token được phát hành; thay đổi HRIS chưa chắc làm token cũ lập tức hết hiệu lực.

### 4.3. Liên kết danh tính qua federation

Trong **federated identity**, IdP phát hành khẳng định hoặc token để ứng dụng khác tin vào kết quả xác thực. Ứng dụng cần một cách ánh xạ chủ thể nhận từ IdP đến tài khoản nội bộ.

Các lựa chọn ánh xạ cần tránh nhầm lẫn:

- **OIDC:** trường subject identifier (thường gọi là **sub**) được hiểu cùng với issuer; không nên mặc định sub là email, hoặc là định danh toàn cầu giữa mọi issuer. Một số triển khai dùng subject theo cặp (pairwise), có thể khác nhau giữa các nhóm ứng dụng.
- **SAML:** NameID hoặc thuộc tính được chỉ định dùng để liên kết; tính ổn định phụ thuộc cấu hình IdP và Service Provider.
- **Just-in-Time provisioning:** một số ứng dụng tự tạo tài khoản ở lần đăng nhập đầu tiên; cần chính sách bảo đảm việc tạo đó được phép và không sinh account ngoài kiểm soát.
- **Account linking:** chỉ liên kết khi có đủ bằng chứng, tránh gán quyền của tài khoản cũ cho một chủ thể khác do email/username bị tái sử dụng.

Điều này giúp giải thích vì sao **digital identity** cần mô hình liên kết nhiều hệ thống, thay vì coi một trường email là khóa cho mọi nơi.

## 5. Bảo đảm danh tính đúng: xác minh và chất lượng dữ liệu

### 5.1. Identity proofing và enrollment

**Identity proofing** là quá trình xác lập đủ tin cậy rằng một chủ thể chính là người/thực thể được khai báo, theo mức độ bảo đảm cần thiết. Trong môi trường doanh nghiệp, việc này có thể dựa trên tuyển dụng, hồ sơ hợp đồng, kiểm tra giấy tờ, quy trình trực tiếp hoặc nguồn xác minh phù hợp. **Enrollment** là bước đăng ký danh tính và gắn phương thức xác thực, account hoặc thông tin liên kết vào hệ thống.

Một luồng Joiner ví dụ:

1. Nguồn có thẩm quyền xác nhận nhân viên đã được tuyển và ngày bắt đầu có hiệu lực.
2. Quy trình xác minh đối chiếu thông tin cần thiết và xác định không nhầm chủ thể/trùng hồ sơ.
3. Identity registry tạo **identityId** và bản ghi vòng đời.
4. Hệ thống cấp tài khoản IdP, đăng ký phương thức xác thực an toàn và xác định tập quyền ban đầu theo nhu cầu.
5. SCIM/API tạo tài khoản ứng dụng; kết quả được đọc lại và đối soát.
6. Audit ghi nhận nguồn, phê duyệt, tài khoản đích, thời điểm và kết quả thực thi.

Chất lượng bảo đảm danh tính nên **tương xứng rủi ro tài nguyên**. Quy trình cho người truy cập tài liệu phổ thông không nhất thiết giống quy trình trao quyền quản trị hệ thống thanh toán.

### 5.2. Quản trị thuộc tính: ai được quyền nói điều gì?

Một thuộc tính chỉ đáng tin khi biết **nguồn, phạm vi, thời gian hiệu lực, cách cập nhật**. Không nên mặc định mọi field do một hệ thống cung cấp đều chính xác hoặc có quyền ghi đè lên tất cả nơi khác.

| Thuộc tính | Nguồn có thẩm quyền minh họa | Câu hỏi kiểm soát |
| --- | --- | --- |
| workerStatus, startDate, endDate | HRIS / nguồn quản lý hợp đồng | Sự kiện có hiệu lực từ khi nào? |
| department, manager | HRIS / hệ thống tổ chức | Bao lâu mới đồng bộ tới IdP? |
| serviceOwner, workloadPurpose | Service registry / nền tảng hạ tầng | Owner có còn hoạt động và chấp nhận trách nhiệm? |
| MFA enrollment | IdP / hệ thống xác thực | Credential có còn được phép dùng? |
| App entitlement | Ứng dụng đích / IGA | Đây là quyền theo chính sách hay ngoại lệ thủ công? |

Khi department trong HRIS đổi nhưng IdP chưa cập nhật, chính sách **ABAC dựa vào department** có thể ra quyết định theo dữ liệu cũ. Nếu ứng dụng lấy thuộc tính từ token phát hành trước sự kiện Mover, độ trễ còn kéo dài tới lúc token được làm mới hoặc phiên bị đánh giá lại.

Vì thế, identity model cần chính sách **độ mới thuộc tính**, phương án xử lý khi thiếu/sai dữ liệu và kiểm soát thích hợp cho quyết định có rủi ro cao.

### 5.3. Trùng danh tính và nhầm liên kết

Các tình huống khó bao gồm:

- Một người có hai hồ sơ do tái tuyển dụng hoặc dữ liệu từ hai nguồn.
- Hai người cùng tên và ngày sinh gần nhau.
- Email cũ được cấp cho người mới trong khi ứng dụng dùng email để liên kết tài khoản.
- Một nhân viên đồng thời là nhà thầu ở đơn vị liên kết.
- Một danh tính được gộp/tách nhầm sau thay đổi tổ chức.

Giải pháp cần quy tắc **match/merge/split** có bằng chứng, có người chịu trách nhiệm đối với trường hợp không rõ ràng, lưu lịch sử và chặn tự động liên kết khi mức tin cậy không đủ. Sai liên kết nguy hiểm vì hệ thống có thể **chuyển quyền và dữ liệu của người A sang người B** mà mọi bước xác thực sau đó vẫn “hợp lệ”.

## 6. Vòng đời danh tính số theo Joiner–Mover–Leaver

Mô hình JML là cách liên kết thông tin nhân sự với vòng đời danh tính và quyền thực tế. Không phải mọi danh tính đều theo đúng ba trạng thái tuyến tính: có thể có chuyển vị trí nhiều lần, tạm nghỉ, tái gia nhập hoặc gia hạn hợp đồng.

### 6.1. Trạng thái và chuyển trạng thái

~~~mermaid
stateDiagram-v2
  [*] --> PENDING: Có hồ sơ nguồn hợp lệ
  PENDING --> ACTIVE: Xác minh và kích hoạt
  ACTIVE --> ACTIVE: Mover / đổi thuộc tính và quyền
  ACTIVE --> SUSPENDED: Tạm ngưng theo chính sách
  SUSPENDED --> ACTIVE: Xác minh và tái kích hoạt
  ACTIVE --> DEACTIVATING: Leaver / hết hạn
  SUSPENDED --> DEACTIVATING: Leaver / hết hạn
  DEACTIVATING --> INACTIVE: Thu hồi đã xác nhận
  INACTIVE --> [*]: Lưu trữ / hủy theo chính sách
~~~

Sơ đồ là **ví dụ trạng thái nghiệp vụ**, không phải tiêu chuẩn bắt buộc. Trạng thái **DEACTIVATING** hữu ích khi đã phát lệnh khóa nhưng một số ứng dụng vẫn chưa xác nhận thu hồi. Trạng thái **INACTIVE** chỉ nên được kết luận dựa trên tiêu chí hoàn tất được tổ chức xác định.

**Quan trọng:** trạng thái danh tính trong registry, trạng thái account tại IdP và trạng thái truy cập thực tế tại từng ứng dụng là **ba lớp trạng thái khác nhau**. Một người có thể có lifecycleStatus = INACTIVE trong dữ liệu nguồn nhưng vẫn còn account enabled tại SaaS do lỗi deprovision.

### 6.2. Joiner: tạo danh tính đúng nguồn, đúng thời điểm

Khi có sự kiện Joiner, hệ thống cần quyết định:

- Chủ thể đã được xác minh chưa? Có thuộc danh mục được phép cấp danh tính không?
- Có danh tính đã tồn tại không; nếu có, quy tắc rehire/duplicate nào áp dụng?
- Ngày bắt đầu có hiệu lực khi nào và cần kích hoạt account trước bao lâu?
- Role và thuộc tính nào được cấp mặc định; quyền nào đòi phê duyệt riêng?
- Ứng dụng nào được provision, ai chịu trách nhiệm và ai nhận cảnh báo khi lỗi?

Tạo account quá sớm hoặc từ nguồn chưa xác minh sẽ làm gia tăng khả năng danh tính giả mạo hoặc quyền truy cập không có cơ sở nghiệp vụ.

### 6.3. Mover: cập nhật danh tính, tính lại quyền

Mover là mọi thay đổi ảnh hưởng ngữ cảnh và quyền: phòng ban, chức danh, tổ chức, người quản lý, dự án, khu vực, trạng thái lao động hoặc cấp độ nhạy cảm. Mover có thể cần:

1. Cập nhật thuộc tính nguồn và phiên bản hồ sơ.
2. Tính lại quyền phù hợp từ **trạng thái hiện tại**.
3. **Thu hồi quyền cũ** không còn lý do tồn tại; xét các ràng buộc phân tách nhiệm vụ (SoD).
4. Cấp quyền mới sau khi được phê duyệt theo mức rủi ro.
5. Đối soát ứng dụng đích và đánh giá phiên/token có còn mang điều kiện cũ.
6. Ghi nhận audit và kết quả thực thi.

Ví dụ: Lan rời nhóm Support để gia nhập Finance. Nếu hệ thống chỉ thêm role Finance nhưng không gỡ quyền truy cập hệ thống khách hàng, Lan sẽ tích lũy quyền (privilege creep). Trong identity model, một thay đổi **department** không chỉ là cập nhật hồ sơ; nó có thể kích hoạt nhiều thay đổi authorization trên các tài nguyên liên quan.

### 6.4. Leaver: đóng danh tính và thu hồi các đường truy cập

Khi chủ thể rời tổ chức, quy trình cần tìm được **mọi account liên kết** và xử lý cả thông tin xác thực/phiên có thể hoạt động độc lập:

- Vô hiệu hóa đăng nhập mới tại IdP và cơ chế truy cập khác theo chính sách.
- Gửi lệnh deprovision đến ứng dụng qua SCIM/API; theo dõi các hệ thống không hỗ trợ tích hợp.
- Thu hồi quyền nhóm, role, ACL, tài khoản đặc quyền, truy cập từ xa và cấp quyền cục bộ.
- Xử lý session, refresh token, API token, khóa SSH và chứng chỉ theo khả năng từng nền tảng.
- Đối soát trạng thái cuối tại từng ứng dụng; xử lý retry và ngoại lệ chưa đóng.
- Lưu audit và dữ liệu cần thiết theo chính sách, đồng thời tách **lưu hồ sơ** khỏi **quyền được đăng nhập**.

**Không nên dùng duy nhất một cờ “disabled” để chứng minh Leaver hoàn tất trên toàn doanh nghiệp.** Việc xóa vĩnh viễn thông tin danh tính cũng không nhất thiết là thao tác đầu tiên; có thể cần giữ hồ sơ tối thiểu để đối soát, điều tra hoặc tuân thủ chính sách lưu giữ.

### 6.5. Thuộc tính thời gian: event, effective, observed

Một hệ thống đa ứng dụng cần phân biệt:

| Thời điểm | Mục đích |
| --- | --- |
| **eventCreatedAt** | Khi nguồn phát sinh sự kiện |
| **effectiveAt** | Khi trạng thái/quan hệ nghiệp vụ cần có hiệu lực |
| **receivedAt** | Khi hệ thống điều phối nhận sự kiện |
| **appliedAt** | Khi hệ thống đích thực thi thay đổi |
| **verifiedAt** | Khi đã kiểm tra trạng thái thực tế |

Ví dụ người nghỉ việc có **effectiveAt = 18:00**, nhưng kết nối SaaS bị lỗi và chỉ **verifiedAt = 18:12**. Nếu chỉ lưu thời điểm yêu cầu được gửi, tổ chức không đo được khoảng quyền truy cập tồn dư 12 phút tại SaaS.

Để xử lý sự kiện trễ hoặc lặp, cần quản lý **version/order**, idempotency, retry có giới hạn, cảnh báo khi quá hạn và đối soát định kỳ. Không để một sự kiện Mover cũ đến muộn khôi phục role đã bị thu hồi.

## 7. Digital identity là dữ liệu đầu vào cho RBAC và ABAC

### 7.1. Vai trò và quyền không phải thuộc tính nhận dạng bất biến

**RBAC (Role-Based Access Control)** gán quyền thông qua vai trò. Identity model có thể cung cấp ngữ cảnh để gán role, ví dụ workerType = EMPLOYEE, jobFunction = ACCOUNTANT. Tuy nhiên, **role được cấp** và **quyền thực tế** cần quản lý như thực thể phân quyền có phê duyệt và lịch sử riêng.

**ABAC (Attribute-Based Access Control)** dùng các thuộc tính của chủ thể, tài nguyên, hành động và ngữ cảnh. Ví dụ:

~~~text
ALLOW view_invoice IF
    subject.lifecycleStatus == ACTIVE
    AND subject.department == resource.ownerDepartment
    AND subject.assuranceLevel >= requiredAssurance
    AND resource.classification <= subject.clearance
ELSE DENY
~~~

Đây là **mã giả chính sách**, không phải một ngôn ngữ ABAC tiêu chuẩn. Trong thực tế, việc quyết định phải dựa vào nguồn thuộc tính có thẩm quyền, độ mới hợp lệ và quy tắc xử lý khi thiếu dữ liệu.

### 7.2. So sánh hai cách khai thác identity model

| Tiêu chí | RBAC | ABAC |
| --- | --- | --- |
| Đầu vào chính | Role được gán cho danh tính | Thuộc tính danh tính, tài nguyên, hành động, ngữ cảnh |
| Mạnh ở | Cấu trúc quyền theo vị trí/nhiệm vụ phổ biến | Ràng buộc theo dự án, phòng ban, khu vực, thời điểm |
| Rủi ro từ dữ liệu | Role cũ không được gỡ khi Mover | Thuộc tính sai, stale hoặc đến từ nguồn không tin cậy |
| Kiểm soát quan trọng | Role mining/review, least privilege, SoD | Quản trị nguồn thuộc tính, kiểm thử policy, mặc định từ chối |

Mô hình kết hợp thường có ích: role “Invoice Reader” thể hiện năng lực cơ bản, còn ABAC yêu cầu hóa đơn thuộc **đơn vị mà người dùng hiện được phép truy cập**.

**Nguyên tắc:** đánh giá quyền cần dựa trên trạng thái danh tính và entitlement **thực tế**. Không giả định rằng IdP đã đổi thuộc tính đồng nghĩa ứng dụng hoặc token cũ đã đổi điều kiện authorization.

## 8. Digital identity của tài khoản dịch vụ và workload

Với ứng dụng, bot và dịch vụ, câu hỏi “ai tạo tài khoản” không đủ để quản trị vòng đời. Danh tính phi con người nên mô tả **workload nào**, **mục đích nào**, **chạy ở đâu**, **ai sở hữu** và **đang cần quyền gì**.

Một ví dụ mô hình rút gọn:

~~~yaml
identityId: "svc-analyst-etl-01"
identityType: "WORKLOAD"
displayName: "Analytics ETL Production"
ownerTeam: "Data Platform"
serviceOwnerIdentityId: "id-61203"
environment: "PRODUCTION"
purpose: "Đọc dữ liệu nguồn và ghi vào kho phân tích"
runtime: "cluster-analytics-prod"
lifecycleStatus: "ACTIVE"
credentialMethod: "WORKLOAD_IDENTITY_FEDERATION"
approvedPermissions:
  - "source-data:read"
  - "warehouse-staging:write"
lastReviewedAt: "2026-11-12T09:00:00+07:00"
~~~

Điểm cần quản lý:

- **Owner có trách nhiệm:** nếu người chịu trách nhiệm nghỉ, ownership phải được bàn giao và quyền/credential được rà soát; workload sản xuất cần kế hoạch chuyển đổi tránh gián đoạn.
- **Không chia sẻ tùy tiện:** mỗi workload nên có danh tính và phạm vi quyền đủ hẹp để dễ truy vết.
- **Thông tin xác thực ngắn hạn:** ưu tiên managed identity, workload federation hoặc chứng thực tự động khi nền tảng hỗ trợ, giảm secret cố định.
- **Quản lý bí mật:** nếu buộc dùng khóa/token lâu dài, lưu ở secret manager, có cơ chế rotate/revoke, không để trong repository hoặc log.
- **Kết thúc đúng vòng đời:** khi dịch vụ ngừng vận hành, thu hồi quyền và credentials, kiểm tra phụ thuộc rồi hủy tài khoản theo chính sách.
- **Theo dõi hành vi:** log phải phân biệt workload, owner và thao tác, tránh tất cả dịch vụ cùng dùng một principal.

## 9. Tính toàn vẹn, bảo mật và quyền riêng tư của danh tính số

### 9.1. Các rủi ro xuất phát từ chính identity model

| Rủi ro | Hậu quả | Biện pháp kiểm soát |
| --- | --- | --- |
| Hồ sơ giả hoặc xác minh không đầy đủ | Cấp quyền cho chủ thể không hợp lệ | Xác minh từ nguồn tin cậy, phê duyệt và lịch sử bằng chứng |
| Trùng hoặc nối sai danh tính | Một người nhận tài khoản/quyền của người khác | Định danh ổn định, quy tắc match/merge, xử lý ngoại lệ |
| Thuộc tính cũ hoặc sai | Quyền bị cấp/giữ sai sau Mover | Quản trị nguồn, sự kiện có phiên bản, kiểm tra độ mới, reconciliation |
| Account ngoài danh mục | Leaver không được thu hồi đủ | Khám phá account, liên kết chủ thể và đối soát với nguồn |
| Truy cập trực tiếp vào dữ liệu danh tính | Lộ thông tin cá nhân, nguy cơ giả mạo | Phân quyền chi tiết, mã hóa phù hợp, giảm dữ liệu lưu và log |
| Tài khoản đặc quyền không gắn owner | Khó truy trách nhiệm, thu hồi sai/thiếu | Liên kết principal–owner, PAM, review theo kỳ |
| Danh tính dịch vụ dùng credential lâu dài | Bị lạm dụng khi khóa lộ hoặc không được rotate | Credential ngắn hạn, quản lý bí mật và vòng đời riêng |

### 9.2. Tối thiểu hóa dữ liệu và phân tách mục đích

Danh tính số có thể mang dữ liệu cá nhân. Thiết kế cần xác định **thuộc tính nào thật sự cần** cho mục đích xác thực/phân quyền, ai có quyền đọc, chia sẻ cho ứng dụng nào và lưu giữ đến khi nào. Một ứng dụng chỉ cần role và mã danh tính không nhất thiết phải nhận ngày sinh, số giấy tờ hoặc hồ sơ nhân sự chi tiết.

Các thực hành hữu ích:

1. Dùng identifier theo phạm vi khi có thể; tránh phát tán số định danh nhạy cảm khắp hệ sinh thái.
2. Chỉ phát hành claim cần thiết trong token SSO; bảo vệ token và cấu hình quan hệ tin cậy.
3. Duy trì bản đồ nguồn thuộc tính, phân loại dữ liệu và kiểm soát truy cập vào registry.
4. Hạn chế log dữ liệu nhạy cảm và bí mật; vẫn giữ đủ trường truy vết giao dịch.
5. Áp dụng lịch sử/retention theo yêu cầu tổ chức; bảo đảm offboarding thu hồi truy cập dù cần giữ một phần hồ sơ để kiểm toán.

### 9.3. Nhật ký và khả năng giải trình

Để chứng minh vòng đời danh tính đã được thực thi, nên có audit trail gồm:

- **identityId**, danh tính tác nhân thực hiện, hệ thống đích và đối tượng bị tác động.
- Loại sự kiện JML, nguồn phát, thời điểm có hiệu lực và phiên bản sự kiện.
- Giá trị/quan hệ thay đổi hoặc tham chiếu được bảo vệ đến bản ghi thay đổi.
- Phê duyệt, chính sách, lý do cấp quyền hoặc lý do ngoại lệ.
- Thao tác tạo/sửa/khóa tài khoản, kết quả tại ứng dụng, thời điểm xác minh.
- Correlation ID để nối yêu cầu với các thao tác đồng bộ và đối soát.

Nhật ký phải được bảo vệ khỏi chỉnh sửa trái phép và được truy cập theo nhu cầu công việc. Chỉ có log “đã gửi lệnh revoke” chưa đủ chứng minh quyền tại ứng dụng đã hết hiệu lực.

## 10. Tình huống thực tế: một danh tính, nhiều bản ghi kỹ thuật

Giả sử nhân viên **An** làm việc tại nhóm Support, có danh tính nội bộ **id-48372**, tài khoản IdP, tài khoản CRM, tài khoản kho mã và một tài khoản VPN.

### Giai đoạn Joiner

HRIS phát sự kiện tuyển dụng kèm mã hồ sơ đã xác minh. Registry tạo một danh tính với identityId bền vững, IdP tạo account và thiết lập MFA. Hệ thống SCIM/API cấp account CRM và repository theo role Support. Bảng accountLinks lưu định danh riêng từng ứng dụng.

**Điểm kiểm soát:** account liên kết đúng chủ thể, quyền được phê duyệt, trạng thái thực tế tại hệ thống đích khớp yêu cầu.

### Giai đoạn Mover

An chuyển sang nhóm Finance. HRIS đổi department; registry cập nhật version và tính lại role. Hệ thống thu hồi quyền CRM Support và VPN không còn phù hợp, đồng thời cấp quyền Finance theo approval. Nếu nhóm cũ không gỡ vì API lỗi, reconciliation phải báo lệch giữa **desired access** và **observed access**.

**Điểm kiểm soát:** Mover không chỉ thay thông tin danh tính mà còn thay quyền hiệu lực, thuộc tính trong policy và các phiên có thể còn hiệu lực.

### Giai đoạn Leaver

Ngày nghỉ có hiệu lực. IdP vô hiệu hóa đăng nhập mới; orchestration gửi SCIM/API deactivation và thu hồi các entitlement. CRM báo thành công, repository thất bại tạm thời. Trạng thái registry có thể ghi **DEACTIVATING** cho đến khi repository xử lý và xác minh xong. Đội phụ trách theo dõi ngoại lệ, phiên, token, VPN và tài khoản quản trị liên quan.

**Điểm kiểm soát:** kết luận Leaver hoàn tất từ **bằng chứng thực thi ở từng hệ thống**, không chỉ từ một trạng thái hồ sơ.

### Dòng dữ liệu minh họa

~~~text
HRIS.worker-8721
      |
      v
IdentityRegistry.id-48372
      |
      +--> IdP.account-42
      +--> CRM.user-703
      +--> Git.user-112
      +--> VPN.principal-9

Mover:
  identity.department: SUPPORT -> FINANCE
  desiredEntitlements: {finance-reader}
  observedEntitlements: {finance-reader, crm-support}
  reconciliation: EXTRA_ACCESS(crm-support)
  action: revoke crm-support, verify result
~~~

Ví dụ cho thấy lợi ích của việc tách **đối tượng danh tính**, **account liên kết** và **entitlement**. Một thay đổi thuộc tính có thể được diễn giải thành hàng loạt hành động mà vẫn xác định được hệ thống nào chưa hoàn thành.

## 11. Thiết kế và kiểm tra một identity model thực dụng

Khi xây dựng hệ thống quản lý vòng đời danh tính, nên trả lời được những câu hỏi sau.

| Câu hỏi thiết kế | Kỳ vọng |
| --- | --- |
| Định danh nội bộ có ổn định và không tái sử dụng không? | Không phụ thuộc email, họ tên hoặc phòng ban; có quy tắc rehire/merge |
| Mỗi loại subject có nguồn thẩm quyền rõ ràng không? | HRIS, hợp đồng, service registry, thiết bị… có trách nhiệm xác định |
| Thuộc tính có nguồn và thời gian hiệu lực không? | Có cơ chế đồng bộ, version và kiểm tra độ mới |
| Có thể tìm toàn bộ tài khoản đại diện một identity không? | Account linking, inventory, xử lý account mồ côi và ngoại lệ |
| Identity status có tách khỏi trạng thái account đích không? | Theo dõi desired state và observed state riêng |
| JML có khởi phát cấp, đổi, thu hồi quyền đúng thời điểm không? | Workflow, approval, retry, cảnh báo và xác minh |
| SSO và SCIM có được hiểu đúng phạm vi không? | SSO hỗ trợ xác thực; SCIM hỗ trợ provisioning theo khả năng ứng dụng |
| RBAC/ABAC có dựa trên thuộc tính/role hợp lệ không? | Chính sách, least privilege, SoD, xử lý thuộc tính cũ |
| Danh tính phi con người có owner và ngày/điều kiện kết thúc không? | Quản lý workload và vòng đời credential |
| Có đo được quyền tồn dư không? | Báo cáo lệch, tài khoản mồ côi, thời gian thu hồi thực tế |
| Có thể truy vết quyết định truy cập không? | Audit trail nối nguồn, approval, thực thi và xác minh |
| Dữ liệu danh tính được bảo vệ theo mục đích không? | Data minimization, least privilege, chính sách lưu giữ |

Các chỉ số vận hành có thể theo dõi bao gồm: **tỷ lệ danh tính liên kết được account**, **số tài khoản mồ côi**, **số thuộc tính stale**, **tỷ lệ JML hoàn tất tại toàn bộ hệ thống đích**, **thời gian xác minh thu hồi quyền**, **số quyền tồn dư sau Mover** và **tỷ lệ service identities có owner**. Mỗi chỉ số cần định nghĩa phạm vi và cách tính để không đánh đồng “đã gửi lệnh” với “đã thu hồi thành công”.

## 12. Câu hỏi tự đánh giá

1. Một nhân viên đổi địa chỉ email. Vì sao hệ thống không nên coi đây là một danh tính mới? Khóa và bảng liên kết nào giúp xử lý?
2. Vì sao tài khoản IdP, account CRM và account Git của cùng một người có thể có identifier khác nhau?
3. Danh tính đã chuyển sang INACTIVE nhưng một ứng dụng còn session hợp lệ. Đây là sai lệch ở những lớp trạng thái nào?
4. Role Finance được cấp đúng cho người chuyển bộ phận. Vì sao vẫn phải so sánh toàn bộ entitlement thực tế?
5. Một ứng dụng dùng email từ OIDC token để nối tài khoản cũ. Rủi ro gì xảy ra nếu email được tái sử dụng?
6. Service owner nghỉ việc nhưng workload phải chạy liên tục. Mô hình danh tính phi con người cần thay đổi những quan hệ và kiểm soát nào?
7. Khi HRIS đã cập nhật department nhưng ABAC vẫn cho phép xem dữ liệu bộ phận cũ, nên kiểm tra nguồn thuộc tính, token hay chính sách theo thứ tự nào?
8. Làm thế nào để chứng minh một sự kiện Leaver đã hoàn tất tại mọi ứng dụng thay vì chỉ hoàn tất trong identity registry?

## 13. Ghi nhớ

**Digital identity** là mô hình đại diện chủ thể trong ngữ cảnh số, gồm định danh ổn định, thuộc tính được quản trị, nguồn tin cậy, quan hệ, trạng thái vòng đời và liên kết tài khoản. **Tài khoản, credential, session và quyền truy cập là những đối tượng có vòng đời liên quan nhưng không đồng nhất với danh tính.**

Trong **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, quản trị tốt digital identity tạo nền tảng cho xác minh và cấp tài khoản khi Joiner, tính lại quyền khi Mover, thu hồi và đối soát khi Leaver. Kết hợp đúng **IdP, SSO, SCIM, RBAC/ABAC**, quản lý service identities và kiểm toán sẽ giảm quyền truy cập tồn dư và cho phép tổ chức giải thích **ai hoặc thực thể nào đang có quyền gì, vì sao và tới khi nào**.
