# Kiến trúc AKS và lựa chọn mô hình cluster

## 1. Bài toán kiến trúc: khi nào cần Kubernetes trên Azure?

Một ứng dụng trên Microsoft Azure có thể bắt đầu bằng một máy ảo, sau đó chuyển sang container để đóng gói runtime và triển khai nhất quán. Khi hệ thống tăng thành nhiều API, worker, tác vụ nền và thành phần dữ liệu, nhóm vận hành phải giải quyết các vấn đề: triển khai hàng chục container, định tuyến lưu lượng, theo dõi sức khỏe, mở rộng theo tải, cập nhật từng phiên bản và bảo vệ kết nối giữa các dịch vụ.

**Azure Kubernetes Service (AKS)** là dịch vụ Kubernetes được quản lý trên Azure. AKS giúp đơn giản hóa việc triển khai và vận hành Kubernetes bằng cách để Azure quản lý phần lớn hạ tầng **control plane**, trong khi nhóm sử dụng tập trung vào thiết kế cluster, node pools, mạng, quyền truy cập, ứng dụng và vòng đời hệ thống.

Bài học thuộc chương **Nền tảng Azure Kubernetes Service** của module khám phá hệ sinh thái Microsoft Azure. AKS kết nối những kiến thức về subscription, resource group, Microsoft Entra ID, mạng ảo, VM, registry, lưu trữ, dữ liệu, giám sát, bảo mật và kiểm soát chi phí thành một kiến trúc ứng dụng chạy container.

**Câu hỏi trọng tâm không phải “làm sao tạo AKS nhanh nhất?” mà là “có thật sự cần AKS và nên chọn mô hình cluster nào để vừa đáp ứng yêu cầu vừa vận hành được?”**

Ví dụ: một doanh nghiệp có ba API Java, một dịch vụ gửi email, một worker xử lý ảnh và một cổng quản trị. Có thể triển khai trên AKS, nhưng nếu nhóm nhỏ và không cần khả năng điều phối Kubernetes chuyên sâu, Azure Container Apps hoặc App Service cũng đáng cân nhắc. Một lựa chọn đúng cần xem cả tính năng, năng lực đội ngũ, chi phí, mức cách ly và yêu cầu vận hành.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả kiến trúc AKS gồm **control plane**, **node pools**, **nodes**, **pods**, **services** và các thành phần hệ thống.
2. Phân biệt trách nhiệm của Azure với trách nhiệm của người vận hành AKS.
3. So sánh trải nghiệm **AKS Standard** và **AKS Automatic** khi các lựa chọn này được hỗ trợ.
4. Quyết định dùng cluster riêng hay chia sẻ, cluster public hay private, single-region hay multi-region.
5. Thiết kế system node pool, user node pools, VM size, Availability Zones và Spot nodes khi phù hợp.
6. Lập kế hoạch VNet, subnet, Pod IP, Service CIDR, ingress, egress và Network Policy.
7. Kết hợp Microsoft Entra ID, Azure RBAC, Kubernetes RBAC, managed identity, workload identity và ACR.
8. Hiểu Deployment, Service, probes, requests/limits, HPA, cluster autoscaler, KEDA và lưu trữ bền vững.
9. Lập kế hoạch nâng cấp Kubernetes, bảo mật, quan sát hệ thống, backup/DR và kiểm soát chi phí.
10. Thực hành kiểm tra một cluster và triển khai workload thử nghiệm không công khai ra Internet.

## 3. Bức tranh tổng thể của kiến trúc AKS

~~~mermaid
flowchart TB
    ADMIN[Quản trị viên / CI-CD] --> API[Kubernetes API Server]
    subgraph CP[Control plane do Azure quản lý]
        API --> SCHED[Scheduler]
        API --> CTRL[Controllers]
        API --> ETCD[(etcd - cluster state)]
    end
    subgraph NODES[Node pools trong Azure]
        N1[Node 1 - kubelet / container runtime]
        N2[Node 2 - kubelet / container runtime]
        N3[Node 3 - kubelet / container runtime]
        N1 --> P1[API Pods]
        N2 --> P2[API Pods]
        N3 --> P3[Worker Pods]
    end
    API --> N1
    API --> N2
    API --> N3
    CLIENT[Người dùng] --> ING[Ingress / Load Balancer]
    ING --> P1
    ING --> P2
    P1 --> DB[(Database)]
    P2 --> DB
    P3 --> STORE[(Queue / Blob Storage)]
    ID[Microsoft Entra ID / Workload Identity] --> P1
    REG[Azure Container Registry] --> NODES
~~~

Đây là sơ đồ khái niệm. Đường truy cập API server, cách ingress được triển khai và cơ chế kéo image phụ thuộc cấu hình thực tế. Control plane không chạy như một tập VM mà người dùng có thể tự đăng nhập rồi chỉnh sửa tùy ý.

Ba lớp cần ghi nhớ:

- **Control plane:** lưu trạng thái mong muốn, nhận yêu cầu Kubernetes API và điều phối các đối tượng.
- **Worker nodes:** VM thực tế dùng CPU/RAM để chạy pods; thường được tổ chức thành node pools.
- **Workloads:** Deployment, StatefulSet, DaemonSet, Job, CronJob, Service và các đối tượng ứng dụng khác.

**AKS được quản lý không đồng nghĩa mọi thành phần đều được Azure tự vận hành thay bạn.** Nhóm sử dụng vẫn phải cấu hình quyền, networking, image, nâng cấp, quota, bảo mật container, backup dữ liệu và khả năng phục hồi của ứng dụng.

## 4. Control plane làm những gì?

Control plane của Kubernetes có những thành phần chính:

| Thành phần | Chức năng | Ý nghĩa khi thiết kế |
|---|---|---|
| **kube-apiserver** | Cung cấp Kubernetes API cho kubectl, controller và automation | Cần bảo vệ endpoint, quyền và đường mạng |
| **etcd** | Lưu trạng thái cấu hình cluster | Không sử dụng nó như cơ sở dữ liệu nghiệp vụ |
| **kube-scheduler** | Quyết định Pod phù hợp được đặt trên Node nào | Phụ thuộc resources, affinity, taints, topology |
| **kube-controller-manager** | Chạy các controller duy trì trạng thái mong muốn | Giúp Kubernetes tái tạo pods và điều phối đối tượng |
| **Cloud integration** | Kết nối Kubernetes với tài nguyên Azure được hỗ trợ | Load Balancer, disk, identity và networking |

Ví dụ bạn khai báo **replicas: 3** cho một Deployment. Controller cố gắng duy trì ba pod tương ứng. Khi một pod chết, hệ thống có thể tạo pod thay thế, nhưng nếu toàn bộ node pool không còn chỗ, pod sẽ **Pending** cho tới khi có capacity thích hợp.

### 4.1. “Managed control plane” không có nghĩa không cần nghĩ đến SLA

Azure quản lý việc triển khai và bảo trì control plane theo gói/dịch vụ được chọn. Tuy nhiên, người dùng vẫn cần:

- Chọn mức dịch vụ/SLA phù hợp nếu ứng dụng cần cam kết availability.
- Bảo vệ truy cập Kubernetes API.
- Lập kế hoạch nâng cấp phiên bản và khả năng tương thích.
- Theo dõi trạng thái cluster và sự kiện control plane.
- Thiết kế ứng dụng vẫn phục vụ được khi Kubernetes API tạm thời không khả dụng, trong phạm vi hoạt động của những pods đang chạy.

**Khả dụng của control plane khác khả dụng của ứng dụng.** Control plane vẫn có thể hoạt động trong khi các pods ứng dụng liên tục crash hoặc database bị lỗi.

## 5. Node, node pool và tài nguyên Azure phía sau

**Node** là máy chạy kubelet và container runtime để thực thi pods. Trong AKS, nodes thường là các Azure VMs được quản lý qua các tài nguyên hạ tầng của cluster. **Node pool** là một nhóm nodes có chung cấu hình quan trọng như VM SKU, OS, image, scaling và các thuộc tính scheduling.

Trong Kubernetes node:

- **kubelet** theo dõi PodSpec và phối hợp với runtime.
- **Container runtime** như containerd khởi chạy containers theo image.
- **CNI/networking components** cấu hình kết nối mạng cho pods.
- **CSI drivers** hỗ trợ gắn volume từ dịch vụ lưu trữ.
- **DaemonSets** có thể chạy một pod trên mỗi node phù hợp để thu thập logs hoặc thực thi agent.

### 5.1. AKS có hai nhóm tài nguyên Azure cần phân biệt

Một AKS thường liên quan đến:

1. **Resource group chứa tài nguyên AKS** mà bạn tạo/chọn, ví dụ **rg-aks-app**.
2. **Node resource group** do AKS tạo/quản lý, thường có tên theo dạng **MC_...**, chứa nhiều tài nguyên cơ sở hạ tầng như VM Scale Sets, NIC, disk và load balancing.

Không nên tự chỉnh sửa các tài nguyên do AKS quản lý trong node resource group bằng cách bỏ qua Kubernetes/AKS API, trừ những thao tác được Microsoft hỗ trợ. Thay đổi thủ công có thể bị bộ điều khiển ghi đè hoặc làm cluster rơi vào cấu hình khó bảo trì.

### 5.2. Không nhầm node pool với namespace

- **Node pool:** phân nhóm **năng lực compute** và đặc tính máy.
- **Namespace:** phân nhóm **đối tượng Kubernetes**, hữu ích cho tổ chức và chính sách.
- **Resource group:** phạm vi quản lý tài nguyên Azure, không phải namespace Kubernetes.

Một namespace có thể có pods chạy ở nhiều node pools; một node pool có thể phục vụ pods của nhiều namespaces nếu không được giới hạn bằng scheduling rules.

## 6. System node pool và user node pool

Một thiết kế AKS thường phân biệt **system node pools** và **user node pools**.

| Loại | Mục đích | Workload điển hình |
|---|---|---|
| **System node pool** | Cung cấp năng lực cho các thành phần hệ thống Kubernetes quan trọng | DNS, networking/monitoring agents và hệ thống |
| **User node pool** | Chạy ứng dụng và công việc của tổ chức | Java API, background worker, batch job |

Một cluster production nên cân nhắc dành đủ năng lực và khả năng dự phòng cho system components, không đặt hệ thống ở tình trạng thiếu tài nguyên khi application pods tăng đột ngột.

### 6.1. Thiết kế mẫu

~~~text
AKS cluster
├── systempool: nhiều nodes ổn định, VM size phù hợp
├── apipool: chạy HTTP API, HPA và autoscale
└── workerpool: xử lý Queue/Batch, có thể khác VM SKU
~~~

Đây là mô hình logic, không phải yêu cầu bắt buộc mọi cluster phải có ba pools. Với hệ thống nhỏ, có thể bắt đầu đơn giản rồi tách khi có lý do vận hành.

### 6.2. Labels, taints và tolerations

Kubernetes hỗ trợ chọn nơi chạy pod:

- **Node labels:** mô tả đặc tính node.
- **nodeSelector/affinity:** yêu cầu hoặc ưu tiên pods chạy trên nodes phù hợp.
- **Taints và tolerations:** hạn chế những pods không được cho phép đặt trên node pool.
- **Topology spread constraints:** phân tán replicas giữa các zone/nodes theo yêu cầu.

Ví dụ, worker dùng GPU không nên vô tình được scheduler đặt lên CPU-only node. Một user pool GPU có thể được gắn label/taint và ứng dụng AI được cấu hình toleration cùng resource request tương ứng.

**Taint không phải một ranh giới bảo mật tuyệt đối.** Nó là công cụ scheduling; khi cần cách ly mạnh phải kết hợp quyền, admission policy, network isolation và đôi khi cluster riêng.

## 7. AKS Standard và AKS Automatic: lựa chọn mức quản lý

Azure có những trải nghiệm triển khai AKS như **AKS Standard** và **AKS Automatic**, tùy thời điểm, region và khả năng hỗ trợ. Cách đặt tên, mặc định và tính năng có thể thay đổi; hãy kiểm tra tính năng thực tế của subscription trước khi chốt kiến trúc.

### 7.1. AKS Standard

Mô hình Standard tập trung vào việc cho nhóm nền tảng chủ động đưa ra nhiều quyết định:

- Chọn networking, node pools, scaling và VM SKU.
- Thiết lập controls cho security, ingress, upgrade và monitoring.
- Điều chỉnh cấu hình theo topology enterprise.
- Chịu trách nhiệm nhiều hơn về thiết kế và vận hành những thành phần của cluster.

Phù hợp khi đội ngũ cần kiểm soát hạ tầng Kubernetes sâu, có yêu cầu mạng phức tạp hoặc muốn áp dụng những chuẩn nội bộ cụ thể.

### 7.2. AKS Automatic

Trải nghiệm Automatic hướng đến việc giảm công việc cấu hình/vận hành cluster bằng cách cung cấp nhiều quyết định mặc định và chức năng được quản lý/tự động hóa hơn.

Phù hợp khi nhóm ưu tiên tốc độ triển khai và chấp nhận những lựa chọn/giới hạn mà trải nghiệm này hỗ trợ. Nhưng vẫn phải chịu trách nhiệm cho ứng dụng, quyền, dữ liệu, chi phí và các chính sách bảo mật.

### 7.3. So sánh hướng quyết định

| Câu hỏi | Nghiêng về Standard | Nghiêng về Automatic |
|---|---|---|
| Cần kiểm soát sâu node pools/networking? | Thường phù hợp hơn | Kiểm tra giới hạn tùy chỉnh |
| Muốn giảm số lựa chọn hạ tầng phải vận hành? | Cần cấu hình bổ sung | Thường phù hợp hơn |
| Có mô hình enterprise đặc thù? | Thuận lợi khi cần cấu hình chi tiết | Xác nhận tính năng trước |
| Nhóm mới với Kubernetes? | Cần đào tạo và vận hành nhiều hơn | Có thể giảm công việc nền tảng |
| Chính sách compliance yêu cầu thiết lập riêng? | Có thể linh hoạt hơn | Phải xác minh có đáp ứng được không |

**Automatic và Standard không phải Kubernetes cluster có/không có control plane.** Cả hai đều thuộc AKS; khác nhau về mức tự động hóa và quyền kiểm soát thiết lập theo từng trải nghiệm. Đồng thời, **mức dịch vụ/SLA của control plane** là một chiều lựa chọn khác, không nên đồng nhất với tên trải nghiệm Automatic/Standard.

## 8. Có thật sự cần AKS không?

Đừng chọn AKS chỉ vì ứng dụng được đóng gói container.

| Nền tảng | Phù hợp khi | Cần cân nhắc |
|---|---|---|
| **Azure App Service** | Web/API với luồng triển khai đơn giản, runtime được hỗ trợ | Ít quyền điều khiển Kubernetes |
| **Azure Container Apps** | Microservices, jobs, container có nhu cầu autoscale nhưng muốn ít vận hành cluster | Giới hạn và mô hình nền tảng khác AKS |
| **AKS** | Nhiều ứng dụng Kubernetes, cần CRD/operator, policies, node pools, topology và quy trình K8s cụ thể | Đòi hỏi năng lực vận hành và chi phí nền tảng |
| **VM/VMSS** | Workload cần kiểm soát OS/VM, chưa phù hợp K8s | Tự quản trị nhiều phần triển khai và lifecycle |

### 8.1. Những dấu hiệu AKS phù hợp

- Tổ chức đã có chuẩn triển khai Kubernetes, Helm/GitOps và đội nền tảng có kỹ năng.
- Cần operator, CRDs, service mesh hoặc các Kubernetes primitives cụ thể.
- Có nhiều workloads cần scheduling với node pools và tài nguyên khác nhau.
- Cần kiểm soát Kubernetes networking, namespace policies, ingress và deployment lifecycle.
- Muốn nhất quán triển khai một tập ứng dụng phức tạp theo mô hình Kubernetes.

### 8.2. Khi nào nên chọn dịch vụ đơn giản hơn?

Nếu chỉ có một API Java và một worker nền, không cần khả năng Kubernetes chuyên sâu, hãy đánh giá App Service hoặc Container Apps trước. Một dịch vụ có ít thành phần nhưng bị buộc chạy AKS có thể phải chịu thêm chi phí nodes, networking, monitoring, Kubernetes upgrades và trực vận hành mà không tăng giá trị tương ứng.

**Tiêu chí chọn là yêu cầu thật của ứng dụng và năng lực đội ngũ, không phải độ phổ biến của công nghệ.**

## 9. Một cluster hay nhiều cluster?

Đây là lựa chọn ảnh hưởng trực tiếp đến chi phí, blast radius và quyền quản trị.

### 9.1. Một cluster dùng chung nhiều ứng dụng

Ví dụ:

~~~text
AKS shared cluster
├── namespace team-orders
├── namespace team-customers
└── namespace team-analytics
~~~

Ưu điểm:

- Chia sẻ node capacity và dịch vụ nền tảng.
- Có thể giảm số control plane, node pools và công việc vận hành.
- Tiện khi nhiều nhóm có tiêu chuẩn bảo mật tương tự nhau.

Hạn chế:

- Lỗi nâng cấp, cấu hình networking hoặc quyền ở cấp cluster ảnh hưởng nhiều nhóm.
- Các ứng dụng cạnh tranh CPU, memory, IP, quota và các giới hạn chung.
- Namespace không phải ranh giới cô lập an ninh mạnh tương đương một cluster độc lập.

### 9.2. Cluster riêng cho môi trường hoặc nhóm có rủi ro cao

Ví dụ:

~~~text
aks-dev-shared
aks-staging
aks-prod-orders
aks-prod-finance
~~~

Ưu điểm:

- Có thể tách quyền, cấu hình network, maintenance window và fault domain vận hành.
- Giảm nguy cơ thay đổi thử nghiệm ảnh hưởng production.
- Phù hợp khi các nhóm có yêu cầu compliance hoặc vòng đời khác nhau.

Hạn chế:

- Tăng số tài nguyên, chi phí quản trị và công việc cập nhật.
- Cần vận hành nhiều pipelines, policies, monitoring và identity integrations.
- Phân mảnh capacity nếu mỗi cluster đều giữ nhiều nodes nhàn rỗi.

### 9.3. Quy tắc gợi ý

**Tách production khỏi development/test** thường là lựa chọn đáng cân nhắc khi yêu cầu an toàn và độ ổn định cao. Với nhiều team có cùng mức tin cậy, cluster production dùng chung có thể tiết kiệm nhưng cần quota, RBAC, Network Policy, admission controls và giám sát rõ ràng. Với workload nhạy cảm hoặc yêu cầu cách ly mạnh, cluster riêng có thể phù hợp hơn.

Không chọn một cluster cho mỗi microservice một cách máy móc; cũng không nên gom mọi workload vào cùng một cluster mà không đánh giá blast radius.

## 10. Public cluster hay private cluster?

Kubernetes API endpoint là điểm quản trị nhạy cảm. Lựa chọn public/private liên quan đến **đường truy cập API server**, không chỉ đến việc ứng dụng có IP public hay không.

### 10.1. API server có public endpoint

Một cluster có API endpoint public cho phép công cụ quản lý truy cập endpoint qua mạng Internet theo cấu hình. Vẫn phải xác thực và phân quyền; có thể giới hạn nguồn truy cập bằng **authorized IP ranges** hoặc cơ chế hỗ trợ khác.

**Public endpoint không có nghĩa mọi người có quyền quản trị cluster.** Rủi ro phụ thuộc authentication, RBAC, giới hạn mạng, bảo mật client và cấu hình cluster.

### 10.2. Private AKS cluster

Với private cluster, truy cập API server được thiết kế qua private connectivity và DNS theo mô hình AKS hỗ trợ. Công cụ kubectl, CI runner và người vận hành phải có đường mạng hợp lệ, ví dụ qua mạng nội bộ kết nối VPN/ExpressRoute, jump host hoặc môi trường quản trị phù hợp.

Ưu điểm:

- Giảm khả năng truy cập API server trực tiếp qua Internet.
- Phù hợp với chính sách enterprise yêu cầu private management plane.

Hạn chế:

- Cần thiết kế DNS, routing, firewall và kết nối quản trị.
- CI/CD hosted runner không có đường vào VNet có thể không quản lý được cluster.
- Việc xử lý sự cố và cấp quyền truy cập phải được chuẩn bị trước.

### 10.3. Không nhầm private API với private ứng dụng

Một cluster có API server private vẫn có thể triển khai **public LoadBalancer/Ingress** cho ứng dụng khách hàng. Ngược lại, cluster API public có thể chạy workloads nội bộ không mở Internet.

Phải ra quyết định riêng cho:

1. Truy cập **Kubernetes API**.
2. Truy cập **ứng dụng**.
3. Đường **egress** từ nodes/pods ra dịch vụ ngoài.

## 11. Thiết kế region, Availability Zones và HA

Một AKS production thường cần nhiều nodes và replicas để chịu lỗi hạ tầng.

### 11.1. Availability Zones

Nếu region và VM SKU hỗ trợ, nên cân nhắc phân bố nodes của các pools quan trọng qua nhiều **Availability Zones**. Nhưng chỉ chọn zones trong node pool chưa đủ: workloads phải có nhiều replicas, lịch scheduling đúng và các dependencies cũng có kế hoạch dự phòng.

Ví dụ:

~~~text
Region hỗ trợ zone
  Zone 1: system node(s), API pod(s)
  Zone 2: system node(s), API pod(s)
  Zone 3: system node(s), API pod(s)
~~~

Đây là mục tiêu kiến trúc; số node thực tế và việc pods được phân bố thế nào cần được kiểm tra.

### 11.2. Replica và PodDisruptionBudget

**Deployment replicas** giúp duy trì nhiều bản ứng dụng. **PodDisruptionBudget (PDB)** hạn chế số pods có thể bị gián đoạn tự nguyện trong các tác vụ như drain hoặc nâng cấp.

Tuy nhiên, PDB không ngăn sự cố mất node/zone ngoài ý muốn, và cấu hình quá chặt có thể ngăn quá trình nâng cấp. Phải kiểm tra PDB cùng tổng replicas và capacity dự phòng.

### 11.3. Multi-region không chỉ là nhiều AKS

Nếu yêu cầu phục hồi khi mất một region, có thể thiết kế **hai AKS clusters ở hai regions** kết hợp Front Door/Traffic Manager hoặc cơ chế định tuyến thích hợp. Nhưng cần:

- Dữ liệu và database replication theo RPO.
- Image có sẵn tại region dự phòng.
- Quyền/secret/config giống mong đợi.
- Network, DNS, TLS và storage được chuẩn bị.
- Kịch bản failover và failback được diễn tập.

**Availability Zones bảo vệ trước một số lỗi trong region; không thay thế disaster recovery đa region.**

## 12. System pool và user pools trong production

Một thiết kế thường dùng:

| Pool | Vai trò | Định hướng |
|---|---|---|
| **systempool** | Kubernetes system components | VM ổn định, năng lực dự phòng phù hợp |
| **apipool** | API stateless | Replicas và autoscale theo lưu lượng |
| **workerpool** | Batch/Queue workers | Có thể dùng SKU hoặc scaling riêng |
| **gpupool** | Xử lý GPU nếu có | Chỉ bật khi có nhu cầu, quota và plugin thích hợp |

Không phải ứng dụng nào cũng cần bốn pools. Nhiều pools giúp phân tách tài nguyên và tối ưu scheduling nhưng tăng quản trị, chi phí cố định và rủi ro phân mảnh compute.

### 12.1. System nodes không nên bị lấp đầy

System components cần CPU, RAM và disk. Nếu bạn cho phép workloads batch chiếm hết tài nguyên của system pool, DNS, network agents và các thành phần nền tảng có thể trở nên không ổn định.

### 12.2. Node pool theo đặc tính workload

Ví dụ:

- API Java cần nhiều RAM cho JVM → chọn pool có bộ nhớ phù hợp.
- Worker xử lý ảnh dùng CPU nhiều → pool compute-oriented.
- Workload Windows cần Windows node pool tương thích.
- Job chịu eviction có thể dùng Spot pool nếu AKS/mode hỗ trợ.

Không đặt Windows/Linux pods vào pool sai OS; dùng node selectors, labels và cấu hình image architecture thích hợp.

## 13. Thiết kế IP trước khi tạo cluster

Kubernetes dùng nhiều lớp địa chỉ:

- **VNet/subnet CIDR:** địa chỉ của nodes và các thành phần Azure.
- **Pod CIDR hoặc Pod subnet:** địa chỉ của pods tùy mô hình CNI.
- **Service CIDR:** không gian IP ảo của Kubernetes Services.
- **DNS service IP:** IP của dịch vụ DNS trong cluster.
- **Mạng on-prem/peered VNet:** các prefix kết nối qua VPN/ExpressRoute.
- **Private endpoints:** địa chỉ trong VNet cho các dịch vụ Azure.

Ví dụ kế hoạch địa chỉ mang tính minh họa:

| Loại | CIDR |
|---|---|
| VNet | 10.40.0.0/16 |
| Node subnet | 10.40.10.0/24 |
| Pod overlay CIDR | 10.244.0.0/16 |
| Service CIDR | 10.96.0.0/16 |
| DNS service IP | 10.96.0.10 |
| On-prem | 172.20.0.0/16 |

**Không được để các dải này chồng lấn với nhau hoặc với mạng phải liên thông**, theo điều kiện networking mode được dùng. Các dải trên chỉ là ví dụ về nguyên tắc tách subnet; khi triển khai thực tế, phải kiểm tra cả reserved ranges, giới hạn AKS và kế hoạch mở rộng.

Thiết kế địa chỉ sai thường khó sửa sau khi cluster có dữ liệu hoặc nhiều workload. Một số thay đổi CIDR yêu cầu tạo cluster mới hoặc quy trình chuyển đổi phức tạp.

## 14. Azure CNI và cách cấp IP cho Pods

**Container Network Interface (CNI)** là lớp kết nối mạng cho pods. AKS hỗ trợ những mô hình Azure CNI khác nhau tùy thời điểm, SKU và cấu hình.

### 14.1. Azure CNI Overlay

Trong mô hình **overlay**, pods có thể lấy địa chỉ từ một không gian Pod CIDR riêng với VNet subnet của nodes. Hạ tầng mạng điều phối lưu lượng pod-pod và pod-ra-ngoài theo cơ chế overlay/NAT của mô hình.

Lợi ích thường gặp:

- Giảm nhu cầu tiêu thụ trực tiếp IP của VNet cho từng pod.
- Hữu ích khi VNet IP space có giới hạn và pod count lớn.
- Cho phép tách quy hoạch IP pod khỏi node subnet theo điều kiện hỗ trợ.

Cần kiểm tra đặc tính routing, network policy, outbound connectivity, tính tương thích với dịch vụ và những trường hợp truy cập pod trực tiếp.

### 14.2. Azure CNI với địa chỉ từ VNet/pod subnet

Một số mô hình Azure CNI cung cấp địa chỉ có thể định tuyến trong mạng Azure cho pods theo cách hỗ trợ, ví dụ cấp từ node subnet hoặc pod subnet.

Điều này có lợi trong một số kiến trúc nhưng **tiêu thụ IP VNet/pod subnet** theo số pods và cấu hình cấp phát, nên phải tính trước khả năng mở rộng.

### 14.3. Network dataplane và policy

AKS có thể hỗ trợ các lựa chọn dataplane/network policy như **Azure CNI powered by Cilium** hoặc những cơ chế khác tùy cấu hình. Các tính năng policy, observability và khả năng tích hợp phải được xác minh ở phiên bản AKS/networking đang dùng.

**Network Policy không thay thế NSG/Azure Firewall**, và NSG cũng không tự áp dụng chính sách giao tiếp pod-to-pod theo cùng cách. Thiết kế có thể cần nhiều lớp bảo vệ.

### 14.4. Không chọn mạng chỉ vì một câu lệnh mẫu

Khi chọn CNI, hãy hỏi:

1. Mỗi node tối đa bao nhiêu pods?
2. Node pool tối đa bao nhiêu nodes?
3. VNet còn đủ địa chỉ không?
4. Có kết nối on-prem/peered VNet hoặc private endpoints không?
5. Có cần kiểm soát east-west traffic giữa namespaces không?
6. Chấp nhận mô hình overlay/NAT hay cần pod IP routable trong VNet?
7. Các công cụ monitoring, security và policy đã được hỗ trợ chưa?

Đây là quyết định nền tảng của cluster; tránh chọn ngẫu nhiên rồi đổi sau khi có workloads.

## 15. Service, Ingress và đường lưu lượng

Kubernetes có các đối tượng giúp ứng dụng giao tiếp:

| Thành phần | Chức năng | Ví dụ |
|---|---|---|
| **ClusterIP Service** | Định danh và cân bằng nội bộ trong cluster | API backend gọi service orders-api |
| **NodePort** | Mở cổng trên nodes theo cơ chế hỗ trợ | Thường là cấu phần kỹ thuật hoặc lab |
| **LoadBalancer Service** | Yêu cầu Azure tạo/tích hợp load balancer theo cấu hình | Endpoint TCP/HTTP public hoặc private |
| **Ingress / Gateway API** | Quy tắc L7 khi có controller/implementation tương ứng | HTTP host/path, TLS, route đến Services |

**Ingress resource không tự xử lý traffic nếu chưa có controller phù hợp.** Ví dụ bạn cần thiết lập một ingress controller hoặc dịch vụ tích hợp được AKS hỗ trợ; cấu hình chỉ có YAML Ingress mà không có controller sẽ không tạo proxy thực tế.

### 15.1. Public ingress

Dùng khi người dùng Internet cần gọi API. Cần TLS, WAF nếu phù hợp, chính sách bảo vệ application/API và health checks.

### 15.2. Internal ingress

Dùng khi API chỉ phục vụ mạng nội bộ, private endpoint hoặc các workload khác. Có thể cấu hình internal Load Balancer hoặc ingress tương ứng, không công khai public IP.

### 15.3. Outbound/egress

Nodes/pods có thể cần tải image từ ACR, gọi API ngoài, truy cập các dịch vụ Azure và gửi telemetry. Hãy thiết kế egress rõ ràng qua NAT Gateway, Azure Firewall hoặc phương án AKS hỗ trợ, tránh dựa vào default outbound không được kiểm soát.

**AKS private cluster vẫn cần đường đến những endpoint bắt buộc để cluster và workloads hoạt động.** Chính sách egress quá chặt có thể làm lỗi image pull, node bootstrap hoặc update.

## 16. DNS và service discovery

Trong cluster, Kubernetes DNS thường cho phép một pod gọi Service bằng tên:

~~~text
orders-api.apps.svc.cluster.local
~~~

Giả sử:

- Service name: **orders-api**
- Namespace: **apps**
- Cluster domain: **cluster.local** (ví dụ phổ biến)

Pod trong namespace khác có thể dùng FQDN này để truy cập Service. Nhưng nếu service nằm ở namespace **apps** và pod ở cùng namespace, tên ngắn **orders-api** thường đủ.

Cần phân biệt:

- **CoreDNS/Kubernetes service discovery:** tên Service trong cluster.
- **Azure Private DNS:** tên của private endpoints hoặc tài nguyên Azure trong VNet.
- **DNS public:** tên miền Internet của ứng dụng.

Một workload AKS dùng Azure SQL qua private endpoint có thể yêu cầu đúng private DNS zone, VNet linkage và routing. Kubernetes DNS hoạt động không đồng nghĩa private DNS của dịch vụ Azure đã được cấu hình đúng.

## 17. Danh tính và quyền truy cập trong AKS

Một thiết kế có ít nhất ba nhóm quyền khác nhau:

1. **Quản trị Azure resource**: ai có quyền thay đổi AKS cluster, node pool, network hoặc IAM qua Azure Resource Manager.
2. **Truy cập Kubernetes API**: ai được list, create, update, delete Kubernetes objects.
3. **Quyền của workload truy cập Azure services**: một pod có thể đọc Blob, lấy secret từ Key Vault hoặc gọi API khác hay không.

### 17.1. Microsoft Entra ID và Kubernetes RBAC

AKS có thể tích hợp Microsoft Entra ID để xác thực người truy cập cluster. Sau bước authentication, authorization có thể do **Kubernetes RBAC** hoặc **Azure RBAC for Kubernetes Authorization** đảm nhận, theo mô hình được chọn.

Đừng nhầm **Azure Contributor ở resource group** với quyền sửa tất cả Deployments trong cluster. Những quyền này thuộc các lớp khác nhau; khả năng lấy kubeconfig và phạm vi thao tác cần được cấu hình rõ.

### 17.2. Managed identities của cluster và kubelet

AKS sử dụng identity để tương tác với những Azure resources cần thiết. Có thể có **cluster identity** và **kubelet identity** cho các nhiệm vụ khác nhau. Chẳng hạn, quyền pull ACR của kubelet/node phải được cấp đúng principal và scope theo chế độ ACR authorization.

### 17.3. Workload Identity

**Microsoft Entra Workload ID** hỗ trợ workload trong Kubernetes lấy token qua liên kết danh tính giữa Kubernetes ServiceAccount và Microsoft Entra ID, trong cấu hình AKS được hỗ trợ.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant P as Pod
    participant SA as Kubernetes ServiceAccount
    participant EN as Microsoft Entra ID
    participant ST as Azure Storage
    P->>SA: Sử dụng identity đã cấu hình
    SA-->>P: Projected service account token
    P->>EN: Đổi token theo federated identity
    EN-->>P: Token cho Azure resource
    P->>ST: Gọi API với quyền được cấp
~~~

Cần cấu hình đúng OIDC issuer, federated credential, ServiceAccount, Azure identity và RBAC data-plane. Không phải chỉ bật một cờ trên cluster là mọi pod đều có quyền đọc Storage.

### 17.4. Secret management

Không đưa password, account key hay private key vào container image hoặc Git. Sử dụng managed identity, Key Vault và Secrets Store CSI Driver hoặc một phương án secrets management được phê duyệt. Kubernetes Secret có thể là một thành phần quản lý cấu hình nhưng vẫn cần bảo vệ quyền truy cập và cơ chế mã hóa theo thiết kế.

## 18. Azure Container Registry trong kiến trúc AKS

Ứng dụng cần image trước khi pods được tạo. Một luồng phổ biến:

~~~text
Source code -> CI build/test -> Azure Container Registry
                                  |
                                  v
                         AKS node pulls image
                                  |
                                  v
                             Kubernetes Pod
~~~

Quy trình:

1. Build image và kiểm thử.
2. Push lên ACR repository với tag rõ ràng.
3. Ghi lại manifest digest.
4. Cấp cho identity phù hợp quyền pull theo ACR RBAC/repository authorization model.
5. Cấu hình Deployment dùng image đã kiểm chứng.
6. Theo dõi pod events nếu pull thất bại.

**ImagePullBackOff** có thể xuất phát từ sai tag/digest, thiếu quyền, private endpoint DNS, firewall hoặc image không hỗ trợ kiến trúc CPU. Không tự bật ACR admin user để giải quyết mọi lỗi.

Production nên pin image bằng digest hoặc có cơ chế kiểm soát tag không bị ghi đè. Tag **latest** không phải bảo đảm về phiên bản mới nhất và có thể gây khác biệt giữa các môi trường.

## 19. Requests, limits và Kubernetes scheduling

Khi nhiều workloads cùng dùng cluster, **resources.requests** và **resources.limits** ảnh hưởng đến placement và cách container sử dụng CPU/memory.

- **CPU request:** lượng CPU scheduler dùng khi quyết định pod có thể đặt lên node hay không.
- **Memory request:** mức RAM scheduler tính cho placement.
- **CPU limit:** giới hạn CPU trong phạm vi cơ chế runtime, có thể gây throttling.
- **Memory limit:** vượt mức có thể khiến container bị OOMKilled.

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
~~~

Trong đó **100m CPU** tương đương 0,1 CPU core theo đơn vị Kubernetes. Đừng đặt request bằng 0 rồi trông chờ cluster autoscaler luôn tự hiểu nhu cầu thực.

### 19.1. Tại sao requests quan trọng?

Giả sử node còn 1 GiB RAM có thể cấp theo scheduler, còn một pod khai báo request 2 GiB: pod không được đặt vào node đó dù CPU có thể rảnh. Nếu không còn node phù hợp, pod **Pending**.

### 19.2. Tại sao limits cần đo?

Memory limit quá thấp làm Java JVM hoặc Node.js bị OOMKilled. CPU limit quá chặt có thể gây throttling và tăng độ trễ. Cần đo tải, Heap/GC, startup và mức RAM thực trước khi chốt.

### 19.3. Quota theo namespace

**ResourceQuota** và **LimitRange** có thể hạn chế tổng tài nguyên/giới hạn mặc định trong namespace. Chúng giúp giảm noisy neighbor nhưng không biến namespace thành ranh giới bảo mật độc lập.

## 20. Ba lớp autoscaling cần phân biệt

AKS thường có nhiều loại scaling ở những lớp khác nhau.

| Cơ chế | Thay đổi cái gì? | Tín hiệu điển hình |
|---|---|---|
| **Horizontal Pod Autoscaler (HPA)** | Số replicas của một workload | CPU, memory hoặc metric được hỗ trợ |
| **KEDA** | Số replicas theo event-driven workload | Queue length, event source hoặc custom scaler |
| **Cluster Autoscaler** | Số nodes của node pool được cấu hình | Pods Pending vì thiếu tài nguyên và điều kiện scale-in |
| **Node Auto Provisioning (nếu hỗ trợ)** | Cung cấp/chọn node capacity linh hoạt hơn | Nhu cầu scheduling và chính sách node provisioning |

### 20.1. HPA: thêm pods

Khi CPU của pods API tăng, HPA có thể yêu cầu Deployment tăng từ 2 lên 5 replicas. Nhưng nếu node pool không có đủ tài nguyên, các pod mới sẽ **Pending**.

### 20.2. Cluster Autoscaler: thêm nodes

Khi có pods Pending vì thiếu capacity và node pool có autoscale hợp lệ, Cluster Autoscaler có thể yêu cầu thêm nodes. Quá trình này mất thời gian VM provisioning.

### 20.3. KEDA: scale theo sự kiện

Worker xử lý Queue có thể cần mở rộng theo số messages hoặc độ trễ xử lý, thay vì CPU. KEDA có thể hữu ích khi được cài/bật và cấu hình trong cluster.

### 20.4. Thứ tự diễn ra

~~~mermaid
flowchart LR
    LOAD[Tải hoặc queue backlog tăng] --> HPA[HPA / KEDA tăng replicas]
    HPA --> SCHED{Đủ tài nguyên node?}
    SCHED -->|Có| PODS[Pods chạy]
    SCHED -->|Không| PENDING[Pods Pending]
    PENDING --> CA[Cluster Autoscaler / node provisioning]
    CA --> NODES[Node mới khởi động]
    NODES --> PODS
~~~

**Tăng replicas không đồng nghĩa hệ thống tăng ngay capacity phục vụ.** Cần đo cả thời gian scheduling, kéo image, startup/readiness và tình trạng hệ thống phụ thuộc.

## 21. Lưu trữ dữ liệu của workloads

Container filesystem thường không phải vị trí phù hợp để giữ dữ liệu bền vững. Một pod có thể bị thay thế hoặc chạy trên node khác.

| Kiểu dữ liệu | Giải pháp cân nhắc | Lưu ý |
|---|---|---|
| Cache/scratch có thể mất | emptyDir hoặc local ephemeral storage phù hợp | Có thể mất khi pod bị xóa/chuyển |
| Database volume hoặc file bền vững | PersistentVolume/PersistentVolumeClaim với Azure Disk CSI | Thường có ràng buộc zone, access mode và detach/attach |
| File dùng chung giữa pods | Azure Files CSI khi phù hợp | Cần cân nhắc protocol, latency, quyền và chi phí |
| Tệp object | Azure Blob Storage SDK hoặc tích hợp phù hợp | Không giống block/file filesystem thông thường |
| Secret | Key Vault/Workload Identity hoặc cơ chế được phê duyệt | Không lưu trong image hoặc file công khai |
| Logs cần giữ | Azure Monitor/Log Analytics hay nơi lưu tập trung | Pod có thể biến mất sau upgrade |

### 21.1. PersistentVolume và PersistentVolumeClaim

**PVC** mô tả nhu cầu dung lượng và access mode của workload. **StorageClass** xác định cách dynamic provisioning hoạt động; **CSI driver** kết nối Kubernetes với Azure storage.

Ví dụ với Azure Disk: một disk thường được gắn theo các ràng buộc access mode/node/zone nhất định, nên không thể mặc định nhiều pods ở nhiều nodes cùng ghi vào một volume như file share.

### 21.2. StatefulSet

**StatefulSet** cung cấp danh tính tương đối ổn định và mẫu volume cho từng replica, hữu ích với một số ứng dụng stateful. Nhưng đây không phải giải pháp tự động đồng bộ hoặc backup database. Nếu có thể, dùng dịch vụ dữ liệu managed phù hợp để giảm gánh nặng tự vận hành cluster stateful.

### 21.3. Backup và restore

Backup của YAML/Helm chart không đồng nghĩa đã sao lưu dữ liệu trong PV. Cần kế hoạch backup tài nguyên cluster, persistent volumes và database theo RPO/RTO. Có thể xem xét khả năng Azure Backup for AKS hoặc công cụ tương ứng khi hỗ trợ, nhưng luôn kiểm thử phục hồi thực tế.

## 22. Probes, Deployment và khả năng sẵn sàng

Kubernetes có các probes phổ biến:

- **Startup probe:** hữu ích với ứng dụng khởi động lâu; tránh liveness kết luận lỗi quá sớm.
- **Readiness probe:** quyết định pod có sẵn sàng nhận traffic qua Service hay không.
- **Liveness probe:** hỗ trợ phát hiện container cần khởi động lại.

Ví dụ API Java sau khi khởi động JVM cần tải cấu hình và kết nối database. Trong giai đoạn này, readiness có thể trả thất bại. Chỉ khi ứng dụng sẵn sàng mới trả thành công.

**Readiness và liveness không phải một.** Nếu liveness check phụ thuộc trực tiếp một dịch vụ bên ngoài đang lỗi, toàn bộ pods có thể bị restart không cần thiết và làm sự cố nghiêm trọng hơn.

### 22.1. Rolling updates

Một Kubernetes Deployment có thể thay pods từng đợt theo rolling strategy. Để giảm gián đoạn:

1. Giữ đủ replicas.
2. Thiết lập readiness đúng.
3. Cấu hình maxUnavailable/maxSurge phù hợp.
4. Xử lý SIGTERM và graceful shutdown.
5. Có capacity dự phòng và PDB phù hợp.
6. Kiểm tra error rate trong lúc rollout.

Rolling update không tự khắc phục database migration không tương thích. Khi rollout hai phiên bản ứng dụng cùng lúc, giao thức giữa các dịch vụ và schema phải có tính tương thích trong giai đoạn chuyển tiếp.

## 23. Nâng cấp AKS và vòng đời cluster

Kubernetes và OS node images cần được nâng cấp để duy trì khả năng hỗ trợ/bảo mật.

Các loại thay đổi:

- **Kubernetes control plane version:** thay đổi phiên bản API/control plane.
- **Node pool Kubernetes version:** cập nhật nodes theo điều kiện tương thích.
- **Node OS image:** cập nhật bản vá image của node.
- **Ứng dụng/Helm release:** cập nhật image và manifest của workload.
- **Add-ons/CSI/CNI:** nâng cấp các thành phần tích hợp có vòng đời riêng.

### 23.1. Quy trình nâng cấp an toàn

1. Kiểm tra phiên bản Kubernetes hiện tại và những phiên bản AKS hỗ trợ.
2. Đọc các deprecations/API removals có ảnh hưởng manifest hoặc controllers.
3. Kiểm tra add-ons, Helm charts và workload compatibility.
4. Nâng cấp môi trường staging tương tự production.
5. Bảo đảm system/user pools có capacity dự phòng.
6. Xem PDB, requests, quotas, topology spread và khả năng drain.
7. Chọn maintenance window, upgrade channel và surge settings theo khả năng hỗ trợ.
8. Theo dõi pods, node replacement, deployment health và metrics.
9. Kiểm thử ứng dụng thật sau nâng cấp.
10. Có phương án khôi phục khi upgrade không đạt; không mặc định có thể downgrade tùy ý Kubernetes cluster.

### 23.2. Không khóa cluster ở một bản cũ quá lâu

Để AKS chạy lâu trên phiên bản Kubernetes đã hết hỗ trợ làm tăng rủi ro bảo mật, lỗi tích hợp và khó nâng cấp nhiều bước. Cần lịch bảo trì và người chịu trách nhiệm cluster lifecycle.

## 24. Bảo mật cluster theo nhiều lớp

Một mô hình bảo mật AKS cần kiểm soát:

| Lớp | Biện pháp |
|---|---|
| **Subscription / ARM** | RBAC, Azure Policy, quản trị resource groups |
| **API server** | Private/public access phù hợp, Entra auth, authorized IP khi dùng public, audit |
| **Kubernetes permissions** | Least-privilege Roles/RoleBindings hoặc Azure RBAC for K8s |
| **Pods** | Non-root, hạn chế capabilities, không privileged nếu không cần, resource limits |
| **Images** | ACR, scanning, digest, provenance, admission policies |
| **Network** | NSG, Network Policy, firewall, private endpoints, TLS |
| **Secrets** | Managed identity, Key Vault, workload identity |
| **Node/OS** | Patch, security monitoring, disk encryption, runtime hardening |
| **Monitoring** | Audit logs, runtime alerts, incident response |
| **Data** | Backup, encryption, access controls và DR |

### 24.1. Admission controls và policies

Azure Policy for Kubernetes, admission controllers hoặc các chính sách tương ứng có thể giúp ngăn chạy container privileged, dùng image registry không được phép hoặc không khai báo security context. Tuy nhiên tính năng và mode enforcement phải được kiểm tra trước khi áp dụng production.

### 24.2. Không cấp cluster-admin cho mọi developer

Quyền cluster-admin có thể sửa hầu hết Kubernetes objects. Cần phân vai rõ:

- Platform team: quyền quản trị cluster có kiểm soát.
- Application team: chỉ sửa Deployment/Service của namespace được giao.
- CI identity: quyền deploy đúng scope.
- Runtime ServiceAccount: chỉ quyền tối thiểu trong Kubernetes và Azure.

### 24.3. Namespace không phải sandbox tuyệt đối

Một pod có đặc quyền host hoặc quyền Kubernetes quá rộng có thể ảnh hưởng cả cluster. Khi workload đến từ nhóm không tin cậy hoặc có yêu cầu tuân thủ rất khác nhau, cluster riêng hoặc isolation mạnh hơn có thể cần thiết.

## 25. Giám sát AKS bằng Azure Monitor và công cụ Kubernetes

Để phát hiện lỗi, cần quan sát ba cấp:

| Cấp | Cần theo dõi | Ý nghĩa |
|---|---|---|
| Cluster/control plane | API availability, upgrade/operation status | Phát hiện lỗi nền tảng/quản trị |
| Node pools/nodes | CPU, RAM, disk, node readiness, pressure | Xác định compute đang nghẽn |
| Pods/workloads | Restarts, OOMKilled, Pending, readiness, HTTP errors | Xác định lỗi ứng dụng |
| Autoscaling | HPA desired/actual replicas, Cluster Autoscaler events | Xác định vì sao không scale |
| Network | DNS, egress, ingress, policy drops | Khắc phục lỗi kết nối |
| Data | Database latency, PVC, CSI attach/mount errors | Khắc phục lỗi stateful |
| Security | Audit events, image scan findings, identity errors | Phát hiện thay đổi không mong muốn |
| Cost | Node hours, disks, LB/NAT, logs, egress | Tối ưu vận hành |

Các công cụ Azure có thể gồm Azure Monitor Container Insights, managed Prometheus/Azure Monitor metrics, Azure Managed Grafana và Log Analytics theo cấu hình/tính năng. Dù dùng sản phẩm nào, phải xác định retention, sampling, labels/cardinality và chi phí thu thập.

### 25.1. Lệnh chẩn đoán Kubernetes hữu ích

~~~bash
kubectl get nodes -o wide
kubectl get pods --all-namespaces
kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
~~~

Lệnh **--previous** hữu ích khi container đã restart và có log của lần chạy trước; không phải lúc nào dữ liệu đó cũng còn. Tránh đưa secrets hoặc dữ liệu nhạy cảm từ logs vào kênh công khai.

## 26. Mẫu quyết định: chọn một trong các kiến trúc cluster

Giả sử doanh nghiệp có API Java, worker đọc Queue, hệ thống dữ liệu và nhóm vận hành Azure.

### Phương án A — Một AKS Standard cluster cho production

~~~text
Production AKS
├── systempool (nhiều nodes ổn định)
├── apipool (API pods, HPA)
└── workerpool (Queue workers, KEDA nếu phù hợp)
    |
    +-- Azure Container Registry
    +-- Managed database
    +-- Azure Blob / Queue
    +-- Key Vault / Workload Identity
    +-- Azure Monitor
~~~

Phù hợp khi công ty có nền tảng Kubernetes rõ ràng, muốn quản lý riêng tính chất các node pools nhưng các ứng dụng có thể chia sẻ rủi ro và chính sách.

### Phương án B — Tách AKS production và non-production

~~~text
aks-nonprod
  - development namespaces
  - test workloads

aks-prod
  - production API/worker
  - stricter RBAC and ingress
  - independent upgrade window
~~~

Phù hợp khi rủi ro cấu hình thử nghiệm không được ảnh hưởng production. Đổi lại cần chi phí và vận hành nhiều hơn.

### Phương án C — AKS production nhiều regions

~~~text
Region A: AKS + ingress + application
Region B: AKS + ingress + application
        \     /
     Global traffic routing
        |
  Dữ liệu sao chép/khôi phục theo kiến trúc
~~~

Phù hợp khi RTO/RPO yêu cầu chịu lỗi toàn region. Không chỉ nhân bản Deployments là đủ: còn DNS, TLS, database, ACR image distribution, secrets, backup và khả năng tự phục vụ ở region B.

### Phương án D — Không dùng AKS

Nếu ứng dụng chỉ gồm vài container, cần autoscale mà không muốn vận hành node pools, cân nhắc **Azure Container Apps**. Nếu chỉ là web/API đơn giản, cân nhắc **App Service**. Nếu workload đặc thù cần kiểm soát OS, cân nhắc VMSS.

**Quy tắc chọn:** dùng mô hình ít phức tạp nhất nhưng vẫn đáp ứng đầy đủ yêu cầu vận hành, bảo mật, tăng trưởng và khả năng phục hồi.

## 27. Ma trận ra quyết định kiến trúc

| Tiêu chí | Cluster chia sẻ | Cluster riêng | Multi-region |
|---|---|---|---|
| Chi phí nền tảng | Thường thấp hơn | Cao hơn do nhiều clusters/pools | Cao nhất trong các phương án này |
| Cách ly thay đổi | Thấp hơn | Tốt hơn | Tách cả failure domain khu vực |
| Tự chủ nâng cấp | Nhiều team cùng phối hợp | Team có thể chọn window riêng | Cần điều phối hai regions |
| Compliance nghiêm ngặt | Cần chứng minh isolation | Thuận lợi hơn nếu yêu cầu tách mạnh | Còn phụ thuộc dữ liệu |
| Năng lực vận hành | Một platform team | Cần vận hành nhiều cụm | Cần DR và traffic routing |
| Dự phòng mất region | Không đủ | Không tự đủ | Có thể đáp ứng nếu toàn hệ được thiết kế |
| Hiệu quả sử dụng node | Dễ chia sẻ | Có thể phân mảnh | Cần capacity dự phòng hai nơi |

Cần đánh giá thêm: **Standard/Automatic**, **public/private API**, **system/user pools** và **networking mode**. Những lựa chọn này không loại trừ lẫn nhau; một doanh nghiệp có thể dùng nhiều cluster riêng, mỗi cluster private, với node pools đa zone.

### 27.1. Một quyết định ghi bằng ADR

Đối với kiến trúc quan trọng, nên ghi **Architecture Decision Record (ADR)** gồm:

- Bối cảnh và yêu cầu.
- Những phương án đã xem xét.
- Quyết định cùng lý do.
- Các trade-offs và điều kiện chưa đáp ứng.
- Người chịu trách nhiệm và ngày đánh giá lại.
- Cách kiểm chứng qua load test, security test và DR test.

Ví dụ: “Tách cluster production vì cần độc lập upgrade và chính sách RBAC; dùng Azure CNI Overlay để tiết kiệm VNet IP, áp dụng private API vì CI runner đã có mạng riêng; user pools chia API/worker vì đặc tính tải khác nhau.”

## 28. Tạo một AKS cluster thử nghiệm bằng Azure CLI

**Lưu ý:** ví dụ chỉ dành cho subscription và resource group được phép, có ngân sách lab. Tên region, SKU, tính năng mạng và CLI flags cần xác nhận theo phiên bản Azure CLI/AKS hiện hành trước khi chạy. Không tự thực thi những lệnh này trong bài viết.

Đăng nhập:

~~~bash
az login
az account set --subscription "<subscription-id>"
~~~

Tạo resource group:

~~~bash
az group create \
  --name rg-aks-architecture-lab \
  --location southeastasia
~~~

Ví dụ tạo cluster thử nghiệm với managed identity, 2 nodes và mạng Azure CNI Overlay:

~~~bash
az aks create \
  --resource-group rg-aks-architecture-lab \
  --name aks-architecture-lab \
  --node-count 2 \
  --node-vm-size Standard_D2s_v5 \
  --enable-managed-identity \
  --network-plugin azure \
  --network-plugin-mode overlay \
  --generate-ssh-keys
~~~

Giải thích:

- **--node-count 2:** số nodes khởi đầu, không phải số replicas ứng dụng.
- **--node-vm-size:** VM SKU phải có quota/capacity và đáp ứng yêu cầu cluster.
- **--enable-managed-identity:** dùng managed identity cho tích hợp Azure được hỗ trợ.
- **--network-plugin azure --network-plugin-mode overlay:** thể hiện một lựa chọn mạng để học, không phải lựa chọn đúng mặc định cho mọi doanh nghiệp.
- **--generate-ssh-keys:** phục vụ môi trường thử nghiệm theo cơ chế của CLI; production cần quản lý khóa phù hợp.

Lệnh tối giản trên **không cấu hình đầy đủ** network security, private API, Availability Zones, node pools bổ sung, workload identity, policy và monitoring production. Không nên dùng nguyên lệnh đó làm blueprint production.

### 28.1. Kết nối kubectl

~~~bash
az aks get-credentials \
  --resource-group rg-aks-architecture-lab \
  --name aks-architecture-lab

kubectl get nodes -o wide
kubectl get namespaces
kubectl get pods -n kube-system
~~~

Lệnh **get-credentials** có thể ghi/điều chỉnh kubeconfig cục bộ. Chỉ chạy trên máy người học/runner được phép và kiểm tra Kubernetes context trước mọi lệnh thay đổi:

~~~bash
kubectl config current-context
kubectl cluster-info
~~~

Không thực hiện thao tác xóa hoặc triển khai trước khi chắc chắn đang trỏ đúng cluster lab.

### 28.2. Xem node pools và cluster

~~~bash
az aks show \
  --resource-group rg-aks-architecture-lab \
  --name aks-architecture-lab \
  --query "{name:name,kubernetesVersion:kubernetesVersion,nodeResourceGroup:nodeResourceGroup}" \
  --output json

az aks nodepool list \
  --resource-group rg-aks-architecture-lab \
  --cluster-name aks-architecture-lab \
  --output table
~~~

Hãy quan sát node resource group và node pool. **Không chỉnh sửa VMSS/NIC ở node resource group theo cách thủ công** để đổi cluster; dùng AKS API/CLI tương ứng.

## 29. Triển khai thử một Deployment và Service

Một bài lab nên bắt đầu với workload không chứa dữ liệu nhạy cảm và không cần mở IP công khai.

Tạo namespace:

~~~bash
kubectl create namespace aks-lab
~~~

Nội dung minh họa của file **aks-demo.yaml**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-web
  namespace: aks-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: demo-web
  template:
    metadata:
      labels:
        app: demo-web
    spec:
      containers:
        - name: web
          image: nginx:stable
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "250m"
              memory: "128Mi"
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 2
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 5
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: demo-web
  namespace: aks-lab
spec:
  type: ClusterIP
  selector:
    app: demo-web
  ports:
    - port: 80
      targetPort: 80
~~~

**image: nginx:stable** chỉ dùng để minh họa ở lab. Trong production, cần pin digest hoặc tag bất biến đã kiểm chứng và kiểm soát nguồn image, không phụ thuộc tag có thể thay đổi.

Áp dụng manifest sau khi đã tạo file ở môi trường lab:

~~~bash
kubectl apply -f aks-demo.yaml

kubectl get deployments -n aks-lab
kubectl get pods -n aks-lab -o wide
kubectl get service -n aks-lab
kubectl rollout status deployment/demo-web -n aks-lab
~~~

Kiểm tra không cần tạo Public Load Balancer bằng cách port-forward:

~~~bash
kubectl port-forward -n aks-lab service/demo-web 8080:80
~~~

Tại terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/
~~~

Đây là đường thử nghiệm chỉ mở phiên chuyển tiếp từ máy đang chạy kubectl, không phải ingress production. Với private cluster, máy chạy kubectl phải có đường mạng vào API server và kết nối liên quan.

## 30. Thử replicas, HPA và quan sát scheduling

Tăng replicas thủ công:

~~~bash
kubectl scale deployment/demo-web \
  --replicas=3 \
  -n aks-lab

kubectl get pods -n aks-lab -o wide
~~~

Nếu cluster còn compute, ba pods sẽ được đặt trên nodes tương ứng; nếu thiếu capacity, một số pods có thể Pending.

### 30.1. HPA cơ bản

Nếu cluster cung cấp metrics API/metrics-server đúng cách:

~~~bash
kubectl autoscale deployment demo-web \
  --cpu-percent=60 \
  --min=2 \
  --max=5 \
  -n aks-lab

kubectl get hpa -n aks-lab
~~~

Ví dụ này cần CPU requests hợp lệ và metrics có dữ liệu. **HPA tăng pods, không tự tăng nodes** nếu node pool chưa có cơ chế autoscale/node provisioning phù hợp.

Nếu muốn thử cluster autoscaler, phải cấu hình autoscale cho đúng node pool được AKS hỗ trợ, đặt giới hạn min/max và theo dõi chi phí. Không bật scale-to-large mà không có quota, ngân sách và kế hoạch cleanup.

### 30.2. Kiểm tra một pod Pending

~~~bash
kubectl get pods -n aks-lab
kubectl describe pod <pending-pod-name> -n aks-lab
kubectl get events -n aks-lab --sort-by=.metadata.creationTimestamp
~~~

Tìm lý do như **Insufficient cpu**, **Insufficient memory**, thiếu node phù hợp, taints/tolerations không khớp hoặc thiếu volume. Không kết luận Azure “không tạo pod” nếu scheduler đã giải thích rõ lý do.

## 31. Bài thực hành kiến trúc: so sánh ba mô hình AKS

**Bối cảnh:** doanh nghiệp có hai API Java, một worker xử lý Queue và dữ liệu trong Azure SQL/Blob. Team đang cân nhắc từ Container Apps chuyển sang AKS vì cần policies và scheduling phức tạp hơn.

### Phần A — Thu thập yêu cầu

Lập bảng:

| Yêu cầu | Câu hỏi |
|---|---|
| Số ứng dụng | Bao nhiêu Deployment/Job/namespace? |
| Tải | Request/s, job/s, peak và thời gian startup? |
| Bảo mật | API private hay public? RBAC/Network Policy nào? |
| Dữ liệu | Stateful services, PVC hay managed database? |
| HA | Chịu mất node, zone hay region? |
| Vận hành | Team có kinh nghiệm Kubernetes, trực sự cố và nâng cấp? |
| Chi phí | Ngân sách nodes/pools, egress, logs, backup? |

### Phần B — Lựa chọn mô hình

Đề xuất ba phương án:

1. **Container Apps** cho phần ứng dụng đơn giản, giảm vận hành Kubernetes.
2. **Một AKS Standard hoặc Automatic cluster** nếu tính năng hỗ trợ, với namespaces và node pools phù hợp.
3. **Tách non-production/production AKS** nếu cần độc lập rủi ro và nâng cấp.

Chấm điểm theo bảo mật, mức độ kiểm soát, chi phí, tính sẵn sàng và năng lực đội ngũ. Không chọn “phương án nhiều thành phần nhất” làm đáp án mặc định.

### Phần C — Thiết kế sơ bộ AKS

Nếu chọn AKS:

1. Chọn region và yêu cầu Availability Zones.
2. Chọn API endpoint public có giới hạn hoặc private.
3. Quy hoạch VNet, node subnet, Pod CIDR, Service CIDR, DNS IP.
4. Chọn CNI và Network Policy phù hợp.
5. Chọn system/user pools, VM SKU và cơ chế autoscale.
6. Xác định managed identity, Entra integration và workload identity.
7. Chọn ingress, egress, ACR và đường đến database/private endpoints.
8. Chọn monitoring, backup, upgrade window và budget.
9. Viết sơ đồ các failure domains và kế hoạch xử lý mất node/zone.

### Phần D — Triển khai lab

1. Tạo AKS thử nghiệm theo mục 28, bảo đảm không sử dụng subscription production.
2. Xác nhận kubeconfig context và quan sát nodes, system pods.
3. Triển khai demo-web bằng Deployment/ClusterIP Service.
4. Kiểm tra readiness và port-forward.
5. Scale replicas từ 2 lên 3, quan sát scheduling.
6. Thử HPA nếu metrics hoạt động; phân biệt HPA và node autoscaler.
7. Mô phỏng một pod crash bằng cách xóa **pod của chính Deployment lab**, quan sát controller tạo pod thay thế; không xóa system pods.
8. Quan sát Event/Log để biết tác động.
9. Dọn namespace và tài nguyên lab theo quy trình được phép.

### Phần E — Báo cáo

Báo cáo gồm:

- Quyết định AKS hay Container Apps và lý do.
- Mô hình cluster đã chọn: Automatic/Standard nếu hỗ trợ, public/private, shared/dedicated.
- CNI, ingress, egress, node pools, Availability Zones.
- Đường xác thực và quyền workload.
- Chiến lược HPA/node autoscaling.
- Khả năng chịu lỗi, backup và DR.
- Dự toán chi phí.
- Kết quả của thử nghiệm scale/restart pod.

**Tiêu chí hoàn thành:** người học chứng minh được tại sao kiến trúc đáp ứng yêu cầu, thay vì chỉ có một cluster được tạo thành công.

## 32. Chi phí AKS: không chỉ là tiền cluster

Các khoản chi phí cần xem:

| Nhóm | Nguồn chi phí |
|---|---|
| **Control plane / service tier** | Tùy mức dịch vụ, SLA và mô hình AKS được chọn |
| **Compute** | Số nodes, VM size, operating system và thời gian chạy |
| **Disk/storage** | OS disks, PV/PVC, snapshots và backup |
| **Network** | Load Balancer, Public IP, NAT Gateway, Firewall, egress |
| **Registry** | ACR SKU, image storage và image build |
| **Monitoring** | Azure Monitor, Log Analytics, metrics và retention |
| **Data services** | Azure SQL, Cosmos DB, Blob/Queue, cache, Key Vault |
| **HA/DR** | Năng lực dự phòng giữa zones/regions, đồng bộ và failover |

Không phải cluster hết tải thì ngừng tính tiền: **node pools giữ minimum nodes vẫn phát sinh chi phí compute**, cùng các dịch vụ mạng, lưu trữ và monitoring.

### 32.1. Tối ưu chi phí không phá HA

- Dùng requests/limits dựa trên số liệu thực để tránh over-provision.
- Autoscale node pools cho workloads biến động.
- Tách system pools ổn định và user pools phù hợp.
- Chọn Spot cho batch có thể retry, không phụ thuộc Spot đơn lẻ cho thành phần quan trọng.
- Giảm image size và log ingestion không cần thiết.
- Hạn chế tạo cluster riêng không có nhu cầu cách ly tương ứng.
- Kiểm soát idle non-production theo giờ làm việc nếu chính sách cho phép.
- Thiết lập Azure Cost Management budgets và cảnh báo chi phí.

Không được cắt system nodes hoặc replicas xuống mức gây ngừng ứng dụng chỉ để giảm hóa đơn. Tối ưu chi phí phải xét cùng SLO và rủi ro.

## 33. Sự cố AKS thường gặp và cách phân loại

### 33.1. Không kết nối được kubectl

Kiểm tra Kubernetes context, quyền lấy credentials, Entra authentication, RBAC và đường mạng đến API server. Với private cluster, kiểm tra private DNS, VPN/ExpressRoute hoặc nơi chạy kubectl.

### 33.2. Pod Pending

Kiểm tra **kubectl describe pod**, CPU/memory requests, quota, taints/tolerations, node selectors, zone/volume constraints và autoscaler events.

### 33.3. ImagePullBackOff

Kiểm tra image registry, repository/tag/digest, ACR RBAC/ABAC, kubelet identity, DNS/firewall/private endpoint và platform image.

### 33.4. CrashLoopBackOff

Kiểm tra startup logs, command/args, secrets, resource limits, OOMKilled, health probes và database connectivity.

### 33.5. Service không truy cập được

Kiểm tra Service selector, endpoints, pod readiness, targetPort, Network Policy, ingress controller, NSG và Azure Load Balancer. Không suy luận lỗi DNS chỉ vì trình duyệt báo timeout.

### 33.6. DNS nội bộ lỗi

Kiểm tra CoreDNS pods, Service DNS, Network Policy, custom DNS forwarders, VNet DNS và đường đến private endpoints.

### 33.7. Scale không tăng

HPA có metrics không? Requests đã đặt chưa? Cluster autoscaler có bật và max node đủ lớn không? Subscription còn quota và subnet còn IP không? Node SKU/zone có capacity không?

### 33.8. Upgrade bị chặn

Kiểm tra PDB quá chặt, thiếu surge capacity, pods không chịu drain, node pool không thể tạo node mới hoặc workload cũ dùng Kubernetes API đã bị loại bỏ.

### 33.9. Dữ liệu mất sau khi pod bị tạo lại

Ứng dụng có thể đang ghi dữ liệu vào container filesystem/emptyDir thay vì PVC hoặc external storage. Kiểm tra data persistence và backup.

### 33.10. Cluster “healthy” nhưng người dùng vẫn lỗi

AKS status không phản ánh đầy đủ chất lượng API. Kiểm tra error rate, latency, database, ingress, DNS, TLS, external dependency và data layer.

## 34. Checklist trước khi đưa AKS vào production

- [ ] Đã xác minh AKS thực sự cần thiết so với Container Apps/App Service/VMSS.
- [ ] Đã chọn Standard/Automatic theo tính năng và trách nhiệm vận hành.
- [ ] Đã quyết định shared/dedicated và tách prod/non-prod theo rủi ro.
- [ ] Đã chọn public/private API server và kiểm tra đường CI/CD access.
- [ ] Đã thiết kế region, zones, fault domains và mục tiêu HA.
- [ ] Có system pool đủ capacity và user pools theo đặc tính workload.
- [ ] VNet, subnet, Pod CIDR, Service CIDR và DNS không chồng lấn.
- [ ] CNI, Network Policy, ingress và egress phù hợp với Azure networking.
- [ ] Azure RBAC/Kubernetes RBAC/Entra integration được kiểm soát.
- [ ] Workload identity, ACR pull và Key Vault được cấu hình đúng.
- [ ] Images được kiểm thử, scan và pin theo digest/tag bất biến.
- [ ] Workload có requests/limits, probes, replicas và PDB hợp lý.
- [ ] HPA/KEDA và node autoscaling có min/max/quota/budget.
- [ ] Stateful workloads có PV/PVC/CSI và backup khôi phục được.
- [ ] Có lịch nâng cấp Kubernetes/node OS và kiểm tra API deprecations.
- [ ] Có logging, metrics, alerts và runbook xử lý incident.
- [ ] Đã diễn tập lỗi pod, node và zone theo mức SLO.
- [ ] Có phương án DR đa region nếu RPO/RTO yêu cầu.
- [ ] Đã tính chi phí compute, disk, network, logs, ACR và backup.
- [ ] Hạ tầng được quản lý bằng IaC/GitOps hoặc quy trình triển khai có kiểm soát.

## 35. Câu hỏi tự kiểm tra

1. Control plane và worker nodes khác nhau ở trách nhiệm nào? Phần nào do Azure quản lý?
2. Namespace, node pool và resource group có giống nhau không?
3. Vì sao không nên sửa thủ công VMSS hoặc NIC trong node resource group của AKS?
4. AKS Standard và Automatic khác nhau về định hướng vận hành như thế nào?
5. Khi nào Azure Container Apps có thể phù hợp hơn AKS?
6. Vì sao nên cân nhắc cluster production riêng thay vì dùng chung với development?
7. Public Kubernetes API và public application ingress có phải cùng một quyết định không?
8. Khi chọn Azure CNI Overlay, bạn cần kiểm tra những dải địa chỉ và kết nối nào?
9. HPA và cluster autoscaler khác nhau ở đối tượng mở rộng gì?
10. Vì sao Deployment có 5 replicas nhưng chỉ 3 pods Running không nhất thiết là lỗi HPA?
11. System node pool phục vụ mục đích gì và tại sao không nên để batch jobs chiếm hết capacity?
12. Workload Identity liên hệ thế nào với Kubernetes ServiceAccount và Microsoft Entra ID?
13. Khi ACR image bị ImagePullBackOff, cần kiểm tra những lớp nào?
14. PersistentVolumeClaim giải quyết vấn đề gì mà emptyDir không giải quyết?
15. PDB giúp gì trong lúc node drain và giới hạn của nó là gì?
16. Vì sao rolling upgrade cần readiness, spare capacity và schema compatibility?
17. Một cluster đa zone có đảm bảo ứng dụng hoạt động khi database mất cả region không?
18. Các khoản chi phí chính của AKS nằm ở đâu khi không có lưu lượng người dùng?
19. Khi ứng dụng trả 5xx nhưng nodes Ready, cần điều tra gì?
20. Những yêu cầu nào khiến bạn chọn cluster riêng hoặc multi-region thay vì shared cluster?

## 36. Tổng kết

**Azure Kubernetes Service (AKS)** cung cấp Kubernetes được quản lý trên Azure, với control plane do nền tảng vận hành và các node pools chạy workloads của tổ chức. Thiết kế tốt cần hiểu rõ **control plane – node – pod – service**, trách nhiệm quản trị và vai trò của từng lớp.

Khi lựa chọn mô hình cluster, hãy bắt đầu từ nhu cầu thực tế: **AKS hay dịch vụ container đơn giản hơn; Standard hay Automatic; một cluster hay nhiều cluster; API public hay private; một region hay nhiều regions**. Sau đó thiết kế **node pools, Availability Zones, VNet/CNI, ingress/egress, identity/RBAC, storage, autoscaling, upgrade, monitoring và backup/DR** thành một hệ thống thống nhất.

Điều quyết định chất lượng kiến trúc không phải số lượng thành phần Kubernetes mà là khả năng **triển khai đúng phiên bản, bảo vệ dữ liệu, scale theo tải, xử lý mất node/zone, khôi phục sau sự cố và kiểm soát được chi phí**. Những quyết định này tạo nền tảng vững chắc cho các bài học AKS tiếp theo về triển khai workloads và vận hành cluster trên Azure.
