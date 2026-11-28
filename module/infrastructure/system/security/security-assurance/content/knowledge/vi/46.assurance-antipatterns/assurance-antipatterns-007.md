# Ngoại lệ không có hạn: anti-pattern làm suy yếu security assurance theo thời gian

**Ngoại lệ bảo mật (security exception)** là quyết định có thẩm quyền cho phép một đối tượng tạm thời không đáp ứng một security requirement hoặc control đã xác định, trong phạm vi và thời gian cụ thể, sau khi đánh giá rủi ro còn lại. Ngoại lệ có thể cần thiết trong thời gian thay đổi kiến trúc, migration ứng dụng legacy, khắc phục sự cố hoặc chờ nhà cung cấp hỗ trợ. Tuy nhiên, ngoại lệ **không chứng minh primary control đã đạt**.

**Ngoại lệ không có hạn** là anti-pattern khi một sai lệch được cho phép mà **không có thời điểm kết thúc hữu hiệu, không có cơ chế tái đánh giá bắt buộc, không có owner chịu trách nhiệm khắc phục hoặc mặc nhiên gia hạn vô hạn**. Một allowlist vĩnh viễn, một đường admin không MFA, một suppression rule không expiry và một ticket gắn nhãn “risk accepted” mãi mãi có thể tạo cùng một vấn đề: khoảng trống kiểm soát được bình thường hóa trong khi threat, dữ liệu, quyền và hệ thống liên tục thay đổi.

Bài học thuộc chương **Anti-pattern assurance** của module **SECURITY_SECURITY_ASSURANCE**, với mục tiêu xây dựng **cách đánh giá có bằng chứng** hệ thống đáp ứng security objectives, từ phân tích rủi ro, yêu cầu và security controls đến testing, audit, remediation, khắc phục findings và continuous assurance. Do đó, trọng tâm là chứng minh **ngoại lệ nào còn hiệu lực, ai có quyền chấp nhận residual risk, điều kiện kiểm soát bù trừ đã được kiểm tra ra sao, khi nào phải thu hồi và trạng thái primary control được báo cáo trung thực thế nào**.

> **Nguyên tắc:** Ngoại lệ là quyết định quản trị rủi ro bị giới hạn theo phạm vi và thời gian; không phải cơ chế chuyển FAIL/INCONCLUSIVE/NOT_TESTED thành PASS. **Sự im lặng không đồng nghĩa tái phê duyệt.**

Các mốc thời gian, chính sách, ID và số liệu dưới đây đều là ví dụ; không có “TTL ngoại lệ 30 ngày” phổ quát và phê duyệt nội bộ không thể tự miễn nghĩa vụ pháp lý hoặc hợp đồng bắt buộc.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Nhận diện anti-pattern ngoại lệ không có hạn cùng các biến thể **không expiry, auto-renew, owner biến mất, event-only deadline, permanent suppression, scope drift**.
2. Phân biệt control failure, exception, risk acceptance, waiver, compensating control, false positive, not applicable, remediation extension và policy revision.
3. Giải thích tại sao ngoại lệ hợp lệ vẫn không phải bằng chứng **control PASS** hoặc tuân thủ một nghĩa vụ không cho phép miễn trừ.
4. Phân tích rủi ro tích lũy theo thời gian do exposure, privilege, data, threat, vendor và compensating controls thay đổi.
5. Viết exception record có objective, condition, control ID, asset scope, owner, approver, residual risk, mitigation evidence, effective time, expiry, review, milestones và test.
6. Thiết kế state machine của exception với PENDING, ACTIVE, REVIEW_REQUIRED, EXPIRED, REVOKED và CLOSED_VERIFIED.
7. Xây cơ chế **time-bound approval cộng event-driven reassessment**, tránh gia hạn ngầm.
8. Quản lý external support access, MFA bypass, logging suppression, vulnerability remediation, encryption, backup/DR và third-party exceptions.
9. Thiết kế expiry automation không gây outage hoặc mất chứng cứ ngoài dự kiến.
10. Chứng minh effectiveness của compensating controls qua tests và source inventory độc lập.
11. Báo cáo exception coverage, expiry, backlog, renewal churn và control debt bằng KPI có mẫu số.
12. Xử lý case studies, bài tập triage, incident-triggered revocation và kiểm toán evidence.

## 2. Ngoại lệ hợp lệ là gì?

### 2.1. Bắt đầu từ một yêu cầu cụ thể

Giả sử baseline yêu cầu **mọi đường đăng nhập quản trị tương tác trong production phải enforce MFA**. Một ứng dụng legacy chưa tích hợp được với IdP hiện hành; đội vận hành xin duy trì một đường local admin để xử lý sự cố trong khi migration.

Một review có cơ sở cần xác định:

- **Security objective:** ngăn truy cập quản trị trái phép.
- **Condition:** đường local admin nào chưa đáp ứng MFA; đã kiểm effective state chưa?
- **Scope:** service, environment, account, principal, network, data classification.
- **Risk:** người có thể tiếp cận, credential exposure và blast radius.
- **Reason:** vì sao chưa thể sửa, tại sao không dùng phương án khác.
- **Compensating controls:** network restriction, PAM/JIT, session recording, monitoring, owner.
- **Evidence:** thử access deny/allow, kiểm actual policies và logs.
- **Decision:** người có thẩm quyền, những điều kiện được phép và không được phép.
- **Time:** effective_from, expires_at, next_review_at.
- **Remediation:** milestones, budget, deadline, test acceptance và owner.
- **Reassessment triggers:** khi đường admin được mở rộng, credential compromise, control drift hoặc vendor release thay đổi.

Nếu được duyệt, **primary MFA control vẫn không đạt cho đường đó**. Exception có thể ACTIVE và compensating controls có thể PASS trong phạm vi riêng. Hai kết luận phải được ghi tách.

### 2.2. Phân biệt các trạng thái hay bị gộp

| Thuật ngữ | Ý nghĩa | Có được ghi primary control PASS? |
|---|---|---|
| **FAIL** | Có bằng chứng assertion không đạt | Không |
| **INCONCLUSIVE** | Chưa đủ bằng chứng để kết luận | Không; cũng không tự xác nhận FAIL |
| **NOT_TESTED** | Thuộc scope nhưng chưa đánh giá | Không |
| **NOT_APPLICABLE** | Requirement không áp dụng và có căn cứ scope | Không; chỉ được loại khỏi tập applicable theo quy tắc |
| **FALSE_POSITIVE** | Phát hiện sai, có chứng cứ bác bỏ | Không phải exception; đánh giá control độc lập |
| **RISK_ACCEPTED** | Chủ thể có thẩm quyền chấp nhận residual risk có điều kiện | Không |
| **EXCEPTION_ACTIVE** | Cho phép tạm sai lệch trong phạm vi/kỳ đã duyệt | Không |
| **COMPENSATING_CONTROL_PASS** | Kiểm soát thay thế đã test đạt theo assertion riêng | Không tự biến primary control thành PASS |
| **FIX_IMPLEMENTED** | Đã thay code/config nhưng chưa retest | Chưa |
| **CLOSED_VERIFIED** | Requirement được retest đạt và closure theo policy | PASS trong scope/kỳ đã kiểm nếu assertion đủ |
| **BASELINE_CHANGED** | Requirement được sửa qua governance có hiệu lực | Đánh giá lại với phiên bản mới, không sửa lịch sử |

**Approved** chỉ nói về thẩm quyền quản trị quyết định, không tự chứng minh kỹ thuật đang an toàn.

### 2.3. Ngoại lệ không phải lối tắt thay policy

Một legacy service có exception liên tục qua nhiều năm có thể phản ánh:

1. Kiến trúc đang cần thay thế nhưng chưa có nguồn lực.
2. Requirement không còn phản ánh threat model hoặc phương thức kiểm soát phù hợp.
3. Thiếu cơ chế kiểm thử một compensating control tương đương.
4. Sai lệch đã được chấp nhận như “thói quen” mà không ai quyết định lại.

Nếu requirement cần thay, phải có **policy/baseline revision** độc lập: phân tích mục tiêu, risk, applicability, controls thay thế, approval, effective date, monitoring và evidence. Không được **hạ baseline chỉ để làm KPI compliance xanh**. Nếu nghĩa vụ hợp đồng/pháp luật không cho phép miễn trừ, không thể sửa policy nội bộ để tuyên bố đã tuân thủ.

## 3. Mười biểu hiện của anti-pattern

### 3.1. Không có expiry từ đầu

Một firewall rule mở cho vendor support có mô tả “temporary” nhưng không có ngày kết thúc, rule owner hoặc control test. Người tạo rule nghỉ việc; connection vẫn mở.

### 3.2. Gia hạn tự động không cần quyết định mới

Workflow tự thay thời gian hết hạn mỗi tháng nếu không ai bấm Reject. **Không phản hồi không phải reapproval**; review cũ không chứng minh current exposure, threat và control vẫn tương đương.

### 3.3. “Cho đến khi migration hoàn thành”

Dự án migration có thể không có budget, deadline, milestone hoặc người chịu trách nhiệm. Event-only expiry không giới hạn khoảng phơi nhiễm. Cần **cả event trigger và mốc lịch tối đa**, cộng escalation nếu trễ.

### 3.4. Owner rời tổ chức

Record giữ email của một người không còn thẩm quyền. Không ai đánh giá risk, tình trạng hiệu lực của mitigation hay reapproval. Owner lifecycle phải được giám sát như một control.

### 3.5. Permanent logging/detection suppression

SOC tắt một cảnh báo nhiều false positives cho toàn production; không có negative tests, owner hoặc expiry. Alert volume giảm nhưng **blind spot có thể tăng**.

### 3.6. Approval được copy sang asset mới

Ngoại lệ cho test server được copy vào production hoặc một wildcard thêm nhiều service mới. Scope mới có dữ liệu, quyền, exposure và dependencies khác. Approval cũ không tự bao phủ.

### 3.7. Exception được đếm là compliant

Dashboard cộng những ngoại lệ ACTIVE vào PASS numerator, che những control FAIL. Có thể báo riêng **risk disposition coverage**, nhưng không sửa metric về **control effectiveness**.

### 3.8. GRC expired, runtime vẫn mở

Decision record ghi EXPIRED nhưng IAM role, local bypass hoặc allowlist tiếp tục tồn tại. **Trạng thái phê duyệt** và **trạng thái thực thi** phải được đối soát riêng.

### 3.9. Lùi ticket deadline như gia hạn exception

Team đổi hạn khắc phục từ tháng này sang tháng khác, không cập nhật risk, evidence, approver. Scheduling khó khăn là **execution constraint**, không phải bằng chứng risk giảm.

### 3.10. Primary control đã sửa nhưng bypass chưa bị thu hồi

Service đã enforce MFA, nhưng local admin exception vẫn được phép dùng. Verified closure phải gồm cả retest primary control và kiểm **bypass/permission/suppression đã được loại**.

## 4. Vì sao rủi ro của ngoại lệ tăng theo thời gian?

### 4.1. Risk context không đứng yên

Một hệ thống trước đây chỉ phục vụ sandbox có thể chuyển production, thêm dữ liệu cá nhân, mở Internet API hoặc phụ thuộc vào service quan trọng. Một vendor account ban đầu chỉ đọc một bảng có thể được thêm quyền export hoặc KMS access. Ngoại lệ cũ **không còn mô tả thực tế**.

### 4.2. Attack surface và threats thay đổi

- Có exploit/public advisories mới.
- Credential bị lộ hoặc có compromise indicators.
- Network/IAM/SSO architecture đổi.
- Khả năng lateral movement mở rộng.
- Policy bù trừ bị drift hoặc bị vô hiệu.
- Logging parser/suppression làm mất detection.
- Key/backup dependencies không còn phù hợp.
- Requirements/contract commitments đổi.

Một quyết định có căn cứ ở ngày đầu có thể không còn phù hợp sau một major change, **ngay cả khi expires_at còn ở tương lai**.

### 4.3. Control debt và normalisation of deviance

Một vòng lặp thường gặp:

~~~mermaid
flowchart TD
    F["Finding: control không đạt"] --> E["Ngoại lệ được cho phép tạm"]
    E --> Q{"Có timebound, owner, test, plan?"}
    Q -- "Không" --> N["Ngoại lệ vô thời hạn"]
    N --> S["Scope / threat / người chịu trách nhiệm thay đổi"]
    S --> G["Không còn review hoặc kiểm bù trừ"]
    G --> P["Dashboard đẹp giả, blind spot tăng"]
    P --> X["Incident / audit finding / risk tích lũy"]
    X --> T["Triage, containment, CAPA"]
    T --> Q
    Q -- "Có" --> M["Monitor và review theo kỳ/sự kiện"]
    M --> D{"Primary control đã test PASS?"}
    D -- "Có" --> C["Thu hồi bypass và verified closure"]
    D -- "Chưa" --> R["Reassess risk, approve lại có hạn hoặc xử lý"]
    R --> M
~~~

Sơ đồ mô tả rủi ro quản trị; không khẳng định mọi ngoại lệ dài hạn chắc chắn dẫn đến incident. Nguy cơ cốt lõi là **không biết tình trạng có còn chấp nhận được tại thời điểm hiện tại**.

### 4.4. Evidence trở nên stale

Nếu exception cũ dựa vào network isolation test một năm trước nhưng route, policy hoặc cloud account đã đổi, bằng chứng cũ chỉ chứng minh **tại thời điểm test**, không tự chứng minh tình trạng hôm nay. Một audit sẽ cần biết source, scope, timestamp, condition và các changes kể từ đó.

## 5. Phân tích nguyên nhân gốc

| Nguyên nhân | Tác động | Corrective action |
|---|---|---|
| Không có exception policy | Ai cũng hiểu “accepted” là miễn lâu dài | Taxonomy, approval limits, lifecycle, expiry policy |
| Không có risk owner | Không ai chịu trách nhiệm residual risk | Owner/backup owner mapping với service catalog |
| Gia hạn không cần evidence | Quyết định cũ lặp lại vô thức | Renewal phải xét risk/threat/control hiện hành |
| Không có remediation funding | “Temporary” thành permanent | CAPA có milestone, budget và escalation |
| GRC tách khỏi runtime | Record đóng nhưng bypass vẫn hiệu lực | Stable IDs, reconciliation giữa GRC/IAM/SIEM/cloud |
| Không có notification | Hết hạn trong im lặng | Alert trước expiry và expired exposure |
| Chỉ đo số ticket Done | Rủi ro không được loại | Verified closure, exception exposure metrics |
| Suppression quá rộng | Khó nhìn attacker | Scope hẹp, test negative/positive, expiry |
| Legal/contract không tham gia | Acceptance vượt thẩm quyền | Applicability và escalation chuyên môn |
| Review dựa vào người viết rule | Không độc lập, dễ bỏ qua weak evidence | Peer/independent review theo criticality |
| Sợ outage nếu tự revoke | Giữ rule vĩnh viễn | Safe expiry strategy, alternate plan, runbook |
| Số liệu thiếu asset ngoài tool | Ngoại lệ nhân bản mà không thấy | Inventory độc lập và detection của scope drift |

## 6. Thời hạn: effective, expiry, review và remediation

### 6.1. Bốn mốc riêng

- **Effective from:** thời điểm bắt đầu có hiệu lực sau đúng approval và điều kiện.
- **Expires at:** thời điểm **decision không còn được phép viện dẫn** nếu không có quyết định mới hợp lệ.
- **Next review at:** thời điểm phải **đánh giá lại trước expiry**, hoặc sớm hơn do rủi ro.
- **Remediation due at:** deadline sửa root cause theo plan.

Review date không phải expiry; **xác nhận đã họp** không đồng nghĩa được gia hạn. Thay deadline ticket không tự đổi expiry có hiệu lực của decision.

### 6.2. Calendar expiry kết hợp event triggers

Một exception có thể buộc xem lại sớm khi:

- Migration/patch hoàn tất và cần retest.
- Bổ sung user/data/service/region vào scope.
- Vendor thay API/permission hoặc phát hành bản vá.
- Tăng threat exposure hoặc xuất hiện active exploitation.
- Compensating control không đạt test.
- Risk/owner/baseline/contract thay đổi.
- Credential/key có dấu hiệu bị compromise.
- Incident hoặc DR fail cho thấy impact cao hơn giả định.

Ghi “đến khi sự kiện X xảy ra” **chưa đủ** nếu sự kiện X không có ngày chốt. Cần maximum calendar expiry, review cadence và milestone/owner.

### 6.3. Những lỗi ngữ nghĩa thời gian

| Anti-pattern | Ví dụ | Kiểm soát |
|---|---|---|
| Không timezone | “Hết ngày 1/12” | UTC timestamp hoặc offset rõ ràng |
| Expiry quá khứ nhưng state ACTIVE | Data sync chậm hoặc job fail | Tính validity từ timestamp và approval, không từ nhãn |
| Review xong sau expiry | Không đủ lead time | Reminder trước hạn và escalation |
| Auto-renew | Gia hạn khi không có phản hồi | Explicit approval cho một kỳ mới |
| Backdate approval | Hôm nay duyệt nhưng ghi từ tuần trước | Giữ unauthorized gap; không sửa lịch sử |
| Deadline dự án vô hạn | “Until migration” | Event + finite calendar cap |
| Hạn rất xa không phù hợp risk | 5 năm cho admin bypass | Max TTL theo policy và kiểm justification |
| Owner mất hiệu lực | Người duyệt nghỉ việc | Reassign và reassess theo authority |
| Expiry decision nhưng runtime còn | Bypass vẫn bật | Reconciliation + response |
| Fix xong nhưng exception còn | Rule bypass không thu hồi | Close condition và verification |

Ví dụ mốc **2026-12-01T00:00:00Z**: nếu hệ thống dùng so sánh **current_time >= expires_at** thì lúc mốc đó exception **đã hết hiệu lực**; không suy diễn rằng được phép hoạt động “đến hết ngày 1/12”.

### 6.4. Vì sao không có TTL chung?

Hạn ngoại lệ phụ thuộc criticality, exposure, các nghĩa vụ không được miễn, impact, chứng cứ compensating controls, availability của fix, nguồn lực triển khai và nhịp thay đổi. Ví dụ privileged vendor access có thể cần lease rất ngắn; migration kiến trúc nhiều giai đoạn có thể cần một khoảng dài hơn nhưng **phải có reviews, milestones và hard end date**. Những ngày cụ thể trong lớp học không được biến thành một “chuẩn quốc tế” tưởng tượng.

## 7. Scope và tính áp dụng phải cụ thể

Một exception phải ghi:

1. Requirement/control ID và phiên bản.
2. Tình trạng không đạt được xác minh hoặc chưa đủ evidence.
3. Asset/service/region/tenant/environment.
4. Principal, role, network route, rule, event class hoặc dataset.
5. Data classification và service criticality.
6. Hành động được phép/bị cấm.
7. Có bao phủ assets/workloads **tạo mới** hay không.
8. Effective time, expiry, review và deadline.
9. Compensating controls đúng attack paths.
10. Evidence, owners và conditions to revoke.

**Wildcard scope** có thể biến một ngoại lệ cho một host thành rủi ro toàn account. Nếu tool chỉ hỗ trợ broad allowlist, đó là **giới hạn kỹ thuật cần đưa vào risk assessment**, không được tuyên bố ngoại lệ vẫn giới hạn như trên giấy.

### 7.1. Scope drift

Nếu asset chuyển từ test sang production, được mở Internet, lưu dữ liệu nhạy cảm hơn, đổi trust boundary hoặc thừa hưởng quyền mới, approval phải được đánh giá lại ngay. Thay đổi material có thể làm exception chuyển **REVIEW_REQUIRED**, cần containment hoặc revoke theo policy, **dù calendar expiry chưa tới**.

### 7.2. Inventory độc lập

Mẫu số đánh giá phải đến từ inventory/control register độc lập: cloud organization, identity paths, hosts, workload controllers, data flows, detection scenarios. **Không chỉ xem những exception đã được nhập vào GRC**, vì các bypass tạo ngoài workflow có thể bị bỏ sót.

## 8. Thẩm quyền, separation of duties và nghĩa vụ

| Vai trò | Trách nhiệm |
|---|---|
| **Requester** | Nêu lý do, condition, scope và action plan |
| **Control owner** | Giải thích objective, assertion và gap |
| **Service owner** | Business impact, availability, nguồn lực |
| **Security assessor** | Kiểm evidence, attack path và mitigation |
| **Risk owner** | Quyết định residual risk theo thẩm quyền |
| **Approver** | Phê duyệt scope, hạn, điều kiện và renewal |
| **IAM/SOC/platform** | Enforce runtime restrictions, monitor và revoke |
| **GRC/assurance** | Exception inventory, reminders, audit trail, KPI |
| **Remediation owner** | Fix root cause và tổ chức retest |
| **Independent reviewer** | Sampling, kiểm chất lượng decision và effectiveness |

Với exceptions high-risk, người tự sửa hệ thống không nên tự duyệt rủi ro còn lại của chính thay đổi nếu governance yêu cầu độc lập. Một người có thể đảm nhiệm nhiều vai trò trong tổ chức nhỏ, nhưng **quyền phê duyệt, kiểm chứng và theo dõi phải được mô tả rõ**.

Một điều kiện pháp luật/hợp đồng hoặc baseline bắt buộc có thể **không cho exception**. Approval nội bộ không biến một control gap thành compliance PASS và không tự miễn nghĩa vụ. Khi chưa chắc applicability hoặc quyền miễn, cần escalation tới bộ phận có thẩm quyền, không tạo waiver vô thời hạn để giải quyết.

## 9. State machine của ngoại lệ có kiểm soát

### 9.1. Các trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Hành động hợp lý |
|---|---|---|
| **REQUESTED** | Đã có yêu cầu, chưa có hiệu lực | Yêu cầu bổ sung scope, rủi ro, evidence |
| **UNDER_REVIEW** | Reviewer đang xác minh điều kiện | Kiểm thực tế, hỏi owner và risk authority |
| **REJECTED** | Không được phép tạo ngoại lệ | Remediate/contain, không cho bypass |
| **APPROVED_NOT_ACTIVE** | Có quyết định nhưng chưa đến thời điểm hoặc chưa đủ điều kiện | Không bật runtime exception trước effective start/guards |
| **ACTIVE** | Approval hợp lệ trong scope và kỳ, conditions còn đạt | Monitor, remediation và review |
| **REVIEW_REQUIRED** | Trigger xuất hiện hoặc sắp tới mốc review | Đánh giá lại theo current context, có thể giới hạn access |
| **EXPIRED** | Thời gian phê duyệt đã kết thúc | Không coi là approved; escalation và xử lý runtime exposure |
| **REVOKED** | Người có thẩm quyền rút approval sớm | Thu hồi bypass theo kế hoạch an toàn, xác minh hiệu lực |
| **REMEDIATION_PENDING_RETEST** | Đã sửa nhưng chưa kiểm control PASS | Giữ theo dõi, test theo assertion |
| **CLOSED_VERIFIED** | Primary control đạt trong scope và exception bypass đã được dọn | Đóng với evidence và audit trail |
| **SUPERSEDED** | Quyết định được thay bằng record mới có thẩm quyền | Giữ record cũ immutable, liên kết decision mới |

Không dùng **CLOSED** mơ hồ để trộn “control được sửa”, “risk accepted” và “exception hết hạn”. Một exception có thể hết hạn **trước khi** primary control được sửa, khiến rủi ro chưa xử lý và trạng thái approval không hợp lệ; hai trạng thái phải tồn tại song song.

### 9.2. Mô hình luồng

~~~mermaid
flowchart TD
    REQ["REQUESTED"] --> REV["UNDER_REVIEW"]
    REV -->|Deny| REJ["REJECTED"]
    REV -->|Approve with conditions| PRE["APPROVED_NOT_ACTIVE"]
    PRE -->|Time and gates valid| ACT["ACTIVE"]
    ACT -->|Reassessment trigger| NEED["REVIEW_REQUIRED"]
    NEED -->|New explicit approval| ACT2["ACTIVE with new decision/version"]
    NEED -->|Deny or conditions fail| REVOKE["REVOKED"]
    ACT -->|Expiry| EX["EXPIRED"]
    ACT2 -->|Expiry| EX
    ACT -->|Fix deployed| FIX["REMEDIATION_PENDING_RETEST"]
    ACT2 -->|Fix deployed| FIX
    FIX -->|Primary PASS and bypass removed| CLOSE["CLOSED_VERIFIED"]
    FIX -->|Retest fail| NEED
    EX --> OPEN["Finding remains OPEN / risk escalated"]
    REVOKE --> OPEN
    OPEN --> FIX
~~~

Ở đây, **ACTIVE with new decision/version** đòi hỏi ghi **điều kiện phê duyệt mới**; không phải quay lại ACTIVE chỉ vì đã cập nhật expires_at.

### 9.3. Quy tắc validity có nhiều điều kiện

Đừng đánh giá exception chỉ bằng một field trạng thái. Quyết định chỉ được coi **có hiệu lực** nếu đồng thời:

1. Có approval từ authority phù hợp.
2. Effective start đã tới, expiry chưa tới.
3. Scope và requirement version còn đúng.
4. Không có revoke/suspension hoặc sự kiện buộc xem lại chưa xử lý.
5. Các compensating controls bắt buộc đang có evidence hiệu lực.
6. Không có nghĩa vụ áp dụng ngăn việc miễn trừ.
7. Asset, owner và residual risk vẫn nằm trong phạm vi phê duyệt.

Tùy policy, một trigger có thể khiến ngoại lệ phải **tạm dừng ngay**, hoặc yêu cầu review khẩn trước khi thực hiện hành động tiếp. Quy tắc phải được định nghĩa trước, tránh để hệ thống tự quyết những biện pháp có tác động lớn ngoài thẩm quyền.

## 10. Mẫu exception record có bằng chứng

### 10.1. Ví dụ YAML

~~~yaml
exception_id: "SEC-EX-2026-007"
record_version: "1.0"
name: "Temporary MFA exception for legacy recovery console"
service: "legacy-payments-console"
environment: "production"
criterion:
  requirement_id: "IAM-PRIV-MFA-001"
  requirement_version: "4"
  expected: "MFA enforced on all required interactive admin paths"
condition:
  control_verdict: "FAIL"
  finding_id: "SEC-F-2026-147"
  evidence_ref: "SEC-EV-2026-1101"
  affected_path: "local-admin-recovery-console"
scope:
  asset_ids: ["legacy-console-example-01"]
  principal_ids: ["breakglass-example-a"]
  network_zone: "restricted-management"
  data_classification: "sensitive"
  expands_to_new_assets: false
justification:
  reason: "Vendor MFA integration not yet supported"
  alternatives_considered:
    - "Remove local access; not feasible for required disaster recovery"
    - "Replace appliance; migration program active"
risk_assessment:
  threat_scenario: "Unauthorized privileged use of local console"
  exposure: "Restricted management enclave, verified at decision time"
  impact: "High"
  residual_risk: "High with verified temporary controls"
  assumptions:
    - "Management network restriction remains effective"
    - "No evidence of active credential compromise"
compensating_controls:
  - control_id: "NET-MGMT-RESTRICT"
    required: true
    test_ref: "SEC-EV-2026-1102"
    verdict: "PASS_WITH_SCOPE"
  - control_id: "SESSION-AUDIT"
    required: true
    test_ref: "SEC-EV-2026-1103"
    verdict: "PASS_WITH_SCOPE"
  - control_id: "JIT-ACCESS"
    required: true
    test_ref: "SEC-EV-2026-1104"
    verdict: "PASS_WITH_SCOPE"
ownership:
  requester_role: "payments-platform"
  control_owner_role: "identity-platform"
  risk_owner_role: "payments-risk-owner"
  reviewer_role: "security-assurance"
approval:
  status: "APPROVED"
  approved_by_role: "authorized-risk-approver"
  approval_ref: "SEC-DEC-2026-031"
  approved_at: "2026-11-28T08:00:00Z"
  effective_from: "2026-11-28T09:00:00Z"
  expires_at: "2026-12-12T09:00:00Z"
  next_review_at: "2026-12-05T09:00:00Z"
remediation:
  owner_role: "legacy-platform-owner"
  plan_ref: "SEC-CAPA-2026-022"
  milestone: "MFA-capable replacement validated"
  due_at: "2026-12-10T09:00:00Z"
  closure_assertion: "No required privileged path bypasses MFA"
reassessment_triggers:
  - "Management network becomes reachable from new zone"
  - "Credential compromise or suspicious activity"
  - "Temporary monitoring control fails"
  - "Appliance becomes a dependency of a new critical service"
runtime_enforcement:
  rule_ref: "restricted-access-rule-example-01"
  expected_action_at_expiry: "REVIEW_AND_REVOKE_SAFELY"
  authorized_executor_role: "identity-operations"
status: "ACTIVE"
evidence_manifest: "restricted-evidence-store/SEC-EX-2026-007"
~~~

**Tất cả ID, ngày và giá trị là giả định**. Record không phải schema chính thức của bất kỳ nền tảng GRC/IAM nào. Một approval record cần được **gắn với effective runtime controls**, nhưng không nên chứa password, key hoặc dữ liệu người dùng nhạy cảm trong YAML.

### 10.2. Chú ý tính nhất quán thời gian

Đối với ví dụ:

- Approval lúc **08:00 UTC**.
- Có hiệu lực từ **09:00 UTC**.
- Next review trước expiry **7 ngày**.
- Milestone remediation trước expiry **2 ngày**.
- Hết hạn tại **09:00 UTC ngày 12/12/2026**.

Không được nhập một bản gia hạn tại 13/12 rồi âm thầm thay ngày trong record cũ để che khoảng chưa được phê duyệt từ 12/12 đến 13/12. Cần tạo **new decision/version** với mốc thực tế, ghi unauthorized gap nếu có.

### 10.3. Phân tách bản ghi quyết định và finding kỹ thuật

Một exception có thể liên kết với nhiều finding units; nhưng mỗi affected asset/control cần có kết quả kỹ thuật độc lập. Tương tự, một finding có thể được quản lý qua nhiều decisions kế tiếp (approval đầu, renewal, revoke). Nên lưu:

- **Finding ID:** condition, control assertion, evidence, remediation, retest.
- **Exception ID:** decision, scope, authority, expiry, controls bù trừ.
- **Runtime rule ID:** IAM role, firewall rule, suppression, vulnerability gate.
- **Service/asset ID:** thuộc population độc lập.
- **Decision version/event:** không ghi đè lịch sử.
- **Evidence manifest:** nguồn, test và limitations.

Điều này giúp auditor truy từ **asset → control FAIL → exception decision → mitigation → expiry → verified closure**.

## 11. Review và renewal: không phải nút kéo dài thời gian

### 11.1. Checklist renewal bắt buộc

Một renewal request tốt phải được xét gần như một risk decision mới:

1. Primary requirement còn applicable và version nào?
2. Condition hiện tại FAIL, INCONCLUSIVE hay đã sửa?
3. Scope assets/principals/data/regions có thay đổi không?
4. Threat/exploit/advisory và access path đã thay đổi thế nào?
5. Compensating controls có evidence mới còn hiệu lực?
6. Có test negative/positive với effective policy và monitoring không?
7. Có incident/finding/drift trong kỳ ngoại lệ?
8. Root cause/remediation đã đạt những milestone nào, vì sao trễ?
9. New deadline có khả thi và đã có resource/owner?
10. Residual risk thay đổi so với lần duyệt trước thế nào?
11. Approver hiện tại có đúng authority không?
12. Yêu cầu/contract/privacy obligations có cho phép renewal không?
13. Nếu từ chối, có containment/safe degraded mode/rollback nào?
14. Nếu chấp thuận, kỳ hiệu lực mới và trigger phải là gì?

### 11.2. Từ chối renewal không có nghĩa cưỡng bức thao tác nguy hiểm

Một exception expired có thể để lại một service đang vận hành qua local admin path. **Trạng thái approved phải kết thúc** theo governance, nhưng hành động runtime tiếp theo phải cân nhắc:

- Có thể hạn chế quyền/lưu lượng tức thì mà không gây mất dữ liệu?
- Có customer impact khi khóa tài khoản hoặc tắt integration?
- Cần incident commander hay emergency change authority?
- Có safe degraded/read-only mode?
- Có khả năng bypass vẫn hiện diện qua đường khác?
- Có đủ log và forensic preservation?
- Khi nào phải ngừng vận hành nếu risk không thể chấp nhận?

Cần tránh hai cực đoan: **auto-renew để khỏi outage** và **auto-disable production vô điều kiện** có nguy cơ gây thiệt hại lớn. Đúng hơn là **expire approval, escalate risk, enforce theo playbook có guardrails**.

### 11.3. Renewal cap và escalations

Các control governance có thể gồm:

- Yêu cầu risk owner cấp cao hơn khi renewal nhiều lần.
- Bắt buộc review độc lập cho exceptions đã quá tuổi chính sách.
- Review tại risk committee khi ảnh hưởng critical service.
- Thêm milestone, budget và owner của remediation program.
- Cấm tạo bản sao exception mới để “reset tuổi”.
- Link tất cả decisions thành một chain và tính **cumulative exposure age**.
- Phân biệt **renewed within authority** với **expired and reauthorized later**.

Các ngưỡng cụ thể do tổ chức lựa chọn. Một exception có ba phiên bản liên tiếp vẫn có thể là **một risk exposure kéo dài**, không phải ba rủi ro mới có tuổi bằng 0.

## 12. Kiểm soát bù trừ phải có hiệu lực và kỳ kiểm

### 12.1. Điều kiện giảm residual risk

Một compensating control chỉ có thể được dùng để hỗ trợ quyết định nếu:

- Liên quan đúng **attack path và security objective**.
- Bao phủ **mọi assets/principals** được exception cho phép.
- Có effective configuration và test, không chỉ diagram.
- Không có alternate paths bypass control.
- Có nguồn telemetry hoặc health checks phát hiện khi nó thất bại.
- Có reviewer, evidence collection và test frequency.
- Có expiry/reassessment khi network, IAM, schema hoặc vendor thay đổi.
- Không làm tăng rủi ro khác trái baseline bắt buộc.

Một MFA exception đi kèm network allowlist không có thử nghiệm deny từ untrusted network không đủ cơ sở để nói “rủi ro đã được giảm đáng kể”.

### 12.2. Ma trận test bù trừ

| Ngoại lệ | Control thay thế | Positive test | Negative test / giới hạn |
|---|---|---|---|
| Local admin thiếu MFA | Restricted network và JIT | Admin được phép trong maintenance window | Outside-zone/admin ngoài thời gian bị từ chối; không bảo vệ credential nếu có đường nội bộ khác |
| Lỗ hổng chưa patch | Segmentation, disable feature | Business workflow cần thiết vẫn hoạt động | Vulnerable endpoint/attack path bị chặn ở mọi entry points đã kiểm |
| Telemetry thiếu field | Log ở nguồn độc lập tạm | Actor/resource được ghi đầy đủ tại nguồn thay thế | Khả năng alert/forensics không bị mất ở required scenario; dữ liệu có thể không đầy đủ như primary |
| Vendor token quá quyền | JIT + scoped proxy | Vendor hoàn thành công việc approved | Actions/resources khác bị deny, session/expiry enforced |
| Encryption migration chưa xong | Data path restriction | Dịch vụ được phép chỉ xử lý data đúng scope | Không thể export/sao chép ra vùng trái quy định |
| DR restore chưa đạt | Containment và alternate recovery | Alternative recovery exercise đạt với dữ liệu đại diện | Không được tuyên bố RTO/RPO đạt nếu chưa thử |

Nếu compensating control **không thể** đáp ứng objective quan trọng, reviewer phải nêu giới hạn và cân nhắc **ngừng/giảm tính năng, tái thiết kế hoặc từ chối ngoại lệ**, không tự gọi một dashboard alert là tương đương MFA.

### 12.3. Kiểm soát bù trừ cũng có vòng đời

Một WAF rule tạm thời có thể bị bypass khi API chuyển qua private route. Một network isolation rule có thể bị mất sau IaC refactor. Một SOC detection có thể bị suppress trong đợt tối ưu parser. Vì thế exception phải có **dependency IDs** và trigger reevaluation khi controls bù trừ đổi.

## 13. Expiry automation: đúng thời hạn nhưng không gây lỗi bất ngờ

### 13.1. Thiết kế một vòng kiểm

Hệ thống có thể chạy định kỳ:

1. Lấy exception inventory đã được phê duyệt.
2. Kiểm thời gian hiện tại theo clock tin cậy.
3. Đối soát owner, scope, requirement và approval.
4. Phát **notice** trước review/expiry theo policy.
5. Kiểm các material change triggers từ asset/IAM/SIEM/cloud inventory.
6. Khi expiry, tính validity = **false**, kể cả nhãn state chưa cập nhật.
7. Escalate theo severity và service risk.
8. Gọi runtime enforcement action phù hợp policy/playbook và quyền.
9. Xác minh effective state sau hành động.
10. Ghi event, evidence, owner, action result, unknowns và next step.
11. Lưu audit history append-only/versioned.
12. Không tự nối hạn hoặc tự ghi control PASS.

### 13.2. Pseudocode kiểm tra trạng thái

~~~text
function evaluateException(record, now, context):
    if record.approval_status != "APPROVED":
        return NOT_AUTHORIZED

    if now < record.effective_from:
        return NOT_YET_ACTIVE

    if now >= record.expires_at:
        return EXPIRED_ESCALATE_AND_ENFORCE_PER_POLICY

    if not context.scope_matches_approved_record:
        return REVIEW_REQUIRED_SCOPE_DRIFT

    if context.material_risk_trigger_detected:
        return REVIEW_REQUIRED_OR_REVOKED_BY_POLICY

    if context.required_compensating_control_unverified:
        return INCONCLUSIVE_AND_ESCALATE

    if context.required_compensating_control_failed:
        return REVOKE_OR_CONTAIN_ACCORDING_TO_POLICY

    return ACTIVE_WITH_MONITORING

function requestRenewal(existing, evidence, decision):
    require(current_threat_and_scope_assessment)
    require(fresh_compensating_control_tests)
    require(remediation_progress_and_plan)
    require(authorized_explicit_approval)
    require(new_effective_and_finite_expiry)
    write_new_version_without_erasing_old_decision()
~~~

Pseudocode trên là mô hình logic **quản trị**, không phải code dùng trực tiếp để tắt production. Hệ thống thật cần các bước phê duyệt, authorization, idempotency, rate limiting của automation, dry run, audit, exception handling và monitoring.

### 13.3. Fail-safe không có nghĩa tắt mọi dịch vụ

Khi một privileged exception hết hạn, an toàn có thể đòi **khóa quyền** ngay; khi exception liên quan DR break-glass, tự khóa không có phương án thay thế có thể khiến tổ chức không khôi phục được dịch vụ. Cần phân loại trước:

| Loại exception | Response khi expiry | Điều cần kiểm |
|---|---|---|
| Vendor temporary support | Revoke scoped access theo policy | Role/session/token không còn hiệu lực |
| Firewall ingress tạm | Thu hẹp route/traffic có kiểm soát | Không còn bypass và không phá safety-critical service |
| Emergency admin/break-glass | Kích hoạt playbook kiểm soát, có alternative path | Access bị hạn chế và recovery still possible |
| Logging suppression | Bỏ suppression có kiểm soát hoặc tune rule | Detection vẫn vận hành, không tạo overload quá mức |
| Vulnerability patch deferral | Escalate, enforce containment và remediation | Risk chưa giải quyết không bị lẩn trong GRC |
| Third-party data transfer | Pause/limit integration nếu cần theo policy | Đối soát messages/data và data obligations |

**Không tự động xóa dữ liệu, rotate key hoặc thu hồi quyền critical không có guardrails** chỉ vì exception hết hạn. Đồng thời, không xem lo ngại outage là lý do đủ để gia hạn vô thời hạn.

### 13.4. Chống race condition và sai trạng thái

Các tình huống kỹ thuật:

- Renewal được approve đúng lúc scheduled expiry job chạy.
- Nhiều workers đồng thời revoke cùng một rule.
- Cloud provider API trả thành công nhưng effective permission chưa đổi.
- Ticket về CLOSED nhưng collector không có dữ liệu mới.
- Giờ hệ thống khác UTC hoặc bị drift.
- Network rule bị tạo lại bằng IaC sau khi auto-revoke.
- Owner thay đổi nhưng event sync đến muộn.

Cần **version/ETag hoặc compare-and-swap semantics khi áp dụng, idempotent actions, authoritative timestamps, reconciliation và retry có kiểm soát**. Trạng thái cuối cùng phải dựa trên **effective state**, không chỉ kết quả API call thành công.

## 14. Evidence, audit trail và thông tin phải bảo tồn

### 14.1. Chuỗi kiểm toán cần đọc được

~~~mermaid
flowchart LR
    REQ["Security requirement"] --> FIND["Finding / condition"]
    FIND --> EX["Exception scope + risk assessment"]
    EX --> DEC["Authorized decision + finite expiry"]
    DEC --> MIT["Compensating controls + test evidence"]
    MIT --> MON["Monitoring / drift / time events"]
    MON --> FIX["Remediation + retest"]
    FIX --> CLOSE["Bypass revoked + verified closure"]
    MON --> REV["Reassessment / renewal decision"]
    REV --> EX
~~~

Một auditor phải lần ra được từ finding tại thời điểm A tới decision có hiệu lực tại thời điểm đó, và có thể xác định các khoảng **chưa có approval hoặc chưa có compensating evidence**.

### 14.2. Evidence register

| Evidence ID | Chứng cứ | Mục đích | Giới hạn |
|---|---|---|---|
| **EX-EV-01** | Policy/control requirement và phiên bản | Xác định criterion | Chưa nói asset có đạt |
| **EX-EV-02** | Effective control test FAIL | Xác nhận condition | Chỉ trong test scope/time |
| **EX-EV-03** | Risk assessment, approved scope | Cơ sở cho decision | Risk có thể đổi |
| **EX-EV-04** | Authorization/approval record | Ai duyệt, khi nào, hạn nào | Không chứng minh mitigation thực tế |
| **EX-EV-05** | Network/IAM effective-state export | Phạm vi quyền/bypass | Snapshot, có drift |
| **EX-EV-06** | Controlled positive/negative tests | Hiệu lực kiểm soát bù trừ | Không bao phủ mọi biến thể |
| **EX-EV-07** | SIEM/alert synthetic event test | Monitoring và loss-of-source | Một event không đại diện toàn kỳ |
| **EX-EV-08** | Remediation milestones, change records | Tiến độ fix | Ticket Done chưa đủ retest |
| **EX-EV-09** | Renewal/rejection history | Quá trình thay risk decision | Không được sửa lại decision cũ |
| **EX-EV-10** | Closure and bypass-revocation test | Primary control đạt và runtime ngoại lệ hết | Cần monitor drift sau closure |

### 14.3. Hash, timestamps và quyền truy cập

- Lưu evidence ở kho có access controls và audit trail.
- Giữ nguồn gốc, thời điểm, phương pháp thu và artifact version.
- Redact secrets/token/customer data khi chia sẻ dashboard.
- Không cho requester sửa approval/evidence sau khi đã phát hành.
- Với hash/signature, bảo vệ trust anchor và mốc tham chiếu, không chỉ tính checksum.
- Có retention policy cho quyết định và findings theo obligations.
- Với dữ liệu đến muộn, ghi restatement và version chứ không ghi đè lịch sử.

**Checksum khớp không chứng minh source event đầy đủ hoặc bản ghi rủi ro đúng**; evidence phải được kiểm relevance và completeness.

## 15. Remediation và verified closure

### 15.1. Đóng ngoại lệ không chỉ đổi trạng thái

Muốn đóng một ngoại lệ MFA:

1. Upgrade hoặc thay authentication path để hỗ trợ requirement.
2. Xác định mọi privileged interactive paths trong scope.
3. Test effective MFA enforcement với required users.
4. Negative test đường bypass bị từ chối.
5. Positive test đường hợp lệ vẫn hoạt động.
6. Kiểm break-glass vẫn có phương án phục hồi an toàn.
7. Gỡ network/IAM/allowlist tạm không còn cần thiết.
8. Kiểm audit/monitoring sau thay đổi.
9. Đánh primary control PASS theo scope và time đã test.
10. Close exception có approval, evidence và revision history.
11. Thêm provisioning/CI/drift guardrail để không tái xuất hiện.

Một team triển khai bản vá nhưng chưa verify runtime nên đánh **FIX_IMPLEMENTED_PENDING_RETEST**, không phải CLOSED_VERIFIED.

### 15.2. Root cause và CAPA

| Root cause | Correction | Preventive action |
|---|---|---|
| Provisioning tạo admin bypass | Bật MFA cho đường hiện tại | Guardrail tạo tài khoản mới; deny/approval tests |
| Firewall exception quên xóa | Gỡ rule cho asset hiện tại | Lease-bound firewall access và expiry monitor |
| SIEM suppress rule vĩnh viễn | Bỏ suppression sau tuning | Detection-as-code với owner/expiry và regression tests |
| Vendor token quá quyền | Rotate/thu hẹp token | Vendor offboarding và scoped access lifecycle |
| Scanner exemption blanket | Kiểm asset và bỏ exemption không hợp lệ | Inventory reconciliation, test coverage |
| Backup encryption exception | Hoàn tất migration và retest decrypt | Release gate cho key lifecycle và restore |
| Exception approvals tự động | Dừng auto-renew | Renewal workflow với explicit risk decision |
| Reviewer mất quyền | Gán owner hợp lệ | HR/service catalog owner-change trigger |

**Corrective action** và **verified closure** phải được nối với test. Một exception được đóng rồi xuất hiện lại trong kỳ mới nên có linked finding/root-cause record, không làm mất lịch sử.

### 15.3. Cách xử lý ngoại lệ hết hạn chưa sửa

Nếu expired trước khi remediation hoàn tất:

- Trạng thái approval: **EXPIRED**.
- Trạng thái technical control: **FAIL hoặc INCONCLUSIVE** theo evidence.
- Tình trạng runtime bypass: phải được kiểm thực tế.
- Residual risk: cần escalation/cấp quyết định mới có thẩm quyền.
- Response: containment hoặc giới hạn hoạt động theo policy và safety.
- Finding: giữ mở đến khi verified closure hoặc disposition đúng governance.
- Báo cáo: ghi khoảng **unapproved exposure** nếu tồn tại.

**Không backdate approval** để biến một khoảng thời gian chưa có thẩm quyền thành hợp lệ.

## 16. Kiểm soát chống ngoại lệ bị nhân bản

### 16.1. Duplicate-safe ID và phạm vi

Cần unique ID cho từng exception decision và stable IDs cho asset/control. Nếu cùng finding được “renew” bằng một exception mới, phải có **supersedes/previous_decision_id**. Không nên tính tuổi từ ngày tạo bản mới; phải biết **original exposure start** khi xác định được.

### 16.2. Đối soát inventory

Tối thiểu so sánh:

- Actual IAM grants, local admin paths, network allowlists.
- Detection suppressions, parser exclusions, log source exemptions.
- Vulnerability scan exclusion lists và unmanaged assets.
- Encryption/security policy exemptions, key permission exceptions.
- CI/CD security gate overrides và artifact bypasses.
- Vendor support tokens, external network accesses.
- Backup/DR excluded datasets và untested recovery scenarios.

Nếu phát hiện runtime bypass **không có approved record**, cần mở finding **UNAUTHORIZED_EXCEPTION_OR_CONTROL_BYPASS**, không tự tạo một approved exception hồi tố để hợp thức hóa.

### 16.3. Gộp để xử lý nguyên nhân nhưng không mất chi tiết

Ví dụ 30 services dùng chung một identity proxy legacy. Có thể tạo **một remediation program** nâng proxy, nhưng exception phải giữ:

- Những services/principals thực sự bị ảnh hưởng.
- Criticality và dữ liệu theo service.
- Những môi trường đã/không được approved.
- Compensating controls/test per scope.
- Ngày start/expiry và owner từng group.
- Kết quả rollout/retest khác nhau.

Một phê duyệt blanket cho “all systems” không có evidence không thể thay thế 30 kết luận.

## 17. Luồng áp dụng cho CI/CD, IaC và security controls

### 17.1. Security gate override phải có lease

Trong pipeline có thể phát sinh override khi một SCA/SAST/IaC policy gate báo lỗi mà team vẫn cần build hotfix. Một override không được là flag tắt kiểm tra vô thời hạn:

- Gắn rule ID, repo/branch/commit/artifact scope.
- Lý do và finding đã xác minh.
- Owner, approver, expires_at và next review.
- Compensating tests hoặc giới hạn deploy.
- Không áp dụng sang repo/branches mới ngoài scope.
- Audit CI executions đã dùng override.
- Tự động đánh hết hiệu lực về mặt approval khi hết hạn.
- Reconcile nếu pipeline vẫn thực thi bypass sau expiry.

Một security pipeline “xanh” khi rules đã bị tắt không chứng minh artifact an toàn.

### 17.2. Policy-as-code giúp enforce nhưng không thay judgment

Có thể tự động bắt buộc metadata và chặn những override thiếu approval/expiry. Tuy nhiên công cụ không biết đầy đủ:

- Contractual obligations và luật áp dụng.
- Business impact của việc khóa access.
- Threat scenario mới chưa được mô tả.
- Lỗ hổng có thể bị khai thác qua đường khác.
- Hiệu lực control bù trừ trong network runtime.
- Dữ liệu nào đã được vendor nhận trước revoke.

Do đó, tự động hóa nên đảm nhận **completeness, validity, audit và cảnh báo**, còn high-risk acceptance cần reviewer đúng authority và evidence thật.

## 18. Quản trị rủi ro khi exception không thể kết thúc đúng hạn

Không phải mọi exception có thể sửa ngay trong kỳ được duyệt. Nhưng điều đó không làm **perpetual exception** trở thành lựa chọn phù hợp.

Quy trình ra quyết định:

1. Xác minh vì sao remediation trễ; phân biệt dependency thật và ưu tiên nguồn lực.
2. Tính lại residual risk từ current threat, exposure, data và controls.
3. Đánh giá affected business impact nếu ngừng một chức năng.
4. Xác định interim containment, giới hạn access hoặc safe degraded mode.
5. Đề xuất alternative technology/architecture hoặc vendor escalation.
6. Xem có thể tách migration thành nhiều milestone nhỏ và kiểm từng phần.
7. Quyết định theo authority, applicability và giới hạn pháp lý/hợp đồng.
8. Nếu renewal hợp lệ, tạo record/version mới có kỳ và điều kiện cụ thể.
9. Nếu không hợp lệ, thực hiện response an toàn và báo **unapproved gap**.
10. Đưa root cause thành funded remediation workstream, không chỉ lùi ticket.
11. Có independent assurance review và retest.
12. Giữ history của toàn bộ exposure, kể cả các lần gia hạn.

Sự trưởng thành của security assurance được thể hiện ở **khả năng ra quyết định minh bạch về rủi ro khó chịu**, thay vì làm trạng thái dashboard đẹp bằng cách giấu ngoại lệ.

## 19. Đối soát bằng dữ liệu: tìm exception hết hạn và bypass không được duyệt

### 19.1. Mô hình dữ liệu tối thiểu

Một hệ thống quản lý có thể gồm:

- **required_control_units:** từng asset × control × environment phải đánh giá.
- **control_results:** test result theo scope, verdict, timestamp, method, version.
- **exception_decisions:** exception_id, control_id, unit_id/scope, approval, effective_from, expires_at, revoked_at, next_review_at, decision_version.
- **runtime_bypasses:** principal/allowlist/suppression/rule IDs quan sát tại runtime.
- **asset_inventory:** service, criticality, data class, owner, lifecycle.
- **compensating_tests:** control thay thế, test version, evidence, verdict và freshness.
- **remediation_actions:** findings, owner, deadlines, milestones, retest.
- **audit_events:** decision changes, rule changes, runtime change actor/time.

Mục tiêu không phải xây một database thật theo đúng tên trường trên mà làm rõ các liên kết **control applicability ↔ decision ↔ effective runtime state ↔ evidence**.

### 19.2. Ví dụ SQL kiểm các decision đã hết hạn

~~~sql
-- SQL minh họa; tên bảng/cột và bind parameters là giả định.
SELECT
    e.exception_id,
    e.control_id,
    e.service_id,
    e.risk_owner_id,
    e.expires_at,
    e.approval_status,
    e.decision_version
FROM exception_decisions e
WHERE e.approval_status = 'APPROVED'
  AND e.effective_from <= :as_of_utc
  AND e.expires_at <= :as_of_utc
  AND e.superseded_at IS NULL
ORDER BY e.expires_at ASC;
~~~

Query phát hiện những record **từng được duyệt và đã quá hạn** theo giả định không có decision mới thay thế. Nó **không chứng minh** runtime bypass vẫn hoạt động; cần nối với rule inventory. Nếu hệ thống lưu version thay thế khác, điều kiện superseded phải theo version chain.

### 19.3. Tìm ngoại lệ thiếu owner hoặc hạn

~~~sql
SELECT
    exception_id, service_id, control_id,
    risk_owner_id, expires_at, next_review_at
FROM exception_decisions
WHERE approval_status IN ('APPROVED', 'PENDING')
  AND (
       risk_owner_id IS NULL
    OR expires_at IS NULL
    OR next_review_at IS NULL
  );
~~~

Một APPROVED record không có expires_at nên được xem là **data quality/governance failure**, không tự coi nó được phê duyệt vô thời hạn. Khi phân tích hệ thống cũ, có thể có legitimate legacy records cần xử lý chuyển đổi; nhưng không tự gán hạn giả trong quá khứ và tuyên bố từng compliant.

### 19.4. Tìm runtime bypass thiếu approval hợp lệ

~~~sql
-- Mô hình giả định: mỗi runtime bypass có control/asset/rule ID.
SELECT
    b.rule_id,
    b.asset_id,
    b.control_id,
    b.observed_at
FROM runtime_bypasses b
LEFT JOIN exception_decisions e
  ON e.rule_id = b.rule_id
 AND e.asset_id = b.asset_id
 AND e.control_id = b.control_id
 AND e.approval_status = 'APPROVED'
 AND e.effective_from <= :as_of_utc
 AND e.expires_at > :as_of_utc
 AND e.revoked_at IS NULL
WHERE b.is_enabled = TRUE
  AND e.exception_id IS NULL;
~~~

Kết quả là **candidate unapproved bypasses**: cần kiểm scope, policy applicability, change windows, eventual consistency, đồng bộ và review exceptions thay thế; không tự kết luận tất cả là malicious actions.

**Cảnh báo:** Nếu nguồn runtime_bypasses chỉ lấy từ các rule đã được onboard, việc tìm thấy “0 unapproved bypasses” không chứng minh toàn hệ thống không có bypass. Cần **population reconciliation** với cloud/IdP/SIEM/CI/CD inventory độc lập.

### 19.5. Không gộp trạng thái quyết định và control tests

Một query báo cáo có thể trả:

| Control unit | Control verdict | Exception decision | Thực thi runtime | Kết luận |
|---|---|---|---|---|
| A | FAIL | ACTIVE hợp lệ | Bypass đúng scope | Gap được chấp nhận có điều kiện, **không PASS** |
| B | FAIL | EXPIRED | Bypass vẫn bật | Unapproved exposure, cần escalation |
| C | INCONCLUSIVE | Không có | Không rõ | Data quality gap, không PASS |
| D | PASS | Còn ACTIVE | Bypass còn bật | Phải xem bypass cần thu hồi dù test primary PASS |
| E | PASS | CLOSED_VERIFIED | Bypass đã gỡ | Đã đóng trong scope/kỳ kiểm |
| F | FAIL | APPROVAL PENDING | Bypass đã bật | Chưa có decision có hiệu lực; cần containment/review |

**Một KPI chỉ nhìn trạng thái “có approval” sẽ bỏ qua cả B, D và F.**

## 20. Case study 1: tài khoản vendor thiếu MFA được duyệt “tạm” suốt hai năm

### 20.1. Bối cảnh

Một nhà cung cấp bảo trì hệ thống vận hành quan trọng bằng local administrator account. Hai năm trước, tích hợp MFA gặp lỗi; team tạo exception để vendor truy cập từ một dải IP được phép. Ticket ghi “until vendor upgrade” và không có expiry. Trong hai năm:

- Dải IP truy cập của vendor đổi.
- Một integration mới đưa thêm dữ liệu khách hàng vào service.
- Privileged account được thêm quyền backup configuration.
- Monitoring rule ban đầu bị đổi khi nâng cấp SIEM.
- Risk owner cũ đã chuyển bộ phận.
- Kế hoạch upgrade của vendor không còn có thời hạn xác định.

Không có evidence cho rằng tài khoản đã bị lạm dụng, nhưng cũng không có test hiện hành chứng minh network restriction và monitoring đầy đủ.

### 20.2. Nhận diện vấn đề

| Khía cạnh | Tình trạng | Đánh giá |
|---|---|---|
| Primary MFA control | Không đáp ứng theo thiết kế cũ | **FAIL** |
| Exception validity | Không expiry và owner không còn thẩm quyền | **NOT_VALIDATED/REVIEW_REQUIRED** |
| Asset scope | Dữ liệu/quyền mới ngoài approval ban đầu | **SCOPE_DRIFT** |
| Network allowlist | Địa chỉ vendor thay đổi | **Needs effective-state retest** |
| Monitoring | Rule thay đổi, chưa có synthetic test | **INCONCLUSIVE** |
| Remediation | Upgrade không có milestone | **Control debt đang tích lũy** |
| Incident evidence | Chưa có compromise được xác nhận | Không kết luận incident/breach |

### 20.3. Phương án xử lý

1. Mở finding về **unbounded exception**, đối chiếu account, permissions, IP và service dependencies.
2. Xác định truy cập nào cần thiết ngay, ai thực hiện và trong thời hạn nào.
3. Giảm quyền backup configuration nếu không cần; xem khả năng JIT/proxy/VPN riêng.
4. Kiểm network path thực tế và các alternate access paths.
5. Xác minh audit events và alert route với synthetic event được phép.
6. Đánh giá credential hygiene, active sessions và quyền vendor.
7. Áp một **short-lived emergency access decision** mới nếu governance và obligations cho phép, với scopes/approvals/expiry rõ; không coi đó là gia hạn mặc định của record cũ.
8. Có plan thay sản phẩm hoặc sửa MFA với milestones, nguồn lực và owner.
9. Retest đường admin enforce MFA, gỡ bypass và verify runtime khi migration xong.
10. Theo dõi theo kỳ các exceptions/privileged access mới phát sinh.

### 20.4. Điểm tinh tế

Nếu xóa account đột ngột có thể làm mất đường recovery, cần thiết kế **alternative recovery path** và thẩm quyền theo service criticality. Nhưng nguy cơ outage không cho phép biến exception cũ thành approved vô hạn. Có thể containment bằng giới hạn phiên JIT, giảm privileges, tạm dừng những chức năng rủi ro và escalation.

**Bài học:** một exception được coi là tạm thời nhưng không có hạn và không có người quản lý sẽ dần biến thành **cấu hình mặc định nằm ngoài security assurance**.

## 21. Case study 2: permanent SIEM suppression và dashboard “green”

### 21.1. Bối cảnh

SOC có detection rule giám sát thay đổi quyền quản trị trên cloud accounts. Một đợt maintenance làm tăng alert volume nên đội vận hành tạo suppression cho tài khoản management. Không có ngày hết hạn. Sáu tháng sau dashboard ghi nhận giảm 70% alerts và đội báo kết quả tuning tốt.

Trong một exercise có kiểm soát, sự kiện thay đổi privileged role trên management account đến log store đầy đủ nhưng **không tạo alert** vì suppression wildcard vẫn hoạt động. Các cloud accounts mới kế thừa cùng group label và cũng bị suppress ngoài intended scope.

### 21.2. Phân biệt các claim

| Claim | Bằng chứng | Kết luận hợp lý |
|---|---|---|
| Log source healthy | Collector heartbeat PASS | Chưa chứng minh detection scenario được bao phủ |
| Privileged events stored | Event ID xuất hiện trong SIEM | Thu event có thể PASS trong tập kiểm |
| Detection coverage | Synthetic rule test không tạo alert | **FAIL trong scope đã test** |
| Alert volume giảm | Dashboard thống kê volume | Không chứng minh false positive rate giảm |
| Suppression approved | Record cũ không expiry/scope hiện hành | **Governance gap** |
| Có incident thật không? | Chưa có chứng cứ | Không kết luận có tấn công |

### 21.3. Remediation và verification

1. Inventory tất cả suppression rules, scopes, owners và timestamps.
2. Đánh **REVIEW_REQUIRED** cho rule không expiry/owner và mở finding detection gap.
3. Đối soát rule trên source, parser, detection logic, suppression và alert routing.
4. Tuning theo root cause của false positives, không xóa toàn bộ class.
5. Tách maintenance suppression thành **time-boxed, principal/asset-scoped rule**.
6. Kiểm positive và negative scenarios, event field fidelity, route tới SOC.
7. Xác định khoảng thời gian suppression làm giảm visibility và nhu cầu hunting/retrospective review theo risk.
8. Bổ sung monitoring cho suppression rule creation/extension/expiry.
9. Retest các cloud accounts mới và group inherited settings.
10. Ghi control verdict và exception decision riêng trong reporting.

**Bài học:** không thể coi giảm alert là giảm risk nếu đổi lại **false negatives hoặc coverage gap**.

## 22. Case study 3: “legacy encryption exception” mở rộng qua data residency và vendor

### 22.1. Bối cảnh

Một ứng dụng cũ được phép tạm thời lưu một lớp dữ liệu không nhạy cảm trên hệ thống chưa hỗ trợ encryption baseline mới. Ngoại lệ được tạo cho môi trường nội bộ và hết hạn sau migration. Sau nhiều lần thay đổi:

- Ứng dụng trở thành service production dùng dữ liệu khách hàng.
- Vendor bổ sung subprocessor mới.
- Storage được sao chép sang một region khác.
- Backup retention và KMS requirements đã đổi.
- Exception record chỉ ghi “legacy data pipeline” mà không có asset IDs, data classes hoặc expiry.
- Cán bộ phê duyệt ban đầu không còn giữ vai trò.

### 22.2. Vì sao không thể chỉ tiếp tục renewal?

Có **material changes** về data class, production status, region, third party và cryptographic control. Những điều kiện này có thể kích hoạt **applicability/legal/privacy/contract review**; không được mặc định cùng exemption áp dụng như trước.

Một xử lý đúng có thể gồm:

1. Data-flow và data classification trước/sau.
2. Actual storage/backup locations, encryption state, IAM/KMS permissions.
3. Applicable obligations và shared responsibility với vendor.
4. Evidence về transport encryption và stored data protection.
5. Immediate containment cho các luồng không được phép.
6. Tách scope không thể duyệt khỏi những parts có thể quản lý tạm.
7. Remediation plan: encryption migration, key lifecycle và restore testing.
8. Risk decision đúng authority, không backdate approval.
9. Test encryption, backup decrypt và data residency boundaries.
10. Retest và verified closure cho từng dataset/service.

**Không kết luận đã vi phạm một đạo luật cụ thể** khi chưa xác định jurisdiction, loại dữ liệu và nghĩa vụ; nhưng cũng không dùng ngoại lệ cũ để phủ nhận yêu cầu mới chưa được đánh giá.

### 22.3. Bài học

Một exception có thể trở thành **không áp dụng được ngay cả trước expiry** khi scope và obligations thay đổi. Một hồ sơ “đã duyệt” không thay cho control effectiveness, data protection và risk assessment hiện hành.

## 23. KPI và dashboard để phát hiện ngoại lệ không có hạn

### 23.1. KPI phải có mẫu số và phân loại

| Metric | Định nghĩa có ích | Cạm bẫy |
|---|---|---|
| **Missing-expiry decision count** | Decision đang được viện dẫn nhưng không có timestamp expiry | Không thấy record tồn tại ngoài GRC |
| **Expired exception exposure** | Required control units có bypass active sau expiry | Chỉ thấy EXPIRED trong ticket, không kiểm runtime |
| **Valid approval coverage** | Required exception decisions có scope, owner, approval, expiry, tests hợp lệ / tập cần đánh giá | Approved không đồng nghĩa control PASS |
| **Overdue review count** | Exceptions chưa được review tại next_review deadline | Không đồng nghĩa mọi controls FAIL |
| **Repeated renewal count** | Decision chains với nhiều lần renewal, theo original exposure | Tạo exception ID mới làm reset tuổi |
| **Cumulative exception age** | Thời gian từ initial verified condition đến closure hoặc hiện tại | Không reset age khi đổi ticket |
| **Compensating control verification coverage** | Required compensating assertions có test PASS còn hiệu lực / tổng required assertions | “Control enabled” không bằng effective PASS |
| **Remediation milestone adherence** | Milestones thực sự đạt đúng hạn / milestones đến hạn | Milestone tự thay deadline làm KPI đẹp |
| **Exception closure quality** | Exceptions primary control PASS và bypass revoked / exceptions cần đóng | Ticket CLOSED chưa đủ |
| **Unapproved runtime bypass count** | Candidate active bypass không có valid approved record | Cần reconciliation và validation |
| **Critical-service exception exposure** | Exception units trên services critical theo severity/age | Không gộp với hệ thống thử ít rủi ro |
| **Renewal decision lead time** | Từ request renewal đến approval/denial có hiệu lực | Thời gian nhanh không chứng minh review chất lượng |
| **Control debt recurrence** | Exception/gap xuất hiện lại sau closure với root cause tương tự | Cần taxonomy và history |

### 23.2. Ví dụ mẫu số và báo cáo

Giả sử 24 exception decision chains liên quan tới các security controls bắt buộc tại mốc chốt:

- 9 ACTIVE có approval, expiry, owner và evidence bù trừ còn hiệu lực.
- 5 APPROVED nhưng sắp expiry và chưa có review trong hạn.
- 4 EXPIRED, runtime bypass vẫn được xác minh còn bật.
- 3 thiếu risk owner hoặc calendar expiry.
- 2 đang RENEWAL_PENDING, chưa có quyết định mới; 1 trong đó đã hết hạn.
- 1 đã FIX_IMPLEMENTED nhưng bypass vẫn bật, chưa retest.

**Chú ý:** các trạng thái minh họa này được định nghĩa là **sáu nhóm loại trừ nhau**, tổng 24. Vì nhóm “5 APPROVED sắp expiry” chưa có review đúng kỳ, việc coi decision có hiệu lực kỹ thuật phải được kiểm theo chính sách và thời điểm. Không được chỉ gộp **9 + 5 = 14 green**.

Những nhóm cần hành động khẩn theo risk context gồm 4 expired runtime bypasses, 3 decision records thiếu điều kiện tối thiểu và 1 pending renewal đã quá hạn. **Không cộng các nhóm giao nhau một lần nữa** khi tính số unique impacted services; cần deduplicate theo asset/control.

Một executive summary nên trình bày **counts + criticality + aging + unapproved exposure + evidence quality + owners/decisions required**; không chỉ “tỷ lệ exceptions được duyệt”.

### 23.3. Verified control coverage không cộng accepted risk

Với 100 required control units:

- 80 PASS có evidence.
- 8 FAIL nhưng có active approved exceptions.
- 5 FAIL không có approval hợp lệ.
- 4 INCONCLUSIVE.
- 3 NOT_TESTED.

**Verified control coverage = 80/100 = 80%.** Không báo 88% compliant vì cộng 8 exceptions vào PASS. Có thể báo thêm **8 control gaps được quản trị bằng ngoại lệ còn hạn**, nhưng phải hiển thị residual risk và điều kiện.

### 23.4. Cảnh báo sớm có ích hơn chỉ đợi audit

- Expiry trong kỳ sắp tới, chưa có renewal evidence.
- Owner không còn trong current service catalog.
- Compensating test đã stale hoặc FAIL.
- Scope tăng asset/permission hoặc data classification.
- Suppression rule không có TTL.
- Renewal chain kéo dài vượt policy cap.
- Remediation milestone trễ nhiều lần.
- Runtime bypass còn sau closure.
- Policy baseline đổi nhưng exceptions chưa được remapped.
- Vendor contract/region thay mà chưa review applicability.

Các early warnings giúp tổ chức **ngăn ngoại lệ trở thành vĩnh viễn** thay vì chỉ khám phá khi incident xảy ra.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Một risk owner duyệt ngoại lệ privileged MFA cho một tài khoản không có ngày hết hạn, vì “vendor upgrade chưa biết lịch”. Vấn đề chính là gì?

**Gợi ý:** Không có finite bound, remediation milestones, trigger và khả năng reapproval. Cần quyết định giới hạn và kế hoạch thay thế; rủi ro không được phép mặc định kéo dài vô thời hạn.

**Câu 2.** Exception ACTIVE nhưng primary control FAIL; có thể đưa vào numerator KPI “control PASS rate” không?

**Gợi ý:** Không. Báo riêng control verdict và risk disposition; risk acceptance không đổi kết quả kỹ thuật.

**Câu 3.** Hệ thống GRC ghi EXPIRED nhưng firewall rule vẫn cho phép traffic. Có thể nói rủi ro đã được loại bỏ?

**Gợi ý:** Không. Effective runtime access phải được kiểm và xử lý; record expiry không tự thu hồi rule.

**Câu 4.** Một exception được ghi “until project complete”, dự án không có deadline. Nó có timebound không?

**Gợi ý:** Không đủ. Cần calendar cap, milestone owner, review cadence và escalation nếu không hoàn tất.

**Câu 5.** Reviewer đã phê duyệt ngoại lệ cho dev account. Ba tháng sau service trở thành production. Approval còn áp dụng không?

**Gợi ý:** Không tự động. Đây là scope/material risk change; cần reassess policy, assets, data, IAM, controls và authority.

**Câu 6.** SOC suppress rule 90 ngày, hết hạn sẽ có rất nhiều alerts. Có nên auto-renew để khỏi overload?

**Gợi ý:** Không nên auto-renew. Tuning, segmentation, rate limiting, staggered restoration và remediation có kiểm soát; approved residual risk phải có review thực.

**Câu 7.** Team đổi remediation due date vì sprint bận. Exception expires_at có tự gia hạn không?

**Gợi ý:** Không. Đây là hai thực thể khác nhau; renewal cần risk reassessment và decision mới.

**Câu 8.** Compensating firewall control có cấu hình đúng, nhưng test deny từ network khác không chạy. Có thể coi control PASS?

**Gợi ý:** Chưa đủ evidence về hiệu lực theo assertion; phải test effective state/bypass paths hoặc ghi giới hạn/INCONCLUSIVE.

**Câu 9.** Một approval có thời hạn hết vào 00:00 UTC. Request renewal nộp trước hạn nhưng approver duyệt sau hạn. Khoảng chờ có được xem là approved không?

**Gợi ý:** Không chỉ nhờ nộp request. Cần ghi gap và quyết định thực tế; không backdate nếu policy không cho và không có approval hợp lệ.

**Câu 10.** Vì sao không thể lấy số exceptions đã nhập trong GRC làm mẫu số đầy đủ để đánh giá bypass?

**Gợi ý:** Những manual IAM/CI/CD/SIEM/network bypass chưa đăng ký có thể không xuất hiện; cần runtime/source-of-truth inventory độc lập.

**Câu 11.** Một ứng dụng có primary MFA PASS rồi nhưng local bypass vẫn ACTIVE. Ngoại lệ có nên CLOSED_VERIFIED không?

**Gợi ý:** Chưa, nếu bypass vẫn là đường không được phép. Thu hồi và kiểm effective access trước closure.

**Câu 12.** Một nhà cung cấp chuyển dữ liệu sang subprocessor khác, nhưng exception encryption còn hạn. Có cần review?

**Gợi ý:** Có thể có material data-flow/applicability change. Cần đánh giá lại dù chưa hết hạn.

**Câu 13.** Một service critical có exception đã gia hạn bảy lần, mỗi lần tạo ID mới. Chỉ số tuổi ngoại lệ tính thế nào?

**Gợi ý:** Dùng linked decision chain và original exposure start, không reset cumulative age.

**Câu 14.** Một exception hợp đồng không cho phép miễn trừ nhưng được CEO phê duyệt nội bộ. Có tự trở thành compliant?

**Gợi ý:** Không. Thẩm quyền nội bộ không miễn nghĩa vụ hợp đồng/pháp lý; cần xử lý theo applicability, bên có thẩm quyền và kế hoạch đáp ứng.

**Câu 15.** Không thấy incident liên quan ngoại lệ trong một năm. Có chứng minh residual risk bằng 0?

**Gợi ý:** Không. Có thể do ít quan sát, xác suất hiếm, threat thay đổi hoặc chưa có detection. Cần đánh giá kiểm soát/evidence và exposure.

**Câu 16.** Nếu auto-revoke exception làm hỏng đường DR recovery, nên bỏ luôn expiry?

**Gợi ý:** Không. Thiết kế safe expiry/playbook với alternate recovery, phân vai và kiểm rights, không giữ approval vô hạn.

## 25. Bài thực hành: audit một exception register có nhiều sai lệch

### 25.1. Dữ liệu tình huống giả định

Bạn tham gia security assurance review của doanh nghiệp quản lý cloud accounts, APIs, IAM, SIEM, SaaS và DR. Có 10 exceptions hoặc bypass candidates:

| ID | Tình trạng | Rủi ro/điều thiếu |
|---|---|---|
| **E01** | Vendor admin không MFA; không expiry; quyền vào production | Privileged access, owner cũ |
| **E02** | Firewall ingress exception hết hạn tuần trước; rule vẫn ACTIVE | Unapproved network exposure |
| **E03** | SIEM suppression có expiry nhưng scope đã mở sang 3 account mới | Detection blind spot và scope drift |
| **E04** | Vulnerability P1 chưa patch; accepted risk đã renew 5 lần | Threat/exposure và remediation chậm |
| **E05** | CI security gate bypass cho release emergency, chưa hậu kiểm | Supply-chain control gap |
| **E06** | Exception encryption từng cho data nội bộ, giờ xử lý dữ liệu khách hàng | New data/applicability scope |
| **E07** | Backup restore exception có expiry tuần sau, rehearsal vẫn FAIL | Resilience risk, needed decision |
| **E08** | Vendor support token đã revoke, nhưng exception record vẫn ACTIVE | Closure/evidence gap |
| **E09** | IAM MFA requirement nay được đáp ứng, nhưng local bypass còn bật | Revocation/verified closure chưa đạt |
| **E10** | Một Kubernetes workload được exempt policy, nhưng không có GRC record | Unapproved runtime bypass |

### 25.2. Nhiệm vụ học viên

1. Với từng item, xác định **primary control verdict**, **approval validity** và **runtime bypass state** riêng.
2. Xếp mức ưu tiên điều tra, immediate containment và escalation theo risk context; không chỉ theo tuổi ticket.
3. Gắn service/asset owner, control owner và risk acceptance authority.
4. Xác định những records **chưa được phép coi ACTIVE** vì thiếu owner, expiry, scope hoặc approval.
5. Liệt kê những material changes buộc tái đánh giá **ngay trước hạn**.
6. Viết finite expiry/next review và milestone cho một exception được phép cấp lại.
7. Đề xuất positive/negative tests của E01, E02, E03 và E09.
8. Thiết kế safe response cho E07 để không phá DR availability nhưng không tự renew.
9. Đối soát các exceptions với IAM, firewall, SIEM, CI/CD và Kubernetes inventory.
10. Viết chương trình CAPA cho ít nhất ba root causes, gồm trigger monitoring.
11. Tính verified control coverage cho tập required units được cung cấp trong mục 23.3.
12. Viết báo cáo risk committee: confirmed gaps, unknowns, affected critical services, mitigation, owners, deadlines và decisions cần phê duyệt.
13. Thiết kế rule chống create-new-ID-to-reset-age.
14. Đề xuất các KPI tách **control effectiveness** khỏi **risk disposition**.
15. Xác định evidence cần giữ sau khi revoked/closed và thời hạn lưu theo policy.
16. Chọn những trường hợp cần legal/privacy/vendor review do applicability changes.

### 25.3. Bảng gợi ý triage, không phải auto-priority

| Item | Nhận định ban đầu | Điều kiện trước khi kết luận |
|---|---|---|
| E01 | High concern: privileged MFA bypass không có hạn | Effective access, compensating evidence, recovery need, authority |
| E02 | Expired approval + enabled runtime ingress | Scope, Internet reachability, safe enforcement path |
| E03 | Suppression scope drift | Test detection scenarios và nguồn affected |
| E04 | Repeated renewals đáng escalation | Exploitation evidence, new patch, business impact, owner/budget |
| E05 | Emergency bypass chưa hậu kiểm | Exact artifact, pipeline permission, evidence |
| E06 | Data classification changed | Data flow, obligations, encryption/KMS, vendor |
| E07 | Recovery assertion FAIL | BIA, alternate recovery, restore tests và safe response |
| E08 | Có thể đủ điều kiện closure | Revoke/deny tests, evidence reference và record cleanup |
| E09 | Primary PASS chưa đủ nếu bypass còn | Negative access test và deprovision |
| E10 | Unapproved exception candidate | Admission/effective state, service ownership, policy applicability |

**Không tự kết luận incident hoặc breach** nếu chỉ có evidence về control gap. Khi có dấu hiệu lạm dụng thật, chuyển sang IR triage theo playbook.

### 25.4. Tiêu chí đánh giá bài thực hành

| Tiêu chí | Đạt khi |
|---|---|
| **Scope** | Affected assets, environments, data và control requirements rõ |
| **Governance** | Approval, authority, validity, expiry, owner tách bạch |
| **Evidence** | Test method, timestamps, source, scope, PASS/FAIL/UNKNOWN rõ |
| **Action** | Có containment, remediation, milestone, owner và deadline |
| **Safety** | Không auto-disable critical services thiếu guardrails |
| **Auditability** | Decision history và exposure gaps không bị backdate |
| **Metrics** | Không cộng accepted risks vào control PASS |
| **Continuous** | Có expiry monitor, drift triggers, CAPA và retest |
| **Obligations** | Không áp acceptance cho requirement không được miễn |
| **Quality** | Nhìn thấy blind spots, không chỉ ticket theo GRC |

## 26. Checklist phòng chống ngoại lệ không có hạn

### 26.1. Khi tạo và phê duyệt

- [ ] Có security requirement/control ID và phiên bản phù hợp.
- [ ] Condition được mô tả, evidence và confidence đủ cho decision.
- [ ] Scope rõ asset, account, principal, region, environment, data class.
- [ ] Nguyên nhân chưa thể khắc phục và alternatives được xem xét.
- [ ] Threat scenario, exposure, business impact và residual risk được đánh giá.
- [ ] Có kiểm tra nghĩa vụ/contract/regulatory applicability trước khi cho miễn.
- [ ] Risk owner/approver đúng authority và separation of duties.
- [ ] Compensating controls có tests và evidence, không chỉ mô tả thiết kế.
- [ ] Có effective_from, finite expires_at và next_review_at rõ timezone.
- [ ] Có remediation owner, funded milestone, deadline và acceptance criteria.
- [ ] Có event triggers khi threat, scope, owner và control changes.
- [ ] Có runtime rule/principal ID để đối soát actual state.
- [ ] Có response/communication plan khi expiry hoặc revoke.
- [ ] Approval chỉ có hiệu lực trong scope/time/conditions đã duyệt.
- [ ] Không tạo ngoại lệ cho điều kiện pháp lý/hợp đồng không cho miễn.

### 26.2. Trong thời gian hiệu lực

- [ ] Theo dõi hiệu lực compensating controls theo risk-appropriate cadence.
- [ ] Kiểm actual IAM/network/SIEM/CI/runtime state, không chỉ ticket.
- [ ] Theo dõi asset/data/privilege scope drift và new workloads.
- [ ] Phát cảnh báo trước review date và expiry đủ lead time.
- [ ] Reassess khi có active exploitation, credential leak hoặc incident.
- [ ] Risk owner và reviewer vẫn còn thẩm quyền và liên hệ được.
- [ ] Remediation milestones đang được cập nhật với bằng chứng.
- [ ] Không âm thầm gia hạn expiry khi ticket due date đổi.
- [ ] Không auto-renew dựa trên im lặng.
- [ ] Không đưa exception ACTIVE vào control PASS rate.
- [ ] Không giấu FAIL/unknown khi compensating test mất dữ liệu.
- [ ] Decision và evidence versions được bảo vệ, audit access phù hợp.

### 26.3. Khi hết hạn, gia hạn hoặc đóng

- [ ] Expiry tính chính xác từ UTC/offset và approval validity.
- [ ] Có escalation đến đúng owner khi hết hạn hoặc owner không tồn tại.
- [ ] Runtime enforcement an toàn, có guardrails/rollback nếu tác động lớn.
- [ ] Nếu cần renewal, có **new assessment, new decision và finite period**.
- [ ] Không backdate approval để che exposure gap.
- [ ] Nếu remediation đã implement, phải có retest đúng control assertion.
- [ ] Bypass, allowlist, suppression hoặc emergency privilege được gỡ/giới hạn.
- [ ] Negative/positive tests xác minh effective state sau cleanup.
- [ ] Findings còn mở được theo dõi đến verified closure hoặc disposition hợp lệ.
- [ ] Có CAPA khi exception lặp hoặc cùng root cause.
- [ ] Tuổi tích lũy không bị reset khi tạo decision ID mới.
- [ ] Báo cáo risk committee về expired/high-risk/unapproved exposures.
- [ ] Evidence, approval, risk assessments và history được lưu theo policy.
- [ ] Reconciliation với inventory độc lập xác minh không còn orphaned bypass.
- [ ] Review exception policy nếu hàng loạt ngoại lệ vô hạn lặp lại.

## 27. Mô hình triển khai trong chương trình security assurance

Một chương trình có thể triển khai theo bốn bước:

**Bước 1 — Kiểm kê và làm sạch:** tổng hợp exception decisions cùng actual bypass/allowlist/suppression; xác định owner, expiry, control, asset; không vội sửa status cũ hoặc xóa bằng chứng.

**Bước 2 — Risk triage:** phân loại nhóm thiếu hạn, quá hạn, owner mất, scope drift, compensating controls không có evidence; ưu tiên critical services/privileged/data boundaries; chuyển issue cần incident response theo bằng chứng.

**Bước 3 — Enforce lifecycle:** thêm finite TTL/explicit approval, review triggers, versioned decisions, monitoring, safe expiry automation và linked remediation; kiểm các trạng thái REVIEW_REQUIRED/EXPIRED/REVOKED.

**Bước 4 — Continuous assurance:** đối soát inventory định kỳ và sau material change; test hiệu lực bù trừ, verified closure, exception age, root-cause recurrence và KPI; tổ chức sampling review độc lập để tránh dashboard tự xác nhận.

### 27.1. Kết quả mong đợi

Chương trình thành công không nhất thiết đưa exception count về zero ngay. Thành công có thể quan sát khi:

- Không còn quyết định **có hiệu lực** mà thiếu owner/expiry/authority.
- Những legacy exceptions được xử lý bằng risk decision minh bạch, không xóa lịch sử.
- Runtime bypasses được phát hiện dù không có trong GRC.
- Critical gap được containment/remediate theo mức rủi ro.
- Mỗi exception có kế hoạch kết thúc và điều kiện re-review có bằng chứng.
- Control PASS và accepted risk được báo cáo riêng.
- Số lần renewal kéo dài không có tiến bộ bị giảm.
- Verified closures gắn với primary assertion và việc thu hồi bypass.
- Service owners thấy trước dependency khi ngoại lệ hết hạn.

## Kết luận

**Ngoại lệ không có hạn là một anti-pattern nguy hiểm vì biến quyết định tạm thời thành lỗ hổng kiểm soát tồn tại ngoài nhịp đánh giá rủi ro.** Threat, dữ liệu, quyền, nhà cung cấp và architecture tiếp tục thay đổi, trong khi một approval cũ không tự bảo đảm residual risk còn chấp nhận được. Thêm ngày hết hạn trên giấy là chưa đủ nếu runtime rule vẫn mở, compensating controls chưa test hoặc mọi renewal đều tự động.

Trong **SECURITY_SECURITY_ASSURANCE**, quản trị ngoại lệ phải duy trì chuỗi **security objective → requirement/control FAIL → risk và scope có bằng chứng → authorized time-bound decision → compensating control tests → continuous monitoring → review/revoke/renewal đúng quyền → remediation → retest → verified closure**. Khi tổ chức tách **trạng thái quyết định** khỏi **trạng thái control và runtime**, đồng thời có cơ chế phát hiện scope drift, expired exposure và audit history, ngoại lệ mới thực sự là **công cụ quản trị rủi ro ngắn hạn**, không phải cách hợp thức hóa vô thời hạn những điểm yếu bảo mật.


