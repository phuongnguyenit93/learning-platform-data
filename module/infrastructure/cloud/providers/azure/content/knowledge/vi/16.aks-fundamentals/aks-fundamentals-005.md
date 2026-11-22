# Private cluster và quyền truy cập Kubernetes API

Azure Kubernetes Service (AKS) giúp vận hành Kubernetes trên Microsoft Azure mà không phải tự quản lý toàn bộ thành phần control plane. Tuy nhiên, một Kubernetes cluster không chỉ phục vụ người dùng ứng dụng: quản trị viên, pipeline CI/CD, công cụ GitOps và các bộ điều khiển cũng cần giao tiếp với **Kubernetes API server** để xem hoặc thay đổi trạng thái hệ thống. Nếu đường truy cập API và cơ chế phân quyền không được thiết kế cẩn thận, một danh tính bị xâm phạm có thể xem dữ liệu nhạy cảm, tạo workload mới, thay đổi cấu hình mạng hoặc chiếm quyền điều khiển cluster.

**AKS private cluster** là một lựa chọn giảm bề mặt truy cập của Kubernetes API bằng cách sử dụng kết nối riêng đến control plane thay vì yêu cầu quản trị Kubernetes qua một API endpoint công khai thông thường. Nhưng **private không đồng nghĩa với được cấp quyền**: sau khi có đường mạng hợp lệ, người gọi vẫn cần xác thực và được phép thực hiện từng hành động.

Bài học thuộc chương **Nền tảng Azure Kubernetes Service** của mô-đun CLOUD_PROVIDERS_AZURE. Nội dung kết nối AKS với subscription, resource group, Microsoft Entra ID, Azure RBAC, VNet, Private DNS, VPN/ExpressRoute, giám sát Azure Monitor, bảo mật và chi phí khi vận hành kiến trúc ứng dụng trên Azure.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Kubernetes control plane, Kubernetes API server, worker nodes, API endpoint và ứng dụng được publish qua ingress.
2. Giải thích cách một AKS private cluster hạn chế đường truy cập API và những giới hạn của mô hình này.
3. Thiết kế DNS và kết nối quản trị từ VM trong VNet, mạng peered, VPN/ExpressRoute hoặc private CI/CD runner.
4. Phân biệt ba vấn đề: **network reachability**, **authentication** và **authorization**.
5. Hiểu Microsoft Entra ID authentication, Azure RBAC for Kubernetes Authorization và Kubernetes native RBAC.
6. Tạo cluster thử nghiệm và kiểm tra cấu hình qua Azure CLI; lấy kubeconfig bằng kubelogin/kubectl ở môi trường được phép.
7. Thiết kế phân quyền namespace theo least privilege, tách identity runtime và quyền cluster.
8. Chẩn đoán lỗi DNS, TCP/TLS, 401, 403, cấp role, kubeconfig và sự cố CI/CD.
9. Xây dựng checklist giám sát, break-glass, thay đổi cấu hình, khôi phục và kiểm soát chi phí.

Các lệnh trong bài là ví dụ cho môi trường lab được cấp quyền, **không tự động chạy**. Khi triển khai thật, hãy đối chiếu SKU, region, tính năng và lựa chọn API server/networking theo tài liệu Azure hiện hành.

## 2. Control plane và Kubernetes API server

### 2.1. Kubernetes quản lý cluster qua API

Kubernetes dùng API server làm điểm vào cho các yêu cầu quản trị: tạo Deployment, đọc Pod, cập nhật ConfigMap, tạo RoleBinding, xem node và rất nhiều thao tác khác.

~~~mermaid
flowchart LR
    U["Admin / kubectl"] --> A["Kubernetes API server"]
    C["CI/CD hoặc GitOps"] --> A
    A --> E["Control plane: trạng thái cluster"]
    E --> N["Worker nodes / kubelet"]
    N --> P["Pods: ứng dụng"]
    X["Người dùng ứng dụng"] --> I["Ingress / Load Balancer"]
    I --> P
~~~

Các nhóm lưu lượng **không giống nhau**:

- **Quản trị Kubernetes:** kubectl, controller hoặc pipeline gửi request đến Kubernetes API server.
- **Ứng dụng:** người dùng truy cập website/API qua ingress, Service hoặc load balancer; không cần truy cập Kubernetes API.
- **Node và control plane:** kubelet, node components và các thành phần điều khiển trao đổi dữ liệu theo kiến trúc AKS.

Có thể có một AKS private cluster mà ứng dụng vẫn công khai qua ingress được bảo vệ. Ngược lại, một cluster có API endpoint public vẫn có thể chạy ứng dụng hoàn toàn nội bộ. **Private cluster không đồng nghĩa mọi Service hay ingress của ứng dụng đều private.**

### 2.2. Control plane được quản lý không có nghĩa bỏ qua quyền

AKS quản lý nhiều thành phần control plane, nhưng tổ chức vẫn cần:

- Định nghĩa ai được tạo và sửa cluster ở Azure management plane.
- Chọn mô hình xác thực người dùng và workload.
- Chọn chính sách phân quyền Kubernetes theo namespace và loại tài nguyên.
- Thiết lập VNet, DNS, egress, firewall và đường quản trị.
- Quản lý phiên bản Kubernetes, node pools, workloads và secrets theo trách nhiệm.
- Bật logging/auditing và quy trình ứng phó sự cố.

Control plane được quản lý bởi Azure không cho phép bỏ qua việc kiểm tra các yêu cầu vào Kubernetes API.

## 3. Public cluster, private cluster và các biến thể truy cập API

### 3.1. Public API endpoint

Ở mô hình AKS có API endpoint công khai, máy có kết nối mạng phù hợp có thể liên hệ endpoint qua Internet, sau đó vẫn phải vượt qua các bước xác thực và phân quyền.

Một cluster public có thể sử dụng **API server authorized IP ranges** hoặc các biện pháp bảo vệ khác để giới hạn địa chỉ nguồn khi tính năng được hỗ trợ. Tuy nhiên:

- Authorized IP ranges không biến endpoint thành private endpoint.
- Danh sách IP nguồn cần được quản lý khi egress/NAT của đội quản trị thay đổi.
- Lộ credential hoặc token vẫn là nguy cơ nếu kẻ tấn công có đường mạng được cho phép.
- Danh sách IP không thay thế Entra ID hoặc RBAC.

### 3.2. Private cluster

Với AKS private cluster, việc truy cập Kubernetes API được thiết kế qua một **đường private network**. Khả năng kết nối phụ thuộc kiểu API server/control plane networking đã chọn, hệ thống DNS và những VNet hoặc mạng hybrid được định tuyến đến private endpoint/địa chỉ API tương ứng.

~~~mermaid
flowchart LR
    O["Admin on-premises"] --> V["VPN / ExpressRoute"]
    J["Jump host / runner trong VNet"] --> VNET["VNet hoặc mạng kết nối"]
    V --> VNET
    VNET --> DNS["Private DNS resolution"]
    DNS --> API["Private AKS API endpoint"]
    API --> CP["Managed control plane"]
    CP --> NP["Node pool"]
    NP --> APP["Application Pods"]
    USER["Khách hàng ứng dụng"] --> INGRESS["App Ingress / LB độc lập"]
    INGRESS --> APP
~~~

**Private cluster bảo vệ đường vào API, không tự bảo vệ mọi thành phần khác**. Người có quyền trong một VM hoặc pod đã kết nối mạng tới API vẫn có thể thử xác thực. Do đó cần cả phân đoạn mạng, quản lý host/runner, xác thực mạnh, least privilege và audit.

### 3.3. Hai khái niệm cần phân biệt trong AKS

Tài liệu AKS có các mô hình triển khai API server phát triển theo thời gian, gồm private cluster dựa trên cơ chế kết nối riêng đến control plane và khả năng **API server VNet integration** ở những cấu hình được hỗ trợ.

Cần phân biệt:

- **Private cluster:** mục tiêu truy cập Kubernetes API qua private network.
- **API server VNet integration:** một kiểu tích hợp API server vào mạng ảo theo kiến trúc và điều kiện sản phẩm riêng; có thể kết hợp với lựa chọn private access theo tính năng hỗ trợ.
- **API endpoint public/private mode:** thuộc tính cần kiểm tra của cluster thực tế, không nên suy ra chỉ từ tên tính năng trong Portal.
- **Private DNS zone:** cơ chế phân giải tên API về private IP trong mạng có quyền kết nối.

Mẫu triển khai có thể khác nhau về tên Private DNS zone, IP API server, tài nguyên mạng và khả năng đổi chế độ sau tạo cluster. Đừng cố áp chính xác một mô hình legacy cho tất cả cluster mới; hãy kiểm tra các thuộc tính **apiServerAccessProfile, privateFqdn và networking mode** của cluster.

## 4. Ba lớp bắt buộc: mạng, xác thực, phân quyền

Một yêu cầu kubectl thành công phải vượt qua ba lớp độc lập:

~~~mermaid
flowchart TD
    K["kubectl / API client"] --> N{"1. DNS + mạng đến API OK?"}
    N -->|Không| NE["Timeout / DNS failure"]
    N -->|Có| A{"2. Xác thực hợp lệ?"}
    A -->|Không| AE["Unauthorized / login error"]
    A -->|Có| R{"3. Có quyền với verb/resource/scope?"}
    R -->|Không| RE["Forbidden (403)"]
    R -->|Có| OK["API chấp nhận yêu cầu"]
~~~

| Lớp | Câu hỏi | Hình thức kiểm tra |
|---|---|---|
| Network reachability | Client giải được FQDN và đi được đến TCP 443 của API không? | DNS, route, NSG/firewall, VPN/peering, TLS |
| Authentication | API biết caller là ai và token còn hợp lệ không? | Entra ID, kubelogin, token, service account hoặc cơ chế được hỗ trợ |
| Authorization | Caller có được phép gọi verb trên resource/namespace đó không? | Azure RBAC for Kubernetes Authorization hoặc Kubernetes native RBAC |

Ví dụ: kỹ sư có Azure Kubernetes Service RBAC Reader nhưng laptop không có đường VPN tới private endpoint sẽ thấy timeout, **không phải lỗi role**. Ngược lại, VM trong VNet kết nối TCP 443 thành công nhưng user không có quyền list pods sẽ nhận lỗi Forbidden.

Cần xử lý đúng lớp xảy ra lỗi, không cấp thêm role cluster-admin để chữa DNS hoặc mở API public để chữa lỗi 403.

## 5. Thiết kế mạng và Private DNS cho private AKS

### 5.1. Thành phần tham khảo

Giả sử một AKS production chạy trong mạng:

~~~text
Subscription: sub-platform-prod
Resource group: rg-aks-prod
Region: southeastasia

VNet: vnet-platform-prod         10.50.0.0/16
  snet-aks-nodes                 10.50.0.0/22
  snet-admin-tools               10.50.8.0/24
  snet-private-endpoints         theo quy hoạch nếu cần

On-premises: 172.20.0.0/16
  ↔ VPN hoặc ExpressRoute
  ↔ VNet/Hub có route và DNS phù hợp

AKS: aks-orders-private
  API access: private
  App ingress: thiết kế riêng, public hoặc private
~~~

Đây là sơ đồ CIDR minh họa. Trong mạng thực, phải kiểm tra overlap, subnet delegation, địa chỉ cần cho nodes/pods, network plugin, load balancer và quy hoạch hub-spoke.

**Private AKS API networking không phải cùng khái niệm với Pod networking.** Azure CNI, CNI Overlay và các cấu hình IP của pods ảnh hưởng đường mạng ứng dụng và nodes; private cluster chủ yếu mô tả cách client quản trị và control plane liên hệ API.

### 5.2. Private FQDN và DNS

AKS private cluster có một **private FQDN** cho Kubernetes API. Client cần phân giải tên này ra private IP hoặc đích mạng đúng theo kiểu triển khai.

Kiểm tra sau khi tạo cluster:

~~~bash
az aks show \
  --resource-group rg-aks-prod \
  --name aks-orders-private \
  --query "{fqdn:fqdn,privateFqdn:privateFqdn,api:apiServerAccessProfile}" \
  --output json
~~~

Tên Private DNS zone có thể liên quan miền azmk8s.io với dạng phụ thuộc kiểu cluster và vùng Azure. **Không hard-code một tên zone duy nhất** cho mọi trường hợp. Hãy lấy tên FQDN và zone thực tế được AKS tạo hoặc được cấu hình, rồi kiểm tra liên kết VNet/forwarding.

Từ client được phép truy cập:

~~~bash
nslookup <PRIVATE_AKS_FQDN>
~~~

Kết quả cần phù hợp với thiết kế private network. Nếu trả IP public không mong đợi, NXDOMAIN hoặc địa chỉ không định tuyến được, kubectl có thể thất bại trước khi tới bước xác thực.

### 5.3. Private DNS zone và VNet link

Có hai hướng vận hành phổ biến:

- **AKS-managed private DNS:** AKS quản lý một phần cấu hình DNS theo cơ chế dịch vụ được chọn.
- **Custom private DNS zone:** tổ chức tự quản lý zone, liên kết mạng và phân quyền tương ứng theo điều kiện AKS hỗ trợ.

Với custom DNS, cần:

1. Quy hoạch zone theo mô hình API server đang sử dụng.
2. Cấp cho identity của AKS những quyền cần thiết trên DNS zone/network theo hướng dẫn dịch vụ.
3. Tạo VNet link cho mạng truy vấn được phép.
4. Cấu hình DNS forwarder hoặc Azure DNS Private Resolver khi client dùng DNS doanh nghiệp.
5. Kiểm tra resolver từ từng phân đoạn mạng thực tế: nodes, jump host, runner và on-premises.
6. Theo dõi thay đổi zone/record và lưu runbook.

**Không tự sửa hoặc xóa DNS record do AKS quản lý** để xử lý lỗi một cách vội vàng. Điều này có thể làm mất kết nối quản trị hoặc ảnh hưởng đến hoạt động cluster.

### 5.4. Khi truy cập từ on-premises

Một người có VPN/ExpressRoute tới VNet chưa chắc đã truy cập được API private. Cần đủ cả:

- Route từ mạng on-premises tới private API IP/đích liên quan.
- Route quay về được thiết kế phù hợp.
- DNS forwarder cho private FQDN qua hạ tầng DNS tương ứng.
- Firewall/NSG cho phép TCP 443 tới endpoint.
- Client TLS trust và danh tính hợp lệ.

Nếu doanh nghiệp dùng custom DNS server ở data center, cấu hình conditional forwarding cho zone private qua cơ chế DNS được Azure hỗ trợ. Không gửi truy vấn nhạy cảm tới một DNS public rồi mong public resolver biết Private DNS zone của VNet.

### 5.5. Truy cập từ VNet peering và hub-spoke

Khi quản trị qua hub:

- Jump host hoặc runner có thể đặt ở hub VNet, AKS nodes ở spoke VNet.
- Cần route, peering và DNS link/forwarding đúng cả hai phía.
- NSG/Azure Firewall/NVA có thể chặn traffic dù hai VNet peered.
- Nếu dùng UDR hoặc inspection, phải bảo đảm đường tới API không bị blackhole.
- Không suy ra quyền đến API chỉ vì peering đã kết nối; DNS và security policy vẫn quyết định kết quả.

Nên kiểm thử từ **chính môi trường chạy kubectl**, không chỉ từ một VM bất kỳ trong cùng subscription.

## 6. Các phương án truy cập Kubernetes API an toàn

### 6.1. VM quản trị hoặc jump host trong mạng riêng

Một lựa chọn dễ kiểm soát là đặt một VM quản trị trong subnet được bảo vệ:

~~~text
Engineer → Azure Bastion/VPN → Jump VM → Private AKS API
~~~

Điều kiện tối thiểu:

1. Không mở SSH/RDP trực tiếp tới toàn Internet khi không cần.
2. VM được cập nhật, có EDR/host firewall, đăng nhập bằng danh tính được quản lý.
3. Chỉ nhóm quản trị phù hợp được quyền truy cập.
4. Không lưu kubeconfig/token lâu dài ở thư mục chia sẻ không được bảo vệ.
5. Audit phiên quản trị và dùng Azure RBAC/Kubernetes RBAC ở phạm vi cần thiết.
6. Cấu hình Private DNS và route tới API.

Azure Bastion giúp quản trị VM, **không phải proxy tự động cho mọi yêu cầu Kubernetes API**. Bạn vẫn cần từ VM đó có mạng tới private endpoint và quyền Kubernetes phù hợp.

### 6.2. VPN/ExpressRoute từ thiết bị doanh nghiệp

Kỹ sư có thể chạy kubectl từ laptop doanh nghiệp nếu:

- Thiết bị kết nối VPN hoặc mạng chuyên dụng được tổ chức cho phép.
- DNS riêng được phân giải qua đường mạng đó.
- Token Entra ID và Kubernetes permission hợp lệ.
- Firewall và route cho phép API TCP 443.

Cách này phù hợp khi tổ chức quản trị endpoint mạnh. Nếu VPN bị mất, kubectl có thể không liên hệ API dù Azure Portal và lệnh management plane vẫn hoạt động.

### 6.3. CI/CD runner ở private network

Pipeline GitHub Actions hoặc Azure DevOps sử dụng hosted runner **không mặc nhiên** nằm trong VNet của bạn. Nếu triển khai bằng kubectl/Helm trực tiếp tới private API, một runner công khai có thể thất bại vì không có đường mạng.

Mô hình thường phù hợp:

~~~mermaid
flowchart LR
    G["GitHub / Azure DevOps"] --> R["Self-hosted runner / private agent"]
    R --> D["Private DNS + VNet routes"]
    D --> A["Private AKS Kubernetes API"]
    A --> W["Deployments / Services"]
    I["Entra ID / federated identity"] -.-> R
~~~

Runner cần:

- Chạy ở subnet/VNet hoặc mạng kết nối có route tới private API.
- Có kết nối outbound tối thiểu tới hệ thống pipeline và các dịch vụ cần thiết.
- Sử dụng workload identity federation/OIDC hoặc managed identity khi được hỗ trợ thay vì lưu service principal secret dài hạn.
- Chỉ được cấp quyền deploy vào namespace được phép.
- Được cập nhật, tách biệt giữa nhóm dự án/mức tin cậy, không cho PR không được kiểm duyệt thực thi với quyền production.
- Ghi audit trail về commit, artifact, approval, kubectl action và kết quả rollout.

**Tách build khỏi deploy:** build/push image tới Azure Container Registry không nhất thiết đòi hỏi quyền tới private Kubernetes API. Chỉ bước deploy cần đường riêng tới cluster nếu sử dụng kubectl/Helm trực tiếp.

### 6.4. GitOps agent trong cluster

Với GitOps, một controller chạy **bên trong cluster** có thể theo dõi repository được phép và đồng bộ Kubernetes manifests. Điều này có thể giảm nhu cầu cho từng pipeline bên ngoài phải mở kết nối inbound tới Kubernetes API.

Tuy nhiên, controller GitOps cũng là workload có quyền thay đổi cluster:

- Dùng identity và quyền namespace tối thiểu.
- Bảo vệ Git source, branch, commit signing và approval.
- Kiểm soát egress tới Git/registry.
- Không nhúng admin kubeconfig vào repository.
- Giám sát drift và lệnh apply/delete ngoài dự kiến.

GitOps không loại bỏ yêu cầu Kubernetes authorization; nó chuyển một phần quyền triển khai tới service account/controller cần được quản trị.

### 6.5. AKS Run Command

AKS có khả năng thực hiện một số lệnh thông qua **az aks command invoke** ở các cấu hình được hỗ trợ, sử dụng Azure management plane và cơ chế thực thi của AKS. Điều này có thể hữu ích trong tình huống vận hành khi người điều khiển không có kết nối trực tiếp đến private API.

Ví dụ chỉ đọc:

~~~bash
az aks command invoke \
  --resource-group rg-aks-prod \
  --name aks-orders-private \
  --command "kubectl get namespaces"
~~~

**Cảnh báo:** cách này không tương đương một đường truy cập thấp quyền theo Kubernetes RBAC của cá nhân. Khả năng Run Command phụ thuộc Azure permissions, tính năng, cấu hình cluster và các giới hạn thực thi. Người được cấp quyền chạy lệnh có thể có mức tác động lớn tới cluster. Hãy quản lý quyền thao tác như quyền vận hành nhạy cảm, ghi audit và không dùng để né chính sách kết nối/least privilege thường ngày.

Không coi Run Command là phương án thay thế vĩnh viễn cho private runner hoặc đường quản trị được thiết kế rõ ràng.

## 7. Xác thực Kubernetes API với Microsoft Entra ID

### 7.1. Authentication là gì?

Khi một client kubectl gọi API, API server cần xác minh caller. Với **AKS tích hợp Microsoft Entra ID** được quản lý, người dùng có thể đăng nhập bằng danh tính Entra, và client nhận token hợp lệ theo luồng được nền tảng hỗ trợ.

Các thành phần chính:

- **Entra tenant:** nơi quản lý người dùng, nhóm và một số danh tính workload.
- **AKS cluster identity:** danh tính dùng để AKS tương tác với tài nguyên Azure; không đồng nghĩa danh tính người dùng kubectl.
- **kubectl/kubeconfig:** client và cấu hình endpoint/certificate/credential thực thi request.
- **kubelogin:** công cụ hỗ trợ đăng nhập và xử lý credential/token cho Kubernetes client tích hợp Entra ID ở những kịch bản hỗ trợ.
- **Kubernetes authorization:** quyết định người dùng đã xác thực có được thực hiện thao tác hay không.

### 7.2. Kubeconfig không phải tấm vé toàn quyền

Một file kubeconfig thường chứa:

- Tên cluster và API server URL.
- Cấu hình certificate/CA hoặc TLS.
- Context mặc định.
- Thông tin cách lấy hoặc sử dụng credential.

**Có kubeconfig chưa có nghĩa được toàn quyền**. Nếu người dùng không có role tương ứng, kubectl vẫn nhận Forbidden. Nếu client nằm ngoài private network, kubeconfig có đúng endpoint vẫn không kết nối được.

Kubeconfig và token được coi là dữ liệu nhạy cảm; giới hạn quyền truy cập file, không commit lên Git và không gửi trong ticket công khai.

### 7.3. Tích hợp Entra ID

Với AKS managed Entra ID integration, có thể dùng người dùng hoặc nhóm Entra làm chủ thể quản trị, thay vì phát credential cluster-admin dùng chung. Lợi ích:

- Có danh tính cá nhân và cơ chế xác thực tập trung.
- Có thể dùng MFA/Conditional Access/PIM theo điều kiện áp dụng.
- Tắt hoặc điều chỉnh thành viên nhóm khi nhân sự thay đổi.
- Ghi lại thông tin sign-in và hoạt động ở các nguồn log tương ứng.
- Tách nhóm read-only, namespace deployer và platform operator.

Tuy nhiên, cấu hình Entra authentication **không tự quyết định** các quyền đọc/ghi trong Kubernetes; cần chọn hệ thống authorization.

## 8. Hai lựa chọn phân quyền: Azure RBAC và Kubernetes native RBAC

Đây là phần dễ nhầm nhất khi quản trị AKS.

### 8.1. Azure management-plane RBAC

Azure RBAC ở management plane quyết định ai được tạo, đọc, cập nhật, xóa cluster hoặc gọi thao tác ARM như lấy user credentials.

Ví dụ role:

- **Azure Kubernetes Service Cluster User Role:** hỗ trợ lấy user kubeconfig/credentials theo quyền của role.
- **Azure Kubernetes Service Cluster Admin Role:** liên quan đến lấy admin credentials; đây là quyền nhạy cảm và không phải role đọc Kubernetes thông thường.

Các role management-plane này **không tự động** cấp quyền list/create/delete Pods trong một namespace dưới mô hình phân quyền Kubernetes. Cần phân biệt role lấy credential với role authorizing Kubernetes API.

### 8.2. Azure RBAC for Kubernetes Authorization

AKS có thể sử dụng **Azure RBAC for Kubernetes Authorization**, tức dùng cơ chế Azure role assignments để cấp quyền gọi Kubernetes API theo phạm vi được hỗ trợ.

Các role dữ liệu Kubernetes tiêu biểu:

| Role | Mục đích thường gặp | Lưu ý |
|---|---|---|
| Azure Kubernetes Service RBAC Reader | Xem một số loại tài nguyên Kubernetes được hỗ trợ | Không mặc định cho phép đọc secrets tùy định nghĩa role |
| Azure Kubernetes Service RBAC Writer | Tạo/sửa một số loại tài nguyên trong phạm vi được cấp | Không nên cấp toàn cluster cho pipeline chỉ deploy một namespace |
| Azure Kubernetes Service RBAC Admin | Quản trị nhiều tài nguyên Kubernetes trong phạm vi | Quyền cao; xem tài liệu chi tiết từng hành động |
| Azure Kubernetes Service RBAC Cluster Admin | Quyền quản trị Kubernetes ở phạm vi cluster | Chỉ cho nhóm platform rất hạn chế, có phê duyệt |

Tên role và các data actions chính xác phải được kiểm tra theo Azure hiện hành. Một role tên Writer không bảo đảm mọi Kubernetes verb/resource đều được cho phép. Nếu role không đáp ứng nghiệp vụ, thiết kế scope/role phù hợp theo khả năng, không mặc định cấp Cluster Admin để vượt lỗi 403.

### 8.3. Kubernetes native RBAC

Trong mô hình dùng **Kubernetes RBAC**, quyền được mô tả bằng:

- **Role:** danh sách resource/verb ở một namespace.
- **RoleBinding:** gắn Role hoặc ClusterRole với User/Group/ServiceAccount trong namespace.
- **ClusterRole:** mô tả quyền dùng toàn cluster hoặc tái sử dụng qua namespace.
- **ClusterRoleBinding:** gắn ClusterRole với chủ thể ở phạm vi cluster.

Khi Entra ID tích hợp để xác thực người dùng nhưng cluster dùng Kubernetes native RBAC, nhóm Entra có thể được ánh xạ theo định danh/nhóm mà AKS cung cấp, rồi RoleBinding xác định quyền. Cần kiểm tra định danh group object ID và cấu hình group claim phù hợp.

### 8.4. Không trộn hai mô hình mà thiếu chủ đích

Chọn mô hình authorization trong thiết kế cluster:

- Nếu dùng **Azure RBAC for Kubernetes Authorization**, quản trị user/group access qua Azure role assignments và scope theo cấu hình được hỗ trợ.
- Nếu dùng **Kubernetes native RBAC**, quản trị quyền bằng Role/RoleBinding/ClusterRole/ClusterRoleBinding. Entra ID vẫn có thể là hệ thống xác thực người dùng.
- Service accounts và controllers có cơ chế cấp quyền riêng trong Kubernetes; không nghĩ một Entra role assignment tự thay thế tất cả việc kiểm soát quyền cho Pods.

Dù dùng mô hình nào, kiểm tra bằng hành động thực tế trong đúng namespace. Một số phép kiểm tra kubectl auth can-i có hành vi phụ thuộc loại authorizer và cấu hình, nên cần đối chiếu kết quả với request thật hoặc audit log nếu phát sinh khác biệt.

### 8.5. Ma trận quyền cho một ứng dụng

Giả sử namespace orders có ba nhóm:

| Chủ thể | Quyền nên có | Không nên có |
|---|---|---|
| Nhóm quan sát ứng dụng | Xem pod/deployment/events ở namespace orders | Đọc secrets, sửa workload, sửa cluster |
| Pipeline orders | Cập nhật Deployment/Service/ConfigMap cần thiết trong orders theo policy | Tạo ClusterRoleBinding, chỉnh namespace khác |
| Platform operator | Quản lý những cấu hình cluster cần thiết với PIM/approval | Dùng tài khoản dùng chung không audit |
| Ứng dụng chạy trong Pod | Chỉ quyền Kubernetes API thật sự cần, nhiều ứng dụng không cần | Tự động mount token với quyền cao hoặc cluster-admin |
| Auditor | Xem thông tin cấu hình và logs phù hợp | Thao tác sửa/xóa production |

Không nên dùng nhóm Entra là **Global Administrator** làm phương pháp cấp quyền cho Kubernetes API. Quyền ở tenant, Azure subscription và Kubernetes cluster là những phạm vi khác nhau.

## 9. Thực hành 1: tạo AKS private cluster trong lab

Ví dụ dưới đây nhằm giải thích chuỗi bước. Cần quota, quyền Azure, subnet đúng kích thước, network policy và dự toán chi phí. Một cluster private có thể không truy cập được từ laptop nếu bạn chưa có VM hoặc private runner trong mạng.

### 9.1. Xác định subscription và tạo mạng lab

Ví dụ Bash:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az group create \
  --name rg-aks-lab \
  --location southeastasia

az network vnet create \
  --resource-group rg-aks-lab \
  --name vnet-aks-lab \
  --location southeastasia \
  --address-prefixes 10.50.0.0/16 \
  --subnet-name snet-nodes \
  --subnet-prefixes 10.50.0.0/22
~~~

Đây là mạng minh họa. Môi trường production phải tính đủ IP nodes/pods, địa chỉ services, Kubernetes network plugin, outbound connectivity, UDR và subnet khác. Không sử dụng CIDR trùng mạng kết nối hybrid.

Lấy resource ID của subnet:

~~~bash
SUBNET_ID=$(az network vnet subnet show \
  --resource-group rg-aks-lab \
  --vnet-name vnet-aks-lab \
  --name snet-nodes \
  --query id --output tsv)

echo "$SUBNET_ID"
~~~

Khi chạy thực tế, hãy xác minh ID thuộc đúng subscription/VNet và identity được cấp quyền cần thiết trên subnet. Không đưa role Owner toàn subscription chỉ để sửa lỗi cấp subnet.

### 9.2. Tạo cluster dùng Entra ID và Azure RBAC authorization

Ví dụ:

~~~bash
az aks create \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --location southeastasia \
  --node-count 2 \
  --node-vm-size Standard_D2s_v5 \
  --network-plugin azure \
  --vnet-subnet-id "$SUBNET_ID" \
  --enable-managed-identity \
  --enable-private-cluster \
  --enable-aad \
  --enable-azure-rbac \
  --disable-local-accounts \
  --generate-ssh-keys
~~~

Các lựa chọn quan trọng:

- **--enable-private-cluster:** yêu cầu API server private theo kiểu triển khai AKS được hỗ trợ.
- **--enable-aad:** bật tích hợp Microsoft Entra ID cho xác thực Kubernetes phù hợp với version AKS/CLI.
- **--enable-azure-rbac:** lựa chọn Azure RBAC for Kubernetes Authorization thay vì mặc định chỉ dùng Kubernetes native authorization.
- **--disable-local-accounts:** hạn chế cơ chế local admin/user credentials; chỉ dùng khi tổ chức có phương án Entra/RBAC và break-glass phù hợp.
- **--enable-managed-identity:** sử dụng managed identity cho cluster.
- **--vnet-subnet-id:** sử dụng subnet đã chuẩn bị.
- **--network-plugin azure:** ví dụ network plugin; chọn network mode/overlay theo thiết kế thực tế.

Không coi mọi flag ở ví dụ là mặc định tốt cho tất cả cluster. API server VNet integration, private DNS zone, outbound type, Azure CNI Overlay, node OS, SKU và network policy là những quyết định kiến trúc riêng. Tham khảo kết quả kiểm tra tính năng theo version trước khi chạy.

**Quan trọng:** vô hiệu hóa local accounts có thể khiến lối truy cập bằng admin kubeconfig không còn dùng được. Cần thử đăng nhập Entra và role assignments trước khi áp chính sách hạn chế production.

### 9.3. Xác minh thuộc tính private

~~~bash
az aks show \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --query "{name:name,private:apiServerAccessProfile.enablePrivateCluster,privateFqdn:privateFqdn,api:apiServerAccessProfile,identity:identity.type}" \
  --output json
~~~

Mục tiêu là xác nhận cluster báo private mode và có private FQDN theo mô hình tương ứng. Một số field có thể null hoặc được biểu diễn khác theo kiểu API integration/phiên bản AKS. Nếu không như kỳ vọng, kiểm tra kiểu triển khai thực tế, không tự suy luận ngay cluster bị lỗi.

### 9.4. Chuẩn bị máy chạy kubectl

Bạn cần một VM/runner từ mạng được phép đi tới private API, với:

- Azure CLI đã đăng nhập qua Entra ID.
- kubectl và kubelogin phù hợp với cluster/client.
- DNS phân giải đúng private FQDN.
- TCP 443 tới API endpoint được cho phép.
- Người hoặc identity có quyền lấy kubeconfig và quyền Kubernetes tương ứng.

Không cần tạo public IP cho Kubernetes API chỉ để lab. Có thể dùng một VM quản trị trong VNet hoặc mạng peered/VPN thích hợp, nhưng phải chuẩn bị đường quản trị tới VM và giải pháp cập nhật phần mềm.

## 10. Thực hành 2: lấy kubeconfig và xác thực

### 10.1. Kết nối từ môi trường có mạng riêng

Trên VM/runner đã chuẩn bị, kiểm tra FQDN:

~~~bash
PRIVATE_FQDN=$(az aks show \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --query privateFqdn --output tsv)

echo "$PRIVATE_FQDN"
nslookup "$PRIVATE_FQDN"
~~~

Nếu hostname không phân giải ra địa chỉ phù hợp private API, hãy xử lý DNS trước. Không cần thử cấp role cho tới khi đường mạng có khả năng kết nối.

Đối với TCP 443, trên Linux có thể dùng:

~~~bash
nc -vz "$PRIVATE_FQDN" 443
~~~

Trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName "<PRIVATE_AKS_FQDN>" -Port 443
~~~

Kiểm tra TCP chỉ cho thấy khả năng đi mạng; nó không chứng minh authentication/authorization đã đạt.

### 10.2. Lấy user kubeconfig

~~~bash
az aks get-credentials \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --overwrite-existing
~~~

Lệnh này lấy cấu hình credential qua Azure management plane theo quyền của người gọi. Nó **không bảo đảm client đang có kết nối tới private Kubernetes API**. Vì vậy có thể lấy kubeconfig thành công rồi kubectl vẫn timeout khi chạy ngoài VNet.

Nếu cluster dùng Entra ID và kubeconfig có exec plugin, cấu hình kubelogin theo phiên bản client phù hợp:

~~~bash
kubelogin convert-kubeconfig -l azurecli
~~~

Cách này dùng Azure CLI login cho kubelogin trong kịch bản hỗ trợ; các môi trường CI/CD có thể dùng phương thức khác theo danh tính workload. Không dùng interactive login người thật làm credential lâu dài cho automation production.

Kiểm tra context:

~~~bash
kubectl config current-context
kubectl config view --minify
~~~

Lệnh config view có thể chứa thông tin nhạy cảm tùy kubeconfig; không đăng output đầy đủ vào log CI hoặc ticket. Hãy tránh dùng --raw khi chia sẻ.

### 10.3. Kiểm tra quyền với kubectl

~~~bash
kubectl get namespaces
kubectl get pods -n orders
kubectl auth can-i list pods -n orders
kubectl auth can-i create deployments -n orders
~~~

Những lệnh này chỉ thành công khi namespace tồn tại, network hoạt động và identity có đủ quyền. Với người đọc ở phạm vi namespace, việc list namespaces có thể bị Forbidden trong khi list pods ở namespace được cấp vẫn thành công; đây là một trường hợp phân quyền **đúng**, không nhất thiết là lỗi cluster.

Không sửa bằng cách cấp cluster-admin chỉ để mọi lệnh trên đều chạy thành công. Điều cần kiểm tra là hành động nào thuộc nhiệm vụ thực tế của người dùng.

### 10.4. Tránh sử dụng admin credentials thường ngày

Một số cluster có thể cho phép lệnh lấy admin credentials bằng tùy chọn admin tùy cấu hình. Nếu local accounts bị disable hoặc chính sách không cho phép, cơ chế này có thể không hoạt động.

Ngay cả khi khả dụng, admin credentials có khả năng quyền rất cao và giảm khả năng phân biệt từng danh tính trong audit. Nên dùng Entra-authenticated user credentials, role assignments phù hợp và quy trình đặc quyền tạm thời.

## 11. Thực hành 3: cấp quyền Azure RBAC theo namespace

Giả sử tổ chức có nhóm Entra ID được phép **chỉ đọc** workload trong namespace orders.

### 11.1. Xác định cluster resource ID

~~~bash
AKS_ID=$(az aks show \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --query id --output tsv)

echo "$AKS_ID"
~~~

Lấy object ID của nhóm Entra được phê duyệt từ hệ thống quản trị danh tính. Không đoán theo tên hiển thị vì có thể có nhóm trùng tên hoặc nhóm chưa được cấp quyền trong tenant.

### 11.2. Quyền lấy user kubeconfig

Một nhóm vận hành có thể cần role lấy kubeconfig khi chưa có role management-plane khác đã cấp hành động đó:

~~~bash
az role assignment create \
  --assignee-object-id "<ENTRA_GROUP_OBJECT_ID>" \
  --assignee-principal-type Group \
  --role "Azure Kubernetes Service Cluster User Role" \
  --scope "$AKS_ID"
~~~

Role này liên quan việc lấy user credentials, **không nên nhầm với quyền list Pods ở Kubernetes API**.

### 11.3. Quyền đọc namespace orders

Với cluster bật Azure RBAC for Kubernetes Authorization, có thể cấp role dữ liệu ở scope namespace được hỗ trợ:

~~~bash
az role assignment create \
  --assignee-object-id "<ENTRA_GROUP_OBJECT_ID>" \
  --assignee-principal-type Group \
  --role "Azure Kubernetes Service RBAC Reader" \
  --scope "$AKS_ID/namespaces/orders"
~~~

Namespace orders phải được tạo bởi người có quyền trước khi người đọc thực hiện bài kiểm tra. Scope cú pháp và quyền thực tế của role phải được xác minh theo mô hình Azure RBAC của cluster. Không cấp vai trò ở toàn cluster chỉ vì lệnh scope namespace bị gõ sai.

Có thể liệt kê role assignments (dữ liệu đầu ra tùy quyền người đọc):

~~~bash
az role assignment list \
  --scope "$AKS_ID" \
  --include-inherited \
  --output table
~~~

Để xem role ở namespace scope, dùng đúng scope namespace khi cần; một lệnh query chỉ scope cluster không mặc nhiên cho bạn toàn bộ thông tin các scope con.

### 11.4. Xác nhận least privilege

Đăng nhập bằng thành viên nhóm được phép, từ máy có đường mạng riêng:

~~~bash
kubectl get pods -n orders
kubectl auth can-i get deployments -n orders
kubectl auth can-i delete deployments -n orders
kubectl auth can-i get pods -n kube-system
~~~

Kỳ vọng người đọc được phép xem thông tin phù hợp trong orders, nhưng không được xóa Deployment hoặc xem những namespace ngoài scope. Nếu kết quả bất thường, kiểm tra role assignment, token refresh, nhóm Entra và cấu hình authorizer. Thay đổi role có thể cần thời gian để phản ánh; đừng mặc định hiệu lực tức thời.

**Lưu ý bảo mật:** quyền đọc một số loại tài nguyên Kubernetes có thể gián tiếp cho phép suy ra cấu hình, tên image và tham số workload. Không cấp quyền đọc secrets hoặc quyền exec vào Pods khi không cần.

## 12. Ví dụ Kubernetes native RBAC để đối chiếu

Nếu cluster sử dụng **Kubernetes RBAC authorization**, không sử dụng ví dụ Azure RBAC ở trên để thay thế các RoleBinding dưới đây. Hai cơ chế cần được chọn chủ đích.

### 12.1. Namespace Role read-only

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-observer
  namespace: orders
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "services", "events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch"]
~~~

Role này không có quyền xem secrets, sửa workload hoặc quản trị cluster.

### 12.2. Gắn Role với nhóm Entra

Trong mô hình Entra authentication kết hợp Kubernetes native RBAC, và sau khi xác minh định dạng group identity của cluster:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-observers
  namespace: orders
subjects:
  - kind: Group
    name: "<ENTRA_GROUP_OBJECT_ID>"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: orders-observer
  apiGroup: rbac.authorization.k8s.io
~~~

Nếu cluster xuất group claims theo một định dạng khác, phải cấu hình subject đúng định danh thực tế; không giả định display name của group có thể dùng thay object ID.

Tác dụng của RoleBinding bị giới hạn tại namespace orders. Một ClusterRoleBinding với role cao có thể mở rộng quyền trên toàn cluster và cần được quản lý như thao tác đặc quyền.

### 12.3. Quyền của ServiceAccount trong Pod

Một ứng dụng thông thường chỉ phục vụ HTTP và truy cập database **không nhất thiết phải gọi Kubernetes API**. Khi không cần, cân nhắc vô hiệu hóa tự động mount service account token:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-example
  namespace: orders
spec:
  automountServiceAccountToken: false
  containers:
    - name: app
      image: "<APPROVED_REGISTRY>/orders-api:<VERSION>"
~~~

Manifest trên là ví dụ ý tưởng Pod; muốn chạy thật cần image hợp lệ, resource requests/limits, security context và các trường ứng dụng theo policy. Không đánh đồng Kubernetes ServiceAccount token với **Azure Workload Identity**: khi Pod cần gọi Azure Key Vault/Storage, có thể dùng Microsoft Entra Workload ID theo cấu hình riêng, nhưng quyền Azure đó không mặc nhiên cấp quyền Kubernetes API.

## 13. CI/CD và GitOps: nguyên tắc đặc quyền tối thiểu

### 13.1. Ba danh tính khác nhau

Trong một pipeline deploy container:

1. **Build identity:** lấy source/build image/push vào Azure Container Registry.
2. **Deploy identity:** cập nhật Kubernetes manifests trong namespace được phép.
3. **Runtime identity:** Pod truy cập Key Vault, Storage, Event Hub hoặc dịch vụ nghiệp vụ.

Các danh tính này nên được tách để giảm blast radius. Ví dụ runtime Pod chỉ cần đọc secret từ Key Vault không có lý do được phép tạo ClusterRoleBinding.

### 13.2. Ví dụ pipeline deploy an toàn

~~~text
Pull request / code review
          |
          v
CI build + test + image scan
          |
          v
ACR image digest được duyệt
          |
          v
CD approval
          |
          v
Private runner có VNet/DNS đến AKS API
          |
          v
Entra auth + namespace-scoped RBAC
          |
          v
kubectl/Helm deploy vào orders
          |
          v
Rollout status + app health + audit log
~~~

Các điều kiện quan trọng:

- Không cấp quyền deploy production cho pipeline chạy code từ PR không được kiểm duyệt.
- Sử dụng OIDC/workload identity federation hoặc managed identity khi công cụ cho phép.
- Build artifact một lần, ghi commit SHA và image digest.
- Lưu kubeconfig ngắn hạn ở workspace riêng có kiểm soát, không commit hoặc in token vào logs.
- Không sử dụng cùng quyền cluster-admin cho tất cả môi trường.
- Tách phê duyệt deployment khỏi quyền merge khi yêu cầu kiểm soát cao.
- Giám sát role assignment, ClusterRoleBinding và thay đổi namespace.

### 13.3. Rủi ro của Helm chart và manifest

Một chart có thể chứa ClusterRole, ClusterRoleBinding, CRD hoặc webhook ở phạm vi cluster. Nếu pipeline chỉ được cấp quyền namespace, những thao tác này có thể bị từ chối **đúng theo chính sách**.

Không mở toàn quyền chỉ vì helm install cần nhiều quyền. Thay vào đó:

- Platform team cài đặt CRDs/controllers chung qua quy trình riêng.
- Application team chỉ triển khai workload namespace-scoped.
- Sử dụng chart đã được review để tránh tạo tài nguyên ngoài phạm vi.
- Kiểm tra helm template hoặc manifest trước khi apply, đặc biệt quyền RBAC và admission webhook.

## 14. Giám sát, audit và quản lý thay đổi

### 14.1. Cần giám sát hai mặt phẳng

| Mặt phẳng | Nguồn tín hiệu | Dùng để làm gì |
|---|---|---|
| Azure management plane | Azure Activity Log, AKS resource changes, Azure role assignments | Ai tạo/sửa cluster, thay đổi network, identities và RBAC ở Azure |
| Kubernetes API/data plane | Kubernetes audit logs theo khả năng AKS diagnostic settings | Ai gọi verb trên resource/namespace, request có được chấp nhận không |
| Identity | Entra sign-in/audit logs | Danh tính đăng nhập và thay đổi nhóm/quyền liên quan |
| Cluster operation | Azure Monitor, Container insights, node/pod health | API/cluster và workloads có khỏe không |
| Network | DNS queries theo hệ thống có log, firewall, VPN/ER, Network Watcher | Có sự cố phân giải tên hoặc mất kết nối private API không |
| CI/CD | Runner/pipeline logs, approval, commit và image digest | Artifact nào được đưa vào cluster bởi ai |
| Security posture | Defender for Cloud và policy evaluation khi bật | Cấu hình thiếu an toàn, quyền quá rộng, image rủi ro |

**Azure Activity Log không thay thế Kubernetes audit logs.** Nó thường ghi các thao tác management plane, không mặc nhiên chứa mọi lệnh kubectl get/apply/delete trong cluster. Muốn điều tra Kubernetes API cần bật và thu thập log phù hợp trước khi xảy ra sự kiện, theo khả năng và mức độ lưu trữ của AKS.

### 14.2. Diagnostic settings và chi phí log

Tại thời điểm triển khai, xem các log categories được AKS hỗ trợ như kube-audit, kube-audit-admin hoặc các nhóm log control plane khác. Chọn loại log phù hợp yêu cầu bảo mật, mức chi tiết và chi phí ingest/retention.

- kube-audit có thể rất nhiều sự kiện và tạo chi phí lớn.
- Các nhóm log audit rút gọn tập trung một số loại thao tác; cần xác minh nội dung/giới hạn trước khi dùng cho kiểm toán.
- Phân quyền Log Analytics workspace và retention theo chính sách tổ chức.
- Khi xuất log tới Storage/Event Hub/Log Analytics, kiểm tra dữ liệu thực sự đến nơi.
- Không lưu token hoặc secret từ audit/log output ra nơi công khai.

Có thể dùng Azure Monitor Alert và Microsoft Sentinel nếu đã triển khai để phát hiện thay đổi quyền, thao tác nhạy cảm hoặc hành vi API bất thường.

### 14.3. Sự kiện đáng cảnh báo

1. Thêm role assignment Kubernetes Cluster Admin hoặc quyền nhạy cảm ở Azure.
2. Tạo ClusterRoleBinding cấp cluster-admin trong Kubernetes native RBAC.
3. Vô hiệu hóa hoặc thay đổi cơ chế xác thực/bảo mật của cluster.
4. Thay đổi private DNS zone, VNet link, API endpoint mode hoặc firewall.
5. Chỉnh sửa namespace kube-system hoặc các controllers quan trọng ngoài change window.
6. Gọi Kubernetes API từ danh tính chưa được phê duyệt hoặc mẫu truy cập bất thường.
7. CI/CD runner mất kết nối API, deploy liên tục thất bại hoặc đột ngột sử dụng identity khác.
8. Tăng lỗi API/timeout, network/DNS hoặc node không Ready.

Cần thiết kế ngưỡng và nguồn log thực tế; không xem một alert được cấu hình là bằng chứng chắc chắn mọi sự kiện đã được theo dõi.

## 15. Sự cố thường gặp và cách xử lý

### 15.1. Bảng chẩn đoán nhanh

| Triệu chứng | Lớp có khả năng lỗi | Hướng kiểm tra |
|---|---|---|
| kubectl: lookup host failed / NXDOMAIN | DNS | Private FQDN, zone/link, resolver và conditional forwarding |
| kubectl: i/o timeout | Network | VNet/peering, VPN, UDR, firewall, TCP 443, route quay về |
| x509: certificate signed by unknown authority | TLS/client | Kubeconfig CA data, FQDN, proxy/TLS inspection, clock |
| HTTP 401 Unauthorized | Authentication | Entra login, kubelogin, token expiry, tenant, kubeconfig |
| HTTP 403 Forbidden | Authorization | Azure RBAC/Kubernetes RBAC, scope, nhóm, verb/resource |
| az aks get-credentials thành công nhưng kubectl fail | Private endpoint hoặc quyền data plane | Kiểm tra DNS/TCP rồi token/role, không chỉ ARM quyền |
| Không lấy được kubeconfig | Azure management-plane permission | Cluster User Role, scope, tenant/subscription |
| Lệnh lấy admin credentials bị từ chối | Local accounts disabled hoặc thiếu quyền | Kiểm tra policy và quy trình break-glass |
| CI hosted runner không deploy được | Runner không có private route | Dùng private agent/VNet integration theo mô hình hỗ trợ |
| Azure role assignment mới nhưng vẫn 403 | Delay/token/groups/scope | Refresh login, xác minh identity và namespace scope |
| User xem pods được nhưng không xem namespaces | Quyền namespace-scoped hợp lệ | Không mở rộng quyền nếu nghiệp vụ không yêu cầu |
| kubectl ở jump host chạy, ở on-premises fail | DNS/route/firewall phía hybrid | Kiểm tra đúng mạng nguồn và private DNS forwarding |
| AKS không tạo được với custom DNS | Identity thiếu quyền zone hoặc cấu hình zone không hợp lệ | Quyền DNS zone, VNet link, feature prerequisites |
| API chạy nhưng nodes NotReady | Sự cố network/egress/runtime khác | Kiểm tra node pool, outbound dependencies, CNI và logs |

### 15.2. Quy trình kiểm tra tuần tự

**Bước 1 — Xác nhận cluster và subscription:**

~~~bash
az account show --output table

az aks show \
  --resource-group rg-aks-lab \
  --name aks-private-lab \
  --query "{state:provisioningState,private:apiServerAccessProfile.enablePrivateCluster,privateFqdn:privateFqdn}" \
  --output json
~~~

**Bước 2 — Xác nhận DNS và TCP từ đúng client:**

~~~bash
nslookup <PRIVATE_AKS_FQDN>
nc -vz <PRIVATE_AKS_FQDN> 443
~~~

**Bước 3 — Kiểm tra kubeconfig, identity và token:**

~~~bash
kubectl config current-context
az account show --query "{tenant:tenantId,subscription:id,user:user.name}" -o json
kubelogin --version
~~~

**Bước 4 — Phân biệt 401 và 403:**

- **401:** kiểm tra đăng nhập và token/tenant/clock.
- **403:** kiểm tra role/namespace/group và loại authorizer.
- **Timeout/DNS:** đừng sửa role trước khi kết nối mạng hoạt động.
- **TLS:** kiểm tra FQDN, certificate và proxy, không tự thêm tùy chọn bỏ xác minh TLS.

**Bước 5 — Đối chiếu log và change:**

Kiểm tra Azure Activity Log, Kubernetes audit log, role assignments, thay đổi DNS và pipeline logs. Ghi rõ thời điểm UTC, caller, source IP khi có, resource ID và namespace.

### 15.3. Không sửa nhanh bằng cách mở API public

Việc bật public endpoint chỉ để chạy kubectl từ laptop là một thay đổi rủi ro, có thể phá vỡ yêu cầu phân tách mạng hoặc compliance. Hãy xác định vì sao private route/DNS không hoạt động và dùng kênh quản trị được phê duyệt.

Tương tự, việc cấp Azure Kubernetes Service RBAC Cluster Admin khi chưa hiểu nguyên nhân Forbidden làm giảm khả năng kiểm soát quyền. Chỉ nâng quyền theo quy trình khẩn cấp khi thực sự cần và có giới hạn thời gian/kiểm toán.

## 16. Break-glass và khôi phục khả năng quản trị

Private cluster kết hợp Entra ID và tắt local accounts giúp hạn chế đường đăng nhập ngoài quản trị tập trung. Tuy nhiên cần trả lời câu hỏi: **nếu DNS, VPN hoặc cấu hình quyền Entra bị lỗi, ai sẽ khôi phục hệ thống và bằng cách nào?**

Một kế hoạch break-glass phù hợp phải mô tả:

1. Ai được phép kích hoạt, qua kênh phê duyệt nào?
2. Có đường truy cập mạng độc lập hoặc VM quản trị dự phòng không?
3. Danh tính Azure nào có thể sửa mạng/DNS và IAM, và được bảo vệ bằng PIM/kiểm toán ra sao?
4. Có thể khôi phục DNS Private Zone/VNet link từ Infrastructure as Code không?
5. Khi local accounts đã disable, lối phục hồi nào được **sản phẩm cho phép** mà không phá vỡ chính sách?
6. Có thể sử dụng Run Command trong tình huống được phê duyệt không, và ai có quyền gọi?
7. Backup/restore cho các cấu hình Kubernetes, GitOps state và dữ liệu ứng dụng nằm ở đâu?
8. Có bài thử recovery định kỳ với kết quả và action items không?

**Không được hứa rằng admin kubeconfig luôn dùng được khi Entra/RBAC có sự cố**, nhất là khi local accounts đã disable. Cũng không nên xóa/đổi DNS zone của cluster trong lúc sự cố nếu chưa hiểu tài nguyên do AKS quản lý.

### 16.1. Kiểm soát thay đổi mạng và danh tính

Những thay đổi như chuyển DNS, đổi outbound type, chỉnh VNet peering, thay API server mode hoặc migration identity có thể làm mất quản trị cluster. Với production:

- Chuẩn bị runbook và backout plan.
- Kiểm thử thay đổi ở staging hoặc cluster lab tương ứng.
- Dùng IaC để giữ bản cấu hình đã biết tốt.
- Xác nhận quyền Azure ARM và Kubernetes API của người thực hiện.
- Quan sát sau thay đổi từ ít nhất hai đường kết nối khi có thể.
- Ghi approval, timestamp và kết quả kiểm tra.

## 17. Chi phí và vận hành private cluster

Bản thân mục tiêu dùng private Kubernetes API không làm toàn bộ hệ thống miễn phí hoặc tự đáp ứng yêu cầu availability.

Các hạng mục cần dự toán:

- AKS control plane tier/mô hình giá và node pools.
- VM nodes, managed disks, load balancer và dữ liệu truyền.
- VNet, Private DNS zone, Private DNS Resolver hoặc DNS forwarder nếu dùng.
- Azure Bastion, VPN Gateway, ExpressRoute, Firewall/NAT nếu cần.
- Private runner/agent và dung lượng compute phục vụ pipeline.
- Azure Monitor, Container insights, Log Analytics và thời gian lưu audit logs.
- Microsoft Defender for Cloud và những gói bảo vệ bổ sung.
- Chi phí vận hành identity, RBAC review, DNS change và diễn tập DR.

**Private API chỉ giảm một bề mặt truy cập**, không tự mang lại multi-region high availability. Cần thiết kế workload replicas, node pools, zones, backups và DR theo mục tiêu ứng dụng.

Từ góc độ vận hành, một API private giúp giới hạn mạng nhưng tăng độ phức tạp DNS/hybrid connectivity. Cân nhắc lợi ích bảo mật so với năng lực quản trị và mức độ sẵn sàng của đội vận hành.

## 18. Tình huống thực tế: AKS chạy dịch vụ đơn hàng production

Giả sử doanh nghiệp có AKS cluster aks-orders-private phục vụ API đơn hàng, nhận traffic khách hàng qua ingress công khai được bảo vệ, nhưng muốn **chỉ nhóm vận hành và pipeline đã phê duyệt** quản trị Kubernetes API.

### 18.1. Kiến trúc lựa chọn

- AKS API ở chế độ private trong mô hình được hỗ trợ.
- Node pool chạy trong subnet đã thiết kế.
- API private FQDN phân giải qua Private DNS và các link/forwarder cần thiết.
- Kỹ sư kết nối VPN hoặc Azure Bastion vào jump host.
- CI/CD deploy bằng self-hosted runner trong VNet; source CI có thể ở hệ thống khác.
- Entra ID dùng xác thực người dùng; Azure RBAC for Kubernetes Authorization cấp quyền theo namespace.
- Nhóm platform có quyền đặc biệt qua PIM; team orders chỉ có quyền ở namespace orders.
- ServiceAccount runtime không có Kubernetes API permissions nếu ứng dụng không cần.
- ACR chứa image, Container insights/Defender for Cloud/audit phục vụ giám sát.
- Database/Storage được bảo vệ bằng Private Endpoint và runtime identity riêng.

### 18.2. Ma trận người dùng

| Chủ thể | API access path | Quyền Kubernetes | Kiểm soát |
|---|---|---|---|
| Platform engineer | VPN → private VM hoặc trực tiếp private route | Quyền vận hành cluster theo scope, PIM khi đặc biệt | MFA, auditing, approval |
| Developer orders | VPN/VM khi được cấp | Reader ở orders | Không xem secrets, không thao tác cluster-wide |
| CI/CD orders | Private runner | Deploy tại orders theo policy | Federated/managed identity, artifact approval |
| Security analyst | Đường quản trị có kiểm soát | Quyền xem thông tin cần điều tra | Audit, không cấp admin thường trực |
| Ứng dụng orders | Trong Pods | Không gọi K8s API trừ khi có nhu cầu thực | ServiceAccount riêng, token mount tối thiểu |

### 18.3. Kịch bản kiểm thử chấp nhận

1. Laptop không có VPN không thể liên hệ private API trực tiếp.
2. Laptop/runner có VPN hoặc trong VNet phân giải đúng private FQDN.
3. User Entra không được cấp role có thể nhận credential theo policy nhưng bị từ chối hành động Kubernetes không có quyền.
4. Nhóm Reader xem Pods tại orders được, sửa Deployment không được.
5. CI/CD có quyền cập nhật Deployment ở orders nhưng không tạo ClusterRoleBinding hoặc xóa namespace.
6. GitOps/service account chỉ có những quyền cần cho controller.
7. Kubernetes audit logs ghi các thao tác quan trọng theo cấu hình đã bật.
8. Sự cố DNS private được phát hiện và có runbook khôi phục.
9. Container image được deploy qua digest với approval và có rollback.
10. Ứng dụng vẫn phục vụ qua ingress theo yêu cầu dù Kubernetes API quản trị không public.

Thành công không chỉ là kubectl get pods chạy được; quan trọng hơn là **người đúng được làm việc đúng trong phạm vi đúng, qua mạng đúng và có dấu vết kiểm toán**.

## 19. Checklist triển khai production

### Mạng và DNS

- [ ] Đã xác định cluster private hay public và lý do.
- [ ] Có sơ đồ private API path, subnet, route và DNS.
- [ ] Client quản trị được chọn có đường private tới Kubernetes API.
- [ ] VNet peering, VPN/ExpressRoute, firewall/NSG đáp ứng TCP 443.
- [ ] Private FQDN phân giải đúng từ jump host, runner và on-premises.
- [ ] Custom DNS zone, VNet link và DNS forwarding có owner rõ ràng.
- [ ] Không công khai API chỉ để giải quyết lỗi cấu hình mạng.

### Danh tính và phân quyền

- [ ] Entra ID authentication được tích hợp và thử bằng user thật.
- [ ] Đã quyết định Azure RBAC hoặc Kubernetes native RBAC.
- [ ] Quyền lấy kubeconfig được tách khỏi quyền thao tác Kubernetes.
- [ ] Có namespace roles/group mapping theo least privilege.
- [ ] Pipeline deploy không dùng cluster-admin thường trực.
- [ ] Workload identities và service accounts không có quyền thừa.
- [ ] Local accounts và break-glass được quản lý theo chính sách đã thử nghiệm.
- [ ] Có audit/alert cho thay đổi role và ClusterRoleBinding.

### CI/CD và vận hành

- [ ] Private runner/GitOps controller được bảo vệ và vá lỗi.
- [ ] Image/digest, approval và rollout có thể truy vết.
- [ ] Kubeconfig/token không bị ghi vào repository hoặc pipeline log.
- [ ] Kubernetes audit/AKS diagnostic logs được thu thập và retention phù hợp.
- [ ] Có dashboard lỗi API, node health, DNS và connectivity.
- [ ] Có runbook điều tra 401/403/DNS/timeout.
- [ ] Đã diễn tập mất kết nối quản trị và khôi phục.
- [ ] Chi phí node, network, resolver, runner và log ingestion được dự toán.

## 20. Câu hỏi tự kiểm tra

1. **Private AKS cluster bảo vệ bề mặt nào chủ yếu?** Đường truy cập Kubernetes API/control plane từ mạng ngoài phạm vi riêng, theo mô hình triển khai được hỗ trợ.
2. **Private cluster có làm ingress của ứng dụng tự động thành private không?** Không. Ingress và các Service ứng dụng có thiết kế mạng riêng.
3. **Có kubeconfig là có quyền cluster-admin không?** Không. Kubeconfig mô tả endpoint và cách xác thực; authorization được kiểm tra riêng.
4. **Vì sao get-credentials thành công nhưng kubectl timeout?** Lệnh lấy kubeconfig dùng Azure management plane; máy chạy kubectl có thể thiếu DNS/route tới private API.
5. **DNS cần trả kết quả nào?** Tên private AKS API phải phân giải tới đích private phù hợp với kiến trúc được triển khai.
6. **TCP 443 kết nối thành công có đồng nghĩa user được list Pods không?** Không. Còn xác thực và phân quyền.
7. **401 khác 403 thế nào?** 401 thường liên quan xác thực/credential; 403 là danh tính đã được xác định nhưng thiếu quyền.
8. **Azure Kubernetes Service Cluster User Role có cấp quyền sửa Deployment không?** Không mặc nhiên. Nó liên quan lấy user kubeconfig qua management plane.
9. **Azure Kubernetes Service RBAC Reader và Cluster User Role có giống nhau không?** Không. Reader là role authorization cho Kubernetes API trong mô hình Azure RBAC; Cluster User Role dùng để lấy credential.
10. **Kubernetes RoleBinding khác ClusterRoleBinding ra sao?** RoleBinding giới hạn tại namespace; ClusterRoleBinding áp ở phạm vi cluster.
11. **Tại sao không cấp cluster-admin cho CI/CD?** Tăng blast radius khi pipeline hoặc token bị xâm phạm; thường chỉ cần quyền namespace.
12. **Hosted CI runner có chắc kết nối được private API không?** Không. Cần đường private network/agent phù hợp.
13. **Azure Activity Log có ghi đủ mọi lệnh kubectl không?** Không. Cần Kubernetes audit logs tương ứng.
14. **Workload Identity cho Pod có tự cấp quyền Kubernetes API không?** Không. Quyền Azure và Kubernetes là hai cơ chế khác nhau.
15. **Có nên bật public API để sửa lỗi 403?** Không. 403 là vấn đề authorization, không phải reachability.
16. **Run Command có phải đường quản trị ít quyền thay kubectl không?** Không. Nó có quyền Azure nhạy cảm và phải kiểm soát riêng.
17. **Một người có thể thấy Pods nhưng không thấy namespaces không?** Có. Đó có thể là thiết kế namespace-scoped RBAC đúng.
18. **Private cluster có thay thế backup hoặc NetworkPolicy không?** Không. Nó chỉ bảo vệ một phần bề mặt API.
19. **Mất private DNS zone có thể gây hậu quả gì?** Máy quản trị/runner không phân giải được API, khó vận hành hoặc triển khai.
20. **Thế nào là một private AKS deployment thành công?** Mạng riêng hoạt động, auth và least privilege đúng, ứng dụng khỏe, có monitoring và kế hoạch phục hồi được thử.

## 21. Tài liệu tham khảo

- [Azure Kubernetes Service documentation](https://learn.microsoft.com/azure/aks/) — AKS architecture, networking, identity và vận hành.
- [Create an AKS private cluster](https://learn.microsoft.com/azure/aks/private-clusters) — điều kiện, private endpoint, DNS và các mô hình private cluster.
- [API Server VNet Integration](https://learn.microsoft.com/azure/aks/api-server-vnet-integration) — mô hình tích hợp API server với VNet.
- [AKS networking concepts](https://learn.microsoft.com/azure/aks/concepts-network) — CNI, node/pod networking và outbound connectivity.
- [AKS authentication with Microsoft Entra ID](https://learn.microsoft.com/azure/aks/enable-authentication-microsoft-entra-id) — xác thực danh tính.
- [Azure RBAC for Kubernetes Authorization](https://learn.microsoft.com/azure/aks/manage-azure-rbac) — quản lý quyền Kubernetes API qua Azure RBAC.
- [Kubernetes RBAC documentation](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) — Role, RoleBinding, ClusterRole và ClusterRoleBinding.
- [kubelogin documentation](https://learn.microsoft.com/azure/aks/kubelogin-authentication) — credential plugin cho AKS tích hợp Entra ID.
- [AKS Run Command](https://learn.microsoft.com/azure/aks/access-private-cluster) — các phương án truy cập private cluster theo tính năng được hỗ trợ.
- [AKS monitoring](https://learn.microsoft.com/azure/aks/monitor-aks) — monitoring và log của AKS.
- [Azure Private DNS](https://learn.microsoft.com/azure/dns/private-dns-overview) — private DNS zones và kết nối mạng riêng.
- [Azure Policy for AKS](https://learn.microsoft.com/azure/governance/policy/concepts/policy-for-kubernetes) — policy và quản trị cấu hình workload.

**Kết luận:** private AKS cluster giúp giới hạn đường truy cập Kubernetes API qua mạng riêng nhưng không thay thế xác thực, phân quyền hoặc bảo mật workload. Một kiến trúc an toàn cần đủ ba lớp **DNS/network → Entra authentication → Azure RBAC hoặc Kubernetes native RBAC**, với CI/CD runner có đường riêng, quyền namespace tối thiểu, audit logs và break-glass được diễn tập. Khi triển khai thực tế, luôn xác minh kiểu API server networking, Private DNS và feature support trên đúng AKS version/region, thay vì suy đoán theo tên cấu hình.
