# Pod network và nguyên tắc mỗi Pod một địa chỉ trong Kubernetes

Một trong những ý tưởng nền tảng của **Kubernetes networking** là: **mỗi Pod có danh tính mạng riêng, thông thường có một địa chỉ IP riêng trên mạng Pod của cluster**. Những container ứng dụng cùng ở trong **một Pod** thường **chia sẻ network namespace, địa chỉ IP, bảng định tuyến và cổng TCP/UDP**; chúng có thể liên lạc với nhau qua **localhost**. Trong khi đó, hai Pod khác nhau được xem như hai đầu cuối mạng khác nhau, kể cả khi chúng cùng chạy trên một node.

Nguyên tắc này giúp ứng dụng container được nhìn như những endpoint mạng có thể kết nối theo mô hình IP quen thuộc, không bắt buộc phải ánh xạ một cổng của mỗi container sang một cổng khác trên host. Nhưng điều đó **không có nghĩa Pod IP luôn cố định, Pod IP nào cũng được mạng bên ngoài truy cập, hoặc các Pod mặc định đã được cô lập an toàn**. Để vận hành đúng phải hiểu **CNI, IPAM, route/overlay/underlay, Service, DNS, NAT, NetworkPolicy, TLS/mTLS, hostNetwork và khả năng quan sát lưu lượng**.

Bài nằm trong chương **Bảo mật mạng Kubernetes** của module **SECURITY_NETWORK_SECURITY**. Trong bối cảnh phòng vệ mạng từ segmentation, firewall, VPN, IDS/IPS, DNS, xác thực kết nối đến cloud network security, Pod network là **đơn vị kết nối mạng gần ứng dụng**. Đây là nền tảng để thiết kế mạng east–west an toàn, hạn chế lateral movement, kiểm soát egress và phân biệt **network reachability** với **workload identity/authorization**.

> **Phạm vi:** các địa chỉ IP, tên Service, manifest và câu lệnh trong bài dùng cho ví dụ hoặc **cluster lab được cấp quyền**. Không áp NetworkPolicy default-deny lên production nếu chưa có allowlist/đường khôi phục được kiểm thử. Một số hành vi phụ thuộc CNI, cloud provider, Kubernetes version và network dataplane; hãy phân biệt **mô hình Kubernetes mong muốn** với **khả năng triển khai cụ thể**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao **Pod** là một đơn vị địa chỉ IP/network namespace, không phải mỗi container mặc định một IP riêng.
2. Phân biệt **Pod IP, container port, host IP, Node IP, Service ClusterIP, external IP và DNS name**.
3. Mô tả cách **kubelet/container runtime/CNI plugin/IPAM** phối hợp tạo network interface, cấp địa chỉ, thiết lập route và dọn state theo vòng đời Pod.
4. Phân tích kết nối **container↔container cùng Pod**, **Pod↔Pod cùng node**, **Pod↔Pod khác node**, **Pod↔Service** và **Pod↔Internet/on-prem**.
5. Nêu ngoại lệ và giới hạn: **hostNetwork, dual-stack IPv4/IPv6, nhiều network interfaces, sidecar/service mesh, Pod sandbox recreation**, cùng sự khác biệt của CNI.
6. Giải thích chức năng của **Service, EndpointSlice, CoreDNS, kube-proxy hoặc dataplane thay thế** và tại sao ứng dụng không nên lưu cứng Pod IP.
7. Thiết kế cơ bản **NetworkPolicy default-deny, allow ingress, allow egress DNS/API**, hiểu selectors, chiều lưu lượng, sự cộng gộp policy và những gì policy không bảo vệ.
8. Nhận diện rủi ro **lateral movement, cross-namespace access, hostNetwork/privileged workloads, metadata/credential exposure, DNS và egress bypass**.
9. Thử nghiệm an toàn bằng **kubectl, các Pod lab nhiều container, Service và NetworkPolicy**, đối chiếu kết quả trước/sau policy.
10. Chẩn đoán các lỗi như **Pod không nhận IP, Pod-to-Pod timeout, Service DNS hoạt động nhưng kết nối lỗi, cổng xung đột, MTU/overlay, policy chặn DNS**.

## 2. Mô hình mạng của Kubernetes: Pod là điểm cuối

### 2.1. Tư duy trước và sau container orchestration

Trên một máy Linux thông thường, nhiều tiến trình có thể dùng chung **network namespace** của host. Chúng nhìn cùng giao diện mạng, route và port space; ví dụ một tiến trình nghe TCP/8080 làm tiến trình khác trên cùng namespace không thể đồng thời nghe **cùng tuple địa chỉ/protocol/port** nếu không có cơ chế socket-sharing thích hợp.

Container runtime có thể tạo network namespace riêng cho container. Kubernetes đưa thêm abstraction: **một Pod gồm một hoặc nhiều container có cùng network namespace theo mô hình Pod thông thường**. Kubernetes không hứa “mỗi container là một host mạng độc lập”; **Pod** mới là đơn vị kết nối chính.

| Đối tượng | Địa chỉ và khả năng kết nối | Vòng đời/ý nghĩa |
| --- | --- | --- |
| **Node** | Có Node IP và network interfaces do hạ tầng cấp | VM/bare metal chạy kubelet và workload |
| **Pod thường** | Có một địa chỉ Pod IP cho mỗi IP family đang dùng trên primary Pod network | Tạo lại/reschedule có thể nhận IP khác |
| **Container A trong Pod P** | Dùng network namespace và Pod IP của P | Không mặc định có IP riêng tách P |
| **Container B trong cùng Pod P** | Cùng IP/localhost/ports với A | Có thể gọi A qua 127.0.0.1 nếu A lắng nghe phù hợp |
| **Pod Q khác Pod P** | Có Pod IP khác trong cluster ở mô hình mặc định | Gọi P qua P Pod IP/Service, không qua 127.0.0.1 của Q |
| **Service (ClusterIP)** | Một virtual IP/service name ổn định hơn Pods | Trỏ traffic tới những EndpointSlices/backends có thể thay đổi |
| **Ingress/Gateway/LoadBalancer** | Điểm vào từ client bên ngoài tùy loại và sản phẩm | Có thể terminate TLS/route tới Service/Pod |

**Địa chỉ IP chỉ là địa chỉ mạng, không phải danh tính có quyền.** Một Pod được cấp IP không tự được quyền gọi mọi Pod khác; quyền nên được kiểm soát qua policy và service identity.

### 2.2. Bốn giả định cốt lõi của mô hình Pod networking

Mô hình Kubernetes phổ biến hướng đến:

1. **Mỗi Pod có một IP duy nhất trong phạm vi Pod network của cluster** ở thời điểm nó đang hoạt động (hoặc một IP tương ứng mỗi family nếu dual-stack).
2. **Các container trong cùng Pod chia sẻ network namespace và có thể liên lạc qua localhost**.
3. **Các Pod có thể giao tiếp trực tiếp với nhau bằng Pod IP** theo khả năng của CNI/dataplane, không cần mỗi ứng dụng tự tổ chức host-port mapping.
4. **Node và Pod networking** phải có các đường cần thiết để kubelet/services hoạt động theo thiết kế.

Những phát biểu này là **mô hình mục tiêu**, không bảo đảm mọi Pod-to-Pod packet đi được nếu **NetworkPolicy, firewall, route, CNI/overlay, security groups hoặc ứng dụng** chặn. Chúng cũng có ngoại lệ như **hostNetwork** và các giải pháp multihoming.

Điểm dễ hiểu nhầm: “Pod giao tiếp trực tiếp không qua NAT” thường mô tả mô hình **Pod IP end-to-end trong cluster**; trên đường thực tế **Service VIP có thể dùng DNAT/load balancing**, và **traffic egress ra ngoài cluster có thể bị SNAT/masquerade**. Không lấy một nguyên tắc logic để khẳng định mọi gói trên mọi path luôn giữ nguyên IP ở mọi hop.

### 2.3. Sơ đồ Pod, container và network namespace

~~~mermaid
flowchart TB
  subgraph N["Node 1 — Node IP 192.0.2.10 (minh họa)"]
    subgraph P["Pod P — Pod IP 10.244.1.12"]
      NA["Container app\nTCP/8080"]
      NS["Container sidecar\nTCP/15000"]
      NET["Một network namespace\neth0, lo, routes, sockets"]
      NA --- NET
      NS --- NET
    end
    subgraph Q["Pod Q — Pod IP 10.244.1.13"]
      QB["Container client"]
      NQ["Network namespace khác\neth0, lo"]
      QB --- NQ
    end
  end
  NS <-->|"127.0.0.1:8080"| NA
  QB -->|"10.244.1.12:8080\nnếu policy cho phép"| NA
~~~

Trong hình, **sidecar gọi app bằng 127.0.0.1:8080** vì chúng nằm cùng Pod; **client ở Pod Q không thể dùng 127.0.0.1 của chính nó** để gọi app của P. Q phải gọi **Pod IP của P hoặc Service DNS/ClusterIP** và đáp ứng network policy tương ứng.

### 2.4. “Mỗi Pod một địa chỉ” có nghĩa chính xác đến đâu?

Nên hiểu phát biểu này là **mỗi Pod thông thường có một định danh IP chính trên mạng Pod mặc định**, thay vì “trong mọi trường hợp vật lý chỉ có đúng một địa chỉ”:

- **Dual-stack Pod** có thể có **một IPv4 và một IPv6** trên primary Pod network.
- **Nhiều interface/multus/SR-IOV hoặc secondary network attachments** có thể cấp thêm IP theo khả năng CNI.
- **hostNetwork: true** đưa Pod vào network namespace của node; nó **không có một IP Pod tách biệt** theo mô hình thông thường và có thể dùng Node IP.
- Một số môi trường có IPv6-only hoặc IPv4-only; không mặc định mọi Pod có IPv4.
- Pod IP có thể thay đổi khi Pod bị thay thế; ngay cả khi một runtime tái tạo sandbox, không nên coi IP là một identity bền vững.

**Mục tiêu khái niệm** là tránh bắt developer quản lý mỗi container như một máy riêng. **Đơn vị lifecycle và policy** quan trọng là Pod/workload, không phải IP cố định trong code ứng dụng.

## 3. Network namespace: vì sao container cùng Pod chia sẻ IP?

### 3.1. Network namespace trong Linux

Network namespace phân tách các tài nguyên mạng của hệ điều hành, chẳng hạn:

- **Network interfaces** như loopback và veth trong namespace.
- **IP addresses**, routing tables, policy routes.
- **Socket/port namespace** cho TCP, UDP và các protocol được hỗ trợ.
- **Một phần trạng thái network stack** như firewall/routing state thuộc namespace tùy triển khai.

Kubernetes sử dụng container runtime và network stack của nền tảng để các container thuộc cùng Pod có thể dùng **chung network namespace**. Mỗi container vẫn có filesystem/process/security context riêng tùy thiết lập; “chung network namespace” **không có nghĩa mọi namespace Linux đều chung**.

### 3.2. Container A gọi container B bằng localhost

Giả sử Pod có:

- Container **api** nghe TCP/8080.
- Container **log-agent** cần truy vấn một health endpoint của api.

Vì chung network namespace, log-agent có thể gửi:

~~~text
http://127.0.0.1:8080/health
~~~

Không cần Service hoặc DNS giữa hai container **trong cùng Pod**. Nhưng nếu api bind **chỉ vào 127.0.0.1**, kết nối từ **Pod khác** qua eth0/Pod IP sẽ không tới được listener đó. Nếu cần nhận traffic liên Pod, api phải bind vào **địa chỉ Pod interface hoặc 0.0.0.0/::** theo IP family và chính sách an ninh.

**Bind 0.0.0.0 không đồng nghĩa public Internet exposure.** Nó nghĩa là ứng dụng lắng nghe trên những interface IPv4 của namespace phù hợp; reachability thực tế còn phụ thuộc Service, CNI, route, NetworkPolicy, NodePort/Ingress và firewall.

### 3.3. Cổng thuộc Pod, không thuộc riêng mỗi container

Hai containers trong cùng Pod không thể thông thường cùng bind **0.0.0.0:8080/TCP** trên một network namespace:

~~~text
Pod P:
  Container api-a  -> 0.0.0.0:8080/TCP    OK
  Container api-b  -> 0.0.0.0:8080/TCP    PORT CONFLICT

Pod Q:
  Container api-c  -> 0.0.0.0:8080/TCP    OK
  (Pod Q có network namespace khác Pod P)
~~~

Đây là một lý do cần **port planning** cho app container, sidecars, metrics exporters và service mesh proxies nằm cùng Pod.

Khai báo **containerPort: 8080** trong Pod manifest là **metadata**, không tự bắt tiến trình phải lắng nghe, không tự tạo Service và không phải firewall allow rule. Ngược lại, một tiến trình vẫn có thể lắng nghe cổng không được khai báo containerPort; điều này không cho phép bỏ qua quy tắc network policy.

### 3.4. Bind-address và phạm vi kết nối

| Listener | Container cùng Pod gọi localhost? | Pod khác có thể kết nối qua Pod IP? |
| --- | --- | --- |
| 127.0.0.1:8080 | Có, nếu app sẵn sàng | Không qua Pod IP IPv4 thông thường |
| 0.0.0.0:8080 | Có | Có thể nếu CNI/NetworkPolicy/route cho phép |
| PodIP:8080 | Thường không qua 127.0.0.1 nếu chỉ bind PodIP | Có thể nếu traffic tới đúng Pod IP được phép |
| [::1]:8080 | Có qua IPv6 loopback | Không qua Pod IPv6 address |
| [::]:8080 | Tùy IPv6 listener và OS socket options | Có thể qua IPv6 Pod IP khi mạng cho phép |

Hành vi dual-stack socket IPv6 có thể phụ thuộc **IPV6_V6ONLY**, framework/runtime và cấu hình host. Không suy rằng bind [::] luôn tương đương bind cả IPv4 và IPv6.

### 3.5. Sidecar, init container và ephemeral container

Mô hình sidecar (proxy, log collector, metrics agent) thường có thể dùng **localhost** để nói chuyện với ứng dụng chính. Một service mesh sidecar có thể áp **iptables/eBPF redirect** trong network namespace của Pod để đưa traffic qua proxy, nhưng hành vi và phần traffic nào bị capture phụ thuộc triển khai/annotation/policy.

**Init containers** có thể chạy trước các containers chính trong cùng Pod context theo cấu hình; **ephemeral containers** có thể được thêm phục vụ debug theo khả năng/permissions. Chúng không được hiểu là các IP độc lập nếu thuộc cùng Pod networking context.

Một container bị compromise trong Pod có thể kết nối tới **ports chỉ bind localhost** của container khác trong Pod. Do đó:

- Không xem **localhost trong Pod** như boundary bảo mật giữa hai containers.
- Không đặt workload có trust levels rất khác nhau trong cùng Pod chỉ để tiện sidecar.
- API admin chỉ bind 127.0.0.1 vẫn có thể được gọi từ **container khác cùng Pod**.
- Kiểm soát Pod creation/debug/ephemeral containers qua RBAC và admission.
- Dùng process/container/host hardening phù hợp vì network namespace chỉ là **một** dạng isolation.

### 3.6. “Pause” / Pod sandbox và CNI lifecycle

Trong nhiều runtime trên Linux, một **Pod sandbox** (thường có infrastructure/pause container hoặc cơ chế tương đương) giữ các tài nguyên chia sẻ như network namespace. Kubelet yêu cầu runtime tạo Pod sandbox, runtime gọi CNI theo thiết kế để cấu hình mạng, sau đó mới chạy các containers nghiệp vụ.

Không nên áp dụng chi tiết **pause container** như một API contract trên mọi runtime/OS. Điểm nhất quán cần hiểu là **Kubernetes quản lý network ở cấp Pod sandbox** theo mô hình Pod thông thường, và CNI là lớp tích hợp networking để thực thi.

Khi Pod bị xóa/tái tạo, namespace và interface có thể bị dọn, IP trả về pool hoặc được cấp lại theo IPAM. **Đừng lưu Pod IP như identity bất biến** trong firewall allowlist dài hạn hay token/session của ứng dụng.

## 4. Các địa chỉ dễ nhầm trong một cluster

### 4.1. Pod IP khác Node IP, Service IP và external IP

~~~mermaid
flowchart LR
  INTERNET["External client"] --> LB["LoadBalancer / Ingress / Gateway\nexternal address"]
  LB --> SVC["Service: orders-api\nClusterIP 10.96.12.34:443"]
  SVC --> P1["Pod 1\n10.244.1.12:8080"]
  SVC --> P2["Pod 2\n10.244.2.21:8080"]
  N1["Node 1\n192.0.2.10"] --- P1
  N2["Node 2\n192.0.2.11"] --- P2
~~~

Trong sơ đồ:

- **Node IP** là địa chỉ máy chạy kubelet/runtime và thuộc network hạ tầng.
- **Pod IP** là địa chỉ endpoint của Pod trong Pod network.
- **Service ClusterIP** là một **virtual IP** cấp cho Service để client có một điểm truy cập logic ổn định.
- **External IP/LoadBalancer address** là địa chỉ/tuyến vào cluster dành cho client phù hợp với loại Service/gateway.
- **DNS name** giúp client gọi Service theo tên, không phải ghi cứng Pod IP.

Các IP minh họa thuộc **những dải giả định khác nhau**, không phản ánh default CIDR của mọi Kubernetes distribution. Một cluster có thể dùng IP ranges khác và một số Service dạng **headless (clusterIP: None)** không có ClusterIP.

### 4.2. Quy tắc địa chỉ theo từng path

| Path | Địa chỉ mà client thường dùng | Ai quyết định backend? |
| --- | --- | --- |
| Container A → B trong cùng Pod | 127.0.0.1 hoặc ::1 và port | OS socket listener cùng network namespace |
| Pod A → Pod B trực tiếp | Pod IP của B + port | CNI route/dataplane tới Pod B |
| Pod A → Kubernetes Service | Service DNS/ClusterIP + service port | Service dataplane (kube-proxy/eBPF hoặc tương đương) |
| Client bên ngoài → ứng dụng | Domain/Ingress/Gateway/LB endpoint | External LB + ingress/gateway controller/dataplane |
| Pod → cloud managed service | DNS/IP của service endpoint | Routes, egress gateway/private endpoint/service networking |
| Pod → Internet | Public hostname/IP | Node/CNI/cloud NAT/egress policy tùy thiết kế |

Không nhầm **containerPort, targetPort, service port, nodePort và external listener**. Chúng có thể có số khác nhau và vai trò khác nhau.

### 4.3. Pod IP có phải “public IP”?

Không. Pod IP thường nằm trong **private cluster address space** hoặc cloud VPC subnet, nhưng bản chất là **địa chỉ định tuyến trong thiết kế mạng**. Pod IP có thể:

- Chỉ reachable nội bộ cluster qua overlay.
- Reachable từ các VMs khác trong cùng VPC trong mô hình VPC-native, tùy route/firewall.
- Reachable qua peering/VPN nếu được cấp tuyến và policy.
- Không reachable trực tiếp từ Internet dù Pod có listener.

**Private IP không tự đảm bảo không thể bị truy cập trái phép**. Với một VPC peering hoặc exposed node/hostNetwork service, tài nguyên bên ngoài cluster có thể có đường vào; xác minh routes, security groups, CNI và application auth.

### 4.4. Pod IP trong API status

Kubernetes có thể cung cấp:

~~~yaml
# Ví dụ kết quả status, không phải manifest để apply.
status:
  podIP: 10.244.1.12
  podIPs:
    - ip: 10.244.1.12
~~~

Trong **dual-stack**, danh sách podIPs có thể chứa IPv4 và IPv6; podIP là địa chỉ chính theo API behavior. Không coi việc status chưa hiện podIP ở một Pod đang Pending/ContainerCreating là bằng chứng đã cấp IP nhưng DNS sai—cần xem **scheduler, sandbox/CNI events và node readiness**.

### 4.5. Pod IP và DNS names

Ứng dụng thường nên gọi **Service DNS** như:

~~~text
orders-api.app.svc.cluster.local
~~~

Thay vì ghi:

~~~text
10.244.1.12
~~~

Vì Pod IP có thể thay đổi khi rollouts, autoscaling, evictions hoặc rescheduling. DNS service name kết hợp Service/EndpointSlice/dataplane giúp che đi sự thay đổi backends. Tuy vậy, **DNS resolution và Service virtual IP không tự bảo đảm các backend khỏe hay được ủy quyền**—cần readiness, policy, TLS và application auth.

## 5. CNI và IPAM: Pod có địa chỉ bằng cách nào?

### 5.1. CNI là lớp tích hợp mạng, không phải tên của một giao thức duy nhất

**Container Network Interface (CNI)** là đặc tả/plugin interface được nhiều container runtimes dùng để cấu hình network cho sandbox. Trong Kubernetes trên Linux, kubelet điều phối Pod thông qua **container runtime**, và runtime/network components gọi plugin CNI phù hợp để chuẩn bị giao diện, cấp địa chỉ và routes theo thiết kế.

Kubernetes không yêu cầu mọi cluster dùng chung một network dataplane. Các nhóm triển khai có thể gồm:

- **Overlay networking** sử dụng encapsulation như VXLAN/Geneve hoặc cơ chế tương đương tùy CNI.
- **Routed/underlay networking** có những route Pod CIDR giữa nodes hoặc routers.
- **VPC-native / cloud IP assignment**, trong đó Pod có thể nhận địa chỉ từ địa chỉ/subnet cloud theo cấu hình CNI.
- **eBPF-based dataplanes** cho forwarding, Service load balancing hoặc policy enforcement khi plugin hỗ trợ.
- **Multiple interfaces/secondary networks** cho những workloads chuyên biệt.

Một CNI có thể kết hợp nhiều kỹ thuật. **Tên plugin không đủ chứng minh overlay đã mã hóa hay mọi NetworkPolicy feature được triển khai**; cần xem mode và options thực tế.

### 5.2. IPAM quản lý địa chỉ Pod

**IP Address Management (IPAM)** quyết định địa chỉ nào được cấp cho một Pod, từ phạm vi nào, tránh trùng lặp và thu hồi ra sao. Nguồn địa chỉ có thể là:

- **Node-local Pod CIDR** được cấp cho node trong một số kiến trúc.
- Pool do CNI/IPAM plugin quản lý trong cluster.
- Địa chỉ thuộc cloud VPC subnet, gắn với interface/secondary IP.
- Dải IPv6 riêng cho dual-stack hoặc IPv6-only.
- Địa chỉ thứ cấp dành cho additional network attachment.

Không mặc định mỗi node có Pod CIDR riêng trong mọi CNI. Trong một số cấu hình cloud-native, Pod IP đến từ **subnet IP pool/ENI/secondary addresses** thay vì biểu diễn một khối /24 hoặc /26 trong trường PodCIDR của node.

### 5.3. Chuỗi thiết lập mạng Pod theo mô hình khái niệm

~~~mermaid
sequenceDiagram
  participant API as API Server
  participant S as Scheduler
  participant K as Kubelet trên node
  participant R as Container runtime
  participant C as CNI/IPAM
  participant P as Pod sandbox
  API->>S: Pod cần được xếp lịch
  S-->>API: Chọn node phù hợp
  K->>API: Theo dõi Pod được gán node
  K->>R: Tạo Pod sandbox
  R->>C: Thiết lập network cho sandbox
  C->>C: Cấp IP, interface/routes,\nchính sách theo plugin
  C-->>R: Kết quả cấu hình mạng
  R-->>K: Sandbox sẵn sàng
  K->>R: Chạy containers trong Pod
  K-->>API: Cập nhật Pod status/Pod IP
~~~

**Chi tiết thứ tự và các API gọi thực** khác theo runtime, Kubernetes version và CNI; sơ đồ là mô hình tư duy. Không có nghĩa scheduler trực tiếp cấp Pod IP hoặc CNI tự quyết định mọi chính sách Kubernetes.

### 5.4. Veth pair, bridge và giao diện eth0

Trong một Linux CNI phổ biến:

1. Một **veth pair** nối network namespace của Pod với host hoặc dataplane.
2. Một đầu veth xuất hiện như **eth0** bên trong Pod, đầu còn lại có thể được nối bridge hoặc route qua host.
3. Pod được cấp IP, route tới gateway hoặc interface theo CNI.
4. Host/dataplane thực hiện forwarding giữa Pod network, Node network và mạng bên ngoài.

~~~text
Pod network namespace
  lo: 127.0.0.1
  eth0: 10.244.1.12
    |
  veth peer / CNI dataplane
    |
  Node routing, bridge, eBPF, overlay hoặc cloud network
    |
  Other Pods / Nodes / Services / External endpoints
~~~

Đây **không phải kiến trúc bắt buộc của mọi CNI**: SR-IOV, direct interface attachment, Windows/HNS networking hoặc những mode khác có thể không dùng đúng veth/bridge như sơ đồ.

### 5.5. Điều kiện để IP assignment hoạt động

Một Pod có thể Pending/ContainerCreating nếu:

- Scheduler chưa chọn được node vì CPU/memory/taint/affinity.
- Node NotReady hoặc kubelet/container runtime gặp vấn đề.
- CNI plugin/agent chưa sẵn sàng hay cấu hình không hợp lệ.
- IP pool/subnet/ENI capacity đã cạn.
- IPAM state bị lệch hoặc address conflict.
- Overlay tunnel/routing dependencies chưa sẵn sàng.
- Quyền cloud IAM cần để cấp interfaces/addresses bị thiếu.
- Pod sandbox creation thất bại vì network setup timeout.

**Không thấy Pod IP** cần được điều tra theo Pod events, node/CNI logs và IPAM metrics. Không vội sửa CoreDNS nếu sandbox chưa có mạng.

### 5.6. Vòng đời địa chỉ IP và rollouts

Pod được tạo lại sau deployment rollout, rescheduling hoặc eviction thường là **Pod object khác** và có thể nhận **Pod IP khác**. Một Pod restart container bên trong có thể giữ IP nếu sandbox còn nguyên, nhưng không nên xây hợp đồng ứng dụng dựa vào giả định IP không bao giờ thay đổi trong mọi trường hợp.

Hệ quả:

- **Không hardcode Pod IP** trong client config dài hạn.
- Dùng **Service/DNS hoặc service discovery** và retry/backoff đúng.
- Lọc security theo **Pod/namespace identity selectors** khi CNI hỗ trợ, thay vì allowlist các IP Pod biến động.
- Theo dõi **EndpointSlices và readiness** khi Pods được thay thế.
- Kiểm tra **session draining** với WebSocket/gRPC/long-running connections.
- Nếu Pod IP được ghi vào cache/service registry, cần có TTL/invalidation phù hợp.

**Replica count = 3** không có nghĩa ba Pod luôn chạy trên ba nodes hoặc ba availability zones. Scheduling topology, affinities và capacity quyết định, còn networking phải hoạt động dù các Pod có thể cùng node hoặc khác node.

## 6. Pod-to-Pod cùng node và khác node

### 6.1. Giao tiếp giữa hai Pod trên cùng node

Giả sử:

~~~text
Node-1: 192.0.2.10
  Pod frontend: 10.244.1.12
  Pod backend:  10.244.1.13

frontend → backend TCP/8080
~~~

Nếu CNI, routes và NetworkPolicy cho phép, frontend có thể kết nối **10.244.1.13:8080**. Packet có thể đi qua bridge, veth, Linux routes, virtual switch hoặc eBPF dataplane tùy plugin. Dù ở cùng node, **hai Pod vẫn khác network namespaces và khác Pod IP**.

Không nhầm với container trong cùng Pod:

| Trường hợp | Gọi localhost? | Gọi Pod IP? |
| --- | --- | --- |
| Container A → Container B cùng Pod | **Có**, nếu listener đúng | Có thể qua Pod IP của chính Pod theo listener/route |
| Pod A → Pod B cùng node | **Không**, localhost là của Pod A | **Có thể**, nếu route/policy đúng |
| Pod A → Pod B khác node | **Không** | **Có thể**, nhờ network dataplane giữa nodes |

### 6.2. Pod-to-Pod cross-node cần routing

~~~mermaid
flowchart LR
  subgraph N1["Node 1 — 192.0.2.10"]
    P1["Frontend Pod\n10.244.1.12"]
    D1["CNI dataplane 1"]
    P1 --> D1
  end
  subgraph N2["Node 2 — 192.0.2.11"]
    D2["CNI dataplane 2"]
    P2["Backend Pod\n10.244.2.21"]
    D2 --> P2
  end
  D1 <-->|"Routed underlay\nhoặc overlay tunnel"| D2
~~~

**Không phải** network traffic giữa các node bắt buộc đi qua API server hoặc kubelet. Chúng tham gia quản lý/control plane; **data plane** do CNI/network stack xử lý theo routing và policy.

Nếu node1 chỉ biết Node IP của node2 mà không có cách chuyển packet tới **10.244.2.21**, kết nối Pod-to-Pod sẽ fail. Overlay hoặc routed dataplane phải cung cấp **đường đến Pod CIDR/Pod IP** và đường trả lời phù hợp.

### 6.3. Overlay: VXLAN/Geneve và encapsulation

Trong overlay mode, lưu lượng giữa Pod network namespaces có thể được **đóng gói bên trong packet mang Node IP**:

~~~text
Inner packet:
  Source Pod IP:      10.244.1.12
  Destination Pod IP: 10.244.2.21
  Application port:   TCP/8080

Outer tunnel packet (minh họa):
  Source Node IP:      192.0.2.10
  Destination Node IP: 192.0.2.11
  Transport:           UDP tunnel port theo plugin
~~~

Overlay giúp hạ tầng dưới chỉ cần biết route **giữa Node IP**, không nhất thiết biết mọi Pod CIDR. Nhưng:

- Encapsulation tăng header overhead, có thể giảm MTU hiệu dụng.
- Một **VXLAN/Geneve tunnel không tự cung cấp mã hóa bí mật dữ liệu**; cần cơ chế encryption phù hợp như WireGuard/IPsec/mTLS theo threat model và tính năng CNI.
- Firewall/security group giữa nodes cần cho traffic tunnel control/data ports đúng sản phẩm.
- Một số IDS/IPS chỉ thấy **outer traffic**, không tự nhìn Pod IP/HTTP plaintext nếu không có khả năng giải mã/decapsulation.
- Route qua tunnel có thể che Pod IP khỏi thiết bị mạng ngoài nodes; log/telemetry cần lấy từ CNI/node nếu muốn thấy inner flows.

**Đừng mở tùy tiện tất cả UDP traffic node-to-node** vì nghĩ CNI luôn dùng một cổng cố định; xác minh CNI version/mode và danh sách port cần thiết của cluster.

### 6.4. Underlay / routed Pod network

Trong routed mode, network biết cách chuyển **Pod IP/Pod CIDR** qua nodes hoặc routers mà không nhất thiết encapsulate mọi packet. Với một số CNI cloud-native, Pod IP đến từ chính VPC subnet/secondary IP:

- Node/cloud routing đảm bảo Pod IP reachable theo topology.
- IP allocation giới hạn bởi subnet capacity, secondary addresses/ENI quotas hoặc cloud networking limits.
- Cloud SG/NACL/firewall có thể áp tại node/interface/Pod scope theo tính năng, không mặc định mọi Pod có SG riêng.
- Pod network có thể được thấy từ VPC peers hoặc on-prem nếu cloud routes/ACL cho phép.

**Routed không có nghĩa mọi Pod được công bố Internet**, và không có nghĩa NAT sẽ không xảy ra cho traffic egress. Cần xét từng destination và chain security policy.

### 6.5. DNS và NAT có thể làm đường đi khó quan sát

Một ứng dụng gọi:

~~~text
http://backend.api.svc.cluster.local:8080
~~~

Client đầu tiên hỏi DNS, có thể nhận Service IP; sau đó dataplane chọn một Pod IP backend. Với iptables/IPVS/eBPF implementation, có thể thấy **DNAT, connection tracking hoặc load balancing rules**, không phải một kết nối trực tiếp chỉ nhắm một Pod IP tĩnh.

Khi debug:

1. Tách **DNS resolution** khỏi **TCP/UDP reachability**.
2. Xem **Service/EndpointSlice/backends** đã sẵn sàng chưa.
3. Kiểm tra Pod IP, Service IP và Node IP theo đúng path.
4. Xem NetworkPolicy egress của client và ingress của backend.
5. Kiểm tra DNS/Service dataplane/cross-node routes nếu Pod IP direct test khác Service test.

### 6.6. MTU, MSS và packet fragmentation

Một tunnel overlay có thể tạo điều kiện “ping nhỏ được, gRPC/HTTPS response lớn bị treo” nếu MTU path không đúng. Khi cần, kiểm tra:

- Pod interface MTU so với node underlay MTU.
- Tunnel overhead: VXLAN/Geneve, IPsec/WireGuard nếu dùng.
- Path MTU Discovery, **ICMP Fragmentation Needed/Packet Too Big**.
- TCP MSS và retransmissions.
- QUIC/UDP packet sizes nếu ứng dụng HTTP/3 hoặc custom UDP.
- Cấu hình CNI, node NIC/offload và cloud network MTU policy.

**Chặn mọi ICMP/ICMPv6 có thể gây lỗi MTU hoặc chẩn đoán**. Không dùng ping thành công làm bằng chứng đầy đủ mọi payload size/port đều được phép.

### 6.7. Lưu lượng qua nodes không phải mặc định encrypted

Nếu CNI dùng overlay không có encryption, hai Pod có thể có kết nối IP thông suốt nhưng application data không được mã hóa chỉ vì nằm trong overlay. Những lớp bảo vệ:

- **TLS/mTLS** giữa services (nếu yêu cầu peer identity và encryption).
- CNI/host encryption khi plugin hỗ trợ.
- Cloud network encryption controls khi có, nhưng cần xác minh scope/guarantees.
- NetworkPolicy/SG/NSG/segmentation để giảm reachable peers.
- EDR/IDS/IPS/flow monitoring phù hợp điểm quan sát.

Mã hóa transport bảo vệ nội dung trước một số kiểu nghe lén, **không thay application authorization hoặc network segmentation**.

## 7. Service, EndpointSlice và CoreDNS: tại sao ứng dụng không gọi IP Pod cố định?

### 7.1. Service tạo một lớp địa chỉ ổn định

Deployment có thể thay Pods theo rolling update, node failure, scaling hoặc eviction. Một **ClusterIP Service** cung cấp tên/địa chỉ logic thay vì yêu cầu client theo dõi IP của từng Pod.

Ví dụ:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
  namespace: app
spec:
  type: ClusterIP
  selector:
    app: orders-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

Giả sử Service ClusterIP là **10.96.12.34**. Client gọi:

~~~text
http://orders-api.app.svc.cluster.local:80
~~~

Dataplane có thể chuyển tới:

~~~text
Pod backend 10.244.1.12:8080
Pod backend 10.244.2.21:8080
Pod backend 10.244.3.18:8080
~~~

Địa chỉ và tên trong ví dụ là giả định; cluster thực sẽ cấp Service IP theo cấu hình. **Service không tự tạo container listener**. Process trong Pod phải nghe đúng targetPort và Pod/network policy phải cho traffic đi qua.

### 7.2. EndpointSlice và backend readiness

Kubernetes dùng **EndpointSlice API** để biểu diễn tập endpoints và trạng thái điều kiện phục vụ Service, thay đổi theo Pod lifecycle. Những điều cần hiểu:

- **Selector của Service** xác định các Pod mục tiêu theo labels khi Service có selector.
- **EndpointSlices** chứa địa chỉ endpoints và metadata hữu ích cho dataplane/discovery.
- **Readiness** ảnh hưởng endpoint có được dùng cho traffic theo kiểu Service/controller/dataplane.
- Khi Pod biến mất, endpoint phải được cập nhật; connection cũ có thể cần timeout/drain.
- Service cũng có thể không có selector và được gắn endpoints theo cơ chế quản lý tương ứng; không mặc định mọi EndpointSlice đều bắt nguồn từ Deployment.

**Một Service tồn tại không chứng minh nó có healthy backend**. Kiểm tra danh sách endpoints, container listener, readiness và policy trước khi kết luận “Service networking hỏng”.

### 7.3. kube-proxy và các dataplane thay thế

Tùy cluster, lưu lượng tới ClusterIP có thể được xử lý bằng:

- **kube-proxy với iptables hoặc các mode hỗ trợ**.
- **IPVS** ở các hệ thống dùng cấu hình/vòng đời phù hợp.
- **eBPF-based Service load balancing** hoặc dataplane thay thế hoàn toàn hay một phần kube-proxy.
- Các cơ chế nền tảng khác cho Windows hoặc môi trường đặc thù.

Đừng yêu cầu mọi người “xem iptables nat chain” như bước duy nhất: một cluster eBPF kube-proxy replacement có thể không biểu diễn Service forwarding theo cách giống iptables cổ điển.

### 7.4. Service IP thường không nằm trên một interface vật lý

ClusterIP thường là **virtual IP trong data plane**, không phải một địa chỉ mà một Pod thật giữ trên eth0. Dataplane nhận packet tới Service IP, rồi **chọn backend endpoint** theo semantics. Điều này lý giải tại sao:

- Không luôn tìm được Service IP trong output địa chỉ interface của Pod/Node.
- **Ping tới Service ClusterIP** thường không phải health check đáng tin, vì Service protocol/implementation có thể không xử lý ICMP theo kỳ vọng.
- Test đúng nên gọi **TCP/UDP port và application protocol**, chẳng hạn HTTPS health endpoint, có authorization khi cần.

### 7.5. Headless Service không có ClusterIP

Một Service khai báo:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: database-peers
  namespace: app
spec:
  clusterIP: None
  selector:
    app: database-peer
  ports:
    - name: db
      port: 5432
~~~

Headless Service không dùng một VIP ClusterIP; DNS/service discovery có thể đưa tới **địa chỉ endpoints** theo semantics của controller, đặc biệt với StatefulSet. Nhưng **Pod IP vẫn không biến thành identity bền vững**; stable DNS name của Pod/StatefulSet và underlying endpoint có thể thay đổi theo lifecycle. Với database, consistency và membership phải do ứng dụng/protocol quản lý, không dựa riêng vào DNS headless.

### 7.6. DNS service name và namespace scope

Từ namespace app, Pod có thể dùng tên ngắn **orders-api** để kết nối Service cùng namespace. Từ namespace khác, có thể cần tên kiểu **orders-api.app.svc.cluster.local**; hậu tố domain cluster thực tế có thể không phải cluster.local.

DNS lookup trả kết quả theo **namespace/search domains, DNS policies và CoreDNS cấu hình thực tế**. Pod có thể dùng dnsPolicy/dnsConfig hoặc hostNetwork, làm khả năng phân giải thay đổi.

**DNS là một service network dependency**: default-deny egress thiếu DNS allowance có thể làm applications lỗi hostname lookup dù Pod IP direct traffic vẫn chạy. Ngược lại, DNS hoạt động không chứng minh application được network policy/TLS cho phép.

### 7.7. Không dùng Service như một security boundary

Service selector, ClusterIP hoặc internal DNS name **không phải firewall**. Một Pod có thể cố kết nối **trực tiếp Pod IP của backend** mà không qua Service name nếu route/policy cho phép. Do đó:

- Dùng **NetworkPolicy** để giới hạn traffic tới backend Pods theo nguồn/đích/port.
- Áp **TLS/mTLS, workload identity và authorization** tại service/gateway.
- Nếu cần API rate limiting hoặc WAF, đặt ở **L7 proxy/gateway thật sự đi qua**; Pod-to-Pod direct bypass có thể tránh gateway nếu không bị hạn chế.
- Không coi namespace và Service name như một ACL tự động.

### 7.8. LoadBalancer, NodePort, Ingress và Gateway

Đường vào từ bên ngoài có thể là:

~~~mermaid
flowchart LR
  C["External client"] --> LB["Cloud LB / NodePort\nTCP hoặc UDP"]
  LB --> ING["Ingress / Gateway proxy\nnếu triển khai"]
  ING --> SVC["Service / EndpointSlice"]
  SVC --> A["Pod A"]
  SVC --> B["Pod B"]
~~~

Thực tế **LoadBalancer Service có thể chuyển traffic thẳng tới Pods hoặc nodes** tùy cấu hình, không bắt buộc lúc nào cũng có Ingress/Gateway ở giữa. Hình là một ví dụ có cả proxy L7. Để bảo mật:

1. Xác định **TLS termination point** và nguồn client IP sau NAT/proxy.
2. Giới hạn **exposure** của LoadBalancer/NodePort/Ingress/Gateway.
3. Không tin X-Forwarded-For hoặc Forwarded từ client chưa xác thực.
4. NetworkPolicy phải cho traffic thực sự đến từ đúng source identity/IP theo dataplane; NAT có thể làm IP ở điểm policy khác kỳ vọng.
5. Backend giữ API auth, không dựa chỉ vào việc request được đưa qua ingress.

**containerPort không công bố Internet**; external exposure xuất hiện khi có listener, network routes và Service/Ingress/LB/firewall cho phép theo thiết kế.

## 8. Pod IP, NAT, Egress và network bên ngoài cluster

### 8.1. Pod ra Internet thường không giữ nguyên source Pod IP

Ví dụ Pod IP **10.244.1.12** gọi một external HTTPS service. Đường đi có thể là:

~~~text
Pod 10.244.1.12
   |
Node / CNI egress
   | SNAT/masquerade tùy cấu hình
Node/Cloud NAT source IP
   |
Internet destination TCP/443
~~~

Địa chỉ mà external server nhìn thấy có thể là **Node IP, NAT gateway public IP hoặc egress gateway IP**, không phải Pod IP. Trong routed/VPC-native cloud networking, Pod IP có thể vẫn được giữ trong một số private-network paths.

Để chẩn đoán egress cần phân biệt:

- **Pod source identity/IP ban đầu**.
- **IP tại điểm NetworkPolicy enforcement**.
- **IP sau SNAT/NAT**.
- **Destination IP sau DNS/service routing**.
- **IP mà external service thực sự thấy**.

**Không dựa vào public IP của NAT gateway để phân biệt từng Pod** nếu nhiều Pods cùng dùng một egress IP; cần logs có workload identity, NAT translation và timestamp.

### 8.2. NetworkPolicy kiểm soát Pod egress, không phải Cloud IAM

Nếu một Pod được phép kết nối TCP/443 tới một cloud service, nó vẫn cần **application/cloud IAM credentials** phù hợp để đọc dữ liệu. Ngược lại, một Pod sở hữu quá nhiều IAM permissions có thể gây rủi ro lớn nếu egress network policy mở rộng.

Defense in depth:

- NetworkPolicy chặn những đích không cần thiết.
- Cloud security groups, VPC routes, private endpoints và egress firewall kiểm soát bên ngoài cluster.
- IAM/workload identity xác minh principal/resource actions.
- TLS/mTLS xác minh server hoặc peer.
- API/DLP/audit logs phát hiện data movements bất thường.

### 8.3. Metadata service và workload credentials

Trên nhiều cloud platforms, VM/node có cơ chế cấp **instance metadata hoặc credentials** qua địa chỉ hoặc endpoint nội bộ của hạ tầng; cách hoạt động khác theo provider.

Nếu một Pod có thể gọi tới metadata/credential endpoint không được hạn chế, workload bị compromise có thể cố lấy quyền của node hoặc service account, tùy cơ chế bảo vệ. Kiểm soát phù hợp:

1. Dùng **workload identity** và credential scoping thay vì gán node role rộng cho mọi Pod.
2. Cấu hình **metadata access restrictions/IMDS controls** theo cloud provider.
3. Giới hạn Pod capabilities/host access và egress phù hợp.
4. Không coi NetworkPolicy đối với một IP metadata nhất định là kiểm soát duy nhất, vì **host/network path exceptions và cloud mechanisms** có thể khác.
5. Giám sát token/credential issuance và cloud IAM audit.

Không hardcode metadata IP chung cho mọi nhà cung cấp hoặc giả định tất cả CNIs đều áp chính sách egress với host/metadata traffic như nhau.

### 8.4. Cross-VPC peering hoặc on-prem: Pod IP có reachable trực tiếp không?

Giả sử Kubernetes node ở VPC-A, database on-prem ở mạng khác qua VPN/peering. Pod gọi database bằng IP private. Traffic:

~~~mermaid
flowchart LR
  P["Pod IP\n10.244.1.12"] --> CNI["CNI/Node dataplane"]
  CNI --> N["VPC routes / Egress NAT\nnếu có"]
  N --> H["VPC Peering / VPN / Transit"]
  H --> DB["On-prem database"]
~~~

Trong overlay mode, on-prem có thể **chỉ cần route tới node/NAT IP** vì source Pod đã được SNAT, hoặc cần các route Pod CIDRs nếu thiết kế giữ source. Trong VPC-native mode, Pod IP có thể thuộc VPC subnet và được định tuyến theo những điều kiện cloud network.

Điều bắt buộc xác minh:

- **Source IP tại database/firewall** là Pod IP, node IP hay NAT IP?
- Route từ Pod tới đích và **route trả lời** đúng không?
- NetworkPolicy/SG/NSG và transit firewall cho phép đúng source/destination/port không?
- CIDR Pod/Service có **overlap** với on-prem/peered networks không?
- TLS certificate/SAN/mTLS identity và database authorization đã đúng chưa?
- IPv6 có đường đi và chính sách tương đương không?

**ClusterIP Service IP không nhất thiết được routable trực tiếp từ on-prem**. Muốn expose service tới mạng khác cần giải pháp được hỗ trợ như private ingress/LB, Gateway hoặc service attachment theo kiến trúc, không cứ thêm route tới Service CIDR là xong.

### 8.5. Egress gateway, DNS filtering và chặn dữ liệu rời cluster

Một số kiến trúc đưa outbound traffic qua **egress gateway/firewall**. Điều này hữu ích để tập trung TLS policy, logging, allowlist destinations và network segmentation, nhưng:

- Traffic cần thật sự được **route/proxied qua gateway** theo CNI/service mesh design.
- Nếu Pod có direct NAT/Internet path khác, egress gateway có thể bị bypass.
- DNS filtering chỉ nhìn được queries đi qua resolver được quản lý; DoH/DoT có thể thay đổi visibility.
- Một policy dựa vào IP đích của SaaS có thể khó duy trì nếu địa chỉ thay đổi thường xuyên.
- Endpoint tới cloud private service hoặc internal metadata có thể có đường đi đặc thù.

**NetworkPolicy chuẩn thường mô tả L3/L4 peers/ports**, không tự quản lý một allowlist FQDN có DNS tracking; FQDN egress policy là khả năng mở rộng của một số CNI/gateway riêng và phải được kiểm tra.

## 9. Ngoại lệ và chế độ nâng cao: hostNetwork, dual-stack và nhiều interface

### 9.1. hostNetwork — Pod dùng mạng của node

Một Pod khai báo:

~~~yaml
spec:
  hostNetwork: true
~~~

Thường dùng **network namespace của host/node** thay vì Pod network namespace riêng. Hệ quả:

- Pod có thể thấy interface/routes của node, và Pod IP được báo có thể là Node IP.
- **Host ports** và Pod process có thể xung đột với các tiến trình cùng nghe địa chỉ/port trên node.
- Isolation network giữa Pod đó và host thấp hơn trường hợp Pod thường.
- NetworkPolicy behavior với hostNetwork thường **khác nhau theo CNI**; không giả định một NetworkPolicy chuẩn sẽ cô lập hostNetwork Pod giống Pod có interface riêng.
- DNS resolution cũng có thể cần cấu hình đặc thù như dnsPolicy phù hợp với cluster DNS.

**hostNetwork không phải một cách “sửa CNI” mặc định**. Nó mở rộng quyền tiếp cận network của Pod và thường dành cho network/system components có yêu cầu rõ, được kiểm soát bằng admission/RBAC, Pod Security Standards và node firewall.

### 9.2. HostPort và NodePort không giống Pod IP

**hostPort** là trường container port mapping từ port trên node tới Pod, phụ thuộc runtime/CNI và khả năng scheduling; dùng rộng có thể gây **xung đột port giữa Pods trên cùng node** hoặc tăng host exposure. **NodePort** là loại Service expose một cổng trên node addresses theo implementation.

Điểm khác nhau:

| Thuộc tính | hostPort | NodePort Service |
| --- | --- | --- |
| Cấp cấu hình | Pod/container | Service |
| Đơn vị exposure | Node port mapping gắn Pod | Node port tới Service backends |
| Rủi ro | Port collision, host exposure, scheduling constraints | Mở ingress trên nhiều nodes/addresses tùy config |
| Có phải địa chỉ Pod không? | Không | Không |

Không dùng hostPort/hostNetwork để thay Service/Ingress/Gateway nếu mục tiêu chỉ là expose một HTTP API chuẩn và có lựa chọn an toàn hơn.

### 9.3. Dual-stack và Pod IPs

Một cluster IPv4/IPv6 dual-stack có thể cấp cho Pod **một IPv4 và một IPv6** trên primary network. Tùy cấu hình, Service có thể có một hoặc hai IP families.

~~~yaml
# Ví dụ status của một Pod dual-stack.
status:
  podIP: 10.244.1.12
  podIPs:
    - ip: 10.244.1.12
    - ip: "fd00:10:244::12"
~~~

Đây không mâu thuẫn với **mô hình một Pod là một network endpoint**: chỉ là một endpoint có nhiều address families. Cần kiểm tra:

- CNI/IPAM và Node/Pod CIDRs IPv4/IPv6.
- Service ipFamilies/ipFamilyPolicy theo khả năng và thiết kế.
- DNS **A và AAAA** records.
- NetworkPolicy **ipBlock** và firewall IPv6 nếu dùng CIDR filtering.
- Ứng dụng bind IPv4/IPv6 và giải quyết hostname.
- External/egress routing và các đường có thể bypass chính sách một family.

Đừng mặc định mọi Kubernetes cluster hỗ trợ dual-stack chỉ vì node OS có IPv6.

### 9.4. Nhiều network interfaces (Multus/SR-IOV hoặc plugin tương đương)

Một workload chuyên biệt có thể gắn **secondary interface/network** để phục vụ storage, telecom/NFV, high-performance network hoặc traffic segmentation:

~~~text
Pod network namespace:
  lo
  eth0 -> Default Pod network IP
  net1 -> Secondary network IP
  net2 -> Another attached network (nếu hỗ trợ)
~~~

Hệ quả:

- Nhiều IP trong **cùng Pod network namespace**, phá cách hiểu quá literal “một Pod chỉ có đúng một địa chỉ”.
- Kubernetes **NetworkPolicy chuẩn có thể chỉ được CNI primary/implementation áp trên một số interfaces**; secondary networks cần cơ chế bảo vệ riêng theo plugin.
- Routing/policy routing khi có nhiều gateways và return path phải được quản trị.
- Không cho Pod tự tùy ý attach vào management/data plane network nếu không được duyệt.
- Cloud/host firewalls, NIC/SR-IOV VF permissions, device plugins và RBAC/admission góp phần định nghĩa boundary.

**Không mặc định secondary interface sẽ được bảo vệ bởi policy bạn áp trên eth0.** Phải đo/kiểm thử đúng interface và CNI triển khai.

### 9.5. Windows containers và CNI/platform differences

Kubernetes có thể chạy Windows nodes/Pods theo phiên bản và môi trường hỗ trợ. Các cơ chế như Windows HNS/overlay/network policy semantics có thể khác Linux veth/iptables. Các ví dụ Linux dùng iproute2, network namespaces hoặc iptables trong bài **không áp nguyên xi cho Windows Pods**.

Khi môi trường Windows:

- Kiểm tra CNI và Windows network dataplane hỗ trợ chế độ nào.
- Dùng công cụ kiểm tra IP/routes/network endpoints phù hợp Windows.
- Xác minh NetworkPolicy feature coverage, hostNetwork-like behavior và DNS.
- Đừng yêu cầu chạy lệnh Linux trong container Windows rồi kết luận Pod network hỏng.

### 9.6. Pod IP và multi-cluster networking

Hai clusters độc lập có thể cùng dùng Pod CIDR **10.244.0.0/16**, vì tính duy nhất của Pod IP thường là **trong phạm vi cluster/network domain**, không mặc nhiên toàn bộ doanh nghiệp. Khi nối hai clusters bằng peering, VPN hoặc service mesh đa cluster, CIDR overlap có thể gây:

- Ambiguous routes và IP collisions.
- DNS service name conflict.
- Khó thiết lập direct Pod-to-Pod connectivity.
- NAT/service gateway translation làm quy nguồn khó hơn.
- Cần thiết kế global service identity và discovery riêng.

Chọn **multi-cluster Service/Gateway, service mesh federation, IPAM không overlap, translation hoặc endpoint exposure** theo công nghệ được hỗ trợ. **Đừng suy rằng hai Pod ở hai clusters khác nhau tự giao tiếp được chỉ vì cả hai đều có Pod IP.**

## 10. NetworkPolicy: từ Pod có IP tới Pod có giới hạn kết nối

### 10.1. Vì sao Pod IP không đủ bảo vệ?

Trong một cluster không có chính sách cô lập network ở cấp Pod, các Pods **thường có thể cố giao tiếp với nhau** trên mạng cluster nếu CNI/route và những controls khác không ngăn cản. Đây là khả năng kết nối hữu ích cho microservices, nhưng cũng có nghĩa:

- Một Pod ứng dụng bị compromise có thể thử kết nối các **Pod/backend khác**.
- Hai namespaces không mặc định cô lập network chỉ vì chúng có tên khác nhau.
- Địa chỉ Pod/Service có thể được phát hiện qua DNS hoặc Kubernetes API theo quyền.
- Một service quản trị chỉ được “giấu” bằng tên Service internal chưa có nghĩa không thể truy cập qua Pod IP.
- Chỉ mở ingress HTTPS ở edge không tự cấm **east–west direct Pod access** bên trong cluster.

**Kubernetes NetworkPolicy** là resource khai báo intent **L3/L4 network isolation** cho các Pods được chọn trong namespace. Việc thực thi phải do **CNI/network policy implementation** hỗ trợ. Có NetworkPolicy objects nhưng CNI không thực thi thì không thể coi hệ thống đã được cô lập.

### 10.2. NetworkPolicy tác động đến những chiều nào?

Mỗi policy mô tả:

- **podSelector:** chọn **các Pods đích của policy trong namespace của chính NetworkPolicy**.
- **policyTypes:** các hướng Ingress, Egress mà policy tác động.
- **ingress:** những nguồn/port được cho phép **đi vào các Pod được chọn**.
- **egress:** những đích/port được cho phép **đi ra từ các Pod được chọn**.

Ví dụ một Pod API có thể bị **ingress-isolated** nhưng chưa bị **egress-isolated**. Khi đó ingress tới API phải khớp một allow rule; egress vẫn theo trạng thái/policies khác, không tự bị chặn chỉ vì có ingress policy.

### 10.3. Policy là allowlist cộng gộp, không có explicit deny tùy tiện

Trong Kubernetes **NetworkPolicy chuẩn**:

1. Nếu Pod không được policy nào chọn để cô lập **ingress**, ingress thường **không bị NetworkPolicy chuẩn hạn chế**.
2. Nếu Pod được policy có loại **Ingress** chọn, ingress chỉ được phép theo **hợp các ingress rules** của tất cả các policy chọn Pod đó.
3. Tương tự cho **Egress** khi Pod được ít nhất một policy cô lập egress chọn.
4. Một Pod-to-Pod flow cần **egress của Pod nguồn** và **ingress của Pod đích** đều cho phép nếu những hướng đó đang chịu isolation, ngoài các controls khác.
5. NetworkPolicy chuẩn thường chỉ có **allow rules**; thêm một policy allow rộng có thể mở lại traffic mà người vận hành tưởng đã “deny” bằng policy khác.

~~~mermaid
flowchart LR
  F["Frontend Pod\nnamespace web"] --> E["Source egress policy\nallow TCP/8080"]
  E --> C["CNI routing/dataplane"]
  C --> I["Destination ingress policy\nallow frontend Pods"]
  I --> B["Backend Pod\nnamespace app"]
  X["Unknown Pod"] -. "Không khớp ingress allow" .-> I
~~~

Sơ đồ minh họa chính sách theo **đúng Pod endpoints**. Không phải Service DNS, namespace name hay Pod IP tự cấp một quyền network. Nếu CNI implementation có policy extensions, semantics mở rộng của nó cần được xem riêng.

### 10.4. Namespace không phải tường lửa mặc định

Namespace tổ chức Kubernetes objects, quota, RBAC và namespacing của nhiều resources. Nhưng:

~~~text
namespace web:
  Pod frontend 10.244.1.10

namespace app:
  Pod backend  10.244.2.10

Without enforced NetworkPolicy or other controls:
  web/frontend -> app/backend may be reachable by Pod IP.
~~~

**Tạo namespace Prod và Dev không tự chặn TCP giữa chúng.** Muốn segmentation theo namespace phải triển khai NetworkPolicy hoặc CNI/security controls có cơ chế phù hợp, rồi thử từ đúng namespaces.

### 10.5. Default-deny ingress

Policy dưới đây **chọn tất cả Pods trong namespace app** và tạo ingress isolation, không khai báo nguồn cho phép:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: app
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

**Điều kiện quan trọng:** CNI đang dùng phải hỗ trợ/enforce NetworkPolicy. Sau khi áp và có hiệu lực, các Pods trong app sẽ **không nhận ingress được NetworkPolicy cho phép** trừ khi có **policy khác bổ sung allow ingress**. Traffic từ Pod này sang Pod khác cùng namespace cũng không tự được allow chỉ vì cùng namespace.

Không cần thêm một ingress rule rỗng để “deny”; field ingress bỏ trống tạo allowlist trống cho hướng Ingress theo semantics policy này.

### 10.6. Default-deny egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: app
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Policy này cô lập egress cho tất cả Pods trong namespace app, trừ những outbound flows được các policies khác bổ sung allow. Nó có thể làm ứng dụng **mất DNS, không gọi được API, không tải được secret/config từ endpoint mạng hoặc không reach observability collectors**.

**Khi rollout production, áp policy sau khi đã chuẩn bị allowlist cần thiết và recovery path.** Tránh “đập” default-deny vào namespace hệ thống không đánh giá trước, bởi DNS/CNI/controller có thể ngừng hoạt động nếu phụ thuộc đường bị chặn.

### 10.7. Default-deny ingress + egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: app
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Các policies mặc định có thể được áp qua platform/security GitOps cho **application namespaces** khi CNI đã xác minh. Nhưng **allowlist tương ứng phải được thiết kế cùng lúc**; nếu không Pod readiness/service discovery và traffic sản xuất có thể bị chặn.

### 10.8. Allow ingress từ frontend được chọn

Giả sử:

- Namespace **web** có label **access-tier: frontend**.
- Pod frontend có label **app: storefront**.
- Namespace **app** chứa backend Pods có label **app: orders-api**.
- Backend lắng nghe TCP/8080.

Policy:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-orders
  namespace: app
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              access-tier: frontend
          podSelector:
            matchLabels:
              app: storefront
      ports:
        - protocol: TCP
          port: 8080
~~~

Một phần tử trong danh sách **from** có cả namespaceSelector và podSelector nghĩa là **cùng lúc thỏa cả hai**: Pods có app=storefront **trong những namespaces có access-tier=frontend**. Nó **không** có nghĩa namespaceSelector HOẶC podSelector.

**Không cho một nhóm không đáng tin quyền tùy ý đặt label namespace hoặc Pod có vai trò privileged selector.** RBAC/admission policy và ownership labels là một phần của bảo vệ NetworkPolicy.

### 10.9. Sai lầm cấu trúc YAML làm OR thay vì AND

Xem hai đoạn:

~~~yaml
# ĐÚNG mục tiêu: Pod app=storefront TRONG namespace có access-tier=frontend
from:
  - namespaceSelector:
      matchLabels:
        access-tier: frontend
    podSelector:
      matchLabels:
        app: storefront
~~~

~~~yaml
# KHÁC: Hai phần tử trong from => OR.
# 1) BẤT KỲ Pod nào trong namespace frontend, HOẶC
# 2) Pod app=storefront trong CÙNG namespace của NetworkPolicy.
from:
  - namespaceSelector:
      matchLabels:
        access-tier: frontend
  - podSelector:
      matchLabels:
        app: storefront
~~~

Chỉ thay **độ thụt dòng/list item** đã biến policy thành **rộng hơn dự kiến**. Đây là lý do cần review YAML cùng negative tests, không chỉ kiểm tra manifest có apply thành công.

### 10.10. Allow egress từ frontend sang backend

Giả sử NetworkPolicy **egress** nằm trong namespace web:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-egress-to-orders
  namespace: web
spec:
  podSelector:
    matchLabels:
      app: storefront
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: app
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 8080
~~~

Trong nhiều Kubernetes versions hiện đại, label **kubernetes.io/metadata.name** của namespace được quản lý tự động. Trước khi dùng nó làm selector, **xác minh label thực có và được CNI hỗ trợ** ở cluster. Có thể thay bằng **label namespace được quản trị có kiểm soát** nếu phù hợp.

Policy này cho phép **egress từ storefront** tới Pods orders-api được chọn trong namespace app trên TCP/8080. Nếu backend chịu ingress isolation, **policy ingress bên backend cũng phải cho phép** source tương ứng. Nếu frontend dùng **Service port 80 → targetPort 8080**, NetworkPolicy nên được thiết kế/test theo **đường packet thực sau Service translation**; xử lý NAT và thứ tự evaluation có thể khác theo CNI.

### 10.11. Allow DNS có kiểm soát

Khi namespace bị egress default-deny, Pods vẫn cần DNS. Ví dụ cho phép DNS tới CoreDNS Pods có labels phù hợp:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-cluster-dns-egress
  namespace: app
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

**Cảnh báo tính di động:** CoreDNS labels, namespace, NodeLocal DNSCache, DNS proxy/redirect và điểm CNI thực thi policy **không giống nhau ở mọi cluster**. Xác minh DNS Pods/endpoints, node-local DNS addresses và behavior thực tế. Một policy đúng YAML nhưng chọn sai DNS endpoints có thể khiến mọi app timeout khi tra tên.

Chỉ mở **DNS TCP/UDP 53** là ví dụ phổ biến, không đủ nếu ứng dụng dùng DNS over TLS/HTTPS có chủ ý; trường hợp đó cần security architecture riêng. Không mở egress TCP/443 ra mọi Internet chỉ để “chữa lỗi DNS” khi chưa biết đích cần thiết.

### 10.12. ipBlock CIDR và điểm giới hạn

NetworkPolicy có thể dùng **ipBlock** cho ranges, gồm **except** theo cấu trúc:

~~~yaml
# Minh họa một phần Egress rule, không phải policy hoàn chỉnh.
egress:
  - to:
      - ipBlock:
          cidr: 198.51.100.0/24
          except:
            - 198.51.100.128/25
    ports:
      - protocol: TCP
        port: 443
~~~

CIDR trên thuộc dải tài liệu TEST-NET. Với traffic thực, phải chỉ rõ egress destinations được phép. ipBlock thường phù hợp khi chọn **external/static IP ranges**, nhưng không nên dựa vào nó để biểu diễn **Pod identity động**; dùng podSelector/namespaceSelector khi phù hợp.

Đặc biệt, **NAT trước hay sau NetworkPolicy enforcement** không được Kubernetes API chuẩn bảo đảm tuyệt đối theo cùng cách ở mọi CNI/cloud service. Với NodePort/LoadBalancer/Service và egress SNAT, địa chỉ gói tại điểm enforce có thể khác IP bạn nghĩ. **Phải thử traffic thật với CNI đang dùng** trước khi ký duyệt ipBlock allow/deny trên một path.

### 10.13. NetworkPolicy không phải một firewall L7

NetworkPolicy chuẩn thường diễn đạt **Pod/namespace/IP peer và protocol/port**, không tự hiểu:

- HTTP path, JWT claims, URL host, gRPC method, SQL query, GraphQL operation.
- User identity, OAuth scopes hoặc service business permissions.
- FQDN wildcard egress có DNS tracking như một API chuẩn.
- TLS certificate validation hoặc mTLS identity.
- Ràng buộc default-deny áp lên **host/node network traffic** của mọi CNI giống nhau.

Một số CNI có **extended network policies (L7, FQDN, host, global/cluster policies)**; đó là features riêng, cần học theo docs của plugin và version thực tế. Không gán những khả năng extension này cho mọi NetworkPolicy objects.

### 10.14. Bảng trạng thái khi nhiều policies chọn cùng Pod

| Policy chọn Pod backend | Ingress state | Ý nghĩa |
| --- | --- | --- |
| Không có NetworkPolicy Ingress chọn Pod | Không ingress-isolated theo NetworkPolicy chuẩn | Traffic có thể tới Pod nếu các lớp khác cho phép |
| Một default-deny ingress | Ingress-isolated, allowlist rỗng | Không có ingress được policy chuẩn cho phép |
| Default-deny + allow storefront TCP/8080 | Ingress-isolated, cho storefront 8080 | Cơ chế union; deny cũ không “đè” allow |
| Thêm allow all TCP/8080 từ mọi source | Ingress-isolated nhưng bị mở rộng | Một allow rule rộng có thể phủ mất mục tiêu least privilege |
| Ingress allow đúng, source egress default-deny chưa allow | Đường đi vẫn bị chặn | Cần xem **cả hai hướng** |

**Không có “policy cuối cùng thắng” theo thứ tự apply YAML** trong mô hình NetworkPolicy additive chuẩn. Chính sách allow được hợp lại; một policy rộng có thể làm cả namespace không còn cô lập như dự kiến.

## 11. Những giới hạn bảo mật phải hiểu ngoài NetworkPolicy

### 11.1. Loopback và containers cùng Pod

NetworkPolicy chọn **Pod làm đơn vị**, không cô lập HTTP calls giữa hai containers **cùng dùng localhost/network namespace**. Nếu sidecar log-collector có khả năng gọi một admin API chỉ bind 127.0.0.1 của main container, NetworkPolicy không tạo một ACL riêng giữa hai containers đó.

Kiểm soát:

- Chỉ đặt containers có **trust relationship được phép** vào cùng Pod.
- Dùng application authentication/authorization ngay cả với những API localhost nhạy cảm nếu cần.
- Giới hạn Linux capabilities, runAsNonRoot, seccomp, filesystem permissions và container runtime privileges.
- Không cho người không đáng tin quyền tạo ephemeral debug containers trong Pod nhạy cảm.
- Audit sidecar injection/upgrade và thành phần có quyền đọc Pod traffic.

### 11.2. hostNetwork và node-level traffic

Traffic giữa một Pod và **node itself**, cũng như Pods dùng **hostNetwork**, có những trường hợp không được Kubernetes NetworkPolicy chuẩn kiểm soát giống Pod-to-Pod. CNI có thể hỗ trợ **host policies** hoặc node firewall rules riêng; phải kiểm tra cụ thể.

Đặc biệt:

- Một privileged/hostNetwork Pod có thể tiếp cận dịch vụ host trên loopback/interface node.
- Kubelet/API server/control-plane services có đường mạng đặc thù cần bảo vệ bằng RBAC, node firewall, admission và cloud SG.
- Pod Security Admission/Standards có thể giúp hạn chế hostNetwork/privileged capabilities theo profile, nhưng cần xác minh namespace enforcement và exceptions.
- Không xây security boundary duy nhất dựa trên một NetworkPolicy trong namespace khi network node/host plane vẫn mở.

### 11.3. Pod labels không phải secret identity

NetworkPolicy chọn Pods bằng **labels**. Labels là metadata tổ chức; chúng **không có chữ ký mật mã** chứng minh workload được tin cậy. Nếu một principal có quyền sửa labels hoặc tạo Pods với labels hợp lệ, nó có thể làm một workload **khớp selector được cấp quyền**.

Vì vậy:

- Hạn chế quyền **create/patch Pod/Deployment/Namespace labels** cho nhóm không đáng tin.
- Dùng admission policies để kiểm soát **privileged labels/namespace tenancy**.
- Kết hợp NetworkPolicy với **mTLS workload identity và API permissions**.
- Theo dõi thay đổi labels và selectors cùng với network policy drift.

**Dựa vào source Pod label chỉ là một phần của network segmentation**, không thay workload authentication ở L7.

### 11.4. Node firewall, VPC routes và cross-cluster paths

Mặc dù NetworkPolicy chặn một Pod→Pod flow ở lớp CNI, Pod khác có thể giao tiếp qua:

- NodePort/LoadBalancer/Ingress exposed ngoài cluster.
- HostNetwork agent/service hoặc host process.
- Private cloud VPC peering/VPN tới Pod IP hoặc Node IP.
- Một external proxy/gateway route về backend khác.
- Secondary interface không nằm trong policy scope.

Các đường này cần được **inventory, route analysis, SG/NSG, firewall và gateway policy** chặn khi trái quyền. NetworkPolicy không tự cô lập toàn bộ network hạ tầng.

### 11.5. NetworkPolicy với DNS/FQDN và data exfiltration

Nếu Pod egress chỉ bị chặn TCP/5432 tới database ngoài cluster nhưng vẫn được phép kết nối **mọi TCP/443 ra Internet**, kẻ có quyền trong Pod có thể cố chuyển dữ liệu qua HTTPS tới endpoint khác (nếu các lớp còn lại cho phép).

Phòng vệ:

- Giới hạn egress theo **đích/dịch vụ/port** được duyệt.
- Dùng gateway/firewall/FQDN policy extension khi phù hợp, nhưng đánh giá DNS TTL, IP rotation, encrypted DNS và proxy bypass.
- Dùng IAM, DLP, application-level monitoring để kiểm soát dữ liệu và quyền.
- Không biến default-deny thành allow-all TCP/443 vì một dependency khó truy tìm.
- Theo dõi **DNS queries, egress flows, workload identity và service request logs** để điều tra.

### 11.6. TLS và NetworkPolicy phục vụ những mục tiêu khác nhau

| Kiểm soát | Mục tiêu bảo vệ | Không bảo đảm |
| --- | --- | --- |
| **NetworkPolicy** | Hạn chế Pod peers/ports tại CNI-supported enforcement points | Mã hóa, user identity, L7 authorization |
| **TLS/mTLS** | Mã hóa và xác thực TLS peer theo cert/policy | Pod chỉ nói chuyện với danh sách IP/port được duyệt |
| **Service mesh authorization** | Workload identity/L7 hoặc policy riêng theo sản phẩm | Tất cả traffic nếu có mesh bypass |
| **Kubernetes RBAC** | Quyền gọi Kubernetes API | Application TCP network traffic mặc định |
| **Pod Security / admission** | Giảm quyền container/host/network capability | Network reachability giữa Pods nếu không có policy |
| **Cloud firewall/SG** | Kiểm soát network path ở VPC/node/interface | User business authorization |
| **WAF/API gateway** | HTTP request policy, throttling, validation | Direct Pod IP bypass ngoài gateway nếu không bị chặn |

Các lớp bổ trợ nhau. **Mỗi Pod một IP** cung cấp địa chỉ mạng, không tự tạo cơ chế xác minh danh tính hoặc least-privilege hoàn chỉnh.

## 12. Bài thực hành: hai container chung IP, hai Pod khác IP

### 12.1. Mục đích và điều kiện an toàn

Mục tiêu kiểm chứng bốn điều:

1. Hai containers cùng Pod dùng chung một **Pod IP và localhost**.
2. Hai Pods khác nhau có **network namespaces/Pod IP khác nhau**, kể cả khi dùng chung node.
3. **Service DNS/ClusterIP** trỏ tới Pod backend mà không yêu cầu client hardcode Pod IP.
4. **NetworkPolicy ingress** có thể chặn một Pod nguồn nhưng cho Pod nguồn khác vào cùng đích/port, trong khi localhost bên trong Pod không bị tách bởi policy đó.

Điều kiện:

- Một **Kubernetes lab/sandbox được cấp quyền**, namespace có thể tạo/xóa theo quy trình.
- Kubernetes API credentials chỉ có quyền cần thiết trong namespace lab.
- **CNI hỗ trợ và thực thi Kubernetes NetworkPolicy**, nếu muốn kiểm chứng bước deny.
- Các images container được tổ chức phê duyệt và sẵn có; ví dụ dùng public images để minh họa, production nên pin digest/scanning theo chính sách.
- Không triển khai lên namespace kube-system hoặc production; không bật default-deny production để làm bài tập.

### 12.2. Manifest tạo namespace, Pod hai container, Service và test clients

Các resources sau chỉ phục vụ lab. Không chạy nếu chưa kiểm tra image sources, admission policies và namespace được phép.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: podnet-lab
  labels:
    training: pod-network
---
apiVersion: v1
kind: Pod
metadata:
  name: shared-ip-demo
  namespace: podnet-lab
  labels:
    app: demo
spec:
  containers:
    - name: app
      image: python:3.12-alpine
      command:
        - python
        - -u
        - -m
        - http.server
        - "8080"
        - --bind
        - 0.0.0.0
      ports:
        - containerPort: 8080
          name: http
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
    - name: probe
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
---
apiVersion: v1
kind: Service
metadata:
  name: shared-ip-demo
  namespace: podnet-lab
spec:
  type: ClusterIP
  selector:
    app: demo
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
---
apiVersion: v1
kind: Pod
metadata:
  name: external-client
  namespace: podnet-lab
  labels:
    role: client
spec:
  containers:
    - name: test
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
---
apiVersion: v1
kind: Pod
metadata:
  name: untrusted-client
  namespace: podnet-lab
  labels:
    role: untrusted
spec:
  containers:
    - name: test
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
~~~

**Không phải manifest production:** chưa khai báo resource requests/limits, readiness/startup probes, image digest, namespace quota, restricted image registry, centralized logging hoặc cleanup orchestration. Một vài policies admission có thể chặn image/manifest; hãy tuân theo cluster lab, không tắt admission để chạy ví dụ.

### 12.3. Xem địa chỉ và namespaces được cấp

Sau khi người học lưu manifest trong **môi trường lab** và triển khai theo quyền được cấp, kiểm tra:

~~~bash
kubectl get pods -n podnet-lab -o wide
kubectl get pod shared-ip-demo -n podnet-lab -o yaml
kubectl get svc shared-ip-demo -n podnet-lab -o wide
kubectl get endpointslices -n podnet-lab \
  -l kubernetes.io/service-name=shared-ip-demo
~~~

Kỳ vọng:

- **shared-ip-demo** là **một Pod**, dù chứa hai containers app và probe.
- Pod có **một primary Pod IP** trong cluster IPv4-only, hoặc danh sách IPs theo family phù hợp.
- **external-client** và **untrusted-client** là hai Pods độc lập, thường có IPs riêng.
- Service **shared-ip-demo** có **ClusterIP** khác Pod IP; EndpointSlice trỏ tới backend Pod phù hợp.

Không nhất thiết hai Pods nằm trên hai nodes. Nếu muốn kiểm tra cross-node path, cần **scheduling permissions và topology** được phê duyệt riêng; không tự thêm node affinity/taints hoặc drain nodes trong production.

### 12.4. Test localhost trong cùng Pod

Từ container probe gọi server app qua localhost:

~~~bash
kubectl exec -n podnet-lab shared-ip-demo -c probe -- \
  wget -qO- http://127.0.0.1:8080/
~~~

Kỳ vọng: nhận HTTP response từ **python.http.server** ở container app. Việc client nằm ở **container probe khác** không cần Service hoặc traffic đi qua mạng bên ngoài Pod.

Nếu lệnh fail:

- Kiểm tra Pod Running và container app Ready/running.
- Xem logs của app: có bind 0.0.0.0:8080 thành công không?
- Kiểm tra image/test tooling có hỗ trợ wget.
- Nếu dùng read-only/strict admission policy khác, kiểm tra container exit.

NetworkPolicy **không nên được dùng như biện pháp phân tách localhost giữa containers trong cùng Pod**.

### 12.5. Test từ Pod khác qua Service DNS

~~~bash
kubectl exec -n podnet-lab external-client -- \
  wget -qO- http://shared-ip-demo:80/
~~~

Kỳ vọng: nếu chưa có ingress/egress isolation hoặc policy tương ứng, request thành công, DNS phân giải Service và data plane chuyển vào backend Pod.

Một thử nghiệm khác có thể gọi **Pod IP trực tiếp** nếu biết IP từ kết quả kubectl và lab cho phép. Nếu Pod IP direct thành công nhưng Service DNS thất bại, hãy phân loại DNS/Service/EndpointSlice/NAT. Nếu Service DNS trả IP đúng mà TCP timeout, kiểm tra network path/listener/NetworkPolicy thay vì tự kết luận DNS hỏng.

### 12.6. Áp NetworkPolicy để chỉ external-client được vào demo

**Chỉ áp trong namespace podnet-lab** sau baseline test:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: limit-demo-ingress
  namespace: podnet-lab
spec:
  podSelector:
    matchLabels:
      app: demo
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              role: client
      ports:
        - protocol: TCP
          port: 8080
~~~

Policy chọn **shared-ip-demo** (app=demo) và chỉ allow ingress từ Pod có **role=client** trong **cùng namespace podnet-lab** tới TCP/8080. Vì external-client có role=client còn untrusted-client có role=untrusted, kỳ vọng:

| Nguồn | Đích | Kết quả nếu CNI policy có hiệu lực |
| --- | --- | --- |
| Container probe cùng shared-ip-demo | 127.0.0.1:8080 | **Allow**, vì cùng Pod network namespace |
| external-client | shared-ip-demo Pod TCP/8080 | **Allow**, nếu egress của client không bị chặn |
| external-client | shared-ip-demo Service TCP/80 | **Allow**, sau Service translation theo CNI |
| untrusted-client | shared-ip-demo Pod TCP/8080 | **Deny** theo ingress isolation |
| untrusted-client | shared-ip-demo Service TCP/80 | **Deny** theo ingress isolation khi traffic tới backend |

Để kiểm chứng trường hợp deny, chạy request từ untrusted-client:

~~~bash
kubectl exec -n podnet-lab untrusted-client -- \
  wget -T 3 -qO- http://shared-ip-demo:80/
~~~

**Hình thức lỗi** có thể là timeout, connection refused, một phản hồi proxy hoặc kết quả khác tùy CNI/proxy; không đòi mọi network deny phải xuất hiện dưới một HTTP status cụ thể. Nếu untrusted-client vẫn truy cập được, điều tra **CNI policy enforcement, policy selector, labels, dataplane/NAT và các policy allow khác**, không vội kết luận YAML sai.

### 12.7. Test default-deny egress phải giữ DNS

Một bước nâng cao trong sandbox là bổ sung **egress default-deny** vào Pods client, rồi thêm allow egress tới DNS và demo backend theo mục 10. Khi egress default-deny được bật nhưng DNS chưa được phép, client có thể **không phân giải được tên Service**. Nếu TCP/8080 Pod IP direct còn được phép bởi một policy, sự khác biệt giúp phân biệt DNS với data path.

Lưu ý thực tế:

1. DNS endpoint có thể là **CoreDNS Service IP** hoặc **NodeLocal DNSCache**.
2. CNI có thể đánh giá policy trước/sau Service DNAT theo implementation.
3. Một Pod chạy với **dnsPolicy đặc thù** có thể không dùng cluster DNS.
4. Không mở egress toàn Internet để khôi phục một phép thử DNS nếu chưa biết đích đúng.

### 12.8. Dọn lab có kiểm soát

Sau khi hoàn thành, người học có thể xóa **chỉ những resources đã tự tạo trong namespace podnet-lab**, theo quyền và chính sách lab. Trước khi xóa namespace, xác minh đó không phải namespace chia sẻ với lớp học hoặc hệ thống khác.

**Không thực thi xóa namespace/resource trên production hoặc cluster chung mà bạn không sở hữu.** Kết quả của bài học là bản ghi các phép thử, không yêu cầu phá hủy tài nguyên của người khác.

### 12.9. Ma trận kiểm thử đầy đủ

| ID | Kiểm thử | Kỳ vọng | Loại bằng chứng |
| --- | --- | --- | --- |
| P01 | Hai containers trong cùng Pod | Cùng primary Pod IP | Pod status, network namespace/localhost |
| P02 | Probe gọi app bằng localhost | HTTP 200 hoặc response phù hợp | Container request/log |
| P03 | Hai Pods khác nhau cùng node | IP khác nhau | kubectl get pods -o wide |
| P04 | Hai Pods khác node (nếu lab cho phép) | Pod IPs khác, routing hoạt động | Node mapping, CNI path |
| P05 | Pod gọi Service DNS | DNS giải tên, request vào backend | CoreDNS/EndpointSlice/request |
| P06 | Pod gọi backend Pod IP trực tiếp | Kết quả phù hợp policy | TCP/HTTP connectivity |
| P07 | Untrusted Pod vào backend sau ingress policy | Deny | NetworkPolicy/logs và negative test |
| P08 | Trusted Pod vào backend sau ingress policy | Allow | Positive TCP/HTTP test |
| P09 | Containers trong cùng Pod sau policy | Localhost không bị tách bởi NetworkPolicy | Localhost test |
| P10 | App chỉ bind 127.0.0.1 | Pod khác không kết nối qua Pod IP | Listener binding evidence |
| P11 | App bind 0.0.0.0 | Có thể kết nối qua Pod IP nếu policy cho phép | Listener/route/flow |
| P12 | Egress default-deny thiếu DNS | Tên Service có thể không phân giải | DNS query timeout/log |
| P13 | Egress DNS được cho phép đúng | DNS phục hồi | Resolver logs, successful lookup |
| P14 | Backend Pod recreated | Pod IP có thể thay; Service vẫn dùng tên cũ | EndpointSlice, client behavior |
| P15 | Pod network IP pool cạn (mô phỏng) | Sandbox CNI setup fail | Pod events/CNI/IPAM metrics |
| P16 | Overlay MTU mismatch (dữ liệu giả lập) | Small packets OK, large traffic lỗi | TCP retransmission/PMTU |
| P17 | CNI không enforce policy | Deny test thất bại dù YAML tồn tại | CNI feature verification |
| P18 | HostNetwork Pod (chỉ mô phỏng) | Dùng host network, behavior khác | Config/node interface identity |
| P19 | Dual-stack Pod | Hai Pod IP families nếu cluster hỗ trợ | podIPs/DNS A/AAAA |
| P20 | External path qua NAT | Peer thấy egress IP khác Pod IP | NAT/cloud flow logs |
| P21 | Service IP ping thất bại nhưng HTTP OK | Không coi ICMP là Service health check | HTTP request/Service endpoints |
| P22 | Selector YAML AND/OR khác nhau | Allowed peers thay đổi đúng thiết kế | YAML review + negative tests |
| P23 | Secondary network interface | Policy coverage phải được kiểm chứng riêng | Interface/CNI-specific evidence |
| P24 | Pod IP cross-cluster overlap | Không tự tạo connectivity hai clusters | IPAM/routing/service gateway review |

**P15–P24** chủ yếu là bài phân tích mô phỏng hoặc yêu cầu sandbox chuyên dụng; không cố làm cạn IP pool, phá CNI, chỉnh MTU hay bật hostNetwork trên cluster đang phục vụ người dùng.

## 13. Threat modeling của Pod network

### 13.1. Bảo vệ những tài sản nào?

Trong một cluster Kubernetes chạy workload có dữ liệu hoặc quyền nhạy cảm, tài sản gồm:

- **Pod/workload identity**: ServiceAccount, mTLS certificate, projected tokens.
- **Application data**: HTTP/gRPC payloads, database traffic, service secrets.
- **Kubernetes control plane**: API server, admission/RBAC, controllers, etcd và credential paths.
- **Node networking**: kubelet, host network services, CNI agents, host firewall, routes.
- **Networking control state**: NetworkPolicy, Service/EndpointSlice, ingress/gateway routes, IPAM pools và CNI configuration.
- **Cloud infrastructure**: VPC subnets, ENIs, security groups, NAT/egress gateway, peering/VPN.
- **Observability**: CNI flow logs, DNS, network policy decisions, app audit và cloud audit.

Pod IP là một thông tin định tuyến có thể thay đổi; không coi **Pod IP** là secret credential hoặc identity có quyền cao. Bảo vệ mạng cần chú ý **ai điều khiển route/selector/identity**, chứ không chỉ việc một địa chỉ được cấp.

### 13.2. Ma trận rủi ro

| ID | Kịch bản | Điều kiện phát sinh | Tác động tiềm năng | Kiểm soát |
| --- | --- | --- | --- | --- |
| KPN-01 | Pod A gọi Pod B ngoài ý định | Không có NetworkPolicy enforced hoặc allow rộng | Lateral movement khi ứng dụng yếu | Default-deny + allowlist + auth |
| KPN-02 | Dev Pod gọi Production Pod | Namespace được coi nhầm là tường lửa | Phá cách ly môi trường | Namespace selectors, trust tiers, separate clusters nếu cần |
| KPN-03 | Container trong cùng Pod gọi local admin port | Chia sẻ localhost/network namespace | Vượt ranh giới container giả định | Tách Pods theo trust level, app auth, runtime hardening |
| KPN-04 | CNI không thực thi policy | CNI thiếu support/agent lỗi/config thiếu | Deny manifest không có tác dụng | Kiểm tra CNI, negative connectivity tests |
| KPN-05 | Namespace/Pod labels bị giả | Principal có quyền patch/create labels | Workload trái quyền khớp allow selector | RBAC/admission + workload identity |
| KPN-06 | hostNetwork privileged workload | Pod dùng host network/capabilities cao | Tiếp cận host ports/services | Pod Security, RBAC, node firewall, IAM |
| KPN-07 | Pod lấy node/cloud credentials | Metadata/credential endpoint không được bảo vệ | Cloud permissions bị lạm dụng | Workload identity, metadata controls, egress/host policies |
| KPN-08 | Egress HTTPS toàn Internet | Rule quá rộng, workload bị compromise | Data exfiltration | Egress gateway/FQDN capability/identity/DLP |
| KPN-09 | Secondary network bypass chính sách | Policy chỉ enforce trên primary interface | Direct path tới sensitive network | Per-interface CNI/network ACL tests |
| KPN-10 | Direct Pod IP bypass API gateway | Pods có route vào backend không cần gateway | Bỏ WAF/rate-limit/auth nếu backend yếu | NetworkPolicy, backend auth, gateway-only exposure |
| KPN-11 | Service selector bị đổi | Principal sửa labels/Service | Route traffic sang Pod không đúng | Admission/RBAC, workload certs, audit |
| KPN-12 | DNS service name confusion | Private DNS, namespace name, search domain sai | Gọi nhầm service hoặc mất availability | FQDN verification, strict TLS SAN, DNS audit |
| KPN-13 | Pod IP address exhaustion | Pool/subnet/cloud quota cạn | Pods không tạo được network, outage | IPAM forecasting, quotas, subnet planning |
| KPN-14 | Overlapping Pod CIDRs multi-cluster | Kết nối clusters không quy hoạch | Route collisions hoặc NAT ambiguity | IPAM, service gateway, routing review |
| KPN-15 | Overlay traffic không mã hóa | Giả định VXLAN là encryption | Nguy cơ nghe lén dữ liệu trên đường | TLS/mTLS, CNI encryption, host trust |
| KPN-16 | Node tunnel port mở rộng | Cho mọi UDP/TCP giữa nodes để chạy CNI | Tăng bề mặt tấn công node | Giới hạn ports/peers CNI thực cần |
| KPN-17 | NAT trước/sau policy gây nhầm IP | Rule ipBlock dựa source/dest sai | False allow/deny trên Service/LB path | Test CNI dataplane, observe post/pre NAT |
| KPN-18 | IPv6 bypass IPv4 rules | Dual-stack nhưng policy/firewall không review IPv6 | Đường kết nối ngoài policy | Dual-stack policy/AAAA/egress tests |
| KPN-19 | NodeLocal DNSCache exception | DNS chạy qua node/local path khác | Mất DNS hoặc bypass quan sát | DNS architecture review, CNI-specific rules |
| KPN-20 | NetworkPolicy egress deny sai | Chặn DNS/telemetry/control dependencies | Outage nhiều services | Phased rollout, dependency map, rollback |
| KPN-21 | Service mesh sidecar bypass | Traffic không được redirect qua proxy | Bỏ mTLS/L7 policy | Mesh coverage, NetworkPolicy, app enforcement |
| KPN-22 | Egress qua VPC peering/on-prem không audit | Chỉ giám sát public Internet gateway | Data movement ra private peer không thấy | Cloud flow + CNI + app logs, route inventory |
| KPN-23 | Quá nhiều ServiceAccount/IAM permission | Pod có network access và cloud token rộng | Privilege escalation/data access | Least privilege IAM, token scope, admission |
| KPN-24 | Pod IP bị tái sử dụng | Cho phép IP lâu dài trong external firewall | Quyền cấp nhầm workload mới | Service identity, dynamic selectors, short-lived mappings |

### 13.3. STRIDE ở Pod network

| Mục STRIDE | Ví dụ | Cần bảo vệ |
| --- | --- | --- |
| **Spoofing** | Workload gắn label được allow, dùng shared IP/NAT làm giả danh tính | RBAC/admission, mTLS/API auth |
| **Tampering** | Sửa CNI config, NetworkPolicy, Service selector hoặc route | GitOps approvals, RBAC, audit |
| **Repudiation** | Chỉ có Pod IP, không gắn được owner/service/process theo timestamp | Workload metadata, event/time correlation, logs |
| **Information disclosure** | East–west plaintext, egress tới peer không được phép | TLS/mTLS, egress controls, data permissions |
| **Denial of service** | IPAM exhaustion, DNS outage, conntrack/overlay issues | Capacity, DNS HA, CNI health, failure tests |
| **Elevation of privilege** | HostNetwork/privileged Pod truy cập node/metadata | Pod Security, node firewall, workload IAM |

### 13.4. Attack tree mức phòng vệ

~~~mermaid
flowchart TD
  ROOT["Rủi ro: mạng Pod trở thành đường truy cập trái ý định"] --> A{"Bề mặt"}
  A --> L["Network reachability"]
  A --> H["Host / runtime access"]
  A --> C["Control-plane mutations"]
  A --> E["Egress / external access"]
  L --> LC["NetworkPolicy, source/dest allowlist,\nService identity + auth"]
  H --> HC["Pod Security, RBAC,\nnode firewall, metadata isolation"]
  C --> CC["CNI health, admission,\nIaC and audit"]
  E --> EC["Egress gateway, NAT/flow logs,\nDLP and cloud IAM"]
  LC --> V["Negative tests, monitoring\nvà incident playbook"]
  HC --> V
  CC --> V
  EC --> V
~~~

Sơ đồ mô tả **các lớp phòng vệ**, không phải hướng dẫn khai thác. Việc có route Pod-to-Pod chưa chứng minh một API bị truy cập trái quyền; cần phối hợp network evidence, identity/authorization và application audit.

### 13.5. Quan hệ tin cậy giữa Pod, node và cluster

Một tổ chức có thể dùng Kubernetes namespaces để quản lý services cùng mức tin cậy nhưng không nên mặc định namespaces cung cấp isolation tương đương **những cluster hoặc cloud accounts riêng biệt**. Workload từ nhóm không đáng tin hoặc có yêu cầu compliance khác có thể cần:

- Cluster/node pool riêng, với IAM/node policies và network segmentation phù hợp.
- Namespace quotas và admission theo trust tier.
- NetworkPolicy được thực thi, ít nhất default-deny và explicit allows.
- CNI Global/Cluster policies khi sản phẩm hỗ trợ và đã review.
- Workload identities, mTLS và resource-level authorization.
- Cross-cluster/service gateway thay vì direct Pod IP routing khi cần.

**Một Pod bị compromise có thể chỉ thực thi hành vi theo quyền Pod hiện có**, không được suy rằng nó tự chiếm node/control plane; threat model phải phân biệt **capabilities và điều kiện tấn công** cụ thể.

## 14. Logging và quan sát: nhìn đúng lớp của mạng Pod

### 14.1. Nguồn log trả lời câu hỏi nào?

| Nguồn | Thấy gì? | Không tự chứng minh |
| --- | --- | --- |
| Kubernetes Pod/Node status | Pod IP, node, conditions, events | Packet thật sự đã chuyển thành công |
| CNI/IPAM logs | Pod network setup, address allocation, policy failures | HTTP/business transaction đã được phép |
| CNI flow/NetworkPolicy logs | Pod IP/labels, allow/deny, ports theo plugin | User identity hoặc payload ứng dụng đã đọc |
| CoreDNS/NodeLocal DNS logs | Query/answer, latency, errors theo deployment | Client đã gọi service thành công |
| Service/EndpointSlice | Các backend endpoint/conditions | Backend logic/authn tốt |
| kube-proxy/eBPF dataplane telemetry | Service translation, connection/session path | Cùng một schema ở mọi CNI |
| Node/VPC/cloud flow logs | Node/Pod/NAT/VPC traffic theo vị trí capture | Inner Pod IP nếu đã encapsulated/NAT và logs không có inner view |
| Ingress/Gateway/WAF logs | HTTP method/path/status, auth/routing và rule decisions | Direct Pod-to-Pod bypass ngoài gateway |
| Service mesh logs | mTLS peer/service identity và request traces khi traffic đi qua mesh | Toàn bộ traffic nếu có mesh bypass |
| Application audit logs | Principal, action, resource, outcome | Network route nếu thiếu correlation |
| Kubernetes/cloud audit | Ai sửa Pod/Service/NetworkPolicy/CNI/IAM/route | Tự chứng minh data transfer đã xảy ra |

Một số CNI không có NetworkPolicy verdict logs hoặc cần bật exporter/enterprise feature. **Không bịa ra field policy verdict** trong logs khi sản phẩm không cung cấp.

### 14.2. Dữ liệu minh họa cho SIEM

~~~json
{
  "event_id": "podnet-lab-flow-014",
  "event_time": "2026-11-28T12:00:00Z",
  "source": "synthetic-cni-flow",
  "cluster": "training-cluster",
  "namespace": "podnet-lab",
  "src": {
    "pod": "untrusted-client",
    "pod_ip": "10.244.1.31",
    "labels": {"role": "untrusted"}
  },
  "dst": {
    "pod": "shared-ip-demo",
    "pod_ip": "10.244.2.12",
    "port": 8080,
    "protocol": "TCP"
  },
  "policy": {
    "name": "limit-demo-ingress",
    "direction": "ingress",
    "decision": "deny",
    "enforcer": "cni"
  },
  "synthetic": true
}
~~~

Đây là **schema tổng hợp cho đào tạo**, không đại diện cú pháp log của một CNI cụ thể. Không phải CNI nào cũng biết tên policy đã deny một flow, nhất là khi có nhiều policies additive. Khi điều tra production phải dùng những trường thật sự quan sát được, kèm **tên nguồn, event timestamp, collector timestamp và thông tin mapping Pod IP→Pod UID**.

### 14.3. Pod IP attribution theo thời điểm

Một IP Pod có thể được tái sử dụng sau khi Pod cũ bị xóa. Do đó, khi flow log chứa:

~~~text
2026-11-28T10:00Z  10.244.1.12 -> 10.244.2.21 TCP/8080
~~~

Đừng tra danh sách Pods **hiện tại** rồi khẳng định 10.244.1.12 tại 10:00Z thuộc Pod đang dùng IP đó lúc 14:00Z. Cần kết hợp:

- **Pod UID, creation/deletion time**, namespace, labels và owner references theo thời điểm.
- CNI/IPAM allocation/release events.
- Node ID, Pod IP family và interface/network attachment.
- NAT/conntrack logs nếu IP được chuyển đổi.
- Clock synchronization/event-time và log ingestion lag.

**IP mapping theo thời điểm là điều kiện quan trọng cho forensic**, nhất là cluster autoscaling và Pod churn lớn.

### 14.4. Kết hợp CNI và application logs

Ví dụ:

~~~text
10:00:00Z  CNI: frontend Pod → orders Pod TCP/8080 allowed
10:00:01Z  Proxy: request_id=req-001 route=/orders GET, 200
10:00:01Z  App: principal=storefront scope=orders:read action allowed
~~~

Chỉ khi ghép nhiều nguồn mới nói được **network flow có thể đi qua, request được xử lý và principal được authorization**. Nếu CNI báo allow nhưng API trả 403, đây có thể là **defense-in-depth hoạt động đúng**, không phải NetworkPolicy thất bại.

### 14.5. Nhận biết bypass/coverage gap

Hãy xem:

- Có traffic **hostNetwork**, NodePort/LoadBalancer hoặc secondary interfaces mà CNI flow logs bỏ qua không?
- Có service mesh sidecar bypass hoặc policy-disabled namespaces không?
- Có Pods ở node mới mà CNI agent/exporter chưa sẵn sàng không?
- Có DNS traffic qua NodeLocal DNSCache không được log bởi CoreDNS central không?
- Có overlay traffic mà VPC flow logs chỉ thấy **Node IP tunnel traffic** không?
- Có egress SNAT mà SIEM không liên kết được Pod identity với NAT source IP không?

**Im lặng trong SIEM không phải bằng chứng traffic bị chặn.** Kết hợp exporter heartbeat, policy-status, synthetic probes và cross-source checks.

### 14.6. Metric quan trọng

| Nhóm | Metric | Dấu hiệu cần theo dõi |
| --- | --- | --- |
| IPAM | Địa chỉ còn trong pool, allocation failures | Pod network không tạo được, IP exhaustion |
| CNI | Plugin/agent readiness, setup latency, errors | ContainerCreating kéo dài |
| Pod | PodIPs theo node/family, restarts, recreate/evictions | Pod IP churn, DNS/service endpoint changes |
| Cross-node | Packet drops, RTT, MTU/MSS, tunnel health | Lỗi chỉ giữa nodes/AZs |
| Policy | Allow/deny flows, selected endpoints, drift | Unexpected lateral paths hoặc default deny |
| DNS | CoreDNS availability, query latency, SERVFAIL/NXDOMAIN | DNS không hoạt động sau egress policy |
| Service | EndpointSlice readiness, service/port connections | ClusterIP reachable nhưng không có backend |
| Egress | Egress gateway bytes, SNAT source, external destinations | Data exfil/egress bypass |
| Identity | mTLS failures, API authorization deny, token issues | Network được nhưng service không tin peer |
| Coverage | Flow exporter heartbeat, missing namespaces/nodes | Mất visibility bị nhầm giảm sự cố |

### 14.7. Bảo vệ dữ liệu trong logs

Không ghi **ServiceAccount tokens, TLS private keys/session secrets, Authorization headers, credentials, raw customer payload** vào flow logs hoặc SIEM chung. Pod names/labels, IPs, namespace và hostnames có thể tiết lộ cấu trúc hạ tầng; cần **RBAC/retention/tenant isolation** cho log access.

Nếu dùng packet capture hoặc TLS keylog trong sandbox, chỉ thu dữ liệu của **workload bạn quản lý** và bảo vệ file theo policy. Trong production, ưu tiên **metadata/traces đã redaction** và application audit theo quyền.

## 15. Troubleshooting Pod networking theo từng lớp

### 15.1. Đừng kết luận “CNI hỏng” từ một lần curl timeout

Một kết nối ứng dụng thành công qua Kubernetes thường phụ thuộc:

1. Pod được **scheduled** tới node có đủ tài nguyên.
2. Runtime/CNI **tạo được sandbox/network**, cấp IP.
3. Application process **đang nghe đúng address/port**.
4. DNS **phân giải đúng Service hoặc hostname** khi client dùng DNS.
5. Service/EndpointSlice/backend selector **trỏ đúng endpoints sẵn sàng**.
6. CNI route/dataplane **chuyển được traffic intra-node/cross-node**.
7. NetworkPolicy/SG/firewall **cho phép cả source egress và destination ingress** khi cần.
8. TLS/mTLS xác thực peer và **application authorization** cho request.
9. Return traffic có đường về, NAT/conntrack/MTU ổn định.

Mỗi lỗi có triệu chứng chồng lấn, nên cần **đặt phép thử theo từng tầng**, tránh sửa một policy rộng hoặc tắt TLS verification để khắc phục timeout chưa rõ nguyên nhân.

### 15.2. Sơ đồ chẩn đoán

~~~mermaid
flowchart TD
  A["Pod/Service không kết nối được"] --> B{"Pod Running và có Pod IP?"}
  B -- "Không" --> B1["Scheduling, kubelet/runtime,\nCNI/IPAM, node events"]
  B -- "Có" --> C{"Listener đúng IP:port?"}
  C -- "Không" --> C1["App bind-address, process,\nport conflict, readiness"]
  C -- "Có" --> D{"Client gọi DNS/Service hay Pod IP?"}
  D -- "DNS/Service" --> E{"DNS và EndpointSlice đúng?"}
  E -- "Không" --> E1["CoreDNS/NodeLocal DNS,\nService selector/readiness"]
  E -- "Có" --> F["Test TCP tới backend Pod IP\nvới quyền sandbox"]
  D -- "Pod IP" --> F
  F --> G{"Policy, route và cross-node path đúng?"}
  G -- "Không" --> G1["CNI route, NetworkPolicy 2 chiều,\nSG/NAT/MTU"]
  G -- "Có" --> H{"TLS/mTLS + API authorization đúng?"}
  H -- "Không" --> H1["CA/SAN, principal, scopes,\nproxy/mesh identity"]
  H -- "Có" --> I["Đo SLO, tracing, retry,\nbackend dependencies"]
~~~

Không dùng phép thử **ping ClusterIP** như tiêu chí duy nhất vì Service chủ yếu định nghĩa transport port translation theo cấu hình và ICMP không nhất thiết được xử lý.

### 15.3. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Bằng chứng ưu tiên |
| --- | --- | --- |
| Pod Pending, không có IP | Scheduler/taint/resources, chưa gán node | Pod events, scheduler status |
| Pod ContainerCreating lâu | Sandbox/CNI setup fail, IPAM exhaustion | Pod events, node/runtime/CNI logs |
| Hai containers cùng Pod không nói qua localhost | Listener không bind, sai port, app crash | App/probe logs, socket listener |
| Hai containers cùng Pod không thể cùng nghe 8080 | Cùng network namespace/cùng port | Bind error, process sockets |
| Hai Pods cùng node không kết nối | CNI local bridge/route/policy, listener | PodIPs, policy, node dataplane |
| Cùng-node OK, cross-node lỗi | Overlay/underlay routes, tunnel firewall, MTU | CNI health, node-to-node path, drops |
| Pod IP direct OK, Service name fail | DNS/CoreDNS/NodeLocal DNS, Service/EndpointSlice | DNS resolve, Service endpoints |
| Service IP resolve OK nhưng không có response | Service no backends, targetPort mismatch, policy | EndpointSlice, app listener, CNI LB |
| Pod đổi IP sau deployment | Pod recreation/rescheduling | Pod UID/events/EndpointSlice |
| Pod có IP nhưng HTTP 403 | API auth/authorization hoặc WAF | Request ID, app/gateway logs |
| Pod có IP nhưng TLS hostname error | Certificate/CA/SNI mismatch | TLS client verification logs |
| NetworkPolicy tồn tại nhưng không chặn | CNI không enforce, selector sai, policy allow khác | Policy inventory, CNI support, negative test |
| Default-deny egress làm mất DNS | Thiếu DNS allow hoặc NodeLocal DNS case | DNS query timeout, policy logs |
| Request được allow từ Pod sai | YAML from OR/AND sai, label spoof, source NAT | Selector/effective sources, audit |
| NodePort/LB request lúc được lúc không | Backend readiness, proxy NAT/health, multi-node path | Per-node/EndpointSlice/ingress logs |
| hostNetwork Pod không bị policy như mong đợi | Host network namespace/CNI exception | Pod spec, CNI host policy behavior |
| External server thấy Node IP | SNAT/NAT gateway/egress proxy | Egress path/NAT/flow logs |
| IPv4 hoạt động, IPv6 timeout | Dual-stack CNI/route/AAAA/firewall khác | podIPs, Service ipFamilies, IPv6 routes |
| Chỉ request lớn bị treo | Overlay/tunnel MTU, PMTU/ICMP block | Retransmissions, MSS, MTU metrics |
| Observability không có Pod source IP | Outer tunnel/VPC flow chỉ thấy Node IP | CNI flow logs, encapsulation view |
| Chỉ một network attachment không được policy | Secondary interface bypass | Multus/SR-IOV CNI policy coverage |
| Lỗi sau node scale-out | IPAM quota, CNI readiness/new-node SG | Per-node IP pools, CNI agent telemetry |
| Curl direct Pod IP success nhưng Gateway WAF deny | API/gateway policy đúng thiết kế | Gateway decision and direct path controls |

### 15.4. Lệnh kiểm tra không làm thay đổi cluster

Các lệnh sau có thể hữu ích trong lab khi có quyền đọc:

~~~bash
# Thông tin Pod, Node IP và Pod IP.
kubectl get pods -n podnet-lab -o wide
kubectl get nodes -o wide

# Events/status trong namespace ứng dụng được giao.
kubectl describe pod shared-ip-demo -n podnet-lab

# Service và backends.
kubectl get svc -n podnet-lab
kubectl get endpointslices -n podnet-lab

# Kiểm tra chính sách được khai báo.
kubectl get networkpolicies -n podnet-lab -o yaml

# Trích địa chỉ Pod.
kubectl get pod shared-ip-demo -n podnet-lab \
  -o jsonpath='{.status.podIP}'
~~~

**Chú ý quyền riêng tư và phạm vi:** liệt kê tất cả namespaces/nodes có thể tiết lộ thông tin hạ tầng; chỉ chạy khi Kubernetes RBAC và quy trình cấp quyền cho phép. Với môi trường bị giới hạn namespace, dùng namespace được chỉ định thay vì cố mở rộng quyền.

### 15.5. Kiểm tra từ trong container

Nếu container có các công cụ mạng và người học có quyền exec:

~~~bash
kubectl exec -n podnet-lab shared-ip-demo -c probe -- \
  sh -c 'hostname && cat /etc/resolv.conf'

kubectl exec -n podnet-lab shared-ip-demo -c probe -- \
  wget -T 3 -qO- http://127.0.0.1:8080/

kubectl exec -n podnet-lab external-client -- \
  wget -T 3 -qO- http://shared-ip-demo:80/
~~~

Không giả định mọi application container đều có công cụ như iproute2, ss, ping, curl, getent hoặc shell: distroless images có thể không có. **Không cài gói hoặc sửa production image để debug** nếu có lựa chọn logging/ephemeral debug container được phê duyệt và RBAC.

### 15.6. Khi CNI/IPAM không cấp được Pod IP

Lộ trình:

1. Xem **Pod events** và lý do Pending/ContainerCreating.
2. Xác minh Pod được schedule và **node Ready**, kubelet/runtime hoạt động.
3. Đối chiếu **CNI daemon health**, config version và startup.
4. Kiểm tra **IPAM allocation pool**, subnet/ENI/cloud API quotas.
5. Xem Pod CIDR/Node CIDR assignment nếu CNI sử dụng.
6. Kiểm tra network attachment definitions khi Pod yêu cầu multiple interfaces.
7. Rà IAM permissions cấp interface/IP trong cloud-native CNI.
8. Chỉ xử lý resource/IP pool hoặc restart components sau khi có **root cause và change approval**.

**Không dọn sạch IPAM state, xóa CNI Pods hoặc restart networking cluster-wide một cách tùy tiện**: có thể làm gián đoạn toàn bộ workloads và tạo IP conflicts khó khôi phục.

### 15.7. Khi Service lỗi nhưng Pod IP direct hoạt động

Đây là tín hiệu đáng điều tra ở **Service layer**:

- Service selector không chọn đúng labels của Pods.
- EndpointSlice không có healthy endpoints.
- Service port/targetPort/protocol sai.
- DNS Service trả name/IP sai.
- Dataplane proxy/eBPF rules chưa cập nhật theo changes.
- NetworkPolicy hoặc NAT order làm Service traffic bị deny khác direct Pod IP traffic.
- Client connection giữ destination đã lỗi sau rollout/failover.

Không sửa bằng cách mở tất cả network policies. Cần **xác định đúng điểm dịch sai**, kiểm tra Service, endpoints, dataplane và route.

### 15.8. Khi NetworkPolicy làm gián đoạn DNS

Một rollout default-deny egress có thể khiến:

~~~text
Lookup orders-api.app.svc.cluster.local => timeout
Direct TCP to known Pod IP             => success/fail tùy policy
~~~

Hãy kiểm tra:

1. Pod đang dùng **cluster DNS Service IP, node-local cache hay resolver khác**?
2. Policy cho phép **UDP và TCP 53** đến đúng Pods/addresses chưa?
3. DNS traffic tại CNI enforcement point có bị DNAT/redirect trước đó không?
4. CoreDNS/NodeLocal DNS Pods có healthy và route tới upstream DNS không?
5. NamespaceSelector/PodSelector có thực sự chọn DNS endpoints không?
6. Có một policy khác mở/đóng egress theo semantics additive không?

Chỉ sau khi xác định path mới chỉnh allowlist phù hợp. **Không mặc định mở mọi egress**, vì có thể đánh mất mục tiêu chống exfiltration.

### 15.9. Khi request lớn lỗi, request nhỏ chạy

Nếu WebSocket/gRPC/HTTPS response lớn thất bại giữa nodes, nhưng localhost hoặc cùng-node vẫn chạy:

- Xem **Pod MTU, node MTU, tunnel overhead**, cloud path restrictions.
- Kiểm tra firewall cho **ICMP Packet Too Big/Fragmentation Needed** cần thiết.
- So packet retransmissions, TCP MSS, eBPF drops và overlay tunnel metrics.
- Kiểm tra timeout/connection draining tại Service/mesh/gateway.
- Phân biệt UDP/QUIC với TCP nếu ứng dụng có nhiều transport protocols.

Một lệnh ping nhỏ không đủ xác nhận **TCP/gRPC traffic với payload lớn** hoạt động ổn.

## 16. Thiết kế triển khai Pod network an toàn

### 16.1. Bước 1 — Chọn network model và IPAM có chủ đích

Trước khi tạo cluster:

- Xác định **Pod CIDR, Service CIDR, Node subnet và IPv6 strategy**; tránh overlap với VPC peering, VPN/on-prem và các clusters khác.
- Chọn CNI theo **feature coverage**: NetworkPolicy, dual-stack, encryption, eBPF/overlay, cloud-native IPAM, secondary networks khi cần.
- Kiểm tra **IP pool/subnet/ENI quotas** và kế hoạch node autoscaling.
- Lập danh sách network ports giữa nodes/control-plane/CNI/observability thật sự cần.
- Xác định Pod egress source IP/NAT và external destinations.
- Đặt owner cho route, cloud IAM, CNI operator, NetworkPolicy và incident response.

Một **địa chỉ Pod per Pod** mang lại mô hình ứng dụng đơn giản, nhưng có **chi phí IP capacity**: với hàng nghìn Pods, IPAM và subnet size phải được tính trước để tránh exhaustion.

### 16.2. Bước 2 — Phân vùng workloads theo trust

Một kiến trúc tham khảo:

~~~mermaid
flowchart TB
  USER["External client"] --> EDGE["Ingress/Gateway/WAF\nTLS termination"]
  subgraph CL["Kubernetes cluster"]
    WEB["Namespace web\nfrontend Pods"]
    APP["Namespace app\nAPI Pods"]
    DATA["Namespace data\ndatabase/proxy Pods"]
    OPS["Namespace platform\nDNS/CNI/telemetry"]
  end
  EDGE --> WEB
  WEB -->|"HTTPS/mTLS\nallowed only"| APP
  APP -->|"DB protocol\nidentity + ACL"| DATA
  OPS -. "Operational dependencies\nstrictly scoped" .-> APP
  APP --> EGR["Controlled egress\nfirewall/gateway"]
  EGR --> EXT["Cloud service / on-prem"]
~~~

Chính sách mong muốn:

- Internet chỉ tới **Ingress/Gateway** đã duyệt, không trực tiếp vào database Pods.
- Frontend chỉ gọi API services cần thiết, không được truy cập data namespace tự do.
- API chỉ gọi database/queue/cache/service endpoints được cấp quyền.
- DNS/telemetry/secrets/cloud IAM dependencies được allow **đúng đường**.
- Management/node/metadata interfaces không thuộc application reachability nếu không cần.
- Egress được kiểm soát cả private VPC peering, NAT và public Internet.

**Namespace-based separation không thay cluster/account isolation** nếu workloads thuộc các trust tiers cực khác nhau. Khi cần, kết hợp separate clusters/node pools/VPCs và IAM boundaries.

### 16.3. Bước 3 — Thiết kế policy theo flow matrix

| Nguồn | Đích | Port | Yêu cầu | Network decision |
| --- | --- | --- | --- | --- |
| Ingress controller | Frontend | TCP/8080 | Route hợp lệ qua Gateway/WAF | Allow scoped |
| Frontend | API | TCP/8080/8443 | mTLS/API auth theo service | Allow scoped |
| Frontend | Database | TCP/5432 | Không có use case | Deny |
| API | Database | TCP/5432 | DB identity riêng | Allow scoped |
| API | CoreDNS | UDP/TCP 53 | Service discovery | Allow scoped |
| API | Authorized cloud endpoint | TCP/443 | TLS/IAM đúng | Allow scoped |
| Untrusted namespace | API/admin | Any | Ngoài quyền | Deny |
| Ordinary Pod | Node metadata/admin | Sensitive ports | Không phải use case ứng dụng | Deny qua nhiều lớp |
| API | Internet arbitrary IP | TCP/443 | Không có hợp đồng egress | Deny trừ exceptions |
| Platform agents | CNI/DNS/control plane | Per component | Vận hành cluster | Chỉ allow dependencies được kiểm kê |

Đây là **ý định kiến trúc**, không phải một NetworkPolicy duy nhất triển khai được tất cả: một số đích nằm ở host/cloud IAM/secondary interfaces phải dùng controls khác.

### 16.4. Bước 4 — Rollout NetworkPolicy theo giai đoạn

1. Inventory **Pod/Service/EndpointSlice, workload owners, labels và current traffic**.
2. Dùng flow logs/traces tìm các **legitimate dependencies** gồm DNS, metrics, secrets và egress.
3. Viết **allow policies tường minh** cho từng ứng dụng, review label selectors và namespace access.
4. Kiểm tra CNI **thực thi** NetworkPolicy và có cơ chế rollback.
5. Triển khai trong **sandbox hoặc canary namespace** có traffic đại diện.
6. Áp ingress default-deny rồi test allowed/denied flows, chuyển sang egress có DNS rules khi sẵn sàng.
7. Thử **same-node, cross-node, IPv4/IPv6, Service VIP và direct Pod IP**.
8. Xem errors/latency, DNS, readiness, mTLS/API auth; ghi record mỗi path.
9. Mở rộng rollout theo workload/trust tier, không nới allow all khi gặp lỗi chưa rõ.
10. Định kỳ kiểm tra **policy drift** khi đổi labels, Services, CNI version hoặc cloud subnet.

Với các plugin có **dry-run/policy audit modes** riêng, có thể dùng để quan sát trước khi enforce nếu được hỗ trợ; Kubernetes NetworkPolicy chuẩn không có cơ chế thống nhất “audit-only” cho mọi CNI.

### 16.5. Bước 5 — Áp chính sách identity và data protection

- Bật TLS/mTLS cho service-to-service có yêu cầu bí mật/peer verification.
- Giới hạn ServiceAccount permissions/RBAC và cloud workload identity.
- Không tự động mount API credentials khi workload không cần, theo cấu hình được phê duyệt.
- Dùng runtime security: **runAsNonRoot, drop capabilities, seccomp, read-only filesystem** khi phù hợp với ứng dụng.
- Kiểm soát debug/ephemeral containers, hostNetwork và privileged profiles.
- Dùng Kubernetes Secrets/service identity management đúng thay vì hardcode tokens.
- Đặt API authorization theo resource/action/tenant, kể cả khi NetworkPolicy allow.

### 16.6. Bước 6 — Chuẩn bị fallback và vòng đời CNI

CNI failure có thể tác động cluster rộng hơn một ứng dụng. Để giảm blast radius:

- Theo dõi **agent readiness, IPAM availability, cloud API quotas và network policy synchronization**.
- Dùng GitOps/versioned config với kiểm thử rollback.
- Có kế hoạch thay Pod/Node image/CNI version theo **canary node pools** khi khả thi.
- Kiểm thử node replacement, autoscaling và cross-AZ routes.
- Đảm bảo rollback không làm lộ thông tin qua **deny-all bị bỏ đi**, host network bypass hoặc open egress.
- Có runbook riêng cho **policy regression** và **CNI/dataplane outage**; nguyên nhân và cách xử lý khác nhau.

**Đổi CNI hoặc node networking không nên thực hiện như một thao tác sửa YAML thông thường trong giờ cao điểm**. Nó có thể gây mất kết nối, thay Pod IP hoặc policy enforcement và cần change management rõ.

### 16.7. Bước 7 — Xác minh và đánh giá định kỳ

Khi thay:

- Kubernetes/CNI version, eBPF service dataplane, Node OS.
- Pod CIDR/Service CIDR, subnet/ENI quotas hoặc dual-stack strategy.
- Cloud VPC peering/VPN/private endpoints/egress gateway.
- Namespace/Pod labels, Service selectors, DNS components.
- Service mesh sidecar injection, mTLS CA hoặc authorization policies.
- Ingress/Gateway/WAF, NodePort/LoadBalancer exposure.
- NetworkPolicy objects và admission controls.

Chạy lại **positive và negative network tests**. “Kubernetes API báo policy tồn tại” không đủ; điều quan trọng là **traffic thực sự được cho phép/từ chối đúng** với CNI/network topology đang chạy.

## 17. Tình huống vận hành: khi một Pod IP tạo ra hiểu nhầm

### Case A — Hai containers cùng Pod, cả hai muốn nghe TCP/8080

Ứng dụng và metrics sidecar cùng cấu hình lắng nghe TCP/8080. Container app chạy trước, sidecar báo lỗi **address already in use**.

**Giải thích:** cả hai containers **chia sẻ network namespace và port space** của Pod. Việc có hai container names không cấp hai IP hoặc hai không gian port riêng.

**Xử lý:** đổi port của một listener, hoặc thiết kế một proxy listener chuyển tiếp tới port app khác. Không giải quyết bằng cách cấp thêm Service IP nếu tiến trình trong cùng Pod vẫn tranh chấp cùng socket.

### Case B — Pod A gọi 127.0.0.1 nhưng server ở Pod B

Frontend Pod gửi HTTP request tới 127.0.0.1:8080 với ý định gọi Backend Pod. Request thất bại hoặc đi tới tiến trình khác của chính Frontend Pod.

**Giải thích:** loopback là **local network namespace của Pod A**, không phải một địa chỉ “cluster local chung”. Sửa thành **Service DNS của Backend** hoặc Pod IP khi test được phép, và xác minh NetworkPolicy/mTLS phù hợp.

### Case C — Rolling update khiến Pod IP đổi và client mất kết nối

Deployment thay Pod backend và cấp IP mới. Một client đã lưu cứng 10.244.1.12 báo connection refused/timeout.

**Giải thích:** Pod IP là **địa chỉ endpoint theo lifecycle**, không phải service identity ổn định. Dùng Service/EndpointSlice/DNS, readiness, retry/backoff, connection drain và application session recovery. Không dùng firewall allowlist IP Pod cũ như chứng cứ Pod mới vẫn có quyền.

### Case D — Pod IP direct OK, ClusterIP HTTP không tới backend

Client gọi 10.244.2.21:8080 thành công nhưng gọi Service DNS không được. Trong Service, selector chỉ app=orders; Backend Pod lại có label app=order.

**Giải thích:** Service selector không chọn backend, EndpointSlice có thể không có endpoint phù hợp. Sửa **labels/selectors** qua change control rồi kiểm tra EndpointSlice; đừng mở SG/NetworkPolicy toàn cluster chỉ để chữa một typo.

### Case E — Default-deny ingress hoạt động nhưng trusted frontend cũng bị chặn

Backend có default-deny ingress và allow policy chọn Pods frontend theo role=client ở namespace web. Frontend label thực là role=storefront hoặc namespace label chưa được áp.

**Giải thích:** NetworkPolicy selectors không khớp nguồn. Kiểm tra **Pod/namespace labels**, cấu trúc AND/OR và CNI enforcement. Không sửa bằng cách xóa default-deny hoặc thêm ingress allow-all; thay selector có review và negative test.

### Case F — Policy cho phép Backend ingress, nhưng Frontend không gửi được

Backend NetworkPolicy đã allow frontend Pod TCP/8080, nhưng client có **egress default-deny** chỉ allow DNS.

**Giải thích:** để Pod-to-Pod flow thành công, phải được **source egress** và **destination ingress** cho phép nếu cả hai phía bị isolation. Thêm egress allow đúng Backend Pods/ports và test cả Pod IP lẫn Service path; không cần mở toàn TCP/443 Internet.

### Case G — DNS bị chặn sau chính sách egress

Sau triển khai default-deny egress, ứng dụng mất khả năng gọi service names nhưng request tới IP cũ đôi lúc còn được.

**Giải thích:** lookup tới CoreDNS/NodeLocal DNSCache có thể chưa được phép. Xác định **DNS resolver thực của Pod**, policy matching labels/IP/port và CNI NAT order; allow DNS đúng scope thay vì hủy egress isolation.

### Case H — Cross-node traffic lỗi, same-node vẫn chạy

Hai Pods trên cùng node kết nối được. Khi scheduler đặt backend ở node khác, kết nối thất bại; node firewall vừa thay đổi.

**Giải thích:** lỗi có thể do **CNI encapsulation/underlay route, tunnel ports hoặc MTU** giữa nodes. Kiểm tra CNI mode, node-to-node permissions, route và drops. Không suy rằng Kubernetes API server phải proxy packet giữa Pods.

### Case I — Một cloud instance hết IP cho Pods dù CPU còn nhiều

Node có CPU/memory trống nhưng Pods mới mắc ở ContainerCreating với CNI address assignment errors.

**Giải thích:** **IPAM/subnet/secondary IP/ENI quota** có thể là tài nguyên khan hiếm độc lập với CPU. Cần capacity planning, subnet pool/IPAM diagnostics và scale node/network đúng quota, không xóa bừa IP allocations hay CNI state.

### Case J — hostNetwork Pod truy cập port quản trị node

Một DaemonSet được cấp hostNetwork/privileged cho mục đích metrics, nhưng có khả năng thấy Node IP/ports và security group cho phép mạng quản trị nội bộ.

**Giải thích:** hostNetwork dùng mạng host và NetworkPolicy namespace có thể không cô lập nó như một Pod thường. Phải rà **RBAC, admission, node firewall, ServiceAccount IAM, host controls** và giới hạn capabilities. Không dùng hostNetwork chỉ để “cho DNS chạy dễ hơn”.

### Case K — IP Pod bị NAT, external service chỉ thấy Node IP

Một API bên ngoài cloud áp allowlist theo Pod IP 10.244.1.12, nhưng logs của nó chỉ thấy IP từ NAT gateway. API từ chối.

**Giải thích:** egress path có thể **SNAT**; external peer không thấy Pod IP. Thiết kế egress identity/allowlist đúng **NAT/egress gateway public identity**, đồng thời xác thực API principal/token/cert riêng. Không gán IP NAT chung cho một Pod duy nhất khi forensic.

### Case L — Overlay chạy tốt nhưng chưa mã hóa

Đội vận hành cho rằng VXLAN/Geneve tạo tunnel nên payload của API đã được mã hóa như VPN. Họ bỏ TLS ở ứng dụng.

**Giải thích:** encapsulation **không mặc định encryption**. Kiểm tra CNI encryption options hoặc dùng TLS/mTLS theo threat model. NetworkPolicy không mã hóa payload; private Node IP cũng không tự cung cấp cryptographic peer identity.

### Case M — NetworkPolicy allow Pod label do người không đáng tin tự đặt

Một allow policy tin Pods với app=payment-client trong namespace rộng. Nhóm dev được phép tạo Pods/labels trong namespace đó, vô tình hoặc cố ý tạo workload với label tương tự.

**Giải thích:** labels là metadata, không phải cryptographic identity. Giới hạn quyền gắn labels/namespace selectors và tách trust domains; dùng **mTLS/service account identity và application authorization** cho payment endpoint. Đừng coi một allow selector là bằng chứng principal đã được xác thực.

### Case N — Một secondary interface vượt policy ở eth0

Pod có eth0 thuộc CNI primary và net1 thuộc một mạng phụ phục vụ appliance; các NetworkPolicy tests ở eth0 đạt, nhưng traffic qua net1 không bị chặn.

**Giải thích:** enforcement scope đối với **secondary networks** có thể khác. Cần policy theo CNI attachment, host/cloud firewall và interface-specific tests, hoặc cô lập workload theo kiến trúc. Không khẳng định “NetworkPolicy an toàn” khi chưa kiểm tra mọi interface.

### Case O — VPC peering mới cho Pod IP reachable từ ngoài cluster

Cloud VPC-A chứa cluster với VPC-native Pod IPs. Một VPC-B mới peered tới VPC-A và có route/firewall đến Pod subnet; một service quản trị chỉ bind Pod IP có thể trở nên reachable ngoài cluster.

**Giải thích:** private Pod IP không tự đồng nghĩa “chỉ nội bộ Kubernetes”. Kiểm tra **VPC routes, peering, SG/NACL, NetworkPolicy enforcement, node/Pod network paths**. Giữ management access và identity policies independent of IP reachability.

### Case P — HTTP 403 sau mTLS, team muốn sửa NetworkPolicy

Frontend kết nối HTTPS tới Backend thành công, nhưng Backend trả 403 do token thiếu scope orders:read.

**Giải thích:** NetworkPolicy/TLS có thể hoạt động đúng, **application authorization** từ chối principal. Không mở thêm IP/ports; sửa token/scope/role qua quy trình IAM nếu đây là request hợp lệ.

### Case Q — IPv6 khiến một policy kiểm IPv4 bỏ sót

Cluster dual-stack có A/AAAA records. Rules chỉ review IPv4 ranges; ứng dụng vẫn kết nối bằng IPv6.

**Giải thích:** cần kiểm tra **Pod/Service IPv6, NetworkPolicy ipBlock IPv6, cloud IPv6 firewall và DNS**. Không giả định policy IPv4 áp tự động lên IPv6, đặc biệt với allow CIDR theo family.

### Case R — SIEM gán một Pod IP cho sai ứng dụng

Flow log lúc 10:00 ghi IP 10.244.1.12 thuộc workload cũ. Lúc 11:00 Pod mới nhận lại IP đó. Dashboard hiện chỉ tra Pod snapshot 11:00 rồi kết luận workload mới đã tạo flow lúc 10:00.

**Giải thích:** cần correlate **Pod UID/IPAM allocation windows và event_time**, không join flow với pod inventory hiện tại một cách vô điều kiện. Nếu CNI metadata không có đủ, ghi rõ forensic uncertainty thay vì suy diễn identity.

## 18. Checklist kiến trúc và nghiệm thu

### 18.1. Pod network model và địa chỉ

- [ ] Mỗi Pod thường có **network namespace/IP chính riêng**; multiple containers cùng Pod share localhost/ports.
- [ ] Biết chính xác cluster dùng IPv4-only, IPv6-only hay dual-stack; xem podIP/podIPs.
- [ ] Đã phân biệt Node IP, Pod IP, Service ClusterIP, external LB IP và Service DNS.
- [ ] Không hardcode Pod IP lâu dài trong service configuration/client allowlists.
- [ ] Pod network CIDRs và Service CIDRs không overlap với node/on-prem/peering paths ngoài kế hoạch.
- [ ] IPAM pools/subnet/ENI quotas đủ cho autoscaling, rollout và DR.
- [ ] CNI setup/remove IP lifecycle có logs và error monitoring.
- [ ] hostNetwork, hostPort và secondary interfaces có ownership/exception review.

### 18.2. CNI, routing và dataplane

- [ ] CNI/dataplane mode đã được ghi rõ: overlay, routed, cloud-native IP, eBPF hoặc kết hợp.
- [ ] Same-node và cross-node traffic đều được kiểm thử trên các AZ/node pools quan trọng.
- [ ] Node firewall/cloud SG cho phép đúng traffic tunnel/underlay cần thiết.
- [ ] Không nhầm encapsulation với TLS/IPsec encryption.
- [ ] MTU/PMTU/ICMP và large payload workloads được test theo path.
- [ ] IPv6 route và ICMPv6 cần thiết được kiểm tra.
- [ ] Egress NAT/source IP mapping đến cloud/private/on-prem được ghi lại.
- [ ] Có capacity/drain/failover tests cho CNI và node replacements.

### 18.3. Service/DNS và exposure

- [ ] Service selectors/EndpointSlices có healthy backends và targetPort đúng.
- [ ] Application chỉ bind localhost khi thật sự chỉ muốn same-Pod traffic.
- [ ] ClusterIP được hiểu là virtual IP, không phải một Pod IP cố định.
- [ ] DNS/CoreDNS/NodeLocal DNS architecture đã được inventory.
- [ ] Không dùng ping ClusterIP làm health check duy nhất.
- [ ] Ingress/Gateway/LoadBalancer/NodePort exposure đúng scope, không mở management ports ngoài dự kiến.
- [ ] TLS termination, client IP/trusted forwarded headers và backend authorization được kiểm tra.
- [ ] Direct Pod IP bypass Gateway/WAF bị giới hạn nếu mục tiêu buộc request qua Gateway.

### 18.4. NetworkPolicy và identity

- [ ] CNI **thực sự enforce NetworkPolicy**, không chỉ chấp nhận YAML.
- [ ] App namespaces được áp default-deny ingress/egress theo rollout đã kiểm thử.
- [ ] Allowed flows được mô tả cụ thể theo **Pod/namespace selectors, port và chiều**.
- [ ] Biết chính xác khác biệt **AND vs OR** của namespaceSelector/podSelector trong một rule.
- [ ] Các policy allow cộng gộp được review để không có allow-all vô ý.
- [ ] DNS, telemetry, secrets và các dependencies thiết yếu được cho phép hẹp.
- [ ] ipBlock/NAT/Service translation behavior được test trên CNI thực.
- [ ] HostNetwork/node metadata traffic và secondary interfaces có controls riêng.
- [ ] RBAC/admission giới hạn ai được đổi Pod/namespace labels và NetworkPolicy.
- [ ] TLS/mTLS, workload identity và application authorization không bị thay bằng IP/labels.

### 18.5. Logs và response

- [ ] Logs ánh xạ **Pod UID, namespace, IP, Node, labels và event_time** chính xác.
- [ ] Flow/CNI/DNS/Service/Gateway/authorization logs được tương quan theo nguồn quan sát.
- [ ] Có alerts cho IPAM exhaustion, CNI agent failure, unexpected egress và policy drift.
- [ ] Có coverage checks cho hostNetwork/NodePort/secondary interfaces/egress NAT.
- [ ] SIEM không lưu raw secrets, TLS private keys, service account tokens, payload khách hàng không cần.
- [ ] Có runbook khi rollout default-deny gây DNS outage và cách rollback không mở tất cả.
- [ ] Positive + negative tests được chạy lại sau CNI, Kubernetes, cloud networking và policy changes.

### 18.6. Tiêu chí nghiệm thu ngắn gọn

| Kiểm tra | Bằng chứng | PASS khi |
| --- | --- | --- |
| Shared Pod network | Hai containers cùng Pod, localhost test | Chia sẻ một Pod IP/netns như dự kiến |
| Pod isolation semantics | Hai Pod khác có IP khác, localhost độc lập | Không dùng localhost để gọi Pod khác |
| CNI/IPAM | Pod events, IP assignment, cross-node connectivity | IP không trùng trong cluster network và route đúng |
| Service abstraction | ClusterIP, DNS, EndpointSlice, port mapping | Client gọi Service dù backend Pods thay |
| Default deny | Policy + negative test với CNI active | Untrusted source bị chặn đúng hướng |
| Explicit allows | Source/destination labels/ports được xác minh | Trusted flow chạy, không mở rộng ngoài policy |
| Egress dependencies | DNS/API/cloud endpoint tests | DNS và approved egress hoạt động, other egress bị deny |
| Host/secondary paths | HostNetwork/extra-interface tests | Không có bypass ngoài policy |
| Identity | mTLS/API authorization logs | Network allow không cấp quyền vượt scope |
| Monitoring | IPAM/CNI/flow/DNS/app logs, heartbeat | Có đủ evidence và ghi rõ coverage gaps |

**Không kết luận chỉ từ YAML hoặc một request trả HTTP 200.** Nghiệm thu cần chứng minh **quyền bị cấm vẫn bị từ chối** và kiểm tra CNI/NetworkPolicy trong đường dữ liệu thật.

## 19. Bài tập thiết kế và câu hỏi ôn tập

### 19.1. Bài tập kiến trúc: một Pod IP nhưng nhiều ranh giới an ninh

Một tổ chức có cluster Kubernetes trong một VPC cloud với:

~~~text
Cluster:
  Nodes: 192.0.2.10, 192.0.2.11, 192.0.2.12
  Pod CIDR minh họa: 10.244.0.0/16
  Service CIDR minh họa: 10.96.0.0/12

Namespaces:
  edge: Ingress/Gateway Pods
  web:  Frontend Pods
  app:  Orders/Payment API Pods
  data: Database proxy/Queue Pods
  ops:  Telemetry services

External:
  Internet clients → cloud LoadBalancer
  VPC peer → reporting API
  VPN/on-prem → enterprise database

Controls:
  Kubernetes NetworkPolicy
  Cloud firewall/security groups
  TLS/mTLS between services
  ServiceAccount/workload identity
  CNI flow logs + DNS + SIEM
~~~

Yêu cầu nhóm học viên:

1. Vẽ **một Pod** có hai containers: app và telemetry-sidecar. Chỉ rõ Pod IP, localhost, port 8080 và sidecar port 15000.
2. Vẽ **hai Pods cùng node** và **hai Pods khác node**; mô tả data path trong overlay và trong VPC-native CNI.
3. Giải thích vì sao **Pod IP có thể đổi sau rollout** và client vẫn có thể gọi API qua Service.
4. Lập bảng Pod/Service/Node/external IP và DNS names, không dùng địa chỉ nào làm identity/cấp quyền.
5. Thiết kế **default-deny + allow** cho edge→web, web→app, app→data, app→DNS; không mở web→database.
6. Giải thích quy tắc **egress nguồn + ingress đích** cùng phải cho phép khi hai hướng chịu isolation.
7. Tạo một negative test có **namespaceSelector + podSelector** dạng AND và một case OR sai cấu trúc.
8. Đánh giá rủi ro **hostNetwork/hostPort/secondary network** và yêu cầu admission/RBAC tương ứng.
9. Kiểm tra đường **Pod→on-prem** qua cloud VPN: nguồn IP trước/sau NAT, route trả lời, firewall và TLS.
10. Thiết kế monitoring gắn Pod UID với Pod IP theo event-time để tránh quy nhầm Pod sau khi IP tái sử dụng.
11. Đề xuất phương án **IPAM capacity** khi scale từ 100 tới 5.000 Pods mà không overlap VPC peers/other clusters.
12. Viết kế hoạch rollout NetworkPolicy có **allow DNS, identity, positive/negative tests, rollback**.
13. Phân biệt một request HTTP 403 với TCP timeout và TLS hostname verification error.
14. Chỉ ra điểm đặt WAF/Ingress/Gateway và biện pháp chặn **direct Pod IP bypass** vào sensitive API.
15. Xây checklist chứng minh CNI thật sự enforce policy ở cả IPv4/IPv6 và paths khác node.

**Tiêu chí đạt:** mô hình đúng “một Pod network namespace mặc định”, không coi mỗi container có IP riêng, không cố định Pod IP trong client, hiểu Service abstraction, policy selectors chính xác, và chứng minh deny/allow tại đúng endpoint với CNI hiện dùng.

### 19.2. Câu hỏi tự kiểm tra

**Câu 1.** Trong một Pod Kubernetes thông thường có ba containers, có mặc định ba Pod IP khác nhau không?

*Gợi ý:* Không. Những containers chia sẻ Pod network namespace và primary Pod IP; multi-interface/dual-stack là các ngoại lệ cần xem theo thiết kế.

**Câu 2.** Vì sao container A có thể gọi container B bằng 127.0.0.1?

*Gợi ý:* Chúng chia sẻ network namespace và loopback trong cùng Pod.

**Câu 3.** Pod Q có dùng 127.0.0.1 để gọi API ở Pod P được không?

*Gợi ý:* Không. Loopback của Q là của Q; cần Pod IP/Service name của P và route/policy phù hợp.

**Câu 4.** Hai containers trong cùng Pod có thể cùng bind 0.0.0.0:8080/TCP không?

*Gợi ý:* Thông thường không, vì dùng cùng network namespace/port space; có ngoại lệ socket-level sharing được thiết kế riêng.

**Câu 5.** containerPort trong manifest có tự mở listener và cho firewall allow không?

*Gợi ý:* Không. Nó là metadata; tiến trình phải bind, policy/Service/network route vẫn quyết định reachability.

**Câu 6.** Một app chỉ bind 127.0.0.1:8080 có thể được Pod khác gọi qua Pod IP không?

*Gợi ý:* Không theo thông lệ IP binding; muốn nhận traffic qua Pod IP phải bind interface/address phù hợp và có policy.

**Câu 7.** Pod IP có giữ nguyên sau Deployment rolling update không?

*Gợi ý:* Không đảm bảo. Pod mới có thể nhận IP khác; dùng Service/DNS/EndpointSlice.

**Câu 8.** CNI và IPAM khác nhau ở đâu?

*Gợi ý:* CNI tích hợp cấu hình mạng/dataplane cho sandbox; IPAM phụ trách phân bổ/thu hồi địa chỉ, có thể là plugin/bộ phận của CNI.

**Câu 9.** Kubernetes scheduler có trực tiếp chọn Pod IP không?

*Gợi ý:* Không theo mô hình chung. Scheduler chọn node, runtime/CNI/IPAM thiết lập network theo thiết kế.

**Câu 10.** Vì sao hai Pods cùng node vẫn có IP khác nhau?

*Gợi ý:* Chúng là hai network namespaces/Pod endpoints khác nhau, dù cùng Node IP.

**Câu 11.** Vì sao Pod-to-Pod khác node cần overlay hoặc routing thích hợp?

*Gợi ý:* Node/dataplane phải biết next hop tới Pod IP/CIDR ở node khác; API server không làm data path proxy mặc định.

**Câu 12.** VXLAN hoặc Geneve overlay có tự mã hóa payload như TLS không?

*Gợi ý:* Không. Encapsulation khác encryption; cần TLS/mTLS hoặc CNI encryption được thiết kế.

**Câu 13.** Vì sao overlay MTU không phù hợp có thể khiến request lớn lỗi nhưng request nhỏ chạy?

*Gợi ý:* Tunnel overhead giảm payload MTU, PMTU/MSS/ICMP có thể bị sai hoặc chặn.

**Câu 14.** Pod IP, ClusterIP và Node IP khác nhau như thế nào?

*Gợi ý:* Pod IP thuộc Pod endpoint, Node IP thuộc máy, ClusterIP là Service virtual address tới backends.

**Câu 15.** ClusterIP không xuất hiện trong giao diện eth0 của Pod có nhất thiết sai không?

*Gợi ý:* Không. Service VIP thường được hiện thực trong dataplane, không phải Pod interface IP.

**Câu 16.** Ping ClusterIP fail có chứng minh Service HTTP fail không?

*Gợi ý:* Không. Cần test đúng TCP/UDP/HTTP port và Service backends; ICMP không phải Service health contract.

**Câu 17.** EndpointSlice giúp giải quyết vấn đề gì?

*Gợi ý:* Biểu diễn tập backend endpoints và trạng thái, cho phép Service/discovery/dataplane cập nhật khi Pods thay.

**Câu 18.** Headless Service có nhất thiết có một ClusterIP virtual address không?

*Gợi ý:* Không. ClusterIP None, DNS/discovery hướng tới endpoints theo semantics.

**Câu 19.** Namespace khác nhau có tự tạo firewall giữa Pods không?

*Gợi ý:* Không. Cần NetworkPolicy hoặc controls khác được thực thi.

**Câu 20.** NetworkPolicy default-deny ingress có làm egress bị chặn tự động không?

*Gợi ý:* Không. Ingress/Egress isolation độc lập theo policyTypes và những policy chọn Pod.

**Câu 21.** Một source Pod bị egress-deny, destination Pod có ingress-allow: flow có thành công không?

*Gợi ý:* Không nếu source chưa được allow egress tới đích/port; khi cả hai hướng bị isolation, cả hai phải cho phép.

**Câu 22.** NetworkPolicy chuẩn có “deny rule cuối cùng thắng” không?

*Gợi ý:* Không. Policies là additive allowlist; các allow rules hợp lại.

**Câu 23.** Trong from rule, namespaceSelector và podSelector nằm trong cùng list item nghĩa gì?

*Gợi ý:* AND: Pod phải khớp label và thuộc namespace cũng khớp selector.

**Câu 24.** Tách namespaceSelector và podSelector thành hai list items nghĩa gì?

*Gợi ý:* OR: có thể mở rộng nguồn ngoài ý định.

**Câu 25.** Một Pod thay label để khớp NetworkPolicy có được coi là xác thực service identity không?

*Gợi ý:* Không. Label không phải credential; cần RBAC/admission và mTLS/API authentication.

**Câu 26.** Vì sao default-deny egress có thể làm DNS mất hoạt động?

*Gợi ý:* DNS traffic ra CoreDNS/NodeLocal DNS không nằm trong allowlist; phải biết resolver thực và cho phép đúng path.

**Câu 27.** NetworkPolicy ipBlock có luôn nhìn thấy cùng IP trước và sau Service DNAT/SNAT không?

*Gợi ý:* Không được đảm bảo thống nhất trên mọi CNI; test path thật và không dùng Pod IP tĩnh thay workload selectors.

**Câu 28.** hostNetwork Pod có IP riêng hoàn toàn tách node như Pod thường không?

*Gợi ý:* Không. Nó dùng host network namespace, có thể thấy Node IP/ports; network security behavior khác theo CNI.

**Câu 29.** Một dual-stack Pod có thể có hơn một IP không?

*Gợi ý:* Có, thường một IPv4 và một IPv6 trên primary network khi cluster hỗ trợ.

**Câu 30.** Một Pod dùng thêm net1 qua Multus có mặc định được bảo vệ bởi NetworkPolicy trên eth0 không?

*Gợi ý:* Không giả định. Phải kiểm chứng enforcement trên secondary interface/plugin.

**Câu 31.** Khi Pod egress qua Internet, external API có nhất thiết thấy Pod IP làm source không?

*Gợi ý:* Không. SNAT/Node IP/NAT gateway/egress gateway có thể đổi source.

**Câu 32.** Cloud VPC peering có tự cho Pod IP reachable từ peer network không?

*Gợi ý:* Tùy VPC-native/overlay, routes/firewall, NAT và CNI; peering không tự cấp application authorization.

**Câu 33.** Vì sao một flow log chỉ có Pod IP chưa đủ xác định workload quá khứ?

*Gợi ý:* Pod IP có thể tái sử dụng; cần Pod UID, thời gian IPAM allocation, namespace/Node và event_time.

**Câu 34.** Nếu Pod thấy HTTP 403, có nên mở thêm NetworkPolicy không?

*Gợi ý:* Không vội. HTTP response có thể do WAF/API authorization sau khi network/TLS thành công.

**Câu 35.** Khi NetworkPolicy YAML đúng nhưng traffic không bị chặn, bước đầu cần xác minh gì?

*Gợi ý:* CNI có hỗ trợ/enforce policy không, selectors khớp không, có allow policy khác, hostNetwork/NAT/secondary paths không.

### 19.3. Bài tập phân tích sự kiện giả lập

Một namespace app vừa áp policy. Nhóm NOC nhận logs:

~~~text
09:00:00Z  Pod backend-a created, podIP=10.244.1.12, UID=uid-a
09:00:05Z  Service orders-api updated EndpointSlice -> backend-a
09:01:00Z  frontend (role=client) -> backend-a TCP/8080: allow
09:01:01Z  outsider (role=unknown) -> backend-a TCP/8080: deny
09:02:00Z  Pod backend-a deleted, IP 10.244.1.12 released
09:03:00Z  Pod backend-b created, podIP=10.244.1.12, UID=uid-b
09:03:05Z  Service orders-api updated EndpointSlice -> backend-b
09:04:00Z  frontend -> orders-api Service: HTTP 403 (app-level)
09:05:00Z  NodeLocal DNSCache unavailable for one node
~~~

Hãy trả lời:

1. Vì sao cùng 10.244.1.12 xuất hiện ở hai Pods mà chưa thể kết luận IPAM collision?
2. Flow tại 09:01 thuộc Pod UID nào, còn Pod tại 09:03 là UID nào?
3. NetworkPolicy ingress có vẻ đã hoạt động đúng trong 09:01 không? Bằng chứng nào còn cần?
4. HTTP 403 lúc 09:04 có nhất thiết do network policy không?
5. Sự cố DNS ở 09:05 có thể làm client thấy lỗi gì, dù backend IP còn route được?
6. Nếu service traffic qua ClusterIP lỗi sau Pod replacement nhưng direct Pod IP đúng, nên xem những gì?
7. Làm sao đảm bảo permission của backend-a không mặc nhiên bị gán sang backend-b chỉ vì IP giống nhau?

**Đáp án định hướng:** Pod IP có thể tái sử dụng **sau khi IP của Pod cũ được giải phóng**; UID/time và workload labels/identity phải được phân biệt. Allow/deny lúc 09:01 chứng minh một phần enforcement nếu CNI log đúng, nhưng cần xem policy selectors, source egress và negative coverage. HTTP 403 là tín hiệu application/gateway authorization, không phải mặc nhiên network policy. DNS lỗi có thể làm Service name resolution fail; EndpointSlice và dataplane cũng cần được kiểm tra khi Pod thay.

## 20. Tổng kết

- **Pod là đơn vị mạng cơ bản** trong Kubernetes thông thường. Nhiều containers **cùng Pod** chia sẻ network namespace, địa chỉ IP, loopback và cổng TCP/UDP; **Pod khác** có địa chỉ/network namespace riêng.
- “**Mỗi Pod một địa chỉ**” là mô hình đơn giản hóa: dual-stack có thể có IPv4 + IPv6, secondary networks có thêm IP, và hostNetwork dùng network của node. Không hiểu nó thành một quy tắc tuyệt đối trong mọi cấu hình.
- **Pod IP không bền vững như danh tính ứng dụng**: rollout, rescheduling hoặc sandbox lifecycle có thể làm IP thay; **Service DNS/ClusterIP/EndpointSlice** giữ điểm truy cập logic ổn định hơn.
- **CNI và IPAM** phối hợp tạo network sandbox, cấp IP/routes và kết nối Pod-to-Pod. Cross-node traffic có thể đi **overlay, routed underlay, cloud VPC-native hoặc eBPF dataplane** tùy sản phẩm.
- **Overlay encapsulation không mặc định mã hóa**, và Pod có IP private không tự bảo đảm không reachable từ mạng peering/VPN hay Internet sau routing/firewall.
- **Service, DNS, Ingress/Gateway và NAT** giải quyết service discovery/translation/exposure; chúng **không tự thay thế NetworkPolicy hay application authorization**.
- **NetworkPolicy chuẩn** là **additive allowlist** theo Pod/namespace selectors và Ingress/Egress directions; không tự cung cấp deny rule có thứ tự, L7 WAF, TLS/mTLS hoặc host policy đầy đủ trên mọi CNI.
- **Default-deny** chỉ có tác dụng khi CNI thực thi; cần mở các dependencies đúng scope như DNS/metrics/API và thử cả allow lẫn deny. **Source egress + destination ingress** đều quan trọng.
- **hostNetwork, secondary network interfaces, NAT, dual-stack và direct Pod IP traffic** là các đường có thể vượt ngoài những giả định policy đơn giản; phải kiểm tra bằng traffic thật và security controls tương ứng.
- **Identity, mTLS, RBAC, admission, Pod Security và cloud IAM** bổ trợ network controls; không xem Pod IP hoặc label như bằng chứng danh tính đã xác thực.
- **Observability tốt** cần CNI/flow, IPAM, DNS, Service/EndpointSlice, cloud routing và application audit, gắn với **Pod UID và event-time** để tránh quy nhầm IP tái sử dụng.
- Mục tiêu bảo mật không chỉ là cấp được IP cho mọi Pod mà còn **biết Pod nào có thể kết nối tới service nào, trên cổng nào, qua đường nào, với danh tính và quyền gì**, và có bằng chứng khi một kết nối phải bị từ chối.
