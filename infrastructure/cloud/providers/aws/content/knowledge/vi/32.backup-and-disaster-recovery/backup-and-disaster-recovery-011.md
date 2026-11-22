# Failover, failback và đồng bộ dữ liệu sau sự cố

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, khôi phục sau thảm họa không kết thúc ở việc khởi chạy máy chủ tại một Region khác. Đội vận hành còn phải xác định nơi giữ dữ liệu mới nhất, ngăn hai môi trường cùng ghi dữ liệu, chuyển traffic, xác minh ứng dụng và đưa hệ thống về trạng thái vận hành bền vững. Khi sự cố được xử lý, failback cần đồng bộ dữ liệu phát sinh tại môi trường dự phòng về môi trường chính, chuyển quyền ghi một cách có kiểm soát và thiết lập lại cơ chế bảo vệ DR.

AWS cung cấp nhiều thành phần cho quy trình này: AWS Elastic Disaster Recovery (DRS) để sao chép workload cấp máy chủ và khởi chạy recovery instances; Amazon Route 53 và Amazon Application Recovery Controller (ARC) để chuyển hướng traffic; ARC Region switch để điều phối quy trình đa Region; các cơ chế replication riêng của RDS, Aurora, DynamoDB, S3 và EFS; AWS Backup để lưu recovery points; cùng CloudWatch, EventBridge và Systems Manager để giám sát, tự động hóa.

Sau bài học, người học có thể:

- Phân biệt failover, switchover, failback, recovery drill và data replication.
- Thiết kế quy trình chuyển dịch vụ sang Region DR dựa trên RTO, RPO và trạng thái dữ liệu.
- Chọn cơ chế replication phù hợp với EC2/on-premises, database, object storage và file system.
- Kiểm soát replication lag, data consistency, write fencing và nguy cơ split-brain.
- Dùng AWS Elastic Disaster Recovery để recovery workload và reverse replication khi failback.
- Dùng Route 53 ARC routing controls hoặc Region switch để điều phối traffic và recovery workflow.
- Đồng bộ dữ liệu từ DR về primary, xác nhận điểm đồng bộ cuối và chuyển quyền ghi an toàn.
- Kiểm thử failover/failback định kỳ, ghi nhận RTO/RPO thực tế và cải thiện runbook.

## 1. Failover, switchover và failback là gì?

Các thuật ngữ này mô tả những thao tác khác nhau trong vòng đời khôi phục.

| Thuật ngữ | Ý nghĩa | Tình huống |
|---|---|---|
| Failover | Chuyển workload hoặc traffic từ môi trường chính bị lỗi sang môi trường dự phòng | Region chính mất khả năng phục vụ |
| Planned switchover | Chuyển vai trò primary/secondary trong điều kiện hai phía còn khỏe mạnh và có thể đồng bộ dữ liệu | Bảo trì, diễn tập hoặc luân phiên Region |
| Failback | Đưa workload từ môi trường đang phục vụ sau failover trở về môi trường chính ban đầu hoặc một đích vận hành mới | Sự cố đã được xử lý, primary sẵn sàng trở lại |
| Recovery drill | Thử khởi chạy workload từ dữ liệu replication/backup để xác minh khả năng phục hồi | Kiểm thử DR định kỳ |
| Reverse replication | Sao chép thay đổi từ recovery environment trở lại source environment | Chuẩn bị failback sau khi DR đã nhận ghi |
| Resynchronization | Đồng bộ lại hai tập dữ liệu sau khi một phía bị gián đoạn hoặc có thay đổi khác nhau | Khôi phục replication sau outage |

Failover và failback là các hoạt động thay đổi quyền phục vụ. Replication chỉ vận chuyển dữ liệu. Một hệ thống có replication hoạt động không có nghĩa là đã có failover tự động, DNS đã chuyển, ứng dụng đã khởi động hoặc người dùng có thể ghi dữ liệu.

Với planned switchover, cả primary và secondary còn hoạt động nên có thể đồng bộ dữ liệu và dừng ghi theo kế hoạch trước khi đổi vai trò. Với unplanned failover, primary có thể không truy cập được; tổ chức phải chọn một recovery point hoặc secondary replica, chấp nhận RPO thực tế và bảo đảm primary cũ không tiếp tục ghi khi nó xuất hiện trở lại.

Failback không đơn giản là đổi DNS về địa chỉ cũ. Trong thời gian DR phục vụ, dữ liệu có thể đã thay đổi. Nếu primary cũ chưa nhận các thay đổi đó, chuyển traffic về primary ngay sẽ làm mất giao dịch mới hoặc tạo hai nhánh dữ liệu không nhất quán.

## 2. Xác định RPO, RTO và chiến lược DR

Trước khi thiết kế quy trình, cần xác định hai mục tiêu:

- **Recovery Point Objective (RPO):** mức mất dữ liệu tối đa có thể chấp nhận, đo bằng khoảng thời gian dữ liệu chưa được sao chép hoặc backup.
- **Recovery Time Objective (RTO):** thời gian tối đa để khôi phục dịch vụ về mức hoạt động được chấp nhận.

RPO và RTO cần được xác định cho từng thành phần của ứng dụng. API có thể cần RTO vài phút nhưng báo cáo phân tích có thể chấp nhận vài giờ. Database giao dịch có thể cần RPO rất thấp, trong khi file log hoặc dữ liệu cache có thể được tái tạo.

Các chiến lược DR thường được sắp xếp từ chi phí thấp/thời gian phục hồi dài tới chi phí cao/thời gian phục hồi ngắn:

| Chiến lược | Môi trường DR | RPO/RTO tham khảo | Chi phí tương đối |
|---|---|---|---|
| Backup and restore | Dữ liệu được backup/copy; hạ tầng được tạo khi có sự cố | RPO thường tính bằng giờ; RTO có thể nhiều giờ | Thấp |
| Pilot light | Thành phần lõi và dữ liệu đã có ở DR; một phần compute chưa chạy | RPO từ vài phút tới hàng chục phút; RTO thường hàng chục phút | Trung bình |
| Warm standby | Toàn bộ stack chạy ở quy mô nhỏ và có thể nhận traffic | RPO từ giây tới phút; RTO vài phút tùy kiến trúc | Cao |
| Multi-site active/active | Nhiều Region cùng phục vụ traffic | RPO/RTO có thể gần bằng 0 nếu thiết kế phù hợp | Rất cao |

Đây là khoảng tham khảo từ hướng dẫn kiến trúc AWS, không phải cam kết dịch vụ. RPO/RTO thực tế phụ thuộc replication lag, kích thước dữ liệu, thời gian provision, quota, quy trình DNS, khả năng ứng dụng và kết quả diễn tập.

Ví dụ, một ứng dụng đặt hàng có thể chọn Aurora Global Database để giảm độ trễ replication, warm standby cho application tier và Route 53 ARC để chuyển traffic. Một hệ thống nội bộ ít quan trọng có thể dùng AWS Backup cross-Region copy và Infrastructure as Code để tạo lại hạ tầng khi cần.

Không chọn chiến lược chỉ dựa trên RTO. Hãy tính cả chi phí duy trì Region dự phòng, độ phức tạp vận hành, khả năng kiểm thử, yêu cầu nhất quán dữ liệu và năng lực đội trực.

## 3. Phân rã ứng dụng thành các lớp cần khôi phục

Một ứng dụng thực tế thường gồm nhiều thành phần phụ thuộc nhau. Failover chỉ thành công khi các thành phần cần thiết sẵn sàng theo đúng thứ tự.

Ví dụ kiến trúc ba lớp:

~~~mermaid
flowchart TD
    U[Users and API clients] --> DNS[Route 53 or ARC routing]
    DNS --> P[Primary Region]
    DNS -. failover .-> D[DR Region]
    subgraph P[Primary Region]
      PA[Application fleet]
      PD[Primary database]
      PS[Secrets and configuration]
      PN[Network, endpoints and load balancer]
      PA --> PD
      PA --> PS
      PA --> PN
    end
    subgraph D[DR Region]
      DA[Recovery application fleet]
      DD[Replicated or restored database]
      DS[Regional secrets and configuration]
      DN[Network, endpoints and load balancer]
      DA --> DD
      DA --> DS
      DA --> DN
    end
~~~

Các lớp cần đưa vào dependency map:

- **Traffic entry:** DNS, CloudFront, Global Accelerator, API Gateway, load balancer, routing controls.
- **Compute:** EC2, Auto Scaling, ECS, EKS, Lambda hoặc máy chủ ngoài AWS.
- **Data:** RDS, Aurora, DynamoDB, S3, EFS, FSx, EBS hoặc hệ thống database tự quản.
- **Identity and secrets:** IAM roles, Cognito, Secrets Manager, Systems Manager Parameter Store, certificates.
- **Network:** VPC, subnet, route table, security group, NACL, NAT, Transit Gateway, VPN và Direct Connect.
- **Shared services:** DNS resolver, container registry, artifact repository, logging, monitoring, queues và event bus.
- **Operations:** backup vault, KMS key, Systems Manager, automation role, runbook và incident communication.

Tạo dependency map giúp xác định thứ tự recovery. Ví dụ, application server không thể chạy đúng nếu database chưa được promote hoặc secret tại Region đích vẫn trỏ tới endpoint cũ. DNS có thể chuyển thành công nhưng traffic vẫn lỗi nếu security group, certificate, WAF, IAM role hoặc quota chưa sẵn sàng.

## 4. Chọn cơ chế đồng bộ theo loại dữ liệu

Không có một cơ chế replication phù hợp cho mọi loại dữ liệu. Hãy chọn theo yêu cầu nhất quán, RPO, khối lượng thay đổi, khả năng ghi đồng thời và cách restore.

| Loại workload/dữ liệu | Cơ chế thường dùng | Điểm cần lưu ý khi failover |
|---|---|---|
| Máy chủ và workload cấp OS | AWS Elastic Disaster Recovery | Continuous block replication tới staging area; recovery instance cần launch và kiểm tra |
| RDS DB instance | Cross-Region read replica hoặc snapshot/copy | Replication thường bất đồng bộ; cần đo lag và promote replica |
| Aurora | Aurora Global Database | Secondary Region có thể được promote; unplanned failover có thể mất giao dịch chưa replicate |
| DynamoDB | Global tables | Nhiều Region có thể nhận ghi; phải thiết kế xử lý conflict và nhất quán ứng dụng |
| Amazon S3 | Cross-Region Replication (CRR) hoặc Same-Region Replication | Replication bất đồng bộ; kiểm tra versioning, delete marker, replication status và object ownership |
| Amazon EFS | EFS replication | Đồng bộ bất đồng bộ; kiểm tra replication status, destination state và quy trình chuyển quyền ghi |
| File server/on-premises | AWS DataSync hoặc công cụ đồng bộ phù hợp | Phù hợp bulk/periodic sync; cần lập lịch, kiểm tra file đang thay đổi và final sync |
| Backup dài hạn | AWS Backup cross-Region/cross-account copy | Recovery point phục vụ restore; không phải live replication hay active-active |

Các cơ chế có thể được kết hợp. Ví dụ, DRS bảo vệ máy chủ, Aurora Global Database bảo vệ database, S3 CRR bảo vệ object, còn AWS Backup giữ recovery point độc lập. Tuy nhiên, cần xác định dữ liệu nào là authoritative và thành phần nào được phép ghi trong từng giai đoạn.

Replication cũng có thể sao chép dữ liệu đã bị hỏng, bị mã hóa bởi ransomware hoặc bị xóa theo logic ứng dụng. Vì vậy, replication không thay thế backup có retention và point-in-time recovery. Một thiết kế DR đầy đủ thường cần cả replication để giảm RPO và backup để phục hồi về thời điểm trước khi dữ liệu bị hỏng.

## 5. Replication lag, consistency và thứ tự giao dịch

Replication lag là khoảng thời gian hoặc lượng thay đổi chưa được áp dụng tại đích. Với asynchronous replication, primary có thể xác nhận giao dịch trước khi secondary nhận giao dịch đó. Nếu primary bị mất ngay sau khi commit, secondary có thể thiếu một số giao dịch cuối.

Cần theo dõi các chỉ số:

- **Lag theo thời gian:** secondary đang chậm bao nhiêu giây/phút so với primary.
- **Backlog:** lượng thay đổi chưa được gửi hoặc áp dụng.
- **Throughput:** tốc độ tạo thay đổi so với tốc độ replicate.
- **Replication errors:** lỗi permission, network, quota hoặc dữ liệu không hợp lệ.
- **Last replicated position:** log sequence number, transaction ID, checkpoint hoặc watermark cuối đã đồng bộ.
- **Data validation:** số bản ghi, checksum, object count hoặc business invariant sau đồng bộ.

Ví dụ: database tạo 5.000 transaction mỗi phút nhưng replication chỉ áp dụng được 4.000 transaction mỗi phút. Backlog tăng 1.000 transaction mỗi phút. Khi đó, replication lag sẽ tăng dù trạng thái service vẫn là RUNNING.

Không chỉ kiểm tra một metric. Với database, cần xem lag ở cả tầng storage và database instance. Với file/object, cần kiểm tra replication status của đối tượng hoặc timestamp hoàn tất. Với DRS, cần xem lag theo từng source server và thời điểm recovery point gần nhất.

Một số ứng dụng cần consistency giữa nhiều nguồn. Ví dụ, database lưu đơn hàng và S3 lưu hóa đơn. Nếu failover database đã có đơn hàng mới nhưng S3 chưa replicate hóa đơn tương ứng, ứng dụng có thể thấy trạng thái không đồng nhất. Cần xác định transaction boundary và dùng outbox/event pattern, idempotent consumer hoặc reconciliation job để sửa sai lệch sau recovery.

## 6. Ngăn split-brain và kiểm soát quyền ghi

Split-brain xảy ra khi hai môi trường cùng nghĩ rằng mình là primary và cùng nhận ghi cho một tập dữ liệu. Khi đó, các thay đổi có thể phân kỳ và khó hợp nhất.

Trước khi chuyển traffic hoặc promote secondary, hãy xác định:

1. Primary cũ còn nhận write request hay không.
2. Có thể stop application, revoke writer credentials, disable endpoint hoặc fence storage/database cũ không.
3. Secondary đã sẵn sàng nhận write chưa.
4. Replication đã dừng hay vẫn còn một chiều.
5. Có client hoặc background worker nào tiếp tục ghi vào endpoint cũ không.

**Write fencing** là biện pháp ngăn hệ thống cũ tiếp tục ghi. Có thể thực hiện bằng cách dừng application, thu hồi credential, vô hiệu hóa writer endpoint, chặn network, chuyển database về read-only hoặc dùng cơ chế fencing token/lease do ứng dụng quản lý. Không dựa vào việc DNS đã đổi để kết luận primary cũ không còn ghi: client có thể giữ DNS cache hoặc connection pool cũ.

Với active/passive, chỉ một Region được phép ghi cho mỗi dữ liệu authoritative. Với active/active, cần cơ chế xử lý ghi đồng thời rõ ràng, chẳng hạn partition theo tenant/region, conflict resolution, versioning hoặc transactional coordination. Nếu chưa có thiết kế conflict resolution, không bật ghi đồng thời chỉ vì cả hai Region đều đang khỏe.

Một quy tắc vận hành hữu ích là ghi nhận rõ trạng thái quyền ghi:

| Giai đoạn | Primary cũ | DR Region | Điều kiện chuyển bước |
|---|---|---|---|
| Bình thường | Read/write | Replica hoặc read-only | Replication khỏe |
| Declared disaster | Fence hoặc không thể truy cập | Chưa nhận ghi | Đã xác định nguồn sự cố và điểm dữ liệu |
| DR active | Không được ghi | Read/write | Secondary đã promote và kiểm tra |
| Reverse sync | Read-only hoặc isolated | Read/write | Dữ liệu DR là authoritative |
| Final failback | Fence DR writes | Chuẩn bị nhận ghi | Primary đã đồng bộ và xác nhận |
| Primary restored | Read/write | Replica/read-only | Traffic, health và replication ổn định |

## 7. Failover từ primary sang DR

Một quy trình failover nên có các checkpoint rõ ràng. Không tự động chuyển traffic chỉ dựa trên một alarm nếu chưa kiểm tra trạng thái dữ liệu và năng lực DR.

~~~mermaid
flowchart TD
    A[Alert and incident declaration] --> B[Assess primary health and blast radius]
    B --> C{Can primary safely serve writes?}
    C -- Yes --> D[Repair or controlled switchover]
    C -- No --> E[Fence old primary if possible]
    E --> F[Choose DR recovery point or replica]
    F --> G[Promote or launch DR data and compute]
    G --> H[Validate dependencies and application]
    H --> I{Health checks pass?}
    I -- No --> J[Stop traffic shift and troubleshoot]
    I -- Yes --> K[Shift traffic to DR]
    K --> L[Monitor errors, latency and data writes]
    L --> M[Declare DR as authoritative]
~~~

Trình tự chi tiết:

1. **Declare incident:** xác định incident commander, người quyết định failover và phạm vi ứng dụng/Region bị ảnh hưởng.
2. **Assess primary:** phân biệt sự cố ứng dụng cục bộ, AZ hay Region. Nếu primary vẫn hoạt động an toàn, cân nhắc repair hoặc planned switchover.
3. **Fence writes:** nếu primary mất khả năng phục vụ, chặn khả năng ghi từ môi trường cũ khi có thể.
4. **Select recovery point:** chọn secondary replica hoặc recovery point có lag thấp nhất và phù hợp RPO.
5. **Promote/launch:** promote database, launch EC2 recovery instances, scale ECS/EKS, restore resources hoặc kích hoạt service tại DR.
6. **Restore dependencies:** cấu hình secret, IAM, certificates, endpoints, network, queues và storage.
7. **Validate:** chạy smoke test, kiểm tra transaction, đọc/ghi thử, health check và business invariants.
8. **Shift traffic:** chuyển DNS/routing control/Global Accelerator tới DR.
9. **Observe:** theo dõi error rate, latency, database connections, queue depth và replication state.
10. **Declare authority:** ghi nhận Region nào đang là nguồn dữ liệu chính và thông báo cho các nhóm liên quan.

Nếu primary không thể fence do Region bị cô lập, không nên cho phép DR và primary cùng nhận ghi khi primary có thể tự phục hồi mạng. Cần một cơ chế authority rõ ràng và quy trình xác nhận primary cũ đã bị cô lập trước khi mở write tại DR.

## 8. Chuyển hướng traffic với Route 53 và ARC

Traffic cutover là bước riêng biệt với data promotion. Có thể dùng Route 53 failover routing, health checks, weighted routing hoặc Amazon Route 53 ARC routing controls.

### 8.1. Route 53 DNS failover

Route 53 có thể dùng failover routing policy để trả endpoint primary hoặc secondary dựa trên health check. Khi endpoint chính unhealthy, DNS có thể trả endpoint DR.

Cần cân nhắc:

- TTL của DNS record và cache ở resolver/client.
- DNS cache trong JVM, container runtime, proxy và connection pool.
- Health check có phản ánh khả năng xử lý giao dịch thực tế hay chỉ kiểm tra TCP/HTTP đơn giản.
- Endpoint DR đã đủ capacity và đã được kiểm thử chưa.
- Client có retry và xử lý connection reset đúng cách không.

DNS failover không thể buộc mọi client cập nhật ngay lập tức. Một số client giữ connection hoặc cache lâu hơn TTL. Vì vậy, sau khi đổi DNS, cần tiếp tục theo dõi traffic còn tới primary cũ.

### 8.2. ARC routing controls

Amazon Application Recovery Controller routing control cung cấp công tắc On/Off để chuyển traffic giữa các replica. Routing control được liên kết với Route 53 health checks và DNS records. Khi đổi state, ARC cập nhật health check tương ứng để Route 53 chuyển traffic.

Routing control không tự giám sát endpoint hoặc đo response time. Nó là cơ chế điều khiển chuyển hướng, vì vậy cần kết hợp với monitoring và quyết định failover phù hợp.

ARC có safety rules để ngăn thao tác routing tạo ra trạng thái không an toàn. Ví dụ, assertion rule có thể yêu cầu ít nhất một Region luôn được bật traffic. Nếu cần break-glass trong thảm họa, có thể override safety rule theo quy trình đã phê duyệt và ghi lại lý do.

ARC routing control cluster có năm Regional endpoints. Automation nên thử các endpoint lần lượt nếu endpoint đang kết nối không khả dụng. AWS khuyến nghị dùng data plane API/CLI để cập nhật routing control trong critical path thay vì phụ thuộc console.

### 8.3. ARC Region switch

Region switch trong ARC hỗ trợ điều phối recovery đa Region bằng plan. Plan gồm workflow, step và execution block; các bước có thể chạy tuần tự hoặc song song. Có thể dùng cho active/passive hoặc active/active, hỗ trợ tài nguyên cross-account và kích hoạt thủ công hoặc bằng CloudWatch alarm.

Region switch có plan evaluation để kiểm tra IAM permissions, resource configuration và capacity; việc đánh giá được thực hiện khi tạo/cập nhật plan và định kỳ khoảng 30 phút trong steady state. Service quota checks có thể phát hiện khác biệt quota giữa account/Region, nhưng quota parity không bảo đảm chắc chắn execution sẽ thành công. Vẫn cần chạy drill thực tế.

Tại thời điểm biên soạn, ARC Readiness Check đã đóng cho khách hàng mới; AWS khuyến nghị khách hàng mới có nhu cầu orchestration multi-Region xem xét Region switch. ARC routing controls, zonal shift, zonal autoshift và Region switch tiếp tục được hỗ trợ. Zonal shift xử lý việc chuyển traffic khỏi AZ bị ảnh hưởng trong cùng Region; nó không thay thế quy trình failover sang Region khác.

## 9. AWS Elastic Disaster Recovery: recovery và reverse replication

AWS Elastic Disaster Recovery (DRS) hỗ trợ bảo vệ máy chủ on-premises, máy chủ trên AWS và một số cloud environment bằng continuous block-level replication tới staging area subnet trong AWS Region đích. Staging area sử dụng storage và compute tối thiểu để duy trì replication. Khi cần, có thể launch drill instances hoặc recovery instances trên AWS.

Quy trình DRS tổng quát:

1. Cài đặt replication agent trên source servers.
2. Cấu hình replication settings, staging area subnet, security group, disks và bandwidth.
3. Chờ initial sync hoàn tất.
4. Theo dõi data replication và lag.
5. Cấu hình launch settings để recovery instance có instance type, subnet, security group, IAM role và network phù hợp.
6. Chạy recovery drill định kỳ để xác nhận instance có thể boot và ứng dụng hoạt động.
7. Khi có thảm họa, khởi chạy recovery instances từ điểm thời gian phù hợp.
8. Kiểm tra ứng dụng và chuyển traffic bằng Route 53 hoặc traffic manager của tổ chức.

DRS hỗ trợ khởi chạy recovery instances, nhưng việc chuyển traffic sang các instance đó được thực hiện bên ngoài DRS. Cần phối hợp DRS với Route 53, ARC hoặc giải pháp traffic management khác.

### 9.1. Failback với DRS

Khi source environment đã được khôi phục, dữ liệu có thể đã thay đổi trên recovery instances. DRS hỗ trợ reverse replication để đưa các thay đổi từ recovery environment về source servers.

Một quy trình điển hình:

1. Khôi phục source infrastructure và bảo đảm nó an toàn để nhận dữ liệu.
2. Xác nhận recovery instances là nguồn dữ liệu authoritative.
3. Bắt đầu reversed replication từ recovery instances về source servers.
4. Theo dõi replication state và lag cho tới khi trạng thái Ready hoặc Ready with lag theo điều kiện của DRS.
5. Nếu cần giảm mất dữ liệu, dừng hoặc quiesce ứng dụng ghi tại DR trong cửa sổ final sync.
6. Chạy failback launch để khởi chạy các server đã được cập nhật tại source infrastructure.
7. Kiểm tra ứng dụng, network, storage, identity và business transactions trên source.
8. Chuyển traffic về source bằng Route 53 hoặc traffic manager.
9. Bảo đảm chỉ source mới nhận ghi; recovery environment không còn tiếp tục nhận write.
10. Sau khi ổn định, thiết lập lại replication từ source mới về Region DR để khôi phục trạng thái bảo vệ.

Đối với source on-premises, failback có thể dùng Failback Client ISO hoặc DRS Failback Automation. Với source là EC2 cùng account hoặc cross-account, có thể khởi động reverse replication từ recovery instance theo hướng dẫn DRS tương ứng. Cần kiểm tra giới hạn kiến trúc và hệ điều hành; ví dụ Failback Client hỗ trợ x86_64, trong khi ARM64 có các giới hạn failback riêng.

DRS không tự thực hiện bước chuyển traffic trong failback. Đội vận hành phải điều khiển DNS hoặc routing sau khi xác nhận dữ liệu đã đồng bộ và workload tại source đã sẵn sàng.

Không chạy bước thay thế source replication trong recovery drill theo cách có thể làm thay đổi production protection. Drill phải giữ nguyên source servers đang phục vụ và replication bình thường.

## 10. Failover và failback cho database

Database thường là thành phần khó nhất vì transaction, replication lag, connection pool và quyền ghi phải được kiểm soát chặt.

### 10.1. Amazon RDS cross-Region read replica

RDS có thể tạo read replica ở Region khác cho các engine và cấu hình được hỗ trợ. Replication thường bất đồng bộ. Khi primary gặp sự cố, có thể promote read replica thành standalone DB instance để nhận ghi.

Trước khi promote:

- Kiểm tra replication lag và thời điểm cập nhật cuối.
- Xác định giao dịch cuối cùng có thể đã mất.
- Dừng hoặc fence write traffic tại primary nếu còn truy cập được.
- Kiểm tra engine version, parameter group, option group, subnet group và security group.
- Cập nhật ứng dụng để dùng endpoint của DB đã promote.

Sau khi failover, replica đã promote không còn là read replica của primary cũ. Để failback, cần xây dựng lại quan hệ replication từ DB đang authoritative tại DR về một đích mới hoặc primary cũ đã được phục hồi. Không thể đơn giản đảo chiều một replica đã promote mà không cấu hình lại topology.

### 10.2. Aurora Global Database

Aurora Global Database dùng replication vật lý bất đồng bộ giữa các Region. Secondary Region có thể phục vụ read traffic; khi cần, có thể promote thành primary.

Cần phân biệt:

- **Switchover:** dùng khi các cluster và dịch vụ liên quan đều khỏe mạnh, thường cho bảo trì hoặc planned Region rotation. Aurora đồng bộ secondary trước khi đổi vai trò, hướng tới RPO bằng 0.
- **Unplanned failover:** dùng khi primary Region gặp sự cố. Secondary được promote nhanh, nhưng RPO thường là giá trị khác 0 tính bằng giây, phụ thuộc replication lag lúc sự cố.

Với unplanned failover, một số transaction có thể chưa replicate tới secondary. Aurora có thể tạo snapshot của storage volume cũ để hỗ trợ khôi phục dữ liệu bị thiếu nếu thao tác đó thành công. Sau khi failover, các secondary Region khác có thể cần được rebuild từ primary mới.

Cần lưu ý nguy cơ split-brain. Aurora cố gắng write fencing old primary trong managed failover, nhưng đây là best-effort và có thể không thành công đúng hạn trong một số tình huống. Nếu primary cũ còn truy cập được, cần kiểm tra event liên quan tới việc dừng ghi và việc client đã nhận endpoint mới trước khi mở write traffic rộng rãi. Giảm DNS cache duration có thể giúp giảm nguy cơ client tiếp tục ghi vào endpoint cũ, nhưng không thay thế fencing và kiểm soát ứng dụng.

Planned switchover và unplanned failover có mục tiêu dữ liệu khác nhau. Không dùng switchover khi primary hoặc secondary đang bị suy giảm nghiêm trọng mà chưa xác minh khả năng đồng bộ.

### 10.3. DynamoDB global tables

DynamoDB global tables cho phép bảng được sao chép giữa các Region và hỗ trợ đọc/ghi tại nhiều replica Region. Đây là mô hình multi-Region, multi-active. Khi tạo global table, phải chọn một trong hai consistency mode: Multi-Region eventual consistency (MREC) hoặc Multi-Region strong consistency (MRSC). Không thể đổi consistency mode sau khi tạo bảng.

| Chế độ | Replication và consistency | RPO và giới hạn chính |
|---|---|---|
| MREC | Replication bất đồng bộ; thay đổi thường lan truyền trong khoảng một giây hoặc ít hơn. Xung đột cùng item được giải quyết theo last-writer-wins dựa trên timestamp nội bộ. | RPO bằng replication delay, thường vài giây; multi-account global tables chỉ hỗ trợ MREC. Transaction chỉ atomic trong Region gọi và có thể quan sát trạng thái chưa đồng bộ ở Region khác. |
| MRSC | Ghi được replicate đồng bộ tới ít nhất một Region khác trước khi trả thành công; strong read ở replica trả phiên bản mới nhất. | RPO bằng 0 theo mô hình hỗ trợ; cần đúng ba Region (ba replicas hoặc hai replicas và một witness), có giới hạn Region set; không hỗ trợ TTL, LSI hoặc transaction APIs. |

MRSC tăng độ trễ ghi và strong read do cần giao tiếp liên Region. Khi hai Region cập nhật cùng item cạnh tranh, thao tác có thể nhận ReplicatedWriteConflictException và cần retry có kiểm soát. Hãy xác nhận Region set, account model và giới hạn tính năng trước khi chọn MRSC. Với MREC, theo dõi CloudWatch ReplicationLatency; metric này không phải SLA về thời gian replication.

Cần thiết kế rõ:

- Client chọn Region nào để đọc và ghi.
- Các thao tác đồng thời trên cùng item được xử lý theo conflict-resolution semantics của consistency mode đã chọn.
- Business invariant nào phải được thực thi ở một nơi hoặc bằng transactional workflow.
- Retry và idempotency key để tránh tạo giao dịch lặp.
- Cách ứng dụng phát hiện Region active và tránh tiếp tục ghi vào Region đã bị cô lập.
- Backup/PITR độc lập để phục hồi khi lỗi logic hoặc dữ liệu bị xóa lan truyền.

Global tables giảm phụ thuộc vào một primary duy nhất, nhưng không loại bỏ mọi conflict nghiệp vụ. Nếu hai Region cùng cập nhật cùng một item, ứng dụng cần hiểu cách hệ thống giải quyết phiên bản và thiết kế dữ liệu phù hợp.

## 11. Failover cho object và file storage

### 11.1. Amazon S3 Cross-Region Replication

S3 CRR sao chép object mới và object được cập nhật theo replication rule từ source bucket sang destination bucket ở Region khác. Hai bucket cần bật versioning. IAM replication role phải có quyền đọc version nguồn và ghi object/replica tại đích. Nếu dùng SSE-KMS, cần cấu hình KMS key policy cho cả hai phía.

Các điểm cần kiểm tra:

- Replication là bất đồng bộ; không giả định object vừa PUT đã có ở destination.
- Kiểm tra replication status của object và replication metrics.
- Replication Time Control (RTC) có thể giúp theo dõi mục tiêu thời gian replication cho phần lớn object; nó không thay thế kiểm tra từng object quan trọng.
- Delete marker replication và delete replication behavior cần được cấu hình, hiểu rõ theo loại rule. Không giả định mọi thao tác xóa sẽ được replicate giống nhau.
- Object tồn tại trước khi bật rule cần S3 Batch Replication nếu muốn replicate dữ liệu cũ.
- Object Lock, ownership, ACL và KMS key cần được cấu hình phù hợp với destination.
- Nếu failover sang bucket đích, cần chuyển ứng dụng sang endpoint bucket đó và kiểm tra quyền write.

Sau khi DR nhận ghi, muốn failback cần có chiến lược đồng bộ thay đổi ngược về bucket primary. Có thể cấu hình replication theo chiều ngược hoặc dùng S3 Batch Replication/DataSync tùy quy mô và yêu cầu. Trước khi chuyển ứng dụng về bucket cũ, phải xác nhận mọi object mới, version và delete marker cần thiết đã được xử lý. Không bật hai chiều replication một cách thiếu kiểm soát nếu chưa thiết kế cách xử lý vòng lặp và conflict.

### 11.2. Amazon EFS và DataSync

EFS replication hỗ trợ sao chép file system sang một file system khác, thường ở Region khác. Destination được dùng làm bản sao phục hồi; trước khi chuyển sang ghi ở đích, hãy kiểm tra replication state, thời điểm đồng bộ gần nhất và quy trình promote/failover theo hướng dẫn EFS hiện hành.

AWS DataSync phù hợp cho việc di chuyển hoặc đồng bộ file theo task giữa on-premises, EFS, FSx và S3. DataSync có thể chạy theo lịch để chuyển các thay đổi định kỳ. Nó không tự biến một file share thành active-active filesystem. Cần xác định cách xử lý file đang mở, file bị đổi trong lúc copy, permission metadata và final sync trước cutover.

Với file system, hãy xác minh số lượng file, kích thước, checksum hoặc manifest sau đồng bộ. Nếu ứng dụng ghi đồng thời ở hai nơi, cần một quy tắc rõ ràng để quyết định phiên bản nào được giữ.

## 12. Quy trình failback và đồng bộ dữ liệu về primary

Sau khi DR đã phục vụ production, failback cần được xem như một thay đổi production lớn. Hãy lập kế hoạch, thông báo downtime hoặc maintenance window nếu cần và có tiêu chí dừng.

~~~mermaid
flowchart TD
    A[Resolve primary Region issue] --> B[Rebuild and secure primary]
    B --> C[Start reverse replication from DR]
    C --> D[Monitor lag and validate data]
    D --> E{Ready for final sync?}
    E -- No --> C
    E -- Yes --> F[Quiesce writes in DR]
    F --> G[Final sync and fence DR writer]
    G --> H[Promote or activate primary]
    H --> I[Run smoke and business validation]
    I --> J{Primary healthy?}
    J -- No --> K[Keep DR authoritative]
    J -- Yes --> L[Shift traffic to primary]
    L --> M[Re-establish replication to DR]
    M --> N[Verify protection restored]
~~~

Các bước chi tiết:

1. **Xác nhận nguyên nhân gốc đã được xử lý:** kiểm tra Region, network, account permissions, quota và dịch vụ phụ thuộc.
2. **Chuẩn bị primary:** vá lỗi, khôi phục capacity, cấu hình security, secrets, KMS, DNS, monitoring và endpoint.
3. **Xác định nguồn dữ liệu chuẩn:** trong giai đoạn DR active, dữ liệu ở DR thường là authoritative. Không lấy dữ liệu từ primary cũ làm nguồn chính nếu chưa reconcile.
4. **Bắt đầu reverse replication:** cấu hình replication từ DR về primary theo công cụ của dịch vụ.
5. **Theo dõi lag:** đợi backlog giảm tới ngưỡng được phê duyệt; xác nhận checkpoint cuối đã đồng bộ.
6. **Quiesce writes:** đưa ứng dụng vào maintenance/read-only hoặc dừng writer/queue consumer tại DR.
7. **Final sync:** hoàn tất thay đổi cuối cùng và kiểm tra số liệu/transaction.
8. **Fence DR writer:** ngăn DR tiếp tục nhận ghi trước khi primary nhận ghi.
9. **Promote/activate primary:** chuyển database hoặc storage tại primary thành nguồn ghi.
10. **Validate:** kiểm tra business transactions, schema, object count, permissions, endpoint và health checks.
11. **Switch traffic:** chuyển DNS/routing về primary.
12. **Monitor:** theo dõi traffic còn đến DR, lỗi kết nối, replication và dữ liệu mới.
13. **Re-establish DR:** cấu hình replication theo chiều primary mới sang DR.
14. **Declare normal operations:** chỉ kết thúc incident khi primary ổn định và khả năng bảo vệ DR đã được khôi phục.

Nếu không thể dừng ghi hoàn toàn, cần một giao thức nhất quán có version/watermark, transaction log hoặc application-level fencing. Đừng dựa vào đồng hồ hệ thống để quyết định bản ghi mới hơn nếu clock skew có thể xảy ra.

## 13. Đối chiếu và reconciliation sau khi hai phía đã ghi

Nếu primary và DR đều nhận ghi trong thời gian sự cố, dữ liệu có thể phân kỳ. Trước khi failback, cần reconciliation.

Một số chiến lược:

- **Single-writer:** chỉ một Region được ghi cho mỗi dataset; cách đơn giản nhất để tránh conflict.
- **Partition ownership:** mỗi Region sở hữu một tập tenant, account hoặc key range.
- **Version vector hoặc revision number:** dùng version để phát hiện thay đổi cạnh tranh.
- **Conflict resolution:** áp dụng quy tắc nghiệp vụ như last-write-wins, merge hoặc manual review.
- **Event replay:** lưu event/transaction log và replay phần thiếu theo thứ tự.
- **Idempotent operations:** dùng idempotency key để retry mà không tạo giao dịch trùng.
- **Reconciliation job:** so sánh tổng số, checksum, trạng thái nghiệp vụ và tạo danh sách sai lệch.

Ví dụ với đơn hàng:

- Đơn hàng có OrderId duy nhất và version tăng theo mỗi lần cập nhật.
- Mỗi giao dịch có idempotency key.
- DR lưu event outbox để biết thay đổi nào đã phát sinh.
- Khi primary trở lại, hệ thống đối chiếu OrderId/version, thanh toán, tồn kho và hóa đơn.
- Giao dịch không thể tự merge được đưa vào hàng đợi manual review.
- Chỉ sau khi reconciliation hoàn tất mới mở write traffic tại primary.

Không xóa bản ghi xung đột để làm cho hai database có vẻ giống nhau. Hãy lưu audit trail, quyết định nghiệp vụ và người phê duyệt đối với mọi thao tác reconciliation có thể ảnh hưởng tài chính hoặc dữ liệu khách hàng.

## 14. Điều phối recovery với ARC Region switch và Systems Manager

Với ứng dụng nhiều thành phần, script failover riêng lẻ rất dễ chạy sai thứ tự. Có thể dùng ARC Region switch để mô hình hóa workflow theo application recovery plan.

Ví dụ một plan active/passive:

1. Xác nhận target Region và trạng thái resource.
2. Scale up compute và database dependencies.
3. Promote database hoặc kích hoạt data endpoint.
4. Cập nhật secret/configuration.
5. Chạy health check và smoke test.
6. Chuyển routing control hoặc DNS.
7. Kiểm tra CloudWatch alarms và application metrics.
8. Ghi execution result và thông báo incident commander.

Region switch có thể chạy execution block tuần tự hoặc song song. Có thể tạo parent plan chứa child plans cho các application tiers hoặc nhóm dịch vụ. Khi thiết kế, chỉ chạy song song các bước không phụ thuộc dữ liệu hoặc trạng thái của nhau.

Systems Manager Automation có thể xử lý tác vụ cụ thể như kiểm tra EC2, cập nhật cấu hình, gọi API hoặc chạy lệnh trên managed node. Step Functions có thể điều phối logic ứng dụng và tích hợp các service API. EventBridge có thể kích hoạt workflow từ alarm hoặc sự kiện. Dù dùng công cụ nào, cần có idempotency, retry có giới hạn, approval và bước kiểm tra hậu điều kiện.

Không nên tự động failover chỉ từ một alarm đơn lẻ nếu chưa xác định false positive, maintenance window, replication lag và capacity DR. Với thao tác không thể đảo ngược hoặc có thể làm mất dữ liệu, cần human approval hoặc break-glass process đã được diễn tập.

## 15. Kiểm thử failover và failback

Một kế hoạch DR chỉ đáng tin cậy khi đã được kiểm thử. Không đợi thảm họa thật mới xác nhận role, quota, network và DNS.

Các loại kiểm thử:

| Loại kiểm thử | Mục tiêu | Tác động |
|---|---|---|
| Tabletop exercise | Kiểm tra vai trò, quyết định và communication | Không thay đổi hệ thống |
| Component restore test | Khôi phục database/file từ backup | Tạo tài nguyên kiểm thử |
| DRS drill | Launch drill instances từ replication | Không làm gián đoạn source workload |
| Planned switchover | Chuyển primary/secondary trong điều kiện khỏe | Có thể gây gián đoạn ngắn |
| Full failover exercise | Chuyển toàn bộ traffic sang DR | Tác động lớn, cần change window |
| Failback exercise | Đồng bộ ngược và chuyển về primary | Tác động lớn, cần kiểm soát write |

Một bài diễn tập nên đo:

- Thời gian phát hiện và declare incident.
- Thời gian fencing primary.
- Replication lag và dữ liệu bị mất thực tế.
- Thời gian khởi chạy database và compute.
- Thời gian chuyển DNS/routing và client reconnect.
- Thời gian smoke test và business validation.
- Thời gian reverse replication và final sync khi failback.
- RTO/RPO thực tế so với mục tiêu.
- Số thao tác thủ công và lỗi trong runbook.

ARC Region switch có thể thực hiện plan evaluation và quota checks để phát hiện một số vấn đề cấu hình. Tuy nhiên, plan evaluation không thay thế recovery drill. Hãy thực thi plan trong môi trường kiểm thử và xác nhận ứng dụng thực sự hoạt động.

## 16. Giám sát, cảnh báo và lưu vết

Trong steady state, cần theo dõi replication và readiness liên tục. Trong incident, cần dashboard cho cả primary và DR.

Những metric hữu ích:

| Nhóm | Chỉ số |
|---|---|
| DRS | Replication lag, data backlog, source server state, staging area health |
| RDS | ReplicaLag, DB connections, failover events, engine health |
| Aurora Global Database | AuroraGlobalDBRPOLag hoặc metric lag phù hợp với engine version |
| S3 | Replication latency, OperationsPending, BytesPendingReplication, OperationsFailedReplication |
| EFS | Replication status, last sync time và throughput |
| Traffic | DNS health, routing control state, requests theo Region, connection errors |
| Application | Availability, latency, error rate, queue backlog, business transaction success |
| Capacity | EC2 capacity, Auto Scaling desired/in-service, database quota, IP/subnet capacity |

Lưu lại:

- Incident ID và người ra quyết định.
- Source/target Region, account và resource identifiers.
- Recovery point hoặc replication checkpoint được chọn.
- Replication lag tại thời điểm failover/failback.
- Thời gian từng bước và execution ID.
- Routing control state trước/sau chuyển traffic.
- Kết quả validation và reconciliation.
- Người phê duyệt, ngoại lệ và thời điểm mở lại write.

CloudTrail giúp kiểm tra ai đã thay đổi routing, database role, IAM policy, security group hoặc backup configuration. CloudWatch và EventBridge giúp phát hiện sự cố, gửi cảnh báo và kích hoạt workflow. Hãy giới hạn quyền đọc log và không ghi secret hoặc dữ liệu nhạy cảm vào ticket.

## 17. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| DR instance không launch | Launch settings sai, quota thiếu hoặc AMI/network không sẵn sàng | Kiểm tra DRS launch settings, instance type, subnet, security group và quota |
| Replication lag tăng | Network, staging storage hoặc source write rate thay đổi | Kiểm tra DRS replication dashboard, throughput và staging area |
| Database secondary thiếu transaction | Async replication chưa bắt kịp primary | Kiểm tra lag/checkpoint và xác định RPO thực tế |
| Aurora failover tạo lỗi write ở old Region | Old primary chưa được fence hoặc client còn kết nối | Kiểm tra RDS events, writer endpoint, DNS cache và ứng dụng |
| DNS đã đổi nhưng traffic vẫn vào primary | Client resolver cache, long-lived connection hoặc proxy cache | Kiểm tra access logs theo Region, TTL và connection pool |
| Ứng dụng ở DR không kết nối database | Secret, security group, endpoint hoặc CA certificate còn trỏ primary | Kiểm tra config/secret tại Region đích và network path |
| S3 object chưa có ở destination | Replication pending/failed hoặc object tạo trước rule | Kiểm tra replication status, Batch Replication, KMS và IAM |
| Failback không bắt đầu | Reverse replication chưa sẵn sàng hoặc source server không reachable | Kiểm tra DRS source/recovery instance state và failback prerequisites |
| Hai phía có dữ liệu khác nhau | Cả hai Region đã nhận ghi hoặc replay trùng | Dừng một writer, lưu snapshot/log và chạy reconciliation |
| Region DR không đủ capacity | Quota hoặc capacity không được chuẩn bị | Kiểm tra quota parity, instance availability và reserved capacity |
| Routing control update thất bại | ARC cluster endpoint không khả dụng hoặc safety rule chặn | Thử endpoint khác, kiểm tra control state và quy trình break-glass |
| Failback xong nhưng DR không còn được bảo vệ | Chưa thiết lập lại replication theo chiều mới | Xác nhận replication direction, source server protection và drill mới |

Khi có lỗi, giữ nguyên dữ liệu và log liên quan. Không khởi chạy đồng thời nhiều quy trình promote hoặc reverse replication nếu chưa biết thao tác nào đang có quyền ghi. Trước khi retry, xác định trạng thái thực tế của database, replication, routing và execution.

## 18. Ví dụ thực hành: failover và failback cho ứng dụng bán hàng

Một cửa hàng trực tuyến chạy ứng dụng trên EC2/ECS tại ap-southeast-1. Database sử dụng Aurora Global Database; file hóa đơn lưu trong S3; Secrets Manager giữ credential; Route 53 ARC routing controls điều khiển traffic. Region DR là ap-southeast-2.

Mục tiêu giả định:

- RPO database dưới 1 phút trong điều kiện replication bình thường.
- RTO ứng dụng dưới 30 phút.
- Chỉ một Region được phép ghi cho mỗi dữ liệu giao dịch.
- Sau khi primary phục hồi, phải reverse sync và kiểm thử trước khi failback.

### Trạng thái bình thường

- ap-southeast-1 là primary và nhận traffic.
- Aurora secondary tại ap-southeast-2 được đồng bộ bất đồng bộ.
- S3 CRR sao chép hóa đơn và file upload.
- Compute ở DR chạy warm standby với capacity thấp.
- Secrets, IAM roles, certificates, network và monitoring được triển khai ở cả hai Region.
- ARC routing control giữ traffic tại primary.

### Khi Region chính gặp sự cố

1. Incident commander xác nhận sự cố vượt khả năng phục hồi tại Region chính.
2. Nhóm database kiểm tra Aurora replication lag và chọn secondary phù hợp.
3. Thực hiện failover Aurora Global Database; ghi nhận RPO thực tế và RDS events.
4. Kiểm tra ứng dụng không còn ghi vào old primary; xác minh writer endpoint và client connections.
5. Scale up compute tại ap-southeast-2.
6. Xác nhận secret, S3 bucket, IAM và network tại DR.
7. Chạy smoke test: đăng nhập, tạo đơn thử, đọc tồn kho và ghi hóa đơn.
8. Bật routing control cho DR, tắt control primary theo safety rule và chuyển traffic.
9. Theo dõi error rate, database connections, order success và S3 replication.
10. Ghi nhận DR là nguồn dữ liệu authoritative.

### Khi Region chính đã phục hồi

1. Kiểm tra hạ tầng primary đã an toàn, vá lỗi và đủ capacity.
2. Xác định dữ liệu hiện tại ở DR là authoritative.
3. Thiết lập replication từ DR về primary theo cơ chế được hỗ trợ cho database và object storage.
4. Theo dõi lag và đối chiếu order, payment, inventory, invoice.
5. Lên maintenance window và đưa ứng dụng vào chế độ hạn chế ghi nếu cần final sync.
6. Hoàn tất final sync và fence writer tại DR.
7. Promote/activate database và storage tại primary.
8. Chạy smoke test và xác minh business invariants.
9. Chuyển traffic về primary bằng routing control.
10. Theo dõi traffic còn đến DR và lỗi ứng dụng.
11. Thiết lập lại replication từ primary về DR.
12. Chạy recovery drill sau failback để xác nhận DR đã được bảo vệ trở lại.

Không chuyển traffic về primary nếu chưa hoàn tất reverse replication, reconciliation và final sync. Nếu primary không đáp ứng health check sau khi chuyển, giữ DR làm authoritative và thực hiện rollback routing theo runbook.

## Kết luận

Failover chuyển workload và traffic sang môi trường có khả năng phục vụ; failback đưa hệ thống trở về môi trường chính sau khi đã đồng bộ các thay đổi phát sinh trong thời gian DR hoạt động. Replication, backup, data promotion và traffic routing là các bước khác nhau, cần được điều phối theo một quy trình có checkpoint.

Một thiết kế đáng tin cậy cần kiểm soát RPO/RTO, replication lag, consistency, quyền ghi và split-brain. AWS Elastic Disaster Recovery hỗ trợ khôi phục máy chủ và reverse replication; database, object và file services có cơ chế replication riêng; Route 53 ARC và Region switch hỗ trợ chuyển traffic và điều phối recovery. Sau mỗi lần failover, hãy kiểm tra dữ liệu, đồng bộ ngược, fencing, final sync và validation trước khi failback.

Hãy diễn tập cả hai chiều failover và failback. Chỉ khi đo được thời gian thực tế, xác nhận dữ liệu nhất quán và khôi phục lại replication bảo vệ DR thì quy trình mới sẵn sàng cho sự cố tiếp theo.

## Tài liệu tham khảo

- [Defining your disaster recovery strategy](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-database-disaster-recovery/defining.html)
- [Disaster recovery options in the cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html)
- [AWS Well-Architected REL13: recovery planning](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html)
- [What is AWS Elastic Disaster Recovery?](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html)
- [Recovery and failback with AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/failback.html)
- [Performing a failback with AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/failback-performing-main.html)
- [Failback with AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/guidance/latest/deploying-cross-region-disaster-recovery-with-aws-elastic-disaster-recovery/failback.html)
- [Routing control in Amazon Application Recovery Controller](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.html)
- [About routing control](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.about.html)
- [Creating safety rules for routing control](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.safety-rules.html)
- [Best practices for routing control](https://docs.aws.amazon.com/r53recovery/latest/dg/route53-arc-best-practices.regional.html)
- [Region switch in Amazon Application Recovery Controller](https://docs.aws.amazon.com/r53recovery/latest/dg/region-switch.html)
- [About Region switch plans](https://docs.aws.amazon.com/r53recovery/latest/dg/region-switch-plans.html)
- [Execute a Region switch plan](https://docs.aws.amazon.com/r53recovery/latest/dg/plan-execution-rs.html)
- [ARC readiness check availability change](https://docs.aws.amazon.com/r53recovery/latest/dg/arc-readiness-availability-change.html)
- [Using switchover or failover in Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-disaster-recovery.html)
- [Cross-Region resiliency for Aurora Global Database](https://docs.aws.amazon.com/us_en/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-secondary-availability.html)
- [AWS disaster recovery with RDS read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.XRgn.html)
- [DynamoDB global tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [How DynamoDB global tables work and consistency modes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html)
- [Amazon S3 replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [S3 Replication Time Control](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-time-control.html)
- [Amazon EFS replication](https://docs.aws.amazon.com/efs/latest/ug/replication.html)
- [AWS DataSync](https://docs.aws.amazon.com/datasync/latest/userguide/what-is-datasync.html)

