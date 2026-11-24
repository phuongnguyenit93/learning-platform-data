# Tạo custom image rồi triển khai lại máy từ image

Custom image là bản mẫu đã được chuẩn bị từ một máy hoặc đĩa hệ thống, có thể dùng để tạo các máy mới với hệ điều hành, runtime, agent và phần mềm nền nhất quán. Thay vì cài đặt thủ công từng máy, đội vận hành chuẩn hóa một máy nguồn, tạo image có phiên bản, kiểm tra image rồi dùng image đó để triển khai máy mới. Cách làm này giúp rút ngắn thời gian cấp compute, giảm sai khác cấu hình và tạo cơ sở cho quy trình cập nhật hoặc rollback.

Image chỉ có giá trị khi máy được tạo từ nó khởi động đúng, nhận cấu hình riêng, kết nối được dependency và đáp ứng yêu cầu bảo mật. Nếu image chứa hostname, machine identity, credential, khóa riêng hoặc dữ liệu runtime của máy nguồn, các máy được tạo ra có thể trùng danh tính hoặc vô tình kế thừa quyền truy cập. Vì vậy, quy trình tạo image cần có bước chuẩn bị, làm sạch trạng thái máy, capture, kiểm tra, triển khai thử và quản lý vòng đời.

Bài học này thuộc chương **Thực hành triển khai và vận hành** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong thực hành compute, custom image là nền tảng để tạo máy ảo có cấu hình lặp lại, triển khai theo nhóm và phục hồi nhanh khi cần thay thế instance.

## 1. Custom image là gì?

### 1.1. Image như một bản mẫu máy

Custom image là artifact mô tả nội dung cần thiết để khởi tạo một máy tính mới. Tùy nền tảng, image có thể bao gồm:
- Hệ điều hành và boot configuration.
- Phân vùng hoặc boot disk.
- Kernel, driver và thư viện hệ thống.
- Runtime như Java, Python, .NET hoặc web server.
- Agent giám sát, logging và quản lý cấu hình.
- Package nền tảng và cấu hình bảo mật.
- Một số file cấu hình mặc định không chứa secret.
- Metadata hoặc cấu hình khởi tạo được nền tảng hỗ trợ.

Khi triển khai máy từ image, nền tảng tạo boot disk hoặc các disk cần thiết từ nội dung image, sau đó gắn tài nguyên compute và khởi động máy theo cấu hình được yêu cầu.

### 1.2. Phân biệt image, snapshot và backup

| Thành phần | Mục đích chính | Nội dung thường có | Khi sử dụng |
|---|---|---|---|
| Custom image | Tạo máy mới có cấu hình nền chuẩn | OS, package, runtime, boot disk và metadata cần thiết | Provision máy mới, scale-out, thay máy |
| Disk snapshot | Lưu trạng thái một disk tại một thời điểm | Block data của disk | Khôi phục disk hoặc tạo disk mới |
| Backup | Bảo vệ dữ liệu và hỗ trợ recovery theo policy | Có thể gồm nhiều disk, database, file, metadata và retention | Khôi phục sau xóa nhầm, hỏng dữ liệu hoặc thảm họa |
| Machine template | Mô tả cấu hình máy khi triển khai | Image reference, machine type, network, identity, disk và metadata | Tạo máy nhất quán từ image |
| Container image | Đóng gói ứng dụng và dependency cho container runtime | Filesystem/layers và entrypoint | Chạy container trên VM hoặc managed container platform |

Custom image không mặc nhiên là bản backup đầy đủ. Image có thể không bao gồm data disk tách rời, database managed, object storage, secret, khóa mã hóa hoặc trạng thái của ứng dụng nằm ở dịch vụ khác. Cần xác định rõ mục tiêu: tạo máy mới hay bảo vệ dữ liệu.

### 1.3. Golden image

Golden image là image chuẩn được tổ chức phê duyệt để dùng làm nền tảng triển khai. Image này thường:
- Dùng phiên bản OS còn được hỗ trợ.
- Đã cài patch và package nền tảng.
- Được harden theo baseline bảo mật.
- Có agent và cấu hình logging/monitoring cần thiết.
- Không chứa credential hoặc dữ liệu định danh riêng của một máy.
- Được kiểm thử và gắn phiên bản.
- Có owner, ngày tạo, thời hạn hỗ trợ và quy trình thay thế.

Golden image có thể là nền cho nhiều workload, nhưng không nên cố gắng nhồi mọi ứng dụng vào một image khổng lồ. Image theo vai trò như web, worker, database-client hoặc gpu-compute giúp giảm package dư thừa và giới hạn bề mặt tấn công.

## 2. Quy trình tổng thể

Quy trình tạo image và triển khai lại máy thường gồm các bước:

1. Xác định workload, hệ điều hành, kiến trúc CPU và yêu cầu runtime.
2. Tạo máy nguồn hoặc build máy tạm từ image nền đáng tin cậy.
3. Cài patch, agent, package và cấu hình bảo mật.
4. Loại bỏ secret, dữ liệu tạm và machine-specific identity.
5. Generalize máy theo yêu cầu của OS/nền tảng.
6. Tạo custom image và ghi metadata/version.
7. Kiểm tra trạng thái image, disk snapshot và encryption.
8. Tạo máy mới từ image với cấu hình compute/network/identity phù hợp.
9. Kiểm tra boot, cloud-init, dịch vụ, logging và kết nối.
10. Thử nghiệm ứng dụng, sau đó chuyển traffic hoặc workload.
11. Giữ phương án rollback và quản lý vòng đời image.

~~~mermaid
flowchart TD
    A["Chọn image nền và yêu cầu workload"]
    B["Tạo máy nguồn"]
    C["Patch, cài runtime, agent và hardening"]
    D["Làm sạch secret và machine identity"]
    E["Generalize / chuẩn bị capture"]
    F["Capture custom image và gắn version"]
    G["Kiểm tra image, disk và encryption"]
    H["Tạo máy mới từ image"]
    I["Boot test và xác minh cấu hình"]
    J["Deploy ứng dụng và kiểm tra nghiệp vụ"]
    K["Cutover hoặc đưa vào pool"]
    L["Theo dõi, rollback và quản lý image"]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J --> K --> L
~~~

Không bỏ qua bước kiểm tra sau capture. Một image có trạng thái available hoặc ready mới chỉ cho biết nền tảng đã hoàn tất thao tác tạo artifact; chưa chứng minh máy tạo từ image sẽ chạy đúng ứng dụng.

## 3. Lập kế hoạch trước khi tạo image

### 3.1. Xác định mục tiêu sử dụng

Trước tiên, trả lời:
- Image dùng cho VM web, worker, batch, HPC hay máy quản trị?
- Máy sẽ chạy một ứng dụng hay nhiều workload?
- Có cần giữ dữ liệu local trên boot disk không?
- Data disk có được tạo riêng từ snapshot hoặc backup không?
- Máy cần truy cập private network, internet hay cả hai?
- Có dùng GPU, accelerator hoặc driver đặc thù không?
- Image có cần dùng ở nhiều zone, region hoặc account/project không?
- Ai được tạo, chia sẻ, dùng và xóa image?

Một image dùng cho nhiều vai trò có thể làm tăng kích thước, thời gian boot và số package không cần thiết. Nên giữ image nền nhỏ, sau đó dùng cloud-init, startup script, configuration management hoặc deployment pipeline để cài cấu hình ứng dụng phù hợp.

### 3.2. Kiểm tra tương thích

Ghi nhận các thuộc tính:
- OS distribution và phiên bản.
- CPU architecture: x86_64 hoặc ARM64.
- Boot mode: BIOS/UEFI và yêu cầu Secure Boot nếu có.
- Disk controller và driver.
- Network driver.
- GPU/accelerator driver và runtime.
- Kernel version.
- Filesystem và partition layout.
- Agent quản lý máy và phiên bản.
- Giới hạn instance family hoặc loại máy được hỗ trợ.

Image x86_64 không thể mặc nhiên chạy trên instance ARM64. Image có driver hoặc kernel module đặc thù có thể không tương thích với một machine family khác. Cần kiểm tra compatibility matrix của nền tảng và workload.

### 3.3. Chọn nguồn image đáng tin cậy

Dùng image nền:
- Đến từ publisher hoặc repository được xác minh.
- Có chữ ký hoặc checksum khi nền tảng cung cấp.
- Còn hỗ trợ bảo mật.
- Có phiên bản và ngày phát hành rõ.
- Phù hợp region, architecture và license.
- Không có package lỗi thời hoặc không cần thiết.

Không dùng một image không rõ nguồn gốc chỉ vì nó đã có sẵn runtime mong muốn. Image nền là gốc của chuỗi cung ứng phần mềm; lỗ hổng hoặc backdoor trong đó sẽ được nhân rộng sang mọi máy được tạo ra.

### 3.4. Xác định cấu hình nằm trong image và cấu hình lúc deploy

| Nên đóng gói trong image | Nên truyền khi triển khai |
|---|---|
| OS và patch nền | Hostname hoặc instance name |
| Runtime và package ổn định | Environment và region |
| Agent cần có trên mọi máy | Endpoint theo môi trường |
| CA bundle công khai đã phê duyệt | Secret và credential |
| Baseline hardening | Workload identity hoặc instance role |
| Script khởi tạo chung | User data/cloud-init riêng |
| Ứng dụng nếu release theo image | Version/feature flag theo deployment |

Image nên chứa phần tương đối ổn định. Cấu hình thay đổi theo môi trường, danh tính và secret cần được cấp tại runtime bằng cơ chế phù hợp.

## 4. Chuẩn bị máy nguồn

### 4.1. Tạo máy build tạm

Có thể tạo một VM tạm từ image nền trong subnet hoặc project build riêng. Máy nguồn nên:
- Có quyền truy cập package repository cần thiết.
- Có network egress được kiểm soát.
- Dùng identity riêng chỉ đủ quyền cài đặt và tải artifact.
- Không có quyền truy cập dữ liệu production không cần thiết.
- Có logging để truy vết các thay đổi.
- Có thể xóa sau khi image được kiểm tra.

Không dùng một máy production đang phục vụ người dùng làm máy build nếu không có quy trình bảo trì và kiểm soát downtime phù hợp.

### 4.2. Cập nhật hệ điều hành

Thực hiện:
- Cài security update và bug fix được phê duyệt.
- Gỡ package không còn dùng.
- Kiểm tra kernel và bootloader.
- Cài timezone/locale theo yêu cầu workload.
- Kiểm tra NTP/time synchronization.
- Kiểm tra filesystem và dung lượng.
- Khởi động lại nếu patch yêu cầu, sau đó xác minh máy hoạt động ổn định.

Không chỉ kiểm tra package manager báo thành công. Cần xác minh phiên bản kernel đang chạy và các service cần thiết sau reboot.

### 4.3. Cài runtime và dependency

Cài các thành phần mà mọi máy thuộc vai trò này cần:
- Runtime đúng phiên bản.
- Package hệ thống và thư viện native.
- Agent giám sát và log.
- Security/endpoint agent theo policy.
- Certificate authority bundle công khai.
- Tool chẩn đoán cần thiết nhưng không dư thừa.
- Driver tương thích nếu workload cần accelerator.

Ghi lại phiên bản package và nguồn cài. Nếu dùng repository bên ngoài, cần pin version hoặc dùng artifact repository nội bộ để tái lập build.

### 4.4. Cài ứng dụng hay chỉ cài nền tảng?

Có hai hướng phổ biến:

**Image chứa cả ứng dụng:** phù hợp khi cần deploy một release bất biến và kiểm soát chặt phiên bản. Mỗi release ứng dụng tạo một image mới. Ưu điểm là khởi động nhanh và dễ rollback theo image version. Nhược điểm là image phải được build lại cho mỗi release.

**Image chỉ chứa OS và runtime:** ứng dụng được triển khai sau khi máy khởi động qua deployment agent hoặc pipeline. Cách này tách vòng đời nền tảng khỏi ứng dụng nhưng làm bootstrapping phức tạp hơn và có thể tăng thời gian provision.

Có thể kết hợp: đóng gói ứng dụng ổn định vào image, còn cấu hình môi trường và secret được cấp khi triển khai.

### 4.5. Hardening máy nguồn

Áp dụng baseline phù hợp:
- Tắt service và port không cần.
- Cấu hình firewall host.
- Giới hạn SSH/RDP.
- Tắt login root hoặc tài khoản mặc định nếu policy yêu cầu.
- Dùng user không đặc quyền cho ứng dụng.
- Áp dụng quyền file và thư mục.
- Bật audit và log cần thiết.
- Cấu hình cập nhật bảo mật.
- Giữ agent quản lý và bảo mật ở trạng thái hoạt động.
- Không lưu private key hoặc credential dùng chung.

Hardening phải tương thích với cách nền tảng quản lý máy. Ví dụ, tắt một agent hoặc endpoint cần thiết có thể làm mất khả năng quản trị sau khi tạo VM mới.

## 5. Làm sạch dữ liệu và machine-specific identity

### 5.1. Vì sao phải generalize?

Máy nguồn có thể chứa các giá trị duy nhất:
- Hostname.
- Machine ID.
- SSH host key.
- Windows SID hoặc thông tin domain join.
- Cloud instance ID và metadata cache.
- DHCP lease và network state.
- Log, temporary file và cache.
- Credential hoặc token được cấp riêng.
- Certificate riêng của máy.
- Agent registration ID.

Nếu capture nguyên trạng, nhiều máy được tạo từ cùng image có thể dùng chung identity hoặc gửi heartbeat với cùng machine ID. Điều này gây nhầm lẫn trong monitoring, quản lý cấu hình, bảo mật và audit.

### 5.2. Generalize không có nghĩa xóa mọi agent

Cần phân biệt:
- **Machine identity:** phải được tạo lại cho từng instance.
- **Agent software:** thường cần giữ để máy mới có thể đăng ký với control plane.
- **Agent registration/token:** có thể phải xóa hoặc reset trước capture để máy mới đăng ký riêng.
- **Cloud-init hoặc provisioning agent:** thường cần giữ và chuẩn bị để chạy ở lần boot tiếp theo.

Không xóa binary của cloud agent, SSM/management agent hoặc monitoring agent nếu chúng là thành phần bắt buộc. Hãy dùng quy trình de-register/reset được nhà cung cấp hoặc agent hỗ trợ.

### 5.3. Làm sạch Linux

Các bước thường được cân nhắc:
- Xóa shell history và file tạm theo policy.
- Xóa credential build và token.
- Xóa cache package không cần.
- Reset machine-id theo hướng dẫn distribution.
- Xóa SSH host key để hệ thống tạo lại ở lần boot.
- Làm sạch cloud-init state/log nếu cần.
- Xóa DHCP lease và network configuration gắn với máy nguồn khi phù hợp.
- Xóa registration identity của agent nếu agent yêu cầu.
- Giữ cấu hình cloud-init, cloud agent và driver cần thiết.

Trên một số distribution dùng systemd, có thể cần làm sạch /etc/machine-id theo hướng dẫn của OS để máy mới tạo machine ID riêng. Cách thực hiện khác nhau giữa distribution; không tự xóa file tùy tiện khi chưa xác định cơ chế boot và systemd của image.

Cloud-init có lệnh cloud-init clean để reset trạng thái cho lần khởi tạo sau. Tùy phiên bản, các tùy chọn như làm sạch log hoặc machine-id có thể khác nhau. Kiểm tra cloud-init clean --help và tài liệu của distribution trước khi chạy. Không xóa cloud-init package hoặc datasource config nếu nền tảng cần nó để cấp hostname, SSH key hoặc user data.

### 5.4. Làm sạch Windows

Với Windows image dùng để tạo nhiều VM:
- Cài update và driver cần thiết.
- Kiểm tra Windows activation và licensing model.
- Xóa dữ liệu người dùng và credential build.
- Gỡ domain membership hoặc xử lý theo quy trình image của tổ chức.
- Xóa certificate/machine credential riêng nếu không được dùng chung.
- Chuẩn bị agent và driver cho lần boot mới.
- Chạy Sysprep generalize theo yêu cầu của nền tảng và phiên bản Windows.

Sysprep thường được dùng để generalize Windows trước khi capture. Thực hiện đúng quy trình được hỗ trợ; một số thao tác sau khi generalize có thể khiến máy không còn ở trạng thái capture hợp lệ. Không khởi động lại máy nguồn theo cách tùy tiện sau bước shutdown/generalize.

### 5.5. Secret và credential

Không để trong image:
- Password người dùng hoặc database.
- Cloud access key.
- API token.
- Private SSH key.
- Private TLS key.
- Credential registry.
- File .env production.
- Token đăng ký agent dùng chung.
- Service account key.

Nếu phát hiện credential đã từng được đóng gói vào image hoặc layer, cần coi credential đó đã lộ. Thu hồi/rotate, kiểm tra lịch sử image và registry, rồi tạo image mới sạch. Xóa file trong một layer mới không loại bỏ dữ liệu khỏi layer cũ.

## 6. Đảm bảo tính nhất quán khi capture

### 6.1. Image từ boot disk và data disk

Cần xác định image sẽ chứa:
- Chỉ boot disk.
- Boot disk cùng các data disk được hỗ trợ.
- Snapshot của nhiều disk được liên kết.
- Một tập disk được capture tại cùng một thời điểm logic.

Không mặc định custom image bao gồm tất cả volume gắn với máy nguồn. Một số nền tảng chỉ capture boot disk; một số hỗ trợ nhiều disk hoặc cho phép chọn disk mapping.

Data disk chứa database hoặc dữ liệu người dùng nên có backup riêng và quy trình consistency phù hợp. Image máy không thay thế backup application-consistent.

### 6.2. Crash-consistent và application-consistent

- **Crash-consistent:** trạng thái disk tương tự máy bị dừng đột ngột. Filesystem hoặc database có thể cần recovery journal/log khi boot.
- **Filesystem-consistent:** dữ liệu filesystem đã được flush hoặc freeze theo cơ chế được hỗ trợ.
- **Application-consistent:** ứng dụng được phối hợp để flush buffer, hoàn tất transaction hoặc tạm dừng ghi trước khi snapshot.

Nếu máy nguồn đang chạy database hoặc xử lý file, cần quiesce ứng dụng hoặc dùng native backup. Capture image trong khi dữ liệu đang thay đổi có thể tạo trạng thái không nhất quán.

### 6.3. Dừng máy hay capture khi đang chạy?

Nền tảng có thể hỗ trợ capture khi VM đang chạy, dừng hoặc sau khi generalize. Quy trình chính xác phụ thuộc nhà cung cấp và loại disk.

Nguyên tắc:
- Đọc yêu cầu capture của nền tảng.
- Dừng hoặc quiesce ứng dụng có state.
- Flush filesystem nếu cần.
- Chọn chế độ reboot/no-reboot theo mục tiêu và semantics của API.
- Ghi nhận downtime hoặc ảnh hưởng.
- Xác minh snapshot hoàn tất trước khi thay đổi máy nguồn.

Chế độ không reboot có thể giảm gián đoạn nhưng không tự bảo đảm application consistency. Chỉ dùng khi workload và nền tảng cho phép.

### 6.4. Kiểm tra sau capture

Xác minh:
- Image có trạng thái ready/available.
- Tất cả snapshot/disk mapping đã hoàn tất.
- Architecture và boot mode đúng.
- Encryption và key reference đúng.
- Image có owner/project/account chính xác.
- Version và source image được ghi nhận.
- Image không chứa secret hoặc dữ liệu tạm.
- Có thể chọn image khi tạo máy ở target region/zone phù hợp.

## 7. Tạo custom image trên cloud

### 7.1. Quy trình chung

Dù tên API khác nhau, quy trình thường có các bước:
1. Chọn VM hoặc disk nguồn.
2. Kiểm tra quyền tạo image và quyền dùng encryption key.
3. Generalize hoặc chuẩn bị OS theo yêu cầu.
4. Dừng/quiesce máy nếu quy trình yêu cầu.
5. Gọi thao tác capture/create image.
6. Chờ nền tảng tạo image và snapshot liên quan.
7. Gắn tên, version, owner, source và metadata.
8. Cấp quyền chia sẻ image đúng phạm vi.
9. Thử tạo VM từ image.

Image thường là resource bất biến hoặc gần bất biến sau khi tạo. Khi cần thay đổi package hoặc patch, nên tạo version mới thay vì sửa nội dung image đã phát hành.

### 7.2. Ví dụ với Amazon EC2 AMI

Trong AWS, Amazon Machine Image (AMI) dùng làm mẫu để khởi chạy EC2 instance. Có thể tạo AMI từ instance đã chuẩn bị.

Ví dụ lệnh minh họa:

~~~bash
aws ec2 create-image \
  --instance-id i-0123456789abcdef0 \
  --name "compute-api-2026-11-22-v1" \
  --description "Approved compute API image version 1"
~~~

Thay instance ID và tên theo môi trường thực tế. Theo hành vi mặc định của API, EC2 cố gắng shutdown instance sạch trước khi tạo image rồi khởi động lại instance; cần kiểm tra tác động và trạng thái ứng dụng trước khi thực hiện. Tham số --no-reboot có thể tránh reboot nhưng tăng trách nhiệm bảo đảm tính nhất quán của dữ liệu.

Sau khi tạo, có thể kiểm tra image:

~~~bash
aws ec2 describe-images \
  --owners self \
  --filters "Name=name,Values=compute-api-2026-11-22-v1"
~~~

Không coi lệnh trả về image ID là bằng chứng image đã được kiểm thử. Chờ trạng thái image/snapshot hoàn tất rồi tạo một instance thử.

### 7.3. Ví dụ với Azure Compute

Trong Azure, có thể dùng managed image hoặc Azure Compute Gallery tùy mục tiêu phân phối và versioning. Quy trình tổng quát:
- Chuẩn bị VM nguồn.
- Deallocate và generalize nếu tạo image generalized.
- Capture thành managed image hoặc version trong Compute Gallery.
- Gắn replication region và quyền chia sẻ theo nhu cầu.
- Tạo VM mới từ image/version đã phát hành.

Generalized image và specialized image có semantics khác nhau. Generalized image thường yêu cầu OS được generalize; specialized image có thể giữ trạng thái máy và identity, nên không phù hợp để tạo hàng loạt máy độc lập nếu không xử lý identity. Chọn loại image theo tài liệu nền tảng và mục tiêu triển khai.

### 7.4. Ví dụ với Google Cloud

Trong Google Cloud, custom image có thể được tạo từ boot disk hoặc nguồn được hỗ trợ. Quy trình thường gồm:
- Chuẩn bị OS và guest environment.
- Dừng instance hoặc disk theo yêu cầu capture.
- Tạo custom image từ disk nguồn.
- Gắn family/label/description phù hợp.
- Tạo instance mới từ custom image.
- Kiểm tra startup script, guest agent và network.

Nếu tạo image Windows hoặc image có ứng dụng cần generalize, thực hiện quy trình OS-specific trước capture. Kiểm tra trạng thái image và khả năng boot trên machine type/zone dự kiến.

### 7.5. Khác biệt giữa nhà cung cấp

| Khái niệm | AWS | Azure | Google Cloud |
|---|---|---|---|
| Image máy ảo | AMI | Managed Image / Compute Gallery image version | Custom image |
| Nguồn capture thường gặp | EC2 instance và EBS snapshots | Generalized VM hoặc disk theo loại image | Boot disk |
| Phân phối | Chia sẻ AMI, copy region/account | Gallery replication và sharing | IAM permissions, image availability theo scope |
| Tạo máy mới | EC2 RunInstances | Create VM from image/version | Compute Engine instance from image |
| Điểm cần chú ý | Reboot behavior, block device mapping, snapshot encryption | Generalized/specialized, Sysprep, gallery version | Guest environment, OS preparation, image family |

Tên resource và yêu cầu capture có thể thay đổi theo loại image, OS và tính năng nền tảng. Luôn kiểm tra tài liệu hiện hành của cloud trước khi chạy lệnh trên production.

## 8. Quản lý version và metadata của image

### 8.1. Quy tắc đặt tên

Tên image nên giúp xác định:
- Workload hoặc role.
- OS và major version.
- Architecture.
- Phiên bản image.
- Ngày hoặc release identifier.

Ví dụ:
- compute-api-ubuntu24-x86-v1.4.0
- batch-worker-rocky9-x86-v2026.11
- gpu-training-ubuntu22-arm64-v2.1.0

Không đặt secret, thông tin cá nhân hoặc tên khách hàng nhạy cảm trong image name/description.

### 8.2. Metadata và tag

Nên gắn metadata:
- owner hoặc team sở hữu.
- workload hoặc role.
- os và os_version.
- architecture.
- image_version.
- source_image.
- build_id hoặc pipeline run.
- created_at.
- security_baseline.
- approval_status.
- support_until hoặc lifecycle date.

Metadata giúp audit, truy vết image, tìm phiên bản cần vá và dọn image cũ. Không dùng tag thay thế quyền truy cập; IAM/resource policy vẫn phải giới hạn ai được dùng hoặc xóa image.

### 8.3. Immutable versioning

Một image đã phát hành nên được xem là immutable. Khi thay đổi:
- Tạo version mới.
- Ghi source image và build input.
- Chạy scan và test.
- Phê duyệt version mới.
- Chuyển deployment template sang version mới.
- Giữ version trước trong thời gian rollback.
- Xóa version hết hạn theo policy.

Không thay nội dung dưới cùng một version label nếu deployment cần khả năng tái lập. Nếu tên hoặc alias trỏ tới image mới, cần ghi rõ đó là alias mutable và kiểm soát thay đổi.

### 8.4. Image family và channel

Có thể phân phối image theo channel:
- dev: image đang thử nghiệm.
- staging: image đã qua kiểm thử tích hợp.
- stable: image được phê duyệt cho production.
- lts: image được hỗ trợ dài hạn.

Channel giúp pipeline chọn image phù hợp, nhưng phải giữ ID/version bất biến trong một lần rollout. Không để một deployment kéo alias mới giữa chừng làm các máy trong cùng nhóm chạy image khác nhau.

## 9. Bảo vệ image, encryption và quyền chia sẻ

### 9.1. Image có thể chứa dữ liệu nhạy cảm

Image có thể vô tình chứa:
- Log có token hoặc dữ liệu người dùng.
- SSH key hoặc private key.
- File cấu hình production.
- Database dump.
- Cache chứa dữ liệu nhạy cảm.
- Credential trong shell history.
- Artifact nội bộ chưa được phép chia sẻ.

Trước khi phát hành, scan filesystem và kiểm tra secret. Dùng quy trình kiểm tra artifact tự động nếu có.

### 9.2. Encryption at rest

Boot snapshot hoặc image backing storage có thể được mã hóa bằng key do cloud quản lý hoặc customer-managed key. Cần kiểm tra:
- Image và snapshot có encryption không.
- Key thuộc account/project nào.
- Principal tạo VM có quyền sử dụng key không.
- Key có được phép dùng ở region đích không.
- Quy trình copy/share image có giữ encryption hay cần re-encrypt.
- Khóa có lifecycle phù hợp với retention image không.

Nếu xóa hoặc disable key đang bảo vệ image, máy mới có thể không tạo được hoặc không đọc được disk. Không xóa key chỉ vì image đã cũ nếu image/backup còn cần cho rollback hoặc recovery.

### 9.3. Chia sẻ image

Khi chia sẻ image giữa account/project:
- Chỉ chia sẻ với principal cần thiết.
- Ưu tiên private sharing.
- Kiểm tra quyền snapshot backing image.
- Xác minh quyền KMS/key.
- Không public image nếu chưa được phê duyệt.
- Thu hồi quyền chia sẻ khi hết nhu cầu.
- Audit việc launch từ image.

Public image có thể làm lộ phần mềm nội bộ, cấu hình hoặc dữ liệu đã bị bỏ sót. Việc image không chứa password rõ ràng không có nghĩa image không chứa thông tin nhạy cảm.

### 9.4. Supply chain và image provenance

Ghi lại:
- Image nền và publisher.
- Package manifest hoặc SBOM nếu quy trình hỗ trợ.
- Pipeline build và source revision.
- Kết quả vulnerability scan.
- Người/phê duyệt phát hành.
- Chữ ký hoặc attestation nếu có.
- Các thay đổi OS/package giữa hai version.

Khi có lỗ hổng mới, metadata giúp xác định image và instance nào bị ảnh hưởng.

## 10. Triển khai máy mới từ custom image

### 10.1. Chọn image version

Trước khi tạo máy:
- Chọn image ID/version đã phê duyệt.
- Kiểm tra OS, architecture và boot mode.
- Kiểm tra region và zone availability.
- Kiểm tra encryption key access.
- Kiểm tra image có tương thích machine type dự kiến.
- Kiểm tra image còn trong support window.

Không dùng tên alias chung nếu không thể xác định chính xác image ID đã dùng trong deployment.

### 10.2. Chọn cấu hình compute

Máy mới cần cấu hình:
- Machine type hoặc instance family.
- vCPU và memory.
- GPU/accelerator nếu cần.
- Boot disk type và size.
- Data disk mapping.
- Network interface.
- Placement/availability zone.
- Quota và reservation nếu cần.

Image không quyết định toàn bộ năng lực compute. Cùng một image có thể chạy trên machine type khác nhau, nhưng ứng dụng phải tương thích và được sizing phù hợp.

### 10.3. Network và security

Cấu hình:
- VPC/VNet và subnet.
- Security group hoặc firewall rule.
- Route và NAT.
- Private endpoint/DNS.
- Load balancer target.
- Public IP nếu thật sự cần.
- Egress policy và network segmentation.

Không sao chép nguyên network identity của máy nguồn. Máy mới cần NIC, IP và hostname riêng. Không mở SSH/RDP hoặc application port ra internet nếu không cần.

### 10.4. Identity và quyền

Gắn identity theo workload:
- Instance profile/role.
- Managed identity.
- Service account.
- Machine identity do nền tảng cấp.
- Quyền đọc secret manager và registry cần thiết.

Không đưa access key tĩnh vào user data hoặc image. Cấp quyền tối thiểu và tách identity giữa build machine, deployment pipeline và máy runtime.

### 10.5. User data và cloud-init

Dùng user data hoặc cloud-init cho các giá trị cần thay theo lần tạo:
- Hostname.
- Environment.
- Endpoint.
- Secret reference.
- Agent registration.
- Startup command.
- Application version hoặc configuration version.

User data có thể được lưu trong metadata hoặc hiển thị cho principal có quyền phù hợp. Không đặt password, token hoặc private key dạng plaintext trong user data. Lấy secret bằng workload identity từ secret manager khi máy đã khởi động.

### 10.6. Ví dụ khởi chạy EC2 từ AMI

Ví dụ lệnh:

~~~bash
aws ec2 run-instances \
  --image-id ami-0123456789abcdef0 \
  --instance-type t3.large \
  --subnet-id subnet-0123456789abcdef0 \
  --security-group-ids sg-0123456789abcdef0 \
  --iam-instance-profile Name=compute-api-role \
  --min-count 1 \
  --max-count 1
~~~

Các ID ở trên chỉ là placeholder minh họa. Trước khi chạy, chọn đúng image ID, instance type, subnet, security group và instance profile của account/region mục tiêu. Có thể bổ sung tag cho instance và volume để truy vết image version, owner và môi trường.

Sau khi lệnh trả về instance ID, chờ trạng thái instance và system checks đạt yêu cầu. Sau đó xác minh SSH/SSM access, cloud-init, agent và application health.

## 11. Kiểm tra máy sau khi boot

### 11.1. Kiểm tra tầng hạ tầng

- Instance ở trạng thái running.
- System/instance status checks đạt.
- Boot disk và data disk đã attach.
- Filesystem mount đúng.
- NIC nhận địa chỉ IP.
- Route, DNS và security policy đúng.
- Time synchronization hoạt động.
- Encryption và metadata đúng kỳ vọng.

### 11.2. Kiểm tra OS và machine identity

Xác minh:
- Hostname mới, không trùng máy nguồn.
- Machine ID mới.
- SSH host key mới nếu quy trình yêu cầu.
- Windows identity/SID và domain join đúng.
- Agent đăng ký instance mới.
- Cloud-init/provisioning không báo lỗi.
- Không còn credential hoặc log riêng của máy nguồn.
- Timezone, locale và kernel đúng.

Nếu hai máy cùng báo một machine ID hoặc agent ID, dừng rollout và xử lý generalization trước khi tạo thêm instance.

### 11.3. Kiểm tra service và dependency

- Service ứng dụng tự khởi động.
- Port lắng nghe đúng.
- Health endpoint trả kết quả mong muốn.
- Database connection thành công.
- Queue/object storage/API kết nối được.
- Secret được lấy bằng identity đúng.
- Monitoring và logging gửi dữ liệu.
- Backup agent hoặc policy đã được áp dụng.
- Không có service không cần thiết đang mở.

### 11.4. Kiểm tra hiệu năng và khả năng lặp lại

Tạo ít nhất một máy thử từ image, sau đó:
- So sánh thời gian boot.
- So sánh package và version.
- Kiểm tra cấu hình runtime.
- Chạy smoke test và workload đại diện.
- Tạo thêm máy thứ hai để kiểm tra identity khác nhau.
- Xác minh hai máy có cùng baseline nhưng hostname, IP và machine identity riêng biệt.

Một image tốt phải tạo ra các máy có baseline tương đương nhưng danh tính và cấu hình instance riêng biệt.

## 12. Thay máy đang chạy bằng máy mới từ image

### 12.1. Không nhất thiết phải cài lại tại chỗ

Với kiến trúc immutable infrastructure, khi cần thay đổi OS hoặc package nền, tạo image mới rồi triển khai máy mới. Sau khi kiểm tra, chuyển workload sang máy mới và loại bỏ máy cũ theo quy trình.

Cách này giúp:
- Có thể tái lập trạng thái máy.
- Dễ rollback về image trước.
- Giảm drift do thay đổi thủ công lâu ngày.
- Dùng cùng image để scale-out.

### 12.2. Rolling replacement

Thay máy từng phần:
1. Tạo một máy mới từ image mới.
2. Chạy health check và smoke test.
3. Đưa máy vào load balancer hoặc pool.
4. Chờ máy healthy và nhận tải.
5. Drain một máy cũ.
6. Xác nhận session/job đã hoàn tất hoặc được chuyển giao.
7. Xóa máy cũ theo policy.
8. Lặp lại tới khi toàn bộ pool dùng image mới.

Rolling replacement giúp giảm downtime nhưng cần đủ capacity trong lúc hai thế hệ máy cùng tồn tại.

### 12.3. Blue-green deployment

Tạo một nhóm máy mới (green) song song với nhóm đang phục vụ (blue):
- Deploy image mới vào green.
- Kiểm thử riêng.
- Chuyển traffic từng phần hoặc toàn bộ.
- Theo dõi lỗi và latency.
- Giữ blue trong thời gian rollback.
- Xóa blue sau khi hết thời gian quan sát và được phê duyệt.

Blue-green cần tính chi phí chạy hai nhóm máy và xử lý dữ liệu/state khi chuyển traffic.

### 12.4. Stateful workload

Với database hoặc ứng dụng giữ dữ liệu local, không thể chỉ tạo máy mới rồi chuyển traffic. Cần:
- Backup/replication dữ liệu.
- Đồng bộ thay đổi cuối.
- Quiesce hoặc chuyển quyền ghi.
- Attach/restore data volume đúng cách.
- Kiểm tra consistency.
- Chuyển leader/endpoint.
- Có failback plan.

Image chứa OS và ứng dụng; dữ liệu bền vững cần được quản lý riêng.

## 13. Rollback khi image mới có lỗi

### 13.1. Rollback theo image version

Nếu image mới lỗi:
- Ngừng tạo thêm máy từ version lỗi.
- Giữ deployment template trỏ tới version đã biết tốt.
- Tạo máy mới từ image trước hoặc khôi phục nhóm máy blue.
- Chuyển traffic theo kế hoạch.
- Giữ log và image lỗi để điều tra nếu policy cho phép.
- Thu hồi image nếu có vấn đề bảo mật nghiêm trọng.

Rollback không tự đảo ngược thay đổi database schema hoặc dữ liệu do ứng dụng mới tạo. Cần compatibility và migration strategy riêng.

### 13.2. Tiêu chí rollback

Có thể đặt ngưỡng:
- Boot failure hoặc instance check fail.
- Application health check fail.
- Error rate tăng.
- p95/p99 latency vượt SLO.
- Agent không đăng ký.
- Database/API connection fail.
- Security scan hoặc policy check không đạt.
- Khác biệt kết quả nghiệp vụ.

Tiêu chí phải được xác định trước rollout để tránh quyết định theo cảm tính khi sự cố xảy ra.

### 13.3. Giữ lại image cũ trong bao lâu?

Retention image cũ phụ thuộc:
- Thời gian quan sát sau release.
- Tốc độ phát hiện lỗi.
- RTO yêu cầu.
- Khả năng tái tạo image.
- Chi phí snapshot/storage.
- Quy định audit và retention.

Không xóa image cũ ngay sau rollout nếu nó còn là đường rollback hoặc cần cho điều tra.

## 14. Quản lý vòng đời và cập nhật image

### 14.1. Patch cadence

Đặt lịch:
- Theo dõi bản cập nhật OS và package.
- Đánh giá CVE ảnh hưởng.
- Build image mới theo baseline.
- Scan image.
- Kiểm thử boot và workload.
- Phê duyệt.
- Rollout theo nhóm.
- Theo dõi instance còn dùng version cũ.
- Retire image hết hỗ trợ.

Không để image tồn tại vô thời hạn chỉ vì vẫn tạo VM được. Image có thể chứa kernel hoặc package đã hết hỗ trợ.

### 14.2. Image drift

Drift xảy ra khi máy được tạo từ cùng image nhưng sau đó bị sửa thủ công khác nhau.

Để giảm drift:
- Dùng configuration management hoặc IaC.
- Hạn chế thay đổi thủ công trên production.
- Ghi lại package/version sau provisioning.
- Dùng image mới cho thay đổi nền tảng.
- Dùng config version để đồng bộ môi trường.
- Thường xuyên thay máy hoặc reconcile về desired state.

### 14.3. Image deprecation và retirement

Trước khi xóa image:
- Tìm instance/template đang tham chiếu image.
- Kiểm tra autoscaling group, scale set hoặc instance template.
- Kiểm tra backup/recovery runbook.
- Kiểm tra account/project khác đang dùng image.
- Thay reference sang version mới.
- Xác nhận không còn phụ thuộc.
- Lưu metadata và audit cần thiết.
- Xóa image và snapshot theo policy.

Xóa image có thể không xóa các instance đã được tạo từ image, nhưng có thể khiến không thể tạo máy mới hoặc rollback về version đó. Cần xác minh semantics của nhà cung cấp.

## 15. Tự động hóa image pipeline

### 15.1. Pipeline tham khảo

Một pipeline có thể gồm:
1. Chọn base image đã phê duyệt.
2. Tạo build instance hoặc build environment.
3. Cài patch và package.
4. Cấu hình runtime và agent.
5. Hardening và generalize.
6. Capture image.
7. Scan vulnerability và secret.
8. Tạo test instance.
9. Chạy smoke/integration test.
10. Gắn approval và phát hành image version.
11. Cập nhật template hoặc deployment pipeline.
12. Theo dõi máy đang chạy và retire version cũ.

### 15.2. Infrastructure as Code

IaC có thể mô tả:
- Image resource hoặc image pipeline.
- VM build instance.
- Disk và encryption.
- Network và security policy.
- IAM/role.
- Instance template/launch template.
- Autoscaling group hoặc scale set.
- Tag và metadata.
- Test environment.

Không hardcode credential trong IaC. Dùng secret reference và workload identity cho pipeline.

### 15.3. Kiểm soát phát hành

Một image chỉ nên được đánh dấu approved khi:
- Build từ nguồn tin cậy.
- Patch và package version được ghi nhận.
- Scan không có finding vượt policy.
- Không phát hiện secret.
- Boot test thành công.
- Agent và monitoring hoạt động.
- Workload smoke test đạt.
- Owner và approval rõ.
- Rollback version có sẵn.

### 15.4. Canary image

Trước khi thay toàn bộ fleet:
- Tạo một hoặc vài máy từ image mới.
- Đưa vào nhóm canary.
- Chuyển một phần traffic hoặc workload.
- Theo dõi metrics và log.
- Mở rộng rollout nếu đạt.
- Rollback nếu vi phạm ngưỡng.

Canary giúp phát hiện vấn đề về driver, kernel, boot, dependency hoặc performance mà kiểm thử build đơn thuần không thấy.

## 16. Tối ưu chi phí và thời gian triển khai

### 16.1. Lợi ích

Custom image có thể giảm:
- Thời gian cài OS và package khi mỗi máy mới khởi động.
- Công sức cấu hình thủ công.
- Sai khác giữa máy.
- Thời gian thay thế máy lỗi.
- Thời gian scale-out của workload cần nhiều dependency nền.

### 16.2. Chi phí cần tính

- Dung lượng image và backing snapshots.
- Replication giữa region.
- Storage retention của nhiều version.
- Build instance và pipeline runtime.
- Scan và test.
- Data transfer.
- Chi phí giữ image cũ để rollback.
- License OS/phần mềm.
- Công sức vận hành và cập nhật.

### 16.3. Giảm image size

- Chỉ cài package cần thiết.
- Xóa package cache và file tạm.
- Không lưu dataset hoặc log runtime.
- Dùng image nền tối thiểu được hỗ trợ.
- Tách image theo vai trò.
- Đưa dữ liệu lớn sang object/storage riêng.
- Không đóng gói tool phát triển vào production image nếu không cần.

Image nhỏ có thể giảm thời gian copy/boot và chi phí lưu trữ, nhưng không được loại bỏ agent hoặc thư viện bảo mật bắt buộc.

## 17. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Image không xuất hiện khi tạo VM | Image chưa ready, sai region hoặc thiếu quyền | Kiểm tra state, owner, sharing và region |
| VM mới không boot | Boot mode, architecture, driver hoặc disk mapping không tương thích | Kiểm tra console log, boot mode, kernel và machine family |
| Máy mới trùng hostname/machine ID | Chưa generalize hoặc cloud-init state chưa được reset | Kiểm tra OS identity và quy trình sysprep/cloud-init |
| Agent báo cùng một ID trên nhiều VM | Agent registration state bị clone | Reset/de-register theo hướng dẫn agent rồi tạo image mới |
| Không đọc được boot disk đã mã hóa | Thiếu quyền KMS/key hoặc key không khả dụng | Kiểm tra key policy, region và principal |
| Cloud-init chạy lại không đúng | Datasource/state hoặc package cloud-init không tương thích | Kiểm tra cloud-init log và image preparation |
| VM boot được nhưng app không chạy | Thiếu secret, endpoint hoặc runtime config | Kiểm tra identity, secret reference, user data và service logs |
| VM không vào được private endpoint | Subnet, route, DNS hoặc firewall sai | Kiểm tra network config của instance mới |
| Image mới chạy chậm | Runtime/package/driver hoặc machine type khác | So sánh benchmark và package manifest |
| Không rollback được | Image cũ đã xóa hoặc key đã bị disable | Kiểm tra retention và dependency của image |
| Máy mới thiếu data disk | Image không chứa disk hoặc mapping không khai báo | Restore/attach data disk theo kế hoạch riêng |
| Nhiều VM cùng dùng credential | Secret bị bake vào image | Thu hồi credential, làm sạch và phát hành image mới |

Khi điều tra, giữ lại image ID, instance ID, build ID, cloud-init log và trạng thái snapshot để truy vết. Không xuất secret hoặc toàn bộ user data nhạy cảm vào log công khai.

## 18. Checklist thực hành

### Chuẩn bị máy nguồn

- [ ] Xác định workload, OS, architecture và machine family mục tiêu.
- [ ] Chọn base image có nguồn gốc và support rõ ràng.
- [ ] Cài patch, runtime, agent và dependency cần thiết.
- [ ] Áp dụng hardening và kiểm tra service.
- [ ] Không lưu credential hoặc dữ liệu production không cần.
- [ ] Xác định disk nào nằm trong image và disk nào backup riêng.

### Generalize và capture

- [ ] Làm sạch hostname, machine ID và identity riêng.
- [ ] Reset agent registration theo hướng dẫn.
- [ ] Chuẩn bị cloud-init hoặc Sysprep đúng OS.
- [ ] Quiesce ứng dụng và đảm bảo consistency.
- [ ] Chọn capture mode phù hợp với downtime và dữ liệu.
- [ ] Chờ image và snapshot hoàn tất.
- [ ] Xác minh encryption, owner, region và architecture.
- [ ] Gắn version, tag, source và build metadata.

### Triển khai máy mới

- [ ] Chọn image ID/version cụ thể.
- [ ] Chọn machine type, disk và placement phù hợp.
- [ ] Cấu hình subnet, route, firewall và DNS.
- [ ] Gắn workload identity với quyền tối thiểu.
- [ ] Cấp secret bằng secret manager hoặc cơ chế an toàn.
- [ ] Truyền user data không chứa credential plaintext.
- [ ] Kiểm tra boot, machine identity, agent và cloud-init.
- [ ] Chạy smoke test và workload test.
- [ ] Tạo máy thứ hai để kiểm tra identity không trùng.

### Rollout và vòng đời

- [ ] Có canary, rolling hoặc blue-green plan.
- [ ] Có tiêu chí rollback đã định trước.
- [ ] Giữ image version trước trong thời gian cần thiết.
- [ ] Theo dõi instance đang dùng image cũ.
- [ ] Có lịch patch, scan và phát hành image mới.
- [ ] Chỉ xóa image khi không còn dependency.
- [ ] Lưu runbook và metadata để tái lập.

## 19. Ghi nhớ

- Custom image là bản mẫu để tạo máy mới có OS, package và runtime nhất quán.
- Image khác snapshot, backup, machine template và container image.
- Chuẩn bị máy nguồn, patch, hardening và kiểm tra tương thích trước capture.
- Generalize giúp mỗi máy mới có hostname, machine ID và agent identity riêng.
- Không xóa agent cần thiết; chỉ reset registration state theo hướng dẫn.
- Secret và credential runtime phải được cấp lúc triển khai, không bake vào image.
- Capture phải tính tới consistency của filesystem, database và nhiều disk.
- Image version nên immutable, có metadata, owner và provenance.
- Khi tạo VM mới, cấu hình compute, disk, network, identity và user data riêng.
- Boot thành công chưa đủ; phải kiểm tra app, dependency, monitoring và security.
- Dùng rolling hoặc blue-green để thay máy có kiểm soát và giữ rollback.
- Image cần patch, scan, kiểm thử, retention và retirement theo vòng đời.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Custom image | Image do tổ chức tạo để làm mẫu triển khai máy mới. |
| Golden image | Image chuẩn đã được phê duyệt về cấu hình và bảo mật. |
| Base image | Image nền được dùng để bắt đầu quá trình build. |
| Machine image | Artifact mô tả OS và disk cần để khởi tạo máy ảo. |
| Snapshot | Ảnh chụp trạng thái disk hoặc volume tại một thời điểm. |
| Backup | Bản sao dữ liệu được giữ theo policy để phục hồi. |
| Generalize | Làm sạch hoặc reset thông tin riêng của máy để image có thể tạo nhiều máy độc lập. |
| Sysprep | Công cụ Windows chuẩn bị hệ điều hành cho triển khai image, gồm generalize theo quy trình hỗ trợ. |
| cloud-init | Công cụ khởi tạo máy Linux theo metadata và user data của nền tảng. |
| Machine ID | Định danh hệ thống duy nhất của một máy. |
| User data | Dữ liệu hoặc script được truyền cho máy khi khởi tạo. |
| Instance profile/role | Danh tính và quyền được gắn với compute instance. |
| Boot disk | Disk chứa OS và dữ liệu cần để khởi động máy. |
| Data disk | Disk chứa dữ liệu ứng dụng hoặc dữ liệu bền vững tách khỏi boot disk. |
| Application-consistent | Trạng thái capture được phối hợp với ứng dụng để đảm bảo dữ liệu hợp lệ. |
| Crash-consistent | Trạng thái tương tự sau khi máy dừng đột ngột. |
| Image version | Phiên bản cụ thể của custom image. |
| Image provenance | Thông tin nguồn gốc, quy trình build và kiểm chứng image. |
| SBOM | Software Bill of Materials, danh mục thành phần phần mềm trong artifact. |
| Immutable infrastructure | Cách vận hành thay máy bằng artifact đã version hóa thay vì sửa lâu dài tại chỗ. |
| Rolling replacement | Thay máy từng phần trong khi hệ thống tiếp tục phục vụ. |
| Blue-green deployment | Duy trì hai nhóm môi trường để chuyển traffic và rollback. |
| Canary deployment | Triển khai thử cho một phần nhỏ workload trước khi mở rộng. |
| Image drift | Sai khác giữa máy thực tế và baseline image/cấu hình mong muốn. |
| Image retirement | Quy trình ngừng phát hành và xóa image đã hết vòng đời. |
