# Thiết kế yêu cầu, sơ đồ kiến trúc và ước tính chi phí dự án

Một dự án AWS thành công bắt đầu từ việc hiểu bài toán và lượng hóa yêu cầu, sau đó mới chọn dịch vụ, vẽ kiến trúc và ước tính chi phí. Nếu bắt đầu bằng danh sách dịch vụ yêu thích, nhóm có thể xây một hệ thống phức tạp nhưng không giải quyết đúng nhu cầu. Nếu chỉ có sơ đồ đẹp mà không có workload, ranh giới bảo mật, giả định và số liệu tải, kiến trúc cũng khó triển khai và dự toán.

Thiết kế dự án cloud là quá trình chuyển yêu cầu kinh doanh thành một hệ thống có thể triển khai, vận hành và phát triển. Người thiết kế cần xác định ai sử dụng hệ thống, chức năng nào bắt buộc, dữ liệu đi qua đâu, tải dự kiến ra sao, yêu cầu bảo mật và phục hồi là gì, đồng thời giải thích vì sao chọn từng dịch vụ AWS. Sơ đồ kiến trúc cần cho thấy thành phần, luồng dữ liệu, ranh giới mạng và quyền truy cập. Bản ước tính chi phí cần thể hiện giả định, đơn vị tính phí, môi trường, tăng trưởng và các yếu tố có thể làm tổng chi phí thay đổi.

Trong module CLOUD_PROVIDERS_AWS, người học khám phá hạ tầng Region/AZ, IAM, VPC, compute, storage, database, integration và serverless để có thể lựa chọn dịch vụ, thiết kế ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. Bài học này kết nối các kiến thức đó thành một quy trình capstone: làm rõ yêu cầu, dựng sơ đồ kiến trúc và lập cost model có thể kiểm tra.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Chuyển một vấn đề kinh doanh thành mục tiêu, phạm vi và tiêu chí nghiệm thu.
- Viết functional requirements và non-functional requirements có thể đo lường.
- Xác định giả định, ràng buộc, dependency và rủi ro của dự án.
- Ước lượng workload từ số người dùng, request, dữ liệu, retention và traffic peak.
- Chọn AWS Region, Availability Zones và dịch vụ phù hợp với yêu cầu.
- Vẽ sơ đồ context, logical architecture, data flow, deployment và security boundary.
- Giải thích lựa chọn compute, database, storage, messaging, networking và security.
- Thiết kế kiến trúc có logging, metrics, tracing, backup, recovery và deployment strategy.
- Dùng AWS Pricing Calculator để ước tính chi phí theo từng dịch vụ.
- Xây dựng baseline, growth và peak scenarios; phân tích độ nhạy và TCO.
- Gắn cost allocation tags, budget, alarm và cơ chế review chi phí.
- Trình bày một architecture decision record và bảo vệ quyết định thiết kế.

## 2. Quy trình thiết kế một dự án AWS

Không có một thứ tự duy nhất cho mọi dự án, nhưng quy trình dưới đây giúp nhóm đi từ bài toán tới bản thiết kế có thể review.

~~~mermaid
flowchart TD
    A[Problem and business goals] --> B[Requirements and constraints]
    B --> C[Workload and data model]
    C --> D[Architecture options]
    D --> E[Select AWS services]
    E --> F[Architecture diagrams and decisions]
    F --> G[Security, reliability and operations review]
    G --> H[Cost model and scenarios]
    H --> I[Prototype and validate assumptions]
    I --> J[Delivery roadmap and acceptance]
    J -->|New evidence or changed requirements| B
~~~

Các bước có thể lặp lại. Ví dụ, khi cost model cho thấy database vượt ngân sách, nhóm quay lại workload/access pattern để xem có thể aggregate, cache hoặc đổi mô hình lưu trữ không. Khi security review yêu cầu dữ liệu nằm trong private network, nhóm phải cập nhật network diagram và tính lại chi phí endpoint/NAT.

### 2.1. Hiểu vấn đề trước khi chọn dịch vụ

Hãy mô tả vấn đề bằng ngôn ngữ người dùng và business owner:

- Ai đang gặp khó khăn?
- Quy trình hiện tại mất bao lâu hoặc có lỗi gì?
- Kết quả nào cần cải thiện?
- Vì sao cần chuyển lên AWS hoặc xây hệ thống mới?
- Có hệ thống cũ nào phải tích hợp?
- Điều gì sẽ được xem là dự án thành công?

Ví dụ, câu “cần một hệ thống serverless trên AWS” chưa phải mục tiêu. Câu “nhân viên cửa hàng có thể tạo và theo dõi đơn hàng từ nhiều chi nhánh, giảm thời gian xử lý và có thể tiếp tục nhận đơn khi một worker downstream tạm thời lỗi” mô tả vấn đề và kết quả rõ hơn.

### 2.2. Xác định stakeholder

Liệt kê người dùng, business owner, product owner, developer, platform team, security, data team, operations và bên thứ ba. Mỗi nhóm có thể có yêu cầu khác nhau:

| Stakeholder | Câu hỏi cần làm rõ |
|---|---|
| Người dùng cuối | Họ thực hiện tác vụ nào, trên thiết bị nào? |
| Business owner | KPI, ngân sách và thời hạn là gì? |
| Developer | API, event, schema và workflow nào cần? |
| Security | Dữ liệu nào nhạy cảm, quyền nào bị hạn chế? |
| Operations | Ai trực, cảnh báo nào cần, RTO/RPO ra sao? |
| Finance/FinOps | Cách phân bổ chi phí và ngân sách theo team/project? |
| Đối tác | API, quota, SLA và cơ chế xác thực nào được cung cấp? |

Ghi rõ người phê duyệt từng nhóm yêu cầu. Nếu không có owner, yêu cầu có thể thay đổi mà không ai chịu trách nhiệm xác nhận tác động.

### 2.3. Xác định phạm vi

Chia phạm vi thành:

- In scope: chức năng và môi trường sẽ bàn giao.
- Out of scope: phần chưa triển khai trong capstone.
- Future phase: khả năng có thể bổ sung sau.

Ví dụ, phiên bản đầu của Order Platform có thể bao gồm đăng nhập, tạo đơn, xem trạng thái, xử lý fulfillment bất đồng bộ và dashboard vận hành. Tích hợp ERP đầy đủ, phân tích dự báo và triển khai multi-Region active-active có thể nằm ngoài giai đoạn đầu.

Phạm vi rõ giúp tránh việc kiến trúc bị mở rộng vô hạn và giúp cost estimate có cơ sở.

## 3. Thu thập và viết yêu cầu

### 3.1. Functional requirements

Functional requirement mô tả hệ thống phải làm gì. Viết theo hành động và kết quả có thể kiểm chứng.

Ví dụ:

1. Người dùng đã xác thực có thể tạo đơn hàng với một hoặc nhiều sản phẩm.
2. Hệ thống kiểm tra sản phẩm còn khả dụng trước khi xác nhận đơn.
3. Mỗi đơn hàng có ID duy nhất và trạng thái vòng đời.
4. Người dùng chỉ xem được đơn hàng thuộc tài khoản hoặc tenant của mình.
5. Khi đơn được tạo, hệ thống phát sự kiện để fulfillment xử lý bất đồng bộ.
6. Nhân viên vận hành có thể tìm đơn theo ID và xem lịch sử trạng thái.
7. Hệ thống lưu dấu vết thay đổi trạng thái để hỗ trợ đối soát.

Tránh viết yêu cầu mơ hồ như “hệ thống phải nhanh”, “dữ liệu phải an toàn” hoặc “có thể mở rộng”. Các câu này cần được chuyển thành tiêu chí đo lường.

### 3.2. Non-functional requirements

Non-functional requirements (NFR) mô tả chất lượng và giới hạn vận hành. Các nhóm thường gặp:

| Nhóm | Ví dụ yêu cầu đo lường |
|---|---|
| Performance | p95 API latency dưới 400 ms ở tải mục tiêu, không tính tác vụ async |
| Availability | Mục tiêu availability 99,9% theo cửa sổ tháng |
| Scalability | Hỗ trợ 100 request/giây trong peak dự kiến |
| Durability | Không mất order đã được xác nhận |
| Recovery | RTO 2 giờ, RPO 15 phút |
| Security | MFA cho operator, least privilege, mã hóa dữ liệu nhạy cảm |
| Privacy | Không lưu thông tin thẻ thanh toán; dữ liệu cá nhân có retention |
| Operability | Có dashboard, alert, runbook và audit trail |
| Compatibility | API có version và tương thích client cũ trong giai đoạn chuyển đổi |
| Cost | Chi phí cloud mục tiêu không vượt ngân sách tháng đã thống nhất |

Các con số trên là ví dụ, không phải cam kết mặc định của AWS. Business owner và operations phải xác nhận mục tiêu thực tế.

### 3.3. Viết NFR theo dạng có thể kiểm tra

Một yêu cầu tốt có bốn thành phần:

- Điều kiện: tải, thời gian, loại dữ liệu hoặc tình huống.
- Hành vi mong muốn.
- Ngưỡng đo lường.
- Cách kiểm thử hoặc bằng chứng.

Ví dụ:

“Trong giờ cao điểm 10:00–11:00 với 100 request/giây, 95% request đọc trạng thái đơn hoàn tất trong 400 ms, đo tại API Gateway bằng p95 latency trong bài load test 15 phút.”

Yêu cầu này rõ hơn câu “API phải nhanh” vì có workload, thời gian, percentile, ngưỡng và cách xác minh.

### 3.4. Acceptance criteria

Acceptance criteria là điều kiện để stakeholder chấp nhận chức năng. Có thể dùng Given/When/Then:

~~~text
Given người dùng đã đăng nhập và có quyền tạo đơn
When người dùng gửi đơn hợp lệ với idempotency key mới
Then hệ thống tạo một order ID và trả trạng thái PENDING

Given người dùng không thuộc tenant sở hữu đơn hàng
When người dùng yêu cầu xem order ID đó
Then API trả lỗi authorization và không tiết lộ nội dung đơn
~~~

Acceptance criteria phải bao gồm cả happy path, validation, authorization và failure path.

### 3.5. Ưu tiên yêu cầu

MoSCoW là một cách phân loại:

- Must have: bắt buộc để dự án có giá trị.
- Should have: quan trọng nhưng có phương án tạm thời.
- Could have: hữu ích nếu còn thời gian/ngân sách.
- Won't have now: chủ động để giai đoạn sau.

Ưu tiên giúp nhóm chọn kiến trúc vừa đủ. Không nên xây multi-Region, data lake hoặc streaming platform nếu phiên bản đầu chưa có yêu cầu và workload tương ứng.

### 3.6. Requirements traceability matrix

Liên kết yêu cầu với thành phần, test và bằng chứng nghiệm thu:

| Requirement ID | Yêu cầu | Thành phần | Cách kiểm tra |
|---|---|---|---|
| FR-01 | Tạo đơn hàng | API Gateway, Lambda, DynamoDB | API integration/E2E test |
| FR-02 | Chỉ đọc đơn thuộc tenant | Cognito authorizer, Lambda, data access layer | Negative authorization test |
| FR-03 | Xử lý fulfillment async | DynamoDB Streams, EventBridge, SQS, worker | Event flow integration test |
| NFR-01 | p95 dưới 400 ms | API, Lambda, DynamoDB | Load test và CloudWatch |
| NFR-02 | RPO 15 phút | DynamoDB PITR/backup | Restore exercise |
| NFR-03 | Audit thay đổi cấu hình | CloudTrail | Kiểm tra trail/event coverage |

Ma trận này giúp reviewer thấy yêu cầu đã được thiết kế và kiểm chứng ở đâu.

## 4. Ghi giả định, ràng buộc và rủi ro

### 4.1. Assumptions

Giả định là điều đang tạm coi đúng để có thể thiết kế. Ví dụ:

- 10.000 người dùng hoạt động mỗi tháng.
- Phần lớn request là đọc trạng thái; ghi đơn chiếm tỷ lệ nhỏ hơn.
- Thanh toán được xử lý qua một nhà cung cấp bên ngoài.
- Người dùng truy cập chủ yếu từ Việt Nam.
- Mỗi đơn có payload nhỏ và file đính kèm lưu riêng trong S3.

Mỗi giả định cần có owner và cách xác minh. Nếu giả định sai, cần đánh giá tác động đến kiến trúc và chi phí.

### 4.2. Constraints

Ràng buộc có thể là:

- Phải dùng một Region cụ thể do data residency.
- Phải tích hợp hệ thống ERP hiện tại.
- Ngân sách tối đa theo tháng.
- Deadline cố định.
- Đội vận hành chỉ hỗ trợ một số runtime/ngôn ngữ.
- Dữ liệu phải được mã hóa bằng customer-managed KMS key.
- Một số dịch vụ không được phép dùng theo policy tổ chức.

Không xem ràng buộc là chi tiết nhỏ. Một yêu cầu về network isolation có thể làm thay đổi lựa chọn compute, endpoint, NAT và chi phí.

### 4.3. Dependency

Liệt kê dependency nội bộ và bên ngoài:

- Identity provider.
- Payment gateway.
- DNS/domain.
- ERP hoặc CRM.
- Email/SMS provider.
- Data source và migration tool.
- CI/CD platform.
- KMS key và account baseline.

Ghi rõ SLA, quota, timeout, authentication, retry và phương án khi dependency không sẵn sàng.

### 4.4. Risk register

| Rủi ro | Xác suất/tác động | Giảm thiểu |
|---|---|---|
| Traffic peak cao hơn dự báo | Trung bình/cao | Load test, quota review, autoscaling |
| Payment provider chậm | Cao/cao | Timeout, queue, retry có giới hạn, idempotency |
| IAM policy sai | Trung bình/cao | IaC policy test, negative test, CloudTrail |
| Dữ liệu test chứa PII | Thấp/cao | Synthetic/masked data, account isolation |
| Chi phí NAT hoặc log vượt dự toán | Trung bình/trung bình | Cost model, tags, budgets, review |
| Restore lâu hơn RTO | Trung bình/cao | Restore exercise và runbook |

Đánh giá rủi ro cần gắn với hành động và người chịu trách nhiệm.

## 5. Mô hình hóa workload trước khi chọn dịch vụ

### 5.1. User và request profile

Ước tính:

- Monthly active users (MAU).
- Daily active users (DAU).
- Số session mỗi người.
- Request mỗi session.
- Tỷ lệ read/write.
- Request trung bình và peak mỗi giây.
- Kích thước payload.
- Tỷ lệ lỗi và retry.

Không lấy số người dùng đăng ký làm số người dùng đồng thời. Cần mô hình hành vi và thời điểm cao điểm.

### 5.2. Tính request volume

Ví dụ có 10.000 MAU, mỗi người tạo trung bình 120 request trong một tháng:

\[
10.000 \times 120 = 1.200.000\ \text{requests/month}
\]

Nếu có 100.000 đơn/tháng và mỗi đơn phát sinh ba event nghiệp vụ:

\[
100.000 \times 3 = 300.000\ \text{events/month}
\]

Các con số cần được kiểm chứng bằng analytics hoặc thử nghiệm. Khi dự báo peak, phân bố request theo giờ/ngày quan trọng hơn phép chia trung bình cho cả tháng.

### 5.3. Ước tính concurrency

Với workload request/response, có thể dùng Little's Law để ước tính concurrency trung bình:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số request đang xử lý trung bình.
- \(\lambda\): tốc độ request đến, tính bằng request/giây.
- \(W\): thời gian xử lý trung bình, tính bằng giây.

Nếu hệ thống nhận 50 request/giây và thời gian xử lý trung bình 0,2 giây:

\[
L = 50 \times 0,2 = 10
\]

Concurrency trung bình khoảng 10 request. Peak concurrency có thể cao hơn nhiều khi traffic burst hoặc latency tăng; phải dùng load test để xác nhận.

### 5.4. Data profile

Xác định:

- Kích thước record.
- Số record mới mỗi ngày.
- Tốc độ tăng dữ liệu.
- Retention online và archive.
- Tỷ lệ đọc/ghi.
- Query pattern và access pattern.
- Data transfer giữa Region/AZ hoặc ra Internet.
- Dữ liệu cần backup và thời gian restore.

Ví dụ, 100.000 đơn/tháng, mỗi order record trung bình 3 KB, chưa tính index và metadata:

\[
100.000 \times 3\ \text{KB} = 300\ \text{MB/month}
\]

Nếu lưu thêm event, audit, index và bản sao backup, dung lượng thực tế lớn hơn. Đừng dùng kích thước record logic làm dung lượng storage cuối cùng mà không tính overhead và bản sao.

### 5.5. Peak và growth factor

Tạo ít nhất ba mức:

| Kịch bản | Mục đích |
|---|---|
| Baseline | Tải trung bình hiện tại |
| Peak | Tải cao điểm theo ngày/chiến dịch |
| Growth | Tăng người dùng và dữ liệu trong 6–12 tháng |

Ví dụ peak traffic gấp 5 lần trung bình trong một giờ. Growth scenario có thể tăng request gấp 3 lần sau 12 tháng. Các hệ số phải dựa trên dữ liệu hoặc giả định được stakeholder chấp nhận.

### 5.6. Workload profile worksheet

| Thuộc tính | Giá trị ví dụ | Cách xác minh |
|---|---:|---|
| MAU | 10.000 | Product analytics |
| Request/tháng | 1,2 triệu | API analytics |
| Order/tháng | 100.000 | Business forecast |
| Peak RPS | 100 | Load test/traffic model |
| Payload API trung bình | 8 KB | Request sampling |
| Order record | 3 KB | Schema estimate |
| File đính kèm | 200 GB/tháng storage | Product usage forecast |
| Retention online | 12 tháng | Business/legal requirement |
| RTO | 2 giờ | Business impact analysis |
| RPO | 15 phút | Data loss tolerance |

Đây là workload minh họa để thực hành, không phải số liệu chuẩn cho mọi dự án.

## 6. Chọn Region, Availability Zones và network

### 6.1. Chọn Region

Đánh giá:

- Người dùng ở đâu và latency mục tiêu.
- Data residency và yêu cầu pháp lý.
- Dịch vụ cần dùng có sẵn trong Region không.
- Giá dịch vụ và data transfer.
- Kết nối tới hệ thống on-premises hoặc đối tác.
- Chiến lược DR và khả năng vận hành.

Không chọn Region chỉ vì một dịch vụ đơn lẻ rẻ hơn. Tổng thể gồm compute, database, storage, network, support và dữ liệu ra/vào Region.

### 6.2. Availability Zones

Một kiến trúc production thường trải workload qua nhiều Availability Zones để giảm rủi ro lỗi một AZ. Cần xác định:

- Subnet public/private theo AZ.
- Load balancer hoặc managed service placement.
- Database replication/failover.
- NAT Gateway hoặc VPC endpoint theo thiết kế.
- Cross-AZ data transfer và tác động chi phí.

Multi-AZ tăng khả năng sẵn sàng nhưng có thể tăng chi phí compute, storage, replication và network. Cần gắn lựa chọn với availability target.

### 6.3. VPC và subnet

Một VPC có thể chia:

- Public subnets cho load balancer hoặc NAT Gateway theo kiến trúc.
- Private application subnets cho compute cần truy cập tài nguyên nội bộ.
- Isolated/database subnets cho RDS/Aurora hoặc tài nguyên không cần Internet route trực tiếp.

Không đặt database vào public subnet chỉ để tiện kết nối. Dùng security group theo nguồn và port cần thiết, NACL theo chính sách tổ chức và route table tối thiểu.

### 6.4. NAT Gateway và VPC endpoints

Nếu workload trong private subnet cần outbound Internet, NAT Gateway là một lựa chọn. Tuy nhiên, NAT Gateway có phí theo giờ và dữ liệu xử lý; lưu lượng qua nhiều AZ hoặc đi sai route có thể làm chi phí tăng.

Với AWS service, cân nhắc VPC endpoints:

- Gateway endpoint cho S3 và DynamoDB.
- Interface endpoint cho các service hỗ trợ PrivateLink.

So sánh chi phí endpoint theo AZ, số lượng service, NAT processing và data transfer. Không mặc định VPC endpoint luôn rẻ hơn; hãy mô hình hóa lưu lượng thực tế.

### 6.5. Network diagram

Sơ đồ network cần thể hiện:

- VPC CIDR.
- Availability Zones.
- Public/private/isolated subnets.
- Internet Gateway, NAT Gateway, VPC endpoints.
- Security group boundary.
- Load balancer và compute.
- Database và đường kết nối.
- VPN/Direct Connect nếu có.

Sơ đồ chỉ ghi “VPC” mà không thể hiện subnet, route và trust boundary thường chưa đủ để review bảo mật.

## 7. Chọn dịch vụ AWS theo yêu cầu

### 7.1. Compute

| Nhu cầu | Dịch vụ có thể chọn | Câu hỏi quyết định |
|---|---|---|
| Event/API ngắn, tự động scale | AWS Lambda | Thời gian chạy, runtime, concurrency, dependency |
| Container không quản lý server | Amazon ECS với Fargate | Workload liên tục, task size, networking |
| Container cần EC2 control | Amazon ECS on EC2 | Có cần tối ưu node, GPU hoặc daemon không? |
| Kubernetes ecosystem | Amazon EKS | Có yêu cầu Kubernetes và năng lực vận hành không? |
| VM/legacy software | Amazon EC2 | OS, license, instance family và patching |

Chọn compute theo execution model, latency, workload duration, scaling, portability và vận hành. Không dùng Lambda chỉ vì từ khóa serverless nếu workload dài hạn hoặc có yêu cầu runtime không phù hợp.

### 7.2. Storage

| Loại dữ liệu | Dịch vụ | Cân nhắc |
|---|---|---|
| Object, file upload, archive | Amazon S3 | Storage class, request, lifecycle, retrieval, replication |
| Shared POSIX file system | Amazon EFS | Throughput, storage mode, mount target theo AZ |
| Block storage cho EC2 | Amazon EBS | Volume type, IOPS, throughput, snapshot |
| Cache/in-memory | ElastiCache | Memory size, node count, replication, backup |

Tách metadata trong database khỏi nội dung file lớn. Dùng S3 cho object thay vì lưu blob lớn trong database nếu access pattern phù hợp.

### 7.3. Database

| Access pattern | Dịch vụ | Khi phù hợp |
|---|---|---|
| Key-value/document, access pattern rõ | DynamoDB | Scale lớn, latency thấp, managed |
| Relational, SQL, transaction và join | RDS/Aurora | Quan hệ dữ liệu và truy vấn SQL |
| Cache/session | ElastiCache | Dữ liệu nóng, giảm tải database |
| Search/full-text | OpenSearch Service | Search và analytics phù hợp |
| Time-series | Timestream hoặc lựa chọn time-series phù hợp | Telemetry theo thời gian |

Không chọn database theo xu hướng. Hãy viết query pattern trước: truy vấn theo khóa nào, sort/filter ra sao, transaction boundary và consistency cần mức nào.

### 7.4. Integration và messaging

| Nhu cầu | Dịch vụ |
|---|---|
| Queue và decoupling | Amazon SQS |
| Pub/sub và event routing | Amazon EventBridge |
| Streaming throughput cao | Amazon Kinesis Data Streams |
| Notification fan-out đơn giản | Amazon SNS |
| Workflow orchestration | AWS Step Functions |
| Data delivery tới S3/analytics | Amazon Data Firehose |

Chọn theo semantics: queue, event bus, stream và workflow giải quyết các vấn đề khác nhau. Xác định delivery guarantee, ordering, retry, DLQ, replay và idempotency.

### 7.5. Identity và security

Các thành phần thường gặp:

- IAM roles cho workload và người vận hành.
- Amazon Cognito hoặc identity provider phù hợp cho user authentication.
- AWS KMS cho encryption key.
- AWS Secrets Manager hoặc Systems Manager Parameter Store cho secret/config.
- AWS WAF và Shield theo nhu cầu bảo vệ endpoint.
- Security groups, VPC endpoints và network controls.
- CloudTrail, Config, GuardDuty và Security Hub theo mức độ quản trị.

Tách authentication khỏi authorization. Đăng nhập thành công không có nghĩa người dùng được phép truy cập mọi record; kiểm tra quyền ở từng resource và tenant boundary.

### 7.6. Observability và operations

Thiết kế từ đầu:

- CloudWatch Logs, Metrics, Alarms và Dashboards.
- AWS X-Ray hoặc OpenTelemetry.
- CloudTrail và AWS Config.
- Runbook, on-call ownership và alert routing.
- Backup, restore và DR test.
- CI/CD và IaC.

Observability là một phần của kiến trúc, không phải công việc bổ sung sau khi deploy.

## 8. Cách vẽ sơ đồ kiến trúc

### 8.1. Sơ đồ context

Sơ đồ context cho biết hệ thống tương tác với ai và với hệ thống bên ngoài nào:

- Người dùng và vai trò.
- Hệ thống đang thiết kế.
- Identity provider.
- Payment/ERP/CRM.
- Nguồn dữ liệu.
- Operator hoặc admin.

Sơ đồ context nên đơn giản, giúp stakeholder hiểu ranh giới dự án mà không cần biết chi tiết dịch vụ.

### 8.2. Logical architecture

Logical architecture thể hiện các capability:

- Presentation/API.
- Business services.
- Data stores.
- Messaging/eventing.
- Identity/security.
- Observability.

Ở bước này có thể dùng tên capability trước khi quyết định dịch vụ cụ thể.

### 8.3. AWS deployment architecture

Deployment diagram ánh xạ capability sang dịch vụ và network:

- CloudFront, API Gateway, Lambda, ECS.
- S3, DynamoDB, RDS.
- SQS, EventBridge.
- VPC, subnet, security group, endpoint.
- IAM, KMS, Secrets Manager.
- CloudWatch, X-Ray, CloudTrail.

Đây là sơ đồ giúp reviewer kiểm tra placement, network path và service integration.

### 8.4. Data flow diagram

Thể hiện:

- Nguồn tạo dữ liệu.
- Protocol hoặc API.
- Thành phần xử lý.
- Data store.
- Consumer.
- Encryption boundary.
- Luồng dữ liệu nhạy cảm.
- Điểm validate, mask hoặc xóa dữ liệu.

Với dữ liệu cá nhân hoặc thanh toán, đánh dấu rõ nơi dữ liệu đi qua và nơi không được lưu.

### 8.5. Sequence diagram

Sequence diagram mô tả một use case theo thời gian. Ví dụ tạo đơn:

~~~mermaid
sequenceDiagram
    actor User
    participant API as API Gateway
    participant Auth as Cognito Authorizer
    participant Fn as Order Lambda
    participant DB as DynamoDB
    participant Stream as DynamoDB Streams
    participant Relay as Event Relay Lambda
    participant Bus as EventBridge
    participant Queue as SQS

    User->>API: POST /orders + token + idempotency key
    API->>Auth: Validate identity
    Auth-->>API: Claims
    API->>Fn: Invoke with request context
    Fn->>DB: Transaction write order + outbox
    DB-->>Fn: Commit
    Fn-->>API: 202 Accepted + orderId
    API-->>User: Order accepted
    DB->>Stream: New outbox record
    Stream->>Relay: Invoke relay
    Relay->>Bus: Publish OrderCreated
    Bus->>Queue: Route event
~~~

Sơ đồ cho thấy response đồng bộ có thể trả trước khi fulfillment hoàn tất. Hệ thống cần trạng thái order và API truy vấn để người dùng biết kết quả xử lý bất đồng bộ.

### 8.6. Quy ước sơ đồ

Một sơ đồ dễ review cần:

- Tên thành phần và vai trò.
- Mũi tên có hướng.
- Nhãn protocol hoặc loại message.
- Ranh giới account, Region, VPC và trust zone.
- Phân biệt synchronous và asynchronous.
- Thể hiện encryption hoặc authentication ở luồng quan trọng.
- Chú thích những thành phần tùy chọn.
- Có legend khi dùng màu/ký hiệu.

Không đưa secret, account credential hoặc dữ liệu cá nhân thật vào sơ đồ. Với kiến trúc lớn, tạo nhiều view thay vì nhồi tất cả thành phần vào một hình.

## 9. Ví dụ capstone: nền tảng quản lý đơn hàng

### 9.1. Bối cảnh dự án

Một doanh nghiệp có nhiều cửa hàng muốn xây nền tảng quản lý đơn hàng. Nhân viên tạo đơn tại quầy hoặc web; khách hàng xem trạng thái; hệ thống gửi đơn tới fulfillment và cập nhật kết quả thanh toán từ nhà cung cấp bên ngoài.

Mục tiêu:

- Tạo và truy vấn đơn hàng qua API.
- Xác thực người dùng và phân quyền theo tenant/cửa hàng.
- Xử lý fulfillment bất đồng bộ.
- Lưu file đính kèm và hóa đơn.
- Theo dõi trạng thái và lịch sử.
- Có audit, dashboard và cảnh báo.
- Có thể mở rộng theo traffic và phục hồi theo RPO/RTO đã chọn.

### 9.2. Functional requirements

| ID | Yêu cầu |
|---|---|
| FR-01 | Người dùng được xác thực có thể tạo đơn hàng |
| FR-02 | Hệ thống tạo order ID duy nhất và hỗ trợ idempotency |
| FR-03 | Người dùng chỉ truy cập dữ liệu thuộc tenant được cấp |
| FR-04 | Đơn mới phát event để fulfillment xử lý |
| FR-05 | Worker cập nhật trạng thái và ghi nhận lỗi |
| FR-06 | Người dùng xem được trạng thái đơn hàng |
| FR-07 | Người dùng tải hóa đơn/file từ đường dẫn được cấp quyền |
| FR-08 | Operator tra cứu đơn và xem audit trail |

### 9.3. Non-functional requirements minh họa

| Thuộc tính | Mục tiêu |
|---|---|
| MAU | 10.000 |
| API request | 1,2 triệu/tháng |
| Peak traffic | 100 request/giây trong chiến dịch |
| API p95 | Dưới 400 ms cho read/create acknowledgement |
| Availability | Mục tiêu 99,9% |
| RPO | 15 phút |
| RTO | 2 giờ |
| Data retention | 12 tháng online, archive theo chính sách |
| Security | TLS, encryption at rest, least privilege, tenant isolation |
| Operations | Dashboard, alert, trace, audit và runbook |

Các mục tiêu này cần được kiểm tra bằng load test, security test và restore exercise trước khi được xem là cam kết.

### 9.4. Sơ đồ kiến trúc tham khảo

~~~mermaid
flowchart TB
    U[Web / Mobile users] --> R53[Route 53]
    R53 --> CF[CloudFront]
    WAF[AWS WAF] -. protect edge .-> CF
    CF --> WEB[S3 static web]
    CF --> API[API Gateway HTTP API]
    API --> AUTH[Cognito authorizer]
    API --> L[Order Lambda]
    L --> DB[(DynamoDB Orders + Outbox)]
    DB --> STR[DynamoDB Streams]
    STR --> RELAY[Outbox Relay Lambda]
    RELAY --> EB[EventBridge custom bus]
    EB --> Q1[SQS Fulfillment]
    EB --> Q2[SQS Notifications]
    Q1 --> WORKER[Fulfillment Worker]
    Q2 --> NOTIFY[Notification Worker]
    WORKER --> DB
    NOTIFY --> EXT[Email/SMS provider]
    L --> S3[S3 invoices and attachments]
    L --> SEC[Secrets Manager]
    SEC --> EXT
    L -. logs metrics traces .-> OBS[CloudWatch / X-Ray]
    WORKER -. logs metrics traces .-> OBS
    AUD[CloudTrail] --> OBS
    KMS[AWS KMS] -. encryption keys .-> DB
    KMS -.-> S3
~~~

Đây là kiến trúc logic tham khảo. Trong thiết kế triển khai, cần bổ sung account boundary, Region/AZ, VPC placement nếu có resource private, IAM roles, KMS key policy, endpoint và network path. Không phải mọi Lambda đều cần nằm trong VPC; chỉ gắn VPC khi cần truy cập private resource hoặc network control tương ứng.

### 9.5. Vì sao chọn các dịch vụ này?

| Thành phần | Lý do lựa chọn | Khi nào xem xét phương án khác |
|---|---|---|
| CloudFront + S3 | Phục vụ web tĩnh và cache gần người dùng | Web SSR hoặc dynamic content có thể cần compute origin |
| AWS WAF | Lọc request theo managed/custom rules | Phụ thuộc threat model, traffic và policy |
| API Gateway HTTP API | API managed, tích hợp Lambda và authorizer | REST API nếu cần feature chỉ có ở REST API |
| Cognito | Quản lý user authentication và token | Dùng enterprise IdP nếu tổ chức đã có identity platform |
| Lambda | Xử lý request ngắn, event-driven | ECS/Fargate nếu workload dài hạn hoặc cần runtime liên tục |
| DynamoDB | Access pattern theo order ID/tenant, scale managed | Aurora/RDS nếu cần join, SQL và quan hệ phức tạp |
| DynamoDB Streams | Phát hiện thay đổi để relay outbox | Event bus/queue trực tiếp nếu chấp nhận semantics khác |
| EventBridge | Định tuyến domain event tới nhiều consumer | SNS hoặc Kinesis nếu semantics phù hợp hơn |
| SQS | Buffer và decouple worker | Kinesis nếu cần ordered stream throughput cao |
| S3 | Lưu invoice, attachment và object | EFS nếu cần shared file system |
| Secrets Manager | Quản lý credential cho external provider | Parameter Store cho cấu hình không nhạy cảm hoặc use case phù hợp |
| CloudWatch/X-Ray | Logs, metrics, alarms và trace | Kết hợp observability platform khác nếu có tiêu chuẩn tổ chức |

Lựa chọn dịch vụ dựa trên access pattern và yêu cầu, không dựa trên việc một dịch vụ có nhiều tính năng hơn.

### 9.6. Data model và access pattern

Trước khi thiết kế DynamoDB, xác định truy vấn:

- Lấy order theo order ID.
- Liệt kê đơn theo tenant và thời gian.
- Tìm đơn theo trạng thái.
- Tra cứu lịch sử event của một order.
- Idempotency lookup theo tenant và key.

Một bảng đơn giản có thể dùng partition key theo tenant/order và sort key cho loại record hoặc thời gian. Nếu có nhiều access pattern, thiết kế single-table hoặc multi-table dựa trên workload; không sao chép một schema relational sang DynamoDB mà không phân tích query.

Outbox record có thể được ghi cùng order trong một DynamoDB transaction. Relay đọc stream, phát event và consumer xử lý idempotent vì stream/consumer có thể retry hoặc phát lại record theo semantics dịch vụ. Cần có cơ chế theo dõi relay lag, lỗi và record chưa publish.

### 9.7. Security design

- User đăng nhập qua Cognito hoặc identity provider được chọn.
- API authorizer xác minh token.
- Lambda kiểm tra tenant claim và resource ownership.
- Execution role chỉ có quyền trên table, queue, bus và bucket cần thiết.
- KMS mã hóa dữ liệu và object theo yêu cầu.
- Secret external provider lưu trong Secrets Manager.
- S3 Block Public Access bật; file được cấp bằng presigned URL có thời hạn.
- CloudTrail ghi hoạt động control plane và data event cần audit.
- WAF bảo vệ endpoint công khai theo threat model.
- Log không ghi token, payment credential hoặc PII không cần thiết.

### 9.8. Reliability và recovery

- API ghi order và outbox trong transaction.
- Relay/worker có retry và idempotency.
- SQS có visibility timeout, redrive policy và DLQ.
- Consumer có timeout và giới hạn retry.
- DynamoDB backup/PITR theo RPO.
- S3 versioning/lifecycle khi cần.
- Multi-AZ được cung cấp bởi dịch vụ managed theo đặc tính dịch vụ; DR Region là quyết định riêng.
- Runbook có quy trình replay event và xử lý DLQ.
- Restore test đo RTO/RPO thực tế.

## 10. Thiết kế bảo mật và quyền truy cập

### 10.1. Identity và trust boundary

Phân biệt:

- Human identity: người dùng cuối, developer, operator.
- Workload identity: Lambda execution role, ECS task role, EC2 instance profile.
- Service principal: dịch vụ AWS assume role hoặc gọi resource theo policy.
- External identity: đối tác, IdP hoặc workload ngoài AWS.

Mỗi identity chỉ có quyền cần thiết. Không dùng access key dài hạn nhúng trong code hoặc container image.

### 10.2. Authentication và authorization

Authentication xác định danh tính; authorization quyết định danh tính đó được làm gì trên resource nào. Ví dụ Cognito xác thực user nhưng Lambda vẫn phải kiểm tra tenant ID và order ownership.

Test cả:

- User hợp lệ, tenant đúng.
- User hợp lệ nhưng tenant sai.
- Token hết hạn hoặc audience sai.
- Operator có quyền đọc nhưng không có quyền sửa.
- Workload role cố truy cập table/bucket ngoài phạm vi.

### 10.3. Encryption

Xác định:

- TLS cho client-to-service và service-to-service khi phù hợp.
- Encryption at rest cho database, object, queue và log.
- KMS key ownership, rotation và key policy.
- Backup/snapshot encryption.
- Secret rotation và access audit.

Nếu dùng customer-managed key, cost model cần tính key và request; kiến trúc cần xác định principal nào được encrypt/decrypt.

### 10.4. Network security

- Không mở database trực tiếp ra Internet.
- Security group chỉ cho phép nguồn/port cần thiết.
- Dùng private subnet cho workload cần truy cập private database.
- Dùng VPC endpoint khi có lợi về bảo mật/chi phí.
- Kiểm tra outbound egress và DNS.
- Phân tách account/environment theo mức độ rủi ro.

### 10.5. Audit và compliance

CloudTrail, AWS Config và các dịch vụ security có thể hỗ trợ audit. Xác định event nào cần ghi, nơi lưu, retention, quyền truy cập và quy trình phản ứng. Không tuyên bố hệ thống “compliant” chỉ vì đã bật một dịch vụ; compliance cần đối chiếu yêu cầu kiểm soát và bằng chứng thực tế.

## 11. Reliability, availability và disaster recovery

### 11.1. Thiết kế failure mode

Liệt kê dependency và điều gì xảy ra khi dependency lỗi:

| Dependency | Failure mode | Biện pháp |
|---|---|---|
| Identity provider | Token không xác thực được | Graceful error, monitoring, provider fallback nếu yêu cầu |
| Database | Timeout/throttling | Retry có giới hạn, backoff, circuit breaker |
| Queue consumer | Worker dừng | Queue buffer, DLQ, alarm |
| Payment provider | API chậm/5xx | Timeout, idempotency, reconciliation |
| Notification provider | Gửi thất bại | Retry, DLQ, trạng thái delivery |
| Region | Không truy cập được | DR strategy, backup/replication, failover runbook |

### 11.2. Retry và idempotency

Retry giúp phục hồi lỗi tạm thời nhưng có thể tạo duplicate. Mỗi operation có side effect cần xác định idempotency boundary. Dùng exponential backoff với jitter, giới hạn attempts và DLQ hoặc failure destination.

Không retry lỗi permanent như validation hoặc authorization. Retry phải có timeout tổng và không vượt thời gian xử lý mà caller chấp nhận.

### 11.3. Availability Zones

Dùng nhiều AZ cho thành phần cần high availability. Xác định managed service đã cung cấp replication/failover ở cấp nào và ứng dụng phải làm gì khi endpoint đổi hoặc connection bị reset.

Multi-AZ trong một Region không bảo vệ khỏi lỗi toàn Region, lỗi dữ liệu logic hoặc thao tác xóa nhầm. Cần backup và DR phù hợp.

### 11.4. Backup và restore

Thiết kế:

- Backup frequency.
- Retention.
- Encryption.
- Account/Region destination.
- Access control.
- Restore procedure.
- Validation sau restore.

Backup chỉ có giá trị khi restore được. Đưa restore exercise vào lịch vận hành và ghi nhận RTO/RPO thực tế.

### 11.5. Chọn DR strategy

| Strategy | Mô tả | Chi phí/độ phức tạp |
|---|---|---|
| Backup and restore | Khôi phục từ backup khi có sự cố | Thấp hơn, RTO thường dài hơn |
| Pilot light | Giữ một phần hạ tầng tối thiểu ở Region dự phòng | Trung bình |
| Warm standby | Môi trường dự phòng chạy ở công suất thấp | Cao hơn, RTO ngắn hơn |
| Multi-site active/active | Nhiều Region phục vụ đồng thời | Cao và phức tạp nhất |

Chọn theo business impact, RTO/RPO, data replication, consistency và ngân sách. Không triển khai active-active chỉ để có sơ đồ “resilient” nếu business không cần.

## 12. Observability và vận hành

### 12.1. Logs, metrics và traces

Mỗi request/event nên có:

- request ID hoặc message ID.
- correlation ID.
- trace context.
- service/environment.
- deployment version.
- outcome/error code.
- duration.

CloudWatch Logs hỗ trợ tìm kiếm và truy vấn; CloudWatch Metrics/Alarms phát hiện xu hướng; X-Ray/OpenTelemetry hỗ trợ phân tích dependency. CloudTrail bổ sung audit event.

### 12.2. Dashboard và alarm

Dashboard tối thiểu:

- API traffic, 4xx/5xx, p95 latency.
- Lambda errors, duration, throttles, concurrency.
- DynamoDB throttling và consumed capacity.
- SQS queue depth, oldest message age và DLQ count.
- Business success/failure count.
- Cost trend và budget status.

Mỗi alarm cần owner, threshold, runbook và hành động. Không tạo alarm không có người xử lý.

### 12.3. Deployment và rollback

Infrastructure as Code giúp tạo lại môi trường nhất quán. CI/CD cần kiểm tra unit, integration, IaC security, deployment và smoke test.

Chọn rolling, canary hoặc blue/green theo workload. Database migration cần backward compatibility; rollback code không tự rollback dữ liệu. Dùng expand-and-contract migration khi có thể.

### 12.4. Runbook

Runbook ghi:

- Triệu chứng và alarm.
- Cách xác định scope.
- Dashboard/log query/trace link.
- Các bước chẩn đoán.
- Cách rollback hoặc failover.
- Cách xử lý DLQ/replay.
- Người chịu trách nhiệm và escalation path.

Runbook cần được kiểm tra trong game day hoặc incident simulation.

## 13. Ước tính chi phí dự án trên AWS

### 13.1. Nguyên tắc cost estimate

Ước tính chi phí không phải cộng giá của các dịch vụ đã chọn một cách sơ sài. Cần chuyển workload thành đơn vị tính phí cho từng service, chọn Region, xác định cấu hình, tính thời gian sử dụng và mô hình tăng trưởng.

Một estimate có thể review cần nêu:

- Region và currency.
- Khoảng thời gian ước tính, thường là tháng và năm.
- Workload assumptions.
- Dịch vụ và cấu hình.
- Đơn vị tính phí và số lượng.
- Giá đơn vị tra từ AWS Pricing Calculator.
- Data transfer và request phụ trợ.
- Môi trường dev/test/staging/prod.
- Backup, log retention và support.
- Các mục chưa xác định và mức độ tin cậy.

Giá AWS thay đổi theo Region, thời điểm, service tier và lựa chọn. Dùng AWS Pricing Calculator với Region thực tế để lấy giá hiện hành; không dùng con số cũ trong slide hoặc bài viết làm báo giá.

### 13.2. Các nhóm chi phí

| Nhóm | Ví dụ chi phí |
|---|---|
| Compute | Lambda requests/GB-seconds, ECS task hours, EC2 instance hours |
| API/edge | API Gateway requests, CloudFront requests/data transfer, WAF |
| Database | Read/write capacity, storage, backup, I/O, instance hours |
| Storage | S3 storage class, requests, retrieval, replication |
| Messaging | SQS requests, EventBridge events, Kinesis capacity |
| Network | NAT Gateway hours/GB, VPC endpoints, data transfer, load balancer |
| Security | KMS keys/requests, Secrets Manager secrets/API calls, WAF |
| Observability | Logs ingestion/storage/query, metrics, alarms, traces |
| Backup/DR | Snapshots, backup storage, cross-Region replication, standby capacity |
| Support/operations | AWS Support plan, third-party tools, staff effort |

### 13.3. Quy trình dùng AWS Pricing Calculator

1. Chọn AWS Pricing Calculator và tạo estimate mới.
2. Chọn Region của workload.
3. Thêm từng AWS service trong kiến trúc.
4. Chọn model pricing phù hợp: On-Demand, Savings Plans, Reserved Instances hoặc option khác nếu workload đủ ổn định.
5. Nhập cấu hình và lượng sử dụng theo workload profile.
6. Tính data transfer, request, backup, storage và monitoring.
7. Tạo các nhóm estimate theo môi trường hoặc theo business unit nếu cần.
8. Lưu giả định, xuất estimate và review với owner.
9. Cập nhật estimate khi workload hoặc kiến trúc thay đổi.

Calculator hỗ trợ lập kế hoạch; hóa đơn thực tế có thể khác do traffic, retry, burst, free tier eligibility, discount, tax, support và usage phát sinh.

### 13.4. Xác định đơn vị tính phí theo service

| Service | Đầu vào cần mô hình hóa |
|---|---|
| API Gateway | Số request, loại API, data transfer, cache nếu dùng |
| Lambda | Invocations, memory, duration, architecture, provisioned concurrency |
| DynamoDB | Read/write request units hoặc capacity, item size, storage, backup, streams |
| SQS | Request units, payload size, send/receive/delete, long polling, batch |
| EventBridge | Số event, event size, bus/rule và feature được dùng |
| S3 | GB-month theo storage class, PUT/GET/LIST, retrieval, lifecycle, replication |
| CloudFront | Data transfer out, request count, cache hit ratio, origin traffic |
| WAF | Web ACL, rule/group, request inspected |
| CloudWatch | Log ingestion, storage, query scan, custom metrics, alarms |
| X-Ray | Trace/segment volume và retrieval theo pricing model |
| KMS | Key type/count và API requests |
| Secrets Manager | Số secret, API calls và rotation phụ thuộc cấu hình |
| NAT Gateway | Số gateway-hour và GB processed |
| VPC endpoints | Endpoint-hour, AZ và data processing theo loại endpoint |

Đọc pricing dimension của từng dịch vụ. Ví dụ SQS tính theo request unit, một message lớn có thể tiêu thụ nhiều request units; không dùng số message làm đại diện chính xác nếu chưa tính payload và batching.

### 13.5. Tính Lambda

Lambda thường có hai nhóm đầu vào chính:

- Số lần invocation.
- Compute duration theo memory allocation và thời gian chạy.

Ví dụ workload có 1,5 triệu invocation/tháng, memory 512 MB và average duration 200 ms:

\[
1.500.000 \times 0,2\ \text{s} \times 0,5\ \text{GB}
= 150.000\ \text{GB-seconds}
\]

Đây là compute usage trước khi áp dụng pricing/free tier/discount phù hợp. Cần cộng request charge và các feature riêng như provisioned concurrency nếu sử dụng. Với Lambda chạy trong VPC, tính thêm NAT hoặc VPC endpoint nếu kiến trúc yêu cầu.

### 13.6. Tính storage

Với S3:

\[
\text{Storage GB-month}
= \text{Dung lượng trung bình lưu trong tháng}
\]

Ví dụ lưu 200 GB trung bình trong một tháng là khoảng 200 GB-month, chưa tính version, replication, backup và object tăng trong tháng. Tính riêng PUT/GET/LIST, retrieval, lifecycle transition và data transfer.

Với database, tách:

- Table/database storage.
- Index hoặc replica.
- Backup/snapshot.
- Read/write request hoặc instance hours.
- I/O và data transfer nếu pricing model có.

### 13.7. Tính network

Network là nhóm dễ bị bỏ sót:

- Data transfer out ra Internet.
- Data transfer giữa AZ.
- Data transfer liên Region.
- NAT Gateway processing.
- VPC endpoint processing.
- Load balancer hours và processed bytes.
- CloudFront origin fetch và cache hit ratio.

Ước lượng data flow trên sơ đồ: bao nhiêu GB từ client vào, từ service sang service, từ AZ này sang AZ khác và từ Region ra Internet. Không mặc định mọi traffic nội bộ đều miễn phí.

### 13.8. Tính observability

Ước tính:

- GB log ingestion mỗi ngày.
- Số ngày retention.
- Tỷ lệ log verbose.
- Số custom metric và dimensions.
- Số alarm.
- Tỷ lệ trace sampling.
- Số lần truy vấn Logs Insights và lượng dữ liệu scan.
- CloudTrail data event volume và retention.

Ví dụ, nếu ứng dụng tạo 10 GB log/tháng và giữ 30 ngày, chi phí ingestion và storage phải được tính riêng. Nếu bật debug log làm volume tăng gấp 5 lần, estimate sẽ thay đổi đáng kể.

## 14. Worked example: cost model cho Order Platform

### 14.1. Giả định workload

Ví dụ dùng cùng workload profile ở phần kiến trúc:

- 10.000 MAU.
- 1,2 triệu API request/tháng.
- 100.000 đơn hàng/tháng.
- 300.000 domain events/tháng.
- 1,5 triệu Lambda invocations/tháng, memory trung bình 512 MB, duration 200 ms.
- DynamoDB ước tính 0,6 triệu write request units và 2,5 triệu read request units/tháng sau khi phân tích item size/access pattern.
- S3 giữ trung bình 200 GB, 500.000 PUT và 2 triệu GET/tháng.
- CloudFront phân phối 150 GB/tháng và 1,2 triệu request.
- CloudWatch ingest 10 GB log/tháng, retention 30 ngày.
- X-Ray/OTel trace sampling 5% request thành công, cộng toàn bộ error trace theo chính sách sampling.

Đây là giả định minh họa. Số request unit của DynamoDB phải tính từ kích thước item, consistency, transaction và access pattern; không lấy trực tiếp số record nghiệp vụ.

### 14.2. Bảng cost worksheet

| Thành phần | Workload đầu vào | Đơn vị cần định giá | Ghi chú |
|---|---|---|---|
| API Gateway HTTP API | 1,2 triệu request/tháng | Request count, data transfer | Chọn đúng loại API |
| Lambda | 1,5 triệu invocation; 150.000 GB-s | Requests và GB-seconds | Thêm provisioned concurrency nếu có |
| DynamoDB | 0,6 triệu WRU; 2,5 triệu RRU; storage | Request units, GB-month, backup | Kiểm tra item size và index |
| DynamoDB Streams | Outbox change records | Read request/stream usage theo model | Relay phải theo kịp stream |
| EventBridge | 300.000 events/tháng | Event ingestion và feature | Tính event size và bus |
| SQS | Events × send/receive/delete | Request units | Batch và payload ảnh hưởng số units |
| S3 | 200 GB-month; 500k PUT; 2m GET | Storage, request, retrieval | Chọn storage class |
| CloudFront | 150 GB out; 1,2m requests | Data transfer, requests | Cache hit ratio ảnh hưởng origin |
| WAF | 1 Web ACL, rule set, 1,2m requests | ACL/rule/request | Chọn managed rules cần thiết |
| CloudWatch | 10 GB logs, 30-day retention | Ingestion, storage, query, metrics | Tránh log noise |
| X-Ray/ADOT | 5% trace baseline + error traces | Trace/segment volume | Sampling cần được kiểm thử |
| KMS | Số key và API calls | Key-month, requests | Customer-managed keys nếu cần |
| Secrets Manager | 2 secrets, rotation theo lịch | Secret-month, API calls | Không lưu secret không cần thiết |
| Network | Egress, cross-AZ, NAT hoặc endpoints | GB, gateway-hour, endpoint-hour | Tính theo data flow |

### 14.3. Công thức tổng chi phí

Với từng dịch vụ:

\[
C_i = \sum_j Q_{ij} \times P_{ij}
\]

Trong đó:

- \(C_i\): chi phí dịch vụ i.
- \(Q_{ij}\): lượng sử dụng của pricing dimension j.
- \(P_{ij}\): giá đơn vị của dimension j tại Region và thời điểm estimate.

Tổng chi phí tháng:

\[
C_{\text{monthly}} =
\sum_i C_i + C_{\text{shared}} + C_{\text{support}}
\]

Chi phí shared có thể gồm network, logging account, security services và platform tooling. Cần tránh cộng trùng chi phí khi một hạng mục đã được tính trong estimate của service khác.

### 14.4. Phân môi trường

Không phải môi trường nào cũng cần cấu hình production:

| Environment | Cấu hình gợi ý | Cách kiểm soát chi phí |
|---|---|---|
| Dev | Tài nguyên nhỏ, dữ liệu synthetic | Tắt ngoài giờ, TTL và cleanup |
| Test | Tạo theo test run khi có thể | Ephemeral stack, auto-delete |
| Staging | Gần production nhưng tải thấp | Scale theo lịch, retention ngắn hơn |
| Production | Theo SLA và peak workload | Autoscaling, budget, alarm, tagging |

Nếu dev/test chạy liên tục, tổng chi phí môi trường ngoài production có thể đáng kể. Thêm chúng vào TCO thay vì chỉ dự toán production.

### 14.5. Ba kịch bản

Tạo ít nhất:

| Kịch bản | Giả định | Câu hỏi |
|---|---|---|
| Baseline | 1,2 triệu API requests/tháng | Chi phí vận hành bình thường? |
| Growth | 3 lần request và 2 lần storage | Khi tăng người dùng, service nào tăng tuyến tính? |
| Peak | 5 lần request trong thời gian ngắn | Có throttling, provisioned capacity hoặc queue backlog? |

Với serverless, chi phí thường tăng theo request/compute; với resource chạy liên tục như NAT Gateway, database instance hoặc ECS service, chi phí có phần cố định dù traffic thấp. Kịch bản cần tách fixed cost và variable cost.

### 14.6. Sensitivity analysis

Thay đổi từng giả định để tìm cost driver:

- Request tăng gấp đôi.
- Average Lambda duration tăng từ 200 ms lên 500 ms.
- Log volume tăng 5 lần.
- Cache hit ratio giảm.
- Storage retention tăng từ 12 lên 24 tháng.
- Bật multi-AZ hoặc cross-Region replication.
- NAT Gateway xử lý thêm 500 GB/tháng.

Xem biến nào làm tổng chi phí tăng mạnh nhất. Ưu tiên tối ưu driver lớn thay vì tập trung vào chi phí nhỏ ít ảnh hưởng.

### 14.7. TCO ngoài hóa đơn AWS

Total Cost of Ownership có thể bao gồm:

- AWS consumption.
- AWS Support plan.
- Phần mềm/observability/security bên thứ ba.
- Nhân sự vận hành và on-call.
- Chi phí migration và training.
- Chi phí kiểm thử DR và compliance.
- Chi phí phát triển, nâng cấp và decommission.

Capstone nên phân biệt monthly cloud run cost với project implementation cost và TCO theo năm.

## 15. FinOps: kiểm soát chi phí sau khi triển khai

### 15.1. Cost allocation tags

Đặt tag nhất quán cho tài nguyên:

~~~text
Project=order-platform
Environment=production
Owner=commerce-team
CostCenter=CC-104
DataClass=confidential
ManagedBy=cdk
~~~

Tag hỗ trợ phân bổ và truy vấn chi phí với điều kiện dịch vụ hỗ trợ cost allocation tags. Không phải mọi resource hoặc mọi loại phí đều có thể được phân bổ chính xác chỉ bằng tag; cần kiểm tra coverage.

### 15.2. AWS Budgets và cảnh báo

Thiết lập:

- Monthly budget tổng.
- Budget theo project/environment.
- Actual cost alert.
- Forecasted cost alert.
- Notification tới owner.

Budget alert là tín hiệu quản trị, không tự động chặn chi tiêu. Nếu cần automation, thiết kế action có kiểm soát và tránh tự động tắt resource production quan trọng.

### 15.3. Cost Explorer và Cost and Usage Report

Cost Explorer giúp xem xu hướng, service, account, Region và tag. Cost and Usage Report (CUR) hoặc dữ liệu billing tương ứng có thể dùng phân tích chi tiết hơn trong Athena/BI.

Review định kỳ:

- Actual vs forecast.
- Chi phí theo service và environment.
- Cost per order hoặc cost per active user.
- Data transfer và NAT.
- Log/metric/trace volume.
- Idle resource và commitment utilization.

### 15.4. Tối ưu sau khi có số liệu

Các hướng thường gặp:

- Giảm payload và request không cần.
- Cache dữ liệu đọc nhiều.
- Dùng storage class/lifecycle phù hợp.
- Tối ưu Lambda memory/duration sau benchmark.
- Batch message khi semantics cho phép.
- Tắt resource dev/test ngoài giờ.
- Điều chỉnh retention log.
- Đánh giá VPC endpoint và NAT usage.
- Dùng Savings Plans/Reserved Instances khi workload ổn định và có dữ liệu sử dụng.

Không mua commitment chỉ dựa trên forecast chưa được xác minh. Theo dõi usage thực tế và rủi ro thay đổi workload trước khi cam kết.

## 16. Architecture Decision Record

Một quyết định kiến trúc cần có bối cảnh và lý do, không chỉ ghi tên dịch vụ.

Mẫu ADR:

~~~markdown
# ADR-001: Chọn DynamoDB cho Order metadata

## Status
Proposed

## Context
Order API cần truy vấn theo tenant và order ID, ghi trạng thái thường xuyên,
traffic biến động và không cần join phức tạp ở giai đoạn đầu.

## Decision
Dùng DynamoDB với access pattern được xác định trước, on-demand capacity
trong giai đoạn đầu và backup/PITR theo RPO.

## Alternatives
- Aurora PostgreSQL
- RDS PostgreSQL

## Consequences
- Cần thiết kế partition/sort key và index theo query pattern.
- Không dùng truy vấn ad hoc như relational database.
- Chi phí phụ thuộc read/write request units, storage và backup.
- Nếu xuất hiện yêu cầu join/transaction phức tạp, đánh giá lại.

## Validation
- Load test access pattern.
- Integration test conditional write và transaction.
- Restore exercise.
- Cost estimate theo baseline/growth.
~~~

ADR có thể ở trạng thái Proposed, Accepted, Superseded hoặc Rejected. Khi yêu cầu thay đổi, ghi quyết định mới và liên kết tới ADR trước đó.

## 17. Kế hoạch triển khai capstone

### 17.1. Milestones

| Giai đoạn | Deliverables | Exit criteria |
|---|---|---|
| Discovery | Problem statement, stakeholder, scope | Business owner xác nhận |
| Requirements | FR, NFR, assumptions, risk register | Có acceptance criteria |
| Workload | Capacity/data profile | Số liệu và giả định có owner |
| Architecture | Context, deployment, data flow, sequence diagrams | Review security/reliability |
| Costing | Pricing Calculator estimate, scenarios | Finance/owner review |
| Prototype | Vertical slice trên AWS test account | Luồng quan trọng hoạt động |
| Validation | Unit/integration/E2E/load/security/restore test | NFR có bằng chứng |
| Handover | Runbook, dashboard, ADR, backlog | Operations nhận bàn giao |

### 17.2. Deliverables tối thiểu

Một capstone có thể review nên có:

1. Problem statement và business goals.
2. Stakeholder map và scope.
3. Functional/non-functional requirements.
4. Assumptions, constraints, dependencies và risk register.
5. Workload/capacity model.
6. Architecture context diagram.
7. AWS deployment/network diagram.
8. Data flow hoặc sequence diagram cho use case quan trọng.
9. Security design và IAM boundary.
10. Reliability/backup/DR strategy.
11. Observability plan và runbook outline.
12. Cost estimate theo Region và kịch bản.
13. ADR cho quyết định chính.
14. Test strategy và acceptance evidence.
15. Implementation roadmap.

### 17.3. Review gate

Trước khi bắt đầu triển khai:

- Business owner xác nhận mục tiêu và phạm vi.
- Security review identity, data flow và network.
- Architecture review kiểm tra service choice và failure mode.
- Operations review RTO/RPO, monitoring và runbook.
- Finance/FinOps review assumptions và cost model.

Review không nhằm tạo thủ tục hình thức. Mỗi gate phải phát hiện một nhóm rủi ro cụ thể.

## 18. Các lỗi thường gặp khi thiết kế dự án

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chọn dịch vụ trước khi hiểu yêu cầu | Kiến trúc không giải quyết đúng bài toán | Bắt đầu từ business outcome |
| NFR không đo được | Không thể nghiệm thu | Đặt percentile, workload và threshold |
| Không ghi assumptions | Estimate không thể kiểm tra | Lưu owner và cách xác minh |
| Không mô hình hóa peak | Throttling hoặc overprovision | Workload profile và load test |
| Sơ đồ chỉ có icon dịch vụ | Thiếu luồng dữ liệu và trust boundary | Vẽ context, deployment, data flow |
| Bỏ qua network cost | Hóa đơn vượt dự toán | Tính NAT, endpoint, cross-AZ và egress |
| Chỉ ước tính production | Thiếu chi phí dev/test/staging | Tính TCO đa môi trường |
| Chọn database theo sở thích | Query khó tối ưu, chi phí cao | Bắt đầu từ access pattern |
| Không thiết kế idempotency | Duplicate event tạo side effect | Retry policy và idempotent consumer |
| Không thử restore | RPO/RTO chỉ tồn tại trên giấy | Restore exercise |
| Không có observability | Khó xác định lỗi sau release | Log, metric, trace, audit và runbook |
| Dùng giá cũ | Cost estimate sai thời điểm | AWS Pricing Calculator theo Region |
| Không theo dõi sau deploy | Không phát hiện cost drift | Budgets, Cost Explorer và review định kỳ |

## 19. Bài tập thực hành

### Bài 1: Viết yêu cầu

Chọn một bài toán như quản lý đơn hàng, đặt lịch, IoT monitoring hoặc quản lý tài liệu. Viết:

- Một problem statement.
- Ba business goals.
- Tám functional requirements.
- Sáu non-functional requirements có số đo.
- Năm assumptions và ba constraints.
- Một risk register có owner.

### Bài 2: Mô hình hóa workload

Ước tính:

- MAU/DAU.
- Request mỗi tháng và peak RPS.
- Read/write ratio.
- Kích thước record và payload.
- Storage growth và retention.
- Event/message volume.
- RTO/RPO.

Ghi rõ nguồn của từng số liệu hoặc đánh dấu là giả định.

### Bài 3: Vẽ kiến trúc

Tạo:

- Context diagram.
- AWS deployment diagram.
- Data flow diagram.
- Sequence diagram cho một use case.

Mỗi sơ đồ phải có ranh giới account/Region/VPC phù hợp, protocol và hướng dữ liệu.

### Bài 4: So sánh dịch vụ

So sánh ít nhất hai lựa chọn cho compute và database. Ghi:

- Access pattern.
- Availability/scaling.
- Operational overhead.
- Security.
- Cost drivers.
- Trade-off.

Viết một ADR cho mỗi quyết định quan trọng.

### Bài 5: Ước tính chi phí

Tạo estimate trên AWS Pricing Calculator:

- Baseline.
- Growth 3x.
- Peak 5x.
- Production và non-production.
- Network, logs, backup và support.

Xuất bảng cost model, nêu rõ giá đơn vị lấy ở Region nào và ngày nào.

### Bài 6: Review kiến trúc

Đóng vai reviewer và trả lời:

- Yêu cầu nào chưa có thành phần đáp ứng?
- Luồng dữ liệu nhạy cảm nào chưa được bảo vệ?
- Thành phần nào là single point of failure?
- Retry có thể tạo duplicate ở đâu?
- RPO/RTO đã được kiểm chứng chưa?
- Cost driver lớn nhất là gì?
- Nếu traffic tăng 3 lần, phần nào cần thay đổi?

## 20. Checklist cuối cùng

### Requirements

- [ ] Problem statement và business outcome rõ ràng.
- [ ] Stakeholder và owner đã xác định.
- [ ] Functional requirements có acceptance criteria.
- [ ] NFR có metric, threshold và cách kiểm thử.
- [ ] Scope, assumptions, constraints và dependencies được ghi.

### Architecture

- [ ] Workload và data profile có cơ sở.
- [ ] Region/AZ được chọn có lý do.
- [ ] Sơ đồ context, deployment và data flow đầy đủ.
- [ ] Compute/database/storage được chọn theo access pattern.
- [ ] Network và trust boundary được thể hiện.
- [ ] IAM least privilege và encryption được thiết kế.
- [ ] Retry, idempotency, DLQ và failure mode được xác định.
- [ ] Backup, restore, RTO/RPO và DR được mô tả.
- [ ] Logs, metrics, traces, audit và runbook được xác định.

### Cost

- [ ] Estimate dùng Region và giá hiện hành.
- [ ] Compute, request, storage và database đã được tính.
- [ ] Network, NAT, endpoints và data transfer đã được tính.
- [ ] Logs, metrics, traces và CloudTrail đã được tính.
- [ ] Backup, DR và non-production được tính.
- [ ] Có baseline, growth và peak scenario.
- [ ] Có cost allocation tags, budget và owner.
- [ ] Assumptions và uncertainty được ghi rõ.

### Delivery

- [ ] ADR cho quyết định quan trọng.
- [ ] IaC và CI/CD strategy.
- [ ] Unit, integration, E2E và non-functional tests.
- [ ] Smoke test và rollback condition.
- [ ] Operations handover và restore exercise.

## 21. Kết luận

Thiết kế một dự án AWS bắt đầu từ vấn đề kinh doanh, stakeholder, phạm vi và yêu cầu có thể đo lường. Workload model giúp lượng hóa request, concurrency, dữ liệu, peak và tăng trưởng. Những đầu vào đó mới là cơ sở để chọn Region, AZ, compute, database, storage, messaging, network và security.

Sơ đồ kiến trúc cần thể hiện hệ thống tương tác với ai, thành phần nào xử lý dữ liệu, luồng đồng bộ/bất đồng bộ đi đâu và ranh giới bảo mật nằm ở đâu. Một sơ đồ deployment có giá trị khi reviewer có thể lần theo request, xác định quyền truy cập, failure mode và vị trí lưu dữ liệu. ADR giúp ghi lại lựa chọn, phương án thay thế và trade-off.

Cost estimate cần được xây từ workload và pricing dimensions của từng dịch vụ, dùng AWS Pricing Calculator tại Region mục tiêu. Hãy tính cả network, observability, backup, DR, môi trường non-production và support; sau đó kiểm tra baseline, growth và peak scenario. Khi kết hợp requirements traceability, kiến trúc có thể giải thích, cost model minh bạch và kế hoạch vận hành, capstone trở thành một đề xuất kỹ thuật có thể review, triển khai và nghiệm thu.

## 22. Tài liệu tham khảo chính thức

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [AWS Architecture Center](https://aws.amazon.com/architecture/)
- [AWS Cloud Adoption Framework](https://aws.amazon.com/cloud-adoption-framework/)
- [AWS Pricing Calculator](https://calculator.aws/)
- [AWS Cost Management](https://aws.amazon.com/aws-cost-management/)
- [AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)
- [AWS Cost and Usage Reports](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html)
- [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/overview/welcome.html)
- [AWS IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Amazon VPC documentation](https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html)
- [AWS Backup documentation](https://docs.aws.amazon.com/aws-backup/latest/devguide/whatisbackup.html)
- [AWS CloudFormation documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/intro.html)
