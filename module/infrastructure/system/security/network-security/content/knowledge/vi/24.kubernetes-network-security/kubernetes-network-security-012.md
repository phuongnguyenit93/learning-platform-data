# Pod security liên quan đến network capability: đặc quyền Linux, namespace và ranh giới mạng trong Kubernetes

Trong Kubernetes, một Pod có thể bị giới hạn đường mạng bằng **NetworkPolicy**, nhưng đồng thời container bên trong Pod vẫn có thể sở hữu các **Linux capabilities** cho phép thực hiện thao tác nhạy cảm đối với network stack. Ví dụ, **CAP_NET_ADMIN** có thể cho phép sửa route và firewall trong network namespace phù hợp; **CAP_NET_RAW** liên quan đến raw/packet sockets; **CAP_NET_BIND_SERVICE** cho phép bind vào privileged ports theo cơ chế kernel. Nếu cấp capability hoặc cấu hình **privileged/hostNetwork** quá rộng, những giả định về cô lập Pod và điểm giám sát mạng có thể trở nên sai lệch.

Bài học **Pod security liên quan đến network capability** thuộc chương **Bảo mật mạng Kubernetes**, trong module **SECURITY_NETWORK_SECURITY**: học các lớp phòng vệ mạng từ phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây đến cloud, phân tích lưu lượng và threat model. Trọng tâm ở đây là **quyền mà tiến trình được làm trên network stack** và cách chúng tương tác với **Pod network namespace, Kubernetes securityContext, Pod Security Standards, admission, CNI, NetworkPolicy và node security**.

**Phân biệt hai câu hỏi:** (1) *tiến trình có quyền thực hiện thao tác mạng đặc biệt nào?* — Linux capabilities/kernel security; (2) *gói tin của workload có được đi qua một ranh giới nào hay không?* — NetworkPolicy, firewall, routing, service mesh và application authorization. Hai nhóm điều khiển này bổ sung nhau, không thể thay thế lẫn nhau.

Tài liệu sử dụng YAML và lệnh **chỉ đọc hoặc thực thi trong lab được cấp quyền**. Các ví dụ có nhãn minh họa, không phải cấu hình production hoàn chỉnh. Không thử thay iptables/route trên node, không bắt gói tin của hệ thống không thuộc quyền, không gỡ security controls trong môi trường đang phục vụ người dùng.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, người học có thể:

1. Giải thích sự khác nhau giữa **Linux capability, root UID, privileged container, network namespace, CNI NetworkPolicy và application identity**.
2. Phân tích tác động bảo mật của **NET_ADMIN, NET_RAW, NET_BIND_SERVICE, SYS_ADMIN, BPF, PERFMON** và những capability liên quan.
3. Xác định phạm vi quyền: thay đổi network stack **trong Pod namespace** khác với thay đổi network stack **của node**.
4. Thiết kế **securityContext** cho Pod không cần quyền mạng đặc biệt: chạy non-root, **drop ALL**, không privilege escalation, seccomp phù hợp.
5. Đánh giá chính xác ngoại lệ cần thiết khi ứng dụng bind port thấp, mesh/CNI helper hoặc network troubleshooting.
6. Hiểu tác động của **hostNetwork, hostPID/hostIPC, privileged, hostPort, hostPath và user namespaces** lên ranh giới tin cậy.
7. So sánh **Pod Security Standards Restricted/Baseline**, Pod Security Admission và policy engines bên ngoài.
8. Phối hợp **NetworkPolicy, CNI/eBPF, seccomp, AppArmor/SELinux, IAM/RBAC và admission** để giảm blast radius.
9. Kiểm tra cấu hình/actual capabilities mà không thực hiện thay đổi nguy hiểm trên cluster thật.
10. Xây dựng **threat model, positive/negative tests, rollout và incident runbook** cho network privilege.

## 2. Những khái niệm không được nhầm lẫn

| Khái niệm | Quyết định điều gì? | Ví dụ | Điều không tự chứng minh |
|---|---|---|---|
| **Linux capability** | Tiến trình được làm thao tác kernel đặc quyền nào | CAP_NET_ADMIN, CAP_NET_RAW | Được truy cập một service bất kỳ |
| **UID/root** | Danh tính Unix và quyền theo DAC | UID 0, UID 10001 | Root luôn có mọi capability hoặc được vượt policy cloud |
| **Pod network namespace** | Nhóm interfaces, routes, sockets, network settings | Pod IP, loopback, port space | Là network namespace của host |
| **Privileged container** | Mở rộng đặc quyền container/runtime đáng kể | securityContext.privileged: true | An toàn chỉ vì không mở Service public |
| **hostNetwork** | Dùng network namespace của node | Pod thấy host network interfaces/routes | Có tách lớp NAT/Pod IP như Pod thường |
| **Core NetworkPolicy** | Quy tắc ingress/egress theo Pod/IP/port khi CNI thực thi | default-deny egress | Tước NET_ADMIN của process |
| **Seccomp** | Lọc syscall theo profile | RuntimeDefault | Tự quyết định API user nào được phép |
| **AppArmor/SELinux** | Giới hạn thao tác theo MAC profile/label | Runtime-specific policy | Tự thay route-level ACL |
| **RBAC/Admission** | Ai được tạo/sửa Pod spec, capabilities và policy | Deny privileged Pod | Bảo vệ hoàn toàn runtime sau khi Pod đang chạy |
| **mTLS/Identity** | Xác thực peer và quyền dịch vụ theo policy | Workload identity | Chặn packet sniffing hoặc route changes ở host |

Với Linux, **capability** là đơn vị đặc quyền riêng lẻ thay vì một công tắc “root có hết”. Một tiến trình chạy UID 0 có thể bị rút bớt capabilities; một tiến trình non-root có thể được cấp một capability cụ thể. Mức hiệu lực còn phụ thuộc **user namespace, bounding/permitted/effective sets, seccomp, LSM, kernel và runtime**.

### 2.1. Hai lớp độc lập trong một flow

~~~mermaid
flowchart LR
    P[Process trong container] --> CAP{Capability / syscall / LSM cho phép?}
    CAP -->|Không| EP[Thao tác kernel bị từ chối]
    CAP -->|Có| NS[Pod hoặc host network namespace]
    NS --> CNI{CNI / NetworkPolicy / Firewall}
    CNI -->|Deny| DROP[Không có đường kết nối được phép]
    CNI -->|Allow| DEST[Service / External endpoint]
    DEST --> AUTH{TLS peer và app authorization}
    AUTH -->|Allow| DATA[Dịch vụ trả dữ liệu được phép]
    AUTH -->|Deny| NO[Ứng dụng từ chối]
~~~

Một **CAP_NET_ADMIN bị từ chối** có thể ngăn một thao tác sửa routing, nhưng không nhất thiết cấm kết nối TCP thông thường. Một **NetworkPolicy deny** có thể ngăn kết nối tới DB, nhưng không thay thế việc tước quyền sửa interface/route của process.

## 3. Linux capabilities hoạt động ra sao?

Linux có nhiều nhóm capability, ví dụ quản lý file ownership, signals, process tracing, network, kernel modules. Trong container, runtime áp capability sets lên tiến trình. Các tập liên quan gồm:

- **Permitted (P):** các capability tiến trình có thể sử dụng/đưa vào effective theo quy tắc kernel.
- **Effective (E):** quyền đang được kernel kiểm tra khi thao tác đặc quyền.
- **Inheritable (I):** ảnh hưởng khả năng capability được giữ/chuyển qua exec trong điều kiện phù hợp.
- **Bounding (B):** giới hạn upper bound của những capability có thể nhận qua exec và file capabilities.
- **Ambient (A):** cơ chế giữ capabilities qua exec cho một số trường hợp process không đặc quyền, chịu điều kiện kernel.

**Một capability có tên trong YAML không chứng minh nó đang effective ở mọi process**; khi debug cần xem process thực tế, image, entrypoint, user namespace và runtime.

### 3.1. Ký hiệu trong Kubernetes

Linux thường dùng tên **CAP_NET_ADMIN**. Trong **securityContext.capabilities.add/drop** của Kubernetes, tên thường được viết **NET_ADMIN** hoặc **ALL** mà không có tiền tố CAP_.

~~~yaml
securityContext:
  capabilities:
    drop:
      - ALL
    add:
      - NET_BIND_SERVICE
~~~

Đoạn này biểu thị một **ngoại lệ cụ thể** so với drop-all. Không có nghĩa nên cấp NET_BIND_SERVICE mặc định cho mọi service; chỉ dùng nếu ứng dụng thực sự cần bind privileged port và môi trường không có cách ít quyền hơn.

### 3.2. Capability không tự tạo lối thoát khỏi container

**CAP_NET_ADMIN trong một network namespace riêng** thường cho phép quản lý tài nguyên mạng thuộc namespace đó, **không tự cấp quyền quản lý toàn bộ host network**. Tuy vậy:
- Nhiều container trong Pod **chia sẻ network namespace**; một container có quyền có thể làm thay đổi đường đi của container còn lại.
- Host networking khiến scope của các network operations liên quan đến host khác hoàn toàn với Pod riêng.
- Các tính năng kernel/runtime, mount/host access, user namespace và lỗ hổng có thể thay đổi mức rủi ro.
- NetworkPolicy và CNI enforcement phụ thuộc data plane thực tế; đừng coi mọi route manipulation đều là bypass, cũng đừng coi mọi implementation miễn nhiễm.

Rủi ro phải được đánh giá theo **quyền + namespace + runtime + điểm thực thi policy**, không chỉ dựa vào tên capability.

## 4. Bảng các network-related capabilities đáng quan tâm

| Capability | Công dụng hợp pháp thường gặp | Rủi ro khi cấp không cần thiết | Ghi nhớ |
|---|---|---|---|
| **CAP_NET_ADMIN** | Quản lý interface, route, network parameters, traffic control/firewall theo scope | Thay đường lưu lượng, ảnh hưởng sidecar, traffic inspection hoặc namespace networking | Rất nhạy cảm; không cấp cho business app thông thường |
| **CAP_NET_RAW** | Raw sockets, packet sockets, một số công cụ chẩn đoán mạng | Tạo/quan sát packet ở mức thấp trong giới hạn namespace, mở rộng bề mặt tương tác network | Không cần cho HTTP client/server bình thường |
| **CAP_NET_BIND_SERVICE** | Bind một số privileged ports (theo kernel/config) | Cho process bind port thấp không được cấp nếu không có quyền | Hẹp hơn NET_ADMIN; có thể tránh bằng port không đặc quyền |
| **CAP_BPF** | Một số thao tác BPF đặc quyền trên kernel hỗ trợ | Can thiệp vào khu vực eBPF nếu đồng thời có những quyền cần thiết khác | Không cần cho ứng dụng thường; kernel-version dependent |
| **CAP_PERFMON** | Truy cập một số cơ chế performance monitoring | Tăng khả năng quan sát sự kiện kernel/process | Cần giới hạn với agent được quản lý |
| **CAP_SYS_ADMIN** | Tập đặc quyền kernel rất rộng, nhiều tác vụ namespace/mount | Tăng đáng kể attack surface và rủi ro vượt ranh giới | Tránh cấp cho workload thông thường |
| **CAP_SYS_MODULE** | Quản lý kernel modules trong điều kiện cho phép | Tác động sâu tới node/kernel | Không phải nhu cầu của Pod nghiệp vụ |
| **CAP_SYS_PTRACE** | Debug/tracing process phù hợp phạm vi | Rò dữ liệu process/credential | Không cấp chỉ để chạy network debugging chung |
| **CAP_NET_BROADCAST** | Capability dành cho broadcast theo lịch sử | Không có trường hợp sử dụng phổ biến trên Linux hiện đại | Không cấp nếu không có yêu cầu được xác minh |

**Capability được kiểm tra cùng những điều kiện khác**; ví dụ tải/gắn một chương trình eBPF có thể phụ thuộc kernel version, CAP_BPF, CAP_NET_ADMIN, CAP_PERFMON, CAP_SYS_ADMIN, sysctl, LSM và loại attachment. Không kết luận chỉ một capability đủ thao tác mọi dạng eBPF.

## 5. NET_ADMIN: vì sao cần kiểm soát chặt?

**CAP_NET_ADMIN** là capability nhạy cảm trong mảng mạng. Một process được cấp nó, trong phạm vi namespace và các kiểm soát kernel tương ứng, có thể được phép thao tác những chức năng như:

- Quản lý một số interface flags, virtual network interfaces và network settings.
- Sửa các tuyến, policy routing và địa chỉ IP trong network namespace.
- Quản lý traffic control/qdisc hoặc network filters tương ứng.
- Thay một số network firewall/routing rules tùy backend và quyền liên quan.
- Tương tác với các chức năng đặc quyền của network stack.

### 5.1. Ví dụ sự cố trong Pod nhiều container

Một Pod có **application container** và **service-mesh sidecar** chia sẻ network namespace. Sidecar sử dụng các route/redirect rules để ứng dụng đi qua proxy. Nếu application container cũng được NET_ADMIN mà không cần:

1. Ứng dụng có thêm khả năng thay đổi network configuration trong namespace chung.
2. Các redirect assumptions của mesh có thể không còn đúng.
3. Luồng mạng, logging hoặc mTLS intercept có thể sai lệch, tùy cơ chế thực thi.
4. Ứng dụng và sidecar cùng gặp lỗi khó chẩn đoán.

Không được suy rằng **mọi CNI NetworkPolicy đều bị bypass** khi có NET_ADMIN. Nhiều chính sách được thực thi ở host/veth/eBPF ngoài network namespace của Pod. Câu đúng là **NET_ADMIN mở rộng quyền thao tác mạng và có thể làm suy yếu một số giả định/đường bảo vệ**, nên phải test trên datapath thực.

### 5.2. Có cần NET_ADMIN cho iptables trong init container?

Một số cách triển khai service mesh cũ hoặc custom networking từng dùng **init container có NET_ADMIN** để thiết lập redirect rules; những triển khai khác dùng **CNI plugin** hoặc datapath không cần app Pod giữ quyền này. Không cấp NET_ADMIN cho toàn bộ app container chỉ vì một init helper cần thiết lập quy tắc mạng.

Khi phải dùng ngoại lệ:
- Tách **init/helper** khỏi application container theo phạm vi khả thi.
- Dùng image đã được kiểm soát, không chứa tools rộng không cần.
- Giới hạn quyền và kiểm tra khả năng sidecar/CNI thay thế tác vụ.
- Kiểm tra admission, namespace, filesystem mounts, service account và audit.
- Có kế hoạch loại bỏ ngoại lệ sau chuyển sang cơ chế ít quyền hơn.

### 5.3. Khi Pod dùng hostNetwork

Một container chạy **hostNetwork: true** sử dụng network namespace của node. Kết hợp với NET_ADMIN/privileged có thể mở rộng ảnh hưởng tới network configuration của node, chứ không chỉ một Pod network namespace. Đây là **rủi ro cao hơn nhiều**, cần chính sách từ chối mặc định và quy trình ngoại lệ riêng cho network agents hệ thống.

## 6. NET_RAW: raw sockets, packet sockets và suy luận đúng mức

**CAP_NET_RAW** có thể cho phép tạo một số **raw sockets hoặc packet sockets** theo quyền sở hữu user/network namespace. Nó hữu ích với công cụ network diagnostics đặc biệt, song hầu hết REST APIs, queue workers, web frontends và database clients không cần capability này.

### 6.1. Raw packet có thể bị lạm dụng thế nào?

- Tương tác với packets ở mức thấp hơn socket TCP/UDP thông thường.
- Thu nhận hoặc gửi một số packet types theo scope/interface và kernel rules.
- Tạo traffic bất thường làm phức tạp phân tích sự cố.
- Làm rộng bề mặt tiếp xúc của kernel networking stack.

**Không đồng nhất CAP_NET_RAW với khả năng sniff mọi traffic cluster.** Packet visibility phụ thuộc network namespace, interfaces, switch/overlay paths, CNI, privileges khác và LSM/namespace restrictions.

### 6.2. Ping có nhất thiết cần CAP_NET_RAW?

**Không phải trong mọi cấu hình Linux.** Một số phiên bản **ping** có thể dùng ICMP datagram sockets được kiểm soát bởi **ping_group_range** thay vì raw socket. Vì vậy:
- Ping chạy được **không chứng minh** tiến trình có NET_RAW.
- Drop NET_RAW **không bảo đảm** mọi ICMP ping đều thất bại.
- Việc ping không chạy cũng có thể do ICMP policy, DNS, routing hoặc executable/config.

Để xác minh capability, xem **securityContext và process capability sets**, không dùng ping làm phép thử duy nhất.

### 6.3. Debug tools và nguyên tắc tạm thời

Khi cần packet capture trong incident được phê duyệt, nên dùng **node/network diagnostics agent có owner rõ** hoặc container debug được kiểm soát với scope tối thiểu, logs và expiry. Không duy trì NET_RAW toàn thời gian trong image production chỉ vì thỉnh thoảng cần tcpdump.

## 7. NET_BIND_SERVICE: trường hợp ngoại lệ hẹp

Trên Linux truyền thống, bind vào TCP/UDP ports **nhỏ hơn 1024** cần CAP_NET_BIND_SERVICE hoặc điều kiện được kernel cho phép. Trong một số runtime/network namespaces, **net.ipv4.ip_unprivileged_port_start** có thể thay đổi ngưỡng, kể cả đặt là 0; vì vậy không nên khẳng định mọi Pod đều cần capability này để listen 80/443.

### 7.1. Phương án ưu tiên

- Cho ứng dụng nghe **8080 hoặc 8443** trong Pod.
- Dùng **Kubernetes Service/Ingress/LoadBalancer** đưa cổng 80/443 bên ngoài tới **targetPort** cao hơn.
- Chạy container với **UID không phải root**, drop ALL và không cần NET_BIND_SERVICE.
- Nếu thật sự phải bind port thấp ở namespace đó, đánh giá ngoại lệ NET_BIND_SERVICE và cấu hình kernel/runtime, đồng thời không cấp NET_ADMIN.

~~~mermaid
flowchart LR
    CLIENT[HTTPS client :443] --> LB[Ingress / LB :443]
    LB --> SERVICE[Kubernetes Service port 443]
    SERVICE --> APP[Pod ứng dụng targetPort 8443]
    NOTE[Non-root + drop ALL capabilities] -.Áp cho app.-> APP
~~~

### 7.2. Tại sao cần hiểu ngưỡng kernel?

Nếu low port đã được cấu hình **unprivileged** trong network namespace, thêm NET_BIND_SERVICE không tạo giá trị cần thiết nhưng vẫn mở thêm quyền. Nếu ngưỡng khác giữa local Docker và cluster, ứng dụng có thể chỉ fail trong một môi trường. **Kiểm tra runtime configuration và lựa chọn cổng** trước khi mở ngoại lệ.

## 8. CAP_BPF, CAP_PERFMON và SYS_ADMIN: liên hệ eBPF/CNI

Nhiều CNI và observability agents hiện đại sử dụng **eBPF** để xử lý packets, network flows hoặc tracing. Một số thao tác BPF yêu cầu capability đặc biệt; kể từ các kernel hiện đại có **CAP_BPF** và **CAP_PERFMON**, trong khi những kernel/tính năng khác còn dựa vào **CAP_SYS_ADMIN** hoặc **CAP_NET_ADMIN**.

### 8.1. Phân biệt hai loại workload

- **Business Pod:** phục vụ API, xử lý đơn hàng, chạy batch; thường **không cần BPF/NET_ADMIN/SYS_ADMIN**.
- **Trusted node networking agent:** CNI, eBPF observability hoặc security sensor; có thể cần quyền mạnh để attach programs, quản lý maps, interfaces hoặc truy cập host networking.

Cho một node networking agent nhiều quyền không có nghĩa **mọi Pod trên node** phải nhận cùng capabilities.

### 8.2. Rủi ro khi đưa quyền agent vào app

Nếu Pod app có CAP_BPF/SYS_ADMIN/NET_ADMIN mà không cần:
- Bề mặt tương tác với kernel/control plane tăng.
- Khả năng can thiệp telemetry hoặc datapath trong những điều kiện phù hợp tăng.
- Một lỗi app có thể gây tác động nghiêm trọng hơn trong network namespace/runtime.
- Khó chứng minh container vẫn tuân thủ mô hình least privilege.
- Một số audit/Pod Security policies sẽ từ chối workload.

**Không giả định CAP_BPF một mình đủ thay thế mọi CNI authorization.** Thao tác BPF phụ thuộc loại program/attach point, kernel, namespaces, seccomp, LSM và host permissions.

### 8.3. Lựa chọn kiến trúc

Đặt agent đặc quyền ở **node-level managed DaemonSet/host process** theo quy trình chuyên biệt, RBAC thấp nhất có thể, signer/provenance của image, node pool isolation nếu cần, không mở quyền cho toàn namespace ứng dụng. Hạn chế quyền sửa DaemonSet và các volume/hostPath nhạy cảm.

## 9. Pod network namespace: phạm vi một quyền

Kubernetes Pod gồm một hoặc nhiều containers thường chia sẻ:
- **Pod IP** và các network interfaces trong Pod network namespace.
- **Loopback**: container A gọi localhost port do container B bind nếu tương ứng.
- **TCP/UDP port space**: không thể bind cùng IP/port xung đột giữa các container.
- **Routing/iptables rules** trong namespace, theo những capability và chính sách cho phép.
- Một số network sysctls được namespaced theo kernel/policy.

~~~mermaid
flowchart TB
    subgraph POD["Pod network namespace 10.244.8.10"]
      APP[Application container\nNET_ADMIN: absent]
      SIDECAR[Proxy sidecar\nspecial rights only if justified]
      ROUTE[Interfaces / routes / sockets / local redirects]
      APP --> ROUTE
      SIDECAR --> ROUTE
    end
    VETH[Pod veth / CNI datapath] --- POD
    VETH --> HOST[Node networking / CNI enforcement]
    HOST --> NET[Cloud VPC / Services]
~~~

### 9.1. Vấn đề bảo mật khi share network namespace

Một container bị chiếm có thể:
- Kết nối tới service chạy trên **localhost** trong cùng Pod nếu service không tự xác thực.
- Dùng cùng Pod IP để phát request; flow logs Pod-level khó phân biệt container nguồn.
- Làm thay đổi network settings chung nếu được cấp NET_ADMIN.
- Tạo network traffic tiêu thụ chung quota/connection budgets.

Vì vậy **Pod là một ranh giới tin cậy quan trọng**, không nên đặt hai workloads có mức tin cậy đối lập trong cùng một Pod chỉ để tiết kiệm tài nguyên.

### 9.2. Network namespaces không tách toàn bộ kernel

Các containers vẫn dùng kernel của node (trừ sandbox/VM runtime có cơ chế riêng). User namespace, seccomp/LSM, cgroups và runtime restrictions vẫn cần thiết. **Không đánh đồng “có network namespace riêng” với “có kernel riêng”.**

## 10. hostNetwork, hostPort và những đường mạng đặc biệt

### 10.1. hostNetwork

**spec.hostNetwork: true** cho Pod dùng network namespace của node. Nó có thể là nhu cầu hợp lệ của một số node network agents, nhưng với app thông thường:
- IP/port space của node trở thành yếu tố trực tiếp.
- Một ứng dụng có thể bind hoặc nghe trên host interfaces theo permission và address.
- Pod có thể thấy các đường network/node-local không giống Pod thông thường.
- Core NetworkPolicy enforcement cho hostNetwork có **khác biệt theo CNI**; không giả định đầy đủ.
- Nếu cộng privileged/NET_ADMIN, rủi ro thay đổi host networking tăng đáng kể.

### 10.2. hostPort

**hostPort** ánh xạ port trên node tới Pod theo cơ chế runtime/CNI. Nó không đồng nghĩa hostNetwork, nhưng tạo **host-level reachability** có thể bỏ qua đường Ingress dự tính nếu node firewall/SG cho phép. Cần kiểm soát ports, address families, admission và alternate routes.

### 10.3. hostPID/hostIPC/hostPath và mức quyền

- **hostPID/hostIPC** chia sẻ thêm namespace của host, tăng nguy cơ quan sát/chạm dữ liệu node tùy quyền.
- **hostPath** có thể cấp quyền truy cập các thư mục nhạy cảm như network runtime sockets hoặc host filesystem.
- **Privileged** có thể bỏ qua nhiều hạn chế runtime và mở rộng quyền với devices/kernel.
- **CAP_SYS_ADMIN** là capability rộng, không phải công tắc “chỉ sửa route”.

Đối với Pod thông thường, nên **không dùng** các trường này nếu không có nhu cầu được xác minh. Đối với CNI/agent nền tảng cần quyền cao, dùng **namespace/system service account riêng, image được tin và policy exception có audit**.

## 11. SecurityContext mẫu cho ứng dụng không cần network capability

Một baseline tham khảo cho workload ứng dụng:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      hostNetwork: false
      hostPID: false
      hostIPC: false
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: registry.example/orders-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            privileged: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              memory: "512Mi"
~~~

Đây là **mẫu học tập**. Cần kiểm tra image có hỗ trợ non-root, write paths, filesystem ownership, health probes, read-only rootfs và entrypoint. Nếu ứng dụng cần ghi file tạm, cấp volume/tmp phù hợp theo policy; không loại bỏ toàn bộ securityContext chỉ để làm chương trình chạy.

### 11.1. Vì sao mỗi trường có ý nghĩa?

| Trường | Ý định | Giới hạn |
|---|---|---|
| runAsNonRoot: true | Từ chối chạy dưới UID 0 theo kubelet/runtime checks | Không tự bỏ Linux capabilities đã cấp |
| runAsUser/runAsGroup | Chọn UID/GID cụ thể | Phụ thuộc image và file permissions |
| allowPrivilegeEscalation: false | Ngăn process tăng đặc quyền qua exec theo no_new_privs khi áp dụng | Không thu hồi những quyền đã có; có ngoại lệ/semantics với privileged hoặc CAP_SYS_ADMIN |
| capabilities.drop: [ALL] | Loại capability sets mặc định theo runtime | Không tự chặn network TCP/UDP bình thường |
| privileged: false | Không yêu cầu chế độ privileged | Chưa đủ để bảo đảm không có capabilities nguy hiểm được add |
| seccompProfile: RuntimeDefault | Áp seccomp mặc định của runtime hỗ trợ | Profile cụ thể khác nhau theo runtime |
| readOnlyRootFilesystem: true | Giảm khả năng ghi lên root filesystem | Không phải điều kiện cốt lõi của mọi Pod Security Standards và không chặn egress |
| hostNetwork/hostPID/hostIPC: false | Tránh chia sẻ host namespaces tương ứng | Không thay kernel/runtime isolation |

**Không có một trường đơn lẻ chứng minh Pod an toàn**. Pod cần được kiểm tra cả **init containers, ephemeral containers, sidecars, volume mounts, admission policy, CNI và workload identity**.

### 11.2. Container port 8080, Service port 80

Có thể dùng Service port 80 hoặc Ingress 443 trỏ tới containerPort 8080/8443. Do đó Pod không nhất thiết cần NET_BIND_SERVICE ngay cả khi API được người dùng truy cập qua 80/443 ở phía ngoài.

## 12. Ngoại lệ tối thiểu khi thực sự phải bind port thấp

Nếu một image cần bind cổng thấp trong network namespace của nó, sau khi xác minh kernel threshold và không thể chuyển sang port cao, có thể xét:

~~~yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  privileged: false
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop:
      - ALL
    add:
      - NET_BIND_SERVICE
~~~

**Đây là đoạn minh họa container.securityContext**, cần đặt ở đúng vị trí trong manifest thật. Không thể đặt field capabilities trực tiếp dưới Pod-level spec.securityContext rồi mặc định runtime hiểu đúng; Kubernetes đặt **capabilities** ở **container-level securityContext**.

Phải chứng minh:
- App thực sự bind cổng thuộc privileged range ở môi trường này.
- NET_BIND_SERVICE là quyền duy nhất cần cộng.
- NET_ADMIN, NET_RAW và SYS_ADMIN không cần thiết.
- Không có cách chuyển Service/Ingress sang targetPort cao hơn.
- Cơ chế Pod Security Admission và security tests cho phép ngoại lệ.
- Không dùng hostNetwork chỉ để bind low port.

Nếu có thể dùng cổng không đặc quyền, **drop ALL mà không add gì** vẫn là phương án dễ quản lý nhất.

## 13. Pod Security Standards: Privileged, Baseline và Restricted

Kubernetes **Pod Security Standards (PSS)** mô tả các profile an ninh cho Pod. Chúng giúp chuẩn hóa các hạn chế đối với privileged containers, host namespaces, capabilities, seccomp và một số securityContext fields.

| Profile | Mục đích | Ý nghĩa đối với network capabilities |
|---|---|---|
| **Privileged** | Gần như không hạn chế theo PSS | Không phù hợp làm baseline workload đa tenant |
| **Baseline** | Ngăn những cấu hình escalation đã biết là nguy hiểm | Có danh sách giới hạn những capabilities được **add**; NET_ADMIN/NET_RAW không thuộc danh sách thêm được chấp thuận |
| **Restricted** | Bổ sung hardening và least privilege | Container phải **drop ALL**, chỉ được add **NET_BIND_SERVICE** theo chính sách; yêu cầu non-root và seccomp phù hợp |

### 13.1. Điều kiện Restricted quan trọng

Với PSS **Restricted**, những kiểm soát thường bao gồm:
- Không chạy privileged.
- Không cho hostNetwork/hostPID/hostIPC.
- Không sử dụng hostPath theo profile.
- Container/Init/Ephemeral securityContext đáp ứng các yêu cầu theo policy.
- **capabilities.drop: [ALL]** bắt buộc trên những loại container thuộc phạm vi.
- Trong các capabilities có thể add, chỉ **NET_BIND_SERVICE** được chấp nhận theo Restricted.
- **allowPrivilegeEscalation: false** trong phạm vi được yêu cầu, với một số ngoại lệ và xử lý liên quan hệ điều hành/nền tảng.
- Cấu hình non-root phù hợp.
- Seccomp **RuntimeDefault** hoặc **Localhost** được phép theo chuẩn; không dùng Unconfined trong profile yêu cầu.
- Các điều kiện về volumes, sysctls và hostPort theo phiên bản chính sách.

**Các điều kiện PSS có thể thay đổi theo phiên bản Kubernetes và hệ điều hành Pod**. Phải kiểm tra đúng profile/version được enforce trong cluster. Trên một số nền tảng Windows, một số Linux-only securityContext fields không áp dụng theo cùng cách. Bài học tập trung Linux Pods.

### 13.2. Baseline có cho NET_BIND_SERVICE không?

PSS **Baseline** hạn chế danh sách capabilities được phép **thêm vào**; NET_BIND_SERVICE nằm trong danh sách đó. Nhưng Baseline **không nhất thiết bắt buộc drop ALL** như Restricted. Vì thế một Pod đạt Baseline chưa chắc đã có mức least privilege cao nhất về capabilities.

### 13.3. “Restricted PASS” không chứng minh hoàn toàn an toàn

PSS không tự xác minh:
- CNI đang thực thi NetworkPolicy.
- API có authentication/authorization đúng.
- File image có vulnerability hay không.
- Service account có cloud IAM scope quá rộng.
- Egress đi qua proxy và firewall đúng không.
- Business Pod có quyền truy cập dữ liệu theo tenant hay không.
- Mọi runtime admission exemptions và workload đã tồn tại.

**PSS là kiểm soát đầu vào cấu hình Pod, không phải thay thế toàn bộ security architecture.**

## 14. Pod Security Admission: enforce, audit và warn

**Pod Security Admission (PSA)** là cơ chế admission gắn với các nhãn namespace để áp Pod Security Standards theo mode. Nó có ba nhóm hành vi:

- **enforce:** từ chối tạo/cập nhật Pod vi phạm policy trong phạm vi admission.
- **audit:** ghi nhận vi phạm trong audit annotations/events theo khả năng/thiết lập.
- **warn:** phát cảnh báo cho người thao tác khi request vi phạm.

Ví dụ nhãn namespace ở mức ý tưởng:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders-prod
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
~~~

**Không apply trực tiếp cho production khi chưa kiểm kê workload**, vì enforcement có thể chặn rollout của init containers, sidecars hoặc agents chưa tuân thủ. Với môi trường thực, nên **pin policy version được phê duyệt** bằng các nhãn **enforce-version/audit-version/warn-version** và xem lại khi nâng cluster; nếu bỏ version, mặc định có thể theo cách diễn giải “latest” của hệ thống.

### 14.1. Lộ trình triển khai PSA

1. Lập inventory Pods, init containers, ephemeral containers, DaemonSets.
2. Thử **warn/audit** trước khi bật enforce ở môi trường production.
3. Phân loại failures theo capability, privileged, host namespace, seccomp, user, volumes.
4. Sửa image hoặc workload spec, loại quyền không cần.
5. Chọn namespace pilot và chạy negative/positive tests.
6. Bật enforce theo rollout được quản trị; ghi quyền ngoại lệ rõ ràng.
7. Kiểm tra config drift và cluster version changes.
8. Theo dõi từ chối deployments, workload health và incident logs.

### 14.2. Exemptions phải được quản trị

PSA có thể cấu hình **exemptions** theo identities, namespaces hoặc runtimeClasses ở control plane tùy triển khai. Một namespace thuộc hệ thống có thể chứa CNI agents được phép dùng host networking hoặc capabilities mạnh. Nếu exemption quá rộng, người có quyền tạo Pod trong phạm vi đó có thể không gặp kiểm soát mong muốn.

**Không coi tên namespace "kube-system" tự tạo exemption an toàn.** Phải kiểm tra cấu hình admission thực và Kubernetes RBAC để biết ai được deploy/sửa những workloads được exempt.

### 14.3. PSA và workload đã tồn tại

Admission thường đánh giá **request tạo/cập nhật** thuộc phạm vi. Đổi nhãn namespace sang Restricted **không có nghĩa mọi Pod đang chạy bị evict tức thì** và không đảm bảo cluster tự sửa spec. Phải inventory Pods hiện hữu, lên kế hoạch rolling replacement và xác minh policy được áp cho Pod mới.

## 15. Vì sao NetworkPolicy không thay việc drop capabilities?

Core **Kubernetes NetworkPolicy** thường chọn Pods và cho phép lưu lượng ingress/egress theo Pod/namespace/CIDR/port khi CNI hỗ trợ. Nó điều khiển **luồng packet**, không tước **CAP_NET_ADMIN/NET_RAW** của process.

~~~mermaid
flowchart TB
    subgraph POD[Pod Orders API]
      APP[Process: drop ALL]
      NETNS[Pod netns: interface/route/sockets]
      APP --> NETNS
    end
    NETNS --> CNI[CNI enforcement: NetworkPolicy]
    CNI --> FW[Cloud security group / firewall]
    FW --> DB[(Approved DB)]
    PSA[Pod Security Admission] -.Kiểm tra spec.-> POD
    LSM[Seccomp + AppArmor/SELinux] -.Giới hạn process.-> APP
    APPID[Workload identity / mTLS] -.Xác thực app.-> DB
~~~

### 15.1. Bốn trường hợp cần phân biệt

| Capabilities trong Pod | NetworkPolicy | Điều có thể xảy ra |
|---|---|---|
| Drop ALL | Không có isolation | Process thiếu đặc quyền nhưng vẫn có thể mở kết nối thông thường tới nhiều địa chỉ |
| Có NET_ADMIN | Default-deny egress | Process có thể sửa một số network settings thuộc scope, nhưng traffic ngoài policy vẫn có thể bị CNI chặn |
| Drop ALL | Egress allowlist | Quyền kernel thấp, luồng chỉ tới đích được cấp khi CNI thực thi |
| Privileged/hostNetwork | Policy kiểu Pod thường | Rủi ro ngoài mô hình/khả năng enforcement cần kiểm chứng riêng |

**Không được tuyên bố CAP_NET_ADMIN tự động bypass tất cả NetworkPolicy.** Nhưng cũng không nên cho NET_ADMIN với giả định CNI sẽ xử lý mọi rủi ro do route/interface/packet manipulation.

### 15.2. Giới hạn của Pod-level traffic attribution

Nhiều container trong một Pod có cùng **Pod IP**; NetworkPolicy thường chọn cả Pod và traffic logs có thể gắn Pod UID hơn là container ID. Nếu sidecar và application có quyền/dữ liệu khác nhau, egress policy theo Pod chưa chắc phân biệt được chúng.

Giải pháp gồm:
- Tách workloads có mức tin cậy khác nhau vào các Pods riêng.
- Dùng service identity/app authorization cho từng logical service.
- Giới hạn capabilities riêng từng container và tránh shared host mounts.
- Với telemetry nâng cao, dùng công cụ được quản trị có khả năng attribution phù hợp, không tự giả định Core NetworkPolicy có container-level rules.

## 16. Init containers, sidecars và ephemeral debug containers

Các loại container không phục vụ business requests trực tiếp vẫn ảnh hưởng đến Pod security.

### 16.1. Init container

Một init container chạy trước app containers có thể:
- Chỉnh file permissions.
- Chuẩn bị configuration.
- Thiết lập redirect networking theo một số mesh deployment.
- Kiểm tra dependency hoặc startup prerequisites.

Nếu init container có **NET_ADMIN/privileged**, nó có thể tạo network settings còn ảnh hưởng khi app chạy sau đó, do network namespace được chia sẻ. Do đó **"app container drop ALL" chưa đủ nếu init container vẫn có đặc quyền và có thể thay đổi network path**.

### 16.2. Sidecar container

Sidecar có thể là proxy TLS/mTLS, logging agent hoặc local cache. Các câu hỏi:
- Nó có **CAP_NET_ADMIN** để sửa redirect rules không?
- Có thể dùng **CNI-managed redirect** để tránh capability trong Pod không?
- Nó có listen trên localhost port mà app hoặc bên khác có thể gọi không?
- Có quyền mount secret/truststore của app không?
- Log có chứa raw Authorization headers/token không?
- Có được truy cập Kubernetes API hay metadata không?

Các mô hình **native sidecars** hoặc sidecar chạy theo cơ chế init container có thể có semantics lifecycle khác tùy phiên bản Kubernetes. Cần kiểm tra thực tế thay vì nhìn đơn giản vào tên container.

### 16.3. Ephemeral containers cho debugging

Kubernetes cho phép dùng **ephemeral containers** trong một số trường hợp debugging Pod đã chạy. Chúng vẫn là thành phần nhạy cảm:
- Quyền tạo/debug qua subresource phải được RBAC quản lý.
- Security policy/admission có thể ràng buộc securityContext.
- Ephemeral container thường chia sẻ network namespace của Pod mục tiêu.
- Nâng cấp debug container thành privileged/NET_ADMIN trên production có thể làm thay đổi rủi ro đáng kể.
- Hoạt động debug cần audit, ticket, người phê duyệt và retention của artifacts.

**Không dùng debug exception để tạo đường nâng quyền lâu dài**. Nếu cần network capture, ưu tiên sensor đã phê duyệt và giới hạn thời gian/phạm vi.

## 17. Seccomp, AppArmor và SELinux: chặn thao tác dù có route

### 17.1. Seccomp

**Seccomp** lọc các syscalls của process. Một profile có thể hạn chế syscalls nguy hiểm hoặc không cần thiết, trong khi capability kiểm tra quyền đối với các syscalls/operations được gọi. Hai lớp bổ trợ:
- Không có capability cần thiết → kernel từ chối operation đặc quyền theo check tương ứng.
- Có capability nhưng syscall bị seccomp chặn → operation vẫn có thể bị từ chối.
- Syscall được phép và có capability → vẫn chịu LSM, namespaces và những kiểm tra kernel khác.

~~~yaml
securityContext:
  seccompProfile:
    type: RuntimeDefault
~~~

**RuntimeDefault** nghĩa profile do container runtime cung cấp, không phải một danh sách syscall giống hệt mọi máy. Nên thử ứng dụng trên runtime thực tế; nếu cần **Localhost profile**, phải phân phối, versioning và kiểm thử trên nodes phù hợp.

### 17.2. AppArmor

**AppArmor** có thể dùng profile để hạn chế file/system operations theo môi trường/kernel. Một số phiên bản Kubernetes có trường securityContext AppArmor trực tiếp; cách khai báo và default behavior phụ thuộc version, runtime và node support.

Không mặc định một Pod dùng AppArmor nếu node không bật/không load profile. Không tự đặt **Unconfined** để sửa lỗi mà không đánh giá.

### 17.3. SELinux

**SELinux** dùng security labels/policies theo mô hình mandatory access control. Nó hữu ích khi phân tách process/resources ở những distributions/runtime hỗ trợ. Một Pod có SELinux label không tự có egress allowlist; cần phối hợp NetworkPolicy và firewall.

### 17.4. Read-only filesystem và non-root

- **readOnlyRootFilesystem** giảm cơ hội thay đổi image filesystem lúc chạy, nhưng không nhất thiết chặn ghi vào mounted volumes và không chặn TCP/UDP outbound.
- **runAsNonRoot** giảm tác hại của root UID, nhưng không tự xóa capabilities đã add.
- **allowPrivilegeEscalation: false** giảm đường tăng đặc quyền qua exec; không xóa các thao tác đã được phép cho process.
- **privileged: false** không chứng minh app thiếu NET_ADMIN nếu capability được add riêng.

Đánh giá **tổ hợp các trường** thay vì coi một “securityContext: {}” mặc định là hardening.

## 18. Network-related sysctls: quyền kernel bổ sung cần kiểm soát

**sysctl** là cơ chế cấu hình kernel. Một số sysctls được **namespaced** và Kubernetes hỗ trợ khai báo ở **Pod-level securityContext.sysctls** theo phạm vi cho phép. Các sysctls khác là cấp node/global hoặc có nguy cơ tác động ngoài Pod.

### 18.1. Ví dụ về tác động

| Nhóm | Mục đích | Rủi ro nếu cấu hình tùy tiện |
|---|---|---|
| net.ipv4.ip_unprivileged_port_start | Ngưỡng port cần CAP_NET_BIND_SERVICE trong namespace tương ứng | Thay giả định low-port privilege |
| net.ipv4.tcp_* | Các tham số TCP được namespaced/allowlisted tùy version | Ảnh hưởng hiệu năng/kết nối và timeout |
| net.ipv4.ip_local_port_range | Khoảng local ephemeral ports theo hỗ trợ | Port collisions/exhaustion khi sai |
| net.ipv4.ip_forward | Hành vi forward packet trong network namespace | Có thể tạo routing/forwarding không dự định nếu được cho phép |
| net.netfilter.* | Một số netfilter settings | Ảnh hưởng conntrack/NAT/firewall theo scope |

**Không có danh sách sysctls "an toàn" bất biến cho mọi version và CNI**. Kubernetes phân biệt nhóm *safe* cho phép theo version và *unsafe* chỉ được bật bằng cấu hình kubelet/policy phù hợp. Một sysctl được namespaced không tự an toàn cho mọi workload.

### 18.2. Tránh mở unsafe sysctls toàn cluster

Nếu dùng **allowed-unsafe-sysctls** trên kubelet hoặc policy tương đương, quyền có thể tác động nhiều Pods lên node; cần:
- Giới hạn node pools và workloads có owner.
- Kiểm tra scheduler, node config và admission.
- Có reason, reviewer và rollback.
- Không áp sysctl node-level qua cơ chế Pod không hỗ trợ.
- Đo tác động tới CNI, service mesh, probes và neighboring workloads.

### 18.3. Ví dụ về Pod-level sysctl có điều kiện

~~~yaml
spec:
  securityContext:
    sysctls:
      - name: net.ipv4.ip_unprivileged_port_start
        value: "0"
~~~

**Chỉ là minh họa cơ chế**, không phải yêu cầu phải cấu hình. Trước khi dùng, kiểm tra sysctl có được Kubernetes/kernel/CNI/runtime/version cho phép và ảnh hưởng theo network namespace. Có thể **tránh cả sysctl và NET_BIND_SERVICE** bằng cách cho app chạy trên cổng cao.

## 19. User namespaces, rootless và ranh giới quyền trên host

**Linux user namespace** tách ánh xạ UID/GID/capabilities khỏi host theo những quy tắc kernel. Một tiến trình thấy mình là root trong user namespace không tự là host root. Tuy vậy, hiệu quả với Pod phụ thuộc **cách runtime/Kubernetes hỗ trợ, UID mapping, filesystems, CNI và isolation**.

### 19.1. Khi nào user namespace giúp ích?

- Giảm một số rủi ro khi process trong container trở thành UID 0.
- Thu hẹp phạm vi capabilities theo user namespace sở hữu tài nguyên.
- Là một lớp bổ sung cùng seccomp, LSM và runtime isolation.

### 19.2. Điều vẫn phải xem xét

- Networking và Pod network namespace có thể được thiết lập bởi runtime với ownership/mapping khác nhau.
- Những operations trên host resources vẫn chịu host permissions.
- Host mounts/devices/sockets có thể tạo đường vượt ranh giới dự kiến nếu không kiểm soát.
- NET_ADMIN/NET_RAW có nghĩa khác khi được đánh giá trong namespace riêng và khi chia sẻ hostNetwork.
- CNI, CSI và runtime support không đồng nhất giữa versions/providers.

**Rootless container không có nghĩa NetworkPolicy tự được áp**, và user namespace không thay role-based Kubernetes admission hoặc network segmentation.

## 20. Kubernetes RBAC và admission: ai được cấp quyền mạng?

Ngay cả khi một image app chạy an toàn hôm nay, một người có quyền patch Deployment hoặc create Pods có thể sửa securityContext/hostNetwork nếu admission không ngăn. Do đó **Kubernetes API permissions là một phần của network security threat model**.

### 20.1. Tài nguyên cần bảo vệ

- Create/patch **Pod/Deployment/DaemonSet/Job**.
- Patch **ephemeralcontainers** subresource trong trường hợp được hỗ trợ.
- Create/modify **NetworkPolicies** và CNI policy CRDs.
- Modify **namespace labels** dùng làm security selectors hoặc PSA.
- Update **ServiceAccounts** và quyền token access.
- Change **RuntimeClass**, node selectors, taints/tolerations.
- Access **hostPath**, CSI secrets và host networking related agents.
- Modify **Ingress/Gateway/Services/NodePort/LoadBalancer** tạo đường tới host ports.
- Deploy privileged CNI/observability DaemonSets.

### 20.2. Tách vai trò

| Actor | Quyền hợp lý | Quyền cần hạn chế |
|---|---|---|
| Developer ứng dụng | Đề xuất/triển khai Deployment tuân thủ baseline trong namespace của đội | Tự add NET_ADMIN/privileged/hostNetwork |
| Network platform operator | Quản lý CNI policy, node agents và routing theo scope | Đọc mọi application secret ngoài nhu cầu |
| Security policy owner | Chỉnh admission/PSA, exception review và audit | Gắn exception không có owner/expiry |
| SRE | Read logs/debug theo ticket, restart/rollback được duyệt | Permanent cluster-admin cho mọi người |
| CI/CD service account | Apply chính xác manifests đã kiểm tra | Wildcard RBAC và sửa namespace admission labels |
| Break-glass admin | Quyền ngắn hạn khi incident, có audit | Bỏ mọi policy mà không có hậu kiểm |

**Kubernetes RBAC phân quyền theo API verbs/resources**, không trực tiếp kiểm tra “NET_ADMIN có hợp lệ cho service này không”. Quy tắc nội dung Pod spec cần **PSA hoặc policy engine/admission webhook**.

### 20.3. Quản lý ngoại lệ

Một ngoại lệ legitimate như CNI DaemonSet cần:
1. Owner và chức năng cụ thể.
2. Capability chính xác và phạm vi namespace/node.
3. Lý do không thể dùng giải pháp ít quyền hơn.
4. Image provenance/signing và runtime restrictions.
5. Admission exemptions hẹp.
6. Monitoring/audit và thời hạn review.
7. Negative tests chứng minh business workloads không nhận quyền này.
8. Quy trình rotate/replace nếu agent hoặc credential bị compromise.

## 21. Policy-as-code: phát hiện NET_ADMIN và privileged trước deploy

**Policy-as-code** cho phép pipeline hoặc admission kiểm tra các trường như capabilities.add, privileged, hostNetwork và seccomp. Các công cụ phổ biến có thể dùng CEL admission policies, Gatekeeper hoặc Kyverno tùy phiên bản và tổ chức. Không dùng một bản YAML không tương thích version rồi giả định có enforce.

### 21.1. Pseudopolicy để review

~~~yaml
# Pseudopolicy logic; KHÔNG phải manifest ValidatingAdmissionPolicy/Kyverno.
applies_to:
  namespaces: ["app-*", "orders-prod", "payments-prod"]
checks:
  all_container_types:
    - disallow_privileged: true
    - require_drop_capabilities: ["ALL"]
    - disallow_added_capabilities_except: ["NET_BIND_SERVICE"]
    - require_allow_privilege_escalation_false: true
    - require_seccomp: ["RuntimeDefault", "Localhost"]
    - require_non_root: true
  pod:
    - disallow_host_network: true
    - disallow_host_pid: true
    - disallow_host_ipc: true
exceptions:
  process: "security-reviewed"
  required: ["owner", "ticket", "expiry", "node-scope", "audit"]
  no_wildcard_exemptions: true
~~~

Để biến pseudopolicy thành enforcement thật phải:
- Chọn engine/schema **đúng Kubernetes version**.
- Bao phủ **containers, initContainers, ephemeralContainers** và cấu hình Pod-level.
- Kiểm tra cả field bị omit/null và inheritance/overrides.
- Thiết kế exemptions cho system DaemonSets có scope tối thiểu.
- Test cả create/update/debug subresources.
- Kiểm tra warning/audit và admission failure mode.
- Đánh giá tác động đến chart operators và managed add-ons.

### 21.2. Chính sách có thể bị làm yếu thế nào?

- Chỉ kiểm tra containers[] và bỏ qua initContainers[].
- Chỉ kiểm tra Deployment nhưng bỏ Pods/Jobs/DaemonSets trực tiếp.
- Chỉ search NET_ADMIN string, bỏ privileged/hostNetwork.
- Exempt cả namespace mà developer có quyền tạo Pods.
- Không bảo vệ quyền sửa namespace labels/admission policy.
- Cho user dùng một API path/RuntimeClass khác không thuộc kiểm soát.
- Admission webhook mất kết nối và cấu hình fail-open trái policy.
- Không kiểm tra các workload/Pods còn chạy từ trước khi policy được bật.

**Admission là một điểm kiểm soát có blast radius lớn**. Quyết định fail-open/fail-closed, HA của webhook, metrics và rollback cần được thiết kế giống các thành phần security-critical khác.

## 22. Threat modeling: một Pod bị chiếm có thể làm gì?

Mô hình đe dọa tốt bắt đầu từ tài sản, mức quyền hiện có, giới hạn namespace, đường mạng và khả năng attacker. Không giả định mọi Pod compromise đều có root/NET_ADMIN/host access.

### 22.1. Tài sản

- API/DB/Secrets và workload identities.
- Pod network namespace, sidecar redirects, TLS/mTLS keys.
- Node networking interfaces/routing/CNI datapath.
- Cluster control plane và Kubernetes API.
- Cloud metadata/IAM credentials.
- DNS resolver, shared services và egress gateway.
- Flow logs, audit logs và IDS/IPS telemetry.

### 22.2. Các kịch bản

| Khả năng ban đầu | Điều đáng lo | Kiểm soát giảm thiểu |
|---|---|---|
| App non-root/drop ALL bị chiếm | Gọi các đích mạng đã allow, khai thác API permissions | NetworkPolicy, mTLS, authZ, least-privilege token |
| App có NET_RAW | Raw packet operations trong giới hạn namespace | Drop NET_RAW khi không cần, seccomp, CNI |
| App có NET_ADMIN | Sửa network settings/routes/redirect trong phạm vi được cấp | Remove capability, dedicated helper, admission |
| Pod dùng hostNetwork | Tương tác nhiều hơn với host networking | Restrict hostNetwork, node firewall, dedicated agents |
| Privileged Pod với host mounts | Mở rộng bề mặt tương tác host/kernel | Deny privileged, restrict hostPath/RuntimeClass |
| CI token có thể patch Pod spec | Tạo cấu hình thêm NET_ADMIN/privileged | RBAC + PSA/admission + approval |
| CNI/network agent bị chiếm | Có khả năng tác động datapath/telemetry diện rộng | Secure supply chain, node scope, audit/HA |
| Shared sidecar/proxy bị chiếm | Can thiệp localhost/egress identity và traffic | Separate trust boundaries, mTLS, per-container hardening |

### 22.3. Kiểm tra các giả định thay vì phỏng đoán

Các câu hỏi:
- Container thực sự effective NET_ADMIN/NET_RAW hay chỉ image chứa công cụ mạng?
- Namespace của process là Pod hay host?
- Có privileged mode, hostPath hoặc raw node access không?
- CNI enforcement diễn ra tại veth/host/eBPF/other hook nào?
- App có thể tạo direct connection ngoài service mesh gateway không?
- Có identity/cert/token nào cho phép đọc dữ liệu dù mạng bị giới hạn?
- Ai có quyền đổi Deployment/Pod/namespace labels?
- Logs có phân biệt attempted vs successful network operations không?

**Đừng dựa trên “không mở NodePort” để kết luận runtime không có quyền mạng nguy hiểm**. Một Pod có thể không public nhưng vẫn có egress/internal reachability và đặc quyền kernel.

## 23. Node-level networking agents và exception boundary

CNI, kube-proxy, eBPF security sensors và một số network controllers thường chạy thành **hệ thống nền tảng** với quyền cao hoặc host networking vì phải quản lý datapath cho nhiều Pods. Đây là tình huống hợp lệ nhưng cần tách khỏi app.

### 23.1. Nguyên tắc quản trị node agents

- Chạy trong **namespace hệ thống** có quyền create/patch giới hạn.
- Sử dụng **DaemonSet hoặc cơ chế managed agent** được kiểm toán.
- Review hostNetwork, privileged, capabilities và hostPath theo capability thực cần.
- Dùng admission exemption/allowlist **đúng service account/image** khi engine hỗ trợ.
- Giới hạn node selectors/taints để agent chỉ chạy nơi phù hợp.
- Theo dõi CNI/agent health, kernel compatibility, eBPF map usage, route drift.
- Có image digest/pinning, provenance/SBOM và quy trình update/rollback.
- Bảo vệ credentials và API RBAC của agent; không tự cấp cluster-admin khi không cần.
- Có incident plan vì agent bị lỗi có thể làm nhiều Pods mất mạng.

### 23.2. Không copy privileged DaemonSet pattern sang app

Một workload orders-api không cần NET_ADMIN chỉ vì network plugin của cluster dùng NET_ADMIN. Nhu cầu của **node dataplane manager** khác hoàn toàn nhu cầu **business request handler**.

### 23.3. Ranh giới giữa kernel networking và user-space proxy

Một CNI có thể thực thi policy ở host-level eBPF hooks trong khi service mesh thực thi policy trong sidecar process hoặc ambient gateway. Quyền ở từng điểm khác nhau. Khi thiết kế:
- Mô tả **traffic path** thực tế.
- Xác định thành phần nào cần đặc quyền kernel.
- Xác định thành phần nào chỉ cần TCP proxy và mTLS identity.
- Hạn chế direct bypass và network namespace modification.
- Test trong những kịch bản app compromised/agent restarted/failover.

## 24. Kiểm tra cấu hình Pod và capabilities theo cách chỉ đọc

Trong lab được cấp quyền, bắt đầu bằng **cấu hình mong muốn trong Kubernetes API** rồi so với **capability sets của process** và **network datapath**. Tránh nhảy thẳng sang sửa iptables, route, sysctls hoặc privileged debug trên node.

### 24.1. Đọc Pod spec và namespace labels

~~~bash
# Liệt kê Pods trong namespace có quyền
kubectl get pods -n orders-prod -o wide

# Đọc mô tả một Pod được phép kiểm tra
kubectl describe pod orders-api-lab-0 -n orders-prod

# Xem YAML spec để xác nhận từng container securityContext
kubectl get pod orders-api-lab-0 -n orders-prod -o yaml

# Xem labels liên quan Pod Security Admission
kubectl get namespace orders-prod --show-labels
~~~

**Pod name là placeholder.** Output có thể chứa private IP, image references, environment metadata hoặc những chi tiết cần giữ nội bộ. Không xuất bản raw YAML/logs nếu chưa redaction. **Đọc spec không chứng minh runtime thực thi đủ mọi controls**.

### 24.2. Xem capability sets của một process

Nếu container chứa công cụ đọc file, có thể xem status của process PID 1:

~~~bash
# Chỉ đọc; PID 1 là process theo PID namespace của container
kubectl exec -n orders-prod orders-api-lab-0 -c app -- \
  cat /proc/1/status
~~~

Trong output, quan sát:
- **CapInh**
- **CapPrm**
- **CapEff**
- **CapBnd**
- **CapAmb**
- **NoNewPrivs** nếu có.

Các giá trị Cap* thường ở dạng bitmask hệ thập lục phân. Công cụ như **capsh --decode** có thể giải mã nếu được cài và cho phép. Không nên chạy decode rồi **suy rằng toàn bộ Pod** có các quyền của một process: init container, sidecar và process con có thể khác capability sets.

### 24.3. Đọc routes và interfaces, không thay đổi

~~~bash
# Chỉ thực hiện nếu Pod có các utility này
kubectl exec -n orders-prod orders-api-lab-0 -c app -- \
  ip -br link show

kubectl exec -n orders-prod orders-api-lab-0 -c app -- \
  ip route show
~~~

Lệnh không sửa trạng thái. Tuy nhiên **Pod route table không cho biết toàn bộ CNI/node cloud routing**, và không đủ để kết luận traffic có bypass policy hay không. Chỉ quan sát những tài sản được cấp quyền.

### 24.4. Kiểm tra quyền có thể tạo Pod đặc quyền

~~~bash
# Kiểm tra quyền hiện tại, không tạo đối tượng
kubectl auth can-i create pods -n orders-prod
kubectl auth can-i patch deployments -n orders-prod
kubectl auth can-i update pods/ephemeralcontainers -n orders-prod
kubectl auth can-i update namespaces
~~~

Kết quả **yes** cho một verb/resource không tự có nghĩa admission cho phép privileged/NET_ADMIN; ngược lại **no** trong một context không loại trừ quyền thông qua credentials khác. Việc cấp capability đặc biệt cần qua **RBAC + admission + policy review**.

### 24.5. Đọc NetworkPolicy nếu cần đối chiếu

~~~bash
kubectl get networkpolicies -n orders-prod
kubectl describe networkpolicy default-deny-egress -n orders-prod
~~~

Không kết luận policy có hiệu lực chỉ vì object tồn tại: **CNI phải thực thi**, và nhiều allow policies có thể hợp lại. Kết quả này nên được ghép với CNI flow logs và negative connectivity test trong lab.

## 25. Ví dụ đối chiếu: Deployment hardening và NetworkPolicy

Bảo vệ mạng của một Orders API nên dùng **hai lớp riêng**: securityContext giới hạn quyền process; NetworkPolicy giới hạn kết nối. Một workload drop ALL vẫn có thể tạo TCP connections đến đích được định tuyến nếu NetworkPolicy/firewall cho phép.

### 25.1. Default-deny egress theo namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: orders-prod
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Với CNI hỗ trợ và khi không có allow policy khác, object này giúp cô lập egress của Pods trong namespace. Nó **không thu hồi CAP_NET_ADMIN** đã được cấp và không kiểm soát node image pulls.

### 25.2. Allowlist DNS có điều kiện

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-allow-dns
  namespace: orders-prod
spec:
  podSelector:
    matchLabels:
      app: orders-api
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

Các labels và đường DNS **chỉ mang tính ví dụ**; NodeLocal DNSCache, DNS proxy hoặc CNI NAT semantics có thể cần chính sách khác. NetworkPolicy này **không bảo đảm FQDN authorization** cho endpoint ra Internet; nó chỉ cho traffic tới đúng DNS Pods được chọn nếu môi trường khớp.

### 25.3. Độ tin cậy của 2 lớp

Với cùng một Orders Pod:

| Biện pháp | Quyền thao tác kernel | Quyền kết nối |
|---|---|---|
| drop ALL | Giảm các special capabilities | Không tự chặn egress |
| default-deny NetworkPolicy | Không thay capability sets | Có thể cô lập egress khi CNI thực thi |
| DNS allow rule | Không cấp NET_RAW hoặc NET_ADMIN | Cho truy vấn DNS tới resolver được chọn |
| mTLS + RBAC app | Không đổi route kernel | Xác thực service và giới hạn hành động nghiệp vụ |

**SecurityContext và NetworkPolicy đều cần**. Một lớp không sửa lỗi cấu hình của lớp kia.

## 26. Kiểm soát sidecar traffic và metadata endpoint

Một service mesh có thể dùng sidecar/ambient datapath để thực hiện mTLS và observability; một cloud cluster có thể có metadata/identity endpoint. Cả hai liên quan đến quyết định **nơi nào được phép có quyền mạng cao**.

### 26.1. Sidecar

Nếu mesh yêu cầu network redirect:
- Ưu tiên cơ chế **CNI-managed setup** được vendor hỗ trợ nếu tránh phải cấp NET_ADMIN cho application Pod.
- Nếu dùng helper có NET_ADMIN, cần namespace/role/owner/expiry rõ, đảm bảo app container vẫn drop ALL.
- Không coi mesh mTLS là tự động chống thay đổi route trong Pod network namespace.
- Bảo vệ localhost admin/status ports của sidecar.
- Không cho app Pod có hostNetwork chỉ để thuận tiện với mesh.
- Kiểm tra traffic bypass, đặc biệt **IPv6, UDP, non-HTTP** và direct socket paths theo sản phẩm.
- Theo dõi phiên bản sidecar, iptables/nftables mode, CNI compatibility và policy drift.

### 26.2. Cloud metadata và workload identity

Cấp **CAP_NET_ADMIN** không tự cho quyền lấy cloud credentials. Nhưng network reachability tới metadata endpoint, service-account mappings và IAM policy có thể tạo rủi ro khi process bị compromise.

Phối hợp:
- Workload IAM tối thiểu.
- Kiểm soát node/Pod metadata access theo provider.
- Không mount shared cloud credentials vào Pod không cần.
- SSRF protections tại ứng dụng.
- Egress policy tới metadata/private management.
- Audit cloud control plane và network attempts.
- Hạn chế quyền CAP_NET_ADMIN/NET_RAW/SYS_ADMIN không cần thiết.

**Không chặn metadata thiếu đánh giá** nếu workload identity phụ thuộc đường này; xác định target nào thật sự cần và chọn kiến trúc ít quyền theo capability nhà cung cấp.

## 27. Ma trận kiểm thử Pod security và network capability

Các tests dưới đây là **kế hoạch nghiệm thu**, không phải lời khẳng định đã thực thi. Với những kịch bản liên quan privileged/hostNetwork, chỉ thực hiện tại **lab được cấp phép và cô lập**, theo admission/owner; không thử sửa firewall/route của node thật. Ghi **cluster version, runtime, CNI, node OS/kernel, namespace, workload manifest, expected/actual result và evidence**.

| ID | Kịch bản | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | Pod app có drop ALL | Capability sets phản ánh hardening thực tế | Spec và /proc status |
| P02 | App không yêu cầu NET_ADMIN | Admission/policy không add NET_ADMIN | Pod spec + policy result |
| P03 | App không yêu cầu NET_RAW | Không có raw-network privilege ngoài dự kiến | CapEff/CapBnd evidence |
| P04 | App nghe TCP/8080 non-root | Chạy được không cần NET_BIND_SERVICE | App listener + spec |
| P05 | Service public port 443 → targetPort 8443 | Không cần quyền low-port trong Pod | Service/Ingress mapping |
| P06 | App thử bind privileged port trong lab | Hành vi theo threshold/capabilities được xác minh | Kernel config + app logs |
| P07 | NET_BIND_SERVICE exception hẹp | Chỉ capability được phê duyệt được add | Manifest + admission |
| P08 | Init container thiếu drop ALL trong Restricted namespace | Bị phát hiện/từ chối theo policy | PSA admission |
| P09 | Sidecar thiếu drop ALL trong Restricted namespace | Bị phát hiện/từ chối | Admission test |
| P10 | Ephemeral debug container vi phạm policy | Bị kiểm soát theo scope/cluster version | RBAC/admission logs |
| P11 | Privileged Pod trong Restricted namespace | Không được admit | Rejected manifest evidence |
| P12 | hostNetwork Pod trong Restricted namespace | Không được admit | Rejected manifest evidence |
| P13 | hostPID/hostIPC ngoài policy | Không được admit | Admission logs |
| P14 | HostPath trên app Pod bị cấm theo Restricted | Bị từ chối | Admission result |
| P15 | Baseline Pod cố add NET_ADMIN | Bị hạn chế theo Baseline controls | PSA/audit |
| P16 | Restricted Pod drop ALL và chỉ add NET_BIND_SERVICE | Được xét theo policy | Admission + runtime |
| P17 | Privileged system agent hợp lệ | Chỉ thuộc exemption hẹp, có owner | Exception inventory |
| P18 | Developer tự gắn app vào exemption namespace | Bị RBAC/admission chặn | RBAC/audit |
| P19 | Pod security labels bị thay trái quyền | Không làm yếu enforcement | Namespace audit |
| P20 | Admission webhook/PSS unavailable trong lab | Fail mode theo chính sách đã phê duyệt | Admission monitoring |
| P21 | RuntimeDefault seccomp được áp | Syscall filter theo runtime profile | Runtime/spec evidence |
| P22 | Localhost seccomp profile thiếu trên một node | Rollout bị phát hiện/an toàn theo policy | Node and admission events |
| P23 | App read-only rootfs | Vẫn chạy với writable mounts được duyệt | Filesystem/app metrics |
| P24 | Container non-root với NET_RAW ngoài ý định | Policy nhận ra capability add dù UID khác root | Pod spec/CI |
| P25 | App và sidecar chia sẻ Pod netns | Cùng routes/localhost theo mô hình | Namespace metadata |
| P26 | CNI enforcement với Pod drop ALL | Egress negative flow vẫn bị chặn | CNI verdict |
| P27 | Pod có NET_ADMIN nhưng CNI policy từ host | Không suy bypass; hành vi được test đúng scope | CNI/datapath evidence |
| P28 | Workload dùng hostNetwork | Được quản lý như exception đặc biệt | Admission/host audit |
| P29 | Node networking agent restart | Không thay app securityContext | Workload spec + CNI health |
| P30 | Pod cùng namespace nhưng khác labels | Admission/policy đúng từng loại container | Label/policy audit |
| P31 | Kubernetes RBAC cho update ephemeralcontainers | Chỉ operator có quyền được cấp | kubectl auth can-i + audit |
| P32 | ServiceAccount không cần Kubernetes API | Không có quyền và token mount không cần | Pod spec/RBAC |
| P33 | Kernel sysctl thay theo version trong lab | Behavior được xác minh, không thay node toàn cục | Config/namespace metadata |
| P34 | IPv6 traffic của Pod | CNI/firewall policy đúng IPv6 | IPv6 flows |
| P35 | Sidecar direct bypass khi không dùng NET_ADMIN | Cấu hình CNI/proxy và egress control vẫn hiệu lực | Mesh/CNI logs |
| P36 | DNS over HTTPS tới đích không được phép | Egress policy/gateway chặn theo thiết kế | Proxy/firewall logs |
| P37 | Image pulls trên node | Có node egress phù hợp, không lệ thuộc Pod policy | Runtime/node logs |
| P38 | Autoscaling thêm Pod trên node mới | PSS, capabilities và CNI parity | Deployment + new Pod evidence |
| P39 | Failover sang vùng/cluster dự phòng | Không nới NET_ADMIN/privileged/hostNetwork | Policy drift tests |
| P40 | Monitoring/log pipeline mất dữ liệu | Có cảnh báo thiếu telemetry | Collector/pipeline health |

**Không đánh dấu PASSED nếu chưa có thực nghiệm.** Với test đòi capability đặc quyền, có thể kiểm chứng *admission rejection* hoặc *cấu hình process* thay vì thực thi tác vụ sửa mạng nguy hiểm. Các negative tests phải giới hạn trong lab, với rollback và người phê duyệt.

## 28. Troubleshooting: lỗi do capability, route hay authorization?

### 28.1. Ứng dụng không bind được port 80/443

**Có thể do:** process non-root thiếu NET_BIND_SERVICE, kernel unprivileged port threshold khác, hostPort/hostNetwork collision, runtime security policy hoặc app chưa mở listener.

**Kiểm tra:** actual container port, UID, CapEff, sysctl network namespace, container logs và Service targetPort. **Ưu tiên chuyển app sang cổng 8080/8443**, không bật privileged hay NET_ADMIN để “sửa” vấn đề này.

### 28.2. Ping không chạy sau drop NET_RAW

**Có thể do:** công cụ ping yêu cầu raw socket, kernel ping_group_range khác, ICMP bị chặn, capability/runtime mismatch.

**Kiểm tra:** process capability sets và đường mạng thực tế; dùng phép kiểm tra TCP/TLS phù hợp với ứng dụng thay vì lấy ping làm điều kiện duy nhất. **Không add NET_ADMIN** để sửa ping.

### 28.3. Sidecar báo lỗi cấu hình redirect

**Có thể do:** mesh init/helper thiếu NET_ADMIN theo kiến trúc cũ, CNI redirect chưa bật, sidecar pod lifecycle khác, policy Restricted mới chặn init container.

**Kiểm tra:** mesh deployment mode, admission event, securityContext của đúng container, node CNI status và vendor guidance. Nếu có thể, chuyển setup sang CNI-managed path; không cấp NET_ADMIN cho main app chỉ để sidecar chạy.

### 28.4. NetworkPolicy chặn traffic nhưng process có NET_ADMIN

**Giải thích:** quyền sửa network settings trong namespace không đồng nghĩa có quyền đi qua datapath CNI/host firewall. Kiểm tra interface/routes chỉ đọc, flow verdict và actual CNI hook. Không kết luận khả năng bypass hoặc lỗi triển khai chỉ từ CapEff.

### 28.5. Pod không tạo được sau khi bật PSS Restricted

**Có thể do:** thiếu drop ALL trong init/sidecar, privileged flag, runAsNonRoot chưa đúng, allowPrivilegeEscalation, seccomp missing, hostNetwork hoặc hostPath.

**Kiểm tra:** admission warning/audit/rejection nêu trường vi phạm. Sửa **container cụ thể** và test image, không bỏ enforce khỏi toàn namespace nếu chỉ một workload lỗi.

### 28.6. App drop ALL nhưng vẫn gọi external API

**Giải thích:** TCP/UDP client operations thông thường không cần NET_ADMIN/NET_RAW trong phần lớn trường hợp. Cần **egress NetworkPolicy, gateway/firewall, DNS và app authentication** để giới hạn destinations; drop ALL không phải công tắc tắt Internet.

### 28.7. System DaemonSet cần privileged nhưng admission từ chối

**Có thể do:** namespace bị áp Restricted, exception quá hẹp, image/runtimeClass hoặc policy engine khác từ chối.

**Kiểm tra:** security owner, DaemonSet manifest, exact capabilities needed, PSA config và admission logs. Tạo **scope exception được phê duyệt** thay vì hạ profile cho mọi ứng dụng.

### 28.8. Hai nodes chạy cùng Pod spec nhưng kết quả khác

**Có thể do:** kernel/runtime versions, seccomp default profile, CNI health, user namespace support, AppArmor/SELinux policies hoặc Pod Security Admission config drift.

**Kiểm tra:** node/runtime inventories và policy-version pinning; thử trên nhiều node pools. Không gắn nhãn capabilities “không ổn định” khi nguyên nhân là runtime khác nhau.

### 28.9. Network sniffing tool chạy trong debug nhưng không thấy traffic cần tìm

**Có thể do:** thiếu NET_RAW hoặc NET_ADMIN, sai network namespace/interface, traffic đi qua host-level CNI/overlay, TLS encryption, thiếu sensor placement.

**Kiểm tra:** tool scope, identity, quyền đã cấp và điểm đặt sensor. Không yêu cầu privileged hostNetwork trên production chỉ để “thấy tất cả”; dùng telemetry tại đúng data plane.

### 28.10. Cloud metadata access thất bại sau hardening

**Có thể do:** egress policy, IAM/workload identity setup, provider metadata protection, DNS/route, hoặc ứng dụng dùng node credentials không còn được phép.

**Kiểm tra:** thiết kế identity hợp lệ và đường cần thiết. Không mở toàn Internet hay cấp NET_ADMIN cho app; sửa **workload identity + routing policy** theo nhu cầu thực.

## 29. Các tình huống phân tích và đáp án gợi ý

### Tình huống A — Business API có NET_ADMIN “cho tiện”

Một Deployment chạy REST API được cấp NET_ADMIN vì đội phát triển từng cần sửa route khi debug.

**Phân tích:** không có nhu cầu thường xuyên. Bỏ capability ở app container, dùng Pod spec drop ALL, kết hợp debug tooling tạm thời với scope/approval và CNI/NetworkPolicy. Không giữ quyền kernel rộng trong production.

### Tình huống B — App dùng cổng 80 nên được privileged

Người vận hành bật privileged: true để non-root app mở cổng 80.

**Phân tích:** privileged quá rộng. Dùng containerPort 8080 và Service/Ingress 80/443, hoặc NET_BIND_SERVICE ngoại lệ hẹp khi thực sự cần và kernel threshold phù hợp.

### Tình huống C — Đã drop ALL nhưng vẫn kết nối Internet

Đội bảo mật cho rằng drop ALL phải chặn TCP outbound, nhưng app vẫn truy cập bên ngoài.

**Phân tích:** Linux capability không phải egress firewall. Dùng NetworkPolicy/CNI/cloud firewall/egress proxy với allowlist, kết hợp application auth.

### Tình huống D — Pod có hai container cùng localhost

Application container không có capability đặc biệt nhưng gọi được local proxy admin port của sidecar trên localhost.

**Phân tích:** containers cùng Pod chia sẻ network namespace/loopback. Phải bảo vệ proxy admin API bằng authorization/port binding, không coi localhost chỉ accessible từ sidecar.

### Tình huống E — NET_RAW bị tước nhưng ping vẫn chạy

Kiểm tra ping trả thành công dù pod drop NET_RAW.

**Phân tích:** một số Linux/ping versions sử dụng ICMP datagram socket và ping_group_range. Dùng process capability sets để xác minh; ping success không chứng minh privilege.

### Tình huống F — NET_ADMIN trong Pod thường

Một Pod có NET_ADMIN nhưng không dùng hostNetwork. Team cho rằng nó sửa được route toàn node.

**Phân tích:** CAP_NET_ADMIN chịu scope network namespace/user namespace. Không tự chứng minh quyền sửa node route. Vẫn là quyền nhạy cảm với các containers cùng Pod và cấu hình network, nên phải bỏ nếu không cần.

### Tình huống G — NET_ADMIN cộng hostNetwork

Một workload không phải agent nền tảng dùng hostNetwork và được NET_ADMIN.

**Phân tích:** quyền ảnh hưởng host networking có thể lớn; đây là cấu hình rủi ro cao. Chặn theo PSS/admission, chỉ ngoại lệ cho trusted node agents có owner và giới hạn quyền.

### Tình huống H — Init helper cấu hình redirect cho sidecar

Main application drop ALL; init container vẫn add NET_ADMIN theo mesh deployment cũ.

**Phân tích:** phải review cả init container và shared network namespace. Ưu tiên CNI-managed redirection nếu có và hợp topology; ngoại lệ cần được ghi nhận/hạn chế, không coi main app policy đủ.

### Tình huống I — Restricted namespace chỉ chặn main container

Một custom admission policy chỉ kiểm tra spec.containers nhưng bỏ spec.initContainers.

**Phân tích:** coverage không đầy đủ. Cần kiểm tra cả regular/init/ephemeral containers và Pod-level settings, test admission trên các loại workload và subresources.

### Tình huống J — App non-root vẫn có quyền NET_RAW

Một image chạy UID 10001 nhưng Pod spec cộng NET_RAW.

**Phân tích:** non-root không tự tước capability được cấp. Cần drop ALL và chỉ add ngoại lệ được duyệt; xác minh CapEff khi runtime.

### Tình huống K — PSS Baseline được hiểu là “drop ALL”

Một Pod đạt Baseline nhưng vẫn có runtime default capabilities không cần thiết.

**Phân tích:** Baseline không đồng nghĩa Restricted; Baseline giới hạn additions nhưng không đòi drop ALL như Restricted. Đặt Restricted cho app namespace khi phù hợp và kiểm tra process capabilities.

### Tình huống L — CNI chạy được nhưng app không start sau bật Restricted

Cluster CNI DaemonSet cần host networking; Pod Orders bị Restricted và không chạy do securityContext thiếu.

**Phân tích:** app phải sửa manifest đúng chuẩn; network agent dùng exception riêng có kiểm soát. Không hạ bảo mật toàn namespace app để giữ agent.

### Tình huống M — Service mesh mTLS được xem như thay NET_ADMIN controls

App có NET_ADMIN vì có mesh mTLS, đội phát triển nghĩ traffic luôn đi qua sidecar.

**Phân tích:** mTLS là layer identity/transport, không tự bảo vệ redirect logic. Đưa redirect vào controlled CNI path, drop NET_ADMIN và test bypass trên data plane thật.

### Tình huống N — Admission chỉ bảo vệ Deployments

Người dùng có quyền create Pod trực tiếp hoặc patch ephemeral containers.

**Phân tích:** admission policy cần bao phủ các API paths và workloads tương ứng; RBAC phải hạn chế create/patch subresources. Không chỉ lint Helm charts rồi kết luận đã enforce.

### Tình huống O — Debug container bật hostNetwork vì không thấy flow

SRE muốn bật privileged + hostNetwork trên production Pod để xem traffic ngoài Pod namespace.

**Phân tích:** mở đặc quyền không phải lựa chọn mặc định. Dùng network observability từ CNI/node agent đã được quản trị hoặc lab reproduction; nếu ngoại lệ thật cần, phải có approval, timebox, audit và kế hoạch thu hồi.

### Tình huống P — Cùng YAML nhưng khác kết quả ở hai nodes

Một node kernel/runtime cũ và node mới có default seccomp/privileged port threshold khác nhau.

**Phân tích:** cần kiểm tra node runtime, kernel capability behavior, seccomp profile và sysctl settings. Pin/test policy và nâng cấp theo kế hoạch; không giải quyết bằng privileged blanket.

### Tình huống Q — App không cần Kubernetes API nhưng có token mount

Một Pod workload chỉ gọi database vẫn có service account token rộng.

**Phân tích:** dùng RBAC/identity tối thiểu, vô hiệu automount nếu không cần; hạn chế Pod egress tới API server và quản lý cloud workload identity riêng. Capabilities không thay quyền API.

### Tình huống R — Failover làm Pod security yếu đi

Primary cluster enforce Restricted; DR cluster chỉ enforce Baseline và có NET_ADMIN exceptions rộng.

**Phân tích:** cần security parity trong IaC/PSA labels/admission policies, test cả authorized và denied Pods khi failover. HTTP 200 sau DR không chứng minh bảo mật tương đương.

## 30. Runbook khi phát hiện Pod có network capability bất thường

### Giai đoạn A — Xác minh và phân loại

1. Xác định **cluster, namespace, Pod UID, owner, node và deployment revision**.
2. Đọc **spec + các securityContext** của regular/init/ephemeral containers.
3. Xác minh actual capability sets ở process được phép quan sát.
4. Kiểm tra **hostNetwork/hostPID/hostIPC, privileged, hostPath, seccomp, user namespace**.
5. Xác định mục đích hợp lệ: application, service mesh init, CNI node agent hay debug.
6. Đối chiếu PSA/admission policy, Kubernetes RBAC, change ticket và audit.
7. Đối chiếu CNI NetworkPolicy, egress gateway, firewall, service identity và logs.
8. Xem có route/interface changes, unusual flows hoặc traffic tới metadata/management không.
9. Bảo toàn evidence có kiểm soát và loại bỏ secret khỏi báo cáo.

### Giai đoạn B — Giảm tác động

- Với **business Pod NET_ADMIN/NET_RAW không cần**: chuẩn bị manifest least privilege và rollout/rollback có kiểm soát.
- Với **hostNetwork/privileged trái policy**: phối hợp security/SRE khoanh vùng, ngăn thêm Pod cấu hình tương tự qua admission, tránh xóa bừa làm đứt hạ tầng.
- Với **node CNI agent**: xác nhận owner, image integrity, quyền cần thiết; không tắt CNI/agent toàn cluster trước khi có phương án traffic recovery.
- Với **credential leakage**: đánh giá/rotate/revoke token, cloud IAM và service account permissions.
- Với **lateral movement/egress abuse**: tăng scope firewall/CNI isolation có chọn lọc theo incident policy và xác minh legitimate traffic.
- Với **policy drift**: khôi phục policy-as-code version đã được phê duyệt, sửa quyền sửa namespace labels hoặc admission exceptions.

### Giai đoạn C — Phục hồi

1. Mở các đường mạng nghiệp vụ cần thiết bằng NetworkPolicy, không mở quyền kernel không cần.
2. Deploy phiên bản Pod có securityContext đúng ở lab/canary.
3. Kiểm tra application health, startup, readiness và user-facing SLO.
4. Kiểm tra process capability sets và admission decision.
5. Chạy negative tests cho privileged/NET_ADMIN/hostNetwork ngoài scope.
6. Xác minh CNI/mesh/firewall path và telemetry không bị bypass.
7. Kiểm tra DNS, cloud IAM, TLS và authorized API calls.
8. Đảm bảo DR/failover cluster giữ profile tương đương.

### Giai đoạn D — Hậu kiểm

Báo cáo root cause:
- Ai đã cấp capability và vì sao?
- Capability có thực sự cần hay do debug convenience?
- Có Pod type/subresource nào policy chưa bao phủ?
- PSS Baseline/Restricted hoặc exemption nào bị cấu hình sai?
- Network datapath/sensor có blind spot không?
- Admission, RBAC hoặc CI test nào thiếu?
- Có tác động tới dữ liệu, availability hoặc node kernel không?
- Ai chịu trách nhiệm sửa, hạn hoàn thành và bằng chứng hồi quy?

Đóng sự cố dựa trên **runtime privilege và network enforcement được chứng minh**, không chỉ vì Deployment đã đổi YAML.

## 31. Sai lầm thường gặp

1. **Coi Linux capability là Kubernetes permission.** Capability cho kernel process; RBAC cho Kubernetes API.
2. **Coi UID 0 đồng nghĩa có mọi capability.** Runtime có thể drop/bounding set.
3. **Coi non-root đồng nghĩa không có NET_ADMIN/NET_RAW.** Capability có thể được add.
4. **Coi NET_ADMIN tự động cho phép sửa host routing.** Namespace quyết định phạm vi.
5. **Coi NET_ADMIN vô hại trong Pod riêng.** Nó có thể làm thay đổi shared Pod networking.
6. **Cho business app NET_ADMIN để debug.** Tăng đặc quyền lâu dài.
7. **Cho privileged để bind cổng 80.** Quá rộng so với nhu cầu.
8. **Quên Service/Ingress có thể map cổng ngoài sang 8080.** Cấp NET_BIND_SERVICE không cần thiết.
9. **Không xét ip_unprivileged_port_start.** Low-port capability requirement có thể khác.
10. **Coi NET_RAW cần cho mọi ping.** ICMP datagram sockets có thể hoạt động không cần nó.
11. **Coi NET_RAW cho phép sniff toàn cluster.** Namespace, interfaces, CNI giới hạn visibility.
12. **Chạy raw packet utilities mà không có authorization.** Debug phải giới hạn scope.
13. **Coi CAP_BPF đủ thao tác mọi eBPF hooks.** Kernel/version/other caps khác nhau.
14. **Cấp SYS_ADMIN cho network agent vì “một capability”.** Đây là quyền cực rộng.
15. **Dùng hostNetwork cho web API thông thường.** Tăng blast radius, khó áp policy như Pod thường.
16. **Coi hostPort giống hostNetwork.** Cơ chế khác nhưng đều cần đánh giá exposure.
17. **Tin một Pod có network namespace riêng là có kernel riêng.** Kernel vẫn được chia sẻ.
18. **Đặt hai workload khác mức tin cậy trong cùng Pod.** Chia sẻ localhost/Pod IP.
19. **Hardening app nhưng bỏ init/sidecar.** Thành phần khác vẫn có đặc quyền.
20. **Không kiểm soát ephemeralcontainers.** Debug có thể tăng rủi ro.
21. **Coi PSS Baseline yêu cầu drop ALL.** Restricted mới có yêu cầu drop ALL tương ứng.
22. **Coi PSS Restricted thay NetworkPolicy.** Không tự giới hạn egress.
23. **Coi NetworkPolicy drop NET_ADMIN.** Nó lọc traffic, không sửa capability sets.
24. **Tin NetworkPolicy object đã được thực thi.** CNI phải hỗ trợ và enforce.
25. **Bỏ qua user namespaces/LSM/seccomp.** Rủi ro cần xét tổ hợp.
26. **Đặt allowPrivilegeEscalation false rồi coi process vô quyền.** Không thu hồi quyền đang có.
27. **Dùng seccomp Unconfined để giải quyết ngay app lỗi.** Bỏ phòng vệ không cần thiết.
28. **Bỏ qua sysctls network và node-level settings.** Có thể đổi ngưỡng quyền/đường đi.
29. **Đặt privileged CNI agent chung namespace business không kiểm soát.** Exemption quá rộng.
30. **Cho developer sửa namespace PSA labels.** Có thể làm yếu admission.
31. **Chỉ kiểm tra Deployments mà không kiểm tra Pod/Job/DaemonSet.** Bỏ đường tạo khác.
32. **Quên init/ephemeral trong policy checks.** Bypass policy content validation.
33. **Không kiểm tra admission fail mode.** Webhook outage có thể fail-open/fail-closed ngoài ý định.
34. **Cho service account cloud/K8s quyền rộng vì Pod drop ALL.** Kernel privilege khác API identity.
35. **Không bảo vệ localhost admin APIs.** Cùng Pod có thể gọi nhau.
36. **Bỏ qua CNI datapath và hostNetwork exceptions.** Kiểm thử Pod thường không đại diện node agent.
37. **Chỉ test HTTP 200, không test denied privilege.** Không biết admission có enforce.
38. **Không kiểm tra nhiều node/kernel versions.** Default seccomp/cap behavior khác.
39. **Không có owner/expiry cho quyền ngoại lệ.** Privileged trở thành mặc định không được xét lại.
40. **Coi một thay đổi securityContext là đã giải quyết incident.** Cần runtime readback và negative tests.

## 32. Checklist triển khai Pod security theo network capability

- [ ] Có inventory workloads, namespaces, owners và độ nhạy của dữ liệu.
- [ ] Xác định container nào thực sự cần capability mạng đặc biệt.
- [ ] Không cấp NET_ADMIN cho business API/worker thông thường.
- [ ] Không cấp NET_RAW nếu không có nhu cầu raw/packet socket được phê duyệt.
- [ ] Không cấp SYS_ADMIN/CAP_BPF/PERFMON cho application Pods ngoài exception.
- [ ] Có **capabilities.drop: [ALL]** cho các containers thuộc phạm vi Restricted.
- [ ] Chỉ add NET_BIND_SERVICE khi low-port requirement thực tế cần.
- [ ] Đã cân nhắc dùng containerPort trên 1024 và Service/Ingress port mapping.
- [ ] Có runAsNonRoot và UID/GID phù hợp image.
- [ ] Có allowPrivilegeEscalation: false và privileged: false.
- [ ] Có seccomp RuntimeDefault/Localhost phù hợp và thử với runtime thật.
- [ ] Xem xét AppArmor/SELinux/user namespaces khi nền tảng hỗ trợ.
- [ ] Đã kiểm tra root filesystem, writable mounts và capability file effects.
- [ ] Không dùng hostNetwork, hostPID, hostIPC, hostPath ở app thông thường.
- [ ] hostPort có owner, port range và network exposure review.
- [ ] Đã kiểm tra **init containers và sidecars**, không chỉ main app.
- [ ] Có chính sách RBAC/admission riêng cho ephemeral debug containers.
- [ ] Dùng PSA Restricted cho app namespaces nơi workload tương thích.
- [ ] Có audit/warn pilot và policy version pinning khi rollout PSA.
- [ ] Exemptions cho CNI/node agents hẹp, có owner, review và audit.
- [ ] Người deploy ứng dụng không thể tự bỏ PSA labels.
- [ ] Admission policy bao phủ Pod/Deployment/Job/DaemonSet và subresources thích hợp.
- [ ] Có network egress/ingress NetworkPolicy theo least privilege.
- [ ] Đã xác minh CNI enforcement và hostNetwork behavior theo vendor.
- [ ] Có TLS/mTLS và application authorization, không tin private IP.
- [ ] Cloud metadata/IAM và Kubernetes API tokens được cấp tối thiểu.
- [ ] Không cấp NET_ADMIN chỉ để sidecar redirect nếu CNI-managed mode khả thi.
- [ ] Có telemetry CNI/mesh/firewall và Kubernetes audit với data minimization.
- [ ] Có log/alert khi Pod mới add NET_ADMIN, NET_RAW hoặc privileged.
- [ ] Có guardrails cho network sysctls/unsafe sysctls.
- [ ] Test process CapEff/CapBnd trong lab đúng process, container và node.
- [ ] Test admission rejection cho privileged/hostNetwork/NET_ADMIN trái policy.
- [ ] Test legitimate API/DNS/metrics traffic vẫn phục vụ đúng.
- [ ] Test denied egress và lateral flows trên Pod thường.
- [ ] Có policy parity giữa clusters, node pools và DR/failover.
- [ ] Mỗi ngoại lệ có lý do, owner, expiry và rollback.
- [ ] Network incident runbook không khuyến khích sửa host firewall/route tùy tiện.
- [ ] Sau upgrade Kubernetes/CNI/runtime, thực hiện regression tests.
- [ ] Security review xem cả namespace trust boundary và quyền sửa workloads.
- [ ] Không coi một manifest tuân thủ PSS là bằng chứng đủ cho toàn bộ hệ thống.

## 33. Bảng thuật ngữ tham khảo nhanh

| Thuật ngữ | Giải thích |
|---|---|
| **Capability set** | Tập quyền kernel rời rạc của process |
| **CAP_NET_ADMIN** | Capability quản lý nhiều thao tác network stack có đặc quyền |
| **CAP_NET_RAW** | Capability liên quan raw và packet sockets |
| **CAP_NET_BIND_SERVICE** | Capability bind privileged network ports trong điều kiện kernel |
| **CAP_BPF** | Capability liên quan các thao tác BPF có đặc quyền trên kernel hỗ trợ |
| **Network namespace** | Miền cô lập interfaces, routes, sockets và nhiều network settings |
| **User namespace** | Miền ánh xạ UID/GID và phạm vi kiểm tra capability |
| **hostNetwork** | Pod dùng network namespace của node |
| **Privileged** | Chế độ runtime mở rộng mạnh quyền và truy cập host/kernel |
| **securityContext** | Cấu hình security kernel/runtime cho Pod hoặc container theo field |
| **PSS** | Pod Security Standards: Privileged, Baseline, Restricted |
| **PSA** | Pod Security Admission, áp PSS theo namespace labels/modes |
| **CNI** | Plugin/network data plane triển khai kết nối và có thể NetworkPolicy |
| **NetworkPolicy** | Kubernetes API khai báo policy ingress/egress cho Pods khi CNI hỗ trợ |
| **Seccomp** | Bộ lọc syscalls cho process |
| **AppArmor/SELinux** | Các cơ chế mandatory access control theo profile/label |
| **LSM** | Linux Security Modules framework |
| **RBAC** | Quyền API theo role/verbs/resources trong Kubernetes |
| **Admission** | Điểm kiểm soát request trước khi tài nguyên được chấp nhận |
| **Service mesh** | Lớp traffic identity/routing/telemetry thường dùng proxy hoặc datapath |
| **Egress gateway** | Điểm xử lý lưu lượng đi ra theo policy |
| **Pod UID** | Định danh instance Pod; không đồng nhất với IP có thể tái sử dụng |

## 34. Tổng kết

**Pod security liên quan đến network capability** đòi hỏi phân biệt **đặc quyền kernel của process** với **quyền kết nối qua mạng**. **NET_ADMIN** có thể tác động networking trong phạm vi namespace được cấp; **NET_RAW** liên quan raw/packet sockets; **NET_BIND_SERVICE** là ngoại lệ hẹp cho privileged ports theo cấu hình kernel. Chúng không tự chứng minh Pod có thể truy cập mọi mạng, cũng không được giả định vô hại chỉ vì Pod có IP riêng.

Đối với ứng dụng thông thường, điểm xuất phát tốt là **non-root, drop ALL capabilities, không privilege escalation, seccomp phù hợp, không privileged/hostNetwork**, kết hợp **Pod Security Standards Restricted/Admission**, RBAC và policy-as-code. Với những node CNI/observability agents thực sự cần quyền cao, sử dụng **ngoại lệ nhỏ nhất, có owner, audit và kiểm thử**. Để tạo ranh giới phòng vệ thực sự trong **SECURITY_NETWORK_SECURITY**, bổ sung **NetworkPolicy/CNI, firewall/segmentation, TLS/mTLS, workload identity, kiểm soát egress, monitoring và kiểm thử cả luồng được phép lẫn quyền bị từ chối**.

**Tiêu chí hoàn thành không phải một YAML đẹp hay một lệnh curl thành công**: cần chứng minh process có đúng capabilities tại runtime, Pod/host namespaces không mở rộng ngoài ý định, admission thực sự từ chối cấu hình nguy hiểm, và network traffic vẫn tuân thủ chính sách sau khi scale, debug, nâng cấp hoặc failover.
