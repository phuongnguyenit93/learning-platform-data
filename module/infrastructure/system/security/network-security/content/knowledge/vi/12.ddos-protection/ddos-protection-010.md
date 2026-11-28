# Anycast và scrubbing service trong phòng chống DDoS

Giả sử một ứng dụng bán vé đặt máy chủ gốc (*origin*) ở một trung tâm dữ liệu, có băng thông kết nối Internet 5 Gbit/s. Vào ngày mở bán, hệ thống nhận một luồng truy cập bất thường với tốc độ lớn hơn nhiều so với đường kết nối đó. Firewall tại origin dù có rule chặn chính xác cũng **không cứu được đường truyền đã bị bão hòa trước khi gói tới firewall**. Cần một lớp hấp thụ và lọc lưu lượng ở **thượng nguồn**, trước điểm nghẽn.

Hai thành phần quan trọng trong kiến trúc bảo vệ DDoS là **Anycast** và **scrubbing service**. Anycast giúp một địa chỉ/tiền tố mạng được phục vụ ở nhiều vị trí và được định tuyến tới một trong các vị trí đó. Scrubbing service dùng năng lực mạng và bộ lọc chuyên dụng để tách lưu lượng có dấu hiệu tấn công ra khỏi lưu lượng hợp lệ, sau đó chuyển phần lưu lượng sạch tới hệ thống cần bảo vệ.

Bài thuộc chương **DDoS** của module **SECURITY_NETWORK_SECURITY**. Mối liên hệ với firewall, phân đoạn mạng, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, bảo mật cloud và threat modeling đặc biệt rõ: khả năng duy trì dịch vụ khi bị tấn công không chỉ phụ thuộc bộ lọc, mà còn phụ thuộc **đường đi mạng, xác thực/ủy quyền, dung lượng, giám sát và quy trình xử lý sự cố**.

## 1. Vấn đề gốc: DDoS làm cạn loại tài nguyên nào?

**Distributed Denial of Service (DDoS)** là hoạt động từ nhiều nguồn hoặc nhiều điểm phát nhằm làm suy giảm tính sẵn sàng của dịch vụ. Mục tiêu có thể là băng thông, packet-processing capacity, bảng trạng thái kết nối hoặc năng lực ứng dụng.

| Nhóm áp lực | Chỉ số thường quan sát | Điểm nghẽn điển hình | Lớp phòng vệ phù hợp |
|---|---|---|---|
| **Volumetric L3/L4** | Gbit/s, packet/s, interface utilization | Đường Internet, uplink, router, cổng trung tâm dữ liệu | Upstream mitigation, Anycast capacity, scrubbing, ISP phối hợp |
| **Packet-rate / forwarding exhaustion** | Packet/s, CPU của thiết bị mạng, dropped packets | Router, firewall, thiết bị xử lý flow | Lọc sớm, hạ tầng forwarding có dung lượng, scrubbing |
| **State/connection exhaustion** | New connections/s, concurrent sessions, SYN backlog, connection table | Stateful firewall, load balancer, máy chủ | Connection protection, state-aware mitigation, rate control |
| **Application-layer L7** | Request/s, p95/p99 latency, CPU/DB pool, tỉ lệ lỗi | API, xác thực, tìm kiếm, database | WAF, bot control, cache, quota, xác thực, bảo vệ backend |
| **Phụ thuộc chung** | DNS errors, gateway 5xx, authentication failures | DNS, IdP, API gateway, logging, cloud control plane | Phân tán phụ thuộc, hạn chế quyền, giám sát và kế hoạch dự phòng |

Một đợt tấn công có thể đồng thời gây áp lực ở nhiều lớp. Do đó **băng thông lớn không tự động giải quyết DDoS L7**, và WAF có logic tốt cũng không giúp được khi gói bị chặn ở đường truyền trước khi tới WAF.

### 1.1. Ba chỉ số dễ bị nhầm

- **bps (bits per second):** tốc độ dữ liệu trên đường truyền; dùng để nhìn rủi ro bão hòa băng thông.
- **pps (packets per second):** số packet thiết bị phải chuyển tiếp hoặc phân loại; gói nhỏ có thể tạo pps lớn dù bps không quá cao.
- **rps (requests per second):** số yêu cầu ở tầng ứng dụng; một request tạo báo cáo có thể nặng hơn nhiều request đọc trang tĩnh.

Không suy khả năng chống DDoS từ một con số “tối đa 100 Gbit/s” đơn lẻ: cần biết **vị trí đo, dung lượng thực tế đang khả dụng, phân bố địa lý, pps, khả năng xử lý phiên, lưu lượng sạch được chuyển về origin và những giới hạn theo hợp đồng**.

## 2. Anycast là gì?

**Anycast** là cách nhiều điểm phục vụ cùng một địa chỉ IP hoặc tiền tố địa chỉ có thể được quảng bá/định tuyến trong mạng. Internet routing, thường qua **Border Gateway Protocol (BGP)** ở quy mô liên mạng, chọn một đường phù hợp để đưa packet đến một địa điểm quảng bá địa chỉ đó.

Một ví dụ trực quan: mạng cung cấp dịch vụ có ba điểm hiện diện (*Point of Presence — PoP*) tại ba khu vực. Cả ba đều sẵn sàng tiếp nhận traffic hướng tới cùng dịch vụ Anycast. Các mạng bên ngoài sẽ đưa traffic đến PoP được BGP chọn theo thuộc tính định tuyến và chính sách.

~~~mermaid
flowchart TB
    U1["Nguồn người dùng A / mạng A"] --> R1["Internet / quyết định BGP"]
    U2["Nguồn người dùng B / mạng B"] --> R2["Internet / quyết định BGP"]
    U3["Nguồn người dùng C / mạng C"] --> R3["Internet / quyết định BGP"]
    R1 --> P1["PoP 1: Anycast service"]
    R2 --> P2["PoP 2: Anycast service"]
    R3 --> P3["PoP 3: Anycast service"]
    P1 --> S["Dịch vụ hoặc hệ thống xử lý khu vực"]
    P2 --> S
    P3 --> S
~~~

**Sơ đồ là minh họa một thời điểm định tuyến**, không hứa mỗi nguồn sẽ luôn gắn với một PoP nhất định. BGP có thể chọn tuyến khác sau thay đổi topology hoặc chính sách. PoP xử lý traffic theo chức năng đã triển khai: DNS, CDN, reverse proxy, lọc DDoS hoặc dịch vụ mạng khác.

### 2.1. Anycast không đồng nghĩa với “vị trí địa lý gần nhất”

Đường được chọn phụ thuộc vào routing policy, local preference, AS path, peering, quy tắc của ISP và trạng thái tuyến. PoP được chọn có thể **không gần nhất theo kilomet**, và không nhất thiết có độ trễ thấp nhất trong mọi thời điểm.

Những điều cần nhớ:

1. **BGP quyết định đường đi theo chính sách mạng**, không nhận trực tiếp thông tin CPU, băng thông ứng dụng hay mức sử dụng cơ sở dữ liệu.
2. Một PoP có thể nhận tỷ lệ traffic lớn hơn dự tính, kể cả khi các PoP khác còn dư dung lượng.
3. Rút một tuyến hoặc đổi thuộc tính quảng bá có thể chuyển traffic sang nơi khác, nhưng tốc độ hội tụ và tác động lên session phụ thuộc tình trạng mạng.
4. Anycast cung cấp một **cơ chế phân phối và điều hướng**, không phải một bộ lọc xác định packet có độc hại hay không.

### 2.2. Anycast khác Unicast và DNS traffic steering

| Cơ chế | Đơn vị lựa chọn | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **Unicast** | Một IP đích gắn với endpoint theo cách định tuyến thông thường | Dễ hình dung, có thể phù hợp cho origin đơn | Một uplink/vị trí riêng có thể thành điểm nghẽn |
| **Anycast** | Nhiều địa điểm quảng bá cùng địa chỉ/tiền tố; BGP chọn tuyến | Phân tán traffic theo mạng và hỗ trợ chuyển vị trí phục vụ | Chênh lệch tải, route convergence, tính ổn định session |
| **DNS geo/latency steering** | DNS trả IP khác nhau dựa trên chính sách/khả năng quan sát resolver | Điều hướng theo tên miền và chính sách DNS | Cache/TTL, lựa chọn resolver, không can thiệp được traffic tới IP đã biết |
| **Global load balancing ở ứng dụng** | Proxy/gateway quyết định backend theo health, latency, identity hoặc policy | Có thể tính đến trạng thái dịch vụ | Phải bảo vệ chính lớp proxy và đường tới proxy |

Các phương pháp **có thể kết hợp**: DNS đưa người dùng tới dải IP Anycast của CDN; PoP Anycast giải mã HTTPS và load balance đến backend khu vực; scrubbing loại lưu lượng bất thường trước khi traffic tới origin.

### 2.3. Anycast và kết nối có trạng thái

Với UDP request/response ngắn, chuyển giữa các địa điểm có thể dễ quản lý hơn, tùy ứng dụng. Với TCP, QUIC, session TLS hoặc ứng dụng giữ state tại PoP, thay đường giữa phiên có thể khiến gói đến một nơi không có session state tương ứng.

Vì vậy không được giả định rằng **Anycast tự động bảo toàn tất cả session khi PoP lỗi**. Giải pháp có thể sử dụng kiến trúc proxy, xử lý state, định tuyến ổn định hoặc cơ chế reconnect của client; cần thử trên workload thực tế, bao gồm WebSocket, HTTP/2, HTTP/3 và các phiên dài.

## 3. Anycast hỗ trợ phòng chống DDoS bằng cách nào?

Anycast có thể giúp **phân tán một phần tải đến nhiều điểm có năng lực xử lý**, tránh đặt mọi lưu lượng trên một cổng Internet nhỏ. Ví dụ các nguồn ở những mạng khác nhau có thể được chuyển đến các PoP khác nhau, nơi nhà cung cấp có thể kiểm tra và lọc ở gần điểm vào.

Tuy nhiên:

- Một nguồn hoặc nhóm mạng lớn có thể vẫn dồn tải vào một PoP.
- Một đợt tấn công đủ lớn có thể vượt dung lượng của một PoP, một tuyến peering hoặc một mạng cung cấp, dù tổng dung lượng toàn cầu rất cao.
- Các luồng đã bị chặn từ upstream trước khi đến dịch vụ sẽ không được chữa bằng cách thêm CPU ở origin.
- Tấn công L7 nhắm vào API tính toán nặng có thể vượt qua phân phối BGP rồi làm cạn backend chung.
- Routing changes có thể làm traffic đổ sang khu vực khác, tạo hiệu ứng dây chuyền nếu capacity planning chưa chuẩn bị.

**Anycast không phải “tấm khiên DDoS” độc lập**. Nó đặc biệt hữu ích khi kết hợp với scrubbing/edge enforcement, năng lực mạng và cơ chế điều phối sự cố.

## 4. Scrubbing service là gì?

**Scrubbing** là quá trình xử lý lưu lượng tại hạ tầng có năng lực giảm thiểu DDoS nhằm nhận diện và loại bỏ/giới hạn phần lưu lượng không mong muốn theo policy, đồng thời giữ phần lưu lượng hợp lệ tiếp tục tới dịch vụ.

Một **scrubbing service** có thể là dịch vụ chuyên dụng của ISP, nhà cung cấp chống DDoS, cloud provider hoặc hệ thống doanh nghiệp tự vận hành. Nó thường có:

- Kết nối mạng và khả năng xử lý ở upstream với dung lượng phù hợp.
- Lọc dựa trên protocol, packet/flow statistics, reputational signals, challenge hoặc chính sách L7 nếu là điểm xử lý HTTP.
- Hệ thống giám sát bất thường, chính sách kích hoạt và giao diện điều phối cùng đội ứng cứu.
- Đường chuyển tiếp **clean traffic** về origin sau lọc.
- Các cơ chế dự phòng, giám sát latency/loss và bản ghi quyết định mitigation.

**Scrubbing không có nghĩa 100% lưu lượng xấu sẽ bị loại hoặc 100% lưu lượng tốt sẽ đi qua.** Khả năng phân biệt phụ thuộc vào vị trí và kỹ thuật kiểm tra, tín hiệu có sẵn, traffic mã hóa, các rule được cấu hình, giới hạn năng lực và chất lượng tuning.

### 4.1. Mô hình luôn bật và kích hoạt khi cần

| Mô hình | Đường đi bình thường | Ưu điểm | Đánh đổi |
|---|---|---|---|
| **Always-on** | Lưu lượng đi qua edge/scrubbing thường xuyên | Quan sát liên tục, tránh độ trễ kích hoạt chuyển tuyến khi sự cố bắt đầu | Phụ thuộc nhà cung cấp/đường chuyển tiếp thường trực; độ trễ và chi phí có thể tăng |
| **On-demand** | Lưu lượng đi đường thường cho đến khi phát hiện sự cố và điều hướng sang scrubbing | Giảm thay đổi đường bình thường, có thể tối ưu chi phí | Có khoảng thời gian phát hiện/kích hoạt/hội tụ; chuyển route có thể ảnh hưởng phiên |
| **Hybrid** | Dịch vụ HTTP qua edge luôn bật, tài nguyên IP/UDP khác dùng scrubbing theo nhu cầu | Phù hợp loại traffic và mức độ bảo vệ khác nhau | Nhiều mặt phẳng policy, dễ bỏ sót endpoint hoặc nhầm trạng thái bảo vệ |

Không chọn chỉ theo giá. Cần xem RTO/RPO liên quan (nếu áp dụng), mức độ nhạy cảm dịch vụ, **thời gian từ phát hiện đến mitigation hiệu lực**, mô hình lưu lượng, khả năng kiểm chứng failover và trách nhiệm vận hành.

## 5. Lưu lượng được điều hướng và làm sạch như thế nào?

Có hai kiến trúc thường gặp, tùy loại dịch vụ và nhà cung cấp.

### 5.1. Reverse proxy / CDN cho HTTP(S)

Client kết nối đến endpoint của nhà cung cấp edge. Tại edge, traffic có thể được lọc theo chính sách mạng và HTTP, sau đó được chuyển đến origin:

~~~mermaid
flowchart LR
    C["Client / nguồn Internet"] --> E["Anycast PoP / CDN / WAF"]
    E --> D{"Phân loại lưu lượng"}
    D -->|"Hợp lệ hoặc phù hợp policy"| G["Kết nối bảo vệ đến origin"]
    D -->|"Bị hạn chế"| B["Drop / Rate limit / Challenge"]
    G --> O["Origin / API backend"]
    E -.->|"Logs / metrics"| M["Giám sát và điều phối"]
    B -.->|"Action / reason"| M
~~~

Edge có thể kết thúc TLS, xử lý cache, quota, WAF và bot controls tùy sản phẩm. **Nếu traffic được TLS pass-through**, nhà cung cấp có thể không nhìn được HTTP URI/body để áp những chính sách L7 đòi hỏi dữ liệu đó; phải xác minh điểm kết thúc TLS và phạm vi thông tin nhà cung cấp xử lý.

Với HTTP, việc trả lời trực tiếp từ cache ở PoP còn giúp giảm số request sạch cần chuyển về origin. Nhưng cache không thích hợp cho mọi dữ liệu: cookie, thông tin cá nhân, nội dung phân quyền theo user/tenant và request ghi phải có chính sách rõ.

### 5.2. BGP diversion tới scrubbing center cho IP service

Với dịch vụ cần giữ IP hoặc giao thức không tiện đặt sau reverse proxy, hạ tầng có thể dùng điều hướng định tuyến:

~~~mermaid
flowchart TB
    I["Internet: traffic đến prefix được bảo vệ"] --> B["Điểm điều hướng BGP được ủy quyền"]
    B --> S1["Scrubbing center / PoP A"]
    B --> S2["Scrubbing center / PoP B"]
    S1 --> F1{"Mitigation policy"}
    S2 --> F2{"Mitigation policy"}
    F1 -->|"Clean traffic"| T["GRE / IPsec / Private interconnect / đường sạch"]
    F2 -->|"Clean traffic"| T
    F1 -->|"Traffic bị loại"| X["Dropped / limited"]
    F2 -->|"Traffic bị loại"| X
    T --> O["Origin / mạng khách hàng"]
    O -.->|"Response path đã thiết kế"| I
~~~

Sơ đồ chỉ là **mô hình khái niệm**, không phải hướng dẫn thao tác điều khiển BGP công cộng. Nhà cung cấp có thể thông báo tuyến thay cho khách hàng trong phạm vi được ủy quyền, hoặc cung cấp phương thức kích hoạt khác. Những thành phần như **GRE, IPsec, private interconnect** là các lựa chọn vận chuyển clean traffic tùy kiến trúc; không phải dịch vụ nào cũng dùng mọi loại.

Các bước logic:

1. **Trạng thái bình thường:** traffic tới prefix/dịch vụ theo đường đang được thiết kế và giám sát baseline.
2. **Phát hiện bất thường:** thống kê bps/pps, session, ứng dụng, flow và cảnh báo upstream cho thấy cần giảm thiểu.
3. **Kích hoạt mitigation được phê duyệt:** traffic được đưa qua điểm scrubbing theo hợp đồng và phương thức định tuyến tương ứng.
4. **Phân loại và lọc:** áp policy theo lớp mạng/transport/ứng dụng trong phạm vi kỹ thuật cho phép.
5. **Chuyển traffic sạch:** đi qua đường an toàn và đủ dung lượng về backend; backend tiếp tục thực hiện xác thực/authorization.
6. **Hậu kiểm:** đánh giá effectiveness, false positive, kinh nghiệm ứng cứu và trả về trạng thái vận hành thích hợp.

### 5.3. Không nhầm giải pháp tunnel với mã hóa

**GRE** là cơ chế đóng gói IP, tự nó **không mã hóa và không xác thực** payload. Nếu đường truyền và threat model yêu cầu bảo mật nội dung hoặc xác thực đường truyền, cần giải pháp bảo vệ thích hợp như IPsec, TLS hoặc private connectivity có các tính chất bảo mật được xác minh. Không coi “đã đi qua GRE tunnel” đồng nghĩa dữ liệu được giữ bí mật.

**MTU/encapsulation overhead** cũng quan trọng: thêm header tunnel có thể khiến packet lớn hơn MTU của đường truyền và phát sinh fragmentation hoặc black-hole nếu Path MTU Discovery/ICMP bị chặn. Khi chuẩn bị scrubbing, phải kiểm thử kích thước packet, TCP MSS, cả IPv4/IPv6 và hành vi failover.

### 5.4. Chiều về và đường bất đối xứng

Trong một số thiết kế, request vào origin đi qua scrubbing nhưng response về client qua một tuyến khác (*asymmetric routing*). Điều này có thể được phép ở lớp routing, nhưng các firewall/stateful device, NAT hoặc cơ chế anti-spoofing có thể không nhận trạng thái kỳ vọng.

Vì vậy phải xác định:

- Đường request/response trong **trạng thái bình thường** và **khi mitigation kích hoạt**.
- Có stateful firewall, NAT, tunnel hoặc thiết bị áp chính sách cần thấy **cả hai chiều** không.
- Source IP được bảo tồn, NAT hoặc proxy thế nào; backend xác định client IP qua nguồn đáng tin nào.
- Có ảnh hưởng tới DNS, TLS certificate, QUIC, WebSocket, load balancing, idle timeout và phiên dài không.
- Khi chuyển từ scrubbing về đường thường, các phiên đang mở được xử lý ra sao.

Không suy ra luồng đã được kiểm tra an toàn chỉ vì thấy tăng băng thông clean traffic; cần xác minh ở đích rằng ứng dụng hoạt động và lưu lượng trái quyền vẫn bị chặn.

## 6. BGP, quyền quảng bá và tính toàn vẹn định tuyến

Kiến trúc Anycast/scrubbing phụ thuộc mạnh vào **quyền quảng bá và tính đúng đắn của định tuyến**. Khách hàng và nhà cung cấp cần xác định quyền điều hướng prefix, trách nhiệm thay đổi, những AS được phép thông báo tuyến và quy trình sự cố.

Các khái niệm phải hiểu:

| Khái niệm | Vai trò trong thiết kế | Rủi ro nếu làm sai |
|---|---|---|
| **AS / ASN** | Miền định tuyến có chính sách BGP | Nhầm bên sở hữu hoặc bên được quyền quảng bá |
| **Prefix** | Khối IP đang được định tuyến và cần bảo vệ | Chỉ bảo vệ một phần hệ thống, bỏ sót địa chỉ phụ |
| **BGP advertisement/withdrawal** | Thông báo hoặc rút đường tới prefix theo quy trình | Mất reachability hoặc chuyển traffic bất ngờ |
| **RPKI / ROA** | Hỗ trợ xác minh quyền origin AS được quảng bá một prefix theo cơ chế RPKI | Cấu hình không phù hợp có thể khiến tuyến hợp lệ bị đánh giá invalid |
| **IRR và route filters** | Thông tin/phương pháp nhà mạng dùng để xây policy lọc tuyến | Danh mục không cập nhật hoặc filter sai làm thay đổi reachability |
| **Peering/transit** | Các đường trao đổi traffic và phạm vi định tuyến | Điểm nghẽn của PoP hoặc tuyến thượng nguồn |
| **Route convergence** | Quá trình các mạng thay đổi lựa chọn tuyến | Có thể gây chập chờn, mất gói, reset session |

**RPKI origin validation không tự chứng minh mọi thuộc tính AS-path và không thay thế chính sách định tuyến tổng thể.** Nếu dùng scrubbing theo yêu cầu, việc ủy quyền quảng bá prefix cho provider cần được rà soát phù hợp các cơ chế kiểm tra tuyến của ISP; không thực hiện quảng bá/rút tuyến thật chỉ để thử học tập.

Quy tắc phòng thủ vận hành: **route change là thay đổi có thể tác động toàn Internet**, cần owner, phê duyệt, rollback, giám sát nhiều vùng và phối hợp với NOC/ISP/provider.

## 7. Phân tầng lọc tại scrubbing service

Lọc traffic DDoS không đơn thuần là một ACL “deny all suspicious”. Các lớp cần được kết hợp, tùy loại traffic và dịch vụ:

| Lớp | Ví dụ kiểm soát phòng vệ | Giới hạn |
|---|---|---|
| **L3/L4 network filtering** | Anti-spoofing khi có thể, protocol sanity checks, loại traffic rõ ràng trái policy | Cần tránh chặn giao thức hợp lệ và traffic NAT/shared sources |
| **Flow/connection protection** | Giới hạn packet/session rate, state exhaustion protection, connection proxy khi phù hợp | Threshold sai có thể chặn giờ cao điểm |
| **UDP/protocol-specific** | Kiểm soát dịch vụ UDP được phép, lọc gói không hợp lệ, quota theo ứng dụng | Một số UDP hợp lệ không phù hợp áp chính sách TCP |
| **HTTP(S) WAF/bot control** | Rate limit theo identity/route, challenge có chọn lọc, cache, bảo vệ endpoint đắt | Không phù hợp với mọi API/mobile/webhook, có false positive |
| **DNS protection** | DNS Anycast, kiểm soát kiểu truy vấn, chống lạm dụng DNS server do mình vận hành | Nếu authoritative DNS không sẵn sàng, cả các tầng khác có thể không truy cập được |
| **Application/backend protection** | AuthN/AuthZ, quota tenant, giới hạn concurrency, queue, circuit breaker | Không xử lý được bão hòa upstream nếu không có lớp mạng đủ sớm |

Một số provider sử dụng những phương pháp giảm thiểu mạng chuyên biệt; cần xác minh **khả năng và giới hạn của sản phẩm**, không coi mọi scrubber đều giải mã HTTPS hoặc có cùng ngữ nghĩa rate limiting.

### 7.1. Vì sao không chỉ dựa vào IP?

Văn phòng nhiều người dùng có thể đi qua một địa chỉ NAT; mạng di động và dịch vụ mạng riêng ảo có thể thay đổi IP. Mặt khác, một sự kiện lưu lượng bất thường có thể trải rộng trên nhiều IP và ASN. Do đó chính sách phân loại nên dùng **ngữ cảnh đa chiều**: tình trạng protocol, lịch sử luồng, workload identity khi có, đường dẫn ứng dụng, baseline theo khu vực và kết quả kiểm tra nghiệp vụ.

IP reputation hoặc địa lý là một tín hiệu, **không phải bằng chứng tuyệt đối về danh tính hoặc động cơ**. Hệ thống phải có khả năng xử lý false positive và ngoại lệ hẹp cho khách hàng hợp lệ, đối tác và hệ thống giám sát.

### 7.2. Blackholing và bảo vệ đích

Trong trường hợp đặc biệt, mạng có thể dùng cơ chế **blackholing** hoặc chính sách lọc ưu tiên để giảm ảnh hưởng lên hạ tầng chung. Đây là đánh đổi nghiêm trọng: traffic hợp lệ tới phạm vi bị blackhole cũng có thể không đến đích.

Không xem blackholing là tương đương scrubbing bảo toàn dịch vụ. Việc kích hoạt cần mục tiêu rõ, phạm vi tối thiểu, thời hạn, bên có thẩm quyền và quy trình khôi phục. Có thể ưu tiên giữ các tài nguyên quan trọng khác hoạt động, nhưng phải nhận diện rằng dịch vụ đích có thể mất sẵn sàng trong giai đoạn đó.

## 8. Kiến trúc tham chiếu cho SaaS và dịch vụ cloud

Giả sử một doanh nghiệp có:

- Website và API công khai ở các khu vực khác nhau.
- Origin nằm trong mạng cloud riêng, chỉ cần nhận traffic từ proxy/scrubbing và đường vận hành có kiểm soát.
- Ứng dụng quản trị truy cập qua VPN/ZTNA, không phục vụ Internet công khai.
- Hệ thống dữ liệu và DNS là các phụ thuộc quan trọng.

### 8.1. Nguyên tắc phân đoạn

~~~mermaid
flowchart LR
    C["Client Internet"] --> E["Anycast edge / Scrubbing / WAF"]
    E --> G["Origin ingress giới hạn nguồn"]
    G --> A["Web / API có authz"]
    A --> D[("Data zone / DB")]
    O["Operator qua ZTNA"] --> M["Management entry point"]
    M --> A
    M --> G
    E -.-> SIEM["Metrics / SIEM / SOC"]
    G -.-> SIEM
    A -.-> SIEM
~~~

Phòng vệ được chia thành các lớp:

1. **Edge:** nhận traffic ở nhiều địa điểm, lọc theo chính sách, duy trì năng lực upstream.
2. **Origin ingress:** chỉ tiếp nhận đường được phê duyệt từ scrubbing/edge và kênh quản trị tương ứng; xác thực upstream nếu giải pháp hỗ trợ.
3. **Ứng dụng:** kiểm tra token, quyền tài nguyên, rate limit theo tài khoản/tenant và thao tác nghiệp vụ.
4. **Data zone:** không mở cơ sở dữ liệu trực tiếp cho Internet; chỉ cho phép kết nối ứng dụng cụ thể.
5. **Management zone:** dành cho nhân sự và automation được xác thực, có MFA/audit, không bỏ qua quy tắc phân đoạn.

### 8.2. Ngăn truy cập trực tiếp origin

Nếu IP origin bị lộ hoặc endpoint khác vẫn mở trực tiếp, traffic có thể **không đi qua Anycast/scrubbing**. Các biện pháp cần được đánh giá:

- Security group/firewall/ACL tại origin chỉ chấp nhận **nguồn được phép và còn hiệu lực** của provider hoặc private interconnect.
- Với HTTP, kiểm tra xác thực upstream/tunnel, hostname/TLS và chính sách proxy; không dựa riêng vào header tự khai báo.
- Rà soát địa chỉ public cũ, subdomain phụ, endpoint debug, IPv6, vùng staging, backup gateway và các đường đối tác.
- Bảo vệ SSH/RDP và control plane bằng đường quản trị riêng, identity mạnh và giới hạn nguồn.
- Giám sát thay đổi DNS, IP, route, firewall và tài nguyên cloud để phát hiện origin exposure.

Nếu một API cần client kết nối trực tiếp và không tương thích proxy, phải thiết kế phương án **network scrubbing/tunnel** hoặc kiểm soát bù trừ được phê duyệt; không thể gọi tên dịch vụ là “đã được bảo vệ” nếu còn đường bypass không được kiểm soát.

### 8.3. Clean traffic vẫn cần kiểm tra quyền

Scrubbing chỉ đánh giá traffic theo những dấu hiệu mà nó có thể quan sát và chính sách đã thiết lập. **Traffic sạch không đồng nghĩa người dùng đã được phép đọc dữ liệu**. Origin phải tiếp tục:

- Xác thực người dùng/workload và phân quyền theo object/tenant.
- Giới hạn endpoint đắt, concurrency, job queue và DB connections.
- Áp WAF/API validation khi thích hợp và tránh lỗi logic nghiệp vụ.
- Ghi audit có correlation ID và hạn chế dữ liệu nhạy cảm.

Đặc biệt với dịch vụ nhiều tenant, clean traffic từ tenant A vẫn không được truy cập tài nguyên tenant B chỉ vì cả hai cùng dùng một điểm edge.

## 9. Capacity planning: tính đúng điểm nghẽn

Một kiến trúc bảo vệ cần được đánh giá theo **đường đầy đủ**, không chỉ tổng dung lượng scrubbing quảng cáo.

| Điểm đo | Câu hỏi |
|---|---|
| Transit/peering của PoP | Có đủ đường truyền khi lưu lượng tập trung ở một khu vực không? |
| Scrubbing processing | Thiết bị/pipeline có đủ pps, flow/session capacity và khả năng L7 không? |
| Clean tunnel/interconnect | Phần traffic được phép còn vượt dung lượng tunnel/đường về không? |
| Firewall/NAT ở origin | Có bị cạn session table hoặc CPU khi traffic sạch dồn tới không? |
| Load balancer/ingress | Giới hạn kết nối, TLS handshakes và retry của client ra sao? |
| Backend/DB/queue | Có bị bão hòa bởi request hợp lệ nhưng quá lớn không? |
| DNS/IdP/monitoring | Phụ thuộc có điểm lỗi duy nhất không? |

### 9.1. Ví dụ minh họa về đường truyền

Giả sử tại một thời điểm:

- Lưu lượng hướng tới dịch vụ: **40 Gbit/s** (không suy rằng tất cả đều xấu).
- Scrubbing point có đủ năng lực để tiếp nhận và xử lý tải đó.
- Sau phân loại, lượng traffic được phép chuyển đến origin: **3 Gbit/s**.
- Đường về origin: **5 Gbit/s**, trong điều kiện đo ở cùng lớp và tính cả overhead thực tế.

Từ dữ kiện này có thể nói **3 Gbit/s nhỏ hơn 5 Gbit/s**, nên về **băng thông trung bình** có vẻ chưa vượt mức đường về. Nhưng chưa thể kết luận hệ thống an toàn: cần xem **packet/s, burst ngắn, tunnel overhead, các luồng khác dùng chung uplink, TLS handshakes, session table và tải ứng dụng**.

Nếu áp một hạn mức UDP/TCP quá chặt để giảm traffic sạch về 1 Gbit/s, có thể làm hỏng dịch vụ hợp lệ. Mục tiêu không phải “băng thông càng thấp càng tốt”, mà là **duy trì nghiệp vụ với các kiểm soát đúng mức rủi ro**.

### 9.2. Đánh giá dự phòng và phân bố tải

Anycast không đảm bảo lưu lượng chia đều giữa các PoP. Hãy kiểm tra cả tình huống **một PoP không sẵn sàng**, tuyến thay đổi khiến nhiều nguồn dồn sang PoP khác, mất một clean tunnel hoặc provider cần bảo trì. Bài test cần đủ thực tế để kiểm chứng SLO và routing convergence, nhưng **không được gây flood lên hạ tầng công cộng để tự thử DDoS**.

Diễn tập nên được phối hợp với nhà cung cấp bằng **test được ủy quyền, lưu lượng tổng hợp có giới hạn hoặc mô phỏng đường đi trên dữ liệu đã có**, không tự phát traffic tấn công ra Internet.

## 10. Phát hiện sự cố và đo hiệu quả mitigation

### 10.1. Nguồn telemetry tối thiểu

| Nguồn | Trường/thước đo nên xem | Mục đích |
|---|---|---|
| Router/ISP | Bps, pps, interface drops, tuyến và trạng thái peering | Nhận diện bão hòa đường mạng và route change |
| Anycast/PoP | Lưu lượng theo khu vực, health và khả dụng từng PoP | Phát hiện tập trung tải, mất vùng phục vụ |
| Scrubbing service | Ingress traffic, filtered/allowed traffic, loại mitigation, thời gian kích hoạt | Đánh giá chính sách lọc và lượng traffic tới origin |
| Tunnel/clean path | Loss, RTT, throughput, MTU/fragmentation, tunnel status | Đảm bảo clean traffic đến origin |
| Firewall/NGFW | Accepted/denied flow, session table, connection drops | Bảo vệ đường vào và phát hiện lệch traffic |
| WAF/API | RPS, 403/429/5xx, bot signals, challenge, authentication failures | Phân biệt L7 abuse và false positive |
| Application | P95/p99 latency, error rate, capacity, transaction completion | Xác nhận người dùng hợp lệ còn sử dụng được |
| SOC/audit | Rule version, change ticket, timeline, nguồn telemetry | Điều tra và giải trình hành động |

**Tỷ lệ “lọc được 95% traffic” không đủ đánh giá thành công** nếu 5% còn lại vẫn làm tê liệt DB, hoặc nếu trong 95% bị lọc có phần lớn là khách hàng hợp lệ. Nên đo **availability và trải nghiệm end-to-end**, số giao dịch thành công, loại traffic bị loại, mức độ sai và chi phí vận hành.

### 10.2. Dòng thời gian sự cố

Ví dụ hồ sơ sự cố **giả định**:

~~~text
09:00  Baseline: dịch vụ ổn định, 1.2 Gbit/s trên vùng edge.
09:03  Telemetry phát hiện bps/pps tăng vượt baseline.
09:05  SOC xác minh ảnh hưởng tới người dùng và phân loại L3/L4 hay L7.
09:07  Provider xác nhận mitigation đã có hiệu lực theo quy trình.
09:10  Clean traffic về origin còn trong năng lực; API p95 giảm.
09:20  Một nhóm người dùng hợp lệ bị rate limit nhầm; exception hẹp được rà soát.
09:40  Đường đi và rule đã ổn định; tiếp tục theo dõi.
10:30  Ghi lại timeline, thay đổi policy, tác động và bài học.
~~~

**Không dùng mốc thời gian mẫu làm cam kết SLA của nhà cung cấp.** Khi vận hành thực tế, đối chiếu timestamp từ router, scrubbing, DNS, gateway và ứng dụng; chuẩn hóa múi giờ và độ lệch đồng hồ.

### 10.3. Alert có ngữ cảnh và false positive

Các nhóm người dùng dùng chung NAT, crawler được phê duyệt, job backup hoặc API đối tác chạy batch có thể tạo traffic bùng nổ hợp lệ. Lọc theo IP đơn lẻ có thể chặn nhiều người dùng tốt, trong khi một nguồn gây hại có thể hoạt động phân tán. Vì vậy cần đánh giá **mẫu lưu lượng, danh tính, tính hợp lệ của giao dịch, tải backend, error rate và lịch vận hành**.

Khi điều tra false positive, ghi rõ **quy tắc nào, điều kiện match nào, nhóm client nào, hậu quả gì, đề xuất exception có phạm vi và thời hạn ra sao**. Không mở allow toàn mạng chỉ để giảm số ticket.

## 11. Quy trình triển khai và ứng cứu DDoS có thể kiểm chứng

### Bước 1 — Kiểm kê dịch vụ và phụ thuộc

Ghi IP/prefix, hostname, origin, cổng/giao thức, luồng client, API đối tác, DNS, quản trị, tunnel và khu vực cloud. Xác định dịch vụ nào có thể dùng reverse proxy, dịch vụ nào cần IP-level scrubbing. Ghi owner và những đường bypass cần xử lý.

### Bước 2 — Chọn mô hình bảo vệ

Quyết định always-on, on-demand hay hybrid dựa vào mức ảnh hưởng khi gián đoạn, đặc tính traffic và năng lực cung cấp. Rà soát điều kiện định tuyến BGP, ủy quyền provider, các yêu cầu RPKI/IRR và **phạm vi prefix được bảo vệ** với nhóm network/ISP.

### Bước 3 — Thiết kế clean path

Chọn tunnel/interconnect/proxy thích hợp. Kiểm thử MTU, độ trễ, return path, NAT/client IP preservation, TLS/mTLS khi cần, firewall state, HA và nguồn dự phòng. Ngăn origin exposure bằng quy tắc ingress hẹp và auth thích hợp.

### Bước 4 — Định nghĩa chính sách lọc và baseline

Xác định traffic hợp lệ theo bps/pps/rps, giao thức, region, giờ cao điểm, đối tác, hoạt động backup và khối lượng giao dịch. Thiết kế rule ở mức tối thiểu cần thiết, quan sát trước và tránh ngưỡng tuyệt đối không dựa trên dữ liệu.

### Bước 5 — Diễn tập chuyển tuyến an toàn

Trong môi trường được ủy quyền, phối hợp provider để kiểm tra logic kích hoạt, hội tụ tuyến, lưu lượng đi/đến, loss/latency, session continuity, DNS, cache và rollback. Thực hiện theo change window hoặc quy trình đã được phê duyệt, **không quảng bá/rút BGP thật và không tạo flood ngoài phạm vi thí nghiệm**.

### Bước 6 — Vận hành khi sự cố xảy ra

Sử dụng runbook có tiêu chí nâng cấp mức ứng cứu: ai trực NOC/SOC, ai liên hệ ISP/provider, ai duyệt rule thay đổi, các tín hiệu quyết định sự cố và cách thông báo cho chủ dịch vụ. Thực hiện mitigation có log, đối chiếu traffic sạch và kết quả người dùng.

### Bước 7 — Hậu kiểm và cải tiến

Ghi đầy đủ timeline, thay đổi route/policy, hiệu năng từng điểm, số khách hàng bị ảnh hưởng, false positive, thời gian khôi phục và bài học. Cập nhật baseline, capacity, emergency contact, hợp đồng dịch vụ và kiểm thử lại khi triển khai thêm vùng hoặc tenant.

## 12. Fail-open, fail-closed và những đánh đổi

Khi scrubbing center hoặc tunnel không sẵn sàng, hệ thống có thể phải chọn giữa:

- **Fail-open/bypass mitigation:** giữ một phần khả năng kết nối bằng đường thường nhưng tăng rủi ro traffic không lọc đi tới origin.
- **Fail-closed:** giữ ranh giới kiểm soát, nhưng người dùng hợp lệ có thể mất kết nối nếu không có đường bảo vệ thay thế.
- **Failover đến PoP/tunnel/provider khác:** có thể duy trì dịch vụ nếu tuyến và khả năng xử lý dự phòng đủ, nhưng có nguy cơ gián đoạn phiên.

Không có câu trả lời chung. Với dịch vụ nhạy cảm, cần **đánh giá tác động kinh doanh, nguy cơ lộ origin, cơ chế chuyển tuyến, yêu cầu tuân thủ và đặc tính phiên** trước khi chọn hành vi lỗi. Đặc biệt, failover mạng và failover ứng dụng không phải cùng một thao tác.

## 13. Rủi ro thiết kế thường gặp

| ID | Sai lầm / tình huống | Hậu quả | Kiểm soát và bằng chứng |
|---|---|---|---|
| D01 | Coi Anycast là bộ lọc DDoS hoàn chỉnh | Không phân biệt traffic tốt/xấu, PoP có thể quá tải | Kết hợp scrubbing/WAF và capacity monitoring |
| D02 | Đánh giá chỉ tổng dung lượng toàn cầu | Một peering/PoP nhỏ vẫn nghẽn | Đo theo PoP, ISP, packet rate và đường về |
| D03 | Origin còn public endpoint bypass | Traffic đi trực tiếp, bỏ qua scrubbing | Chặn nguồn không được phép, rà DNS/IP/IPv6 |
| D04 | Tunnel GRE bị xem là đường mã hóa | Dữ liệu không có tính bí mật/xác thực theo giả định | Dùng IPsec/TLS hoặc kênh phù hợp theo threat model |
| D05 | Không kiểm thử MTU và return path | Kết nối chập chờn, packet loss, session reset | Test encapsulation, PMTU, firewall state, routing |
| D06 | Ủy quyền quảng bá prefix không rõ | Route bị đánh giá invalid hoặc mất reachability | Quy trình với ISP/provider, rà RPKI/ROA/IRR |
| D07 | Kích hoạt on-demand quá chậm | Origin quá tải trước khi lọc có hiệu lực | Giám sát sớm, runbook, mục tiêu activation rõ |
| D08 | Rule rate limit quá rộng theo IP | Chặn NAT/mobile/API đối tác hợp lệ | Threshold theo route/identity và false-positive review |
| D09 | Chỉ lọc volumetric mà bỏ qua L7 | DB/API vẫn quá tải bởi request được phép | WAF, quota, concurrency, backend protection |
| D10 | Dùng blackhole như phương án mặc định | Mất sẵn sàng cho cả người dùng hợp lệ | Phê duyệt, scope hẹp, thời hạn và rollback |
| D11 | Không thiết kế PoP/tunnel dự phòng | Một lỗi chuyển thành sự cố toàn khu vực | Diễn tập failover và đánh giá capacity khi một vùng mất |
| D12 | Theo dõi traffic lọc mà không đo nghiệp vụ | Báo cáo “mitigation thành công” dù người dùng lỗi | End-to-end SLO, transaction success, p95/p99 |
| D13 | Đổi tuyến/chính sách không có audit | Không xác định nguyên nhân hoặc khôi phục khó | Change ticket, owner, version, timeline, rollback |
| D14 | Xem clean traffic là đã được cấp quyền | Lộ dữ liệu, truy cập chéo tenant | AuthN/AuthZ, phân đoạn và bảo vệ dữ liệu tại origin |

### 13.1. Khung đánh giá rủi ro

Cho mỗi điểm yếu, xác định: **tài sản**, **đường khai thác/đường lỗi**, **nguyên nhân**, **mức độ phơi bày**, **ảnh hưởng tới SLO và dữ liệu**, **kiểm soát đã có**, **bằng chứng kiểm thử**, **owner** và **hành động tiếp theo**. Không chỉ gán “cao/thấp” dựa trên tên kỹ thuật.

## 14. Bài tập tình huống: chọn kiến trúc chống DDoS

**Bối cảnh giả định:** một công ty có website thương mại điện tử và API thanh toán. Website phục vụ qua HTTPS, API có cả mobile app và đối tác dùng OAuth; origin ở một cloud region. Kết nối về origin có năng lực 5 Gbit/s, backend chịu tối đa 2.000 request/giây ở một endpoint tìm kiếm phức tạp trong điều kiện kiểm thử hiện tại. Công ty dự kiến dùng dịch vụ Anycast edge và có lựa chọn scrubbing on-demand cho một dịch vụ TCP riêng.

Đội vận hành ghi nhận trong một thời điểm:

| Thông số | Quan sát | Câu hỏi cần giải quyết |
|---|---|---|
| Ingress tại mạng bảo vệ | 35 Gbit/s | PoP nào gánh tải? Có vượt băng thông/pps từng PoP không? |
| Clean traffic về origin | 3,5 Gbit/s | Tunnel/return path/overhead còn phù hợp không? |
| HTTP request tới search | 4.000 request/s | Backend cần quota, cache hay tách hàng đợi ra sao? |
| Tỉ lệ 429 từ edge | Tăng ở một số IP NAT | Có đang chặn nhóm user/đối tác hợp lệ không? |
| Client mobile | Không xử lý JavaScript challenge | Cơ chế xác thực/quota nào phù hợp? |
| Origin cũ | Vẫn có IP public trong cấu hình phụ | Có đường đi bỏ qua edge không? |
| TLS/WAF | HTTPS kết thúc tại edge cho website | Dữ liệu nào có thể được kiểm tra, ai có quyền quản lý chứng chỉ? |

**Câu hỏi:**

1. Vì sao “dịch vụ Anycast toàn cầu” chưa đủ để kết luận ứng dụng chịu được 35 Gbit/s?
2. Nếu scrubbing loại nhiều traffic, tại sao endpoint `/search` vẫn có thể quá tải?
3. Nên áp những lớp bảo vệ nào cho website, mobile API, dịch vụ TCP riêng và origin?
4. Những nguy cơ nào xuất hiện nếu on-demand diversion làm thay đổi tuyến khi có kết nối dài?
5. Làm sao chứng minh mitigation **giúp dịch vụ còn hoạt động**, không chỉ giảm traffic?

**Gợi ý lời giải:**

- Cần đối chiếu **tải theo PoP/peering, bps và pps, năng lực scrubbing, đường clean traffic, failover và SLO**. BGP có thể dồn tải, không chia đều theo địa lý.
- 3,5 Gbit/s dưới mức uplink 5 Gbit/s **không chứng minh** backend đủ năng lực xử lý 4.000 request/s; endpoint tìm kiếm có thể vượt năng lực đã kiểm thử. Dùng cache/pagination, quota theo identity/route, concurrency control và autoscaling trong phạm vi khả thi.
- Website HTTPS có thể dùng Anycast CDN/WAF với bot management; mobile/API đối tác dùng OAuth/mTLS theo nhu cầu, quota theo client/tenant thay vì CAPTCHA bắt buộc; dịch vụ TCP riêng cần scrubbing đường mạng và kiểm tra tunnel/return path; origin phải chặn đường bypass.
- Kiểm tra chuyển tuyến BGP, session state TCP/QUIC, MTU, NAT, firewall bất đối xứng và các phiên dài. Có test failover được phê duyệt và phương án rollback.
- Đối chiếu transaction success, p95/p99, lỗi 5xx/429, kết nối bị chặn nhầm, số người dùng hợp lệ ảnh hưởng, dropped packets, thời gian kích hoạt và health từng PoP. Chỉ báo “bao nhiêu Gbit/s bị lọc” **không đủ**.

## 15. Checklist triển khai Anycast và scrubbing service

- [ ] Xác định tài sản, IP/prefix, domain, giao thức và mức độ quan trọng từng dịch vụ.
- [ ] Phân biệt DDoS làm cạn bandwidth, pps, session state và tài nguyên L7.
- [ ] Hiểu Anycast là cơ chế định tuyến; không mặc định traffic tới nơi gần nhất hoặc được chia đều.
- [ ] Đã xác định mọi PoP/ISP, capacity tại điểm nghẽn và cơ chế phân phối lưu lượng khi failover.
- [ ] Chọn always-on/on-demand/hybrid với tiêu chí phản ứng, SLA và thử nghiệm tương ứng.
- [ ] Có ủy quyền/provider agreement rõ về prefix và quảng bá tuyến, RPKI/ROA/IRR được rà soát.
- [ ] Kiểm thử đường clean traffic, reverse proxy/tunnel, MTU, encryption, routing hai chiều, NAT và stateful firewall.
- [ ] Không coi GRE là mã hóa; bảo vệ đường truyền bằng cơ chế phù hợp nếu cần.
- [ ] Origin không có đường bypass ngoài chính sách qua public IP, IPv6, phụ domain hoặc kênh quản trị.
- [ ] Duy trì firewall, IAM/authentication, authorization ở API/DB và bảo vệ tenant riêng dù traffic đã lọc.
- [ ] Rate limiting/challenge không chặn nhầm mobile, API đối tác, crawler hợp lệ hoặc người dùng NAT chung.
- [ ] Có kế hoạch capacity cho tunnel, PoP, firewall, WAF, load balancer, DNS, IdP và backend.
- [ ] Giám sát theo PoP, bps/pps/rps, filtered/allowed, tunnel health, p95/p99 và kết quả giao dịch.
- [ ] Có runbook liên hệ NOC/SOC/ISP/provider, trách nhiệm thay rule, rollback và phương án fail-open/fail-closed.
- [ ] Diễn tập chuyển tuyến/failover trong phạm vi được phê duyệt, không tạo traffic flood trái phép.
- [ ] Lưu timeline sự cố, thay đổi cấu hình, false positive và bài học để cập nhật kiến trúc.

**Ghi nhớ:** **Anycast phân phối đường đi; scrubbing lọc lưu lượng; ứng dụng vẫn phải bảo vệ quyền và năng lực xử lý của chính mình.** Phòng chống DDoS hiệu quả là sự phối hợp của đường mạng đủ năng lực, điểm lọc đặt đúng vị trí, routing được ủy quyền, clean path tin cậy, phân đoạn và xác thực, giám sát sát với trải nghiệm người dùng, cùng quy trình ứng cứu đã được diễn tập.
