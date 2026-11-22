# Bảo mật network policy và vận hành EKS nhiều AZ

Một cluster **Amazon Elastic Kubernetes Service (Amazon EKS)** có thể chạy hàng trăm Pod, thuộc nhiều namespace và triển khai trên nhiều **Availability Zone (AZ)**. Mặc dù những Pod này nằm trong các subnet của VPC, không nên mặc định chúng được cách ly với nhau. Một ứng dụng bị xâm nhập có thể cố kết nối đến dịch vụ nội bộ khác; ngược lại, cấu hình **NetworkPolicy** quá chặt có thể làm DNS, database hoặc health check ngừng hoạt động.

Về tính sẵn sàng, việc tạo EKS cluster với nhiều subnet **không tự bảo đảm Pod được phân bố đều giữa các AZ**. Một deployment ba replica vẫn có thể đặt cả ba Pod trên một node hoặc một AZ nếu không có yêu cầu scheduling phù hợp. Khi AZ đó gặp sự cố, ứng dụng có thể ngừng phục vụ dù control plane EKS vẫn hoạt động.

Bài học thuộc chương **Kubernetes với EKS** trong mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless để người học thiết kế ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Kubernetes NetworkPolicy**, **security groups**, **network ACL**, **IAM** và **Kubernetes RBAC** theo đúng lớp bảo vệ.
2. Giải thích nguyên tắc **default allow**, **default deny**, tính cộng gộp của các policy, **ingress** và **egress**.
3. Viết chính sách giới hạn luồng **frontend → API → backend**, đồng thời cho phép DNS và các kết nối thật sự cần thiết.
4. Nêu điều kiện, giới hạn và cách bật tính năng NetworkPolicy với **Amazon VPC CNI**, bao gồm **standard/strict enforcement**.
5. Thiết kế EKS chạy nhiều AZ bằng **node groups**, **topology spread constraints**, **PodDisruptionBudget**, health probes và autoscaling.
6. Giải thích ràng buộc AZ của **Amazon EBS**, vai trò của **EFS**, backup và các dịch vụ database Multi-AZ.
7. Sử dụng **kubectl** và **AWS CLI** để kiểm kê, phân tích network policy, sự cố scheduling, thiếu Pod IP và lỗi mất AZ.
8. Lập runbook triển khai, nâng cấp, giám sát, khôi phục và ước lượng chi phí vận hành EKS.

## 2. Mô hình trách nhiệm: EKS quản lý gì, chúng ta quản lý gì?

Amazon EKS quản lý **Kubernetes control plane** với khả năng sẵn sàng cao theo thiết kế AWS. AWS triển khai các thành phần control plane trên nhiều AZ. Người dùng vẫn quản lý phần lớn cấu hình **data plane**, workloads, Kubernetes add-ons, IAM, network, dữ liệu và quy trình triển khai. Các lựa chọn compute hiện có gồm **EC2 managed node groups**, self-managed nodes, Fargate và những chế độ được quản lý khác như **EKS Auto Mode**, mỗi loại có giới hạn và trách nhiệm riêng.

| Thành phần | Vai trò | Điều tổ chức vẫn cần chịu trách nhiệm |
|---|---|---|
| **EKS control plane** | Kubernetes API server và các thành phần điều phối được AWS quản lý | Nâng cấp phiên bản, endpoint access, authentication/authorization và cấu hình cluster |
| **EC2 worker nodes / node groups** | Cung cấp CPU, RAM, network và storage cho Pod | Phân bố AZ, sizing, cập nhật node, IAM node role, OS/add-ons |
| **Kubernetes scheduler** | Chọn node cho Pod theo yêu cầu đã khai báo | Replicas, resource requests, affinity, topology spread, tolerations |
| **Amazon VPC CNI** | Cấp IP và kết nối mạng Pod trong VPC | Cấu hình IP/subnet, network policy enforcement khi được hỗ trợ, nâng cấp add-on |
| **CoreDNS / kube-proxy và thành phần mạng** | DNS nội bộ và đường đi dịch vụ theo cấu hình | Sẵn sàng, scale, bảo mật, cập nhật và đo đạc |
| **Application workloads** | Cung cấp API, xử lý job, lưu dữ liệu | Health checks, retry, graceful shutdown, dữ liệu bền vững, SLO |

**Phân biệt control plane HA với workload HA:** cluster vẫn có thể nhận lệnh **kubectl** trong khi ứng dụng đã mất toàn bộ Pod ở AZ bị sự cố. Tương tự, nếu tất cả worker nodes đặt một AZ, HA của control plane không cứu được dịch vụ.

### 2.1. Kiến trúc EKS nhiều AZ minh họa

~~~mermaid
flowchart TB
    USER["Client / Route 53"] --> ALB["ALB / Kubernetes Ingress"]
    CP["EKS control plane<br/>AWS quản lý đa AZ"] -. "Kubernetes scheduling / API" .-> NG["EC2 worker node groups"]
    subgraph VPC["VPC trong một AWS Region"]
        subgraph AZA["AZ A"]
            NA["Node A"]
            PA["API Pod A"]
        end
        subgraph AZB["AZ B"]
            NB["Node B"]
            PB["API Pod B"]
        end
        subgraph AZC["AZ C"]
            NC["Node C"]
            PC["API Pod C"]
        end
        NA --> PA
        NB --> PB
        NC --> PC
    end
    NG --> NA
    NG --> NB
    NG --> NC
    ALB --> PA
    ALB --> PB
    ALB --> PC
    PA --> DB["RDS / DynamoDB<br/>Dữ liệu tách khỏi Pod"]
    PB --> DB
    PC --> DB
~~~

Sơ đồ là mục tiêu kiến trúc, **không phải bảo đảm tự động**. Trong thực tế phải có worker capacity ở nhiều AZ, scheduling constraints, target health, mạng phù hợp và backend có khả năng phục hồi.

## 3. Năm lớp bảo mật dễ bị nhầm

| Cơ chế | Phạm vi và cách áp dụng | Ví dụ |
|---|---|---|
| **Kubernetes NetworkPolicy** | Kiểm soát kết nối **L3/L4** tới/từ Pod được chọn; cần network plugin thực thi | Chỉ Pod **frontend** được gọi Pod **api** cổng TCP 8080 |
| **Security group** | Lọc traffic ở cấp ENI/tài nguyên VPC, có thể gắn cho Pod trong cấu hình hỗ trợ | Chỉ workload phù hợp được kết nối RDS TCP 5432 |
| **VPC network ACL** | Kiểm soát stateless ở cấp subnet | Chặn hoặc cho phép dải IP/port vào ra subnet |
| **AWS IAM / EKS Pod Identity / IRSA** | Quyền API AWS, ví dụ S3, SQS, DynamoDB | Pod role chỉ được **s3:GetObject** trên bucket được cấp |
| **Kubernetes RBAC / EKS access entries** | Ai được gọi **Kubernetes API** và thao tác tài nguyên cluster | Nhóm vận hành được xem Pod nhưng không tạo ClusterRole |

**NetworkPolicy không cấp hoặc thu hồi IAM permissions.** Chặn một Pod nói chuyện TCP với dịch vụ khác không tương đương chặn **s3:PutObject**. Ngược lại, role chỉ có quyền S3 đọc không tự chặn lưu lượng TCP từ Pod đó đến Pod khác.

Khi cần bảo vệ toàn diện, phải xét **nhiều lớp đồng thời**: identity và quyền API, mạng, mã hóa TLS, cấu hình ứng dụng, admission control, image security, runtime security và khả năng giám sát.

## 4. Kubernetes NetworkPolicy: nguyên tắc đánh giá

**NetworkPolicy** là một API Kubernetes chuẩn, nhóm **networking.k8s.io/v1**, áp dụng cho **Pod trong namespace**. Một policy dùng **podSelector** để chọn Pod bị điều khiển, rồi khai báo các kết nối **ingress/egress** được phép.

### 4.1. Mặc định là cho phép khi chưa có policy

Theo mô hình chuẩn:

- Pod **chưa bị policy ingress nào chọn** thì mặc định ingress không bị cô lập bởi NetworkPolicy.
- Pod **chưa bị policy egress nào chọn** thì mặc định egress không bị cô lập bởi NetworkPolicy.
- Khi một Pod được policy chọn cho **Ingress**, chỉ những luồng ingress được các policy cho phép mới hợp lệ.
- Khi một Pod được policy chọn cho **Egress**, chỉ những luồng egress được các policy cho phép mới hợp lệ.

**Một yêu cầu giữa hai Pod** cần được phép ở cả **egress của Pod nguồn** và **ingress của Pod đích**, nếu hai phía đang bị policy cô lập theo từng chiều. Các policy cùng chọn một Pod có quyền **cộng gộp (union)**; thứ tự tạo policy không quyết định kết quả.

### 4.2. Ingress khác egress

~~~mermaid
flowchart LR
    FE["Pod frontend"] -->|"Egress frontend + ingress api:<br/>TCP 8080"| API["Pod api"]
    API -->|"Egress api + ingress redis:<br/>TCP 6379"| REDIS["Pod redis"]
    API -->|"Egress DNS: TCP/UDP 53"| DNS["CoreDNS trong kube-system"]
~~~

Ví dụ trên minh họa **những hướng kiểm soát khác nhau**; các chính sách chỉ hoạt động khi network plugin có implementation hỗ trợ.

### 4.3. Một vài nguyên tắc chọn lọc

| Thành phần | Ý nghĩa |
|---|---|
| **podSelector: {}** ở phần spec | Chọn **mọi Pod** trong namespace của policy |
| **matchLabels: app: api** | Chọn Pod mang nhãn **app=api** |
| **namespaceSelector** | Chọn namespace theo nhãn; có thể kết hợp podSelector trong **cùng một phần tử** để chọn Pod thuộc namespace đó |
| **ipBlock.cidr** | Chọn phạm vi IP/CIDR; cần kiểm tra hành vi với NAT/service translation của CNI |
| **policyTypes: [Ingress, Egress]** | Cô lập cả hai chiều cho Pod được chọn |
| **ingress / egress rules** | Các peer và port/protocol được phép |

**Mẫu YAML phổ biến gây lỗi:** hai phần tử riêng trong **from:** như **- namespaceSelector: ...** và **- podSelector: ...** thường là phép **OR**, không phải yêu cầu Pod cùng thỏa cả hai. Khi muốn chọn **các Pod mang nhãn trong một namespace cụ thể**, đặt **namespaceSelector và podSelector vào cùng một phần tử**.

### 4.4. Không có Deny tường minh trong NetworkPolicy chuẩn

NetworkPolicy Kubernetes thông thường là tập các **quy tắc cho phép (allow)**. Để chặn mặc định, chọn Pod bằng policy với rule list rỗng rồi tạo các allow policies khác. Không có thứ tự rule kiểu firewall để viết **Deny ưu tiên hơn Allow** trong chính API NetworkPolicy chuẩn.

**Điểm nâng cao trên EKS:** những phiên bản Amazon VPC CNI/EKS hỗ trợ có thể cung cấp **ClusterNetworkPolicy** ở cấp admin/cluster, với hành động như **Deny** theo API riêng của AWS. Đây **không phải** cùng tài nguyên với **networking.k8s.io/v1 NetworkPolicy**. Khi dùng loại policy nâng cao, phải kiểm tra version, thứ tự ưu tiên và semantics của tài liệu AWS cho loại resource đó. Bài thực hành bên dưới sử dụng **NetworkPolicy chuẩn** để người học hiểu nền tảng trước.

### 4.5. Giới hạn L3/L4

NetworkPolicy chuẩn thường điều khiển **Pod/IP/port/protocol**, không lọc **HTTP path**, tên API, nội dung request, danh tính người dùng hoặc các rule AWS IAM. Nếu cần chặn **GET /admin**, xét authorization ở ứng dụng, API Gateway/WAF, service mesh hoặc sản phẩm bảo mật lớp 7 phù hợp. Không coi NetworkPolicy là hệ thống DNS-based firewall tổng quát; IP bên ngoài có thể thay đổi theo thời gian.

## 5. Amazon VPC CNI phải thực thi policy thì YAML mới có tác dụng

Một file YAML **NetworkPolicy được Kubernetes API chấp nhận** không có nghĩa traffic chắc chắn đã được chặn. Cluster cần **CNI/network policy engine** hỗ trợ và đã bật enforcement. Trong EKS dùng Amazon VPC CNI, AWS cung cấp tính năng NetworkPolicy qua **network policy controller** và **network policy agent**.

### 5.1. Điều kiện và giới hạn Amazon VPC CNI

| Điều kiện | Ý nghĩa vận hành |
|---|---|
| **Amazon VPC CNI network policy feature phải được bật** | Không bật mặc định trên mọi cluster; kiểm tra add-on configuration |
| **Phiên bản hỗ trợ** | Đối chiếu tài liệu hiện hành về VPC CNI/EKS; AWS nêu yêu cầu **VPC CNI 1.21.0 trở lên** cho nhóm standard và admin policies trong hướng dẫn hiện hành |
| **EC2 Linux worker nodes** | VPC CNI network policy không áp dụng cho Pod trên **Fargate** hoặc node **Windows** |
| **Hệ điều hành/kernel phù hợp** | eBPF network policy agent cần kernel và node OS được hỗ trợ |
| **hostNetwork** | Pod dùng host networking không được áp dụng network policy theo cách thông thường của VPC CNI |
| **Primary Pod interface** | VPC CNI policy áp dụng trên interface chính (**eth0**); interface bổ sung từ Multus hoặc cơ chế khác có thể nằm ngoài |
| **IPv4/IPv6** | Quy tắc phải cùng IP family mà cluster sử dụng; rule family khác có thể bị bỏ qua |
| **Controller-managed Pods** | Policy enforcement được tối ưu cho Pod có **ownerReferences**, ví dụ Deployment/ReplicaSet; Pod độc lập tạo trực tiếp có thể có hành vi không nhất quán |

Nếu cluster dùng **Calico**, **Cilium** hoặc giải pháp policy bên thứ ba, phải kiểm tra plugin nào thực sự thực thi chính sách. Không để hai policy engines đồng thời quản lý cùng luồng một cách thiếu kiểm soát; khi di chuyển engine cần quy trình thay node và kiểm chứng rule cũ.

**Hạn chế theo phiên bản có thể thay đổi.** Trước rollout production, kiểm tra tài liệu AWS cho đúng Kubernetes version, VPC CNI add-on build, loại node, OS, chế độ kết nối và cluster network mode.

### 5.2. Bật feature cho add-on phù hợp

Với **EKS managed add-on vpc-cni**, AWS cho phép cấu hình **enableNetworkPolicy** và node agent qua phần configuration values. Ví dụ lệnh **đọc trước**:

~~~bash
aws eks describe-addon \
  --region ap-southeast-1 \
  --cluster-name demo-eks \
  --addon-name vpc-cni \
  --query 'addon.{Version:addonVersion,Status:status,Configuration:configurationValues}' \
  --output json
~~~

Để cập nhật add-on, cần xem **addon version**, schema cấu hình phiên bản, quyền IAM, loại node, các custom configuration đang dùng và kế hoạch rollback. Không sao chép một lệnh update thiếu các thiết lập đã tồn tại, bởi cập nhật add-on có thể ghi đè giá trị hoặc làm gián đoạn kết nối Pod.

Ví dụ cấu hình ở mức khái niệm (không phải lệnh có thể áp dụng cho mọi version):

~~~json
{
  "enableNetworkPolicy": "true",
  "nodeAgent": {
    "enablePolicyEventLogs": "true"
  }
}
~~~

Trong môi trường dùng **self-managed VPC CNI**, cấu hình thay đổi thông qua Helm hoặc DaemonSet theo hướng dẫn AWS thay vì luôn dùng managed add-on. Tất cả thay đổi ở network layer phải được thử trên môi trường đại diện trước production.

### 5.3. Standard mode và strict mode

Amazon VPC CNI có hai chế độ ảnh hưởng tới **giai đoạn Pod vừa khởi tạo**:

| Mode | Giai đoạn NetworkPolicy chưa được lập đủ | Hệ quả |
|---|---|---|
| **standard** | Pod có thể bắt đầu bằng **default allow** trước khi rule được áp dụng | Có khoảng thời gian đầu đời Pod chưa bị cô lập như mong muốn |
| **strict** | Pod bắt đầu với **default deny** trước khi rule cụ thể được áp dụng | Chặt chẽ hơn nhưng phải có policy cho DNS và mọi dependency khởi động |

Chế độ strict được đặt bằng cấu hình **NETWORK_POLICY_ENFORCING_MODE=strict** trong **aws-node** theo tài liệu triển khai. Strict mode có thể khiến **CoreDNS, monitoring agent, webhook hoặc Pod bootstrap** không hoạt động nếu thiếu allow rules. Pod dùng host network có hành vi đặc thù; phải kiểm tra lớp khác để bảo vệ các luồng đó.

**Cách triển khai:** chuẩn bị policies cho CoreDNS và hệ thống, thử DNS/service discovery, bật mode trên nhóm canary, theo dõi denied flows rồi mới mở rộng. Không chuyển từ standard sang strict trong toàn cluster mà chưa lập bảng các kết nối cần thiết.

### 5.4. Network policy logs

VPC CNI network policy agent có khả năng ghi log quyết định allow/deny. Tài liệu AWS mô tả log ở node, ví dụ **/var/log/aws-routed-eni/network-policy-agent.log**, và tùy chọn chuyển log lên CloudWatch Logs.

**Network policy event logs không mặc định bật trong mọi cấu hình**; việc bật có thể tăng CPU, lưu lượng và chi phí CloudWatch. Chỉ thu thập ở mức cần thiết, đặt retention và tránh log dữ liệu nhạy cảm. Nếu policy không có tác dụng, kiểm tra **policyendpoints.networking.k8s.aws** được network policy controller tạo ra, quyền RBAC cho controller/agent và tình trạng các Pod **aws-node**.

## 6. Ví dụ thực hành: default-deny rồi mở đúng luồng

Giả sử namespace **shop** có ba nhóm Pod, đều được Deployment quản lý:

- **app=frontend**: giao diện/ứng dụng nội bộ, gọi API TCP **8080**.
- **app=api**: ứng dụng Java, gọi cache **redis** cổng TCP **6379** và CoreDNS.
- **app=redis**: cache nội bộ, chỉ nhận kết nối từ API.

Ứng dụng và namespace đã tồn tại; mục tiêu là minh họa **kết nối nội bộ**, chưa bao gồm ingress từ ALB hoặc một ingress controller bên ngoài. Với các đường vào ứng dụng thực tế, cần thêm policy tương ứng theo kiến trúc CNI/ALB và cơ chế kiểm soát nguồn; ví dụ dưới đây **không chủ đích cho phép traffic từ Internet vào frontend**.

### 6.1. Policy A — default deny trong namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: shop
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Khi policy này được thực thi, mọi Pod trong namespace **shop** bị cô lập cả ingress lẫn egress, **trừ** những luồng được các NetworkPolicy khác cho phép. **Không có** nghĩa là Kubernetes lập tức chặn luồng nếu CNI chưa bật enforcement.

### 6.2. Policy B — mọi Pod được truy vấn CoreDNS

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: shop
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

Đây là rule cho DNS phổ biến dùng CoreDNS. **Trước khi áp dụng, kiểm tra nhãn Pod CoreDNS thực tế**, chẳng hạn bằng **kubectl -n kube-system get pods --show-labels**. Với **NodeLocal DNSCache**, DNS proxy hoặc plugin khác, đường đi/nhãn/địa chỉ có thể khác và cần policy phù hợp. DNS egress từ namespace shop chưa đủ nếu policy ở kube-system cũng cô lập CoreDNS ingress.

### 6.3. Policy C — frontend chỉ được gọi API

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: frontend-egress-to-api
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 8080
~~~

Nếu ứng dụng frontend còn cần những kết nối khác như external identity provider, API ngoài cluster hoặc S3 endpoint, các kết nối đó cần được **khảo sát và cấp riêng**. Không thêm **0.0.0.0/0** chỉ để “hết timeout” mà không có đánh giá bảo mật.

### 6.4. Policy D — API chỉ nhận từ frontend, chỉ gọi Redis

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-ingress-egress
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - protocol: TCP
          port: 6379
~~~

Policy này cộng gộp với **allow-dns-egress**, nên Pod API vừa được gọi DNS vừa được kết nối Redis. Nếu API còn gọi RDS, SQS, STS hoặc các dịch vụ AWS qua VPC endpoints, thiết kế đường egress bổ sung; quyền IAM và SG vẫn cần đúng.

### 6.5. Policy E — Redis chỉ nhận từ API

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-ingress-from-api
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: redis
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 6379
~~~

Kết quả mong muốn đối với traffic nội bộ:

| Luồng | Kỳ vọng | Vì sao |
|---|---|---|
| Frontend → API TCP 8080 | **ALLOW** | Egress frontend và ingress API đều cho phép |
| API → Redis TCP 6379 | **ALLOW** | Egress API và ingress Redis đều cho phép |
| Frontend → Redis TCP 6379 | **DENY** | Redis chỉ cho phép source **app=api** |
| API → CoreDNS TCP/UDP 53 | **ALLOW** khi policy/nhãn khớp | Allow DNS egress được cộng gộp |
| Redis → API TCP 8080 tạo kết nối mới | **DENY** | Không có allow rule tương ứng |
| Pod khác namespace → API | **DENY** nếu không có policy cho phép | API ingress chỉ chọn frontend cùng namespace |

**Tính stateful của kết nối:** phản hồi của một kết nối đã được phép thường được network plugin xử lý để lưu thông; bảng trên nói về **kết nối mới**, không phải từng packet response.

### 6.6. Thứ tự áp dụng trong lab

Một cách ít rủi ro là lưu từng policy thành manifest tương ứng, kiểm tra label và áp dụng **allow policies trước**, sau đó mới áp dụng **default-deny-all**. Với môi trường thử nghiệm:

~~~bash
# Chỉ ví dụ: các tệp manifest cần được tạo tương ứng với YAML ở trên.
kubectl apply -f allow-dns-egress.yaml
kubectl apply -f frontend-egress-to-api.yaml
kubectl apply -f api-ingress-egress.yaml
kubectl apply -f redis-ingress-from-api.yaml
kubectl apply -f default-deny-all.yaml

kubectl -n shop get networkpolicy
kubectl -n shop describe networkpolicy api-ingress-egress
kubectl -n shop get pods -L app -o wide
~~~

Chạy thử các kết nối từ **Pod do Deployment/ReplicaSet quản lý** để tránh giới hạn policy trên standalone Pod của VPC CNI. Nếu dùng **kubectl exec** để chẩn đoán, container phải có công cụ cần thiết; production image dạng distroless thường không có shell/curl. Có thể sử dụng một **Deployment chẩn đoán tạm thời** có quyền và nhãn được kiểm soát.

**Trình tự trong production:** đưa policy qua CI/CD, kiểm tra impact, triển khai canary, theo dõi denied flows và rollback. Cấu hình NetworkPolicy không giải quyết các lỗi SG/NACL, Route 53, DNS hoặc IAM.

## 7. Bảo mật mạng EKS vượt ngoài NetworkPolicy

### 7.1. Security groups for Pods

Trong các cấu hình **Amazon VPC CNI trên EC2** được hỗ trợ, **Security Groups for Pods** có thể gán SG cho Pod qua cơ chế **SecurityGroupPolicy**/branch ENI. Điều này đặc biệt hữu ích khi cần giới hạn giao tiếp từ một nhóm workload đến **RDS**, ElastiCache hoặc dịch vụ mạng AWS.

NetworkPolicy tập trung **Pod-to-Pod/in-cluster L3/L4**, còn SG for Pods tập trung **lớp VPC ENI** và các resource khác. Dùng đồng thời cần đảm bảo **cả hai cùng cho phép** luồng; SG cho phép port 5432 không thể vượt qua NetworkPolicy đang chặn egress.

**Chi phí/giới hạn:** SG for Pods tạo yêu cầu ENI và các giới hạn pod-ENI trên instance; có thể làm chậm Pod startup hoặc gây **Insufficient vpc.amazonaws.com/pod-eni**. Kiểm tra instance types, số ENI, IP và quota trước khi triển khai đại trà.

### 7.2. IAM cho Pod: EKS Pod Identity và IRSA

Để Pod gọi AWS API, ưu tiên dùng **IAM role gắn với Kubernetes service account**, theo **EKS Pod Identity** hoặc **IAM Roles for Service Accounts (IRSA)** khi phù hợp:

- **EKS Pod Identity** sử dụng association của EKS giữa service account và IAM role, với Pod Identity Agent trên các node được hỗ trợ.
- **IRSA** sử dụng OIDC identity provider của cluster, annotation service account và trust policy phù hợp.

Hai cơ chế này cấp **AWS credentials tạm thời** cho ứng dụng; chúng **không thay thế Kubernetes NetworkPolicy**, không tự mở SG và không quyết định quyền Kubernetes API của service account. Tránh cho Pod dùng quyền rộng của EC2 node instance profile hoặc mở IMDS không cần thiết.

### 7.3. EKS API endpoint và truy cập quản trị

EKS cluster endpoint có thể cấu hình **public**, **private** hoặc cả hai theo tùy chọn dịch vụ. Khi dùng public endpoint, hạn chế **public access CIDR ranges**, đảm bảo IAM authentication, EKS access entries/Kubernetes RBAC và audit logs. Với private endpoint, cần có kết nối mạng hợp lệ từ máy quản trị/CI đến VPC, chẳng hạn VPN, Direct Connect hoặc runner bên trong VPC.

**Ẩn endpoint ra private không tự chặn một principal đã có quyền thao tác Kubernetes API từ mạng được phép.** IAM/RBAC và quyền cluster vẫn phải tuân thủ least privilege.

### 7.4. TLS, admission và workload security

- Dùng HTTPS/TLS qua Ingress/ALB hoặc service mesh tùy nhu cầu; NetworkPolicy không mã hóa payload.
- Hạn chế privileged containers, hostPath, hostNetwork, Linux capabilities và quyền service account.
- Áp dụng **Pod Security Standards** với admission hoặc giải pháp policy phù hợp (ví dụ Kyverno/Gatekeeper) theo tính năng cluster.
- Quản lý secret qua Kubernetes Secrets kết hợp encryption/KMS và giải pháp quản lý secret ngoài cluster nếu cần.
- Quét image từ ECR hoặc registry khác, pin image digest/phiên bản, đặt resource requests/limits.

## 8. Vận hành EKS nhiều AZ: thiết kế thật chứ không chỉ chọn subnet

### 8.1. Phân bố subnet và worker nodes

AWS khuyến nghị thiết kế EKS cluster qua **ít nhất hai AZ**, và với hệ thống quan trọng thường cân nhắc ba AZ khi Region/vùng mạng hỗ trợ. Subnet dành cho EKS/control-plane ENIs, node groups, private workloads và public load balancer phải được lập kế hoạch hợp lý.

Ví dụ mạng:

| AZ | Private subnet | Workload minh họa | Hạng mục cần dự phòng |
|---|---|---|---|
| AZ A | 10.20.0.0/20 | Node A + API Pod A | EC2 capacity, IP addresses, đường ra |
| AZ B | 10.20.16.0/20 | Node B + API Pod B | EC2 capacity, IP addresses, đường ra |
| AZ C | 10.20.32.0/20 | Node C + API Pod C | EC2 capacity, IP addresses, đường ra |

Các CIDR chỉ là ví dụ. Đảm bảo chúng không chồng lấn với mạng khác và có đủ IP cho **Pod ENIs, nodes, load balancers và nâng cấp**. Amazon VPC CNI dùng IP VPC cho Pod trong các cấu hình thường gặp; IP exhaustion có thể khiến Pod **Pending/ContainerCreating** dù EC2 còn CPU/RAM.

**Đường ra Internet:** private subnet có thể sử dụng NAT Gateway hoặc VPC endpoints. Một NAT Gateway duy nhất ở AZ A là điểm phụ thuộc liên AZ; nếu AZ A gặp sự cố hoặc route sang NAT ở AZ A bị hỏng, Pod ở AZ B/C có thể mất egress. Cân nhắc NAT theo AZ và route của từng private subnet hoặc VPC endpoints phù hợp, đánh đổi với chi phí.

### 8.2. Vị trí của node không tự quyết định vị trí Pod

Một managed node group có subnet ở ba AZ có thể mang lại worker capacity đa AZ, nhưng scheduler chỉ dựa trên **requests, taints/tolerations, affinity, topology** và tình trạng node để chọn. Nếu không có scheduling rules, ba replica có thể vẫn nằm gần nhau.

~~~bash
kubectl get nodes -L topology.kubernetes.io/zone
kubectl -n shop get pods -o wide
kubectl -n shop get deployments
~~~

Đối chiếu **Pod → Node → topology.kubernetes.io/zone**; lệnh get pods thông thường không hiển thị AZ trực tiếp trên mọi phiên bản, nên phải tra node label hoặc công cụ observability phù hợp.

### 8.3. Topology spread constraints

Ví dụ Deployment cho API có ba replica và yêu cầu phân bố tương đối đều theo AZ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: orders-api
      containers:
        - name: app
          image: 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:stable
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              memory: "512Mi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
~~~

Đây là manifest học tập; image URI phải tồn tại, DNS/secret/network và Node capacity phải sẵn sàng. **topologyKey = topology.kubernetes.io/zone** dựa vào node label. **maxSkew: 1** giới hạn độ chênh replica giữa các miền đủ điều kiện. **DoNotSchedule** có thể khiến Pod Pending khi không thể thỏa constraint.

**Không hứa rằng ba replica luôn nằm đúng ba AZ.** Với chỉ hai AZ đủ điều kiện hoặc khả năng scheduling thay đổi, vẫn có thể có chênh lệch theo semantics scheduler. Nếu bắt buộc ba AZ, hãy xác định eligible domains và dùng thêm node affinity, **minDomains** hoặc chính sách theo phiên bản Kubernetes phù hợp, rồi kiểm thử thực tế. **ScheduleAnyway** giảm rủi ro Pod Pending nhưng chỉ là ưu tiên mềm, không bảo đảm phân tán cứng.

### 8.4. Pod anti-affinity và phân tán theo node

Topology spread theo **zone** giúp phân tán giữa các AZ; để tránh nhiều replica nằm trên cùng một node, có thể thêm spread constraint theo **kubernetes.io/hostname** hoặc **podAntiAffinity**:

- **preferredDuringSchedulingIgnoredDuringExecution**: cố ưu tiên khác node/AZ khi có thể.
- **requiredDuringSchedulingIgnoredDuringExecution**: bắt buộc điều kiện tại thời điểm scheduling; có thể gây Pending khi không đủ node.

**Trade-off:** ràng buộc quá cứng tăng HA trong điều kiện đủ capacity nhưng có thể làm rollout kẹt hoặc không phục hồi sau sự cố AZ nếu scheduler không được phép dồn Pod về những AZ còn khỏe. Chọn chính sách theo **SLO và khả năng chấp nhận giảm bảo vệ sau sự cố**, không áp dụng DoNotSchedule cho mọi Deployment một cách máy móc.

## 9. PodDisruptionBudget, rollout và health probes

### 9.1. PodDisruptionBudget (PDB)

**PDB** kiểm soát số Pod có thể bị gián đoạn trong các **voluntary evictions** dùng Eviction API, ví dụ khi drain node để bảo trì. Với deployment **orders-api** có ba replica:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: shop
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

PDB yêu cầu giữ **ít nhất hai Pod khỏe** trong các tình huống eviction tự nguyện được hỗ trợ. **PDB không ngăn được mất node/AZ đột ngột, Spot interruption, lỗi phần cứng hay mọi lệnh delete/terminate**. Nó cũng không thay thế **Deployment rollingUpdate.maxUnavailable/maxSurge**; hai cơ chế cần được thiết kế thống nhất.

Khi một AZ lỗi, PDB không thể buộc hai replica còn lại tự động phục vụ đúng nếu chúng cùng ở AZ đó hoặc backend không sẵn sàng.

### 9.2. Probes và graceful termination

| Cấu hình | Mục đích | Sai lầm thường gặp |
|---|---|---|
| **startupProbe** | Cho ứng dụng khởi động chậm thời gian trước khi đánh liveness | Liveness khởi động quá sớm khiến Pod restart loop |
| **readinessProbe** | Quyết định Pod có vào Service endpoints để nhận traffic không | Trả ready dù DB/config chưa sẵn sàng |
| **livenessProbe** | Phát hiện tiến trình không thể phục hồi và cần restart | Phụ thuộc quá nhiều hệ thống ngoài, gây restart diện rộng |
| **terminationGracePeriodSeconds** | Cho Pod thời gian dừng sạch | Chấm dứt khi request dài hoặc job chưa checkpoint |
| **preStop hook** | Thực hiện bước chuẩn bị trước khi terminate theo lifecycle | Hook quá dài gây timeout/grace exhaustion |
| **PDB** | Giới hạn voluntary disruptions | Cấu hình minAvailable quá cao làm drain/nâng cấp kẹt |

Với ALB/NLB và AWS Load Balancer Controller, cần kiểm tra cả thời điểm thay đổi **Kubernetes EndpointSlice/Service**, trạng thái target group, deregistration và kết nối đang mở. **ReadinessProbe** hoạt động đúng không tự bảo đảm không mất request khi node bị tắt đột ngột.

### 9.3. RTO/RPO nhiều AZ

**RTO** là thời gian phục hồi dịch vụ tối đa mục tiêu; **RPO** là lượng dữ liệu có thể mất tối đa theo thời gian. Nếu app stateless và có đủ replica ở hai AZ còn khỏe, RTO có thể thấp. Nhưng nếu một thành phần stateful lưu dữ liệu duy nhất trên EBS cùng AZ bị mất, ứng dụng có thể không phục hồi được dữ liệu dù Pod mới được schedule.

Vì vậy thiết kế nhiều AZ cần bao gồm **compute, network, ingress, DNS, storage, database, queue, IAM và observability** chứ không chỉ Kubernetes scheduler.

## 10. Storage nhiều AZ: EBS, EFS và database

### 10.1. Amazon EBS là volume cấp AZ

Một **EBS volume** được tạo trong một AZ và chỉ gắn vào EC2 instance trong **cùng AZ**. Với **Amazon EBS CSI driver**, PersistentVolume/PersistentVolumeClaim (PV/PVC) thường gắn với topology của AZ. Nếu Pod StatefulSet/Deployment dùng PVC EBS đang nằm AZ A nhưng scheduler cố đưa Pod tới node AZ B, việc attach có thể thất bại hoặc Pod Pending.

Ví dụ StorageClass (dùng **EBS CSI driver truyền thống trên EC2 worker nodes**, không phải Auto Mode):

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3-wait-consumer
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
allowVolumeExpansion: true
~~~

**WaitForFirstConsumer** trì hoãn việc cấp volume cho đến khi scheduler có thông tin về Pod/node, giúp chọn đúng AZ khi tạo PV lần đầu. Nó **không làm EBS volume có thể tự di chuyển giữa AZ sau khi tạo**. **Retain** giữ PV/dữ liệu sau khi PVC bị xóa theo hành vi reclaim, nhưng không phải backup. Có thể dùng snapshot/backup và restore sang AZ khác theo quy trình nếu cần.

**Phân biệt EKS Auto Mode:** StorageClass dùng provisioner **ebs.csi.eks.amazonaws.com** theo cơ chế Auto Mode; không áp dụng nguyên xi ví dụ **ebs.csi.aws.com**. EBS volumes thông thường không mount cho Fargate Pods; luôn kiểm tra engine và node type.

### 10.2. Amazon EFS cho file share đa AZ

**Amazon EFS** hỗ trợ truy cập NFS qua mount targets phù hợp trong VPC và là lựa chọn khi nhiều Pod cần **ReadWriteMany** trên file storage. Với **EFS CSI driver**, thiết kế mount targets, security group, IAM/access points, latency và throughput hợp lý.

EFS có thể đơn giản hóa việc nhiều Pod đọc/ghi một bộ tệp giữa các AZ, nhưng **không tự giải quyết concurrency, file locking và tính nhất quán nghiệp vụ**. Phải đo latency, network traffic liên AZ, throughput và chi phí.

### 10.3. Database nên tách khỏi đời sống Pod

Đối với transactional data, cân nhắc **Amazon RDS/Aurora Multi-AZ**, **DynamoDB** hoặc dịch vụ database phù hợp. Bản thân ứng dụng có nhiều replica không có nghĩa database cũng HA. Cần connection pooling, retry có giới hạn, timeout, idempotency, backup và kiểm thử failover database.

**Lưu trữ stateful bằng EBS trong một AZ** không nên bị nhầm với bảo vệ dữ liệu khi mất AZ. Nếu tự vận hành database trên Kubernetes, cần thiết kế đồng bộ, quorum, storage placement, backup/restore và controller/operational expertise tương xứng.

## 11. Autoscaling ở nhiều tầng

| Cơ chế | Điều chỉnh cái gì? | Không tự giải quyết |
|---|---|---|
| **Horizontal Pod Autoscaler (HPA)** | Số replica của Deployment/StatefulSet theo metric | Không tự tạo node khi cluster hết chỗ |
| **Cluster Autoscaler** | Số EC2 worker nodes trong node groups/ASG | Không tự sửa resource requests hoặc HA scheduling của Pod |
| **Karpenter** | Provision/consolidate nodes theo scheduling demand và NodePool/NodeClass | Không tự thay workload replication hoặc database HA |
| **EKS Auto Mode** | Tự quản lý nhiều công việc liên quan node/network/storage theo phạm vi tính năng | Vẫn phải cấu hình application scheduling, security và reliability |

HPA scale-out có thể tạo thêm Pending Pods khi **thiếu node**. Cluster Autoscaler/Karpenter cần quan sát các Pending Pods đó và bổ sung nodes đủ CPU/RAM/IP/zone constraints; việc provision thành công phụ thuộc EC2 capacity, quota, subnet IP và giới hạn topology.

### 11.1. Đa AZ và chi phí capacity

- Node group trải nhiều AZ giúp capacity phân tán nhưng phải có chỗ **đón Pod khi mất một AZ**.
- Với volume EBS ràng buộc AZ, node autoscaler phải provision node đúng AZ của PV.
- Nếu dùng **Spot**, cần diversification, khả năng thay thế, PDB/graceful termination và quyết định On-Demand baseline phù hợp.
- Không để **Cluster Autoscaler và Karpenter cùng điều khiển một nhóm node** nếu không có quy hoạch ownership rõ ràng.
- Ràng buộc topology hard kết hợp subnet thiếu IP có thể khiến Pod Pending vĩnh viễn dù còn capacity ở AZ khác.

### 11.2. Quy hoạch IP cho Pod

Amazon VPC CNI thường cấp **địa chỉ IP VPC** cho Pod, nên quy mô workload bị ảnh hưởng bởi CIDR subnet, ENI/IP limits, prefix delegation và cấu hình IP address management. Khi tăng số Pod trên EC2, CPU chưa chắc là giới hạn đầu tiên.

Dấu hiệu thiếu IP:

- Pod stuck ở **ContainerCreating/Pending**.
- Events có thông báo lỗi từ **aws-node/IPAM** hoặc không cấp được Pod IP.
- AWS EC2/VPC subnet không còn đủ địa chỉ hoặc instance đạt giới hạn ENI/IP.

Khắc phục có thể gồm lập lại CIDR, chọn subnet thích hợp, prefix delegation nếu được hỗ trợ, node type có năng lực IP cao hơn hoặc cân bằng workload giữa AZ. Tránh chỉ tăng số node khi subnet không còn địa chỉ.

## 12. Nâng cấp và vận hành an toàn

### 12.1. Thứ tự nâng cấp cần có kế hoạch

Kubernetes/EKS có chu kỳ hỗ trợ phiên bản và tương thích add-ons. Một runbook nâng cấp thường xét:

1. Kiểm tra phiên bản Kubernetes hiện hành, lịch hỗ trợ, **deprecated API**, CRDs, webhooks và workloads.
2. Chuẩn bị backup/restore cho dữ liệu và cấu hình cần thiết; xuất manifest/IaC, xác định phương án rollback ứng dụng.
3. Xác minh **VPC CNI, CoreDNS, kube-proxy, EBS/EFS CSI, AWS Load Balancer Controller**, network policy agents tương thích với đích.
4. Nâng cấp **control plane** theo đường phiên bản được EKS hỗ trợ.
5. Cập nhật add-ons và worker node groups theo hướng dẫn tương thích, lần lượt từng nhóm để giữ capacity.
6. Quan sát **PDB**, target health, DNS, network policy enforcement, EBS attachment, pending pods và SLO.
7. Kiểm thử các luồng API và khôi phục workload, rồi ghi nhận thay đổi.

**Không giả định nâng cấp control plane có thể đảo ngược phiên bản bằng một lệnh.** Phải đọc giới hạn rollback/upgrade của EKS và chuẩn bị khôi phục ở lớp data plane/application.

### 12.2. Khi drain node

**kubectl drain** gửi yêu cầu eviction và có thể bị PDB chặn. Trong một node group đang upgrade, quá nhiều Pod có **minAvailable quá cao**, thời gian kết thúc dài hoặc Pod không thể schedule sang node khác có thể khiến quá trình bị kẹt.

Chỉ thực hiện drain trong môi trường được phép và cửa sổ bảo trì. Trước khi drain, xác minh có đủ nodes, subnet IP, compute capacity ở AZ còn lại, replicas và các PV constraints. Quan sát **kubectl get pdb**, Pod disruptions allowed, events và replacement scheduling.

### 12.3. Multi-AZ không đồng nghĩa Multi-Region

Một EKS cluster là tài nguyên trong một **AWS Region**. Nhiều AZ giảm ảnh hưởng lỗi AZ, nhưng không tự tạo cluster dự phòng ở Region khác. Với yêu cầu phục hồi thảm họa cấp Region cần thiết kế thêm **multi-Region cluster deployment**, DNS failover, dữ liệu replication, secrets/KMS, image registry, CI/CD và diễn tập RTO/RPO.

## 13. AWS CLI và kubectl để kiểm kê (read-only)

Các lệnh dưới đây **chỉ đọc cấu hình/trạng thái** trong môi trường bạn được ủy quyền. Thay cluster, Region, namespace theo hệ thống thực. Với lệnh kubectl, kubeconfig phải trỏ đúng cluster và danh tính có quyền Kubernetes API.

~~~bash
# Thông tin cluster, version và endpoint access.
aws eks describe-cluster \
  --region ap-southeast-1 \
  --name demo-eks \
  --query 'cluster.{Name:name,Version:version,Status:status,Subnets:resourcesVpcConfig.subnetIds,Private:resourcesVpcConfig.endpointPrivateAccess,Public:resourcesVpcConfig.endpointPublicAccess}' \
  --output json

# Kiểm kê managed node groups.
aws eks list-nodegroups \
  --region ap-southeast-1 \
  --cluster-name demo-eks

# Kiểm tra VPC CNI add-on được quản lý.
aws eks describe-addon \
  --region ap-southeast-1 \
  --cluster-name demo-eks \
  --addon-name vpc-cni \
  --query 'addon.{Version:addonVersion,Status:status,Config:configurationValues}' \
  --output json

# Danh sách node và nhãn AZ.
kubectl get nodes -L topology.kubernetes.io/zone

# Workloads, vị trí Pod và network policies.
kubectl -n shop get deployments,pods -o wide
kubectl -n shop get networkpolicies
kubectl -n shop describe networkpolicy default-deny-all

# PDB, events và tài nguyên bị Pending.
kubectl -n shop get pdb
kubectl -n shop get events --sort-by=.lastTimestamp
kubectl -n shop get pods --field-selector=status.phase=Pending
~~~

**Đọc và đối chiếu:** nếu có ba replicas nhưng chúng ở cùng node/AZ, cần xem scheduler constraints và node placement. Nếu NetworkPolicy đã tồn tại nhưng traffic vẫn thông, xác minh network policy engine/feature. Nếu một Pod bị Pending, dùng **kubectl describe pod** để xem **FailedScheduling**, PVC binding, taints hoặc IPAM.

### 13.1. Kiểm tra policy engine (tùy add-on và quyền)

~~~bash
kubectl -n kube-system get daemonset aws-node
kubectl -n kube-system get pods -l k8s-app=aws-node -o wide

# Với add-on hỗ trợ NetworkPolicy:
kubectl get crd policyendpoints.networking.k8s.aws
kubectl -n shop get policyendpoints

# Cần pod name cụ thể; chỉ đọc log khi có quyền:
kubectl -n kube-system logs POD_AWS_NODE \
  -c aws-network-policy-agent --tail=100
~~~

**Lưu ý:** CRD hoặc container agent có thể không tồn tại nếu tính năng chưa bật, phiên bản không hỗ trợ hoặc không dùng VPC CNI engine. Không sửa/xóa **PolicyEndpoint** do EKS quản lý để “thử hết lỗi”.

## 14. Phân tích sự cố thường gặp

| Triệu chứng | Nhóm nguyên nhân cần điều tra | Bằng chứng và hướng xử lý |
|---|---|---|
| **NetworkPolicy tạo thành công nhưng traffic vẫn được phép** | VPC CNI feature chưa bật, Pod Fargate/Windows/hostNetwork, policy chọn sai nhãn, standalone Pod | Kiểm tra add-on, aws-network-policy-agent, policyendpoints, labels, node type |
| **Pod không phân giải DNS sau default deny** | Thiếu allow TCP/UDP 53 hoặc nhãn CoreDNS không khớp | Kiểm tra CoreDNS labels, namespace policies, NodeLocal DNSCache |
| **Frontend gọi API bị timeout** | Thiếu egress frontend hoặc ingress API, SG/NACL/route/port sai | Kiểm tra cả hai chiều NetworkPolicy và network path |
| **API không đến RDS** | NetworkPolicy egress, SG for Pods, RDS SG, DNS, route hoặc IAM/TLS | Kiểm tra pod-to-RDS path, credential và security layers |
| **Pod vẫn thông lúc vừa khởi tạo dù strict posture** | Amazon VPC CNI đang ở standard startup mode | Kiểm tra enforcing mode, kiểm thử startup traffic |
| **Bật strict làm CoreDNS gián đoạn** | Policy chưa cho hệ thống truy cập DNS | Triển khai allow rules cho CoreDNS và dependencies |
| **Pod Pending sau thêm spread constraints** | Không đủ AZ/node eligible, capacity, taints, maxSkew cứng | kubectl describe pod, topologyKey, node labels, autoscaler |
| **Pod StatefulSet Pending vì EBS volume** | PV chỉ có ở AZ A, Pod bị ràng buộc AZ B | PV nodeAffinity, StorageClass WaitForFirstConsumer, PV topology |
| **Pod stuck ContainerCreating** | Thiếu Pod IP, VPC CNI/IPAM/ENI, image pull hoặc volume attach | Pod events, aws-node logs, subnet free addresses |
| **Mất AZ khiến API chỉ còn 0 healthy replicas** | Replicas đều trong một AZ, node groups không phân tán hoặc backend phụ thuộc AZ lỗi | Node/Pod AZ placement, ALB health, data tier |
| **Drain node không hoàn tất** | PDB quá chặt, không có replacement node, PVC bound hoặc Pod không cho eviction | PDB disruptionsAllowed, events, node capacity |
| **HPA tăng replicas nhưng latency không giảm** | DB bottleneck, node autoscaler chưa cấp nodes, policy/network chặn backend | HPA metrics, Pending Pods, DB latency, tracing |
| **Một zone bị nghẽn nhưng HPA chung scale không đúng chỗ** | Load distribution, topology/zone capacity khác nhau | Metric theo AZ, ingress routing, scheduler/autoscaler placement |
| **Chi phí liên AZ tăng mạnh** | Pod nói chuyện DB/cache qua AZ, NAT/traffic đi vòng, cross-zone flows | VPC Flow Logs, Cost Explorer, traffic metrics, topology |

### 14.1. Quy trình phân tích lỗi network policy

~~~mermaid
flowchart TD
    A["App timeout / connection refused"] --> B["Xác minh DNS, IP, port,<br/>Pod source và destination"]
    B --> C["NetworkPolicy chọn những Pod nào?<br/>Ingress + egress"]
    C --> D{"VPC CNI policy engine<br/>đang thực thi?"}
    D -->|"Không / không hỗ trợ"| E["Kiểm tra add-on, node type,<br/>agent, policyendpoints"]
    D -->|"Có"| F["Kiểm tra denied flow logs<br/>và rule/labels"]
    E --> G["Đối chiếu SG, NACL,<br/>route, VPC endpoint, IAM/TLS"]
    F --> G
    G --> H["Sửa rule tối thiểu<br/>kiểm thử cả allow/deny"]
~~~

**Không xóa tất cả network policies chỉ để “test mạng” trên production.** Có thể dùng namespace/staging riêng hoặc thay đổi có phê duyệt và rollback; ưu tiên log/trace, kiểm tra nhãn và định tuyến trước khi sửa lớp bảo vệ.

### 14.2. Quy trình phân tích lỗi đa AZ

1. Xác định loại sự cố: **node/AZ down, subnet IP exhausted, EBS volume bound, DNS/ALB/DB unavailable**.
2. Xem replicas thực, ready pods và AZ của từng node.
3. Kiểm tra scheduling constraints, tolerations, PDB, resource requests, HPA/Cluster Autoscaler/Karpenter.
4. Đối chiếu khả năng cung cấp EC2 capacity và IP ở AZ còn khỏe.
5. Xác minh trạng thái backend và đường mạng từ những Pod đã phục hồi.
6. Kiểm thử synthetic transactions, đo thời gian phục hồi và làm rõ giới hạn RTO/RPO còn lại.

## 15. Tình huống thiết kế

### Tình huống A — Một namespace có ứng dụng và cache

Một nhóm đặt frontend, API và Redis trong namespace **shop**. Hiện mọi Pod đều có thể gọi Redis. Bộ phận bảo mật muốn frontend chỉ gọi API và chỉ API được gọi Redis.

**Yêu cầu:** xây dựng NetworkPolicy default deny ingress/egress, allow DNS, allow frontend → API TCP 8080, API → Redis TCP 6379, và từ chối frontend → Redis.

**Gợi ý:** dùng các policy trong phần 6; thử cả hai phía egress/ingress. Kiểm tra engine Amazon VPC CNI thực thi policy trên EC2 Linux node trước khi kết luận policy hoạt động.

### Tình huống B — Production nhiều AZ nhưng tất cả Pod nằm một AZ

EKS cluster có subnet ở ba AZ. Deployment **checkout-api** có 3 replicas, nhưng tất cả Pod chạy trên node cùng AZ A. Khi AZ A gặp sự cố, service không còn endpoint khỏe.

**Yêu cầu:** mô tả tại sao “cluster có ba subnet” không đủ, và đề xuất thiết kế.

**Gợi ý:** đảm bảo worker capacity trên ba AZ, đặt **topologySpreadConstraints** theo zone, cân nhắc theo hostname, có đủ replica/requests/quota, readiness và PDB. Kiểm chứng bằng Pod → node → AZ; thử mất một AZ và đo tải trên các zone còn lại.

### Tình huống C — Strict mode làm ứng dụng mất DNS

Nhóm bật NetworkPolicy strict mode. Pod API mới không phân giải được địa chỉ **redis.shop.svc.cluster.local**, trong khi kết nối theo IP vẫn có thể hoạt động ở các luồng được cho phép.

**Yêu cầu:** tìm lỗi mà không mở toàn bộ egress.

**Gợi ý:** kiểm tra CoreDNS/NodeLocal DNSCache, UDP/TCP 53, Pod/namespace labels, ingress policy tại kube-system và aws-network-policy-agent logs. Thêm đúng allow policy DNS, không dùng **ipBlock 0.0.0.0/0** như bản sửa duy nhất.

### Tình huống D — EBS PVC khiến Pod không failover AZ

Một StatefulSet có một PVC gp3 đã provision tại AZ A. Sau sự cố node tại AZ A, scheduler cố đặt Pod lên node AZ B nhưng volume không attach được.

**Yêu cầu:** giải thích ràng buộc EBS và lựa chọn khôi phục.

**Gợi ý:** EBS gắn với AZ; **WaitForFirstConsumer** chỉ giúp quyết định AZ tại lúc tạo PV. Khi AZ A không còn sử dụng được, cần phương án restore từ snapshot/backup vào AZ khác hoặc thiết kế lưu trữ/database replication phù hợp. EFS có thể đáp ứng file share đa AZ trong những workload phù hợp nhưng không thay thế database consensus.

### Tình huống E — PDB ngăn nâng cấp node group

Deployment có hai replicas, PDB **minAvailable: 2**, node group cần rollout AMI mới. Kubernetes drain không thể eviction các Pod vì không có Pod dự phòng.

**Yêu cầu:** đề xuất thay đổi mà vẫn bảo vệ SLO.

**Gợi ý:** tăng replicas/capacity tạm thời, phân bố Pod sang node/AZ khác, xem xét PDB và Deployment rollout, đảm bảo nodes mới có thể được tạo trước node cũ bị drain. Không ép delete Pod trong production chỉ để bỏ qua PDB mà không xem tác động.

### Tình huống F — Kết nối RDS thất bại dù NetworkPolicy Allow

API Pod được allow egress tới RDS TCP 5432; kết nối vẫn timeout. RDS được bảo vệ bằng security group, Pod có Security Groups for Pods.

**Yêu cầu:** kể tên các lớp cần kiểm tra.

**Gợi ý:** policy egress, Pod SG và RDS SG, subnet routes/NACL, DNS, đúng endpoint/port, network path, TLS; sau khi TCP thông, kiểm tra IAM/DB credentials và quyền database. NetworkPolicy Allow không vượt qua SG Deny hoặc database authentication.

## 16. Quan sát, bảo mật và chi phí vận hành

### 16.1. Các nguồn thông tin cần duy trì

| Nguồn | Giám sát điều gì? | Vì sao quan trọng |
|---|---|---|
| **CloudWatch Container Insights / Prometheus** | CPU, memory, Pod restarts, cluster/node health | Sizing, HPA và sự cố workload |
| **Kubernetes Events / pod descriptions** | FailedScheduling, eviction, image pull, volume binding | Phân biệt lỗi scheduler, storage và app |
| **Amazon VPC CNI/network policy agent logs** | Rule enforcement, denied flow và vấn đề IPAM | Điều tra network isolation và Pod networking |
| **VPC Flow Logs** | Dòng traffic trong phạm vi log được cấu hình | Kiểm tra SG/route và xu hướng liên AZ |
| **EKS control plane logs** | API server/audit/authenticator/controller/scheduler theo cấu hình | Điều tra truy cập Kubernetes API và vấn đề điều phối |
| **ALB/NLB metrics và app tracing** | Lỗi 4xx/5xx, healthy targets, p95 latency | Chứng minh khách hàng vẫn nhận dịch vụ |
| **AWS Cost Explorer / CUR** | Chi phí EKS, EC2/Fargate, network và storage | Tối ưu TCO và nhận diện chi phí liên AZ |

**VPC Flow Logs và NetworkPolicy logs không giống nhau.** VPC Flow Logs phản ánh luồng VPC theo khả năng ghi log của dịch vụ; network policy agent logs cho biết verdict của policy engine. Không suy rằng cứ có VPC Flow Logs là đã biết chính xác policy Kubernetes nào gây Deny.

### 16.2. Các khoản chi phí dễ bỏ sót

- **EKS cluster/control plane** theo giá hiện hành, bao gồm mức phí khác nhau tùy vòng đời phiên bản nếu có.
- **EC2 managed/self-managed nodes, Fargate** hoặc chế độ compute tương ứng.
- **Inter-AZ data transfer**, NAT Gateway, VPC endpoints, load balancers.
- **EBS/EFS**, snapshots, database, backup và bản sao dữ liệu.
- **CloudWatch logs/metrics**, Prometheus, network policy flow logs và hệ thống bảo mật.
- **Dư địa capacity cho failover**, số replica nền, PodDisruptionBudget làm chậm scale-in và tác động của Spot.

Tối ưu chi phí không nên đánh đổi không được kiểm soát: dồn hết Pod vào một AZ để giảm traffic có thể làm tăng rủi ro downtime. Nếu chọn traffic routing **same-zone**, phải xem cách cân bằng tải, khi một AZ lỗi có thể chuyển sang AZ khác hay không và đo SLO thực.

## 17. Checklist trước production

- [ ] Cluster dùng các subnet thuộc ít nhất **hai AZ** và đã lập kế hoạch capacity trong từng AZ.
- [ ] Worker nodes, critical workloads, DNS/ingress và backend có phương án chịu lỗi một node/AZ.
- [ ] Đã xác nhận CNI/network plugin thực thi NetworkPolicy; không coi YAML được accept là bằng chứng enforcement.
- [ ] Đã kiểm tra giới hạn **EC2 Linux/Fargate/Windows/hostNetwork/standalone Pods** theo phiên bản VPC CNI đang dùng.
- [ ] Đã tạo default deny và allow rules theo các luồng thực, gồm **DNS TCP/UDP 53** khi cần.
- [ ] Đã kiểm tra cả source **egress** và destination **ingress**, network policy logs, SG/NACL và route.
- [ ] Đã tách AWS IAM cho Pods qua Pod Identity/IRSA khỏi Kubernetes RBAC/network permissions.
- [ ] Đã bảo vệ EKS API endpoint, admission, service account, secrets, TLS và node IAM.
- [ ] Đã đặt **topologySpreadConstraints** và/hoặc podAntiAffinity theo SLO, kiểm tra Pod AZ placement.
- [ ] Đã chọn replicas, **PDB**, readiness/liveness/startup probes và graceful shutdown phù hợp.
- [ ] Đã có autoscaler/node provisioning, IP capacity, quotas và đường failover khi AZ mất.
- [ ] Đã biết **EBS volume ràng buộc AZ**; StorageClass, EFS hoặc database HA/DR phù hợp với dữ liệu.
- [ ] Đã thử rollout/upgrade node và hành vi khi không đủ AZ/capacity, không bỏ qua PDB tùy tiện.
- [ ] Đã giám sát denied flows, application SLO, lỗi scheduling, storage, logs và tải theo AZ.
- [ ] Đã đo RTO/RPO, kiểm thử khôi phục và dự toán inter-AZ/NAT/storage/compute cost.

## 18. Ghi nhớ

**Kubernetes NetworkPolicy** là cơ chế giới hạn luồng **L3/L4** tới và từ Pod, nhưng chỉ có tác dụng khi **network plugin thực thi**. Trong EKS dùng Amazon VPC CNI, phải bật tính năng theo phiên bản/node được hỗ trợ và hiểu rõ khác biệt **standard** với **strict**. Một thiết kế **default deny** chỉ an toàn và vận hành được khi đã mở chính xác những luồng cần thiết, nhất là **DNS** và các API/backend quan trọng.

**EKS nhiều AZ** đòi hỏi nhiều hơn việc chọn subnet: phải có **worker capacity và Pod distribution theo AZ**, topology spread/anti-affinity, PDB, probes, autoscaling, mạng và storage phù hợp. **EBS gắn với một AZ** trong khi những dịch vụ như **EFS** hoặc database Multi-AZ cung cấp những mô hình lưu trữ/khôi phục khác. Sự kết hợp **least privilege + multi-AZ scheduling + quan sát + diễn tập failover** giúp ứng dụng an toàn, phục hồi được và có chi phí dự báo tốt hơn.

### Tài liệu AWS và Kubernetes chính thức để đối chiếu

- [Amazon EKS — Limit Pod traffic with Kubernetes network policies](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html) — tính năng, giới hạn và NetworkPolicy/admin policy.
- [Configure Network Policies in Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html) — standard/strict enforcement và node agent.
- [Troubleshoot EKS Network Policies](https://docs.aws.amazon.com/eks/latest/userguide/network-policies-troubleshooting.html) — policyendpoints, logs, common issues.
- [Amazon EKS Best Practices — Network Security](https://docs.aws.amazon.com/eks/latest/best-practices/network-security.html) — NetworkPolicy và lớp bảo vệ VPC.
- [Amazon EKS Best Practices — VPC and Subnets](https://docs.aws.amazon.com/eks/latest/best-practices/subnets.html) — thiết kế multi-AZ và IP addresses.
- [Amazon EKS Best Practices — Data Plane](https://docs.aws.amazon.com/eks/latest/best-practices/data-plane.html) — worker nodes, scheduling, autoscaling.
- [Amazon EKS Best Practices — Cluster Upgrades](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html) — PDB, topology spread, add-ons/worker updates.
- [AWS Prescriptive Guidance — Spread workloads across AZs](https://docs.aws.amazon.com/prescriptive-guidance/latest/ha-resiliency-amazon-eks-apps/spread-workloads.html) — topology spread và anti-affinity.
- [Amazon EKS — Use Kubernetes storage with Amazon EBS](https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html) — EBS CSI, Auto Mode và giới hạn theo node.
- [Amazon EKS — Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-configure-pods.html) — IAM role cho service accounts.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/) — semantics chuẩn và YAML.
- [Kubernetes — Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) — scheduling trên failure domains.
- [Kubernetes — Pod Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/) — PDB và voluntary disruptions.
- [Amazon EKS pricing](https://aws.amazon.com/eks/pricing/) và [AWS Pricing Calculator](https://calculator.aws/) — chi phí theo cluster/compute/network.
