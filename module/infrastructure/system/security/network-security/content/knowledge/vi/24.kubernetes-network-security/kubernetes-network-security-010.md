# CNI plugin và ảnh hưởng đến chính sách mạng

Trong Kubernetes, **Container Network Interface (CNI)** là một đặc tả giao diện giữa runtime/orchestrator và các plugin cấu hình mạng cho workload. Ở cấp thực hành, CNI cùng các thành phần mạng liên quan quyết định **Pod có interface và địa chỉ IP như thế nào, có đường đi tới Pod khác hay không, dùng overlay hay định tuyến trực tiếp**, và trong nhiều giải pháp còn hỗ trợ **thực thi chính sách mạng**. Tuy nhiên, **đặc tả CNI tự nó không định nghĩa hoặc bảo đảm việc Kubernetes NetworkPolicy được thực thi**.

Sự khác biệt này rất quan trọng. Một cluster có Pod-to-Pod connectivity hoạt động bình thường vẫn có thể **không thực thi NetworkPolicy** nếu giải pháp mạng không cung cấp policy engine tương ứng hoặc policy chưa được áp dụng đúng. Ngược lại, cluster dùng CNI có hỗ trợ NetworkPolicy vẫn có thể bị truy cập ngoài ý định do **selector quá rộng, đường hostNetwork/NodePort, NAT, ingress/egress khác luồng đã xét, hoặc policy mở cho DNS mà chưa chặn đích ứng dụng**.

Ví dụ, nhóm bảo mật muốn chỉ các Pod có nhãn **app=checkout** trong namespace **shop** được gọi **orders-api** tại namespace **payments** qua TCP 8443. Một bản YAML NetworkPolicy đúng cú pháp chưa chứng minh được ranh giới ấy. Cần xác minh **CNI/policy agent thực thi thật, packet path đi qua điểm enforcement, selector chọn đúng Pods và các đường alternate ingress/egress đều được kiểm thử**.

Trong chương **Bảo mật mạng Kubernetes** của module **SECURITY_NETWORK_SECURITY**, chủ đề này kết nối với phân đoạn mạng, cloud firewall, VPN/hybrid routing, TLS/mTLS, DNS, IDS/IPS, kiểm soát dịch vụ và quan sát xâm nhập. Nội dung tập trung vào cách hiểu **datapath** và kiểm soát quyền kết nối, không chỉ cách viết YAML.

> **Nguyên tắc:** **Pod có IP và kết nối được** là năng lực mạng; **NetworkPolicy mô tả luồng được phép**; **CNI/network dataplane thực thi theo khả năng thực tế**; còn **TLS, định danh workload và authorization ứng dụng** kiểm tra nguồn, đích và quyền dữ liệu. Không dùng một lớp để thay thế lớp khác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **CNI specification, CNI plugin, IPAM, network namespace, kubelet/CRI** và các thành phần mạng trong Pod lifecycle.
2. Phân biệt **Pod networking**, **Service networking**, **DNS discovery** và **Kubernetes NetworkPolicy**.
3. Nhận diện các mô hình **overlay VXLAN/Geneve, direct routing/BGP, cloud VPC-native Pod IP**, cũng như vai trò của **iptables, nftables, eBPF và Open vSwitch** trong triển khai.
4. Hiểu điều kiện để **NetworkPolicy thực sự được enforce**; lý giải tại sao một hệ thống chỉ cung cấp connectivity không đồng nghĩa có network isolation.
5. Đọc đúng semantics của **podSelector, namespaceSelector, ipBlock, ingress, egress, protocol/port và default deny**, đặc biệt phép **AND/OR** giữa peers và hợp của các policies.
6. Phân tích ảnh hưởng của **Service VIP, kube-proxy hoặc dataplane thay thế, DNAT/SNAT, source IP preservation, hostNetwork, NodePort, LoadBalancer, Ingress**.
7. Thiết kế chính sách cho **DNS egress, cross-namespace service access, external API, database và quản trị**, gồm IPv4/IPv6.
8. Phân biệt **standard Kubernetes NetworkPolicy** với các cơ chế mở rộng như FQDN-aware policies, L7 HTTP rules, global policies và service identity.
9. Chẩn đoán từ **Pod → Service → endpoint → node → cloud firewall** bằng lệnh quan sát được cấp quyền và log ở đúng điểm.
10. Xây dựng **ma trận kiểm thử positive/negative**, quy trình rollout, kiểm soát thay đổi và runbook khi thay CNI hoặc bật default deny.

## 2. CNI là gì và không phải là gì?

### 2.1. CNI specification

**CNI** mô tả cách một runtime gọi plugin mạng để cấu hình hoặc dọn mạng cho một workload: cấp interface, địa chỉ, đường đi và những thông tin tương ứng theo khả năng plugin. Những thao tác khái niệm thường nhắc tới là **ADD**, **DEL** và **CHECK** ở các phiên bản/hỗ trợ thích hợp.

CNI **không phải một công cụ bảo mật duy nhất** và cũng **không bắt buộc phải cung cấp Kubernetes NetworkPolicy**. Một triển khai thường gồm plugin dùng trong quá trình tạo Pod, **IP Address Management (IPAM)** và daemon/agent/controller để quản lý route, policy và trạng thái dataplane về sau.

### 2.2. Kubelet, CRI và quá trình tạo Pod

Ở mức khái niệm:

1. Scheduler chỉ định Pod tới một node.
2. **Kubelet** yêu cầu container runtime qua **Container Runtime Interface (CRI)** thiết lập Pod sandbox.
3. Runtime và stack mạng gọi thành phần CNI thích hợp để cấu hình interface/IP/route theo kiến trúc.
4. CNI/IPAM có thể cung cấp Pod IP và đường kết nối node/cluster.
5. Các agent/controller của giải pháp mạng tiếp tục duy trì **service routing, policy enforcement, observability** nếu có hỗ trợ.
6. Container trong cùng một Pod thường chia sẻ **network namespace và Pod IP**, dù có nhiều container ứng dụng hoặc sidecar.

Sơ đồ chỉ mang tính kiến trúc; thứ tự chính xác và thành phần thực thi phụ thuộc runtime, plugin, phiên bản Kubernetes và môi trường managed cluster.

~~~mermaid
flowchart TD
    K["Kubelet / CRI"] --> S["Pod sandbox và network namespace"]
    S --> C["CNI plugin: ADD / network setup"]
    C --> IP["IPAM: Pod IP + routes/interfaces"]
    IP --> DP["Dataplane: veth/overlay/direct routing"]
    DP --> Q{"Policy engine có hoạt động?"}
    Q -->|Có| P["Enforce NetworkPolicy theo khả năng"]
    Q -->|Không| N["Connectivity có thể hoạt động nhưng không có K8s policy enforcement"]
    P --> APP["Pod ↔ Pod/Service/External"]
    N --> APP
    CTRL["CNI agents / controllers"] -. "Program routes, service, policy" .-> DP
~~~

### 2.3. CNI so với Kubernetes NetworkPolicy

| Thành phần | Quyết định/chức năng chính | Điều không được suy ra |
| --- | --- | --- |
| **CNI specification** | Giao diện cấu hình mạng container | Không bảo đảm policy engine |
| **CNI/IPAM plugin** | Interface, địa chỉ và những route cơ bản | Không tự cấp quyền API |
| **CNI dataplane / networking agents** | Chuyển packet, NAT/tunnel, có thể xử lý Service/policy | Không phải mọi dataplane có cùng tính năng |
| **Kubernetes NetworkPolicy API** | Diễn tả kết nối L3/L4 được phép giữa Pods và các peers | Không tự thực thi nếu không có engine tương ứng |
| **Admission/RBAC/policy-as-code** | Kiểm soát ai có thể tạo/sửa manifests và các ràng buộc quản trị | Không thay runtime enforcement |
| **TLS/mTLS/service mesh** | Xác minh endpoint/service identity, có thể áp L7 authorization | Không thay mọi network isolation |
| **Cloud security group / network firewall** | Giới hạn traffic ở các điểm cloud/network | Không nhất thiết thấy pod identity hoặc các luồng overlay |

### 2.4. Pod IP không phải danh tính đáng tin lâu dài

Pod có thể được tạo lại và nhận IP khác. Một policy chỉ gắn quyền với **Pod IP tĩnh** dễ bị lỗi khi scale, restart hoặc reschedule. Kubernetes NetworkPolicy thường dùng **labels/selectors** để theo workload; ngược lại phải bảo vệ **quyền tạo/sửa labels và namespace**, nếu không workload không đáng tin có thể tự nhận thuộc nhóm được phép.

## 3. Các tầng trên đường đi của một packet

Một request **checkout → orders-api** có thể gặp:

~~~mermaid
flowchart LR
    A["checkout Pod<br/>namespace shop"] -->|"TCP 8443"| V["Service VIP / DNS-resolved address"]
    V -->|"Service LB / NAT / eBPF"| E["orders-api endpoint Pod"]
    A -. "Egress policy" .-> PE["CNI policy dataplane"]
    PE -. "Ingress policy" .-> E
    E --> APP["TLS / API authentication & authorization"]
    APP --> DATA[("Business data")]
~~~

Thực tế một packet có thể đi qua veth pair, Linux bridge, routing table, tunnel, node eBPF hooks, OVS flows, host firewall và cloud virtual network. **Thứ tự NAT và điểm đánh giá policy không giống nhau trong mọi CNI.**

### 3.1. Phân biệt năm hoạt động

| Hoạt động | Câu hỏi chính | Ví dụ kiểm tra |
| --- | --- | --- |
| **DNS** | Tên Service trả IP nào? | A/AAAA Service DNS |
| **Service discovery** | Service có endpoints nào? | Service, EndpointSlice, readiness |
| **Routing/NAT** | Packet tới endpoint qua đường nào? | ClusterIP, node routing, kube-proxy/eBPF |
| **Network policy** | Nguồn có được phép nối tới đích/port không? | CNI policy agent, flow verdict |
| **Application security** | Caller có quyền thao tác dữ liệu không? | TLS identity, JWT, RBAC/nghiệp vụ |

**DNS thành công nhưng TCP timeout** có thể là lỗi network policy hoặc dataplane; **TCP thành công nhưng HTTP 403** thường là một quyết định ở tầng ứng dụng/gateway. Không trộn những lỗi này thành “CNI hỏng”.

## 4. Network namespace, veth và Pod networking

### 4.1. Network namespace

Pod thường có một **network namespace** với các interface, địa chỉ, bảng định tuyến và loopback của Pod. Các containers trong cùng Pod chia sẻ không gian mạng, nên một sidecar và ứng dụng có thể trao đổi qua **localhost**. Hai Pods khác nhau không mặc nhiên chia sẻ loopback.

**NetworkPolicy chuẩn chọn Pod**, không phân biệt hai containers thuộc cùng một Pod ở cổng localhost theo cách một số người mong muốn. Nếu cần cô lập hai thành phần có mức tin cậy khác nhau, việc đặt chúng trong cùng Pod đòi hỏi đánh giá riêng.

### 4.2. veth pair và packet path

Nhiều CNI dùng **virtual Ethernet pair (veth)** để nối namespace Pod với node/bridge hoặc dataplane tương ứng. Một đầu của veth thuộc Pod, đầu còn lại thuộc host/network stack. Nhưng **không phải mọi CNI, mode, runtime dùng cùng một kiến trúc veth/bridge**.

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    NS1["Pod A netns"] --> VA["veth/attachment A"]
    VA --> NODE["Node dataplane<br/>routing/bridge/eBPF/OVS"]
    NODE --> TUN["Overlay tunnel hoặc underlay"]
    TUN --> N2["Node B dataplane"]
    N2 --> VB["veth/attachment B"]
    VB --> NS2["Pod B netns"]
~~~

### 4.3. IPAM

**IPAM** cấp phát và quản lý Pod IP theo phạm vi mạng đã thiết kế. Tùy CNI, IP có thể đến từ:

- Pool địa chỉ riêng của cluster/CNI.
- CIDR cấp cho node hoặc overlay.
- Dải địa chỉ mạng cloud/VPC, có thể gắn với các interface của node.
- Cơ chế phụ trợ IPAM plugin hoặc controller.

Sai IPAM có thể gây **trùng địa chỉ, thiếu IP khi scale, route blackhole**, khiến kết nối lỗi dù NetworkPolicy cho phép. Cần phân biệt **allocation capacity** với lỗi security rule.

### 4.4. Tác động an ninh

- Pod có thể nhận IP khác sau khi recreate: **đừng hardcode allowlist theo Pod IP** nếu không cần thiết.
- Một Pod có nhiều containers cùng namespace: **localhost không phải security boundary giữa containers trong Pod**.
- Dải Pod CIDR có thể **không được định tuyến ra ngoài cluster** nếu dùng overlay/NAT.
- Cần xác minh **source IP thực sự ở enforcement point**, đặc biệt khi traffic qua SNAT, gateway hoặc cloud load balancer.

## 5. Overlay và underlay/direct routing

### 5.1. Overlay

Ở mô hình **overlay**, gói tin Pod-to-Pod có thể được đóng gói trong tunnel như **VXLAN** hoặc **Geneve** để đi qua mạng giữa các nodes. Mạng underlay thấy packet giữa nodes/tunnel endpoints, trong khi địa chỉ Pod gốc nằm bên trong gói được đóng gói.

Hệ quả:

- Cloud/network firewall ở underlay có thể chỉ thấy **node IP + tunnel protocol**, không thấy trực tiếp Pod IP hoặc service port gốc nếu không có cơ chế giải mã/quan sát nội bộ.
- MTU giảm do overhead tunneling; fragmentation/PMTU issues có thể gây lỗi lạ.
- Muốn áp policy theo Pod/namespace thường cần enforce ở **node/CNI dataplane** nơi có đủ ngữ cảnh.
- Một rule ở cloud firewall chỉ giới hạn tunnel giữa nodes **không thay** isolation của Pods bên trong.

### 5.2. Direct routing / underlay-routable Pod IP

Trong **direct routing**, mạng giữa nodes có route để chuyển gói theo Pod CIDR/IP mà không cần cùng kiểu tunnel overlay. Một số CNI có thể dùng **BGP** hoặc route programming, hoặc dùng địa chỉ từ cloud VPC/VNet.

Lợi ích có thể gồm giảm overhead encapsulation hoặc tăng khả năng quan sát Pod IP ở một số điểm. Nhưng **route leak, mất route khi node thay đổi, CIDR overlap, cloud quotas và chính sách firewall** vẫn cần được đánh giá.

### 5.3. So sánh ở góc nhìn security

| Đặc tính | Overlay/tunnel | Direct routing / VPC-native |
| --- | --- | --- |
| Địa chỉ Pod trên underlay | Thường nằm trong gói tunnel | Có thể nhìn thấy/định tuyến trực tiếp |
| Cloud firewall quan sát Pod flow | Có thể chỉ thấy tunnel/node traffic | Có thể thấy Pod IP, phụ thuộc NAT/điểm quan sát |
| Policy enforcement tối ưu | CNI dataplane gần Pod | CNI và/hoặc cloud-native controls phù hợp |
| Routing dependencies | Tunnel connectivity, nodes, MTU | Pod CIDR routes, peering, cloud IP/ENI |
| Điểm thất bại | Tunnel/MTU/encapsulation, CNI agent | Route propagation, IP exhaustion, cloud ACL |
| Có NetworkPolicy mặc định? | **Không suy ra** từ overlay | **Không suy ra** từ direct routing |

**Overlay không mặc định kém an toàn hơn direct routing, và direct routing không tự cấp quyền tốt hơn.** Kiểm soát hiệu quả phụ thuộc policy engine, mô hình đe dọa và bằng chứng enforcement.

## 6. Những công nghệ thực thi: iptables, nftables, eBPF, OVS

Một CNI hoặc policy engine có thể dùng các cơ chế kernel/network khác nhau:

| Công nghệ | Vai trò phổ biến | Lưu ý khi điều tra |
| --- | --- | --- |
| **iptables** | Lọc, NAT, connection tracking và Service/policy rules ở một số stack | Chain/rule ownership phức tạp, có thể dùng backend nftables |
| **nftables** | Framework packet filtering/NAT của Linux | Quy tắc và thứ tự hooks cần hiểu theo deployment |
| **eBPF** | Chương trình trên các hooks phù hợp để xử lý forwarding, policy, observability | Không suy mọi eBPF dataplane có cùng L7/identity features |
| **Open vSwitch (OVS)** | Virtual switching và OpenFlow/flow tables | Cần đọc flow/action ở đúng bridge và pipeline |
| **Linux routing/conntrack** | Chuyển tiếp L3, quản lý trạng thái phiên | NAT, state timeout và asymmetric paths có thể thay verdict |

### 6.1. eBPF không đồng nghĩa tự động có bảo mật mạnh hơn

eBPF là một công nghệ cho phép tạo dataplane/observability theo cách cụ thể. Một giải pháp eBPF có thể hỗ trợ network policy hiệu quả hoặc những phần mở rộng sâu hơn, nhưng **các tính năng được bật và cách xử lý traffic** mới quyết định khả năng phòng vệ. Không dựa vào tên **eBPF** để kết luận mọi L7 rule, ingress/egress hoặc encryption đang hoạt động.

### 6.2. Policy có thể được thực thi ở nhiều điểm

Một plugin có thể đặt hook tại Pod veth, node network stack hoặc điểm forwarding khác. Nếu cần kiểm tra một packet **Service ClusterIP → endpoint**, phải biết **policy được áp trước hay sau DNAT** và engine nhận dạng service/backend ra sao.

**Không thể khẳng định chung rằng NetworkPolicy ipBlock luôn nhìn thấy IP gốc hoặc IP sau NAT**: Kubernetes lưu ý rằng hành vi liên quan rewriting và ipBlock có thể khác theo plugin/network implementation.

## 7. Ví dụ các họ CNI và khả năng policy

Tên giải pháp không phải bằng chứng cấu hình hiện tại. Bảng dưới chỉ giúp xác định những câu hỏi cần kiểm chứng:

| Giải pháp/kiểu CNI | Mô hình thường được biết đến | Câu hỏi quan trọng khi chọn |
| --- | --- | --- |
| **Flannel** | Chủ yếu cung cấp connectivity/overlay hoặc routing | Có policy engine khác phối hợp không? Không tự giả định Flannel một mình thực thi NetworkPolicy |
| **Calico** | Networking và network policy trên những dataplane/mode hỗ trợ | Đang dùng iptables hay eBPF? Standard vs extended policies nào được bật? |
| **Cilium** | eBPF-based dataplane, Kubernetes policies và một số mở rộng | Cilium policies, kube-proxy replacement, observability mode nào đang bật? |
| **Antrea** | OVS-based Kubernetes networking và network policies | Agent/controller, OVS flows và các policy extensions được hỗ trợ ra sao? |
| **OVN-Kubernetes** | OVN-based networking và network policy tích hợp theo môi trường | OVN ACL, route/NAT, namespace policy và platform integration ra sao? |
| **Cloud VPC-native CNI** | Pod IP được gắn với mạng cloud theo kiểu dịch vụ | Policy engine là thành phần nào, network rules áp tới Pod hay node, có quota/ENI constraints không? |

**Tính năng, giới hạn và cách cài đặt của từng sản phẩm thay đổi theo phiên bản và nhà cung cấp managed Kubernetes.** Khi triển khai cần tra đúng tài liệu của bản được sử dụng, không so sánh bằng tên thương mại hoặc giả định “có Kubernetes là có NetworkPolicy”.

### 7.1. CNI chaining và nhiều thành phần

Trong một số kiến trúc, plugin đảm nhiệm IP assignment/connectivity còn **một thành phần khác** cung cấp policy, observability hoặc network attachment phụ. Có thể dùng chaining hoặc nhiều interface theo cơ chế được hỗ trợ.

Đừng kết luận cluster không có policy chỉ vì CNI chính thiên về connectivity, cũng không kết luận có policy chỉ vì một policy controller đã được cài mà **agent/dataplane chưa sẵn sàng**.

## 8. Kubernetes NetworkPolicy API và điều kiện enforcement

**NetworkPolicy** là đối tượng Kubernetes dùng để mô tả traffic được phép cho Pods được chọn theo **ingress** và/hoặc **egress**. Nó là một policy L3/L4 với những trường chính như:

- **podSelector**: Pods trong namespace của chính NetworkPolicy.
- **policyTypes**: Ingress, Egress hoặc cả hai.
- **ingress.from**: những nguồn được phép đến Pods đã chọn.
- **egress.to**: những đích được phép từ Pods đã chọn.
- **ports**: protocol/port được cho phép theo quy tắc API.
- **namespaceSelector, podSelector, ipBlock** trong các peer selectors.

NetworkPolicy **không phải Kubernetes RBAC**: cho phép kết nối tới Pod không tự cấp quyền gọi API hay đọc dữ liệu. Và Kubernetes API server chấp nhận manifest **không bảo đảm dataplane thực thi được nó**.

### 8.1. CNI cần hỗ trợ và đang hoạt động

Để NetworkPolicy có tác dụng, phải có giải pháp mạng/policy controller **hỗ trợ enforcement** cho những policy được dùng. Các bước xác minh:

1. Xác định **CNI/policy implementation** ở cluster đang chạy.
2. Kiểm tra trạng thái agents/controllers và chính sách egress/ingress thực sự hỗ trợ.
3. Đảm bảo policy chọn đúng Pods theo labels/namespace.
4. Kiểm tra những luồng có thể không đi qua điểm enforcement: **hostNetwork, NodePort, external traffic, đặc điểm CNI/host**.
5. Thực hiện **positive và negative connectivity tests**, có log/flow verdict ở đúng lớp.

### 8.2. Union of policies

Các NetworkPolicies chuẩn **mang tính cộng dồn quyền allow** đối với traffic của Pods được chọn. Nếu nhiều policy cùng áp, một kết nối có thể được phép nếu thỏa một rule phù hợp theo semantics. Không có rule Kubernetes NetworkPolicy chuẩn dạng “deny ưu tiên cao” để ghi đè các allow khác.

**Muốn traffic từ Pod A tới Pod B thành công**, khi các Pods tương ứng bị cô lập theo chiều nào thì chiều đó phải có allow phù hợp: **egress phía A** và **ingress phía B** nếu hai phía đều bị isolation.

### 8.3. Isolation theo chiều

| Pod chịu policy | Ingress | Egress | Ý nghĩa |
| --- | --- | --- | --- |
| Không bị ingress-isolated | Mặc định không bị Kubernetes NetworkPolicy chuẩn giới hạn chiều ingress | Tùy egress policy | Vẫn có thể bị cloud firewall/host policy chặn |
| Ingress-isolated | Chỉ các ingress được phép bởi hợp rules | Không tự thay đổi egress nếu chưa cô lập | Không có rule ingress phù hợp thì drop theo enforcement |
| Egress-isolated | Không tự thay đổi ingress nếu chưa cô lập | Chỉ các egress được phép bởi hợp rules | DNS egress có thể mất nếu không cho phép |
| Isolated cả hai | Áp cả ingress rules | Áp cả egress rules | Cần thiết kế luồng trả lời và service dependencies phù hợp |

Đối với kết nối stateful, traffic phản hồi thường được xử lý theo connection tracking của dataplane; **không nên nhầm return traffic với việc cấp quyền mở một kết nối mới ngược chiều**.

## 9. Default deny và sự khác biệt giữa cấu hình với thực thi

### 9.1. Default deny chuẩn theo namespace

Ví dụ NetworkPolicy sau **chọn tất cả Pods trong namespace shop** và không khai báo bất kỳ ingress/egress allow rule nào:

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

Với engine thực thi đầy đủ Kubernetes NetworkPolicy, các Pods được chọn sẽ bị cô lập ở cả hai hướng theo semantics tương ứng, **ngoại trừ các luồng do NetworkPolicies khác cho phép và các trường hợp đặc biệt của network implementation**.

### 9.2. Default deny không bao giờ có nghĩa “không ai có thể chạm node”

Theo Kubernetes NetworkPolicy model, traffic **từ/đến node**, host networking và đặc điểm nền tảng có những quy tắc/sự khác nhau cần hiểu riêng. Không tự khẳng định một default-deny-all ở namespace đã:

- Khóa toàn bộ traffic giữa Pod và host/node.
- Chặn mọi truy cập từ Internet đi qua NodePort/LoadBalancer trong mọi CNI mode.
- Chặn localhost giữa containers trong cùng Pod.
- Chặn service-account API permissions hoặc truy cập Secret từ API server.
- Chặn lưu lượng ở các mạng phụ ngoài network interface do policy engine quản lý.

### 9.3. Test âm tính bắt buộc

Sau khi tạo policy, một Pod lab ngoài danh sách **phải không kết nối được** tới cổng bảo vệ, trong khi một Pod nằm trong danh sách **vẫn kết nối được**. Nếu cả hai đều kết nối được, cần kiểm tra **label selectors, policy aggregation, enforcement agent và packet path**, thay vì chỉ xác minh lệnh apply báo thành công.

## 10. Selector semantics: namespaceSelector, podSelector và AND/OR

Đây là một trong những nguồn sai sót phổ biến nhất khi viết NetworkPolicy.

### 10.1. podSelector ở đâu?

Trong **spec.podSelector** của NetworkPolicy, selector chọn **Pods mà chính sách áp dụng** trong **namespace chứa NetworkPolicy**. Trong một peer item thuộc **ingress.from** hoặc **egress.to**, podSelector chọn đối tượng đích/nguồn theo quy tắc kết hợp với namespaceSelector.

### 10.2. Hai selector cùng một peer item nghĩa là AND

Ví dụ:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: shop
    podSelector:
      matchLabels:
        app: checkout
~~~

Ý nghĩa là **chỉ các Pods có app=checkout thuộc các namespaces có label phù hợp**. Hai điều kiện nằm trong **cùng một item** của danh sách from nên được hiểu theo phép **AND**.

### 10.3. Hai peer items riêng nghĩa là OR

Ví dụ:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: shop
  - podSelector:
      matchLabels:
        app: checkout
~~~

Đây là **hai nguồn được phép độc lập**: tất cả Pods trong namespace được chọn **hoặc** Pods có app=checkout trong namespace của NetworkPolicy (theo semantics Pod-only selector). Nếu mong muốn chỉ checkout từ shop, cấu hình này có thể **mở rộng quyền ngoài dự định**.

### 10.4. Labels không tự là danh tính mật mã

Một attacker hoặc workload không được tin có thể khai thác policy theo label nếu họ có quyền tạo/sửa Pods hoặc namespace labels theo cách không được kiểm soát. Hệ thống cần **RBAC, admission policy, namespace ownership, policy-as-code** để bảo vệ nguồn nhãn được dùng cấp quyền. **NetworkPolicy không tự xác minh mTLS principal của Pod.**

### 10.5. Namespace label tồn tại hay không

Label **kubernetes.io/metadata.name** thường được Kubernetes cung cấp cho namespace ở những phiên bản thích hợp, nhưng vẫn nên kiểm tra version, labels thật và điều kiện trong môi trường. Nếu sử dụng label do nhóm tự quản lý như **environment=prod**, cần bảo vệ quyền thay label đó.

## 11. Policy ví dụ: chỉ checkout được gọi Orders API

Giả định lab:

- Namespace **shop** có client Pod **app=checkout**.
- Namespace **payments** có backend Pods **app=orders-api**.
- Orders API phục vụ **TCP 8443**, có TLS/authorization riêng.
- CNI thực sự enforce Kubernetes NetworkPolicy.

### 11.1. Ingress policy trên backend

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-from-approved-checkout
  namespace: payments
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
              kubernetes.io/metadata.name: shop
          podSelector:
            matchLabels:
              app: checkout
      ports:
        - protocol: TCP
          port: 8443
~~~

**Điều policy này làm:** đối với Pods app=orders-api trong payments, khai báo một luồng inbound được phép từ checkout Pods ở namespace shop vào TCP 8443 theo selectors.

**Điều nó không làm:** không tự chặn các luồng được **policy ingress khác** cho phép cùng Pods; không chặn egress của checkout; không bảo vệ dữ liệu theo user/tenant; không xác minh ingress/Service/TLS endpoint.

### 11.2. Egress policy của client

Nếu muốn hạn chế checkout chỉ gọi backend Orders trong các luồng ứng dụng tương ứng, áp policy egress ở namespace shop:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-to-orders
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: checkout
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: payments
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 8443
~~~

**Chú ý:** nếu checkout đã bị egress-isolated và DNS cũng bị chặn, **client có thể không resolve được Service name** dù policy cho kết nối TCP tới backend. Cần bổ sung **DNS egress** theo cơ chế cluster.

### 11.3. Hợp policies và ý nghĩa thực tế

Nếu tồn tại một policy khác chọn checkout và cho egress tới mọi destination trên TCP 8443, rule rộng ấy có thể tiếp tục cho traffic ngoài Orders. **Không có NetworkPolicy deny rule chuẩn với độ ưu tiên cao để “ghi đè” allow rộng đó.**

Muốn chắc chắn **chỉ Orders được phép**: rà soát **tất cả NetworkPolicies áp dụng**, cùng policy toàn cluster/extended policies của CNI nếu có. Positive test chỉ chứng minh kết nối hợp lệ; **negative test xác minh đích ngoài danh sách không tới được**.

## 12. DNS egress và NetworkPolicy

Khi áp egress isolation, Pod thường cần gửi DNS requests tới **cluster DNS, CoreDNS hoặc NodeLocal DNSCache**, tùy thiết kế.

### 12.1. Ví dụ policy DNS với giả định cụ thể

Đoạn YAML chọn checkout Pods trong namespace shop và cho phép UDP/TCP 53 đến DNS Pods ở namespace kube-system theo label giả định:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-to-cluster-dns
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: checkout
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

**Đây không phải cấu hình mặc định áp dụng được cho mọi cluster.** Cần kiểm tra đúng labels CoreDNS, địa chỉ DNS Service, cách CNI áp policy sau/before Service translation và có NodeLocal DNSCache hay không.

### 12.2. NodeLocal DNSCache

Nếu Pod dùng **NodeLocal DNSCache**, truy vấn có thể đi tới địa chỉ link-local trên node và không khớp selector DNS Pod ví dụ ở trên. Hành vi bảo vệ của CNI đối với **node-local endpoints** có thể khác với Pod-to-Pod communication. Cần test tại Pod thực tế, không chỉ nhìn manifest.

### 12.3. FQDN-aware egress không nằm trong NetworkPolicy chuẩn

Standard Kubernetes NetworkPolicy không có field portable kiểu **allowFQDN: api.partner.example.test**. Một số CNI hỗ trợ **mở rộng FQDN/domain policies** với DNS proxy/cache hoặc cơ chế riêng, nhưng phải hiểu:

- Domain/IP đổi theo TTL, CDN và resolver.
- Quy tắc với **direct IP, DNS over HTTPS/TLS, IPv6** khác nhau theo sản phẩm.
- Một hostname có thể trỏ nhiều IP; một IP có thể phục vụ nhiều domains.
- DNS answer không tự xác minh **TLS hostname/service identity**.

Một Pod được phép query DNS cho tên database **không đồng nghĩa được phép kết nối tới database**; network egress và database authentication phải riêng.

## 13. ipBlock và tính không chắc chắn do NAT

**ipBlock** trong Kubernetes NetworkPolicy cho phép biểu diễn một dải địa chỉ IP/CIDR, có thể dùng trường **except** để loại trừ dải con theo cú pháp hỗ trợ.

Ví dụ egress tới một dải **địa chỉ tài liệu** trong lab:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: batch-to-approved-lab-external-range
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: batch-report
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 203.0.113.0/24
            except:
              - 203.0.113.128/25
      ports:
        - protocol: TCP
          port: 443
~~~

Dải **203.0.113.0/24** dành cho tài liệu, không được hiểu là endpoint Internet có dịch vụ. Manifest minh họa cấu trúc allow CIDR và except; không dùng như policy cho production.

### 13.1. ipBlock thường phù hợp với CIDR ngoài cluster

Kubernetes khuyến nghị dùng **podSelector/namespaceSelector** cho Pods vì IP Pods động; ipBlock thường hữu ích với **dải địa chỉ ngoài cluster**. Có những implementation xử lý Pod CIDR/ipBlock khác nhau, nhất là khi dùng NAT/Service translation, do đó không dùng CIDR Pod làm thay danh tính Pod nếu chưa có bằng chứng.

### 13.2. Service IP và thứ tự DNAT

Giả sử Pod gọi Service VIP **10.96.0.20**, được dịch tới backend Pod **10.244.2.17**. Nếu policy chỉ allow một IP trong hai địa chỉ, **kết quả phụ thuộc điểm policy evaluation và cách dataplane nhận diện Service mapping**. Không khẳng định portable rằng ipBlock luôn được xét trước hoặc sau DNAT.

### 13.3. ExternalTrafficPolicy và địa chỉ nguồn

Với các Service types có external traffic, lựa chọn như **externalTrafficPolicy: Local/Cluster** có thể ảnh hưởng phân phối endpoints, địa chỉ nguồn được bảo toàn và đường packet/NAT theo môi trường. Những khác biệt này tác động đến **logging, IP-based allowlisting, rate limit và policy enforcement**; không dùng IP được backend quan sát làm bằng chứng user identity.

## 14. Service, kube-proxy và eBPF replacement

Kubernetes **Service** cung cấp điểm truy cập logic tới một hoặc nhiều endpoints. Với ClusterIP, lưu lượng đến Service VIP thường được xử lý bởi **kube-proxy** hoặc dataplane thay thế (ví dụ một CNI có cơ chế service load balancing dựa trên eBPF) theo cấu hình cluster.

### 14.1. Không đồng nhất Service proxy với CNI plugin

Một CNI có thể chỉ cung cấp Pod routing, để kube-proxy xử lý Service; CNI khác có thể tích hợp **Service routing/load balancing** và thay thế một số hoặc nhiều vai trò kube-proxy. **Không giả định kube-proxy chạy và lập trình iptables trên mọi cluster**.

### 14.2. Packet path trước/sau Service translation

~~~mermaid
flowchart TD
    C["Client Pod"] --> VIP["Service ClusterIP: 10.96.0.20:8443"]
    VIP --> MAP["Service dataplane / endpoint selection"]
    MAP --> DNAT["Pod endpoint: 10.244.2.17:8443"]
    DNAT --> POL["CNI ingress/egress policy verdict theo implementation"]
    POL --> A["Backend Pod"]
    C -. "Policy cũng có thể được đánh giá ở hook trước VIP translation" .-> POL
~~~

Ví dụ địa chỉ chỉ mang tính minh họa. Trong một số dataplanes, policy enforcement có thể xảy ra **trước** bước mapping hoặc tại nhiều hooks; sơ đồ không quy định thứ tự chung cho mọi sản phẩm.

### 14.3. EndpointSlice và readiness

Nếu Service không có **ready endpoints**, DNS vẫn có thể trả ClusterIP trong khi kết nối không tới một backend ready. Vì thế **DNS trả IP**, **Service VIP reachable**, **backend endpoint tồn tại**, **CNI policy allow** và **TLS/application ready** cần được xác minh riêng.

### 14.4. Hairpin và cùng node

**Hairpin traffic** có thể xuất hiện khi Pod gọi Service dẫn trở lại một Pod trên cùng node hoặc chính Pod đó. Kiểu chuyển packet phụ thuộc Service dataplane/NAT và CNI. Một lab chỉ thử **cross-node** có thể bỏ sót lỗi **same-node/hairpin** và ngược lại.

## 15. NodePort, LoadBalancer, Ingress và đường vào thực tế

Một client từ ngoài cluster có thể đi:

**Internet → Cloud LoadBalancer → NodePort/ingress controller → Service → backend Pod**.

Tùy platform, load balancer có thể gọi node hoặc Pod endpoint trực tiếp theo cấu hình. Điểm NetworkPolicy nhìn thấy và xử lý **source IP, destination IP và route** có thể khác.

### 15.1. Ingress object không phải network firewall

**Ingress/Gateway routing** định nghĩa cách một reverse proxy/gateway tiếp nhận và chuyển HTTP(S) request; nó không tự thay **NetworkPolicy giữa ingress controller và backend Pods**, cũng không tự cấp quyền API theo người dùng.

### 15.2. NodePort và truy cập ngoài đường gateway

Nếu một Service/NodePort hoặc load balancer khác được mở trực tiếp, client có thể có đường **bypass WAF/ingress controller**. Cần:

- Inventory các Service types/NodePorts/LoadBalancers.
- Cloud firewall/source restrictions tại điểm vào.
- Ingress NetworkPolicy ở backend theo **nguồn Pod/endpoint thực tế**.
- TLS/authn/authz tại gateway và backend.
- Negative tests từ các đường không được phép.

### 15.3. HostPort và hostNetwork

**hostPort/hostNetwork** đưa một số luồng gần hoặc trực tiếp vào node network namespace theo cơ chế runtime. Kubernetes NetworkPolicy chuẩn không mô tả được toàn bộ hành vi với traffic host trong mọi CNI. Việc dùng hostNetwork vì monitoring/ingress có thể cần **host firewall, CNI host policies, cloud security groups** hoặc controls khác.

### 15.4. Không tin X-Forwarded-For từ client

Sau nhiều proxy/load balancer, backend có thể thấy IP của proxy hoặc node do SNAT. **X-Forwarded-For** là metadata HTTP có thể bị giả mạo nếu không chuẩn hóa tại trusted proxy chain. Không dùng một header client tự khai làm bằng chứng source IP để bỏ NetworkPolicy hoặc cấp quyền admin.

## 16. Cross-node, same-node và host-to-Pod traffic

Nhiều lỗi policy chỉ xuất hiện trên một kiểu đường:

| Đường test | Thành phần có thể khác | Điều cần xác minh |
| --- | --- | --- |
| **Pod A → Pod B cùng node** | veth/bridge/eBPF/OVS local | Policy không bị bypass vì traffic không qua tunnel |
| **Pod A → Pod B khác node** | Routing, tunnel, cloud firewall, MTU | Route và enforcement nhất quán |
| **Pod → Service VIP → Pod khác** | Service translation, endpoint selection | Policy match đúng Pod, không nhầm VIP |
| **Pod → host/node** | Host network, local gateway | Có thể cần host-specific controls |
| **Host/node → Pod** | Node-originated traffic, monitoring, probes | Hành vi không luôn tương đương Pod-to-Pod |
| **Internet → LB/NodePort → Pod** | Cloud firewall, NAT, ingress proxy | Source identity và policy coverage |
| **Pod → Internet via NAT** | Egress routing, SNAT, proxy | CNI egress policy và cloud egress firewall |
| **Pod → private endpoint** | Cloud routing, DNS và IAM | Endpoint policy và application authorization |

### 16.1. Traffic tới/từ node đặc biệt thế nào?

Kubernetes NetworkPolicy mô tả rằng các Pods có thể giao tiếp với **node trên đó chúng chạy** theo những semantics nhất định; những traffic host-related khác có thể phụ thuộc CNI. Đây là lý do **default-deny không nên được xem là host isolation hoàn toàn**.

### 16.2. Liveness/readiness probes

Kubelet thường phát những **liveness/readiness/startup probes** từ node tới Pod. Cần kiểm tra cách CNI nhận diện và cho luồng này, tránh thiết kế policy làm hỏng health checks trong một số implementations. Ngược lại, một endpoint health trả 200 **không chứng minh Pod đã được cấp đúng quyền ứng dụng**.

## 17. IPv4, IPv6 và dual-stack CNI policy

Kubernetes có thể triển khai **IPv4-only, IPv6-only hoặc dual-stack** tùy cluster và CNI. Hai address families có route, firewall và Service behavior khác nhau, cần kiểm thử riêng.

### 17.1. Những câu hỏi chính

1. Node và Pod CIDRs có IPv4, IPv6 hay cả hai?
2. Service có IP families nào và DNS trả **A/AAAA** nào?
3. CNI mode đang dùng có enforce NetworkPolicy cho **IPv6** không?
4. CNI/cloud firewall có route tới **::/0** hoặc external IPv6 theo thiết kế không?
5. ipBlock rules có chấp nhận **IPv6 CIDR** và kết quả exclude đúng không?
6. Managed load balancer/Ingress có public IPv6 listener tạo đường vào mới không?
7. Observability có log verdict cho IPv6 và tương quan được với IPv4 không?

### 17.2. Ví dụ về sai lệch policy

Workload được cấu hình chặn egress tới những external IPv4 destinations nhưng ứng dụng resolve AAAA và kết nối bằng IPv6 qua một đường chưa kiểm soát. Nếu kiến trúc cho phép dual-stack, **không suy IPv4 restrictions tự chuyển sang IPv6**.

### 17.3. Chỉ kiểm tra IPv4 chưa đủ

Một negative test thất bại trên IPv4 có thể cho cảm giác an toàn, trong khi IPv6 hoặc ingress path khác vẫn cho phép. Test matrix phải tách **A/AAAA, protocol, routes, network policy và cloud firewall** cho từng address family được bật.

## 18. Đường đi cloud-native và giới hạn cloud firewall

Trong managed Kubernetes, Pod networking có thể gắn sâu với **VPC/VNet, cloud NIC/ENI, IP pool hoặc cloud-native routing**. Khi đó:

- Cloud firewall có thể chỉ áp ở **node interface/security group** hoặc có tính năng gắn riêng theo Pod tùy nền tảng.
- Node SNAT/Pod IP translation thay đổi địa chỉ nguồn được cloud firewall nhìn thấy.
- Load balancer có thể điều phối tới nodes hoặc Pod IP trực tiếp theo loại Service và controller.
- Những network policy của Kubernetes có thể cùng tồn tại với **cloud firewall, subnet ACL, route rules và org-level policies**.

### 18.1. AWS/Azure/GKE và những tên sản phẩm

Những hệ thống như **Amazon EKS, Azure Kubernetes Service (AKS), Google Kubernetes Engine (GKE)** có nhiều chế độ dataplane/CNI và chính sách mạng tùy phiên bản/dịch vụ. Không thể chỉ dựa tên managed service để kết luận:

- Mọi Pod đã được cấp security group riêng.
- NetworkPolicy chuẩn được enforce.
- eBPF/Kube-proxy replacement đã bật.
- Cloud firewall thấy tên Pod hoặc namespace.
- Những policy mở rộng L7/FQDN đang có hiệu lực.

**Kiểm chứng cluster configuration và tính năng theo đúng version/profile đang dùng**. Bảng đối chiếu sản phẩm chỉ hữu ích khi đi kèm câu hỏi “nó enforce ở đâu?”.

### 18.2. Pod-to-cloud managed service

Một Pod truy cập object storage, secret manager hoặc managed database qua **private endpoint** vẫn cần **IAM/workload identity, service authorization và TLS**. NetworkPolicy chỉ giới hạn luồng kết nối nếu endpoint được dataplane nhận diện và policy áp dụng đúng.

### 18.3. Hybrid VPN và overlay

Nếu cluster nối on-prem qua VPN/private circuit, hãy kiểm tra **CIDR overlap, route propagation, tunnel encapsulation, source NAT, return route và danh sách đích được phép**. Không đồng nhất mạng nội bộ/VPN với trust zone của ứng dụng.

## 19. Standard NetworkPolicy so với chính sách mở rộng của CNI

Kubernetes NetworkPolicy chuẩn hỗ trợ chủ yếu **L3/L4 allow-based access control** với những trường trong API ổn định. Một số CNI mở rộng bằng các **CustomResourceDefinitions (CRDs)** hoặc API riêng để thực hiện:

- Global/cluster-wide policies và những thứ tự rule/deny semantics riêng.
- FQDN-aware egress hoặc chính sách dựa trên DNS.
- HTTP path/method, gRPC hoặc application-layer rules nếu dataplane/sidecar/proxy phù hợp.
- Policy dựa trên **service identity** hoặc tags ngoài selector chuẩn.
- Bảo vệ **host endpoints, node traffic**, network segmentation ở những interface đặc biệt.
- Encryption liên node, flow visibility, DNS proxy hoặc L7 protocol visibility.

### 19.1. Bảng so sánh khả năng

| Nhu cầu | NetworkPolicy chuẩn | Có thể cần CNI extension / lớp khác |
| --- | --- | --- |
| Chỉ cho app Pods gọi DB TCP 5432 | Có, nếu engine hỗ trợ | Không bắt buộc |
| Cho phép theo namespace + Pod labels | Có | Phải bảo vệ quyền sửa labels |
| Deny có priority cao ghi đè một allow rộng | **Không** trong model chuẩn | Global/deny policies tùy sản phẩm |
| Cho phép theo FQDN và theo dõi DNS TTL | Không có field chuẩn portable | FQDN-aware CNI/egress proxy |
| Chặn riêng HTTP POST /admin | Không có HTTP path/method rule chuẩn | Gateway, WAF, service mesh/L7 policy |
| Phân quyền theo user JWT hoặc object | Không | API authorization |
| Xác thực hai đầu workload bằng mTLS | Không | Service mesh, workload PKI |
| Chặn mọi node-to-Pod/hostNetwork traffic | Không được bảo đảm portable | Host policies/cloud/host firewall |
| Bảo vệ nhiều interface/secondary networks | Không được bảo đảm | Chính sách theo network attachment/dataplane |
| Giám sát flow verdict và HTTP details | Không phải một phần bắt buộc API | CNI observability, proxy, SIEM |

### 19.2. Cân nhắc portability

Một NetworkPolicy chuẩn thường **dễ di chuyển hơn** giữa những CNIs hỗ trợ, nhưng vẫn phải test do NAT/host exceptions. Một CRD độc quyền có thể cung cấp tính năng rất hữu ích nhưng tạo **vendor lock-in và yêu cầu migration** khi đổi CNI.

Không cố “dịch” một policy deny theo priority của sản phẩm A thành **một Kubernetes NetworkPolicy allow-only** rồi tin rằng tương đương. Cần **threat model và ma trận allow/deny** để xác nhận tương đương về hành vi.

### 19.3. Layer 7 không tự có khi CNI dùng eBPF

Một eBPF dataplane có thể phân tích metadata mạng hoặc phối hợp với L7 proxy, nhưng không có nghĩa mọi traffic HTTPS được giải mã. **Muốn áp policy trên HTTP path/method phải có vị trí quan sát nội dung phù hợp**; TLS end-to-end có thể che payload đối với dataplane không terminate/decrypt TLS.

## 20. Phân đoạn mạng, service identity và Zero Trust trong Kubernetes

NetworkPolicy giúp giảm bề mặt kết nối ở mạng cluster, nhưng mô hình Zero Trust đòi **không mặc định tin chỉ vì kết nối xuất phát từ một Pod có nhãn đúng**.

### 20.1. Ba lớp quyết định

| Lớp | Câu hỏi | Kiểm soát minh họa |
| --- | --- | --- |
| **Network reachability** | Pod/source nào được phép đến dịch vụ/port nào? | CNI NetworkPolicy, cloud firewall |
| **Workload/service authentication** | Kết nối có thật sự đến từ service được chấp thuận và đến đúng server? | mTLS, SPIFFE/SVID theo nền tảng, workload identity |
| **Application authorization** | Caller có quyền làm operation trên resource/tenant cụ thể không? | Access token scope/audience, app RBAC/ABAC, object checks |

Một Pod bị xâm nhập và vẫn giữ label **app=checkout** có thể tiếp tục được network policy cho phép gọi Orders API. Vì vậy backend cần xác minh **service identity, user/context và quyền thao tác**, không tin kết nối chỉ vì đến từ một dải IP hoặc namespace.

### 20.2. ServiceAccount không tự là network principal

Kubernetes **ServiceAccount** liên quan tới danh tính của workload khi tương tác với Kubernetes API hoặc các hệ thống được tích hợp; NetworkPolicy chuẩn không có peer selector trực tiếp “ServiceAccount name equals X”. Một số CNI/service mesh tích hợp identity theo cách riêng, nhưng cần kiểm tra cơ chế chứng thực và claim mapping.

### 20.3. Host-level threat model

Nếu node hoặc privileged container bị chiếm quyền, kẻ tấn công có thể tác động tới dataplane/traffic trong những điều kiện cụ thể. NetworkPolicy nằm trên node **không bảo vệ tuyệt đối trước một đối thủ có quyền quản trị node**. Cần thêm node hardening, quyền Kubernetes RBAC, Pod Security Standards, admission, runtime detection, host firewall và giám sát control plane.

### 20.4. Traffic mã hóa và IDS/IPS

NetworkPolicy thường ra quyết định L3/L4; IDS/IPS hoặc CNI observability thấy dữ liệu tùy vị trí, traffic encryption và các hooks được bật. Một IDS trên underlay overlay có thể **không thấy địa chỉ Pod hoặc HTTP payload đầy đủ**, trong khi per-node eBPF flow logs có thể thấy những metadata gần Pod hơn. **Không khẳng định mọi sensor nhìn cùng một luồng**.

## 21. Governance: quyền sửa policy, labels và CNI configuration

Trong cluster, quyền thay đổi NetworkPolicy, labels, namespace membership hoặc CNI configuration có ảnh hưởng trực tiếp tới segmentation.

### 21.1. Những thay đổi cần kiểm soát

- Tạo/sửa/xóa **NetworkPolicy** hoặc CRD policy mở rộng.
- Tạo Pod hoặc sửa **pod labels**, Pod template labels, workload controllers.
- Đổi namespace labels dùng trong **namespaceSelector**.
- Sửa **CNI DaemonSet, ConfigMap, CRDs, agent/controller RBAC**, tùy sản phẩm.
- Thay **Service, EndpointSlice, NodePort, Ingress/Gateway, cloud LoadBalancer**.
- Thay **PodCIDR/IPAM pool, routes, tunnels, BGP peers, kube-proxy replacement**.
- Bật **hostNetwork, hostPort, privileged/host access hoặc secondary interfaces**.
- Đổi cloud firewall, subnet ACL, security group hoặc route to/from cluster.

### 21.2. Quản trị theo quy trình

1. Giao **network/platform owner** và **security reviewer** cho chính sách.
2. Định nghĩa **luồng nghiệp vụ cần thiết** bằng service inventory, không dựa vào “allow all” để tránh lỗi.
3. Dùng **GitOps/IaC** và code review cho policy/route/CNI parameters.
4. Chạy validation về schema, selector, public exposure và required DNS egress.
5. Thử trên lab/staging cùng CNI version/mode tương tự production.
6. Rollout theo namespace/canary, theo dõi DNS/TCP/error rates.
7. Giữ **rollback plan** và chứng cứ effective policy/flow verdict.
8. Rà soát exceptions định kỳ, có ticket/owner/expiry.

### 21.3. Vì sao “kubectl apply thành công” chưa đủ?

Kubernetes API server có thể lưu YAML hợp lệ dù CNI/policy agent chưa triển khai rule thành công, không hỗ trợ tính năng cần thiết hoặc dataplane không nhìn thấy luồng. **Apply success là bằng chứng control plane đã nhận khai báo, không phải chứng nhận network isolation.**

### 21.4. Không tự vá outage bằng cách mở mọi port

Một lỗi DNS sau default-deny thường nên được sửa bằng **DNS egress cụ thể**; một lỗi health check có thể do host traffic semantics; một lỗi IPAM cần quản lý pool. Mở **egress bất kỳ** hoặc xóa toàn bộ policies là giải pháp dễ tạo lỗ hổng và che nguyên nhân.

## 22. Thay CNI: migration phải dựa trên hành vi thực tế

Việc đổi CNI hoặc dataplane mode là thay đổi có phạm vi lớn. Hai hệ thống đều hỗ trợ Kubernetes NetworkPolicy chuẩn nhưng có thể khác về **NAT timing, hostNetwork behavior, IPAM, tunneling, cloud integration, observability và policy extensions**.

### 22.1. Checklist trước migration

| Thành phần | Câu hỏi cần xác minh |
| --- | --- |
| **Inventory** | Có bao nhiêu nodes, Pods, namespaces, policies, CRDs và special networking modes? |
| **Compatibility** | Kubernetes, kernel, CRI và cloud driver hỗ trợ CNI mới? |
| **IPAM** | Có cần đổi Pod CIDR, IP pool, cloud ENI/quota hoặc secondary interfaces? |
| **Routing** | Overlay/direct, BGP, node-to-node tunnels, MTU và return route ra sao? |
| **Service** | kube-proxy còn chạy? eBPF replacement? ClusterIP/NodePort/LoadBalancer parity? |
| **Policy** | Standard NetworkPolicy có cùng semantics trong các đường đang dùng? Extended CRDs chuyển đổi thế nào? |
| **Host traffic** | Node, hostNetwork, hostPort, probes và metadata endpoints được bảo vệ ra sao? |
| **Egress** | NAT, DNS, IPv6, private endpoints và external IP allowlists có thay đổi? |
| **Observability** | Flow logs, drops, policy verdicts và dashboards có hoạt động? |
| **Rollback** | Có cách quay về mode cũ phù hợp với IPAM/state và tránh data loss? |

### 22.2. Staged migration

Một quy trình thận trọng:

1. Kiểm kê và chụp baseline **effective policies/allow-deny outcomes**.
2. Tạo lab/staging có những luồng đại diện: same-node, cross-node, Service VIP, DNS, ingress/egress, cloud endpoints.
3. Đánh giá CNI-specific CRDs, extensions và dependency.
4. Lên kế hoạch node pool/cluster migration theo hướng được nhà cung cấp hỗ trợ; **không tự thay plugin trên từng node production một cách tùy tiện**.
5. Thử canary và so sánh **allowed-flow success**, **negative-test deny**, latency, errors.
6. Kiểm tra fallback/rollback, upgrade path, backups và tình trạng IPAM.
7. Hoàn thiện documentation và giám sát theo CNI mới.

### 22.3. So sánh “không có lỗi” với “có cách ly”

Một cluster sau migration có thể đạt **100% HTTP 200 cho traffic hợp lệ** nhưng vẫn không enforce deny rules như dự định. Cần có các ca thử **từ Pod không được phép tới database** để phát hiện vấn đề khó thấy chỉ từ availability metrics.

## 23. Mẫu chính sách/kiến trúc trung lập với sản phẩm

YAML dưới đây mô tả **yêu cầu và bằng chứng cần có**, không phải cấu hình có thể áp trực tiếp cho Calico, Cilium, Antrea, Flannel, cloud CNI hay Kubernetes.

~~~yaml
kubernetesCniSecurityRequirements:
  name: cni-network-policy-enforcement
  environment: isolated-training
  architecture:
    kubernetesVersion: approved-and-supported
    cniPluginAndVersion: recorded-from-runtime
    ipamMode: documented
    dataPathMode: overlay-or-direct-or-vpc-native
    serviceProxyMode: kube-proxy-or-approved-replacement
    podAddressFamilies: explicitly-documented-ipv4-ipv6
  trustZones:
    namespaces:
      shop: frontend
      payments: backend
      data: sensitive
      kube-system: infrastructure
    labelIntegrity: protected-by-rbac-and-admission
    directNodeAccess: separately-controlled
  policy:
    requireNetworkPolicyEnforcementEvidence: true
    ingressEgressDefaultDeny: staged-per-namespace
    allowCrossNamespaceTraffic: approved-pods-and-ports-only
    preserveRequiredDnsEgress: to-effective-cluster-resolver
    avoidAllowAllEgress: true
    rejectUnauthorizedPublicServiceExposure: true
    reviewIpv6AndServiceNat: true
    doNotAssumePortableFqdnOrL7: true
    protectHostNetworkAndSecondaryInterfaces: separately
  serviceSecurity:
    validateTlsServerIdentity: true
    useServiceToServiceAuthForSensitiveApps: true
    requireObjectAndTenantAuthorization: true
  operations:
    protectCniAgentsAndControllers: true
    verifyAgentHealth: true
    captureFlowVerdicts: where-supported
    correlateDnsServiceAndNetworkFailures: true
    auditPolicyAndLabelChanges: true
    testSameNodeAndCrossNode: true
    testServiceAndDirectPodPaths: true
    testIpv4AndIpv6: when-enabled
    testIngressEgressAndExternalTraffic: true
  governance:
    changeApprovalForCniOrServiceMode: true
    testExtendedPolicyPortability: true
    expireTemporaryExceptions: true
    maintainRollbackPlan: true
~~~

### 23.1. Không được nhầm mô hình ý định với engine thực thi

Một dòng như **requireNetworkPolicyEnforcementEvidence: true** không làm policy được thực thi. Người triển khai phải chuyển yêu cầu thành:

- CRD/API policies phù hợp.
- Workload/network labels được bảo vệ.
- CNI/policy controller/agent đang chạy và lập trình dataplane.
- Network/cloud firewall phối hợp cho những đường ngoài phạm vi chuẩn.
- Test verdict và application logs tại source/destination.

### 23.2. Định nghĩa policy ownership

Mỗi policy nên có ít nhất **namespace, owner, chức năng, target Pod labels, allowed peers/ports, thời hạn nếu tạm, ticket, version và test evidence**. Không nên để policy tên “allow-temp” tồn tại vô thời hạn mà không ai biết nó cho phép những nguồn nào.

## 24. Troubleshooting theo tầng: CNI hay NetworkPolicy đang gây lỗi?

**Quy trình chỉ áp dụng trên cluster được cấp quyền**, ưu tiên quan sát read-only và test traffic có giới hạn. Không tháo policies, tắt CNI agent hoặc can thiệp node production chỉ để kiểm thử.

### Bước 1 – Ghi chính xác luồng

Ví dụ giả lập:

~~~text
Source:       checkout Pod, namespace shop, node-01
Destination:  orders-api Service, namespace payments
Protocol:     TCP
Port:         8443
DNS name:     orders-api.payments.svc.cluster.local
Expected:     ALLOW only from app=checkout in namespace shop
Observed:     DNS resolves, TCP connection times out
Environment:  authorized lab
~~~

Lưu ý **DNS resolve thành công** cho thấy một bước đã đạt, không cho biết policy của gói TCP.

### Bước 2 – Đọc đối tượng Pod/Service

~~~bash
# Quan sát đối tượng được phép; thay tên Pod/namespace theo lab.
kubectl -n shop get pods -o wide --show-labels
kubectl -n payments get pods -o wide --show-labels
kubectl -n payments get service orders-api -o wide
kubectl -n payments get endpointslice -l kubernetes.io/service-name=orders-api
~~~

Kiểm tra **Pod labels, Pod IP, node placement, Service IP, port, targetPort, endpoints và readiness**. Service không có endpoint ready không được chữa bằng cách mở NetworkPolicy rộng.

### Bước 3 – Đọc những NetworkPolicies liên quan

~~~bash
kubectl -n shop get networkpolicy -o yaml
kubectl -n payments get networkpolicy -o yaml
kubectl get namespace shop --show-labels
kubectl get namespace payments --show-labels
~~~

**Xem tất cả policies cùng chọn Pod**, không chỉ policy được sửa gần nhất. Đối chiếu phép AND/OR của các peer items, port/protocol và namespace selector.

### Bước 4 – Xác nhận CNI/policy engine thực thi

Đọc inventory cluster do platform team quản lý để xác định **CNI version, agent/controller health, policy engine mode**. Có thể quan sát system pods theo các đối tượng được phép, nhưng **không dùng một label cố định cho mọi CNI** vì product/version khác nhau.

Không suy **CNI agent Healthy** có nghĩa mọi policy đều enforce; cần test một deny có chủ đích trong lab.

### Bước 5 – Tách DNS, Service dataplane và network policy

1. DNS name có trả đúng **Service VIP/AAAA** không?
2. Service có endpoints healthy không?
3. Pod có thể kết nối tới endpoint qua đường trực tiếp được phép không?
4. Source và destination policies có cho chiều liên quan không?
5. TCP được host/cloud firewall cho phép không?
6. Lưu lượng đi qua Service NAT, NodePort, proxy hoặc overlay path nào?

Nếu dùng debug tool, hãy dùng **toolbox image được phê duyệt** trong lab; không tùy tiện tạo privileged Pod trong production hoặc cài package trực tiếp vào Pod ứng dụng.

### Bước 6 – Đối chiếu network logs và ứng dụng

Tìm những bằng chứng như **drop verdict/policy identity/rule ID**, CNI agent errors, flow records ở node và Service traces. Đối chiếu với **application listener/TLS logs** để phân biệt kết nối bị chặn với ứng dụng trả 401/403.

### Bước 7 – Kiểm tra host/IPv6/alternate paths

Nếu chỉ test Pod-to-Pod cùng node, thêm **cross-node**, Service VIP, ingress LB, hostNetwork và IPv6 khi được bật. Những đường đặc biệt có thể xử lý NAT/policy khác nhau.

### Bước 8 – Thay đổi hẹp, xác minh allow và deny

Chỉ sửa đúng **selector/egress/ingress rule** gây lỗi, không mở mọi port. Kiểm tra:

- Checkout hợp lệ gọi Orders: **allow**.
- Pod không thuộc shop/checkout gọi Orders: **deny**.
- Checkout gọi endpoint không thuộc danh mục: **deny**.
- DNS/health/telemetry cần thiết vẫn hoạt động.
- TLS/application authorization không bị nới lỏng.

## 25. Quan sát CNI: flow logs, verdicts, metrics và audit

### 25.1. Tại sao “không có log deny” không phải bằng chứng allowlist?

Nếu Pod traffic **không đi qua policy hook**, CNI agent đang lỗi, logging chưa bật hoặc luồng được xử lý ở network path khác, hệ thống có thể không ghi deny event. **Không có log** có thể đồng nghĩa không có traffic, không có telemetry hoặc **mất enforcement coverage**.

Những nguồn dữ liệu cần phối hợp:

| Nguồn | Dữ liệu thường có | Giới hạn |
| --- | --- | --- |
| **CNI flow verdict/monitoring** | Nguồn/đích Pod/identity, port, allow/drop, policy/rule ID nếu hỗ trợ | Phụ thuộc CNI/version/dataplane và sampling |
| **CNI agent/controller logs** | Lỗi lập trình policy, IPAM, routing, tunnel, service mapping | Có thể không chứa từng packet |
| **Kubernetes audit** | Ai tạo/sửa NetworkPolicy, Pods, labels, Services, CRDs | Không tự chứng minh traffic đã được chặn |
| **Service/EndpointSlice state** | Endpoint readiness, Service IP, port/targetPort | Không nêu policy verdict |
| **Cloud flow/firewall logs** | IP/port, flow result ở cloud network | Overlay có thể che Pod IP trong tunnel |
| **DNS logs/CoreDNS** | Tên truy vấn, RCODE, latency, upstream errors theo cấu hình | Không thấy resolver/DoH đi vòng |
| **Proxy/Ingress/WAF** | HTTP host/path, rule, response, client context khi có | Chỉ những luồng qua proxy |
| **Application/TLS logs** | Request ID, TLS identity, status, user/tenant decision | Có thể không thấy packet bị drop trước ứng dụng |
| **Host/EDR telemetry** | Process network behavior, node threats | Quyền quan sát và độ bao phủ tùy agent |

### 25.2. Log giả lập: egress policy chặn Pod ngoài quyền

~~~json
{
  "timestamp": "2026-11-28T21:05:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "kubernetes_network_policy_verdict",
  "cni_mode": "policy-enabled-lab",
  "source": {
    "namespace": "shop",
    "pod": "unapproved-client-01",
    "labels": {"app": "debug-client"},
    "node": "lab-node-01",
    "pod_ip": "10.244.1.31"
  },
  "destination": {
    "namespace": "payments",
    "pod": "orders-api-01",
    "pod_ip": "10.244.2.17",
    "port": 8443,
    "protocol": "TCP"
  },
  "policy_direction": "ingress",
  "decision": "drop",
  "rule_context": "orders-from-approved-checkout",
  "reason": "source-selector-not-allowed",
  "application_received_request": false
}
~~~

Đây là **dữ liệu tổng hợp**, không phải schema của một CNI cụ thể. Một số sản phẩm không có field **rule_context** hoặc không quan sát đầy đủ destination Pod sau Service NAT. Nếu log cho thấy drop tại ingress policy, còn Pod không nhận request, có bằng chứng phù hợp hơn chỉ dựa vào client timeout.

### 25.3. Log giả lập: policy agent không lập trình được dataplane

~~~json
{
  "timestamp": "2026-11-28T21:08:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "cni_policy_reconciliation_error",
  "node": "lab-node-03",
  "policy": "default-deny-all",
  "namespace": "data",
  "desired_version": "network-policy-2026-11-28-04",
  "observed_version": "network-policy-2026-11-28-02",
  "reason": "dataplane-programming-failed",
  "impact": "enforcement-state-not-verified",
  "action": "quarantine-and-validate-node-before-trusting-policy"
}
~~~

**Không thể khẳng định mọi CNI khi lỗi lập trình rule đều fail-open**. Có giải pháp có thể drop traffic, giữ policy cũ hoặc hành xử khác theo mode. Log minh họa **một khoảng không chắc chắn cần điều tra**, không mô tả fail mode chung cho mọi sản phẩm.

### 25.4. Log giả lập: cùng Pod nhưng Service translation khác

~~~json
{
  "timestamp": "2026-11-28T21:10:00+07:00",
  "dataset": "synthetic-training-event",
  "request_id": "lab-service-req-027",
  "source_pod": "checkout-01",
  "service_ip": "10.96.0.20",
  "service_port": 8443,
  "selected_endpoint_ip": "10.244.2.17",
  "selected_endpoint_port": 8443,
  "network_policy_decision": "allow",
  "tls_server_identity_validation": "pass",
  "application_status": 403,
  "interpretation": "network-allowed-but-application-authorization-denied"
}
~~~

Ví dụ này giúp phân biệt **network policy đã cho kết nối** với **application authorization từ chối**. HTTP 403 ở đây không phải bằng chứng CNI lỗi.

### 25.5. Những metric nên theo dõi

- Số nodes có **CNI agent ready**, policy reconciliation success/failure và node coverage.
- Mức dùng **Pod IP/IPAM pools**, address exhaustion, orphan allocations và lỗi ADD/DEL.
- Tỷ lệ **policy drop/allow** theo namespace/service/port (nếu được cung cấp).
- **Same-node vs cross-node** latency, packet drops, tunnel health và MTU/fragmentation issues.
- **Service VIP → endpoints** mapping/connection failures, kube-proxy hoặc dataplane health.
- DNS timeout/NXDOMAIN/SERVFAIL và egress DNS denies.
- Thay đổi bất thường về **hostNetwork, NodePort, LoadBalancer, namespace/Pod labels**.
- IPv4/IPv6 coverage, cloud network paths và return-route failures.
- Rule/config drift và số **temporary allow exceptions** quá hạn.
- API/TLS/identity failure rates để tránh quy kết mọi lỗi cho CNI.

### 25.6. Bảo vệ log và dữ liệu riêng tư

Flow logs có thể chứa IP, labels, service names, network destinations, hostname và thời điểm truy cập. Phải có **IAM/RBAC, retention, access audit, redaction và mã hóa** phù hợp. Không thu thập Bearer token, private key hoặc request payload nhạy cảm chỉ để điều tra policy.

## 26. Ma trận kiểm thử CNI và NetworkPolicy trong lab

**Phạm vi:** cluster và network routes được cấp quyền. Không áp stress/flood vào CNI production, không thay node routes/iptables/eBPF maps trên máy vận hành chỉ để chứng minh deny, và không truy cập bên thứ ba ngoài danh sách được phê duyệt.

### 26.1. Các ca kiểm thử

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-01 | Pod A và Pod B cùng node, không bị isolation trong lab | Kết nối theo topology và service readiness |
| T-02 | Pod A/B khác node có route/tunnel hợp lệ | Pod-to-Pod reachability theo thiết kế |
| T-03 | DNS Service FQDN trả ClusterIP hợp lệ | DNS thành công, được kiểm tra độc lập với TCP |
| T-04 | Service VIP kết nối đúng endpoint sẵn sàng | Kết nối ứng dụng thành công khi policy cho phép |
| T-05 | Namespace payments dùng ingress default deny trong lab | Client không có allow bị chặn |
| T-06 | app=checkout ở namespace shop gọi Orders TCP 8443 | Allow theo ingress/egress rules đã phê duyệt |
| T-07 | Pod ở shop nhưng app=debug-client gọi Orders TCP 8443 | Deny, không khớp đúng source selector |
| T-08 | app=checkout ở namespace dev gọi Orders | Deny nếu chỉ shop được cho phép |
| T-09 | app=checkout gọi Orders TCP port không được phép | Deny |
| T-10 | Checkout egress-isolated nhưng thiếu DNS egress | DNS bị chặn theo policy, không kết luận CoreDNS không khỏe |
| T-11 | Checkout có DNS allow UDP/TCP 53 đúng resolver | DNS thành công; các cổng ứng dụng khác vẫn có thể deny |
| T-12 | DNS Pod label/namespace khác giả định của manifest | Chính sách cần được chỉnh theo cấu hình thật và test |
| T-13 | NodeLocal DNSCache được bật trong lab | DNS path và host/policy handling đúng |
| T-14 | Hai policies cùng chọn Pod: một allow rộng, một allow hẹp | Quy tắc hợp allow được xác nhận; không tự giả định deny ưu tiên |
| T-15 | Peer AND trong cùng item: namespace shop + app checkout | Chỉ nguồn thỏa cả hai được phép |
| T-16 | Peer OR ở hai items tách biệt | Test phát hiện phạm vi rộng hơn mong đợi |
| T-17 | ipBlock egress tới CIDR lab được duyệt | Đúng allow/except theo implementation và NAT path |
| T-18 | Service VIP/DNAT và direct Pod-IP destination | Kết quả được giải thích theo dataplane thực tế |
| T-19 | Traffic hairpin/same-node tới Service | Kết nối và policy verdict đúng mong đợi |
| T-20 | Pod → node/host endpoint trong lab | Đường host được kiểm tra riêng, không dựa hoàn toàn vào default deny |
| T-21 | hostNetwork/hostPort Pod được phép thử trong lab | Đánh giá host firewall/CNI host policy và exposure |
| T-22 | Internet → LoadBalancer/Ingress → backend | Chỉ đường public đã duyệt hoạt động; backend có auth |
| T-23 | NodePort/alternate LB đi vòng ingress nếu tồn tại trong lab | Phát hiện và giới hạn theo cloud/network policy |
| T-24 | App-to-DB TCP 5432 từ workload đúng role | Allow ở mạng, DB auth vẫn cần |
| T-25 | Dev Pod hoặc workload sai role tới production DB | Deny, ghi log tại enforcement point |
| T-26 | Pod → external Internet qua SNAT | Egress policy và cloud firewall cùng đáp ứng |
| T-27 | IPv4/IPv6 Service/Pod trên cluster dual-stack | Both address families được kiểm thử riêng |
| T-28 | CNI agent trên một node lỗi trong lab cô lập | Alert và fail mode quan sát/ghi nhận, không suy chung |
| T-29 | Pod IP pool sắp hết ở node pool lab | Alert/quota thấy được, không nhầm với policy deny |
| T-30 | Chuyển mode overlay → direct hoặc thay CNI trong staging | Positive và negative test giữ parity theo design |
| T-31 | CNI extended FQDN/L7 policy được bật trong lab hỗ trợ | Hành vi đúng phiên bản, không giả là API chuẩn |
| T-32 | Policy selector theo Pod/namespace labels bị sửa trái phép trong lab | Admission/RBAC/audit phát hiện; traffic không mở ngoài ý định |
| T-33 | HTTPS tới API có network allow nhưng access token thiếu quyền | Application từ chối, không quy kết network |
| T-34 | Pod đến cloud private endpoint với IAM không đủ quyền | Network có thể tới endpoint, resource action bị từ chối |
| T-35 | Kiểm thử sự cố và phục hồi Node/CNI agent từng zone | Không tạo đường fail-open mới, log/metrics đầy đủ |

### 26.2. Bằng chứng cần lưu

1. **Environment/quyền thử, source/destination**, Pod/namespace/node và labels.
2. **CNI name/version/dataplane mode, IPAM, Kubernetes version**, policy engine status.
3. **NetworkPolicy/CRDs áp dụng**, rule ID/config version, các policies khác cùng chọn Pod.
4. **DNS name, Service VIP, EndpointSlice/Pod IP, TCP port**, IPv4/IPv6.
5. **Ingress và egress policy verdict**, source identity/NAT context theo tool hỗ trợ.
6. **Route/MTU/host/cloud firewall** nếu traffic vượt node hoặc ra Internet.
7. **TLS/API authorization outcome**, để không đồng nhất network allow với quyền ứng dụng.
8. **Pass/fail**, thời gian thực hiện, tác động tới request hợp lệ và rollback.

### 26.3. Vì sao HTTP 200 chưa chứng minh isolation?

Nếu chỉ thử checkout hợp lệ và thấy HTTP 200, hệ thống có thể đang **allow-all**, hoặc một policy rộng cho mọi clients. Cần thử một Pod **không được phép** cùng đường Service và port; request đó phải bị chặn tại đúng lớp và backend không nhận nó.

### 26.4. Vì sao timeout chưa chứng minh rule đã deny?

Timeout có thể do thiếu route, CoreDNS lỗi, Service không có endpoints, MTU, node outage hoặc target không listen. **Cần flow verdict, routing/endpoint evidence và log ứng dụng** để chứng minh đúng policy đang thực thi.

### 26.5. Giới hạn kiểm thử

Không dùng scans diện rộng hoặc test nguồn không được ủy quyền. Với negative tests, ưu tiên **một hoặc vài kết nối có giới hạn** và synthetic logs; không thực hiện flood, exhaustion hoặc chỉnh sửa dataplane production bất thường.

## 27. Runbook: NetworkPolicy không còn chặn sau thay CNI

**Tình huống:** Sau khi đổi dataplane mode ở một node pool, ứng dụng checkout vẫn gọi Orders API được, nhưng một Pod test không được phép cũng kết nối được tới Orders API qua TCP 8443. Các NetworkPolicy vẫn tồn tại trong Kubernetes và lệnh đọc manifest không báo lỗi.

### 27.1. Phân loại ban đầu

Đây là một **nghi vấn mất network isolation**. Không tự kết luận cụm đã bị xâm nhập, nhưng cần giảm nguy cơ bằng cách coi **positive test đang pass mà negative test đang fail** là dấu hiệu policy có thể không được enforce đúng.

### 27.2. Bước 1 – Bảo toàn chứng cứ

Ghi:

- Thời điểm thay đổi CNI, versions/modes trước và sau.
- Namespace/Pod/node của nguồn hợp lệ và nguồn bị cấm.
- Service VIP, Pod endpoint, IP family, ingress path và port.
- Tất cả **NetworkPolicy/extended policies** liên quan, policy config versions.
- Agent/controller health, errors và CNI flow verdicts.
- Cloud firewall/host routing/Service dataplane logs nếu luồng đi qua các lớp đó.

Không để logs chứa credential; không đọc hoặc ghi secrets khi không cần.

### 27.3. Bước 2 – Xác minh policy chọn đúng Pods

1. Kiểm tra **labels thực tế** của backend và client.
2. Kiểm tra **namespaceSelector AND podSelector** có đúng một peer item không.
3. Đọc **mọi policies** đang chọn backend: có rule allow rộng hơn tồn tại không?
4. Đọc các policies egress của client; một allow rộng có thể cho outbound nhưng backend vẫn phải enforce ingress isolation khi được chọn.
5. Đối chiếu **network policy modes/CRDs** trên CNI mới: có quy tắc nào bị bỏ qua khi chuyển không?

Nếu lỗi do selector thay đổi, sửa selector hẹp và xác nhận logs; không quy hết cho CNI upgrade.

### 27.4. Bước 3 – Kiểm tra engine và dataplane

- Agent/daemonset đang ready trên **node chứa source và destination** chưa?
- Policy reconciliation đã thành công hay còn pending/error?
- Có **iptables/nftables/eBPF/OVS hook** tương ứng đang xử lý flow trong mode mới không? Dùng tool do platform team hỗ trợ, không sửa tay cấu hình node.
- Service proxy mode có đổi từ kube-proxy sang replacement hoặc ngược lại không?
- Có sự khác nhau giữa **ClusterIP traffic, direct Pod IP, same-node/cross-node** không?
- Có đường hostNetwork/NodePort/secondary network không được engine bảo vệ theo dự kiến?
- Source IP có bị NAT khiến quy tắc CIDR/identity diễn giải khác không?

**Một CNI agent chạy không lỗi chưa bảo đảm mọi luật đã được cài đúng**. Cần kiểm tra **verdict có thể quan sát và negative test**.

### 27.5. Bước 4 – Khoanh vùng

Theo quy trình incident/change được duyệt:

- Tạm dừng rollout CNI/dataplane mới tới các node pool khác.
- Giới hạn traffic đến tài nguyên nhạy cảm bằng **một điểm kiểm soát độc lập phù hợp** nếu khả thi (cloud firewall/service mesh auth/endpoint policy).
- Không tắt application TLS/mTLS/authorization; đây là lớp phòng vệ còn lại.
- Nếu có node pool chưa thay đổi mà policy vẫn enforce, cân nhắc dịch workloads theo phương án vận hành được hỗ trợ; đánh giá rủi ro IPAM/data availability trước khi làm.
- Tránh tùy tiện xóa CNI resources, sửa eBPF maps hoặc chạy lệnh iptables trực tiếp trên node production.

### 27.6. Bước 5 – Xác minh phục hồi

| Test | Kỳ vọng |
| --- | --- |
| Checkout hợp lệ → Orders TCP 8443 | Allow |
| Pod app=debug-client từ shop → Orders | Deny tại đúng ingress/policy path |
| Pod app=checkout từ namespace khác → Orders | Deny |
| Checkout → DNS cần thiết | Allow |
| Checkout → cổng backend khác 8443 | Deny nếu không được duyệt |
| Internet/NodePort/bypass path → Orders | Theo cloud+ingress policy riêng, không mở ngoài dự kiến |
| T-01/T-02 same-node/cross-node | Kết quả nhất quán |
| IPv4/IPv6 đang bật | Không tồn tại đường truy cập phụ |
| TLS/API auth | Vẫn kiểm tra đầy đủ quyền người gọi |

### 27.7. Bước 6 – Root cause và phòng ngừa

Tổng hợp nguyên nhân: **policy controller không hoạt động**, hook bị đổi, label/rule mismatch, CNI-specific CRDs không tương thích, Service NAT path, hostNetwork path hoặc IPAM/routing khác dự kiến. Bổ sung **migration acceptance tests** để mỗi lần đổi CNI hoặc dataplane phải có **negative-test gating**, không chỉ yêu cầu Pods ready và tỷ lệ request thành công.

## 28. Tình huống tổng hợp: policy đúng YAML nhưng backend vẫn lộ

Một công ty có ba namespaces:

- **shop**: frontend checkout.
- **payments**: Orders API.
- **data**: PostgreSQL và service chứa dữ liệu nhạy cảm.

Yêu cầu an toàn: chỉ checkout trong shop được gọi Orders API TCP 8443; chỉ Orders API được kết nối PostgreSQL TCP 5432; Internet chỉ đi qua gateway/WAF.

Đội triển khai một CNI có hỗ trợ NetworkPolicy và áp dụng ingress rule tại payments. Trên staging, request checkout thành công. Nhưng test từ một Pod debug ở namespace shop cũng gọi được Orders API. Đồng thời, database có một LoadBalancer cũ chưa gỡ.

### 28.1. Vấn đề thứ nhất: cấu trúc peer quá rộng

Một rule đã được viết như sau:

~~~yaml
# PHẢN VÍ DỤ: Hai peer items tạo phép OR, không phải AND.
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: shop
  - podSelector:
      matchLabels:
        app: checkout
~~~

Điều này có thể cho phép **bất kỳ Pod nào từ shop** hoặc checkout Pod trong namespace chứa policy. Để chỉ cho checkout ở shop, phải ghép namespaceSelector và podSelector vào **cùng một peer item** như mục 11.

### 28.2. Vấn đề thứ hai: còn đường công khai

Database bị expose qua một **LoadBalancer cũ**, khiến traffic có thể đến qua đường không đi theo ingress được kiểm soát như dự kiến. Việc NetworkPolicy trên Orders API không tự chặn đường công khai tới database.

Cần kiểm kê Service types, cloud LBs, public IPv4/IPv6, NodePorts, firewall, Ingress/Gateway mappings và database authentication. **Không kết luận data đã bị đọc chỉ từ việc tồn tại public LB**; phải kiểm tra reachability, listener và audit database.

### 28.3. Vấn đề thứ ba: thiếu chính sách tại data tier

Giả sử database namespace chưa có **ingress isolation** đúng và Orders API vẫn dùng shared database credential quá rộng. Khi Pod khác được route tới database, nó có thể thử kết nối ngay cả khi không đi qua Orders API.

Phòng vệ:

1. NetworkPolicy data-tier chỉ cho nguồn Pods đã duyệt vào TCP 5432.
2. Cloud/network firewall khóa public access và đường bypass.
3. PostgreSQL authentication, TLS và quyền trên database giới hạn cho từng workload.
4. Workload identity/secret management và audit truy cập.
5. Negative tests cho Pod không được phép và những đường external.

### 28.4. Sơ đồ bảo vệ sau khi sửa

~~~mermaid
flowchart LR
    PUB["Internet"] -->|"HTTPS public được duyệt"| EDGE["Gateway / WAF"]
    EDGE -->|"Approved route"| CHECK["checkout / shop"]
    CHECK -->|"TCP 8443; matching namespace AND Pod labels"| ORD["orders-api / payments"]
    ORD -->|"TCP 5432; riêng app role"| DB[("PostgreSQL / data")]
    PUB -. "Deny direct public LB/NodePort" .-> DB
    WRONG["debug-client / shop"] -. "NetworkPolicy deny" .-> ORD
    WRONG -. "NetworkPolicy deny" .-> DB
    ORD -. "mTLS + application authorization" .-> DB
~~~

### 28.5. Tiêu chí nghiệm thu

- Policy matcher chỉ chọn đúng **app=checkout trong shop**, không cho Pod khác.
- Không có allow rộng ở một NetworkPolicy khác làm vô hiệu mục tiêu.
- CNI thực thi đúng ở same-node/cross-node, qua Service VIP và direct Pod IP theo thiết kế.
- Database không được công bố trực tiếp ra Internet và có NetworkPolicy/app auth riêng.
- API vẫn xác minh **TLS identity và quyền business**; không tin Pod labels như danh tính người dùng.
- Flow logs và app/db audit đủ chứng cứ khi một request bị từ chối hoặc truy cập thành công.

**Bài học:** một YAML đúng cú pháp, một request thành công và một CNI hỗ trợ policy chỉ là các điều kiện riêng lẻ. **Ranh giới an toàn** cần sự kết hợp của chính sách đúng, enforcement thật và bao phủ mọi đường vào/ra.

## 29. Sai lầm thường gặp và câu hỏi tự kiểm tra

### 29.1. Những sai lầm phổ biến

| Sai lầm | Tác động | Cách làm đúng |
| --- | --- | --- |
| “CNI plugin luôn enforce NetworkPolicy” | Cluster có connectivity nhưng không có isolation | Xác minh policy engine và negative tests |
| “Apply manifest thành công chứng minh deny” | K8s lưu object nhưng dataplane không enforce | Đọc flow verdict và kiểm thử |
| “Chỉ cần ingress allow; egress isolation không quan trọng” | Workload có thể chủ động gọi đích ngoài ý định | Rà soát cả hai chiều theo threat model |
| “Hai peer items là AND” | Rule mở rộng hơn dự kiến | Gộp namespaceSelector và podSelector vào cùng peer item |
| “Policy hẹp ghi đè policy allow rộng” | Luồng vẫn được phép qua policy khác | Đọc hợp các policy chuẩn, bỏ allow thừa |
| “Default-deny-all chặn cả node/host trong mọi CNI” | Host bypass hoặc quản trị ngoài dự kiến | Kiểm soát host networking, node/cloud firewall |
| “Label app=admin là danh tính đáng tin” | Thay label có thể mở kết nối | Bảo vệ labels bằng RBAC/admission và dùng mTLS |
| “Có ClusterIP là đã có isolation” | Service discovery/routing không cấp quyền | NetworkPolicy + application auth |
| “iptables luôn chứa toàn bộ rules” | Bỏ qua eBPF/OVS/dataplane khác | Xác định actual packet path và tools CNI |
| “eBPF tự giải mã HTTPS để áp L7” | Tin vào tính năng không được triển khai | Kiểm tra TLS termination/L7 proxy thật |
| “Overlay làm cloud firewall thấy Pod IP” | Sai điểm quan sát và allowlisting | Hiểu encapsulation và CNI-level logs |
| “ipBlock luôn kiểm tra Service VIP trước DNAT” | Policy không portable giữa modes | Test NAT/Service semantics thực tế |
| “Chỉ DNS UDP/53 là đủ” | TCP fallback/NodeLocal DNS bị chặn | Xác minh DNS path và protocol |
| “NetworkPolicy chuẩn có FQDN allowlist” | Bỏ sót DNS bypass/IP changes | Dùng CNI extension/egress proxy được hỗ trợ |
| “Chặn IPv4 đồng nghĩa chặn IPv6” | Alternate family bypass | Test dual-stack policy/firewall |
| “HostNetwork Pod giống Pod thường về isolation” | Node path không được bảo vệ đầy đủ | Host-specific security controls |
| “NodePort an toàn vì có Ingress” | Có đường bypass WAF/gateway | Inventory routes, cloud firewall và LB |
| “Healthy service là policy được enforce” | Availability che mất lỗ hổng isolation | Negative tests bắt buộc |
| “HTTP 403 là NetworkPolicy đã chặn” | Có thể backend/gateway trả 403 | Kiểm tra flow verdict và app logs |
| “Thay CNI không ảnh hưởng policy cũ” | Extension/NAT/host semantics khác | Migration parity testing và rollback |
| “Pod IP thay đổi thì luôn sửa allowlist IP” | Policy dễ lỗi sau scale | Pod/namespace selectors được quản lý |
| “Private endpoint đồng nghĩa có quyền dữ liệu” | Sai IAM/resource authorization | Network + IAM + TLS + app checks |

### 29.2. Câu hỏi 1 – CNI specification có bắt buộc NetworkPolicy không?

**Gợi ý:** Không. CNI định nghĩa interface cấu hình mạng container; khả năng enforce Kubernetes NetworkPolicy cần network/policy implementation tương ứng.

### 29.3. Câu hỏi 2 – Vì sao một Pod-to-Pod connection thành công không chứng minh network isolation?

**Gợi ý:** policy có thể không tồn tại, agent không thực thi hoặc có một allow rộng. Cần dùng Pod không được phép để kiểm tra từ chối.

### 29.4. Câu hỏi 3 – Nếu một NetworkPolicy allow đúng checkout nhưng policy khác allow cả namespace, kết quả ra sao?

**Gợi ý:** Standard policies cộng dồn các luồng allow; không có deny ưu tiên trong API chuẩn để ghi đè.

### 29.5. Câu hỏi 4 – Hai điều kiện namespaceSelector + podSelector phải đặt ở đâu?

**Gợi ý:** cùng một peer item để tạo AND. Hai items riêng nghĩa OR.

### 29.6. Câu hỏi 5 – Flannel cung cấp Pod networking có đủ để khẳng định NetworkPolicy được bảo vệ không?

**Gợi ý:** Không. Xác minh có policy engine khác/giải pháp CNI phối hợp và test enforcement.

### 29.7. Câu hỏi 6 – Vì sao CNI mode overlay ảnh hưởng khả năng quan sát của cloud firewall?

**Gợi ý:** cloud firewall underlay có thể chỉ thấy packet giữa nodes/tunnel endpoints thay vì inner Pod IP/port.

### 29.8. Câu hỏi 7 – Vì sao NAT/Service VIP làm ipBlock có hành vi phụ thuộc implementation?

**Gợi ý:** policy hook có thể nằm trước/sau translation, còn CNI nhận diện endpoint/service theo các cách khác nhau.

### 29.9. Câu hỏi 8 – Một Pod đã bị egress-isolated đột nhiên không gọi được tên Service. Có nên mở toàn bộ egress?

**Gợi ý:** Không. Kiểm tra resolver thực, UDP/TCP 53, CoreDNS/NodeLocal, policy và CNI dataplane.

### 29.10. Câu hỏi 9 – ServiceAccount và Pod labels có tự chứng minh user được quyền đọc dữ liệu không?

**Gợi ý:** Không. Cần TLS/workload identity và application authorization.

### 29.11. Câu hỏi 10 – Vì sao NetworkPolicy chuẩn không bảo vệ hết hostNetwork và NodePort?

**Gợi ý:** host/node paths và Service translation có semantics khác nhau theo CNI, cloud và proxy; cần kiểm soát host/cloud/ingress bổ sung.

### 29.12. Câu hỏi 11 – Khi đổi CNI từ iptables sang eBPF dataplane, điều gì cần test lại?

**Gợi ý:** standard/extended policies, Service VIP, NAT, host paths, cross-node, DNS, IPv6, flow visibility và negative cases.

### 29.13. Câu hỏi 12 – Vì sao traffic bị timeout không đủ chứng minh NetworkPolicy deny?

**Gợi ý:** route, IPAM, DNS, Service endpoint, MTU, host firewall hoặc listener đều có thể làm kết nối thất bại.

### 29.14. Bài tập thiết kế kiến trúc

Một cluster Kubernetes có **namespaces shop, payments, data, monitoring và kube-system**; các workload gồm checkout, orders-api, billing-api, PostgreSQL và CoreDNS. Cluster chạy trên cloud với public ingress gateway, NodeLocal DNSCache và một dịch vụ managed storage qua private endpoint.

Hãy:

1. Vẽ **Pod → CNI/IPAM → node/overlay/direct dataplane → Service VIP → endpoint** và đánh dấu những điểm policy có thể enforce.
2. Xác định CNI version/mode, NetworkPolicy engine và những ngoại lệ về **hostNetwork/NodePort/IPv6** cần kiểm tra.
3. Lập ma trận **nguồn → đích → port → policy ingress/egress → TLS/service identity → application authorization**.
4. Viết **default-deny ingress/egress** cho data namespace theo rollout có kiểm soát.
5. Viết allow rule chỉ cho **app=orders-api trong payments** kết nối PostgreSQL TCP 5432 ở namespace data.
6. Viết allow egress phù hợp cho checkout gọi orders-api TCP 8443 và truy vấn cluster DNS qua endpoint thật.
7. Giải thích AND/OR giữa namespaceSelector và podSelector, và viết một negative test phát hiện OR quá rộng.
8. Chỉ ra giới hạn **ipBlock** và cách Service NAT hoặc cloud SNAT ảnh hưởng tới cách đọc policy/log.
9. Thiết kế đường từ Pod tới **private storage endpoint**, kết hợp NetworkPolicy/egress controls, IAM và TLS.
10. Thiết kế **host/NodePort/LoadBalancer protection** để Internet không bypass public ingress gateway.
11. Lập ít nhất **mười positive/negative tests** ở same-node, cross-node, Service VIP, DNS, NodeLocal, egress, IPv6 và cloud LB.
12. Đề xuất quan sát flow verdict, Kubernetes audit, CNI agent logs và application authorization khi có sự cố.
13. Xây dựng kế hoạch **thay CNI có acceptance gates**, canary và rollback dựa trên deny outcomes, không chỉ request success.
14. Viết runbook khi Pod debug có thể gọi Orders API sau khi một chính sách ingress được triển khai.

**Tiêu chí đạt:** cluster có đường mạng cho phép nghiệp vụ hợp lệ, nhưng nguồn ngoài quyền **không thể kết nối** tới cổng nhạy cảm; mọi kết luận đều có **bằng chứng từ cả policy lẫn dataplane**, và API vẫn thực hiện xác thực/ủy quyền độc lập.

## 30. Những điều cần ghi nhớ

- **CNI cung cấp cơ chế cấu hình mạng container; NetworkPolicy enforcement không phải bảo đảm tự động của mọi CNI.**
- **Pod IP, IPAM, veth, overlay/direct routing, Service proxy, NAT và eBPF/iptables/OVS** có thể thay đổi packet path và nơi policy được kiểm tra.
- **NetworkPolicy chuẩn là L3/L4 allow-based và các policies cộng dồn**; default deny chỉ có ý nghĩa trong phạm vi engine thực thi thật.
- **namespaceSelector và podSelector đặt trong cùng một peer item là AND; tách thành các peer items là OR.**
- **Ingress và egress isolation cần được xét theo hai phía**; DNS, node/host, kube-system và service dependencies phải được kiểm tra theo topology thực.
- **ipBlock, Service VIP, NodePort, hostNetwork và IPv6 có giới hạn portability**; phải kiểm tra NAT, cloud firewall và CNI-specific behavior.
- **Extended policies như FQDN/L7/host protection phụ thuộc CNI/version**, không mặc định là tính năng của Kubernetes NetworkPolicy API.
- **Labels/service accounts không thay TLS/mTLS workload identity hoặc application authorization**; Pod được phép nối mạng không tự có quyền đọc dữ liệu.
- **Không có flow deny hoặc ứng dụng HTTP 200 không chứng minh isolation**; cần kiểm thử cả allow và deny tại đúng enforcement point.
- **Thay CNI/dataplane phải được coi là thay đổi bảo mật lớn**, có migration matrix, canary, coverage monitoring và rollback.
- **Triển khai least privilege cần đi cùng RBAC/admission, policy-as-code, audit, cloud networking và giám sát** để bảo vệ cả cấu hình lẫn runtime.
- **Chỉ kiểm thử trong môi trường được cấp phép**, thu thập log/flow verdict và bảo đảm những nguồn trái quyền bị chặn mà luồng hợp lệ vẫn hoạt động.




