# Thiết kế nhóm máy ảo và ảnh máy chuẩn hóa

Trong kiến trúc ứng dụng trên đám mây (**Cloud Architecture**), máy ảo (Virtual Machine – VM) là lựa chọn linh hoạt cho ứng dụng, dịch vụ nền, cơ sở dữ liệu tự quản lý và workload cần quyền kiểm soát hệ điều hành. Khi số VM tăng, tạo từng máy thủ công khiến cấu hình lệch nhau, khó vá lỗi, khó kiểm toán và tăng rủi ro vận hành. Hai thực hành quan trọng để giải quyết vấn đề này là **nhóm máy ảo (VM groups)** và **ảnh máy chuẩn hóa (standardized/golden images)**.

Nhóm VM giúp mô tả những máy có cùng vai trò, chính sách, cách mở rộng và vòng đời. Ảnh máy chuẩn hóa cung cấp nền tảng hệ điều hành và phần mềm cơ sở có thể tái lập, kiểm tra và phát hành theo phiên bản. Kết hợp hai cơ chế giúp triển khai nhất quán, phục hồi nhanh và quản lý fleet lớn hơn, đồng thời hỗ trợ đánh giá các đánh đổi về **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân loại VM theo workload, môi trường, mức độ quan trọng và yêu cầu vận hành.
- Thiết kế nhóm VM bằng template, instance group, scale set hoặc cơ chế tương đương.
- Hiểu vai trò của golden image, image pipeline, image catalog và quản lý phiên bản.
- Xây dựng quy trình tạo ảnh an toàn, kiểm thử, phê duyệt, phát hành và thu hồi.
- Kết hợp image với cloud-init, startup script, configuration management và secret management.
- Lập chiến lược vá lỗi, rollout, rollback, autoscaling, backup và khôi phục cho các nhóm VM.
- Chuyển yêu cầu kiến trúc thành tiêu chí nghiệm thu có thể đo lường và kiểm toán.

## 1. Nhóm máy ảo là gì?

**Nhóm máy ảo (VM group)** là tập hợp những instance được quản lý theo một mục tiêu chung. Tùy nền tảng cloud, cơ chế có thể được gọi là instance group, virtual machine scale set, autoscaling group, managed instance group hoặc một nhóm tài nguyên được điều phối bằng IaC và configuration management. Tên dịch vụ và tính năng khác nhau giữa nhà cung cấp, nhưng ý tưởng chung là chuẩn hóa cách tạo, cấu hình, cập nhật và vận hành các VM có vai trò tương tự.

Ví dụ, một ứng dụng web có thể có ba nhóm:

- **Web group:** nhận HTTP/HTTPS từ load balancer, chạy web/API process, mở rộng theo request hoặc CPU.
- **Worker group:** xử lý hàng đợi và tác vụ nền, mở rộng theo độ dài queue hoặc độ trễ xử lý.
- **Admin group:** phục vụ quản trị theo quy trình được kiểm soát, số lượng nhỏ, quyền truy cập hẹp và giám sát chặt.

Mỗi VM trong group có thể khác nhau về hostname, địa chỉ IP, zone hoặc metadata định danh, nhưng cần tuân theo một **hợp đồng cấu hình chung**: hệ điều hành, image family/version, instance type được phép, security profile, monitoring agent, logging, patch policy và phương pháp quản lý.

### 1.1. Phân biệt nhóm logic và nhóm được nền tảng quản lý

| Kiểu nhóm | Đặc điểm | Ví dụ sử dụng |
| --- | --- | --- |
| **Nhóm logic theo inventory/tag** | Dùng nhãn hoặc inventory để gom VM; vòng đời không nhất thiết được điều phối cùng nhau | Chọn VM thuộc production và áp chính sách vá theo nhóm |
| **Nhóm triển khai cố định** | Dùng template để tạo số instance định trước; có thể phân bố qua nhiều zone | Một nhóm ứng dụng có 3 replica tối thiểu |
| **Nhóm autoscaling/managed group** | Nền tảng điều chỉnh số VM theo chính sách, health check và template | Web tier tăng từ 3 lên 12 instance khi tải tăng |
| **Nhóm workload đặc thù** | Gắn với ổ đĩa, placement, lịch vận hành hoặc yêu cầu node riêng | Database node, license-bound workload, GPU worker |

Một nhóm logic hữu ích cho quản trị nhưng không tự tạo ra autoscaling, tự thay instance lỗi hay cân bằng tải. Ngược lại, managed instance group có cơ chế vòng đời và health check riêng. Khi thiết kế, phải nêu chính xác cơ chế đang dùng thay vì gọi tất cả là VM group.

### 1.2. Không gom VM chỉ vì chúng giống kích thước

Hai VM cùng 4 vCPU và 16 GiB RAM không nhất thiết thuộc cùng nhóm. Một máy chạy API stateless và một máy chạy database có yêu cầu khác nhau về dữ liệu, quyền mạng, backup, restart, mức sẵn sàng, RTO/RPO, hành vi scale và cách kiểm tra sức khỏe.

**Vai trò và vòng đời workload** là tiêu chí chính. Instance type chỉ là một thuộc tính tài nguyên.

## 2. Phân loại workload trước khi tạo nhóm VM

Nhóm VM tốt bắt đầu từ yêu cầu nghiệp vụ và cách workload hoạt động, không phải từ việc chia danh sách server thành những nhóm có kích thước bằng nhau.

| Chiều | Câu hỏi | Tác động đến nhóm |
| --- | --- | --- |
| **Vai trò ứng dụng** | Web, API, worker, scheduler, database hay công cụ quản trị? | Xác định image, port, process và dependency |
| **Môi trường** | Dev, test, staging, production hay DR? | Tách quyền, dữ liệu, account/project và chính sách |
| **Mức quan trọng** | Workload ảnh hưởng trực tiếp đến giao dịch hay hỗ trợ? | Đặt HA, patch window, giám sát và ưu tiên khôi phục |
| **Đặc tính tải** | CPU-bound, memory-bound, I/O-bound, burst hay chạy liên tục? | Chọn instance family, scaling metric và giới hạn |
| **Trạng thái** | Stateless hay stateful? | Quyết định khả năng thay thế, lưu trữ và backup |
| **Tuân thủ** | Có dữ liệu cá nhân, thanh toán hoặc bí mật ngành? | Xác định network, encryption, access, region và audit |
| **Phần cứng** | x86_64, ARM64, GPU/NPU hoặc thiết bị chuyên biệt? | Chọn image và instance tương thích |
| **Vòng đời** | Có thể thay mới thường xuyên hay phải chạy dài hạn? | Chọn rolling replacement, patch và maintenance |
| **Sở hữu vận hành** | Đội nào chịu trách nhiệm và trực xử lý? | Gắn owner, escalation và lịch bảo trì |

### 2.1. Ma trận nhóm VM ví dụ

Một nền tảng đặt thuê thiết bị có thể tổ chức như sau:

| VM group | Công việc | Đặc tính | Scale policy | Yêu cầu chính |
| --- | --- | --- | --- | --- |
| prod-web | Web/API stateless | Request nhiều, CPU vừa | Request rate, CPU hoặc custom metric | Đa zone, health check, không giữ session cục bộ |
| prod-worker | Xử lý thông điệp | CPU và queue dependent | Queue backlog/processing lag | Idempotent, graceful shutdown |
| prod-batch | Báo cáo định kỳ | CPU/RAM và I/O tăng theo lịch | Theo lịch hoặc queue | Giới hạn ảnh hưởng tới DB giao dịch |
| prod-admin | Công cụ quản trị nội bộ | Ít instance, quyền cao | Thường cố định | Private access, MFA, audit |
| staging-web | Kiểm thử tích hợp | Tải biến động | Scale nhỏ theo nhu cầu | Tách production, dữ liệu an toàn |
| dr-web | Năng lực khôi phục | Warm hoặc pilot light | Theo kế hoạch DR | Image và cấu hình đã kiểm thử |

Đây là ví dụ logic; một hệ thống có thể dùng container cho web/worker và VM cho database hoặc thành phần legacy. Không cần ép mọi workload chạy VM chỉ vì đang thiết kế VM group.

### 2.2. Tách nhóm theo blast radius

Một nhóm không nên bao trùm những máy có sự cố hoặc thay đổi gây tác động quá khác nhau. Cân nhắc tách group khi quyền mạng, quyền dữ liệu, lịch bảo trì, mức độ quan trọng, scaling metric, phần cứng, chu kỳ vá hoặc đội sở hữu khác nhau.

Không nên tách quá nhỏ đến mức mỗi VM là một group riêng mà không mang lại lợi ích. Mục tiêu là cân bằng giữa **ranh giới quản trị rõ** và **chi phí duy trì chính sách**.

## 3. Ảnh máy chuẩn hóa là gì?

**Machine image** là bản mẫu đóng gói trạng thái khởi tạo của VM, thường bao gồm hệ điều hành, boot configuration và một số phần mềm hoặc cấu hình đã cài đặt. Tùy cloud, image có thể được gọi là machine image, AMI, image version hoặc managed image.

**Ảnh máy chuẩn hóa (golden image)** là image được tạo theo quy trình kiểm soát, có nguồn gốc, phiên bản, bằng chứng kiểm thử, trạng thái bảo mật và người phê duyệt rõ ràng. Nó cung cấp baseline thống nhất để tạo VM trong một môi trường hoặc một nhóm workload.

Một golden image tốt giúp:

- Rút ngắn thời gian provisioning và giảm cài đặt thủ công.
- Giảm khác biệt cấu hình giữa các instance.
- Đảm bảo agent nền tảng, logging và bảo mật được cài sẵn.
- Hỗ trợ audit và điều tra vì biết VM được tạo từ image/version nào.
- Tạo lại máy sau sự cố theo cách có thể tái lập.
- Kiểm soát phiên bản hệ điều hành và thư viện cơ sở.

Golden image **không phải ảnh chụp tùy ý của máy production đang chạy**. Nếu image chứa dữ liệu thật, secret, token, khóa riêng hoặc trạng thái máy không sạch, việc nhân bản có thể phát tán thông tin nhạy cảm ra nhiều instance.

### 3.1. Thành phần trong image

| Thành phần | Đưa vào image? | Ghi chú |
| --- | --- | --- |
| Hệ điều hành và kernel được hỗ trợ | Có | Chọn phiên bản còn hỗ trợ bảo mật |
| Security updates và package cơ sở | Có | Ghi nhận thời điểm build và nguồn cập nhật |
| CA certificate và cấu hình tin cậy chuẩn | Có, nếu chính sách cho phép | Không đưa private key môi trường vào image |
| Monitoring/logging agent | Thường có | Endpoint và identity có thể inject lúc boot |
| Runtime dùng chung như Java | Tùy vai trò | Ghi rõ version, nguồn và cách cập nhật |
| Ứng dụng/agent chuyên dụng | Có thể | Đóng gói nếu version và rollout cần kiểm soát cùng image |
| Cấu hình môi trường | Phần bất biến, không nhạy cảm | Tách endpoint hoặc feature setting có thể đổi |
| Secret, API key, mật khẩu, token | Không | Lấy từ secret manager hoặc cơ chế runtime |
| Dữ liệu người dùng, database dump, log | Không | Dùng storage bền vững và dữ liệu phù hợp |
| SSH private key, machine identity dùng chung | Không | Mỗi máy cần danh tính riêng |

Một số tổ chức chọn image tối thiểu rồi cài ứng dụng lúc boot; tổ chức khác đóng gói ứng dụng vào image để tăng tính bất biến và giảm thời gian khởi động. Cả hai đều có thể đúng nếu quy trình build, provenance, kiểm tra và rollout phù hợp.

## 4. Thiết kế image pipeline

Ảnh máy đáng tin cậy được sản xuất như một artifact có vòng đời.

~~~mermaid
flowchart LR
    SRC["OS base image đã duyệt"] --> BUILD["Build image tự động"]
    CODE["Recipe / package manifest"] --> BUILD
    BUILD --> HARDEN["Hardening và baseline"]
    HARDEN --> SCAN["Patch, vulnerability và compliance scan"]
    SCAN --> TEST["Boot, agent và application smoke test"]
    TEST --> REVIEW["Review và phê duyệt"]
    REVIEW --> SIGN["Provenance / ký nếu hỗ trợ"]
    SIGN --> PUBLISH["Publish image version bất biến"]
    PUBLISH --> ROLLOUT["Canary / rolling rollout"]
    ROLLOUT --> OBS["Theo dõi, rollback hoặc retire"]
~~~

Các bước chính:

1. **Chọn nguồn base image:** nguồn chính thức hoặc nguồn nội bộ được phê duyệt; xác định publisher, checksum hoặc signature khi có.
2. **Build có thể tái lập:** dùng Packer, image builder của nhà cung cấp hoặc công cụ tương đương; lưu recipe, manifest và dependency version.
3. **Hardening:** áp baseline hệ điều hành, cấu hình SSH, firewall, audit, quyền, dịch vụ không cần thiết và cơ chế bảo vệ.
4. **Cập nhật bảo mật:** cài bản vá đã kiểm tra; ghi nhận CVE và ngoại lệ.
5. **Cài agent/runtime:** chỉ đưa thành phần cần thiết, xác định version và nguồn.
6. **Kiểm tra:** boot test, package, agent, cấu hình, quyền file, cổng, log và smoke test.
7. **Phê duyệt:** pipeline hoặc người có thẩm quyền duyệt theo tiêu chí; lưu kết quả scan và test.
8. **Phát hành:** publish version bất biến và cập nhật catalog.
9. **Rollout:** cập nhật theo canary, rolling hoặc blue/green tùy workload.
10. **Theo dõi và thu hồi:** quan sát VM dùng phiên bản cũ, deprecation, ngăn tạo mới và retire image lỗi thời.

### 4.1. Vì sao version của image cần bất biến?

Nếu tên image latest trỏ tới artifact khác nhau theo thời điểm, cùng script deploy có thể tạo hai VM với trạng thái hệ điều hành khác nhau. Điều tra lỗi sẽ khó biết instance nào được khởi tạo từ gói nào.

Nên dùng version hoặc ID bất biến, ví dụ:

~~~text
org-linux-web-2026.11.18-build.042
org-linux-worker-2026.11.18-build.042
org-linux-base-lts-2026.11.18-build.017
~~~

Tên trên chỉ là quy ước. Nguồn sự thật phải liên kết tới **image ID/version của cloud**, recipe commit, package manifest, scan result và approval record. Tag latest có thể hữu ích cho discovery nhưng không nên là tham chiếu duy nhất của production deployment.

### 4.2. Packer và image as code

Packer là lựa chọn để mô tả cách tạo ảnh máy bằng cấu hình lưu trong version control. Recipe nêu nguồn base, provisioner, biến và output rõ ràng.

Ví dụ HCL tối giản mang tính minh họa:

~~~hcl
source "amazon-ebs" "app_base" {
  region        = var.region
  source_ami    = var.approved_base_ami
  instance_type = "t3.small"
  ssh_username  = var.ssh_username
  ami_name      = "org-app-base-build"
}

build {
  sources = ["source.amazon-ebs.app_base"]

  provisioner "shell" {
    script = "scripts/install-baseline.sh"
  }

  provisioner "shell" {
    script = "scripts/security-hardening.sh"
  }
}
~~~

Đây chỉ thể hiện cấu trúc. Pipeline thực tế phải định nghĩa biến, quyền build, vùng, tài khoản, kết nối, output, kiểm tra và cơ chế dọn máy build. Không hardcode credential hoặc dùng placeholder như cấu hình có thể apply ngay. Tên builder và thuộc tính cần đối chiếu với version Packer/plugin đang dùng.

## 5. Hardening và baseline hệ điều hành

Golden image là điểm kiểm soát tốt để áp baseline đồng bộ, nhưng hardening phải dựa trên threat model, workload và tiêu chuẩn tổ chức áp dụng.

**Tài khoản và xác thực.** Vô hiệu tài khoản mặc định không cần; hạn chế quyền sudo/admin; quản lý SSH/RDP qua danh tính tập trung hoặc cơ chế truy cập được kiểm soát; mỗi VM dùng machine identity riêng.

**Dịch vụ và port.** Gỡ hoặc tắt dịch vụ không cần; chỉ bật port workload cần; không mở SSH/RDP ra Internet công khai theo mặc định.

**Hệ thống file và kernel.** Cấu hình quyền file, mount option và kernel parameter khi baseline yêu cầu; tránh tùy chỉnh chung có thể phá workload khác. Kiểm thử tương thích driver, storage và monitoring.

**Audit và log.** Bật audit theo nhu cầu, ghi hành động quản trị, đăng nhập và sự kiện quan trọng; chuyển log về hệ thống tập trung qua đường được bảo vệ. Không ghi token, password hoặc dữ liệu cá nhân không cần thiết.

**Mã hóa và khóa.** Mã hóa volume/boot disk theo chính sách; lấy khóa và secret theo identity runtime; không lưu private key dùng chung trong image.

**Software supply chain.** Chỉ lấy package từ repository được quản lý; pin version khi cần tái lập; kiểm tra chữ ký/hash; scan dependency; ghi nhận nguồn và bản quyền phần mềm.

**Security agent.** EDR, vulnerability agent, host firewall hoặc endpoint monitoring phải có version, chính sách cập nhật, trạng thái sức khỏe và quy trình xử lý khi agent không hoạt động.

### 5.1. Baseline không phải checklist bất biến

Image cho web stateless và database có thể cần baseline khác nhau. Database có I/O và kernel tuning riêng; image GPU worker cần driver tương thích với GPU/runtime; workload legacy có thể phụ thuộc thư viện cũ.

Cách phù hợp là duy trì **base image chung** với hardening nền, tạo **image family theo vai trò** nếu khác biệt package/driver đủ lớn, kế thừa baseline và ghi ngoại lệ có owner, thời hạn và biện pháp bù. Không tạo image family riêng cho mọi dự án nếu chỉ khác vài tham số có thể inject lúc boot.

## 6. Image, bootstrapping và quản lý cấu hình

Không phải cấu hình nào cũng nên đóng vào image. Cần phân biệt:

| Nhóm | Ví dụ | Vị trí phù hợp |
| --- | --- | --- |
| **Bất biến, dùng chung** | OS package, runtime, agent version, baseline system config | Golden image |
| **Theo môi trường/nhóm** | Region endpoint, log destination, service port, feature setting | IaC, template, configuration management hoặc metadata được kiểm soát |
| **Bí mật và danh tính** | Password, token, private key, DB credential | Secret manager, identity service, PKI hoặc secure provisioning |

### 6.1. cloud-init và startup script

cloud-init hoặc startup script có thể đặt hostname, đăng ký agent, tải cấu hình, lấy certificate, khởi tạo dịch vụ hoặc gửi trạng thái về control plane.

Không biến startup script thành hệ thống cài đặt khổng lồ khiến boot kéo dài và không thể tái lập. Nếu script tải package từ repository thay đổi theo thời gian, cùng image version có thể cho kết quả khác nhau ở hai lần tạo VM.

- Đóng gói runtime nền tảng và thành phần có version cố định trong image.
- Dùng startup config cho tham số môi trường, machine identity và bootstrap nhỏ.
- Nếu cài package lúc boot, pin phiên bản, kiểm tra checksum và quản lý repository.
- Thiết kế script **idempotent**: chạy lại không tạo cấu hình trùng hay phá trạng thái hợp lệ.
- Có timeout, retry có giới hạn và log rõ; health check chỉ báo ready khi workload thật sự sẵn sàng.
- Không ghi secret vào user-data/startup log; dùng identity tối thiểu để lấy từ secret manager.

### 6.2. Configuration drift

Configuration drift là khác biệt giữa cấu hình được khai báo/duyệt và trạng thái thực tế. Một kỹ sư cài thêm package thủ công trên VM production có thể khiến máy đó khác với image và replica còn lại.

Cách kiểm soát: hạn chế sửa trực tiếp production VM; đưa thay đổi qua code/recipe/configuration management; theo dõi package, agent và cấu hình bảo mật; phát hiện drift bằng policy scan; với VM stateless ưu tiên replace bằng image mới đã kiểm tra. Với stateful hoặc legacy VM, cần quy trình drift có kiểm soát vì thay máy không đơn giản.

## 7. Thiết kế template cho nhóm VM

Một VM group thường cần các đầu vào:

- **Image/version:** ID image chuẩn hóa theo vai trò.
- **Machine type/size:** vCPU, RAM, kiến trúc CPU, GPU nếu có.
- **Network:** VPC/VNet, subnet, security group/firewall, route và load balancer.
- **Identity:** service account/managed identity/instance profile với quyền tối thiểu.
- **Storage:** boot disk, volume dữ liệu, encryption, snapshot/backup policy.
- **Metadata/bootstrap:** environment, owner, role, startup config không chứa secret.
- **Health:** startup, liveness/readiness, application check và cơ chế thay instance.
- **Scale:** desired/min/max capacity, metric và cooldown.
- **Maintenance:** patch window, disruption budget, rollout batch và rollback.

Ví dụ mô tả group ở mức khái niệm:

~~~yaml
group:
  name: prod-web
  owner: web-platform
  environment: production
  image:
    family: org-linux-web
    version: "2026.11.18-build.042"
  machine:
    architecture: x86_64
    instance_class: general_purpose
    vcpu: 4
    memory_gib: 16
  placement:
    zones: [zone-a, zone-b, zone-c]
    minimum_instances: 3
    maximum_instances: 20
  network:
    ingress: load_balancer_only
    egress_policy: approved_destinations
  identity:
    role: prod-web-runtime
    secret_source: managed_secret_store
  storage:
    boot_disk_encrypted: true
    persistent_user_data: false
  health:
    readiness_check: application_ready
    replace_unhealthy: true
  scaling:
    metric: requests_per_instance
    target: approved_capacity_target
~~~

Đây là bản mô tả kiến trúc, **không phải schema áp dụng chung cho Terraform hay API cloud**. Instance class, zone, metric, target và policy phải được map vào provider cụ thể, kiểm tra quota và phê duyệt trước khi deploy.

### 7.1. Desired state và observed state

- **Desired state:** số instance, image version, machine size, cấu hình và chính sách mong muốn.
- **Observed state:** instance thực tế, version đang chạy, health, zone, package và dung lượng.

Nhóm VM được quản lý tốt khi có thể so sánh hai trạng thái, phát hiện drift và xử lý khi khác nhau. Không nên chỉ thấy group có năm VM rồi kết luận tất cả đang dùng cùng image hoặc patch mới.

## 8. Autoscaling và cân bằng tải

Đối với workload stateless, managed instance group có thể tự tạo hoặc xóa VM dựa trên metric. Autoscaling cần thiết kế cùng load balancer và giới hạn ứng dụng.

| Metric | Phù hợp khi | Rủi ro nếu dùng đơn lẻ |
| --- | --- | --- |
| CPU utilization | Xử lý tính toán chủ yếu CPU-bound | Không phản ánh request khi CPU còn nhàn nhưng ứng dụng chờ DB |
| Memory utilization | Workload tăng bộ nhớ theo số kết nối/worker | Memory có thể khó giảm khi scale down |
| Request per instance | Web/API có traffic đo được | Cần kiểm soát độ phức tạp request và phân phối tải |
| Queue depth/backlog | Worker xử lý tác vụ bất đồng bộ | Số message không phản ánh đầy đủ tuổi message |
| Processing lag | Streaming/queue cần xử lý kịp thời | Cần đo watermark và tốc độ tiêu thụ đúng |
| Scheduled scaling | Có giờ cao điểm dự báo | Không phản ứng đủ nhanh với biến động bất ngờ |

Không dùng CPU 70% như ngưỡng phổ quát. Target phụ thuộc SLO latency, tốc độ tăng tải, thời gian boot và năng lực instance.

### 8.1. Warm-up và thời gian khởi động

Nếu VM mất 5–8 phút để boot, cài agent và nạp ứng dụng, autoscaling phản ứng sau khi tải tăng có thể quá muộn. Golden image giúp rút ngắn thời gian cài đặt, nhưng cần đo **time-to-ready** thực tế, gồm kiểm tra mạng, secret, dependency và health check.

Có thể cần duy trì số instance tối thiểu, dùng scheduled scaling cho pattern đã biết, giữ buffer capacity, tối ưu boot và scale theo leading metric như request rate hoặc queue arrival rate thay vì chỉ CPU trễ sau khi quá tải.

### 8.2. Scale down an toàn

Trước khi worker VM bị xóa:

1. Ngừng nhận job mới.
2. Hoàn tất hoặc checkpoint công việc đang xử lý.
3. Ack message sau khi ghi trạng thái bền vững.
4. Đóng kết nối và flush log/metrics cần thiết.
5. Báo health controller rằng instance đã ngừng phục vụ.
6. Mới cho phép terminate.

Nếu ứng dụng không hỗ trợ graceful shutdown hoặc idempotency, scale down có thể gây trùng tác vụ hoặc mất tiến độ. Với VM stateful, cần thiết kế riêng cho leader, replication, quorum và dữ liệu; không áp dụng cơ chế thay instance stateless một cách máy móc.

## 9. Cập nhật image và rollout theo nhóm

Phát hành image mới không có nghĩa phải tắt toàn bộ máy cũ cùng lúc. Rollout cần cân nhắc availability, capacity, tương thích dữ liệu và khả năng rollback.

| Chiến lược | Cách làm | Lợi ích | Đánh đổi |
| --- | --- | --- | --- |
| **Rolling replacement** | Thay từng batch instance cũ bằng instance mới | Duy trì một phần capacity | Phiên bản cũ/mới cùng chạy trong giai đoạn chuyển tiếp |
| **Canary** | Thay tỷ lệ nhỏ trước, quan sát rồi mở rộng | Giới hạn phạm vi lỗi ban đầu | Cần metric và tiêu chí dừng rõ |
| **Blue/green** | Tạo group mới, kiểm tra rồi chuyển traffic | Rollback chuyển traffic nhanh | Tốn tài nguyên song song, cần kiểm soát session/data |
| **Replace all** | Dừng và tạo lại toàn bộ | Đơn giản cho môi trường chấp nhận downtime | Không phù hợp workload cần availability |
| **In-place patching** | Cập nhật hệ điều hành trên instance đang chạy | Có thể cần cho workload stateful/legacy | Tạo drift và khó tái lập hơn |

~~~mermaid
flowchart TB
    IMG["Image version mới đã phê duyệt"] --> CANARY["Tạo canary group / thay 1 instance"]
    CANARY --> CHECK{"Health, latency, lỗi và bảo mật đạt?"}
    CHECK -- "Không" --> STOP["Dừng rollout, cô lập và rollback"]
    CHECK -- "Có" --> BATCH["Rolling theo batch nhỏ"]
    BATCH --> WATCH["Theo dõi metric và error budget"]
    WATCH --> OK{"Tiêu chí tiếp tục đạt?"}
    OK -- "Không" --> STOP
    OK -- "Có" --> FULL["Hoàn thành rollout"]
    FULL --> RETIRE["Deprecated image cũ"]
~~~

Tiêu chí canary có thể gồm boot/readiness thành công, CPU/RAM/disk/network trong giới hạn, tỷ lệ 5xx và latency p95/p99, security agent, vulnerability scan, kết quả nghiệp vụ và tương thích dependency.

### 9.1. Rollback image không phải lúc nào cũng đủ

Nếu image mới đi cùng thay đổi schema DB hoặc format dữ liệu không tương thích, khôi phục VM về image cũ có thể không phục hồi được dữ liệu. Cần thay đổi schema tương thích ngược, backup/restore test, feature flag, tách quyết định rollback ứng dụng/image/database và ghi tiêu chí dừng rollout.

## 10. Quản lý bản vá và tuổi đời image

Image chuẩn hóa chỉ có giá trị khi được cập nhật thường xuyên. Golden image không được duy trì có thể trở thành **đường phát tán lỗ hổng** vì nhiều VM được tạo từ cùng baseline cũ.

- **Immutable replacement:** build image mới, tạo instance mới, chuyển traffic và retire instance cũ; phù hợp nhiều workload stateless.
- **In-place patching:** cập nhật package trên VM hiện có; có thể cần cho stateful hoặc legacy, nhưng phải quản lý drift.
- **Hybrid:** image cung cấp baseline; agent/package manager quản lý một số bản vá khẩn hoặc nội dung thay đổi nhanh theo chính sách.

Một zero-day nghiêm trọng có thể yêu cầu biện pháp tạm thời hoặc cập nhật ngay instance đang chạy trước khi image pipeline kịp phát hành bản mới.

Policy tuổi đời image cần xác định chu kỳ cập nhật, thời hạn hiệu lực tối đa, thời điểm deprecated, chặn tạo VM mới từ image hết hạn, quy trình exception có owner và deadline, báo cáo VM đang chạy version cũ và retention phục vụ rollback/DR. Thời hạn cụ thể phụ thuộc chính sách tổ chức và workload, không có một số ngày chung cho mọi trường hợp.

## 11. Backup, snapshot và khôi phục

**Image, snapshot và backup có mục đích khác nhau.**

| Artifact | Mục đích chính | Điều không nên giả định |
| --- | --- | --- |
| Golden image | Tạo VM với baseline OS/phần mềm đã kiểm soát | Không phải backup dữ liệu nghiệp vụ |
| Boot disk snapshot | Khôi phục trạng thái disk tại thời điểm chụp | Có thể không nhất quán ứng dụng nếu không quiesce |
| Data volume backup | Bảo vệ dữ liệu workload | Không thay thế restore test và tính nhất quán đa volume |
| Database backup/log backup | Phục hồi dữ liệu và thời điểm | Không thể chỉ dựa vào image chứa database software |
| IaC/config backup | Tái tạo cấu hình và hạ tầng | Không chứa mọi state bên ngoài nếu chưa export |

Đối với web/worker stateless, phương án thường là tái tạo VM từ golden image và IaC, lấy cấu hình/secret lúc boot; dữ liệu bền vững nằm trong DB, object store hoặc dịch vụ thích hợp.

Đối với database hoặc ứng dụng lưu dữ liệu trên disk cục bộ, phải dùng native backup, snapshot/quiesce hoặc replication được hỗ trợ; xác định transaction consistency, giữ key giải mã, RPO/RTO, và diễn tập restore. Không tạo golden image từ database VM đang chạy rồi coi image đó là backup hợp lệ.

## 12. Bảo mật và supply chain cho image

Image là artifact đặc quyền: mã trong image có thể nhận quyền machine identity của VM. Do đó, pipeline build image là một phần của chuỗi cung ứng phần mềm.

| Rủi ro | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Base image không rõ nguồn | Mã độc hoặc package bị sửa | Chỉ dùng nguồn được duyệt; kiểm chứng chữ ký/hash nếu có |
| Build pipeline bị xâm nhập | Golden image phát tán mã độc đến nhiều VM | Isolate build runner, quyền tối thiểu, secret ngắn hạn, audit |
| Secret bị đóng vào image | Nhiều instance cùng lộ credential | Secret scanning và loại bỏ secret trước publish |
| Image lỗi thời | Nhiều VM dùng package có lỗ hổng | Scan định kỳ, expiry/deprecation, patch SLA |
| Artifact bị thay sau publish | VM tạo từ artifact sai nguồn | Version bất biến, hash/signature, quyền write hạn chế |
| Metadata/user-data không an toàn | Secret xuất hiện trong log hoặc bị đọc | Không đặt secret trong metadata công khai |
| Image từ production VM | Mang dữ liệu, log hoặc identity cũ | Build từ pipeline sạch, scrub và kiểm tra |

### 12.1. Provenance và chữ ký

Với image quan trọng, lưu base image ID/publisher, recipe commit, build tool, package manifest, dependency source, scan/test result, pipeline identity, approval, image ID/checksum/signature và nơi publish.

Nếu nền tảng hỗ trợ image signing hoặc policy chỉ cho phép launch từ image được duyệt, hãy kết hợp với IAM và audit. **Có chữ ký chỉ chứng minh artifact tương ứng với khóa ký**, không tự chứng minh nội dung an toàn; bảo vệ signing key và kiểm soát build vẫn phải đáng tin cậy.

### 12.2. Quyền truy cập image catalog

- Chỉ pipeline phát hành được quyền publish vào catalog production.
- Nhóm workload chỉ được đọc/pull image version được cấp phép.
- Chia sẻ image giữa account/project theo allowlist.
- Ngăn user thông thường tạo VM từ image chưa được duyệt.
- Audit copy, share, modify permission, deprecate và delete.
- Không coi image public là an toàn chỉ vì nằm trong catalog của nhà cung cấp.

## 13. Định danh máy và secrets khi tạo VM

Một lỗi thường gặp là tạo golden image từ máy đã đăng ký domain hoặc cấp certificate rồi clone máy đó hàng loạt. Nếu identity cũ được nhân bản, hệ thống có thể có hostname, certificate, agent ID hoặc key trùng nhau.

Cần tách:

- **Machine identity:** tạo riêng cho mỗi instance khi boot/provisioning qua quy trình tin cậy; không đóng khóa riêng của máy mẫu vào image.
- **Service identity:** VM nhận quyền cần thiết để gọi DB, object store, secret manager hoặc message queue; dùng managed identity/instance role nếu hỗ trợ.
- **User identity:** người vận hành kết nối qua hệ thống quản trị tập trung, MFA và quyền thời hạn; không dùng chung tài khoản quản trị local cho fleet.
- **Secrets:** cấp phát lúc runtime theo machine/service identity; lưu trong secret manager hoặc PKI, có xoay vòng, thu hồi và audit.

Sau khi clone từ image, mỗi VM cần tạo hostname/agent registration/certificate phù hợp và báo trạng thái về inventory. Quy trình deprovision phải thu hồi danh tính, chứng chỉ và quyền khi VM bị xóa.

## 14. Triển khai đa vùng và phục hồi thảm họa

Golden image giúp chuẩn hóa VM giữa các vùng, nhưng image không tự động portable. Các vùng có thể khác nhau về image catalog/ID, instance family, CPU architecture, quota, subnet, security group/firewall, route, DNS, encryption key, storage, load balancer và license.

Một kế hoạch DR phải xác định image nào được copy hoặc build lại ở vùng dự phòng, ai phê duyệt, cách đảm bảo checksum/provenance và cách thay tham số vùng lúc khởi tạo.

| Mô hình | Mô tả | Đánh đổi |
| --- | --- | --- |
| **Backup and restore** | Giữ image/config/backup; tạo VM khi có sự cố | Chi phí thấp hơn, RTO có thể dài |
| **Pilot light** | Duy trì một số thành phần tối thiểu, scale khi cần | Khởi động nhanh hơn nhưng phải test dependency |
| **Warm standby** | Nhóm VM nhỏ ở vùng dự phòng luôn chạy | RTO thấp hơn, chi phí duy trì cao hơn |
| **Active-active** | Nhiều vùng cùng phục vụ traffic | Phức tạp về dữ liệu, routing, deployment và chi phí |

Chọn theo RTO/RPO nghiệp vụ và khả năng chịu lỗi. Nếu chỉ giữ image ở vùng chính và chờ copy khi thảm họa, thời gian phục hồi phải tính cả copy artifact, quota, tạo disk, bootstrap, identity, health check và chuyển traffic.

## 15. Tối ưu chi phí nhóm VM

Golden image không tự làm VM rẻ hơn. TCO cần tính compute theo instance size/CPU/GPU/thời gian, boot và data disk, snapshot và image storage, license, NAT/egress/log/monitoring/backup, buffer capacity, chi phí build pipeline, test, image catalog, bảo trì recipe và nhân sự.

- Dùng autoscaling cho workload có tải biến động; giữ min capacity theo availability.
- Scale nhỏ môi trường dev/test ngoài giờ theo chính sách.
- Chọn family theo CPU, memory, storage, network và accelerator được đo.
- Tránh giữ instance quá lớn chỉ để phòng một đỉnh tải hiếm.
- Tách workload bursty khỏi workload latency-sensitive khi cần.
- Theo dõi orphan disk, snapshot, image version và VM không còn owner.
- Đánh giá commitment/reservation khi tải nền đủ ổn định và mô hình mua phù hợp.

Giữ vô hạn image và snapshot cũ làm tăng chi phí lưu trữ, nhưng xóa tất cả ngay sau release có thể phá hỏng rollback và DR. Cần retention policy: giữ version đã phê duyệt, artifact phục vụ điều tra theo thời hạn, xóa snapshot tạm và bảo vệ bản cần cho recovery.

## 16. Quan sát và vận hành fleet

Đối với hàng trăm hoặc hàng nghìn VM, nhóm vận hành cần thấy **ai đang chạy gì, ở đâu, từ image nào và có tuân thủ không**.

### 16.1. Inventory nên có

| Thuộc tính | Ví dụ |
| --- | --- |
| VM ID/hostname | Định danh duy nhất |
| Group/workload role | prod-web, prod-worker |
| Environment/region/zone | production, region-a, zone-b |
| Image ID/version | Image đã được phê duyệt |
| OS/kernel/package baseline | Phiên bản thực tế |
| Instance type/architecture | General purpose x86_64 |
| Owner/service | Đội chịu trách nhiệm |
| Identity/profile | Service identity được cấp |
| Patch/compliance state | compliant, pending, exception |
| Created/updated time | Lịch sử vòng đời |
| Health/agent status | ready, degraded, offline |

### 16.2. Chỉ số nên theo dõi

- **Fleet compliance:** tỷ lệ VM chạy image được duyệt, patch level đạt chuẩn và security agent khỏe.
- **Image adoption:** thời gian từ khi phát hành image mới đến khi production áp dụng.
- **Provisioning latency:** từ yêu cầu tạo VM đến lúc ứng dụng ready.
- **Replacement success:** tỷ lệ thay instance thành công và số lần rollback.
- **Capacity:** CPU, RAM, disk, network và số instance theo zone.
- **Application SLO:** latency, error rate, request rate, queue lag và transaction success.
- **Lifecycle:** image hết hạn, VM không owner, instance sai region hoặc quyền quá rộng.

Log, metric và trace cần gắn group/image version để điều tra tác động của lần phát hành. Không gửi dữ liệu nhạy cảm không cần thiết lên hệ thống quan sát; áp retention và quyền truy cập.

## 17. Ví dụ hoàn chỉnh: nhóm web production với golden image

Giả sử nền tảng đặt thuê thiết bị chạy API Java trên ba availability zone. Yêu cầu giả định:

| Thuộc tính | Yêu cầu |
| --- | --- |
| Workload | Web/API stateless |
| Sẵn sàng | Ít nhất 3 instance healthy, phân bố 3 zone nếu dịch vụ hỗ trợ |
| Scale | Từ 3 đến 18 instance theo request rate và CPU |
| Runtime | Java LTS được phê duyệt |
| Network | Chỉ nhận traffic từ load balancer |
| Data | Không lưu trạng thái phiên hoặc nghiệp vụ bền vững trên boot disk |
| Access | Service identity tối thiểu, quản trị qua hệ thống được kiểm soát |
| Image | OS được hỗ trợ, patch và agent đã kiểm thử, version bất biến |

### 17.1. Image family và group template

Golden image family org-linux-java-web chứa Linux base version được duyệt, security patch, baseline hệ điều hành, Java runtime cụ thể, logging/monitoring/security agent đã kiểm tra, trust store và startup agent. Không chứa private key hoặc secret môi trường.

Group template tham chiếu image version cố định, machine type đã load test, subnet ở ba zone, service identity prod-web-runtime, boot disk mã hóa, load balancer health check và scaling policy. Đây là tên minh họa.

### 17.2. Quy trình phát hành

1. Pipeline lấy base image ID đã duyệt và recipe từ Git.
2. Build image trong tài khoản/project riêng với quyền tối thiểu; hủy builder tạm khi xong.
3. Cài patch, Java runtime và agent; thực hiện hardening.
4. Scan package/CVE, boot test, smoke test và compliance test.
5. Ghi provenance; phê duyệt và publish image ID/version bất biến.
6. Tạo canary instance trong staging rồi production với tỷ lệ nhỏ.
7. Quan sát lỗi, latency, resource, agent và kết quả nghiệp vụ.
8. Rolling replace các instance còn lại theo batch; duy trì capacity và disruption limit.
9. Đối chiếu inventory để xác nhận instance đã dùng image mới hoặc có exception được duyệt.
10. Deprecated image cũ theo retention policy, giữ rollback trong khoảng thời gian yêu cầu.

### 17.3. Sự cố giả định sau canary

Sau khi thay một instance, p99 latency tăng mạnh. Điều tra cho thấy Java runtime mới thay đổi default connection pool và làm số kết nối database tăng. Quy trình tốt sẽ dừng rollout khi metric vượt ngưỡng, cô lập hoặc rollback canary, xác định tương quan với image version, kiểm thử pool và DB quota trong staging, phát hành image/recipe đã sửa và thêm tình huống lỗi vào test suite.

Golden image giảm drift nhưng **không bảo đảm ứng dụng không có regression**. Kiểm thử phải có lớp OS, runtime và hành vi workload.

## 18. Tiêu chí chọn số lượng image family

Không nên tạo một image mới cho mỗi team hoặc VM. Quá nhiều family làm nặng build, scan, patch, phê duyệt và retention.

Cân nhắc tạo family riêng khi khác nhau thực sự về OS/CPU architecture, driver/kernel dependency, runtime/package cơ sở, security baseline, vòng đời patch hoặc chế độ khởi động.

Nếu khác biệt chỉ là endpoint, môi trường, port hay feature flag, có thể cấu hình theo group/boot thay vì fork image. Điều này giảm số nhánh và giữ baseline thống nhất.

## 19. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng snapshot VM production làm golden image | Mang theo dữ liệu, log, secret hoặc identity cũ | Build sạch từ base image; scan và scrub |
| Một image cho mọi workload | Runtime, driver và baseline không phù hợp | Base family chung, family theo vai trò khi cần |
| Dùng tag latest trong production | Cùng template tạo trạng thái khác nhau | Pin image ID/version bất biến |
| Cài package không pin lúc boot | Hai VM cùng image vẫn khác nhau | Đưa package vào image hoặc pin/verify |
| Đưa secret vào image/user-data | Lan credential qua fleet và log | Secret manager, machine identity, secret scanning |
| Tạo identity rồi clone | Certificate/agent ID/hostname trùng | Enrollment riêng sau boot |
| Cập nhật tất cả VM cùng lúc | Lỗi image ảnh hưởng toàn fleet | Canary, rolling batch, stop/rollback |
| Patch VM thủ công nhưng không cập nhật recipe | Drift, VM mới vẫn có lỗ hổng | Đưa thay đổi vào pipeline |
| Coi image là backup database | Không bảo toàn tính nhất quán dữ liệu | Native backup, restore test, DR plan |
| Rollback app nhưng bỏ qua schema | Phiên bản cũ không tương thích | Expand–migrate–contract, test rollback |
| Autoscaling chỉ theo CPU | Phản ứng trễ hoặc sai nút thắt | Metric gắn với SLO và tải nghiệp vụ |
| Chỉ có image ở region chính | DR mất thời gian copy và thiếu dependency | Replicate/build ở vùng hợp lệ, diễn tập |
| Không retire image lỗi thời | Tiếp tục tạo VM từ artifact có lỗ hổng | Deprecation, policy ngăn launch, retention |

## 20. Quy trình bàn giao và nghiệm thu

Một thiết kế VM group và golden image nên bàn giao được:

1. **Workload classification:** vai trò group, owner, môi trường, dữ liệu và mức quan trọng.
2. **Group specification:** image version, machine family, network, identity, storage, health, autoscaling và maintenance.
3. **Image build recipe:** nguồn base, package manifest, hardening, version và công cụ build.
4. **Image verification evidence:** scan, boot/smoke test, compliance, approval và provenance.
5. **Rollout/rollback plan:** canary, batch, capacity floor, tiêu chí dừng và khôi phục.
6. **Patch/lifecycle policy:** tuổi đời image, exception, deprecation, retirement và xử lý VM cũ.
7. **Backup/DR plan:** phân biệt image với dữ liệu; RTO/RPO và kết quả diễn tập.
8. **Operations dashboard/runbook:** inventory, drift, health, scale, cảnh báo và người xử lý.

### Checklist nghiệm thu

- [ ] Mỗi nhóm VM có vai trò, owner và ranh giới quyền truy cập rõ.
- [ ] Mọi group tham chiếu image version bất biến và machine type đã kiểm thử.
- [ ] Image được build từ nguồn tin cậy, có recipe version control và provenance.
- [ ] Secret, private key, dữ liệu người dùng và machine identity cũ không nằm trong image.
- [ ] Hardening, patch, agent và package baseline đã được kiểm tra.
- [ ] Image boot thành công và workload readiness đạt tiêu chí gần production.
- [ ] VM có identity riêng và chỉ được cấp quyền cần thiết.
- [ ] Autoscaling có metric, min/max, cooldown và graceful shutdown.
- [ ] Rolling/canary có tiêu chí dừng, rollback và capacity còn lại đủ.
- [ ] Cấu hình môi trường được tách khỏi image; drift được phát hiện và xử lý.
- [ ] Backup dữ liệu, image retention và DR được thiết kế riêng, có restore test.
- [ ] Inventory cho biết từng VM chạy image, patch level và policy nào.

## 21. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Nhóm chạy đa zone phù hợp? Instance hỏng có được thay an toàn? Rollout image mới có giữ đủ capacity? Database và stateful data có backup/restore test? |
| **Bảo mật** | Base image đến từ đâu? Có scan, hardening, signing/provenance? Secret và machine identity được cấp riêng? Image cũ có bị ngăn tạo mới? |
| **Hiệu quả hiệu năng** | Machine family phù hợp CPU/RAM/I/O/network? Startup latency, autoscaling lag và resource contention có đạt mục tiêu? |
| **Tối ưu chi phí** | Có overprovisioning, idle VM, snapshot/image dư thừa hoặc license? Min capacity và retention có phù hợp? |
| **Khả năng vận hành** | Có inventory, version adoption, drift detection, rollout automation, log/metrics và owner? |

Chuẩn hóa image và VM groups không chỉ nhằm tiết kiệm thời gian khởi tạo. Nó tạo ra một **đường kiểm soát có thể lặp lại từ nguồn phần mềm đến instance đang chạy**. Khi mỗi VM biết được nó thuộc group nào, dùng image nào, nhận quyền gì và đã qua kiểm thử nào, tổ chức có thể xử lý thay đổi và sự cố dựa trên bằng chứng.

## 22. Bài tập áp dụng

Một doanh nghiệp chạy ứng dụng quản lý đơn hàng trên cloud, gồm API, worker xử lý đơn và nhóm máy báo cáo. API cần duy trì ít nhất ba instance; worker tăng số lượng khi queue backlog cao; báo cáo chỉ chạy ban đêm và cần RAM lớn. Hiện tại các VM được tạo thủ công và một số máy dùng hệ điều hành đã hết thời hạn hỗ trợ.

Hãy thiết kế:

1. Các VM group cần có, role và owner của từng group.
2. Image family nào dùng chung, image nào cần tách và tại sao?
3. Quy trình build, scan, phê duyệt và publish image mới.
4. Cách lấy cấu hình môi trường, secret và machine identity lúc boot.
5. Autoscaling metric cho API và worker; cách chạy báo cáo mà không ảnh hưởng API/database.
6. Kế hoạch thay máy dùng OS hết hỗ trợ, gồm canary, rollback, kiểm tra dữ liệu và lịch deprecation.
7. Chỉ số chứng minh fleet đã đồng bộ và không còn VM ngoài chính sách.

Một đáp án tốt giải thích được vì sao các workload thuộc những group khác nhau, image có thể dùng chung đến mức nào, và quy trình thay VM không làm mất dữ liệu hoặc giảm availability vượt giới hạn.

**Điểm cốt lõi:** nhóm VM xác định cách tổ chức và quản lý workload; golden image xác định baseline có thể tái lập để tạo instance. Chúng chỉ phát huy hiệu quả khi gắn với IaC, identity, secret management, patching, kiểm thử, rollout và quan sát. Trong kiến trúc Cloud Architecture, mục tiêu là tạo fleet máy ảo có cấu hình nhất quán, quyền hạn đúng, có thể thay thế và phục hồi, với chi phí cũng như rủi ro vận hành được kiểm soát.
