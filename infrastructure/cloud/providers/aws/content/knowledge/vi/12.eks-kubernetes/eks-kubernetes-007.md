# AWS Load Balancer Controller và công bố dịch vụ

> **Chương:** Kubernetes với EKS  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS từ Region/AZ, IAM và VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; thực hành thiết kế hệ thống an toàn, có giám sát, khả năng phục hồi và kiểm soát chi phí.

Trên **Amazon Elastic Kubernetes Service (Amazon EKS)**, một ứng dụng đang chạy ở trạng thái `Running` chưa chắc người dùng bên ngoài đã truy cập được. **Pod** có thể được thay thế và nhận địa chỉ IP mới; **Service** cung cấp điểm truy cập ổn định trong cluster; còn ứng dụng public thường cần **AWS Application Load Balancer (ALB)** hoặc **Network Load Balancer (NLB)** để nhận lưu lượng và chuyển tới đúng backend. **AWS Load Balancer Controller** là bộ điều khiển Kubernetes giúp chuyển những cấu hình khai báo đó thành tài nguyên Elastic Load Balancing trong AWS.

Bài học giải thích cách AWS Load Balancer Controller hoạt động với **Ingress**, **Service type `LoadBalancer`**, **Security Group**, subnet và health check, cũng như cách kiểm tra lỗi khi người dùng nhận `502`, `503` hoặc không kết nối được. Các YAML/ARN/địa chỉ IP trong bài là minh họa, **không được áp dụng nguyên trạng vào production**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của **AWS Load Balancer Controller** và cơ chế **reconciliation** giữa Kubernetes API với Elastic Load Balancing.
2. Phân biệt `Service ClusterIP`, `NodePort`, `LoadBalancer` và `Ingress`; lựa chọn **ALB Layer 7** hoặc **NLB Layer 4** theo yêu cầu.
3. Phân tích hai chế độ target của ELB: **`instance`** và **`ip`**, bao gồm luồng traffic tới NodePort hoặc thẳng tới Pod IP.
4. Thiết kế public/internal load balancer đúng subnet, IAM, Security Group, Kubernetes Service và health check.
5. Đọc và điều chỉnh manifest mẫu `Deployment + Service + Ingress` cho ALB HTTPS; nhận diện mẫu `Service type LoadBalancer` cho NLB.
6. Kiểm tra quyền controller bằng **IRSA hoặc EKS Pod Identity**, cùng các điều kiện VPC CNI, subnet discovery, quota và DNS.
7. Xử lý sự cố target unhealthy, sai target group, thiếu quyền IAM, subnet tag không phù hợp, lỗi pull image và quá trình rollout không an toàn.

## 2. Kubernetes Service không đồng nghĩa public endpoint

Kubernetes có các abstraction mạng khác nhau:

| Tài nguyên | Tác dụng | Có tự tạo AWS load balancer? |
| --- | --- | --- |
| **Pod** | Chạy một hoặc nhiều container có mạng chung trong Pod | Không |
| **Service `ClusterIP`** | Cung cấp virtual IP/DNS nội bộ cho nhóm Pods theo selector | Không |
| **Service `NodePort`** | Mở port nhất định trên Node để chuyển traffic tới Pods | Không chỉ nhờ NodePort |
| **Service `LoadBalancer`** | Yêu cầu một bộ điều khiển cloud triển khai load balancer tương ứng | Có, khi controller và class/annotations tương thích |
| **Ingress** | Khai báo định tuyến HTTP(S) theo host/path đến Kubernetes Services | Chỉ khi có **Ingress controller** phù hợp, ví dụ AWS Load Balancer Controller |
| **IngressClass** | Chỉ rõ controller chịu trách nhiệm Ingress | Không tự tạo ALB nếu chưa có controller hoạt động |

**Điểm phân biệt:** `Service` không phải instance của AWS ELB; `Ingress` cũng không phải bản thân ALB. Chúng là tài nguyên Kubernetes, còn controller đọc tài nguyên, gọi AWS API để tạo/cập nhật và theo dõi hạ tầng.

Ví dụ:

~~~text
Pod IP:            10.20.11.31:8080      (thay đổi khi Pod được tạo lại)
Service ClusterIP: 172.20.105.10:80      (điểm truy cập logic trong cluster)
Ingress host:      api.example.com        (khai báo routing HTTP)
AWS ALB DNS:       k8s-shop-api-xyz.elb.amazonaws.com
~~~

Những địa chỉ chỉ là ví dụ; EKS sử dụng Kubernetes Service CIDR và VPC subnet CIDR theo cấu hình thực tế. DNS `api.example.com` chỉ hoạt động trên Internet sau khi có bản ghi public DNS phù hợp; **controller không tự tạo mọi Route 53 record theo tên host của Ingress**.

## 3. AWS Load Balancer Controller làm gì?

**AWS Load Balancer Controller (LBC)** là một controller chạy trong Kubernetes cluster (thường được triển khai trong namespace `kube-system`). Nó theo dõi những tài nguyên Kubernetes mà mình phụ trách và **reconcile** trạng thái thực trong AWS về trạng thái khai báo mong muốn.

~~~mermaid
flowchart TB
    DEV["DevOps khai báo YAML"] --> API["Kubernetes API Server"]
    API --> ING["Ingress + IngressClass"]
    API --> SVC["Service type LoadBalancer"]
    ING --> LBC["AWS Load Balancer Controller"]
    SVC --> LBC
    LBC -->|"AWS API + IAM role"| ELB["Elastic Load Balancing"]
    ELB --> ALB["ALB + listeners + rules + target groups"]
    ELB --> NLB["NLB + listeners + target groups"]
    LBC -->|"Target registration"| POD["Pod IP hoặc EC2 NodePort"]
    ALB --> POD
    NLB --> POD
~~~

Trong một luồng điển hình:

1. Người triển khai tạo/đổi `Ingress` hoặc `Service`.
2. Kubernetes API lưu trạng thái mong muốn.
3. Controller quan sát tài nguyên, kiểm tra cấu hình, tìm subnets, Security Groups và endpoint liên quan.
4. Controller gọi AWS ELBv2/EC2 API để tạo hoặc cập nhật ALB/NLB, listener, rule và target group, rồi đăng ký target.
5. Controller cập nhật trạng thái như `status.loadBalancer.ingress` và tiếp tục reconcile khi Pods thay đổi.

**Reconciliation không phải một thao tác “chạy xong là kết thúc”.** Sau khi Pod bị thay, HPA scale-out hoặc bạn sửa Ingress, controller có thể sửa target list, rule và các AWS resources. Nếu sửa trực tiếp AWS ELB bằng tay, cấu hình thủ công có thể bị controller ghi đè ở vòng reconcile tiếp theo.

### 3.1. Controller phụ trách ALB và NLB như thế nào?

| Kubernetes entrypoint | AWS resource thường được tạo | Mô hình traffic chính |
| --- | --- | --- |
| **Ingress** có IngressClass/controller `alb` | **Application Load Balancer** | HTTP/HTTPS tới host/path và Kubernetes backend Service |
| **Service type `LoadBalancer`** được LBC nhận quản lý | **Network Load Balancer** | TCP/UDP/TLS theo các cấu hình được hỗ trợ |

Khi dùng **EKS Auto Mode**, AWS có cơ chế tự động quản lý một số load balancer, **khác đường triển khai controller tự quản lý**. Ngoài ra, có những Kubernetes cloud provider/controller cũ cũng có thể tạo load balancer cho Service. Do đó **cần xác định ai đang sở hữu mỗi tài nguyên bằng `IngressClass` / `loadBalancerClass` / annotations và cơ chế cluster hiện có**, tránh hai controller cùng cố quản lý một Service.

> **Nguyên tắc:** trước khi tạo Service `type: LoadBalancer`, xác định controller/`loadBalancerClass` tương thích với phiên bản EKS và LBC đang sử dụng. Các annotation dành cho LBC tự quản lý không mặc nhiên áp dụng giống nhau trong EKS Auto Mode.

## 4. Chọn ALB hay NLB?

### 4.1. Khác nhau ở lớp giao thức

| Tiêu chí | ALB | NLB |
| --- | --- | --- |
| Lớp chính | **Layer 7** (HTTP/HTTPS/gRPC theo hỗ trợ) | **Layer 4** (TCP/UDP/TLS theo hỗ trợ) |
| Quy tắc định tuyến | Host, path, HTTP headers và các điều kiện listener phù hợp | Chọn listener/protocol/port, không định tuyến theo HTTP path kiểu ALB |
| Kubernetes resource thường gặp | `Ingress` | `Service type LoadBalancer` |
| Chứng chỉ/TLS | HTTPS listener với ACM certificate | TLS listener nếu dùng cơ chế terminate TLS tương ứng, hoặc TCP passthrough |
| Backend | Target groups có `instance` hoặc `ip` theo cấu hình | Target groups có `instance` hoặc `ip` theo cấu hình |
| Tính năng HTTP | Redirect, fixed response, một số cách tích hợp authentication/WAF | Không cung cấp trọn bộ tính năng HTTP Layer 7 của ALB |
| Ví dụ ứng dụng | Web/API, nhiều service cùng tên miền | TCP service, gRPC theo yêu cầu Layer 4, dịch vụ cần mô hình NLB |

**Chọn theo giao thức, không chỉ theo tên “LoadBalancer”.** Một API HTTP muốn định tuyến `/catalog/*` và `/checkout/*` đến hai services thường hợp với ALB; dịch vụ dùng TCP riêng không phải HTTP thường chọn NLB.

### 4.2. Mô hình nhiều backend qua ALB

~~~mermaid
flowchart LR
    C["Client HTTPS"] --> L["ALB listener :443"]
    L -->|"Host api.example.com + /catalog/*"| TC["Target group catalog"]
    L -->|"Host api.example.com + /checkout/*"| TP["Target group checkout"]
    TC --> PCS["Catalog Pod IPs :8080"]
    TP --> PPS["Checkout Pod IPs :9090"]
~~~

ALB listener và target group chịu trách nhiệm phân phối traffic, còn Kubernetes Deployment quản lý số Pod. **Health check của target group** quyết định một target có đáp ứng tiêu chí để phục vụ hay không, nhưng không thay thế readiness/liveness của Kubernetes và không tự đảm bảo backend có dữ liệu đúng.

### 4.3. Public hay internal?

- **Internet-facing ALB/NLB:** nhận kết nối từ mạng ngoài theo đường public đã thiết kế, còn chịu Security Group/WAF/TLS/network restrictions phù hợp.
- **Internal ALB/NLB:** dùng cho client ở những mạng có routing đến private addresses của load balancer (trong VPC hoặc qua kết nối nội bộ), **không tự public ra Internet**.

Một hệ thống có thể có **public ALB** cho request của khách hàng và **internal ALB/NLB** cho API nội bộ, nhưng cần đánh giá chi phí và phạm vi lỗi của từng LB.

## 5. Target groups: `instance` hay `ip`?

Đây là lựa chọn quan trọng nhất khi kết nối Kubernetes workloads với AWS ELB.

### 5.1. Target type `instance`

Khi target group dùng `instance`, ELB đăng ký **EC2 worker nodes** và gửi traffic tới **NodePort** tương ứng của Kubernetes Service. Node sau đó chuyển request tới Pod theo dataplane/kube-proxy/CNI phù hợp.

~~~text
ALB/NLB
  → EC2 node (instance ID + NodePort)
    → Kubernetes Service
      → Pod IP:containerPort
~~~

Điều kiện:

- Có EC2 worker nodes làm target được hỗ trợ.
- Service thường cần `NodePort` hoặc cách định tuyến node-level được controller hỗ trợ.
- Security Group và NACL cho phép LB → node trên **NodePort** và traffic phản hồi.
- Kiểm tra `externalTrafficPolicy`, topology và target health theo loại LB vì có thể ảnh hưởng hành vi chuyển traffic.

`instance` không phải lựa chọn trực tiếp cho **EKS Fargate-only Pods** vì Fargate không cung cấp EC2 worker node theo cách đăng ký instance target này.

### 5.2. Target type `ip`

Với `ip`, controller đăng ký **địa chỉ IP của Pods** vào target group; load balancer gửi traffic trực tiếp tới **Pod IP:port**.

~~~text
ALB/NLB
  → Pod 10.20.11.31:8080
  → Pod 10.20.12.47:8080
~~~

Ưu điểm:

- Giảm thêm hop qua NodePort trong nhiều mô hình EKS dùng Amazon VPC CNI.
- Phù hợp với **EKS Fargate** hoặc workload muốn target trực tiếp tới Pod IP.
- Cho phép target group theo dõi endpoint khi Kubernetes thay đổi Pods.

Điều kiện:

- Pod IP phải **định tuyến được từ load balancer** theo mạng VPC/CNI.
- Security Group/network policy/NACL phải cho phép LB → Pod trên đúng port.
- Phải hiểu CNI đang sử dụng, pod readiness, IP capacity, cách gán SG cho Pods nếu có.

**Không giả định mọi Pod IP đều được AWS ELB truy cập trực tiếp**: nếu dùng overlay CNI, mạng đa cluster, IP không thuộc phạm vi hỗ trợ hoặc route đặc thù, phải kiểm chứng đường đi. Với Amazon VPC CNI thông thường, Pods nhận IP từ VPC theo cấu hình, phù hợp với mô hình `ip` khi các điều kiện khác đúng.

### 5.3. Bảng so sánh nhanh

| Tình huống | Target type thường cân nhắc |
| --- | --- |
| EKS chạy trên Fargate | **`ip`** |
| EKS EC2, cần LB đi thẳng Pod IP | **`ip`** |
| EKS EC2, traffic qua worker node NodePort | **`instance`** |
| Pod IP không định tuyến được tới LB | Không thể chỉ đặt `ip` rồi mong hoạt động; phải thiết kế lại networking |

Với ALB Ingress, annotation thường dùng:

~~~yaml
alb.ingress.kubernetes.io/target-type: ip
~~~

Với NLB Service do LBC quản lý, annotation:

~~~yaml
service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
~~~

**Hai annotation khác nhóm tài nguyên**, không được sao chép annotation của Ingress sang Service rồi giả định controller hiểu giống nhau.

## 6. Điều kiện trước khi triển khai AWS Load Balancer Controller

### 6.1. Cluster và Kubernetes APIs

Cần một EKS cluster vận hành được, worker nodes/Fargate profiles theo kiến trúc, Kubernetes networking phù hợp và người triển khai có quyền truy cập Kubernetes API. Các resource chuẩn gồm `Ingress` (API `networking.k8s.io/v1`), `Service`, `Deployment`; controller còn tạo và dùng các custom resources của nó như `TargetGroupBinding` khi cần.

Nếu cluster có cơ chế load balancer tự động khác, kiểm tra ownership và tương thích trước khi cài AWS Load Balancer Controller. Tên resource hay annotation cũ có thể thay đổi về mức hỗ trợ giữa các phiên bản.

### 6.2. Cài đặt controller và IAM

Controller thường được cài qua **Helm** hoặc phương án AWS/EKS được hỗ trợ, chạy như một Deployment với Kubernetes ServiceAccount được gắn **IAM role** đủ quyền quản lý Elastic Load Balancing, EC2 networking resources, tagging và những API cần thiết.

Hai cách cấp AWS credentials phổ biến:

1. **IAM Roles for Service Accounts (IRSA):** dùng OIDC provider liên kết EKS cluster, IAM role có trust policy giới hạn đúng ServiceAccount/namespace và Kubernetes projected token.
2. **EKS Pod Identity:** dùng Pod Identity Agent/add-on và association liên kết IAM role với ServiceAccount khi mô hình/platform hỗ trợ.

**Không gắn `AdministratorAccess` cho controller chỉ để sửa lỗi triển khai.** Dùng chính sách IAM do AWS Load Balancer Controller tài liệu chính thức cung cấp cho phiên bản cụ thể, giới hạn trust/role và quyền theo cluster khi phù hợp.

Ví dụ kiểm tra controller đã chạy:

~~~bash
kubectl -n kube-system get deployment aws-load-balancer-controller
kubectl -n kube-system get pods \
  -l app.kubernetes.io/name=aws-load-balancer-controller -o wide
kubectl -n kube-system get serviceaccount aws-load-balancer-controller -o yaml
~~~

Đây là lệnh **chỉ đọc**. Tên label/ServiceAccount có thể khác nếu chart release đã được cấu hình khác; đọc deployment và Helm release thực tế thay vì mặc định một cấu hình.

### 6.3. Quota và quyền truy cập AWS API

Controller gọi EC2 và ELB APIs để tìm VPC/subnet/SG, tạo target group/listener và đăng ký targets. Những vấn đề thường gặp:

- Thiếu IAM actions cho thao tác ELBv2, EC2 Describe, Security Group hoặc tagging.
- Thiếu kết nối **outbound tới AWS APIs** khi controller chạy trong private cluster mà không có NAT/VPC endpoints tương thích.
- API throttling, quota số ALB/NLB/target groups/listeners hoặc giới hạn subnet IP.
- Security Group rules/quota không còn đủ chỗ cho traffic backend.

**Kubernetes RBAC và AWS IAM là hai lớp riêng:** một ServiceAccount có thể được phép đọc Ingress bằng Kubernetes RBAC nhưng thiếu IAM để tạo ALB; ngược lại IAM đầy đủ không tự cấp quyền đọc tài nguyên Kubernetes nếu RBAC không cho.

### 6.4. VPC CNI và địa chỉ Pod

Mô hình `ip` yêu cầu mạng từ load balancer đến Pod IP khả dụng. Với EKS dùng **Amazon VPC CNI**, Pods thường nhận địa chỉ VPC subnet; phải dành đủ IP cho số Pods và giai đoạn rollout.

Đừng chỉ xem số EC2 nodes: Pod IP, ENI, prefix delegation, network policies, SG for Pods và loại compute có ảnh hưởng tới mật độ Pod và tính ổn định đường mạng. Việc cài controller **không tự sửa** CNI, subnet routing hay IP exhaustion.

## 7. Subnet discovery và cách chọn nơi đặt ALB/NLB

AWS load balancer phải được đặt vào subnet thích hợp để có ENI/node và khả năng nhận traffic. Controller có thể tìm subnet qua **tags và cấu hình của controller**; bạn cũng có thể khai báo rõ subnet IDs trên từng resource khi cần.

### 7.1. Các subnet tags thường dùng

| Loại subnet | Tag thường dùng | Ý nghĩa |
| --- | --- | --- |
| **Public** | `kubernetes.io/role/elb = 1` | Subnet dự kiến cho load balancer internet-facing |
| **Private** | `kubernetes.io/role/internal-elb = 1` | Subnet dự kiến cho load balancer internal |
| **Cluster association** (khi dùng) | `kubernetes.io/cluster/<cluster-name> = shared` hoặc `owned` | Giúp thể hiện subnet liên quan cluster và tránh nhầm trong VPC dùng chung |

Yêu cầu về **cluster association tag** đã thay đổi theo phiên bản controller; các phiên bản mới có thể không bắt buộc tag này trong tình huống thông thường, nhưng ở VPC dùng chung vẫn nên quản trị cách chọn subnet rõ ràng. Không tự áp dụng tài liệu của bản controller cũ cho phiên bản mới.

### 7.2. Public/private subnet không chỉ là tên

Một public subnet cần route mặc định phù hợp tới **Internet Gateway** khi sử dụng cho internet-facing LB. Internal load balancer cần subnet có private routing phù hợp tới clients và backends. Security Group, NACL và VPC route table vẫn phải cho phép luồng.

Ví dụ:

~~~text
VPC: 10.20.0.0/16

AZ A:
  public-a   10.20.0.0/24   (kubernetes.io/role/elb=1)
  private-a  10.20.11.0/24  (kubernetes.io/role/internal-elb=1)
  Pods       10.20.11.31, ...

AZ B:
  public-b   10.20.1.0/24   (kubernetes.io/role/elb=1)
  private-b  10.20.12.0/24  (kubernetes.io/role/internal-elb=1)
  Pods       10.20.12.47, ...
~~~

Một **ALB** thường được cấu hình ở **ít nhất hai subnet thuộc hai AZ khác nhau**; đảm bảo IP còn trống theo yêu cầu ALB và LBC. Nếu một AZ hết IP hoặc thiếu tagged subnet, controller có thể không tạo ALB hoặc gặp vấn đề khi scale.

### 7.3. Chỉ định subnet rõ trong Ingress

Khi muốn kiểm soát vị trí tạo ALB, có thể dùng annotation:

~~~yaml
alb.ingress.kubernetes.io/subnets: subnet-0a111111111111111,subnet-0b222222222222222
~~~

Hai subnet IDs phải tồn tại trong cùng VPC mà cluster dùng, thuộc AZ phù hợp và có route/role đúng với scheme. Đây chỉ là ví dụ giá trị annotation, không phải cấu hình AWS có sẵn. Dùng explicit subnets giúp tránh việc controller chọn nhầm subnet trong VPC chia sẻ với ứng dụng khác, nhưng đồng thời tăng công bảo trì khi topology thay đổi.

### 7.4. Subnet IP và chi phí theo AZ

Subnet phải đủ địa chỉ IP cho **load balancer ENIs/nodes**, Pods, VPC endpoints và các tài nguyên khác. Khi đổi AZ/subnet hoặc tạo nhiều LB, có thể cần thêm IP. Để đạt high availability, phải kiểm tra **routing và năng lực ở từng AZ**, không chỉ đặt annotation có hai subnet IDs.

## 8. Kiến trúc mẫu: công bố API HTTPS qua ALB

Giả sử ứng dụng shop API chạy trên EKS trong **private subnets ở hai AZ**, còn ALB nhận traffic HTTPS từ Internet.

~~~mermaid
flowchart TB
    U["Internet client"] --> DNS["Route 53: api.example.com"]
    DNS -.->|"Phân giải DNS tới ALB"| U
    U --> ALB["ALB internet-facing\nHTTPS listener :443\nSG: sg-alb"]
    ALB --> TG["Target group: target-type ip\nHTTP backend :8080"]
    subgraph VPC["Amazon VPC, EKS cluster"]
      subgraph A["AZ A"]
        PUBA["Public subnet A"]
        PODA["Pod A private IP :8080"]
      end
      subgraph B["AZ B"]
        PUBB["Public subnet B"]
        PODB["Pod B private IP :8080"]
      end
      TG --> PODA
      TG --> PODB
      PODA --> DB["RDS / downstream private"]
      PODB --> DB
    end
~~~

Đường request:

1. Client phân giải `api.example.com` tới ALB DNS name (thông qua Route 53 alias hoặc CNAME phù hợp).
2. Client kết nối `HTTPS :443` tới ALB public.
3. ALB listener kiểm tra host/path, chọn target group tương ứng.
4. Với `target-type: ip`, ALB gửi request qua mạng VPC tới **Pod IP:8080** đang được đăng ký.
5. Pod phải lắng nghe trên địa chỉ có thể truy cập từ ngoài Pod (`0.0.0.0:8080` khi phù hợp), có Security Group/network policy cho phép.
6. Pod kết nối tới database/backend nếu request yêu cầu, trả HTTP response cho ALB và client.

**Không cần public IP cho từng Pod**. ALB có public endpoint; Pods nằm trong subnet private. Khi một Pod bị thay, IP target group được cập nhật qua controller.

## 9. Manifest mẫu: Deployment, ClusterIP Service và ALB Ingress

Các YAML sau **chưa triển khai** và chỉ nhằm giải thích các thành phần cần khớp. Giả định cluster đã có AWS Load Balancer Controller, `IngressClass` tương ứng, các subnet public/private và IAM đủ quyền.

### 9.1. IngressClass cho AWS Load Balancer Controller

~~~yaml
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: alb
spec:
  controller: ingress.k8s.aws/alb
~~~

Chỉ tạo `IngressClass` này nếu chưa có class phù hợp và cluster được phép sử dụng. Một số chart/cluster đã có sẵn; **không tạo trùng resource** hay thay class đang được workload khác dùng mà chưa kiểm tra.

### 9.2. Deployment API

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-api
  namespace: shop
spec:
  replicas: 4
  selector:
    matchLabels:
      app: shop-api
  template:
    metadata:
      labels:
        app: shop-api
    spec:
      containers:
        - name: api
          image: 123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/shop-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 3
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              memory: "512Mi"
~~~

**Lưu ý:** namespace `shop` phải tồn tại. Image URI chỉ minh họa và không được đảm bảo tồn tại; cần ImagePull/authentication, IAM/node role hoặc Fargate execution role đúng. Readiness/liveness endpoints phải được **ứng dụng thực sự cung cấp**; nếu probe không đúng path, Pod có thể không sẵn sàng dù container đã chạy.

### 9.3. Service ClusterIP phía sau Ingress

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: shop-api
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: shop-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

Service chọn các Pods qua label `app: shop-api` và cung cấp port **80** trong Kubernetes. Khi Ingress backend tham chiếu `shop-api:80`, LBC tìm Pods/EndpointSlices và đăng ký **Pod IP:8080** theo model `ip`. Chú ý sự phân biệt **Service port 80** và **container target port 8080**.

### 9.4. HTTPS Ingress tạo ALB

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-api
  namespace: shop
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP":80},{"HTTPS":443}]'
    alb.ingress.kubernetes.io/ssl-redirect: "443"
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-southeast-1:123456789012:certificate/00000000-1111-2222-3333-444444444444
    alb.ingress.kubernetes.io/healthcheck-path: /health/ready
    alb.ingress.kubernetes.io/healthcheck-port: traffic-port
    alb.ingress.kubernetes.io/success-codes: "200"
spec:
  ingressClassName: alb
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: shop-api
                port:
                  number: 80
~~~

Giải thích:

| Trường | Ý nghĩa |
| --- | --- |
| `spec.ingressClassName: alb` | Giao Ingress cho controller chịu trách nhiệm class `alb` |
| `scheme: internet-facing` | Tạo ALB có public-facing scheme trong subnet phù hợp |
| `target-type: ip` | Đăng ký Pod IP vào target group |
| `listen-ports` | Nhận HTTP 80 và HTTPS 443 trên ALB theo cấu hình |
| `ssl-redirect` | Chuyển HTTP client tới HTTPS 443 bằng listener rule tương ứng |
| `certificate-arn` | ACM certificate hợp lệ cho `api.example.com` và Region của ALB |
| `healthcheck-path` | ALB kiểm tra `/health/ready` của target |
| `spec.rules[*].http.paths` | Chọn Kubernetes Service backend theo host/path |

**Các điều kiện còn thiếu trước khi đưa lên production:** subnet tags/route, Security Groups, ALB access logs/WAF nếu cần, permission của controller, DNS Route 53, domain ownership, ACM certificate thực, application container image, quan sát, rollback và chi phí. Không dùng ARN giả định trong môi trường thật.

### 9.5. Trạng thái sau khi tạo Ingress

Khi controller xử lý thành công, lệnh:

~~~bash
kubectl -n shop get ingress shop-api
~~~

có thể hiển thị cột `ADDRESS` là **AWS ALB DNS name**. Để khách truy cập `api.example.com`, phải tạo bản ghi **Route 53 alias A/AAAA** hoặc DNS record phù hợp tới ALB. Nhiều nhóm dùng **ExternalDNS** tự đồng bộ DNS từ Kubernetes annotations/rules; đó là **controller riêng**, không phải AWS Load Balancer Controller tự tạo toàn bộ Route 53 records.

## 10. Service type LoadBalancer tạo NLB

Không phải mọi dịch vụ đều nên đi qua HTTP Ingress. Với TCP app, service nội bộ hoặc trường hợp cần NLB, một `Service type: LoadBalancer` là cách khai báo quen thuộc.

### 10.1. NLB theo LBC và `loadBalancerClass`

Với phiên bản AWS Load Balancer Controller có hỗ trợ class `service.k8s.aws/nlb`, có thể định nghĩa:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: tcp-gateway
  namespace: shop
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-scheme: internal
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
spec:
  type: LoadBalancer
  loadBalancerClass: service.k8s.aws/nlb
  selector:
    app: tcp-gateway
  ports:
    - name: tcp
      port: 8443
      targetPort: 8443
      protocol: TCP
~~~

Ví dụ giả định Pods được gắn label `app: tcp-gateway` và lắng nghe TCP `8443`. Kết quả mong đợi là **internal NLB**, chuyển traffic tới Pod IP trên port 8443, không cần public IP cho Pod.

**Quan trọng về phiên bản:** `loadBalancerClass` và annotations phụ thuộc phiên bản controller/Kubernetes và cơ chế quản lý load balancer. Với một số phiên bản hoặc mô hình cũ, LBC dùng annotation `service.beta.kubernetes.io/aws-load-balancer-type: external`; trong **EKS Auto Mode**, class/annotations có thể khác. Trước khi áp dụng, xác định **controller nào sẽ nhận Service**, không trộn hướng dẫn của hai controller.

### 10.2. Khi cần internet-facing NLB

Đổi scheme thành `internet-facing` chỉ là một phần. Cần public subnet được chọn đúng, route, TLS/cert nếu dùng TLS listener, khả năng kết nối của client, Security Group/NACL và quy tắc hạn chế nguồn truy cập. NLB hoạt động ở Layer 4 nên **không tự định tuyến `/catalog` hay `/checkout` theo HTTP path**.

### 10.3. NLB health check và source IP

NLB target group cũng có health checks. Với target type `ip`, kiểm tra khả năng NLB tới **Pod IP:port**. Với target type `instance`, kiểm tra đường đến node/NodePort.

Những điểm phải xem khi thiết kế:

- Health check protocol/port/path cần hợp lệ với service.
- **Nguồn IP mà backend nhìn thấy** phụ thuộc target type, protocol, client-IP preservation và cách triển khai; không giả định mọi NLB luôn giữ source IP giống nhau.
- Kubernetes `externalTrafficPolicy` có thể ảnh hưởng routing/health khi target type `instance`.
- Nếu dùng Security Group cho NLB hoặc backend, kiểm tra khả năng quản lý rule của controller và model network hiện hành.

## 11. Security Group và mạng VPC cho ALB/NLB

AWS Security Group là lớp lọc **stateful** tại ENI. Với ALB internet-facing và Pod IP targets, thiết kế thường có ba vùng:

~~~text
Client HTTPS :443
  → ALB Security Group
    → Target group (Pod IP :8080)
      → Node/Pod networking + Security Groups / NetworkPolicy
        → Container listener :8080
~~~

### 11.1. Quy tắc ALB và backend

| Đối tượng | Inbound điển hình | Outbound cần xem |
| --- | --- | --- |
| **ALB SG** | TCP 443 từ client/CIDR hợp lệ; TCP 80 nếu muốn redirect HTTP | TCP 8080 tới nhóm IP/SG backend và health check port |
| **Node / Pod SG** (tùy mạng) | TCP 8080 từ ALB SG hoặc nhóm nguồn phù hợp | Gọi database, AWS APIs, DNS và dependencies thật |
| **Database SG** | DB port chỉ từ app Pod/Node SG được phép | Theo yêu cầu dịch vụ |
| **Interface VPC endpoint SG** | TCP 443 từ Pod/Node nguồn hợp lệ | Phản hồi stateful |

Kubernetes **NetworkPolicy** (khi CNI/network policy engine hỗ trợ và đã bật) là một lớp bổ sung. Không coi NetworkPolicy mặc định luôn được thực thi trong mọi cluster EKS; cần xác minh Amazon VPC CNI Network Policy feature hoặc policy engine đang dùng.

### 11.2. Controller quản lý Security Group tự động hay thủ công?

AWS LBC có thể tạo/đính kèm frontend Security Group cho load balancer theo cấu hình và **quản lý những backend security group rules** khi đáp ứng điều kiện/phiên bản.

Khi tự chỉ định SG cho ALB:

~~~yaml
alb.ingress.kubernetes.io/security-groups: sg-0123456789abcdef0
~~~

Bạn phải xem liệu controller sẽ **tự cập nhật backend security group rules** hay bạn cần quản lý chúng. Có cấu hình/annotation như:

~~~yaml
alb.ingress.kubernetes.io/manage-backend-security-group-rules: "true"
~~~

Nhưng không được thêm vào mọi môi trường một cách máy móc; nó có ràng buộc quyền, SG topology và cách controller phân quyền backend. Một SG do controller tạo và một SG chỉ định bằng tay **không nhất thiết được quản lý giống nhau**.

### 11.3. NACL và ephemeral ports

Network ACL **stateless** ở subnet có thể chặn kết nối dù Security Groups đã Allow:

- Client → ALB cần inbound public subnet port 443; ALB → client cần outbound tới ephemeral port của client.
- ALB → Pod IP cần outbound từ ALB subnet và inbound tới Pod subnet trên port 8080; response Pod → ALB về ephemeral port phía ALB.
- Custom NACL cần đủ rule theo từng chiều và những luồng khác như DB, DNS, image pull.

Hãy vẽ cặp **source IP:source port → destination IP:destination port** và đảo chiều cho response. Không chỉ mở TCP 443 ở cả hai chiều rồi mong các gói phản hồi tự đi qua NACL.

### 11.4. Egress và image pull

Pod ở private subnet có thể cần outbound để lấy image từ **Amazon ECR**, gọi Secrets Manager, CloudWatch Logs, STS hoặc các API khác. Tùy nền tảng, image pull có thể do node/container runtime hoặc Fargate thực hiện; quyền và mạng cần kiểm tra theo đúng vai trò.

Phương án egress:

- **NAT Gateway** cho kết nối tới public AWS API/endpoints và Internet cần thiết.
- **VPC endpoints** cho các dịch vụ được hỗ trợ (ví dụ ECR API/DKR, S3 gateway, CloudWatch Logs, STS), kèm SG, DNS và endpoint policy.
- Đường truy cập **Kubernetes API Server** phù hợp với cấu hình endpoint public/private của cluster.

Lỗi image pull, STS, WebIdentity/POD Identity hoặc log delivery có thể khiến Pod không sẵn sàng dù ALB đã tạo thành công.

## 12. Health checks, readiness và quá trình rollout

### 12.1. Hai loại “healthy”

**Kubernetes readinessProbe** quyết định một Pod có sẵn sàng để nhận traffic qua Kubernetes Service hay không. **ALB/NLB target health** là trạng thái được AWS ELB đánh giá trên target đã đăng ký. Chúng liên quan nhưng **không giống nhau**:

| Tín hiệu | Ai kiểm tra? | Điều kiện thường dùng |
| --- | --- | --- |
| `readinessProbe` | Kubelet | HTTP/TCP/exec/gRPC probe trong Pod |
| `livenessProbe` | Kubelet | Có cần restart container không |
| **ALB target group health** | ELB health checks | HTTP/HTTPS path/status hoặc giao thức tùy target group |
| **EKS controller reconciliation** | AWS Load Balancer Controller | Target group/target registration và resource trạng thái |

Ví dụ Deployment có readiness `GET /health/ready`, còn Ingress annotation đặt target health path cũng là `/health/ready`. Nếu application bind port khác, SG chặn 8080 hoặc response không phải 200, target có thể **unhealthy** dù Pod đã `Running`.

### 12.2. Pod readiness gates cho ALB targets

AWS Load Balancer Controller có khả năng sử dụng **Pod readiness gates** qua webhook/configuration phù hợp, để Kubernetes xem xét trạng thái target group trước khi xác nhận Pod đã đủ sẵn sàng theo các điều kiện. Một nhãn namespace thường được dùng để bật cơ chế injection:

~~~yaml
metadata:
  labels:
    elbv2.k8s.aws/pod-readiness-gate-inject: enabled
~~~

**Không coi nhãn đơn lẻ là bảo đảm thành công**. Pod readiness gates được inject vào lúc tạo Pod theo yêu cầu của webhook và việc tìm matching Service/target group; cần đặt namespace label **trước khi tạo Pod**, xác minh controller/webhook và target type hỗ trợ. Với rollout nghiêm ngặt, readiness gates có thể giúp tránh loại Pod cũ trước khi target mới được ALB đánh giá khỏe.

### 12.3. Graceful termination và draining

Khi Deployment cập nhật:

1. Kubernetes tạo Pod mới (tùy `maxSurge`, `maxUnavailable` và resource availability).
2. Controller phát hiện endpoint/target thay đổi rồi đăng ký target mới.
3. ALB/NLB đánh giá target health.
4. Pod cũ bắt đầu termination/deregistration; ELB có **deregistration delay** để hỗ trợ draining kết nối/request.
5. Container nhận `SIGTERM` và phải kết thúc request đang xử lý trong `terminationGracePeriodSeconds` hợp lý.

**Đừng đồng nhất** Pod `Ready`, ELB target `healthy` và request nghiệp vụ thành công. Để giảm 5xx khi rollout, cần phối hợp readiness gates, deployment strategy, connection draining, shutdown handler, capacity và metrics.

### 12.4. Khi toàn bộ targets đều unhealthy

ALB có hành vi **fail-open** trong một số tình huống khi tất cả registered targets thuộc target group ở các AZ enabled đều không khỏe: nó vẫn có thể gửi traffic đến chúng. Vì vậy, health check không thay thế kiểm tra auth/authorization và cơ chế bảo vệ dữ liệu trong ứng dụng; cũng không phải một “tường lửa” chặn mọi request khi backend lỗi.

## 13. IngressGroup, nhiều Services và ranh giới bảo mật

AWS LBC có tính năng **IngressGroup** cho phép một số Ingress cùng dùng chung **một ALB**, giúp tái sử dụng listeners/rules và giảm số LB.

Ví dụ annotation:

~~~yaml
alb.ingress.kubernetes.io/group.name: shop-public
alb.ingress.kubernetes.io/group.order: "10"
~~~

Điều cần hiểu:

- Nhiều Ingress cùng `group.name` có thể chia sẻ một ALB.
- Rule được hòa vào ALB và sắp xếp theo cơ chế controller, trong đó `group.order` có ý nghĩa về thứ tự ưu tiên.
- **Ranh giới trust:** người có quyền tạo/sửa Ingress với cùng group name có thể ảnh hưởng routing cho ứng dụng khác trong group. Không dùng chung IngressGroup giữa các nhóm **không tin cậy lẫn nhau** nếu chưa có cơ chế kiểm soát admission/RBAC phù hợp.
- Tái sử dụng một ALB tăng khả năng tối ưu chi phí nhưng cũng làm tăng **blast radius** khi thay đổi listener/security group/WAF.

**Ví dụ:** checkout và catalog đều đặt IngressGroup `shop-public`. Một người thuộc team catalog có quyền tạo Ingress nhưng không đáng được thay đổi đường `/checkout/*`. Nếu không giới hạn group membership và namespace authorization, người đó có thể khai báo rule cạnh tranh. Kubernetes namespace **không tự cách ly** mọi AWS resources dùng chung trong một group.

## 14. Liên kết DNS, TLS, WAF và nguồn traffic

### 14.1. Route 53 không tự xuất hiện từ `Ingress.host`

Khi Ingress tạo ALB thành công:

~~~text
Ingress host: api.example.com
ALB DNS name: k8s-shop-shopapi-123456789.ap-southeast-1.elb.amazonaws.com
~~~

Bạn vẫn phải tạo Route 53 alias hoặc cấu hình DNS tương ứng cho `api.example.com` trỏ tới ALB. Nếu dùng **ExternalDNS**, nó đọc tài nguyên Kubernetes theo quyền được cấp để tạo/sửa Route 53 records; đó là một thành phần vận hành **khác** và cần chính sách IAM độc lập.

### 14.2. HTTPS với ACM

Với ALB HTTPS listener:

- ACM certificate phải hợp lệ cho hostname cần phục vụ và nằm trong **Region của ALB**.
- `certificate-arn` chỉ ra chứng chỉ để ALB terminate TLS.
- Nếu redirect HTTP → HTTPS, listener port 80 cũng phải được thiết kế và giới hạn theo nhu cầu.
- Backend ALB → Pod **HTTP** khác với TLS end-to-end; nếu bắt buộc mã hóa cả hop nội bộ, xem target-group/backend protocol và cấu hình server TLS.

Không hardcode secret hoặc private key của chứng chỉ vào Kubernetes manifest khi có thể dùng ACM để quản lý phần TLS trên ALB.

### 14.3. WAF, authentication và quyền truy cập

ALB có thể tích hợp **AWS WAF** để lọc HTTP request khi được cấu hình; một số tính năng xác thực OIDC/Cognito, header/redirect và bảo vệ app còn phụ thuộc annotations và yêu cầu cụ thể. **WAF không thay thế authorization bên trong ứng dụng** hoặc IAM dùng để truy cập AWS APIs.

Đối với internal apps, đừng mở `internet-facing` chỉ để “test nhanh”. Hãy dùng internal scheme và mạng client được ủy quyền (VPN, Direct Connect, VPC peering/TGW khi phù hợp), đồng thời kiểm tra route và SG.

## 15. Chẩn đoán bằng kubectl và AWS CLI (chỉ đọc)

Những lệnh dưới đây chỉ đọc trạng thái, không triển khai resource. Giả sử namespace `shop`, Ingress `shop-api`, Service `shop-api`. Cần đúng kubeconfig/context và quyền AWS theo tài khoản/Region.

### 15.1. Kiểm tra kubeconfig và Ingress

~~~bash
kubectl config current-context
kubectl get ingressclass
kubectl -n shop get ingress shop-api -o wide
kubectl -n shop describe ingress shop-api
kubectl -n shop get events --sort-by=.lastTimestamp
~~~

Hãy đọc các **Events**:

- Không tìm được subnet hợp lệ.
- Thiếu IAM API permissions.
- Không giải quyết được Security Group hoặc VPC.
- Cấu hình annotation/IngressClass không được hỗ trợ.
- Listener/target group không tạo được vì quota hoặc cấu hình lỗi.

Nếu `ADDRESS` còn trống, không mặc định rằng cần chờ TTL; trước tiên kiểm tra **controller có reconcile được Ingress và tạo ALB hay không**.

### 15.2. Kiểm tra Service, Pod và EndpointSlices

~~~bash
kubectl -n shop get svc shop-api -o yaml
kubectl -n shop get pods -l app=shop-api -o wide
kubectl -n shop get endpointslice \
  -l kubernetes.io/service-name=shop-api
kubectl -n shop describe deployment shop-api
~~~

Nếu selector `app: shop-api` không khớp labels của Pods, Service không có endpoints phù hợp; target group có thể trống hoặc unhealthy. Nếu Pods không Ready, kiểm tra image pull, readiness probe, resource requests, IAM để truy cập ECR/secrets và logs của ứng dụng.

### 15.3. Kiểm tra controller và logs

~~~bash
kubectl -n kube-system get deployment aws-load-balancer-controller
kubectl -n kube-system logs \
  deployment/aws-load-balancer-controller \
  --tail=200
kubectl get targetgroupbindings -A
~~~

`TargetGroupBinding` là CRD do LBC cung cấp; tên resource/khả năng liệt kê phụ thuộc phiên bản và việc controller đã được cài. Logs chỉ là dữ liệu điều tra; cần tránh sao chép token hoặc secret sang ticket công khai.

### 15.4. Xem ALB, target groups và trạng thái targets

~~~bash
aws elbv2 describe-load-balancers \
  --region ap-southeast-1 \
  --query "LoadBalancers[].{Name:LoadBalancerName,Type:Type,Scheme:Scheme,State:State.Code,DNS:DNSName}" \
  --output table

aws elbv2 describe-target-groups \
  --region ap-southeast-1 \
  --target-group-arns TARGET_GROUP_ARN \
  --query "TargetGroups[].{Name:TargetGroupName,Type:TargetType,Protocol:Protocol,Port:Port,HealthPath:HealthCheckPath}" \
  --output json

aws elbv2 describe-target-health \
  --region ap-southeast-1 \
  --target-group-arn TARGET_GROUP_ARN \
  --query "TargetHealthDescriptions[].{Target:Target,State:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}" \
  --output json
~~~

Thay `TARGET_GROUP_ARN` bằng ARN của target group thực, đọc qua AWS Console/API hoặc tài nguyên mà controller tạo. Với `ip` target type, `Target.Id` thường là **Pod IP**; với `instance` là EC2 instance ID.

### 15.5. Xem subnet tags và Security Group

~~~bash
aws ec2 describe-subnets \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-0123456789abcdef0 \
  --query "Subnets[].{Id:SubnetId,AZ:AvailabilityZone,AvailableIPs:AvailableIpAddressCount,Tags:Tags}" \
  --output json

aws ec2 describe-security-groups \
  --region ap-southeast-1 \
  --group-ids sg-0123456789abcdef0 \
  --query "SecurityGroups[].{Id:GroupId,Ingress:IpPermissions,Egress:IpPermissionsEgress}" \
  --output json
~~~

ID chỉ là placeholder. Quan sát cả subnet thật sự được LB chọn, ingress/egress của ALB SG và backend SG, thay vì suy từ tên resource.

### 15.6. Kiểm tra website sau khi DNS sẵn sàng

~~~bash
dig api.example.com A
curl -I https://api.example.com/health/ready
~~~

`dig` và `curl` cần được cài đặt, domain và TLS certificate phải thật. Nếu đường TLS chưa cấu hình hoặc DNS chưa trỏ về ALB, bài thử sẽ thất bại; không giải quyết bằng cách tắt TLS verification hoặc mở rộng SG toàn Internet.

## 16. Bảng lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân hay gặp | Kiểm tra ưu tiên |
| --- | --- | --- |
| **Ingress không có ADDRESS** | Controller chưa chạy, sai IngressClass, thiếu IAM, subnet discovery lỗi | Controller logs, `kubectl describe ingress`, IAM và tags |
| **Controller AccessDenied** | IRSA/Pod Identity association/trust sai hoặc IAM policy thiếu action | ServiceAccount, IAM role, OIDC/Pod Identity Agent, CloudTrail |
| **Failed build model / không tìm được subnets** | Tags không đúng, thiếu subnets/AZ, IP còn trống thấp | Subnet tags, AZ, route, controller version |
| **ALB đã tạo nhưng website không phân giải tên** | Chưa có Route 53 record/ExternalDNS hoặc DNS delegation sai | Ingress ADDRESS, authoritative DNS |
| **HTTPS cert error** | ACM cert sai Region/hostname/trạng thái, ALB listener sai | Certificate ARN, validation, listener 443 |
| **Target group trống** | Service selector sai, không có EndpointSlices/Ready Pods, LBC reconcile lỗi | Service, Pod labels, controller logs |
| **Target.Timeout** | SG/NACL chặn Pod port, Pod chỉ bind localhost, routing/CNI lỗi | ALB SG, Pod IP, port, route và listener |
| **Target.ResponseCodeMismatch** | Health path sai, app trả 301/401/404/500 thay vì 200 | `/health/ready`, matcher, app logs |
| **Pod Running nhưng ALB unhealthy** | ALB health độc lập với Kubernetes readiness | Target group health, SG/port/path |
| **ImagePullBackOff** | ECR credentials/network, image/tag không tồn tại, node/Fargate role thiếu quyền | Pod events, ECR/S3/NAT/endpoints, IAM |
| **Service LoadBalancer chưa có EXTERNAL-IP/hostname** | Sai class/controller, IAM, subnet hoặc quota | `kubectl describe svc` và controller logs |
| **IngressGroup bị thay routing ngoài dự kiến** | Nhiều teams chia sẻ group, group.order/rule conflict | RBAC, namespaces, IngressGroup annotations |
| **502/503/504 từ ALB** | Backend lỗi, target thiếu/không khỏe, timeout, response malformed | ALB metrics/access logs + target health + Pod logs |
| **Công bố thành công nhưng mất AZ là ngừng phục vụ** | Pods/backend/capacity chỉ ở một AZ; ALB subnet nhiều AZ không đủ | Pod distribution, PDB, HPA/ASG, RDS/egress |

**Không sửa bằng cách mở toàn bộ Security Groups hoặc gán `AdministratorAccess` cho controller.** Xác định đúng lớp lỗi, rồi bổ sung quyền/route/port cần thiết có phạm vi hẹp.

## 17. Nhiều AZ, scale, readiness và khả năng phục hồi

### 17.1. ALB trải hai AZ không có nghĩa ứng dụng HA

Giả sử ALB bật ở AZ A/B, nhưng cả bốn Pods đều nằm trên EC2 nodes ở AZ A. Khi AZ A bị sự cố, ALB ở AZ B có thể còn phục vụ DNS, nhưng **không còn Pods khỏe** để chuyển request tới.

Thiết kế production cần:

- **Worker nodes/Pools** hoặc Fargate placement trên nhiều AZ.
- **Pod topology spread constraints** hoặc khả năng sắp lịch phù hợp; không để mọi replica rơi vào một AZ.
- **PodDisruptionBudget (PDB)** để giới hạn một số dạng gián đoạn có chủ đích; PDB **không ngăn được sự cố AZ**.
- **HPA/Karpenter/Cluster Autoscaler hoặc capacity manager** phù hợp, kèm quota/địa chỉ IP dự phòng.
- Dữ liệu và dependencies như RDS, ElastiCache, EFS, S3 và egress/NAT được thiết kế chịu lỗi theo yêu cầu.

### 17.2. Tính capacity khi một AZ không khả dụng

Giả sử app phải phục vụ **300 requests/giây** ở giờ cao điểm. Benchmark cho thấy mỗi Pod phục vụ bền vững **100 requests/giây** ở mức latency SLO mong muốn.

~~~text
Năng lực cần còn lại sau khi mất 1 AZ = 300 req/s
Năng lực mỗi Pod theo benchmark = 100 req/s
Số Pod cần còn sống = ceil(300 / 100) = 3

Nếu chia đều 2 AZ, mỗi AZ phải dự phòng tối thiểu 3 Pods
Tổng Pods khi hệ thống bình thường = 6 Pods
~~~

Đây là mô hình tối giản. Thực tế cần thêm margin cho tải biến động, CPU/memory, connection pool, data-store limits, HPA reaction time, quota, node disruption và thời gian để target mới trở thành healthy. **Không dựa hoàn toàn vào autoscaling sau khi AZ đã mất** nếu SLO không cho phép chờ.

### 17.3. Private networking và NAT theo AZ

Controller có thể tạo public ALB ở hai AZ nhưng Pods private vẫn cần **egress** tới ECR, STS, AWS APIs/telemetry và dependencies. Nếu mọi private subnets đều trỏ một NAT Gateway ở AZ A, sự cố AZ A có thể làm mất egress của Pods ở AZ B. Xem xét NAT theo AZ hoặc VPC endpoints nhiều AZ được cấu hình DNS/SG đúng; đồng thời cân đối chi phí.

### 17.4. Triển khai/rollback

Trong rolling update, Pods mới cần được pull image, schedule, Ready, đăng ký target và qua ELB health check trước khi đủ sức phục vụ. Dùng `maxSurge/maxUnavailable`, readiness gates, grace period, target deregistration delay và application graceful shutdown phù hợp. Rollback Kubernetes không nhất thiết rollback mọi tài nguyên ELB chỉnh sửa riêng nếu nhiều Ingress cùng chia sẻ ALB; phải có IaC/config review và quản lý quyền thay đổi.

## 18. Giám sát, bảo mật và chi phí vận hành

### 18.1. Metrics cần xem

| Thành phần | Gợi ý metrics/trạng thái |
| --- | --- |
| **ALB** | `RequestCount`, `HTTPCode_ELB_5XX_Count`, `HTTPCode_Target_5XX_Count`, `TargetResponseTime` |
| **Target group** | `HealthyHostCount`, `UnHealthyHostCount`, `TargetConnectionErrorCount` |
| **Kubernetes** | Pod Ready/Restart, Deployment available replicas, events, `EndpointSlices` |
| **Controller** | Reconciliation errors, leader/controller logs, crash/restarts |
| **Nodes/Pods** | CPU, memory, IP exhaustion, network drops, CNI health |
| **Network** | VPC Flow Logs, ALB access logs, SG/NACL configuration changes |
| **Costs** | LB hours/LCU hoặc NLCU, public IPv4, cross-AZ data transfer, NAT/PrivateLink endpoints, CloudWatch logs |

**`HealthyHostCount > 0` không chứng minh hệ thống còn đủ capacity khi mất AZ.** Cảnh báo cần so theo số targets tối thiểu để giữ SLO và tình trạng nhiều AZ.

### 18.2. Trách nhiệm bảo mật

- **RBAC và admission policies:** giới hạn ai được tạo/sửa Ingress, Service `LoadBalancer`, IngressGroup, Security Group annotations và hostname.
- **IAM controller:** giới hạn AWS API access, tin cậy ServiceAccount đúng namespace và tránh role dùng chung cho mọi workload.
- **IAM ứng dụng:** sử dụng IRSA/Pod Identity cho app theo quyền cần thiết, không lấy quyền của controller làm quyền app.
- **Network:** public/internal scheme, ALB/Pod SG, NetworkPolicy (nếu thực thi), NACL, TLS và WAF.
- **Thay đổi hạ tầng:** GitOps/IaC review, CloudTrail, log retention, cảnh báo khi tạo public LB hoặc sửa SG.
- **Dữ liệu:** auth/authz trong app, secrets management, DB least privilege, encryption và backup.

Khi cho phép một developer tạo Ingress public không giới hạn, người đó về thực tế có thể đề xuất tạo **tài nguyên AWS có endpoint Internet**. Quyền tạo Kubernetes resource vì thế cần được xem như quyền thay đổi hạ tầng mạng, không chỉ là quyền “deploy YAML”.

### 18.3. Kiểm soát chi phí

Một Ingress riêng có thể tạo một ALB riêng, tăng phí theo giờ và mức sử dụng. IngressGroup giúp chia sẻ ALB nhưng tăng phạm vi ảnh hưởng/rủi ro giữa các nhóm. NLB có mô hình tính phí khác ALB. Ngoài phí LB, cần tính:

- Data transfer giữa AZ, load balancer tới targets và các Region/VPC khác theo đường đi thực tế.
- EC2/Fargate, địa chỉ public IPv4 và Subnet/IP planning.
- NAT Gateway, interface VPC endpoints, WAF, CloudWatch Logs/metrics và số lượng request.
- Chi phí môi trường staging, blue/green hoặc canary nếu cần nhiều LB/target groups.

Không có mô hình nào “luôn rẻ nhất”. Chọn theo protocol, bảo mật, khả dụng, số lượng services, lưu lượng và chính sách tách biệt các đội.

## 19. Quy trình triển khai an toàn

1. **Xác định hướng công bố:** HTTP(S) nhiều path/host → Ingress/ALB; TCP/UDP/TLS Layer 4 → Service/NLB; mạng internal hay internet-facing?
2. **Kiểm tra ownership:** LBC tự quản lý, EKS Auto Mode hay controller khác? Xác định `IngressClass`/`loadBalancerClass` phù hợp.
3. **Chuẩn bị cluster networking:** subnets có route/tags/AZ, VPC CNI, Pod IP space, SG/NACL, egress và DNS.
4. **Cấp quyền controller:** IRSA/Pod Identity, IAM policy phiên bản phù hợp, Kubernetes RBAC và đường tới AWS APIs.
5. **Triển khai app trước:** Pod/Deployment có readiness/liveness, resource requests, image access và Service selector/ports đúng.
6. **Khai báo ALB/NLB:** target type, scheme, subnet, listener, certificate, health check, Security Groups, annotations.
7. **Quan sát reconcile:** Ingress/Service events, controller logs, AWS ELB/target group status.
8. **Thử đầu-cuối:** DNS → HTTPS/TCP → LB → Pod → database; kiểm tra mã lỗi, source IP, auth và TLS.
9. **Kiểm thử rollout và mất AZ:** đảm bảo target draining, readiness, đủ capacity và đường egress còn sống.
10. **Giám sát sau triển khai:** alerts, logs, AWS cost, IAM/SG change audit; có kế hoạch rollback.

### 19.1. Checklist production

- [ ] Đã xác định controller và `IngressClass` / `loadBalancerClass`; không có hai controller cùng quản lý.
- [ ] Controller chạy khỏe, ServiceAccount/IRSA/Pod Identity role và AWS API networking đúng.
- [ ] Subnets public/private đúng route, tags, nhiều AZ và đủ IP.
- [ ] Target type `ip`/`instance` phù hợp với Fargate/EC2, CNI và Pod networking.
- [ ] Kubernetes Service selector, port/targetPort, readiness probe và container listener khớp.
- [ ] ALB/NLB health checks, listeners, target groups và SG/NACL cho phép traffic có chủ đích.
- [ ] DNS Route 53 và ACM/TLS được cấu hình; không public nhầm internal service.
- [ ] IngressGroup và shared LB được giới hạn theo ranh giới tin cậy của các nhóm.
- [ ] Logs/metrics/CloudTrail và cảnh báo target health/reconcile errors đã được kiểm chứng.
- [ ] Pod replication, AZ capacity, rollout/draining và dữ liệu downstream đáp ứng SLO.
- [ ] Phí ALB/NLB, public IP, NAT/endpoints, transfer và WAF được dự toán.

## 20. Bài tập củng cố

### Bài tập 1 — ALB hay NLB?

Một website cần định tuyến `/catalog/*` và `/checkout/*` tới hai Kubernetes Services có tên khác nhau. Một ứng dụng khác chỉ dùng TCP trên port 5432.

**Gợi ý:** website có yêu cầu Layer 7 → **ALB + Ingress**; ứng dụng TCP có thể cân nhắc **NLB + Service type LoadBalancer** nếu cần LB. Với database, đừng public `5432` theo mặc định; đánh giá internal access và auth trước.

### Bài tập 2 — target type bị chọn sai

EKS Fargate chạy Pods `10.20.11.31:8080` nhưng Ingress annotation lại chọn `target-type: instance`. Vì sao không phù hợp?

**Gợi ý:** `instance` đăng ký EC2 worker instance/NodePort; Fargate Pods không có EC2 worker node theo mô hình đó. Chọn **`ip`** và đảm bảo ELB đi được tới Pod IP.

### Bài tập 3 — Pod Running nhưng target unhealthy

Deployment có container listen `127.0.0.1:8080`. Service port 80 → targetPort 8080. ALB health check gửi request tới Pod IP:8080 nhưng timeout.

**Gợi ý:** listener chỉ bind loopback trong Pod, nên traffic từ ngoài Pod IP không tới được. Thay đổi app để listen `0.0.0.0:8080` khi phù hợp và kiểm tra SG/NACL.

### Bài tập 4 — Ingress chưa có ADDRESS

`kubectl describe ingress` báo không tìm thấy subnet phù hợp. Cluster có hai private subnets nhưng chưa có public subnet tags. Bài toán yêu cầu internet-facing ALB.

**Gợi ý:** cần public subnet có route/Internet Gateway, tag `kubernetes.io/role/elb` phù hợp hoặc chỉ định explicit subnet IDs hợp lệ, nhiều AZ và đủ IP.

### Bài tập 5 — Service có endpoints nhưng target group trống

Bạn tạo `ClusterIP Service` cùng selector khớp Pods, nhưng chưa tạo Ingress hoặc `Service type LoadBalancer` được controller quản lý. Tại sao chưa có AWS ELB?

**Gợi ý:** `ClusterIP` chỉ là Kubernetes service nội bộ; không tự phát sinh ALB/NLB. Phải khai báo Ingress tương ứng hoặc một Service `LoadBalancer` đúng class/controller.

### Bài tập 6 — IngressGroup chung giữa hai đội

Hai đội độc lập cùng dùng `alb.ingress.kubernetes.io/group.name=shared-prod`. Đội A có quyền tạo Ingress với host/path bất kỳ. Nêu rủi ro và cách giảm thiểu.

**Gợi ý:** đội A có thể định nghĩa routing rule ảnh hưởng tới đội B trên cùng ALB. Tách group theo ranh giới trust, dùng RBAC/admission policies, review annotation/hostname, kiểm soát người tạo public ALB.

### Bài tập 7 — RTO khi mất AZ

Sáu Pods được trải đều hai AZ, mỗi Pod xử lý an toàn 100 req/s. Lưu lượng đỉnh là 320 req/s. Nếu mất một AZ, hệ thống còn đủ năng lực không?

**Gợi ý:** còn ba Pods = 300 req/s, **không đủ** tải đỉnh 320 req/s. Cần ít nhất bốn Pods còn sống (ví dụ bốn Pods/AZ theo mô hình hai AZ) và kiểm chứng DB/egress/Node capacity.

### Bài tập 8 — So sánh NetworkPolicy và SG

Một cluster đã giới hạn SG của ALB tới Pod port 8080. Có thể coi vậy là đủ để cấm một Pod khác trong cluster truy cập API đó không?

**Gợi ý:** còn tùy CNI, SG for Pods/node và mạng giữa Pods. Muốn kiểm soát **east–west** traffic, cần xem NetworkPolicy hoặc Security Group topology cụ thể; không mặc định SG của ALB kiểm soát mọi Pod→Pod traffic.

## 21. Ghi nhớ

**AWS Load Balancer Controller** là cầu nối giữa **Kubernetes desired state** và **AWS ELB resources**. Nó đọc `Ingress` để quản lý **ALB** và những `Service type LoadBalancer` phù hợp để quản lý **NLB**, đồng thời theo dõi target registration và thay đổi Pods.

Hãy luôn kiểm tra năm điểm nối trong đường phục vụ:

1. **Ingress/Service class** có được đúng controller quản lý không?
2. **Load balancer** có nằm ở subnet, scheme, AZ và listener đúng không?
3. **Target type** là `ip` hay `instance` phù hợp với Pod networking/Fargate/EC2?
4. **Security Group/NACL** có cho LB kết nối tới Pod IP/NodePort và trả phản hồi không?
5. **Kubernetes readiness + ELB health check** có cùng phản ánh một backend thực sự phục vụ được không?

Thiết kế production còn cần **IAM least privilege, DNS/TLS, AZ capacity, rollout/draining, monitoring và chi phí**. Một Ingress tạo được ALB chưa chứng minh hệ thống an toàn hay có khả năng phục hồi; phải kiểm thử đường đi và các tình huống lỗi thực tế.

### Tài liệu AWS và Kubernetes chính thức

- [AWS Load Balancer Controller documentation](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/) — tổng quan, cài đặt và các phiên bản.
- [AWS Load Balancer Controller: Ingress annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress/annotations/) — target type, listener, SG, health checks và IngressGroup.
- [AWS Load Balancer Controller: Service annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/service/annotations/) — NLB Service, target type, internal/public và class.
- [Subnet discovery](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/deploy/subnet_discovery/) — subnet roles, tags và auto-discovery.
- [IngressClass and IngressClassParams](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress/ingress_class/) — chọn đúng controller.
- [EKS: Route application and HTTP traffic with Application Load Balancers](https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html) — ALB trong EKS.
- [EKS: Route TCP and UDP traffic with Network Load Balancers](https://docs.aws.amazon.com/eks/latest/userguide/network-load-balancing.html) — NLB với EKS.
- [EKS: Install AWS Load Balancer Controller](https://docs.aws.amazon.com/eks/latest/userguide/lbc-helm.html) — cài đặt controller và IAM.
- [EKS: Assign IAM roles to Kubernetes service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) — IRSA.
- [EKS: Pod Identities](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) — IAM roles cho ServiceAccount qua Pod Identity.
- [EKS: EKS Auto Mode load balancing](https://docs.aws.amazon.com/eks/latest/userguide/auto-configure-nlb.html) — khác biệt giữa quản lý tự động và LBC tự cài.
- [Kubernetes Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/) và [Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/) — API và thuật ngữ Kubernetes.
- [Elastic Load Balancing: Target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html) — health, trạng thái và nguyên nhân lỗi.
