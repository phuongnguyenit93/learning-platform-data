# Docker network mode và rủi ro lựa chọn: thiết kế mạng container an toàn

Trong chương **Bảo mật mạng container** thuộc module **SECURITY_NETWORK_SECURITY**, việc chọn **Docker network mode** quyết định container có network namespace riêng hay chia sẻ mạng với host hoặc container khác, gắn với mạng ảo nào, có thể trao đổi với những endpoint nào và các luồng Internet/điều khiển sẽ đi qua đâu. Đây là một quyết định **kiến trúc và bảo mật**, không đơn thuần là tùy chọn để ứng dụng “ping được” hay mở cổng thuận tiện.

Docker cung cấp những cách tổ chức mạng thường gặp như **bridge, host, none, container network namespace**, và những driver/kịch bản chuyên biệt như **macvlan, ipvlan, overlay**. Các tên này không đồng nghĩa hoàn toàn: **network mode** trong lệnh chạy container xác định cách tham gia network namespace hoặc network; **network driver** quy định cách một Docker network được triển khai. Ví dụ **bridge** vừa là driver vừa là kiểu kết nối quen thuộc, trong khi **container:ID** là chế độ chia sẻ network namespace của một container khác, không phải một driver mạng độc lập.

Lựa chọn sai có thể khiến database mở ra Internet qua port publishing, một container dùng **host network** nhìn thấy nhiều dịch vụ host hơn dự kiến, hai nhóm ứng dụng chia sẻ broadcast domain không cần thiết, hoặc traffic liên node không được bảo vệ theo giả định. Một lựa chọn khác có thể tạo đường đi vòng firewall, phá DNS service discovery, làm mất khả năng giám sát hoặc khiến ứng dụng không thể kết nối qua môi trường Docker Desktop/rootless.

**Mục tiêu học tập:**

- Phân biệt **network namespace, Docker bridge, veth, host stack, NAT, route, Docker DNS và port publishing**.
- Chọn đúng **bridge/default bridge/user-defined bridge, host, none, container, macvlan, ipvlan và overlay** theo trust boundary.
- Biết rõ kết nối **container ↔ container, host ↔ container, Internet ↔ container, container ↔ Internet** có cùng hay khác chính sách.
- Nhận diện rủi ro **lateral movement, exposed ports, Docker daemon/socket access, network escape/bypass, IPv6, DNS, overlay trust và route/firewall drift**.
- Thiết kế **Docker Compose networks**, quyền kết nối và chính sách firewall/egress, không lạm dụng network mode để thay cho authorization.
- Kiểm chứng cấu hình bằng **Docker inspect, network inspect, port list, host firewall/flow logs, kiểm tra route và positive/negative tests** trong môi trường được cấp quyền.

## 1. Mô hình mạng container: lớp nào đang bị cô lập?

Trên Docker Engine chạy Linux thông thường, container dùng **Linux network namespace** để có góc nhìn riêng về network interfaces, routing table, socket bindings và một phần trạng thái mạng khác. Hệ thống có thể dùng **virtual Ethernet pairs (veth)** nối namespace với bridge của host, đồng thời áp NAT, filtering và các chức năng mạng của Linux. Chi tiết thực thi phụ thuộc **network driver, hệ điều hành, rootless/rootful, Docker Desktop và phiên bản**.

~~~mermaid
flowchart LR
    U["Client ngoài Docker host"] --> H["Host NIC và host firewall"]
    H --> N["DNAT / published port hoặc proxy"]
    N --> B["Docker bridge / virtual fabric"]
    B --> V1["veth -> Container APP namespace"]
    B --> V2["veth -> Container DB namespace"]
    V1 --> S1["APP listening socket"]
    V2 --> S2["DB listening socket"]
    B -. "routing/NAT/forward filtering" .-> F["Host network controls"]
~~~

Sơ đồ minh họa **Linux bridge network phổ biến**, không khẳng định mọi traffic bắt buộc qua cùng một NAT/proxy process. Trong **host mode**, container chia sẻ network namespace của host và không đi qua một veth bridge riêng theo mô hình này. Trên **Docker Desktop**, Docker Engine thường nằm sau lớp VM và đường host/container có khác biệt.

### 1.1. Network namespace không phải toàn bộ sandbox

Network namespace cô lập cách container nhìn/điều khiển các interface và socket theo cấu hình. Nó **không tự cô lập**:

1. Các thư mục host được bind mount vào container.
2. Docker API/socket hoặc credential cloud được cấp cho workload.
3. Kernel mà container chia sẻ với host Linux.
4. Quyền Linux capabilities, privileged mode, device mounts và chính sách seccomp/LSM.
5. Các ứng dụng reachable qua những route và firewall rules được phép.
6. Dữ liệu qua DNS, HTTP proxy, mounted secrets và ứng dụng bên ngoài.

Một container trên mạng **none** vẫn có thể làm lộ dữ liệu bằng cách **ghi vào host-mounted path, gọi một host socket được mount hoặc sử dụng một khả năng ngoài mạng khác** nếu các quyền đó được cấp. Vì vậy, đừng dùng **network isolation** như bằng chứng hoàn chỉnh về **workload isolation**.

### 1.2. Bốn câu hỏi phải giải trước khi chọn mode

- **Ingress:** ai được kết nối từ ngoài host? Có cần public endpoint, internal reverse proxy hay chỉ giao tiếp cùng host?
- **East–west:** container được nói chuyện với những container/service nào? Dùng network identity hoặc authentication gì?
- **Egress:** container có cần DNS, Internet, registry, object storage hay chỉ database nội bộ?
- **Control plane:** ai có thể chạy container, tạo network, thay network mode, publish ports hoặc sửa rules? Quyền đó có thể phá mọi giới hạn data plane.

## 2. Bảng so sánh nhanh các lựa chọn mạng

| Mode/driver | Không gian mạng của container | Điểm mạnh | Rủi ro cần xét | Phù hợp khi |
| --- | --- | --- | --- | --- |
| **bridge mặc định** | Namespace riêng, gắn bridge mặc định của Engine | Dễ bắt đầu, hỗ trợ nhiều container trên một host | Chia sẻ mạng mặc định, discovery/cách ly kém linh hoạt, nguy cơ dùng chung môi trường | Lab ngắn, workload đơn giản có kiểm soát |
| **user-defined bridge** | Namespace riêng trên bridge do người dùng tạo | DNS theo tên, tách nhóm networks, kết nối/ngắt mạng linh hoạt | Các container **cùng network** có thể trao đổi trực tiếp theo policy; không mặc định per-port deny | Mặc định ưu tiên cho ứng dụng nhiều container cùng host |
| **host** | Dùng chung network namespace với host | Ít lớp ảo hóa mạng, một số workload đặc thù dễ dùng | Giảm network isolation, port collision, service binding, telemetry khó tách | Một số agent/thiết bị cần host networking và đã được phê duyệt |
| **none** | Namespace riêng, không cấu hình network connectivity thông thường; có loopback | Không có đường IP thông thường tới mạng khác | Không thay bảo vệ host mounts/daemon, không phù hợp service cần kết nối | Job tính toán offline, xử lý cô lập |
| **container:<id>** | Chia sẻ namespace của container khác | Sidecar dùng chung localhost/IP stack | Sidecar có thể truy cập listener nội bộ của peer; khó áp route/port riêng | Sidecar đồng mức tin cậy, được thiết kế cùng lifecycle |
| **macvlan** | Namespace riêng; container xuất hiện trực tiếp trên LAN L2 theo mô hình driver | Có IP/MAC riêng trên mạng vật lý | Bỏ qua giả định bridge NAT/host firewall; L2 exposure, switch/VLAN, MAC limits | Thiết bị/ứng dụng legacy phải hiện diện trên LAN |
| **ipvlan** | Namespace riêng; dùng mô hình L2/L3 của ipvlan | Có thể giảm nhu cầu nhiều MAC, hỗ trợ routing theo thiết kế | Phức tạp route/parent interface/host reachability, policy khác bridge | Mạng L2/L3 được quản trị chặt và có yêu cầu IP riêng |
| **overlay** | Namespace riêng, kết nối nhiều Docker hosts tham gia overlay | Service-to-service nhiều node, Swarm networking | Underlay ports, trust giữa nodes, encryption không tự được suy ra, routing mesh exposure | Dịch vụ đa node/Swarm với lifecycle rõ ràng |

**Không có mode nào làm ứng dụng “tự động an toàn”.** Người thiết kế cần xác minh route, firewall, identity, TLS/mTLS, quyền Docker control plane và khả năng quan sát phù hợp với từng mode.

### 2.1. Mode không đồng nghĩa driver

Ví dụ:

~~~text
docker run --network bridge ...       # Tham gia network 'bridge' mặc định
docker run --network app_net ...      # Tham gia user-defined Docker network
docker run --network host ...         # Chia sẻ mạng với host (nếu được hỗ trợ)
docker run --network none ...         # Không thiết lập network thông thường
docker run --network container:api ...# Chia sẻ namespace của container api
~~~

Một Docker network được tạo bằng **--driver bridge**, **--driver macvlan**, **--driver ipvlan** hoặc **--driver overlay** tùy hệ thống. Khi dùng **--network app_net**, mode ở góc nhìn container là tham gia network đó; driver của app_net mới quyết định data plane.

Các lệnh trong bài nhằm **giải thích**, chỉ chạy trên môi trường/lab được cấp quyền; phần lớn image và tên tài nguyên là ví dụ.

## 3. Bridge networking: nền tảng cho nhiều container trên một host

### 3.1. Default bridge là gì?

Trên Docker Engine Linux thông thường, network **bridge** mặc định là mạng bridge có sẵn; container không chỉ định network có thể được gắn vào đó tùy daemon configuration. Mỗi container thường có network namespace riêng, một interface liên quan veth, IP của Docker-managed subnet và default route phù hợp.

**Các container trên cùng bridge** có thể giao tiếp theo policy mạng/daemon, nhưng **khả năng phân giải tên tự động bằng tên container** trên default bridge không giống user-defined bridge. Những cơ chế legacy như links có hạn chế và không nên được dùng thay quản lý service discovery hiện đại.

~~~text
Docker host
  |
  +-- bridge mặc định
        |
        +-- container-A: 172.x.y.a
        +-- container-B: 172.x.y.b

Container-A ↔ Container-B:
  Có khả năng giao tiếp bằng IP trên cùng bridge theo cấu hình/policy.
  Tên container không tự có cùng DNS discovery như user-defined bridge.
~~~

### 3.2. User-defined bridge khác gì?

Tạo mạng bridge dành riêng cho một ứng dụng:

~~~bash
# Chỉ chạy trong lab đã được phê duyệt.
docker network create --driver bridge demo_app

# Kiểm tra sau khi tạo; không làm trên production ngoài change process.
docker network inspect demo_app
~~~

**User-defined bridge** có các lợi ích thường gặp:

- **Service/container-name resolution** thông qua Docker embedded DNS theo ngữ cảnh network.
- Tách workload sang **nhiều bridge networks** có membership được kiểm soát.
- Cho phép gắn/tách container vào network theo cơ chế Docker khi được hỗ trợ.
- Có thể cấu hình IPAM/subnet, gateway hoặc các driver options trong phạm vi hỗ trợ.
- Không cần publish port ra host để **hai container trên cùng user-defined bridge** giao tiếp.

Ví dụ:

~~~mermaid
flowchart LR
    P["reverse-proxy"] -->|app_net| A["api"]
    A -->|data_net| D["database"]
    P -. "Không cùng data_net" .- D
    P -. "ports public/host chỉ khi được phép" .-> H["Host ingress"]
~~~

**Sơ đồ mạng hai nhánh không tự chứng minh reverse-proxy không thể tiếp cận database bằng mọi cách:** proxy có thể gửi request tới API để API tác động DB; API có thể làm application-layer proxy; host có thể có tuyến/đặc quyền; và workload có thể được nối thêm network khác. Đây là **tách connectivity**, không thay quyền truy cập ứng dụng.

### 3.3. Hành vi khi các container cùng bridge

Một sai lầm là nghĩ chỉ những container có **ports: hoặc EXPOSE** mới nghe được từ container khác. Trong Docker bridge thông thường, **một process lắng nghe trên địa chỉ phù hợp bên trong container** có thể reachable từ các container **cùng network** mà không cần publish host port; firewall và các hạn chế riêng vẫn có thể thay đổi điều đó.

~~~text
Container DB:
  Process listens on 0.0.0.0:5432 inside its namespace
  No host -p or ports declared

Container APP on same bridge:
  Có thể kết nối DB:5432 theo network reachability/policy.

Client ngoài Docker host:
  Không vì thế được cấp host published port 5432.
~~~

**Không publish port** giảm exposure từ bên ngoài host trong mô hình thường gặp, nhưng **không tạo firewall per-port giữa các container chung bridge**.

### 3.4. Giới hạn của tách bridge

Hai user-defined bridge networks khác nhau thường được Docker quản lý theo mô hình cô lập tương ứng; container chỉ gắn với một mạng không mặc định thông nhau với container chỉ gắn mạng kia. Tuy nhiên:

- Một container **multi-homed** tham gia cả hai mạng có thể truy cập dịch vụ ở cả hai mạng.
- Host có quyền network và Docker daemon có thể có khả năng kết nối/định tuyến vượt ranh giới namespace.
- Docker **published ports** hoặc cơ chế proxy/service ingress có thể mở đường giữa các vùng qua endpoint công khai.
- Những workload có **NET_ADMIN, privileged, Docker socket hoặc host networking** có thể làm thay đổi giả định threat model.
- Cấu hình daemon, inter-container communication và Docker firewall backend có thể thay đổi behavior.

Vì vậy, user-defined bridge là một cơ chế **tách mạng hữu ích**, không được coi ngang với VPC có network firewall độc lập hoặc một mandatory access control cho từng ứng dụng.

## 4. Host network mode: giảm cô lập, mở rộng bề mặt host

Chế độ **--network host** làm container sử dụng **host network namespace** trên môi trường hỗ trợ. Container không còn có namespace riêng cho interfaces, routing table và socket bindings theo mô hình bridge mặc định.

~~~mermaid
flowchart LR
    H["Host IP stack / TCP-UDP ports"] --> P["Process host"]
    H --> C["Process trong container host network"]
    C -. "Không có container bridge/veth riêng" .-> H
    P -. "Cạnh tranh port / cùng network namespace" .-> C
~~~

### 4.1. Hệ quả bảo mật

1. **Mất ranh giới network namespace riêng**: container nhìn network interfaces/routes/socket context theo cùng namespace với host; mức thao tác thực tế còn phụ thuộc Linux capabilities, quyền người dùng và host controls.
2. **Port collision:** hai process không thể cùng bind một địa chỉ/protocol/port nếu không có cơ chế chia sẻ socket thích hợp.
3. **Loopback scope thay đổi:** localhost trong container **host mode** là loopback của host network namespace, không còn loopback container độc lập.
4. **Port publication semantics khác:** tùy Docker/OS, **-p/--publish bị bỏ qua** hoặc không có ý nghĩa như bridge vì không có lớp DNAT mapping riêng.
5. **Host service exposure:** process trong container có thể truy cập những dịch vụ host đang lắng nghe theo địa chỉ và policy, kể cả các dịch vụ vốn giả định chỉ host-local.
6. **Quan sát và quy kết:** log IP/port có thể khó phân biệt traffic của workload với host nếu thiếu process/cgroup/identity telemetry.

Không nên tuyên bố mọi container host mode **mặc nhiên có quyền đổi firewall hoặc sniff mọi packet**; các thao tác đó phụ thuộc capabilities/privileges, hệ điều hành và cơ chế bảo vệ khác. Nhưng **mất cô lập mạng** là thay đổi trust boundary đáng kể.

### 4.2. Khi nào có thể phù hợp?

Một số **host-level monitoring agents, performance-sensitive services hoặc workload cần tiếp cận network stack đặc thù** có thể chọn host mode. Trước khi dùng, hãy hỏi:

- Có thể thay bằng **user-defined bridge + published ports hẹp** không?
- Agent có thật sự cần **host network namespace** hay chỉ cần một socket/metrics endpoint được ủy quyền?
- Container process chạy dưới **user không đặc quyền**, đã bỏ capabilities không cần thiết và có seccomp/AppArmor/SELinux phù hợp chưa?
- Host firewall và cloud security group có kiểm soát **port thực sự bind** không?
- Có các host services chỉ bind **127.0.0.1** với kỳ vọng không bị container khác gọi tới không?
- Những môi trường **Docker Desktop/rootless** đang dùng có hỗ trợ host networking theo ngữ nghĩa được mong đợi không?

**Docker Desktop host networking có khả năng và giới hạn khác Linux Engine**, phụ thuộc nền tảng/phiên bản/tùy chọn. Không chuyển một lệnh host mode từ Linux server sang macOS/Windows rồi giả định nhìn được mọi interface host hoặc L2 như Linux native.

### 4.3. Không dùng host mode để sửa lỗi DNS tùy tiện

Nếu container bridge không resolve được tên API, nguyên nhân có thể là **DNS configuration, proxy, resolver, firewall hoặc default route**. Chuyển sang host mode để “chạy được” có thể che lỗi và mở thêm quyền mạng. Hãy chẩn đoán DNS và đường đi trước khi đổi trust boundary.

## 5. None network mode: cắt đường IP thông thường

**--network none** tạo container không được cấu hình kết nối vào một Docker network thông thường. Trong môi trường Docker Linux, namespace vẫn có **loopback interface**, nhưng không có đường veth/bridge/host route mặc định như mode bridge.

~~~text
docker run --rm --network none alpine:3.20 ip addr

Kỳ vọng khái niệm:
  - Có loopback (lo) trong namespace.
  - Không có network interface/route đi tới bridge hoặc Internet thông thường.
~~~

Lệnh trên chỉ là ví dụ cho **lab**, cần image đã được phê duyệt và công cụ ip trên image. Không phải mọi image tối giản đều có tiện ích ip.

### 5.1. Trường hợp sử dụng

- Batch job xử lý dữ liệu có sẵn trong container/volume và **không cần network**.
- Công cụ parse/convert dữ liệu không tin cậy mà yêu cầu giảm kênh giao tiếp.
- Test cô lập network stack hoặc chương trình cần xác minh behavior offline.

### 5.2. Giới hạn của none

**None không tương đương air gap hoàn chỉnh** nếu workload vẫn có:

- **Bind-mounted host directories**, có thể ghi kết quả vào file được process khác đọc hoặc đồng bộ.
- **Unix domain sockets** được mount từ host, ví dụ Docker socket hoặc service socket có quyền mạnh.
- **Privileged/device access**, kernel interfaces hoặc khả năng tạo/thay network namespace nếu được trao quyền quá rộng.
- **Logging/output channels**, job orchestration và artifact upload do host/control plane thực hiện.
- Cơ chế network được thêm sau đó bởi actor có quyền, nếu lifecycle/daemon cho phép.

Để cô lập mạnh hơn, kết hợp **read-only filesystem, rootless/non-root UID, capability dropping, seccomp/LSM, không mount Docker socket, ít volumes, secret minimization** và kiểm soát đường xuất kết quả.

## 6. Container network namespace sharing: network=container:...

Chế độ **--network container:<target>** cho một container dùng **network namespace của một container khác**. Các process có thể thấy cùng IP addresses, interface, routing table và TCP/UDP port namespace theo mô hình Docker/Linux hỗ trợ.

~~~mermaid
flowchart LR
    N["Shared network namespace"] --> A["Container app process :8080"]
    N --> S["Container sidecar process :15000"]
    N --> L["127.0.0.1 shared loopback"]
    A --> L
    S --> L
~~~

Đây là dạng hữu ích cho **sidecar proxy, diagnostics agent hoặc thành phần cùng lifecycle**, nhưng:

- **localhost không còn private giữa app và sidecar**. Service chỉ bind 127.0.0.1 của namespace chung có thể được peer cùng namespace gọi nếu policy ứng dụng cho phép.
- **Port bind collision** có thể xảy ra giữa app và sidecar trên cùng namespace.
- Không thể luôn gán **port mappings, DNS, MAC/IP/network flags riêng** cho container tham gia namespace; tùy Docker có các hạn chế cụ thể.
- Nếu một sidecar không được tin cậy bị chiếm, nó có thể truy cập những dịch vụ của app reachable trong namespace chung theo quyền process.
- Lifecycle/chuyển trạng thái namespace phải được quản lý; target container kết thúc có thể ảnh hưởng kỳ vọng mạng/diagnostics.

**Chia sẻ namespace không đồng nghĩa chia sẻ filesystem, PID namespace hoặc user namespace** trừ khi có cấu hình khác. Dù vậy, **độ tin cậy giữa sidecar và app cần cao**, đặc biệt nếu sidecar được trao credential hoặc quyền điều khiển traffic.

## 7. Macvlan: đưa container trực tiếp ra broadcast domain L2

**macvlan** cung cấp cách gắn container vào mạng vật lý/ảo ở tầng 2 theo thiết kế, thường giúp container có **địa chỉ MAC riêng** và IP trên cùng LAN/VLAN của parent interface.

~~~mermaid
flowchart LR
    SW["Physical/virtual switch + VLAN"] --> H["Docker host parent NIC"]
    H --> M["macvlan network"]
    M --> C1["Container A: MAC/IP riêng trên LAN"]
    M --> C2["Container B: MAC/IP riêng trên LAN"]
    SW --> X["LAN peers / network firewall"]
~~~

### 7.1. Điểm khác biệt với bridge NAT

- Container có thể **xuất hiện như một thiết bị mạng riêng** đối với các LAN peers, tùy switch và virtualization.
- Luồng thường **không dùng cơ chế host port publishing/NAT giống bridge**, vì container tham gia LAN với IP riêng.
- **Firewall/NAT rules dành cho Docker bridge chưa chắc kiểm soát traffic macvlan** theo cùng cách.
- Network security phải được áp ở **switch/VLAN, router/firewall, container host/endpoint** và chính sách workload.
- Có thể cần cấu hình **promiscuous mode/MAC learning/port security** phù hợp; không phải cloud/vSwitch nào cũng cho phép.

### 7.2. Host-to-macvlan limitation

Một đặc điểm Linux macvlan phổ biến: **host parent interface không tự giao tiếp trực tiếp với các macvlan endpoints theo đường vật lý đơn giản**. Người triển khai có thể cần **một macvlan subinterface trên host và route phù hợp** hoặc thiết kế khác nếu host phải quản trị container. Cách giải quyết phụ thuộc mode/macvlan/parent interface.

Đừng suy luận rằng container có IP trong LAN thì host và mọi workload trên host mặc nhiên ping hoặc truy cập được IP đó.

### 7.3. Rủi ro bảo mật

1. **Vượt giả định private bridge:** endpoint trở thành tài sản mạng LAN; các hosts ngoài Docker có thể thấy hoặc truy cập nó tùy ACL.
2. **MAC/VLAN exposure:** có thể ảnh hưởng switch port-security, MAC count và policy L2.
3. **Thiếu NAT boundary:** dịch vụ lắng nghe trên IP macvlan có thể reachable trực tiếp, không cần **docker -p**.
4. **Khó tương thích trên public cloud/VM:** hypervisor hoặc provider có thể hạn chế nhiều MAC trên một virtual NIC.
5. **Giám sát lệch:** IDS chỉ đặt trên Docker bridge không nhất thiết thấy luồng macvlan.

### 7.4. Khi nào chọn?

Thích hợp trong **lab thiết bị mạng, ứng dụng legacy cần hiện như host L2, một số dịch vụ discovery/broadcast** khi các giới hạn driver và quyền mạng đã được hiểu rõ. Không nên dùng macvlan chỉ vì muốn tránh cấu hình reverse proxy hoặc DNS.

## 8. Ipvlan: tách IP theo mô hình L2/L3

**ipvlan** cho phép các containers sử dụng địa chỉ IP theo mô hình chung với parent interface, với **L2 mode** hoặc **L3 mode** tùy thiết kế.

| Chế độ | Mô hình khái niệm | Điểm cần quản trị |
| --- | --- | --- |
| **IPvlan L2** | Các container IP cùng phân đoạn L2 theo cách driver điều phối, thường chia sẻ MAC của parent theo mô hình Linux | IPAM, switch/ARP/ND, VLAN và reachability |
| **IPvlan L3** | Container subnets được định tuyến qua parent/host; giảm phụ thuộc broadcast theo thiết kế | Routes ở mạng upstream, return path, router/firewall policies |

**Ipvlan L3 không tự động làm mạng upstream biết route đến container prefix**. Nếu không có route quay về hoặc next hop hợp lệ, traffic một chiều có thể bị drop dù container có IP/route đúng.

### 8.1. Rủi ro cần kiểm tra

- **Overlapping IP ranges** với host/LAN/VPN hoặc VPC gây route ambiguity.
- **Firewall host/bridge không nằm trên path** như sơ đồ thiết kế ban đầu.
- **IP address ownership, L2 isolation và neighbor discovery** khác bridge/macvlan.
- Phải kiểm tra **host–container reachability**, không dựa trên kỳ vọng bridge mode.
- Cần hiểu giới hạn **Docker Engine Linux, host kernel, vSwitch và provider** trước khi triển khai.
- Chuyển driver **không bảo vệ ứng dụng** khỏi authentication bypass hoặc lộ secrets.

### 8.2. Macvlan và ipvlan: chọn theo hạ tầng thật

Macvlan thường được nhắc tới khi **cần MAC độc lập** của container trên LAN; ipvlan có thể hữu ích khi **mạng upstream không chấp nhận nhiều MAC** hoặc khi cần routing L3 theo thiết kế. Nhưng hiệu quả/bảo mật phụ thuộc **switch topology, cloud policies, IPAM, ACL, Linux kernel và ứng dụng**.

Trước khi quyết định, thử **khả năng triển khai thật trên switch/vSwitch**, đánh giá ARP/ND, upstream routes và firewall visibility. Không coi một câu lệnh thành công trong laptop Docker Desktop là bằng chứng driver sẽ hoạt động trên cluster production.

## 9. Overlay networking: liên lạc giữa nhiều Docker hosts

**Overlay network** trong hệ sinh thái Docker thường được dùng với **Swarm mode** để kết nối container/services trên nhiều nodes qua một underlay IP network, dựa trên cơ chế encapsulation và điều phối endpoint.

~~~mermaid
flowchart LR
    subgraph A["Docker node A"]
        C1["Service A / overlay endpoint"]
        N1["Overlay driver"]
        C1 --> N1
    end
    subgraph B["Docker node B"]
        N2["Overlay driver"]
        C2["Service B / overlay endpoint"]
        N2 --> C2
    end
    N1 <-->|Encapsulated traffic over underlay| N2
    N1 -. "Host/underlay ACL" .-> F["Network controls"]
    N2 -. "Host/underlay ACL" .-> F
~~~

### 9.1. Overlay không tự bảo đảm mã hóa

Encapsulation là cơ chế đưa packet của overlay qua mạng vật lý, **không tự đồng nghĩa data confidentiality/integrity**. Trong môi trường Docker Swarm phù hợp, overlay network có thể hỗ trợ **mã hóa dữ liệu overlay bằng option driver thích hợp**, nhưng:

- Cần **chủ động bật, xác minh và kiểm thử** cơ chế mã hóa được dùng.
- Xem compatibility/performance/OS limitations; đừng giả định Linux/Windows nodes hỗ trợ đồng nhất.
- **Control-plane bảo mật của cluster** và **data-plane overlay encryption** là những phạm vi khác nhau.
- Service-to-service **mTLS ở tầng ứng dụng** vẫn có thể cần cho định danh và quyền truy cập.
- Underlay firewall vẫn phải giới hạn **node-to-node control/data ports** theo topology triển khai.

Không đưa cluster overlay lên mạng không đáng tin chỉ vì thấy chữ “overlay”.

### 9.2. Swarm ingress routing mesh không phải overlay service isolation

Trong Docker Swarm, **published service ports** có thể dùng **routing mesh/ingress** tùy publish mode. Điều đó có thể khiến port được tiếp nhận ở nhiều nodes và chuyển đến task phù hợp, **không chỉ node đang chạy ứng dụng**.

Khi review phải tách:

- **Overlay network membership:** task/service nào có thể nói chuyện bên trong.
- **Published service port:** những node/IP nào lắng nghe ingress và được client ngoài cluster kết nối.
- **Host firewall/security group:** node nào chấp nhận traffic từ Internet hoặc subnet khác.
- **Service authentication:** ai được phép gọi API sau khi kết nối.

Chỉ xem IP của task đang chạy có thể bỏ sót **các node khác đang mở cổng ingress**.

### 9.3. Overlay và phân đoạn multi-tenant

Một overlay network chung cho nhiều nhóm ứng dụng có thể tạo **east–west reachability** rộng. Nên:

1. Tách network membership theo trust boundaries và nhu cầu ứng dụng.
2. Có **identity/mTLS** cho service-to-service và authorization theo role.
3. Hạn chế quyền **join/attach network**, deploy services và publish ports.
4. Theo dõi **overlay endpoint inventory, service discovery, inter-node flows và node membership**.
5. Đánh giá **MTU/encapsulation overhead, packet fragmentation, latency và failover**.

Overlay là công cụ kết nối đa node; nó **không tự mang đầy đủ policy engine như Kubernetes NetworkPolicy**. Các nền tảng orchestration dùng network policy riêng không được trộn lẫn semantics vào Docker Swarm nếu không có implementation tương ứng.

## 10. Port publishing, EXPOSE, bind address và bề mặt Internet

**Dockerfile EXPOSE** thường là **metadata/documentation** cho cổng mà ứng dụng dự kiến sử dụng; nó **không tự publish cổng của container lên Docker host hoặc Internet**.

Trong Docker bridge networking:

~~~bash
# Minh họa lab: host port 8080 chuyển vào container port 80.
docker run --rm --name web-lab \
  --network demo_app \
  --publish 8080:80 \
  nginx:stable-alpine
~~~

Nếu không chỉ định host bind IP, Docker có thể publish cổng trên **nhiều/all host interfaces**, bao gồm IPv4/IPv6 tùy môi trường và daemon settings. Cần kiểm tra **cổng thực tế đang bind**, không suy rằng nó chỉ mở ở localhost.

### 10.1. Ví dụ các dạng publish

| Ví dụ | Ý nghĩa thường gặp | Kiểm tra bảo mật |
| --- | --- | --- |
| **-p 8080:80** | Host port 8080 đến container port 80, trên host bind addresses mặc định | Có thể exposed rộng; kiểm tra host IP, IPv4/IPv6 và firewall |
| **-p 127.0.0.1:8080:80** | Ràng buộc host-side publish tới IPv4 loopback theo cấu hình | Dùng cho local agent/reverse proxy, kiểm thử remote reachability và phiên bản Docker |
| **-p 10.1.2.3:8080:80** | Publish tại địa chỉ host cụ thể | IP có tồn tại, SG/firewall có chặn ngoài phạm vi không? |
| **-p 8443:443** | Host port 8443 trỏ tới TLS service trong container | TLS identity/cert chain, trusted reverse proxy và auth |
| **--publish-all hoặc -P** | Publish các exposed ports vào host ports được cấp phát theo Docker semantics | Có thể mở ngoài ý muốn nhiều service; cần inventory port |
| **Không có -p** | Không thiết lập host port mapping do tham số này | Vẫn có giao tiếp trên cùng Docker network hoặc đường route khác |

**Cẩn trọng phiên bản:** Một số phiên bản Docker Engine cũ từng có trường hợp localhost-bound published port có thể được máy trong cùng L2 segment tiếp cận trong điều kiện nhất định; không được coi **127.0.0.1 bind** là biện pháp bảo vệ duy nhất khi chưa kiểm tra trên đúng host/version. Host firewall và network boundary vẫn cần thiết.

### 10.2. Lắng nghe 127.0.0.1 bên trong container khác host 127.0.0.1

Trong **bridge mode**, khi ứng dụng chỉ bind **127.0.0.1** trong container network namespace, nó thường **không lắng nghe trên địa chỉ container interface** mà Docker port mapping hoặc container khác muốn tới. Đó có thể là nguyên nhân khiến publish không hoạt động.

Ngược lại, ứng dụng bind **0.0.0.0** trong container có thể được các peers cùng network gọi. Nhưng **0.0.0.0 ở container không tự tạo host published port** khi không có -p, và **0.0.0.0** là địa chỉ bind/khái niệm wildcard, không phải một địa chỉ nguồn/đích để dùng như server IP cụ thể.

### 10.3. Published port có thể đi vòng suy đoán host firewall

Docker có thể quản lý NAT/filtering rules trong **iptables/nftables** hoặc cơ chế tương ứng. Trên một số cấu hình Linux, traffic published ports được xử lý qua chuỗi Docker trước những quy tắc host firewall tưởng sẽ chặn, khiến công cụ quản trị như **UFW** không có hiệu quả như người vận hành suy đoán.

Biện pháp:

- Kiểm tra **firewall backend và ruleset thực tế** của Docker Engine/host.
- Áp chính sách ở **cloud security group, upstream firewall hoặc host filtering đúng hook**.
- Không xóa tùy tiện các Docker-managed rules vì có thể mất networking hoặc làm lộ đường khác.
- Với backend iptables tương thích, vị trí **DOCKER-USER** có thể hữu ích để đặt rules trước forwarding cho bridge; **không mặc định chain này có cùng ngữ nghĩa trên mọi phiên bản hoặc nftables backend**.
- Nếu dùng pre-DNAT IP/port cho policy, nhớ rằng rules nhìn thấy **địa chỉ/port có thể đã bị DNAT**; muốn match original destination có thể cần cơ chế conntrack/phù hợp với firewall.
- Kiểm tra bằng **external reachability test có quyền**, không chỉ xem firewall config text.

## 11. DNS, service discovery và rủi ro nhầm danh tính

### 11.1. Docker embedded DNS

Trên **user-defined Docker networks** theo cấu hình hỗ trợ, Docker cung cấp **service/container name resolution** và thường hiển thị resolver nội bộ qua địa chỉ như **127.0.0.11** trong góc nhìn container. Resolver này có thể forward những truy vấn không thuộc Docker network tới DNS upstream theo policy của Engine.

~~~text
Network: app_net

proxy  ---> resolves "api" ---> container/service IP hiện tại
api    ---> resolves "db"  ---> database endpoint cùng network được tham gia

Không publish host port chỉ để gọi api bằng service name.
~~~

**Tên DNS không phải bằng chứng authentication.** Nếu workload có thể tự tham gia mạng và đăng ký alias trùng/ngữ nghĩa gây nhầm, hoặc DNS bị đổi, client có thể kết nối sai endpoint. Cần TLS/mTLS, service authorization, hạn chế network membership và kiểm soát container orchestration.

### 11.2. Default bridge và user-defined bridge

Không giả định default bridge tự phân giải tên container giống user-defined bridge. Nếu một ứng dụng chạy được trên Compose nhưng không resolve tên khi chạy bằng lệnh Docker tùy ý, hãy kiểm tra **network membership, aliases, resolver và DNS policy**, thay vì đưa container sang host mode.

### 11.3. DNS security vẫn cần ở các tầng khác

- **DNS queries** có thể đi qua Docker resolver hoặc DNS upstream; phải xem route/egress policy.
- **DoH/DoT** có thể đi theo đường ứng dụng, không được coi Docker DNS là điểm quan sát duy nhất.
- Response DNS có thể trả **IPv6 AAAA** khiến client chọn đường mà firewall IPv4 chưa bao phủ.
- Khi nhiều user-defined networks có **aliases giống nhau**, cần xác minh resolution context và kết quả trên đúng container.
- Đối với database/identity endpoints, nên sử dụng **TLS hostname/identity verification**, không tin mỗi IP trả từ DNS.

## 12. IPv4, IPv6, NAT và đường đi thực của container

### 12.1. Bridge IPv4 và NAT

Trong cấu hình Docker bridge Linux phổ biến, container có private IPv4 và có thể sử dụng Docker-managed routing/NAT để kết nối ra ngoài khi network/daemon/host firewall cho phép.

~~~text
Container APP 172.x.0.5:54000
      |
      | outbound request
      v
Host Docker bridge -> source NAT / routing -> external service
      |
      v
Internet / internal networks

Return traffic cần khớp trạng thái flow/NAT và host policy.
~~~

**NAT không phải access control**. Một container có thể gửi yêu cầu tới địa chỉ không mong muốn nếu default egress không được hạn chế. Firewall outbound, DNS policy, service identity và workload-level authorization vẫn cần thiết.

### 12.2. IPv6 cần đánh giá độc lập

Docker có hỗ trợ nhiều cấu hình IPv6 tùy daemon/network, nhưng không thể lấy một rule IPv4 để kết luận traffic IPv6 đã được kiểm soát. Khi bật dual-stack:

- Xác minh **IPv6 address allocation và route** trong namespace.
- Kiểm tra **IPv6 inbound/outbound firewall**, NAT hoặc chế độ routing đúng thực tế.
- Xác nhận cổng publish có **IPv6 host listener/exposure** không.
- Kiểm tra DNS AAAA và application preference/happy eyeballs.
- Đánh giá security policy cho **neighbor discovery, router advertisement và traffic tới mạng ngoài** theo phạm vi có hỗ trợ.

**Container không publish IPv4 port** vẫn có thể có đường IPv6 riêng trong cấu hình định tuyến phù hợp; không được suy từ một lệnh Docker hiển thị IPv4 mà bỏ IPv6.

### 12.3. Không có Internet không có nghĩa không có mạng

Một **internal bridge network** có thể được cấu hình hạn chế kết nối ngoài; container trên mạng đó vẫn có thể liên lạc nội bộ theo policy và có thể truy cập một số dịch vụ host/network tùy cấu hình triển khai. Nếu container được nối thêm **mạng thứ hai có egress**, nó có thể có đường ra ngoài qua mạng đó.

**internal: true không phải ranh giới chống exfiltration tuyệt đối**. Cần xét multi-homing, host mounts, mounted sockets, application proxying và quyền quản trị Docker.

## 13. Rootful, rootless và Docker Desktop: cùng cú pháp chưa chắc cùng đường đi

### 13.1. Docker Engine rootful trên Linux

Docker daemon rootful có quyền rất mạnh với host network, namespaces và firewall rules. Người có quyền sử dụng **Docker socket/API** có thể tạo container với mount, privileges hoặc network mode mới; trên mô hình phổ biến, quyền điều khiển Docker daemon gần với **quyền quản trị host**.

Do đó:

- Không mount **/var/run/docker.sock** vào ứng dụng không được tin.
- Không cho application user không cần thiết quyền chạy Docker admin commands.
- Dùng **RBAC, approval, CI credentials giới hạn và kiểm toán Docker API** ở nơi có thể.
- Cân nhắc **rootless mode, user namespaces, capabilities/LSM** như các lớp giảm rủi ro, nhưng hiểu giới hạn còn lại.

### 13.2. Rootless Docker

**Rootless Docker** chạy daemon/containers trong cơ chế user namespaces, giảm quyền hệ thống cần cho nhiều thao tác. Tuy nhiên, network stack có thể dựa vào **user-mode networking** (ví dụ một số triển khai dùng slirp4netns hoặc pasta), khiến behavior về **host ports, source IP, network performance, ping, low ports và host reachability** khác rootful Linux.

**Rootless không có nghĩa mọi chức năng network driver hoạt động y hệt rootful**. Cần test mode/driver trên đúng phiên bản và host policy, không dựa vào output từ môi trường khác.

### 13.3. Docker Desktop trên Windows/macOS

Docker Desktop thường chạy Linux containers trong **VM/lớp ảo hóa**, nên:

- Bridge interfaces có thể nằm **bên trong VM**, không xuất hiện như Linux bridge trực tiếp trên host OS.
- **Host-to-container access và port forwarding** có cơ chế trung gian.
- Host network mode có thể yêu cầu version/tùy chọn riêng và không giống Linux native trong mọi lớp giao thức.
- **macvlan/ipvlan** thường không trực tiếp nối được tới NIC vật lý host giống Linux Engine theo mô hình đơn giản.
- Kết quả traceroute, firewall rules và inbound exposure phải được kiểm tra trên **host OS + VM/Engine + upstream network**.

Một quy trình bảo mật nên ghi rõ **Docker Engine version, OS, rootless/rootful, Desktop/VM architecture** và network backend. Không kết luận production tương đương chỉ dựa trên việc cùng chạy Compose YAML ở laptop.

## 14. Segmentation và kiểm soát quyền: network membership mới là điểm bắt đầu

Docker networks giúp tách các tập endpoint, nhưng **Docker bridge network không mặc định là zero trust**. Hai containers cùng mạng có thể có khả năng truy cập nhiều listener của nhau.

### 14.1. Thiết kế theo luồng nghiệp vụ

Giả sử kiến trúc ba tầng:

~~~text
External client -> Reverse proxy -> API -> Database

Allowed:
  Internet -> proxy:443
  proxy -> api:8080
  api -> db:5432

Denied by design:
  Internet -> api/db
  proxy -> db direct
  db -> Internet except approved maintenance dependencies
  unrelated service -> db
~~~

Các luồng **denied** cần được thực thi bằng **network membership, host/cloud firewall, application authentication/authorization và egress policy** thích hợp. Việc proxy không cùng data network giảm direct reachability, nhưng không ngăn nó sử dụng API để gây tác động DB nếu API có lỗ hổng.

### 14.2. Phân biệt reachability và authorization

| Khả năng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Same-network membership** | Hai containers có thể có IP route tới nhau | API và DB cùng data network |
| **TCP reachability** | Có thể tạo connection tới cổng listener theo policy | API kết nối TCP 5432 |
| **Authenticated session** | Endpoint nhận được danh tính hợp lệ | PostgreSQL xác thực user của API |
| **Authorized operation** | Identity được phép thực hiện hành động | API user chỉ được đọc bảng cần thiết |
| **Observed successful access** | Có evidence application đã thực hiện | DB audit ghi một truy vấn thành công |

**Một container có thể ping được DB không chứng minh được phép đọc DB**; ngược lại, **không ping được** không tự chứng minh cổng TCP đã bị chặn, vì ICMP có policy riêng.

### 14.3. Multi-homed container và đường vòng

Một container gắn cả **front_net** và **data_net** có quyền kết nối tới cả hai, và có thể trở thành điểm **application proxy/forwarding** hoặc kênh exfil nếu bị chiếm quyền. Hạn chế:

- Không gắn **proxy/sidecar** vào data network nếu không có nghiệp vụ rõ.
- Dùng **application credentials** tách theo service, hạn chế quyền DB.
- Không cấp **NET_ADMIN, privileged hoặc Docker socket** cho mọi container.
- Giới hạn outbound bằng host/cloud firewall hoặc policy engine phù hợp với mô hình Docker.
- Theo dõi sự kiện **network connect/disconnect** và thay đổi Compose/service topology.

**Network driver không thay cho một policy engine egress per-container bắt buộc**. Với yêu cầu chặn chặt, phải lựa chọn và kiểm thử công nghệ thực thi tại đúng host/overlay/cluster, thay vì dựa vào tên network.

## 15. Docker Compose: phân chia network theo ba tầng

### 15.1. Ví dụ kiến trúc

Một stack minh họa gồm reverse proxy, API và database:

~~~mermaid
flowchart LR
    U["Người dùng / test client"] -->|Host published port| P["proxy"]
    subgraph APPNET["app_net (internal bridge)"]
        P --> A["api"]
    end
    subgraph DATANET["data_net (internal bridge)"]
        A --> D["db"]
    end
    P -. "Không tham gia data_net" .- D
    D -. "Không publish host port" .- H["Docker host ingress"]
~~~

### 15.2. Compose YAML có chú giải về phạm vi

~~~yaml
# compose.yaml — ví dụ học tập, KHÔNG phải stack production chạy ngay.
# Thay placeholder images và cấu hình ứng dụng/TLS trước khi triển khai.
services:
  proxy:
    image: nginx:stable-alpine
    ports:
      - "127.0.0.1:8080:80"  # Chỉ local-facing theo cấu hình này.
    networks:
      - edge_net
      - app_net
    # Thực tế cần cấu hình upstream api và TLS/WAF ở điểm ingress phù hợp.

  api:
    image: registry.example.invalid/team/api:1.0
    expose:
      - "8080"                # Metadata, không phải firewall rule.
    networks:
      - app_net
      - data_net
    # Không publish API trực tiếp lên Docker host.

  db:
    image: registry.example.invalid/team/db:1.0
    networks:
      - data_net
    # Không đặt database password cố định trong file này.
    # Thiết lập secrets, volumes, health checks và DB auth thực tế riêng.

networks:
  edge_net:
    driver: bridge

  app_net:
    driver: bridge
    internal: true

  data_net:
    driver: bridge
    internal: true
~~~

**Cấu hình có placeholder** và chưa có database credentials, volume, healthcheck hay cấu hình NGINX upstream: nó là bài toán **đọc network membership**, không phải tệp triển khai đầy đủ.

### 15.3. Phân tích điểm được và chưa được bảo vệ

| Kiểm soát | Mục tiêu trong ví dụ | Giới hạn còn lại |
| --- | --- | --- |
| **proxy: edge_net + app_net** | Có đường nhận request và gọi API | Proxy multi-homed có thể là pivot nếu bị chiếm |
| **api: app_net + data_net** | API nói chuyện với proxy và DB | API có thể truy cập mọi listener hợp lệ trong data_net |
| **db: data_net** | Không join edge_net/app_net; không có published host port | Docker host, người có quyền daemon hoặc các đường khác vẫn cần xét |
| **internal: true** | Hạn chế kết nối ngoài với các bridge được đánh dấu internal | Không thay application auth, không ngăn egress thông qua một thành viên multi-homed có chức năng proxy |
| **127.0.0.1 host bind** | Thu hẹp ingress ví dụ về phía host | Cần xác minh Docker version, host firewall và remote reachability |
| **Không dùng host mode/privileged** | Giữ network namespace riêng cho dịch vụ | Vẫn phải hạn chế daemon socket, capabilities, mounts và IAM |

**Network membership chỉ giảm các đường kết nối trực tiếp.** Một client có thể gửi yêu cầu hợp lệ tới proxy rồi API bị khai thác để làm thay đổi DB; bài toán đó cần **authentication, authorization, input validation, WAF/API controls, mTLS và DB least privilege**.

### 15.4. Compose network_mode cần dùng đúng

Trong Compose, **network_mode** dùng cho những kiểu như **host**, **none** hoặc chia sẻ namespace với service khác tùy khả năng/nền tảng.

~~~yaml
# Các đoạn minh họa ĐỘC LẬP, không ghép nguyên xi vào Compose ở trên.
services:
  diagnostic:
    image: alpine:3.20
    network_mode: "none"

  shared_sidecar:
    image: alpine:3.20
    network_mode: "service:api"
~~~

**Không đồng thời đặt network_mode và networks trên cùng một service** nếu đó là tổ hợp không hợp lệ theo Compose. Với network_mode: host, các cấu hình host-port mapping theo kiểu bridge **không nên được sử dụng**; hành vi validation/ignore tùy Docker/Compose. Với network_mode chia sẻ service, phải hiểu rằng **127.0.0.1 và port namespace được dùng chung**, không còn là hai endpoint mạng tách biệt.

### 15.5. Khi nào nên dùng một mạng hoặc nhiều mạng?

- Dùng **một user-defined bridge riêng** cho một nhóm microservices có độ tin cậy và quyền tương tự nếu overhead đơn giản được ưu tiên.
- Tách **frontend, application, data, management** khi nhiều thành phần không cần giao tiếp trực tiếp.
- Tránh tạo **một network lớn dùng chung mọi stack** chỉ để DNS resolution thuận tiện.
- Không tạo quá nhiều mạng mà không có owner, kiểm thử và khả năng quan sát: phức tạp sai cấu hình có thể lớn hơn lợi ích.
- Nếu yêu cầu **policy theo identity/port/egress** không được đáp ứng bằng Docker networks, bổ sung **host/network firewall, service proxy, policy-capable platform hoặc orchestration** tương ứng.

## 16. Firewall, ingress và egress trên Linux Docker host

### 16.1. Ba điểm thực thi nên phân biệt

~~~mermaid
flowchart TD
    E["Client từ bên ngoài"] --> N["Cloud SG / upstream firewall"]
    N --> H["Docker host listener / DNAT / packet filtering"]
    H --> C["Container network interface"]
    C --> A["Application listener + authorization"]
    C --> O["Outbound/egress routing"]
    O --> F["Host/cloud egress controls"]
    F --> D["External DNS/API/database"]
~~~

- **Cloud SG / upstream ACL:** hữu ích để giới hạn trước khi traffic tới host; phải ghi đúng source CIDR, port, IPv4/IPv6 và network path.
- **Docker host firewall:** chịu ảnh hưởng Docker-managed rules, NAT/forwarding, iptables/nftables backend, daemon config và network driver.
- **Application/service policy:** giới hạn chức năng kể cả khi connection đã tới được cổng.

Một policy “cloud SG chỉ cho Internet tới TCP 443” không tự bảo vệ traffic giữa các containers trên host bridge. Ngược lại, chỉ đặt rule trong container không bảo vệ các host ports ngoài vùng kiểm soát.

### 16.2. DOCKER-USER và các điều kiện áp dụng

Trên Linux Engine sử dụng **iptables backend** phù hợp, chain **DOCKER-USER** là điểm thường dùng để áp filtering cho traffic được Docker chuyển tiếp, trước một số Docker rules trong forward path. Nhưng:

1. **Không phải mọi traffic đều qua FORWARD/DOCKER-USER**: host-local, output của host, loopback hoặc host networking có thể theo hook khác.
2. **DNAT có thể đã xảy ra** khi packet đến điểm filtering; destination hiện tại có thể là container IP/port, khác host published port ban đầu.
3. Với **nftables backend**, vị trí/khả năng dùng chain tương đương và behavior có thể khác.
4. Docker daemon có thể cập nhật rules; sửa trực tiếp các chuỗi managed mà không có cơ chế quản trị có thể làm hỏng network hoặc mất quy tắc.
5. **IPv6** cần ruleset/address family tương ứng; không mặc định iptables IPv4 kiểm soát traffic IPv6.
6. Host mode và macvlan/ipvlan có thể đòi hỏi **policy ở hook/gateway khác**.

**Đọc đúng ruleset, xác minh đường data plane và dùng cấu hình đã được hỗ trợ** là phương pháp an toàn hơn sao chép một lệnh iptables từ Internet.

### 16.3. Container egress cần policy riêng

Một workload bị khai thác có thể liên lạc với:

- Endpoint Internet thông qua Docker bridge NAT.
- Các subnet nội bộ reachable từ host/router.
- Host services hoặc metadata/credential services nếu topology/policy cho phép.
- DNS servers, HTTP proxies, object storage, database và bên thứ ba.

Thiết kế egress:

1. Kiểm kê **đích nghiệp vụ, ports/protocols, DNS/identity** của từng service.
2. Đặt **default deny hoặc allowlist hợp lý** tại enforcement point có quan sát đúng packet.
3. Hạn chế access tới **host management, Docker API socket, cloud metadata endpoints** khi không cần.
4. Có phương án **DNS egress**, proxy authentication, certificate verification và xử lý IPv6.
5. Kiểm tra **fail-open/fail-closed** của proxy/firewall/agent nếu policy phụ thuộc thành phần ngoài container.
6. Ghi telemetry và **negative tests** để chứng minh traffic không được phép thực sự bị chặn.

Nếu container được nối tới mạng **internal** và một mạng có default egress, không được mô tả nó là “không có Internet” chỉ vì có network internal.

## 17. Threat model: chọn network mode sai tạo ra rủi ro nào?

| Threat / sai cấu hình | Mode/driver liên quan | Tác động có thể xảy ra | Control / bằng chứng |
| --- | --- | --- | --- |
| **DB exposed qua published port** | bridge + -p | Ngoài host có thể chạm trực tiếp DB nếu firewall cho phép | Port inventory, host bind IP, SG/firewall, external negative test |
| **Host localhost service reachable ngoài ý định** | host mode | Workload host-network có thể gọi host-local listeners | Network mode inventory, host services, capability and policy audit |
| **Lateral movement giữa dịch vụ** | Bridge network chung | Container bị chiếm tiếp cận nhiều service ports trên cùng network | Tách networks, app auth, host/network policy, east–west flow test |
| **Multi-homed pivot** | Một container nối nhiều networks | API/sidecar làm trung gian ngoài intended boundary | Membership review, least privilege, egress policy |
| **Misleading localhost isolation** | container:ID/service sharing | Sidecar gọi endpoint app vốn chỉ bind loopback | Shared namespace review, listener inspection, authorization |
| **False assumption of air gap** | none | Data vẫn đi qua host mounts/socket/artifacts | Mount/API audit, non-network controls, isolation tests |
| **LAN exposure ngoài ý muốn** | macvlan | Container trở thành node LAN, reachable theo VLAN policy | Switch/VLAN ACL, container IP scan có quyền, network inventory |
| **Route/return path thiếu** | ipvlan L3/macvlan | Timeout, kết nối một chiều, khó điều tra | Effective routes, upstream ARP/ND, firewall logs |
| **Overlay traffic bị nghe trộm trên underlay** | overlay nếu encryption không được áp | Mất confidentiality trong các threat models phù hợp | Overlay encryption audit, wire/underlay test, mTLS |
| **Swarm ingress rộng hơn dự kiến** | overlay + published service | Port exposed qua nhiều nodes | Swarm port publishing inventory, node SG, external tests |
| **Untrusted container controls Docker** | Mọi mode nếu có Docker API/socket | Có thể tạo privileged/host-network container hoặc thay topology | API RBAC, daemon audit, không mount socket, rootless khi phù hợp |
| **IPv6 alternate ingress/egress** | bridge/macvlan/host | IPv6 đường ngoài policy IPv4 | IPv6 routes, host/container firewalls, AAAA/dns tests |
| **Docker firewall drift** | bridge + iptables/nftables | Host firewall không enforce như suy đoán | Ruleset review, post-deploy reachability/flow evidence |
| **IPAM collision** | custom bridge/macvlan/ipvlan/overlay | Route ambiguity, VPN/CIDR overlap, outage | IPAM inventory, CIDR reviews, negative overlap tests |
| **Alias/DNS confusion** | user-defined networks | Kết nối sai service hoặc trust name quá mức | Service identity, TLS/mTLS, restrict network joins |
| **Open metrics/admin port** | host hoặc published bridge port | Lộ debug/admin endpoints | Port scan có quyền, bind addresses, auth, firewall |
| **Resource exhaustion qua connections** | Mọi mode có network ingress | Sockets/RAM/CPU/conntrack bị cạn | Rate/concurrency/timeouts, queue bounds, host/network monitoring |
| **Host routing/firewall manipulation** | host network + excessive capabilities | Ảnh hưởng lưu lượng host | Drop NET_ADMIN/privileged, host security baseline, audit |

### 17.1. Chứng minh mức độ rủi ro bằng từng lớp

Một **port publish** hoặc **network route** có thể tạo khả năng kết nối, nhưng không chứng minh đã có compromise. Cần tách:

1. **Potential exposure:** Docker host đã bind/publish port hoặc macvlan IP nằm trong LAN.
2. **Network reachability:** nguồn thử nghiệm thực sự đến được listener theo ACL/firewall hiện hành.
3. **Authentication/authorization:** ứng dụng cho phép định danh nào sử dụng dịch vụ.
4. **Observed action:** logs cho thấy một thao tác đã được thực hiện.

Không kết luận “đã rò dữ liệu DB” chỉ vì thấy TCP 5432 được mở; nhưng cũng **không coi port mở là vô hại** chỉ vì chưa tìm thấy request thành công.

## 18. Case study 1: Docker database bị công khai do publish port

### 18.1. Bối cảnh giả định

Một nhóm triển khai database để phục vụ API trong cùng host. File Compose cũ có mapping:

~~~yaml
# VÍ DỤ CẦN ĐÁNH GIÁ LẠI; không phải cấu hình được khuyến nghị.
services:
  db:
    image: postgres:16
    ports:
      - "5432:5432"
~~~

Nhóm nghĩ rằng vì database ở **bridge network** và không có DNS public nên Internet không thể truy cập nó. Tuy nhiên, Docker host có **public IP** và upstream firewall đang cho phép cổng 5432 từ vùng mạng quá rộng.

### 18.2. Evidence giả định

| Evidence | Quan sát | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- | --- |
| **E1 – Compose config** | db được publish host port 5432 không chỉ định bind IP | Có ý định mở mapping ở host theo mặc định Docker | Không khẳng định Internet reachability qua mọi firewall |
| **E2 – docker port / inspect** | Host binding trên địa chỉ rộng | Mapping tồn tại ở Docker level | Không chứng minh ứng dụng đang authenticate |
| **E3 – Cloud SG** | Inbound TCP 5432 được phép từ CIDR rộng | Có khả năng exposure lớn | Chưa chứng minh kết nối đã đến DB |
| **E4 – Authorized external test** | Có TCP connection tới host:5432 | Network reachability xác nhận | Không chứng minh truy cập dữ liệu |
| **E5 – DB auth audit** | Log ghi các lần authenticate failed | Có truy cập tới DB authentication surface | Không khẳng định thành công hoặc exfiltration |
| **E6 – Firewall/flow logs** | Traffic từ nguồn không thuộc app subnet | Có access attempts không mong muốn | Cần đánh giá nguồn, mức độ và timeline |

### 18.3. Xử lý đúng

1. **Tạo incident/change record**, inventory DB listener, Docker mapping và nguồn được phép.
2. **Giới hạn ingress ngay tại upstream firewall/cloud SG** theo policy khẩn cấp phù hợp, đồng thời bảo vệ đường quản trị.
3. **Bỏ host port mapping của DB** nếu API nằm cùng user-defined network và không cần host exposure.
4. Tạo **app_net/data_net** hẹp; chỉ những service cần DB được tham gia data network.
5. Bảo đảm **DB authentication, credential rotation nếu có nghi vấn, TLS khi phù hợp và least privilege**.
6. Kiểm tra **external negative test** tới host:5432, **internal positive test** API→DB, log firewall và DB.
7. Rà soát **IPv6 exposure, other Docker hosts, backup instances và drift**.
8. Nếu phát hiện xác thực thành công trái phép, mở rộng phạm vi điều tra về truy cập dữ liệu theo quy trình IR.

### 18.4. Bài học

**Bridge mode không tự ngăn ingress từ Internet khi đã publish port ra host.** Phải kết hợp **port inventory, host binding, upstream firewall và app auth**. Một database được gắn **internal network** nhưng có host port mapping không được tự gán nhãn “không reachable từ bên ngoài” mà chưa kiểm tra behavior thực.

## 19. Case study 2: đổi sang host mode làm lộ admin endpoint

### 19.1. Bối cảnh

Một ứng dụng đang ở **bridge** và chỉ cần public ingress qua reverse proxy. Sau một sự cố performance, đội triển khai chuyển service sang **network_mode: host** mà không rà soát listeners. Ứng dụng có endpoint metrics/admin lắng nghe trên **0.0.0.0:9090**.

### 19.2. Sự thay đổi trust boundary

~~~text
Trước khi đổi:
  Container bridge:
    APP listens 0.0.0.0:9090 bên trong container namespace
    Không có host published port tương ứng
    Mức truy cập tùy container networks và host policy

Sau khi đổi:
  Container dùng host network namespace:
    APP binds trên host network addresses/port theo behavior OS
    Host firewall / upstream SG quyết định ingress tới 9090
~~~

Nếu cloud SG/host firewall vô tình cho phép port 9090 hoặc network nội bộ không tin cậy có đường tới host, endpoint có thể exposed rộng hơn dự kiến.

### 19.3. Ứng phó và phòng ngừa

1. Đối chiếu **network mode change, container process listeners, host listening ports và SG/firewall**.
2. Kiểm tra endpoint metrics/admin có **authentication, bind restriction và sensitive information exposure** không.
3. Trở lại **user-defined bridge** nếu không có yêu cầu bắt buộc host networking.
4. Nếu cần host mode, ràng buộc port/bind address phù hợp, lọc ingress/egress và giảm capabilities.
5. Thực hiện external/internal tests từ các nguồn đã cấp quyền; xác nhận metrics endpoint chỉ reachable từ monitoring zone.
6. Đặt kiểm soát CI/IaC để **network_mode: host** phải có security approval.

**Bài học:** không dùng host mode như một mẹo “tăng hiệu năng” mặc định; trước tiên phải đo bottleneck và đánh giá những dịch vụ **tự động trở thành host listeners**.

## 20. Case study 3: macvlan và overlay gây sai giả định phân đoạn

### 20.1. Macvlan trên VLAN nội bộ

Một ứng dụng cũ cần IP riêng trên VLAN vận hành. Team chuyển nó từ bridge sang macvlan, nhưng quên cập nhật sơ đồ firewall: trước đây port được expose qua host và có host filtering, còn hiện tại container có IP LAN riêng.

**Kết quả có thể xảy ra:** các máy trên VLAN có đường tới container bằng IP riêng theo switch/router ACL; host firewall rules dành cho Docker bridge không nhất thiết thấy flow như trước.

Các bước cần kiểm tra:

- Parent interface và VLAN ID đúng; switch cho phép topology/MAC learning cần thiết.
- Container IP/CIDR/gateway không overlap, nằm trong IPAM được phê duyệt.
- **Network ACL/firewall ở LAN edge** kiểm soát những source được phép.
- Host ↔ macvlan connectivity được thiết kế nếu cần monitoring/management.
- Flow/IDS sensor được đặt đúng vị trí, không chỉ trên Docker bridge.

**Không kết luận macvlan làm container “có quyền ngang host”.** Đây là thay đổi **network attachment và L2 exposure**, còn quyền OS/filesystem/daemon tùy cấu hình khác.

### 20.2. Overlay Swarm và encrypted data plane

Một Swarm application dùng overlay giữa hai nodes. Nhóm bảo mật tin rằng vì cluster được bảo vệ bằng mutual TLS ở control plane nên **mọi application traffic giữa nodes đều encrypted**.

Rủi ro là **trộn hai lớp bảo vệ**. Cần xác minh:

1. Overlay network có **encryption option** tương thích và đã được bật không?
2. Những nodes/workloads nào có thể **tham gia overlay** và nhận workload IP?
3. Underlay firewall chỉ cho phép **những node IP/ports thực sự cần thiết** không?
4. Có **mTLS ở lớp ứng dụng** nếu cần xác thực end-to-end giữa services?
5. Swarm ingress có publish ports ở **các nodes ngoài vùng ingress dự kiến** không?
6. MTU/encapsulation và failover có tạo packet loss hoặc bypass khi lỗi không?

**Bài học:** overlay là một cơ chế connectivity đa host; phải chứng minh rõ **encryption, membership, ingress exposure và identity**.

## 21. Điều tra Docker network: quy trình chẩn đoán không xâm lấn

### 21.1. Thu trạng thái trước khi đổi cấu hình

Đầu tiên, xác định **Docker host, Engine/rootless/Desktop, container ID/service, thời gian, error và luồng cần kiểm tra**. Với sự cố đang xảy ra, ưu tiên **read-only Docker queries** để tránh vô tình xóa networks hoặc ngắt traffic.

~~~bash
# Chỉ chạy trên Docker daemon được phép quản trị.
# Liệt kê Docker networks: tên, driver và scope.
docker network ls

# Xem container nào đang chạy, gồm biểu diễn published ports.
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'

# Xem network mode của container.
docker inspect --format '{{.HostConfig.NetworkMode}}' api-container

# Xem Docker networks mà container đang tham gia.
docker inspect --format '{{json .NetworkSettings.Networks}}' api-container

# Xem host-published ports của container.
docker port api-container

# Xem driver, subnet, gateway và endpoints thuộc network được phép.
docker network inspect app_net
~~~

**Lưu ý dữ liệu nhạy cảm:** output từ inspect có thể chứa IP nội bộ, tên services, labels/metadata. Không xuất toàn bộ **docker inspect** hoặc environment/secret values vào ticket công khai; chỉ lấy các trường cần điều tra.

### 21.2. Kiểm tra từ trong container

Nếu image có công cụ phù hợp:

~~~bash
# Chỉ kiểm tra đúng container/network và service được sở hữu.
docker exec api-container ip address
docker exec api-container ip route
docker exec api-container ss -lnt
docker exec api-container cat /etc/resolv.conf

# Kiểm tra DNS và kết nối ứng dụng tới endpoint được cấp quyền.
# Công cụ curl/getent có thể không tồn tại trong image tối giản.
docker exec api-container getent hosts db
docker exec api-container curl -fsS http://api:8080/health
~~~

Khi image không có shell/curl/ip/ss, sử dụng **debug tooling được phê duyệt, telemetry của platform hoặc container kiểm thử trên lab network**; tránh cài thêm công cụ và thêm capabilities vào container production chỉ để kiểm tra.

### 21.3. Điều tra theo loại lỗi

| Triệu chứng | Nhóm nguyên nhân có thể | Bằng chứng ưu tiên |
| --- | --- | --- |
| **Container không resolve được tên service** | Không cùng user-defined network, alias sai, DNS upstream, service chưa có endpoint | Network membership, resolver, service/alias |
| **Resolve đúng nhưng TCP connect fail** | Listener bind loopback, route/ACL, app không chạy, host firewall | Listener, IP/port, flow logs, app health |
| **Container khác gọi được nhưng host không gọi được** | Không publish port, host route/firewall hoặc driver hạn chế | docker port, host bind, network driver |
| **Host gọi được nhưng Internet không gọi được** | Bind loopback, SG/ACL, host firewall, NAT/public IP | Host listeners, external test, firewall logs |
| **Public endpoint reachable ngoài ý muốn** | -p all interfaces, host mode, macvlan LAN, Swarm ingress | Docker port, network mode, host/SG logs |
| **Container không có Internet** | internal/none, DNS, default route, SNAT/conntrack, rootless setup | Network inspect, route, DNS, egress logs |
| **Chỉ IPv6 có đường khác IPv4** | Dual-stack config, IPv6 publish/default route | IPv4/IPv6 listeners, routes, firewalls |
| **macvlan host không ping được container** | Host/macvlan namespace behavior, routing/parent interface | L2/L3 topology, host subinterface, ARP/ND |
| **ipvlan L3 một chiều** | Upstream return route thiếu hoặc firewall không đúng | Routes cả hai chiều, counters, policy |
| **Overlay liên node lỗi** | Underlay ACL, node membership, MTU, route, encryption option | Swarm overlay info, node health, inter-node logs |
| **High latency hoặc packet loss** | MTU mismatch, CPU/TLS, conntrack, DNS, backend saturation | Packet/flow evidence, host metrics, app traces |
| **Traffic không thấy tại host firewall mong muốn** | Route/driver khác, firewall hook khác, logging thiếu | Actual forwarding path, nft/iptables ruleset |

### 21.4. Phân biệt lỗi Docker network với lỗi ứng dụng

Một client có thể TCP connect thành công nhưng API trả **401/403/500**, hoặc một database mở TCP port nhưng từ chối login. Đây không phải bằng chứng network driver lỗi. Ngược lại, **ECONNREFUSED** có thể do app không listen hoặc firewall reject; **timeout** có thể do drop, route hoặc backend quá tải.

Một quy trình tốt đi theo:

~~~mermaid
flowchart TD
    A["Xác định source -> destination:port"] --> B["Inspect network mode và membership"]
    B --> C{"DNS / IP address đúng?"}
    C -- "Không" --> D["Kiểm tra DNS, aliases, networks"]
    C -- "Có" --> E{"Route và host/published-port đúng?"}
    E -- "Không" --> F["Kiểm tra route/NAT/firewall/driver"]
    E -- "Có" --> G{"TCP/TLS connect thành công?"}
    G -- "Không" --> H["Listener, firewall, MTU, packet/flow"]
    G -- "Có" --> I["Kiểm tra authentication, app policy, logs"]
~~~

**Đừng chuyển container sang --network host chỉ để bỏ qua bước chẩn đoán**. Hành động đó làm thay đổi trust boundary và có thể tạo một sự cố security trong khi chưa sửa nguyên nhân.

## 22. Observability: chứng minh đúng mode và đúng đường đi

### 22.1. Metrics và audit cần có

| Nguồn | Trường cần thu | Mục tiêu |
| --- | --- | --- |
| **Docker daemon events/audit** | Container create/start, network connect/disconnect, publish changes, actor | Phát hiện drift hoặc thay đổi network membership |
| **Container inventory** | Image, service, network mode, networks, IPs, published ports | Biết bề mặt kết nối thực tế |
| **Host firewall/NAT** | Conntrack, DNAT/SNAT mapping, policy action, IPv4/IPv6 | Phân biệt published port với path thật |
| **Cloud SG/flow logs** | Source/destination/port, allow/deny, subnet/host | Xác minh host exposure từ vùng ngoài |
| **Service/application logs** | Request ID, auth identity, action, response | Không nhầm reachability với successful access |
| **DNS metrics** | Query target, resolver, NXDOMAIN, latency, IP answer | Phát hiện routing/name discovery sai |
| **Network/host resource metrics** | PPS, BPS, drops, retransmits, CPU, FD, conntrack | DDoS/resource exhaustion và capacity |
| **Overlay/Swarm metrics** | Node membership, endpoint attach, health, ingress ports | Quan sát cross-host topology |
| **Security alerts** | New host mode, docker.sock mount, privileged, open admin ports | Phát hiện thay đổi security posture |

### 22.2. Mẫu event điều tra

~~~json
{
  "caseId": "DOCKER-NET-005",
  "timestamp": "2026-11-28T04:15:00Z",
  "dockerHost": "host-lab-01",
  "container": "api",
  "networkMode": "bridge",
  "networkNames": ["app_net", "data_net"],
  "publishedHostPorts": [],
  "expectedEgress": "approved-dependencies-only",
  "observedSource": "app-net-endpoint",
  "testDestination": "db:5432",
  "testAction": "authorized-connectivity-check",
  "result": "network-reachable",
  "applicationAuthResult": "not-asserted",
  "evidenceOwner": "Container Platform / Security"
}
~~~

Đây là **schema học tập**, không phải output gốc của Docker. Nếu log có **credential, token, Docker socket URI, secrets, internal asset IDs hoặc dữ liệu cá nhân**, chỉ thu thập theo chính sách bảo mật và che thông tin khi chia sẻ.

### 22.3. Thiếu firewall logs không chứng minh không có traffic

Tùy mode/driver, packet có thể **không đi qua đúng hook/sensor** mà người vận hành kỳ vọng. Không thấy conntrack trên một interface cũng có thể do **namespace, overlay encapsulation, capture point hoặc policy logging**.

Hãy ghép **network mode + interface/route + firewall hook + flow logs + app evidence**, thay vì dùng một packet capture duy nhất để kết luận toàn bộ traffic bị chặn.

## 23. Bộ kiểm thử Docker network an toàn

Các test sau áp dụng cho **Docker host/network có ủy quyền rõ**, ưu tiên **staging hoặc lab**. Không tạo hàng loạt kết nối, scan nhiều subnet hay thử phá firewall trên tài nguyên của người khác. Có thể dùng **read-only inspection và synthetic health checks** để tránh gây nhiễu production.

| Test | Điều kiện/thao tác trong phạm vi được phép | Kỳ vọng |
| --- | --- | --- |
| **P1 – bridge name resolution** | Hai containers trên cùng user-defined bridge | Resolve service name và kết nối endpoint hợp lệ |
| **N1 – bridge isolation** | Container không tham gia data_net thử tới DB private IP/port | Không có direct connectivity theo policy đã thiết kế |
| **P2 – API → DB** | API được tham gia data_net dùng DB credential đã cấp | Kết nối và auth đúng role, không cần host publish |
| **N2 – DB host port** | Kiểm tra DB không có host-published port, external test có quyền | Không reachable qua host ingress ngoài thiết kế |
| **N3 – host mode unauthorized** | Review policy/CI test với service không được phép host mode | Config bị từ chối hoặc flagged trước deploy |
| **P3 – host-mode controlled service** | Lab agent thực sự cần host network | Port/loopback behavior đúng, host firewall vẫn enforce |
| **N4 – none network** | Job lab network none thử kết nối TCP ngoài namespace | Không có route IP thông thường, không cấp daemon socket |
| **P4 – shared namespace** | App và sidecar test có chủ đích dùng chung loopback | Cả hai hiểu đúng port/lifecycle, auth của admin endpoints vẫn có |
| **N5 – macvlan LAN exposure** | Authorized test từ LAN peer tới macvlan IP/port | Chỉ các source/ports được firewall/VLAN cho phép |
| **P5 – ipvlan L3 return** | Truy cập endpoint với routes hai chiều | Connectivity thành công và đúng path upstream |
| **N6 – overlay encryption** | Review overlay settings và traffic proof trong lab | Không gán nhãn encrypted nếu data plane chưa cấu hình/xác minh |
| **N7 – Swarm ingress** | Liệt kê published ports ở mọi nodes được phép | Không có mở ingress ngoài network policy |
| **N8 – IPv6 egress bypass** | Dual-stack test tới endpoint IPv6 không được duyệt | Bị chặn tại policy IPv6 mong muốn |
| **N9 – Docker socket** | Review volumes/mounts/privileges trong Compose/IaC | Không mount socket vào workload không cần |
| **N10 – DNS trust** | Test alias/service DNS đúng network, TLS identity đúng | Service discovery hoạt động, app không tin DNS như auth |
| **O1 – drift detection** | Thay network membership trong test pipeline có quyền | Có audit/alert với actor, network cũ/mới |
| **F1 – network failure** | Trong staging làm upstream DNS/gateway unavailable | Ứng dụng fail theo policy, không tự đổi host mode |

### 23.1. Các tiêu chí chấp nhận

Một lựa chọn Docker network được coi là đáp ứng thiết kế khi:

- **Network mode và driver được ghi rõ**, tương thích Engine/OS/rootless/Desktop thực tế.
- **Ingress ports** có owner và nằm sau các điểm WAF/LB/firewall được phê duyệt; không có host-published admin/DB ports trái ý định.
- **Service-to-service reachability** chỉ đúng các luồng nghiệp vụ, có authorization và mTLS/TLS khi cần.
- **Egress** bị kiểm soát ở đúng điểm, gồm DNS, IPv4/IPv6, internal/external services và đường multi-homed.
- Các đường **macvlan/ipvlan/overlay** được xác minh trên hạ tầng thật, có return paths/underlay security.
- Người dùng workload không có khả năng tự đổi trust boundary thông qua **Docker socket, privileged hoặc host networking** nếu không được cấp quyền.
- Có **positive và negative test** chứng minh policy, không chỉ “ping không được”.
- Có **telemetry, owner, versioned config và rollback plan**.

## 24. Lộ trình triển khai và thay đổi network mode

### 24.1. Trước thay đổi

1. **Inventory:** container/service, host, Engine version, Docker Desktop/rootless, network mode/driver, IPAM, published ports, mounts, capabilities.
2. **Flow matrix:** user, proxy, API, DB, monitoring, DNS, registry, external API và management traffic.
3. **Trust boundaries:** phân định public ingress, internal east–west, management plane, egress và multi-node/overlay.
4. **Policy mapping:** control ở Docker network, host firewall, cloud SG, API identity, mTLS hay NVA nào thực thi từng luồng.
5. **Compatibility:** kiểm tra macvlan/ipvlan host/vSwitch, overlay node setup, Compose validation và app listeners.
6. **Rollback:** nơi lưu cấu hình trước đổi, ai có quyền restore, đường quản trị out-of-band.

### 24.2. Thực hiện trong staging/canary

- Tạo network với **driver/IPAM/options** phù hợp và **không overlap** những networks hiện có.
- Gắn dịch vụ pilot, kiểm tra DNS/route/ports, user và device authentication.
- Xác minh **tất cả luồng cần thiết** và **các luồng phải bị deny**, gồm host-side và Internet-side tests.
- Đo latency, throughput, MTU, CPU, packet drops, firewall/session logs và storage/database connectivity.
- Thử restart/update, host reboot hoặc failover theo phạm vi staging.
- Không quên **IPv6, Docker API access, privileged/capabilities** trong policy review.

### 24.3. Sau triển khai

- So **desired Compose/IaC** với runtime Docker network inspect và cloud/host firewall.
- Đối chiếu port inventory mới với danh sách endpoint được công bố.
- Kiểm tra logs chứng minh flow đi đúng WAF/ingress/egress; nếu phải overlay encryption, xác minh nó **đã được bật và hoạt động**.
- Ghi **incident/change ID, owner, hiệu quả, false positives, residual risks**.
- Thiết lập cảnh báo khi thêm **host networking, new published port, network joins và Docker socket mounts** ngoài policy.

## 25. Những nhầm lẫn thường gặp

1. **“EXPOSE làm cổng container public.”** EXPOSE chỉ là metadata; host publish và network routes quyết định exposure.
2. **“Không có -p nghĩa không ai truy cập được container.”** Các peers cùng network có thể gọi trực tiếp; macvlan có IP LAN riêng; host có thể có đường.
3. **“Bridge là firewall chặn mọi container khác.”** Containers cùng bridge có thể kết nối nhiều listeners với nhau theo policy.
4. **“User-defined bridge cho mỗi container một danh tính được xác thực.”** Docker DNS name/IP không thay TLS/mTLS hoặc application authorization.
5. **“Tách network tự động cấm mọi đường vòng.”** Multi-homed containers, published ports, host access và Docker daemon quyền cao có thể tạo đường khác.
6. **“Host mode chỉ làm nhanh hơn, không đổi security.”** Nó làm mất network namespace riêng và thay đổi listener/loopback semantics.
7. **“Host mode cần -p để publish port.”** Với host namespace, cơ chế host-port NAT mapping không như bridge và publish thường bị bỏ qua/không phù hợp.
8. **“localhost bên trong container bridge là localhost của host.”** Đó là loopback của container namespace.
9. **“None là air gap hoàn chỉnh.”** Host mounts, sockets, privileged access và orchestrator channels vẫn có thể tồn tại.
10. **“network=container:... cho sidecar một IP/port namespace riêng.”** Nó chia sẻ network namespace với target.
11. **“Macvlan giống bridge nhưng có IP đẹp hơn.”** Nó thay đổi L2 exposure và assumptions về host firewall/NAT.
12. **“Host luôn truy cập được macvlan container bằng parent NIC.”** Linux macvlan có host reachability restrictions phổ biến.
13. **“Ipvlan L3 tự động quảng bá route tới toàn bộ LAN.”** Upstream router cần route/next hop hợp lệ.
14. **“Overlay là encrypted tự động.”** Encapsulation và mã hóa data plane là hai chuyện khác.
15. **“Swarm service port chỉ mở trên node chạy container.”** Ingress routing mesh có thể mở trên nhiều nodes.
16. **“Một TCP connection tương đương một HTTP request.”** H2/H3 multiplex và application request concurrency vẫn cần kiểm soát.
17. **“Docker networking trên Linux, Windows/macOS Desktop và rootless giống hệt.”** VM/user-mode networking và driver support khác nhau.
18. **“Docker engine đã có firewall nên host UFW luôn chặn được -p.”** Docker-managed NAT/filter chains có thể thay đổi điểm thực thi.
19. **“DOCKER-USER xử lý toàn bộ network modes.”** Hook đó không mặc định thấy host mode, macvlan, local host traffic hoặc nft backend như iptables.
20. **“Đã chặn IPv4 thì IPv6 cũng chặn.”** Dual-stack cần route/firewall/capture riêng.
21. **“internal: true chặn mọi kiểu thoát dữ liệu.”** Multi-homed, mounts, host sockets và ứng dụng proxy có thể tạo kênh khác.
22. **“Container có network riêng thì Docker socket không nguy hiểm.”** Docker daemon control có thể phá chính network isolation.
23. **“Không ping được DB chứng minh DB port bị chặn.”** ICMP và TCP có policy khác, cần kiểm tra đúng service/port.
24. **“Port công khai chắc chắn đã bị khai thác.”** Exposure là rủi ro cần xử lý; truy cập dữ liệu phải dựa trên auth/app evidence.
25. **“Nâng Docker privileges sẽ sửa mọi lỗi mạng.”** Điều đó có thể tăng nguy cơ host compromise mà chưa giải quyết DNS/route.
26. **“Giữ mọi container trên một mạng lớn giúp dễ vận hành nên an toàn.”** Dễ tạo lateral movement và không rõ owner/trust boundary.

## 26. Bài tập vận dụng và gợi ý

### Bài 1 — EXPOSE và publish

Dockerfile của API có **EXPOSE 8080**, nhưng Compose không khai **ports**. API nằm trong user-defined network cùng proxy. Người dùng Internet có tự truy cập được API qua host:8080 không? Proxy có gọi API:8080 được không?

**Gợi ý:** EXPOSE không tự publish host port. Proxy cùng network có thể gọi listener API phù hợp bằng network DNS/IP nếu các policy cho phép. Internet→host:8080 cần một đường ingress được cấu hình và cho phép riêng.

### Bài 2 — Host mode thay đổi gì?

Một agent chạy bridge, metrics listener chỉ bind **127.0.0.1:9100** trong container. Team chuyển sang host mode. Địa chỉ loopback đó bây giờ thuộc namespace nào và cần kiểm tra điều gì?

**Gợi ý:** host network namespace. Cần rà soát host-local services, bind conflicts, host firewall, khả năng agent đọc/gửi traffic theo quyền và mô hình metrics authentication; không dùng -p với kỳ vọng như bridge.

### Bài 3 — None có đủ để chạy mã không đáng tin?

Một worker chạy **--network none** nhưng được mount **/var/run/docker.sock** và một thư mục host chứa secret. Có thể tuyên bố nó “offline an toàn” không?

**Gợi ý:** không. Docker socket cho quyền điều khiển daemon, host mount có thể tạo kênh truy xuất dữ liệu và ảnh hưởng host. Cần tách quyền control plane/volumes và áp sandbox controls ngoài network namespace.

### Bài 4 — Macvlan và host firewall

Ứng dụng đổi từ bridge có host publish TCP 8443 sang macvlan có IP riêng trên VLAN. Host firewall trước đây chặn cổng 8443 theo Docker bridge path. Vì sao phải review lại?

**Gợi ý:** macvlan traffic có đường L2/ACL khác. Cần kiểm tra switch/VLAN/router firewall, IPAM, source/dest reachability, host–container limitations và sensor coverage; không mặc định host Docker NAT rules vẫn kiểm soát luồng.

### Bài 5 — Ipvlan L3 kết nối một chiều

Container có IP thuộc subnet riêng và default route được cấu hình, có thể gửi packet ra router, nhưng LAN peer không gửi response về được. Nguyên nhân gì cần kiểm tra?

**Gợi ý:** upstream router thiếu route return tới container CIDR qua host/parent interface, firewall và L3 policy không phù hợp, hoặc IP overlap. Cần kiểm tra **hai chiều**, không chỉ route tại container.

### Bài 6 — Overlay giữa hai nodes

Hai services chạy ở hai Docker hosts khác nhau, cùng overlay. Cluster manager dùng kết nối bảo mật; application traffic giữa nodes đã được bảo vệ confidentiality theo yêu cầu chưa?

**Gợi ý:** chưa thể kết luận. Cần kiểm tra overlay encryption data plane option, underlay ACL, khả năng tương thích, service-level mTLS và ingress publish mode; control plane protection không đủ.

### Bài 7 — Multi-homed API và phân đoạn

Proxy ở **front_net + app_net**, API ở **app_net + data_net**, DB chỉ ở **data_net**. Proxy không có direct DB connection. Thiết kế đã loại bỏ hoàn toàn rủi ro proxy làm lộ dữ liệu DB chưa?

**Gợi ý:** chưa. Proxy có thể khai thác API logic hoặc gọi endpoint quyền rộng; API có thể trở thành pivot. Cần API authentication/authorization, DB role tối thiểu, mTLS khi phù hợp, rate limits, WAF, logging và hạn chế quyền container.

### Bài 8 — IPv6 ngoài ý muốn

Host có IPv4 firewall chặn TCP 9090 từ Internet. Một container host-network bind wildcard trên IPv6 và mạng có route IPv6. Mức bảo vệ đã đủ chưa?

**Gợi ý:** phải xác minh listener là IPv4/IPv6 hay dual-stack, cloud SG/host IPv6 firewall, ::/0, DNS AAAA và external test IPv6 trong phạm vi được phép.

### Bài 9 — Thiết kế threat → control → evidence

Bạn có **Docker Linux host, reverse proxy, API, DB, metrics agent và một worker offline**. Hãy lập bảng:

1. Service nào nên dùng **user-defined bridge, host, none hoặc network namespace sharing**?
2. Những network memberships và host-published ports nào thực sự cần?
3. Có cần **macvlan/ipvlan/overlay** không, hay chúng chỉ tăng complexity?
4. Control nào xác nhận **Internet→DB denied, proxy→API allowed, API→DB allowed, DB→Internet hạn chế**?
5. Docker daemon/socket, rootless, capabilities, host firewall và IPv6 được bảo vệ thế nào?
6. Những **read-only commands, host/cloud flow logs và positive/negative tests** nào chứng minh quyết định?

**Gợi ý:** bắt đầu từ **luồng nghiệp vụ và trust boundaries**, không bắt đầu từ network driver yêu thích; ánh xạ từng luồng tới policy thực thi và evidence.

## 27. Checklist quyết định network mode trước deployment

| Câu hỏi | Evidence mong đợi |
| --- | --- |
| Container chạy trên Linux Engine, Docker Desktop hay rootless? | OS/Engine version, rootless status, driver support |
| Có cần host namespace không hay bridge là đủ? | Requirement được phê duyệt, alternatives đã đánh giá |
| Có cần LAN IP/MAC riêng hoặc multi-host overlay không? | L2/L3/Swarm requirements, network topology |
| Những Docker networks nào mỗi service được join? | Compose/IaC, docker network inspect |
| Có container multi-homed tạo đường vòng không? | Network membership matrix và egress tests |
| Những ports nào được publish trên host, bind IP nào? | docker port, host listeners, IPv4/IPv6 mapping |
| Có cổng DB/admin/metrics ngoài vùng được duyệt không? | External negative tests và SG/firewall evidence |
| DNS/service aliases và upstream resolvers đúng? | Resolver state, name resolution, TLS identity |
| Docker bridge isolation đang dựa trên control nào? | Firewall/backend rules và inter-network tests |
| Host firewall/DOCKER-USER/nftables có đúng hook cho mode? | Ruleset, actual packet path, test result |
| Macvlan/ipvlan có IPAM, VLAN/route và return path hợp lệ? | Switch/vSwitch config và end-to-end connectivity |
| Overlay có cần encryption và mTLS không? | Driver option audit, data-plane validation, service identity |
| Swarm ingress có mở trên những nodes không mong muốn? | Published service ports và node firewalls |
| Có egress restriction và DNS/IPv6 policy không? | Routes, flow logs, negative tests |
| Container có privileged, NET_ADMIN, host mounts hoặc Docker socket? | Runtime/Compose security review |
| Đã kiểm thử failure, restart và drift chưa? | Staging/canary validation, monitoring, change history |
| Có owner và rollback plan không? | Runbook, ticket, approval, accountable team |

## 28. Tổng kết

**Docker network mode và rủi ro lựa chọn** phải được hiểu theo **đường đi thật của traffic và ranh giới tin cậy**, không chỉ theo tên driver. **User-defined bridge** thường là điểm khởi đầu hợp lý cho ứng dụng nhiều containers trên một Linux host, nhưng cần tách mạng theo luồng nghiệp vụ và không coi DNS hay network membership là xác thực. **Host** làm giảm network namespace isolation; **none** cắt kết nối IP thông thường nhưng không thay sandboxing toàn diện; **container:ID** tạo shared loopback/port namespace cho sidecar. **Macvlan/ipvlan** đưa workload vào topology L2/L3 đặc thù, còn **overlay** giúp kết nối đa host nhưng yêu cầu kiểm soát underlay, encryption, membership và published service ports.

Để thiết kế **SECURITY_NETWORK_SECURITY** an toàn, phải kết hợp **Docker mode/driver, port publishing, IPv4/IPv6 routing, DNS, host/cloud firewall, WAF/API authentication, TLS/mTLS, daemon authorization, workload hardening và observability**. Đặc biệt, **EXPOSE không phải publish**, **internal network không phải air gap**, **NAT không phải firewall**, và **Docker socket có thể phá giả định cô lập mạng** nếu được cấp cho workload không đáng tin.

Một quyết định network mode chỉ được xem là đã kiểm chứng khi **dịch vụ hợp lệ hoạt động qua đường đã phê duyệt**, **luồng trái quyền bị chặn ở đúng điểm enforcement**, **không có port/route/IPv6/overlay bypass ngoài ý muốn** và **có đủ log, runtime inspection, positive/negative tests, owner cùng phương án rollback để duy trì bảo mật khi hệ thống thay đổi**.
