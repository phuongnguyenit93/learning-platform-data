# Viết runbook, postmortem và hành động ngăn tái diễn

## Mục tiêu học tập

Một hệ thống AWS production không thể tránh hoàn toàn sự cố. Điều tạo nên khác biệt giữa một đội vận hành trưởng thành và một đội luôn phản ứng trong tình trạng khẩn cấp là khả năng chuẩn bị trước, xử lý có kỷ luật, ghi nhận bằng chứng và biến mỗi sự cố thành cải tiến có thể kiểm chứng.

Runbook mô tả một quy trình có kết quả dự đoán được, chẳng hạn rollback deployment, khôi phục một resource hoặc kiểm tra backlog của queue. Playbook hướng dẫn điều tra khi nguyên nhân chưa rõ: thu thập tín hiệu, đưa ra giả thuyết, kiểm tra từng giả thuyết, cô lập phạm vi ảnh hưởng và quyết định khi nào cần escalation. Postmortem ghi lại điều đã xảy ra, tác động, các yếu tố góp phần và những thay đổi cần thực hiện để giảm khả năng tái diễn.

Bài học thuộc chương **Kiểm thử và xử lý sự cố** của module CLOUD_PROVIDERS_AWS. Nội dung kết nối quy trình vận hành với các dịch vụ AWS như Amazon CloudWatch, Amazon EventBridge, AWS Systems Manager Automation, OpsCenter, CloudTrail và CloudWatch Investigations.

Sau bài học, người học có thể:

- Phân biệt event, alert, incident và problem.
- Phân biệt runbook, playbook, incident response plan và postmortem.
- Thiết kế vòng đời incident với vai trò, mức độ nghiêm trọng, escalation và truyền thông.
- Viết runbook có mục tiêu, điều kiện tiên quyết, bước thực hiện, kết quả mong đợi và rollback.
- Viết playbook điều tra theo decision point, evidence và escalation.
- Tự động hóa các bước ổn định bằng Systems Manager Automation, Lambda, CloudWatch và EventBridge.
- Dùng CloudWatch Investigations và OpsCenter đúng phạm vi.
- Tổ chức postmortem theo hướng blameless, có timeline và nhiều contributing factors.
- Tạo corrective actions có owner, deadline, mức ưu tiên và tiêu chí xác minh.
- Đo hiệu quả cải tiến bằng MTTD, time to engage, time to mitigate, recurrence rate và SLO.
- Kiểm thử runbook, tabletop exercise và game day trước khi cần dùng thật.

## 1. Từ event đến incident và problem

Các khái niệm vận hành có liên quan nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event | Sự kiện xảy ra trong hệ thống, có thể bình thường hoặc bất thường | Deployment hoàn tất, EC2 instance reboot, S3 object được tạo |
| Alert | Thông báo được tạo khi một điều kiện cần chú ý xảy ra | CloudWatch alarm báo p95 latency vượt ngưỡng |
| Incident | Sự gián đoạn hoặc suy giảm dịch vụ cần phối hợp xử lý | API checkout trả 5xx cho nhiều khách hàng |
| Problem | Nguyên nhân hoặc nhóm nguyên nhân nền cần điều tra và xử lý lâu dài | Connection pool không đủ khi traffic tăng |
| Change | Thay đổi có chủ đích đối với hệ thống | Deploy phiên bản mới, đổi policy hoặc tăng capacity |
| Near miss | Sự kiện suýt gây tác động lớn nhưng được ngăn chặn kịp thời | Queue gần hết retention nhưng consumer phục hồi trước khi mất message |

Một alert không nhất thiết là incident. CPU tăng trong vài phút nhưng latency và error rate vẫn trong SLO có thể chỉ cần theo dõi. Ngược lại, incident có thể bắt đầu trước khi alarm được kích hoạt hoặc không có alarm nào phát hiện.

Problem management nhìn xa hơn việc đóng incident. Nếu restart service khôi phục hệ thống nhưng connection leak vẫn tồn tại, incident đã được mitigate nhưng problem chưa được giải quyết.

~~~mermaid
flowchart TD
    A[Event] --> B{Có điều kiện cần chú ý?}
    B -->|Không| C[Record hoặc bỏ qua theo policy]
    B -->|Có| D[Alert]
    D --> E{Có customer / business impact?}
    E -->|Không| F[Operational task hoặc investigation]
    E -->|Có| G[Declare incident]
    G --> H[Mitigate và recover]
    H --> I[Close incident]
    I --> J[Post-incident analysis]
    J --> K[Problem và corrective actions]
    K --> L[Prevent, detect, mitigate tốt hơn]
~~~

## 2. Runbook, playbook, incident plan và postmortem

Bốn loại tài liệu phục vụ các giai đoạn khác nhau.

| Tài liệu | Câu hỏi trả lời | Khi dùng |
|---|---|---|
| Incident management plan | Ai điều phối, mức độ nào, liên hệ ai và cập nhật thông tin ra sao? | Khi incident được khai báo |
| Playbook | Làm sao điều tra một triệu chứng chưa rõ nguyên nhân? | Trong triage và investigation |
| Runbook | Làm thế nào thực hiện một quy trình đã biết để đạt kết quả cụ thể? | Khi triển khai, kiểm tra hoặc remediation |
| Postmortem | Điều gì đã xảy ra, vì sao và cần thay đổi gì? | Sau khi tác động đã được kiểm soát |

Ví dụ: CloudWatch báo SQS backlog tăng.

- Incident plan xác định Incident Commander, đội ứng dụng và người truyền thông.
- Playbook hướng dẫn kiểm tra arrival rate, consumer concurrency, DLQ, downstream dependency và deployment gần nhất.
- Runbook hướng dẫn tăng Lambda reserved concurrency sau khi xác minh quota và dependency capacity, hoặc rollback một thay đổi cấu hình.
- Postmortem ghi nhận nguyên nhân backlog, tác động khách hàng, yếu tố góp phần và hành động dài hạn.

Một runbook nên có kết quả dự đoán được. Một playbook nên có các nhánh quyết định vì nguyên nhân chưa biết. Không biến runbook thành tài liệu troubleshooting vô tận.

## 3. Vòng đời incident

Một quy trình phổ biến gồm các giai đoạn:

1. **Detect:** alarm, customer report, support case hoặc event phát hiện dấu hiệu bất thường.
2. **Declare:** xác nhận incident, chọn severity, tạo incident record và mở kênh phối hợp.
3. **Triage:** xác định phạm vi, customer impact, service bị ảnh hưởng và giả thuyết ban đầu.
4. **Mitigate:** giảm hoặc chặn tác động tới khách hàng; ưu tiên khôi phục dịch vụ an toàn.
5. **Resolve:** xử lý nguyên nhân hoặc thay thế thành phần lỗi bằng phiên bản/cấu hình tốt.
6. **Recover:** xác nhận hệ thống trở lại trạng thái bình thường, xử lý backlog và kiểm tra dữ liệu.
7. **Communicate and close:** cập nhật trạng thái, xác nhận owner và điều kiện đóng incident.
8. **Learn:** thực hiện postmortem, tạo corrective actions và cập nhật runbook/playbook.

Không phải incident nào cũng cần cùng mức thủ tục. Một lỗi nhỏ không ảnh hưởng khách hàng có thể được xử lý như operational task. Incident có mất dữ liệu, bảo mật hoặc ảnh hưởng rộng cần quy trình chuyên biệt.

Trong thời gian incident, ưu tiên là bảo vệ khách hàng và dữ liệu. Điều tra nguyên nhân sâu có thể tiếp tục sau khi dịch vụ đã được khôi phục, miễn là bằng chứng được giữ lại.

## 4. Phân loại mức độ nghiêm trọng

Severity cần phản ánh tác động thực tế, không chỉ một metric đơn lẻ.

Một ma trận mẫu:

| Mức | Tác động | Ví dụ | Cách phản ứng |
|---|---|---|---|
| SEV-1 Critical | Dịch vụ trọng yếu ngừng hoạt động, mất dữ liệu hoặc sự cố bảo mật nghiêm trọng | Checkout không thể giao dịch trên diện rộng | Kích hoạt incident process ngay, điều phối tập trung và cập nhật liên tục |
| SEV-2 High | Chức năng quan trọng suy giảm đáng kể, nhiều khách hàng bị ảnh hưởng | Tỷ lệ thanh toán thất bại tăng mạnh | Gọi đội sở hữu và dependency team, mitigation ưu tiên cao |
| SEV-3 Medium | Ảnh hưởng giới hạn hoặc có workaround | Một nhóm người dùng không xem được báo cáo | Giao owner, theo dõi và xử lý theo SLA |
| SEV-4 Low | Không có customer impact rõ ràng, lỗi nhỏ hoặc near miss | Alarm cảnh báo sớm nhưng SLO vẫn đạt | Tạo operational task hoặc backlog improvement |

Khi phân loại, xem xét:

- Số lượng và tỷ lệ khách hàng bị ảnh hưởng.
- Tác động tới doanh thu, thanh toán, dữ liệu và nghĩa vụ pháp lý.
- Phạm vi service, Region, Availability Zone hoặc tenant.
- Có workaround hay không.
- Tốc độ lan rộng và khả năng phục hồi.
- Có dấu hiệu credential compromise, data exposure hoặc integrity loss không.

Severity có thể tăng hoặc giảm khi có bằng chứng mới. Ghi lại lý do thay đổi để các nhóm hiểu quyết định tại thời điểm đó.

## 5. Vai trò trong incident response

Incident lớn cần phân vai rõ để tránh nhiều người cùng thực hiện một hành động hoặc không ai chịu trách nhiệm.

| Vai trò | Trách nhiệm |
|---|---|
| Incident Commander (IC) | Điều phối, xác định ưu tiên, giao owner, quyết định escalation và giữ nhịp xử lý |
| Technical Lead / Operations Lead | Điều tra kỹ thuật, đề xuất và điều phối mitigation |
| Subject Matter Expert (SME) | Phân tích thành phần chuyên môn như database, network, IAM hoặc application |
| Communications Lead | Cập nhật stakeholder, support và khách hàng theo kế hoạch |
| Scribe | Ghi timeline, quyết định, evidence, action và owner |
| Business Owner | Đánh giá tác động nghiệp vụ, workaround và ưu tiên phục hồi |

Trong incident nhỏ, một người có thể kiêm nhiều vai trò. Trong incident lớn, IC nên tránh tự làm mọi thao tác kỹ thuật vì sẽ mất khả năng điều phối.

Chỉ định người có quyền ra quyết định và người có quyền thực thi remediation. Runbook phải nêu rõ ai được phép restart, failover, rollback, rotate credential hoặc thay đổi traffic.

## 6. Xây dựng incident management plan

Incident plan là tài liệu cấp dịch vụ hoặc tổ chức. Nó không chứa toàn bộ lệnh kỹ thuật; nó xác định cách con người phối hợp.

Một plan nên có:

- Danh sách service và business owner.
- Severity definition và tiêu chí khai báo incident.
- Kênh incident chính thức và kênh dự phòng.
- Cách gọi on-call và escalation path.
- Vai trò IC, technical lead, communications lead và scribe.
- Quy tắc cập nhật nội bộ và khách hàng.
- Quyền truy cập khẩn cấp và break-glass procedure.
- Nơi lưu runbook, playbook, architecture diagram và dependency map.
- Cách mở AWS Support case khi cần.
- Điều kiện mitigation, recovery và close.
- Yêu cầu postmortem và thời hạn thực hiện.

Danh sách liên hệ phải được kiểm tra định kỳ. Một số điện thoại hoặc contact cũ trong plan có thể làm mất nhiều thời gian trong sự cố thật.

## 7. Runbook nên có cấu trúc thống nhất

Runbook cần đủ thông tin để một kỹ sư không phải tác giả có thể thực hiện đúng quy trình.

Mẫu metadata:

| Trường | Nội dung |
|---|---|
| Runbook ID | Mã duy nhất, ví dụ RUN-SQS-001 |
| Title | Tên quy trình |
| Service / Environment | Dịch vụ và môi trường áp dụng |
| Desired outcome | Trạng thái cần đạt sau khi chạy |
| Trigger | Alarm, request hoặc điều kiện bắt đầu |
| Owner | Nhóm chịu trách nhiệm bảo trì |
| Version | Phiên bản tài liệu/automation |
| Last validated | Ngày kiểm thử gần nhất |
| Required permissions | IAM role và quyền cần thiết |
| Tools | AWS CLI, Console, CloudWatch, Systems Manager |
| Risk | Tác động nếu thực hiện sai |
| Approval | Có cần phê duyệt trước bước mutating không? |
| Escalation | Người/nhóm cần gọi nếu không thành công |

Phần procedure nên có các cột:

| Step | Hành động | Kết quả mong đợi | Nếu không đạt |
|---|---|---|---|
| 1 | Kiểm tra trạng thái và phạm vi | Xác định đúng resource | Dừng, xác minh target |
| 2 | Thu thập metrics/logs | Có bằng chứng trước thay đổi | Escalate nếu thiếu dữ liệu |
| 3 | Thực hiện remediation | Resource chuyển trạng thái mong muốn | Rollback hoặc dừng |
| 4 | Verify | SLO và health trở lại bình thường | Tiếp tục playbook |
| 5 | Record | Có execution ID và kết quả | Tạo action nếu runbook lỗi |

Runbook cần có owner và lịch kiểm thử. Tài liệu không được cập nhật theo hệ thống sẽ trở thành nguồn rủi ro.

## 8. Viết bước runbook có thể thực hiện an toàn

Mỗi bước nên dùng động từ cụ thể và chỉ rõ resource.

Ví dụ tốt:

- Lấy ApproximateAgeOfOldestMessage của queue orders-processing-prod.
- Kiểm tra ConcurrentExecutions và Throttles của Lambda consumer trong 15 phút gần nhất.
- So sánh deployment version hiện tại với version trước thời điểm incident.
- Chỉ tăng reserved concurrency sau khi xác nhận downstream database còn capacity.
- Sau thay đổi, quan sát queue age và error rate trong 10 phút.

Ví dụ mơ hồ:

- Kiểm tra queue.
- Tăng tài nguyên nếu cần.
- Restart service.
- Theo dõi xem đã ổn chưa.

Một bước tốt luôn nêu:

1. Resource nào được tác động?
2. Dùng tool hoặc API nào?
3. Input/parameter nào?
4. Kết quả mong đợi là gì?
5. Nếu kết quả khác dự kiến thì làm gì?
6. Bước có thay đổi state hay không?
7. Ai phê duyệt hoặc có thể rollback?

## 9. Playbook điều tra cần decision point

Playbook thường bắt đầu từ triệu chứng chứ chưa biết nguyên nhân.

Ví dụ: API latency tăng.

~~~mermaid
flowchart TD
    A[Alert: API latency tăng] --> B[Confirm customer impact]
    B --> C{Error rate cũng tăng?}
    C -->|Có| D[Kiểm tra 5xx, dependency và deployment]
    C -->|Không| E[Kiểm tra queue, CPU, DB latency và traffic]
    D --> F{Có deployment gần đây?}
    F -->|Có| G[So sánh version và cân nhắc rollback]
    F -->|Không| H[Điều tra dependency và network]
    E --> I{Một dependency bị nghẽn?}
    I -->|Có| J[Giảm tải / scale có kiểm soát]
    I -->|Không| K[Kiểm tra query, cache và request profile]
    G --> L[Verify SLO]
    H --> L
    J --> L
    K --> L
    L --> M{Đã phục hồi?}
    M -->|Có| N[Theo dõi và ghi evidence]
    M -->|Không| O[Escalate / mở rộng phạm vi điều tra]
~~~

Mỗi nhánh nên có lệnh hoặc query cụ thể, kết quả mong đợi và điều kiện dừng. Playbook không nên giả định giả thuyết đầu tiên là đúng.

## 10. Chuẩn bị evidence trước khi remediation

Khi sự cố xảy ra, thao tác sửa nhanh có thể làm mất bằng chứng. Trước một thay đổi lớn, thu thập tối thiểu:

- Thời điểm bắt đầu và thời điểm phát hiện.
- CloudWatch alarm state/history và metric datapoints.
- Application logs, service logs và trace IDs.
- CloudTrail events liên quan đến deployment, policy hoặc configuration.
- Resource ARN, Region, Availability Zone và deployment version.
- Request IDs, error codes và sample sanitized request.
- Queue depth, database load, connection count hoặc resource utilization.
- Những hành động đã thực hiện và kết quả.

Không trì hoãn mitigation khẩn cấp chỉ để thu thập đầy đủ evidence. Hãy lưu phần dữ liệu quan trọng nhất trước nếu có thể, rồi tiếp tục sau khi impact được kiểm soát.

Với security incident, cần tuân theo incident response plan riêng: bảo toàn log và snapshot, hạn chế thay đổi không cần thiết, ghi lại chain of custody và phối hợp security/legal. Không xóa resource hoặc credential evidence trước khi nhóm có thẩm quyền đánh giá.

## 11. Escalation và handoff

Escalation cần dựa trên thời gian, mức độ và điều kiện kỹ thuật.

Ví dụ:

| Điều kiện | Hành động |
|---|---|
| Không xác định được impact sau 10 phút | Gọi service owner và IC |
| Hai lần remediation không thành công | Escalate tới technical lead hoặc platform team |
| Có dấu hiệu mất dữ liệu | Gọi database/data owner ngay |
| Có dấu hiệu credential compromise | Kích hoạt security incident process |
| Incident vượt một Region | Gọi cloud/platform owner và disaster recovery lead |
| Recovery vượt RTO | Kích hoạt phương án DR đã phê duyệt |
| Không có tiến triển sau một chu kỳ điều tra | Tổ chức checkpoint và phân công SME mới |

Các mốc thời gian là ví dụ. Tổ chức cần đặt theo SLO, support coverage và severity. Escalation không có nghĩa là chuyển trách nhiệm rồi rời khỏi incident; người đang giữ vai trò cần xác nhận người nhận đã tiếp quản.

Một handoff tốt bao gồm: impact hiện tại, timeline, giả thuyết đã kiểm tra, evidence, thay đổi đã thực hiện, rủi ro còn lại, bước tiếp theo và người đang sở hữu từng action.

## 12. Alert phải gắn với quy trình phản ứng

Một alert có giá trị khi người nhận biết phải làm gì. Mỗi alarm cần có:

- Metric và threshold.
- Evaluation period và datapoints-to-alarm.
- Severity hoặc priority.
- Owner team.
- Customer impact có thể xảy ra.
- Link tới dashboard.
- Link tới playbook/runbook.
- Escalation condition.
- Hướng dẫn xác định false positive và recovery.

Tránh tạo alert chỉ vì metric khác 0. Threshold phải dựa trên baseline, SLO và hành vi workload.

Ví dụ, SQS queue depth cao không phải lúc nào cũng incident. ApproximateAgeOfOldestMessage có thể liên quan trực tiếp hơn tới độ trễ xử lý. Với API, latency và error rate nên được xem cùng request volume và business SLO.

## 13. Kết nối CloudWatch, EventBridge và Systems Manager Automation

AWS hỗ trợ tự động hóa response từ monitoring event:

1. CloudWatch alarm phát hiện metric vượt điều kiện.
2. Alarm chuyển sang trạng thái ALARM và phát event.
3. SNS có thể thông báo cho người trực hoặc hệ thống paging.
4. EventBridge có thể route event tới Lambda, Systems Manager Automation hoặc tạo OpsItem.
5. Automation runbook thu thập trạng thái hoặc thực hiện remediation được phê duyệt.
6. Kết quả được ghi vào CloudWatch Logs, OpsItem hoặc incident tracking system.

Không tự động thực hiện mọi hành động chỉ vì alarm chuyển ALARM. Có thể bắt đầu bằng read-only diagnostics, sau đó yêu cầu approval cho bước mutating như restart, failover, scale hoặc rollback.

CloudWatch alarm actions chỉ thực thi theo state transition trong nhiều trường hợp; nếu alarm giữ ALARM trong nhiều giờ, action thông thường không tự lặp lại liên tục. Thiết kế retry hoặc periodic re-evaluation riêng nếu cần.

## 14. AWS Systems Manager Automation runbook

Systems Manager Automation thực thi quy trình theo bước. Một Automation document có thể gọi AWS API, chờ resource state, rẽ nhánh, chạy script hoặc gọi runbook khác.

Các action thường gặp:

| Action | Mục đích |
|---|---|
| aws:executeAwsApi | Gọi AWS API |
| aws:assertAwsResourceProperty | Xác nhận resource/event đang ở trạng thái mong đợi |
| aws:waitForAwsResourceProperty | Chờ resource chuyển trạng thái |
| aws:branch | Chọn nhánh theo kết quả |
| aws:executeScript | Chạy Python hoặc PowerShell |
| aws:runCommand | Chạy lệnh trên managed node |
| aws:approve | Dừng để chờ phê duyệt |

Role của Automation cần quyền tối thiểu cho các action được gọi. Runbook phải giới hạn parameter, target và concurrency; với thao tác nguy hiểm, cần approval hoặc execution scope rõ ràng.

### 14.1. Ví dụ runbook chỉ đọc để chẩn đoán SQS backlog

Ví dụ sau lấy queue attributes và CloudWatch alarm state. Nó không thay đổi queue hoặc Lambda.

~~~yaml
---
description: "Read-only diagnostics for an SQS backlog"
schemaVersion: "0.3"
assumeRole: "{{ AutomationAssumeRole }}"
parameters:
  AutomationAssumeRole:
    type: String
    description: "IAM role used by Systems Manager Automation"
  QueueUrl:
    type: String
    description: "URL of the queue to inspect"
  AlarmName:
    type: String
    description: "CloudWatch alarm associated with the queue"
mainSteps:
  - name: inspectQueue
    action: aws:executeAwsApi
    inputs:
      Service: sqs
      Api: GetQueueAttributes
      QueueUrl: "{{ QueueUrl }}"
      AttributeNames:
        - ApproximateNumberOfMessages
        - ApproximateNumberOfMessagesNotVisible
        - ApproximateNumberOfMessagesDelayed
        - VisibilityTimeout
        - RedrivePolicy
    outputs:
      - Name: VisibleMessages
        Selector: "$.Attributes.ApproximateNumberOfMessages"
        Type: String
      - Name: InFlightMessages
        Selector: "$.Attributes.ApproximateNumberOfMessagesNotVisible"
        Type: String
  - name: inspectAlarm
    action: aws:executeAwsApi
    inputs:
      Service: cloudwatch
      Api: DescribeAlarms
      AlarmNames:
        - "{{ AlarmName }}"
    outputs:
      - Name: AlarmState
        Selector: "$.MetricAlarms[0].StateValue"
        Type: String
~~~

Role cần sqs:GetQueueAttributes trên queue và cloudwatch:DescribeAlarms cho alarm. Trong triển khai thực tế, cần xử lý trường hợp alarm không tồn tại, queue URL sai hoặc response không có field mong đợi. Có thể bổ sung output, validation và notification. aws:executeAwsApi có giới hạn thời gian cho mỗi API action; không dùng một step để chạy tác vụ dài.

### 14.2. Phân loại bước read-only và mutating

| Loại bước | Ví dụ | Kiểm soát |
|---|---|---|
| Read-only | Describe queue, get alarm, query metrics | Có thể tự động nếu IAM scope phù hợp |
| Low-risk change | Thêm tag, tạo ticket, tăng log level có thời hạn | Giới hạn target, thời gian và audit |
| Mutating | Restart instance, đổi desired count, rollback deployment | Approval, pre-check, post-check và rollback |
| High-impact | Failover database, rotate credential diện rộng, thay security policy | Incident Commander/owner phê duyệt và runbook riêng |

Không coi aws:executeAwsApi là read-only theo mặc định. Action gọi API có thể thay đổi resource; cần phân loại dựa trên API cụ thể.

## 15. OpsCenter và CloudWatch Investigations

AWS Systems Manager OpsCenter tập trung các operational work items (OpsItems) liên quan đến AWS resource. OpsItem có thể được tạo thủ công, từ CloudWatch alarm hoặc EventBridge event; người vận hành xem resource context và chạy Systems Manager Automation để điều tra/remediate.

CloudWatch Investigations hỗ trợ điều tra operational issue bằng cách tập hợp tín hiệu và đưa ra AI-generated suggestions. Người điều tra xem xét, chấp nhận hoặc loại bỏ findings và có thể thực hiện remediation qua automated runbooks.

Một số lưu ý quan trọng về lựa chọn công cụ:

- AWS Systems Manager Incident Manager đã ngừng nhận khách hàng mới từ ngày 7 tháng 11 năm 2025 và không tiếp tục bổ sung tính năng mới.
- Account đã bật Incident Manager trước thời điểm đó có thể tiếp tục sử dụng trong các account tương ứng.
- AWS khuyến nghị OpsCenter cho việc quản lý operational issues; OpsCenter không cung cấp paging và on-call rotation.
- Nếu cần automated paging, escalation và on-call schedule cho triển khai mới, đánh giá giải pháp từ AWS Partner Network hoặc hệ thống incident management hiện có.
- CloudWatch Investigations hỗ trợ phân tích và gợi ý, nhưng người vận hành vẫn cần xác minh evidence và chịu trách nhiệm với remediation.

Không thiết kế quy trình mới phụ thuộc vào việc mọi account đều có thể bật Incident Manager. Kiểm tra điều kiện account và khả năng hiện hành trước khi chọn dịch vụ.

## 16. Truyền thông trong incident

Truyền thông cần ngắn, chính xác, có timestamp và nêu bước tiếp theo. Không suy đoán nguyên nhân khi chưa có evidence.

Mẫu cập nhật nội bộ:

~~~text
INCIDENT: INC-2026-042
SEVERITY: SEV-2
STATUS: Investigating
STARTED: 2026-11-20 08:15 UTC

CUSTOMER IMPACT:
Một phần request tạo đơn hàng bị timeout tại khu vực ap-southeast-1.

CURRENT FINDINGS:
Tỷ lệ timeout tăng cùng thời điểm queue age tăng. Chưa xác nhận nguyên nhân cuối cùng.

ACTIONS:
- Incident Commander đã được chỉ định.
- Consumer team đang kiểm tra concurrency và downstream database.
- Đang giữ nguyên deployment hiện tại để thu thập evidence.

NEXT UPDATE:
2026-11-20 08:35 UTC
~~~

Mẫu cập nhật khách hàng:

~~~text
Chúng tôi đang điều tra tình trạng chậm xử lý một số yêu cầu tạo đơn hàng.
Một phần yêu cầu có thể cần thử lại. Dữ liệu đơn hàng đã được ghi nhận sẽ tiếp tục được xử lý
sau khi dịch vụ phục hồi.

Chúng tôi sẽ cập nhật khi có thông tin xác nhận về phạm vi ảnh hưởng và thời điểm khôi phục.
~~~

Chỉ người được giao trách nhiệm truyền thông mới phát hành thông báo chính thức. Với security incident, phối hợp security, legal và privacy team trước khi công bố chi tiết có thể ảnh hưởng điều tra.

## 17. Khi nào đóng incident?

Incident không nên được đóng chỉ vì một alarm chuyển về OK.

Điều kiện close thường gồm:

- Customer impact đã dừng.
- SLO và business KPI trở lại mức chấp nhận được trong khoảng quan sát đã định.
- Queue/backlog đã xử lý hoặc có kế hoạch drain rõ ràng.
- Không còn data integrity issue chưa được đánh giá.
- Workaround và residual risk được ghi lại.
- Owner cho các vấn đề còn lại đã được chỉ định.
- Stakeholder đã nhận cập nhật cuối.
- Evidence và timeline đã được lưu.
- Postmortem có lịch và facilitator nếu incident thuộc diện review.

Mitigation và resolution là hai mốc khác nhau. Nếu rollback giúp khách hàng giao dịch lại nhưng nguyên nhân deployment vẫn chưa được hiểu, incident có thể được đóng sau khi hệ thống ổn định trong khi problem ticket tiếp tục mở.

## 18. Postmortem là gì và khi nào cần thực hiện?

Postmortem (còn gọi là post-incident analysis hoặc Correction of Error - COE trong một số quy trình) là review có cấu trúc sau sự cố. Mục tiêu là hiểu hệ thống và quy trình đã cho phép sự cố xảy ra như thế nào, rồi tạo thay đổi giảm khả năng tái diễn hoặc giảm tác động nếu sự cố xảy ra lại.

Nên review:

- Mọi incident có customer impact đáng kể.
- Sự cố gây mất dữ liệu hoặc ảnh hưởng security/compliance.
- Near miss có thể dẫn đến tác động lớn.
- Incident tái diễn hoặc cùng pattern xuất hiện nhiều lần.
- Incident có thời gian phát hiện, escalation hoặc phục hồi vượt mục tiêu.
- Fault injection/game day cho thấy runbook hoặc control không hoạt động.

Không cần tổ chức postmortem đầy đủ cho mọi cảnh báo nhỏ. Tuy nhiên, sự cố nhỏ lặp lại có thể chỉ ra một weakness lớn đang tích tụ.

## 19. Blameless postmortem

Blameless không có nghĩa là bỏ qua trách nhiệm. Nó có nghĩa là review hành vi và quyết định trong bối cảnh thông tin, công cụ, áp lực và quy trình mà người thực hiện có tại thời điểm đó.

Tránh cách viết:

- "Kỹ sư đã quên kiểm tra."
- "Operator xử lý sai."
- "Developer bất cẩn."

Thay bằng câu hỏi về hệ thống:

- Tại sao thao tác có thể được thực hiện mà không có pre-check?
- Tại sao review không phát hiện thay đổi?
- Tại sao alarm không cảnh báo trước khi customer impact xảy ra?
- Tại sao rollback không được kiểm thử?
- Tại sao người trực không tìm thấy runbook phù hợp?
- Tại sao quyền hạn hoặc escalation không rõ ràng?

Nếu con người mắc lỗi, cần tìm điều kiện khiến lỗi dễ xảy ra và thiếu cơ chế ngăn chặn. Kết quả tốt là thêm validation, automation, guardrail, training hoặc cải tiến thiết kế.

## 20. Thu thập timeline và đo thời gian phản ứng

Timeline cần dùng timestamp UTC thống nhất và phân biệt các mốc.

| Mốc | Ý nghĩa | Ví dụ |
|---|---|---|
| T0 - Incident start | Tác động khách hàng bắt đầu | 08:15 |
| T1 - Detection | Alarm hoặc người dùng phát hiện | 08:19 |
| T2 - Engagement | Đúng responder tham gia | 08:24 |
| T3 - Mitigation | Tác động dừng hoặc giảm | 08:37 |
| T4 - Resolution | Hệ thống ổn định và xử lý tồn đọng | 09:05 |

Từ timeline có thể tính:

- **Time to detect (TTD):** T1 - T0.
- **Time to engage:** T2 - T1.
- **Time to mitigate:** T3 - T0 hoặc T3 - T2; phải ghi rõ cách tính khi báo cáo.
- **Time to resolve:** T4 - T0.
- **Customer impact duration:** khoảng thời gian khách hàng thực sự bị ảnh hưởng.

Không dùng một chỉ số MTTR mà không định nghĩa repair, recovery hay resolution. Các đội khác nhau có thể tính MTTR theo cách khác nhau; hãy công bố định nghĩa trong dashboard.

Timeline có thể được dựng từ CloudWatch alarm history, CloudTrail, deployment events, application logs, trace, ticket và incident chat. Automation có thể thu thập dữ liệu; người review phải xác nhận timestamp và diễn giải.

## 21. Template postmortem/COE

Mẫu dưới đây có thể dùng làm tài liệu review cho một incident:

~~~text
# POSTMORTEM / CORRECTION OF ERROR

Incident ID:
Service / Environment:
Severity:
Incident start:
Detection:
Mitigation:
Resolution:
Facilitator:
Review date:
Participants:

## 1. Executive summary
Điều gì đã xảy ra trong 3-5 câu?

## 2. Customer and business impact
- Người dùng / tenant / Region bị ảnh hưởng:
- Tỷ lệ request lỗi hoặc giao dịch thất bại:
- Dữ liệu mất, trùng hoặc sai lệch:
- Tác động doanh thu, SLA hoặc compliance:
- Workaround:

## 3. Timeline (UTC)
| Time | Event | Evidence | Decision / Action | Owner |

## 4. Detection and response
- Alarm nào phát hiện?
- Có alert bị thiếu hoặc noisy không?
- Ai được gọi và khi nào?
- Runbook/playbook nào được dùng?
- Mitigation nào hiệu quả hoặc không hiệu quả?

## 5. What happened
Mô tả technical sequence dựa trên evidence.

## 6. Contributing factors
- Trigger:
- Latent conditions:
- Detection gaps:
- Design / capacity gaps:
- Process / communication gaps:
- Dependency factors:

## 7. Root cause analysis
Five Whys / Ishikawa / causal graph.
Phân biệt evidence, hypothesis và conclusion.

## 8. What went well
Những control hoặc hành động giúp giảm impact.

## 9. What did not go well
Những khoảng trống trong detection, response, recovery hoặc communication.

## 10. Corrective and preventive actions
| Action | Type | Priority | Owner | Due date | Verification |

## 11. Cross-workload learning
Workload/team nào có cùng pattern cần kiểm tra?

## 12. Follow-up
Ngày review action, facilitator và cách xác nhận hiệu quả.
~~~

Postmortem phải dễ tìm, có access control phù hợp và liên kết với incident record, code change, alarm, dashboard và action tickets.

## 22. Tìm contributing factors thay vì dừng ở một nguyên nhân

Sự cố thường xuất hiện khi nhiều điều kiện kết hợp.

Ví dụ: một deployment làm tăng database query latency. Connection pool của consumer tăng, Lambda concurrency đạt giới hạn, SQS backlog tăng và request tạo đơn hàng timeout. Deployment là trigger, nhưng không nhất thiết là toàn bộ nguyên nhân.

Phân loại contributing factors:

- **Trigger:** sự kiện trực tiếp bắt đầu tác động.
- **Latent condition:** điểm yếu tồn tại trước đó, chưa gây sự cố.
- **Detection gap:** monitoring không phát hiện đủ sớm.
- **Mitigation gap:** không có cách giảm impact nhanh.
- **Recovery gap:** rollback hoặc failover chưa được kiểm thử.
- **Process gap:** owner, approval hoặc escalation chưa rõ.
- **External dependency:** service bên ngoài, quota hoặc provider behavior.

Dùng causal graph hoặc Ishikawa để xem nhiều nhánh nguyên nhân. Một root cause statement đơn giản có thể che mất điều kiện hệ thống đã làm sự cố lan rộng.

## 23. Five Whys và Ishikawa

Five Whys là kỹ thuật hỏi "tại sao" lặp lại để tìm điều kiện sâu hơn. Không bắt buộc đúng năm câu hỏi; dừng khi các nguyên nhân có thể kiểm chứng và có hành động cụ thể.

Ví dụ:

1. Vì sao đơn hàng xử lý chậm? Vì consumer xử lý message chậm.
2. Vì sao consumer chậm? Vì Lambda bị throttling và database connection chạm giới hạn.
3. Vì sao concurrency tăng nhanh? Vì deployment thay đổi thời gian xử lý mỗi message.
4. Vì sao rollout gây tải vượt capacity? Vì load test không mô phỏng burst và database connection.
5. Vì sao thiếu kiểm tra đó? Vì release checklist chỉ đo API response trung bình, không đo queue age và downstream connection.

Kết luận không nên là "đội triển khai thiếu cẩn thận". Những contributing factors có thể là: thiếu queue-age alarm, load test không có burst, concurrency không được giới hạn theo database capacity và rollback chưa được diễn tập.

Ishikawa có thể nhóm nguyên nhân theo:

- People: kỹ năng, training, phân vai.
- Process: review, change management, escalation.
- Technology: code, architecture, dependency.
- Data: payload, schema, volume, quality.
- Environment: Region, AZ, network, quota.
- Measurement: metric, log, alarm và retention.

## 24. Corrective action phải cụ thể và có thể xác minh

Một action item tốt trả lời:

- Thay đổi gì?
- Vấn đề nào được xử lý?
- Ai sở hữu?
- Khi nào hoàn thành?
- Cách xác minh?
- Rủi ro hoặc dependency nào cần theo dõi?

Phân loại action:

| Loại | Mục tiêu | Ví dụ |
|---|---|---|
| Prevention | Ngăn trigger hoặc điều kiện gây sự cố | Thêm connection limit và validation |
| Detection | Phát hiện sớm hơn | Alarm theo queue age và error budget |
| Mitigation | Giảm blast radius | Giới hạn concurrency, circuit breaker |
| Recovery | Phục hồi nhanh và an toàn | Kiểm thử rollback và restore |
| Process | Cải thiện con người/quy trình | Thêm owner, escalation và review |
| Learning | Lan truyền kiến thức | Cập nhật runbook, training và readiness review |

Action yếu: "Cải thiện monitoring."

Action tốt: "Platform team thêm alarm ApproximateAgeOfOldestMessage vượt 120 giây trong 3 datapoints, gửi tới on-call channel và liên kết playbook SQS-Backlog; hoàn thành trước ngày 15/12; xác minh bằng game day."

### 24.1. Action tracker

| ID | Hành động | Loại | Priority | Owner | Due | Verification | Status |
|---|---|---|---|---|---|---|---|
| ACT-01 | Thêm queue-age alarm và escalation | Detection | P1 | Platform | 15/12 | Game day tạo backlog | Open |
| ACT-02 | Giới hạn concurrency theo DB capacity | Prevention | P1 | App team | 18/12 | Load test burst | Open |
| ACT-03 | Thêm dashboard connection pool | Detection | P2 | DBA | 20/12 | Metric hiển thị đủ | Open |
| ACT-04 | Diễn tập rollback consumer release | Recovery | P2 | Release team | 22/12 | Rollback trong RTO | Open |

Không đóng action chỉ vì code đã merge. Cần xác minh metric, test, runbook hoặc hành vi hệ thống đã đạt mục tiêu.

## 25. Ưu tiên corrective actions

Không phải mọi action có mức độ khẩn cấp giống nhau. Có thể ưu tiên theo:

- Mức customer impact nếu lỗi tái diễn.
- Xác suất tái diễn.
- Phạm vi workload bị ảnh hưởng.
- Khả năng giảm blast radius.
- Độ khó và thời gian triển khai.
- Rủi ro tạo regression mới.

Ví dụ:

| Priority | Tiêu chí mẫu | Kỳ vọng |
|---|---|---|
| P0 | Lỗ hổng đang gây mất dữ liệu/security hoặc outage diện rộng | Xử lý ngay theo incident/change process |
| P1 | Nguy cơ tái diễn với impact cao | Đưa vào sprint gần nhất và theo dõi sát |
| P2 | Cải thiện resilience/detection đáng kể | Lên kế hoạch có owner và deadline |
| P3 | Tối ưu nhỏ hoặc tài liệu | Đưa vào backlog và review định kỳ |

Đây là quy ước mẫu, tổ chức cần định nghĩa theo risk appetite. Không dùng priority thấp để bỏ qua một action có rủi ro compliance hoặc security.

## 26. Đóng vòng lặp ngăn tái diễn

Một postmortem chỉ có giá trị khi action được thực hiện và kiểm chứng.

Vòng lặp cải tiến:

~~~mermaid
flowchart LR
    A[Incident / Near miss] --> B[Evidence and timeline]
    B --> C[Postmortem / RCA]
    C --> D[Contributing factors]
    D --> E[Corrective action backlog]
    E --> F[Implement change]
    F --> G[Test and verify]
    G --> H[Update runbook / playbook / ORR]
    H --> I[Measure recurrence and SLO]
    I --> A
~~~

Các cơ chế duy trì:

- Gắn action với issue/ticket có owner và due date.
- Review action P0/P1 trong operational review.
- Quá hạn phải có escalation và lý do.
- Cập nhật alarm, dashboard, runbook và playbook.
- Tìm workload khác có cùng pattern.
- Đưa câu hỏi mới vào Operational Readiness Review (ORR).
- Kiểm thử cải tiến qua game day hoặc controlled failure test.
- Đo recurrence rate và response time sau khi action hoàn tất.

Một action được đánh dấu Done nhưng không có evidence kiểm chứng thì chưa chứng minh đã giảm rủi ro.

## 27. Đo hiệu quả vận hành

Một số metric hữu ích:

| Metric | Cách hiểu | Dùng để |
|---|---|---|
| MTTD / TTD | Thời gian từ incident start tới detection | Đánh giá monitoring |
| Time to engage | Từ detection tới khi đúng responder tham gia | Đánh giá paging/escalation |
| Time to mitigate | Từ incident start hoặc engagement tới khi customer impact giảm | Đánh giá containment |
| Time to resolve | Từ incident start tới khi hệ thống ổn định hoàn toàn | Đánh giá recovery |
| Incident recurrence rate | Tỷ lệ incident lặp lại cùng pattern | Đánh giá preventive action |
| Alert precision | Tỷ lệ alert thực sự cần hành động | Đánh giá noise |
| Runbook success rate | Tỷ lệ execution hoàn tất đúng kết quả | Đánh giá tài liệu/automation |
| Action closure on time | Tỷ lệ action hoàn tất đúng hạn | Đánh giá follow-through |
| SLO / error budget | Mức độ đáp ứng reliability target | Liên kết vận hành với trải nghiệm khách hàng |

Không tối ưu metric một cách máy móc. Ví dụ giảm time to resolve bằng cách đóng incident sớm có thể che giấu backlog hoặc data integrity issue. Kết hợp metric định lượng với customer impact và review định tính.

## 28. Kiểm thử runbook trước khi xuất bản

Runbook cần được kiểm thử như code:

1. Chạy trên môi trường test hoặc resource không production.
2. Dùng input hợp lệ, sai định dạng và resource không tồn tại.
3. Kiểm tra IAM permission theo least privilege.
4. Xác minh step output và trạng thái cuối.
5. Thử nhánh failure và timeout.
6. Kiểm tra rollback hoặc recovery path.
7. Nhờ một kỹ sư không viết tài liệu thực hiện theo hướng dẫn.
8. Kiểm tra CloudWatch Logs, execution history và audit trail.
9. Đánh giá thời gian thực hiện so với mục tiêu.
10. Cập nhật version và ngày validated.

Với runbook mutating, cần kiểm tra giới hạn target, concurrency, approval và điều kiện dừng. Một runbook restart instance có thể hoạt động đúng về mặt API nhưng gây outage nếu target selector chọn toàn bộ fleet.

## 29. Tabletop exercise và game day

Tabletop exercise là buổi diễn tập theo kịch bản, không nhất thiết gây lỗi thật. Game day chủ động tạo tình huống trong môi trường được kiểm soát để xác minh hành vi hệ thống và người phản ứng.

Ví dụ tabletop:

- CloudWatch báo database connection saturation.
- IC khai báo SEV-2.
- DBA kiểm tra Database Insights.
- App team kiểm tra connection pool.
- Nhóm quyết định giảm consumer concurrency.
- Communications Lead chuẩn bị status update.
- Scribe ghi lại timeline và decision.

Ví dụ game day trong pre-production:

- Tăng message arrival rate có kiểm soát.
- Quan sát queue age và consumer concurrency.
- Xác minh alarm kích hoạt.
- Chạy playbook và runbook diagnostics.
- Kiểm tra escalation.
- Dừng thử nghiệm nếu stop condition kích hoạt.
- Xác minh backlog drain và SLO phục hồi.

Không bắt đầu bằng hành động phá hủy trên production. Mọi experiment cần hypothesis, scope, owner, stop condition, rollback và lịch được phê duyệt.

## 30. Tự động hóa postmortem evidence collection

Có thể tự động thu thập dữ liệu để facilitator tập trung vào phân tích:

- CloudWatch alarm history trong incident window.
- Metric datapoints trước/trong/sau sự cố.
- CloudTrail management events và deployment/configuration changes.
- CloudFormation stack events.
- Lambda/ECS/RDS/SQS logs.
- X-Ray trace hoặc OpenTelemetry trace.
- Systems Manager Automation execution history.
- Incident ticket/chat timestamps.
- Version và commit SHA của release gần nhất.

Tự động hóa không tự quyết định root cause. Một summary hoặc AI suggestion chỉ là giả thuyết cần kiểm tra với evidence và con người. Người review cần hỏi thêm những điều kiện nào đã kết hợp để gây impact và vì sao control hiện có không ngăn được.

Giữ retention đủ dài để có thể điều tra pattern lịch sử. Đảm bảo evidence có access control, redaction và retention theo security/privacy policy.

## 31. Security incident cần playbook riêng

Sự cố bảo mật có thể yêu cầu cách xử lý khác incident availability thông thường.

Các bước cấp cao:

1. Xác nhận finding và xác định resource/account/Region.
2. Kích hoạt security incident process và chỉ định incident lead.
3. Bảo toàn CloudTrail, VPC Flow Logs, service logs, snapshot và evidence liên quan.
4. Xác định principal, credential, resource và dữ liệu có thể bị ảnh hưởng.
5. Contain theo kế hoạch đã được phê duyệt: revoke/disable credential, isolate instance, chặn network hoặc hạn chế access.
6. Phối hợp security, legal, privacy và compliance owner.
7. Eradicate persistence hoặc cấu hình không an toàn.
8. Recover từ known-good state và rotate secret/key khi phù hợp.
9. Verify monitoring và access controls.
10. Postmortem và theo dõi corrective action.

Không xóa log, instance hoặc snapshot trước khi đánh giá nhu cầu forensic. Không tự động rotate hoặc revoke credential diện rộng nếu chưa xác định dependency và blast radius, trừ khi security incident plan quy định rõ hành động khẩn cấp.

## 32. Case study: SQS backlog làm chậm xử lý đơn hàng

Một nền tảng thương mại điện tử dùng API Gateway, Lambda, SQS và DynamoDB. Sau một deployment, queue orders-processing tăng backlog và khách hàng thấy trạng thái đơn hàng cập nhật chậm.

**Phát hiện**

- CloudWatch alarm theo ApproximateAgeOfOldestMessage chuyển ALARM.
- Dashboard cho thấy Lambda Throttles tăng và ConcurrentExecutions đạt giới hạn.
- DynamoDB consumed capacity tăng cùng thời điểm.
- API vẫn nhận order nhưng trạng thái fulfillment bị trễ.

**Phản ứng**

- IC khai báo SEV-2 và giao technical lead cho app team.
- Scribe ghi timeline và deployment version.
- Playbook kiểm tra queue, DLQ, Lambda concurrency, DynamoDB throttling và release.
- Team xác nhận consumer xử lý chậm sau thay đổi query; concurrency tăng làm database chịu áp lực.
- Mitigation: rollback phiên bản consumer và giữ concurrency ở mức an toàn đã xác nhận.
- Team theo dõi queue age giảm và backlog drain.
- Sau khi SLO phục hồi, IC cập nhật stakeholder và đóng incident.

**Postmortem**

- Trigger: deployment làm thời gian xử lý mỗi message tăng.
- Contributing factor 1: load test không có burst tương tự campaign.
- Contributing factor 2: consumer concurrency không gắn với database capacity.
- Contributing factor 3: alarm chỉ theo queue depth, chưa có queue age.
- Contributing factor 4: runbook không chỉ rõ dependency check trước khi tăng concurrency.

**Corrective actions**

1. Thêm queue-age alarm và liên kết playbook.
2. Bổ sung load test có burst và database connection pressure.
3. Giới hạn concurrency theo capacity của DynamoDB.
4. Thêm dashboard cho per-message processing time và throttling.
5. Cập nhật runbook scale consumer, yêu cầu kiểm tra database trước khi tăng capacity.
6. Diễn tập rollback consumer release trong pre-production.

Mỗi action có owner, due date, verification evidence và trạng thái. Khi hoàn tất, game day xác minh queue age không vượt SLO dưới workload đại diện.

## 33. Checklist production readiness cho runbook và postmortem

### Incident process

- [ ] Severity và customer impact criteria được định nghĩa.
- [ ] Có Incident Commander và escalation path.
- [ ] Có kênh nội bộ và customer communication plan.
- [ ] Có người ghi timeline và decision.
- [ ] Có điều kiện mitigation, recovery và close.
- [ ] Có security incident path và break-glass access.

### Runbook / playbook

- [ ] Có owner, version và ngày kiểm thử.
- [ ] Desired outcome và trigger rõ ràng.
- [ ] Có prerequisites, IAM permissions và tools.
- [ ] Các bước có expected result và failure path.
- [ ] Có decision points và escalation.
- [ ] Mutating actions có approval/guardrail.
- [ ] Có verification và rollback.
- [ ] Người không phải tác giả đã thử chạy.

### Postmortem / corrective actions

- [ ] Có timeline UTC và customer impact.
- [ ] Có evidence từ CloudWatch, CloudTrail và service logs.
- [ ] Có contributing factors thay vì chỉ một trigger.
- [ ] Review theo hướng blameless.
- [ ] Action có owner, due date, priority và verification.
- [ ] Action được theo dõi tới khi hoàn tất.
- [ ] Bài học được chia sẻ với workload có cùng pattern.
- [ ] Runbook, alarm, ORR và test được cập nhật.

### Automation and learning

- [ ] CloudWatch/EventBridge trigger đúng response.
- [ ] Systems Manager Automation role dùng least privilege.
- [ ] Có kiểm soát concurrency, approval và stop condition.
- [ ] Automation output được ghi log và audit.
- [ ] CloudWatch Investigations findings được con người xác minh.
- [ ] OpsCenter hoặc incident tracking system có owner và status.
- [ ] Có tabletop/game day theo lịch.
- [ ] Đo recurrence rate, detection time và action closure.

## 34. Bài tập tự kiểm tra

### Câu 1

Runbook và playbook khác nhau thế nào?

**Đáp án:** Runbook thực hiện một quy trình có kết quả dự đoán được; playbook hướng dẫn điều tra một tình huống chưa biết nguyên nhân, với các decision point và escalation.

### Câu 2

Event, alert, incident và problem khác nhau thế nào?

**Đáp án:** Event là sự kiện; alert là thông báo cần chú ý; incident là tác động cần phối hợp xử lý; problem là nguyên nhân hoặc weakness nền cần khắc phục.

### Câu 3

Vì sao severity không nên chỉ dựa vào CPU hoặc memory?

**Đáp án:** Severity phản ánh customer/business impact, phạm vi, dữ liệu và khả năng phục hồi. Metric tài nguyên chỉ là tín hiệu kỹ thuật.

### Câu 4

Incident Commander chịu trách nhiệm gì?

**Đáp án:** Điều phối, ưu tiên, giao owner, escalation, quyết định và giữ nhịp truyền thông.

### Câu 5

Runbook cần có những thành phần nào?

**Đáp án:** Desired outcome, trigger, prerequisites, permissions, tools, steps, expected results, error path, escalation, verification và rollback.

### Câu 6

Vì sao runbook mutating cần approval và guardrail?

**Đáp án:** Vì thao tác có thể thay đổi hoặc làm gián đoạn resource; cần giới hạn target, blast radius và quyền thực thi.

### Câu 7

Postmortem blameless có nghĩa là không ai chịu trách nhiệm?

**Đáp án:** Không. Nó tập trung vào hệ thống và điều kiện cho phép sự cố, đồng thời vẫn giao owner cụ thể cho corrective actions.

### Câu 8

Timeline postmortem cần những mốc nào?

**Đáp án:** Incident start, detection, engagement, mitigation và resolution; các mốc cần timestamp UTC và evidence.

### Câu 9

Five Whys có bắt buộc đúng năm câu hỏi không?

**Đáp án:** Không. Số lần hỏi tùy vấn đề; dừng khi các nguyên nhân có thể kiểm chứng và có hành động.

### Câu 10

Vì sao không nên dừng postmortem ở deployment làm trigger?

**Đáp án:** Vì deployment có thể chỉ là trigger; cần tìm latent conditions như thiếu test, alarm, capacity guardrail hoặc rollback.

### Câu 11

Một corrective action tốt cần có gì?

**Đáp án:** Thay đổi cụ thể, owner, deadline, priority, dependency và cách xác minh hiệu quả.

### Câu 12

Metric nào giúp đo tốc độ phát hiện incident?

**Đáp án:** Time to detect (TTD/MTTD), tính từ lúc customer impact bắt đầu tới lúc được phát hiện.

### Câu 13

Mitigation và resolution khác nhau thế nào?

**Đáp án:** Mitigation dừng hoặc giảm tác động; resolution xử lý đầy đủ và xác nhận hệ thống ổn định.

### Câu 14

CloudWatch và EventBridge có thể kích hoạt Systems Manager Automation không?

**Đáp án:** Có. CloudWatch alarm tạo event/state transition và EventBridge có thể route tới Automation hoặc các target khác theo cấu hình.

### Câu 15

OpsCenter có thay thế hoàn toàn Incident Manager không?

**Đáp án:** Không. OpsCenter quản lý OpsItems và hỗ trợ Automation; nó không cung cấp paging hoặc on-call rotation.

### Câu 16

AWS Systems Manager Incident Manager có mở cho khách hàng mới từ tháng 11/2025 không?

**Đáp án:** Không. Dịch vụ ngừng nhận khách hàng mới từ ngày 7/11/2025; account đã bật trước đó tiếp tục sử dụng được.

### Câu 17

CloudWatch Investigations có thể tự động quyết định root cause thay con người không?

**Đáp án:** Không. AI-generated suggestions là đầu vào hỗ trợ; người điều tra phải xác minh evidence và chịu trách nhiệm quyết định.

### Câu 18

Vì sao cần test runbook với người không phải tác giả?

**Đáp án:** Để phát hiện bước mơ hồ, thiếu quyền, thiếu tool hoặc phụ thuộc vào kiến thức cá nhân.

### Câu 19

Khi nào nên thực hiện game day?

**Đáp án:** Khi có môi trường, hypothesis, owner, stop condition và rollback được chuẩn bị; thường thực hiện ở pre-production hoặc phạm vi được phê duyệt.

### Câu 20

Khi nào một corrective action được xem là hoàn tất?

**Đáp án:** Khi thay đổi đã triển khai và verification evidence chứng minh nó đạt mục tiêu giảm rủi ro hoặc cải thiện detection/recovery.

## 35. Tài liệu tham khảo chính thức

- [OPS05-BP01: Develop and test runbooks to perform procedures](https://docs.aws.amazon.com/wellarchitected/latest/framework/ops05-bp01.html)
- [REL12-BP01: Use playbooks to investigate failures](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel12-bp01.html)
- [OPS07-BP01: Perform post-incident analysis](https://docs.aws.amazon.com/wellarchitected/latest/framework/ops07-bp01.html)
- [REL12-BP02: Perform post-incident analysis](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel12-bp02.html)
- [OPS10: Manage workload and operations events](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/responding-to-events.html)
- [AWS Well-Architected concepts: Five Whys, COE, RCA, playbook and runbook](https://docs.aws.amazon.com/wellarchitected/latest/framework/concepts.html)
- [AWS Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-automation.html)
- [Systems Manager Automation actions reference](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-actions.html)
- [aws:executeAwsApi action](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-executeAwsApi.html)
- [AWS Systems Manager OpsCenter](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter.html)
- [CloudWatch alarm actions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarm-actions.html)
- [Investigate operational issues with CloudWatch Investigations](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Investigations-Investigate.html)
- [Recommended best practices to enhance CloudWatch investigations](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Investigations-RecommendedServices.html)
- [AWS Systems Manager Incident Manager availability change](https://docs.aws.amazon.com/incident-manager/latest/userguide/incident-manager-availability-change.html)
- [Migrating to AWS Systems Manager OpsCenter](https://docs.aws.amazon.com/incident-manager/latest/userguide/migration-opscenter.html)
- [AWS FIS and game day planning](https://docs.aws.amazon.com/fis/latest/userguide/getting-started-planning.html)

Runbook actions, automation limits, service availability and incident tooling change over time. Pin document versions, validate IAM permissions and test every automated action in a controlled environment before connecting it to production alerts.

