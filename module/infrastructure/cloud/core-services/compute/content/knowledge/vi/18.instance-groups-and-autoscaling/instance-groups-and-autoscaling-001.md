# Nhóm instance có quản lý và mẫu cấu hình máy thành viên

Khi một ứng dụng cần nhiều máy ảo để phục vụ tải, việc tạo và quản lý từng VM riêng lẻ nhanh chóng trở nên khó kiểm soát. Nhóm instance có quản lý (managed instance group hoặc scale set tùy nền tảng) cho phép khai báo số lượng máy mong muốn cùng một cấu hình chuẩn, sau đó nền tảng tự tạo, kiểm tra sức khỏe, thay thế và cập nhật các máy thành viên theo chính sách.

**Mẫu cấu hình máy thành viên (instance template hoặc machine model)** mô tả cách tạo một VM: image, loại máy, ổ đĩa, mạng, danh tính, metadata, startup configuration và các thuộc tính liên quan. **Managed instance group** dùng mẫu này làm nguồn cấu hình để duy trì một tập VM có cùng vai trò. Khi một thành viên bị lỗi hoặc cần mở rộng quy mô, bộ điều khiển của nền tảng tạo hoặc loại bỏ VM để đưa nhóm về trạng thái mong muốn.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, nhóm instance có quản lý là nền tảng để vận hành fleet VM nhất quán, hỗ trợ autoscaling, phân phối qua nhiều zone và cập nhật theo đợt. Thiết kế tốt cần xác định rõ mẫu cấu hình, chính sách vòng đời, health check, phân phối tải, cách cập nhật và dữ liệu nào được phép tồn tại độc lập với từng VM.

## 1. Managed instance group là gì?

Managed instance group là một tài nguyên điều khiển tập hợp VM thay cho việc quản lý từng máy riêng lẻ. Người vận hành khai báo trạng thái mong muốn; nền tảng liên tục so sánh trạng thái thực tế với trạng thái đó và thực hiện hành động để hội tụ.

Một nhóm thường có các thành phần:

- **Group/controller:** tài nguyên quản lý tập VM và chính sách vòng đời.
- **Instance template/model:** cấu hình dùng để tạo VM thành viên.
- **Desired capacity:** số VM hoặc mức capacity mà nhóm cần duy trì.
- **Minimum/maximum capacity:** giới hạn dưới và trên nếu nhóm hỗ trợ autoscaling.
- **Health check/autohealing:** cách xác định thành viên không khỏe và hành động thay thế.
- **Update policy:** cách thay VM cũ bằng VM theo template mới.
- **Placement/distribution policy:** cách phân bổ thành viên theo zone, subnet hoặc failure domain.
- **Lifecycle controls:** bảo vệ scale-in, draining, hooks hoặc chế độ standby tùy nền tảng.

Nhóm được quản lý theo **declarative model**: người vận hành mô tả kết quả mong muốn, controller chịu trách nhiệm thực hiện các thay đổi cần thiết. Nếu một VM bị xóa ngoài ý muốn trong khi desired capacity vẫn giữ nguyên, group có thể tạo VM thay thế.

### 1.1. So sánh quản lý từng VM và quản lý theo nhóm

| Tiêu chí | VM quản lý riêng lẻ | Managed instance group |
| --- | --- | --- |
| Tạo máy | Tạo từng VM bằng console/API/IaC | Tạo thành viên từ một template/model |
| Duy trì số lượng | Người vận hành theo dõi và tạo lại | Controller duy trì desired capacity |
| Phát hiện máy lỗi | Monitoring và thao tác thủ công | Có thể tích hợp health check và autohealing |
| Cập nhật image | Thực hiện trên từng VM hoặc theo script | Có update policy/instance refresh |
| Mở rộng | Tạo thêm VM và đăng ký backend | Thay đổi desired capacity hoặc dùng autoscaler |
| Tính đồng nhất | Dễ drift giữa các máy | Template và quy trình rollout tạo chuẩn chung |
| Vòng đời | Thường gắn với từng VM | Thành viên có thể được thay thế tự động |

Managed group giảm thao tác lặp lại nhưng không tự giải quyết mọi vấn đề của ứng dụng. Ứng dụng vẫn cần thiết kế stateless hoặc có cơ chế lưu trạng thái bên ngoài, hỗ trợ shutdown/drain và xử lý việc VM bị thay thế.

## 2. Instance template là nguồn cấu hình chuẩn

Instance template mô tả cấu hình được dùng khi group tạo thành viên mới. Template càng rõ ràng và có version càng dễ kiểm soát việc tạo mới, mở rộng và cập nhật.

Một template thường chứa các nhóm thuộc tính:

| Nhóm cấu hình | Nội dung thường gặp | Tác động |
| --- | --- | --- |
| Compute | Machine type, vCPU, RAM, accelerator, architecture | Năng lực xử lý và chi phí mỗi VM |
| Boot image | Image ID, image family hoặc image version | Hệ điều hành, kernel, agent và phần mềm nền |
| Storage | Boot disk, data disk, type, size, encryption, delete policy | Dung lượng, hiệu năng và độ bền dữ liệu |
| Network | VPC/VNet, subnet, NIC, security group, IP mode | Kết nối, phân đoạn mạng và bề mặt tấn công |
| Identity | Instance role, managed identity, service account | Quyền workload khi gọi API |
| Metadata/bootstrap | User data, cloud-init, startup script, custom metadata | Cấu hình khi máy khởi động |
| Placement | Zone, placement group, tenancy hoặc host affinity | Độ trễ, phân tán lỗi và hiệu năng |
| Operations | Monitoring, logging, shutdown behavior, tags/labels | Quan sát, quản lý và tự động hóa |

Template nên chứa cấu hình không nhạy cảm và có thể tái tạo. Không đưa password, private key hoặc access key dài hạn vào user data, startup script hay metadata. Workload nên dùng managed identity/instance role hoặc lấy secret từ secret manager bằng danh tính có quyền tối thiểu.

### 2.1. Compute và kiến trúc máy

Chọn machine type phù hợp với đặc tính workload:

- Compute-optimized cho tác vụ CPU-bound.
- Memory-optimized cho working set lớn hoặc cache trong RAM.
- General-purpose cho workload hỗn hợp.
- Storage-optimized cho I/O cục bộ hoặc throughput storage cao.
- GPU/accelerator cho tác vụ có thể tận dụng phần cứng tăng tốc.

Các thành viên trong cùng group thường được tạo theo một machine model nhất quán. Một số nền tảng hỗ trợ nhiều instance type hoặc override theo nhóm; nếu sử dụng, cần kiểm tra chênh lệch CPU, RAM, network và kiến trúc để ứng dụng vẫn hoạt động ổn định.

Không nên thay machine type chỉ dựa trên CPU utilization. Hãy xem memory pressure, network throughput, I/O wait, queue, latency và cost per request.

### 2.2. Image và phần mềm trong máy

Image là đầu vào quan trọng nhất để tạo ra một fleet nhất quán. Nên:

- Dùng image đã được kiểm thử và có ID/version rõ ràng.
- Pin image cụ thể trong template thay vì tham chiếu một tag thay đổi không kiểm soát.
- Cập nhật OS package, kernel, runtime và agent trong pipeline build image.
- Quét lỗ hổng và kiểm tra baseline trước khi phát hành image.
- Lưu lại image ID, build provenance và thời điểm tạo.
- Có chiến lược thay thế các VM cũ khi image mới được phát hành.

Image family hoặc alias động có thể tiện cho môi trường phát triển, nhưng trong production nên kiểm soát rõ version mà mỗi lần rollout sử dụng. Nếu template trỏ đến một image alias tự thay đổi, lần scale-out sau có thể tạo máy khác phiên bản với những thành viên đang chạy.

### 2.3. Boot disk và data disk

Template cần mô tả rõ:

- Loại và kích thước boot disk.
- Loại volume, IOPS/throughput nếu có cấu hình.
- Encryption và key được dùng.
- Chính sách giữ hoặc xóa boot disk khi VM bị terminate.
- Data volume có gắn cố định, được tạo theo instance hay được quản lý độc lập.
- Mount point và quy trình khởi tạo filesystem.

Boot disk thường có thể được tái tạo từ image. Dữ liệu nghiệp vụ cần được lưu ở database, object storage, shared file service hoặc persistent volume có vòng đời độc lập. Nếu data disk được tạo riêng cho từng VM, cần xác định điều gì xảy ra khi group thay thành viên.

Không bật tự động xóa mọi disk khi terminate nếu có khả năng disk chứa dữ liệu cần giữ. Ngược lại, không giữ vô hạn các boot disk tạm sau khi VM bị thay thế vì có thể phát sinh chi phí và để lại dữ liệu nhạy cảm.

### 2.4. Network và bảo mật

Các thành viên cần được tạo trong network/subnet và security policy phù hợp. Template có thể định nghĩa:

- VPC/VNet và subnet hoặc subnet selection.
- Network interface và public/private IP mode.
- Security group/firewall policy.
- DNS, route và endpoint cần truy cập.
- Network acceleration hoặc bandwidth configuration nếu hỗ trợ.

Với fleet ứng dụng nội bộ, ưu tiên private address và chỉ mở cổng cần thiết từ load balancer hoặc nguồn tin cậy. Tránh gắn public IP cho từng thành viên nếu không có nhu cầu. Không hardcode một địa chỉ IP riêng vào ứng dụng; dùng service discovery, load balancer hoặc DNS.

### 2.5. Identity, metadata và startup

Template có thể gắn instance role, managed identity hoặc service account để workload xác thực với dịch vụ cloud. Cấp quyền tối thiểu theo nhiệm vụ của nhóm.

Startup script nên:

- Idempotent để chạy lại không gây cấu hình lặp hoặc hỏng trạng thái.
- Có timeout và log rõ ràng.
- Kiểm tra dependency trước khi khởi động ứng dụng.
- Lấy secret từ secret manager bằng workload identity.
- Không ghi credential vào log hoặc file world-readable.
- Báo trạng thái readiness sau khi hoàn tất cấu hình cần thiết.

Startup script không nên tải phần mềm tùy ý từ nguồn không được kiểm soát mỗi lần VM boot. Tốt hơn là build phần mềm vào image đã kiểm thử; bootstrap chỉ xử lý cấu hình môi trường và tác vụ khởi tạo tối thiểu.

## 3. Cách group duy trì desired capacity

Giả sử group được cấu hình desired capacity là 4. Nếu một thành viên bị xóa hoặc bị đánh dấu unhealthy, controller có thể tạo VM thay thế để đưa số thành viên hoạt động về 4, miễn là quota, capacity và các điều kiện khác cho phép.

Các giá trị capacity thường gồm:

- **Minimum:** số thành viên tối thiểu được phép duy trì.
- **Desired:** số thành viên controller hướng tới tại thời điểm hiện tại.
- **Maximum:** giới hạn trên của group.

Với group dùng autoscaling, desired capacity có thể thay đổi theo policy hoặc lịch. Với group tĩnh, desired capacity thường do người vận hành đặt.

Ví dụ:

| Thuộc tính | Giá trị |
| --- | ---: |
| Minimum | 2 |
| Desired | 4 |
| Maximum | 10 |

Nếu tải tăng và autoscaler quyết định cần 7 VM, desired capacity có thể được nâng lên 7. Khi tải giảm, desired có thể giảm về 4 hoặc 2 tùy policy và giới hạn.

Controller không bảo đảm luôn đạt desired ngay lập tức. Quota, thiếu capacity ở zone, image lỗi, startup script thất bại, subnet hết IP hoặc policy không đủ quyền có thể khiến group thiếu thành viên. Cần theo dõi cả desired capacity và số instance thực tế healthy/in-service.

## 4. Health check và tự động thay thế máy lỗi

Managed group thường có thể kết hợp health check để nhận biết thành viên không còn đủ điều kiện phục vụ. Tùy nền tảng, nguồn health có thể là trạng thái VM, kiểm tra hệ điều hành, health check của load balancer hoặc tín hiệu do người dùng cấu hình.

### 4.1. Các lớp health

- **Infrastructure health:** VM có được hypervisor/provider xem là hoạt động không?
- **Guest health:** OS có boot, agent và network cơ bản không?
- **Application health:** ứng dụng có nhận request và trả kết quả đúng không?
- **Load balancer health:** backend có vượt qua probe theo port/path/protocol đã cấu hình không?
- **Dependency health:** ứng dụng có kết nối được database, cache hoặc queue thiết yếu không?

Một VM có thể ở trạng thái running nhưng ứng dụng chết. Nếu chỉ dùng infrastructure health, group sẽ không nhận ra lỗi ở tầng ứng dụng. Ngược lại, health check quá sâu hoặc phụ thuộc vào dịch vụ phụ trợ không thiết yếu có thể đánh dấu tất cả instance unhealthy khi dependency tạm thời gián đoạn.

### 4.2. Readiness và liveness

Readiness trả lời câu hỏi “instance đã sẵn sàng nhận traffic chưa?”. Liveness trả lời “process có còn sống và cần được khởi động lại không?”. Hai tín hiệu có mục tiêu khác nhau.

Trong fleet VM, health check của load balancer thường giúp loại backend chưa sẵn sàng khỏi traffic. Group health/autohealing có thể dùng tín hiệu để thay VM không khỏe. Cần cấu hình grace period đủ cho boot và bootstrap, nhưng không dài đến mức giữ máy lỗi quá lâu.

### 4.3. Tránh vòng lặp thay thế liên tục

Nếu image hoặc startup script có lỗi, group có thể liên tục tạo VM mới rồi lại đánh dấu unhealthy. Hệ quả là:

- Tốn chi phí do VM khởi tạo liên tục.
- Tăng tải lên quota, API và image registry.
- Làm backend capacity biến động.
- Che lấp nguyên nhân gốc vì instance lỗi bị thay quá nhanh.

Nên có log bootstrap, alarm về số lần launch/terminate, giới hạn tốc độ thay thế hoặc cơ chế dừng rollout khi lỗi hàng loạt. Khi nhiều VM cùng unhealthy sau một thay đổi, cần xem xét rollback template/image thay vì để controller tiếp tục lặp lại.

## 5. Phân phối instance qua nhiều zone

Một group có thể phân bổ thành viên qua nhiều availability zone hoặc failure domain để giảm phụ thuộc vào một điểm lỗi. Cách phân phối cụ thể phụ thuộc provider và cấu hình group.

Ví dụ group có 6 VM trên 3 zone có thể hướng đến 2 VM mỗi zone. Khi một zone thiếu capacity, provider có thể phân phối không đều hoặc không tạo đủ số lượng tùy chính sách.

Lợi ích:

- Tăng khả năng chịu lỗi khi một zone gặp sự cố.
- Có thể giảm rủi ro bảo trì hoặc lỗi hạ tầng tập trung.
- Hỗ trợ load balancer phân phối traffic qua nhiều failure domain.

Đánh đổi:

- Request và replication có thể đi qua network liên zone.
- Có thể phát sinh transfer charge.
- Database/cache cần topology hỗ trợ truy cập từ nhiều zone.
- Scale-in và rolling update cần tránh làm một zone mất quá nhiều capacity.

Không nên coi việc đặt VM ở nhiều zone là đủ để có high availability. Load balancer, database, cache, DNS, identity và các dependency cũng phải có thiết kế chịu lỗi phù hợp.

## 6. Cập nhật template và rollout thành viên

Khi thay image, machine type, disk, network hoặc startup configuration, cần xác định cách các thành viên hiện tại nhận cấu hình mới.

Nhiều nền tảng không tự sửa toàn bộ VM đang chạy chỉ vì template đã thay đổi. Có thể cần một thao tác update/refresh để thay instance cũ bằng instance mới.

### 6.1. Version hóa template

Mỗi thay đổi quan trọng nên tạo một version hoặc model revision có thể truy vết. Ví dụ:

| Revision | Image | Machine type | Mục đích |
| --- | --- | --- | --- |
| v12 | app-image-2026-10 | general-4 | Phiên bản đang phục vụ |
| v13 | app-image-2026-11 | general-4 | Vá OS và dependency |
| v14 | app-image-2026-11 | compute-8 | Thử tăng CPU cho workload |

Không sửa lịch sử version đã dùng cho production nếu nền tảng hỗ trợ version bất biến. Tạo revision mới giúp biết VM nào được tạo từ cấu hình nào và có thể rollback về revision đã biết hoạt động.

### 6.2. Rolling update

Rolling update thay thế thành viên theo từng batch thay vì dừng cả group cùng lúc. Các tham số thường cần quyết định:

- Số instance tối đa được thay cùng lúc.
- Số instance tối thiểu phải healthy trong quá trình update.
- Capacity tạm thời có thể vượt desired bao nhiêu.
- Thời gian chờ health check sau khi tạo VM mới.
- Điều kiện dừng khi launch hoặc health check thất bại.
- Cách rollback về template revision trước.

Nếu group cần luôn giữ tối thiểu 4 VM healthy, update policy phải bảo đảm không đồng thời làm mất quá nhiều thành viên. Với workload có startup lâu, batch nhỏ và thời gian chờ phù hợp sẽ giảm nguy cơ gián đoạn.

### 6.3. Blue-green hoặc replacement theo batch

Với thay đổi lớn như đổi OS, runtime hoặc kiến trúc máy, có thể tạo group mới song song, kiểm thử rồi chuyển traffic qua load balancer. Cách này tốn capacity tạm thời nhưng giúp quay lại group cũ nhanh hơn.

Không phải workload nào cũng cần blue-green. Với fleet stateless, rolling update thường tiết kiệm hơn. Với thay đổi rủi ro cao hoặc cần kiểm thử tương thích rộng, blue-green có thể đáng chi phí.

### 6.4. Xử lý lỗi trong quá trình update

Khi rollout thất bại:

1. Dừng batch tiếp theo.
2. Giữ lại log, image ID, template revision và health result.
3. Kiểm tra các thành viên mới có lỗi chung hay chỉ một zone.
4. Xác định traffic đã được chuyển đến instance mới chưa.
5. Rollback template hoặc chuyển traffic về group ổn định.
6. Chỉ cleanup VM/disk tạm sau khi xác minh chúng không chứa dữ liệu cần giữ.
7. Sửa image/bootstrap rồi thử lại với revision mới.

## 7. Scale-in và vòng đời của thành viên

Scale-out thường tạo thêm VM. Scale-in loại bớt VM khi desired capacity giảm. Việc chọn đúng thành viên cần loại bỏ rất quan trọng để tránh ngắt request hoặc làm mất trạng thái.

### 7.1. Graceful shutdown và connection draining

Trước khi terminate, ứng dụng nên có thời gian:

- Ngừng nhận request mới.
- Hoàn tất request đang xử lý.
- Commit transaction hoặc ghi checkpoint.
- Xử lý message đang giữ và ack/nack đúng cách.
- Đóng kết nối database/cache.
- Flush log và metric cần thiết.
- Giải phóng lock hoặc lease.

Load balancer có thể hỗ trợ connection draining/deregistration delay. Lifecycle hook hoặc shutdown hook có thể cho ứng dụng thêm thời gian hoàn tất. Cần cấu hình timeout phù hợp; nếu quá dài, scale-in chậm và có thể vượt giới hạn shutdown của nền tảng.

### 7.2. Chọn instance để scale-in

Một số group hỗ trợ policy chọn thành viên theo tuổi, zone, template version hoặc mức sử dụng. Cần kiểm tra lựa chọn đó có phù hợp với workload không.

Không nên giả định group sẽ chọn VM ít tải nhất. Nếu một VM đang xử lý tác vụ dài hoặc giữ session, ứng dụng cần có cơ chế drain và phục hồi công việc khi VM bị loại bỏ.

### 7.3. Scale-in protection

Scale-in protection hoặc cơ chế tương đương có thể ngăn một instance cụ thể bị loại trong lúc đang xử lý công việc quan trọng. Tuy nhiên, protection không nên bật vô thời hạn; nếu tất cả thành viên đều được bảo vệ, group có thể không giảm được capacity và tiếp tục phát sinh chi phí.

Dùng protection có thời hạn, gắn với lifecycle event và có cơ chế bỏ protection sau khi công việc hoàn tất. Với workload xử lý batch, checkpoint và queue thường bền vững hơn việc giữ một VM không thể terminate.

## 8. Stateful và stateless trong managed group

Managed group phù hợp nhất với thành viên có thể thay thế. Nếu mỗi VM giữ trạng thái duy nhất trên local disk hoặc RAM, việc autohealing và scale-in có thể làm mất dữ liệu.

### 8.1. Thiết kế stateless

Một instance stateless không giữ trạng thái nghiệp vụ duy nhất cần tồn tại qua vòng đời máy. Session, file upload, job state và dữ liệu giao dịch được lưu ở dịch vụ dùng chung hoặc storage bền vững.

Khi đó, VM có thể bị thay thế mà ứng dụng vẫn tiếp tục hoạt động trên các thành viên khác. Đây là mô hình thuận lợi cho autoscaling và rolling update.

### 8.2. Nếu workload cần state

Nếu không thể tránh state cục bộ:

- Xác định rõ dữ liệu nào phải giữ khi VM terminate.
- Dùng persistent volume có vòng đời độc lập và cơ chế attach phù hợp.
- Dùng database/shared storage hoặc replication thay vì chỉ lưu trên ephemeral disk.
- Có checkpoint và cơ chế resume.
- Bảo đảm chỉ một instance sở hữu quyền ghi khi dùng shared volume.
- Cấu hình scale-in protection hoặc lifecycle hook theo thời gian có giới hạn.

Không nên gắn một persistent disk vào mọi VM thành viên nếu storage không hỗ trợ multi-attach an toàn. Multi-attach block storage cần filesystem cluster-aware hoặc ứng dụng có cơ chế khóa phù hợp.

## 9. So sánh các mô hình của nhà cung cấp cloud

Các nhà cung cấp có tên gọi và khả năng riêng, nhưng đều cung cấp mô hình quản lý tập VM dựa trên cấu hình chuẩn.

| Khái niệm chung | AWS | Microsoft Azure | Google Cloud |
| --- | --- | --- | --- |
| Nhóm VM có quản lý | EC2 Auto Scaling Group | Virtual Machine Scale Sets (VMSS) | Managed Instance Group (MIG) |
| Mẫu cấu hình | EC2 Launch Template | VMSS VM profile/model | Instance Template |
| Số lượng mong muốn | Desired capacity | Capacity của scale set | Target size |
| Kiểm tra sức khỏe | EC2/ELB health checks | VM health extension và health monitoring tùy cấu hình | Health check và autohealing policy |
| Cập nhật | Instance refresh hoặc rolling replacement theo cấu hình | Rolling upgrades hoặc update policy | MIG rolling update/recreate |
| Phân phối zone | AZ/subnet và group settings | Availability zones | Regional/zonal MIG |

Tên tính năng, giới hạn và hành vi mặc định thay đổi theo phiên bản API, loại group và region. Khi triển khai, cần đọc tài liệu của đúng dịch vụ và kiểm tra các điều kiện như quota, loại disk, network, health integration và update policy.

### 9.1. AWS EC2 Auto Scaling Group

EC2 Auto Scaling Group (ASG) quản lý một tập EC2 instance. ASG thường tham chiếu Launch Template và version cụ thể. Launch Template mô tả image, instance type, key pair nếu dùng, network interface, security group, IAM instance profile, storage mapping, user data và các thuộc tính hỗ trợ.

Các điểm cần chú ý:

- Chọn Launch Template version rõ ràng; tránh dùng $Latest hoặc $Default nếu không kiểm soát được thay đổi.
- Dùng health check phù hợp, có thể kết hợp EC2 status và load balancer health.
- Dùng instance refresh để thay thành viên theo batch khi cập nhật template.
- Xác định lifecycle hook, connection draining và termination policy.
- Nếu dùng nhiều instance type, kiểm tra khả năng tương thích của ứng dụng và capacity trong các AZ.

### 9.2. Azure Virtual Machine Scale Sets

VM Scale Sets quản lý một tập VM có cấu hình thống nhất hoặc theo các chế độ orchestration được hỗ trợ. VMSS model mô tả image, VM size, storage profile, network profile, identity, extension và các thuộc tính liên quan.

Các điểm cần chú ý:

- Hiểu chế độ orchestration và update mode của scale set.
- Xác định cách instance nhận model mới và khi nào cần rolling upgrade/reimage.
- Dùng health extension hoặc tích hợp health phù hợp để phát hiện ứng dụng không khỏe.
- Kiểm tra zone distribution, upgrade policy, instance protection và rolling limits.
- Xác minh extension/startup script chạy thành công trước khi instance nhận traffic.

### 9.3. Google Cloud Managed Instance Groups

Managed Instance Group của Google Cloud tạo và quản lý VM từ Instance Template. MIG có thể là zonal hoặc regional và hỗ trợ autoscaling, autohealing, rolling update và các chính sách phân phối theo khả năng của loại group.

Các điểm cần chú ý:

- Instance Template là cấu hình dùng để tạo VM; tạo template revision mới khi cần thay đổi.
- Cập nhật MIG sang template mới bằng update policy phù hợp.
- Dùng health check và autohealing policy để thay VM không khỏe.
- Regional MIG giúp phân phối thành viên qua nhiều zone trong region.
- Kiểm tra giới hạn surge/unavailable, capacity và hành vi thay thế theo update policy.

## 10. Ví dụ mẫu cấu hình khái niệm

Ví dụ YAML dưới đây minh họa một nhóm VM stateless chạy dịch vụ API. Đây là mô hình trung lập, không phải schema trực tiếp của AWS, Azure hoặc Google Cloud.

~~~yaml
instance_template:
  name: orders-api-v17
  image: orders-api-image-2026-11
  machine:
    type: general-purpose-4
    architecture: x86_64
  boot_disk:
    type: balanced-ssd
    size_gib: 40
    encrypted: true
    delete_on_termination: true
  network:
    subnet: private-app-subnet
    public_ip: false
    security_policy: orders-api-backend
  identity:
    workload_role: orders-api-read-runtime
  bootstrap:
    source: baked-image
    startup_script: configure-environment
  metadata:
    application: orders-api
    environment: production
    template_revision: v17

managed_group:
  name: orders-api-fleet
  template_revision: v17
  min_size: 3
  desired_size: 6
  max_size: 20
  zones:
    - zone-a
    - zone-b
    - zone-c
  health_check:
    type: application
    path: /health/ready
    grace_period_seconds: 180
  update_policy:
    strategy: rolling
    max_surge: 1
    max_unavailable: 1
  scale_in:
    connection_draining_seconds: 60
~~~

Khi chuyển thành cấu hình provider, cần ánh xạ từng trường sang API và xác minh semantics. Ví dụ max_surge có thể được biểu diễn bằng tham số khác hoặc bị giới hạn theo loại group. Health path phải thực sự kiểm tra readiness của ứng dụng và không phụ thuộc vào một hệ thống ngoài không thiết yếu.

### 10.1. Trình tự triển khai nhóm

1. Build và kiểm thử image.
2. Tạo template revision mới.
3. Tạo group với min/desired/max và zone distribution.
4. Kiểm tra VM thành viên được tạo đúng image, size, disk, network và identity.
5. Đợi bootstrap hoàn tất và health check đạt.
6. Đăng ký backend với load balancer hoặc xác minh tích hợp tự động.
7. Chạy smoke test và kiểm tra metric.
8. Bật autoscaling sau khi xác nhận group hoạt động ổn định.

Không nên bật scale-out trước khi xác minh subnet còn đủ IP, quota đủ và bootstrap có thể hoàn tất khi nhiều VM được tạo cùng lúc.

## 11. Kiểm soát drift và tính nhất quán cấu hình

Drift xảy ra khi cấu hình VM thực tế khác template hoặc baseline được quản lý. Ví dụ, một người đăng nhập vào VM rồi cài thêm package, mở port, đổi file cấu hình hoặc gắn disk thủ công.

Trong managed group, thành viên mới có thể được tạo lại từ template sạch, trong khi thành viên cũ vẫn giữ thay đổi thủ công. Điều này tạo ra fleet không đồng nhất.

Biện pháp kiểm soát:

- Dùng image bất biến và bootstrap có thể lặp lại.
- Quản lý template bằng IaC và review thay đổi qua version control.
- Hạn chế đăng nhập thay đổi thủ công trên production.
- Quét inventory và so sánh cấu hình runtime với baseline.
- Dùng instance refresh để thay VM drift bằng thành viên mới từ template chuẩn.
- Ghi nhận ngoại lệ cần thiết và thời hạn loại bỏ.
- Không cập nhật template mà bỏ qua rollout các thành viên cũ.

Template là nguồn cấu hình cho VM được tạo mới, nhưng không phải lúc nào cũng là công cụ tự sửa drift bên trong VM đang chạy. Cần có quy trình cập nhật hoặc thay thế thành viên rõ ràng.

## 12. Quan sát và vận hành managed group

Theo dõi group ở cả cấp nhóm và cấp instance.

| Chỉ số/trạng thái | Câu hỏi vận hành |
| --- | --- |
| Desired vs actual capacity | Group có đủ số VM theo mục tiêu không? |
| Healthy/in-service instances | Bao nhiêu VM thực sự sẵn sàng nhận traffic? |
| Pending/launching instances | VM mới mất bao lâu để boot và bootstrap? |
| Launch/terminate failure | Có lỗi quota, IP, image, KMS, permission hoặc capacity không? |
| Replacement rate | Có VM bị thay liên tục do health check sai hoặc lỗi ứng dụng không? |
| Template revision per VM | Fleet có đang chạy nhiều revision ngoài dự kiến không? |
| Zone distribution | Thành viên có phân bố đúng và còn đủ capacity khi một zone lỗi không? |
| Scale-in events | Có request/job bị gián đoạn khi giảm capacity không? |
| Cost and utilization | VM có bị cấp dư hoặc thiếu tài nguyên không? |

Nên thiết lập cảnh báo cho:

- Actual capacity thấp hơn desired trong thời gian dài.
- Healthy capacity xuống dưới ngưỡng phục vụ.
- Launch failure tăng đột biến.
- Nhiều instance bị terminate hoặc replace liên tiếp.
- Một zone mất capacity hoặc group phân bố lệch kéo dài.
- Rollout không tiến triển hoặc dừng do health check.
- Thành viên chạy template revision cũ ngoài thời hạn cho phép.

## 13. Các lỗi cấu hình thường gặp

### 13.1. Group không tạo đủ instance

Nguyên nhân có thể là quota, capacity zone, subnet hết IP, image không tồn tại, KMS key không truy cập được, IAM thiếu quyền hoặc startup configuration không hợp lệ.

Hướng kiểm tra:

1. Xem group activity/event và lỗi launch cụ thể.
2. Kiểm tra quota, zone capacity và instance type.
3. Xác minh image/template version còn tồn tại.
4. Kiểm tra subnet address capacity và security policy.
5. Kiểm tra quyền đọc image, dùng encryption key và gắn network.
6. Xem log bootstrap của một instance thử nghiệm.

### 13.2. VM được tạo nhưng unhealthy

Có thể do grace period quá ngắn, health endpoint sai, ứng dụng khởi động chậm, dependency chưa sẵn sàng hoặc security group chặn probe.

Không tăng grace period vô hạn để che lỗi. Đo thời gian boot/bootstrap, sửa readiness endpoint và kiểm tra đường probe từ load balancer/health service.

### 13.3. Template mới không áp dụng cho thành viên hiện tại

Thay đổi template có thể chỉ ảnh hưởng các VM tạo sau đó. Cần kiểm tra update policy, instance refresh hoặc rolling upgrade đã được kích hoạt chưa, và revision nào được group tham chiếu.

### 13.4. Scale-in làm gián đoạn ứng dụng

Nếu request hoặc job bị cắt, kiểm tra connection draining, lifecycle hook, shutdown timeout và cơ chế checkpoint. Với queue worker, cần bảo đảm message đang xử lý có thể được retry an toàn.

### 13.5. Fleet có cấu hình không đồng nhất

Kiểm tra template revision, user-data, image digest, package runtime và thay đổi thủ công. Chuẩn hóa bằng image mới và rollout có kiểm soát; không dựa vào việc sửa tay từng VM.

## 14. Những sai lầm thường gặp

- Dùng template trỏ tới image alias thay đổi mà không kiểm soát version.
- Đưa secret dài hạn vào user data hoặc metadata.
- Coi trạng thái VM running là ứng dụng healthy.
- Đặt health check quá nông hoặc phụ thuộc quá nhiều dịch vụ phụ.
- Không cấu hình grace period cho startup dài.
- Thay template nhưng không rollout thành viên hiện tại.
- Dùng local disk để lưu dữ liệu nghiệp vụ duy nhất.
- Không drain connection trước scale-in.
- Bảo vệ mọi instance khỏi scale-in vô thời hạn.
- Không kiểm tra subnet IP, quota và capacity trước khi bật autoscaling.
- Đặt tất cả VM vào một zone dù yêu cầu chịu lỗi nhiều zone.
- Cho phép drift thủ công khiến các thành viên cùng group khác cấu hình.
- Để group liên tục tạo rồi xóa VM khi image/bootstrap có lỗi chung.

## 15. Checklist thiết kế managed instance group

**Template**

- [ ] Image ID/version được pin và đã kiểm thử.
- [ ] Machine type, kiến trúc và accelerator phù hợp workload.
- [ ] Boot/data disk có loại, dung lượng, mã hóa và delete policy rõ ràng.
- [ ] Network, subnet, firewall/security group và IP mode đúng thiết kế.
- [ ] Workload identity có quyền tối thiểu.
- [ ] Startup/bootstrap idempotent, có timeout và không chứa secret dài hạn.
- [ ] Tags/labels, monitoring và logging được cấu hình.

**Group**

- [ ] Min, desired và max capacity phù hợp.
- [ ] Health check kiểm tra readiness đúng tầng.
- [ ] Grace period đủ cho boot/bootstrap.
- [ ] Zone distribution và capacity dự phòng đáp ứng yêu cầu.
- [ ] Update/refresh policy có batch, surge và unavailable limit rõ ràng.
- [ ] Scale-in có draining, shutdown hook và checkpoint.
- [ ] Có cách xử lý instance protection và lifecycle.

**Vận hành**

- [ ] Có alarm cho launch failure và healthy capacity.
- [ ] Theo dõi template revision của từng thành viên.
- [ ] Có quy trình rollback khi rollout thất bại.
- [ ] Có inventory và phát hiện drift.
- [ ] Dữ liệu nghiệp vụ tồn tại độc lập với VM có thể bị thay thế.
- [ ] Đã thử scale-out, scale-in, autohealing và lỗi zone trong môi trường kiểm thử.

## 16. Quy trình thay đổi template an toàn

1. Xác định mục tiêu thay đổi: vá OS, nâng runtime, đổi size, network hoặc identity.
2. Tạo image/template revision mới, không sửa mơ hồ cấu hình đang chạy.
3. Quét image, kiểm thử bootstrap và kiểm tra quyền.
4. Tạo nhóm thử nghiệm hoặc triển khai canary với một số ít thành viên.
5. Xác minh boot, readiness, network, storage, logging và metric ứng dụng.
6. Bắt đầu rolling update với giới hạn surge/unavailable phù hợp.
7. Theo dõi healthy capacity, lỗi, latency, throughput và chi phí.
8. Dừng rollout nếu health hoặc SLO xấu đi; rollback template hoặc traffic.
9. Xác minh toàn fleet chạy revision dự kiến.
10. Đánh dấu revision cũ deprecated và lưu thông tin phục vụ audit/rollback theo retention.

## 17. Nguyên tắc vận hành

1. **Một nguồn cấu hình rõ ràng:** dùng template/version làm chuẩn tạo VM thành viên.
2. **Thiết kế thành viên có thể thay thế:** lưu trạng thái nghiệp vụ ngoài vòng đời VM.
3. **Duy trì desired capacity có quan sát:** theo dõi cả desired, actual và healthy capacity.
4. **Health check đúng tầng:** phân biệt infrastructure, guest và application readiness.
5. **Phân phối qua failure domain:** cân bằng zone, latency, transfer cost và availability.
6. **Version hóa và rollout:** thay đổi template phải có update strategy và khả năng rollback.
7. **Shutdown có kiểm soát:** drain request, hoàn tất job và checkpoint trước scale-in.
8. **Quyền tối thiểu:** gắn workload identity riêng, tránh credential dài hạn trong template.
9. **Kiểm soát drift:** hạn chế sửa tay và đối chiếu runtime với baseline.
10. **Kiểm thử vòng đời:** thử launch, replace, scale, update và zone failure trước production.

Managed instance group kết hợp một controller duy trì số lượng máy với template mô tả cấu hình của từng thành viên. Khi template được version hóa, health check phản ánh đúng khả năng phục vụ và ứng dụng chịu được việc thay thế VM, fleet có thể mở rộng và phục hồi nhất quán hơn. Việc quản lý disk, identity, network, bootstrap, rollout và scale-in cẩn thận giúp nhóm máy vừa đáp ứng tải vừa giữ được dữ liệu, độ sẵn sàng và chi phí trong giới hạn mong muốn.
