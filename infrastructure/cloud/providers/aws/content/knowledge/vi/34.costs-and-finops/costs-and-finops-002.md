# AWS Pricing Calculator và ước tính chi phí kiến trúc

AWS Pricing Calculator giúp ước tính chi phí của một workload trước khi triển khai hoặc khi thay đổi kiến trúc trên AWS. Công cụ nhận các giả định về dịch vụ, Region, cấu hình tài nguyên và mức sử dụng, sau đó tính chi phí dự kiến theo mô hình giá tương ứng. Kết quả hỗ trợ so sánh phương án, lập ngân sách, thảo luận với chủ sở hữu sản phẩm và đánh giá tác động tài chính của quyết định kỹ thuật.

Một kiến trúc chỉ có thể được ước tính tốt khi mô hình kỹ thuật và mô hình sử dụng được mô tả đủ rõ. Chọn đúng EC2 instance nhưng quên EBS, data transfer, NAT Gateway, load balancer, log ingestion hoặc backup sẽ làm tổng chi phí thiếu đáng kể. Tương tự, nhập số request trung bình nhưng bỏ qua peak, retry, cache miss hoặc traffic liên AZ có thể làm estimate thấp hơn thực tế.

Trong hệ sinh thái AWS, Pricing Calculator có thể giúp lập mô hình chi phí cho compute, storage, database, networking, integration, serverless, monitoring và các thành phần khác. Công cụ là bước lập kế hoạch; sau khi hệ thống chạy, cần so sánh estimate với chi phí thực tế qua AWS Billing, Cost Explorer, Cost and Usage Reports và quy trình FinOps.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt public AWS Pricing Calculator với trải nghiệm Pricing Calculator trong AWS Billing and Cost Management console.
- Thu thập yêu cầu kỹ thuật và chuyển chúng thành các đơn vị sử dụng có thể định giá.
- Tạo estimate theo service, Region, workload và nhóm kiến trúc.
- Ước tính các thành phần compute, storage, database, network, data transfer, integration, serverless và observability.
- So sánh On-Demand, Spot, Reserved Instances và Savings Plans khi mô hình sử dụng phù hợp.
- Xây dựng baseline, phương án tối ưu và kịch bản tăng trưởng; giải thích rõ assumptions và giới hạn.
- Xuất, lưu, chia sẻ estimate và đưa kết quả vào quy trình review kiến trúc/FinOps.
- Đối chiếu estimate với actual cost sau triển khai để hiệu chỉnh giả định.

## 2. AWS Pricing Calculator là gì?

AWS Pricing Calculator là công cụ lập ước tính dựa trên thông tin sử dụng mà người thiết kế cung cấp. Người học có thể truy cập public calculator tại https://calculator.aws/ mà không cần tạo AWS account. Công cụ cho phép thêm dịch vụ, chọn Region, cấu hình thông số workload, tổ chức theo group và xem tổng upfront, monthly, 12-month cost. Public calculator không phải hệ thống đo usage của account đang chạy.

AWS hiện cung cấp hai trải nghiệm cần phân biệt:

| Tiêu chí | Public AWS Pricing Calculator | In-console AWS Pricing Calculator |
|---|---|---|
| Nơi truy cập | Website calculator.aws | AWS Billing and Cost Management console |
| AWS account | Không bắt buộc | Bắt buộc |
| Mục đích | Ước tính workload mới hoặc kiến trúc dự kiến bằng các mức giá công khai | Mô hình hóa workload và tác động lên bill của account/Organization |
| Dữ liệu lịch sử | Người dùng tự nhập giả định | Có thể nhập usage lịch sử; cần Cost Explorer được bật cho việc import usage |
| Discounts/commitments | Public calculator tập trung vào public rates và các lựa chọn được hỗ trợ trong service configurator | Có thể dùng after-discount rates và mô hình hóa Savings Plans/Reserved Instances hiện có hoặc dự kiến theo quyền và rate preference |
| Kết quả | Estimate theo dịch vụ và nhóm; có thể export PDF/CSV và tạo public share link | Workload estimate hoặc bill estimate; quản lý trong account và hỗ trợ API/SDK theo tài liệu in-console |
| Người dùng | Người đang nghiên cứu, kiến trúc sư, nhóm dự án, người chưa có account | FinOps, billing owner, management account và member account được cấp quyền |

### 2.1 Public calculator

Public calculator phù hợp khi cần ước tính nhanh một workload mới, so sánh Region hoặc chuẩn bị phương án trước khi có account. Quy trình phổ biến gồm:

1. Tạo estimate.
2. Thêm service vào estimate.
3. Chọn Region và nhập cấu hình/usage.
4. Lưu service vào estimate.
5. Tổ chức dịch vụ theo group.
6. Xem tổng upfront, monthly và 12-month cost.
7. Export CSV/PDF hoặc tạo share link.

Public calculator không yêu cầu đăng nhập. Estimate share link được lưu trên máy chủ công khai của AWS; người nhận có link có thể truy cập estimate. Không đưa bí mật, thông tin định danh nội bộ nhạy cảm hoặc chi tiết kiến trúc bị hạn chế chia sẻ vào tên/description của estimate.

Theo hướng dẫn public calculator, hiện không có API cho public website. Nếu cần tích hợp estimate vào quy trình tự động, hãy kiểm tra API của in-console Pricing Calculator và các API dữ liệu giá phù hợp; không tự giả định public calculator có endpoint không được tài liệu công bố.

### 2.2 In-console calculator

In-console Pricing Calculator có hai loại estimate:

- **Workload estimate:** ước tính chi phí cho workload, ứng dụng, tài nguyên hoặc thay đổi kiến trúc cụ thể. Có thể dùng public rates hoặc các effective rates được management account cho phép, bao gồm mức sau discount và sau discount cộng commitment.
- **Bill estimate:** ước tính tác động của usage/commitment được mô hình hóa lên toàn bộ consolidated bill của Organization. Bill estimate tự đưa usage của kỳ billing gần nhất và các commitment hiện có như Savings Plans/Reserved Instances vào mô hình; loại estimate này dành cho management account hoặc standalone account.

Workload estimate hữu ích khi trả lời “nếu triển khai kiến trúc A thì workload này tốn bao nhiêu?”. Bill estimate hữu ích khi trả lời “nếu thay đổi usage hoặc commitment thì tổng bill của Organization sẽ thay đổi thế nào?”. Hai câu hỏi có phạm vi khác nhau; đừng dùng workload estimate để thay thế phân tích consolidated bill nếu commitment chưa được tính đến.

In-console calculator có thể sử dụng dữ liệu lịch sử và discount theo quyền. Management account cấu hình rate preference cho member accounts; nếu chưa cấp quyền dùng after-discount rates, member estimate có thể dùng public rates. Việc nhập usage lịch sử yêu cầu Cost Explorer được bật theo hướng dẫn của AWS.

Workload estimates được cung cấp miễn phí. Với bill estimates, mỗi account có năm estimate miễn phí mỗi tháng; từ estimate thứ sáu trong cùng tháng dương lịch, mỗi estimate có giá 2 USD theo tài liệu AWS hiện hành. Nếu estimate thất bại, estimate đó không bị tính vào số lượng miễn phí và không bị tính phí. Hãy kiểm tra trang pricing hiện hành trước khi lập ngân sách cho hoạt động phân tích lặp lại.

## 3. Estimate là mô hình có giả định, không phải báo giá

Pricing Calculator đưa ra con số gần đúng theo thông số đã nhập. Kết quả không phải báo giá ràng buộc, không bảo đảm hóa đơn thực tế và không thay thế hợp đồng, báo giá từ AWS hoặc đối tác. Chi phí thực tế phụ thuộc usage thực, Region, thời điểm sử dụng, thay đổi giá, tier, discount, commitment, dịch vụ phát sinh và cách workload vận hành.

Chất lượng estimate bị giới hạn bởi chất lượng đầu vào. Nếu người thiết kế nhập một EC2 instance chạy 730 giờ mỗi tháng nhưng production thực tế chạy nhiều instance hơn, bật thêm môi trường staging hoặc tăng autoscaling, hóa đơn sẽ khác. Nếu kiến trúc có data transfer, NAT Gateway, snapshots, logs, support hoặc Marketplace license mà estimate bỏ qua, tổng chi phí cũng thiếu.

Hãy ghi rõ ba loại dữ liệu trong mỗi estimate:

| Loại dữ liệu | Ví dụ | Cách quản lý |
|---|---|---|
| Đã biết | Số node hiện tại, kích thước DB, Region đã được chọn | Dẫn nguồn inventory, tài liệu thiết kế hoặc dữ liệu đo |
| Giả định | 2.000.000 request/ngày, 30% cache hit, 500 GB egress/tháng | Ghi người xác nhận, ngày và lý do |
| Chưa biết | Tăng trưởng sau launch, tỷ lệ retry, lượng log khi peak | Dựng kịch bản thấp/cơ sở/cao và xác định cách đo sau triển khai |

Một estimate hữu ích có thể giải thích tại sao chi phí xuất hiện, điều gì làm nó tăng và giả định nào cần kiểm chứng. Chỉ trình bày một con số tổng mà không có cấu trúc và assumptions sẽ khó dùng để ra quyết định.

## 4. Chuẩn bị dữ liệu trước khi mở Calculator

Trước khi thêm service, hãy mô tả workload bằng các câu hỏi kỹ thuật. Đừng bắt đầu từ danh sách dịch vụ rồi nhập số mặc định của công cụ.

### 4.1 Phạm vi kiến trúc

- Workload phục vụ sản phẩm nào, môi trường nào và cost center nào?
- Triển khai ở một Region hay nhiều Region?
- Có cần Multi-AZ, read replica, standby, disaster recovery hoặc active-active không?
- Thành phần nào chạy liên tục, thành phần nào chỉ chạy theo lịch hoặc khi có request?
- Có môi trường development, test, staging, production và sandbox nào phải tính?
- Dữ liệu đi qua các dịch vụ nào, có traffic liên AZ, liên Region hoặc ra Internet không?
- Có dịch vụ bên thứ ba, AWS Marketplace, license hệ điều hành/database hoặc support plan không?

### 4.2 Mức sử dụng

Thu thập cả trung bình và peak:

- Số instance/container/task/pod và số giờ chạy.
- vCPU, RAM, kiến trúc CPU, OS, tenancy, license.
- Request/second, request/day, thời lượng xử lý, concurrency, retry và cache hit ratio.
- Dung lượng lưu trữ trung bình, dung lượng tăng mới mỗi tháng, IOPS, throughput và số request.
- Dữ liệu vào/ra Internet, giữa Availability Zone, giữa Region và giữa dịch vụ.
- Dung lượng log/metric/trace, thời gian giữ, truy vấn và export.
- Backup, snapshot, replication, data retrieval và restore frequency.
- Số người dùng, số API call, message, event và batch job.

### 4.3 Đơn vị đo phải thống nhất

| Nhóm | Đơn vị thường dùng | Ví dụ |
|---|---|---|
| Compute | instance-hour, vCPU-hour, GB-hour, task-hour | 2 instance chạy 730 giờ/tháng |
| Request | request, invocation, message, API call | 30 triệu invocation/tháng |
| Storage | GB-month hoặc TB-month | Dung lượng trung bình 2 TB/tháng |
| I/O | IOPS, I/O request, throughput | 5.000 IOPS và 100 MB/s |
| Data transfer | GB/TB theo chiều và điểm đến | 800 GB Internet egress/tháng |
| Logging | GB ingest, GB scanned, metric-month | 40 GB log ingest/tháng |
| Database | instance-hour, ACU-hour, vCPU/RAM-hour, storage, I/O | DB Multi-AZ chạy liên tục |
| Backup | GB-month, snapshot storage, copy, restore | 2 TB recovery points retained |

Không trộn GB với GiB, MB/s với Mbps hoặc request/ngày với request/tháng mà không quy đổi. Nếu nguồn đo dùng byte và calculator dùng GB, hãy ghi rõ cách quy đổi. Sai đơn vị có thể tạo chênh lệch lớn dù công thức đúng.

### 4.4 Xác định thời gian sử dụng

Một dịch vụ có thể chạy 24/7, chỉ chạy giờ hành chính, hoặc tăng tải theo sự kiện. Public calculator thường dùng giả định 730 giờ cho một tháng khi tính chi phí tháng. Nếu workload chạy 8 giờ/ngày, 22 ngày/tháng, số giờ dự kiến là 176 giờ, nhưng cần tính thêm thời gian ngoài giờ cho deployment, retry, maintenance và môi trường không tắt.

Với autoscaling, hãy tính tổng giờ của từng nhóm capacity thay vì chỉ lấy số instance tối đa nhân 730. Ví dụ: 2 instance baseline chạy cả tháng và 2 instance bổ sung chạy 4 giờ/ngày trong 30 ngày tạo ra 1.700 instance-hours trong tháng giả định:

    Baseline = 2 × 730 = 1.460 instance-hours
    Burst    = 2 × 4 × 30 = 240 instance-hours
    Total    = 1.460 + 240 = 1.700 instance-hours

Nếu instance burst dùng loại khác hoặc Spot, tách riêng usage để định giá đúng.

## 5. Quy trình tạo estimate bằng Public Calculator

### Bước 1: Xác định cách tổ chức estimate

Trước khi mở công cụ, chọn cách nhóm phù hợp:

- Theo product/workload: website, order service, data platform, mobile backend.
- Theo kiến trúc: edge, application, database, analytics, observability.
- Theo môi trường: production, staging, development.
- Theo cost center/team/client.
- Theo Region: primary, disaster recovery hoặc Region cần so sánh.

AWS khuyến nghị xác định cách chia estimate trước để sử dụng Group có ý nghĩa. Một estimate có thể chứa nhiều service và group; tổng của các group giúp nhìn toàn cảnh workload.

### Bước 2: Tạo estimate và thêm service

Mở https://calculator.aws/ và chọn Create estimate. Tại trang Add service, tìm dịch vụ theo tên hoặc lọc theo location/service category. Chọn Configure để mở trang cấu hình. Mỗi service có bộ input riêng; không phải mọi service đều có cùng mô hình đơn vị.

### Bước 3: Chọn location và Region

Chọn Region nơi tài nguyên dự kiến chạy, không chọn Region theo thói quen hoặc chỉ vì giá thấp. Giá, khả năng cung cấp instance, tính năng, quota, data residency, độ trễ, khả năng DR và kết nối với hệ thống hiện tại có thể khác nhau giữa Region.

Nếu kiến trúc có nhiều Region, tạo group hoặc service estimate riêng cho từng Region. Kiểm tra cả chi phí copy dữ liệu, inter-Region transfer, replication, backup và traffic chuyển vùng. Không cộng giá một Region cho tất cả dịch vụ khi một số thành phần được đặt ở Region khác.

### Bước 4: Nhập thông số service

Với mỗi service:

1. Đặt description có ý nghĩa, ví dụ “API production – application tier”.
2. Chọn Region/location type.
3. Chọn cấu hình tài nguyên sát với yêu cầu kỹ thuật.
4. Nhập số lượng và thời gian sử dụng.
5. Nhập storage, request, I/O, throughput hoặc data transfer liên quan.
6. Chọn pricing model nếu configurator hỗ trợ và phù hợp với workload.
7. Kiểm tra các add-on, monitoring, backup, data transfer và license.
8. Dùng Show calculation/chi tiết tính toán để xem cách hình thành chi phí.
9. Lưu và thêm service vào estimate.

Không giữ nguyên giá trị mặc định chỉ vì công cụ đã điền sẵn. Một số màn hình mặc định một instance hoặc dung lượng khởi đầu nhỏ để minh họa; hãy thay bằng usage đã thu thập.

### Bước 5: Thêm các dịch vụ phụ thuộc

Sau khi thêm compute hoặc database, kiểm tra các thành phần phụ trợ:

- EBS hoặc block storage cho EC2.
- Load balancer, NAT Gateway, public IPv4, data transfer và Route 53.
- Snapshot, backup, replication và storage retrieval.
- CloudWatch logs, metrics, alarms, dashboards và tracing.
- KMS requests, Secrets Manager secrets/API calls và certificate.
- SQS, SNS, EventBridge, API Gateway, Step Functions hoặc data transfer giữa dịch vụ.
- AWS Support, Marketplace software, license và chi phí dịch vụ ngoài AWS nếu phạm vi TCO yêu cầu.

Calculator chỉ tính những gì đã được thêm hoặc được configurator bao gồm. Hãy rà soát kiến trúc từ đầu đến cuối để không bỏ sót dependency.

### Bước 6: Tổ chức group và xem tổng

Tạo group cho từng layer, workload, Region hoặc cost center. Di chuyển service vào đúng group để review theo trách nhiệm. Trang My estimate hiển thị tổng upfront, monthly và 12-month cost cùng chi tiết service/group. Hãy xem cả phần chi tiết, không chỉ số tổng.

### Bước 7: Lưu và export

Tạo share link nếu cần cộng tác qua public calculator; ghi lại link cùng mô tả, ngày lập, phiên bản giả định và người chịu trách nhiệm. Export CSV để phân tích dữ liệu hoặc PDF để review với stakeholder. PDF public calculator có share link của estimate.

Nếu thay đổi estimate, hãy tạo link mới sau khi lưu. Public calculator không tự ghi đè link cũ; các link public được tạo từ 31-05-2023 có hiệu lực một năm theo tài liệu hiện hành. Với estimate nhạy cảm hoặc cần quản trị theo IAM, cân nhắc in-console calculator.

## 6. Các nhóm thông số cần nhập theo dịch vụ

### 6.1 Compute: EC2, ECS, EKS và Lambda

| Thành phần | Đầu vào chính | Chi phí dễ bị bỏ sót |
|---|---|---|
| EC2 | Region, instance type, OS, tenancy, số instance, workload pattern, giờ chạy, pricing model | EBS, snapshots, data transfer, detailed monitoring, Elastic IP/public IPv4, license, load balancer |
| ECS on EC2 | EC2 capacity, số node, CPU/RAM utilization, scaling | EC2 idle capacity, EBS, networking, load balancer, logs |
| ECS/Fargate | vCPU, memory, ephemeral storage, task count, duration, platform | NAT/data transfer, load balancer, logs, image pulls, idle service minimum |
| EKS | Cluster/control-plane fee, node group hoặc Fargate profile, pod capacity | EC2/EBS, load balancer, NAT, inter-AZ, observability, add-ons |
| Lambda | Invocations, memory, duration, architecture, provisioned concurrency, ephemeral storage | API Gateway, EventBridge/SQS, retries, logs, data transfer, provisioned concurrency |

Với EC2, chọn OS chính xác vì Windows, Linux và một số license có cách tính khác nhau. Kiểm tra tenancy Shared/Dedicated/Host, instance family, kích thước, số instance và pattern sử dụng. Calculator có thể mô hình workload constant, daily spike, weekly spike hoặc monthly spike trong configurator EC2. Workload pattern giúp ước lượng phần usage On-Demand và phần reservation phù hợp hơn.

Với burstable instance, kiểm tra Unlimited mode và CPU credit surplus nếu tải trung bình có thể vượt baseline. Không chọn instance chỉ dựa vào vCPU/RAM; network performance, EBS bandwidth, CPU architecture, memory pressure và licensing cũng ảnh hưởng đến lựa chọn.

Với container, đừng coi số pod là đơn vị bill trực tiếp trong mọi trường hợp. ECS on EC2 trả chi phí capacity EC2 và storage/network; Fargate tính theo vCPU/memory/time theo cấu hình; EKS có phí cluster/control plane và chi phí node hoặc Fargate. Phải tính capacity dự phòng để đáp ứng autoscaling và rolling deployment.

Với Lambda, request count chưa đủ. Cần duration, memory, architecture, provisioned concurrency, ephemeral storage và tỷ lệ retry. Một hàm chạy ít nhưng duration dài hoặc provisioned concurrency lớn có thể có chi phí đáng kể. Đừng quên log ingestion và dịch vụ kích hoạt.

### 6.2 Storage: EBS, S3, EFS và FSx

| Dịch vụ | Đầu vào | Cần kiểm tra |
|---|---|---|
| EBS | Volume type, GB-month, IOPS, throughput, số volume | gp3/io2/gp2 khác nhau; provisioned IOPS/throughput; snapshots |
| S3 | Dung lượng trung bình theo storage class, PUT/GET/LIST, retrieval, lifecycle, replication | Versioning, object count, minimum storage duration, retrieval fee, request fee, data transfer |
| EFS | Storage class, average storage, throughput mode, provisioned throughput, requests | Regional/One Zone, lifecycle, IA/archive access, backup |
| FSx | File system type, capacity, throughput, deployment type, backup | Multi-AZ, SSD/HDD, throughput capacity, backup storage, data transfer |

Không dùng tổng dung lượng cuối tháng thay cho dung lượng trung bình nếu storage tăng đều. Nếu 1 TB dữ liệu tăng từ 0 lên 1 TB trong 30 ngày, dung lượng trung bình gần 0,5 TB-month trong mô hình tuyến tính, nhưng thực tế còn phụ thuộc thời điểm ingest và retention.

Với S3, cần tách Standard, Intelligent-Tiering, Standard-IA, One Zone-IA, Glacier Instant/Flexible/Deep Archive theo pattern truy cập. Ước lượng số object, request class, retrieval, transition, minimum storage duration, restore và replication. Storage rẻ hơn có thể tạo phí retrieval hoặc thời gian chờ lớn hơn.

Với EBS, tính dung lượng và IOPS/throughput đã provision. Snapshot thường incremental nhưng chi phí phụ thuộc lượng block thay đổi và thời gian lưu. Nếu snapshot được copy sang Region khác, cần thêm chi phí copy/storage ở Region đích và data transfer theo quy tắc dịch vụ.

### 6.3 Database: RDS, Aurora, DynamoDB và ElastiCache

| Dịch vụ | Đầu vào | Các khoản cần mô hình hóa |
|---|---|---|
| RDS | Engine, instance class, số instance, Multi-AZ, storage, IOPS, backup, data transfer | Primary/standby/read replica, storage, I/O, backup vượt free allocation, license engine |
| Aurora | Engine, provisioned hoặc Serverless v2, instance/ACU, storage, I/O, backup | Reader, Multi-AZ storage, I/O request, backup, data transfer |
| DynamoDB | Read/write request units, on-demand/provisioned, table/index storage, backup, streams, global tables | GSI/LSI, transactional requests, PITR, export/import, replication |
| ElastiCache | Engine, node type, node count, replicas, shard count, data tiering | Multi-AZ/replica, backup, snapshots, data transfer |

Với RDS Multi-AZ, hãy chọn cấu hình Multi-AZ trong calculator nếu configurator cung cấp. Đừng vừa chọn Multi-AZ vừa cộng thêm một standby riêng lần nữa nếu giá đã bao gồm standby. Read replica là thành phần bổ sung có mục đích khác; tính riêng theo cấu hình thực tế.

Aurora provisioned và Aurora Serverless v2 có đơn vị capacity khác nhau. Với Serverless v2, cần ước lượng mức ACU trung bình, min/max ACU, thời gian hoạt động và pattern scale. Với DynamoDB, phân biệt on-demand với provisioned capacity, table/index, read/write, transactional, backup/PITR, streams và global table replication.

### 6.4 Networking và content delivery

| Thành phần | Đơn vị/đầu vào | Lưu ý |
|---|---|---|
| Application/Network Load Balancer | Load balancer-hour, LCU/NLCU-hour | LCU dựa trên các chiều sử dụng; lấy chiều lớn nhất theo quy tắc dịch vụ |
| NAT Gateway | Gateway-hour, GB processed | Tính số AZ có NAT và lưu lượng qua từng gateway |
| Data transfer | GB theo source/destination/Region/AZ | Tách Internet egress, inter-AZ, inter-Region, cross-account và service-specific transfer |
| CloudFront | Data transfer out theo edge region, request, invalidation và tính năng | Cache hit ratio làm thay đổi origin traffic; giá khác theo location |
| Route 53 | Hosted zone, query, health check, resolver endpoint/query | Tính cả private hosted zone và health checks nếu dùng |
| Public IPv4 | Address-hour hoặc loại sử dụng tương ứng | Kiểm tra loại địa chỉ và thời gian gắn với resource |
| VPC endpoints | Endpoint-hour, data processing | Interface endpoint và Gateway endpoint có mô hình phí khác nhau |

Networking là nhóm thường bị thiếu trong estimate. Một workload có thể có EC2 giá hợp lý nhưng chi phí NAT, inter-AZ transfer, load balancer và Internet egress cao. Hãy vẽ data flow và tính lượng byte qua từng ranh giới mạng.

### 6.5 Integration, serverless và application services

- API Gateway: số request, loại API, cache, data transfer, private integration.
- SQS: số request, batch size, payload, long polling, FIFO và dead-letter queue.
- SNS: publish/delivery, protocol và số endpoint.
- EventBridge: event ingestion, archive/replay, cross-account/Region event bus.
- Step Functions: số state transition, Standard/Express workflow, retry và execution duration.
- Kinesis: shard-hours hoặc throughput/on-demand data, retention và enhanced fan-out.
- AppSync: request, connection, data transfer và resolver usage.
- Secrets Manager: số secret, API call, rotation Lambda và cross-Region replication.

Một request của người dùng có thể kích hoạt nhiều dịch vụ. Ví dụ API Gateway nhận một request, Lambda chạy hai lần do retry, ghi một message vào SQS, phát event, đọc secret và ghi log. Estimate chỉ tính request API mà bỏ các lần invoke và downstream request sẽ đánh giá thiếu.

### 6.6 Observability và security

Chi phí vận hành và bảo mật cũng là một phần của kiến trúc:

- CloudWatch Logs: GB ingest, storage/retention, Logs Insights scan, subscription/filter và export.
- CloudWatch Metrics: custom metric, dimension/cardinality, high-resolution metric, alarms và dashboard.
- X-Ray/Application Signals: trace ingestion, sampling, retention và service map.
- KMS: API requests, key type, rotation và multi-Region key nếu có.
- AWS Config: configuration item recording, rule evaluation và conformance pack.
- CloudTrail: management/data events, Lake ingestion/retention và S3 storage.
- GuardDuty/Security Hub/Inspector: resource coverage, finding volume, scan hoặc ingestion model theo pricing page.
- AWS Backup: protected storage, warm/cold tier, copy và restore.

Telemetry càng chi tiết càng hữu ích cho vận hành nhưng cũng có chi phí. Ước lượng log volume từ số request × log bytes/request; ước lượng trace sau sampling; kiểm soát metric cardinality và retention. Đừng dùng một số GB log tùy ý nếu chưa có mẫu log hoặc benchmark.

## 7. Các mô hình giá cần hiểu trước khi so sánh

### 7.1 On-Demand

On-Demand phù hợp khi usage chưa ổn định, workload mới hoặc cần khả năng thay đổi capacity. Chi phí thường phụ thuộc đơn vị sử dụng như instance-hour, GB-month, request hoặc I/O. Mức giá thay đổi theo Region, service, OS, instance type và thời gian.

Ưu điểm là không cần cam kết dài hạn; nhược điểm là đơn giá có thể cao hơn khi usage ổn định lâu dài. Hãy dùng On-Demand làm baseline trước khi mô hình discount/commitment.

### 7.2 Savings Plans

Savings Plans là cam kết chi tiêu theo USD/giờ trong thời hạn thường là một hoặc ba năm, đổi lấy mức giá ưu đãi cho usage đủ điều kiện. Hai nhóm chính:

- Compute Savings Plans có phạm vi linh hoạt hơn giữa EC2, Fargate và Lambda theo điều kiện chương trình.
- EC2 Instance Savings Plans gắn với family/Region cụ thể và thường có mức tiết kiệm cao hơn khi workload ổn định trong phạm vi đó.

Commitment được tính theo mức chi tiêu mỗi giờ, không phải số instance được giữ chỗ. Usage đủ điều kiện được áp dụng mức ưu đãi; phần usage vượt commitment hoặc không đủ điều kiện tiếp tục theo mức giá tương ứng. Commitment không được sử dụng hết vẫn tạo chi phí cam kết.

### 7.3 Reserved Instances

Reserved Instances (RI) là mô hình định giá cho các dịch vụ/loại tài nguyên được hỗ trợ. Với EC2, RI cung cấp discount cho usage phù hợp với thuộc tính reservation; Standard RI có mức discount cao hơn nhưng ít linh hoạt hơn Convertible RI. RI không đồng nghĩa với việc tự động đặt trước capacity trừ khi chọn tùy chọn capacity reservation phù hợp. RDS và một số dịch vụ khác có reservation model riêng.

Thời hạn phổ biến là một hoặc ba năm. Payment option gồm No Upfront, Partial Upfront và All Upfront. All Upfront có thể cho tổng chi phí thấp hơn nhưng cần tiền trả trước; No Upfront giảm khoản trả ban đầu nhưng vẫn là cam kết theo kỳ hạn.

### 7.4 Spot

Spot sử dụng capacity EC2 dư thừa với mức giá chiết khấu và có thể bị AWS thu hồi khi cần capacity. Spot phù hợp với workload chịu được interruption như batch, stateless worker, CI job hoặc xử lý phân tán có checkpoint. Không nên dùng Spot làm capacity duy nhất cho thành phần không thể gián đoạn.

Public EC2 configurator có thể hiển thị mức discount Spot lịch sử và cho nhập giả định discount để tạo estimate. Giá Spot thực tế thay đổi theo pool, Region và thời gian; con số lịch sử không bảo đảm mức tiết kiệm tương lai. Với workload cần mô hình Spot chính xác hơn, lập kịch bản riêng và xác minh theo pricing/Spot data.

### 7.5 Dedicated tenancy, Host và license

Dedicated Instances, Dedicated Hosts hoặc license model có thể thay đổi chi phí đáng kể. Nếu yêu cầu license Windows Server, SQL Server, Oracle hoặc BYOL, phải xác định license được tính trong hourly price, theo core/socket, theo host hay theo thỏa thuận riêng. AWS Pricing Calculator không tự bao gồm mọi phí license bên thứ ba hoặc Marketplace.

### 7.6 Chọn mô hình theo mức ổn định

| Đặc điểm workload | Điểm bắt đầu phù hợp | Cần kiểm tra |
|---|---|---|
| Chưa biết traffic, mới launch | On-Demand | Thu thập actual usage sau khi chạy |
| Baseline chạy liên tục, peak thay đổi | Commitment cho baseline + On-Demand cho burst | Mức commitment có thể sử dụng ổn định |
| Batch chịu interruption | Spot kết hợp capacity dự phòng | Checkpoint, retry, thời gian hoàn tất |
| EC2 family/Region ổn định | So sánh EC2 Instance Savings Plan và RI | Linh hoạt family, Region, OS và term |
| Nhiều compute service thay đổi | Compute Savings Plan | Phạm vi service đủ điều kiện và utilization |
| RDS workload ổn định | RDS Reserved DB Instances nếu phù hợp | Engine, Region, class, Multi-AZ và term |

Đừng mua commitment chỉ vì estimate hiển thị mức tiết kiệm cao. Trước hết cần biết baseline usage, thời gian cam kết, kế hoạch migration, mức tăng trưởng và khả năng tận dụng commitment nếu workload thay đổi.

## 8. Phân tích chi phí mạng và data transfer

Chi phí data transfer thường phụ thuộc hướng truyền, Region, Availability Zone, loại dịch vụ và điểm kết nối. Cần tách ít nhất các luồng:

1. Internet ingress: dữ liệu từ người dùng vào AWS.
2. Internet egress: dữ liệu từ AWS ra người dùng.
3. Inter-AZ: dữ liệu giữa Availability Zones trong cùng Region.
4. Inter-Region: dữ liệu giữa Region.
5. Cross-account: dữ liệu/backup chia sẻ giữa account, tùy service pricing.
6. Service-to-service: dữ liệu giữa EC2, S3, CloudFront, NAT, VPC endpoint và dịch vụ khác.

Không áp dụng một mức giá data transfer chung cho mọi luồng. Một số dịch vụ có allowance hoặc quy tắc riêng; một số đường đi qua cùng Region có thể có phí theo service hoặc theo AZ. Luôn tra trang pricing của nguồn và đích.

### 8.1 NAT Gateway

NAT Gateway có thể tạo chi phí theo số gateway-hour và lượng GB được xử lý. Trong kiến trúc Multi-AZ, nếu mỗi AZ có NAT Gateway riêng để tránh phụ thuộc chéo AZ, hãy tính số gateway thực tế và phân bổ lượng traffic qua từng gateway. Nếu chỉ tính một NAT trong khi triển khai ba AZ, estimate sẽ thiếu cả giờ gateway và có thể thiếu data processing/inter-AZ transfer.

Một số traffic đến dịch vụ AWS có thể tránh NAT bằng Gateway endpoint hoặc Interface endpoint. Tuy nhiên, Interface endpoint có phí endpoint-hour và data processing; Gateway endpoint cho S3/DynamoDB có mô hình giá khác. Hãy so sánh theo traffic và yêu cầu bảo mật, không mặc định endpoint luôn rẻ hơn NAT.

### 8.2 Load balancer

Application Load Balancer và Network Load Balancer có phí theo giờ và đơn vị xử lý (LCU/NLCU) theo các chiều được dịch vụ định nghĩa. Hãy ước lượng new connections, active connections, processed bytes và rule evaluations theo loại load balancer. Dùng chiều có mức sử dụng lớn nhất theo cách tính của dịch vụ, tránh cộng tất cả chiều như các khoản độc lập nếu calculator đã tự chọn mức lớn nhất.

### 8.3 CloudFront và cache

CloudFront có thể giảm origin requests và cải thiện trải nghiệm người dùng, nhưng chi phí phụ thuộc edge location, data transfer, request, invalidation và tính năng bật thêm. Cache hit ratio cao có thể giảm traffic về origin và giảm tải backend; cache miss, dynamic content, invalidation hoặc TTL quá ngắn có thể làm chi phí origin tăng.

Khi so sánh có/không CloudFront, tính đồng thời chi phí CloudFront và phần EC2/ALB/S3/Data Transfer được giảm. Không chỉ so sánh giá CDN với giá egress origin.

### 8.4 Inter-AZ và topology

Ứng dụng phân tán trên nhiều AZ có thể phát sinh data transfer khi node ở AZ A gọi database hoặc service ở AZ B. Tăng số replica hoặc chia shard có thể cải thiện HA và throughput nhưng tăng inter-AZ traffic. Hãy vẽ luồng thực tế và ước lượng GB/tháng thay vì chỉ ghi “Multi-AZ”.

## 9. Công thức ước tính và kiểm tra đơn vị

Một số mô hình tính đơn giản giúp kiểm tra kết quả Calculator:

    Monthly compute ≈ số đơn vị × giờ sử dụng × giá mỗi đơn vị-giờ
    Monthly storage ≈ dung lượng trung bình (GB-month) × giá mỗi GB-month
    Request cost ≈ số request / đơn vị tính giá × giá mỗi đơn vị
    Data transfer cost ≈ GB tính phí theo từng tuyến × giá tuyến tương ứng
    Monthly total ≈ compute + storage + I/O + network + request + operations + support + license

Đây là mô hình kiểm tra, không phải công thức thay thế pricing page. Một số dịch vụ dùng tier, minimum charge, per-second billing, capacity, throughput, peak metric hoặc combination nhiều chiều. Dùng trang Show calculation để kiểm tra calculator đang tính theo đơn vị nào.

### 9.1 Quy đổi giờ

    1 instance chạy liên tục theo giả định calculator = 730 instance-hours/tháng
    4 instance chạy 12 giờ/ngày trong 30 ngày = 4 × 12 × 30 = 1.440 instance-hours
    2 instance baseline + 2 instance chạy thêm 4 giờ/ngày:
      2 × 730 + 2 × 4 × 30 = 1.700 instance-hours

Đừng dùng 730 giờ như số giờ thực tế của mọi tháng. Đây là giả định chuẩn của calculator để so sánh. Nếu hệ thống chạy theo tháng lịch, thời gian bắt đầu giữa tháng hoặc per-second billing, actual charge có thể khác.

### 9.2 Dung lượng trung bình

Nếu dữ liệu tăng tuyến tính từ 100 GB lên 400 GB trong 30 ngày, dung lượng trung bình gần:

    Average storage = (100 + 400) / 2 = 250 GB

Nếu dữ liệu được nạp toàn bộ ngay ngày đầu, dung lượng trung bình gần 400 GB. Nếu dữ liệu cũ bị xóa theo lifecycle, hãy mô hình hóa dung lượng retained thay vì chỉ lấy tổng ingest.

### 9.3 Request và duration

Với Lambda, cần tính request count và compute duration theo cấu hình memory. Ví dụ 10 triệu invocation, duration trung bình 200 ms:

    Total execution time = 10.000.000 × 0,2 giây
                         = 2.000.000 giây

Đây là thời gian thực thi cộng dồn để kiểm tra quy mô; chi phí cụ thể còn phụ thuộc memory, architecture, ephemeral storage, provisioned concurrency, free tier và Region.

### 9.4 Data transfer

Giả sử 1.000.000 request/ngày, mỗi response trung bình 80 KB và 30 ngày:

    Monthly response bytes = 1.000.000 × 80 KB × 30
                           = 2.400.000.000 KB

Đây là dữ liệu response trước khi tính compression, cache, protocol overhead, retry và quy đổi đơn vị. Nếu CloudFront cache 70% response, lượng dữ liệu origin trả về có thể thấp hơn đáng kể; nhưng CloudFront vẫn phục vụ dữ liệu cho người dùng và có chi phí riêng.

### 9.5 Tránh double-count

Các lỗi cộng trùng thường gặp:

- Chọn RDS Multi-AZ trong calculator rồi cộng thêm một DB standby thủ công dù configurator đã tính.
- Chọn EC2 configurator có EBS mặc định rồi cộng cùng volume thêm một lần.
- Nhập data transfer vào EC2 và lại thêm toàn bộ cùng một traffic trong mục network chung.
- Cộng toàn bộ request ở tầng API và cộng lại request nội bộ nếu calculator đã tính trong service usage.
- Dùng giá đã discount rồi trừ discount thêm lần nữa.
- Cộng snapshot/backup hai lần khi estimate đã bao gồm backup storage.

Mỗi dòng chi phí cần một đơn vị đo, một nguồn dữ liệu và một owner. Đánh dấu các khoản đã được service configurator bao gồm và các khoản phải thêm thủ công.

## 10. Ví dụ: ước tính kiến trúc web bán hàng

Giả sử nhóm dự án thiết kế ứng dụng bán hàng cho khách hàng tại Việt Nam. Đây là ví dụ về cách lập giả định; không đưa giá USD cố định vì đơn giá, Region và service availability có thể thay đổi.

### 10.1 Kiến trúc giả định

    Người dùng
       |
    Route 53 / CloudFront
       |
    Application Load Balancer
       |
    EC2 Auto Scaling (2 AZ)
       |                 \
    RDS Multi-AZ       S3 hóa đơn
       |
    ElastiCache

    Lambda + SQS xử lý tác vụ nền
    NAT / VPC endpoints cho outbound traffic
    CloudWatch cho logs, metrics và alarms
    AWS Backup cho snapshot và bản sao DR

### 10.2 Bảng usage đầu vào

| Thành phần | Giả định cơ sở | Đơn vị estimate |
|---|---|---|
| EC2 application | 2 instance baseline 730 giờ; thêm 2 instance 4 giờ/ngày trong 30 ngày | 1.700 instance-hours |
| EBS | 2 volume gp3, mỗi volume 100 GB | 200 GB-month |
| ALB | 1 ALB chạy liên tục, traffic trung bình và peak đã đo | 730 ALB-hours + LCU-hours |
| RDS | 1 database Multi-AZ, class đã benchmark, storage 500 GB | DB-hours + 500 GB-month + I/O |
| ElastiCache | 2 node cache chạy liên tục | 1.460 node-hours |
| S3 | Dung lượng trung bình 500 GB; 5 triệu GET và 200.000 PUT/tháng | GB-month + request |
| CloudFront | 1 TB data served/tháng, cache hit 70% | GB transfer theo edge + requests |
| NAT Gateway | 2 AZ, mỗi AZ một NAT, tổng 300 GB processed | 1.460 gateway-hours + 300 GB |
| Lambda | 10 triệu invocation, 256 MB, 200 ms trung bình | Requests + GB-seconds |
| SQS | 20 triệu request/tháng, batch size đã xác định | Request units |
| CloudWatch Logs | 40 GB ingest/tháng, giữ 30 ngày | Ingest + storage + query |
| Backup | 1 TB recovery points warm, copy 1 Region DR | Storage + copy/transfer |

Các số trên là input giả định để thực hành. Khi làm dự án thật, phải thay bằng số liệu từ benchmark, analytics, access log, CloudWatch hoặc hệ thống tương đương. RDS class và EC2 type phải được chọn từ yêu cầu CPU/RAM/network và kết quả test tải.

### 10.3 Tạo estimate theo group

Tạo các group:

| Group | Service đưa vào |
|---|---|
| Edge and network | Route 53, CloudFront, ALB, NAT Gateway, VPC endpoints, data transfer |
| Application | EC2, EBS, Lambda, SQS |
| Data | RDS, ElastiCache, S3 |
| Operations and security | CloudWatch, KMS, Secrets Manager, AWS Backup |
| Disaster recovery | Copy Region, backup storage và tài nguyên DR nếu chạy standby |

Trong từng service, chọn Region thực tế và nhập các usage dimension tương ứng. Nếu calculator không có một dimension hoặc service cần thiết, ghi khoản đó vào assumptions/adjustment register và xác định cách ước tính riêng từ pricing page. Không bỏ qua khoản đó chỉ vì configurator không hiển thị.

### 10.4 Tạo ba kịch bản

| Kịch bản | Giả định | Mục đích |
|---|---|---|
| Low | Traffic thấp, cache hit cao, log volume thấp, burst hiếm | Kiểm tra chi phí khi adoption chậm |
| Base | Usage dự kiến từ business plan và benchmark | Dùng cho budget ban đầu |
| High | Traffic tăng, cache hit giảm, log/egress tăng, scale-out kéo dài | Kiểm tra ngân sách và khả năng chịu tải |

Kịch bản high không phải chỉ tăng 10% mọi dòng. Hãy tăng các driver có tương quan: request tăng có thể làm Lambda, SQS, logs, data transfer và database I/O tăng đồng thời. Một campaign có thể tạo peak trong vài giờ; không nhân peak cả tháng nếu workload chỉ đạt peak trong thời gian ngắn.

### 10.5 Đọc kết quả

Sau khi tính, kiểm tra:

- Thành phần nào chiếm tỷ trọng lớn nhất?
- Chi phí cố định nào vẫn xuất hiện khi traffic thấp?
- Thành phần nào tăng tuyến tính theo request hoặc data volume?
- Có chi phí tăng theo peak capacity hay số AZ không?
- Chi phí DR có bao gồm storage/copy nhưng chưa bao gồm compute failover không?
- Có khoản nào bị tính hai lần hoặc bị bỏ sót?
- Kịch bản high có vượt budget hoặc làm thay đổi lựa chọn kiến trúc không?

Nếu compute chiếm phần lớn, benchmark instance family, Graviton, autoscaling và commitment. Nếu network chiếm phần lớn, kiểm tra NAT, data transfer, cache và topology. Nếu storage/database chiếm phần lớn, kiểm tra retention, storage class, IOPS, query pattern và backup.

## 11. So sánh phương án kiến trúc bằng Calculator

Calculator có giá trị nhất khi dùng để so sánh các phương án có cùng yêu cầu chất lượng dịch vụ. Không chọn kiến trúc chỉ dựa vào monthly total nếu hai phương án có RPO, RTO, availability, latency hoặc security khác nhau.

### 11.1 Single-AZ và Multi-AZ

Tạo hai group hoặc hai estimate:

- Phương án A: một AZ, ít replica, chi phí thấp hơn nhưng blast radius và availability khác.
- Phương án B: nhiều AZ, có standby/replica, load balancer và network path tương ứng.

Tính đầy đủ compute, database standby, load balancer, inter-AZ traffic, NAT theo AZ, backup và data transfer. So sánh chi phí tăng thêm với mức giảm rủi ro downtime và mục tiêu SLA/SLO.

### 11.2 EC2 và container/serverless

So sánh EC2, ECS/Fargate, EKS hoặc Lambda với cùng throughput, latency và concurrency. Bao gồm:

- Capacity dự phòng và mức sử dụng CPU/RAM.
- Phí cluster/control plane nếu có.
- Load balancer, network, logs và image storage.
- Chi phí idle khi traffic thấp.
- Thời gian vận hành, patching, scaling và mức độ phức tạp.

Serverless không mặc định rẻ hơn cho workload luôn chạy và throughput cao; EC2 không mặc định rẻ hơn nếu utilization thấp. Benchmark và usage pattern mới quyết định.

### 11.3 Region A và Region B

Tạo group cho mỗi Region, nhưng giữ cùng workload assumption. So sánh service availability, giá compute/storage/database, data transfer, latency, compliance, support và chi phí kết nối. Nếu Region B cần copy dữ liệu từ Region A hoặc người dùng ở xa, phải cộng transfer/latency trade-off.

### 11.4 On-Demand và commitment

Đặt On-Demand làm baseline. Sau đó mô hình commitment cho phần baseline ổn định và giữ phần burst ở On-Demand. So sánh tổng chi phí trong toàn bộ term, upfront payment, monthly payment, unused commitment và rủi ro workload giảm.

Không so sánh monthly price riêng lẻ nếu một phương án có upfront payment. Dùng tổng chi phí trong term, cash flow và khả năng sử dụng commitment.

### 11.5 Storage class và retention

So sánh S3 Standard với Intelligent-Tiering hoặc các storage class phù hợp dựa trên access frequency, retrieval, minimum duration và lifecycle. Với EBS, so sánh gp3 với io2 dựa trên IOPS/latency cần thiết; với EFS/FSx, so sánh storage class và throughput. Tính cả backup, replication, restore và retrieval.

## 12. Những giả định và giới hạn cần công khai

Public calculator có một số giả định tổng quát quan trọng theo trang AWS Pricing Assumptions:

| Giả định | Ảnh hưởng đến estimate |
|---|---|
| 730 giờ/tháng | Không bằng chính xác số giờ của mọi tháng; không phản ánh leap year |
| USD | Quy đổi sang VND có thể thay đổi theo tỷ giá |
| Chưa bao gồm thuế | Thuế/VAT và khoản phải trả theo địa phương cần xử lý riêng |
| Free Tier không tự động áp dụng | Không mặc định giảm estimate bằng Free Tier hoặc credit |
| Promotional credits/discount không được tính đầy đủ trong public calculator | Actual bill có thể thấp hơn nếu account được hưởng ưu đãi |
| Tiered pricing | Usage hiện tại ngoài estimate có thể ảnh hưởng tier thực tế |
| Per-second billing | Một số service có cách tính theo giây; giả định calculator có thể khác actual |
| Third-party license | Marketplace/software license có thể không nằm trong estimate |
| Giá thay đổi | Giá On-Demand và feature/pricing model có thể cập nhật |
| Usage thực tế | Instance count, data transfer, request, retention và traffic khác giả định sẽ làm bill thay đổi |

Một số assumptions riêng của EC2:

- Default tenancy có thể là Shared Instances; phải thay nếu kiến trúc yêu cầu Dedicated.
- OS mặc định có thể là Linux; chọn đúng OS/license.
- Default instance count có thể là một.
- EBS volume mặc định có thể được điền sẵn; thay bằng số lượng và dung lượng thật.
- Detailed monitoring, data transfer, Elastic IP và additional costs cần được xem xét.
- Burstable instance có thể phát sinh chi phí CPU credit khi cấu hình/usage vượt baseline theo điều kiện dịch vụ.

Với public calculator, không giả định Free Tier, promotional credit hoặc discount sẽ được áp dụng nếu configurator không thể hiện rõ. Với in-console calculator, đọc rate preference, usage import và loại estimate để biết dữ liệu lịch sử/discount/commitment nào được tính.

## 13. Review estimate và kiểm tra tính hợp lý

Một quy trình review tốt nên kiểm tra cả kiến trúc, số lượng và đơn giá:

1. **Scope:** estimate bao gồm đúng workload, môi trường, Region và thời gian.
2. **Completeness:** mọi thành phần trong sơ đồ có dòng chi phí hoặc ghi rõ lý do không tính.
3. **Quantity:** instance-hours, GB-month, request, IOPS, GB transfer và retention khớp với workload.
4. **Pricing model:** On-Demand, Spot, RI hoặc Savings Plans đúng với tính ổn định và term.
5. **Architecture:** Multi-AZ, DR, replica, NAT, endpoints và load balancer được tính đầy đủ.
6. **Dependencies:** logs, metrics, backup, KMS, secrets, support và license đã được xét.
7. **Assumptions:** dữ liệu đã biết, giả định và unknown được phân biệt.
8. **Sensitivity:** low/base/high và driver làm chi phí thay đổi được giải thích.
9. **Double-count:** không cộng trùng thành phần đã được configurator tính.
10. **Owner:** mỗi giả định có người xác nhận và thời hạn cập nhật.

### 13.1 Sanity check theo tỷ trọng

Nếu một workload web nhỏ có chi phí NAT/data transfer lớn hơn nhiều lần compute, kiểm tra lượng GB qua NAT, số NAT gateway và đường đi traffic. Nếu database chiếm tỷ trọng lớn, xem class, Multi-AZ, storage, IOPS và replica. Nếu CloudWatch chiếm tỷ trọng bất thường, kiểm tra log ingestion, retention, custom metric cardinality và query scan.

Tỷ trọng không có giá trị chuẩn cho mọi kiến trúc. Mục tiêu là tìm ra dòng chi phí không phù hợp với mô hình sử dụng và xác minh lại đầu vào.

### 13.2 So sánh với baseline thực tế

Nếu đã có workload tương tự, dùng Cost Explorer hoặc Cost and Usage Report để lấy actual usage/cost làm baseline. Điều chỉnh cho quy mô, Region, traffic, instance size và thời gian vận hành. So sánh actual và estimate theo từng cost dimension, không chỉ tổng bill.

Với in-console calculator, có thể import usage lịch sử để tạo workload estimate và bill estimate. Với public calculator, tự thu thập số liệu lịch sử rồi nhập thành usage assumptions.

## 14. Lưu, chia sẻ, export và cập nhật estimate

### 14.1 Public share link

Public calculator tạo unique public link cho mỗi estimate. Link có thể chia sẻ với stakeholder hoặc dùng để mở lại estimate. Estimate được lưu trên public server của AWS; người có link có thể truy cập. Vì vậy:

- Không đưa secret, credential, customer PII hoặc thông tin nội bộ nhạy cảm vào description.
- Dùng tên workload và group ở mức phù hợp với phạm vi chia sẻ.
- Lưu link trong tài liệu dự án cùng ngày lập, owner và assumptions.
- Sau khi chỉnh sửa estimate, tạo link mới vì thay đổi không tự ghi đè link cũ.
- Kiểm tra ngày hết hạn của link; link tạo từ 31-05-2023 trở đi có hiệu lực một năm theo tài liệu AWS hiện hành.

### 14.2 Export CSV/PDF

Tại My estimate, chọn Export và xuất CSV hoặc PDF. CSV phù hợp để tổng hợp, pivot, so sánh service/group hoặc nhập vào bảng tính review. PDF phù hợp để gửi stakeholder và có chứa share link của estimate.

Export là snapshot tại thời điểm xuất. Nếu giá hoặc service configurator được cập nhật sau đó, file đã tải không tự đổi. Ghi ngày export và calculator version/update status trong hồ sơ estimate.

### 14.3 Cập nhật estimate cũ

Khi mở estimate đã lưu, kiểm tra trạng thái cập nhật:

- **Required inputs:** service configurator có thay đổi và cần nhập thông số mới.
- **Cost updated:** thay đổi pricing model hoặc phép tính ảnh hưởng tổng; calculator có thể tự cập nhật.
- **Read-only:** estimate cũ không hỗ trợ cập nhật trực tiếp; có thể cần tạo lại service estimate.
- **Check for updates:** group có service cần xem lại.

Sau khi cập nhật, kiểm tra tổng và các giả định bị thay đổi. Khi lưu thay đổi, tạo share link mới; link cũ không tự cập nhật.

### 14.4 In-console sharing và quyền truy cập

In-console calculator dùng quyền IAM/role và cơ chế quản lý estimate trong account. Đây là lựa chọn phù hợp hơn khi estimate chứa thông tin workload hoặc chi phí cần quản trị theo Organization. Kiểm tra quyền xem discount, quyền đọc usage lịch sử, Cost Explorer và phạm vi account trước khi yêu cầu member account tạo estimate.

## 15. Từ estimate đến FinOps

Estimate có giá trị nhất khi được kết nối với vòng đời vận hành:

    Yêu cầu sản phẩm
          |
    Kiến trúc và usage assumptions
          |
    AWS Pricing Calculator
          |
    Review kỹ thuật + tài chính
          |
    Budget / forecast / phê duyệt
          |
    Triển khai và gắn cost allocation tags
          |
    Cost Explorer / CUR / Billing
          |
    So sánh estimate với actual
          |
    Điều chỉnh kiến trúc và forecast

### 15.1 Estimate, budget và forecast khác nhau

| Khái niệm | Câu hỏi | Dữ liệu chính |
|---|---|---|
| Estimate | Kiến trúc dự kiến sẽ tốn bao nhiêu theo assumptions? | Cấu hình và usage dự kiến |
| Budget | Mức chi tiêu được phép là bao nhiêu? | Hạn mức và owner |
| Forecast | Với xu hướng hiện tại, cuối kỳ có thể chi bao nhiêu? | Actual usage, lịch sử và xu hướng |
| Actual cost | Đã phát sinh chi phí bao nhiêu? | Billing data, Cost Explorer, CUR |

Không dùng estimate như budget đã được phê duyệt hoặc forecast được đo từ actual. Chúng là các công cụ có mục đích khác nhau nhưng có thể liên kết với nhau.

### 15.2 Cost allocation

Đặt tag nhất quán như Application, Environment, Owner, CostCenter, BusinessUnit và DataClass. Dùng AWS Organizations, cost allocation tags và cost categories để phân bổ chi phí theo trách nhiệm. Nếu không gắn tag từ đầu, việc phân bổ chi phí sau khi hệ thống chạy có thể khó chính xác.

Estimate group có thể dùng cùng cấu trúc với cost center hoặc product stack để đối chiếu sau triển khai. Tuy nhiên, group trong calculator không tự động trở thành billing tag hoặc cost category; phải thiết lập cơ chế phân bổ trong Billing.

### 15.3 So sánh estimate với actual

Sau tháng đầu:

1. Lấy actual cost theo service, Region, usage type và tag.
2. So sánh quantity thực với quantity đã estimate.
3. Phân loại variance thành volume, rate, architecture, discount, timing hoặc missing service.
4. Cập nhật assumptions cho tháng tiếp theo.
5. Tạo action có owner: right-size, giảm log volume, chỉnh retention, thay storage class, tối ưu NAT/data transfer hoặc xem commitment.

Nếu actual cao hơn estimate, hãy tìm driver trước khi giảm tài nguyên. Một chi phí tăng có thể đến từ traffic tăng và phản ánh thành công kinh doanh; mục tiêu FinOps là tối ưu unit economics và giá trị, không chỉ làm tổng bill nhỏ hơn.

### 15.4 Unit economics

Ngoài tổng USD/tháng, hãy tính chi phí trên đơn vị kinh doanh:

- Cost per order.
- Cost per active user.
- Cost per API request.
- Cost per GB processed.
- Cost per training job hoặc inference request.
- Cost per tenant/customer.

Ví dụ:

    Cost per order = total workload cost / số đơn hàng hoàn tất

Nếu bill tăng 20% nhưng số đơn hàng tăng 50%, cost per order có thể giảm. Đây là góc nhìn tốt hơn khi quyết định scale hoặc đầu tư thêm capacity.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Giữ nguyên input mặc định | Estimate không phản ánh workload | Thay bằng số liệu inventory/benchmark |
| Chọn sai Region | Sai đơn giá, service availability và transfer | Chọn Region thực tế, tách group khi multi-Region |
| Dùng số instance tối đa × 730 giờ | Overestimate workload autoscaling | Tính baseline và burst-hours riêng |
| Chỉ tính compute | Thiếu storage, network, logs, backup | Review sơ đồ kiến trúc theo từng dependency |
| Bỏ qua NAT Gateway | Thiếu gateway-hour và GB processed | Tính số NAT theo AZ và traffic |
| Bỏ qua inter-AZ traffic | Thiếu chi phí mạng khi scale nhiều AZ | Đo luồng service-to-service |
| Chọn Multi-AZ rồi cộng standby lần nữa | Double-count database | Kiểm tra configurator đã bao gồm gì |
| Nhập GB cuối tháng thay cho trung bình | Sai GB-month | Mô hình hóa average storage và retention |
| Dùng request count mà bỏ duration | Sai chi phí Lambda/compute | Thu thập duration và memory/concurrency |
| Giả định discount sẽ áp dụng | Estimate thấp hơn actual | Xác minh rate preference và eligibility |
| Coi Spot là capacity bảo đảm | Rủi ro interruption và thiếu capacity | Dùng cho workload chịu interruption |
| Không tính Marketplace/license | Thiếu TCO | Thêm custom cost hoặc dòng điều chỉnh riêng |
| Coi estimate là báo giá | Quyết định tài chính sai | Ghi rõ assumptions, ngày và giới hạn |
| Không lưu link hoặc export | Không tái lập được estimate | Lưu link, CSV/PDF, owner và version |
| Không cập nhật estimate cũ | Giá/inputs có thể stale | Kiểm tra Required inputs/Cost updated/Read-only |

## 17. Bài thực hành: estimate một kiến trúc ba tầng

### Mục tiêu

Tạo một estimate cho web application có tầng frontend, application, database và storage; mô hình hóa ít nhất một phương án HA và một phương án tiết kiệm; lưu lại assumptions để người khác review.

### Chuẩn bị

- Chọn Region dự kiến triển khai.
- Chọn một workload giả định hoặc workload lab đã có benchmark.
- Chuẩn bị số instance, giờ chạy, storage, request, data transfer và retention.
- Xác định RPO/RTO, số AZ và nhu cầu DR.
- Chuẩn bị ba kịch bản low/base/high.

### Thực hiện

1. Mở public calculator tại https://calculator.aws/ và tạo estimate.
2. Tạo group Edge, Application, Data và Operations.
3. Thêm ALB/CloudFront/Route 53 nếu kiến trúc sử dụng.
4. Thêm EC2 hoặc ECS/Fargate và nhập instance/task count, hours, OS, storage.
5. Thêm RDS/Aurora hoặc DynamoDB; chọn engine/capacity, Multi-AZ, storage và I/O.
6. Thêm S3/EBS/EFS theo dung lượng trung bình, request, retrieval và retention.
7. Thêm NAT, data transfer và VPC endpoint phù hợp.
8. Thêm Lambda/SQS/API Gateway nếu có request-driven processing.
9. Thêm CloudWatch/backup/security theo lượng ingest, retention và protected storage.
10. Xem Show calculation, rà soát input mặc định và kiểm tra double-count.
11. Tạo group/estimate riêng cho phương án HA và phương án tối ưu chi phí.
12. Tạo low/base/high scenario, so sánh monthly, upfront và 12-month total.
13. Export CSV/PDF, lưu share link và viết assumptions register.

### Kết quả cần nộp

- Link hoặc bản export estimate.
- Sơ đồ kiến trúc và bảng usage assumptions.
- Bảng tổng chi phí theo group.
- So sánh ba kịch bản.
- Ít nhất ba driver ảnh hưởng nhiều nhất đến tổng cost.
- Giải thích trade-off giữa chi phí, availability, performance và security.

### Câu hỏi thảo luận

1. Nếu traffic tăng gấp đôi nhưng cache hit ratio tăng, những dòng chi phí nào thay đổi?
2. Khi chuyển sang Multi-AZ, chi phí nào tăng trực tiếp và chi phí nào phụ thuộc traffic?
3. Nếu ứng dụng chạy liên tục, khi nào commitment đáng cân nhắc?
4. Nếu estimate không có giá cho một thành phần, bạn sẽ ghi nhận và kiểm chứng khoản đó ra sao?
5. Sau một tháng chạy thật, dữ liệu nào cần lấy để hiệu chỉnh estimate?

## 18. Câu hỏi tự kiểm tra

**Câu 1.** AWS Pricing Calculator có phải báo giá chính thức không?

**Đáp án:** Không. Đây là estimate dựa trên usage assumptions, không bảo đảm actual cost và không bao gồm mọi khoản thuế/discount/third-party license.

**Câu 2.** Public calculator và in-console calculator khác nhau thế nào?

**Đáp án:** Public calculator không cần AWS account và tập trung vào public pricing assumptions. In-console calculator có thể dùng usage lịch sử, discounts và commitments; hỗ trợ workload estimate và bill estimate.

**Câu 3.** Bill estimate khác workload estimate ở điểm nào?

**Đáp án:** Workload estimate tập trung một workload/application; bill estimate mô hình hóa thay đổi trên consolidated bill và tính usage lịch sử cùng commitment hiện có, với điều kiện account/permission phù hợp.

**Câu 4.** Vì sao cần chọn Region trước khi cấu hình service?

**Đáp án:** Giá, service availability, instance availability, data transfer và tính năng có thể khác nhau giữa Region.

**Câu 5.** Public calculator giả định bao nhiêu giờ mỗi tháng?

**Đáp án:** 730 giờ/tháng theo Pricing Assumptions. Đây là quy ước 365 ngày/năm chia 12 tháng, không phải số giờ thực tế của mọi tháng.

**Câu 6.** Estimate có tự động tính thuế và promotional credits không?

**Đáp án:** Không nên giả định như vậy. Public calculator không bao gồm thuế và không tự tính Free Tier/credit/discount không được thể hiện trong configurator.

**Câu 7.** Khi ước tính EC2, cần nhập những thông tin nào ngoài instance type?

**Đáp án:** Region, OS, tenancy, số instance, workload pattern, hours, pricing model, EBS, data transfer, monitoring, Elastic IP và license/add-on liên quan.

**Câu 8.** Tại sao phải tách baseline và burst-hours?

**Đáp án:** Số instance tối đa không chạy liên tục cả tháng. Tách usage giúp tránh overestimate và hỗ trợ phân tích commitment cho baseline.

**Câu 9.** Savings Plans commitment được biểu diễn theo đơn vị nào?

**Đáp án:** Mức chi tiêu theo USD/giờ trong term cam kết; usage đủ điều kiện được hưởng mức ưu đãi.

**Câu 10.** Spot phù hợp với workload nào?

**Đáp án:** Workload có thể chịu interruption, checkpoint/retry được và không yêu cầu capacity luôn sẵn sàng.

**Câu 11.** Vì sao NAT Gateway thường bị bỏ sót?

**Đáp án:** Người thiết kế chỉ tính EC2 và data transfer tổng quát, quên gateway-hour và GB processed, đặc biệt khi triển khai NAT ở nhiều AZ.

**Câu 12.** Estimate Multi-AZ RDS có cần cộng standby instance riêng không?

**Đáp án:** Chỉ khi configurator chưa bao gồm nó. Phải kiểm tra cấu hình và Show calculation để tránh double-count.

**Câu 13.** Dung lượng storage cuối tháng có luôn bằng GB-month không?

**Đáp án:** Không. GB-month dựa trên dung lượng và thời gian lưu trong tháng; cần dùng dung lượng trung bình hoặc mô hình theo thời gian.

**Câu 14.** Estimate có tự bao gồm Marketplace software license không?

**Đáp án:** Không nhất thiết. Third-party licensing fees có thể không được tính; phải bổ sung hoặc ghi nhận riêng.

**Câu 15.** Public estimate link có tự cập nhật sau khi sửa không?

**Đáp án:** Không. Sau khi cập nhật estimate, cần lưu và tạo link mới; link cũ vẫn là phiên bản trước.

**Câu 16.** Vì sao nên export CSV?

**Đáp án:** CSV hỗ trợ pivot, so sánh service/group, review giả định và đối chiếu actual cost.

**Câu 17.** Estimate và forecast khác nhau thế nào?

**Đáp án:** Estimate dùng cấu hình/usage dự kiến; forecast dùng actual và xu hướng để dự báo chi phí cuối kỳ.

**Câu 18.** Vì sao unit economics hữu ích hơn tổng bill trong một số quyết định?

**Đáp án:** Nó cho biết chi phí trên mỗi đơn hàng/user/request và giúp phân biệt tăng trưởng kinh doanh với lãng phí.

## 19. Checklist trước khi trình estimate

- [ ] Xác định rõ workload, owner, môi trường, cost center và Region.
- [ ] Ghi nguồn dữ liệu và ngày cập nhật cho mọi usage assumption.
- [ ] Tách giá trị đã biết, giả định và unknown.
- [ ] Kiểm tra service availability và pricing model tại Region đã chọn.
- [ ] Nhập đúng instance type, OS, tenancy, count và hours.
- [ ] Tính EBS, S3, EFS/FSx, database storage, I/O và backup.
- [ ] Tính NAT, load balancer, public IPv4, VPC endpoint và data transfer theo từng tuyến.
- [ ] Tính API/request, Lambda duration, message, event và retry.
- [ ] Tính log ingestion, metric cardinality, trace sampling và retention.
- [ ] Kiểm tra support, Marketplace, license, tax và khoản ngoài Calculator.
- [ ] So sánh On-Demand, Spot, RI/Savings Plans khi workload phù hợp.
- [ ] Kiểm tra upfront, monthly và 12-month cost.
- [ ] Tạo low/base/high scenario và nêu driver nhạy cảm.
- [ ] Rà soát Multi-AZ/DR, dependency và double-count.
- [ ] Ghi rõ calculator version/date, currency và assumptions.
- [ ] Export CSV/PDF và lưu share link phù hợp với chính sách chia sẻ.
- [ ] Có người review kỹ thuật và tài chính trước khi phê duyệt.
- [ ] Đặt lịch so sánh estimate với actual sau khi triển khai.

## 20. Tài liệu tham khảo chính thức

1. [AWS Pricing Calculator – What is the calculator?](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/what-is-pricing-calculator.html) — chức năng, phạm vi và public calculator.
2. [Getting started](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/getting-started.html) — truy cập, cấu trúc console và giả định Free Tier.
3. [Create and configure an estimate](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/create-configure-estimate.html) — quy trình thêm service và cấu hình.
4. [Using groups to organize estimates](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/estimate-groups.html) — nhóm theo cost center, product stack và Region.
5. [AWS Pricing Assumptions](https://aws.amazon.com/calculator/calculator-assumptions/) — giả định chung, 730 giờ/tháng, USD, taxes, tiered pricing và các giới hạn.
6. [Generating Amazon EC2 estimates](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/ec2-estimates.html) — EC2, workload pattern, payment options, EBS và data transfer.
7. [Sharing your estimate](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/save-share-estimate.html) — public link và cập nhật estimate.
8. [Exporting your estimates](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/export-estimate.html) — export CSV/PDF.
9. [Generating estimates with Pricing Calculator](https://docs.aws.amazon.com/cost-management/latest/userguide/pricing-calculator.html) — phân biệt public và in-console calculator, workload/bill estimate.
10. [AWS Pricing Calculator FAQs](https://aws.amazon.com/aws-cost-management/aws-pricing-calculator/faqs/) — assumptions, discounts, usage history và commitment.
11. [AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html) — dữ liệu giá và cách theo dõi thay đổi giá.
12. [AWS Savings Plans](https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html) — phạm vi và cơ chế commitment.
13. [Amazon EC2 pricing](https://aws.amazon.com/ec2/pricing/) — mô hình giá EC2, RI và Spot.
14. [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/) — volume, provisioned performance và snapshot.
15. [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) — storage class, request, retrieval và transfer.
16. [Amazon RDS pricing](https://aws.amazon.com/rds/pricing/) — DB instance, storage, I/O và deployment option.
17. [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/) — NAT Gateway, endpoint và data processing.
18. [AWS Data Transfer pricing](https://aws.amazon.com/ec2/pricing/on-demand/#Data_Transfer) — phân biệt các tuyến transfer.
19. [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html) — phân tích chi phí và usage thực tế.
20. [AWS Cost and Usage Reports](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html) — dữ liệu chi phí chi tiết để đối chiếu estimate.

---

**Kết luận:** Một estimate đáng tin bắt đầu từ mô hình workload, không phải từ giá trị mặc định của calculator. Hãy tính đủ các dịch vụ và dependency, chọn đúng Region và pricing model, ghi rõ assumptions, so sánh các kịch bản và review các khoản dễ bị bỏ sót. Sau khi triển khai, đối chiếu estimate với actual cost để biến ước tính ban đầu thành một vòng lặp FinOps liên tục.
