# So sánh capture ở client, proxy và server

## 1. Vì sao phải quan sát cùng một luồng ở nhiều điểm?

Một người dùng báo trang web mất 30 giây rồi trả **504 Gateway Timeout**. Access log ở reverse proxy cho biết upstream không phản hồi kịp, nhưng chưa trả lời đầy đủ các câu hỏi: client thực sự đã kết nối tới proxy chưa, proxy có mở kết nối tới server không, server có nhận request và gửi response không, hay packet phản hồi bị mất trên đường về?

**Packet capture (PCAP)** là bằng chứng về các packet mà điểm thu thập **quan sát được** trên một interface trong một khoảng thời gian. Đặt điểm thu ở **client**, **proxy** và **server** tạo ra ba góc nhìn khác nhau. So sánh chúng giúp thu hẹp vị trí phát sinh sự cố: đoạn client–proxy, xử lý nội bộ tại proxy, đoạn proxy–server hoặc xử lý tại ứng dụng.

Trong chương **Packet capture và phân tích lưu lượng** của mô-đun **SECURITY_NETWORK_SECURITY**, cách tiếp cận đa điểm còn giúp xác minh kết quả của phân đoạn mạng, firewall/ACL, WAF, NAT, VPN, load balancer, IDS/IPS, DNS và kết nối trong hạ tầng đám mây. PCAP bổ sung cho flow log, access log, metric và distributed tracing; nó không tự cung cấp kết luận về nguyên nhân gốc.

**Mục tiêu bài học:**

- Phân biệt chính xác những gì client, proxy và server có thể nhìn thấy.
- Hiểu vì sao hai kết nối TCP/TLS ở hai phía reverse proxy không phải một kết nối duy nhất.
- Thiết kế capture đồng thời với bộ lọc và giao diện thích hợp.
- Đối chiếu packet qua NAT, TLS termination, retry, cache, WAF và các tầng mạng.
- Dùng kết quả để điều tra timeout, reset, mất kết nối, độ trễ và sai lệch chính sách mạng.
- Nhận ra giới hạn quan sát, false positive do offloading, capture loss và sai lệch đồng hồ.

## 2. Mô hình tham chiếu: một request, hai chặng kết nối

Xét một hệ thống giả định:

~~~text
   Client                  Reverse proxy / WAF               Application server
   198.51.100.22           Public: 203.0.113.10:443           10.30.1.7:8080
                           Private: 10.20.1.5

   [Capture C]                  [Capture P-in]                  [Capture S]
        |                              |                             |
        +--- TCP/TLS, HTTPS :443 ----->|                             |
                                       |   [Capture P-out]           |
                                       +---- TCP/HTTP :8080 -------->|
                                       |<--- TCP/HTTP response ------+
        |<--- HTTPS response ----------+
~~~

Các địa chỉ **198.51.100.0/24** và **203.0.113.0/24** là dải dành cho tài liệu; địa chỉ 10.x minh họa mạng nội bộ. Các địa chỉ, port và giao diện phải được thay bằng thông tin thực tế khi áp dụng.

Trong mô hình này, reverse proxy **kết thúc TLS phía client**, đọc HTTP request, áp dụng WAF/routing rồi tạo **kết nối HTTP mới** đến server. Khi đó:

- Chặng **client ↔ proxy** có TCP sequence, ACK, cửa sổ, retransmission và phiên TLS riêng.
- Chặng **proxy ↔ server** có TCP sequence và ACK **khác**; nếu cấu hình HTTPS upstream, nó còn có phiên TLS riêng.
- TCP packet phía client **không được chuyển nguyên xi** đến server theo kiểu end-to-end; proxy nhận, xử lý và phát sinh các packet mới.
- Proxy có thể trả response từ cache, từ rule WAF, từ cấu hình redirect hoặc khi không có upstream khỏe; trong các trường hợp đó **không nhất thiết có packet tại server**.

Một hệ thống **forward proxy**, **L4 load balancer**, **transparent proxy** hoặc **direct server return (DSR)** có thể hoạt động khác. Trước khi so sánh PCAP, phải xác nhận thiết bị là **TCP endpoint thực sự** (L7 reverse proxy) hay chỉ forward/chuyển địa chỉ packet. Không thể suy mô hình xử lý chỉ từ nhãn "proxy".

## 3. Bảng so sánh ba điểm capture

| Tiêu chí | Client | Proxy | Server |
| --- | --- | --- | --- |
| Câu hỏi ưu tiên | Client gửi/nhận những packet nào? | Request có tới proxy, được xử lý và forward ra upstream không? | Server có nhận kết nối, request và gửi response không? |
| Địa chỉ quan sát | Đích thường là VIP/IP của proxy | Chân ngoài thấy client; chân trong thấy upstream và địa chỉ proxy/NAT | Nguồn thường là địa chỉ proxy hoặc load balancer, tùy chế độ NAT/transparent |
| TLS | Thấy các bản ghi TLS trên dây; plaintext có thể tồn tại ở tầng ứng dụng client nhưng không nằm trong PCAP NIC thông thường | Nếu TLS termination: có thể quan sát bản tin HTTP sau giải mã qua application logs, hoặc đoạn upstream không mã hóa | Thấy HTTP nếu proxy gửi plaintext; chỉ thấy ciphertext nếu kết nối upstream dùng TLS |
| TCP sequence/ACK | Theo phiên TCP client–proxy | Hai bộ trạng thái TCP riêng nếu proxy terminate L7 | Theo phiên TCP proxy–server |
| DNS | Có thể thấy truy vấn DNS của client nếu thu đúng interface và DNS không được mã hóa | Có thể thấy truy vấn DNS của proxy để phân giải upstream | Có thể thấy DNS do server tự thực hiện, không mặc nhiên có truy vấn client |
| Trường hợp WAF chặn | Thấy response/chặn hoặc timeout phía client | Thấy rule, action, có thể không mở upstream | Có thể không có packet cho request này |
| Giới hạn | Không chứng minh packet đã tới proxy | Chỉ nhìn được interface và leg đã capture; không mặc nhiên thấy lưu lượng nội bộ của mọi container | Không chứng minh client đã nhận response |
| Kết hợp nguồn dữ liệu | Client log, hệ điều hành, DNS cache | Access/WAF log, route, upstream timing, NAT/session table | Application log, connection pool, trace, host/network counters |

**Điểm quan trọng:** chữ "thấy" chỉ có nghĩa là packet xuất hiện tại **đúng điểm quan sát**. Một dòng PCAP không khẳng định tất cả hop khác đã nhận packet đó. Và **không thấy** packet tại một điểm có thể do filter, sai interface, capture loss hoặc đường mạng bất đối xứng.

## 4. Capture phía client: điểm nhìn từ người phát sinh yêu cầu

### 4.1. Những điều client có thể xác nhận

Trên giao diện đi ra mạng của client, PCAP có thể cho thấy:

1. Client gửi gói **TCP SYN** tới địa chỉ/port đích hay không.
2. Có **SYN-ACK**, **RST**, **ICMP error** hoặc không có phản hồi trong cửa sổ quan sát.
3. Kết nối có thực hiện TLS handshake hoặc QUIC handshake hay không.
4. Khi kết nối đã thiết lập, client có truyền payload dạng bản ghi mã hóa, chờ ACK, retransmit hoặc nhận FIN/RST.
5. Thời điểm client quan sát response đầu tiên và thời gian các packet về đến interface.

Nếu người dùng gõ tên miền mà không kết nối được, capture riêng **TCP/443** không đủ để phân tích bước DNS: cần kiểm tra DNS cache, resolver, DoH/DoT hoặc thu thêm các luồng thích hợp. PCAP client cũng không cho biết trực tiếp bước xử lý server nào gây chậm.

### 4.2. Hai ví dụ diễn giải

~~~text
Client PCAP:
12:00:00.000  198.51.100.22 -> 203.0.113.10 TCP SYN 443
12:00:01.001  198.51.100.22 -> 203.0.113.10 TCP SYN 443 (retry)
12:00:03.003  198.51.100.22 -> 203.0.113.10 TCP SYN 443 (retry)
~~~

Diễn giải đúng: **client đã phát SYN; trong capture không quan sát thấy SYN-ACK**. Chưa đủ dữ kiện để khẳng định firewall drop; phải kiểm tra tại phía proxy hoặc các hop trung gian.

~~~text
Client PCAP:
12:10:00.000  SYN
12:10:00.025  SYN-ACK
12:10:00.026  ACK
12:10:00.050  TLS handshake ...
12:10:00.080  TLS Application Data (request)
12:10:30.090  TLS Application Data (response)
~~~

Ở ví dụ thứ hai, client thấy độ trễ khoảng 30 giây giữa các bản ghi ứng dụng, nhưng PCAP tại interface không thể mặc nhiên biết đây là lỗi **Java backend**, **proxy buffering**, **WAF inspection**, **upstream timeout** hay thao tác khác. Cần kiểm tra proxy và server cùng thời điểm.

**Giới hạn tại host:** NIC offloading (TSO/GSO/GRO/LRO, checksum offload) có thể khiến packet trong capture trên máy khác packet thực tế đi trên dây. Hãy đối chiếu counters, thông số offloading và, khi cần, capture độc lập trên SPAN/TAP.

## 5. Capture tại proxy: tách ingress và egress

Đây thường là vị trí cung cấp nhiều tín hiệu nhất vì reverse proxy biết cả **kết nối đi vào** và **kết nối upstream đi ra**.

### 5.1. Leg vào (downstream / ingress)

Capture tại interface public-facing hoặc interface nhận traffic từ load balancer phía trước trả lời:

- SYN từ client có tới proxy không, và proxy có trả SYN-ACK/RST không?
- TLS handshake có được thiết lập không?
- Client có gửi dữ liệu và nhận phản hồi không?
- Một connection có bị đóng sớm, reset hay retransmit nhiều lần không?

Nếu có CDN/WAF phía trước reverse proxy, "client" mà proxy nhìn thấy có thể là **CDN edge**; cần xem sơ đồ đầy đủ trước khi kết luận request từ trình duyệt đã trực tiếp tới proxy.

### 5.2. Leg ra (upstream / egress)

Capture tại interface nối backend trả lời:

- Proxy có tạo kết nối tới IP/port upstream nào?
- SYN của proxy có được server trả lời?
- Có TLS handshake mới với server không, hay upstream chạy HTTP plaintext?
- Proxy gửi dữ liệu lúc nào, server gửi byte đầu tiên hoặc reset lúc nào?
- Có nhiều kết nối đến các backend khác nhau vì retry, failover hoặc load balancing không?

Ngay cả khi proxy dùng chung một kết nối upstream cho **nhiều request HTTP/1.1 tuần tự**, multiplex HTTP/2 hoặc gRPC, không được lấy một 5-tuple làm định danh duy nhất của request. Nên kết hợp **correlation ID**, **trace ID**, request ID của proxy, upstream address, timestamp và các trường log ứng dụng.

### 5.3. Các hành vi khiến hai leg khác nhau

| Hoạt động của proxy | PCAP ở client side | PCAP ở server side |
| --- | --- | --- |
| **TLS termination** | Ciphertext TLS | Có thể plaintext HTTP hoặc TLS phiên mới |
| **L7 routing/load balancing** | Kết nối đến VIP | Kết nối đến một trong nhiều backend |
| **WAF deny** | Có thể thấy HTTP 403 qua TLS hoặc kết nối bị đóng | Thường không có upstream request liên quan |
| **Cache hit** | Có response | Không bắt buộc có request tới origin |
| **Retry/failover** | Client có thể chỉ có một logical request | Có thể có nhiều upstream attempts |
| **Buffering** | Client gửi nhanh, chờ phản hồi | Proxy có thể gửi/nhận theo thời điểm khác |
| **Request/response rewrite** | Payload sau mã hóa của phía client | HTTP header/body có thể đã biến đổi |
| **Idle timeout** | Client thấy FIN/RST hoặc timeout | Upstream có thể vẫn mở hoặc đã đóng ở thời điểm khác |

Proxy có thể ở trong container hoặc service mesh. Trong hệ thống này, **container network namespace**, **veth**, **overlay tunnel** và sidecar quyết định nơi packet xuất hiện. Bắt trên NIC vật lý của node không có nghĩa chắc chắn thấy toàn bộ inner traffic hoặc traffic trên loopback giữa các process.

## 6. Capture phía server: xác nhận điều backend thực nhận

PCAP ở interface mà server nhận request từ proxy giúp xác nhận **TCP/UDP transport** của chặng upstream:

- SYN tới server hay chỉ xuất hiện trước firewall?
- Server trả SYN-ACK, RST hay không phản hồi?
- Có packet từ proxy chứa dữ liệu ứng dụng hay TLS Application Data không?
- Server đã ACK dữ liệu, tiếp tục gửi response hay đóng kết nối?
- Có retransmission, zero window, reset hoặc ICMP lỗi mạng không?

Nếu upstream sử dụng HTTP plaintext, PCAP có thể nhìn thấy dòng HTTP sau khi đủ packet được thu, nhưng phải tuân thủ giới hạn dữ liệu và quyền truy cập. Nếu upstream sử dụng TLS, PCAP server thường không đọc được HTTP headers/body. Nếu server ứng dụng chạy sau **local sidecar** hoặc **loopback reverse proxy**, capture trên eth0 của host có thể chỉ thấy traffic đã biến đổi; cần biết data path trước khi chọn interface.

**ACK ở mức TCP không đồng nghĩa ứng dụng đã xử lý thành công request.** ACK chỉ xác nhận stack TCP đã nhận các byte theo trạng thái giao thức, không chứng minh business logic đã hoàn tất. Khi server đã nhận request nhưng mất nhiều thời gian mới trả response, dùng application log, thread pool metric, database traces và profiling để xác định nguyên nhân thực tế.

**Nguồn IP server nhìn thấy** thường là IP private của proxy hoặc SNAT address. Một số kiến trúc transparent proxy/DSR giữ lại IP client, và **PROXY protocol** có thể mang địa chỉ gốc ở tầng application/transport metadata nếu hai đầu hỗ trợ. Header **X-Forwarded-For** là dữ liệu HTTP, không phải bằng chứng rằng packet ở server có source IP tương ứng; header này phải được proxy tin cậy chuẩn hóa để tránh spoofing.

## 7. Những yếu tố làm khác nhau giữa ba PCAP

### 7.1. NAT, địa chỉ và port

Client có thể gửi tới VIP **203.0.113.10:443**, proxy kết nối backend **10.30.1.7:8080** từ IP **10.20.1.5**, nên hai capture hoàn toàn khác 5-tuple:

~~~text
Client -> Proxy:
198.51.100.22:51514 -> 203.0.113.10:443   TCP

Proxy -> Server:
10.20.1.5:43218 -> 10.30.1.7:8080          TCP
~~~

Đó là đặc điểm bình thường của reverse proxy L7, không phải dấu hiệu traffic bị "đổi sai đích". Nếu có NAT trung gian, phải kết hợp NAT/conntrack/session log để ánh xạ địa chỉ và port. Với HTTP/2 multiplexing hoặc upstream connection reuse, nhiều request có thể chia sẻ cùng một connection; **không nên cố nối packet một-một theo sequence number giữa hai leg TCP**.

### 7.2. TLS termination và mức nhìn thấy payload

| Chặng | Có thể nhìn thấy trong PCAP thông thường |
| --- | --- |
| Client ↔ proxy với HTTPS/TLS | IP, TCP, packet timing, TLS record metadata; không đọc plaintext HTTP theo mặc định |
| Proxy ↔ server với HTTP | IP, TCP và nội dung HTTP nếu snaplen/điểm quan sát cho phép |
| Proxy ↔ server với HTTPS/mTLS | IP, TCP và TLS metadata, không đọc HTTP plaintext theo mặc định |
| HTTP/3 giữa client và proxy | UDP/QUIC packet metadata; HTTP/3 data được mã hóa và không suy ra như HTTP/1.1 |

TLS 1.3 mã hóa nhiều thông tin handshake sau giai đoạn đầu; ECH có thể che SNI thật. Không nên giả định PCAP luôn đọc được tên miền, đường dẫn hoặc mã lỗi ứng dụng. Muốn chẩn đoán nội dung HTTP, ưu tiên **access log đã chuẩn hóa** hoặc tracing được bật theo quy định; chỉ dùng TLS key log và công cụ giải mã trong môi trường được phép và có biện pháp bảo vệ bí mật phù hợp.

### 7.3. Giao thức và khả năng thay đổi ở proxy

Phía client có thể sử dụng **HTTP/2 qua TLS**, nhưng proxy gọi upstream bằng **HTTP/1.1**, hoặc client dùng **HTTP/3/QUIC** trong khi chặng backend dùng TCP. Vì vậy khác giao thức/port là bình thường khi đã xác định đúng kiến trúc.

Proxy có thể thêm, xóa hoặc viết lại header, nén response, đổi HTTP version, route, buffer và retry. Những thay đổi này làm kích thước và thời điểm packet khác nhau; không được so sánh hai PCAP theo giả định payload/packet length sẽ trùng nhau.

### 7.4. Phân đoạn mạng, VPN và cloud

Traffic có thể đi qua VLAN, overlay VXLAN, IPsec tunnel, policy routing, private link, service mesh và cloud load balancer. Capture **trước tunnel** có thể thấy inner packet; capture **trên outer interface** chỉ thấy encapsulated/encrypted traffic. Một số dịch vụ managed load balancer không cho bắt trực tiếp trên thiết bị; hãy thu tại endpoint hoặc dùng traffic mirroring mà nền tảng hỗ trợ, kết hợp log của dịch vụ.

## 8. Chọn điểm capture theo triệu chứng

| Triệu chứng chính | Điểm nên ưu tiên | Câu hỏi cần kiểm chứng |
| --- | --- | --- |
| Client không kết nối được, không có log ở proxy | Client và ingress proxy; thêm hop giữa nếu cần | SYN có tới proxy và có SYN-ACK quay lại không? |
| Proxy nhận request nhưng upstream timeout | Egress proxy và server; kết hợp ingress proxy | Proxy có gửi SYN/data không? Server có ACK/response? |
| Lỗi 502/connection reset ngắt quãng | Hai leg proxy, server | RST/FIN phát sinh từ endpoint nào, có retry và failover không? |
| HTTP 403 nghi do WAF | Ingress proxy + WAF/security log | Proxy chặn request trước khi forward hay server tự trả 403? |
| Client chờ lâu nhưng backend log nhanh | Ingress và egress proxy, client | Có buffering, network latency hoặc chậm chuyển response không? |
| Server log phản hồi thành công nhưng client thất bại | Server, egress/ingress proxy, client | Response rời server chưa, proxy nhận chưa, client nhận chưa? |
| Lỗi DNS phía người dùng | Client và resolver thích hợp | Có truy vấn/phản hồi DNS liên quan không, DoH/DoT có che nội dung không? |
| Nghi firewall/NAT/VPN làm mất packet | Hai phía ranh giới đang xét | Cùng attempt có đi qua ranh giới không và NAT/tunnel có đúng không? |
| IDS/IPS cảnh báo bất thường | Điểm IDS nhìn thấy flow, endpoint liên quan | Sensor có cả hai chiều, alert có khớp traffic không? |

Nên bắt **tối thiểu hai điểm** khi nghi sự cố nằm giữa chúng; thêm điểm thứ ba khi muốn tách lỗi trong proxy khỏi lỗi ở server. Nếu các log đã giải thích rõ nguyên nhân, không cần thu PCAP chỉ để có thêm tệp.

## 9. Thiết kế một phiên capture ba điểm

### 9.1. Trước khi bắt: xác định câu hỏi và topology

Ví dụ giả thuyết: "Request HTTPS tới proxy nhận 504 vì server **không** gửi response cho kết nối upstream". Cần ghi:

1. Client public/private IP sau NAT; proxy VIP, IP private và backend IP/port thực.
2. Lớp trước proxy (CDN, WAF, VPN, load balancer) và có terminating TLS/NAT ở lớp nào.
3. Thời gian tái hiện, múi giờ, đồng bộ NTP/PTP và **correlation ID/trace ID** nếu có.
4. Giao diện client, ingress/egress proxy và server; xác định container namespace nếu cần.
5. Tiêu chí đủ bằng chứng, dung lượng, snaplen, thời lượng, quyền truy cập, dữ liệu nhạy cảm và retention.

Nếu có nhiều backend, **đừng chỉ lọc một IP server** khi chưa biết upstream được chọn. Có thể bắt theo subnet/backend list hoặc xem access log của proxy để thu hẹp trước.

### 9.2. Ví dụ tcpdump ở client

~~~bash
# Chạy trên client, thay eth0 bằng giao diện thực.
sudo tcpdump -i eth0 -nn -s 192 -c 10000 \
  -w client-https.pcap \
  'host 203.0.113.10 and tcp port 443'
~~~

Capture filter này giữ TCP/443 giữa client và VIP của proxy. Nếu ứng dụng dùng HTTP/3/QUIC, cần quan sát UDP/443 tương ứng, ví dụ filter **host 203.0.113.10 and (tcp port 443 or udp port 443)**. Nếu cần điều tra ICMP hoặc DNS, phải mở rộng filter có chủ đích; filter trên **không** tự thu các gói đó.

### 9.3. Ví dụ tcpdump trên proxy

~~~bash
# Chặng client -> proxy. Giao diện thực tế ví dụ là ens160.
sudo tcpdump -i ens160 -nn -s 192 -c 10000 \
  -w proxy-ingress.pcap \
  'host 198.51.100.22 and tcp port 443'

# Chặng proxy -> backend. Giao diện thực tế ví dụ là ens192.
sudo tcpdump -i ens192 -nn -s 192 -c 10000 \
  -w proxy-egress.pcap \
  'host 10.30.1.7 and tcp port 8080'
~~~

Nếu ingress proxy ở sau CDN thì địa chỉ source sẽ là IP CDN, không nhất thiết là IP client 198.51.100.22. Nếu proxy và server được nối qua overlay hoặc sidecar, phải thay interface và filter theo **địa chỉ thực tế tại điểm bắt**. Trên proxy chỉ có một interface, hai luồng có thể cùng xuất hiện ở đó; cần phân biệt bằng IP/port và đôi khi bằng network namespace.

### 9.4. Ví dụ tcpdump tại server

~~~bash
# Thu đúng luồng từ proxy private IP tới HTTP backend.
sudo tcpdump -i eth0 -nn -s 192 -c 10000 \
  -w server-upstream.pcap \
  'host 10.20.1.5 and tcp port 8080'
~~~

Những lệnh trên cần khởi động **gần đồng thời** trên các máy hoặc dùng thời điểm tái hiện đã thống nhất. Tên file là ví dụ; chọn vị trí lưu có đủ quyền và dung lượng. TCP port trong filter phản ánh chặng cụ thể, **không** phải luôn 443 ở mọi phía. Dùng **-s 192** để hạn chế dữ liệu thu, nhưng snaplen này có thể cắt trường cần xem, đặc biệt khi có encapsulation, extension headers hoặc muốn đọc handshake dài. Khi thực sự cần toàn bộ packet và được phép, có thể đổi sang **-s 0**.

Các tùy chọn chính: **-i** chọn interface, **-nn** không phân giải tên/IP và port khi hiển thị, **-s** giới hạn bytes mỗi packet, **-c** dừng sau số packet nhất định, **-w** ghi tệp PCAP. Khi kiểm tra sự cố ngắt quãng, dùng ring buffer có giới hạn dung lượng thay vì capture không giới hạn:

~~~bash
sudo tcpdump -i eth0 -nn -s 192 \
  -C 25 -W 4 -w server-ring.pcap \
  'tcp port 8080 and host 10.20.1.5'
~~~

Ở tcpdump, **-C 25** xấp xỉ 25 triệu byte/tệp; **-W 4** dùng tối đa bốn tệp xoay vòng trong chế độ này. Cần dừng kịp thời để không ghi đè khoảng sự cố. Ghi thống kê packets captured/received/dropped khi kết thúc, vì thiếu packet có thể do chính công cụ capture.

## 10. Cách đối chiếu PCAP khi không có packet giống hệt nhau

Với reverse proxy L7, cách nối ba điểm **không phải** tìm cùng một TCP sequence number; cần nối **sự kiện** và **request logic** theo nhiều dấu hiệu:

1. **Thời gian:** bắt cùng cửa sổ; thống nhất UTC và kiểm tra clock skew giữa client, proxy, server.
2. **Địa chỉ/port trong từng leg:** dùng 5-tuple để lọc connection trong **mỗi** PCAP, kèm NAT/conntrack mapping nếu có chuyển địa chỉ.
3. **Mốc TCP:** SYN, SYN-ACK, ACK, client data, upstream data, FIN/RST; kiểm tra thứ tự và RTT trong phạm vi mỗi leg.
4. **Mốc application/proxy log:** timestamp nhận request, route, upstream host, thời gian connect/first byte/response, status và retry count.
5. **Correlation ID và trace ID:** nối các log và span giữa client–proxy–server; không kỳ vọng đọc được ID trong PCAP TLS mã hóa.
6. **Số lần thử:** proxy có thể retry upstream nhiều lần cho một request; xem từng upstream attempt riêng.

Một bảng timeline minh họa:

| UTC tương đối | Nguồn quan sát | Bằng chứng | Diễn giải |
| --- | --- | --- | --- |
| +0 ms | Client PCAP | SYN tới 203.0.113.10:443 | Client bắt đầu kết nối |
| +10 ms | Proxy ingress PCAP | SYN từ client | Packet tới interface proxy |
| +13 ms | Proxy ingress PCAP | SYN-ACK | Proxy đáp handshake TCP |
| +70 ms | Proxy access log | Nhận request, correlation ID = C001 | Proxy nhận request logic |
| +75 ms | Proxy egress PCAP | SYN tới 10.30.1.7:8080 | Proxy bắt đầu kết nối upstream |
| +78 ms | Server PCAP | SYN từ 10.20.1.5 | Server quan sát kết nối đến |
| +90 ms | Server PCAP | ACK dữ liệu request | TCP nhận byte; chưa chứng minh xử lý xong |
| +25.100 ms | Server PCAP | Các byte HTTP response đầu tiên | Server bắt đầu gửi response sau thời gian chờ |
| +25.115 ms | Proxy egress PCAP | Nhận response bytes | Proxy nhận response upstream |
| +25.130 ms | Client PCAP | Nhận TLS Application Data | Client thấy dữ liệu phía proxy |

Đây là **timeline giả định** để minh họa phương pháp. Nếu đồng hồ lệch nhau, khoảng thời gian tính từ các máy khác nhau sẽ sai; nên đối chiếu mốc tại cùng host, offset đồng hồ và timestamp của proxy log. Việc log request ở proxy sau TCP handshake cũng không chứng minh app client đã nhận response, trừ khi có bằng chứng ở client.

### 10.1. Lọc và đọc PCAP sau thu thập

~~~bash
# Đọc packet và timestamp từ tệp của client:
tcpdump -nn -tttt -r client-https.pcap

# Trích các cờ TCP, thời gian và địa chỉ để đối chiếu:
tshark -r proxy-egress.pcap \
  -Y 'tcp.flags.syn == 1 || tcp.flags.reset == 1' \
  -T fields \
  -e frame.time_epoch -e ip.src -e tcp.srcport \
  -e ip.dst -e tcp.dstport -e tcp.flags
~~~

Các display filter Wireshark/tshark hay dùng:

| Mục đích | Display filter |
| --- | --- |
| SYN mở kết nối (chưa ACK) | **tcp.flags.syn == 1 && tcp.flags.ack == 0** |
| TCP reset | **tcp.flags.reset == 1** |
| Retransmission được Wireshark suy đoán | **tcp.analysis.retransmission** |
| Một TCP conversation trong một tệp | **tcp.stream == 2** |
| DNS | **dns** |
| TLS handshake | **tls.handshake** |
| QUIC | **quic** |
| ICMP IPv4 hoặc IPv6 | **icmp || icmpv6** |

**tcp.stream** là chỉ số do Wireshark gán trong **tệp đang phân tích**, không ổn định giữa ba PCAP. Cũng cần phân biệt **capture filter libpcap/BPF** (áp dụng lúc ghi) với **display filter Wireshark** (áp dụng lúc xem). Ví dụ **tcp.flags.reset == 1** là display filter, không dùng nguyên dạng đó làm capture filter tcpdump.

### 10.2. Correlation ID hữu ích thế nào?

Giả sử reverse proxy log:

~~~json
{"correlation_id":"C001","client":"198.51.100.22","status":504,"upstream":"10.30.1.7:8080","upstream_connect_ms":4,"upstream_response_ms":30000}
~~~

Log này giúp liên hệ request ứng dụng với upstream IP/port và cửa sổ thời gian, từ đó khoanh vùng đúng flow trong proxy-egress/server PCAP. Nếu hệ thống có OpenTelemetry, có thể dùng **trace_id** nối các span. Tuy nhiên, **correlation ID không mặc nhiên đi qua mọi proxy**; nó phải được cấp và truyền theo chính sách. Khi traffic đã mã hóa, muốn đọc correlation ID từ HTTP header ở bên ngoài TLS cần có phương thức giải mã được cấp quyền; thường nên dùng log hơn.

## 11. Bốn tình huống điều tra thực tế

### Tình huống 1: client timeout, proxy không hề thấy SYN

**Triệu chứng:** client báo không mở được kết nối HTTPS tới proxy.

| Capture | Quan sát | Ý nghĩa |
| --- | --- | --- |
| Client | Nhiều SYN gửi đi; không thấy SYN-ACK | Client đã thử kết nối |
| Proxy ingress | Không thấy SYN ứng với flow/thời gian kiểm tra | Chưa có bằng chứng SYN đến interface proxy |
| Server | Không có upstream traffic liên quan | Phù hợp với tình huống proxy chưa nhận request |

**Hướng điều tra:** xác nhận capture ingress đúng interface/IP và filter, không mất packet; xem firewall, routing, VPN, CDN hoặc NAT **trước proxy**. Nếu có thiết bị trung gian, bắt hai phía ranh giới nghi vấn để xác định hop mất gói. Không kết luận firewall drop chỉ từ việc thiếu SYN ở một tệp.

### Tình huống 2: proxy nhận request, WAF chặn trước upstream

**Triệu chứng:** client nhận **403 Forbidden**.

| Capture hoặc log | Quan sát |
| --- | --- |
| Client PCAP | TLS Application Data phản hồi từ proxy |
| Proxy ingress PCAP | Client kết nối và gửi dữ liệu mã hóa |
| Proxy WAF/access log | Rule từ chối request và ghi HTTP 403 |
| Proxy egress PCAP | Không thấy upstream attempt của request này |
| Server PCAP | Không có packet gắn với request tương ứng |

**Diễn giải:** bằng chứng từ WAF log cộng với sự vắng upstream attempt hỗ trợ kết luận proxy đã chặn trước khi chuyển tiếp. Chỉ riêng PCAP ở client **không đọc được mã HTTP 403** nếu TLS đang mã hóa. Kiểm tra rule/action và correlation ID trước khi sửa chính sách.

### Tình huống 3: proxy gửi upstream request, server chậm trả

**Triệu chứng:** client chờ 30 giây rồi nhận 504.

| Capture hoặc log | Quan sát |
| --- | --- |
| Client PCAP | Handshake hoàn thành, request được gửi; chờ lâu mới có response |
| Proxy ingress PCAP | Có dữ liệu từ client; connection vẫn mở khi chờ |
| Proxy egress PCAP | SYN/ACK và dữ liệu tới backend; không thấy response bytes trước timeout |
| Server PCAP | TCP ACK dữ liệu vào; chưa phát response bytes trong khoảng chờ |
| Application log | Request vào controller; truy vấn DB hoặc downstream bị treo |

**Diễn giải:** hai PCAP upstream cho thấy **network transport đã giao packet đến TCP stack server**; khoảng chờ tiếp theo nhiều khả năng nằm trong xử lý ứng dụng hoặc phụ thuộc của nó, nhưng cần log/trace để xác định. TCP ACK không đồng nghĩa controller đã xử lý xong. Khi proxy hết timeout, nó có thể trả 504 về client trong lúc server vẫn tiếp tục xử lý; cần xem điều gì xảy ra sau đó và cách request bị hủy.

### Tình huống 4: server gửi response nhưng client vẫn timeout

Server PCAP ghi response bytes đã được phát; proxy egress PCAP nhìn thấy bytes vào, nhưng client không nhận response. Hãy đối chiếu **proxy ingress** xem có response bytes gửi về client không; nếu có, tiếp tục kiểm tra ranh giới proxy–client, đường về, MTU, NAT, reset và capture loss. Nếu proxy nhận upstream response nhưng không gửi xuống client, hãy xem buffering, WAF/response filtering, downstream connection state, cấu hình timeout và log proxy. Không quy trách nhiệm cho server chỉ vì client nhìn thấy timeout.

## 12. Những sai lầm phổ biến khi so sánh ba điểm

| Sai lầm | Vì sao sai | Cách kiểm chứng |
| --- | --- | --- |
| Tìm cùng TCP sequence ở client và server | Reverse proxy L7 tạo phiên TCP mới | Ghép bằng thời gian, access log, upstream address, correlation ID/trace ID |
| Cho rằng server thấy IP client | Proxy có thể SNAT/terminate kết nối | Kiểm tra 5-tuple tại từng leg và NAT/conntrack log |
| Không có upstream packet = packet loss | Cache hit, WAF block, lỗi route, không tạo attempt hoặc filter sai đều có thể xảy ra | Đọc proxy access/WAF/upstream log và xác nhận điểm capture |
| TCP ACK = ứng dụng đã xử lý | ACK thuộc TCP stack, không biểu thị kết quả business logic | Dùng application log, span, event timeline |
| Response xuất hiện tại server = client đã nhận | Packet còn phải qua proxy và đường về | Đối chiếu proxy-egress, proxy-ingress và client |
| So sánh timestamp của ba máy như đồng hồ tuyệt đối | Có clock skew hoặc timestamp bị trễ | Đồng bộ NTP/PTP, ước lượng lệch giờ, dùng mốc cùng máy |
| Wireshark gắn retransmission = chắc chắn mạng bị mất gói | Capture thiếu packet, offloading hoặc asymmetric path có thể làm heuristic sai | Kiểm tra sequence/ACK, capture drop, offload, điểm bắt thứ hai |
| Không thấy payload = không có request | TLS/QUIC mã hóa và có thể proxy buffer | Dựa vào packet metadata, handshake, log và traces |
| Dùng cùng TCP/443 filter cho cả ba máy | Upstream có thể HTTP/8080, gRPC/mTLS, UDP/QUIC | Lập sơ đồ protocol/port cho từng chặng |
| Bắt interface host là đã thấy hết traffic pod | Container veth, CNI, overlay, loopback, mesh có thể đổi đường đi | Chọn namespace/interface đúng data path |
| Dùng một IP backend cố định | Load balancer có retry, failover hoặc chọn nhiều endpoint | Xem log upstream hoặc thu đủ backend trong phạm vi cho phép |
| Chỉ dựa vào SYN/SYN-ACK | Với HTTP/2 keepalive có thể không có handshake mới cho mỗi request | Kiểm tra connection reuse, HTTP stream và proxy log |

**Rủi ro riêng của host capture:** checksum offload khiến Wireshark báo "bad checksum" giả; GSO/TSO/GRO/LRO làm packet size hoặc segmentation khác trên dây. **Rủi ro riêng của SPAN:** mirror chỉ một hướng hoặc bị quá tải gây thiếu packet. **Rủi ro của cloud:** traffic mirror có giới hạn dịch vụ/điểm nguồn hoặc thay đổi encapsulation. Kết luận phải ghi rõ đã kiểm tra những yếu tố nào.

## 13. Thu thập, quản lý và bảo vệ PCAP

PCAP có thể chứa credential, cookie, token, payload HTTP plaintext, địa chỉ mạng nội bộ và metadata nhạy cảm. Tại proxy termination hoặc backend không dùng TLS, nguy cơ lộ dữ liệu ứng dụng cao hơn. Một kế hoạch đúng cần:

1. **Phạm vi và quyền:** chỉ capture trên hệ thống/interface được phép; xác định mục tiêu và nhóm được xem tệp.
2. **Giảm thiểu dữ liệu:** dùng capture filter phù hợp, giới hạn packet/time/dung lượng; chọn snaplen đủ cho câu hỏi. Nếu phải đọc payload thì thu theo quy trình được phép.
3. **Độ tin cậy bằng chứng:** ghi hostname, interface, network namespace, IP, filter, snaplen, phiên bản công cụ, thời gian UTC, clock offset và thống kê packet drop.
4. **Lưu trữ:** phân quyền hạn chế, mã hóa phù hợp, truyền an toàn; retention và tiêu hủy theo chính sách.
5. **Tính toàn vẹn:** lưu checksum SHA-256 của từng tệp cùng biên bản điều tra, ví dụ:

~~~bash
sha256sum client-https.pcap proxy-ingress.pcap proxy-egress.pcap server-upstream.pcap
~~~

Hash giúp phát hiện thay đổi sau thời điểm ghi nhận, **không** tự chứng minh capture đã đúng interface hoặc đủ packet. Trước khi chia sẻ cho nhà cung cấp, cần rà soát nội dung, ẩn hoặc loại bỏ dữ liệu nhạy cảm theo chính sách và phân biệt rõ bản đã xử lý với bản gốc.

Đối với dữ liệu có giá trị pháp lý hoặc điều tra an ninh chuyên sâu, cần tuân theo quy trình lưu giữ/chuyển giao bằng chứng của tổ chức; việc thu và giải mã nội dung chỉ nên thực hiện trong giới hạn quyền hạn được cấp.

## 14. Bài thực hành: phân tích chậm giữa proxy và server

**Bối cảnh:** nhóm vận hành thấy tỷ lệ HTTP 504 tăng trên endpoint API. Application log server không ghi rõ nguyên nhân. Cần phân biệt lỗi đường truyền, proxy timeout và ứng dụng chậm.

### Bước 1. Xác định dữ kiện trước capture

Ghi IP nguồn/đích và các lớp trung gian theo sơ đồ thực tế; xác nhận chặng client–proxy là TLS/443, chặng proxy–server là HTTP/8080. Đồng bộ đồng hồ, bật/đọc access log proxy có request ID, upstream address và upstream timing. Đặt giả thuyết: "Sau khi proxy gửi request, server nhận đủ bytes nhưng không phản hồi trong thời hạn".

### Bước 2. Thu đồng thời

Thu capture client, ingress proxy, egress proxy và server với filter riêng từng leg như mục 9. Bắt đầu trước khi tái hiện, ghi giờ xảy ra lỗi và correlation ID, dừng khi đủ dữ liệu. Kiểm tra thống kê dropped packets; nếu bị mất nhiều packet, capture chưa đáng tin để kết luận chính xác.

### Bước 3. Điền bảng quan sát

| Kiểm tra | Kết quả cần ghi |
| --- | --- |
| Client SYN có đến ingress proxy? | Có/Không/Chưa đủ dữ liệu |
| Proxy có gửi SYN upstream? | Có/Không/Chưa đủ dữ liệu |
| Server có nhận SYN và dữ liệu request? | Có/Không/Chưa đủ dữ liệu |
| Có TCP retransmission hoặc RST trong leg nào? | Leg, thời điểm, seq/ack, capture loss |
| Server phát response bytes trước khi timeout? | Có/Không/Chưa đủ dữ liệu |
| Proxy gửi response nào về client? | Mốc thời gian/bytes và HTTP status từ log |
| Correlation ID, route và upstream attempt khớp? | Mã, backend, attempt và log liên quan |

### Bước 4. Kết luận có điều kiện

- **Có request tại server, TCP ổn, không có response:** điều tra application log, phụ thuộc và deadline server.
- **Proxy gửi SYN nhưng server không nhận, capture đáng tin:** tiếp tục kiểm tra firewall/NAT/route trên đoạn proxy–server.
- **Server gửi response, proxy không nhận:** kiểm tra đường về, firewall state, routing, TCP retransmission.
- **Proxy nhận response nhưng client không nhận:** kiểm tra downstream leg, proxy buffering và client network.
- **Không có upstream request nhưng proxy ghi WAF deny/cache hit:** xử lý chính sách WAF hoặc cache; không mặc định quy lỗi cho backend.

Hãy ghi kết luận như một mệnh đề **có bằng chứng và giới hạn**, ví dụ: "Trong cửa sổ 14:03:00–14:03:45 UTC, server PCAP xác nhận request bytes từ proxy đã được ACK, nhưng không quan sát thấy response bytes trước khi proxy ghi upstream timeout; không ghi nhận capture drop tại hai điểm. Cần kiểm tra xử lý ứng dụng để xác định nguyên nhân chậm." Điều này chính xác hơn khẳng định "mạng chắc chắn không lỗi".

## 15. Checklist áp dụng trong vận hành

- [ ] Đã phân biệt reverse proxy L7, L4 load balancer, CDN/WAF và các điểm NAT/TLS termination.
- [ ] Đã vẽ rõ **client → proxy ingress → proxy egress → server** cùng IP, port và interface tại mỗi điểm.
- [ ] Đã xác định câu hỏi ở mức packet mà log/metric/flow chưa trả lời đủ.
- [ ] Capture đúng thời gian, cả hai chiều nếu cần và đúng giao thức (TCP, UDP/QUIC, DNS, ICMP).
- [ ] Có giới hạn phạm vi, snaplen, dung lượng, quyền truy cập và retention.
- [ ] Đã kiểm tra packet drop, offloading, SPAN/mirror, clock skew và container/network namespace.
- [ ] Đã đối chiếu 5-tuple riêng từng leg với access log, NAT/session log, correlation ID, upstream attempts và trace.
- [ ] Phân biệt bằng chứng quan sát được với giả thuyết; không suy diễn từ một tệp thiếu packet.
- [ ] Đã ghi nhận thời gian, filter, vị trí, kết quả kiểm chứng và giới hạn của kết luận.

**Điểm cốt lõi:** capture ở client cho biết những gì client gửi và nhận; capture ở proxy kết nối hai góc nhìn nhưng thường gồm **hai phiên mạng khác nhau**; capture ở server cho biết điều backend thật sự nhận và phát ra ở mức packet. Khi so sánh đủ ba điểm, phối hợp timestamp, log proxy, NAT mapping và correlation ID, kỹ sư có thể thu hẹp đoạn xảy ra sự cố và xác minh tác động của firewall, WAF, VPN hay kiến trúc mạng mà không nhầm lẫn tín hiệu packet với kết quả xử lý ứng dụng.
