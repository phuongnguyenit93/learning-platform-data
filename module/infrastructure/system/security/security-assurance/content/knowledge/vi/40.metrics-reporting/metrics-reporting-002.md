# KPI bảo mật: đo hiệu lực security controls và báo cáo security assurance có bằng chứng

**KPI bảo mật (Security Key Performance Indicator)** là chỉ số được lựa chọn để theo dõi mức độ thực hiện một **mục tiêu bảo mật hoặc kết quả vận hành quan trọng** trong một phạm vi và kỳ đo xác định. KPI giúp trả lời những câu hỏi như: tổ chức đang phát hiện sự cố đủ sớm không, những tài sản quan trọng có được bảo vệ và kiểm thử không, các phát hiện nghiêm trọng có thực sự được khắc phục đúng hạn không, và những security controls thiết yếu có tiếp tục hoạt động sau mỗi thay đổi hệ thống không?

KPI chỉ đáng tin khi **định nghĩa rõ dữ liệu đầu vào, tử số, mẫu số, thời điểm đo, phạm vi áp dụng, giả định, giới hạn và hành động sẽ thực hiện khi chỉ số vượt ngưỡng**. Một dashboard đầy con số đẹp nhưng loại bỏ các hệ thống chưa được giám sát có thể làm giảm khả năng nhận biết rủi ro thay vì cải thiện bảo mật.

Bài học thuộc chương **Metrics và reporting** của module **SECURITY_SECURITY_ASSURANCE**. Mục tiêu của module là xây dựng cách đánh giá **có bằng chứng** rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit và khắc phục phát hiện; đồng thời tổ chức security assurance liên tục trong phát triển và vận hành. Vì vậy, bài này xem KPI không chỉ là công cụ trình bày hiệu suất, mà còn là một phần của chuỗi **security objective → control assertion → measurement → evidence → quyết định rủi ro → hành động → retest**.

Một nguyên tắc xuyên suốt: **KPI tốt hỗ trợ quyết định, nhưng không tự thay thế điều tra, đánh giá rủi ro, kiểm toán hoặc bằng chứng về hiệu lực control**.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **KPI**, **KRI** (Key Risk Indicator), **KCI** (Key Control Indicator), metric kỹ thuật, SLA/SLO và chỉ số tuân thủ.
2. Xây bộ KPI theo mục tiêu bảo mật và threat/risk scenario, thay vì chọn các số dễ thu thập hoặc dễ làm đẹp.
3. Viết **metric specification** có công thức, unit, population, nguồn dữ liệu, thời gian, owner, quality gates, ngưỡng và hành động.
4. Đo hiệu lực các mảng quan trọng: asset coverage, IAM, vulnerability management, detection, incident response, logging, backup/DR, third-party assurance và audit findings.
5. Phân biệt các loại thời gian như **MTTD**, **MTTA**, **MTTC**, **MTTR** bằng những mốc được công bố rõ.
6. Thiết kế tỷ lệ coverage mà **mẫu số lấy từ inventory độc lập**, không chỉ từ các đối tượng đã được kết nối công cụ.
7. Phân tích cách missing data, sample bias, false positive, false negative, timestamp drift và dữ liệu đến muộn làm sai KPI.
8. Trình bày dashboard cho SOC, engineering, service owner, lãnh đạo và audit mà không che khuất rủi ro trọng yếu.
9. Xác định leading/lagging indicators, diễn giải xu hướng và tránh hiện tượng “tối ưu số liệu nhưng làm yếu bảo mật”.
10. Gắn KPI với finding, remediation, kiểm thử lại và continuous assurance.

## 2. KPI bảo mật là gì, và khác các thước đo liên quan ra sao?

### 2.1. KPI phải phản ánh mục tiêu

Giả sử mục tiêu là **giảm nguy cơ lạm dụng tài khoản quản trị trong production**. Có thể đo:

- Số lượng tài khoản quản trị trong scope được kiểm kê và có owner.
- Tỷ lệ đường đăng nhập quản trị được xác minh enforce MFA.
- Số ngoại lệ MFA quá hạn, đặc biệt trên tài sản quan trọng.
- Thời gian từ khi một privileged identity mới được tạo đến lúc control được kiểm chứng.
- Số bài test bypass/authentication bị fail hoặc chưa kiểm.
- Số sự cố truy cập trái phép đã được xác nhận trong kỳ.

Không phải tất cả đều là KPI chính. Tổ chức cần chọn **một số chỉ số dẫn đến hành động cụ thể**, rồi giữ metric chi tiết để điều tra nguyên nhân.

### 2.2. Phân biệt các loại chỉ số

| Thuật ngữ | Mục đích | Ví dụ | Giới hạn |
|---|---|---|---|
| **Metric** | Bất kỳ phép đo có định nghĩa | 120 tài khoản privileged | Chỉ là số đếm, chưa biết tốt/xấu |
| **KPI** | Theo dõi hiệu suất thực hiện mục tiêu trọng yếu | 98% đường privileged access đã được xác minh MFA | Không nói về các mục tiêu ngoài phạm vi |
| **KRI** | Cảnh báo mức phơi nhiễm/rủi ro đang tăng | Số tài khoản đặc quyền không có MFA trên hệ thống critical | Có thể là chỉ báo thay thế, không trực tiếp đo xác suất tổn thất |
| **KCI** | Theo dõi thiết kế/vận hành của một control | Tỷ lệ control test PASS trên các đơn vị phải kiểm | Một control đạt không chứng minh tổng hệ thống an toàn |
| **SLA** | Cam kết mức dịch vụ hoặc thời hạn theo thỏa thuận | Khắc phục finding Critical theo hạn đã phê duyệt | Là yêu cầu/cam kết, không phải số đo đạt được |
| **SLO** | Mục tiêu vận hành đo lường được | 99% alert critical được route trong thời hạn mục tiêu | Phải định nghĩa đúng population và cửa sổ |
| **KPI compliance** | Theo dõi việc đáp ứng yêu cầu trong phạm vi | Tỷ lệ control assertions mandatory đã xác minh đạt | Chưa đủ để kết luận toàn bộ nghĩa vụ pháp lý |
| **Outcome/impact metric** | Đo hậu quả hoặc kết quả đã xảy ra | Số sự cố gây gián đoạn đã xác nhận | Sự cố hiếm, khả năng quan sát không đồng đều |

Các nhãn KPI/KRI/KCI có thể giao nhau tùy chương trình. Quan trọng hơn tên gọi là **phép đo đại diện cho điều gì và hỗ trợ quyết định nào**.

### 2.3. Leading và lagging indicators

**Leading indicators (chỉ báo sớm)** phản ánh trạng thái hoặc hành vi có thể báo hiệu rủi ro sắp xuất hiện: coverage MFA, thiết bị thiếu EDR, backlog critical vulnerabilities, số rule detection không được test.

**Lagging indicators (chỉ báo sau)** phản ánh kết quả đã xảy ra: incident severity, thời gian containment thực tế, data loss đã xác nhận, breach of SLA hoặc downtime do sự cố.

| Leading indicator | Lagging indicator liên quan | Không nên suy diễn |
|---|---|---|
| MFA coverage có retest | Sự cố dùng credential bị chiếm | MFA coverage cao không bảo đảm không có account compromise |
| Detection test pass rate | MTTD của incident đã xác nhận | Test case PASS không chứng minh nhận biết mọi kỹ thuật tấn công |
| Patch SLA adherence | Sự cố khai thác lỗ hổng đã biết | Không có exploit được ghi nhận chưa chứng minh không có exploit |
| Backup restore success | Thời gian phục hồi sau sự cố thật | Restore test trên dataset nhỏ chưa chứng minh production RTO |
| Log source health/coverage | Thời gian điều tra được hỗ trợ bởi evidence | Heartbeat không chứng minh mọi event class được thu |

Một dashboard cân bằng thường cần cả **leading, lagging và chỉ số chất lượng đo**. Nếu chỉ báo sau thấp vì hệ thống không phát hiện được sự cố, tổ chức có thể hiểu lầm rủi ro đang giảm.

### 2.4. Các dạng metric

- **Count:** số finding, tài sản, ngoại lệ, incident. Cần phân tổ và kỳ.
- **Ratio/rate:** PASS / required; incident / exposure time; remediation đúng hạn / số cần xử lý.
- **Duration:** thời gian từ mốc A đến mốc B, thường xem median/percentiles.
- **Distribution:** phân phối độ tuổi finding, ingest lag, time to detect, theo severity.
- **Threshold/exception:** số đơn vị vượt hạn, vi phạm critical gates hoặc nguồn mất dữ liệu.
- **Coverage:** bao nhiêu phần của population bắt buộc được đo và đạt.
- **Risk-weighted view:** tổ hợp theo criticality; cần công bố trọng số và vẫn giữ chi tiết từng nhóm.

Số tổng có thể hữu ích để theo dõi khối lượng nhưng dễ che nhóm nguy cơ cao. Ví dụ, 1.000 máy đạt baseline không bù cho một máy quản trị trung tâm có đường truy cập nguy hiểm.

## 3. Thiết kế KPI theo mục tiêu và quyết định

### 3.1. Bắt đầu từ câu hỏi, không từ biểu đồ

Một quy trình lựa chọn KPI:

1. Xác định **security objective hoặc risk scenario**: muốn giảm sự kiện nào hoặc chứng minh control nào?
2. Chỉ ra **quyết định** người nhận phải đưa ra: đầu tư, ưu tiên sửa, kích hoạt incident, mở rộng telemetry hay điều chỉnh policy?
3. Mô tả **control assertions** có thể kiểm thử, ví dụ mọi cloud account production gửi audit log.
4. Chọn những **đơn vị đo** liên quan trực tiếp: service × control, asset × control, detection scenario × environment.
5. Xây công thức, population, kỳ, scope và phương pháp lấy evidence.
6. Định nghĩa **ngưỡng hành động** và ai chịu trách nhiệm khi fail.
7. Kiểm tra quality gates: asset ngoài inventory, log trễ, dữ liệu thiếu, test chưa chạy.
8. Đánh giá khả năng gây hiểu lầm và những cách có thể “game” số.
9. Chạy thử trên dữ liệu và cải tiến định nghĩa trước khi đưa lên dashboard.
10. Review khi môi trường, threat model hoặc risk appetite thay đổi.

### 3.2. Mối liên kết từ rủi ro đến KPI

~~~mermaid
flowchart LR
    R["Rủi ro / mục tiêu bảo mật"] --> O["Security objective"]
    O --> C["Control + assertion"]
    C --> T["Test / event / evidence"]
    T --> M["Metric có population và kỳ"]
    M --> K["KPI / KRI / threshold"]
    K --> DEC["Quyết định / hành động"]
    DEC --> RET["Remediation + retest"]
    RET --> C
    T --> QUAL["Data quality / limitation"]
    QUAL --> M
~~~

Ví dụ chuỗi truy vết:

| Thành phần | Ví dụ |
|---|---|
| Risk | Truy cập quản trị production trái phép |
| Security objective | Ngăn tài khoản privileged dùng xác thực yếu |
| Control | MFA cho mọi đường đăng nhập tương tác thuộc scope, theo policy |
| Assertion | Không tồn tại đường admin không được enforce MFA ngoài ngoại lệ hợp lệ |
| Evidence | Privileged inventory, effective auth policy, test bypass, exception register |
| KPI | Verified privileged MFA coverage |
| KRI | Số đường privileged không đạt MFA trên hệ thống critical |
| Target | Theo yêu cầu control được phê duyệt, có thể yêu cầu 100% cho critical gate |
| Action | Hạn chế quyền, sửa provisioning, retest, đánh giá ngoại lệ |

### 3.3. Metric phải tạo được hành động

Một KPI có màu đỏ nhưng không có owner hoặc playbook chỉ là tín hiệu bị bỏ quên. Metric specification nên có:

- Chủ sở hữu metric và chủ sở hữu control.
- Người có quyền phê duyệt rủi ro.
- Mức độ ảnh hưởng và nhóm dịch vụ trọng yếu.
- Tình huống tạo ticket, escalation, paging hoặc change gate.
- Điều kiện cần xác minh trước khi tự động remediation.
- Kết quả retest và cách đóng cảnh báo.
- Thời hạn review khi metric không còn phù hợp.

**Không tự động chặn/xóa tài nguyên production chỉ để đưa KPI về xanh** nếu chưa đánh giá tác động nghiệp vụ.

## 4. Metric specification: hợp đồng đo lường

KPI nên có một hồ sơ định nghĩa như một phần của control-as-code/metric catalog, để không mỗi dashboard hoặc đội dùng một cách tính khác nhau.

### 4.1. Các trường bắt buộc

| Nhóm | Trường | Câu hỏi |
|---|---|---|
| **Identity** | metric_id, name, version | Đây là chỉ số nào, định nghĩa phiên bản nào? |
| **Purpose** | objective, decision/use_case | Chỉ số phục vụ quyết định gì? |
| **Scope** | service, environment, data class, asset group | Những gì nằm trong và ngoài phạm vi? |
| **Population** | unit, independent source, inclusion/exclusion | Mẫu số là gì và ai xác nhận? |
| **Formula** | numerator, denominator, aggregation, null handling | Tính như thế nào, có thể chạy lại không? |
| **Time** | event time/measurement time, window, timezone, refresh | Dữ liệu thuộc kỳ nào? |
| **Sources** | system of record, queries, transformations | Nguồn nào và phiên bản logic? |
| **Quality** | freshness, completeness, missing/stale policy | Khi nào số liệu không đủ tin cậy? |
| **Targets** | threshold, severity, review cadence | Ngưỡng nào đã phê duyệt, theo bối cảnh nào? |
| **Responsibility** | owner, reviewer, approver | Ai vận hành và quyết định? |
| **Action** | runbook, escalation, remediation, retest | Khi vượt ngưỡng phải làm gì? |
| **Evidence** | artifact IDs, lineage, retention, access | Người kiểm toán có thể tái kiểm thế nào? |
| **Limitations** | known blind spots, sample bias | Điều không được suy ra từ KPI? |

### 4.2. Ví dụ metric specification bằng YAML

~~~yaml
metric_id: "KPI-SEC-IAM-001"
version: "1.0"
name: "Verified privileged MFA coverage"
metric_type: "KCI"
security_objective: "Prevent unauthorized interactive privileged access"
unit_of_analysis: "privileged-interactive-login-path"
scope:
  service_groups: ["business-critical"]
  environment: "production"
  inclusion_rule: "All active interactive privileged login paths"
  exclusion_rule: "Only explicitly reviewed and approved N/A"
population:
  authoritative_source: "privileged-identity-and-access-inventory"
  reconciliation_source: "IdP-and-platform-native-admin-inventory"
formula:
  numerator: "Paths with verified effective MFA enforcement"
  denominator: "All mandatory paths in scope"
  value_format: "percentage"
  not_evaluated_handling: "Remain in denominator; classify separately"
evaluation:
  evidence:
    - "Effective authentication configuration"
    - "Controlled bypass/deny test"
    - "Exception register"
  test_version: "iam-mfa-assurance-v3"
  frequency: "after-relevant-change-and-periodic"
quality_gates:
  population_completeness: "all known privileged sources reconciled"
  evidence_age: "as required by risk-approved test cadence"
  on_failure: "INCONCLUSIVE_NO_GREEN_STATUS"
target:
  interpretation: "Mandatory control requires no unapproved uncovered paths"
ownership:
  metric_owner: "security-assurance"
  control_owner: "identity-platform"
  risk_owner: "service-risk-owner"
action:
  if_fail: "open-remediation-and-restrict-privileged-exposure"
  retest: "reconcile-inventory-and-recheck-enforcement"
limitations:
  - "Does not prove absence of account compromise"
  - "Scope must be reviewed after identity architecture changes"
~~~

Đây là **schema ví dụ**, không phải cấu hình chính thức của một sản phẩm GRC/SIEM. Các ngưỡng cần căn cứ vào chính sách, BIA và mức rủi ro thật; không áp mặc định cho mọi tổ chức.

### 4.3. Versioning định nghĩa

KPI có thể thay đổi khi:

- Đơn vị đo được chuyển từ **tài khoản** sang **đường đăng nhập**.
- Inventory có thêm cloud tenant hoặc loại workload mới.
- Rule detection thay đổi, tạo nhiều alert hơn từ cùng event.
- SLA remediation được sửa, phân loại severity khác trước.
- Một nguồn bổ sung làm phát hiện nhiều incident hơn.
- Kỳ đánh giá thay từ snapshot ngày sang cả quý.

Nếu định nghĩa đổi, phải ghi **metric version** và thời điểm có hiệu lực. Khi so sánh xu hướng trước/sau, có thể cần tính lại lịch sử với dữ liệu tương thích hoặc đánh dấu **structural break**, tránh diễn giải thay đổi phương pháp thành cải thiện/thụt lùi bảo mật.

## 5. Công thức KPI: tử số, mẫu số, kỳ và trạng thái chưa biết

### 5.1. Coverage thực sự có mẫu số độc lập

Định nghĩa tham khảo:

\[
\text{Verified Control Coverage}
=\frac{N_{\text{verified PASS in required scope}}}
{N_{\text{required control units}}}\times 100\%
\]

Một **control unit** có thể là asset × control × period hoặc scenario × environment × control version. Cần chốt một cách nhất quán.

Các đơn vị **FAIL, NOT_TESTED, INCONCLUSIVE** vẫn thuộc mẫu số khi đó là yêu cầu bắt buộc. **NOT_APPLICABLE** chỉ được loại nếu có căn cứ và phê duyệt scope; **ACCEPTED_RISK** không chuyển thành PASS.

### 5.2. Ví dụ tránh tỷ lệ xanh giả

Có 50 cloud account production nằm trong scope logging:

- 40 account đã test PASS.
- 3 account confirmed FAIL.
- 4 account chưa kiểm được do collector lỗi.
- 3 account mới chưa onboard.

**Verified coverage = 40/50 = 80%.** Không báo 40/43 = 93,0% là coverage toàn phạm vi; tỷ lệ 40/43, nếu muốn sử dụng, chỉ là **pass rate trong nhóm có kết quả conclusive** với định nghĩa khác. Cũng không tính 40/40 = 100% chỉ vì chỉ nhìn các account đã bật thành công.

| Trạng thái | Số account | Ý nghĩa |
|---|---:|---|
| PASS | 40 | Có bằng chứng đạt assertion trong scope |
| FAIL | 3 | Có bằng chứng không đạt |
| INCONCLUSIVE | 4 | Dữ liệu không đủ để kết luận |
| NOT_TESTED | 3 | Thuộc scope nhưng chưa có test |
| **Tổng bắt buộc** | **50** | Mẫu số độc lập |

Nếu chỉ số cho lãnh đạo cần màu trạng thái, việc có **critical FAIL** hay **mất coverage** nên được thể hiện rõ bên cạnh tỷ lệ 80%, không bị gói vào trung bình.

### 5.3. Chất lượng đo và KPI nghiệp vụ là hai lớp

Đo một KCI tốt cần ít nhất:

1. **Population coverage:** có kiểm tra mọi asset cần đo không?
2. **Data completeness:** có đủ event và field cần thiết không?
3. **Timeliness:** dữ liệu có đủ mới, có late arrival hoặc clock skew không?
4. **Metric correctness:** query/rule chạy đúng phiên bản và logic không?
5. **Result quality:** PASS/FAIL được xác nhận bằng phương pháp phù hợp?
6. **Actionability:** phát hiện sai lệch có owner và ticket?

Nếu quality gate không đạt, dashboard nên báo **UNKNOWN / STALE / PARTIAL DATA** thay vì giữ xanh từ lần thu trước.

### 5.4. Điểm cần phân biệt trong tỷ lệ

- **Pass rate** = trường hợp PASS / các trường hợp đã được đánh giá theo tập con định nghĩa.
- **Coverage** = đơn vị đã kiểm hoặc đã xác minh đạt / tất cả đơn vị phải kiểm.
- **SLA adherence** = việc hoàn thành đúng hạn / các việc có hạn trong kỳ.
- **Open backlog** = lượng việc chưa đóng ở một thời điểm.
- **Throughput** = số việc hoàn thành trong một khoảng thời gian.
- **Incident rate** = số sự cố / quy mô phơi nhiễm phù hợp, nếu quy mô và chất lượng dữ liệu cho phép.
- **False positive rate** trong tập kiểm có nhãn không tự bằng **tỷ lệ alert bị analyst đóng benign**.

**Đừng thay đổi mẫu số âm thầm** để một chỉ số trông tốt hơn.

### 5.5. Không có dữ liệu phải là trạng thái có nghĩa

Một số trường hợp:

| Tình huống | Cách xử lý |
|---|---|
| Không có incident trong kỳ | Ghi zero incident được ghi nhận; không kết luận xác suất xảy ra là zero |
| Không có alert từ sensor mới | Xác minh sensor/telemetry và test canary trước khi kết luận không có đe dọa |
| Không có phép test trong kỳ | NOT_TESTED, không phải PASS |
| Thiếu timestamp bắt đầu | Không tự tính duration; ghi unknown hoặc interval/estimate có giới hạn |
| Không có asset inventory độc lập | Coverage INCONCLUSIVE, yêu cầu đối soát population |
| Mẫu số bằng 0 | N/A hoặc undefined theo logic đã phê duyệt, không mặc định 100% |
| Kết quả đến muộn | Giữ mốc chốt và cơ chế restatement/late-data revision rõ |
| Ngoại lệ hợp lệ | Theo policy, báo riêng và kiểm expiry; không giấu trong PASS |

## 6. KPI cho asset coverage và security hygiene

### 6.1. Asset inventory completeness

**Mục tiêu:** những hệ thống phải bảo vệ được nhận diện và có owner.

Một định nghĩa gần thực tiễn:

\[
\text{Asset Inventory Reconciliation Coverage}
=\frac{\text{Required assets có bản ghi hợp lệ và owner}}
{\text{Required assets xác định từ nguồn độc lập}}\times 100\%
\]

Cần đối chiếu cloud organization API, endpoint management, cluster inventory, service catalog và tài sản của bên thứ ba tùy scope. Nếu inventory chỉ chứa những asset đã đăng ký, số liệu sẽ bỏ qua **shadow IT** hoặc tài sản mới.

**Dữ liệu phụ trợ:** số asset chưa có owner, age kể từ lúc tạo đến lúc onboard, số asset không có service criticality/data classification, orphaned accounts.

### 6.2. Security baseline coverage

Ví dụ các assertions: encryption at rest, approved network policy, agent/EDR coverage, hardening, logging, backup policy.

Không nên gộp thành một “security score” rồi cho mỗi control trọng số bằng nhau nếu rủi ro không tương đương. Với control trọng yếu, nên có **critical gate**: chỉ một asset quản trị trung tâm thiếu logging có thể cần hành động khẩn cấp dù tỷ lệ chung vẫn cao.

### 6.3. Configuration drift

Định nghĩa có thể dùng:

- **Drift instances:** số thay đổi khiến effective configuration lệch baseline, phân theo severity.
- **Time to detect drift:** từ timestamp change được xác minh đến lúc hệ thống tạo finding có thể hành động.
- **Time to remediate drift:** từ finding xác nhận đến khi retest đạt.
- **Recurring drift rate:** tỷ lệ control/asset tái vi phạm sau verified closure.

Cần xem loại nguồn tạo thay đổi: IaC, thao tác console, operator, auto-scaling, vendor hoặc thay đổi inherited policy. Số finding tăng có thể là do detector tốt hơn, không nhất thiết hệ thống đang kém hơn.

### 6.4. Control onboarding latency

Một cloud account được tạo lúc 08:00 nhưng audit logging chỉ được verified lúc 13:00 có **khoảng phơi nhiễm chưa xác minh** 5 giờ. KPI có thể đo:

- Phân phối thời gian từ asset creation đến control onboarding verified.
- Số asset được đưa vào production trước khi critical controls verified.
- Tỷ lệ asset mới có đủ required controls trước go-live.
- Số lần exception onboarding được phê duyệt và thời gian tồn tại.

Nếu không biết giờ creation hoặc onboarding có nhiều giai đoạn, phải công bố độ chính xác và cách tính.

## 7. KPI cho IAM và privileged access

### 7.1. Verified privileged MFA coverage

Nên đo theo **đường truy cập quản trị tương tác**, không chỉ user count:

- IdP/SSO admin.
- Local admin và emergency/break-glass.
- Remote administrative access.
- Provider console và tenant-level admin.
- Vendor support access có quyền đặc biệt.

Tử số gồm các đường đã kiểm chứng **effective MFA enforcement** bằng configuration evidence hoặc controlled test phù hợp. Mẫu số là mọi đường bắt buộc trong scope. Account đã vô hiệu hóa hoặc không tương tác phải được phân loại theo criterion, không tự tạo ngoại lệ mơ hồ.

### 7.2. Privileged access review completion

\[
\text{On-time Review Completion}
=\frac{\text{Reviews required in period completed and approved on time}}
{\text{Reviews due in period}}\times100\%
\]

Một review hoàn thành chỉ khi có **population, reviewer, quyết định, hành động thu hồi/sửa và bằng chứng thời gian** theo control. Chỉ gửi email nhắc hoặc export danh sách quyền chưa đủ.

Chỉ số bổ sung:

- Số quyền vượt baseline hoặc orphaned identities.
- Tuổi của quyền tạm thời chưa thu hồi.
- Quyền vendor còn tồn tại sau hợp đồng.
- Ngoại lệ privileged access quá hạn.
- Thời gian vô hiệu hóa quyền khi người dùng rời nhóm hoặc nghỉ việc, theo mốc quy định.

### 7.3. Time-to-revoke có ý nghĩa hơn số lượng tài khoản xóa

Khi nhân sự rời tổ chức, KPI **time to revoke access** cần mốc bắt đầu: ngày/giờ được thông báo offboarding hợp lệ hay thời điểm kết thúc làm việc? Mốc kết thúc là khi **quyền thật sự không còn hiệu lực**, bao gồm session/token còn sống nếu yêu cầu tính. Phải xem cả direct và inherited access, không chỉ trạng thái user ở một directory.

### 7.4. Rủi ro metric bị tối ưu sai

Một đội có thể giảm số tài khoản privileged trên dashboard bằng cách đổi tên role hoặc chuyển quyền thành service account không được đo. Vì vậy, cần kiểm tra **effective permissions** và asset inventory độc lập, không chỉ label “admin”.

## 8. KPI vulnerability và remediation

### 8.1. Patch SLA adherence

Một định nghĩa kiểm soát:

\[
\text{On-time Remediation Rate}
=\frac{\text{Findings due in period remediated and verified by deadline}}
{\text{All findings with remediation deadline in period}}\times100\%
\]

Cần quy định có bao gồm các finding được phát hiện nhưng chưa đến hạn hay không, ngoại lệ theo policy, reopened findings và duplicate. Đừng bỏ finding overdue khỏi mẫu số vì đã chuyển chủ sở hữu.

### 8.2. Backlog và tuổi lỗ hổng

Các chỉ số thường hữu ích:

| KPI | Cách hiểu đúng | Rủi ro khi diễn giải |
|---|---|---|
| **Open critical/high findings** | Số finding còn mở tại snapshot, phân theo asset criticality | Scanner mới mở rộng coverage có thể làm số tăng |
| **Overdue critical remediation** | Finding quá hạn chưa có retest PASS | Thay deadline có thể làm KPI đẹp giả |
| **Age distribution** | Tuổi từ detection/confirmed đến current/closure theo định nghĩa | Điểm bắt đầu có thể đổi khi gộp duplicate |
| **Verified closure rate** | Finding được retest đạt trong kỳ / tập xác định | Ticket Done chưa chứng minh đã sửa |
| **Repeat vulnerability rate** | Finding cùng nguyên nhân/tài sản xuất hiện lại | Cần taxonomy và phân biệt reintroduced vs unresolved |
| **Exposure-weighted backlog** | Risk backlog xét asset và điều kiện có thể khai thác | Cần minh bạch trọng số, tránh che các critical cases |
| **Scan coverage** | Required assets được scan đúng phương pháp/kỳ / required assets | Không bao gồm unscannable assets nếu chỉ tính scanned population |

### 8.3. CVSS không phải thước đo duy nhất của rủi ro

Severity từ scanner/CVSS là thông tin hữu ích nhưng remediation priority cần xét:

- Tài sản thuộc production hoặc hệ thống trọng yếu.
- Có tiếp xúc Internet, dữ liệu nhạy cảm hoặc trust boundary.
- Quyền cần có và khả năng khai thác trong bối cảnh.
- Có đường tấn công thực tế hay kiểm soát bù trừ nào.
- Có dấu hiệu bị khai thác hoặc threat intelligence đáng tin.
- Khả năng patch/mitigation và nghĩa vụ được phê duyệt.

Vì vậy, chỉ số “trung bình điểm CVSS của lỗ hổng mở” có thể che một số ít lỗ hổng cực kỳ quan trọng; nên phân tổ risk và exposure.

### 8.4. Ví dụ tính tuổi remediation

Một finding được xác nhận 01/11, sửa cấu hình 08/11, retest đạt 11/11. Có hai mốc khác nhau:

- **Implementation time:** 7 ngày từ confirmed đến sửa.
- **Verified closure time:** 10 ngày từ confirmed đến retest PASS.

Nếu yêu cầu là **khắc phục và kiểm chứng trong hạn**, không dùng ngày sửa 08/11 để kết luận control đã đạt khi kết quả retest chỉ có 11/11.

## 9. KPI detection engineering và security monitoring

### 9.1. Detection scenario coverage

Một rule không tự đồng nghĩa một scenario được bao phủ. Có thể định nghĩa:

\[
\text{Verified Detection Coverage}
=\frac{\text{Scenario units có end-to-end test PASS}}
{\text{Required scenario units theo threat model}}\times100\%
\]

Đơn vị có thể là scenario × asset class × environment × parser/source variant. Test phải kiểm signal ở nguồn, ingestion, rule, alert routing và triage nếu đó là control yêu cầu.

### 9.2. Telemetry coverage và health

| Metric | Assertion cần kiểm |
|---|---|
| **Required source coverage** | Asset/sources bắt buộc đều onboard |
| **Synthetic event delivery** | Event class quan trọng đến pipeline đúng field và thời hạn |
| **Ingestion lag** | Độ trễ event time → ingest time theo nhóm source/percentile |
| **Drop/error rate** | Queue/collector/parser không mất dữ liệu vượt ngưỡng |
| **Field completeness** | Các trường actor, action, resource, outcome có đủ theo schema |
| **Rule runtime health** | Rule được bật và chạy đúng phiên bản/index/schedule |
| **Alert delivery success** | Alert cần báo được route/ack đúng nơi |
| **Suppression exposure** | Ngoại lệ có owner, scope và expiry; bao phủ của rule sau suppression |

Heartbeat chứng minh thành phần còn hoạt động, **không chứng minh mọi event type được ghi**. Số log/giây tăng không tự chứng minh khả năng detection tốt hơn.

### 9.3. False positive, false negative và precision

Cho một **tập test được gắn nhãn đủ tin cậy**:

- **TP (true positive):** trường hợp thực sự thuộc điều kiện cần phát hiện và được phát hiện.
- **FN (false negative):** trường hợp thực sự cần phát hiện nhưng bị bỏ sót.
- **FP (false positive):** trường hợp không thuộc điều kiện nhưng bị báo là positive.
- **TN (true negative):** trường hợp không thuộc điều kiện và không bị báo là positive.

Các công thức:

\[
\text{Recall/TPR}=\frac{TP}{TP+FN}
\]

\[
\text{Precision}=\frac{TP}{TP+FP}
\]

\[
\text{False Positive Rate}=\frac{FP}{FP+TN}
\]

\[
\text{False Negative Rate}=\frac{FN}{TP+FN}
\]

Cần phân biệt **false positive rate** với **tỷ lệ alert bị đóng benign**. Một alert bị analyst đóng benign chưa chắc ground truth đã xác định đúng; TN thường rất khó định nghĩa trong continuous event streams. Precision/recall trên synthetic labeled test **không tự đại diện cho mọi cuộc tấn công production**.

### 9.4. Ví dụ dữ liệu kiểm thử

Trong tập test đã gắn nhãn có 20 trường hợp đáng phát hiện và 80 trường hợp không đáng phát hiện. Engine báo:

- TP = 16.
- FN = 4.
- FP = 8.
- TN = 72.

Khi đó:

- Recall = 16/20 = **80%**.
- Precision = 16/(16+8) = **66,7%**.
- False positive rate = 8/80 = **10%**.
- False negative rate = 4/20 = **20%**.

Các số này chỉ nói về **tập test và ground truth đã chọn**. Nếu tập này không chứa các biến thể tấn công khó, kết quả sẽ lạc quan. Nếu chỉ tập trung rare positives, precision trong production có thể khác do base rate.

### 9.5. Không tối ưu giảm alert bằng cách tắt detection

Một SOC có thể giảm false positives bằng cách:

- Nâng chất lượng analytics và enrichment.
- Phân loại asset/context đúng hơn.
- Bổ sung negative test và cập nhật baseline.
- Thu hẹp suppression theo điều kiện, có owner/expiry.
- Xây detection tương quan hành vi thay cho exact match quá hẹp.

Nhưng nếu chỉ **tăng threshold, tắt rule hoặc mở allowlist**, số alert giảm có thể trông tốt trong khi **detection blind spot tăng**. Phải theo dõi đồng thời coverage, FN test và control changes.

## 10. KPI incident response và thời gian xử lý

### 10.1. Định nghĩa timestamp chuẩn

Trong một incident cần phân biệt:

- **Tattack:** thời điểm hoạt động gây hại thật sự bắt đầu, thường không biết chính xác.
- **Tfirst-observed:** dấu vết sớm nhất được xác minh trong dữ liệu hiện có.
- **Tdetected:** thời điểm hệ thống/đội nhận biết và đáp ứng tiêu chí phát hiện.
- **Talert-received:** cảnh báo tới hàng đợi hoặc kênh trực.
- **Ttriage-start:** analyst bắt đầu phân tích.
- **Tacknowledged:** người phụ trách xác nhận tiếp nhận.
- **Tcontained:** biện pháp hạn chế đã có hiệu lực và được kiểm chứng.
- **Trecovered:** dịch vụ đáp ứng tiêu chí phục hồi đã xác định.
- **Tclosed:** case được đóng theo quy trình, có thể sau recovery.

**MTTD, MTTA, MTTC, MTTR** là những nhãn được dùng khác nhau giữa tổ chức/công cụ. Không thể so sánh nếu không công bố mốc đo và tập incident.

### 10.2. Một bộ công thức minh bạch

Ví dụ theo định nghĩa nội bộ:

\[
\text{Detection Duration}_i=T_{\text{detected},i}-T_{\text{first observed},i}
\]

\[
\text{Acknowledgement Duration}_i=T_{\text{ack},i}-T_{\text{alert received},i}
\]

\[
\text{Containment Duration}_i=T_{\text{contained},i}-T_{\text{detected},i}
\]

\[
\text{Recovery Duration}_i=T_{\text{recovered},i}-T_{\text{disruption start},i}
\]

Sau đó **MTTD/MTTA/MTTC/MTTR** có thể là mean (trung bình cộng) của duration tương ứng, **nếu tổ chức đã chọn các định nghĩa đó**. Một số chương trình dùng MTTR = mean time to respond, remediate, resolve hoặc recover; phải ghi rõ tên và công thức, không sử dụng mơ hồ.

### 10.3. Ví dụ timeline

Một sự cố giả định có:

| Mốc | UTC | Ý nghĩa |
|---|---|---|
| First observed malicious activity | 09:05 | Dấu vết sớm nhất hiện có |
| Alert generated | 09:12 | Engine tạo alert |
| Alert received by SOC | 09:13 | Hàng đợi SOC nhận |
| Acknowledged | 09:17 | Analyst nhận case |
| Detection confirmed | 09:20 | Theo định nghĩa của chương trình |
| Containment verified | 09:31 | Credential bị thu hồi, test deny PASS |
| Service recovery verified | 10:44 | Đạt tiêu chí chức năng và an toàn |

Nếu chọn **detected = 09:20**:

- Detection duration từ first observed đến confirmed = **15 phút**.
- Acknowledgment duration từ alert received đến acknowledged = **4 phút**.
- Containment duration từ detected đến verified containment = **11 phút**.

Nếu một đội chọn Tdetected = alert generated 09:12, detection duration sẽ thành **7 phút**. Cả hai có thể nhất quán với định nghĩa riêng, nhưng không thể gộp hoặc so sánh trực tiếp mà bỏ chú thích.

### 10.4. Thời gian dài và dữ liệu bị kiểm duyệt

Khi incident chưa được containment tại mốc chốt báo cáo, duration là **right-censored**: không được tự điền số 0 hay coi là hoàn tất đúng hạn. Có thể báo riêng **open incidents**, tuổi hiện tại và số vượt target; với phân tích nghiêm túc có thể dùng phương pháp survival analysis phù hợp.

Tương tự, nếu không biết Tattack thì chỉ được tính từ **earliest observed**, không thể kết luận đó là toàn bộ thời gian attacker hiện diện.

### 10.5. Trung bình, median và tail latency

Một bộ thời gian từ phát hiện đến containment (phút): **8, 10, 11, 12, 139**.

- Mean = 180/5 = **36 phút**.
- Median = **11 phút**.

Mean tăng mạnh do một sự cố 139 phút. Median mô tả trải nghiệm điển hình hơn nhưng che ca rất dài. Nên xem **median, p90/p95 khi đủ mẫu, maximum, count và phân tổ severity**. Với chỉ 5 incident, p95 không ổn định; không vẽ percentile như tín hiệu thống kê chắc chắn.

### 10.6. Số incident tăng có thể là điều tốt?

Số incident được phát hiện tăng có thể vì:

- Telemetry mới giúp tìm ra hoạt động trước đây bị bỏ sót.
- Quy trình triage tốt hơn, classifier chính xác hơn.
- Threat landscape/risk exposure tăng.
- Thay đổi định nghĩa incident hoặc severity.
- Một tấn công thật sự tăng số lần xảy ra.

Vì vậy, **incident count** cần đi với detection coverage, false-negative testing, assets at risk và impact đã xác nhận. Chỉ dùng “giảm số incident” làm thưởng phạt dễ khuyến khích không khai báo.

## 11. KPI cho logging, audit evidence và control health

### 11.1. Log source coverage

\[
\text{Log Source Coverage}
=\frac{\text{Required source units đã kiểm chứng hoạt động}}
{\text{Required source units từ asset/control inventory}}\times100\%
\]

Một source unit có thể là account × event class hoặc host × sensor, tùy quy định. Không lấy tổng số agent đang hoạt động làm mẫu số nếu có host chưa onboard.

### 11.2. Event integrity và completeness

Những phép đo cần tách:

- **Ingest completeness:** số event/batch nhận được so với số event/batch nguồn có thể xác minh, khi có sequence/counter đáng tin.
- **Field completeness:** tỷ lệ event đã nhận có đủ trường actor/action/resource/outcome.
- **Integrity verification:** tỷ lệ segment/checkpoint/hashes/signatures được xác minh hợp lệ trong phạm vi.
- **Last checkpoint age:** mốc bằng chứng được anchor gần nhất.
- **Source silence detection:** số nguồn bắt buộc không có heartbeat hoặc synthetic event theo kỳ.
- **Log retention coverage:** các nguồn có retention policy và phép kiểm đáp ứng kỳ yêu cầu.

Hash khớp cho biết artifact khớp mốc tham chiếu, **không chứng minh event nguồn đã trung thực hoặc không thiếu log**. Event count ổn định không chứng minh các sự kiện quan trọng vẫn được thu nếu parser/drop filter đã thay đổi.

### 11.3. Audit evidence readiness

Một số chỉ số:

| Metric | Định nghĩa có ích |
|---|---|
| **Evidence availability** | Assertion bắt buộc có evidence được lưu và truy xuất được / assertion cần evidence |
| **Evidence freshness** | Evidence đúng kỳ/tuổi đã phê duyệt / evidence bắt buộc |
| **Evidence traceability** | Assertion có reference tới source, test, method và result / assertion đã đánh giá |
| **Evidence gap age** | Thời gian từ lúc thiếu evidence được phát hiện đến lúc đủ căn cứ |
| **Control validation coverage** | Control units đã test đúng method/period / required control units |
| **Audit finding recurrence** | Finding đã verified closed nhưng tái vi phạm trên scope tương đương |

Nếu hồ sơ chưa có evidence, kết quả có thể là **INCONCLUSIVE**, không nhất thiết đã xác nhận **control FAIL**. KPI nên trình bày riêng hai trạng thái.

### 11.4. Phân biệt hệ thống đang chạy và hệ thống có thể chứng minh

Một SIEM có thể vận hành đúng nhưng evidence export không lưu được trong kỳ yêu cầu. Ngược lại, evidence collector có thể còn chạy trong khi rule detection bị tắt. Vì vậy, cần theo dõi đồng thời:

- Health và execution của **control**.
- Health và coverage của **measurement pipeline**.
- Health và bảo vệ của **evidence store**.
- Sự thống nhất giữa config, runtime và báo cáo.

Một KPI “evidence collector online” không phải KPI “security assurance passed”.

## 12. KPI backup, disaster recovery và cyber recovery

### 12.1. Backup job success không phải recovery success

Một tổ chức có thể báo **100% backup jobs completed** mà vẫn không khôi phục được dịch vụ vì:

- Backup bị corruption, không đủ transaction log hoặc metadata.
- Khóa KMS không thể sử dụng tại recovery region/account.
- Không có capacity/quota hoặc artifact tin cậy để dựng ứng dụng.
- Restore được database nhưng message broker không khớp transaction state.
- Không có DNS/identity/secret hoặc integration với hệ thống đối tác.
- Bản backup chứa malware/persistence hoặc credential bị chiếm.

Vì thế cần tách **backup process metrics**, **restore validation metrics** và **business recovery outcomes**.

### 12.2. Các KPI mẫu

| KPI | Đơn vị/mẫu số | Bằng chứng | Giới hạn |
|---|---|---|---|
| **Required backup coverage** | Datasets bắt buộc có backup hợp lệ / toàn bộ datasets bắt buộc | Data inventory, backup catalog, job/retention config | Backup hiện hữu chưa chứng minh restore được |
| **Backup freshness** | Độ lùi điểm backup mới nhất so với kỳ vọng | Backup timestamp + data consistency point | Timestamp file không phải lúc dữ liệu cuối nhất quán |
| **Verified restore coverage** | Required datasets/services được restore thử PASS / tất cả required units cần thử | Restore log, decrypt, application validation | Sandbox nhỏ không chứng minh production RTO |
| **DR exercise pass rate** | Exercise đạt toàn bộ assertions / exercise cần/đã thực hiện theo định nghĩa | Runbook, test report, approvals | Một test PASS chưa bao phủ mọi failure scenario |
| **RTO attainment** | Exercise/sự cố đạt mục tiêu thời gian / các trường hợp nằm trong mục tiêu được đánh giá | T0, T1, business verification | Không lấy thời gian server boot làm service recovery |
| **RPO attainment** | Trường hợp có điểm khôi phục nhất quán trong ngưỡng / các trường hợp phải đánh giá | T0, last consistent data point, transaction test | Replication lag thấp không chứng minh dữ liệu sạch |
| **Cyber recovery readiness** | Required clean recovery assertions PASS / assertions bắt buộc | Artifact trust, isolated restore, identity tests | Kết quả scanner sạch không chứng minh tuyệt đối |
| **Failback validation** | Kịch bản failback đã kiểm và dữ liệu đối soát đạt / kịch bản cần kiểm | Reconciliation, routing, rollback test | Failover PASS không suy ra failback PASS |

### 12.3. Công thức đo theo từng exercise

Đối với một kịch bản đã được BIA phê duyệt:

\[
\text{Actual Recovery Duration}=T_{\text{service verified}}-T_{\text{disruption}}
\]

\[
\text{Recovery Point Lag}=T_{\text{disruption}}-T_{\text{last consistent recovery point}}
\]

Ví dụ:

- Mất site chính lúc 09:00 UTC.
- Điểm dữ liệu nhất quán mới nhất: 08:52 UTC.
- Hệ thống dựng xong máy chủ lúc 09:48 UTC.
- Chỉ đến 10:44 UTC, ứng dụng, data reconciliation, IAM và logging đạt tiêu chí chấp nhận.

Kết quả:

- **Recovery duration = 104 phút**.
- **Recovery point lag = 8 phút**.

Nếu target RTO = 120 phút và RPO = 15 phút, bài thử đáp ứng hai mục tiêu **trong phạm vi scenario và dữ liệu đã kiểm**, không đồng nghĩa tất cả failure modes đều đạt.

### 12.4. Bắt buộc có security gate

Không nên thưởng cho DR đạt RTO sớm hơn bằng cách bỏ qua authentication, TLS, log collection, key management hoặc kiểm tra backup sạch. Khi một security gate bắt buộc chưa đạt, có thể trình bày:

- **RTO measured:** thời gian dựng dịch vụ thử.
- **RTO accepted:** thời gian đạt đầy đủ business và security acceptance criteria.
- **Security-control verdict:** PASS/FAIL/INCONCLUSIVE riêng.
- **Risk decision:** nếu dịch vụ phải hoạt động degraded, ai phê duyệt và giới hạn nào.

Số đầu tiên là telemetry kỹ thuật; số thứ hai mới hỗ trợ kết luận mục tiêu phục hồi đã được thỏa thuận.

## 13. KPI third-party assurance và supply-chain risk

### 13.1. Không dùng tỷ lệ hoàn thành questionnaire làm điểm an toàn

Một nhà cung cấp có thể trả lời 100/100 câu hỏi nhưng không cung cấp evidence cho quyền truy cập production hoặc backup DR. Nên đo riêng:

| Metric | Cách tính | Câu hỏi quản trị |
|---|---|---|
| **Vendor assessment coverage** | Dịch vụ bên thứ ba cần đánh giá có assessment hợp lệ / tổng dịch vụ cần đánh giá | Có bỏ sót shadow SaaS không? |
| **Critical assertion verification** | Critical control assertions PASS / tổng critical assertions applicable | Có bằng chứng đủ cho quyết định go-live không? |
| **Questionnaire completion** | Câu hỏi đã nhận câu trả lời hợp lệ / tổng câu hỏi phải trả lời | Tiến độ phản hồi, không phải security posture |
| **Evidence freshness** | Bằng chứng đúng scope và kỳ / bằng chứng phải có | Báo cáo độc lập đã cũ hoặc ngoài scope? |
| **High-risk finding backlog** | Finding trọng yếu còn mở, phân theo hạn và criticality | Có blocker chưa xử lý không? |
| **Overdue exception** | Ngoại lệ vendor hết hạn mà chưa có đánh giá lại | Có risk acceptance vô thời hạn không? |
| **Subprocessor change coverage** | Material changes đã được review / thay đổi cần review | Data flow có đổi mà security chưa biết? |
| **Incident notification conformance** | Thông báo thuộc nghĩa vụ thực tế được xử lý trong hạn / thông báo phải được xử lý | Cần dữ liệu đủ và định nghĩa trigger đúng |
| **Exit verification** | Offboarding có kiểm chứng thu hồi quyền/xử lý dữ liệu / vendor exits cần kiểm | Hủy subscription chưa đủ bảo đảm thu hồi quyền |

### 13.2. Báo cáo theo service và trách nhiệm chia sẻ

Đơn vị đánh giá nên là **vendor service + dữ liệu + quyền + scope**, không phải toàn công ty vendor theo nhãn chung. Một chứng nhận độc lập có thể chỉ bao phủ một sản phẩm, region, kỳ đánh giá hoặc pháp nhân.

Các controls khách hàng phải tự cấu hình (ví dụ tenant SSO, export audit log, token API) cần có metric riêng, không bị cộng vào “vendor compliance score”. Nên công bố **shared-responsibility gap**: assertion nào vendor có bằng chứng đạt nhưng phía khách hàng chưa triển khai điều kiện bổ sung.

### 13.3. Khi vendor không thể chia sẻ evidence

Một finding chưa đủ dữ liệu không nên bị đánh NO nếu nhà cung cấp chưa xác nhận thiếu control, cũng không được coi PASS vì tên tuổi nhà cung cấp. Dùng **INCONCLUSIVE**, mô tả evidence gap, biện pháp xác minh thay thế hoặc giới hạn tích hợp, và quyết định risk owner có thời hạn nếu được policy cho phép.

## 14. KPI compliance assurance, audit findings và CAPA

### 14.1. Compliance metric phải gắn nghĩa vụ áp dụng

Một tổ chức có 200 control assertions trong thư viện nhưng chỉ 130 applicable cho dịch vụ cụ thể không nên dùng mẫu số 200 nếu đang đo “applicable control pass rate” của dịch vụ đó. Ngược lại, không được xóa các **required but NOT_TESTED** khỏi mẫu số 130.

Quy trình:

1. Obligation register xác nhận requirement và ngày hiệu lực.
2. Applicability assessment xác nhận service, data, environment, contract scope.
3. Control mapping xác định assertions.
4. Evidence/test đánh giá theo kỳ.
5. Verdict phân tách PASS/FAIL/INCONCLUSIVE/NOT_TESTED/N/A.
6. Báo cáo coverage, exceptions và risk decisions.

### 14.2. Metric cho audit finding lifecycle

| KPI | Định nghĩa | Cảnh báo |
|---|---|---|
| **Finding aging** | Tuổi của finding từ confirmed đến thời điểm đánh giá hoặc verified closure | Không xóa tuổi khi đổi ticket owner |
| **Open critical findings** | Số finding critical còn mở có severity được phê duyệt | Số thấp có thể do ít audit |
| **Overdue remediation** | Finding đã quá deadline mà chưa có verified closure hoặc trạng thái xử lý phù hợp | Tách implemented vs verified |
| **Corrective action completion** | Hành động đã triển khai / hành động bắt buộc trong kỳ | Không nói control đã hoạt động hiệu quả |
| **Verified closure coverage** | Findings được retest PASS và phê duyệt đóng / findings cần đóng theo định nghĩa | Risk accepted không tự thành PASS |
| **Repeat findings** | Finding cùng root cause tái xuất hiện trong scope tương đương | Cần taxonomy, phân biệt recurring vs new |
| **Evidence deficiency** | Assertions không đủ evidence / assertions cần evidence | Không tự khẳng định kỹ thuật fail |
| **Exception expiry** | Exceptions quá hạn chưa review/khắc phục | Cần theo dõi ngoại lệ không có expiry |

### 14.3. Ví dụ các trạng thái không nên gộp

Có 40 finding trong chương trình theo dõi:

- 12 **CLOSED_VERIFIED**.
- 8 đã triển khai correction nhưng chưa retest.
- 14 đang remediation.
- 4 được risk owner chấp nhận có điều kiện.
- 2 chờ xác định criterion/evidence.

**Verified closure = 12/40 = 30%** trong population đã định nghĩa. Không cộng 8 correction + 4 accepted risk vào “đã sửa đạt” chỉ để báo 60%. Có thể báo riêng **implementation progress**, **risk decision coverage**, **verification backlog**.

### 14.4. Đo hiệu lực chứ không chỉ tốc độ đóng

Một đội đóng 100 finding trong tháng nhưng 30 finding mở lại tháng sau có thể đang giải quyết triệu chứng, chưa giải quyết root cause. Nên theo dõi:

- Verified closure time theo severity.
- Reopen/recurrence rate.
- Tỷ lệ CAPA có kiểm thử nguyên nhân tái phát.
- Số control violations mới sau khi sửa provisioning/gating.
- Số finding được tạo từ nguồn phát hiện liên tục trước kỳ audit.

**Tốc độ** và **độ bền của kết quả** phải được xem cùng nhau.

## 15. Risk-weighted metrics, mục tiêu và ngưỡng hành động

### 15.1. Cần phân tổ trước khi gộp

Một tỷ lệ 99% patch coverage có thể che máy chủ quản trị critical chưa vá. Vì vậy, nên phân loại:

- Asset criticality: critical/high/medium/low theo BIA.
- Exposure: Internet-facing, privileged, internal restricted, test.
- Data classification: công khai/nội bộ/nhạy cảm.
- Business service, environment, cloud tenant và owner.
- Threat relevance và loại control.
- Control mandatory hay recommended.
- Severity và age của finding.

Một cách báo cáo tốt là **tỷ lệ chung + chỉ số riêng cho critical units + danh sách blocker**, không chỉ một điểm trung bình.

### 15.2. Risk-weighted score cần công khai quy tắc

Ví dụ minh họa có ba nhóm:

| Nhóm | PASS / Required | Tỷ lệ | Trọng số minh họa |
|---|---:|---:|---:|
| Critical assets | 9/10 | 90% | 5 |
| High assets | 18/20 | 90% | 3 |
| Non-critical assets | 70/70 | 100% | 1 |

Nếu dùng **một trọng số cho mỗi đơn vị trong nhóm**, điểm weighted coverage là:

\[
\frac{(9\times5)+(18\times3)+(70\times1)}
{(10\times5)+(20\times3)+(70\times1)}
=\frac{169}{180}\approx93.9\%
\]

Còn unweighted coverage là **97/100 = 97%**.

Hai số khác nhau do phương pháp. Dù weighted score cao, **một critical asset FAIL** vẫn cần hiển thị như blocker nếu policy quy định. Trọng số 5/3/1 chỉ dùng để minh họa; không phải chuẩn chung và không thể biến metric này thành xác suất không bị tấn công.

### 15.3. Chọn target bằng ngữ cảnh

Target có thể xuất phát từ:

- Security baseline hoặc nghĩa vụ bắt buộc, đôi khi cần đạt **100% đối với một assertion critical**.
- BIA và availability/recovery goals đã được duyệt.
- Khả năng giám sát, loại tài sản và chi phí thực thi.
- Kết quả lịch sử/đường cơ sở và xu hướng rủi ro.
- Cam kết SLA/SLO có nguồn phê duyệt.
- Kiểm thử thực tế hoặc threat scenario tạo ngưỡng phát hiện.

Không áp một mục tiêu “MTTD dưới 5 phút” cho mọi sự cố mà không định nghĩa mốc, loại threat và nguồn dữ liệu. Không chọn target chỉ vì “tháng trước đạt 98%” nếu 2% còn lại là critical security boundary.

### 15.4. Các loại ngưỡng

| Loại | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| **Hard compliance gate** | Assertion bắt buộc; sai một đơn vị cần điều tra/được quản trị | Unapproved privileged MFA bypass count > 0 |
| **Performance target** | Chỉ tiêu thực hiện trong cửa sổ xác định | 95% alert critical được ack trong hạn phê duyệt |
| **Early warning** | Cảnh báo nguy cơ trước khi fail | Backup freshness gần chạm RPO mục tiêu |
| **Data quality gate** | Ngăn hiển thị PASS nếu nguồn đo thiếu | Asset reconciliation thấp hơn ngưỡng chấp nhận |
| **Trend anomaly** | Thay đổi đáng kể so với baseline theo phân tổ | Field null rate tăng sau parser deployment |
| **Exception expiry** | Một ngoại lệ sắp hết hoặc đã hết hạn | Expired exceptions > 0 |

Ngưỡng phải có **owner và response** tương ứng, nếu không sẽ tạo alert fatigue hoặc dashboard bị bỏ qua.

## 16. Kiến trúc dữ liệu cho security metrics

### 16.1. Không xây KPI chỉ từ một hệ thống

Các nguồn thường cần:

- **Asset inventory:** cloud organizations, endpoint/MDM, Kubernetes, service catalog, CMDB.
- **Identity/privileged inventory:** IdP, PAM, local admin, service accounts, IAM.
- **Security telemetry:** SIEM, EDR, cloud audit, detection engine, parser/collector health.
- **Vulnerability:** scanners, asset risk enrichment, ticket/change history.
- **Incident:** alert, case management, triage, containment và recovery timestamps.
- **Resilience:** backup catalog, restore test, DR exercise, BIA objectives.
- **Governance:** obligation/control register, questionnaire, findings, exceptions, risk acceptance.
- **Development:** repo, IaC, CI/CD, artifact registry, deployment/change events.

Một nguồn đơn lẻ hiếm khi đủ làm **mẫu số độc lập, bằng chứng hiệu lực và rủi ro nghiệp vụ** cùng lúc.

### 16.2. Kiến trúc pipeline tham khảo

~~~mermaid
flowchart LR
    A["Asset / service / data inventory"] --> J["Normalize IDs + reconcile"]
    B["IAM / SIEM / EDR / scanners"] --> J
    C["GRC / audit / incident / tickets"] --> J
    D["Backup / DR / CI-CD / changes"] --> J
    J --> Q["Data quality gates"]
    Q --> CALC["Versioned metric calculations"]
    CALC --> STORE["Metric snapshots + evidence lineage"]
    STORE --> SOC["SOC / Engineering dashboard"]
    STORE --> EXEC["Risk / Executive reporting"]
    STORE --> AUD["Audit / Assurance evidence"]
    Q --> ALERT["Missing / stale / invalid source alerts"]
    CALC --> ACTION["Finding / remediation / retest"]
    ACTION --> J
~~~

Pipeline không nên sao chép dữ liệu nhạy cảm tràn lan. Có thể tính số liệu tổng hợp từ nguồn theo **quyền read-only**, giữ reference tới evidence raw trong kho phân quyền để auditor kiểm tra khi cần.

### 16.3. Vấn đề ID, duplicate và chuyển đổi

Cùng một tài sản có thể xuất hiện dưới nhiều tên:

- Cloud account ID và tên dự án.
- Hostname thay đổi sau rebuild.
- Instance ID mới sau auto-scaling.
- Kubernetes pod ngắn hạn và workload controller dài hạn.
- User email đổi tên nhưng principal ID không đổi.
- Một vulnerability được scanner ghi nhiều lần trên cùng asset.

Cần xác định **canonical identity**, stable identifiers và deduplication rules theo mục đích. Ví dụ, endpoint coverage tính theo thiết bị vật lý có thể khác coverage theo workload instances; không đổi đơn vị giữa các kỳ nếu chưa version metric.

### 16.4. Event time, processing time và late data

Để phân tích xu hướng:

- **Event time:** thời điểm hoạt động nguồn thực sự ghi nhận.
- **Collection/ingestion time:** lúc pipeline nhận.
- **Calculation time:** lúc metric được tính.
- **Reporting cutoff:** mốc dữ liệu được chốt.
- **Effective period:** thời gian policy/control áp dụng.

Khi event đến muộn, có thể có **restate/backfill** cho kỳ trước. Phải lưu lịch sử phiên bản và sự thay đổi; không sửa KPI đã phê duyệt âm thầm. Với dữ liệu quan trọng, báo cáo nên có **as-of time**, **last refresh** và **data completeness**.

### 16.5. Quality gates bắt buộc

Một metric pipeline nên tự đánh giá:

1. Có đủ required sources và asset groups không?
2. Có nguồn nào bị mất heartbeat nhưng không có alert không?
3. Có field bắt buộc null nhiều hơn kỳ vọng không?
4. Có thay đổi parser/schema làm logic metric sai không?
5. Có giá trị ngoài phạm vi, timestamp âm hoặc thiếu timezone không?
6. Có duplicate do retry hoặc missing batch không?
7. Có đơn vị chưa được kiểm trong kỳ không?
8. Có mismatch giữa source inventory và tool inventory không?
9. Có thay đổi rule/denominator không được version không?
10. Có dữ liệu mới vượt reporting cutoff không?

Nếu quality gate fail, metric nên hiển thị **DEGRADED/UNKNOWN**, không trả lại số cũ như một trạng thái xanh mới.

## 17. Ví dụ tính KPI bằng SQL và dữ liệu có kiểm soát

Các câu SQL sau là **pseudocode theo schema giả định**, không phải câu lệnh sẵn chạy cho bất kỳ SIEM, cloud hay GRC cụ thể. Mục đích là minh họa cách giữ mẫu số, trạng thái chưa kiểm và truy vết tới asset.

### 17.1. Mô hình dữ liệu tối thiểu

Giả định có các bảng:

- **required_control_units:** unit_id, asset_id, service_id, control_id, environment, required_at, lifecycle_status.
- **control_test_results:** unit_id, control_id, tested_at, test_version, verdict, evidence_id.
- **metric_snapshots:** metric_id, window_end, numerator, denominator, value, quality_state.
- **exceptions:** unit_id, control_id, approved_by, valid_until, scope.
- **asset_inventory:** asset_id, service_id, criticality, status.

Khi nhiều bản test, phải chọn kết quả hiệu lực **theo quy tắc freshness, time window và version**, không đơn giản lấy lần mới nhất của một đối tượng đã đổi scope.

### 17.2. Đếm PASS/FAIL/INCONCLUSIVE/NOT_TESTED

~~~sql
WITH required AS (
  SELECT unit_id, asset_id, control_id
  FROM required_control_units
  WHERE lifecycle_status = 'required'
    AND environment = 'production'
    AND control_id = :target_control_id
),
recent_results AS (
  SELECT unit_id, control_id, verdict,
         ROW_NUMBER() OVER (
           PARTITION BY unit_id, control_id
           ORDER BY tested_at DESC
         ) AS rn
  FROM control_test_results
  WHERE tested_at >= :window_start
    AND tested_at < :window_end
    AND test_version = :approved_test_version
),
current_result AS (
  SELECT unit_id, control_id, verdict
  FROM recent_results
  WHERE rn = 1
)
SELECT
  COUNT(*) AS required_units,
  SUM(CASE WHEN c.verdict = 'PASS' THEN 1 ELSE 0 END) AS verified_pass,
  SUM(CASE WHEN c.verdict = 'FAIL' THEN 1 ELSE 0 END) AS confirmed_fail,
  SUM(CASE WHEN c.verdict = 'INCONCLUSIVE' THEN 1 ELSE 0 END) AS inconclusive,
  SUM(CASE WHEN c.verdict IS NULL THEN 1 ELSE 0 END) AS not_tested
FROM required r
LEFT JOIN current_result c
  ON c.unit_id = r.unit_id AND c.control_id = r.control_id;
~~~

**Giới hạn:** ví dụ giả định mỗi unit/control chỉ cần kết quả mới nhất trong cửa sổ. Với control liên tục, một FAIL đầu kỳ rồi PASS cuối kỳ không tự chứng minh toàn kỳ đã compliant. Cần **lịch sử trạng thái/duration** hoặc kiểm tra việc thực hiện nhiều lần theo kỳ.

Ngoài ra, **exception hợp lệ không tự gộp vào PASS**; cần một phép join/đánh giá riêng theo policy và thời điểm.

### 17.3. Kiểm tra asset mới thiếu nguồn telemetry

~~~sql
WITH required_assets AS (
  SELECT asset_id, service_id, criticality
  FROM asset_inventory
  WHERE status = 'active'
    AND environment = 'production'
),
sources AS (
  SELECT DISTINCT asset_id
  FROM telemetry_source_inventory
  WHERE required_event_type = 'admin-audit'
    AND validation_status = 'PASS'
    AND validated_at >= :freshness_cutoff
)
SELECT a.asset_id, a.service_id, a.criticality
FROM required_assets a
LEFT JOIN sources s ON a.asset_id = s.asset_id
WHERE s.asset_id IS NULL;
~~~

Kết quả liệt kê **asset chưa có bằng chứng telemetry đạt**, không tự chứng minh sensor hoàn toàn bị tắt. Điều tra tiếp event gốc, pipeline routing, parser và log store.

### 17.4. KPI cần có evidence lineage

Sau mỗi lần tính, record nên giữ:

~~~yaml
metric_run_id: "METRIC-RUN-2026-11-28-009"
metric_id: "KPI-SEC-LOG-001"
metric_version: "2.1"
window:
  start: "2026-11-01T00:00:00Z"
  end: "2026-11-28T00:00:00Z"
calculated_at: "2026-11-28T01:00:00Z"
population:
  unit: "production-account-x-required-event-class"
  required: 50
  verified_pass: 40
  confirmed_fail: 3
  inconclusive: 4
  not_tested: 3
value:
  verified_coverage_percent: 80.0
  quality_state: "PARTIAL_COVERAGE"
sources:
  - "inventory-snapshot/example-2026-11-28"
  - "control-test-results/example-run-009"
test_version: "logging-assurance-v4"
evidence_manifest: "restricted-evidence-store/metric-run-009"
limitations:
  - "4 units have incomplete source data"
  - "3 units have not been tested"
owner_role: "security-assurance"
~~~

Dữ liệu là ví dụ và các đường dẫn chỉ là tham chiếu minh họa. Metric record không nên chứa secret hoặc dữ liệu khách hàng không cần thiết.

## 18. Thiết kế dashboard theo đối tượng ra quyết định

### 18.1. Không có một dashboard phù hợp tất cả

| Đối tượng | Quyết định họ phải đưa ra | Chỉ số ưu tiên |
|---|---|---|
| **SOC / detection team** | Triage, tune detection, sửa nguồn log/rule | Telemetry health, alert routing, verified detection coverage, FN test, ingest lag |
| **Engineering / platform** | Sửa cấu hình, vá lỗ hổng, cải thiện pipeline | Asset coverage, baseline drift, overdue critical fixes, deployment gates |
| **Identity team** | Thu hồi quyền, sửa auth, review privilege | Effective MFA, orphaned admins, exception expiry, time to revoke |
| **Service/business owner** | Quyết định mức rủi ro và ưu tiên công việc | Critical control gaps, RTO/RPO exercise, service-specific findings |
| **Security assurance/GRC** | Chứng minh control, chuẩn bị audit, theo dõi ngoại lệ | Required control units PASS/FAIL/unknown, evidence freshness, retest |
| **CISO/management** | Phân bổ nguồn lực, chấp nhận rủi ro, xem xu hướng | Top risks, critical blockers, coverage trends, closure quality, residual risk |
| **Board/leadership** | Giám sát risk appetite và tác động nghiệp vụ | Risk exposure, incident impact, resilience readiness, material exceptions |

### 18.2. Một dashboard có cấu trúc tốt

Nên theo thứ tự câu hỏi:

1. **Coverage và chất lượng dữ liệu:** phần nào đang được quan sát đáng tin?
2. **Mục tiêu cốt lõi:** control nào đạt/chưa đạt, theo mức rủi ro?
3. **Xu hướng:** cải thiện hay xấu đi trong cùng phương pháp đo?
4. **Blockers:** những sai lệch critical nào cần quyết định?
5. **Remediation:** ai đang sửa, hạn nào, retest đến đâu?
6. **Residual risks/unknown:** phần chưa kiểm và ngoại lệ có ảnh hưởng gì?

Không nhất thiết đặt một **overall security score** ở đầu nếu nó có thể che rủi ro. Với lãnh đạo, 4–8 KPI quan trọng cùng phần diễn giải và quyết định cần duyệt thường hữu ích hơn hàng chục biểu đồ không có hành động.

### 18.3. Bộ KPI minh họa cho executive review

| Chỉ số | Kết quả giả định | Trạng thái cần chú ý | Quyết định |
|---|---:|---|---|
| Critical asset control coverage | 92/100 PASS | 3 FAIL, 5 chưa xác minh | Ưu tiên ba critical gaps và kiểm năm đơn vị chưa rõ |
| Verified detection coverage | 34/45 scenario units PASS | 6 FAIL, 5 NOT_TESTED | Bổ sung telemetry/analytic và exercise |
| Critical remediation on-time | 18/22 PASS trong kỳ | 4 quá hạn | Escalate owner theo severity |
| DR scenarios verified | 7/10 đạt | 2 FAIL, 1 NOT_TESTED | Phê duyệt capacity/remediation và lịch thử lại |
| Privileged MFA coverage | 199/200 đường PASS | 1 đường chưa đạt | Giới hạn đường admin và sửa MFA |
| Stale required evidence | 11 artifacts | Tập trung một hệ thống critical | Kiểm tra collector và refresh evidence |

Đây là **bảng minh họa không chứa kết quả thực tế**. Trong sản phẩm thật, các ngưỡng, màu trạng thái và scope phải dựa trên policy được phê duyệt, và thông tin **chưa xác minh** phải hiển thị độc lập với FAIL.

### 18.4. Drill-down và tính giải thích

Từ một KPI nên có khả năng đi tới:

- Danh sách asset/scenario thuộc mẫu số.
- Danh sách PASS, FAIL, INCONCLUSIVE, NOT_TESTED.
- Control/rule version và evidence reference.
- Thời điểm đo, freshness, chất lượng pipeline.
- Owner, finding, ngoại lệ và due date.
- Kết quả retest sau hành động.
- Lịch sử metric version và sự thay đổi mẫu số.

Không cần xuất raw secrets hoặc log chứa dữ liệu nhạy cảm cho mọi viewer. Có thể dùng masked identifiers và controlled evidence links.

## 19. Case study 1: dashboard 100% xanh do mẫu số thiếu

### 19.1. Bối cảnh

Một tổ chức có 25 cloud account production thuộc phạm vi phải gửi cloud audit log tập trung. SIEM source dashboard báo **100% nguồn healthy**. Đội assurance đối soát asset inventory độc lập và thấy chỉ 22 account tồn tại trong source registry; ba account tạo mới chưa onboard.

Trong 22 account đang có, 21 gửi event đủ chuẩn; một account có nguồn sống nhưng parser bỏ mất field bắt buộc của nhóm thay đổi IAM.

### 19.2. Đánh giá lại metric

| Tập hợp | Số account |
|---|---:|
| Required production accounts | 25 |
| Đã có source registered | 22 |
| Source kiểm chứng đủ event/field | 21 |
| Source có lỗi field fidelity | 1 |
| Chưa onboard/NOT_TESTED | 3 |

**Verified event coverage = 21/25 = 84%.**

Dashboard “100% healthy” có thể đang đo heartbeat của **22 source đã onboard**, không sai trong phạm vi metric đó, nhưng **không phải tỷ lệ coverage yêu cầu**. Nếu không phân biệt, báo cáo assurance có thể sai đáng kể.

### 19.3. Những kiểm tra cần thực hiện

1. Xác định danh sách bắt buộc từ cloud organization inventory và production service catalog.
2. Đối chiếu source ID/alias và số lượng account.
3. Phát event test có marker ở các account được phép.
4. Theo dõi source → collector → parser → index và đối chiếu field bắt buộc.
5. Mở finding cho parser sai và ba account chưa onboard theo đúng condition.
6. Sửa onboarding gate và parser; ghi change version.
7. Retest event end-to-end trên toàn scope.
8. Thêm KPI **required source coverage**, **field completeness** và **unmonitored account age**.
9. Giữ lịch sử ngày trước khi sửa, không ghi đè thành “luôn đạt 100%”.

### 19.4. Kết luận dành cho lãnh đạo

> Công cụ SIEM trước đây báo 100% source health nhưng chỉ theo dõi các account đã đăng ký. Đối soát inventory xác định 25 account bắt buộc và chỉ 21 có bằng chứng event/field đủ điều kiện, tương đương verified coverage 84%. Một source cần sửa parser, ba account cần onboarding; trong khi chưa kiểm chứng, khả năng phát hiện hành vi quản trị trên các account này bị giới hạn. Kế hoạch remediation gồm sửa pipeline, provisioning gate và retest theo từng account.

**Bài học:** KPI phải gắn **mẫu số của mục tiêu bảo mật**, không chỉ các đối tượng công cụ đã biết.

## 20. Case study 2: MTTD giảm nhưng detection có thể kém hơn

### 20.1. Hiện tượng

Một SOC báo cáo MTTD giảm từ 30 phút xuống 8 phút trong quý, số alert cũng giảm mạnh. Management cho rằng detection engineering cải thiện rõ rệt.

Kiểm tra kỹ cho thấy:

- Rule mới chỉ giữ lại nhóm alert dễ nhận diện, nhiều cảnh báo phức tạp bị suppress.
- Một số event class từ cloud accounts mới không được gửi vào SIEM.
- Định nghĩa **Tdetected** chuyển từ thời điểm analyst xác nhận incident sang thời điểm engine tạo alert.
- Các incident chưa được phát hiện không nằm trong tập tính MTTD.
- Một số vụ việc lâu điều tra vẫn đang mở và bị loại khỏi phép tính.

### 20.2. Phân tích vì sao KPI cải thiện giả

MTTD chỉ tính trên các **incident có dữ liệu đầu và cuối đủ để đo**. Khi tập phát hiện thay đổi, metric có thể giảm do loại trường hợp khó hoặc rút ngắn mốc định nghĩa, không phải phản ứng nhanh hơn.

Cần đối chiếu:

| Kiểm tra | Câu hỏi |
|---|---|
| Metric definition | Hai quý có cùng mốc bắt đầu/kết thúc không? |
| Incident population | Bao gồm nhóm severity và trạng thái nào? |
| Telemetry coverage | Source nào mất hoặc mới được thêm? |
| Detection tests | Positive/negative tests và FN có thay đổi không? |
| Suppressions | Có exception nào che nhóm rủi ro trọng yếu? |
| Open incidents | Sự cố chưa containment có bị loại khỏi thống kê không? |
| Data lag | Có event đến muộn làm thay đổi earliest observed không? |
| Risk changes | Asset/attack surface và threat scenario thay đổi không? |

### 20.3. Kết luận và hành động

Không nên tuyên bố “MTTD giảm 73%” như bằng chứng đã cải thiện nếu hai kỳ đo khác định nghĩa. Các hành động:

1. Chốt một **metric version** và định nghĩa mốc.
2. Đánh dấu điểm gãy chuỗi thời gian khi đổi logic.
3. Báo riêng các incident chưa đủ timestamps và đang mở.
4. Thêm coverage theo threat scenario và synthetic end-to-end tests.
5. Review suppression, alert routing và source inventory.
6. Đo phân phối theo severity, incident type, service và kỳ.
7. Cập nhật dashboard với data quality và giới hạn so sánh.

**Bài học:** KPI vận hành có thể đẹp lên khi hệ thống **nhìn thấy ít vấn đề hơn**. Muốn khẳng định hiệu quả detection tăng cần thêm bằng chứng kiểm thử và coverage độc lập.

## 21. Case study 3: backlog vulnerability giảm nhờ loại tài sản khỏi scanner

### 21.1. Bối cảnh

Một đội platform được giao giảm số lượng **critical vulnerabilities quá hạn**. Sau một tháng, dashboard scanner giảm từ 40 findings xuống 9. Báo cáo ghi “giảm 77,5%”.

Trong thời gian đó, đội đã chuyển 15 máy chủ quan trọng từ nhóm VM cũ sang container workloads và bỏ nguồn host inventory cũ khỏi scanner. Nhiều findings biến mất vì **asset không còn được đo**, không phải vì chúng đã được sửa hoặc rủi ro đã được loại bỏ.

### 21.2. Phân tích metric

Các câu hỏi cần làm rõ:

- 15 máy chủ cũ thực sự đã được decommission hay chỉ chuyển sang workload/host mới?
- Vulnerability ở image, thư viện, runtime hoặc host mới có được kiểm đúng công cụ?
- Những findings “đã đóng” có bằng chứng sửa/rebuild/retest hay chỉ bị đánh disappeared?
- Tổng required assets và workload types trước/sau thay đổi là bao nhiêu?
- Có tác động từ cách deduplicate findings khi đổi scanner không?
- Thời gian phơi nhiễm rủi ro trong giai đoạn chuyển đổi là bao lâu?
- Critical findings ở hạ tầng mới có được bổ sung vào mẫu số tương ứng không?

Một finding **không còn quan sát được** phải có trạng thái phù hợp (ví dụ OUT_OF_SCOPE_VERIFIED nếu asset thực sự retired, hoặc NOT_EVALUATED) thay vì tự động coi RESOLVED.

### 21.3. Điều chỉnh bộ KPI

Thay vì chỉ có **critical open findings**, nên báo đồng thời:

| KPI | Ý nghĩa |
|---|---|
| Required workload vulnerability coverage | Tỷ lệ assets/workloads bắt buộc được kiểm với phương pháp phù hợp |
| Verified critical remediation | Finding critical có retest đạt hoặc bằng chứng asset đã retired hợp lệ |
| Overdue critical exposure | Những critical findings còn tồn tại/quá hạn, theo loại asset và exposure |
| Scanner/source completeness | Các loại VM, container, image, dependency và cloud services có được thu |
| Finding disappearance without closure proof | Số finding mất khỏi nguồn mà không có nguyên nhân hợp lệ |
| Recurrence after rebuild | Lỗ hổng quay lại qua base image, dependency hoặc deploy mới |

**Bài học:** muốn giảm rủi ro, phải biết liệu đối tượng đã được bảo vệ tốt hơn hay chỉ **biến mất khỏi cách quan sát**.

## 22. Metric governance: ngăn số liệu bị thao túng và sai nghĩa

### 22.1. Goodhart's law và an toàn hệ thống

Một hiện tượng phổ biến trong quản trị: khi một chỉ số trở thành mục tiêu thưởng phạt cứng, người tham gia có thể tối ưu chỉ số thay vì mục tiêu thật.

Trong bảo mật, biểu hiện gồm:

- Hạ severity để giảm số critical findings.
- Xóa/đổi tên ticket để làm backlog nhỏ.
- Loại asset khó kiểm khỏi scope mà không phê duyệt.
- Đóng ticket sau khi merge PR nhưng không retest.
- Tăng alert threshold để giảm false positives.
- Không ghi nhận incident để tỷ lệ incident thấp.
- Dời mốc bắt đầu đo thời gian phản ứng cho đẹp.
- Bỏ các case chưa hoàn tất khỏi MTTD/MTTR.
- Cộng accepted risk vào PASS.
- Làm questionnaire thật dài để báo nhiều “câu hỏi đã trả lời”.

KPI không nên biến thành áp lực làm mất tính trung thực của evidence. Nên đánh giá **chất lượng điều tra, công khai unknown, khả năng khắc phục bền vững và giảm rủi ro thực tế**.

### 22.2. Các biện pháp quản trị dữ liệu và metric

1. **Metric catalog có version:** mọi chỉ số có công thức, người phê duyệt và effective date.
2. **Data lineage:** biết từng KPI lấy dữ liệu từ nguồn nào, qua transform nào.
3. **Mẫu số độc lập:** đối soát với asset/risk inventory thay vì dashboard tự chọn mẫu số.
4. **Change review:** thay query, rule, source hoặc scope phải có lý do và kiểm tra ảnh hưởng xu hướng.
5. **Evidence integrity:** lưu test results và input snapshots với audit trail.
6. **Separation of duties:** người vận hành control không tự ý sửa metric target hoặc loại finding khỏi denominator.
7. **Independent sampling:** định kỳ chọn mẫu để đối chiếu dashboard với dữ liệu gốc.
8. **Data quality status:** UNKNOWN, STALE hoặc PARTIAL phải được hiển thị chứ không bị che.
9. **Anti-gaming checks:** phát hiện ticket deleted, severity downgraded, deadline extended và disappearances.
10. **Business relevance review:** KPI không dẫn tới quyết định hoặc không còn đại diện rủi ro thì thay/loại có kiểm soát.

### 22.3. Leading indicators không chứng minh quan hệ nhân quả tuyệt đối

Nếu sau khi tăng MFA coverage, số incident account compromise giảm, đây là tín hiệu tích cực nhưng chưa đủ chứng minh chỉ có MFA tạo ra thay đổi. Có thể cùng lúc:

- Cải tiến detection khiến classification đổi.
- Thay đổi attack surface hoặc số lượng người dùng.
- Tăng phishing awareness.
- Đổi quy trình incident classification.
- Thay source/logging hoặc thiếu dữ liệu.
- Xu hướng threat landscape giảm/tăng độc lập.

Nên báo **association và context**, và khi đánh giá một cải tiến lớn có thể so sánh các nhóm/kỳ tương đương, xem alternative explanations. Không tự tạo causal claim từ một đường biểu đồ đi xuống.

### 22.4. Tránh metric gây xâm phạm quyền riêng tư

Security metrics có thể lấy từ endpoint activity, danh tính, nhật ký truy cập và hành vi nhân sự. Chỉ thu dữ liệu cần thiết cho security objective:

- Tổng hợp theo control/service/team ở mức phù hợp.
- Chỉ drill-down vào danh tính cá nhân khi có nhu cầu và thẩm quyền.
- Bảo vệ raw logs và bằng chứng nhạy cảm bằng phân quyền, audit và retention.
- Không xuất password, token hoặc nội dung dữ liệu khách hàng vào dashboard.
- Xác định mục đích xử lý dữ liệu, phạm vi tiếp cận và điều kiện áp dụng theo chính sách/pháp luật liên quan.

Một KPI chất lượng không cần biến mọi nhân viên thành đối tượng giám sát chi tiết thiếu căn cứ.

## 23. Độ tin cậy thống kê và so sánh xu hướng

### 23.1. Không suy rộng từ mẫu nhỏ

Ví dụ tháng này có ba incident, MTTD lần lượt 5, 9 và 80 phút. Trung bình khoảng 31,3 phút nhưng một trường hợp chi phối mạnh. Việc báo “MTTD giảm 10%” so với tháng trước có thể không có ý nghĩa nếu:

- Kỳ trước và kỳ này có incident classes khác nhau.
- Mẫu chỉ có vài sự cố.
- Một số case chưa có timestamp.
- Detection rules hoặc scope thay đổi.
- Thời gian là ước lượng từ log thiếu.

Báo số case, median, range và giới hạn, thay vì trình bày biến động nhỏ như một cải tiến chắc chắn.

### 23.2. Phân phối và tail risk

Với dữ liệu duration, có thể xem:

- Median: giá trị giữa của tập.
- Mean: trung bình, nhạy với outliers.
- p90/p95: tail latency khi có đủ mẫu và cách tính phù hợp.
- Count: kích thước tập.
- Maximum: trường hợp xấu nhất đã quan sát.
- Open/censored cases: các trường hợp chưa kết thúc.
- Segment: severity, service, threat category, time-of-day.

Nếu chỉ báo cáo một percentile cho một tuần có hai incident, người đọc có thể tưởng con số đó ổn định hơn thực tế.

### 23.3. Baseline, target và control limits

**Target** là yêu cầu mong muốn, còn **baseline** là trạng thái đo trong kỳ tham chiếu. Chúng không nhất thiết trùng nhau. Một metric có thể:

- Đang vượt target nhưng có xu hướng xấu dần.
- Chưa đạt target nhưng cải thiện đều.
- Biến động bình thường theo mùa/traffic.
- Có điểm nhảy do đổi metric definition hoặc onboarding thêm asset.
- Xuất hiện sự cố hiếm nhưng cực kỳ nghiêm trọng trong tail.

Tùy độ trưởng thành, có thể dùng trend analysis/control charts cho metric có đủ dữ liệu, nhưng không nên giả định phân phối chuẩn hoặc tính p-value tùy tiện khi tập dữ liệu thiếu/không độc lập.

### 23.4. Tỷ lệ phần trăm cần mẫu số

Phát biểu “critical findings giảm 50%” phải đi với số lượng gốc:

- Từ 2 xuống 1 là giảm 50%, nhưng một finding vẫn có thể critical.
- Từ 400 xuống 200 cũng giảm 50%, song phạm vi và tác động khác hẳn.
- Giảm từ 10 xuống 5 khi scanner mất một nửa assets không phải cải thiện đã được chứng minh.

Cần giữ **counts, denominator, scope, data quality và metric version** bên cạnh phần trăm.

## 24. Mẫu báo cáo KPI bảo mật phục vụ quyết định

Một báo cáo định kỳ nên được người đọc hiểu mà không cần mở toàn bộ log. Nhưng mỗi claim quan trọng phải cho phép truy evidence.

### 24.1. Executive summary mẫu (giả định)

> **Kỳ đánh giá:** 01–28/11/2026, phạm vi các dịch vụ production trọng yếu. Kết quả verified security control coverage đạt 92/100 đơn vị bắt buộc; ba đơn vị confirmed FAIL, năm đơn vị chưa được xác minh. Detection coverage đã có end-to-end test PASS đối với 34/45 scenario units. Có bốn finding critical quá hạn cần escalation; các correction mới triển khai chưa được cộng vào verified closure trước khi retest. Kết quả DR đạt yêu cầu ở bảy trong mười scenario units đã định nghĩa. Ưu tiên kỳ tiếp theo là sửa logging ở cloud account mới, bảo vệ một đường privileged access còn thiếu MFA và xác minh lại backup restore cho service có RTO nghiêm ngặt.
>
> **Giới hạn:** số liệu dựa trên inventory và evidence tính đến mốc chốt; năm control units chưa xác minh vẫn nằm trong mẫu số. Các kết quả test không đại diện cho mọi kỹ thuật tấn công hoặc failure mode ngoài scope. Những điều kiện rủi ro nghiêm trọng cần quyết định của owner đã được liệt kê theo finding ID.

Đây là **báo cáo hoàn toàn minh họa**.

### 24.2. Mẫu KPI report record

~~~yaml
report_id: "SEC-METRIC-2026-11"
report_version: "1.0"
period_start: "2026-11-01T00:00:00Z"
period_end: "2026-11-28T00:00:00Z"
report_cutoff_at: "2026-11-28T02:00:00Z"
scope:
  service_groups: ["business-critical-production"]
  inventory_revision: "inventory-2026-11-28"
metrics:
  - metric_id: "KPI-SEC-CTRL-001"
    version: "2.0"
    numerator: 92
    denominator: 100
    value_percent: 92.0
    confirmed_fail: 3
    inconclusive_or_not_tested: 5
    data_quality: "PARTIAL_COVERAGE"
    evidence_ref: "metric-run/ctrl-001"
  - metric_id: "KPI-SEC-DETECT-001"
    version: "1.1"
    numerator: 34
    denominator: 45
    value_percent: 75.56
    data_quality: "VALID_WITH_SCOPE"
    evidence_ref: "metric-run/detect-001"
material_findings:
  - finding_id: "F-LOG-021"
    severity: "HIGH"
    owner_role: "cloud-platform"
    decision_needed: "Approve remediation priority"
  - finding_id: "F-IAM-034"
    severity: "CRITICAL"
    owner_role: "identity-platform"
    decision_needed: "Restrict privileged access pending retest"
report_status: "DRAFT_FOR_REVIEW"
prepared_by_role: "security-assurance"
reviewer_role: "security-governance"
limitations:
  - "Metrics do not prove absence of unobserved incidents"
  - "Metric versions and inventory scope must be preserved for trend analysis"
~~~

Các số liệu, ID và finding là **ví dụ**. Bản chính thức cần có nguồn dữ liệu và phê duyệt phù hợp; YAML này không phải schema chuẩn.

### 24.3. Ba phần không nên thiếu trong báo cáo lãnh đạo

**Một là kết luận có giới hạn:** báo đúng những gì evidence hỗ trợ, không dùng câu “toàn công ty an toàn 92%”.

**Hai là rủi ro cần quyết định:** liệt kê asset/control critical FAIL, ngoại lệ quá hạn, coverage gap, finding ảnh hưởng nghiệp vụ và phương án xử lý.

**Ba là hành động có thể kiểm tra:** owner, deadline, acceptance criteria, retest và kỳ báo cáo lại.

Báo cáo không có quyết định và hành động tiếp theo dễ trở thành tài liệu trang trí, không tạo hiệu quả assurance.

## 25. Quy trình triển khai và vận hành bộ KPI

### 25.1. Giai đoạn 1 — Chọn ít chỉ số nhưng quan trọng

1. Lấy security objectives và top risks đã có trong risk register.
2. Chọn tối thiểu một KPI/KCI cho mỗi control trọng yếu.
3. Chọn KRI cảnh báo exposure mà lãnh đạo cần quyết định.
4. Định nghĩa **required population** theo asset/service/control inventory.
5. Viết metric specifications, reviewer và ngưỡng hành động.
6. Bắt đầu bằng những metric có thể chứng minh đúng bằng evidence.

**Không nên khởi đầu bằng hàng trăm chỉ số** chưa có người dùng hoặc không có nguồn đáng tin.

### 25.2. Giai đoạn 2 — Chuẩn hóa dữ liệu và kiểm tra chất lượng

- Đối soát canonical IDs và asset inventory.
- Xác định mốc event time/measurement time và reporting cutoff.
- Ghi test/query/version và evidence manifest.
- Đo completeness/freshness, tình trạng collector và missing data.
- So sánh kết quả tự động với một mẫu kiểm tra thủ công độc lập.
- Thiết lập cơ chế sửa sai và restatement có lịch sử.
- Hạn chế quyền truy cập dữ liệu gốc theo nhu cầu.

**Điều kiện chuyển tiếp:** metric không thể hiện PASS khi population thiếu hoặc collector im lặng.

### 25.3. Giai đoạn 3 — Đưa metric vào workflow

- Kết nối KPI với owner, ticket, risk register và control register.
- Tự động tạo finding khi assertion fail hoặc evidence quá hạn.
- Áp ngưỡng phù hợp mức độ nghiêm trọng và service criticality.
- Theo dõi cả triển khai sửa và retest PASS.
- Report periodical theo cùng metric version.
- Đánh giá lại sau incident, major change và threat-model update.
- Kiểm tra khả năng audit truy ngược từ biểu đồ tới evidence.

### 25.4. Giai đoạn 4 — Hiệu chỉnh theo rủi ro

Sau vài kỳ vận hành, xem:

- KPI nào tạo quyết định hữu ích hoặc phát hiện control gap sớm?
- KPI nào có quá nhiều false alerts và bị bỏ qua?
- Chỉ số nào bỏ qua trường hợp rủi ro critical?
- Khi onboarding asset mới, population có tự cập nhật đúng?
- Dashboard có bị thao túng qua deadline/severity/scope changes không?
- Kết quả sau cải tiến có được retest hoặc kiểm chứng độc lập không?

Có thể giảm số KPI nếu những chỉ số còn lại phản ánh rủi ro chính xác hơn và kích hoạt hành động hiệu quả.

### 25.5. Cadence báo cáo theo người nhận

| Nhịp vận hành | Hoạt động điển hình | Người nhận |
|---|---|---|
| Gần thời gian thực hoặc theo trigger | Source health, critical security control drift, incident alerts | SOC, platform/on-call |
| Hằng ngày hoặc theo quy trình | Critical findings, overdue SLA, collector failures | Control owners và security operations |
| Hằng tuần | Remediation progress, detection test, exception, retest backlog | Engineering leads, assurance |
| Hằng tháng | Coverage, data quality, critical risk trends và quyết định | Service owners, CISO hoặc security leadership |
| Hằng quý/theo BIA và nghĩa vụ | Control effectiveness, third-party, DR, audit findings | Risk committee, governance, audit |
| Khi có material change | Đánh giá lại scope và KPI bị ảnh hưởng | Architecture, legal/compliance, assurance |

Nhịp trên chỉ minh họa. Tần suất thật phải theo nghĩa vụ, criticality, độ biến động và khả năng tạo hành động, không dựa vào một chuẩn “mọi KPI phải cập nhật mỗi giờ”.

## 26. Những nhầm lẫn thường gặp về KPI bảo mật

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “KPI xanh nghĩa hệ thống an toàn.” | KPI chỉ đo một assertion trong scope, với dữ liệu và giới hạn. |
| “Ít incident được ghi nhận nghĩa ít tấn công.” | Có thể do thiếu visibility hoặc thay đổi tiêu chí phân loại. |
| “Ít alert hơn nghĩa detection tốt hơn.” | Rule/suppression có thể làm tăng blind spot. |
| “Nhiều rule hơn nghĩa bao phủ tốt hơn.” | Coverage dựa vào threat scenario và test thực tế, không phải rule count. |
| “Tỷ lệ 100% từ dashboard là toàn population.” | Phải kiểm tra mẫu số độc lập và missing assets. |
| “Mọi finding mất khỏi scanner nghĩa đã được vá.” | Có thể asset bị loại khỏi scope hoặc scanner ngừng hoạt động. |
| “Ticket Done đồng nghĩa vulnerability đã hết.” | Cần evidence fix/retest hoặc xác minh asset retired hợp lệ. |
| “MFA enabled trong IdP nghĩa mọi privileged path được bảo vệ.” | Local, break-glass và provider native admins có thể ngoài scope. |
| “Backup success = DR success.” | Cần restore, data integrity, IAM/KMS và business acceptance. |
| “MTTD = 8 phút là tốt hơn 10 phút ở công ty khác.” | Mốc, dữ liệu, loại incident và mẫu đo có thể khác nhau. |
| “Mean giảm là mọi sự cố được xử lý nhanh hơn.” | Tail cases và phân phối có thể vẫn xấu. |
| “Không có data là 0.” | Missing data phải thành UNKNOWN/INCONCLUSIVE theo phương pháp. |
| “Accepted risk được cộng vào PASS.” | Risk decision không thay thế control effectiveness. |
| “Một phần trăm risk-weighted là xác suất an toàn.” | Đó là điểm tổng hợp nội bộ, không phải xác suất bị tấn công. |
| “Policy-as-code PASS nghĩa runtime compliant.” | Cần kiểm drift, manual changes và assets ngoài IaC. |
| “Bảng câu hỏi vendor trả lời hết nghĩa đã được verify.” | Response completion khác assurance verdict. |
| “Có nhiều dữ liệu hơn thì KPI tự chính xác.” | Quality, provenance, scope và logic quan trọng hơn số lượng. |
| “Không cần version metric.” | Thay công thức tạo xu hướng giả. |
| “Một KPI phải là mục tiêu thưởng phạt.” | Đo quá cứng có thể khuyến khích che giấu hoặc game số. |
| “Một lần PASS chứng minh control luôn đạt.” | Cần theo dõi drift, change, incident và retest. |

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Có 100 asset phải được kiểm soát EDR, tool quản lý hiện thấy 85 asset và cả 85 có agent healthy. Có thể kết luận EDR coverage 100% không?

**Gợi ý:** Không. Theo inventory độc lập, tối đa mới có 85/100 = 85% asset được xác minh; 15 asset không xuất hiện cần điều tra/đánh NOT_TESTED hoặc INCONCLUSIVE tùy nguyên nhân.

**Câu 2.** SOC báo “false positive rate 70%” vì 70/100 alert được đóng benign. Công thức và kết luận có đúng không?

**Gợi ý:** Chưa đúng nếu không có ground truth và TN. Có thể gọi là tỷ lệ alert được phân loại benign theo quy trình, không tự bằng FP/(FP+TN).

**Câu 3.** Tháng trước có 20 incident, tháng này chỉ có 10. Có chứng minh bảo mật cải thiện 50% không?

**Gợi ý:** Không. Cần kiểm nguồn detection, classification, exposure, thời kỳ, impact và số lượng chưa được quan sát.

**Câu 4.** Trong bộ 50 detection scenario units bắt buộc, 30 PASS, 10 FAIL và 10 NOT_TESTED. Verified coverage là bao nhiêu?

**Gợi ý:** 30/50 = 60%. NOT_TESTED vẫn nằm trong mẫu số required units.

**Câu 5.** Rule detection có precision rất cao trong synthetic test nhưng incident production vẫn bị bỏ sót. Điều gì có thể xảy ra?

**Gợi ý:** Tập test thiên lệch, biến thể attack ngoài scope, thiếu telemetry, parser/routing lỗi, suppression quá rộng hoặc rule không triển khai ở production.

**Câu 6.** Một finding critical được sửa ngày 5, retest PASS ngày 9, trong khi SLA yêu cầu xác minh đóng trước ngày 7. Có đạt verified closure SLA không?

**Gợi ý:** Không nếu SLA định nghĩa phải đạt retest/closure trước ngày 7. Thời điểm correction và verified closure phải được ghi riêng.

**Câu 7.** DR test restore database xong sau 20 phút nhưng service chỉ đạt tiêu chí nghiệp vụ và bảo mật sau 80 phút. Khi đo RTO của dịch vụ nên dùng mốc nào?

**Gợi ý:** 80 phút từ mốc disruption đã được định nghĩa, nếu đây là thời điểm cuối cùng mọi điều kiện chấp nhận bắt buộc đạt.

**Câu 8.** KPI 99% baseline compliance có một tài khoản root production không được bảo vệ. Có thể cho tình trạng tổng “green” không?

**Gợi ý:** Không nên để trung bình che critical gate. Báo riêng critical FAIL và kích hoạt response/risk decision phù hợp.

**Câu 9.** Metric được đổi từ “tài khoản MFA” sang “đường đăng nhập quản trị enforce MFA”. Có thể vẽ hai kỳ trên cùng biểu đồ không chú thích không?

**Gợi ý:** Không. Đơn vị đo và denominator đã đổi; version metric và đánh dấu structural break hoặc tính lại lịch sử nếu có dữ liệu tương thích.

**Câu 10.** Một dữ liệu lỗi khiến detector không chạy ba ngày nhưng dashboard giữ trạng thái PASS gần nhất. Hệ thống metric nên làm gì?

**Gợi ý:** Kiểm data freshness và last successful run; trạng thái chuyển STALE/UNKNOWN, cảnh báo owner và đánh giá khoảng không có coverage.

**Câu 11.** Vì sao KPI “number of tickets closed” dễ gây hiểu sai?

**Gợi ý:** Có thể đóng bằng đổi trạng thái, gộp/xóa, accepted risk hoặc correction chưa retest. Cần verified closure và recurrence.

**Câu 12.** Security score có trọng số được tính chính xác đến hai chữ số thập phân. Điều đó có chứng minh xác suất xảy ra sự cố đã được ước lượng chính xác đến 0,01% không?

**Gợi ý:** Không. Điểm score dùng trọng số chính sách không phải mô hình xác suất đã hiệu chuẩn; độ chính xác hiển thị không đồng nghĩa độ tin cậy của kết luận.

## 28. Bài thực hành: thiết kế KPI dashboard cho security assurance

Giả sử bạn chịu trách nhiệm xây bộ KPI cho nền tảng thương mại điện tử có cloud accounts, Kubernetes, managed database, IdP, CI/CD, SIEM, vulnerability scanner và các nhà cung cấp SaaS. Trong kỳ đánh giá có dữ liệu giả định:

- Asset inventory độc lập ghi **60 cloud accounts production**; SIEM có 54 source được onboard, nhưng chỉ 51 source có end-to-end event test PASS.
- Có **200 privileged login paths** trong scope; 194 verified MFA, 3 confirmed FAIL và 3 chưa kiểm.
- Detection registry yêu cầu **45 scenario units**; 34 PASS, 6 FAIL, 5 NOT_TESTED.
- Vulnerability platform có 30 critical/high findings đến hạn; 23 retest PASS, 4 correction đã triển khai chưa retest, 3 quá hạn chưa sửa.
- Bộ DR có 10 required exercise units; 7 đạt, 2 FAIL, 1 chưa thử.
- SOC có 8 incident được xác nhận, nhưng hai case thiếu mốc đầu tiên và một case vẫn chưa containment.
- Một SaaS xử lý dữ liệu khách hàng mới thêm subprocessor nhưng chưa có reassessment.
- Dashboard cũ đang hiển thị “Security posture 96%” nhưng không lưu cách tính và phiên bản.

### 28.1. Yêu cầu bài tập

1. Chọn **6–8 KPI/KRI/KCI** trực tiếp phục vụ những quyết định trọng yếu của security assurance.
2. Với mỗi KPI, viết metric ID, version, objective, population, numerator, denominator, thời kỳ, data source, owner và action.
3. Tính chính xác **verified coverage** cho logging, MFA, detection, vulnerability remediation và DR, nêu ý nghĩa của phần thiếu evidence.
4. Giải thích vì sao 54 SIEM sources onboard không đồng nghĩa 54 source đủ event coverage.
5. Đề xuất **critical gates** không được phép che bằng overall score.
6. Với incident metrics, định nghĩa timestamp đầu/cuối và cách xử lý ba case có dữ liệu thiếu hoặc đang mở.
7. Xây một **metric data-quality rule** cảnh báo khi một cloud account mới chưa được onboarding.
8. Thiết kế báo cáo executive ngắn: điều đã biết, điều chưa biết, top risks, owner và quyết định cần phê duyệt.
9. Viết cách version dashboard khi bỏ “Security posture 96%” chưa rõ phương pháp.
10. Gắn các metrics với remediation tickets và phép retest chứ không dừng ở trạng thái đỏ/xanh.

### 28.2. Tính toán tham khảo

| KPI | Tử số / mẫu số | Kết quả đã xác minh |
|---|---:|---:|
| End-to-end log source coverage | 51/60 | **85%** |
| Privileged MFA verified coverage | 194/200 | **97%** |
| Detection scenario verified coverage | 34/45 | **75,6%** |
| On-time verified vulnerability remediation trong tập đến hạn | 23/30 | **76,7%** |
| DR exercise verified coverage | 7/10 | **70%** |

Kết quả không cho phép cộng các phần trăm thành một “security score” rồi khẳng định mức độ an toàn. Chúng đại diện **năm assertion và population khác nhau**. Cần nhấn mạnh 3 MFA FAIL, 6 detection FAIL, 2 DR FAIL và các phần chưa kiểm độc lập với tỷ lệ.

### 28.3. Tiêu chí đánh giá bài thực hành

| Tiêu chí | Đạt khi |
|---|---|
| **Mục tiêu** | Mỗi KPI gắn quyết định/rủi ro cụ thể |
| **Công thức** | Numerator, denominator, unit và window không mơ hồ |
| **Population** | Required scope độc lập với dữ liệu tool đang có |
| **Data quality** | Missing/stale/unknown được phản ánh rõ |
| **Security assurance** | PASS chỉ dựa vào evidence/test, không dựa vào câu trả lời tự khai |
| **Critical risk** | Các critical failures được hiển thị riêng |
| **Hành động** | Có owner, escalation, remediation và retest |
| **Báo cáo** | Có period, source, metric version, caveat và decision |
| **Ethics/privacy** | Bảo vệ log và thông tin danh tính, không lạm dụng dữ liệu |
| **Continuous monitoring** | Change trigger, drift và recurrence được đo |

## 29. Checklist triển khai KPI bảo mật

- [ ] Mỗi KPI có security objective, risk scenario và quyết định muốn hỗ trợ.
- [ ] Phân biệt KPI, KRI, KCI, SLA/SLO và metric kỹ thuật.
- [ ] Có metric catalog và versioning; không thay công thức âm thầm.
- [ ] Unit of analysis, scope, kỳ và reporting cutoff được xác định.
- [ ] Mẫu số lấy từ required inventory/control register độc lập với công cụ đo.
- [ ] Tử số chỉ tính các đơn vị đã có evidence/test đáp ứng assertion.
- [ ] PASS, FAIL, INCONCLUSIVE, NOT_TESTED, N/A và accepted risk được tách đúng.
- [ ] Zero denominator không được tự động báo 100%.
- [ ] Data quality gồm source health, freshness, completeness và parser/schema checks.
- [ ] Đường nối metric → source data → rule/query version → evidence tồn tại và kiểm tra được.
- [ ] Có dữ liệu kỳ và kiểm soát late arrival/clock drift/restatement.
- [ ] Có metric owner, control owner, risk owner và reviewer phù hợp.
- [ ] Targets/thresholds có căn cứ từ risk, BIA, control và nghĩa vụ đã phê duyệt.
- [ ] Các critical control failures không bị số trung bình che khuất.
- [ ] Dashboard hiển thị độ bao phủ, chất lượng dữ liệu và giới hạn.
- [ ] Chỉ số coverage, time to remediate và risk đều có phân tổ quan trọng.
- [ ] Thời gian MTTD/MTTA/MTTC/MTTR có định nghĩa mốc và tập incident rõ.
- [ ] Censored/open incidents và missing timestamps không bị gộp sai.
- [ ] Detection metrics có test coverage và kiểm tra false negatives, không chỉ alert count.
- [ ] Vulnerability metrics có scan coverage và verified closure, không chỉ backlog.
- [ ] IAM metrics xét effective access và đường bypass, không chỉ user count.
- [ ] DR metrics có data integrity, RTO/RPO, security gates và failback khi cần.
- [ ] Vendor metrics phân biệt questionnaire response và assurance verdict.
- [ ] Compliance metrics dựa trên applicability và evidence trong đúng kỳ.
- [ ] Finding/risk acceptance/exceptions có owner, due date, expiry và retest.
- [ ] Hệ thống KPI có giám sát chính nó: source silent, missing asset, failed calculation.
- [ ] Quy tắc chống gaming kiểm severity downgrade, deadline extension và disappearance.
- [ ] Báo cáo lãnh đạo nêu decisions required, không chỉ biểu đồ.
- [ ] Privacy/retention/access controls bảo vệ dữ liệu nguồn và bằng chứng.
- [ ] Sau incident, architecture change hoặc audit finding, KPI và giả định được đánh giá lại.

## Kết luận

**KPI bảo mật có giá trị khi đo đúng mục tiêu, đúng phạm vi, đúng kỳ và dựa trên bằng chứng có thể kiểm chứng.** Một tỷ lệ hoặc thời gian trung bình không tự chứng minh hệ thống an toàn; nó cần mẫu số đầy đủ, định nghĩa có phiên bản, chất lượng dữ liệu, bối cảnh rủi ro và phương pháp kiểm tra hiệu lực security controls.

Trong **SECURITY_SECURITY_ASSURANCE**, KPI nối **security objectives và requirements** với **control assertions, evidence, continuous monitoring, findings, remediation và retest**. Khi tổ chức biết điều gì đang được đo, điều gì chưa được quan sát, vì sao một metric thay đổi và ai phải hành động, dashboard mới trở thành công cụ ra quyết định giảm rủi ro thực sự — thay vì chỉ là những con số đẹp.


