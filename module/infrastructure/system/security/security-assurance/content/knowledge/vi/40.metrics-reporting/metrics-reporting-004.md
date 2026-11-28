# Control coverage: Đo mức bao phủ kiểm soát bảo mật và báo cáo có bằng chứng

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **control coverage** trong security assurance và phân biệt mức bao phủ với **hiệu lực kiểm soát (control effectiveness)**, mức tuân thủ, mức hoàn thành triển khai và rủi ro tồn dư.
2. Chọn đúng đơn vị đo, tập đối tượng áp dụng (**population**), mẫu số (**denominator**), khoảng thời gian, điều kiện loại trừ và quy tắc xác nhận bằng chứng.
3. Xây dựng các chỉ số bao phủ theo **tài sản, danh tính, dữ liệu, yêu cầu, threat scenarios, control objectives và thời gian**.
4. Tính tỷ lệ bao phủ đơn giản, mức bao phủ đã xác minh, khoảng trống chưa biết, trọng số theo rủi ro và xu hướng, đồng thời giải thích giới hạn của từng phép tính.
5. Thiết kế data model, evidence contract, dashboard và chuỗi truy vết **risk → requirement → control → asset → test → evidence → finding → remediation**.
6. Phát hiện những méo mó do inventory thiếu, telemetry không đầy đủ, ngoại lệ không hợp lệ, đếm trùng, mẫu số thay đổi hoặc chỉ đo cấu hình.
7. Sử dụng kết quả đo để ưu tiên remediation, kiểm thử lại và báo cáo một cách trung thực cho lãnh đạo, nhóm vận hành và auditor.

## 1. Control coverage trả lời câu hỏi gì?

**Control coverage** là mức độ mà những đối tượng, điều kiện, rủi ro hoặc yêu cầu **cần được bảo vệ** đã được một hoặc nhiều **security controls phù hợp** bao phủ, theo định nghĩa và phương pháp đo xác định.

Ví dụ:

- Trong số các tài khoản production cần MFA, có bao nhiêu tài khoản đã được policy thực sự áp dụng?
- Trong số các nguồn log security quan trọng, bao nhiêu nguồn đang tạo, truyền và lưu event đúng yêu cầu?
- Trong số các workload Kubernetes được phân loại Critical, bao nhiêu workload đã được kiểm tra và đáp ứng baseline security?
- Trong số các threat scenarios ưu tiên, bao nhiêu scenario có controls phòng ngừa, phát hiện và phản ứng được xác minh?
- Trong số các dịch vụ cần khôi phục sau thảm họa, có bao nhiêu dịch vụ đã chứng minh được khả năng đạt mục tiêu RTO/RPO?

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, control coverage giúp kiểm tra xem security objectives, rủi ro và yêu cầu đã được chuyển thành controls và bằng chứng trên **toàn bộ phạm vi cần bảo vệ** hay chưa. Đây là chỉ số quan trọng của **metrics và reporting**, nhưng không phải một phép đo duy nhất cho mức an toàn của hệ thống.

Một tỷ lệ “95% coverage” chỉ hữu ích khi người đọc biết rõ **95% của cái gì**, đối với **control nào**, **trong khoảng thời gian nào**, bằng **nguồn dữ liệu và phương pháp kiểm tra nào**, và **5% còn lại là ai hoặc cái gì**.

### 1.1. Phân biệt những khái niệm gần nhau

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Control existence** | Control có được định nghĩa hoặc được mua/cài đặt không? | Tổ chức có EDR platform. |
| **Control deployment/implementation** | Control đã được triển khai vào đối tượng trong phạm vi chưa? | Agent EDR được cài trên 900 endpoint. |
| **Control applicability** | Control có bắt buộc hoặc phù hợp với đối tượng đó không? | Agent EDR áp dụng cho 1.000 endpoint theo policy. |
| **Control coverage** | Trong population cần được bảo vệ, đối tượng nào nằm trong phạm vi control phù hợp? | 900/1.000 endpoint có agent, với định nghĩa triển khai đã xác nhận. |
| **Verified coverage** | Đối tượng nào có bằng chứng đủ mạnh rằng coverage thực sự đáp ứng tiêu chí? | 850 endpoint có agent, policy đúng, đang healthy và có telemetry xác minh. |
| **Control effectiveness** | Control có ngăn, phát hiện, đáp ứng hoặc giảm tác động như dự kiến không? | EDR thử nghiệm trên những technique ưu tiên tạo alert và phản ứng đúng. |
| **Control assurance** | Mức tin cậy của claim về control, dựa trên logic, evidence và giới hạn nào? | Scope, inventory, test, source health, reviewer, exceptions đều được ghi. |
| **Residual risk** | Sau controls, mức nguy cơ còn lại là gì? | Technique mới hoặc credential abuse chưa được kiểm soát đầy đủ. |
| **Compliance status** | Yêu cầu áp dụng có được đáp ứng theo audit criteria không? | Đạt/chưa đạt một baseline hoặc nghĩa vụ đã chọn. |

**Coverage không tự chứng minh effectiveness.** Một agent có mặt trên mọi endpoint có thể bị tắt, dùng policy sai hoặc bỏ lỡ hành vi quan trọng. Ngược lại, một control rất hiệu quả trong lab vẫn có thể không bao phủ đúng những hệ thống production cần được bảo vệ.

### 1.2. Bốn tuyên bố có sức mạnh khác nhau

Giả sử doanh nghiệp quản lý 100 VM production:

1. “Đã mua 100 EDR licenses” — chứng minh năng lực mua sắm.
2. “Có 96 VM hiển thị agent installed” — chỉ báo triển khai, còn phải xác minh inventory và trạng thái.
3. “Có 92 VM được xác nhận agent healthy, policy đúng và gửi heartbeat trong cửa sổ đã định” — bằng chứng mạnh hơn về **verified operational coverage**.
4. “Tại 92 VM đó, các detection tests theo threat model đã đạt trong phạm vi đã thử” — thêm bằng chứng về **effectiveness**.

Không nên đưa cả bốn tuyên bố dưới một nhãn “EDR coverage = 100%”.

## 2. Định nghĩa phép đo trước khi thu số liệu

Mọi metric cần một **measurement contract** được thống nhất trước khi dữ liệu được tính.

### 2.1. Các thành phần bắt buộc của measurement contract

| Thành phần | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| **Purpose/decision** | Metric hỗ trợ quyết định gì? | Ưu tiên triển khai, đánh giá assurance hay báo cáo compliance? |
| **Control objective** | Đang đo mục tiêu giảm rủi ro nào? | Ngăn truy cập admin trái phép, bảo toàn log hay phục hồi dịch vụ? |
| **Scope** | Hệ thống, business unit, account, tenant, vùng và kỳ nào? | Production hay tất cả environments? |
| **Unit of analysis** | Một dòng trong population đại diện cho gì? | Asset, asset-control pair, privileged identity, data flow hay threat scenario? |
| **Applicability rule** | Khi nào đối tượng bắt buộc chịu control? | Chỉ identity có quyền admin tương tác hoặc mọi service account? |
| **Numerator/denominator** | Điều kiện nào được tính là có coverage, tổng số gì? | Đã triển khai, healthy hay đã test effectiveness? |
| **Evidence rule** | Cần nguồn nào, độ tươi và tính đầy đủ ra sao? | Config, runtime, test, logs và khoảng thời gian kiểm tra. |
| **Status/exception** | Partial, missing, unknown, N/A và ngoại lệ xử lý thế nào? | Ngoại lệ có loại khỏi mẫu số hay báo riêng? |
| **Aggregation/weighting** | Gộp theo asset, control, business impact hoặc risk thế nào? | Có ngăn đếm trùng và giới hạn trọng số? |
| **Owner/reviewer** | Ai tạo dữ liệu, ai xác minh và xử lý findings? | Asset owner, control owner, GRC và independent reviewer. |
| **Refresh/change trigger** | Bao lâu đo lại, khi nào metric hết hiệu lực? | Asset mới, control đổi, nguồn dữ liệu lỗi, incident. |

**Cần công bố metric contract cùng kết quả**, nhất là khi báo cáo nhiều kỳ. Nếu thay mẫu số hoặc định nghĩa PASS mà không thông báo, đường biểu diễn có thể đẹp hơn dù mức bảo vệ thực tế không đổi.

### 2.2. Ví dụ contract dạng YAML

~~~yaml
metric_id: CC-IAM-PRIV-001
name: "Verified MFA coverage for human privileged identities"
objective: "Reduce unauthorized interactive privileged access"
scope:
  environments: ["production"]
  identity_population: "human principals with effective privileged access"
  population_source: "authoritative-IAM-inventory-v3"
  snapshot_at_utc: "2026-11-28T00:00:00Z"
applicability:
  required_by: "SEC-IAM-04 v3.2"
  exclusions: "only documented non-applicability under approved policy"
measurement:
  unit: "identity-control-pair"
  numerator: "verified compliant effective MFA enforcement"
  denominator: "all applicable privileged human identities"
  unknown_handling: "remain in denominator, never count as covered"
  partial_handling: "report separately"
  exception_handling: "separate approved exception count"
evidence:
  sources:
    - "effective IAM privileges"
    - "IdP conditional access configuration"
    - "authorization and sign-in validation"
  maximum_age: "defined-by-assurance-policy"
outputs:
  - verified_coverage_rate
  - implemented_unverified_rate
  - uncovered_count
  - unknown_count
  - exception_count
  - population_completeness
owner: "identity-platform"
reviewer: "security-assurance"
~~~

Mẫu mang tính **minh họa**, không phải schema của một công cụ. Thời hạn evidence, cách đo privilege và các loại trừ phải lấy từ policy và nhu cầu thực của tổ chức; các nhãn trong YAML không tự chứng minh dữ liệu đã đủ.

## 3. Chọn đơn vị đo và population: phần quyết định chất lượng

Một lỗi phổ biến là đo sai **mẫu số**. Tổ chức có thể tính 90 agent installed / 90 devices trong công cụ EDR, trong khi inventory độc lập xác định có 120 thiết bị cần được bảo vệ. Dashboard EDR hiển thị **100%**, nhưng tỷ lệ triển khai đối với population thực là **75%**.

### 3.1. Những đơn vị đo thường gặp

| Đơn vị đo | Khi phù hợp | Ví dụ metric |
|---|---|---|
| **Asset** | Một control áp dụng nhất quán cho từng tài sản. | Số production VM có EDR healthy / số VM cần EDR. |
| **Identity** | Truy cập và xác thực là đối tượng chính. | Human privileged identities được MFA enforce / tổng identities áp dụng. |
| **Asset–control pair** | Các tài sản cần nhiều controls khác nhau. | Pairs đã verified / tất cả pairs applicable. |
| **Requirement–control mapping** | Đánh giá độ bao phủ yêu cầu. | Security requirements trọng yếu có controls và tests phù hợp. |
| **Threat scenario / attack path** | Đánh giá việc giảm rủi ro theo kỹ thuật đe dọa. | Scenario ưu tiên có prevention/detection/response đã thử. |
| **Data flow / trust boundary** | Đánh giá data protection, authorization và vendor integration. | Luồng dữ liệu nhạy cảm có enforcement và audit đúng policy. |
| **Business service** | Báo cáo mức bảo vệ của khả năng kinh doanh. | Dịch vụ Critical có DR restore exercise đạt RTO/RPO. |
| **Event/time interval** | Control cần hoạt động liên tục. | Tỷ lệ thời gian log source healthy hoặc tỷ lệ event có audit theo scope. |

Một hệ thống có nhiều controls có thể đóng góp nhiều **asset–control pairs**. Nếu một báo cáo dùng asset count còn báo cáo khác dùng pair count, không được so sánh hai tỷ lệ mà không chuẩn hóa.

### 3.2. Applicability không đồng nghĩa “mọi control cho mọi asset”

Không phải mọi workload cần cùng bộ controls:

- Human interactive admin có thể cần MFA, approval và session monitoring.
- Service identity không tương tác có thể cần workload identity, short-lived tokens, secret rotation và permission boundaries thay vì cùng một MFA flow.
- Database chứa PII cần encryption, key management, audit và retention phù hợp.
- Stateless frontend có thể không cần backup dữ liệu như transactional DB, nhưng cần khả năng redeploy, configuration và recovery.
- Kubernetes pods được quản lý bởi policy khác endpoint Windows, dù cùng mục tiêu giảm đặc quyền.

Vì vậy cần map **asset type → control applicability → control objective**. Tự loại một asset khỏi mẫu số vì control không hỗ trợ kỹ thuật **không tự làm nó Not applicable**; có thể đây là khoảng trống coverage hoặc nhu cầu compensating control.

### 3.3. Status của từng cặp asset–control

Đề xuất các trạng thái **loại trừ lẫn nhau tại cùng thời điểm**:

| Status | Điều kiện | Tính vào verified numerator? |
|---|---|---|
| **VERIFIED_COVERED** | Control áp dụng và đã có bằng chứng thỏa tiêu chí coverage. | Có. |
| **IMPLEMENTED_UNVERIFIED** | Có dấu hiệu đã cấu hình/triển khai nhưng chưa đủ evidence xác nhận. | Không. |
| **PARTIALLY_COVERED** | Một số đường, cấu phần hoặc điều kiện được bảo vệ nhưng chưa đáp ứng đầy đủ. | Không trong tỷ lệ full coverage; báo riêng. |
| **UNCOVERED** | Control áp dụng nhưng không hiện diện hoặc không thỏa yêu cầu coverage. | Không. |
| **UNKNOWN** | Không thể xác định tình trạng do mất source, sai inventory, thiếu quyền hoặc dữ liệu. | Không. |
| **NOT_APPLICABLE** | Có căn cứ đã phê duyệt rằng yêu cầu không áp dụng. | Không nằm trong mẫu số applicable, nhưng phải lưu lý do. |

**Approved exception/waiver** nên là **thuộc tính quản trị riêng** (exception ID, owner, thời hạn, compensating controls), không phải một status bảo vệ tương đương VERIFIED_COVERED. Nếu chính sách cho phép con đường control thay thế và bằng chứng đáp ứng đầy đủ, có thể đánh giá theo **alternative control criterion** đã phê duyệt; không tự loại khỏi mẫu số để làm tỷ lệ đẹp hơn.

### 3.4. Mẫu số phải đến từ nguồn có thẩm quyền

Tùy đối tượng, nguồn population có thể gồm:

- CMDB/asset inventory kết hợp cloud resource discovery.
- Kubernetes API, cluster inventory và lịch thay đổi workload.
- IAM/IdP effective permissions và service principal inventory.
- Data catalog, data lineage, object storage inventory và danh mục luồng dữ liệu.
- CI/CD, artifact inventory, software bill of materials và deployment history.
- Risk register, threat model, security requirement register.
- Business service catalog, BIA và criticality classification.

Cần **đối chiếu nhiều nguồn khi có thể**. Một công cụ chỉ nhìn thấy tài sản đã cài agent không thể tự xác nhận rằng các tài sản chưa cài agent không tồn tại.

## 4. Công thức coverage và cách diễn giải

Ký hiệu:

- **A**: tập các đơn vị đo được xác nhận *applicable* trong phạm vi.
- **V**: tập các đơn vị applicable có trạng thái VERIFIED_COVERED.
- **I**: tập applicable IMPLEMENTED_UNVERIFIED.
- **P**: tập applicable PARTIALLY_COVERED.
- **U**: tập applicable UNCOVERED.
- **Q**: tập applicable UNKNOWN.

Các tập V, I, P, U, Q phải không chồng lấn và hợp thành A tại mốc đánh giá theo quy tắc đã chọn.

### 4.1. Verified coverage

\[
\text{Verified coverage}=\frac{|V|}{|A|}\times 100\%
\]

Đây là một chỉ số bảo thủ, chỉ tính khi evidence đủ theo metric contract.

**Implemented coverage**, nếu tổ chức cần theo dõi tiến độ triển khai, có thể được định nghĩa:

\[
\text{Implemented or verified coverage}
=\frac{|V|+|I|}{|A|}\times100\%
\]

Tuy nhiên, tỷ lệ này **không phải verified coverage**; việc có dấu hiệu triển khai mà chưa đủ chứng cứ không được ngầm chuyển thành đạt assurance.

### 4.2. Gaps và unknowns

\[
\text{Uncovered rate}=\frac{|U|}{|A|}\times100\%
\]

\[
\text{Unknown rate}=\frac{|Q|}{|A|}\times100\%
\]

\[
\text{Partial rate}=\frac{|P|}{|A|}\times100\%
\]

Nếu mỗi đối tượng applicable có đúng một status và không chồng lấn thì tổng các tỷ lệ V, I, P, U, Q bằng 100% (ngoại trừ sai số làm tròn).

**Điểm quan trọng:** UNKNOWN không được chuyển sang NOT_APPLICABLE chỉ vì hệ thống không phát hiện được agent hoặc collector không trả dữ liệu.

### 4.3. Điều kiện mẫu số bằng 0

Nếu số đối tượng applicable bằng 0, tỷ lệ **không có giá trị toán học**; báo **N/A — zero applicable population** kèm căn cứ, không mặc định 100%.

Cần phân biệt:

- Không có đối tượng phải áp dụng sau khi xác minh inventory và quy tắc applicability.
- Không biết có đối tượng hay không vì inventory lỗi.
- Có đối tượng nhưng chưa phân loại applicable.

Ba trường hợp này dẫn tới kết luận assurance khác nhau.

### 4.4. Ví dụ tính đơn giản

Giả sử có 50 production endpoints cần EDR:

- 42 VERIFIED_COVERED.
- 4 IMPLEMENTED_UNVERIFIED.
- 2 PARTIALLY_COVERED.
- 1 UNCOVERED.
- 1 UNKNOWN.

Khi đó:

| Metric | Tính toán | Kết quả |
|---|---:|---:|
| Verified coverage | 42 / 50 | **84%** |
| Implemented or verified coverage | (42 + 4) / 50 | **92%** |
| Partial coverage | 2 / 50 | **4%** |
| Uncovered | 1 / 50 | **2%** |
| Unknown | 1 / 50 | **2%** |

Công bố đầy đủ trạng thái giúp reviewer không nhầm **92% đã có dấu hiệu triển khai** với **84% đã được xác minh**. Tổng V, I, P, U, Q bằng 50; ví dụ không có loại trừ N/A.

## 5. Nhiều chiều coverage: số nào dùng cho quyết định nào?

### 5.1. Asset coverage

Đo phần trăm tài sản cần bảo vệ đã được control áp dụng. Hữu ích cho triển khai agent, network policy, hardening, encryption, logging và backup.

Nhược điểm: nếu mọi tài sản được trọng số bằng nhau, một hệ thống thử nghiệm ít quan trọng có thể che một hệ thống giao dịch Critical chưa được bảo vệ.

### 5.2. Requirement/control-objective coverage

Một yêu cầu bảo mật có thể cần nhiều controls. Ví dụ “ngăn lạm dụng quyền quản trị” cần identity, approval, least privilege, logging và detection. Chỉ mapping yêu cầu tới **một control bất kỳ** không đủ.

Đề xuất phân biệt:

- **Mapped requirement:** đã xác định controls dự định bảo vệ yêu cầu.
- **Implemented requirement:** controls cần thiết đã triển khai trong scope.
- **Verified requirement:** tất cả điều kiện cần của requirement đã được kiểm chứng.
- **Effectiveness-assessed requirement:** có test đủ phù hợp với risk scenarios và kỳ.
- **Uncovered requirement:** yêu cầu chưa có cơ chế phù hợp hoặc không có bằng chứng.

Một requirement có thể được xem là verified chỉ khi đáp ứng **logic kết hợp** đã phê duyệt. Nếu cần cả prevent và detect, không dùng phép OR tùy tiện.

### 5.3. Threat-scenario coverage

Một threat scenario có thể gồm nhiều attack paths. Ví dụ đánh cắp credential dẫn đến:

1. Đăng nhập trái phép.
2. Chuyển session hoặc lạm dụng OAuth grant.
3. Tăng quyền IAM/RBAC.
4. Đọc dữ liệu nhạy cảm.
5. Đẩy dữ liệu ra ngoài qua API hoặc egress.

Coverage theo scenario nên hỏi:

- Attack paths ưu tiên đã được threat model hóa và owner xác nhận chưa?
- Mỗi path có controls prevent, detect, respond nào?
- Có test case tạo được hành vi hoặc mô phỏng đủ gần để kiểm tra control không?
- Có điều kiện bypass, event thiếu, suppression, allowlist hoặc exception?
- Có cơ chế quản lý residual risk với những path không được bao phủ?

**Một detection rule gắn nhãn technique không chứng minh toàn bộ technique được bao phủ.** Rule có thể chỉ phát hiện một biến thể, trên một log source, ở một platform hoặc sau một số bước attack.

### 5.4. Data-flow và trust-boundary coverage

Đơn vị đo là đường truyền/điểm xử lý dữ liệu thuộc phạm vi, như:

- API từ internet tới application.
- Workload tới database chứa PII.
- Export từ nội bộ tới SaaS bên thứ ba.
- CI/CD tới production cloud account.
- Backup data tới vault bên ngoài fault domain.

Một đường cần nhiều điều kiện: authorization, encryption, allowed data fields, egress control và audit. Chỉ có TLS trên đường truyền không đủ để tuyên bố **data protection coverage** đạt đầy đủ.

### 5.5. Time-based coverage

Nhiều controls thay đổi theo thời gian: agent healthy, audit pipeline, token policy, backup schedule, detection service.

Tại mốc 10:00, source healthy không chứng minh nó healthy cả tháng. Khi yêu cầu control phải hoạt động liên tục, cần đo:

\[
\text{Observed healthy-time coverage}
=\frac{\text{thời lượng healthy đã xác minh}}
{\text{tổng thời lượng phải hoạt động trong phạm vi}}\times100\%
\]

Cần định nghĩa đơn vị thời gian, nguồn heartbeat, khoảng trống quan sát, planned maintenance và điều kiện ngoại lệ. Nếu nguồn giám sát tự ngừng hoạt động, không thể coi khoảng thời gian **không có telemetry** là healthy.

Ví dụ 30 ngày có 720 giờ, source log được xác minh healthy 700 giờ, có 10 giờ confirmed unhealthy và 10 giờ không đủ evidence. Verified time coverage = 700/720 ≈ **97,22%**, không phải 710/720 hay 100%.

## 6. Control coverage và effectiveness: hai trục khác nhau

Một control có thể triển khai đầy đủ nhưng không phát huy tác dụng, hoặc rất hiệu quả tại một vùng nhỏ mà chưa có mặt trên toàn bộ population.

| | Effectiveness chưa chứng minh / thấp | Effectiveness được xác minh phù hợp |
|---|---|---|
| **Coverage thấp** | Lỗ hổng lớn: nhiều đối tượng không được bảo vệ, hiệu lực cũng thiếu bằng chứng. | Control có hiệu lực trong phạm vi nhỏ; ưu tiên mở rộng nếu phù hợp. |
| **Coverage cao** | Mọi nơi có control nhưng rule/agent/policy có thể sai hoặc chưa test. | Trạng thái mong muốn hơn, nhưng vẫn phải xem gaps, threats chưa biết và thời điểm. |

Ví dụ với WAF:

- 100% API đều đi qua WAF: chỉ báo routing/coverage.
- WAF đã bật một tập rule: chỉ báo configuration.
- Test các payload đại diện trong scope cho thấy rule chặn đúng, không làm hỏng traffic hợp lệ: chỉ báo effectiveness.
- Logging/alert được gửi và response xử lý: chỉ báo operational readiness.

Không báo “100% WAF security” từ việc DNS trỏ qua WAF. Cần phân biệt controls giúp phòng ngừa, phát hiện, phản ứng và phục hồi.

### 6.1. Coverage hierarchy

Một mô hình trưởng thành có thể theo dõi:

1. **Declared:** control được yêu cầu theo policy/architecture.
2. **Mapped:** asset hoặc requirement được gắn control owner và phương án.
3. **Deployed:** có cấu hình/artifact.
4. **Operating:** có bằng chứng runtime/telemetry.
5. **Tested:** đạt các test theo control contract.
6. **Sustained:** hoạt động trong kỳ đo và có drift/health monitoring.

Không bắt buộc mọi chương trình dùng sáu nhãn. Nhưng phải công bố **metric đang đo tầng nào**. Trộn các tầng làm tỷ lệ không thể so sánh.

### 6.2. Assurance argument cho coverage

~~~mermaid
flowchart TD
    G["Claim: control C được bao phủ đủ trên population P trong kỳ T"]
    S["Strategy: applicability, inventory, implementation, validation"]
    A["Subclaim A: P đầy đủ và đúng scope"]
    B["Subclaim B: C áp dụng cho từng đối tượng cần bảo vệ"]
    C["Subclaim C: C được triển khai đúng ở các đối tượng covered"]
    D["Subclaim D: C đáp ứng quy tắc verified trong kỳ T"]
    E1["Evidence: authoritative inventory + reconciliation"]
    E2["Evidence: policies + applicability decision"]
    E3["Evidence: effective configuration + runtime state"]
    E4["Evidence: tests, telemetry health, review"]
    G --> S
    S --> A
    S --> B
    S --> C
    S --> D
    A --> E1
    B --> E2
    C --> E3
    D --> E4
~~~

Nếu thiếu bằng chứng cho **population completeness**, top claim có thể chưa đủ assurance dù mọi đối tượng **đã được nhìn thấy** đều hiển thị healthy.

## 7. Risk-weighted coverage và những giới hạn

Khi các đơn vị đo có mức độ quan trọng khác nhau, có thể dùng **risk-weighted coverage** để ưu tiên đầu tư và báo cáo. Tuy nhiên phải chọn trọng số trước khi thấy kết quả, ghi nguồn phê duyệt và không biến nó thành một thước đo định lượng tuyệt đối của rủi ro.

### 7.1. Công thức

Với mỗi đơn vị applicable i, định nghĩa:

- w(i): trọng số không âm, phản ánh criticality hoặc mức ưu tiên theo chính sách.
- v(i) = 1 nếu VERIFIED_COVERED, ngược lại bằng 0.

\[
\text{Risk-weighted verified coverage}
=\frac{\sum_{i\in A} w(i)\,v(i)}{\sum_{i\in A}w(i)}\times100\%
\]

Giá trị chỉ có ý nghĩa khi mẫu số trọng số dương và cách tạo weights minh bạch. Trọng số có thể đến từ BIA, data sensitivity, privilege hoặc severity của threat scenario; cần tránh **đếm trùng trọng số** khi một mục được đánh giá theo nhiều chiều.

### 7.2. Ví dụ

| Tài sản | Criticality weight | Verified? |
|---|---:|---|
| Payment DB | 5 | Có |
| Order API | 5 | Không |
| Internal wiki | 1 | Có |
| Static help page | 1 | Có |

Unweighted coverage = 3/4 = **75%**.

Risk-weighted coverage = (5 + 1 + 1)/(5 + 5 + 1 + 1) = 7/12 ≈ **58,33%**.

Chênh lệch cho thấy lỗ hổng tại **Order API** ảnh hưởng đáng kể. Tuy nhiên:

- Điểm 5 và 1 là chính sách ưu tiên tương đối, không phải số tiền tổn thất hay xác suất tấn công.
- Một lỗ hổng severity cao ở Payment DB dù coverage reported verified vẫn cần đánh giá risk riêng.
- Mô hình trọng số thay đổi qua kỳ có thể làm metric thay đổi dù controls không đổi.
- Không để nhiều tài sản trọng số thấp **che** một dịch vụ Critical không được bao phủ; nên hiển thị critical gaps riêng.

### 7.3. Các mức coverage không thể thay thế nhau

- **Asset-weighted** trả lời mức bao phủ theo criticality tài sản.
- **Control-family-weighted** phân biệt IAM, data protection, logging, DR theo trọng số policy.
- **Threat-risk-weighted** ưu tiên scenarios có tác động và likelihood cao.
- **Business-service-weighted** tính mức ảnh hưởng tới các khả năng kinh doanh.

Không trộn hoặc cộng các tỷ lệ này vào một “security coverage score” nếu chưa có mô hình rõ về đơn vị, điều kiện và mức phụ thuộc. Một điểm tổng duy nhất có thể che những failure modes quan trọng.

## 8. Kiểm tra completeness của population và evidence

### 8.1. Những nguồn dễ gây thiếu denominator

| Nguồn chính | Lỗ hổng thường gặp | Cách đối chiếu |
|---|---|---|
| **Cloud asset inventory** | Bỏ region, subscription/account, ephemeral instance. | Cloud APIs theo danh sách accounts/regions; đối chiếu billing, tags, CMDB. |
| **Kubernetes inventory** | Chỉ nhìn Deployment mà bỏ Job, CronJob, DaemonSet, namespace hoặc cluster khác. | API resources, ownerReferences, admission/audit và discovery. |
| **IAM inventory** | Chỉ đếm human users, bỏ service accounts, roles, nested groups, delegated admin. | Effective permissions, SSO, IAM trust relationships và audit history. |
| **EDR console** | Chỉ thấy máy có agent; máy chưa cài biến mất khỏi dashboard. | CMDB, MDM, hypervisor/cloud inventory, network discovery hợp lệ. |
| **SIEM source list** | Chỉ thấy connector có dữ liệu; nguồn chưa bật log hoặc mất heartbeat không hiển thị. | Authoritative source register, heartbeat/canary, logging configuration. |
| **Data catalog** | Bỏ shadow exports, object versions, SaaS, backups, data pipeline tạm. | Data lineage, DLP/egress, storage discovery, vendor register. |
| **Risk/threat register** | Scenario không được đưa vào vì chưa ai model hóa. | Architecture review, incident lessons learned, independent threat modeling. |

**Coverage 100% đối với nguồn quan sát sai** vẫn có thể là coverage thấp đối với thực tế. Cần đo hoặc ghi **population completeness confidence** riêng thay vì cố ép thành một tỷ lệ đã xác minh khi không có nguồn độc lập.

### 8.2. Evidence freshness và monitoring health

Mỗi verified coverage claim cần metadata:

- Thời điểm collection và kỳ đánh giá.
- Nguồn, API/query, tool/version, commit của policy hoặc test.
- Tài sản và trạng thái effective control.
- Timestamp có độ tin cậy và timezone.
- Coverage của collector/source và những lỗi truy xuất.
- Thời hạn chứng cứ còn phù hợp theo control risk.
- Reviewer/owner, exception và finding liên quan.

Nếu một kết quả test quá cũ so với tần suất thay đổi của môi trường, không tự giữ **VERIFIED_COVERED** vô thời hạn. Cần revalidate hoặc chuyển sang trạng thái chưa được xác minh theo measurement contract.

### 8.3. Giám sát đo lường cũng cần monitoring

Metric pipeline có thể hỏng do:

- API bị rate limit và bỏ qua phân trang.
- Parser schema drift làm mất các trường.
- Nguồn asset inventory bị chậm đồng bộ.
- Event-time và ingest-time bị trộn.
- Service account đọc dữ liệu bị giảm quyền.
- Dedupe/aggregation sai khiến một asset có nhiều dòng.
- Query loại asset thiếu telemetry ra khỏi population.

Cần dữ liệu về **collection success**, **source coverage**, **last successful refresh**, **parser errors**, **unmatched asset IDs** và **stale evidence**. Thiếu hệ đo chính là một loại assurance gap phải báo.

## 9. Data model: từ asset–control mapping tới metric

### 9.1. Mô hình dữ liệu logic

~~~mermaid
flowchart LR
    R["Risk / threat scenario"] --> REQ["Security requirement"]
    REQ --> CTL["Control definition & acceptance"]
    INV["Authoritative asset/identity/data-flow inventory"] --> APP["Applicability mapping"]
    CTL --> APP
    APP --> ASMT["Coverage assessment per unit"]
    TEST["Control test result"] --> ASMT
    EV["Evidence + provenance"] --> ASMT
    ASMT --> MET["Metrics and segment views"]
    ASMT --> FIND["Finding and remediation"]
    FIND --> RETEST["Retest / validation"]
    RETEST --> ASMT
~~~

Mỗi dòng **coverage assessment** nên có khóa duy nhất:

**(unit_type, unit_id, control_id, assessment_period hoặc snapshot)**.

Nếu asset có nhiều versions/configurations trong cùng kỳ, cần mô hình event/time hoặc version riêng để không làm mất lịch sử.

### 9.2. Ví dụ JSON của một assessment

~~~json
{
  "assessment_id": "CCA-2026-11-00017",
  "metric_id": "CC-LOG-CRITICAL-01",
  "control_id": "CTRL-LOG-002",
  "unit_type": "log-source",
  "unit_id": "k8s-prod-api-audit",
  "business_service": "order-platform",
  "criticality": "critical",
  "applicability": {
    "status": "applicable",
    "source": "LOG-BASELINE-v3",
    "reason": "production privileged API activity"
  },
  "scope": {
    "environment": "production",
    "cluster": "prod-cluster-a",
    "observed_from_utc": "2026-11-01T00:00:00Z",
    "observed_to_utc_exclusive": "2026-12-01T00:00:00Z"
  },
  "coverage": {
    "status": "PARTIALLY_COVERED",
    "reason": "event heartbeat healthy but admin verbs missing",
    "test_case_ids": ["LOG-T01", "LOG-T02"]
  },
  "evidence": {
    "sources": ["EV-SOURCE-01", "EV-CANARY-07"],
    "collector_version": "collector-example-2",
    "reviewed_at_utc": "2026-11-28T12:00:00Z",
    "quality": "sufficient-to-establish-partial-coverage"
  },
  "exception_id": null,
  "finding_id": "FIND-LOG-017",
  "owner": "platform-logging"
}
~~~

Dữ liệu giả định này thể hiện một source **có heartbeat nhưng thiếu các hành vi quan trọng**. Không được đánh dấu VERIFIED_COVERED chỉ vì source xuất hiện trong SIEM.

### 9.3. Quy tắc chất lượng dữ liệu

- Mỗi asset/control/snapshot có một record hiệu lực hoặc cơ chế giải quyết lịch sử rõ ràng.
- Giá trị applicability có nguồn và người phê duyệt.
- UNKNOWN không bị loại khi lấy tổng.
- Một finding có thể liên kết nhiều units nhưng không được đếm trùng nếu đếm asset gaps.
- Dữ liệu stale được đánh dấu; không dùng evidence đã hết hiệu lực để giữ trạng thái VERIFIED.
- Record bị lỗi parse phải được đưa vào **data-quality exception**, không lặng lẽ bỏ.
- Nếu nguồn đổi ID asset, cần mapping alias/version thay vì tính là asset mới.
- Population change phải được báo cáo riêng cho metrics so sánh.

## 10. Ví dụ SQL tính verified coverage

Giả sử có bảng đánh giá đã được chuẩn hóa với các cột:

- **period_id, unit_id, control_id, applicability, coverage_status, criticality, evidence_valid**.
- Mỗi cặp unit-control trong một period có **đúng một dòng đã được reconcile**; nếu chưa, phải làm sạch trước.
- Applicability được xác nhận từ nguồn inventory và policy, không suy từ control console.

~~~sql
SELECT
    period_id,
    control_id,
    SUM(CASE WHEN applicability = 'APPLICABLE'
             THEN 1 ELSE 0 END) AS applicable_units,
    SUM(CASE WHEN applicability = 'APPLICABLE'
              AND coverage_status = 'VERIFIED_COVERED'
              AND evidence_valid = 1
             THEN 1 ELSE 0 END) AS verified_units,
    SUM(CASE WHEN applicability = 'APPLICABLE'
              AND coverage_status = 'UNKNOWN'
             THEN 1 ELSE 0 END) AS unknown_units,
    SUM(CASE WHEN applicability = 'APPLICABLE'
              AND coverage_status = 'UNCOVERED'
             THEN 1 ELSE 0 END) AS uncovered_units,
    ROUND(
        100.0 *
        SUM(CASE WHEN applicability = 'APPLICABLE'
                  AND coverage_status = 'VERIFIED_COVERED'
                  AND evidence_valid = 1
                 THEN 1 ELSE 0 END)
        / NULLIF(
            SUM(CASE WHEN applicability = 'APPLICABLE'
                     THEN 1 ELSE 0 END),
            0
        ),
        2
    ) AS verified_coverage_pct
FROM normalized_control_assessments
GROUP BY period_id, control_id
ORDER BY period_id, control_id;
~~~

SQL này chỉ minh họa phép tổng hợp; cú pháp NULLIF/ROUND phổ biến nhưng chi tiết có thể khác giữa hệ quản trị. **Điều quan trọng không phải truy vấn mà là chất lượng bảng đầu vào**.

### 10.1. Negative test cho metric pipeline

Hệ thống tính metrics nên có các test dữ liệu:

1. Thêm một asset applicable chưa có control vào inventory — denominator phải tăng, tỷ lệ không được tăng.
2. Cố ý làm mất một trang API export — collection phải báo lỗi/gap, không được công bố kết quả 100%.
3. Đưa hai record trùng cùng asset-control-period — phải deduplicate theo rule, không đếm gấp đôi.
4. Cho evidence hết hạn — verified numerator phải giảm hoặc chuyển đánh giá sang cần xác minh.
5. Đổi một record từ applicable sang N/A không có approval — phải bị chặn/cảnh báo.
6. Tắt nguồn telemetry và không gửi heartbeat — trạng thái phải chuyển unknown/unhealthy theo rule, không giữ healthy.
7. Thêm account/cluster/region mới — phải đưa vào population hoặc báo out-of-scope có chủ đích và rationale.
8. Đưa một exception hết hạn — không được tính như đáp ứng control.
9. Với denominator = 0 — trả N/A hoặc NULL có căn cứ thay vì chia 0 hoặc mặc định 100.
10. Thêm một control không áp dụng — không được tự ý làm mẫu số nhiều hơn nếu applicability đã xác nhận sai.

## 11. Tình huống xuyên suốt: dashboard cho nền tảng Order Platform

### 11.1. Bối cảnh

Một công ty vận hành Order Platform với các API, database, workers, Kubernetes clusters và cloud accounts. Nhóm security assurance cần báo cáo mức bao phủ các security controls trọng yếu:

- **IAM:** quyền đặc quyền và xác thực theo policy.
- **LOG:** thu thập và giám sát audit từ nguồn trọng yếu.
- **BKP:** có khả năng backup/restore cho dữ liệu cần bảo toàn.
- **DR:** khả năng khôi phục dịch vụ Critical theo mục tiêu đã duyệt.

Dữ liệu minh họa cho một kỳ đánh giá sau khi đối chiếu authoritative inventory:

| Control family | Applicable units | VERIFIED_COVERED | IMPLEMENTED_UNVERIFIED | UNCOVERED | UNKNOWN / PARTIAL |
|---|---:|---:|---:|---:|---:|
| IAM | 10 | 8 | 1 | 1 | 0 |
| Logging | 10 | 7 | 1 | 2 | 0 |
| Backup/restore | 6 | 4 | 1 | 1 | 0 |
| Disaster recovery | 4 | 2 | 1 | 1 | 0 |
| **Tổng số pairs** | **30** | **21** | **4** | **5** | **0** |

**Lưu ý:** 30 là **số cặp đơn vị–control áp dụng**, không phải 30 hệ thống khác nhau. Một hệ thống có thể xuất hiện nhiều hàng nếu có nhiều control objectives.

### 11.2. Tính số liệu và giải thích

| Metric | Cách tính | Kết quả |
|---|---:|---:|
| **Overall verified coverage** | 21 / 30 | **70,00%** |
| **Implemented-or-verified coverage** | (21 + 4) / 30 | **83,33%** |
| **Uncovered rate** | 5 / 30 | **16,67%** |
| **IAM verified** | 8 / 10 | **80%** |
| **Logging verified** | 7 / 10 | **70%** |
| **Backup/restore verified** | 4 / 6 | **66,67%** |
| **DR verified** | 2 / 4 | **50%** |

**Cách diễn giải phù hợp:** “Trong 30 cặp đơn vị–control thuộc phạm vi được xác định và đối chiếu, 21 cặp có verified coverage theo contract; bốn cặp có dấu hiệu triển khai nhưng thiếu xác nhận, năm cặp chưa được bao phủ.”

**Cách diễn giải sai:** “70% hệ thống trong công ty an toàn” hoặc “70% các cuộc tấn công được ngăn chặn”. Cả hai phát biểu đều vượt quá ý nghĩa của số đo.

### 11.3. Risk-weighted coverage

Giả sử chính sách minh họa quy định trọng số cố định theo control family: IAM = 3, Logging = 3, Backup = 5, DR = 5.

- Tổng trọng số applicable = 10×3 + 10×3 + 6×5 + 4×5 = **110**.
- Tổng trọng số verified = 8×3 + 7×3 + 4×5 + 2×5 = **75**.
- Weighted verified coverage = 75/110 ≈ **68,18%**.

Chỉ số giảm so với 70% vì những control data recovery có trọng số cao vẫn thiếu coverage. Trọng số ở đây chỉ là **quy ước ưu tiên minh họa**, không phải mức nguy cơ định lượng.

### 11.4. Những phát hiện quan trọng ẩn sau tỷ lệ

| Gap | Điều kiện quan sát | Tác động tiềm ẩn | Owner và kiểm chứng cần làm |
|---|---|---|---|
| IAM-09 | Một service/human privilege path chưa được policy phê duyệt áp dụng đủ. | Có thể tăng quyền ngoài quy trình. | Identity owner; test effective policy, review approval và access deny. |
| LOG-08 | Một nguồn admin audit có collector nhưng chưa chứng minh source health trong kỳ. | Không thể xác nhận detection coverage. | Logging owner; heartbeat/canary, đối chiếu raw event và alert. |
| LOG-10 | Một nguồn audit thuộc scope không gửi log. | Mất visibility ở hệ thống quan trọng. | Cloud/platform owner; bật source, test end-to-end, đánh giá gap. |
| BKP-06 | Database có backup job nhưng chưa restore được trong phạm vi exercise. | Có thể không khôi phục dữ liệu khi thảm họa. | Data/DB owner; restore test, consistency và KMS. |
| DR-04 | Một dịch vụ Critical chưa có đường phục hồi đáp ứng dependency. | RTO có nguy cơ không đạt. | DR owner; exercise end-to-end và kiểm tra dependencies. |

Có thể một gap tác động lớn hơn những gap khác; không ưu tiên chỉ bằng cách “đóng nhiều ticket nhất để tăng tỷ lệ”.

### 11.5. Executive summary minh họa

> Tại kỳ đo đã chốt, tỷ lệ verified coverage của 30 cặp đối tượng–control là **70%**. Đã xác định **5 cặp chưa được bao phủ** và **4 cặp đã triển khai nhưng chưa có bằng chứng đủ mạnh**. Các lỗ hổng ưu tiên liên quan đến nguồn log quản trị không hoạt động và khả năng khôi phục của dịch vụ Critical. Trọng số ưu tiên theo chính sách cho thấy coverage đạt **68,18%**; đây là chỉ báo coverage, **không phải xác suất hệ thống an toàn**. Các owners đã được giao remediation và retest theo deadlines; kết luận chỉ áp dụng cho scope và kỳ đã kiểm chứng.

Một báo cáo tốt nên bổ sung **critical gaps, unknowns, xu hướng từng control, actions, deadlines và mức độ tin cậy** chứ không chỉ một con số tổng.

## 12. Thiết kế dashboard theo đối tượng sử dụng

Một dashboard có cùng dữ liệu nguồn nhưng **góc nhìn khác nhau** theo quyết định cần ra.

### 12.1. Dành cho lãnh đạo và risk owner

Cần thấy:

- Tỷ lệ verified coverage theo business service, criticality và control objective.
- Số assets/data flows Critical không được bao phủ.
- Các gaps trọng yếu, chủ sở hữu, thời hạn và mức tác động.
- Coverage trend với phương pháp/mẫu số nhất quán, mọi thay đổi scope được chú thích.
- Phần chưa kiểm chứng và nguồn dữ liệu thiếu, thay vì gộp vào nhóm “an toàn”.
- Quyết định cần phê duyệt: ngân sách, chấp nhận residual risk có điều kiện hoặc thay kiến trúc.

### 12.2. Dành cho control owners và operations

Cần drill-down tới từng đối tượng:

- Asset/identity ID, control ID, trạng thái, reason và last verified timestamp.
- Evidence link, test failure, source heartbeat, policy drift.
- Owner/ticket, remediation action, ETA, planned retest.
- Danh sách new assets chưa onboard, stale evidence và exceptions sắp hết hạn.
- Công cụ vận hành cần xử lý gap, không chỉ một biểu đồ phần trăm.

### 12.3. Dành cho auditor hoặc assurance reviewer

Cần truy vết:

- Measurement contract và phiên bản đã áp dụng.
- Nguồn population, scope và phương pháp reconciliation.
- Applicability rule, reason cho exclusions, phê duyệt N/A.
- Dữ liệu numerator/denominator, query/version và sample design.
- Evidence provenance/integrity, test results và limitations.
- Findings, exception decisions, retest và review signoff.

### 12.4. Cấu trúc dashboard mẫu

~~~text
CONTROL COVERAGE — Order Platform — November 2026
Scope: Production | Snapshot: 2026-11-28 UTC
Definition: Verified controls / applicable asset-control pairs

Verified coverage: 70.00% (21 / 30)
Implemented but unverified: 4 / 30
Uncovered: 5 / 30
Unknown: 0 / 30
Risk-weighted verified: 68.18% (75 / 110)

By control:
  IAM                8 / 10  80.00%
  Logging            7 / 10  70.00%
  Backup/Restore     4 /  6  66.67%
  Disaster Recovery  2 /  4  50.00%

Priority gaps:
  LOG-10   Critical  owner=platform     test=pending
  DR-04    Critical  owner=dr-team      test=pending
  BKP-06   High      owner=data-team    restore=not-verified

Data quality:
  Population inventory reconciliation: completed within scope
  Evidence timestamp: per record
  Exclusions: require approval; none counted as verified by default
  Limitations: effectiveness beyond defined tests not guaranteed

Decisions:
  Assign owners and deadlines; run source-health and recovery tests.
~~~

Các trạng thái, số liệu và tên ở đây là **dữ liệu giả định để học tính toán**. Trong dashboard thật, không nên chỉ báo “snapshot 28/11” rồi khẳng định coverage cho toàn tháng nếu không có event history hoặc evidence period tương ứng.

## 13. Xu hướng và lỗi so sánh giữa các kỳ

### 13.1. Khi mẫu số thay đổi

Giả sử:

- Tháng 10: 80/100 asset-control pairs đã verified = 80%.
- Tháng 11: 120/150 pairs đã verified = 80%.

Tỷ lệ không đổi nhưng **số cặp verified tăng 40**, đồng thời số chưa verified tăng từ 20 lên 30. Cần tách:

- **Coverage of fixed cohort:** những asset/control đã tồn tại ở cả hai kỳ.
- **Coverage of new population:** assets, identities, requirements hoặc controls mới.
- **Retired population:** đối tượng đã ngừng và có căn cứ loại khỏi scope.
- **Definition changes:** thay đổi policy, criterion hoặc phương pháp phân loại.

Nếu tháng 11 tăng coverage vì xóa những asset khó bảo vệ khỏi inventory, dashboard có thể tăng dù rủi ro thực tế chưa giảm. Báo cáo cần theo dõi **denominator drift**.

### 13.2. Hiệu ứng gộp nhóm

Một doanh nghiệp có hai mảng:

- Dịch vụ Critical: coverage giảm từ 95% xuống 80%.
- Dịch vụ ít quan trọng: coverage tăng từ 70% lên 95%.

Tỷ lệ tổng có thể tăng hoặc giảm tùy số lượng assets mỗi mảng; một con số gộp có thể che sự suy giảm của dịch vụ Critical. Vì vậy cần **segment theo criticality, business service, region, asset type, control family** và công bố trọng số khi dùng.

### 13.3. Baseline và target phải có nguồn

Đặt một target “95%” chỉ vì dễ nhìn chưa đủ. Mục tiêu phải dựa trên:

- Yêu cầu bắt buộc từ policy/contract hoặc security objective.
- Risk appetite, criticality và attack surface.
- Điều kiện tối thiểu của controls, ví dụ không chấp nhận bỏ sót audit logging ở một số systems Critical.
- Mức độ trưởng thành và phương án triển khai có deadline.
- Tính khả thi, số gaps, các ưu tiên trong risk register.

Một số control thuộc phạm vi rủi ro cao có thể yêu cầu **100% coverage theo policy**, nhưng đó là tiêu chí tổ chức đặt ra, không phải ngưỡng phổ quát áp dụng mọi control.

## 14. Exceptions, N/A và compensating controls

### 14.1. Ba trường hợp không được nhập nhằng

**Not applicable:** control không áp dụng theo chính sách đã được xác nhận, có rationale và thẩm quyền. Ví dụ control “MFA interactive login” không áp dụng như nhau cho non-interactive workload identity nhưng vẫn phải có control thích hợp cho danh tính đó.

**Approved exception:** control áp dụng nhưng chưa đạt, và risk owner đã phê duyệt chấp nhận một tình trạng nhất định có giới hạn. Không tự ghi là verified covered.

**Compensating/alternative control:** có một cơ chế khác được chấp thuận đáp ứng cùng mục tiêu trong điều kiện cụ thể. Phải có **criteria và test evidence riêng** chứng minh tác dụng tương đương trong phạm vi.

### 14.2. Ví dụ exception sai

Một hệ thống Critical không cài EDR vì agent không tương thích OS. Team đánh dấu NOT_APPLICABLE để khỏi giảm tỷ lệ.

Cách xử lý phù hợp hơn:

1. Kiểm tra policy có thực sự yêu cầu EDR đối với loại hệ thống đó không.
2. Nếu có, trạng thái mặc định là UNCOVERED hoặc PARTIALLY_COVERED theo tiêu chí; không đổi thành N/A chỉ vì khó triển khai.
3. Đánh giá compensating controls như host isolation, application allowlisting, audit, network monitoring và hardening.
4. Ghi risk exception, owner, expiry và điều kiện theo dõi.
5. Nếu một alternative path được phê duyệt làm điều kiện đạt, kiểm chứng bằng test riêng và công bố dạng coverage tương ứng.
6. Giữ lịch sử chính xác để lãnh đạo thấy có gap về control chuẩn, dù rủi ro được quản lý tạm thời.

### 14.3. Unknown có thể là rủi ro quản trị nghiêm trọng

Nếu một nhóm asset không có owner hoặc telemetry, việc không xác định được coverage có thể là vấn đề quản lý inventory, onboarding và monitoring. Cần có **finding về evidence/pipeline completeness**, không âm thầm tính vào PASS hay xóa khỏi scope.

## 15. Continuous coverage monitoring và integration với CI/CD

Control coverage nên trở thành một quá trình liên tục, không chỉ báo cáo trước đợt audit.

### 15.1. Dòng dữ liệu

~~~mermaid
flowchart LR
    INV["Authoritative inventories"] --> JOIN["Applicability + key reconciliation"]
    POL["Policy / controls / requirements"] --> JOIN
    CFG["Config + runtime state"] --> EV["Evidence normalization"]
    TST["Tests / detection / DR exercises"] --> EV
    LOG["Telemetry health + event history"] --> EV
    JOIN --> ASSESS["Coverage assessment"]
    EV --> ASSESS
    ASSESS --> M["Versioned metrics"]
    ASSESS --> F["Findings + remediation"]
    F --> RET["Retest / closure"]
    RET --> ASSESS
    M --> REPORT["Dashboard / assurance case / audit"]
~~~

### 15.2. Kiểm tra trước deploy

Ví dụ:

- IaC không cho tạo storage public ngoài policy.
- Kubernetes admission không cho workload privileged trái policy.
- Pipeline buộc image signature/digest phù hợp.
- Terraform plan không cấp quyền IAM wildcard ngoài approval.

Đây là bằng chứng **prevention ở thời điểm triển khai**, không tự chứng minh runtime hiện tại đã sạch drift hoặc mọi resource đều đến từ pipeline.

### 15.3. Kiểm tra runtime

- Đối chiếu effective IAM/RBAC, không chỉ manifest khai báo.
- Quét configuration và runtime của cloud/Kubernetes/endpoint.
- Kiểm tra source logging health, canary events và mất telemetry.
- Rà soát secret/token usage, ngoại lệ và permission changes.
- Kiểm tra backup/restore và DR ở kỳ phù hợp với yêu cầu.
- Kiểm tra closed findings bằng retest, không chỉ ticket status.

### 15.4. Triggers khiến coverage cần đo lại

- Phát sinh hoặc ngừng asset, account, cluster, data store.
- Có yêu cầu mới, phiên bản policy hoặc control baseline thay đổi.
- Thêm quyền admin hoặc đường trust/CI/CD mới.
- Thay logging pipeline, parser hoặc detection rule.
- Phát hiện incident hoặc control bypass.
- Thêm third-party/subprocessor và data flow mới.
- Bản test trước đó hết độ tươi theo policy.
- Kết quả remediation/failback/restore mới hoặc exception hết hạn.

### 15.5. Giới hạn của tự động hóa

Không phải control nào cũng đo trực tiếp bằng API. Ví dụ văn hóa phê duyệt, chất lượng risk assessment, readiness của incident response và sự phù hợp của một assurance argument có thể cần **examine, interview, test và judgment**.

Metric pipeline cần phân biệt **auto-verified**, **manually-reviewed**, **pending-review** và **not-testable-by-current-source**. Không chuyển trạng thái chỉ để đạt tỷ lệ cao.

## 16. Assurance case cho một tuyên bố coverage

Một báo cáo nghiêm túc nên giải thích tại sao coverage được xem là đáng tin chứ không chỉ cho số.

### 16.1. Claim–Argument–Evidence

**Claim:** “Trong kỳ và phạm vi được xác định, các nguồn cloud audit thuộc policy LOG-03 v4 có verified collection coverage tối thiểu theo mục tiêu đã phê duyệt.”

**Argument:**

1. Population nguồn audit có tính đầy đủ phù hợp với inventory production.
2. Mọi source có applicability được đánh giá theo cùng criterion.
3. Verified status chỉ được cấp cho source có bằng chứng configuration, event generation, delivery và health phù hợp.
4. Unknown, partial, failure và exceptions được giữ riêng.
5. Timestamp, source identity và các bước tổng hợp có thể truy vết.
6. Reviewer đã xem findings và những limitations có thể làm kết luận thay đổi.

**Evidence:** inventory/reconciliation, source configs, raw synthetic events, ingestion logs, pipeline health, test results, query/version, evidence register và signed review decision nếu chính sách yêu cầu.

### 16.2. Defeaters cần xem

| Defeater | Có thể làm sai điều gì? | Cách giảm rủi ro |
|---|---|---|
| Một cloud account không có trong inventory. | Denominator thiếu, tỷ lệ bị thổi phồng. | Cross-account discovery và ownership review. |
| Log chỉ xuất hiện từ node A, không phải mọi node. | Verified coverage không đủ. | Kiểm tra node/source-level completeness. |
| Synthetic event không qua cùng pipeline production. | Test không đại diện cho đường dữ liệu thật. | Test end-to-end theo đường cần kiểm chứng. |
| Rule/collector thay sau test. | Evidence stale. | Version pin, change trigger và retest. |
| Ngoại lệ hết hạn nhưng vẫn bị loại. | Tỷ lệ coverage sai. | Exception expiry checks và approval audit. |
| Timestamp sai khiến health window bị tính nhầm. | Coverage theo thời gian không đáng tin. | NTP/clock evidence, event-time vs ingest-time. |
| Hai source cùng một dữ liệu bị đếm riêng. | Numerator/denominator đếm trùng. | Canonical IDs, reconciliation và grain contract. |

Khi một defeater có tác động lớn chưa được xử lý, verdict phù hợp có thể là **inconclusive** dù phép chia đã tính được phần trăm.

## 17. Xây dựng findings và hành động khắc phục từ coverage gaps

Một record remediation hữu ích bao gồm:

- **Gap ID, control ID, đơn vị bị ảnh hưởng, asset owner, business service và criticality.**
- Trạng thái hiện tại, expected criterion, source và evidence.
- Mức rủi ro, threat scenario và tác động đến security objective.
- Nguyên nhân đã xác minh hoặc giả thuyết chưa chắc chắn.
- Hành động khắc phục, owner, deadline, phụ thuộc và sự phê duyệt.
- Compensating controls/exception nếu có, phạm vi và expiry.
- Test chấp nhận và bằng chứng cần tạo để chuyển sang VERIFIED_COVERED.
- Ngày retest, reviewer và quyết định đóng.

### 17.1. Ví dụ finding

~~~yaml
finding_id: CCGAP-2026-023
metric_id: CC-LOG-CRITICAL-01
control_id: CTRL-LOG-002
unit_id: cloud-account-prod-c
business_service: order-platform
status: open
observed_coverage: UNCOVERED
required_condition: "Privileged cloud audit reaches monitored pipeline"
evidence:
  - "EV-INVENTORY-010"
  - "EV-CONFIG-033"
  - "EV-HEALTH-008"
risk:
  scenario: "Unauthorized privilege change not observable"
  severity: critical
root_cause:
  status: under-investigation
owner: cloud-platform
remediation:
  - "Enable audit source and correct event routing"
  - "Add source-health alert and authorized detection canary"
acceptance:
  - "Audit raw event generated and received within defined window"
  - "Source monitoring/alert coverage tested"
retest:
  status: pending
  reviewer: security-assurance
~~~

Dữ liệu là **minh họa**. Nếu nguồn log không có trong kỳ trước, bật log hôm nay không thể tự tạo lại các event lịch sử đã mất. Finding cần ghi giai đoạn không đủ chứng cứ và ảnh hưởng tới các security investigations trong kỳ.

### 17.2. Khi nào đóng một coverage gap?

Đóng khi:

1. Asset/applicability được xác nhận.
2. Control đáp ứng criterion đã phê duyệt.
3. Evidence có nguồn và kỳ phù hợp.
4. Test có kết quả PASS hoặc một alternative control path được chứng minh phù hợp.
5. Không còn exception/defeater trọng yếu làm suy yếu kết luận.
6. Reviewer có thẩm quyền xác nhận retest và lưu decision.

**Đóng ticket không đồng nghĩa đã có verified coverage**. Tỷ lệ chỉ tăng khi dữ liệu assessment thực sự thay đổi theo quy tắc.

## 18. KPI đi kèm control coverage

Một dashboard chỉ hiển thị coverage có thể bỏ sót tình trạng kiểm soát bị lỗi hoặc chương trình đánh giá không hoạt động.

| KPI bổ trợ | Cách đo | Tại sao hữu ích |
|---|---|---|
| **Asset inventory reconciliation** | Mức khớp giữa authoritative inventory và các nguồn discovery, theo đối tượng. | Đánh giá độ tin cậy của mẫu số. |
| **Evidence freshness** | Tỷ lệ verified records còn trong kỳ hiệu lực theo control policy. | Tránh dùng config/test cũ để duy trì màu xanh. |
| **Unknown/partial coverage rate** | Unknown hoặc partial / applicable population. | Phản ánh những vùng chưa hiểu hoặc chưa đủ kiểm chứng. |
| **Critical uncovered count** | Số pairs Critical chưa đạt, kèm business service. | Ngăn tỷ lệ trung bình che lỗ hổng nguy hiểm. |
| **Control test pass rate** | Tests hợp lệ pass / tests hợp lệ đã chạy, phân nhóm theo scenario. | Đo hiệu lực trong phạm vi thử, khác deployment coverage. |
| **Source health/SLO** | Thời gian nguồn chứng cứ healthy hoặc event nhận thành công. | Bảo vệ độ tin cậy của coverage metrics về logging/detection. |
| **Coverage drift time** | Thời gian từ khi đối tượng phát sinh/gap xuất hiện tới khi được xác nhận/sửa. | Đo tốc độ onboarding và phục hồi baseline. |
| **Remediation retest rate** | Findings đã verified closed / findings báo đã sửa. | Chống tình trạng “ticket closed” không có evidence. |
| **Exception age/expiry** | Số ngoại lệ quá hạn, theo risk và owner. | Ngăn che gaps bằng ngoại lệ kéo dài. |
| **New-asset onboarding coverage** | Đối tượng mới được áp control trước deadline / tổng đối tượng mới applicable. | Kiểm tra hiệu quả integration với provisioning/CI/CD. |
| **Threat-scenario test coverage** | Scenario ưu tiên có test phù hợp / tổng scenario ưu tiên trong scope. | Nối metric với risk, không chỉ trạng thái asset. |
| **Data-quality failures** | Lỗi API, parser, pagination, source health và unmatched keys. | Đánh giá dashboard còn đáng tin không. |

### 18.1. Không dùng một metric làm mục tiêu duy nhất

Khi đội nhóm bị thưởng/phạt chỉ theo “coverage phải 100%”, có thể phát sinh hành vi:

- Loại những asset khó triển khai ra khỏi inventory.
- Chuyển status uncovered thành N/A không có thẩm quyền.
- Đặt threshold health quá lỏng.
- Không ghi nhận test failure hoặc stale evidence.
- Chỉ đo những controls dễ kiểm tra, bỏ qua threat paths khó.
- Đổi trọng số ngay trước kỳ báo cáo.

Bảo vệ chất lượng đo bằng **metric contract, dữ liệu raw có thể kiểm tra, review độc lập và công bố hạn chế**.

## 19. Các sai lầm phổ biến

1. **Tính coverage dựa trên những gì công cụ đã thấy.** Những đối tượng chưa có agent/connector thường không hiện ra; denominator phải từ nguồn độc lập phù hợp.
2. **Đồng nhất installed với effective.** Một agent cài nhưng unhealthy hoặc policy sai chưa phải verified operational coverage.
3. **Đếm controls thay vì đo đối tượng cần bảo vệ.** Có nhiều control definitions không chứng minh chúng áp dụng đúng các tài sản trọng yếu.
4. **Loại UNKNOWN ra khỏi mẫu số.** Điều này có thể tạo 100% ảo khi những hệ thống khó quan sát bị ẩn.
5. **Lạm dụng NOT_APPLICABLE.** Không hỗ trợ công nghệ hoặc khó triển khai không đồng nghĩa policy không áp dụng.
6. **Tính exception như PASS.** Risk acceptance có thể hợp lệ về quản trị nhưng không biến control đang thiếu thành control đã hoạt động.
7. **Không phân biệt point-in-time và period coverage.** Ảnh chụp hôm nay chưa chứng minh cả tháng không drift.
8. **Cộng tỷ lệ khác mẫu số.** Asset coverage, pair coverage, requirement coverage và threat coverage không nên cộng bừa.
9. **Đếm trùng assets hoặc evidence.** Một VM có nhiều IP hay agent records có thể bị tính nhiều lần.
10. **Dùng evidence cũ.** Chính sách, workload, log schema hoặc cloud permission đổi làm kết quả kiểm tra trước mất giá trị.
11. **Chỉ nhìn tỷ lệ gộp.** Một gap Critical bị che bởi hàng nghìn endpoints ít quan trọng.
12. **Xem không có alerts là detection coverage tốt.** Source có thể không ghi hoặc rule chưa thử.
13. **Cho rằng 100% coverage nghĩa là rủi ro bằng 0.** Controls có thể bị bypass, threat model thiếu hoặc có nguy cơ ngoài phạm vi.
14. **Không công bố thay đổi inventory qua kỳ.** Metric tăng vì mẫu số giảm không phải luôn là tiến bộ bảo mật.
15. **Đóng finding khi có kế hoạch sửa.** Phải có retest và evidence đạt criterion.
16. **Đánh đồng SOC/ISO chứng nhận với coverage nội bộ.** Báo cáo và chứng nhận có scope; customer-side config và runtime vẫn cần kiểm tra.
17. **Đo tự động mà không kiểm tra data pipeline.** Parser, API và identity mapping có thể gây sai lệch âm thầm.
18. **Diễn giải weighted score như xác suất breach.** Trọng số là mô hình ưu tiên, cần nguồn và giới hạn.

## 20. Bài tập thực hành

Một tổ chức quản lý 40 service production, gồm 10 Critical, 20 High và 10 Medium. Policy yêu cầu mỗi service có security logging và incident alert routing. Hệ thống inventory nhận được từ CMDB có 40 services; dashboard SIEM chỉ liệt kê 35 services.

Kết quả so sánh:

- Trong 35 services SIEM nhìn thấy, 30 có logging và alert-routing test PASS.
- 3 services có log nhưng chưa kiểm tra alert routing.
- 2 services đã xác minh thiếu một nhóm audit events bắt buộc.
- 5 services còn lại trong CMDB không xuất hiện ở SIEM và chưa có evidence nào khác.
- Có 2 services Critical nằm trong nhóm 5 không xuất hiện.
- Một service có giấy exception đã hết hạn nhưng vẫn được dashboard loại khỏi mẫu số.

**Yêu cầu:**

1. Xác định đúng population và unit of analysis, rồi phân loại các trạng thái theo measurement contract được đề xuất.
2. Tính **verified coverage** theo cách bảo thủ nếu mỗi service là một đơn vị cần đồng thời logging và alert routing.
3. Chỉ rõ vì sao dashboard SIEM có thể báo một tỷ lệ cao hơn và tỷ lệ đó không chứng minh bao phủ toàn bộ.
4. Nêu cách xử lý nhóm 5 services không có evidence: UNKNOWN hay UNCOVERED trong những điều kiện nào?
5. Đề xuất phân đoạn báo cáo cho Critical/High/Medium và cách không che 2 services Critical thiếu visibility.
6. Thiết kế 3 negative tests cho source health, alert routing và ngoại lệ hết hạn.
7. Xác định controls/evidence cần bổ sung để chuyển 3 services có log nhưng chưa test sang VERIFIED_COVERED.
8. Viết một finding về nguồn audit thiếu và một finding về denominator/exclusion sai.
9. Đề xuất metric theo thời gian để phát hiện nguồn đã từng healthy nhưng mất log một số giờ.
10. Lập một executive report ngắn kèm limitation, owner, deadlines và retest.

**Gợi ý giải:** Nếu yêu cầu là **cả logging và alert routing đã verified**, có **30 VERIFIED_COVERED trên 40 applicable services**, tỷ lệ **75%**. Ba services thiếu test routing là IMPLEMENTED_UNVERIFIED hoặc PARTIALLY_COVERED tùy contract; hai services thiếu audit events là UNCOVERED/PARTIAL; năm services chưa quan sát phải giữ UNKNOWN hoặc xác minh thành UNCOVERED. Cần kiểm tra hiệu lực exception trước khi loại bất kỳ service nào; một exception hết hạn không là N/A hợp lệ. **30/35 ≈ 85,71%** chỉ là tỷ lệ trong danh sách SIEM nhìn thấy, không phải coverage cho 40 services.

### 20.1. Mẫu đáp án finding

**Finding A — Incomplete population:**

- Condition: 5/40 services thuộc authoritative inventory không có record tương ứng trong nguồn SIEM tại kỳ được đánh giá.
- Evidence: CMDB snapshot, SIEM source register, reconciliation log và timestamps.
- Risk: không thể xác nhận monitoring coverage; trong nhóm có hai services Critical.
- Action: xác định owner, cấu hình/thu telemetry, health checks, test end-to-end, giữ UNKNOWN cho tới khi đủ evidence.
- Retest: đối chiếu lại đầy đủ population, thực hiện authorized canary và xác nhận alert routing.

**Finding B — Invalid exclusion:**

- Condition: một service bị loại khỏi mẫu số dựa trên exception hết hạn.
- Evidence: policy version, exception register, dashboard query và history.
- Risk: coverage bị báo cáo cao hơn thực tế, gây quyết định sai.
- Action: khôi phục service vào applicable population, xử lý exception theo thẩm quyền và sửa logic kiểm tra expiry.
- Retest: kiểm tra với data fixture ngoại lệ hết hạn, xác minh tỷ lệ tính lại.

## 21. Checklist xây dựng và báo cáo Control coverage

- [ ] Xác định rõ security objective, risk và control muốn đo.
- [ ] Metric contract mô tả scope, kỳ, đơn vị đo, population, applicability, numerator và denominator.
- [ ] Asset/identity/data-flow population đến từ authoritative inventory và có kiểm tra completeness.
- [ ] Không dùng danh sách của tool triển khai control làm nguồn duy nhất cho mẫu số nếu nó bỏ đối tượng chưa được bảo vệ.
- [ ] Mỗi cặp unit-control chỉ có một status hiệu lực tại thời điểm đo.
- [ ] VERIFIED, IMPLEMENTED_UNVERIFIED, PARTIAL, UNCOVERED, UNKNOWN và N/A có điều kiện rõ.
- [ ] N/A có rationale và nguồn phê duyệt; exceptions không tự động được tính như verified.
- [ ] Mọi evidence có provenance, scope, timestamp, version, source health và độ tươi phù hợp.
- [ ] Đã xác định đang đo existence, deployment, verified coverage, effectiveness hay period continuity.
- [ ] Có rule xử lý denominator = 0, pagination failure, duplicate IDs và stale evidence.
- [ ] Control requirements đòi nhiều điều kiện được đánh giá theo logic phù hợp, không gom PASS tùy tiện.
- [ ] Có segment theo business service, criticality, environment, control family và owner.
- [ ] Risk-weighted metrics có trọng số và phương pháp được duyệt trước kỳ, nêu giới hạn.
- [ ] Dashboard công bố cả số lượng tuyệt đối, numerator/denominator, gaps và unknowns.
- [ ] Trend so sánh cùng phương pháp hoặc chú thích cohort, scope và policy changes.
- [ ] Coverage và effectiveness được báo riêng; không suy diễn sang xác suất xâm nhập hoặc residual risk.
- [ ] Có drill-down tới từng asset/control, evidence, ticket, exception và owner.
- [ ] Data pipeline có kiểm tra health, source coverage, schema drift và reconciliation.
- [ ] Findings ghi scenario, severity, expected vs actual, remediation, deadline và retest.
- [ ] Kết quả sau remediation chỉ tăng khi có evidence phù hợp, không chỉ ticket đóng.
- [ ] Có reviewer đủ độc lập và kiểm tra được claims trong assurance case.
- [ ] Có triggers tái đo khi thay đổi assets, identity, threat, policy, control hoặc logging pipeline.
- [ ] Thông điệp cho lãnh đạo có limitations và decisions, không chỉ phần trăm màu xanh.

## 22. Câu hỏi tự đánh giá

1. Control coverage khác control effectiveness ở đâu? Hãy lấy ví dụ với EDR, SIEM hoặc backup.
2. Vì sao không nên dùng EDR console làm nguồn duy nhất xác định tổng số thiết bị cần được bảo vệ?
3. Đơn vị asset–control pair khác asset count thế nào? Khi nào cần dùng pair-based coverage?
4. Một service đã cấu hình logging nhưng chưa có heartbeat và test tạo alert nên ở trạng thái nào?
5. Nên xử lý UNKNOWN thế nào để tránh chỉ số coverage đẹp giả tạo?
6. Khi nào NOT_APPLICABLE là hợp lệ, và vì sao một exception chưa sửa control không mặc nhiên là N/A?
7. Một kết quả kiểm tra point-in-time không chứng minh coverage xuyên suốt quý vì sao?
8. Hãy tính verified coverage với 42 verified, 4 implemented unverified, 2 partial, 1 uncovered và 1 unknown trên tổng 50 applicable.
9. Hai kỳ đều đạt 80% nhưng population tăng từ 100 lên 150; điều gì cần giải thích khi báo cáo trend?
10. Tại sao 100% control deployment không đủ để kết luận threat scenarios được kiểm soát?
11. Độ độc lập giữa authoritative inventory và control console ảnh hưởng như thế nào tới độ tin cậy của denominator?
12. Khi nào risk-weighted coverage hữu ích và vì sao nó không phải xác suất hệ thống bị xâm nhập?
13. Một API export thiếu trang dữ liệu sẽ ảnh hưởng numerator, denominator và confidence ra sao?
14. Thiết kế hai phép thử phát hiện trường hợp metric pipeline lặng lẽ xóa tài sản UNKNOWN.
15. Viết một claim–argument–evidence ngắn cho coverage của Kubernetes admission policy.
16. Nêu những thông tin bắt buộc trong một dashboard để auditor kiểm tra lại kết quả 70% coverage.
17. Vì sao nên báo riêng các gap Critical ngay cả khi overall coverage đang tăng?
18. Hãy định nghĩa một measurement contract cho privileged IAM, logging hoặc DR mà bạn đang vận hành, kèm điều kiện PASS và limitations.

**Điểm cốt lõi:** **Control coverage chỉ có ý nghĩa khi biết chính xác cái gì cần được bảo vệ và bằng chứng nào chứng minh control đang bao phủ nó.** Tỷ lệ phần trăm không thay thế inventory đầy đủ, logic applicability, phép thử effectiveness hoặc phân tích rủi ro. Trong security assurance, cần dùng **numerator/denominator minh bạch, trạng thái UNKNOWN tách biệt, evidence có provenance, báo cáo theo mức quan trọng và vòng remediation–retest** để biến coverage thành công cụ ra quyết định, thay vì một con số trông đẹp trên dashboard.
