# Ánh xạ khái niệm VM giữa Amazon EC2, Azure Virtual Machines và Compute Engine

Máy ảo (VM) là một đơn vị năng lực tính toán có hệ điều hành, CPU ảo, bộ nhớ, giao diện mạng và các đĩa lưu trữ được cấu hình để chạy workload. Ba nền tảng cloud lớn đều cung cấp VM, nhưng tên dịch vụ, cách tổ chức mạng, danh mục kích thước, danh tính máy và công cụ tự động hóa khác nhau.

Trong AWS, dịch vụ VM là **Amazon EC2** và một máy cụ thể được gọi là EC2 instance. Trong Microsoft Azure, dịch vụ tương ứng là **Azure Virtual Machines** (Azure VM). Trong Google Cloud, dịch vụ VM là **Compute Engine** và một máy cụ thể được gọi là Compute Engine instance. Các khái niệm có thể ánh xạ với nhau ở mức kiến trúc, nhưng thông số và hành vi không phải lúc nào cũng tương đương một-một.

Khi chuyển workload giữa các cloud, cần ánh xạ cả cấu hình tính toán, image, vùng sẵn sàng, mạng, đĩa, danh tính, khởi tạo máy, mở rộng và mô hình giá. Chỉ chọn một VM có số vCPU và RAM gần giống máy cũ chưa đủ để bảo đảm hiệu năng, tính sẵn sàng hoặc bảo mật tương đương.

Sau bài học, bạn có thể:

- Nhận diện các khái niệm VM tương ứng giữa EC2, Azure Virtual Machines và Compute Engine.
- Đối chiếu họ máy, image, vùng, mạng, đĩa, danh tính và cơ chế tự động mở rộng.
- Lập cấu hình tương đương theo yêu cầu workload thay vì so khớp tên SKU.
- Kiểm tra cấu hình VM bằng CLI và lập danh sách xác minh khi di chuyển giữa cloud.

## 1. Bản đồ khái niệm chung

| Khái niệm | Amazon EC2 | Azure Virtual Machines | Google Compute Engine |
|---|---|---|---|
| Máy ảo đang chạy | EC2 instance | Virtual machine (VM) | VM instance |
| Họ/kích thước máy | Instance type, ví dụ m7i.large | VM size, ví dụ một size thuộc họ D-series | Machine type, ví dụ n2-standard-2 |
| Image khởi động | Amazon Machine Image (AMI) | Image hoặc phiên bản image trong Azure Compute Gallery | Image hoặc image family |
| Vùng địa lý | Region | Region | Region |
| Khu vực sẵn sàng trong region | Availability Zone (AZ) | Availability Zone (nơi region hỗ trợ) | Zone |
| Mạng riêng logic | VPC | Virtual Network (VNet) | VPC network |
| Mạng con | Subnet gắn với một AZ | Subnet trong VNet | Subnet thuộc một region trong VPC network |
| Giao diện mạng | Elastic Network Interface (ENI) | Network Interface (NIC) | Network interface |
| Quy tắc lọc lưu lượng | Security Group và Network ACL | Network Security Group (NSG), Azure Firewall và các lớp mạng liên quan | VPC firewall rules, Cloud NGFW và các lớp mạng liên quan |
| Đĩa block bền vững | Amazon EBS volume | Azure Managed Disk | Persistent Disk hoặc Hyperdisk |
| Danh tính workload trên máy | IAM role qua instance profile | Managed Identity | Service account gắn với VM |
| Khởi tạo khi boot | User data, cloud-init | Custom Data, cloud-init, VM extensions | Startup scripts, metadata và guest agent |
| Nhóm VM tự mở rộng | EC2 Auto Scaling group | Virtual Machine Scale Sets (VMSS) | Managed Instance Group (MIG) |

Bản đồ này giúp tìm đúng khái niệm khi đọc tài liệu hoặc thiết kế kiến trúc đa cloud. Hãy tiếp tục kiểm tra phạm vi và hành vi của từng dịch vụ: ví dụ, một VPC của Google Cloud có phạm vi toàn cục, trong khi subnet của nó thuộc một region; VPC của AWS có phạm vi region và subnet được đặt trong một AZ. Tên gọi gần nhau không có nghĩa ranh giới tài nguyên giống nhau.

## 2. Ánh xạ năng lực CPU và bộ nhớ

Mỗi nhà cung cấp tổ chức danh mục máy theo họ và kích thước. Có thể nhóm chúng theo mục đích:

| Mục đích | Amazon EC2 | Azure VM | Compute Engine |
|---|---|---|---|
| General purpose | Họ M, một số họ T cho tải burst | Họ D, B cho tải burst | Họ E2, N2 và các họ general-purpose khác |
| Compute optimized | Họ C | Họ F | Họ C và một số họ tối ưu CPU |
| Memory optimized | Họ R, X và các biến thể liên quan | Họ E, M | Họ M và họ memory-optimized |
| Accelerated/GPU | Họ P, G, Trn và các loại accelerator khác | Các họ N-series có GPU | Các loại máy có GPU gắn kèm hoặc accelerator được hỗ trợ |

Tên họ và thế hệ thay đổi theo region, kiến trúc CPU và danh mục sản phẩm. Bảng trên là cách định hướng ban đầu, không phải bảng quy đổi SKU chính xác. Một VM thuộc họ M của EC2 không nhất thiết có cùng CPU, băng thông bộ nhớ, hiệu năng mạng hoặc mức giá với một VM thuộc họ D của Azure hay N2 của Google Cloud.

### So sánh theo đặc tính workload

- **General purpose:** phù hợp web/API, dịch vụ ứng dụng, máy chủ công cụ và workload có tỷ lệ CPU/bộ nhớ cân bằng.
- **Compute optimized:** phù hợp xử lý số, batch, build, mã hóa và ứng dụng cần nhiều CPU trên mỗi GB RAM.
- **Memory optimized:** phù hợp cache lớn, phân tích dữ liệu trong bộ nhớ, database và ứng dụng giữ working set lớn trong RAM.
- **Accelerated:** phù hợp huấn luyện hoặc suy luận AI, xử lý đồ họa, mô phỏng và workload tận dụng GPU/accelerator.
- **Burstable:** phù hợp workload có mức CPU nền thấp và thỉnh thoảng tăng cao. Cần hiểu cơ chế credit hoặc baseline CPU của đúng họ máy.

### Cách chọn cấu hình tương đương

Khi di chuyển, hãy thu thập tối thiểu:

1. Kiến trúc CPU: x86-64 hay Arm64; tập lệnh và thư viện native có hỗ trợ không.
2. Số vCPU và mức sử dụng CPU thực tế; một vCPU không luôn tương đương cùng một lượng hiệu năng giữa các thế hệ.
3. RAM, băng thông bộ nhớ và mức sử dụng đỉnh, không chỉ mức trung bình.
4. Hiệu năng và giới hạn mạng: băng thông, packet rate, số luồng và hành vi burst.
5. Hiệu năng lưu trữ: IOPS, throughput, độ trễ và số đĩa có thể gắn.
6. GPU hoặc accelerator: model, bộ nhớ thiết bị, driver, runtime và khả năng tương thích.
7. Giới hạn theo vùng, quota tài khoản, khả năng đặt chỗ và giá của cấu hình dự kiến.

Ví dụ, nếu workload hiện chạy trên EC2 general purpose với 2 vCPU và 8 GiB RAM, có thể tìm một Azure VM hoặc Compute Engine machine type có dung lượng gần tương đương làm ứng viên thử nghiệm. Sau đó benchmark CPU, RAM, network và disk trên cả hai môi trường. Không kết luận hai máy tương đương chỉ vì số vCPU và RAM trùng nhau.

Với workload phụ thuộc CPU, kiểm tra thế hệ CPU và hiệu năng đơn luồng. Với workload memory-bound, đo băng thông bộ nhớ và cache miss. Với workload mạng hoặc lưu trữ, so sánh throughput và latency thực tế. Chọn máy lớn hơn có thể giải quyết nút thắt nhưng cũng làm tăng chi phí; đôi khi chia workload thành nhiều VM nhỏ hoặc chuyển sang dịch vụ phù hợp hơn sẽ hiệu quả hơn.

## 3. Image, hệ điều hành và khởi tạo VM

Image là khuôn mẫu để tạo ổ đĩa khởi động và hệ điều hành ban đầu. Ba nền tảng đều có image do nhà cung cấp cung cấp, image marketplace và image tùy chỉnh, nhưng định dạng và quy trình quản lý không giống nhau.

| Nội dung | EC2 | Azure VM | Compute Engine |
|---|---|---|---|
| Image nền | AMI theo region và kiến trúc | Platform image, Marketplace image hoặc image tùy chỉnh | Public image project, image family hoặc custom image |
| Tạo image riêng | Tạo AMI từ instance hoặc snapshot theo quy trình | Capture image hoặc xây image trong Azure Compute Gallery | Tạo custom image từ disk hoặc image pipeline |
| Cấu hình lúc khởi động | User data; thường dùng cloud-init trên Linux | Custom Data; cloud-init trên Linux; VM extensions | Startup script qua metadata; cloud-init/guest agent tùy image |
| Cập nhật hệ điều hành | Quản lý patch bằng công cụ hệ điều hành và dịch vụ AWS phù hợp | Azure Update Manager hoặc công cụ quản trị khác | OS patch management và công cụ hệ điều hành phù hợp |

Không nên sao chép image nhị phân giữa các cloud rồi giả định máy sẽ boot được. Image có thể phụ thuộc driver, firmware, boot mode, agent, cấu hình mạng, disk controller và cơ chế cấp danh tính của nhà cung cấp. Khi chuyển cloud, thường nên xây image mới từ cấu hình hệ điều hành được chuẩn hóa, cài agent phù hợp và triển khai ứng dụng bằng automation.

### User data, Custom Data và startup script

Các cơ chế bootstrap cho phép truyền script hoặc cấu hình để máy tự cài package, lấy cấu hình, đăng ký vào hệ thống giám sát và khởi chạy ứng dụng. Chúng có vai trò tương tự nhau nhưng tên trường, giới hạn kích thước, thời điểm thực thi và cách lưu dữ liệu khác nhau.

Ví dụ, một bootstrap script Linux có thể thực hiện các bước ở mức khái niệm:

```bash
#!/bin/bash
set -euo pipefail

install_runtime_packages
fetch_configuration_from_secret_manager
configure_monitoring_agent
enable_application_service
```

Các tên hàm trong ví dụ là placeholder để thể hiện trình tự; thay bằng lệnh phù hợp với hệ điều hành và công cụ cấu hình của tổ chức. Nên thiết kế bootstrap có tính idempotent để chạy lại không gây hỏng trạng thái. Tránh nhúng mật khẩu, private key hoặc token dài hạn vào user data, Custom Data hay metadata vì các dữ liệu này có thể được lưu lại hoặc đọc bởi người có quyền truy cập VM metadata/configuration.

## 4. Region, zone và kiến trúc sẵn sàng cao

Region là khu vực địa lý mà nhà cung cấp đặt hạ tầng. Zone/AZ là một miền lỗi riêng trong region, giúp triển khai các bản sao ở những vị trí có khả năng chịu lỗi độc lập hơn.

| Nhà cung cấp | Khái niệm vị trí | Lưu ý khi thiết kế |
|---|---|---|
| AWS | Region và Availability Zone | Subnet được tạo trong một AZ. Tên AZ như us-east-1a có thể ánh xạ khác nhau giữa các tài khoản; AZ ID dùng để xác định vị trí nhất quán hơn giữa tài khoản. |
| Azure | Region và Availability Zone | Chỉ một số region/SKU hỗ trợ zone. Cần kiểm tra VM size, disk và dịch vụ mạng có hỗ trợ zone đã chọn không. |
| Google Cloud | Region và Zone | VM được tạo trong một zone. VPC network có phạm vi toàn cục, còn subnet thuộc region; kiểm tra machine type và quota tại zone cụ thể. |

Để triển khai HA, thường cần ít nhất hai bản sao ứng dụng ở các zone khác nhau, load balancer phân phối traffic và một cơ chế kiểm tra sức khỏe. Cần xác minh database, disk, NAT, firewall, DNS và các dependency cũng có thiết kế chịu lỗi tương ứng. Hai VM ở hai zone nhưng cùng phụ thuộc một disk đơn lẻ hoặc một database không chịu lỗi vẫn có thể gián đoạn.

Một số điểm khác biệt cần chú ý:

- EC2 Auto Scaling group có thể phân phối instance qua nhiều AZ trong một region.
- Azure VM Scale Sets có thể triển khai theo zone hoặc zone-redundant tùy cấu hình và khả năng region.
- Compute Engine Managed Instance Group có thể là zonal hoặc regional; regional MIG hỗ trợ phân phối VM qua nhiều zone trong region.

Khi di chuyển, giữ nguyên mục tiêu về miền lỗi và RTO/RPO thay vì chỉ sao chép số lượng VM. Xác minh hành vi khi một zone mất kết nối, khi instance bị thay thế và khi load balancer loại bỏ một backend không khỏe.

## 5. Ánh xạ mạng và bảo mật

Mạng là một trong những nơi khác biệt giữa các cloud dễ gây lỗi khi di chuyển. Cần ánh xạ kiến trúc mạng và chính sách truy cập, không chỉ đổi tên VPC thành VNet.

| Thành phần | AWS | Azure | Google Cloud |
|---|---|---|---|
| Mạng riêng | VPC | VNet | VPC network |
| Subnet | Thuộc một AZ | Subnet trong VNet | Subnet thuộc một region |
| Giao diện mạng | ENI | NIC | Network interface |
| Lọc traffic ở VM | Security Group gắn với ENI/instance | NSG gắn với subnet hoặc NIC | VPC firewall rules áp dụng theo network và target |
| Định tuyến | Route table gắn subnet | Route table gắn subnet | VPC routes và dynamic routing tùy cấu hình |
| Kết nối riêng đến dịch vụ | VPC endpoints/PrivateLink | Private Endpoint/Service Endpoint | Private Service Connect và các cơ chế private access |

### Security Group, NSG và VPC firewall rules

- **AWS Security Group** là firewall trạng thái (stateful) gắn với network interface của instance. Network ACL có thể áp dụng thêm ở cấp subnet và là stateless.
- **Azure NSG** có rule inbound/outbound, có thể gắn vào subnet hoặc NIC; Azure Firewall và các thành phần khác có thể bổ sung kiểm soát ở cấp mạng.
- **Google Cloud VPC firewall rules** áp dụng ở cấp VPC network và chọn target bằng network tag hoặc service account trong các mô hình phù hợp. Cần kiểm tra thứ tự ưu tiên, implied rules và hierarchical firewall policies nếu được dùng.

Ví dụ, yêu cầu “chỉ cho phép HTTPS từ Internet, SSH chỉ từ mạng quản trị, ứng dụng truy cập database qua cổng riêng” cần được chuyển thành rule tương ứng trên từng nền tảng. Không thể dịch trực tiếp một Security Group sang NSG hay firewall rule mà không kiểm tra nguồn/đích, chiều traffic, trạng thái kết nối, priority và phạm vi gắn rule.

### Địa chỉ IP và kết nối

Địa chỉ private IP thường gắn với NIC hoặc network interface. Public IP có thể là tài nguyên riêng được gắn vào NIC hoặc instance theo mô hình của nền tảng. Khi stop/deallocate hoặc thay VM, địa chỉ IP động có thể thay đổi; nếu cần địa chỉ ổn định, dùng tài nguyên IP tĩnh phù hợp và kiểm tra chi phí cũng như vòng đời gắn kết.

Không công khai cổng quản trị chỉ để thuận tiện. Ưu tiên VPN, bastion hoặc giải pháp quản trị từ xa có kiểm soát, dùng danh tính cá nhân và ghi log phiên truy cập. Giới hạn egress theo nhu cầu, mã hóa lưu lượng và phân đoạn mạng giữa lớp web, application và database.

## 6. Đĩa, snapshot và dữ liệu bền vững

VM thường có đĩa hệ điều hành và một hoặc nhiều đĩa dữ liệu. Đĩa block bền vững tách vòng đời dữ liệu khỏi vòng đời compute:

| Nhu cầu | EC2 | Azure VM | Compute Engine |
|---|---|---|---|
| Block storage bền vững | EBS volume | Azure Managed Disk | Persistent Disk hoặc Hyperdisk |
| Snapshot | EBS snapshot | Managed Disk snapshot | Disk snapshot |
| Đĩa cục bộ/ephemeral | Instance store (nếu loại máy hỗ trợ) | Temporary disk/local temporary storage tùy size | Local SSD (nếu loại máy hỗ trợ) |
| Gắn đĩa vào VM | EBS attach | Managed disk attach | Disk attach |

Đĩa local thường có độ trễ thấp và phù hợp cache hoặc scratch, nhưng dữ liệu có thể mất khi VM dừng, bị thay thế hoặc gặp sự cố tùy loại máy và cơ chế cung cấp. Không lưu dữ liệu duy nhất hoặc dữ liệu cần khôi phục trên đĩa ephemeral.

Khi đối chiếu đĩa, hãy so sánh dung lượng, loại hiệu năng, IOPS tối đa, throughput tối đa, độ trễ, mã hóa, khả năng resize, multi-attach, snapshot consistency và giới hạn số đĩa trên VM. Cũng cần xem liệu giới hạn IOPS/throughput đến từ disk, VM size hay tổng cả hai.

Snapshot thường hữu ích cho backup hoặc tạo image, nhưng không thay thế chiến lược backup nhất quán cho ứng dụng có ghi dữ liệu. Với database, dùng cơ chế backup phù hợp hoặc dừng/flush ứng dụng trước snapshot theo quy trình được hỗ trợ. Kiểm tra phục hồi định kỳ thay vì chỉ kiểm tra snapshot đã tạo thành công.

Khi migrate, xác định dữ liệu nào cần sao chép, dữ liệu nào có thể tái tạo, thời gian đồng bộ cuối cùng và cách tránh ghi đồng thời vào cả hai môi trường. Đừng gắn cùng một block volume vào nhiều VM hoặc cloud khác nhau trừ khi loại đĩa và filesystem hỗ trợ rõ ràng chế độ chia sẻ đó.

## 7. Danh tính VM và quyền truy cập dịch vụ

Một VM thường cần gọi object storage, secret manager, registry, monitoring hoặc API nội bộ. Mỗi cloud cung cấp cơ chế danh tính workload để máy nhận credential ngắn hạn thay vì lưu access key tĩnh:

- EC2 dùng IAM role gắn qua instance profile.
- Azure VM dùng system-assigned hoặc user-assigned Managed Identity.
- Compute Engine VM dùng service account được gắn vào instance.

Hãy cấp quyền tối thiểu theo đúng tài nguyên và thao tác cần thiết. Ví dụ, một VM chỉ cần đọc object trong một bucket/container cụ thể không nên được cấp quyền quản trị toàn bộ tài khoản. Kiểm tra cả danh tính mà ứng dụng dùng và quyền của người vận hành tạo/sửa VM.

Các điểm cần xác minh:

1. VM có gắn đúng role, managed identity hoặc service account không?
2. Danh tính có quyền đúng phạm vi tài nguyên và không có quyền quản trị dư thừa không?
3. Ứng dụng lấy credential qua SDK hoặc metadata service được hỗ trợ không?
4. Có ngăn ứng dụng không tin cậy truy cập metadata endpoint hoặc lấy credential của workload khác không?
5. Log có ghi nhận hoạt động API quan trọng để điều tra và audit không?

Khi chuyển cloud, không sao chép access key của nền tảng cũ sang biến môi trường của máy mới. Tạo danh tính workload mới, gán quyền tương ứng và kiểm thử luồng lấy credential trước khi cắt chuyển.

## 8. Tự động hóa, scaling và vòng đời VM

Các nền tảng đều có dịch vụ nhóm VM để duy trì số lượng máy mong muốn và thay thế máy lỗi:

| Khả năng | AWS | Azure | Google Cloud |
|---|---|---|---|
| Nhóm VM | Auto Scaling group | Virtual Machine Scale Sets | Managed Instance Group |
| Scaling | Policy theo metric, lịch hoặc điều kiện | Autoscale theo metric/lịch | Autoscaler theo metric/lịch |
| Health check | EC2 health checks, ELB health checks theo cấu hình | VMSS health extension/load balancer probe tùy thiết kế | MIG autohealing health check |
| Cập nhật nhóm | Launch template/version và instance refresh | Model/upgrade policy của VMSS | Instance template và rolling update |

Nhóm VM giúp chuẩn hóa cấu hình và thay thế instance, nhưng không tự bảo đảm ứng dụng stateless hoặc dữ liệu được lưu đúng nơi. Dữ liệu quan trọng nên nằm trên dịch vụ lưu trữ bền vững; VM được tạo mới phải có khả năng khởi động từ image và cấu hình đã chuẩn hóa.

Các trạng thái vòng đời cũng cần được hiểu theo nhà cung cấp:

- **Stop/deallocate:** VM không chạy compute, nhưng đĩa bền vững và một số tài nguyên liên quan có thể tiếp tục tính phí. Trên Azure, thao tác deallocate giải phóng compute allocation; một số địa chỉ IP động có thể được giải phóng. Trên EC2, stop instance thường giữ EBS nhưng instance store không giữ dữ liệu. Trên Compute Engine, dừng VM giữ persistent disks; ephemeral external IP có thể được giải phóng nếu không phải IP tĩnh.
- **Delete/terminate:** xóa VM có thể giữ hoặc xóa disk tùy cài đặt và hành vi mặc định của tài nguyên. Luôn xác minh chính sách xóa disk và backup trước khi thực hiện.
- **Resize:** thay machine size có thể cần dừng VM, thay đổi có thể bị giới hạn bởi zone, quota, kiến trúc CPU hoặc khả năng của disk/network.

Với workload gián đoạn được như batch, cân nhắc Spot/Preemptible capacity:

- AWS cung cấp EC2 Spot Instances.
- Azure cung cấp Azure Spot Virtual Machines.
- Google Cloud cung cấp Spot VMs.

Các loại capacity này có thể bị thu hồi theo điều kiện của nhà cung cấp và thường có giá thấp hơn capacity theo yêu cầu. Workload cần checkpoint, xử lý retry và không phụ thuộc vào một VM duy nhất. Không dùng Spot làm nơi giữ dữ liệu duy nhất hoặc chạy tác vụ không thể khởi động lại.

## 9. Mô hình chi phí khi đối chiếu giữa cloud

Không so sánh VM chỉ bằng giá niêm yết theo giờ. Tổng chi phí có thể gồm:

`Tổng chi phí = compute + disk + snapshot/backup + network + IP/load balancer + license + monitoring + support`

Các yếu tố chính:

- **On-demand/pay-as-you-go:** phù hợp thử nghiệm và tải không dự đoán được, nhưng chi phí đơn vị có thể cao hơn cam kết dài hạn.
- **Commitment/discount:** AWS Savings Plans hoặc Reserved Instances, Azure Reservations/Savings Plan và Google Cloud committed use discounts có điều kiện và cách áp dụng khác nhau. Đọc kỹ phạm vi áp dụng, thời hạn, loại tài nguyên và điều kiện thanh toán.
- **Spot/preemptible:** tiết kiệm cho workload có thể bị gián đoạn; cần tính chi phí checkpoint, retry và thời gian chờ capacity.
- **Storage:** disk được cấp có thể phát sinh phí ngay cả khi VM đã dừng. Snapshot, dung lượng provisioned, hiệu năng disk và giao dịch I/O có thể được tính riêng.
- **Network:** lưu lượng egress liên vùng/liên cloud, NAT, load balancer, public IP và kết nối riêng có thể tạo khoản phí đáng kể.
- **License:** Windows, SQL Server hoặc phần mềm thương mại có thể có chi phí và điều kiện BYOL khác nhau.

Để so sánh công bằng, hãy dùng cùng region hoặc vị trí gần tương đương, cùng thời gian đo, cùng mức dự phòng, cùng hiệu năng mục tiêu và cùng phạm vi dịch vụ đi kèm. Tính cả chi phí dự phòng HA và nhân lực vận hành, không chỉ giá một VM đơn lẻ.

## 10. Quy trình ánh xạ một workload giữa ba cloud

Giả sử một API nội bộ hiện chạy trên một EC2 instance Linux. Nhóm muốn đánh giá chuyển sang Azure VM hoặc Compute Engine. Có thể làm theo quy trình:

1. **Ghi lại cấu hình hiện tại:** instance type, kiến trúc CPU, AMI, region/AZ, subnet, security groups, EBS, IAM role, user data, monitoring và cách backup.
2. **Đo baseline:** CPU, RAM, network, disk IOPS/throughput/latency, request rate, response time và mức sử dụng đỉnh.
3. **Chọn ứng viên:** chọn Azure VM size hoặc Compute Engine machine type có kiến trúc CPU và dung lượng gần mục tiêu; kiểm tra GPU, network, disk và quota nếu có.
4. **Thiết kế vị trí và mạng:** chọn region/zone, subnet, private IP, firewall/NSG, route, DNS, load balancer và đường kết nối đến dependency.
5. **Tạo image và bootstrap:** dùng image được hỗ trợ, cài agent, áp dụng hardening, cấu hình ứng dụng và lấy secret qua workload identity.
6. **Chuyển dữ liệu:** tạo disk/snapshot hoặc đồng bộ dữ liệu theo cơ chế phù hợp; xác định điểm đồng bộ cuối cùng và cách rollback.
7. **Thử nghiệm:** chạy cùng workload và dữ liệu đại diện, đo CPU, memory, network, disk, latency và chi phí.
8. **Cắt chuyển:** chuyển traffic có kiểm soát, theo dõi lỗi và hiệu năng, giữ phương án rollback đến khi xác nhận ổn định.

Không nhất thiết phải chuyển mọi thành phần cùng lúc. Có thể giữ database ở cloud cũ trong giai đoạn thử nghiệm, nhưng phải tính độ trễ và chi phí truyền dữ liệu liên cloud. Nếu mục tiêu là đánh giá năng lực compute thuần, hãy cô lập yếu tố mạng và lưu trữ để kết quả benchmark có thể so sánh.

## 11. Kiểm tra cấu hình VM bằng CLI

Các lệnh sau chỉ đọc thông tin VM hiện có. Thay placeholder bằng ID, tên resource group và zone thực tế; tài khoản CLI cần được đăng nhập và có quyền đọc tài nguyên.

**AWS CLI — xem instance type, AZ và trạng thái:**

```bash
aws ec2 describe-instances \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].{ID:InstanceId,Type:InstanceType,AZ:Placement.AvailabilityZone,State:State.Name}' \
  --output table
```

**Azure CLI — xem VM size, region, zone và OS disk:**

```bash
az vm show \
  --resource-group rg-app \
  --name app-vm \
  --query '{name:name,size:hardwareProfile.vmSize,location:location,zones:zones,osDisk:storageProfile.osDisk.managedDisk.id}' \
  --output yaml
```

**gcloud CLI — xem machine type, zone, trạng thái, network và disk:**

```bash
gcloud compute instances describe app-vm \
  --zone=us-central1-a \
  --format='yaml(name,machineType,zone,status,networkInterfaces,disks)'
```

Sau khi đọc cấu hình, xác minh thêm các thông tin không thể kết luận chỉ từ lệnh mô tả VM: quyền workload identity, rule firewall hiệu lực, metric hiệu năng, chính sách backup, autoscaling và chi phí. Có thể dùng console, CLI chuyên biệt hoặc hệ thống quản trị nội bộ để kiểm tra các lớp đó.

## 12. Checklist ánh xạ VM đa cloud

- [ ] Đã xác định workload, kiến trúc CPU, hệ điều hành và yêu cầu license.
- [ ] Đã so sánh vCPU, RAM, hiệu năng CPU, băng thông bộ nhớ, network và disk bằng benchmark.
- [ ] Đã chọn đúng image, boot mode, driver, agent và bootstrap cho nền tảng đích.
- [ ] Đã ánh xạ region/zone và miền lỗi theo mục tiêu HA.
- [ ] Đã thiết kế lại VPC/VNet, subnet, NIC, route, firewall và IP.
- [ ] Đã chọn disk bền vững, local scratch, snapshot và backup phù hợp.
- [ ] Đã tạo IAM role, Managed Identity hoặc service account với quyền tối thiểu.
- [ ] Đã cấu hình nhóm VM, health check, autoscaling và cập nhật rolling nếu cần.
- [ ] Đã đánh giá Spot/preemptible chỉ cho workload chịu được gián đoạn.
- [ ] Đã tính compute, storage, network, license, monitoring và commitment trong tổng chi phí.
- [ ] Đã kiểm tra metric, backup restore, failover, rollback và quyền truy cập trước cutover.

Khi ánh xạ VM giữa EC2, Azure Virtual Machines và Compute Engine, hãy giữ nguyên mục tiêu của workload và thiết kế lại cách đạt mục tiêu đó bằng dịch vụ tương ứng. Một cấu hình tốt là cấu hình đáp ứng được hiệu năng, bảo mật, tính sẵn sàng và chi phí đã đo trong môi trường đích, không phải cấu hình có tên gọi giống nền tảng nguồn.
