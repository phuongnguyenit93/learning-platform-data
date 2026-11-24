# Phân tích khác biệt về vòng đời, hạn mức và phạm vi áp dụng SLA

Chọn dịch vụ máy ảo giữa các nhà cung cấp cloud không chỉ là so sánh số vCPU, memory hoặc giá theo giờ. Một workload còn chịu ảnh hưởng bởi vòng đời VM, cách lưu dữ liệu khi stop/delete, thời điểm host maintenance, cơ chế Spot/preemptible, quota theo account/project/region và điều kiện để được áp dụng Service Level Agreement (SLA). Hai VM có cấu hình gần giống nhau vẫn có thể tạo ra hành vi vận hành khác nhau khi scale, thay host hoặc phục hồi sau sự cố.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, bài học này so sánh cách tiếp cận của Amazon EC2, Azure Virtual Machines và Google Compute Engine. Trọng tâm là phân tích vòng đời, hạn mức và phạm vi SLA; các chi tiết được trình bày theo nguyên tắc và cần đối chiếu với điều khoản hiện hành của region, SKU, operating system và cấu hình triển khai trước khi cam kết với khách hàng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả các trạng thái chính trong vòng đời VM và ý nghĩa billing/data của từng trạng thái.
- So sánh stop, deallocate, reboot, redeploy, resize, delete và host maintenance.
- Phân biệt persistent disk với local/temporary/ephemeral disk.
- Phân tích khác biệt giữa On-Demand, Reserved/committed capacity và Spot/preemptible VM.
- Phân biệt quota có thể yêu cầu tăng với giới hạn hệ thống hoặc capacity thực tế.
- Xác định quota scope theo account, subscription, project, region, zone và VM family.
- Lập capacity request có tính cả rolling deployment, failover và headroom.
- Giải thích SLA của nhà cung cấp bao phủ thành phần nào, điều kiện nào và loại trừ nào.
- Phân biệt provider SLA, application SLO và SLA end-to-end với người dùng.
- Tính availability của các tầng nối tiếp và đánh giá lợi ích của redundancy.
- Xây dựng checklist đánh giá compute provider cho một workload cụ thể.

## 1. Phạm vi so sánh và thuật ngữ

Ba dịch vụ được đối chiếu:

| Nhà cung cấp | Dịch vụ VM | Cơ chế quản lý nhóm VM thường gặp |
|---|---|---|
| Amazon Web Services | Amazon EC2 | EC2 Auto Scaling groups |
| Microsoft Azure | Azure Virtual Machines | Virtual Machine Scale Sets |
| Google Cloud | Compute Engine | Managed Instance Groups |

Các dịch vụ đều cung cấp VM theo nhu cầu, image/template, disk, network, identity, monitoring và cơ chế tự động mở rộng. Tên trạng thái, thao tác control plane, quota và điều khoản SLA không hoàn toàn giống nhau.

### 1.1. Vòng đời VM

Vòng đời là tập hợp trạng thái và thao tác từ lúc yêu cầu VM, cấp phát host, boot guest OS, vận hành, dừng, khởi động lại, thay đổi cấu hình đến khi xóa. Vòng đời có cả hai mặt:

- **Control plane:** trạng thái mà API/portal của nhà cung cấp báo cáo.
- **Guest/workload:** trạng thái OS, process, connection, file system và ứng dụng bên trong VM.

VM có thể ở trạng thái Running trong control plane nhưng ứng dụng không healthy. Ngược lại, VM có thể đang reboot hoặc deallocate trong control plane dù trước đó ứng dụng đã nhận shutdown signal.

### 1.2. Quota, limit và capacity

- **Quota:** ngân sách tài nguyên được cấp cho một phạm vi, ví dụ số vCPU hoặc GPU có thể sử dụng trong region.
- **Service limit/system limit:** giới hạn kỹ thuật hoặc chính sách của dịch vụ; có thể không tăng được bằng yêu cầu quota thông thường.
- **Available capacity:** tài nguyên vật lý/SKU thực sự có thể cấp tại zone/region và thời điểm yêu cầu.
- **Reservation:** cơ chế giữ trước capacity hoặc cam kết sử dụng/chi phí; semantics phụ thuộc loại reservation của nhà cung cấp.

Quota còn dư không bảo đảm có host/SKU phù hợp tại zone mong muốn. Ngược lại, region có capacity vật lý nhưng request vẫn có thể thất bại nếu quota, policy hoặc subnet IP đã hết.

### 1.3. SLA, SLO và SLI

- **SLI (Service Level Indicator):** chỉ số đo được, như tỷ lệ request thành công hoặc thời gian VM sẵn sàng.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho SLI trong một cửa sổ thời gian.
- **SLA (Service Level Agreement):** cam kết hợp đồng về mức dịch vụ, phạm vi, cách đo và biện pháp khắc phục/service credit nếu không đạt điều kiện.

Provider SLA không tự động trở thành SLA của ứng dụng do khách hàng xây dựng trên VM.

## 2. Vòng đời VM nhìn từ vận hành

Một vòng đời phổ biến có các giai đoạn:

1. **Request/provision:** chọn image, machine type, disk, subnet, identity, zone và quota.
2. **Boot/initialization:** host cấp phát, hypervisor khởi tạo VM, guest OS boot và bootstrap chạy.
3. **Running:** VM có thể nhận workload; health check và application readiness vẫn cần được xác minh.
4. **Maintenance/recovery:** provider có thể thông báo maintenance, live migrate, reboot, redeploy hoặc yêu cầu thay instance tùy dịch vụ/SKU.
5. **Stop/suspend:** dừng compute nhưng có thể giữ disk và một số resource khác.
6. **Start/resume:** cấp lại compute hoặc khôi phục VM từ trạng thái đã lưu nếu tính năng hỗ trợ.
7. **Delete/terminate:** xóa VM; disk, IP, snapshot, backup và NIC có thể được giữ hoặc xóa theo policy riêng.

Không coi một thao tác có tên gần giống nhau là tương đương giữa các cloud. Đặc biệt cần phân biệt stop guest OS, stop VM nhưng vẫn giữ host allocation, deallocate/release compute, suspend có lưu memory và delete instance.

## 3. So sánh trạng thái và thao tác vòng đời

### 3.1. Amazon EC2

EC2 thể hiện các trạng thái phổ biến như pending, running, stopping, stopped, shutting-down và terminated.

- Khi launch, instance đi qua pending rồi tới running nếu cấp phát và boot thành công.
- Reboot khởi động lại guest OS; instance vẫn là cùng instance identity.
- Stop áp dụng cho loại instance hỗ trợ stop, thường là EBS-backed. Compute capacity được giải phóng; EBS volume được giữ theo cấu hình.
- Start từ stopped có thể cấp host mới. Public IPv4 tự động có thể thay đổi; Elastic IP hoặc cấu hình network tương ứng dùng để giữ địa chỉ ổn định.
- Instance store là storage tạm gắn với host; dữ liệu trên đó mất khi stop/terminate hoặc khi host bị thay theo semantics của loại instance.
- Terminate kết thúc vòng đời instance. EBS volume có thể tự xóa hoặc giữ lại tùy delete-on-termination; snapshot và các resource liên quan cần quản lý riêng.

Hibernation có thể lưu nội dung RAM vào EBS để resume với điều kiện instance, OS, volume và cấu hình hỗ trợ. Hibernation không áp dụng cho mọi instance type hoặc mọi workload.

### 3.2. Azure Virtual Machines

Azure phân biệt các trạng thái cấp phát như starting/running/stopping/stopped/deallocating/deallocated và deleting/deleted trong các góc nhìn quản trị.

- Stop từ trong guest OS có thể để VM ở trạng thái stopped nhưng vẫn giữ allocation trên host; compute billing có thể tiếp tục.
- Stop/deallocate từ control plane giải phóng compute allocation. Disk và một số resource liên quan vẫn tồn tại và có thể tiếp tục phát sinh phí.
- Start từ deallocated cần cấp phát compute mới; việc cấp phát có thể bị ảnh hưởng bởi quota và capacity của zone/region.
- OS disk và data disk managed thường tồn tại độc lập với VM nếu không chọn hành vi xóa cùng VM.
- Temporary disk là storage tạm; dữ liệu có thể mất khi VM redeploy, host maintenance hoặc thao tác lifecycle nhất định.
- Delete VM không đồng nghĩa mọi disk, NIC, public IP và snapshot đều bị xóa; hành vi phụ thuộc delete option và loại resource.

Azure có các tùy chọn ephemeral OS disk trên SKU phù hợp. Vì ephemeral disk gắn với local storage của host, cần xác minh rõ behavior khi redeploy, reimage, deallocate và host event trước khi đặt dữ liệu quan trọng ở đó.

### 3.3. Google Compute Engine

Compute Engine có các trạng thái như PROVISIONING, STAGING, RUNNING, STOPPING, SUSPENDING, SUSPENDED và TERMINATED.

- Khi tạo VM, tài nguyên được provision và staging trước khi VM vào RUNNING.
- Stop đưa VM tới TERMINATED; Persistent Disk thường vẫn tồn tại và tiếp tục có chi phí lưu trữ.
- Suspend, nếu được hỗ trợ, lưu trạng thái memory để resume; không phải mọi machine type hoặc thiết bị gắn kèm đều hỗ trợ mọi trường hợp.
- Local SSD là storage gắn với host và có semantics về độ bền khác Persistent Disk; dữ liệu có thể không tồn tại qua stop/terminate hoặc host event tùy cấu hình và loại VM.
- Khi delete VM, Persistent Disk có thể được giữ hoặc xóa theo auto-delete setting; IP ephemeral và resource phụ trợ cũng có vòng đời riêng.
- Maintenance có thể dùng live migration với machine type hỗ trợ; một số cấu hình cần terminate/restart hoặc xử lý theo maintenance policy.

### 3.4. Bảng đối chiếu thao tác

| Thao tác | Amazon EC2 | Azure VM | Google Compute Engine |
|---|---|---|---|
| Reboot | Khởi động lại guest OS trên instance | Restart guest/VM theo thao tác được chọn | Reset/restart VM theo thao tác được chọn |
| Stop/deallocate | Stop giải phóng compute; EBS giữ theo cấu hình | Cần phân biệt stopped với deallocated; deallocated giải phóng compute | Stop đưa VM về TERMINATED; persistent disk thường còn |
| Suspend/hibernate | Hibernation lưu RAM vào EBS nếu hỗ trợ | Suspend/hibernate tùy SKU và tính năng được cung cấp | Suspend lưu memory state nếu VM hỗ trợ |
| Local temporary storage | Instance store gắn với host | Temporary disk gắn với host | Local SSD gắn với host |
| Disk sau khi xóa VM | EBS phụ thuộc delete-on-termination | Managed disks phụ thuộc delete option | Persistent Disk phụ thuộc auto-delete |
| Host maintenance | Có thể có retirement/replacement; behavior tùy instance | Có thể live migrate/redeploy tùy VM/SKU | Live migration hoặc maintenance action tùy machine type |

Bảng tóm tắt khái niệm, không thay thế tài liệu lifecycle theo loại VM. Trước khi dùng stop, suspend hoặc delete trong automation, cần kiểm tra chính xác trạng thái cuối, billing, disk retention, IP và data loss.

## 4. Persistent disk và local/ephemeral disk

Một trong những khác biệt có ảnh hưởng lớn nhất là nơi dữ liệu được lưu và dữ liệu tồn tại qua thao tác nào.

### 4.1. Persistent storage

Persistent block disk được quản lý tách khỏi vòng đời compute ở mức độ nhất định. VM có thể stop hoặc thay thế trong khi disk vẫn tồn tại, tùy delete policy. Persistent disk phù hợp với OS/data disk cần giữ lại, nhưng vẫn cần backup, snapshot, replication và restore test.

### 4.2. Local/temporary storage

Local/temporary disk thường có latency hoặc throughput tốt và phù hợp scratch data, cache tái tạo, temporary file hoặc buffer. Tuy nhiên, dữ liệu có thể mất khi:

- VM bị stop/deallocate.
- Host bị thay hoặc gặp maintenance.
- Instance bị terminate/delete.
- VM được redeploy/reimage.
- Provider thực hiện recovery theo loại machine.

Không đặt database primary, session duy nhất hoặc file người dùng duy nhất trên local ephemeral storage nếu chưa có replication và recovery protocol.

### 4.3. Quy tắc thiết kế

| Loại dữ liệu | Vị trí khuyến nghị | Lý do |
|---|---|---|
| OS image và package | Image/template hoặc OS disk | Có thể tái tạo từ image chuẩn |
| Database data | Managed database hoặc replicated persistent disk | Cần durability, backup và recovery |
| User upload/report | Object storage hoặc shared file service | Truy cập được từ nhiều VM |
| Session/cache | Shared cache hoặc store có TTL | Không phụ thuộc một instance |
| Build scratch/temp file | Local temporary disk | Có thể tạo lại sau khi mất |
| Queue/event | Managed queue/stream hoặc durable broker | Tách producer/consumer và hỗ trợ retry |

## 5. Maintenance, resize và thay đổi host

VM là workload chạy trên hạ tầng vật lý do provider quản lý. Provider cần vá hypervisor, thay host, cập nhật firmware và duy trì capacity. Cách xử lý maintenance ảnh hưởng downtime và khả năng tự phục hồi của ứng dụng.

### 5.1. Live migration và restart-based maintenance

Live migration chuyển VM đang chạy sang host khác với gián đoạn tối thiểu nếu machine type và workload hỗ trợ. Một số host event vẫn cần reboot, stop/start hoặc redeploy. Không nên giả định mọi VM đều live migrate được.

Thiết kế ứng dụng cần chịu được:

- Guest reboot bất ngờ.
- Network connection reset.
- Clock/time drift nhỏ trong quá trình chuyển host.
- Storage/network path bị gián đoạn ngắn.
- VM bị retire và phải tạo instance thay thế.

### 5.2. Resize

Resize thay đổi CPU/memory hoặc machine family. Thao tác có thể yêu cầu stop/deallocate, không giữ nguyên host hoặc làm thay đổi NIC/NUMA/CPU feature. Kiểm tra:

- OS và driver có hỗ trợ shape mới không.
- Disk throughput/IOPS có thay đổi không.
- Network bandwidth và PPS limit.
- License/CPU topology và application tuning.
- Reservation/Spot availability cho shape mới.
- Downtime và rollback path.

### 5.3. Instance replacement

Với VM group, ưu tiên thay instance bằng template/image mới thay vì sửa từng VM. Rolling replacement cần giới hạn số instance unavailable, dùng health check và chờ readiness trước khi drain instance cũ.

Nếu workload có state local, cần replicate hoặc checkpoint trước khi terminate. Autoscaling group không tự bảo đảm dữ liệu local được chuyển sang VM mới.

## 6. Spot, preemptible và capacity interruptible

Các nhà cung cấp có sản phẩm compute giá thấp hơn cho phép thu hồi instance khi cần capacity:

- AWS EC2 Spot Instances.
- Azure Spot Virtual Machines.
- Google Cloud Spot VMs (trước đây có tên Preemptible VMs).

Điểm chung là mức sẵn sàng capacity không được bảo đảm như On-Demand; instance có thể bị thu hồi với thông báo/thời gian cảnh báo và behavior phụ thuộc provider.

### 6.1. Khác biệt cần đánh giá

| Tiêu chí | AWS Spot | Azure Spot VM | Google Cloud Spot VM |
|---|---|---|---|
| Capacity | Dựa trên capacity dư của EC2 | Dựa trên capacity dư của Azure | Dựa trên capacity dư của Compute Engine |
| Thu hồi | Có interruption notice theo semantics dịch vụ; stop/hibernate/terminate tùy cấu hình được hỗ trợ | Eviction; policy có thể deallocate hoặc delete | Có thể preempt/terminate; thời gian thông báo hạn chế |
| Giá | Thay đổi theo thị trường/offer và instance pool | Có giá Spot/maximum price policy theo sản phẩm | Giá Spot thay đổi theo loại tài nguyên và thời điểm |
| Phù hợp | Batch, stateless worker, CI, fault-tolerant fleet | Batch, scale set, stateless/interruptible workloads | Batch, HPC worker, stateless/interruptible workloads |
| Rủi ro | Capacity interruption và pool shortage | Eviction, quota/capacity theo region/SKU | Preemption và giới hạn availability |

Không dùng các mô tả này để suy ra một SLA chung cho Spot. Đọc điều khoản riêng của sản phẩm và cấu hình eviction hiện hành.

### 6.2. Workload phù hợp

- Batch có thể retry hoặc checkpoint.
- CI build/test có thể chạy lại.
- Queue worker stateless đọc job từ queue.
- Distributed compute có scheduler và task requeue.
- Render/transcode có checkpoint theo segment.

Không đặt database primary, license server không thể khởi động lại hoặc giao dịch không idempotent trên Spot nếu không có thiết kế dự phòng riêng.

### 6.3. Chuẩn bị interruption

1. Nhận interruption event qua metadata/notification channel mà provider hỗ trợ.
2. Ngừng nhận job mới.
3. Lưu checkpoint hoặc trả lease/message về queue.
4. Flush output theo commit protocol an toàn.
5. Đóng connection và kết thúc trước deadline nếu có thể.
6. Scheduler tạo replacement capacity hoặc requeue job.

Ứng dụng vẫn phải chịu được mất instance đột ngột; interruption notice không phải bảo đảm luôn đủ thời gian để hoàn tất công việc.

## 7. So sánh quota và hạn mức

Quota là một phần của capacity planning. Mỗi cloud có cách nhóm quota và giao diện yêu cầu tăng khác nhau.

### 7.1. AWS EC2 và Service Quotas

EC2 có quota theo nhiều dimension, bao gồm vCPU-based On-Demand quotas theo instance family/region, Spot-related quotas và giới hạn các resource khác. Một số quota được hiển thị trong Service Quotas và có thể yêu cầu tăng; một số giới hạn phụ thuộc loại resource hoặc policy.

Khi tính capacity, kiểm tra:

- On-Demand vCPU quota theo family/region.
- Spot vCPU quota và pool availability.
- GPU/accelerator quota.
- EBS volume, snapshot và throughput constraints.
- Elastic IP, ENI, security group và subnet IP capacity.
- Auto Scaling group desired/max và API rate.

Quota vCPU còn dư không bảo đảm instance type có capacity ở một Availability Zone cụ thể.

### 7.2. Azure quota và subscription limits

Azure quota thường gắn với subscription, region và VM family/series; ngoài quota tổng vCPU còn có các giới hạn cho resource liên quan. Việc tăng quota có thể cần request theo subscription/region và không đồng nghĩa provider bảo đảm có SKU tại zone.

Khi tính capacity, kiểm tra:

- Regional vCPU quota.
- Family-specific vCPU quota.
- Spot vCPU quota và eviction policy.
- GPU/accelerator family quota.
- Managed disk, snapshot, NIC và public IP limits.
- VM Scale Set maximum capacity và subnet address space.
- Azure Policy hoặc subscription-level restriction.

Quota có thể khác giữa subscription dù cùng tenant. Hãy kiểm tra đúng subscription đang triển khai.

### 7.3. Google Cloud quotas

Compute Engine có quota theo project, region và một số phạm vi global; có quota cho CPU, GPU, disk, IP, snapshots và các API/resource khác. Một số giới hạn là quota có thể yêu cầu tăng, một số là system limit hoặc phụ thuộc capacity.

Khi tính capacity, kiểm tra:

- Regional CPU quota và machine family constraints.
- GPU/accelerator quota.
- Spot capacity/availability.
- Persistent Disk capacity/performance limits.
- External IP, network, forwarding rule và subnet IP capacity.
- Managed Instance Group limits và API rate.
- Project-level policy và organization constraints.

Một quota global hoặc regional không bảo đảm capacity ở zone cụ thể. Kiểm tra cả zone availability và machine type availability.

### 7.4. Ma trận quota theo scope

| Dimension | AWS EC2 | Azure VM | Google Compute Engine |
|---|---|---|---|
| Account scope | Account và region/service quota | Subscription và region | Project và phạm vi quota |
| Compute CPU | vCPU quota theo family/market | vCPU quota theo region/family | CPU quota theo region/project và loại |
| Accelerator | GPU/accelerator quota | GPU VM family quota | GPU quota theo region/project |
| Network | ENI, IP, security group, subnet | NIC, public IP, subnet | IP, forwarding rule, network limits |
| Storage | EBS volumes/snapshots/throughput | Managed disks/snapshots | Persistent Disk/snapshot quotas |
| Group scaling | Auto Scaling group và API constraints | VM Scale Set và API constraints | Managed Instance Group và API constraints |

Tên và cách hiển thị quota thay đổi theo dịch vụ và thời điểm. Trước deployment, truy vấn quota trong đúng account/subscription/project và region.

## 8. Quota không đồng nghĩa capacity được bảo đảm

Đây là khác biệt quan trọng khi lập kế hoạch cho peak hoặc disaster recovery:

- Quota là quyền được phép yêu cầu sử dụng đến một ngưỡng.
- Capacity là tài nguyên thực tế có thể cấp tại thời điểm và vị trí yêu cầu.
- Reservation/capacity reservation có thể giữ trước một loại capacity theo điều khoản cụ thể.
- Autoscaling chỉ tự động gọi API tạo instance; nó không vượt quota hoặc tạo thêm host vật lý khi provider không có capacity.

Ví dụ, project có quota 200 vCPU nhưng zone đang hết capacity cho một machine family cụ thể. Request VM vẫn có thể thất bại. Ngược lại, zone còn host nhưng quota subscription chỉ cho phép 120 vCPU thì request vượt mức cũng thất bại.

### 8.1. Quota headroom

Khi tính quota, cộng cả:

- Capacity đang chạy.
- Rolling deployment surge.
- Replacement khi VM unhealthy.
- Failover workload từ zone khác.
- Autoscaling peak và batch overlap.
- Temporary VM cho migration hoặc restore.
- VM/worker của team khác dùng chung quota.

Ví dụ một workload chạy 40 VM, mỗi VM 2 vCPU, cần thêm 25% surge khi rolling update:

~~~text
Baseline = 40 × 2 = 80 vCPU
Surge    = 80 × 25% = 20 vCPU
Peak     = 80 + 20 = 100 vCPU
~~~

Nếu failover còn cần thêm 20 vCPU ở region/zone khác, quota/capacity plan phải tính riêng cho failure scenario đó. Không giả định surge và failover không bao giờ xảy ra cùng lúc nếu quy trình vận hành cho phép chúng chồng lấp.

### 8.2. Quy trình trước khi mở rộng

1. Tính desired capacity theo tải và SLO.
2. Tính vCPU/GPU/disk/network/IP theo từng region/zone/family.
3. Kiểm tra quota hiện tại và quota đã sử dụng bởi workload khác.
4. Kiểm tra max size của VM group và autoscaling policy.
5. Kiểm tra zone/SKU availability và capacity reservation nếu cần.
6. Gửi quota increase sớm, không chờ tới thời điểm peak.
7. Thử tạo một số instance đại diện trong từng zone.
8. Đặt alert khi quota usage gần ngưỡng và theo dõi failed allocation.

## 9. So sánh phạm vi SLA của compute service

SLA là cam kết hợp đồng theo dịch vụ và cấu hình đủ điều kiện. Không thể kết luận một cloud “có SLA 99.x%” rồi áp dụng con số đó cho mọi VM, disk, network và ứng dụng.

### 9.1. AWS EC2

EC2 có Service Level Agreement riêng với cách định nghĩa monthly uptime percentage, điều kiện áp dụng và service credit. Cần đọc chính xác phạm vi instance/region, topology triển khai, exclusions, cách tính downtime và thời hạn gửi claim trong AWS Service Terms.

EC2 SLA không tự động bao phủ mọi thành phần trong kiến trúc. EBS, load balancing, network và các managed service khác có điều khoản riêng. Một EC2 instance khỏe không bảo đảm ứng dụng trả request thành công nếu EBS, database, DNS hoặc application process lỗi.

### 9.2. Azure Virtual Machines

Azure Virtual Machines SLA gắn với cấu hình deployment và mức availability được thiết kế, ví dụ single instance, availability set hoặc availability zone khi SKU/region hỗ trợ. Một số cam kết có điều kiện về disk type, instance count, placement và cấu hình.

Cần kiểm tra:

- VM có được phân bố trong availability set/zone đúng cách không.
- Disk và network dependency có SLA riêng không.
- SKU/region/OS có nằm trong phạm vi cam kết không.
- Maintenance, customer action và các exclusions được định nghĩa thế nào.
- Điều kiện service credit và quy trình claim.

### 9.3. Google Compute Engine

Compute Engine có SLA theo dịch vụ và cấu hình VM/zone deployment. Phạm vi có thể phân biệt instance đơn, nhiều instance trong một zone hoặc triển khai nhiều zone tùy điều khoản. Persistent Disk, load balancing, networking và các managed service có cam kết riêng.

Cần xác minh machine type, region/zone, disk, network dependency và deployment topology có nằm trong phạm vi SLA được viện dẫn hay không. Không suy ra SLA của toàn ứng dụng từ trạng thái RUNNING của VM.

### 9.4. Đối chiếu phạm vi cam kết

| Câu hỏi | AWS EC2 | Azure VM | Google Compute Engine |
|---|---|---|---|
| SLA chính | EC2 service SLA | Virtual Machines SLA | Compute Engine SLA |
| Phạm vi phụ thuộc | Region, instance eligibility, topology và điều khoản | VM deployment model, zone/set, SKU và điều khoản | Instance/zone topology, machine type và điều khoản |
| Storage | EBS có điều khoản riêng | Managed Disks có điều khoản riêng | Persistent Disk có điều khoản riêng |
| Load balancing/network | Xem SLA riêng của từng dịch vụ | Xem SLA riêng của từng dịch vụ | Xem SLA riêng của từng dịch vụ |
| Bồi hoàn | Service credit theo AWS terms và claim process | Service credit theo Microsoft SLA terms | Service credit theo Google Cloud SLA terms |
| Điều cần tránh | Dùng EC2 SLA như SLA end-to-end | Dùng VM SLA cho mọi dependency | Dùng Compute Engine SLA cho toàn bộ ứng dụng |

Các điều khoản và ngưỡng số có thể thay đổi. Trước khi ký hợp đồng hoặc công bố availability target, lưu bản SLA có hiệu lực tại thời điểm mua và xác minh đúng SKU/region.

## 10. SLA bao phủ gì và thường loại trừ gì?

Một SLA cần đọc theo các mục:

1. **Covered service:** dịch vụ/resource nào được cam kết.
2. **Eligibility:** region, SKU, OS, disk, topology và cấu hình tối thiểu.
3. **Measurement:** cách tính uptime, measurement window và nguồn dữ liệu.
4. **Exclusions:** sự kiện nào không tính vào downtime được bồi hoàn.
5. **Remedy:** service credit, mức credit và giới hạn.
6. **Claim process:** thời hạn, bằng chứng, resource ID và kênh gửi claim.

Các exclusions thường có thể liên quan đến:

- Lỗi do cấu hình hoặc thao tác của khách hàng.
- Guest OS, application code hoặc phần mềm bên thứ ba.
- Credential, firewall, DNS hoặc network do khách hàng quản lý.
- Dịch vụ beta/preview hoặc loại instance không đủ điều kiện.
- Maintenance hoặc sự kiện được nêu rõ trong điều khoản.
- Force majeure, abuse hoặc điều kiện loại trừ khác theo hợp đồng.

Danh sách này chỉ giúp định hướng đọc hợp đồng; không thay thế wording cụ thể trong SLA của provider.

### 10.1. Service credit không phải bồi thường toàn bộ thiệt hại

Service credit thường là biện pháp khắc phục hợp đồng theo công thức và giới hạn đã công bố. Nó không nhất thiết hoàn lại toàn bộ chi phí kinh doanh bị mất, chi phí nhân sự hoặc thiệt hại gián tiếp. Đội pháp lý/procurement cần xem điều khoản liability và credit riêng.

### 10.2. SLA khác với support response time

SLA về availability không đồng nghĩa với thời gian support phản hồi ticket. Support plan có thể quy định response target theo severity, trong khi service SLA quy định uptime và credit. Hai cam kết cần được theo dõi riêng.

## 11. Từ provider SLA đến application SLO

Ứng dụng nhiều tầng có thể bị lỗi dù từng VM vẫn RUNNING. Cần đặt SLO end-to-end dựa trên request thành công và latency người dùng quan sát.

### 11.1. Các tầng nối tiếp

Nếu request cần đi qua edge, load balancer, web, application và database theo chuỗi, availability của toàn luồng phụ thuộc tất cả thành phần. Với giả định các failure độc lập:

\[
A_{end-to-end}=\prod_{i=1}^{n} A_i
\]

Ví dụ ba thành phần nối tiếp, mỗi thành phần có availability 99,9%:

~~~text
A = 0,999 × 0,999 × 0,999
  ≈ 0,997003
  ≈ 99,7003%
~~~

Trong thực tế, lỗi không hoàn toàn độc lập; shared network, identity, DNS hoặc control plane có thể tạo correlated failure. Công thức chỉ là mô hình sơ bộ để thấy rằng nhiều dependency nối tiếp có thể làm availability end-to-end thấp hơn từng thành phần.

### 11.2. Redundancy và failure independence

Với hai instance độc lập, mỗi instance availability A, và load balancer có thể chuyển traffic sang instance còn lại, availability của nhóm có thể ước tính:

\[
A_{group}=1-(1-A)^2
\]

Ví dụ mỗi instance availability 99,9%, mô hình độc lập cho nhóm hai instance:

~~~text
A_group = 1 - (1 - 0,999)^2
        = 0,999999
        = 99,9999%
~~~

Con số này chỉ đúng khi failure độc lập và failover thực sự hoạt động. Nếu cả hai VM nằm cùng host/zone hoặc dùng chung database bị lỗi, redundancy VM không mang lại mức availability đó.

### 11.3. Error budget

Với SLO 99,9% trong một tháng 30 ngày, downtime budget lý thuyết:

~~~text
30 × 24 × 60 × (1 - 0,999)
= 43,2 phút
~~~

SLO nội bộ có thể nghiêm ngặt hơn provider SLA để dành budget cho application bug, deployment, network và dependency. Theo dõi error budget theo request-based SLI, không chỉ uptime VM.

## 12. Chọn topology để đáp ứng SLA

### 12.1. Một VM

Phù hợp môi trường thử nghiệm hoặc workload chấp nhận gián đoạn. Không có redundancy ở tầng compute; host/guest failure có thể làm dịch vụ dừng.

### 12.2. Nhiều VM trong một zone

Giảm rủi ro instance failure nhưng vẫn chịu lỗi zone, network zone hoặc dependency dùng chung. SLA/credit có thể khác với topology multi-zone; kiểm tra đúng điều khoản.

### 12.3. Nhiều zone

Phân bố VM và load balancer qua nhiều zone; database cần replication/failover phù hợp. Đây là lựa chọn phổ biến cho production cần chịu lỗi zone, nhưng cần xác minh subnet/IP, quota, disk topology và data replication.

### 12.4. Nhiều region

Hỗ trợ disaster recovery hoặc active-active. Cần giải quyết replication lag, data consistency, global routing, identity, secret, quota dự phòng và failback. Hai region không tự động tạo một SLA tổng hợp nếu chưa có kiến trúc ứng dụng và vận hành phù hợp.

## 13. Ví dụ phân tích một workload trên ba cloud

Một dịch vụ API cần 60 VM, mỗi VM 4 vCPU và 16 GiB memory. Hệ thống chạy qua ba zone, có rolling deployment surge 20% và yêu cầu chịu được mất một zone.

### 13.1. Tính baseline và surge

~~~text
Baseline vCPU = 60 × 4 = 240 vCPU
Baseline RAM  = 60 × 16 = 960 GiB

Surge VM      = 60 × 20% = 12 VM
Surge vCPU    = 12 × 4 = 48 vCPU
Peak rolling  = 240 + 48 = 288 vCPU
~~~

Quota cần đủ cho peak rolling, đồng thời tính workload khác trong cùng scope. Nếu zone failure yêu cầu tạo lại VM ở hai zone còn lại, cần mô hình thêm capacity đó.

### 13.2. Kiểm tra từng nhà cung cấp

**AWS EC2**

- Chọn instance family và region/zone hỗ trợ.
- Kiểm tra On-Demand vCPU quota cho family, Spot quota nếu có worker interruptible.
- Xác nhận EBS, ENI, subnet IP và Auto Scaling group max.
- Nếu cần capacity chắc chắn, đánh giá Capacity Reservation/placement phù hợp.
- Kiểm tra EC2 SLA cùng EBS, load balancer và network terms.

**Azure Virtual Machines**

- Kiểm tra regional vCPU quota và family-specific quota của subscription.
- Xác nhận SKU có sẵn ở các Availability Zone đã chọn.
- Kiểm tra VM Scale Set max, NIC, managed disk và subnet IP.
- Xác định VM deallocation và temporary disk behavior trong automation.
- Kiểm tra SLA theo deployment model, zone và disk tier.

**Google Compute Engine**

- Kiểm tra regional CPU quota và machine family/accelerator quota của project.
- Xác nhận machine type có capacity ở zone cần triển khai.
- Kiểm tra Managed Instance Group size, Persistent Disk và IP quota.
- Xác định Local SSD/maintenance behavior và reservation nếu cần.
- Kiểm tra Compute Engine SLA cùng Persistent Disk và load balancing terms.

### 13.3. Tiêu chí chọn

Không chọn provider chỉ vì một loại VM có giá thấp hơn. So sánh:

- VM shape có đáp ứng CPU/memory/network/IOPS không.
- Quota có đủ và có thể tăng trước deadline không.
- Capacity có thể cấp ở đúng zone không.
- Lifecycle có phù hợp với stateful/ephemeral workload không.
- SLA có bao phủ đúng topology và resource không.
- Kỹ năng vận hành, observability, identity và automation hiện có.
- Chi phí compute, disk, network, backup, support và idle headroom.

## 14. Bảng quyết định theo workload

| Workload | Lifecycle cần ưu tiên | Quota cần chú ý | SLA/topology cần kiểm tra |
|---|---|---|---|
| Web/API stateless | Thay VM, rolling update, health check | vCPU family, subnet IP, LB targets | Multi-zone VM + LB + data dependency |
| Database stateful | Disk persistence, backup, failover | Disk, IOPS, storage, network | SLA database/disk/replication |
| Batch worker | Spot interruption, checkpoint, retry | Spot/CPU/GPU quota | Không dựa SLA compute interruptible |
| GPU inference | GPU lifecycle, driver/image, capacity reservation | GPU family/zone quota | Compute + accelerator + network/storage |
| CI runner | Ephemeral VM, cleanup sau job | Concurrent VM quota, API rate | SLA theo nhu cầu, queue và artifact store |
| HPC cluster | Placement, low-latency network, coordinated shutdown | CPU/GPU, NIC, placement/capacity | SLA từng node và shared fabric/storage |

## 15. Quy trình đọc và so sánh SLA

1. Xác định service chính xác: VM compute, disk, load balancer, network hay database.
2. Chọn region, zone, SKU, OS và deployment topology cụ thể.
3. Tải điều khoản SLA có hiệu lực tại thời điểm đánh giá.
4. Đọc định nghĩa downtime/availability và measurement window.
5. Kiểm tra exclusions, maintenance và customer responsibilities.
6. Kiểm tra service credit table, cap và claim deadline.
7. Lưu URL/version/date và người phê duyệt vào ADR/procurement record.
8. Ánh xạ cam kết provider vào SLO end-to-end của ứng dụng.
9. Kiểm thử failover và thu thập SLI thực tế.
10. Đánh giá lại khi đổi region, SKU, disk tier hoặc topology.

### 15.1. Câu hỏi cần trả lời trước khi ký

- SLA có áp dụng cho VM đơn hay cần nhiều VM/zone?
- Có yêu cầu dùng load balancer hoặc managed disk cụ thể không?
- Instance type/OS/region đang chọn có đủ điều kiện không?
- Stop/deallocate hoặc maintenance có được tính là downtime không?
- Outage do customer network/configuration được xử lý thế nào?
- Có SLA riêng cho disk, network, IP, DNS và load balancer không?
- Thời hạn claim và bằng chứng cần nộp là gì?
- Service credit có giới hạn và loại trừ thiệt hại gián tiếp không?

## 16. Kiểm soát quota trong vòng đời workload

Quota cần được quản lý như một dependency production:

- Đưa quota hiện tại, usage và headroom vào dashboard.
- Theo dõi quota theo region/family thay vì chỉ tổng vCPU.
- Cảnh báo trước khi đạt max autoscaling.
- Đưa quota increase vào quy trình change/capacity review.
- Kiểm tra quota trước disaster recovery exercise.
- Dọn resource mồ côi như disk, IP, snapshot và NIC để giảm lãng phí.
- Theo dõi API rate limit khi tạo hàng loạt VM.
- Tạo capacity plan cho rolling deployment và blue-green.

### 16.1. Quota increase không phải capacity reservation

Yêu cầu tăng quota thường tăng mức được phép sử dụng. Nó không tự giữ trước host vật lý. Nếu cần bảo đảm capacity cho peak hoặc failover, đánh giá reservation/capacity guarantee theo sản phẩm và hợp đồng riêng.

### 16.2. Kiểm thử quota exhaustion

Trong môi trường kiểm thử, mô phỏng quota gần chạm ngưỡng hoặc đặt max group thấp để xác minh:

- Autoscaler báo lỗi rõ ràng.
- Alert được kích hoạt.
- Workload không tạo retry loop vô hạn.
- Queue/backpressure giữ tải an toàn.
- Runbook chỉ ra quota scope cần tăng.
- Sau khi quota được tăng, scaling tiếp tục mà không tạo instance trùng.

Không cố tình làm cạn quota production dùng chung với workload quan trọng.

## 17. Các rủi ro khi di chuyển giữa cloud

### 17.1. Lifecycle mismatch

Script tự động hóa có thể giả định stop luôn giải phóng compute, disk luôn tồn tại sau delete hoặc public IP không đổi. Các giả định này có thể sai giữa provider. Chuẩn hóa lifecycle qua abstraction nhưng vẫn giữ provider-specific adapter và integration test.

### 17.2. Quota mismatch

Một region có thể có quota vCPU lớn nhưng quota GPU/NIC/IP thấp. Mapping instance type tương đương không bảo đảm quota tương đương. Trước migration, lập bảng resource theo family và scope, gửi request tăng quota sớm và test capacity.

### 17.3. SLA mismatch

Một cấu hình multi-zone ở provider A có thể đáp ứng điều kiện SLA khác với cấu hình single-zone ở provider B. Không so sánh các con số SLA khi topology và phạm vi covered service khác nhau.

### 17.4. Data durability mismatch

Local SSD, temporary disk và persistent disk có behavior khác nhau. Migration phải xác định dữ liệu nào cần copy, replicate, backup hoặc tái tạo; không sao chép cấu hình disk theo tên tương tự mà bỏ qua semantics.

### 17.5. Operational mismatch

Monitoring event, maintenance notification, identity, image lifecycle, autoscaling API và shutdown hook khác nhau. Dùng một runbook chung ở mức quy trình, nhưng có bước provider-specific cho command, event và resource identifier.

## 18. Công cụ và tài liệu tham khảo chính thức

### AWS

- EC2 instance lifecycle: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html
- EC2 instance store: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/InstanceStorage.html
- Service Quotas: https://docs.aws.amazon.com/servicequotas/latest/userguide/intro.html
- AWS Service Level Agreements: https://aws.amazon.com/legal/service-level-agreements/

### Microsoft Azure

- VM states and billing: https://learn.microsoft.com/azure/virtual-machines/states-billing
- VM quotas and limits: https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits
- Azure Service Level Agreements: https://azure.microsoft.com/support/legal/sla/
- Ephemeral OS disks: https://learn.microsoft.com/azure/virtual-machines/ephemeral-os-disks

### Google Cloud

- VM instance lifecycle: https://cloud.google.com/compute/docs/instances/instance-lifecycle
- Compute Engine quotas: https://cloud.google.com/compute/quotas
- Compute Engine SLA: https://cloud.google.com/compute/sla
- Local SSD: https://cloud.google.com/compute/docs/disks/local-ssd

Các liên kết là điểm bắt đầu tra cứu. Trước khi triển khai, kiểm tra trang tài liệu hiện hành cho region, SKU và tính năng cụ thể; các quota, trạng thái và SLA có thể được cập nhật.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi stop và deallocate là giống nhau | Dự toán compute billing sai | Kiểm tra trạng thái và billing semantics của provider |
| Lưu dữ liệu quan trọng trên local disk | Mất dữ liệu khi host/VM bị thay | Dùng persistent storage, replication và backup |
| Giả định delete VM xóa hoặc giữ mọi disk giống nhau | Mất dữ liệu hoặc phát sinh disk mồ côi | Kiểm tra delete/auto-delete policy từng resource |
| Quota còn dư nghĩa là luôn tạo được VM | Scale-out thất bại do zone/SKU capacity | Kiểm tra quota và capacity riêng |
| Chỉ kiểm tra tổng vCPU quota | Thiếu quota family/GPU/IP/disk | Lập quota matrix theo resource và scope |
| Đặt max autoscaling bằng quota tuyệt đối | Không còn headroom cho rollout/failover | Dành quota cho surge và recovery |
| Dùng Spot cho stateful primary | Mất capacity đột ngột gây gián đoạn/dữ liệu lỗi | Chỉ dùng cho workload interruptible có checkpoint |
| Lấy provider SLA làm application SLA | Cam kết với khách hàng vượt phạm vi được bảo đảm | Xây dựng SLO end-to-end và kiểm thử |
| So sánh SLA khác topology | Kết luận sai về mức availability | Chuẩn hóa zone, instance count và dependency |
| Không đọc exclusions/claim deadline | Không đủ điều kiện nhận service credit | Lưu điều khoản và quy trình claim |
| Không test restore/failover | Không biết RTO/RPO thực tế | Diễn tập định kỳ và đo kết quả |
| Giả định maintenance luôn live migrate | Workload không chịu được reboot/retire | Test restart/replacement và graceful shutdown |

## 20. Checklist đánh giá provider và production readiness

**Lifecycle**

- [ ] Đã hiểu trạng thái create, run, stop, deallocate, suspend, reboot và delete.
- [ ] Đã xác định billing behavior của từng trạng thái.
- [ ] Đã phân loại persistent disk và local/temporary disk.
- [ ] Đã xác định public IP, NIC và disk behavior khi stop/start/delete.
- [ ] Đã hiểu host maintenance, live migration và retirement event.
- [ ] Workload có thể phục hồi sau VM replacement.

**Quota và capacity**

- [ ] Đã kiểm tra quota theo account/subscription/project và region.
- [ ] Đã kiểm tra quota theo VM family, GPU, disk, IP và API.
- [ ] Đã kiểm tra SKU/zone availability.
- [ ] Đã tính rolling surge, failover và DR capacity.
- [ ] Có headroom và alert cho quota usage.
- [ ] Đã phân biệt quota increase với capacity reservation.

**SLA và SLO**

- [ ] Đã lưu đúng SLA version và URL có hiệu lực.
- [ ] Đã xác minh covered service, region, SKU và topology.
- [ ] Đã đọc measurement, exclusions, remedy và claim deadline.
- [ ] Đã kiểm tra SLA riêng của disk, network, load balancer và database.
- [ ] Có application SLO và error budget độc lập với provider SLA.
- [ ] Đã test multi-zone failover, backup restore và recovery.

**Migration và vận hành**

- [ ] Lifecycle automation có adapter/provider-specific tests.
- [ ] Disk/data được migrate theo durability semantics.
- [ ] Quota request hoàn tất trước migration cutover.
- [ ] Autoscaling và replacement được thử ở từng region.
- [ ] Runbook maintenance, interruption và rollback đã có owner.
- [ ] Cost model tính cả idle headroom, disk, network và support.

## 21. Kết luận

Vòng đời VM, quota và SLA là ba yếu tố liên quan nhưng không thể thay thế cho nhau. Lifecycle quyết định VM và dữ liệu thay đổi thế nào khi create, stop, resize, maintenance hoặc delete. Quota xác định mức tài nguyên được phép yêu cầu trong một scope; capacity thực tế vẫn phụ thuộc zone, SKU và thời điểm. SLA xác định phạm vi dịch vụ được cam kết, điều kiện đo và biện pháp khắc phục theo hợp đồng.

Khi so sánh AWS EC2, Azure Virtual Machines và Google Compute Engine, hãy chuẩn hóa workload, topology, disk, quota scope và SLA eligibility. Tính quota cho cả rolling deployment và failover, thiết kế workload chịu được VM replacement, tách dữ liệu bền vững khỏi local disk và xây dựng SLO end-to-end riêng. Quyết định provider nên dựa trên bằng chứng vận hành, khả năng cấp capacity, semantics lifecycle và điều khoản có hiệu lực thay vì chỉ dựa trên giá VM hoặc một con số SLA tổng quát.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| VM lifecycle | Các trạng thái và thao tác từ provision đến terminate/delete. |
| Deallocate | Giải phóng compute allocation; disk/resource khác có thể vẫn tồn tại và tính phí. |
| Hibernate/suspend | Lưu trạng thái memory để resume nếu loại VM hỗ trợ. |
| Persistent Disk | Block storage được quản lý tách khỏi vòng đời VM ở mức độ nhất định. |
| Local/ephemeral disk | Storage gắn với host, thường dùng cho dữ liệu tạm và có thể mất khi VM bị thay. |
| Spot/preemptible VM | Compute capacity giá thấp có thể bị provider thu hồi. |
| Quota | Mức tài nguyên tối đa được phép yêu cầu trong một scope. |
| System limit | Giới hạn kỹ thuật/policy không nhất thiết tăng được bằng quota request. |
| Available capacity | Tài nguyên thực tế có thể cấp tại zone/region và thời điểm yêu cầu. |
| Capacity reservation | Cơ chế giữ trước capacity theo semantics và điều khoản của provider. |
| SLA | Cam kết hợp đồng về mức dịch vụ, phạm vi, cách đo và remedy. |
| SLO | Mục tiêu chất lượng dịch vụ nội bộ. |
| SLI | Chỉ số đo dùng để đánh giá SLO. |
| Error budget | Phần downtime/error có thể chấp nhận trong cửa sổ SLO. |
| Service credit | Khoản credit theo điều khoản SLA khi đáp ứng điều kiện claim. |
| Availability Zone | Failure domain trong một region. |
| Live migration | Chuyển VM giữa host với gián đoạn tối thiểu nếu workload/platform hỗ trợ. |
| Connection draining | Ngừng nhận request mới và chờ request đang chạy trước khi loại backend. |
| Quota headroom | Phần quota dự phòng cho surge, replacement và failover. |
