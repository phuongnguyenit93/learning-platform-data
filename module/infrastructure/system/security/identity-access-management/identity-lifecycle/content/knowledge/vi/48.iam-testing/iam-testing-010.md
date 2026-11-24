# Kiểm thử khôi phục trong vòng đời danh tính IAM

## 1. Khôi phục IAM phải bảo toàn cả tính sẵn sàng và tính đúng đắn của quyền

**Kiểm thử khôi phục** (recovery testing) xác minh hệ thống Identity and Access Management (IAM) có thể trở về trạng thái hoạt động an toàn sau lỗi hệ thống, mất kết nối, sai cấu hình, mất dữ liệu, lỗi đồng bộ hoặc sự cố danh tính. Với vòng đời **Joiner–Mover–Leaver (JML)**, tiêu chí quan trọng không chỉ là IdP/SSO đăng nhập trở lại được mà còn là **quyền truy cập sau khôi phục vẫn đúng theo trạng thái nhân sự và chính sách hiện hành**.

Trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, IAM kết nối HRIS, Identity Provider (IdP), Single Sign-On (SSO), SCIM, các quyết định RBAC/ABAC, tài khoản dịch vụ và hệ thống kiểm toán. Một bản sao lưu cũ có thể chứa quyền của nhân viên đã nghỉ hoặc vai trò cũ của nhân viên đã chuyển bộ phận. Nếu restore nguyên trạng rồi mở truy cập, hệ thống có thể **hồi sinh entitlement đã thu hồi**. Vì vậy recovery testing phải kiểm tra đồng thời **khả năng phục vụ, tính toàn vẹn dữ liệu và kiểm soát bảo mật**.

Những nhóm tình huống cần phân biệt:

- **Khôi phục dịch vụ:** IdP, cơ sở dữ liệu IAM, connector SCIM hoặc message broker gặp sự cố rồi được phục hồi.
- **Khôi phục trạng thái danh tính:** sửa identity bị khóa nhầm, mapping bị hỏng hoặc provisioning bị gián đoạn.
- **Khôi phục quyền hợp lệ:** cấp lại entitlement bị mất do lỗi, nhưng chỉ sau khi đối chiếu với nguồn chuẩn và phê duyệt.
- **Khôi phục xác thực:** reset MFA, thay credential, phục hồi tài khoản sau sự cố xác minh danh tính.
- **Khôi phục sau thảm họa:** restore backup, chuyển sang vùng dự phòng, chạy lại event và đối soát quyền.
- **Rehire / reactivation:** người từng Leaver trở lại; đây là luồng nghiệp vụ có xác minh và phê duyệt mới, **không phải lý do tự động mở lại quyền cũ**.

## 2. Đặt mục tiêu phục hồi và tiêu chí kiểm thử

Trước khi thử, lấy các chỉ tiêu được duyệt của tổ chức:

| Chỉ tiêu | Ý nghĩa | Phép đo |
|---|---|---|
| RTO (Recovery Time Objective) | Thời gian tối đa mục tiêu để khôi phục dịch vụ | Thời gian từ sự cố đến khi kiểm thử chức năng thiết yếu đạt |
| RPO (Recovery Point Objective) | Mức mất dữ liệu tối đa chấp nhận được theo thời gian | Độ cũ của bản sao/trạng thái có thể phục hồi |
| Revocation SLA | Thời hạn quyền bị thu hồi phải hết hiệu lực | Từ sự kiện hợp lệ đến API thực tế trả DENY |
| Provisioning SLA | Thời hạn cấp/cập nhật quyền hợp lệ | Từ sự kiện đến trạng thái đúng tại ứng dụng |
| Reconciliation window | Khoảng thời gian mục tiêu để xử lý sai lệch hậu phục hồi | Từ phục hồi hệ thống đến khi inventory/policy hội tụ |
| Audit completeness | Mức độ đầy đủ của dấu vết kiểm toán | Kiểm tra event, actor, quyết định và trạng thái thực thi |

**RTO đạt không đồng nghĩa bảo mật đạt.** Ví dụ IdP sẵn sàng sau 15 phút nhưng phục hồi backup trước thời điểm Leaver, khiến tài khoản nghỉ việc đăng nhập được: bài test phải FAIL về an toàn dù service health báo xanh.

Không mặc định các con số SLA/RTO/RPO trong tài liệu: giá trị phải lấy từ chính sách và kiến trúc được phê duyệt. Khi chưa có mục tiêu rõ ràng, ghi một finding về thiếu tiêu chí thay vì tự công bố PASS.

## 3. Kiến trúc khôi phục và các nguồn sự thật

~~~mermaid
flowchart TD
    H[HRIS / nguồn trạng thái nhân sự hiện hành] --> O[IAM Recovery Orchestrator]
    B[Backup IAM / IdP] --> O
    E[Event log / outbox / queue] --> O
    P[Policy RBAC / ABAC hiện hành] --> O
    O --> V[Kiểm tra version, effectiveAt và precedence]
    V --> I[Khôi phục dịch vụ IdP / IAM]
    I --> C[Reconcile SCIM / ứng dụng đích]
    C --> S[Kiểm thử SSO, token và quyền thực tế]
    S --> Q{Đúng chính sách và SLA?}
    Q -->|Có| A[Audit, xác nhận recovery]
    Q -->|Không| F[Chặn quyền rủi ro, cảnh báo, remediation]
~~~

Phân biệt những thành phần:

1. **Source of truth:** nguồn nhân sự/nhà thầu và trạng thái vòng đời mới nhất có thẩm quyền.
2. **Desired state:** danh tính, nhóm, vai trò, thuộc tính, thời hạn và ngoại lệ hợp lệ do policy tính toán.
3. **Restored state:** dữ liệu thực sự thu được từ backup hoặc vùng dự phòng.
4. **Observed state:** quyền có hiệu lực ở IdP, ứng dụng, phiên/tokens, tài khoản cục bộ và service identities.

Recovery an toàn cần đưa observed state về desired state; không được coi restored state là chân lý cuối cùng nếu nó cũ hơn sự kiện nghiệp vụ đã được xác nhận.

## 4. Test oracle cho khôi phục an toàn

Ví dụ ba sự kiện đã xảy ra:

~~~text
v10: JOINER(person-301, SALES)
v11: MOVER(person-301, FINANCE)
v12: LEAVER(person-301, TERMINATED)

Backup chứa trạng thái v10.
Event log hoặc nguồn HRIS hiện hành chứa trạng thái v12.
Sau recovery: person-301 phải TERMINATED; không được có quyền SALES/FINANCE.
~~~

Một oracle minh họa:

~~~text
current = sourceOfTruth.identityState(personId)
desired = policy.evaluate(current, approvedExceptions, effectiveTime)
restored = restore.backupState(personId)
actual = inventory.effectiveAccess(personId, allTargets)

assert restored không được ghi đè current nếu dữ liệu cũ hơn
assert actual.unapprovedGrants == {}
assert actual.requiredGrants == desired.requiredGrants sau SLA
assert terminatedIdentity cannot create new interactive session
assert audit records recovery decisions and reconciliation
~~~

Với hệ thống dùng nhiều nguồn, cần quy định rõ version/sequence có thể so sánh được giữa các sự kiện. Không chỉ dựa vào thứ tự message được phát lại, vì network retry và queue có thể giao sai thứ tự. Khi không thể xác minh tính mới hoặc tính hợp lệ của một quyết định cấp quyền, cơ chế an toàn là cách ly yêu cầu, yêu cầu đối chiếu hoặc tạm chặn quyền nhạy cảm theo chính sách.

## 5. Chuẩn bị fixture và môi trường thử

Thực hành recovery nên chạy ở môi trường tách biệt có backup, dữ liệu giả, IdP/test tenant, SCIM sandbox và API ứng dụng mô phỏng gần thực tế. Tạo bộ danh tính:

| Identity | Trạng thái trước sự cố | Rủi ro cần quan sát sau phục hồi |
|---|---|---|
| `test-join-01` | Joiner đã được duyệt nhưng app chưa đồng bộ | Cấp thiếu quyền hoặc tạo account trùng |
| `test-move-02` | Mover Sales → Finance | Khôi phục quyền Sales cũ |
| `test-leave-03` | Leaver đã bị khóa | Mở lại account từ backup cũ |
| `test-admin-04` | Privileged access hết hạn | Đặc quyền tạm thời bị hồi sinh |
| `test-contractor-05` | Hợp đồng hết hạn | Quyền contractor bị kéo dài |
| `test-service-06` | Bot đã đổi owner/secret | Secret cũ hoặc owner cũ có quyền |
| `test-orphan-07` | Tài khoản cục bộ không có owner | Bị bỏ qua khi đối soát |

Đặt mốc `T0` (snapshot), `T1` (có Mover/Leaver), `T2` (lỗi), `T3` (restore), `T4` (reconcile), `T5` (xác minh truy cập). Ghi rõ mốc thời gian UTC hoặc timezone nhất quán để tránh so sánh nhầm thời điểm hiệu lực.

## 6. Ma trận testcase recovery IAM

| ID | Tình huống | Kỳ vọng | Ưu tiên |
|---|---|---|---|
| R01 | IdP khởi động lại sau sự cố | Đăng nhập hợp lệ hoạt động lại, chính sách không bị giảm | Cao |
| R02 | Restore backup cũ hơn Leaver | Không hồi sinh quyền người đã nghỉ | Rất cao |
| R03 | Restore backup trước Mover | Quyền sau phục hồi theo role mới | Rất cao |
| R04 | Connector SCIM lỗi rồi chạy lại | Reconcile đúng quyền, không tạo trùng | Cao |
| R05 | Queue replay sự kiện trùng/out-of-order | Kết quả cuối theo version hợp lệ mới nhất | Rất cao |
| R06 | Reset MFA cho người chưa xác minh | Không cho chiếm tài khoản | Rất cao |
| R07 | Identity bị khóa nhầm | Phục hồi sau xác minh và phê duyệt phù hợp | Cao |
| R08 | Rehire sau Leaver | Không tự mở quyền lịch sử | Rất cao |
| R09 | Restore nhóm quản trị từ backup | Không kích hoạt lại ngoại lệ đã hết hạn | Rất cao |
| R10 | SSO session/token trước sự cố | Tuân thủ expiry/revocation policy sau khôi phục | Rất cao |
| R11 | Failover sang IdP vùng dự phòng | Không bypass MFA, conditional access và deny policy | Rất cao |
| R12 | Service account owner đã rời tổ chức | Owner mới, key/secret hiện hành vẫn được quản lý | Cao |
| R13 | Backup restore thiếu audit events | Phát hiện khoảng trống kiểm toán và cảnh báo | Cao |
| R14 | Nguồn HRIS chưa kết nối lại | Không tin trạng thái cũ để tự cấp quyền mới | Rất cao |
| R15 | Khôi phục thất bại giữa chừng | Báo partial failure, retry/rollback an toàn | Cao |
| R16 | Tài khoản ứng dụng cục bộ tồn dư | Bị inventory và reconciliation phát hiện | Rất cao |

Mỗi ca cần ghi `caseId, initialState, fault, backupPoint, expected, actual, observedAt, deadline, evidence, outcome, remediation`. Test dương tính (người hợp lệ hoạt động lại) phải đi kèm test âm tính (người đã Leaver không còn truy cập).

## 7. Kiểm thử backup/restore của IdP và dữ liệu IAM

Thiết lập các điểm kiểm thử:

- **Tính toàn vẹn:** backup đọc được, dữ liệu có thể kiểm tra và không bị sửa đổi ngoài ý muốn; mã hóa và quyền truy cập backup phù hợp.
- **Phạm vi dữ liệu:** identity ID, group, role, policy version, cấu hình SCIM, mapping external ID và audit cần thiết được khôi phục hoặc tái dựng có kiểm soát.
- **Tính tương thích:** cấu hình/schema/phiên bản dịch vụ được hỗ trợ; thiếu migration phải được phát hiện.
- **Khóa và bí mật:** cơ chế bảo vệ signing key, encryption key, client secret không làm lộ thông tin khi backup/restore. Rotation và invalidation phải được kiểm tra.
- **Trạng thái khóa:** tài khoản bị khóa trước sự cố vẫn bị chặn sau restore; người dùng không được tự tạo session mới từ cấu hình cũ.
- **Policy:** các quyết định deny, MFA, conditional access, SoD và expiry không bị thay thế bởi cấu hình cũ ngoài ý muốn.

Ví dụ backup lúc 16:00, nhân viên nghỉ lúc 17:00 và restore lúc 18:00. Nếu sau restore hệ thống thấy `ACTIVE` từ backup, bài kiểm thử phải bắt buộc chạy đối chiếu HRIS/event có thẩm quyền trước khi cho phép xác thực. Trường hợp không truy cập được nguồn chuẩn, cần có chế độ hạn chế tương ứng, không được âm thầm cho phép toàn bộ tài khoản từ snapshot cũ.

## 8. Kiểm thử SCIM và reconciliation sau recovery

SCIM/API connector thường có trạng thái bất đồng bộ. Khi lỗi giữa chừng, ứng dụng đích có thể đã cập nhật mà IAM chưa nhận phản hồi. Test cần kiểm tra:

1. Truy vấn lại bằng `externalId` hoặc khóa ổn định, tránh tạo tài khoản trùng.
2. Đọc lại trạng thái User, Group, direct grants, `active`, thuộc tính ABAC.
3. Xử lý `429`, `5xx`, mất mạng và timeout với retry/backoff có giới hạn.
4. Phát lại event idempotent, không gỡ nhầm quyền của identity khác.
5. Xử lý `404` có điều tra mapping, không tự xem mọi Not Found là đã hoàn tất deprovisioning.
6. Khi một ứng dụng lỗi, hiển thị trạng thái `PARTIAL_FAILURE/PENDING` hoặc trạng thái tương đương, cảnh báo và remediation.
7. So sánh cả quyền nội bộ ở ứng dụng và phiên còn sống, vì SCIM user inactive không đảm bảo mọi API token đều vô hiệu.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant I as IAM
    participant A as SCIM App
    participant P as Policy
    I->>A: Reconnect after outage
    I->>H: Get authoritative identity state
    H-->>I: TERMINATED v12
    I->>P: Compute desired access
    P-->>I: DENY / no grants
    I->>A: Read user and groups
    A-->>I: active=true, stale role
    I->>A: Deactivate + remove stale grant
    A-->>I: Success
    I->>A: Readback + test access
    A-->>I: DENY
~~~

## 9. Khôi phục MFA, credential và tài khoản bị khóa nhầm

**Account recovery** cho người dùng hợp lệ khác với restore dữ liệu hệ thống. Việc reset mật khẩu, đổi thiết bị MFA hoặc mở khóa phải có xác minh danh tính phù hợp mức rủi ro; không cho phép người khác chiếm tài khoản qua email/tên dễ đoán.

Thử các trường hợp:

- Người dùng chứng minh được danh tính, được phép phục hồi phương thức MFA theo quy trình đã duyệt.
- Yêu cầu khôi phục từ người chưa xác minh hoặc identity đã terminated bị từ chối.
- Mã khôi phục hết hạn, dùng lại hoặc vượt số lần cho phép không có hiệu lực.
- Recovery không tự nâng role hay bỏ qua chính sách xác thực mạnh với tài nguyên nhạy cảm.
- Reset credential cần vô hiệu hóa phiên cũ theo chính sách sự cố, thông báo và audit phù hợp.
- Nếu một danh tính bị khóa nhầm, chỉ mở khóa sau xác nhận nguồn trạng thái hiện hành; quyền sau mở khóa vẫn theo entitlement được duyệt.

Đối với **rehire**, dùng nguồn HRIS mới và phê duyệt lại thay vì khôi phục mọi nhóm từ bản sao cũ. Trạng thái danh tính vật lý có thể được liên kết với ID trước đây theo policy, nhưng quyền truy cập phải được tái tính từ vai trò và ngày hiệu lực hiện tại.

## 10. Failover, break-glass và khả năng chống fail-open

Trong sự cố IdP hoặc đường mạng, tổ chức có thể dùng vùng dự phòng, tài khoản break-glass hoặc quy trình vận hành khẩn cấp. Mục tiêu kiểm thử là bảo đảm **khôi phục khả năng vận hành mà không bỏ qua các chốt bảo mật ngoài ngoại lệ đã phê duyệt**.

| Trường hợp | Kiểm tra |
|---|---|
| Chuyển sang IdP dự phòng | Chính sách khóa account, MFA và conditional access tương đương hoặc theo thiết kế đã duyệt |
| Thiếu tín hiệu trạng thái nhân sự | Không cấp thêm quyền nhạy cảm chỉ dựa vào cache lỗi thời |
| Không kết nối được PDP/PIP | Áp dụng failure mode đã duyệt, tránh fail-open với tài nguyên nhạy cảm |
| Break-glass access | Có phạm vi, owner, cảnh báo, lý do và audit; kiểm tra thu hồi sau sự cố |
| Khóa ký token chuyển vùng | Resource server chỉ tin issuer/key hợp lệ và cấu hình còn hiệu lực |
| Phục hồi kết nối SCIM | Reconcile cả các thay đổi quyền xảy ra trong lúc outage |

Không thử failover phá hủy trên tenant sản xuất nếu chưa có kế hoạch và phê duyệt vận hành. Test ở sandbox hoặc môi trường diễn tập; với hệ thống quan trọng có thể dùng phương pháp game day có giới hạn ảnh hưởng, rollback và điểm dừng an toàn.

## 11. Tài khoản dịch vụ, secret và phụ thuộc vận hành

Service account và workload identity có vòng đời khác tài khoản con người. Khi hệ thống IAM/secret manager được khôi phục, kiểm thử rằng secret hiện hành vẫn được bảo vệ, key rotation không bị đảo ngược và owner mới vẫn được ghi nhận. Nếu backup giữ một key đã bị hủy sau sự cố, tuyệt đối không mặc nhiên đưa key cũ trở lại trạng thái hợp lệ.

Các ca cần có: bot vẫn chạy với credential mới; credential cũ bị từ chối; nhân viên đã Mover/Leaver không còn quyền đọc vault hoặc thay đổi cấu hình; máy chủ dùng workload federation không nhận token sai audience; tài khoản dịch vụ mồ côi được phát hiện và chỉ định owner khắc phục.

Lưu ý rằng xóa service principal khi người sở hữu nghỉ việc có thể làm gián đoạn các job hợp lệ. Recovery cần tuân theo trách nhiệm ownership và kế hoạch chuyển giao, không đánh đồng service account với user account.

## 12. Ví dụ tự động hóa kiểm thử recovery

Đây là **mã giả Python** mô tả test phục hồi backup cũ hơn một sự kiện Leaver. Các client, fault injector, `eventually` và chính sách được cung cấp bởi test harness:

~~~python
def test_restore_does_not_resurrect_leaver(
    hris, iam, idp, crm, backup, recovery, policy
):
    person_id = "test-leave-03"

    # Backup mô tả trạng thái cũ còn active.
    checkpoint = backup.capture_test_checkpoint()
    hris.publish({
        "eventId": "leave-03-v12",
        "personId": person_id,
        "version": 12,
        "type": "LEAVER",
        "effectiveAt": policy.test_effective_at,
    })
    eventually(
        lambda: idp.is_disabled(person_id),
        timeout_seconds=policy.revoke_sla_seconds,
    )

    recovery.restore_test_checkpoint(checkpoint)
    recovery.reconcile_against_authoritative_source()

    eventually(
        lambda: idp.is_disabled(person_id),
        timeout_seconds=policy.recovery_reconcile_sla_seconds,
    )
    eventually(
        lambda: crm.effective_permissions(person_id) == set(),
        timeout_seconds=policy.recovery_reconcile_sla_seconds,
    )
    assert idp.try_new_sign_in(person_id).denied
    assert crm.authorize(person_id, "customer.read") == "DENY"
    assert iam.audit_contains(event_id="leave-03-v12")
~~~

Trong một hệ thống có cửa sổ giữa restore và reconcile, bài test phải kiểm tra **không có thời điểm cho phép truy cập trái phép trong cửa sổ đó**, không chỉ kiểm trạng thái cuối cùng. Ví dụ có thể cần chặn đăng nhập trong khi xác minh nguồn chuẩn. Test harness phải dùng dữ liệu giả và cách khôi phục được hỗ trợ; không chạy restore trên sản xuất.

## 13. Audit, bảo mật của bản sao lưu và tiêu chí PASS

Hồ sơ recovery test cần có:

- **Trước sự cố:** version dữ liệu, cấu hình policy, identity state, grant, session/credential có kiểm soát.
- **Sự cố:** fault đã tiêm, thời điểm bắt đầu, phạm vi ảnh hưởng, dịch vụ không khả dụng.
- **Phục hồi:** checkpoint, thao tác restore/failover, actor, change record, phiên bản cấu hình.
- **Đối soát:** desired state theo nguồn chuẩn, trạng thái từng IdP/app/connector, quyền thiếu hoặc thừa.
- **Enforcement:** kết quả ALLOW/DENY ở API, token/session cũ, các mốc thời gian và bằng chứng.
- **Kiểm toán:** correlation ID, các bản ghi bị thiếu, alert và công việc khắc phục.

Các log và báo cáo không được chứa password, MFA recovery codes, access token, private key hoặc secret dưới dạng rõ. Tài liệu diễn tập cần xác định ai có quyền truy cập backup, cách mã hóa và thời hạn lưu bằng chứng.

Kết luận **PASS** chỉ khi dịch vụ đạt mục tiêu vận hành đã định, danh tính/entitlement ở các đích đúng chính sách sau đối soát, không có quyền bị thu hồi nào được hồi sinh, các trường hợp nhạy cảm được kiểm soát trong suốt quá trình khôi phục và audit đầy đủ. Nếu quyền trái phép từng được mở dù sau đó đã sửa, testcase bảo mật tương ứng phải FAIL.

## 14. Bài thực hành tổng hợp

Giả lập một tenant IAM có HRIS, IdP, ứng dụng CRM hỗ trợ SCIM, app Finance và một bot deploy. Chuẩn bị snapshot trước khi một nhân viên chuyển Sales → Finance và một nhà thầu nghỉ việc.

1. Tạo backup tại `T0`, sau đó phát Mover và Leaver tại `T1`; xác minh cập nhật thành công trước khi gây lỗi.
2. Mô phỏng IdP/connector outage tại `T2`, restore backup cũ tại `T3`.
3. Bảo đảm giai đoạn chờ đối soát không mở truy cập sai cho người đã Leaver.
4. Replay sự kiện theo thứ tự đảo ngược và có event trùng; xác minh state cuối theo nguồn HRIS mới nhất.
5. Kiểm tra quyền Finance của người Mover, quyền Sales đã gỡ, account Leaver bị chặn, session/token cũ và quyền local trong CRM.
6. Giả lập SCIM timeout sau khi ứng dụng xử lý thành công; test idempotency và readback.
7. Kiểm tra bot deploy vẫn hoạt động dưới owner được phê duyệt và secret cũ không được khôi phục thành hợp lệ.
8. Đo RTO, RPO, thời gian reconciliation và revocation SLA; tổng hợp `caseId, fault, checkpoint, desired, observed, deadline, evidence, outcome, remediation`.

Sau diễn tập, ghi lại từng sai lệch ở lớp **backup, nguồn trạng thái, event processing, provisioning, xác thực, phân quyền hoặc enforcement**. Mục tiêu cuối cùng là hệ thống IAM không chỉ hoạt động trở lại, mà **hoạt động trở lại với đúng danh tính và đúng quyền theo vòng đời hiện hành**, không làm sống lại quyền truy cập tồn dư.
