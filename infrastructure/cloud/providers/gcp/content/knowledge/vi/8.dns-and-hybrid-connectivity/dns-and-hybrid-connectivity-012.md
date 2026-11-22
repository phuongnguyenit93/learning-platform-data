# Chẩn đoán lỗi DNS, BGP và tunnel VPN trên Google Cloud

> **Chương:** DNS và kết nối hybrid  
> **Bài học:** Chẩn đoán lỗi DNS, BGP và tunnel VPN  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu; qua các tình huống triển khai, người học biết chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Kết nối hệ thống nội bộ doanh nghiệp (on-premises) với Google Cloud thường cần ba thành phần hoạt động đồng thời:

- **DNS:** chuyển tên ứng dụng như `orders.corp.example` thành địa chỉ IP phù hợp.
- **Cloud VPN/IPsec:** tạo đường truyền được mã hóa giữa hai mạng.
- **Cloud Router/BGP:** trao đổi các tiền tố IP để hai mạng tìm được đường tới nhau.

Ba thành phần liên quan chặt chẽ nhưng **không thay thế nhau**. Một tunnel đang `ESTABLISHED` không chứng minh BGP đã học đủ route; BGP `UP` không chứng minh DNS trả đúng bản ghi; DNS giải được IP không bảo đảm firewall và ứng dụng cho phép truy cập.

Bài viết xây dựng phương pháp chẩn đoán từ triệu chứng đến nguyên nhân, ưu tiên **quan sát và đối chiếu cấu hình hai đầu** trước khi thay đổi mạng. Các địa chỉ, domain, project và tên tài nguyên trong ví dụ là giả định dành cho thực hành; thay bằng giá trị thực tế sau khi được phê duyệt.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đường đi của một truy vấn ứng dụng từ DNS đến VPN, định tuyến BGP, firewall và dịch vụ đích.
2. Phân biệt **Cloud DNS private zone**, forwarding zone, inbound forwarding, resolver trên VM và DNS server on-premises.
3. Dùng `dig`, `nslookup`, `getent` và các lệnh `gcloud` chỉ đọc để xác định lỗi DNS nằm ở client, zone, forwarding hay đường trả lời.
4. Phân biệt trạng thái **IKE SA**, **IPsec/CHILD SA**, **VPN tunnel**, **BGP session** và **routes đã học/quảng bá**.
5. Kiểm tra tunnel HA VPN, trạng thái HA gateway, BGP peer, ASN, BGP peering IP, advertisements và learned routes.
6. Nhận biết lỗi do dải IP chồng lấn, định tuyến bất đối xứng, bộ lọc route, ACL/firewall, MTU và dịch vụ đích.
7. Xây dựng quy trình xử lý sự cố có bằng chứng, rollback, cảnh báo và bảo mật cho hệ thống Compute Engine, GKE, Cloud Run, Cloud SQL.

## 2. Mô hình kết nối hybrid cần hình dung trước

Giả sử một doanh nghiệp có mạng on-premises `192.168.50.0/24`, VPC `retail-vpc` trên Google Cloud có dải subnet `10.30.10.0/24` và `10.30.20.0/24`. Hai phía kết nối bằng **HA VPN** với hai tunnel trên hai giao diện HA VPN gateway và Cloud Router trao đổi route bằng BGP.

~~~mermaid
flowchart LR
    Client["ERP on-prem<br/>192.168.50.20"] --> DNSOn["DNS on-prem"]
    Client --> Peer["VPN Gateway on-prem<br/>IKE/IPsec + BGP"]
    DNSOn -. "Chuyển tiếp tên miền nội bộ" .-> Inbound["Cloud DNS inbound forwarding"]
    Peer == "Tunnel A / Tunnel B<br/>IPsec được mã hóa" ==> VPN["HA VPN gateway trên GCP"]
    VPN --> CR["Cloud Router<br/>BGP control plane"]
    VPN --> VPC["VPC retail-vpc<br/>10.30.0.0/16"]
    VPC --> LB["Internal Application Load Balancer"]
    LB --> Run["Cloud Run Orders API"]
    VPC --> DB["Private endpoint / Cloud SQL"]
    Inbound -. "Kết quả DNS" .-> DNSOn
~~~

**Ý nghĩa của sơ đồ:**

- **Data plane:** gói dữ liệu ứng dụng đi qua VPN tunnel và đường định tuyến của mạng Google Cloud, tới IP của dịch vụ đích. **Cloud Router không phải máy chủ chuyển tiếp gói dữ liệu** nằm giữa VPN và VPC.
- **Control plane:** Cloud Router thiết lập BGP peer và quản lý các route học được/quảng bá; việc phiên BGP có ổn hay không ảnh hưởng khả năng định tuyến.
- **Name resolution:** DNS là một đường truy vấn riêng. Đối với on-premises truy vấn private zone trên Cloud DNS, cần cấu hình **inbound forwarding** phù hợp; không mặc định gửi trực tiếp truy vấn đến IP DNS của metadata server trong VM.
- **Ứng dụng và bảo mật:** route đúng chưa đủ. Firewall, load balancer, ingress của Cloud Run, quyền IAM/danh tính gọi dịch vụ và cấu hình cơ sở dữ liệu vẫn phải đúng.

**Cloud VPN** là dịch vụ IPsec **site-to-site**, không phải VPN client để từng laptop “dial in”. **HA VPN** dùng định tuyến động **BGP**; **Classic VPN** hiện chỉ nên xem xét trong tình huống định tuyến tĩnh/di sản và khả năng sản phẩm phù hợp. Khi điều tra một hệ thống cũ, xác định gateway là HA hay Classic trước khi áp quy trình Cloud Router.

## 3. Nguyên tắc chẩn đoán theo lớp

Làm việc theo **chứng cứ có thể kiểm tra**, tránh thay đồng thời DNS, VPN và BGP vì dễ xóa mất dấu vết. Bắt đầu từ triệu chứng người dùng, phạm vi ảnh hưởng và mốc thời gian.

~~~mermaid
flowchart TD
    A["Ứng dụng không truy cập được dịch vụ hybrid"] --> B{"Tra tên DNS có đúng IP không?"}
    B -->|Không| D["Kiểm tra resolver, zone, forwarding, ACL và DNS response"]
    B -->|Có| C{"Tunnel VPN ESTABLISHED?"}
    C -->|Không| E["Kiểm tra peer IP, UDP 500/4500, IKE, PSK, cipher, CHILD SA"]
    C -->|Có| F{"BGP session UP?"}
    F -->|Không| G["Kiểm tra tunnel gắn router, ASN, peer IP, BGP/BFD"]
    F -->|Có| H{"Route tới đích + route chiều về đúng?"}
    H -->|Không| I["Kiểm tra quảng bá/học route, overlap, policy, mode, priority"]
    H -->|Có| J["Kiểm tra firewall, ACL, service, TLS, MTU, timeout"]
    D --> K["Ghi bằng chứng và thử lại từng lớp"]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

Trong thực tế **DNS và tunnel có thể được kiểm tra song song**: nếu tra DNS không được, kiểm tra `dig` tới DNS server on-premises và trực tiếp tại VM GCP; nếu truy vấn qua hybrid mới thất bại, VPN/route/firewall cho DNS có thể là nguyên nhân. Sơ đồ là **trình tự khoanh vùng**, không hàm ý DNS hỏng luôn độc lập với mạng.

### 3.1. Ma trận triệu chứng nhanh

| Triệu chứng | Lớp nghi ngờ đầu tiên | Quan sát xác nhận |
|---|---|---|
| VM GCP giải tên private được, máy on-premises không giải được | Inbound forwarding, resolver on-prem, VPN/route hoặc DNS ACL | So sánh `dig` hai phía, inbound forwarding policy và đường TCP/UDP 53 |
| Một tên miền trả `NXDOMAIN` | Zone/record/search domain hoặc authoritative name server | `dig +noall +answer +comments` và quản lý record |
| `SERVFAIL` hoặc DNS timeout từ một mạng | Forwarder, DNS target, ACL, route trả lời hoặc DNSSEC/upstream | Truy vấn trực tiếp từng resolver, Cloud DNS log và DNS server log |
| VPN báo `FIRST HANDSHAKE` lâu hoặc `NO INCOMING PACKETS` | Peer IP, IKE, đường Internet, UDP 500/4500 | Trạng thái tunnel, Cloud VPN logs, peer appliance logs |
| VPN `ESTABLISHED`, BGP `DOWN` | ASN, peer IP, giao diện BGP, BFD, liên kết tunnel/Cloud Router | `gcloud compute routers get-status` và peer logs |
| BGP `UP`, VPC thiếu route on-prem | Thiếu prefix advertisement, route policy, giới hạn/overlap | Learned routes, effective routes và bảng định tuyến peer |
| Gói từ GCP sang on-prem đi được, chiều ngược thất bại | Route chiều về, ACL/stateful firewall, policy | Route hai đầu, log, truy vấn cùng flow ở hai phía |
| IP truy cập được nhưng hostname không | DNS, search domain, split-horizon hoặc record lỗi | So sánh `dig` với thử kết nối bằng IP |
| DNS đúng, VPN/BGP tốt, TCP timeout | Firewall, listener, LB, port, MTU | `nc`, `curl`, VPC Flow Logs, backend health |
| Chỉ kết nối lớn bị treo | MTU, fragmentation/PMTUD, MSS | Kiểm tra tunnel MTU, thử lưu lượng nhỏ/lớn |
| Lỗi gián đoạn khi một tunnel mất | Chưa đủ HA, failover, BGP timers, đường dự phòng | Trạng thái cả hai tunnel và trạng thái HA VPN gateway |

## 4. Preflight: xác định đúng project, region và phạm vi sự cố

Trước khi chạy chẩn đoán, thu thập:

| Thuộc tính | Ví dụ minh họa | Câu hỏi |
|---|---|---|
| Project ID | `retail-network-prod` | Ai sở hữu network? Shared VPC host hay service project? |
| VPC / subnet / region | `retail-vpc` / `subnet-app` / `asia-southeast1` | Route và DNS policy áp cho đúng VPC không? |
| VPN gateway / tunnel | `ha-vpn-sg` / `tunnel-to-hq-a` | HA VPN hay Classic VPN? Hai đường dự phòng ở trạng thái nào? |
| Cloud Router / BGP peer | `router-hybrid-sg` / `peer-hq-a` | ASN, peer address và status là gì? |
| On-premises gateway | Thiết bị của đội mạng | Ai có quyền cung cấp config/log hai đầu? |
| Source / target | `192.168.50.20` → `10.30.20.10:443` | Có thể tái hiện được bằng IP không? |
| Domain / loại record | `orders.corp.example` / `A` | Client dùng resolver nào? Record dự kiến là gì? |
| Mốc sự cố | 14:10 UTC, từ bản deploy mới | Có thay đổi DNS/VPN/BGP/firewall cùng thời điểm không? |

Kiểm tra danh tính và ngữ cảnh CLI:

~~~bash
gcloud auth list
gcloud config get-value project
gcloud projects describe PROJECT_ID --format="yaml(projectId,name,projectNumber)"
~~~

Các lệnh trên chỉ đọc hoặc xem cấu hình, không tạo tài nguyên. Đối với hạ tầng dùng **Shared VPC**, network, Cloud DNS policy, VPN và Cloud Router có thể thuộc **host project**, còn workload thuộc **service project**; kiểm tra đúng vị trí tài nguyên trước khi kết luận không tồn tại.

### 4.1. Nhận diện điều gì đã thay đổi?

Hỏi người vận hành:

- Bắt đầu lỗi từ khi nào? Một workload hay toàn bộ hệ thống on-premises?
- Chỉ ảnh hưởng một site, một subnet, một vùng hay cả hai chiều?
- Mới thay **DNS zone, DNS policy, BGP advertisement, route priority, firewall/ACL, IKE cipher, pre-shared key, gateway firmware** hay không?
- Có sự kiện **Cloud Router maintenance, BGP flap, rekey IPsec hoặc failover** trùng thời điểm?
- Các dịch vụ GCP nội bộ còn hoạt động, nhưng chỉ đường hybrid bị lỗi hay không?

Giữ ảnh chụp cấu hình và log đã được phân quyền xem trước khi chỉnh sửa. Không đưa pre-shared key, token hoặc cấu hình nhạy cảm nguyên văn lên ticket công khai.

## 5. Chẩn đoán Cloud DNS: bắt đầu từ resolver mà client thực sự dùng

### 5.1. Các kiểu DNS cần phân biệt

| Mô hình | Ý nghĩa | Lỗi thường gặp |
|---|---|---|
| **Public managed zone** | DNS công khai, truy vấn từ Internet theo delegation DNS | NS delegation, cache/TTL, record, DNSSEC |
| **Private managed zone** | DNS chỉ được truy vấn trong các VPC được ủy quyền và các đường truy cập phù hợp | Sai mạng authorized, zone/record không tồn tại |
| **Forwarding zone** | Cloud DNS chuyển truy vấn hậu tố xác định tới DNS target | Forwarding target lỗi, route/ACL phản hồi, mismatch hậu tố |
| **Peering zone** | Cloud DNS chuyển truy vấn theo liên kết DNS peering được hỗ trợ | Chọn sai consumer/producer VPC, vùng khả dụng, xung đột zone |
| **Inbound server policy** | Cho phép hệ thống ngoài VPC gửi truy vấn tới Cloud DNS private resolution bằng forwarding entry point | Chưa bật inbound forwarding, endpoint sai region/VPC, route/ACL |
| **Outbound server policy** | Điều chỉnh đường truy vấn từ VPC tới bộ giải quyết khác theo cấu hình được hỗ trợ | Sai target, lặp forward, mất route trả lời |

Private managed zone gắn với **authorized VPC network**, không phải mặc định mọi project đều tra được. Cloud DNS có quy tắc chọn zone theo tên miền/policy; nếu nhiều vùng DNS và forwarding trùng hậu tố, cần kiểm tra **thứ tự phân giải và hậu tố khớp dài nhất** theo tài liệu thay vì thử đoán.

### 5.2. Kiểm tra trên máy nguồn

Trên Linux, kiểm tra cấu hình resolver trước:

~~~bash
cat /etc/resolv.conf
getent hosts orders.corp.example
dig orders.corp.example A
dig orders.corp.example AAAA
dig orders.corp.example A +noall +answer +comments
~~~

- `getent hosts` sử dụng chuỗi phân giải của hệ điều hành (có thể có `/etc/hosts`, NSS, cache); hữu ích để so sánh với một truy vấn DNS thuần.
- `dig` hỏi DNS theo cấu hình resolver mặc định, kiểm tra mã phản hồi, loại record và TTL.
- `A` là IPv4, `AAAA` là IPv6. Nếu ứng dụng ưu tiên IPv6 nhưng mạng hybrid chưa hỗ trợ IPv6, quá trình kết nối có thể không như mong đợi.
- Nếu `/etc/resolv.conf` trỏ đến local stub resolver (ví dụ `127.0.0.53`), kiểm tra cấu hình DNS thật của systemd-resolved hoặc công cụ quản lý mạng tương ứng.

Truy vấn **một DNS server cụ thể**:

~~~bash
dig @192.168.50.53 orders.corp.example A
dig @192.168.50.54 orders.corp.example A
dig @192.168.50.53 orders.corp.example A +tcp
~~~

Hai máy DNS on-premises trả lời khác nhau có thể do cấu hình zone, split-horizon, cache/TTL hoặc trạng thái đồng bộ. Thử `+tcp` để phát hiện đường TCP/53 hỏng trong khi UDP/53 hoạt động. Tránh kết luận dựa trên một lần truy vấn vì cache có thể che giấu lỗi.

### 5.3. Đọc mã phản hồi DNS

| Kết quả | Nghĩa cơ bản | Hướng điều tra |
|---|---|---|
| `NOERROR` và có record đúng | DNS resolver trả lời phù hợp | Tiếp tục thử kết nối IP/port; vẫn kiểm tra TTL |
| `NOERROR` nhưng không có A/AAAA yêu cầu | Tên có thể tồn tại nhưng thiếu loại record, hoặc câu trả lời rỗng hợp lệ | Kiểm tra record type, CNAME, zone và policy |
| `NXDOMAIN` | Resolver kết luận tên được hỏi không tồn tại trong ngữ cảnh ấy | Kiểm tra suffix, zone/record, authorized VPC, conditional forward |
| `SERVFAIL` | Resolver không giải quyết thành công | Kiểm tra upstream, DNSSEC/ủy quyền, forwarding, log và ACL |
| Timeout | Client không nhận phản hồi đúng hạn | Đường UDP/TCP 53, firewall, route, resolver availability |
| Trả IP sai | Record cũ, nhầm vùng DNS, cache hoặc split-horizon | Hỏi từng DNS server, xem TTL, cấu hình zone/forwarding |

**`ping` đến tên miền thành công không chứng minh bản ghi DNS tối ưu**, và `ping` thất bại cũng chưa chứng minh DNS sai: ICMP có thể bị chặn. Dùng `dig` để kiểm tra phân giải, sau đó dùng công cụ thử **đúng protocol/port** của ứng dụng.

### 5.4. VM Google Cloud tra được, on-premises không tra được

Đối với private zone trên Cloud DNS, máy trong VPC được ủy quyền thường có thể dùng cơ chế resolver của môi trường Google Cloud. Máy on-premises **không tự động** có cùng cơ chế private DNS. Cần cấu hình **Cloud DNS inbound forwarding** cho VPC phù hợp rồi cấu hình DNS on-premises forward các hậu tố cụ thể tới địa chỉ forwarding được cấp.

Thứ tự kiểm tra:

1. Trong **Cloud DNS → Zones**, xác nhận đúng private zone, DNS name, A/AAAA/CNAME và **authorized network**.
2. Từ **VM GCP thuộc VPC được ủy quyền**, truy vấn tên cần tra; ghi DNS server thực tế mà VM đang dùng.
3. Trong **Cloud DNS → DNS policies**, xác nhận **inbound forwarding** được bật cho VPC phù hợp.
4. Xem địa chỉ IP forwarding entry point được Google Cloud tạo tại subnet/vùng thích hợp; không dùng IP của Cloud Router/BGP làm DNS server.
5. Trên DNS on-premises, cấu hình conditional forward **đúng suffix** tới các địa chỉ inbound forwarding cần thiết.
6. Kiểm tra đường VPN/Interconnect, route và ACL/firewall **TCP lẫn UDP port 53** giữa on-premises và forwarding entry point.
7. Hỏi trực tiếp từ on-premises bằng `dig @FORWARDING_IP orders.corp.example A` rồi hỏi qua DNS on-premises để khoanh vùng cấu hình forward.
8. Kiểm tra log của resolver on-premises và Cloud DNS query logging (khi tính năng ghi log đã bật).

Để xem các DNS server policies ở project được phép:

~~~bash
gcloud dns policies list --project=PROJECT_ID
gcloud dns managed-zones list --project=PROJECT_ID
~~~

Để tìm IP dành cho Cloud DNS inbound forwarding (khi có quyền xem):

~~~bash
gcloud compute addresses list --project=PROJECT_ID --filter="purpose=DNS_RESOLVER" --format="table(name,address,subnetwork,region)"
~~~

Nếu không có địa chỉ như dự kiến, xác nhận project, VPC, subnet và inbound forwarding policy trước khi thay đổi.

### 5.5. Google Cloud không giải được tên miền on-premises

Khi workload trong VPC cần tra `erp.corp.example` do DNS on-premises quản lý, mô hình thường là **Cloud DNS forwarding zone** tới DNS target on-premises. Lỗi có thể nằm ở:

- Hậu tố forwarding zone không khớp tên được hỏi.
- Địa chỉ DNS target sai, target không trả lời hoặc ACL chặn.
- Route tới DNS target không đi qua VPN/Interconnect phù hợp.
- **Đường trả lời** từ on-premises về dải nguồn của Cloud DNS forwarding không tồn tại.
- DNS target trả lời từ **địa chỉ khác** IP đã cấu hình làm forwarding target, khiến phản hồi không được chấp nhận.
- Vòng lặp chuyển tiếp: Cloud DNS → DNS on-premises → Cloud DNS cho cùng suffix.

**Trường hợp forwarding target qua VPN/Interconnect theo cơ chế nguồn mặc định:** Cloud DNS có thể gửi truy vấn từ dải proxy `35.199.192.0/19`. On-premises cần cho phép DNS query đến server bằng **TCP/UDP 53** từ dải nguồn này, và có **route trả lời tới `35.199.192.0/19` đi về cùng VPC** qua kết nối hybrid. Đây là dải nguồn dịch vụ DNS forwarding, **không phải dải subnet tự chọn để cấp cho VM**. Với các phương án outbound endpoint mới, nguồn và yêu cầu route có thể khác; phải kiểm tra loại cấu hình đang dùng.

Kiểm tra ở hai đầu:

~~~bash
# Từ VM trong authorized VPC:
dig erp.corp.example A

# Từ hệ thống DNS server on-premises (nếu được cấp quyền):
# xem access log hoặc capture giới hạn TCP/UDP 53 theo quy trình vận hành.
~~~

Đừng tự gắn route `35.199.192.0/19` vào mọi VPC hay mở ACL toàn mạng khi chưa xác nhận đây là mô hình đang sử dụng. Thay đổi route hoặc firewall cần chủ sở hữu mạng kiểm tra để tránh làm gián đoạn dịch vụ.

### 5.6. Cloud DNS logging và cache

Bật **DNS query logging** cho phạm vi được hỗ trợ theo chính sách tổ chức để phân tích tên truy vấn, thời điểm và phản hồi. Bản ghi có thể chứa thông tin tên dịch vụ nội bộ và metadata, nên giới hạn quyền xem/retention. Nếu ứng dụng đang dùng cache ở client, proxy hoặc DNS server trung gian, thay record trên Cloud DNS chưa chắc xuất hiện ngay cho đến khi cache hết TTL. Tránh thay đổi TTL hoặc xóa record chỉ để thử khi chưa xác định resolver nào đang trả lời.

## 6. Chẩn đoán Cloud VPN: tunnel có thực sự được thiết lập?

### 6.1. Ba tầng trạng thái không đồng nhất

| Tầng | Thành phần | Cần quan sát |
|---|---|---|
| **IKE** | IKE SA/Phase 1 | Peer có phản hồi không, IKE version, pre-shared key/authentication và cipher có tương thích không? |
| **IPsec** | CHILD SA/Phase 2 và tunnel | SA/traffic selectors, rekey, encryption, dữ liệu vào/ra có ổn định không? |
| **Routing** | Cloud Router/BGP hoặc static route | Prefix remote và return route đã sẵn sàng chưa? |

Đối với **HA VPN**, route được trao đổi qua BGP. **Tunnel `ESTABLISHED` là điều kiện cần để chuyển traffic**, nhưng route, firewall và ứng dụng vẫn phải kiểm tra. Đối với **Classic VPN** đang dùng static routing, không dùng tiêu chí “BGP phải UP” để đánh giá.

### 6.2. Xem trạng thái qua Google Cloud Console

1. Vào **Hybrid Connectivity / VPN** hoặc trang **VPN** tương ứng, chọn project và region đúng.
2. Mở **Cloud VPN gateways / VPN tunnels**, chọn tunnel bị ảnh hưởng.
3. Ghi trạng thái, thời gian bắt đầu lỗi và thông điệp chi tiết.
4. Đối với **HA VPN**, kiểm tra **cả hai giao diện/tunnel**, peer gateway và trạng thái high availability.
5. Đối chiếu với bảng trạng thái của thiết bị VPN ở phía on-premises.

Một số trạng thái thường thấy:

| Trạng thái | Diễn giải | Bước tiếp theo |
|---|---|---|
| `ESTABLISHED` | Tunnel được thiết lập và đang hoạt động ở mức VPN | Sang BGP, route và kiểm tra traffic |
| `FIRST HANDSHAKE` | Đang thương lượng IKE, có thể thử lại nhiều lần | Kiểm tra đường tới peer và IKE settings |
| `NO INCOMING PACKETS` | Không nhận gói từ VPN peer | Kiểm tra peer IP, Internet path, NAT và thiết bị đối tác |
| `AUTHORIZATION ERROR` | Lỗi ở bước xác thực/thương lượng | Kiểm tra shared secret và thông tin auth hai đầu |
| `NEGOTIATION FAILURE` | Đàm phán hoặc cấu hình tunnel bị từ chối | Xem tunnel detail, IKE/cipher logs và chính sách hỗ trợ |
| `WAITING FOR FULL CONFIG` | Chưa đủ cấu hình để thiết lập hoạt động | Kiểm tra liên kết tunnel/route/Cloud Router |
| `STOPPED` hoặc trạng thái đóng | Tunnel không hoạt động | Điều tra cấu hình hoặc tài nguyên liên quan bị xóa/thay đổi |

Tên/ý nghĩa chi tiết có thể khác giữa trạng thái API, Console và log theo phiên bản; không đoán nguyên nhân chỉ từ màu biểu tượng.

### 6.3. Các lệnh gcloud chỉ đọc

~~~bash
# Liệt kê tunnel VPN trong project và region được phép.
gcloud compute vpn-tunnels list --project=PROJECT_ID

# Xem cấu hình và trạng thái tunnel cụ thể.
gcloud compute vpn-tunnels describe TUNNEL_NAME --project=PROJECT_ID --region=REGION

# Xem trạng thái HA VPN gateway và cấu hình dự phòng.
gcloud compute vpn-gateways get-status HA_GATEWAY_NAME --project=PROJECT_ID --region=REGION
~~~

Nếu lệnh `get-status` không phù hợp với tài nguyên, kiểm tra đây có phải **HA VPN gateway** hay Classic VPN gateway. Tên tunnel/gateway giả định cần thay bằng tên thực tế. Các lệnh đọc có thể yêu cầu IAM quyền xem tài nguyên; `PERMISSION_DENIED` không đồng nghĩa tunnel đã mất.

### 6.4. IKE/IPsec lỗi: đối chiếu hai đầu

| Tình huống | Điều cần xác minh |
|---|---|
| Không thấy packet từ peer | Public peer IP, NAT one-to-one nếu có, đường Internet, ACL/NAT/firewall và thiết bị đối tác |
| IKE SA không tạo được | IKE version, pre-shared key, supported proposal/cipher, authentication, ID/mode phù hợp |
| IKE lên nhưng CHILD SA không ổn | Traffic selectors theo loại VPN, crypto proposal, PFS/DH group, lifetime và rekey |
| Tunnel mất định kỳ | Log rekey/SA_DELETE, mismatch lifetime, ổn định ISP/peer, BGP/BFD flap |
| Kết nối lớn bị treo | MTU/MSS, fragmentation, PMTUD, firewall chặn ICMP cần thiết |
| Chỉ một tunnel hoạt động | Tình trạng interface thứ hai, peer gateway, route quảng bá, điều kiện SLA |
| BGP peer còn DOWN sau khi tunnel lên | Cấu hình Cloud Router/peer IP/ASN, interface, BGP timers và BFD |

Cloud VPN dùng IPsec; đường tới địa chỉ VPN public thường cần **UDP 500**, **UDP 4500** (NAT Traversal) và **ESP** theo mô hình peer/firewall. Với thiết bị nằm sau NAT, kiểm tra tài liệu giới hạn **one-to-one NAT**; không giả định nhiều gateway có thể cùng chia sẻ một public IP qua NAT theo port.

**Không đưa pre-shared key vào dòng lệnh chẩn đoán, nhật ký chung hoặc yêu cầu hỗ trợ công khai.** Đối chiếu bí mật qua kênh quản lý secret được phê duyệt. Với lỗi `no-proposal-chosen`, kiểm tra các tập cipher/proposal giao nhau ở hai phía, không tắt mã hóa để thử “cho dễ kết nối”.

### 6.5. Xem log IPsec trong Cloud Logging

Tại **Logging → Logs Explorer**, giới hạn đúng project và khoảng thời gian xảy ra sự cố. Một bộ lọc tham khảo cho log VPN:

~~~text
resource.type="vpn_gateway"
("initiating IKE_SA" OR "generating IKE_SA_INIT request")
~~~

Một bộ lọc cho peer không phản hồi:

~~~text
resource.type="vpn_gateway"
"establishing IKE_SA failed, peer not responding"
~~~

Có thể tìm các sự kiện `IKE_SA`, `CHILD_SA` và `SA_DELETE` để xác định lỗi handshake, rekey hay tunnel reset. Dữ liệu log phụ thuộc tính khả dụng, cấp quyền và mức ghi log của dịch vụ. Ghi lại **thời điểm, tunnel, peer, loại lỗi**, không sao chép bí mật.

## 7. Chẩn đoán BGP và Cloud Router: tunnel lên nhưng chưa có đường đi

### 7.1. Cloud Router làm việc gì?

**Cloud Router** là thành phần điều khiển BGP và quản lý route động được học/quảng bá qua VPN hoặc Cloud Interconnect. Nó **không nằm trên data plane** để nhận, mã hóa hay chuyển tiếp mọi gói từ VM. Trong HA VPN, phiên BGP được gắn với Cloud Router interface liên kết với tunnel, thường dùng địa chỉ peering **link-local** theo cấu hình hỗ trợ.

BGP có thể ở trạng thái `UP` nhưng ứng dụng vẫn không tới được đích khi:

- Peer không quảng bá prefix cần thiết, hoặc Cloud Router không nhập route vì chính sách/giới hạn.
- Route hiệu lực chọn next hop khác do độ ưu tiên, route type hoặc dải prefix.
- Mạng on-premises không có **return route** tới subnet Google Cloud.
- IP ranges chồng lấn, firewall chặn, ACL trên peer hoặc app không lắng nghe.
- BGP quảng bá route đến một vùng không phải nơi traffic đi theo thiết kế dự kiến.

### 7.2. Xem cấu hình và trạng thái peer

~~~bash
# Cấu hình Cloud Router: ASN, interfaces và bgpPeers.
gcloud compute routers describe ROUTER_NAME --project=PROJECT_ID --region=REGION

# Trạng thái thực tế: BGP session status, learned và advertised routes.
gcloud compute routers get-status ROUTER_NAME --project=PROJECT_ID --region=REGION

# Liệt kê Cloud Router trong project.
gcloud compute routers list --project=PROJECT_ID
~~~

Các trường cần đọc gồm:

| Trường / thông tin | Diễn giải | Câu hỏi chẩn đoán |
|---|---|---|
| `bgp.asn` | ASN của Cloud Router | Có trùng không hợp lệ với peer ASN? |
| `bgpPeers[].peerAsn` | ASN peer được khai báo | Có khớp ASN thực ở thiết bị on-premises? |
| `bgpPeers[].ipAddress` | BGP local peering IP của Cloud Router | Peer on-prem có cấu hình IP này làm remote neighbor? |
| `bgpPeers[].peerIpAddress` | IP BGP phía peer | Có khớp IP local trên peer/router? |
| `interfaces[].linkedVpnTunnel` | Interface Cloud Router gắn VPN tunnel | Có trỏ đúng tunnel và cùng region? |
| BGP peer `status/state/statusReason` | Trạng thái/giải thích lỗi theo API | Session `UP` hay `DOWN`, vì sao? |
| `bestRoutes` / learned routes | Prefix học từ đối tác và route chọn | Có route `192.168.50.0/24`? |
| Advertised routes | Prefix Cloud Router thông báo đối tác | Có subnet `10.30.10.0/24` / `10.30.20.0/24`? |

**ASN và peering IP đều phải khớp cả hai đầu.** Địa chỉ BGP peering không phải DNS server, IP dịch vụ hoặc route default cho VM. Đừng thay ASN hay dải IP peering khi chưa đối chiếu cấu hình của peer.

### 7.3. BGP DOWN dù VPN ESTABLISHED

Thứ tự kiểm tra:

1. Tunnel có thật sự `ESTABLISHED` và đang gắn với interface Cloud Router mong đợi không?
2. Cloud Router và tunnel có cùng region/đúng VPC không?
3. BGP peer có bị `disabled` hoặc có trạng thái lỗi trong `get-status` không?
4. Local/peer peering IP và ASN ở hai đầu có đúng và không xung đột không?
5. Thiết bị on-premises có BGP neighbor trên đúng tunnel, đúng ASN, phiên và authentication (nếu được dùng) không?
6. Chính sách thiết bị on-prem có chặn **BGP TCP/179 bên trong đường tunnel** không? Không mở TCP/179 từ Internet vào gateway VPN công khai.
7. Nếu dùng **Bidirectional Forwarding Detection (BFD)**, trạng thái và timer hai phía có hợp lệ không?
8. Đọc Cloud Router logs, thiết bị on-premises và timeline maintenance/rekey để tìm reset hoặc flap.

Cloud Router có thể tạm reset phiên khi vận hành/di chuyển tác vụ nền; một lần BGP flap không đủ để kết luận gateway hỏng. Kiểm tra tần suất, cơ chế **graceful restart**, hold timer và tác động thực tế đến lưu lượng. Nếu peer quảng bá quá nhiều prefix, Cloud Router có thể đóng phiên theo giới hạn hiện hành; cần xem log và tài liệu giới hạn cụ thể, không mặc định tăng quota để xử lý.

### 7.4. BGP UP nhưng thiếu route

Kiểm tra đồng thời hai chiều:

~~~text
Google Cloud:
  Remote prefix cần học từ on-prem: 192.168.50.0/24
  Local prefix dự kiến quảng bá: 10.30.10.0/24, 10.30.20.0/24

On-premises:
  Nhận prefix Google Cloud: 10.30.10.0/24, 10.30.20.0/24
  Quảng bá prefix on-prem: 192.168.50.0/24
~~~

Các điều cần kiểm tra:

- **BGP advertisements:** Cloud Router đang dùng mặc định hay custom? Có thiếu subnet region khác khi VPC ở **regional dynamic routing mode** so với nhu cầu **global dynamic routing mode**?
- **BGP route policies/filters** ở Cloud Router hoặc on-premises: prefix có bị bỏ, ưu tiên hay thay đổi không?
- **Cloud Router learned routes và VPC effective routes:** route học được có thật sự được cài vào VPC và được chọn theo quy tắc route selection không?
- **Route priority/MED và prefix length:** có tunnel khác hoặc next hop không như dự kiến không?
- **CIDR overlap:** dải on-prem chồng lấn với subnet GCP hoặc route khác; longest-prefix/route type có thể làm lưu lượng đi sai.
- **Return path:** remote router/firewall đã có đường ngược về prefix GCP chưa?
- **VPC Peering không phải transit mặc định:** đừng giả định VPN tại VPC A làm mọi VPC peered B tự đi qua A nếu không có cơ chế và chính sách được hỗ trợ.

**Ví dụ:** Cloud Router nhận `192.168.50.0/24` từ peer nhưng VM chỉ kết nối được tới `192.168.60.10`? Kiểm tra bản ghi DNS có nhầm subnet, hoặc peer thiếu quảng bá `192.168.60.0/24`. Đừng thay firewall khi routing table đã chứng minh đích không có route.

## 8. Chẩn đoán data plane sau khi DNS, tunnel và BGP đều ổn

### 8.1. Thử theo IP và đúng port

~~~bash
# Từ một VM thử nghiệm đã được cấp quyền, kiểm tra DNS.
dig orders.corp.example A +noall +answer

# Thử TCP tới IP/port dự kiến; chỉ thực hiện khi công cụ có sẵn.
nc -vz -w 5 10.30.20.10 443

# Kiểm tra HTTP/TLS với hostname đúng.
curl -v --connect-timeout 5 https://orders.corp.example/health
~~~

**Lưu ý:** `curl -k` bỏ xác minh chứng chỉ, không nên biến thành thao tác khắc phục mặc định. Nếu chứng chỉ sai, điều tra SAN, hostname, chain và thời gian hệ thống. Có thể thử kết nối bằng IP để khoanh vùng định tuyến nhưng HTTPS vẫn cần **SNI/Host** phù hợp; chỉ gọi IP trực tiếp có thể trả kết quả TLS sai dù network vẫn hoạt động.

### 8.2. Firewall và route hai chiều

| Điểm kiểm tra | Câu hỏi |
|---|---|
| VPC firewall ingress | Cho phép nguồn on-prem `192.168.50.0/24` đến target port 443 chưa? |
| VPC firewall egress | Có rule/policy hạn chế outbound và đường trả lời không? |
| On-prem firewall/ACL | Cho phép chiều nguồn/đích và stateful return traffic không? |
| OS firewall/listener | Dịch vụ đang nghe đúng IP/port? |
| Cloud Load Balancer | Frontend, forwarding rule, backend health và policy có hoạt động? |
| Cloud Run | Ingress, authentication, service URL/Load Balancer integration phù hợp? |
| Cloud SQL | Private connection, IP/network, user DB và quyền kết nối phù hợp? |
| Route/priority | Đường đi về có cân bằng hoặc bất đối xứng qua hai tunnel không? |
| MTU/MSS | IPsec làm giảm MTU hữu dụng, gói lớn có bị treo/loss không? |

**VPC Flow Logs** có thể hỗ trợ quan sát traffic của subnet hoặc loại tài nguyên được hỗ trợ, nhưng có cấu hình lấy mẫu và không thay thế packet capture tại peer. **Firewall Rules Logging** cũng cần được bật trên rule phù hợp; không có log **không** luôn chứng minh không có gói.

### 8.3. Network Intelligence Center / Connectivity Tests

**Connectivity Tests** có thể mô phỏng đường đi theo thông tin topology và cấu hình Google Cloud, giúp phát hiện một số lỗi route/firewall. Đối với đường hybrid và thành phần nằm ngoài quyền kiểm soát Google Cloud, kết quả mô phỏng **không thể xác nhận toàn bộ hành vi thiết bị on-premises**. Kết hợp với log/tables ở peer và thử traffic thật trong phạm vi an toàn.

### 8.4. MTU và rekey

IPsec thêm overhead vào gói, vì vậy MTU khả dụng khác với mạng Ethernet thuần. Lỗi MTU thường xuất hiện như:

- Truy vấn DNS nhỏ thành công nhưng truy vấn lớn hoặc TCP/HTTPS gặp timeout.
- Kết nối TCP handshake thành công nhưng tải dữ liệu lớn bị treo.
- Đường một tunnel hoạt động tốt, failover qua tunnel khác có chất lượng kém.

Thử kiểm tra **path MTU**, **TCP MSS clamping** và cơ chế xử lý fragmentation theo thiết bị peer và tài liệu Cloud VPN. Không cố gắng “khắc phục” bằng cách tắt toàn bộ firewall hoặc cho phép traffic vô hạn. Quan sát thêm log **CHILD_SA rekey** khi gián đoạn ngắn lặp lại theo chu kỳ.

## 9. Tình huống thực hành A: on-premises không giải được private DNS

**Kiến trúc giả định:** một ứng dụng ERP trong mạng `192.168.50.0/24` cần gọi `orders.corp.example`. Tên này nằm trong **Cloud DNS private managed zone** và trỏ đến internal Application Load Balancer trong Google Cloud, frontend `10.30.20.10`. Backend là Cloud Run Orders API.

**Triệu chứng:** VM trong VPC tra được record, ERP on-premises nhận DNS timeout; khi thử trực tiếp IP `10.30.20.10:443` từ máy thử on-premises thì kết nối được.

### Bước 1 — Ghi bằng chứng

~~~bash
# Trên VM trong VPC Google Cloud.
dig orders.corp.example A +noall +answer

# Trên máy on-premises.
dig @192.168.50.53 orders.corp.example A +noall +answer +comments

# Nếu đã biết DNS inbound forwarding IP:
dig @FORWARDING_IP orders.corp.example A +noall +answer +comments
~~~

**Diễn giải:** từ GCP có `10.30.20.10`, từ on-premises timeout. IP TCP hoạt động cho thấy có một đường data plane tới frontend, nên ưu tiên kiểm tra đường **DNS forwarding** thay vì sửa BGP indiscriminately.

### Bước 2 — Khoanh vùng

1. DNS on-premises có conditional forward cho `corp.example` hay không?
2. Inbound forwarding đã bật đúng VPC và có forwarding IP thích hợp không?
3. Bên on-prem có route và ACL cho UDP/TCP 53 tới forwarding IP không?
4. Cloud DNS private zone có authorize VPC mà forwarding policy dùng không?
5. Nếu hỏi trực tiếp forwarding IP thành công nhưng hỏi qua `192.168.50.53` thất bại, kiểm tra DNS server on-premises và forwarder rule.
6. Nếu cả hai cách hỏi từ on-prem thất bại, xem VPN/route/ACL đến forwarding IP, sau đó log hai phía.

### Bước 3 — Xác minh sau khi sửa

Hỏi lại từ nhiều client có cùng DNS policy; thử A/AAAA nếu ứng dụng sử dụng cả IPv4/IPv6, kiểm tra TTL và `curl` qua hostname. Ghi lại thay đổi, thời điểm, kết quả và ảnh hưởng đến kết nối API. **Không xóa private zone hoặc biến dịch vụ thành public** để tránh phải chẩn đoán DNS.

## 10. Tình huống thực hành B: VPN lên nhưng BGP không học route

**Kiến trúc giả định:** hai tunnel HA VPN kết nối đến hai interface trên peer gateway. Tunnel A `ESTABLISHED`, tunnel B `ESTABLISHED`. Nhưng VM `10.30.10.20` không truy cập được máy `192.168.50.20` ở trụ sở.

### Bước 1 — Xem HA VPN và Cloud Router

~~~bash
gcloud compute vpn-tunnels describe TUNNEL_A --project=PROJECT_ID --region=REGION
gcloud compute vpn-tunnels describe TUNNEL_B --project=PROJECT_ID --region=REGION
gcloud compute vpn-gateways get-status HA_GATEWAY_NAME --project=PROJECT_ID --region=REGION
gcloud compute routers get-status ROUTER_NAME --project=PROJECT_ID --region=REGION
~~~

**Giả định kết quả:** BGP session A `UP`, BGP session B `DOWN`. Router A học `192.168.60.0/24` nhưng không học `192.168.50.0/24`. Phía peer có prefix filter chỉ xuất `192.168.60.0/24`.

### Bước 2 — Tách hai vấn đề

- **Sự cố route đích:** ngay cả BGP A `UP` cũng không đủ nếu prefix `192.168.50.0/24` không được quảng bá và cài vào VPC.
- **Sự cố độ sẵn sàng:** BGP B `DOWN` có thể làm đường dự phòng không hoạt động theo ý định; cần điều tra riêng ASN, peering IP, peer status, tunnel binding và BFD.

### Bước 3 — Phối hợp sửa ở đúng phía

Đội on-premises xác nhận prefix filter và quảng bá dải cần thiết theo policy được phê duyệt; đội GCP xem learned/effective routes. Đồng thời kiểm tra và khôi phục BGP B theo cấu hình hai bên. Sau đó thử **hai chiều**, xác nhận route từ on-prem đến `10.30.10.0/24`, kiểm tra failover và chỉ chốt khi cả yêu cầu kết nối lẫn dự phòng đáp ứng mục tiêu.

**Không nên** tự sửa route mặc định `0.0.0.0/0` hoặc mở `0.0.0.0/0` trong firewall khi mục tiêu chỉ là `192.168.50.0/24`.

## 11. Tình huống thực hành C: tunnel flapping hoặc hiệu năng giảm theo chu kỳ

**Triệu chứng:** sau vài chục phút hoặc một khoảng lặp, các phiên truyền dữ liệu lớn bị ngắt 10–30 giây, rồi tự phục hồi. Dashboard cho thấy IKE/CHILD SA rekey cùng thời điểm BGP session reset.

Quy trình:

1. Lấy timeline 24 giờ từ Cloud VPN logs, Cloud Router logs và thiết bị peer, đồng bộ múi giờ UTC.
2. Xem có `SA_DELETE`, thay đổi cipher, mismatch lifetime, NAT timeout, chuyển gateway hay maintenance cùng thời điểm.
3. Kiểm tra thông số IKE/IPsec phù hợp giữa hai đầu; với rekey, peer nên hỗ trợ tạo SA mới trước khi SA cũ hết hạn theo cơ chế của thiết bị.
4. Kiểm tra BGP graceful restart, hold timer, BFD và chính sách failover; lưu ý Cloud Router có thể có gián đoạn phiên control plane khi bảo trì mà **không nhất thiết làm traffic mất** nếu cơ chế khôi phục hoạt động đúng.
5. Đo packet loss và throughput theo từng tunnel, kiểm tra MTU/MSS và CPU/crypto capacity trên peer.
6. Khi cần thay đổi, xử lý **từng tunnel**, giữ đường dự phòng còn hoạt động theo change window; rollback nếu metric xấu đi.
7. Xác nhận sau khi sửa: số lần reset giảm, độ trễ/packet loss ở mức chấp nhận được, ứng dụng hoạt động xuyên suốt một chu kỳ rekey.

Một lần log reset chưa đủ kết luận Google Cloud bị lỗi; cần đối chiếu hai đầu và dữ liệu traffic để xác định ảnh hưởng thực sự.

## 12. Giám sát, cảnh báo và Runbook vận hành

### 12.1. Tín hiệu cần theo dõi

| Nhóm tín hiệu | Chỉ số hoặc sự kiện | Hành động |
|---|---|---|
| VPN | Trạng thái từng tunnel, packet vào/ra, dropped packets, số lần handshake thất bại | Cảnh báo nếu tunnel mất hoặc traffic giảm bất thường |
| HA | Hai interface/tunnel và trạng thái HA gateway | Đánh giá khả năng failover, không chỉ “có một tunnel UP” |
| BGP | Session status, thay đổi learned/advertised prefixes, flap/restart | Kiểm tra route, peering và device đối tác |
| DNS | Tỉ lệ `SERVFAIL`/timeout, forwarding target, query latency | Điều tra resolver/forwarder/return route |
| VPC | Firewall deny, flow logs, bất thường egress/ingress | Khoanh vùng policy, route, target |
| Ứng dụng | p95/p99 latency, HTTP 5xx, database connection errors | Liên kết mạng với trải nghiệm người dùng |
| Chi phí | Tunnel/VPN traffic, logging, egress, Monitoring | Đặt budget/alert; cân đối mức log retention |

Đặt alert theo **mức ảnh hưởng**, ví dụ: “cả hai tunnel quan trọng đều xuống”, “một tunnel xuống làm mất redundancy”, “BGP route quan trọng biến mất” và “DNS timeout vượt ngưỡng”. Từng tình huống có mức ưu tiên khác nhau; cảnh báo nên có **người chịu trách nhiệm, liên hệ on-prem và runbook**.

### 12.2. Mẫu ghi nhận sự cố

~~~text
Incident ID:
Thời điểm bắt đầu (UTC) / Time zone:
Người báo cáo / Mức ảnh hưởng:
Project / VPC / Region:
Cloud DNS zone + authorized VPC:
On-prem resolver / Cloud DNS forwarding:
Source IP:port / Destination FQDN, IP:port:
Tunnel A / Tunnel B trạng thái:
Cloud Router và BGP peer trạng thái:
Learned routes / advertised routes:
Kết quả dig / getent / nc / curl:
Firewall / ACL / LB / ứng dụng:
Thay đổi gần nhất / log timestamp:
Giả thuyết và bằng chứng:
Thay đổi đã phê duyệt / rollback:
Kết quả thử hai chiều và failover:
Owner / Biện pháp phòng ngừa:
~~~

### 12.3. Quy trình ứng cứu theo giai đoạn

1. **Đánh giá tác động:** phân loại sự cố DNS đơn lẻ, mất tuyến, mất dự phòng hay mất kết nối toàn bộ.
2. **Khôi phục an toàn:** nếu có đường dự phòng đã được thiết kế, chọn phương án theo runbook và approval phù hợp; không chỉnh hàng loạt.
3. **Lưu bằng chứng:** cấu hình, learned routes, tunnel trạng thái, log IKE/BGP, DNS response, test ứng dụng.
4. **Khoanh vùng đúng lớp:** dùng ma trận triệu chứng, tránh thử nghiệm ngẫu nhiên hoặc “mở tất cả cổng”.
5. **Thay đổi được duyệt:** một yếu tố mỗi lần; ghi thời gian và thay đổi trước/sau, giữ rollback.
6. **Xác minh thực tế:** DNS đúng trên cả hai phía, BGP route đi/về hợp lệ, traffic/ứng dụng và failover hoạt động.
7. **Post-incident review:** giải thích root cause dựa vào bằng chứng, thêm alert và hành động phòng ngừa.

## 13. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| “Tunnel xanh nghĩa là ứng dụng chắc chắn hoạt động” | Không chứng minh BGP route, firewall, DNS, backend | Kiểm tra từng lớp và hai chiều |
| “BGP UP thì mọi subnet on-prem đã được học” | Prefix filter/quảng bá/route selection có thể loại prefix | Xem learned/advertised/effective routes |
| Dùng IP BGP peering làm DNS server | BGP IP không cung cấp dịch vụ DNS | Dùng resolver/forwarding entry point được hỗ trợ |
| Cho on-prem hỏi trực tiếp private zone mà chưa cấu hình inbound forwarding | Private zone có ranh giới VPC | Thiết kế DNS inbound forwarding |
| Chỉ mở UDP 53 | DNS có thể cần TCP 53 | Kiểm tra cả TCP/UDP 53 theo mạng và resolver |
| Quên route trả lời `35.199.192.0/19` khi dùng forwarding target mặc định on-prem | DNS server nhận query nhưng trả lời sai đường | Kiểm tra route/ACL hai chiều và loại outbound endpoint |
| Chỉnh mọi VM firewall khi IKE tunnel còn DOWN | Sai lớp vấn đề | Khắc phục peer/IKE trước |
| Mở TCP/179 ra Internet để “sửa BGP” | BGP của HA VPN chạy trong ngữ cảnh kết nối hybrid, làm tăng rủi ro | Kiểm tra BGP bên trong tunnel và ACL liên quan |
| Đổi ASN hoặc peer IP khi chưa đồng bộ hai phía | Có thể làm mất cả kết nối | Đối chiếu config Cloud Router và router on-prem |
| Xóa một route để thử khi production đang chạy | Có thể gây mất tuyến, traffic bất đối xứng | Thử trong sandbox, change window và rollback |
| Dùng `ping` làm tiêu chuẩn duy nhất | ICMP có thể bị chặn, DNS/TCP vẫn độc lập | Dùng `dig` + thử protocol/port thực tế |
| Gộp mọi lỗi vào “VPN chậm” | DNS timeout, MTU, BGP flap và CPU peer có biểu hiện khác nhau | Quan sát log/metric theo timeline |
| Chỉ theo dõi tunnel A | Bỏ sót đường dự phòng hỏng | Theo dõi cả hai tunnel và HA topology |
| Thu thập log bằng tài khoản Owner | Thừa quyền và tăng rủi ro | Cấp role đọc phù hợp, bảo vệ dữ liệu log |

## 14. Bài tập tự đánh giá

### Bài 1 — DNS

VM `10.30.10.20` trong VPC tra `erp.corp.example` qua forwarding zone và nhận timeout. DNS server on-prem `192.168.50.53` ghi nhận request có IP nguồn `35.199.194.10` nhưng gửi phản hồi về default gateway Internet. Tunnel `ESTABLISHED`, BGP `UP`.

**Câu hỏi:** Nghi ngờ lỗi ở lớp nào? Route nào cần kiểm tra trên on-prem? Vì sao không ưu tiên sửa CNAME/A record trước?

**Gợi ý:** Đường trả lời của Cloud DNS forwarding target về dải `35.199.192.0/19` theo cơ chế mặc định chưa quay lại VPC đúng đường; DNS server đã nhận query nên record chưa phải giả thuyết mạnh nhất. Kiểm tra kiểu outbound forwarding hiện tại trước khi bổ sung route.

### Bài 2 — VPN

Tunnel báo `NO INCOMING PACKETS`, trên peer thiết bị không có bản ghi IKE từ địa chỉ HA VPN gateway. Cloud Router BGP cũng `DOWN`.

**Câu hỏi:** Bước kiểm tra thứ tự là gì? Có nên đổi BGP ASN ngay không?

**Gợi ý:** Kiểm tra peer IP, Internet path, NAT, ACL/UDP 500/4500/ESP và trạng thái thiết bị trước; chưa có tunnel nên chưa đủ bằng chứng để đổi ASN.

### Bài 3 — BGP

HA VPN tunnel `ESTABLISHED` và BGP `UP`. Cloud Router nhận `192.168.60.0/24`; ứng dụng lại cần `192.168.50.20`.

**Câu hỏi:** Vì sao BGP UP vẫn không tới được đích? Hai đầu cần kiểm tra gì?

**Gợi ý:** Chưa có learned/effective route cho `192.168.50.0/24`; cần kiểm tra prefix advertisement/filter, route selection và return path.

### Bài 4 — Ứng dụng

`dig orders.corp.example A` trả `10.30.20.10` ở cả hai phía. Hai tunnel HA VPN `ESTABLISHED` và BGP học đủ route. `curl` báo timeout nhưng `nc` kết nối đến `10.30.20.10:443` được.

**Câu hỏi:** Lỗi nào còn có khả năng? Vì sao `nc` thành công chưa đủ xác nhận ứng dụng?

**Gợi ý:** TCP handshake có thể hoàn tất nhưng TLS/SNI, HTTP routing, backend health, ứng dụng, xác thực hoặc MTU/lưu lượng lớn vẫn lỗi. Kiểm tra `curl -v`, LB và log backend.

### Bài 5 — Mất dự phòng

Một trong hai tunnel HA VPN bị lỗi sau nâng cấp peer, tunnel còn lại truyền dữ liệu bình thường.

**Câu hỏi:** Được coi là “mọi thứ ổn” không? Cần làm gì trước khi kết luận SLA và khả năng chịu lỗi?

**Gợi ý:** Dịch vụ có thể chưa gián đoạn nhưng redundancy đã suy giảm. Kiểm tra topology, HA gateway status, BGP/route trên cả hai đường, khả năng failover và yêu cầu SLA cụ thể.

## 15. Checklist chẩn đoán cuối bài

- [ ] Đã biết project, VPC, region, subnet, source/destination, tên DNS và thời điểm sự cố.
- [ ] Đã phân biệt DNS resolution với kết nối IP/TCP và quyền ứng dụng.
- [ ] Đã so `dig` từ VPC và on-premises, kiểm tra resolver/record/zone/forwarding policy.
- [ ] Đã kiểm tra inbound hoặc outbound Cloud DNS forwarding đúng mô hình, TCP/UDP 53 và return route.
- [ ] Đã xác minh trạng thái **từng** tunnel VPN cùng peer IP, IKE/IPsec và log/rekey.
- [ ] Đã xác minh HA topology thay vì chỉ xem một tunnel xanh.
- [ ] Đã kiểm tra Cloud Router `describe` và `get-status`: ASN, peering IP, interface, BGP state.
- [ ] Đã kiểm tra learned routes, advertised routes, effective routes và return path hai đầu.
- [ ] Đã loại trừ overlap CIDR, firewall/ACL, LB/backend, service listener và MTU.
- [ ] Đã bảo vệ shared secret, thông tin định tuyến nhạy cảm và quyền truy cập logs.
- [ ] Đã kiểm thử sau thay đổi trên đúng hostname/IP/port, cả hai chiều và đường dự phòng.
- [ ] Đã ghi bằng chứng, owner, rollback và hành động giám sát/phòng ngừa.

## 16. Tài liệu Google Cloud chính thức

Tài liệu dưới đây trình bày trạng thái, cú pháp lệnh và phạm vi sản phẩm có thể thay đổi theo phiên bản. Kiểm tra phần tương ứng trước khi thay đổi môi trường thật:

- [Troubleshoot Cloud DNS](https://docs.cloud.google.com/dns/docs/troubleshooting)
- [Create a Cloud DNS forwarding zone](https://docs.cloud.google.com/dns/docs/zones/forwarding-zones)
- [Cloud VPN overview](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Check Cloud VPN status](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/checking-vpn-status)
- [Cloud VPN troubleshooting](https://docs.cloud.google.com/network-connectivity/docs/vpn/support/troubleshooting)
- [Troubleshoot BGP sessions](https://docs.cloud.google.com/network-connectivity/docs/router/support/troubleshoot-bgp-sessions)
- [Troubleshoot BGP routes and route selection](https://docs.cloud.google.com/network-connectivity/docs/router/support/troubleshoot-bgp-routes)
- [View Cloud Router details](https://docs.cloud.google.com/network-connectivity/docs/router/how-to/viewing-router-details)
- [Cloud VPN best practices](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/best-practices)

**Điểm cần nhớ:** Điều tra kết nối hybrid hiệu quả cần tách **tên (DNS)**, **đường mã hóa (IPsec/VPN)**, **đường định tuyến (BGP/route)** và **khả năng phục vụ ứng dụng (firewall/LB/service)**. Chẩn đoán bằng trạng thái và dữ liệu từ **cả Google Cloud lẫn on-premises**, kiểm tra lưu lượng **hai chiều**, sửa đúng lớp hỏng và xác minh **đường dự phòng**. Phương pháp này giúp duy trì hệ thống Compute Engine, GKE, Cloud Run và dữ liệu ổn định, an toàn và có thể kiểm soát chi phí.
