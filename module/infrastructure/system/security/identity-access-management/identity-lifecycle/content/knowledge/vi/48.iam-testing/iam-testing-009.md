# Kiểm thử access review trong vòng đời danh tính IAM

## 1. Access review là gì?

**Access review** (rà soát quyền truy cập) là quá trình người có trách nhiệm xác nhận rằng tài khoản, nhóm, vai trò và quyền truy cập vẫn cần thiết, phù hợp công việc và được phê duyệt. Trong **Identity and Access Management (IAM)**, access review còn được gọi là access certification hoặc entitlement review. Đây là một kiểm soát quan trọng để phát hiện **quyền truy cập tồn dư**, đặc biệt khi việc cấp và thu hồi tự động chưa hoàn toàn bao phủ mọi ứng dụng.

Trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, access review gắn với mô hình **Joiner–Mover–Leaver (JML)**: Joiner phải nhận quyền đúng phạm vi; Mover cần được rà soát để gỡ quyền của vai trò cũ; Leaver không được tiếp tục có quyền truy cập hoạt động. Quy trình có thể lấy dữ liệu từ HRIS, IAM, IdP, SSO, SCIM, RBAC/ABAC, hệ thống cấp phát ứng dụng và kho kiểm toán.

**Kiểm thử access review** không chỉ xác minh giao diện hiện danh sách quyền và người duyệt nhấn nút. Mục tiêu là chứng minh danh sách đem đi duyệt **đầy đủ, đúng thời điểm và đúng chủ thể**, quyết định duyệt hợp lệ, yêu cầu thu hồi được thực thi đến ứng dụng đích và những sai lệch có bằng chứng xử lý.

## 2. Các loại access review thường gặp

| Loại rà soát | Người xác nhận phù hợp | Đối tượng điển hình | Rủi ro cần kiểm thử |
|---|---|---|---|
| Manager review | Quản lý trực tiếp có thẩm quyền | Quyền nhân viên, contractor | Quản lý cũ duyệt khi nhân sự đã chuyển bộ phận |
| Application owner review | Chủ sở hữu ứng dụng | Role và quyền nội bộ SaaS | Thiếu quyền cấp trực tiếp ngoài IAM |
| Privileged access review | Chủ sở hữu hệ thống/bảo mật | Admin role, quyền đặc biệt, break-glass | Duyệt tự động hoặc bỏ qua ngoại lệ hết hạn |
| Role/entitlement owner review | Người chịu trách nhiệm định nghĩa role | Role RBAC, group, tập quyền | Role kế thừa chứa quyền thừa |
| Service identity review | Owner ứng dụng/máy | Service account, API key, certificate | Tài khoản máy không có owner hoặc credential đã quá hạn |
| Event-driven review | Quản lý/owner sau biến cố | Mover, hợp đồng sắp hết hạn | Quyền cũ không được kiểm tra kịp thời |
| Periodic certification | Người duyệt theo chu kỳ đã duyệt | Tài khoản và entitlement trọng yếu | Bỏ sót danh tính hoặc hoàn thành hình thức |

Chu kỳ (hàng tháng, hàng quý hoặc theo rủi ro), ngưỡng SLA và ai được duyệt là **chính sách riêng của tổ chức**; bài kiểm thử lấy chúng từ baseline hiện hành, không tự mặc định một tần suất chung.

## 3. Kiến trúc dữ liệu và luồng rà soát

~~~mermaid
flowchart TD
    H[HRIS / nguồn trạng thái danh tính] --> I[IAM identity inventory]
    D[IdP / Directory groups] --> C[Entitlement collector]
    S[SCIM / Ứng dụng / ACL] --> C
    I --> R[Đối soát và tạo review snapshot]
    C --> R
    R --> O[Chọn đúng reviewer / approver]
    O --> V[Quyết định KEEP / REVOKE / ESCALATE]
    V --> A{Quyết định hợp lệ?}
    A -->|Không| E[Chặn hoặc yêu cầu duyệt lại]
    A -->|Có| P[Provision / Deprovision]
    P --> B[Readback effective access]
    B --> Q{Khớp quyết định?}
    Q -->|Có| L[Audit và đóng review]
    Q -->|Không| F[Alert / Retry / Remediation]
~~~

Quy trình thường có hai mốc cần phân biệt: **snapshot dùng để người duyệt ra quyết định** và **trạng thái quyền thực tế tại thời điểm thực thi**. Nếu trong lúc review có Mover hoặc Leaver, quyết định giữ quyền từ snapshot cũ không được phép phục hồi quyền đã bị thu hồi. Test cần kiểm tra cơ chế tái xác minh chính sách trước khi áp dụng quyết định.

Các nguồn cần đối chiếu:

1. **HRIS hoặc nguồn nhân sự:** trạng thái đang làm, bộ phận, manager, ngày hợp đồng hết hạn.
2. **IAM policy:** vai trò RBAC, thuộc tính ABAC, ngoại lệ, phân tách nhiệm vụ (SoD).
3. **IdP/Directory:** tài khoản, nhóm trực tiếp, nhóm lồng nhau, trạng thái xác thực.
4. **Ứng dụng:** role cục bộ, quyền chia sẻ trực tiếp, account không đi qua SSO/SCIM.
5. **Workload inventory:** service principal, owner, secret, token và ngày rà soát.
6. **Audit:** ai yêu cầu, ai duyệt, thời gian, căn cứ quyết định và lịch sử sửa đổi.

## 4. Test oracle: thế nào là một access review đạt?

Định nghĩa trước bộ quy tắc độc lập với giao diện cần kiểm thử. Ví dụ một yêu cầu review được đánh giá PASS khi:

- Tập đối tượng thuộc phạm vi chiến dịch được đưa vào snapshot đầy đủ, không lặp và không nhầm người.
- Reviewer có thẩm quyền, không vi phạm chính sách tự phê duyệt hoặc SoD.
- Mỗi quyết định được ghi nhận với chủ thể, entitlement, trạng thái, thời điểm và căn cứ cần thiết.
- Quyết định `REVOKE` dẫn tới gỡ quyền thực tế trong SLA hoặc có trạng thái lỗi rõ ràng; `KEEP` chỉ duy trì quyền còn hợp lệ theo chính sách hiện hành.
- Review quá hạn, chưa có người duyệt, ứng dụng không thu hồi được hoặc quyền không rõ owner phải được cảnh báo/escalate.
- Kết quả có thể đối soát bằng readback tại điểm thực thi, không chỉ bằng trạng thái tác vụ trên portal.

Ví dụ các tập dữ liệu logic:

~~~text
scope = inventory.identitiesAndGrants(campaignPolicy)
snapshot = review.listedIdentityGrantPairs()
missingFromReview = scope - snapshot
unexpectedInReview = snapshot - scope

revoked = review.approvedRevocations()
stillEffective = app.effectiveGrants() ∩ revoked

PASS nếu missingFromReview = {}
     và unexpectedInReview = {}
     và stillEffective = {} sau SLA thu hồi
     và mọi quyết định đều có reviewer hợp lệ.
~~~

Quyền hợp lệ có thể xuất hiện qua nhiều đường cấp khác nhau, do đó so sánh nên dùng cặp `(identity, entitlement, target)` cùng nguồn cấp quyền và thời điểm để tránh gộp nhầm. Đối với quyền chồng lấn, gỡ một role không đủ nếu effective permission vẫn có qua role khác.

## 5. Dữ liệu kiểm thử và trường hợp biên

Sử dụng danh tính và tài nguyên giả trong môi trường tách biệt. Bộ fixture tối thiểu nên gồm:

| Identity | Trạng thái | Quyền ban đầu | Điều cần phát hiện |
|---|---|---|---|
| `test-new-01` | Joiner ACTIVE | Role Sales hợp lệ | Reviewer thấy quyền và căn cứ cấp |
| `test-move-02` | Mover Sales → Finance | Sales và Finance | Quyền Sales không còn hợp lệ |
| `test-leave-03` | TERMINATED | Group CRM còn tồn tại | Quyền truy cập tồn dư |
| `test-contractor-04` | Hợp đồng sắp hết hạn | Role dự án | Quyền hết hạn và reviewer phù hợp |
| `test-admin-05` | ACTIVE | Admin tạm thời | Expiry, phê duyệt và owner |
| `test-service-06` | Machine identity | API integration | Owner/secret rotation và quyền tối thiểu |
| `test-orphan-07` | Không có owner hợp lệ | Direct app grant | Escalation và remediation |

Đối với mỗi entitlement, nên có `grantId`, `sourceSystem`, `target`, `role`, `effectiveAt`, `expiresAt`, `lastUsedAt` (nếu có nguồn đáng tin cậy), `approvedBy` và `policyVersion`. Dấu `lastUsedAt` không chứng minh một quyền chắc chắn không cần thiết: ứng dụng có thể không ghi đủ mọi hoạt động, nên quyết định thu hồi vẫn phải dựa trên chính sách và xác nhận có thẩm quyền.

## 6. Kiểm thử completeness và accuracy của review scope

Một rủi ro lớn là chiến dịch báo “100% reviewed” nhưng đã bỏ sót entitlement vì connector không thu thập đủ dữ liệu. Tạo test đối chiếu inventory gốc với snapshot:

1. Liệt kê user và service principal thuộc phạm vi với ID bất biến.
2. Đọc role, group trực tiếp, nested group, direct grant và quyền cục bộ từ từng ứng dụng.
3. Đối chiếu số lượng và định danh, kiểm tra pagination/filter, tenant, inactive account, dữ liệu lỗi và account không có HRIS mapping.
4. Giả lập một connector không phản hồi hoặc trả dữ liệu không đầy đủ; chiến dịch phải báo thiếu dữ liệu, không coi snapshot thiếu là đầy đủ.
5. Kiểm tra sự kiện thay đổi giữa lúc tạo snapshot: hệ thống phải có mốc dữ liệu, version hoặc cơ chế incremental reconciliation.

Ví dụ: một nhân viên có quyền CRM thông qua IdP group và thêm `crm.export.all` cấp trực tiếp trong CRM. Nếu review chỉ chứa group từ IdP, testcase **phải FAIL về độ đầy đủ**. Một quyền nhạy cảm không được đưa ra rà soát vẫn là lỗ hổng dù mọi hàng đang hiển thị đều được duyệt.

## 7. Kiểm thử phân công reviewer, SoD và ủy quyền

Reviewer cần đủ thông tin để quyết định nhưng không được tùy ý tự duyệt quyền nhạy cảm của bản thân nếu policy cấm. Những tình huống cần thử:

- Mapping manager từ HRIS đúng tại thời điểm chiến dịch; người vừa chuyển bộ phận không bị gửi nhầm về manager cũ.
- Reviewer nghỉ việc, bị khóa, không còn trong nhóm có thẩm quyền hoặc thay đổi vai trò; task được chuyển giao/escalate đúng.
- Reviewer ủy quyền cho người khác: thời hạn, phạm vi và quyền ủy quyền được kiểm chứng.
- Không thể tự chứng nhận quyền của chính mình khi chính sách yêu cầu người độc lập.
- Người dùng không có quyền reviewer không xem hoặc sửa được quyết định của người khác (kiểm thử authorization API).
- Bulk approval, API batch hoặc workflow tự động không được bỏ qua cảnh báo SoD, quyền đặc quyền hay lý do bắt buộc.
- Quyền cao cần approver bổ sung hoặc review hai cấp nếu chính sách quy định.

Khi reviewer quyết định `KEEP`, lý do như “cần cho công việc” có thể chưa đủ nếu thiếu căn cứ vai trò hoặc ngoại lệ. Kiểm thử tính bắt buộc của trường dữ liệu theo policy và kiểm tra khả năng truy vết sau đó.

## 8. Kiểm thử quyết định KEEP, REVOKE, ESCALATE

| Quyết định | Kết quả cần thử | Bẫy thường gặp |
|---|---|---|
| `KEEP` | Quyền chỉ được duy trì nếu vẫn hợp chính sách | Giữ quyền đã hết hạn vì reviewer dùng snapshot cũ |
| `REVOKE` | Tạo hành động thu hồi và xác minh tại ứng dụng | Ticket đóng nhưng quyền vẫn có hiệu lực |
| `ESCALATE` | Chuyển cho owner hoặc cấp phê duyệt đúng | Task bị bỏ quên hoặc quay vòng không có owner |
| Chưa quyết định | Nhắc/escalate theo deadline và xử lý mặc định theo policy | Hệ thống tự đánh dấu approved khi hết hạn |
| Quyết định bị thay đổi | Theo dõi version, actor và lịch sử | Sửa sau khi kết thúc mà không lưu dấu vết |

Đối với `REVOKE`, kiểm tra cả trường hợp ứng dụng trả `200/204` nhưng session cũ hoặc API token vẫn dùng được. Đối với `KEEP`, kiểm tra người đã Leaver không được cấp lại quyền nếu quyết định đến muộn. Trạng thái chiến dịch chỉ nên “completed” theo định nghĩa đã công bố, phân biệt **hoàn tất chứng nhận** với **hoàn tất remediation**.

## 9. Kiểm thử thực thi deprovisioning sau quyết định

Quyết định thu hồi có thể đi qua IAM orchestration, IdP, SCIM và ứng dụng. Kiểm tra:

~~~mermaid
sequenceDiagram
    participant R as Reviewer
    participant I as IAM Review
    participant D as IdP
    participant A as App
    R->>I: REVOKE(user, entitlement)
    I->>D: Remove group if applicable
    D-->>I: Success
    I->>A: SCIM/API remove grant
    A--xI: Timeout
    I->>A: Readback current grants
    A-->>I: Grant still effective
    I->>A: Retry/remediate
    A-->>I: Removed
    I->>A: Authorization test
    A-->>I: DENY
    I-->>R: Remediation verified
~~~

Với role trực tiếp hoặc nhóm lồng nhau, chỉ xóa membership một nơi có thể chưa làm hết quyền. Thử quyền có hiệu lực tại PEP, session SSO và token trong deadline được phê duyệt. Một số JWT vẫn hợp lệ tới hết hạn nếu ứng dụng chỉ kiểm chữ ký offline; testcase phải dựa trên chính sách revoke thực tế.

Giả lập lỗi connector, rate limit, timeout sau khi ứng dụng đã thực thi và retry lặp. Kết quả cần idempotent, có trạng thái `PENDING/FAILED` rõ ràng, cảnh báo khi quá SLA và xác minh sau retry. Không cho quyết định `KEEP` cũ ghi đè lại Leaver hoặc thay đổi quyền mới hơn.

## 10. Ma trận test case access review

| ID | Tình huống | Kỳ vọng | Ưu tiên |
|---|---|---|---|
| AR01 | Tạo chiến dịch từ inventory đầy đủ | Tất cả entitlement trong scope xuất hiện | Rất cao |
| AR02 | Ứng dụng chỉ trả trang đầu | Phát hiện thiếu dữ liệu pagination | Rất cao |
| AR03 | Direct grant không có tại IdP | Vẫn được đưa vào review | Rất cao |
| AR04 | Manager đổi do Mover | Task tới reviewer hợp lệ | Cao |
| AR05 | Reviewer cố tự duyệt quyền nhạy cảm | Bị chặn theo SoD | Rất cao |
| AR06 | Reviewer bị vô hiệu trước khi duyệt | Reassign/escalate | Cao |
| AR07 | Giữ quyền hợp lệ | Quyền tiếp tục theo policy | Cao |
| AR08 | Giữ quyền đã hết hạn | Không phục hồi hoặc kéo dài quyền trái phép | Rất cao |
| AR09 | Thu hồi role thông thường | Không còn quyền thực tế sau SLA | Rất cao |
| AR10 | Thu hồi admin role qua nhóm lồng nhau | Không còn đường effective grant | Rất cao |
| AR11 | SCIM hoặc connector lỗi | Báo partial failure và retry | Cao |
| AR12 | Leaver trong khi review đang mở | Không cấp lại quyền qua quyết định muộn | Rất cao |
| AR13 | Reviewer không quyết định trước deadline | Nhắc/escalate/đóng theo policy | Cao |
| AR14 | Contractor hết hạn | Quyền và account đúng expiration policy | Cao |
| AR15 | Service account không có owner | Phát hiện, chuyển xử lý có kiểm soát | Cao |
| AR16 | Bulk approve | Không vượt validation/phê duyệt bắt buộc | Rất cao |
| AR17 | Chỉnh sửa quyết định đã hoàn tất | Có version/audit hoặc bị chặn | Cao |
| AR18 | Quyền bị gỡ nhưng session vẫn truy cập | Báo quyền tồn dư | Rất cao |

Với mỗi ca, lưu `caseId`, `campaignId`, `identityId`, `entitlementId`, `reviewerId`, `expected`, `actual`, `observedAt`, `deadline`, `evidence` và `outcome`.

## 11. Ví dụ tự động hóa kiểm thử

Mã giả Python dưới đây minh họa kiểm thử quyết định thu hồi. `eventually`, client IAM và client ứng dụng là abstraction của test harness:

~~~python
def test_access_review_revokes_stale_grant(review, iam, crm, policy):
    campaign_id = review.start_test_campaign("quarterly-privileged-review")
    user_id = "test-move-02"
    grant = "crm.customer.export"

    # Quyền ứng dụng phải xuất hiện trong snapshot.
    snapshot = review.get_snapshot(campaign_id)
    assert snapshot.contains(user_id, grant, target="crm")

    reviewer = review.authorized_reviewer(campaign_id, user_id)
    review.decide(
        campaign_id=campaign_id,
        user_id=user_id,
        entitlement=grant,
        decision="REVOKE",
        reviewer_id=reviewer,
        reason="No longer required after Mover",
    )

    eventually(
        lambda: grant not in crm.effective_permissions(user_id),
        timeout_seconds=policy.review_remediation_sla_seconds,
    )
    assert crm.request_as(user_id, "customer.export").denied
    assert iam.audit_has_decision(
        campaign_id=campaign_id, user_id=user_id, decision="REVOKE"
    )
~~~

Đoạn mã giả định test fixture có quyền ban đầu và các trạng thái giả lập. Trong bài test thực, `request_as` phải dùng xác thực và authorization tại ứng dụng đích, không chỉ mock một phương thức kiểm tra. Cần thêm ca kiểm tra reviewer không hợp lệ, snapshot thiếu quyền và event Leaver đến khi chiến dịch còn mở.

## 12. Metrics, audit và tiêu chí hoàn thành

Các chỉ số hữu ích:

| Chỉ số | Cách đo | Lưu ý |
|---|---|---|
| Coverage | Số cặp identity–grant được review / số cặp thuộc phạm vi | Mẫu số phải lấy từ inventory đáng tin cậy |
| Decision completion | Số quyết định hợp lệ / tổng số cần duyệt | Không thay thế remediation completion |
| Revocation completion | Quyền REVOKE đã hết hiệu lực / tổng quyền REVOKE | Xác minh readback |
| Overdue reviews | Số task quá deadline | Phân tách theo mức độ rủi ro |
| Remediation latency | Thời gian từ quyết định tới lúc quyền bị chặn | So với SLA theo entitlement |
| Orphan identities | Account/service principal không có owner hợp lệ | Điều tra trước khi xóa |
| Residual access findings | Quyền chưa được phê duyệt nhưng vẫn hiệu lực | Cần severity và owner xử lý |

Audit trail cần ghi review ID, snapshot version, actor/reviewer, thẩm quyền, quyết định, lý do, thời điểm, request remediation, phản hồi từng target và readback. Tránh lưu mật khẩu, token hoặc secret trong báo cáo.

Một chiến dịch kiểm thử đạt khi chứng minh được **scope đầy đủ, phân công đúng reviewer, quyết định hợp lệ, quyền bị thu hồi thật sự trong SLA và lỗi có hướng xử lý**. Nếu còn quyền tồn dư chưa được xử lý, cần ghi nhận rõ trạng thái thay vì tuyên bố hoàn tất toàn bộ.

## 13. Bài thực hành

Giả sử tổ chức có HRIS, IdP, CRM qua SCIM, hệ thống báo cáo tài chính và một bot triển khai. Hãy tạo một chiến dịch access review giả với nhân viên Sales vừa chuyển sang Finance, một Leaver còn quyền CRM cục bộ, một admin role hết hạn và service account thiếu owner.

1. Thu thập inventory ở cả IdP và ứng dụng, đối chiếu mọi quyền trong scope có xuất hiện trên snapshot.
2. Gán reviewer theo manager và application owner; thử một hành vi tự phê duyệt quyền đặc biệt.
3. Quyết định KEEP với quyền Finance hợp lệ, REVOKE với quyền Sales cũ và ESCALATE với service account thiếu owner.
4. Giả lập SCIM timeout, rồi xác minh trạng thái remediation chưa hoàn tất và retry an toàn.
5. Gửi Leaver trong lúc một quyết định KEEP cũ còn chờ xử lý; xác minh quyền không được khôi phục.
6. Gọi API với session đã tạo trước khi thu hồi để phát hiện quyền tồn dư.
7. Lập bảng kết quả `caseId, campaignId, expected, actual, reviewer, evidence, deadline, observedAt, remediation, status`.

Kết quả phải giúp phân biệt sai lệch ở **inventory, reviewer assignment, policy decision, provisioning hay enforcement**. Access review chỉ có giá trị kiểm soát khi một quyết định thu hồi được theo đến **quyền truy cập thực tế**, qua đó giảm tích lũy quyền trong toàn bộ vòng đời JML.
