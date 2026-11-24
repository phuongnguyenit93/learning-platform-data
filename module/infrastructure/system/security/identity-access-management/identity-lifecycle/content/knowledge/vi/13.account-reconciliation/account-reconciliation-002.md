# So sánh identity source trong Account reconciliation

## 1. Bài toán: nhiều hệ thống cùng mô tả một danh tính

Trong **Identity and Access Management (IAM)**, một người có thể xuất hiện đồng thời trong hệ thống nhân sự (HRIS), nền tảng quản trị danh tính, **Identity Provider (IdP)**, thư mục doanh nghiệp và nhiều ứng dụng. Một máy chủ hoặc dịch vụ tự động cũng có thể xuất hiện trong hệ thống quản lý workload, IdP và các nền tảng cloud. Mỗi hệ thống có góc nhìn, trường dữ liệu và nhịp cập nhật riêng.

**So sánh identity source** là hoạt động đối chiếu các bản ghi danh tính từ những nguồn đó để xác định chúng có mô tả **đúng cùng một chủ thể**, có nhất quán về **trạng thái, tổ chức, vai trò, thời hạn** hay không, và những sai lệch nào cần điều chỉnh. Đây là bước cốt lõi của **account reconciliation**: đối soát giữa trạng thái tài khoản/quyền *đáng lẽ phải có* và trạng thái *thực tế đang tồn tại* trong các hệ thống.

Ví dụ, HRIS ghi nhận nhân viên Bình đã kết thúc hợp đồng; IdP đã vô hiệu hóa tài khoản đăng nhập; ứng dụng SaaS vẫn có tài khoản Bình ở trạng thái hoạt động. Việc ba hệ thống chứa cùng họ tên hoặc email không đủ để kết luận chúng là một danh tính duy nhất. IAM phải xác minh **liên kết tài khoản**, xác định trạng thái HR nào có thẩm quyền và kiểm tra quyền thực tế tại SaaS trước khi đánh dấu quá trình thu hồi hoàn tất.

Kết quả mong muốn là:

- Biết **nguồn nào có thẩm quyền** cho từng loại dữ liệu và sự kiện vòng đời.
- Liên kết đúng **person, employment, identity và account**, tránh nhập nhằng hoặc gộp sai người.
- Tìm được **missing account, orphan account, trạng thái sai, nhóm và quyền lệch**.
- Chỉ rõ **ai xử lý, hệ thống nào cần cập nhật, lúc nào cần hoàn tất và bằng chứng xác nhận**.
- Ngăn **quyền truy cập tồn dư** sau các sự kiện **Joiner–Mover–Leaver (JML)**.

## 2. Identity source là gì?

*Identity source* là hệ thống hoặc tập dữ liệu cung cấp thông tin về danh tính, thuộc tính, quan hệ hoặc tài khoản. Không phải mọi identity source đều là **nguồn có thẩm quyền** (*authoritative source*) cho tất cả các trường. Có nguồn quyết định trạng thái nghiệp vụ, có nguồn chỉ ghi nhận trạng thái kỹ thuật.

| Identity source | Thông tin thường cung cấp | Phạm vi có thể có thẩm quyền | Giới hạn cần hiểu |
| --- | --- | --- | --- |
| **HRIS** | Mã nhân sự, hợp đồng, phòng ban, ngày bắt đầu/kết thúc, quản lý | Quan hệ lao động và thuộc tính do HR quản trị | Không nhất thiết biết account, ACL hoặc token ở ứng dụng |
| **Hệ thống quản trị nhà thầu/đối tác** | Sponsor, tổ chức bảo trợ, hợp đồng và hạn cộng tác | Danh tính phi nhân viên theo quy trình của tổ chức | Không đồng nghĩa một hồ sơ nhân viên trong HRIS |
| **IAM governance / IGA** | Identity tổng hợp, phê duyệt, role, entitlement mục tiêu | Quyết định quản trị và quyền đã được phê duyệt | Quyền mục tiêu có thể khác quyền đang hiệu lực |
| **IdP / directory** | Account đăng nhập, trạng thái xác thực, nhóm, thuộc tính đồng bộ | Tài khoản và chính sách xác thực tại IdP | Không phải nơi quan sát đầy đủ account cục bộ và quyền ứng dụng |
| **Ứng dụng SaaS / on-premise** | Local account ID, vai trò, nhóm, ACL, session, token cục bộ | Trạng thái kỹ thuật thực tế trong chính ứng dụng | Không có thẩm quyền quyết định tình trạng lao động |
| **Danh mục dịch vụ / workload** | Service account, owner team, ứng dụng, môi trường | Vòng đời danh tính máy và người chịu trách nhiệm | Không thay thế nguồn HR cho nhân viên |
| **Hệ thống dự án/organization** | Thành viên dự án, tenant, ngày phân công | Tư cách và phạm vi dự án theo ủy quyền | Không mặc nhiên chứng minh quyền tài nguyên nhạy cảm |
| **Nhà cung cấp liên kết danh tính bên ngoài** | External subject, federation claim, trạng thái theo đối tác | Xác thực hoặc thuộc tính theo hợp đồng tin cậy | Cần kiểm tra ranh giới tin cậy, hợp đồng và độ mới của claim |

**Một nguồn có thẩm quyền theo trường dữ liệu**, không phải danh hiệu tuyệt đối của toàn hệ thống. Chẳng hạn HRIS có thể là nguồn chuẩn cho employment status, còn hệ thống dự án là nguồn chuẩn cho project assignment. Ứng dụng vẫn là nơi kiểm tra **effective access** của chính nó.

## 3. Cần so sánh những thực thể nào?

Các hệ thống thường đặt tên khác nhau cho những khái niệm liên quan. Đối soát tốt phải tách chúng:

| Thực thể | Câu hỏi | Ví dụ định danh |
| --- | --- | --- |
| **Person** | Đây là con người nào? | personId |
| **Employment / worker relation** | Người đó có quan hệ làm việc nào đang hiệu lực? | workerId, employmentId |
| **IAM identity** | Bản ghi danh tính số nào quản lý chủ thể? | identityId |
| **Account** | Tài khoản nào tồn tại trong hệ thống đích? | accountId, directory object ID |
| **Group / role assignment** | Người hoặc account đang thuộc nhóm, vai trò nào? | groupId, roleId |
| **Entitlement** | Có quyền gì trên tài nguyên nào? | resourceId, action, scope |
| **Workload identity** | Quy trình hoặc dịch vụ nào sử dụng danh tính máy? | workloadId, clientId |

Một người có thể có nhiều account; một người cũng có thể có nhiều giai đoạn tuyển dụng hoặc nhiều hợp đồng đồng thời. Vì vậy, quan hệ **person → employment → identity → account** không luôn là một–một.

~~~mermaid
flowchart LR
    HR["HRIS / Nguồn bảo trợ"] -->|"bản ghi công việc"| EMP["Employment / Sponsorship"]
    EMP -->|"liên kết đã xác minh"| ID["IAM identity"]
    ID -->|"liên kết account"| IDP["IdP account"]
    ID -->|"liên kết account"| APP["Application account"]
    IGA["IGA: quyền mục tiêu, phê duyệt"] -->|"expected state"| COMP["Reconciliation engine"]
    EMP --> COMP
    ID --> COMP
    IDP -->|"observed state"| COMP
    APP -->|"observed state"| COMP
    COMP -->|"sai lệch"| EX["Exception / Remediation"]
    EX -->|"đọc lại xác nhận"| COMP
~~~

Sơ đồ thể hiện luồng logic. Hệ thống triển khai thật có thể dùng nhiều connector, queue, API và kho dữ liệu trung gian; điều quan trọng là không đồng nhất **bản ghi mong muốn** với **quyền đang tồn tại**.

## 4. Quy tắc liên kết cùng một danh tính giữa các nguồn

Trước khi so sánh hai record, phải xác định chúng thuộc cùng chủ thể theo **bằng chứng liên kết đáng tin cậy** (*identity correlation*). Nếu liên kết nhầm, kết quả đối soát có thể chuyển quyền của người này sang người khác.

### Khóa định danh nên ưu tiên

1. **ID ổn định từ nguồn có thẩm quyền:** mã person, worker hoặc employment với phạm vi tổ chức được xác định.
2. **Liên kết được tạo khi provisioning:** identityId gắn với account ID do hệ thống đích trả về.
3. **External ID có quản trị:** ví dụ SCIM externalId do bên cấp phát quản lý và ánh xạ theo hợp đồng tích hợp. Giá trị này không tự động duy nhất trên mọi ứng dụng nếu chưa định nghĩa phạm vi.
4. **Định danh chủ thể trong IdP:** issuer kết hợp subject ID hoặc directory object ID được xác minh, tránh nhầm các realm.
5. **Liên kết đã được phê duyệt bằng tay:** cho tài khoản tồn tại từ trước hoặc nguồn thiếu ID chung.

**Không dùng riêng email, họ tên, số điện thoại, tên hiển thị hoặc username để tự động khẳng định cùng một người.** Những giá trị này có thể thay đổi, trùng nhau, bị tái sử dụng hoặc thuộc shared account. Email có thể là dấu hiệu tìm kiếm ứng viên liên kết nhưng không phải bằng chứng đủ để gộp.

Một bản ghi liên kết nên chứa **sourceSystem, sourceObjectId, identityId, linkMethod, verifiedAt, confidence/verificationState và auditReference**. Đối với hai nguồn có ID trùng chuỗi, vẫn phải kiểm tra chúng có thuộc cùng **tenant/issuer/namespace** không.

### Ba kết quả liên kết

| Kết quả | Nghĩa | Hành động |
| --- | --- | --- |
| **CONFIRMED_MATCH** | Có ID hoặc bằng chứng liên kết đáng tin cậy | Cho phép so sánh thuộc tính và quyền |
| **NO_MATCH** | Không tìm thấy chủ thể/account liên quan | Phân loại tài khoản mồ côi hoặc tài khoản thiếu; điều tra |
| **AMBIGUOUS_MATCH** | Có nhiều ứng viên hoặc dữ liệu xung đột | Cô lập khỏi thao tác gộp/cấp quyền tự động, yêu cầu xác minh |

Khi nguồn dữ liệu không đủ tin cậy, **không tự động chuyển account vào identity gần giống nhất**. Cần xử lý thủ công có quyền hạn và ghi bằng chứng rõ ràng.

## 5. So sánh thuộc tính nào và tin nguồn nào?

Một **ma trận thẩm quyền theo trường** là nền tảng của bộ quy tắc reconciliation. Bảng dưới đây là ví dụ thiết kế, cần điều chỉnh theo phân công quản trị thực tế:

| Thuộc tính | Nguồn quyết định mong muốn | Nguồn kiểm chứng thực tế | Xung đột điển hình |
| --- | --- | --- | --- |
| Person/worker ID | HRIS hoặc nguồn bảo trợ | IAM và các account liên kết | Account bị nối sai worker |
| Employment status | HRIS được ủy quyền | IAM, IdP và ứng dụng | HR đã terminated nhưng account vẫn active |
| Start/end date | HRIS/hợp đồng | Lịch IAM, account expiration | Job kích hoạt/khóa chạy sai thời điểm |
| Department/job code | HRIS | IAM/IdP claims | Nhân viên đã chuyển nhóm nhưng IdP còn thuộc tính cũ |
| Project membership | Hệ thống dự án có thẩm quyền | IAM, group và ứng dụng | Nhân viên vẫn thuộc nhóm dự án cũ |
| Organization/tenant membership | Nguồn quản trị membership/tenant được chỉ định | Ứng dụng đích | Có quyền truy cập sai tenant |
| Approved role/entitlement | IAM governance và chủ tài nguyên | IdP, ứng dụng, policy engine | Role chưa cấp hoặc cấp rộng hơn phê duyệt |
| Account creation/state | Chính sách provisioning đã duyệt | IdP hoặc ứng dụng sở hữu account | Lệnh tạo thành công nhưng account thực tế chưa tồn tại |
| Local ACL/PAT/session | Chính sách quyền và vòng đời | Ứng dụng phát hành/kiểm tra | Quyền cục bộ tồn tại dù nhóm IdP đã thu hồi |
| Workload owner | Danh mục dịch vụ/đội vận hành | IAM, cloud, secret manager | Service account không còn owner hợp lệ |

Không chọn đơn giản bản ghi có **updatedAt mới nhất** từ mọi nguồn. Một ứng dụng có thể được cập nhật hôm nay nhưng chỉ đang lưu trạng thái kỹ thuật cũ; HRIS có thể ghi quyết định có hiệu lực từ ngày mai. Cần dựa vào **thẩm quyền, mốc nghiệp vụ, version và policy**, không chỉ timestamp.

## 6. Chuẩn hóa dữ liệu trước khi so sánh

Hai hệ thống có thể mô tả cùng một giá trị theo cách khác nhau:

- HRIS ghi trạng thái **terminated**, IdP dùng **disabled**, ứng dụng dùng **active = false**.
- HRIS ghi **departmentId = ENG-01**, IdP ghi **engineering**, SaaS ghi tên hiển thị **Engineering**.
- HRIS dùng **ngày lịch**, IdP dùng **UTC timestamp** cho ngày hết hạn.
- Account ID có thể bao gồm tenant hoặc realm, trong khi hệ thống khác chỉ lưu local ID.
- Phạm vi role khác nhau: **Viewer** trong app A không mặc nhiên đồng nghĩa **Reader** trong app B.

Một bước **normalization** cần xử lý:

1. **Định dạng và kiểu:** string, boolean, date-only, timestamp, mã hệ thống.
2. **Từ vựng trạng thái:** ánh xạ giá trị của từng source sang mô hình nội bộ có ngữ nghĩa rõ.
3. **Múi giờ và thời gian hiệu lực:** xác định cách diễn giải ngày bắt đầu/kết thúc, không mặc định 00:00 UTC.
4. **Ánh xạ mã tổ chức, dự án, role:** tra cứu bảng mapping có phiên bản, tránh đoán từ tên.
5. **Phạm vi định danh:** kết hợp source ID, tenant/realm, object ID để tránh xung đột.
6. **Trường chưa biết:** phân biệt null/unknown, không có quyền, chưa đồng bộ và không áp dụng.
7. **Độ mới dữ liệu:** ghi snapshotAt, sourceVersion, receivedAt, effectiveAt.

### Không biến thiếu dữ liệu thành kết quả từ chối hoặc chấp thuận

Giả sử ứng dụng trả về **role = null** do API không có quyền đọc role. Không được suy ra người dùng **không có role** rồi tự đánh dấu PASS. Đây là trạng thái **UNKNOWN/UNVERIFIED**; cần nguồn kiểm chứng khác hoặc phân công xử lý. Tương tự, HRIS thiếu end date không đủ để kết luận quyền được giữ vô thời hạn.

## 7. Pipeline đối soát identity source

Một quy trình thường gồm những giai đoạn sau:

~~~mermaid
flowchart TD
    A["Thu thập snapshot từ HRIS, IdP, IGA, ứng dụng"] --> B["Xác thực nguồn, phiên bản, thời điểm và độ đầy đủ"]
    B --> C["Chuẩn hóa schema, trạng thái, timezone, org/role"]
    C --> D["Identity correlation theo ID đã xác minh"]
    D --> E{"Liên kết đúng và đủ dữ liệu?"}
    E -->|"Không"| X["Exception: missing / ambiguous / stale"]
    E -->|"Có"| F["Tính expected identity/account/access"]
    F --> G["Đọc observed state ở hệ thống đích"]
    G --> H["So sánh expected và observed"]
    H --> I{"Có sai lệch?"}
    I -->|"Không"| P["PASS, ghi bằng chứng"]
    I -->|"Có"| J["Phân loại nguyên nhân, rủi ro, owner"]
    J --> K["Duyệt và thực thi remediation phù hợp"]
    K --> L["Đọc lại trạng thái, xác minh effective access"]
    L --> H
    X --> M["Điều tra nguồn/ánh xạ và sửa có kiểm soát"]
    M --> C
~~~

**Thu thập:** dùng API, SCIM, export hoặc connector được quản trị để lấy bản ghi hiện hành, không chỉ sự kiện thay đổi. Lưu run ID, source version và thời điểm snapshot.

**Liên kết:** xác định person/identity/account mapping. Trường hợp chưa chắc chắn không được tiếp tục tự động cấp hoặc chuyển quyền.

**Tính trạng thái mong muốn:** xét employment, assignment, nhóm, phê duyệt, thời hạn, chính sách RBAC/ABAC và các quan hệ hợp lệ khác.

**So sánh:** xét **thiếu tài khoản**, **thừa tài khoản**, **khác trạng thái**, **khác owner**, **khác quyền** và **quyền hiệu lực** qua nhiều đường cấp.

**Remediation:** xác định hành động, người phê duyệt khi cần, mức ưu tiên, tính idempotent và khả năng khôi phục.

**Xác minh:** đọc lại tại ứng dụng/IdP sau khi thay đổi. Một job provisioning trả thành công vẫn chưa đủ nếu trạng thái đích không phản ánh quyết định.

## 8. Các loại sai lệch cần phân loại

| Loại sai lệch | Ví dụ | Nguy cơ hoặc tác động | Hướng xử lý |
| --- | --- | --- | --- |
| **Missing account** | Joiner đã duyệt nhưng app bắt buộc chưa có account | Nhân viên không làm được việc | Kiểm tra phê duyệt/connector rồi provision |
| **Orphan account** | SaaS có account không liên kết được identity hoặc owner | Đường truy cập không được quản trị | Cô lập/điều tra, xác minh trước khi khóa hoặc gộp |
| **Stale active account** | Leaver trong HR nhưng app vẫn active | Quyền truy cập tồn dư | Ưu tiên deprovision theo chính sách, xác minh tại đích |
| **Incorrect identity link** | Tài khoản của A gắn với identity B | Lộ dữ liệu hoặc thu hồi sai | Ngừng tự động thay đổi, sửa mapping theo bằng chứng |
| **Attribute drift** | Department/organization ở IdP lệch HR | Chính sách ABAC sai phạm vi | Cập nhật từ nguồn thẩm quyền, kiểm tra claim/token |
| **Missing entitlement** | Role đã phê duyệt chưa có ở app | Thiếu quyền cần thiết | Provision/duyệt lại và xác minh |
| **Excess entitlement** | App có role admin không nằm trong phê duyệt | Đặc quyền vượt mức | Thu hồi theo quy trình bảo mật, kiểm tra nguyên nhân |
| **Residual project access** | Mover đổi dự án nhưng còn ACL trực tiếp | Truy cập dữ liệu ngoài nhiệm vụ | Tính lại quyền, thu hồi mọi đường liên quan |
| **Duplicate account** | Retry tạo thêm account thứ hai | Khó kiểm soát và audit | Xác minh liên kết; hợp nhất/đóng theo quy trình |
| **Stale snapshot** | Dữ liệu ứng dụng cũ hơn sự kiện mới | Sai lệch giả hoặc bỏ sót | Làm mới dữ liệu trước khi hành động |
| **Ownerless workload** | Bot còn token nhưng owner nghỉ việc | Credential không ai chịu trách nhiệm | Chuyển owner, rà soát quyền và secret |

**Sai lệch có mức độ rủi ro khác nhau.** Tài khoản đang hoạt động của Leaver hoặc role admin vượt quyền thường cần ưu tiên hơn lỗi tên hiển thị chưa đồng bộ. Nhưng khi chưa chắc account thuộc ai, không nên tự động gộp hoặc xóa dữ liệu bằng một phép so khớp email.

## 9. Ví dụ so sánh ba nguồn cho một nhân viên

Giả sử HRIS đã xác nhận **Bình chuyển từ Dự án Atlas sang Nova lúc 00:00 ngày 01/12 theo giờ Việt Nam**. IAM đã lưu quyền mục tiêu sau Mover. Ứng dụng mã nguồn chưa cập nhật kịp.

| Thông tin | HRIS / nguồn dự án có thẩm quyền | IAM/IGA: trạng thái mong muốn | Ứng dụng: trạng thái quan sát |
| --- | --- | --- | --- |
| Worker / identity | worker-510 | iam-id-510 | account git-720 liên kết iam-id-510 |
| Trạng thái làm việc | active | identity active | account active |
| Phân công dự án | Nova, kể từ 01/12 | Nova | Vẫn có membership Atlas |
| Quyền đọc repository Atlas | Không còn căn cứ | Thu hồi | **Đang còn** qua nhóm atlas-readers |
| Quyền đọc repository Nova | Có căn cứ, đã duyệt | Cấp | **Chưa có** |
| Owner/phê duyệt | HR và chủ dự án xác nhận | Approval Mover hợp lệ | Chưa xác nhận thực thi |

Kết quả reconciliation phải phân biệt:

- **Đúng:** account gắn đúng identity, trạng thái hoạt động phù hợp employment còn hiệu lực.
- **Sai lệch thừa:** quyền Atlas chưa thu hồi, tạo **residual access**.
- **Sai lệch thiếu:** quyền Nova chưa được cấp, ảnh hưởng công việc.
- **Cần xử lý:** thu hồi membership/ACL Atlas, cấp Nova theo phê duyệt, đối soát effective access tại ứng dụng.

Nếu HR nhập sự kiện chuyển dự án từ ngày 01/12 nhưng snapshot ứng dụng chụp **trước 01/12**, không được xem khác biệt đó là lỗi đang tồn tại tại thời điểm tương lai. Phải so sánh theo **cùng mốc hiệu lực**, dữ liệu đủ mới và SLA đã định.

## 10. Ví dụ cấu trúc dữ liệu và kết quả reconciliation

JSON dưới đây là **mô hình minh họa**, không phải schema chính thức của SCIM hay một sản phẩm IAM.

~~~json
{
  "reconciliationRunId": "recon-2026-1201-01",
  "subject": {
    "personId": "person-510",
    "employmentId": "emp-2026-14",
    "identityId": "iam-id-510"
  },
  "sourceSnapshots": [
    {
      "source": "hris",
      "recordId": "worker-510",
      "employmentStatus": "active",
      "departmentId": "engineering",
      "snapshotAt": "2026-12-01T01:00:00+07:00",
      "version": 23
    },
    {
      "source": "iam-governance",
      "recordId": "iam-id-510",
      "expectedGroups": ["nova-readers"],
      "snapshotAt": "2026-12-01T01:01:00+07:00",
      "version": 52
    },
    {
      "source": "git-service",
      "recordId": "git-720",
      "observedGroups": ["atlas-readers"],
      "snapshotAt": "2026-12-01T01:02:00+07:00",
      "version": 78
    }
  ],
  "correlationStatus": "CONFIRMED_MATCH",
  "findings": [
    {
      "type": "EXCESS_ENTITLEMENT",
      "target": "git-service",
      "entitlement": "atlas-readers",
      "action": "REVOKE",
      "status": "OPEN"
    },
    {
      "type": "MISSING_ENTITLEMENT",
      "target": "git-service",
      "entitlement": "nova-readers",
      "action": "PROVISION",
      "status": "OPEN"
    }
  ]
}
~~~

Khi hai thuộc tính khác nhau, phải lưu **source của giá trị expected** và **source quan sát actual**. Trạng thái OPEN chỉ cho biết đã phát hiện sai lệch; sau khi remediation phải đọc lại hệ thống đích và cập nhật kết quả VERIFIED hoặc trạng thái ngoại lệ phù hợp.

## 11. Quy tắc đối chiếu theo Joiner–Mover–Leaver

### Joiner: so sánh để tránh thiếu hoặc gán nhầm

Nguồn nhân sự xác nhận người mới, ngày bắt đầu, organization, job code. IAM kiểm tra person/worker ID, liên kết hoặc tạo identity, xác định account/role cần có. Các nguồn kỹ thuật (IdP, ứng dụng) cho biết account **đã thực sự tồn tại** và quyền có hiệu lực hay chưa.

Các dấu hiệu cần tìm: account chưa được tạo, account trùng, wrong-identity mapping, cấp quyền quá rộng, kích hoạt trước ngày bắt đầu, ứng dụng đích chưa nhận provisioning và MFA/SSO chưa đáp ứng tiêu chí.

### Mover: so sánh trạng thái trước và sau thay đổi

HR hoặc hệ thống dự án có thẩm quyền cho biết **phân công mới và thời điểm hiệu lực**. IGA tính lại tập quyền mong muốn, phân loại quyền giữ, thêm, thu hồi; IdP và ứng dụng cho biết tập quyền đang còn.

Chỉ cộng nhóm mới mà không kiểm tra nhóm cũ gây **privilege accumulation**. Đối soát phải tìm cả **ACL chia sẻ trực tiếp**, nhóm lồng nhau, role ứng dụng và token mang claim quyền cũ. Nếu có quyền bàn giao hợp lệ, cần phê duyệt, phạm vi và thời hạn rõ.

### Leaver: so sánh để chứng minh đã thu hồi

Nguồn HR/bảo trợ xác nhận quan hệ làm việc kết thúc. IAM xác định có quan hệ hợp lệ khác hay không trước khi vô hiệu toàn bộ danh tính. Sau khi thực hiện deprovisioning, phải đối chiếu ở IdP, ứng dụng, PAT, session, token và quyền cục bộ.

**Khóa IdP hoặc SCIM đặt active = false không tự chứng minh mọi phiên/access token đã mất hiệu lực**. Nguồn ứng dụng/resource server mới cung cấp bằng chứng trạng thái thực tế của token/ACL thuộc ứng dụng đó. Hạng mục chưa xác minh cần giữ trạng thái còn mở thay vì đóng Leaver bằng một cờ đồng bộ.

## 12. IdP, SSO, SCIM và sai lệch giữa nguồn với quyền thực tế

**IdP** có thể lưu một bộ thuộc tính người dùng được đồng bộ từ HR hoặc IAM, chẳng hạn department và groups. **SSO** dùng token/claim để chuyển thông tin xác thực hoặc thuộc tính đã cấu hình đến ứng dụng. **SCIM** thường được dùng provisioning và cập nhật user/group ở ứng dụng có hỗ trợ.

Khi đối soát, cần hiểu:

| Cơ chế | Có thể so sánh | Không thể suy ra trực tiếp |
| --- | --- | --- |
| IdP | Account state, nhóm, thuộc tính và lịch sử cấp phát tại IdP | Toàn bộ ACL và token cục bộ ở ứng dụng |
| SSO/OIDC/SAML | Issuer, subject mapping, login/session hoặc claim khi có bằng chứng | Trạng thái employment hiện hành chỉ từ một token cũ |
| SCIM | User/Group từ hệ thống hỗ trợ, phản hồi tạo/cập nhật | Mọi role đặc thù, PAT, khóa API và quyền hiệu lực |
| RBAC | Role được gán, mapping role → entitlement | Quyền đã được thực thi tại mọi hệ thống nếu mapping lỗi |
| ABAC | Thuộc tính chủ thể/tài nguyên/ngữ cảnh | Quyết định đúng nếu thuộc tính nguồn đã cũ hoặc bị giả mạo |

Ví dụ, HRIS đổi department sang Finance, IdP đã cập nhật thuộc tính, nhưng JWT access token được cấp trước đó còn claim department = Sales. API xác minh token offline có thể tiếp tục dùng giá trị cũ nếu không kiểm tra lại quyền. **So sánh identity source** phải xét độ mới của claim và cơ chế resource server thực thi chính sách, đặc biệt khi quyền phải bị thu hồi ngay.

### Quyền mục tiêu và effective access

IAM có thể cho biết nhóm Atlas phải bị xóa. Nhưng ứng dụng vẫn có thể cho phép truy cập Atlas qua **một nhóm khác, ACL trực tiếp hoặc role kế thừa**. Cần so sánh **quyền hiệu lực** (*effective access*) bên cạnh trường membership được đồng bộ; nếu không có khả năng đọc quyền hiệu lực, phải ghi rõ giới hạn kiểm chứng.

## 13. Xử lý nguồn không đồng bộ, sự kiện cũ và snapshot lệch thời điểm

Reconciliation hiếm khi có snapshot tuyệt đối đồng thời từ mọi hệ thống. Các nguyên tắc quan trọng:

1. **Nguồn theo phiên bản:** dùng eventId, sourceVersion hoặc sequence để không ghi đè thông tin mới bằng sự kiện cũ.
2. **Thời gian nghiệp vụ:** phân biệt effectiveAt (khi công việc có hiệu lực) với recordedAt/updatedAt và processedAt.
3. **Độ mới tối thiểu:** định nghĩa ngưỡng snapshot age theo rủi ro; snapshot quá cũ không được dùng kết luận người dùng đã mất quyền.
4. **Độ trễ chấp nhận:** một thay đổi vừa phát sinh có thể đang provisioning; đánh dấu PENDING trong SLA thay vì tự kết luận thất bại tức thì.
5. **Lỗi nguồn:** nếu API ứng dụng trả thiếu dữ liệu hoặc connector không có quyền đọc, trạng thái là UNKNOWN/FAILED, không phải bằng chứng không có account.
6. **Đối soát toàn phần định kỳ:** sự kiện có thể bị mất; cần so sánh snapshot đủ rộng bên cạnh kiểm tra tăng dần theo sự kiện.
7. **Retry idempotent:** gửi lại thao tác cấp/thu hồi không làm phát sinh thêm tài khoản hay entitlement ngoài ý muốn.

Nếu người dùng đã có nhiều quan hệ lao động, một sự kiện kết thúc employment A không luôn làm identity chung mất hiệu lực. Hệ thống phải tính quyền từ **toàn bộ quan hệ còn hoạt động** trước khi kết luận. Với rehire, không tự bật lại các role và credential cũ chỉ vì personId trùng.

## 14. Tài khoản dịch vụ và identity source phi nhân viên

Không thể áp dụng cứng quy tắc “mọi account đều phải có employee record” cho **service account, workload identity, robot và API client**. Chúng có thể được quản lý bởi danh mục dịch vụ, nền tảng CI/CD hoặc hệ thống cloud.

Một lần đối soát workload nên kiểm tra:

- Workload có **serviceId/workloadId** ổn định và ứng dụng/môi trường đang hoạt động không?
- Có **owner team hoặc người bảo trợ** còn hợp lệ không?
- Account, OAuth client, role và secret hiện có khớp với **quyền đã duyệt** không?
- Token, API key, certificate có thời hạn, chủ sở hữu và cơ chế thu hồi phù hợp không?
- Workload đã ngừng nhưng account/credential còn tồn tại không?
- Người từng là owner đã Mover/Leaver nhưng **quan hệ sở hữu** chưa được chuyển giao không?

Ví dụ, bot triển khai vẫn chạy hợp lệ sau khi quản trị viên cũ nghỉ việc. Account reconciliation cần nhận diện đây là **workload account có owner cũ đã hết hiệu lực**, chuyển owner và rà soát credential. Không tự động xóa bot đang phục vụ sản xuất chỉ vì không khớp với employee record. Ngược lại, PAT cá nhân do người nghỉ việc tạo cho pipeline cần được thay thế và thu hồi theo chính sách.

## 15. Mã giả đối soát và phát hành hành động khắc phục

Mã giả sau mô tả ý tưởng so sánh expected và observed; không phải API của một sản phẩm cụ thể:

~~~text
reconcileIdentity(subjectReference, runId):
    sourceRecords = loadTrustedSourceSnapshots(subjectReference)
    validateSourceFreshnessAndVersions(sourceRecords)

    identityLink = correlateIdentityAndAccounts(sourceRecords)
    if identityLink.isAmbiguous:
        return openException("AMBIGUOUS_IDENTITY_LINK", owner="identity-governance")

    if not identityLink.isVerified:
        return openException("UNVERIFIED_IDENTITY", owner="identity-governance")

    normalized = normalizeBySourceContract(sourceRecords)
    expected = calculateExpectedState(
        authoritativeAttributes(normalized),
        approvedRoleAndEntitlementPolicy(),
        effectiveTime = runId.businessEffectiveAt
    )
    observed = readActualAccountsRolesAndAccess(identityLink)

    if not observed.isCompleteOrFresh:
        return openException("INCOMPLETE_OBSERVED_STATE", owner=observed.targetOwner)

    findings = compareWithFieldLevelAuthority(expected, observed)
    recordAudit(runId, identityLink, expected, observed, findings)

    for finding in findings:
        if finding.requiresIdentityProofing or finding.isHighImpact:
            openReviewWithAppropriateOwner(finding)
        else if finding.isApprovedForAutomatedRemediation:
            applyIdempotentChange(finding)
        else:
            openReviewWithAppropriateOwner(finding)

    verifyAtTargetSystemsAfterChanges(findings)
    return closeOnlyVerifiedFindings(findings)
~~~

Trong hệ thống thật, cần kiểm soát quyền đọc/ghi connector, timeout, giới hạn tốc độ, xung đột cập nhật đồng thời, phân loại rủi ro và cách khôi phục khi một phần thao tác thành công. **Hành động tự động** chỉ phù hợp khi danh tính, nguồn thẩm quyền, chính sách và phạm vi sửa đã được xác thực chắc chắn.

### Tại sao không tự động sửa mọi sai lệch?

Một local account không liên kết được HR có thể là **workload**, tài khoản khẩn cấp được quản trị riêng, tài khoản đối tác hợp lệ hoặc một orphan account cần vô hiệu hóa. Nếu lập tức xóa tất cả tài khoản chưa thấy trong HR, hệ thống có thể gây gián đoạn vận hành hoặc mất quyền cần cho công tác khẩn cấp. Phải phân loại và có owner trước khi quyết định. Ngược lại, một tài khoản của Leaver đã được xác minh có quyền truy cập nguy hiểm có thể cần hành động chặn ngay theo quy trình được phê duyệt.

## 16. Phê duyệt và xử lý sai lệch

Hệ thống reconciliation nên tạo một **finding có thể kiểm toán**, tối thiểu gồm:

| Thuộc tính | Nội dung |
| --- | --- |
| Finding ID / run ID | Định danh sai lệch và lần đối soát |
| Subject và target reference | Identity, account, application, tenant và resource |
| Expected / actual | Giá trị mong muốn và giá trị thực tế |
| Authority và evidence | Nguồn chuẩn, phiên bản, thời điểm và bằng chứng liên kết |
| Risk/severity | Mức ảnh hưởng, đặc quyền, dữ liệu nhạy cảm |
| Proposed action | Provision, revoke, correct link, investigate hoặc no action có lý do |
| Owner và approval | Người chịu trách nhiệm, phê duyệt khi cần |
| Deadline / trạng thái | Open, pending, blocked, verified, accepted exception |
| Verification evidence | Đọc lại trạng thái đích và kiểm tra quyền hiệu lực |

Các trường hợp **unknown identity, duplicate account, quyền quản trị cao, tài khoản không có owner** cần quy trình xử lý đủ chặt chẽ. Không nên cho phép một connector tự sửa HRIS theo dữ liệu ứng dụng chỉ để xóa cảnh báo. Ngược lại, cũng không nên sửa account ở đích nếu chưa biết đó là tài khoản của ai.

Một sai lệch có thể có **ngoại lệ hợp lệ**: quyền bàn giao sau Mover, yêu cầu hỗ trợ có thời hạn, account khẩn cấp hoặc tài khoản kỹ thuật đặc biệt. Ngoại lệ cần mục đích, chủ sở hữu, phạm vi, phê duyệt và ngày rà soát; không để ngoại lệ trở thành cách bỏ qua lỗi vô thời hạn.

## 17. Bảo mật dữ liệu và kiểm toán quá trình so sánh

Việc ghép dữ liệu nhiều nguồn tạo ra hồ sơ tổng hợp có thể chứa thông tin cá nhân, cấu trúc tổ chức và quyền truy cập nhạy cảm. Vì vậy, reconciliation cần:

- **Tối thiểu hóa trường:** chỉ lấy ID, thuộc tính, trạng thái và quyền cần cho phép đối chiếu; không sao chép toàn bộ hồ sơ HR.
- **Bảo vệ đường truyền và lưu trữ:** dùng xác thực connector, mã hóa theo nền tảng, phân quyền truy cập, quản lý secret phù hợp.
- **Tách quyền đọc và sửa:** hệ thống đọc trạng thái tài khoản không mặc nhiên có quyền quản trị tài nguyên hoặc sửa hồ sơ nhân sự.
- **Không ghi credential:** token, mật khẩu, recovery code, private key không được đưa vào snapshot hoặc log.
- **Dấu vết nguồn và người ra quyết định:** giữ version, thời điểm, policy, approval, action, kết quả và owner của sai lệch.
- **Phân quyền xem báo cáo:** tránh để báo cáo đối soát trở thành danh sách account đặc quyền hoặc dữ liệu nhân sự bị truy cập rộng rãi.
- **Chính sách lưu dữ liệu:** giới hạn thời gian giữ snapshot và audit theo yêu cầu pháp lý, tổ chức, nhu cầu điều tra.

Nếu cần kiểm chứng access token/phiên sau Leaver, nên sử dụng công cụ được ủy quyền và bằng chứng từ resource server hoặc token kiểm thử có phạm vi hẹp, không đưa bearer token sản xuất vào báo cáo.

## 18. Chỉ số vận hành và mức độ tin cậy

Một hệ thống account reconciliation tốt không chỉ báo số lượng khác biệt; nó cần giúp biết mức độ đáng tin và khả năng sửa:

| Chỉ số | Cách hiểu |
| --- | --- |
| **Identity correlation coverage** | Tỷ lệ account được liên kết với identity hoặc owner đã xác minh |
| **Ambiguous match count** | Số trường hợp có nhiều ứng viên, không thể gộp tự động |
| **Orphan account count** | Account không có nguồn hoặc chủ thể hợp lệ đã xác định |
| **Leaver access residuals** | Account/quyền còn active sau mốc phải thu hồi |
| **Mover stale entitlements** | Quyền từ vai trò/dự án cũ chưa thu hồi đúng hạn |
| **Missing required accounts** | Joiner không có account bắt buộc theo chính sách |
| **Excess privilege findings** | Quyền vượt phê duyệt hoặc role quản trị bất thường |
| **Reconciliation freshness** | Độ tuổi của snapshot và độ trễ cập nhật nguồn |
| **Time to verified remediation** | Thời gian từ phát hiện đến khi hệ thống đích xác nhận sửa xong |
| **Unverified target ratio** | Tỷ lệ ứng dụng không đọc được trạng thái hoặc không xác minh đủ |

Cần phân loại KPI theo **mức độ rủi ro và ứng dụng**, tránh một tỷ lệ trung bình tốt che giấu vài tài khoản đặc quyền chưa thu hồi. Với quyền nhạy cảm, ngưỡng thu hồi/đối soát phải phù hợp chính sách và khả năng hệ thống; không có một SLA chung đúng cho mọi tổ chức.

## 19. Bài tập tình huống

**Bối cảnh:** Một tổ chức có ba nguồn:

- **HRIS:** Hòa có workerId W-018, đang làm ở Finance; Minh có workerId W-025, đã nghỉ từ 18/11.
- **IdP:** account U-100 liên kết W-018, nhóm finance-readers; account U-105 liên kết W-025, đang disabled.
- **SaaS:** có account A-77 dùng email công việc của Hòa, role FinanceViewer; account A-81 mang email cũ của Minh nhưng trạng thái active và có PAT; một account automation-bot không có bản ghi HR.

**Câu hỏi 1:** Có thể tự gán A-77 cho W-018 vì email giống nhau không?

**Gợi ý:** Chưa đủ. Cần bằng chứng mapping account từ provisioning, externalId đáng tin cậy hoặc quy trình xác minh; email chỉ là dấu hiệu tìm kiếm.

**Câu hỏi 2:** Account A-81 cần được xem là gì?

**Gợi ý:** Là ứng viên **stale active account hoặc orphan account** có rủi ro Leaver. Phải xác nhận liên kết với Minh, tìm nguồn quyền/owner và thu hồi account/PAT theo quy trình; trạng thái disabled ở IdP không tự chứng minh PAT hết hiệu lực.

**Câu hỏi 3:** Có nên tự động xóa automation-bot vì không có workerId?

**Gợi ý:** Không. Xác định đây có phải workload identity hợp lệ, có owner, dịch vụ, môi trường, entitlement và thời hạn hay không. Nếu thực sự mồ côi, xử lý theo quy trình workload và rủi ro.

**Câu hỏi 4:** Khi HR chuyển Hòa từ Finance sang Sales, hệ thống nào xác định quyền mục tiêu và hệ thống nào chứng minh quyền đã đổi?

**Gợi ý:** HR xác nhận thay đổi công việc; IAM/IGA và chủ tài nguyên xác định entitlement theo chính sách; IdP và ứng dụng cho biết account/group/role đang tồn tại; resource server/ứng dụng xác nhận quyền hiệu lực.

**Câu hỏi 5:** Vì sao không kết luận PASS nếu connector SaaS trả lỗi đọc ACL?

**Gợi ý:** Vì thiếu bằng chứng; phải đánh dấu UNKNOWN/UNVERIFIED, retry hoặc chuyển xử lý ngoại lệ. Lỗi truy vấn không đồng nghĩa không có quyền.

## 20. Checklist thiết kế đối soát identity source

| Câu hỏi | Cần xác định rõ |
| --- | --- |
| Những identity source nào được dùng? | HRIS, đối tác, IAM/IGA, IdP, app, nguồn workload |
| Nguồn nào có thẩm quyền từng thuộc tính? | Authority matrix theo trường và loại danh tính |
| Liên kết identity–account bằng gì? | ID ổn định, namespace/tenant, externalId đã xác minh, bằng chứng mapping |
| Có xử lý person nhiều employment/rehire không? | Không tự kế thừa quyền; tách quan hệ theo thời gian |
| Schema và thời gian được chuẩn hóa thế nào? | Enum, timezone, effectiveAt, version, null/unknown |
| So sánh trạng thái mục tiêu hay thực tế? | Cả expected và observed, có effective access khi cần |
| Có phân loại mức rủi ro và quyền quá rộng? | Leaver, role admin, sai tenant, tài khoản mồ côi |
| Khi nguồn đến muộn, thiếu hoặc lỗi? | Freshness, idempotency, retries, đối soát snapshot |
| Tài khoản máy không có HR record thì sao? | Xác định workload source, owner và vòng đời riêng |
| Remediation được phê duyệt và xác nhận ra sao? | Owner, policy, workflow, readback, audit |
| Báo cáo có làm lộ dữ liệu nhạy cảm không? | Tối thiểu hóa dữ liệu, phân quyền, không ghi token |
| Làm sao chứng minh JML hoàn tất? | Đối soát account, quyền và phiên ở từng hệ thống bắt buộc |

## 21. Tổng kết

**So sánh identity source** trong **Account reconciliation** là quá trình xác định **nguồn nào nói đúng điều gì**, liên kết các bản ghi cùng chủ thể, chuẩn hóa dữ liệu và đối chiếu **trạng thái mong muốn** với **tài khoản/quyền thực tế**. Không có một identity source duy nhất biết mọi thông tin: **HRIS** và nguồn bảo trợ xác nhận quan hệ làm việc; **IAM/IGA** quản lý quyết định quyền; **IdP/SSO/SCIM** hỗ trợ đăng nhập và đồng bộ; **ứng dụng/resource server** xác nhận quyền hiệu lực; nguồn workload chịu trách nhiệm cho danh tính máy.

Để hỗ trợ **Joiner–Mover–Leaver**, phải đối chiếu theo thời điểm hiệu lực và thẩm quyền từng trường, liên kết bằng ID tin cậy, phát hiện account mồ côi, thiếu quyền, thừa quyền và truy cập tồn dư. Mỗi sai lệch cần được đánh giá rủi ro, khắc phục đúng phạm vi và **đọc lại ở hệ thống đích** trước khi ghi nhận hoàn tất. Đây là cơ sở để cấp quyền theo **RBAC/ABAC** chính xác, thu hồi đúng tài khoản và có bằng chứng kiểm toán xuyên suốt vòng đời danh tính.
