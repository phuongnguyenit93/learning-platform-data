# Tự động hóa thao tác lặp và giảm gánh nặng vận hành

> **Chương:** Vận hành hệ thống  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào cách tìm, thiết kế và vận hành automation cho các thao tác lặp; giảm toil, rút ngắn thời gian xử lý, tăng tính nhất quán và bảo vệ độ tin cậy, bảo mật, khả năng mở rộng và chi phí theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt automation với scripting, orchestration và self-service; nhận diện công việc vận hành lặp có thể tự động hóa.
2. Ưu tiên cơ hội automation dựa trên tần suất, thời gian, lỗi thao tác, rủi ro và giá trị giảm toil.
3. Thiết kế workflow có trigger, precondition, action, postcondition, timeout, retry, idempotency và rollback/compensation.
4. Đưa guardrail, quyền tối thiểu, approval và audit vào automation có tác động tới production.
5. Chọn giữa scheduled job, event-driven automation, workflow engine, infrastructure as code và runbook automation.
6. Tích hợp automation với monitoring, incident management, CI/CD, cloud APIs và hệ thống ghi nhận thay đổi.
7. Đo hiệu quả, kiểm thử failure mode và quản lý lifecycle để automation không trở thành một nguồn sự cố mới.

## 1. Vì sao cần tự động hóa thao tác lặp?

Đội vận hành cloud thường phải xử lý nhiều công việc định kỳ hoặc lặp lại khi có sự kiện:

- Tạo môi trường development/staging theo mẫu chuẩn.
- Kiểm tra backup, bản vá, certificate và secret sắp hết hạn.
- Scale worker khi queue backlog tăng.
- Thu thập log và thông tin chẩn đoán khi có incident.
- Khởi chạy kiểm thử smoke sau deployment.
- Thu hồi quyền tạm thời khi hết hạn.
- Dọn tài nguyên thử nghiệm không còn owner.
- Tạo báo cáo chi phí và cảnh báo resource bất thường.
- Thực hiện failover, restore hoặc replay theo runbook đã được kiểm chứng.

Làm thủ công từng lần tạo ra độ trễ, chi phí nhân lực và sai khác giữa người thực hiện. Nhưng tự động hóa thiếu kiểm soát có thể khuếch đại lỗi: một script xóa nhầm tài nguyên trên toàn bộ production nhanh hơn nhiều so với thao tác tay; một vòng retry sai có thể tạo hàng nghìn resource hoặc giao dịch trùng.

**Mục tiêu của automation là làm một quy trình lặp trở nên có thể dự đoán, quan sát, kiểm soát và cải tiến.** Số lượng script hoặc workflow không phải thước đo thành công.

### 1.1. Automation, scripting và orchestration

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Scripting | Thực hiện một chuỗi lệnh hoặc biến đổi có giới hạn | Script kiểm tra certificate expiry |
| Automation | Tự động kích hoạt và thực hiện một công việc theo điều kiện/quy tắc | Tạo cảnh báo và ticket khi certificate còn 14 ngày |
| Orchestration | Điều phối nhiều bước, hệ thống hoặc dependency theo workflow | Provision network, database, identity rồi deploy service |
| Self-service | Cho phép người dùng được ủy quyền yêu cầu tác vụ chuẩn qua giao diện/API | Developer tự tạo staging environment từ template |
| Remediation automation | Phát hiện và thực hiện hành động khắc phục theo policy | Tự cô lập instance có dấu hiệu compromise trong phạm vi xác định |

Một script có thể là thành phần của automation; orchestration thường phối hợp nhiều automation. Self-service cần policy, quota và audit để yêu cầu của người dùng không vượt guardrail.

## 2. Tìm cơ hội automation và giảm toil

Toil là công việc vận hành thủ công, lặp lại, có tính phản ứng và tăng theo quy mô mà không tạo ra cải tiến lâu dài cho hệ thống. Không phải mọi công việc thủ công đều là toil: review kiến trúc, xử lý một sự cố mới hoặc đưa ra quyết định nghiệp vụ có thể cần phán đoán của con người.

### 2.1. Dấu hiệu công việc đáng tự động hóa

- Xuất hiện thường xuyên với quy trình tương đối ổn định.
- Có đầu vào, đầu ra và điều kiện hoàn thành rõ.
- Người thực hiện thường phải copy/paste hoặc làm theo checklist.
- Kết quả có thể kiểm tra tự động bằng metric/config/state.
- Lỗi thao tác gây incident hoặc tốn nhiều thời gian phát hiện.
- Quy mô tăng khiến số lần chạy tăng theo số service, account hoặc tenant.
- Có thể tạo guardrail để giới hạn hành động sai.

Ví dụ: kiểm tra 200 certificate mỗi ngày và nhắc owner là cơ hội tốt. Quyết định có nên chấp nhận rủi ro khi certificate hết hạn ảnh hưởng hệ thống thanh toán vẫn cần người có thẩm quyền hoặc policy quyết định rõ.

### 2.2. Chấm điểm cơ hội automation

Có thể dùng bảng ưu tiên định tính:

| Tiêu chí | Câu hỏi |
| --- | --- |
| Tần suất | Công việc xảy ra bao nhiêu lần mỗi ngày/tuần/tháng? |
| Thời gian | Mỗi lần cần bao nhiêu phút của kỹ sư? |
| Error rate | Có bao nhiêu lỗi thao tác, retry hoặc rework? |
| Variability | Các lần chạy có cùng điều kiện và quy tắc không? |
| Impact | Sai thao tác gây ảnh hưởng bao nhiêu service/user/data? |
| Repeatability | Đầu vào và kết quả có thể xác định bằng máy không? |
| Reversibility | Hành động có thể rollback/compensate không? |
| Automation cost | Xây dựng, vận hành, kiểm thử và bảo trì tốn bao nhiêu? |

Một mô hình đơn giản:

\[
AnnualBenefit = N \times T \times C
\]

Trong đó:
- \(N\): số lần thực hiện trong năm.
- \(T\): thời gian tiết kiệm mỗi lần, tính theo giờ.
- \(C\): chi phí lao động quy đổi mỗi giờ.

Có thể mở rộng thêm chi phí lỗi tránh được và chi phí vận hành automation:

\[
NetValue = AnnualBenefit + AvoidedIncidentCost - BuildCost - AnnualRunCost
\]

Đây là mô hình tài chính giản lược. Không nên biến giờ tiết kiệm thành lợi ích tiền mặt nếu tổ chức không thực sự giảm chi phí hoặc tạo thêm năng lực có giá trị. Cần tính cả review, exception, failed run và bảo trì workflow.

### 2.3. Ma trận ưu tiên

| Công việc | Tần suất | Tính ổn định | Rủi ro khi tự động hóa | Hướng tiếp cận |
| --- | --- | --- | --- | --- |
| Kiểm tra certificate expiry | Cao | Cao | Thấp | Tự động kiểm tra và cảnh báo |
| Tạo môi trường test theo template | Trung bình/cao | Cao | Trung bình | Self-service có quota/TTL |
| Xóa resource idle production | Cao | Trung bình | Cao | Phát hiện tự động, phê duyệt trước khi xóa |
| Rotate secret cho service hỗ trợ | Theo lịch | Cao nếu có quy trình chuẩn | Trung bình/cao | Tự động theo wave, verify và rollback |
| Failover database | Hiếm | Quy trình có điều kiện | Rất cao | Runbook hỗ trợ + approval; tự động từng bước đã thử |
| Điều tra incident mới | Không dự đoán | Thấp | Cao | Hỗ trợ thu thập dữ liệu, giữ quyết định cho responder |

Tự động hóa kiểm tra và đề xuất thường an toàn hơn tự động hóa hành động phá hủy. Có thể tiến dần từ observe-only → recommend → approval-gated → bounded auto-remediation.

## 3. Từ runbook thủ công tới automation

Runbook là quy trình ghi rõ cách thực hiện và xác minh một công việc. Trước khi tự động hóa, cần làm rõ quy trình hiện tại và những trường hợp ngoại lệ.

### 3.1. Chuẩn hóa runbook

Một runbook hữu ích cần:
- Mục đích và phạm vi.
- Trigger hoặc tình huống áp dụng.
- Điều kiện tiên quyết và quyền cần thiết.
- Các bước thao tác theo thứ tự.
- Kết quả mong đợi sau mỗi bước.
- Timeout, retry và điều kiện dừng.
- Cách rollback/compensation.
- Bằng chứng/log cần lưu.
- Owner, escalation và thời điểm review.

Nếu runbook chỉ có câu "restart service nếu thấy chậm", quy trình chưa đủ rõ để tự động hóa. Phải xác định tín hiệu nào chứng minh restart là lựa chọn đúng, service nào được phép restart, giới hạn số lần và cách xác nhận sau đó.

### 3.2. Mô hình runbook-to-automation

~~~mermaid
flowchart TD
    A["Runbook thủ công"] --> B["Chuẩn hóa input / precondition"]
    B --> C["Chia bước và dependency"]
    C --> D["Định nghĩa success / failure"]
    D --> E["Thêm guardrail, quyền và audit"]
    E --> F["Chạy ở dry-run / staging"]
    F --> G["Canary / approval-gated"]
    G --> H["Bounded automation"]
    H --> I["Metrics, review và cải tiến"]
~~~

Bắt đầu bằng việc tự động thu thập thông tin hoặc thực hiện bước ít rủi ro. Chỉ tự động hóa toàn bộ khi quy trình đã có bằng chứng thành công qua nhiều tình huống, gồm cả lỗi.

### 3.3. Ví dụ: runbook restart worker

Quy trình thủ công ban đầu:

1. Xác định queue nào đang backlog.
2. Kiểm tra worker health và dependency database.
3. Xem số message đang xử lý và age của message cũ nhất.
4. Xác định worker bị stuck hay sink đang quá tải.
5. Chỉ restart worker nếu nguyên nhân thuộc worker.
6. Chờ worker khởi động, xác minh consumer lag giảm.
7. Nếu lỗi tiếp tục, dừng và escalate.

Nếu tự động hóa trực tiếp bước restart chỉ vì queue lag cao, hệ thống có thể restart worker trong khi database đang bão hòa, khiến backlog nặng hơn. Automation phải kiểm tra dependency và có concurrency cap trước hành động.

## 4. Kiến trúc automation trên cloud

Một hệ thống automation có thể gồm các thành phần:

- **Trigger:** lịch, event, alert, API request, change/deployment.
- **Policy/decision:** xác minh scope, precondition, approval và risk.
- **Workflow/orchestrator:** điều phối step, dependency, timeout và trạng thái.
- **Executor/worker:** gọi cloud API, script, IaC hoặc internal service.
- **State store:** lưu workflow ID, idempotency key, checkpoint và kết quả.
- **Secrets/identity:** cung cấp quyền và credential phù hợp.
- **Observability:** log, metric, trace, audit, alert.
- **Notification/approval:** yêu cầu người có thẩm quyền khi cần.

~~~mermaid
flowchart LR
    T["Schedule / Event / API / Alert"] --> G["Trigger validation"]
    G --> P["Policy + precondition"]
    P --> W["Workflow orchestrator"]
    W --> A["Approval gate"]
    A --> E["Executor / cloud API / IaC"]
    E --> V["Postcondition verification"]
    V --> S[("Workflow state / audit")]
    W --> S
    P --> S
    V --> N["Notify owner / ticket"]
    E --> O["Metrics / logs / traces"]
    W --> O
~~~

Không phải mọi automation cần workflow engine riêng. Một scheduled function hoặc CI job đơn giản có thể đủ. Chọn công cụ theo nhu cầu durability, retry, branching, approval, visibility và số hệ thống cần điều phối.

### 4.1. Các kiểu kích hoạt

| Trigger | Khi phù hợp | Ví dụ |
| --- | --- | --- |
| Scheduled | Công việc định kỳ | Báo cáo cost, kiểm tra backup |
| Event-driven | Có sự kiện cụ thể | Certificate sắp hết hạn, deployment hoàn tất |
| Alert-driven | Metric vượt ngưỡng | Queue age cao, node unhealthy |
| API/self-service | Người được quyền chủ động yêu cầu | Tạo staging environment |
| Pipeline-driven | Một thay đổi cần bước xác minh | Smoke test sau deploy |
| Human-approved | Hành động có tác động lớn | Failover, xóa dữ liệu, rotate key cấp hệ thống |

Scheduled job cần xử lý timezone, daylight saving khi liên quan, missed schedule và job chạy chồng. Event-driven cần xử lý duplicate, out-of-order và event bị phát lại.

## 5. Thiết kế workflow có thể tin cậy

### 5.1. Mỗi workflow cần input contract

Input nên được validate và có schema rõ ràng:
- resource/service/environment.
- actor hoặc requesting identity.
- operation và parameters.
- idempotency key hoặc request ID.
- approval reference nếu cần.
- deadline và correlation ID.

Không tin các trường nhạy cảm do client gửi như tenant_id, role, environment hoặc resource owner nếu chưa được xác minh từ identity và inventory đáng tin cậy.

### 5.2. Preconditions, action và postconditions

| Giai đoạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Precondition | Có đúng tài nguyên và trạng thái không? | Resource thuộc project cho phép; backup gần nhất hợp lệ |
| Authorization | Ai được phép yêu cầu và thực hiện? | Workflow identity chỉ có quyền scale worker pool |
| Action | Thay đổi gì? | Scale từ 4 lên 6 worker |
| Postcondition | Làm sao chứng minh đạt? | Replica ready, queue age giảm, DB saturation không tăng |
| Failure handling | Điều gì xảy ra nếu không đạt? | Rollback scale hoặc giữ trạng thái và alert |
| Evidence | Lưu gì để kiểm tra? | Request ID, old/new value, actor, timestamp, metric |

Nếu postcondition không được xác minh, không đánh dấu workflow thành công chỉ vì API trả HTTP 200.

### 5.3. Idempotency

Một automation có thể được kích hoạt nhiều lần do event duplicate, timeout hoặc scheduler retry. Idempotency giúp cùng một yêu cầu logic không tạo tác dụng phụ lặp.

Ví dụ:
- Dùng idempotency key để tạo một resource hoặc một ticket duy nhất.
- Kiểm tra trạng thái đích trước khi thực hiện action.
- Lưu operation ID và kết quả.
- Dùng desired state trong IaC thay vì lệnh imperative không có kiểm soát.
- Với tài nguyên cloud, dùng deterministic name/tag và reconcile nếu đã tồn tại.

Idempotency cần xác định phạm vi và thời gian lưu key. Hai request có payload giống nhau có phải cùng một ý định không? Nếu không, key phải đại diện đúng operation/business identity.

### 5.4. Retry, timeout và backoff

- Chỉ retry lỗi transient có khả năng phục hồi.
- Dùng exponential backoff với jitter để tránh retry storm.
- Giới hạn số lần thử và tổng deadline.
- Phân biệt lỗi input/authorization với lỗi tạm thời của provider.
- Trước retry action không idempotent, kiểm tra operation trước đó có hoàn tất ở phía đích không.
- Có DLQ/manual review cho workflow không thể tiếp tục.

Một timeout không chứng minh action chưa xảy ra. API cloud có thể đã tạo resource nhưng response bị mất; retry mù có thể tạo resource trùng hoặc chi phí ngoài dự kiến.

### 5.5. Compensation và rollback

Không phải mọi workflow có thể rollback theo nghĩa khôi phục trạng thái trước. Ví dụ gửi email không thể "gửi ngược"; tạo charge cần refund; xóa dữ liệu có thể không phục hồi nếu backup không có.

Phân biệt:
- **Rollback:** đưa cấu hình/resource về trạng thái trước khi thay đổi.
- **Compensation:** thực hiện hành động nghiệp vụ bù trừ.
- **Forward recovery:** tiếp tục sửa từ trạng thái hiện tại để đạt trạng thái hợp lệ.
- **Manual intervention:** dừng và giao cho người xử lý khi không thể tự quyết định an toàn.

Workflow nhiều bước nên ghi checkpoint và trạng thái từng bước để biết phần nào đã hoàn tất trước khi lỗi.

## 6. Orchestration và choreography

### 6.1. Orchestration

Một workflow engine hoặc coordinator quản lý thứ tự, state, retry và timeout của các bước. Phù hợp khi cần quy trình dài, nhiều nhánh, approval, compensation hoặc audit đầy đủ.

Ưu điểm:
- Nhìn thấy workflow end-to-end.
- Có state machine và lịch sử step.
- Dễ đặt timeout, retry, dependency và approval.
- Dễ trả lời công việc đang ở bước nào.

Đánh đổi:
- Orchestrator trở thành dependency vận hành.
- Workflow definition có lifecycle/version.
- Cần tránh tập trung mọi logic nghiệp vụ vào coordinator.
- Phải quản lý state, concurrency, quota và upgrade.

### 6.2. Choreography

Các thành phần phản ứng với event của nhau mà không có một coordinator trung tâm. Phù hợp với event-driven architecture và các consumer độc lập.

Ưu điểm:
- Thành phần ít phụ thuộc trực tiếp vào coordinator.
- Có thể mở rộng consumer độc lập.
- Tách producer và consumer theo event contract.

Đánh đổi:
- Khó nhìn toàn bộ quy trình nếu thiếu correlation/lineage.
- Retry và duplicate có thể lan qua nhiều service.
- Phải quản lý event schema, ordering, idempotency và dead-letter.
- Khó hủy một quy trình nhiều bước khi một consumer thất bại.

### 6.3. So sánh

| Tiêu chí | Orchestration | Choreography |
| --- | --- | --- |
| Điều phối | Central workflow/state machine | Event và phản ứng giữa service |
| Quan sát tiến trình | Thường rõ theo workflow ID | Cần correlation và event tracing |
| Phụ thuộc | Orchestrator | Broker/event contract |
| Thay đổi quy trình | Có thể cần version workflow | Có thể phân tán theo consumer |
| Phù hợp | Quy trình dài, approval, compensation | Event fan-out, consumer độc lập |
| Rủi ro chính | Coordinator bottleneck/failure | Luồng phân tán khó debug |

Có thể kết hợp: orchestration cho quy trình provision/failover, choreography cho phát sự kiện sau khi resource sẵn sàng.

## 7. Guardrail, approval và mức tự động hóa

Không phải mọi thao tác nên tự động hoàn toàn. Mức độ tự động hóa phải tương xứng với tác động và khả năng đảo ngược.

### 7.1. Mô hình mức độ

| Mức | Automation thực hiện | Ví dụ |
| --- | --- | --- |
| Observe | Phát hiện và thu thập thông tin | Kiểm tra backup và tạo report |
| Recommend | Đề xuất action, con người quyết định | Đề xuất right-size instance |
| Approve-to-run | Tạo kế hoạch, chờ người duyệt | Scale production pool hoặc rotate secret |
| Bounded auto-action | Tự hành động trong giới hạn được duyệt | Scale worker trong min/max |
| Fully automated | Tự xử lý end-to-end theo policy | Dọn artifact hết hạn trong namespace riêng |
| Emergency automation | Kích hoạt theo điều kiện khẩn cấp đã định | Cô lập workload có dấu hiệu compromise theo playbook |

Mức tự động hóa có thể khác theo environment. Xóa resource trong dev sandbox có thể tự động; xóa database production cần approval, backup verification và xác nhận owner.

### 7.2. Guardrail bắt buộc cho action rủi ro cao

- Allowlist account, region, environment và resource type.
- Resource ownership/tag đã được xác minh từ inventory.
- Dry-run hoặc preview thay đổi trước khi thực hiện.
- Approval có thời hạn, gắn với chính xác action/parameters.
- Limit số resource, số lần chạy và blast radius mỗi batch.
- Maintenance window hoặc change freeze check khi phù hợp.
- Backup/restore point trước destructive action.
- Postcondition, alert và stop condition.
- Audit actor, approver, input, output và evidence.

Approval không nên chỉ phê duyệt một câu chung như "cho phép chạy automation". Người duyệt cần thấy tác động, phạm vi, tham số cụ thể, rủi ro và kế hoạch phục hồi.

### 7.3. Human-in-the-loop

Con người cần tham gia khi action phụ thuộc vào phán đoán, có rủi ro khó đảo ngược hoặc cần chấp nhận residual risk. Approval workflow nên có:
- Approver role và delegation rules.
- Expiry cho approval.
- Revalidation nếu input/resource thay đổi sau khi duyệt.
- Từ chối và yêu cầu sửa kế hoạch.
- Escalation nếu quá thời hạn.
- Audit và lý do quyết định.

Nếu workflow được duyệt lúc 10:00 cho một database cụ thể nhưng tới 15:00 resource đã được thay thế hoặc trạng thái backup thay đổi, không được mặc nhiên dùng approval cũ.

## 8. Identity và security cho automation

Automation thường có quyền thao tác cloud resource nên identity của nó là một phần quan trọng của security architecture.

Nguyên tắc:
- Dùng workload identity/managed identity hoặc federation thay long-lived static key khi khả thi.
- Mỗi automation hoặc nhóm chức năng có identity riêng.
- Quyền chỉ áp dụng cho API/resource/action cần thiết.
- Tách quyền đọc/đánh giá với quyền thay đổi.
- Secret lấy từ secret manager và không ghi vào log.
- Credential/token có thời hạn và rotation/revocation rõ.
- Production executor không dùng quyền admin toàn account.
- Approval identity tách khỏi executor identity.
- Audit mọi action và policy decision.

### 8.1. Separation of duties

Người đề xuất thay đổi không nhất thiết là người phê duyệt hoặc người kiểm chứng. Với thay đổi có tác động lớn, có thể tách:
- Requester: mô tả mục tiêu.
- Approver: xác nhận risk và scope.
- Executor: workflow identity thực hiện.
- Validator: kiểm tra kết quả và evidence.

Đội nhỏ có thể dùng cơ chế kiểm soát thay thế, nhưng cần xác định rõ ngoại lệ và review.

### 8.2. Bảo vệ automation supply chain

- Version control workflow/script/IaC.
- Code review và test cho thay đổi.
- Pin action/plugin/dependency theo chính sách.
- Build artifact có provenance và quyền deploy scoped.
- Runner/executor cô lập và cập nhật.
- Không tải script động từ nguồn không tin cậy rồi chạy với cloud credential.
- Quét dependency và xử lý lỗ hổng.
- Có kill switch và quy trình thu hồi quyền.

Một workflow đáng tin cậy vẫn có thể bị compromise nếu runner hoặc plugin bị thay thế. Bảo vệ executor quan trọng như bảo vệ workload production.

## 9. Automation với Infrastructure as Code và configuration management

Infrastructure as Code (IaC) định nghĩa hạ tầng dưới dạng mã để review, version và apply theo quy trình. Nó là nền tảng quan trọng cho automation nhưng không phải mọi automation đều nên viết thành IaC.

### 9.1. Desired state và imperative action

- **Declarative/desired state:** mô tả trạng thái mong muốn; tool xác định thay đổi cần làm để reconcile.
- **Imperative:** mô tả các lệnh cần chạy theo trình tự.

Declarative phù hợp với provisioning và configuration lặp lại; imperative có ích cho các tác vụ thủ tục hoặc API operation đặc thù. Với imperative workflow, cần đặc biệt quản lý idempotency, retry và trạng thái từng bước.

### 9.2. Pipeline IaC an toàn

~~~mermaid
flowchart LR
    CODE["IaC change"] --> REVIEW["Code review"]
    REVIEW --> CHECK["Format / policy / security checks"]
    CHECK --> PLAN["Plan / diff"]
    PLAN --> APPROVE["Approval theo môi trường"]
    APPROVE --> APPLY["Apply"]
    APPLY --> VERIFY["Drift / health / cost verification"]
    VERIFY --> AUDIT["Record state and evidence"]
~~~

Các bước:
1. Chạy static validation, lint và policy checks.
2. Tạo plan/diff để thấy resource sẽ thêm, sửa, xóa.
3. Xác định ảnh hưởng và dependency.
4. Duyệt theo scope và environment.
5. Apply với identity giới hạn.
6. Kiểm tra health, drift và kết quả.
7. Lưu state, output, approval và evidence an toàn.

Không đưa secret trực tiếp vào plan/log/artifact. State file của IaC có thể chứa dữ liệu nhạy cảm và cần encryption, access control, locking, backup.

### 9.3. Drift detection

Drift xuất hiện khi trạng thái thực tế khác desired state do thao tác tay, console change hoặc automation khác. Có thể:
- Phát hiện định kỳ và cảnh báo.
- Phân loại drift cho phép/không cho phép.
- Tự reconcile drift ít rủi ro.
- Yêu cầu approval cho drift có tác động.
- Cập nhật source of truth khi thay đổi được chấp thuận.

Không tự động xóa mọi drift. Một thay đổi thủ công có thể là mitigation trong incident và cần được ghi nhận trước khi reconcile.

## 10. Event-driven automation và xử lý duplicate

Event-driven automation phản ứng với metric, audit event, deployment event, cloud resource event hoặc ticket state.

Một event có thể được phát nhiều lần do delivery semantics at-least-once; event có thể đến trễ hoặc sai thứ tự. Workflow cần:
- Event ID và source xác định.
- Validate schema và trust source.
- Deduplicate theo event ID/business key.
- Check resource current state trước action.
- Giới hạn concurrency để tránh nhiều workflow sửa cùng resource.
- Có ordering/version check với event thay đổi trạng thái.
- Replay an toàn và audit.

Ví dụ certificate expiry event có thể được phát mỗi giờ. Automation nên tra trạng thái certificate hiện tại và idempotency key theo certificate ID + expiry generation; nếu certificate đã được renew, không tạo ticket hoặc rotate thêm một lần.

### 10.1. Tránh automation loop

Automation A đổi resource, làm phát event kích hoạt automation B, rồi B đổi lại resource khiến A được kích hoạt liên tục. Để tránh:
- Phân biệt event do user/provider/automation nào tạo.
- Ghi operation/correlation ID.
- Có suppression hoặc debounce phù hợp.
- Dùng desired-state reconciliation có ổn định.
- Đặt rate limit, loop detection và maximum attempts.
- Không bỏ qua event thật chỉ vì nguồn là automation; cần trace và phân loại.

## 11. Các trường hợp sử dụng phổ biến trong cloud operations

### 11.1. Certificate lifecycle

Workflow kiểm tra expiry, chain, endpoint sử dụng, owner và dependency; tạo ticket hoặc cảnh báo theo ngưỡng; renew tự động; deploy certificate; chạy TLS smoke test; verify và rollback khi cần.

Điểm cần chú ý:
- Không rotate mọi endpoint cùng lúc nếu có dependency/cache.
- Có overlap giữa certificate cũ và mới khi giao thức hỗ trợ.
- Theo dõi certificate ở load balancer, ingress, service mesh và external provider.
- Không log private key.
- Cảnh báo nếu renew thành công nhưng deploy/verification thất bại.

### 11.2. Backup verification

Không chỉ kiểm tra job backup thành công. Automation có thể:
1. Xác nhận backup point tồn tại và metadata hợp lệ.
2. Kiểm tra age/retention/encryption.
3. Khởi tạo restore test trong môi trường cô lập theo lịch.
4. Kiểm tra database integrity và application smoke test.
5. Thu thập thời gian restore, dung lượng và lỗi.
6. Ghi evidence, cảnh báo owner nếu không đạt RTO/RPO.

Restore test phải giới hạn network/identity để dữ liệu khôi phục không vô tình kết nối production hoặc phát side effect.

### 11.3. Scaling theo tín hiệu queue

Automation quan sát oldest message age, backlog, throughput và sink health; tính số worker mới trong min/max; kiểm tra quota; scale theo batch nhỏ; sau đó xác minh backlog và dependency saturation.

Không scale chỉ dựa trên queue length nếu mỗi message có chi phí khác nhau hoặc database sink đã quá tải.

### 11.4. Resource cleanup

Phát hiện resource hết TTL hoặc owner không còn hợp lệ; gửi thông báo; xác minh không có dependency/stateful data; tạo snapshot nếu policy yêu cầu; chờ grace period; rồi mới xóa theo allowlist.

Resource production hoặc resource không xác định owner không nên bị xóa tự động chỉ vì thiếu tag. Cần quarantine/notify và escalation.

### 11.5. Incident evidence collection

Khi alert mở, automation có thể thu thập:
- Deployment/feature flag gần đây.
- Metrics/traces/logs trong time window.
- Dependency status, queue age và resource saturation.
- Top error signature, affected tenant/region.
- Runbook liên quan và trạng thái backup.

Thu thập phải tuân thủ data access policy; không copy secret, token hoặc PII ngoài phạm vi cần thiết vào ticket.

## 12. Reliability: timeout, state, concurrency và failure recovery

Automation thường chạy qua nhiều API và có thể kéo dài từ vài giây tới vài giờ. Cần coi workflow là một workload production.

### 12.1. Workflow state machine

Một state machine có thể gồm:
- Pending: đã nhận yêu cầu.
- Validating: kiểm tra input, policy và precondition.
- AwaitingApproval: chờ người có quyền.
- Running: các action đang thực hiện.
- Verifying: kiểm tra postcondition.
- Succeeded: hoàn tất.
- Failed: dừng do lỗi.
- Compensating: thực hiện hành động bù trừ.
- NeedsIntervention: cần người can thiệp.
- Cancelled/Expired: bị hủy hoặc hết hạn.

Trạng thái phải được lưu bền vững nếu workflow có thể restart hoặc executor bị thay thế.

### 12.2. Workflow concurrency và locking

Hai workflow cùng scale, rotate hoặc delete một resource có thể xung đột. Cần:
- Lock theo resource hoặc operation khi thích hợp.
- Optimistic concurrency/version check.
- Queue partition theo resource key.
- Max concurrent runs toàn hệ thống và per tenant.
- TTL và recovery cho lock bị bỏ lại.
- Không giữ lock trong thời gian chờ approval nếu có thể; khi chạy lại phải kiểm tra state/version.

Lock không thay thế idempotency. Executor có thể crash sau action nhưng trước khi lưu state; khi khởi động lại cần truy vấn trạng thái thực tế.

### 12.3. Durable execution và resume

Workflow dài nên lưu checkpoint sau bước đã hoàn tất và thiết kế resume. Khi executor restart:
1. Đọc workflow state.
2. Xác minh version và input còn hợp lệ.
3. Kiểm tra action trước đã xảy ra chưa.
4. Tiếp tục, compensate hoặc yêu cầu người can thiệp.
5. Không giả định step chưa ghi "Succeeded" nghĩa là action chưa thực hiện.

### 12.4. Stop condition và kill switch

Cần có điều kiện dừng khi:
- Tác động vượt giới hạn đã duyệt.
- Dependency hoặc policy service không đáng tin cậy.
- Số retry vượt ngân sách.
- Một postcondition quan trọng thất bại.
- Workflow phát hiện resource ngoài scope.
- Error rate hoặc SLO bị ảnh hưởng.
- Có lệnh kill switch từ người có thẩm quyền.

Kill switch nên dừng khởi tạo workflow mới và cho phép workflow đang chạy đi tới trạng thái an toàn nếu có thể. Với action nguy hiểm, có thể cần dừng tức thì; hành vi phải được thiết kế trước.

## 13. Observability, audit và quản trị workflow

Một automation không quan sát được là một hộp đen có quyền thay đổi production.

### 13.1. Log và trace

Mỗi workflow nên ghi:
- Workflow ID, operation ID, correlation ID.
- Trigger source và event ID.
- Requesting principal và executor identity.
- Input đã chuẩn hóa, loại bỏ secret/PII không cần thiết.
- Policy decision, approval reference và scope.
- Step start/end, attempt, duration và result.
- Resource old/new state theo mức được phép.
- Error classification, retry, compensation và manual intervention.
- Postcondition và evidence link.

Dùng trace context xuyên qua workflow step và service API nếu phù hợp. Không log token, private key hoặc payload nhạy cảm toàn phần.

### 13.2. Metrics

| Metric | Ý nghĩa |
| --- | --- |
| Automation success rate | Tỷ lệ run đạt postcondition |
| Failure rate by step | Bước nào thường lỗi |
| Retry/duplicate rate | Workflow có bất ổn hoặc trigger trùng? |
| Manual intervention rate | Tỷ lệ cần người xử lý |
| Workflow duration p50/p95 | Thời gian hoàn thành và tail latency |
| Approval wait time | Thời gian chờ người duyệt |
| Cost per run | Chi phí executor/API/resource |
| Toil hours saved | Thời gian thủ công thực tế được loại bỏ |
| Change failure rate | Thay đổi do automation gây ra bị rollback/incident |
| Guardrail rejection | Số yêu cầu bị chặn đúng policy |
| Overdue workflow | Công việc chạy lâu/quá hạn |

Thành công kỹ thuật không chỉ là API call trả 200; phải đo outcome và impact. Một workflow tạo 100 resource thành công nhưng không đạt mục tiêu sử dụng có thể là automation kém.

### 13.3. Audit trail và retention

Audit trail cần chống sửa ngoài quy trình, có quyền đọc phù hợp, retention theo policy và liên kết tới ticket/change record. Với action có tác động cao, lưu bản plan, approval, executor version, policy version và postcondition evidence.

Không giữ log vô hạn nếu không có mục đích và căn cứ. Chi phí, privacy và data residency cũng áp dụng cho workflow state/audit store.

## 14. Kiểm thử automation trước production

Automation có thể nguy hiểm hơn code ứng dụng vì nó thường có quyền thay đổi nhiều resource.

### 14.1. Các lớp kiểm thử

1. **Unit test:** validation, policy logic, calculation, state transitions.
2. **Contract test:** cloud/API response, event schema, workflow integration.
3. **Simulation/dry-run:** hiển thị action dự kiến nhưng không thay đổi resource.
4. **Integration test:** chạy với test account/project và resource giả lập.
5. **Failure injection:** timeout, duplicate event, API 429/5xx, executor crash, approval expiry.
6. **Concurrency test:** hai workflow cùng thao tác một resource.
7. **Security test:** identity chỉ có quyền cần, input ngoài scope bị deny.
8. **Canary:** chỉ áp dụng trên một nhóm resource nhỏ trước khi mở rộng.
9. **Recovery test:** resume, compensation, rollback và manual handoff.

### 14.2. Test matrix

| Kịch bản | Kết quả mong muốn |
| --- | --- |
| Event gửi hai lần | Một tác động logic; run duplicate được nhận diện |
| Provider timeout sau khi action hoàn tất | Query state trước retry, không tạo tác động trùng |
| Input yêu cầu xóa resource ngoài allowlist | Từ chối và audit |
| Approval hết hạn | Không thực thi action |
| Executor crash giữa workflow | Resume từ checkpoint hoặc needs intervention |
| Dependency DB unhealthy | Không scale worker vượt giới hạn sink |
| Cloud API trả 429 | Backoff/jitter, không retry storm |
| Postcondition fail | Không báo success; stop/compensate/escalate |
| Policy engine unavailable | Hành vi fail-safe theo loại action |
| Hai run cùng resource | Lock/version check ngăn conflict |

### 14.3. Dry-run không thay thế kiểm thử thật

Dry-run giúp thấy plan và scope nhưng có thể khác hành vi runtime: quyền thật, quota, race condition, provider eventual consistency và API error. Cần chạy test account tương đồng và canary production theo change policy.

## 15. Tình huống thực tế: tự động hóa kiểm tra và gia hạn certificate

### 15.1. Bối cảnh

Một nền tảng đặt chỗ có:
- 120 endpoint HTTPS ở nhiều môi trường.
- Certificate nằm tại load balancer, ingress và một số service.
- Nhiều owner và lịch release khác nhau.
- Một số certificate do CA-managed, số khác được import từ đối tác.
- Sự cố certificate hết hạn từng làm API partner ngừng hoạt động.

### 15.2. Workflow đề xuất

~~~mermaid
flowchart TD
    S["Scheduled daily scan"] --> D["Discover certificates"]
    D --> V["Validate owner, SAN, chain, expiry"]
    V --> T{"Expiry threshold?"}
    T -->|"Còn xa"| R["Record healthy state"]
    T -->|"Sắp hết hạn"| C{"Can auto-renew?"}
    C -->|"Không"| N["Create owner task + alert"]
    C -->|"Có"| P["Check renewal policy and dependency"]
    P --> A["Renew in staged wave"]
    A --> I["Deploy certificate"]
    I --> H["TLS health and endpoint smoke test"]
    H -->|"Pass"| OK["Record evidence"]
    H -->|"Fail"| RB["Rollback / restore previous cert"]
    RB --> N
~~~

### 15.3. Guardrail

- Scope theo inventory certificate đã xác minh owner.
- Không renew/import certificate từ external partner nếu thiếu quy trình phối hợp.
- Kiểm tra SAN, issuer, chain, key type và compatibility.
- Không export private key để đưa vào log hoặc ticket.
- Deploy theo wave, giới hạn số endpoint cùng lúc.
- Có overlap và rollback trong thời gian tương thích.
- Dừng wave nếu TLS error rate tăng hoặc endpoint health fail.
- Ticket và alert phải chứa certificate ID, endpoint, owner và expiry, không chứa secret.

### 15.4. Đo kết quả

- Tỷ lệ certificate có owner và inventory đầy đủ.
- Số certificate hết hạn ngoài dự kiến.
- Tỷ lệ renew/deploy/verification thành công.
- Thời gian từ cảnh báo tới khắc phục.
- Số sự cố TLS và manual intervention.
- Chi phí automation so với toil trước đó.

## 16. Tình huống thực tế thứ hai: self-service tạo môi trường staging

Một đội có nhiều service và môi trường thử nghiệm tạm thời. Mỗi lần developer cần staging, Platform phải tạo network, database, secret, compute, DNS và monitoring. Yêu cầu có thể được tự phục vụ nhưng không được tạo tài nguyên vượt ngân sách hoặc mở public endpoint ngoài policy.

### 16.1. Luồng self-service

1. Developer đăng nhập qua SSO.
2. Chọn template, service, owner, TTL và data profile.
3. Policy engine xác thực quyền, quota, environment và template version.
4. IaC plan hiển thị tài nguyên và cost estimate.
5. Nếu vượt ngưỡng, yêu cầu manager/Platform approval.
6. Workflow apply bằng deploy identity scoped.
7. Smoke test, network/security policy và monitoring verification.
8. Ghi registry resource, owner, expiry và cost tags.
9. Trước TTL, thông báo owner; sau grace period, snapshot theo policy và destroy.
10. Nếu destroy thất bại, giữ ticket/escalation và không giả định đã dọn xong.

### 16.2. Guardrail cho self-service

- Template được version và review.
- Allowlist region, instance size, database engine và image.
- Default private; public access chỉ qua approval.
- Quota theo user/team và môi trường.
- TTL bắt buộc; ngoại lệ TTL cần owner và expiry.
- Không dùng production data trừ khi có masking và approval riêng.
- Secret riêng cho environment.
- Cost tag và budget alert.
- Resource inventory cập nhật sau create/destroy.
- Cleanup có dependency check và postcondition.

Self-service tốt giảm việc chờ Platform, đồng thời biến policy thành đường mặc định dễ dùng thay vì bắt developer tự nhớ mọi quy định.

## 17. Đánh đổi: automation, reliability, performance và cost

| Quyết định | Lợi ích | Đánh đổi/rủi ro |
| --- | --- | --- |
| Tự động remediation | Giảm MTTR, toil và human error | Lỗi policy có thể khuếch đại trên diện rộng |
| Retry tự động | Phục hồi lỗi transient | Retry storm hoặc duplicate side effect |
| Workflow engine | State, audit và orchestration rõ | Thêm dependency và chi phí nền |
| Self-service | Tăng tốc delivery và developer autonomy | Cần guardrail, quota và support model |
| Auto-cleanup | Giảm cost/resource sprawl | Xóa nhầm resource hoặc dữ liệu |
| Auto-scaling | Phản ứng nhanh với tải | Cold start, connection storm và cost spike |
| Approval gate | Giảm hành động rủi ro không mong muốn | Tăng thời gian chờ và approval toil |
| Centralized automation | Chuẩn hóa và reuse | Blast radius/central dependency lớn hơn |

### 17.1. Automation cũng cần SLO

Có thể đặt SLO riêng:
- Tỷ lệ workflow provisioning thành công trong thời hạn.
- Tỷ lệ certificate renew trước expiry.
- Tỷ lệ backup restore test đạt mục tiêu.
- Thời gian automation thu thập incident evidence.
- Tỷ lệ workflow kết thúc ở trạng thái rõ ràng (không stuck).
- Tỷ lệ hành động tự động không gây rollback/incident.

Automation critical path cần availability và DR riêng. Nếu workflow engine không hoạt động, phải biết tác vụ nào có thể chờ và tác vụ nào cần runbook thủ công.

## 18. Quản lý lifecycle và ownership

Automation phải có owner chịu trách nhiệm cả nội dung lẫn vận hành:
- Business/service owner: xác định outcome và risk.
- Automation owner: workflow logic, version, tests và runbook.
- Platform owner: executor, runner, orchestration, state store và quota.
- Security: identity, policy và audit.
- Operations/SRE: SLO, alert, incident response và recovery.

Cần review định kỳ:
- Trigger và API có còn cần thiết?
- Scope/permission có rộng hơn thực tế?
- Dependency/API version có thay đổi?
- Owner còn tồn tại và có năng lực trực?
- Workflow có manual intervention hoặc retry tăng?
- Có automation khác làm cùng hành động?
- Runbook và rollback có còn đúng?
- Có thể loại bỏ automation không còn giá trị?

Automation không có owner nên được coi là nợ vận hành, đặc biệt khi nó có quyền production.

## 19. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tự động hóa quy trình chưa chuẩn hóa | Lỗi và ngoại lệ được khuếch đại | Chuẩn hóa runbook, precondition và success criteria |
| Chỉ đo số script đã tạo | Không chứng minh giảm toil hoặc rủi ro | Đo outcome, thời gian, lỗi và chi phí |
| Retry mọi lỗi | Retry storm và side effect trùng | Phân loại lỗi, retry budget và idempotency |
| Timeout rồi retry ngay | Action cũ có thể đã hoàn tất | Query state và idempotency key |
| Executor dùng quyền admin rộng | Compromise automation gây blast radius lớn | Scoped workload identity và separation of duties |
| Không có approval cho action phá hủy | Xóa nhầm production/resource data | Preview, approval, backup và allowlist |
| Không kiểm tra postcondition | Workflow báo thành công giả | Verify kết quả và lưu evidence |
| Script chạy từ laptop cá nhân | Khó truy vết, environment khác nhau | Runner chuẩn, version control và audit |
| Không có concurrency/locking | Hai run sửa cùng resource | Lock/version check và per-resource serialization |
| Automation loop | Trigger lặp và resource dao động | Correlation, loop detection, rate limit |
| Không quản lý version workflow | Run cũ chạy logic mới hoặc không tương thích | Versioned definition và migration |
| Không có kill switch | Khó dừng khi automation gây sự cố | Stop condition và emergency control |
| Auto-cleanup chỉ dựa vào tag thiếu | Xóa resource chưa rõ owner | Inventory, quarantine, notice và grace period |
| Bỏ qua secret trong state/log | Rò rỉ credential qua audit | Redaction, encryption và access control |
| Không test provider outage/quota | Workflow bị stuck hoặc tạo thay đổi nửa chừng | Failure injection, resume và compensation |
| Không review automation cũ | Permission và dependency lỗi thời | Periodic owner/permission/lifecycle review |

## 20. Bài tập thực hành

Một nền tảng SaaS cloud có 30 service, 6 cluster, nhiều database và khoảng 200 môi trường staging tạm. Platform team dành nhiều thời gian kiểm tra certificate, tạo môi trường, scale worker và thu thập log khi incident. Gần đây, một script cleanup đã xóa nhầm một resource còn được sử dụng vì tag owner bị thiếu.

Hãy thực hiện:

1. Lập inventory các thao tác lặp; ước lượng tần suất, thời gian, lỗi thao tác, impact và automation cost.
2. Chọn ba cơ hội ưu tiên và giải thích tại sao; phân biệt toil với công việc cần phán đoán của con người.
3. Viết runbook chuẩn cho một tác vụ trước khi tự động hóa.
4. Thiết kế workflow có trigger, input contract, precondition, authorization, action, postcondition và evidence.
5. Xác định idempotency key, retry/backoff, timeout, checkpoint và compensation cho event duplicate/provider timeout.
6. Chọn orchestration hay choreography; giải thích tradeoff và state management.
7. Thiết kế approval, guardrail, quota, scope, allowlist và kill switch cho cleanup production.
8. Đề xuất workload identity, least privilege, separation of duties và audit.
9. Viết test matrix gồm duplicate event, crash giữa bước, 429, approval expiry, concurrency và dependency outage.
10. Đặt metrics/SLO cho success rate, duration, retry, intervention, toil saved và change failure rate.
11. Viết ADR cho một automation có tác động production và kế hoạch rollout/canary/rollback.
12. Nêu cách review, deprecate và chuyển owner khi automation không còn được duy trì.

**Tiêu chí tự đánh giá:** lời giải tốt giảm công việc lặp thực sự, có outcome và metric, không biến một lỗi nhỏ thành thay đổi diện rộng, có quyền tối thiểu, trạng thái có thể phục hồi, kiểm tra postcondition và biết khi nào cần dừng để con người quyết định.

## 21. Checklist trước khi đưa automation vào production

- [ ] Công việc và outcome được mô tả; có bằng chứng toil hoặc risk cần giảm.
- [ ] Runbook thủ công đã chuẩn hóa và có owner.
- [ ] Trigger, input schema, requester identity và scope được xác thực.
- [ ] Preconditions, authorization, action và postconditions được định nghĩa.
- [ ] Workflow idempotent; duplicate event và ambiguous timeout được xử lý.
- [ ] Retry có phân loại lỗi, backoff, jitter, budget và deadline.
- [ ] State/checkpoint bền vững; resume và compensation đã kiểm thử.
- [ ] Concurrency, lock và conflict giữa nhiều run được kiểm soát.
- [ ] Guardrail, allowlist, quota, dry-run và approval đúng mức rủi ro.
- [ ] Executor có workload identity và quyền tối thiểu.
- [ ] Secrets không nằm trong code, log, plan hoặc artifact không bảo vệ.
- [ ] Có stop condition, kill switch, rollback và manual handoff.
- [ ] Audit ghi actor, approver, policy, version, action và evidence.
- [ ] Metrics/alerts theo dõi outcome, failure, retry, duration và toil.
- [ ] Đã test duplicate, timeout, crash, 429, policy deny và dependency outage.
- [ ] Có canary/staged rollout và kiểm soát blast radius.
- [ ] Workflow definition, dependency và policy được version/review.
- [ ] Owner, runbook, SLO, lifecycle review và deprecation plan đã rõ.
- [ ] TCO gồm build, runner, orchestration, storage, observability và maintenance.
- [ ] Hiệu quả được đo sau rollout; automation không được giữ chỉ vì đã đầu tư.

## Ghi nhớ

Tự động hóa vận hành hiệu quả bắt đầu từ một quy trình đã hiểu rõ, có đầu vào/đầu ra và điều kiện hoàn thành. Workflow phải xác thực người yêu cầu, kiểm tra policy, thực hiện action có giới hạn, xử lý duplicate/retry, xác minh kết quả và lưu audit. Với hành động có tác động lớn hoặc khó đảo ngược, cần approval và cơ chế dừng rõ ràng.

Hãy đi theo chuỗi **tìm toil → chuẩn hóa runbook → thiết kế workflow và guardrail → kiểm thử failure mode → rollout có kiểm soát → đo kết quả → review lifecycle**. Automation tốt giảm công việc lặp mà vẫn giữ quyền kiểm soát, tính đúng đắn và độ tin cậy của hệ thống.
