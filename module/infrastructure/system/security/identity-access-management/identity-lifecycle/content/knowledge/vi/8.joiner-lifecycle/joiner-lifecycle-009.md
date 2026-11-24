# Ngày kích hoạt trong Joiner lifecycle

> **Chương: Joiner lifecycle.** Trong quản lý vòng đời danh tính (**Identity and Access Management — IAM**), **ngày kích hoạt** là mốc thời gian mà chính sách cho phép một danh tính hoặc tài khoản bắt đầu có hiệu lực truy cập. Mốc này phải được ràng buộc với dữ liệu nhân sự đáng tin cậy, kết quả xác minh danh tính, trạng thái cấp phát tài khoản và các yêu cầu bảo mật. **Tạo sẵn identity không đồng nghĩa với cho phép đăng nhập ngay.**

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **ngày bắt đầu làm việc**, **ngày tạo identity**, **ngày cấp phát account**, **ngày kích hoạt** và **thời điểm thực sự có quyền truy cập**.
2. Xác định nguồn dữ liệu, múi giờ và điều kiện để chọn thời điểm kích hoạt hợp lệ trong Joiner–Mover–Leaver (JML).
3. Mô tả luồng **pre-provisioning → pending activation → activation → verification** với IdP, SSO, SCIM và RBAC/ABAC.
4. Thiết kế kích hoạt tự động có kiểm tra chính sách, an toàn khi retry, xử lý sự kiện đến sai thứ tự hoặc Leaver xuất hiện trước ngày kích hoạt.
5. Kiểm tra các quyền và phiên thực tế, đối soát lỗi một phần, ghi bằng chứng và ngăn truy cập sớm hoặc quyền tồn dư.

## 1. Ngày kích hoạt là gì?

**Activation date/time** là thời điểm hoặc điều kiện thời gian mà quy trình IAM được phép chuyển một danh tính/tài khoản từ trạng thái chuẩn bị sang trạng thái có thể sử dụng theo chính sách. Trong thực tế, sự kiện kích hoạt có thể bao gồm việc mở đăng nhập ở IdP, mở tài khoản tại ứng dụng, gán nhóm có hiệu lực, cho phép đăng ký authenticator hoặc bật quyền truy cập đến tài nguyên đã được phê duyệt.

Một người mới có thể ký hợp đồng trước ngày bắt đầu làm việc nhiều tuần. Bộ phận IT muốn tạo sẵn email, công cụ cộng tác và cấu hình máy tính để ngày đầu có thể làm việc ngay. Tuy nhiên, hệ thống vẫn phải **ngăn người đó truy cập trước mốc được phép**, trừ các luồng onboarding trước ngày bắt đầu đã được chính sách cho phép rõ ràng.

Ví dụ:

| Mốc | Thời điểm minh họa | Điều diễn ra |
| --- | --- | --- |
| HR xác nhận tuyển dụng | 20/11, 10:00 | Gửi sự kiện Joiner đáng tin cậy. |
| Identity được tạo | 20/11, 10:05 | IAM tạo mã danh tính, lưu thuộc tính và liên kết nguồn. |
| Tài khoản được chuẩn bị | 25/11, 14:00 | IdP và ứng dụng đích tạo account ở trạng thái chờ hoặc bị hạn chế. |
| **Ngày/giờ kích hoạt** | **01/12, 08:00** | Quy trình kiểm tra điều kiện và cho phép truy cập theo chính sách. |
| Kiểm tra hoàn tất | 01/12, 08:03 | Đọc lại trạng thái và quyền tại các hệ thống bắt buộc. |

Các thời điểm trên chỉ là ví dụ. Doanh nghiệp có thể chọn kích hoạt từ đầu ngày, đầu ca, sau khi hoàn tất xác minh hoặc từ một mốc khác. Quyết định phải dựa trên hợp đồng, quy trình nghiệp vụ, rủi ro và chính sách truy cập của tổ chức.

### Những khái niệm dễ nhầm

| Khái niệm | Câu hỏi trả lời | Có tự cho phép truy cập không? |
| --- | --- | --- |
| **Hire / contract start date** | Quan hệ nhân sự/hợp đồng bắt đầu khi nào? | Không tự động; là đầu vào để tính quyền. |
| **Identity creation time** | Bản ghi danh tính IAM được tạo khi nào? | Không. |
| **Account provisioning time** | User được tạo trong IdP/ứng dụng khi nào? | Không nhất thiết; tài khoản có thể bị disable hoặc chưa có entitlement. |
| **Activation effective time** | Chính sách cho phép truy cập bắt đầu từ lúc nào? | Là một điều kiện cần; còn các điều kiện khác. |
| **Authentication enrollment time** | Người dùng đăng ký passkey/MFA khi nào? | Không tự cấp quyền đến tài nguyên nghiệp vụ. |
| **First successful login** | Lần đăng nhập thành công đầu tiên xảy ra khi nào? | Là sự kiện quan sát, có thể muộn hơn ngày kích hoạt. |
| **Entitlement effective time** | Quyền cụ thể có hiệu lực từ khi nào? | Có thể khác mốc kích hoạt tài khoản. |
| **End / deactivation time** | Khi nào phải ngừng quyền truy cập? | Giới hạn trên của khoảng truy cập hợp lệ. |

**Tài khoản tồn tại** và **tài khoản được phép hoạt động** là hai trạng thái khác nhau. **Kích hoạt đúng thời điểm** cũng khác với **quyền thực tế đã đồng bộ thành công**; trạng thái sau cần được xác minh ở ứng dụng đích.

## 2. Nguồn xác định ngày kích hoạt

Ngày kích hoạt thường được tính từ nguồn có thẩm quyền, chẳng hạn HRIS/HCM, hệ thống hợp đồng nhà thầu hoặc quy trình phê duyệt đặc thù. IAM không nên đoán ngày này từ ngày nhận email onboarding, thời điểm người quản lý nhắn tin hay ngày account được tạo.

Các đầu vào quan trọng gồm:

| Trường dữ liệu | Ý nghĩa | Kiểm soát |
| --- | --- | --- |
| `personId` / `sourceId` | Định danh người trong hệ thống nguồn. | Sử dụng cùng namespace/nguồn; tránh liên kết nhầm. |
| `employmentStartAt` | Thời điểm quan hệ lao động có hiệu lực. | Kiểm tra ngày, loại hợp đồng, sự kiện cập nhật. |
| `accessActivationAt` | Thời điểm chính sách cho phép quyền bắt đầu. | Tính theo quy tắc có thẩm quyền; có thể khác ngày làm việc đầu tiên. |
| `employmentEndAt` | Thời điểm quan hệ kết thúc hoặc hết hiệu lực. | Kiểm tra mốc trên; không kích hoạt sau Leaver. |
| `employmentStatus` | Đang chờ, đang hoạt động, hủy tuyển dụng, nghỉ việc... | Đọc trạng thái mới nhất khi kích hoạt. |
| `proofingStatus` | Tình trạng xác minh danh tính. | Đạt mức yêu cầu cho quyền dự định cấp. |
| `approvalStatus` | Phê duyệt quyền/ngoại lệ. | Quyền nhạy cảm cần approval còn hiệu lực. |
| `sourceVersion` / `eventId` | Thứ tự thay đổi và idempotency. | Chống sự kiện cũ ghi đè mốc mới. |
| `timeZone` | Múi giờ dùng để diễn giải thời gian nghiệp vụ. | Dùng múi giờ được nguồn và chính sách xác định. |

**Ngày bắt đầu làm việc không nhất thiết là ngày kích hoạt trực tiếp.** Ví dụ, công ty cho phép thực hiện một bước đăng ký MFA trước ngày làm nhưng chưa cấp quyền xem dữ liệu nội bộ. Khi đó có thể tách **quyền phục vụ onboarding** và **quyền làm việc chính thức**, mỗi loại có điều kiện thời gian riêng.

### Ai chịu trách nhiệm?

- **HR hoặc chủ sở hữu hợp đồng:** cung cấp quan hệ công việc, ngày hiệu lực và trạng thái nguồn.
- **IAM / identity governance:** diễn giải quy tắc, tổ chức lịch kích hoạt, liên kết identity và theo dõi trạng thái.
- **IdP và dịch vụ provisioning:** thực thi thay đổi User, nhóm, phương thức đăng nhập hoặc tài khoản đích theo yêu cầu.
- **Resource owner / approver:** xác nhận các quyền cần phê duyệt riêng, phạm vi và thời hạn.
- **Ứng dụng nghiệp vụ:** kiểm tra quyền tại điểm sử dụng, kể cả khi SSO đã thành công.
- **Audit / monitoring:** đối soát thời gian thực tế, sai lệch và bằng chứng.

## 3. Thời gian phải chính xác: ngày, giờ, múi giờ và hiệu lực

Trường `2026-12-01` chỉ chứa **ngày lịch**, chưa xác định chính xác thời điểm kích hoạt. “Đầu ngày” ở Thành phố Hồ Chí Minh khác với “đầu ngày” ở New York. Tương tự, một người làm ca đêm có thể bắt đầu lúc 22:00 theo giờ địa phương.

Khi triển khai, cần thống nhất:

1. **Đơn vị thời gian:** ngày lịch hay timestamp đầy đủ; nếu là ngày, quy tắc nào chuyển thành giờ cụ thể?
2. **Múi giờ có thẩm quyền:** múi giờ của địa điểm làm việc, tổ chức, hợp đồng hay hệ thống nguồn?
3. **Chuyển đổi khi lưu và thực thi:** lưu timestamp tuyệt đối (ví dụ UTC), đồng thời giữ múi giờ nghiệp vụ để audit và diễn giải.
4. **Đổi ca hoặc địa điểm:** thay đổi múi giờ/giờ làm phải tạo sự kiện cập nhật có phiên bản, không sửa ngầm.
5. **Giờ mùa hè (DST):** một số múi giờ có giờ không tồn tại hoặc lặp lại khi chuyển DST; cần chính sách xác định trường hợp mơ hồ.
6. **Đồng bộ đồng hồ:** scheduler, IdP và hệ thống ghi log cần đồng hồ tin cậy; đo độ trễ và không xem thời gian nhận sự kiện là thời điểm hiệu lực.

Ví dụ một sự kiện có múi giờ rõ ràng:

~~~json
{
  "source": "HRIS",
  "personId": "EMP-2041",
  "accessActivationAt": "2026-12-01T08:00:00+07:00",
  "businessTimeZone": "Asia/Ho_Chi_Minh",
  "sourceVersion": 38
}
~~~

Trong ví dụ, 08:00 tại Việt Nam tương ứng **01:00 UTC**. Dùng timestamp có offset và timezone xác định giúp tránh kích hoạt sớm hoặc muộn do máy chủ chạy ở múi giờ khác.

**Lưu ý kỹ thuật:** Không chỉ chuyển đổi một ngày về 00:00 UTC nếu hợp đồng quy định bắt đầu vào 08:00 địa phương. Với những quốc gia có DST, nên dùng thư viện hỗ trợ múi giờ IANA và quy tắc rõ ràng cho thời điểm bị lặp hoặc không tồn tại.

### Khoảng thời gian truy cập hợp lệ

Một cách biểu diễn phổ biến là khoảng nửa mở:

~~~text
start = accessActivationAt
end   = accessEndAt
isWithinWindow(now) = start <= now AND (end is null OR now < end)
~~~

Cú pháp trên chỉ mang tính minh họa. Điều kiện thời gian **chưa đủ** để cho phép truy cập; còn cần trạng thái danh tính, proofing, phê duyệt, chính sách và quyền tại tài nguyên. Quy tắc `now < end` giúp tránh diễn giải mơ hồ ở đúng giây kết thúc; hệ thống cần quy ước thống nhất với nguồn HR.

## 4. Pre-provisioning và activation là hai bước khác nhau

Một thiết kế Joiner tốt thường chuẩn bị tài khoản trước, nhưng **giới hạn quyền đến mốc hợp lệ**.

~~~mermaid
flowchart TD
    HR["HR phát Joiner<br/>nguồn + ngày hiệu lực"] --> V["Kiểm tra nguồn, proofing<br/>đối sánh identity"]
    V --> I["Tạo identity IAM<br/>PENDING_ACTIVATION"]
    I --> P["Pre-provision IdP/User<br/>và app account theo chính sách"]
    P --> S["Ghi lịch activation<br/>kèm version và điều kiện"]
    S --> T{"Đến thời điểm<br/>kích hoạt?"}
    T -->|Chưa| S
    T -->|Rồi| G{"Revalidate trạng thái HR,<br/>proofing, approval, Leaver?"}
    G -->|Không đạt| B["BLOCKED / SUPERSEDED<br/>ghi lý do và cảnh báo"]
    G -->|Đạt| A["Bật khả năng truy cập<br/>và entitlement cần thiết"]
    A --> R["Readback tại IdP/ứng dụng<br/>vai trò + phiên + trạng thái"]
    R --> Q{"Đúng desired state?"}
    Q -->|Có| O["ACTIVE / VERIFIED<br/>audit"]
    Q -->|Không| F["PARTIAL_FAILURE<br/>retry / reconcile / owner"]
~~~

### Pre-provisioning: chuẩn bị có điều kiện

Trước ngày kích hoạt, IAM có thể tạo bản ghi identity, User ở IdP và các account đích tùy khả năng kỹ thuật. Tuy nhiên, phải xác định **cơ chế thực sự ngăn truy cập**, chẳng hạn trạng thái disabled, nhóm chưa có quyền, chính sách deny hoặc chỉ cho phép một luồng enrollment được giới hạn.

Chỉ đặt nhãn `PENDING_ACTIVATION` trong hệ thống IAM **không đủ** nếu tài khoản đích đã được bật, có mật khẩu sử dụng được hoặc tồn tại quyền cục bộ. Cần đọc lại trạng thái thực tế, không chỉ kiểm tra dòng công việc trong workflow.

### Activation: kiểm tra lại trước khi bật

Đúng mốc đến hạn, workflow cần kiểm tra lại:

- Sự kiện Joiner vẫn hợp lệ, chưa bị hủy; quan hệ công việc/hợp đồng chưa chuyển sang Leaver.
- Identity đã được resolve đúng người; proofing và enrollment đáp ứng yêu cầu.
- Quyền dự kiến còn phù hợp với **vai trò hiện tại**, không dùng snapshot cũ nếu đã có Mover.
- Manager/sponsor/resource owner đã duyệt những quyền cần phê duyệt, chưa hết hạn.
- Không có cảnh báo rủi ro hoặc khóa truy cập còn hiệu lực đòi chặn kích hoạt theo chính sách.
- Chưa quá thời hạn kết thúc và đúng mốc kích hoạt sau khi diễn giải timezone.

Nếu một điều kiện không đạt, cần dừng hoặc giới hạn phần kích hoạt liên quan, gán trạng thái có lý do và chuyển owner xử lý. **Không được dùng retry mù** để cố bật tài khoản khi nguyên nhân là chính sách từ chối.

### Verification: đọc trạng thái sau khi kích hoạt

Trước khi báo “hoàn thành”, đọc lại từng hệ thống bắt buộc:

| Đối tượng | Điều cần xác minh |
| --- | --- |
| **Identity IAM** | Identity đúng nguồn, đúng personId, trạng thái hợp lệ và ngày hiệu lực. |
| **IdP User** | Đã được bật theo chính sách; đăng ký MFA/authenticator đúng yêu cầu. |
| **SSO và phiên** | Đăng nhập theo luồng dự kiến; không tồn tại đường đăng nhập sớm ngoài chính sách. |
| **SCIM / ứng dụng đích** | User và nhóm/role được đồng bộ, không có quyền cục bộ quá mức. |
| **RBAC/ABAC** | Quyền đúng vai trò, tenant, đối tượng và điều kiện thực thi. |
| **Workflow/audit** | Có mốc thời gian, request/correlation ID, người phê duyệt, kết quả từng đích. |

Việc IdP báo thành công không có nghĩa SCIM đã cấp account ở CRM hoặc ứng dụng đã cho phép đúng phạm vi nghiệp vụ. Kết quả xác minh cần tách theo ứng dụng và loại quyền.

## 5. Thiết kế trạng thái và tác vụ kích hoạt

Một mô hình trạng thái khái niệm:

| Trạng thái | Ý nghĩa | Hành động kế tiếp |
| --- | --- | --- |
| `JOINER_RECEIVED` | Nhận yêu cầu từ nguồn có thẩm quyền. | Kiểm tra, proofing, đối sánh. |
| `IDENTITY_CREATED` | Có identityId và liên kết nguồn. | Chuẩn bị account và tính quyền. |
| `PREPROVISIONED` | Các tài khoản bắt buộc đã được chuẩn bị an toàn. | Kiểm tra còn bị hạn chế trước hiệu lực. |
| `PENDING_ACTIVATION` | Có mốc hợp lệ trong tương lai hoặc còn điều kiện chờ. | Đăng ký lịch và theo dõi sự kiện cập nhật. |
| `ACTIVATION_DUE` | Đến mốc kích hoạt. | Kiểm tra lại trạng thái nguồn và chính sách. |
| `ACTIVATING` | Đang thực thi theo từng đích. | Ghi kết quả, readback, xử lý một phần. |
| `ACTIVE_VERIFIED` | Đã đáp ứng các điều kiện bắt buộc, quyền được xác minh. | Duy trì vòng đời Mover/Leaver. |
| `BLOCKED` | Một điều kiện bảo mật/nghiệp vụ chưa đạt. | Chuyển reviewer/owner, chờ sự kiện hợp lệ. |
| `PARTIAL_FAILURE` | Một số đích chưa cập nhật đúng. | Retry có kiểm soát, reconciliation. |
| `SUPERSEDED` | Lịch cũ bị thay thế bởi sự kiện mới hoặc Leaver. | Không bật lại quyền theo lịch cũ. |

Tên trạng thái là **ví dụ thiết kế nội bộ**, không phải trạng thái chuẩn bắt buộc của SCIM hoặc IdP. Một identity có thể `PREPROVISIONED` trong IAM trong khi từng app đang ở các trạng thái khác nhau; do đó nên theo dõi cả **trạng thái tổng** và **trạng thái theo từng hệ thống đích**.

### Logic kích hoạt minh họa

Pseudocode:

~~~text
activateJoiner(job):
    identity = loadIdentity(job.identityId)
    latest = loadAuthoritativeEmployment(identity.sourceKey)

    if job.version != identity.currentActivationVersion:
        return SUPERSEDED

    if latest.status in [CANCELLED, TERMINATED, LEAVER_EFFECTIVE]:
        ensureAccessDisabled(identity)
        return SUPERSEDED

    if now() < identity.activationAt:
        return NOT_DUE

    if identity.endAt != null AND now() >= identity.endAt:
        ensureAccessDisabled(identity)
        return SUPERSEDED

    if not proofingSatisfied(identity):
        return BLOCKED("PROOFING_REQUIRED")

    desired = evaluateCurrentPolicy(
        identity,
        latest,
        validApprovals(identity)
    )
    if not desired.activationAllowed:
        return BLOCKED("POLICY_NOT_SATISFIED")

    results = reconcileTargetsIdempotently(identity, desired)
    verified = readBackRequiredTargets(identity, desired)
    writeAudit(job, latest, desired, results, verified)

    if verified.allMandatoryTargetsPass:
        return ACTIVE_VERIFIED
    return PARTIAL_FAILURE
~~~

Đây là logic minh họa; không phải mã sản xuất hoàn chỉnh. Trong triển khai thực tế, cần bảo vệ race condition bằng khóa đồng thời hoặc cập nhật có điều kiện theo phiên bản, đảm bảo thao tác an toàn khi scheduler chạy nhiều lần và đưa các yêu cầu thu hồi Leaver vào luồng ưu tiên.

### Chống kích hoạt trùng

Tác vụ định kỳ, message queue hoặc webhook có thể thực thi nhiều lần vì timeout. Nên có:

1. **Idempotency key** gắn với identity, loại hành động và phiên bản activation.
2. **Compare-and-set/transaction** để nhiều worker không cùng chuyển trạng thái sai.
3. **Upsert hoặc kiểm tra trước khi tạo** ở IdP/SCIM, tránh sinh account trùng.
4. **Readback sau timeout:** một API có thể đã xử lý thành công dù client chưa nhận response.
5. **Audit theo correlation ID** để một kích hoạt lặp được nhận diện là retry, không phải sự kiện mới.

Ví dụ, nếu bước bật IdP User đã hoàn tất nhưng kết nối tới ứng dụng Git timeout, lần retry phải đọc lại trạng thái Git và chỉ thực hiện phần còn thiếu. Không tự cấp lại một vai trò quyền cao hoặc gửi lại thông tin khởi tạo nhạy cảm.

## 6. Ngày kích hoạt và quyền truy cập thực tế

Trong mô hình IAM, một quyết định truy cập có thể được mô tả:

~~~text
ALLOW access KHI
    identity.status = ACTIVE
    AND now >= accessActivationAt
    AND (accessEndAt IS NULL OR now < accessEndAt)
    AND proofingRequirementSatisfied = true
    AND authenticationRequirementSatisfied = true
    AND RBAC/ABAC policy allows(subject, action, resource, context)
ELSE DENY
~~~

**Không mặc định mọi ứng dụng đều tự hiểu điều kiện `activationAt`.** Nếu ứng dụng chỉ đọc nhóm được đẩy qua SCIM và không tự kiểm tra mốc thời gian, quy trình provisioning cần quản lý lúc bật/gỡ nhóm kèm đối soát. Nếu ứng dụng hỗ trợ policy thời gian tại điểm truy cập, điều kiện có thể được kiểm tra ở đó để giảm rủi ro trễ đồng bộ.

### RBAC và ABAC

- **RBAC** quyết định quyền nền theo vai trò, ví dụ DeveloperReader hoặc SupportAgent; vai trò có thể được chuẩn bị trước nhưng chỉ có hiệu lực theo chính sách.
- **ABAC** xét các thuộc tính như `employmentStatus`, `startAt`, tenant, team và yêu cầu mức xác thực; nếu thuộc tính bị cache quá lâu, ứng dụng có thể đánh giá sai mốc kích hoạt.
- **Least privilege** bảo đảm rằng quyền được bật chỉ phục vụ nhiệm vụ hiện tại, đúng tài nguyên và thời hạn. Không vì nhân viên được kích hoạt mà cấp tự động quyền quản trị.
- **SoD/PAM** vẫn áp dụng cho đặc quyền: kích hoạt identity không thay thế phê duyệt độc lập, JIT hoặc phiên đặc quyền có hạn.

### IdP, SSO và SCIM

| Thành phần | Có thể hỗ trợ gì tại ngày kích hoạt? | Giới hạn |
| --- | --- | --- |
| **IdP** | Bật User, áp điều kiện đăng nhập, MFA và cập nhật nhóm. | Không tự đảm bảo quyền cục bộ tại từng ứng dụng. |
| **SSO (OIDC/SAML)** | Cho phép đăng nhập liên thông sau xác thực hợp lệ. | Không tự tính lịch cấp quyền, thời hạn hợp đồng hoặc gỡ token cũ. |
| **SCIM** | Tạo/cập nhật User/Group, thay đổi trạng thái theo API của đích. | SCIM không phải scheduler và không đảm bảo tự hủy session/token. |
| **RBAC/ABAC** | Kiểm tra chức năng và điều kiện sử dụng tài nguyên. | Phải dùng thuộc tính đáng tin cậy và đủ mới. |
| **IGA/IAM workflow** | Xếp lịch, phê duyệt, theo dõi và đối soát. | Phải xác nhận thao tác đích thực sự áp dụng. |

Đối với SCIM, `active=true` thường biểu thị tài khoản ở trạng thái hoạt động tại service provider, nhưng hiệu quả thực tế tùy sản phẩm và cấu hình. Một ứng dụng có thể còn cơ chế quyền cục bộ hoặc session riêng. **Không kết luận “truy cập đã được mở đúng” chỉ dựa trên một giá trị `active`**.

## 7. Các tình huống khó cần xử lý

### 7.1. Ngày bắt đầu làm việc bị lùi

HR đổi mốc từ 01/12 sang 15/12 sau khi IAM đã pre-provision account. Hệ thống phải cập nhật lịch activation theo **phiên bản mới**, đồng thời bảo đảm không có account hoặc quyền nào đã được mở sớm.

Nếu lịch cũ đang chạy cùng lúc sự kiện cập nhật, activation phải kiểm tra bản ghi mới nhất và dùng cập nhật có điều kiện để không kích hoạt theo phiên bản đã bị thay thế.

### 7.2. Tuyển dụng bị hủy trước ngày đi làm

Sự kiện `CANCELLED` hoặc Leaver có hiệu lực trước activation phải **vô hiệu hóa đường truy cập và hủy lịch cũ**. Những tài khoản đã chuẩn bị cần được đóng hoặc xử lý theo chính sách, tránh tạo orphan account. Không để scheduler mở lại tài khoản vài ngày sau khi tuyển dụng đã bị hủy.

### 7.3. Nhân viên chuyển vị trí trước ngày kích hoạt

Một người được tuyển vào đội A, nhưng gần ngày bắt đầu HR chuyển sang đội B. Quyền chuẩn bị theo đội A có thể sai. Tại activation, tính lại role và phạm vi theo nguồn hiện tại, gỡ quyền đội A không còn phù hợp và chỉ cấp đội B theo phê duyệt mới.

### 7.4. Proofing hoặc MFA chưa hoàn tất

Đến ngày hiệu lực nhưng quy trình xác minh danh tính chưa đạt mức yêu cầu hoặc người dùng chưa đăng ký MFA. Có thể giữ account ở trạng thái hạn chế và cho phép một **enrollment flow** an toàn nếu chính sách hỗ trợ, nhưng không tự cấp quyền nhạy cảm khi điều kiện bảo mật thiếu.

### 7.5. Ứng dụng đích chưa đồng bộ

IdP đã bật User, nhưng Git hoặc CRM chưa tạo account hoặc chưa áp role. IAM phải ghi `PARTIAL_FAILURE` theo từng đích, cảnh báo owner và retry có kiểm soát. Nếu hệ thống thất bại là bắt buộc để người dùng làm việc, chưa nên báo onboarding hoàn thành.

### 7.6. Lịch chạy muộn hoặc hệ thống bị gián đoạn

Nếu scheduler không hoạt động đúng mốc 08:00 mà đến 08:12 mới chạy, cần xem liệu trạng thái nguồn/chính sách **hiện tại** còn cho phép kích hoạt không. Không dùng dữ liệu cũ để kích hoạt bù một cách vô điều kiện. Log phải phân biệt `scheduledAt`, `startedAt`, `completedAt` và `verifiedAt` để đo độ trễ.

### 7.7. Tài khoản đã tồn tại hoặc người được tuyển lại

Account trùng email có thể thuộc người khác hoặc là account của người này từ thời gian làm việc trước. Phải resolve theo ID nguồn và bằng chứng đáng tin, không tự mở lại account và phục hồi quyền cũ. Ngày kích hoạt của lần Joiner mới không làm các entitlement từ hợp đồng cũ trở nên hợp lệ.

### 7.8. Nhân viên làm việc xuyên múi giờ

HR ghi ngày bắt đầu theo Việt Nam, hệ thống điều phối chạy tại UTC và ứng dụng SaaS dùng timezone khác. Luồng phải chuyển mốc nghiệp vụ sang timestamp tuyệt đối và ghi lại cả timezone gốc để kiểm toán. Không so sánh các chuỗi ngày/giờ không có timezone.

### 7.9. Tài khoản dịch vụ và workload

Danh tính máy có thể dùng ngày triển khai hoặc ngày hợp đồng dịch vụ có hiệu lực thay cho ngày vào làm. Trước activation cần xác minh owner, workload thực tế, trust relationship và phạm vi quyền; khi dịch vụ ngừng, thực hiện thu hồi theo vòng đời workload. Không cần áp proofing giấy tờ của con người trực tiếp lên service account.

### 7.10. Quyền onboarding được cấp trước ngày chính thức

Đôi khi người mới cần truy cập cổng ký giấy tờ hoặc đăng ký MFA trước ngày bắt đầu. Nên cấp một **tập quyền onboarding riêng, hẹp và có thời hạn**, không bật mặc định quyền nghiệp vụ hoặc dữ liệu nội bộ. Kiểm tra luồng trước ngày bắt đầu không thể tự nâng lên quyền sản xuất chỉ vì account đã tồn tại.

## 8. Thiết kế kiểm toán và tiêu chí hoàn thành

Một sự kiện kích hoạt đáng tin cậy cần lưu:

| Dữ liệu kiểm toán | Ví dụ | Mục đích |
| --- | --- | --- |
| Identity và khóa nguồn | `ID-8F31`, `HRIS-A:EMP-2041` | Xác định đúng người và namespace. |
| Sự kiện và phiên bản | `JOINER-9201`, version 38 | Chống xử lý trùng và dùng sự kiện lỗi thời. |
| Mốc theo nguồn | `2026-12-01T08:00:00+07:00` | Chứng minh thời điểm được phép. |
| Mốc thực thi | `startedAt`, `completedAt`, `verifiedAt` | Đo độ trễ và truy vết. |
| Kết quả kiểm tra | HR active, proofing pass, approval valid | Giải thích vì sao cho phép kích hoạt. |
| Quyền mong muốn | Role, scope, hạn sử dụng, policy version | So sánh với quyền thực tế. |
| Kết quả từng hệ thống | IdP PASS, Git PASS, CRM PENDING | Nhận diện lỗi một phần. |
| Người và hệ thống chịu trách nhiệm | Workflow actor, owner, approver | Phục vụ điều tra và xử lý ngoại lệ. |
| Correlation ID | `act-2041-v38` | Liên kết log xuyên các thành phần. |

Ví dụ event nội bộ minh họa:

~~~json
{
  "eventType": "IDENTITY_ACTIVATION",
  "identityId": "ID-8F31",
  "sourceKey": "HRIS-A:EMP-2041",
  "sourceVersion": 38,
  "activationAt": "2026-12-01T08:00:00+07:00",
  "executedAt": "2026-12-01T08:00:04+07:00",
  "state": "PARTIAL_FAILURE",
  "policyVersion": "iam-access-v5",
  "targetResults": [
    {"target": "CORPORATE_IDP", "status": "VERIFIED"},
    {"target": "GIT", "status": "VERIFIED"},
    {"target": "CRM", "status": "PENDING_RETRY"}
  ],
  "correlationId": "act-2041-v38"
}
~~~

Đây là mô hình JSON khái niệm, **không phải schema chuẩn của SCIM/OIDC hay một sản phẩm cụ thể**. Trong log thực tế, không lưu mật khẩu, token nguyên vẹn, private key hoặc bằng chứng danh tính nhạy cảm không cần thiết.

### Tiêu chí hoàn thành

Một lần activation chỉ được coi là thành công khi:

1. **Đúng chủ thể:** identity đã gắn với nguồn và hồ sơ được xác minh, không có mapping mơ hồ.
2. **Đúng thời điểm:** thời gian và chính sách hiện tại cho phép kích hoạt; không có Leaver/hủy tuyển dụng có hiệu lực.
3. **Đúng quyền:** role, tenant, tài nguyên và điều kiện được tính theo vị trí hiện tại và phê duyệt hợp lệ.
4. **Đúng trạng thái thực tế:** các đích bắt buộc đã được đọc lại và khớp trạng thái mong muốn.
5. **Không để quyền thừa:** account và nhóm được chuẩn bị không vô tình cấp quyền trước mốc; các quyền cũ không phù hợp đã được loại bỏ.
6. **Có bằng chứng:** có audit, correlation ID, kết quả theo đích, owner và cách xử lý sai lệch.

Trong trường hợp hệ thống có nhiều app, nên xác định **những đích bắt buộc** cho ngày đầu làm việc và những đích không bắt buộc có thể tiếp tục xử lý. Không thay khái niệm “cấp quyền an toàn” bằng việc đạt số lượng task thành công.

### Chỉ số theo dõi

- **Activation lateness:** độ trễ giữa mốc được phép và lúc các đích bắt buộc đã được xác minh.
- **Early access incidents:** số lần phát hiện khả năng truy cập trước mốc chính sách.
- **Partial provisioning rate:** tỷ lệ kích hoạt có ít nhất một đích thất bại hoặc trạng thái sai.
- **Stale schedule attempts:** số tác vụ lịch cũ bị chặn vì Mover/Leaver/cập nhật ngày hiệu lực.
- **Orphan pre-provisioned accounts:** tài khoản đã chuẩn bị nhưng không còn Joiner hợp lệ hoặc không có owner.
- **Time to reconcile:** thời gian xử lý chênh lệch giữa desired state và observed state.

Các ngưỡng vận hành nên do tổ chức xác định theo rủi ro, mức nhạy cảm tài nguyên và thỏa thuận phục vụ; không tồn tại một con số áp dụng cho mọi môi trường.

## 9. Tình huống thực hành

### Tình huống A — Tạo trước, bật sớm

**Bối cảnh:** Nhân viên mới Lan bắt đầu ngày 01/12 lúc 08:00. Ngày 25/11, IT tạo User trong IdP và gắn nhóm `SupportAgent`. SaaS CRM cho phép đăng nhập ngay khi User có nhóm đó.

**Câu hỏi:** Rủi ro nào phát sinh?

**Gợi ý:** Pre-provisioning đang kích hoạt quyền quá sớm. Cần cơ chế disabled/deny hoặc tách nhóm chưa có hiệu lực, giới hạn các quyền enrollment trước ngày bắt đầu, đồng thời đọc lại quyền thực tế tại CRM.

### Tình huống B — HR lùi ngày bắt đầu

**Bối cảnh:** HR đổi ngày bắt đầu của Lan từ 01/12 sang 15/12. Scheduler vẫn giữ job kích hoạt phiên bản cũ.

**Câu hỏi:** Làm sao tránh kích hoạt theo lịch lỗi thời?

**Gợi ý:** Lưu phiên bản nguồn và bản ghi lịch, đánh dấu job cũ `SUPERSEDED`, kiểm tra trạng thái HR mới nhất và so sánh phiên bản ngay trước khi bật quyền. Retry của job cũ phải trở thành no-op an toàn.

### Tình huống C — Lệch timezone

**Bối cảnh:** HR lưu “01/12 08:00” theo giờ Việt Nam nhưng scheduler diễn giải thành 08:00 UTC.

**Câu hỏi:** Sai lệch nào xảy ra và cách sửa?

**Gợi ý:** Kích hoạt muộn bảy giờ so với mong muốn. Cần nguồn định rõ timezone `Asia/Ho_Chi_Minh`, lưu mốc có offset hoặc timestamp UTC đã chuyển đổi và xác minh ở hệ thống đích.

### Tình huống D — Leaver đến trong lúc retry

**Bối cảnh:** Job kích hoạt chưa hoàn tất Git nên retry. Trong thời gian đó HR báo tuyển dụng bị hủy và quyền đã được thu hồi ở IdP.

**Câu hỏi:** Job retry có được tiếp tục mở Git User không?

**Gợi ý:** Không. Phải kiểm tra state/version mới nhất và ưu tiên hủy/thu hồi; đồng thời đối soát các tài khoản được tạo sớm để không còn đường truy cập tồn dư.

### Tình huống E — Ngày kích hoạt đúng nhưng quyền sai

**Bối cảnh:** Nhân viên chuyển từ hỗ trợ sang kế toán một ngày trước activation. IdP bật đúng 08:00 nhưng nhóm `SupportAgent` từ snapshot cũ vẫn được áp dụng.

**Câu hỏi:** Activation có hoàn thành hợp lệ không?

**Gợi ý:** Chưa. Thời gian đúng không đủ; phải tính lại desired entitlement theo Mover và nguồn hiện hành, gỡ nhóm cũ, xin phê duyệt quyền mới, readback tại ứng dụng.

## 10. Câu hỏi tự kiểm tra

**1. Identity đã được tạo và có email, có nghĩa người dùng được đăng nhập trước ngày bắt đầu không?**

Không. Tạo danh tính/tài khoản và cấp quyền truy cập là các bước riêng; cần cơ chế hạn chế thực tế cho đến khi chính sách cho phép.

**2. Vì sao ngày kích hoạt cần mốc có múi giờ, thay vì chỉ có một chuỗi ngày?**

Vì hệ thống có thể chạy ở nhiều timezone, ca làm và quy tắc DST khác nhau. Timestamp có offset và timezone nghiệp vụ giúp thực thi và kiểm toán chính xác.

**3. SCIM User có `active=true` có chứng minh toàn bộ quyền đã khớp với chính sách không?**

Không. Cần đọc lại nhóm, role, quyền cục bộ, phạm vi dữ liệu, phiên và trạng thái các đích liên quan.

**4. Scheduler nhận cùng job kích hoạt hai lần do timeout. Điều gì ngăn tạo account trùng?**

Idempotency key, khóa mapping nguồn, thao tác cập nhật có điều kiện, kiểm tra observed state và readback trước retry.

**5. Nếu HR phát Leaver trước mốc activation nhưng job cũ vẫn đến hạn, phải làm gì?**

Không kích hoạt. Đánh dấu lịch cũ không còn hiệu lực, thu hồi các tài khoản đã chuẩn bị, xác minh đường truy cập và lưu audit.

**6. Nếu tài khoản CRM lỗi sau khi IdP đã bật thành công, nên báo trạng thái gì?**

Theo dõi `PARTIAL_FAILURE` hoặc trạng thái tương đương, retry có kiểm soát, đối soát và chỉ công bố hoàn thành phần bắt buộc khi đã xác minh.

**7. Một nhân viên cần điền hồ sơ onboarding trước ngày làm việc; giải pháp an toàn là gì?**

Chỉ cấp luồng onboarding được phê duyệt, quyền hẹp và có hạn; chưa mở quyền nghiệp vụ hoặc dữ liệu nhạy cảm trước activation chính thức.

## Ghi nhớ

- **Ngày kích hoạt** là mốc cho phép truy cập theo chính sách, có thể khác ngày tạo identity, ngày provision User và ngày đăng nhập đầu tiên.
- **Nguồn HR/hợp đồng**, ngày hiệu lực, timezone, proofing, phê duyệt và trạng thái JML mới nhất phải được kiểm tra trước activation.
- **Pre-provisioning** giúp chuẩn bị tài khoản, nhưng cơ chế hạn chế quyền phải có hiệu lực thực tế tại IdP và ứng dụng; không chỉ dựa vào một nhãn trạng thái.
- **IdP/SSO/SCIM** hỗ trợ xác thực và cấp phát; **RBAC/ABAC** bảo đảm quyền đúng vai trò và phạm vi. Thành công ở một hệ thống không chứng minh mọi đích đã hoàn tất.
- **Idempotency, kiểm tra phiên bản sự kiện, readback, reconciliation và audit** giúp chống kích hoạt sớm, lặp hoặc theo lịch cũ và ngăn quyền truy cập tồn dư.
- Activation kết thúc an toàn khi **đúng người, đúng thời điểm, đúng quyền và đã xác minh trạng thái thực tế**, sẵn sàng cho các thay đổi Mover và thu hồi Leaver sau này.
