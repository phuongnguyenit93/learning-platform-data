# Đối chiếu image, metadata, danh tính workload và startup script

## 1. Vì sao cần đối chiếu bốn thành phần này?

Khi triển khai một VM trên cloud, image quyết định hệ điều hành và phần mềm nền; metadata cung cấp thông tin về instance và môi trường chạy; workload identity xác định máy được phép truy cập tài nguyên nào; startup script tự động hóa các bước khởi tạo sau khi máy boot. Bốn thành phần này phối hợp để biến một VM vừa được cấp phát thành một workload có thể vận hành.

Các cloud provider cung cấp khái niệm tương tự nhưng tên dịch vụ, định dạng image, API metadata, cơ chế cấp credential và vòng đời startup script khác nhau. Một image hoạt động trên nền tảng này chưa chắc boot được nguyên trạng trên nền tảng khác. Một script lấy thông tin instance từ metadata endpoint của cloud này có thể không chạy ở cloud kia. Một role hoặc service account cũng không thể sao chép trực tiếp sang account hay provider khác.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, việc đối chiếu này giúp lựa chọn và triển khai compute trên nhiều cloud, hiểu khác biệt về CPU, bộ nhớ, mạng, bảo mật và cách vận hành. Mục tiêu là thiết kế workload có thể di chuyển khi cần, đồng thời vẫn tận dụng đúng cơ chế native của từng nền tảng.

Sau bài học, người học có thể:

- Phân biệt machine image, boot disk image, snapshot và image gallery.
- Đối chiếu các khái niệm image của AWS, Microsoft Azure và Google Cloud.
- Nhận diện các khác biệt ảnh hưởng đến portability như firmware, driver, architecture, disk mapping và license.
- Phân biệt instance metadata với user data và startup script.
- So sánh metadata service và cách bảo vệ truy cập metadata trên từng cloud.
- Đối chiếu instance role, managed identity, service account và workload identity federation.
- Thiết kế startup automation có tính idempotent, có log và không chứa secret.
- Lập quy trình đóng gói, import, kiểm thử và migration image giữa các cloud.

## 2. Bức tranh tổng thể

### 2.1. Vai trò của từng thành phần

| Thành phần | Câu hỏi cần trả lời | Ví dụ thông tin/cấu hình |
|---|---|---|
| Image | Máy boot từ hệ điều hành và phần mềm nền nào? | OS, package, agent, bootloader, driver, filesystem |
| Metadata | Máy đang chạy ở đâu và có thuộc tính gì? | Instance ID, zone, region, network interface, user data |
| Workload identity | Máy hoặc ứng dụng được phép làm gì? | Role, managed identity, service account, token |
| Startup script | Cần làm gì khi máy khởi động? | Cài agent, lấy cấu hình, mount volume, khởi chạy service |

Image là nền tảng ban đầu; metadata mô tả runtime context; identity cấp quyền; startup automation nối các thành phần thành một quy trình khởi động. Nếu thiết kế phụ thuộc chặt vào một provider, cần có lớp cấu hình tương ứng khi chuyển cloud.

### 2.2. Phân biệt image, snapshot và machine configuration

- **Image:** mẫu dùng để tạo boot disk hoặc VM; có thể chứa OS và phần mềm đã cài.
- **Disk snapshot:** bản chụp một volume tại thời điểm nhất định; thường dùng để backup hoặc tạo disk mới.
- **Machine image:** có thể bao gồm nhiều disk và một phần cấu hình máy tùy provider.
- **Instance template/launch template:** mô tả cách tạo VM như machine type, image reference, network, metadata và identity; không nhất thiết chứa dữ liệu disk.
- **Infrastructure as Code:** mô tả tài nguyên cần tạo và quan hệ giữa chúng; không thay thế image hoặc backup dữ liệu.

Không nên coi các khái niệm này là tương đương. Khi migration, phải xác định chính xác artifact nào chứa OS, data disk, NIC, security policy, identity và cấu hình khởi tạo.

### 2.3. Control plane và guest operating system

Cloud control plane tạo VM, gắn disk, NIC, security policy và identity. Guest operating system boot, nhận thiết bị, đọc metadata và chạy startup automation. Một VM có thể được tạo thành công ở control plane nhưng không trở nên healthy vì image không tương thích, cloud agent lỗi, script thất bại hoặc identity không lấy được token.

Troubleshooting cần kiểm tra cả hai phía: trạng thái resource trên cloud và log bên trong guest OS.

## 3. Đối chiếu machine image giữa các cloud

### 3.1. AWS: AMI và EBS snapshots

Amazon Machine Image (AMI) là mẫu dùng để khởi chạy EC2 instance. AMI tham chiếu đến cấu hình block device mapping và snapshot cho các EBS-backed volume; AMI có thể xác định boot volume và các volume bổ sung tùy cách tạo. Một số chi tiết như instance store, architecture, virtualization mode, boot mode và quyền chia sẻ ảnh hưởng đến loại instance có thể khởi chạy.

Khi vận hành AMI, cần quản lý:

- Region và architecture của AMI.
- Root device type và block device mapping.
- Snapshot encryption và KMS key policy.
- Boot mode, kernel/driver và yêu cầu instance family.
- Image ownership, sharing permission và lifecycle.
- Versioning, tagging và quy trình cập nhật base image.

AMI là artifact của EC2. Không thể lấy AMI ID rồi dùng trực tiếp làm image reference trên Azure hoặc Google Cloud. Muốn di chuyển, cần export/import disk theo định dạng và quy trình được hỗ trợ, sau đó tạo image native ở nền tảng đích.

### 3.2. Azure: Managed Images và Azure Compute Gallery

Azure hỗ trợ managed image và Azure Compute Gallery để quản lý, version và phân phối image. Gallery phù hợp với việc chuẩn hóa image cho nhiều VM, subscription hoặc region theo quyền chia sẻ được cấu hình.

Khi làm việc với image Azure, cần kiểm tra:

- OS type, OS state và generation (Gen1/Gen2) phù hợp với VM.
- Hyper-V generation, boot mode và khả năng Secure Boot/Trusted Launch nếu dùng.
- OS disk và data disk được mô tả trong image version như thế nào.
- Region replication, target region và quota.
- Disk encryption, encryption set và quyền truy cập.
- Publisher/offer/SKU nếu dùng image từ Marketplace.
- Agent và extension cần có trong guest OS.

Azure Compute Gallery giúp phân phối image version, nhưng không tự chuyển managed identity, NIC, subnet, NSG, role assignment hoặc toàn bộ cấu hình VM sang một cloud khác.

### 3.3. Google Cloud: custom image và machine image

Google Compute Engine có custom image để tạo boot disk và machine image để lưu trạng thái máy cùng cấu hình và disk theo phạm vi được dịch vụ hỗ trợ. Instance template lại mô tả cấu hình dùng để tạo instance hoặc nhóm instance.

Khi làm việc với image Google Cloud, cần kiểm tra:

- Source disk và boot disk image.
- Guest OS support, architecture và boot mode.
- Machine image có chứa cấu hình/disk nào và giới hạn restore ra sao.
- Image family, image project và quyền sử dụng.
- Encryption key, Cloud KMS và quyền của service agent.
- Guest environment/agent, startup script và metadata.
- Region/zone, machine type và network interface compatibility.

Custom image và machine image có mục đích khác nhau. Khi di chuyển sang cloud khác, cần tái tạo network, service account, firewall rule và các resource liên quan thay vì giả định machine image mang theo toàn bộ môi trường.

### 3.4. Bảng đối chiếu khái niệm

| Khả năng | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Image khởi tạo VM | EC2 AMI | Managed Image / Compute Gallery image version | Compute Engine custom image |
| Chụp disk | EBS snapshot | Managed disk snapshot | Persistent Disk snapshot |
| Chụp máy/cấu hình rộng hơn | AMI với block device mapping; một số cơ chế backup riêng | Image/backup solution theo phạm vi | Machine image |
| Phân phối image | AMI sharing, copy giữa region/account | Azure Compute Gallery replication/sharing | Image project, image family và quyền IAM |
| Cấu hình tạo nhiều VM | Launch Template / Auto Scaling | VM Scale Set model | Instance Template / Managed Instance Group |
| Khởi tạo trong guest | User data, cloud-init, EC2Launch | Custom Data, cloud-init, VM extensions | Metadata startup scripts, guest environment |
| Danh tính VM | EC2 instance profile / IAM role | System-assigned hoặc user-assigned managed identity | Attached service account |

Bảng trên đối chiếu khái niệm tương đương ở mức kiến trúc, không có nghĩa định dạng hoặc tính năng giống nhau. Tên dịch vụ và giới hạn có thể thay đổi theo loại VM, region và phiên bản.

### 3.5. Định dạng image trung gian

Khi chuyển image giữa hypervisor hoặc cloud, có thể gặp các định dạng như RAW, VHD/VHDX, VMDK, QCOW2 hoặc OVA. Mỗi nền tảng chỉ hỗ trợ một tập định dạng, biến thể và điều kiện import nhất định.

Trước khi chuyển đổi, xác định:

- Image là disk đơn, nhiều disk hay appliance package.
- Virtual size và actual size.
- Fixed-size hay dynamic disk.
- Partition table (MBR/GPT), filesystem và bootloader.
- BIOS hay UEFI, Secure Boot và firmware requirements.
- Driver storage/network và guest tools.
- Sparse allocation, alignment và checksum.

Chuyển đổi định dạng không tự giải quyết khác biệt driver, boot firmware, license hoặc cloud agent. Sau import phải boot thử trên VM đích và xác minh thiết bị, network, storage và identity.

## 4. Những yếu tố ảnh hưởng đến image portability

### 4.1. CPU architecture

Image `x86_64` không thể mặc định chạy trên VM `Arm64` và ngược lại. Ứng dụng có binary native, kernel module hoặc package phụ thuộc kiến trúc càng nhạy với khác biệt này.

Khi chuyển cloud:

- Kiểm tra architecture của image và machine type đích.
- Xác minh package repository có build cho kiến trúc đó.
- Rebuild binary native nếu cần.
- Kiểm tra instruction set, SIMD và thư viện phụ thuộc.
- Benchmark lại vì cùng số vCPU không bảo đảm hiệu năng tương đương.

### 4.2. Boot mode và firmware

VM có thể dùng BIOS/Legacy hoặc UEFI. Image tạo theo một boot mode có thể không boot trên instance chỉ hỗ trợ mode khác. Gen1/Gen2 trên Azure, boot mode của EC2 và firmware configuration trên Compute Engine cần được đối chiếu theo loại máy cụ thể.

Kiểm tra partition table, EFI System Partition, bootloader, Secure Boot và driver trước khi import. Không thay đổi firmware mode tùy tiện trên image production vì có thể làm hệ điều hành không boot.

### 4.3. Storage driver và device mapping

Tên thiết bị block và driver khác nhau giữa nền tảng. Ứng dụng không nên giả định volume luôn xuất hiện tại cùng một tên `/dev/...`. Dùng UUID, filesystem label hoặc cơ chế mount theo metadata đã xác minh.

Với Windows, kiểm tra driver storage, boot-critical driver, drive letter, volume GUID và policy domain. Với Linux, kiểm tra initramfs, udev, `/etc/fstab` và driver NVMe/SCSI phù hợp.

### 4.4. Network driver và interface naming

NIC ảo có thể dùng driver và model khác nhau. Interface name có thể thay đổi; cấu hình network tĩnh gắn với MAC cũ có thể khiến máy không có IP sau migration.

Ưu tiên DHCP hoặc cấu hình network được quản lý bằng cloud-init/NetworkManager/systemd-networkd theo nền tảng. Sau boot, xác minh route, DNS, MTU, security policy và throughput.

### 4.5. Cloud agent và guest tools

Mỗi provider có agent hoặc guest environment riêng để hỗ trợ metadata, shutdown, disk, network, telemetry hoặc extension. Một image có thể chứa agent của cloud nguồn nhưng thiếu agent của cloud đích.

Trước migration:

- Xác định agent bắt buộc và agent tùy chọn.
- Cài guest agent của nền tảng đích theo hướng dẫn chính thức.
- Tránh hai agent cùng quản lý một cấu hình gây xung đột.
- Xác minh service khởi động, log và quyền cần thiết.
- Gỡ agent cũ chỉ sau khi xác nhận không còn phụ thuộc.

### 4.6. License và activation

Một số image có license theo instance, host, subscription hoặc Marketplace. Sao chép disk không đồng nghĩa license được chuyển hợp lệ. Windows activation, commercial software license và subscription repository có thể cần đăng ký lại.

Kiểm tra điều khoản license và cơ chế bring-your-own-license của provider trước migration. Không đóng license key hoặc activation secret vào image dùng chung.

### 4.7. Encryption và key management

Snapshot hoặc image có thể được mã hóa bằng key của provider nguồn. Cloud đích thường có hệ thống KMS và policy riêng. Phải xác định khả năng export dữ liệu đã mã hóa, re-encrypt và cấp quyền cho service identity ở đích.

Không giả định có thể mang nguyên key material giữa cloud. Thông thường cần giải mã theo quy trình được phép ở nguồn rồi mã hóa lại bằng key đích, hoặc dùng cơ chế import key được cả hai nền tảng hỗ trợ và tổ chức phê duyệt.

## 5. Metadata service: thông tin runtime của VM

### 5.1. Metadata khác user data

Metadata service cung cấp thông tin về instance, project/account, zone, network, identity hoặc cấu hình được nền tảng công bố. User data/custom data là dữ liệu do người vận hành truyền khi tạo VM, thường dùng cho cấu hình khởi tạo.

Startup script có thể đọc metadata hoặc user data, nhưng hai nguồn này không giống nhau. Metadata thường mô tả môi trường cloud; user data thường chứa tham số hoặc script do người tạo VM cung cấp.

Không nên lưu password, private key hoặc credential dài hạn trong user data. Metadata có thể được đọc bởi process trong VM tùy cấu hình và quyền truy cập; xem nó như dữ liệu không phù hợp để chứa secret.

### 5.2. AWS EC2 Instance Metadata Service

EC2 Instance Metadata Service (IMDS) cung cấp metadata qua địa chỉ link-local `169.254.169.254`. IMDSv2 dùng session token: client gửi yêu cầu PUT để lấy token, rồi đưa token vào header khi truy vấn metadata. Có thể cấu hình yêu cầu IMDSv2 và giới hạn hop limit để giảm nguy cơ truy cập từ workload không mong muốn.

Ví dụ truy vấn instance ID bằng IMDSv2:

```bash
TOKEN=$(curl -sS -X PUT \
  "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

curl -sS \
  -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  "http://169.254.169.254/latest/meta-data/instance-id"
```

Đây là ví dụ cho Linux shell. Trong ứng dụng, dùng SDK/provider library khi phù hợp, xử lý lỗi và không ghi token vào log. IMDSv2 làm giảm một số kiểu SSRF nhưng không thay thế bảo vệ ứng dụng và network.

### 5.3. Azure Instance Metadata Service

Azure Instance Metadata Service (IMDS) cung cấp thông tin VM qua endpoint link-local `169.254.169.254`. Request cần header `Metadata: true`; API yêu cầu chỉ định phiên bản. Endpoint cũng được dùng để lấy token cho managed identity theo resource/audience được yêu cầu.

Ví dụ đọc thông tin instance:

```bash
curl -H "Metadata: true" \
  "http://169.254.169.254/metadata/instance?api-version=2021-02-01"
```

API version trong ví dụ cần được xác minh với tài liệu hiện hành và tính năng sử dụng. Không bỏ header bắt buộc. Khi lấy managed identity token, giới hạn resource/audience đúng với dịch vụ đích và không ghi access token vào log.

### 5.4. Google Compute Engine metadata server

Google Compute Engine cung cấp metadata server, thường truy cập qua hostname `metadata.google.internal` hoặc địa chỉ metadata link-local. Request cần header `Metadata-Flavor: Google`.

Ví dụ đọc instance ID:

```bash
curl -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/id"
```

Metadata server cũng có thể cấp access token cho service account gắn với VM. Ứng dụng cần dùng đúng scope/audience theo cơ chế xác thực và API đích, đồng thời không lưu token lâu hơn cần thiết.

### 5.5. Bảng đối chiếu metadata

| Nội dung | AWS EC2 | Azure VM | Google Compute Engine |
|---|---|---|---|
| Metadata endpoint | `169.254.169.254` | `169.254.169.254` | `metadata.google.internal` / link-local endpoint |
| Header/yêu cầu chính | IMDSv2 token header khi yêu cầu IMDSv2 | `Metadata: true` | `Metadata-Flavor: Google` |
| Thông tin instance | Instance ID, type, AZ, network và metadata khác | VM ID, location, size, NIC và metadata khác | Instance ID, zone, machine type, network và metadata khác |
| User-supplied data | EC2 user data | Custom data | Instance/project metadata startup scripts hoặc custom metadata |
| Credential workload | Temporary credentials từ instance profile role | Token từ managed identity | Token từ attached service account |
| Lưu ý bảo vệ | Ưu tiên IMDSv2, giới hạn hop và kiểm soát SSRF | Bắt buộc header, giới hạn quyền truy cập và bảo vệ SSRF | Bắt buộc flavor header, kiểm soát SSRF và service account scope/IAM |

Các endpoint và API là giao diện riêng của từng nền tảng. Không viết một script dùng chung bằng cách hardcode một URL metadata duy nhất.

### 5.6. Bảo vệ metadata khỏi SSRF

Server-Side Request Forgery (SSRF) có thể khiến ứng dụng bị lừa gửi request đến metadata endpoint. Nếu metadata cho phép lấy credential, kẻ tấn công có thể tìm cách lấy token của VM.

Biện pháp bảo vệ:

- Ưu tiên cơ chế metadata an toàn của provider như IMDSv2 và header bắt buộc.
- Kiểm tra và giới hạn URL mà ứng dụng server-side được phép truy cập.
- Không cho user kiểm soát URL đích của request nội bộ mà không validate.
- Dùng network policy/host firewall phù hợp để giảm đường truy cập metadata từ workload không cần thiết.
- Giới hạn role/managed identity/service account theo least privilege.
- Không trả nội dung metadata hoặc token trong error message.
- Cập nhật framework và thư viện có bảo vệ SSRF.

Metadata service không nên được coi là secret store. Credential lấy từ metadata thường có vòng đời ngắn, nhưng nếu bị lộ vẫn có thể bị sử dụng trong thời hạn hiệu lực.

## 6. Đối chiếu danh tính workload

### 6.1. Vì sao VM cần workload identity?

VM thường cần đọc secret, ghi log, tải object, giải mã volume hoặc gọi API cloud. Cách cũ là đặt access key/password dài hạn trong file cấu hình. Cách này khó rotation và dễ bị lộ qua image, backup, log hoặc process.

Workload identity cho phép máy hoặc ứng dụng nhận credential ngắn hạn dựa trên danh tính được gắn vào tài nguyên. Ứng dụng lấy token/credential khi cần và provider kiểm tra quyền theo IAM policy.

### 6.2. AWS: IAM role và instance profile

Với EC2, IAM role được gắn vào instance thông qua instance profile. Instance metadata cung cấp temporary security credentials cho role; SDK có thể tự lấy và làm mới credential.

Thiết kế:

- Tạo role riêng cho workload hoặc service class.
- Gắn role qua instance profile.
- Chỉ cấp action và resource cần thiết.
- Dùng condition và resource policy khi phù hợp.
- Theo dõi CloudTrail và credential usage.
- Tránh đặt access key dài hạn trong AMI hoặc user data.

Nếu một instance cần nhiều danh tính cho các ứng dụng khác nhau, cân nhắc cơ chế credential broker hoặc tách workload thành tài nguyên riêng thay vì cấp một role rộng cho tất cả process.

### 6.3. Azure: Managed Identity

Azure Managed Identity có hai dạng phổ biến:

- **System-assigned:** vòng đời gắn với resource; khi xóa resource, identity tương ứng cũng được quản lý theo vòng đời đó.
- **User-assigned:** identity là resource riêng, có thể gắn vào nhiều resource được phép và có vòng đời độc lập.

Ứng dụng có thể dùng Azure Identity SDK hoặc endpoint phù hợp để lấy token. Gán role ở phạm vi resource cần truy cập, tránh cấp quyền rộng ở subscription nếu chỉ cần một storage account hoặc secret vault.

Khi migration, managed identity ID/principal của Azure không thể mang nguyên sang AWS hoặc Google Cloud. Cần tạo identity tương ứng ở đích và ánh xạ quyền theo chức năng.

### 6.4. Google Cloud: attached service account

VM Compute Engine có thể được gắn service account. Metadata server cung cấp access token cho service account; IAM policy quyết định tài nguyên và API được phép truy cập.

Nên dùng service account riêng cho workload, giới hạn IAM role và tránh dùng default service account với quyền rộng. Kiểm tra OAuth scopes và IAM roles; scopes không thay thế IAM policy và có thể giới hạn token theo cách cần hiểu rõ.

Khi migration, service account email và IAM binding thuộc Google Cloud. Cần tạo workload identity tương đương ở provider đích.

### 6.5. Bảng đối chiếu workload identity

| Mục tiêu | AWS | Azure | Google Cloud |
|---|---|---|---|
| Danh tính VM | IAM role gắn qua instance profile | Managed Identity | Attached service account |
| Cấp credential | Temporary credentials qua IMDS/SDK | Token qua managed identity endpoint/SDK | OAuth access token qua metadata server/SDK |
| Phân quyền | IAM identity/resource policy | Azure RBAC và resource access policy | IAM roles và resource policy |
| Danh tính workload trên Kubernetes | IRSA hoặc EKS Pod Identity tùy cấu hình | Microsoft Entra Workload ID | Workload Identity Federation for GKE |
| Thay thế khi migration | Tạo role và policy mới | Tạo managed identity và role assignment mới | Tạo service account và IAM binding mới |

Tên cơ chế và khả năng hỗ trợ phụ thuộc dịch vụ, phiên bản cluster và cấu hình. Đối chiếu quyền theo hành động thực tế, không chỉ dịch tên role giữa các provider.

### 6.6. Least privilege và permission mapping

Một role trên cloud nguồn có thể gồm nhiều policy statement. Khi chuyển sang cloud đích, không tìm một role tên tương tự rồi gán ngay. Hãy lập bảng permission theo hành động:

| Hành động workload | Tài nguyên | Điều kiện/phạm vi | Quyền đích cần ánh xạ |
|---|---|---|---|
| Đọc cấu hình | Secret/config store | Chỉ secret của service | Read secret cụ thể |
| Đọc input | Object storage | Prefix hoặc bucket của job | Read object/prefix |
| Ghi output | Object storage | Output path của workload | Write object/prefix |
| Ghi telemetry | Logging/monitoring | Project/resource của service | Publish log/metric |
| Giải mã disk/data | KMS | Key cụ thể | Decrypt theo điều kiện |

Kiểm thử cả quyền được phép và quyền phải bị từ chối. Permission mapping không hoàn tất chỉ vì happy path hoạt động; cần xác minh workload không có quyền ngoài dự kiến.

## 7. Startup script và cơ chế khởi tạo

### 7.1. Startup script làm gì?

Startup script là mã chạy trong guest OS khi VM khởi động hoặc ở một giai đoạn lifecycle được nền tảng hỗ trợ. Nó có thể:

- Cài đặt hoặc cấu hình agent.
- Lấy cấu hình từ service discovery/secret manager.
- Mount volume hoặc chuẩn bị filesystem.
- Tạo user/group và thư mục ứng dụng.
- Cấu hình service và khởi động process.
- Đăng ký node với hệ thống quản lý.
- Gửi tín hiệu readiness hoặc báo trạng thái bootstrap.

Startup script nên ngắn, có thể chạy lặp an toàn và ghi log. Các bước dài hoặc phức tạp nên chuyển thành configuration management, image baking hoặc orchestration riêng.

### 7.2. AWS: EC2 user data và cloud-init/EC2Launch

EC2 user data cho phép truyền script hoặc cloud-config khi khởi chạy instance. Linux AMI thường tích hợp cloud-init; Windows sử dụng EC2Launch hoặc cơ chế tương ứng theo generation/AMI. Cách thực thi phụ thuộc OS, agent và cấu hình user data.

Một số cấu hình mặc định chỉ chạy user data ở lần boot đầu, trong khi cloud-init có nhiều module/giai đoạn và có thể được cấu hình chạy ở các lần boot sau. Không giả định mọi script luôn chạy một lần hoặc mỗi lần reboot; kiểm tra cloud-init config và log trên image.

Ví dụ cloud-config tổng quát:

```yaml
#cloud-config
package_update: true
packages:
  - curl
  - jq
runcmd:
  - [ sh, -c, "systemctl enable app-agent" ]
  - [ sh, -c, "systemctl start app-agent" ]
```

Đây là ví dụ cloud-init, không phải cú pháp riêng của EC2. Image phải có cloud-init và package manager phù hợp. Trong production, pin package version khi cần, kiểm tra lỗi từng bước và không đặt credential trong user data.

### 7.3. Azure: Custom Data, cloud-init và VM extensions

Azure hỗ trợ Custom Data khi tạo VM và cloud-init cho nhiều Linux image. VM extensions như Custom Script Extension có thể chạy script cài đặt hoặc cấu hình sau khi VM được cấp phát. Windows có các extension và cơ chế provisioning tương ứng.

Phân biệt:

- Custom Data là dữ liệu truyền lúc tạo VM; không phải mọi image đều tự thực thi nội dung này nếu thiếu cloud-init/agent phù hợp.
- cloud-init xử lý cấu hình Linux theo các stage.
- VM extension có lifecycle, trạng thái provisioning và cách retry riêng.

Không đặt secret trong Custom Data vì dữ liệu có thể được lưu trong cấu hình resource hoặc xuất hiện trong log. Dùng Managed Identity để lấy secret khi runtime cần.

### 7.4. Google Cloud: startup scripts và guest environment

Compute Engine hỗ trợ startup script qua instance/project metadata; guest environment/agent trên VM đọc metadata và thực thi script theo quy tắc của nền tảng. Có thể dùng startup script dạng inline hoặc tham chiếu file/script từ vị trí được phép truy cập.

Kiểm tra guest environment đã cài và đang chạy. Nếu image custom loại bỏ agent cần thiết, metadata startup script có thể không được thực thi. Startup script có thể chạy ở các lần boot theo cơ chế của guest agent; cần làm script idempotent và tránh tạo side effect trùng khi VM reboot.

### 7.5. Bảng đối chiếu startup automation

| Khía cạnh | AWS | Azure | Google Cloud |
|---|---|---|---|
| Dữ liệu khởi tạo | EC2 user data | Custom Data | Instance/project metadata |
| Linux bootstrap phổ biến | cloud-init | cloud-init | Startup script qua guest environment; cloud-init cũng có thể dùng tùy image |
| Windows bootstrap | EC2Launch/agent và user data theo image | VM extensions và cơ chế provisioning Windows | Windows guest environment/startup scripts theo image |
| Cơ chế mở rộng | SSM/agent, configuration management | VM extensions, Run Command và automation | Guest agent, OS Config và configuration tooling |
| Quan sát lỗi | cloud-init/EC2Launch log, instance status | Extension status, provisioning state, guest log | Serial port output, guest agent/startup script log |

Các lựa chọn không loại trừ lẫn nhau. Có thể dùng image baking cho phần cài đặt ổn định và startup script cho cấu hình phụ thuộc môi trường.

## 8. Thiết kế startup script portable và an toàn

### 8.1. Tách phần chung và phần provider-specific

Phần chung có thể gồm cài đặt ứng dụng, tạo thư mục, cấu hình service và kiểm tra health. Phần provider-specific gồm đọc metadata, lấy token, đăng ký identity, cấu hình network hoặc gọi API của cloud.

Tách hai phần giúp giữ logic ứng dụng nhất quán và giới hạn mã phụ thuộc provider. Dùng adapter/script riêng cho mỗi cloud thay vì viết một đoạn shell dài với nhiều nhánh khó kiểm thử.

### 8.2. Idempotency

Startup script có thể được thực thi lại do reboot, extension retry hoặc thao tác vận hành. Một script idempotent có thể chạy nhiều lần mà không tạo trạng thái sai.

Ví dụ:

```bash
#!/usr/bin/env bash
set -euo pipefail

install -d -m 0755 /opt/example-app

if ! id -u appuser >/dev/null 2>&1; then
  useradd --system --home-dir /opt/example-app --shell /usr/sbin/nologin appuser
fi

install -d -o appuser -g appuser -m 0750 /var/lib/example-app
systemctl enable example-app.service
```

Ví dụ cần điều chỉnh theo Linux distribution và service thực tế. Tránh dùng lệnh có tác dụng phụ lặp lại như tạo resource cloud mới mỗi lần boot mà không kiểm tra trạng thái hiện có.

### 8.3. Không nhúng secret

Không đặt API key, password, private key hoặc access token trong:

- AMI/managed image/custom image.
- User data hoặc Custom Data.
- Instance/project metadata.
- Startup script, environment variable được lưu lâu dài hoặc log.
- Source repository hoặc build artifact.

Thay vào đó, gắn workload identity tối thiểu và lấy secret từ secret manager khi cần. Nếu script cần credential để bootstrap, dùng cơ chế ngắn hạn, scope hẹp và rotation.

### 8.4. Chống lộ metadata và SSRF

Ứng dụng web có thể bị khai thác SSRF để truy cập metadata service. Bảo vệ bằng IMDSv2, header bắt buộc, network control và input validation theo provider. Startup script chỉ nên đọc trường metadata cần thiết và không dump toàn bộ metadata vào log.

### 8.5. Retry và timeout cho bootstrap

Package repository, secret manager hoặc API cấu hình có thể tạm thời không sẵn sàng khi VM vừa boot. Startup script nên dùng timeout và retry có backoff, có cap và giới hạn tổng thời gian. Nếu bootstrap thất bại, ghi trạng thái lỗi rõ ràng và để orchestration quyết định retry/replace.

Không dùng vòng lặp vô hạn khiến VM ở trạng thái provisioning mãi. Có thể chia bootstrap thành các bước có trạng thái để tiếp tục từ điểm an toàn.

### 8.6. Logging và exit status

Ghi log vào journald, cloud-init output hoặc logging agent theo nền tảng. Không ghi secret/token. Script cần trả exit code phù hợp; che giấu lỗi bằng `|| true` cho mọi lệnh làm cho control plane báo thành công dù máy chưa sẵn sàng.

### 8.7. Readiness sau bootstrap

VM chỉ nên được đưa vào load balancer hoặc instance group phục vụ khi:

- OS boot hoàn tất.
- Disk và filesystem bắt buộc đã mount.
- Workload identity lấy được token.
- Cấu hình và secret cần thiết đã được tải.
- Application process hoạt động.
- Health endpoint hoặc smoke test đạt.

Startup script kết thúc không đồng nghĩa ứng dụng đã sẵn sàng. Dùng health check và readiness ở lớp điều phối để xác nhận khả năng phục vụ.

## 9. Đóng gói image chuẩn và cấu hình runtime

### 9.1. Golden image

Golden image là image chuẩn đã được kiểm thử, thường chứa OS, security patch, agent, runtime và cấu hình nền. Nó giúp giảm thời gian boot và đảm bảo VM nhất quán.

Golden image cần có:

- Owner và version rõ ràng.
- Base OS được hỗ trợ và lịch patch.
- Package inventory/SBOM nếu quy trình yêu cầu.
- Agent cần thiết cho monitoring, security và cloud integration.
- Không có secret, token hoặc machine identity dùng chung.
- Quy trình build tái lập, scan và phê duyệt.
- Kiểm thử trên instance type và region mục tiêu.

### 9.2. Image baking và boot-time configuration

**Image baking** cài đặt phần mềm và cấu hình ổn định trước khi publish image. **Boot-time configuration** áp dụng giá trị phụ thuộc môi trường khi VM khởi động, ví dụ region, endpoint, role hoặc cấu hình service.

Đưa quá nhiều việc vào startup script làm boot chậm và dễ lỗi do repository/network. Đưa quá nhiều cấu hình động vào image làm image khó tái sử dụng và có nguy cơ chứa thông tin môi trường cũ. Cần phân chia theo tính ổn định của dữ liệu.

### 9.3. Không clone machine identity bừa bãi

Image hoặc disk clone có thể mang theo machine ID, SSH host key, certificate, monitoring agent ID hoặc domain state. Nếu nhiều VM dùng cùng identity, hệ thống quản lý và audit có thể nhầm máy.

Golden image nên được tổng quát hóa theo hướng dẫn của OS/provider; tạo host key hoặc machine identity duy nhất khi provision. Với domain-joined Windows hoặc Linux đăng ký vào hệ thống quản lý, dùng quy trình specialize/generalize phù hợp.

### 9.4. Versioning và rollback

Không ghi đè image version đã phát hành. Tạo version mới, lưu digest/checksum, source build và test result. Giữ một số version rollback trong thời gian hỗ trợ.

Khi phát hành image mới, rollout theo canary hoặc một phần fleet, kiểm tra boot success, startup duration, health check, agent và metric trước khi thay toàn bộ instance.

## 10. Đối chiếu startup parameters và metadata theo kiến trúc

### 10.1. Không phụ thuộc tên field provider

Một script portable không nên giả định tất cả cloud dùng cùng tên trường như `instance_id`, `zone` hay `region`. Hãy chuẩn hóa thành cấu trúc nội bộ:

```json
{
  "provider": "example-cloud",
  "instance_id": "vm-123",
  "region": "region-a",
  "zone": "zone-a",
  "machine_type": "compute-medium",
  "network": {
    "private_ip": "10.0.1.10"
  }
}
```

Đây là schema nội bộ minh họa, không phải response metadata của provider. Adapter riêng đọc metadata native rồi chuyển thành schema chung; field không có trên một cloud nên để null/không có thay vì bịa giá trị.

### 10.2. Adapter theo provider

Một thiết kế có thể có:

- `metadata/aws`: đọc IMDSv2 và kiểm tra token.
- `metadata/azure`: gọi IMDS với header bắt buộc và API version.
- `metadata/gcp`: gọi metadata server với flavor header.
- `identity/aws`: dùng SDK credential chain/instance profile.
- `identity/azure`: dùng Managed Identity SDK.
- `identity/gcp`: dùng Application Default Credentials/attached service account.

Ứng dụng gọi interface nội bộ như `get_instance_context()` hoặc `get_secret()` thay vì tự xây URL metadata trong từng module nghiệp vụ.

### 10.3. Provider detection

Không xác định cloud chỉ dựa trên một biến môi trường do user có thể sửa. Có thể dùng metadata endpoint, agent hoặc deployment config đã được kiểm soát. Nếu không xác định được provider, fail rõ ràng hoặc dùng cấu hình tĩnh đã được phê duyệt; không thử gọi metadata endpoint của mọi cloud liên tục.

### 10.4. Local development và test

Ở máy phát triển, metadata service có thể không tồn tại. Thiết kế adapter để hỗ trợ mock hoặc credential chain dành cho developer. Không giả lập metadata production bằng cách ghi credential thật vào file cấu hình.

Kiểm thử các trường hợp:

- Metadata endpoint timeout hoặc trả 401/403.
- Token hết hạn hoặc clock skew.
- Field tùy chọn không tồn tại.
- Network route đến metadata bị chặn.
- Workload identity không có quyền.
- Provider không được nhận diện.

## 11. Quy trình migration image giữa các cloud

### 11.1. Bước 1 – Inventory nguồn

Ghi nhận:

- Image ID, version, source OS và architecture.
- Boot mode, partition table, filesystem và disk size.
- Package/agent/driver và license.
- Machine identity, host key và domain state.
- Startup script/user data và metadata dependency.
- IAM role/managed identity/service account và quyền thực tế.
- NIC, IP, route, firewall, DNS và endpoint dependency.
- Encryption key, backup và RTO/RPO.

Không đọc hoặc export secret vào inventory. Chỉ ghi tên secret, nơi lưu và identity được phép truy cập.

### 11.2. Bước 2 – Xác định portability boundary

Phân loại thành ba nhóm:

- **Portable:** ứng dụng, package, script shell chuẩn, file cấu hình không phụ thuộc provider.
- **Adaptable:** cloud-init, service config, agent, disk mapping, network config và metadata adapter.
- **Provider-specific:** AMI ID, Azure resource ID, GCP image/project ID, role/managed identity/service account, KMS key, NIC/subnet và API metadata.

Ưu tiên giữ phần portable, viết adapter cho phần adaptable và tái tạo phần provider-specific ở đích.

### 11.3. Bước 3 – Chuẩn bị image đích

Chọn image format và import path được cloud đích hỗ trợ. Chuyển đổi disk khi cần, kiểm tra checksum và kích thước. Cập nhật bootloader/driver/agent, bỏ cấu hình network tĩnh của nguồn và tạo image version mới.

Nếu image chứa dữ liệu nhạy cảm hoặc credential, xử lý theo quy trình security. Rotate credential và tạo machine identity mới khi cần.

### 11.4. Bước 4 – Tạo network và workload identity

Tạo VPC/VNet, subnet, route, firewall/security group, DNS và private endpoint ở cloud đích. Tạo workload identity và ánh xạ quyền theo hành động, resource và scope.

Kiểm tra quyền được phép và quyền bị từ chối. Không cấp role quản trị rộng để làm cho bootstrap chạy qua.

### 11.5. Bước 5 – Viết lại metadata adapter và startup script

Thay endpoint metadata, header, API version và identity SDK theo provider đích. Giữ startup script idempotent, không chứa secret và có timeout/retry. Tách config chung khỏi config provider-specific.

### 11.6. Bước 6 – Boot test trong môi trường cô lập

Tạo VM thử nghiệm không nhận production traffic. Kiểm tra:

- OS boot, firmware, driver và disk mapping.
- Metadata endpoint và user data.
- Workload identity token và quyền truy cập.
- Startup script status, log và idempotency khi reboot.
- NIC, IP, route, DNS và kết nối dependency.
- Monitoring/security agent và health check.

### 11.7. Bước 7 – Performance và security validation

Benchmark CPU, memory, storage và network trên machine type đích. Kiểm tra image scanning, patch level, firewall, IAM scope, metadata protection và log. Cùng số vCPU không đảm bảo throughput bằng nhau giữa các provider hoặc instance family.

### 11.8. Bước 8 – Cutover và rollback

Chạy canary hoặc blue/green. Đồng bộ dữ liệu, chuyển traffic từng bước, theo dõi error rate và latency. Giữ phương án rollback có dữ liệu nhất quán; nếu workload có ghi, xác định rõ điểm freeze, replication lag và quyền ghi tại mỗi thời điểm.

## 12. Ví dụ thực hành: chuẩn hóa startup contract

### 12.1. Cấu trúc cấu hình chung

Một ứng dụng có thể đọc cấu hình đã được chuẩn hóa từ adapter:

```yaml
runtime:
  provider: aws
  region: ap-southeast-1
  zone: ap-southeast-1a
  instance_id: i-example
identity:
  mechanism: instance-role
  secret_source: managed-secret-store
application:
  environment: production
  config_ref: orders-api/prod
```

Đây là ví dụ cấu trúc nội bộ. Không lưu access token hoặc secret value trong file này. Thông tin runtime nên được tạo từ metadata/identity adapter và cấu hình được quản lý, không hardcode vào golden image.

### 12.2. Pseudocode bootstrap

```text
function bootstrap():
    context = provider_adapter.get_instance_context()
    identity = provider_adapter.get_workload_identity()

    assert context.instance_id is present
    assert identity.can_read("orders-api/prod")

    config = secret_store.read_config("orders-api/prod", identity)
    validate(config)
    ensure_required_volumes_mounted()
    ensure_application_version_installed()
    write_runtime_config_atomically(config)
    start_application_service()
    wait_until_health_check_passes(deadline=bootstrap_deadline)
    report_bootstrap_success(context.instance_id)
```

Pseudocode mô tả trình tự, không phải ngôn ngữ thực thi. `ensure_*` cần idempotent; `write_runtime_config_atomically` tránh để service đọc file đang ghi dở; identity chỉ được cấp quyền cần thiết.

### 12.3. Tiêu chí thành công

Bootstrap chỉ được xem là thành công khi:

- Metadata adapter trả context hợp lệ.
- Workload identity lấy được token và truy cập đúng secret/config.
- Volume bắt buộc được mount đúng.
- Ứng dụng chạy đúng version.
- Health check đạt trong deadline.
- Log không chứa credential.
- Reboot test không tạo resource hoặc side effect trùng.

## 13. Troubleshooting

### 13.1. VM boot thành công nhưng không có network

Kiểm tra NIC đã attach, driver, interface name, DHCP/static config, route table, security policy và DNS. Nếu image được clone từ cloud khác, kiểm tra cấu hình network gắn với MAC/interface cũ và cloud agent đang quản lý network.

### 13.2. Startup script không chạy

Kiểm tra user data/custom data/metadata đã được gán đúng lúc tạo VM chưa; image có cloud-init hoặc guest agent không; script có đúng format và quyền execute không; log bootstrap có lỗi syntax, package repository hoặc network không.

Không chạy script thủ công rồi kết luận provisioning tự động đã hoạt động. Cần kiểm thử lại bằng một VM mới từ image đã phát hành.

### 13.3. Workload không lấy được credential

Kiểm tra identity đã gắn vào VM chưa, token endpoint có truy cập được không, role assignment/IAM binding có đúng resource scope không, audience/scope có phù hợp không và clock có đồng bộ không.

Nếu `AccessDenied`/`Forbidden`, đọc audit log và xác định action/resource cụ thể. Không cấp quyền owner/admin toàn project để thử.

### 13.4. Ứng dụng không đọc được metadata

Kiểm tra endpoint, header và token flow của provider. AWS yêu cầu token nếu instance ép IMDSv2; Azure cần `Metadata: true`; Google Cloud cần `Metadata-Flavor: Google`. Xác minh firewall, proxy environment và SSRF mitigation không vô tình chặn request hợp lệ của agent.

### 13.5. Image không boot trên cloud đích

Kiểm tra architecture, BIOS/UEFI, partition, bootloader, storage driver, initramfs, Secure Boot và image format. Xem serial/console log. Tạo bản copy để sửa, giữ nguyên artifact nguồn và ghi lại checksum.

### 13.6. VM boot nhưng identity hoặc monitoring agent bị trùng

Image clone có thể giữ host key, machine ID hoặc agent ID. Dùng quy trình generalize/specialize, tạo identity duy nhất và đăng ký lại agent. Không xóa file identity ngẫu nhiên nếu chưa hiểu ảnh hưởng đến domain, cloud agent hoặc hệ thống quản lý.

## 14. Những sai lầm thường gặp

- **Coi image ID là portable:** AMI ID, Azure image version và GCP image ID thuộc namespace/provider riêng.
- **Coi machine image là backup toàn môi trường:** NIC, IAM, DNS, firewall và secret có thể nằm ngoài image.
- **Bỏ qua boot mode/architecture:** image import được nhưng VM không boot.
- **Giữ network config cũ:** interface name, MAC hoặc IP tĩnh không còn phù hợp.
- **Copy machine identity:** host key, machine ID và agent ID bị trùng.
- **Đóng credential vào image hoặc user data:** secret có thể bị đọc từ metadata, log hoặc artifact.
- **Dùng metadata endpoint sai:** header/token/API version không đúng provider.
- **Tắt bảo vệ metadata để sửa lỗi:** tăng nguy cơ SSRF và credential theft.
- **Cấp role quá rộng:** bootstrap chạy được nhưng workload có quyền vượt nhu cầu.
- **Giả định startup script chỉ chạy một lần:** reboot hoặc extension retry tạo side effect trùng.
- **Cài mọi thứ ở boot:** tăng thời gian provisioning và phụ thuộc network/repository.
- **Không kiểm tra guest agent:** metadata hoặc extension không được thực thi.
- **Không kiểm tra license:** migration vi phạm điều khoản hoặc activation thất bại.
- **Không test lại trên VM mới:** script thủ công chạy được nhưng quy trình tự động vẫn lỗi.
- **Chỉ kiểm tra happy path:** không biết hành vi khi metadata, token hoặc secret service gián đoạn.

## 15. Checklist đối chiếu và migration

### Image

- [ ] Đã xác định image, snapshot, machine image và template khác nhau thế nào.
- [ ] Đã ghi architecture, firmware/boot mode, partition và filesystem.
- [ ] Đã kiểm tra storage/network driver, guest agent và license.
- [ ] Đã xác minh image format và import path được cloud đích hỗ trợ.
- [ ] Đã giữ checksum, version, owner và quy trình rollback.
- [ ] Image không chứa secret hoặc machine identity dùng chung.

### Metadata và startup

- [ ] Đã xác định metadata endpoint và header/token flow của từng provider.
- [ ] Ứng dụng không hardcode một metadata URL dùng cho mọi cloud.
- [ ] User data/custom data không chứa secret.
- [ ] Startup script idempotent, có timeout, retry và log.
- [ ] Guest agent/cloud-init/extension cần thiết được cài và kiểm tra.
- [ ] Health check xác nhận ứng dụng sẵn sàng sau bootstrap.

### Identity và bảo mật

- [ ] Đã ánh xạ instance role/managed identity/service account theo permission thực tế.
- [ ] Credential là ngắn hạn và lấy qua workload identity.
- [ ] IAM policy theo least privilege và đã test quyền bị từ chối.
- [ ] Secret lấy từ secret manager, không đóng vào image.
- [ ] Metadata endpoint được bảo vệ trước SSRF.
- [ ] Key/encryption policy và audit log hoạt động ở cloud đích.

### Migration validation

- [ ] VM boot thử trong môi trường cô lập.
- [ ] Disk, NIC, route, DNS và dependency được xác minh.
- [ ] Startup script được kiểm thử cả lần boot đầu và reboot.
- [ ] Workload identity truy cập đúng tài nguyên.
- [ ] Monitoring/security agent hoạt động và identity không trùng.
- [ ] Performance benchmark đáp ứng yêu cầu workload.
- [ ] Có canary/cutover, rollback và người chịu trách nhiệm.

## 16. Kết luận

AWS AMI, Azure Managed Image/Compute Gallery và Google Cloud custom image/machine image đều giúp chuẩn hóa cách tạo VM, nhưng chúng không phải định dạng có thể dùng trực tiếp thay thế cho nhau. Image portability phụ thuộc architecture, boot mode, driver, disk mapping, encryption, license và guest agent. Khi migration, cần import hoặc tạo image native ở đích rồi kiểm thử trên loại VM thực tế.

Metadata service cung cấp runtime context và có thể cấp credential ngắn hạn; mỗi provider có endpoint, header và token flow riêng. Workload identity cũng khác nhau: IAM role/instance profile, Azure Managed Identity và Google service account cần được ánh xạ theo quyền thực tế thay vì sao chép tên role. Startup script nên ngắn, idempotent, có timeout/log, không chứa secret và tách phần portable khỏi adapter provider-specific.

Một quy trình cross-cloud đáng tin cậy bắt đầu bằng inventory image và quyền, xác định portability boundary, chuẩn bị network/identity đích, chuyển đổi image, cập nhật metadata adapter/startup automation, boot test trong môi trường cô lập rồi mới cutover. Kiểm thử cả lỗi metadata, token, agent và reboot giúp workload có thể di chuyển mà vẫn duy trì bảo mật, khả năng vận hành và hiệu năng compute.
