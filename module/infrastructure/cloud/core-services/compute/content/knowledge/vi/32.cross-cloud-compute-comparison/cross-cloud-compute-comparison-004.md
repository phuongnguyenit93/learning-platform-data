# Đối chiếu mô hình chạy container và trách nhiệm quản lý máy chủ

Container giúp đóng gói ứng dụng và dependency thành một image có thể chạy nhất quán trên nhiều môi trường. Tuy nhiên, việc đóng gói thành container không tự động loại bỏ trách nhiệm quản lý máy chủ. Nếu container chạy trực tiếp trên VM do đội vận hành tự quản lý, đội đó vẫn phải cập nhật hệ điều hành, runtime, network và capacity. Nếu dùng managed Kubernetes hoặc serverless container, nhà cung cấp quản lý thêm control plane, node hoặc hạ tầng thực thi; khách hàng vẫn chịu trách nhiệm về image, ứng dụng, dữ liệu, quyền truy cập và cấu hình workload.

**Mô hình chạy container** mô tả cách container được triển khai, lập lịch, kết nối mạng, mở rộng và thay thế. **Trách nhiệm quản lý máy chủ** xác định ai vận hành phần cứng, hypervisor, host OS, worker node, container runtime, control plane và các lớp ứng dụng.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, cần phân biệt container tự quản lý trên VM, managed container orchestration, managed Kubernetes với node do khách hàng quản lý, Kubernetes với compute được nhà cung cấp quản lý và serverless container. Mức độ managed càng cao thường giảm công việc quản lý node và cluster, nhưng không chuyển toàn bộ trách nhiệm bảo mật, dữ liệu, availability và vận hành ứng dụng sang nhà cung cấp.

## 1. Container không đồng nghĩa với managed compute

Container là cách đóng gói và cô lập tiến trình ở mức hệ điều hành. Một image có thể chạy trên:

- VM do đội ngũ tự tạo và quản lý.
- VM nằm trong managed Kubernetes cluster.
- Dịch vụ điều phối container do cloud provider quản lý.
- Nền tảng serverless nhận image và tự cấp phát compute.

Do đó, câu hỏi quan trọng không chỉ là “ứng dụng chạy bằng container hay không”, mà là “ai chịu trách nhiệm cho từng lớp từ máy chủ đến ứng dụng?”.

### 1.1. Các lớp trong một nền tảng container

| Lớp | Thành phần | Ví dụ trách nhiệm |
| --- | --- | --- |
| Hạ tầng vật lý | Datacenter, server, network fabric, storage | Cung cấp phần cứng và nguồn điện |
| Virtualization | Hypervisor hoặc isolation boundary | Tạo và cô lập compute |
| Host/guest OS | Kernel, package, security patch | Cập nhật hệ điều hành máy chạy container |
| Container runtime | Containerd, CRI-O hoặc runtime tương đương | Pull image, tạo container, quản lý lifecycle |
| Orchestration/control plane | Scheduler, API server, controller, service scheduler | Lập lịch, duy trì desired state, quản lý service |
| Worker/node | CPU, RAM, disk, network và agent | Cung cấp capacity thực thi |
| Container image | Base image, runtime, dependency | Build, scan, version và phát hành |
| Application | Code, API, configuration, health endpoint | Xử lý nghiệp vụ và request |
| Data/dependency | Database, cache, queue, object storage | Lưu dữ liệu, backup và consistency |
| Operations | Monitoring, alert, incident, DR, cost | Đảm bảo SLO và vận hành liên tục |

Provider có thể quản lý một số lớp nhưng không mặc nhiên quản lý mọi lớp còn lại. Phạm vi chính xác phụ thuộc dịch vụ, chế độ triển khai, hợp đồng và cấu hình được chọn.

### 1.2. Shared responsibility

Shared responsibility là mô hình phân chia trách nhiệm giữa cloud provider và khách hàng. Provider chịu trách nhiệm bảo vệ và vận hành hạ tầng thuộc dịch vụ của họ; khách hàng chịu trách nhiệm cấu hình và sử dụng dịch vụ an toàn.

Ví dụ, provider có thể vá control plane Kubernetes, nhưng khách hàng vẫn phải:

- Chọn image an toàn và cập nhật dependency.
- Cấu hình RBAC và workload identity.
- Giới hạn network access.
- Bảo vệ secret và dữ liệu.
- Cấu hình replica, autoscaling, readiness và disruption policy.
- Theo dõi lỗi ứng dụng và xử lý incident.

Không nên hiểu từ “managed” là provider sẽ tự thiết kế kiến trúc, khôi phục dữ liệu hoặc bảo đảm mọi workload đáp ứng SLO của khách hàng.

## 2. Các mô hình chạy container phổ biến

Có thể chia mô hình theo mức độ trừu tượng và phần máy chủ khách hàng phải quản lý.

### 2.1. Container tự quản lý trên VM

Đội ngũ tạo VM, cài container runtime, cấu hình network, storage và triển khai container bằng Docker, Podman hoặc công cụ tương đương. Việc lập lịch và thay thế container có thể do script, systemd hoặc nền tảng tự xây dựng.

Đặc điểm:

- Kiểm soát cao đối với OS, kernel, runtime và network.
- Có thể tận dụng kiến thức vận hành VM sẵn có.
- Đội ngũ phải vá guest OS và container runtime.
- Phải tự xây dựng hoặc vận hành cơ chế deployment, restart, health check, scaling và service discovery.
- Mỗi VM có thể trở thành điểm lỗi hoặc bottleneck nếu không có fleet management.

Mô hình phù hợp với workload nhỏ, phần mềm đặc thù hoặc đội ngũ cần quyền kiểm soát host. Khi số service và VM tăng, chi phí vận hành có thể tăng nhanh.

### 2.2. Managed container orchestration trên VM

Dịch vụ điều phối quản lý desired state, task/service placement, health và thay thế container. Compute có thể chạy trên VM do khách hàng quản lý hoặc trên capacity do provider cấp phát.

Ví dụ:

- Amazon ECS với EC2 capacity provider: AWS quản lý control plane ECS; khách hàng vẫn quản lý EC2 capacity và node OS theo cấu hình.
- Amazon ECS với AWS Fargate: provider quản lý hạ tầng máy chủ cho task; khách hàng khai báo task, image, IAM, network và tài nguyên.
- Các nền tảng managed container service tương tự có thể cung cấp service scheduler, rollout và tích hợp load balancer.

Orchestration giảm công việc điều phối từng container nhưng trách nhiệm node có thể vẫn thuộc khách hàng nếu chọn mô hình VM-backed.

### 2.3. Managed Kubernetes với node do khách hàng quản lý

Provider vận hành control plane Kubernetes như API server, scheduler và controller manager. Khách hàng tạo hoặc cấu hình worker node/node pool, chọn instance type, quản lý workload và nhiều phần vận hành cluster.

Ví dụ thường gặp:

- Amazon EKS với managed node group hoặc self-managed node.
- Azure Kubernetes Service (AKS) với node pool.
- Google Kubernetes Engine (GKE) Standard với node pool.

“Managed control plane” không đồng nghĩa toàn bộ node được provider vận hành. Tùy sản phẩm, provider có thể cung cấp node image, node auto-upgrade hoặc công cụ tự động hóa, nhưng khách hàng vẫn phải chọn policy, kiểm tra rollout và xử lý tương thích workload.

### 2.4. Managed Kubernetes với compute được quản lý nhiều hơn

Một số chế độ giảm trách nhiệm quản lý worker node:

- GKE Autopilot quản lý nhiều phần cấu hình và vận hành node, đồng thời áp dụng các giới hạn và policy cho workload.
- Amazon EKS Fargate chạy pod trên compute do AWS quản lý, trong phạm vi profile và loại workload được hỗ trợ.
- Một số dịch vụ managed Kubernetes có chế độ tự động quản lý node provisioning, upgrade hoặc scaling.

Khách hàng vẫn quản lý Kubernetes workload, image, resource request, identity, network policy, data và application behavior. Khả năng cấu hình host hoặc daemon đặc quyền có thể bị giới hạn hơn.

### 2.5. Serverless container/application platform

Khách hàng cung cấp image hoặc source artifact, cấu hình CPU/RAM, concurrency, network và scale. Provider quản lý phần lớn hạ tầng máy chủ, runtime platform và capacity provisioning.

Ví dụ:

- Google Cloud Run.
- Azure Container Apps.
- AWS App Runner.
- AWS ECS on Fargate cho task/service container không cần quản lý EC2 node.

Một số nền tảng hỗ trợ scale-to-zero, request-based scaling hoặc event-driven scaling. Đổi lại, khách hàng cần xem xét cold start, execution/request timeout, concurrency, networking, persistent storage và giới hạn runtime.

## 3. So sánh nhanh các mô hình

| Mô hình | Ai quản lý máy chủ/OS? | Ai quản lý orchestration? | Mức kiểm soát host | Công việc vận hành khách hàng |
| --- | --- | --- | --- | --- |
| Container tự quản lý trên VM | Khách hàng quản lý guest OS và runtime | Khách hàng tự vận hành hoặc tự xây | Cao | VM, patch, runtime, deploy, health, scale, network |
| ECS trên EC2 hoặc mô hình tương đương | Khách hàng quản lý node/VM; provider quản lý service control plane | Provider quản lý scheduler/service | Trung bình đến cao | EC2 capacity, node patch, task, image, IAM, network |
| Managed Kubernetes Standard | Provider quản lý control plane; node responsibility phụ thuộc cấu hình | Provider quản lý control plane; khách hàng quản lý workload và nhiều policy | Cao ở workload/node config | Node pool, upgrade policy, cluster add-on, workload, security |
| Managed Kubernetes với serverless/Autopilot compute | Provider quản lý nhiều phần node/capacity | Provider quản lý control plane; khách hàng khai báo workload | Thấp hơn | Workload, resource request, policy, data, IAM, network |
| Serverless container platform | Provider quản lý host và capacity | Provider quản lý runtime/service orchestration | Thấp | Image, app, config, identity, data, SLO và service limits |

Mức độ managed không phải thang đo tuyệt đối. Một dịch vụ có thể quản lý control plane nhưng để khách hàng chịu trách nhiệm node; một dịch vụ khác quản lý node nhưng vẫn yêu cầu khách hàng cập nhật image và dependency. Hãy đọc responsibility matrix của đúng mode.

## 4. Ma trận trách nhiệm theo từng lớp

Bảng dưới đây mô tả xu hướng tổng quát. “Provider” nghĩa là nhà cung cấp chịu trách nhiệm vận hành lớp hạ tầng dịch vụ; “Khách hàng” nghĩa là khách hàng phải cấu hình, giám sát hoặc cập nhật phần đó. Một số lớp là trách nhiệm chia sẻ.

| Lớp | VM + container tự quản lý | Managed Kubernetes với node pool | Serverless container |
| --- | --- | --- | --- |
| Datacenter và phần cứng | Provider | Provider | Provider |
| Hypervisor/host virtualization | Provider | Provider | Provider |
| Guest/worker OS | Khách hàng | Chia sẻ theo node mode và upgrade policy | Provider |
| Container runtime trên node | Khách hàng | Provider hoặc chia sẻ theo dịch vụ/node mode | Provider |
| Kubernetes/control plane | Khách hàng nếu tự cài | Provider | Provider không lộ Kubernetes cho người dùng |
| Worker capacity | Khách hàng tạo và scale VM | Chia sẻ: khách hàng cấu hình node pool, provider có thể hỗ trợ quản lý | Provider cấp phát theo service |
| Container image | Khách hàng | Khách hàng | Khách hàng |
| Application code/runtime dependency | Khách hàng | Khách hàng | Khách hàng |
| Application configuration | Khách hàng | Khách hàng | Khách hàng |
| IAM/workload identity | Chia sẻ | Chia sẻ | Chia sẻ |
| Network và firewall | Chia sẻ | Chia sẻ | Chia sẻ |
| Data và database | Khách hàng hoặc dịch vụ dữ liệu riêng | Khách hàng hoặc dịch vụ dữ liệu riêng | Khách hàng hoặc dịch vụ dữ liệu riêng |
| Backup/restore dữ liệu | Khách hàng cấu hình | Khách hàng cấu hình | Khách hàng cấu hình |
| Observability ứng dụng | Khách hàng | Khách hàng | Khách hàng |
| Availability của workload | Khách hàng thiết kế | Khách hàng thiết kế | Khách hàng thiết kế trong giới hạn platform |
| Patch dependency trong image | Khách hàng | Khách hàng | Khách hàng |
| Patch node/control plane | Khách hàng | Chia sẻ theo dịch vụ | Provider cho host/runtime nền |

Provider vận hành một lớp không có nghĩa khách hàng có thể bỏ qua lớp đó. Ví dụ, provider có thể thay node bị lỗi nhưng ứng dụng vẫn cần readiness probe, graceful shutdown, replica đủ số lượng và dữ liệu bên ngoài container.

## 5. Đối chiếu theo nhà cung cấp cloud

### 5.1. AWS

| Mô hình | Provider quản lý | Khách hàng quản lý |
| --- | --- | --- |
| EC2 + Docker/Podman | Datacenter, server và hypervisor | Guest OS, runtime, deploy, scaling, health, network và dữ liệu |
| ECS trên EC2 | ECS control plane và scheduler service | EC2 instances/capacity, node OS, task definition, image, IAM, network |
| ECS trên Fargate | Hạ tầng máy chủ và runtime capacity cho task | Task definition, image, CPU/RAM, IAM, network, scaling và ứng dụng |
| EKS trên EC2 | Kubernetes control plane | Node pool/EC2, node upgrade policy, add-on, workload, policy và dữ liệu |
| EKS Fargate | Control plane và compute host cho pod được hỗ trợ | Pod spec, image, profile, IAM, network, workload và dữ liệu |

ECS là dịch vụ orchestration container của AWS, không phải Kubernetes. EKS cung cấp Kubernetes control plane. Fargate là compute option giúp chạy task/pod mà không cần khách hàng quản lý EC2 host cho workload đủ điều kiện.

Với EKS, managed node group hỗ trợ quản lý vòng đời node nhưng khách hàng vẫn cần chọn cấu hình, lịch nâng cấp, capacity và kiểm tra tương thích. Fargate có giới hạn so với node EC2, chẳng hạn khả năng tùy chỉnh host và loại workload được hỗ trợ.

### 5.2. Microsoft Azure

| Mô hình | Provider quản lý | Khách hàng quản lý |
| --- | --- | --- |
| VM + container runtime | Datacenter và hypervisor | Guest OS, runtime, orchestration, scaling, image và app |
| AKS | Kubernetes control plane và các chức năng managed được chọn | Node pool policy, workload, image, identity, network, data và upgrade configuration |
| AKS Automatic hoặc chế độ tự động hóa tương ứng | Nhiều phần cluster/node lifecycle hơn tùy mode | Workload, image, app security, data, SLO và policy còn lại |
| Azure Container Apps | Hạ tầng cluster/container runtime và scale nền | Container image, app config, identity, ingress, scaling rules và data |

AKS có thể tự động hóa node image upgrade và cluster upgrade theo policy, nhưng khách hàng vẫn cần kiểm tra disruption, PDB, compatibility và workload readiness. Azure Container Apps trừu tượng hóa cluster Kubernetes bên dưới; khách hàng tập trung nhiều hơn vào container app, revision, ingress và scaling.

### 5.3. Google Cloud

| Mô hình | Provider quản lý | Khách hàng quản lý |
| --- | --- | --- |
| Compute Engine VM + container runtime | Datacenter và hypervisor | Guest OS, runtime, orchestration, image, app và network |
| GKE Standard | Kubernetes control plane và managed service | Node pool, workload, image, policy, data và nhiều cấu hình cluster |
| GKE Autopilot | Control plane và nhiều phần node provisioning/management | Workload, image, resource requests, IAM, network policy và dữ liệu |
| Cloud Run | Host, runtime platform và capacity provisioning | Image, app, config, identity, ingress, concurrency, min/max instances và data |

GKE Standard cung cấp quyền kiểm soát cluster và node cao hơn. GKE Autopilot giảm công việc vận hành node nhưng áp dụng các giới hạn/policy về workload và tài nguyên. Cloud Run tập trung vào triển khai container theo service/job với mức trừu tượng cao hơn Kubernetes.

### 5.4. Cách đọc bảng đối chiếu

Không nên chỉ so sánh tên sản phẩm. Cần so sánh đúng mode:

- Kubernetes Standard với node tự quản lý không tương đương Autopilot.
- ECS trên EC2 không tương đương ECS trên Fargate.
- AKS node pool không tương đương Azure Container Apps.
- GKE Standard không tương đương Cloud Run.

Mỗi mode có phạm vi patching, scaling, network, storage, observability và quota khác nhau.

## 6. Ai chịu trách nhiệm patching và nâng cấp?

Patching là điểm khác biệt lớn giữa mô hình VM-backed và serverless container.

### 6.1. VM + container tự quản lý

Khách hàng chịu trách nhiệm:

- Vá guest OS và kernel.
- Cập nhật container runtime.
- Cập nhật agent bảo mật và monitoring.
- Thay base image và dependency trong container image.
- Kiểm thử tương thích trước khi phát hành.
- Lập lịch reboot hoặc thay VM.
- Giám sát VM chưa được vá.

Một image ứng dụng mới không tự vá host OS. Ngược lại, vá host OS không tự cập nhật dependency được đóng gói bên trong image.

### 6.2. Managed Kubernetes

Provider thường quản lý control plane theo dịch vụ. Trách nhiệm worker node phụ thuộc node mode:

- Self-managed node: khách hàng chịu trách nhiệm phần lớn vòng đời node.
- Managed node group: provider cung cấp cơ chế tạo/nâng cấp node, khách hàng cấu hình và theo dõi.
- Serverless/Autopilot compute: provider quản lý nhiều phần host/node, khách hàng quản lý workload và image.

Khách hàng vẫn phải:

- Nâng phiên bản API và add-on theo compatibility matrix.
- Cập nhật image của ứng dụng.
- Kiểm tra deprecated API.
- Kiểm thử PDB, topology spread và rolling update.
- Xác minh workload không phụ thuộc vào host cụ thể.

### 6.3. Serverless container

Provider quản lý host OS và phần lớn runtime platform. Khách hàng vẫn phải cập nhật:

- Base image.
- Runtime và thư viện ứng dụng.
- Dependency có lỗ hổng.
- Certificate và secret theo vòng đời.
- Code, cấu hình và policy.

Không thể bỏ patching chỉ vì không nhìn thấy node. Image cũ vẫn có thể chứa thư viện dễ bị khai thác.

## 7. Ai chịu trách nhiệm scaling và capacity?

### 7.1. Container tự quản lý trên VM

Khách hàng phải phối hợp:

- Scale số VM.
- Scale số container trên mỗi VM.
- Load balancing và service discovery.
- Capacity planning CPU/RAM/disk/network.
- Quota và placement theo zone.
- Drain container trước khi terminate VM.

Nếu VM không đủ capacity, container không thể được tạo chỉ bằng cách tăng replica count.

### 7.2. Managed Kubernetes

HPA thay đổi số pod; node autoscaler hoặc node provisioning controller bổ sung node khi cần. Khách hàng phải cấu hình:

- CPU/memory requests và limits.
- Min/max replicas.
- Node pool min/max và instance type.
- Quota, subnet IP và zone capacity.
- Pod topology, affinity và disruption policy.
- Metric scale phù hợp.

HPA không tạo node trực tiếp và không đảm bảo cloud provider còn capacity. Nếu node pool đạt max hoặc quota cạn, pod có thể Pending.

### 7.3. Serverless container

Provider thường tự cấp phát compute theo request, event hoặc concurrency trong giới hạn service. Khách hàng vẫn đặt:

- Min/max instances hoặc task count.
- Concurrency per instance.
- CPU/RAM.
- Request timeout hoặc execution limit.
- Queue/event trigger và scaling rule.
- Quota và maximum scale.

Scale tự động không đồng nghĩa capacity vô hạn. Cold start, concurrency limit, regional quota hoặc dependency bottleneck vẫn có thể làm request chậm hoặc thất bại.

## 8. Network và service discovery

Mô hình càng managed, chi tiết node networking có thể càng ít lộ ra, nhưng khách hàng vẫn phải cấu hình đường đi của traffic.

| Thành phần | VM/container tự quản lý | Managed Kubernetes | Serverless container |
| --- | --- | --- | --- |
| Public entry point | Khách hàng tạo LB/reverse proxy | Ingress/Gateway/LB theo cấu hình | Service URL hoặc managed ingress |
| Service discovery | DNS/registry tự quản lý | Kubernetes Service/DNS | Service name hoặc platform endpoint |
| Network isolation | VPC, subnet, firewall, host rules | VPC, security group, CNI, NetworkPolicy | VPC connector/private networking theo dịch vụ |
| Pod/container IP | Khách hàng quản lý network plugin hoặc host port | Platform/CNI quản lý | Thường được trừu tượng hóa |
| Egress control | Firewall/NAT/route | VPC, network policy và egress gateway | Egress setting, VPC integration và policy |
| TLS | Khách hàng cấu hình proxy/certificate | Ingress/Gateway/service mesh | Managed certificate hoặc gateway tùy dịch vụ |

Không nên gắn public IP trực tiếp cho từng container nếu không cần. Dùng gateway hoặc load balancer làm điểm vào, áp dụng TLS, authentication, rate limit và network segmentation.

## 9. Storage và dữ liệu

Container thường có writable layer gắn với vòng đời container. Khi container bị xóa, dữ liệu ở layer đó có thể mất. Điều này đặc biệt quan trọng khi chuyển từ VM truyền thống sang managed container.

### 9.1. Ephemeral storage

Phù hợp cho:

- File tạm.
- Cache có thể tái tạo.
- Scratch space của job.
- Nội dung trung gian có thể tạo lại.

Không dùng làm nơi lưu dữ liệu nghiệp vụ duy nhất hoặc session cần tồn tại qua restart.

### 9.2. Persistent storage

Có thể dùng:

- Managed database.
- Object storage.
- Shared file storage.
- Persistent volume/block storage.

Trong Kubernetes, PersistentVolume và StorageClass cung cấp abstraction cho volume. Với serverless container, khả năng mount volume và semantics storage phụ thuộc dịch vụ; object storage hoặc managed database thường dễ tách khỏi vòng đời instance hơn.

### 9.3. Backup và recovery

Provider có thể bảo vệ hạ tầng storage nhưng khách hàng vẫn phải xác định:

- Dữ liệu nào cần backup.
- Retention và encryption.
- RPO/RTO.
- Point-in-time recovery.
- Kiểm thử restore.
- Quyền truy cập backup và KMS key.

Không coi việc provider duy trì service availability là thay thế backup chống xóa nhầm, corruption hoặc thao tác sai.

## 10. Bảo mật và identity

### 10.1. Host security

Với VM-backed container, khách hàng có nhiều trách nhiệm hơn về guest OS, SSH access, host firewall, runtime socket, kernel patch và agent bảo mật.

Với serverless container, provider quản lý host và runtime nền nhưng khách hàng vẫn phải bảo vệ image, application process, identity, secret và network.

### 10.2. Workload identity

Không nên nhúng cloud access key dài hạn vào image hoặc environment variable cố định. Dùng cơ chế workload identity, task role, managed identity hoặc service account tùy nền tảng.

Mỗi workload nên có quyền tối thiểu:

- Chỉ đọc đúng secret cần dùng.
- Chỉ truy cập database/schema hoặc bucket cần thiết.
- Chỉ publish/consume queue được chỉ định.
- Tách danh tính production khỏi môi trường test.
- Có audit và rotation phù hợp.

### 10.3. Container image security

Khách hàng chịu trách nhiệm:

- Dùng base image được duy trì.
- Scan image và dependency.
- Pin version/digest.
- Chạy non-root nếu có thể.
- Drop capabilities và tránh privileged mode.
- Không mount host socket hoặc hostPath không cần thiết.
- Ký image hoặc xác minh provenance theo policy tổ chức.

Managed platform không tự sửa package lỗi thời bên trong image ứng dụng.

### 10.4. Cluster và application policy

Với Kubernetes, khách hàng còn phải cấu hình RBAC, admission policy, NetworkPolicy, Pod Security và secret access. Với serverless container, các policy có thể nằm ở service IAM, VPC, ingress và execution configuration.

Dù mô hình nào, authorization nghiệp vụ vẫn phải được kiểm tra trong ứng dụng hoặc gateway tin cậy; private network không thay thế authentication.

## 11. Availability và trách nhiệm phục hồi

Managed service có thể tăng availability của control plane hoặc compute infrastructure, nhưng ứng dụng cần được thiết kế để tiếp tục phục vụ khi replica hoặc zone bị lỗi.

### 11.1. Replica và failure domain

Khách hàng cần quyết định:

- Số replica tối thiểu.
- Phân bố qua node/zone.
- Readiness và liveness.
- Graceful shutdown.
- PDB hoặc disruption policy tương đương.
- Autoscaling và capacity buffer.

Nếu mọi replica nằm trong cùng một zone, managed control plane không tự làm workload chịu được zone outage.

### 11.2. Dependency availability

Kiểm tra database, cache, queue, DNS, identity, secret manager, KMS và object storage. API có thể còn container healthy nhưng không phục vụ được request nếu dependency chính bị lỗi.

### 11.3. DR và failover

Khách hàng phải xác định:

- Backup/replication strategy.
- Recovery region và network.
- Image/artifact availability.
- Quota và capacity.
- Secret, certificate và identity.
- Traffic cutover và DNS.
- Actual RPO/RTO qua diễn tập.

Provider có thể cung cấp multi-zone hoặc multi-region building blocks, nhưng khách hàng phải cấu hình và kiểm chứng quy trình phục hồi.

## 12. Observability và vận hành

Mức managed cao hơn có thể giảm việc quan sát host, nhưng không làm mất nhu cầu quan sát ứng dụng.

| Tín hiệu | VM/container tự quản lý | Managed Kubernetes | Serverless container |
| --- | --- | --- | --- |
| Host metric | Khách hàng cài agent và thu thập | Tích hợp node metrics hoặc agent | Host metric thường bị trừu tượng hóa |
| Container metric | Runtime/cAdvisor hoặc agent | Metrics API, Prometheus hoặc dịch vụ managed | Request, instance và execution metrics của platform |
| Application metric | Khách hàng instrument | Khách hàng instrument | Khách hàng instrument |
| Distributed trace | Khách hàng cấu hình | Khách hàng cấu hình | Khách hàng cấu hình |
| Platform event | VM/system log | Kubernetes events và audit | Service events và execution logs |
| Alert/SLO | Khách hàng xác định | Khách hàng xác định | Khách hàng xác định |

Theo dõi:

- Request rate, error rate và p95/p99 latency.
- CPU, memory, throttling và restart.
- Queue depth và dependency latency.
- Desired/actual replicas và pending workload.
- Startup time, cold start và scale event.
- Cost per request/job và idle capacity.

## 13. Chi phí và mô hình tính phí

### 13.1. VM-backed container

Thường trả cho VM/node theo thời gian, disk, network và các dịch vụ đi kèm. Nếu container idle nhưng VM vẫn chạy, chi phí compute vẫn phát sinh.

Ưu điểm là có thể tối ưu utilization bằng cách đặt nhiều container trên node. Nhược điểm là cần dự phòng capacity và quản lý node.

### 13.2. Managed Kubernetes

Chi phí có thể gồm:

- Worker node hoặc serverless pod capacity.
- Managed control plane fee nếu dịch vụ có tính phí.
- Disk, load balancer, NAT và egress.
- Registry, logging, monitoring và add-on.
- Nhân lực platform engineering.

Cluster dùng chung nhiều workload có thể phân bổ chi phí nền tốt hơn. Cluster riêng cho một workload nhỏ có thể tạo overhead đáng kể.

### 13.3. Serverless container

Có thể tính theo vCPU-second, GB-second, request, task duration, minimum instance hoặc provisioned capacity. Chi phí idle có thể thấp nếu scale-to-zero, nhưng dịch vụ phụ trợ như database, gateway, storage và log vẫn có thể tính phí.

### 13.4. So sánh chi phí cần cùng điều kiện

Không so giá VM đơn lẻ với giá serverless execution mà bỏ qua:

- Multi-zone và standby capacity.
- Database, storage và network.
- Observability và security.
- Minimum instance/concurrency.
- Chi phí vận hành nhân lực.
- Migration và vendor-specific integration.

Tính TCO theo tháng/năm và cost per successful request/job trên cùng SLO.

## 14. Ma trận lựa chọn theo nhu cầu

| Nhu cầu | Mô hình thường phù hợp | Lý do và đánh đổi |
| --- | --- | --- |
| Cần kiểm soát kernel, host và agent đặc thù | Container trên VM | Kiểm soát cao, nhưng tự vận hành OS/runtime |
| Nhiều microservice và cần Kubernetes API | Managed Kubernetes Standard | Nhiều tính năng điều phối, cần năng lực platform |
| Muốn Kubernetes nhưng giảm quản lý node | Autopilot/serverless pod mode | Giảm node operations, ít quyền tùy chỉnh host |
| Dịch vụ container đơn giản, HTTP/event | Serverless container platform | Giảm cluster/node management, cần chấp nhận service limits |
| Batch chạy dài, cần node/driver đặc thù | VM-backed hoặc managed Kubernetes node pool | Kiểm soát phần cứng và runtime tốt hơn |
| Tải gián đoạn, có thể scale-to-zero | Serverless container | Giảm chi phí idle, cần đánh giá cold start |
| Workload ổn định 24/7 và nhiều service dùng chung | Managed Kubernetes hoặc orchestration trên node pool | Có thể tăng utilization, nhưng phải tính platform overhead |
| Cần chuyển đổi dần từ VM cũ | Container trên VM rồi managed orchestration | Cho phép migration theo giai đoạn |

Đây là gợi ý định hướng, không phải quy tắc tuyệt đối. Benchmark, security requirement, quota, region availability và kỹ năng đội ngũ có thể làm thay đổi lựa chọn.

## 15. Ví dụ: cùng một API trên ba mô hình

Giả sử một API Orders cần 3 replica tối thiểu, scale lên 20 replica, truy cập managed database và object storage, có yêu cầu rolling deployment không làm gián đoạn.

### 15.1. Phương án A: container trên VM

Đội ngũ tạo VM fleet, cài runtime, triển khai container bằng automation và đặt load balancer phía trước.

Khách hàng chịu trách nhiệm:

- Guest OS, patch và runtime.
- VM scaling, health monitoring và replacement.
- Container deployment và restart.
- Network/firewall và service discovery.
- Log/metric agent và backup cấu hình.

Đội ngũ có quyền kiểm soát cao nhưng phải vận hành nhiều lớp.

### 15.2. Phương án B: managed Kubernetes

Đội ngũ tạo cluster, node pool, Deployment, Service, HPA, PDB và ingress.

Provider quản lý control plane; trách nhiệm node phụ thuộc loại node pool. Khách hàng chịu trách nhiệm:

- Node pool configuration và upgrade policy.
- Container image, Deployment và rollout.
- Resource requests/limits, HPA và topology.
- RBAC, network policy và workload identity.
- Database connection budget và application SLO.

Nền tảng giảm công việc control plane nhưng yêu cầu năng lực Kubernetes.

### 15.3. Phương án C: serverless container

Đội ngũ triển khai image vào service, cấu hình CPU/RAM, concurrency, min/max instances, ingress và identity.

Provider quản lý host và capacity provisioning. Khách hàng vẫn chịu trách nhiệm:

- API stateless và graceful request handling.
- Image, dependency và vulnerability patch.
- IAM, secret, data và network configuration.
- Concurrency, timeout, scale limits và cold start.
- SLO, observability và downstream capacity.

Đội ngũ ít quản lý máy chủ hơn nhưng phải thiết kế theo giới hạn và semantics của platform.

## 16. Quy trình chuyển từ VM sang managed container

1. **Lập inventory:** ứng dụng, OS dependency, port, file path, daemon, license và dữ liệu.
2. **Phân loại state:** session, file, cache và job nào đang gắn với VM.
3. **Externalize state:** chuyển dữ liệu cần tồn tại sang database, object storage, cache hoặc queue.
4. **Đóng gói image:** pin dependency, build pipeline, scan và version hóa.
5. **Chọn mô hình managed:** Kubernetes, task orchestration hay serverless container.
6. **Lập ma trận trách nhiệm:** xác định ai patch node, image, runtime, network, secret và backup.
7. **Thiết kế health/lifecycle:** readiness, startup, liveness, graceful shutdown và draining.
8. **Thiết kế capacity:** resource requests/limits, concurrency, HPA và quota.
9. **Thiết kế security:** identity, RBAC, network policy, image policy và audit.
10. **Triển khai thử:** staging, canary hoặc traffic shadowing.
11. **Kiểm tra failure:** terminate replica, drain node, dependency outage và zone failure trong phạm vi thử.
12. **Đo TCO/SLO:** latency, error, availability, utilization, cost và operational effort.
13. **Migrate theo đợt:** có rollback và thời gian chạy song song.
14. **Cập nhật runbook:** chuyển quyền vận hành, alert, escalation và lịch patch.

## 17. Những hiểu nhầm thường gặp

- Cho rằng dùng container thì không còn phải quản lý OS.
- Cho rằng managed Kubernetes đồng nghĩa provider quản lý mọi worker node.
- Cho rằng serverless container không cần patch image.
- Cho rằng provider chịu trách nhiệm backup dữ liệu ứng dụng.
- Cho rằng HPA có thể tạo capacity vượt quota hoặc khi zone hết tài nguyên.
- Cho rằng private network thay thế authentication.
- Cho rằng managed control plane bảo đảm workload multi-zone.
- Cho rằng container image portable đồng nghĩa mọi platform behavior giống nhau.
- Chỉ so sánh giá compute mà bỏ qua control plane, logging, egress và nhân lực.
- Không kiểm tra giới hạn runtime, concurrency, timeout hoặc storage của serverless platform.

## 18. Checklist xác định trách nhiệm trước production

**Compute và máy chủ**

- [ ] Ai quản lý VM/worker node và node pool?
- [ ] Ai cập nhật guest OS, kernel và container runtime?
- [ ] Ai cấu hình autoscaling, quota và capacity?
- [ ] Ai xử lý node drain, reboot và replacement?

**Platform và workload**

- [ ] Ai quản lý control plane, cluster version và add-on?
- [ ] Ai build, scan, sign và cập nhật container image?
- [ ] Ai quản lý deployment, rollout, rollback và health probe?
- [ ] Ai quản lý service discovery, ingress và load balancing?

**Security và data**

- [ ] Ai cấp workload identity và review IAM?
- [ ] Ai quản lý secret, certificate và rotation?
- [ ] Ai cấu hình network isolation và egress?
- [ ] Ai backup, restore, encryption và retention dữ liệu?

**Operations**

- [ ] Ai chịu trách nhiệm SLO, alert và on-call?
- [ ] Ai xử lý incident ở host, platform và application?
- [ ] Ai diễn tập failover/DR và đo RPO/RTO?
- [ ] Ai theo dõi chi phí, license và shared platform overhead?
- [ ] Runbook có nêu rõ escalation đến provider khi lỗi thuộc dịch vụ managed?

## 19. Nguyên tắc vận hành

1. **Đọc đúng mô hình dịch vụ:** container trên VM, managed Kubernetes và serverless container có ranh giới trách nhiệm khác nhau.
2. **Tách control plane khỏi worker node:** provider quản lý control plane không có nghĩa khách hàng không còn trách nhiệm node.
3. **Phân biệt host patch và image patch:** provider có thể vá host nhưng khách hàng vẫn cập nhật dependency ứng dụng.
4. **Xác định rõ shared responsibility:** IAM, network, data, backup, SLO và observability thường vẫn cần khách hàng cấu hình.
5. **Tính capacity end-to-end:** autoscaler không vượt quota và không bảo đảm dependency còn capacity.
6. **Thiết kế workload có thể thay thế:** statelessness, readiness và graceful shutdown giúp tận dụng managed orchestration.
7. **Đánh giá giới hạn platform:** cold start, concurrency, timeout, storage và runtime restrictions ảnh hưởng kiến trúc.
8. **Tính TCO đầy đủ:** node, control plane, network, logging, security, license và nhân lực.
9. **Kiểm thử trách nhiệm thực tế:** diễn tập node upgrade, image update, scale-out, failover và restore.
10. **Duy trì ownership rõ ràng:** mỗi lớp có owner, runbook, alert và đường escalation.

Các mô hình chạy container khác nhau chủ yếu ở mức trừu tượng và phần hạ tầng mà nhà cung cấp vận hành. Container tự quản lý trên VM đem lại quyền kiểm soát cao nhưng yêu cầu đội ngũ quản lý máy chủ, runtime và orchestration. Managed Kubernetes giảm trách nhiệm control plane nhưng node và workload vẫn cần được cấu hình, cập nhật và quan sát. Serverless container giảm nhiều công việc host và capacity provisioning, trong khi trách nhiệm về image, ứng dụng, dữ liệu, identity, network và SLO vẫn thuộc khách hàng. Khi đối chiếu theo từng lớp trách nhiệm thay vì chỉ nhìn tên dịch vụ, tổ chức có thể chọn mô hình phù hợp với năng lực vận hành, yêu cầu kiểm soát và chi phí của workload.
