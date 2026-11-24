# Xác định account scope khi thiết kế chương trình IAM

Trong một chương trình **Identity and Access Management (IAM)**, “quản lý vòng đời danh tính” chỉ có hiệu quả nếu tổ chức biết chính xác **những tài khoản nào phải được quản lý, chúng nằm ở đâu, thuộc về ai và cần áp dụng kiểm soát nào**. Công việc xác định ranh giới đó gọi là **account scope**.

Một nhân viên có thể sở hữu tài khoản tại Identity Provider (IdP), ứng dụng SaaS, hệ thống nội bộ, kho mã nguồn và cơ sở dữ liệu. Khi họ chuyển bộ phận hoặc nghỉ việc, chỉ vô hiệu hóa tài khoản IdP chưa chắc đã thu hồi được tài khoản cục bộ, khóa API hoặc quyền quản trị trực tiếp trong các hệ thống khác. Ngược lại, đưa mọi tài khoản vào cùng một quy trình cấp quyền cũng có thể làm gián đoạn tài khoản dịch vụ hoặc tài khoản khôi phục khẩn cấp.

Bài học thuộc chương **Thiết kế chương trình IAM** của chủ đề **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Trọng tâm là xác định phạm vi quản trị tài khoản trong mô hình **Joiner–Mover–Leaver (JML)**, liên kết IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và mục tiêu giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích account scope và phân biệt nó với identity source, identity scope, entitlement scope và OAuth scope.
2. Phân loại tài khoản theo chủ thể sở hữu, loại hệ thống, mức đặc quyền, môi trường và phương thức quản lý.
3. Lập **account inventory** và **scope matrix** nêu rõ phạm vi, owner, sự kiện vòng đời, phương thức cấp/thu hồi và bằng chứng đối soát.
4. Thiết kế phạm vi kiểm soát cho tài khoản người dùng, tài khoản đặc quyền, tài khoản dịch vụ, danh tính máy, tài khoản chia sẻ và tài khoản khẩn cấp.
5. Quyết định phạm vi triển khai theo rủi ro, lập ngoại lệ có thời hạn và kiểm chứng mức bao phủ thực tế của IAM.

## 2. Account scope là gì?

**Account scope** là tập tài khoản kỹ thuật và quan hệ liên quan được một chương trình IAM xác định là thuộc trách nhiệm **kiểm kê, liên kết với danh tính/chủ sở hữu, áp chính sách vòng đời, quản lý quyền và giám sát** trong một phạm vi tổ chức, hệ thống hoặc giai đoạn triển khai.

Một account scope tốt phải trả lời được năm câu hỏi:

- **What:** Những loại tài khoản nào, kể cả tài khoản người dùng, quản trị, service account, API key và workload identity?
- **Where:** Tài khoản tồn tại ở tenant, ứng dụng, subscription, project, máy chủ hay môi trường nào?
- **Who/What owns it:** Tài khoản gắn với con người, đối tác, dịch vụ hoặc workload nào? Ai chịu trách nhiệm nghiệp vụ và kỹ thuật?
- **When:** Sự kiện nào tạo, thay đổi, khóa, vô hiệu hóa, xóa hoặc rà soát tài khoản?
- **How:** Cơ chế nào thực thi, xác minh và lưu bằng chứng cho các hành động đó?

**Phân biệt các khái niệm gần nhau:**

| Khái niệm | Câu hỏi trọng tâm | Ví dụ |
|---|---|---|
| **Identity scope** | Những thực thể danh tính nào thuộc IAM? | Nhân viên, nhà thầu, đối tác, khách hàng, workload. |
| **Identity source** | Hệ thống nào có thẩm quyền xác nhận danh tính và thuộc tính vòng đời? | HRIS là nguồn trạng thái lao động; catalog dịch vụ là nguồn owner workload. |
| **Account scope** | Những tài khoản cụ thể nào phải được kiểm kê và quản lý? | Tài khoản nhân viên tại SaaS A, tài khoản quản trị Linux, robot đồng bộ dữ liệu. |
| **Entitlement scope** | Những nhóm, vai trò, quyền nào phải được cấp, thu hồi hoặc rà soát? | Nhóm `finance-read`, vai trò `billing-admin`, quyền đọc bí mật. |
| **Authentication/SSO scope** | Những ứng dụng và tài khoản sử dụng cơ chế xác thực tập trung? | Tài khoản vào ứng dụng qua SAML hoặc OIDC. |
| **OAuth scope** | Những quyền được một token ủy quyền yêu cầu/cấp trong giao thức OAuth? | `read:profile`; không phải phạm vi kiểm kê account của chương trình IAM. |

Một tài khoản có thể thuộc **account scope** dù chưa thể đăng nhập qua SSO hoặc chưa hỗ trợ SCIM. Ví dụ, tài khoản quản trị local trên máy chủ vẫn có thể phải được kiểm kê, ràng buộc owner, đặt dưới PAM, luân chuyển mật khẩu và đối soát định kỳ.

### Identity khác account

**Identity** biểu diễn một thực thể hoặc một mối quan hệ được quản lý; **account** là định danh kỹ thuật tại hệ thống đích dùng để xác thực hoặc thực hiện thao tác. Quan hệ không nhất thiết là một-một:

- Một nhân viên có một identity nội bộ nhưng nhiều account ở IdP và các ứng dụng.
- Một người có account thông thường và account quản trị tách riêng để bảo vệ quyền đặc quyền.
- Một service account phục vụ workload cụ thể, không nên bị gán giả thành account của kỹ sư vận hành.
- Một tài khoản chia sẻ có thể được nhiều người sử dụng; cần cơ chế ghi nhận từng phiên/người vận hành vì không thể mặc định suy ra một owner cá nhân từ account name.
- Một account mồ côi có thể tồn tại trong ứng dụng mà chưa liên kết được với identity nào.

Vì thế, danh sách nhân viên trong HRIS hoặc danh sách người dùng trên IdP **chưa đủ** để khẳng định đã xác định xong account scope.

## 3. Các chiều cần xét khi khoanh vùng tài khoản

Không nên quyết định phạm vi chỉ bằng tên ứng dụng. Một ứng dụng có thể chứa nhiều loại tài khoản và nhiều cơ chế quản lý khác nhau.

| Chiều phân loại | Câu hỏi cần xác định | Giá trị ví dụ |
|---|---|---|
| **Chủ thể** | Ai/cái gì sử dụng tài khoản? | Employee, contractor, partner, customer, service, workload. |
| **Loại tài khoản** | Vai trò kỹ thuật của account là gì? | Standard user, privileged admin, shared, break-glass, service, machine. |
| **Hệ thống đích** | Account được lưu và có quyền ở đâu? | Directory, SaaS, máy chủ, database, cloud IAM, CI/CD, thiết bị mạng. |
| **Đơn vị triển khai** | Account thuộc tenant, organization, project hay môi trường nào? | Production, staging, development; tenant nội bộ và tenant đối tác. |
| **Mức đặc quyền** | Truy cập ảnh hưởng đến tài nguyên nào? | Read-only, dữ liệu nhạy cảm, quản trị người dùng, quản trị hạ tầng, root. |
| **Cách xác thực** | Ai kiểm soát việc đăng nhập? | Federation SAML/OIDC, tài khoản local, SSH key, API token, chứng chỉ, workload federation. |
| **Cách provision** | Có thể cấp/thu hồi bằng kỹ thuật nào? | SCIM, API, connector, IaC, PAM, thao tác có kiểm soát. |
| **Nguồn vòng đời** | Sự kiện Joiner/Mover/Leaver tới từ đâu? | HRIS, VMS, partner registry, service catalog, cloud orchestration. |
| **Owner và trách nhiệm** | Ai chứng nhận nhu cầu và xử lý ngoại lệ? | Application owner, service owner, manager, security owner. |
| **Tình trạng tài khoản** | Account đang hoạt động, bị khóa, hết hạn hay chưa xác minh? | Active, suspended, disabled, expired, orphaned, pending review. |

Một account có thể xuất hiện đồng thời trong nhiều chiều, chẳng hạn `service account + production + privileged + cloud + API-based`. Cần lưu chúng thành các thuộc tính của cùng một bản ghi quản trị để tránh đếm trùng.

### Phạm vi phải có hai lớp

**Lớp 1 — Discovery / visibility:** mọi tài khoản tìm được trong những hệ thống được xác định phải có thể được phân loại, kể cả account chưa thể tự động hóa. Đây là nền tảng phát hiện orphan account và quyền tồn dư.

**Lớp 2 — Lifecycle control:** xác định kiểm soát nào thực sự được bật cho mỗi loại account hoặc hệ thống: xác minh, phê duyệt, provisioning, deprovisioning, access review, credential rotation, reconciliation và audit.

Nếu một ứng dụng chưa hỗ trợ SCIM, điều đó chỉ giới hạn **phương thức tự động hóa**, không đủ để loại toàn bộ account của ứng dụng khỏi inventory và quy trình thu hồi.

## 4. Phân loại account và kiểm soát vòng đời tương ứng

### 4.1. Tài khoản người dùng thông thường

Tài khoản dành cho nhân viên, nhà thầu và đối tác thường có thể liên kết với identity nội bộ và sự kiện JML. Khi thiết kế scope, cần xác định:

- Account tại IdP, directory và từng ứng dụng đích nào phải được quản lý.
- Có bao nhiêu tài khoản cho một identity và khi nào được phép có tài khoản phụ.
- Chênh lệch giữa thời điểm tạo sẵn account và thời điểm được phép đăng nhập.
- Quy tắc thay đổi vai trò khi Mover và cách loại bỏ quyền cũ.
- Quy trình Leaver vô hiệu hóa, kết thúc phiên, thu hồi quyền, sau đó lưu giữ/xóa theo chính sách.

Ví dụ: đối với nhân viên, HRIS phát sinh sự kiện Leaver. IAM cần biết account ở IdP, ứng dụng quản lý công việc, kho mã nguồn và hệ thống nội bộ có thuộc scope hay không. Nếu chỉ quản lý tài khoản IdP, một tài khoản local riêng có thể tiếp tục tồn tại.

### 4.2. Tài khoản đặc quyền (privileged accounts)

Account quản trị hệ thống, cloud admin, database admin hoặc domain admin thường cần chính sách chặt hơn tài khoản thông thường. Scope phải bao gồm cả account cấp qua IdP và account đặc quyền tồn tại riêng ở đích.

Các yêu cầu thường gặp:

- Liên kết account với người có trách nhiệm hoặc cơ chế xác thực/ủy quyền được phê duyệt.
- Quyền tối thiểu, phân tách tài khoản làm việc thường ngày và tài khoản quản trị khi phù hợp.
- MFA, PAM, Just-in-Time/Just-Enough-Access (nếu có), thời hạn cấp quyền và ghi nhận phiên.
- Rà soát đặc quyền, kiểm tra account không sử dụng và thu hồi sau khi Mover/Leaver.
- Không coi việc thay đổi một nhóm trong IdP đã chắc chắn gỡ toàn bộ quyền quản trị trực tiếp tại cloud hoặc database.

### 4.3. Service account và danh tính máy

**Service account** thường được ứng dụng, tác vụ nền hoặc tích hợp sử dụng; **workload identity** gắn với tiến trình/dịch vụ đang chạy, có thể được cấp thông qua cloud IAM hoặc cơ chế liên kết danh tính thay vì mật khẩu tĩnh.

Trong inventory, mỗi tài khoản phi con người nên có:

| Trường cần biết | Mục đích |
|---|---|
| `serviceId` hoặc `workloadId` | Liên kết đến dịch vụ/workload có thật. |
| `businessOwner`, `technicalOwner` | Có người chịu trách nhiệm chấp thuận và xử lý sự cố. |
| `environment`, `resourceScope` | Biết account tác động tới production hay môi trường thử nghiệm. |
| `purpose` và `lastUsedAt` | Rà soát nhu cầu và phát hiện account có thể đã bỏ dùng. |
| `credentialType`, `rotationPolicy` | Kiểm soát khóa bí mật, certificate, key hoặc token. |
| `reviewAt`, `expiresAt` (nếu áp dụng) | Đặt hạn hoặc chu kỳ tái xác nhận. |

Không nên buộc một service account dùng chính `employeeId` của kỹ sư đã tạo nó. Khi người đó nghỉ việc, dịch vụ có thể vẫn còn nhu cầu hoạt động. Sự kiện Leaver cần kích hoạt rà soát/chuyển owner và thay thế credential có liên quan, còn việc dừng account phải dựa trên vòng đời dịch vụ hoặc quyết định quản trị phù hợp.

### 4.4. Tài khoản chia sẻ và break-glass

Tài khoản chia sẻ có thể tồn tại vì thiết bị cũ hoặc ứng dụng không hỗ trợ user riêng. **Break-glass account** dùng để khôi phục quyền quản trị khi hệ thống xác thực thông thường gặp sự cố.

Hai nhóm này cần được đưa vào scope với kiểm soát đặc biệt: owner xác định, lý do tồn tại, giới hạn quyền, cơ chế truy cập có ghi nhận cá nhân, bảo vệ credential, giám sát sử dụng và lịch rà soát. Không nên tự động khóa mọi break-glass account theo một luồng JML của một nhân viên bất kỳ, vì có thể làm mất khả năng khôi phục. Thay vào đó cần quản trị rõ chủ thể được phép sử dụng, cơ chế khẩn cấp và luân chuyển credential sau mỗi lần sử dụng hoặc khi người được ủy quyền rời tổ chức.

Các account chia sẻ mới nên được hạn chế; nếu ứng dụng hỗ trợ định danh cá nhân, cần xem xét chuyển đổi để có trách nhiệm và audit rõ ràng.

### 4.5. Tài khoản cục bộ và tài khoản cũ (legacy)

Một ứng dụng có thể hỗ trợ SSO cho người dùng mới nhưng vẫn tồn tại account local cũ hoặc tài khoản quản trị gốc. Khi lập scope, phải kiểm kê cả hai loại: account liên kết với IdP và account có credential riêng. Mọi account còn khả năng xác thực hoặc còn quyền phải được đánh giá.

Nếu hệ thống đích không có API tự động thu hồi, có thể dùng quy trình ticket với owner xác nhận, hạn xử lý và bằng chứng thay đổi. Giai đoạn chuyển đổi sang SCIM hoặc tự động hóa khác cần được ghi nhận trong kế hoạch, không được đánh dấu tài khoản là đã thu hồi chỉ vì ticket đã tạo.

## 5. Xác định hệ thống và ranh giới kỹ thuật

Account scope cần dựa trên danh sách **hệ thống thực tế đang chứa account**, gồm cả các đơn vị quản trị bên trong hệ thống:

- **IdP và directory:** tenant, domain, forest, nhóm và tài khoản đồng bộ/tách biệt.
- **SaaS:** mỗi tenant/workspace/organization; có thể gồm nhiều tài khoản cục bộ hoặc tài khoản được federate.
- **Cloud:** account/subscription/project, IAM role, user tĩnh, service principal và workload identity.
- **Hạ tầng:** Linux/Windows, database, network devices, container, Kubernetes cluster, secrets platform.
- **Developer tooling:** repository organization, CI/CD runner, bot account, deployment key, token.
- **Hệ thống nghiệp vụ:** ERP, CRM, tài chính, phân tích dữ liệu, hệ thống nội bộ và đối tác tích hợp.

Ví dụ tổ chức dùng cùng một SaaS tại **hai tenant**, một cho production và một cho thử nghiệm. Tích hợp SCIM chỉ kết nối tenant production không có nghĩa tenant thử nghiệm đã thuộc phạm vi provisioning. Scope phải ghi rõ cả **tên ứng dụng và định danh tenant**; nếu không sẽ phát sinh “đã tích hợp ứng dụng” nhưng bỏ sót account ở tenant còn lại.

### Account không đồng nghĩa với credential hoặc phiên

Một account có thể sử dụng nhiều yếu tố truy cập: password, khóa SSH, access key, API token, certificate, refresh token hoặc phiên đăng nhập. Chúng là **đối tượng kiểm soát liên quan** cần đưa vào *lifecycle control scope*, ngay cả khi hệ thống kiểm kê account chỉ có một bản ghi.

Ví dụ: vô hiệu hóa user trong ứng dụng không nhất thiết tự thu hồi một access token đã phát hành hoặc key tạo trước đó. Phải làm rõ loại credential nào hệ thống đích hỗ trợ thu hồi, thời hạn token và cách kiểm tra.

## 6. Lập account inventory có khả năng đối soát

Mục tiêu không đơn thuần là lấy được tổng số user, mà là xây dựng bản ghi chuẩn để chứng minh **tài khoản này được phát hiện ở đâu, thuộc về chủ thể nào và hiện chịu kiểm soát gì**.

| Trường inventory | Ý nghĩa |
|---|---|
| `targetSystemId` + `tenantId` | Hệ thống và phạm vi kỹ thuật nơi account tồn tại. |
| `nativeAccountId` | ID ổn định do hệ thống đích cung cấp. |
| `identityId` hoặc `serviceId` | Liên kết tới identity/chủ thể có thẩm quyền; có thể để trống khi đang điều tra. |
| `accountType` | Standard, privileged, service, workload, shared, break-glass... |
| `accountStatus`, `lastSeenAt`, `lastUsedAt` | Trạng thái tại đích và bằng chứng cập nhật. |
| `privilegeTier` và `entitlementRefs` | Mức rủi ro và tập quyền liên quan. |
| `lifecycleSource`, `ownershipSource` | Nguồn điều khiển vòng đời/owner. |
| `controlMode` | SCIM, API, PAM, IaC, manual with evidence, monitor-only. |
| `scopeDecision`, `scopePhase` | In scope, exception hoặc excluded, cùng giai đoạn triển khai. |
| `reviewOwner`, `reviewDueAt`, `exceptionId` | Người xét duyệt, hạn rà soát và ngoại lệ có thể truy vết. |

**Khóa duy nhất của account đích** nên dựa trên tổ hợp hệ thống + tenant/phạm vi + native account ID. Không nên dựa vào email, username hay display name vì chúng có thể thay đổi hoặc trùng nhau giữa các tenant.

Ví dụ bản ghi JSON ở lớp inventory:

~~~json
{
  "accountKey": {
    "system": "code-hosting",
    "tenant": "engineering-org",
    "nativeAccountId": "u-8721"
  },
  "accountType": "STANDARD_USER",
  "identityRef": "idn-1042",
  "ownerTeam": "Engineering",
  "environment": "PRODUCTION",
  "observed": {
    "accountStatus": "ACTIVE",
    "lastSeenAt": "2026-10-10T08:00:00Z"
  },
  "scope": {
    "decision": "IN_SCOPE",
    "phase": 1,
    "controlMode": "API",
    "lifecyclePolicy": "EMPLOYEE_JML"
  }
}
~~~

Ví dụ này minh họa cấu trúc dữ liệu, không phải định dạng API bắt buộc. Account hiện `ACTIVE` là **trạng thái quan sát từ hệ thống đích**, có thể khác trạng thái mong muốn do IAM tính từ nguồn danh tính. Cần lưu đủ cả hai để phát hiện sai lệch.

### Những trạng thái cần được phân biệt

Trong quản trị scope, ít nhất cần tách:

1. **Discovered:** tìm thấy account trong inventory.
2. **Classified:** đã xác định loại account, hệ thống và rủi ro.
3. **Correlated:** đã liên kết đáng tin cậy với identity/workload hoặc owner.
4. **Governed:** đã áp chính sách, owner, rà soát và cơ chế thu hồi.
5. **Provisioning managed:** có cơ chế kỹ thuật để tạo/sửa/vô hiệu hóa với xác nhận kết quả.

Một account **được phát hiện** chưa chắc đã **được quản trị**; một account **được quản trị** chưa chắc đã **có thể provision tự động**. Báo cáo mức bao phủ cần phân biệt những cấp độ này.

## 7. Ma trận scope và chính sách hành động JML

Mỗi đơn vị scope nên có một dòng quyết định: **loại account × hệ thống/tenant × nhóm chủ thể × lớp kiểm soát**. Ví dụ:

| Nhóm account | Quyết định scope | Sự kiện vòng đời | Cách xử lý chính | Bằng chứng hoàn thành |
|---|---|---|---|---|
| Nhân viên tại IdP | In scope, đợt 1 | Joiner/Mover/Leaver từ HRIS | Tạo/khóa IdP, rà soát nhóm, chấm dứt phiên theo chính sách | Trạng thái user và phiên sau thay đổi. |
| Nhân viên tại SaaS hỗ trợ SCIM | In scope, đợt 1 | JML từ nguồn nhân sự qua IAM | Provision/deprovision qua SCIM, đối soát nhóm/quyền | Trạng thái và quyền đọc lại từ SaaS. |
| Nhà thầu tại ứng dụng nội bộ | In scope, đợt 1 | Bắt đầu/hết hạn hợp đồng từ VMS | API hoặc ticket được xác nhận | Account disabled và quyền đã thu hồi. |
| Quản trị cloud | In scope, đợt 1 | Thay đổi vai trò, nghỉ việc, yêu cầu đặc quyền | PAM/JIT và thu hồi role trực tiếp | Danh sách role thực tế, log cấp/thu hồi. |
| Service account production | In scope, đợt 2 nếu chưa sẵn sàng | Tạo/ngừng workload, chuyển owner | Quản trị owner, quyền, credential; ưu tiên account rủi ro cao | Inventory và quyền/credential đã đối soát. |
| Account local trên hệ thống legacy | In scope, kiểm soát thủ công tạm | JML, sự kiện bảo mật, rà soát định kỳ | Ticket có owner và xác nhận tại hệ thống | Bằng chứng thao tác + kiểm tra lại trạng thái. |
| Tài khoản break-glass | In scope, kiểm soát chuyên biệt | Sử dụng khẩn cấp, đổi người giữ quyền, diễn tập | Bảo vệ credential, giám sát và kiểm tra định kỳ | Log truy cập, xác nhận luân chuyển/kiểm tra. |

**Lưu ý:** “Đợt 2” nghĩa là lộ trình tự động hóa hoặc mở rộng kiểm soát; không nhất thiết trì hoãn inventory, owner và đánh giá rủi ro đến đợt 2. Các tài khoản đặc quyền và phi con người có rủi ro lớn cần biện pháp tối thiểu từ giai đoạn đầu.

### Luồng quyết định cho account vừa được tìm thấy

~~~mermaid
flowchart TD
    A["Phát hiện account tại hệ thống / tenant"] --> B["Xác minh khóa native, loại account và rủi ro"]
    B --> C{"Liên kết được identity / service owner?"}
    C -- "Có" --> D["Gán owner và nguồn vòng đời"]
    C -- "Chưa" --> E["Đánh dấu uncorrelated / orphan candidate"]
    E --> F["Điều tra owner, mục đích, quyền và thời điểm sử dụng"]
    F --> G{"Được chấp thuận duy trì?"}
    G -- "Có" --> D
    G -- "Không" --> H["Cách ly hoặc thu hồi theo quy trình"]
    D --> I{"Có thể quản lý tự động?"}
    I -- "Có" --> J["Tích hợp API / SCIM / PAM / IaC"]
    I -- "Chưa" --> K["Quy trình thủ công có SLA và bằng chứng"]
    J --> L["Kiểm tra trạng thái thực tế và audit"]
    K --> L
    H --> L
~~~

“Orphan candidate” là nhãn cần điều tra. Không nên xóa ngay một tài khoản chỉ vì chưa liên kết được với owner, nhất là với tài khoản hệ thống có khả năng gây gián đoạn khi dừng. Tuy nhiên, account không xác định được chủ thể và có quyền cao phải được ưu tiên kiểm soát, cô lập hoặc thu hồi theo đánh giá rủi ro và quy trình ứng phó.

## 8. Áp account scope vào các giai đoạn Joiner–Mover–Leaver

### Joiner — tạo account theo phạm vi cần thiết

Một identity được xác nhận bắt đầu quan hệ với tổ chức chưa có nghĩa phải tạo tài khoản ở **mọi** hệ thống thuộc scope. IAM phải xác định role và điều kiện cấp quyền theo chính sách, dựa trên nguồn danh tính, RBAC/ABAC và phê duyệt.

Ví dụ nhân viên mới thuộc bộ phận kỹ thuật có thể cần IdP, kho mã và hệ thống quản lý công việc; quyền database production có thể cần phê duyệt bổ sung hoặc truy cập theo phiên. Scope cho biết **hệ thống và kiểu account nào phải được kiểm soát**, còn policy cho biết **account/quyền nào thực sự cần cấp**.

### Mover — rà soát tất cả account và entitlement bị ảnh hưởng

Khi thay đổi chức danh, phòng ban, đội dự án hoặc quan hệ hợp đồng, IAM cần truy vấn các account gắn với identity, tính lại quyền dự kiến và so sánh với trạng thái thực tế. Một thay đổi có thể làm:

- Thu hồi nhóm cũ ở IdP và ứng dụng.
- Gỡ quyền đặc quyền cấp trực tiếp ở tài nguyên.
- Tạo tài khoản ở một hệ thống mới nếu công việc mới cần.
- Đóng hoặc giới hạn account thứ cấp không còn lý do tồn tại.
- Chuyển người phê duyệt/owner cho quyền và tài khoản dịch vụ liên quan.

Quản lý account scope đầy đủ giúp phát hiện **quyền tồn dư** mà chỉ kiểm tra role ở IdP không thấy được.

### Leaver — phạm vi thu hồi phải khép kín

Một quy trình Leaver cần truy xuất mọi account đã tương quan với identity: IdP, SaaS, ứng dụng local, account privileged và credential được gán cá nhân. Sau đó IAM điều phối vô hiệu hóa đăng nhập, thu hồi phiên hoặc token khi được hỗ trợ, gỡ entitlement và kiểm tra ở đích.

Điều kiện kết luận không chỉ là “đã gửi yêu cầu deprovision”. Với mỗi hệ thống thuộc scope phải có:

1. Trạng thái mong muốn và thời điểm hiệu lực từ nguồn có thẩm quyền.
2. Hành động đã chạy và kết quả thực thi.
3. Trạng thái thực tế đọc lại từ hệ thống đích hoặc bằng chứng được owner xác nhận khi thao tác thủ công.
4. Xử lý ngoại lệ nếu hệ thống đích lỗi hoặc không thể thu hồi ngay.

Một số account phải được giữ dữ liệu cho mục đích kiểm toán hoặc lưu giữ hợp pháp sau khi quyền đã bị chặn. Cần phân biệt **disable access**, **revoke entitlement**, **delete account** và **delete retained data**; mỗi việc có thời điểm và thẩm quyền riêng.

### Luồng dữ liệu minh họa

~~~mermaid
flowchart LR
    S["Nguồn có thẩm quyền<br/>HRIS / VMS / Service Catalog"] --> R["Identity registry<br/>Liên kết identity ↔ account"]
    R --> P["JML + policy engine<br/>RBAC / ABAC / approval"]
    P --> I["IdP / SSO"]
    P --> A["SCIM / API / PAM / IaC / ticket"]
    I --> T["Phiên và xác thực"]
    A --> X["Account, quyền và credential<br/>ở hệ thống đích"]
    X --> V["Discovery / reconciliation"]
    I --> V
    V --> R
    V --> U["Audit / exception / owner review"]
~~~

**SSO giải quyết việc xác thực**, không thay thế inventory account hay deprovision ở đích. **SCIM giải quyết provisioning khi được hỗ trợ**, không tự xác định phạm vi tài khoản hay sự kiện nghỉ việc. **RBAC/ABAC xác định entitlement dự kiến**, nhưng cần đối soát account và quyền thực tế để tìm quyền cấp trực tiếp ngoài chính sách.

## 9. Thiết kế chính sách scope có thể kiểm tra

Một quyết định scope nên được biểu diễn như một cấu hình/tài liệu quản trị có phiên bản. Ví dụ:

~~~yaml
# Ví dụ minh họa cho thiết kế; không phải schema chuẩn của sản phẩm IAM.
scopeId: corp-iam-prod
owner: IdentityGovernanceTeam
systems:
  - systemId: collaboration-saas
    tenantId: corp-prod
    includedAccountTypes:
      - STANDARD_USER
      - PRIVILEGED_USER
    identityTypes:
      - EMPLOYEE
      - CONTRACTOR
    lifecycleSource:
      EMPLOYEE: HRIS
      CONTRACTOR: VMS
    controls:
      inventory: true
      correlation: true
      provisioning: SCIM
      accessReview: true
      reconcile: true
  - systemId: legacy-erp
    tenantId: production
    includedAccountTypes:
      - STANDARD_USER
      - LOCAL_ADMIN
    controls:
      inventory: true
      correlation: true
      provisioning: MANUAL_WITH_EVIDENCE
      accessReview: true
      reconcile: true
exceptions:
  - id: EXC-2026-014
    accountKey: legacy-erp/production/admin-local
    reason: "Chưa thể federate tài khoản quản trị"
    compensatingControls:
      - "Bảo quản credential qua PAM"
      - "Rà soát và ghi log truy cập"
    reviewOwner: InfrastructureSecurity
    reviewDueAt: "2026-12-31"
~~~

Thông số và ngày trong ví dụ chỉ minh họa. Một hệ thống có thể cần scope riêng theo môi trường vì production có mức rủi ro và quyền khác development. Quy tắc cấu hình phải được đối chiếu với danh sách tài khoản thực tế; không nên đánh đồng “tenant đã khai báo” với “mọi tài khoản trong tenant đã được quản trị”.

### Khi nào được đánh dấu out of scope?

Một quyết định **excluded / out of scope** cần có bằng chứng, owner và ngày rà soát. Ví dụ chương trình IAM cho nhân viên có thể tách hệ thống khách hàng B2C sang một chương trình CIAM chuyên trách. Khi đó cần ghi rõ **đơn vị nào vẫn chịu trách nhiệm quản trị account khách hàng** và ranh giới tích hợp dữ liệu giữa hai chương trình.

Không nên dùng nhãn out of scope chỉ vì hệ thống chưa có connector, chưa biết owner hoặc dữ liệu khó thu thập. Những trường hợp này nên được ghi là **in scope nhưng chưa tích hợp**, **chờ phân loại**, hoặc **ngoại lệ có biện pháp kiểm soát thay thế**, kèm người chịu trách nhiệm và thời hạn giải quyết.

## 10. Các bước xây dựng account scope trong dự án thực tế

### Bước 1 — Chọn mục tiêu quản trị và ranh giới tổ chức

Thống nhất tổ chức, pháp nhân, địa điểm, tenant và môi trường cần bao phủ; mục tiêu ưu tiên có thể là Leaver, đặc quyền, nhà thầu hoặc tài khoản phi con người. Nêu rõ hệ thống thuộc chương trình khác nhưng vẫn cần giao diện chuyển tiếp và owner.

**Đầu ra:** bản đồ ranh giới chương trình và tiêu chí xác định in-scope.

### Bước 2 — Thu thập inventory từ nhiều kênh

Khai thác dữ liệu thực tế từ IdP, ứng dụng, cloud, PAM, CMDB/catalog, HR/VMS, hệ thống ticket và chủ hệ thống. Nếu chỉ dựa vào một danh sách SSO hoặc hóa đơn SaaS, rất dễ bỏ sót tài khoản local, bot, tenant phụ và tài khoản không dùng SSO.

**Đầu ra:** inventory có nguồn phát hiện, timestamp và native account ID; các account chưa tương quan giữ trạng thái chưa xác minh.

### Bước 3 — Phân loại và gán chủ sở hữu

Tách human/non-human, standard/privileged/shared/break-glass, production/non-production; xác định nguồn vòng đời và owner. Kiểm tra liên kết danh tính bằng khóa ổn định của nguồn thay vì tự ghép vì trùng email.

**Đầu ra:** account taxonomy và danh sách orphan/duplicate/suspicious account cần điều tra.

### Bước 4 — Quyết định kiểm soát và ưu tiên rủi ro

Đánh giá mức đặc quyền, độ nhạy dữ liệu, khả năng truy cập ngoài mạng, ảnh hưởng khi account bị chiếm, giới hạn kỹ thuật và tần suất thay đổi. Đặt mức kiểm soát tối thiểu cho mọi account thuộc scope, sau đó xếp đợt tự động hóa.

**Đầu ra:** scope matrix với control mode, owner, yêu cầu kiểm tra và kế hoạch tích hợp.

### Bước 5 — Diễn tập toàn bộ JML và xử lý ngoại lệ

Chọn vài identity mẫu đại diện: nhân viên mới, người chuyển bộ phận, nhà thầu hết hạn, quản trị viên, service owner nghỉ việc. Theo dõi từ sự kiện nguồn đến account và quyền thực tế ở từng hệ thống. Thử tình huống connector lỗi, event đến trễ, account local và các ngoại lệ có thời hạn.

**Đầu ra:** kết quả diễn tập, danh sách sai lệch, giới hạn công nghệ và trách nhiệm xử lý.

### Bước 6 — Duy trì scope khi hệ thống thay đổi

Mỗi lần thêm SaaS, tenant, cloud account, workload hoặc tích hợp mới cần có cổng onboarding IAM. Inventory và ma trận scope được cập nhật theo thay đổi; owner nhận nhiệm vụ rà soát định kỳ; báo cáo phát hiện account không có owner hoặc khác trạng thái mong muốn.

**Đầu ra:** quy trình vận hành scope liên tục, thay vì bảng inventory chỉ đúng tại thời điểm khởi tạo dự án.

## 11. Đo lường mức bao phủ và tính hiệu quả

Một tổ chức có thể báo cáo “đã tích hợp 90% ứng dụng” nhưng vẫn bỏ sót tài khoản đặc quyền hoặc tài khoản cục bộ. Nên theo dõi ít nhất hai loại chỉ số: **mức bao phủ** và **hiệu quả thực thi vòng đời**.

| Chỉ số | Cách hiểu |
|---|---|
| **Discovered account coverage** | Số account đã được kiểm kê so với tổng account ước tính/đối chiếu theo các nguồn độc lập; nêu rõ độ tin cậy mẫu số. |
| **Ownership coverage** | Tỷ lệ account được gắn với identity hoặc service/workload owner có xác minh. |
| **Lifecycle-controlled coverage** | Tỷ lệ account trong scope đã có quy trình JML và đường thu hồi được xác nhận. |
| **Privileged coverage** | Tỷ lệ account đặc quyền được đưa vào PAM/đánh giá quyền và giám sát phù hợp. |
| **Leaver closure latency** | Thời gian từ lúc sự kiện nghỉ việc có hiệu lực đến khi mọi account bắt buộc trong scope được thu hồi và xác minh. |
| **Reconciliation drift** | Số account hoặc entitlement thực tế khác trạng thái mong muốn theo chính sách IAM. |
| **Orphan account rate** | Account chưa xác định được identity/owner trong một khoảng thời gian và theo loại rủi ro. |
| **Exception aging** | Số ngoại lệ quá hạn, nhất là account đặc quyền hoặc tài khoản không tự động hóa. |

Không nên tính “đã gửi yêu cầu thu hồi” là “đã thu hồi thành công”. Cần phân biệt trạng thái `REQUESTED`, `IN_PROGRESS`, `CONFIRMED` và `FAILED` hoặc `EXCEPTION` với bằng chứng kiểm tra. Một số ứng dụng chỉ hỗ trợ đọc trạng thái theo đợt; khi ấy phải công bố rõ độ trễ quan sát.

## 12. Những sai lầm phổ biến

1. **Đồng nhất danh sách IdP với toàn bộ account.** Dẫn tới bỏ sót account local, privileged, service và tenant khác.
2. **Xác định scope theo ứng dụng nhưng không theo tenant và account type.** Có connector cho một tenant vẫn để sót account ở tenant khác.
3. **Dùng tên đăng nhập/email làm khóa toàn cục.** Có thể ghép nhầm account, đặc biệt khi nhiều hệ thống và tài khoản phụ dùng tên giống nhau.
4. **Gọi hệ thống chưa có SCIM là out of scope.** Thực chất đây là hạn chế tự động hóa, vẫn cần inventory và thu hồi có kiểm chứng.
5. **Coi account được phát hiện là account đã được kiểm soát.** Thiếu owner, chính sách vòng đời và quyền truy cập vẫn tạo ra rủi ro.
6. **Bỏ qua đặc quyền hoặc service account để ưu tiên user thường.** Những account này có thể giữ quyền lớn và không tuân theo JML nhân viên thông thường.
7. **Đánh dấu Leaver hoàn thành sau khi khóa IdP.** Token, tài khoản local và entitlement trực tiếp có thể tiếp tục hoạt động.
8. **Ngoại lệ không có owner hoặc thời hạn.** Lâu dần trở thành vùng tối quản trị.
9. **Không tái phát hiện account sau khi onboarding ứng dụng.** Account mới, bot, khóa và tenant phụ được tạo ngoài quy trình sẽ lọt khỏi scope.

## 13. Tình huống thực hành

Một doanh nghiệp có 600 nhân viên, 80 nhà thầu, một IdP dùng SSO, ba tenant SaaS, hệ thống ERP cũ với account local, môi trường cloud production và một công cụ CI/CD dùng nhiều service account.

Một nhân viên thuộc nhóm tài chính sắp chuyển sang kỹ thuật. Người này sở hữu account IdP, SaaS quản lý công việc, ERP local, tài khoản kho mã và một cloud admin account được cấp cho dự án trước đây. Đồng thời người ấy được ghi là technical owner của robot CI/CD.

Hãy trả lời các câu hỏi sau:

1. Những account nào cần có trong inventory và nên dùng khóa nào để nhận diện riêng từng account/tenant?
2. Trường hợp nào là account của con người và trường hợp nào là account của workload? Nguồn nào quyết định vòng đời của từng loại?
3. Khi Mover, những account và entitlement nào cần được đối soát? Có thể giữ account nhưng gỡ quyền cũ trong tình huống nào?
4. Nếu ERP không hỗ trợ SCIM và cloud admin được cấp trực tiếp, bạn thiết kế đường thu hồi và bằng chứng hoàn thành thế nào?
5. Khi người này nghỉ việc sau đó, robot CI/CD có cần bị xóa ngay không? Phải chuyển owner và rà soát credential ra sao?
6. Bạn sẽ ghi nhận một tenant SaaS chưa tích hợp vào scope matrix và báo cáo tiến độ thế nào?

**Gợi ý cấu trúc câu trả lời:** lập bảng gồm `system/tenant`, `nativeAccountId`, `accountType`, `identityOrServiceOwner`, `source`, `JML event`, `controlMode`, `verification`. Đừng bỏ qua cloud admin, ERP local và robot CI/CD chỉ vì chúng không xuất hiện trong danh sách SSO.

### Tiêu chí nghiệm thu account scope

Một bản thiết kế đủ dùng để bắt đầu vận hành cần chứng minh:

- Mọi hệ thống/tenant trong ranh giới chương trình có owner và phương pháp discovery rõ ràng.
- Mỗi loại account được phân loại và có chủ thể hoặc quy trình điều tra khi chưa biết owner.
- Quan hệ account ↔ identity/service được liên kết bằng khóa ổn định, có dấu vết nguồn.
- Mỗi account thuộc scope có chính sách vòng đời, phương thức cấp/thu hồi và cách kiểm tra kết quả.
- Đặc quyền, tài khoản chia sẻ, break-glass, tài khoản local và non-human có kiểm soát riêng phù hợp.
- Các trường hợp chưa tự động hóa được ghi trong scope và có biện pháp thay thế, owner cùng thời hạn rà soát.
- Mức bao phủ và độ trễ thu hồi có thể đo bằng kết quả thực tế của hệ thống đích.

**Account scope là ranh giới trách nhiệm vận hành của IAM.** Khi ranh giới này được mô tả đến từng loại tài khoản và từng hệ thống đích, chương trình mới có thể thực thi Joiner–Mover–Leaver nhất quán, kiểm soát RBAC/ABAC, phát hiện tài khoản mồ côi và chứng minh quyền truy cập không còn tồn tại sau khi không còn nhu cầu.
