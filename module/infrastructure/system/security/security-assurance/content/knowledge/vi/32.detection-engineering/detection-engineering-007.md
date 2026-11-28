# Detection test: Kiểm thử khả năng phát hiện trong security assurance

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **detection test** và phân biệt kiểm thử logic phát hiện, chất lượng telemetry, tích hợp pipeline và hiệu quả phản ứng.
2. Viết **detection contract** có thể kiểm chứng: giả thuyết đe dọa, phạm vi, nguồn dữ liệu, điều kiện kích hoạt, ngoại lệ và tiêu chí chấp nhận.
3. Tạo dữ liệu thử **positive, negative, boundary, adversarial và regression**; đánh giá kết quả bằng expected/actual thay vì quan sát dashboard theo cảm tính.
4. Kiểm thử cửa sổ thời gian, thứ tự sự kiện, dữ liệu trễ, trùng, thiếu, parser thay đổi và sự cố pipeline.
5. Thiết kế thử nghiệm end-to-end có kiểm soát, từ hành vi hoặc sự kiện nguồn đến alert, case và phản ứng của người trực.
6. Lưu bằng chứng đủ để auditor hoặc reviewer độc lập đánh giá **claim → control → test → evidence → decision**, đồng thời xác định khoảng trống và rủi ro tồn dư.

## 1. Detection test là gì?

**Detection test** là hoạt động tạo, tái phát hoặc mô phỏng các sự kiện có đầu ra kỳ vọng đã định để xác minh rằng một cơ chế phát hiện bảo mật nhận diện đúng hành vi cần chú ý, hạn chế cảnh báo sai và chuyển kết quả đến đúng nơi trong thời hạn mong muốn.

Một rule được bật trong SIEM, EDR hoặc nền tảng phân tích log **không đồng nghĩa** rule đã được kiểm thử hoặc đang có khả năng phát hiện. Rule có thể đúng cú pháp nhưng sai tên trường; đúng trên dữ liệu giả nhưng nguồn production thiếu log; tạo alert nhưng không được chuyển tới người trực; hoặc từng hoạt động tốt nhưng ngừng khớp khi parser đổi schema.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, detection test là một phương pháp tạo bằng chứng cho chương trình security assurance liên tục: từ phân tích rủi ro và security controls đến kiểm thử, audit, ghi nhận phát hiện và xác minh khắc phục. Detection test tập trung vào **khả năng phát hiện và xử lý tín hiệu**; nó không tự chứng minh rằng biện pháp phòng ngừa đã ngăn được xâm nhập.

### 1.1. Một tuyên bố cần kiểm chứng

Giả sử nhóm bảo mật đưa ra claim:

> Trong cluster production, mọi lần tạo hoặc sửa quyền truy cập quản trị trái chính sách đều được ghi nhận, phát hiện và chuyển thành cảnh báo có đủ thông tin điều tra trong tối đa 5 phút.

Có ít nhất bốn thành phần phải chứng minh:

- **Visibility:** nguồn có phát sự kiện cho những thao tác thuộc phạm vi không?
- **Logic:** rule có phân biệt thao tác bị cấm, thao tác được phê duyệt và các tình huống biến thể không?
- **Delivery:** kết quả có đi qua collector, parser, correlation, alert router và hệ thống case không?
- **Response readiness:** alert có đến đúng owner, đủ bối cảnh và được tiếp nhận/điều tra theo thời hạn không?

Nếu chỉ replay một JSON và thấy rule trả true, ta mới chứng minh được **một phần logic** trên **một mẫu dữ liệu**. Claim end-to-end vẫn chưa được chứng minh.

### 1.2. Phân biệt với các phép thử liên quan

| Hoạt động | Câu hỏi cần trả lời | Kết quả điển hình |
|---|---|---|
| **Detection test** | Giả thuyết phát hiện có đúng trong những điều kiện đã định không? | Pass/fail theo test case, độ trễ, evidence. |
| **Telemetry validation** | Nguồn và pipeline có cung cấp sự kiện đủ trường, đúng thời gian không? | Coverage, parse/ingest quality, health. |
| **Detection engineering** | Nên phát hiện hành vi gì, bằng những tín hiệu, logic và quy trình nào? | Use case, rule, phiên bản, runbook, test suite. |
| **Threat hunting** | Có dấu hiệu hoạt động đáng nghi chưa được phát hiện tự động không? | Giả thuyết điều tra, findings, detection gaps. |
| **Adversary emulation / purple teaming** | Khi một kỹ thuật đe dọa được mô phỏng có kiểm soát, tầng bảo vệ/giám sát nhìn thấy điều gì? | Kết quả thực thi, observed telemetry, alert và gaps. |
| **Penetration testing** | Kẻ tấn công có thể khai thác điểm yếu và tạo tác động nào trong phạm vi được phép? | Bằng chứng khai thác, rủi ro, khuyến nghị. |
| **Incident response exercise** | Người và quy trình phản ứng có xử lý đúng không? | Timeline, quyết định, chất lượng runbook. |

Những hoạt động này có thể hỗ trợ nhau. Detection test không yêu cầu tạo ra xâm nhập thực; nhiều phép thử có thể dùng event synthetic đã kiểm soát hoặc replay dữ liệu đã ẩn danh.

## 2. Mô hình kiểm thử theo lớp

Một detection pipeline có thể mô tả:

~~~mermaid
flowchart LR
    T["Hành vi / test event"] --> S["Nguồn telemetry"]
    S --> C["Collector + transport"]
    C --> P["Parse + normalize"]
    P --> R["Rule / correlation"]
    R --> A["Alert routing"]
    A --> I["Case + triage"]
    I --> O["Kết quả phản ứng"]
    S -.-> H["Data health"]
    C -.-> H
    P -.-> H
~~~

Một phép thử có thể chạy ở một tầng, nhiều tầng hoặc toàn bộ chuỗi:

| Lớp test | Đầu vào | Điều được chứng minh | Điều chưa được chứng minh |
|---|---|---|---|
| **T1 — Rule unit test** | Fixture event đã chuẩn hóa. | Điều kiện, filter, join, grouping, threshold, suppression và output của rule trong môi trường test. | Hành vi nguồn thật, parser, collector, routing. |
| **T2 — Parser/schema contract test** | Raw event từ phiên bản nguồn cụ thể. | Biến đổi sang field chuẩn, timestamp và các giá trị thiết yếu. | Rule tạo alert hay không, độ trễ cuối chuỗi. |
| **T3 — Pipeline integration test** | Raw event phát vào một ingress/bus được ủy quyền. | Truyền, ingest, parse, correlation, alert tạo đúng. | Nguồn phát sinh event cho hành vi thật; người trực phản ứng. |
| **T4 — Source-to-alert test** | Hành vi an toàn được thực hiện trên hệ thống thử nghiệm. | Nguồn thực sinh telemetry; alert đến đích và trong SLA. | Người trực hiểu và xử lý alert theo quy trình. |
| **T5 — End-to-end response test** | Tình huống diễn tập đã thông báo và cho phép. | Alert, routing, acknowledgment, triage, escalation, kiểm soát hành động. | Mọi kỹ thuật tấn công có thể xảy ra đều được bao phủ. |
| **T6 — Resilience/health test** | Thay đổi schema, nguồn ngắt thử nghiệm, event trễ/trùng hoặc parser lỗi có kiểm soát. | Năng lực phát hiện gián đoạn và hành vi recovery. | Không có điểm mù ngoài phạm vi được thử. |

**Nguyên tắc:** kết luận phải gắn với tầng đã kiểm thử. Một test T1 pass không được ghi nhận như kết quả T5.

### 2.1. Khi nào chọn tầng nào?

- Khi **viết/sửa rule**, bắt đầu bằng T1 và T2 để phát hiện lỗi nhanh, deterministic và chi phí thấp.
- Khi **đổi collector, parser, index hoặc correlation engine**, ưu tiên T2/T3 cùng thử nghiệm dữ liệu trễ và lỗi đầu vào.
- Khi **bật source hoặc triển khai môi trường mới**, cần T4 để tránh trường hợp rule tốt nhưng không có event thật.
- Khi **cam kết SLA phát hiện/phản ứng**, cần T4/T5 và đo timestamp đầy đủ.
- Khi **triển khai chương trình assurance liên tục**, cần T6, synthetic canary, regression và inventory nguồn giám sát.

## 3. Viết detection contract trước khi viết test

Một test tốt bắt đầu bằng tiêu chí chấp nhận có thể quan sát, không bắt đầu bằng một câu query rời rạc.

### 3.1. Cấu trúc detection contract

| Thành phần | Nội dung cần định nghĩa |
|---|---|
| **ID, phiên bản, owner** | Định danh ổn định; người sở hữu rule và bộ test. |
| **Threat hypothesis** | Hành vi nguy hiểm, actor giả định, tài sản cần bảo vệ, tác động. |
| **Scope** | Tài khoản/cloud account, cluster, namespace, tenant, asset, môi trường. |
| **Required telemetry** | Nguồn log, event type, trường bắt buộc, schema/parser version. |
| **Logic** | Predicate, threshold, time window, grouping key, join, allowlist. |
| **Output contract** | Alert type, severity, actor, target, time, correlation ID, link raw evidence. |
| **Time contract** | Lấy event_time hay ingest_time; cửa sổ tính thế nào; chấp nhận late event bao lâu. |
| **Exception/suppression** | Điều kiện cho phép, người duyệt, hiệu lực và ngày hết hạn. |
| **Response contract** | Alert gửi đến kênh nào, owner, runbook, mốc SLA. |
| **Pass/fail** | Tập test bắt buộc, expected result, độ trễ tối đa, tiêu chí dữ liệu. |
| **Limitations** | Kỹ thuật không bao phủ, điểm mù có chủ đích, giới hạn nguồn. |

### 3.2. Mẫu hợp đồng YAML minh họa

~~~yaml
id: DET-K8S-RBAC-007
version: "1.0.0"
title: "Cảnh báo cấp quyền cluster-admin ngoài phê duyệt"
owner: "security-detection-team"
scope:
  environment: production
  clusters: ["cluster-prod-a"]
threat:
  hypothesis: "Actor tăng quyền truy cập cluster trái chính sách"
data:
  source: "kubernetes-api-audit"
  schema_version: "v1"
  required_fields:
    - event_time
    - cluster
    - actor.id
    - action
    - target.kind
    - target.name
    - response.status
rule:
  actions: ["rbac.binding.create", "rbac.binding.update"]
  required_effective_privilege: "cluster-admin-equivalent"
  allowlist_policy: "approved-change-v3"
  dedupe_window_seconds: 300
alert:
  severity: high
  required_fields:
    - actor_id
    - cluster
    - target
    - evidence_reference
  max_delivery_seconds: 300
test:
  required_cases: ["P01", "P02", "N01", "N02", "B01", "I01"]
  max_delivery_seconds: 300
exceptions:
  approval_required: true
  expiration_required: true
~~~

Đây là **định dạng mô tả để học tập**, không phải schema chuẩn của một SIEM cụ thể; các khóa như **required_effective_privilege** đòi logic tra cứu quyền thực tế trong triển khai. “cluster-admin-equivalent” phải có định nghĩa kiểm chứng, vì tên role tùy ý không đủ để suy ra quyền hiệu lực.

## 4. Thiết kế dữ liệu và kết quả kỳ vọng

### 4.1. Đơn vị của phép thử

Một test case nên có:

1. **Precondition:** môi trường, phiên bản rule/parser, tập quyền và nguồn dữ liệu.
2. **Input:** raw event, normalized event hoặc hành vi thử nghiệm, kèm thứ tự/timing.
3. **Expected observation:** số lượng detection hit, alert, field, severity, target và thời điểm kỳ vọng.
4. **Negative expectation:** sự kiện nào **không** được tạo alert.
5. **Acceptance threshold:** độ trễ, độ chính xác trường, số event bị drop, hành vi de-dup.
6. **Cleanup/rollback:** xóa dữ liệu hoặc quyền thử nghiệm và khôi phục cấu hình trong phạm vi được phép.
7. **Evidence:** test ID, timestamp, artifact version, actual output và người review.

Cần phân biệt **test failed** với **test inconclusive**. Test bị ngắt do lỗi hạ tầng hoặc thiếu dữ liệu nguồn không nên tự động tính là detection đã fail logic; cũng không được tính là pass.

### 4.2. Các nhóm test cơ bản

| Nhóm | Đầu vào | Câu hỏi |
|---|---|---|
| **Positive** | Hành vi rõ ràng đáp ứng rule. | Có phát hiện và cảnh báo đúng không? |
| **Negative** | Hành vi hợp lệ hoặc không thuộc phạm vi. | Có tránh alert sai không? |
| **Near-miss/boundary** | Ngay dưới, bằng, trên ngưỡng; sát biên time window. | Rule xử lý toán tử, ranh giới thời gian và state đúng không? |
| **Variant/evasion-resistant** | Biến thể tên role, actor, IP, cách gọi API hoặc trình tự thực hiện vẫn thuộc threat. | Rule có dựa vào giả định quá hẹp không? |
| **Correlation** | Nhiều nguồn, nhiều actor, nhiều tenant, thứ tự event phức tạp. | Có join/group đúng chủ thể và bối cảnh không? |
| **Schema/parser** | Field thiếu/null, enum đổi, nested field, timestamp lỗi. | Hệ thống fail safely và tạo tín hiệu health không? |
| **Reliability** | Duplicate, delay, out-of-order, replay, backlog, lỗi bus. | Có mất alert, double count hoặc tạo false positive không? |
| **Routing/response** | Alert có độ ưu tiên, kênh người trực, nhận ticket/case. | Alert có thể được xử lý và truy vết không? |
| **Regression** | Bộ tình huống từng pass/fail đã sửa. | Bản cập nhật có làm hỏng hành vi cần giữ không? |

Một rule chỉ được test với positive case dễ gặp có nguy cơ **overfitting**. Cần đặc biệt kiểm tra các negative case gần giống threat thật, nơi có thể tạo nhiều cảnh báo nhiễu.

### 4.3. Dữ liệu thử nên đại diện, xác định và an toàn

Có bốn chiến lược, tùy câu hỏi kiểm chứng:

- **Synthetic fixtures:** event giả lập có field theo schema xác định; nhanh, không lộ dữ liệu thật, nhưng có nguy cơ bỏ qua hành vi nguồn.
- **Sanitized historical replay:** dữ liệu thực đã làm sạch, giữ ngữ nghĩa cần thiết; tốt cho regression, nhưng phải quản trị quyền riêng tư và drift.
- **Controlled behavior generation:** phát sinh một hành động hợp lệ trong sandbox/cluster thử nghiệm; dùng để xác nhận nguồn thực phát telemetry.
- **Authorized adversary emulation:** mô phỏng kỹ thuật đe dọa dưới phạm vi, mục tiêu và ngưỡng dừng đã duyệt; dùng để tìm điểm mù ngoài giả định ban đầu.

Đừng cố làm test “giống thật” bằng cách dùng credential, secrets hoặc dữ liệu của khách hàng trong môi trường không an toàn. Dữ liệu giả đủ để test logic; test hành vi thật dùng đối tượng thử đã tạo có chủ đích.

### 4.4. Dataset có nhãn và trường hợp cần thận trọng

Một bản ghi thử có thể được gắn:

- **should_alert=true**: có đủ bằng chứng theo detection contract để cảnh báo.
- **should_alert=false**: hành vi hợp lệ hoặc không đáp ứng điều kiện.
- **indeterminate**: trường không đủ, mẫu không đại diện hoặc chuyên gia chưa thống nhất.

Các nhãn là **ground truth cho tình huống thử**, không tự động chứng minh ground truth của lưu lượng production. Nhãn có thể sai hoặc thay đổi khi risk policy thay đổi; cần version và người review.

## 5. Ví dụ xuyên suốt: kiểm thử phát hiện thay đổi RBAC trong Kubernetes

### 5.1. Threat hypothesis

Một danh tính bị lộ có thể cấp quyền quản trị cluster cho một subject khác bằng **ClusterRoleBinding**, hoặc sửa một binding hiện hữu để trỏ sang role mạnh hơn. Mục tiêu là phát hiện khi hành vi xảy ra **ngoài thay đổi được phê duyệt**, bao gồm cả role đặt tên khác thường nhưng có quyền hiệu lực tương đương.

**Ranh giới kiểm chứng:** một cluster thử nghiệm được ủy quyền và bản kiểm thử logic của rule production. Để chứng minh claim áp dụng cho production, cần thu thêm bằng chứng cấu hình và nguồn telemetry production; không mặc định kết quả sandbox áp dụng nguyên vẹn.

### 5.2. Event mẫu đã chuẩn hóa

~~~json
{
  "event_id": "audit-000314",
  "event_time": "2026-11-28T08:00:01Z",
  "ingested_at": "2026-11-28T08:00:04Z",
  "environment": "test",
  "cluster": "cluster-lab-1",
  "actor": {
    "id": "system:serviceaccount:lab:automation-test",
    "type": "service-account"
  },
  "action": "rbac.binding.create",
  "target": {
    "kind": "ClusterRoleBinding",
    "name": "grant-test-admin"
  },
  "role_ref": {
    "kind": "ClusterRole",
    "name": "cluster-admin"
  },
  "subject": {
    "kind": "ServiceAccount",
    "name": "sandbox-test",
    "namespace": "lab"
  },
  "response": {"status": "success"},
  "approved_change": false,
  "correlation_id": "run-20261128-01"
}
~~~

Các tên nguồn và actor trong ví dụ là **dữ liệu giả**. Trong Kubernetes audit thật, cấu trúc sự kiện khác JSON này; cần parser chuyển đổi và kiểm tra quyền hiệu lực. Giá trị **approved_change** phải đến từ nguồn quản lý thay đổi đáng tin, không lấy nguyên từ payload do actor kiểm soát.

### 5.3. Logic rule cần test

~~~text
DETECTION: unexpected_privileged_rbac_binding

INPUT: normalized Kubernetes API audit events

1. Chỉ xét environment thuộc production policy scope.
2. Chỉ xét action create/update/patch trên RoleBinding
   hoặc ClusterRoleBinding, outcome thành công.
3. Xác định quyền hiệu lực được cấp qua roleRef tại thời
   điểm kiểm tra và phạm vi quyền chịu tác động.
4. Nếu quyền thuộc privilege policy nhạy cảm:
      - đối chiếu actor, target, thời gian với approval có hiệu lực
      - chỉ loại trừ khi approval xác thực khớp cả phạm vi và hành động
5. Nếu không có approval hợp lệ:
      tạo alert gắn actor, cluster, binding, subject,
      effective_privilege, event_time và raw-event reference
6. Dedupe các event tương ứng cùng một thay đổi theo
   stable event id / correlation key phù hợp.
~~~

**Lưu ý:** thông tin quyền hiệu lực trong audit event đôi khi không đủ. Khi phải truy vấn state hiện tại, cần phòng tránh **race condition**: role/binding có thể đã bị sửa/xóa sau hành động. Chỉ kết luận chắc chắn quyền tại thời điểm sự kiện nếu có snapshot đáng tin hoặc chuỗi audit cho phép tái dựng trạng thái.

### 5.4. Bảng test bắt buộc

| ID | Điều kiện đầu vào | Expected | Mục đích |
|---|---|---|---|
| **P01** | Tạo ClusterRoleBinding mới cấp cluster-admin, không có approval. | 1 alert High, đầy đủ actor/target/subject. | Positive cho create. |
| **P02** | Update/patch binding để tăng quyền hiệu lực, không có approval. | Alert High. | Phát hiện thay đổi, không chỉ tạo mới. |
| **P03** | Bind role tên tùy ý nhưng chứa quyền nhạy cảm tương đương. | Alert tương ứng. | Tránh dựa vào chuỗi tên role. |
| **N01** | Tạo RoleBinding chỉ cấp quyền đọc tài nguyên thử được phép. | 0 alert cho detection này. | Giảm false positive. |
| **N02** | Thay đổi nhạy cảm có approval đã xác thực, còn hiệu lực, đúng actor và resource. | 0 alert vi phạm; có thể giữ audit info. | Kiểm chứng ngoại lệ hẹp. |
| **N03** | Yêu cầu thay đổi quyền bị Kubernetes API từ chối, không có quyền hiệu lực phát sinh. | Không tạo alert “đã cấp quyền thành công”; có thể có rule riêng theo dõi attempt. | Phân biệt attempt và action hoàn tất. |
| **B01** | Approval hết hạn một giây trước event_time. | Alert. | Thử biên thời hạn ngoại lệ. |
| **B02** | Approval hợp lệ cho cluster A nhưng event xảy ra ở cluster B. | Alert. | Không lẫn scope. |
| **C01** | Hai event cùng correlation ID nhưng thuộc hai binding khác nhau. | Đúng hai alert hoặc hai finding riêng theo hợp đồng. | Không de-dup quá mức. |
| **C02** | Một event được gửi lại với cùng event_id. | Không double count alert. | Idempotency. |
| **D01** | Event thiếu roleRef hoặc actor đáng tin. | Không gắn nhãn “benign”; tạo health/parser finding theo contract. | Đối xử dữ liệu thiếu. |
| **E01** | Alert đến đúng kênh người trực, có runbook và chứng cứ liên kết. | Alert/case được tạo trong SLA. | End-to-end delivery. |

Không nên sửa kết quả kỳ vọng để khớp rule hiện tại. Nếu detection có chủ đích bỏ qua attempted changes, giữ N03 là test âm tính và thêm use case riêng để theo dõi các nỗ lực bất thường, nếu threat model yêu cầu.

### 5.5. Fixture định dạng đơn giản

Trong thực tế, một bộ fixture có thể mô tả case theo cấu trúc sau:

~~~yaml
suite_id: DET-K8S-RBAC-007-regression
version: "1.0"
rule_under_test: unexpected_privileged_rbac_binding
schema_version: "normalized-k8s-audit-v1"
cases:
  - id: P01
    input_file: fixtures/p01-unapproved-create.jsonl
    expected:
      alert_count: 1
      alert_severity: high
      actor_id: "system:serviceaccount:lab:automation-test"
      target_kind: ClusterRoleBinding
  - id: N01
    input_file: fixtures/n01-readonly-binding.jsonl
    expected:
      alert_count: 0
  - id: C02
    input_file: fixtures/c02-duplicate-event.jsonl
    expected:
      alert_count: 1
  - id: D01
    input_file: fixtures/d01-missing-roleref.jsonl
    expected:
      security_alert_count: 0
      data_quality_finding_count: 1
~~~

Cách tổ chức này giúp CI so sánh **actual** với **expected**. Đây là schema học tập, cần ánh xạ sang framework test và cơ chế query/alert thực tế của tổ chức.

### 5.6. Kiểm thử thủ công theo trình tự

1. Chuẩn bị namespace, service account, role/binding và policy trong **sandbox được phép**.
2. Ghi lại commit/digest phiên bản rule, parser, cấu hình nguồn và tên test run.
3. Đảm bảo nguồn Kubernetes audit, collector và đường truyền đã healthy; đồng bộ thời gian và ghi timestamp gốc.
4. Chạy N01 để xác minh thay đổi được phép không tạo cảnh báo nhạy cảm.
5. Chạy P01 trong môi trường thử nghiệm với subject và quyền giới hạn phạm vi thử; sau đó kiểm tra raw audit → normalized event → detection hit → alert.
6. Chạy P02/P03 và các biến thể boundary; xác nhận field actor/target, logic privilege và approval.
7. Chạy C02 để phát hiện alert bị lặp, D01 để xác nhận pipeline báo thiếu dữ liệu.
8. Kiểm tra E01 với kênh on-call thử hoặc diễn tập có thông báo; giữ trace event ID và thời gian từng mốc.
9. Khôi phục role/binding và các cấu hình thử; lưu evidence, verdict và ticket cho case fail.

**Không làm thí nghiệm bằng cách cấp cluster-admin mới trên production chỉ để xem alert có hoạt động.** Nếu cần xác thực đường production, dùng phương thức canary được cấp phép, test account/tài nguyên không nhạy cảm hoặc cách kiểm chứng được phê duyệt phù hợp với hệ thống.

## 6. Kiểm thử correlation và cửa sổ thời gian

Các rule chuỗi sự kiện có thể đúng trên một file JSON được sắp xếp nhưng sai khi chạy thực tế vì log đến trễ, trùng hoặc lệch đồng hồ.

### 6.1. Ví dụ: nhiều lần xác thực thất bại rồi thành công

Giả thuyết: một actor có **ít nhất 5 lần thất bại trong 10 phút** rồi đăng nhập thành công từ cùng context đáng tin có thể đáng điều tra. Các số liệu chỉ để minh họa.

~~~text
RULE login_after_failures

GROUP BY actor_id + trusted_session_context
WINDOW  = 10 minutes measured by event_time
MATCH   = 5 or more failed logins,
          followed by 1 successful login in that window
OUTPUT  = one alert per relevant session/sequence
EXCLUDE = verified synthetic load tests with valid approval
~~~

Với **event_time**:

~~~text
09:00:00  failure
09:01:00  failure
09:02:00  failure
09:03:00  failure
09:04:00  failure
09:05:00  success
EXPECTED: 1 alert

09:00:00  failure
09:01:00  failure
09:02:00  failure
09:03:00  failure
09:05:00  success
EXPECTED: 0 alert theo ngưỡng 5

09:00:00  failure (actor A)
09:01:00  failure (actor B)
09:02:00  failure (actor A)
09:03:00  failure (actor B)
09:04:00  failure (actor A)
09:05:00  success (actor A)
EXPECTED: 0 alert nếu actor A mới có 3 failures
~~~

Định nghĩa cửa sổ cần chính xác:

- Nếu rule dùng cửa sổ **[t-10 phút, t]**, có tính event ở đúng đầu biên không?
- Đếm các thất bại **trước** thành công hay mọi event xuất hiện trong window?
- Nếu success đến trước failure trên bus nhưng event_time đúng thứ tự, có xử lý lại không?
- Nếu cùng event_id được gửi lại, có nhân đôi bộ đếm không?
- Actor qua proxy/NAT có cùng IP; có đủ danh tính tin cậy để không gộp nhầm hai người?
- Nếu event_time lệch 4 phút với đồng hồ hệ thống, kết quả và thời gian cảnh báo bị ảnh hưởng ra sao?

### 6.2. Event time, processing time và late arrival

| Mốc | Ý nghĩa | Nguy cơ khi nhầm |
|---|---|---|
| **event_time** | Lúc hành vi được nguồn ghi nhận. | Đồng hồ nguồn sai hoặc timestamp bị làm giả. |
| **ingested_at** | Khi collector/ingestion nhận bản ghi. | Bị ảnh hưởng bởi transport lag/backpressure. |
| **processed_at** | Khi rule engine đánh giá bản ghi. | Có thể muộn do queue hoặc lịch chạy batch. |
| **alert_created_at** | Khi alert được tạo. | Có thể khác thời gian người trực nhận cảnh báo. |
| **acknowledged_at** | Khi người trực/case nhận xác nhận. | Không đo được nếu chưa tích hợp hệ thống xử lý. |

Ví dụ event xảy ra lúc **10:00:00**, đến pipeline lúc **10:03:00**, rule tạo alert lúc **10:03:10**, người trực nhận lúc **10:03:20**. Detection latency từ hành vi đến alert là **190 giây**, trong đó **180 giây** là chậm ingest; runtime xử lý nhanh không có nghĩa toàn chuỗi nhanh.

### 6.3. Test matrix cho event timing

| Test ID | Tình huống | Expected |
|---|---|---|
| TW01 | Event ở đúng mốc ranh giới cửa sổ. | Kết quả theo quy ước biên đã tài liệu hóa. |
| TW02 | Event đến muộn nhưng còn trong allowed lateness. | Rule giữ khả năng phát hiện theo hợp đồng. |
| TW03 | Event đến sau khi cửa sổ đã đóng. | Xử lý theo policy: late finding, backfill/re-evaluate hoặc gap được ghi nhận, không silently ignore. |
| TW04 | Trùng một event_id ba lần. | Không làm tăng count nếu hệ thống cam kết dedup. |
| TW05 | Các event đến đảo thứ tự. | Không mất chuỗi cần phát hiện trong giới hạn đã định. |
| TW06 | Timestamp bị thiếu hoặc không parse được. | Quarantine/data-quality alert; không âm thầm gắn nhãn benign. |
| TW07 | Hai actor dùng cùng IP công cộng. | Correlation không gộp sai nếu group key theo actor. |
| TW08 | Service restart giữa cửa sổ. | State được khôi phục hoặc gap được phát hiện theo khả năng cam kết. |

**Đối với hệ thống stateful:** cần kiểm tra checkpointing, window eviction, reprocessing và semantics xử lý. “Exactly once” là một cam kết phức tạp của toàn chuỗi; không thể suy ra chỉ từ việc message broker hỗ trợ acknowledgment.

## 7. Kiểm thử dữ liệu nguồn, parser và schema drift

Một detection có thể lỗi dù logic bất biến vì định dạng upstream đổi.

### 7.1. Những vấn đề thường gặp

- API chuyển trường **user.id** sang **principal.id**, khiến filter cũ bỏ qua.
- Log bị đổi kiểu dữ liệu: status code dạng chuỗi thay vì số.
- Trường action bị đổi chữ hoa/chữ thường, namespace hoặc prefix.
- Timestamp bị mất timezone, bị gửi dưới millisecond vs second.
- Nguồn log mới dùng field **roleName**, nhưng rule cần kiểm tra quyền hiệu lực chứ không chỉ tên.
- Agent ngừng đẩy event hoặc chỉ gửi một phần do filter/retention.
- Multi-tenant pipeline làm mất tenant ID, dẫn đến nhầm target hoặc correlate sai.
- Parser lỗi nhưng hệ thống vẫn đưa event thành mẫu rỗng rồi phân loại “không có rủi ro”.

### 7.2. Parser contract test

Ví dụ input raw event:

~~~json
{
  "kind": "Event",
  "verb": "create",
  "objectRef": {
    "resource": "clusterrolebindings",
    "name": "grant-test-admin"
  },
  "user": {
    "username": "system:serviceaccount:lab:automation-test"
  },
  "responseStatus": {"code": 201},
  "requestReceivedTimestamp": "2026-11-28T08:00:01Z"
}
~~~

Expected normalized fields:

~~~yaml
action: "rbac.binding.create"
target.kind: "ClusterRoleBinding"
target.name: "grant-test-admin"
actor.id: "system:serviceaccount:lab:automation-test"
response.status: "success"
event_time: "2026-11-28T08:00:01Z"
~~~

**Điểm cần phân biệt:** phép chuyển **responseStatus.code = 201 → success** chỉ xác nhận API trả kết quả thành công theo phạm vi thao tác. Nó **không** chứng minh role đã cấp quyền admin; parser/logic enrichment phải tra cứu đối tượng liên quan bằng nguồn đáng tin. Nếu event gốc không chứa roleRef, phải thu thêm dữ liệu hoặc kết luận “insufficient context”.

### 7.3. Negative contract test

- Trường target.name null → parser ghi lỗi hoặc đánh dấu quality finding; không tự thay bằng một tên hợp lệ khác.
- event_time không parse → không tạo một timestamp giả rồi tuyên bố latency đạt.
- actor.id thiếu → data-quality finding; không mặc định actor là “system”.
- Event status **403** bị từ chối → không biến thành sự kiện “đã thay đổi quyền”.
- Event từ tenant B → không gắn vào case của tenant A do thiếu tenant scope.

Những test này liên quan **data integrity** và có giá trị bảo mật ngay cả khi chưa tạo alert.

## 8. Kiểm thử alert output, suppression và routing

Một rule khớp đúng nhưng tạo cảnh báo thiếu actor, sai severity hoặc gửi nhầm kênh có thể không đáp ứng nhu cầu assurance.

### 8.1. Output contract

Một alert hữu ích thường chứa:

- Detection ID, rule version, điều kiện trigger, severity và mức tin cậy.
- Event/case ID, actor, target, tenant, cluster/account, thời gian và reference đến log gốc.
- Giải thích vì sao rule khớp, field nào quyết định kết quả, liên kết runbook.
- Owner, kênh routing, SLA và trạng thái xử lý.
- Dấu vết suppression/dedup/enrichment có thể kiểm tra, không làm mất raw evidence.

Kiểm thử alert cần xác minh **nội dung**, **số lượng**, **độ trễ**, **người nhận** và **quyền xem**. Ví dụ 1 alert gửi đúng SIEM nhưng nhóm trực không có quyền xem raw event sẽ gây chậm điều tra.

### 8.2. Suppression và allowlist

Một ngoại lệ hợp lệ cần giới hạn theo actor, action, target, environment và thời gian; không chỉ đối chiếu actor name.

Test nên có:

| Test | Kỳ vọng |
|---|---|
| Approval hợp lệ, đúng actor và target, thời gian trong hiệu lực. | Không phát alert vi phạm; có audit về ngoại lệ được áp dụng. |
| Approval hết hạn. | Alert. |
| Approval cho cluster khác. | Alert. |
| Actor khác dùng cùng ticket ID. | Alert nếu không đúng phạm vi phê duyệt. |
| Ticket tồn tại nhưng chưa được duyệt. | Alert. |
| Rule suppression bị xóa/cập nhật bởi principal không được phép. | Thay đổi bị chặn hoặc có audit/finding theo control tương ứng. |

Nếu rule gặp thay đổi quyền thực sự nguy hiểm nhưng có suppression rộng và im lặng hoàn toàn, bộ test phải thể hiện đây là **lỗ hổng coverage**, không phải “giảm false positive thành công”.

### 8.3. Tránh alert storm và mất tín hiệu quan trọng

Kiểm tra trường hợp cùng một hành vi tạo nhiều log:

- Nhiều pod hoặc collector gửi trùng event.
- Event update và watch notification trùng nội dung nhưng khác event_id.
- Rule chạy lại cửa sổ và tạo alert cũ.
- Một actor thực hiện nhiều thay đổi khác nhau gần nhau, cần phân biệt những finding riêng.

Tiêu chí dedupe cần vừa hạn chế nhiễu vừa không gộp các đối tượng bị xâm phạm khác nhau. Nếu test chỉ so sánh số alert, bổ sung kiểm tra **alert payload** và **số tài sản/actor bị tác động**.

## 9. Từ test rule đến end-to-end exercise

### 9.1. Thực hiện test trong môi trường được phép

Một quy trình khả dụng:

~~~mermaid
flowchart TD
    A["Chốt claim + phạm vi + rủi ro"] --> B["Tạo test ID và expected outcome"]
    B --> C["Xác nhận nguồn và pipeline healthy"]
    C --> D["Chạy fixture / hành vi có kiểm soát"]
    D --> E["Thu raw event, normalized event"]
    E --> F["Đối chiếu detection hit, alert, case"]
    F --> G{"Đạt tất cả acceptance criteria?"}
    G -->|Có| H["Lưu evidence + verdict PASS"]
    G -->|Không| I["FAIL/INCONCLUSIVE + root cause"]
    I --> J["Sửa và regression test"]
    J --> C
    H --> K["Rà soát + lịch kiểm tra lại"]
~~~

Các bước:

1. Phê duyệt phạm vi, người thực hiện và loại hành vi được phép phát sinh.
2. Xác nhận test không ảnh hưởng người dùng thật; dùng synthetic event hoặc tài nguyên lab nếu đủ mục tiêu.
3. Ghi trạng thái ban đầu của source, collector, parser, rule và kênh alert.
4. Tạo test run ID duy nhất để phân biệt với hoạt động thực.
5. Ghi thời gian hành vi, ingest, detection, routing, acknowledgment bằng UTC.
6. Kiểm chứng expected vs actual theo cùng phiên bản rule và dataset.
7. Thu bằng chứng và dọn dẹp state/permissions của test.
8. Phân loại kết quả, khắc phục và chạy lại case đã fail cùng regression quan trọng.

Nếu diễn tập có thể kích hoạt phản ứng tự động gây gián đoạn, cấu hình trước chế độ test hoặc cơ chế phê duyệt. Không cố tình tắt log production, khai thác lỗ hổng thật hay cấp quyền admin thật chỉ để có bằng chứng.

### 9.2. Test dữ liệu và logic không thay thế test con người

Ví dụ rule tạo alert trong 20 giây nhưng kênh trực không có người nhận trong 30 phút. Mục tiêu “phát hiện trong một phút” có thể đạt, còn mục tiêu “tiếp nhận trong năm phút” **không đạt**. Cần test routing và response trong bài diễn tập để phân biệt các kết luận.

## 10. Đo độ hiệu quả: metrics và diễn giải đúng

### 10.1. Confusion matrix cho tập test có nhãn

| | Hành vi thực sự cần cảnh báo | Hành vi không cần cảnh báo |
|---|---|---|
| **Rule tạo alert** | True positive (TP) | False positive (FP) |
| **Rule không tạo alert** | False negative (FN) | True negative (TN) |

Các chỉ số:

- **Precision** = TP / (TP + FP): trong những cảnh báo tạo ra, bao nhiêu cảnh báo đúng theo nhãn.
- **Recall / sensitivity** = TP / (TP + FN): trong những tình huống đáng phát hiện của **tập thử**, có bao nhiêu được phát hiện.
- **False-positive rate** = FP / (FP + TN): trong những trường hợp âm tính của tập thử, tỷ lệ bị cảnh báo sai.
- **Specificity** = TN / (TN + FP): trong những trường hợp âm tính, tỷ lệ được phân loại đúng.
- **Detection latency** = alert_created_at − event_time, nếu nguồn thời gian đáng tin và cùng hệ quy chiếu.
- **Delivery latency** = received_at − alert_created_at, nếu đã có mốc nhận đáng tin.
- **Coverage** = số use case ưu tiên có test đạt / tổng use case ưu tiên trong phạm vi và kỳ báo cáo.

**Không áp dụng công thức khi mẫu số bằng 0.** Đặc biệt, nếu tập dữ liệu chỉ có positive cases thì không thể kết luận precision hoặc false-positive rate; nếu chỉ test một kiểu tấn công, recall tính ra chỉ phản ánh tập đó.

### 10.2. Ví dụ tính metrics từ test suite

Một bộ thử gồm 40 trường hợp đã được reviewer gắn nhãn: 20 positive, 20 negative. Kết quả:

- 17 positive có alert → TP = 17.
- 3 positive bị bỏ sót → FN = 3.
- 4 negative bị alert → FP = 4.
- 16 negative không alert → TN = 16.

Suy ra:

- **Precision** = 17 / (17 + 4) ≈ **81,0%**.
- **Recall** = 17 / (17 + 3) = **85%**.
- **False-positive rate** = 4 / (4 + 16) = **20%**.
- **Specificity** = 16 / (16 + 4) = **80%**.

Đây là kết quả **trên bộ test được chọn**, không phải tỷ lệ dự đoán chắc chắn trong production. Dataset synthetic có thể không đại diện cơ cấu hành vi thực tế; tỷ lệ xuất hiện threat ngoài thực tế thường rất khác tỷ lệ 50% positive trong test suite. Cần kết hợp hậu kiểm incident, dữ liệu vận hành, đánh giá mẫu alert và authorized emulation để hiểu giới hạn.

### 10.3. Đo thời gian bằng timestamp đúng

Giả sử:

~~~text
event_time         = 10:00:00 UTC
ingested_at        = 10:00:07 UTC
rule_evaluated_at  = 10:00:20 UTC
alert_created_at   = 10:00:25 UTC
received_at        = 10:00:33 UTC
acknowledged_at    = 10:01:10 UTC
~~~

Khi timestamp đáng tin:

- Ingestion latency = **7 giây**.
- Detection latency (event → alert) = **25 giây**.
- Delivery latency (alert → received) = **8 giây**.
- Time-to-ack (received → acknowledged) = **37 giây**.

Phải khai báo định nghĩa trước khi so với SLA. Không đánh đồng MTTD trên sự cố thực với detection latency của các event canary.

## 11. Tự động hóa test trong CI/CD và định kỳ

### 11.1. Cấu trúc pipeline thử nghiệm

Một workflow có thể gồm:

~~~mermaid
flowchart LR
    PR["Rule / parser change"] --> L["Lint + schema check"]
    L --> U["Unit positive/negative/boundary"]
    U --> C["Correlation + replay"]
    C --> E["Integration test"]
    E --> R["Review approval"]
    R --> D["Deploy có kiểm soát"]
    D --> S["Scheduled canary + health + regression"]
    S --> F["Findings / cải tiến"]
    F --> PR
~~~

Gợi ý về những gate phải vượt qua:

| Gate | Khi chạy | Điều kiện pass |
|---|---|---|
| **Static/schema gate** | Mỗi pull request. | Rule parse được, trường hợp lệ, owner và test metadata đủ. |
| **Logic regression gate** | Mỗi thay đổi rule/allowlist. | Các positive/negative/boundary bắt buộc đúng expected. |
| **Parser contract gate** | Khi parser/schema nguồn thay đổi. | Field trọng yếu không mất hoặc được migration có test. |
| **Integration gate** | Trước deploy và khi pipeline thay đổi. | Event có thể đi qua ingestion, correlation, alert đúng. |
| **Response gate** | Theo lịch và khi thay đổi routing/runbook. | Alert được chuyển đúng nơi, case/ack có trace. |
| **Continuous health gate** | Theo lịch vận hành. | Nguồn critical healthy, độ trễ và backlog trong ngưỡng. |

Một false-positive test fail có thể là release blocker đối với rule có ảnh hưởng vận hành lớn. Phân loại mức độ chặn theo rủi ro và thẩm quyền phê duyệt, tránh tạo một pipeline chỉ có tên “security” nhưng luôn cho qua các fail không được review.

### 11.2. Duy trì bộ test có giá trị

- Version rule, parser, fixture, môi trường và expected outcome cùng nhau.
- Dùng stable test IDs để truy vết từ lần đầu phát hiện lỗi tới lần sửa.
- Gắn test với threat/use-case ID và control requirement để xác định phạm vi.
- Lưu case thể hiện bug từng xảy ra dưới dạng regression.
- Thay đổi threshold phải kéo theo sửa expected kết hợp đánh giá noise và coverage.
- Không bỏ test fail khỏi suite chỉ để pipeline chuyển màu xanh; nếu cần loại trừ, ghi owner, lý do, rủi ro và thời hạn.
- Theo dõi test flakiness; phân biệt do hạ tầng với do logic.
- Định kỳ chạy test bằng raw-source/event giả lập có kiểm soát, vì unit fixture có thể bypass parser hoặc collector.

### 11.3. Synthetic canary là phép thử health, không thay hết threat test

Một event giả dạng **security.detection.test_canary**, có test_run_id, phát từ nguồn chuyên dụng và đi qua pipeline, giúp đo đường ingest và alert. Tuy nhiên, canary không chứng minh IAM audit hoặc Kubernetes audit **thật** còn đủ quyền, đủ trường và đang thu thập đúng môi trường. Cần bổ sung source health, asset inventory, sampling data quality và các test sinh hành vi được ủy quyền.

## 12. Bằng chứng assurance và quyết định PASS/FAIL

### 12.1. Truy vết từ mục tiêu đến bằng chứng

~~~mermaid
flowchart LR
    Risk["Risk / threat"] --> Claim["Detection claim"]
    Claim --> Control["Telemetry + rule + runbook"]
    Control --> Cases["Test cases + criteria"]
    Cases --> Results["Actual results"]
    Results --> Evidence["Evidence + provenance"]
    Evidence --> Decision["PASS / FAIL / INCONCLUSIVE"]
    Decision --> Action["Fix / exception / retest"]
    Action --> Claim
~~~

Một hồ sơ kiểm thử cần trả lời:

- **Đã kiểm tra gì?** Detection/use-case ID, security objective và phạm vi.
- **Đã kiểm tra ở đâu?** Environment, tenant/cluster, log source, integration route, rule/parser version.
- **Đã tạo gì?** Test IDs, dữ liệu hoặc hành vi, timestamp, expected outcomes.
- **Thực tế ra sao?** Raw/normalized event, alert/case, timing, lỗi và health signals.
- **Được ai đánh giá?** Người chạy, reviewer, owner, quyết định và thời hạn.
- **Còn thiếu gì?** Chưa thử production, thiếu kỹ thuật biến thể, dữ liệu trễ ngoài giới hạn hoặc tác động không thể kết luận.

### 12.2. Cấu trúc evidence minh họa

~~~text
assurance/detection-tests/DET-K8S-RBAC-007/
  contract.yaml
  scope-and-risk.md
  run-2026-11-28/
    run-metadata.json
    rule-version.txt
    parser-version.txt
    data-source-health.json
    test-fixtures/
      positive.jsonl
      negative.jsonl
      boundary.jsonl
    expected-results.json
    actual-results.json
    raw-events-sanitized.jsonl
    normalized-events.jsonl
    alert-and-case-timeline.csv
    evidence-integrity.txt
    exceptions-and-gaps.md
    review-decision.md
~~~

Đây là **mô hình lưu trữ**, không phải yêu cầu cố định của công cụ. Trong môi trường thật, chú ý:

- Phân quyền truy cập, encryption, retention và giới hạn dữ liệu cá nhân.
- Không đưa token/secret hay dữ liệu nhạy cảm vào fixture và báo cáo.
- Liên kết event/alert bằng ID và truy vết được đến nguồn; tránh chỉ lưu ảnh dashboard.
- Lưu timestamp có timezone, commit/digest của rule và parser, phiên bản schema.
- Bảo vệ bằng chứng khỏi chỉnh sửa/xóa trái phép và có audit quyền quản trị.
- Nếu vì riêng tư chỉ giữ dữ liệu tổng hợp, phải nêu giới hạn khả năng tái hiện/đối chiếu.

### 12.3. Ghi verdict rõ ràng

| Trạng thái | Khi dùng | Hành động |
|---|---|---|
| **PASS** | Test chạy hợp lệ, mọi điều kiện expected quan trọng được thỏa. | Lưu evidence, cập nhật trạng thái coverage và lịch kiểm tra lại. |
| **FAIL** | Test hợp lệ nhưng actual trái expected. | Tạo finding/ticket, severity, owner, kế hoạch sửa và regression. |
| **INCONCLUSIVE** | Test không đủ dữ liệu hoặc hạ tầng test bị lỗi nên không xác định hiệu lực. | Sửa môi trường/nguồn, chạy lại; không tính thành pass. |
| **NOT RUN** | Chưa chạy vì ngoài phạm vi, chưa được phép hoặc chưa có điều kiện. | Nêu lý do, rủi ro và kế hoạch/ngoại lệ. |
| **WAIVED/EXCEPTION** | Quy trình chấp nhận rủi ro tồn dư đã phê duyệt. | Ghi người phê duyệt, giới hạn và hạn hết hiệu lực; không đổi thành PASS. |

**Kết luận đúng phải theo phạm vi claim.** Tất cả unit tests pass chỉ cho phép khẳng định logic hoạt động trên fixture. Muốn khẳng định detection hoạt động trong production phải có bằng chứng chất lượng nguồn, pipeline và cảnh báo trong môi trường đó, kèm giới hạn kiểm chứng được công bố.

## 13. Các thất bại thường gặp và cách khắc phục

| Vấn đề | Tại sao kết luận dễ sai | Cách xử lý |
|---|---|---|
| Chỉ có test dương tính. | Rule có thể cảnh báo tất cả event. | Thêm negative và near-miss để đo phân biệt. |
| Coi event replay là kiểm thử end-to-end. | Replay bỏ qua nguồn và một phần pipeline. | Đánh dấu T1/T3 đúng tầng; bổ sung T4/T5. |
| So expected trên số alert mà bỏ qua payload. | Alert thiếu actor/target, sai tenant hoặc severity vẫn được tính pass. | So cả field bắt buộc và provenance. |
| Dùng cùng dataset xây rule và đánh giá. | Kết quả có thể overfit. | Giữ holdout/cases độc lập, thử variants có kiểm soát. |
| Không test event trễ hoặc out-of-order. | Stateful rule mất chuỗi hoặc tăng đếm sai. | Time-window, replay, dedup và restart tests. |
| Coi thiếu log là negative outcome. | Không phân biệt không xảy ra hành vi và mất telemetry. | Data health gate, inconclusive và source gap alert. |
| Không kiểm tra approval/suppression hết hạn. | Allowlist quá rộng che hành vi nguy hiểm. | Boundary và scope tests cho ngoại lệ. |
| Hard-code tên role hoặc username. | Biến thể tên làm bỏ sót quyền tương đương. | Test effective permissions và actor identity. |
| Chỉ đo rule execution time. | Chậm ingest/routing vẫn làm trượt SLA. | Timestamp event → ingest → alert → delivered → ack. |
| Dùng dataset synthetic để suy ra false-negative rate production. | Phân bố synthetic khác môi trường thật. | Nêu hạn chế, kết hợp incident review và authorized emulation. |
| Kích hoạt hành động nguy hiểm trong production. | Test làm tăng rủi ro hơn giá trị bảo đảm. | Sandbox, canary và plan kiểm soát/rollback. |
| Lưu ảnh màn hình nhưng thiếu versions. | Auditor không thể tái hiện hoặc xác định rule nào đã chạy. | Thêm fixture, raw/normalized event, expected/actual, commit và timeline. |

## 14. Bài tập ứng dụng: đánh giá một test suite có vấn đề

**Bối cảnh:** nhóm detection có rule cảnh báo “nhiều lần đăng nhập thất bại rồi thành công”. Để chứng minh chất lượng, họ chạy 10 positive fixtures, cả 10 đều tạo alert. Hệ thống cho biết “100% detection accuracy” và đóng issue. Sau deploy, nhân viên trực nhận hàng trăm cảnh báo do một service account tự động retry; trong khi một số hành vi đáng ngờ khác không bị phát hiện vì event đến trễ hơn window của rule.

**Phân tích:**

1. **Tuyên bố vượt quá bằng chứng:** 10/10 positive pass chỉ chứng minh recall trên **10 positive fixtures cụ thể**, không thể tính accuracy/precision/FPR khi chưa có negative cases.
2. **Thiếu negative context:** service account retry và shared IP cần là test âm tính/near-miss nếu đáp ứng định nghĩa hành vi hợp lệ.
3. **Thiếu time-window tests:** chưa xác minh allowed lateness, event-time ordering và window closure.
4. **Thiếu tầng tích hợp:** bộ fixture không xác nhận parser, nguồn production, alert routing và người trực.
5. **Quyết định sửa:** giữ 10 positive fixtures, bổ sung negative/edge cases, kiểm tra rule filtering/correlation, cập nhật runbook, chạy regression và thử source-to-alert trong môi trường được phép.
6. **Assurance finding:** ghi phạm vi claim chưa đạt, owner, ngưỡng chất lượng mới, ngày khắc phục và bằng chứng chạy lại.

**Yêu cầu thực hành:** thiết kế tối thiểu 8 test cases (2 positive, 2 negative, 2 boundary, 1 reliability, 1 end-to-end). Với mỗi case, nêu input, expected alert count, các field phải đúng và một bằng chứng cần giữ.

## 15. Checklist trước khi kết luận detection test đạt

- [ ] Test gắn với threat hypothesis, use-case ID và security claim cụ thể.
- [ ] Phạm vi hệ thống, dữ liệu, environment và kỹ thuật tấn công rõ ràng.
- [ ] Rule version, parser version, schema và nguồn dữ liệu được chốt.
- [ ] Có test positive, negative, boundary và regression liên quan rủi ro.
- [ ] Correlation kiểm tra actor, tenant, target, điều kiện thời gian và join key.
- [ ] Có test trùng lặp, thứ tự đảo, đến trễ và trường dữ liệu thiếu khi áp dụng.
- [ ] Dữ liệu không đạt chất lượng sinh health finding hoặc verdict inconclusive đúng chính sách.
- [ ] Alert payload, severity, dedup, suppression, routing và runbook được xác minh.
- [ ] Tuyên bố về SLA có đo mốc event, ingest, alert, delivered và acknowledgment phù hợp.
- [ ] Test end-to-end được thực hiện trong phạm vi được phép, có rollback hoặc cleanup.
- [ ] PASS/FAIL/INCONCLUSIVE phân biệt rõ; case fail có owner và kế hoạch khắc phục.
- [ ] Evidence có ID, thời điểm, phiên bản, expected/actual và người review.
- [ ] Kết luận chỉ áp dụng cho phạm vi đã thử; điểm mù và rủi ro tồn dư được ghi.
- [ ] Test suite được tái chạy sau thay đổi rule, parser, nguồn, policy và hệ thống vận hành.

## 16. Câu hỏi tự đánh giá

1. Một rule tạo đúng một alert trên JSON fixture. Đã có thể tuyên bố “phát hiện mọi trường hợp cấp quyền admin trong production” chưa? Cần thêm bằng chứng nào?
2. Vì sao cần negative tests và near-miss tests, kể cả khi mục tiêu ưu tiên của tổ chức là không bỏ sót hành vi nguy hiểm?
3. Event có event_time 10:00 nhưng ingest lúc 10:05; rule tạo alert lúc 10:05:05. Nếu SLA là phát hiện trong 2 phút từ khi hành vi xảy ra, kết quả ra sao?
4. Sự kiện đổi quyền bị API từ chối nhưng rule vẫn tạo alert “quyền admin đã được cấp”. Đây là loại lỗi nào, và nên có test gì?
5. Khi rule được sửa để giảm false positive, tại sao phải chạy lại cả positive và regression cases?
6. Một canary event đi qua SIEM bình thường nhưng Kubernetes audit đã bị ngừng. Claim nào được canary hỗ trợ, claim nào vẫn chưa được chứng minh?
7. Bạn sẽ lưu những bằng chứng gì để một người không tham gia thử nghiệm có thể tái hiện hoặc thẩm định kết quả?

**Điểm cốt lõi:** detection test không chỉ kiểm tra query có chạy hay không. Nó chứng minh trong **phạm vi xác định** rằng nguồn dữ liệu cung cấp đủ tín hiệu, logic phân biệt đúng hành vi, cảnh báo đến đúng nơi đúng thời gian và các giới hạn được ghi nhận minh bạch. Đó là cơ sở để vận hành security assurance liên tục và khắc phục những khoảng trống phát hiện có bằng chứng.
