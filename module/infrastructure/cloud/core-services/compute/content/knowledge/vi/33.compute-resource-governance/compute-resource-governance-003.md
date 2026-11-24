# Chính sách giới hạn region, machine type và nguồn image được phép

Trong môi trường cloud, người dùng có thể tạo máy ảo ở nhiều region, chọn nhiều loại máy và khởi chạy từ nhiều nguồn image. Nếu không có chính sách quản trị, một workload có thể được triển khai ở region không đáp ứng yêu cầu dữ liệu, dùng machine type vượt ngân sách hoặc khởi động từ image không được kiểm duyệt.

Chính sách giới hạn region, machine type và nguồn image tạo ra ranh giới an toàn cho hoạt động cấp phát compute. Region allowlist quy định nơi workload được phép chạy; machine type policy giới hạn family, size, kiến trúc và accelerator; image source policy chỉ cho phép image từ nhà phát hành hoặc registry đã được tin cậy. Các chính sách cần được quản lý tập trung, kiểm tra trong Infrastructure as Code (IaC), thực thi ở control plane và giám sát liên tục.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, chương **Quản trị tài nguyên compute**. Nội dung tập trung vào cách thiết kế allowlist và deny-by-default, áp dụng chính sách theo tổ chức/project/subscription, kiểm soát region, machine type và image, quản lý ngoại lệ, audit vi phạm và triển khai policy-as-code an toàn.

## 1. Vì sao cần giới hạn tài nguyên compute?

Quyền tạo VM hoặc node thường cho phép người dùng chọn nhiều thuộc tính ảnh hưởng trực tiếp tới bảo mật, chi phí và tuân thủ:

- Region và zone quyết định vị trí dữ liệu, độ trễ, khả năng phục hồi và nơi phát sinh chi phí.
- Machine type quyết định CPU, RAM, GPU, network performance, kiến trúc và đơn giá.
- Image source quyết định hệ điều hành, package, agent, cấu hình bảo mật và phần mềm có sẵn khi máy khởi động.

Một người dùng có thể có quyền tạo VM hợp lệ nhưng vẫn chọn cấu hình không phù hợp chính sách doanh nghiệp. Ví dụ, triển khai workload chứa dữ liệu nhạy cảm ở region chưa được phê duyệt; tạo GPU instance đắt tiền cho một dịch vụ không cần accelerator; hoặc khởi động từ public image không rõ nguồn gốc.

### 1.1. Ba nhóm rủi ro

| Nhóm | Rủi ro | Hệ quả |
|---|---|---|
| Region | Dữ liệu hoặc workload ở vị trí không được phê duyệt | Vi phạm residency, tăng latency, khó đáp ứng yêu cầu pháp lý |
| Machine type | Dùng family/size/GPU không phù hợp hoặc không được phép | Vượt ngân sách, thiếu quota, mở rộng attack surface |
| Image source | Image chưa kiểm tra, cũ, chứa lỗ hổng hoặc bị thay đổi | Compromise hệ thống, cấu hình không đồng nhất, khó truy vết |

Chính sách cần ngăn lựa chọn rủi ro ngay trước khi tài nguyên được tạo, đồng thời phát hiện tài nguyên đã tồn tại nhưng không còn phù hợp.

### 1.2. Governance không thay thế thiết kế workload

Policy có thể giới hạn những lựa chọn được phép, nhưng không tự chọn cấu hình tối ưu cho ứng dụng. Nhóm workload vẫn phải xác định CPU/RAM, storage, network, HA và chi phí dự kiến. Governance đặt ranh giới để lựa chọn nằm trong vùng tổ chức chấp nhận.

## 2. Nguyên tắc thiết kế policy

Một chính sách tốt phải dễ hiểu, có thể kiểm thử, có chủ sở hữu và có cách xử lý ngoại lệ rõ ràng.

### 2.1. Allowlist và deny-by-default

Allowlist chỉ định rõ những region, machine type hoặc image source được phép. Những giá trị không có trong danh sách mặc định bị từ chối hoặc yêu cầu phê duyệt.

Ví dụ chính sách khái niệm:

~~~yaml
computeGovernance:
  allowedRegions:
    - ap-southeast-1
    - ap-southeast-2
  allowedMachineTypes:
    - general-purpose.small
    - general-purpose.medium
    - memory-optimized.large
  allowedImageSources:
    - project: platform-golden-images
    - registry: registry.example.internal
~~~

Đây là YAML minh họa cho mô hình policy nội bộ, không phải schema trực tiếp của AWS, Azure, Google Cloud hay Kubernetes. Khi triển khai, cần chuyển quy tắc sang policy language và resource field mà nền tảng thực tế hỗ trợ.

Deny-by-default phù hợp với tài nguyên có rủi ro cao, nhưng danh sách cho phép phải được duy trì. Nếu allowlist quá hẹp hoặc lỗi thời, nhóm phát triển có thể không triển khai được workload hợp lệ.

### 2.2. Least privilege và separation of duties

- Người dùng workload chỉ được tạo tài nguyên trong phạm vi đã phê duyệt.
- Nhóm platform/security sở hữu policy tổ chức và danh sách nguồn tin cậy.
- Nhóm ứng dụng đề xuất nhu cầu region, machine type và image.
- Nhóm vận hành kiểm tra quota, capacity, backup và khả năng hỗ trợ.
- Người phê duyệt ngoại lệ không nên tự phê duyệt thay đổi của chính mình trong trường hợp rủi ro cao.

### 2.3. Policy phải có chủ sở hữu và thời hạn xem xét

Mỗi policy nên có owner, mục tiêu, phạm vi áp dụng, ngày hiệu lực, phiên bản, lý do và lịch review. Danh sách machine type hoặc image source cần được cập nhật khi nền tảng ngừng hỗ trợ, thay đổi giá hoặc xuất hiện rủi ro bảo mật.

## 3. Các lớp policy và phạm vi kế thừa

Cloud thường có cấu trúc quản trị phân cấp. Tên gọi khác nhau giữa các provider, nhưng mô hình thường gồm tổ chức, folder/group, account/subscription/project và resource.

~~~mermaid
flowchart TD
    O["Organization policy baseline"] --> F["Folder / Management group"]
    F --> P["Account / Subscription / Project"]
    P --> R["Resource group / VPC / Cluster"]
    R --> W["VM / Node / Instance"]
    O --> G["Central policy repository"]
    G --> C["CI policy checks"]
    G --> A["Audit and compliance"]
~~~

### 3.1. Organization-level baseline

Đặt các ranh giới chung mà mọi workload phải tuân thủ:

- Chỉ cho phép region được tổ chức phê duyệt.
- Cấm hoặc giới hạn machine family rủi ro cao.
- Chỉ cho phép image từ nguồn tin cậy.
- Bắt buộc gắn tag owner, environment và cost center.
- Cấm một số cấu hình không an toàn như public IP hoặc disk encryption bị tắt nếu chính sách yêu cầu.

Baseline nên ổn định, có phạm vi rõ ràng và không chứa các ngoại lệ chỉ dành cho một ứng dụng.

### 3.2. Policy theo nhóm workload

Nhóm workload có thể cần profile khác nhau:

| Nhóm | Region | Machine type | Image |
|---|---|---|---|
| Production | Chỉ region được phê duyệt cho dữ liệu | Family production đã kiểm thử | Golden image production |
| Development | Region sandbox được phê duyệt | Small/general-purpose | Golden image development |
| HPC/AI | Region có capacity và accelerator phù hợp | GPU/HPC family được duyệt | Image HPC/AI có driver đã xác minh |
| Regulated | Region theo residency | SKU được chứng nhận và kiểm soát | Image có baseline và evidence tuân thủ |

Policy cấp nhóm có thể bổ sung giới hạn chặt hơn baseline, nhưng không được mở rộng quyền vượt qua ranh giới tổ chức nếu cơ chế policy của provider không cho phép.

### 3.3. Thứ tự ưu tiên và xung đột

Một số hệ thống có quy tắc deny luôn thắng allow; hệ thống khác có inheritance, override hoặc exemption riêng. Không giả định mọi provider xử lý policy conflict giống nhau.

Khi thiết kế, cần trả lời:

- Policy cấp tổ chức có thể bị cấp dưới override không?
- Deny có luôn thắng allow không?
- Exemption cần ai phê duyệt?
- Policy được đánh giá ở thời điểm create, update hay cả runtime?
- Tài nguyên hiện hữu bị ảnh hưởng thế nào khi policy mới được bật?

Viết test cho các trường hợp kế thừa và xung đột trước khi enforce trên production.

## 4. Chính sách giới hạn region

Region policy xác định vị trí địa lý mà tài nguyên compute được phép tạo hoặc di chuyển tới. Danh sách region cần dựa trên yêu cầu dữ liệu, pháp lý, bảo mật, độ trễ, disaster recovery và khả năng cung cấp dịch vụ.

### 4.1. Tiêu chí chọn region

- **Data residency:** dữ liệu phải lưu trữ và xử lý trong khu vực được phép.
- **Regulatory scope:** yêu cầu pháp lý, hợp đồng hoặc tiêu chuẩn ngành.
- **Latency:** khoảng cách tới người dùng, database và hệ thống tích hợp.
- **Availability:** số zone, dịch vụ và capacity thực tế.
- **Disaster recovery:** region dự phòng và khả năng phục hồi xuyên vùng.
- **Cost:** giá compute, storage, network egress và license.
- **Service parity:** machine family, GPU, managed service và feature có sẵn.

Không chọn region chỉ theo giá VM. Egress, replication, data transfer và việc thiếu loại máy cần thiết có thể làm tổng chi phí cao hơn.

### 4.2. Region allowlist

Danh sách allowlist nên dùng mã region chính thức thay vì tên hiển thị tự do. Mã region cần được đối chiếu với provider và môi trường triển khai.

Ví dụ:

~~~yaml
policy:
  name: allowed-compute-regions
  effect: deny
  when:
    resource.type: virtual-machine
    resource.region:
      notIn:
        - ap-southeast-1
        - ap-southeast-2
  message: "Compute resource region is not approved"
~~~

Đây là pseudocode. Cú pháp notIn, resource.type và effect cần được chuyển sang ngôn ngữ policy thật của nền tảng.

### 4.3. Phạm vi áp dụng

Region policy cần xem xét nhiều loại tài nguyên liên quan, không chỉ VM:

- VM, managed instance group và autoscaling group.
- Disk, snapshot và image.
- GPU/accelerator instance.
- Node pool của Kubernetes.
- Backup, replica và artifact storage.
- Resource tạo ra gián tiếp bởi managed service.

Nếu chỉ chặn VM nhưng cho phép tạo disk hoặc snapshot ở region khác, dữ liệu vẫn có thể rời khỏi phạm vi được phê duyệt.

### 4.4. Region và zone

Region gồm một hoặc nhiều availability zone. Chính sách có thể cho phép region nhưng vẫn cần giới hạn zone hoặc topology nếu workload có yêu cầu đặc biệt.

Ví dụ, một volume block có thể gắn với zone cụ thể; workload chạy ở zone khác không thể attach trực tiếp. Policy cần kết hợp region, zone, placement và khả năng HA để tránh cấu hình hợp lệ về mặt region nhưng không thể vận hành.

### 4.5. Region cho disaster recovery

Region DR cần được phê duyệt rõ ràng trước khi có sự cố. Nếu chỉ cho phép region primary, đội vận hành có thể không tạo được compute ở region dự phòng trong thời gian khẩn cấp.

Danh sách DR nên xác định region chính và region dự phòng, loại workload được phép failover, dữ liệu nào được replicate, quyền tạo tài nguyên trong tình huống DR, cách ghi nhận và hết hạn quyền khẩn cấp.

## 5. Chính sách giới hạn machine type

Machine type xác định cấu hình phần cứng ảo hoặc node profile: CPU, RAM, GPU, local storage, network bandwidth, kiến trúc và đặc tính hiệu năng. Policy cần giới hạn cả family lẫn size phù hợp với từng môi trường.

### 5.1. Allowlist theo family và size

Một machine type allowlist có thể giới hạn:

- General-purpose cho workload web/API.
- Compute-optimized cho workload CPU-bound.
- Memory-optimized cho database hoặc in-memory analytics.
- Storage-optimized cho I/O-intensive workload.
- GPU/accelerator family cho HPC/AI.
- Arm hoặc x86 architecture theo khả năng tương thích.

Không nên chỉ allow một family mà không giới hạn size. Một family có thể chứa các size rất lớn với chi phí cao.

### 5.2. Ví dụ policy theo môi trường

~~~yaml
machineProfiles:
  development:
    allowedFamilies:
      - general-purpose
    maxVcpu: 8
    maxMemoryGiB: 32
    accelerators: forbidden
  production:
    allowedFamilies:
      - general-purpose
      - compute-optimized
      - memory-optimized
    allowedSizes:
      - general-purpose.medium
      - compute-optimized.large
      - memory-optimized.large
  hpc:
    allowedFamilies:
      - hpc
      - gpu-accelerated
    requireApproval: true
~~~

Đây là schema minh họa nội bộ. Tên family và size phải map sang machine SKU thực tế của provider. maxVcpu và maxMemoryGiB là điều kiện bổ sung, không thay thế allowlist SKU.

### 5.3. Giới hạn theo thuộc tính

Ngoài machine name, policy có thể kiểm tra số vCPU tối đa hoặc tối thiểu, RAM tối đa/tối thiểu và tỷ lệ RAM/vCPU, CPU architecture, số GPU hoặc accelerator model, local NVMe hoặc ephemeral disk, network performance tier, confidential computing capability và license/software requirement.

Giới hạn theo thuộc tính hữu ích khi provider thêm SKU mới. Tuy nhiên, rule quá rộng có thể vô tình cho phép loại máy chưa được kiểm thử. Nên kết hợp allowlist family/SKU với giới hạn thuộc tính.

### 5.4. Giới hạn GPU và accelerator

GPU instance thường có đơn giá, quota, driver và image dependency riêng. Policy nên yêu cầu workload/project được gắn nhãn AI/HPC đã phê duyệt, GPU model nằm trong allowlist, region có capacity và driver support, image chứa driver/runtime đã được kiểm duyệt, budget/quota phù hợp và có owner chịu trách nhiệm.

Không cấp GPU chỉ dựa trên yêu cầu tự khai báo mà không có owner, workload profile hoặc cost center.

### 5.5. Hạn mức và quota khác policy

Quota giới hạn lượng tài nguyên có thể cấp trong một account/project/region. Policy quy định loại tài nguyên được phép. Một machine type có thể nằm trong allowlist nhưng không thể tạo do quota hết; ngược lại, quota còn nhưng policy vẫn từ chối SKU đó.

Cần theo dõi riêng:

- Allowed by policy.
- Available by quota.
- Available capacity in region/zone.
- Approved by budget.

## 6. Chính sách nguồn image được phép

Image chứa hệ điều hành, package, agent, runtime và cấu hình khởi đầu của máy. Nguồn image ảnh hưởng tới độ tin cậy, khả năng vá lỗi, khả năng truy vết và tính nhất quán.

Các nguồn có thể gồm golden image do platform team xây dựng, image do cloud provider phát hành, image marketplace từ publisher đã được phê duyệt, image custom từ pipeline nội bộ, container image từ private registry, hoặc image từ public registry/tài khoản/project bên ngoài.

Không phải mọi image public đều độc hại, nhưng không nên cho phép người dùng tùy ý chọn nguồn chưa được xác minh trong môi trường production.

### 6.1. Golden image

Golden image là image chuẩn đã được tổ chức kiểm duyệt. Nó thường bao gồm OS version và package baseline, security patch đã áp dụng, endpoint protection/monitoring agent, logging và configuration management agent, hardening settings, CA certificates và trust configuration, metadata để truy vết build và owner.

Golden image cần được rebuild định kỳ, kiểm thử và thay thế khi OS hết hỗ trợ hoặc xuất hiện lỗ hổng nghiêm trọng.

### 6.2. Allowlist theo publisher, project hoặc registry

Đối với VM image, policy có thể cho phép image do provider hoặc project nội bộ phát hành, hoặc chỉ cho phép image ID/version đã được duyệt.

Đối với container image, policy có thể giới hạn registry, repository, namespace và digest. Không nên chỉ tin vào tên tag như latest hoặc production vì tag có thể bị di chuyển sang nội dung khác.

### 6.3. Image ID và immutable digest

Image ID/version hoặc digest xác định nội dung image cụ thể. Một policy mạnh có thể yêu cầu image ID nằm trong danh sách đã phê duyệt, image owner/publisher nằm trong danh sách tin cậy, container image được tham chiếu bằng digest, chữ ký image hợp lệ và issuer được tin cậy, provenance chỉ ra pipeline/build identity đã tạo artifact.

Digest bảo đảm tham chiếu tới nội dung cụ thể, nhưng không chứng minh image an toàn. Vẫn cần scan, signature verification và review.

### 6.4. Image public và marketplace

Nếu cho phép marketplace image, cần phê duyệt publisher, license, support lifecycle và cơ chế cập nhật. Một image marketplace có thể chứa phần mềm tính phí theo giờ hoặc license riêng; policy nguồn image cần phối hợp với cost governance.

Public image có thể bị xóa, thay đổi hoặc ngừng cập nhật. Hãy mirror hoặc import image đã duyệt vào repository nội bộ nếu tổ chức cần kiểm soát retention và khả năng tái triển khai.

### 6.5. VM image và container image có control khác nhau

VM image thường được kiểm soát bằng image ID, owner/project, publisher, version hoặc gallery/catalog. Container image thường được kiểm soát bằng registry, repository, tag/digest, signature và admission policy.

Không dùng một quy tắc allowlist registry để thay thế kiểm soát VM image. Hai loại artifact có metadata và lifecycle khác nhau.

## 7. Policy enforcement theo nền tảng cloud

Các provider có dịch vụ policy riêng, nhưng mục tiêu chung là đánh giá request tạo hoặc cập nhật tài nguyên trước khi thao tác được chấp nhận.

| Nền tảng | Cơ chế thường dùng | Ví dụ phạm vi |
|---|---|---|
| AWS | Organizations Service Control Policies (SCP), IAM condition keys, AWS Config và Control Tower controls | Giới hạn region, quyền tạo EC2, image owner/ID theo điều kiện hỗ trợ |
| Microsoft Azure | Azure Policy, management groups, policy initiatives và exemptions | Allowed locations, VM SKU, image publisher/offer/SKU theo policy definition |
| Google Cloud | Organization Policy, IAM, custom constraints khi được hỗ trợ và Policy Intelligence | Resource locations, giới hạn thuộc tính compute qua constraint phù hợp |
| Kubernetes | Admission controller, ValidatingAdmissionPolicy, Gatekeeper hoặc Kyverno | Registry/repository, image digest/signature, workload policy và node placement |

Tên dịch vụ và constraint cụ thể phụ thuộc provider, resource type, API version và loại subscription/project. Trước khi triển khai, kiểm tra tài liệu chính thức hiện hành để xác nhận field được hỗ trợ, cách kế thừa và behavior của deny/audit/exemption.

### 7.1. AWS

AWS Organizations SCP có thể đặt giới hạn quyền tối đa cho member account. SCP không tự cấp quyền IAM; IAM identity policy vẫn phải cho phép thao tác. Region guardrail thường dựa trên request context như aws:RequestedRegion, nhưng cần thiết kế ngoại lệ cho dịch vụ global hoặc API control-plane có hành vi đặc biệt.

Đối với EC2 image, có thể dùng quyền IAM và điều kiện phù hợp để giới hạn image ID/owner trong những API/action hỗ trợ condition key tương ứng. Cần kiểm tra từng action và condition key trước khi giả định một điều kiện áp dụng cho mọi đường tạo instance, launch template hoặc autoscaling.

### 7.2. Azure

Azure Policy có thể gán ở management group, subscription hoặc resource group. Built-in policy có thể kiểm tra allowed locations hoặc allowed virtual machine SKUs; custom policy có thể kiểm tra thuộc tính image khi alias tương ứng được hỗ trợ.

Effect như Deny, Audit, Modify hoặc DeployIfNotExists có behavior khác nhau. Deny chặn request không tuân thủ; Audit ghi nhận vi phạm; Modify/DeployIfNotExists có thể thay đổi hoặc triển khai cấu hình bổ sung khi đủ quyền và đúng loại resource. Không dùng Audit như thể nó đang chặn tạo tài nguyên.

### 7.3. Google Cloud

Organization Policy cung cấp constraint ở cấp tổ chức, folder hoặc project. Có thể dùng constraint location phù hợp để giới hạn nơi tạo resource. Với machine type và image, cần xác định constraint managed hoặc custom constraint có hỗ trợ resource/API cụ thể; không giả định mọi trường của Compute Engine đều có một constraint built-in tương ứng.

Nếu policy không thể kiểm tra một thuộc tính trực tiếp, kết hợp IAM, custom validation trong pipeline, service perimeter hoặc kiểm tra inventory. Không coi một rule location là đủ để quản trị image hay machine SKU.

### 7.4. Kubernetes và node image

Kubernetes admission policy có thể chặn Pod dùng container image ngoài registry được phép hoặc không có digest. Tuy nhiên, admission policy cho Pod không kiểm soát toàn bộ image của VM node hoặc image do cloud autoscaling group sử dụng.

Node pool cần được quản trị ở tầng cloud/IaC và dùng node image đã được duyệt. Workload admission và node image governance là hai lớp khác nhau.

## 8. Policy-as-code và kiểm tra trước khi triển khai

Policy-as-code lưu quy tắc dưới dạng source có version, review và test. Cách này giúp nhóm platform thay đổi allowlist có kiểm soát và tái sử dụng rule giữa các môi trường.

### 8.1. Luồng policy-as-code

~~~mermaid
flowchart TD
    A["Policy source in Git"] --> B["Pull request review"]
    B --> C["Unit tests / policy tests"]
    C --> D["IaC plan validation"]
    D --> E["Deploy policy in audit mode"]
    E --> F["Review violations and impact"]
    F --> G["Enforce deny"]
    G --> H["Continuous compliance scan"]
    H --> I["Remediate or approved exception"]
~~~

Policy cần có test positive và negative:

- Region trong allowlist phải được chấp nhận.
- Region ngoài allowlist phải bị từ chối.
- Machine SKU được phê duyệt phải được chấp nhận.
- GPU SKU bị cấm trong development phải bị từ chối.
- Image từ registry tin cậy phải qua.
- Image từ registry không tin cậy hoặc tag mutable phải bị từ chối khi policy yêu cầu digest.

### 8.2. Kiểm tra trong pull request

IaC plan nên được kiểm tra trước khi apply. Policy test có thể đọc resource plan và xác minh region, machine type, image source cùng tag bắt buộc.

Ví dụ rule pseudocode:

~~~text
deny if vm.region not in approved_regions
deny if vm.machine_type not in approved_machine_types
deny if vm.image_id not in approved_vm_images
deny if container.image_registry not in approved_registries
deny if production and container.image_reference is not digest
~~~

Đây là logic mô tả, không phải cú pháp Rego, CEL hay Azure Policy. Khi dùng OPA/Rego, Sentinel, Terraform policy checks hoặc Azure Policy, hãy viết test theo đúng schema của công cụ.

### 8.3. Plan và runtime có thể khác nhau

IaC validation kiểm tra ý định trước triển khai. Tài nguyên vẫn có thể được tạo ngoài pipeline qua console, CLI hoặc API nếu control plane không enforce policy. Vì vậy, IaC check phải đi cùng organization-level guardrail và inventory scan.

## 9. Enforce ở thời điểm tạo và cập nhật

Preventive control chặn request trước khi tạo resource. Đây là lớp quan trọng nhất để ngăn cấu hình sai đi vào môi trường.

Các điểm kiểm soát:

- Cloud API authorization/policy evaluation.
- Launch template hoặc instance template validation.
- Managed node group/node pool configuration.
- IaC plan và deployment pipeline.
- Kubernetes admission request.
- Registry pull policy hoặc image verification.

### 9.1. Create và update

Policy cần đánh giá cả create lẫn update. Một VM hợp lệ hôm qua có thể bị sửa machine type hoặc thay image hôm nay. Một autoscaling template có thể được cập nhật để tạo instance mới với SKU hoặc image ngoài allowlist.

Kiểm tra create VM/instance, update machine size/type, thay image hoặc launch template, tạo node pool/autoscaling group, restore snapshot hoặc tạo image mới, clone/import image và thay container image trong workload spec.

### 9.2. Tài nguyên được tạo gián tiếp

Managed service có thể tạo VM hoặc node thay mặt người dùng. Nếu chỉ kiểm tra thao tác tạo VM trực tiếp, resource gián tiếp có thể bỏ qua policy.

Hãy xác định các service principal và API path có thể tạo compute, sau đó kiểm tra policy được áp dụng lên resource cuối cùng hay không. Ví dụ: managed Kubernetes node pool, managed batch, autoscaling, image builder và deployment service.

## 10. Admission control cho container image

Với Kubernetes, admission control là điểm kiểm tra request tạo hoặc cập nhật object trước khi API server lưu object. Có thể dùng nó để giới hạn registry và yêu cầu image reference bất biến.

Ví dụ ValidatingAdmissionPolicy minh họa cho registry allowlist:

~~~yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: approved-image-registries
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: "object.spec.containers.all(c, c.image.startsWith('registry.example.internal/'))"
      message: "Container images must come from the approved registry"
~~~

Ví dụ trên chỉ minh họa kiểm tra container list chính. Production policy cần kiểm tra cả initContainers và ephemeralContainers, xử lý registry hostname/port chính xác, tránh bypass bằng dạng tên tương đương và tạo ValidatingAdmissionPolicyBinding để policy thực sự được áp dụng. Cần xác minh phiên bản Kubernetes hỗ trợ API này.

### 10.1. Yêu cầu digest

Một image reference dùng tag có thể thay đổi nội dung:

~~~text
registry.example.internal/payments/api:stable
~~~

Reference bằng digest xác định nội dung cụ thể:

~~~text
registry.example.internal/payments/api@sha256:0123456789abcdef...
~~~

Digest ví dụ là chuỗi minh họa, không phải digest hợp lệ để triển khai. Policy production nên xác minh định dạng digest và, nếu cần, kiểm tra chữ ký/provenance bằng admission integration.

### 10.2. Kiểm tra init container và sidecar

Không chỉ kiểm tra containers. Pod có thể chứa initContainers, sidecar được inject bởi mutating webhook hoặc ephemeralContainers được thêm để debug. Policy cần có chiến lược cho từng loại:

- Init container phải dùng registry và image đã duyệt.
- Sidecar injection phải đến từ controller/webhook được quản trị.
- Ephemeral container có thể bị giới hạn hoặc yêu cầu quyền debug riêng.
- Image pull secret phải lấy từ secret manager hoặc cơ chế quản lý credential phù hợp.

### 10.3. Signature và provenance

Registry allowlist chỉ xác nhận vị trí lưu image, không chứng minh ai tạo image hoặc nội dung đã qua kiểm tra. Với workload production, có thể yêu cầu chữ ký hợp lệ từ identity CI được tin cậy, provenance liên kết image digest với source commit và build workflow, SBOM gắn với digest, vulnerability scan đạt policy threshold, image không bị thu hồi hoặc đánh dấu compromised.

Admission controller hoặc deployment pipeline phải xác minh các evidence này. Không chấp nhận một annotation tự khai rằng image đã được scan nếu không có hệ thống kiểm chứng.

## 11. Audit, enforce và remediation

Không nên bật deny diện rộng ngay khi vừa viết policy. Một rule có thể đúng về ý định nhưng sai field, thiếu API path hoặc ảnh hưởng tài nguyên hợp lệ đang chạy.

### 11.1. Audit mode trước khi enforce

Triển khai theo giai đoạn:

1. Thu thập inventory hiện tại.
2. Viết policy và test các trường hợp cho phép/từ chối.
3. Bật audit hoặc report-only nếu nền tảng hỗ trợ.
4. Đo số lượng resource sẽ bị ảnh hưởng.
5. Xác định owner và workload phụ thuộc.
6. Sửa tài nguyên hoặc cấp exception có thời hạn.
7. Bật deny cho phạm vi nhỏ.
8. Mở rộng dần sau khi theo dõi không có false positive nghiêm trọng.

Audit mode không chặn thao tác. Trong thời gian này, cần giới hạn người có quyền tạo resource và giám sát vi phạm để tránh policy chưa enforce bị xem nhầm là đã bảo vệ hệ thống.

### 11.2. Preventive, detective và corrective control

| Loại control | Mục tiêu | Ví dụ |
|---|---|---|
| Preventive | Chặn cấu hình sai trước khi tạo | SCP, Azure Policy Deny, admission policy |
| Detective | Phát hiện resource vi phạm | Cloud inventory, Config, Policy compliance scan |
| Corrective | Đưa resource về trạng thái tuân thủ | Resize, migrate region, rebuild image, quarantine |

Một hệ thống governance cần cả ba. Chỉ có preventive control sẽ bỏ sót tài nguyên cũ hoặc được tạo bởi service path chưa được kiểm soát; chỉ có detective control thì vi phạm vẫn có thể tồn tại lâu trước khi được xử lý.

### 11.3. Xử lý resource vi phạm

Khi phát hiện:

- Xác định resource ID, owner, environment và workload phụ thuộc.
- Phân loại mức độ rủi ro và dữ liệu liên quan.
- Chặn tạo mới hoặc thay đổi tiếp nếu cần.
- Lập kế hoạch migrate/resize/rebuild có kiểm thử.
- Kiểm tra backup, snapshot và rollback.
- Xác nhận resource sau remediation đáp ứng policy.
- Ghi lại thời điểm, người xử lý và bằng chứng.

Không tự động xóa VM hoặc disk đang chứa dữ liệu quan trọng chỉ vì policy mới phát hiện sai region hoặc machine type. Ưu tiên containment an toàn và remediation có owner.

## 12. Quản lý ngoại lệ có kiểm soát

Một số workload có nhu cầu hợp lệ ngoài allowlist, chẳng hạn GPU model mới để nghiên cứu, region DR khi diễn tập hoặc image vendor chưa được đưa vào golden image. Ngoại lệ cần có quy trình riêng, có giới hạn và có thời hạn.

### 12.1. Nội dung yêu cầu exception

Yêu cầu exception nên nêu workload, project/account/subscription và owner, region/machine SKU/image source cần ngoại lệ, lý do kỹ thuật/nghiệp vụ, dữ liệu và mức độ nhạy cảm, rủi ro và biện pháp bù trừ, thời gian bắt đầu và ngày hết hạn, người phê duyệt platform/security/cost, cùng kế hoạch quay lại baseline.

### 12.2. Exception có phạm vi hẹp

Không mở allowlist toàn tổ chức chỉ để đáp ứng một dự án. Hãy giới hạn ngoại lệ theo project, resource group, principal, tag, image digest hoặc thời gian nếu nền tảng hỗ trợ.

Ví dụ:

~~~yaml
exception:
  id: EXC-2026-041
  scope:
    project: hpc-research
    workload: climate-model
  allow:
    region:
      - approved-dr-region
    machineType:
      - gpu-research-approved
    imageDigest:
      - sha256:approved-digest-placeholder
  owner: research-platform
  approver: cloud-security
  expiresAt: 2026-12-31
  compensatingControls:
    - isolated-network
    - enhanced-monitoring
    - weekly-image-review
~~~

Đây là schema minh họa. Placeholder digest không phải giá trị triển khai. Exception phải được kiểm tra tự động khi hết hạn và không được mở rộng phạm vi ngoài yêu cầu.

### 12.3. Emergency break-glass

Trong sự cố, người có quyền break-glass có thể cần tạo compute ở region hoặc machine type ngoài baseline. Cơ chế này phải dùng identity riêng, MFA và quyền giới hạn; yêu cầu incident/ticket ID; có thời hạn ngắn và audit đầy đủ; gửi cảnh báo tới security/platform; tự hết hiệu lực hoặc được thu hồi sau sự cố; có post-incident review và đưa resource về baseline.

Break-glass không nên là một role dùng thường xuyên hoặc một policy exemption vĩnh viễn.

## 13. Quản lý vòng đời image

Image được phép hôm nay có thể không còn an toàn sau vài tháng. Chính sách nguồn image cần gắn với lifecycle từ build tới deprecation.

### 13.1. Quy trình golden image

~~~mermaid
flowchart TD
    A["Approved base image"] --> B["Patch and harden"]
    B --> C["Install required agents"]
    C --> D["Scan and test"]
    D --> E["Sign and publish"]
    E --> F["Add to approved catalog"]
    F --> G["Deploy to canary"]
    G --> H["Promote to production"]
    H --> I["Monitor CVE and support lifecycle"]
    I --> J["Rebuild or deprecate"]
~~~

### 13.2. Image freshness

Policy nên quy định tuổi tối đa hoặc chu kỳ cập nhật cho image theo mức độ rủi ro. Image cũ có thể chứa package hết hỗ trợ, kernel có lỗ hổng hoặc certificate đã hết hạn.

Các tín hiệu cần theo dõi: OS/vendor support end date, security patch age, critical/high CVE, agent version, image build timestamp, signature và provenance status, owner và workload đang sử dụng.

Không chỉ kiểm tra image source. Một image đến từ registry tin cậy vẫn có thể lỗi thời hoặc chứa lỗ hổng.

### 13.3. Deprecation và revocation

Khi image bị thu hồi:

1. Đánh dấu image/digest không còn được phép cho deployment mới.
2. Tìm tất cả VM, launch template, node pool và workload đang dùng.
3. Xác định mức độ khai thác và urgency.
4. Tạo image thay thế và test tương thích.
5. Rollout theo nhóm/canary.
6. Xác minh không còn workload sử dụng image cũ.
7. Thu hồi quyền pull hoặc xóa theo retention policy.

Với image bị nghi compromise, có thể cần quarantine registry repository hoặc chặn digest ngay, đồng thời lập kế hoạch phục hồi cho workload đang chạy.

### 13.4. Không thay đổi tag đang triển khai

Không di chuyển tag production sang image mới mà không có quy trình versioning. Deployment record cần giữ digest thực tế. Nếu tag được cập nhật, nhóm phải biết workload nào vẫn đang chạy digest cũ và workload nào đã chuyển sang digest mới.

## 14. Machine type governance và capacity planning

Allowlist machine type phải cân bằng bảo mật, chi phí và khả năng cấp phát. Một SKU được cho phép về governance nhưng không còn capacity ở region/zone có thể làm deployment thất bại.

### 14.1. Catalog machine type

Nên duy trì catalog có các trường:

| Trường | Ý nghĩa |
|---|---|
| Provider/SKU | Tên machine type chính xác |
| Family/profile | General, compute, memory, storage, GPU/HPC |
| vCPU/RAM | Năng lực CPU và bộ nhớ |
| Architecture | x86-64, Arm hoặc loại khác |
| Accelerator | GPU model/count nếu có |
| Network | Băng thông hoặc tier |
| Region availability | Region/zone hỗ trợ |
| Cost tier | Nhóm chi phí hoặc giá tham chiếu |
| Approved workload | Loại workload được dùng |
| Lifecycle | Current, deprecated hoặc restricted |

Catalog nên được đồng bộ với inventory/provider API hoặc review định kỳ để phát hiện SKU mới, SKU hết hỗ trợ và khác biệt availability giữa region.

### 14.2. Tránh wildcard quá rộng

Rule cho phép mọi machine type có prefix của một family có thể tự động mở quyền cho SKU mới khi provider phát hành. Nếu chưa kiểm thử, SKU mới có thể có giá cao, architecture khác hoặc đặc tính network khác.

Ưu tiên exact SKU allowlist cho production. Nếu cần wildcard, kết hợp giới hạn vCPU/RAM/accelerator/cost tier và có quy trình review SKU mới.

### 14.3. Machine type và quota

Sau khi policy chấp nhận SKU, hệ thống vẫn cần kiểm tra quota và capacity. Theo dõi vCPU quota theo region/family, GPU quota theo accelerator, capacity theo zone, reservation hoặc committed capacity, limit theo subscription/project và giới hạn license theo core/GPU.

Policy có thể cho phép một SKU nhưng không bảo đảm nhà cung cấp có sẵn capacity tại thời điểm tạo.

### 14.4. Resize và migration

Thay machine type có thể cần stop/deallocate, thay đổi disk/network hoặc restart. Không phải mọi instance đều resize được trực tiếp giữa các family hoặc architecture.

Trước khi remediation một VM ngoài allowlist, kiểm tra architecture và OS compatibility, driver/accelerator dependency, disk và network attachment, downtime và tác động HA, license và quota, cùng kế hoạch rollback.

## 15. Region policy và dữ liệu liên quan

Region restriction không chỉ là lựa chọn nơi chạy compute. Dữ liệu có thể được sao chép hoặc xử lý qua dịch vụ khác trong quá trình provisioning và vận hành.

### 15.1. Các đường dữ liệu cần xem xét

- Boot disk và data disk.
- Snapshot và backup.
- Custom VM image và image replication.
- Object storage chứa input/output.
- Log, telemetry và crash dump.
- Container registry và artifact cache.
- KMS/HSM key và secret store.
- Database replica và message queue.

Một VM chạy trong region được phép nhưng ghi log hoặc snapshot sang region không được phép vẫn có thể vi phạm yêu cầu residency.

### 15.2. Region pinning và disaster recovery

Region pinning giúp giữ workload trong phạm vi được phê duyệt nhưng có thể làm giảm khả năng failover. Cần phê duyệt sẵn region DR và xác định cách replicate dữ liệu.

Nếu region DR không được phép cho dữ liệu cụ thể, có thể cần backup đã mã hóa, tokenization, dữ liệu tổng hợp hoặc quy trình khôi phục chỉ sau khi có phê duyệt. Không tự động replicate dữ liệu nhạy cảm qua biên giới.

## 16. Inventory và continuous compliance

Policy chỉ có hiệu lực lâu dài khi tổ chức biết những tài nguyên nào đang tồn tại. Inventory cần thu thập region, zone, machine SKU, image ID/digest, owner, project, trạng thái, thời điểm tạo và nguồn triển khai.

### 16.1. Các trường inventory quan trọng

| Nhóm | Thuộc tính |
|---|---|
| Identity | Resource ID, account/subscription/project, owner, service principal |
| Location | Region, zone, network location |
| Machine | SKU/family, vCPU, RAM, architecture, GPU |
| Image | Image ID, owner/publisher, version, digest, build time |
| Governance | Policy version, compliance state, exception ID |
| Lifecycle | Created time, last update, deprecation status |
| Cost | Cost center, environment, allocated/billable hours |

### 16.2. Drift detection

Drift xảy ra khi resource thực tế khác policy hoặc cấu hình được khai báo trong IaC. Nguyên nhân có thể là thay đổi thủ công, deployment ngoài pipeline, policy update hoặc provider thay đổi metadata.

Continuous compliance nên quét định kỳ toàn bộ account/project/subscription, phát hiện resource ngoài region/SKU/image allowlist, so sánh actual resource với IaC state khi có thể, theo dõi launch template/autoscaling template/node pool, phát hiện image đã bị deprecate hoặc thu hồi và gửi finding tới owner/hệ thống ticket.

### 16.3. Tài nguyên không có owner

Resource không có owner hoặc cost center làm remediation chậm. Hãy yêu cầu tag bắt buộc ở thời điểm tạo và phát hiện resource thiếu tag qua inventory. Nếu không xác định được owner, chuyển finding tới platform operations theo quy trình ownership mặc định.

## 17. Logging, audit trail và bằng chứng

Khi policy từ chối một request, log cần đủ thông tin để người dùng biết cách sửa và security có thể điều tra.

Ghi nhận:

- Principal hoặc service identity thực hiện request.
- Resource type và resource ID nếu đã được cấp.
- Region, machine SKU và image reference được yêu cầu.
- Policy ID, version và rule đã match.
- Decision: allow, deny, audit hoặc exemption.
- Thời điểm, request/correlation ID và nguồn gọi API.
- Exception ID và người phê duyệt nếu áp dụng.

Không ghi secret, credential hoặc payload nhạy cảm vào policy log.

### 17.1. Lý do từ chối rõ ràng

~~~text
Request denied by compute-region-policy.
Requested region: region-x
Approved regions: region-a, region-b
Next step: select an approved region or submit a time-bounded exception.
Policy version: compute-baseline-12
~~~

Không tiết lộ thông tin nội bộ nhạy cảm trong thông báo gửi tới người dùng không có quyền, nhưng vẫn cung cấp mã policy và hướng dẫn đủ để xử lý.

### 17.2. Evidence cho audit

Giữ lại policy source và version đã deploy, pull request và reviewer, kết quả policy tests, deployment record và thời điểm hiệu lực, audit findings trước/sau enforcement, exception approvals và expiry, remediation evidence và inventory snapshot theo kỳ.

Evidence cần có retention phù hợp với yêu cầu nội bộ/pháp lý và quyền truy cập được kiểm soát.

## 18. Xử lý policy violation như một quy trình vận hành

Không phải mọi vi phạm đều có cùng mức độ. Một image bị thu hồi do compromise có urgency cao hơn một machine type vượt giới hạn cost tier nhưng không có dấu hiệu rủi ro bảo mật.

### 18.1. Phân loại severity

| Mức | Ví dụ | Hành động |
|---|---|---|
| Critical | Image bị xác nhận compromise, dữ liệu ở region cấm | Contain ngay, chặn deployment mới, incident response |
| High | Image có lỗ hổng nghiêm trọng, machine SKU ngoài policy trong production | Tạo remediation khẩn, owner và deadline ngắn |
| Medium | SKU không còn được khuyến nghị, image quá tuổi | Lập kế hoạch migrate/rebuild theo thời hạn |
| Low | Thiếu tag, metadata hoặc owner | Giao ticket và hoàn thiện inventory |

Severity cần dựa trên dữ liệu thực tế, loại workload và khả năng khai thác; không tự động suy luận từ một field duy nhất.

### 18.2. Quy trình remediation

1. Tạo finding có resource ID và policy ID.
2. Xác định owner và dependency.
3. Đánh giá rủi ro bảo mật, residency và downtime.
4. Chọn hành động: resize, migrate region, rebuild image hoặc exception.
5. Kiểm thử ở môi trường phù hợp.
6. Thực hiện thay đổi theo change management.
7. Quét lại để xác nhận compliance.
8. Đóng finding với evidence.

### 18.3. Không xóa tài nguyên tự động khi chưa hiểu tác động

Một VM ngoài allowlist có thể đang chạy database hoặc dịch vụ quan trọng. Xóa ngay có thể gây mất dữ liệu và outage. Tự động remediation chỉ nên áp dụng cho hành động có thể đảo ngược và đã được thiết kế/test, ví dụ gắn tag, chặn deployment mới hoặc cô lập image bị thu hồi theo quy trình incident.

## 19. Ví dụ thực tế: chuẩn hóa compute cho tổ chức nhiều nhóm

Một doanh nghiệp có ba nhóm workload: web production, development và HPC research. Các nhóm trước đây tự chọn region, VM size và image. Hóa đơn tăng, một số VM chạy ở region chưa được duyệt và image không đồng nhất.

### 19.1. Thiết kế baseline

- Region production giới hạn theo residency và DR plan.
- Development chỉ dùng region sandbox.
- Machine family production cho phép general-purpose, compute-optimized và memory-optimized với SKU cụ thể.
- GPU/HPC SKU chỉ được tạo trong project research có budget và owner.
- VM chỉ dùng golden image từ project image factory.
- Container workload chỉ pull từ private registry và dùng digest đã được xác minh.

### 19.2. Triển khai theo giai đoạn

1. Inventory tất cả VM, node pool, image và launch template.
2. Tạo catalog region, machine SKU và image source được duyệt.
3. Viết policy-as-code và test allow/deny.
4. Chạy audit mode trong hai tuần để tìm resource hợp lệ nhưng chưa được catalog.
5. Làm việc với owner để migrate image cũ và đổi machine SKU.
6. Bật deny cho deployment mới ở development.
7. Bật deny cho production sau khi hoàn tất remediation.
8. Bật admission control cho container image.
9. Thiết lập exception có expiry cho HPC/DR.
10. Theo dõi compliance và chi phí hàng tuần.

### 19.3. Kết quả mong đợi

- Workload mới chỉ được tạo ở region được phê duyệt.
- Machine type được giới hạn theo profile và budget.
- VM image có nguồn gốc và version rõ ràng.
- Container image có registry, digest và evidence.
- Ngoại lệ có owner, approver và thời hạn.
- Resource cũ được phát hiện và xử lý có kiểm soát.

Kết quả thực tế cần được đo bằng số vi phạm, tỷ lệ deployment bị từ chối đúng, số false positive, thời gian remediation, tỷ lệ image đạt baseline và chi phí theo nhóm.

## 20. Các lỗi thiết kế policy thường gặp

- **Allowlist theo tên hiển thị:** tên có thể khác giữa provider hoặc thay đổi; dùng mã region/SKU/image ID chính xác.
- **Chỉ giới hạn region của VM:** bỏ sót disk, snapshot, backup, log, registry và managed resource.
- **Chỉ giới hạn machine family:** vô tình cho phép size rất lớn hoặc SKU mới chưa kiểm thử.
- **Nhầm quota với allowlist:** quota còn không có nghĩa SKU được phép.
- **Chỉ kiểm tra IaC:** console, CLI hoặc service principal có thể tạo resource ngoài pipeline.
- **Chỉ kiểm tra Pod image:** bỏ sót VM node image, init container, sidecar hoặc ephemeral container.
- **Chỉ allow registry:** image có thể chưa ký, chưa scan hoặc bị compromise.
- **Tin tag mutable:** tag có thể trỏ sang nội dung khác; lưu digest trong deployment record.
- **Bật deny ngay:** có thể làm hỏng workload hợp lệ đang chạy hoặc deployment phụ thuộc.
- **Không có exception expiry:** ngoại lệ tạm thời biến thành quyền vĩnh viễn.
- **Không kiểm tra policy inheritance:** child scope có thể bị override hoặc deny từ parent.
- **Không quản lý image lifecycle:** image cũ vẫn được tạo mới dù nguồn vẫn nằm trong allowlist.
- **Tự động xóa resource vi phạm:** có thể gây outage hoặc mất dữ liệu.
- **Không lưu policy version:** khó giải thích tại sao request trước được phép còn request sau bị từ chối.

## 21. Checklist triển khai region, machine type và image policy

Trước khi bật enforcement, xác nhận:

- [ ] Có owner và mục tiêu rõ ràng cho từng policy.
- [ ] Region allowlist dựa trên residency, latency, DR, service availability và cost.
- [ ] Disk, snapshot, backup, log và resource tạo gián tiếp được xem xét theo region.
- [ ] Machine allowlist có family và exact SKU phù hợp môi trường.
- [ ] vCPU, RAM, architecture, GPU, network và license được kiểm tra khi cần.
- [ ] Quota/capacity được theo dõi tách khỏi policy decision.
- [ ] VM image source có publisher/owner/image ID được phê duyệt.
- [ ] Container image chỉ đến registry/repository được tin cậy.
- [ ] Production image có digest, signature/provenance và scan evidence theo policy.
- [ ] Golden image có patch, owner, build timestamp và deprecation lifecycle.
- [ ] Policy được test với trường hợp allow, deny, inheritance và exception.
- [ ] IaC validation đi cùng control-plane enforcement và inventory scan.
- [ ] Audit mode đã được chạy và false positive được xử lý.
- [ ] Exception có scope, approver, compensating control và expiry.
- [ ] Có logging, finding owner, remediation SLA và evidence.
- [ ] Có kế hoạch rollback policy nếu enforcement gây ảnh hưởng ngoài dự kiến.

## 22. Quy trình quản trị liên tục

1. **Discover:** thu thập inventory compute, machine SKU và image.
2. **Classify:** gắn workload với data class, environment, owner và cost center.
3. **Define:** quản lý allowlist region, machine type và image source trong Git.
4. **Test:** chạy unit test policy và IaC validation.
5. **Observe:** bật audit mode và đánh giá tác động.
6. **Enforce:** bật deny theo scope và theo giai đoạn.
7. **Monitor:** theo dõi violation, exception, image freshness và drift.
8. **Remediate:** sửa resource với owner và kế hoạch an toàn.
9. **Review:** cập nhật catalog khi provider thêm/bỏ region, SKU hoặc image.
10. **Retire:** thu hồi policy exception, image và machine type không còn được hỗ trợ.

## 23. Ghi nhớ

Chính sách giới hạn region, machine type và nguồn image giúp tổ chức kiểm soát nơi compute chạy, loại phần cứng được cấp và phần mềm nền được tin cậy. Hãy dùng allowlist rõ ràng, deny-by-default cho phạm vi rủi ro cao, áp dụng baseline ở cấp tổ chức và profile chặt hơn cho từng nhóm workload.

Region policy phải tính cả dữ liệu, backup và resource được tạo gián tiếp. Machine type policy cần giới hạn family/SKU cùng thuộc tính CPU, RAM, architecture và accelerator; quota và capacity là điều kiện riêng. Image policy phải phân biệt VM image với container image, kiểm soát publisher/registry, version/digest, signature, provenance, scan và lifecycle.

Triển khai policy-as-code có test, audit mode, enforcement từng bước, exception có thời hạn và continuous compliance. Khi phát hiện vi phạm, đánh giá owner và tác động trước khi remediation. Một governance program tốt không chỉ chặn request sai mà còn giúp workload được triển khai nhất quán, có thể truy vết, đáp ứng residency và kiểm soát chi phí.
