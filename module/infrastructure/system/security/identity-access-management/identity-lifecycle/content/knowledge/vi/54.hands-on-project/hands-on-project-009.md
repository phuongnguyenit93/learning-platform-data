# Dự án thực hành: Thu hồi quyền truy cập khi Leaver

> **Chương:** Dự án thực hành  
> **Đề bài:** Thu hồi khi leaver  
> **Bối cảnh:** Module quản lý vòng đời danh tính (IAM Identity Lifecycle) theo mô hình **Joiner–Mover–Leaver (JML)**. Dự án thực hành cách tiếp nhận sự kiện nghỉ việc, xác minh, chặn đăng nhập, thu hồi tài khoản/quyền/credential, đối soát ứng dụng, kiểm toán và khắc phục **quyền truy cập tồn dư**. Có liên hệ với **IdP, SSO, SCIM, RBAC/ABAC và tài khoản dịch vụ**.

## 1. Mục tiêu và sản phẩm cuối cùng

Trong dự án này, bạn đóng vai kỹ sư IAM được giao thiết kế **luồng offboarding an toàn cho một người rời tổ chức (Leaver)**. Hệ thống có HRIS, IdP, nhiều ứng dụng, một số API key và ít nhất một phần mềm cũ không hỗ trợ tự động hóa đầy đủ.

Bạn không chỉ viết lệnh tắt tài khoản. Một yêu cầu Leaver chỉ được xem là **đã hoàn tất** khi các đường truy cập nằm trong phạm vi đã mất hiệu lực theo chính sách, có **bằng chứng đọc lại trạng thái** hoặc được báo cáo minh bạch là ngoại lệ cần xử lý. Phản hồi thành công từ IdP hay HTTP API đơn lẻ không chứng minh tất cả token, phiên và quyền ứng dụng đã bị thu hồi.

### 1.1. Bạn sẽ thực hành được gì?

1. Xác minh **sự kiện Leaver có nguồn đáng tin**, mã chủ thể ổn định, thời điểm hiệu lực và tính khẩn cấp.
2. Vẽ **bản đồ đường truy cập** từ danh tính nhân sự đến IdP/SSO, ứng dụng SaaS, hệ thống không SCIM, quyền trực tiếp, session, API key và PAT.
3. Xây dựng **desired state** cho người đã nghỉ: không còn khả năng truy cập không hợp lệ, nhưng vẫn có thể giữ hồ sơ hoặc dữ liệu theo chính sách.
4. Viết bộ điều phối (orchestrator) và adapter thu hồi cho nhiều hệ đích; hỗ trợ **retry, idempotency, sự kiện đến muộn và lỗi một phần**.
5. Thực hiện **readback** từ hệ đích, phát hiện quyền tồn dư và tạo nhiệm vụ khắc phục có người chịu trách nhiệm.
6. Thiết lập audit trail, điều kiện nghiệm thu và các chỉ số như **leaver revocation latency**.
7. Giải thích cách xử lý **service account/workload identity** do người nghỉ việc sở hữu mà không vô tình làm gián đoạn hệ thống đang hoạt động.

### 1.2. Các sản phẩm phải bàn giao

| Sản phẩm | Nội dung | Bằng chứng |
| --- | --- | --- |
| Sơ đồ kiến trúc | HRIS/sponsor, orchestrator, IdP, ứng dụng, credential, audit | Sơ đồ và các ranh giới tin cậy |
| Đặc tả sự kiện | subjectId, eventId, sourceVersion, effectiveAt, chế độ bình thường/khẩn cấp | JSON sự kiện mẫu và quy tắc validation |
| Ma trận offboarding | Mỗi hệ đích phải thu hồi gì, bằng cách nào, ai xác nhận | Target inventory có owner |
| Trình điều phối | Nhận sự kiện, xác định quyền mục tiêu, thực thi và readback | Code hoặc mock chạy lặp lại được |
| Bộ ca kiểm thử | Leaver thường, khẩn cấp, trùng, lỗi, event muộn, PAT tồn dư | Expected/Actual/PASS–FAIL |
| Audit trail | Nguồn, phê duyệt, thao tác, readback, thời điểm, ngoại lệ | Bản ghi có correlation ID |
| Runbook | Cách xử lý khi app offline, token không thu hồi được, account không tìm thấy | Các bước containment và escalation |
| Báo cáo nghiệm thu | Các target VERIFIED, PARTIAL, FAILED, UNKNOWN; tồn dư còn mở | Bảng kết luận có người chịu trách nhiệm |

### 1.3. Phạm vi và nguyên tắc an toàn

Thực hiện trên **môi trường lab được phép**, với nhân viên, ứng dụng, token và dữ liệu **giả lập**. Không dùng tài khoản công ty thật để thử khóa, thu hồi token hay kiểm tra đăng nhập. Các địa chỉ API, ID và bí mật trong tài liệu là ví dụ minh họa, không dùng trực tiếp vào production.

**Leaver không đồng nghĩa xóa dữ liệu:** khóa đăng nhập, thu hồi quyền và credential là hoạt động quản trị truy cập; xóa tài khoản vĩnh viễn và dữ liệu cần quy trình, thời hạn lưu giữ và nghĩa vụ riêng. Một account ở trạng thái *inactive* được lưu đúng chính sách không nhất thiết là quyền tồn dư.

## 2. Đề bài nghiệp vụ và điều kiện nghiệm thu

Doanh nghiệp giả lập **DemoCo** có năm hệ thống:

| Hệ thống | Chức năng | Đường truy cập | Cách thu hồi |
| --- | --- | --- | --- |
| **Corp IdP** | Xác thực SSO, MFA, nhóm | SAML/OIDC, IdP session | Disable user; revoke phiên/refresh token do IdP kiểm soát |
| **CRM SaaS** | Ticket và dữ liệu khách hàng | SSO, account SCIM, direct ACL | Đặt user inactive, gỡ group/ACL, kiểm tra app session |
| **Finance Portal** | Báo cáo/đối soát tài chính | SSO và role nội bộ | Disable app account hoặc revoke role qua API riêng |
| **Code Hosting** | Kho mã và tự động hóa | SSO, PAT, SSH key, repo membership | Gỡ member, revoke PAT/key cá nhân, xử lý automation phụ thuộc |
| **Legacy VPN** | Truy cập từ xa | Account/credential riêng | API hoặc bước thủ công có owner và bằng chứng |

**Nhân vật:** Lan, mã bất biến **EMP-LAB-041**, đang thuộc Support. Lan dùng CRM, Finance Viewer, code hosting; trước đây Lan có một **grant trực tiếp customers:export** và một PAT được dùng trong pipeline.

**Sự kiện:** HRIS xác nhận Lan rời tổ chức ngày **30/11/2026 lúc 17:00 +07:00**. Tại thời điểm có hiệu lực, phải ngăn các đường truy cập không còn hợp lệ, bàn giao workflow và ghi bằng chứng. Một biến thể khác là **Leaver khẩn cấp** được duyệt để chặn ngay theo quy trình.

### 2.1. Trạng thái mong muốn

| Đối tượng | Trạng thái sau khi Leaver có hiệu lực | Không nên kết luận sai |
| --- | --- | --- |
| Danh tính HR | Terminated theo sự kiện nguồn hợp lệ | HR đổi trạng thái không tự khiến mọi app khóa |
| IdP account | Disabled, không cấp SSO mới; phiên thuộc phạm vi được xử lý | Disable IdP không mặc nhiên hủy toàn bộ app session |
| CRM | Không còn quyền app hợp lệ, user inactive hoặc chính sách tương đương | SCIM active=false không mặc định vô hiệu mọi API key |
| Finance | Không còn role/truy cập theo quan hệ đã chấm dứt | Xóa group IdP không xóa grant trực tiếp trong Finance |
| Code Hosting | Không còn repo membership/PAT/SSH key thuộc Lan | Không thể chỉ chặn giao diện web nếu token API vẫn chạy |
| VPN | Không còn đường đăng nhập từ xa hợp lệ | Hệ thống không SCIM vẫn cần người chịu trách nhiệm |
| Tài sản số | Workflow, dashboard và repo được chuyển owner đúng | Không cần giữ tài khoản Lan active chỉ để bàn giao |
| Dữ liệu/hồ sơ | Được giữ hoặc xử lý theo chính sách áp dụng | Không tự động xóa vĩnh viễn khi nhận Leaver |

### 2.2. Khi nào được ghi COMPLETED?

Phải có **định nghĩa hoàn tất** rõ:

- Sự kiện HRIS được xác minh từ nguồn đáng tin, đúng subjectId, thời điểm và thẩm quyền.
- Mọi hệ đích **bắt buộc trong phạm vi** đã xác minh account/quyền/credential cần thu hồi không còn hiệu lực theo chính sách.
- Các phiên, token, khóa, quyền local và direct ACL có đường xử lý và bằng chứng tương ứng.
- Không còn job Joiner/Mover cũ có thể cấp lại quyền trái với trạng thái Leaver.
- Việc bàn giao owner và lưu giữ dữ liệu được thực hiện hoặc quản lý như nhiệm vụ riêng có dấu vết.
- Mọi ngoại lệ chưa xử lý được ghi **PARTIAL/FAILED/UNKNOWN**, có owner, mức rủi ro và hạn xử lý; không được báo nhầm là hoàn tất toàn bộ.

Trong lab, hãy cố ý tạo một lỗi để thấy trạng thái tổng **PARTIAL** dù bốn trên năm hệ đích đã VERIFIED.

## 3. Kiến trúc luồng thu hồi end-to-end

~~~mermaid
flowchart TD
    HR["HRIS / Sponsor\nLeaver event"] --> IN["Ingest + Authenticate source"]
    IN --> VALID{"Event hợp lệ?\nPhiên bản và mốc hiệu lực đúng?"}
    VALID -->|Không| QUAR["Quarantine / điều tra / audit"]
    VALID -->|Có| DES["Tính desired state\nKhông còn access không hợp lệ"]
    DES --> DISC["Inventory target accounts\nGroups + ACL + tokens"]
    DISC --> ORCH["Offboarding Orchestrator"]
    ORCH --> IDP["IdP adapter\nDisable + session"]
    ORCH --> SCIM["CRM SCIM adapter\nActive + groups"]
    ORCH --> APP["Finance / Code adapters\nRoles + PAT + SSH"]
    ORCH --> MANUAL["VPN manual task\nOwner + due date"]
    IDP --> REC["Readback / Reconciliation"]
    SCIM --> REC
    APP --> REC
    MANUAL --> REC
    REC --> RESULT{"Mọi target bắt buộc VERIFIED?"}
    RESULT -->|Có| DONE["COMPLETED\nAudit + handover"]
    RESULT -->|Không| EX["PARTIAL / FAILED\nRetry + escalation"]
    EX --> REC
    ORCH --> AUD["Audit trail"]
    REC --> AUD
    EX --> AUD
~~~

### 3.1. Vai trò từng thành phần

1. **Identity Source:** HRIS hoặc sponsor xác nhận quan hệ chấm dứt, mã chủ thể ổn định và mốc hiệu lực.
2. **Event Ingestor:** xác thực nguồn, chống event trùng, xử lý version, kiểm tra dữ liệu thiếu và tránh event giả mạo.
3. **Policy/IGA:** xác định điều kiện dừng truy cập, phạm vi hệ thống, yêu cầu lưu giữ, owner, phê duyệt ngoại lệ và trường hợp khẩn cấp.
4. **Orchestrator:** quản lý trạng thái theo target, thứ tự thực thi, retry và readback.
5. **Target Adapters:** IdP, SCIM, API ứng dụng, token store hoặc manual task.
6. **Reconciler:** đọc quyền hiệu lực; phát hiện direct grant, account local, token còn hiệu lực và sai lệch desired–actual.
7. **Audit/Operations:** ghi bằng chứng và cảnh báo khi Leaver chưa hoàn tất.

### 3.2. Lưu ý về thứ tự thu hồi

Với Leaver theo kế hoạch, có thể chuẩn bị inventory và bàn giao trước khi đến **effectiveAt**; không tự động khóa tài khoản sớm nếu chưa được ủy quyền. Với Leaver khẩn cấp, các đường chặn rủi ro cao (IdP login, VPN, token cá nhân, tài khoản đặc quyền) có thể được tiến hành song song theo runbook và thẩm quyền, sau đó tiếp tục xử lý từng ứng dụng cho đến khi VERIFIED.

Thứ tự công việc cần phụ thuộc **mức rủi ro, khả năng hệ đích và điều kiện bảo toàn nghiệp vụ**. Không coi một sequence cố định là giải pháp cho mọi tổ chức. Đặc biệt, token có thời hạn đã phát hành có thể vẫn được chấp nhận ở resource server dù IdP đã disable user.

## 4. Thiết kế sự kiện, trạng thái và dữ liệu

### 4.1. Envelope Leaver

~~~json
{
  "eventId": "HR-LEAVE-LAB-0101",
  "subjectId": "EMP-LAB-041",
  "eventType": "LEAVER",
  "sourceVersion": 27,
  "occurredAt": "2026-11-23T10:00:00+07:00",
  "effectiveAt": "2026-11-30T17:00:00+07:00",
  "mode": "PLANNED",
  "source": "demo-hris",
  "approvedBy": "HR-LAB-OWNER",
  "employmentStatus": "terminated"
}
~~~

Đây là **schema nghiệp vụ do lab định nghĩa**, không phải payload chuẩn SCIM. Phải kiểm tra tính xác thực/ủy quyền nguồn sự kiện bằng phương pháp phù hợp kết nối thật; trường **source** hoặc **approvedBy** trong JSON đơn lẻ **không chứng minh** sự kiện đáng tin.

### 4.2. Phân biệt thời điểm và phiên bản

| Trường | Ý nghĩa | Ví dụ lỗi cần ngăn |
| --- | --- | --- |
| **occurredAt** | Lúc nguồn ghi nhận sự thay đổi | Đồng nhất sai với lúc user phải bị khóa |
| **effectiveAt** | Lúc sự kiện có hiệu lực nghiệp vụ | Khóa quá sớm hoặc quá trễ |
| **receivedAt** | Lúc workflow nhận event | Coi webhook đến trễ là thời điểm cần khóa |
| **verifiedAt** | Lúc đọc lại target xác nhận kết quả | Báo hoàn tất ngay khi gửi API request |
| **sourceVersion** | Trật tự thay đổi theo nguồn | Job Mover v26 cấp lại quyền sau Leaver v27 |
| **eventId** | ID sự kiện dùng cho idempotency và audit | Nhận webhook hai lần và tạo nhiệm vụ trùng |

Một trường hợp người đã nghỉ được **tái tuyển dụng (rehire)** cần **sự kiện/phiên bản mới và chính sách xác minh mới**. Không vô hạn chặn mọi Joiner tương lai chỉ vì lịch sử từng có Leaver; đồng thời không để sự kiện cũ vô tình kích hoạt lại quyền.

### 4.3. Trạng thái từng workflow và từng target

| Trạng thái | Ý nghĩa |
| --- | --- |
| **SCHEDULED** | Sự kiện có hiệu lực trong tương lai; đã kiểm tra và chuẩn bị |
| **IN_PROGRESS** | Đang thực hiện các thao tác chặn và thu hồi |
| **PENDING_VERIFICATION** | Lệnh đã gửi; chưa đọc lại trạng thái hiệu lực |
| **PARTIAL** | Một số target đạt, target khác lỗi/không rõ/chưa xong |
| **FAILED** | Lỗi cần can thiệp/escalation, không tự khắc phục theo đường hiện tại |
| **COMPLETED** | Mọi target bắt buộc VERIFIED theo tiêu chí |
| **REJECTED/QUARANTINED** | Event không hợp lệ hoặc chưa đủ căn cứ triển khai |
| **SUPERSEDED** | Event đã bị thay thế bởi trạng thái nguồn mới hơn |

Không đánh đồng **ACK/SUCCESS của API** với trạng thái **VERIFIED** của target. Một task thủ công cũng cần xác nhận thực tế, không chỉ đóng ticket.

### 4.4. Dữ liệu tối thiểu của một target

~~~yaml
subjectId: EMP-LAB-041
targetSystem: crm-lab
targetAccountId: CRM-U-4481
revocationSurfaces:
  - account-active
  - group-membership
  - direct-acl
  - local-session
adapter: SCIM_AND_APP_API
owner: crm-application-owner
critical: true
desiredState: NO_INVALID_ACCESS
workflowStatus: PENDING_VERIFICATION
lastVerifiedAt: null
~~~

Mỗi đường (account, group, direct ACL, session, credential) phải được kiểm tra theo khả năng của hệ đích. Một field tổng **inactive** không đủ để mô tả tất cả bề mặt thu hồi.

## 5. Inventory: biết phải thu hồi những gì

Trước khi thực thi, lập bản đồ **subjectId → từng targetAccountId và đường truy cập**. Đặc biệt tránh dùng email hoặc tên hiển thị làm khóa nối vì có thể thay đổi hoặc tái sử dụng.

| Bề mặt | Đường cấp quyền | Hành động thu hồi | Cách xác minh |
| --- | --- | --- | --- |
| IdP | Account, group, MFA, IdP session | Disable user, xử lý session/refresh token trong phạm vi | Đọc account inactive, kiểm tra đăng nhập mới bị chặn |
| CRM SCIM | User active, group | SCIM disable và gỡ membership khi cần | GET User/Group và entitlement thực tế |
| CRM app ACL | Role hoặc ACL gán thẳng | App API xóa direct grant | Đọc lại ACL/role; kiểm thử hành động không còn được phép |
| Finance | App account và role | Disable app account/revoke role bằng API riêng | Đọc lại user và role |
| Code Hosting | Repo membership, PAT, SSH | Revoke quyền, key/token cá nhân | Liệt kê membership và trạng thái key/token |
| VPN | Account/credential riêng | Disable qua API hoặc thao tác admin | Xác nhận từ hệ VPN và bằng chứng chặn |
| Workflow ownership | Dashboard, pipeline, repo, scheduled jobs | Chuyển owner hoặc thay credential cá nhân | Owner mới xác nhận, job hoạt động đúng |
| Dữ liệu lưu giữ | Hồ sơ, lịch sử hành động | Quản lý retention/xóa theo chính sách riêng | Hồ sơ lưu giữ không cần account active |

**Bài tập inventory:** tạo một direct grant customers:export ở CRM cho Lan, dù nhóm CRM-Exporters đã bị xóa. Khi Leaver chạy, kiểm tra cả **group và direct grant**; nếu direct grant còn, hệ thống chưa đạt desired state.

### 5.1. Service account do người nghỉ việc sở hữu

Người nghỉ có thể tạo hoặc quản lý **service principal, bot, CI/CD pipeline, workload identity**. Không nên tự động xóa service account đang dùng production chỉ vì owner là Leaver, vì có thể gây ngừng dịch vụ. Cần:

1. Chuyển **business/technical owner** cho người có trách nhiệm hợp lệ.
2. Kiểm kê PAT cá nhân, API key, SSH key, secret và trust relationship do Lan sở hữu hoặc đã biết.
3. Chuyển automation sang **workload identity/managed identity/federation** với scope tối thiểu khi khả thi.
4. Revoke credential cá nhân cũ, xoay secret dùng chung khi chính sách hoặc rủi ro yêu cầu.
5. Kiểm tra pipeline còn hoạt động hợp lệ và không còn đường truy cập cá nhân của Leaver.

Nếu có dấu hiệu credential đã lộ hoặc sự kiện khẩn cấp, ưu tiên containment theo rủi ro và phối hợp khôi phục thay vì kéo dài giữ token rủi ro vì muốn tránh gián đoạn.

## 6. Chuẩn bị lab và dựng trạng thái ban đầu

Bạn có thể làm bài bằng **Java 17+** và những adapter lưu trạng thái trong bộ nhớ. Mô phỏng giúp hiểu điều phối mà không cần quyền truy cập hệ thống thật. Khi chuyển sang nền tảng thật, phải thay mock bằng adapter tuân theo API, authorization và giới hạn riêng của từng dịch vụ.

### 6.1. Fixture: một danh tính với nhiều đường truy cập

~~~yaml
identity:
  subjectId: EMP-LAB-041
  department: Support
  employmentStatus: active
  sourceVersion: 26

targets:
  - name: idp
    accountActive: true
    idpSessionActive: true
  - name: crm-scim
    accountActive: true
    groups: [Support-Agent]
  - name: crm-direct-acl
    entitlements: [customers:export]
  - name: finance
    accountActive: true
    roles: [Finance-Viewer]
  - name: code-hosting
    memberships: [repo-team]
    credentials: [PAT-LAB-01, SSH-LAB-01]
  - name: vpn
    localAccountActive: true
~~~

Các giá trị chỉ là dữ liệu giả. **Không dùng token thật** trong fixture, log hoặc tài liệu.

### 6.2. Các thao tác mà lab phải quan sát được

- **Trước Leaver:** từng target cho thấy account, group, ACL hoặc token còn có hiệu lực.
- **Lần chạy đầu:** IdP, CRM, Finance, Code Hosting thành công nhưng VPN cố ý lỗi một lần.
- **Kết luận lần đầu:** **PARTIAL**, không phải COMPLETED; ghi VPN là target chưa VERIFIED.
- **Chạy lại cùng event:** các target đã xong không tạo thêm quyền; VPN được thử lại, đọc lại và đánh dấu VERIFIED.
- **Kết luận sau retry:** **COMPLETED** khi toàn bộ target bắt buộc xác nhận mất đường truy cập.
- **Event Mover cũ:** không được grant quyền trở lại nếu nguồn mới nhất đã xác nhận Leaver.

### 6.3. Các giả định cần ghi rõ

Lab tự chọn mô hình giản lược để có thể quan sát trạng thái. Trong thực tế, **disable account**, **gỡ role/ACL**, **revoke token** và **hủy session** thường là những API khác nhau, có độ trễ và semantics khác nhau. Một mock target đại diện cho một **bề mặt thu hồi đã kiểm chứng**; không thể coi một mock target “CRM” duy nhất là bằng chứng mọi phiên CRM đã hết hiệu lực nếu chưa mô hình hóa đường phiên riêng.

Để minh bạch, hãy tạo target độc lập cho **IdP account**, **CRM account**, **CRM direct ACL**, **Finance role**, **PAT** và **VPN**. Khi bổ sung khả năng đọc lại một bề mặt mới, thêm target tương ứng.

## 7. Cài đặt bộ điều phối Java 17 trong bộ nhớ

Đoạn mã sau là **chương trình Java hoàn chỉnh có thể lưu thành một file LeaverLab.java** để nghiên cứu. Nó cố tình không gọi hệ thống thật. Mỗi MockTarget đại diện cho **một đường truy cập** và lưu cờ đang hoạt động. Trình điều phối chỉ trả về COMPLETED khi mọi đường được đánh dấu **đã chặn** sau bước readback.

### 7.1. Cấu trúc dữ liệu, adapter và workflow

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.HashSet;

public class LeaverLab {

    enum HrState { ACTIVE, TERMINATED }

    record LeaverEvent(
            String eventId,
            String subjectId,
            long sourceVersion,
            Instant effectiveAt,
            boolean emergency
    ) {}

    record SourceSnapshot(long version, HrState state) {}

    interface Target {
        String name();
        void revoke(String subjectId);
        boolean accessBlocked(String subjectId);
    }

    static final class MockTarget implements Target {
        private final String name;
        private final Set<String> activeSubjects = new HashSet<>();
        private boolean failNext;

        MockTarget(String name, String subjectId) {
            this.name = name;
            activeSubjects.add(subjectId);
        }

        MockTarget failOnce() {
            failNext = true;
            return this;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public void revoke(String subjectId) {
            if (failNext) {
                failNext = false;
                throw new IllegalStateException("Simulated connector timeout");
            }
            activeSubjects.remove(subjectId);
        }

        @Override
        public boolean accessBlocked(String subjectId) {
            return !activeSubjects.contains(subjectId);
        }
    }

    static final class OffboardingService {
        private final Map<String, SourceSnapshot> source;
        private final List<Target> targets;
        private final Clock clock;

        // Bản ghi xử lý để phát hiện eventId bị dùng lại cho dữ liệu khác.
        private final Map<String, LeaverEvent> acceptedEvents = new HashMap<>();
        private final Map<String, String> workflowStatus = new HashMap<>();
        private final Map<String, Map<String, String>> targetStatus =
                new HashMap<>();

        OffboardingService(
                Map<String, SourceSnapshot> source,
                List<Target> targets,
                Clock clock
        ) {
            this.source = source;
            this.targets = new ArrayList<>(targets);
            this.clock = clock;
        }

        String handle(LeaverEvent event) {
            Objects.requireNonNull(event);
            if (event.eventId() == null || event.eventId().isBlank()
                    || event.subjectId() == null || event.subjectId().isBlank()
                    || event.effectiveAt() == null) {
                return "QUARANTINED";
            }

            LeaverEvent previous =
                    acceptedEvents.putIfAbsent(event.eventId(), event);
            if (previous != null && !previous.equals(event)) {
                return "QUARANTINED"; // Cùng eventId nhưng payload khác.
            }

            // Mọi quyết định phải dựa trên trạng thái nguồn mới nhất.
            SourceSnapshot latest = source.get(event.subjectId());
            if (latest == null || latest.version() < event.sourceVersion()) {
                return "QUARANTINED";
            }
            if (latest.state() != HrState.TERMINATED) {
                return "SUPERSEDED"; // Ví dụ: đã được tái tuyển dụng.
            }
            if (!event.emergency()
                    && clock.instant().isBefore(event.effectiveAt())) {
                return "SCHEDULED";
            }

            if ("COMPLETED".equals(workflowStatus.get(event.eventId()))) {
                return "COMPLETED";
            }

            Map<String, String> results = targetStatus.computeIfAbsent(
                    event.eventId(), ignored -> new LinkedHashMap<>()
            );

            for (Target target : targets) {
                try {
                    // Mỗi adapter đưa đích về desired state;
                    // không cộng thêm quyền mỗi khi retry.
                    if (!target.accessBlocked(event.subjectId())) {
                        target.revoke(event.subjectId());
                    }
                    boolean verified = target.accessBlocked(event.subjectId());
                    results.put(target.name(),
                            verified ? "VERIFIED" : "UNKNOWN");
                } catch (RuntimeException connectorError) {
                    results.put(target.name(), "FAILED");
                }
            }

            boolean allVerified = targets.stream().allMatch(t ->
                    "VERIFIED".equals(results.get(t.name()))
            );
            String status = allVerified ? "COMPLETED" : "PARTIAL";
            workflowStatus.put(event.eventId(), status);
            return status;
        }

        Map<String, String> targetResults(String eventId) {
            return Map.copyOf(targetStatus.getOrDefault(
                    eventId, Map.of()
            ));
        }
    }

    public static void main(String[] args) {
        String subject = "EMP-LAB-041";
        LeaverEvent event = new LeaverEvent(
                "HR-LEAVE-LAB-0101",
                subject,
                27L,
                Instant.parse("2026-11-30T10:00:00Z"),
                false
        );

        Map<String, SourceSnapshot> authoritative = Map.of(
                subject, new SourceSnapshot(27L, HrState.TERMINATED)
        );

        List<Target> targets = List.of(
                new MockTarget("idp-account", subject),
                new MockTarget("idp-session", subject),
                new MockTarget("crm-scim-account", subject),
                new MockTarget("crm-direct-acl", subject),
                new MockTarget("finance-role", subject),
                new MockTarget("code-hosting-PAT", subject),
                new MockTarget("vpn-local", subject).failOnce()
        );

        Clock clock = Clock.fixed(
                Instant.parse("2026-11-30T10:01:00Z"),
                ZoneOffset.UTC
        );

        OffboardingService service =
                new OffboardingService(authoritative, targets, clock);

        System.out.println("First  = " + service.handle(event));
        System.out.println("Targets= " + service.targetResults(event.eventId()));

        System.out.println("Retry  = " + service.handle(event));
        System.out.println("Targets= " + service.targetResults(event.eventId()));

        System.out.println("Replay = " + service.handle(event));
    }
}
~~~

### 7.2. Kết quả dự kiến

~~~text
First  = PARTIAL
Targets= {... vpn-local=FAILED, idp-account=VERIFIED, ...}
Retry  = COMPLETED
Targets= {... vpn-local=VERIFIED, idp-account=VERIFIED, ...}
Replay = COMPLETED
~~~

Thứ tự mục trong Map có thể khác tùy cách hiển thị và JDK; điều cần kiểm chứng là **trạng thái**. Mock sử dụng Clock cố định để mô phỏng thời điểm sau **17:00 +07:00**; trong một ca khác hãy đặt Clock trước mốc này để xác minh kết quả **SCHEDULED**.

### 7.3. Những gì mã mẫu đã chứng minh và chưa chứng minh

**Đã minh họa:**

- Cùng một event có thể chạy lại mà không tạo grant; bề mặt đã chặn được đọc lại.
- Một target lỗi không làm các target đã thành công bị lùi trạng thái.
- Workflow tổng **PARTIAL** khi một target chưa verified; có thể retry để đi tới **COMPLETED**.
- Trạng thái nguồn mới nhất quyết định việc tiếp tục offboarding; có so sourceVersion.
- Mỗi đường truy cập có một target riêng thay vì gộp “IdP đã khóa = mọi quyền đã mất”.

**Chưa phải cài đặt production:**

- Không có cơ sở dữ liệu bền vững, hàng đợi, transaction/outbox hoặc khóa đồng thời.
- Không có xác thực và ủy quyền nguồn HR event; boolean **emergency** ở lab không phải bằng chứng phê duyệt khẩn cấp.
- Không có SCIM/HTTP thực, OIDC/SAML, xử lý timeout thật, readback có độ trễ, rotation hay rate limit.
- Không giữ audit trail bền vững hoặc retry policy có backoff/escalation.
- Không kiểm tra thời điểm thực sự ngừng access token tại một resource server.
- Không tự động xử lý trường hợp đăng nhập hợp lệ mới, rehire hoặc nhiều sự kiện cập nhật cạnh tranh.

Ở môi trường thật, cần lưu bản ghi event và target state **bền vững**, ràng buộc tính duy nhất eventId, xử lý concurrency theo subjectId và thực thi **kiểm tra version ở sát thời điểm ghi** để job cũ không cấp lại quyền.

### 7.4. Bài tập mở rộng mã mẫu

1. Thêm một target **crm-app-session** có thể chỉ bị thu hồi sau bước xác minh riêng.
2. Cho **crm-direct-acl** lỗi hai lần; thêm số lần thử và lịch retry có giới hạn.
3. Thêm trạng thái **UNKNOWN** khi readback không trả được kết quả, phân biệt với đã gửi lệnh thành công.
4. Thêm hàm xử lý **MOVER** có kiểm tra phiên bản; chứng minh Mover v26 không thể cấp role Finance khi nguồn đã ở **LEAVER v27**.
5. Lưu snapshot trạng thái target trước và sau; tạo báo cáo chênh lệch **desired/actual**.
6. Thêm owner và thời hạn khắc phục cho những target FAILED.

Không cần kết nối dịch vụ thật để hoàn thành các bài tập mở rộng này.

## 8. Thiết kế adapter thật: IdP, SCIM, API, credential và tác vụ thủ công

Sau khi hiểu mô phỏng, hãy viết **hợp đồng adapter** cho từng hệ đích. Không nên trộn “gửi lệnh revoke” với “xác minh quyền đã mất”. Mỗi adapter phải trình bày ít nhất **identity mapping, thao tác, kết quả, readback và lỗi có thể xảy ra**.

### 8.1. IdP: vô hiệu danh tính và phiên

Các thao tác tùy sản phẩm có thể bao gồm:

1. Tìm user bằng **ID được ánh xạ từ subjectId**, không dựa duy nhất vào email.
2. Disable account hoặc đặt trạng thái không được đăng nhập.
3. Revoke những phiên/refresh token do IdP quản lý nếu tính năng có hỗ trợ.
4. Đọc lại user state; kiểm tra một đăng nhập SSO mới bị từ chối trong môi trường thử nghiệm được phép.
5. Lưu thời điểm, correlation ID và những đường phiên/token **không thuộc quyền điều khiển của IdP**.

Đừng mặc định IdP có API để hủy mọi phiên SaaS. OIDC, SAML và các ứng dụng có thể dùng session riêng; việc disable danh tính chỉ đảm bảo những cơ chế thực sự tham chiếu đến IdP được áp dụng theo sản phẩm.

### 8.2. CRM SCIM: cập nhật trạng thái User

Với ứng dụng hỗ trợ **SCIM 2.0**, một adapter có thể yêu cầu cập nhật thuộc tính **active** của User bằng PATCH tương đương:

~~~http
PATCH /scim/v2/Users/CRM-U-4481 HTTP/1.1
Content-Type: application/scim+json
Authorization: Bearer <SCIM_CONNECTOR_CREDENTIAL>

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Đoạn này minh họa **cú pháp PatchOp**, không phải lời khuyên dán trực tiếp vào hệ thống thật. Placeholder credential không phải bí mật. Trong triển khai thực, endpoint, phương thức xác thực, mã account, quota, lỗi và semantics **active=false** phải theo tài liệu của ứng dụng.

**Readback tối thiểu:**

~~~http
GET /scim/v2/Users/CRM-U-4481 HTTP/1.1
Authorization: Bearer <SCIM_CONNECTOR_CREDENTIAL>
~~~

Kiểm tra trạng thái **active** nhận được, nhưng **đừng dừng tại đó**. Nếu ứng dụng còn ACL trực tiếp hoặc token riêng, cần API hoặc tác vụ kiểm chứng bổ sung. Một số ứng dụng xử lý cập nhật bất đồng bộ, nên câu trả lời thành công từ PATCH chưa chứng minh quyền đã biến mất ngay lập tức.

### 8.3. App entitlement: xử lý direct grant

Đối với quyền **customers:export** cấp trực tiếp trong CRM, adapter cần:

- Liệt kê **effective entitlements** và nguồn cấp (group, role, direct ACL) nếu ứng dụng cung cấp.
- Xóa direct grant liên quan đến Lan; không xóa nhầm quyền của nhóm người khác.
- Đọc lại ACL và khả năng thực thi **customers:export** trong ngữ cảnh thử nghiệm.
- Nếu quyền xuất vẫn đến từ một group khác, tiếp tục loại bỏ đường cấp không hợp lệ.

**Bài kiểm thử:** khi đã xóa group CRM-Exporters nhưng còn direct grant, hệ thống phải trả **NOT_VERIFIED/PARTIAL**. Chỉ sau khi direct grant được xử lý và quyền xuất bị từ chối, bề mặt này mới VERIFIED.

### 8.4. Finance API: app không dùng SCIM

Nếu Finance có API riêng:

~~~text
findAccount(subjectId) -> financeUserId
disableAccount(financeUserId) -> operationId
revokeRole(financeUserId, roleId) -> operationId
readAccount(financeUserId) -> active/state
listRoles(financeUserId) -> actualRoles
~~~

Các phương thức trên là **hợp đồng giả mã**. Khi gắn vào sản phẩm thật, cần xử lý mapping và quyền của service credential gọi API; không để người dùng tự gửi ID của người khác để xóa role.

Nếu Finance chỉ hỗ trợ thao tác admin thủ công, thay adapter tự động bằng task có **owner, deadline, hướng dẫn, ảnh/bản ghi bằng chứng được bảo vệ** và bước xác nhận. Không đánh dấu VERIFIED chỉ vì ticket đã được chuyển người phụ trách.

### 8.5. Code hosting: PAT, SSH key, OAuth grant và automation

Kiểm kê credential thuộc Lan và cách thu hồi của từng loại:

| Đường truy cập | Kết quả cần xác minh | Cạm bẫy |
| --- | --- | --- |
| Repo membership | Lan không còn collaborator/team role | Repo riêng hoặc nhóm khác còn cấp quyền |
| Personal Access Token (PAT) | PAT đã revoke, không còn dùng được | PAT tiếp tục chạy dù SSO user disabled nếu nền tảng cho phép |
| SSH key | Khóa không còn là đường truy cập được ủy quyền | Authorized key nằm ở server/repo độc lập |
| OAuth app grant | Quyền ứng dụng bên thứ ba liên quan được xử lý | Chỉ xóa role nhưng vẫn còn grant riêng |
| Pipeline sử dụng PAT | Có credential workload mới hoặc pipeline bị dừng có kiểm soát | Cắt PAT bất ngờ có thể làm hỏng job quan trọng |

Nếu nghi token bị lộ, cần ưu tiên chặn đường truy cập có rủi ro theo quy trình; nếu chỉ bàn giao theo kế hoạch, có thể chuẩn bị credential workload trước mốc và revoke PAT đúng thời điểm. Trong cả hai trường hợp phải có owner và bằng chứng.

### 8.6. Session và access token: xác minh đúng ranh giới

Một phiên ứng dụng không nhất thiết kết thúc khi IdP disable user. Với **access token tự chứa** đã cấp, resource server có thể tiếp tục chấp nhận đến hết hạn nếu không tra trạng thái mới hoặc cơ chế revoke. Tùy kiến trúc, lựa chọn có thể gồm:

- Revoke session tại hệ đích, nếu app có API.
- Revoke refresh token để không thể cấp thêm access token.
- Sử dụng introspection/deny-list hoặc policy check ở resource server nếu được hỗ trợ.
- Thiết lập TTL đủ ngắn và kiểm soát thời gian còn hiệu lực theo rủi ro.
- Dùng chặn tại gateway/đường truy cập khi cần containment khẩn cấp và có thẩm quyền.

**Không hứa thu hồi tức thời khi hệ thống không hỗ trợ.** Hãy ghi trạng thái **UNKNOWN/IN_PROGRESS**, độ trễ rủi ro còn lại và biện pháp đang áp dụng; đo thời điểm readback thực sự xác nhận ngừng truy cập.

## 9. Xử lý sự kiện, thời điểm và race condition

### 9.1. Leaver theo kế hoạch

Với **effectiveAt=30/11/2026 17:00 +07:00**:

| Mốc | Việc có thể thực hiện | Điều phải tránh |
| --- | --- | --- |
| Trước 17:00 | Xác minh HR event, kiểm kê account/credential, bàn giao owner, chuẩn bị job | Disable trước giờ nếu chưa được ủy quyền |
| Đúng mốc có hiệu lực | Bắt đầu chặn đăng nhập và revoke theo runbook | Dùng giờ máy không có timezone, xử lý chậm không có cảnh báo |
| Sau khi gửi lệnh | Đọc lại trạng thái từng target, xử lý app chưa xong | Báo COMPLETED chỉ từ API ACK |
| Sau đối soát | Đóng event hoặc giữ ngoại lệ có owner | Che giấu target UNKNOWN hoặc FAILED |

Một task được lập lịch cần bền vững qua restart. Nếu hệ thống nhận event **sau effectiveAt**, phải xử lý theo chính sách với mức ưu tiên phù hợp, không đợi thêm một chu kỳ vô hạn.

### 9.2. Leaver khẩn cấp

Kịch bản: HR/Security có quyết định hợp lệ yêu cầu khóa Lan **ngay** vì lý do đã được xác minh. Bộ điều phối phải:

1. Xác thực người/phần mềm yêu cầu và thẩm quyền theo runbook; không tin cờ **emergency=true** do client bất kỳ gửi.
2. Xác định cách chặn nhanh các đường có rủi ro cao: IdP, VPN, tài khoản admin, API key/PAT liên quan.
3. Tiến hành các tác vụ có thể song song, ghi thời điểm từng target bị chặn.
4. Báo ngay những target chưa liên lạc được; duy trì biện pháp giảm rủi ro thay thế nếu có.
5. Tiếp tục readback và hậu kiểm; không nhầm “đã cố gắng thu hồi” với “đã chặn thành công”.

Trong lab, **emergency** là giả định đã được bên ngoài xác thực. Khi thiết kế sản xuất, cần đối tượng **authorization decision** riêng có quyết định, người/phần mềm phê duyệt, thời điểm và log kiểm toán.

### 9.3. Mover cũ đến sau Leaver

~~~text
16:55  HR phát MOVER v26: cấp role Finance-Viewer
16:57  Job Mover v26 gặp timeout ở Finance
17:00  HR phát LEAVER v27 cho cùng subjectId
17:01  Leaver v27 revoke role và disable các account
17:02  Job Mover v26 được retry
~~~

Nếu job v26 chỉ gọi **grant Finance-Viewer**, quyền có thể sống lại sau Leaver. Cần:

- Kiểm tra **sourceVersion và trạng thái nguồn mới nhất** trước mọi thao tác grant hoặc retry.
- Không thực hiện grant dựa trên một event đã bị thay thế.
- Dùng kiểm soát cạnh tranh theo subjectId, điều kiện cập nhật hoặc điều phối tuần tự khi phù hợp.
- Kiểm tra trạng thái sau các job song song, vì việc kiểm tra phiên bản quá sớm vẫn có thể dẫn tới race giữa check và apply.
- Đối soát toàn bộ quyền thực tế sau xử lý Leaver.

### 9.4. Leaver cũ đến sau sự kiện tái tuyển dụng

Một người từng nghỉ, sau đó có Joiner mới được xác minh với **sourceVersion cao hơn**. Event Leaver cũ tới muộn không được tùy tiện khóa danh tính đã được tái kích hoạt theo chính sách. Vì vậy không nên dùng quy tắc tuyệt đối “đã từng Leaver thì không bao giờ được active”; phải đánh giá **trạng thái mới nhất, effectiveAt, version và quy trình identity reactivation**. Nếu có nghi ngờ hoặc dữ liệu nguồn mâu thuẫn, cần cách ly để xác minh.

### 9.5. Idempotency và retry

Lệnh thu hồi được thiết kế theo **trạng thái mục tiêu**, không theo số lần gọi:

~~~text
BAD:
  deleteUser(); throwErrorIfAlreadyDeleted()

BETTER:
  if account exists and still grants invalid access:
      disableOrRevoke(account)
  verifyNoInvalidAccess()
~~~

Nhưng ngay cả thao tác “đảm bảo account disabled” cũng phải xử lý timeout: lệnh có thể đã thành công nhưng phản hồi bị mất. Khi retry, **đọc lại trạng thái trước**, tránh tạo lỗi giả hoặc tác động không cần thiết.

Phân loại ví dụ:

| Trường hợp | Hành động phù hợp |
| --- | --- |
| 429 / rate limit | Retry có giới hạn, backoff và tôn trọng thông tin retry của API |
| Timeout/mạng ngắt | Readback khi có thể; retry an toàn theo trạng thái mục tiêu |
| Không tìm thấy user | Xác minh mapping và kỳ vọng account; có thể đã vô hiệu/xóa hoặc map sai |
| 403 do connector thiếu quyền | Escalate quyền connector/cấu hình, không tự cấp đặc quyền bừa bãi |
| HR event sai ID/nguồn | Cách ly, không thay account khác dựa trên suy đoán |
| SCIM trả OK nhưng app vẫn active | PENDING_VERIFICATION, kiểm tra cơ chế bất đồng bộ và readback |
| Manual task quá hạn | Escalate cho app owner, báo rủi ro và giữ trạng thái mở |

Đừng chỉ dựa vào mã HTTP; hành vi lỗi và hợp đồng API cần được kiểm tra ở hệ thống đích thực tế.

## 10. Ma trận kiểm thử dự án

Hãy chuẩn bị dữ liệu giả và chạy các tình huống sau. Mỗi lần thử lưu **Expected, Actual, PASS/FAIL, evidence reference** và trạng thái quyền hiệu lực sau chạy. Các ca kiểm thử được phân loại để dễ nghiệm thu.

| ID | Dữ liệu / tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **LV-01** | Leaver theo lịch trước effectiveAt | SCHEDULED, chưa chặn sớm ngoài chính sách |
| **LV-02** | Đến effectiveAt, mọi adapter hoạt động | Mọi target VERIFIED, workflow COMPLETED |
| **LV-03** | Leaver event được gửi hai lần | Kết quả nhất quán, không có side effect sai |
| **LV-04** | Cùng eventId nhưng payload khác | Cách ly/không tin dữ liệu mâu thuẫn |
| **LV-05** | Nguồn HR không đáng tin hoặc chữ ký sai | Không thực thi; ghi lý do/alert |
| **LV-06** | Thiếu subjectId hoặc mapping user | Không thao tác bừa; yêu cầu xác minh |
| **LV-07** | Ứng dụng CRM timeout một lần | PARTIAL, retry có kiểm soát, readback sau retry |
| **LV-08** | SCIM trả ACK nhưng app vẫn active | PENDING_VERIFICATION, không COMPLETED |
| **LV-09** | IdP disabled, Finance còn role | PARTIAL; tiếp tục revoke ở Finance |
| **LV-10** | CRM Group đã gỡ, direct ACL vẫn còn | Phát hiện quyền tồn dư và gỡ ACL |
| **LV-11** | PAT cá nhân vẫn gọi API | Không kết luận Leaver hoàn tất, xử lý PAT |
| **LV-12** | Phiên app cũ còn hiệu lực | Ghi thời gian/biện pháp chặn theo cơ chế app |
| **LV-13** | VPN chỉ hỗ trợ admin thao tác thủ công | Có task, owner, bằng chứng readback |
| **LV-14** | Legacy app owner không phản hồi | Escalation, ngoại lệ quá hạn không bị che |
| **LV-15** | Mover v26 chạy lại sau Leaver v27 | Không cấp lại quyền/khôi phục account |
| **LV-16** | Leaver v27 tới muộn sau rehire v28 | Không khóa nhầm identity đang hợp lệ |
| **LV-17** | Leaver khẩn cấp được ủy quyền | Chặn ưu tiên các đường rủi ro, ghi audit |
| **LV-18** | Client giả mạo Leaver khẩn cấp | Bị từ chối do thiếu thẩm quyền |
| **LV-19** | Account đã inactive từ trước | Revoke idempotent, xác minh quyền đã mất |
| **LV-20** | Repo ownership chưa bàn giao | Có task/owner; không giữ quyền truy cập vô hạn |
| **LV-21** | Pipeline dùng PAT của người đã nghỉ | Chuyển workload credential, thu hồi PAT |
| **LV-22** | Job retry chạy đồng thời | Không ghi đè trạng thái mới hơn và có readback |
| **LV-23** | Attribute ABAC vẫn là active tại một app | Phát hiện drift và chặn theo policy |
| **LV-24** | Có tài khoản local ngoài SSO | Inventory và thu hồi được đường login local |
| **LV-25** | Toàn bộ target VERIFIED | Audit có event, actions, verifiedAt, không còn ngoại lệ mở |

### 10.1. Ví dụ báo cáo kiểm thử

~~~yaml
testCase: LV-07
eventId: HR-LEAVE-LAB-0101
subjectId: EMP-LAB-041
target: crm-lab
input: "SCIM connector fails once"
expectedFirst: PARTIAL
actualFirst: PARTIAL
expectedAfterRetry: COMPLETED
actualAfterRetry: COMPLETED
verification:
  account: inactive
  directAcl: no-invalid-grant
  token: no-valid-personal-token
result: PASS
evidenceRef: "lab://evidence/LV-07"
~~~

Đây là kết quả **giả định minh họa**, không phải chứng nhận đã chạy test. Người học phải thay **actual** bằng dữ liệu quan sát được; nếu không kiểm tra được token hoặc session, đánh dấu **UNKNOWN/PENDING** thay vì điền PASS.

## 11. Runbook: xử lý Leaver còn quyền khi hệ thống lỗi

Một dự án thực hành tốt phải chỉ rõ **người trực vận hành cần làm gì** khi workflow không thể tự hoàn tất. Runbook không nên chỉ ghi “retry” mà phải giải thích trạng thái, rủi ro, containment, owner, readback và bằng chứng.

### 11.1. Quy trình chuẩn theo mức ưu tiên

1. **Tiếp nhận cảnh báo:** lấy eventId, subjectId, hệ đích, thời điểm phải thu hồi, lỗi gần nhất và trạng thái đã xác minh.
2. **Xác định mức rủi ro:** quyền production admin, tài chính, dữ liệu khách hàng hoặc credential độc lập thường cần ưu tiên khác quyền đọc dữ liệu ít nhạy cảm.
3. **Kiểm tra nguồn:** HRIS/sponsor có xác nhận đúng Leaver, phiên bản và thời điểm không? Tránh khóa nhầm người.
4. **Containment theo thẩm quyền:** chặn những đường sẵn có như IdP, VPN, gateway, khóa/token; không tự giả định có thể thao tác mọi hệ đích.
5. **Điều tra nguyên nhân:** connector lỗi API, account mapping sai, token còn hiệu lực, policy stale hay manual task không có người nhận?
6. **Remediation:** retry an toàn hoặc thực hiện các bước thay thế theo runbook được duyệt, không cấp quyền rộng cho connector tùy tiện.
7. **Verification:** đọc lại account, group, ACL, session, credential theo bề mặt bị ảnh hưởng.
8. **Closure:** chỉ đóng sau khi đủ bằng chứng; nếu thiếu, giữ ngoại lệ có owner, deadline và biện pháp giảm rủi ro.

### 11.2. Ví dụ: CRM offline tại thời điểm Leaver

**17:00:** HR event có hiệu lực. IdP và Finance xác nhận inactive, nhưng CRM connector timeout.

**17:01:** Workflow ghi trạng thái CRM=FAILED/UNKNOWN, tổng=PARTIAL. Cảnh báo chứa subjectId, eventId, thời điểm, error class và mức rủi ro, **không chứa access token hay mật khẩu**.

**17:03:** App owner xác định hệ CRM offline. IAM/Security đánh giá biện pháp chặn tạm ở gateway hoặc kênh đăng nhập khác có thẩm quyền; ghi rõ hạn chế (ví dụ app session đã cấp trước đó có thể còn hiệu lực).

**17:10:** CRM phục hồi. Connector đọc lại account trước để tránh thay đổi trùng, thực hiện disable và gỡ direct ACL; đọc lại user/group/ACL. Nếu phiên hoặc PAT độc lập cần xử lý, tiếp tục theo phương án app hỗ trợ.

**17:12:** Tất cả đường bắt buộc VERIFIED; lưu **verifiedAt** thực tế cho CRM. Không dùng **17:00** làm thời điểm CRM đã bị khóa nếu chưa có bằng chứng từ thời điểm đó.

Mốc giờ trên là **tình huống giả định**, không phải SLA chuẩn. SLA và kênh escalation cần dựa trên mức nhạy cảm, hợp đồng vận hành và khả năng kỹ thuật.

### 11.3. Bảng xử lý lỗi nhanh

| Dấu hiệu | Giả thuyết | Cách xác minh | Hướng xử lý |
| --- | --- | --- | --- |
| IdP inactive nhưng CRM đăng nhập được | App local session/credential riêng còn sống | Xác minh đường app login, session, token | Revoke tại app hoặc containment theo policy |
| SCIM PATCH thành công nhưng user active | Xử lý bất đồng bộ, mapping sai hoặc app không áp dụng | SCIM GET và app status | Đối chiếu mapping, retry/owner |
| Group bị xóa nhưng quyền export còn | Direct ACL, nhóm khác, token scope | Liệt kê effective grants | Gỡ từng đường không hợp lệ |
| PAT vẫn chạy khi account disabled | Token độc lập với SSO | Token inventory/endpoint test được phép | Revoke/rotate, thay workload credential |
| VPN không có SCIM | Thiếu kênh automation | App owner xác nhận account local | Manual task + readback |
| Job Mover cấp lại role | Sự kiện cũ được retry không kiểm tra version | Log sourceVersion, target state | Chặn grant cũ, revoke lại, sửa điều phối |
| Không thể xác minh account | Target offline hoặc API không hỗ trợ readback | Owner xác định hạn chế | Giữ UNKNOWN, bằng chứng thay thế có xác nhận |
| Service principal không có owner | Nhân viên nghỉ nhưng workload chưa bàn giao | Danh mục workload, secret và usage | Chuyển owner, review scope/credential |

### 11.4. Mẫu phiếu ngoại lệ

~~~yaml
exceptionId: OFFBOARD-LAB-EX-003
eventId: HR-LEAVE-LAB-0101
subjectId: EMP-LAB-041
targetSystem: crm-lab
issue: "SCIM readback unavailable"
riskClass: HIGH
workflowStatus: PARTIAL
containment: "SSO disabled; independent app session not yet verified"
owner: crm-application-owner
escalationOwner: security-on-call
nextAction: "Verify app session and direct ACL when API returns"
dueAt: "2026-11-30T17:30:00+07:00"
verifiedAt: null
~~~

Một ngoại lệ không biến quyền đang tồn dư thành quyền hợp lệ. Nó là **bản ghi sai lệch minh bạch** để có người chịu trách nhiệm xử lý đến khi kết thúc.

## 12. Thiết kế audit trail và báo cáo kiểm chứng

Kết quả offboarding phải có thể truy vết theo chuỗi:

**Nguồn Leaver → Kiểm tra thẩm quyền → Quyết định và phạm vi → Lệnh gửi → Kết quả hệ đích → Readback → Ngoại lệ → Xác nhận đóng.**

### 12.1. Trường audit gợi ý

| Trường | Giải thích |
| --- | --- |
| **eventId** | Mã sự kiện HR/sponsor |
| **subjectId** | Danh tính bất biến của người nghỉ |
| **source, sourceVersion** | Nguồn có thẩm quyền và phiên bản hiện tại |
| **mode, effectiveAt** | Nghỉ theo kế hoạch hay khẩn cấp, mốc cần chặn |
| **workflowId, correlationId** | Nối các thao tác của cùng một workflow |
| **policyVersion, approvalRef** | Căn cứ quyết định và thẩm quyền |
| **targetSystem, targetAccountId** | Tài khoản cụ thể cần thu hồi |
| **requestedAction, adapterResult** | Đã yêu cầu làm gì và API phản hồi gì |
| **actualState, verifiedAt** | Trạng thái thực tế đã đọc lại, thời điểm xác nhận |
| **exceptionId, owner, dueAt** | Phần chưa đạt, người xử lý và hạn |
| **completedAt** | Lúc toàn workflow thỏa điều kiện hoàn tất |

### 12.2. Ví dụ bản ghi sau khi Leaver hoàn tất

~~~json
{
  "workflowId": "OFFBOARD-LAB-0101",
  "eventId": "HR-LEAVE-LAB-0101",
  "subjectId": "EMP-LAB-041",
  "effectiveAt": "2026-11-30T17:00:00+07:00",
  "status": "COMPLETED",
  "targets": [
    {
      "system": "idp",
      "status": "VERIFIED",
      "actual": "disabled",
      "verifiedAt": "2026-11-30T17:00:30+07:00"
    },
    {
      "system": "crm",
      "status": "VERIFIED",
      "actual": "inactive; no-invalid-grants",
      "verifiedAt": "2026-11-30T17:12:00+07:00"
    },
    {
      "system": "finance",
      "status": "VERIFIED",
      "actual": "disabled",
      "verifiedAt": "2026-11-30T17:01:15+07:00"
    },
    {
      "system": "code-hosting",
      "status": "VERIFIED",
      "actual": "no-personal-PAT-or-membership",
      "verifiedAt": "2026-11-30T17:05:00+07:00"
    },
    {
      "system": "vpn",
      "status": "VERIFIED",
      "actual": "disabled",
      "verifiedAt": "2026-11-30T17:06:00+07:00"
    }
  ],
  "openExceptions": [],
  "completedAt": "2026-11-30T17:12:00+07:00"
}
~~~

Đây là **bản ghi giả định sau khi mọi target đã xác minh**. Khi dùng thực tế, cần bổ sung đường session/token nào nằm trong phạm vi, link bằng chứng và trạng thái bàn giao owner. Không tự gộp nhiều đường truy cập chưa kiểm tra vào một trường “disabled” cho đẹp báo cáo.

### 12.3. Chỉ số nên tính từ dữ liệu đọc lại

| Chỉ số | Công thức/ý nghĩa |
| --- | --- |
| **Leaver revocation latency** | verifiedAt của target bắt buộc cuối cùng trừ thời điểm cần thu hồi |
| **Critical target latency** | verifiedAt của từng hệ nhạy cảm trừ effectiveAt |
| **Partial completion rate** | Số workflow Leaver còn PARTIAL/FAILED chia số workflow trong phạm vi đo |
| **Residual access count** | Số account, ACL, key hoặc token còn truy cập được mà không có căn cứ |
| **Orphan account count** | Account không ánh xạ với chủ thể/workload hoặc owner hợp lệ |
| **Token revocation coverage** | Tỷ lệ đường token thuộc phạm vi có thể xác minh kết quả thu hồi |
| **Reconciliation coverage** | Tỷ lệ app có readback entitlement/account thực tế |
| **Exception overdue count** | Số ngoại lệ còn mở quá deadline đã đặt theo rủi ro |
| **Regrant-after-leaver incidents** | Số lần grant được thực thi sai sau trạng thái chấm dứt |

Nếu hệ đích chưa xác minh được quyền mất hiệu lực, không dùng thời điểm gửi lệnh làm mốc verifiedAt. Với workflow vẫn PARTIAL, báo cáo **latency đang mở/không xác định** thay vì một con số thành công giả.

### 12.4. Bảo mật bằng chứng

- Không ghi password, private key, raw PAT, access token hoặc refresh token vào audit.
- Bảo vệ log khỏi sửa trái phép, hạn chế người có quyền truy cập và có quy trình lưu giữ.
- Chỉ lưu thông tin định danh cần cho truy vết; tránh lan truyền dữ liệu cá nhân không cần thiết.
- Tách quyền xem audit khỏi quyền thay đổi account khi chính sách cần phân nhiệm.
- Đối với bằng chứng kiểm chứng thủ công, chỉ dùng phương pháp thu thập được cho phép, tránh chứa dữ liệu nhạy cảm trong ảnh hoặc ticket.

## 13. Đánh giá rủi ro: khi nào không thể dùng một luồng chung?

Một số tình huống thay đổi thứ tự và tính khẩn cấp của công việc:

### 13.1. Nghỉ việc có kế hoạch

Có thời gian chuẩn bị bàn giao, chuyển owner, thay credential trong automation và kiểm thử trước mốc có hiệu lực. Không nên mặc định khóa sớm tài khoản nếu còn nhiệm vụ hợp lệ.

### 13.2. Chấm dứt khẩn cấp có thẩm quyền

Ưu tiên containment nhanh và hành động có thể thực thi ngay. Nếu một app offline, có thể dùng biện pháp chặn khác theo runbook, nhưng phải ghi rõ **đường nào vẫn chưa xác minh**. Trạng thái PARTIAL là thông tin quan trọng, không phải lý do để bỏ qua quy trình.

### 13.3. Người có quyền đặc biệt

Một Leaver có role quản trị cloud, database hoặc hệ thống tài chính có thể cần thêm PAM/JIT, secret rotation, break-glass review, session termination và kiểm tra quyền cấp trực tiếp. Không đủ nếu chỉ gỡ role nhân sự cơ bản.

### 13.4. Nhà thầu và tài khoản bên ngoài

Nguồn chấm dứt có thể là **ngày hết hợp đồng** hoặc quyết định của sponsor. Phải đối soát guest user, external group, liên kết chia sẻ và quyền theo tenant. Nếu hợp đồng được gia hạn hợp lệ, cần kiểm tra sự kiện mới nhất trước khi thu hồi nhầm.

### 13.5. Workload gắn với cá nhân

Khi owner nghỉ, cần phân biệt **danh tính cá nhân phải thu hồi** với **danh tính máy vẫn có nghiệp vụ cần hoạt động**. Chuyển owner và credential có kiểm soát không có nghĩa giữ PAT cá nhân của Leaver vô thời hạn.

### 13.6. App không hỗ trợ revoke tức thời

Giới hạn kỹ thuật có thể khiến một access token có hiệu lực đến khi hết TTL. Hãy mô tả thời gian còn lại, cơ chế giảm rủi ro và mức độ chấp nhận theo thẩm quyền. Không tự khẳng định đã thu hồi tức thời nếu resource server vẫn chấp nhận token.

## 14. Rubric tự đánh giá dự án

Tự chấm theo thang **0–3** cho từng tiêu chí: **0 = chưa có**, **1 = chỉ mô tả**, **2 = có thực thi nhưng thiếu kiểm chứng/lỗi**, **3 = có thực thi, test âm tính và bằng chứng đầy đủ**.

| Tiêu chí | Cách đạt mức 3 |
| --- | --- |
| **Nguồn và thời gian** | Event có nguồn, ID, version, effectiveAt; xử lý lịch và khẩn cấp được kiểm chứng |
| **Danh mục truy cập** | Có đủ IdP, app, ACL, local login, session, token, workload owner trong phạm vi |
| **Desired state** | Quyền mục tiêu rõ, không xóa dữ liệu tùy tiện, có yêu cầu bàn giao |
| **Tự động hóa** | Các adapter idempotent, trạng thái từng target và retry có kiểm soát |
| **Readback** | Thực sự kiểm tra account/entitlement/session/token tương ứng theo khả năng đích |
| **Lỗi một phần** | Target offline dẫn tới PARTIAL, owner xử lý, không báo sai |
| **Chống regrant** | Mover cũ, event trùng, rehire và race có kiểm tra version |
| **Quyền tồn dư** | Direct ACL, PAT và local account được phát hiện, xử lý, xác minh |
| **Kiểm toán** | Truy được nguồn → quyết định → lệnh → readback → kết luận |
| **Runbook** | Có containment, escalation, hạn xử lý, verification và closure |
| **Dữ liệu và bảo mật** | Lab dùng dữ liệu giả, không lộ token và log có phạm vi cần thiết |
| **Tài liệu bàn giao** | Người khác có thể dựng fixture và lặp lại ca kiểm thử |

Thang tối đa minh họa là **36 điểm**; đây không phải chứng nhận chuyên môn. Quan trọng nhất là khả năng nói rõ **điều gì đã được chứng minh** và **điều gì chưa thể xác minh**.

### 14.1. Checklist nghiệm thu cuối

- [ ] Event Leaver có subjectId, eventId, version, effectiveAt và được xác minh từ nguồn đáng tin.
- [ ] Danh mục target bao phủ account, group, direct ACL, session, token, VPN và các đường app local thuộc phạm vi.
- [ ] Có policy về thời điểm chặn và phân biệt nghỉ theo lịch với tình huống khẩn cấp.
- [ ] IdP bị disable và có bằng chứng chặn SSO mới.
- [ ] App có SCIM/API được cập nhật và đọc lại trạng thái thực tế.
- [ ] Direct grant không còn hiệu lực; kiểm thử được quyền nhạy cảm bị từ chối.
- [ ] PAT/API key/SSH key và session liên quan đã được xử lý hoặc ghi ngoại lệ minh bạch.
- [ ] Legacy/manual target có owner, deadline, bước xác nhận.
- [ ] Workflow không biến ACK thành VERIFIED khi chưa có readback.
- [ ] Duplicate event không gây side effect sai.
- [ ] Mover cũ không thể cấp lại quyền sau Leaver mới hơn.
- [ ] Có xử lý sự kiện đến sau rehire theo trạng thái nguồn mới nhất.
- [ ] Một target lỗi làm tổng trạng thái PARTIAL; retry và escalation được kiểm chứng.
- [ ] Workload/service account có owner hợp lệ và credential cá nhân cũ được rà soát.
- [ ] Bằng chứng chứa effectiveAt, verifiedAt, trạng thái từng target và các ngoại lệ.
- [ ] Không sử dụng dữ liệu, hệ thống hoặc credential thật ngoài phạm vi được phép.

## 15. Bài tập thảo luận và hướng giải

### Bài tập A — “Đã xong” nhưng còn direct ACL

**Bối cảnh:** Leaver của Lan hoàn tất disable IdP và SCIM CRM User thành inactive. App owner phát hiện vẫn có direct ACL **customers:export**.

**Câu hỏi:** Có thể đóng workflow chưa? Cần bổ sung gì?

**Gợi ý:** Chưa thể coi mọi bề mặt đã VERIFIED. Cần xác định app có tiếp tục cho phép hành động qua đường nào; gỡ direct ACL, kiểm chứng quyền hiệu lực và ghi kết quả. Nếu account inactive đủ chặn mọi thao tác theo cơ chế đã kiểm chứng, vẫn phải ghi rõ đường ACL và cách xử lý theo chính sách để tránh quyền bị khôi phục khi rehire.

### Bài tập B — Job grant đã gửi trước nhưng hoàn tất sau Leaver

**Bối cảnh:** Mover v26 gửi lệnh Finance grant lúc 16:59, server Finance chỉ áp dụng lúc 17:02, trong khi Leaver v27 đã chạy lúc 17:00.

**Câu hỏi:** Chỉ kiểm tra sourceVersion lúc gửi lệnh Mover có đủ không?

**Gợi ý:** Không. Tình huống là race giữa check và apply. Cần điều phối/điều kiện cập nhật, theo dõi job đang chờ và **đối soát sau Leaver** để đảm bảo quyền mục tiêu vẫn không có hiệu lực. Có thể cần hủy job cũ hoặc revoke bổ sung.

### Bài tập C — PAT trong pipeline

**Bối cảnh:** Pipeline ban đêm cần chạy để đối soát dữ liệu, nhưng đang dùng PAT của Lan. Lan rời tổ chức lúc 17:00.

**Câu hỏi:** Làm thế nào vừa thu hồi quyền cá nhân vừa không để pipeline không có owner?

**Gợi ý:** Trước mốc nếu có thể, chuyển ownership, triển khai credential workload có scope tối thiểu, kiểm thử pipeline trên đường mới, revoke PAT cá nhân đúng thời điểm và ghi bằng chứng. Nếu PAT có rủi ro cao/khẩn cấp, containment có thể đi trước và đội vận hành xử lý khôi phục chức năng.

### Bài tập D — Leaver rồi rehire

**Bối cảnh:** HR gửi Leaver v27, sau đó HR xác minh rehire v28. Một bản sao của Leaver v27 đến muộn.

**Câu hỏi:** Hệ thống dựa vào thông tin gì để không khóa nhầm nhân viên?

**Gợi ý:** Trạng thái nguồn có thẩm quyền mới nhất, sourceVersion, thời điểm hiệu lực, mapping subject/account và chính sách reactivation. Bỏ hoặc cách ly event cũ khi đã bị thay thế, ghi audit quyết định.

### Bài tập E — Không thể đọc lại trạng thái VPN

**Bối cảnh:** Quản trị viên xác nhận đã disable VPN qua ticket nhưng không có API kiểm tra account.

**Câu hỏi:** Có thể báo VERIFIED bằng cách nào?

**Gợi ý:** Thiết kế bằng chứng thay thế có người chịu trách nhiệm (ví dụ xác nhận trạng thái trên console quản trị được phép, hồ sơ thao tác hoặc kiểm thử có kiểm soát). Ghi giới hạn của bằng chứng. Không biến việc “ticket assigned” thành kết quả VERIFIED nếu chưa có chứng cứ thực hiện.

## 16. Tổng kết dự án và bước tiếp theo

Đầu ra quan trọng nhất của bài **Thu hồi khi leaver** không phải số API đã gọi, mà là **bản đồ quyền đã bị chặn thực tế và bằng chứng có thể kiểm tra lại**. Một Leaver đáng tin phải gắn được:

**Sự kiện nguồn được xác minh → Thời điểm có hiệu lực → Danh mục tài khoản/credential → Thu hồi theo từng target → Readback quyền hiệu lực → Ngoại lệ có owner → Kiểm toán và kết luận.**

Qua dự án, người học cần nhớ:

- **IdP/SSO** quản lý xác thực liên kết; không mặc định điều khiển phiên hoặc PAT riêng của mọi ứng dụng.
- **SCIM/API** giúp đồng bộ User/Group/account; semantics disable và khả năng revoke session/token phải kiểm tra theo sản phẩm.
- **RBAC/ABAC, ACL và direct grant** có thể tạo nhiều đường tới cùng quyền, nên phải đọc lại **effective access**.
- **Joiner–Mover–Leaver** là chuỗi liên tục: job cũ, sự kiện đến muộn và rehire phải được xử lý theo trạng thái nguồn mới nhất.
- **Service account** có vòng đời riêng; người tạo nghỉ việc không có nghĩa tự động xóa workload còn cần thiết.
- **Audit và reconciliation** là bằng chứng rằng kết quả đã xảy ra; PARTIAL/UNKNOWN là trạng thái hợp lệ khi chưa thể chứng minh hoàn tất.

**Bước nâng cao:** thay mock adapter bằng một môi trường thử nghiệm hợp lệ có IdP và một ứng dụng hỗ trợ SCIM, thêm nguồn sự kiện đáng tin, kho trạng thái bền vững, hàng đợi retry, policy engine, kiểm thử chéo tenant và dashboard theo dõi quyền tồn dư. Chỉ triển khai lên production sau khi có quy trình phê duyệt, phân quyền connector, thử nghiệm phương án khôi phục và runbook vận hành phù hợp.

Khi bạn có thể mô phỏng **một Leaver bình thường, một Leaver khẩn cấp, một connector lỗi, một PAT còn sống và một Mover cũ đến muộn**, đồng thời giải thích được trạng thái thực tế sau từng bước, bạn đã đi từ hiểu khái niệm IAM lifecycle đến biết **thiết kế và kiểm chứng một luồng thu hồi có kiểm soát**.
