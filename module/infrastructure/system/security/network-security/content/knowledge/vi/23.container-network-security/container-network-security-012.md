# Quan sát lưu lượng container: Từ network namespace đến flow logs, eBPF và phát hiện bất thường

## 1. Vì sao cần quan sát lưu lượng container?

**Quan sát lưu lượng container (container network observability)** là khả năng thu thập, liên kết và giải thích các bằng chứng về **ai đang kết nối tới ai, qua giao thức/cổng nào, khi nào, với kết quả gì và có phù hợp chính sách mạng hay không** trong môi trường container. Bằng chứng có thể đến từ **flow logs**, counters, packet capture, DNS logs, các điểm gắn eBPF, CNI, ingress/egress gateways, service mesh, ứng dụng và hệ thống giám sát.

Trong chương **Bảo mật mạng container** của học phần **SECURITY_NETWORK_SECURITY**, quan sát mạng không chỉ phục vụ tìm lỗi kết nối. Nó còn giúp nhận diện **east–west lateral movement, đường egress trái phép, nhầm quyền giữa namespace, truy cập đến metadata/administrative endpoints, lỗi NetworkPolicy, DNS bất thường và dấu hiệu exfiltration**. Các lớp giám sát bổ sung cho phân đoạn, firewall, VPN, IDS/IPS, WAF và bảo vệ DNS trong một kiến trúc defense in depth.

**Thách thức:** container và pod có vòng đời ngắn; một địa chỉ IP hôm nay thuộc workload A, vài phút sau có thể được cấp lại cho workload B. Một yêu cầu tới **Kubernetes Service IP** có thể được NAT tới một **pod IP**; traffic qua service mesh có thể được chuyển qua **sidecar hoặc node proxy**; traffic HTTPS tiếp tục mã hóa dù qua nhiều nút. Vì vậy, chỉ xem IP nguồn/đích trong một packet thường **không đủ để xác định danh tính workload hoặc nguyên nhân bảo mật**.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích đường đi gói tin qua **container network namespace, veth, CNI, service routing, kube-proxy/eBPF, overlay và node network**.
2. Chọn đúng **điểm quan sát** cho traffic intra-pod, pod-to-pod, pod-to-service, ingress, egress và cross-node.
3. Phân biệt **flow metadata, metrics, packet capture, DNS, L7 telemetry, distributed traces và Kubernetes audit**.
4. Tương quan traffic với **pod UID, namespace, workload, service account, node, network identity và thời điểm**.
5. Hiểu điểm mạnh, điểm mù và chi phí của **tcpdump, conntrack, CNI flow logs, eBPF và service mesh telemetry**.
6. Thiết kế pipeline quan sát với **giảm thiểu dữ liệu nhạy cảm, sampling, retention, RBAC và sức khỏe collector**.
7. Tạo use cases phát hiện, thực hành trong lab hợp lệ và xử lý sự cố dựa trên bằng chứng thay vì suy đoán.

## 2. Nền tảng mạng container: Đối tượng thực sự đang giao tiếp

### 2.1. Network namespace

Trên Linux, một **network namespace** thường có không gian riêng cho interfaces, addresses, route tables, sockets, một số cấu trúc firewall/connection tracking và network settings. Một container runtime có thể tạo namespace mạng riêng hoặc gắn tiến trình vào namespace đã có.

Trong Kubernetes, các container bình thường của **cùng một Pod** thường **chia sẻ network namespace** của pod: cùng pod IP, cùng loopback và không gian cổng. Chúng **không có IP riêng cho từng container** theo mô hình Pod networking thông thường. Do đó:

- Kết nối từ container A tới container B **trong cùng pod** bằng loopback có thể không đi qua veth của pod ra node.
- Flow logs quan sát ở host veth có thể **không nhìn thấy loopback nội bộ**.
- Khi một pod có nhiều container (app, sidecar), **pod IP không đủ phân biệt container nào tạo socket**; cần process/socket-level telemetry hoặc application logs phù hợp.

**Ngoại lệ:** hostNetwork, plugin đặc thù, multiple interfaces qua Multus hoặc runtime khác có thể làm datapath và cách đánh nhãn thay đổi. Không giả định mọi workload có đúng một interface hoặc đi qua cùng datapath.

### 2.2. veth, bridge và CNI

Trong nhiều cấu hình Linux container, một cặp **virtual Ethernet (veth)** kết nối network namespace của pod với host networking. Một đầu veth ở pod, đầu kia ở node; CNI plugin có thể cấu hình bridge, routing, tunnels, eBPF datapath, policy hoặc IP address management.

~~~mermaid
flowchart LR
    subgraph POD["Pod network namespace"]
      APP["Application socket"]
      ETH["eth0 / Pod IP"]
      APP --> ETH
    end
    ETH --> VETH["veth endpoint"]
    VETH --> HOST["Node datapath<br/>bridge / routing / eBPF"]
    HOST --> NIC["Node NIC / underlay"]
    NIC --> OTHER["Other node / network"]
    HOST -. "Flow/policy observation" .-> COL["Telemetry collector"]
~~~

Sơ đồ chỉ mô tả **một mô hình thường gặp**, không bảo đảm CNI đang sử dụng Linux bridge hoặc host veth giống hệt. Có môi trường dùng routed datapath, eBPF hooks, overlay hoặc datapath được offload; vị trí hook quyết định bạn thấy **source/destination trước hay sau NAT, trước hay sau encapsulation**.

### 2.3. Pod IP, Service IP và Endpoint

| Khái niệm | Ý nghĩa | Điều cần nhớ khi điều tra |
| --- | --- | --- |
| **Pod IP** | Địa chỉ được cấp cho pod trong mạng cluster | Có thể đổi khi pod được thay hoặc IP bị tái sử dụng |
| **Container** | Tiến trình/ứng dụng chạy trong pod | Thường chia sẻ IP với container khác cùng pod |
| **Service ClusterIP** | Địa chỉ logic cung cấp một nhóm endpoints | Có thể được dịch đích tới một pod IP; không nhất thiết là server thực |
| **EndpointSlice** | Dữ liệu về endpoints phục vụ Service | Quan trọng để biết target khả dụng ở thời điểm cụ thể |
| **Node IP** | Địa chỉ node/host ở underlay | Có thể xuất hiện do SNAT hoặc overlay |
| **External IP / NAT egress IP** | Địa chỉ nhìn từ bên ngoài cloud/cluster | Nhiều pods/tenants có thể chia sẻ một IP |
| **Service account** | Danh tính Kubernetes cho workload truy cập API theo RBAC | Không tự đồng nghĩa network identity hoặc app user |
| **Workload owner** | Deployment/StatefulSet/DaemonSet/Job và chuỗi owner references | Phù hợp cho baseline lâu dài hơn tên pod tạm thời |

**Service name khác container name, pod UID và source IP.** Một HTTP request tới service frontend có thể được gán cho pod backend khác nhau sau load balancing, và proxy mesh có thể tạo thêm hop. Khi phân tích log, cần biết **flow quan sát ở tầng nào**.

### 2.4. Những kiểu đường đi cần phân biệt

| Luồng | Đường đi khái niệm | Điểm quan sát đáng cân nhắc |
| --- | --- | --- |
| **Trong cùng pod** | Container A → loopback → container B | Application/process/socket-level; loopback capture trong pod |
| **Cùng node, khác pod** | Pod A → node datapath → Pod B | veth/tc/eBPF/CNI flow log |
| **Khác node** | Pod A → node A → underlay/overlay → node B → Pod B | CNI, node underlay, tunnels, veth |
| **Pod → ClusterIP Service** | Pod → Service VIP → selected backend Pod | Service translation, conntrack, CNI/service-map telemetry |
| **Internet → ingress → pod** | Edge/LB → ingress controller → service/pod | Edge/WAF/LB logs, ingress L7, CNI, app |
| **Pod → Internet** | Pod → node/egress gateway/NAT → Internet | CNI egress flow, node/egress NAT, DNS, firewall |
| **Service mesh** | App → proxy/ambient component → proxy → app | Proxy access logs/traces + CNI/underlay |
| **Host network pod** | Pod tiến trình dùng host networking | Host/process telemetry, node firewall, socket owner |

Không lấy **đường đi một loại traffic** làm mô hình duy nhất cho toàn cluster. Khi có service mesh, hostNetwork, direct server return, externalTrafficPolicy hoặc egress NAT, gói tin có thể đi qua những điểm quan sát khác nhau.

## 3. Service routing, kube-proxy và NAT

### 3.1. Tại sao đích trong flow log không giống Service?

Client gọi Service ở ClusterIP, ví dụ:

~~~text
Request logic:
  namespace: shop
  service: catalog
  clusterIP: 10.96.0.25:8080

Selected endpoint:
  pod UID: catalog-pod-uid-7
  podIP: 10.244.2.17:8080

Flow quan sát trước destination translation:
  10.244.1.10:52144 -> 10.96.0.25:8080

Flow quan sát sau destination translation:
  10.244.1.10:52144 -> 10.244.2.17:8080
~~~

**Các địa chỉ trên chỉ là ví dụ topology nội bộ**, không phải dải Kubernetes bắt buộc. Một IP 10.96.x có thể dùng ở cluster A nhưng không có ở cluster B. Cần đọc cấu hình Pod CIDR/Service CIDR thực, không suy từ bài học.

Kubernetes có thể triển khai Service forwarding qua **iptables, IPVS hoặc eBPF-based service handling** tùy CNI/proxy mode/version. Endpoint selection, session affinity và NAT có thể khiến:

- Nơi quan sát trước DNAT thấy **Service VIP**.
- Nơi quan sát sau DNAT thấy **Pod endpoint**.
- Trong một số đường đi, source IP bị SNAT hoặc thay bằng node/egress gateway IP.
- Conntrack lưu mapping của luồng, hữu ích khi truy vết nhưng có TTL và có thể bị mất khi node restart.

### 3.2. Các trường cần lưu khi có NAT

Khi nhà cung cấp telemetry hỗ trợ, nên giữ cả **original tuple** và **translated tuple**, cộng thời điểm:

~~~text
Observed at: node-a / hook-pre-DNAT
Original:
  src=10.244.1.10:52144
  dst=10.96.0.25:8080
  protocol=TCP
Translated destination:
  dst=10.244.2.17:8080
Context:
  service=shop/catalog
  src_pod_uid=...
  dst_pod_uid=...
  time=...
~~~

Không phải mọi CNI flow record có đủ các trường trên; việc **không có translated tuple** khác với khẳng định không có NAT. Cần xác định khả năng của sensor và điểm gắn hook.

### 3.3. Overlay versus underlay

Một số CNI dùng **overlay tunneling** như VXLAN hoặc Geneve để đưa gói pod qua mạng giữa nodes. Quan sát tại **node NIC dưới lớp tunnel** có thể chỉ thấy:

~~~text
Outer traffic:
  node-a-IP:UDP → node-b-IP:tunnel-port

Inner traffic:
  pod-a-IP:TCP → pod-b-IP:service-port
~~~

Nếu packet capture tại underlay **không decapsulate** hoặc sensor chỉ ghi outer 5-tuple, bạn có thể nhầm nhiều kết nối pod với một luồng node-to-node. Tùy CNI, traffic có thể đi qua native routing, encapsulation, encrypted tunnel hay direct routing; không mặc định luôn có VXLAN hoặc tất cả inner metadata đều lộ.

### 3.4. Connection tracking và return traffic

**Conntrack** giúp hệ điều hành/firewall ghi trạng thái luồng, NAT mappings và cách phản hồi được xử lý. Dùng dữ liệu conntrack để đối chiếu:

- SYN/handshake có vào node và được forward không?
- NAT mapping nào được áp dụng?
- Một luồng đã tồn tại hay bị coi là NEW?
- Mức sử dụng conntrack table có cao và gây drops không?

**Conntrack record không tự xác thực user hay container**. Nó có thể chỉ cung cấp network tuples/state, và dữ liệu sau khi luồng kết thúc có thể bị xóa hoặc tái sử dụng. Khi làm incident timeline, phải giữ snapshot/log theo thời điểm thay vì dựa vào bảng conntrack hiện tại.

## 4. Sáu loại telemetry khác nhau

Quan sát mạng container không đồng nghĩa phải lưu **mọi packet**. Các nguồn có độ sâu, chi phí và độ nhạy dữ liệu khác nhau:

| Loại telemetry | Ví dụ trường | Trả lời tốt | Giới hạn |
| --- | --- | --- | --- |
| **L3/L4 flow logs** | Source/destination, ports, protocol, bytes, verdict, time | Ai kết nối tới ai, có bị policy drop? | Không biết nội dung HTTPS hoặc user thực |
| **Interface/socket metrics** | Packets, drops, retransmits, socket states, RTT | Nghẽn/timeout/loss ở đâu? | Không luôn gắn với request nghiệp vụ |
| **Packet capture (PCAP)** | Headers và packet bytes | Phân tích giao thức, handshake, DNS plaintext | Tốn dung lượng, nhạy cảm và có thể thiếu nội dung đã mã hóa |
| **DNS telemetry** | QNAME, response code, resolver, answer, latency | Workload tra tên nào, lỗi DNS gì? | DoH/DoT/cache/alternate resolver tạo điểm mù |
| **L7 access logs/traces** | HTTP/gRPC method, route, status, duration, trace ID | Endpoint nào bị lỗi, latency và service graph | Cần hook sau TLS termination/proxy/instrumentation |
| **Kubernetes control-plane events/audit** | Pod scheduled, identity, policy update, workload changes | Cái gì đã deploy/thay policy khi luồng xảy ra? | Không mô tả toàn bộ packet data plane |

**Không thể thay thế tất cả nguồn bằng một dashboard.** Flow log có thể cho thấy TCP connection được phép nhưng không biết ứng dụng trả HTTP 403; access log có thể ghi HTTP 500 nhưng không biết gói bị mất ở node trước đó; Kubernetes audit có thể ghi thay đổi NetworkPolicy nhưng không cho biết rule đang chặn packet nào.

### 4.1. Flow log không phải packet capture

Một flow log có thể **tổng hợp** nhiều packet thành một record, ghi byte/packet counts sau một khoảng hoặc chỉ khi flow kết thúc. Một vài record mô tả **verdict policy** chứ không phải toàn bộ byte thực sự đi qua. Các trường và độ chính xác tùy plugin/agent.

**Đừng suy ra** “đã ghi một flow FORWARDED” = “HTTP transaction thành công”. Mạng có thể cho phép TCP connection, nhưng TLS handshake, authorization hoặc backend business logic vẫn thất bại.

### 4.2. Packet capture quan sát sâu nhưng có giới hạn

Một PCAP có thể giúp phân tích TCP SYN/ACK/RST, DNS UDP plaintext hoặc VXLAN encapsulation. Nhưng:

- HTTPS/mTLS, IPsec và các tunnel mã hóa có thể che payload.
- Capture tại interface sai có thể chỉ thấy outer flow.
- Snaplen, capture filter, ring buffer hoặc packet drops có thể cắt mất packet.
- Hardware offload/GRO/GSO/TSO làm kích thước và số packet nhìn thấy khác wire capture.
- Packet trong pod loopback không xuất hiện ở host veth.
- PCAP có thể chứa secrets, cookies, tokens và dữ liệu cá nhân; chỉ thu thập có mục đích và phê duyệt.

### 4.3. Logs khác traces và metrics

- **Metric:** số đo tổng hợp qua thời gian (connection count, drop rate, RTT percentiles).
- **Log:** record sự kiện/flow/request có ngữ cảnh.
- **Trace:** các spans mô tả đường đi của một giao dịch qua nhiều dịch vụ, có thể dùng sampling.

Distributed traces tốt cho việc thấy request **checkout → payment → inventory**, nhưng không bao phủ mọi gói TCP hay các kết nối không được instrument. Ngược lại, packet capture không tự dựng được trace cho một transaction nếu thiếu correlation metadata.

## 5. Chọn điểm quan sát và hiểu giới hạn của mỗi điểm

~~~mermaid
flowchart TB
    INTERNET["External client"] --> EDGE["CDN / LB / Ingress"]
    EDGE --> P1["Pod frontend"]
    P1 --> SVC["Service VIP / routing"]
    SVC --> P2["Pod backend"]
    P2 --> EGRESS["Egress gateway / node NAT"]
    EGRESS --> EXT["External service"]
    EDGE -. "L7 access + WAF" .-> OBS["Observability pipeline"]
    P1 -. "Process / app / mesh" .-> OBS
    SVC -. "CNI/eBPF service translation" .-> OBS
    P2 -. "Flow/policy telemetry" .-> OBS
    EGRESS -. "Firewall/NAT logs" .-> OBS
~~~

### 5.1. Quan sát tại ingress

**Ingress controller, API gateway, reverse proxy hoặc cloud load balancer** là điểm phù hợp để ghi HTTP host/path/status, TLS handshake, policy action và request duration khi nó thực sự xử lý L7. Tuy nhiên, ở đây thường chỉ thấy các request **đi qua ingress**; giao tiếp pod-to-pod trực tiếp và egress pod ra Internet có thể không xuất hiện.

### 5.2. Quan sát tại veth/tc/eBPF

Trong Linux datapath, **traffic control (tc)** hoặc eBPF hooks có thể quan sát hay áp chính sách ở các điểm ingress/egress của interface. Khi CNI hỗ trợ ánh xạ tới network identity, dữ liệu có thể gắn **namespace, pod labels và policy verdict**.

Không có nghĩa **mọi eBPF program đều có thể giải mã TLS hoặc biết HTTP URL**. Thông tin quan sát được tùy hook (socket, tc, XDP, cgroup, kprobe/tracepoint), bối cảnh kernel và phần mềm cung cấp.

### 5.3. Quan sát tại node NIC

Node NIC hoặc cloud VPC flow logs có thể cho bức tranh traffic **giữa nodes, tới Internet hoặc tới dịch vụ cloud**, nhưng pod IP có thể đã bị NAT hoặc bị ẩn sau encapsulation. Node-to-node flow không đủ thay cho **pod identity-aware CNI logs** khi cần điều tra một namespace cụ thể.

### 5.4. Quan sát tại sidecar hoặc service mesh

Một sidecar hoặc proxy data plane có thể ghi **mTLS identity, service destination, HTTP route, response code và latency**, tùy chế độ mesh. Đây là dữ liệu hữu ích cho **east–west service communication**.

Điểm mù: traffic **không đi qua mesh proxy**, traffic UDP/giao thức chưa hỗ trợ, traffic trong cùng pod loopback, những endpoint miễn trừ hoặc proxy telemetry bị sampling. Mesh access log không thay thế CNI/network flow log và NetworkPolicy.

### 5.5. Quan sát bằng egress gateway/NAT

Ở egress, thường thấy public destination, DNS/HTTP proxy metadata hoặc NAT mappings. Nếu nhiều workloads dùng chung một egress IP, **IP nguồn bên ngoài không đủ xác định pod nào gửi**. Cần map **pod/service identity → gateway flow → external destination** và lưu theo thời điểm.

### 5.6. Quy tắc chọn hook

**Hãy bắt đầu bằng câu hỏi cần trả lời**, không phải bằng việc kích hoạt mọi loại sensor:

| Câu hỏi | Nguồn ưu tiên | Nguồn bổ trợ |
| --- | --- | --- |
| Pod nào bị NetworkPolicy chặn? | CNI policy verdict logs | Kubernetes policies, packet capture |
| HTTP 503 phát sinh ở ingress hay backend? | Ingress/mesh + app logs | Traces, target health |
| Vì sao Pod A không gọi được Pod B? | CNI flows, DNS, endpoints | Conntrack, TCP capture |
| Workload nào truy cập Internet? | CNI egress + NAT gateway logs | DNS logs, identity mapping |
| Có quét nhiều ports nội bộ? | Flows theo source/destination/port/time | IDS/IPS, endpoint runtime alerts |
| Tại sao lưu lượng giữa nodes cao? | Node interface metrics + CNI | Overlay capture, app traffic |
| Ai thay network policy? | Kubernetes audit + GitOps/IaC | CNI policy revision/verdict |

## 6. Liên kết network flow với danh tính container/workload

### 6.1. Vì sao IP và tên Pod không phải khóa định danh bền vững?

Kubernetes thường tạo tên pod kèm hậu tố ngẫu nhiên hoặc số thứ tự. Khi Deployment rollout, Job hoàn tất hoặc node mất kết nối, pod cũ có thể bị xóa và một pod mới nhận **IP từng thuộc pod khác**. Nếu SIEM hôm nay tra IP **10.244.2.17** bằng trạng thái Kubernetes hiện tại rồi gán cho flow xảy ra hôm qua, kết luận có thể sai.

**Danh tính nên ưu tiên theo mục đích:**

- **Pod UID:** định danh một pod instance trong vòng đời của nó.
- **Namespace và cluster UID/name:** tránh nhầm các pods/không gian trùng tên trên nhiều clusters.
- **Owner workload:** Deployment, StatefulSet, DaemonSet, Job/CronJob; hữu ích để gom các pod instance cùng ứng dụng.
- **Service account:** danh tính Kubernetes mà workload dùng để truy cập API; có thể bổ sung nhưng không mặc nhiên là danh tính mTLS.
- **CNI network/security identity:** có thể suy từ labels, selectors hoặc policy engine; semantics khác nhau giữa plugins.
- **Node UID/name, runtime/container ID:** dùng để phân biệt nơi chạy và tiến trình khi cần.
- **Thời điểm hiệu lực:** bắt buộc khi xét IP, labels, node assignment, policy revision và NAT mapping.

### 6.2. Ví dụ tái sử dụng Pod IP

~~~text
09:00–09:20 UTC:
  cluster=lab-east
  namespace=shop
  pod=checkout-7cbd-abc
  pod_uid=uid-111
  pod_ip=10.244.2.17

09:20:
  Pod uid-111 bị xóa.

10:30–11:10 UTC:
  namespace=monitoring
  pod=collector-52f-xyz
  pod_uid=uid-222
  pod_ip=10.244.2.17  (IP được sử dụng lại)

Flow lúc 09:10 tới 10.244.2.17:
  Phải đối chiếu uid-111, không được dùng mapping hiện tại uid-222.
~~~

Các tên/UID/IP trong ví dụ hoàn toàn giả lập. **Không được suy ra một CNI sẽ tái sử dụng địa chỉ sau đúng 70 phút**; ví dụ chỉ thể hiện lỗi thường gặp khi không lưu lịch sử mapping.

### 6.3. Một bản ghi flow chuẩn hóa gợi ý

~~~json
{
  "event_time_utc": "2026-11-28T09:10:00Z",
  "observed_at": "node-b/tc-ingress",
  "cluster_id": "lab-east",
  "node_id": "node-b",
  "source": {
    "pod_uid": "uid-source-01",
    "namespace": "shop",
    "workload": "checkout",
    "service_account": "checkout-sa",
    "ip": "10.244.1.10"
  },
  "destination": {
    "pod_uid": "uid-111",
    "namespace": "shop",
    "workload": "catalog",
    "ip": "10.244.2.17",
    "port": 8080
  },
  "protocol": "TCP",
  "policy_verdict": "FORWARDED",
  "bytes_observed": 1840,
  "policy_revision": "lab-policy-rev-17",
  "sensor_version": "lab-cni-v1"
}
~~~

Đây **không phải schema chuẩn của một CNI cụ thể**. Nó minh họa những thuộc tính nên có hoặc nên enrichment. Ví dụ **FORWARDED** phản ánh một verdict ở sensor đang xét, không có nghĩa request nghiệp vụ thành công. Nếu sensor không có dữ liệu về Pod UID, hãy ghi **unknown** và bổ sung bằng lookup có thời điểm; đừng tạo UID suy đoán rồi ghi như sự thật.

### 6.4. Pipeline enrichment theo thời gian

~~~mermaid
flowchart LR
    FLOW["Flow event<br/>5-tuple, time, node, verdict"] --> JOIN["Temporal join"]
    K8S["Pod/EndpointSlice events<br/>UID, IP, labels, owner"] --> JOIN
    NET["CNI/service/NAT records<br/>before/after translation"] --> JOIN
    JOIN --> NORMAL["Normalized event<br/>cluster + workload identity"]
    NORMAL --> SIEM["Search / SIEM / NDR"]
    NORMAL --> GRAPH["Service dependency graph"]
    NORMAL --> DETECT["Detection rules"]
~~~

Một hệ thống enrichment đáng tin cần giải quyết:

1. **Thời gian sự kiện** (*event time*) khác **thời gian log được ingest**.
2. Watch events có thể tới trễ hoặc mất khi collector ngừng.
3. CNI identity được tạo/cập nhật theo policy hoặc labels; một thay đổi label có thể thay bucket.
4. Service VIP và NAT khiến flow tuples ở hai hook không giống nhau.
5. Node restart, container restart hoặc pod migration có thể làm mất bản ghi tạm thời.
6. Một workload có thể có nhiều địa chỉ/interfaces (IPv4, IPv6, Multus).

**Không dùng lookup trực tiếp vào Kubernetes API ở thời điểm điều tra để thay thế lịch sử.** Cần snapshot hoặc event stream đủ để dựng mapping **đúng tại thời điểm flow xảy ra**.

### 6.5. Labels: hữu ích nhưng không tự là bằng chứng bảo mật

Kubernetes labels rất hữu ích để nhóm flow theo **team, app, environment, tier**. Nhưng một label có thể được thay bởi chủ thể có quyền sửa workload, và không phải mọi label đều do nền tảng đáng tin cấp.

Không tự coi **app=payments** là bằng chứng request đã được dịch vụ payment có quyền thực hiện. Nếu cần identity mạnh, sử dụng cơ chế **workload identity, mTLS/SPIFFE hoặc token có xác minh** và phân quyền tại ứng dụng; labels chỉ giúp diễn giải policy khi nguồn/owner được tin cậy.

## 7. Quan sát NetworkPolicy: Intended policy và effective enforcement

### 7.1. Kubernetes NetworkPolicy kiểm soát điều gì?

**Kubernetes NetworkPolicy** mô tả quy tắc ingress/egress cho **Pod selectors**, namespace selectors và các loại peer/port theo API. Việc thực thi phụ thuộc **CNI plugin** và khả năng hỗ trợ. NetworkPolicy truyền thống chủ yếu kiểm soát traffic theo các khái niệm **L3/L4**; các chính sách L7 nâng cao, deny rules hoặc DNS/FQDN rules thường là **mở rộng của từng CNI**, không phải những thuộc tính mặc định của mọi NetworkPolicy.

Theo mô hình policy chuẩn, với một kết nối pod-to-pod, cần xét **policy ingress tại destination** và **policy egress tại source** khi chúng được chọn/cách ly tương ứng. Các quy tắc allow có tính cộng dồn; việc một NetworkPolicy khác cho phép không bị phủ định đơn giản bằng cách thêm một policy allow rỗng. Hãy đọc semantics thực tế của plugin và API.

### 7.2. Default deny và quan sát drops

Ví dụ network policy **default deny ingress** cho các pod trong namespace **shop-lab**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: shop-lab
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Manifest chỉ là ví dụ để học, **không tự áp lên production**. Nó chọn tất cả pods trong namespace đó để cô lập ingress theo NetworkPolicy semantics, nhưng **không phải default deny egress**, cũng không phải firewall cho mọi node/host traffic. Phải có CNI hỗ trợ và test thực tế.

**Một điểm nguy hiểm khi phân tích flow:** một connection bị drop có thể do **NetworkPolicy, cloud security group, node firewall, route thiếu, DNS lỗi hoặc backend không listen**. Không gắn nhãn policy drop nếu telemetry chỉ thể hiện TCP timeout mà không có policy verdict đáng tin.

### 7.3. Selectors và quy tắc giữa namespaces

Giả sử chỉ cho pod gắn nhãn **role=frontend** ở namespace **web-lab** gọi TCP/8080 đến các pod **app=catalog** trong namespace **shop-lab**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-web-to-catalog
  namespace: shop-lab
spec:
  podSelector:
    matchLabels:
      app: catalog
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: web-lab
          podSelector:
            matchLabels:
              role: frontend
      ports:
        - protocol: TCP
          port: 8080
~~~

Lưu ý **namespaceSelector và podSelector ở cùng một phần tử trong from** nghĩa là **kết hợp cả hai điều kiện**. Nếu viết chúng thành hai phần tử danh sách riêng, kết quả có thể là **OR** rộng hơn dự kiến. Một sai khác thụt lề YAML có thể thay đổi phạm vi cho phép.

Manifest minh họa chỉ giới hạn **ingress** của catalog pods; để đạt policy end-to-end, cần kiểm tra **egress ở source**, DNS, kube-system dependencies, lối vào khác và app authorization.

### 7.4. Policy action khác network outcome

| Sensor event | Có thể suy ra | Không nên tự suy ra |
| --- | --- | --- |
| **Policy DROPPED** | Điểm thực thi đã từ chối theo một rule/verdict | User xấu hoặc dữ liệu đã bị lấy |
| **Policy FORWARDED** | Traffic vượt qua điểm enforcement cụ thể | Ứng dụng trả 200 hoặc user có quyền |
| **TCP RST** | Một bên/hop phản hồi reset | Chắc chắn firewall block |
| **TCP retransmissions** | Có packet không được ACK/nhận đúng thời gian | Chắc chắn CNI lỗi |
| **DNS NXDOMAIN** | Resolver báo không tìm được tên | Chắc chắn DNS tunneling |
| **HTTP 403** | L7 server/proxy từ chối theo chính sách | Chắc chắn NetworkPolicy chặn |
| **gRPC UNAVAILABLE** | L7 request không hoàn thành do vấn đề availability | Chắc chắn pod network packet drop |

Nên bổ sung **policy name/UID/revision, direction, endpoint identity, node và time** vào record nếu CNI hỗ trợ, cùng **mức tin cậy của nguồn bằng chứng**.

### 7.5. CNI-specific policy/flow logs

Các CNI như **Cilium, Calico** và một số giải pháp cloud-native có cách thực thi policy và tạo telemetry khác nhau; tính năng có thể phụ thuộc edition, mode, CRDs, kernel và các agent chạy trên node.

- **Cilium/Hubble** có thể cung cấp flow observation dựa trên datapath eBPF, identities và policy verdicts; một số L7 observations phụ thuộc cấu hình proxy/policy và feature support.
- **Calico** có thể cung cấp flow/policy logs theo các thành phần/edition/config được hỗ trợ; không tự mặc định mọi bản Calico cài sẵn đầy đủ flow logs.
- **Cloud VPC flow logs** thường tập trung vào lớp network interface/hạ tầng; khả năng map đến pod và visibility trước/sau NAT khác CNI flow logs.
- **Service mesh telemetry** phản ánh proxy/service traffic được mesh xử lý, không thay CNI policy verdict.

**Chọn datasource theo điều thực sự cần xác minh**, không dựa vào tên sản phẩm. Kiểm tra documentation của phiên bản và quyền thu thập trước khi bật ghi toàn cluster.

## 8. Quan sát bằng eBPF và điểm gắn kernel

### 8.1. eBPF giúp gì?

**eBPF (extended Berkeley Packet Filter)** cho phép chạy chương trình được kiểm tra/giới hạn theo cơ chế kernel ở những hook nhất định. Công cụ observability có thể dùng eBPF để thu thập **network events, socket metadata, drops, DNS flows hoặc policy verdicts** với ngữ cảnh process/cgroup/pod tùy thiết kế.

**eBPF không phải một công cụ duy nhất**. Hai sản phẩm “đều dùng eBPF” có thể quan sát hoàn toàn khác: một sản phẩm gắn ở socket/cgroup, sản phẩm khác ở tc/XDP, sản phẩm thứ ba dùng kprobes hoặc tracepoints.

### 8.2. Những hook thường được nhắc đến

| Hook/điểm gắn | Dữ liệu thường có thể nhìn | Điểm mù/cảnh báo |
| --- | --- | --- |
| **XDP** (rất sớm trong ingress driver path) | Packet metadata, early drop, L3/L4 | Trước một số bước xử lý, không tự có Pod identity hoặc payload sau TLS |
| **tc ingress/egress** | Packet headers, interface, policy/routing context | Thứ tự so với NAT/overlay thay đổi theo datapath |
| **cgroup socket hooks** | Connect/bind/sendmsg context theo process/cgroup | Không thay quan sát mọi packet trên wire |
| **tracepoints/kprobes** | Kernel events, drops, sockets/conntrack tùy chương trình | Có rủi ro compatibility/version và overhead |
| **Userspace proxy instrumentation** | HTTP/gRPC method, route, response, mTLS identity | Chỉ traffic đi qua proxy, có thể sampling |

### 8.3. eBPF có đọc được HTTPS không?

Thông thường, một hook mạng ở kernel nhìn traffic **đang được truyền dưới dạng TLS ciphertext**, không tự có HTTP URL/body plaintext. Một số giải pháp quan sát L7 ở process/library hoặc proxy layer có thể nhìn được dữ liệu **trước khi mã hóa hoặc sau giải mã** trong phạm vi quyền và hỗ trợ riêng, nhưng điều đó không phải khả năng mặc định của mọi eBPF agent.

Khi thiết kế security telemetry:

- Đừng ghi “eBPF giám sát toàn bộ payload HTTPS” nếu không xác minh điểm instrumentation.
- Tách **TLS handshake/connection metadata** khỏi **nội dung HTTP**.
- Xác định nơi traffic thực sự được terminate/decrypt.
- Tuân thủ privacy, data minimization và quyền kiểm soát instrumentation.

### 8.4. Event drops và overhead

eBPF event collectors thường sử dụng buffers và userspace agents để xuất dữ liệu. Với lưu lượng cao, có thể có:

- Ring/perf buffer overflow hoặc event loss.
- Sampling rate làm bỏ qua một phần flows.
- CPU/memory overhead ở node hoặc collector.
- Cardinality cao theo pod/IP/port/labels.
- Phiên bản kernel/agent thiếu feature.
- Collector bị mất kết nối tới backend log.

**Không có event không có nghĩa không có traffic.** Luôn giám sát **sensor health, buffer drops, agent restarts và pipeline delivery latency**.

## 9. DNS telemetry và egress visibility

### 9.1. DNS là nguồn tín hiệu gì?

DNS query/response logs có thể chỉ ra workload đang hỏi tên miền nào, trả kết quả nào, tần suất, lỗi NXDOMAIN/SERVFAIL và thời gian phân giải. Điều này hữu ích để:

- Phát hiện ứng dụng dùng resolver sai hoặc bị lỗi cấu hình DNS.
- Phân tích egress đến tên miền mới hoặc không thuộc policy.
- Tương quan kết nối IP với tên miền đã được workload phân giải.
- Nhận diện dấu hiệu DNS exfiltration/tunneling ở mức **nghi vấn cần kiểm tra**, không kết luận từ một chuỗi tên miền lạ.

### 9.2. CoreDNS, NodeLocal DNSCache và cache trong ứng dụng

Trong Kubernetes, DNS có thể được phục vụ bởi **CoreDNS** hoặc cơ chế resolver tương đương; **NodeLocal DNSCache** có thể giảm độ trễ và chuyển hướng DNS path trên node. Ứng dụng cũng có thể cache tên, hardcode IP, dùng IP endpoint trực tiếp hoặc gọi resolver ngoài cluster.

Vì vậy:

- Một DNS query tới CoreDNS không luôn tương ứng một HTTP request.
- Một kết nối TCP mới không nhất thiết tạo DNS query mới.
- DNS query có thể gắn với node/cache hơn là pod nếu log thiếu source context.
- DNS response có thể chứa nhiều A/AAAA records và TTL khác nhau.
- Một tên miền có thể trỏ tới nhiều địa chỉ hoặc dùng CDN; không coi IP sau đó là danh tính ứng dụng cố định.

### 9.3. DoH/DoT, encrypted DNS và những trường hợp không thấy query

Nếu workload dùng **DNS over HTTPS (DoH)**, **DNS over TLS (DoT)**, một resolver riêng hoặc DNS proxy ở sidecar, DNS logs truyền thống của CoreDNS có thể **không nhìn thấy** truy vấn. Traffic tới IP trực tiếp cũng không đi qua DNS.

Đừng kết luận “không có DNS event là ứng dụng không truy cập Internet”. Cần đối chiếu **egress flow/NAT logs, runtime configuration và DNS controls**.

### 9.4. Egress qua NAT/gateway

Một egress gateway có thể ghi:

~~~text
Observed at cluster egress:
  source private: 10.244.2.17:52144
  translated source: gateway-public-IP:60018
  destination: external-IP:443
  protocol: TCP
  time: 09:10 UTC
~~~

NAT gateway flow chỉ cho biết địa chỉ/ports tại điểm đo; để quy kết tới một pod cần **source Pod UID mapping theo thời điểm**, connection tuple/port mapping và các proxy hops trung gian.

### 9.5. DNS allowlist và FQDN-based egress policy

Một số CNI/proxy cho phép policy dựa trên DNS/FQDN, nhưng phải hiểu:

- Kết nối IP có thực sự được ràng buộc với DNS answer đã được tin không?
- Cách cache và TTL hoạt động, khi record thay đổi hoặc có nhiều answers.
- IPv6 addresses và traffic không dùng DNS.
- Workload có được phép dùng resolver tùy ý?
- FQDN policy có được áp trên tất cả egress paths hay bị bỏ qua qua hostNetwork/privileged paths?

**FQDN allowlist không tự là xác thực danh tính server.** HTTPS vẫn cần TLS hostname/certificate verification, và client phải kiểm tra đúng quyền truy cập dịch vụ.

## 10. Service mesh, sidecar và ambient networking

### 10.1. Mesh thay đổi đường đi quan sát như thế nào?

Một service mesh có thể chèn **proxy sidecar**, **node-level/ambient proxy** hoặc cơ chế tương đương để cung cấp mTLS, routing, retries, traffic policy và telemetry. Thay vì ứng dụng gọi trực tiếp pod đích, đường truyền có thể:

~~~mermaid
sequenceDiagram
    participant A as App trong Pod A
    participant PA as Mesh proxy nguồn
    participant PB as Mesh proxy đích
    participant B as App trong Pod B
    A->>PA: Request tới service
    Note over PA: Ghi identity, route, timing nếu được cấu hình
    PA->>PB: Kênh mTLS / datapath mesh
    Note over PB: Xác minh peer và policy nếu được áp
    PB->>B: Chuyển request nội bộ
    B-->>PB: Response
    PB-->>PA: Response qua mesh
    PA-->>A: Trả response
~~~

Sơ đồ mô tả một **logical proxy-to-proxy path**; ambient mesh, waypoint/L7 proxies và những mode khác có cách triển khai riêng. Không mặc định mọi hop trong mesh đều có L7 access log, hoặc tất cả traffic chạy qua sidecar.

### 10.2. Network identity và application identity

**mTLS workload identity** có thể gắn với service account, namespace, SPIFFE identity hoặc loại principal khác tùy hệ thống. Nó chứng minh **đầu cuối kết nối** khi chain và certificate policy được xác thực; không tự chứng minh user cuối cùng trong HTTP request đã được ủy quyền.

Khi một API nhận request từ service frontend:

- Mesh có thể biết **frontend workload identity**.
- API có thể biết **end-user identity** qua JWT/session đã xác thực.
- CNI có thể ghi **pod IP/network security identity**.
- Kubernetes audit có thể biết **ai cập nhật Deployment**.

Các identity này **không được trộn lẫn**. Ví dụ một request qua frontend workload hợp lệ vẫn có thể là user chưa được phép đọc dữ liệu của tenant khác.

### 10.3. Sidecar có thể làm sai cách đếm flow

Nếu app → local proxy → remote proxy → app được ghi ở nhiều hook, một logical API call có thể tạo **nhiều flow records**. Không cộng mọi byte ở mỗi hook rồi coi là byte dữ liệu nghiệp vụ duy nhất; có thể đếm hai lần hoặc nhiều lần.

Đặt trường **observation_point, traffic_direction, transport tuple và trace/span correlation** để phân biệt:

1. App → local sidecar.
2. Sidecar → remote workload/proxy.
3. Remote sidecar → app.

Trong chế độ TLS, các gói từ proxy tới proxy còn có handshake, retries và framing overhead; bytes trên wire không nhất thiết bằng kích thước HTTP payload.

### 10.4. Điểm mù của mesh

- Pods chưa được enroll vào mesh.
- Traffic đi qua **hostNetwork**, node agents hoặc egress paths ngoài interception.
- Lưu lượng một số giao thức/ports được loại khỏi mesh policy.
- Loopback trong pod hoặc giao tiếp local không qua proxy.
- L7 telemetry bị tắt/sampling để giảm chi phí.
- Proxy chỉ có L4 mTLS identity nhưng không được cấu hình L7 interception/waypoint phù hợp.

Không viết một policy “mTLS bắt buộc cho mọi dịch vụ” chỉ dựa trên việc namespace có label mesh injection. Cần **kiểm thử enforcement và traffic path thực**.

## 11. Ingress/egress và bối cảnh cloud

### 11.1. Ingress logs cho điều gì?

Khi request đi qua cloud LB, API gateway, ingress controller hoặc reverse proxy, có thể ghi:

- Request host, route/method, status, bytes, latency và request ID.
- TLS termination point, protocol, client certificate identity nếu có mTLS.
- WAF/rate-limit actions, backend pool/service và target errors.
- Source IP đã được chuẩn hóa qua **trusted proxy chain**.

**X-Forwarded-For, Forwarded và PROXY protocol** chỉ đáng tin khi các hops được cấu hình/giới hạn kết nối hợp lệ. Dùng raw XFF từ Internet làm khóa rate limit có thể dẫn tới né giới hạn, sai nguồn log hoặc chặn oan người dùng chung NAT.

### 11.2. CNI, ingress controller và app đều cần tương quan

~~~text
One user request:
  Edge LB log:
    request_id=r-100, status=200, target=ingress-controller

  Ingress log:
    request_id=r-100, upstream=checkout.shop.svc, status=200

  CNI flow:
    source=ingress-pod, destination=checkout-pod, verdict=FORWARDED

  Application trace:
    trace_id=t-200, operation=POST:/checkout, status=success
~~~

Các IDs là ví dụ; hệ thống thật có thể phải cấu hình propagation. Một flow CNI thường **không có HTTP request ID**, nên tương quan cần **time window + source/destination pod + tuples + tracing metadata tại L7**. Không tạo quan hệ “một flow = một HTTP request” khi HTTP keep-alive hoặc HTTP/2 multiplexing dùng chung kết nối.

### 11.3. Egress policies và cloud NAT

Một pod kết nối tới một HTTPS API bên ngoài có thể qua:

~~~text
Pod IP → CNI routing → Node SNAT → Cloud NAT/egress gateway
       → Cloud firewall → Internet
~~~

Tùy cloud/CNI, một số bước được bỏ qua hoặc thay bằng private endpoints/proxy. Để truy vết:

1. Xác định traffic **thực sự đi qua egress gateway nào**.
2. Tìm NAT mappings gắn với thời điểm và TCP/UDP ports.
3. Kiểm tra DNS name đã được resolver tin cậy cung cấp (nếu có).
4. Liên kết source tới Pod UID/service/workload.
5. Đối chiếu policy egress và firewall decisions.

Nếu chỉ biết public egress IP, **không thể kết luận** chính xác pod nào phát sinh yêu cầu khi hàng trăm pods dùng chung gateway.

### 11.4. Kubernetes NetworkPolicy không thay cloud SG/NSG

| Lớp | Bảo vệ điển hình | Không thay thế |
| --- | --- | --- |
| **Cloud firewall/SG/NSG** | Node/VM/network interface ingress/egress, subnet/route boundaries | Pod identity và application authorization |
| **CNI NetworkPolicy** | Pod-to-pod ingress/egress theo selectors và peer/port semantics | Cloud public LB, host firewall, DNS/web auth |
| **Service mesh** | Workload mTLS và có thể L7 authorization | Cloud SG/NACL hoặc mọi lưu lượng không qua mesh |
| **Ingress WAF** | L7 request protection trên traffic đi qua nó | East–west traffic và direct origin bypass |
| **App authorization** | User/tenant/resource operations | Routing, network segmentation và volumetric DDoS |

Một thiết kế phòng vệ đầy đủ phải **kiểm tra cùng một request qua các lớp tương ứng**, không xem “policy tồn tại” là bằng chứng chắc chắn traffic bị chặn.

## 12. Quan sát traffic được mã hóa

### 12.1. TLS làm thay đổi điều gì?

Với HTTPS/mTLS, network sensors có thể nhìn:

- Source/destination IP/port/protocol và packet counts.
- Một số thông tin handshake và connection metadata theo protocol/version.
- Packet lengths, direction, timing, retransmissions.
- Có thể có SNI trong một số TLS modes, nhưng **không mặc định** SNI luôn hiện rõ nếu ECH hoặc các biến thể privacy được dùng.

Sensors **không tự thấy** HTTP method, URL, status, JSON body hoặc dữ liệu ứng dụng đã mã hóa. Nếu cần L7 visibility hợp lệ, thu thập tại **TLS termination point, application instrumented span hoặc proxy có quyền quan sát**.

### 12.2. Service mesh mTLS và endpoint telemetry

Mesh có thể biết workload identities/peer authorization dù node capture thấy TLS ciphertext. Trong khi đó app có thể log route/status sau khi proxy giải mã. Để diễn giải đúng, gắn:

~~~text
network observed:   Pod A -> Pod B TCP/15008, encrypted
mesh observed:      principal=shop/checkout -> shop/catalog
application traced: GET /items, response HTTP 200
~~~

Port **15008** chỉ là ví dụ thường được nhắc tới trong một số mesh modes, **không phải cổng chuẩn chung cho mọi mesh**. Cần xem cấu hình thật; không áp firewall theo số này khi chưa biết datapath và sản phẩm.

### 12.3. TLS inspection có rủi ro riêng

Không bật **giải mã và lưu toàn bộ HTTP payload** chỉ vì muốn tăng visibility: điều đó có thể thu thập mật khẩu, cookie, thông tin khách hàng và bí mật ứng dụng. Nếu có nhu cầu đặc biệt được phê duyệt, phải xác định:

- Mục đích và phạm vi thu thập.
- Điểm termination được quản trị, quyền truy cập keys/telemetry.
- Không lưu tokens/credentials/raw payload ngoài nhu cầu.
- Thời hạn giữ, kiểm soát truy cập, audit và chính sách pháp lý.
- Cách loại bỏ dữ liệu nhạy cảm trước khi đưa vào pipeline.

**Flow metadata + các application security events đã chọn** thường hữu ích hơn việc sao chép toàn bộ dữ liệu người dùng vào một hệ thống tập trung.

## 13. Metrics kỹ thuật và health của mạng container

### 13.1. Những loại số liệu có ý nghĩa

| Metric | Phản ánh | Khi bất thường, cần xét |
| --- | --- | --- |
| **Flows/s và bytes/s theo workload** | Lượng giao tiếp/volume | Deploy, batch jobs, loop, abuse hoặc retry |
| **Policy drops theo namespace/source/dest** | Những kết nối bị network policy chặn | Rule thay, policy mới, sai labels hoặc traffic lạ |
| **TCP SYN/handshake failures** | Khó kết nối transport | Pod chưa listen, firewall, routing, conntrack |
| **TCP retransmits/RTT** | Chất lượng truyền tải | Packet loss, MTU, queueing hoặc congestion |
| **Conntrack usage/evictions/drops** | Áp lực connection tracking | NAT/flow churn, limit thấp, burst traffic |
| **DNS latency/NXDOMAIN/SERVFAIL** | Sức khỏe phân giải tên | CoreDNS, NodeLocal cache, upstream resolvers |
| **HTTP/gRPC p95/p99 latency** | Trải nghiệm request được instrument | Ứng dụng, mesh proxy, DB, timeout |
| **Ingress/egress total bytes** | Tài nguyên network | NAT costs, exfil hypothesis, backup jobs |
| **Mesh authn/authz denials** | Kiểm soát danh tính/service policy | Cert rotation, policy drift, service migration |
| **Packet/flow export drops** | Mất coverage quan sát | Collector overload, ring buffer, sampling |
| **Interface errors/drops** | Sức khỏe network node/interface | NIC, veth, CNI, kernel/offload |
| **NetworkPolicy coverage** | Tỷ lệ workloads có kiểm soát | Shadow workloads, namespaces mới, CNI support |

**Không nên dùng request latency làm đại diện duy nhất cho network latency.** HTTP p99 còn chứa thời gian ứng dụng xử lý và DB; RTT từ socket có thể bình thường khi backend CPU đã quá tải.

### 13.2. “Tăng throughput” không chứng minh network khỏe

Khi một pod gửi rất nhiều dữ liệu, throughput có thể tăng nhưng đồng thời **packet drops, retransmissions và queue delay** cũng tăng. Ngược lại traffic rất ít có thể là triệu chứng app không thể tạo kết nối chứ không phải dịch vụ ít người dùng.

Nên có dashboard đồng thời cho **traffic volume, error/drop ratio, latency, target availability và network policy decisions**.

### 13.3. Metric cardinality và retention

Một cluster nhiều pod có thể sinh hàng triệu tổ hợp:

~~~text
cluster × namespace × pod × destination IP × port × verdict × label
~~~

Nếu dùng toàn bộ tổ hợp làm **metric labels**, hệ thống time-series có thể tăng chi phí/CPU/storage đột ngột. Chỉ nên dùng labels có cardinality phù hợp (cluster, namespace, workload, policy, verdict); dữ liệu chi tiết theo IP/Pod UID nên đưa vào **event logs có retention/chiến lược tìm kiếm** phù hợp.

### 13.4. Phân biệt signal với ground truth

Metric “policy_drops tăng 300%” có thể do:

- Policy vừa được triển khai và đang **chặn traffic không cần thiết** đúng mục đích.
- App mới bắt đầu gọi nhầm service/port.
- Client retry loop sau network outage.
- Runtime bug hoặc sự kiện tấn công.

Nên gắn thông tin **deploy/change window, owner, baseline, policy revision** và xem sample events trước khi kết luận.

## 14. Thiết kế pipeline observability cho container network

~~~mermaid
flowchart TD
    CNI["CNI/eBPF flow + policy verdicts"] --> AGENT["Collectors / Agents"]
    MESH["Mesh / Ingress L7 logs"] --> AGENT
    DNS["DNS logs"] --> AGENT
    K8S["Kubernetes lifecycle + audit"] --> AGENT
    NODE["Node / conntrack / metrics"] --> AGENT
    AGENT --> QC["Normalize, parse, schema & loss checks"]
    QC --> ENRICH["Temporal enrichment<br/>cluster, pod UID, owner, NAT"]
    ENRICH --> STORE["Metrics / log store / traces"]
    STORE --> VIS["Dashboards + service map"]
    STORE --> DET["Detection + SOC / alerting"]
    DET --> FEED["Investigation + detector feedback"]
    FEED -. "Rule tuning" .-> DET
~~~

### 14.1. Thu thập theo điểm đặt hợp lý

Một số tác vụ cần **node-level DaemonSet** để thu thập flows từ tất cả pods/node. Một số khác dùng **sidecar/mesh proxy telemetry**, **cloud-native flow logs** hoặc **Kubernetes API watches**. Không cài mọi agent ở chế độ privileged chỉ vì “để giám sát tốt hơn”.

Cần review:

- Node agent cần quyền gì (CAP_BPF/CAP_NET_ADMIN/CAP_NET_RAW, host PID/network, BPF filesystem, kernel access)?
- RBAC nào cần để xem Pods, Nodes, EndpointSlices, NetworkPolicies và Events?
- Telemetry được gửi đi qua TLS, xác thực và network policy nào?
- Khi agent lỗi có ảnh hưởng data plane/CNI policy không?
- Có thể sampling/filter trước khi xuất để giảm tải và dữ liệu nhạy cảm không?

Một số platform **đã tích hợp flow exporter**, do đó cài agent thứ hai có thể làm lặp event hoặc tăng chi phí vô ích.

### 14.2. Chuẩn hóa một flow record

Các trường tối thiểu thường có:

- **event_time, ingest_time**, sensor/collector ID và clock provenance.
- **cluster, node, namespace, pod UID, workload owner** nếu có bằng chứng.
- **source/destination network tuple**, transport protocol, direction.
- **verdict/action**, policy ID/revision nếu nguồn hỗ trợ.
- **bytes, packets, latency/duration** và định nghĩa đơn vị/aggregation.
- **observation point**, NAT/encapsulation context và khả năng sampling.
- **sensor version, collection status, parse errors**.

Trường nào không đo được thì ghi **unknown/not_collected**. Không biến sự thiếu vắng **pod UID** thành giá trị Pod UID suy đoán từ tên DNS hoặc IP hiện tại.

### 14.3. OpenTelemetry và công cụ tập trung

**OpenTelemetry (OTel)** cung cấp các cơ chế instrumentation/export cho **metrics, logs và traces**; OTel Collector có thể gom và định tuyến telemetry theo cấu hình receiver/processor/exporter. Nhưng **OTel không tự động tạo network flow records từ kernel** chỉ vì cài Collector. Cần có nguồn như CNI/eBPF, proxy/access logs hoặc exporter tương thích.

Khi chuẩn hóa, tránh khai báo các trường vendor-specific là những attributes chuẩn nếu không có mapping rõ. Đặt tên schema nhất quán cho service, namespace, pod, network peer, response status và event time theo đặc tả/tổ chức đang dùng.

### 14.4. Sức khỏe pipeline quan trọng như detection rules

Theo dõi:

| Pipeline indicator | Tình huống cần phát hiện |
| --- | --- |
| Agent/DaemonSet coverage theo node | Node mới chưa được cài sensor hoặc sensor crash |
| Receiver/collector queue | Log bị tồn đọng |
| Dropped event/sampling rate | Mất một phần quan sát |
| Parse/schema errors | CNI upgrade đổi định dạng record |
| Export errors/retries | SIEM/log backend unavailable |
| Time-to-search latency | Incident timeline bị trễ |
| Kubernetes watch reconnect/gaps | Mất mapping pod IP/UID theo thời gian |
| Storage retention/partition health | Không thể truy vấn lịch sử cần thiết |

**Một bảng điều khiển không có alert** có thể vì hệ thống an toàn, nhưng cũng có thể do agents chết, records bị drop hoặc rule bị disable. Thực hiện **synthetic/known-good observation tests** được phê duyệt để kiểm chứng luồng dữ liệu.

### 14.5. Quyền riêng tư và bảo vệ bằng chứng

Flow logs có thể tiết lộ địa chỉ nội bộ, kiến trúc microservices, tên domain và thời gian hoạt động. L7 logs có thể chứa URL nhạy cảm, headers hoặc nội dung ứng dụng.

Hãy:

1. Chỉ thu thập trường thực sự phục vụ mục đích rõ ràng.
2. **Không ghi password, JWT, API key, cookie, private key, request body nhạy cảm** vào log mặc định.
3. Giới hạn quyền xem PCAP và logs; audit truy cập và chia sẻ.
4. Áp retention và mã hóa phù hợp với dữ liệu, luật và chính sách tổ chức.
5. Pseudonymize/hashing khi làm dashboard tổng hợp nếu không cần biết cá nhân.
6. Tách log lưu bằng chứng sự cố khỏi hệ thống vận hành thông thường khi cần chain of custody.
7. Đảm bảo collector không trở thành **đường egress tự do** ra ngoài tổ chức.

**Tăng observability không được biến thành một kho tập trung chứa bí mật của mọi ứng dụng.**

## 15. Baseline traffic container và dựng service dependency map

### 15.1. Baseline cần theo workload, không chỉ pod

Pod có thể được tái tạo mỗi lần rollout, nên baseline phù hợp thường được nhóm theo **workload owner (Deployment/StatefulSet), namespace, service account, route và môi trường**. Những thuộc tính hữu ích:

| Đặc trưng | Ví dụ baseline hợp lệ | Khi thay đổi cần xem |
| --- | --- | --- |
| Workload → workload | frontend → catalog → inventory | App mới gọi payment/admin service |
| Source/destination namespace | shop → shop-data | Shop pod bắt đầu gọi namespace kube-system |
| Destination port/protocol | catalog → database TCP/5432 | Kết nối đến cổng SSH/RDP hoặc service lạ |
| Egress domains/ASNs | Nền tảng thanh toán và telemetry cho phép | Gọi domain mới hoặc IP không rõ mục đích |
| DNS query rate/NXDOMAIN | Query ổn định trong chu kỳ deploy | Rất nhiều tên ngẫu nhiên hoặc lỗi resolver |
| Bytes/flows per workload | Đặc trưng theo job/app role | Upload bất thường, vòng lặp retry hoặc batch |
| Policy drop rate | Gần 0 hoặc có deny đã biết | Rule drift, quét lateral, service vừa di chuyển |
| L7 status/latency | HTTP 2xx/4xx/5xx theo API | Tăng 5xx hoặc handshake errors |
| Connections/concurrency | Mức tải app bình thường | Conntrack exhaustion hoặc sudden burst |
| Encryption/identity | mTLS từ workloads được phép | Traffic đi ngoài mesh hoặc cert failures |

**Không dùng một ngưỡng cố định cho mọi namespace.** Jobs import dữ liệu, service backup hoặc CronJob có thể tạo lưu lượng lớn đúng lịch; service login và control plane cần bảo vệ theo mục tiêu khác.

### 15.2. Dựng sơ đồ quan hệ phụ thuộc

Service graph có thể dựa trên các flow edges:

~~~mermaid
flowchart LR
    FE["namespace web / frontend"] -->|"HTTP/443"| CART["namespace shop / cart"]
    FE -->|"HTTP/443"| CAT["namespace shop / catalog"]
    CART -->|"TCP/6379"| CACHE["namespace data / cache"]
    CART -->|"TCP/5432"| DB["namespace data / database"]
    CAT -->|"HTTPS/443"| EXT["External inventory API"]
    CART -. "Deny to kube-system" .-> KUBE["Kubernetes system services"]
~~~

Hình thể hiện **logical workload dependencies**, không phải sơ đồ vật lý node-to-node. Để xây đúng, cần giải quyết:

- Các flows tới Service VIP được map tới đúng service/endpoint.
- Cùng connection được quan sát ở nhiều hooks không bị tính thành nhiều dependencies độc lập.
- Pod IP reuse không gắn flow cũ vào workload mới.
- NAT/mesh proxy không che identity của logical caller.
- Edges có **độ tin cậy** và thể hiện rõ **observed/allowed/dropped**.

### 15.3. Baseline để thiết kế least-privilege, không tự động mở quyền

Quan sát vài tuần có thể cho biết workload thường kết nối tới những đích nào. Nhưng **“đã từng thấy traffic” không đồng nghĩa “phải cho phép”**. Một luồng trái phép hoặc bị malware điều khiển vẫn có thể xuất hiện trong dữ liệu.

Trước khi chuyển observed service graph thành **NetworkPolicy allowlist**:

1. Xác nhận owner/role của các dependencies.
2. Kiểm tra cả hoạt động hiếm nhưng hợp lệ (backup, failover, certificate renewal).
3. Phân biệt DNS/control-plane traffic và business traffic.
4. Thử lab/staging, bắt đầu bằng policy rõ ràng và quan sát effects.
5. Cần rollback có kiểm soát để không chặn DNS/health/telemetry quan trọng.

### 15.4. Change events làm “ngữ cảnh” cho bất thường

Một workload bắt đầu gọi service mới ngay sau deploy có thể hợp lệ; cũng có thể do thay config sai hoặc bị chèn dependency. Correlate:

- Deployment/Helm/GitOps release và image digest.
- Pod scheduling/restart, node migrations và autoscaling.
- NetworkPolicy/CNI policy revisions.
- DNS changes, service/endpoints updates.
- Secret rotation, mTLS trust changes, firewall/ingress configs.
- Incident/maintenance window đã được duyệt.

Không nên **tắt toàn bộ detector trong deployment window**: attacker cũng có thể lợi dụng khoảng “ồn ào”. Hãy gắn context để ưu tiên và triage chính xác.

## 16. Các use case phát hiện an ninh dựa trên lưu lượng container

### 16.1. East–west lateral scanning

**Dấu hiệu:** một pod vốn chỉ gọi một API bắt đầu thử kết nối tới nhiều pod IP, namespace, ports hoặc services, đặc biệt những cổng quản trị không thuộc vai trò.

**Tín hiệu:** count_distinct(destination_pod), count_distinct(destination_port), failed connection rate, policy drops và workload history trong một cửa sổ thời gian.

**Có thể hợp lệ:** service discovery, health probes, security scanner đã phê duyệt, quá trình migration hoặc test kết nối tự động. Vì vậy **không kết luận quét tấn công chỉ từ số port**; cần owner, baseline, tool identity và approval.

### 16.2. Egress tới địa chỉ mới hoặc ngoài policy

**Dấu hiệu:** pod web nội bộ không có lý do gọi Internet bắt đầu kết nối liên tục tới IP/ASN/domain mới, nhất là từ namespace dữ liệu nhạy cảm.

**Cần đối chiếu:** DNS logs, CNI egress flow, NAT mapping, service account, change history và mục đích nghiệp vụ. Tên miền mới có thể là CDN, upstream vendor mới hoặc proxy hợp lệ.

**Cần nhớ:** public IP NAT không đủ để quy kết tới một pod; policy egress chỉ có ý nghĩa nếu traffic đi qua điểm enforcement.

### 16.3. Mất ranh giới mạng giữa namespaces

**Dấu hiệu:** workload ở namespace **public-web** có đường đến một namespace **admin/data** mà kiến trúc dự kiến không cho phép.

**Kiểm tra:** NetworkPolicy effective selectors, CNI support, ingress/egress isolation, cloud SG/NSG, hostNetwork và các lối đi NodePort/Service khác. **Một flow FORWARDED tại một hook chưa chứng minh ứng dụng data chấp nhận yêu cầu**; nhưng nó có thể cho thấy ranh giới L3/L4 không đủ nếu mục tiêu là chặn kết nối.

### 16.4. Bất thường DNS và dấu hiệu tunneling

Các tín hiệu có thể gồm **tăng mạnh truy vấn**, rất nhiều subdomains có độ ngẫu nhiên cao, NXDOMAIN ratio tăng hoặc record types/lengths khác thường. Đây là tín hiệu đáng điều tra; các hệ thống telemetry, service discovery hoặc app bị lỗi cũng có thể sinh patterns tương tự.

Không đưa payload DNS raw chứa secrets vào SIEM không được bảo vệ; giảm nhạy cảm bằng aggregation/pseudonymization phù hợp. Không kết luận DNS exfiltration chỉ từ entropy của một domain.

### 16.5. Truy cập Kubernetes API bất thường

Một workload vốn không cần Kubernetes API bỗng có lưu lượng tới kube-apiserver hoặc các API endpoints nội bộ. Để đánh giá:

1. Xác nhận **destination thực** qua route/IP/service mapping.
2. Kiểm tra service account đang gắn với pod và RBAC.
3. Đọc Kubernetes audit để xem **request verb/resource/user/result** nếu logging được bật.
4. Xem deploy/config mới và quyền owner.
5. Phân biệt client thật với traffic của sidecar/monitoring components.

**Flow tới API server không chứng minh request được cấp quyền**. Lớp API vẫn áp authentication và RBAC; cần audit logs để thấy access decision.

### 16.6. Lưu lượng tới metadata/credential endpoints

Một số cloud cung cấp **instance metadata service** hoặc workload identity endpoints. Với Kubernetes/container, khả năng tiếp cận và cơ chế bảo vệ phụ thuộc cloud, node runtime và network policy.

**Dấu hiệu:** workload không có nhu cầu truy vấn metadata bắt đầu gửi requests tới metadata-related endpoints. **Đánh giá:** đang dùng node identity hay workload identity? Metadata có giới hạn hop/token/IMDS policy theo provider không? Egress policy/SDK có đường hợp lệ?

Không giả định một địa chỉ metadata IP duy nhất áp dụng cho mọi cloud, hoặc việc nhìn thấy một kết nối tới metadata đồng nghĩa credentials đã bị lộ.

### 16.7. Bất thường network từ container bị chiếm

**Dấu hiệu đa tín hiệu:** pod bắt đầu mở nhiều outbound connections, traffic byte tăng, DNS queries lạ, socket owners bất thường, image/process runtime alerts và một loạt policy drops.

**Triage:** kết hợp CNI flows, process/runtime security telemetry, image/deploy history, service account rights và application logs. Traffic tăng sau release có thể chỉ là job batch. Không tự động xóa pod trước khi bảo toàn bằng chứng nếu runbook yêu cầu điều tra, trừ khi cần containment khẩn cấp theo phê duyệt.

### 16.8. Exfiltration hypothesis

Một workload gửi nhiều dữ liệu ra ngoài hoặc tạo số lượng lớn HTTP responses **có thể** gợi ý exfiltration, nhưng **byte counters không chứng minh dữ liệu nào đã bị lấy**.

Xác minh:

- **Chiều đếm bytes** từ góc nhìn sensor: egress/ingress của pod, gateway hay NIC.
- Traffic backup, monitoring, artifact upload, log export hoặc business jobs.
- **App-level data access/audit** và loại tài nguyên đã đọc.
- Destination đã được phép hay không.
- NAT/mesh/overlay overhead và double counting.

### 16.9. Mất mTLS hoặc mesh policy

**Dấu hiệu:** một workload trước đây luôn có mTLS peer identity lại được ghi nhận traffic **ngoài mesh**, hoặc có nhiều authentication failures do trust/cert rotation.

Cần xác minh:

- Có proxy injection/ambient enrollment và policy hiệu lực không?
- Traffic có đi qua node proxy, sidecar hay bypass route?
- Mesh telemetry có được bật trên mọi endpoint không?
- Chứng thư workload/CA trust, SAN/identity, expiry và clock có đúng không?

**Không tự diễn giải “không thấy mTLS telemetry” thành “mTLS đã bị tắt”** nếu sensor bị sampling hoặc không hỗ trợ đường đi đó.

### 16.10. NetworkPolicy changes làm tăng allow hoặc deny

**Dấu hiệu:** sau một lần cập nhật policy, lượng **DROPPED** giảm đột ngột, hoặc một nhóm service trước đây bị chặn nay kết nối được. Đây có thể là nới quyền hợp lệ hoặc một thay đổi rủi ro.

Xác minh **policy change/audit**, namespace selector và pod labels, CNI revision, nhóm traffic mới cùng ticket. Trong môi trường có nhiều allow policies, một policy mới có thể mở rộng quyền ngay cả khi default-deny policy vẫn còn.

## 17. Ma trận use case và mức tin cậy của bằng chứng

| Use case | Bằng chứng sơ cấp | Enrichment quan trọng | Phản hồi đề xuất |
| --- | --- | --- | --- |
| **Lateral scanning** | Nhiều dest/ports + policy drops theo source workload | Approved scanner, rollout, connection outcomes | Điều tra nguồn, điều chỉnh segmentation |
| **Unexpected egress** | CNI egress flows tới destination mới | NAT mapping, DNS, business owner | Triage, đối chiếu policy |
| **Cross-namespace boundary** | Source/dest identities + allow/drop verdict | Effective NetworkPolicy, CNI, route | Xác minh và siết rule khi cần |
| **Suspicious DNS** | DNS events có pattern khác baseline | Resolver/cache paths, deployment | Điều tra và bảo vệ egress |
| **Kubernetes API access** | Traffic tới apiserver | Kubernetes audit, RBAC, service account | Kiểm tra quyền, audit và runtime |
| **Metadata access** | Flow tới metadata/identity endpoint | Provider topology, SDK, identity usage | Xác minh việc truy cập có được phép |
| **Exfiltration candidate** | Outbound bytes/flows bất thường | App data access logs, backup/change context | Incident triage, không kết luận chỉ từ bytes |
| **mTLS enforcement gap** | Traffic ngoài mesh hoặc authz denials | Mesh enrollment, cert/policy status | Sửa trust/policy hoặc đường bypass |
| **Policy drift** | Flow verdict đổi sau deploy | IaC/K8s audit, policy revision | Review changes và rollback nếu sai |
| **Node datapath outage** | Flow drops/retransmits trên nhiều pods một node | CNI health, kernel, node metrics | Xử lý availability và giảm nhiễu SOC |

**Không tự động gắn severity cao cho mọi flow DROPPED.** Một default-deny policy tốt có thể tạo nhiều drops từ traffic không cần thiết; mức ưu tiên nên dựa trên **tài nguyên đích, danh tính nguồn, độ tin cậy, lịch sử và hậu quả thực tế**.

### 17.1. Cảnh báo nên nêu đủ bối cảnh

Một alert hữu ích thường có:

~~~text
Use case: Unexpected cross-namespace egress
Time: 2026-11-28 09:10 UTC (example)
Cluster: lab-east
Source:
  namespace=shop
  workload=checkout
  pod_uid=uid-source-01
Destination:
  namespace=admin
  workload=control-api
Protocol/port: TCP/8443
Verdict: DROPPED at CNI policy hook
Policy revision: lab-policy-rev-17
Corroboration:
  no authorized dependency in current service map
  deployment changed 7 minutes before event
Uncertainty:
  not proof that application data was accessed
~~~

Các trường là **ví dụ giả lập**; alert production cần trích nguyên nguồn đáng tin và không tự tạo bằng chứng. Khi không có pod identity, phải nói rõ mapping chưa được xác minh.

### 17.2. Ngưỡng và thời gian

Các rule thường dùng cửa sổ **5–15 phút** hoặc những cửa sổ theo job/deploy cycle, nhưng đây **không phải con số chuẩn**. Khi workload có batch theo giờ hoặc CronJob, phải so với lịch hợp lệ; với workloads nhạy cảm, có thể ưu tiên **policy violation** thay vì đợi số lần vượt ngưỡng.

### 17.3. False positive và false negative

| Tình huống | Rủi ro phân loại | Cách xử lý |
| --- | --- | --- |
| Autoscaling tạo nhiều pod IP mới | FP “new destination” | Group theo workload owner và Pod UID/time |
| CronJob backup tạo egress spikes | FP “exfil” | Lịch, workload role, app audit |
| Service mesh retries làm nhiều flows | FP “scanning” | Dedup theo logical request/mesh context |
| DNS cache không tạo query mới | FN nếu chỉ dựa DNS | Kết hợp egress flows |
| mTLS che payload | FN nếu chỉ trông vào packet inspection | L7 proxy/app telemetry được phê duyệt |
| Node-level flow logs sau NAT | FN/misattribution | Temporal NAT mapping, CNI flows |
| Collector mất records | FN | Pipeline health, event loss/sampling metrics |
| Labels bị sửa để trông như workload khác | Misattribution | Owner refs, RBAC/admission, identity integrity |
| CNI policy chỉ áp một số đường đi | FN | Test hostNetwork, direct node/ingress/egress paths |

**False negative thực tế khó đo chỉ từ alerts đã có**: hành vi không được phát hiện không hiện trong dashboard. Cần **kiểm thử có nhãn, incident retrospectives và negative tests** để đánh giá coverage.

## 18. Điều tra sự cố network container theo thứ tự

### 18.1. Quy trình từ triệu chứng tới vị trí nghẽn

~~~mermaid
flowchart TD
    A["App/pod báo timeout hoặc bị deny"] --> B{"DNS resolve đúng không?"}
    B -->|Không| C["CoreDNS/NodeLocal/cache/search domains"]
    B -->|Có| D{"Service có endpoint ready?"}
    D -->|Không| E["EndpointSlice, readiness, pod health"]
    D -->|Có| F{"Source/dest có flow bị policy DROP?"}
    F -->|Có| G["Effective ingress+egress policy, labels, CNI"]
    F -->|Không/không rõ| H{"TCP/UDP path hoạt động?"}
    H -->|Không| I["Routing, NAT, conntrack, SG/NSG, MTU"]
    H -->|Có| J{"TLS/mTLS handshake đúng?"}
    J -->|Không| K["CA/SAN, mesh identity, cert, clock"]
    J -->|Có| L["Application authz, HTTP/gRPC status, backend"]
    C --> M["Kiểm thử lại qua chính đường đi"]
    E --> M
    G --> M
    I --> M
    K --> M
    L --> M
~~~

**Không được nhảy ngay tới việc tắt NetworkPolicy** khi gặp timeout. Timeout có thể đến từ DNS, backend không ready, cloud firewall, service mesh TLS hoặc ứng dụng chậm. Mỗi bước cần bằng chứng từ một điểm quan sát phù hợp.

### 18.2. Phân biệt lỗi DNS, TCP, TLS và ứng dụng

| Triệu chứng | Giả thuyết | Dữ liệu ưu tiên |
| --- | --- | --- |
| NXDOMAIN/SERVFAIL | Tên sai, DNS upstream lỗi, policy DNS | Resolver logs, pod resolv.conf, CoreDNS |
| DNS có IP nhưng TCP timeout | NetworkPolicy, SG/NSG, route, target health | CNI flows, node/cloud flow, endpoints |
| TCP connection refused/RST | App không listen, port sai hoặc explicit rejection | Socket list, app logs, packet summary |
| SYN retransmits | Loss/filter/path/conntrack/MTU vấn đề | tcpdump phù hợp, counters, node logs |
| TLS unknown CA/cert expired | Truststore/CA/rotation lỗi | Mesh/TLS logs, certificate chain, clock |
| TLS handshake success nhưng HTTP 403 | App/mesh authorization | Ingress/mesh logs, JWT identity, app audit |
| HTTP 502/503/504 | Upstream error, unavailable hoặc timeout | Ingress/gateway, target health, app/DB |
| Slow queries nhưng network RTT ổn | Backend processing/DB bottleneck | Distributed traces, CPU, DB metrics |

### 18.3. Triage một policy drop

Với flow có verdict DROPPED:

1. Xác định **cluster/node, source/dest Pod UID và event time**.
2. Xác nhận **policy enforcement point** và policy ID/revision thực tế.
3. Kiểm tra ingress policy của destination và egress policy của source.
4. Kiểm tra namespaceSelector, podSelector, port, protocol, IPBlock và các rule bổ sung của CNI nếu có.
5. Xem **Service → Endpoint** translation và NAT ở nơi sensor đo.
6. Đối chiếu ứng dụng có thật sự cần flow này không.
7. Thử thay đổi trong **lab/staging**, canary và rollback theo owner trước khi nới quyền.

**Không cho phép mọi traffic** chỉ vì một ứng dụng bị lỗi; hãy mở đúng source/destination/port hoặc điều chỉnh service discovery phù hợp.

### 18.4. Triage traffic bất thường

Khi một pod có egress spike:

1. Xác minh **số byte và chiều đếm** ở một observation point cụ thể.
2. Map Pod UID và workload owner theo thời gian; kiểm tra IP reuse.
3. Xem source process/app, job schedule, recent deployment và DNS.
4. Đối chiếu destination, egress gateway/NAT mapping, dữ liệu ứng dụng đã đọc.
5. Xác minh có chính sách egress/mTLS/WAF nào đang chặn/cho qua.
6. Nếu có bằng chứng compromise, thực hiện incident response theo runbook, bao gồm **bảo toàn log và kiểm soát quyền**.

Không coi mọi outbound spike là exfiltration; nhưng cũng không bỏ qua chỉ vì process tên giống ứng dụng hợp lệ.

## 19. Quan sát trên Docker/host networking và các ngoại lệ

### 19.1. Docker bridge/network namespace

Trong Docker hoặc các container runtimes chạy trên Linux, container có thể dùng bridge networking, host networking, overlay hoặc networks riêng tùy trình điều khiển. Kiểm tra chính xác **network driver** và namespace trước khi chọn interface capture.

Một container trong **bridge network** thường có network namespace và veth; khi gọi Internet, có thể đi qua Docker NAT trên host. Một container dùng **host network** chia sẻ network namespace của host, nên không thể dựa vào “pod eth0” để phân biệt luồng.

**Không phải mọi Docker bridge giống Kubernetes CNI** và lệnh Docker networking không tự cho thấy Kubernetes Service/NetworkPolicy identities.

### 19.2. Multiple interfaces và SR-IOV

Một số workloads có nhiều network interfaces qua **Multus**, macvlan/ipvlan hoặc SR-IOV. Traffic data plane có thể đi trực tiếp qua một interface bổ sung, **bỏ qua datapath/hook của default CNI** mà sensor đang theo dõi.

Khi ứng dụng dùng network accelerators hoặc network attachments riêng, inventory cần lưu:

- Pod UID và **danh sách interfaces/networks**.
- Routing rules và source policy routing.
- Điểm capture/enforcement cho từng interface.
- NetworkPolicy có áp vào secondary interfaces không.
- Cloud/underlay ACLs, device assignments và lưu lượng DPDK/SR-IOV nếu có.

**Không thấy traffic ở default CNI không đủ kết luận workload không giao tiếp** nếu nó có secondary interface.

### 19.3. Node-local traffic và hostNetwork

Node agents, hostNetwork pods hoặc node-originated traffic có thể được tính theo **node identity** thay vì pod identity ở một số sensors. Nếu workload cố tình hoặc vô tình dùng host networking, cần bổ sung **process/socket owner, cgroup, container runtime context và host firewall logs**.

Những quyền như hostNetwork/privileged containers tăng phạm vi tác động nếu ứng dụng bị xâm phạm. Cần **admission controls, runtime hardening, RBAC và segmentation** bên cạnh quan sát mạng.

## 20. Thực hành lab: Quan sát Pod, Service và NetworkPolicy

**Giới hạn an toàn:** chỉ thực hiện trong cluster/container môi trường bạn được quyền truy cập và thu thập. Các lệnh quan sát đọc bên dưới không tự sửa manifest, nhưng có thể **hiển thị thông tin hạ tầng nhạy cảm**; không dán kết quả chứa secrets, token hoặc dữ liệu cá nhân vào nơi công cộng. Không chạy packet capture diện rộng trên production nếu chưa có phê duyệt.

### 20.1. Môi trường giả định

~~~text
Cluster: lab-east

Namespace web-lab:
  frontend (Deployment, Pod IP giả định: 10.244.1.10)

Namespace shop-lab:
  catalog (Deployment, Pod IP giả định: 10.244.2.17)
  Service catalog (ClusterIP giả định: 10.96.0.25:8080)

Namespace data-lab:
  database (chỉ cho kết nối từ workloads được duyệt)

Mục tiêu:
  frontend -> catalog: được phép TCP/8080
  frontend -> database trực tiếp: không được phép
  DNS tới resolver cluster: được phép theo chính sách
~~~

Các tên namespace/labels/IP **chỉ phục vụ ví dụ**, không tự tồn tại trên máy người học. Trong Kubernetes thật, selectors/ports và implementation policy phải được kiểm tra trước khi thử.

### 20.2. Đọc Kubernetes inventory

Các lệnh sau **chỉ đọc**, với điều kiện bạn có quyền Kubernetes RBAC tương ứng:

~~~bash
# Danh sách pods và địa chỉ IP theo cluster.
kubectl get pods -A -o wide

# Liệt kê service và endpoints ở namespace lab.
kubectl get services -n shop-lab -o wide
kubectl get endpointslices -n shop-lab \
  -l kubernetes.io/service-name=catalog -o wide

# Quan sát NetworkPolicy đã khai báo.
kubectl get networkpolicies -A
kubectl describe networkpolicy -n shop-lab

# Liên hệ pod IP với Pod UID/node tại thời điểm truy vấn.
kubectl get pods -n shop-lab \
  -o custom-columns=NAME:.metadata.name,UID:.metadata.uid,NODE:.spec.nodeName,IP:.status.podIP
~~~

**Đọc cấu hình chưa chứng minh enforcement.** Một NetworkPolicy tồn tại trong API server nhưng plugin thiếu hỗ trợ, selector không chọn đúng pod hoặc traffic đi qua một interface khác có thể làm kết quả khác mong đợi. Cần có **flow/policy verdict** và kiểm thử có quyền.

### 20.3. Liên kết Pod với Deployment và service account

~~~bash
# Chi tiết pod đã xác định và các event liên quan.
kubectl describe pod -n shop-lab <pod-name>

# Xem danh sách workloads, không cần truy vấn secrets.
kubectl get deployments,statefulsets,daemonsets -n shop-lab

# Một số trường danh tính/scheduling từ Pod API:
kubectl get pod -n shop-lab <pod-name> \
  -o jsonpath='{.metadata.uid}{"\n"}{.spec.nodeName}{"\n"}{.spec.serviceAccountName}{"\n"}'
~~~

Trong ví dụ, **<pod-name>** là placeholder phải thay bằng pod thật do bạn được phép xem. Các lệnh đọc Kubernetes API có thể cho kết quả khác theo RBAC và phiên bản; lỗi **Forbidden** là thiếu quyền, không nhất thiết là sự cố mạng.

### 20.4. Quan sát mạng từ container đang chạy

Nếu một pod lab được cài sẵn những công cụ Linux cần thiết và RBAC cho phép exec, một số lệnh **chỉ đọc** gồm:

~~~bash
# Chạy bên trong container có công cụ iproute2.
ip -br address
ip route
ip -6 route
ss -tn

# Kiểm tra resolver configuration trong lab.
cat /etc/resolv.conf
~~~

Nếu container image tối giản không có **ip, ss hoặc cat**, việc lệnh không chạy được **không chứng minh mạng đã lỗi**. Có thể dùng debug container/image được tổ chức phê duyệt trong **lab**, nhưng việc thêm ephemeral container hoặc chạy với quyền network capture có thể **thay đổi Pod và mở rộng quyền truy cập**; cần quy trình cấp phép và kiểm soát image provenance.

### 20.5. Packet capture giới hạn trong môi trường lab

Chỉ khi đã được cấp quyền capture và có đúng Linux interface/namespace:

~~~bash
# Capture tối đa 20 packet, giới hạn snaplen 64 byte
# và lọc vào traffic thử nghiệm của một API lab.
# Có thể vẫn chứa metadata nhạy cảm: không chia sẻ raw output tùy ý.
tcpdump -i any -nn -c 20 -s 64 'tcp port 8080 or udp port 53'
~~~

**Lưu ý:**

- Cần có quyền CAP_NET_RAW/quyền tương ứng và công cụ tcpdump.
- Linux **any** interface có thể hiển thị gói ở nhiều điểm, khiến một flow xuất hiện nhiều lần.
- Snaplen 64 giới hạn bytes chụp của mỗi packet, nhưng **không bảo đảm ẩn mọi dữ liệu nhạy cảm**.
- Filter có thể không thấy HTTPS traffic nếu nó đi qua cổng/namespace khác.
- Network offload hoặc overlay có thể làm PCAP nhìn khác packet trên dây.
- Chỉ dùng test traffic do bạn được phép tạo, không capture toàn cluster để “xem thử”.

### 20.6. Quan sát conntrack và node network

Nếu một node lab có công cụ và quyền phù hợp:

~~~bash
# Tổng quan interface và counters.
ip -s link show

# Nếu conntrack command được cài:
conntrack -S
~~~

Đây là quan sát kỹ thuật cục bộ; **không tự gắn được UID workload** nếu thiếu enrichment. Conntrack counters có thể là tổng theo node/netns, cách expose và ý nghĩa phụ thuộc kernel/config.

### 20.7. CNI/mesh flow visibility theo sản phẩm

Nếu cluster lab có **Cilium/Hubble**, hãy sử dụng giao diện quan sát flow được quản trị viên cấp quyền để lọc:

~~~text
Filter đề xuất trong UI/CLI tương ứng:
  cluster = lab-east
  namespace = shop-lab
  time range = 5 phút gần nhất
  verdict = FORWARDED hoặc DROPPED
  source workload = frontend
  destination workload = catalog

Fields cần thu:
  event time, Pod UID/identity, source/destination,
  L4 ports, observation point, policy/verdict, node
~~~

**Không tự giả định Cilium/Hubble hoặc công cụ nào đã được cài.** Nếu CNI không cung cấp tính năng này, có thể dùng cloud flow logs, mesh/ingress logs hoặc node metrics tương ứng nhưng phải ghi rõ điểm mù.

### 20.8. Kiểm chứng bằng lưu lượng hợp lệ nhỏ

Mục tiêu là so sánh **luồng được phép và bị từ chối theo policy** bằng **ít request**, không tạo tải lớn. Khi người quản trị lab đã tạo endpoint HTTP thử và chính sách:

1. Gửi **một** HTTP request từ frontend lab tới catalog service qua service DNS.
2. Ghi kết quả ở client, timestamp, status và DNS resolution.
3. Tìm flow record tại CNI/sensor; đối chiếu service/endpoint mapping.
4. Gửi **một** request tới endpoint đã được thiết kế là **không được phép** trong lab.
5. Xác nhận policy drop hoặc network denial ở đúng điểm, không chỉ HTTP 403.
6. Kiểm tra log ứng dụng: request bị chặn trước khi tới app **không có lý do xuất hiện trong app access log**.

Không thử kết nối tới các địa chỉ nội bộ không thuộc lab hoặc cố tình scan cả subnet. Chỉ dùng endpoints đã được chuẩn bị, có sự đồng ý của owner.

### 20.9. Ma trận kiểm thử điểm mù

| Bài thử | Bằng chứng kỳ vọng | Điều cần phân biệt |
| --- | --- | --- |
| Pod A → Pod B cùng node | Flow tại CNI/veth phù hợp | Intra-pod loopback khác inter-pod |
| Pod A → Pod B khác node | Flow với node mapping, overlay nếu có | Underlay outer IP không phải Pod UID |
| Pod A → ClusterIP Service | Service VIP và endpoint thực tương quan | Before/after DNAT |
| Pod → Internet | Egress flow + NAT context | Public IP không là pod identity |
| Pod → DNS resolver | DNS event hoặc flow đúng resolver | Cache/DoH/DoT làm thiếu DNS logs |
| NetworkPolicy block | Verdict/drop tại enforcement point | TCP timeout không tự là policy deny |
| App HTTP 403 | App/mesh access log | L3/L4 có thể vẫn FORWARDED |
| mTLS handshake fail | Mesh/TLS logs | Connection allowed nhưng xác thực thất bại |
| Pod restart và IP reuse | Historical UID mapping chính xác | Tránh tra Kubernetes state hiện tại |
| HostNetwork/secondary NIC | Coverage rõ ràng hoặc gap được ghi | Default CNI không thấy mọi traffic |
| Collector mất kết nối | Pipeline health alert | Không hiểu “0 event” là không có traffic |

### 20.10. Tiêu chí hoàn thành bài lab

Học viên phải mô tả được **hai flow hợp lệ, một flow bị chặn, một thay đổi pod IP hoặc workload state, một bằng chứng DNS/ingress và một giới hạn quan sát**. Không bắt buộc lưu PCAP nếu các log metadata đã đủ trả lời câu hỏi, và không cần bật quyền privileged cho toàn cluster.

## 21. Kiến trúc mẫu: Bản đồ quan sát cho một dịch vụ đặt hàng

### 21.1. Sơ đồ chức năng

~~~mermaid
flowchart TD
    USERS["External clients"] --> LB["Cloud LB / WAF"]
    LB --> ING["Ingress controller"]
    ING --> FRONT["Frontend pod / web namespace"]
    FRONT --> ORDER["Order service / shop"]
    ORDER --> PAY["Payment service / finance"]
    ORDER --> DATA["Database / data namespace"]
    ORDER --> OUT["Egress gateway / allowed provider"]
    LB -. "Request/WAF logs" .-> SOC["SOC + SRE observability"]
    ING -. "L7 request logs" .-> SOC
    FRONT -. "CNI flows" .-> SOC
    ORDER -. "CNI + mesh/trace" .-> SOC
    PAY -. "Service identity + authz logs" .-> SOC
    OUT -. "DNS/NAT egress logs" .-> SOC
~~~

Một backend có thể hoạt động bình thường nhưng:

- WAF chặn request trước ingress → **backend không có app log**.
- Ingress đã chuyển request, CNI drop trước order pod → **network policy log** giải thích timeout.
- CNI allow, mesh mTLS reject → **TLS/service identity logs** giải thích.
- mTLS thành công, app trả 403 → **application authorization logs** quyết định.
- App xử lý thành công nhưng database timeout → **trace/DB metrics** cần được xem.

### 21.2. Câu hỏi cần chứng minh bằng dữ liệu

1. Chỉ đúng ingress controller/identity mới được gọi frontend hay không?
2. Chỉ order service được truy cập database qua đúng cổng và authorization?
3. Khi order cần gọi payment, peer workload identity và TLS policy có đúng không?
4. Các requests bị WAF/ingress block có tạo CNI/app events không?
5. Egress tới payment provider có thể quy về đúng Pod UID và tenant/service?
6. Deployment mới có làm tăng DNS failures, retry hoặc policy drops không?
7. Một connection qua service mesh có bị **đếm nhiều lần** ở datapath logs không?
8. Logs có đến SIEM với event time và collection-lag chấp nhận được không?

### 21.3. Ai sở hữu từng loại bằng chứng?

| Đội | Dữ liệu cần sở hữu | Phối hợp |
| --- | --- | --- |
| **Platform/Kubernetes** | Pod lifecycle, CNI, NetworkPolicy, nodes | Networking/SRE |
| **Network/Cloud** | VPC/NSG/SG, NAT, LB/ingress routes | Platform/SOC |
| **App team** | HTTP logs, traces, identity/authz, dependencies | SRE/SOC |
| **Security/SOC** | Detections, incident correlation, retention/access | Owners các data sources |
| **Identity/PKI** | Workload identities, mTLS certs, trust/revocation | Platform/App |
| **SRE/Observability** | Pipeline health, metrics, dashboards, sampling | Platform/SOC |

Một alert SOC không nên chỉ gửi “pod X kết nối lạ” mà không có đường tra **owner, thời điểm, policy và cách xác minh**. Cần có runbook và quy trình yêu cầu log chi tiết khi cần.

## 22. Triển khai quan sát lưu lượng theo giai đoạn

### Bước 1 — Xác định phạm vi và câu hỏi nghiệp vụ

Chọn các workloads/namespace có yêu cầu rõ ràng: API public, database, authentication, payment, jobs, control plane dependencies và egress. Nêu câu hỏi cụ thể: **Có chứng minh được default-deny đang hoạt động? Pod nào gọi domain ngoài danh sách? Khi app 504, vấn đề ở DNS, CNI hay backend?**

Tránh thu thập toàn bộ packets của cluster nếu **flow metadata + L7 request logs** đã đủ cho use case.

### Bước 2 — Kiểm kê datapath và các điểm mù

Ghi nhận CNI, runtime, Service routing mode, kube-proxy/eBPF, network interfaces, overlay/native routes, sidecar/ambient mesh, cloud VPC, egress NAT, ingress/edge và dual-stack. Kiểm tra các trường hợp **hostNetwork, SR-IOV/Multus, NodePort, cluster-external paths**.

**Không có bản đồ datapath**, các log ở node hoặc egress rất dễ bị gán sai cho pod/user.

### Bước 3 — Xác định identity và temporal mapping

Thiết kế mối quan hệ:

~~~text
Flow event (time, node, 5-tuple)
     |
     +-- Pod UID / namespace / owner at event time
     +-- Service VIP -> selected endpoint mapping
     +-- NAT/egress translations at event time
     +-- Network policy revision/verdict
     +-- Mesh/TLS peer identity if available
     +-- App request/trace ID if applicable
~~~

Sử dụng **Pod UID và owner refs**, không chỉ Pod name/IP hiện tại. Trường nào thiếu phải có confidence/unknown thay vì tự gán.

### Bước 4 — Chọn signals tối thiểu

Một cấu hình khởi đầu có thể:

| Mục tiêu | Thu thập tối thiểu | Bổ sung khi cần |
| --- | --- | --- |
| Segmentation compliance | CNI allow/drop verdicts + K8s policy | Timed NAT/endpoint mapping, cloud SG |
| Application availability | Ingress/app logs, latency/5xx | Traces, mesh, TCP metrics |
| Egress security | CNI egress + cloud NAT/firewall | DNS, workload runtime, data audit |
| Lateral movement detection | Flows theo source workload/dest ports | Runtime process, IDS/IPS |
| DNS troubles | CoreDNS/NodeLocal logs/metrics | Resolver path/capture |
| Certificate/mTLS faults | Mesh/authn logs và cert inventory | App TLS handshake diagnostics |

### Bước 5 — Bảo vệ collectors

Đánh giá DaemonSet privileges, Kubernetes RBAC, TLS authentication cho đường export, network policies, secrets, audit và memory/storage budget. Hạn chế lọc quá rộng và tránh agent restart/loss khi node chịu tải.

### Bước 6 — Baseline và kiểm thử coverage

Thu thập dữ liệu có đại diện theo workload role/giờ/deploy cycle. Tạo service graph, kiểm thử các tình huống có nhãn **allow, deny, DNS fail, TLS fail, pod replacement và collector outage**.

### Bước 7 — Bật cảnh báo có ngữ cảnh

Bắt đầu với dấu hiệu dễ liên kết chính sách: **NetworkPolicy drops tới vùng cấm, egress ngoài danh sách, workload truy cập Kubernetes API không mong đợi, mTLS auth failures**. Sau đó mở rộng sang phát hiện thống kê như service map drift, DNS anomaly hoặc bytes spike.

### Bước 8 — Rollout và phản hồi

Dùng thay đổi được review và canary theo node/namespace nếu nền tảng hỗ trợ. Theo dõi **collector CPU/memory, event loss, ingest latency, alerts, false positives và backend health**. Xem việc tăng visibility có làm tăng nguy cơ lộ dữ liệu hoặc chi phí ngoài ngân sách không.

### Bước 9 — Bảo trì liên tục

Sau CNI/kernel/mesh upgrades, thêm network attachment hoặc chuyển cluster/region, phải thử lại datapath coverage. Định kỳ rà soát **quyền của collectors, log retention, policy owners, các nguồn đã ngừng gửi data và hệ thống mapping pod IP**.

## 23. Checklist nghiệm thu observability cho container

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng chấp nhận |
| --- | --- | --- |
| **Datapath inventory** | Biết mỗi workload đi qua interfaces/CNI/mesh nào? | Sơ đồ actual path và CNI inventory |
| **Pod identity** | Có mapping Pod UID, owner và namespace đúng thời điểm? | Test IP reuse và event timeline |
| **Service translation** | Service VIP và endpoint được liên kết đúng? | Before/after NAT/EndpointSlice evidence |
| **Intra-pod visibility** | Biết loopback traffic có/không được thấy? | Test trong pod và documented gap |
| **Same/cross-node** | Flows giữa nodes có được nhìn đúng nội dung/outer tunnel? | CNI/node evidence và topology |
| **NetworkPolicy** | Drop được xác định bằng verdict và policy revision? | Test deny + source/dest identities |
| **Cloud firewall** | Có dữ liệu SG/NSG/route/egress tương ứng? | Allow/deny test theo đường thực |
| **Service mesh** | Biết traffic nào có mTLS/L7 proxy telemetry? | Mesh identity, access logs và bypass tests |
| **DNS** | Thấy DNS query/failure theo đúng nguồn hỗ trợ? | CoreDNS/NodeLocal logs và known gaps |
| **Egress NAT** | Map external flow về đúng workload khi có dữ liệu? | Temporal NAT + CNI correlation |
| **IPv4/IPv6** | Cả hai giao thức được kiểm tra nếu cluster hỗ trợ? | Dual-stack flow test và policy logs |
| **hostNetwork/secondary NIC** | Biết trường hợp nào ngoài default CNI? | Workload/attachment inventory |
| **TLS boundaries** | Có biết đâu nhìn thấy plaintext/L7 và đâu không? | TLS topology và L7 log source |
| **Packet capture** | Chỉ capture có phê duyệt, phạm vi và giới hạn? | SOP, RBAC, audit, retention |
| **Log identity integrity** | Không tin labels/client headers tự khai làm identity mạnh? | Auth/workload identity verification |
| **Flow sampling** | Biết event loss/sampling rate? | Sensor metrics và known-good test |
| **Pipeline health** | Có cảnh báo collector mất log hoặc schema lỗi? | Health dashboards, outage drill |
| **Privacy** | Tránh tokens/PII và giới hạn quyền xem? | Data classification, retention, access review |
| **Detection** | Có test TP/FP/undetermined và context? | Labeled lab exercises/incident review |
| **Rollback** | Có plan khôi phục khi sensor gây quá tải? | Owner, canary, approved runbook |

**Một mạng “quan sát được” không nhất thiết là mạng “an toàn”.** Chỉ số độ phủ cao cần đi cùng enforcement policy thật, identity đúng, an toàn dữ liệu và xử lý incident có chủ sở hữu.

## 24. Tình huống tổng hợp: Sau NetworkPolicy mới, dịch vụ checkout mất kết nối

### 24.1. Bối cảnh

Cluster **lab-east** có ứng dụng:

~~~text
Namespace: web-lab
  frontend -> Service checkout.shop-lab:8080

Namespace: shop-lab
  checkout -> Service catalog.shop-lab:8080
  checkout -> Service payment.finance-lab:8443

Namespace: finance-lab
  payment -> external payment provider via egress gateway

DNS:
  CoreDNS / NodeLocal DNSCache theo cấu hình lab
~~~

Trước đó, checkout hoạt động bình thường. Nhóm platform triển khai **default-deny egress** cho namespace shop-lab, kèm một allow policy chỉ cho checkout gọi **catalog TCP/8080**. Ngay sau deploy, checkout báo timeout với payment; DNS lookup trong một số pod cũng thất bại.

### 24.2. Dữ kiện giả lập thu được

| UTC | Nguồn | Sự kiện |
| --- | --- | --- |
| 09:00 | Kubernetes audit | NetworkPolicy shop-lab/default-deny-egress được tạo |
| 09:01 | CNI policy | checkout → catalog:8080 FORWARDED |
| 09:02 | App trace | GET catalog success |
| 09:03 | DNS/app | Lookup payment.finance-lab có timeout |
| 09:03 | CNI policy | checkout → resolver:53 DROPPED |
| 09:04 | CNI policy | checkout → payment:8443 DROPPED khi dùng IP trực tiếp |
| 09:05 | Ingress | Client checkout HTTP 504 từ luồng nghiệp vụ |

**Đây là kịch bản lab giả lập**, không phải incident thực. Các flows có thể không xuất hiện cùng cấu trúc trên mọi CNI.

### 24.3. Phân tích nguyên nhân theo tầng

1. **NetworkPolicy thay đổi lúc 09:00** là thay đổi có quan hệ thời gian rõ; chưa đủ kết luận nếu không có log drop.
2. **Catalog FORWARDED và app success** chứng minh đường cụ thể tới catalog hoạt động theo trường hợp đã đo.
3. **DNS resolver DROP** có thể gây lỗi lookup tên payment; một DNS failure chưa chứng minh payment backend đã hỏng.
4. **Payment TCP/8443 DROP** xác nhận thêm một đường egress bị policy chặn khi đã có IP đích.
5. **HTTP 504 tại ingress** là hậu quả nhìn từ client; nó không chỉ ra chính xác policy nào gây lỗi nếu không có app/CNI timeline.

### 24.4. Hướng khắc phục có kiểm soát

Không xóa default deny toàn namespace. Thay vào đó:

- Xác minh **payment** có phải dependency được phê duyệt của checkout không.
- Xác định đúng resolver IP/namespace/port mà checkout thực sự sử dụng; NodeLocal DNSCache nếu có có thể cần path khác CoreDNS Service.
- Bổ sung **egress allow rules hẹp** cho DNS và payment theo policy/selector phù hợp, song song với ingress policy của destination.
- Kiểm thử **positive** (checkout → catalog/payment/DNS đúng) và **negative** (checkout → admin/data bị chặn) trong lab.
- Quan sát CNI verdict, app traces và 5xx rate sau canary.
- Giữ policy revision/change record và khả năng rollback.

### 24.5. Biến thể làm điều tra khó hơn

Giả sử ở 10:00 pod checkout được thay, IP cũ được gán cho pod monitoring. Một flow 09:03 nếu được gán theo **current Pod IP mapping** sẽ bị kết luận sai là “monitoring truy vấn payment”. Bài học: **network incident timeline phải dùng Pod UID và thời gian hiệu lực**.

Nếu payment call được service mesh mTLS proxy chuyển tiếp, một lỗi certificate/identity còn có thể xảy ra sau khi network policy đã allow. **Không sửa policy rồi dừng điều tra** khi TLS/app vẫn lỗi.

### 24.6. Câu hỏi phân tích tình huống

1. Bằng chứng nào xác nhận DNS bị NetworkPolicy chặn thay vì CoreDNS chết?
2. HTTP 504 tại ingress có đủ chỉ ra lỗi là egress policy không?
3. Tại sao cần kiểm tra **cả policy egress của checkout và ingress của payment**?
4. NetworkPolicy có default-deny egress thì frontend có còn được gọi checkout không?
5. Vì sao cho DNS TCP/UDP 53 cần hiểu resolver path thực, không chỉ assume một ClusterIP?
6. Nếu Pod IP được tái sử dụng, trường gì ngăn gán nhầm flow?
7. Một policy allow theo namespace và pod selector có thể rộng ra thế nào khi YAML thụt lề sai?
8. Nếu checkout → payment FORWARDED nhưng TLS mTLS lỗi, tìm logs nào tiếp?

**Gợi ý:** (1) CNI DROPPED cho đúng resolver identity/flow, đối chiếu DNS app logs; (2) không; (3) allow phải đáp ứng chính sách áp dụng ở cả hai phía khi isolation tương ứng; (4) ingress policy quyết định inbound, default-deny egress chỉ xét outbound của pods được chọn, nhưng các kết nối và chiều phản hồi phải hiểu theo enforcement semantics; (5) NodeLocal cache, hostNetwork và DNS path khác nhau; (6) Pod UID + event time; (7) hai selectors tách thành hai phần tử có thể thành OR; (8) mesh proxy/TLS handshake, cert, trust và app authorization logs.

## 25. Câu hỏi tự kiểm tra và đáp án gợi ý

**1. Vì sao một pod có hai container thường không có hai Pod IP?**

Vì các container thông thường trong cùng pod **chia sẻ network namespace** và địa chỉ mạng của pod. Muốn phân biệt ai tạo kết nối loopback, cần process/socket/app telemetry thay vì chỉ dựa vào Pod IP.

**2. Vì sao tcpdump trên node NIC có thể không hiển thị IP pod mà chỉ thấy IP node?**

Vì traffic cross-node có thể được encapsulate trong VXLAN/Geneve hoặc đã trải qua SNAT. Phải xác định capture point, outer/inner headers và CNI datapath.

**3. IP của Kubernetes Service có luôn là endpoint thực nhận TCP connection không?**

Không. ClusterIP có thể là một **logical VIP**, được xử lý qua iptables/IPVS/eBPF service forwarding tới một endpoint pod khác; cần flow và endpoint mapping theo thời điểm.

**4. Vì sao không nên tìm một flow cũ bằng Pod IP hiện tại rồi kết luận owner?**

Vì pod IP có thể được tái sử dụng. Phải dùng **Pod UID, cluster, thời gian hiệu lực và workload owner**.

**5. Flow verdict FORWARDED có nghĩa HTTP request đã thành công không?**

Không. Nó chỉ phản ánh traffic vượt qua **một điểm enforcement/observation**; TLS, app authz, DB hoặc backend có thể tiếp tục thất bại.

**6. HTTP 403 ở ứng dụng có nghĩa NetworkPolicy đã drop packet không?**

Không. HTTP 403 thường được tạo bởi ứng dụng/gateway/mesh tại L7; traffic có thể đã vượt qua L3/L4 bình thường.

**7. NetworkPolicy được khai báo nhưng CNI không thực thi, điều gì có thể xảy ra?**

Không thể coi policy đó là ranh giới bảo vệ có hiệu lực. Cần xác minh CNI support và kiểm thử **deny** thực tế.

**8. Tại sao phải kiểm tra cả ingress và egress policy trong một kết nối pod-to-pod?**

Vì luồng có thể chịu enforcement ở cả source và destination khi những pods bị isolation bởi policies tương ứng. Một allow ở source không tự mở ingress của destination.

**9. Hai mục namespaceSelector và podSelector cùng phần tử from khác gì hai phần tử from riêng biệt?**

Cùng một phần tử thường là **AND** (pod matching trong namespace matching). Tách thành hai phần tử danh sách sẽ cho **OR**, có thể mở rộng phạm vi được phép.

**10. CNI flow log có thay Kubernetes audit không?**

Không. Flow log phản ánh data plane; audit cho biết API actions như ai cập nhật NetworkPolicy/Deployment và kết quả của hành động đó.

**11. Cilium/Hubble hoặc eBPF có tự giải mã mọi HTTPS không?**

Không. Dữ liệu L7 chỉ quan sát được khi có instrumentation/proxy ở điểm có plaintext và quyền phù hợp; network hooks thường thấy encrypted packets/metadata.

**12. Tại sao “không có DNS query” không chứng minh container không ra Internet?**

Vì cache, DNS ngoài cluster, DoH/DoT, proxy hoặc kết nối trực tiếp tới IP có thể không tạo event ở resolver đang giám sát.

**13. Một public NAT IP duy nhất có xác định pod gây outbound connection không?**

Không. Cần **NAT mappings theo thời gian**, source Pod UID và network tuples, nhất là khi nhiều pods dùng chung gateway.

**14. Vì sao service mesh telemetry có thể đếm một request nhiều lần?**

Vì cùng logical request được nhìn ở app→local proxy, proxy→remote proxy và remote proxy→app, hoặc ở nhiều network hooks. Phải dedup/diễn giải theo observation point.

**15. HostNetwork Pod có bắt buộc xuất hiện như traffic qua default CNI pod veth không?**

Không. Nó dùng host network namespace và cần host/process-level observation hoặc sensor khác.

**16. Kết nối trên secondary interface/SR-IOV có thể bỏ qua quan sát của default CNI không?**

Có thể, tùy plugin/driver. Vì vậy inventory interfaces và policy/enforcement coverage phải được kiểm chứng.

**17. Những dấu hiệu nào giúp phân biệt network timeout với ứng dụng quá tải?**

DNS resolution, endpoint readiness, TCP handshake/retransmission, policy verdict, mesh TLS, HTTP/gRPC status, application traces và backend metrics.

**18. Vì sao lưu lượng lớn từ backup job không tự là exfiltration?**

Vì phải xác minh hướng byte, lịch công việc, destination, app data access và quyền; byte counter không cho biết dữ liệu có bị truy cập trái phép.

**19. Vì sao chỉ theo dõi flow count có thể bỏ lỡ workload tốn tài nguyên?**

Một connection duy nhất có thể truyền rất nhiều byte hoặc nhiều HTTP/2/gRPC requests; cần bytes/latency/concurrency và L7 metrics.

**20. Nếu collector ngừng gửi log, số alert giảm, đó có phải cải thiện an ninh?**

Không. Cần theo dõi **collector health, event loss, ingest latency và coverage**. “Không thấy” có thể là mất telemetry.

**21. Vì sao không dùng raw HTTP headers hoặc full PCAP làm log mặc định cho mọi pod?**

Vì dễ chứa credentials, tokens, nội dung cá nhân/nhạy cảm và gây chi phí lớn. Ưu tiên metadata đủ mục đích, masking, RBAC và retention.

**22. Một service graph được dựng từ observed flows có tự trở thành allowlist an toàn không?**

Không. Flows có thể gồm hoạt động trái phép, thử nghiệm, retry hoặc artifact của proxy/NAT. Owner phải xác minh legitimate dependencies trước khi áp policy.

**23. Một TCP reset có luôn là bằng chứng firewall chặn không?**

Không. Endpoint hoặc proxy có thể gửi RST vì service không listen, timeout hoặc chính sách. Cần xác định nguồn reset và log liên quan.

**24. Khi gắn alert “Pod A quét nhiều cổng”, những dữ liệu bổ sung quan trọng là gì?**

Pod UID và owner, số destination ports/identities theo thời điểm, policy verdicts, scanner đã được phê duyệt, deploy context, runtime/process và phạm vi các network paths.

**25. Tại sao NetworkPolicy ingress/egress không thay quyền API?**

Vì NetworkPolicy kiểm soát kết nối L3/L4 theo nguồn/đích/port (và những khả năng mở rộng của CNI nếu có), không chứng minh user có quyền đọc từng tài nguyên nghiệp vụ. API vẫn phải authenticate/authorize request.

## 26. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Mỗi container trong một Pod có một IP riêng.” | Container thông thường trong cùng Pod chia sẻ network namespace/Pod IP. |
| “Nếu Pod A gọi được Service VIP thì đã có thể kết luận IP nào thực nhận.” | Endpoint selection và NAT cần được đối chiếu. |
| “Flow trên node NIC luôn hiển thị các Pod IP.” | Overlay/SNAT có thể che inner Pod identities. |
| “Pod IP cố định là identity an ninh đủ tin cậy.” | IP có thể đổi/tái sử dụng; dùng Pod UID, workload, time và identity đúng nguồn. |
| “Tất cả flows đều phải đi qua Linux bridge.” | CNI có routed/eBPF/tunnel/offload và nhiều datapaths khác. |
| “NetworkPolicy tồn tại nghĩa là CNI đang chặn traffic.” | Phải kiểm tra plugin support, selectors và enforcement thực tế. |
| “Default-deny ingress tự deny mọi egress.” | Ingress và egress là các hướng policy khác nhau. |
| “Một allow policy có thể phủ định mọi allow policy khác.” | NetworkPolicy chuẩn có additive allow semantics; cần đọc policy hiệu lực. |
| “CNI FORWARDED nghĩa là ứng dụng trả HTTP 200.” | Network verdict khác TLS/auth/app status. |
| “HTTP 403 là do NetworkPolicy.” | HTTP 403 thường là kết quả L7; policy drop có biểu hiện khác. |
| “Một flow record là một HTTP request.” | Persistent connections/HTTP2/gRPC có thể có nhiều requests trên một flow. |
| “Chụp PCAP ở một interface là thấy toàn cluster.” | Có nhiều namespaces, tunnels, secondary interfaces và offload. |
| “Cài eBPF agent là tự thấy plaintext HTTPS.” | Phụ thuộc hook, TLS endpoint và instrumentation. |
| “Service mesh thấy tất cả network traffic của workloads.” | Có bypass, exempt ports, ambient modes, protocol limitations. |
| “Bật mTLS đã kiểm tra quyền user của mọi API.” | Workload authentication khác end-user authorization. |
| “Không thấy CoreDNS query nghĩa là không có DNS.” | Cache, DoH/DoT, resolvers khác và IP trực tiếp tạo điểm mù. |
| “Một public NAT IP tương đương một pod.” | Nhiều pods có thể chia sẻ egress IP; cần temporal NAT mapping. |
| “Bytes out tăng tức là data theft.” | Cần xem hướng đo và application/data audit. |
| “Một Pod mới gọi endpoint mới là tấn công.” | Deployment/scale/new dependency có thể hợp lệ. |
| “Flow logs thay được Kubernetes audit.” | Data plane và control plane ghi các loại bằng chứng khác nhau. |
| “Có metric count thì không cần sensor health.” | Collector drop/sampling/restart có thể làm metric/alert sai. |
| “Mọi dữ liệu càng chi tiết càng an toàn.” | Nguy cơ lộ secrets, privacy và storage/CPU rất lớn. |
| “Tắt NetworkPolicy sẽ là cách nhanh nhất sửa timeout.” | Nguy cơ mở ranh giới; phải tìm DNS/policy/routing/TLS nguyên nhân. |
| “Một service graph tự sinh từ logs luôn là least-privilege.” | Phải xác minh quyền nghiệp vụ và những dependency chưa thấy do sampling. |

## 27. Tổng kết

**Quan sát lưu lượng container** là quá trình dựng lại bức tranh mạng dựa trên **đường đi thật và danh tính thật của workload**, không chỉ dựa trên IP/port. Trong Kubernetes và container networking, gói tin có thể đi qua **namespace, veth, CNI, service forwarding/NAT, overlay, node interfaces, ingress/egress gateways và service mesh**. Mỗi điểm quan sát chỉ thấy một phần.

Một mô hình đáng tin cần kết hợp:

- **CNI/eBPF flow logs và network policy verdicts** để biết L3/L4 traffic được cho phép hay chặn.
- **Kubernetes Pod/EndpointSlice/audit events theo thời gian** để gắn Pod UID, workload owner, policy revision và service mapping.
- **DNS, cloud NAT, ingress/mesh L7 logs, application traces** để phân tích tên đích, yêu cầu nghiệp vụ, TLS và authorization.
- **Metrics về RTT, packet drops, retransmits, conntrack, DNS và pipeline health** để phân biệt sự cố khả dụng và tấn công.
- **Privacy, RBAC, sampling/retention, log integrity và incident runbook** để việc quan sát không trở thành lỗ hổng mới.

Trong **SECURITY_NETWORK_SECURITY**, những bằng chứng này hỗ trợ thiết kế **phân đoạn mạng, firewall, network access control, IDS/IPS, bảo vệ DNS, VPN, bảo mật workload/cloud và điều tra xâm nhập**. Hãy bắt đầu từ câu hỏi cần trả lời, xác minh **điểm quan sát có thấy được traffic đó không**, liên kết dữ liệu bằng danh tính và thời gian, sau đó mới quyết định có cần bổ sung quyền hay telemetry sâu hơn.

### Tài liệu tham khảo và hướng đọc thêm

- **Kubernetes Documentation — Services, EndpointSlices, DNS for Services and Pods:** logical service routing, endpoints và tên miền nội bộ.
- **Kubernetes Documentation — Network Policies:** selectors, ingress/egress isolation và yêu cầu hỗ trợ từ CNI.
- **Kubernetes Documentation — Pod Lifecycle, Pod Networking và Audit:** identity/vòng đời pod, cơ chế mạng và audit API.
- **Kubernetes Documentation — Debugging Services và Debugging Pods:** cách kiểm tra hợp lệ khi pod/service không kết nối.
- **Container Network Interface (CNI) Specification:** cấu trúc plugin và cơ chế triển khai mạng container.
- **Linux kernel documentation — Network namespaces, veth, traffic control, eBPF và conntrack:** cơ chế Linux datapath và điểm quan sát.
- **Cilium / Hubble Documentation:** eBPF datapath, flow observation, identities và policy verdicts theo tính năng/version.
- **Calico Documentation:** chính sách mạng và khả năng flow logs theo sản phẩm/mode triển khai.
- **Istio, Linkerd và các service mesh docs đang dùng:** mTLS workload identity, access logs, proxy/ambient traffic và limits.
- **OpenTelemetry Documentation:** khái niệm traces, metrics, logs, Collectors và resource attributes.
- **RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3:** mã hóa kênh truyền và handshake.
- **RFC 9110 / RFC 9113:** HTTP semantics và HTTP/2 multiplexing, giúp phân biệt request với connection.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** dải địa chỉ cho ví dụ minh họa.
- **NIST SP 800-207 — Zero Trust Architecture:** lý do network access cần kết hợp identity/authorization theo tài nguyên.
- **OWASP Kubernetes Security Cheat Sheet:** hardening, RBAC, phân đoạn và kiểm soát container/Kubernetes.
- **Tài liệu CNI, cloud network/flow logging và mesh của đúng phiên bản đang triển khai:** xác minh chính xác datapath, fields, sampling, limitations và policy enforcement.
