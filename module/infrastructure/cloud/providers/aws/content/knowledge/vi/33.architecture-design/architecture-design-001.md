# AWS Well-Architected Framework và sáu trụ cột

Khi thiết kế một workload trên AWS, lựa chọn dịch vụ phù hợp mới chỉ là một phần của công việc. Kiến trúc còn phải đáp ứng mục tiêu kinh doanh, bảo vệ dữ liệu, chịu được lỗi, duy trì hiệu năng, kiểm soát chi phí và sử dụng tài nguyên có trách nhiệm. Một quyết định tối ưu cho một mục tiêu có thể tạo ra vấn đề ở mục tiêu khác: thêm bản sao giúp tăng khả năng phục hồi nhưng làm tăng chi phí; mã hóa và kiểm tra sâu bảo vệ dữ liệu nhưng có thể tăng độ trễ; dùng dịch vụ tự quản lý cho phép kiểm soát chi tiết nhưng tăng khối lượng vận hành.

AWS Well-Architected Framework cung cấp một cách tiếp cận có cấu trúc để đánh giá các quyết định đó. Framework đặt ra những câu hỏi và best practices giúp nhóm kiến trúc nhận diện rủi ro, ghi lại trade-off và lên kế hoạch cải thiện trong suốt vòng đời workload. Framework không phải danh sách dịch vụ bắt buộc, một kiến trúc mẫu dùng cho mọi hệ thống hay một chứng nhận compliance.

Bài học tập trung vào sáu trụ cột của Cloud Workloads: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization và Sustainability. Nội dung cũng giới thiệu Cloud Foundations, phần nền tảng tổ chức được AWS bổ sung vào bản Framework cập nhật ngày 16-11-2026, cùng cách sử dụng AWS Well-Architected Tool để thực hiện review và theo dõi cải tiến.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích mục đích của AWS Well-Architected Framework và vai trò của sáu trụ cột.
- Phân biệt Cloud Foundations với Cloud Workloads trong cấu trúc Framework hiện hành.
- Chuyển yêu cầu kinh doanh thành tiêu chí kiến trúc có thể đo lường.
- Nhận diện các quyết định thiết kế cần đánh giá ở từng trụ cột.
- Phân tích trade-off giữa bảo mật, độ tin cậy, hiệu năng, chi phí, vận hành và tính bền vững.
- Thực hiện một Well-Architected review có phạm vi, bằng chứng, owner và improvement plan rõ ràng.
- Sử dụng AWS Well-Architected Tool, lenses, profiles, milestones và workload reports để theo dõi tiến độ.
- Áp dụng Framework vào một workload thương mại điện tử triển khai trên AWS.

## 1. AWS Well-Architected Framework là gì?

AWS Well-Architected Framework là tập hợp các nguyên tắc thiết kế, câu hỏi đánh giá và best practices giúp nhóm xây dựng, triển khai và vận hành workload trên AWS. Framework tạo ra ngôn ngữ chung để product owner, architect, developer, security engineer, SRE, operations và finance cùng thảo luận về chất lượng kiến trúc.

Framework giúp trả lời các câu hỏi như:

- Workload có thể tiếp tục cung cấp chức năng khi một Availability Zone hoặc thành phần bị lỗi không?
- Ai và dịch vụ nào được phép truy cập dữ liệu, và quyền đó được kiểm soát ra sao?
- Nhóm có phát hiện được vấn đề trước khi người dùng bị ảnh hưởng không?
- Hiệu năng có đáp ứng nhu cầu ở giờ cao điểm và khi tải thay đổi không?
- Chi phí của workload có tương xứng với giá trị kinh doanh không?
- Tài nguyên được cấp phát có được sử dụng hiệu quả trong suốt vòng đời không?

Review theo Framework là một cuộc trao đổi mang tính xây dựng về các quyết định kiến trúc. Đây không phải một cuộc audit hay cơ chế tự động chứng nhận workload tuân thủ mọi tiêu chuẩn. Review giúp tìm khoảng trống, hiểu lý do đằng sau quyết định và xác định hành động cải thiện.

### 1.1. Workload là gì?

Workload là tập hợp tài nguyên AWS, mã ứng dụng, dữ liệu, cấu hình và các thành phần liên quan tạo nên một ứng dụng hoặc dịch vụ phục vụ một mục tiêu kinh doanh. Ví dụ:

- Hệ thống thương mại điện tử gồm website, API, dịch vụ đặt hàng, thanh toán, cơ sở dữ liệu, hàng đợi và pipeline triển khai.
- Nền tảng xử lý dữ liệu gồm ingestion, lưu trữ, xử lý batch/stream, catalog, phân tích và dashboard.
- Dịch vụ nội bộ gồm ứng dụng, danh tính, tích hợp mạng doanh nghiệp, logging và cơ chế hỗ trợ.

Phạm vi workload nên đủ rõ để xác định owner, người dùng, ranh giới dữ liệu, dependency, môi trường, mục tiêu kinh doanh và tiêu chí vận hành. Nếu chọn phạm vi quá rộng, review khó đi sâu vào quyết định cụ thể. Nếu quá hẹp, các dependency quan trọng có thể bị bỏ qua.

### 1.2. Cấu trúc Framework cập nhật ngày 16-11-2026

Trong bản cập nhật ngày 16-11-2026, AWS hợp nhất nội dung sáu pillar whitepapers vào một nguồn Framework thống nhất, cập nhật nhiều best practices, bổ sung Cloud Foundations và mở rộng hướng dẫn về AI adoption, AI-driven operations và architecture reviews.

Framework hiện được trình bày thành hai phần:

| Phần | Phạm vi | Câu hỏi trọng tâm |
|---|---|---|
| Cloud Foundations | Năng lực nền tảng ở cấp tổ chức, account và shared services. | Tổ chức đã tạo được môi trường AWS có governance, identity, observability, security, networking và cost management nhất quán chưa? |
| Cloud Workloads | Thiết kế, xây dựng và vận hành từng workload. | Workload cụ thể có đáp ứng sáu trụ cột hay không? |

Cloud Foundations thường do cloud platform, foundation engineering hoặc cloud engineering team quản lý. Cloud Workloads thường do các nhóm sản phẩm và workload owner thiết kế, xây dựng và vận hành. Hai phần bổ trợ nhau: nền tảng tốt giúp workload kế thừa guardrails và shared services; workload review giúp phát hiện yêu cầu mới mà nền tảng cần hỗ trợ.

### 1.3. Bảy năng lực của Cloud Foundations

| Năng lực | Nội dung |
|---|---|
| Multi-account environment | Tổ chức AWS accounts và organizational units để tạo ranh giới cô lập, phân tách môi trường và áp dụng policy nhất quán. |
| Identity and access management | Tập trung quản lý danh tính, bảo vệ tài khoản đặc quyền và áp dụng least privilege. |
| Central observability management | Chuẩn hóa logs, metrics, traces và tổng hợp telemetry để có góc nhìn thống nhất trên toàn tổ chức. |
| Resource and inventory management | Chuẩn hóa tags, inventory, dependency, shared patterns và tự động hóa patching. |
| Security and compliance | Thiết lập emergency access, audit logging, threat detection, vulnerability management và forensic readiness. |
| Cloud financial management | Phân bổ chi phí, budgets, licensing, cost visibility và commitment strategies. |
| Networking and connectivity | Quản lý network topology, DNS, protection controls và kết nối giữa accounts, Regions, workloads và on-premises. |

Ví dụ, một tổ chức có thể dùng AWS Organizations và service control policies để quản trị account; IAM Identity Center để quản lý workforce access; account logging tập trung để thu thập CloudTrail; Amazon CloudWatch và Amazon OpenSearch Service để quan sát; AWS Config và Security Hub để phát hiện sai lệch; AWS Cost Explorer và Cost and Usage Reports để quản lý chi phí; Transit Gateway và Route 53 Resolver để quản lý kết nối.

Cloud Foundations không thay thế review từng workload. Một landing zone được cấu hình tốt vẫn có thể chứa ứng dụng thiết kế sai về dữ liệu, khả năng phục hồi hoặc hiệu năng.

## 2. Các nguyên tắc thiết kế chung trên AWS

Ngoài sáu trụ cột, Framework đưa ra các nguyên tắc chung giúp định hướng quyết định kiến trúc:

1. **Không phỏng đoán nhu cầu capacity:** đo tải, đặt ngưỡng và dùng scaling phù hợp thay vì cấp phát cố định theo dự đoán thiếu dữ liệu.
2. **Kiểm thử ở quy mô gần production:** tạo môi trường thử nghiệm đủ đại diện để đánh giá hành vi khi tải cao hoặc khi có lỗi.
3. **Tự động hóa để thử nghiệm kiến trúc:** dùng Infrastructure as Code, pipeline và môi trường có thể tái tạo để so sánh phương án và giảm thao tác thủ công.
4. **Xây dựng kiến trúc có thể tiến hóa:** ưu tiên quyết định có thể thay đổi, triển khai theo từng bước và giảm chi phí đảo ngược khi yêu cầu thay đổi.
5. **Dùng dữ liệu để dẫn dắt quyết định:** dựa trên latency, throughput, error rate, utilization, availability, chi phí và kết quả kinh doanh.
6. **Tổ chức game days:** mô phỏng sự cố và diễn tập quy trình vận hành để phát hiện khoảng trống trước khi sự cố thật xảy ra.

Các nguyên tắc này liên kết với nhau. Ví dụ, autoscaling cần telemetry đáng tin cậy; thử nghiệm ở quy mô production cần môi trường tự động tạo và hủy; game day cần runbook, người chịu trách nhiệm và tiêu chí thành công.

## 3. Sáu trụ cột của AWS Well-Architected Framework

| Trụ cột | Mục tiêu | Câu hỏi kiến trúc |
|---|---|---|
| Operational Excellence | Vận hành hiệu quả, quan sát được workload và liên tục cải thiện quy trình. | Nhóm có thể triển khai thay đổi, phát hiện vấn đề, phản ứng và học từ sự cố không? |
| Security | Bảo vệ dữ liệu, hệ thống và tài sản; kiểm soát truy cập, phát hiện và phản ứng với sự kiện. | Đúng danh tính có truy cập đúng tài nguyên, đúng điều kiện và có thể audit không? |
| Reliability | Workload thực hiện chức năng chính xác, nhất quán và phục hồi khi xảy ra lỗi. | Workload chịu được lỗi, thay đổi tải và phục hồi trong mục tiêu kinh doanh không? |
| Performance Efficiency | Dùng tài nguyên hiệu quả để đáp ứng yêu cầu hiệu năng khi nhu cầu và công nghệ thay đổi. | Kiến trúc có đáp ứng latency, throughput và capacity với lựa chọn tài nguyên phù hợp không? |
| Cost Optimization | Tạo giá trị kinh doanh ở mức chi phí phù hợp và loại bỏ lãng phí. | Nhóm biết chi phí đến từ đâu và đã chọn đúng dịch vụ, kích thước, mô hình giá chưa? |
| Sustainability | Giảm năng lượng, tài nguyên tiêu thụ và tác động môi trường của workload. | Mỗi đơn vị công việc có được hoàn thành với mức tài nguyên cần thiết và hiệu quả không? |

Không nên tối đa hóa riêng một trụ cột rồi mặc định toàn bộ kiến trúc đã tốt. Một hệ thống chạy nhiều bản sao ở nhiều Region có thể có độ sẵn sàng cao nhưng đắt và khó vận hành. Một hệ thống chọn tài nguyên rẻ nhất có thể không đáp ứng latency hoặc availability. Cần xác định mục tiêu kinh doanh, giới hạn bắt buộc và mức chấp nhận rủi ro trước khi quyết định.

## 4. Operational Excellence – Vận hành xuất sắc

Operational Excellence tập trung vào khả năng xây dựng phần mềm đúng cách, vận hành workload hiệu quả, hiểu tình trạng hệ thống và cải thiện liên tục để mang lại giá trị cho người dùng.

AWS tổ chức hướng dẫn của trụ cột này thành bốn hoạt động: Organization, Prepare, Operate và Evolve.

### 4.1. Tổ chức nhóm quanh kết quả kinh doanh

Nhóm phát triển và vận hành cần hiểu mục tiêu mà workload phục vụ, ví dụ tỷ lệ đặt hàng thành công, thời gian xử lý giao dịch, số người dùng được phục vụ hoặc thời gian khôi phục. Trách nhiệm cần rõ ràng giữa product owner, application team, platform team, security và on-call team.

Các thực hành nên áp dụng:

- Xác định owner cho từng workload và dependency quan trọng.
- Định nghĩa KPI kỹ thuật gắn với kết quả kinh doanh.
- Thiết lập quy trình change management và quyền quyết định khi có sự cố.
- Dùng managed services khi chúng giảm gánh nặng vận hành và đáp ứng yêu cầu.
- Ghi lại kiến thức vận hành để giảm phụ thuộc vào một cá nhân.

### 4.2. Prepare – Chuẩn bị trước production

Trước khi đưa workload vào production, cần xác định rủi ro, kiểm thử quy trình thay đổi và bảo đảm nhóm có khả năng hỗ trợ hệ thống.

Ví dụ:

- Dùng AWS CodePipeline, CodeBuild hoặc GitHub Actions để tự động hóa build/test/deploy.
- Dùng CloudFormation, AWS CDK hoặc Terraform để quản lý hạ tầng dưới dạng code.
- Áp dụng quality gates: unit test, integration test, security scan, policy validation và approval phù hợp.
- Dùng canary hoặc blue/green deployment để giảm blast radius.
- Chuẩn bị runbook, escalation path, dashboard và on-call rotation.
- Xác định service quota, dependency, backup và quy trình rollback trước khi release.

### 4.3. Operate – Vận hành và quan sát

Một workload cần tạo ra telemetry để nhóm hiểu điều gì đang xảy ra. Chỉ số nên gắn với hành vi người dùng và mục tiêu dịch vụ.

Ví dụ:

- Amazon CloudWatch metrics, logs, alarms và dashboards.
- AWS X-Ray hoặc OpenTelemetry để theo dõi request qua nhiều service.
- CloudTrail để audit hoạt động quản trị AWS.
- SLO, error budget, latency percentile, throughput, error rate và queue age.
- EventBridge, SNS, SQS hoặc Systems Manager Automation để điều phối phản ứng.

Tránh tạo quá nhiều alert không có hành động rõ ràng. Một cảnh báo hữu ích phải chỉ ra tác động, owner, điều kiện kích hoạt và bước xử lý tiếp theo.

### 4.4. Evolve – Học hỏi và cải thiện

Sau mỗi sự cố, deployment lỗi hoặc game day, nhóm cần tìm nguyên nhân hệ thống thay vì chỉ quy trách nhiệm cá nhân.

Các hoạt động gồm:

- Thực hiện post-incident review và ghi lại bài học.
- Đo change failure rate, MTTR và số lượng thao tác thủ công lặp lại.
- Tự động hóa các quy trình có kết quả và điều kiện rõ ràng.
- Cập nhật runbook, kiến trúc, dashboard và decision records.
- Đưa improvement items vào backlog có owner và deadline.

Ví dụ: nếu nhóm thường xuyên xử lý thủ công khi queue backlog tăng, hãy đánh giá autoscaling consumer, visibility timeout, dead-letter queue và cảnh báo theo age of oldest message.

## 5. Security – Bảo mật

Security tập trung bảo vệ dữ liệu, hệ thống và tài sản; bảo đảm đúng người và workload identity có quyền truy cập phù hợp; duy trì khả năng quan sát, bảo vệ và phản ứng khi có sự cố. Bảo mật cần được tích hợp trong thiết kế, phát triển, triển khai và vận hành.

AWS tổ chức nội dung trụ cột thành bốn vùng thực hành chính.

### 5.1. Security governance and operations

Tổ chức cần xác định control objectives, chính sách, trách nhiệm và quy trình phản ứng. Cần có khả năng phát hiện sự kiện, điều tra và phục hồi.

Ví dụ:

- AWS Organizations, service control policies và account separation.
- AWS CloudTrail, AWS Config và Security Hub.
- Amazon GuardDuty để phát hiện hành vi đáng ngờ.
- Amazon Inspector để phát hiện lỗ hổng.
- AWS Security Incident Response hoặc quy trình incident response nội bộ.
- Quy trình lưu evidence và thực hiện tabletop/game day.

### 5.2. Identity and access management

Mọi truy cập cần gắn với một danh tính và một bộ quyền được giới hạn theo nhiệm vụ.

Thực hành:

- Dùng IAM roles và temporary credentials cho workload thay vì access key dài hạn.
- Dùng IAM Identity Center hoặc federation cho workforce.
- Áp dụng least privilege, permission boundaries và separation of duties.
- Bảo vệ root user và tài khoản đặc quyền bằng MFA.
- Dùng IAM Access Analyzer để rà soát policy/trust relationship.
- Rà soát định kỳ quyền và loại bỏ credential không còn sử dụng.

Một ECS task cần đọc object từ S3 nên dùng task role giới hạn vào bucket/prefix cần thiết. Không nhúng access key của tài khoản quản trị vào biến môi trường hoặc source code.

### 5.3. Data protection

Dữ liệu cần được phân loại và bảo vệ trong toàn bộ vòng đời: tạo, truyền, lưu trữ, truy cập, sao lưu, chia sẻ và xóa.

Ví dụ:

- AWS KMS để quản lý encryption keys.
- TLS để bảo vệ dữ liệu truyền qua mạng.
- S3 Block Public Access, bucket policies và access points.
- Amazon Macie để phát hiện dữ liệu nhạy cảm trong S3.
- Backup, retention, lifecycle và kiểm soát truy cập vào bản sao lưu.
- Tokenization hoặc masking khi ứng dụng không cần dữ liệu gốc.

Không chỉ bật encryption rồi xem như hoàn tất. Cần quản lý key policy, rotation, quyền decrypt, backup và quy trình khôi phục.

### 5.4. Infrastructure and application protection

Bảo vệ cần được áp dụng theo nhiều lớp: account, network, compute, application và data.

Ví dụ:

- Security groups, network ACL, AWS Network Firewall và AWS WAF.
- Patch management bằng Systems Manager.
- Harden AMI/container image và kiểm tra dependency.
- Secure coding, code review, secret scanning và SAST/DAST.
- Kiểm soát pipeline triển khai và quyền của CI/CD role.
- Tách public subnet, private subnet và data subnet theo trust boundary phù hợp.

### 5.5. Shared Responsibility Model

AWS chịu trách nhiệm bảo vệ hạ tầng cloud mà AWS vận hành, bao gồm cơ sở vật lý, phần cứng, networking và lớp ảo hóa. Khách hàng chịu trách nhiệm bảo mật trong cloud theo dịch vụ đã chọn: dữ liệu, danh tính, cấu hình tài nguyên, ứng dụng và guest operating system khi sử dụng EC2.

Với EC2, khách hàng quản lý hệ điều hành, patch, application software và security group. Với dịch vụ managed như S3 hoặc DynamoDB, AWS quản lý nhiều thành phần hạ tầng hơn, nhưng khách hàng vẫn quản lý dữ liệu, quyền IAM, encryption options, backup và replication strategy.

Mức trách nhiệm thay đổi theo dịch vụ và mô hình triển khai. Architect cần đọc trách nhiệm cụ thể của từng dịch vụ trước khi thiết kế control.

## 6. Reliability – Độ tin cậy

Reliability là khả năng workload thực hiện đúng chức năng một cách nhất quán khi được kỳ vọng, trong suốt vòng đời. Trụ cột này tập trung vào resilience: khả năng phục hồi sau gián đoạn, đáp ứng thay đổi tải và giảm tác động của lỗi hoặc cấu hình sai.

AWS nhóm các best practices thành bốn vùng.

### 6.1. Foundations

Nền tảng phải hỗ trợ mục tiêu reliability của workload:

- Kiểm tra service quotas và giới hạn API.
- Thiết kế network topology và dependency.
- Chọn Region/AZ phù hợp yêu cầu business continuity.
- Xác định dependency vào dịch vụ bên ngoài và khả năng thay thế.
- Kiểm tra quyền, DNS, certificate và kết nối trước production.

### 6.2. Workload architecture

Thiết kế hệ thống để lỗi ở một thành phần không kéo theo toàn bộ workload.

Các kỹ thuật:

- Phân phối workload qua nhiều Availability Zones khi yêu cầu availability cần thiết.
- Dùng Elastic Load Balancing và Auto Scaling để phân phối tải và thay thế instance lỗi.
- Tách thành phần bằng SQS, EventBridge hoặc streaming service.
- Dùng retry có exponential backoff và jitter, timeout, circuit breaker và idempotency.
- Giới hạn blast radius bằng cell-based architecture hoặc fault isolation.
- Tránh single point of failure trong đường đi quan trọng.

Multi-AZ và multi-Region phục vụ mục tiêu khác nhau. Multi-AZ thường giúp chịu lỗi trong một Region; multi-Region có thể phục vụ disaster recovery, data residency hoặc yêu cầu latency toàn cầu nhưng tăng độ phức tạp và chi phí. Không nên triển khai multi-Region nếu RTO/RPO và tác động kinh doanh chưa yêu cầu.

### 6.3. Change management

Thay đổi cũng là nguồn gây lỗi. Cần theo dõi resource, điều chỉnh capacity và kiểm soát deployment.

Ví dụ:

- Monitor workload resource và dependency.
- Dùng autoscaling dựa trên metric phù hợp.
- Triển khai thay đổi theo từng giai đoạn.
- Kiểm tra compatibility và migration plan cho schema/database.
- Tự động rollback khi health check hoặc SLO vượt ngưỡng.

### 6.4. Failure management

Lỗi sẽ xảy ra; kiến trúc cần chuẩn bị để phát hiện, cô lập, phục hồi và học hỏi.

Thực hành:

- Backup dữ liệu và kiểm tra khả năng restore.
- Dùng fault isolation để hạn chế phạm vi sự cố.
- Thiết kế để chịu được lỗi component/AZ.
- Thử nghiệm failure scenario và recovery procedure.
- Lập kế hoạch disaster recovery dựa trên RTO và RPO.

RTO (Recovery Time Objective) là thời gian mục tiêu để khôi phục dịch vụ. RPO (Recovery Point Objective) là mức mất dữ liệu tối đa tính theo thời gian mà doanh nghiệp có thể chấp nhận. Backup tồn tại chưa đủ; cần kiểm thử restore và đo thời gian thực tế.

## 7. Performance Efficiency – Hiệu quả hiệu năng

Performance Efficiency tập trung vào việc sử dụng tài nguyên hiệu quả để đáp ứng yêu cầu hiệu năng và duy trì hiệu quả khi tải hoặc công nghệ thay đổi.

### 7.1. Xác định performance requirements

Bắt đầu bằng yêu cầu kinh doanh có thể đo lường:

- p95/p99 latency cho API quan trọng.
- Throughput hoặc transactions per second.
- Số người dùng đồng thời.
- Thời gian xử lý batch.
- Tỷ lệ lỗi và độ ổn định khi traffic tăng.
- Data freshness hoặc thời gian hoàn tất truy vấn.

Không tối ưu một con số kỹ thuật nếu nó không phản ánh trải nghiệm người dùng hoặc mục tiêu sản phẩm.

### 7.2. Chọn và cấu hình tài nguyên

Chọn dịch vụ theo access pattern và đặc tính workload:

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Compute tổng quát | EC2, ECS, EKS hoặc AWS Lambda theo mô hình vận hành và tải. |
| Container không muốn quản lý server | AWS Fargate. |
| Key-value/document access có quy mô lớn | Amazon DynamoDB. |
| Relational data và SQL transaction | Amazon RDS hoặc Amazon Aurora. |
| Object/file storage | Amazon S3 hoặc dịch vụ lưu trữ phù hợp. |
| Cache đọc nhiều | Amazon ElastiCache hoặc cache ở edge. |
| Nội dung phân phối toàn cầu | Amazon CloudFront. |
| Xử lý event và message | Amazon SQS, SNS, EventBridge hoặc streaming service. |

Ngoài loại dịch vụ, cần chọn đúng instance family, storage class, IOPS, network throughput, cache strategy và database index.

### 7.3. Monitor, test và improve

- Dùng CloudWatch metrics và dashboards để theo dõi latency, utilization và saturation.
- Load test theo traffic profile gần production.
- Profiling để xác định CPU, memory, query hoặc network bottleneck.
- Kiểm tra cache hit ratio và data access pattern.
- So sánh cấu hình bằng thử nghiệm có thể tái tạo.
- Review lại khi workload, traffic hoặc AWS service thay đổi.

Ví dụ, nếu p99 latency của trang sản phẩm tăng do database read load, hãy kiểm tra query plan, index, cache hit ratio và connection pool trước khi tăng kích thước database một cách mù quáng.

## 8. Cost Optimization – Tối ưu chi phí

Cost Optimization là quá trình liên tục nhằm đạt kết quả kinh doanh ở mức chi phí phù hợp. Mục tiêu không phải luôn chọn dịch vụ rẻ nhất, mà là đạt business value với mức chi phí thích hợp trong khi vẫn đáp ứng yêu cầu chức năng, bảo mật, reliability, performance và sustainability.

AWS nhóm nội dung trụ cột thành bốn vùng.

### 8.1. Effective Cloud Financial Management

Tổ chức cần biết ai chịu trách nhiệm về chi phí và workload cần đạt mức chi phí nào.

Thực hành:

- Xác định owner và cost allocation tags.
- Xây dựng budget và forecast.
- Kết hợp finance, engineering và product team.
- Đặt cost target theo workload hoặc đơn vị nghiệp vụ.
- Đánh giá business value trên mỗi đơn vị chi phí.

### 8.2. Expenditure and usage awareness

Không thể tối ưu khoản chi không được quan sát và phân bổ.

Công cụ và thực hành:

- AWS Cost Explorer để phân tích usage/cost.
- AWS Budgets để cảnh báo theo ngưỡng.
- Cost and Usage Reports để phân tích chi tiết.
- Cost allocation tags và cost categories để quy trách nhiệm.
- Theo dõi data transfer, NAT Gateway, idle resources, storage và log ingestion.

### 8.3. Cost-efficient resources

Chọn đúng dịch vụ, loại tài nguyên, kích thước và pricing model.

Ví dụ:

- Right-size EC2/RDS theo utilization.
- Dùng Graviton nếu tương thích và hiệu quả hơn cho workload.
- Dùng Spot Instances cho workload chịu được gián đoạn.
- Dùng Savings Plans hoặc Reserved Instances cho mức sử dụng ổn định sau khi phân tích.
- Dùng S3 Lifecycle để chuyển dữ liệu ít truy cập sang storage class phù hợp.
- Tắt hoặc schedule môi trường dev/test khi không sử dụng.

Không mua commitment chỉ để đạt discount nếu nhu cầu thực tế chưa ổn định.

### 8.4. Continuous optimization

Chi phí thay đổi theo tải, kiến trúc và giá dịch vụ. Cần có lịch review và automation.

- Dùng AWS Compute Optimizer để tìm cơ hội right-sizing.
- Tự động scale theo demand.
- Loại bỏ snapshot, volume, IP và resource không còn sử dụng theo quy trình an toàn.
- Review data transfer và cross-Region traffic.
- Đánh giá lại lựa chọn dịch vụ khi AWS có managed capability mới.
- Theo dõi cost per request, cost per order hoặc cost per transaction.

Một kiến trúc tối ưu chi phí cần cân nhắc chi phí vận hành, license, data transfer, backup, observability và nhân lực, không chỉ giá compute.

## 9. Sustainability – Tính bền vững

Sustainability pillar tập trung vào tác động môi trường của workload, đặc biệt là năng lượng và hiệu quả sử dụng tài nguyên. Mục tiêu là hoàn thành công việc hữu ích với ít tài nguyên cần thiết hơn trong toàn bộ vòng đời workload.

AWS tổ chức nội dung thành sáu vùng thực hành.

### 9.1. Region selection

Chọn Region theo yêu cầu pháp lý, data residency, latency, cost, availability và mục tiêu sustainability. Region gần người dùng có thể giảm latency và network transfer; các yếu tố về năng lượng và mục tiêu môi trường cũng cần được cân nhắc.

### 9.2. Alignment to demand

Căn chỉnh tài nguyên với nhu cầu thực:

- Autoscaling theo tải.
- Tắt workload không cần chạy liên tục.
- Xóa resource không còn sử dụng.
- Giảm capacity dư thừa.
- Dùng queue hoặc batch processing để tận dụng tài nguyên hiệu quả khi phù hợp.

### 9.3. Software and architecture

- Chọn thuật toán và cấu trúc dữ liệu hiệu quả.
- Giảm công việc tính toán lặp lại.
- Dùng cache để tránh truy vấn hoặc truyền dữ liệu không cần thiết.
- Thiết kế service để scale độc lập.
- Giảm payload và xử lý dữ liệu dư thừa.
- Tránh overprovisioning chỉ để đáp ứng một đỉnh tải hiếm gặp.

### 9.4. Data

- Xác định thời gian lưu trữ phù hợp.
- Dùng lifecycle policy để chuyển dữ liệu sang storage tier thích hợp.
- Xóa bản sao và dữ liệu không còn giá trị theo policy.
- Nén, partition và tối ưu format dữ liệu khi phù hợp.
- Tránh di chuyển dữ liệu qua mạng nhiều lần không cần thiết.

### 9.5. Hardware and services

Chọn compute, storage và managed services phù hợp với công việc. Theo dõi các lựa chọn phần cứng hiệu quả hơn, chẳng hạn Graviton khi ứng dụng tương thích. Managed services có thể giúp chia sẻ và tận dụng hạ tầng ở quy mô lớn, đồng thời giảm công việc vận hành mà nhóm phải tự thực hiện.

### 9.6. Process and culture

Đặt sustainability goals và đo tác động theo đơn vị công việc, ví dụ năng lượng hoặc tài nguyên trên mỗi giao dịch. Đưa tiêu chí sử dụng tài nguyên vào review kiến trúc, procurement, development và operations. Theo dõi cải thiện theo thời gian thay vì chỉ thực hiện một lần.

Sustainability không đồng nghĩa với việc giảm tài nguyên bằng mọi giá. Một workload bị thiếu capacity có thể chạy lâu hơn, retry nhiều hơn và gây tác động lớn hơn. Cần đo output và resource consumption cùng lúc.

## 10. Trade-off giữa sáu trụ cột

Một quyết định kiến trúc thường ảnh hưởng nhiều trụ cột. Hãy ghi lại mục tiêu, phương án, tác động và thời điểm review lại quyết định.

| Quyết định | Lợi ích chính | Chi phí hoặc rủi ro cần cân nhắc |
|---|---|---|
| Multi-AZ database | Tăng khả năng chịu lỗi ở cấp AZ. | Tăng chi phí, replication traffic và yêu cầu kiểm thử failover. |
| Multi-Region active-active | Có thể giảm downtime và latency cho người dùng toàn cầu. | Tăng độ phức tạp, đồng bộ dữ liệu, conflict handling và chi phí. |
| Synchronous replication | Giảm nguy cơ mất dữ liệu khi failover. | Có thể tăng write latency và phụ thuộc network. |
| Dùng managed service | Giảm công việc patching, scaling và vận hành nền tảng. | Giảm quyền kiểm soát chi tiết và có thể gặp service constraints. |
| Logging chi tiết | Tăng khả năng điều tra và audit. | Tăng chi phí ingest, lưu trữ và nhiễu nếu không lọc tốt. |
| Cache mạnh | Giảm latency và tải database. | Cần xử lý cache invalidation, stale data và consistency. |
| Capacity dự phòng | Có thể hấp thụ tải đột biến hoặc lỗi component. | Tăng chi phí idle capacity và tác động sustainability. |
| Serverless | Giảm vận hành server và phù hợp tải biến động. | Cần cân nhắc cold start, concurrency quota, timeout và chi phí theo request. |

### 10.1. Ghi lại architectural decision

Một Architecture Decision Record (ADR) có thể chứa:

1. Bối cảnh và yêu cầu kinh doanh.
2. Các lựa chọn đã đánh giá.
3. Quyết định được chọn và lý do.
4. Trụ cột được cải thiện.
5. Tác động lên các trụ cột còn lại.
6. Chỉ số xác minh thành công.
7. Rủi ro còn chấp nhận và biện pháp giảm thiểu.
8. Owner và ngày review lại.

Ví dụ: workload đặt hàng chạy trên ba Availability Zones để đáp ứng mục tiêu availability. Nhóm chấp nhận chi phí compute/database cao hơn và đặt mục tiêu failover trong thời gian xác định. Quyết định được review hàng quý bằng availability, RTO, cost per order và kết quả game day.

Không có một mức availability, RTO hoặc RPO phù hợp với mọi workload. Các giá trị phải xuất phát từ tác động kinh doanh của downtime và mất dữ liệu.

## 11. Quy trình thực hiện Well-Architected review

Review nên được thực hiện ở các mốc quan trọng như trước production, sau một thay đổi kiến trúc lớn, sau sự cố nghiêm trọng hoặc khi business requirements thay đổi.

### Bước 1: Xác định phạm vi workload

Ghi lại:

- Tên workload, owner, môi trường và tài khoản AWS.
- Người dùng và business outcome.
- Data classification và regulatory constraints.
- Các dependency nội bộ/bên ngoài.
- Region/AZ, network boundary và luồng dữ liệu.
- Các SLO, availability, latency, throughput, RTO và RPO.

### Bước 2: Thu thập bằng chứng

Chuẩn bị sơ đồ kiến trúc, data flow, IAM model, deployment pipeline, dashboard, incident history, cost report, backup/restore test và security findings. Bằng chứng giúp review dựa trên cách workload đang hoạt động thay vì giả định trong tài liệu.

### Bước 3: Đánh giá sáu trụ cột

Với từng câu hỏi, xác định:

- Best practice đang được áp dụng.
- Bằng chứng hỗ trợ.
- Thực hành chưa áp dụng hoặc không phù hợp.
- Lý do nếu đánh dấu không áp dụng.
- Rủi ro và tác động nếu không cải thiện.

Không đánh dấu một practice là đã áp dụng chỉ vì có bật một dịch vụ AWS. Ví dụ, có CloudWatch chưa có nghĩa observability tốt nếu thiếu SLO, dashboard và cảnh báo có thể hành động.

### Bước 4: Xác định và ưu tiên rủi ro

Phân loại risk theo mức độ ảnh hưởng, khả năng xảy ra, phạm vi tài nguyên, khả năng khai thác và yêu cầu kinh doanh. Xác định những vấn đề cần xử lý trước production hoặc trước lần release tiếp theo.

### Bước 5: Lập improvement plan

Mỗi improvement item cần:

- Mô tả vấn đề và tác động.
- Hành động cụ thể.
- Owner và nhóm phối hợp.
- Mức ưu tiên và deadline.
- Effort, dependency và change window.
- Tiêu chí hoàn tất và bằng chứng xác minh.

### Bước 6: Thực hiện và xác minh

Triển khai thay đổi qua IaC/pipeline hoặc change process phù hợp. Kiểm tra lại bằng metrics, security checks, load tests, restore tests hoặc game days. Cập nhật kiến trúc và ADR để phản ánh trạng thái mới.

### Bước 7: Lưu milestone và review lại

Lưu milestone để chụp trạng thái workload tại một thời điểm. So sánh milestone giữa các lần review để đo số risk đã giảm, risk còn tồn tại và những vấn đề mới phát sinh.

## 12. AWS Well-Architected Tool và lenses

AWS Well-Architected Tool (AWS WA Tool) hỗ trợ ghi lại kiến trúc, đánh giá workload theo best practices và theo dõi cải tiến. Công cụ giúp chuẩn hóa quy trình review và tạo improvement plan.

### 12.1. Workload và lens

Khi tạo workload trong WA Tool, nhóm khai báo thông tin về workload, môi trường, owner, kiến trúc và các lens cần đánh giá.

Lens là bộ câu hỏi và best practices cho một phạm vi kiến trúc:

- AWS Well-Architected Framework lens đánh giá sáu trụ cột.
- AWS-provided lenses tập trung vào ngành hoặc công nghệ như serverless, SaaS, generative AI, analytics hoặc migration.
- Custom lenses cho phép tổ chức đưa yêu cầu nội bộ, policy hoặc tiêu chí kỹ thuật riêng vào review.

Một workload có thể áp dụng nhiều lens để kiểm tra các khía cạnh khác nhau. Hãy chọn lens theo loại workload và rủi ro cần đánh giá, tránh thêm lens không liên quan chỉ để tăng số lượng câu hỏi.

### 12.2. Profiles và review templates

Profiles cho phép xác định business goals và ưu tiên các câu hỏi/rủi ro phù hợp với mục tiêu của workload. Ví dụ, workload thanh toán có thể ưu tiên security, reliability và compliance; workload phân tích nội bộ có thể chú trọng cost, performance và data governance.

Review templates giúp chuẩn hóa câu trả lời và giảm công việc lặp lại khi nhiều workload có cùng đặc điểm hoặc tiêu chuẩn nền tảng.

### 12.3. Improvement plan và milestones

Sau review, WA Tool tổng hợp risk và đề xuất improvement items theo lens. Nhóm có thể:

1. Mở improvement plan.
2. Xem câu hỏi và best practices có risk.
3. Chọn hành động cần thực hiện.
4. Giao owner và đưa vào backlog.
5. Cập nhật câu trả lời/notes sau khi cải thiện.
6. Lưu milestone mới để đo tiến độ.

Milestone ghi lại trạng thái review tại thời điểm lưu và hỗ trợ so sánh giữa các lần đánh giá. Workload report có thể chia sẻ trạng thái, câu trả lời, risk và đề xuất cải thiện với stakeholder.

### 12.4. Tích hợp và hỗ trợ mới

WA Tool có thể tích hợp với các dịch vụ như AWS Trusted Advisor và AWS Service Catalog AppRegistry để hỗ trợ thu thập thông tin workload. Công cụ cũng cung cấp API và các tính năng chia sẻ để đưa review vào quy trình governance.

AWS Well-Architected Agent là tính năng AI riêng đang ở public preview, hỗ trợ phân tích môi trường và đề xuất cải thiện; nó không thay thế AWS WA Tool hoặc quyết định của người chịu trách nhiệm. Bản cập nhật Agent ngày 16-11-2026 bổ sung organizational profiles, tích hợp AWS Organizations, chia sẻ profiles/recommendations và basic profile onboarding. Quyền truy cập Agent phụ thuộc support plan và điều kiện AWS công bố.

## 13. Tình huống thực hành: thiết kế website thương mại điện tử

Một doanh nghiệp muốn xây dựng website bán hàng trên AWS. Hệ thống có website, catalog, đăng nhập, giỏ hàng, order service, payment integration và quản lý tồn kho. Traffic tăng mạnh vào chiến dịch khuyến mãi. Dữ liệu đơn hàng cần bảo vệ và dịch vụ phải phục hồi khi có lỗi hạ tầng.

### 13.1. Kiến trúc tham khảo

~~~mermaid
flowchart TB
    U["Người mua hàng"] --> CF["Amazon CloudFront"]
    CF --> WAF["AWS WAF"]
    WAF --> ALB["Application Load Balancer"]
    ALB --> APP["ECS services trên nhiều AZ"]
    APP --> CACHE["ElastiCache"]
    APP --> DB["Aurora / RDS Multi-AZ"]
    APP --> Q["Amazon SQS"]
    Q --> WORKER["Order / Inventory workers"]
    WORKER --> DB
    APP --> S3["Amazon S3"]
    APP --> ID["Amazon Cognito / IAM integration"]
    APP --> PAY["Payment provider"]
    APP --> OBS["CloudWatch / X-Ray"]
    DB --> BACKUP["AWS Backup / snapshots"]
~~~

Đây là sơ đồ khái niệm. Lựa chọn database, identity, payment integration, queue và triển khai AZ phải được xác nhận theo yêu cầu dữ liệu, workload profile, Region availability và business constraints.

### 13.2. Đánh giá theo sáu trụ cột

| Trụ cột | Quyết định thiết kế | Cách xác minh |
|---|---|---|
| Operational Excellence | Dùng IaC, CI/CD, CloudWatch dashboards, tracing và runbooks. | Kiểm tra deployment, alert response, change failure rate và MTTR. |
| Security | Dùng IAM roles, encryption bằng KMS, WAF, TLS, secret management và audit logging. | Kiểm tra quyền, policy, security findings và khả năng truy vết. |
| Reliability | Chạy service/database qua nhiều AZ, dùng SQS để tách xử lý đơn hàng, retry và backup. | Thử mất một AZ, queue backlog, restore database và failover. |
| Performance Efficiency | Dùng CloudFront, cache, autoscaling và database/index phù hợp access pattern. | Load test, theo dõi p95/p99 latency, throughput và cache hit ratio. |
| Cost Optimization | Rightsize compute, autoscale, lifecycle S3 và đo cost per order. | Review Cost Explorer, budgets, utilization và data transfer. |
| Sustainability | Tắt môi trường không dùng, scale theo demand, giảm xử lý lặp và lưu dữ liệu đúng lifecycle. | Đo resource consumption trên mỗi order và tỷ lệ idle capacity. |

### 13.3. Phân tích một trade-off

Giả sử doanh nghiệp muốn xử lý đơn hàng ngay cả khi một AZ gặp sự cố. Nhóm chọn triển khai service và database Multi-AZ, đồng thời dùng SQS để tách bước nhận đơn khỏi bước xử lý tồn kho.

Lợi ích:

- Request có thể tiếp tục được nhận khi một số worker bị lỗi.
- Queue lưu công việc trong thời gian consumer phục hồi.
- Database có cơ chế availability phù hợp với cấu hình đã chọn.

Chi phí và giới hạn:

- Multi-AZ tăng chi phí tài nguyên.
- Queue cần xử lý duplicate delivery bằng idempotency.
- Failover có thể làm gián đoạn kết nối trong một khoảng thời gian.
- Backup cần được kiểm thử restore; Multi-AZ không thay thế backup.
- Độ nhất quán giữa order, payment và inventory cần được thiết kế ở cấp ứng dụng.

Nhóm cần định nghĩa SLO, RTO/RPO, quy tắc retry và tiêu chí reconcile giao dịch trước khi quyết định mức redundancy.

## 14. Những hiểu lầm thường gặp

1. **Framework là checklist dịch vụ AWS.** Framework đánh giá quyết định và best practices; không yêu cầu mọi workload dùng cùng một bộ dịch vụ.
2. **Review là audit hoặc chứng nhận compliance.** Review là cuộc trao đổi để nhận diện rủi ro và cải thiện kiến trúc.
3. **Chỉ cần xem sáu trụ cột khi thiết kế ban đầu.** Workload thay đổi theo business, tải, dependency và dịch vụ AWS; cần review định kỳ và theo sự kiện.
4. **Multi-AZ đồng nghĩa không thể downtime.** Failover, application dependency, deployment và lỗi logic vẫn có thể gây gián đoạn.
5. **Multi-Region luôn tốt hơn Multi-AZ.** Multi-Region tăng độ phức tạp và chi phí; cần dựa vào RTO/RPO, latency và business continuity.
6. **Security chỉ là IAM và encryption.** Security còn gồm governance, detection, infrastructure/application protection và incident response.
7. **Có CloudWatch nghĩa là observability đã tốt.** Cần KPI/SLO, telemetry đủ ngữ cảnh, dashboard và alert có thể hành động.
8. **Cost Optimization nghĩa là chọn dịch vụ rẻ nhất.** Cần cân bằng giá với business value, reliability, security và performance.
9. **Sustainability chỉ là chọn Region.** Cần tối ưu software, architecture, data, hardware, demand và process.
10. **Một lần review là đủ.** Best practices, workload và AWS services thay đổi; cần milestone và review lại.

## 15. Câu hỏi tự kiểm tra

**1. AWS Well-Architected Framework giải quyết vấn đề gì?**

Framework cung cấp câu hỏi và best practices để đánh giá quyết định kiến trúc, nhận diện rủi ro và lập kế hoạch cải thiện workload.

**2. Sáu trụ cột của Framework là gì?**

Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization và Sustainability.

**3. Cloud Foundations khác Cloud Workloads như thế nào?**

Cloud Foundations thiết lập năng lực và guardrails ở cấp tổ chức/account; Cloud Workloads đánh giá thiết kế và vận hành từng workload.

**4. Vì sao một chỉ số kỹ thuật riêng lẻ không đủ đánh giá kiến trúc?**

Chất lượng kiến trúc phụ thuộc nhiều mục tiêu và trade-off. Cần xem business outcome, risk, dependency, bằng chứng và tác động giữa các trụ cột.

**5. RTO và RPO mô tả điều gì?**

RTO là thời gian mục tiêu khôi phục dịch vụ; RPO là mức mất dữ liệu tối đa có thể chấp nhận tính theo thời gian.

**6. Vì sao Multi-AZ không thay thế backup?**

Multi-AZ giúp chịu lỗi hạ tầng/AZ theo cơ chế dịch vụ, nhưng không bảo vệ đầy đủ khỏi xóa nhầm, lỗi logic, corruption hoặc yêu cầu khôi phục dữ liệu về thời điểm trước.

**7. Khi nào nên dùng managed services?**

Khi dịch vụ đáp ứng yêu cầu và việc giảm gánh nặng vận hành có giá trị hơn phần quyền kiểm soát chi tiết mà nhóm phải từ bỏ.

**8. Cost per transaction giúp ích gì?**

Chỉ số này liên hệ chi phí với business output, giúp đánh giá chi phí có giảm thực sự khi tối ưu tài nguyên hoặc tăng hiệu quả hay không.

**9. AWS Well-Architected Tool hỗ trợ những việc gì?**

Ghi nhận workload, thực hiện review bằng lenses, xác định risk, lập improvement plan, lưu milestones và tạo workload reports.

**10. Khi nào nên thực hiện Well-Architected review?**

Trước khi production, tại các milestone lớn, sau thay đổi kiến trúc đáng kể, sau sự cố và khi yêu cầu kinh doanh thay đổi.

**11. Game day có mục đích gì?**

Mô phỏng sự cố để kiểm tra khả năng phát hiện, phản ứng, phục hồi và chất lượng runbook trong điều kiện có kiểm soát.

**12. Vì sao cần ghi lại trade-off bằng ADR?**

ADR lưu bối cảnh, lựa chọn, lý do, tác động và điều kiện review lại, giúp nhóm hiểu quyết định cũ và tránh lặp lại tranh luận.

## 16. Checklist review kiến trúc production

- [ ] Workload boundary, business owner, người dùng và business outcome đã rõ.
- [ ] Có sơ đồ kiến trúc, data flow, dependency và trust boundaries.
- [ ] Có SLO/KPI, availability target, latency, throughput, RTO và RPO.
- [ ] Cloud Foundations cung cấp account, identity, observability, networking và security guardrails cần thiết.
- [ ] Operational Excellence có runbook, deployment controls, dashboards và incident process.
- [ ] Security có least privilege, data classification, encryption, detection và incident response.
- [ ] Reliability có fault isolation, scaling, backup, restore test và DR strategy.
- [ ] Performance Efficiency có load test, profiling, capacity strategy và resource selection phù hợp.
- [ ] Cost Optimization có cost attribution, budgets, lifecycle và lịch review.
- [ ] Sustainability có tiêu chí resource efficiency và theo dõi tác động theo workload output.
- [ ] Các trade-off quan trọng được ghi lại cùng owner và ngày review.
- [ ] Improvement items có priority, deadline và tiêu chí xác minh.
- [ ] Có milestone để so sánh trạng thái trước/sau cải thiện.
- [ ] Kiến trúc, ADR và runbook được cập nhật sau thay đổi.
- [ ] Có lịch review định kỳ và trigger review khi business hoặc technology thay đổi.

## Tài liệu tham khảo

- [AWS Well-Architected Framework – Framework hiện hành](https://docs.aws.amazon.com/wellarchitected/latest/framework/framework.html)
- [AWS Well-Architected Framework – Release notes](https://docs.aws.amazon.com/wellarchitected/latest/framework/release-notes.html)
- [AWS Well-Architected Cloud Foundations](https://docs.aws.amazon.com/wellarchitected/latest/framework/cloud-foundations.html)
- [AWS Well-Architected Cloud Workloads](https://docs.aws.amazon.com/wellarchitected/latest/framework/workloads.html)
- [The six pillars of the Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html)
- [General design principles](https://docs.aws.amazon.com/wellarchitected/latest/framework/general-design-principles.html)
- [Operational Excellence](https://docs.aws.amazon.com/wellarchitected/latest/framework/operational-excellence.html)
- [Security](https://docs.aws.amazon.com/wellarchitected/latest/framework/security.html)
- [Reliability](https://docs.aws.amazon.com/wellarchitected/latest/framework/reliability.html)
- [Performance Efficiency](https://docs.aws.amazon.com/wellarchitected/latest/framework/performance-efficiency.html)
- [Cost Optimization](https://docs.aws.amazon.com/wellarchitected/latest/framework/cost-optimization.html)
- [Sustainability](https://docs.aws.amazon.com/wellarchitected/latest/framework/sustainability.html)
- [Shared responsibility](https://docs.aws.amazon.com/wellarchitected/latest/framework/shared-responsibility.html)
- [Understanding architectural trade-offs](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel-understanding-tradeoffs.html)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/tool.html)
- [Tutorial: Document a workload with AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/tutorial.html)
- [Using lenses in AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/lenses.html)
- [Profiles in AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/profiles.html)
- [Generate a workload report](https://docs.aws.amazon.com/wellarchitected/latest/userguide/workloads-report.html)
- [AWS Well-Architected Tool user guide release notes](https://docs.aws.amazon.com/wellarchitected/latest/userguide/release-notes.html)
- [AWS Well-Architected documentation homepage](https://docs.aws.amazon.com/wellarchitected/)

