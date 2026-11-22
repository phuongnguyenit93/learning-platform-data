# AWS Elastic Disaster Recovery và phục hồi máy chủ

Một sự cố tại trung tâm dữ liệu, vùng cloud hoặc hệ điều hành có thể làm máy chủ ngừng hoạt động và khiến doanh nghiệp mất dữ liệu mới phát sinh. Disaster Recovery (DR) là năng lực khôi phục workload và dữ liệu sau sự cố để đáp ứng mục tiêu RPO và RTO đã cam kết. Một kế hoạch DR tốt cần có bản sao dữ liệu đủ mới, hạ tầng đích có thể khởi chạy, cấu hình mạng/ứng dụng đã chuẩn bị, thứ tự phục hồi rõ ràng và bài kiểm tra định kỳ.

AWS Elastic Disaster Recovery (AWS DRS) là dịch vụ block-level replication và recovery cho máy chủ vật lý, máy ảo và máy chủ cloud chạy hệ điều hành được hỗ trợ. DRS liên tục sao chép các thay đổi từ source server vào staging area trong AWS; khi cần kiểm tra hoặc khôi phục, dịch vụ chuyển đổi bản sao thành EC2 instance có thể boot trong AWS. Có thể khôi phục từ trạng thái mới nhất hoặc một point-in-time snapshot trước đó, thực hiện recovery drill không làm gián đoạn source server, và failback dữ liệu về hạ tầng ban đầu khi sự cố đã được xử lý.

Bài thuộc chương **Sao lưu và khôi phục thảm họa**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối DRS với Amazon EC2, EBS, VPC, IAM, AWS Systems Manager, CloudWatch, CloudTrail, Route 53 và AWS Backup để thiết kế, vận hành và kiểm thử phục hồi máy chủ.

> **Phân biệt trách nhiệm:** AWS DRS quản lý replication, tạo drill/recovery instances và hỗ trợ reverse replication/failback. Việc quyết định thời điểm failover, chuyển traffic/DNS, xác nhận ứng dụng hoạt động và điều phối business continuity vẫn thuộc kế hoạch của tổ chức. DRS không tự động chuyển người dùng sang recovery instances.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích RPO, RTO, failover, recovery, recovery drill và failback.
2. Mô tả kiến trúc AWS DRS gồm source server, replication agent, staging area và recovery instance.
3. Phân biệt replication liên tục với backup/long-term retention.
4. Đánh giá source server OS, disk, architecture và agent prerequisites.
5. Thiết kế network path, staging subnet, security group và firewall rules cho DRS.
6. Phân biệt TCP 443 và TCP 1500 trong replication workflow.
7. Giải thích block-level replication, initial sync, continuous replication và replication lag.
8. Cấu hình replication settings, EBS encryption và point-in-time retention.
9. Cấu hình launch settings, EC2 launch template và post-launch actions.
10. Thực hiện recovery drill không làm gián đoạn production source.
11. Thực hiện recovery/failover và chuyển traffic có kiểm soát.
12. Dùng Recovery Plans để khởi chạy nhiều máy chủ theo thứ tự phụ thuộc.
13. Thực hiện failback về on-premises hoặc AWS source environment.
14. Thiết kế bảo mật IAM, KMS/EBS encryption, snapshots và audit.
15. Theo dõi replication health, lag, launch results và chi phí.
16. Xử lý các lỗi agent, connectivity, bandwidth, conversion và failback.
17. Xây dựng runbook DR và kiểm tra định kỳ theo RPO/RTO.

## 2. Khái niệm DR và mục tiêu khôi phục

### 2.1. RPO và RTO

| Khái niệm | Câu hỏi cần trả lời | Ý nghĩa |
|---|---|---|
| RPO (Recovery Point Objective) | Có thể chấp nhận mất tối đa bao nhiêu dữ liệu? | Khoảng thời gian dữ liệu có thể mất giữa thời điểm sự cố và điểm khôi phục |
| RTO (Recovery Time Objective) | Dịch vụ được phép gián đoạn tối đa bao lâu? | Thời gian từ khi bắt đầu sự cố đến khi workload hoạt động lại ở mức đã định |
| MTD (Maximum Tolerable Downtime) | Doanh nghiệp chịu gián đoạn tối đa bao lâu? | Giới hạn kinh doanh để xác định RTO và phương án dự phòng |
| WRT (Work Recovery Time) | Cần thêm bao lâu để xử lý nghiệp vụ sau khi hệ thống lên? | Thời gian kiểm tra dữ liệu, đối soát và đưa quy trình nghiệp vụ về bình thường |

Ví dụ: một hệ thống thanh toán có RPO 1 phút và RTO 30 phút. Khi sự cố xảy ra, doanh nghiệp chấp nhận mất tối đa khoảng một phút giao dịch chưa được sao chép, và cần khôi phục luồng thanh toán trong vòng 30 phút. Đây là mục tiêu thiết kế/kiểm thử, không phải bảo đảm rằng mọi lần khôi phục đều đạt được.

### 2.2. Failover, recovery, drill và failback

- **Replication:** đồng bộ block-level changes từ source server tới AWS staging area.
- **Recovery drill:** khởi chạy instance kiểm thử từ bản sao đã replicate để xác nhận khả năng boot và hoạt động; không thay thế source production.
- **Recovery:** khởi chạy recovery instances trong AWS khi cần phục hồi thật.
- **Failover:** chuyển người dùng hoặc traffic từ môi trường primary sang recovery environment. Đây là hoạt động do tổ chức thực hiện bằng DNS, load balancer, routing hoặc cơ chế traffic management khác.
- **Failback:** đưa workload và dữ liệu từ recovery environment trở lại hạ tầng primary sau khi đã xử lý sự cố; DRS hỗ trợ reverse replication và launch tại source environment.

Không nhầm việc EC2 recovery instance khởi chạy thành việc ứng dụng đã failover thành công. Cần xác minh boot, network, dependencies, database consistency, application health và traffic cutover.

### 2.3. AWS DRS phù hợp khi nào?

DRS phù hợp khi cần bảo vệ full servers và muốn khôi phục workload hiện có trên EC2 mà không phải thiết kế lại ứng dụng trước. Các nguồn có thể là physical servers, VMware/Hyper-V virtual machines hoặc cloud-based servers chạy OS được hỗ trợ. DRS cũng có thể hỗ trợ migration sang AWS, nhưng mục tiêu chính trong bài là disaster recovery.

DRS không phải lựa chọn thay thế cho mọi hình thức bảo vệ dữ liệu:

- Với database native replication, cần đánh giá consistency, transaction log, cluster topology và database-specific recovery.
- Với ứng dụng serverless hoặc managed services, dùng cơ chế backup/replication/failover của từng dịch vụ.
- Với file/object backup dài hạn, dùng AWS Backup, S3 versioning/Object Lock hoặc archive theo retention policy.
- Với multi-Region active-active, cần thiết kế traffic, data consistency và conflict handling riêng.

## 3. Kiến trúc AWS Elastic Disaster Recovery

### 3.1. Các thành phần

| Thành phần | Vai trò |
|---|---|
| Source server | Máy chủ vật lý, VM hoặc cloud instance chứa workload và dữ liệu nguồn |
| AWS Replication Agent | Agent cài trên từng source server, theo dõi block writes và gửi thay đổi tới AWS |
| AWS DRS service | Điều phối replication, quản lý source server, point-in-time states, launch và failback workflow |
| Staging area subnet | Subnet trong target AWS Region chứa replication servers |
| Replication server | EC2 instance do DRS quản lý để nhận và ghi replicated blocks vào EBS staging volumes |
| EBS staging volumes/snapshots | Lưu bản sao dữ liệu và các recovery points |
| EC2 launch template | Quy định cách drill/recovery instances được tạo: subnet, instance type, security groups, disks, IP và tags |
| Recovery instance | EC2 instance được khởi chạy từ replicated data để kiểm thử hoặc phục hồi workload |
| Post-launch actions | SSM commands/Automation documents chạy sau khi recovery instance khởi chạy |

### 3.2. Luồng dữ liệu

~~~mermaid
flowchart LR
    SRC["Source server<br/>Physical / VM / Cloud"] --> AGENT["AWS Replication Agent<br/>Block-level tracking"]
    AGENT -->|"TCP 1500<br/>TLS 1.2, encrypted data"| REPL["Replication server<br/>Staging subnet"]
    AGENT -->|"TCP 443<br/>DRS API / control plane"| DRS["AWS DRS service"]
    REPL --> EBS["EBS staging volumes"]
    EBS --> PIT["Point-in-time snapshots"]
    PIT -->|"Drill / Recovery launch"| EC2["EC2 recovery instance"]
    EC2 --> APP["Application / dependencies"]
    DRS --> LAUNCH["Launch settings / recovery plan"]
    LAUNCH --> EC2
~~~

Quy trình tổng quát:

1. Khởi tạo DRS trong target Region.
2. Cấu hình replication template và staging subnet.
3. Cài AWS Replication Agent trên từng source server.
4. Agent thực hiện initial sync, sao chép các block cần thiết vào staging area.
5. Khi initial sync hoàn tất, DRS tiếp tục replicate các block thay đổi.
6. DRS tạo và duy trì point-in-time recovery states theo retention policy.
7. Khi drill/recovery, DRS tạo EBS volumes và EC2 instances từ recovery point được chọn.
8. Instance conversion thực hiện các điều chỉnh cần thiết để máy chủ có thể boot trên EC2, như driver, bootloader và network configuration.
9. Tổ chức kiểm tra ứng dụng; nếu là failover thật, tổ chức chuyển traffic.
10. Khi primary environment sẵn sàng, thực hiện reverse replication và failback theo loại source.

### 3.3. RPO và RTO của DRS

AWS mô tả RPO điển hình của DRS ở mức dưới một giây khi continuous replication khỏe mạnh và hội tụ. Đây là kết quả có thể đạt được trong điều kiện replication hoạt động bình thường, không phải cam kết cho mọi source server. Nếu write rate cao hơn bandwidth, agent mất kết nối, replication server gặp lỗi hoặc backlog chưa được xử lý, recovery point có thể cũ hơn.

RTO phụ thuộc vào nhiều bước: chọn recovery point, tạo EBS volumes, conversion, EC2 capacity, boot, post-launch actions, application initialization, dependency readiness và traffic cutover. AWS có thể khởi chạy recovery instances trong vài phút trong nhiều tình huống, nhưng thời gian thực tế phải đo bằng recovery drills.

Hãy đo RPO/RTO ở cấp ứng dụng. Một server boot thành công nhưng database, DNS, Active Directory hoặc queue chưa sẵn sàng thì business service vẫn chưa recover.

## 4. Nguồn máy chủ và điều kiện hỗ trợ

### 4.1. Kiểu source server

AWS DRS có thể replicate:

- Máy chủ vật lý tại data center.
- Máy ảo trong hypervisor được hỗ trợ.
- Máy chủ trên cloud provider khác.
- EC2 instance trong AWS, kể cả khi cần recovery sang Region/account khác theo mô hình được hỗ trợ.

DRS replicate ở cấp máy chủ và block volumes; nếu source server chạy container, các container nằm trên máy chủ đó cũng được sao chép như một phần của server. DRS không phải công cụ Kubernetes/container migration độc lập: trạng thái external volumes, managed databases, load balancers và control plane cần bảo vệ bằng cơ chế riêng.

DRS xử lý block devices như local disks. Với SAN, nếu LUN được expose thành block device trên source server thì agent có thể replicate như disk khác. Với NAS/NFS share được mount qua network, cần cài agent trên chính NFS server để replicate filesystem gốc. DRS hỗ trợ hardware RAID và LVM, nhưng boot partition trải rộng hoặc mirror bằng software qua nhiều physical disks không được hỗ trợ; kiểm tra layout trước khi cài agent.

### 4.2. Operating systems và CPU architecture

Phải kiểm tra danh sách OS được hỗ trợ trước khi cài agent vì danh sách và điều kiện hỗ trợ thay đổi theo release. Một số OS đã hết vòng đời có thể bị AWS ngừng hỗ trợ dù agent cũ từng hoạt động.

Tại thời điểm 20/11/2026:

- Source server 64-bit x86_64 được hỗ trợ theo danh sách OS hiện hành.
- Linux `arm64` trên AWS Graviton EC2 được hỗ trợ từ tháng 09/2026 cho AWS-to-AWS recovery.
- `arm64` hiện chỉ hỗ trợ source là EC2 Graviton và recovery/failback trong AWS; on-premises/other cloud source và Windows `arm64` không được hỗ trợ.
- Windows source server hỗ trợ `x86_64`; không hỗ trợ Windows `arm64`.
- Không hỗ trợ hệ điều hành 32-bit.

Luôn xem Supported Linux operating systems và Supported Windows operating systems trước khi lập inventory.

### 4.3. Agent installation prerequisites

Linux source server thường cần:

- Root hoặc sudo để cài driver và service.
- Ít nhất 300 MB RAM trống cho AWS Replication Agent; Python 2.4+ hoặc Python 3.x; MAC address ổn định qua reboot/network changes.
- Kernel headers khớp chính xác kernel đang chạy.
- `gcc`, `make` và các package được yêu cầu.
- Tối thiểu 4 GB trống trên `/` và 500 MB trên `/tmp`.
- Nếu `/boot` là partition riêng, cần ít nhất 50 MB trống; bootloader phải là GRUB 1 hoặc 2 và Secure Boot không được hỗ trợ.
- `/tmp` cho phép thực thi installer; mount `noexec` có thể làm cài đặt thất bại.
- Cài `dhclient` để recovery instance có thể dùng DHCP networking; không dùng source server paravirtualized.
- Không có disk filter driver xung đột; Oracle ASM Filter Driver phải được xử lý theo hướng dẫn AWS, PowerPath cần liên hệ Support.

Windows source server cần:

- Administrator privilege.
- .NET Framework phù hợp với phiên bản Windows.
- Ít nhất 300 MB RAM trống và MAC address ổn định; `net.exe` và `sc.exe` phải có trong system PATH.
- Ít nhất 1 GB trống trên ổ C:.
- TLS 1.2 được bật.
- BitLocker phải được tắt trên các volume cần replicate theo yêu cầu của DRS.
- Chạy installer từ PowerShell theo hướng dẫn AWS.

Cần kiểm tra OS-specific prerequisites và installer architecture trước khi triển khai hàng loạt. Không dùng chung installer x86_64 cho Linux arm64.

### 4.4. Giới hạn disk và volume

Theo agent prerequisites hiện hành:

- Mỗi volume mặc định tối đa 16 TiB; từ tháng 08/2026 DRS hỗ trợ volume tới 64 TiB nếu chọn gp3 staging disk type.
- Mỗi source server tối đa 63 volumes.
- Volume vượt giới hạn không được replicate.
- Thêm disk mới sau khi cài agent cần kiểm tra cấu hình tự động replicate new disks và replication settings.

Hãy inventory boot disk, data disk, mount points, filesystem, LVM/RAID, database volumes và disk dependencies. Một volume bị bỏ sót có thể làm recovery instance boot được nhưng ứng dụng thiếu dữ liệu.

## 5. Network architecture và firewall requirements

DRS cần hai luồng network khác nhau. TCP 443 phục vụ control plane/API và download agent; TCP 1500 truyền replicated blocks giữa source server và replication server.

| Nguồn | Đích | Port | Mục đích |
|---|---|---:|---|
| Source server | DRS regional endpoint `drs.<region>.amazonaws.com` | TCP 443 outbound | Agent registration, service communication, status và metadata |
| Source server | S3 regional endpoints/buckets cần thiết | TCP 443 outbound | Download agent/updates và service artifacts |
| Source server | EC2 regional endpoint | TCP 443 outbound | AWS API/control operations cần thiết cho agent/replication workflow |
| Source server | Replication server trong staging subnet | TCP 1500 | Block-level replication stream |
| Replication server trong staging subnet | DRS regional endpoint | TCP 443 outbound | Control plane, service coordination |
| Replication server trong staging subnet | S3 và EC2 regional endpoints | TCP 443 outbound | Download artifacts và AWS API operations |

Mọi communication được mã hóa. DRS dùng TLS 1.2 end-to-end giữa agent và replication server trên port 1500. Không để firewall/proxy/SSL inspection thiết bị trung gian giải mã hoặc làm gián đoạn TLS stream này.

### 5.1. Staging area subnet

Tạo subnet riêng trong VPC tại target Region để chứa replication servers. AWS khuyến nghị dùng dedicated staging subnet nhằm tách traffic replication và đơn giản hóa routing/security.

Cần thiết kế:

- CIDR đủ địa chỉ IP cho replication servers theo số lượng source disks và scale dự kiến.
- Dự trù khoảng một replication server cho mỗi 15 source volumes; cần thêm địa chỉ IP cho conversion server khi drill/recovery launch, thường một conversion server cho mỗi source server được khởi chạy.
- Route tới DRS, S3 và EC2 regional endpoints qua NAT/Internet gateway hoặc VPC endpoints theo kiến trúc được hỗ trợ.
- Nếu dùng S3 VPC endpoint, endpoint policy phải cho phép các DRS service buckets và Amazon Linux 2023 repository bucket `al2023-repos-<REGION>-de612dc2`; replication servers chạy Amazon Linux 2023 và cần bucket này để cài package/update.
- Security group cho replication server cho phép inbound TCP 1500 từ source network và outbound TCP 443 tới AWS endpoints.
- Network ACL cho phép traffic hai chiều và ephemeral return ports.
- DNS resolution/hostnames hoạt động đúng.
- Không overlap CIDR với source networks nếu cần private IP routing.
- Tách staging subnet khỏi operational subnet nơi recovery instances sẽ chạy.

DRS có thể tạo replication servers trong public subnet với public IPv4 theo default configuration. Nếu chọn private IP data routing, source server phải có private connectivity và route tới private IP của replication server. Không bật private IP option khi source không thể reach subnet đó.

### 5.2. Kết nối private và public

Có thể dùng Internet/NAT cho control plane và replication traffic, hoặc private connectivity như VPN, AWS Direct Connect, VPC peering và các mô hình network được AWS hỗ trợ. Private path giúp giảm phụ thuộc Internet và hỗ trợ yêu cầu network isolation, nhưng vẫn cần route, DNS, security group, NACL và endpoint policies đúng.

Không cho rằng chỉ có VPN là đủ. Kiểm tra TCP 443 tới DRS/S3/EC2 endpoints, TCP 1500 giữa source và replication server, return traffic và MTU/path behavior. DRS replication traffic được nén và mã hóa; không cần TLS inspection ở giữa.

### 5.3. Kiểm tra connectivity

Linux source server có thể kiểm tra DRS API endpoint:

~~~bash
curl -v https://drs.ap-southeast-1.amazonaws.com/
~~~

Windows source server:

~~~powershell
Test-NetConnection drs.ap-southeast-1.amazonaws.com -Port 443
~~~

Kiểm tra port 1500 tới địa chỉ replication server được hiển thị trong DRS console:

~~~bash
nc -vz <replication-server-ip> 1500
~~~

Các lệnh trên kiểm tra TCP connectivity, không xác nhận agent đã được đăng ký hoặc replication đã healthy. Sau khi kiểm tra network, xác nhận agent service đang chạy và DRS console hiển thị source server.

## 6. Khởi tạo DRS và cài AWS Replication Agent

### 6.1. Khởi tạo target Region

DRS được khởi tạo riêng trong từng AWS Region mà bạn muốn dùng làm recovery target. Với AWS-to-AWS disaster recovery, initialize DRS ở cả source Region và target Region trước khi cài agent/replicate. Quá trình initialization tạo service configuration, replication template và service-linked role cần thiết.

Quy trình tổng quát:

1. Chọn target Region phù hợp yêu cầu latency, compliance, capacity và disaster isolation.
2. Mở AWS Elastic Disaster Recovery Console.
3. Initialize service trong Region đó.
4. Chọn staging area subnet và default replication settings.
5. Cấu hình EBS encryption, EBS volume type, data routing, bandwidth throttling và point-in-time retention.
6. Cấu hình default launch settings và post-launch actions.
7. Kiểm tra service-linked role `AWSServiceRoleForElasticDisasterRecovery` đã được tạo.

Service-linked role được DRS tạo tự động khi cấu hình replication template; không cần tự tạo role thay thế. Người khởi tạo cần IAM permissions cho DRS và quyền tạo service-linked role.

### 6.2. Tạo credentials cài agent

AWS Replication Agent cần credential IAM để đăng ký source server. Principal cài agent phải được cấp policy `AWSElasticDisasterRecoveryAgentInstallationPolicy` theo tài liệu AWS và chỉ dùng trong thời gian cài đặt.

Nguyên tắc:

- Dùng role/temporary credentials nếu môi trường hỗ trợ.
- Không nhúng long-term access keys vào image hoặc script lưu trong source control.
- Không chia sẻ một credential vượt quyền cho nhiều nhóm.
- Thu hồi/rotate credential cài đặt sau khi hoàn tất.
- Tách quyền cài agent khỏi quyền quản trị recovery/failover.
- Theo dõi CloudTrail để xác định ai đã thêm source server.

### 6.3. Cài agent trên Linux/Windows

Agent phải được cài trên từng source server cần bảo vệ. Chọn đúng target Region và installer architecture.

Các bước chung:

1. Xác minh OS/architecture nằm trong danh sách hỗ trợ.
2. Kiểm tra disk space, kernel headers, package và quyền administrator/root.
3. Xác minh TCP 443 và TCP 1500 theo network design.
4. Tải installer từ AWS DRS console hoặc S3 regional bucket được chỉ định.
5. Chạy installer với IAM credentials/policy phù hợp.
6. Chọn target Region đã initialize.
7. Xác minh agent service đang chạy và source server xuất hiện trong DRS console.
8. Theo dõi initial sync cho tới khi hoàn tất và replication status chuyển Healthy.

Với Linux, service thường được quản lý qua systemd. Có thể kiểm tra:

~~~bash
sudo systemctl status aws-replication-agent
~~~

Với Windows, dùng PowerShell:

~~~powershell
Get-Service AwsReplicationService
~~~

Tên service/command có thể khác theo OS/agent release; dùng đúng installer guide cho phiên bản đang triển khai.

### 6.4. Initial sync và continuous replication

Initial sync đọc các block cần thiết từ source disks và chuyển chúng tới staging area. Thời gian initial sync phụ thuộc dung lượng dữ liệu cần sao chép, write rate, bandwidth, IOPS và tình trạng network. Không nên đưa workload vào production DR readiness chỉ vì agent đã cài xong.

Khi initial sync hoàn tất, DRS tiếp tục theo dõi các block thay đổi và gửi chúng tới replication server. Source server vẫn chạy production trong suốt replication. Agent nhẹ và được thiết kế để không gây gián đoạn ứng dụng, nhưng vẫn cần theo dõi CPU, RAM, disk I/O và replication lag trên các máy chủ write-intensive.

## 7. Replication settings, EBS và point-in-time recovery

### 7.1. Replication settings

DRS có default replication settings áp dụng cho source servers mới được thêm sau khi thay đổi. Khi sửa default settings, các source servers đã tồn tại không tự động nhận cấu hình mới; cần chỉnh individual replication settings nếu muốn cập nhật chúng.

Các tham số quan trọng:

| Setting | Tác động |
|---|---|
| Staging area subnet | Vị trí replication servers trong VPC |
| Replication server instance type | Compute capacity để nhận/ghi replicated data |
| EBS volume type | Chi phí, throughput và IOPS của staging volumes |
| EBS encryption | Mã hóa staging volumes/snapshots |
| Automatically replicate new disks | Tự động bảo vệ disk mới được thêm vào source |
| Data routing / Use private IP | Chọn đường replication qua public hoặc private IP |
| Network bandwidth throttling | Giới hạn băng thông replication để bảo vệ production network |
| Point-in-time policy | Tần suất và thời gian giữ recovery points |
| Security group | Quy tắc network cho replication servers |

Dedicated replication server có thể được cấu hình riêng theo source server; không phải mọi setting đều hỗ trợ trong default template. Thay đổi một số replication settings có thể làm agent reconnect hoặc full sync; đọc impact trước khi chỉnh production.

### 7.2. Chọn EBS volume type và throughput

DRS tạo staging volumes có dung lượng tương ứng source disks. EBS type ảnh hưởng chi phí và khả năng ghi các block thay đổi. Auto volume type selection có thể chọn loại phù hợp theo size/throughput cho các disk lớn; disk nhỏ hơn 125 GiB có hành vi volume type riêng theo tài liệu DRS.

Một replication server có thể phục vụ nhiều staging disks, tối đa 15 disks theo pricing guidance hiện hành. Số lượng replication servers cần thiết phụ thuộc tổng số disks và write throughput; source write-intensive có thể cần instance type mạnh hơn hoặc dedicated replication server.

Không đổi volume type chỉ vì muốn dùng SSD nhanh hơn. Đo source write throughput, replication lag và staging disk IOPS trước. Tăng performance có thể giảm lag nhưng làm tăng chi phí EBS.

### 7.3. Tính bandwidth replication

Tổng bandwidth khả dụng phải lớn hơn tổng write throughput trung bình của các source servers đi qua cùng network path. AWS khuyến nghị thêm ít nhất 20% headroom để hấp thụ burst writes.

Công thức thiết kế:

\[
B_{\min} \geq \sum_{i=1}^{n} W_i \times 1.2
\]

Trong đó:

- \(B_{\min}\): bandwidth tối thiểu cần dự trù.
- \(W_i\): average write throughput của source server thứ i.
- Hệ số 1.2 là headroom tối thiểu khuyến nghị; workload có burst lớn có thể cần nhiều hơn.

Ví dụ hai server ghi trung bình 5 MB/s và 7 MB/s trên cùng đường truyền:

\[
B_{\min} \geq (5+7)\times 1.2 = 14.4\ MB/s
\]

Đo write rate ít nhất 24 giờ để có cả peak và average. Nếu bandwidth thấp hơn write rate, backlog tăng, replication không hội tụ và recovery point ngày càng cũ.

### 7.4. Encryption at rest và in transit

DRS truyền replicated data đã mã hóa và nén; agent mã hóa dữ liệu trước khi gửi và sử dụng TLS 1.2 cho kết nối agent-to-replication-server. EBS staging volumes/snapshots có thể được mã hóa bằng AWS KMS theo replication settings.

Nếu dùng customer managed KMS key:

- Chọn key trong đúng Region.
- Key policy/grants phải cho phép service và principal cần thiết.
- Bảo vệ quyền `kms:DisableKey`, `kms:ScheduleKeyDeletion` và policy changes.
- Không xóa key khi staging snapshots hoặc recovery resources còn phụ thuộc.
- Kiểm tra cross-account access nếu staging và recovery accounts khác nhau.

### 7.5. Point-in-time recovery (PIT)

DRS lưu các recovery points để có thể chọn trạng thái dữ liệu gần nhất hoặc một thời điểm trước đó. Lịch PIT hiện hành gồm:

- Snapshot mỗi 10 phút trong giờ gần nhất.
- Snapshot mỗi giờ trong 24 giờ gần nhất.
- Snapshot mỗi ngày theo retention policy.
- Daily retention có thể cấu hình từ 1 đến 365 ngày; giá trị dài hơn tăng chi phí EBS snapshot storage.

PIT policy cần đúng ba rules MINUTE, HOUR và DAY; interval/retention của MINUTE và HOUR được AWS cố định, còn DAY retention có thể cấu hình. Kiểm tra policy hiện hành trong console/API vì schema có thể thay đổi.

PIT snapshots giúp phục hồi trước thời điểm corruption, accidental deletion hoặc ransomware đã đồng bộ về staging. Tuy nhiên, DRS replication không phải bản backup immutable: attacker có quyền vào account có thể cố xóa snapshots hoặc phá hủy key. Bảo vệ quyền snapshot, KMS và DRS bằng IAM least privilege, SCP/guardrails, separation of duties và AWS Backup/Vault Lock khi yêu cầu retention/immutability.

### 7.6. Chọn recovery point

- Chọn **Use most recent data** khi ưu tiên RPO thấp nhất và replication đang Healthy.
- Chọn snapshot trước một thời điểm cụ thể khi cần tránh corruption hoặc thay đổi sai đã được replicate.
- Đối chiếu event timeline, CloudTrail, application logs và database consistency trước khi chọn.
- Không chọn recovery point chỉ vì timestamp gần nhất nếu dữ liệu đã bị mã hóa/xóa/hỏng từ trước đó.
- Kiểm tra mọi server trong application group dùng recovery points tương thích để tránh database/application version mismatch.


## 8. Launch settings và post-launch actions

### 8.1. DRS launch settings và EC2 launch template

Launch settings quyết định cách DRS tạo drill/recovery instances. Chúng gồm DRS launch settings và EC2 launch template. Mỗi source server có launch configuration riêng, được tạo tự động khi source được thêm vào DRS; có thể sửa ngay cả khi initial sync chưa hoàn tất.

Các lựa chọn thường cần review:

| Setting | Mục đích |
|---|---|
| Instance type right-sizing | Chọn EC2 instance type phù hợp CPU/RAM/OS của source |
| Start instance upon launching | Tự động start recovery instance hoặc tạo ở trạng thái stopped |
| Copy private IP | Cố gắng giữ private IP source trên recovery instance khi topology cho phép |
| Operating system licensing | Chọn AWS-provided license hoặc BYOL theo OS/contract |
| Recovery mode | Chọn Optimal conversion hoặc Fast mode trong các tình huống được hỗ trợ |
| EC2 launch template | Cấu hình subnet, security groups, IAM instance profile, instance type, EBS mappings, tags và metadata options |

Lưu ý: nếu bật instance type right-sizing, lựa chọn do DRS tính có thể ghi đè instance type trong EC2 launch template. Thay đổi launch settings chỉ ảnh hưởng các drill/recovery instances khởi chạy sau đó; các instance đã chạy không tự cập nhật.

Từ tháng 08/2026, DRS giữ nguyên UEFI boot mode cho Linux source server khởi động bằng UEFI. EC2 launch template cũng hỗ trợ truyền `VolumeInitializationRate` trong block device mappings để tăng tốc EBS volume initialization khi drill/recovery.

### 8.2. Chuẩn bị operational subnet và security groups

Recovery instances thường chạy trong operational subnet riêng, tách khỏi staging subnet. Chuẩn bị trước:

- VPC, subnets ở nhiều AZ nếu workload cần HA.
- Route tables, NAT/Internet egress hoặc private endpoints.
- Security groups cho application tiers, database và administration.
- IAM instance profile cho Systems Manager, CloudWatch và ứng dụng.
- KMS permissions cho encrypted EBS volumes.
- DNS, domain join, AD/DNS servers, license servers và secrets access.
- Load balancer target groups, certificates và routing.
- EC2 quotas, instance family capacity và EBS volume quotas.

Không để recovery instance dùng production subnet một cách vô thức trong drill. Một drill có thể tạo IP/hostname trùng, gửi email thật, kết nối production database hoặc chạy scheduled jobs. Dùng isolated drill subnet và dữ liệu/test dependencies phù hợp.

### 8.3. Recovery mode: Optimal và Fast

DRS có hai recovery modes trong launch settings:

- **Optimal (default):** chạy conversion đầy đủ trước khi launch, gồm driver injection, boot configuration và filesystem adjustments. Dùng khi không chắc source tương thích EC2 hoặc khi recovery cross-platform/on-prem/cloud.
- **Fast:** bỏ qua conversion process và launch trực tiếp từ replicated snapshots, giảm thời gian recovery. Dùng cho AWS-to-AWS khi source server đã có driver và configuration tương thích EC2. Fast mode yêu cầu AWS Replication Agent version 6.42.20 trở lên theo tài liệu hiện hành.

Không chọn Fast chỉ vì muốn RTO thấp. Test từng OS/instance family/boot mode trong drill, kiểm tra boot, network và disk integrity trước khi đưa vào runbook production.

### 8.4. Post-launch actions

Post-launch actions cho phép tự động hóa các bước sau khi recovery instance boot. DRS dùng AWS Systems Manager (SSM) để chạy command hoặc Automation documents.

Các predefined actions có thể gồm:

- Enable SSM và cài SSM Agent khi cần.
- Install CloudWatch Agent.
- Create AMI từ instance.
- Configure time synchronization.
- Validate disk space.
- Check EC2 connectivity tới host/port được định nghĩa.
- Verify HTTP/HTTPS response.
- Verify tags.
- Validate volume integrity và process status.

Có thể thêm custom SSM documents để cấu hình service, update endpoint, mount filesystem, đổi application config hoặc chạy validation scripts. Post-launch actions chạy với IAM permissions tương ứng; cần kiểm tra instance profile và role của người khởi tạo automation. Không để action chứa password, token hoặc secret plaintext trong script/log.

Post-launch action không thay thế application acceptance test. Ví dụ HTTP 200 ở health endpoint chưa chứng minh payment flow, database transaction hoặc queue processing đã hoạt động đúng.

## 9. Recovery drill và kiểm thử định kỳ

### 9.1. Mục tiêu của recovery drill

Recovery drill là bài kiểm tra không gây gián đoạn source server và ongoing replication. DRS dùng quy trình launch tương tự recovery thật để kiểm tra:

- Recovery instance có boot và pass EC2 system/instance status checks không.
- Disk/filesystem có mount đúng và dữ liệu có nhất quán không.
- Network routes, DNS, security groups và dependencies có hoạt động không.
- Application services có start đúng thứ tự không.
- Người dùng/test client có truy cập được các chức năng quan trọng không.
- RPO thực tế và RTO từ lúc bắt đầu drill tới khi business test pass.
- Post-launch actions, monitoring, alert và runbook có hoạt động không.

AWS khuyến nghị thực hiện drill thường xuyên, ít nhất vài lần mỗi năm; tài liệu recovery drill khuyến nghị tối thiểu theo quý. Tần suất thực tế phụ thuộc compliance, business impact, change frequency và RTO/RPO.

### 9.2. Thực hiện drill trong Console

1. Mở AWS Elastic Disaster Recovery Console trong target Region.
2. Vào **Source servers** và xác nhận initial sync đã hoàn tất.
3. Kiểm tra replication status, lag, launch settings và post-launch actions.
4. Chọn một hoặc nhiều source servers, mở **Initiate recovery job**.
5. Chọn **Initiate recovery drill**.
6. Chọn **Use most recent data** hoặc một recovery point cụ thể.
7. Khởi chạy drill và theo dõi Recovery job history.
8. Kết nối SSH/RDP hoặc test endpoint theo test plan.
9. Kiểm tra application, database, dependencies, metrics và logs.
10. Ghi nhận thời gian, RPO/RTO, lỗi, quyết định và action items.
11. Sau khi hoàn tất, terminate recovery/drill instances và resources liên quan theo quy trình cleanup.

Có thể drill khi initial sync hoàn tất ngay cả khi source server đang có trạng thái Lag/Stall, nhưng đây không phải dấu hiệu production replication đã sẵn sàng. Muốn xác nhận DR readiness, cần giải quyết replication issues và đạt trạng thái Healthy.

### 9.3. Drill bằng AWS CLI

Ví dụ liệt kê source servers:

~~~bash
aws drs describe-source-servers \
  --region ap-southeast-1
~~~

Xem recovery snapshots của một source server:

~~~bash
aws drs describe-recovery-snapshots \
  --source-server-id s-123456789abcdefgh \
  --region ap-southeast-1
~~~

Khởi chạy drill từ latest data:

~~~bash
aws drs start-recovery \
  --source-servers sourceServerID=s-123456789abcdefgh \
  --is-drill \
  --region ap-southeast-1
~~~

Nếu muốn dùng recovery snapshot cụ thể, thêm `recoverySnapshotID` vào source server entry theo cú pháp AWS CLI hiện hành. Xác nhận đúng source server ID và recovery point trước khi chạy lệnh.

### 9.4. Cleanup sau drill

DRS không tự động terminate tất cả instances do Recovery Plan launch khi execution kết thúc, bị cancel hoặc timeout. Các drill instances tiếp tục phát sinh EC2, EBS và các phí liên quan cho tới khi được terminate. Với drill đơn lẻ, kiểm tra Recovery instances và dùng action terminate theo quy trình cleanup.

Trước khi terminate:

- Xác nhận đây là drill instance, không phải production recovery instance.
- Xác nhận application owner đã hoàn tất test.
- Thu thập logs, screenshots, metrics và test results.
- Gỡ DNS/route tạm thời và tài nguyên test liên quan.
- Xác nhận source server vẫn đang replicate bình thường.

Một lần launch thành công nhưng bỏ quên instance chạy lâu dài vừa làm sai cost estimate vừa có thể tạo rủi ro bảo mật.

## 10. Recovery Plans và phục hồi ứng dụng nhiều máy chủ

### 10.1. Vì sao cần Recovery Plans?

Một ứng dụng thường gồm nhiều tầng phụ thuộc: Active Directory/DNS, database, message broker, application servers, batch workers và web tier. Nếu khởi chạy tất cả cùng lúc, app tier có thể boot trước database hoặc authentication chưa sẵn sàng.

AWS DRS Recovery Plans được giới thiệu trong năm 2026 để định nghĩa thứ tự khởi chạy nhiều source servers. Plan có thể chạy ở chế độ Drill hoặc Recovery và theo dõi execution theo từng step.

### 10.2. Cấu trúc Recovery Plan

Một Recovery Plan thuộc một AWS account và Region, có tên duy nhất trong phạm vi đó. Theo giới hạn hiện hành:

- Tối đa 20 ordered steps trong một plan.
- Tổng cộng tối đa 100 source servers trong một plan.
- Server step có thể chứa nhiều servers; DRS khởi chạy các server trong step song song và chỉ chuyển sang step tiếp theo khi tất cả hoàn tất.
- Wait step tạm dừng từ 1 đến 120 phút; không thể là step đầu tiên.
- Server failure impact có thể đặt Critical hoặc Optional. Critical là mặc định; lỗi Critical làm step/execution thất bại, còn Optional không dừng toàn plan.
- Một source server chỉ được xuất hiện một lần trong cùng một plan, nhưng có thể nằm trong nhiều plans khác nhau.
- Mỗi plan chỉ có một execution đang chạy tại một thời điểm; nếu source server đang thuộc execution của plan khác, execution mới có thể bị từ chối cho tới khi execution hiện tại kết thúc.

### 10.3. Ví dụ thứ tự phục hồi

| Step | Loại | Server/Wait | Mục đích |
|---:|---|---|---|
| 1 | Server step | Domain controllers, DNS | Khôi phục identity và name resolution |
| 2 | Wait step | 5 phút | Chờ AD/DNS khởi tạo và replication/health checks ổn định |
| 3 | Server step | Database primary, message broker | Khởi chạy data tier |
| 4 | Wait step | 10 phút | Chờ database recovery và broker readiness |
| 5 | Server step | Application servers | Khởi chạy service layer |
| 6 | Wait step | 5 phút | Chờ health checks và dependency connections |
| 7 | Server step | Web/API tier, workers | Mở user-facing services và background processing |

Đây chỉ là ví dụ. Thứ tự thực tế phải dựa trên dependency graph, database recovery time, domain services và application startup logic. Wait step là khoảng chờ cố định; nó không tự chứng minh dịch vụ đã healthy. Kết hợp post-launch validations và người vận hành kiểm tra readiness trước traffic cutover.

### 10.4. Drill hoặc Recovery bằng plan

Quy trình:

1. Tạo Recovery Plan và thêm server/wait steps theo thứ tự.
2. Chọn Critical/Optional impact level cho từng server.
3. Review launch settings, recovery points và post-launch actions của tất cả servers.
4. Chạy plan ở chế độ **Drill** để kiểm tra trình tự và dependencies.
5. Theo dõi execution status, từng step và từng source server.
6. Xác minh ứng dụng end-to-end trước khi hoàn tất drill.
7. Terminate mọi drill instances và kiểm tra chi phí.
8. Chỉ chạy **Recovery** khi có incident decision và approval theo runbook.

Một execution là snapshot của plan tại thời điểm bắt đầu; thay đổi plan sau đó không sửa execution đang chạy. DRS không tự động chuyển DNS/traffic sau khi plan hoàn tất.
Khi execution đang chạy, operator có thể retry hoặc skip step lỗi, hoặc cancel execution. Cancel không rollback các step đã hoàn tất; phải thực hiện rollback thủ công theo runbook nếu cần.


## 11. Recovery và failover sang AWS

### 11.1. Điều kiện trước khi recovery

Không khởi chạy recovery chỉ vì source server mất ping. Trước khi quyết định failover, incident commander và application owner cần:

- Xác nhận incident và phạm vi ảnh hưởng.
- Quyết định primary environment không thể phục hồi trong RTO.
- Kiểm tra source servers có initial sync hoàn tất và recovery readiness phù hợp.
- Kiểm tra replication lag, last successful drill và last recovery result.
- Chọn recovery point phù hợp RPO và application consistency.
- Xác định recovery Region/account, VPC, subnet, security groups, IAM, KMS và EC2 capacity.
- Xác định thứ tự phụ thuộc và các bước cần làm ngoài DRS.
- Xác định người phê duyệt traffic cutover và cách rollback nếu recovery validation thất bại.

Không dùng action **Disconnect from AWS** cho source server đã launch recovery instances trong một sự cố thật. Action này chấm dứt replication resources và PIT recovery points, làm mất các lựa chọn recovery/failback cần thiết.

Khi có thể, source server nên ở trạng thái replication Healthy và Ready for recovery. Nếu sự cố khiến source mất kết nối, DRS vẫn có thể dùng dữ liệu đã replicate trước đó; cần hiểu rõ recovery point và lag cuối cùng.

### 11.2. Khởi chạy recovery instances

1. Mở AWS DRS Console và chọn source servers hoặc Recovery Plan.
2. Chọn **Initiate recovery** hoặc chạy plan ở chế độ **Recovery**.
3. Chọn latest recovery point hoặc point-in-time snapshot trước đó.
4. Khởi chạy recovery job và theo dõi từng server/job.
5. Xác minh recovery instances xuất hiện trong EC2 và trạng thái instance/system checks.
6. Xác minh volumes, filesystem, hostname, IP, security groups và IAM instance profile.
7. Chạy post-launch actions và application validation.
8. Bật EC2 termination protection sau khi launch validation pass, trước khi chuyển traffic.
9. Ghi nhận recovery instance IDs, IPs, timestamps và recovery point đã dùng.

DRS tạo recovery instances nhưng không tự chuyển DNS hoặc user traffic. Không chuyển traffic khi instance chỉ mới ở trạng thái running mà chưa qua application checks.

### 11.3. Chuyển traffic (failover)

Failover được thực hiện bên ngoài DRS bằng cơ chế routing/traffic management của tổ chức, ví dụ:

- Amazon Route 53 failover/weighted records.
- Application Load Balancer hoặc Network Load Balancer target groups.
- AWS Global Accelerator endpoint weights.
- DNS provider, BGP hoặc network routing bên ngoài AWS.
- Cập nhật service discovery/API endpoints theo application architecture.

Trước khi mở traffic:

1. Fence/disable writers ở primary để tránh split-brain và concurrent writes.
2. Kiểm tra database role/primary status và replication consistency.
3. Xác minh authentication, secrets, certificates, DNS và external dependencies.
4. Chuyển traffic theo kế hoạch, bắt đầu bằng canary/weighted traffic nếu phù hợp.
5. Theo dõi 4xx/5xx, latency, queue depth, database connections và business transactions.
6. Thông báo stakeholder và cập nhật incident timeline.

Nếu primary vẫn ghi dữ liệu trong lúc recovery environment cũng nhận writes, hai phía có thể diverge. Cần xác định rõ write authority và fencing strategy trước cutover.

### 11.4. Sau failover

- Xác nhận các luồng nghiệp vụ quan trọng hoạt động.
- Kiểm tra scheduled jobs, batch processing, email/payment integrations và downstream services.
- Tăng capacity theo nhu cầu nhưng giữ quota/budget controls.
- Tạo backup mới từ recovery environment theo policy.
- Giữ lại logs, snapshots và event evidence theo incident retention.
- Cập nhật DNS TTL, runbook và contact tree nếu cần.
- Không terminate recovery instances khi chúng đang là production primary.

## 12. Failback về hạ tầng ban đầu

### 12.1. Khi nào thực hiện failback?

Failback đưa workload đang chạy ở AWS recovery environment trở lại primary infrastructure sau khi primary đã được sửa chữa hoặc thay thế. Chỉ failback khi:

- Root cause đã được xử lý và primary environment ổn định.
- Network, compute, storage, security và identity dependencies đã sẵn sàng.
- Đã quyết định nguồn dữ liệu authoritative và thời điểm freeze writes.
- Có đủ bandwidth cho reverse replication.
- Có kế hoạch chuyển traffic, rollback và giữ recovery instances cho tới khi xác nhận hoàn tất.

Không failback chỉ để "trở về như cũ" nếu recovery environment đang hoạt động ổn định và business không yêu cầu. Việc chuyển ngược có thể tạo downtime và rủi ro dữ liệu nếu không được diễn tập.

### 12.2. Các phương thức failback

| Source infrastructure ban đầu | Cơ chế failback |
|---|---|
| On-premises physical/virtual server | Dùng AWS DRS Failback Client ISO hoặc DRS failback automation theo hướng dẫn |
| AWS cùng account | Start reverse replication từ protected recovery instance |
| AWS cross-account | Start reverse replication từ recovery instance trong failover account với trusted account roles |
| Other cloud | Cơ chế phụ thuộc provider và network; kiểm tra hướng dẫn cụ thể |

Với on-premises, Failback Client được boot trên máy chủ đích và kết nối với DRS để nhận dữ liệu từ recovery instance. Với AWS-to-AWS, reverse replication gửi các thay đổi mới từ recovery instance về source environment.

### 12.3. Quy trình failback tổng quát

1. Xác minh source infrastructure đã sẵn sàng nhận dữ liệu.
2. Xác minh connectivity, credentials, security groups và port 443/1500.
3. Khởi tạo failback/reverse replication theo loại source.
4. Theo dõi reverse replication tới khi trạng thái Ready hoặc Ready with lag theo hướng dẫn của DRS.
5. Chọn thời điểm freeze writes trên recovery environment.
6. Chờ final synchronization hoàn tất để giảm data loss.
7. Launch failback instances hoặc boot source servers theo quy trình.
8. Kiểm tra OS, volumes, application, database consistency và dependencies.
9. Chuyển traffic về primary bằng DNS/routing ngoài DRS.
10. Theo dõi hệ thống sau cutover và xác nhận business transactions.
11. Bật replication lại từ failed-back servers về AWS để duy trì DR protection.
12. Chỉ cleanup recovery instances/resources sau khi đã xác nhận source là primary và replication hai chiều/chiều bảo vệ mới hoạt động đúng.

### 12.4. Network và lỗi thường gặp khi failback

Failback cũng cần TCP 443 tới DRS endpoints và TCP 1500 giữa replication source/target. Với failback client hoặc recovery instance, security group và firewall phải cho phép đúng chiều traffic theo topology. Trong một số AWS failback flows, inbound TCP 1500 trên recovery instance security group cần được mở. Nếu Failback Client kết nối qua public Internet (không có VPN/Direct Connect), recovery instance cần public IP; EC2 launch template của DRS mặc định tắt auto-assign public IP, vì vậy phải cấu hình rõ nếu dùng đường public.

Các lỗi thường gặp:

- Agent trên recovery instance không kết nối được DRS.
- Failback Client không được associate hoặc không nhận credentials.
- Port 1500 bị chặn ở firewall/security group/NACL.
- TLS inspection làm gián đoạn kết nối replication.
- Clock skew làm credential validation thất bại.
- Source instance thiếu tag hoặc launch setting cần thiết cho phép launch back into source instance.
- Reverse replication không hội tụ do write rate lớn hơn bandwidth.

Không tự xóa recovery instance khi reverse replication chưa hoàn tất. Nếu lỗi lặp lại, kiểm tra DRS troubleshooting logs và mở AWS Support case với error code, source server ID, job ID và thời điểm xảy ra.

### 12.5. Cleanup sau failback

Sau khi primary đã nhận workload và DRS replication đã được thiết lập lại:

- Xác nhận không còn hai source server records đại diện cho cùng workload.
- Kiểm tra agent trên failed-back server và trạng thái replication.
- Xóa recovery resources không còn cần thiết theo inventory.
- Xóa temporary security group/routing rules.
- Giữ snapshots/logs theo retention policy.
- Xác nhận KMS keys vẫn tồn tại cho dữ liệu còn cần restore.
- Cập nhật CMDB, recovery plan, RTO/RPO measurements và post-incident review.

## 13. Multi-account, multi-Region và DR ở quy mô lớn

### 13.1. Region isolation

DRS được initialize riêng ở từng target Region. Để bảo vệ khỏi sự cố Region, source replication cần gửi dữ liệu sang Region khác với primary. Recovery resources như VPC, subnet, security groups, KMS keys, AMIs, IAM roles, DNS và application dependencies cũng phải sẵn sàng trong Region đích.

Không nhầm Availability Zone redundancy với Region-level DR. DRS target Region cần có capacity và quotas đủ để khởi chạy toàn bộ recovery fleet trong cùng thời điểm.

### 13.2. Multi-account staging và target accounts

DRS giới hạn mặc định 300 concurrently replicating source servers cho mỗi AWS account mỗi Region. Với môi trường lớn hơn, có thể dùng nhiều staging accounts và một hoặc nhiều target accounts. AWS mô tả khả năng khôi phục tới 3.000 source servers vào một target account bằng cách dùng nhiều staging accounts.

Mô hình này giúp:

- Tách replication infrastructure khỏi production recovery account.
- Chia billing, ownership và security boundaries.
- Mở rộng số lượng source servers vượt giới hạn một staging account.
- Phục hồi nhiều staging accounts về một recovery account tập trung.
- Tạo nhiều target accounts cho production, test hoặc business units.

Cần cấu hình trusted accounts/roles, chia sẻ EBS encryption key phù hợp và network access. Target account dùng role để truy cập source server metadata/resources ở staging accounts. Review IAM trust policy, KMS key policy, EBS snapshot sharing và resource ownership.

### 13.3. Quotas cần đưa vào capacity planning

Các giới hạn DRS hiện hành quan trọng:

| Quota | Default limit |
|---|---:|
| Concurrently replicating source servers/account/Region | 300 |
| Source servers trong một recovery job | 100 |
| Source servers trên tất cả active jobs | 500 |
| Concurrent jobs in progress/Region | 20 |
| Recovery Plan steps | 20 |
| Source servers trong một Recovery Plan | 100 |
| Volume size/source server | 64 TiB mỗi volume khi dùng gp3 staging disk; 16 TiB với các lựa chọn staging khác |
| Volumes/source server | 63 |

Quota có thể khác theo API/resource type và thay đổi theo thời gian. Kiểm tra AWS Service Quotas và DRS endpoints and quotas trước khi triển khai. Không giả định EC2 quotas, EBS volume quotas, IP address capacity và DRS quotas sẽ tự tăng theo nhau.

### 13.4. Disaster recovery at scale

Với hàng trăm hoặc hàng nghìn servers:

- Phân nhóm theo application, dependency và business criticality.
- Dùng Recovery Plans cho các nhóm phụ thuộc trong giới hạn plan.
- Xác định thứ tự failover giữa nhiều plans.
- Giới hạn concurrency để không làm cạn EC2 capacity hoặc EBS throughput.
- Theo dõi source servers Stalled, Disconnected, Lag và chưa drill.
- Tạo dashboard tập trung qua AWS Organizations/cross-account IAM.
- Dùng IaC để tạo VPC, subnet, security groups, route tables, IAM và DNS.
- Kiểm tra quotas ở tất cả target Regions.
- Diễn tập từng nhóm nhỏ trước khi chạy full-scale recovery.



## 14. Security, IAM và bảo vệ recovery data

### 14.1. Shared responsibility

AWS bảo vệ hạ tầng dịch vụ DRS và cung cấp các cơ chế encryption/identity integration. Khách hàng chịu trách nhiệm về:

- Ai có quyền initialize DRS, cài agent, sửa replication settings và khởi chạy recovery.
- Network path, firewall, VPC, security groups và subnet isolation.
- IAM roles/instance profiles cho recovery instances và post-launch actions.
- KMS key policies, EBS encryption và key lifecycle.
- Bảo vệ snapshots, logs và recovery credentials.
- Kiểm tra application security, patching, secrets và data access sau recovery.

### 14.2. IAM và service-linked role

DRS sử dụng service-linked role `AWSServiceRoleForElasticDisasterRecovery` với trust service principal `drs.amazonaws.com` để thực hiện các thao tác AWS cần thiết thay mặt người dùng. Role được tạo tự động khi cấu hình replication template.

Tách quyền theo nhiệm vụ:

| Role | Quyền nên có |
|---|---|
| DRS administrator | Initialize service, quản lý replication/launch settings, source servers và recovery plans |
| Agent installer | Chỉ dùng policy cài AWS Replication Agent |
| Recovery operator | Khởi chạy drill/recovery và theo dõi job |
| Application validator | Truy cập recovery instances/test endpoints để xác nhận ứng dụng |
| Key administrator | Quản lý KMS policy/rotation/deletion, không mặc định có quyền đọc dữ liệu |
| Auditor | Đọc CloudTrail, DRS state và reports; không có quyền thay đổi protection |

Dùng IAM Identity Center/role-based access, MFA và temporary credentials. Hạn chế quyền `drs:StartRecovery`, `drs:StartFailback` và quyền terminate EC2 theo approval workflow. Cài agent có thể bắt đầu phát sinh phí ngay khi source server được đăng ký; kiểm soát ai có quyền này.

### 14.3. Encryption và KMS

Replication data được mã hóa khi truyền. Staging EBS volumes và snapshots có thể dùng AWS managed key hoặc customer managed KMS key. Với CMK, cần bảo đảm DRS/service role và recovery principals có quyền cần thiết.

AWS DRS chỉ lưu configuration/log data trong encrypted service database; replicated data được lưu trong VPC của khách hàng ở staging area và mã hóa khi truyền. Vì vậy, khách hàng vẫn phải bảo vệ staging VPC, EBS volumes/snapshots và KMS key như các dữ liệu nhạy cảm khác.

Nếu dùng cross-account staging/target accounts, chia sẻ encryption key theo hướng dẫn multi-account DRS. Key policy ở account sở hữu key và identity policy ở account gọi phải cho phép đúng operations.

Không disable/schedule deletion KMS key còn bảo vệ staging snapshots, recovery volumes hoặc backup. Key bị xóa vĩnh viễn có thể làm ciphertext không thể giải mã.

### 14.4. Bảo vệ PIT snapshots và chống ransomware

DRS liên tục replicate block changes, vì vậy file bị xóa, database bị corrupt hoặc ransomware encrypt file có thể được replicate sang staging. PIT snapshots cho phép quay về recovery point trước sự cố nếu retention còn giữ.

Tuy nhiên, PIT snapshots của DRS không phải immutable backup độc lập. Một attacker chiếm quyền AWS account đủ mạnh có thể cố xóa snapshots, dừng replication hoặc disable KMS key. Nên:

- Dùng least privilege cho DRS, EC2, EBS snapshot và KMS APIs.
- Tách quyền vận hành DRS khỏi quyền xóa snapshot/key.
- Dùng SCP/permissions boundary hoặc controls phù hợp để ngăn destructive actions trái phép.
- Lưu backup độc lập bằng AWS Backup với vault policies/Backup Vault Lock khi cần immutability.
- Giữ bản backup ngoài account/Region vận hành chính theo threat model.
- Thực hiện restore test từ backup độc lập; đừng chỉ kiểm tra replication status.

### 14.5. Bảo vệ recovery instances

- Dùng private subnets khi không cần public ingress.
- Dùng security groups tối thiểu và chỉ mở administration từ bastion/SSM.
- Bật IMDSv2 trong EC2 launch template khi ứng dụng tương thích.
- Gắn instance profile đúng scope, không tái sử dụng role admin.
- Bảo vệ secrets bằng Secrets Manager/Parameter Store và rotation.
- Tách drill subnet khỏi production để ngăn kết nối nhầm.
- Bật termination protection cho recovery instances production sau launch validation.
- Ghi log và monitor mọi thay đổi security group, route, IAM và DNS.

## 15. Monitoring, CloudWatch, EventBridge và CloudTrail

### 15.1. Theo dõi trạng thái source server

Trên Source servers page, theo dõi hai trạng thái chính:

| Recovery readiness | Ý nghĩa |
|---|---|
| Ready | Có thể launch drill/recovery theo trạng thái hiện tại |
| Ready with lag | Có thể launch nhưng recovery point bị trễ; cần xem lag duration |
| Initial sync | Đang sao chép lần đầu, chưa thể coi là DR-ready |
| Disconnected | Agent không liên lạc được DRS |
| Not ready | Có lỗi nghiêm trọng như stall hoặc launch prerequisites |

Data replication status gồm:

- **Initiating:** DRS đang bắt đầu cấu hình replication.
- **Initial sync:** đang sao chép block lần đầu.
- **Rescanning:** đọc lại disk/block theo yêu cầu.
- **Healthy:** replication ổn định và source server sẵn sàng khởi chạy recovery job.
- **Lag:** replication bị trễ; console hiển thị thời gian lag.
- **Stalled:** replication dừng do lỗi cần can thiệp.
- **Disconnected:** agent đã mất kết nối với DRS.

Một source server có thể Ready with lag nhưng vẫn chưa đạt RPO mục tiêu. Cần theo dõi lag duration và backlog thay vì chỉ nhìn trạng thái Ready.

### 15.2. CloudWatch metrics

DRS cung cấp metrics để theo dõi replication và recovery readiness. Các metric quan trọng gồm:

| Metric | Ý nghĩa |
|---|---|
| `TotalSourceServerCount` | Tổng số source servers |
| `LagDuration` | Tuổi của consistent snapshot mới nhất, tính bằng giây |
| `Backlog` | Dung lượng dữ liệu đã ghi ở source nhưng chưa đồng bộ tới AWS, tính bằng bytes |
| `DurationSinceLastSuccessfulRecoveryLaunch` | Thời gian từ lần drill/recovery launch thành công gần nhất |
| `ElapsedReplicationDuration` | Tổng thời gian source server đã replicate |

Tạo dashboard theo application, account và Region. Đặt alarm cho lag/backlog vượt ngưỡng RPO, stalled/disconnected, thời gian từ successful drill quá lâu và số recovery launch failures.

### 15.3. EventBridge events

DRS gửi service events trực tiếp tới EventBridge và gửi API events qua CloudTrail. Các event trực tiếp có thể gồm:

- `DRS Source Server Launch Result`
- `DRS Source Server Data Replication Stalled Change`
- `DRS PIT Snapshot Taken`
- `DRS Recovery Instance Failback State Change`
- `DRS Source Network Protection Status Change`
- `DRS Source Network Recovery Result`

Có thể tạo EventBridge rule theo `source = aws.drs` và `detail-type` để route event tới SNS, Lambda, SQS hoặc incident workflow. Event delivery là best effort; cần kết hợp polling/API và dashboard nếu yêu cầu completeness.

Ví dụ event pattern cho replication stalled:

~~~json
{
  "source": ["aws.drs"],
  "detail-type": ["DRS Source Server Data Replication Stalled Change"]
}
~~~

Rule có thể route event tới SNS topic để on-call nhận cảnh báo. Không dùng event notification làm nguồn trạng thái duy nhất; xác nhận lại source server trong DRS console/API.

### 15.4. CloudTrail audit

CloudTrail ghi nhận DRS API calls từ Console, CLI và SDK. Dùng để truy vết:

- Ai thêm/xóa source server hoặc stop/start replication.
- Ai thay đổi replication/launch settings và recovery plans.
- Ai khởi chạy drill/recovery/failback.
- Ai thay đổi IAM roles, KMS policies, security groups, route tables và EC2 launch templates.
- Ai terminate recovery instances hoặc xóa snapshots.

Dùng organization trail/multi-Region trail và lưu log ở account audit riêng nếu cần. Đảm bảo retention và access control cho CloudTrail logs.

## 16. Troubleshooting và xử lý replication errors

### 16.1. Bảng triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Agent installer không kết nối | TCP 443 bị chặn, sai Region, proxy sai | Kiểm tra route/firewall/proxy và DRS endpoint |
| Source server Disconnected | Agent service dừng, mất mạng, credentials/identity lỗi | Kiểm tra agent service, DNS, TCP 443 và logs |
| Replication server không nhận data | TCP 1500 bị chặn, security group/NACL sai | Kiểm tra source outbound và staging inbound TCP 1500 |
| Replication Lag tăng | Write rate tăng, bandwidth thiếu, disk IOPS thấp | Đo write throughput, tăng bandwidth/headroom, đánh giá EBS type |
| NOT_CONVERGING | Data change rate vượt khả năng replication | Tăng network capacity, staging throughput hoặc điều chỉnh throttle |
| Stalled | Lỗi agent, network, replication server hoặc storage | Đọc replication status details và agent logs |
| Recovery launch fail | Instance type/AMI/boot mode/license/subnet/SG không phù hợp | Review EC2 launch template, quotas, Marketplace license và conversion mode |
| Instance boot nhưng app không chạy | Dependencies, DNS, secret, disk mount hoặc startup order sai | Kiểm tra post-launch actions, logs, Recovery Plan và application validation |
| Failback Client không connect | Port 443/1500, credentials hoặc source server không tồn tại | Kiểm tra network, client pairing, IAM và source server state |
| Reverse replication thất bại | Recovery agent không hoạt động hoặc thiếu network path | Kiểm tra service trên recovery instance, SG và route |
| Credential retrieval failed | Clock skew hoặc role/trust policy sai | Đồng bộ thời gian, kiểm tra trusted account roles và IAM |
| PIT recovery point thiếu | Retention quá ngắn hoặc snapshots bị xóa | Kiểm tra PIT policy, CloudTrail và snapshot protection |

### 16.2. Xử lý replication không hội tụ

Khi status `NOT_CONVERGING` hoặc lag tăng liên tục:

1. Kiểm tra agent có đang chạy và source server có connected không.
2. Kiểm tra TCP 1500 từ source tới replication server.
3. Đo average/peak write throughput của tất cả servers cùng network path.
4. So sánh với available bandwidth; cần tối thiểu tổng write rate và headroom.
5. Kiểm tra replication server CPU, memory và EBS throughput/IOPS.
6. Kiểm tra disk type; có thể cần đổi staging disk type sang loại throughput phù hợp.
7. Xem replication lag và ETA sau khi thay đổi.
8. Nếu lỗi không hết, thu thập agent logs và mở AWS Support case.

Sau reboot hoặc agent/service restart, DRS có thể rescan disk và lag tăng tạm thời. Không kết luận network thiếu capacity chỉ từ một spike ngắn; xem trend và backlog có giảm hay không.

### 16.3. Lỗi port 1500 và TLS inspection

Lỗi `Connection refused`, `connect timed out` hoặc `No route to host` thường liên quan firewall, route table, NACL hoặc security group. Kiểm tra:

- Source server outbound TCP 1500.
- Replication server inbound TCP 1500.
- Network ACL inbound/outbound và ephemeral return ports.
- Source/replication server private/public IP routing.
- NAT gateway, DNS resolution và VPC endpoint policies.
- Không có proxy/firewall decrypt hoặc modify TLS session trên port 1500.

### 16.4. Lỗi recovery launch

Khi launch thất bại, kiểm tra theo thứ tự:

1. Recovery job history và error code cụ thể.
2. Source server Ready/Healthy và recovery point còn tồn tại.
3. EC2 launch template: instance type, subnet, security group, IAM profile, disk mapping, metadata options.
4. EC2 quota, instance capacity, EBS volume limits và IP address capacity.
5. OS boot mode, driver compatibility, Marketplace licensing và BYOL restrictions.
6. KMS key state và decrypt permissions.
7. Post-launch actions/SSM permissions và SSM agent connectivity.


## 17. Chi phí AWS Elastic Disaster Recovery

### 17.1. Phí dịch vụ DRS

Theo bảng giá AWS DRS được kiểm tra ngày 20/11/2026, giá dịch vụ tiêu chuẩn công bố là **0,028 USD cho mỗi source server mỗi giờ**. DRS dùng usage-based pricing, không có upfront fee và không yêu cầu minimum fee. Phí DRS bao gồm continuous replication, test launches, recovery launches và point-in-time recovery theo mô hình pricing của dịch vụ. Hourly DRS rate giống nhau bất kể Region đích, số lượng disks, dung lượng storage hoặc số lần drill/recovery launch; các chi phí hạ tầng bổ sung như EBS/EC2 vẫn phụ thuộc Region và cấu hình.

Giá công bố có thể được AWS cập nhật; currency, tax và các chi phí tài nguyên bổ sung phụ thuộc billing setup/Region. Luôn xác minh AWS DRS Pricing và AWS Pricing Calculator trước khi lập budget.

### 17.2. Chi phí hạ tầng bổ sung

Phí DRS theo source server không bao gồm toàn bộ tài nguyên AWS được sử dụng. Có thể phát sinh thêm:

- Amazon EBS staging volumes theo dung lượng source disks.
- EBS snapshots theo PIT retention và thay đổi dữ liệu.
- EC2 replication server instances trong staging area.
- EC2 conversion server instances được tạo trong quá trình drill/recovery launch; chúng chỉ chạy trong thời gian conversion nhưng vẫn phát sinh EC2 usage charges.
- EC2 drill/recovery instances trong thời gian chạy.
- EBS volumes của drill/recovery instances.
- Data transfer/network charges theo đường replication và traffic.
- NAT Gateway, VPN, Direct Connect hoặc các dịch vụ network khác.
- CloudWatch, EventBridge, CloudTrail, SSM và các service integrations theo usage.
- AWS Backup hoặc storage/archive độc lập nếu được cấu hình.

Drill instances đang chạy tiếp tục tính EC2/EBS charges. Recovery Plans không tự terminate instances sau khi execution kết thúc; cần cleanup thủ công hoặc automation an toàn.

### 17.3. Dự toán chi phí

Ví dụ 10 source servers được replicate liên tục trong 30 ngày:

\[
10 \times 24 \times 30 \times 0.028 = 201.60\ USD
\]

Đây chỉ là phí DRS service theo hourly source-server rate; chưa bao gồm EC2 replication servers, EBS volumes/snapshots, data transfer và drill/recovery resources.

Dự toán đầy đủ cần tính:

1. Số source servers và số giờ replication.
2. Dung lượng từng source disk và số lượng disks.
3. Write rate/change rate ảnh hưởng snapshot storage.
4. PIT retention (1–365 ngày).
5. Replication server instance types và staging EBS types.
6. Số lần drill/thời gian chạy drill instances.
7. Số lượng EC2 recovery instances và thời gian chạy sau failover.
8. Data transfer và private connectivity.
9. Multi-account/multi-Region overhead.
10. Backup immutable/long-term retention riêng.

### 17.4. Tối ưu chi phí an toàn

- Dùng Auto EBS volume type selection khi phù hợp để cân bằng throughput và storage cost.
- Chọn PIT retention theo business RPO/compliance thay vì đặt dài nhất mặc định.
- Throttle bandwidth chỉ khi cần bảo vệ production network; throttle quá mức có thể làm lag tăng và phá RPO.
- Terminate drill instances sau khi hoàn tất validation.
- Xóa temporary resources và security groups theo inventory.
- Giữ staging capacity phù hợp write rate; tối ưu quá mức có thể làm replication không hội tụ.
- Đánh giá cost của recovery instances dựa trên RTO và thời gian workload cần chạy tại AWS.
- Dùng AWS Backup cho backup/retention độc lập thay vì kéo dài PIT snapshots ngoài nhu cầu.

**Cảnh báo stop replication:** khi stop replication của source server, DRS ngừng ongoing replication và staging infrastructure charges, đồng thời xóa các saved PIT snapshots của server. Dữ liệu thay đổi sau đó không còn được bảo vệ và các recovery points cũ không còn khả dụng. Chỉ stop replication khi decommission/retire workload và đã xác nhận có backup khác.

## 18. Runbook DR mẫu cho một ứng dụng ba tầng

Giả sử ứng dụng gồm database, application servers và web/API tier. Mục tiêu mẫu: RPO 1 phút, RTO 30 phút. Các giá trị phải được business owner xác nhận và kiểm chứng qua drill.

### 18.1. Trước sự cố

- DRS replication status của tất cả source servers ở Healthy.
- Recovery readiness là Ready và có successful drill gần nhất.
- PIT retention đáp ứng yêu cầu rollback.
- Recovery Plan có thứ tự database → application → web/API.
- Recovery VPC/subnets/security groups và IAM roles đã sẵn sàng.
- Route 53/Global Accelerator/traffic management có quy trình cutover.
- KMS keys, secrets, certificates, DNS, AD và external dependencies đã kiểm tra.
- On-call contacts, incident commander và application owners được xác định.

### 18.2. Khi tuyên bố disaster

1. Incident commander xác nhận phạm vi và tuyên bố failover.
2. Application owner xác định recovery point theo RPO và thời điểm corruption nếu có.
3. Network owner xác nhận recovery VPC và routing sẵn sàng.
4. DRS operator chạy Recovery Plan ở chế độ Recovery.
5. Database tier launch trước và được kiểm tra consistency/readiness.
6. Application tier launch sau khi database sẵn sàng.
7. Web/API tier launch sau khi service dependencies pass.
8. Bật termination protection cho recovery instances production.
9. Application owner chạy smoke tests và business transactions.
10. Network owner chuyển traffic bằng DNS/Global Accelerator/traffic manager.
11. Incident commander xác nhận service restored và theo dõi SLO.

### 18.3. Sau khi failover

- Đặt recovery environment làm authoritative writer.
- Chặn writes ở primary để tránh split-brain.
- Kiểm tra backup, monitoring, alerting và capacity.
- Theo dõi error rate, latency, database connections, queue depth và data integrity.
- Ghi lại recovery timestamps, recovery point, RPO/RTO thực tế và các sai lệch.
- Chuẩn bị failback plan nhưng không thực hiện cho tới khi primary ổn định.

### 18.4. Khi failback

1. Sửa chữa/khôi phục primary environment và xác minh network/security.
2. Khởi tạo reverse replication từ recovery environment.
3. Chờ reverse replication Ready/Healthy theo cơ chế source type.
4. Lên lịch maintenance/freeze writes.
5. Chờ final sync và kiểm tra data consistency.
6. Khởi chạy/boot workload tại primary và kiểm thử.
7. Chuyển traffic về primary.
8. Xác minh replication bảo vệ lại primary về AWS.
9. Cleanup recovery resources không còn dùng và cập nhật CMDB/runbook.

## 19. Bài thực hành trên AWS sandbox

Các lab cần dùng account và source servers do người học quản lý. Không cài agent lên production server hoặc stop replication của workload thật trong bài lab.

### 19.1. Lab A — Khởi tạo DRS và thêm source server

1. Chọn một AWS Region được DRS hỗ trợ.
2. Initialize DRS và tạo staging subnet riêng.
3. Kiểm tra default replication template, EBS encryption và PIT policy.
4. Tạo IAM principal chỉ có agent installation policy.
5. Chuẩn bị một Linux/Windows test server tương thích.
6. Kiểm tra TCP 443 và TCP 1500 trước khi cài agent.
7. Cài agent và xác nhận source server xuất hiện trong DRS console.
8. Theo dõi initial sync đến khi Healthy.

### 19.2. Lab B — Replication lag và bandwidth

1. Ghi nhận average write rate của source server.
2. Kiểm tra replication lag, backlog và ETA.
3. Tạo workload ghi dữ liệu trong giới hạn sandbox.
4. Quan sát lag/backlog tăng và giảm theo bandwidth.
5. Thử network bandwidth throttling trong sandbox.
6. Khôi phục bandwidth đủ cao và xác nhận replication hội tụ.
7. Ghi lại tác động tới RPO và chi phí.

Không tạo workload ghi quá mức làm ảnh hưởng máy chủ hoặc account dùng chung.

### 19.3. Lab C — Recovery drill và post-launch actions

1. Cấu hình launch template vào isolated drill subnet.
2. Chọn instance type, security groups, IAM profile và IMDSv2.
3. Bật post-launch actions để enable SSM và CloudWatch Agent.
4. Khởi chạy recovery drill từ latest data.
5. Kiểm tra EC2 status checks, disk mounts, SSH/RDP và application health.
6. Đo thời gian launch và validation.
7. Terminate drill instances/resources sau khi thu thập kết quả.
8. Xác nhận source replication vẫn Healthy.

### 19.4. Lab D — Recovery Plan cho database và application

1. Thêm ít nhất hai source servers test vào DRS.
2. Tạo Recovery Plan với database server step trước application server step.
3. Thêm wait step phù hợp và đặt Critical/Optional impact level.
4. Chạy plan ở chế độ Drill.
5. Kiểm tra thứ tự launch, dependencies và execution history.
6. Kiểm tra application test sau khi tất cả steps hoàn tất.
7. Terminate toàn bộ drill instances vì Recovery Plan không tự cleanup.
8. Sửa plan dựa trên kết quả drill và chạy lại.

### 19.5. Lab E — Failback tabletop và security review

1. Dùng sơ đồ source → staging → recovery đã xây dựng.
2. Diễn tập failover: chọn recovery point, launch recovery và traffic cutover.
3. Diễn tập failback: source readiness, reverse replication, freeze writes và traffic return.
4. Review IAM roles, KMS key policies, snapshot delete permissions và CloudTrail.
5. Tạo EventBridge rule cho DRS replication stalled event.
6. Gửi event tới SNS test topic và xác minh on-call workflow.
7. Ghi lại recovery gaps, owner và remediation deadline.

## 20. Checklist đánh giá DR readiness trước production

### Source inventory và replication

- [ ] Tất cả source servers nằm trong OS/architecture được hỗ trợ?
- [ ] Disk/volume limits không vượt 64 TiB/volume (gp3 staging disk) và 63 volumes/server?
- [ ] Agent cài đúng Region, đúng architecture và đang chạy?
- [ ] Initial sync hoàn tất và replication status Healthy?
- [ ] Average/peak write rate đã đo ít nhất 24 giờ?
- [ ] Bandwidth có headroom phù hợp, replication lag/backlog không tăng kéo dài?
- [ ] Disk mới được tự động replicate hoặc có quy trình add disk?

### Network và staging

- [ ] TCP 443 tới DRS/S3/EC2 endpoints được mở?
- [ ] TCP 1500 giữa source và replication server được mở đúng chiều?
- [ ] Firewall/proxy không TLS-inspect replication stream?
- [ ] Staging subnet có CIDR, route, DNS, SG/NACL và endpoint policy đúng?
- [ ] Private IP routing/VPN/Direct Connect đã được kiểm thử nếu sử dụng?
- [ ] Operational/recovery subnet đã chuẩn bị riêng?

### Recovery launch và orchestration

- [ ] EC2 launch template có subnet, SG, IAM role, instance type và disk mappings đúng?
- [ ] Recovery mode Optimal/Fast phù hợp source architecture?
- [ ] KMS keys, IAM, license và EC2 quotas đã xác minh?
- [ ] Post-launch actions đã test và không chứa secrets plaintext?
- [ ] Recovery Plan phản ánh dependency graph và Critical/Optional server?
- [ ] Wait steps được kiểm chứng bằng health checks/validation?
- [ ] Đã có successful drill gần đây và drill cleanup?

### Failover/failback

- [ ] RPO/RTO được business owner xác nhận và đo thực tế?
- [ ] Recovery point selection và data consistency có runbook?
- [ ] Primary fencing/split-brain prevention đã rõ?
- [ ] Traffic cutover ngoài DRS có owner và procedure?
- [ ] Recovery instances production có termination protection?
- [ ] Failback đã được diễn tập cho loại source tương ứng?
- [ ] Sau failback, source được bảo vệ lại và không có duplicate server entity?

### Security, monitoring và cost

- [ ] IAM least privilege, agent credentials và service-linked role được kiểm soát?
- [ ] EBS encryption/KMS policy và snapshot deletion controls được review?
- [ ] Có backup immutable độc lập khi yêu cầu?
- [ ] CloudWatch metrics, EventBridge events và CloudTrail audit được tích hợp?
- [ ] Alert cho Lag, Backlog, Stalled, Disconnected và failed launches?
- [ ] Dự toán DRS hourly fee cùng EC2/EBS/networking costs?
- [ ] PIT retention phù hợp và có owner?
- [ ] Stop replication/decommission có approval và backup verification?

## 21. Câu hỏi tự đánh giá

1. AWS DRS giải quyết vấn đề gì trong disaster recovery?
2. RPO và RTO khác nhau thế nào?
3. Failover khác recovery launch ra sao?
4. Vì sao DRS không tự chuyển DNS/traffic?
5. Recovery drill ảnh hưởng source server và ongoing replication không?
6. Source server, replication agent và staging area có vai trò gì?
7. TCP 443 và TCP 1500 được dùng cho luồng nào?
8. Vì sao không được TLS-inspect TCP 1500 replication stream?
9. Initial sync khác continuous replication thế nào?
10. Vì sao write throughput phải thấp hơn available bandwidth?
11. Tại sao AWS khuyến nghị thêm 20% bandwidth headroom?
12. Recovery Point Objective điển hình của DRS là bao nhiêu và điều kiện nào ảnh hưởng?
13. DRS có thay thế AWS Backup hoặc immutable backup không?
14. PIT policy giữ các recovery points theo lịch nào?
15. Daily PIT retention có thể cấu hình từ bao nhiêu đến bao nhiêu ngày?
16. Vì sao DRS snapshots có thể bị ảnh hưởng khi AWS account bị compromise?
17. Default replication settings có tự cập nhật source servers đã tồn tại không?
18. EBS volume type ảnh hưởng replication cost/performance thế nào?
19. Launch settings gồm DRS launch settings và EC2 launch template ra sao?
20. Recovery mode Optimal và Fast khác nhau ở đâu?
21. Khi nào Fast mode phù hợp và yêu cầu agent version nào?
22. Post-launch actions dùng AWS Systems Manager để làm gì?
23. Recovery Plans giải quyết vấn đề nào khi ứng dụng có nhiều server dependencies?
24. Recovery Plan có giới hạn bao nhiêu steps, servers và wait time?
25. Critical và Optional impact levels khác nhau thế nào?
26. Vì sao Recovery Plan drill instances phải được terminate thủ công?
27. Failback về on-premises khác AWS-to-AWS failback ra sao?
28. Vì sao cần freeze writes trước final failback sync?
29. DRS hỗ trợ bao nhiêu concurrently replicating source servers mỗi account/Region?
30. Multi-staging accounts giúp mở rộng quy mô ra sao?
31. Những CloudWatch metrics nào giúp phát hiện replication lag/backlog?
32. EventBridge có thể phát hiện những DRS service events nào?
33. Làm gì khi replication status NOT_CONVERGING?
34. Tại sao không nên stop replication chỉ để tiết kiệm phí nếu chưa có backup khác?
35. Những bước nào cần có trong runbook failover/failback?
36. Vì sao phải đo RPO/RTO bằng recovery drill thay vì chỉ dựa vào tài liệu dịch vụ?

### Định hướng đáp án

- **RPO/RTO:** RPO là mức mất dữ liệu chấp nhận được; RTO là thời gian khôi phục dịch vụ. DRS có thể đạt RPO sub-second khi replication khỏe mạnh, nhưng cần đo thực tế.
- **Architecture:** Agent gửi block changes tới replication server trong staging subnet; EBS volumes/PIT snapshots là recovery data; DRS launch EC2 instances.
- **Ports:** TCP 443 cho DRS/S3/EC2 API và control plane; TCP 1500 cho replication stream, mã hóa TLS 1.2.
- **Recovery:** Drill kiểm tra không gián đoạn source; Recovery tạo instance phục hồi thật; failover/traffic redirect do tổ chức thực hiện ngoài DRS.
- **Recovery Plans:** Server steps chạy song song trong nhóm và tuần tự giữa steps; wait step là khoảng chờ; Critical/Optional điều khiển failure behavior.
- **Failback:** Reverse replication đưa thay đổi từ recovery về source; freeze writes và final sync giúp tránh mất dữ liệu; sau cutover phải bảo vệ lại source.
- **Security/cost:** DRS snapshots không thay backup immutable; IAM/KMS/CloudTrail cần bảo vệ; DRS hourly fee chưa bao gồm EC2/EBS/network usage.


## 22. Tài liệu AWS chính thức

1. [What is AWS Elastic Disaster Recovery?](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html) — Tổng quan kiến trúc, replication và recovery.
2. [Getting started with AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/getting-started.html) — Quy trình khởi tạo Region, cài agent, initial sync, drill và recovery.
3. [AWS DRS best practices](https://docs.aws.amazon.com/drs/latest/userguide/best_practices_drs.html) — Planning, drilling, monitoring, recovery, failback và security.
4. [AWS DRS network requirements](https://docs.aws.amazon.com/drs/latest/userguide/Network-Requirements.html) — TCP 443/1500, TLS và network paths.
5. [Verifying network connectivity](https://docs.aws.amazon.com/drs/latest/userguide/verifying-network-connectivity.html) — Kiểm tra port, route, security group và NACL.
6. [Agent installation prerequisites](https://docs.aws.amazon.com/drs/latest/userguide/agent-install-prerequisites.html) — Linux/Windows prerequisites và disk/architecture limits.
7. [Supported Linux operating systems](https://docs.aws.amazon.com/drs/latest/userguide/Supported-Operating-Systems-Linux.html) — Linux OS và Graviton support.
8. [Supported Windows operating systems](https://docs.aws.amazon.com/drs/latest/userguide/Supported-Operating-Systems-Windows.html) — Windows OS và architecture support.
9. [Using service-linked roles for AWS DRS](https://docs.aws.amazon.com/drs/latest/userguide/using-service-linked-roles.html) — Service-linked role và permissions.
10. [Replication settings](https://docs.aws.amazon.com/drs/latest/userguide/settings.html) — Default/individual replication, launch và post-launch settings.
11. [Point-in-time policy](https://docs.aws.amazon.com/drs/latest/userguide/point-in-time.html) — Snapshot intervals và retention 1–365 ngày.
12. [Replication bandwidth requirements](https://docs.aws.amazon.com/drs/latest/userguide/comm-bandwidth-planning.html) — Tính write rate, bandwidth và headroom.
13. [Configuring launch settings](https://docs.aws.amazon.com/drs/latest/userguide/launching-target-servers.html) — EC2 launch templates và recovery instance preparation.
14. [DRS launch settings](https://docs.aws.amazon.com/drs/latest/userguide/launch-general-settings.html) — Right-sizing, start behavior, licensing và recovery modes.
15. [Post-launch actions](https://docs.aws.amazon.com/drs/latest/userguide/post-launch-action-settings-overview.html) — SSM, validation và custom automation.
16. [Preparing for recovery and performing drills](https://docs.aws.amazon.com/drs/latest/userguide/preparing-failover.html) — Drill objectives, steps và cleanup.
17. [Using DRS for recovery and failback](https://docs.aws.amazon.com/drs/latest/userguide/failback.html) — Recovery, failover distinction và failback mechanisms.
18. [Failback to on-premises](https://docs.aws.amazon.com/drs/latest/userguide/failback-performing.html) — Failback Client và source server recovery.
19. [Recovery Plans concepts](https://docs.aws.amazon.com/drs/latest/userguide/recovery-plans-concepts.html) — Recovery plan, server step, wait step và impact level.
20. [Adding and ordering Recovery Plan steps](https://docs.aws.amazon.com/drs/latest/userguide/recovery-plans-steps.html) — Step limits và wait duration.
21. [Running a Recovery Plan](https://docs.aws.amazon.com/drs/latest/userguide/recovery-plans-executing.html) — Drill/recovery execution và cleanup.
22. [Using multiple staging accounts](https://docs.aws.amazon.com/drs/latest/userguide/multi-account.html) — Multi-account architecture và scale beyond one staging account.
23. [AWS DRS quotas](https://docs.aws.amazon.com/general/latest/gr/drs.html) — Service quotas và API limits.
24. [Monitoring DRS with CloudWatch metrics](https://docs.aws.amazon.com/drs/latest/userguide/monitoring-event-bridge-metrics.html) — LagDuration, Backlog và recovery metrics.
25. [AWS DRS events in EventBridge](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-drs.html) — Service events và CloudTrail events.
26. [Troubleshooting replication errors](https://docs.aws.amazon.com/drs/latest/userguide/troubleshooting-replication.html) — Agent, network, performance và replication errors.
27. [Replication performance errors](https://docs.aws.amazon.com/drs/latest/userguide/replication-performance-errors.html) — NOT_CONVERGING, lag và backlog.
28. [AWS DRS pricing](https://aws.amazon.com/disaster-recovery/pricing/) — Hourly source server pricing và additional resource charges.
29. [AWS DRS FAQ](https://aws.amazon.com/disaster-recovery/faqs/) — RPO, security, failback, multi-account và service behavior.
30. [AWS DRS service release notes](https://docs.aws.amazon.com/drs/latest/userguide/drs-service-release-notes.html) — Thay đổi hỗ trợ OS, Graviton và Recovery Plans.

> **Ghi nhớ cuối bài:** AWS DRS duy trì block-level replication vào staging area, giữ point-in-time recovery states và tạo EC2 instances khi drill/recovery. Muốn đạt RPO/RTO, cần bảo đảm replication hội tụ, launch settings đúng, dependency order rõ ràng, traffic cutover có kiểm soát và failback đã được diễn tập. DRS là một thành phần của chiến lược DR; backup immutable, security controls, observability, quotas và cost planning vẫn cần được thiết kế riêng.
