# Architecture review và ghi nhận quyết định thiết kế

## Mục tiêu học tập

Một kiến trúc AWS có thể chạy được nhưng vẫn khó vận hành, tốn kém, thiếu khả năng phục hồi hoặc không đáp ứng yêu cầu bảo mật. Architecture review là hoạt động đánh giá có cấu trúc để kiểm tra thiết kế trước và sau khi triển khai, phát hiện rủi ro, làm rõ giả định và thống nhất các hành động cần thực hiện. Architecture Decision Record (ADR) lưu lại lý do một lựa chọn được đưa ra để đội ngũ có thể hiểu, kiểm tra và xem xét lại quyết định đó khi bối cảnh thay đổi.

Trong module CLOUD_PROVIDERS_AWS, người học cần biết cách chọn và kết hợp dịch vụ AWS trong bối cảnh Region/AZ, IAM, VPC, compute, storage, database, integration và serverless. Bài học này kết nối các kiến thức đó thành một quy trình review có thể áp dụng cho workload thực tế.

Sau bài học, người học có thể:

- Chuẩn bị hồ sơ kiến trúc với business goals, scope, assumptions, constraints và non-functional requirements.
- Tổ chức architecture review dựa trên AWS Well-Architected Framework và các yêu cầu riêng của tổ chức.
- Đánh giá độ tin cậy, bảo mật, hiệu năng, chi phí, vận hành và tính bền vững của một workload.
- Phân tích luồng dữ liệu, trust boundary, dependency, failure mode và blast radius.
- So sánh phương án thiết kế bằng tiêu chí và bằng chứng có thể kiểm tra.
- Ghi lại quyết định, lựa chọn thay thế, hệ quả và điều kiện xem xét lại bằng ADR.
- Theo dõi finding, action item, exception và thay đổi kiến trúc sau review.
- Biết khi nào cần review lại và cách dùng AWS Well-Architected Tool trong quy trình cải tiến liên tục.

## 1. Architecture review giải quyết vấn đề gì?

Architecture review là một cuộc đánh giá thiết kế có mục tiêu, phạm vi, người tham gia, tiêu chí và kết quả được ghi nhận. Review có thể diễn ra trước khi triển khai, trước khi đưa workload vào production, sau một thay đổi lớn hoặc theo chu kỳ vận hành.

Một review tốt trả lời được những câu hỏi:

- Workload đang giải quyết nhu cầu kinh doanh nào?
- Các yêu cầu về availability, latency, throughput, data retention, privacy và recovery có được lượng hóa không?
- Những thành phần nào có thể lỗi, và khi lỗi xảy ra thì người dùng hoặc dữ liệu bị ảnh hưởng ra sao?
- Identity nào được phép gọi thành phần nào? Dữ liệu đi qua trust boundary nào?
- Kiến trúc có đáp ứng mục tiêu RTO/RPO và quy trình restore đã kiểm thử không?
- Chi phí dự kiến có phù hợp với ngân sách và mô hình tăng trưởng không?
- Đội vận hành có đủ telemetry, runbook, quyền truy cập và quy trình ứng phó không?
- Lựa chọn dịch vụ có dựa trên constraint, workload pattern và trade-off được ghi nhận không?

Review không phải buổi trình bày sơ đồ để tìm lỗi chính tả. Nó là cách kiểm tra giả định, rủi ro và khả năng vận hành của hệ thống bằng dữ liệu, kịch bản và bằng chứng.

### 1.1. Review không thay thế trách nhiệm thiết kế

Nhóm thiết kế vẫn sở hữu kiến trúc và quyết định kỹ thuật. Reviewer đặt câu hỏi, thách thức giả định, phát hiện khoảng trống và đề xuất lựa chọn. Người chịu trách nhiệm workload phải quyết định cách xử lý finding, chấp nhận rủi ro trong phạm vi quyền hạn hoặc chuyển cấp phê duyệt.

Một review không thể bảo đảm hệ thống không có lỗi. Nó giảm khả năng bỏ sót vấn đề bằng cách dùng góc nhìn độc lập, tiêu chí nhất quán và bằng chứng rõ ràng.

### 1.2. Các loại review thường gặp

| Loại review | Thời điểm | Trọng tâm |
|---|---|---|
| Concept review | Khi mới hình thành ý tưởng | Mục tiêu, phạm vi, phương án tổng thể, tính khả thi |
| Architecture design review | Trước khi chốt thiết kế | Component, data flow, integration, failure mode và trade-off |
| Security review | Trước khi xử lý dữ liệu hoặc mở kết nối | Threat model, identity, trust boundary, encryption, logging |
| Production readiness review | Trước go-live | Monitoring, capacity, runbook, backup, recovery, access |
| Change review | Trước thay đổi có ảnh hưởng lớn | Blast radius, compatibility, rollback, migration |
| Periodic review | Theo chu kỳ hoặc sau incident | Drift, chi phí, capacity, reliability và technical debt |
| Post-incident architecture review | Sau sự cố nghiêm trọng | Nguyên nhân hệ thống, điểm yếu thiết kế và biện pháp phòng ngừa |

Không phải mọi thay đổi đều cần một hội đồng lớn. Mức độ review phải tương xứng với mức độ rủi ro, độ phức tạp và tác động của workload.

## 2. Bắt đầu từ workload và yêu cầu

Đừng bắt đầu review bằng câu hỏi “nên dùng dịch vụ AWS nào?”. Trước hết phải hiểu workload cần làm gì, ai sử dụng, dữ liệu nào được xử lý và điều kiện thành công là gì.

### 2.1. Xác định workload

Một workload là tập hợp ứng dụng, dữ liệu, hạ tầng, quy trình vận hành và dependency cùng phục vụ một mục tiêu kinh doanh. Có thể triển khai workload trên một account hoặc nhiều account, một Region hoặc nhiều Region, nhưng phạm vi review phải được xác định rõ.

Hồ sơ workload tối thiểu nên có:

- Tên workload, owner kỹ thuật, owner nghiệp vụ và kênh liên hệ vận hành.
- Mục tiêu kinh doanh, nhóm người dùng và hành trình quan trọng.
- Dữ liệu được tạo, đọc, sửa, truyền và lưu trữ.
- Môi trường dev, test, staging, production và account/Region liên quan.
- Các hệ thống nội bộ, đối tác và dịch vụ bên ngoài phụ thuộc.
- Mức độ quan trọng, giờ hoạt động, lịch cao điểm và thời gian bảo trì.
- Trạng thái hiện tại: ý tưởng, đang xây dựng, production hay đang chuyển đổi.

### 2.2. Functional requirements và non-functional requirements

Functional requirements mô tả hành vi sản phẩm, ví dụ khách hàng tạo đơn, tra cứu giao dịch hoặc nhân viên phê duyệt yêu cầu. Non-functional requirements (NFR) mô tả chất lượng và giới hạn mà hệ thống phải đáp ứng.

| NFR | Câu hỏi cần trả lời | Ví dụ cách lượng hóa |
|---|---|---|
| Availability | Dịch vụ cần sẵn sàng bao nhiêu? | 99.9% theo tháng cho API giao dịch |
| Latency | Request phải hoàn thành trong bao lâu? | p95 dưới 300 ms cho endpoint đọc |
| Throughput | Tải bình thường và đỉnh là bao nhiêu? | 2.000 request/giây, peak 5.000 |
| Scalability | Tải tăng thì hệ thống mở rộng thế nào? | Tăng gấp 3 trong 10 phút |
| Durability | Mức độ mất dữ liệu chấp nhận được? | Không mất giao dịch đã xác nhận |
| RTO | Bao lâu phải phục hồi dịch vụ? | 60 phút |
| RPO | Dữ liệu cũ tối đa bao lâu? | 5 phút |
| Security | Identity và dữ liệu cần bảo vệ thế nào? | MFA cho quản trị, encryption at rest/in transit |
| Privacy | Dữ liệu cá nhân được xử lý ra sao? | Phân loại, giới hạn truy cập và retention |
| Operability | Đội vận hành cần quan sát và can thiệp gì? | Alert có owner, runbook và audit trail |
| Cost | Ngân sách và đơn vị chi phí là gì? | Chi phí trên 1.000 giao dịch |
| Sustainability | Có thể giảm tài nguyên và lãng phí ở đâu? | Scale theo tải, giảm idle capacity |

Con số trong bảng là ví dụ minh họa. Mỗi workload cần mục tiêu được owner nghiệp vụ và kỹ thuật thống nhất. Tránh các yêu cầu mơ hồ như “hệ thống phải nhanh”, “phải highly available” hoặc “chi phí thấp”.

### 2.3. Phân biệt target, constraint và assumption

- **Target:** kết quả mong muốn, có thể đo được.
- **Constraint:** điều kiện bắt buộc giới hạn phương án, ví dụ Region được phép, công nghệ đã chuẩn hóa, ngân sách hoặc thời hạn.
- **Assumption:** điều đang tạm coi là đúng để thiết kế tiếp tục, nhưng cần xác minh.

Ví dụ: “p95 dưới 300 ms” là target; “dữ liệu phải lưu tại Region được tổ chức phê duyệt” là constraint; “đối tác hỗ trợ TLS 1.2” là assumption. Nếu assumption sai, kiến trúc có thể cần thay đổi.

## 3. Dùng AWS Well-Architected Framework làm khung review

AWS Well-Architected Framework cung cấp cách đặt câu hỏi để đánh giá workload theo sáu trụ cột:

1. Operational Excellence – Vận hành xuất sắc.
2. Security – Bảo mật.
3. Reliability – Độ tin cậy.
4. Performance Efficiency – Hiệu quả hiệu năng.
5. Cost Optimization – Tối ưu chi phí.
6. Sustainability – Tính bền vững.

Sáu trụ cột bổ sung cho nhau. Một quyết định giảm chi phí có thể làm tăng thời gian phục hồi; một biện pháp bảo mật có thể ảnh hưởng latency; một lựa chọn tăng redundancy có thể tăng mức tiêu thụ tài nguyên. Review cần nhìn vào tổng thể và ghi nhận trade-off.

### 3.1. Operational Excellence

Trụ cột này tập trung vào khả năng vận hành và cải tiến liên tục:

- Có owner và mô hình trách nhiệm rõ ràng không?
- Infrastructure và cấu hình có được quản lý bằng code không?
- Có quy trình triển khai, rollback, change management và incident response không?
- Log, metric, trace và event có đủ để phát hiện và điều tra sự cố không?
- Runbook có thể thực thi và được kiểm thử không?
- Có post-incident review và cơ chế cải tiến không?

Trong AWS, các thành phần có thể bao gồm CloudWatch, CloudTrail, AWS Config, Systems Manager, EventBridge, deployment pipeline và IaC. Việc có dịch vụ không đồng nghĩa đã có năng lực vận hành; phải kiểm tra cấu hình, ownership và quy trình sử dụng.

### 3.2. Security

Trụ cột Security kiểm tra cách bảo vệ workload, identity, dữ liệu và hạ tầng:

- Identity được xác thực và phân quyền theo least privilege chưa?
- Có tách quyền người dùng, workload role và quyền quản trị không?
- Data classification, encryption, key lifecycle và secret management có rõ không?
- Network boundary, ingress/egress và private connectivity được kiểm soát ra sao?
- Có logging, detection, incident response và vulnerability management không?
- Security control có được kiểm tra liên tục và có bằng chứng không?

Các dịch vụ có thể dùng gồm IAM, IAM Identity Center, Organizations, SCP, KMS, Secrets Manager, ACM, VPC, Security Groups, Network Firewall, GuardDuty, Security Hub và CloudTrail. Chọn dịch vụ dựa trên threat model và yêu cầu kiểm soát.

### 3.3. Reliability

Reliability đánh giá khả năng workload thực hiện đúng chức năng khi có lỗi, tải thay đổi hoặc dependency suy giảm:

- Có xác định failure mode và blast radius không?
- Có loại bỏ single point of failure không?
- Có dùng Multi-AZ hoặc multi-Region theo RTO/RPO không?
- Có retry, timeout, backoff, circuit breaker và idempotency không?
- Có backup, restore test và failover/failback exercise không?
- Có kiểm tra service quota, capacity và dependency limit không?

Các dịch vụ như Route 53, Elastic Load Balancing, Auto Scaling, RDS Multi-AZ, DynamoDB, S3, AWS Backup, SQS và EventBridge có thể hỗ trợ reliability. Tuy nhiên, chọn dịch vụ managed không loại bỏ nhu cầu thiết kế failure handling.

### 3.4. Performance Efficiency

Performance Efficiency xem xét việc sử dụng tài nguyên và công nghệ phù hợp với workload:

- Có benchmark bằng tải đại diện không?
- Compute, storage và database có phù hợp với access pattern không?
- Có cache, queue hoặc asynchronous processing khi cần không?
- Có scale theo metric đúng và tránh scale oscillation không?
- Có xem xét managed/serverless service để giảm vận hành không?
- Có đo p50/p95/p99, throughput, saturation và error rate không?

Có thể dùng EC2, ECS, EKS, Lambda, Fargate, Aurora, DynamoDB, ElastiCache, CloudFront hoặc OpenSearch tùy pattern. Benchmark và profile thực tế quan trọng hơn việc chọn dịch vụ theo xu hướng.

### 3.5. Cost Optimization

Cost Optimization đánh giá tổng chi phí sở hữu và hiệu quả kinh tế:

- Có biết chi phí theo workload, môi trường và đơn vị nghiệp vụ không?
- Có dùng right-sizing, autoscaling và scheduling cho non-production không?
- Có chọn storage class, retention và backup phù hợp không?
- Có đo data transfer, NAT Gateway, log ingestion và cross-Region cost không?
- Có so sánh managed service với chi phí vận hành tự quản không?
- Có budget, anomaly detection, owner và review định kỳ không?

Cost Explorer, AWS Budgets, Cost and Usage Report, Compute Optimizer và tagging strategy có thể hỗ trợ. Giá thấp nhất trên một dòng dịch vụ chưa chắc là tổng chi phí thấp nhất khi tính cả vận hành và rủi ro.

### 3.6. Sustainability

Sustainability xem xét hiệu quả sử dụng tài nguyên và tác động môi trường:

- Có scale tài nguyên theo nhu cầu thực tế không?
- Có tắt hoặc giảm cấu hình môi trường idle không?
- Có tối ưu dữ liệu lưu trữ, retention và truyền dữ liệu không?
- Có chọn managed service và kiến trúc giảm overhead khi phù hợp không?
- Có tránh provision quá mức và workload chạy không cần thiết không?

Sustainability không chỉ là chọn instance nhỏ hơn. Cần cân bằng hiệu quả tài nguyên với reliability, security, latency và trải nghiệm người dùng.

## 4. Chuẩn bị hồ sơ cho buổi review

Một reviewer không thể đánh giá kiến trúc chính xác nếu chỉ có một sơ đồ tổng quát. Người thiết kế cần cung cấp đủ thông tin để hiểu cách hệ thống hoạt động, dữ liệu di chuyển ra sao và hệ thống phản ứng thế nào khi một phần bị lỗi.

### 4.1. Bộ hồ sơ tối thiểu

| Artifact | Nội dung |
|---|---|
| Workload brief | Business goal, owner, scope, criticality, users |
| Requirements matrix | Functional requirements, NFR, target, constraint, assumption |
| Context diagram | Người dùng, workload, hệ thống ngoài và boundary |
| Component/container diagram | Service, runtime, database, queue, cache, storage |
| Deployment diagram | Account, Region, AZ, VPC, subnet, routing và endpoint |
| Data flow diagram | Data classification, protocol, direction, encryption, retention |
| Trust boundary / threat model | Identity, attacker, threat, control và residual risk |
| Failure-mode analysis | Dependency, failure, detection, mitigation và recovery |
| Capacity/performance model | Traffic, growth, concurrency, latency và benchmark |
| Cost estimate | Service assumptions, pricing dimensions, data transfer, environment |
| Operations model | Monitoring, alert, runbook, backup, restore, support ownership |
| Decision log / ADR | Quyết định đã đưa ra, lý do, lựa chọn khác và hệ quả |

Không phải workload nào cũng cần mọi tài liệu ở mức chi tiết như nhau. Tuy nhiên, reviewer phải biết tài liệu nào chưa có và khoảng trống đó ảnh hưởng thế nào đến kết luận.

### 4.2. Sơ đồ phải thể hiện điều gì?

Một sơ đồ hữu ích cần cho người đọc biết:

- Ai gọi ai, theo giao thức và hướng nào.
- Thành phần nào nằm ở account, Region, AZ, VPC hoặc subnet nào.
- Điểm kết thúc TLS và nơi dữ liệu được giải mã.
- Dữ liệu nào là nhạy cảm, nơi lưu trữ và cách mã hóa.
- Identity/role nào gọi service hoặc truy cập resource.
- Queue, retry, DLQ, cache và database nằm ở đâu.
- Thành phần nào là managed service, thành phần nào do đội ngũ tự vận hành.
- Những dependency nào nằm ngoài quyền kiểm soát của nhóm.

Sơ đồ không cần thể hiện mọi ARN hoặc mọi security group rule. Chi tiết đó nên nằm trong IaC, inventory hoặc appendix. Sơ đồ phải đủ rõ để review được luồng và ranh giới.

### 4.3. Data flow và trust boundary

Đánh dấu vị trí dữ liệu được tạo, truyền, biến đổi, lưu và xóa. Với mỗi luồng, ghi:

- Data classification.
- Source và destination.
- Protocol/port.
- Authentication và authorization.
- Encryption in transit và at rest.
- Retention, backup, deletion và residency.
- Logging, masking và khả năng truy cập.

Một request đi từ Internet qua CloudFront, ALB, ECS, RDS có nhiều điểm trust boundary. Nếu TLS kết thúc ở ALB và backend dùng HTTP, phải thể hiện rõ điều đó. Không nên vẽ một đường “HTTPS” xuyên suốt khi thực tế TLS kết thúc giữa đường.

## 5. Quy trình architecture review

Một quy trình đơn giản nhưng có kỷ luật gồm sáu giai đoạn:

~~~mermaid
flowchart TD
    A[Intake: mục tiêu và phạm vi] --> B[Preparation: hồ sơ và reviewer]
    B --> C[Review: câu hỏi, bằng chứng, trade-off]
    C --> D[Findings: mức độ rủi ro và owner]
    D --> E[Disposition: xử lý hoặc chấp nhận rủi ro]
    E --> F[Follow-up: action, deadline, verify]
    F --> G[Periodic review / trigger mới]
    G --> A
~~~

### 5.1. Intake

Người yêu cầu review cung cấp workload brief, lý do review, thời điểm cần quyết định và phạm vi. Điều phối viên xác định reviewer có đủ chuyên môn và độc lập phù hợp hay không.

Kết quả intake:

- Workload và owner đã xác định.
- Scope và out-of-scope rõ ràng.
- Review type và mức độ sâu được thống nhất.
- Decision deadline và người có quyền quyết định được ghi nhận.

### 5.2. Preparation

Nhóm thiết kế chuẩn bị tài liệu. Reviewer đọc trước và ghi câu hỏi theo từng trụ cột. Nếu thiếu tài liệu quan trọng, có thể yêu cầu bổ sung trước buổi review hoặc đánh dấu assumption chưa được xác minh.

Không dùng buổi review để lần đầu tiên tìm hiểu business goal hoặc dựng lại sơ đồ từ đầu. Preparation tốt giúp dành thời gian cho các quyết định và rủi ro thực sự.

### 5.3. Review session

Một agenda tham khảo:

1. Business context và success criteria.
2. Scope, assumptions và constraints.
3. Architecture overview và data flow.
4. Reliability, security, performance, operations, cost và sustainability.
5. Các phương án và trade-off cần quyết định.
6. Finding, owner và next step.

Reviewer nên hỏi “bằng chứng nào cho thấy mục tiêu này đạt?” thay vì chỉ hỏi “đã bật dịch vụ X chưa?”. Ví dụ, câu hỏi “RTO 60 phút đã được chứng minh bằng restore exercise nào?” hữu ích hơn câu “có AWS Backup không?”.

### 5.4. Findings và disposition

Finding cần mô tả vấn đề, tác động, bằng chứng, mức độ ưu tiên, owner và thời hạn. Nhóm thiết kế đề xuất cách xử lý. Người có thẩm quyền quyết định sửa, chấp nhận rủi ro, chuyển cấp hoặc ghi nhận exception.

Không đánh dấu finding là “resolved” chỉ vì đã tạo ticket. Cần có bằng chứng thay đổi đã được triển khai và kiểm tra.

### 5.5. Follow-up

Theo dõi action item đến khi:

- Hoàn thành và có bằng chứng.
- Được thay thế bằng một quyết định mới.
- Được chấp nhận rủi ro theo quy trình.
- Không còn áp dụng vì scope hoặc requirement thay đổi.

Khi finding quá hạn, cần có escalation path. Không để các finding quan trọng tồn tại vô thời hạn trong một spreadsheet không có owner.

## 6. Review độ tin cậy (Reliability)

Reliability review phải đi từ failure mode đến hành vi hệ thống. Không thể kết luận “high availability” chỉ vì có hai AZ hoặc dùng dịch vụ managed.

### 6.1. Failure domain và blast radius

Phân loại các lỗi có thể xảy ra:

- Process/container/instance.
- Availability Zone.
- Region.
- Network path, DNS hoặc certificate.
- Database/storage.
- Identity provider hoặc KMS key.
- Queue, event bus hoặc downstream service.
- Deployment/configuration error.
- Operator error hoặc credential compromise.
- Provider/third-party dependency.

Với mỗi lỗi, hỏi:

1. Lỗi có thể xảy ra như thế nào?
2. Hệ thống phát hiện bằng tín hiệu nào?
3. Người dùng nhìn thấy điều gì?
4. Thành phần nào tiếp tục hoạt động?
5. Có tự phục hồi hay cần thao tác người vận hành?
6. Dữ liệu có mất hoặc bị nhân đôi không?
7. Recovery time và recovery point là bao nhiêu?

### 6.2. Multi-AZ và multi-Region

Multi-AZ thường bảo vệ trước lỗi ở một AZ trong cùng Region. Multi-Region có thể giảm tác động của sự cố Region nhưng làm tăng độ phức tạp về replication, data consistency, routing, IAM, key management, cost và failback.

Không chọn multi-Region chỉ vì nghe có vẻ an toàn hơn. Cần so sánh:

| Tiêu chí | Multi-AZ | Multi-Region |
|---|---|---|
| Failure domain | AZ | Region |
| Data replication | Thường được dịch vụ quản lý trong Region | Phải xác định cơ chế theo dịch vụ |
| Latency | Thường thấp hơn giữa AZ trong Region | Có thể cao hơn giữa Region |
| Complexity | Thấp hơn tương đối | Cao hơn, cần runbook và test |
| Cost | Có thể tăng do standby/capacity | Thường tăng thêm replication, transfer và capacity |
| Recovery objective | Phù hợp nhiều HA workload | Dành cho yêu cầu phục hồi Region hoặc residency strategy |

Đối với mỗi service, kiểm tra tính năng HA/replication cụ thể. Không phải mọi resource đều có cùng semantics hoặc cùng độ trễ replication.

### 6.3. Retry, timeout và idempotency

Retry có thể tăng resilience khi lỗi tạm thời, nhưng retry không giới hạn dễ tạo retry storm. Review cần xem:

- Timeout có phù hợp với latency budget không?
- Retry có exponential backoff và jitter không?
- Có giới hạn số lần retry không?
- Request có idempotent hoặc có idempotency key không?
- Queue/DLQ có giữ thông điệp lỗi để xử lý không?
- Circuit breaker hoặc bulkhead có cần thiết không?

Với SQS, kiểm tra visibility timeout, message retention, redrive policy và dead-letter queue. Với EventBridge, kiểm tra retry policy, target DLQ và khả năng xử lý duplicate. Với Step Functions, kiểm tra retry/catch và state transition. Đừng giả định delivery exactly-once nếu hệ thống thực tế có thể phát lại message.

### 6.4. Backup, restore và disaster recovery

Review phải kiểm tra cả backup policy và bằng chứng restore:

- Recovery point có đủ mới để đáp ứng RPO không?
- Retention có đáp ứng quy định và nhu cầu vận hành không?
- Backup vault, KMS key và quyền restore có được bảo vệ không?
- Có copy sang account/Region khác nếu threat model yêu cầu không?
- Restore có được kiểm thử trên môi trường cô lập không?
- Dữ liệu và ứng dụng sau restore đã được xác minh chưa?
- Có runbook, owner và quyết định failover/failback không?

Backup job thành công không chứng minh restore thành công. Restore job hoàn tất cũng không chứng minh dữ liệu đúng hoặc ứng dụng sẵn sàng. Review cần yêu cầu bằng chứng validation và đo RTO/RPO đầu-cuối.

## 7. Review bảo mật (Security)

Security review nên dựa trên data flow và threat model. Mỗi thành phần, identity và trust boundary đều cần được đánh giá.

### 7.1. Identity và least privilege

- Human access có dùng federation/SSO và MFA không?
- Workload có IAM role riêng thay vì access key dài hạn không?
- Policy có resource scope, condition và permission boundary phù hợp không?
- Quyền cross-account được thiết kế rõ ràng không?
- Có tách quyền deploy, runtime, audit và break-glass không?
- Secrets có được lưu trong Secrets Manager/Parameter Store hoặc hệ thống phù hợp không?
- Credential có rotation và audit không?

Với AWS Organizations, review account boundary, OU, SCP, delegated administrator và account vending. SCP giới hạn quyền tối đa có thể dùng trong member account; nó không tự cấp quyền cho principal.

### 7.2. Network và trust boundary

Review VPC CIDR, subnet, route table, internet/NAT path, VPC endpoint, security group và network ACL. Kiểm tra inbound/outbound có đúng nguồn, đích và port. Đánh giá private connectivity cho AWS service và đối tác.

Đừng dùng “private subnet” như bằng chứng đầy đủ của bảo mật. Một workload trong private subnet vẫn có thể truy cập Internet qua NAT, service endpoint hoặc route khác. Phải xem routing thực tế và policy.

### 7.3. Data protection

Đối với dữ liệu nhạy cảm, kiểm tra:

- Encryption at rest và in transit.
- KMS key ownership, policy, rotation và deletion protection.
- Certificate lifecycle và TLS policy.
- Data classification, masking và tokenization nếu phù hợp.
- Backup encryption và quyền restore.
- Data retention, deletion và legal hold.
- Cross-Region/cross-account data transfer.

Đặc biệt, key policy hoặc secret access sai có thể khiến dữ liệu không đọc được sau restore hoặc failover. Security và reliability phải được review cùng nhau.

### 7.4. Threat modeling

Có thể dùng STRIDE để gợi ý nhóm mối đe dọa:

| Nhóm | Câu hỏi ví dụ |
|---|---|
| Spoofing | Kẻ tấn công có giả danh workload hoặc user được không? |
| Tampering | Request, message hoặc object có thể bị sửa trái phép không? |
| Repudiation | Có audit trail đủ để truy vết hành động không? |
| Information Disclosure | Dữ liệu có rò rỉ qua log, URL, bucket hoặc network không? |
| Denial of Service | Một client hoặc dependency có thể làm cạn capacity không? |
| Elevation of Privilege | Lỗi cấu hình IAM hoặc application có thể tăng quyền không? |

Threat model cần gắn threat với control, owner và residual risk. Một bảng STRIDE điền đủ tên nhưng không có luồng dữ liệu hoặc biện pháp xử lý không phải là threat model hoàn chỉnh.

## 8. Review hiệu năng và khả năng mở rộng

Hiệu năng phải được đánh giá trên workload pattern thực tế, không chỉ trên cấu hình dịch vụ.

### 8.1. Mô hình tải

Xác định:

- Request rate trung bình, peak và burst.
- Read/write ratio.
- Payload size và data volume.
- Concurrent users, connections và background jobs.
- Diurnal/seasonal pattern.
- Growth forecast.
- Latency target theo percentile.
- Workload mix và tenant skew.

Một hệ thống có 1.000 request/giây nhưng payload 1 KB khác đáng kể hệ thống 1.000 request/giây với payload 5 MB. Cần biết cả throughput dữ liệu và request.

### 8.2. Chọn compute

| Lựa chọn | Phù hợp khi | Câu hỏi review |
|---|---|---|
| EC2 | Cần kiểm soát OS, runtime hoặc cấu hình đặc thù | Capacity, patching, scaling, instance family và HA |
| ECS/Fargate | Container workload muốn giảm quản lý host | Task sizing, deployment, networking, task role và scaling |
| EKS | Cần Kubernetes ecosystem hoặc platform standard | Cluster operations, add-on, node capacity, upgrade và policy |
| Lambda | Event-driven hoặc request workload phù hợp execution model | Timeout, concurrency, cold start, package, retry và cost |

Không có lựa chọn “tốt nhất” chung. So sánh theo operational burden, runtime constraints, scaling behavior, latency, portability, security và total cost.

### 8.3. Data tier và caching

Review database/storage dựa trên access pattern:

- Relational transaction, constraint và join.
- Key-value/document lookup theo key.
- Object storage cho blob, file, backup và data lake.
- Shared file system cho workload cần file semantics.
- Cache cho dữ liệu đọc nhiều và có chiến lược invalidation.
- Search engine cho full-text hoặc search analytics.

Kiểm tra connection pool, hot partition, index, cache hit ratio, eviction, consistency và behavior khi cache unavailable. Cache không nên trở thành nguồn dữ liệu chuẩn nếu chưa có chủ đích.

### 8.4. Benchmark và load test

Review yêu cầu benchmark có thể lặp lại:

- Dataset đại diện và không chứa dữ liệu production nhạy cảm nếu không được phép.
- Cấu hình runtime, instance, database và Region được ghi lại.
- Load profile và thời gian warm-up rõ ràng.
- Đo latency percentile, throughput, error rate, CPU, memory, I/O và queue depth.
- Có test steady-state, burst, stress và recovery sau tải.
- Kết quả có ngưỡng pass/fail và phiên bản phần mềm.

Một benchmark chỉ đo một request đơn lẻ không thể chứng minh hệ thống đáp ứng tải đỉnh.

## 9. Review chi phí và hiệu quả kinh tế

Cost review nên bắt đầu từ mô hình usage và đơn vị kinh doanh, ví dụ cost per order, cost per active user hoặc cost per GB processed.

### 9.1. Thành phần chi phí dễ bị bỏ sót

- Compute chạy liên tục và idle capacity.
- Database instance, storage, I/O, backup và replica.
- S3 storage class, request, retrieval và lifecycle.
- NAT Gateway, data transfer giữa AZ/Region và Internet egress.
- Load balancer, public IPv4, VPC endpoint và IP consumption.
- CloudWatch logs ingestion, retention, metrics và tracing.
- KMS requests, secrets, queue/event và API calls.
- DR standby capacity, replication và restore exercise.
- Support, operational labor và license bên thứ ba.

### 9.2. So sánh tổng chi phí sở hữu

Khi so sánh EC2 với Lambda hoặc RDS với database tự quản trên EC2, đừng chỉ nhìn giá compute. Tính cả:

- Provisioned/consumed capacity.
- Storage, backup và network.
- License và support.
- Patch, upgrade, scaling và incident handling.
- Engineering time và on-call burden.
- Cost của downtime và data loss.

Managed service có thể có giá dịch vụ cao hơn nhưng giảm công vận hành. Self-managed có thể tối ưu ở quy mô đặc thù nhưng cần tính chi phí chuyên môn và rủi ro.

### 9.3. Cost estimate cần ghi giả định

Một estimate phải nêu Region, currency, usage profile, commitment, discount assumption, retention, data transfer và growth. Nếu dùng pricing calculator, lưu bản estimate hoặc snapshot để có thể so sánh với actual spend sau triển khai.

Không trình bày estimate như hóa đơn chính xác. Actual cost phụ thuộc usage, giá hiện hành, discount, tax và hành vi workload.

## 10. Review vận hành, observability và support

Một kiến trúc production phải cho phép đội ngũ biết điều gì đang xảy ra và hành động khi hệ thống lệch khỏi trạng thái bình thường.

### 10.1. Observability

Kiểm tra:

- Metrics có đo golden signals: latency, traffic, errors, saturation không?
- Logs có structured fields, correlation ID và retention phù hợp không?
- Traces có theo dõi luồng qua service boundary không?
- Alert có actionable, có owner và runbook không?
- Dashboard có giúp trả lời câu hỏi vận hành không?
- Có phân biệt alert symptom và alert cause không?
- Telemetry có giới hạn cardinality, PII và chi phí không?

CloudWatch, X-Ray, OpenTelemetry/ADOT, Managed Prometheus hoặc công cụ observability khác có thể được sử dụng tùy yêu cầu. Không cần bật mọi tín hiệu cho mọi component; cần tín hiệu phục vụ mục tiêu và điều tra.

### 10.2. Runbook và incident response

Runbook nên chỉ rõ:

- Trigger hoặc symptom.
- Điều kiện và quyền cần thiết.
- Các bước kiểm tra theo thứ tự.
- Hành động an toàn và hành động cần phê duyệt.
- Điều kiện rollback hoặc escalation.
- Cách xác minh phục hồi.
- Cách ghi nhận evidence.

Review một runbook bằng cách hỏi người trực on-call có thể thực hiện nó khi áp lực cao hay không. Nếu các bước phụ thuộc vào trí nhớ của một cá nhân, runbook chưa đủ tốt.

### 10.3. Support và service limits

Kiểm tra support plan, escalation path, service quota, API rate limit, account limit, Region availability và maintenance window. Một kiến trúc có thể đúng về logic nhưng không triển khai được vì quota hoặc feature không có ở Region đã chọn.

Đưa quota vào capacity model. Nếu hệ thống có thể tăng đột biến, hãy xác minh quota trước khi cần tăng và có quy trình yêu cầu nâng hạn mức.

## 11. Review kiến trúc tích hợp và data consistency

Các thành phần tích hợp tạo ra coupling và failure propagation. Cần review cách hệ thống phản ứng khi downstream chậm, lỗi hoặc xử lý trùng.

### 11.1. Synchronous và asynchronous

Synchronous call dễ hiểu và trả kết quả trực tiếp, nhưng làm tăng coupling về availability và latency. Asynchronous messaging giúp tách thời gian xử lý, hấp thụ burst và retry, nhưng tạo eventual consistency và yêu cầu quản lý message lifecycle.

| Tiêu chí | Synchronous API | Asynchronous messaging |
|---|---|---|
| Response | Trả ngay trong request | Xử lý sau, có thể phản hồi bằng event/status |
| Coupling | Chặt hơn theo thời gian | Lỏng hơn |
| Failure handling | Timeout, retry, circuit breaker | Retry, visibility, DLQ, replay |
| Consistency | Có thể read-after-write tùy thiết kế | Thường eventual consistency |
| Scale burst | Caller có thể bị chặn | Queue có thể hấp thụ burst |
| Complexity | Ít thành phần hơn | Cần quản lý event/schema/order/deduplication |

### 11.2. Event schema và compatibility

Đối với EventBridge, SNS, SQS hoặc stream, review:

- Schema có version và owner không?
- Consumer cũ có xử lý được field mới không?
- Có phân biệt breaking và non-breaking change không?
- Có idempotency key và deduplication strategy không?
- Có thứ tự xử lý cần đảm bảo không?
- Có DLQ, replay và retention phù hợp không?
- Có thể truy vết event từ producer đến consumer không?

Không dùng event payload như một database dùng chung không có contract. Event nên biểu diễn sự kiện hoặc command theo ý nghĩa rõ ràng.

### 11.3. Data consistency và migration

Nếu hệ thống dùng nhiều database, cache, search index hoặc data lake, cần ghi rõ source of truth và cách đồng bộ. Review migration theo các bước expand/contract khi cần tương thích nhiều phiên bản ứng dụng.

Một migration an toàn thường có:

1. Thêm cấu trúc mới tương thích với phiên bản cũ.
2. Deploy producer/consumer hỗ trợ cả định dạng cũ và mới.
3. Backfill hoặc dual-write có kiểm soát.
4. Verify count, checksum và invariant.
5. Chuyển read path.
6. Ngừng cấu trúc cũ sau khi xác nhận không còn consumer.

Dual-write có thể tạo trạng thái không nhất quán nếu một phía thành công và phía kia thất bại. Cần có reconciliation hoặc outbox pattern nếu phù hợp.

## 12. Đánh giá các lựa chọn dịch vụ AWS

Architecture review không phải cuộc thi liệt kê dịch vụ. Mỗi lựa chọn phải gắn với workload pattern, requirement và trade-off.

### 12.1. ALB, API Gateway hay CloudFront?

| Thành phần | Vai trò thường gặp | Câu hỏi trước khi chọn |
|---|---|---|
| CloudFront | CDN, edge caching, phân phối nội dung và lớp edge | Cacheability, origin, WAF, geography và invalidation |
| ALB | Layer 7 routing tới target group | HTTP routing, target health, TLS termination và integration với compute |
| API Gateway | Quản lý API, throttling, auth integration, API lifecycle | API type, latency, payload, auth, quota và pricing |

Có thể kết hợp nhiều dịch vụ theo lớp. Ví dụ CloudFront phía trước ALB hoặc API Gateway. Cần xác định nơi áp dụng WAF, TLS, authentication, rate limit và logging để không tạo khoảng trống hoặc kiểm soát trùng lặp không cần thiết.

### 12.2. RDS/Aurora hay DynamoDB?

RDS/Aurora phù hợp khi cần relational model, SQL, transaction và quan hệ dữ liệu. DynamoDB phù hợp với access pattern dựa trên key, throughput lớn và mô hình dữ liệu được thiết kế theo query.

Review phải xem:

- Access pattern và query shape.
- Transaction và consistency requirement.
- Data model, index và partition strategy.
- Backup/PITR và recovery.
- Scaling, connection management và operational skills.
- Cost theo request, storage, capacity và traffic.

Không chọn DynamoDB chỉ vì muốn “serverless”, cũng không chọn relational database chỉ vì đội ngũ đã quen SQL mà chưa phân tích access pattern.

### 12.3. ECS, EKS hay Lambda?

So sánh execution model, packaging, runtime, startup, scaling, observability, security boundary, upgrade và skill set. Một workload có thể kết hợp Lambda cho event processing và ECS cho API service. Tránh đưa mọi thứ vào một platform duy nhất chỉ vì tổ chức đã chuẩn hóa, nếu điều đó làm tăng độ phức tạp hoặc chi phí không cần thiết.

### 12.4. S3, EFS hay FSx?

- S3 là object storage, không phải POSIX file system.
- EFS cung cấp shared file system semantics cho Linux workload.
- FSx cung cấp các file system chuyên biệt như Windows File Server, Lustre, ONTAP và OpenZFS.

Review theo protocol, access pattern, latency, throughput, locking, metadata, file semantics, data sharing và backup. Việc ứng dụng yêu cầu rename atomic hoặc POSIX permission có thể ảnh hưởng quyết định.

## 13. Ghi nhận quyết định bằng Architecture Decision Record

ADR là một bản ghi ngắn gọn về một quyết định kiến trúc quan trọng. ADR giữ lại bối cảnh và lý do, để người đọc tương lai hiểu vì sao hệ thống được thiết kế như hiện tại.

Một ADR tốt không phải tài liệu quảng bá lựa chọn đã được chọn. Nó nêu vấn đề, các lựa chọn thực tế, tiêu chí, quyết định, hệ quả và điều kiện có thể khiến quyết định thay đổi.

### 13.1. Khi nào cần ADR?

Nên tạo ADR khi quyết định:

- Ảnh hưởng nhiều component hoặc nhiều team.
- Tạo coupling dài hạn hoặc khó đảo ngược.
- Thay đổi data model, API contract, identity hoặc trust boundary.
- Chọn Region, account structure hoặc DR strategy.
- Ảnh hưởng đáng kể đến cost, security, compliance hoặc availability.
- Chọn một platform hoặc dịch vụ có chi phí migration cao.
- Tạo exception so với standard hoặc guardrail của tổ chức.

Không cần ADR cho mọi thay đổi nhỏ như đổi tên biến hoặc chỉnh một threshold không ảnh hưởng kiến trúc. Hãy chọn quyết định có giá trị cần lưu lại.

### 13.2. Cấu trúc ADR

Một mẫu ADR có thể gồm:

~~~markdown
# ADR-0042: Chọn mô hình database cho Order Service

- Status: Proposed | Accepted | Rejected | Superseded
- Date: YYYY-MM-DD
- Decision owner: Team/role
- Reviewers: Names or roles
- Scope: Workload/component

## Context
Business goal, requirements, constraints, assumptions and current problem.

## Decision drivers
Latency, consistency, availability, security, operability, cost and skills.

## Options considered
Option A, Option B, Option C with evidence and trade-offs.

## Decision
The selected option and the reason it best satisfies the drivers.

## Consequences
Positive effects, negative effects, new risks, operational tasks and migration cost.

## Validation
Benchmark, proof of concept, security review, DR test or other evidence.

## Revisit conditions
The events or thresholds that should trigger a new review.

## References
Architecture diagrams, review findings, code, tickets and AWS documentation.
~~~

Mẫu trên là cấu trúc tham khảo. Tổ chức có thể bổ sung owner, risk acceptance, expiration date hoặc link approval theo governance của mình.

### 13.3. Status và lifecycle

| Status | Ý nghĩa |
|---|---|
| Proposed | Đang được thảo luận, chưa phải quyết định có hiệu lực |
| Accepted | Đã được người có thẩm quyền chấp nhận |
| Rejected | Đã xem xét nhưng không chọn |
| Superseded | Đã có ADR mới thay thế |
| Deprecated | Quyết định không còn được khuyến nghị, nhưng có thể còn tồn tại ở workload cũ |

Không xóa ADR cũ khi kiến trúc thay đổi. Đánh dấu ADR cũ là Superseded và liên kết đến ADR mới để giữ lịch sử.

## 14. Ví dụ ADR: chọn database cho Order Service

Ví dụ này minh họa cách ghi lại trade-off. Các con số và giả định là dữ liệu giả lập để luyện tập, không phải benchmark hay giá dịch vụ AWS.

### ADR-0042: Chọn database cho Order Service

**Status:** Accepted

**Scope:** Order Service của một ứng dụng thương mại điện tử

**Decision owner:** Architecture owner và Order team

#### Context

Order Service lưu đơn hàng, trạng thái thanh toán, item và lịch sử thay đổi. Workload cần transaction cho các thao tác cập nhật quan trọng, query theo order ID, customer ID và trạng thái, đồng thời có báo cáo theo ngày. Dữ liệu cần giữ tính nhất quán giữa order và order item.

Yêu cầu giả định:

- 1.500 request/giây ở peak.
- p95 dưới 250 ms cho các query chính.
- RPO 5 phút và RTO 60 phút.
- Cần SQL transaction và constraint.
- Team đã có kinh nghiệm vận hành relational database.

#### Options considered

| Option | Điểm mạnh | Trade-off |
|---|---|---|
| Amazon Aurora | Relational model, SQL, managed cluster và khả năng HA/read scaling theo cấu hình | Chi phí, connection management, capacity planning và giới hạn engine |
| Amazon RDS for PostgreSQL | PostgreSQL managed, relational semantics và ecosystem quen thuộc | HA/read scaling và capacity phụ thuộc cấu hình instance |
| DynamoDB | Managed key-value/document, scale theo access pattern | Cần thiết kế partition/index, query flexibility và transaction model khác SQL |

#### Decision

Chọn Aurora PostgreSQL cho Order Service vì transaction và relational integrity là yêu cầu chính, query cần SQL và team có kỹ năng PostgreSQL. Read scaling, Multi-AZ, backup và PITR được thiết kế theo mục tiêu workload.

#### Consequences

Tích cực:

- Dùng được transaction, foreign key và SQL query.
- Giảm công vận hành database so với tự quản trên EC2.
- Có thể tách read workload nếu benchmark cho thấy cần thiết.

Tiêu cực:

- Cần kiểm soát connection pool và query performance.
- Chi phí có thể cao hơn lựa chọn key-value ở access pattern đơn giản.
- Cần kiểm thử restore và failover, không giả định managed đồng nghĩa không gián đoạn.

#### Validation

- Benchmark với dataset và workload đại diện.
- Kiểm tra p95/p99, connection saturation và failover.
- Restore test vào môi trường cô lập.
- Xác minh transaction, schema, constraint và RPO marker.

#### Revisit conditions

Review lại nếu workload chuyển sang key-based access với throughput lớn, transaction cross-table không còn cần thiết, chi phí vượt target hoặc latency không đạt sau tối ưu query.

Điểm quan trọng là ADR lưu lại cả lý do chọn và điều kiện khiến quyết định cần xem xét lại. Nếu chỉ ghi “dùng Aurora vì phù hợp”, người đọc sau này không biết tiêu chí nào đã được cân nhắc.

## 15. So sánh phương án bằng decision matrix

Khi có nhiều phương án, decision matrix giúp làm rõ tiêu chí và trọng số. Nó không thay thế phán đoán kỹ thuật, nhưng làm giảm tranh luận dựa trên cảm giác.

Ví dụ giả lập cho hai lựa chọn deployment:

| Tiêu chí | Trọng số | ECS/Fargate | EKS |
|---|---:|---:|---:|
| Operational simplicity | 25% | 5 | 2 |
| Kubernetes ecosystem | 15% | 1 | 5 |
| Workload portability | 10% | 2 | 5 |
| Team skill fit | 20% | 5 | 3 |
| Scaling/control needs | 15% | 4 | 5 |
| Cost at expected load | 15% | 4 | 3 |

Giả sử thang điểm 1–5, điểm tổng hợp là tổng của điểm từng tiêu chí nhân với trọng số. Với các số giả định trên:

[
Score_{Fargate}=0.25(5)+0.15(1)+0.10(2)+0.20(5)+0.15(4)+0.15(4)=3.80
]

[
Score_{EKS}=0.25(2)+0.15(5)+0.10(5)+0.20(3)+0.15(5)+0.15(3)=3.55
]

Fargate có điểm cao hơn trong ví dụ, nhưng nếu Kubernetes ecosystem là constraint bắt buộc thì EKS có thể vẫn là lựa chọn đúng. Decision matrix là công cụ làm rõ trade-off; không được dùng điểm số để che giấu constraint, risk hoặc dữ liệu chưa xác minh.

### 15.1. Chọn tiêu chí và trọng số

- Tiêu chí phải liên quan đến requirement.
- Trọng số phải được owner thống nhất trước khi chấm điểm.
- Điểm phải có giải thích hoặc bằng chứng.
- Không dùng cùng một ý dưới nhiều tiêu chí để làm lệch kết quả.
- Ghi rõ tiêu chí bắt buộc và tiêu chí có thể đánh đổi.
- Thực hiện sensitivity analysis nếu kết quả phụ thuộc nhiều vào một trọng số.

Nếu hai lựa chọn gần điểm nhau, hãy làm proof of concept hoặc benchmark thay vì tạo cảm giác có một câu trả lời toán học chính xác.

## 16. Quản lý findings, risk và exception

Một finding phải đủ cụ thể để người khác có thể hiểu, ưu tiên và xác minh.

### 16.1. Mẫu finding

~~~text
ID: AR-2026-014
Title: Restore process chưa chứng minh đạt RPO 5 phút
Category: Reliability
Severity: High
Evidence: Backup schedule là 15 phút; chưa có restore validation
Impact: Có thể mất nhiều dữ liệu hơn mục tiêu khi database gặp sự cố
Recommendation: Bổ sung PITR/recovery-point monitoring và restore exercise
Owner: Database team
Due date: YYYY-MM-DD
Disposition: Open
Verification: Restore test + transaction marker comparison
~~~

### 16.2. Phân loại mức độ

| Mức | Diễn giải | Cách xử lý gợi ý |
|---|---|---|
| Critical | Có thể gây compromise nghiêm trọng, mất dữ liệu lớn hoặc ngừng dịch vụ trọng yếu | Escalate ngay, chặn go-live hoặc yêu cầu biện pháp tạm thời |
| High | Rủi ro lớn, không đáp ứng NFR quan trọng | Có owner và deadline trước mốc phát hành đã thống nhất |
| Medium | Có tác động đáng kể nhưng có workaround | Đưa vào kế hoạch có thời hạn và theo dõi |
| Low | Cải tiến hoặc rủi ro giới hạn | Ghi backlog và xem xét theo chu kỳ |

Severity cần xét impact, likelihood, exposure, detectability và khả năng phục hồi. Không nên gán mức chỉ theo cảm nhận hoặc số lượng comment.

### 16.3. Risk acceptance

Chấp nhận rủi ro là một quyết định có chủ đích. Record cần có:

- Risk statement và evidence.
- Business impact và residual risk.
- Mitigation hiện có và lựa chọn đã cân nhắc.
- Người có thẩm quyền chấp nhận.
- Phạm vi workload, account, Region hoặc dữ liệu áp dụng.
- Expiration/review date.
- Trigger khiến exception phải được xem xét lại.

Người thiết kế không nên tự chấp nhận rủi ro vượt thẩm quyền. Một exception không có owner hoặc ngày xem xét lại thường trở thành nợ kỹ thuật không được kiểm soát.

## 17. AWS Well-Architected Tool

AWS Well-Architected Tool hỗ trợ ghi nhận workload, trả lời câu hỏi theo framework, tạo milestone và theo dõi improvement plan. Nó giúp chuẩn hóa review và lưu lịch sử đánh giá.

### 17.1. Cách sử dụng ở mức quy trình

1. Xác định workload và owner.
2. Tạo workload trong Well-Architected Tool với thông tin scope phù hợp.
3. Chọn lens hoặc workload review phù hợp với loại workload.
4. Trả lời câu hỏi dựa trên bằng chứng.
5. Ghi nhận risk/high-risk issue và improvement plan.
6. Giao owner và due date cho action.
7. Tạo milestone để lưu trạng thái review.
8. Thực hiện lại review khi có thay đổi lớn hoặc theo chu kỳ.

Tool không tự khám phá mọi cấu hình AWS hoặc tự chứng minh một câu trả lời là đúng. Chất lượng kết quả phụ thuộc vào người trả lời và bằng chứng được cung cấp.

### 17.2. Lens và scope

Well-Architected Framework cung cấp baseline. AWS và cộng đồng có thể cung cấp lens chuyên biệt cho workload hoặc ngành. Chọn lens theo nhu cầu, không chọn tất cả lens chỉ để tăng số lượng câu hỏi.

Khi một câu hỏi không áp dụng, ghi lý do và phạm vi. Không dùng “Not applicable” để né một yêu cầu khó.

### 17.3. Improvement plan

Improvement plan nên mô tả:

- Risk hoặc best practice chưa đạt.
- Hành động cần thực hiện.
- Owner và due date.
- Dependency và effort.
- Expected outcome.
- Cách xác minh sau khi hoàn thành.

Không đóng improvement plan chỉ vì đã tạo PR hoặc ticket. Cần xác minh control đã được triển khai và đạt kết quả mong đợi.

## 18. Quản lý tài liệu và decision log

Architecture diagram, ADR, review finding và IaC cần có quan hệ rõ ràng.

### 18.1. Nơi lưu trữ

Có thể lưu ADR cạnh source code trong repository, hoặc trong một kho tài liệu có version history và quyền truy cập phù hợp. Điều quan trọng:

- Có thể tìm theo workload và quyết định.
- Có version history.
- Có owner và trạng thái.
- Liên kết đến ticket, code, diagram và evidence.
- Có retention và access control phù hợp.

### 18.2. Quy tắc đặt tên

Ví dụ:

~~~text
docs/
  architecture/
    diagrams/
      order-context.drawio
      order-deployment.drawio
    decisions/
      ADR-0001-order-database.md
      ADR-0002-event-delivery.md
    reviews/
      2026-11-production-readiness.md
    risks/
      architecture-risk-register.md
~~~

Đặt tên theo số thứ tự ổn định và chủ đề. Không đổi tên ADR chỉ vì lựa chọn đã thay đổi; tạo ADR mới và liên kết ADR cũ.

### 18.3. Đồng bộ tài liệu với hệ thống thật

Review định kỳ cần so sánh sơ đồ với IaC, inventory và telemetry. Nếu tài liệu chỉ mô tả thiết kế ban đầu, nó sẽ nhanh chóng lệch khỏi production.

Có thể thêm review gate vào pull request cho thay đổi có ảnh hưởng kiến trúc: yêu cầu cập nhật diagram, ADR hoặc threat model khi thay đổi network, data model, trust boundary hoặc dependency. Không yêu cầu cập nhật tài liệu cho mọi thay đổi không có ý nghĩa kiến trúc.

## 19. Tích hợp architecture review vào SDLC và IaC

Architecture review nên là một phần của vòng đời phát triển:

~~~mermaid
flowchart LR
    A[Discover requirements] --> B[Architecture options]
    B --> C[ADR proposed]
    C --> D[Design review]
    D --> E[Build with IaC]
    E --> F[Automated checks]
    F --> G[Deploy to test]
    G --> H[Performance / security / DR validation]
    H --> I[Production readiness review]
    I --> J[Operate and observe]
    J --> K[Periodic review]
    K --> B
~~~

### 19.1. Review sớm

Những quyết định như account structure, Region, database model, data residency và trust boundary thường tốn kém để thay đổi. Review sớm giúp phát hiện vấn đề khi chi phí sửa còn thấp.

### 19.2. Guardrail tự động

Có thể dùng:

- CloudFormation Guard hoặc policy-as-code để kiểm tra template.
- cfn-lint, Terraform validate và static analysis.
- IAM Access Analyzer để phát hiện quyền truy cập ngoài dự kiến.
- AWS Config rules và conformance packs để kiểm tra cấu hình.
- Security Hub và các công cụ security posture.
- CI policy gate cho secret, image, dependency và IaC.

Automated check chỉ kiểm tra những gì rule được viết ra. Một template pass không chứng minh kiến trúc đáp ứng RTO/RPO hoặc ứng dụng có thể phục hồi. Kết hợp kiểm tra tự động với review thiết kế và kiểm thử runtime.

### 19.3. Change impact analysis

Trước thay đổi, xác định:

- Component và team bị ảnh hưởng.
- API/schema compatibility.
- Data migration và rollback.
- Security group, IAM, KMS và network route.
- Capacity, quota và cost.
- Observability và alert.
- Backup, restore và DR.
- Thời gian triển khai, maintenance window và communication.

Một thay đổi nhỏ trong security group có thể ảnh hưởng nhiều service. Một thay đổi schema có thể ảnh hưởng consumer cũ. Review cần đánh giá tác động thực tế thay vì chỉ dựa trên số dòng code.

## 20. Các anti-pattern trong architecture review

1. **Review quá muộn:** quyết định khó đảo ngược đã được triển khai trước khi đánh giá.
2. **Chỉ review sơ đồ:** không xem NFR, data flow, IAM, failure mode hoặc chi phí.
3. **Service checklist:** đánh dấu đã dùng CloudWatch, Backup hoặc KMS mà không kiểm tra cấu hình và bằng chứng.
4. **One-size-fits-all:** ép mọi workload dùng cùng pattern dù requirement khác nhau.
5. **Opinion-driven:** chọn công nghệ vì sở thích hoặc xu hướng, không có tiêu chí.
6. **No alternatives:** ADR chỉ ghi phương án đã chọn, không ghi lựa chọn khác và trade-off.
7. **False precision:** dùng decision score hoặc estimate giả định như kết luận chắc chắn.
8. **No owner:** finding không có người chịu trách nhiệm và deadline.
9. **Risk accepted forever:** exception không có ngày hết hạn hoặc trigger review.
10. **Documentation drift:** sơ đồ và ADR không được cập nhật sau thay đổi.
11. **Tool-driven review:** coi kết quả Well-Architected Tool là chứng nhận tự động.
12. **Security-only review:** bỏ qua performance, cost, operability và sustainability.
13. **No failure test:** kiến trúc được review trong happy path nhưng chưa kiểm tra khi dependency hỏng.
14. **No evidence:** kết luận dựa trên lời nói, không có benchmark, log, test hoặc policy.
15. **Review as approval theater:** tổ chức buổi họp nhưng không theo dõi finding hoặc outcome.

## 21. Case study: review kiến trúc nền tảng đặt hàng

Một doanh nghiệp triển khai nền tảng đặt hàng trên AWS. Người dùng truy cập qua web/mobile. Hệ thống có Catalog, Checkout, Order, Payment và Inventory. Đội thiết kế đề xuất:

- CloudFront và WAF ở edge.
- ALB định tuyến tới ECS services.
- Aurora PostgreSQL cho Order.
- DynamoDB cho Catalog cache/index theo access pattern.
- SQS để xử lý tác vụ nền.
- EventBridge để phát domain event.
- S3 lưu hóa đơn và file export.
- CloudWatch, CloudTrail và AWS Backup cho vận hành.

### 21.1. Các câu hỏi review

**Business và NFR**

- Peak traffic có mô hình theo campaign không?
- Checkout latency target là bao nhiêu?
- Payment có yêu cầu idempotency và audit không?
- RTO/RPO cho Order khác Catalog như thế nào?

**Reliability**

- Nếu Payment provider timeout, Checkout có retry và tránh charge trùng không?
- Nếu SQS backlog tăng, có alarm theo age of oldest message không?
- Nếu Aurora failover, connection pool có reconnect đúng không?
- Có restore test cho database và file invoice không?

**Security**

- Payment data có được lưu không, và nếu có thì phạm vi nào?
- Task role của Payment có quyền đọc Catalog bucket không?
- Client chỉ truy cập qua edge hay ALB còn public trực tiếp?
- S3 bucket policy và KMS key có giới hạn principal không?

**Performance**

- Catalog cache invalidation hoạt động thế nào?
- Aurora connection count có phù hợp với ECS task scale không?
- Queue worker scale theo backlog hay CPU?
- Có benchmark campaign peak và test dependency chậm không?

**Cost**

- CloudFront cache giảm origin request được bao nhiêu?
- NAT Gateway và cross-AZ traffic có đáng kể không?
- Có thể scale down staging ngoài giờ không?
- Log retention có phù hợp với yêu cầu audit không?

**Operations**

- Có correlation ID xuyên qua Checkout, Order và Payment không?
- Có runbook khi Payment provider outage không?
- Ai chịu trách nhiệm xử lý DLQ?
- Có quy trình restore, validation và failback không?

### 21.2. Finding mẫu

| ID | Finding | Severity | Action |
|---|---|---|---|
| AR-01 | Payment retry chưa có idempotency key xuyên request | High | Bổ sung contract và test duplicate charge |
| AR-02 | ECS task role dùng policy rộng cho nhiều service | High | Tách role theo service và thu hẹp resource scope |
| AR-03 | Chưa đo queue age khi downstream chậm | Medium | Thêm metric, alarm và runbook |
| AR-04 | RTO database mới chỉ dựa trên estimate | High | Thực hiện restore test và đo T0–T5 |
| AR-05 | Chi phí NAT/data transfer chưa được đưa vào estimate | Medium | Bổ sung traffic model và actual cost review |

### 21.3. ADR mẫu được tạo

Một ADR có thể ghi quyết định sử dụng SQS cho công việc cần retry và xử lý nền, đồng thời dùng EventBridge cho domain event routing tới nhiều consumer. ADR cần giải thích vì sao một queue đơn không thay thế event bus trong trường hợp nhiều subscriber, và vì sao event bus không thay thế queue khi cần buffering, visibility timeout hoặc DLQ theo consumer.

Sau review, đội thiết kế cập nhật IAM role, idempotency, queue alarms, restore test và cost model. Review chỉ được đóng khi các action có bằng chứng hoặc risk acceptance hợp lệ.

## 22. Mẫu agenda và biên bản review

~~~markdown
# Architecture Review Record

## Workload
- Name:
- Owner:
- Business objective:
- Environment / account / Region:
- Review type:
- Date:

## Scope
- In scope:
- Out of scope:
- Assumptions:
- Constraints:

## Requirements
- Availability:
- Latency / throughput:
- RTO / RPO:
- Security / privacy:
- Cost:
- Compliance:

## Participants
- Architect:
- Engineering:
- Security:
- Operations:
- Business owner:

## Review summary
- Architecture overview:
- Main decisions:
- Evidence reviewed:
- Open questions:

## Findings
| ID | Category | Severity | Finding | Owner | Due date | Status |

## Decisions
- ADR link:
- Accepted trade-offs:
- Risk acceptance:

## Outcome
- Ready:
- Ready with actions:
- Rework required:
- Decision owner:
- Next review date:
~~~

### 22.1. Kết luận review

Có thể dùng ba kết luận đơn giản:

- **Ready:** không còn finding ngăn cản và bằng chứng cần thiết đã đạt.
- **Ready with actions:** có thể tiếp tục trong phạm vi đã thống nhất, với action, owner và deadline rõ.
- **Rework required:** còn rủi ro hoặc thiếu thông tin khiến chưa thể đưa ra quyết định.

Đây là quy ước governance nội bộ, không phải trạng thái được AWS định nghĩa. Tổ chức phải xác định ai có quyền đưa ra kết luận và ngoại lệ nào cần escalation.

## 23. Khi nào cần review lại?

Kiến trúc không bất biến. Review lại khi:

- Workload tăng trưởng hoặc thay đổi traffic profile đáng kể.
- Có Region, account, data store hoặc third-party dependency mới.
- Thay đổi authentication, authorization, trust boundary hoặc data classification.
- Thay đổi RTO/RPO, retention, compliance hoặc data residency.
- Có incident, outage, data corruption hoặc security finding.
- Có thay đổi lớn về AWS service feature, quota, pricing hoặc support.
- Chi phí lệch khỏi forecast trong nhiều kỳ.
- Team, ownership hoặc operational model thay đổi.
- ADR ghi rõ revisit condition đã xảy ra.

Periodic review không nên chỉ chạy theo lịch. Kết hợp lịch định kỳ với event trigger giúp review đúng lúc có thay đổi quan trọng.

## 24. Bài tập tự kiểm tra

### Câu 1

Một nhóm nói workload có availability cao vì chạy hai EC2 instance trong cùng một AZ. Reviewer cần hỏi gì?

**Đáp án:** Hai instance có nằm trong failure domain khác nhau không, load balancer health check ra sao, AZ outage được xử lý thế nào, state nằm ở đâu và RTO/RPO đã được kiểm thử chưa. Hai instance cùng AZ vẫn có thể cùng chịu ảnh hưởng của lỗi AZ.

### Câu 2

Yêu cầu “API phải nhanh” có đủ để chọn compute và database không?

**Đáp án:** Không. Cần lượng hóa latency percentile, throughput, payload, concurrency, access pattern và growth để benchmark và so sánh phương án.

### Câu 3

ADR chỉ ghi “chọn EKS vì linh hoạt”. Điều gì còn thiếu?

**Đáp án:** Context, decision drivers, lựa chọn thay thế, trade-off, operational burden, security, cost, validation evidence, consequences và điều kiện xem xét lại.

### Câu 4

AWS Well-Architected Tool đánh dấu câu hỏi là best practice achieved. Điều đó có chứng minh production đã cấu hình đúng không?

**Đáp án:** Không. Tool lưu câu trả lời và đánh giá theo thông tin được cung cấp. Cần bằng chứng cấu hình, test và vận hành thực tế.

### Câu 5

Một workload cần RTO 30 phút và RPO 1 phút. Có thể kết luận cần multi-Region ngay không?

**Đáp án:** Chưa. Cần phân tích failure domain, khả năng Multi-AZ/PITR, yêu cầu Region outage, replication semantics, consistency, cost và failover/failback. Multi-Region chỉ là một phương án.

### Câu 6

Tại sao không nên coi một finding là resolved khi ticket đã được tạo?

**Đáp án:** Ticket chỉ ghi nhận công việc. Cần triển khai thay đổi, kiểm tra kết quả và lưu bằng chứng trước khi đóng finding.

### Câu 7

Khi nào nên chấp nhận risk thay vì sửa ngay?

**Đáp án:** Khi owner có thẩm quyền đánh giá residual risk là chấp nhận được trong phạm vi và thời hạn cụ thể, có mitigation, expiry/review date và trigger rõ. Rủi ro vượt thẩm quyền phải được escalation.

### Câu 8

Một request đi qua CloudFront, ALB và ECS. Vì sao sơ đồ phải đánh dấu TLS termination?

**Đáp án:** Vì TLS có thể kết thúc ở một điểm và chặng tiếp theo có thể dùng HTTP hoặc TLS riêng. Đánh dấu điểm giải mã giúp đánh giá đúng data exposure và trust boundary.

### Câu 9

Decision matrix cho EKS điểm cao hơn ECS, nhưng tổ chức không có năng lực vận hành Kubernetes. Có nên tự động chọn EKS không?

**Đáp án:** Không. Team skill và operational capability là constraint/driver. Cần đánh giá training, platform team, managed add-on, on-call burden và chi phí trước khi quyết định.

### Câu 10

Sau khi thay đổi database model, có cần review ADR cũ không?

**Đáp án:** Cần xem điều kiện revisit của ADR. Nếu quyết định mới thay thế quyết định cũ, tạo ADR mới và đánh dấu ADR cũ Superseded, giữ liên kết lịch sử.

### Câu 11

Một service dùng SQS nhưng không có DLQ hoặc metric queue age. Reviewer nên ghi nhận gì?

**Đáp án:** Đây là khoảng trống về failure handling và operability. Cần xem retry/redrive, message retention, visibility timeout, alarm theo backlog/age và owner xử lý message lỗi.

### Câu 12

Một estimate chỉ tính EC2 và RDS nhưng bỏ NAT Gateway, data transfer và log ingestion. Estimate có đáng tin không?

**Đáp án:** Chưa. Cần bổ sung network, observability, backup, request, storage, support và vận hành để có total cost phù hợp.

### Câu 13

Khi nào nên tạo ADR?

**Đáp án:** Khi quyết định có ảnh hưởng dài hạn, nhiều team/component, khó đảo ngược hoặc ảnh hưởng security, reliability, cost, data model, account/Region hay platform.

### Câu 14

Một workload đã review trước production. Có cần review sau incident không?

**Đáp án:** Có nếu incident cho thấy giả định hoặc control trong kiến trúc không đúng. Post-incident review giúp cập nhật failure model, runbook, ADR và action plan.

### Câu 15

Sáu trụ cột Well-Architected có thể tối ưu độc lập không?

**Đáp án:** Không hoàn toàn. Các trụ cột có trade-off và tác động lẫn nhau. Cần tối ưu tổng thể theo mục tiêu workload và chấp nhận rủi ro có chủ đích.

## 25. Checklist architecture review

### Business và scope

- [ ] Workload, owner, business objective và user journey đã rõ.
- [ ] Scope, out-of-scope, assumptions và constraints được ghi lại.
- [ ] Functional requirements và NFR được lượng hóa.
- [ ] Data classification và dependency được xác định.

### Design và decision

- [ ] Context, component, deployment và data flow diagram có đủ chi tiết.
- [ ] Các phương án và trade-off được so sánh.
- [ ] Failure mode và blast radius đã được đánh giá.
- [ ] ADR được tạo cho quyết định quan trọng.
- [ ] ADR có status, owner, consequence, validation và revisit condition.

### Well-Architected

- [ ] Operational Excellence có telemetry, runbook, ownership và change process.
- [ ] Security có least privilege, encryption, threat model và audit.
- [ ] Reliability có HA, quota, retry, backup, restore và DR test.
- [ ] Performance có workload model và benchmark.
- [ ] Cost có estimate, usage assumptions và owner.
- [ ] Sustainability có kế hoạch giảm idle capacity và waste.

### Review outcome

- [ ] Finding có severity, evidence, owner và deadline.
- [ ] Risk acceptance có thẩm quyền, phạm vi và expiry/review date.
- [ ] Action item có cách xác minh.
- [ ] Diagram, ADR và IaC được đồng bộ.
- [ ] Kết luận và ngày review tiếp theo được ghi lại.

## 26. Tài liệu tham khảo chính thức

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/intro.html)
- [AWS Well-Architected Framework: Operational Excellence](https://docs.aws.amazon.com/wellarchitected/latest/framework/operational-excellence.html)
- [AWS Well-Architected Framework: Security](https://docs.aws.amazon.com/wellarchitected/latest/framework/security.html)
- [AWS Well-Architected Framework: Reliability](https://docs.aws.amazon.com/wellarchitected/latest/framework/reliability.html)
- [AWS Well-Architected Framework: Performance Efficiency](https://docs.aws.amazon.com/wellarchitected/latest/framework/performance-efficiency.html)
- [AWS Well-Architected Framework: Cost Optimization](https://docs.aws.amazon.com/wellarchitected/latest/framework/cost-optimization.html)
- [AWS Well-Architected Framework: Sustainability](https://docs.aws.amazon.com/wellarchitected/latest/framework/sustainability.html)
- [AWS Architecture Center](https://aws.amazon.com/architecture/)
- [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/welcome.html)
- [AWS Cloud Adoption Framework](https://docs.aws.amazon.com/whitepapers/latest/overview-aws-cloud-adoption-framework/welcome.html)
- [AWS CloudFormation Guard](https://docs.aws.amazon.com/cfn-guard/latest/ug/what-is-guard.html)
- [AWS IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html)
- [AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/WhatIsConfig.html)
- [AWS Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html)

Tên tính năng, câu hỏi trong lens, quota, giá và khả năng hỗ trợ dịch vụ có thể thay đổi theo thời gian và Region. Khi review một workload cụ thể, đối chiếu tài liệu hiện hành và bằng chứng trong account/Region đang triển khai.
