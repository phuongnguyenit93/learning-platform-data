# Spot interruption và thiết kế workload chịu gián đoạn

## 1. Amazon EC2 Spot giải quyết bài toán nào?

Amazon EC2 Spot cho phép sử dụng phần compute capacity chưa được EC2 dùng đến với mức giá thấp hơn On-Demand. AWS công bố mức tiết kiệm có thể lên đến 90% so với giá On-Demand, nhưng giá và khả năng cấp capacity phụ thuộc instance type, Availability Zone (AZ), thời điểm và nhu cầu của hệ thống.

Đổi lại, AWS có thể thu hồi Spot Instance khi cần capacity. Một instance có thể bị interrupt dù ứng dụng vẫn khỏe và không có lỗi cấu hình. Vì vậy, Spot phù hợp với workload có thể tạm dừng, chạy lại, phân chia thành phần nhỏ hoặc chuyển công việc sang worker khác.

Một thiết kế Spot tốt không cố giữ một máy cụ thể chạy mãi. Nó duy trì kết quả nghiệp vụ dù worker bị thay thế. Các kỹ thuật thường dùng gồm:

- Chia workload thành task nhỏ và độc lập.
- Checkpoint tiến độ vào storage bền vững.
- Dùng queue để phân phối công việc.
- Xử lý message idempotently để retry không tạo side effect trùng.
- Theo dõi tín hiệu interruption và chủ động drain worker.
- Dùng Auto Scaling Capacity Rebalancing để thay instance có nguy cơ bị thu hồi.
- Kết hợp On-Demand capacity cho phần workload cần bảo đảm hơn.

Spot là một công cụ tối ưu chi phí cho compute có khả năng chịu gián đoạn. Nó không phải cam kết capacity luôn có sẵn hoặc một cơ chế HA tự động thay thế thiết kế fault-tolerant của ứng dụng.

## 2. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích Spot capacity pool, Spot price và nguyên nhân interruption.
2. Phân biệt rebalance recommendation với Spot interruption notice.
3. Mô tả hành vi terminate, stop và hibernate khi Spot bị thu hồi.
4. Thu nhận tín hiệu interruption từ EventBridge và EC2 Instance Metadata Service v2 (IMDSv2).
5. Thiết kế shutdown/drain sequence trong khoảng thời gian cảnh báo.
6. Dùng EC2 Auto Scaling Capacity Rebalancing và allocation strategy phù hợp.
7. Tạo instance flexibility bằng nhiều instance types và AZ.
8. Kết hợp On-Demand baseline với Spot capacity linh hoạt.
9. Thiết kế queue worker, batch job, container và Kubernetes workload chịu interruption.
10. Dùng checkpoint, idempotency, retry và persistent storage để bảo toàn tiến độ.
11. Kiểm thử interruption bằng AWS Fault Injection Service (FIS).
12. Đo cost per completed work unit và xây dựng runbook vận hành.

## 3. Khi nào nên dùng Spot?

Spot phù hợp khi công việc có thể được retry, phân phối hoặc tiếp tục từ checkpoint.

| Workload | Mức phù hợp | Điều kiện thiết kế |
|---|---|---|
| Batch processing | Rất phù hợp | Job chia nhỏ, retry và checkpoint |
| CI build/test runner | Phù hợp | Pipeline có thể chạy lại, artifact lưu ngoài instance |
| Queue consumers | Phù hợp | Message ack sau commit, idempotent, visibility timeout phù hợp |
| Stateless web/API tier | Phù hợp | Có On-Demand baseline, nhiều AZ, load balancing và autoscaling |
| Data ETL / analytics | Phù hợp | Lưu intermediate state bền vững, chia partition |
| ML training | Phù hợp có điều kiện | Checkpoint model/optimizer thường xuyên, resume được |
| Rendering / transcoding | Phù hợp | Chia frame/chunk, lưu output ngoài instance |
| HPC / simulation | Phù hợp có điều kiện | Distributed checkpoint, xử lý worker mất và giao tiếp lại |
| Database primary | Không phù hợp | Database cần compute ổn định và stateful |
| Stateful single-node service | Không phù hợp | Mất node có thể mất trạng thái hoặc làm gián đoạn toàn bộ dịch vụ |
| Workload có SLA không chấp nhận thiếu capacity | Không phù hợp | Dùng On-Demand hoặc capacity reservation phù hợp |

Không đánh giá một workload chỉ dựa vào việc process có thể khởi động lại. Cần xác định chi phí chạy lại, khả năng mất dữ liệu chưa commit, thời gian phục hồi, tính toàn vẹn nghiệp vụ và capacity thay thế.

## 4. Spot capacity pool và tính linh hoạt

Một Spot capacity pool là tổ hợp của:

- Instance type, ví dụ `m7i.large`.
- Availability Zone, ví dụ một AZ trong Region.

Hai pool cùng instance type nhưng khác AZ được xem là hai pool riêng. Năng lực capacity của mỗi pool biến động theo cung/cầu.

Nếu chỉ cho phép một instance type ở một AZ, workload phụ thuộc vào một pool. Khi pool đó cạn capacity hoặc có nguy cơ bị thu hồi, hệ thống có ít lựa chọn thay thế.

Tăng tính linh hoạt bằng cách:

- Chọn nhiều instance types có cùng khả năng xử lý workload.
- Cho phép nhiều AZ nếu dữ liệu và kiến trúc hỗ trợ.
- Dùng attribute-based instance type selection khi phù hợp.
- Tránh ràng buộc launch group hoặc Availability Zone group nếu không thật sự cần.
- Dùng nhiều pool để phân tán rủi ro.

Instance types thay thế cần tương thích về CPU architecture, số vCPU, memory, GPU, network bandwidth, EBS bandwidth, local NVMe và license. Một instance có nhiều vCPU hơn không nhất thiết thay thế trực tiếp được nếu ứng dụng bị giới hạn bởi memory hoặc GPU.

### 4.1. Spot placement score

Spot placement score giúp ước lượng khả năng đáp ứng một yêu cầu Spot capacity tại Region/AZ và cấu hình đã chọn. Score phản ánh điều kiện capacity tại thời điểm truy vấn, không phải cam kết capacity sẽ còn khi launch hoặc trong suốt thời gian chạy.

Dùng score để so sánh phương án placement trước khi tạo fleet lớn. Lấy score mới khi điều kiện hoặc cấu hình thay đổi.

## 5. Vì sao Spot Instance bị interrupt?

EC2 có thể thu hồi Spot Instance trong các trường hợp chính:

1. **Capacity:** AWS cần lấy lại capacity để phục vụ nhu cầu khác, bảo trì host hoặc thay đổi hạ tầng.
2. **Price constraint:** nếu request đặt maximum price và Spot price vượt ngưỡng đó, instance có thể bị interrupt. AWS khuyến nghị không đặt maximum price nếu không có lý do đặc biệt; đặt ngưỡng có thể làm interruption thường xuyên hơn.
3. **Request constraints:** một số ràng buộc như launch group hoặc Availability Zone group có thể khiến các instance liên quan bị thu hồi theo nhóm khi không còn đáp ứng được constraint.

Spot price thay đổi theo cung/cầu dài hạn và không phải là tín hiệu duy nhất quyết định interruption. Một pool giá thấp vẫn có thể có capacity khan hiếm. Vì vậy, chỉ chọn pool có giá thấp nhất không phải cách giảm interruption tốt.

## 6. Ba hành vi khi Spot bị interrupt

Khi tạo Spot request, có thể chọn interruption behavior phù hợp trong các trường hợp dịch vụ hỗ trợ:

| Behavior | Kết quả | Khi nào cân nhắc |
|---|---|---|
| Terminate | Instance bị chấm dứt; dữ liệu EBS còn lại tùy cấu hình volume/lifecycle | Phổ biến cho fleet/Auto Scaling và worker có thể thay thế |
| Stop | Instance dừng; EBS volumes được giữ và chỉ còn phí lưu trữ khi stopped | Standalone persistent Spot request cần tiếp tục lại cùng instance |
| Hibernate | RAM được lưu vào encrypted EBS root volume rồi instance chuyển stopped | Một số ứng dụng cần resume process state và đáp ứng hibernate prerequisites |

Terminate là behavior mặc định. Với stop, Spot request phải là persistent và phải đáp ứng giới hạn của Spot request/EC2 Fleet. Khi capacity phù hợp xuất hiện trở lại, EC2 có thể khởi động lại instance theo request.

Hibernation có điều kiện về instance type, AMI, root EBS volume, encryption, RAM và cấu hình hệ điều hành. Dữ liệu trên instance store bị mất khi hibernate. Không dùng hibernate cho instance thuộc Auto Scaling group hoặc instance được Amazon ECS quản lý; các hệ thống này cần lifecycle và replacement theo mô hình của chúng.

**Lưu ý về thời gian cảnh báo:** với terminate/stop, Spot interruption notice thường được gửi khoảng hai phút trước khi EC2 thu hồi instance. Với hibernate, quá trình hibernation bắt đầu ngay và không có khoảng hai phút shutdown như terminate/stop. Không thiết kế quy trình phụ thuộc vào việc luôn có đủ hai phút.

## 7. Hai tín hiệu quan trọng: rebalance recommendation và interruption notice

### 7.1. EC2 Instance Rebalance Recommendation

Rebalance recommendation thông báo instance đang có nguy cơ interruption cao hơn. Tín hiệu này có thể đến sớm hơn interruption notice và cho phép hệ thống chủ động:

- Ngừng giao công việc mới cho instance.
- Khởi chạy capacity thay thế.
- Chuyển task hoặc checkpoint sang worker khác.
- Drain target khỏi load balancer.
- Thu thập log và metadata.

Tín hiệu không đảm bảo luôn đến trước interruption notice. Có trường hợp hai tín hiệu xuất hiện gần như đồng thời.

### 7.2. Spot Instance Interruption Notice

Interruption notice thông báo EC2 dự kiến stop hoặc terminate Spot Instance. Với terminate/stop, thời gian cảnh báo thường khoảng hai phút.

AWS phát notice dưới dạng:

- EventBridge event.
- Metadata trên chính Spot Instance.

Các notice được phát theo best-effort basis. Vì vậy, ứng dụng phải chịu được interruption ngay cả khi không nhận được event.

AWS khuyến nghị kiểm tra metadata interruption mỗi 5 giây. Không chờ đến notice mới bắt đầu thiết kế checkpoint; hãy sử dụng rebalance recommendation để có thêm thời gian.

## 8. Nhận interruption notice bằng IMDSv2

Trên Linux Spot Instance, có thể lấy token IMDSv2 rồi kiểm tra `spot/instance-action`.

Ví dụ:

```bash
TOKEN=$(curl -sS -X PUT \
  "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

curl -sS \
  -H "X-aws-ec2-metadata-token: $TOKEN" \
  "http://169.254.169.254/latest/meta-data/spot/instance-action"
```

Khi không có interruption đang chờ, endpoint có thể trả HTTP 404. Đây là trạng thái bình thường, không phải lỗi cần restart ứng dụng.

Khi có action, response có dạng:

```json
{
  "action": "terminate",
  "time": "2026-11-20T08:22:00Z"
}
```

Các giá trị action có thể gồm `terminate`, `stop` hoặc `hibernate`. Ứng dụng nên:

1. Poll endpoint định kỳ, khoảng 5 giây.
2. Xử lý 404 như không có interruption pending.
3. Khi có action, chuyển instance sang trạng thái draining.
4. Ngừng nhận work mới.
5. Ghi checkpoint và flush dữ liệu.
6. Gửi trạng thái shutdown về control plane nếu còn thời gian.

Sử dụng IMDSv2 và không hardcode token. Cấu hình metadata endpoint chỉ cho phép IMDSv2 khi workload tương thích.

## 9. Nhận interruption bằng Amazon EventBridge

EventBridge cho phép xử lý interruption bên ngoài instance. Ví dụ rule cho Spot interruption notice:

```json
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Spot Instance Interruption Warning"]
}
```

Rule cho rebalance recommendation:

```json
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Instance Rebalance Recommendation"]
}
```

Một event interruption mẫu:

```json
{
  "version": "0",
  "id": "12345678-1234-1234-1234-123456789012",
  "detail-type": "EC2 Spot Instance Interruption Warning",
  "source": "aws.ec2",
  "region": "ap-southeast-1",
  "resources": [
    "arn:aws:ec2:ap-southeast-1a:111122223333:instance/i-0123456789abcdef0"
  ],
  "detail": {
    "instance-id": "i-0123456789abcdef0",
    "instance-action": "terminate"
  }
}
```

EventBridge target có thể là Lambda, SQS, SNS hoặc Systems Manager Automation tùy quy trình. Một handler bên ngoài instance có thể:

- Tìm workload/ASG/cluster liên quan.
- Đánh dấu instance sắp bị thu hồi.
- Dừng scheduler giao task mới.
- Gửi lệnh checkpoint.
- Ghi incident record và phát notification.
- Theo dõi replacement instance.

Không dùng EventBridge làm nguồn tín hiệu duy nhất vì interruption notices và rebalance recommendations là best-effort. Kết hợp event với metadata polling và khả năng tự phục hồi của workload.

## 10. Quy trình graceful shutdown trong thời gian ngắn

Với termination notice, hãy ưu tiên thao tác có giá trị cao và hoàn tất nhanh. Một sequence điển hình:

1. Đánh dấu instance `DRAINING`.
2. Ngừng nhận request hoặc task mới.
3. Gỡ target khỏi load balancer hoặc queue consumer pool.
4. Hoàn tất transaction đang commit nếu có thể.
5. Lưu checkpoint vào S3, EFS, FSx hoặc database phù hợp.
6. Ghi trạng thái task, offset, partition hoặc lease.
7. Flush log và metric quan trọng.
8. Release distributed lock/lease có kiểm soát.
9. Báo control plane rằng instance đã sẵn sàng kết thúc.

Không cố hoàn tất toàn bộ workload dài trong hai phút. Nếu công việc không thể kết thúc trong cửa sổ này, hãy checkpoint và giao phần còn lại cho worker khác.

Graceful shutdown phải có timeout nội bộ ngắn hơn deadline dự kiến. Khi không kịp hoàn tất, process cần dừng an toàn và để retry/recovery tiếp tục. Một shutdown script bị treo không thể ngăn EC2 thu hồi instance.

## 11. Thiết kế application chịu interruption

### 11.1. Stateless compute

Đối với web/API và microservice:

- Không giữ session duy nhất trong memory của một Spot Instance.
- Lưu upload và artifact lên S3.
- Lưu session/cache trong dịch vụ dùng chung phù hợp.
- Dùng ALB và nhiều instance/AZ.
- Có On-Demand baseline nếu dịch vụ cần capacity tối thiểu ổn định.
- Khi nhận rebalance recommendation, ngừng gửi request mới tới instance đó.

Spot có thể phù hợp cho phần capacity mở rộng theo tải, trong khi On-Demand duy trì mức capacity nền. Không giả định Spot luôn đủ để đáp ứng minimum service capacity.

### 11.2. Checkpointable jobs

Chia job dài thành các bước có thể lưu tiến độ:

- Đọc input theo partition hoặc range.
- Lưu output trung gian vào S3/EFS/FSx.
- Ghi checkpoint gồm job ID, partition, offset, step và version.
- Khi worker mới nhận job, đọc checkpoint rồi tiếp tục.
- Commit kết quả theo transaction hoặc idempotency key.

Checkpoint cần atomic hoặc có version để tránh worker cũ ghi đè tiến độ mới. Không chỉ lưu biến tiến độ trong local disk hoặc RAM.

### 11.3. Idempotency và duplicate execution

Interruption có thể xảy ra sau khi consumer đã thực hiện side effect nhưng trước khi acknowledge message. Message được giao lại là điều bình thường.

Dùng idempotency key theo business operation, unique constraint theo event/job ID, conditional writes hoặc transaction, lease/lock có expiration và output path theo job ID/attempt/version.

Mẫu xử lý:

1. Nhận message hoặc job.
2. Kiểm tra idempotency key.
3. Đọc checkpoint/version gần nhất.
4. Thực hiện một phần công việc.
5. Commit kết quả và trạng thái bằng thao tác nguyên tử nếu có thể.
6. Chỉ acknowledge message sau khi commit thành công.

Không coi việc queue chỉ giao một lần là bảo đảm cho side effect của ứng dụng.

## 12. EC2 Auto Scaling Capacity Rebalancing

Capacity Rebalancing giúp Auto Scaling group chủ động thay Spot Instance nhận rebalance recommendation.

Khi bật tính năng:

1. EC2 Spot gửi rebalance recommendation.
2. Auto Scaling đánh giá và cố gắng launch Spot Instance thay thế.
3. Instance mới cần pass health check.
4. Sau khi replacement khỏe, Auto Scaling bắt đầu terminate instance cũ.
5. Lifecycle hook có thể thực hiện drain/shutdown bổ sung.

Tính năng này giúp replacement được chuẩn bị trước khi instance cũ bị thu hồi. Nó không bảo đảm replacement luôn launch được vì pool có thể hết capacity hoặc health check thất bại.

Auto Scaling chỉ chủ động launch replacement khi pool mới có mức availability bằng hoặc tốt hơn instance đang có rebalance recommendation. Nếu pool thay thế có nguy cơ interruption cao hơn, hệ thống tiếp tục đánh giá các pool khác; instance cũ vẫn có thể bị interrupt trước khi replacement sẵn sàng.

Auto Scaling có thể tạm vượt maximum size của group tới 10% desired capacity để launch replacement trước khi terminate instance cũ. Do đó, cần dự trù headroom và chi phí capacity tạm thời.

### 12.1. Bật Capacity Rebalancing

Ví dụ:

```bash
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name workers-spot-asg \
  --capacity-rebalance \
  --region ap-southeast-1
```

Kiểm tra cấu hình:

```bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names workers-spot-asg \
  --region ap-southeast-1 \
  --query "AutoScalingGroups[].{CapacityRebalance:CapacityRebalance,Desired:DesiredCapacity,Min:MinSize,Max:MaxSize,AZs:AvailabilityZones,Instances:Instances[].{Id:InstanceId,AZ:AvailabilityZone,Health:HealthStatus,State:LifecycleState}}"
```

### 12.2. Lifecycle hooks

Lifecycle hook hữu ích để drain worker, gỡ instance khỏi service discovery, flush log và checkpoint, thu thập metadata, cập nhật trạng thái job.

Tuy nhiên, Spot interruption có hard deadline. EC2 có thể forcibly terminate instance sau cửa sổ cảnh báo khoảng hai phút ngay cả khi lifecycle hook chưa hoàn tất. Hook không kéo dài thời gian EC2 giữ Spot capacity. Vì vậy, hook là cơ hội thực hiện cleanup, không phải bảo đảm shutdown hoàn tất.

## 13. Chọn allocation strategy và đa dạng hóa capacity

AWS khuyến nghị `price-capacity-optimized` cho phần lớn Spot workload. Strategy này cân bằng giá và khả năng capacity, chọn các pool có khả năng ít bị interrupt hơn trong số các pool có giá tốt.

| Strategy | Dịch vụ hỗ trợ | Hành vi | Use case |
|---|---|---|---|
| `price-capacity-optimized` | Auto Scaling, EC2 Fleet, Spot Fleet | Ưu tiên pool có capacity tốt rồi cân nhắc giá | Lựa chọn mặc định tốt cho phần lớn workload |
| `capacity-optimized` | Auto Scaling, EC2 Fleet, Spot Fleet | Ưu tiên pool có capacity sẵn có cao | Workload có chi phí interruption cao |
| `capacity-optimized-prioritized` | Auto Scaling, EC2 Fleet, Spot Fleet | Tối ưu capacity, đồng thời cân nhắc priority của instance type theo best effort | Workload có yêu cầu thứ tự ưu tiên instance |
| `diversified` | EC2 Fleet, Spot Fleet | Phân bổ trên nhiều Spot pools | Fleet lớn, muốn giảm phụ thuộc một pool |

Lưu ý: `diversified` là strategy của EC2 Fleet/Spot Fleet, không nằm trong danh sách allocation strategies Spot của EC2 Auto Scaling group. Với Auto Scaling group, chọn một trong các strategy được hỗ trợ trong tài liệu hiện hành.

Tránh `lowest-price` cho production workload cần tính sẵn sàng. Strategy này chỉ xét giá và có thể chọn pool có rủi ro interruption cao hơn.

### 13.1. Instance flexibility

Ví dụ workload cần 4 vCPU và 16 GiB memory có thể đánh giá nhiều instance family tương thích thay vì cố định một type. Cần kiểm tra CPU architecture, instruction set, memory, network/EBS bandwidth, GPU/local storage, AMI/driver và license.

Với Auto Scaling mixed instances policy, dùng nhiều instance type và nhiều AZ để tăng số Spot pools có thể chọn.

### 13.2. Spot placement score không phải reservation

Placement score phản ánh xác suất tương đối tại thời điểm hỏi. Score cao không bảo đảm launch thành công hoặc instance không bị interrupt sau đó. Không coi placement score là capacity reservation.

## 14. Kết hợp Spot với On-Demand capacity

Một pattern thường dùng là giữ On-Demand baseline cho phần tải thiết yếu và dùng Spot cho capacity linh hoạt.

Ví dụ:

- On-Demand: API capacity tối thiểu, control plane, coordinator, monitoring.
- Spot: worker xử lý queue, batch, rendering, ETL hoặc phần web capacity có thể thay thế.
- Khi Spot pool thiếu capacity, hệ thống giảm tốc độ xử lý, giữ backlog trong queue hoặc dùng thêm capacity theo policy đã định.

Với Auto Scaling mixed instances policy, có thể xác định:

- `OnDemandBaseCapacity`: số capacity On-Demand nền.
- `OnDemandPercentageAboveBaseCapacity`: tỷ lệ On-Demand trên phần capacity vượt baseline.
- `SpotAllocationStrategy`: chiến lược chọn Spot pools.

Không đặt On-Demand fallback ở mức vô hạn. Khi Spot thiếu capacity, chi phí có thể tăng đáng kể nếu mọi phần tải chuyển sang On-Demand. Đặt quota, maximum capacity, budget alert và admission control phù hợp.

## 15. Amazon ECS: draining task trên Spot

### 15.1. ECS trên EC2 Spot

Nếu ECS cluster dùng Auto Scaling group capacity provider:

- Bật managed instance draining nếu phù hợp.
- Cấu hình managed termination protection theo chính sách scale-in.
- Đảm bảo service có desired task count và placement trên nhiều instance/AZ.
- Thiết lập minimumHealthyPercent/maximumPercent phù hợp với deployment.
- Task cần xử lý SIGTERM và dừng nhận công việc mới.
- Dùng health check và load balancer deregistration delay hợp lý.

ECS managed instance draining có thể đưa container instance vào trạng thái DRAINING khi instance bị thay thế hoặc nhận Spot interruption. Scheduler cố gắng chuyển task sang instance khác.

Nếu dùng managed instance draining, không cần bật riêng `ECS_ENABLE_SPOT_INSTANCE_DRAINING` cho cùng mục đích. Cấu hình termination protection và draining đúng với capacity provider; hai tính năng giải quyết hai mục tiêu khác nhau.

### 15.2. Fargate Spot

Fargate Spot cung cấp capacity Fargate với giá Spot. Khi task bị interrupt, ECS gửi cảnh báo khoảng hai phút trước khi dừng task qua task state change event trên EventBridge và gửi SIGTERM đến container. Ứng dụng cần xử lý tín hiệu này để shutdown có kiểm soát.

Ứng dụng cần bắt SIGTERM, ngừng nhận request/job mới, flush output và checkpoint, hoàn tất cleanup trong thời gian cho phép, và để SQS hoặc workflow retry task nếu chưa commit.

Fargate Spot không tự chuyển task sang Fargate On-Demand khi Spot capacity không có. Capacity provider strategy cần có On-Demand/Fargate capacity nếu dịch vụ yêu cầu mức phục vụ ổn định.

## 16. Amazon EKS: node và pod chịu interruption

### 16.1. EKS managed node groups với Spot

EKS managed node group có capacity type Spot sẽ cấu hình Auto Scaling group và Capacity Rebalancing theo best practices của EKS. Dùng nhiều instance types để tăng số capacity pools.

Khi có rebalance recommendation, EKS cố gắng launch node thay thế. Khi node mới Ready, EKS cordon và drain node cũ. Nếu interruption notice đến trước khi node mới Ready, EKS vẫn bắt đầu drain theo best effort.

Không giả định mọi Pod có đủ hai phút. EKS drain tuần tự để bảo vệ Kubernetes API server; khi nhiều node bị thu hồi cùng lúc hoặc node có mật độ Pod cao, một số Pod có thể nhận tín hiệu trễ hoặc bị terminate cưỡng bức.

Với Spot workloads:

- Dùng Pod termination grace period ngắn, AWS khuyến nghị 30 giây hoặc ít hơn.
- Tránh preStop hook dài.
- Dùng topology spread constraints để tránh mọi replica nằm trên cùng node/AZ.
- Dùng PodDisruptionBudget phù hợp nhưng không coi PDB là bảo đảm chống Spot reclaim.
- Lưu checkpoint ra storage bền vững.
- Theo dõi Pod eviction và node termination metrics.

Workload cần graceful termination được bảo đảm nên dùng On-Demand capacity.

### 16.2. Karpenter interruption handling

Karpenter có thể theo dõi interruption events thông qua SQS interruption queue. Khi nhận event, Karpenter taint, drain node và launch node mới để chuyển Pod.

Nếu bật interruption handling:

- Tạo queue và cấu hình EventBridge rules theo hướng dẫn Karpenter.
- Cấp IAM permission cho Karpenter đọc queue.
- Cấu hình `--interruption-queue` hoặc Helm value tương ứng.
- Thiết kế Pod disruption và checkpoint.
- Không đồng thời bật Node Termination Handler cho cùng loại interruption nếu chưa hiểu xung đột và hành vi của hai controller.

## 17. AWS Batch, EMR và workload xử lý dữ liệu

### 17.1. AWS Batch

AWS Batch phù hợp với job có thể retry hoặc checkpoint. Khi dùng Spot:

- Chia job thành phần nhỏ.
- AWS khuyến nghị checkpoint hoặc chia job thành các phần khoảng 30 phút hoặc ngắn hơn.
- Tránh job chạy liên tục hàng giờ mà không có checkpoint.
- Cấu hình retry strategy; Batch hỗ trợ từ 1 đến 10 attempts.
- Dùng 1-3 retries làm điểm khởi đầu rồi điều chỉnh theo failure profile.
- Lưu checkpoint và output vào S3/EFS/FSx thay vì local-only state.
- Dùng `evaluateOnExit` để phân biệt lỗi có thể retry và lỗi cấu hình/validation cần dừng.

Retry không sửa được job deterministic luôn thất bại. Nếu nguyên nhân là dữ liệu lỗi hoặc permission denied, cần chuyển trạng thái FAILED và cảnh báo thay vì retry vô hạn.

### 17.2. Amazon EMR và Spark

Spot có thể phù hợp với task nodes hoặc executor capacity có thể được thay thế. Đối với dữ liệu lớn:

- Giữ dữ liệu nguồn và kết quả trung gian ở S3/HDFS phù hợp.
- Chọn partition size để task có thời gian chạy hợp lý.
- Dùng speculative execution hoặc retry task theo engine nếu phù hợp.
- Tránh đặt metadata/control plane quan trọng lên Spot.
- Kiểm tra tác động khi mất nhiều executor cùng lúc.

### 17.3. ML training và HPC

Checkpoint cần bao gồm model weights, optimizer state, epoch/step, random seed và dataset cursor nếu cần tái lập. Lưu checkpoint theo version và ghi manifest để resume chính xác.

Đối với distributed training, cần xác định behavior khi một worker biến mất: restart toàn bộ job, elastic training hoặc tiếp tục từ checkpoint. Chọn strategy theo framework và mức chi phí restart.

## 18. Queue workers: pattern phổ biến để tận dụng Spot

Một worker đọc SQS message và thực hiện job. Khi nhận interruption:

1. Worker ngừng nhận message mới.
2. Nếu đang xử lý message, checkpoint tiến độ.
3. Nếu có thể hoàn thành trong thời gian còn lại, commit side effect.
4. Xóa message chỉ sau khi commit thành công.
5. Nếu chưa thể hoàn thành, để visibility timeout hết hạn hoặc điều chỉnh visibility phù hợp để message được retry.
6. Worker khác nhận lại và tiếp tục từ checkpoint.

Đặt visibility timeout lớn hơn thời gian xử lý dự kiến nhưng không dài đến mức làm chậm recovery. Với job dài, dùng ChangeMessageVisibility và checkpoint định kỳ. Cấu hình DLQ để cô lập poison message.

Không xóa message trước khi kết quả được commit. Nếu worker bị interrupt sau khi xóa message nhưng trước khi ghi output, công việc có thể mất.

## 19. Lưu trữ và state khi instance bị thu hồi

| Storage | Khi terminate/stop | Cách dùng |
|---|---|---|
| Instance store | Dữ liệu mất khi instance terminate hoặc stop/start | Cache/tạm thời, không giữ dữ liệu duy nhất |
| EBS volume | Có thể giữ hoặc xóa tùy DeleteOnTermination và behavior | Dữ liệu cần tồn tại qua instance replacement |
| S3 | Dữ liệu bền vững theo lifecycle/policy của bucket | Checkpoint, artifact, output, logs |
| EFS | Shared file system cho nhiều compute | Shared state hoặc checkpoint phù hợp |
| FSx | Shared/high-performance file system tùy loại | HPC, ML và workload cần throughput |
| DynamoDB/RDS | Durable structured state | Job state, lease, idempotency records |

Hibernation lưu RAM vào encrypted EBS root volume theo cơ chế suspend-to-disk nhưng không bảo toàn instance store. Không dùng hibernation thay cho application checkpoint: dữ liệu RAM không phải bản sao nhất quán của business state và việc resume vẫn phụ thuộc điều kiện capacity.

## 20. Cost model: đo chi phí cho kết quả hoàn thành

Giá mỗi instance-hour chỉ là một phần của chi phí. Một Spot workload có thể rẻ trên mỗi giờ nhưng đắt trên mỗi kết quả nếu interruption khiến phải chạy lại nhiều lần.

Đánh giá:

- Compute cost của Spot và On-Demand baseline.
- Chi phí replacement capacity tạm thời khi Capacity Rebalancing.
- EBS volumes còn lưu khi instance stopped.
- S3/EFS/FSx checkpoint và artifact storage.
- Data transfer, NAT và cross-AZ traffic.
- CloudWatch logs/metrics và EventBridge/SQS orchestration.
- Chi phí reprocessing sau interruption.
- Thời gian kỹ sư vận hành và xử lý failed jobs.

Một công thức thực dụng:

```text
Cost per successful unit =
  (Compute + Storage + Network + Orchestration + Rework)
  / Number of successfully completed units
```

Theo dõi cả throughput và completion time. Nếu interruption tăng khiến job phải chạy lại nhiều, hãy so sánh tổng chi phí với On-Demand.

Spot savings có thể lên đến 90% so với On-Demand nhưng không phải mức giảm cố định. Giá thay đổi theo pool và thời gian; hãy dùng AWS Cost and Usage Report/Data Exports và Cost Explorer để đo actual usage.

## 21. Theo dõi interruption và hiệu quả vận hành

Theo dõi các tín hiệu:

- Số rebalance recommendations.
- Số Spot interruption notices.
- Số instance bị interrupt theo instance type/AZ/pool.
- Thời gian từ rebalance recommendation đến interruption.
- Số job checkpoint thành công.
- Số job retry, failed và duplicate.
- Queue age và backlog.
- Thời gian drain.
- Tỷ lệ replacement instance launch thành công.
- Chi phí trên mỗi job hoàn tất.

Dùng EventBridge để route interruption events tới Lambda/SQS hoặc monitoring pipeline. Ghi instance ID, ASG, instance type, AZ, job ID và timestamp để phân tích pool nào thường bị ảnh hưởng.

Không chỉ theo dõi tổng số interruption. Một pool có interruption rate cao nhưng job rất ngắn có thể vẫn kinh tế; một interruption duy nhất trong job training dài không checkpoint có thể gây lãng phí lớn.

## 22. Security và vận hành an toàn

- Dùng IAM instance profile/IRSA/task role thay vì access key lưu trên instance.
- Bảo vệ checkpoint và artifact bằng KMS encryption.
- Giới hạn quyền đọc/ghi S3 prefix theo job hoặc service.
- Không lưu secret trong user data hoặc checkpoint.
- Dùng IMDSv2 và giới hạn hop limit theo kiến trúc.
- Bảo vệ EventBridge rule, SQS interruption queue và Lambda execution role.
- Ghi log interruption và shutdown nhưng không log dữ liệu nhạy cảm.
- Dùng AMI chuẩn hóa và patch thường xuyên.
- Giới hạn maximum capacity để tránh chi phí bùng nổ khi replacement.
- Cấu hình budget/alert cho Spot, On-Demand fallback và storage.

Interruption handler cần quyền tối thiểu. Ví dụ, handler chỉ cần cập nhật trạng thái instance/job và gọi checkpoint API thì không nên có quyền quản trị toàn bộ Auto Scaling group hoặc xóa bucket.

## 23. Anti-patterns thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng Spot cho database primary | Interruption làm gián đoạn dữ liệu và dịch vụ | Dùng managed database/On-Demand compute |
| Chỉ chọn một instance type/AZ | Pool cạn capacity thì không có phương án thay thế | Diversify instance types và AZ |
| Chỉ dựa vào hai phút notice | Notice best-effort, rebalance có thể đến muộn | Checkpoint định kỳ và tự phục hồi |
| Chờ đến interruption mới checkpoint | Không đủ thời gian lưu tiến độ | Checkpoint theo chu kỳ và theo rebalance signal |
| Lưu kết quả duy nhất trên instance store | Mất dữ liệu khi instance bị thu hồi | Dùng S3/EBS/EFS/FSx phù hợp |
| Worker không idempotent | Retry tạo side effect trùng | Idempotency key và transactional update |
| Retry không giới hạn | Poison message và chi phí tăng | Retry budget, DLQ và alarm |
| Dùng lowest-price cho fleet quan trọng | Chọn pool rẻ nhưng dễ bị interrupt | price-capacity-optimized |
| Lifecycle hook kéo dài quá hai phút | Spot vẫn bị terminate khi deadline đến | Hoàn tất cleanup nhanh, checkpoint trước |
| Dùng Spot cho toàn bộ capacity thiết yếu | Không có capacity khi nhiều pool thiếu | On-Demand baseline và admission control |
| Dùng hibernate trong ASG/ECS | Không tương thích với lifecycle quản lý | Dùng terminate/drain và replacement |
| Chỉ đo giá mỗi giờ | Không thấy chi phí rework và thời gian phục hồi | Đo cost per successful unit |

## 24. Runbook mẫu: Spot worker nhận interruption

### 24.1. Tình huống

Một Auto Scaling group chạy SQS workers bằng Spot Instance. Worker đang xử lý job ETL và nhận rebalance recommendation.

### 24.2. Trình tự xử lý

1. EventBridge nhận `EC2 Instance Rebalance Recommendation`.
2. Handler xác định instance ID, ASG, AZ và worker/job đang chạy.
3. Worker chuyển sang trạng thái DRAINING và ngừng nhận message mới.
4. Worker ghi checkpoint gồm job ID, partition, offset và output version.
5. Worker commit output tạm thời lên S3.
6. Worker cập nhật job lease/state trong database.
7. Auto Scaling Capacity Rebalancing launch replacement instance.
8. Replacement chạy health check và đăng ký vào worker fleet.
9. Worker cũ hoàn tất cleanup, flush logs và kết thúc.
10. Nếu interruption notice đến trước khi cleanup hoàn tất, worker dừng; message/lease hết hạn để worker mới tiếp tục.
11. Consumer mới đọc checkpoint, xác minh version và tiếp tục job.
12. CloudWatch ghi nhận completion, retry và interruption metrics.

### 24.3. Điều kiện dừng và escalation

- Không có checkpoint hợp lệ: đánh dấu job cần restart từ bước an toàn gần nhất.
- Checkpoint checksum/version không khớp: quarantine artifact và không tiếp tục từ dữ liệu lỗi.
- Replacement capacity không có: giữ job trong queue và giảm tốc độ producer nếu backlog tăng quá ngưỡng.
- DLQ tăng: dừng redrive tự động, điều tra poison message.
- Chi phí On-Demand vượt budget: giảm admission rate hoặc giới hạn fallback theo policy.

## 25. Kiểm thử interruption bằng AWS Fault Injection Service

AWS cung cấp khả năng initiate Spot interruption để kiểm tra ứng dụng. Bài thử có thể tạo rebalance recommendation, phát interruption notice rồi interrupt instance sau khoảng hai phút theo behavior được chọn.

Quy trình test:

1. Dùng môi trường staging hoặc account lab.
2. Chọn một Spot Instance không chứa dữ liệu duy nhất.
3. Bảo đảm có worker/instance thay thế hoặc queue giữ công việc.
4. Bật checkpoint và interruption handler.
5. Dùng FIS/EC2 Spot interruption test theo tài liệu AWS.
6. Quan sát EventBridge event và IMDSv2 metadata.
7. Xác minh worker ngừng nhận việc mới.
8. Kiểm tra checkpoint và log đã lưu.
9. Xác minh job được worker khác tiếp tục.
10. Kiểm tra duplicate side effect và DLQ.
11. Đo thời gian drain và thời gian hoàn tất job.
12. So sánh kết quả với RTO và cost target.

Không thử interruption trên node database hoặc workload production không có kế hoạch rollback. Cần có stop condition và người chịu trách nhiệm quan sát.

## 26. AWS CLI: kiểm tra và cấu hình Spot Auto Scaling

### 26.1. Bật Capacity Rebalancing

```bash
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name batch-spot-asg \
  --capacity-rebalance \
  --region ap-southeast-1
```

### 26.2. Xem cấu hình Auto Scaling group

```bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names batch-spot-asg \
  --region ap-southeast-1 \
  --query "AutoScalingGroups[].{Desired:DesiredCapacity,Min:MinSize,Max:MaxSize,CapacityRebalance:CapacityRebalance,AZs:AvailabilityZones,Instances:Instances[].{Id:InstanceId,AZ:AvailabilityZone,Lifecycle:LifecycleState,Health:HealthStatus}}"
```

### 26.3. Xem Spot interruption history qua request status

```bash
aws ec2 describe-spot-instance-requests \
  --filters Name=state,Values=active,closed,failed \
  --region ap-southeast-1 \
  --query "SpotInstanceRequests[].{RequestId:SpotInstanceRequestId,InstanceId:InstanceId,State:State.Code,Status:Status.Code,Message:Status.Message,Type:LaunchSpecification.InstanceType}"
```

Dùng request status và CloudTrail/CloudWatch để điều tra nguyên nhân. Không dùng danh sách request state làm metric duy nhất cho interruption rate.

### 26.4. Xem Spot price history

```bash
aws ec2 describe-spot-price-history \
  --instance-types m7i.large m7a.large c7i.large \
  --product-descriptions "Linux/UNIX" \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --region ap-southeast-1
```

Price history giúp phân tích chi phí quá khứ. Nó không dự báo chắc chắn capacity hoặc interruption tương lai.

## 27. Bài thực hành: xây dựng worker chịu interruption

### 27.1. Mục tiêu

Tạo một worker fleet có Spot capacity, xử lý job từ SQS và tiếp tục công việc sau khi instance bị interrupt.

### 27.2. Điều kiện chuẩn bị

- AWS account lab.
- Một SQS queue và DLQ.
- Một S3 bucket để lưu checkpoint/output.
- Một EC2 Auto Scaling group có nhiều instance types và ít nhất hai AZ.
- Một launch template và IAM instance profile.
- Một EventBridge rule cho rebalance recommendation/interruption warning.
- CloudWatch logs và alarms.
- Job worker có thể chia thành nhiều partition.

### 27.3. Các bước

1. Chọn job có thể chia thành các partition độc lập.
2. Thiết kế checkpoint gồm job ID, partition ID, offset và version.
3. Lưu checkpoint vào S3 hoặc database có conditional write.
4. Làm consumer idempotent theo job ID/partition/version.
5. Tạo Spot Auto Scaling group có nhiều instance types/AZ.
6. Chọn `price-capacity-optimized`.
7. Bật Capacity Rebalancing.
8. Cấu hình worker poll IMDSv2 và EventBridge handler.
9. Khi nhận rebalance recommendation, worker ngừng nhận job mới.
10. Tạo checkpoint và commit output.
11. Kiểm thử interruption trong lab bằng FIS hoặc EC2 Spot interruption test.
12. Xác minh instance cũ bị thay thế và job tiếp tục trên worker mới.
13. Gửi duplicate job để kiểm tra idempotency.
14. Gửi payload lỗi để kiểm tra DLQ.
15. Đo interruption count, job retry, completion time và cost per successful unit.

### 27.4. Tiêu chí hoàn thành

- Có nhiều Spot capacity pools để lựa chọn.
- Capacity Rebalancing được bật.
- Worker nhận được tín hiệu interruption hoặc tự phục hồi khi không nhận được tín hiệu.
- Worker ngừng nhận việc mới và lưu checkpoint.
- Replacement worker tiếp tục job từ checkpoint hợp lệ.
- Duplicate execution không tạo side effect trùng.
- Poison message được chuyển DLQ.
- Dashboard thể hiện interruption, retry, backlog và completion.
- Cost per successful unit được tính và so sánh với On-Demand.

## 28. Câu hỏi tự kiểm tra

### Câu 1

Spot Instance là gì?

**Đáp án:** Compute capacity EC2 chưa được sử dụng, có giá thấp hơn On-Demand nhưng có thể bị AWS thu hồi khi cần capacity.

### Câu 2

Spot capacity pool được xác định bởi yếu tố nào?

**Đáp án:** Instance type và Availability Zone. Mỗi tổ hợp là một pool riêng.

### Câu 3

Rebalance recommendation khác interruption notice thế nào?

**Đáp án:** Rebalance recommendation báo instance có nguy cơ interruption cao hơn và có thể đến sớm; interruption notice báo instance sắp bị stop/terminate, thường khoảng hai phút trước.

### Câu 4

Có thể luôn dựa vào hai phút interruption notice không?

**Đáp án:** Không. Notice được phát best-effort; rebalance signal có thể đến muộn hoặc cùng lúc. Workload phải checkpoint định kỳ và tự phục hồi.

### Câu 5

Vì sao price-capacity-optimized thường phù hợp hơn lowest-price?

**Đáp án:** Strategy này cân bằng giá với khả năng capacity và chọn pool ít có nguy cơ interruption hơn trong các pool có giá tốt. lowest-price chỉ ưu tiên giá và có thể chọn pool dễ bị thu hồi.

### Câu 6

Capacity Rebalancing trong Auto Scaling làm gì?

**Đáp án:** Khi Spot Instance nhận rebalance recommendation, Auto Scaling cố gắng launch replacement trước, chờ health check rồi mới terminate instance cũ.

### Câu 7

Lifecycle hook có thể kéo dài thời gian Spot giữ instance vô hạn không?

**Đáp án:** Không. Spot có hard interruption window; instance có thể bị terminate khi hết khoảng cảnh báo dù lifecycle hook chưa hoàn tất.

### Câu 8

Vì sao worker cần idempotent?

**Đáp án:** Worker có thể bị interrupt sau khi commit side effect nhưng trước khi acknowledge message. Message được giao lại không được tạo tác động nghiệp vụ trùng.

### Câu 9

Vì sao không nên lưu checkpoint duy nhất trên instance store?

**Đáp án:** Instance store mất dữ liệu khi instance bị stop/terminate. Checkpoint phải nằm trên storage bền vững hoặc database dùng chung.

### Câu 10

EKS Spot Pod có luôn nhận đủ hai phút graceful shutdown không?

**Đáp án:** Không. EKS drain best-effort, có thể trễ khi nhiều node bị thu hồi hoặc node có nhiều Pod. Workload nên có termination grace period ngắn và checkpoint.

### Câu 11

AWS Batch khuyến nghị gì với job chạy trên Spot?

**Đáp án:** Chia hoặc checkpoint job thành phần ngắn, khoảng 30 phút hoặc ít hơn, và cấu hình automated retries phù hợp.

### Câu 12

Nên đo hiệu quả Spot bằng giá mỗi instance-hour hay cost per successful unit?

**Đáp án:** Cost per successful unit phản ánh compute, storage, network, orchestration và công việc phải chạy lại, nên hữu ích hơn để đánh giá hiệu quả thực tế.

## 29. Checklist production

### Workload fit

- [ ] Workload có thể retry, checkpoint hoặc phân phối lại.
- [ ] Không dùng Spot cho database/stateful primary hoặc control plane thiết yếu.
- [ ] Có On-Demand baseline cho capacity không thể gián đoạn.
- [ ] Đã tính chi phí rework và thời gian phục hồi.

### Capacity strategy

- [ ] Có nhiều instance types tương thích.
- [ ] Có nhiều AZ/pools phù hợp.
- [ ] Allocation strategy là price-capacity-optimized hoặc strategy được giải thích rõ.
- [ ] Không phụ thuộc một pool duy nhất.
- [ ] Capacity Rebalancing đã bật khi dùng Auto Scaling.
- [ ] Có headroom cho replacement và giới hạn maximum capacity.

### Interruption handling

- [ ] Có rebalance recommendation handler.
- [ ] Có Spot interruption handler qua EventBridge và/hoặc IMDSv2.
- [ ] Hiểu notice là best-effort và có thể đến muộn.
- [ ] Worker ngừng nhận việc mới khi drain.
- [ ] Có checkpoint định kỳ.
- [ ] Shutdown hoàn tất nhanh hơn deadline.
- [ ] Không phụ thuộc lifecycle hook để giữ instance sau hard deadline.

### Application reliability

- [ ] Consumer idempotent.
- [ ] Message chỉ được acknowledge sau khi commit.
- [ ] Có retry budget và DLQ.
- [ ] Checkpoint lưu trên storage bền vững.
- [ ] Có version/lease để tránh worker cũ ghi đè checkpoint mới.
- [ ] Có xử lý duplicate và out-of-order nếu cần.

### Service integration

- [ ] ECS managed draining/Fargate Spot được cấu hình đúng.
- [ ] EKS Spot node group có nhiều instance types và Pod disruption design.
- [ ] Karpenter interruption queue có IAM/resource permissions phù hợp.
- [ ] AWS Batch job có retry/checkpoint.
- [ ] Không đặt state duy nhất trên Spot worker.

### Monitoring và cost

- [ ] Có metric interruption/rebalance.
- [ ] Có queue age/backlog và DLQ alarm.
- [ ] Có job retry, checkpoint failure và completion metrics.
- [ ] Có cost per successful unit.
- [ ] Có budget alert và giới hạn On-Demand fallback.
- [ ] Đã kiểm thử interruption trong môi trường lab/staging.

## 30. Tài liệu tham khảo chính thức

### EC2 Spot và interruption

- [Amazon EC2 Spot best practices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html)
- [Spot Instance interruptions](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-interruptions.html)
- [Spot Instance interruption notices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html)
- [EC2 instance rebalance recommendations](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/rebalance-recommendations.html)
- [Behavior of Spot Instance interruptions](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/interruption-behavior.html)
- [Billing for interrupted Spot Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/billing-for-interrupted-spot-instances.html)
- [Spot placement score](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-sps-works.html)

### Auto Scaling và allocation

- [Capacity Rebalancing in Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-capacity-rebalancing.html)
- [Spot allocation strategies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/allocation-strategies.html)
- [EC2 Fleet and Spot Fleet allocation strategies](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-fleet-allocation-strategy.html)
- [Gracefully handle instance termination](https://docs.aws.amazon.com/autoscaling/ec2/userguide/gracefully-handle-instance-termination.html)
- [Mixed instances policy](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-mixed-instances-groups.html)

### ECS, EKS và Batch

- [ECS managed instance draining](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instance-draining.html)
- [ECS Fargate capacity providers and Spot notices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-capacity-providers.html)
- [EKS managed node groups](https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html)
- [EKS Karpenter best practices](https://docs.aws.amazon.com/eks/latest/best-practices/karpenter.html)
- [AWS Batch Spot best practices](https://docs.aws.amazon.com/batch/latest/userguide/bestpractice6.html)
- [AWS Batch automated job retries](https://docs.aws.amazon.com/batch/latest/userguide/job_retries.html)

### Kiểm thử và vận hành

- [Initiate a Spot Instance interruption](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/initiate-a-spot-instance-interruption.html)
- [AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html)
- [Amazon CloudWatch User Guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html)

