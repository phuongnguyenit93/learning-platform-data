# Private clusters và bảo vệ truy cập control plane trong GKE

Một doanh nghiệp thương mại điện tử chạy API và các worker trên **Google Kubernetes Engine (GKE)**, lưu dữ liệu giao dịch ở **Cloud SQL**, ảnh sản phẩm ở **Cloud Storage** và container images trong **Artifact Registry**. Đội bảo mật đặt yêu cầu: các node không được có external IP, Kubernetes API không được trở thành một endpoint quản trị công khai ngoài chủ đích, người phát triển chỉ được xem tài nguyên cần thiết, còn SRE có thể xử lý sự cố từ mạng doanh nghiệp hoặc một đường truy cập được kiểm soát.

Ở GKE, **private cluster** thường đề cập trước hết đến **các node sử dụng địa chỉ IP nội bộ thay vì external IP**, kết hợp với cách cấu hình kết nối tới **control plane**. Nhưng một hiểu nhầm nguy hiểm là: **“private nodes” không mặc nhiên đồng nghĩa “Kubernetes API chỉ có private endpoint”**. GKE có các cơ chế cấu hình IP-based endpoint (private/public) và DNS-based endpoint; lựa chọn nào khả dụng còn tùy loại cluster, phiên bản và chế độ endpoint access.

Bài học thuộc chương **GKE cơ bản**, mô-đun **CLOUD_PROVIDERS_GCP**. Trọng tâm là cách thiết kế và xác minh các lớp **đường mạng, danh tính, quyền Kubernetes và quản trị vận hành** để bảo vệ control plane; nội dung liên hệ với organization, IAM, VPC, Compute Engine, Cloud Run, lưu trữ/cơ sở dữ liệu, tự động hóa phát hành, độ tin cậy và chi phí.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **control plane** với **node/workload data plane**, và phân biệt private nodes với private control-plane endpoint.
2. So sánh **IP-based public endpoint**, **IP-based private endpoint**, **DNS-based endpoint**, cùng giới hạn của **Master Authorized Networks**.
3. Chọn đường quản trị Kubernetes API phù hợp: từ VPC, qua Cloud VPN/Interconnect, bastion truy cập qua IAP hoặc DNS-based endpoint theo chính sách.
4. Hiểu vai trò của **Google Cloud IAM**, **Kubernetes RBAC** và danh tính workload, không nhầm quyền lấy kubeconfig với quyền sửa toàn bộ cluster.
5. Thiết kế subnet, Pod/Service secondary ranges, egress tới Google APIs và quyền pull images cho private nodes.
6. Đọc cấu hình GKE bằng `gcloud`, lấy credentials bằng đúng endpoint và khoanh vùng các lỗi mạng, xác thực và ủy quyền.
7. Lập checklist triển khai, khôi phục quyền quản trị, giám sát và đánh giá chi phí cho một private cluster.

## 2. Control plane là gì và tại sao cần bảo vệ?

### 2.1. Control plane và nơi chạy workload

Một GKE cluster có hai nhóm thành phần logic:

- **Control plane:** Kubernetes API server, các cơ chế quản lý trạng thái và thành phần điều phối do GKE quản lý theo loại cluster. Người dùng/CI/CD sử dụng Kubernetes API để tạo, đọc và cập nhật những tài nguyên như `Deployment`, `Service`, `Secret` hoặc `RoleBinding`.
- **Nodes và workloads:** Compute Engine worker nodes hoặc hạ tầng node do GKE quản lý, nơi Pod thực sự chạy và giao tiếp với nhau/dịch vụ dữ liệu. Với **Standard**, người dùng có nhiều quyền cấu hình node pools; với **Autopilot**, GKE quản lý nhiều khía cạnh node và scheduling hơn.

~~~mermaid
flowchart TD
    USER["Kỹ sư / CI/CD"] --> API["Kubernetes API server\n(control plane do GKE quản lý)"]
    API --> SCHED["Trạng thái mong muốn / scheduling"]
    SCHED --> N1["Worker node A"]
    SCHED --> N2["Worker node B"]
    N1 --> P1["Pod: orders-api"]
    N2 --> P2["Pod: catalog-api"]
    P1 --> DB["Cloud SQL"]
    P2 --> STORE["Cloud Storage"]
    REG["Artifact Registry"] -. "Image pull qua danh tính node" .-> N1
    REG -.-> N2
~~~

**Control plane là bề mặt quản trị cực kỳ nhạy cảm**. Nếu một principal có thể sửa `Deployment`, `RoleBinding`, workload identity hoặc `Secret`, hậu quả có thể vượt ra ngoài một Pod. Do đó, bảo vệ Kubernetes API cần cả **hạn chế đường truy cập** và **ủy quyền chính xác**.

### 2.2. Control plane reachability không đồng nghĩa workload reachability

Ví dụ kỹ sư từ Internet có thể gọi một **public IP-based Kubernetes API endpoint** nếu cluster có bật endpoint này, policy cho phép nguồn IP và danh tính hợp lệ. Điều đó không có nghĩa kỹ sư có đường trực tiếp đến Pod IP hoặc VM node. Ngược lại, Pod có thể gọi Cloud SQL qua private IP mà người quản trị từ laptop vẫn không thể đến private Kubernetes API endpoint.

| Đường truy cập | Đích | Kiểm soát chính |
| --- | --- | --- |
| Máy quản trị → Kubernetes API | Control plane endpoint | Endpoint mode, route, firewall/allowlist thích hợp, IAM/authn, Kubernetes authorization. |
| Control plane → worker nodes | Node control/management channel | Kết nối do kiến trúc GKE và cluster networking yêu cầu. |
| Pod → Pod/Service | Data plane nội bộ | VPC-native networking, Kubernetes NetworkPolicy khi được bật/hỗ trợ, service routing. |
| Pod → Google APIs | Cloud Storage, Secret Manager... | DNS/egress, IAM, Workload Identity Federation for GKE. |
| Node → Artifact Registry | Container image pull | Node identity, OAuth scopes khi áp dụng và mạng tới registry. |

Một private cluster không tự bật NetworkPolicy, không tự quản lý quyền Kubernetes và không tự cho ứng dụng quyền truy cập Cloud SQL/Storage.

## 3. Ba khái niệm dễ bị nhầm

### 3.1. Private nodes

**Private nodes** là các node không được cấp địa chỉ IP công khai trực tiếp theo mô hình private-cluster networking. Node giao tiếp qua VPC internal IP và vẫn cần đường tới những dịch vụ thiết yếu, chẳng hạn:

- Google APIs và GKE control/management services phù hợp.
- Artifact Registry để kéo container images.
- Các nguồn package ngoài Google Cloud, nếu startup hoặc ứng dụng thực sự cần.
- Cloud SQL, Cloud Storage, Pub/Sub và những phụ thuộc nghiệp vụ.

Không có external IP **không có nghĩa VM không thể tạo outbound connection**. Outbound phụ thuộc route, DNS, Private Google Access, Cloud NAT, Private Service Connect endpoints hoặc phương án hỗ trợ khác.

### 3.2. Private IP-based control-plane endpoint

**Private endpoint** là đường kết nối tới Kubernetes API thông qua **địa chỉ private IP** được GKE cung cấp theo kiến trúc của cluster. Với loại cluster và chế độ endpoint hỗ trợ, client có thể quản trị qua VPC, một host có đường private đến endpoint hoặc kết nối hybrid đã định tuyến đúng.

Chọn private endpoint giúp tránh dựa vào việc công bố một public IP-based endpoint cho quản trị. Tuy nhiên:

- Client từ **Cloud Shell/laptop Internet** không mặc nhiên có route tới private IP.
- Có thể cần bastion, VPN, Interconnect hoặc một đường quản trị bảo mật đã thiết kế.
- Private endpoint có thể bị ảnh hưởng bởi cấu hình authorized networks cho private endpoint **nếu chế độ kiểm soát đó được bật/hỗ trợ**, cùng các quy tắc endpoint access khác.
- Một số cluster sử dụng công nghệ kết nối control plane khác nhau (bao gồm các kiến trúc dựa trên Private Service Connect); không áp mọi giả định routing/VPC peering từ cluster cũ cho cluster mới.

### 3.3. DNS-based endpoint

GKE còn hỗ trợ **DNS-based endpoint** của Kubernetes control plane, có thể được quản lý bằng các tùy chọn endpoint access và xác thực Google Cloud tương ứng. Đây là phương án được Google Cloud khuyến nghị trong nhiều quy trình quản trị hiện đại, đặc biệt khi muốn áp dụng **IAM** và các lớp bảo vệ như **VPC Service Controls** trong môi trường được hỗ trợ.

Quan trọng: **DNS-based endpoint không đồng nghĩa với private IP endpoint**. Một DNS endpoint có thể được truy cập qua đường Internet/Google APIs theo phương án hỗ trợ, trong khi việc **ai được kết nối** được kiểm soát bằng cơ chế xác thực và IAM/policy. Vì vậy nếu yêu cầu nội bộ là “API tuyệt đối không được quản trị từ ngoài mạng doanh nghiệp”, phải xác minh cả **DNS endpoint đang bật hay tắt**, không chỉ nhìn cờ private nodes/private endpoint.

Tên hostname, phạm vi kiểm soát IAM và các cách bật/tắt DNS endpoint có thể thay đổi giữa các phiên bản GKE/CLI. Hãy đọc trạng thái endpoint thực tế thay vì suy từ tên `private-cluster`.

## 4. So sánh các cách đưa Kubernetes API tới người quản trị

| Kiểu endpoint | Đường kết nối điển hình | Kiểm soát cần chú ý | Hiểu nhầm cần tránh |
| --- | --- | --- | --- |
| **Public IP-based endpoint** | Client có đường Internet đến public endpoint của API server. | Master Authorized Networks đối với IP endpoint, authentication và authorization; chính sách cluster/org. | “Có public IP là ai cũng điều khiển được cluster” — sai vì vẫn cần quyền; nhưng mở rộng bề mặt mạng. |
| **Private IP-based endpoint** | Client ở VPC hoặc mạng có private route tới control plane. | Network reachability, chế độ IP endpoint, IAM/RBAC, authorized networks trên private endpoint khi hỗ trợ. | “VM trong VPC nào cũng tới được” — còn phụ thuộc network/route/policy. |
| **DNS-based endpoint** | Client gọi endpoint qua DNS/Google APIs theo cơ chế GKE hỗ trợ. | IAM, endpoint access policy, VPC Service Controls khi áp dụng, principal và Kubernetes authorization. | “Tên DNS đồng nghĩa địa chỉ private” — không đúng. |

### 4.1. Master Authorized Networks không phải một hệ thống IAM

**Master Authorized Networks (MAN)** là kiểm soát phạm vi **nguồn IP/CIDR được phép tới IP-based control-plane endpoint** khi sử dụng chế độ và loại endpoint được hỗ trợ. Đây là **allowlist mạng**, không phải danh sách người dùng và không thay thế xác thực/ủy quyền Kubernetes.

Ví dụ:

~~~text
Public IP-based endpoint: enabled
Authorized networks: 203.0.113.0/24   (CIDR minh họa theo RFC 5737)

Người A trong dải CIDR:
  Có thể vượt qua bước kiểm soát nguồn IP, nhưng vẫn cần authn/authz.

Người B ngoài dải CIDR:
  Có thể bị chặn ở lớp truy cập mạng ngay cả khi có tài khoản IAM hợp lệ.
~~~

**MAN không giới hạn DNS-based endpoint theo cùng cơ chế của IP-based endpoint.** Khi bật DNS endpoint, cần hiểu rõ các lớp bảo vệ riêng, không dựa duy nhất vào allowlist IP đã cấu hình.

### 4.2. “Public endpoint tắt” vẫn phải kiểm tra DNS endpoint

Một cluster có private IP endpoint và không dùng public IP-based endpoint có thể vẫn có **DNS-based endpoint** nếu được cấu hình bật. Do đó, báo cáo bảo mật nên ghi riêng:

~~~text
private nodes:              enabled/disabled
IP-based public endpoint:   enabled/disabled
IP-based private endpoint:  enabled/disabled
DNS-based endpoint:         enabled/disabled
authorized networks:       scope/allowlist thích hợp
~~~

Không kết luận cluster có hay không có đường quản trị từ Internet chỉ bằng một trường `privateClusterConfig` ở kết quả `gcloud describe`.

### 4.3. Chọn mô hình theo mục tiêu

| Mục tiêu | Thiết kế cần xem xét |
| --- | --- |
| Node không có external IP, quản trị viên ở văn phòng cần vào API. | Private nodes + private IP endpoint + VPN/Interconnect hoặc bastion bảo mật. |
| Đội phân tán cần quản trị từ nhiều mạng, kiểm soát danh tính nghiêm ngặt. | DNS-based endpoint với IAM/policy phù hợp và quyết định rõ phạm vi network access. |
| Vẫn dùng public IP endpoint cho kịch bản được cho phép. | Master Authorized Networks hẹp, IAM/RBAC tối thiểu, theo dõi nguồn truy cập. |
| Tổ chức yêu cầu chỉ có private path tới Kubernetes API. | Đánh giá cả IP-based và DNS-based endpoint, quản trị từ private network, kiểm thử không còn đường truy cập ngoài dự kiến. |
| Tổ chức có VPC Service Controls. | Xem hỗ trợ và thiết lập perimeter đối với DNS endpoint/API mà GKE cho phép, không coi VPC SC là firewall thông thường. |

## 5. Networking cho private GKE cluster

### 5.1. VPC-native, subnet và secondary ranges

GKE thường sử dụng **VPC-native networking** (alias IP) cho cluster hiện đại. Ví dụ sơ đồ IP:

~~~text
Project: retail-lab
VPC: retail-vpc
Region: asia-southeast1

Primary subnet range (nodes):      10.30.0.0/20
Secondary range (Pods):            10.40.0.0/16
Secondary range (Services):        10.50.0.0/20
Private control-plane range
  (với kiến trúc cần CIDR riêng):  172.16.0.0/28

On-premises network:               192.168.100.0/24
~~~

Đây là **địa chỉ minh họa**, không phải IP plan được cấp phát. Phạm vi control-plane private CIDR và cách nó được quản lý phụ thuộc **loại cluster/kiến trúc control plane**; không phải mọi cluster mới đều cần tự đặt `--master-ipv4-cidr`. Với subnet/secondary ranges, phải tính số Pod/Service/Node và dự báo scale trong vòng đời cluster.

Hãy kiểm tra **overlap** giữa:

- Primary subnet dành cho nodes.
- Pod secondary range và Service secondary range.
- Dải control-plane endpoints/peering nếu kiến trúc yêu cầu.
- Các VPC khác, mạng on-premises và mạng được nối qua VPN/Interconnect.

Nếu CIDR xung đột, mạng có thể chọn route sai hoặc không thể tạo/cấu hình cluster. Đổi CIDR sau khi cluster đã có workload thường khó và có thể cần migration; đừng chỉ tăng firewall allowlist để che đi vấn đề routing.

### 5.2. Control plane kết nối với worker nodes

GKE quản lý các thành phần control plane, nhưng cluster vẫn cần **luồng quản lý tới nodes** và các thành phần như webhook/metrics server theo kiến trúc cụ thể. Khi tạo private cluster:

1. Chọn đúng VPC, subnet và region/zone.
2. Kiểm tra firewall rules được GKE tạo/quản lý và mọi policy mạng cấp tổ chức.
3. Khi có **webhook** tự triển khai hoặc thành phần gọi từ API server, xác minh port, đường đi và chứng chỉ.
4. Đừng xóa firewall rules GKE tạo chỉ vì tên khó hiểu; xác định vai trò chính xác trước khi đổi.
5. Đọc tài liệu networking của loại cluster để phân biệt kết nối control plane qua cơ chế mới và VPC peering truyền thống.

**Private cluster không tự động đồng nghĩa mọi request trong data plane được mã hóa end-to-end**. Mã hóa liên dịch vụ, network segmentation và authentication là các lớp bổ sung.

### 5.3. Egress từ private nodes

Một node không có external IP vẫn cần pull container images, gửi metrics/logs và đôi khi tải package updates. Có một số hướng tiếp cận:

| Đích | Phương án cần xem xét | Lưu ý |
| --- | --- | --- |
| Google APIs / Cloud Storage | Private Google Access hoặc giải pháp private Google APIs được hỗ trợ; đúng DNS/route/IAM. | PGA không cấp IAM và không thay thế egress policy. |
| Artifact Registry | Đường tới hostname registry, IAM Reader cho node identity và cấu hình private access tương ứng. | `*.pkg.dev` cần kiểm tra DNS và các endpoint hỗ trợ, không tự xem là `*.googleapis.com`. |
| Nguồn package/public Internet | Cloud NAT hoặc egress proxy/firewall được quản lý nếu cần. | Cloud NAT là outbound NAT, **không** mở cổng inbound SSH tới node. |
| Cloud SQL private IP | Kết nối mạng/private service phù hợp cùng database auth. | Route tới DB không tự cấp quyền truy cập bảng. |
| Hệ thống doanh nghiệp | Cloud VPN/Interconnect, Cloud Router/BGP và DNS hybrid theo nhu cầu. | Cần kiểm tra đường đi về và chính sách egress/ingress. |

**Không mở external IP cho tất cả nodes** chỉ để xử lý một lỗi pull image. Chẩn đoán DNS, TCP 443, IAM, OAuth scopes (nếu áp dụng) và proxy/NAT theo đúng đích.

### 5.4. Quản trị qua hybrid connectivity

Kỹ sư có thể cần đến private control-plane endpoint từ mạng công ty:

~~~mermaid
flowchart LR
    LAP["Laptop trong mạng doanh nghiệp"] --> ON["Router on-premises"]
    ON --> VPN["HA VPN / Interconnect"]
    VPN --> VPC["GCP VPC: retail-vpc"]
    VPC --> API["Private IP-based endpoint\nGKE control plane"]
    API --> CL["Cluster resources"]
    IAM["IAM + Kubernetes authorization"] -. "Kiểm tra danh tính và quyền" .-> API
~~~

Cần có routing tới đúng private endpoint, firewall và các điều kiện global access theo region/topology được hỗ trợ. Nếu người dùng ở region khác vùng control plane, phải xác minh **master global access** hoặc cơ chế truy cập liên vùng tương ứng thay vì mặc định private endpoint luôn hoạt động từ mọi region.

## 6. Bảo vệ control plane theo nhiều lớp

### 6.1. Lớp mạng và endpoint

Hãy quyết định rõ:

- Có dùng **public IP endpoint** không?
- Nếu có, **Master Authorized Networks** giới hạn nguồn thế nào?
- Có bật **private IP endpoint** cho các kênh quản trị nội bộ không?
- **DNS endpoint** có bật không? Những principal/IAM policy nào được quyền kết nối?
- Network path từ đội vận hành/CI/CD đi qua đâu, ai sở hữu, có log/audit không?

Không tối ưu một tiêu chí (ví dụ tắt public endpoint) mà quên rằng pipeline CI/CD hoặc hệ thống quan sát cần truy cập Kubernetes API để triển khai và khắc phục sự cố.

### 6.2. Lớp danh tính: Google Cloud IAM

**IAM** giúp kiểm soát thao tác với tài nguyên GKE/Google Cloud: xem cluster, lấy thông tin endpoint/credentials, chỉnh cấu hình cluster, gọi những API được bảo vệ và các quyền tích hợp được hỗ trợ.

Ví dụ:

| Principal | Nhu cầu | Phạm vi cần thiết |
| --- | --- | --- |
| Platform admin | Quản lý cluster và endpoint config. | Role GKE quản trị phù hợp, có phê duyệt cho thay đổi nhạy cảm. |
| Developer | Xem trạng thái workload của một namespace. | Quyền đọc thông tin cluster cần thiết + Kubernetes authorization hẹp. |
| CI deployer | Cập nhật Deployment/Service ở namespace được giao. | Quyền kết nối cluster và Kubernetes authorization tương ứng; không cần Owner toàn project. |
| Security auditor | Xem IAM, API audit logs và cấu hình network. | Reader/Auditor phù hợp, không cần quyền sửa toàn cluster. |

Các role IAM GKE thường gặp gồm `roles/container.clusterViewer`, `roles/container.developer` và `roles/container.admin`; **không chọn chỉ theo tên role**. Phải đọc permissions thực tế và tác động ở phạm vi project/cluster, đặc biệt khi kết hợp với Kubernetes RBAC.

### 6.3. Lớp Kubernetes: authorization và RBAC

Kubernetes dùng **Role/ClusterRole** và **RoleBinding/ClusterRoleBinding** để xác định quyền gọi Kubernetes API. GKE có tích hợp **Google Cloud IAM authorization** cho các thao tác Kubernetes được hỗ trợ; vì vậy quyền hiệu lực có thể liên quan tới cả IAM và RBAC.

**Không khẳng định luôn bắt buộc có cả một IAM role cho Kubernetes resource lẫn RBAC binding trong mọi trường hợp**, hoặc rằng một binding RBAC đơn lẻ đủ để vượt qua mọi kiểm soát endpoint/IAM. Phải kiểm tra đường xác thực, IAM permissions và chính sách Kubernetes hiện hành.

~~~mermaid
flowchart TD
    U["Principal: developer@example.com"] --> PATH["Đường kết nối tới endpoint"]
    PATH --> AUTHN["Authentication / principal identity"]
    AUTHN --> AUTHZ["Kubernetes authorization\nRBAC và/hoặc GKE IAM theo mô hình"]
    AUTHZ --> NS["Namespace: retail"]
    NS --> P["Read Pods / Services"]
    NS -. "Không tự có quyền" .-> SEC["Secrets / cluster-wide admin"]
~~~

Nguyên tắc quyền tối thiểu: developer cần xem Pod/Service của namespace `retail` **không** nên được gán `cluster-admin` chỉ để khắc phục một lỗi `kubectl get pods`.

### 6.4. Ví dụ Kubernetes RBAC cho quyền đọc namespace

Các manifest dưới đây **chỉ minh họa** một cách cấp quyền đọc Pod và Service cho danh tính phù hợp. Đừng áp dụng trước khi xác định chính xác principal mà GKE authentication map sang Kubernetes username:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: retail-observer
  namespace: retail
rules:
  - apiGroups: [""]
    resources: ["pods", "services"]
    verbs: ["get", "list", "watch"]
~~~

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: retail-observer-binding
  namespace: retail
subjects:
  - kind: User
    name: developer@example.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: retail-observer
  apiGroup: rbac.authorization.k8s.io
~~~

Role trên **không cấp quyền đọc Secrets**, sửa Deployment hoặc tạo ClusterRoleBinding. Việc tạo RoleBinding là hành động có ảnh hưởng quyền truy cập và phải được một admin cho phép. Nếu organization sử dụng Google Groups for RBAC, cấu hình identity và `subjects.kind: Group` có quy trình riêng; không tự thay `User` bằng group email mà chưa xác nhận tích hợp.

### 6.5. Workload identity không phải quyền quản trị cluster

**Workload Identity Federation for GKE** cho phép Pod sử dụng danh tính Kubernetes/Google Cloud theo kiến trúc để gọi Google APIs mà không phải nhúng khóa service account tĩnh. Nó giải quyết **quyền runtime của ứng dụng** như đọc Cloud Storage hoặc Secret Manager, **không tự cấp cho người phát triển quyền `kubectl`**.

Tương tự, một node service account có quyền pull image trong Artifact Registry không mặc nhiên trao quyền cluster-admin cho các Pods. Tách **principal quản lý GKE**, **principal pull image** và **principal runtime** là yêu cầu quan trọng.

## 7. Hai đường quản trị private IP endpoint thường dùng

### 7.1. Bastion VM được bảo vệ bằng IAP

Một **bastion** là VM được quản lý trong VPC, có route tới private IP endpoint. Kỹ sư có thể dùng **IAP TCP forwarding** để SSH tới bastion **không cần external IP**, sau đó dùng `gcloud` và `kubectl` ở bastion.

~~~mermaid
flowchart LR
    USER["Laptop kỹ sư"] --> IAP["IAP TCP forwarding"]
    IAP --> B["Bastion VM: internal IP"]
    B --> API["GKE private control-plane IP"]
    API --> K["Kubernetes API resources"]
    IAM["IAM + Kubernetes RBAC"] -. "Phân quyền" .-> API
~~~

Các lớp cần phân biệt:

1. **IAM của IAP** cho phép dùng TCP tunnel đến bastion.
2. **OS Login/SSH policy** kiểm soát ai được vào hệ điều hành bastion.
3. **VPC/private route và firewall** cho phép bastion tới private endpoint.
4. **GKE IAM/Kubernetes authorization** kiểm soát API request tới cluster.

**IAP không trực tiếp biến Kubernetes private endpoint thành một IAP-protected Kubernetes API.** Trong sơ đồ này, IAP bảo vệ đường vào **bastion VM**; Kubernetes API vẫn cần chính sách endpoint và quyền riêng.

### 7.2. Quản trị qua Cloud VPN hoặc Interconnect

Nếu doanh nghiệp đã có HA VPN hoặc Cloud Interconnect:

- Kết nối on-premises/VPC phải quảng bá và học những route phù hợp.
- Private endpoint của control plane phải có đường truy cập được hỗ trợ trong topology.
- Firewall/endpoint access mode và scope địa lý phải cho phép.
- Kubernetes authentication/authorization vẫn áp dụng bình thường.

Không coi **Cloud Router BGP Established** là bằng chứng `kubectl` sẽ thành công. BGP chỉ giải quyết một phần routing; các lớp DNS, TCP 443, endpoint mode, IAM/RBAC và API availability cần xác minh riêng.

### 7.3. Khi nào dùng DNS endpoint?

Một đội phân tán theo nhiều địa điểm có thể cân nhắc DNS endpoint nếu muốn quản trị thông qua **định danh IAM** và các cơ chế bảo vệ được hỗ trợ, thay vì duy trì một VPN cho mỗi máy cá nhân. Nhưng:

- Phải phê duyệt rõ ràng yêu cầu **API có thể được gọi từ loại mạng nào**.
- Phải kiểm tra endpoint authorization, IAM Conditions và VPC Service Controls khi dùng.
- Phải hạn chế principals có quyền nhạy cảm, quản lý MFA và thông tin xác thực CLI.
- Phải kiểm toán sự kiện truy cập và thay đổi cluster.

Nếu chính sách nội bộ yêu cầu chỉ private network path, **không được mặc nhiên bật DNS endpoint để xử lý lỗi timeout**.

## 8. Thực hành gcloud: đọc cấu hình trước khi thay đổi

### 8.1. Chuẩn bị context

Các lệnh trong phần này dùng **Bash**, tài nguyên và project tên giả định. Lệnh có `create`, `update`, `enable` sẽ **thay đổi tài nguyên thật, có thể phát sinh phí và gây mất đường quản trị**; chỉ chạy trong project thử nghiệm đã được phê duyệt.

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"
CLUSTER="retail-private"
NETWORK="retail-vpc"
SUBNET="gke-subnet"

# READ-ONLY: kiểm tra principal và project CLI.
gcloud auth list
gcloud config get-value project

# READ-ONLY: kiểm kê clusters mà tài khoản có thể nhìn thấy.
gcloud container clusters list \
  --project="$PROJECT_ID"
~~~

### 8.2. Đọc toàn bộ cấu hình control plane endpoint

~~~bash
# READ-ONLY: kiểm tra cấu hình GKE đã tồn tại.
gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=yaml
~~~

Trong output cần xem các nhóm trường **khi chúng tồn tại trong schema của cluster**:

| Nhóm thông tin | Câu hỏi |
| --- | --- |
| `privateClusterConfig` | Private nodes và private endpoint được cấu hình như thế nào? |
| `controlPlaneEndpointsConfig` | IP-based và DNS-based endpoint access được thiết lập ra sao trong API/phiên bản hỗ trợ? |
| `masterAuthorizedNetworksConfig` | Có allowlist CIDR cho IP-based endpoint không? |
| `network`, `subnetwork`, `networkConfig` | Cluster nằm ở VPC/subnet nào? |
| `ipAllocationPolicy` | Pod và Service CIDR/secondary ranges nào được sử dụng? |
| `releaseChannel`, version và cluster mode | Cấu hình hoặc tính năng endpoint có phụ thuộc phiên bản/mode không? |

Không dựa vào **một trường** rồi khẳng định cluster là “an toàn”. Kiểm tra endpoint access thực tế, IAM/RBAC, VPC connectivity và chính sách tổ chức. Một số trường hiển thị dạng mới hoặc bị lược bỏ khi chưa được hỗ trợ; dùng `--format=yaml` trước khi xây bộ lọc tự động.

### 8.3. Kiểm tra subnet và secondary ranges

~~~bash
# READ-ONLY: kiểm tra subnet và secondary IP ranges.
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(name,network,ipCidrRange,secondaryIpRanges,privateIpGoogleAccess)"

# READ-ONLY: xem network.
gcloud compute networks describe "$NETWORK" \
  --project="$PROJECT_ID" \
  --format="yaml(name,subnetworks,routingConfig)"
~~~

Nếu VPC dùng **Shared VPC**, subnet thuộc **host project**, còn cluster có thể thuộc service project. Phải đọc/cấp quyền trong đúng project; không tự suy cluster và subnet cùng project chỉ vì tên giống nhau.

## 9. Minh họa tạo private GKE Standard cluster

### 9.1. Thiết kế trước khi chạy lệnh

Giả sử người học đã có:

- Một project lab cho phép tạo GKE.
- VPC `retail-vpc`, subnet `gke-subnet` tại `asia-southeast1`.
- Primary subnet range cho node, secondary ranges tên `gke-pods` và `gke-services` có dung lượng phù hợp.
- Đường truy cập quản trị từ **bastion/VPC** tới private IP endpoint.
- IAM phù hợp, quota, khả năng egress và chi phí cluster/node đã được phê duyệt.
- Một dải IP private **không trùng** dành cho control plane nếu kiến trúc tạo cluster yêu cầu cấp dải riêng.

**Đặc biệt:** lệnh bật private endpoint có thể làm `kubectl` từ máy quản trị bên ngoài VPC **không kết nối được**. Trước khi tạo hoặc chuyển cluster production sang private endpoint, phải xác minh đường quản trị thay thế.

### 9.2. Ví dụ tạo cluster

Lệnh sau minh họa một **GKE Standard cluster** theo mô hình cấu hình private IP endpoint sử dụng master CIDR riêng. Một số mô hình GKE mới dùng endpoint/control-plane networking khác và có yêu cầu khác với `--master-ipv4-cidr`; hãy kiểm tra trợ giúp CLI/tài liệu của loại cluster định tạo.

~~~bash
# WRITE: ví dụ tạo GKE Standard cluster trong sandbox được phép.
gcloud container clusters create retail-private \
  --project=retail-lab \
  --region=asia-southeast1 \
  --network=retail-vpc \
  --subnetwork=gke-subnet \
  --enable-ip-alias \
  --cluster-secondary-range-name=gke-pods \
  --services-secondary-range-name=gke-services \
  --enable-private-nodes \
  --enable-private-endpoint \
  --master-ipv4-cidr=172.16.0.0/28 \
  --num-nodes=1
~~~

Các giá trị chỉ là mẫu học tập; **không thực thi nguyên lệnh nếu subnet ranges, region và control-plane CIDR chưa được kiểm tra**. Với regional Standard cluster, `--num-nodes=1` có thể được hiểu là một node **mỗi zone** theo default node locations, nên số VM và chi phí thực tế có thể lớn hơn một.

Các cờ chính:

| Cờ | Ý nghĩa |
| --- | --- |
| `--enable-ip-alias` | Bật VPC-native/alias IP networking. |
| `--cluster-secondary-range-name` | Chọn secondary range dùng cho Pod IPs. |
| `--services-secondary-range-name` | Chọn secondary range dùng cho Kubernetes Services. |
| `--enable-private-nodes` | Yêu cầu private node networking. |
| `--enable-private-endpoint` | Chọn private IP-based endpoint theo cơ chế hỗ trợ, tránh public IP-based path trong mô hình ví dụ. |
| `--master-ipv4-cidr` | Dải dành cho control-plane connectivity trong những mô hình cluster yêu cầu tham số này. |
| `--num-nodes` | Số node khởi tạo theo semantics của cluster zone/region. |

**Cần kiểm tra DNS-based endpoint một cách độc lập sau khi tạo**, vì chọn private IP endpoint không phải một lời khẳng định về DNS endpoint ở tất cả phiên bản và mode.

### 9.3. Cấu hình endpoint có thể thay đổi theo đời sản phẩm

Trong các triển khai mới, Google Cloud có thể cung cấp chế độ **DNS-based endpoint access**, hoặc các tùy chọn bật/tắt IP access riêng. Khi cập nhật endpoint trên cluster đã tồn tại:

1. Dùng `gcloud container clusters describe` để ghi nhận trạng thái thực.
2. Đọc trợ giúp `gcloud container clusters update --help` của CLI hiện hành.
3. Xác nhận tác động tới cả **IP-based** và **DNS-based** access.
4. Review đường mạng của người dùng, CI/CD, GitOps controller và SRE.
5. Giữ một phiên quản trị hợp lệ để kiểm chứng cấu hình sau thay đổi.

Không đưa ra một lệnh tắt endpoint hàng loạt dùng cho mọi loại cluster, vì sai một flag có thể làm mất đường quản trị trước khi thiết lập xong kênh thay thế.

## 10. Lấy kubeconfig và sử dụng đúng endpoint

### 10.1. Private IP endpoint

Từ **bastion hoặc máy có private route** tới endpoint:

~~~bash
# READ/LOCAL WRITE: lấy cluster info và ghi kubeconfig của người dùng.
gcloud container clusters get-credentials retail-private \
  --project=retail-lab \
  --region=asia-southeast1 \
  --internal-ip

# READ-ONLY Kubernetes API, nhưng cần route, authentication và permission.
kubectl cluster-info
kubectl get namespaces
kubectl get nodes
~~~

`get-credentials` có thể thành công vì nó gọi **Google Cloud Container API** để lấy thông tin cấu hình, nhưng sau đó `kubectl` vẫn **timeout** do máy không có đường đến private Kubernetes API endpoint. Đây là khác biệt quan trọng giữa **quyền lấy cấu hình** và **khả năng mở TCP/TLS tới API server**.

`kubectl get nodes` có thể bị `Forbidden` dù `kubectl cluster-info` hoặc `kubectl get namespaces` hoạt động, nếu Kubernetes authorization không cho phép đọc node resources.

### 10.2. DNS-based endpoint

Đối với cluster đã **bật và cho phép DNS endpoint**:

~~~bash
# READ/LOCAL WRITE: lấy kubeconfig trỏ tới DNS-based endpoint.
gcloud container clusters get-credentials retail-private \
  --project=retail-lab \
  --region=asia-southeast1 \
  --dns-endpoint

# READ-ONLY: xác minh server endpoint và context hiện tại.
kubectl config current-context
kubectl config view --minify
~~~

Nếu DNS endpoint bị tắt, quyền IAM không đủ hoặc chính sách VPC Service Controls chặn, lệnh/hoạt động tiếp theo có thể thất bại. Lấy kubeconfig theo DNS không đồng nghĩa bạn được phép thực hiện mọi Kubernetes operation.

**An toàn khi xem kubeconfig:** file chứa server URL, CA data và cách chạy credential plugin; không đăng nguyên kubeconfig hoặc token ra log/ticket công khai. Tránh dùng `kubectl config view --raw` trong môi trường ghi log không kiểm soát.

### 10.3. `gke-gcloud-auth-plugin`

Các phiên bản GKE/kubectl hiện đại sử dụng **`gke-gcloud-auth-plugin`** để lấy credentials Google Cloud cho quá trình xác thực Kubernetes API. Nếu máy chưa có plugin hoặc CLI đang dùng sai tài khoản, `kubectl` có thể thất bại ngay cả khi route tới endpoint đã đúng.

~~~bash
# READ-ONLY: kiểm tra người dùng gcloud và công cụ auth.
gcloud auth list
gcloud version
gke-gcloud-auth-plugin --version

# READ-ONLY Kubernetes authorization (khi endpoint hoạt động).
kubectl auth can-i list pods -n retail
kubectl auth can-i create deployments -n retail
kubectl auth can-i get secrets -n retail
~~~

`kubectl auth can-i` phản ánh kiểm tra quyền tại thời điểm gọi theo cơ chế API hỗ trợ, không phải công cụ chứng minh toàn bộ IAM/organization policies đều an toàn. Với user/group binding, kiểm tra danh tính thực đang được xác thực và namespace mục tiêu.

### 10.4. Kiểm tra endpoint trong kubeconfig

Sau `get-credentials`, kubeconfig xác định **context**, cluster `server` và phương án auth. Khi có nhiều môi trường:

- Gắn rõ project/cluster/region với từng context.
- Trước khi chạy lệnh ghi, kiểm tra `kubectl config current-context`.
- Dùng `--namespace` hoặc context riêng để tránh sửa nhầm namespace.
- Tách quyền staging/prod và dùng quy trình phê duyệt cho RBAC thay đổi.
- Không commit kubeconfig có thông tin môi trường nhạy cảm vào repository.

## 11. Bảo vệ đường quản trị từ laptop và CI/CD

### 11.1. Người phát triển chỉ cần xem namespace

Ví dụ `developer@example.com` cần xem Pod của namespace `retail`, không cần sửa node pools. Thiết kế:

1. IAM cho phép xác định/đọc cấu hình cluster và xác thực qua endpoint được phê duyệt.
2. Endpoint mode/đường mạng cho phép kết nối.
3. Kubernetes RBAC/IAM authorization chỉ cho phép đọc những resources cần thiết.
4. Logs ghi nhận thao tác quản trị nhạy cảm phù hợp chính sách.

**Không cấp `roles/container.admin` hoặc ClusterRoleBinding `cluster-admin`** chỉ để xử lý lỗi `Forbidden` trên một namespace.

### 11.2. CI/CD deployer

Một pipeline có thể cần cập nhật `Deployment` trong namespace `retail-prod`. Nên phân tách:

- **CI build identity:** xây image và push lên Artifact Registry.
- **Deployer identity:** kết nối Kubernetes API và cập nhật resource được giao.
- **Node identity:** pull image từ Artifact Registry.
- **Pod workload identity:** gọi Cloud SQL/Cloud Storage/Secret Manager khi container chạy.

Nếu CI ở bên ngoài VPC và cluster chỉ có private endpoint, pipeline phải có **đường mạng hợp lệ** như runner trong VPC, VPN/hybrid connectivity hoặc dùng DNS endpoint nếu chính sách cho phép. Không bật public endpoint rồi allow `0.0.0.0/0` chỉ để pipeline chạy.

### 11.3. GitOps/controller trong cluster

Một GitOps controller chạy **bên trong cluster** có thể áp dụng Kubernetes manifests mà không phải cấp đường private IP trực tiếp cho mọi lập trình viên. Tuy vậy:

- Controller có quyền gì trong cluster cần được giới hạn và kiểm tra.
- Cách controller đọc Git/artifact và xác thực cần an toàn.
- Nguồn manifests/revision phải được review và theo dõi provenance.
- Những cập nhật lên cluster cấp cao hoặc RBAC nhạy cảm cần quy trình riêng.
- Nếu cluster/control plane có sự cố, cơ chế GitOps có thể chưa xử lý được cho tới khi control plane phục hồi.

Đây là một kiến trúc vận hành, **không phải lý do vô hiệu hóa authentication/authorization của Kubernetes API**.

## 12. Không nhầm bảo vệ control plane với bảo mật workload

### 12.1. Private cluster vẫn có thể có public Service

Một cluster dùng private nodes/private endpoint vẫn có thể triển khai một **external Application Load Balancer** hoặc một `Service` kiểu `LoadBalancer` public theo loại controller/config được hỗ trợ. Điều này hoàn toàn khác với **public control-plane endpoint**:

~~~text
Kubernetes API (control plane):
  private IP-based endpoint cho quản trị

Frontend ứng dụng:
  HTTPS load balancer public → Ingress/Gateway/Service → Pods
~~~

Muốn ứng dụng **chỉ nội bộ**, cần cấu hình **internal load balancer**, đúng annotations/controller, firewall và authentication. Không trông chờ private nodes tự biến toàn bộ ứng dụng thành private.

### 12.2. Pod-to-Pod và egress policy

Sau khi control plane được bảo vệ, workloads vẫn cần:

- **Kubernetes NetworkPolicy** hoặc policy của GKE Dataplane V2 nếu có để giới hạn traffic giữa namespaces/Pods.
- **Workload Identity Federation for GKE** để Pod gọi Google APIs với quyền tối thiểu, không dùng key tĩnh.
- **Pod Security Standards / admission controls** để giảm rủi ro privileged containers.
- **Image provenance**, Artifact Registry access, vulnerability scanning và Binary Authorization nếu phù hợp.
- **Secrets management**, KMS và rotation theo yêu cầu dữ liệu.
- **Cloud Logging/Monitoring** với quyền truy cập audit phù hợp.

Node không có external IP không ngăn một Pod gửi dữ liệu ra Internet nếu bạn đã cấu hình Cloud NAT và egress policy cho phép. Muốn kiểm soát egress, cần kiểm tra chính sách cấp Pod, VPC và NAT/proxy.

### 12.3. GKE Standard và Autopilot

Standard và Autopilot khác nhau ở quyền kiểm soát node, cách quản lý tài nguyên và những lựa chọn networking/security hỗ trợ. Khi đọc ví dụ `gcloud container clusters create ...`:

- Ví dụ ở phần 9 dành cho **Standard cluster**.
- Với **Autopilot**, sử dụng quy trình `create-auto` và kiểm tra private networking/control-plane endpoint settings được sản phẩm hỗ trợ.
- Không chép tất cả các cờ `--num-nodes`, node-pool hay master CIDR của Standard sang Autopilot.
- Đánh giá giá trị Autopilot dựa trên mức quản trị, workload và chi phí thực, không chỉ vì có từ “private”.

## 13. Tình huống triển khai: retail production GKE

### 13.1. Yêu cầu

Một doanh nghiệp sử dụng:

- **GKE Standard regional cluster** chạy `catalog-api` và các worker bất đồng bộ.
- **Cloud Run** cung cấp một phần API ở ngoài cluster.
- **Artifact Registry** chứa images đã kiểm tra.
- **Cloud SQL** dùng private connectivity trong vùng được thiết kế.
- **Cloud Storage** lưu ảnh sản phẩm.
- Hệ thống nội bộ doanh nghiệp kết nối qua **HA VPN/Interconnect** để quản trị.
- CI/CD thực hiện rollout qua danh tính riêng.

Yêu cầu bảo mật:

1. GKE nodes không có external IP.
2. Không dựa vào public IP-based control-plane endpoint cho quản trị.
3. Người ở văn phòng/SRE có đường tới Kubernetes API theo chính sách.
4. CI/CD không được cluster-admin vô thời hạn.
5. Pod chỉ có quyền gọi các Google APIs cần thiết.

### 13.2. Thiết kế đề xuất

| Hạng mục | Quyết định minh họa | Điểm cần kiểm chứng |
| --- | --- | --- |
| Cluster | GKE Standard regional, VPC-native. | Secondary IP ranges, số zone, quota và phiên bản. |
| Nodes | Private nodes, node SA riêng. | Không external IP; egress và pull images hoạt động. |
| Control plane | Private IP-based endpoint; DNS endpoint theo chính sách tổ chức (bật hoặc tắt có chủ đích). | Có/không có đường quản trị ngoài dự kiến. |
| Đường cho SRE | Hybrid route tới private endpoint hoặc IAP bastion trong VPC. | DNS/TCP 443, endpoint access và authn/authz. |
| Truy cập namespace | Kubernetes Role/RoleBinding/Google IAM authorization phù hợp. | Không cấp quyền sửa cluster-wide nếu không cần. |
| CI/CD | Runner có network path; deployer identity có scope hẹp. | Không dùng key JSON dài hạn hoặc bypass allowlist. |
| Image pull | Node identity có Reader tại Artifact Registry. | Cross-project repo IAM, OAuth scopes và egress. |
| Pod identity | Workload Identity Federation for GKE. | Quyền Cloud SQL/Storage/Secret Manager tối thiểu. |
| Service exposure | Application LB public hoặc internal theo từng API. | Không nhầm Service public với control plane public. |
| Giám sát | Audit Logs, `kubectl` failures, node readiness, SLI ứng dụng. | Có runbook và cảnh báo đúng lớp. |

### 13.3. Luồng một lần triển khai

~~~mermaid
sequenceDiagram
    participant DEV as Developer
    participant CI as CI/CD
    participant AR as Artifact Registry
    participant API as GKE private control plane
    participant N as GKE node
    participant W as Pod workload
    DEV->>CI: Merge commit được duyệt
    CI->>AR: Push image, nhận digest
    CI->>API: Kubernetes API qua đường quản trị được phép
    Note over CI,API: IAM, endpoint access và authorization
    API->>N: Điều phối Pod/Deployment
    N->>AR: Pull image bằng node identity
    N->>W: Khởi chạy container
    W-->>API: Readiness / resource status
    W->>AR: Không cần push image trong runtime
~~~

Luồng thực tế phức tạp hơn (scheduler, kubelet, admission và controller). Điểm chính là **đường CI→control plane**, **đường node→registry**, và **quyền Pod→dữ liệu** là ba nhóm kiểm soát độc lập.

### 13.4. Diễn tập sự cố

1. **SRE ngoài VPC không gọi được API:** kiểm tra private route/bastion thay vì mở public endpoint không kiểm soát.
2. **CI `Forbidden` khi cập nhật Deployment:** kiểm tra Kubernetes authorization và principal, không tự cấp cluster-admin.
3. **Pod `ImagePullBackOff`:** kiểm tra node identity, registry URI và egress; không sửa control-plane endpoint.
4. **App API public bị truy cập trái phép:** kiểm tra ingress/load balancer/WAF/authentication; private control plane không bảo vệ HTTP API người dùng.
5. **Toàn bộ node không lấy được image:** kiểm tra Artifact Registry access, NAT/PGA/registry DNS và chính sách mạng.
6. **VPN on-prem mất:** kiểm thử đường quản trị dự phòng (bastion hoặc endpoint mode được phê duyệt), người chịu trách nhiệm và thời gian phục hồi.

## 14. Troubleshooting: phân biệt mạng, danh tính và Kubernetes RBAC

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `gcloud get-credentials` thành công, `kubectl` timeout | Máy không có route tới private IP endpoint, VPN/bastion/firewall hoặc DNS không phù hợp. | Đọc kubeconfig server, cluster endpoint config, kiểm tra TCP 443 và network path. |
| `kubectl` báo `Unauthorized`/401 | Token hoặc auth plugin sai/hết hạn, principal không được chấp nhận. | `gcloud auth list`, `gke-gcloud-auth-plugin`, phiên xác thực. |
| `kubectl` báo `Forbidden`/403 | Principal đã xác thực nhưng không được phép thao tác Kubernetes; IAM/RBAC/endpoint policy. | `kubectl auth can-i`, RoleBindings, IAM permissions và logs. |
| `get-credentials --internal-ip` rồi truy cập từ Cloud Shell thất bại | Cloud Shell không tự nằm trong cùng VPC/private route tới control plane. | Dùng đường quản trị được phê duyệt; không mở public IP tùy tiện. |
| DNS endpoint không hoạt động | Chưa bật DNS access, IAM thiếu, VPC SC/policy hoặc DNS/egress lỗi. | Endpoint config, principal, API access và logs. |
| Private endpoint chỉ truy cập được từ một phần mạng | Routing/peering, authorized networks cho private endpoint khi áp dụng hoặc giới hạn region/global access. | Kiểm tra network paths, endpoint mode và CIDR thực tế. |
| Cluster tạo thành công nhưng nodes `NotReady` | Node egress/GKE management path, VM startup, quota, firewall hoặc guest/system issue. | GKE/node pool status, node logs, VPC/firewall/Google APIs. |
| Pod `ImagePullBackOff` | Node identity thiếu Reader, sai image URI/digest, OAuth scopes hoặc egress. | `kubectl describe pod`, Artifact Registry IAM, node network. |
| Pod không gọi được Cloud Storage | Workload identity/IAM, DNS/Google APIs egress, thiếu token hoặc VPC SC. | ServiceAccount mapping, IAM, request logs, network. |
| External Service không truy cập được | Load balancer/Ingress controller, firewall, backend health, DNS hoặc app auth. | LB frontend/backend health và app logs, không tập trung vào control plane. |
| CI vẫn có thể sửa cluster sau khi thu hồi một RoleBinding | Có binding khác, IAM authorization, group hoặc quyền cấp ở phạm vi cao hơn. | Đánh giá quyền hiệu lực và audit, không chỉ một file RBAC. |

### 14.1. Quy trình điều tra bảy bước

1. **Đúng cluster?** Đọc project, region, cluster name, kubecontext và server endpoint.
2. **Endpoint đang bật loại nào?** Đọc IP/DNS endpoint config, private/public access, authorized networks.
3. **Máy đang ở mạng nào?** Laptop, Cloud Shell, bastion, VPC runner, VPN hay một region khác.
4. **Có TCP/TLS tới Kubernetes API không?** Nếu không, ưu tiên route, DNS, firewall và endpoint mode.
5. **Có authentication không?** Kiểm tra gcloud principal, credential plugin, token và IAM.
6. **Có authorization không?** Kiểm tra `kubectl auth can-i`, RBAC/IAM và namespace.
7. **Workload có khỏe không?** Nếu API truy cập được nhưng Pod lỗi, chuyển sang node, registry, network policy và ứng dụng.

Đừng điều tra một lỗi `403 Forbidden` bằng việc thay Pod CIDR. Đừng sửa IAM khi lỗi thực sự là timeout đến private endpoint.

## 15. Audit, thay đổi cấu hình và khôi phục quản trị

### 15.1. Những sự kiện cần theo dõi

- Ai tạo/xóa GKE cluster hoặc cập nhật endpoint access, authorized networks, network settings?
- Ai cấp role IAM hoặc tạo/sửa RoleBinding/ClusterRoleBinding nhạy cảm?
- Principal nào đăng nhập/triển khai workload trong cluster, theo log/audit được bật?
- Có thay đổi node pools, network policies, service accounts hoặc ingress public ngoài quy trình không?
- Có lần `kubectl` thất bại do xác thực, mạng hoặc thiếu quyền tăng đột biến không?
- Tỷ lệ API operations thành công, trạng thái control plane/nodes và SLO ứng dụng thế nào?

**Cloud Audit Logs và GKE/Kubernetes control plane logging** có phạm vi, loại log, chi phí và chính sách giữ riêng. Không tự khẳng định mọi lần đọc resource hoặc mọi lệnh `kubectl` đã được ghi mặc định; cần kiểm tra từng loại audit log và cấu hình cụ thể.

### 15.2. Tránh tự khóa quyền truy cập

Những thay đổi dễ gây mất đường quản trị:

1. Chuyển sang private IP endpoint khi CI/SRE chỉ kết nối từ Internet.
2. Tắt DNS endpoint trong khi pipeline chỉ dùng `--dns-endpoint`.
3. Thu hẹp authorized networks nhưng quên IP NAT egress thực tế của đội vận hành.
4. Xóa RoleBinding của nhóm platform admin trước khi có quyền thay thế hợp lệ.
5. Thay firewall/VPN route mà không kiểm tra private control-plane traffic.

Trước khi thay đổi:

- Ghi lại cấu hình endpoint, IAM/RBAC và VPC routes hiện có.
- Thiết lập **đường quản trị thay thế** đã được thử nghiệm từ đúng principal.
- Review chính sách bằng IaC/merge request, xác định người phê duyệt.
- Có quy trình rollback/break-glass được tổ chức cho phép và nhật ký sự kiện.
- Sau thay đổi, thử `get-credentials` và một `kubectl get` theo đúng endpoint/proxy.

Không mặc định “luôn có thể mở lại API bằng một lệnh khác” nếu principal đã bị thu hồi quyền hoặc đường mạng bị cắt. Kế hoạch khôi phục phải được thiết kế và tập dượt trước.

### 15.3. Tự động hóa quản trị

Terraform hoặc công cụ Infrastructure as Code phù hợp có thể quản lý cluster, VPC/subnet, endpoint mode, IAM và node pools. Kubernetes manifests/GitOps quản lý các resource trong cluster theo quy tắc ownership.

Cần tránh xung đột giữa:

- IaC quản lý IAM/cluster configuration.
- GKE tự tạo/quản lý firewall rules và thành phần nền.
- GitOps/Helm quản lý Kubernetes RoleBindings/Deployments.
- Người vận hành chỉnh tay qua Console hoặc `gcloud`.

Thiết lập **source of truth**, review và cơ chế drift detection để không tạo trường hợp công cụ A vừa bật endpoint thì công cụ B tự tắt lại ở lần apply tiếp theo.

## 16. Chi phí và độ tin cậy

### 16.1. Private cluster có miễn phí hay không?

**Không.** Mô hình private networking là một lựa chọn kiến trúc và bảo mật. Chi phí có thể đến từ:

| Thành phần | Chi phí cần tính |
| --- | --- |
| GKE cluster | Phí quản lý cluster theo chế độ và điều kiện hiện hành; Standard/Autopilot có mô hình khác nhau. |
| Compute/node pools | vCPU, memory, VM disks, node pool sizing và autoscaling. |
| Networking | Cloud NAT, VPN/Interconnect, load balancer, data transfer, IP/network services khi áp dụng. |
| Artifact pull | Artifact Registry storage/transfer, network path và các dịch vụ liên quan. |
| Logging/monitoring | Log volume, retention, metrics/traces và audit theo chính sách giá. |
| Bảo mật/quản trị | Bastion VM, IAP/đường quản trị, policy và các giải pháp bổ sung được dùng. |

Không có external IP trên nodes không đồng nghĩa **không có outbound traffic charge** hoặc **không cần Cloud NAT**. Cloud NAT nếu sử dụng có mô hình giá riêng. Tương tự, VPN dự phòng có thể nâng độ tin cậy đường quản trị nhưng phải tính cả chi phí và failure domains.

### 16.2. Control plane HA không thay thế workload HA

GKE quản lý control plane theo thiết kế dịch vụ, nhưng độ sẵn sàng ứng dụng còn phụ thuộc:

- Có đủ replicas ở nhiều nodes/zones phù hợp không?
- Readiness/liveness probes và PodDisruptionBudgets có hợp lý không?
- Cluster autoscaling có đủ quota và capacity không?
- Dữ liệu Cloud SQL/Storage, kết nối VPC và backend load balancer có khả dụng không?
- CI/CD có fallback khi control-plane endpoint tạm không truy cập được không?

Một cluster có private endpoint thiết kế tốt nhưng chỉ có **một Pod** xử lý mọi giao dịch vẫn có thể ngừng dịch vụ khi Pod chết. Đo SLO từ góc nhìn người dùng thay vì chỉ trạng thái API server.

### 16.3. Những chỉ số vận hành hữu ích

- Phần trăm cluster có endpoint access đáp ứng chính sách.
- Số principal có quyền cluster-admin hoặc IAM quản trị nhạy cảm.
- Tỷ lệ deployment thành công và lỗi `kubectl` do authorization/network.
- Node readiness, Pod scheduling latency, image pull failures.
- Kết nối từ on-premises/bastion/CI runner tới private endpoint.
- Số thay đổi policy/network ngoài lịch bảo trì, thời gian khôi phục.
- Lưu lượng logs và chi phí mạng/cluster theo dự toán.

## 17. Bài tập thực hành

### Bài 1 — Private nodes có đủ không?

Một GKE cluster bật private nodes nhưng vẫn có public IP-based Kubernetes API endpoint. Có được khẳng định API “không thể truy cập từ Internet” không? Nếu tổ chức muốn đường quản trị private-only, cần kiểm tra thêm những endpoint nào?

**Gợi ý:** không. Kiểm tra IP-based public/private endpoint và DNS-based endpoint độc lập; thiết kế kênh quản trị private và IAM/RBAC.

### Bài 2 — `get-credentials` thành công nhưng `kubectl` timeout

Một kỹ sư chạy `gcloud container clusters get-credentials ... --internal-ip` từ laptop tại nhà. Lệnh lấy credentials thành công, `kubectl get pods` lại timeout. Hãy giải thích vì sao hai kết quả không mâu thuẫn và đề xuất một đường truy cập được kiểm soát.

**Gợi ý:** Container API trả metadata cho kubeconfig, nhưng laptop không có private route tới control plane; dùng VPN hoặc IAP bastion nếu được phê duyệt.

### Bài 3 — IAM và RBAC

Một developer phải đọc Pod/Service của namespace `retail`, nhưng không được sửa cluster-wide RBAC. Hãy mô tả quyền IAM để xem/kết nối cluster, Role/RoleBinding hẹp cho namespace và cách kiểm tra bằng `kubectl auth can-i`. Vì sao không cấp `cluster-admin`?

### Bài 4 — DNS endpoint và authorized networks

Đội hạ tầng đã cấu hình Master Authorized Networks cho public IP-based endpoint. Sau đó bật DNS-based endpoint. Danh sách IP allowlist đó có tự động giới hạn DNS endpoint cùng một cách không? Cần kiểm soát thêm lớp nào?

**Gợi ý:** không. Xem IAM, endpoint access policy, VPC Service Controls khi hỗ trợ và quyền Kubernetes; quyết định rõ yêu cầu mạng của doanh nghiệp.

### Bài 5 — Private node không pull được image

GKE private nodes báo `ImagePullBackOff` khi image nằm trong Artifact Registry project khác. Hãy kiểm tra node service account, IAM Reader trên repo nguồn, OAuth scopes nếu áp dụng, DNS/egress tới registry và image URI. Vì sao sửa RoleBinding của developer chưa chắc giải quyết lỗi?

### Bài 6 — Thiết kế cluster phục vụ retail

Giả sử GKE, Cloud SQL và Cloud Run ở Singapore; mạng doanh nghiệp dùng VPN; ảnh ở Cloud Storage và image ở Artifact Registry. Hãy đề xuất:

- Private/public/DNS control-plane endpoint mode.
- Đường vào Kubernetes API của SRE/CI.
- Pod/Service CIDR và kiểm tra không trùng mạng on-premises.
- Phân tách IAM của CI, node, Pod runtime.
- Các chỉ số SLO, cách kiểm thử mất VPN và thủ tục khôi phục.

### Bài 7 — Tìm lỗi sai tầng

`kubectl get pods` hoạt động nhưng Pod không đọc được Secret Manager. Lỗi này có bắt buộc do control-plane endpoint không? Nêu các bước kiểm tra Workload Identity Federation for GKE, IAM Secret Manager, DNS/Google APIs egress và logs ứng dụng.

### Bài 8 — Kịch bản tự khóa quyền

Một đội muốn tắt public IP endpoint và DNS endpoint trong production, nhưng CI hiện chỉ chạy trên hosted runner ngoài VPC. Hãy lập kế hoạch migration đường CI trước khi đổi cấu hình endpoint, cùng bước kiểm tra và rollback.

## 18. Checklist production và tài liệu chính thức

| Hạng mục | Điều cần xác minh trước triển khai |
| --- | --- |
| **Cluster mode** | Standard/Autopilot và phiên bản GKE hỗ trợ cấu hình endpoint dự kiến. |
| **Private nodes** | Không external IP; có đường egress cho images, quản lý nodes và Google APIs. |
| **IP endpoints** | Public/private IP endpoint mode phù hợp chính sách; không suy từ tên cluster. |
| **DNS endpoint** | Đã phê duyệt bật/tắt, IAM và VPC SC khi áp dụng được xem xét riêng. |
| **Master Authorized Networks** | CIDR hẹp trên IP endpoints được hỗ trợ, không nhầm với DNS endpoint IAM. |
| **VPC/IP planning** | Primary node range, Pod/Service secondary ranges và control-plane range không overlap. |
| **Hybrid access** | VPN/Interconnect, route, master global access khi cần và đường đi về hợp lệ. |
| **Bastion/IAP** | Bastion được bảo vệ, IAM IAP, OS Login/SSH, logs và network path được kiểm tra. |
| **IAM** | Ai quản trị cluster, ai đọc metadata, ai được connect/deploy theo phạm vi tối thiểu. |
| **Kubernetes authorization** | RBAC/IAM resource permissions, namespace boundaries, quyền cluster-admin được review. |
| **Workload identity** | Node identity/pull image tách Pod runtime identity và quyền dữ liệu. |
| **Network segmentation** | Ingress/LB, NetworkPolicy, firewall và egress policy theo workload. |
| **Logging/audit** | Control plane, IAM, endpoint/network changes và sự kiện Kubernetes nhạy cảm được giám sát. |
| **CI/CD** | Có đường API hợp lệ, image digest, review manifests, rollback và xác thực ngắn hạn. |
| **Resilience** | Runbook tránh lockout, multi-zone Pods, kịch bản mất VPN hoặc endpoint. |
| **Cost** | GKE/node/network/NAT/VPN/bastion/logging/transfer được dự toán và theo dõi. |

Tài liệu Google Cloud chính thức để đối chiếu theo cluster mode, phiên bản và khả năng endpoint mới nhất:

- [GKE cluster networking overview](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-networking)
- [GKE private clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/private-cluster-concept)
- [Create a private GKE Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/legacy/network-isolation)
- [Customize control plane access](https://cloud.google.com/kubernetes-engine/docs/how-to/control-plane-authorized-networks)
- [GKE DNS-based endpoint](https://cloud.google.com/kubernetes-engine/docs/concepts/about-control-plane-endpoints)
- [GKE access control](https://cloud.google.com/kubernetes-engine/docs/concepts/access-control)
- [Kubernetes RBAC with GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/role-based-access-control)
- [GKE Workload Identity Federation](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [VPC-native clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips)
- [Private Google Access](https://cloud.google.com/vpc/docs/private-google-access)
- [IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding)
- [gcloud container clusters reference](https://cloud.google.com/sdk/gcloud/reference/container/clusters)

**Điểm cần nhớ:** GKE private nodes giảm bề mặt mạng của **worker nodes**, còn control-plane access phải được bảo vệ **riêng** bằng lựa chọn IP/DNS endpoint, đường kết nối được phê duyệt, IAM và Kubernetes authorization. Private IP không thay thế RBAC; DNS endpoint không đồng nghĩa private IP; IAM không sửa được một lỗi routing. Khi phân tách đúng các lớp đó, đội vận hành có thể quản trị cluster an toàn, giữ đường phục hồi và triển khai ứng dụng có độ tin cậy cùng chi phí kiểm soát được.
