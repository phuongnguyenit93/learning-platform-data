# Xác định metric khi thiết kế chương trình IAM

Trong một chương trình **Identity and Access Management (IAM)**, câu hỏi “hệ thống có tự động tạo và khóa tài khoản không?” chưa đủ để đánh giá thành công. Tổ chức cần biết **tạo tài khoản đúng lúc đến mức nào, thu hồi quyền mất bao lâu, bao nhiêu quyền tồn dư sau khi thay đổi vai trò, những đích nào chưa được kiểm soát, và bằng chứng có đủ để xác nhận kết quả hay không**. Các câu hỏi này cần được biến thành **metric** (chỉ số đo lường) có định nghĩa thống nhất, nguồn dữ liệu đáng tin cậy và cách diễn giải không gây hiểu nhầm.

Ví dụ, đội IAM báo “99% yêu cầu Leaver được xử lý trong 5 phút” vì lệnh khóa account đã được gửi tới IdP. Tuy nhiên một số SaaS và account local chỉ được thu hồi quyền sau 30 phút. Nếu chỉ đo thời gian **gửi lệnh** mà không đo **quyền thực tế ở hệ thống đích**, dashboard có thể cho cảm giác an toàn sai lệch.

Bài học thuộc chương **Thiết kế chương trình IAM**, module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Trọng tâm là thiết kế hệ đo lường cho vòng đời **Joiner–Mover–Leaver (JML)** từ xác minh danh tính, cấp tài khoản và role, đến review và thu hồi khi chuyển vai trò hoặc chấm dứt quan hệ. Các metric cần liên kết IdP, SSO, SCIM, RBAC/ABAC, quyền đặc biệt, tài khoản dịch vụ, kiểm toán và mục tiêu giảm **quyền truy cập tồn dư**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **metric, KPI, KRI, SLI, SLO, SLA**, cùng các chỉ số hoạt động và kết quả.
2. Thiết kế metric theo câu hỏi quản trị: *đang đo điều gì, đơn vị nào, trong phạm vi nào, với mẫu số nào, tại mốc thời gian nào?*
3. Định nghĩa các chỉ số Joiner, Mover, Leaver dựa trên **effectiveAt, eventReceivedAt, commandSentAt và targetVerifiedAt**.
4. Đo độ bao phủ identity/account/entitlement, chất lượng nguồn danh tính, provisioning drift, SoD, đặc quyền, approval, access review và non-human identity.
5. Xây dựng **metric catalog** có công thức, tập dữ liệu, owner, nguồn sự thật, dữ liệu thiếu, chu kỳ cập nhật, phân nhóm và mục tiêu.
6. Thiết kế dashboard, cảnh báo, thử nghiệm chất lượng dữ liệu và ví dụ truy vấn đo lường.
7. Nhận diện lỗi KPI phổ biến: mẫu số bị thay đổi, bỏ qua hệ thống không tích hợp, dùng giá trị trung bình che đuôi phân phối, đánh đồng gửi lệnh với thu hồi thành công.

## 2. Metric, KPI, KRI, SLI, SLO và SLA khác nhau thế nào?

**Metric** là đại lượng có cách đo rõ ràng; **KPI** là metric được chọn để đánh giá tiến độ đạt mục tiêu; **KRI** là chỉ số báo hiệu mức rủi ro; **SLI** mô tả mức chất lượng dịch vụ quan sát được; **SLO** là mục tiêu mong muốn cho SLI; **SLA** là cam kết dịch vụ có điều kiện và trách nhiệm đã được thỏa thuận.

| Thuật ngữ | Ý nghĩa | Ví dụ trong IAM |
|---|---|---|
| **Metric** | Phép đo có đơn vị, công thức và phạm vi | Số entitlement bị thu hồi trong tuần. |
| **KPI — Key Performance Indicator** | Đo kết quả quan trọng của chương trình | Tỷ lệ Leaver được xác nhận thu hồi toàn bộ quyền bắt buộc đúng hạn. |
| **KRI — Key Risk Indicator** | Dấu hiệu rủi ro hiện hữu hoặc tăng lên | Số privileged account không có owner hợp lệ. |
| **SLI — Service Level Indicator** | Chất lượng dịch vụ đo được theo quan sát | Tỷ lệ lệnh provisioning được xác minh tại đích trong ngưỡng quy định. |
| **SLO — Service Level Objective** | Mức mục tiêu nội bộ cho SLI | Mục tiêu thí điểm: 99% hành động thu hồi thuộc scope được xác nhận trong ngưỡng rủi ro tương ứng. |
| **SLA — Service Level Agreement** | Cam kết chính thức với bên sử dụng dịch vụ | Thời hạn xử lý yêu cầu IAM và điều kiện áp dụng do các bên thỏa thuận. |
| **Leading indicator** | Tín hiệu sớm có thể dự báo rủi ro | Tỷ lệ event bị lỗi schema hoặc backlog chưa xử lý. |
| **Lagging indicator** | Kết quả sau khi điều kiện đã xảy ra | Quyền Leaver còn tồn dư quá thời hạn kiểm soát. |

Các ngưỡng ví dụ trong bài nhằm minh họa cách xây dựng SLO; **không phải chuẩn bắt buộc áp dụng cho mọi tổ chức**. Với quyền quản trị production hoặc chấm dứt khẩn cấp, yêu cầu có thể khác đáng kể quyền ứng dụng ít nhạy cảm. Ngưỡng phải được chủ sở hữu kiểm soát, bảo mật và nghiệp vụ phê duyệt theo rủi ro.

### Chọn metric có thể dẫn đến hành động

Metric tốt phải giúp ai đó ra quyết định. Chẳng hạn:

- “Tổng số user đang tồn tại” chỉ cho biết quy mô, **không chứng minh danh tính hợp lệ**.
- “Số lệnh SCIM thành công” đo hoạt động của connector, **không chứng minh tất cả quyền ở đích đã đúng**.
- “Số Leaver còn entitlement sau mốc hiệu lực” cho biết nguy cơ cần xử lý, nếu đo dựa trên inventory đủ bao phủ.
- “Tỷ lệ review đã bấm quyết định” đo tiến độ reviewer, nhưng phải đi kèm **tỷ lệ remediation đã xác minh** mới đo được hành động thực tế.

Không nên chọn metric chỉ vì dữ liệu dễ lấy. Bắt đầu từ **mục tiêu kiểm soát** rồi xác định dữ liệu và hệ thống nào phải bổ sung.

## 3. Xây dựng cây mục tiêu đo lường cho chương trình IAM

Một cách chia nhóm là dùng năm chiều:

| Chiều đo lường | Câu hỏi quản trị | Nhóm metric đại diện |
|---|---|---|
| **Coverage — độ bao phủ** | Chúng ta đang quản trị được bao nhiêu danh tính, tài khoản, ứng dụng và entitlement cần quản trị? | Account correlation coverage, target integration coverage, direct grant discovery. |
| **Correctness — tính đúng** | Quyền hiện có có phù hợp role, chính sách, phê duyệt, scope và thời hạn không? | Entitlement drift, orphan account, SoD violations, unauthorized direct grants. |
| **Timeliness — tính kịp thời** | Sau sự kiện JML hoặc hết hạn, hệ thống mất bao lâu để thay đổi quyền thật? | Joiner readiness, Mover revoke latency, Leaver verified deprovision latency. |
| **Assurance — bằng chứng** | Có chứng minh được quyết định và quyền tại đích không? | Target readback coverage, audit correlation completeness, review remediation confirmation. |
| **Reliability — độ tin cậy vận hành** | Nếu nguồn, queue hoặc connector lỗi, hệ thống có phát hiện và khôi phục không? | Event lag, retry age, dead-letter backlog, reconciliation freshness. |

~~~mermaid
flowchart TD
    GOAL["Mục tiêu IAM<br/>Đúng người - đúng quyền - đúng thời điểm"] --> C["Coverage<br/>Phạm vi quản trị"]
    GOAL --> R["Correctness<br/>Quyền hợp lệ"]
    GOAL --> T["Timeliness<br/>JML kịp thời"]
    GOAL --> A["Assurance<br/>Bằng chứng"]
    GOAL --> O["Reliability<br/>Vận hành"]
    C --> CA["Identity / Account / Entitlement"]
    R --> RA["RBAC-ABAC / SoD / Drift"]
    T --> TA["Joiner / Mover / Leaver"]
    A --> AA["Readback / Review / Audit"]
    O --> OA["Event pipeline / Connector / Reconciliation"]
~~~

Các chiều không thay thế nhau. **Coverage thấp** có thể làm mọi tỷ lệ correctness trông rất tốt vì hệ thống chưa tích hợp không xuất hiện trong mẫu số. **Reliability thấp** cũng khiến dữ liệu assurance không đầy đủ. Vì vậy nên trình bày các chỉ số như một bộ chỉ báo thay vì ép tất cả thành một “IAM health score” duy nhất không giải thích được.

## 4. Trước khi tính: xác định đối tượng, mẫu số và phạm vi

### 4.1. Đơn vị đo quan trọng hơn tên metric

Chương trình IAM thường có các thực thể sau:

| Đơn vị | Cách định danh nên có | Cảnh báo |
|---|---|---|
| **Identity** | `identityId` và source reference | Một người có nhiều account và có thể nhiều quan hệ. |
| **Relationship** | `sourceSystem + sourceRecordId` hoặc contract ID | Một danh tính có thể giữ nhiều quan hệ độc lập. |
| **Account** | `targetSystemId + tenantId + nativeAccountId` | Email/username không đủ để phân biệt account qua tenant. |
| **Role assignment** | `assignmentId` và scope/expiry | Một role có thể gán nhiều lần ở tài nguyên khác nhau. |
| **Entitlement grant** | `grantId` hoặc tổ hợp native permission và provenance | Một quyền hiệu lực có thể đến từ nhiều grant. |
| **Lifecycle event** | `sourceSystem + eventId`, version và `effectiveAt` | Event trùng không phải hai lần thay đổi nghiệp vụ. |
| **Provisioning action** | `actionId`, target và attempt | Retry không làm tăng số lượng tác vụ nghiệp vụ. |
| **Review item** | `campaignId + reviewItemId` | Một identity có thể có hàng chục review item. |
| **Evidence** | `evidenceId`, thời điểm quan sát và nguồn | Lệnh thành công khác với readback quyền thực tế. |

**Đếm theo user không giống đếm theo account hoặc entitlement.** Một nhân viên có một IdP account, hai SaaS account, một cloud identity và ba quyền đặc biệt. Nếu Leaver đã thu hồi ba account nhưng còn cloud role, phải nêu rõ tỷ lệ **theo account** khác với kết luận **đã khóa toàn bộ quyền theo identity**.

### 4.2. Mẫu số phải bao gồm đối tượng không thành công

Ví dụ metric “tỷ lệ Leaver đã xác nhận thu hồi”:

\[
\text{Leaver verified completion rate}
= \frac{\text{Số Leaver trong cohort có mọi hành động thu hồi bắt buộc đã xác minh}}{\text{Tổng số Leaver thuộc cohort phải thu hồi}}\times100\%.
\]

Nếu chỉ lấy những Leaver mà connector đã gửi thành công làm mẫu số, những event bị mất, account local không được phát hiện hoặc lệnh chưa tạo sẽ **biến mất khỏi báo cáo**. Mẫu số cần được hình thành từ nguồn vòng đời có thẩm quyền và inventory scope đã công bố, không từ “những bản ghi pipeline tình cờ xử lý được”.

### 4.3. Chọn cửa sổ đo và cohort

- **Event cohort:** tập sự kiện có `effectiveAt` nằm trong kỳ; thích hợp đo kết quả JML.
- **Receipt cohort:** event được IAM nhận trong kỳ; thích hợp đo sức khỏe kênh tiếp nhận nhưng không đủ để đo bao phủ event bị mất.
- **Action cohort:** các lệnh được tạo trong kỳ; thích hợp đo connector nhưng không đại diện toàn bộ biến cố JML.
- **Snapshot cohort:** toàn bộ account/quyền tại thời điểm snapshot; thích hợp đo orphan, drift hoặc review coverage.
- **Rolling window:** cửa sổ 7/30 ngày; giúp xem xu hướng nhưng cần giải thích cách xử lý cohort chưa đủ thời gian hoàn tất.

Khi công bố KPI phải nêu rõ cohort và thời điểm **as-of**. Nếu một Leaver có hiệu lực cuối ngày, quyền được xác nhận thu hồi sang ngày hôm sau, thì báo cáo ngày trước đó có thể đang **pending**, không nên xóa Leaver khỏi mẫu số vì chưa hoàn tất.

## 5. Hợp đồng dữ liệu đo lường (metric contract)

Mỗi metric quan trọng nên được quản lý như một đối tượng có version, owner và ngữ nghĩa ổn định:

| Trường | Cần trả lời |
|---|---|
| `metricId`, `version` | Chỉ số này có định nghĩa ổn định không; sửa công thức thế nào? |
| `controlObjective` | Rủi ro hay mục tiêu nào cần đo? |
| `businessDefinition` | Một người đọc dashboard hiểu kết quả là gì? |
| `unit` | Identity, account, entitlement, event hay action? |
| `numerator` / `denominator` | Chính xác tập đếm và điều kiện lọc ra sao? |
| `startTimestamp` / `endTimestamp` | Lấy mốc nào để tính latency? |
| `scope` / `exclusions` | Những hệ thống/tenant/identity type nào được tính hoặc loại trừ, và tại sao? |
| `authoritativeSources` | Nguồn có thẩm quyền của cả dữ kiện nghiệp vụ và trạng thái đích? |
| `freshness` / `qualityChecks` | Độ mới và quy tắc phát hiện sai lệch dữ liệu? |
| `dimensions` | Có thể phân tách theo hệ thống, risk tier, identity type, team, tenant không? |
| `aggregation` | Đếm, tỷ lệ, percentile hay xu hướng; xử lý no-data thế nào? |
| `owner`, `reviewer` | Ai chịu trách nhiệm metric và ai chấp thuận thay đổi? |
| `target` / `alertCondition` | Ngưỡng mong muốn và điều kiện cảnh báo có được phê duyệt? |
| `actionOnBreach` | Khi vượt ngưỡng, ai điều tra và khắc phục? |

### Ví dụ catalog entry

~~~yaml
# Ví dụ minh họa để thiết kế metric; không phải schema chuẩn của sản phẩm IAM.
metric:
  id: iam.leaver.verified_revocation_within_target
  version: 1
  controlObjective: Xác nhận thu hồi quyền Leaver đúng hạn
  ownerTeam: IdentityGovernance
  unit: LEAVER_RELATIONSHIP
  cohort:
    timestamp: effectiveAt
    identityTypes: [EMPLOYEE, CONTRACTOR]
    scopePolicy: IAM_ACCOUNT_SCOPE_V3
  numerator:
    condition: ALL_REQUIRED_REVOCATIONS_CONFIRMED_WITHIN_TARGET
  denominator:
    condition: ALL_IN_SCOPE_EFFECTIVE_LEAVERS
  timestamps:
    start: relationship.effectiveAt
    end: latestRequiredRevocation.verifiedAt
  segmentation:
    - riskTier
    - sourceSystem
    - targetSystem
    - identityType
  missingData:
    targetReadback: NOT_CONFIRMED
    missingSourceRecord: DATA_QUALITY_EXCEPTION
  validation:
    - rejectNegativeLatencyForReview
    - requireStableIdentityAndTargetKeys
    - monitorTargetInventoryCoverage
  alerting:
    method: APPROVED_RISK_TIER_THRESHOLDS
  evidence:
    - sourceEventId
    - actionIds
    - targetEvidenceIds
~~~

Mốc `latestRequiredRevocation.verifiedAt` chỉ có nghĩa khi mọi hành động bắt buộc đã có bằng chứng và tập đích yêu cầu đã được xác định. Nếu còn đích chưa xác nhận, **không tự gán end timestamp bằng thời điểm gửi lệnh**.

## 6. Mô hình thời gian và bằng chứng cho metric JML

Một sự kiện vòng đời có thể đi qua nhiều mốc:

~~~mermaid
flowchart LR
    E["effectiveAt<br/>Điều kiện nghiệp vụ có hiệu lực"] --> R["receivedAt<br/>IAM nhận event"]
    R --> D["decisionAt<br/>Tính trạng thái mong muốn"]
    D --> S["sentAt<br/>Gửi lệnh đến đích"]
    S --> K["ackAt<br/>Đích phản hồi"]
    K --> V["verifiedAt<br/>Đọc lại quyền thực tế"]
~~~

Lưu ý: thứ tự trên là **đường đi minh họa** khi event được nhận sau mốc hiệu lực. Với Joiner/Leaver được lên lịch trước, `receivedAt` có thể **sớm hơn** `effectiveAt`; không lấy thứ tự hình vẽ làm quy tắc sắp xếp bắt buộc. Các timestamp nên dùng ISO 8601 kèm offset hoặc UTC và đồng bộ đồng hồ phù hợp.

### Các công thức latency

| Tên | Cách tính | Câu hỏi trả lời |
|---|---|---|
| **Delivery lag** | `receivedAt − publishedAt` | Tin từ nguồn đến IAM nhanh thế nào? |
| **Decision lag** | `decisionAt − receivedAt` | IAM mất bao lâu để tính quyết định sau khi nhận? |
| **Dispatch lag** | `sentAt − dueAt`, trong đó `dueAt` là mốc phải thực hiện theo policy | Lệnh được phát trễ so với thời điểm cần hành động bao nhiêu? |
| **Connector acknowledgment lag** | `ackAt − sentAt` | Đích phản hồi kỹ thuật nhanh thế nào? |
| **Verification lag** | `verifiedAt − dueAt` | Khi nào trạng thái thực tế được xác nhận phù hợp? |
| **Residual access duration — observed** | `verifiedAt − effectiveAt` với quyền Leaver và các giả thiết thích hợp | Khoảng chậm nhất mà ta có thể xác nhận đã hoàn tất thu hồi kể từ mốc kết thúc. |

Với **sự kiện có hiệu lực tương lai**, một lệnh provision được lập lịch sớm hoặc chuẩn bị trước không phải tự nhiên có dispatch lag âm là “xuất sắc”. Cần đo readiness theo mục tiêu của Joiner và quyền hiệu lực đúng thời điểm; đối với Leaver, cần phân biệt trước/sau mốc bắt buộc.

Nếu target chỉ được kiểm tra ở 18:05 (vẫn active) và 18:12 (disabled), **thời điểm mất quyền thực tế nằm đâu đó giữa hai quan sát**, trừ khi ứng dụng cung cấp event authoritative chính xác hơn. `verifiedAt − effectiveAt` là độ trễ **xác nhận**; không mặc định là thời gian chính xác user còn dùng được quyền.

### Xử lý latency âm và thiếu mốc

- Event được báo trước làm `receivedAt − effectiveAt` âm là tình huống hợp lệ của scheduler.
- `verifiedAt < effectiveAt` có thể hợp lệ nếu thu hồi được phép và đã thực hiện trước ngày kết thúc; muốn đo sai lệch nghiệp vụ phải xem policy có cho thu hồi sớm không.
- Timestamp bất khả thi do clock skew cần gắn nhãn dữ liệu chất lượng kém, không tùy tiện dùng `abs()` để biến thành thời gian dương.
- Khi thiếu `verifiedAt`, action chưa có chứng cứ; metric latency phải thể hiện **pending/censored** và báo số lượng chưa xác nhận, không tự loại khỏi phân phối.

## 7. Metric cho Joiner: sẵn sàng đúng lúc và đúng quyền

Một Joiner thành công không chỉ là “đã tạo user”. Tổ chức cần nhân viên có những công cụ cần thiết **đúng thời điểm** nhưng không được cấp quyền nhạy cảm quá sớm hoặc ngoài nhiệm vụ.

| Metric | Định nghĩa gợi ý | Điểm cần lưu ý |
|---|---|---|
| **Joiner identity linkage coverage** | Joiner trong cohort có identity nội bộ và khóa nguồn hợp lệ / tổng Joiner trong cohort | Tránh liên kết nhầm và tài khoản trùng. |
| **Day-one baseline readiness** | Joiner có toàn bộ account/role baseline yêu cầu đã xác nhận sẵn sàng tại mốc bắt đầu / tổng Joiner phải có baseline | Quyền không được kích hoạt sớm nếu policy không cho. |
| **Joiner provisioning latency** | Phân phối độ trễ từ mốc được phép kích hoạt đến khi baseline được xác minh | Phân tách theo target và loại user. |
| **Over-provisioned Joiners** | Joiner có entitlement ngoài chính sách hoặc approval / tổng Joiner được kiểm tra | Nhận diện cấp nhầm quyền vượt nhu cầu. |
| **Joiner missing-critical-access rate** | Joiner thiếu account/entitlement cần thiết tại mốc bắt đầu / tổng Joiner yêu cầu quyền đó | Chỉ dùng danh mục baseline đã phê duyệt. |
| **New-account duplicate rate** | Account được tạo trùng hoặc identity correlation sai / tổng account mới tạo hoặc kiểm tra | Quy tắc xác định duplicate cần rõ. |

### Ví dụ tính readiness

Trong tháng có **200 Joiner** bắt đầu làm việc. Theo baseline policy, tất cả cần cổng nội bộ và ứng dụng công việc; 190 người được xác minh đủ cả hai **đúng mốc**, 7 người thiếu một ứng dụng và 3 người chỉ đủ sau giờ bắt đầu.

\[
\text{Day-one baseline readiness}=\frac{190}{200}\times100\%=95\%.
\]

Không tính 3 người hoàn tất muộn thành “đúng hạn” chỉ vì quyền đã được cấp trước khi chạy báo cáo cuối tháng. Tuy vậy cần theo dõi thêm **eventual completion** và **độ trễ xử lý của 10 người** để xác định nguyên nhân.

### Chất lượng thay vì chỉ tốc độ

Một đội có thể nâng readiness bằng cách cấp thật nhiều quyền cho tất cả Joiner, nhưng tạo rủi ro. Do đó readiness phải đi cùng **over-provisioning rate** và các cảnh báo về role nhạy cảm chưa có phê duyệt. Mục tiêu là **đúng quyền đúng lúc**, không phải tối đa hóa số account đã được tạo.

## 8. Metric cho Mover: thu hồi quyền cũ và ngăn privilege creep

Mover thường khó đo hơn Joiner: người dùng có thể tiếp tục làm việc, vẫn còn một số quyền cũ hợp lệ cho dự án chuyển tiếp, và nhiều role cùng cấp một entitlement.

| Metric | Định nghĩa gợi ý | Giá trị quản trị |
|---|---|---|
| **Mover evaluation coverage** | Mover event trong cohort đã được đánh giá lại quyền theo policy / mọi Mover ảnh hưởng truy cập | Phát hiện event bỏ sót hoặc chưa tính lại role. |
| **Mover obsolete-grant revocation rate** | Grant hết căn cứ sau Mover đã được xác nhận thu hồi / tổng grant hết căn cứ cần gỡ | Đo kết quả thực tế, không chỉ đã gửi lệnh. |
| **Mover revocation latency** | Từ thời điểm grant không còn hợp lệ đến khi target xác nhận grant hết hiệu lực | Đo độ trễ quyền tồn dư theo risk tier. |
| **Privilege creep after Mover** | Quyền ngoài desired state còn tồn tại sau cửa sổ xử lý / tập quyền phải loại bỏ | Theo dõi tồn dư và aging. |
| **SoD conflict exposure** | Số Mover có thời đoạn giữ quyền xung đột vượt policy | Ưu tiên kiểm soát rủi ro, cần dữ liệu thời gian. |
| **Approved transition exceptions** | Ngoại lệ Mover còn hạn, có owner và biện pháp bù trừ / tổng ngoại lệ Mover | Đo chất lượng quản trị giai đoạn chuyển tiếp. |

### Không đánh đồng role bị gỡ với permission bị gỡ

Ví dụ `FINANCE_ANALYST` và `PROJECT_REPORT_READER` đều cấp `report:read`. Sau Mover, role Finance bị thu hồi nhưng role Project vẫn hợp lệ. **Entitlement `report:read` có thể vẫn tồn tại hợp lệ** nếu phạm vi và chính sách cho phép.

Metric phải tách:

1. **Role assignment revocation:** role cũ đã bị thu hồi chưa?
2. **Effective access compliance:** quyền hiệu lực sau thay đổi có còn đúng chính sách không?
3. **Grant provenance:** entitlement còn lại được cấp vì nguồn nào?

Đếm mọi permission còn có tên giống role cũ thành “privilege creep” sẽ tạo báo động sai; ngược lại chỉ đếm role bị xóa mà không xét direct grant sẽ bỏ sót rủi ro thật.

## 9. Metric cho Leaver: thu hồi được xác nhận

Với Leaver, thời điểm hợp đồng hoặc quan hệ kết thúc là mốc quan trọng; tuy nhiên cách đo phải xét event được báo trước, account scope, quyền trực tiếp và rủi ro từng đích.

### 9.1. Các chỉ số cốt lõi

| Metric | Định nghĩa và công thức ngắn | Cảnh báo khi diễn giải |
|---|---|---|
| **Leaver identity coverage** | Leaver từ nguồn có thẩm quyền liên kết được toàn bộ account trong inventory / tổng Leaver trong cohort | Không tự coi account chưa inventory là không tồn tại. |
| **Confirmed deprovision completion** | Leaver đã xác minh hoàn tất toàn bộ hành động bắt buộc / tổng Leaver trong cohort | Mẫu số bắt đầu từ HRIS/VMS, không từ queue đã xử lý. |
| **Target-level revoke success** | Action phải thu hồi được xác nhận ở đích / tổng action phải thu hồi | Có thể cao dù một số Leaver vẫn còn quyền tại một đích. |
| **Leaver verified revocation latency** | Từ mốc Leaver có hiệu lực đến thời điểm xác nhận hành động cuối cùng bắt buộc | Chỉ tính hoàn tất đầy đủ, theo dõi riêng pending. |
| **Overdue Leaver count** | Leaver có ít nhất một entitlement/account vượt ngưỡng thu hồi chưa xác nhận | Ưu tiên theo risk tier và thời gian tồn dư. |
| **Orphan access after Leaver** | Account/credential còn active không có căn cứ danh tính sau Leaver | Phải kiểm tra account local và quyền ngoài IdP. |
| **Emergency termination latency** | Thời gian xác nhận chặn các đường truy cập bắt buộc trong tình huống chấm dứt khẩn cấp | Scope/đường chặn có thể khác quy trình thông thường. |

### 9.2. Ví dụ hai chỉ số cho cùng một cohort

Trong tuần có **50 Leaver** với tổng **150 hành động thu hồi bắt buộc** trên các hệ thống. Có 147 hành động được xác nhận; 3 hành động tại ứng dụng legacy vẫn pending, thuộc **2 Leaver**.

- **Target-level revoke success = 147/150 = 98%**.
- **Confirmed deprovision completion = 48/50 = 96%**.
- **Overdue Leaver count** phụ thuộc ngưỡng xử lý, không thể suy chỉ từ số pending.

Không được báo “98% Leaver đã an toàn” vì 98% là tỷ lệ **action**, không phải tỷ lệ **danh tính đã hoàn tất**. Hai Leaver có hành động chưa xong vẫn cần owner xử lý và theo dõi rủi ro.

### 9.3. Quy trình Leaver có nhiều đích

~~~mermaid
flowchart TD
    L["HRIS / VMS<br/>Leaver + effectiveAt"] --> I["IAM xác định toàn bộ account và grant thuộc scope"]
    I --> P["Tính hành động bắt buộc<br/>IdP, SaaS, cloud, local, token"]
    P --> A["Phát actionId và retry có kiểm soát"]
    A --> V["Readback từng hệ thống đích"]
    V --> C{"Tất cả hành động bắt buộc đã xác minh?"}
    C -- "Không" --> O["Giữ pending / drift<br/>Cảnh báo + owner + aging"]
    O --> V
    C -- "Có" --> D["Leaver confirmed<br/>Đóng bằng chứng"]
~~~

**Một Leaver có thể có account bị khóa nhưng token đã phát hành vẫn còn hiệu lực**. Khả năng thu hồi phiên, refresh token hoặc credential phải được tính trong control scope theo thiết kế. Không thể tuyên bố mọi truy cập đã hết nếu chỉ đo trạng thái IdP và bỏ qua các kênh truy cập độc lập.

## 10. Metric về account inventory và identity source

Trước khi đo quyền có hợp lệ hay không, IAM phải biết **các account nào đang tồn tại và liên kết với danh tính nào**.

| Metric | Công thức gợi ý | Mục tiêu |
|---|---|---|
| **Account correlation coverage** | Số account trong inventory liên kết được identity/workload có nguồn hợp lệ / tổng account inventory | Phát hiện orphan và lỗi identity matching. |
| **Orphan account rate** | Account không có identity/service owner hợp lệ / tổng account inventory | Giảm tài khoản không có chủ thể chịu trách nhiệm. |
| **In-scope target discovery coverage** | Target đã inventory đầy đủ theo tiêu chí / tổng target phải quản trị | Phát hiện ứng dụng chưa kết nối. |
| **Account status mismatch** | Account actual state không khớp desired state / account đã có cả hai trạng thái | Đo drift; công bố tỷ lệ chưa có observed state. |
| **Duplicate identity candidate rate** | Hồ sơ bị nghi trùng khóa hoặc cùng chủ thể / hồ sơ được đánh giá | Yêu cầu xác minh, không tự gộp theo email. |
| **Unowned privileged accounts** | Privileged account không có owner/quan hệ hợp lệ | KRI ưu tiên cao. |
| **Identity source freshness** | Tuổi bản ghi/luồng cập nhật từ nguồn có thẩm quyền | Giúp xác định độ tin cậy của quyết định. |
| **Authority conflict count** | Thuộc tính có hai nguồn báo giá trị xung đột cần xử lý | Đánh giá chất lượng hợp đồng dữ liệu. |

### Định nghĩa orphan cần chặt chẽ

Một account có thể có email hoặc trường `createdBy` nhưng **chưa chắc có owner hợp lệ**. Đối với account nhân viên, cần liên kết với identity và quan hệ hiện hành; đối với service account, cần `serviceId` hoặc workload ID, owner dịch vụ và mục đích đã đăng ký.

Nên phân loại orphan:

- **Uncorrelated:** chưa liên kết được account tới identity/service record;
- **Owner invalid:** đã liên kết nhưng owner không còn hợp lệ;
- **Policy invalid:** liên kết có nhưng quan hệ hoặc lý do cấp quyền đã hết;
- **Unknown due to missing inventory:** chưa xác định được vì nguồn dữ liệu không đủ.

Không dùng duy nhất tỷ lệ `correlated / discovered` để kết luận độ bao phủ tốt, nếu một phần lớn SaaS hoặc cloud project chưa được quét inventory.

## 11. Metric về quyền, role model, RBAC/ABAC và SoD

Nhóm này tập trung vào **quyền hiệu lực** và khả năng giải thích: người dùng có quyền gì, đến từ đâu và còn phù hợp với chính sách không?

| Metric | Định nghĩa | Lưu ý |
|---|---|---|
| **Governed entitlement coverage** | Entitlement/grant có nguồn cấp, owner và policy/approval hợp lệ / tổng entitlement/grant trong inventory | Phân biệt quyền được gán với quyền hiệu lực. |
| **Direct grant exception rate** | Direct grant không có căn cứ hoặc ngoại lệ được phê duyệt / tổng direct grant phát hiện | Không mặc định mọi direct grant đều sai, nhưng phải giải thích được. |
| **Role owner coverage** | Role active có owner nghiệp vụ và kỹ thuật hợp lệ / tổng role active | Role không owner khó review và sửa mapping. |
| **Role mapping drift** | Mapping role → entitlement ở đích khác catalog đã duyệt | Một thay đổi role có thể ảnh hưởng hàng loạt account. |
| **Effective privilege drift** | Quyền hiệu lực vượt hoặc khác desired state theo policy / tập quyền được đánh giá | Cần tính nhóm lồng nhau, scope, inheritance, direct grant. |
| **SoD violation exposure** | Số trường hợp xung đột vai trò/quyền/giao dịch chưa xử lý | Đo cả thời gian tồn tại và rủi ro, không chỉ số lượng. |
| **ABAC enforcement coverage** | Action/resource cần kiểm tra ABAC có điểm thực thi hợp lệ / tổng action/resource cần bảo vệ | Không chỉ dựa vào claim SSO; API phải chặn sai tenant. |
| **Expired access still active** | Grant có expiry đã qua nhưng quyền ở đích vẫn hiện hữu | KRI về privilege creep. |

### Ví dụ entitlement coverage

Ứng dụng có 1.000 **grant hiện hữu** trong inventory. Trong đó 920 grant có role/policy hoặc request hợp lệ và owner, 50 grant cấp trực tiếp có ngoại lệ còn hạn và 30 grant chưa có căn cứ.

Nếu chính sách chấp nhận ngoại lệ được duyệt là **governed**, thì:

\[
\text{Governed grant coverage}=\frac{920+50}{1000}\times100\%=97\%.
\]

**Ungoverned grant count = 30**, nhưng vẫn phải tách **50 grant ngoại lệ** thành KRI riêng để tránh mục tiêu “đẩy mọi quyền ra ngoại lệ” làm đẹp chỉ số. Nếu 100 grant không đọc được từ API, kết quả phải kèm trạng thái **coverage incomplete**, không chỉ công bố 97%.

## 12. Metric cho approval và request fulfillment

Approval hỗ trợ cấp quyền có trách nhiệm, nhưng cần đo cả **quyết định hợp lệ** và **kết quả sau duyệt**:

| Metric | Mẫu đo phù hợp | Điều cần tránh |
|---|---|---|
| **Approval decision latency** | Từ request đủ điều kiện đến khi đủ bước phê duyệt hoặc có quyết định cuối | Không tính thời gian provisioning vào độ trễ duyệt nếu mục tiêu chỉ đo approver. |
| **Approval authority coverage** | Request được phê duyệt bởi approver đúng thẩm quyền / request được duyệt | Không chấp nhận tự duyệt trái chính sách. |
| **Overdue request ratio** | Request quá SLA chưa có quyết định / request đủ điều kiện cần quyết định | Không tự đánh dấu `APPROVED` khi hết hạn. |
| **Approved-to-confirmed latency** | Từ phê duyệt cuối đến khi target readback đúng quyền | Đo riêng lỗi SCIM/API. |
| **Fulfillment confirmation rate** | Request đã duyệt và đủ điều kiện có quyền thực tế được xác nhận / request cần thực thi | Không dùng HTTP ACK làm kết quả cuối. |
| **Post-approval invalidation count** | Request bị hủy vì identity/scope/policy đổi sau khi duyệt | Có thể phản ánh dữ liệu thay đổi tự nhiên hoặc process lag. |
| **Self-approval / SoD block count** | Lần bị chặn do xung đột approver hoặc entitlement | Không coi “không có block” đương nhiên là an toàn nếu thiếu kiểm tra. |

Nên phân tách theo loại quyền: quyền đọc thông thường, dữ liệu nhạy cảm, quản trị cloud, credential của workload và ngoại lệ. So sánh trung bình một request portal với một request production-admin có thể không có ý nghĩa.

## 13. Metric cho access review và recertification

**Review decision completion** và **remediation completion** là hai kết quả khác nhau:

\[
\text{Decision completion rate}=
\frac{\text{Review item có quyết định hợp lệ}}{\text{Tổng item phải được quyết định}}\times100\%.
\]

\[
\text{Remediation confirmation rate}=
\frac{\text{Action bắt buộc đã xác minh ở đích}}{\text{Tổng action bắt buộc từ quyết định review}}\times100\%.
\]

Ví dụ một chiến dịch có **120 review item**, 114 item đã có quyết định hợp lệ; trong các quyết định có 30 action Revoke/Modify bắt buộc, 24 action đã xác minh.

- **Decision completion = 114/120 = 95%**.
- **Remediation confirmation = 24/30 = 80%**.
- Còn 6 item chưa có quyết định và 6 action chưa xác nhận, cần owner, SLA và phân loại rủi ro.

Các metric bổ sung:

| Metric | Ý nghĩa |
|---|---|
| **Reviewer authority coverage** | Item được giao đúng người có quyền chứng nhận. |
| **Overdue review ratio** | Item chưa được quyết định trước due date. |
| **Remediation aging** | Thời gian action bị treo sau khi reviewer chọn Revoke/Modify. |
| **Repeated Keep without evidence** | Quyền rủi ro cao được chứng nhận Keep mà thiếu căn cứ hoặc reviewer không đủ authority. |
| **Campaign scope coverage** | Tỷ lệ entitlement thuộc kế hoạch đã được đưa vào chiến dịch. |
| **Expired exceptions reviewed** | Ngoại lệ đến hạn có review/thu hồi phù hợp, không mặc nhiên gia hạn. |

Một mục `KEEP` phải gắn với **đúng entitlement, tenant, role và snapshot version**. Nếu role đổi trong khi campaign diễn ra, review trên snapshot cũ phải được xác minh lại trước khi ghi nhận quyền hợp lệ.

## 14. Metric cho service account và workload identity

Tài khoản phi con người không đi theo một HRIS employee status duy nhất. Vì vậy không nên chỉ đo `employeeId` đã liên kết mà phải theo `serviceId`, `workloadId`, owner và môi trường.

| Metric | Định nghĩa | Rủi ro cần phát hiện |
|---|---|---|
| **Workload identity owner coverage** | Workload/service account có owner hợp lệ và còn hoạt động / tổng workload account | Robot thiếu người chịu trách nhiệm. |
| **Service identity purpose coverage** | Workload có service record, purpose và scope rõ / tổng workload identity | Quyền không giải thích được. |
| **Overprivileged workload rate** | Workload có entitlement vượt approved policy/least privilege / workload được đánh giá | Service principal được cấp quyền admin không cần thiết. |
| **Long-lived credential exposure** | Credential dài hạn không đáp ứng policy rotation/expiry / credential trong scope | Key tĩnh tồn tại quá lâu hoặc không rõ owner. |
| **Credential revocation verification** | Credential bị thu hồi có bằng chứng hết hiệu lực / credential cần thu hồi | Xóa record không đủ nếu key ở đích còn dùng được. |
| **Retired workload access drift** | Workload đã retired nhưng account/grant/credential vẫn hoạt động | Vòng đời dịch vụ kết thúc mà quyền còn tồn dư. |
| **Former-owner workload review completion** | Workload gắn với owner đã Leaver có owner mới và quyền/credential đã được rà soát / workload cần xử lý | Không tự xóa dịch vụ đang hoạt động nhưng cũng không bỏ quên rủi ro. |

Với credential, nên đo bằng **identifier, trạng thái và bằng chứng**; không đưa secret, private key, API key hoặc bearer token thô vào pipeline metric/log.

## 15. Metric cho IdP, SSO, SCIM và policy enforcement

Đây là nhóm đo **sức khỏe cơ chế thực thi**, không tự động đại diện cho an toàn IAM toàn diện.

| Thành phần | Metric hữu ích | Ý nghĩa và giới hạn |
|---|---|---|
| **IdP** | Account disable verification, security hold propagation latency | Khóa ở IdP không chứng minh mọi account local bị khóa. |
| **SSO** | Successful/failed authentication, MFA coverage theo risk tier, session invalidation evidence | Thành công đăng nhập không có nghĩa được ủy quyền tài nguyên; token ở app có thể còn hiệu lực. |
| **SCIM** | Provisioning request failure rate, retry age, target readback mismatch | Phân biệt accepted, applied và verified. |
| **IGA / provisioning orchestration** | Action backlog, workflow stuck, duplicate-event rate | Phát hiện mất event hoặc lỗi điều phối. |
| **RBAC role service** | Assignment drift, role mapping change impact, owner coverage | Role mapping sai có thể mở rộng quyền của nhiều người. |
| **ABAC / PDP-PEP** | Policy decision error rate, enforcement coverage, unexpected Permit/Deny anomaly | PDP trả Deny không đủ nếu API PEP vẫn cho hành động. |
| **PAM / JIT** | Privileged elevation duration, active-after-expiry, session audit coverage | Theo dõi quyền đặc biệt thực tế và thời gian tồn tại. |

Tỷ lệ `HTTP 2xx` hoặc `SCIM success` có ích cho vận hành, nhưng phải có metric **end-to-end confirmation** đối với các đường kiểm soát quan trọng, đặc biệt Leaver và thu hồi đặc quyền.

### Phân biệt availability với security outcome

Một SSO endpoint có thể đạt uptime cao trong khi policy phân quyền sai tenant; ngược lại hệ thống có thể chủ động từ chối cấp quyền khi thiếu thuộc tính nguồn và điều đó **không phải lỗi bảo mật**. Cần tách các lớp SLI và định nghĩa rõ tính đúng của decision.

## 16. Metric cho audit, evidence và reconciliation

Muốn tin dashboard, phải đo chính **chất lượng dữ liệu làm ra dashboard**.

| Metric | Cách đo gợi ý | Ý nghĩa |
|---|---|---|
| **Audit source coverage** | Nguồn/target trong scope có đường audit được kiểm thử / tổng nguồn/target cần thiết | Tránh blind spot. |
| **Required event completeness** | Event đủ loại/trường/correlation / event nghiệp vụ được kỳ vọng từ nguồn khác | Cần nguồn đối chiếu để phát hiện event chưa từng đến. |
| **Target evidence coverage** | Action cần readback có evidence hợp lệ / tổng action cần readback | Đo khả năng xác nhận trạng thái, không chỉ kết quả connector. |
| **Audit correlation completeness** | JML flow có đầy đủ source event, decision, action và target evidence / flow trong cohort | Khả năng truy vết end-to-end. |
| **Audit delivery freshness** | Độ trễ producer → central ledger, phân phối theo nguồn | Phát hiện collector/queue bị nghẽn. |
| **Inventory reconciliation freshness** | Thời gian từ lần quan sát cuối cho mỗi target | Tránh tin snapshot quá cũ. |
| **Unresolved drift aging** | Tuổi các finding chưa được xử lý, phân tầng theo risk tier | Ưu tiên quyền tồn dư thực tế. |
| **Audit integrity exceptions** | Số vi phạm tính toàn vẹn, collector mất heartbeat, truy cập trái quyền | Đo mức tin cậy của bằng chứng. |

### Không thể dùng chính log bị mất để chứng minh log đầy đủ

Nếu collector dừng, kho audit có thể không nhận thêm bản ghi nào và vẫn báo **100% bản ghi đã lưu đều hợp lệ**. Để phát hiện thiếu dữ liệu cần heartbeat, sequence gap, số lượng kỳ vọng từ nguồn nghiệp vụ độc lập, đối soát snapshot hoặc kiểm tra chủ động từ hệ thống đích.

Đối với metric bắt buộc có evidence, hãy công bố ba trạng thái: **confirmed**, **not confirmed** và **unknown/data unavailable**. Không gộp unknown thành success; nếu muốn tính tỷ lệ thành công, nêu rõ unknown nằm trong mẫu số hay trong thống kê chất lượng dữ liệu riêng, không che giấu nó.

## 17. Thiết kế SLI, SLO và cảnh báo theo mức độ rủi ro

Đặt ngưỡng không phải bước đầu tiên. Trước hết phải có **baseline**, hiểu phân phối thời gian và mức rủi ro, rồi cùng owner quyết định mục tiêu phù hợp.

Một quy trình:

1. Chọn đối tượng kiểm soát, ví dụ Leaver employee trong account scope.
2. Xác định **SLI** cụ thể: tỷ lệ Leaver có toàn bộ quyền bắt buộc được readback xác nhận trong thời hạn chính sách.
3. Phân tách theo risk tier, target và loại quan hệ; không trộn quyền đặc biệt với quyền thông thường nếu ngưỡng khác nhau.
4. Đo baseline từ dữ liệu đủ tin cậy; công bố các target chưa có inventory.
5. Xác định **SLO** và thời gian cảnh báo, được Security/Business owner phê duyệt.
6. Định nghĩa **ai xử lý cảnh báo**, kênh escalation và điều kiện đóng sau khi khắc phục.
7. Đánh giá lại mục tiêu khi account scope hoặc nguồn dữ liệu thay đổi.

### Vì sao nên dùng percentile?

Một batch có 99 hành động hoàn tất trong 1 phút nhưng 1 hành động mất 3 giờ có **trung bình gần 2,8 phút**. Giá trị trung bình có vẻ tốt, song một account đặc quyền có thể tồn dư rất lâu. Vì vậy nên dùng:

- **P50:** thời gian điển hình, hỗ trợ nhận diện xu hướng chung;
- **P90/P95/P99:** phần đuôi phân phối, hỗ trợ đánh giá những ca xử lý chậm;
- **Max/oldest pending:** ca cực trị và item còn mở;
- **Count overdue:** số đối tượng vượt ngưỡng đã được phê duyệt;
- **Coverage / unknown:** số đối tượng không có đủ dữ liệu để tính.

Percentile chỉ tính trên các hành động **đã hoàn tất** có thể đẹp giả tạo nếu rất nhiều hành động vẫn pending. Luôn hiển thị **completed count, pending count, overdue count** cạnh phân phối latency.

### Alert không chỉ từ tỷ lệ tổng

Ví dụ 99,9% hành động đã hoàn tất nhưng một quyền cloud admin của Leaver chưa được gỡ. Tùy chính sách, **một trường hợp critical** đã đủ cần cảnh báo ngay. Dùng rule theo risk tier và đối tượng có tác động cao, không chỉ đợi tỷ lệ tổng vượt ngưỡng.

## 18. Thiết kế dashboard phục vụ từng nhóm người dùng

Một dashboard hữu ích cần hỗ trợ **đi từ bức tranh toàn cảnh xuống từng account/grant/action có bằng chứng**:

| Người dùng | Nên nhìn thấy | Thao tác tiếp theo |
|---|---|---|
| **Program owner** | Coverage, JML outcome, drift trend, review remediation, ngoại lệ | Ưu tiên đầu tư và kiểm soát. |
| **IAM operations** | Pending/failed actions, connector backlog, event lag, oldest unresolved | Retry, xử lý sự cố, liên hệ owner đích. |
| **Security / risk** | Unrevoked privileged access, SoD, orphan, expired credential, blind spots | Ưu tiên giảm rủi ro và điều tra. |
| **Application/data owner** | Entitlement chưa có căn cứ, review item, target reconciliation | Xác nhận phạm vi quyền và quyết định xử lý. |
| **Internal audit** | Coverage theo scope, policy/version, evidence completeness, ngoại lệ, timeline JML | Kiểm tra bằng chứng và giới hạn của kết luận. |

~~~mermaid
flowchart TD
    A["Program Dashboard<br/>Coverage - Correctness - Timeliness - Assurance"] --> B["Theo identity type / risk tier"]
    B --> C["Theo target system / tenant"]
    C --> D["Theo cohort Joiner / Mover / Leaver"]
    D --> E["Danh sách identity / account / grant / action"]
    E --> F["Evidence: sourceEventId - policy - actionId - targetReadback"]
    F --> G["Owner / ticket / SLA / remediation"]
~~~

### Không giấu dữ liệu chưa bao phủ

Dashboard nên có phần riêng: **systems in scope**, **systems discovered**, **systems integrated**, **systems with target readback** và **systems unavailable**. Nếu CRM đã tích hợp đầy đủ nhưng ERP local không có API, không nên gộp ERP vào trạng thái “không có lỗi” mà phải đánh dấu **unmeasured** hoặc dùng bằng chứng thủ công đã được chấp thuận.

Tránh đưa PII hoặc thông tin bí mật lên biểu đồ rộng quyền xem. Chỉ người được phân quyền mới truy cập danh sách identity/account chi tiết và nội dung bằng chứng.

## 19. Thiết kế pipeline đo lường và chất lượng dữ liệu

~~~mermaid
flowchart LR
    HR["Nguồn vòng đời<br/>HRIS / VMS / Service catalog"] --> EV["Event ledger<br/>ID + version + effectiveAt"]
    EV --> MODEL["Dữ liệu chuẩn hóa<br/>Identity / account / entitlement"]
    TARGET["IdP / SCIM / SaaS / Cloud / PAM"] --> OBS["Target observations<br/>ObservedAt + evidence"]
    OBS --> MODEL
    POLICY["Role / policy / approval / review"] --> MODEL
    MODEL --> QA["Quality checks<br/>Coverage + timeliness + keys"]
    QA --> MART["Metric mart<br/>Versioned definitions"]
    MART --> DASH["Dashboard + SLO alerts"]
    MART --> AUDIT["Audit / trace<br/>Drill-down đến action"]
~~~

**Các khóa liên kết** cần nhất quán:

- `sourceSystem + sourceRecordId` cho quan hệ nghiệp vụ;
- `identityId` hoặc `workloadId` ổn định cho danh tính;
- `targetSystemId + tenantId + nativeAccountId` cho account tại đích;
- `grantId` hoặc entitlement reference có provenance cho quyền;
- `sourceEventId`, `correlationId`, `actionId` và `evidenceId` cho đường thực thi.

### Kiểm thử dữ liệu bắt buộc

1. **Uniqueness:** mỗi event/action có định danh phù hợp, retry không bị đếm thành event nghiệp vụ mới.
2. **Referential integrity:** action phải tham chiếu identity/account và target đã xác định; trường thiếu cần vào hàng lỗi.
3. **Temporal consistency:** mốc thời gian có offset, kiểm tra clock skew và sự kiện future effective.
4. **Authority validation:** employment status lấy từ nguồn có thẩm quyền; security hold không bị HRIS ghi đè.
5. **Scope completeness:** kiểm tra target/tenant trong danh sách bắt buộc và trạng thái quét inventory.
6. **Freshness:** tuổi snapshot và event pipeline nằm trong ngưỡng cho phép hay được đánh dấu stale.
7. **State semantics:** `REQUESTED`, `ACKNOWLEDGED`, `CONFIRMED`, `FAILED` không bị gộp.
8. **Denominator reconciliation:** đối chiếu số Leaver gốc từ HRIS/VMS với số event mà metric mart nhận.
9. **Late-arriving updates:** event hoặc readback đến sau kỳ báo cáo phải có cách backfill/restate theo version.
10. **Privacy/security:** pipeline metric không sao chép password, secret, token hoặc toàn bộ PII không cần thiết.

## 20. Ví dụ dữ liệu và truy vấn metric

Giả sử kho đo lường có các bảng logic:

- `lifecycle_events`: `event_id, source_system, subject_relation_id, event_type, effective_at, published_at`;
- `required_revocation_actions`: `action_id, event_id, target_system_id, account_id, required_at`;
- `action_status`: `action_id, latest_state, target_verified_at`.

Để tính tỷ lệ **action thu hồi Leaver được xác nhận** theo cohort ngày hiệu lực, có thể dùng truy vấn minh họa:

~~~sql
-- SQL minh họa; cấu trúc bảng và dialect tùy nền tảng.
WITH cohort AS (
    SELECT DISTINCT event_id
    FROM lifecycle_events
    WHERE event_type IN ('EMPLOYMENT_TERMINATED', 'CONTRACT_TERMINATED')
      AND effective_at >= TIMESTAMP '2026-11-01 00:00:00'
      AND effective_at <  TIMESTAMP '2026-12-01 00:00:00'
),
required AS (
    SELECT a.action_id, a.event_id
    FROM required_revocation_actions a
    JOIN cohort c ON c.event_id = a.event_id
)
SELECT
    COUNT(*) AS required_actions,
    SUM(CASE WHEN s.latest_state = 'CONFIRMED'
                   AND s.target_verified_at IS NOT NULL
             THEN 1 ELSE 0 END) AS confirmed_actions,
    100.0 * SUM(CASE WHEN s.latest_state = 'CONFIRMED'
                          AND s.target_verified_at IS NOT NULL
                     THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
        AS confirmed_action_pct
FROM required r
LEFT JOIN action_status s ON s.action_id = r.action_id;
~~~

**Giới hạn quan trọng:** truy vấn chỉ tính các `required_revocation_actions` đã được lập. Nếu một Leaver không sinh action vì lỗi pipeline, action thiếu sẽ không có trong bảng và tỷ lệ có thể bị thổi phồng. Muốn đánh giá **Leaver-level completion**, phải xuất phát từ **cohort nguồn** và kiểm tra đủ target/account/credential bắt buộc đã được lập action. Không thể sửa lỗ hổng này chỉ bằng `COUNT(*)` trên bảng action.

### Giả mã đếm Leaver hoàn tất đúng nghĩa

~~~text
for each effectiveLeaver in authoritativeSourceCohort:
    requiredTargets = resolveRequiredAccountsAndCredentials(
        effectiveLeaver,
        accountScopeVersion
    )

    if requiredTargets.isUnknownOrIncomplete:
        mark(effectiveLeaver, DATA_QUALITY_EXCEPTION)
        continue

    observations = loadTargetEvidence(requiredTargets)
    if allRequiredRevocationsConfirmed(observations):
        mark(effectiveLeaver, CONFIRMED)
        record(latency = latestVerifiedAt(observations)
                         - effectiveLeaver.effectiveAt)
    else:
        mark(effectiveLeaver, NOT_CONFIRMED)
        recordPendingOrOverdueTargets()
~~~

Trong thực tế, phải xử lý Leaver có **không có account thuộc scope**, các mốc trước ngày hiệu lực, mối quan hệ còn hiệu lực khác và ngoại lệ hợp lệ. Không được mặc định người có nhiều quan hệ bị mất mọi quyền chỉ vì một hợp đồng kết thúc; metric cần dựa trên **desired state và account scope đã được quy định**.

## 21. Quản trị thay đổi định nghĩa metric

Một chỉ số có thể tăng hoặc giảm chỉ vì **công thức thay đổi**, không phải IAM thật sự tốt hay xấu hơn.

Ví dụ trước tháng 10 chỉ đo IdP và hai SaaS; tháng 11 thêm ERP local và ba cloud project. Tỷ lệ deprovision đúng hạn giảm từ 99% xuống 93%. Điều đó có thể phản ánh **độ bao phủ tốt hơn đã phát hiện rủi ro trước đây không thấy**. Báo cáo phải nêu phiên bản account scope, số hệ thống bổ sung và tác động lên mẫu số.

Quản trị metric tương tự policy:

1. Có `metricId` và version.
2. Owner phê duyệt sửa công thức/mẫu số và định nghĩa trạng thái.
3. Ghi lịch sử thay đổi, phạm vi tác động và mốc bắt đầu hiệu lực.
4. Đánh dấu điểm gãy chuỗi thời gian; backfill dữ liệu nếu có thể và hợp lý.
5. Không đặt hai số khác định nghĩa cạnh nhau mà không có chú thích.
6. Phân quyền truy cập dashboard và dữ liệu theo trách nhiệm.

### Các hành vi làm KPI đẹp nhưng tăng rủi ro

- Chỉ đo hệ thống tích hợp tốt, loại ứng dụng legacy lỗi khỏi mẫu số.
- Tính “thành công” khi action được đưa vào queue thay vì đích đã xác nhận.
- Đánh dấu ngoại lệ quá hạn là “đã xử lý” mà không có biện pháp kiểm soát.
- Đếm Leaver theo số account đã xử lý, bỏ qua người có account chưa được inventory.
- Chỉ báo độ trễ của các action thành công, không cho thấy những action đang treo.
- Gộp quyền đặc biệt vào trung bình chung để làm mất tín hiệu của ca rủi ro cao.
- Thu hồi entitlement indiscriminately để đạt KPI trong khi phá quyền hợp lệ ở role khác.

Vì vậy mỗi KPI nên có **guardrail metric** đi kèm. Ví dụ tăng Joiner readiness phải đi cùng giảm over-provision; tăng revoke success phải đi cùng kiểm tra không thu hồi nhầm quyền còn hợp lệ.

## 22. Tình huống tổng hợp: xây dựng dashboard JML cho doanh nghiệp

Giả sử tổ chức có:

- HRIS quản lý nhân viên, VMS quản lý nhà thầu;
- IdP hỗ trợ SSO và quản lý group cơ sở;
- hai SaaS có SCIM, một ERP local và cloud IAM;
- service catalog quản lý workload và người chịu trách nhiệm;
- role catalog với RBAC/ABAC, approval service và công cụ access review.

Trong một cohort tháng:

| Dữ kiện | Giá trị |
|---|---:|
| Joiner có hiệu lực | 200 |
| Joiner có đủ baseline đúng giờ | 190 |
| Mover thay đổi quyền | 80 |
| Mover có grant cũ hết hiệu lực cần gỡ | 160 grant |
| Grant cũ đã xác nhận thu hồi | 152 |
| Leaver có hiệu lực | 50 |
| Leaver đã xác nhận hoàn tất toàn bộ hành động bắt buộc | 48 |
| Hành động thu hồi Leaver bắt buộc | 150 |
| Hành động Leaver đã xác nhận | 147 |
| Review item phải quyết định | 120 |
| Review item có quyết định hợp lệ | 114 |
| Remediation action bắt buộc từ review | 30 |
| Remediation được xác nhận tại đích | 24 |

### Tính các tỷ lệ chính

| Metric | Công thức | Kết quả |
|---|---|---:|
| Joiner baseline readiness | `190 / 200` | **95%** |
| Mover grant revoke confirmation | `152 / 160` | **95%** |
| Leaver identity-level completion | `48 / 50` | **96%** |
| Leaver target-action confirmation | `147 / 150` | **98%** |
| Review decision completion | `114 / 120` | **95%** |
| Review remediation confirmation | `24 / 30` | **80%** |

Kết quả cần đọc cùng **mẫu số và độ bao phủ**. Nếu ERP local không có target readback đáng tin, các tỷ lệ trên phải ghi rõ limitation hoặc giảm mức khẳng định. Nếu 8 grant còn tồn sau Mover thuộc hệ thống production nhạy cảm, “95%” không đủ để quyết định ưu tiên; phải đi vào danh sách rủi ro theo từng account/grant.

### Ba câu hỏi dashboard phải trả lời tiếp

1. **Những ai đang chịu rủi ro?** Hai Leaver chưa hoàn tất là identity nào, ở hệ thống/tenant nào, quyền gì, bao lâu và owner nào nhận xử lý?
2. **Lỗi xảy ra ở đâu?** Event bị nhận trễ, policy chưa sinh action, connector lỗi, hay target đã báo ACK nhưng vẫn còn entitlement?
3. **Độ tin cậy của số đo ra sao?** Bao nhiêu target có inventory đầy đủ, bao nhiêu action có readback, bao nhiêu mốc thời gian đang missing/stale?

Một metric **không thể dẫn đến danh sách đối tượng và bằng chứng cần hành động** thường chưa đủ hữu ích cho vận hành IAM.

## 23. Lộ trình triển khai metric program

| Giai đoạn | Công việc | Sản phẩm bàn giao |
|---|---|---|
| **1. Chọn mục tiêu** | Thống nhất 5–10 câu hỏi kiểm soát quan trọng về JML, quyền, rủi ro | Objective tree và danh sách metric ưu tiên. |
| **2. Xác định scope** | Liệt kê identity/account/target/tenant, phân loại rủi ro, nguồn có thẩm quyền | Scope matrix được duyệt. |
| **3. Đặc tả metric** | Viết công thức, mẫu số, timestamp, owner, xử lý missing data | Metric catalog versioned. |
| **4. Chuẩn hóa dữ liệu** | Event IDs, native account keys, grant provenance, target evidence, policy refs | Data contract và mapping. |
| **5. Thiết lập đối soát** | Lấy snapshot quyền thực tế, phát hiện drift, kiểm tra source completeness | Reconciliation và quality checks. |
| **6. Tạo dashboard thử nghiệm** | Hiển thị số liệu theo risk tier, target và cohort, drill-down đến action | Báo cáo baseline, chưa gán nhãn SLO khi chưa duyệt. |
| **7. Thử nghiệm tình huống lỗi** | Leaver connector timeout, duplicate event, local account, token còn hiệu lực | Kết quả test, gap và phương án sửa. |
| **8. Phê duyệt SLO/cảnh báo** | Chủ chương trình và Security thống nhất ngưỡng, on-call, escalation | Runbook xử lý vi phạm. |
| **9. Vận hành/điều chỉnh** | Giám sát coverage, độ trễ, KPI quality và thay đổi account scope | Dashboard định kỳ và lịch sử version. |

### Bộ metric tối thiểu cho giai đoạn đầu

Nếu chưa đủ nguồn lực, có thể ưu tiên một bộ **ít nhưng đáng tin**:

1. **Account/target inventory coverage** — biết đang nhìn thấy phần nào của hệ thống.
2. **Joiner baseline readiness** — đúng người, đúng thời điểm.
3. **Mover obsolete-access confirmed revocation** — quyền cũ được gỡ và kiểm chứng.
4. **Leaver identity-level verified completion + latency + overdue count** — kết quả thu hồi thực tế.
5. **Privileged/orphan/unowned access count** — rủi ro cần xử lý ngay.
6. **Review remediation confirmation** — quyết định thu hồi đã thành sự thật ở đích.
7. **Audit evidence and reconciliation coverage** — có tin được các con số trên không.

Danh sách này là điểm bắt đầu, không thay cho metric hợp đồng, SoD, tài khoản dịch vụ và policy đặc thù theo rủi ro của từng tổ chức.

## 24. Các lỗi thiết kế metric thường gặp

1. **Không ghi rõ đơn vị đo:** tỷ lệ theo identity bị báo như tỷ lệ theo action hoặc account.
2. **Lấy queue xử lý thành công làm mẫu số:** event bị mất và account chưa discovery không xuất hiện.
3. **Đánh đồng `sentAt` với `verifiedAt`:** biến “đã phát lệnh” thành “đã thu hồi”.
4. **Chỉ tính những ca đã thành công:** các action pending rất lâu bị loại khỏi latency.
5. **Đo trung bình nhưng không xem đuôi phân phối:** một quyền production còn tồn tại hàng giờ bị che khuất.
6. **Gộp mọi mức rủi ro:** báo số toàn công ty tốt trong khi privileged access có lỗi nghiêm trọng.
7. **Không đo accuracy cùng tốc độ:** cấp đủ quyền nhưng cấp thừa đặc quyền.
8. **Coi tài khoản có email là đã có owner:** bỏ qua orphan account và non-human identity.
9. **Không phân biệt grant và effective permission:** role bị gỡ nhưng quyền còn được cấp trực tiếp hoặc ngược lại.
10. **Review completion thay cho remediation:** người duyệt đã bấm Revoke nhưng ứng dụng chưa thu hồi.
11. **Không giám sát dữ liệu thiếu:** collector dừng vẫn vẽ “100% events valid”.
12. **Thay định nghĩa mà không version:** chuỗi KPI tăng giảm do thay mẫu số chứ không do cải thiện hệ thống.
13. **Không phân quyền dữ liệu metric:** dashboard làm lộ danh tính hoặc hành vi nhạy cảm không cần thiết.
14. **Không gắn owner và hành động khi vượt ngưỡng:** báo cáo đỏ kéo dài nhưng không có ai chịu trách nhiệm.
15. **Tối ưu KPI bằng cách loại hệ thống khó:** mức đo đẹp lên trong khi vùng quyền truy cập chưa kiểm soát tăng.

## 25. Bài tập thực hành: thiết kế metric catalog và dashboard IAM

Một doanh nghiệp có HRIS, VMS, IdP/SSO, ba SaaS, ERP local, cloud production và các service account CI/CD. Một số ứng dụng hỗ trợ SCIM, một ứng dụng chỉ có thao tác thủ công. Ban lãnh đạo muốn đo **chất lượng tự động hóa JML và mức độ giảm quyền tồn dư**, trong khi Security cần nhìn rõ các quyền privileged và sự cố connector.

Hãy thực hiện:

1. **Viết metric catalog** tối thiểu tám metric bao phủ Joiner, Mover, Leaver, inventory/orphan, quyền đặc biệt, review và audit. Mỗi metric nêu `metricId`, đơn vị, mẫu số, tử số, nguồn, mốc thời gian, owner, phân nhóm và cách xử lý unknown.
2. **Phân biệt Leaver completion theo identity và theo action.** Với 50 Leaver, 150 action, 147 confirmed nhưng còn 2 Leaver có action pending, tính hai tỷ lệ và giải thích vì sao khác nhau.
3. **Thiết kế độ trễ JML** dùng `effectiveAt`, `receivedAt`, `sentAt`, `verifiedAt`; giải thích trường hợp event đến trước thời điểm hiệu lực hoặc readback đến muộn.
4. **Viết một metric contract YAML** cho `iam.mover.obsolete_access_revocation` với phạm vi quyền, nguồn role/policy và target readback.
5. **Đề xuất dashboard ba tầng**: toàn chương trình → theo target/risk → theo identity/action/evidence.
6. **Xử lý hệ thống legacy không có API readback:** chỉ rõ điều có thể đo, bằng chứng thủ công được chấp nhận và chỉ số nào phải đánh dấu chưa xác minh.
7. **Thiết kế guardrail** cho Joiner readiness để ngăn cấp thừa, và cho Leaver speed để không đánh dấu success khi chỉ có ACK.
8. **Nêu tám kiểm thử dữ liệu:** duplicate event, missing source ID, cross-tenant account, future effective date, connector retry, quyền trực tiếp, target không có readback, collector downtime.
9. **Chọn hai SLO đề xuất**, kèm lý do rủi ro, cách lấy baseline, phương pháp phê duyệt và on-call xử lý khi vi phạm; không coi ngưỡng mẫu là tiêu chuẩn chung.
10. **Mô tả cách version metric** khi doanh nghiệp bổ sung một SaaS và ERP local vào account scope.

### Tiêu chí nghiệm thu

Thiết kế metric được xem là đủ rõ để triển khai khi:

- **Mỗi chỉ số trả lời một câu hỏi kiểm soát**, có owner, mẫu số, đơn vị, cohort và phạm vi nhất quán.
- **Dữ liệu nguồn có thẩm quyền** được phân biệt với trạng thái mong muốn và quyền thực tế tại đích.
- **Joiner–Mover–Leaver** dùng mốc thời gian, account scope và bằng chứng xác nhận phù hợp.
- **Account, grant, role, entitlement và identity** không bị đếm lẫn nhau.
- **Sự kiện thiếu, event trùng, hệ thống chưa tích hợp và action pending** không bị loại khỏi báo cáo một cách im lặng.
- **Metric tốc độ** đi kèm kiểm tra đúng quyền, least privilege và SoD.
- **Đặc quyền, workload, review, credential và audit evidence** có chỉ số rủi ro tương ứng.
- **SLO/cảnh báo** dựa trên baseline và phân loại rủi ro, có owner và runbook xử lý.
- **Dashboard drill-down được** tới event, policy/version, action và target evidence, đồng thời bảo vệ dữ liệu nhạy cảm.
- **Phiên bản định nghĩa và phạm vi** được quản trị để so sánh xu hướng có ý nghĩa.

**Xác định metric là thiết kế cách chứng minh chương trình IAM đang làm đúng việc, đúng lúc và trong đúng phạm vi.** Khi dữ liệu nguồn, quyền thực tế, thời điểm hiệu lực, bằng chứng thu hồi và mẫu số được quản trị chặt chẽ, các con số không chỉ phục vụ báo cáo mà còn giúp phát hiện quyền truy cập tồn dư, sửa lỗ hổng JML và ưu tiên cải tiến IAM dựa trên rủi ro thực.
