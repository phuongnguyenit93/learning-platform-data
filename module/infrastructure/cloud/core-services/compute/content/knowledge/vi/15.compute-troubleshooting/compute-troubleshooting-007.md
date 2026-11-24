# Kết nối chập chờn: route, DNS, firewall và giới hạn cổng kết nối

Một workload cloud có thể hoạt động bình thường trong vài phút rồi đột ngột timeout, kết nối thành công lúc được lúc không, hoặc chỉ lỗi khi tải tăng. Hiện tượng này thường khó chẩn đoán hơn một lỗi mất kết nối hoàn toàn vì nhiều lớp vẫn hoạt động: máy chủ còn chạy, ứng dụng vẫn lắng nghe, nhưng một số request không đến được đích hoặc response không quay về đúng đường.

Các nguyên nhân thường gặp nằm ở nhiều lớp: route trong hệ điều hành hoặc cloud network, DNS phân giải không nhất quán, firewall/security policy, NAT và connection tracking, dải cổng nguồn tạm thời (ephemeral ports), backlog, file descriptor hoặc giới hạn kết nối của ứng dụng. Một lỗi biểu hiện giống nhau như timeout có thể xuất phát từ những nguyên nhân rất khác nhau. Vì vậy, cần khoanh vùng theo thời điểm, nguồn, đích, giao thức và từng chặng của kết nối.

Bài học này thuộc chương **Chẩn đoán sự cố compute** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong phạm vi đó, chẩn đoán kết nối chập chờn giúp phân biệt lỗi compute, mạng và ứng dụng, giảm thời gian gián đoạn và xác định đúng giới hạn cần điều chỉnh.

## 1. Hiểu đường đi của một kết nối

### 1.1. Các bước của kết nối TCP

Với kết nối TCP thông thường, client cần phân giải tên đích (nếu dùng hostname), chọn route, chọn địa chỉ IP nguồn và cổng nguồn, sau đó gửi SYN tới địa chỉ IP và cổng đích.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant D as DNS Resolver
    participant N as Cloud Network / Firewall
    participant S as Server
    C->>D: Resolve hostname
    D-->>C: A/AAAA record
    C->>C: Route lookup + source IP/port
    C->>N: TCP SYN
    N->>S: Forward if route and policy allow
    S-->>N: TCP SYN-ACK
    N-->>C: Return packet
    C->>S: TCP ACK
    Note over C,S: TCP connection established
~~~

Sau khi bắt tay TCP thành công, ứng dụng mới trao đổi dữ liệu. Do đó, cần phân biệt:

- **DNS failure:** client không lấy được địa chỉ hoặc lấy địa chỉ không phù hợp.
- **Route failure:** hệ điều hành hoặc cloud network không có đường tới đích.
- **Firewall/policy drop:** packet bị chặn hoặc không có đường về được cho phép.
- **Port/listener failure:** máy đích không có tiến trình lắng nghe trên IP/port mong muốn.
- **Connection resource exhaustion:** client, server, NAT hoặc load balancer hết tài nguyên kết nối.
- **Application failure:** TCP đã kết nối nhưng ứng dụng không phản hồi đúng hạn hoặc đóng kết nối.

TCP timeout không cho biết chính xác lớp nào có lỗi. Một packet SYN bị drop, SYN-ACK bị drop, server quá tải hoặc NAT hết cổng đều có thể khiến client chờ đến timeout.

### 1.2. Các lớp cần kiểm tra

| Lớp | Câu hỏi chẩn đoán | Ví dụ lỗi |
|---|---|---|
| DNS | Tên có phân giải ổn định ra đúng địa chỉ không? | Resolver timeout, record cũ, split-horizon sai |
| Routing | Kernel và cloud có chọn đúng next hop không? | Default route sai, route thiếu, đường về bất đối xứng |
| Network policy | Packet có được phép qua từng lớp không? | Security group, NACL, host firewall, network policy |
| NAT/connection tracking | Kết nối có được dịch địa chỉ và theo dõi trạng thái không? | NAT port exhaustion, conntrack table đầy |
| TCP/UDP port | Cổng đích có listener? Cổng nguồn còn khả dụng? | Không có listener, ephemeral port exhaustion |
| Host resources | Host còn đủ socket, FD, CPU và memory không? | File descriptor limit, SYN backlog, CPU saturation |
| Application | Pool, timeout và concurrency có phù hợp không? | Pool cạn, worker treo, upstream chậm |

### 1.3. Xác định phạm vi trước khi thay đổi

Trước tiên, xác định lỗi xảy ra với:

- Một client hay nhiều client.
- Một hostname hay mọi hostname.
- Một IP đích hay tất cả IP của dịch vụ.
- Một port/giao thức hay nhiều dịch vụ.
- Một subnet, zone, node pool hay toàn hệ thống.
- Kết nối mới hay cả kết nối đã thiết lập.
- Một khoảng thời gian cụ thể, chẳng hạn lúc traffic tăng hoặc sau khi triển khai.

Các câu hỏi này giúp phân biệt lỗi cục bộ với lỗi diện rộng. Ví dụ, nếu chỉ một nhóm client lỗi nhưng nhóm khác vẫn thành công, cần so sánh route, DNS resolver, source IP và firewall của hai nhóm trước khi thay đổi server.

## 2. Thu thập bằng chứng và tái hiện lỗi

### 2.1. Ghi lại thông tin của một lần lỗi

Mỗi lần lỗi nên có các thông tin tối thiểu:

- Timestamp kèm timezone.
- Hostname hoặc IP đích.
- IP nguồn, subnet, node hoặc instance.
- Protocol và destination port.
- Loại lỗi: DNS error, connection refused, timeout, reset, TLS error hay HTTP error.
- Thời gian chờ trước khi lỗi.
- Request ID hoặc trace ID nếu có.
- Tỷ lệ lỗi và tổng số request trong cùng khoảng thời gian.

Không nên chỉ ghi “mạng chập chờn”. Một bản ghi như “từ worker subnet A tới api.internal.example:443, TCP timeout khoảng 3 giây, xuất hiện ở 2% request trong 10 phút” có giá trị chẩn đoán cao hơn nhiều.

### 2.2. So sánh lần thành công và lần thất bại

Chạy cùng phép thử từ cùng máy tới cùng đích nhiều lần, ghi lại timestamp và kết quả. Sau đó thử từ một máy khác trong cùng subnet và một máy ở subnet khác.

Nếu lỗi chỉ xảy ra ở một instance, kiểm tra cấu hình riêng của host đó. Nếu nhiều instance cùng lỗi ở một thời điểm, kiểm tra shared dependency như DNS resolver, NAT gateway, route table, firewall, load balancer hoặc dịch vụ đích.

### 2.3. Kiểm tra theo từng chặng

Không bắt đầu bằng cách thay nhiều cấu hình cùng lúc. Thực hiện lần lượt:

1. Kiểm tra hostname có phân giải đúng không.
2. Kiểm tra route và source IP được chọn.
3. Kiểm tra TCP có tới được destination port không.
4. Kiểm tra listener và firewall tại máy đích.
5. Kiểm tra đường trả về.
6. Kiểm tra giới hạn kết nối và tài nguyên khi tải tăng.
7. Đối chiếu log ứng dụng, load balancer và network telemetry.

Mỗi bước nên lưu kết quả để có thể so sánh trước và sau khi thay đổi.

## 3. Chẩn đoán DNS

### 3.1. DNS có thể gây lỗi chập chờn như thế nào?

DNS phân giải tên thành địa chỉ IP. Một hostname có thể trả về một hoặc nhiều bản ghi A (IPv4), AAAA (IPv6), CNAME hoặc các loại record khác. Kết quả có thể thay đổi theo resolver, vị trí mạng, TTL, health-based routing hoặc cấu hình split-horizon.

Các nguyên nhân phổ biến:

- Resolver không phản hồi hoặc phản hồi chậm.
- Một trong các DNS server được cấu hình không khả dụng.
- Record A/AAAA chứa địa chỉ cũ hoặc endpoint không còn hoạt động.
- Một địa chỉ trong tập record có lỗi, trong khi các địa chỉ khác vẫn khỏe.
- Cache của ứng dụng, hệ điều hành hoặc thư viện giữ record cũ lâu hơn dự kiến.
- DNS nội bộ và DNS công cộng trả về các kết quả khác nhau.
- Search domain hoặc cấu hình resolver khiến hostname ngắn được nối sai suffix.
- Một số client ưu tiên IPv6 nhưng đường IPv6 chưa được cấu hình đầy đủ.

Một ứng dụng có thể báo timeout dù DNS vẫn phân giải thành công: resolver trả về một IP hợp lệ về mặt cú pháp nhưng đường mạng tới IP đó bị lỗi. Vì vậy, cần kiểm tra từng IP được trả về thay vì chỉ kiểm tra hostname.

### 3.2. Kiểm tra phân giải trên Linux

Các lệnh thường dùng:

~~~bash
# Kiểm tra cấu hình resolver
cat /etc/resolv.conf

# Kiểm tra kết quả phân giải
getent ahosts api.internal.example

# Truy vấn A và AAAA
dig api.internal.example A
dig api.internal.example AAAA

# Truy vấn qua một resolver cụ thể
dig @10.0.0.53 api.internal.example A

# Kiểm tra CNAME và TTL
dig api.internal.example CNAME
dig api.internal.example A +noall +answer
~~~

**getent** hữu ích vì thường đi qua cơ chế Name Service Switch của hệ điều hành, có thể bao gồm DNS, **/etc/hosts** và các nguồn khác. **dig** giúp quan sát trực tiếp câu trả lời DNS, TTL, resolver và thời gian truy vấn.

Không nên chỉ dựa vào **nslookup** hoặc **dig** để kết luận ứng dụng chắc chắn dùng cùng kết quả. Runtime có thể có cache riêng, dùng resolver khác hoặc áp dụng thứ tự ưu tiên IPv4/IPv6 khác.

### 3.3. Kiểm tra DNS trên Windows

~~~powershell
# Xem DNS server trên các interface
Get-DnsClientServerAddress

# Phân giải hostname
Resolve-DnsName api.internal.example

# Chỉ truy vấn A hoặc AAAA
Resolve-DnsName api.internal.example -Type A
Resolve-DnsName api.internal.example -Type AAAA

# Truy vấn qua DNS server cụ thể
Resolve-DnsName api.internal.example -Server 10.0.0.53

# Xem cache DNS
Get-DnsClientCache
~~~

Nếu kết quả khác nhau giữa các máy, so sánh DNS server, suffix search list, interface metric, cache và vị trí mạng. Không xóa cache DNS trên toàn fleet khi chưa xác định nguyên nhân; thao tác đó có thể làm tăng đột biến truy vấn resolver và chỉ che giấu vấn đề gốc.

### 3.4. TTL và cache

TTL xác định thời gian một DNS record có thể được cache theo quy tắc DNS. TTL thấp giúp thay đổi endpoint nhanh hơn nhưng có thể tăng truy vấn tới resolver. TTL cao giảm tải DNS nhưng client có thể tiếp tục dùng địa chỉ cũ lâu hơn dự kiến.

Ngoài cache của resolver, ứng dụng có thể tự cache kết quả. Một số runtime hoặc thư viện có chính sách cache riêng, vì vậy thay đổi DNS chưa chắc có hiệu lực ngay trên mọi tiến trình.

Khi điều tra:

- So sánh authoritative answer và recursive resolver answer.
- Ghi nhận TTL còn lại.
- Kiểm tra cache của hệ điều hành và runtime.
- Kiểm tra record A và AAAA riêng.
- Thử từng IP trả về bằng công cụ kết nối.
- Xác minh endpoint cũ còn hoạt động trong thời gian chuyển đổi.

### 3.5. Split-horizon và DNS nội bộ

Split-horizon DNS trả về kết quả khác nhau tùy vị trí hoặc resolver. Ví dụ, hostname **db.internal.example** có thể trả về private IP trong VPC và không có record tương ứng trên DNS công cộng.

Điều này hữu ích trong cloud nhưng dễ gây nhầm lẫn khi máy dùng resolver sai, VPN không cấp DNS nội bộ hoặc container không nhận đúng DNS configuration.

Kiểm tra từ đúng network namespace hoặc container đang gặp lỗi. Kết quả **dig** trên host không chứng minh container có cùng resolver hoặc cùng route tới DNS server.

### 3.6. Phân biệt DNS lỗi và kết nối tới IP lỗi

Sau khi lấy được IP, kiểm tra trực tiếp IP và port:

~~~bash
# Kiểm tra route tới IP cụ thể
ip route get 10.20.4.15

# Kiểm tra TCP tới port
nc -vz -w 3 10.20.4.15 443

# Kiểm tra HTTP/TLS bằng hostname và giữ nguyên Host/SNI
curl -v --connect-timeout 3 https://api.internal.example/health
~~~

Khi thử IP trực tiếp với HTTPS, cần giữ đúng hostname để TLS SNI và HTTP Host header được gửi chính xác. Nếu chỉ thay hostname bằng IP trong URL, kết quả có thể khác với kết nối ứng dụng thực tế.

## 4. Chẩn đoán routing

### 4.1. Route trong guest OS và cloud network

Đường đi của packet thường chịu tác động của hai lớp:

- **Guest OS:** route table, policy routing, interface, source IP và firewall trong máy.
- **Cloud network:** route table của subnet/VPC/VNet, peering, transit gateway, NAT, load balancer, network firewall và chính sách của NIC.

Một route hợp lệ trong Linux không bảo đảm cloud network có đường đi. Ngược lại, route table cloud đúng cũng không giúp nếu kernel chọn sai NIC hoặc source IP.

### 4.2. Kiểm tra route trên Linux

~~~bash
# Interface và địa chỉ
ip -br link
ip -br addr

# Route mặc định và route cụ thể
ip route
ip route get 10.20.4.15

# Policy routing
ip rule show
ip route show table all

# Kiểm tra đường đi với source IP cụ thể
ip route get 10.20.4.15 from 10.10.1.20
~~~

**ip route get** cho biết kernel dự kiến chọn interface, gateway và source IP nào cho packet. Nó không chứng minh packet đã đi qua firewall hoặc tới được đích.

Nếu máy có nhiều NIC hoặc nhiều default route, kiểm tra cả **ip rule** và bảng định tuyến tùy chỉnh. Route metric thấp hơn thường được ưu tiên giữa các route tương đương, nhưng policy routing có thể thay đổi bảng được tra cứu.

### 4.3. Kiểm tra route trên Windows

~~~powershell
# Interface và địa chỉ
Get-NetIPConfiguration
Get-NetIPAddress

# Route table
Get-NetRoute -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv6

# Xem interface metric
Get-NetIPInterface

# Kiểm tra đường đi tới đích
Test-NetConnection 10.20.4.15 -Port 443 -InformationLevel Detailed

# Theo dõi hop nếu ICMP/TTL-expired được cho phép
tracert 10.20.4.15
~~~

**Test-NetConnection** hữu ích để kiểm tra TCP tới một port, trong khi **tracert** có thể bị firewall hoặc mạng trung gian chặn. Không kết luận route sai chỉ vì traceroute không hiển thị đủ hop.

### 4.4. Default route và nhiều gateway

Máy có nhiều NIC hoặc nhiều gateway có thể chọn đường ra không như mong muốn. Ví dụ, request đi vào NIC frontend nhưng response đi ra NIC backend do default route ưu tiên khác. Stateful firewall hoặc NAT có thể loại bỏ response.

Cần xác định:

- Interface nhận request.
- Destination và source IP của request.
- Route lookup cho response.
- Gateway được chọn.
- Route table cloud cho chiều đi và chiều về.
- Có NAT, peering hoặc firewall stateful trên đường không.

Nếu cần định tuyến theo source IP, cấu hình policy routing có thể phù hợp hơn việc chỉ thêm nhiều default route. Sau thay đổi, kiểm tra lại bằng route lookup và packet capture.

### 4.5. MTU và Path MTU Discovery

Một kết nối có thể thiết lập được nhưng truyền dữ liệu lớn lại bị treo hoặc chậm. Một nguyên nhân là MTU không phù hợp trên một đoạn đường, hoặc ICMP cần thiết cho Path MTU Discovery bị chặn.

Dấu hiệu có thể gồm:

- TCP handshake thành công nhưng tải file lớn bị đứng.
- Request nhỏ hoạt động, response lớn timeout.
- Một số VPN, overlay hoặc tunnel gặp lỗi.
- Retransmission tăng khi gửi packet lớn.

Kiểm tra MTU interface:

~~~bash
ip link show
tracepath 10.20.4.15
~~~

Có thể dùng **ping** với tùy chọn không phân mảnh trên IPv4 để hỗ trợ kiểm tra MTU, nhưng cú pháp và quyền phụ thuộc hệ điều hành. Không nên giảm MTU hàng loạt chỉ dựa trên một phép thử; cần xác định MTU trên toàn đường truyền và chính sách ICMP của mạng.

## 5. Chẩn đoán firewall và chính sách mạng

### 5.1. Các lớp firewall trong cloud

Một kết nối cloud có thể chịu nhiều lớp kiểm soát:

- Security group hoặc network security group gắn với NIC/instance.
- Network ACL gắn với subnet.
- Cloud firewall hoặc network virtual appliance.
- Firewall của load balancer.
- Firewall trong guest OS.
- Kubernetes NetworkPolicy hoặc chính sách CNI.
- Firewall của dịch vụ đích.

Security group thường là stateful trong nhiều nền tảng, nghĩa là response của kết nối đã được cho phép có thể được chấp nhận tự động. Network ACL thường stateless ở một số nền tảng, nên phải cho phép cả chiều đi và chiều về, bao gồm dải cổng nguồn tạm thời. Hành vi chính xác phụ thuộc nhà cung cấp và loại dịch vụ.

Không nên suy luận rằng một kết nối được phép ở security group thì mọi lớp khác cũng cho phép.

### 5.2. Phân tích rule theo tuple

Một rule mạng cần được đối chiếu theo:

- Source IP/CIDR.
- Destination IP/CIDR.
- Protocol (TCP, UDP, ICMP hoặc protocol khác).
- Destination port hoặc port range.
- Interface/subnet áp dụng.
- Hướng inbound/outbound.
- Thứ tự rule và hành vi mặc định.
- Có NAT hoặc proxy làm thay đổi source IP không.

Ví dụ, server lắng nghe TCP/443 nhưng firewall chỉ cho phép source từ một CIDR cũ. Một số client ở subnet mới sẽ lỗi, trong khi client ở subnet cũ vẫn hoạt động. Điều này tạo cảm giác kết nối chập chờn nếu traffic được phân phối giữa nhiều nguồn.

### 5.3. Kiểm tra firewall trên Linux

Với hệ thống dùng nftables:

~~~bash
sudo nft list ruleset
sudo nft list counters
~~~

Với hệ thống còn dùng iptables:

~~~bash
sudo iptables -S
sudo iptables -L -n -v
sudo ip6tables -S
~~~

Với firewalld:

~~~bash
sudo firewall-cmd --state
sudo firewall-cmd --list-all
sudo firewall-cmd --list-all-zones
~~~

Các công cụ có thể là frontend của cùng một bộ luật hoặc cùng tồn tại theo cấu hình phân phối. Không nên sửa trực tiếp nhiều lớp firewall khi chưa biết công cụ nào là nguồn cấu hình chuẩn.

### 5.4. Kiểm tra firewall trên Windows

~~~powershell
Get-NetFirewallProfile
Get-NetFirewallRule -Enabled True
Get-NetFirewallSetting
~~~

Để tìm rule liên quan đến port, có thể lọc thêm theo protocol và port filter. Cần xem cả profile Domain, Private, Public và interface đang áp dụng profile nào.

### 5.5. Dùng packet capture để xác định điểm rơi

Trên Linux:

~~~bash
# Chỉ quan sát handshake tới một host và port
sudo tcpdump -ni any 'host 10.20.4.15 and tcp port 443'

# Chỉ xem các packet có cờ SYN, bao gồm SYN-ACK
sudo tcpdump -ni any 'host 10.20.4.15 and tcp port 443 and (tcp[tcpflags] & tcp-syn != 0)'
~~~

Một số dấu hiệu:

| Quan sát | Hướng điều tra |
|---|---|
| Không thấy SYN rời client | Ứng dụng, route cục bộ, firewall outbound hoặc host resource |
| Thấy SYN rời client nhưng không có SYN-ACK | Route/cloud policy, firewall trung gian, server không phản hồi hoặc return path |
| Server thấy SYN nhưng không trả SYN-ACK | Listener, host firewall, SYN backlog hoặc host quá tải |
| Server trả SYN-ACK nhưng client không nhận | Route chiều về, NAT/stateful firewall hoặc packet drop trung gian |
| Có RST ngay | Không có listener, ứng dụng từ chối hoặc firewall chủ động reject |
| TCP handshake thành công rồi dữ liệu bị retransmit | Mất packet, MTU, congestion, host/app chậm hoặc đường truyền lỗi |

Capture trên **any** có thể hiển thị packet ở nhiều interface hoặc nhiều giai đoạn của cùng luồng. Nếu có NAT, cần capture ở cả hai phía của thiết bị hoặc đối chiếu flow log để hiểu địa chỉ trước và sau dịch.

Packet capture có thể chứa payload hoặc dữ liệu nhạy cảm. Giới hạn host/port, thời gian và quyền truy cập file capture; ưu tiên chỉ thu header khi phù hợp.

## 6. Giới hạn cổng kết nối và ephemeral ports

### 6.1. Cổng nguồn và cổng đích

Một kết nối TCP được nhận diện bởi bộ bốn (four-tuple):

**source IP : source port -> destination IP : destination port**

Ví dụ:

**10.10.1.20:53124 -> 10.20.4.15:443**

Trong đó:

- **Destination port 443** là cổng dịch vụ HTTPS trên server.
- **Source port 53124** thường là cổng tạm thời do client chọn.
- Mỗi kết nối đồng thời cần một tuple phù hợp; một số tổ hợp có thể được tái sử dụng theo quy tắc TCP và trạng thái socket.

Cổng nguồn tạm thời thường được gọi là **ephemeral port**. Dải cổng do hệ điều hành cấu hình và có thể khác nhau giữa Linux, Windows và các nền tảng khác.

### 6.2. Ephemeral port exhaustion

Một client mở rất nhiều kết nối TCP ngắn tới cùng một destination IP/port có thể dùng hết các cổng nguồn khả dụng trong dải ephemeral. Khi đó, kết nối mới có thể thất bại với lỗi như **Cannot assign requested address**, **Address not available** hoặc timeout tùy stack và ứng dụng.

Các nguyên nhân làm tăng tiêu thụ cổng:

- Tạo kết nối mới cho từng request thay vì tái sử dụng connection pool.
- Đóng/mở kết nối quá nhanh.
- Có nhiều socket ở trạng thái TIME_WAIT.
- Retry đồng loạt khi upstream đang lỗi.
- Nhiều worker cùng kết nối tới một endpoint duy nhất.
- Ứng dụng dùng nhiều source IP hoặc nhiều destination khác nhau nhưng cấu hình pool không hiệu quả.

Kiểm tra trên Linux:

~~~bash
# Dải ephemeral port
sysctl net.ipv4.ip_local_port_range

# Thống kê socket theo trạng thái
ss -s

# Đếm TIME_WAIT
ss -ant state time-wait | wc -l

# Xem socket kết nối tới một destination
ss -ant dst 10.20.4.15:443
~~~

Trên Windows:

~~~powershell
netsh int ipv4 show dynamicport tcp
netstat -ano
Get-NetTCPConnection | Group-Object State | Sort-Object Count -Descending
~~~

Không nên mặc định tăng dải ephemeral port là đủ. Trước hết cần xác định số kết nối mới mỗi giây, thời gian giữ socket, số source IP, destination và tỷ lệ tái sử dụng kết nối.

### 6.3. TIME_WAIT và tái sử dụng kết nối

TIME_WAIT là trạng thái TCP xuất hiện sau khi một endpoint chủ động đóng kết nối trong một số trường hợp. Trạng thái này giúp xử lý packet trễ và bảo đảm kết nối cũ kết thúc an toàn. Có nhiều TIME_WAIT không tự động chứng minh lỗi; số lượng cần được đặt trong bối cảnh dải port, tốc độ tạo kết nối và destination.

Các biện pháp thường hiệu quả hơn chỉnh kernel tùy tiện:

- Dùng HTTP keep-alive và connection pooling.
- Tái sử dụng kết nối database và cache.
- Đặt pool size theo capacity của upstream.
- Dùng timeout hợp lý để tránh giữ socket vô hạn.
- Tránh retry quá nhanh hoặc retry không giới hạn.
- Dùng nhiều destination hoặc source IP khi kiến trúc thực sự cần và nền tảng hỗ trợ.

Không nên bật các kernel option về TCP reuse/recycle theo hướng dẫn cũ mà không kiểm tra phiên bản. Một số tùy chọn đã thay đổi hoặc bị loại bỏ; chỉnh sai có thể gây lỗi kết nối và ảnh hưởng bảo mật.

### 6.4. SNAT/NAT gateway port exhaustion

Khi nhiều workload đi Internet hoặc mạng khác qua cùng một NAT gateway, NAT có thể cần cấp phát source port để phân biệt các kết nối. Một lượng lớn kết nối đồng thời tới cùng đích hoặc qua cùng địa chỉ NAT có thể gây cạn cổng SNAT, tùy cơ chế và giới hạn của nền tảng.

Dấu hiệu:

- Nhiều VM trong cùng subnet lỗi kết nối outbound cùng lúc.
- Kết nối nội bộ vẫn tốt nhưng outbound qua NAT thất bại.
- Lỗi tăng theo số lượng kết nối mới hoặc burst traffic.
- NAT gateway báo số cổng được sử dụng cao, allocation failure hoặc drop.
- Thêm một NAT path hoặc source IP làm thay đổi tỷ lệ lỗi.

Hướng điều tra:

1. Xác định subnet và route có đi qua NAT gateway không.
2. Kiểm tra metric/counter của NAT theo nhà cung cấp.
3. So sánh số kết nối mới, số kết nối đồng thời và destination phổ biến.
4. Xem ứng dụng có mở kết nối ngắn liên tục hay không.
5. Kiểm tra timeout và connection reuse.
6. Đánh giá tăng capacity NAT, thêm địa chỉ IP NAT hoặc chia tải theo thiết kế cloud nếu cần.

Nhiều nền tảng có cách phân bổ port và quota NAT khác nhau. Không áp dụng một con số cổng cố định cho mọi cloud provider; dùng metric và tài liệu của dịch vụ đang chạy.

### 6.5. Conntrack table đầy

Linux có thể dùng connection tracking (conntrack) để theo dõi trạng thái kết nối, thường được firewall/NAT sử dụng. Nếu số entry chạm giới hạn, packet mới có thể bị drop hoặc log xuất hiện thông báo bảng conntrack đầy.

Kiểm tra khi hệ thống có công cụ conntrack:

~~~bash
sudo conntrack -S
sudo conntrack -C
sysctl net.netfilter.nf_conntrack_max
~~~

Các lệnh và file sysctl phụ thuộc kernel/module đã nạp. Không phải mọi VM đều dùng conntrack cho mọi luồng. Cần kiểm tra counter insert failed, drop và current count trước khi tăng **nf_conntrack_max**.

Tăng giới hạn mà không tăng bộ nhớ hoặc kiểm soát số kết nối có thể làm host tiêu thụ thêm RAM và che giấu connection leak. Cần tìm nguyên nhân tăng entry, timeout không phù hợp hoặc workload tạo quá nhiều kết nối.

## 7. Giới hạn ở server: listener, backlog và file descriptor

### 7.1. Không có listener hoặc bind sai địa chỉ

Server có thể không lắng nghe trên port mong muốn, hoặc chỉ bind vào loopback. Ví dụ ứng dụng bind **127.0.0.1:8080** sẽ không nhận kết nối từ NIC bên ngoài qua **10.20.4.15:8080**.

Kiểm tra Linux:

~~~bash
ss -lntup
sudo lsof -iTCP -sTCP:LISTEN -P -n
~~~

Kiểm tra Windows:

~~~powershell
Get-NetTCPConnection -State Listen
netstat -ano
~~~

Đối chiếu địa chỉ bind, port, protocol, PID và trạng thái process. **0.0.0.0** chỉ có nghĩa lắng nghe trên các địa chỉ IPv4 cục bộ; IPv6 listener và dual-stack phụ thuộc cấu hình socket và hệ điều hành.

### 7.2. TCP listen backlog

Khi client gửi SYN, kernel và ứng dụng cần xử lý quá trình thiết lập kết nối. Nếu server quá tải hoặc ứng dụng không accept đủ nhanh, hàng đợi SYN hoặc accept queue có thể đầy. Kết quả có thể là handshake bị trì hoãn, retransmission hoặc connection failure.

Một số chỉ số/cấu hình Linux:

~~~bash
sysctl net.core.somaxconn
sysctl net.ipv4.tcp_max_syn_backlog
ss -lnt
~~~

**ss -lnt** có thể hiển thị Recv-Q và Send-Q cho socket đang listen; ý nghĩa cụ thể phụ thuộc trạng thái và phiên bản. Kiểm tra log kernel và counter TCP nếu nghi backlog overflow.

Tăng backlog chỉ hữu ích nếu ứng dụng có khả năng accept và xử lý kết nối. Nếu CPU, worker hoặc database đã quá tải, tăng queue có thể chỉ làm thời gian chờ dài hơn.

### 7.3. File descriptor và socket limit

Trên Unix-like OS, socket là file descriptor. Một process mở quá nhiều file hoặc socket có thể chạm giới hạn **ulimit -n**, giới hạn systemd **LimitNOFILE** hoặc giới hạn toàn hệ thống.

Kiểm tra:

~~~bash
ulimit -n
cat /proc/$(pidof my-service)/limits
ls /proc/$(pidof my-service)/fd | wc -l
cat /proc/sys/fs/file-nr
~~~

Thay **my-service** bằng tên process thực tế. **ulimit** trong shell hiện tại không nhất thiết phản ánh giới hạn của service đã được systemd khởi chạy. Cần kiểm tra unit file, override và giới hạn process thực tế.

Khi gặp **Too many open files**, tìm socket hoặc file bị giữ lâu, connection leak, log file không rotate hoặc pool không đóng tài nguyên. Tăng limit có thể là cần thiết nhưng phải đi kèm kiểm soát memory và số kết nối.

### 7.4. Connection pool cạn

Ứng dụng có thể không hết cổng hệ điều hành nhưng vẫn hết kết nối trong pool. Ví dụ, API chỉ có 50 connection tới database. Khi 50 connection đều bị giữ bởi query chậm, request mới phải chờ dù database và network vẫn hoạt động.

Theo dõi:

- Pool size và số connection đang dùng/đang chờ.
- Thời gian chờ lấy connection.
- Thời gian giữ connection.
- Query duration và lock wait.
- Timeout, leak detection và số lần retry.
- Số kết nối thực tế trên database.

Không nên chỉ tăng pool size. Database có giới hạn connection và mỗi connection tiêu thụ memory/CPU. Cần tối ưu query, transaction, pool timeout và concurrency theo capacity của database.

## 8. Kết nối chập chờn trong container và Kubernetes

### 8.1. Kiểm tra từ đúng network namespace

Container hoặc pod có network namespace riêng. DNS, route, interface và firewall path bên trong có thể khác host. Vì vậy, một lệnh chạy trên node thành công không chứng minh pod có thể kết nối.

Kiểm tra từ container/pod đang lỗi:

~~~bash
cat /etc/resolv.conf
getent ahosts api.internal.example
ip -br addr
ip route
nc -vz -w 3 api.internal.example 443
~~~

Nếu image ứng dụng không có công cụ debug, dùng ephemeral debug container hoặc một pod chẩn đoán có cùng namespace/network policy theo quy trình nền tảng. Không cài công cụ tùy tiện vào image production chỉ để debug.

### 8.2. CNI, NetworkPolicy và service routing

Kubernetes network path có thể liên quan tới:

- Pod network interface và CNI.
- NetworkPolicy.
- Service ClusterIP và kube-proxy hoặc dataplane thay thế.
- CoreDNS.
- Ingress/Gateway và load balancer.
- Node route, overlay hoặc eBPF dataplane.
- Security group/firewall của node và subnet.

Nếu chỉ một namespace hoặc label selector bị lỗi, kiểm tra NetworkPolicy trước. Nếu tất cả pod cùng node bị ảnh hưởng, xem node, CNI, route và NIC. Nếu pod kết nối Service lỗi nhưng kết nối trực tiếp Pod IP thành công, kiểm tra Service endpoint, dataplane và readiness.

### 8.3. DNS trong Kubernetes

CoreDNS thường phục vụ DNS cho pod. Các nguyên nhân có thể gồm CoreDNS quá tải, lỗi upstream resolver, NetworkPolicy chặn UDP/TCP 53, search path dài hoặc ứng dụng tạo truy vấn quá nhiều.

Kiểm tra:

~~~bash
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl get svc -n kube-system kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100
~~~

Label, namespace và cách triển khai CoreDNS có thể khác giữa các cluster. Xác minh tên deployment/service thực tế trước khi chạy lệnh.

DNS thường dùng UDP/53 nhưng có thể dùng TCP/53 khi response lớn hoặc cần fallback. Firewall chỉ cho UDP mà chặn TCP có thể tạo lỗi với một số truy vấn.

### 8.4. Pod churn và connection reset

Khi pod bị restart, scale down hoặc thay endpoint, kết nối đang mở tới pod cũ có thể bị reset. Client cần xử lý lỗi kết nối và tái lập connection phù hợp. Readiness probe giúp tránh gửi request mới tới pod chưa sẵn sàng, nhưng không bảo đảm mọi kết nối dài đang mở được chuyển sang pod khác.

Cần kiểm tra:

- Pod restart count và termination reason.
- EndpointSlice thay đổi.
- Readiness/liveness probe.
- Graceful shutdown và **terminationGracePeriodSeconds**.
- Connection draining tại ingress/load balancer.
- Keep-alive, retry và idempotency của client.

## 9. Quy trình chẩn đoán có hệ thống

### 9.1. Bước 1: Xác định triệu chứng và phạm vi

Ghi lại nguồn, đích, port, protocol, thời gian và tỷ lệ lỗi. Xác định lỗi chỉ xảy ra với request mới hay cả kết nối đang hoạt động.

### 9.2. Bước 2: Kiểm tra DNS

Phân giải hostname từ chính môi trường lỗi. Ghi lại A/AAAA, TTL, resolver và so sánh từng IP. Thử kết nối trực tiếp tới mỗi IP trong khi vẫn giữ hostname/SNI khi kiểm tra TLS.

### 9.3. Bước 3: Kiểm tra route và source IP

Dùng **ip route get** hoặc công cụ tương đương để xác nhận interface, gateway và source IP. Kiểm tra route table cloud, peering, NAT và return path.

### 9.4. Bước 4: Kiểm tra port và firewall

Xác nhận server có listener đúng địa chỉ/port. Kiểm tra firewall host, security group, NACL, NetworkPolicy và load balancer. Đối chiếu cả chiều đi và chiều về.

### 9.5. Bước 5: Kiểm tra TCP handshake và packet loss

Dùng **tcpdump**, flow log hoặc metric network để xác định SYN, SYN-ACK, ACK, RST và retransmission. Xác định packet biến mất ở phía client, mạng trung gian hay server.

### 9.6. Bước 6: Kiểm tra giới hạn kết nối

Đo số socket, TIME_WAIT, ephemeral port range, NAT port usage, conntrack count, listener backlog, file descriptor và connection pool. Đối chiếu với thời điểm lỗi.

### 9.7. Bước 7: Kiểm tra tải host và ứng dụng

Theo dõi CPU, memory, network, disk I/O, GC, worker queue, database latency và upstream response time. Kết nối TCP có thể thành công nhưng ứng dụng vẫn timeout vì không có worker hoặc dependency phản hồi.

### 9.8. Bước 8: Thay đổi có kiểm soát và xác minh

Chỉ thay một nhóm cấu hình có liên quan mỗi lần. Lưu cấu hình cũ, có phương án rollback và kiểm tra lại cùng phép thử. Sau thay đổi, theo dõi tỷ lệ lỗi đủ lâu để bao phủ chu kỳ tải đã từng gây sự cố.

## 10. Bảng triệu chứng và hướng điều tra

| Triệu chứng | Khả năng cần kiểm tra | Bằng chứng hữu ích |
|---|---|---|
| Hostname lúc phân giải được, lúc không | Resolver, upstream DNS, cache, record | dig, Resolve-DnsName, DNS logs |
| Một IP trong nhiều IP bị timeout | Endpoint lỗi, route hoặc firewall riêng | Test từng IP, health check, flow logs |
| TCP timeout nhưng DNS thành công | Route, firewall drop, NAT, return path | ip route get, packet capture |
| Connection refused ngay | Không có listener hoặc reject | ss -lntup, server logs, RST |
| Lỗi tăng mạnh khi tải cao | Port, NAT, conntrack, backlog, pool, FD | Socket state, NAT metrics, app metrics |
| Chỉ outbound Internet lỗi | Default route, NAT gateway, egress firewall | Route table, NAT metrics, flow logs |
| Chỉ một subnet lỗi | Route, NACL, security policy, DNS resolver subnet | So sánh cấu hình subnet |
| Request nhỏ thành công, dữ liệu lớn treo | MTU/PMTUD, packet loss, congestion | tracepath, retransmission, packet capture |
| Kết nối đã mở bị reset khi deploy | Pod/VM replacement, draining, process restart | Deployment events, endpoint changes |
| TCP connect thành công nhưng HTTP timeout | App worker, upstream, DB, pool, queue | Trace, app log, pool metrics |

Bảng chỉ đưa ra hướng điều tra. Một triệu chứng có thể có nhiều nguyên nhân; cần xác nhận bằng bằng chứng tại thời điểm lỗi.

## 11. Ví dụ xử lý sự cố thực tế

### Tình huống: API outbound chập chờn khi tải tăng

Một nhóm worker trong private subnet gọi tới API đối tác qua NAT gateway. Ở tải thấp, request thành công. Khi số job đồng thời tăng, tỷ lệ timeout tăng lên. DNS vẫn phân giải hostname, còn kết nối nội bộ tới database hoạt động bình thường.

Quy trình điều tra:

1. Ghi timestamp, hostname, IP trả về và tỷ lệ timeout.
2. Phân giải hostname nhiều lần và thử từng IP đích để loại trừ một endpoint lỗi.
3. Kiểm tra **ip route get** xác nhận traffic đi qua default route tới NAT gateway.
4. Kiểm tra firewall outbound và security policy; không thấy rule drop bất thường.
5. Quan sát socket client, thấy số lượng kết nối mới tăng nhanh và nhiều socket ở TIME_WAIT.
6. Đối chiếu metric NAT, thấy số cổng SNAT sử dụng tăng cao và có allocation failure cùng thời điểm.
7. Kiểm tra ứng dụng, phát hiện mỗi request tạo một HTTP client mới và không tái sử dụng connection.
8. Thay đổi ứng dụng để dùng connection pool/keep-alive, giới hạn concurrency và retry có backoff.
9. Theo dõi số kết nối mới, NAT port usage, timeout và latency sau triển khai.
10. Nếu vẫn thiếu capacity, đánh giá mở rộng NAT theo tính năng của nhà cung cấp và chia tải theo kiến trúc cloud.

Kết quả cần được xác minh bằng metric trước/sau. Không nên kết luận NAT là nguyên nhân chỉ vì số TIME_WAIT cao; bằng chứng quan trọng là NAT allocation failure trùng thời điểm lỗi và được cải thiện sau khi giảm tốc độ tạo kết nối.

### Tình huống: Chỉ một phần client lỗi HTTPS

Một dịch vụ có hai bản ghi A. Một endpoint đã được thay thế nhưng vẫn còn trong DNS hoặc cache. Client nhận record khác nhau theo resolver và thời điểm. Một endpoint hoạt động, endpoint còn lại không còn listener.

Các bước:

- Truy vấn A record qua resolver nội bộ và authoritative DNS.
- Ghi lại TTL và các địa chỉ trả về.
- Thử TCP/443 tới từng IP.
- Kiểm tra health check và listener trên endpoint.
- Cập nhật record hoặc phục hồi endpoint theo quy trình.
- Duy trì endpoint cũ trong thời gian chuyển đổi phù hợp với TTL và cache ứng dụng.
- Theo dõi tỷ lệ lỗi theo destination IP.

Bài học là một hostname có thể phân giải thành công nhưng vẫn chứa một endpoint không phục vụ được.

### Tình huống: TCP handshake thành công nhưng upload lớn bị treo

Client gửi request nhỏ thành công, nhưng upload file lớn bị timeout. Packet capture cho thấy retransmission của các segment lớn. Route và firewall không có thay đổi rõ ràng.

Nhóm kiểm tra MTU giữa VPN, overlay và subnet, phát hiện một tunnel có MTU thấp hơn nhưng ICMP cần cho Path MTU Discovery bị chặn. Sau khi điều chỉnh MTU hoặc chính sách ICMP theo thiết kế mạng, upload được kiểm thử lại với nhiều kích thước payload.

## 12. Phòng ngừa kết nối chập chờn

### 12.1. Thiết kế DNS có kiểm soát

- Dùng resolver dự phòng và giám sát latency/lỗi truy vấn.
- Quản lý TTL theo khả năng chuyển đổi endpoint.
- Xóa record cũ đúng thời điểm và theo dõi cache ứng dụng.
- Kiểm tra cả A và AAAA.
- Dùng health check để tránh trả endpoint không khỏe nếu nền tảng hỗ trợ.
- Giám sát DNS từ từng subnet hoặc network namespace quan trọng.

### 12.2. Quản lý kết nối ứng dụng

- Dùng connection pooling và keep-alive.
- Đặt timeout riêng cho DNS, connect, TLS handshake, request và response.
- Dùng retry có giới hạn, exponential backoff và jitter.
- Chỉ retry thao tác có thể retry an toàn; với request không idempotent cần idempotency key hoặc cơ chế bảo vệ.
- Dùng circuit breaker để ngăn retry storm khi upstream lỗi.
- Giới hạn concurrency và queue depth.
- Đóng socket, response body và connection đúng cách.

Timeout tổng nên phù hợp với ngân sách latency của request. Nếu connect timeout, read timeout và retry đều quá lớn, một request có thể giữ worker và socket quá lâu.

### 12.3. Capacity và giới hạn kết nối

- Theo dõi ephemeral ports, TIME_WAIT và connection rate.
- Theo dõi NAT gateway port usage và allocation failure.
- Theo dõi conntrack count, drop và insert failure.
- Theo dõi listen backlog, socket queue và file descriptor.
- Đặt pool size theo capacity của upstream.
- Giới hạn số kết nối trên mỗi host/tenant.
- Kiểm tra quota và giới hạn load balancer hoặc proxy.

### 12.4. Quản lý firewall và route

- Lưu cấu hình route và firewall dưới dạng mã khi phù hợp.
- Review thay đổi security group, NACL, NetworkPolicy và host firewall.
- Duy trì route hai chiều và kiểm tra return path.
- Kiểm thử cả IPv4 và IPv6 nếu workload bật dual-stack.
- Tránh thay đổi đồng thời nhiều lớp mạng mà không có trace/bằng chứng.
- Giám sát flow log và counter drop.

### 12.5. Quan sát xuyên suốt

Kết hợp các nguồn:

- Application log có request ID.
- Distributed tracing và span DNS/connect/TLS/upstream.
- Metrics của client connection pool.
- Host metrics và socket state.
- Cloud flow logs, NAT metrics và load balancer metrics.
- DNS resolver logs và latency.
- Firewall counters và packet capture khi cần.

Metric nên được gắn nhãn theo workload, zone, node pool và destination service ở mức cardinality có thể kiểm soát. Tránh gắn mỗi IP client hoặc request ID làm label metric có cardinality rất cao.

## 13. Những sai lầm thường gặp

**Chỉ ping hostname để kiểm tra.** Ping thường dùng ICMP, không chứng minh TCP port của ứng dụng hoạt động. DNS có thể phân giải đúng trong khi TCP bị chặn.

**Chỉ thử một IP của hostname.** DNS có thể trả nhiều địa chỉ và chỉ một endpoint gặp lỗi. Cần thử từng IP.

**Cho rằng DNS thành công nghĩa là kết nối thành công.** DNS chỉ trả lời câu hỏi tên tương ứng với địa chỉ nào; route, firewall, listener và ứng dụng vẫn có thể lỗi.

**Tăng timeout để che giấu lỗi.** Timeout dài hơn có thể làm worker và socket bị giữ lâu hơn, khiến sự cố tài nguyên nghiêm trọng hơn.

**Retry không giới hạn.** Retry storm làm tăng kết nối mới và tải lên dịch vụ đang lỗi, có thể gây cạn ephemeral ports hoặc NAT ports.

**Tăng ephemeral port range mà không đo.** Vấn đề có thể nằm ở connection leak, NAT, conntrack hoặc pool. Cần xác định nơi cạn tài nguyên trước.

**Tăng backlog hoặc file descriptor mà không kiểm tra ứng dụng.** Nếu worker không accept hoặc xử lý kịp, queue lớn hơn chỉ làm request chờ lâu hơn.

**Chỉ xem firewall của host.** Cloud security group, NACL, route, NAT, load balancer và NetworkPolicy có thể là điểm chặn.

**Bỏ qua đường về.** Request tới server không bảo đảm response quay lại đúng đường. Cần kiểm tra source IP, policy routing và stateful device.

**Sửa nhiều lớp cùng lúc.** Khi route, DNS và firewall cùng thay đổi, khó xác định thay đổi nào giải quyết hoặc gây lỗi. Thay từng bước và lưu bằng chứng.

## 14. Checklist xử lý sự cố

### Thu thập thông tin

- [ ] Ghi timestamp, source, destination, port, protocol và request ID.
- [ ] Xác định phạm vi client, subnet, zone, node và workload.
- [ ] Phân loại lỗi DNS, timeout, refused, reset hay ứng dụng chậm.
- [ ] So sánh một lần thành công với một lần thất bại.

### DNS và routing

- [ ] Kiểm tra A/AAAA, TTL, resolver và cache.
- [ ] Thử từng IP trả về.
- [ ] Kiểm tra route, source IP và interface đầu ra.
- [ ] Kiểm tra cloud route table, peering, NAT và return path.
- [ ] Kiểm tra IPv4/IPv6 và MTU nếu lỗi phụ thuộc kích thước dữ liệu.

### Firewall và TCP

- [ ] Kiểm tra security group, NACL, host firewall và NetworkPolicy.
- [ ] Xác nhận listener đúng IP/port/protocol.
- [ ] Kiểm tra SYN, SYN-ACK, ACK, RST và retransmission.
- [ ] Xác minh firewall cho cả chiều đi và chiều về.

### Giới hạn kết nối

- [ ] Kiểm tra ephemeral port range và socket state.
- [ ] Đo TIME_WAIT và connection rate.
- [ ] Kiểm tra NAT/SNAT port usage và allocation failure.
- [ ] Kiểm tra conntrack count/drop.
- [ ] Kiểm tra listen backlog, file descriptor và connection pool.
- [ ] Đối chiếu với CPU, memory và tải upstream.

### Khắc phục và xác minh

- [ ] Xác định nguyên nhân bằng bằng chứng tại thời điểm lỗi.
- [ ] Lưu cấu hình cũ và chuẩn bị rollback.
- [ ] Thay đổi từng nhóm cấu hình có liên quan.
- [ ] Chạy lại cùng phép thử từ đúng môi trường.
- [ ] Theo dõi tỷ lệ lỗi và latency qua chu kỳ tải đại diện.
- [ ] Ghi nhận nguyên nhân, hành động và biện pháp phòng ngừa.

## 15. Ghi nhớ

- Kết nối chập chờn có thể xuất phát từ DNS, routing, firewall, NAT, cổng nguồn, backlog, file descriptor hoặc ứng dụng.
- DNS phân giải thành công không chứng minh mọi IP trả về đều hoạt động.
- Route phải đúng ở cả guest OS và cloud network; luôn kiểm tra đường đi và đường về.
- Security group, NACL, host firewall, NetworkPolicy và firewall trung gian có hành vi khác nhau.
- Ephemeral port exhaustion thường liên quan tới tốc độ tạo kết nối, TIME_WAIT và thiếu connection reuse.
- NAT gateway có thể hết khả năng cấp phát port; cần kiểm tra metric dịch vụ thay vì đoán giới hạn.
- Conntrack, listen backlog, file descriptor và connection pool là các giới hạn độc lập.
- Packet capture giúp xác định SYN/SYN-ACK/RST và vị trí packet bị mất.
- Connection pooling, timeout hợp lý, retry có backoff và giới hạn concurrency giúp giảm áp lực mạng.
- Mọi thay đổi cần được xác minh bằng cùng phép thử và metric trước/sau.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| DNS | Domain Name System, hệ thống phân giải tên miền thành địa chỉ và thông tin dịch vụ. |
| A record | Bản ghi DNS ánh xạ hostname sang địa chỉ IPv4. |
| AAAA record | Bản ghi DNS ánh xạ hostname sang địa chỉ IPv6. |
| TTL | Time To Live, thời gian một DNS record có thể được cache. |
| Split-horizon DNS | Cơ chế DNS trả về kết quả khác nhau tùy resolver hoặc vị trí mạng. |
| Route table | Bảng quy tắc chọn next hop và interface cho packet. |
| Asymmetric routing | Đường đi và đường về sử dụng các tuyến khác nhau. |
| Security group | Chính sách firewall gắn với tài nguyên mạng/compute trong cloud. |
| NACL | Network Access Control List, chính sách kiểm soát packet ở subnet trong một số nền tảng cloud. |
| Ephemeral port | Cổng nguồn tạm thời do hệ điều hành cấp cho kết nối đi ra. |
| Four-tuple | Bộ source IP, source port, destination IP và destination port nhận diện luồng TCP/UDP. |
| TIME_WAIT | Trạng thái TCP sau khi một endpoint chủ động đóng kết nối trong các trường hợp quy định. |
| SNAT | Source Network Address Translation, thay đổi địa chỉ nguồn khi packet đi qua NAT. |
| Conntrack | Cơ chế theo dõi trạng thái kết nối, thường được firewall/NAT sử dụng. |
| Backlog | Hàng đợi kết nối hoặc yêu cầu chờ được ứng dụng accept/xử lý. |
| File descriptor | Định danh tài nguyên mở của tiến trình, bao gồm file và socket trên Unix-like OS. |
| Connection pool | Tập kết nối được tái sử dụng để giảm chi phí mở/đóng kết nối. |
| Keep-alive | Cơ chế giữ kết nối để tái sử dụng cho nhiều request hoặc trao đổi tiếp theo. |
| MTU | Maximum Transmission Unit, kích thước packet/frame tối đa trên một liên kết theo cấu hình. |
| PMTUD | Path MTU Discovery, cơ chế xác định MTU phù hợp trên toàn đường truyền. |
| CNI | Container Network Interface, giao diện tích hợp mạng cho container và pod. |
| NetworkPolicy | Chính sách kiểm soát lưu lượng vào/ra của pod trong Kubernetes. |
| Retransmission | Việc gửi lại packet khi chưa nhận được xác nhận theo giao thức. |
| Circuit breaker | Cơ chế tạm ngừng gọi dependency đang lỗi để ngăn lỗi lan rộng. |
