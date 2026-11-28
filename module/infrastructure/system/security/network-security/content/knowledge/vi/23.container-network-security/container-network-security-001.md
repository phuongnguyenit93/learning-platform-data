# Network namespace và interface trong container: Nền tảng cô lập và bảo mật mạng

## 1. Network namespace giải quyết bài toán gì?

Một máy Linux có thể chạy hàng chục hoặc hàng trăm container cùng lúc. Nếu tất cả ứng dụng cùng nhìn thấy toàn bộ interface, bảng route, địa chỉ IP và socket như một hệ điều hành duy nhất, việc vận hành và cách ly các dịch vụ sẽ khó kiểm soát. **Network namespace (netns)** là cơ chế của Linux kernel cung cấp những **ngữ cảnh mạng riêng biệt**, để các tiến trình trong các ngữ cảnh khác nhau có thể có network interfaces, địa chỉ, routes, socket và các trạng thái mạng riêng.

Khi một container bình thường được cấp một netns riêng, lệnh `ip addr` bên trong nó thường chỉ hiện những interface thuộc **netns của container**, chẳng hạn `lo` và `eth0`; nó không tự nhìn thấy mọi interface của host. Container có thể dùng `127.0.0.1` mà không đụng trực tiếp tới một container ở netns khác. Hai container có thể cùng lắng nghe TCP/8080 trong **hai netns riêng** mà không tranh chấp cùng một cổng ở **host network namespace**.

Tuy nhiên, **network namespace không phải tường lửa, cũng không phải máy ảo riêng kernel**. Các netns vẫn dùng chung kernel Linux và có thể được kết nối thông qua **virtual Ethernet pairs (veth), Linux bridge, routing, NAT, overlay hoặc network driver khác**. Nếu mạng giữa chúng cho phép kết nối, dữ liệu vẫn đi qua được. Hệ thống cần thêm firewall, policy, identity và kiểm soát quyền để đạt mục tiêu bảo mật.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **network namespace**, sự cô lập network stack và sự khác biệt với PID/user/mount namespace.
2. Hiểu cách hoạt động của **loopback, `eth0`, veth pair, Linux bridge, virtual NIC, route, DNS và NAT**.
3. Phân biệt networking modes của container: **bridge, host, none, macvlan, ipvlan, overlay và rootless** theo nhu cầu.
4. Giải thích vì sao **các container trong cùng một Kubernetes Pod thường dùng chung network namespace**, còn Pod khác có không gian mạng riêng theo mô hình chuẩn.
5. Hiểu trách nhiệm của CNI, IPAM, Kubernetes Service và các data plane (iptables, nftables, IPVS, eBPF khi được dùng).
6. Phân tích mối nguy khi mở host ports, dùng `hostNetwork`, cấp `CAP_NET_ADMIN`, sai NetworkPolicy hoặc hiểu nhầm `localhost`.
7. Dùng các lệnh **quan sát chỉ đọc**, xây dựng một lab netns cô lập và kiểm thử luồng được phép/bị cấm.

Trong module **SECURITY_NETWORK_SECURITY**, kiến thức này liên kết với **phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, TLS, DNS, cloud networking và kiến trúc zero trust**. Container networking là một lớp hạ tầng quan trọng, không phải vật thay thế cho các lớp trên.

> **Phạm vi an toàn:** lab dùng tên và IP ví dụ riêng, chỉ chạy trên VM Linux do người học sở hữu hoặc môi trường được cấp phép, không chạy các lệnh tạo/xóa namespace, đổi routes, firewall hoặc Docker networking trên node production. Khi quan sát môi trường thực, ưu tiên lệnh chỉ đọc và hạn chế xuất log chứa thông tin nội bộ.

## 2. Mỗi network namespace chứa những gì?

Linux network namespace cô lập nhiều đối tượng của **network stack**. Những nhóm đối tượng đáng chú ý:

| Đối tượng | Bên trong netns | Tác động thực tế |
|---|---|---|
| Network devices/interfaces | Mỗi netns sở hữu những interface được đặt vào đó | `eth0` của container A không phải `eth0` của container B |
| IPv4/IPv6 addresses | Gắn với interface theo netns | Các container có thể dùng những dải mạng khác nhau |
| Routing tables / policy routing | Ngữ cảnh route riêng | Default gateway khác nhau, dù chạy cùng host |
| Loopback interface | Có `lo` riêng | `127.0.0.1` và `::1` gắn với netns đang chạy |
| Sockets và port binding | Socket nằm trong ngữ cảnh mạng của tiến trình | Hai netns có thể cùng bind một cổng mà không xung đột trực tiếp |
| Neighbor/ARP/ND state | Theo interface và phạm vi netns | Reachability layer 2/layer 3 phụ thuộc link riêng |
| Netfilter/nftables state | Các bảng và trạng thái mạng phù hợp theo netns/driver | Không phải mọi rule nhìn thấy trong container đều là policy ở host |
| Network-specific sysctls | Nhiều tham số gắn với network namespace | Không phải **mọi** sysctl của kernel đều namespaced |
| Một số cấu hình liên quan protocol stack | Port ranges, thiết lập socket, thông tin mạng phù hợp | Cần phân biệt với file cấu hình DNS trong filesystem |

**Không phải tất cả trạng thái máy đều được namespaced.** Kernel, tài nguyên phần cứng và nhiều thành phần quản trị vẫn dùng chung. Các cơ chế cô lập khác như **user namespace, mount namespace, PID namespace, cgroups, seccomp và LSM** bổ sung bảo vệ; chỉ sử dụng netns không tạo ranh giới bảo mật tương đương một VM độc lập.

### 2.1. Netns của host và container

~~~mermaid
flowchart TB
    subgraph NODE["Một Linux host — kernel dùng chung"]
        subgraph H["Host network namespace"]
            EN["Physical NIC / ens3"]
            BR["Bridge hoặc routing"]
            FW["Host firewall / NAT"]
        end
        subgraph C1["Container A netns"]
            LA["lo"]
            EA["eth0 / 10.80.0.2"]
            APP1["Process A :8080"]
        end
        subgraph C2["Container B netns"]
            LB["lo"]
            EB["eth0 / 10.80.0.3"]
            APP2["Process B :8080"]
        end
        EA <-->|"veth pair A"| BR
        EB <-->|"veth pair B"| BR
        BR --> FW
        FW --> EN
    end
~~~

Đây là **một mô hình bridge networking thường gặp**, không phải cách mọi runtime hoặc CNI bắt buộc triển khai. Container có thể dùng host networking, rootless userspace networking, macvlan, SR-IOV hoặc overlay; lúc đó vị trí bridge/veth và đường dữ liệu có thể khác.

### 2.2. Namespace identity là thuộc tính kernel, không phải tên `docker0`

Một netns có thể có **identity qua namespace inode** được hiển thị bằng `/proc/<pid>/ns/net`, ví dụ `net:[4026532xxx]`. Hai process cùng netns có cùng identity namespace theo cách quan sát phù hợp. Tên `container-name`, tên interface `eth0` hoặc Linux bridge `docker0` **không phải định danh bất biến của namespace**.

Các namespace được tạo bằng `ip netns add` thường có **tên do administrator đặt**; container runtime thường tạo netns theo cách quản lý riêng và có thể không xuất hiện trong `ip netns list`. Không dùng danh sách named namespaces để suy ra toàn bộ netns trên một host.

## 3. Loopback và khái niệm localhost trong container

**Loopback interface (`lo`)** gắn với network namespace đang chạy. Hai địa chỉ quen thuộc:

- IPv4: `127.0.0.1` (thuộc dải loopback `127.0.0.0/8`).
- IPv6: `::1`.

Nếu container A và B ở **hai netns riêng**, một service chỉ bind `127.0.0.1:8080` trong A thông thường **không thể được B truy cập trực tiếp bằng `127.0.0.1:8080`**. B sẽ gọi loopback của chính B. Muốn B gọi A qua mạng, dịch vụ A cần lắng nghe trên địa chỉ/interface phù hợp, có kết nối mạng giữa hai netns và được phép theo firewall/policy.

### 3.1. Bind `127.0.0.1` và bind `0.0.0.0`

~~~text
Container A netns:
  lo      127.0.0.1
  eth0    10.80.0.2

Application listens at 127.0.0.1:8080:
  A's own processes -> can connect via localhost
  B's network connection to 10.80.0.2:8080 -> normally not served

Application listens at 0.0.0.0:8080:
  A's own processes -> can connect
  B -> 10.80.0.2:8080 -> may connect if route + policy permit
  Internet -> A -> NOT automatically accessible
~~~

`0.0.0.0` khi dùng trong socket bind là wildcard **trong chính netns**, không có nghĩa ứng dụng được mở trực tiếp ra Internet. Public exposure còn phụ thuộc published ports, route, host firewall, cloud security group và policy.

### 3.2. `localhost` không luôn trỏ về host vật lý

Khi vào shell container và chạy `curl http://localhost:8080`, bạn đang truy cập service trong **netns của tiến trình shell**. Nếu host có service tại `127.0.0.1:8080`, container bridge bình thường không tự gọi được service đó qua `localhost`.

**Đường truy cập host** tùy runtime/OS: gateway của bridge, host-specific DNS names, host network mode hoặc cấu hình bridge/route riêng. Không hardcode `127.0.0.1` như “địa chỉ máy host” bên trong container.

### 3.3. Trường hợp ngoại lệ quan trọng: containers cùng Kubernetes Pod

Trong một Kubernetes Pod chuẩn, các application containers thường **chia sẻ một network namespace**; do đó:

- Chúng nhìn thấy cùng **Pod IP** và cùng tập interface được chia sẻ.
- Một container bind `127.0.0.1:8080`, container còn lại trong Pod có thể gọi `localhost:8080`.
- Chúng **không thể cùng bind trùng địa chỉ/cổng/protocol** nếu socket conflict trong shared netns.
- Tên Kubernetes namespace (`metadata.namespace`) dùng để tổ chức API resources và policies, **không phải** Linux network namespace.

Pod có `hostNetwork: true` là một trường hợp khác: Pod sử dụng network namespace của node theo khả năng môi trường, kéo theo rủi ro và port collisions riêng. Sẽ phân tích ở phần Kubernetes.

## 4. Veth pair: “dây Ethernet ảo” nối giữa các namespace

Một **veth pair** gồm hai đầu interface ảo liên kết với nhau. Frame đi vào một đầu có thể xuất hiện ở đầu kia; hai đầu có thể nằm trong **hai network namespaces khác nhau**. Đây là thành phần cốt lõi của nhiều mô hình container bridge networking.

~~~mermaid
flowchart LR
    subgraph N1["Netns RED"]
        R["v-red / 10.200.0.1"]
    end
    subgraph N2["Netns BLUE"]
        B["v-blue / 10.200.0.2"]
    end
    R <-->|"veth peer — L2 link"| B
~~~

Veth **không có sẵn bảo vệ mật mã**. Nó là một cơ chế data plane cục bộ. Nếu hai đầu thuộc hai netns và route/firewall cho phép, hai bên có thể trao đổi. Nếu cần chia sẻ một physical uplink cho nhiều container, một đầu veth thường gắn vào **Linux bridge hoặc routing datapath ở host**.

### 4.1. Interface names không phải địa chỉ bảo mật

`eth0` thường là tên interface trong container; đầu còn lại có thể mang tên `veth...` trên host. Tên có thể thay đổi khi container restart/recreate. **ifindex** là chỉ số giao diện trong phạm vi netns; chỉ dựa vào tên hoặc ifindex không đủ chứng minh một endpoint tin cậy qua vòng đời container.

Khi quan sát mapping, kết hợp **container/pod identity, PID/netns inode, veth peer data, IPAM, bridge membership và CNI logs**, chứ không dùng mỗi một địa chỉ MAC hay tên `eth0`.

### 4.2. Linux bridge làm gì?

Một **Linux bridge** hoạt động như switch ảo ở tầng 2 cho những ports gắn vào. Nó có thể chuyển frame giữa các veth peers và uplink theo chính sách kernel/bridge. Với nhiều container trên cùng bridge, việc chúng có thể liên lạc trực tiếp tùy link state, VLAN/filtering, firewall và runtime configuration.

~~~mermaid
flowchart TB
    C1["Container A: eth0"] <-->|"veth A"| BR["Host Linux bridge"]
    C2["Container B: eth0"] <-->|"veth B"| BR
    C3["Container C: eth0"] <-->|"veth C"| BR
    BR --> RT["Host routing / netfilter"]
    RT --> NIC["Physical interface"]
~~~

Không được đồng nhất bridge networking với **container isolation**: cùng một Docker bridge thường có kết nối giữa những container được gắn trên bridge đó theo network configuration, nếu không có policy chặn. Container ở các bridge khác nhau vẫn có thể được kết nối qua host routing hoặc published services tùy cấu hình.

## 5. Đường đi một gói từ container ra mạng ngoài

Ví dụ mô hình Docker bridge IPv4 trên Linux host (minh họa, không mô tả mọi cấu hình):

~~~text
Container A
  process opens TCP connection to 203.0.113.80:443
       |
       v
  eth0 / 10.80.0.2
       |
       v
  veth peer -> Linux bridge
       |
       v
  Host routing + forwarding/filtering
       |
       v
  SNAT/MASQUERADE if configured
       |
       v
  Host physical NIC -> external network
~~~

### 5.1. Địa chỉ và default gateway

Container cần một đường tới destination. Trong trường hợp có bridge network, nó thường có IP trong subnet riêng, cùng một default route trỏ về gateway của mạng container, ví dụ:

~~~text
Container eth0: 10.80.0.2/24
Default gateway: 10.80.0.1
Destination: 203.0.113.80

Route lookup:
  10.80.0.0/24 -> eth0
  0.0.0.0/0    -> via 10.80.0.1 dev eth0
~~~

Không phải mọi container đều có default route; chế độ `none`, những network policies đặc biệt hoặc một Pod được cấu hình thêm interfaces có thể khác.

### 5.2. NAT và firewall ở những điểm nào?

Trong mô hình rootful Docker bridge truyền thống, host có thể thực hiện **SNAT/MASQUERADE** cho outbound và **DNAT hoặc cơ chế proxy tương ứng** cho published inbound ports. Những rules này được runtime/công cụ mạng thiết lập ở phạm vi phù hợp, có thể dùng iptables hoặc nftables backend.

**Không suy rằng NAT tự ngăn mọi inbound hoặc tự bảo vệ ứng dụng.** Một container có published port vẫn có thể nhận request từ bên ngoài qua host; các port khác có thể bị chặn hoặc chỉ truy cập nội bộ tùy bridge/rules. Khi một bridge container gọi Internet thành công, điều đó chỉ chứng minh **egress**, không chứng minh nó cần được cấp full outbound.

### 5.3. Kết nối east–west và north–south

| Loại traffic | Ví dụ | Điểm cần kiểm soát |
|---|---|---|
| **East–west** | Container A → container B hoặc Pod → Pod | Microsegmentation, NetworkPolicy, service identity, TLS/mTLS |
| **North–south inbound** | Internet → LB/ingress → Pod | Firewall, WAF, ingress, TLS, authentication |
| **North–south outbound** | Pod/container → API bên ngoài | Egress policy, DNS, NAT/proxy, firewall, identity |
| **Host↔container** | Node agent/host process → container network | Node firewall, namespaces, runtime policy |

Việc **tách netns** là nền móng kỹ thuật để tạo network interfaces/đường riêng; quyết định allow/deny vẫn cần các controls ở ranh giới chính xác.

## 6. Docker networking: bridge, host, none và các lựa chọn khác

Docker cung cấp những **network drivers/modes** với cơ chế kết nối khác nhau. Người vận hành phải hiểu **chế độ đã được chọn**, thay vì suy rằng mọi container Docker đều có `docker0` và một `eth0` nối qua veth.

| Chế độ | Cấu trúc điển hình | Mục đích | Rủi ro hoặc giới hạn |
|---|---|---|---|
| **bridge** | Netns riêng, veth và bridge của host trong mô hình Linux rootful | Ứng dụng độc lập trên một host | Kết nối giữa peers và published ports cần kiểm soát |
| **host** | Container dùng **network namespace của host** | Một số tác vụ cần trực tiếp host networking hoặc hiệu năng/đặc tính cụ thể | Giảm cách ly network, cổng có thể xung đột với host |
| **none** | Container có netns nhưng không có external network interface được cấp theo cách thông thường; loopback có thể sử dụng | Job không cần mạng, xử lý dữ liệu local | Không thay thế cô lập process/filesystem/capabilities |
| **overlay** | Kết nối các endpoint qua nhiều host bằng dataplane overlay phù hợp | Multi-host service networks | Đường underlay, tunnel, encryption và policy cần được review |
| **macvlan** | Endpoint có interface với MAC riêng trên mạng vật lý/logical tương ứng | Tích hợp một số mạng L2 hiện hữu | Có thể tăng L2 exposure, yêu cầu kiểm soát switch/uplink |
| **ipvlan** | Chia sẻ đặc điểm interface parent, xử lý L2/L3 theo mode | Mô hình host-network integration khác macvlan | Route, IPAM và isolation tùy mode |
| **rootless networking** | Docker/runtime chạy không cần root với backend như userspace stack theo phiên bản | Giảm đặc quyền daemon/runtime | Dataplane, source IP, port handling và performance khác rootful bridge |

**Không có một mức bảo mật xếp hạng tuyệt đối cho các chế độ.** Cần xem ai có quyền sử dụng, topology, chính sách firewall, danh tính workload, TLS, quyền kernel, observability và nhu cầu ứng dụng.

### 6.1. Docker default bridge và user-defined bridge

Trong mô hình Linux rootful truyền thống, Docker có thể cung cấp mạng bridge mặc định. **User-defined bridge** thường có những tính năng discovery/name resolution và vận hành container-to-container tiện hơn, nhưng vẫn phải xét firewall và việc container được nối vào mạng nào.

Một container nối vào hai Docker networks có thể trở thành **đầu mối liên thông** nếu ứng dụng hoặc tiến trình bên trong có quyền chuyển tiếp traffic. Phân đoạn theo nhiều bridge chỉ có ý nghĩa khi không có đường khác cho phép bypass, và khi runtime/host enforcement đúng.

### 6.2. Host networking phá vỡ giả định “localhost chỉ trong container”

Với `--network host` trên nền tảng hỗ trợ host networking theo ngữ nghĩa tương ứng, container **không có netns độc lập theo cùng cách bridge mode**. Nó nhìn thấy host network stack; cổng mà tiến trình bind có thể va chạm với ứng dụng trên host.

~~~text
Bridge mode:
  Container A localhost:8080 != Host localhost:8080

Host networking mode:
  Container process và host process chia sẻ network namespace
  Việc bind port chịu cùng không gian socket và network policy
~~~

Đây là lựa chọn nhạy cảm với security posture. Không dùng host networking chỉ để “sửa lỗi DNS/port forwarding” mà chưa xác định nguyên nhân thực.

### 6.3. `--network none` có phải sandbox hoàn chỉnh?

Không. `none` loại bỏ kết nối mạng thông thường do driver thiết lập, nhưng nếu tiến trình có quyền kernel cao, có mount filesystem nhạy cảm, socket Unix của host, host PID namespace hay những khả năng đặc quyền khác, nó vẫn có thể gây rủi ro. Một job không có networking vẫn cần **user namespace, capabilities tối thiểu, filesystem permissions, seccomp, LSM, secrets protection** và giới hạn tài nguyên.

### 6.4. Rootless khác rootful

Trong **rootless Docker/container runtime**, tiến trình không chạy với đặc quyền root host như Docker daemon rootful truyền thống. Một số môi trường sử dụng **slirp4netns, pasta hoặc các backend khác** để kết nối mạng, nên không nên kỳ vọng `docker0`, iptables rules và đường packet giống hệt rootful Docker.

Khi xử lý sự cố rootless, phải xem **runtime version, host OS, network backend, published port behavior và khả năng hiển thị địa chỉ client**; không kết luận chỉ từ sơ đồ veth/bridge của rootful.

## 7. Published ports: cổng trong container và cổng của host khác nhau

Một application trong Docker container bridge có thể lắng nghe TCP/80 ở IP container, nhưng **Internet không tự truy cập được chỉ vì nó listen trên `0.0.0.0:80` trong netns**. Khi publish port, runtime tạo đường kết nối host→container tương ứng (thông qua NAT/proxy hoặc cơ chế khác).

Ví dụ cú pháp Docker trong lab:

~~~bash
# Minh họa cú pháp; chỉ chạy trên VM lab và với image đã được duyệt.
# Tạo container và có thể tải image; không phải lệnh chỉ đọc.
docker run --rm --name web-lab \
  --publish 127.0.0.1:18080:80 \
  nginx:alpine
~~~

Trong cấu hình phổ biến, `127.0.0.1:18080:80` yêu cầu bind host listener ở loopback, còn `-p 18080:80` khi không chỉ định host IP có thể publish lên các host interfaces theo defaults/runtime. **Không coi loopback publish là lớp bảo vệ duy nhất:** cần kiểm tra phiên bản Docker, host firewall, network path và cách runtime thực thi port mapping; một số phiên bản/thiết kế có đặc tính reachability đặc biệt.

### 7.1. Đọc ký hiệu port mapping

~~~text
HOST_BIND_ADDRESS : HOST_PORT : CONTAINER_PORT

127.0.0.1 : 18080 : 80

Client (theo đường được phép) -> Host 127.0.0.1:18080
Runtime port mapping        -> Container IP:80
Application listens         -> Container port 80
~~~

Không nhầm `EXPOSE 80` trong Dockerfile với `--publish`: `EXPOSE` thường là **metadata tài liệu cho port**, không tự mở cổng host ra ngoài.

### 7.2. Một số lỗi cấu hình

| Triệu chứng | Nguyên nhân thường gặp | Cần xác minh |
|---|---|---|
| Host `curl localhost:18080` lỗi | Container không chạy, app không listen, mapping sai | `docker ps`, `docker port`, app logs |
| Host connect được nhưng máy ngoài không | Chỉ bind `127.0.0.1`, host firewall, cloud SG hoặc route | Host bind address, IPv4/IPv6, ACL |
| Cổng host không bind được | Host app/container khác đã dùng cổng | `ss -lnt` trên host, published mapping |
| Container nghe 127.0.0.1 nhưng publish thất bại | App chỉ bind loopback **bên trong netns**, mapping tới IP khác | Listener trong netns, container IP và runtime path |
| Thêm `-p` khi dùng host network không có hiệu lực theo kỳ vọng | Host networking không thực hiện mapping kiểu bridge | Runtime mode và port bindings |
| Kết nối được qua public IP ngoài dự kiến | `-p` không chỉ định host IP, host firewall/SG quá mở | Actual listen/mapping, firewall, exposure scan được phép |

**Bài học:** kiểm tra đồng thời **network namespace, socket bind, published mapping và firewall**. Một thuộc tính đơn lẻ không đủ kết luận cổng đã hoặc chưa public.

## 8. Linux namespace lifecycle: ai “sở hữu” network stack?

### 8.1. Process tham gia netns như thế nào?

Kernel gắn mỗi thread/process với những namespace nhất định. Những syscall như `clone`, `unshare` và `setns` có thể tạo hoặc tham gia một network namespace khi đáp ứng permission/capability. Container runtime tổ chức việc đó cùng các namespace khác.

Không phải tên container làm namespace tồn tại; namespace có thể tồn tại khi còn **process/reference hoặc handle được giữ**. Tên trong `ip netns list` thường đến từ những namespace được bind ở vị trí quản lý của `iproute2`, không phải mọi anonymous netns do container runtime quản lý.

### 8.2. Interface khi netns bị xóa

Khi network namespace cuối cùng bị hủy, **veth interfaces** gắn trong đó sẽ được xử lý theo ngữ nghĩa kernel của pair (thường dẫn tới peer biến mất khi veth end bị hủy). Một số loại physical device có xử lý khác và có thể trở lại network namespace ban đầu. Trên container platform, CNI/runtime cần dọn **addresses, routes, device references, policies và IPAM allocations** phù hợp.

Nếu cleanup lỗi, có thể xảy ra stale rules, IPAM leak hoặc orphaned virtual interfaces. Không nên xóa thủ công interface trên production node chỉ vì tên của nó “giống veth cũ” mà chưa kiểm tra owner và runtime state.

### 8.3. Không nhầm network namespace với Kubernetes namespace

| Thuật ngữ | Layer | Ví dụ |
|---|---|---|
| **Linux network namespace** | Kernel network stack | Tách interfaces, routes, sockets |
| **Kubernetes namespace** | API resource scope | `team-a`, `production`, `kube-system` |
| **Docker network** | Runtime network abstraction | `bridge`, `app-net` |
| **Pod** | Kubernetes scheduling/lifecycle unit | Nhóm containers chia sẻ Pod networking |
| **Node** | Máy chạy workload | Kernel, CNI agents, interfaces |
| **VPC subnet** | Cloud network address segment | CIDR của subnet chứa node hoặc Pod IP theo CNI |

Một Kubernetes namespace có thể chứa nhiều Pods, mỗi Pod sở hữu netns riêng theo mô hình chuẩn. Ngược lại, nhiều containers trong cùng Pod dùng chung một netns, **dù chúng là các container khác nhau**.

## 9. Lab 1 — Tạo hai network namespaces nối bằng veth

Lab này minh họa trực tiếp cách netns và interface độc lập. **Chỉ chạy trên VM Linux lab riêng, có quyền sudo, không chạy trên node production/Kubernetes, và đảm bảo không có tài nguyên sẵn tên `lab-red-w3`, `lab-blue-w3`, `v-red-w3`, `v-blue-w3`.** Nó không sửa default route hoặc firewall host nhưng **tạo network resources trong kernel** và cần cleanup.

### 9.1. Topology và kỳ vọng

~~~mermaid
flowchart LR
    RED["netns lab-red-w3<br/>v-red-w3 10.200.0.1/30"] <-->|"veth pair"| BLUE["netns lab-blue-w3<br/>v-blue-w3 10.200.0.2/30"]
    RED -. "Không có default route được cấu hình" .-> OUT["Internet"]
~~~

Địa chỉ `10.200.0.0/30` chỉ dùng trong netns lab. Chọn prefix không xung đột với mạng đang có để tránh gây nhầm lẫn; trong lab này không kết nối các namespace với host bridge/uplink.

### 9.2. Tạo hai namespaces và pair

~~~bash
# Dùng duy nhất trên VM lab riêng; các lệnh này THAY ĐỔI network state.
sudo ip netns add lab-red-w3
sudo ip netns add lab-blue-w3

# Tạo cặp veth, sau đó đặt mỗi đầu vào một netns.
sudo ip link add v-red-w3 type veth peer name v-blue-w3
sudo ip link set v-red-w3 netns lab-red-w3
sudo ip link set v-blue-w3 netns lab-blue-w3

# Gán địa chỉ cho từng interface trong namespace tương ứng.
sudo ip -n lab-red-w3 address add 10.200.0.1/30 dev v-red-w3
sudo ip -n lab-blue-w3 address add 10.200.0.2/30 dev v-blue-w3

# Bật loopback và hai đầu veth.
sudo ip -n lab-red-w3 link set lo up
sudo ip -n lab-blue-w3 link set lo up
sudo ip -n lab-red-w3 link set v-red-w3 up
sudo ip -n lab-blue-w3 link set v-blue-w3 up
~~~

**Cơ chế an toàn:** hai netns có kết nối trực tiếp với nhau nhưng **không được gắn với host uplink, không có NAT, không có default Internet route** trong lab thiết kế. Điều này minh họa **network reachability bởi interface/route**, không chứng minh netns là một security sandbox mạnh khi tiến trình có quyền kernel cao.

### 9.3. Quan sát ở hai netns

~~~bash
# Các lệnh dưới đây chỉ đọc/quan sát trạng thái.
sudo ip -n lab-red-w3 -br addr
sudo ip -n lab-blue-w3 -br addr
sudo ip -n lab-red-w3 route
sudo ip -n lab-blue-w3 route

# ICMP qua veth pair: chỉ tạo 2 packet probes trong lab.
sudo ip netns exec lab-red-w3 ping -c 2 -W 1 10.200.0.2

# Thử loopback riêng, chỉ trong lab.
sudo ip netns exec lab-red-w3 ping -c 1 -W 1 127.0.0.1
~~~

**Kỳ vọng:** RED thấy `v-red-w3`, BLUE thấy `v-blue-w3`, chúng có kết nối trong subnet `/30`. RED không nhìn thấy `v-blue-w3` như interface của chính RED. Nếu ping thất bại, xem trạng thái links, addresses, netns và khả năng ICMP của kernel lab; không tự sửa iptables của host trước khi hiểu lỗi.

### 9.4. Thu dọn namespace lab

~~~bash
# Chỉ trên VM lab vừa tạo và đã xác minh không có tiến trình ứng dụng cần giữ.
# Không dùng lệnh này trên namespace của container production.
sudo ip netns pids lab-red-w3
sudo ip netns pids lab-blue-w3

# Khi không còn tiến trình cần bảo vệ trong các namespaces lab:
sudo ip netns del lab-red-w3
sudo ip netns del lab-blue-w3

# Xác minh tài nguyên lab đã được dọn.
ip netns list
~~~

Nếu namespace còn process/reference thì cần xử lý theo lifecycle, không dùng xóa cưỡng bức hoặc kill tùy tiện. Veth pair lab thường biến mất khi các đầu thuộc netns bị dọn theo kernel semantics; xác minh trên VM thay vì đoán.

### 9.5. Những kết luận người học cần ghi lại

- `lo` và `v-red-w3` thuộc RED, không phải interface của BLUE.
- Mỗi netns có routes riêng; chỉ những prefix có route phù hợp mới có đường đi.
- `127.0.0.1` là loopback của **process netns**, không đại diện cho mọi container trên host.
- Một veth pair có thể kết nối hai namespaces dù chúng vẫn **khác namespace**.
- Không thể từ lab này kết luận có firewall deny giữa hai namespaces; nếu test veth thành công thì chúng **đang reachable** theo đường đã tạo.

## 10. Quan sát read-only trên Docker host

### 10.1. Xem mode, IP và mạng container

~~~bash
# Chỉ thực hiện trên Docker host bạn có quyền quản trị.
docker ps
docker network ls
docker network inspect bridge

# Thay CONTAINER_NAME bằng tên đã được cấp phép.
docker inspect CONTAINER_NAME
docker port CONTAINER_NAME

# Nếu image có iproute2, lệnh dưới đây chỉ xem network interfaces/routes.
docker exec CONTAINER_NAME ip -br address
docker exec CONTAINER_NAME ip route
docker exec CONTAINER_NAME ip -6 route
~~~

`docker inspect` có thể hiển thị **environment variables, mount paths, network addresses, runtime configuration và thông tin nhạy cảm**. Khi gửi báo cáo, nên chỉ trích những trường liên quan, ẩn secrets và hạn chế người được xem. Không dùng `docker exec` để chạy lệnh thay đổi networking khi đang kiểm tra read-only.

### 10.2. So namespace inode với PID

~~~bash
# Đọc namespace identity của process host.
readlink /proc/1/ns/net

# Câu lệnh lấy PID từ Docker trong mô hình Docker Linux rootful thường gặp.
docker inspect --format '{{.State.Pid}}' CONTAINER_NAME

# Với PID thật trả về và khi được phép xem /proc:
readlink /proc/CONTAINER_PID/ns/net

# Quan sát các namespace mà host có thể liệt kê.
lsns -t net
ip netns list
~~~

Trong cấu hình Docker Linux rootful, `State.Pid` thường có ý nghĩa trong host PID namespace. Với **rootless, containerd/CRI, remote Docker daemon, nested containers hoặc runtime khác**, mapping và quyền đọc `/proc` có thể khác. `lsns` không phải bằng chứng hoàn chỉnh khi permission bị giới hạn; `ip netns list` không liệt kê mọi anonymous netns.

### 10.3. Xem trạng thái trong netns mà không thay đổi nó

Nếu có quyền trên một Linux VM lab, có thể dùng:

~~~bash
# Read-only inspection từ một process PID đã được xác định và phê duyệt.
# nsenter cần quyền phù hợp; lệnh chỉ xem state của network namespace.
sudo nsenter --target CONTAINER_PID --net ip -br addr
sudo nsenter --target CONTAINER_PID --net ip route
sudo nsenter --target CONTAINER_PID --net ss -lnt
~~~

**Phân biệt:** `nsenter` thay đổi namespace mà **lệnh kiểm tra đang chạy** tạm thời tham gia, chứ không tự sửa cấu hình network. Nhưng nếu thay `ip route` bằng một lệnh ghi, nó có thể thay đổi networking của container; chỉ dùng các lệnh quan sát trên. Không thực hiện `nsenter` tùy tiện trên host multi-tenant/production.

### 10.4. Vì sao container không có `ip` hoặc `ss`?

Nhiều image nhỏ hoặc distroless không chứa `iproute2`, `ss`, `ping` hay shell. Đây **không phải lỗi networking**. Khi cần chẩn đoán, ưu tiên log runtime/CNI, API metadata hoặc công cụ debugging được tổ chức phê duyệt; không tự cài package vào container production chỉ để xem route.

## 11. Kubernetes Pod: nhiều container dùng một network namespace

Trong mô hình Kubernetes Pod bình thường, **Pod** là đơn vị scheduling/networking quan trọng. Mỗi Pod có **Pod network identity** và những containers bên trong chia sẻ network stack; các container trong cùng Pod giao tiếp qua **`localhost`** khi một service bind phù hợp.

~~~mermaid
flowchart TB
    subgraph NODE["Kubernetes node"]
        subgraph POD1["Pod frontend: shared network namespace"]
            F["Frontend container :8080"]
            SIDE["Sidecar container :15001"]
            LOOP["lo / localhost"]
            ETH["eth0 / Pod IP 10.244.1.10"]
            F <--> LOOP
            SIDE <--> LOOP
        end
        subgraph POD2["Pod backend: another network namespace"]
            API["API container :8080"]
            E2["eth0 / Pod IP 10.244.1.20"]
        end
        DATA["Node CNI dataplane"]
        ETH --> DATA
        E2 --> DATA
    end
~~~

**Mô hình trên giả định Pod networking chuẩn, không dùng `hostNetwork`.** Một Pod có thể có sidecar hoặc nhiều application containers nhưng vẫn dùng chung TCP/UDP port space trong netns. Vì vậy hai container trong **cùng Pod** cùng bind `0.0.0.0:8080` thường gây port conflict, dù chúng có file system/process isolation riêng.

### 11.1. Pod IP và Service IP khác nhau

| Khái niệm | Phạm vi | Bản chất |
|---|---|---|
| **Pod IP** | Được CNI/IPAM cấp cho Pod theo networking model | Địa chỉ gắn với networking của Pod, có thể thay khi Pod được tạo lại |
| **Container port** | Port ứng dụng bind trong shared Pod netns | Tên/khai báo manifest không tự tạo listener |
| **Service ClusterIP** | Virtual service destination | Thông thường do dataplane/Service proxy xử lý; không mặc nhiên là interface riêng nằm trong Pod |
| **Node IP** | Địa chỉ của host/node | Dùng cho node networking, không đồng nhất Pod IP |
| **Ingress / Gateway** | Điểm nhận traffic theo cách triển khai | Có thể route tới Service/Pod, cần TLS/authz/filtering |
| **Kubernetes namespace** | API resource namespace | Không tự làm một subnet hay Linux netns riêng |

Kubernetes Service có thể cung cấp **địa chỉ ổn định** cho một nhóm Pod backends, trong khi các Pod IP thay đổi. Cơ chế chọn/forward traffic tùy implementation, có thể dùng iptables, IPVS, nftables hoặc eBPF datapath; **không thể dựa vào sự tồn tại của interface `kube-ipvs0` hay bridge `cni0` trên mọi cluster**.

### 11.2. Sidecar dùng localhost không đồng nghĩa mọi request an toàn

Một service mesh sidecar có thể intercept inbound/outbound traffic và dùng `localhost` để giao tiếp với app trong cùng Pod. Nhưng:

- **Traffic app → sidecar trên loopback** không nhất thiết được TLS bảo vệ như traffic sidecar → sidecar.
- mTLS giữa workloads phụ thuộc mesh policy, certificate rotation, identity và cấu hình proxy.
- Một container khác trong cùng Pod **chia sẻ local ports/network stack**, nên cần cân nhắc trust giữa các container đồng Pod.
- Sidecar không tự thay thế API authentication, application authorization hoặc data policy.

**Không coi mọi container cùng Pod là một tenant tách biệt về network security.** Nếu cần ranh giới mạng độc lập, nên xem thiết kế **Pod riêng + NetworkPolicy + service identity**.

### 11.3. `hostNetwork: true` trên Kubernetes

~~~yaml
# PHẢN VÍ DỤ về isolation nếu được áp dụng không có đánh giá.
apiVersion: v1
kind: Pod
metadata:
  name: example-host-network-pod
  namespace: sandbox-app
spec:
  hostNetwork: true
  containers:
    - name: service
      image: example.invalid/approved-service:1.0
~~~

Khi `hostNetwork: true`, Pod sử dụng network namespace của node theo mô hình Kubernetes; như vậy các giả định về **Pod IP/netns riêng, port binding và network isolation** không còn giống Pod bình thường. Chính sách Kubernetes NetworkPolicy đối với host-networked Pods có thể **phụ thuộc CNI implementation và không nên mặc định được áp dụng như Pod bình thường**.

YAML chỉ là mẫu giải thích; image dùng domain giả không phải image thật để triển khai. Đội security nên hạn chế/admission-control host networking theo nhu cầu và xem host firewall, capabilities, routing, node isolation.

## 12. CNI, IPAM và đường đi Pod-to-Pod

**CNI (Container Network Interface)** mô tả cách container runtime/cluster orchestration tích hợp plugins mạng để thiết lập network connectivity cho container/pod sandbox. **IPAM (IP Address Management)** quản lý việc cấp và thu hồi địa chỉ. Kubernetes networking dựa vào CNI implementation phù hợp để tạo **interfaces, addresses, routes, policies hoặc dataplane hooks**.

### 12.1. CNI không đồng nghĩa một kiến trúc duy nhất

Các giải pháp CNI khác nhau có thể dùng:

- **Linux bridge + veth** trong những triển khai cơ bản.
- **Routing trực tiếp** giữa Pod CIDRs trên các nodes.
- **VXLAN/Geneve overlay** chạy qua underlay mạng node.
- **eBPF dataplane** để xử lý forwarding, load balancing và policy ở các kernel hooks phù hợp.
- **Cloud VPC-native IPs** gắn Pod IP với networking của VPC theo khả năng provider.
- **SR-IOV hoặc multiple interfaces** trong những môi trường chuyên biệt.

**CNI spec không bắt buộc mọi Pod phải có interface tên `eth0`, bridge `cni0` hay tunnel VXLAN.** Thực tế nhiều nền tảng dùng `eth0` cho interface chính, nhưng đó là convention/implementation detail. Khi có Multus hoặc plugin tạo nhiều interface, Pod có thể có `net1` và nhiều addresses/routes.

### 12.2. Mô hình Pod-to-Pod giữa hai nodes

~~~mermaid
flowchart LR
    subgraph N1["Node A"]
        P1["Pod A / 10.244.1.10"]
        C1["CNI dataplane A"]
        P1 --> C1
    end
    subgraph N2["Node B"]
        C2["CNI dataplane B"]
        P2["Pod B / 10.244.2.20"]
        C2 --> P2
    end
    C1 <-->|"Underlay routing hoặc overlay tunnel"| C2
    POL["NetworkPolicy / network controls"] -. "Enforcement theo CNI" .-> C1
    POL -. "Enforcement" .-> C2
~~~

Kubernetes networking model thường kỳ vọng Pods có thể giao tiếp bằng Pod IP với nhau theo mô hình cluster, nhưng **NetworkPolicy và các controls khác có thể hạn chế**. Đường giữa nodes phụ thuộc CNI/router/firewall/MTU/tunnel, và Pod IP có thể không được route từ mạng ngoài cluster.

### 12.3. Overlay và underlay: khác biệt khi kiểm tra packet

Với overlay, một packet Pod-to-Pod có thể được **đóng gói trong một packet tunnel** giữa hai nodes. Host underlay thấy node source/destination và tunnel protocol; ứng dụng Pod nhìn IP Pod đích. Với direct routing hoặc VPC-native model, đường đi khác.

**Không giả định overlay được mã hóa chỉ vì có tunnel.** VXLAN/Geneve tạo encapsulation, không tự bảo đảm confidentiality. Nếu cần mã hóa in transit, dùng TLS/mTLS hoặc cơ chế encryption được CNI/underlay hỗ trợ và cấu hình đúng.

### 12.4. MTU và fragmentation

Overlay thêm overhead, có thể làm **effective MTU nhỏ hơn** underlay. Nếu MTU/PMTUD sai, một số kết nối nhỏ hoạt động nhưng TLS handshake hoặc request có payload lớn bị treo. Khi troubleshooting, cần xem:

- MTU trong Pod và node uplink/tunnel;
- ICMP Packet Too Big/fragmentation behavior theo IPv4/IPv6;
- Security controls có chặn thông điệp PMTU cần thiết không;
- Đường thay thế giữa nodes hoặc VPN/cloud transit;
- CNI tunnel mode và link overhead.

Không tăng MTU hoặc bật fragmentation settings trên production trước khi có bằng chứng và change plan.

## 13. NetworkPolicy trong Kubernetes không phải network namespace

**Kubernetes NetworkPolicy** mô tả những kết nối **Ingress/Egress L3/L4** được phép đối với Pods do selector chọn, khi **network plugin hỗ trợ và thực thi policy**. Nó bổ sung network isolation ở mức workloads; **không tạo Linux network namespaces mới**.

### 13.1. Không có policy chọn Pod thường nghĩa là chưa có policy isolation

Mặc định theo API NetworkPolicy, nếu không có NetworkPolicy chọn một Pod theo một hướng, Pod đó **không bị cách ly theo NetworkPolicy ở hướng đó**. Các policies có tính **cộng dồn allow rules**: một policy cho phép một flow không bị một policy khác “deny ngược” theo cú pháp chuẩn của Kubernetes NetworkPolicy.

Để kết nối từ Pod A tới Pod B khi hai bên đều bị cách ly, cần:

1. **Egress từ A được cho phép** bởi policy áp dụng cho A;
2. **Ingress tới B được cho phép** bởi policy áp dụng cho B.

Ngoài ra, các firewall/cloud/CNI policies khác vẫn có thể deny. Kubernetes NetworkPolicy không được dùng để thay thế workload authentication hoặc user RBAC.

### 13.2. Default deny cho một Kubernetes namespace

~~~yaml
# Chỉ áp dụng trong cluster lab và namespace sandbox-app được phê duyệt.
# NetworkPolicy này có thể ngắt toàn bộ traffic Pod nếu triển khai thật.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress-egress
  namespace: sandbox-app
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Trong một CNI thực thi NetworkPolicy đúng, policy trên chọn **tất cả Pods trong Kubernetes namespace `sandbox-app`** và đánh dấu chúng được cách ly ở cả hai hướng mà không có rule allow. Điều này có thể chặn cả **DNS, API calls và dependency**; đừng áp dụng lên production mà không chuẩn bị allow rules và đường quản trị.

**Phân biệt:** `metadata.namespace: sandbox-app` là **phạm vi API Kubernetes**, không phải một `ip netns` mang tên `sandbox-app`. Mỗi Pod bình thường vẫn có netns mạng của riêng Pod.

### 13.3. Allow API ingress từ frontend đã chỉ định

~~~yaml
# Ví dụ minh họa, cần namespace/pod labels khớp môi trường lab.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-api
  namespace: sandbox-app
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8443
~~~

Policy này cho phép **Ingress TCP/8443** tới Pods `app=api` từ Pods `app=frontend` **trong cùng namespace `sandbox-app`** (do `podSelector` chỉ nằm trong cùng namespace khi không có `namespaceSelector`). Nếu frontend còn bị cách ly egress, cần policy allow egress riêng; một policy ingress không tự cho phép chiều đi ở nguồn.

### 13.4. DNS egress cần được thiết kế chứ không mở bừa

Trong cluster có default-deny egress, DNS queries có thể bị chặn nếu không có policy phù hợp. Một ví dụ:

~~~yaml
# CHỈ lab; labels của DNS Pods phụ thuộc cluster/CNI distribution.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-to-cluster-dns
  namespace: sandbox-app
spec:
  podSelector:
    matchLabels:
      needs-dns: "true"
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

Policy chỉ chọn Pods có `needs-dns: "true"` và dựa trên **labels giả định** cho cluster DNS. Các cluster dùng CoreDNS/NodeLocal DNSCache hoặc network dataplane khác có DNS addresses và labels khác; quá trình DNAT khi truy cập Service IP cũng có thể ảnh hưởng cách network policies được thực thi tùy CNI. **Không copy policy trên vào production mà không xác minh DNS topology và plugin behavior**.

### 13.5. Giới hạn của NetworkPolicy

NetworkPolicy chuẩn thường tập trung **L3/L4 Pod traffic**; nó không mô tả đầy đủ:

- HTTP method/path, JWT subject, SQL role, API authorization;
- Host firewall cho mọi node processes và `hostNetwork` ở mọi CNI;
- DNS/FQDN allowlist ở cấp policy chuẩn theo cách portable;
- Việc cưỡng chế tất cả egress ngoài cluster ở điểm cloud gateway;
- Mã hóa packet (TLS/mTLS) và trust certificate.

Một số CNI bổ sung **extended policies** như FQDN, L7, global policies, host endpoints hoặc encryption, nhưng đó là **tính năng sản phẩm**, không mặc nhiên thuộc API NetworkPolicy tiêu chuẩn.

## 14. Tại sao Pod network security phải xét cả Service và ingress?

Một Pod private chỉ có Pod IP nội bộ vẫn có thể được người dùng Internet gọi qua **Ingress Controller, Gateway API hoặc external LoadBalancer Service**, nếu các thành phần được cấu hình xuất bản ứng dụng. Điều này giống nguyên tắc **private workload vẫn có public application entry point** trong cloud networking.

### 14.1. Một chuỗi request tiêu biểu

~~~mermaid
flowchart LR
    U["Internet client"] --> W["Cloud LB / WAF"]
    W --> IG["Kubernetes Ingress / Gateway"]
    IG --> SVC["Service virtual IP / routing"]
    SVC --> POD["Private Pod IP / app listener"]
    NP["NetworkPolicy / CNI enforcement"] -. "Allow/deny theo Pod và hướng" .-> POD
    TLS["TLS / service identity"] -. "Bảo vệ từng TLS hop" .-> IG
~~~

Nhiều điểm có thể kết thúc TLS: cloud LB, ingress controller, service mesh sidecar hoặc application. Chỉ vì `https://` ở edge **không có nghĩa** hop tới Pod đã được TLS bảo vệ. Cần xác định điểm nào được phép thấy plaintext, nơi nào có mTLS và policy cho client/server identity.

### 14.2. ClusterIP không phải ranh giới bảo mật

`ClusterIP` mô tả kiểu Service virtual address được định tuyến bên trong cluster theo cấu hình thông thường, **không phải một firewall rule**. Pods khác trong cluster có thể gọi Service nếu network policies/routing cho phép, kể cả khi Service không mang external IP.

Một Pod không được chọn bởi NetworkPolicy (hoặc cluster CNI không thực thi policy) có thể **nhận kết nối từ nhiều Pods hơn dự định**, dù Services/Pods dùng private addresses. Cần negative tests **Pod ở namespace khác → API/DATA** chứ không chỉ test Internet→Pod.

### 14.3. `hostPort`, `NodePort` và `LoadBalancer` không đồng nghĩa

| Cơ chế | Ý tưởng | Rủi ro cần xem |
|---|---|---|
| **Pod containerPort** | Metadata mô tả port container | Không tự publish lên node/Internet |
| **hostPort** | Expose một cổng trên network host theo CNI/kubelet implementation | Có thể tạo node-level exposure và conflict |
| **NodePort Service** | Làm Service truy cập qua port của node theo các điều kiện cấu hình | Node firewall và external routing/allowed IP ranges |
| **LoadBalancer Service** | Tích hợp external/internal LB tùy cloud/controller configuration | Phải xác minh LB public/private và inbound policy |
| **Ingress / Gateway** | Routing HTTP/HTTPS hoặc các giao thức hỗ trợ theo controller | TLS termination, host/path routing, WAF, authentication |

**Không kết luận service an toàn chỉ vì Pod IP thuộc RFC1918.** Phải xét toàn bộ ingress path, source allowlist, network policy, listener, DNS và TLS/authz.

## 15. Threat modeling: netns cô lập cái gì và không cô lập cái gì?

### 15.1. Tài sản và trust boundaries

Trong một cluster có frontend, API, database và node agents, những tài sản cần bảo vệ gồm:

- **Nội dung ứng dụng và dữ liệu nhạy cảm** đi giữa Pods/Services hoặc ra Internet.
- **Workload identities, service account tokens, TLS keys và secrets**.
- **Kernel/node network stack**, CNI dataplane, IPAM, policy engine và network control plane.
- **Cloud metadata endpoints**, DNS resolver, kube-apiserver và các dịch vụ control-plane.
- **Logs/flow telemetry** có thông tin IP, Pod names, DNS queries hoặc hoạt động người dùng.

Các trust boundaries cần đánh dấu:

1. Từ Internet đến **public load balancer / ingress**.
2. Từ ingress đến **Pod frontend/API**.
3. Từ frontend đến **API** và **DATA** giữa các Pod namespaces.
4. Từ Pod đến **node/host network** và các services cấp cluster.
5. Từ Pod tới **Internet và cloud APIs**.
6. Giữa các workloads ở **nodes, clusters hoặc tenants khác nhau**.

### 15.2. Bảng mối đe dọa

| Rủi ro | Cơ chế gây ra | Biện pháp giảm thiểu | Giới hạn |
|---|---|---|---|
| Container tưởng riêng nhưng dùng host netns | `--network host`, `hostNetwork: true` | Admission/Runtime policy, host firewall, rà soát đặc quyền | Phụ thuộc runtime/CNI |
| Truy cập lateral giữa Pods | Pod IP kết nối được và chưa có NetworkPolicy | Default deny + allowlist theo label/namespace, app authorization | CNI phải thực thi policy |
| Container cùng Pod truy cập port local của nhau | Shared Pod netns và loopback | Chỉ đặt containers cùng trust boundary vào cùng Pod, app auth | NetworkPolicy không tách localhost giữa containers cùng Pod |
| Public port ngoài ý định | Docker publish, NodePort/LB, hostPort | Inventory, host firewall, cloud SG, admission | Service vẫn phải harden và authenticate |
| Egress dữ liệu ra ngoài | NAT/route cho Pod đi Internet quá rộng | Egress policy/gateway, DNS controls, workload identity | NAT không tự là DLP |
| Truy cập node/cloud metadata | Network path tới metadata endpoint + quyền workload | Metadata protections, workload identity, SSRF defense, egress deny | Khả năng enforcement tùy CNI/cloud |
| ARP/ND manipulation cùng L2 segment | Một network segment chia sẻ nhưng không giới hạn peer | L2 isolation khi cần, network driver phù hợp, drop NET_RAW theo đánh giá | Không phải mọi dataplane có broadcast domain như nhau |
| Thay interface/route trong container | Cấp `CAP_NET_ADMIN`/privileged không cần thiết | Drop capabilities, admission, userns/LSM | Netns không bảo vệ trước host compromise |
| Host bị xâm phạm | Kernel exploit hoặc đặc quyền runtime | Patch kernel/runtime, seccomp, LSM, rootless/userns, isolate nodes | Dùng chung kernel nên không bằng VM isolation |
| Pod spoof identity/IP | Sai network enforcement, IPAM/route config hoặc quyền cao | CNI policy, anti-spoofing controls, service identity/mTLS | IP không đủ làm danh tính người dùng |
| DNS spoof/route bypass | Resolver, CNI routing hoặc proxy bị cấu hình sai | DNS policy, TLS identity validation, route audit | DNS đúng không tự xác thực application |
| Overlay bị nghe lén trong underlay | Encapsulation không kèm encryption | TLS/mTLS, encryption của CNI/underlay khi cần | Overlay bản thân không chứng minh confidentiality |
| Log thiếu dấu vết | Traffic bypass enforcement point hoặc CNI logging tắt | Flow logs tại nguồn, workload trace, audit | Một điểm quan sát không thấy mọi traffic |
| IPv6 bypass | Dual-stack nhưng policy chỉ xét IPv4 | IPv4/IPv6 route/policy parity và tests | Plugin support cần xác minh |

**Security conclusion:** ranh giới namespace làm tách **network state**, nhưng authorization và confidentiality của dịch vụ vẫn cần **identity, TLS, segmentation, secrets management và host security**.

## 16. Capabilities, privileged mode và ranh giới bảo vệ kernel

### 16.1. `CAP_NET_ADMIN` cho phép làm gì?

Trong Linux, khả năng **`CAP_NET_ADMIN`** cho phép nhiều thao tác quản trị networking trong phạm vi mà tiến trình có quyền, ví dụ thay đổi địa chỉ, interface state, routes hoặc một số firewall settings. Nếu cấp capability này cho container không cần thiết, một ứng dụng bị chiếm quyền có thể **thay đổi topology mạng nội bộ của chính netns** và khai thác các quyền khác nếu môi trường bị cấu hình sai.

`CAP_NET_RAW` thường liên quan thao tác raw/packet sockets; không phải ứng dụng HTTP nào cũng cần quyền này. Không nên mặc định rằng drop một capability sẽ chặn mọi kỹ thuật tấn công, nhưng **principle of least privilege** giúp giảm bề mặt lạm dụng.

### 16.2. `--privileged` không phải cách sửa lỗi network

Một container chạy với **privileged mode** có thể nhận quyền truy cập kernel/devices rộng hơn nhiều so với container bình thường, tùy runtime. Nếu bind thêm host namespaces hoặc mount socket quản trị container, nó có thể có tác động **vượt ra ngoài netns mặc định**.

Các hành động nên tránh khi troubleshooting production:

- Bật `--privileged` để chạy `ping`, `ip`, hoặc một agent vốn chỉ cần đọc log.
- Bật `hostNetwork` để chữa một lỗi DNS mà chưa kiểm tra CNI/DNS.
- Mount container runtime socket của host cho workload không đáng tin.
- Cấp `CAP_NET_ADMIN` để ứng dụng tự thêm route/NAT mà không có design review.
- Tắt toàn bộ NetworkPolicy rồi coi kết nối lại được là “đã sửa xong”.

Hãy dùng **debugging có kiểm soát, công cụ platform và logs** để xác minh nguyên nhân, sau đó áp dụng thay đổi tối thiểu.

### 16.3. Network namespace không tách kernel vulnerability domain

Container khác VM ở chỗ thường **dùng chung một kernel** với host. Nếu kernel hoặc các subsystem networking có vulnerability, netns không đảm bảo chống lại mọi tấn công giữa workload và host. Đối với workload không tin cậy hoặc tenant độc lập, cân nhắc **node isolation, virtualization/sandboxing bổ sung và hạn chế syscall/capabilities** theo threat model.

### 16.4. Sysctls phải phân loại đúng phạm vi

Một số network sysctls có thể được thiết lập theo netns; những tham số khác hoặc thao tác ảnh hưởng toàn host. Kubernetes có phân loại sysctls an toàn/không an toàn theo khả năng runtime và pod policy. **Không sửa `/proc/sys` hoặc bật IP forwarding trên node production** chỉ để thử tuyến mạng container.

Thay đổi sysctls/routing nên thuộc quản lý node/CNI với review, không để application Pods tự ý quyết định.

## 17. Phòng vệ nhiều lớp cho container networking

### 17.1. Tách ingress, application, data và management

~~~mermaid
flowchart TD
    U["Internet / Người dùng"] --> W["Public WAF / Ingress"]
    subgraph CL["Kubernetes cluster"]
        W --> FE["Frontend Pod / namespace web"]
        FE --> API["API Pod / namespace app"]
        API --> DB["Database Pod hoặc managed DB"]
        AG["Node agents / control plane"] -. "Management access có kiểm soát" .-> API
        CNI["CNI NetworkPolicy dataplane"] -. "Allow/deny giữa Pods" .-> FE
        CNI -. "Allow/deny" .-> API
        CNI -. "Allow/deny" .-> DB
    end
    API -. "Egress theo allowlist" .-> E["Egress gateway / firewall"]
    E --> EXT["Approved external services"]
~~~

Ý định bảo mật:

- **Ingress:** chỉ publish những Services/gateway thật sự cần Internet-facing, dùng TLS, WAF, rate limit và identity.
- **Application:** nhận traffic từ các Pod/source identities có quyền; có NetworkPolicy ingress và egress.
- **Data:** chỉ từ API đúng port, database credentials/authorization, TLS và backup policy.
- **Node/management:** giới hạn quyền node administrators, kubelet/kube-apiserver API, container runtime sockets, control-plane routes.
- **Egress:** service nào cần Internet thì được phép qua đúng gateway/destination; không mở tất cả namespaces.

### 17.2. NetworkPolicy là một lớp, mTLS là lớp khác

| Bảo vệ | Câu hỏi được giải quyết |
|---|---|
| Network namespace | Process thấy network interfaces/routes/socket state nào? |
| Kubernetes NetworkPolicy / CNI policy | IP/Pod nào có quyền kết nối theo L3/L4? |
| Cloud SG/NSG/firewall | Node/LB/subnet/zone nào được kết nối với mạng khác? |
| TLS/mTLS | Dữ liệu được mã hóa và peer identity nào đã được xác thực? |
| Application authn/authz | User/service được thực hiện hành động nào? |
| DNS security | Tên dịch vụ trỏ tới đích nào và độ tin cậy ra sao? |
| WAF/IDS/IPS/observability | Phát hiện/chặn hành vi bất thường ở điểm có visibility? |

**Một Pod có IP private, ở Kubernetes namespace riêng và được bao bởi CNI vẫn có thể xử lý một request độc hại hợp lệ từ ingress public**. Muốn bảo vệ dữ liệu cần nhiều lớp, không thể dồn toàn bộ vào một nhãn network.

### 17.3. Service mesh và workload identity

Service mesh có thể cung cấp **mTLS giữa workloads**, certificate rotation và authorization policies theo identity. Nhưng cần xác định:

- Sidecar hoặc ambient dataplane nào là TLS endpoint?
- Request từ node/host network hoặc một sidecar bị bypass có được kiểm soát không?
- Mesh policy có áp dụng cho egress tới external services không?
- Identity được ánh xạ tới namespace/service account/Pod hay một danh tính khác?
- Logs và flow telemetry có hiển thị cả deny do CNI và deny do mesh không?

Không gọi một cấu hình là zero trust chỉ vì mesh bật mTLS: **identity, segmentation, continuous policy verification và least privilege** phải hoạt động đồng bộ.

## 18. Quan sát Kubernetes networking bằng lệnh chỉ đọc

Các lệnh sau chỉ dành cho cluster đã được cấp quyền. Những API calls dạng `get`, `describe` thường **không chỉnh trạng thái**, nhưng output có thể chứa địa chỉ nội bộ, images, environment references, service accounts, host networking và topology nhạy cảm.

### 18.1. Pod identity và network mode

~~~bash
# Liệt kê Pod IP, node và trạng thái trong namespace lab.
kubectl get pods -n sandbox-app -o wide

# Xem Pod metadata/spec/events; kiểm tra hostNetwork, containers, DNS policy.
kubectl describe pod POD_NAME -n sandbox-app

# Một số fields cần xem; output phụ thuộc tài nguyên thật.
kubectl get pod POD_NAME -n sandbox-app \
  -o jsonpath='{.spec.hostNetwork}{"\n"}{.status.podIP}{"\n"}{.spec.nodeName}{"\n"}'
~~~

Không suy Pod có netns riêng chỉ từ việc nó xuất hiện trong `kubectl get pods`: xem `hostNetwork`, CNI sandbox state và runtime configuration khi có quyền. Không ép yêu cầu một Pod có **một IP duy nhất trong mọi trường hợp** vì dual-stack/multi-network implementations có thể có thêm addresses.

### 18.2. Đọc interfaces/routes bên trong Pod khi image có công cụ

~~~bash
# Chỉ xem trạng thái từ application container đã được cấp quyền.
kubectl exec -n sandbox-app POD_NAME -c CONTAINER_NAME -- ip -br address
kubectl exec -n sandbox-app POD_NAME -c CONTAINER_NAME -- ip route
kubectl exec -n sandbox-app POD_NAME -c CONTAINER_NAME -- ip -6 route
kubectl exec -n sandbox-app POD_NAME -c CONTAINER_NAME -- ss -lnt
~~~

Nếu image không có `ip` hoặc `ss`, **đừng coi đó là sự cố mạng**. Dùng CNI/cluster telemetry, node runtime inspection trong khung quyền được phê duyệt hoặc debugging workflow riêng. Không tùy tiện tạo ephemeral debug containers trên production để “lấy công cụ”.

### 18.3. Kiểm tra Service, endpoints và NetworkPolicy

~~~bash
# Xem service endpoints mà Pod có thể cần gọi.
kubectl get services -n sandbox-app -o wide
kubectl get endpointslices -n sandbox-app

# Liệt kê NetworkPolicies.
kubectl get networkpolicies -A

# Xem policy áp dụng cho API Pod trong namespace lab.
kubectl describe networkpolicy allow-frontend-to-api -n sandbox-app

# Xem labels của Pods/namespaces để hiểu selector.
kubectl get pods -n sandbox-app --show-labels
kubectl get namespaces --show-labels
~~~

**Quan trọng:** `kubectl get networkpolicies -A` chỉ chứng minh objects tồn tại, **không chứng minh CNI đang thực thi** hoặc traffic không có đường bypass qua node/hostNetwork. Phải kiểm tra CNI compatibility, flow logs và các phép thử kết nối từ đúng source/destination Pods.

### 18.4. Chỉ đọc trên node khi được cấp quyền

~~~bash
# Trên Linux lab node, lệnh read-only và có thể cần sudo.
ip -br link
ip -br address
ip route
ip -6 route
lsns -t net
ss -lntup

# Xem rules mà node network stack đang có; output có thể nhạy cảm.
sudo nft list ruleset
~~~

Chỉ xem `nft list ruleset` chưa chắc đủ: dataplane có thể dùng **iptables backend, IPVS, eBPF hoặc cloud network enforcement**, và host firewall không cho biết ứng dụng đang xác thực kết nối ra sao. Không sửa rules trong quá trình chẩn đoán chỉ đọc.

### 18.5. Làm sao biết hai container cùng netns?

Nếu có quyền ở node lab và có thể xác định PID host tương ứng từng container, so identity `/proc/<pid>/ns/net`. Hai containers trong cùng Pod chuẩn thường có **netns inode trùng nhau**, nhưng có thể khác PID/mount namespaces. Khi runtime dùng sandbox/pause container, process đó có thể giữ network namespace của Pod trong vòng đời Pod.

Không dùng namespace inode như một identity nghiệp vụ lâu dài: Pod restart/recreate có thể có netns mới, Pod IP và process ID mới. Audit cần **Pod UID, node, thời điểm, workload identity và CNI mapping** để liên kết sự kiện.

## 19. Ma trận kiểm thử netns, interfaces và network isolation

Để khẳng định một container/Pod đã được cô lập đúng, không thể chỉ nhìn vào `ip addr` hoặc một network policy YAML. Bộ test cần phân biệt **ngữ cảnh network, khả năng kết nối thực, chính sách L3/L4 và kết quả ứng dụng**.

| Test ID | Câu hỏi cần xác minh | Cách thử trong lab có phép | Kỳ vọng |
|---|---|---|---|
| **NS-01** | Hai container bridge khác nhau có netns riêng không? | So `/proc/<pid>/ns/net` và interfaces theo runtime | Netns khác nếu runtime cấp riêng |
| **NS-02** | Containers cùng Pod chia sẻ netns? | So Pod IP/netns identity của containers cùng Pod chuẩn | Cùng network namespace và port space |
| **NS-03** | Pod `hostNetwork` dùng host networking? | Đọc Pod spec và netns trên node lab | Nhận diện ngoại lệ, không báo isolation giả |
| **LO-01** | Loopback riêng giữa hai netns? | Service test bind 127.0.0.1, thử kết nối đúng phạm vi | Không nhầm localhost giữa namespaces |
| **LO-02** | Container cùng Pod liên lạc localhost? | App test trong Pod dùng loopback đúng port | Kết nối nếu service listen và app policy cho phép |
| **IF-01** | Veth pair lab được nối đúng? | `ip -n ... addr`, `ip link`, ping giới hạn | Hai netns liên thông qua cặp veth đã tạo |
| **ROUTE-01** | Container có default route đúng? | `ip route` và network metadata | Next hop đúng CNI/runtime design |
| **ROUTE-02** | Pod-to-Pod cross-node có đường hợp lệ? | Controlled connectivity + CNI route/overlay telemetry | Kết nối theo design, không bypass security policy |
| **MTU-01** | Overlay không gây MTU blackhole? | App test payload theo kích thước có phép | Không treo do PMTUD/MTU sai |
| **PUB-01** | Docker published port đúng host bind? | `docker port`, host `ss`, host firewall | Chỉ host interfaces được duyệt tiếp nhận |
| **PUB-02** | Port không được publish không tự public? | Review mapping/routes + controlled reachability | Không có public ingress ngoài design |
| **HOST-01** | Host networking bị hạn chế? | Inventory Pod spec/Docker modes và admission | Không có workload ngoài allowlist dùng host networking |
| **CAP-01** | Container không có NET_ADMIN ngoài nhu cầu? | Review Pod security context/runtime config | Không cấp network/admin capabilities quá mức |
| **NP-01** | Default-deny ingress có hiệu lực? | Controlled Pod A→Pod B sau policy, positive control | Unauthorized ingress bị deny |
| **NP-02** | Default-deny egress có hiệu lực? | Controlled Pod→external lab destination | Unauthorized egress bị deny |
| **NP-03** | Frontend→API TCP/8443 vẫn được phép? | Source frontend Pod đúng labels→API | Allow khi ingress+egress rules đáp ứng |
| **NP-04** | Unrelated Pod→API bị từ chối? | Pod từ namespace khác không có grant → API | Không kết nối theo enforcement policy |
| **DNS-01** | Pod có DNS egress đúng? | Resolver query từ Pod có policy cho phép | Chỉ DNS destination/port được duyệt |
| **DNS-02** | NetworkPolicy không làm hỏng app bằng lỗi DNS? | So DNS logs và app resolution | App dependency hoạt động, policy vẫn giới hạn |
| **SERVICE-01** | ClusterIP không tạo public exposure? | Review Service/ingress/LB association | Không có đường public ngoài các entry points |
| **SERVICE-02** | NodePort/LoadBalancer được kiểm soát? | Inventory Service types, node/LB firewall | Chỉ listener công khai đã duyệt hoạt động |
| **IPV6-01** | Dual-stack không tạo đường bypass? | So IPv4/IPv6 routes, Pod IPs và controlled tests | Cùng ý định allow/deny cho cả hai stack |
| **EGRESS-01** | Pod không truy cập metadata/API ngoài ý định? | Policy review và controlled test endpoint giả lập | Không có đường rộng ngoài quyền |
| **OBS-01** | Log phản ánh đúng Pod/network identity? | So CNI flow, Pod UID, node, IPAM và app logs | Không dựa vào Pod IP cũ sau restart |
| **REG-01** | Restart/migration không làm mất policy? | Lặp test sau restart Pod/move node trong lab | Policy và đường mạng vẫn đúng |

### 19.1. PASS, FAIL và INCONCLUSIVE

- **PASS:** có bằng chứng từ **namespace/interface state, runtime/CNI configuration và phép thử thực tế** theo đúng nguồn/đích. Ví dụ netns của hai Pods khác nhau, một test frontend→API được phép, test Pod không có quyền→API bị từ chối bởi CNI policy.
- **FAIL:** traffic trái policy vẫn được phép, published port mở ngoài ý định, Pod có hostNetwork/NET_ADMIN ngoài allowlist hoặc policy được cấu hình nhưng CNI không thực thi.
- **INCONCLUSIVE:** test thất bại vì target Pod chưa Ready, DNS sai, route lỗi, command `ip` không có trong image, test chạy nhầm namespace/Pod hoặc thiếu telemetry để xác nhận lý do deny.

**Negative test cần positive control.** Nếu Pod B không nghe TCP/8443, mọi request đều có thể timeout/refused kể cả khi NetworkPolicy không chặn. Hãy chứng minh service đích hoạt động từ một nguồn được phép, sau đó mới kết luận test từ nguồn không được phép được chặn đúng.

### 19.2. Mẫu evidence cho một bài test

~~~yaml
test_id: NP-API-DENY-LAB-01
environment: authorized-isolated-cluster
time_utc: pending
source:
  namespace: sandbox-other
  pod: unapproved-client
destination:
  namespace: sandbox-app
  service: api
  protocol: TCP
  port: 8443
expected: deny
positive_control:
  source_namespace: sandbox-app
  source_pod_label: app=frontend
  expected: allow
evidence:
  - pod-uid-and-node
  - pod-network-namespace-or-runtime-identity
  - service-and-endpoints
  - networkpolicy-and-pod-labels
  - cni-policy-enforcement-logs
  - positive-and-negative-connectivity-results
result: pending-validation
~~~

Ví dụ **chưa được thực thi**; không ghi dữ liệu người dùng, service tokens hoặc private keys vào evidence. Trong một số CNI, flow logs không bật mặc định; không có log thì cần phương án khác để xác minh.

## 20. Case study: tách Kubernetes namespace nhưng chưa ngăn lateral movement

### 20.1. Tình huống giả định

Một team chạy ứng dụng với ba nhóm workloads:

~~~text
Kubernetes namespace web:
  frontend Pod, HTTP ingress

Kubernetes namespace app:
  api Pod, TCP/8443

Kubernetes namespace data:
  internal datastore, TCP/5432
~~~

Đội triển khai cho rằng ba Kubernetes namespaces **tự tách thành ba network segments**, nên không tạo NetworkPolicy. CNI cluster hỗ trợ NetworkPolicy nhưng **chưa có policy chọn các Pods**, và các Pod-to-Pod routes được thiết lập sẵn theo mô hình cluster.

Trong một diễn tập được cấp phép, một Pod test nằm trong `web` có thể mở kết nối TCP tới datastore ở namespace `data` qua Pod IP hoặc Service. Đây là **khoảng trống phân đoạn**, dù datastore không có public IP hay public LoadBalancer.

### 20.2. Đường đi thực tế và ranh giới sai giả định

~~~mermaid
flowchart TD
    PUB["Internet ingress"] --> FE["Frontend Pod / namespace web"]
    FE --> API["API Pod / namespace app"]
    API --> DATA["Datastore / namespace data"]
    FE -. "Đường không được duyệt nhưng có thể đi khi thiếu policy" .-> DATA
    NET["CNI pod routing"] -. "Kết nối các Pod netns" .-> FE
    NET -. "Kết nối" .-> API
    NET -. "Kết nối" .-> DATA
~~~

**Lỗi nhận thức:** Linux netns cô lập các network stacks của từng Pod; Kubernetes namespace chỉ **phân nhóm API resources**. Việc các Pods thuộc hai Kubernetes namespaces khác nhau **không tự chặn** kết nối khi CNI định tuyến được và không có network controls cấm.

### 20.3. Phân tích theo lớp

| Lớp | Giả định sai | Điều thực sự cần |
|---|---|---|
| Kubernetes namespace | `web` và `data` là hai firewall zones tự động | Cần NetworkPolicy/CNI enforcement và cloud/network controls |
| Linux network namespace | Khác netns nghĩa là không thể route sang nhau | CNI có thể nối qua veth, routing hoặc overlay |
| Service | Datastore ClusterIP sẽ chặn Pod ngoài namespace | ClusterIP không phải authorization mechanism |
| Firewall | Private Pod IP là đủ an toàn | Phải có ingress/egress rules theo source identities |
| Application | Không public nên không cần DB auth | DB vẫn cần credentials, roles, TLS và audit |
| Observability | Không có Internet request tới DB là đạt | Phải xem east–west traffic và negative tests |

### 20.4. Phương án cải thiện

1. **Khoanh vùng tác động:** inventory Pod labels, Services/Endpoints, các ngả route, CNI capabilities và sự tồn tại của policy.
2. **Xác định trust boundaries:** `web → app TCP/8443`, `app → data TCP/5432`, các dependencies DNS/identity/monitoring.
3. **Thêm default-deny theo namespace/Pod group** theo rollout có kiểm soát; tránh ngắt DNS và health probes vì thiếu allow rules.
4. **Thêm allowlist đúng:** frontend có quyền tới API; API được tới datastore; frontend không được gọi datastore trực tiếp.
5. **Bảo vệ data plane:** TLS/mTLS khi cần, DB authentication/authorization và workload identities, không dựa IP/namespace làm danh tính duy nhất.
6. **Giới hạn public ingress:** chỉ expose frontend/API gateways đã duyệt; kiểm tra NodePort, LoadBalancer, hostPort, hostNetwork và cloud LB.
7. **Chạy positive/negative tests:** thử đúng source labels/namespaces, đúng port, cả service DNS và direct Pod IP khi có phép.
8. **Theo dõi sau triển khai:** CNI flow logs, app errors, DNS resolution, Pod readiness, policy changes và rollout rollback.

### 20.5. Trạng thái trước/sau mong muốn

~~~text
BEFORE (kịch bản lab):
  web/frontend -> app/api TCP/8443: ALLOW
  app/api -> data/db TCP/5432: ALLOW
  web/frontend -> data/db TCP/5432: ALLOW (vi phạm mục tiêu)

AFTER (thiết kế cần kiểm chứng):
  web/frontend -> app/api TCP/8443: ALLOW
  app/api -> data/db TCP/5432: ALLOW
  web/frontend -> data/db TCP/5432: DENY
  unrelated namespace -> app/api: DENY
  approved DNS/identity dependencies: ALLOW
  unauthorized Internet egress: DENY where policy requires

Status: PROPOSED, not executed
~~~

**Bài học:** tạo Kubernetes namespace hoặc Linux netns chỉ xây nên **phạm vi tổ chức hoặc network stack riêng**; muốn chống lateral movement phải **thiết kế và kiểm chứng đường đi được phép/bị cấm** ở đúng CNI/network enforcement point.

## 21. Troubleshooting container networking theo từng lớp

| Triệu chứng | Giả thuyết hợp lý | Bằng chứng nên xem |
|---|---|---|
| Container không có `eth0` | Network mode `none`, interface tên khác, CNI lỗi hoặc multi-network | Container mode, `ip -br link`, runtime state |
| `localhost` từ container A không tới B | Hai container khác netns; A gọi loopback của chính A | Netns identity, listener bind, Pod membership |
| Sidecar không kết nối localhost với app | App không listen đúng port/IPv4-IPv6 hoặc lỗi readiness | `ss -lnt`, app logs, shared Pod networking |
| Hai containers cùng Pod bị port conflict | Chia sẻ network namespace và socket bind space | Pod containers, listener ports |
| Docker host không gọi được container | Published port không có/sai, app bind loopback trong container | `docker port`, `docker inspect`, app listener |
| Container có IP nhưng không ra Internet | Không có default route, NAT/forwarding/firewall/DNS lỗi | Routes, host rules, DNS vs IP connectivity |
| Container gọi IP được nhưng DNS lỗi | `/etc/resolv.conf`, DNS upstream, NetworkPolicy egress | DNS configuration, resolver logs, DNS test |
| Pod A cùng node gọi Pod B được, cross-node lỗi | CNI routing/overlay/underlay firewall, MTU | Pod/node IP, CNI logs, tunnel/route |
| HTTP nhỏ thành công, request lớn treo | MTU/PMTUD/fragmentation hoặc proxy limits | Interface MTU, packet-too-big handling, app logs |
| NetworkPolicy tồn tại nhưng không deny | CNI không hỗ trợ/enforce, policy không chọn Pods, direction sai | CNI docs, labels, policyTypes, flow evidence |
| Allow ingress nhưng API không nhận từ frontend | Source egress policy deny hoặc app/Service không khỏe | Both-side policies, endpoints, health |
| Pod chỉ lỗi sau khi bật default-deny | DNS, API dependency, health probe hoặc egress thiếu | DNS/service flow, allowed destination inventory |
| Pod IP khác sau restart | IPAM cấp lại khi sandbox/Pod được tạo mới | Pod UID, endpointslices, DNS/cache |
| NodePort lộ ngoài mong muốn | Service type, node firewall/LB path | Service spec, node exposure, security group |
| `hostNetwork` Pod có cổng xung đột | Dùng host netns và socket port space | Pod spec, host listeners, scheduling |
| Rootless Docker khác rootful logs | Userspace networking backend và port forwarding khác | Docker info, runtime version, rootless backend |
| Host thấy veth nhưng container không thấy | Veth peer bên host, container thấy đầu còn lại/tên khác | Netns mapping, peer ifindex/link data |
| Egress policy bị bypass qua IPv6 | Dual-stack routing/policy không tương ứng | IPv6 Pod addresses, CNI capabilities, logs |
| NetworkPolicy chặn app khi dùng Service IP | DNAT/service IP handling hoặc wrong policy selector | Service routing, CNI policy semantics, source/dest |
| TLS lỗi dù network allow | Certificate/hostname mismatch hoặc protocol/port sai | Handshake logs, SNI, endpoint identity |
| Flow logs không khớp app logs | NAT, overlay, proxy/sidecar hoặc missing telemetry | Socket peer, Pod UID, time, CNI path |

### 21.1. Trình tự chẩn đoán khuyến nghị

1. **Xác định source và destination**: Pod UID/container, network namespace, node, IP, port, protocol, thời điểm.
2. **Kiểm tra listener**: service có chạy, bind `127.0.0.1`, `0.0.0.0`, Pod IP hay IPv6?
3. **Xem interfaces/addresses/routes** trong netns đúng: `lo`, veth, default gateway, secondary interfaces.
4. **Xem Service/Endpoints** nếu có Kubernetes: địa chỉ backend Ready, ClusterIP, NodePort hoặc LB mapping.
5. **Kiểm tra DNS** từ đúng source workload, kể cả NodeLocal DNSCache/cluster resolver.
6. **Xem CNI/bridge/overlay/NAT** và đường từ node này sang node khác; không mặc định luôn có `docker0`.
7. **Xem NetworkPolicy ở cả hai đầu** và các network/firewall policies khác; kiểm tra selectors/labels.
8. **Tách TLS/app errors** ra khỏi lỗi route/firewall, dùng positive control.
9. **Thu evidence/metrics**: CNI flow logs, app traces, host listeners, config diff; hạn chế dữ liệu nhạy cảm.
10. **Khắc phục có rollback**: đừng bật privileged/hostNetwork hay mở toàn bộ ingress chỉ vì test đang timeout.

### 21.2. Phân biệt REFUSED, TIMEOUT và DNS failure

- **Connection refused** có thể do service không listen trên địa chỉ/cổng, hoặc mạng/proxy từ chối chủ động; không mặc định là policy deny.
- **Timeout** có thể do firewall drop, missing route, network blackhole, endpoint không khỏe hoặc PMTU.
- **DNS failure** thường xảy ra trước bước mở kết nối tới IP đích và có thể do NetworkPolicy egress hoặc resolver.
- **HTTP 401/403/5xx** chứng minh có phản hồi ở một lớp ứng dụng nhưng không tự cho biết Pod networking đã an toàn hoặc app được phân quyền đúng.

Không dùng một mã lỗi đơn độc như bằng chứng cuối cùng của security enforcement. Cần **đúng source/destination, đúng thời điểm và lý do từ policy/route/application logs**.

## 22. Runbook triển khai mạng container an toàn

### Bước 1 — Xác định ranh giới tin cậy và luồng nghiệp vụ

Lập danh sách **services, Pods/containers, users, node agents, cloud dependencies và API endpoints**. Với mỗi luồng, ghi nguồn, đích, port/protocol, mục đích và owner. Phân biệt kết nối **container→container trong cùng Pod**, **Pod→Pod**, **node→Pod**, **Internet→ingress** và **Pod→Internet**.

### Bước 2 — Kiểm kê network modes và quyền

Kiểm tra Docker/Kubernetes/CRI runtimes, CNI, IPAM, network attachments, namespace identity, hostNetwork/hostPort, Docker published ports, bridge/overlay/IPv6. Lọc những workload có **privileged mode, `CAP_NET_ADMIN`, `CAP_NET_RAW`, host sockets hoặc quyền truy cập node network stack** không có lý do nghiệp vụ.

Không thay đổi đồng loạt khi chưa biết tác động: một số network appliances, monitoring agents hoặc plugins cần capability đặc biệt; phải xác minh **đúng quyền cần thiết** theo thiết kế, không mặc định bật cho mọi workload.

### Bước 3 — Chọn mô hình kết nối

Quyết định:

- Container nào chỉ cần loopback/cùng Pod?
- Services nào cần Pod IP riêng, Service VIP hoặc Ingress/Gateway?
- Traffic Pod-to-Pod giữa nodes dùng overlay/direct/VPC-native theo CNI nào?
- Có cần **secondary interfaces/SR-IOV** hoặc host networking thật sự?
- Pod IP range có trùng VPC/VNet/VPN/on-premises không?
- Kết nối tới cloud APIs qua egress NAT, private endpoints hay proxy?

Với network overlay, kiểm tra MTU, underlay reachability, tunnel filtering và bảo vệ traffic phù hợp. Không dùng hình vẽ “veth + docker0” để thay cho dữ liệu của một cloud CNI có cách triển khai khác.

### Bước 4 — Thiết kế chính sách deny/allow

Với Kubernetes có CNI hỗ trợ NetworkPolicy:

1. Xác định những Pod groups/namespaces cần **default-deny ingress hoặc egress**.
2. Tạo allow rules cho các **luồng nghiệp vụ chính xác**, tránh cho cả namespace gọi DATA nếu không cần.
3. Bảo đảm ứng dụng nguồn có egress allow và ứng dụng đích có ingress allow khi cả hai bị cách ly.
4. Bổ sung chính sách cho **DNS, identity services, monitoring, health probes và service discovery** cần thiết.
5. Kiểm tra NodePort/LoadBalancer/hostNetwork traffic và network controls ngoài NetworkPolicy.
6. Với cloud/VPC, giữ node/subnet firewalls và egress controls tương ứng.

**Lưu ý:** Kubernetes NetworkPolicy chuẩn dùng **allowlists cộng dồn** và phụ thuộc plugin. Không thể tạo một rule “deny overriding allow” theo cách nghĩ của ACL truyền thống bằng cách chồng nhiều NetworkPolicy chuẩn.

### Bước 5 — Bảo vệ identity và data plane

Nếu Pod A có thể truy cập Pod B qua network policy, kết nối vẫn cần được **xác thực và phân quyền** theo tác vụ. Sử dụng TLS/mTLS với certificate/identity phù hợp, token được quản lý an toàn, API RBAC và database privileges. Network namespace không xác thực user/service, còn Pod IP có thể thay đổi khi Pod recreated.

### Bước 6 — Pilot có kiểm soát

Chọn namespace hoặc một nhóm Pods lab đại diện, bật những policy tối thiểu, thu:

- Network namespace/interface/routes và listener state;
- Pod/Service/EndpointSlice/NetworkPolicy labels;
- Positive flows: frontend→API, API→DATA đúng port, DNS;
- Negative flows: unrelated Pod→API, frontend→DATA, unauthorized egress;
- CNI flow logs, app latency/errors, DNS và readiness;
- IPv6/cross-node behavior nếu cluster hỗ trợ.

Nếu lỗi, phân tích chính xác **source egress, destination ingress, route, Service NAT và listener**. Đừng tắt toàn bộ policy trước khi có bằng chứng.

### Bước 7 — Rollout, hậu kiểm và rollback

~~~mermaid
flowchart TD
    D["Inventory runtime/CNI/netns và luồng"] --> P["Thiết kế policy + baseline"]
    P --> L["Lab: positive và negative tests"]
    L --> G{"Đúng policy, app SLO, DNS?"}
    G -- "Không" --> F["Sửa selector/routing/allowlist"]
    F --> L
    G -- "Có" --> C["Canary rollout"]
    C --> O["Quan sát CNI logs, app/errors, DNS"]
    O --> H{"Có regression hoặc đường bypass?"}
    H -- "Có" --> R["Rollback có kiểm soát"]
    R --> F
    H -- "Không" --> A["Mở rộng rollout + audit"]
~~~

Change plan nên có **owner, version control, môi trường kiểm thử, tập workloads ảnh hưởng, test evidence, rollback point và thời điểm hậu kiểm**. Đặc biệt, việc thay CNI plugin hoặc đổi networking mode có thể tác động toàn node/cluster, nên đánh giá theo node/zone và khả năng phục hồi ứng dụng.

### Bước 8 — Giám sát lâu dài

Một baseline audit nên theo dõi:

- Tỷ lệ workloads dùng **hostNetwork/privileged/network capabilities** ngoài allowlist.
- Services mới có **external LoadBalancer/NodePort/hostPort**.
- Pod networks không có NetworkPolicy enforce đúng theo môi trường.
- Denied/allowed flows theo namespace/workload identity và port.
- DNS/egress bất thường, các endpoints metadata/internal admin ngoài ý định.
- CNI failures, IPAM exhaustion, MTU blackholes, Pod-to-Pod latency.
- Namespace/Pod labels bị đổi làm policy selector rộng hoặc hẹp ngoài ý định.
- Những thay đổi subnet/firewall/cloud NAT ảnh hưởng kết nối container.

IP và Pod identity có tính **tạm thời**. Khi audit, gắn telemetry với **Pod UID, workload owner, namespace API, node, timestamp và network policy revision** để tránh quy kết sai sau khi Pod được tạo lại.

## 23. Bài tập vận dụng và đáp án gợi ý

### Bài 1 — Hai container cùng bind cổng

Container A và B ở hai Docker bridge-mode network namespaces khác nhau cùng lắng nghe TCP/8080. Có bắt buộc xảy ra port conflict ở host không?

**Gợi ý:** không; chúng thuộc hai netns với socket spaces riêng. Nhưng nếu **publish cùng host IP:port** cho cả hai, mapping host có thể xung đột.

### Bài 2 — Localhost trong hai Pods

Pod `frontend` và Pod `api` ở cùng Kubernetes namespace `sandbox-app`. Frontend dùng `http://localhost:8443` để gọi API ở Pod khác. Vì sao thất bại?

**Gợi ý:** cùng Kubernetes namespace **không có nghĩa cùng Linux netns**. `localhost` của frontend trỏ tới chính Pod frontend. Dùng Service DNS/Pod IP phù hợp và policies.

### Bài 3 — Localhost trong cùng Pod

Một sidecar và application container cùng Pod; app bind `127.0.0.1:8080`. Sidecar có thể gọi localhost này không?

**Gợi ý:** trong mô hình Pod network namespace chung, có thể nếu listener/protocol/port và ứng dụng cho phép; hai container chia sẻ loopback.

### Bài 4 — Veth và bridge

Mỗi Docker container có `eth0`, trong khi host thấy nhiều interface `veth...` gắn bridge. Giải thích đường một packet đi giữa hai container trên cùng bridge.

**Gợi ý:** `eth0`→veth peer→bridge→veth peer của đích→`eth0` đích, theo link state, route, policy và implementation; không mặc nhiên có encryption.

### Bài 5 — `--network host`

Một ứng dụng dùng host networking để giảm độ phức tạp port mapping. Thay đổi này ảnh hưởng gì tới `127.0.0.1`, port binding và network isolation?

**Đáp án:** ứng dụng chia sẻ host network namespace theo runtime, localhost và port space không còn độc lập; cần review host firewall, privileges và exposure.

### Bài 6 — `--network none`

Một container được chạy với network mode `none`. Có thể xem nó là sandbox hoàn chỉnh chống mọi xâm nhập không?

**Đáp án:** không. Networking được hạn chế theo mode, nhưng tiến trình còn dùng kernel, filesystem, permissions và các cơ chế khác. Cần defense in depth.

### Bài 7 — Docker `EXPOSE`

Dockerfile của image ghi `EXPOSE 8080`. Điều này có tự làm node hoặc public IP nhận kết nối TCP/8080 không?

**Đáp án:** không. Đó chủ yếu là metadata; cần thực tế listener, publish/ingress/network path và firewall.

### Bài 8 — Pod không có policy

Kubernetes có namespace `data` chứa database Pod, không có NetworkPolicy nào chọn Pod đó. Namespace khác có route tới Pod IP và app đang listen. Namespace `data` có tự chặn kết nối không?

**Đáp án:** không mặc định. Kubernetes namespace tổ chức tài nguyên API, còn NetworkPolicy/CNI/network controls và app authentication mới có thể giới hạn connection.

### Bài 9 — NetworkPolicy hai hướng

API Pod có allow ingress từ frontend, nhưng frontend bị default-deny egress không có rule cho API. Kết nối sẽ thế nào?

**Gợi ý:** source egress vẫn có thể bị chặn. Cần cả source egress và destination ingress khi các hướng đều được cách ly.

### Bài 10 — Default deny và DNS

Sau khi thêm default-deny egress, Pod không gọi được `api.service.local` dù route tới API vẫn tồn tại. Điều gì nên kiểm tra trước?

**Gợi ý:** DNS resolver access, EndpointSlice/Service, CNI DNAT behavior và NetworkPolicy egress cho DNS; `NXDOMAIN`/DNS timeout khác TCP timeout tới API.

### Bài 11 — Policy có tác dụng hay không?

`kubectl get networkpolicies` hiển thị đối tượng `deny-all`, nhưng Pod vẫn gọi một đích bị cấm. Kết luận cần thêm dữ kiện nào?

**Gợi ý:** policy có chọn đúng Pod/namespace và direction không, CNI hỗ trợ enforce không, peer/hostNetwork path và existing network rules, test từ đúng workload.

### Bài 12 — Overlay và MTU

Pod-to-Pod cùng node hoạt động tốt; cross-node HTTPS đôi khi treo ở response lớn. Lớp nào đáng xem ngoài NetworkPolicy?

**Gợi ý:** MTU/PMTUD và overlay tunnel overhead, underlay routes/firewall, rồi TLS/application logs.

### Bài 13 — Mục tiêu mTLS

Nếu NetworkPolicy đã cho frontend→API TCP/8443, mTLS còn có ích không?

**Đáp án:** có. NetworkPolicy quyết định connectivity L3/L4, còn mTLS mã hóa kênh và xác thực service identity theo cấu hình. API vẫn cần authorization.

### Bài 14 — Quyền kernel

Một Pod được cấp `CAP_NET_ADMIN` để ứng dụng đổi routes. Vì sao đây là một security review item?

**Gợi ý:** ứng dụng có thể thay đổi network state trong phạm vi quyền, làm hỏng route/policy hoặc tăng hậu quả khi bị chiếm quyền; cần giảm privilege và dùng control plane của CNI.

### Bài 15 — Public Pod IP vs public app

Pod có IP private nhưng Service type `LoadBalancer` tạo public endpoint. Có thể khẳng định ứng dụng không internet-facing không?

**Đáp án:** không. Public LB có thể chuyển request vào Pod; phải review source exposure, ingress rules, TLS và app auth.

### Bài 16 — Dựng thiết kế theo tầng

Hãy thiết kế Kubernetes cluster có frontend, API và database. Mô tả **hai luồng ALLOW, hai luồng DENY**, Pod/namespace layout, DNS egress và một cơ chế service authentication.

**Gợi ý:** frontend→API TCP/8443 ALLOW; API→DATA TCP/5432 ALLOW; frontend→DATA DENY; unrelated Pod→API DENY; default deny + allow đúng, DNS egress riêng, mTLS/TLS và DB roles.

## 24. Checklist kiểm tra network namespace và interface container

- [ ] Biết **container/network runtime, CNI, IPAM và network modes** thực đang được dùng.
- [ ] Phân biệt **Linux network namespace**, Kubernetes namespace, Pod, Docker network và VPC subnet.
- [ ] Xác định các netns có **interfaces, IP addresses, routes, loopback và sockets** riêng, cũng như những ngoại lệ dùng chung.
- [ ] Có inventory **Pod IP, node, netns inode/UID khi cần, veth peers hoặc dataplane tương đương**; không dựa tên interface bất biến.
- [ ] Không nhầm `127.0.0.1` trong container với `localhost` của host hay Pod khác.
- [ ] Hiểu containers trong **cùng Pod dùng chung network namespace và port space** theo networking model chuẩn.
- [ ] Xem xét mọi trường hợp **hostNetwork, hostPort, NodePort, external LoadBalancer và Docker published ports**.
- [ ] Hạn chế **privileged containers, CAP_NET_ADMIN, CAP_NET_RAW và truy cập runtime sockets** theo chức năng thực.
- [ ] Đánh giá **overlay/underlay, MTU, DNS, NAT, IPv4/IPv6 và cloud routes** theo CNI thực tế.
- [ ] Không coi NAT/overlay/private Pod IP là **mã hóa hoặc tường lửa tự động**.
- [ ] Dùng **default deny + allowlist theo workload** khi có CNI hỗ trợ NetworkPolicy; test selector và hai hướng traffic.
- [ ] Có policies cho **DNS, identity, health probes, external dependencies và egress** cần thiết.
- [ ] Không suy rằng chỉ có Kubernetes namespace riêng thì lateral movement đã bị chặn.
- [ ] Xác minh direct Pod IP và Service routing theo policy, không chỉ một path qua ingress.
- [ ] Giữ **TLS/mTLS, API authentication/authorization, database permissions và secrets protection** tách khỏi IP-based policy.
- [ ] Cấm/ngăn **direct-to-node/host bypass** ngoài chủ đích bằng cloud firewall, node hardening và admission policies.
- [ ] Cân nhắc **rootless networking** và runtime-specific differences khi so kết quả troubleshooting.
- [ ] Thu **flow logs, Pod UID, workload identity, namespace, node, timestamps và policy revision** theo quyền truy cập thích hợp.
- [ ] Có **positive/negative tests** cho localhost, cross-Pod, cross-node, ingress, egress, IPv6, DNS và thay Pod/node.
- [ ] Sau mỗi thay đổi CNI/NetworkPolicy/ingress/cloud routes, có **canary, rollback, alert và hậu kiểm**.

**Kết luận:** Linux network namespace giúp cô lập **góc nhìn và trạng thái mạng của tiến trình**, còn interfaces như veth, bridge, routes và CNI là **cơ chế chủ động tạo kết nối giữa những không gian đó**. Trong container security, câu hỏi không chỉ là “có netns riêng không?” mà phải là **ai được phép nối tới đâu, dữ liệu đi qua enforcement point nào, danh tính được xác thực ra sao và có bằng chứng kiểm thử không**. Kết hợp netns với NetworkPolicy, firewall/cloud segmentation, TLS/mTLS, least privilege và giám sát mới tạo được lớp bảo vệ có ý nghĩa.

### Tài liệu tham khảo

- [Linux manual — network_namespaces(7)](https://man7.org/linux/man-pages/man7/network_namespaces.7.html): phạm vi cô lập networking trong Linux.
- [Linux manual — namespaces(7)](https://man7.org/linux/man-pages/man7/namespaces.7.html): namespace lifecycle và cách quan sát.
- [Linux manual — veth(4)](https://man7.org/linux/man-pages/man4/veth.4.html): virtual Ethernet pairs.
- [Linux manual — ip-netns(8)](https://man7.org/linux/man-pages/man8/ip-netns.8.html): quản lý named network namespaces.
- [Linux manual — capabilities(7)](https://man7.org/linux/man-pages/man7/capabilities.7.html): phạm vi quyền `CAP_NET_ADMIN`, `CAP_NET_RAW` và các capabilities.
- [Docker Docs — Network drivers](https://docs.docker.com/engine/network/drivers/): bridge, host, none, overlay, macvlan, ipvlan.
- [Docker Docs — Publishing ports](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/): phân biệt container ports và published host ports.
- [Docker Docs — Rootless mode](https://docs.docker.com/engine/security/rootless/): runtime không cần root và các giới hạn.
- [Kubernetes Docs — Networking model](https://kubernetes.io/docs/concepts/services-networking/): networking cơ bản cho Pods/Services.
- [Kubernetes Docs — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): selectors, ingress/egress và policy isolation.
- [Kubernetes Docs — Pods](https://kubernetes.io/docs/concepts/workloads/pods/): containers chia sẻ network namespace trong Pod.
- [Kubernetes Docs — Services](https://kubernetes.io/docs/concepts/services-networking/service/): ClusterIP, NodePort và LoadBalancer.
- [CNI Specification](https://www.cni.dev/docs/spec/): giao diện tích hợp container networking và lifecycle.
- [NIST SP 800-190 — Application Container Security Guide](https://csrc.nist.gov/pubs/sp/800/190/final): threat model, container platform và runtime security.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): bảo vệ theo danh tính và least privilege.
- [OWASP — Kubernetes Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html): thực hành bảo mật Kubernetes.





