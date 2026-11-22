# Chiến lược pilot light và warm standby

Khi một AWS Region gặp sự cố nghiêm trọng, một workload có thể mất khả năng phục vụ dù dữ liệu vẫn còn ở nơi khác. Tổ chức cần một môi trường dự phòng đủ khả năng tiếp nhận traffic, có dữ liệu phù hợp và có thể được kích hoạt trong thời gian đã cam kết. Hai chiến lược thường được cân nhắc là **pilot light** và **warm standby**.

Pilot light giữ sẵn những thành phần cốt lõi cần thiết để phục hồi, thường bao gồm data store hoặc bản sao dữ liệu, network, IAM và một số tài nguyên nền tảng. Khi có sự cố, đội vận hành triển khai hoặc mở rộng phần compute và các thành phần còn lại để đưa ứng dụng hoạt động ở Region dự phòng.

Warm standby duy trì một phiên bản thu nhỏ nhưng hoạt động được của workload tại Region dự phòng. Khi Region chính gặp sự cố, đội vận hành tăng quy mô tài nguyên dự phòng và chuyển traffic sang đó. Vì một phần ứng dụng đã chạy sẵn, warm standby thường có thể đạt RTO ngắn hơn pilot light, đổi lại chi phí duy trì cao hơn.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, lựa chọn giữa hai chiến lược cần dựa trên RTO, RPO, kiến trúc dữ liệu, dependency, khả năng vận hành và ngân sách. Mục tiêu của module là giúp người học thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí; do đó một phương án DR phải được kiểm thử từ dữ liệu, compute, network, quyền truy cập tới thời điểm nghiệp vụ thực sự hoạt động trở lại.

## 1. Khi nào cần pilot light hoặc warm standby?

Một workload có thể cần phục hồi sau các sự cố như:

- Một Region không thể cung cấp dịch vụ trong thời gian dài.
- Lỗi cấu hình hoặc thay đổi diện rộng làm ứng dụng ở Region chính không hoạt động.
- Sự cố bảo mật buộc tổ chức cô lập account hoặc môi trường production.
- Hỏng hóc dữ liệu hoặc dịch vụ phụ thuộc khiến workload phải chuyển sang môi trường khác.
- Sự cố vận hành hoặc năng lực hạ tầng làm thời gian khôi phục tại Region chính vượt RTO.

Pilot light và warm standby thường được dùng trong DR đa Region. Chúng khác với **high availability (HA)** trong một Region hoặc nhiều Availability Zone. Multi-AZ giúp workload tiếp tục hoạt động khi một AZ gặp lỗi; DR đa Region chuẩn bị cho tình huống Region chính không còn là nơi phục vụ được. Hai lớp này bổ trợ nhau.

Không phải mọi workload đều cần môi trường dự phòng chạy liên tục. Nếu nghiệp vụ chấp nhận RTO tính bằng giờ và RPO một ngày, backup and restore có thể hợp lý hơn. Nếu hệ thống cần RTO vài phút, warm standby có thể phù hợp. Nếu gần như không chấp nhận gián đoạn, cần đánh giá active/active hoặc multi-site, nhưng độ phức tạp dữ liệu và chi phí sẽ tăng đáng kể.

## 2. Pilot light là gì?

Pilot light là chiến lược duy trì một tập thành phần tối thiểu nhưng quan trọng tại Region dự phòng để có thể khởi động workload khi cần. Tên gọi gợi ý một ngọn lửa nhỏ luôn được giữ cháy: phần lõi đã sẵn sàng, còn các tài nguyên compute hoặc thành phần không cần chạy liên tục sẽ được tạo hoặc mở rộng trong quá trình failover.

Một kiến trúc pilot light thường có:

- Data store ở Region dự phòng hoặc cơ chế replication liên tục từ Region chính.
- VPC, subnet, route, security group và endpoint cần thiết đã được chuẩn bị.
- IAM role, KMS key, secret và cấu hình bảo mật tương ứng.
- AMI, container image, package, IaC template và deployment artifact đã được sao chép hoặc có thể truy xuất.
- Compute capacity được tạo khi failover hoặc duy trì ở mức tối thiểu.
- Runbook tự động hóa quá trình scale, deploy, validate và chuyển traffic.

Điểm quan trọng là dữ liệu và dependency cốt lõi phải sẵn sàng. Nếu chỉ có snapshot nằm trong S3 hoặc AWS Backup vault mà chưa có data store được restore, giải pháp có thể gần với backup and restore hơn là pilot light.

### Ví dụ

Một ứng dụng Orders chạy trên ECS và Amazon Aurora ở Region chính. Tại Region dự phòng:

- Aurora Global Database có secondary cluster nhận dữ liệu từ primary.
- VPC, subnet, security group, KMS key và secret đã được chuẩn bị.
- ECR image và task definition được đồng bộ.
- ECS cluster có thể được tạo hoặc mở rộng trong quá trình failover.
- Load balancer, listener và DNS routing được cấu hình bằng IaC.

Khi Region chính gặp sự cố, đội vận hành promote secondary database, triển khai ECS service, chạy health check, rồi chuyển traffic tới endpoint dự phòng.

## 3. Warm standby là gì?

Warm standby duy trì một bản triển khai hoàn chỉnh và hoạt động được của workload ở Region dự phòng, nhưng thường chạy với capacity nhỏ hơn Region chính. Ứng dụng, data store, network và các dependency thiết yếu đã sẵn sàng. Khi failover, đội vận hành tăng số lượng instance/task/pod hoặc chuyển database sang vai trò ghi, sau đó chuyển traffic.

Một warm standby điển hình có:

- Compute đang chạy ở mức tối thiểu nhưng có thể phục vụ health check hoặc tải nhỏ.
- Data store được replicate và có thể nhận traffic theo quy trình promote/failover.
- Network, load balancer, DNS, certificate và IAM đã được cấu hình.
- Artifact và cấu hình ứng dụng tương ứng với production.
- Monitoring và alert ở cả Region chính lẫn Region dự phòng.
- Automation để tăng capacity, kiểm tra dữ liệu và chuyển traffic.

Warm standby thường giảm thời gian cần để khởi động compute và triển khai ứng dụng. Tuy nhiên, nếu database chưa sẵn sàng, secret không đọc được, quota thiếu hoặc DNS chưa chuyển, việc có vài EC2 instance đang chạy vẫn không bảo đảm RTO.

### Ví dụ

Ứng dụng API chạy trên ECS ở hai Region. Region dự phòng luôn duy trì một ECS service nhỏ với một số task, ALB và kết nối tới Aurora secondary. Khi có sự cố, nhóm vận hành tăng desired count, promote database, cập nhật routing và xác nhận các luồng nghiệp vụ.

## 4. So sánh pilot light và warm standby

| Tiêu chí | Pilot light | Warm standby |
|---|---|---|
| Compute ở Region dự phòng | Có thể chưa chạy hoặc chỉ chạy thành phần tối thiểu | Đã chạy ở quy mô nhỏ |
| Data store | Thường đã replicate hoặc sẵn sàng promote/restore | Thường đã replicate và sẵn sàng phục vụ theo quy trình |
| Thời gian kích hoạt | Cần tạo/khởi động thêm nhiều thành phần | Chủ yếu tăng capacity và chuyển traffic |
| RTO | Thường dài hơn warm standby | Thường ngắn hơn pilot light |
| RPO | Phụ thuộc cơ chế replication/backup | Phụ thuộc cơ chế replication/backup |
| Chi phí duy trì | Thường thấp hơn | Thường cao hơn do compute chạy liên tục |
| Độ phức tạp | Cần automation khởi tạo và cấu hình nhiều thành phần khi failover | Cần duy trì môi trường chạy, đồng bộ version và scale |
| Kiểm thử | Phải kiểm tra cả quá trình dựng và khởi động | Có thể kiểm tra workload thường xuyên hơn, nhưng vẫn phải thử tăng tải/failover |
| Phù hợp | Workload quan trọng nhưng có thể chấp nhận thời gian kích hoạt lâu hơn | Workload quan trọng cần khôi phục nhanh hơn |

RPO không tự động tốt hơn ở warm standby. Nếu cả hai phương án dùng cùng cơ chế replication và có cùng độ trễ, RPO có thể tương đương. Điểm khác biệt chính là mức độ sẵn sàng của compute và thời gian đưa ứng dụng vào trạng thái phục vụ.

## 5. Vị trí của hai chiến lược trong phổ DR

AWS Well-Architected mô tả bốn chiến lược DR đa Region phổ biến. Chúng thể hiện sự đánh đổi giữa mức chuẩn bị, tốc độ phục hồi và chi phí.

| Chiến lược | Mô tả ngắn | Đặc điểm vận hành |
|---|---|---|
| Backup and restore | Khôi phục hạ tầng và dữ liệu từ backup sau sự cố | Ít tài nguyên chạy liên tục; thời gian restore và dựng lại dài hơn |
| Pilot light | Giữ data và thành phần lõi; triển khai compute khi cần | Cần automation khởi tạo và mở rộng |
| Warm standby | Duy trì workload thu nhỏ, có thể hoạt động | Tăng capacity và chuyển traffic khi failover |
| Multi-site active/active | Nhiều Region cùng phục vụ traffic | Phải xử lý consistency, conflict, routing và vận hành đồng thời |

Không có một mốc RTO/RPO cố định áp dụng cho mọi kiến trúc. Các tài liệu AWS thường mô tả pilot light có thể đạt RTO ở mức hàng chục phút và warm standby ở mức vài phút trong thiết kế phù hợp, nhưng kết quả phụ thuộc workload, dữ liệu, automation, quota và diễn tập. Hãy dùng kết quả kiểm thử thực tế để cam kết.

## 6. Kiến trúc tham khảo cho pilot light

~~~mermaid
flowchart TB
    subgraph Primary["Region chính"]
      P1[Route 53 / Global Accelerator]
      P2[ALB]
      P3[ECS hoặc EC2 Compute]
      P4[Primary Database]
      P1 --> P2 --> P3 --> P4
    end
    subgraph DR["Region dự phòng - Pilot Light"]
      D1[Network và IAM đã chuẩn bị]
      D2[Secondary Database / Replica]
      D3[ECR Image và IaC Artifact]
      D4[Compute tạo khi failover]
      D5[ALB và endpoint dự phòng]
      D1 --> D4 --> D5
      D2 --> D4
      D3 --> D4
    end
    P4 -. Replication .-> D2
    P1 -. Failover routing .-> D5
~~~

Trong sơ đồ, data store và nền tảng bảo mật đã được chuẩn bị ở Region dự phòng. Compute có thể được triển khai khi failover. Tùy dịch vụ, replica có thể ở trạng thái read-only hoặc chỉ được promote thành primary khi có sự cố.

### Các thành phần cần chuẩn bị trước

**Network:** VPC CIDR không xung đột với mạng hiện hữu, subnet theo AZ, route table, NAT/egress, security group, NACL, VPC endpoint và kết nối hybrid nếu cần.

**Identity và encryption:** IAM role, trust policy, KMS key tại Region dự phòng, key policy, secret replication hoặc quy trình tạo secret, certificate và quyền truy cập artifact.

**Data:** replica database, snapshot copy, backup vault, S3 replication, DynamoDB Global Tables hoặc cơ chế phù hợp với dịch vụ.

**Application:** image, AMI, task definition, launch template, IaC, cấu hình runtime, parameter và phiên bản tương thích với schema dữ liệu.

**Traffic:** ALB/NLB, target group, health check, Route 53 record hoặc AWS Global Accelerator endpoint.

**Operations:** CloudWatch dashboard, alarm, log, EventBridge, runbook, người phê duyệt và kênh liên lạc ngoài băng.

## 7. Kiến trúc tham khảo cho warm standby

~~~mermaid
flowchart TB
    subgraph Primary["Region chính"]
      A1[Global routing]
      A2[Load Balancer]
      A3[Compute - full capacity]
      A4[Primary Data Store]
      A1 --> A2 --> A3 --> A4
    end
    subgraph Standby["Region dự phòng - Warm Standby"]
      B1[Load Balancer]
      B2[Compute - minimum capacity]
      B3[Replica Data Store]
      B1 --> B2 --> B3
      B4[Monitoring và Automation]
      B4 --> B2
    end
    A4 -. Continuous / frequent replication .-> B3
    A1 -. Route traffic after validation .-> B1
~~~

Warm standby cần duy trì một phiên bản ứng dụng có thể chạy được, không chỉ là một cụm compute đang bật. Phiên bản ứng dụng, cấu hình, schema, secret và quyền cần tương thích với dữ liệu được replicate. Nếu Region chính đã triển khai version mới nhưng Region dự phòng vẫn dùng version cũ, failover có thể gây lỗi tương thích.

Nên triển khai cùng một release artifact qua pipeline tới cả hai Region. Khác biệt về capacity có thể được quản lý bằng tham số môi trường, nhưng không nên để hai Region chạy hai codebase không tương thích.

## 8. Thiết kế replication dữ liệu

Data replication là yếu tố quyết định RPO. Cần xác định dữ liệu được replicate đồng bộ hay bất đồng bộ, có thể promote ở Region đích hay phải restore, và cách xử lý ghi đang diễn ra khi chuyển đổi.

| Dịch vụ | Cơ chế có thể dùng | Điểm cần kiểm tra |
|---|---|---|
| Amazon Aurora | Aurora Global Database hoặc snapshot/copy theo nhu cầu | Replication lag, secondary cluster, promotion và failover |
| Amazon RDS | Cross-Region read replica hoặc snapshot copy theo engine hỗ trợ | Engine/version, lag, promotion, backup và connection endpoint |
| DynamoDB | Global Tables hoặc backup/restore | Conflict resolution, consistency mode, replica Region và write routing |
| Amazon S3 | Cross-Region Replication (CRR) hoặc Same-Region Replication (SRR) | Replication status, delete marker, versioning, Object Lock và KMS |
| EBS | Snapshot copy sang Region khác | Tần suất snapshot, copy duration, encryption key và volume creation |
| EFS | AWS Backup hoặc giải pháp replication phù hợp với yêu cầu | File consistency, restore target, throughput và metadata |
| OpenSearch Service | Cross-Cluster Replication hoặc snapshot/restore theo thiết kế | Cluster version, index mapping, lag và quyền truy cập |

Không phải mọi dịch vụ có replication đều bảo đảm zero data loss. Replication bất đồng bộ có thể có lag; dữ liệu chưa tới Region đích tại thời điểm sự cố có thể mất. Với RPO rất thấp, cần đo lag và có quy trình ngăn ghi mới hoặc đối soát giao dịch khi promote.

### Replication và backup phải bổ trợ nhau

Replication giữ bản sao cập nhật nhanh để giảm thời gian chuyển đổi. Backup giữ các recovery point lịch sử để quay về trước khi dữ liệu bị xóa, sửa sai hoặc mã hóa. Nếu một thao tác xóa hợp lệ nhưng nhầm lẫn được replicate ngay, replica không giúp khôi phục trạng thái trước thao tác đó.

Đối với dữ liệu quan trọng, nên kết hợp:

- Replication để đạt RPO/RTO cho sự cố Region.
- Backup định kỳ hoặc point-in-time recovery để khôi phục lỗi logic.
- Bản sao backup cross-account hoặc immutable để chống xóa trái phép.
- Restore test để xác nhận dữ liệu và quyền truy cập.

## 9. Đồng bộ các dependency ngoài dữ liệu

Một môi trường DR chỉ hoạt động khi các thành phần ngoài database cũng sẵn sàng.

| Dependency | Cách chuẩn bị ở Region dự phòng |
|---|---|
| VPC và subnet | Quản lý bằng IaC, kiểm tra CIDR và route |
| Security group/NACL | Đồng bộ policy và rà soát nguồn/đích |
| IAM role | Tạo role và trust policy tương ứng; kiểm tra principal dịch vụ |
| KMS | Tạo key riêng tại Region đích, đồng bộ key policy và grants cần thiết |
| Secrets Manager | Bật replication hoặc tạo secret theo quy trình có kiểm soát |
| Parameter Store | Đồng bộ parameter qua IaC/pipeline; kiểm tra SecureString và KMS |
| Container image | Bật ECR replication hoặc copy image theo digest |
| AMI | Copy AMI và snapshot liên quan sang Region dự phòng |
| Certificate | Cấp hoặc import certificate phù hợp tại Region đích |
| DNS | Chuẩn bị record, health check, TTL và quyền cập nhật |
| Service quota | Kiểm tra quota compute, ENI, IP, load balancer và database |
| Observability | Chuẩn bị log group, alarm, dashboard và quyền ghi log |

KMS key là tài nguyên theo Region. Một key ARN ở Region chính không thể được dùng như key cùng Region ở nơi dự phòng. Khi copy snapshot hoặc replica mã hóa, phải xác định key đích và policy cho dịch vụ restore.

## 10. Chuyển traffic khi failover

Sau khi data store và ứng dụng ở Region dự phòng sẵn sàng, traffic phải được chuyển tới endpoint mới. Hai lựa chọn phổ biến là Amazon Route 53 và AWS Global Accelerator.

### Route 53

Route 53 có thể dùng failover routing policy với primary/secondary record và health check. Khi endpoint primary không khỏe theo điều kiện đã cấu hình, DNS có thể trả về endpoint secondary. Cần chú ý DNS caching và TTL: client hoặc resolver có thể tiếp tục dùng địa chỉ cũ trong một khoảng thời gian.

Health check phải phản ánh khả năng phục vụ thực tế. Một endpoint trả HTTP 200 nhưng database không nhận ghi hoặc thanh toán không hoạt động không nên được coi là healthy cho mục tiêu nghiệp vụ.

### AWS Global Accelerator

Global Accelerator cung cấp static anycast IP và định tuyến tới endpoint theo health/traffic dial. Nó có thể giúp chuyển traffic giữa các Region mà không cần thay địa chỉ IP public của client. Cần chuẩn bị accelerator, listener, endpoint group và health check trước khi sự cố xảy ra.

### AWS Application Recovery Controller

AWS Route 53 Application Recovery Controller (ARC) cung cấp routing controls và readiness checks để hỗ trợ kiểm soát failover đa Region. Routing control có thể được vận hành qua API hoặc console theo quy trình đã thiết kế; không nên xem nó là hệ thống tự quyết định mọi sự cố. Readiness checks giúp kiểm tra một số điều kiện tài nguyên và cấu hình, nhưng vẫn cần diễn tập ứng dụng.

### Thứ tự chuyển traffic

1. Xác nhận Region chính không còn phù hợp để phục vụ.
2. Ngăn hai Region cùng nhận ghi nếu kiến trúc không hỗ trợ active/active.
3. Promote database hoặc xác nhận replica đã sẵn sàng ghi.
4. Scale compute và xác minh health check.
5. Kiểm tra authentication, secrets, payment, queue và các dependency.
6. Chuyển traffic bằng Route 53, Global Accelerator hoặc ARC routing control.
7. Theo dõi error rate, latency, transaction và log sau chuyển đổi.

Không chuyển DNS chỉ vì instance ở Region dự phòng đã chạy. Cần xác nhận data plane và luồng nghiệp vụ thực sự sẵn sàng.

## 11. Failover runbook cho pilot light

Một runbook mẫu có thể chia thành các giai đoạn:

| Giai đoạn | Hành động | Điều kiện hoàn tất |
|---|---|---|
| Declare | Xác nhận incident và phê duyệt DR activation | Có incident commander và phạm vi được thống nhất |
| Fence primary | Ngăn ghi hoặc traffic mới tới Region chính nếu cần | Không có hai primary gây split-brain |
| Promote data | Promote replica hoặc restore data store | Data store ở trạng thái có thể phục vụ |
| Provision | Tạo compute, load balancer và dependency còn thiếu | Tài nguyên cần thiết đã sẵn sàng |
| Configure | Gắn IAM role, secret, KMS và cấu hình ứng dụng | Workload đọc được dependency |
| Validate | Chạy health check và test nghiệp vụ | Giao dịch mẫu hoạt động và dữ liệu nhất quán |
| Route | Chuyển traffic | Request đi tới Region dự phòng |
| Observe | Theo dõi và thông báo trạng thái | Error rate/latency ổn định, owner xác nhận |

Automation có thể dùng AWS Systems Manager Automation, Step Functions, Lambda hoặc pipeline IaC. Mỗi bước cần timeout, retry, logging, idempotency và điều kiện dừng. Các thao tác như promote database hoặc thay đổi routing cần guardrail để tránh chạy lặp ngoài ý muốn.

## 12. Failover runbook cho warm standby

Warm standby thường bỏ qua hoặc rút ngắn giai đoạn provision compute vì ứng dụng đã chạy sẵn ở mức tối thiểu. Tuy nhiên, vẫn cần tăng capacity và xác nhận data store.

1. Declare incident và quyết định failover.
2. Fence Region chính hoặc khóa đường ghi nếu cần.
3. Promote data store ở Region dự phòng.
4. Scale ECS service, EKS node group/deployment hoặc EC2 Auto Scaling group tới capacity cần thiết.
5. Điều chỉnh connection pool, worker concurrency và downstream limit.
6. Xác nhận ALB target health, application health và giao dịch đại diện.
7. Chuyển traffic.
8. Theo dõi tải, error, queue depth, database connection và replication.

Warm standby cần được kiểm tra ở tải thực tế. Một service chạy một task có thể khỏe mạnh khi không có traffic nhưng không đủ capacity khi toàn bộ khách hàng chuyển tới. Cần xác định cách scale và giới hạn quota trước khi sự cố xảy ra.

## 13. Failback: quay lại Region chính

Failback là quá trình đưa workload trở lại Region chính sau khi môi trường đó đã được sửa chữa. Failback có thể nguy hiểm hơn failover nếu không xử lý đúng chiều dữ liệu và vai trò primary/secondary.

Trước khi failback:

- Xác nhận nguyên nhân sự cố đã được khắc phục.
- Đánh giá Region chính có đủ capacity và dependency không.
- Đồng bộ dữ liệu mới từ Region đang phục vụ về Region chính.
- Kiểm tra replication lag và consistency.
- Xác định thời điểm dừng ghi hoặc cách chuyển đổi không mất giao dịch.
- Kiểm tra version ứng dụng, schema và secret.
- Chuẩn bị kế hoạch rollback nếu failback thất bại.

Một quy trình failback an toàn thường:

1. Giữ Region DR là primary trong khi Region cũ được phục hồi.
2. Đồng bộ dữ liệu từ Region DR về Region cũ.
3. Thử nghiệm ứng dụng ở Region cũ bằng dữ liệu mới nhất.
4. Thực hiện cutover có kiểm soát, tránh hai primary cùng ghi.
5. Chuyển traffic về Region chính.
6. Theo dõi và xác nhận giao dịch.
7. Thiết lập lại replication theo chiều DR ban đầu.

Không giả định failback chỉ là đổi DNS ngược lại. Nếu database đã được promote ở Region DR, chiều replication và endpoint có thể đã thay đổi.

## 14. Bảo mật trong môi trường DR

Region dự phòng là một phần của production security boundary. Nếu môi trường DR có quyền rộng hơn hoặc ít giám sát hơn, attacker có thể chọn nó làm đường vòng.

Các nguyên tắc:

- Dùng IAM role riêng cho automation failover, với quyền tối thiểu cần thiết.
- Bảo vệ quyền promote database và thay đổi DNS bằng phê duyệt phù hợp.
- Giữ KMS key policy và secret access ở Region dự phòng ở mức least privilege.
- Bảo vệ backup vault và replication destination khỏi xóa hoặc sửa trái phép.
- Ghi CloudTrail và log automation ở cả hai Region.
- Bảo đảm security group, WAF, network firewall và endpoint policy tương đương yêu cầu production.
- Kiểm tra image, package và IaC artifact có nguồn tin cậy.
- Duy trì break-glass access được kiểm soát và thử nghiệm định kỳ.

Nếu DR được kích hoạt vì sự cố bảo mật thay vì lỗi Region, không nên replicate nguyên trạng một workload có thể đã bị compromise sang môi trường mới. Cần xác định recovery point sạch, rebuild từ artifact đáng tin cậy, rotate credential và điều tra persistence trước khi đưa workload trở lại.

## 15. Giám sát và readiness của Region dự phòng

Một môi trường warm standby có thể ngừng hoạt động âm thầm nếu không có traffic thường xuyên. Pilot light có thể bị lệch cấu hình hoặc image quá cũ. Vì vậy, cần monitoring liên tục.

Theo dõi:

- Replication lag, replica health và trạng thái promotion readiness.
- Backup/copy job status và tuổi recovery point.
- Trạng thái ECS/EKS/EC2 và khả năng scale.
- Load balancer health check và chứng chỉ.
- KMS key enabled state, IAM policy drift và secret availability.
- Route 53 health check, Global Accelerator endpoint health hoặc ARC routing control state.
- Service quota, subnet IP capacity và ENI.
- Log delivery, metric, alarm và kết nối tới hệ thống thông báo.

Readiness check không thay thế failover drill. Chỉ một bài diễn tập mới xác nhận được các bước có thể phối hợp để đạt RTO/RPO.

## 16. Diễn tập DR và kiểm chứng RTO/RPO

Nên kiểm thử theo mức độ tăng dần:

1. **Component test:** restore một database, tạo instance từ AMI, copy image hoặc xác minh secret tại Region đích.
2. **Partial failover:** khởi động ứng dụng ở Region dự phòng nhưng chưa chuyển toàn bộ traffic.
3. **Traffic shift test:** chuyển một phần hoặc toàn bộ traffic theo kế hoạch có kiểm soát.
4. **Regional game day:** giả lập Region chính không thể phục vụ và chạy toàn bộ runbook.
5. **Failback drill:** kiểm tra khả năng đưa dữ liệu và workload trở lại.

Ghi lại thời điểm declare, data ready, application ready, traffic switched và business validated. So sánh thời gian với RTO và điểm dữ liệu với RPO. Đừng chỉ ghi nhận lệnh automation kết thúc thành công.

### Những lỗi cần cố tình kiểm thử

- Replica có lag vượt RPO.
- KMS key tại Region đích bị disabled hoặc policy thiếu quyền.
- Secret chưa được replicate.
- Image hoặc AMI chưa có ở Region đích.
- Subnet thiếu IP hoặc quota không đủ.
- Health check chỉ kiểm tra HTTP nhưng database không ghi được.
- DNS resolver giữ cache lâu hơn dự kiến.
- Automation chạy lặp lại hoặc dừng giữa chừng.
- Region chính quay lại trong lúc Region DR đang nhận ghi.
- Log và alert không tới được đội trực.

## 17. Chi phí và tối ưu hóa

Pilot light thường có chi phí thấp hơn warm standby vì compute ít hoặc chưa chạy ở Region dự phòng. Tuy nhiên, vẫn có chi phí cho database replica, storage, snapshot copy, KMS, network, artifact replication, load balancer và monitoring.

Warm standby phát sinh thêm chi phí compute, load balancer, database capacity, network và telemetry do workload luôn chạy ở quy mô nhỏ. Khi failover, capacity phải được tăng đủ nhanh; nếu phải giữ capacity lớn để tránh scale delay, chi phí sẽ tiến gần production đầy đủ.

Để kiểm soát chi phí:

- Xác định tài nguyên nào phải chạy liên tục và tài nguyên nào có thể tạo khi failover.
- Dùng capacity tối thiểu nhưng đủ để health check và smoke test.
- Kiểm tra chi phí data replication, snapshot copy và cross-Region transfer.
- Dùng IaC để tạo tài nguyên nhất quán và xóa tài nguyên thử nghiệm đúng quy trình.
- Đo thời gian scale và kiểm tra quota trước khi giảm capacity.
- Rà soát retention backup và lifecycle.
- Gắn tag cost center, environment và workload ở cả hai Region.
- Theo dõi chi phí DR riêng để biết mức chi phí sẵn sàng so với chi phí khi failover.

Không giảm capacity dự phòng tới mức không thể chứng minh RTO. Chi phí DR là khoản đầu tư cho mức gián đoạn và mất dữ liệu mà nghiệp vụ đã chấp nhận.

## 18. Ví dụ lựa chọn: Orders cần RTO 20 phút

Một nền tảng thương mại điện tử đặt mục tiêu RTO 20 phút và RPO 5 phút cho dịch vụ Orders. Workload chạy ECS và Aurora; invoice lưu ở S3; cấu hình nằm trong Parameter Store và Secrets Manager.

**Pilot light** có thể được chọn nếu:

- Aurora Global Database secondary được duy trì và replication lag nằm trong ngưỡng.
- VPC, IAM, KMS, secret, ECR image và load balancer đã chuẩn bị.
- ECS service được triển khai khi failover bằng pipeline/runbook.
- Thời gian provision và warm-up đã được đo dưới ngân sách RTO.

**Warm standby** có thể được chọn nếu:

- ECS service và ALB đã chạy ở Region dự phòng với capacity nhỏ.
- Aurora secondary sẵn sàng promote.
- Smoke test định kỳ chứng minh ứng dụng kết nối database và downstream.
- Khi failover, chỉ cần promote, scale và chuyển traffic trong ngân sách 20 phút.

Nếu diễn tập pilot light mất 35 phút để tạo compute và xác minh luồng thanh toán, phương án chưa đạt RTO 20 phút. Tổ chức có thể chuyển sang warm standby, tăng mức automation hoặc thương lượng lại RTO với nghiệp vụ dựa trên BIA.

| Hạng mục | Pilot light | Warm standby |
|---|---|---|
| Aurora secondary | Duy trì | Duy trì |
| ECS service | Tạo khi failover | Chạy ở capacity nhỏ |
| ALB | Có thể tạo khi failover hoặc chuẩn bị sẵn | Chạy sẵn |
| ECR image | Replicate | Replicate |
| KMS/Secrets | Chuẩn bị sẵn | Chuẩn bị sẵn |
| Failover action | Deploy, scale, promote, validate, route | Promote, scale, validate, route |
| Chi phí liên tục | Thấp hơn | Cao hơn |
| RTO thực tế | Phải đo thời gian deploy/warm-up | Phải đo thời gian scale và chuyển traffic |

Không thể kết luận warm standby đạt RTO chỉ từ sơ đồ. Cả hai lựa chọn phải được diễn tập với dữ liệu, tải và quy trình tương tự tình huống thực tế.

## 19. Checklist triển khai pilot light hoặc warm standby

- [ ] RTO, RPO và phạm vi sự cố đã được nghiệp vụ phê duyệt.
- [ ] Đã chọn pilot light hoặc warm standby dựa trên kết quả BIA và chi phí.
- [ ] Region dự phòng có quota và capacity phù hợp.
- [ ] VPC, subnet, route, security group và endpoint đã được chuẩn bị.
- [ ] IAM role, KMS key, secret, certificate và parameter đã sẵn sàng.
- [ ] Database replication/backup đáp ứng RPO và có cảnh báo lag.
- [ ] Container image, AMI, IaC và deployment artifact đã được đồng bộ.
- [ ] Compute dự phòng có thể được tạo hoặc scale trong ngân sách RTO.
- [ ] Load balancer, DNS, Global Accelerator hoặc ARC đã được cấu hình.
- [ ] Monitoring, log, alert và quyền truy cập hoạt động ở Region dự phòng.
- [ ] Runbook có precondition, phê duyệt, timeout, retry và idempotency.
- [ ] Có cơ chế ngăn split-brain và xử lý ghi trong thời gian cutover.
- [ ] Có kế hoạch failback và đồng bộ dữ liệu ngược.
- [ ] Backup độc lập và bản sao bất biến được bảo vệ.
- [ ] Đã diễn tập component, failover, traffic shift và failback.
- [ ] RTO/RPO thực tế được đo và báo cáo cho owner.
- [ ] Chi phí sẵn sàng và chi phí khi failover được theo dõi.

## 20. Ghi nhớ

Pilot light giữ sẵn data và các thành phần nền tảng cốt lõi, sau đó tạo hoặc mở rộng compute khi failover. Warm standby duy trì một workload thu nhỏ nhưng hoạt động được, rồi tăng capacity và chuyển traffic khi cần. Warm standby thường đạt RTO ngắn hơn, nhưng tốn chi phí duy trì cao hơn.

RPO của hai chiến lược phụ thuộc chủ yếu vào cách dữ liệu được backup hoặc replicate; compute chạy sẵn không làm RPO tự động tốt hơn. Cả hai phương án đều cần chuẩn bị IAM, KMS, network, secrets, artifact, quota, DNS, monitoring và runbook. Replication phải đi cùng backup độc lập để bảo vệ khỏi corruption hoặc thao tác xóa bị sao chép.

Chọn chiến lược bằng BIA, RTO/RPO và chi phí; kiểm tra readiness liên tục; diễn tập failover và failback; đo thời gian tới khi nghiệp vụ hoạt động an toàn. Một môi trường DR chỉ có giá trị khi tổ chức chứng minh được nó có thể tiếp nhận workload trong mục tiêu đã cam kết.

## Tài liệu tham khảo

- [AWS Well-Architected: Disaster Recovery (DR) Objectives](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/disaster-recovery.html)
- [AWS Well-Architected: Use Defined Recovery Strategies](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html)
- [Disaster Recovery of Workloads on AWS: Pilot Light](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/pilot-light.html)
- [Disaster Recovery of Workloads on AWS: Warm Standby](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/warm-standby.html)
- [Amazon Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html)
- [Amazon RDS Cross-Region Read Replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.XRgn.html)
- [Amazon DynamoDB Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [Amazon S3 Replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [Amazon ECR Replication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/replication.html)
- [AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html)
- [Amazon Route 53 Failover Routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-failover.html)
- [AWS Global Accelerator](https://docs.aws.amazon.com/global-accelerator/latest/dg/what-is-global-accelerator.html)
- [AWS Application Recovery Controller](https://docs.aws.amazon.com/r53recovery/latest/dg/what-is-route53-recovery.html)
- [AWS Backup Cross-Region Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/cross-region-backup.html)
- [AWS Backup Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
