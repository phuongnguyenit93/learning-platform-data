# Kiến trúc EKS control plane và data plane

> **Chương:** Kubernetes với EKS  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; học cách chọn dịch vụ, thiết kế hệ thống an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

**Amazon Elastic Kubernetes Service (Amazon EKS)** là dịch vụ Kubernetes được AWS quản lý. Thay vì tự triển khai, vá lỗi và duy trì toàn bộ cụm Kubernetes, nhóm phát triển có thể để AWS quản lý các thành phần trọng yếu của **control plane** và lựa chọn cách cung cấp tài nguyên tính toán cho **data plane**.

Tuy nhiên, “managed Kubernetes” **không đồng nghĩa AWS vận hành thay toàn bộ ứng dụng**. Một cụm có control plane được phân tán nhiều Availability Zone vẫn có thể mất dịch vụ nếu Pod chỉ chạy trên một node, các subnet hết địa chỉ IP, lệnh deploy làm toàn bộ replica không khỏe hoặc ứng dụng phụ thuộc một database duy nhất.

Sau bài học, bạn có thể:

1. Phân biệt chính xác **control plane** và **data plane**; mô tả vai trò của `kube-apiserver`, `etcd`, scheduler, controller manager, kubelet và container runtime.
2. Giải thích AWS quản lý những gì trong **EKS-managed control plane** và người vận hành vẫn phải chịu trách nhiệm ở các lựa chọn data plane khác nhau.
3. So sánh **EKS managed node groups**, **self-managed EC2 nodes**, **AWS Fargate** và **EKS Auto Mode**.
4. Theo dõi một lần `kubectl apply` từ API server đến scheduler, kubelet, Pod và đường vào ứng dụng.
5. Hiểu vai trò của VPC, subnet/AZ, cluster endpoint, control-plane ENI, AWS VPC CNI, CoreDNS, kube-proxy, load balancer và storage.
6. Phân biệt **IAM authentication/access entries**, **Kubernetes RBAC** và quyền AWS được cấp cho ứng dụng chạy trong Pod.
7. Đề xuất khả năng sẵn sàng, giám sát, autoscaling, bảo mật, backup/restore và chi phí cho cụm production.
8. Dùng AWS CLI và `kubectl` với các lệnh **chỉ đọc** để quan sát một cụm EKS được cấp quyền.

## 1. EKS là gì, và Kubernetes cần những lớp nào?

Kubernetes quản lý **trạng thái mong muốn** của workload: số Pod cần chạy, container image, tài nguyên CPU/RAM, cổng dịch vụ, cách cập nhật phiên bản, quyền truy cập và các đối tượng khác. Các bộ điều khiển liên tục đối chiếu trạng thái thực với trạng thái khai báo rồi thực hiện thay đổi trong phạm vi có thể.

Kiến trúc thường được tách thành:

| Lớp | Thành phần chính | Trách nhiệm |
|---|---|---|
| **Control plane** | API server, etcd, scheduler, controller manager | Nhận cấu hình, lưu trạng thái, ra quyết định lập lịch, điều khiển vòng đời đối tượng |
| **Data plane** | Worker nodes, kubelet, container runtime, Pod/containers | Thực thi workload và xử lý lưu lượng của ứng dụng |
| **Networking** | CNI, CoreDNS, Service networking, load balancing | Cấp IP Pod, phân giải tên, chuyển traffic giữa dịch vụ và client |
| **Storage** | CSI driver, PV/PVC, EBS/EFS và dịch vụ khác | Gắn/gỡ volume, cung cấp lưu trữ cần thiết cho Pod |
| **Identity & security** | IAM, access entries/RBAC, Pod Identity/IRSA, security controls | Xác thực quản trị, phân quyền Kubernetes và quyền gọi AWS API |
| **Operations** | Logs, metrics, autoscaling, upgrades, backup và IaC | Theo dõi, bảo trì, khôi phục và kiểm soát chi phí |

### 1.1. Sơ đồ cụm EKS

~~~mermaid
flowchart TB
    Dev[Người vận hành / CI-CD] -->|kubectl + AWS IAM auth| EP[EKS Kubernetes API endpoint]
    subgraph CP["Control plane do EKS quản lý - AWS-managed environment"]
        API[kube-apiserver]
        ETCD[(etcd - trạng thái Kubernetes)]
        SCH[kube-scheduler]
        CM[kube-controller-manager]
        API <--> ETCD
        SCH <--> API
        CM <--> API
    end
    EP --> API
    subgraph VPC["Customer VPC - nhiều AZ"]
        subgraph AZA["AZ-A"]
            N1[Worker node A]
            P1[Pod frontend]
            P2[Pod API]
            N1 --> P1
            N1 --> P2
        end
        subgraph AZB["AZ-B"]
            N2[Worker node B]
            P3[Pod frontend]
            P4[Pod API]
            N2 --> P3
            N2 --> P4
        end
        LB[ALB / NLB theo thiết kế] --> N1
        LB --> N2
    end
    API <-->|Kubernetes API / kết nối vận hành| N1
    API <-->|Kubernetes API / kết nối vận hành| N2
~~~

Sơ đồ trên là **mô hình khái niệm**, không biểu diễn đầy đủ từng luồng trong VPC hay tài nguyên riêng của AWS. AWS duy trì control plane trong môi trường do AWS quản lý; phần workload thường hiện diện trong subnet của VPC do khách hàng lựa chọn (với các ngoại lệ và chế độ data plane cụ thể).

**Phân biệt quan trọng:** control plane là nơi **điều phối**, không phải nơi chạy ứng dụng Java/Web/API của bạn. Các container workload chạy trên data plane mà bạn chọn.

### 1.2. EKS khác cụm Kubernetes tự dựng như thế nào?

Với cụm Kubernetes tự quản lý trên EC2, nhóm vận hành phải tự thiết kế, triển khai, thay thế, vá lỗi, sao lưu và mở rộng cả API server, etcd và các thành phần control plane. Với EKS chuẩn:

- AWS cung cấp và vận hành **Kubernetes control plane** được quản lý.
- Bạn vẫn quyết định **cluster configuration**, phiên bản được hỗ trợ, kết nối VPC, quyền truy cập và cách vận hành workloads.
- Data plane có nhiều mô hình quản lý; mức trách nhiệm của bạn phụ thuộc lựa chọn.
- Việc **nâng cấp phiên bản Kubernetes** vẫn cần lập kế hoạch: AWS quản lý hạ tầng control plane, nhưng ứng dụng, admission policies, add-ons, node versions và API deprecations cần được đánh giá.

## 2. Control plane: bộ não của cụm

### 2.1. kube-apiserver — cổng điều khiển

`kube-apiserver` cung cấp Kubernetes API cho:

- `kubectl`, CI/CD pipeline và các công cụ quản trị;
- controllers/scheduler/kubelets theo quyền được cấu hình;
- các Kubernetes operators và controllers do ứng dụng cài đặt.

Khi bạn chạy:

~~~bash
kubectl apply -f deployment.yaml
~~~

client gửi yêu cầu đến API server. Máy chủ kiểm tra authentication/authorization, admission và tính hợp lệ của đối tượng trước khi ghi nhận trạng thái mong muốn vào hệ thống.

**Lỗi hay gặp:** `kubectl get pods` trả `Unauthorized` hoặc `Forbidden` không nhất thiết là cluster bị lỗi. Cần phân biệt **kết nối tới API endpoint**, **AWS IAM authentication**, **EKS access entries/legacy access mapping** và **Kubernetes RBAC**.

### 2.2. etcd — lưu trạng thái Kubernetes

**etcd** là kho key-value nhất quán dùng để lưu trạng thái của Kubernetes:

- Deployment, Pod, Service và metadata liên quan;
- ConfigMap, Secret và nhiều đối tượng cấu hình;
- trạng thái cần để controllers tái lập, điều phối và quan sát hệ thống.

Trong EKS, AWS quản lý etcd thuộc control plane. Người vận hành **không SSH trực tiếp vào các nút etcd** như một cụm tự dựng. Dù etcd do AWS quản lý, bạn vẫn chịu trách nhiệm với **cấu hình ứng dụng**, nguồn manifest/IaC, chiến lược backup dữ liệu ứng dụng và quy trình phục hồi những đối tượng bạn sở hữu.

**Kubernetes Secret không mặc nhiên là kho bí mật dành cho mọi ứng dụng production**: cần đánh giá mã hóa, RBAC, audit, rotation và việc dùng AWS Secrets Manager/Parameter Store cùng cơ chế tích hợp thích hợp.

### 2.3. kube-scheduler — chọn node cho Pod

Scheduler quan sát các Pod chưa được gán node rồi chọn vị trí chạy có thể đáp ứng điều kiện:

- `resources.requests` CPU và RAM;
- `nodeSelector`, node affinity/anti-affinity;
- taints và tolerations;
- `topologySpreadConstraints` để phân bố giữa node/AZ;
- volume topology, khả năng mạng và ràng buộc khác.

Scheduler **không tạo CPU hoặc RAM mới** nếu toàn bộ nodes thiếu capacity. Pod có thể ở `Pending` cho tới khi có node phù hợp, autoscaler cấp thêm node hoặc yêu cầu tài nguyên được điều chỉnh.

### 2.4. kube-controller-manager — duy trì trạng thái mong muốn

Controller manager chạy những controller vòng lặp, chẳng hạn theo dõi node, ReplicaSet, Deployment hoặc endpoint theo những chức năng Kubernetes tương ứng. Trong luồng thường gặp:

1. Bạn khai báo Deployment có 3 replicas.
2. Controller tạo/điều chỉnh ReplicaSet và các Pod.
3. Scheduler gán Pod vào node.
4. kubelet trên node tạo container để hoàn thành trạng thái mong muốn.
5. Nếu Pod biến mất và vẫn còn capacity phù hợp, controllers tạo Pod thay thế.

**Lưu ý:** controller chỉ có thể đạt trạng thái mong muốn nếu điều kiện thực tế cho phép, ví dụ có tài nguyên, quyền, image và network.

### 2.5. EKS quản lý độ sẵn sàng của control plane

AWS vận hành các thành phần control plane với cơ chế dự phòng trên **nhiều Availability Zones trong một Region**, quản lý thay thế thành phần lỗi và bảo trì cơ sở hạ tầng. API server và etcd không phải do bạn trực tiếp đặt trên EC2 node groups của mình.

Tuy nhiên:

- Control plane HA **không tự phân bố application Pods** trên nhiều AZ.
- Control plane khỏe **không bảo đảm mọi Pod khỏe**, API service hoạt động tốt hoặc database không lỗi.
- Quy trình nâng cấp, sửa policies, giới hạn quota hoặc sự cố kết nối API vẫn có thể ảnh hưởng vận hành.
- **Control plane logging** cần cấu hình chủ động; không mặc định mọi log Kubernetes đã được lưu vô hạn trong CloudWatch.

## 3. Data plane: nơi chạy container thực tế

### 3.1. Worker node gồm những gì?

Với mô hình EC2 nodes, mỗi worker node thường có:

- Hệ điều hành/AMI và kernel;
- **kubelet**: nhận PodSpec được gán, làm việc với container runtime và báo trạng thái;
- **container runtime** như containerd, tùy AMI/phiên bản EKS hỗ trợ;
- CNI networking và thành phần service routing như `kube-proxy`, theo mô hình cụm;
- Pod workload: web/API, workers, ingress controllers hoặc agents.

~~~mermaid
flowchart TD
    API[EKS kube-apiserver] -->|PodSpec và watch| K[kubelet trên EC2 node]
    K --> CR[Container runtime]
    CR --> P1[Pod: api-service]
    CR --> P2[Pod: background-worker]
    CNI[AWS VPC CNI / networking] --> P1
    CNI --> P2
    DNS[CoreDNS service] -. Phân giải dịch vụ .-> P1
    DNS -. Phân giải dịch vụ .-> P2
~~~

**CoreDNS** thường là Kubernetes Deployment/Pods chạy trên data plane chứ không nằm trong AWS-managed control plane. Tương tự, nhiều add-ons được cài ở namespace như `kube-system` và cần node/compute để chạy.

### 3.2. Các lựa chọn data plane

| Mô hình | Ai cung cấp/nâng cấp compute? | Phù hợp khi nào? | Điều vẫn phải quản lý |
|---|---|---|---|
| **EKS managed node groups** | AWS tự động hóa nhiều bước vòng đời EC2 Auto Scaling nodes | Phần lớn workloads EC2 cần quản lý node đơn giản | Type/size, scaling, AMI/version strategy, workload, quyền, addons, maintenance |
| **Self-managed EC2 nodes** | Người vận hành tự điều phối EC2, bootstrap, update và lifecycle | Cần cấu hình host đặc thù hoặc kiểm soát sâu | Hầu như toàn bộ vòng đời node, vá lỗi và bootstrap |
| **AWS Fargate for EKS** | AWS cung cấp compute chạy Pod, không cần quản lý EC2 worker nodes | Một số workload phù hợp mô hình serverless Pods | Fargate profiles, resources, subnet/network, IAM, ứng dụng, giới hạn tính năng |
| **EKS Auto Mode** | AWS tự động quản lý nhiều thành phần compute/network/storage cho workloads theo chế độ này | Muốn giảm vận hành cụm/EC2 nodes và autoscaling | Cấu hình intent, workloads, IAM/security, giới hạn khả năng tương thích, chi phí |
| **Hybrid Nodes** (khi triển khai phù hợp) | Nodes có thể ở hạ tầng on-premises/edge theo tính năng EKS | Cần vận hành workloads ngoài AWS với control plane EKS | Kết nối mạng, host/lifecycle, bảo mật, độ trễ, hỗ trợ dịch vụ |

Tính năng và giới hạn của từng chế độ có thể thay đổi theo Region, phiên bản Kubernetes và release AWS. Khi chọn, kiểm tra **EKS User Guide** hiện hành và workload prerequisites thay vì chỉ nhìn tên “managed”.

### 3.3. Managed node groups

**EKS managed node group** giúp tự động tạo và duy trì nhóm EC2 worker nodes, tích hợp với Auto Scaling group và chức năng thay thế/update node theo khả năng dịch vụ.

Bạn vẫn cần:

1. Chọn instance family/size, CPU architecture và AMI phù hợp.
2. Chọn subnet/AZ, security groups, launch template khi dùng, EBS root volume và chiến lược IAM.
3. Đặt min/desired/max capacity, cân nhắc On-Demand/Spot và dự phòng.
4. Tương thích Kubernetes/control-plane version và node image/add-ons khi nâng cấp.
5. Thiết kế resource requests/limits, PDB, readiness và node draining.
6. Theo dõi capacity, Pod pending, lỗi image pull, disk pressure và chi phí EC2.

**“Managed” không có nghĩa node tự động đáp ứng tất cả nhu cầu scaling**, và một node group không tự cho mọi Pod chạy đa AZ. Các cấu hình scaling/controller phải phù hợp.

### 3.4. Self-managed nodes

Bạn tự quản lý EC2, bootstrap, kubelet, kết nối cluster API, cấu hình OS và quy trình nâng cấp. Cách này cho phép tùy biến cao hơn, nhưng tăng khối lượng vận hành và rủi ro:

- Node không join cluster dù EC2 `running`;
- AMI/container runtime sai phiên bản;
- Kubelet thiếu IAM/quyền mạng;
- Thiếu quy trình drain trước khi terminate;
- Không cập nhật bản vá an ninh đúng hạn.

Chỉ chọn self-managed nodes khi có **lý do kỹ thuật rõ ràng** và đội vận hành có khả năng hỗ trợ dài hạn.

### 3.5. AWS Fargate for EKS

Với **EKS trên AWS Fargate**, người dùng định nghĩa những Pod sẽ chạy dựa trên **Fargate profiles** và selectors. AWS cấp tài nguyên chạy Pod mà không yêu cầu bạn quản lý trực tiếp các EC2 worker nodes.

Các đặc điểm cần xem xét:

- Fargate Pods trong EKS hoạt động theo **mô hình mạng riêng** và cần subnet phù hợp; thường dùng **private subnets** với đường kết nối đến các AWS APIs cần thiết.
- Có giới hạn với DaemonSets, privileged containers, cấu hình host/network và các tác vụ cần quyền host ở mức sâu.
- Storage không giống EC2/EBS: cần kiểm tra hỗ trợ lưu trữ EFS và các loại volume tương ứng.
- Việc triển khai các thành phần như ingress/controller, logging agent, monitoring cần xét tính tương thích Fargate.
- Tính phí dựa trên tài nguyên Pod được cấp theo biểu giá Fargate và các dịch vụ liên quan; không đồng nhất với phí node EC2.

Fargate phù hợp khi **workload và add-ons đều tương thích mô hình Pod-managed**. Nó không thay thế việc tối ưu `requests`, xác thực, VPC endpoints/NAT và giải quyết sự cố ứng dụng.

### 3.6. EKS Auto Mode

**EKS Auto Mode** hướng tới giảm công việc vận hành hạ tầng Kubernetes bằng cách để AWS tự động quản lý nhiều phần như cấp phát compute cho Pods, các thành phần networking/load balancing/storage được hỗ trợ và vòng đời nodes. Khái niệm cốt lõi:

- Người vận hành vẫn khai báo workload, resource requests, scheduling constraints và các chính sách cần thiết.
- AWS tự động tạo/quản lý compute và tích hợp một số tính năng add-on theo thiết kế Auto Mode.
- Tính năng/kỹ thuật không phải lúc nào cũng tương đương với managed node groups hay Fargate; **kiểm tra hỗ trợ DaemonSets, custom AMIs, các drivers/controllers, instance types và networking**.
- Auto Mode có **mô hình giá và giới hạn riêng** bên cạnh những thành phần EC2/storage/network; cần so tổng chi phí và lợi ích giảm vận hành.

Không nên áp sẵn một manifest cài AWS Load Balancer Controller hoặc CSI driver như với cụm truyền thống mà **chưa kiểm tra Auto Mode có quản lý chức năng tương ứng hay không**.

## 4. Luồng điển hình: từ Deployment đến một request HTTP

### 4.1. Một lần deploy

Giả sử muốn chạy API Java với 3 replicas:

~~~mermaid
sequenceDiagram
    participant Dev as kubectl / CI-CD
    participant API as EKS API server
    participant ET as etcd
    participant CTR as Kubernetes controllers
    participant SCH as scheduler
    participant K as kubelet trên node
    participant RT as container runtime
    Dev->>API: Apply Deployment replicas=3
    API->>API: Authenticate, authorize, validate/admit
    API->>ET: Ghi trạng thái mong muốn
    CTR->>API: Tạo ReplicaSet/Pods
    SCH->>API: Đọc unscheduled Pods và gán node
    K->>API: Watch PodSpec thuộc node
    K->>RT: Pull image / create containers
    RT-->>K: Container running hoặc lỗi
    K->>API: Cập nhật Pod/Node status
    Dev->>API: kubectl get deploy/pods
~~~

Sơ đồ này thể hiện **vai trò** các thành phần, không mô phỏng chính xác toàn bộ lệnh gọi API và cơ chế watch. Nếu không có node đủ CPU/RAM, Pod vẫn `Pending`; nếu image bị sai hoặc thiếu quyền ECR, Pod có thể ở `ImagePullBackOff` mặc dù control plane hoạt động bình thường.

### 4.2. Một request từ người dùng đến Pod

Một mô hình phổ biến:

~~~mermaid
flowchart LR
    U[Internet client] --> DNS[Route 53 / DNS]
    DNS --> LB[Application Load Balancer]
    LB --> T[Target group]
    T --> S[Kubernetes Service / Pod targets]
    S --> P1[Pod API - AZ A]
    S --> P2[Pod API - AZ B]
    P1 --> D[(RDS / DynamoDB / S3)]
    P2 --> D
~~~

Đường cụ thể phụ thuộc **Service type**, load balancer controller, target mode (instance/IP), CNI và cấu hình mạng. ALB có thể chuyển traffic trực tiếp tới Pod IP trong mô hình IP target hoặc đi qua NodePort/instance target theo kiểu tích hợp phù hợp; không phải mọi cụm đều có thêm NodePort ở đường đi.

Kubernetes objects quan trọng:

| Object | Vai trò |
|---|---|
| **Pod** | Đơn vị triển khai container nhỏ nhất thường gặp |
| **Deployment** | Quản lý ReplicaSet/rolling update cho Pod stateless |
| **Service (ClusterIP)** | DNS/điểm truy cập ổn định bên trong cluster |
| **Service (LoadBalancer)** | Có thể yêu cầu load balancer ngoài cluster tùy controller và annotation |
| **Ingress** | Quy tắc HTTP/HTTPS host/path, do Ingress controller thực thi |
| **EndpointSlice** | Thông tin các endpoints của Service |
| **ConfigMap/Secret** | Cấu hình và dữ liệu nhạy cảm với biện pháp bảo vệ thích hợp |
| **PVC/PV** | Khai báo nhu cầu và đối tượng lưu trữ có vòng đời riêng |

**Lưu ý:** tự tạo Ingress/Service không chắc chắn sinh ra ALB đúng kiểu. Cần **AWS Load Balancer Controller**, tích hợp EKS Auto Mode hoặc controller/provisioner được thiết kế phù hợp; điều kiện hỗ trợ thay đổi theo cấu hình cluster.

## 5. Ranh giới mạng: VPC, subnet và EKS cluster endpoint

### 5.1. Hai phạm vi hạ tầng khác nhau

EKS control plane được quản lý trong môi trường AWS vận hành. Khi tạo cluster, người dùng cung cấp VPC và các subnet/thiết lập mạng của cluster. AWS sử dụng **cross-account network interfaces (ENIs)** trong các subnet được chỉ định để phục vụ kết nối giữa control plane và các thành phần trong VPC khách hàng theo thiết kế EKS.

~~~mermaid
flowchart TD
    subgraph AWSVPC["AWS-managed VPC / EKS control plane"]
        APISERVER[Kubernetes API servers]
        CP[etcd, scheduler, controller manager]
    end
    subgraph CVPC["Customer VPC"]
        CE[Control-plane ENIs do EKS quản lý]
        SA[Private subnet AZ-A - worker/Pod]
        SB[Private subnet AZ-B - worker/Pod]
        E[Internet/NAT/VPC endpoints theo nhu cầu]
    end
    APISERVER <-->|EKS managed connectivity| CE
    CE <--> SA
    CE <--> SB
    SA --> E
    SB --> E
~~~

**Không xóa hoặc tùy tiện thay những ENI EKS tạo** chỉ vì chúng trông giống tài nguyên “không rõ chủ sở hữu”. Chúng là thành phần kết nối phục vụ EKS. Số lượng và cách đặt ENI do dịch vụ quản lý, có thể thay đổi qua vận hành và nâng cấp cluster.

### 5.2. Public và private API endpoint access

Kubernetes API endpoint có các chế độ truy cập phù hợp với VPC configuration:

| Cấu hình | Ý nghĩa | Lưu ý an ninh |
|---|---|---|
| **Public endpoint access** | API endpoint có đường truy cập công khai theo cấu hình | Giới hạn `publicAccessCidrs` khi phù hợp, bật auth/RBAC chặt chẽ |
| **Private endpoint access** | API endpoint có thể truy cập riêng từ VPC theo thiết kế | Muốn quản trị từ ngoài VPC cần kết nối mạng/DNS phù hợp như VPN, Direct Connect hoặc điểm quản trị nội bộ |
| **Public + private** | Hỗ trợ các đường truy cập theo cấu hình | Vẫn cần giới hạn CIDR, IAM, RBAC và security controls |

**Private API endpoint không có nghĩa workloads tự động ở private subnet**. Đây là hai quyết định khác nhau: một bên là đường truy cập **Kubernetes API**, một bên là đường kết nối mạng của Pod/EC2 và các dịch vụ ứng dụng.

**Ví dụ:** bạn bật private-only endpoint, rồi chạy `kubectl` từ laptop ngoài VPC và gặp timeout. Nguyên nhân có thể là **thiếu đường mạng/DNS**, không phải thiếu IAM. Ngược lại, nhận `Forbidden` nghĩa là request có thể đã tới API nhưng thiếu quyền Kubernetes.

### 5.3. Subnet và Availability Zone

Một kiến trúc phù hợp production nên:

- Có các subnet ở **ít nhất hai AZ** đáp ứng yêu cầu của EKS và workload.
- Phân bố nodes và Pods qua nhiều AZ khi ứng dụng cần chịu lỗi một AZ.
- Dự trù **số IP khả dụng trong subnet**, vì AWS VPC CNI cấp địa chỉ cho Pod theo mô hình mạng.
- Xem **route tables, NACL, security groups, NAT Gateway/VPC endpoints** cho các dependencies thực tế.
- Kiểm tra quota và availability của EC2 instance types, EBS và các load balancers theo từng AZ.

**EKS control plane nhiều AZ không tự sửa subnet IP exhaustion**. Nếu một subnet không còn IP, Pod có thể không khởi tạo được mạng dù EC2 còn CPU/RAM.

### 5.4. AWS VPC CNI

**Amazon VPC CNI** là plugin mạng phổ biến cho EKS chạy Pod trên EC2, cho phép Pod sử dụng địa chỉ IP có quan hệ trực tiếp với VPC theo các chế độ hỗ trợ. Plugin có thể cần bổ sung **secondary IP**, **prefix delegation**, ENI và các cấu hình IP management khác.

Các vấn đề cần quan sát:

- Có đủ địa chỉ IP cho **Pod density** trên node không?
- Instance type có giới hạn ENIs/IPs ảnh hưởng số Pods không?
- Có đang dùng IPv4/IPv6 và chế độ custom networking phù hợp không?
- Security group ở node và (nếu bật tính năng hỗ trợ) **security groups for Pods** có đúng không?
- Network policies có thực sự được bật và thực thi bởi CNI/plugin đang dùng không?

**Không xem Kubernetes NetworkPolicy là firewall tự hoạt động ở mọi EKS cluster.** Cần plugin và cấu hình hỗ trợ; không có enforcement phù hợp thì manifest policy có thể không đem lại tác dụng dự kiến.

### 5.5. CoreDNS và kube-proxy

- **CoreDNS:** phân giải tên Kubernetes Service như `api.default.svc.cluster.local`, thường được vận hành dưới dạng Deployment và có thể được quản lý qua EKS add-on.
- **kube-proxy:** điều phối một phần Service routing trên nodes theo chế độ networking; cũng có thể được quản lý qua EKS add-on ở mô hình phù hợp.
- **AWS VPC CNI:** triển khai Pod networking; không thay thế DNS hoặc tầng Service trên toàn bộ kiến trúc.

Một triệu chứng `DNS lookup failed` có thể do CoreDNS Pods không chạy, upstream resolution lỗi, network policy, security group, node networking hoặc cấu hình DNS; không phải lỗi API server theo mặc định.

## 6. IAM, Kubernetes RBAC và quyền của Pod

### 6.1. Có ít nhất ba câu hỏi khác nhau

1. **Ai được kết nối và xác thực với EKS Kubernetes API?** Liên quan AWS IAM credentials, EKS cluster authentication/access mechanisms và network path.
2. **Danh tính đã xác thực được phép làm gì trong Kubernetes?** Liên quan **Kubernetes RBAC** và các Kubernetes authorizers/admission controls.
3. **Ứng dụng chạy trong Pod được phép gọi AWS APIs gì?** Liên quan **IAM role for workloads** như EKS Pod Identity hoặc IAM Roles for Service Accounts (IRSA).

Không thể dùng một IAM policy cho `s3:GetObject` để kết luận người đó có quyền `kubectl delete pods`. Ngược lại, quyền Kubernetes `cluster-admin` không tự cấp quyền gọi mọi API AWS cho Pod.

### 6.2. Truy cập API: IAM + EKS access entries + RBAC

Một người vận hành đăng nhập qua IAM Identity Center/role; `kubectl` dùng AWS CLI token flow phù hợp để xác thực. EKS có **access entries** và **access policies** để cấu hình quyền truy cập; một số cụm cũ còn dùng ConfigMap `aws-auth` theo chế độ authentication đã chọn.

~~~text
Operator IAM role
    ↓ AWS token authentication
EKS Kubernetes API
    ↓ EKS access entry / mapping + RBAC hoặc access policy
Allowed Kubernetes API operations
~~~

Quy trình an toàn:

- Sử dụng **IAM role** tạm thời và MFA theo chính sách tổ chức.
- Chỉ cấp quyền cần dùng cho namespace/nhóm quản trị.
- Kiểm tra authorization mode và nguồn access mapping của cluster trước khi thay.
- Dùng **Kubernetes Role/RoleBinding** cho namespace scope và ClusterRole/ClusterRoleBinding khi thật sự cần trên phạm vi cluster.
- Không dùng `system:masters` hoặc `cluster-admin` làm giải pháp chung cho mọi `Forbidden`.

Ví dụ RBAC ở một namespace, chỉ cho xem Pods:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: training
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: training
subjects:
  - kind: Group
    name: training-readers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Đây là YAML để **giải thích**, không tự tạo quyền AWS IAM hay thêm thành viên vào nhóm `training-readers`. Cần mapping danh tính vào group theo cơ chế EKS của cụm, và có quyền tạo RBAC objects nếu muốn áp dụng.

### 6.3. Quyền gọi AWS API trong Pod: IRSA và EKS Pod Identity

Ví dụ API Java cần đọc `s3://school-files/reports/*`. Hướng tối thiểu là gắn quyền cho **workload identity**, không cấp `s3:*` trên node IAM role để mọi Pod cùng thừa hưởng quyền rộng.

| Cách cấp quyền | Cơ chế tổng quan | Cần kiểm tra |
|---|---|---|
| **IRSA** | Kubernetes service account được liên kết với IAM role qua OIDC và web identity token | OIDC provider, trust policy, service account annotation, SDK, audience và condition |
| **EKS Pod Identity** | EKS quản lý Pod Identity association; agent và IAM role cho Pod theo chế độ hỗ trợ | Association, IAM trust, agent/permissions và hỗ trợ compute type |
| **Node IAM role** | Node dùng quyền AWS cho bootstrap/pull image/add-ons theo cấu hình | Không dùng làm quyền ứng dụng chung nếu có phương án workload IAM riêng |

**Không trộn trust policy của hai phương thức.** IRSA và EKS Pod Identity sử dụng cơ chế trust/association khác nhau. Kiểm tra mức hỗ trợ với Fargate, EKS Auto Mode và cluster phiên bản hiện hành trước khi chọn; không giả định mọi cách đều áp được đồng nhất.

Một Pod có `serviceAccountName: report-reader` chưa có nghĩa nó được IAM cấp quyền. Cần cấu hình vai trò và liên kết danh tính theo phương thức đã chọn.

### 6.4. Trách nhiệm bảo mật bổ sung

- **Pod Security Admission** và security contexts: không chạy root/privileged khi không cần; giới hạn capabilities và filesystem write.
- **Secrets:** không commit mật khẩu vào Git; cân nhắc AWS Secrets Manager và cơ chế CSI/SDK phù hợp.
- **Image security:** quét image, pin tag/digest theo quy trình và bảo vệ ECR.
- **Network:** giới hạn đường ingress/egress, security groups và network policy có enforcement.
- **Encryption:** Kubernetes secrets encryption/KMS theo cấu hình EKS, EBS/EFS/S3 encryption và TLS theo chuẩn.
- **Audit:** bật log thích hợp của EKS control plane và giữ retention/cảnh báo phù hợp với yêu cầu tuân thủ.

## 7. Add-ons và controllers nằm ở đâu trong kiến trúc?

Một cụm EKS cần các thành phần bổ trợ. Một số là **Amazon EKS add-ons** có vòng đời quản lý phiên bản; các thành phần khác do khách hàng cài bằng Helm/operator hoặc được thay thế bằng tính năng managed của EKS Auto Mode.

| Thành phần | Vai trò | Chạy ở đâu thông thường? | Cần lưu ý |
|---|---|---|---|
| **Amazon VPC CNI** | Pod IP/networking | Nodes/data plane của chế độ hỗ trợ | Quyền IAM, IP exhaustion, compatibility |
| **CoreDNS** | DNS cho Kubernetes Services | Pod trên data plane | Replicas, scheduling, CPU/RAM, health |
| **kube-proxy** | Service traffic routing | Trên worker nodes theo mô hình hỗ trợ | Phiên bản tương thích và datapath |
| **AWS Load Balancer Controller** | Tạo/quản lý ALB/NLB theo đối tượng K8s | Controller Pods (nếu tự cài) | IAM, ingress class, tags, subnet discovery |
| **EBS CSI driver** | Provision/mount EBS volumes theo CSI | Controller + node components | IAM, AZ binding, PVC, snapshot support |
| **EFS CSI driver** | Truy cập EFS shared file storage | Thành phần CSI theo thiết kế | EFS mount targets, network, permissions |
| **Metrics Server** | Cung cấp resource metrics cho HPA khi dùng | Deployment trong cluster | Chỉ số HPA, bảo mật API, phiên bản |
| **Observability agents** | Logs, metrics, tracing | DaemonSet/Deployment hoặc tính năng managed | Chi phí, retention, tương thích compute |

Các add-ons chạy trên EC2 node groups có thể cần năng lực CPU/RAM riêng; lập kế hoạch capacity mà chỉ tính application Pods sẽ gây `Pending` hoặc OOM cho các system Pods.

### 7.1. Managed add-on không nghĩa tự cập nhật mọi lúc

Một EKS add-on có thể được AWS hỗ trợ quản lý cài đặt/phiên bản, nhưng **không giả định nó sẽ tự nâng cấp theo control plane mà không cần xem cấu hình**. Cần kiểm tra:

- Phiên bản tương thích cluster/node;
- Chế độ update và chính sách bảo vệ cấu hình tùy biến;
- Quyền IAM service account/Pod identity thích hợp;
- Tác động sau update tới CNI IP allocation, DNS và Service routing;
- Quá trình rollback hoặc khôi phục cấu hình nếu update lỗi.

## 8. Tính sẵn sàng: control plane HA khác workload HA

### 8.1. Những mức lỗi khác nhau

| Sự cố | Control plane | Data plane/workload | Hướng phòng vệ |
|---|---|---|---|
| Một node EC2 lỗi | Có thể vẫn hoạt động | Pod trên node ngừng chạy | Replica, ASG/node replacement, PDB |
| Một AZ mất kết nối | Control plane được thiết kế dự phòng | Node/Pod/volume AZ đó có thể không dùng được | Nhiều AZ, topology spread, data replication |
| API endpoint không thể truy cập từ operator | Có thể khỏe nhưng network/auth không phù hợp | Workload hiện có có thể vẫn chạy tùy phụ thuộc | Private access, VPN/DNS, kiểm tra IAM/RBAC |
| Toàn bộ Pods cùng chung một node | Không bị ảnh hưởng ngay | Ứng dụng gián đoạn khi node lỗi | Replicas rải node/AZ, anti-affinity |
| Cluster hết IP Pod | Vẫn nhận API request | Pod mới không lên mạng | VPC/subnet capacity, CNI/IP monitoring |
| Image registry hoặc IAM lỗi | Vẫn nhận desired state | Pod mới `ImagePullBackOff` | ECR/network/permissions/rollout validation |
| Database một điểm lỗi | Vẫn hoạt động | API lỗi dù Pod `Running` | RDS Multi-AZ hoặc replication và recovery |
| Thao tác xóa sai manifest | Control plane thực thi yêu cầu hợp lệ | Workload bị xóa hoặc mất cấu hình | RBAC, GitOps/IaC, backups, review |

### 8.2. Phân bố Pods qua AZ

Kubernetes hỗ trợ **topology spread constraints** và **pod anti-affinity** để điều khiển việc đặt Pod. Nhưng điều này chỉ hữu ích khi:

- Có nodes khả dụng trong AZ cần thiết;
- Có đủ CPU/RAM và địa chỉ IP;
- Scheduler constraints không mâu thuẫn;
- Storage/volume topology tương thích với nơi đặt Pod;
- Autoscaler có thể cấp capacity cho những AZ phù hợp.

Ví dụ minh họa phần cấu hình Pod template:

~~~yaml
spec:
  replicas: 3
  template:
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: catalog-api
      containers:
        - name: api
          image: example.invalid/catalog-api:replace-me
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
~~~

**`ScheduleAnyway` chỉ ưu tiên phân bố**, không bảo đảm tuyệt đối có Pod ở nhiều AZ. Nếu muốn ràng buộc cứng, đánh giá `DoNotSchedule`, `minDomains` và tác động đến availability khi một AZ thiếu capacity; không chọn “cứng” nếu nguy cơ Pod bị `Pending` làm giảm SLA hơn.

### 8.3. Replica, readiness và PodDisruptionBudget

Đối với HTTP API stateless, thường cần:

1. Deployment có **nhiều replicas** và phân bố phù hợp.
2. **Readiness probe** phản ánh khả năng nhận request, tránh gửi traffic khi ứng dụng chưa sẵn sàng.
3. **Liveness probe** chỉ dùng cho điều kiện thực sự cần restart; sai liveness có thể khiến Pod restart liên tục.
4. **Startup probe** nếu ứng dụng Java khởi động chậm.
5. **PodDisruptionBudget (PDB)** để giới hạn **voluntary disruptions** trong drain/upgrade theo khả năng controller.
6. Graceful termination, `preStop` hoặc logic shutdown và thời gian chờ phù hợp để giảm lỗi request đang xử lý.

Ví dụ PDB:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: catalog-api-pdb
  namespace: training
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: catalog-api
~~~

PDB **không thể ngăn mọi sự cố hạ tầng bất ngờ**. Nó có thể làm quy trình drain/upgrade bị chặn khi không còn đủ replicas khỏe, vì vậy cần kết hợp capacity và rollout strategy.

## 9. Scheduling và Auto Scaling: scale Pods khác scale nodes

### 9.1. Ba lớp mở rộng thường gặp

| Lớp | Công cụ/cơ chế | Điều chỉnh gì? |
|---|---|---|
| **Workload** | Horizontal Pod Autoscaler (HPA), KEDA hoặc controller tương đương | Số replicas của Pod/controller |
| **Compute capacity** | Cluster Autoscaler, Karpenter, EKS Auto Mode theo lựa chọn | Số/lớp nodes và năng lực hạ tầng |
| **Vertical resources** | Vertical Pod Autoscaler hoặc đo chỉnh cấu hình | `requests/limits` của Pods phù hợp chính sách |

~~~mermaid
flowchart TD
    M[CPU / custom metrics / queue depth] --> H[HPA hoặc event-driven scaler]
    H --> R[Deployment: tăng replicas]
    R --> S{Pods có đủ node capacity?}
    S -->|Có| P[Pods Running]
    S -->|Không| Q[Pods Pending]
    Q --> N[Node autoscaler / EKS Auto Mode]
    N --> C[Thêm node/compute nếu quota và AZ cho phép]
    C --> P
~~~

**HPA không tự tạo EC2 nodes**, còn node autoscaler không tự tăng replicas cho ứng dụng nếu không có demand signal/controller phù hợp. Nếu `requests.cpu` quá lớn hoặc subnet thiếu IP, tăng node size/count mà không phân tích có thể vẫn không giải quyết Pod pending.

### 9.2. Resource requests và limits

- **Requests** giúp scheduler đánh giá capacity để đặt Pod.
- **Limits** giới hạn tài nguyên theo cơ chế kernel/runtime; CPU limits có thể dẫn đến throttling, memory limits có thể dẫn đến OOM kill.
- Đặt requests quá thấp có thể làm node bị overcommit, quá cao gây lãng phí hoặc Pod `Pending`.
- HPA dựa trên CPU utilization thường so với **requests**; một request không hợp lý làm tín hiệu scaling khó diễn giải.

Với Java/JVM, cần cân nhắc container memory awareness, JVM heap/non-heap, GC, startup và readiness. Không chọn memory limit bằng đúng giá trị `-Xmx` vì còn có native memory, threads, metaspace và agent.

### 9.3. Spot và nhiều node types

Dùng Spot để tiết kiệm compute cho workload có thể bị gián đoạn, kết hợp:

- Nhiều instance families/sizes tương thích;
- Node disruption handling và graceful termination;
- PDB phù hợp nhưng không kỳ vọng PDB chống mọi Spot interruption;
- Replicas và khả năng chạy On-Demand cho thành phần trọng yếu;
- State bên ngoài node hoặc data replication.

Nếu workload có dữ liệu cần bền vững, cân nhắc **RDS/Aurora/DynamoDB/S3/EFS/EBS** theo kiến trúc và phạm vi AZ; đừng lưu dữ liệu quan trọng chỉ trên container filesystem rồi giả định Pod có thể di chuyển mà không mất dữ liệu.

## 10. EBS, EFS và lưu trữ cho Pod

### 10.1. PersistentVolume không phải máy chủ độc lập

Kubernetes quản lý yêu cầu lưu trữ qua **PersistentVolumeClaim (PVC)**, **PersistentVolume (PV)**, StorageClass và **CSI driver**. Backend thật là dịch vụ AWS có lifecycle/độ bền/chi phí riêng.

| Storage | Kiểu sử dụng | Ràng buộc chính |
|---|---|---|
| **EBS** | Block storage, phù hợp một Pod/ứng dụng stateful theo mô hình gắn volume được hỗ trợ | Volume gắn AZ; khi Pod chuyển sang AZ khác cần thiết kế provisioning/khôi phục phù hợp |
| **EFS** | Shared filesystem NFS | Network, mount targets, IAM/access points và performance modes theo yêu cầu |
| **S3** | Object storage/API | Không phải PVC block filesystem thông thường; dùng SDK/API hoặc tích hợp phù hợp |
| **Ephemeral container storage** | Cache/tmp/build artifacts tạm thời | Có thể mất khi Pod/node bị thay hoặc terminate |

**EBS volume ở một AZ không tự di chuyển thành volume AZ khác khi Pod bị reschedule.** Với stateful application, cần thiết kế storage class topology, backup/snapshot và replication ở tầng ứng dụng. Multi-AZ EKS cluster không làm một EBS volume có tính chất multi-AZ.

### 10.2. CSI controller thuộc lớp nào?

Ví dụ EBS CSI driver có những thành phần controller và node plugins chạy theo mô hình hỗ trợ trên data plane. Chúng tương tác với Kubernetes API, AWS EBS APIs và kernel/volume attachments. Driver **không phải một phần của AWS-managed Kubernetes control plane mặc định theo nghĩa etcd/API server**, dù có thể được quản lý dưới dạng EKS add-on hoặc bằng chức năng Auto Mode tương ứng.

## 11. Giá EKS và kiểm soát chi phí

### 11.1. Các khoản thường phát sinh

| Hạng mục | Nguồn chi phí | Khuyến nghị |
|---|---|---|
| **EKS cluster/control plane** | Phí cluster theo giờ và mức hỗ trợ phiên bản Kubernetes đang áp dụng | Dọn cluster lab, nâng cấp phiên bản đúng lịch để tránh extended support nếu không cần |
| **EC2 worker nodes** | Instance hours, purchase option, EBS root/data, public IPv4 | Right-size, autoscaling, On-Demand/Spot |
| **Fargate** | Tài nguyên Pod được cấp theo cấu hình/hỗ trợ | Đặt requests hợp lý, tắt workloads không dùng |
| **EKS Auto Mode** | Phần compute/infrastructure cùng mô hình phí Auto Mode tương ứng | So sánh tổng chi phí với lợi ích giảm vận hành |
| **Networking** | NAT Gateway, data transfer liên AZ, ALB/NLB, VPC endpoints | VPC design, đo traffic và tận dụng endpoint khi phù hợp |
| **Storage** | EBS, EFS, S3, snapshots/backup | Lifecycle, encryption, retention và dung lượng |
| **Logging/monitoring** | CloudWatch Logs, metrics, Container Insights, tracing | Chọn log types, retention và sampling |
| **Khác** | ECR image storage/data transfer, Route 53, WAF, KMS requests | Tag, Cost Explorer, budgets, cost allocation |

Giá **thay đổi theo Region, phiên bản hỗ trợ, loại compute và thời điểm**. Không lấy một con số giá theo giờ từ bài học làm cam kết tài chính; đối chiếu [Amazon EKS pricing](https://aws.amazon.com/eks/pricing/) và AWS Pricing Calculator.

### 11.2. Lab vẫn tốn chi phí khi không có ứng dụng

Ngay cả khi `kubectl get pods` cho thấy không có workload của bạn, **EKS cluster vẫn có thể phát sinh phí control plane**, và EC2/node groups, NAT, EBS, load balancer, logs vẫn có thể đang chạy. Một workload nhỏ trên EKS không nhất thiết rẻ hơn **Lambda**, **ECS Fargate** hoặc một EC2; hãy chọn EKS khi có lý do hợp lý về orchestration, hệ sinh thái Kubernetes hoặc yêu cầu vận hành.

### 11.3. Quản trị chi phí

- Gắn tags nhất quán cho cluster, node groups và tài nguyên liên quan theo chính sách tổ chức.
- Đặt AWS Budgets và cảnh báo; **budget không mặc định khóa mọi khoản chi**.
- Ghi chủ sở hữu, môi trường, ngày dự kiến dọn lab và thời gian giữ logs.
- Dùng Cost Explorer/Cost and Usage Report khi được cấp quyền để phân tích phí compute, EKS, NAT và storage.
- Sau khi dọn Kubernetes workloads, phải kiểm tra **AWS resources do controller tạo** như ALB/NLB/EBS vẫn còn hay không.

## 12. Thực hành chỉ đọc: khám phá một EKS cluster được cấp quyền

> **Điều kiện:** có EKS cluster sandbox đã tồn tại, AWS CLI v2, `kubectl` tương thích và quyền tối thiểu để xem cluster. Bài lab này **không tạo, cập nhật, nâng cấp hoặc xóa EKS cluster**. Nếu không có cluster được cấp, hoàn thành phần phân tích kiến trúc và bài tập thay vì tự tạo cluster mới.

### 12.1. Bước 1 — Xác nhận account và Region

Ví dụ Bash:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
aws eks list-clusters --region "$REGION" --profile "$AWS_PROFILE"
~~~

Thay profile và Region theo sandbox. Nếu dùng AWS CloudShell mà **không có profile `aws-lab-dev`**, bỏ dòng `export AWS_PROFILE=...` và những tham số `--profile`, dùng credentials phiên đăng nhập hiện tại. Kiểm tra `Account`/`Arn` và danh sách cluster trước khi tiếp tục.

**Lưu ý về quyền:** một IAM identity có quyền `eks:ListClusters` chưa chắc có quyền vào Kubernetes API hoặc `kubectl get pods`. Đây là hai cấp quyền khác nhau.

### 12.2. Bước 2 — Quan sát control plane và endpoint

~~~bash
CLUSTER_NAME=aws-lab-eks

aws eks describe-cluster \
  --name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE" \
  --query 'cluster.{Name:name,Status:status,Version:version,Endpoint:endpoint,Platform:platformVersion,Subnets:resourcesVpcConfig.subnetIds,SecurityGroups:resourcesVpcConfig.securityGroupIds,ClusterSecurityGroup:resourcesVpcConfig.clusterSecurityGroupId,PublicAccess:resourcesVpcConfig.endpointPublicAccess,PrivateAccess:resourcesVpcConfig.endpointPrivateAccess,Logging:logging.clusterLogging}' \
  --output json
~~~

Tên cluster ở trên **chỉ là ví dụ**, cần thay bằng cluster sandbox được cấp. Đọc:

| Trường | Ý nghĩa kiểm tra |
|---|---|
| `status` | `ACTIVE`, đang tạo/cập nhật hoặc trạng thái khác |
| `version` | Kubernetes version của cluster |
| `endpoint` | URL Kubernetes API server do EKS cung cấp |
| `subnetIds` | Các subnets được khai báo trong cluster VPC config |
| `endpointPublicAccess` / `endpointPrivateAccess` | Đường truy cập Kubernetes API |
| `clusterSecurityGroupId` | Security group do EKS tạo/quản lý cho cluster theo cấu hình |
| `clusterLogging` | Các log types được bật/tắt ở EKS control plane |

**Không** thử sửa cluster security group hoặc ENI khi chưa hiểu những kết nối hệ thống mà nó phục vụ.

### 12.3. Bước 3 — Xem managed node groups, Fargate profiles và add-ons

~~~bash
aws eks list-nodegroups \
  --cluster-name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE"

aws eks list-fargate-profiles \
  --cluster-name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE"

aws eks list-addons \
  --cluster-name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE"
~~~

Không có node group trong danh sách **không đồng nghĩa không có worker/data plane**: cluster có thể dùng Fargate, self-managed nodes hoặc các chế độ compute khác. Với EKS Auto Mode, cần kiểm tra **cluster compute configuration** theo phiên bản API hỗ trợ; không suy từ `list-nodegroups` một cách tuyệt đối.

Nếu có managed node group thật:

~~~bash
NODEGROUP_NAME=aws-lab-workers

aws eks describe-nodegroup \
  --cluster-name "$CLUSTER_NAME" \
  --nodegroup-name "$NODEGROUP_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE" \
  --query 'nodegroup.{Status:status,InstanceTypes:instanceTypes,CapacityType:capacityType,Subnets:subnets,Scaling:scalingConfig,Version:version,Release:releaseVersion,Health:health}' \
  --output json
~~~

Kiểm tra instance types, subnet/AZ, min/desired/max capacity và health issues.

### 12.4. Bước 4 — Chuẩn bị kubeconfig và chỉ đọc Kubernetes API

`aws eks update-kubeconfig` **chỉ cập nhật kubeconfig tại máy bạn**, nhưng thay đổi context/entry trong file local. Trước khi chạy, lưu bản cấu hình hiện tại nếu cần, không ghi đè kubeconfig đang dùng chung. Ví dụ:

~~~bash
aws eks update-kubeconfig \
  --name "$CLUSTER_NAME" \
  --region "$REGION" \
  --profile "$AWS_PROFILE" \
  --alias aws-lab-eks-readonly
~~~

Lệnh trên **không thay đổi tài nguyên AWS**; nó cấu hình truy cập client local. Để an toàn, luôn xem current context:

~~~bash
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
kubectl get namespaces
kubectl get pods -A -o wide
~~~

Nếu `kubectl` báo `Unauthorized/Forbidden`, phải kiểm tra IAM identity, EKS access entries hoặc legacy mapping, Kubernetes RBAC và access policies; **không tự thêm cluster-admin**.

Nếu endpoint private-only, máy chạy `kubectl` cần ở trong mạng có đường truy cập/DNS phù hợp đến cluster endpoint. Thay đổi kubeconfig sẽ không tự tạo VPN hoặc route.

### 12.5. Bước 5 — Phân biệt component ở control plane và data plane

Xem các đối tượng hệ thống được phép quan sát:

~~~bash
kubectl get pods -n kube-system -o wide
kubectl get deployments -n kube-system
kubectl get daemonsets -n kube-system
kubectl get services -n kube-system
kubectl get nodes -L topology.kubernetes.io/zone
~~~

Ví dụ có thể thấy `coredns`, `aws-node`, `kube-proxy` và agents tùy cấu hình. Hãy đối chiếu:

- **CoreDNS Pods:** thuộc data plane?
- **VPC CNI components:** dùng Pod/DaemonSet nào?
- **Control-plane `etcd`:** có xuất hiện như Pod do bạn quản lý trong `kube-system` không?
- Nodes có phân bố qua nhiều AZ không?
- Node readiness có phù hợp không?

**Không thấy `etcd` trong namespace** là hành vi bình thường với AWS-managed control plane; điều đó không chứng minh EKS thiếu etcd.

### 12.6. Bước 6 — Xem Deployment, Service và Pod placement

Nếu namespace `training` đã tồn tại và bạn được cấp quyền đọc:

~~~bash
kubectl get deployments -n training
kubectl get pods -n training -o wide
kubectl get services -n training
kubectl get events -n training --sort-by=.lastTimestamp
~~~

Phân tích:

1. Có bao nhiêu replicas `DESIRED/READY/AVAILABLE`?
2. Pods chạy trên những nodes/AZ nào?
3. Pod pending vì insufficient resources, scheduling constraints hay thiếu IP?
4. Service có `ClusterIP` hay `LoadBalancer`; ingress/load balancer có tồn tại không?
5. `kubectl describe pod <pod-name> -n training` hiển thị những events gì? **Chú ý** mô tả có thể chứa metadata hoặc môi trường nhạy cảm theo cách workload cấu hình; chỉ xem trong phạm vi được cấp.

### 12.7. Bước 7 — Câu hỏi quan sát

Từ các lệnh chỉ đọc, hãy trả lời:

- Cluster được EKS quản lý ở control plane; bạn có quyền thấy các API servers/etcd machines như EC2 trong account không?
- Worker nodes thuộc loại gì, nằm ở subnet/AZ nào?
- Node group có giới hạn min/desired/max ra sao?
- Cluster dùng public/private API endpoint theo cách nào?
- Có Pod system nào như CoreDNS/CNI/kube-proxy trên data plane?
- Nếu một Pod `Pending`, bạn cần thêm dữ liệu từ scheduler events và nodes để kết luận gì?

**Không cần chạy `kubectl apply` hoặc tạo EKS cluster** để hoàn thành bài lab cốt lõi.

## 13. Ví dụ manifest: Deployment và Service ở data plane

Đây là **ví dụ tham khảo**, không phải lệnh triển khai bắt buộc. Tên image `example.invalid` là placeholder có chủ đích; nếu áp dụng cần thay bằng image thật đã được build/scan/cho phép, đúng kiến trúc CPU.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: training
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      serviceAccountName: catalog-api
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: catalog-api
      containers:
        - name: catalog-api
          image: example.invalid/catalog-api:replace-me
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: training
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - port: 80
      targetPort: 8080
~~~

Điều manifest **làm được** nếu điều kiện triển khai hợp lệ:

- Deployment khai báo **3 Pods** có nhãn `app: catalog-api`.
- Scheduler chọn nodes theo capacity/constraints và topology preferences.
- Kubelet trên nodes tạo containers.
- Service `ClusterIP` cung cấp điểm truy cập trong cụm đến endpoints sẵn sàng.

Điều manifest **không tự làm**:

- Không tạo IAM role/Pod Identity association cho `catalog-api` service account.
- Không tự đưa API ra Internet vì `ClusterIP` chỉ dành cho truy cập trong cluster.
- Không bảo đảm có 3 Pods phân bố sang nhiều AZ nếu cluster không có capacity.
- Không tạo database, secrets, load balancer hoặc persistent volume.
- Không bảo đảm ứng dụng thật có `/ready` hoặc image tồn tại.
- Không thay thế PodDisruptionBudget, policies và monitoring của production.

Nếu bạn muốn triển khai trên sandbox, cần tạo namespace/service account đúng quyền, chuẩn bị image, quan sát resource requests và xác nhận không ảnh hưởng những workload khác. Với production, nên dùng Helm/IaC/GitOps và review pipeline phù hợp.

## 14. Chẩn đoán lỗi theo control plane và data plane

### 14.1. Bảng sự cố

| Triệu chứng | Lớp cần kiểm tra | Nguyên nhân đáng nghi | Công cụ/quan sát |
|---|---|---|---|
| `kubectl` timeout tới endpoint | API connectivity | Endpoint private, DNS/VPN/routing/firewall | `describe-cluster`, DNS và đường mạng client |
| `kubectl` trả `Unauthorized` | Authentication | IAM credentials/token sai hoặc chưa được mapping đúng | `sts get-caller-identity`, access entries/mode |
| `kubectl` trả `Forbidden` | Kubernetes authorization | RBAC/access policies thiếu quyền | `kubectl auth can-i` nếu được phép |
| EC2 `running` nhưng node không join | Data plane bootstrap | Kubelet/AMI/role, cluster endpoint/DNS, networking | EKS node group health, node/bootstrap logs |
| Pod `Pending` với `Insufficient cpu` | Scheduling/capacity | Nodes không đủ CPU theo requests | `kubectl describe pod`, node allocatable |
| Pod `Pending` dù CPU còn | Scheduling constraints | AZ/taints/nodeSelector/PVC constraints | Pod events và affinity/volume topology |
| Pod không có IP hoặc `ContainerCreating` kéo dài | Networking/CNI | Hết IP subnet, CNI/ENI permissions, plugin lỗi | CNI logs, subnet addresses, Pod events |
| Pod `ImagePullBackOff` | Runtime/registry | Image tag sai, ECR credentials, đường mạng | Events, ECR/network/role |
| Pod `CrashLoopBackOff` | Application/startup | App crash, OOM, probe sai, thiếu config | `kubectl logs --previous`, describe Pod |
| `kubectl get svc` có ClusterIP nhưng bên ngoài không truy cập | Exposing traffic | Chưa có Ingress/LoadBalancer hoặc DNS/network | Service type, controller, ALB/NLB |
| Service DNS không resolve | Cluster DNS | CoreDNS unhealthy hoặc plugin/network lỗi | `kube-system` Pods, CoreDNS logs |
| ALB healthy nhưng API lỗi 5xx | Application/dependency | DB/secret/permission/timeout | Logs/traces, downstream metrics |
| Control plane logs không có trong CloudWatch | Observability config | Log types chưa bật hoặc retention/view quyền | `describe-cluster` logging, CloudWatch |
| HPA scale Pods nhưng `Pending` | Compute autoscaling | Node autoscaler không cấp thêm capacity, quota/AZ | HPA, events, Karpenter/CA logs |
| EC2 nodes nhiều nhưng chi phí cao, tải thấp | Cost/capacity | Requests quá lớn, node group min cao, idle nodes | CPU/memory usage, AWS billing, autoscaler |
| Upgrade control plane xong nhưng workloads lỗi | Version compatibility | Deprecated APIs/add-ons/drivers/node mismatch | EKS upgrade insights, release notes, logs |

### 14.2. Trình tự xử lý

~~~text
1. Xác nhận AWS account, Region, cluster name và access mode.
2. API server có kết nối được không? (DNS / route / endpoint)
3. Request có bị Unauthorized hay Forbidden? (IAM + RBAC)
4. Cluster status / node health / addons ra sao?
5. Pod đang Pending, ContainerCreating, Running hay CrashLoopBackOff?
6. Scheduler events, resources, taints, topology constraints có hợp lệ?
7. Nếu container chạy, readiness và Service endpoints có đúng không?
8. Kiểm tra CoreDNS, VPC CNI, Ingress/LB, SG/VPC routing.
9. Kiểm tra IAM workload, secrets, storage, AWS API dependencies.
10. Theo dõi SLO, chi phí, chọn thay đổi tối thiểu và kiểm thử lại.
~~~

### 14.3. Đừng nhầm status của thành phần với sức khỏe nghiệp vụ

- **Cluster `ACTIVE`:** cluster đã được EKS đánh dấu trạng thái hoạt động, không chứng minh ứng dụng khỏe.
- **Node `Ready`:** kubelet/node tương đối sẵn sàng, không chứng minh mọi container chạy đúng.
- **Pod `Running`:** Pod được lên lịch và container có thể đang chạy; không chứng minh endpoint nghiệp vụ trả kết quả hợp lệ.
- **Readiness `True`:** một điểm kiểm tra ứng dụng đạt; không chứng minh mọi dependency hoặc đường thanh toán hoạt động.
- **ALB target healthy:** health check đạt; không chứng minh tất cả API routes không lỗi.

Giám sát nên có **metrics, logs, traces, business transactions và synthetic checks** theo yêu cầu hệ thống.

## 15. Bài tập tình huống: nền tảng khóa học chạy EKS

### 15.1. Yêu cầu

Một hệ thống học trực tuyến cần vận hành:

- **Frontend API** Java/Spring Boot có tải theo giờ học, cần HA.
- **Video thumbnail workers** xử lý hàng đợi, có thể retry.
- **RDS** lưu dữ liệu học viên, **S3** lưu video và tài liệu.
- **Secrets Manager** chứa credentials cấu hình được quản trị tập trung.
- Chi phí cần theo dõi, log tập trung, dùng IAM tối thiểu.
- Môi trường production phải chịu được **mất một worker node** và giảm ảnh hưởng khi một AZ bị sự cố.

### 15.2. Thiết kế tham khảo

~~~mermaid
flowchart TD
    U[Học viên] --> CF[CloudFront / DNS]
    CF --> ALB[ALB HTTPS + WAF nếu cần]
    ALB --> S[Kubernetes Service]
    subgraph EKS["EKS cluster - control plane AWS managed"]
        CP[K8s API / Scheduler / etcd managed]
    end
    subgraph VPC["VPC private subnets - 2+ AZ"]
        subgraph A["AZ A"]
            API1[API pods]
            WORK1[Worker pods]
        end
        subgraph B["AZ B"]
            API2[API pods]
            WORK2[Worker pods]
        end
        RDS[(RDS Multi-AZ theo yêu cầu)]
        Q[SQS queue]
    end
    S --> API1
    S --> API2
    API1 --> RDS
    API2 --> RDS
    Q --> WORK1
    Q --> WORK2
    WORK1 --> S3[(S3)]
    WORK2 --> S3
    CP -. Điểu phối .-> API1
    CP -. Điểu phối .-> API2
~~~

**Lưu ý sơ đồ:** “EKS cluster - control plane AWS managed” được vẽ riêng để nhấn mạnh chức năng quản lý; các Pods/Services trong sơ đồ thực tế là Kubernetes resources thuộc **cùng cluster EKS**, chạy trên data plane ở customer VPC.

### 15.3. Quyết định thiết kế

| Hạng mục | Gợi ý | Lý do |
|---|---|---|
| Control plane | Amazon EKS managed | Không tự quản lý API/etcd infrastructure |
| Compute API | Managed node groups hoặc Auto Mode phù hợp | Có node/compute cho HTTP Pods; đo tải và capacity |
| Compute batch | Node groups hỗ trợ Spot hoặc compute phù hợp | Workloads có retry/checkpoint, tối ưu chi phí |
| AZ | Worker capacity tại nhiều AZ | Giảm ảnh hưởng node/AZ failure |
| Deployment | >= 2 replicas, topology spread, readiness, PDB | Giảm downtime khi drain/update |
| Networking | Private subnets, VPC CNI, ingress ALB theo controller | Bảo vệ workload và chuẩn hóa đường vào |
| IAM workload | IRSA hoặc EKS Pod Identity theo hỗ trợ | Tách quyền S3/SQS/Secrets khỏi node IAM role |
| Storage | S3, RDS managed; PVC chỉ cho trường hợp cần | Dữ liệu bền vững ngoài vòng đời Pod |
| Scaling | HPA + node autoscaler/Auto Mode | Cân đối replicas và hạ tầng |
| Observability | EKS logs + workload metrics/logs/traces | Phân biệt lỗi điều phối và lỗi ứng dụng |
| Recovery | Backups/snapshot, GitOps, diễn tập AZ/node failure | RTO/RPO và tái lập cấu hình |
| Cost | Budgets + tags + right-sizing | Tránh cụm rỗng vẫn tốn phí không kiểm soát |

### 15.4. Câu hỏi suy luận

1. Nếu `kubectl apply` thành công nhưng không có node, Deployment có chạy được Pod không?
2. Có nên xem CoreDNS là một máy thuộc AWS-managed etcd/control plane không?
3. Vì sao một cụm với control plane HA vẫn cần Deployment replicas phân bố nhiều AZ?
4. Nếu toàn bộ application Pods `Running` mà ALB trả 503, cần kiểm tra lớp nào?
5. IRSA/EKS Pod Identity và EKS access entries khác nhau về mục tiêu gì?
6. Tại sao Pod của API không nên dùng node IAM role với `s3:*`?
7. Khi HPA tăng replicas nhưng Pods Pending, những hạn chế nào có thể xuất hiện?
8. Một PVC dùng EBS volume tại AZ A có tự gắn vào node ở AZ B không?
9. Khi nâng Kubernetes control plane version, vì sao vẫn cần kiểm tra CNI/CoreDNS/kube-proxy/node images?
10. Nếu dừng toàn bộ Deployments trong lab, vì sao hóa đơn EKS có thể vẫn tăng?
11. Fargate có phù hợp cho workload cần privileged DaemonSet và thao tác host kernel không?
12. `Cluster ACTIVE` có nghĩa hệ thống đã đạt p99 latency và SLO nghiệp vụ không?

**Gợi ý đáp án ngắn:**

1. Không, scheduler vẫn cần capacity để đặt Pod.
2. Không, CoreDNS thường là Pod ở data plane.
3. Vì HA control plane không tự giải quyết điểm lỗi ứng dụng/node/AZ.
4. Listener/target health, Ingress controller, Service endpoints, security group và backend.
5. Access entries/RBAC cho **quản trị Kubernetes API**; IRSA/Pod Identity cho **Pod gọi AWS APIs**.
6. Tránh chia quyền rộng cho mọi Pod và tăng phạm vi ảnh hưởng khi node/container bị xâm nhập.
7. Compute capacity, quotas, AZ/subnet IP, taints/affinity, node autoscaler.
8. Không; EBS volume có AZ affinity và cần cơ chế data recovery/replication thích hợp.
9. Để tránh version/API compatibility và network/plugin regressions.
10. Control plane, EC2 nodes, storage, NAT, ALB/logs vẫn có thể tính phí.
11. Thường không; kiểm tra giới hạn Fargate và chọn compute model phù hợp.
12. Không; cần theo dõi health và metrics của ứng dụng.

## 16. Hiểu lầm thường gặp

**“EKS là Kubernetes serverless hoàn toàn.”** Không chính xác. EKS quản lý control plane, còn mô hình data plane có thể là EC2-managed/self-managed, Fargate hoặc EKS Auto Mode với mức quản lý khác nhau.

**“Có EKS cluster là đã có worker nodes.”** Không luôn đúng. Cluster có thể chưa có compute, chưa cấu hình Fargate hoặc nodes đang gặp vấn đề join.

**“EKS tự chạy CoreDNS/kube-proxy bên trong control plane, nên tôi không cần capacity cho chúng.”** Với mô hình data plane EC2 truyền thống, CoreDNS, CNI/kube-proxy thường chạy trên data plane hoặc theo tích hợp được AWS hỗ trợ; phải kiểm tra cấu hình thực.

**“Cluster ở ba AZ nên mọi application Pods cũng sẽ ở ba AZ.”** Sai. Scheduler cần worker capacity và constraints phù hợp, không tự nhân Pods và dữ liệu theo AZ của control plane.

**“`kubectl Unauthorized` và `Forbidden` đều chỉ cần thêm `AdministratorAccess` IAM.”** Sai. Cần phân biệt authentication, EKS access configuration và Kubernetes RBAC; cấp quyền rộng có thể phá mô hình least privilege.

**“Một Kubernetes Service loại ClusterIP luôn tạo ALB.”** Sai. ClusterIP cho dịch vụ nội bộ; đường ra Internet cần ingress/load balancer hoặc cơ chế khác phù hợp.

**“Nếu Pod `Running` thì ứng dụng đã khỏe.”** Sai. Phải có readiness, health checks và theo dõi SLO.

**“EBS PVC tự di chuyển giữa hai AZ.”** Sai. EBS volume ràng buộc AZ; thiết kế lưu trữ/replication phải phản ánh đặc tính này.

**“HPA sẽ tự cấp EC2 mới khi tăng replicas.”** Không tự động; node autoscaling/compute provisioning phải được thiết lập phù hợp.

**“Không có Pods thì EKS không phát sinh phí.”** Sai. Control plane và tài nguyên cloud khác vẫn có thể chạy, tính phí.

## 17. Checklist trước khi đưa EKS vào production

### Kiến trúc và vận hành

- [ ] Phân biệt AWS-managed control plane với data plane thực tế.
- [ ] Có lựa chọn compute rõ ràng: managed node groups, Fargate, Auto Mode hoặc self-managed.
- [ ] Đã xác minh Kubernetes version, upgrade lifecycle, add-on compatibility và quota.
- [ ] VPC/subnets/AZ có đủ địa chỉ IP, route, DNS và security groups phù hợp.
- [ ] Kubernetes API endpoint access được giới hạn theo yêu cầu vận hành/bảo mật.
- [ ] Application Deployments có resource requests/limits và probes phù hợp.
- [ ] Có replica và scheduling topology đáp ứng yêu cầu lỗi node/AZ.
- [ ] Có HPA và compute/node autoscaling theo nhu cầu, kiểm tra khi hết capacity.
- [ ] Có chiến lược PVC/EBS/EFS/S3 và backup/restore theo RPO/RTO.
- [ ] Có kế hoạch upgrade và rollback workloads/add-ons/infra.

### Bảo mật và chi phí

- [ ] IAM roles của cluster/nodes/controllers/workloads tuân thủ least privilege.
- [ ] EKS access entries/legacy mappings và Kubernetes RBAC được rà soát.
- [ ] Ứng dụng dùng workload identity, không nhúng AWS credentials vào Pod.
- [ ] Pod security, image scanning, secrets, TLS và network policies được kiểm tra.
- [ ] EKS control plane logs và workload observability được bật theo nhu cầu.
- [ ] Có alert về Pod Pending/OOM/CrashLoop, node health, DNS/CNI và latency/error rate.
- [ ] Có tags, AWS Budgets, Cost Explorer và retention cho logs/storage.
- [ ] Có runbook dọn cluster/node groups/load balancers/EBS/NAT trong sandbox.
- [ ] Đã diễn tập ít nhất tình huống node failure và rollout lỗi.

**Kết quả mong đợi:** Bạn có thể mô tả **control plane do AWS quản lý, data plane do các compute models cung cấp**, vẽ đường đi từ `kubectl apply` đến Pod và từ client đến Service, xác định trách nhiệm IAM/network/add-ons, và đề xuất cách vận hành EKS có khả năng phục hồi, giám sát và kiểm soát chi phí.

## Tài liệu AWS chính thức

- [What is Amazon EKS?](https://docs.aws.amazon.com/eks/latest/userguide/what-is-eks.html)
- [Amazon EKS architecture](https://docs.aws.amazon.com/eks/latest/userguide/eks-architecture.html)
- [Amazon EKS cluster endpoint access control](https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html)
- [Amazon EKS managed node groups](https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html)
- [AWS Fargate for Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html)
- [Amazon EKS Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/automode.html)
- [Amazon EKS Hybrid Nodes](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-overview.html)
- [Amazon EKS access entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
- [IAM Roles for Service Accounts (IRSA)](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [Amazon VPC CNI for Kubernetes](https://docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html)
- [Amazon EKS add-ons](https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html)
- [Amazon EKS control plane logging](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html)
- [Amazon EKS pricing](https://aws.amazon.com/eks/pricing/)
- [Kubernetes Components](https://kubernetes.io/docs/concepts/overview/components/)
- [Kubernetes Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Kubernetes Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)

> **Lưu ý triển khai:** Tên cluster, ARN, profile, ví dụ manifest và command trong bài dùng để đào tạo, không xác nhận có cluster hay image thực. EKS release, compute models, chi phí, add-on compatibility và giới hạn mạng thay đổi theo Region và phiên bản. Trước khi tạo hoặc nâng cấp hệ thống thật, hãy tra cứu tài liệu AWS/Kubernetes hiện hành, thử nghiệm trên sandbox và thực hiện theo quy trình duyệt thay đổi.
