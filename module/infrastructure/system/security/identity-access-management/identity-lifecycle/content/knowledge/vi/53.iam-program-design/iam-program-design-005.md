# Xác định lifecycle event khi thiết kế chương trình IAM

Trong **Identity and Access Management (IAM)**, một nhân viên được tuyển dụng, chuyển phòng ban hoặc nghỉ việc không tự làm thay đổi quyền ở mọi hệ thống. Chương trình IAM cần biết **điều gì đã xảy ra, nguồn nào xác nhận, khi nào thay đổi có hiệu lực và phải thực hiện hành động gì**. Những thông tin đó được mô tả bằng *lifecycle event* — sự kiện vòng đời danh tính.

Ví dụ, HRIS ghi nhận ngày 01/06 rằng một nhân viên sẽ gia nhập công ty ngày 15/06. Nếu hệ thống IAM coi thời điểm tạo hồ sơ là ngày bắt đầu làm việc, tài khoản và quyền có thể được kích hoạt quá sớm. Ngược lại, nếu HRIS xác nhận nhân viên nghỉ việc ngay lập tức nhưng bộ cấp quyền chỉ đồng bộ qua một tác vụ chạy ban đêm, quyền truy cập có thể tồn dư nhiều giờ.

Bài học thuộc chương **Thiết kế chương trình IAM** trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Trọng tâm là xác định những sự kiện dẫn dắt mô hình **Joiner–Mover–Leaver (JML)**, kết nối nguồn danh tính với IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và quy trình thu hồi quyền thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **sự kiện nghiệp vụ**, **trạng thái danh tính**, **lệnh điều phối** và **kết quả thực thi**.
2. Thiết kế danh mục lifecycle event cho nhân viên, nhà thầu, đối tác, tài khoản dịch vụ và workload.
3. Định nghĩa hợp đồng sự kiện có khóa nguồn, ID, phiên bản, thời gian phát sinh/hiệu lực và dấu vết kiểm toán.
4. Xử lý sự kiện trùng, đến trễ, sai thứ tự, được lên lịch trong tương lai hoặc bị hủy/thay thế.
5. Ánh xạ sự kiện JML thành hành động cấp/đổi/thu hồi quyền, có xác nhận từ hệ thống đích.
6. Đo được độ trễ, tỷ lệ thất bại và những quyền truy cập còn tồn dư sau sự kiện vòng đời.

## 2. Lifecycle event là gì?

**Lifecycle event** là thông báo có cấu trúc rằng một sự kiện có ý nghĩa đối với vòng đời danh tính hoặc quan hệ của danh tính với tổ chức **đã xảy ra hoặc đã được xác nhận sẽ có hiệu lực**. Sự kiện thường do một hệ thống có thẩm quyền phát hành, chẳng hạn HRIS cho nhân viên, hệ thống quản lý hợp đồng cho nhà thầu hoặc service catalog cho workload.

Ví dụ:

- `EMPLOYMENT_START_SCHEDULED`: quan hệ lao động đã được xác nhận, ngày bắt đầu nằm trong tương lai.
- `EMPLOYMENT_STARTED`: quan hệ lao động chính thức có hiệu lực.
- `ORGANIZATIONAL_ASSIGNMENT_CHANGED`: phòng ban, chức năng, người quản lý hoặc đơn vị công tác đã thay đổi.
- `EMPLOYMENT_TERMINATED`: quan hệ lao động kết thúc tại một thời điểm hiệu lực cụ thể.
- `CONTRACT_END_CHANGED`: ngày kết thúc hợp đồng của nhà thầu được điều chỉnh.
- `SECURITY_HOLD_PLACED`: danh tính bị đặt hạn chế truy cập bởi quy trình bảo mật có thẩm quyền.
- `WORKLOAD_RETIRED`: workload hoặc dịch vụ đã kết thúc vòng đời hoạt động.

**Sự kiện không đồng nghĩa với lệnh.** “Nhà thầu đã hết hợp đồng” là một dữ kiện nghiệp vụ; “vô hiệu hóa tài khoản SaaS” là lệnh mà IAM phát ra dựa trên dữ kiện và chính sách. “SaaS xác nhận account đã disabled” là kết quả thực thi. Phân biệt ba bước này giúp biết chính xác tiến trình đã hoàn tất hay đang dừng ở đâu.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Business event** | Điều gì đã xảy ra hoặc được xác nhận? | HRIS phát sự kiện hợp đồng kết thúc. |
| **Identity lifecycle state** | Hiện quan hệ/danh tính ở trạng thái nào? | `ACTIVE`, `SUSPENDED`, `TERMINATED`. |
| **Lifecycle policy decision** | IAM cần làm gì theo quy định? | Thu hồi role và chặn đăng nhập khi Leaver có hiệu lực. |
| **Provisioning command** | Yêu cầu hành động nào được gửi tới đích? | `DisableAccount` hoặc `RemoveEntitlement`. |
| **Execution result** | Hệ thống đích đã thực hiện đến đâu? | `CONFIRMED`, `FAILED` hoặc `PENDING`. |
| **Reconciliation finding** | Trạng thái thực tế đã khớp mong muốn chưa? | Account vẫn active dù Leaver đã có hiệu lực. |

Một chương trình có thể dùng sự kiện thay đổi thuộc tính hoặc snapshot toàn bộ bản ghi nguồn. Dù triển khai kiểu nào, cần giải thích được **ý nghĩa nghiệp vụ** của thay đổi và có cách xác nhận trạng thái hiện hành để tránh quyết định dựa vào một thông báo thiếu bối cảnh.

## 3. Lập danh mục lifecycle event theo nhóm danh tính

Một danh mục tốt không bắt đầu từ tên API của IdP hay thao tác SCIM. Nó bắt đầu từ **những biến cố làm thay đổi tính hợp lệ, phạm vi công việc hoặc quyền truy cập**.

### 3.1. Nhân viên

| Event nghiệp vụ | Nguồn có thẩm quyền thường gặp | Ý nghĩa | Phản ứng IAM |
|---|---|---|---|
| `EMPLOYMENT_START_SCHEDULED` | HRIS | Đã có quyết định tuyển dụng và ngày bắt đầu. | Tạo hồ sơ nội bộ; chuẩn bị account theo chính sách nhưng chưa mặc định bật truy cập. |
| `EMPLOYMENT_STARTED` | HRIS | Đã đến thời điểm quan hệ có hiệu lực. | Kiểm tra điều kiện, cấp baseline và role được phê duyệt. |
| `ORGANIZATIONAL_ASSIGNMENT_CHANGED` | HRIS | Thay đổi bộ phận, người quản lý, chức danh, địa điểm. | Tính lại RBAC/ABAC; thu hồi quyền cũ, xem xét cấp quyền mới. |
| `EMPLOYMENT_SUSPENDED` | HRIS hoặc quy trình có thẩm quyền | Quan hệ tạm thời bị đình chỉ theo chính sách. | Xác định hạn chế truy cập, thời gian và đường khôi phục. |
| `EMPLOYMENT_TERMINATION_SCHEDULED` | HRIS | Có kế hoạch kết thúc quan hệ vào thời điểm tương lai. | Lên lịch thu hồi; kiểm tra mốc hiệu lực và ngoại lệ đã duyệt. |
| `EMPLOYMENT_TERMINATED` | HRIS | Quan hệ kết thúc có hiệu lực. | Chặn truy cập, gỡ entitlement, vô hiệu hóa account và đối soát. |
| `EMPLOYMENT_REINSTATED` | HRIS | Quan hệ được phục hồi hoặc có quyết định tuyển lại. | Xác minh lại danh tính, chính sách và phê duyệt; không tự phục hồi mọi quyền cũ. |

Tên event ở đây là **đề xuất danh mục chuẩn hóa**, không phải tên bắt buộc mà mọi HRIS phải phát. Hệ thống nguồn có thể chỉ gửi `employeeStatusChanged` hoặc snapshot; lớp tiếp nhận IAM phải ánh xạ chính xác sang ngữ nghĩa nội bộ.

**Không suy từ mọi thay đổi nhân sự rằng quyền phải đổi.** Ví dụ thay số điện thoại liên hệ có thể chỉ cần cập nhật thông tin, trong khi thay bộ phận có thể thay toàn bộ entitlement. Hợp đồng sự kiện cần nêu **các trường nào ảnh hưởng tới chính sách truy cập**.

### 3.2. Nhà thầu và đối tác

| Event | Nguồn thường gặp | Lưu ý thiết kế |
|---|---|---|
| `CONTRACT_APPROVED` | VMS/hệ thống hợp đồng | Có hợp đồng đã duyệt chưa đồng nghĩa đến ngày được phép truy cập. |
| `CONTRACT_STARTED` | VMS | Kích hoạt đúng scope và thời gian đã phê duyệt. |
| `CONTRACT_SCOPE_CHANGED` | VMS/owner hợp đồng | Tính lại quyền theo dự án, đơn vị bảo trợ hoặc phạm vi dịch vụ. |
| `CONTRACT_END_CHANGED` | VMS | Hủy/lập lại lịch thu hồi nếu ngày kết thúc thay đổi; phải có version. |
| `CONTRACT_EXPIRED` hoặc `CONTRACT_TERMINATED` | VMS | Thu hồi theo mốc hiệu lực; kết thúc sớm cần được xử lý ưu tiên. |
| `SPONSOR_CHANGED` | Hệ thống quản lý người bảo trợ | Rà soát owner phê duyệt; không tự gia hạn hợp đồng. |
| `PARTNER_RELATIONSHIP_ENDED` | Partner registry | Chấm dứt quyền của tài khoản/nhóm thuộc quan hệ đối tác theo phạm vi xác định. |

Ngày hợp đồng kết thúc nên được hiểu theo định nghĩa nghiệp vụ đã thống nhất. Ví dụ `endAt` là mốc **đầu tiên mà quyền không còn hợp lệ** giúp tránh mơ hồ “còn được truy cập hết ngày 30/09 hay không”. Nếu nguồn cung cấp ngày không kèm giờ, phải quy định múi giờ, giờ kết thúc và phép chuyển đổi rõ ràng.

### 3.3. Service account và workload identity

Danh tính phi con người có vòng đời tách biệt với ngày tuyển dụng hoặc nghỉ việc của kỹ sư:

| Event | Nguồn | Tác động dự kiến |
|---|---|---|
| `SERVICE_REGISTERED` | Service catalog | Ghi nhận service ID, owner, môi trường và mục đích. |
| `WORKLOAD_DEPLOYED` | Hệ thống triển khai/cloud orchestration | Cấp workload identity và quyền tối thiểu cho workload được xác minh. |
| `SERVICE_OWNER_CHANGED` | Service catalog | Rà soát quyền, quy trình phê duyệt và trách nhiệm credential. |
| `WORKLOAD_SCOPE_CHANGED` | Deployment/infrastructure catalog | Tính lại quyền theo môi trường, resource và nhiệm vụ mới. |
| `CREDENTIAL_COMPROMISED` | Hệ thống bảo mật | Cô lập/thu hồi credential liên quan theo quy trình khẩn cấp. |
| `WORKLOAD_RETIRED` | Hệ thống triển khai/service catalog | Thu hồi role, token/credential và tài khoản không còn cần thiết. |

Khi nhân viên sở hữu service account nghỉ việc, sự kiện Leaver có thể kích hoạt **chuyển chủ sở hữu và đánh giá credential**, nhưng không đủ để khẳng định workload cũng đã kết thúc. Nguồn có thẩm quyền của workload mới quyết định vòng đời dịch vụ.

### 3.4. Sự kiện bảo mật và rà soát quyền

Một số event liên quan IAM không thuộc trực tiếp quy trình nhân sự:

- `SECURITY_HOLD_PLACED` và `SECURITY_HOLD_RELEASED`: đặt/gỡ hạn chế truy cập theo thẩm quyền của bộ phận an ninh.
- `ACCESS_REVIEW_REVOKE_APPROVED`: owner kết luận entitlement không còn cần thiết; IAM phát lệnh thu hồi.
- `PRIVILEGED_GRANT_EXPIRED`: quyền đặc biệt đến hạn phải được thu hồi.
- `ACCOUNT_COMPROMISE_DETECTED`: tín hiệu sự cố thúc đẩy các hành động ứng phó.

Các sự kiện này **không được tự động ghi đè** trạng thái nhân sự. Ví dụ HRIS vẫn báo `ACTIVE` thì không vì vậy gỡ `securityHold=true`; mỗi loại dữ liệu có nguồn và owner riêng.

## 4. Xác định ranh giới sự kiện và ngữ nghĩa chính xác

Một event dễ hiểu phải mô tả **một sự thật đã xác nhận**. Có bốn câu hỏi phải thống nhất với owner nguồn:

1. **Sự kiện xảy ra khi nào?** Ngày nhập liệu, ngày phê duyệt, ngày nghiệp vụ có hiệu lực có thể khác nhau.
2. **Sự kiện đại diện cho sự thật gì?** Hồ sơ được tạo, quyết định được phê duyệt hay quan hệ đã bắt đầu?
3. **Điều gì có thể thay đổi sau đó?** Lịch bắt đầu/nghỉ việc có thể bị hoãn, hủy hoặc chỉnh; sự kiện cần cách thay thế và liên kết.
4. **Sự kiện áp dụng cho đối tượng nào?** Một con người có thể đồng thời có quan hệ nhân viên và nhà thầu, hoặc nhiều hợp đồng độc lập.

Ví dụ, `EMPLOYMENT_TERMINATION_SCHEDULED` khác với `EMPLOYMENT_TERMINATED`. Sự kiện thứ nhất có thể kích hoạt chuẩn bị danh sách account, tạo kế hoạch thu hồi và đặt lịch; sự kiện thứ hai xác nhận kết thúc theo mốc hiệu lực. Nếu HRIS không phát loại thứ hai, IAM cần **hợp đồng chuyển trạng thái dựa trên mốc có thẩm quyền** và cơ chế tái xác nhận trước khi thi hành.

### Event nghiệp vụ hay event thay đổi thuộc tính?

Hai cách thường gặp:

**Business event:**

~~~json
{
  "type": "ORGANIZATIONAL_ASSIGNMENT_CHANGED",
  "identitySourceId": "EMP-1042",
  "newDepartmentId": "ENG",
  "effectiveAt": "2026-06-15T00:00:00+07:00"
}
~~~

**Attribute change notification:**

~~~json
{
  "type": "EMPLOYEE_RECORD_UPDATED",
  "identitySourceId": "EMP-1042",
  "changedFields": ["departmentId", "managerId"],
  "sourceVersion": 18
}
~~~

Business event trình bày ý nghĩa rõ hơn; attribute event thường đơn giản hơn cho nguồn phát nhưng đòi hỏi IAM đọc lại trạng thái nguồn, đánh giá thay đổi và xác định ý nghĩa JML. Không nên từ chối một mô hình chỉ vì tên event khác nhau, miễn **hợp đồng dữ liệu và quy tắc ra quyết định được kiểm thử**.

## 5. Hợp đồng dữ liệu lifecycle event

Mỗi event nên có **envelope** (vỏ thông điệp) chung, cộng phần payload theo loại. Một hợp đồng tối thiểu gồm:

| Trường | Mục đích | Lưu ý |
|---|---|---|
| `eventId` | Định danh duy nhất cho lần phát hành sự kiện. | Dùng để phát hiện bản sao trong phạm vi nguồn. |
| `eventType` | Tên nghiệp vụ ổn định. | Có catalog và phiên bản schema. |
| `schemaVersion` | Phiên bản định dạng. | Thay đổi breaking cần quy trình nâng cấp. |
| `source.system` | Hệ thống phát hành được xác thực. | Không tin tự do vào tên nguồn trong payload. |
| `source.recordId` | Khóa đối tượng ở nguồn. | Kết hợp source system để liên kết identity. |
| `source.version` / `sequence` | Thứ tự của các thay đổi cho cùng đối tượng. | Tránh áp bản cũ đè bản mới. |
| `subjectType` | Employee, contractor, partner, service, workload... | Điều khiển đúng bộ chính sách. |
| `occurredAt` | Khi sự kiện/biến cố được ghi nhận. | Phân biệt với thời điểm có hiệu lực. |
| `effectiveAt` | Khi điều kiện nghiệp vụ bắt đầu có hiệu lực. | Dùng cho lập lịch và thời điểm thu hồi. |
| `publishedAt` | Khi hệ thống nguồn đưa event ra luồng. | Hỗ trợ đo độ trễ vận chuyển. |
| `correlationId` | Liên hệ chuỗi xử lý xuyên hệ thống. | Liên kết event → lệnh → xác nhận. |
| `causationId` / `supersedesEventId` | Event nào dẫn tới hoặc bị thay thế. | Hữu ích cho thay lịch và replay. |
| `payload` | Thuộc tính nghiệp vụ cần thiết. | Hạn chế PII, mô tả schema và trường bắt buộc. |

Ba mốc **`occurredAt`, `effectiveAt` và `publishedAt`** không được dùng lẫn nhau. Ngoài ra, IAM có thể ghi `receivedAt` khi nhận, `processedAt` khi quyết định xong và `verifiedAt` khi đích xác nhận để đo chính xác độ trễ từng phần.

### Ví dụ hợp đồng cho sự kiện Mover

~~~json
{
  "eventId": "evt-f79a",
  "eventType": "ORGANIZATIONAL_ASSIGNMENT_CHANGED",
  "schemaVersion": 1,
  "subjectType": "EMPLOYEE",
  "source": {
    "system": "HRIS",
    "recordId": "EMP-1042",
    "version": 18
  },
  "occurredAt": "2026-06-01T08:30:00+07:00",
  "effectiveAt": "2026-06-15T00:00:00+07:00",
  "publishedAt": "2026-06-01T08:30:05+07:00",
  "correlationId": "corr-d2b4",
  "payload": {
    "previousDepartmentId": "FIN",
    "newDepartmentId": "ENG",
    "newManagerSourceId": "EMP-1020"
  }
}
~~~

Ví dụ mô tả một quyết định thay đổi phòng ban được ghi ngày 01/06 nhưng có hiệu lực ngày 15/06. IAM có thể lập kế hoạch từ sớm, song **không được áp role mới ngay** chỉ vì đã nhận event. Khi đến hạn, cần kiểm tra lịch thay đổi vẫn còn hợp lệ, rồi áp chênh lệch quyền và đối soát.

### Cách quản trị hợp đồng với hệ thống nguồn

Trước khi tích hợp, IAM và owner nguồn cần thống nhất:

- Các `eventType` và trường bắt buộc; định nghĩa rõ điều kiện tạo event.
- Cơ chế xác thực và ủy quyền hệ thống phát; bảo vệ đường truyền và chống giả mạo.
- Sự ổn định của source record ID và nguyên tắc không tái sử dụng ID.
- Cách nguồn cấp version/sequence, phát event sửa sai và hủy lịch.
- Ký hiệu thời gian (ISO 8601 có offset hoặc UTC), quy tắc múi giờ và tính chính xác timestamp.
- Dung sai trễ, độ ưu tiên sự kiện khẩn cấp, SLA, retry, replay và lịch đối soát.
- Cách giới hạn dữ liệu cá nhân, thời hạn lưu giữ và quyền truy cập nhật ký.

**Không đưa bản ghi nhân sự đầy đủ vào mọi event nếu không cần.** IAM chỉ cần dữ liệu tối thiểu đủ để xác định danh tính, tác động và chính sách, hoặc tham chiếu tới bản ghi nguồn đã được xác thực.

## 6. Mô hình trạng thái danh tính và chuyển trạng thái

Một sự kiện không phải bản thân trạng thái; nó có thể **kích hoạt một chuyển trạng thái** sau khi kiểm tra điều kiện.

Ví dụ giản lược cho một **quan hệ lao động**:

~~~mermaid
stateDiagram-v2
    [*] --> Pending: EmploymentStartScheduled
    Pending --> Active: EmploymentStarted / effectiveAt reached
    Pending --> Cancelled: PlannedStartCancelled
    Active --> OnHold: EmploymentSuspended
    OnHold --> Active: EmploymentResumed
    Active --> Ended: EmploymentTerminated
    OnHold --> Ended: EmploymentTerminated
    Ended --> [*]
    Cancelled --> [*]
~~~

Sơ đồ không áp dụng nguyên xi cho mọi tổ chức. Đặc biệt:

- Một người có thể có **nhiều quan hệ** (nhân viên, nhà thầu, đối tác) trong các thời kỳ khác nhau. Trạng thái của mỗi quan hệ cần được theo dõi độc lập.
- Tuyển dụng lại có thể là **quan hệ mới** với ID nguồn hoặc hợp đồng mới. Không nên tự khôi phục toàn bộ entitlement của lần làm việc trước.
- `securityHold` có thể là **trạng thái hạn chế truy cập độc lập** với trạng thái lao động, tránh làm mất ý nghĩa khi HRIS cập nhật.
- `OnHold` có thể có nhiều nguyên nhân. Chính sách nghỉ phép, đình chỉ hoặc tạm ngừng truy cập có thể khác nhau theo tổ chức.

### Trạng thái nghiệp vụ và trạng thái thực thi

Sau event Leaver, quan hệ có thể là `ENDED`, trong khi việc thu hồi quyền ở hệ thống SaaS vẫn đang `PENDING` do API lỗi. Đó là hai sự thật cùng tồn tại:

~~~text
Relationship state  = ENDED
Desired access      = DISABLED
Provisioning status = RETRYING
Target account      = ACTIVE   <- sai lệch cần khắc phục
~~~

Không được chờ API hoàn tất mới đổi trạng thái quan hệ nghiệp vụ. Đồng thời không được đánh dấu yêu cầu thu hồi là hoàn tất khi quyền ở đích vẫn còn.

## 7. Chuyển lifecycle event thành hành động JML

### 7.1. Joiner — chuẩn bị và kích hoạt đúng thời điểm

Một event bắt đầu quan hệ có thể đi qua các bước:

1. Xác minh nguồn và khóa định danh; kiểm tra bản ghi chưa được xử lý/trùng người.
2. Xác định thời điểm bắt đầu và các điều kiện bắt buộc (xác minh danh tính, phê duyệt, bảo mật).
3. Tạo identity nội bộ và lập kế hoạch account thuộc phạm vi.
4. Tính entitlement cơ sở từ RBAC/ABAC, tạo yêu cầu phê duyệt cho role nhạy cảm.
5. Tạo hoặc chuẩn bị account theo chính sách; kích hoạt truy cập chỉ khi đủ điều kiện.
6. Đọc lại trạng thái tài khoản, role và phiên đăng nhập ở đích; ghi audit.

Một lời mời nhận việc hoặc bản ghi HRIS được nhập sớm **không tự động cấp quyền**. Account có thể được chuẩn bị trước, nhưng chính sách cần phân biệt `PREPARED` và `ACTIVE`.

### 7.2. Mover — đánh giá lại quyền, không chỉ thêm nhóm

Khi event thay đổi phòng ban, dự án, manager, vai trò công việc hoặc tenant có hiệu lực, IAM phải tính lại **trạng thái quyền mong muốn** theo các chính sách đã duyệt:

~~~text
desired = evaluateCurrentPolicies(identity, newAuthoritativeFacts)
actual  = observeAccountsAndEntitlements(identity)

toGrant  = desired - actual
toRevoke = actual - desired

validateApprovalsAndSeparationOfDuties()
executeRiskAwareChangePlan(toRevoke, toGrant)
readBackTargetStatesAndRecordEvidence()
~~~

Đây là giả mã định hướng. Trong thực tế cần giữ **nguồn gốc của từng entitlement**: nếu quyền được cấp đồng thời từ hai role hợp lệ, không được gỡ chỉ vì một role kết thúc. Các quyền trực tiếp ngoài role catalog cần được phát hiện và rà soát riêng.

Ví dụ chuyển từ người phê duyệt chi sang người thực hiện thanh toán, nếu **Separation of Duties (SoD)** cấm giữ hai quyền, phải chặn xung đột trong khoảng chuyển tiếp. Có thể cần thu hồi và xác minh quyền duyệt cũ trước khi kích hoạt quyền thanh toán mới.

### 7.3. Leaver — thu hồi quyền có xác nhận

Event Leaver có thẩm quyền phải dẫn tới kế hoạch thu hồi trên **mọi account thuộc scope**:

- Chặn đăng nhập ở IdP và ngắt phiên/token khi nền tảng hỗ trợ.
- Thu hồi assignment, group và entitlement qua SCIM/API, PAM hoặc quy trình có bằng chứng.
- Kiểm tra tài khoản cục bộ, quyền cấp trực tiếp và credential gắn với cá nhân.
- Đối soát bằng dữ liệu đọc lại từ từng hệ thống đích.
- Ghi nhận và chuyển xử lý lỗi hoặc đối tượng chưa thể thu hồi.

**SSO** kiểm soát đường đăng nhập liên kết, **SCIM** hỗ trợ thao tác tài khoản, còn **RBAC/ABAC** xác định quyền nên có; không cơ chế nào riêng lẻ chứng minh toàn bộ quyền đã được thu hồi. Một tài khoản SaaS bị vô hiệu hóa nhưng token riêng hoặc khóa API chưa hết hiệu lực vẫn có thể là vấn đề cần xử lý.

### 7.4. Hạn chế bảo mật khẩn cấp

`SECURITY_HOLD_PLACED` có thể đòi hỏi chặn truy cập **ngay khi xác nhận** và ưu tiên cao hơn các event thay đổi phòng ban thông thường. Chỉ nguồn có thẩm quyền bảo mật mới được phát `SECURITY_HOLD_RELEASED`. Một event HRIS `ACTIVE` đến sau không được tự gỡ trạng thái khóa.

Đồng thời phải tránh coi event khóa bảo mật là nghỉ việc: có thể cần giữ quan hệ nhân sự và account phục vụ điều tra/khôi phục, chỉ hạn chế truy cập cho đến khi được phép.

## 8. Event-driven architecture và đường đối soát

~~~mermaid
flowchart TD
    SRC["HRIS / VMS / Service Catalog / Security"] --> VAL["Tiếp nhận event<br/>xác thực + schema + version"]
    VAL --> LOG["Inbox / event ledger<br/>dedupe + nguồn gốc"]
    LOG --> STATE["Kiểm tra trạng thái hiện hành<br/>và thời điểm hiệu lực"]
    STATE --> POLICY["JML policy<br/>RBAC / ABAC / SoD"]
    POLICY --> PLAN["Action plan + transactional outbox"]
    PLAN --> IDP["IdP / SSO<br/>account, session"]
    PLAN --> APP["SCIM / API / PAM / ticket<br/>entitlement, credential"]
    IDP --> VERIFY["Đọc lại trạng thái ở đích"]
    APP --> VERIFY
    VERIFY --> AUDIT["Audit / evidence / alert"]
    VERIFY --> RECON{"Drift còn tồn tại?"}
    RECON -- "Có" --> PLAN
    RECON -- "Không" --> DONE["Đánh dấu action confirmed"]
    LOG --> RECON
~~~

Luồng minh họa tách:

1. **Input event:** dữ kiện nghiệp vụ từ nguồn có thẩm quyền.
2. **Decision:** đánh giá lại trạng thái danh tính và chính sách.
3. **Command:** phát yêu cầu thay đổi tài khoản/quyền.
4. **Confirmation:** kiểm tra hệ thống đích và hoàn tất hay báo lỗi.
5. **Reconciliation:** kiểm tra lại định kỳ khi có khả năng event hoặc phản hồi bị mất.

Event-driven giúp giảm độ trễ JML; **đối soát toàn lượng định kỳ** vẫn cần để phát hiện event bị bỏ sót, tài khoản tạo ngoài luồng hoặc entitlement drift. Không nên giả định hạ tầng message đảm bảo xử lý **exactly once** từ đầu đến cuối khi nhiều hệ thống đích và API cùng tham gia.

## 9. Xử lý sự kiện trùng, mất, đến trễ hoặc sai thứ tự

Một thiết kế lifecycle event tốt phải coi những trường hợp này là bình thường trong hệ thống phân tán.

| Sự cố | Nguy cơ | Biện pháp |
|---|---|---|
| **Event gửi lặp** | Tạo trùng account, gửi nhiều yêu cầu hoặc ghi log sai. | Dedupe theo `(sourceSystem, eventId)`; lệnh idempotent theo action ID. |
| **Event cũ đến sau event mới** | Khôi phục phòng ban hoặc trạng thái cũ. | So sánh version/sequence theo đúng source record; từ chối áp bản lạc hậu. |
| **Event bị mất** | IAM giữ quyền dù HRIS/VMS đã chấm dứt quan hệ. | Snapshot/reconciliation định kỳ, phát hiện version gap, cơ chế replay. |
| **Event từ nguồn không hợp lệ** | Giả mạo thông tin hoặc cấp/thu hồi sai quyền. | Xác thực nguồn, ủy quyền loại event và schema validation. |
| **Event thiếu trường bắt buộc** | Không liên kết được danh tính hoặc quyết định sai. | Đưa vào hàng lỗi có cảnh báo và owner, không âm thầm chấp nhận. |
| **Nguồn không có version** | Không xác định thứ tự cập nhật chính xác. | Thỏa thuận cơ chế thay thế như snapshot sequence hoặc tra cứu trạng thái hiện hành có kiểm chứng. |
| **API đích thành công nhưng phản hồi thất lạc** | Gửi lại thành nhiều hành động ngoài ý muốn. | Idempotency key, kiểm tra trạng thái đích trước/sau retry. |
| **Event có hiệu lực tương lai bị thay đổi** | Thực thi một kế hoạch cũ vào ngày sai. | Schedule có version, hủy/thay kế hoạch và xác minh lại khi đến hạn. |
| **Hai nguồn gửi giá trị xung đột** | Nguồn phụ ghi đè dữ liệu có thẩm quyền. | Ma trận authority theo thuộc tính, cảnh báo và đối soát; không “last write wins” tùy ý. |

### Mẫu xử lý với inbox và outbox

~~~text
onEvent(event):
    verifyProducerSignatureOrAuthenticatedChannel(event)
    validateSchemaAndAuthority(event)

    beginTransaction()
        if inbox.contains(event.sourceSystem, event.eventId):
            commit()
            return ACK_DUPLICATE

        record = findSourceRecord(event.sourceSystem, event.sourceRecordId)
        if event.version < record.acceptedVersion:
            inbox.markStale(event)
            commit()
            return ACK_STALE

        if event.version == record.acceptedVersion:
            resolveReplayOrVersionConflict(event, record)
            # Không tự ghi đè nếu cùng version nhưng payload khác

        proposed = validateLifecycleTransition(record, event)
        saveEventAndUpdateDesiredState(proposed)
        outbox.append(buildIdempotentActions(proposed))
        inbox.markAccepted(event)
    commit()

    # Worker ngoài transaction gửi action, retry và readback riêng.
    dispatchOutboxAndReconcile()
~~~

Đoạn mã là **giả mã mô tả trách nhiệm**, không phải thư viện chạy trực tiếp. Với event có hiệu lực trong tương lai, `saveEventAndUpdateDesiredState` phải lưu lịch cùng version thay vì kích hoạt quyền ngay. Các lệnh outbox nên có action ID ổn định để retry không gây hiệu ứng ngoài ý muốn.

**Transactional outbox** giúp tránh tình trạng database đã ghi trạng thái mới nhưng lệnh gửi connector bị mất. Ngược lại, lệnh gửi thành công rồi worker bị dừng cũng phải có cách đọc lại trạng thái và tránh áp thao tác gây hại nhiều lần.

### Dedupe và ordering không chỉ theo event timestamp

Timestamp có thể bị lệch đồng hồ hoặc event đến muộn. Nếu nguồn có version tăng đơn điệu trên một record, version thường thích hợp hơn thời điểm nhận để xác định thứ tự thay đổi. Không nên giả định version của HRIS và VMS có thể so sánh trực tiếp; chúng thuộc hai namespace khác nhau. Khi hai nguồn đồng quản lý thuộc tính khác nhau, cần ma trận thẩm quyền thay vì chỉ so một số phiên bản toàn cục.

## 10. Lập lịch và thay đổi event có hiệu lực tương lai

Sự kiện JML đặc biệt dễ mắc lỗi vì có thể được **công bố trước nhưng có hiệu lực sau**.

Giả sử:

| Thời điểm | Thông báo | Điều IAM nên làm |
|---|---|---|
| 01/06 09:00 | Nhận lịch nhân viên chuyển Finance → Engineering ngày 15/06 | Lưu kế hoạch, kiểm tra SoD và phê duyệt cần thiết. |
| 10/06 16:00 | HRIS hoãn ngày chuyển sang 01/07 với version mới | Hủy/thay lịch cũ, giữ quyền hiện hành đúng chính sách. |
| 15/06 00:00 | Bộ lập lịch cũ kích hoạt nhầm | Phải bị chặn vì kế hoạch đã bị thay thế. |
| 01/07 00:00 | Đến thời điểm hiệu lực mới | Kiểm tra version, trạng thái mới nhất, rồi áp chênh lệch quyền. |

Để thực hiện an toàn:

1. Lưu **source record + version + effectiveAt + trạng thái lịch**.
2. Event sửa ngày phải có cơ chế xác định kế hoạch bị thay thế.
3. Trước khi chạy lịch, truy vấn trạng thái/phiên bản hiện hành hoặc bằng chứng nguồn đủ mới.
4. Thao tác thu hồi/cấp quyền phải có thứ tự phù hợp với rủi ro và SoD.
5. Mọi kết quả phải được ghi vào audit cùng phiên bản sự kiện gây ra hành động.

### Múi giờ và ranh giới thời gian

Nếu HRIS chỉ cho ngày `2026-09-30`, hệ thống phải biết ngày đó có nghĩa **được truy cập hết ngày 30/09** hay **không còn truy cập từ đầu ngày 30/09**. Chuyển ngày thành một instant không mơ hồ (kèm timezone của quan hệ/cơ sở làm việc và quy tắc DST nếu áp dụng) trước khi lập lịch.

Một mẫu hợp đồng tốt cho thời điểm hết hạn là trường `endExclusiveAt`: khi `now >= endExclusiveAt` thì quan hệ không còn hiệu lực. Giá trị có offset UTC cụ thể giúp tránh chạy sai khi các hệ thống nằm ở nhiều múi giờ.

## 11. Sự kiện JML và IdP, SSO, SCIM, RBAC/ABAC

Lifecycle event là **nguồn kích hoạt quyết định**, không phải bản thân cơ chế truy cập:

| Thành phần | Nhận thông tin từ event như thế nào? | Kiểm soát cần có |
|---|---|---|
| **Identity registry / IGA** | Chuẩn hóa khóa nguồn, lưu trạng thái, quyết định policy và quyền mong muốn. | Correlation, ownership, trạng thái vòng đời, audit. |
| **IdP** | Nhận lệnh tạo/khóa account, cập nhật group, ngắt phiên hoặc yêu cầu MFA. | Không nhận event HRIS `ACTIVE` làm lý do tự gỡ security hold. |
| **SSO** | Tài khoản và claim đã thay đổi ảnh hưởng phiên/đăng nhập liên kết. | Token cũ hoặc local login có thể tồn tại; cần kiểm tra vòng đời phiên. |
| **SCIM / provisioning API** | Nhận lệnh tạo/sửa/vô hiệu hóa user hoặc group tại SaaS. | Retry, readback, trạng thái thực tế, idempotency. |
| **RBAC** | Tính lại role theo nhóm nhiệm vụ và thuộc tính đã xác nhận. | Quy tắc gán role, phê duyệt, thu hồi role cũ và SoD. |
| **ABAC** | Thay đổi thuộc tính có thể làm đổi quyết định truy cập ngay tại API. | Độ mới nguồn, cache/claim, PEP phải thực thi giới hạn tài nguyên. |
| **PAM / cloud IAM** | Thu hồi hoặc thay thời hạn nâng quyền đặc biệt khi event có hiệu lực. | Kiểm tra quyền trực tiếp, session, JIT và audit. |
| **Audit / SIEM** | Nhận event, lệnh, kết quả và sai lệch. | Correlation ID, bằng chứng và bảo vệ dữ liệu nhạy cảm. |

Ví dụ một sự kiện `ORGANIZATIONAL_ASSIGNMENT_CHANGED` đổi `departmentId` từ Finance sang Engineering. RBAC có thể gỡ role `FINANCE_ANALYST`, ABAC có thể chặn truy cập dữ liệu tài chính theo thuộc tính mới, IdP cập nhật claim/group và ứng dụng SaaS nhận lệnh SCIM. Nếu API vẫn giữ role cũ do lỗi, **runtime ABAC và lớp đối soát** phải giúp giảm rủi ro quyền tồn dư.

## 12. Sự kiện nhạy cảm, quyền thu hồi khẩn cấp và tình huống xung đột

### Tình huống A — Nguồn nhân sự vẫn ACTIVE, SOC đã khóa truy cập

SOC phát `SECURITY_HOLD_PLACED` vì nghi ngờ account bị chiếm đoạt. Sau đó HRIS gửi sự kiện cập nhật phòng ban với trạng thái nhân viên `ACTIVE`.

**Cách xử lý:** IAM chấp nhận thay đổi phòng ban thuộc thẩm quyền HRIS nhưng giữ khóa truy cập thuộc thẩm quyền bảo mật. Chỉ `SECURITY_HOLD_RELEASED` hợp lệ từ quy trình SOC mới được gỡ khóa. Event thay đổi nhân sự không tự quyết định rằng thiết bị/tài khoản đã an toàn.

### Tình huống B — Nhà thầu được gia hạn sau khi lịch hết hạn đã tạo

VMS phát `CONTRACT_END_CHANGED` với `endExclusiveAt` ngày 01/10. Sau đó hợp đồng được gia hạn đến 01/11 nhưng event mới tới chậm.

**Cách xử lý:** lệnh thu hồi đã lên lịch phải ghi rõ version hợp đồng. Khi đến hạn, IAM kiểm tra version/trạng thái hiện hành và quyết định theo nguồn có thẩm quyền. Nếu thay đổi vẫn chưa xác minh được, không tự mặc định gia hạn; cần chính sách xử lý bất định dựa trên rủi ro, có cảnh báo và đường xử lý khẩn cấp được phê duyệt.

### Tình huống C — Nhân viên nghỉ việc, đồng thời đang là owner của service account

HRIS phát `EMPLOYMENT_TERMINATED`. Tài khoản người dùng và quyền cá nhân cần thu hồi; catalog dịch vụ vẫn cho thấy robot đồng bộ dữ liệu đang được sử dụng.

**Cách xử lý:** tạo hành động **chuyển giao owner/credential review** cho dịch vụ, xử lý credential gắn với nhân viên theo chính sách. Không tự suy ra `WORKLOAD_RETIRED` từ sự kiện Leaver của cá nhân. Việc xóa robot phụ thuộc nguồn vòng đời dịch vụ và đánh giá vận hành.

### Tình huống D — Event Leaver đã ghi nhận, connector SaaS lỗi

IAM chặn đăng nhập ở IdP nhưng SaaS không trả xác nhận vô hiệu hóa, trong khi user local vẫn hiện `ACTIVE`.

**Cách xử lý:** trạng thái nghiệp vụ đã kết thúc; lệnh thu hồi SaaS phải ở `FAILED` hoặc `RETRYING`, được retry có kiểm soát và đưa vào xử lý rủi ro. Không báo hoàn tất Leaver chỉ vì hàng đợi đã phát lệnh. Cần bằng chứng đọc lại tại SaaS hoặc biện pháp cô lập thay thế được phê duyệt.

## 13. Kết quả thực thi: mô hình theo dõi action và reconciliation

Một lifecycle event có thể sinh nhiều hành động song song hoặc tuần tự. Cần có **mã riêng cho từng action** và trạng thái xác minh:

~~~text
Lifecycle event:
  evt-terminate-1042

Action plan:
  act-001 -> Disable IdP account             CONFIRMED
  act-002 -> Revoke SaaS A group membership  CONFIRMED
  act-003 -> Disable legacy local user       RETRYING
  act-004 -> Revoke cloud admin role         CONFIRMED
  act-005 -> Rotate personally owned API key PENDING

Overall:
  BUSINESS_STATE = TERMINATED
  ACCESS_REVOCATION = INCOMPLETE
~~~

Hành động có thể có vòng đời: `PLANNED` → `DISPATCHED` → `IN_PROGRESS` → `CONFIRMED`, hoặc đi qua `FAILED` / `RETRYING` / `EXCEPTION`. Trạng thái `CONFIRMED` nên đi kèm **bằng chứng đích**: native account ID, trạng thái quyền đọc lại, timestamp, nguồn xác nhận hoặc chứng cứ thao tác thủ công có người chịu trách nhiệm.

### Ghi nhận trạng thái mong muốn và trạng thái thực tế

| Khía cạnh | Ví dụ sau Leaver |
|---|---|
| **Nguồn nghiệp vụ** | HRIS xác nhận kết thúc quan hệ lúc 18:00 ngày 30/09. |
| **Desired state** | IdP và account SaaS không còn quyền; các role cloud đã thu hồi. |
| **Observed state** | IdP disabled; SaaS B vẫn active; role cloud đã gỡ. |
| **Drift** | SaaS B active trái với desired state. |
| **Hành động khắc phục** | Retry, ticket có owner/SLA, chặn kênh bổ sung nếu khả dụng, theo dõi đến khi xác nhận. |

**Kết thúc việc gửi lệnh** và **hoàn tất hành động tại đích** là hai dấu mốc khác nhau. Việc lưu cả hai cho phép báo cáo chính xác thời gian tồn dư quyền.

## 14. Kiểm thử hợp đồng và luồng event

Mỗi event type cần kiểm thử cả **ngữ nghĩa nghiệp vụ** và **xử lý kỹ thuật**:

| Ca kiểm thử | Dữ kiện | Kết quả kỳ vọng |
|---|---|---|
| Joiner có hiệu lực tương lai | HRIS báo bắt đầu ngày 15/06, hiện tại 01/06 | Lên kế hoạch đúng mốc; chưa bật truy cập sớm ngoài chính sách. |
| Mover bình thường | Department Finance → Engineering | Gỡ role cũ, cấp role mới có phê duyệt và đối soát. |
| Mover có SoD | Quyền thanh toán mới xung đột với quyền phê duyệt cũ | Không có khoảng thời gian giữ cả hai quyền trái policy. |
| Event lặp | Hai bản sao cùng `eventId` | Chỉ một bản được ghi nhận là có hiệu lực; không tạo account trùng. |
| Event sai thứ tự | Version 18 đến trước version 17 | Version cũ không ghi đè trạng thái mới. |
| Cùng version, payload khác | Hai event nguồn không nhất quán | Ghi lỗi và chuyển owner xử lý, không tự chọn ngẫu nhiên. |
| Hủy lịch tương lai | Joiner/Mover/Leaver đã lập lịch được thay thế | Tác vụ lịch cũ không còn hiệu lực, bản mới được ghi nhận. |
| Thiếu khóa nguồn | Event không có `source.recordId` | Từ chối hoặc đưa vào hàng lỗi; không tự đoán danh tính. |
| Nhà thầu hết hạn | `now >= endExclusiveAt` | Thu hồi tài khoản và quyền đúng thời điểm. |
| Security hold | SOC khóa, HRIS vẫn ACTIVE | Truy cập tiếp tục bị chặn cho đến khi SOC gỡ khóa hợp lệ. |
| Workload owner nghỉ | HRIS phát Leaver | Kiểm tra/chuyển owner dịch vụ; không tự xóa workload còn hoạt động. |
| Connector trả lỗi | SCIM disable thất bại | Action chưa confirmed; cảnh báo, retry và đối soát. |
| Ghi lệnh thành công, mất phản hồi | API đã đổi nhưng worker bị dừng | Retry an toàn và đọc lại đích; không thao tác gây hại lặp vô hạn. |
| Token còn hạn | Role thu hồi nhưng token cũ vẫn có claim | Hệ thống nhạy cảm không cho phép dựa trên quyền đã hết hiệu lực. |
| Source mất kết nối | Không nhận được feed HRIS | Cảnh báo freshness; không coi mất feed là tất cả nhân viên đã nghỉ. |

**Không chỉ kiểm thử handler** nhận event. Kiểm thử end-to-end phải chứng minh account ở ứng dụng đã thay đổi, API từ chối quyền không còn hợp lệ và lệnh thu hồi có bằng chứng xác nhận. Với ca không thể tự động hóa, cần kiểm tra cả SLA, owner và tính đầy đủ của chứng cứ thủ công.

## 15. Vận hành, đo lường và kiểm toán lifecycle event

Các chỉ số nên tách **luồng event** khỏi **kết quả truy cập**:

| Chỉ số | Cách hiểu |
|---|---|
| **Event delivery latency** | Khoảng từ `publishedAt` đến `receivedAt`. |
| **Event processing latency** | Khoảng từ nhận event đến quyết định và lưu action plan. |
| **Event backlog / dead-letter rate** | Sự kiện đang chờ, không hợp lệ hoặc không xử lý được. |
| **Duplicate/stale event rate** | Tỷ lệ bản sao hoặc version lạc hậu, cho biết chất lượng nguồn/luồng. |
| **Scheduled event accuracy** | Tỷ lệ hành động xảy ra đúng thời điểm có hiệu lực đã được phê duyệt. |
| **Joiner provisioning completion** | Tài khoản và role cần thiết đã được xác minh, không chỉ đã gửi lệnh. |
| **Mover entitlement drift** | Quyền cũ còn lại hoặc quyền mới cấp sai sau thay đổi vai trò. |
| **Leaver deprovision latency** | Thời gian từ thời điểm Leaver hiệu lực đến khi các quyền bắt buộc tại đích được xác minh thu hồi; theo dõi cả trường hợp quá SLA. |
| **Orphan account count** | Account không thể liên kết với identity/service owner hợp lệ. |
| **Action confirmation rate** | Phần trăm hành động provisioning/thu hồi có bằng chứng đích và không còn drift. |

Ví dụ, một Leaver có `effectiveAt=18:00`, IAM nhận lúc `18:01`, gửi lệnh lúc `18:02`, nhưng SaaS chỉ xác nhận đã thu hồi quyền lúc `18:20`. Độ trễ **nhận event** là 1 phút, còn độ trễ **thu hồi thực tế** là 20 phút. Khi đánh giá mức độ an toàn, không được lấy độ trễ gửi lệnh thay cho độ trễ quyền thực tế còn tồn tại.

### Bằng chứng cần lưu

Để kiểm toán một lifecycle event, cần truy ra:

1. Nguồn phát, khóa định danh, event ID, type, version và các thời điểm liên quan.
2. Quy tắc JML/role/policy nào đã được áp dụng và phiên bản của chúng.
3. Account, hệ thống đích và entitlement nào nằm trong phạm vi tác động.
4. Lệnh nào được gửi, có retry/ngoại lệ không và ai chấp thuận ngoại lệ.
5. Trạng thái đọc lại từ đích, thời điểm xác nhận và kết quả đối soát.
6. Người hoặc đội nào sở hữu ticket, cảnh báo hoặc việc thu hồi chưa hoàn tất.

Nhật ký phải hạn chế PII và tránh chứa password, session token hay secret. Khi truyền hoặc lưu event, dùng cơ chế xác thực/ủy quyền nguồn, kiểm soát truy cập, bảo vệ tính toàn vẹn và chính sách lưu giữ phù hợp.

## 16. Quy trình xác định lifecycle event cho một chương trình IAM

Một nhóm triển khai có thể áp dụng quy trình sau:

1. **Liệt kê identity và account scope.** Ghi rõ nhân viên, nhà thầu, đối tác, tài khoản đặc quyền, service account, workload và hệ thống/tenant liên quan.
2. **Xác định nguồn có thẩm quyền.** Với từng loại quan hệ, thống nhất hệ thống và owner được phép phát sinh trạng thái bắt đầu, thay đổi, kết thúc, khóa/khôi phục.
3. **Lập event catalog.** Định nghĩa event name, ý nghĩa, điều kiện phát, payload, version, thời điểm có hiệu lực và trường hợp hủy/sửa.
4. **Vẽ state transition.** Quy định trạng thái hợp lệ, đường chuyển, trường hợp không hợp lệ, event trùng, tuyển lại và quan hệ chồng lấp.
5. **Ánh xạ policy và action plan.** Với mỗi event, chỉ rõ RBAC/ABAC, quyền nào cần cấp/thu hồi, phê duyệt/SoD và yêu cầu đối soát.
6. **Thiết kế hợp đồng tích hợp.** Xác thực nguồn, schema, ordering, idempotency, retry, outbox/inbox, scheduler và reconciliation.
7. **Diễn tập tình huống thực tế.** Joiner tương lai, Mover xung đột, Leaver khẩn cấp, nhà thầu gia hạn, owner dịch vụ nghỉ, connector lỗi.
8. **Vận hành và cải tiến.** Theo dõi SLA, backlog, lỗi version, drift, quyền tồn dư, review owner và kiểm toán định kỳ.

### Mẫu bảng đặc tả event catalog

| Thuộc tính | Ví dụ cho `CONTRACT_TERMINATED` |
|---|---|
| **Business meaning** | Hợp đồng nhà thầu chấm dứt và quyền theo hợp đồng không còn hiệu lực. |
| **Authorized source** | VMS, thuộc owner quản lý hợp đồng. |
| **Identity key** | `(VMS, contractId)` liên kết tới identity nội bộ. |
| **Required payload** | `contractId`, `effectiveAt`, `sourceVersion`, `eventId`, `sponsorId`. |
| **State transition** | `ACTIVE → TERMINATED` cho quan hệ hợp đồng. |
| **Policy impact** | Dừng quyền theo hợp đồng; giữ quyền khác chỉ khi có quan hệ độc lập hợp lệ. |
| **Target scope** | Account, role, session, credential được liên kết với hợp đồng. |
| **Completion proof** | Quyền ở mọi đích cần thu hồi đã được xác minh; lỗi được theo dõi. |
| **Exception handling** | Retry, alert, ticket và biện pháp hạn chế bổ sung theo mức rủi ro. |

## 17. Những sai lầm phổ biến

- **Lấy thời điểm tạo hồ sơ làm thời điểm hiệu lực:** kích hoạt tài khoản trước ngày bắt đầu hoặc thu hồi sai ngày nghỉ việc.
- **Không phân biệt event và command:** coi gửi `DisableAccount` là bằng chứng HRIS đã kết thúc quan hệ hoặc quyền đích đã bị vô hiệu hóa.
- **Không có ID và version:** sự kiện trùng/sai thứ tự tạo account trùng hoặc phục hồi quyền cũ.
- **Dùng “last write wins” với nhiều nguồn:** trạng thái phụ có thể ghi đè dữ liệu của nguồn có thẩm quyền.
- **Không hỗ trợ thay lịch tương lai:** tác vụ Leaver hoặc Mover cũ vẫn chạy dù ngày hiệu lực đã đổi.
- **Định nghĩa mọi thay đổi HRIS là Mover:** gây cấp lại/thu hồi quyền không cần thiết và khó kiểm toán.
- **Chỉ cập nhật IdP:** bỏ qua account local, quyền trực tiếp ở cloud, token và ứng dụng không dùng SCIM.
- **Không xem lại SoD khi Mover:** có thời điểm đồng thời giữ quyền mới và quyền cũ xung đột.
- **Xóa service account vì owner nhân sự nghỉ:** có thể làm dừng workload hợp lệ và không giải quyết đầy đủ vấn đề chuyển owner.
- **Đánh dấu Leaver hoàn tất khi action được gửi:** chưa xác minh quyền ở đích, không đo được quyền tồn dư.
- **Thiếu reconciliation:** event bị mất hoặc quyền cấp ngoài luồng không được phát hiện.
- **Không quản trị schema/version và PII:** thay đổi nguồn làm hỏng handler hoặc log tiết lộ dữ liệu nhạy cảm.

## 18. Bài tập thực hành: thiết kế event catalog cho IAM

Một doanh nghiệp quản lý 500 nhân viên, 60 nhà thầu, ba ứng dụng SaaS, IdP dùng SSO, một hệ thống ERP có account local, cloud production và robot CI/CD. HRIS hỗ trợ event theo từng thay đổi, VMS phát sự kiện hợp đồng có ngày kết thúc, còn service catalog lưu owner của robot.

Trong cùng tháng có các trường hợp:

1. Nhân viên A được tạo hồ sơ ngày 01/06, bắt đầu làm việc ngày 15/06.
2. Nhân viên B được thông báo chuyển Finance → Engineering ngày 20/06, sau đó HRIS đổi sang 25/06.
3. Nhà thầu C kết thúc hợp đồng ngày 30/06 và gia hạn trước hạn nhưng event mới đến IAM chậm.
4. Quản trị viên D bị khóa bảo mật lúc 10:00 trong khi HRIS vẫn báo `ACTIVE`.
5. Nhân viên E nghỉ việc và đang là owner của robot CI/CD vẫn chạy ở production.
6. IdP đã vô hiệu hóa account của E nhưng ERP local còn `ACTIVE` do lỗi kết nối.

**Yêu cầu:**

- Lập event catalog tối thiểu sáu loại event với nguồn có thẩm quyền, khóa nguồn, `effectiveAt`, payload bắt buộc, hành động dự kiến và bằng chứng hoàn thành.
- Vẽ state machine cho quan hệ nhân viên; chỉ ra `securityHold` độc lập với trạng thái lao động.
- Viết JSON minh họa một event Mover có hiệu lực tương lai và một event sửa lịch với source version cao hơn.
- Thiết kế dedupe và ordering: event trùng ID, version thấp hơn, version bằng nhau nhưng payload khác và event đến sai thứ tự.
- Cho biết event nào dẫn tới gỡ role trong RBAC/ABAC, chặn phiên SSO, gửi lệnh SCIM, xử lý tài khoản ERP local và chuyển owner robot.
- Nêu điều kiện kết luận Leaver hoàn tất khi một ứng dụng đích đang lỗi.
- Đề xuất ít nhất năm ca kiểm thử và ba chỉ số đo thời gian xử lý, trễ thu hồi và drift.

### Tiêu chí nghiệm thu

Một thiết kế lifecycle event có thể đưa vào triển khai cần chứng minh:

- Mỗi event có **ý nghĩa nghiệp vụ**, nguồn, owner và điều kiện phát rõ ràng.
- Identity/relationship được liên kết bằng khóa ổn định, có event ID và cơ chế phiên bản.
- Thời điểm nhận, phát sinh và hiệu lực được phân biệt; lịch tương lai có thể thay thế/hủy.
- Handler xử lý an toàn khi event trùng, trễ, sai thứ tự, thiếu dữ liệu hoặc connector lỗi.
- Chính sách JML xác định rõ hành động cấp, sửa, khóa, thu hồi; đặc quyền và workload có quy tắc phù hợp.
- Trạng thái nghiệp vụ, action đang chạy và trạng thái quyền thực tế tại đích được theo dõi riêng.
- Có bằng chứng đối soát, cảnh báo và owner cho mọi quyền còn tồn dư hoặc yêu cầu chưa hoàn tất.
- Audit có thể truy ngược từ event nguồn đến chính sách, lệnh và xác nhận ở hệ thống đích.

**Lifecycle event là cầu nối có thể kiểm chứng giữa thay đổi nghiệp vụ và thay đổi quyền truy cập.** Khi nguồn, ngữ nghĩa, thời điểm hiệu lực, phiên bản, hành động JML và xác nhận tại đích được thiết kế rõ ràng, chương trình IAM có thể phản ứng chính xác với Joiner–Mover–Leaver, giảm quyền tồn dư và giải thích được toàn bộ lịch sử cấp hoặc thu hồi quyền.
