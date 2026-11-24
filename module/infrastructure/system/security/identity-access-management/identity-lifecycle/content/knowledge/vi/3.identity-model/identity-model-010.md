# Identity relationship: quan hệ giữa danh tính và các thực thể trong IAM

## 1. Identity relationship là gì?

Trong **Identity and Access Management (IAM)**, *identity relationship* là **mối liên hệ có ý nghĩa nghiệp vụ hoặc bảo mật giữa một danh tính với con người, tài khoản, tổ chức, nhóm, vai trò, tài nguyên, hay với một danh tính khác**. Những mối liên hệ này giúp hệ thống trả lời không chỉ “đây là ai?” mà còn “danh tính này đại diện cho ai, thuộc phạm vi nào, chịu trách nhiệm bởi ai, có tài khoản ở đâu và vì sao được cấp quyền?”.

Ví dụ, một kỹ sư có thể đồng thời có các quan hệ:

- Là **danh tính của** nhân viên có mã nhân sự xác định.
- **Thuộc** phòng kỹ thuật và **được phân công** cho Dự án Atlas.
- **Được quản lý bởi** trưởng nhóm kỹ thuật.
- **Liên kết với** tài khoản ở nhà cung cấp danh tính (IdP), hệ thống mã nguồn và nền tảng cloud.
- **Là thành viên** nhóm `atlas-developers`, nhóm này **được gán** vai trò đọc repository Atlas.
- **Là người chịu trách nhiệm** một tài khoản dịch vụ chạy quy trình triển khai.

Một sự kiện chuyển nhóm có thể làm thay đổi nhiều quan hệ cùng lúc. IAM cần nhận biết quan hệ nào còn hiệu lực, quan hệ nào phải tạo hoặc thu hồi, và liệu những thay đổi đó đã được áp dụng trong các hệ thống đích hay chưa.

**Phân biệt quan trọng:** một quan hệ trong mô hình dữ liệu **không tự động trở thành quyền truy cập**. Chẳng hạn “A là quản lý của B” mô tả cơ cấu tổ chức; A chỉ được xem dữ liệu nhạy cảm của B nếu có chính sách cấp quyền tương ứng. Tương tự, “X sở hữu tài nguyên Y” có thể là trách nhiệm phê duyệt mà không mặc nhiên cho phép X đọc mọi dữ liệu của Y.

## 2. Những thực thể thường xuất hiện trong mô hình

| Thực thể | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Person** | Con người trong thế giới thực, có thể có nhiều mối quan hệ công việc | Nhân viên Lan, nhà thầu Minh |
| **Identity** | Bản ghi danh tính số được IAM quản lý, có định danh và trạng thái | `identity:lan-482` |
| **Account** | Tài khoản thực tế ở một hệ thống hoặc ứng dụng; có thể ánh xạ tới một identity | `lan@corp.example`, tài khoản Git |
| **Organization / Department / Project** | Đơn vị tổ chức hoặc phạm vi công việc | Phòng Kỹ thuật, Dự án Atlas |
| **Group** | Tập danh tính/tài khoản phục vụ quản lý hoặc cấp quyền | `atlas-developers` |
| **Role** | Gói trách nhiệm hoặc quyền sử dụng theo công việc | `ProjectReader`, `BillingApprover` |
| **Entitlement** | Quyền cụ thể tại một hệ thống, có thể được cấp trực tiếp hoặc qua vai trò/nhóm | `repo:atlas:read` |
| **Resource** | Đối tượng được bảo vệ bởi kiểm soát truy cập | Repository Atlas, bucket dữ liệu, API |
| **Service / Workload identity** | Danh tính dùng cho dịch vụ hoặc tác vụ tự động | `deploy-bot-atlas` |

Trong thực tế, **person**, **identity** và **account** không nhất thiết có quan hệ một–một:

- Một người có thể có danh tính nhân viên và danh tính đối tác được quản lý theo hai quan hệ hợp đồng khác nhau.
- Một identity có thể liên kết tới nhiều tài khoản ứng dụng; mỗi tài khoản có mã định danh cục bộ riêng.
- Một ứng dụng có thể chưa hỗ trợ liên kết tài khoản đủ tin cậy; khi đó cần xác minh trước khi khẳng định hai bản ghi thuộc cùng một người.
- Một workload identity không nhất thiết tương ứng với một person đăng nhập, nhưng phải có **chủ sở hữu chịu trách nhiệm** và trạng thái vòng đời rõ ràng.

Mô hình cụ thể tùy tổ chức và sản phẩm IAM. Điều quan trọng là **định nghĩa rõ từng loại thực thể, từng quan hệ và quy tắc quản trị**.

## 3. Các loại quan hệ cần quản lý

| Quan hệ | Ý nghĩa | Được dùng để làm gì? |
| --- | --- | --- |
| `represents` — identity đại diện cho person | Liên kết bản ghi số với người có thật | Xác minh nguồn danh tính, xử lý trùng lặp |
| `has_account` — identity liên kết account | Ánh xạ danh tính trung tâm với tài khoản ứng dụng | Cấp, cập nhật và vô hiệu hóa đúng tài khoản |
| `member_of` — thuộc nhóm | Danh tính hoặc tài khoản tham gia một nhóm | Phân phối quyền, phối hợp quản trị truy cập |
| `assigned_to` — được phân công | Người/danh tính tham gia phòng ban, dự án, tenant | Tính điều kiện đủ để cấp và giữ quyền |
| `reports_to` — báo cáo cho quản lý | Quan hệ quản lý về mặt tổ chức | Chuyển yêu cầu duyệt, xác định người liên hệ |
| `has_role` — có vai trò | Vai trò được gán theo công việc | Áp dụng RBAC và chứng minh căn cứ cấp quyền |
| `grants` / `permits` — gắn với entitlement | Vai trò/nhóm/chính sách dẫn tới quyền cụ thể | Xác định phạm vi quyền hiệu lực |
| `owns` — sở hữu, chịu trách nhiệm | Cá nhân/nhóm chịu trách nhiệm tài nguyên hoặc identity máy | Phê duyệt, rà soát, thu hồi khi hết nhu cầu |
| `delegated_to` — ủy quyền | Một chủ thể cho phép chủ thể khác thực hiện việc được xác định | Kiểm soát phạm vi, thời hạn và truy vết hành động |

Không nên đánh đồng các quan hệ. **“Quản lý của”**, **“sở hữu”**, **“được duyệt”**, **“được cấp quyền”** và **“đã thực sự đăng nhập”** có ý nghĩa khác nhau. Từng quan hệ phải có nguồn tin cậy và quy tắc sử dụng riêng.

### Mô hình khái niệm

Sơ đồ sau biểu diễn **các đường liên kết thường gặp**, không áp đặt số lượng tuyệt đối cho từng sản phẩm:

~~~mermaid
flowchart LR
    P["Person<br/>Con người"] -->|"được biểu diễn bởi"| I["Identity<br/>Danh tính số"]
    I -->|"liên kết"| A["Account<br/>Tài khoản ứng dụng"]
    I -->|"là thành viên"| G["Group<br/>Nhóm"]
    I -->|"được phân công"| O["Department / Project<br/>Đơn vị, dự án"]
    I -->|"được gán"| R["Role<br/>Vai trò"]
    G -->|"có thể ánh xạ"| R
    R -->|"bao gồm"| E["Entitlement<br/>Quyền cụ thể"]
    E -->|"áp dụng tới"| T["Resource<br/>Tài nguyên"]
    I -.->|"chịu trách nhiệm quản trị"| W["Workload identity<br/>Danh tính dịch vụ"]
    W -->|"sử dụng quyền được cấp"| T
~~~

Sơ đồ cho thấy **quan hệ nghiệp vụ** (ví dụ phân công dự án), **quan hệ cung cấp tài khoản** và **quan hệ cấp quyền** phải được kết nối nhưng vẫn tách bạch về ý nghĩa. Chỉ có đường liên kết trong sơ đồ chưa đủ để kết luận quyết định cho phép truy cập.

## 4. Quan hệ có thuộc tính và có vòng đời

Một identity relationship nên được lưu thành thông tin có thể kiểm chứng, thay vì chỉ là nhãn tự do. Các thuộc tính thường hữu ích:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| **Subject, predicate, object** | Ai/cái gì có quan hệ nào với ai/cái gì? |
| **ID ổn định và phạm vi tenant** | Hai đầu quan hệ được nhận diện duy nhất ở đâu? |
| **Nguồn tạo và căn cứ** | Quan hệ đến từ HR, hệ thống dự án, yêu cầu đã duyệt hay đồng bộ kỹ thuật? |
| **Trạng thái** | Đang chờ, đã phê duyệt, đang hiệu lực, hết hạn hay đã thu hồi? |
| **Thời gian hiệu lực** | Bắt đầu từ lúc nào, có ngày kết thúc không? |
| **Người chịu trách nhiệm/phê duyệt** | Ai có quyền xác nhận và rà soát quan hệ? |
| **Dấu vết thay đổi** | Ai hoặc tiến trình nào sửa quan hệ và vì sao? |

Ví dụ bản ghi **minh họa** cho quan hệ dự án, không phải cấu hình chuẩn của một sản phẩm IAM:

~~~json
{
  "relationshipId": "rel-3921",
  "subject": { "type": "identity", "id": "id-lan-482" },
  "relation": "assigned_to",
  "object": { "type": "project", "id": "project-atlas" },
  "tenantId": "tenant-main",
  "source": "project-assignment-system",
  "validFrom": "2026-11-01T00:00:00Z",
  "validUntil": "2026-12-31T23:59:59Z",
  "state": "active",
  "approvalReference": "approval-725"
}
~~~

Hệ thống IAM có thể suy ra từ quan hệ này rằng Lan **đủ điều kiện được xem xét** nhận quyền Dự án Atlas. Quyền thật sự chỉ phát sinh khi chính sách cấp quyền, điều kiện bảo mật và cơ chế thực thi của ứng dụng đều cho phép.

Đối với quan hệ dựa trên thời gian, cần định nghĩa rõ **thời điểm hiệu lực** và **thời điểm ghi nhận sự kiện**. Ví dụ, hệ thống nhân sự ghi nhận ngày 15/11 rằng việc chuyển nhóm có hiệu lực từ 18/11; quyền truy cập phải thay đổi theo mốc có hiệu lực đã được phê duyệt. Các hệ thống phải thống nhất cách xử lý múi giờ, gia hạn, hủy quyết định và bản ghi lịch sử.

## 5. Nguồn tin cậy cho từng quan hệ

Không phải ứng dụng nào cũng là nguồn xác thực cho mọi loại quan hệ. Một tổ chức có thể thiết kế các **nguồn dữ liệu có thẩm quyền** (*authoritative sources*) như sau:

| Loại quan hệ | Nguồn có thể có thẩm quyền | Nơi tiêu thụ dữ liệu |
| --- | --- | --- |
| Người có hợp đồng/lao động và trạng thái làm việc | HR hoặc hệ thống quản lý đối tác | IAM, IdP |
| Người thuộc phòng ban, có quản lý trực tiếp | HR hoặc hệ thống cơ cấu tổ chức | IAM, phê duyệt truy cập |
| Người tham gia dự án và thời hạn tham gia | Hệ thống quản lý dự án được tổ chức giao quản trị | IAM, công cụ phân quyền dự án |
| Identity liên kết tài khoản ứng dụng | IAM/IdP kết hợp bản ghi cấp phát ở hệ thống đích | Quy trình provisioning và deprovisioning |
| Thành viên nhóm, vai trò và entitlement | Nền tảng quản trị truy cập cùng chủ tài nguyên/ứng dụng | IdP, ứng dụng, gateway |
| Tài nguyên thuộc chủ sở hữu nào | Danh mục tài sản và chủ tài nguyên | Rà soát, duyệt quyền |
| Workload thuộc ứng dụng/đội vận hành nào | Danh mục dịch vụ, nền tảng ứng dụng hoặc hệ thống quản lý workload | IAM, quản lý khóa và tài khoản dịch vụ |

Quy trình đồng bộ nên xác định **nguồn nào được quyền ghi**, nguồn nào chỉ tiếp nhận, trường nào được cập nhật tự động và cách giải quyết xung đột. Nếu HR nói một nhân viên đã rời tổ chức nhưng tài khoản ứng dụng vẫn đang hoạt động, cần ưu tiên nguồn có thẩm quyền về trạng thái làm việc và kích hoạt thu hồi, thay vì xem bản ghi ứng dụng là bằng chứng rằng người đó vẫn được phép truy cập.

### Liên kết tài khoản (identity correlation)

Để thu hồi đúng tài khoản, IAM phải nối được danh tính trung tâm với các tài khoản cục bộ. Đây gọi là **identity correlation** hay *account linking*.

- Ưu tiên **mã định danh ổn định** do nguồn tin cậy quản lý, ví dụ mã nhân sự bất biến trong phạm vi có quy định, external ID đã xác minh, hoặc liên kết được tạo qua quy trình cấp phát có theo dõi.
- Không tự động gộp chỉ vì **trùng tên hiển thị** hoặc **trùng email**: email có thể đổi, tái sử dụng hoặc được chia sẻ trong một số môi trường.
- Khi có hai tài khoản khả nghi hoặc liên kết mâu thuẫn, cần quy trình xác minh và phê duyệt trước khi gộp. Gộp sai có thể trao tài nguyên của người này cho người khác.
- Nếu một người có nhiều hợp đồng, nhiều danh tính theo tenant hoặc quay lại làm việc, cần quy tắc xử lý riêng để tránh kế thừa nhầm quyền của đợt làm việc cũ.
- Duy trì ánh xạ hai chiều: từ identity tìm được tài khoản liên quan và từ tài khoản xác định được identity/chủ sở hữu; tài khoản không truy ra chủ thể hợp lệ phải được đánh dấu để rà soát.

## 6. Identity relationship trong Joiner–Mover–Leaver

Mô hình **Joiner–Mover–Leaver (JML)** mô tả vòng đời từ xác minh, tạo tài khoản và cấp quyền, tới thay đổi vai trò và chấm dứt quyền. Quản trị các **quan hệ** là cơ sở để tránh việc cấp thiếu hoặc để sót truy cập.

| Giai đoạn | Quan hệ được tạo/thay đổi | Hành động cần kiểm tra |
| --- | --- | --- |
| **Joiner — gia nhập** | `person → identity`, `identity → account`, quan hệ phòng ban/dự án/manager và nhóm/role ban đầu | Xác minh danh tính, tạo tài khoản chính xác, cấp quyền theo vai trò/phân công đã phê duyệt |
| **Mover — thay đổi vai trò** | Cập nhật `assigned_to`, `reports_to`, `member_of`, `has_role`; có thể đổi chủ sở hữu workload | Tính khác biệt giữa quyền cũ và mới; thu hồi quan hệ không còn hợp lệ; duyệt và cấp quan hệ mới |
| **Leaver — rời tổ chức** | Hết hiệu lực quan hệ lao động, trạng thái identity, quan hệ tài khoản và entitlement | Vô hiệu hóa/thu hồi tài khoản và quyền trên hệ thống đích; xử lý session, token, quyền trực tiếp, trách nhiệm sở hữu tài nguyên |

### Joiner

Trước khi tạo tài khoản, IAM cần có quan hệ tin cậy giữa người mới và tổ chức. Các quan hệ như phòng ban, quản lý, dự án hoặc loại hợp đồng quyết định quy trình cấp quyền ban đầu. Ví dụ, nhà thầu chỉ tham gia ba tuần không nên được tạo quyền vô thời hạn nhờ cùng nhãn “developer” với nhân viên chính thức.

### Mover

Khi một identity đổi dự án, hệ thống cần phân biệt:

1. **Quan hệ cũ phải kết thúc:** thành viên dự án cũ, nhóm truy cập cũ, vai trò/phạm vi đặc thù.
2. **Quan hệ mới cần hình thành:** dự án mới, quản lý mới, nhóm hoặc entitlement mới.
3. **Quan hệ có thể giữ lại:** tài khoản đăng nhập cơ bản, quyền dùng hệ thống dùng chung nếu vai trò mới vẫn cần.
4. **Quan hệ bàn giao tạm thời:** có chủ sở hữu phê duyệt, phạm vi xác định và thời điểm hết hạn.

Chỉ **thêm nhóm mới** mà không xử lý quan hệ cũ sẽ dẫn đến *privilege accumulation* — tích lũy quyền truy cập tồn dư qua nhiều lần điều chuyển.

### Leaver

Khi một người rời tổ chức, cần truy lần lượt từ person/identity đến các account, nhóm, vai trò, entitlement, quyền ứng dụng cục bộ và quyền sở hữu tài nguyên. Việc khóa một tài khoản IdP không bảo đảm mọi đường truy cập đã bị cắt: tài khoản cục bộ không liên kết, phiên hiện tại, API token hoặc khóa dịch vụ vẫn có thể tồn tại. Các quan hệ **sở hữu** workload/tài nguyên cũng cần được chuyển cho người chịu trách nhiệm mới trước khi đóng hoàn toàn danh tính.

## 7. Quan hệ hỗ trợ RBAC, ABAC và ReBAC như thế nào?

**RBAC (Role-Based Access Control)** sử dụng quan hệ giữa identity, role và entitlement: người dùng được gán vai trò, vai trò cho phép thực hiện một tập hành động trên những tài nguyên quy định.

**ABAC (Attribute-Based Access Control)** đánh giá thuộc tính của identity, tài nguyên và môi trường. Quan hệ phân công dự án có thể cung cấp thuộc tính `assignedProjectIds`, trong khi tài nguyên có `projectId`; hệ thống chỉ cho phép khi hai giá trị phù hợp và các điều kiện khác được thỏa.

**ReBAC (Relationship-Based Access Control)** sử dụng trực tiếp quan hệ trong đồ thị, chẳng hạn “đang là thành viên của dự án sở hữu tài liệu này” hoặc “được ủy quyền xem một tài nguyên bởi người có quyền hợp lệ”. Đây là cách tiếp cận hữu ích khi quyền phụ thuộc nhiều vào cấu trúc dự án, nhóm, chủ sở hữu hoặc chia sẻ. Tuy nhiên, việc hệ thống có hỗ trợ ReBAC hay không và cách duyệt quan hệ phải được thiết kế rõ.

Ví dụ chính sách dạng **mã giả**, không gắn với sản phẩm cụ thể:

~~~text
cho_phep(identity, "read", resource) NẾU
    identity.status == "active"
    VÀ quan_he(identity, "assigned_to", resource.project).dang_hieu_luc
    VÀ (
         quan_he(identity, "has_role", "ProjectReader").dang_hieu_luc
         HOẶC quan_he(identity, "member_of", "project-readers").dang_hieu_luc
    )
    VÀ identity.tenant_id == resource.tenant_id
    VÀ khong_co_quy_tac_cam_uu_tien_cao_hon(identity, resource)
NGƯỢC LẠI từ_chối
~~~

Mối quan hệ “là thành viên của nhóm” không tự nó nói lên **quyền cụ thể** nếu chưa biết nhóm đó ánh xạ đến entitlement nào. Tương tự, một người có thể “là chủ tài nguyên” để phê duyệt yêu cầu nhưng quyền đọc hoặc sửa vẫn phải xét theo chính sách của tài nguyên.

**Quyền hiệu lực** có thể phát sinh từ nhiều đường: vai trò trực tiếp, nhóm lồng nhau, vai trò kế thừa, ACL của ứng dụng hoặc ủy quyền tạm thời. Khi thu hồi một quan hệ, IAM phải xem còn đường nào khác duy trì quyền truy cập hay không.

## 8. Tác động của IdP, SSO và SCIM đến các quan hệ

**IdP (Identity Provider)** giữ và xác minh danh tính, trạng thái, nhóm hoặc một số thuộc tính liên quan. **SSO (Single Sign-On)** giúp đăng nhập thống nhất và chuyển các claim/token phù hợp cho ứng dụng. **SCIM (System for Cross-domain Identity Management)** thường được dùng để đồng bộ vòng đời tài khoản và nhóm sang ứng dụng có hỗ trợ.

Một chuỗi vận hành minh họa:

~~~mermaid
sequenceDiagram
    participant HR as Hệ thống nhân sự / dự án
    participant IAM as IAM governance
    participant IdP as IdP
    participant App as Ứng dụng đích
    HR->>IAM: Xác nhận chuyển Dự án Atlas sang Nova
    IAM->>IAM: Đánh giá quan hệ cũ, mới và quyền hiệu lực
    IAM->>IdP: Cập nhật thuộc tính và nhóm được duyệt
    IdP->>App: Đồng bộ người dùng/nhóm qua SCIM nếu hỗ trợ
    App-->>IAM: Kết quả provisioning / deprovisioning
    IAM->>App: Đối chiếu nhóm, ACL và quyền thực tế
    App-->>IAM: Trạng thái quyền hiệu lực đã kiểm chứng
~~~

SSO giúp ứng dụng biết ai đang đăng nhập, nhưng **không thay thế kiểm tra quyền trên tài nguyên**. SCIM có thể truyền nhóm và tài khoản, nhưng không phải ứng dụng nào cũng hỗ trợ toàn bộ entitlement cục bộ. Khi IdP đổi trạng thái hoặc nhóm, các ứng dụng vẫn có thể chịu độ trễ đồng bộ, token đang có hiệu lực hoặc cơ chế cache riêng; cần kiểm tra và xử lý theo khả năng từng hệ thống.

## 9. Quan hệ của danh tính máy, tài khoản đặc quyền và ủy quyền

### Workload / service identity

Một dịch vụ chạy tự động cần các quan hệ khác với nhân viên:

- `workload_identity → owned_by → team/person`: ai chịu trách nhiệm phê duyệt, giám sát và thu hồi.
- `workload_identity → deployed_as → application/environment`: workload chạy ở ứng dụng và môi trường nào.
- `workload_identity → has_entitlement → resource`: những API, bucket, secret hoặc database nào được phép truy cập.
- `workload_identity → lifecycle_of → workload`: danh tính hoặc credential cần hết hiệu lực khi workload ngừng hoạt động.

Không nên dùng account của một cá nhân làm tài khoản cố định của dịch vụ. Khi cá nhân chuyển công tác hoặc nghỉ việc, việc quản trị và thu hồi sẽ khó, đặc biệt nếu credential gắn với quá trình chạy tự động.

### Tài khoản đặc quyền

Một người có thể có tài khoản thông thường và tài khoản quản trị riêng. Mô hình cần liên kết cả hai về cùng **chủ thể chịu trách nhiệm**, nhưng không gộp quyền: tài khoản đặc quyền có điều kiện xác thực mạnh hơn, được sử dụng khi cần và được giám sát riêng. Quan hệ liên kết hỗ trợ kiểm toán “ai đã thực hiện thao tác”, còn phạm vi quyền phải được kiểm soát tại tài khoản đặc quyền.

### Quan hệ ủy quyền

Ví dụ, quản lý A ủy quyền cho B phê duyệt một số yêu cầu trong thời gian nghỉ phép. Quan hệ ủy quyền cần ghi rõ **đối tượng, hành động, phạm vi, thời gian, người cấp và người nhận**. Không suy ra rằng B được mọi quyền dữ liệu của A. Khi thời hạn kết thúc hoặc A mất quyền ủy quyền tương ứng, hệ thống cần đánh giá và chấm dứt quyền phái sinh.

## 10. Ví dụ xuyên suốt: một nhân viên đổi dự án

Giả sử Lan chuyển từ Atlas sang Nova ngày 18/11. Trước khi chuyển:

| Quan hệ hiện tại | Giá trị |
| --- | --- |
| `represents` | Identity của Lan liên kết với bản ghi nhân viên đã xác minh |
| `has_account` | Tài khoản IdP và tài khoản ứng dụng mã nguồn |
| `assigned_to` | Dự án Atlas |
| `member_of` | Nhóm `atlas-dev` |
| `has_role` | Vai trò `Developer` trong phạm vi Atlas |
| `owns` | Chịu trách nhiệm quản trị bot báo cáo Atlas cùng nhóm vận hành |

Quy trình đúng cần:

1. Ghi nhận sự kiện chuyển dự án từ nguồn có thẩm quyền, kèm **thời điểm hiệu lực**.
2. Kết thúc quan hệ `assigned_to → Atlas` và gán `assigned_to → Nova`.
3. Đánh giá lại `atlas-dev` và quyền trên các repository, dashboard, secret Atlas; chỉ giữ quyền bàn giao nếu có phê duyệt và hạn sử dụng.
4. Cấp quan hệ nhóm/vai trò và entitlement Nova theo chính sách, sau khi phê duyệt cần thiết.
5. Chuyển giao quan hệ **chủ sở hữu bot Atlas** sang người hoặc nhóm có trách nhiệm; không tự động xóa bot chỉ vì Lan đổi dự án.
6. Đồng bộ thay đổi tới IdP và các ứng dụng, đối chiếu quyền thực tế và ghi dấu vết kiểm toán.

Nếu quyền Atlas còn hiệu lực dù Lan đã bị xóa khỏi `atlas-dev`, cần tìm đường cấp quyền khác: nhóm lồng nhau, ACL chia sẻ trực tiếp, role ứng dụng không được đồng bộ hoặc token còn hạn. **Xóa một cạnh quan hệ không luôn đồng nghĩa với xóa mọi đường truy cập tới tài nguyên.**

## 11. Kiểm soát chất lượng và phát hiện quan hệ bất thường

Các điều kiện cần được theo dõi trong vận hành:

| Kiểm tra | Vì sao cần thiết? | Ví dụ sự cố |
| --- | --- | --- |
| **Tính toàn vẹn tham chiếu** | Quan hệ phải trỏ đến thực thể có thật, đúng tenant | Membership trỏ tới nhóm đã xóa |
| **Định danh duy nhất và liên kết đúng** | Tránh gộp hai người hoặc gán nhầm account | Email cũ được cấp lại cho người mới |
| **Nguồn có thẩm quyền** | Tránh dữ liệu cục bộ ghi đè nguồn nhân sự | Ứng dụng vẫn giữ trạng thái “active” sau khi HR đánh dấu nghỉ việc |
| **Hiệu lực theo thời gian** | Quan hệ tạm thời phải tự hết hạn | Nhà thầu vẫn thuộc dự án sau khi hết hợp đồng |
| **Chủ sở hữu và người phê duyệt** | Có người giải thích vì sao quan hệ cần tồn tại | Service account không có owner |
| **Quyền hiệu lực** | Phát hiện nhiều đường cấp quyền | Xóa nhóm chính nhưng vẫn còn ACL chia sẻ trực tiếp |
| **Phạm vi tenant / tổ chức** | Ngăn quan hệ vượt ranh giới dữ liệu | Account ở tenant A được liên kết nhầm với identity tenant B |
| **Độ trễ thực thi và thu hồi** | Kiểm tra thay đổi đã đến hệ thống đích | SCIM cập nhật thành công nhưng phiên cũ vẫn truy cập được |

Các chỉ số vận hành tham khảo:

- Số lượng account hoặc service identity **không liên kết được chủ thể/chủ sở hữu**.
- Số quan hệ cấp quyền **đã hết hạn nhưng vẫn có hiệu lực**.
- Số danh tính đã rời tổ chức nhưng còn account hoặc entitlement hoạt động.
- Thời gian từ sự kiện Joiner/Mover/Leaver đến lúc thay đổi hiện diện trong **quyền hiệu lực ở hệ thống đích**.
- Tỷ lệ truy cập nhạy cảm có thể truy vết tới nguồn, quan hệ công việc, yêu cầu phê duyệt và chủ tài nguyên.

Không có một ngưỡng cố định phù hợp mọi hệ thống. Tổ chức cần xác định ngưỡng và ưu tiên theo mức độ nhạy cảm của tài nguyên, yêu cầu kiểm toán và đặc tính vận hành.

### Lỗi mô hình hóa thường gặp

**Nhầm identity với account.** Chỉ xóa một username trong IdP mà bỏ sót tài khoản ở ứng dụng khác. Cần quản lý ánh xạ identity–account và kiểm tra các tài khoản liên kết.

**Suy quyền từ quan hệ nghiệp vụ một cách máy móc.** Ví dụ xem việc “là quản lý” đồng nghĩa có thể đọc toàn bộ hồ sơ nhân sự. Cần chính sách cụ thể về hành động, tài nguyên, điều kiện và phê duyệt.

**Lưu quan hệ mà không lưu lịch sử.** Không thể giải thích tại sao người dùng có quyền ở một thời điểm trước đây. Cần dấu vết thời gian, nguồn, người phê duyệt và các lần thay đổi.

**Không đánh giá lại khi Mover.** Nhóm và vai trò cũ tiếp tục tồn tại bên cạnh nhóm mới. Cần tính chênh lệch entitlement và thu hồi quyền không còn căn cứ.

**Đồng nhất dữ liệu mong muốn với dữ liệu thực tế.** Quan hệ đã đổi ở IAM nhưng ứng dụng chưa cập nhật hoặc vẫn tồn tại cache/token. Cần đối chiếu quyền hiệu lực, xác nhận thu hồi và xử lý lỗi đồng bộ.

## 12. Bài tập tự kiểm tra

**Tình huống:** Minh là nhà thầu của Dự án Alpha. Minh có tài khoản IdP, tài khoản trên công cụ mã nguồn, thuộc nhóm `alpha-readers` và được phép xem repository Alpha. Sau khi hợp đồng kết thúc, tài khoản IdP đã bị vô hiệu hóa nhưng token truy cập ứng dụng vẫn hoạt động.

Hãy xác định:

1. **Những quan hệ nào đã tồn tại?** Ít nhất có quan hệ nhà thầu–tổ chức, person–identity, identity–account, identity–project, identity–group và nhóm/vai trò–entitlement–resource.
2. **Quan hệ nào phải kết thúc?** Quan hệ hợp đồng/phân công, membership và entitlement liên quan phải được đánh giá để thu hồi theo chính sách; tài khoản và phiên/token phải được xử lý tại các hệ thống đích.
3. **Vì sao khóa IdP chưa đủ?** IdP quản lý xác thực tập trung nhưng ứng dụng có thể chấp nhận token đang còn hiệu lực hoặc tồn tại đường truy cập cục bộ khác.
4. **Cần bằng chứng gì để đóng yêu cầu?** Trạng thái identity, tài khoản liên kết, quyền hiệu lực tại ứng dụng, kết quả vô hiệu hóa/token revocation trong phạm vi hỗ trợ và nhật ký xác nhận thu hồi.

## 13. Tổng kết

**Identity relationship** là nền tảng liên kết **con người hoặc workload với danh tính số, tài khoản, cơ cấu tổ chức, nhóm, vai trò, quyền và tài nguyên**. Mô hình tốt phải diễn đạt đúng ý nghĩa từng quan hệ, dùng định danh ổn định, có nguồn tin cậy, chủ sở hữu, thời hạn và dấu vết thay đổi. Trong IAM theo **Joiner–Mover–Leaver**, những quan hệ đó được tạo, cập nhật và thu hồi theo thay đổi công việc; **IdP, SSO và SCIM** hỗ trợ xác thực và đồng bộ, còn **RBAC/ABAC/ReBAC và cơ chế tại hệ thống đích** quyết định truy cập thực tế. Kiểm tra quan hệ cùng quyền hiệu lực là cách phát hiện tài khoản mồ côi, quyền tích lũy và truy cập tồn dư.
