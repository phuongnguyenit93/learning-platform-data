# Network policy cho service discovery: tìm đúng dịch vụ, chỉ cho phép đúng kết nối

Trong một hệ thống microservices, dịch vụ `orders` gọi `payments` qua tên `payments.apps.svc.cluster.local`. Sau khi bật chính sách **default deny egress**, ứng dụng bắt đầu báo “name resolution failed”. Đội vận hành mở cổng 53 để DNS hoạt động, tên dịch vụ được phân giải thành công, nhưng cuộc gọi HTTPS vẫn timeout. Một người đề xuất cho tất cả Pod kết nối tới mọi IP trong cluster để “service discovery chạy lại”.

Đề xuất đó giải quyết được một số triệu chứng nhưng có thể **phá vỡ ranh giới an ninh**. Service discovery và kết nối ứng dụng là **hai luồng có điều kiện cấp quyền khác nhau**: client cần được phép hỏi nơi phân giải/đăng ký dịch vụ; sau đó nó còn cần được phép kết nối tới endpoint ứng dụng, và ứng dụng đích vẫn phải xác thực, phân quyền.

**Network policy cho service discovery** là thiết kế các quy tắc mạng và quyền control plane để workload có thể **tìm được dịch vụ cần thiết**, nhưng không vì thế có quyền dò tìm, thay đổi registry hoặc truy cập mọi service trong hạ tầng. Bài thuộc chương **API và network service security**, module **SECURITY_NETWORK_SECURITY**, liên hệ với phân đoạn mạng, firewall, DNS, NAC, VPN, IDS/IPS, TLS/mTLS, mạng không dây và kiến trúc cloud.

**Nguyên tắc:** **DNS/registry trả lời “dịch vụ ở đâu?”; network policy trả lời “đường kết nối nào được phép?”; authentication/authorization trả lời “chủ thể được thực hiện hành động nào?”**. Không được dùng kết quả phân giải tên hoặc địa chỉ IP như bằng chứng cấp quyền.

## 1. Mục tiêu học tập

Sau bài này, người học cần:

1. Mô tả **service discovery qua DNS**, **service registry/API**, và quá trình chuyển từ tên dịch vụ đến endpoint thực tế.
2. Phân biệt **discovery control plane**, **đường DNS/registry query**, **data plane tới service** và **quyền ở ứng dụng**.
3. Giải thích cách **Kubernetes NetworkPolicy** lựa chọn Pod bằng label, cách policy ingress/egress cộng gộp, và vì sao **default deny** không tự tạo ngoại lệ cho DNS.
4. Thiết kế chính sách tối thiểu cho `orders` → DNS resolver → `payments`, gồm **UDP/TCP 53**, đích Pod, namespace và application port.
5. Nhận biết những biến thể như **CoreDNS, NodeLocal DNSCache, headless Service, ExternalName, dual stack IPv4/IPv6, service mesh và DNS qua proxy**.
6. Giải thích giới hạn của NetworkPolicy chuẩn đối với **FQDN**, identity của service, multicast và bảo vệ node/host.
7. Xây ma trận kiểm thử positive/negative, threat model, telemetry và quy trình rollout/rollback có kiểm soát.

## 2. Service discovery là gì và có những dạng nào?

Khi endpoint thay đổi do autoscaling, deploy, failover hoặc Pod được tái tạo, client không nên hardcode một địa chỉ IP riêng lẻ. **Service discovery** giúp client lấy thông tin tới service logic hoặc các endpoint hiện hành theo cơ chế của môi trường.

| Cơ chế | Cách tìm dịch vụ | Thường xuất hiện ở đâu | Ranh giới cần bảo vệ |
|---|---|---|---|
| **DNS-based discovery** | Truy vấn A/AAAA/CNAME/SRV và cơ chế liên quan | Kubernetes DNS, DNS nội bộ, cloud private DNS | Đường tới resolver, quyền nhìn namespace, tính chính xác câu trả lời |
| **Kubernetes Service** | Tên DNS trỏ tới virtual Service IP hoặc thông tin endpoint theo loại Service | Cluster Kubernetes | Quyền tạo/sửa Service, EndpointSlice, DNS, đường tới Pod |
| **Headless Service** | DNS có thể trả nhiều địa chỉ endpoint thay vì virtual ClusterIP | Stateful workloads, database cluster | Endpoint IP động, client-side selection, policy chọn Pod |
| **Service registry qua API** | Client/agent truy vấn một registry có thông tin instance và health | Consul, Eureka hoặc registry tự xây | Xác thực registry client, quyền read/write và bảo vệ kết nối |
| **Service mesh discovery** | Data plane proxy nhận service identity/endpoint/config từ control plane | Istio/Envoy và nền tảng tương tự | Quyền proxy ↔ control plane, mTLS và policy tới workload |
| **mDNS/zeroconf** | Phát hiện dịch vụ trong phạm vi multicast cục bộ | Wi-Fi/IoT/văn phòng | L2 broadcast/multicast domain, thông tin bị lộ và rogue responders |
| **Cloud service discovery** | Private DNS, managed registry, endpoint service và VPC/VNet DNS | Hệ thống hybrid/cloud | IAM, security groups, route, private endpoint policies |

Không có một kiểu network policy phù hợp cho mọi discovery mechanism. **Kubernetes NetworkPolicy** là trọng tâm thực hành của bài, nhưng các ý tưởng **least privilege, nguồn registry đáng tin, egress control và service identity** cũng áp dụng với VM, cloud và mạng doanh nghiệp.

### 2.1. Khác nhau giữa service name và endpoint

Ví dụ:

~~~text
Service name:       payments.apps.svc.cluster.local
Service port:       8443/TCP
Service ClusterIP:  10.96.30.40       (địa chỉ minh họa)
Endpoint Pod A:     10.244.2.18:8443  (địa chỉ minh họa)
Endpoint Pod B:     10.244.4.21:8443  (địa chỉ minh họa)
~~~

Các IP trên chỉ minh họa một cluster cấu hình dải tương ứng, **không phải quy ước bắt buộc**. Tên `cluster.local` cũng là domain phổ biến nhưng **có thể được thay đổi** trong cài đặt Kubernetes.

Trong mô hình Service `ClusterIP`, DNS thường trả **địa chỉ Service** cho client. Các cơ chế forwarding/load balancing trong cluster sau đó đưa traffic đến endpoint Pod thích hợp. Nhưng:

- Một **headless Service** (`clusterIP: None`) có thể khiến DNS trả **IP của các endpoint** trực tiếp.
- `ExternalName` chủ yếu cung cấp **DNS CNAME**, không tự tạo proxy và không tự đảm bảo đích được phép.
- Backend có thể thay IP do Pod churn; dùng IP được DNS trả ở thời điểm cũ làm định danh lâu dài dễ sai.
- Một `Service` có thể có nhiều port; discovery **không** quyết định ứng dụng được phép dùng tất cả port đó.

### 2.2. Có thể khám phá tên mà vẫn không kết nối được

~~~mermaid
flowchart LR
    A["orders Pod"] -->|"DNS query 53"| D["CoreDNS / DNS resolver"]
    D -->|"A/AAAA/SRV response"| A
    A -->|"TCP 8443"| S["payments Service"]
    S --> EP["payments Pod(s)"]
    EP --> DB[("Payment data")]
    P["NetworkPolicy / CNI"] -.->|"Kiểm tra luồng egress/ingress"| A
    P -.-> EP
    I["mTLS / API AuthN/AuthZ"] -.-> EP
~~~

Sơ đồ là đường logic: chính sách CNI được thực thi tại những điểm **phụ thuộc plugin và datapath**, không có nghĩa một NetworkPolicy controller trung gian nhận tất cả packet như hình vẽ.

**DNS được phép** chỉ đủ để lấy địa chỉ. Nếu `orders` bị chặn **egress tới `payments`** hoặc `payments` bị chặn **ingress từ `orders`**, cuộc gọi vẫn thất bại. Ngược lại, mở kết nối IP mà không giới hạn quyền ở ứng dụng có thể khiến caller hợp lệ gọi sai đối tượng.

## 3. Vẽ trust boundary cho service discovery

### 3.1. Bốn đường cần vẽ riêng

1. **Client workload → DNS/registry:** truy vấn tên, endpoint, thông tin service hoặc health.
2. **Registry/control plane → DNS/agent:** cập nhật danh sách Service và endpoint, dựa trên quyền đọc và theo dõi trạng thái.
3. **Client workload → service endpoint:** TCP/UDP/gRPC/HTTPS thật sự mang dữ liệu nghiệp vụ.
4. **Operator/controller → registry/configuration:** tạo, sửa hoặc xóa service, route, label, EndpointSlice, certificate và network policy.

Một đường control plane như Kubernetes API server phục vụ watch/update của CoreDNS **không giống** việc mọi application Pod đều cần quyền gọi Kubernetes API để dùng DNS.

### 3.2. Mô hình dữ liệu và luồng điều khiển trong Kubernetes

~~~mermaid
flowchart TB
    subgraph CONTROL["Control plane / khu vực quản trị"]
       K["Kubernetes API server"]
       O["Operators / controllers"]
       R["Service / EndpointSlice state"]
       O -->|"RBAC-controlled writes"| K
       K --> R
    end
    subgraph SYSTEM["System namespace"]
       DNS["CoreDNS / DNS service"]
       NODE["NodeLocal DNSCache, nếu có"]
    end
    subgraph APPS["Application namespace apps"]
       ORD["orders Pod"]
       PAY["payments Pod"]
       SVC["payments Service"]
    end
    DNS <-->|"Authorized read/watch qua API"| K
    ORD -->|"DNS UDP/TCP"| NODE
    NODE -.->|"Cache miss/forward khi được cấu hình"| DNS
    ORD -->|"Service IP/endpoint request"| SVC
    SVC --> PAY
    FW["CNI NetworkPolicy + node/cloud firewall"] -.-> ORD
    FW -.-> PAY
    AUTH["Service auth/mTLS/API authorization"] -.-> PAY
~~~

Trong cluster **không bật NodeLocal DNSCache**, Pod có thể hỏi trực tiếp ClusterIP của DNS Service; đường qua NodeLocal trong sơ đồ là nhánh tùy chọn. Một số môi trường dùng DNS proxy do CNI/service mesh cung cấp hoặc resolver bên ngoài nên cần **xác minh `/etc/resolv.conf`, DNS Service và đường đi thực tế** thay vì đoán.

| Boundary | Vấn đề nếu sai | Điểm thực thi |
|---|---|---|
| **Pod → resolver** | Không phân giải được hoặc hỏi nhầm resolver/zone | Egress policy, DNS proxy, endpoint configuration |
| **Resolver → Kubernetes API** | Không nhận cập nhật Service/EndpointSlice hoặc lộ metadata | RBAC/service account, API connectivity, audit |
| **Pod → workload đích** | Lateral movement hoặc timeout do deny nhầm | Pod ingress/egress policy, CNI datapath, cloud ACL |
| **Workload → dữ liệu** | Đúng service nhưng gọi sai tenant/resource | mTLS, token scopes, application AuthZ |
| **Tenant → registry objects** | Tạo service giả/đổi label/endpoint | RBAC, admission policy, namespace ownership |
| **Proxy/mesh ↔ control plane** | Tải route/certificate sai hoặc bị lộ identity | Workload certificates, authorization, management network |

**Tên có thể dễ đoán; quyền truy cập phải khó giả mạo.** DNS security hoặc việc ẩn tên khỏi một giao diện không thay được network segmentation, identity và authorization.

## 4. Kỹ thuật Kubernetes NetworkPolicy: semantics phải hiểu chính xác

Kubernetes `NetworkPolicy` chuẩn cho phép mô tả một số điều kiện lưu lượng **L3/L4** giữa các Pod, namespace và IP blocks. Việc enforcement phụ thuộc **network plugin/CNI thực sự hỗ trợ NetworkPolicy**; tạo object thành công **không chứng minh packet đã bị lọc**.

### 4.1. Policy chọn Pod, không trực tiếp chọn Service theo tên

Ví dụ:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sample-policy
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: orders
  policyTypes:
    - Egress
  egress: []
~~~

Ý nghĩa: **các Pod trong namespace `apps` có label `app=orders`** bị cô lập về **egress** bởi policy này; `egress: []` không cấp đường ra nào. **Ingress** của những Pod đó không bị policy này cô lập nếu không có ingress policy khác. Policy này cũng không nói gì về Pod ở namespace khác.

Không mặc định dùng IP của Pod hoặc DNS name làm selector. Trong **Kubernetes NetworkPolicy chuẩn**, `podSelector` và `namespaceSelector` là các điều kiện trên **labels**; bản thân tên DNS `payments.apps.svc.cluster.local` **không** trở thành một đối tượng `to: FQDN` hợp lệ của NetworkPolicy chuẩn.

### 4.2. Ingress và egress độc lập

- Nếu không policy nào chọn Pod cho **egress**, Pod không bị cô lập egress bởi NetworkPolicy chuẩn.
- Khi có ít nhất một policy chọn Pod và cô lập egress, **chỉ những egress flows được bất kỳ policy áp dụng nào cho phép** mới được cấp phép theo semantics NetworkPolicy.
- Tương tự với **ingress**, nhưng được đánh giá **riêng chiều**.
- Để một kết nối Pod → Pod đi được trong trường hợp cả hai đầu bị cô lập, cần **egress của nguồn** và **ingress của đích** cùng được cho phép. Lưu lượng phản hồi của kết nối được phép được xử lý theo semantics stateful của policy/datapath.
- NetworkPolicy chuẩn về cơ bản kết hợp **allow rules theo kiểu cộng gộp**, không có **explicit deny rule** để phủ định một allow khác. Một policy “deny all” không thể ghi đè allow do policy khác cấp.

Vì vậy:

> **Default deny + thêm allow hẹp** là chiến lược triển khai, không phải hai lớp firewall có quy tắc “deny ưu tiên hơn allow”.

### 4.3. Chọn namespace và Pod: AND khác OR

Trong một phần tử `to`:

~~~yaml
to:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: finance
    podSelector:
      matchLabels:
        app: payments
~~~

**Cả hai selector trong cùng một mục** nghĩa là chọn **Pod có `app=payments` thuộc namespace `finance`**: điều kiện **AND**.

Ngược lại:

~~~yaml
to:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: finance
  - podSelector:
      matchLabels:
        app: payments
~~~

Đây là **hai mục riêng** (OR): mục thứ nhất cho phép mọi Pod trong namespace `finance`, mục thứ hai cho phép các Pod `app=payments` **trong namespace hiện tại của NetworkPolicy**. Nếu đọc nhầm hai cấu trúc, có thể mở kết nối rộng ngoài ý định.

Nhãn namespace `kubernetes.io/metadata.name` được Kubernetes gắn theo phiên bản/khả năng hệ thống; trong cluster cũ hoặc môi trường đặc biệt phải xác minh nhãn hiện có. Nếu dùng nhãn tenant tự định nghĩa, bảo đảm tenant không thể **tự gán nhãn đặc quyền** cho namespace/Pod để đi qua policy.

### 4.4. IPBlock, port và giới hạn selector

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `podSelector` | Chọn Pod của namespace chứa policy hoặc peer Pod trong ngữ cảnh selector | Pod label có thể thay đổi; bảo vệ quyền sửa label |
| `namespaceSelector` | Chọn namespace dựa vào label | Cần chính sách ownership và admission |
| `ipBlock.cidr` | Chọn tập IP theo CIDR; có thể `except` subranges | Không phải nơi phù hợp mặc định cho IP Pod động |
| `ports` | Lọc theo protocol/port, ví dụ TCP 8443 hoặc UDP 53 | Không hiểu phương thức HTTP, hostname hoặc quyền ứng dụng |
| `policyTypes` | Xác định `Ingress`, `Egress` hoặc cả hai | Đừng suy egress bị deny chỉ vì có ingress policy |
| `podSelector: {}` trong `spec` | Chọn mọi Pod trong **namespace policy** | Dùng cẩn thận với deny-all/allow-all |

**NetworkPolicy chuẩn không có native FQDN policy** và không xác thực service identity bằng certificate. Một số CNI cung cấp **policy mở rộng dựa trên FQDN, L7, identity, egress gateway**; phải phân biệt tính năng riêng đó với API chuẩn của Kubernetes.

## 5. DNS lookup là một yêu cầu mạng độc lập

### 5.1. CoreDNS/kube-dns thường đi qua cổng nào?

DNS thông dụng dùng **UDP 53**; **TCP 53** cũng cần được cân nhắc cho trường hợp câu trả lời lớn, retry, transfer trong những hoàn cảnh được phép, hoặc resolver policy cụ thể. Client không nên bị buộc phụ thuộc duy nhất UDP 53 nếu môi trường yêu cầu DNS trên TCP.

Lưu ý:

- **DNS-over-TLS (DoT)** thường qua TCP 853, còn **DNS-over-HTTPS (DoH)** thường dùng HTTPS. Đây **không phải** lối đi mặc định của mọi Kubernetes Pod.
- DNS client còn có thể dùng `nsswitch`, local stub resolver, DNS cache, service mesh DNS capture hoặc sidecar.
- Trong Kubernetes, namespace `kube-system` có thể chứa các Pod resolver được phục vụ qua một Service thường có tên `kube-dns`, nhưng tên, label, IP và topology phải **được kiểm tra tại cluster cụ thể**.
- Hệ thống **NodeLocal DNSCache** có thể lắng nghe tại địa chỉ local của node, ví dụ một IP link-local theo cấu hình. Đường tới resolver đó có thể không được xử lý giống egress thông thường tới CoreDNS Pod.

### 5.2. DNS policy phải xét đường tới resolver thực

~~~mermaid
flowchart TD
    C["App Pod muốn tìm payments"] --> R{"Resolver đang được Pod cấu hình?"}
    R -->|"Cluster DNS Service"| S["DNS ClusterIP"]
    S --> K["CoreDNS Pod(s)"]
    R -->|"NodeLocal DNSCache"| N["Node-local address"]
    N -->|"Cache miss/forward theo policy"| K
    R -->|"Custom/external resolver"| X["Resolver được phê duyệt"]
    K --> A["DNS records/Service state"]
    X --> A
    A --> C
~~~

Một allow rule chọn `kube-system` + label CoreDNS **có thể** hoạt động với datapath/CNI cụ thể, nhưng cần xác minh:

1. Resolver Pod đang dùng **ClusterIP** hay **NodeLocal DNSCache**?
2. CNI đánh giá policy trên **địa chỉ Service trước hay địa chỉ backend sau DNAT**, trong bối cảnh triển khai đó?
3. Pod/CoreDNS có dùng `hostNetwork` hoặc proxy DNS đặc biệt không?
4. Có lối DNS bổ sung cho IPv6 hoặc cloud resolver khác không?
5. Có sidecar/mesh DNS capture khiến truy vấn đi qua một local proxy không?

**Đừng sửa bằng cách mở UDP/TCP 53 tới `0.0.0.0/0` nếu chỉ có một resolver nội bộ cần thiết.** Mở DNS outbound toàn Internet có thể cho phép client sử dụng resolver trái phép, gây mất khả năng kiểm soát query logging và chính sách private DNS.

### 5.3. DNS search path và ndots

Một Pod có thể dùng:

~~~text
/etc/resolv.conf (ví dụ minh họa):
nameserver 10.96.0.10
search apps.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
~~~

Các giá trị **phụ thuộc cluster**. Với short name `payments`, resolver có thể thử thêm search suffix. Không nên suy một lệnh `nslookup payments` chỉ tạo một DNS query. Search behavior, caching và negative responses có thể làm số lượng query tăng; với nhiều service và thất bại DNS, cần xét cả tải/timing.

Đối với hệ thống có split-horizon DNS, DNS name có thể cho câu trả lời khác theo zone/view. Phải phân biệt **tên đúng → địa chỉ đúng → route đúng → quyền đúng**.

## 6. Ví dụ thực hành: `orders` chỉ tìm và gọi `payments`

Giả sử namespace `apps` chứa hai workload:

- `orders`: client gọi API thanh toán.
- `payments`: HTTPS service trên **TCP 8443**.

Service `payments.apps.svc.cluster.local` trỏ tới các Pod có label `app=payments`. DNS trong cluster chạy trên CoreDNS, các Pod DNS có label giả định `k8s-app=kube-dns` và namespace được hệ thống gắn nhãn `kubernetes.io/metadata.name=kube-system`.

**Đây là giả định phục vụ học tập**. Không triển khai policy ngay nếu chưa xác minh **labels, namespace, CNI, resolver path, Service endpoint và phụ thuộc vận hành** của hệ thống thật.

### 6.1. Service ứng dụng (tham khảo)

~~~yaml
# Ví dụ Kubernetes Service, không phải toàn bộ manifest workload.
apiVersion: v1
kind: Service
metadata:
  name: payments
  namespace: apps
spec:
  selector:
    app: payments
  ports:
    - name: https
      protocol: TCP
      port: 8443
      targetPort: 8443
~~~

Theo cài đặt cluster thông thường, Service này nhận **ClusterIP** và DNS name theo cluster domain; tuy nhiên nó có thể chưa có endpoint nếu không Pod nào mang label hoặc chưa sẵn sàng. **Service tồn tại không bảo đảm backend healthy**.

### 6.2. Default deny cho namespace ứng dụng

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress-egress
  namespace: apps
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
~~~

Policy này chọn **mọi Pod trong `apps`**; với CNI hỗ trợ, nó làm những Pod đó bị cô lập ở **cả hai chiều**. Mọi traffic cần thiết sẽ phải được cấp phép bằng policy khác.

**Tác động phải đánh giá trước khi áp:** không chỉ `orders → payments`, mà còn metrics scraping, log forwarding, probe của thành phần ngoài Pod, connection tới DB/queue, identity provider, time sync hoặc control plane tùy kiến trúc. Không áp default deny diện rộng trên production mà không có danh sách luồng và rollback.

### 6.3. Chỉ cho `orders` hỏi DNS resolver được quản lý

~~~yaml
# Minh họa cho cluster có CoreDNS Pods mang label k8s-app=kube-dns
# trong namespace kube-system, và CNI xử lý policy theo Pod labels.
# Nếu dùng NodeLocal DNSCache/DNS proxy, cần điều chỉnh theo datapath thật.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-allow-cluster-dns
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: orders
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

**Giải thích từng bước:**

1. `podSelector` trên chọn **nguồn `orders`** trong namespace `apps`.
2. Trong `to[0]`, namespace và Pod selectors là **AND**: chỉ các Pod được dán label DNS phù hợp trong `kube-system`.
3. Chỉ **UDP/TCP 53** được cấp phép theo rule; nó không mở HTTPS tới tất cả Pod `kube-system`.
4. Policy **không tự mở TCP 8443 tới payments**.
5. **Không đảm bảo tương thích mọi cluster**: nếu DNS truy vấn qua Service ClusterIP/NodeLocal/proxy hoặc CNI đánh giá policy tại một vị trí khác, phải kiểm thử và điều chỉnh theo hướng dẫn sản phẩm.
6. Nếu các Pod **CoreDNS cũng bị cô lập ingress** bởi NetworkPolicy trong `kube-system`, cần có **allow ingress UDP/TCP 53** từ nguồn DNS query hợp lệ theo đường đi thật. Egress allow ở `orders` một mình không ghi đè ingress deny của resolver.

Nếu `payments` cũng cần truy vấn DNS để gọi database/identity service, phải tạo allow DNS tương ứng cho `payments`; ví dụ này **chỉ cấp DNS cho `orders`** để làm rõ quyền tối thiểu.

### 6.4. Cho `orders` kết nối tới Pod `payments`

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-egress-to-payments
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: orders
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: payments
      ports:
        - protocol: TCP
          port: 8443
~~~

Vì `to` chỉ có `podSelector`, nó tham chiếu các Pod `app=payments` **trong cùng namespace `apps`**. Policy không cho phép mọi Pod tên tương tự ở namespace khác.

### 6.5. Cho `payments` nhận kết nối từ `orders`

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payments-ingress-from-orders
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: payments
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: orders
      ports:
        - protocol: TCP
          port: 8443
~~~

Vì default deny đang cô lập cả hai chiều, **cần cả allow egress ở `orders` và allow ingress ở `payments`** để đường ứng dụng này được phép theo semantics của NetworkPolicy chuẩn.

### 6.6. Kết quả mong muốn

| Luồng | Kết quả dự kiến | Điều kiện bổ sung |
|---|---|---|
| `orders → CoreDNS UDP/TCP 53` | ALLOW | Resolver path và CNI khớp giả định |
| `orders → payments:8443/TCP` | ALLOW | Service endpoints đúng; TLS/app hoạt động |
| `orders → payments:5432/TCP` | DENY | Không policy khác cấp phép port này |
| `orders → random Pod in apps:8443` | DENY | Random Pod không được gán label phù hợp |
| `payments → orders` chủ động tạo connection mới | DENY | Trừ khi có allow policy riêng |
| `orders → external DNS/Internet` | DENY | Không có other egress allow; node/host exceptions phụ thuộc datapath |
| `orders → payments` qua direct Pod IP | Có thể ALLOW trên 8443 | NP chọn **đích Pod**, không bắt buộc caller phải qua DNS Service |

Hàng cuối rất quan trọng: **NetworkPolicy cho phép lưu lượng tới Pod phù hợp, không bắt buộc client đã hỏi DNS trước**. Một client biết IP của `payments` có thể kết nối trực tiếp nếu network policy và route cho phép. Nếu ứng dụng cần chứng minh đúng service identity, phải dùng **TLS/mTLS hostname/workload identity và AuthZ**, không chỉ yêu cầu “truy vấn DNS trước”.

## 7. Cross-namespace service discovery và tenant isolation

Giả sử chuyển `payments` sang namespace `finance`, và `orders` ở `apps`. Tên DNS đầy đủ tương ứng có thể là `payments.finance.svc.cluster.local`.

### 7.1. Egress policy với hai selector kết hợp

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-egress-to-finance-payments
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: orders
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: finance
          podSelector:
            matchLabels:
              app: payments
      ports:
        - protocol: TCP
          port: 8443
~~~

Policy tương ứng **cho phép egress** tới `payments` ở `finance`; nếu Pod đích bị ingress-isolated, cũng phải cấp **ingress tại namespace `finance`** cho source `orders` thuộc `apps`.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payments-ingress-from-apps-orders
  namespace: finance
spec:
  podSelector:
    matchLabels:
      app: payments
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: apps
          podSelector:
            matchLabels:
              app: orders
      ports:
        - protocol: TCP
          port: 8443
~~~

Hai YAML này là **các ví dụ thay thế** cho trường hợp cross-namespace, không phải yêu cầu thêm chúng lên cluster cùng ví dụ trước mà không kiểm tra các allow rules cộng gộp.

### 7.2. Label và namespace cũng là tài sản bảo mật

Một rủi ro thường bị quên: nếu caller có quyền tạo Pod với label `app=orders` hoặc thay label namespace thành một giá trị được whitelist, nó có thể thỏa điều kiện NetworkPolicy dù không phải workload có danh tính mong muốn.

Do đó cần:

- RBAC/admission giới hạn quyền tạo/sửa namespace, Pod, labels và service accounts.
- Không dùng label client tự điền làm chứng cứ nhận diện mạnh duy nhất.
- Áp admission constraints với nhãn security-sensitive, namespace owner và workload identity.
- Kết hợp **mTLS/service accounts/IAM** và application authorization cho quyền nghiệp vụ.
- Theo dõi drift khi `Deployment`, `Service`, `EndpointSlice` hoặc policy được thay đổi.

**NetworkPolicy không phải hệ thống xác thực Pod.** Nó áp chính sách theo metadata và địa chỉ/traffic mà datapath quan sát được. Cách cứng hóa metadata và chủ thể tạo Pod là một phần của threat model.

## 8. EndpointSlice, headless Service và đích động

### 8.1. EndpointSlice và cập nhật instance

Các Service controller/nguồn được phép có thể tạo **EndpointSlice** để mô tả những endpoint tương ứng với Service. Khi Pod được tạo mới, scale hoặc đổi readiness, tập endpoint thay đổi.

Điều cần phân biệt:

- **DNS trả tên/địa chỉ tại một thời điểm**; dữ liệu cache/TTL và connection pooling có thể giữ endpoint cũ trong một khoảng thời gian.
- **NetworkPolicy theo label Pod** thường phù hợp hơn hardcode IP Pod, vì endpoint IP có thể đổi.
- **Service selector** và **NetworkPolicy selector** phải được đối chiếu: nếu Service chọn `app=payments` nhưng policy chỉ cho `role=payment-v1`, backend rollout có thể bị lỗi khi gắn label không nhất quán.
- Những Service **không có selector** hoặc EndpointSlice được quản trị thủ công có trust model khác: cần giới hạn quyền thay endpoint và kiểm tra destination IP/identity.

### 8.2. Headless Service

Với `clusterIP: None`, client có thể nhận trực tiếp IP của các Pod được phục vụ. Khi endpoint thay đổi nhanh, kết nối mới được tái định tuyến dựa trên discovery mới; những connection dài hạn có thể vẫn bám endpoint cũ.

Nếu chọn đích theo Pod labels, NetworkPolicy có thể theo kịp Pod churn nhờ CNI được cấu hình đúng. Nhưng nếu discovery trả IP **ngoài cluster**, selectors có thể không bao phủ. Không mặc định cấu hình egress tới một ClusterIP duy nhất như cách bảo vệ mọi mô hình Service.

### 8.3. ExternalName và outbound external service

Với Kubernetes `ExternalName`, DNS thường cung cấp alias/CNAME trỏ tới tên ngoài cluster. Nó **không**:

1. Tự tạo Service proxy tới IP bên ngoài.
2. Tự mở firewall/egress NetworkPolicy.
3. Xác minh TLS certificate của hostname được alias.
4. Chặn client gọi IP/public hostname khác để bypass.

Nếu client kết nối đến tên Service nội bộ nhưng đích cuối có certificate chỉ hợp với tên external, thiết kế TLS/SNI/hostname validation phải được làm rõ; không “fix” bằng bỏ certificate verification.

### 8.4. IP/FQDN-based egress: một giới hạn quan trọng

Kubernetes NetworkPolicy chuẩn hỗ trợ CIDR qua `ipBlock`, **không** có trường native `toFQDNs`. Với dịch vụ SaaS dùng CDN có IP thay đổi hoặc DNS geo-routing:

- Chỉ allow một IP tĩnh có thể làm gãy dịch vụ khi DNS trả IP mới.
- Mở cả `0.0.0.0/0` hoặc `::/0` để giảm lỗi có thể tạo egress quá rộng.
- Một số CNI/secure web gateways hỗ trợ **FQDN-aware egress**, DNS proxy, L7 HTTP policy hoặc service identity policy; đây là **khả năng mở rộng riêng**, cần kiểm tra policy update, cache, TTL, CNAME, IPv6 và đường bypass.
- **Chỉ thấy DNS lookup hợp lệ không có nghĩa kết nối tiếp theo bị ràng buộc vào đúng tên đã lookup**. Client có thể dùng cached IP, direct IP, DoH hoặc DNS ngoài policy.

Đối với ứng dụng public, có thể kết hợp egress gateway, proxy có TLS verification, allowlist được quản lý và workload identity để bảo vệ phù hợp hơn so với IP-only policy.

## 9. Không nhầm DNS reachability với DNS security

Cho phép Pod truy vấn DNS là **quyền network**; nó không tự chứng minh câu trả lời là đúng hoặc dịch vụ có thẩm quyền.

| Vấn đề | Cách xuất hiện | Lớp kiểm soát |
|---|---|---|
| **Rogue resolver** | Pod bị đưa tới máy phân giải không được quản lý | Egress restriction, resolver config, node security |
| **DNS poisoning/misconfiguration** | Resolver/record sai, TTL cũ hoặc zone lẫn | DNSSEC khi áp dụng, change control, logging, monitoring |
| **Service-name enumeration** | Caller đoán tên service và hỏi DNS | DNS access controls khi có, giảm lộ metadata; chủ yếu phải bảo vệ kết nối |
| **DNS tunneling/exfiltration** | Dùng truy vấn DNS làm kênh truyền dữ liệu trái phép | Resolver egress, query analytics, endpoint controls |
| **DoH/DoT bypass** | App dùng HTTPS/TLS resolver khác policy | Egress/web policies, control agent, application audit |
| **DNS amplification/abuse** | Query storm hoặc bất thường traffic | Rate limit, capacity, cache, alerts |
| **Private DNS view leak** | Tên nội bộ bị hỏi ra public resolver | Split DNS và egress DNS restriction |

**Đừng coi khóa UDP 53 đủ để chặn mọi DNS query**: DNS có thể chạy trên TCP 53, DoT, DoH hoặc resolver được nhúng trong ứng dụng. Ngược lại, không chặn toàn bộ HTTPS chỉ vì có thể chứa DoH mà không hiểu các dịch vụ HTTPS hợp lệ.

### 9.1. CoreDNS bản thân cũng cần kết nối control plane

Một policy do đội bảo mật áp lên `kube-system` không đúng có thể làm CoreDNS **không gọi được Kubernetes API server** để theo dõi Service/EndpointSlice, hoặc **không hỏi được upstream resolver** cho domain công khai theo cấu hình.

Khi bảo vệ DNS system components, cần kiểm kê riêng:

- CoreDNS ↔ Kubernetes API server theo phương thức được hạ tầng triển khai.
- CoreDNS ↔ upstream resolver/forwarder, nếu có.
- Health/metrics endpoint, logging và sự sẵn sàng của resolver.
- NodeLocal DNSCache ↔ CoreDNS/upstream và health của DaemonSet tương ứng.
- Policy ở namespace hệ thống, node firewall và control plane network; không giả định NetworkPolicy chuẩn đủ bao trùm hostNetwork/host processes.

Không cho mọi ứng dụng quyền Kubernetes API chỉ vì DNS cần quyền read/watch Service. **Service account/RBAC của DNS** và app workloads phải được tách.

## 10. Service registry: Consul, Eureka và hệ thống tự quản

Trong mô hình registry API, client/agent có thể:

- **Register:** thông báo instance/service và health state.
- **Discover/read:** tra endpoint hiện hành của service.
- **Watch/subscribe:** nhận cập nhật khi endpoint thay đổi.
- **Health check:** đánh giá khả năng phục vụ theo phương pháp triển khai.
- **Deregister:** rút endpoint cũ khi rời hệ thống.

Các thao tác này có **mức quyền khác nhau**. Một ứng dụng chỉ cần gọi `payments` thường **không nên có quyền đăng ký đè endpoint `payments`** hoặc đổi health của service khác.

### 10.1. Phân tách policy theo vai trò

| Chủ thể | Quyền cần thiết | Quyền cần tránh |
|---|---|---|
| Application consumer | Đọc endpoint của service được phép | Đổi registry entries, ACL, admin API |
| Service instance/agent | Đăng ký/trả health cho danh tính của chính nó | Đăng ký thay service khác |
| Registry controller | Quản lý instance theo phạm vi operator | Dùng cùng credential admin cho mọi Pod |
| Operator | Điều tra và thay config được phê duyệt | Truy cập admin trực tiếp từ mọi app namespace |
| Security/automation | Audit, reconcile và thu hồi quyền | Log token/secret nguyên bản |

### 10.2. Một kết nối registry cần bảo vệ cả L3/L4 và L7

- **Network policy:** Pod nào được kết nối registry endpoint, qua TCP/UDP port và network segment nào?
- **TLS/mTLS:** client xác minh đúng registry server và registry xác minh caller khi phù hợp.
- **Registry ACL/RBAC:** caller có quyền `read`, `register`, `update`, `watch` đối tượng nào?
- **Integrity of records:** ai được sửa service name, tags, health, zone, address và port?
- **Egress/application policy:** sau khi nhận endpoint, caller vẫn phải có quyền kết nối và thực hiện API request.

Không kết luận “registry có TLS” nghĩa là mọi client đều được phép sửa record; cũng không coi một ACL registry đầy đủ là thay thế firewall và application authorization.

### 10.3. Registry poisoning và health state bị thao túng

Nếu attacker sửa được endpoint của service `payments` thành máy của họ, client có thể nhận đường sai dù DNS/registry query hợp lệ. Phòng vệ gồm:

- Chỉ cho agent/service identity được phép đăng ký endpoint của chính mình.
- Kiểm tra ownership/zone/namespace và tập địa chỉ được chấp nhận.
- TLS/mTLS với **server identity của dịch vụ đích** sau discovery.
- Giám sát thay đổi endpoint/health bất thường và tài khoản thao tác.
- Không đặt fail-open policy “registry unavailable → gọi bất kỳ IP tìm được”.

## 11. Service mesh, sidecar và network policy

Service mesh có thể cho proxy bên cạnh workload thực hiện service discovery, mTLS, retry và L7 authorization. Nhưng điều đó **không loại bỏ** câu hỏi về mạng:

1. Pod ứng dụng cần kết nối tới local sidecar hoặc inbound/outbound proxy.
2. Sidecar cần lấy cấu hình/service discovery từ **mesh control plane**.
3. Data plane proxy cần kết nối service endpoint đích.
4. Nếu có mTLS, peer workload identity/authorization vẫn phải được xác minh.
5. Một số ứng dụng có thể có luồng **bypass proxy**, cần được policy hóa.

Khi sidecar là container **cùng Pod**, NetworkPolicy chuẩn chọn **Pod**, không phân biệt mọi process/container theo cách của host firewall. Nếu mesh intercept traffic, source/destination mà CNI nhìn thấy có thể khác với suy luận ban đầu. Cần kiểm tra CNI integration và network namespace thực tế.

### 11.1. DNS capture trong mesh

Một số service mesh có thể intercept DNS hoặc proxy DNS lookup, khiến DNS name đi qua local proxy trước khi tới CoreDNS hoặc registry. Chỉ cấp egress từ Pod tới CoreDNS đôi khi chưa đủ, hoặc có thể không đúng point of enforcement. Khi đó:

- Kiểm tra DNS capture đã bật chưa, intercept rules và sidecar lifecycle.
- Xác định backend resolver/control-plane path và timeout.
- Giữ chính sách đường từ proxy tới service endpoint.
- Xác minh L7 authorization và không để DNS route bypass mesh security.

### 11.2. mTLS có thay NetworkPolicy được không?

**Không thay hoàn toàn.** mTLS xác thực peer và bảo vệ kênh theo phạm vi mesh; NetworkPolicy giảm **lateral movement và reachability** ở tầng mạng. Kết hợp:

- **NetworkPolicy:** default deny + allow đúng source/destination/port.
- **Mesh AuthorizationPolicy** (nếu có): workload identity, method/path và service-specific permissions.
- **API AuthZ:** người dùng cuối/tenant/object-level permission.
- **Infrastructure IAM/RBAC:** ai được chỉnh labels, route, certificates và policy.

Nếu sidecar bị bypass, mTLS/mesh policy có thể không còn cover traffic; NetworkPolicy giúp giảm phần nào blast radius. Nếu Pod selectors bị lạm dụng, mTLS identity có thể tiếp tục chặn caller giả danh.

## 12. Dual-stack, cloud và các dạng discovery ngoài cluster

### 12.1. IPv6 và chính sách nhất quán

Một hệ thống dual-stack có thể trả A và AAAA, DNS Service hoặc backend có địa chỉ IPv4/IPv6. NetworkPolicy cần được kiểm thử với cả hai:

- Một allow CIDR IPv4 không tự bao gồm IPv6.
- FQDN có thể resolve tới IPv6 mà client ưu tiên theo hệ điều hành/Happy Eyeballs.
- CNI/cloud network policy phải có enforcement cho traffic IPv6 theo thiết kế.
- Không suy ping IPv4 fail là đã chặn được gRPC/HTTPS IPv6.

Không mở `::/0` chỉ để khắc phục ứng dụng IPv6 bị timeout. Thay vào đó xác minh DNS answer, route và destination workload/egress policy.

### 12.2. Cloud VPC/VNet và hybrid service discovery

Trong hybrid cloud, một DNS query có thể được forward từ on-premises resolver đến **private DNS zone** trong cloud qua VPN/Direct Connect/ExpressRoute hoặc kết nối riêng tương ứng. Những lớp policy phải khớp:

| Lớp | Cần xem |
|---|---|
| DNS forwarding | Zone nào forward đi đâu, resolver IP nào được phép |
| Network routing | VPC/VNet/subnet/VRF route đến private endpoints |
| Security groups / cloud firewalls | Source workloads và port tới service endpoints |
| Kubernetes/CNI policy | Pod-level ingress/egress và DNS path |
| Service identity | TLS hostname, mTLS/authorization và token scopes |
| Observability | DNS query, flow logs, service discovery failures và cloud audit |

Một private DNS name **không tự làm ứng dụng trở thành private**, nếu endpoint cũng public hoặc firewall mở rộng; cần kiểm tra exposure thật và identity.

### 12.3. mDNS trên Wi-Fi/IoT không giống DNS unicast trong cluster

mDNS thường sử dụng **multicast UDP 5353** trong phạm vi mạng cục bộ. Nó có thể làm lộ tên thiết bị hoặc dịch vụ như printer/IoT cho các client cùng broadcast/multicast domain.

Khác với Kubernetes ClusterIP DNS, multicast discovery phụ thuộc L2/VLAN, AP client isolation, multicast filtering hoặc gateway proxy khi đi giữa zone. **NetworkPolicy Kubernetes không phải giải pháp tổng quát cho mDNS trên mạng Wi-Fi.** Cần thiết kế VLAN, firewall/multicast gateway, NAC và chính sách xuất bản service phù hợp.

## 13. Threat modeling: những đường phá vỡ boundary

| ID | Rủi ro | Kịch bản | Kiểm soát và phép kiểm |
|---|---|---|---|
| D01 | **Mở egress DNS toàn Internet** | Pod có thể hỏi resolver trái policy | Allow resolver được quản lý, giám sát DoH/DoT |
| D02 | **Quên TCP 53** | UDP query lớn/truncated hoặc một số kịch bản retry bị lỗi | Kiểm thử DNS UDP/TCP và response size |
| D03 | **Policy selector OR nhầm AND** | Mở quyền sang cả namespace/Pod không mong muốn | Review cấu trúc một peer và nhiều peer |
| D04 | **Label spoofing** | Attacker tự tạo Pod có label được allow | Namespace RBAC, admission, workload identity |
| D05 | **Default deny không được CNI enforce** | Policy object tồn tại nhưng traffic vẫn đi | Kiểm tra CNI support, negative network tests |
| D06 | **NodeLocal DNSCache bị bỏ sót** | DNS thất bại dù đã allow CoreDNS Pods | Kiểm tra `resolv.conf`, path, node/CNI policy |
| D07 | **CoreDNS mất Kubernetes API access** | Service/EndpointSlice thay nhưng record không cập nhật | RBAC, API connectivity, CoreDNS logs |
| D08 | **Registry record bị thay** | Endpoint `payments` trỏ tới attacker | Registry RBAC, certificate identity, change audit |
| D09 | **Service selector trùng/nhầm** | Service chọn sai Pod hoặc cả tenant khác | Label governance, EndpointSlice inspection |
| D10 | **Direct Pod IP bypass discovery** | Caller kết nối đích mà không hỏi DNS | NetworkPolicy và mTLS/AuthZ ở đích |
| D11 | **Headless endpoint churn** | IP cũ gây timeout hoặc trỏ workload khác sau tái sử dụng | Client retry/TTL, label policy và identity |
| D12 | **ExternalName hoặc CDN IP drift** | Egress allowlist lỗi hoặc bị mở quá rộng | FQDN-aware control được thẩm định, egress proxy |
| D13 | **DoH/DoT bypass** | Client dùng HTTPS/853 tới resolver khác | Egress/web policy, endpoint governance |
| D14 | **IPv6 policy gap** | IPv4 bị deny nhưng AAAA/IPv6 còn kết nối được | Dual-stack tests, IPv6 firewall/CNI |
| D15 | **Mesh DNS capture/sidecar bypass** | Policy không chặn đường được suy đoán | Kiểm thử datapath, mesh identity và CNI integration |
| D16 | **Cross-tenant registry read** | Client thấy service metadata của tenant khác | Registry ACL và namespace isolation |
| D17 | **Egress chạm Kubernetes API** | App Pod có token/route tới API không cần thiết | Kube RBAC, service account controls, network scope |
| D18 | **Health thông tin sai** | Endpoint unhealthy vẫn được chọn | Health checks, readiness, retry budget, SLO |
| D19 | **DNS queries/logs lộ metadata** | Query names bộc lộ hệ thống nhạy cảm | RBAC log, retention, redaction |
| D20 | **Allow policy cộng gộp mở rộng** | Policy khác thêm `egress to any` làm default deny vô hiệu thực tế | Policy inventory, admission guardrail, drift detection |
| D21 | **Node/hostNetwork bypass assumptions** | Host process không chịu Pod NetworkPolicy như dự tính | Node firewall, CNI-specific controls, host hardening |
| D22 | **mTLS identity không đúng service** | DNS tới attacker nhưng TLS client bỏ validate | Certificate/hostname/workload ID validation |

### 13.1. Chọn ranh giới ưu tiên theo rủi ro

1. **Chống giả mạo registry:** quyền ghi Service/EndpointSlice/registry và xác minh identity đích.
2. **Chặn lateral movement:** app egress và service ingress chỉ mở theo consumer/provider thực tế.
3. **Ngăn DNS bypass:** resolver được quản lý, telemetry và kiểm soát DoH/DoT theo môi trường.
4. **Bảo vệ control plane:** hạn chế service account token, quyền list/watch và management interface.
5. **Kiểm chứng datapath:** CNI hỗ trợ, node-local/mesh/cloud behavior và IPv4/IPv6 nhất quán.

Không thể suy rằng “chỉ có DNS 53 được mở” nghĩa attacker không thể khám phá service. Discovery có thể xảy ra qua registry API, metadata, log, tệp cấu hình hoặc tên dễ đoán. **Điểm bảo vệ quyết định là không cho caller trái quyền chạm tới service/operation nhạy cảm**.

## 14. Quan sát và chẩn đoán từ DNS đến service

### 14.1. Các nguồn dữ liệu cần ghép

| Nguồn | Thông tin cần xem | Phân biệt điều gì |
|---|---|---|
| **Application** | Tên truy vấn, timeout, TLS error, HTTP/gRPC status | DNS vs TCP vs AuthN/AuthZ |
| **Pod resolver config** | `nameserver`, `search`, `ndots` | Resolver nào và suffix nào đang được dùng |
| **CoreDNS logs/metrics** | Query rate, RCODE, latency, upstream failure | NXDOMAIN/SERVFAIL/timeout |
| **NodeLocal DNSCache** | Cache hits, forward errors, health | Resolver cục bộ hay upstream đang lỗi |
| **Service/EndpointSlice** | ClusterIP, ports, endpoint addresses, readiness | Service có đích hoạt động không |
| **NetworkPolicy/CNI** | Chosen labels, allowed/denied flows, policy revisions | Bị block ở egress hay ingress |
| **Registry API** | ACL decisions, update actor, service revision, endpoint health | Caller không có quyền hay record sai |
| **Mesh/proxy** | Service identity, route, mTLS, proxy error | Data plane reachability vs L7 denial |
| **Cloud/node firewall** | Route, security group/ACL action, node flow logs | Policy ngoài cluster đang chặn |
| **API service** | TLS peer, token scopes, 401/403, per-tenant decision | Gọi đúng đích nhưng không có quyền |

### 14.2. Tách lớp lỗi theo triệu chứng

~~~mermaid
flowchart TD
    A["orders không gọi được payments"] --> D{"DNS lookup có kết quả?"}
    D -->|"Không"| DNS["resolv.conf, CoreDNS/NodeLocal, UDP/TCP 53, CoreDNS RBAC"]
    D -->|"Có"| S{"Service có endpoint ready?"}
    S -->|"Không"| ES["Service selector, EndpointSlice, readiness"]
    S -->|"Có"| N{"TCP 8443 kết nối được?"}
    N -->|"Không"| NP["CNI ingress/egress, routing, Service NAT, node/cloud ACL"]
    N -->|"Có"| T{"TLS/mTLS hợp lệ?"}
    T -->|"Không"| TLS["Certificate, hostname, workload identity, mesh config"]
    T -->|"Có"| H{"API trả success hay 401/403/5xx?"}
    H -->|"401/403"| AZ["Kiểm tra user/service identity và quyền tenant/object"]
    H -->|"5xx"| BE["Backend dependencies, timeout, retry, application logs"]
    H -->|"Success"| OK["Ghi nhận đường đi và policy như mong đợi"]
~~~

**DNS query thành công không đủ kết luận policy ứng dụng đúng; connection timeout không đủ kết luận network policy đã deny đúng.** Hãy dùng test đối chứng từ một Pod hợp lệ và kiểm tra log tại điểm thực thi.

### 14.3. Metric vận hành hữu ích

- Tỷ lệ DNS `NOERROR`, `NXDOMAIN`, `SERVFAIL`, timeout và p95/p99 query latency.
- Tỷ lệ cache hit/forward error của NodeLocal DNSCache hoặc DNS proxy.
- Số lượng Service/EndpointSlice, số endpoint `ready`, endpoint churn.
- Số policy deny cho `orders → payments` và các luồng cross-namespace trái phép.
- Kết nối TCP success/timeout theo service identity, port và CNI policy version.
- mTLS handshake failures, HTTP 401/403/5xx và business SLO.
- Registry read/write audit, quyền ACL thay đổi, bất thường số lượng đăng ký.
- Drift của labels, namespace ownership, DNS resolver config và policy manifests.

Không log raw access token, secret của registry, payload nghiệp vụ hay query chứa dữ liệu cá nhân nếu không cần thiết. Khi quan sát DNS/flow logs, lưu timestamp, Pod UID/namespace và policy revision phù hợp để tránh gán nhầm khi IP được tái sử dụng.

## 15. Các lệnh chỉ đọc để kiểm chứng

Các lệnh dưới đây dùng cho **cluster lab hoặc cluster được cấp quyền kiểm tra**. Đừng tự áp NetworkPolicy, tắt DNS hoặc restart CNI/NodeLocal trong production chỉ để làm bài tập. Không giả định mọi container có shell/`nslookup`/`curl`.

### 15.1. Xác nhận Service và EndpointSlice

~~~bash
# Quan sát Service và endpoint của namespace apps.
kubectl -n apps get service payments -o wide
kubectl -n apps get endpointslice \
  -l kubernetes.io/service-name=payments -o wide

# Xem labels Pod liên quan đến policy.
kubectl -n apps get pods --show-labels
~~~

Nếu Service không có endpoint, cần kiểm tra selector, Pod readiness và namespace. Không sửa network policy theo kiểu mở toàn bộ port để bù cho Service chưa có backend hợp lệ.

### 15.2. Xác minh DNS và NetworkPolicy thực tế

~~~bash
# Quan sát resolver Services và labels Pod của hệ thống DNS.
kubectl -n kube-system get services
kubectl -n kube-system get pods --show-labels
kubectl get namespaces --show-labels

# Đọc policy, không apply/delete/edit.
kubectl -n apps get networkpolicy
kubectl -n apps describe networkpolicy orders-allow-cluster-dns
kubectl -n apps get networkpolicy orders-egress-to-payments -o yaml
~~~

Khi dùng `kubectl describe`, chính sách sẽ chỉ cho biết **ý định cấu hình** và metadata: để khẳng định enforcement, cần thêm CNI capability, flow logs và negative test. **Không mặc định mọi CNI cung cấp policy-deny logs**; có hệ thống chỉ có counters hoặc telemetry giới hạn.

### 15.3. Đọc resolver và kiểm tra tên từ Pod có sẵn

~~~bash
# Lệnh chỉ quan sát từ Pod/Deployment đã tồn tại và có công cụ tương ứng.
kubectl -n apps exec deploy/orders -- cat /etc/resolv.conf
kubectl -n apps exec deploy/orders -- nslookup payments.apps.svc.cluster.local

# Nếu ứng dụng container có getent, có thể dùng để đối chiếu OS resolver.
kubectl -n apps exec deploy/orders -- getent hosts payments.apps.svc.cluster.local
~~~

Các câu lệnh giả định `Deployment/orders` tồn tại và container đã cài `cat`, `nslookup`, `getent`. Distroless container có thể không có các lệnh này; khi đó dùng logging/diagnostics chính thức trong môi trường lab. Không triển khai debug Pod đặc quyền không được kiểm soát trong cluster production.

### 15.4. Kiểm tra ứng dụng có bảo vệ TLS

Trong lab có client phù hợp, có thể gửi một yêu cầu **không làm thay đổi trạng thái** tới endpoint được phép:

~~~bash
# Ví dụ chỉ khi app cung cấp GET /healthz an toàn và cert hợp lệ với host.
# Chạy trong Pod/container lab đã được ủy quyền, có curl.
curl --fail-with-body --show-error --silent \
  https://payments.apps.svc.cluster.local:8443/healthz
~~~

Đừng thêm `-k`/`--insecure` chỉ để vượt lỗi TLS. Nếu certificate không hợp với service DNS name, cần thiết kế **SAN, SNI, service identity hoặc mesh TLS** đúng, chứ không bỏ peer verification. Tùy phiên bản curl, `--fail-with-body` có thể không được hỗ trợ; có thể dùng phương pháp quan sát HTTP code khác.

Một HTTP `200` chỉ chứng minh **một request cụ thể** hoạt động. Không có nghĩa các API ghi dữ liệu đã có authorization đúng.

## 16. Ma trận kiểm thử positive và negative

| ID | Nguồn và hành động | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | `orders` hỏi DNS cluster bằng UDP 53 | Resolve đúng tên | Resolver logs, response, policy path |
| P02 | `orders` hỏi DNS bằng TCP 53 | Resolve theo khả năng server | TCP flow, DNS answer |
| N01 | `orders` hỏi DNS ngoài danh sách được phép | Bị deny theo egress policy | CNI/egress flow, test đối chứng |
| P03 | `orders` tìm `payments.apps.svc.cluster.local` | Nhận địa chỉ phù hợp Service hiện hành | DNS record + Service/EndpointSlice |
| P04 | `orders` gọi `payments:8443/TCP` | Có network reachability; app tiếp tục TLS/AuthZ | Source/dest flow và app logs |
| N02 | `orders` gọi `payments:5432/TCP` | Không được network policy cho phép | Policy/port evidence |
| N03 | `orders` gọi Pod không có label payments | Bị chặn nếu không allow policy khác | Pod labels + deny flow |
| N04 | Pod lạ gọi payments 8443 | Bị ingress policy từ chối | Ingress rule và flow logs |
| N05 | User tenant A dùng DNS tên tenant B | Có thể phân giải, nhưng không được truy cập trái tenant | Network + application AuthZ |
| P05 | Scale payments Pod +1 | Service/EndpointSlice cập nhật, Pod mới nhận đúng policy | Endpoint and label reconciliation |
| P06 | Xóa Pod payments trong lab được phê duyệt | Service bỏ endpoint không còn ready | EndpointSlice/state và recovery |
| N06 | Pod mới thiếu label dự định | Không âm thầm được cấp quyền sai | Policy selection và admission logs |
| N07 | Namespace selector và Pod selector bị tách làm hai peer | Test phát hiện allow rộng ngoài ý định | Policy diff và negative tests |
| P07 | Cross-namespace apps → finance/payments | Đúng ingress+egress và TLS nếu được phép | Namespace labels, CNI logs |
| N08 | Namespace không được duyệt thử gọi finance/payments | Bị deny | Source namespace, policy |
| P08 | CoreDNS hỏi Kubernetes API theo quyền | Đọc được Service metadata cần thiết | CoreDNS health, RBAC and API logs |
| N09 | Application Pod cố ghi registry Service khác | Bị từ chối bởi RBAC/registry ACL | API audit/ACL; không thử trên production |
| P09 | NodeLocal DNSCache nếu có | DNS path được phép và cache hoạt động | Resolver config, NodeLocal metrics |
| N10 | DNS query dùng DoH/DoT ngoài policy | Không bypass được egress security controls | Web/DNS agent, flow logs |
| P10 | Dual-stack A/AAAA | Lưu lượng được phép đúng cho IPv4/IPv6 | Route, DNS, CNI policy |
| N11 | IPv6 route tới zone không được phép | Bị chặn tương đương IPv4 | IPv6 deny logs |
| N12 | Direct Pod IP tới dịch vụ không được cấp quyền | Không vượt segmentation/identity | CNI và service AuthZ |
| P11 | Registry health chuyển unhealthy | Caller không chọn endpoint lỗi theo design | Registry and client logs |
| N13 | Registry entry giả được tạo trong lab | Ghi registry bị chặn nếu caller không có quyền | Audit và identity |
| P12 | Mesh sidecar/capture bật | Data path đúng, mTLS/AuthZ đúng | Proxy/control-plane logs |
| N14 | Mesh bypass path | Không truy cập data service trái policy | CNI deny + service auth |
| P13 | Policy change canary | Đúng behavior và SLO, có rollback | Manifest diff, telemetry |
| N15 | CNI chưa enforce NetworkPolicy | Negative test phát hiện fail-open | CNI status và flow evidence |

Các test liên quan sửa object, scale, xóa Pod hay tạo record giả **chỉ thực hiện trong lab được ủy quyền theo change/test plan**. Bảng là kế hoạch kiểm thử chứ không chỉ dẫn làm gián đoạn hệ thống đang chạy.

### 16.1. Cần phân biệt “deny” thật với lỗi ngẫu nhiên

Một ca negative chỉ được coi là đã xác minh policy khi:

- Có **điểm đích đang hoạt động** và kiểm thử đối chứng từ caller được phép.
- Quan sát đủ DNS answer, đích IP/port và source/destination namespace/Pod context.
- Có bằng chứng từ **CNI policy decision, firewall, mesh hoặc application authorization** tương ứng.
- Không nhầm timeout do Pod crash, thiếu route hoặc cert lỗi với một deny có chủ đích.
- Kiểm tra **IPv4/IPv6** và cả endpoint thay thế (Service IP/headless/direct Pod IP) trong phạm vi cần thiết.

## 17. Troubleshooting: những bẫy dễ gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xác minh |
|---|---|---|
| `nslookup` timeout từ mọi Pod ứng dụng | Default deny chưa allow resolver, NodeLocal path sai | `resolv.conf`, CoreDNS/NodeLocal health, CNI |
| Chỉ DNS TCP fail | Policy chỉ mở UDP 53 | TCP port rule và query qua TCP |
| DNS trả NXDOMAIN với short name | Search suffix/namespace hoặc Service name sai | FQDN và `ndots`, Service inventory |
| DNS trả SERVFAIL | CoreDNS/upstream/control-plane hoặc DNSSEC validation issue | CoreDNS logs, upstream path |
| DNS trả ClusterIP nhưng TCP timeout | App egress hoặc payments ingress deny; Service NAT/route | Source/destination policy, CNI datapath |
| Service tồn tại nhưng không có endpoint | Pod selector không khớp, readiness fail | EndpointSlice/Pod labels/readiness |
| Chỉ một bản deploy payments lỗi | Label mới không khớp policy hoặc certificate | Deployment diff, selectors, mTLS logs |
| Cross-namespace mở rộng bất thường | OR/AND selectors nhầm, namespace label spoof | NetworkPolicy diff, RBAC/admission |
| Internal DNS OK nhưng SaaS public fail | No egress to upstream, FQDN/IP drift, proxy auth | Resolver upstream, egress gateway |
| Dual-stack app kết nối chập chờn | A/AAAA, IPv6 policy gap, route/MTU | DNS + IPv4/IPv6 lookup, CNI logs |
| Chỉ sidecar-injected Pod lỗi | Mesh capture và CNI/registry control plane mismatch | Envoy/mesh policy, proxy route |
| Kết nối HTTP 403 | AuthN/AuthZ thất bại dù network path đúng | mTLS/token/scopes/tenant logs |
| Thỉnh thoảng nhận endpoint cũ | TTL/cache, stale EndpointSlice, connection pooling | Registry/DNS events, client resolver |
| Policy tồn tại nhưng vẫn thông mạng | CNI không enforce hoặc policy khác allow rộng | CNI support, policy union, negative tests |

**Quy tắc điều tra:** luôn làm rõ **query DNS đi đâu**, **địa chỉ nào được trả**, **client kết nối IP/port nào**, **policy nào thực sự chọn Pod** và **lớp nào quyết định từ chối**.

## 18. Runbook thiết kế và rollout trong môi trường thật

### Bước 1 — Kiểm kê các luồng discovery

Liệt kê Pod/namespace/site/tenant, resolver IP/Service, CoreDNS, NodeLocal, mesh DNS capture, registry API, private cloud DNS, Service/EndpointSlice và lưu lượng ứng dụng. Tách **DNS query**, **registry control plane** và **service data traffic** trong sơ đồ DFD.

### Bước 2 — Ghi ownership và trust boundaries

Chỉ rõ ai sở hữu Service/EndpointSlice, ai có quyền thay label/namespace, ai được đọc/ghi registry. Xác định app identities, service accounts, network zones, TLS/mTLS endpoint và quyền user/tenant ở API.

### Bước 3 — Thiết lập baseline và phụ thuộc

Đo DNS query latency, RCODE, HTTP/gRPC success, endpoint churn, CNI behavior, IPv4/IPv6, SLO và flow logs trước khi áp deny. Xác minh **CNI support**, vị trí DNAT, hostNetwork/NodeLocal, Service routing, node/cloud ACL.

### Bước 4 — Tạo allowlist trước khi đóng đường

Chọn một workload hoặc namespace canary, liệt kê các kết nối tối thiểu: DNS UDP/TCP, API đích, logging, metrics, DB/queue và identity control theo nhu cầu thực. Đừng chỉ copy ví dụ `orders`/ `payments` rồi khóa cả namespace production.

### Bước 5 — Áp default deny có điều phối

Phát hành NetworkPolicy theo change window, kiểm tra `policyTypes`, selectors/labels và mọi policy hiện có (vì union cho phép). Giữ đường rollback và quan sát riêng cho DNS/control-plane khi áp policy trong `kube-system`.

### Bước 6 — Kiểm thử positive/negative

Chạy ma trận trên Pod thật: tên service, direct Pod IP, allowed/denied TCP port, cross-namespace, NodeLocal, IPv6, headless Service và mesh. **Bảo đảm denial được chứng minh ở layer dự kiến**, không chỉ vì endpoint không hoạt động.

### Bước 7 — Quan sát sau rollout và rollback

Theo dõi tăng `SERVFAIL`/timeout, CNI drop, 5xx, p95/p99 latency, cache hit, service endpoint readiness và lỗi business. Nếu có tác động ngoài mức chấp nhận, revert policy theo ticket và đối chiếu các allow rules cộng gộp; không tắt hàng loạt lớp bảo vệ không liên quan.

### Bước 8 — Quản trị drift theo vòng đời

Mỗi lần Service thêm port, đổi namespace, scale deployment, bật sidecar, chuyển DNS sang NodeLocal, dùng IPv6 hoặc thêm cloud registry, review lại selectors, RBAC và allow flows. Nên tự động kiểm tra manifest/policy trong CI hoặc admission framework phù hợp, nhưng **việc deploy thành công không thay phép thử runtime**.

## 19. Bài tập tình huống: default deny làm mất service discovery

**Bối cảnh:** Cluster doanh nghiệp có namespace `sales` chứa `orders`, namespace `finance` chứa `payments`, và CoreDNS ở `kube-system`. Đội bảo mật áp default deny ingress/egress lên `sales` và `finance`.

**Quan sát giả định:**

| Quan sát | Câu hỏi cần đặt |
|---|---|
| `orders` đôi khi nhận `SERVFAIL` từ DNS | DNS query đi CoreDNS hay NodeLocal? CoreDNS có gọi Kubernetes API được không? |
| `nslookup payments.finance.svc.cluster.local` đôi khi OK | Service/EndpointSlice, DNS cache và policy path có tương thích? |
| Khi DNS OK, TCP 8443 vẫn timeout | Có cả egress `orders` và ingress `payments` chưa? |
| Policy `to` khai báo hai mục namespaceSelector và podSelector tách riêng | Đây là AND hay OR? Đã mở tới Pod/namespace ngoài dự kiến chưa? |
| `payments` vừa rollout Pods với label `app=payments-v2` | Service selector và NetworkPolicy selector còn khớp không? |
| Một Pod guest cùng cluster biết direct Pod IP của payments | DNS restriction có chặn được kết nối đó không? |
| Registry được bật mTLS nhưng API token cho phép mọi `register` | Tại sao mTLS chưa đủ để bảo vệ ownership của record? |
| Người dùng `orders` gọi một resource thuộc tenant khác và nhận `200` | Vấn đề mạng hay authorization ở application? |

### 19.1. Câu hỏi vận dụng

1. Hãy vẽ **bốn luồng**: `orders → DNS`, `CoreDNS → API server`, `orders → payments` và `operator → Service/EndpointSlice`.
2. Lập chính sách đủ để `orders` ở `sales` hỏi resolver và gọi `payments:8443` ở `finance`, nhưng không gọi được Pod/port khác.
3. Vì sao cần cả **source egress và destination ingress** khi cả hai namespace bị cô lập?
4. Giải thích sự khác nhau giữa **selector AND/OR** trong NetworkPolicy và hậu quả bảo mật.
5. Làm sao phân biệt **DNS resolver path**, **Service endpoint selection**, **network policy deny** và **mTLS/AuthZ failure**?
6. Nếu tổ chức đổi qua NodeLocal DNSCache, những kiểm thử và policy nào phải review lại?
7. Đề xuất ít nhất **ba negative tests** chứng minh caller lạ không thể bypass bằng direct IP, IPv6 hoặc label/namespace khác.
8. Xử lý thế nào khi `payments-v2` đổi label hoặc certificate nhưng chưa cập nhật policy và Service selectors?

### 19.2. Gợi ý đáp án

- **Đường DNS:** client hỏi resolver đúng được cấu hình; CoreDNS cần đường và RBAC tới API server; DNS success chỉ phản ánh discovery path, không có nghĩa caller đã được cấp quyền ứng dụng.
- **Đường service:** egress `orders` phải cho phép **Pod `payments` thuộc finance trên TCP 8443**; ingress payments cho phép **Pod orders thuộc sales**; cả hai dùng selectors cùng một peer (AND). Cần đối chiếu runtime CNI và Service NAT.
- **Label drift:** `Service.selector` và các NetworkPolicy selectors cần được điều chỉnh theo rollout có phê duyệt; policy theo Pod label có thể phải chấp nhận cả thế hệ cũ/mới trong cửa sổ chuyển đổi nhưng không mở wildcard mơ hồ.
- **Direct Pod IP:** DNS không phải enforcement boundary; NetworkPolicy/mTLS/AuthZ phải tiếp tục từ chối caller không có quyền.
- **NodeLocal:** xác minh DNS endpoint, chính sách CNI tới node-local address, cache/upstream path, logs và negative tests; không copy rule CoreDNS-only rồi mặc định nó đủ.
- **Registry/tenant:** mTLS có thể xác thực client registry, nhưng **registry ACL** vẫn phải giới hạn quyền sửa service; quyền đọc resource tenant khác ở API do **application AuthZ** xử lý.

## 20. Checklist Network policy cho service discovery

- [ ] Phân biệt **service discovery**, **network connectivity**, **service identity** và **application authorization**.
- [ ] Đã ghi rõ cách client tìm dịch vụ: DNS, Service/EndpointSlice, registry API, mesh hay mDNS.
- [ ] Vẽ đường DNS/registry và đường data plane tới endpoint **riêng biệt**.
- [ ] Biết resolver thực: CoreDNS ClusterIP, NodeLocal DNSCache, custom DNS proxy hay cloud resolver.
- [ ] Đã kiểm tra UDP/TCP 53 phù hợp và những giao thức DNS khác theo chính sách.
- [ ] Không mở DNS egress toàn Internet nếu chỉ cần resolver do tổ chức quản lý.
- [ ] Đã xác minh Kubernetes NetworkPolicy được CNI **enforce**, không chỉ được API server chấp nhận.
- [ ] Hiểu ingress/egress độc lập, allow rules cộng gộp và default deny không phủ định allow khác.
- [ ] `podSelector`, `namespaceSelector` và `ipBlock` được dùng đúng semantics; AND/OR không nhầm.
- [ ] Namespace/Pod labels có owner, RBAC và admission controls chống giả mạo.
- [ ] Có allow hẹp cho nguồn hỏi DNS và caller gọi đúng destination service/port.
- [ ] Không coi việc DNS resolve thành công là quyền được gọi backend.
- [ ] Bảo vệ Pod đích bằng ingress policy và application TLS/mTLS/AuthZ phù hợp.
- [ ] NetworkPolicy không dùng FQDN như selector chuẩn; đã nhận diện những extension CNI nếu sử dụng.
- [ ] Đã thử Service ClusterIP, direct Pod IP, headless Service và ExternalName khi liên quan.
- [ ] Đã kiểm tra IP/endpoint churn, Service selector, EndpointSlice readiness và cache/TTL.
- [ ] CoreDNS/NodeLocal/control plane có RBAC/route/health checks riêng, không cho mọi Pod quyền API server.
- [ ] Cloud VPC/VNet, node/hostNetwork, service mesh và CNI có ranh giới enforcement được kiểm chứng.
- [ ] IPv4/IPv6 dual-stack và các đường proxy/DoH/DoT không tạo bypass policy.
- [ ] Registry có ACL phân quyền read/register/update/watch và audit thay đổi endpoint/health.
- [ ] Có negative tests cho tenant khác, Pod khác, port khác, direct IP, label spoof và policy union.
- [ ] Quan sát DNS RCODE/latency, CNI flows, Service endpoints, mTLS và API 401/403/5xx.
- [ ] Có canary rollout, change approval, rollback và đo business SLO.
- [ ] Log và dữ liệu query/identity được bảo vệ, không lưu secret/token quá mức.
- [ ] Review lại policy khi thêm port, đổi label, namespace, DNS architecture, cloud endpoint hoặc mesh.

**Ghi nhớ:** **Network policy cho service discovery không đơn giản là “mở DNS 53”.** Phải bảo vệ đồng thời **quyền hỏi resolver/registry, quyền quản trị thông tin endpoint, quyền kết nối tới workload đích và quyền thực hiện thao tác trên API**. Với Kubernetes, thiết kế đúng đòi hỏi hiểu **selector và phép cộng gộp allow rules, hai chiều ingress/egress, datapath của CNI, DNS thực tế và các biến thể NodeLocal/mesh/IPv6**. Chỉ khi kiểm thử được cả đường **được phép** lẫn đường **bị từ chối** mới có thể kết luận discovery hoạt động mà không làm rộng ranh giới tin cậy.
