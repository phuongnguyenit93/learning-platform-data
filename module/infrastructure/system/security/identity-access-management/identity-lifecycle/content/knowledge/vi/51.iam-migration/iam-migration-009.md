# Rollback di trú IAM: quay lui an toàn mà không hồi sinh quyền truy cập

## 1. Rollback di trú IAM là gì?

**Rollback di trú IAM** là tập hợp các thao tác đưa một hệ thống quản lý danh tính trở lại phương án vận hành an toàn khi quá trình chuyển đổi IdP, directory, provisioning connector, chính sách phân quyền hoặc ứng dụng đích gặp sự cố. Rollback không nhất thiết là khôi phục toàn bộ bản sao cũ: với IAM, **khôi phục dữ liệu cũ có thể làm sống lại tài khoản Leaver hoặc quyền Mover đã bị thu hồi**. Vì vậy, cần phân biệt quay lui cấu hình/đường xử lý với đảo ngược các quyết định nghiệp vụ về danh tính.

Trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, vòng đời **Joiner–Mover–Leaver (JML)** được điều phối từ HRIS hoặc nguồn danh tính có thẩm quyền tới IdP, SSO, SCIM, ứng dụng, RBAC/ABAC và tài khoản dịch vụ. Khi di trú, hai thế giới cũ–mới có thể đồng thời tồn tại; một lỗi chuyển luồng đăng nhập, mapping `externalId`, token audience hoặc connector SCIM có thể khiến người hợp lệ mất quyền hoặc người đã nghỉ vẫn có quyền.

**Nguyên tắc trung tâm:** rollback chỉ được coi là thành công khi **khả năng phục vụ được phục hồi và quyền truy cập thực tế vẫn phù hợp chính sách tại thời điểm hiện tại**, có bằng chứng đọc lại từ hệ thống đích. “Đăng nhập đã hoạt động” chưa đủ để kết luận hoàn tất.

## 2. Những gì có thể và không thể rollback

| Thành phần | Có thể quay lui | Không được mặc nhiên quay lui |
|---|---|---|
| Routing/SSO | Chuyển đường đăng nhập về IdP cũ đã được xác nhận | Bật lại tài khoản đã terminated |
| IdP configuration | Chính sách, client config, federation đã được version hóa | Hạ mức MFA hoặc bỏ conditional access ngoài phê duyệt |
| SCIM connector | Tắt connector mới, khôi phục connector cũ hoặc đồng bộ bù | Ghi đè trạng thái account đích bằng snapshot cũ |
| Directory/group mapping | Sửa mapping hoặc phục hồi mapping được kiểm chứng | Gán lại toàn bộ nhóm từ bản sao trước Mover |
| Session/token | Chấm dứt phiên, buộc đăng nhập lại hoặc đổi routing | Tin mọi token ký bởi key cũ mà không xét chính sách |
| Entitlement | Tái cấp những quyền hợp lệ bị mất do di trú | Tái cấp quyền đã bị thu hồi theo JML |
| Service identity | Chuyển lại endpoint, federation config, secret reference an toàn | Khôi phục khóa đã revoke hoặc owner đã Leaver |
| Audit pipeline | Khôi phục exporter, ingest và đối soát log | Xóa dấu vết thất bại hoặc sửa lịch sử quyết định |

Sự thay đổi mang tính **nghiệp vụ** (nhân sự nghỉ việc, thay vai trò, quyền hết hạn) là nguồn sự thật mới hơn, không phải “cấu hình lỗi” cần đảo ngược. Với thành phần đã thực thi thao tác không thể hoàn tác (ví dụ gửi thông báo, thay khóa, xóa tài khoản), cần **compensation** có kiểm soát thay vì gọi rollback như phép đảo ngược hoàn hảo.

## 3. Mô hình trạng thái và nguồn tin cậy

Một di trú IAM an toàn phải quản lý ít nhất bốn loại trạng thái:

1. **Authoritative identity state:** HRIS, nguồn quản lý contractor và các quyết định JML có hiệu lực mới nhất.
2. **Desired access state:** tập entitlement được chính sách RBAC/ABAC và phê duyệt hợp lệ tính ra ở thời điểm hiện hành.
3. **Migration state:** cấu hình IdP/SSO, version mapping, trạng thái connector, checkpoint, đường routing và nguồn ghi chủ động.
4. **Observed effective state:** tài khoản, nhóm, ACL, quyền local, token/session và quyền thực sự được ứng dụng thực thi.

~~~mermaid
flowchart TD
    H[HRIS / authoritative JML] --> P[Policy RBAC / ABAC]
    P --> E[Desired identity and grants]
    C[Migration checkpoint / version] --> R[Rollback controller]
    E --> R
    R --> O[Old IdP / connector]
    R --> N[New IdP / connector]
    O --> A[Applications / PEP]
    N --> A
    A --> V[Readback and authorization checks]
    V --> D{Observed matches desired?}
    D -->|Có| F[Close with audit]
    D -->|Không| X[Containment / reconcile / escalate]
~~~

**Không dùng thời gian ghi file backup làm căn cứ duy nhất** để chọn sự kiện mới nhất. Nên dựa vào định danh nguồn ổn định, version hoặc thứ tự sự kiện được nguồn có thẩm quyền bảo đảm và thời điểm hiệu lực. Nếu các nguồn không thể so sánh thứ tự, phải có quy tắc reconciliation và xử lý xung đột rõ ràng.

## 4. Thiết lập điều kiện kích hoạt rollback

Đội di trú cần thống nhất **go/no-go** và trigger trước thời điểm cutover. Ví dụ:

| Dấu hiệu | Nguồn chứng cứ | Hành động dự kiến |
|---|---|---|
| SSO login thất bại trên nhiều ứng dụng quan trọng | Synthetic sign-in, IdP errors | Tạm dừng rollout, xét chuyển routing về cũ |
| SCIM tạo sai user hoặc cấp nhầm quyền | Correlation ID, target readback | Ngừng writer gây lỗi và containment ngay |
| Leaver vẫn truy cập được sau hạn | Thử API với session/token, reconciliation | Cảnh báo nghiêm trọng, chặn truy cập theo playbook |
| Mover mất quyền thiết yếu kéo dài | Desired/actual diff | Remediation; rollback nếu vượt ngưỡng cutover |
| Token issuer/audience không được ứng dụng chấp nhận | Auth logs, application tests | Khôi phục trust config đã được duyệt |
| Connector phát sinh duplicate identity | Mapping và inventory | Dừng provisioning, điều tra ID trước retry |
| Mất audit/không truy vết quyết định | Audit pipeline health | Chặn giai đoạn di trú tiếp theo theo chính sách |

Các ngưỡng, thời hạn, mức ưu tiên phải lấy từ **migration plan và SLA được phê duyệt**. Một lỗi đơn lẻ có thể khắc phục bằng forward fix an toàn; không cần rollback toàn hệ thống nếu rủi ro đảo ngược lớn hơn. Ngược lại, lỗi truy cập trái phép nghiêm trọng có thể cần **containment ngay lập tức**, không chờ quyết định rollback thông thường.

## 5. Điều kiện tiên quyết và checkpoint

Trước cutover, chuẩn bị:

- **Inventory:** identity ID, tenant, trạng thái HR, group/role, direct grants, ứng dụng, service principal, token/session policy.
- **Mapping có thể đảo:** định danh nguồn, `externalId`, subject/NameID, user ID cũ–mới; giải quyết trường hợp trùng email, đổi tên.
- **Version cấu hình:** client IDs, redirect URI, issuer, SAML metadata, SCIM endpoints, policy version, signing key trust và routing.
- **Bản sao cấu hình an toàn:** backup được bảo vệ, mã hóa và thử phục hồi; không phát tán private key/secret trong tài liệu.
- **Runbook và RACI:** người ra quyết định, người đổi routing, người kiểm tra bảo mật, application owner và communications owner.
- **Observability:** correlation ID, audit, dashboard, synthetic tests, reconciliation, báo động quá SLA.
- **Điều kiện sẵn sàng của hệ cũ:** còn vận hành, có capacity, trust và đường đồng bộ trạng thái mới nhất; không giả định có thể bật lại ngay.

Checkpoint minh họa:

~~~yaml
checkpointId: iam-cutover-cp-2026-12-01
environment: sandbox
sourceOfTruth: HRIS
oldIdp: idp-old
newIdp: idp-new
writerMode: single-writer
mappingVersion: "mappings-v7"
policyVersion: "iam-policy-v12"
capturedAt: "2026-12-01T01:00:00Z"
requireReconciliationBeforeResume: true
~~~

Đây là mẫu lập kế hoạch, không phải API chuẩn. **Single-writer** là nguyên tắc hữu ích trong di trú để tránh hai connector ghi ngược chiều hoặc tranh nhau kích hoạt/vô hiệu cùng một tài khoản.

## 6. Quy trình rollback từng giai đoạn

### Giai đoạn A — Xác nhận sự cố và đóng băng thay đổi gây lỗi

1. Mở incident/change record, đánh dấu thời điểm, phạm vi và owner.
2. Thu thập evidence về tác động AuthN, AuthZ, provisioning, audit và quyền tồn dư.
3. Dừng tăng tỷ lệ traffic sang hệ mới; tạm dừng writer gây lỗi nhưng **không làm mất hoặc bỏ qua sự kiện Leaver khẩn cấp**.
4. Bảo đảm tồn tại đường containment có thẩm quyền đối với tài khoản rủi ro trong lúc chuyển đổi.
5. Lập danh sách sự kiện JML nhận trong cửa sổ di trú và trạng thái xử lý từng target.

### Giai đoạn B — Chuẩn bị đường quay lui

1. Xác minh IdP/connector cũ còn sẵn sàng và có cấu hình/trust đáp ứng chính sách hiện hành.
2. Xác minh identity mapping chính xác theo ID bất biến, kiểm các tài khoản đổi email.
3. Tính desired state từ nguồn HRIS mới nhất và các ngoại lệ được duyệt.
4. Kiểm tra những thay đổi security đã thực thi ở hệ mới: Leaver, revoke token, rotation secret, privileged expiry.
5. Định nghĩa fail-safe khi source of truth tạm thời không sẵn: không tự cấp quyền nhạy cảm từ snapshot cũ.

### Giai đoạn C — Thực hiện chuyển đổi

1. Chỉ một operator được ủy quyền thực thi thay đổi cấu hình/routing theo change record.
2. Chuyển authentication flow về provider cũ theo kế hoạch; kiểm tra client/issuer/audience, session và chứng chỉ.
3. Dừng connector mới hoặc đưa về read-only; chỉ bật connector cũ khi dữ liệu và quyền đang được đối soát an toàn.
4. Reconcile trạng thái identity–entitlement theo HRIS/policy; **không nạp đè snapshot cũ lên quyết định JML mới**.
5. Chạy synthetic login và authorization tests cho đối tượng active, Mover, Leaver, admin và workload identity.

### Giai đoạn D — Xác minh và đóng

1. Đọc lại user/group/role ở IdP và các ứng dụng, gồm quyền cấp trực tiếp.
2. Kiểm SSO login, MFA, conditional access và app token validation.
3. Kiểm quyền có hiệu lực bằng request API ALLOW/DENY, cả phiên/token tạo trước cutover.
4. Kiểm queue/outbox, retry, dead-letter và pending workflows.
5. Ghi audit outcome, residual risks, findings và owner. Chỉ tuyên bố hoàn tất khi tiêu chí an toàn đạt.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant R as Rollback controller
    participant O as Old IdP
    participant N as New IdP
    participant A as Application
    R->>N: Quiesce new provisioning writer
    R->>H: Fetch current JML state/version
    H-->>R: Current identity state
    R->>O: Reconcile to approved desired state
    O-->>R: Readback identity/groups
    R->>R: Switch SSO routing with approved change
    R->>A: Test old/new session and authorization
    A-->>R: ALLOW / DENY evidence
    R->>R: Log completion or escalate finding
~~~

## 7. Xử lý thay đổi JML trong cửa sổ rollback

### Joiner

Nếu Joiner đã được cấp trên IdP mới nhưng chưa có ở hệ cũ, rollback có thể làm người hợp lệ mất quyền. Runbook phải tạo/liên kết identity đúng theo nguồn hiện hành, không tạo tài khoản trùng. Account được chuẩn bị trước ngày bắt đầu không tự động được mở quyền trước `effectiveAt`.

### Mover

Một nhân viên chuyển Sales → Finance trong lúc di trú có thể mang role Sales trong backup của IdP cũ. Sau rollback, tính lại tập quyền theo chính sách hiện hành, thêm quyền Finance đã duyệt, gỡ Sales không còn hợp lệ. Nếu cần giữ quyền bàn giao, phải có ngoại lệ được duyệt và giới hạn thời gian.

### Leaver

Trường hợp nguy hiểm nhất: trước cutover, backup lưu account `ACTIVE`; sau cutover, HRIS phát `LEAVER`. Khi quay về hệ cũ, tuyệt đối không mở lại login hoặc entitlement cũ. Cần thử đăng nhập mới, refresh token, session cũ, role local và API key theo SLA thực tế. Nếu resource server chỉ kiểm JWT offline, token cũ có thể còn hiệu lực đến `exp`; phải có kiểm soát phù hợp để không vượt thời hạn chấp nhận.

Ví dụ sự kiện:

~~~text
v30 JOINER: SALES
v31 MOVER: FINANCE
v32 LEAVER: TERMINATED

Old IdP checkpoint = v30
New IdP processed = v32
Rollback required after connection failure

Expected final = TERMINATED, no interactive access.
Do not restore v30 grants or process stale v31 afterward.
~~~

## 8. SCIM và API connector: replay và idempotency

SCIM provisioning thường là eventual-consistent. Nếu connector mới timeout, server có thể đã tạo hoặc vô hiệu account dù IAM chưa nhận phản hồi. Sau khi quay về connector cũ:

- Đối chiếu user bằng khóa liên kết ổn định `externalId`, không chỉ email.
- GET/readback trạng thái `active`, group membership và quyền ứng dụng; xử lý pagination.
- Trước khi retry Create, kiểm tồn tại để tránh duplicate; trước khi retry Revoke, kiểm quyền còn hiệu lực không.
- Giữ version/sequence của sự kiện và không phát lại stale event tạo grant đã bị gỡ.
- Phân biệt `404` do account đã bị xóa hợp lệ với `404` do mapping sai; không kết luận thành công chỉ từ mã HTTP.
- Dùng backoff có giới hạn cho `429`, `5xx` và timeout; ghi `PARTIAL_FAILURE` khi target chưa hội tụ.

Điều kiện kiểm tra cuối là **observed effective grants đúng với approved desired grants** theo deadline, không chỉ SCIM báo thành công.

## 9. SSO, session và khóa ký trong rollback

Việc chuyển lại IdP cũ có thể thay đổi `issuer`, `audience`, federation metadata, khóa ký, token claims và session cookie. Những lỗi thường gặp:

| Vấn đề | Triệu chứng | Kiểm tra an toàn |
|---|---|---|
| Issuer/audience không khớp | App từ chối token hợp lệ | Đối chiếu trust và client config |
| Client redirect/ACS URL sai | Vòng lặp đăng nhập | Synthetic SSO flow |
| Signing key quá cũ | Token bị từ chối hoặc tin nhầm token cũ | Chỉ trust key còn được phê duyệt |
| Claim role thay đổi | App cấp thiếu/thừa quyền | Test RBAC/ABAC tại resource |
| Phiên cũ tiếp tục sống | Leaver vẫn truy cập dù IdP bị khóa | Kiểm session revocation và enforcement |
| MFA/conditional access khác nhau | Người dùng vào app với mức xác minh thấp | Test policy sau chuyển routing |

Không khôi phục các secret/key đã bị revoke chỉ để làm ứng dụng hoạt động; cần điều chỉnh trust/rotation theo thiết kế và phê duyệt bảo mật. Với token chưa hết hạn ở cả hai phía, phải xác định thời gian chấp nhận đồng thời và cách thu hồi trong quá trình chuyển đổi.

## 10. Tài khoản dịch vụ và hệ thống không tương tác

Machine identity có thể dùng workload federation, chứng chỉ, client credentials hoặc secret từ vault. Quay lui SSO của người dùng không bảo đảm các job CI/CD, API integration và scheduled task hoạt động lại.

Checklist:

1. Liệt kê service principals phụ thuộc IdP hoặc endpoint mới.
2. Kiểm owner còn hợp lệ, nhất là trường hợp owner đã Mover/Leaver.
3. Kiểm audience, certificate, workload trust, scope và secret reference.
4. Không phục hồi secret đã được rotate/revoke sau checkpoint.
5. Thử đường gọi API máy với credential hiện hành, bảo đảm quyền tối thiểu.
6. Kiểm quyền quản trị secret của người cũ đã bị gỡ, nhưng bot hợp lệ vẫn hoạt động.

Nếu phải rotate credential trong rollback, thực hiện qua secret manager, có kế hoạch cập nhật consumer và kiểm tra credential cũ bị từ chối.

## 11. Rollback hay roll-forward?

Không phải mọi lỗi di trú IAM đều nên quay lui. So sánh:

| Yếu tố | Rollback | Roll-forward (sửa hệ mới) |
|---|---|---|
| Hệ cũ còn an toàn và hoạt động | Phù hợp khi đã kiểm chứng | Có thể không cần quay về |
| Mapping/trust ở hệ mới lỗi nhỏ | Có thể gây gián đoạn lớn hơn | Thường cân nhắc sửa trực tiếp |
| Hệ mới cấp quyền sai diện rộng | Containment rồi quay lui có thể cần thiết | Chỉ áp dụng nếu sửa nhanh và có bằng chứng |
| Backup cũ hơn nhiều thay đổi JML | Rủi ro phục hồi quyền cũ | Có thể tốt hơn sửa tiến trên trạng thái mới |
| Credential đã rotate và dữ liệu khó đảo | Cần compensation và kiểm chứng | Thường thuận lợi nếu sửa đúng nguyên nhân |
| Cutover đã hoàn tất nhiều ứng dụng | Có nhiều phụ thuộc phải quay lại | Phải cân nhắc theo phạm vi tác động |

Quyết định nên dựa trên **thời gian phục hồi dự kiến, khả năng hội tụ quyền, tính toàn vẹn nguồn JML, mức độ rủi ro và chứng cứ thử nghiệm**, không chỉ vì rollback là mục tiêu đã viết trong kế hoạch.

## 12. Ma trận kiểm thử rollback

| ID | Kịch bản | Kỳ vọng |
|---|---|---|
| RBK01 | SSO cutover lỗi, route về IdP cũ | Active user đăng nhập đúng chính sách |
| RBK02 | Leaver phát sinh sau checkpoint cũ | Không hồi sinh account/quyền |
| RBK03 | Mover trong cửa sổ di trú | Quyền mới đúng, quyền cũ bị thu hồi |
| RBK04 | Joiner chỉ tồn tại ở IdP mới | Provision đúng, không duplicate |
| RBK05 | SCIM timeout sau thao tác thành công | Readback trước retry, idempotent |
| RBK06 | Hai connector cùng ghi | Chặn xung đột single-writer |
| RBK07 | Event cũ tới sau Leaver | Không khôi phục quyền từ version cũ |
| RBK08 | Role local ở app còn hiệu lực | Phát hiện và thu hồi quyền tồn dư |
| RBK09 | JWT cũ vẫn gọi được API | Phát hiện theo SLA/kiến trúc revoke |
| RBK10 | MFA policy khác nhau giữa IdP | Không giảm assurance trái phép |
| RBK11 | Service account dùng secret đã rotate | Không hồi sinh secret cũ; bot hợp lệ vẫn chạy |
| RBK12 | Hệ HRIS không sẵn trong rollback | Không tự cấp quyền nhạy cảm từ dữ liệu cũ |
| RBK13 | Mất audit một giai đoạn | Phát hiện và mở finding |
| RBK14 | Một ứng dụng không hội tụ | Đánh dấu partial failure, escalation |
| RBK15 | Rollback bị lặp | Không nhân đôi identity hoặc grant |

Với mỗi ca, ghi `caseId`, `checkpointId`, version đầu vào, sự kiện JML, expected grants, actual grants, observedAt, SLA, evidence và outcome.

## 13. Ví dụ kiểm thử tự động sau rollback

Đây là **mã giả Python** để mô tả test tình huống backup cũ hơn Leaver; các client và `eventually` là abstraction của test harness:

~~~python
def test_rollback_preserves_leaver_revocation(
    hris, migration, idp_old, app, policy
):
    person_id = "test-person-901"
    checkpoint = migration.create_test_checkpoint()

    hris.publish({
        "eventId": "leaver-901-v32",
        "version": 32,
        "personId": person_id,
        "type": "LEAVER",
        "effectiveAt": policy.test_effective_at,
    })
    eventually(
        lambda: hris.current_status(person_id) == "TERMINATED",
        timeout_seconds=policy.source_update_sla_seconds,
    )

    migration.rollback_test_checkpoint(checkpoint)
    migration.reconcile_current_identity_state()

    eventually(
        lambda: idp_old.is_disabled(person_id),
        timeout_seconds=policy.rollback_reconcile_sla_seconds,
    )
    eventually(
        lambda: app.effective_permissions(person_id) == set(),
        timeout_seconds=policy.rollback_reconcile_sla_seconds,
    )
    assert idp_old.try_sign_in(person_id).denied
    assert app.authorize(person_id, "customer.read") == "DENY"
~~~

**Lưu ý:** kiểm tra trạng thái cuối chưa đủ nếu có thời điểm rollback tạm mở quyền trái phép. Thêm phép thử truy cập liên tục trong cửa sổ chuyển đổi để chắc chắn không phát sinh khoảng hở; với hệ thống nhạy cảm, cần chặn truy cập khi chưa đối soát xong. Mã giả không được chạy trên production và không thay thế test bảo mật thực tế ở PEP.

## 14. Audit, metrics và quyết định đóng rollback

Những bằng chứng cần giữ:

- Thời điểm nhận sự cố, ai phê duyệt rollback, phạm vi và phương án thực hiện.
- Checkpoint/configuration version, routing trước/sau, danh sách connector đã dừng/bật.
- JML events trong cửa sổ cutover, những phiên bản bị stale và kết quả replay.
- Kết quả IdP sign-in, MFA/SSO, SCIM target readback, direct grants, session/token.
- Sai lệch desired–observed, các remediation, owner, deadline, sự cố còn tồn.
- Kiểm tra bot/service identity và quyền đối với vault/secret.

Chỉ số hữu ích: rollback execution duration, time-to-safe-authentication, reconciliation latency, số tài khoản duplicate, số stale grants, số lỗi connector, tỉ lệ test ALLOW/DENY đạt và số audit gaps. Phân biệt **service restored** với **security verified**; dashboard xanh về uptime không thay cho xác nhận quyền thực tế.

## 15. Runbook rollback mẫu

~~~markdown
# IAM Migration Rollback Record

Change ID / Incident ID:
Migration phase and affected targets:
Decision owner and approver:
Checkpoint / policy / mapping version:
Rollback trigger and evidence:
Authoritative HRIS state/version source:

## Before rollback
- [ ] Containment for risky identities
- [ ] Old IdP and connector security preflight
- [ ] All JML events since checkpoint accounted for
- [ ] No conflicting provisioning writers

## Execution
- [ ] Quiesce failed writer
- [ ] Switch approved routing/config
- [ ] Reconcile active, mover, leaver and privileged grants
- [ ] Verify SSO / MFA / service credentials

## Verification
- [ ] Check active users ALLOW where approved
- [ ] Check Leaver / revoked access DENY
- [ ] Check stale events cannot restore grants
- [ ] Check sessions, local roles, service principals
- [ ] Attach audit, target readback and deviations

## Closure
Remaining findings / owners / deadlines:
Security approval:
Operations approval:
Rollback result: PASS / PARTIAL_FAILURE / FAILED
~~~

## 16. Bài thực hành tổng hợp

Giả lập di trú từ `idp-old` sang `idp-new` với CRM dùng SCIM, Finance dùng OIDC và một bot deploy dùng workload federation:

1. Tạo checkpoint trước cutover, ghi mapping version, policy version và owner.
2. Phát Joiner, Mover và Leaver trong thời gian chạy hệ mới; đánh dấu một admin grant đã hết hạn.
3. Giả lập lỗi SSO issuer và SCIM timeout; thu thập evidence để quyết định rollback hay roll-forward.
4. Dừng writer bị lỗi, bảo đảm Leaver khẩn cấp vẫn được containment.
5. Quay lại routing IdP cũ, đối soát trạng thái HRIS hiện hành trước khi mở truy cập.
6. Thử active user đăng nhập, Mover chỉ có quyền mới, Leaver không đăng nhập/không gọi API, admin grant đã hết hạn không tái xuất hiện.
7. Phát lại một Mover event cũ và một Create event trùng; xác minh idempotency và không hồi sinh quyền.
8. Thử service bot và secret đã rotate; kiểm tra owner đúng.
9. Xuất báo cáo `caseId, decision, checkpoint, desired, observed, evidence, owner, remediation, outcome`.

**Tiêu chí nghiệm thu:** routing/cấu hình được phục hồi theo kế hoạch, không cấp lại quyền đã bị thu hồi, không tạo trùng danh tính, hoạt động hợp lệ được khôi phục và những sai lệch có owner cùng bằng chứng. Điểm cốt lõi là **quay lui hạ tầng IAM nhưng không quay lui thực tế nghiệp vụ của người dùng và quyền truy cập**.
