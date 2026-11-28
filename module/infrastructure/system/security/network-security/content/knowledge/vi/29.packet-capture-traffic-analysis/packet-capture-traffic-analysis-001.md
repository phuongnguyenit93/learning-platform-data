# Khi nào cần packet capture?

## 1. Packet capture giải quyết câu hỏi gì?

**Packet capture** (bắt gói tin, thường viết **PCAP**) là quá trình ghi lại các gói mạng quan sát được tại một giao diện, một điểm mirror/SPAN hoặc một cảm biến chuyên dụng trong một khoảng thời gian. Kết quả thường được lưu thành tệp **.pcap** hoặc **.pcapng** để phân tích bằng Wireshark, tcpdump, tshark và các công cụ phù hợp.

Trong phạm vi **Packet capture và phân tích lưu lượng** của mô-đun **SECURITY_NETWORK_SECURITY**, PCAP là công cụ cung cấp bằng chứng ở mức gói tin khi cần kiểm tra cách các cơ chế phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, kết nối không dây hoặc hạ tầng đám mây thực sự hoạt động. Ví dụ, access log của ứng dụng có thể ghi "upstream timeout"; PCAP giúp xem client có gửi SYN hay không, server có trả SYN-ACK hay không, có gói retransmission, TCP reset hoặc phản hồi DNS bất thường hay không.

Tuy nhiên, **PCAP không phải bước mặc định cho mọi sự cố mạng**. Nó tốn tài nguyên lưu trữ, có thể chứa thông tin nhạy cảm, và chỉ thấy lưu lượng tại điểm được đặt cảm biến. Nên sử dụng PCAP khi có **một câu hỏi cụ thể mà log, metric hoặc flow telemetry chưa trả lời đủ**, đồng thời có thể bắt được đúng lưu lượng trong khung thời gian cần thiết.

Sau bài này, người học có thể:

- Nhận biết tình huống cần bằng chứng ở mức packet và tình huống chỉ cần log, metric hoặc flow.
- Chọn vị trí, thời điểm, giao diện, hướng lưu lượng và bộ lọc bắt gói phù hợp.
- Xác định các giới hạn của PCAP do TLS, NAT, VPN, offloading, sampling và vị trí quan sát.
- Thu thập lượng dữ liệu vừa đủ, bảo vệ thông tin nhạy cảm và duy trì chất lượng bằng chứng.
- Giải thích kết quả theo thời gian, kết hợp PCAP với firewall log, IDS/IPS, DNS log và distributed tracing.

## 2. So sánh PCAP với các nguồn telemetry khác

Các nguồn dữ liệu quan sát mạng có độ chi tiết, chi phí và câu hỏi trả lời khác nhau:

| Nguồn dữ liệu | Thường trả lời tốt | Giới hạn thường gặp |
| --- | --- | --- |
| **Metric** (latency, error rate, packet drop, CPU, băng thông) | Có sự cố lúc nào, mức độ ảnh hưởng ra sao? | Không cho thấy từng gói, cờ TCP hay trường giao thức cụ thể |
| **Application/access log** | Request nào lỗi, route và HTTP status nào liên quan? | Có thể không nhìn thấy request bị chặn hoặc lỗi trước ứng dụng |
| **Firewall/WAF/IDS/IPS log** | Rule hoặc chữ ký nào match, quyết định allow/drop/alert là gì? | Phụ thuộc độ đầy đủ log; có thể thiếu chuỗi packet để xác định nguyên nhân |
| **Flow telemetry** (NetFlow/IPFIX, VPC Flow Logs tùy nền tảng) | Ai giao tiếp với ai, cổng nào, bao nhiêu byte/gói? | Metadata tổng hợp, không tái hiện đầy đủ sequence hay nội dung packet |
| **Distributed trace** | Yêu cầu đi qua dịch vụ nào, span nào chậm? | Chủ yếu phản ánh các dịch vụ đã instrument; không thay thế quan sát TCP/IP |
| **PCAP** | Trên dây tại điểm quan sát đã thấy packet gì, thứ tự, cờ và trường giao thức nào? | Không tự giải thích nguyên nhân; có thể thiếu packet hoặc không giải mã được nội dung mã hóa |

Ví dụ: một dashboard hiển thị tỷ lệ lỗi kết nối tăng đột ngột, log firewall không có dòng deny rõ ràng và traceroute chưa xác định được điểm hỏng. Lúc này bắt gói ở **hai phía của firewall** có thể phân biệt: gói chưa tới firewall, gói tới nhưng không đi qua, hay gói đi qua nhưng upstream không phản hồi.

Một PCAP đơn lẻ **không chứng minh tuyệt đối** rằng gói "không tồn tại trên mạng". Nó chỉ cho biết gói có hoặc không xuất hiện tại **vị trí và thời điểm bắt**, với độ tin cậy phụ thuộc chất lượng cảm biến và mức mất gói của công cụ.

## 3. Khi nào nên bật packet capture?

### 3.1. Nghi ngờ lỗi ở lớp mạng hoặc vận chuyển

PCAP đặc biệt hữu ích khi cần xác nhận các hiện tượng thuộc TCP, UDP, ICMP, IP hoặc lớp liên kết:

- **Kết nối TCP không thiết lập được:** xem SYN, SYN-ACK, ACK, RST và hướng đi của từng gói.
- **Timeout, retransmission, reset:** xem retransmission, duplicate ACK, zero window, RST, thời điểm ngắt kết nối hoặc lưu lượng đi một chiều.
- **Mất kết nối ngắt quãng:** so sánh đường đi và trạng thái kết nối ở thời điểm lỗi với thời điểm bình thường.
- **Sự cố MTU / Path MTU Discovery:** kiểm tra kích thước gói, cờ Don't Fragment ở IPv4, phản hồi ICMP cần thiết và dấu hiệu packet lớn bị chặn.
- **Bất đối xứng đường đi:** kiểm tra hướng gửi/nhận tại nhiều hop; một cảm biến đơn lẻ có thể chỉ nhìn thấy một chiều.
- **ARP hoặc IPv6 Neighbor Discovery:** phát hiện vấn đề phân giải địa chỉ lớp 2/khả năng tới next hop trong cùng segment.

Ví dụ, log ứng dụng chỉ báo "connection timed out" trong khi client liên tục gửi SYN. PCAP tại client xác nhận client gửi SYN nhưng **chưa xác nhận** SYN đã đến server. Muốn quy trách nhiệm cho network path hoặc firewall phải đối chiếu PCAP, counter và log tại các điểm tiếp theo.

### 3.2. Nghi ngờ DNS hoặc handshake giao thức có vấn đề

Nên bắt gói khi cần xem điều thực sự được gửi/nhận:

- Truy vấn DNS không có phản hồi; phản hồi chậm, RCODE bất thường, truy vấn bị lặp hoặc trả về địa chỉ ngoài dự kiến.
- TCP/UDP 53 bị chặn, chuyển từ UDP sang TCP không thành công, hoặc gói DNS bị fragmentation/truncation.
- TLS handshake bị ngắt, kết nối bị reset trước khi lên ứng dụng, hoặc hai bên thương lượng protocol/version không như mong đợi.
- DHCP không cấp địa chỉ, thông điệp Discover/Offer/Request/Ack không đi qua đúng segment.

Cần biết **DNS-over-HTTPS (DoH)** và **DNS-over-TLS (DoT)** mã hóa nội dung DNS; PCAP bên ngoài kết nối chỉ thấy một phần metadata. Tương tự, HTTPS/TLS 1.3 không cho phép đọc HTTP body hoặc các trường handshake đã được mã hóa nếu không có dữ liệu giải mã được phép và công cụ phù hợp.

### 3.3. Xác minh chính sách mạng và an ninh

PCAP có giá trị khi kiểm tra một chính sách **có tác động thực tế lên packet** hay chưa:

- **Phân đoạn mạng:** từ VLAN/subnet A tới subnet B có lưu lượng vượt qua ranh giới không; có response trở lại không.
- **Firewall và ACL:** SYN bị drop hay được forward; rule log có khớp hành vi packet ở cả phía trước và sau thiết bị không.
- **NAT:** địa chỉ/port nguồn hoặc đích thay đổi ra sao; có thiếu ánh xạ làm phản hồi không quay lại đúng endpoint không.
- **VPN và tunnel:** tunnel outer có lưu lượng nhưng inner không tới đích; MTU của tunnel có gây nghẽn; packet được quan sát trước hay sau đóng gói.
- **IDS/IPS:** cảnh báo có tương ứng với luồng packet thực tế hay không; sensor có nhìn đủ hai chiều để phân tích chính xác không.
- **Giám sát DNS hoặc traffic bất thường:** một host phát sinh mẫu truy vấn hoặc kết nối khác thường; cần đối chiếu packet với log endpoint, DNS server và IDS.

Chỉ thu thập trên hệ thống, phân đoạn và kết nối mà người vận hành được phép giám sát. Khi đánh giá cảnh báo bảo mật, PCAP là bằng chứng kỹ thuật hỗ trợ phân tích; hành vi bất thường trong packet **không tự động khẳng định có tấn công thành công**.

### 3.4. Tái hiện lỗi khó xuất hiện và kiểm chứng sửa lỗi

Khi một sự cố chỉ xuất hiện trong thời gian ngắn, có thể cấu hình **capture vòng (ring buffer)** với giới hạn dung lượng và tự động thu đúng thời điểm xảy ra lỗi. Nên lập sẵn tiêu chí kích hoạt, chẳng hạn "ngay khi kết nối từ subnet đối tác sang API tăng timeout" hoặc "khi số lần TCP reset tăng trong đợt triển khai".

PCAP cũng hữu ích trước và sau khi thay đổi firewall, route, VPN, load balancer hoặc cấu hình DNS. Muốn so sánh có ý nghĩa, cần giữ điều kiện kiểm thử nhất quán: cùng client, destination, route, kích thước gói và các tác nhân có thể ảnh hưởng.

## 4. Khi nào chưa cần hoặc không nên bắt gói?

Trước khi thu PCAP, hãy kiểm tra liệu vấn đề đã đủ rõ ở lớp cao hơn chưa:

| Tình huống | Hướng xử lý hợp lý trước | Khi nào nâng lên PCAP? |
| --- | --- | --- |
| HTTP 401/403 do ứng dụng báo rõ lỗi quyền | Authentication log, authorization policy, trace | Khi nghi gateway/WAF/proxy thay đổi hoặc chặn request bất thường |
| Database trả lỗi SQL cụ thể | Query log, schema, connection pool metric | Khi log cho thấy timeout mạng/transport khó giải thích |
| CPU/memory cao trên service | Host metric, profiler, workload log | Khi cần xác minh lượng packet đến bất thường hoặc hiện tượng retransmission đi kèm |
| Firewall log ghi rule deny đúng ý định | Kiểm tra chính sách và rule order | Khi packet dường như không khớp với log/counter hoặc bị chặn ở vị trí khác |
| Flow log xác nhận lưu lượng bình thường | Metric, log phía ứng dụng | Khi cần biết lý do phiên thất bại ở mức handshake hoặc các packet cụ thể |
| Cần thống kê tổng lưu lượng nhiều ngày | Flow telemetry, counters, sampled metrics | Khi cần kiểm chứng một mẫu protocol cụ thể mà telemetry thiếu |
| Traffic có dữ liệu nhạy cảm mà chưa có quyền thu | Xin quyền và xác định cách giảm dữ liệu | Chỉ capture sau khi đáp ứng quy định bảo vệ dữ liệu |

Một dấu hiệu cho thấy **câu hỏi điều tra còn quá rộng** là yêu cầu "bắt toàn bộ traffic trên tất cả server để xem có gì lạ". Trước tiên cần khoanh vùng bằng dashboard, SIEM, firewall log, endpoint telemetry, route, thời gian và địa chỉ có liên quan; sau đó mới chọn PCAP đúng đích.

## 5. Cây quyết định: có nên dùng PCAP?

~~~mermaid
flowchart TD
    A[Phát hiện lỗi hoặc hành vi bất thường] --> B{Log, metric và flow đã trả lời nguyên nhân?}
    B -->|Có| C[Khắc phục và theo dõi bằng telemetry hiện có]
    B -->|Chưa| D{Có câu hỏi cụ thể cần nhìn ở mức packet?}
    D -->|Không| E[Thu hẹp thời gian, nguồn, đích và giả thuyết]
    E --> D
    D -->|Có| F{Có quyền thu và điểm đặt cảm biến phù hợp?}
    F -->|Không| G[Xử lý quyền, vị trí quan sát hoặc chọn nguồn dữ liệu khác]
    F -->|Có| H[Thiết kế bộ lọc, thời lượng, kích thước và bảo vệ dữ liệu]
    H --> I[Bắt gói trong lúc tái hiện sự cố]
    I --> J[Kiểm tra packet drop và đối chiếu log, trace, thời gian]
    J --> K{Bằng chứng đã đủ?}
    K -->|Chưa| L[Điều chỉnh giả thuyết hoặc điểm capture]
    L --> H
    K -->|Đủ| M[Kết luận có giới hạn và lưu bằng chứng theo chính sách]
~~~

Ba điều kiện nên đồng thời có trước khi bật PCAP:

1. **Câu hỏi điều tra có thể kiểm chứng**, ví dụ: "TCP SYN từ client A có đến phía trong firewall B không?".
2. **Điểm quan sát nhìn thấy lưu lượng liên quan**, bao gồm đúng giao diện, đúng hướng và cả hai chiều nếu cần.
3. **Phạm vi thu đủ hẹp và hợp lệ** để vận hành an toàn: đúng thời gian, host, protocol, dung lượng, quyền truy cập và retention.

Nếu thiếu một trong ba điều kiện, có thể capture ra hàng gigabyte nhưng vẫn không trả lời được câu hỏi.

## 6. Chọn vị trí bắt gói theo vấn đề

Một request có thể đi qua nhiều thành phần:

~~~text
Client ── LAN/Wi-Fi ── Firewall/NAT ── VPN/Internet ── Edge/WAF
                                                       │
                                                 Load Balancer
                                                       │
                                                Reverse Proxy
                                                       │
                                                 Application
~~~

| Vị trí | Thấy được | Điều không nên suy diễn |
| --- | --- | --- |
| **Máy client** | Packet đi/đến network stack của client | Packet có chắc đến được server hay không |
| **Máy server** | Packet mà host quan sát qua interface đang bắt | Mọi packet đã đi qua upstream firewall |
| **Hai phía firewall/NAT** | Thay đổi IP/port, packet forward/drop, lỗi đường phản hồi | Mọi quyết định nội bộ của thiết bị nếu không có log/counter |
| **SPAN/TAP trên switch** | Bản sao frame từ cổng/VLAN được cấu hình mirror | Mọi traffic mạng nếu mirror thiếu cổng/VLAN hoặc quá tải |
| **Bên ngoài VPN** | Outer tunnel, peer, port, kích thước và nhịp traffic | Nội dung inner packet được mã hóa |
| **Bên trong VPN, tại endpoint giải mã** | Inner IP/protocol sau xử lý tunnel, nếu có interface phù hợp | Toàn bộ traffic khác không đi qua endpoint |
| **Cloud traffic mirror** | Traffic tại nguồn mirror mà nền tảng hỗ trợ | Lưu lượng của các endpoint hay dịch vụ không thuộc phạm vi mirror |
| **IDS sensor** | Packet mà sensor thực tế nhận được | Sensor chắc chắn thấy cả chiều request và response |

**Nguyên tắc hai điểm quan sát:** khi nghi packet bị mất/biến đổi giữa hai thiết bị, bắt gần như đồng thời **trước và sau** đoạn nghi vấn. Ví dụ, client gửi SYN nhưng server không thấy, hãy tiến dần qua các hop để tìm đoạn cuối cùng có SYN và đoạn đầu tiên không còn thấy. Đồng bộ giờ giữa các máy là điều kiện quan trọng để đối chiếu.

Trong Kubernetes hoặc service mesh, hãy xác định đang quan sát **pod veth, node interface, ingress, sidecar hay overlay network**. Nhiều lớp encapsulation, proxy nội bộ và NAT có thể làm địa chỉ/port khác với dữ liệu ứng dụng. Trong cloud, lưu lượng mirror có thể bị hạn chế bởi loại interface, topology hoặc dịch vụ; cần kiểm tra chính xác khả năng của nền tảng trước khi dựa vào PCAP.

## 7. Xác định phạm vi capture trước khi thực hiện

Ghi lại một mẫu kế hoạch nhỏ, ví dụ:

| Hạng mục | Ví dụ trong một sự cố timeout API |
| --- | --- |
| Câu hỏi | SYN-ACK từ API có trở lại client không? |
| Nguồn / đích | Client 10.10.10.25, VIP API 10.20.30.40 |
| Giao thức | TCP/443; có thể kèm DNS nếu chưa xác định được địa chỉ |
| Điểm bắt | Client và server/VIP ingress, có thể thêm hai phía firewall |
| Thời gian | Bắt đầu vài giây trước khi tái hiện, dừng ngay sau lỗi |
| Mức dữ liệu | Ưu tiên header trước; nâng lên toàn packet nếu cần và được phép |
| Dự kiến điều tra | SYN, SYN-ACK, ACK, RST, retransmission, timestamp, hướng traffic |
| Giới hạn | Dung lượng, số gói, retention, nhóm được phép đọc tệp |

Cần tách ba loại lọc:

- **Capture filter:** áp dụng ngay trong lúc bắt để quyết định packet nào được ghi, thường dùng cú pháp **libpcap/BPF** như `host 10.20.30.40 and tcp port 443`.
- **Display filter:** áp dụng sau khi đã có tệp trong Wireshark/tshark; dùng cú pháp riêng như `tcp.flags.syn == 1 && tcp.flags.ack == 0`.
- **Log/query filter:** áp dụng với dữ liệu log hoặc flow, cú pháp tùy hệ thống. Không dùng nhầm cú pháp này cho tcpdump.

Lọc quá hẹp có thể làm mất gói phản hồi, DNS đi trước kết nối, ICMP báo lỗi MTU, ARP/ND hoặc luồng NAT khác địa chỉ. Khi câu hỏi liên quan đến đường đi và phân giải kết nối, hãy chọn filter đủ rộng để giữ **bằng chứng quyết định**, sau đó dùng display filter để thu hẹp lúc phân tích.

## 8. Bắt gói tối thiểu với tcpdump và phân tích bằng Wireshark

Các lệnh sau minh họa trên Linux với traffic **được phép giám sát**. Tên giao diện và địa chỉ chỉ là ví dụ, phải thay bằng thông số thực tế.

### 8.1. Xác định giao diện cần dùng

~~~bash
sudo tcpdump -D
~~~

Không nên chọn `any` theo thói quen: trên Linux, giao diện pseudo **any** có thể phù hợp để quan sát tổng quan nhưng không cung cấp đầy đủ thông tin link layer giống capture tại một NIC cụ thể. Nếu cần kiểm chứng VLAN tag hoặc frame Ethernet, nên chọn đúng interface hỗ trợ thông tin đó.

### 8.2. Capture giới hạn số packet

~~~bash
sudo tcpdump -i eth0 -nn -s 160 -c 5000 \
  -w api-timeout.pcap \
  'host 10.20.30.40 and tcp port 443'
~~~

Giải thích:

- `-i eth0`: chọn giao diện thực tế.
- `-nn`: không phân giải tên DNS/service port, giúp đầu ra ổn định và giảm truy vấn phụ.
- `-s 160`: chỉ lưu tối đa 160 byte đầu của mỗi packet; có thể đủ cho một số phân tích header, **không bảo đảm** đủ với IPv6 extensions, VLAN, encapsulation hoặc TLS ClientHello dài.
- `-c 5000`: dừng khi đã nhận 5.000 packet, tránh chạy vô hạn; nếu sự cố không xuất hiện trước khi chạm ngưỡng, cần thiết kế lại khoảng thu.
- `-w`: ghi dữ liệu packet vào tệp thay vì in text ra console.
- Biểu thức trong dấu nháy là **capture filter BPF**.

Khi cần kiểm tra đủ handshake, các phần mở rộng và payload mà chính sách cho phép, có thể dùng `-s 0` để thu toàn bộ packet được công cụ cung cấp. **Không tự động dùng full capture** nếu chỉ cần header hoặc flow; lượng dữ liệu nhạy cảm và chi phí lưu trữ sẽ tăng.

### 8.3. Ring buffer cho lỗi ngắt quãng

~~~bash
sudo tcpdump -i eth0 -nn -s 160 \
  -C 20 -W 5 -w api-ring.pcap \
  'host 10.20.30.40 and tcp port 443'
~~~

Với cách đặt `-C 20 -W 5`, tcpdump xoay vòng các tệp khi gần đạt **20 triệu byte/tệp**, giữ tối đa **5 tệp** luân phiên (xấp xỉ 100 MB dữ liệu PCAP, cộng sai khác thực tế). Đây là **giới hạn theo dung lượng**, không phải thời gian; cần dừng capture theo quy trình vận hành và lưu bản sao bằng chứng ngay khi sự cố xảy ra trước khi các vòng sau ghi đè. Đảm bảo dung lượng còn trống và cấu hình phân quyền cho nơi lưu file.

### 8.4. Đọc lại và lọc sau capture

~~~bash
tcpdump -nn -r api-timeout.pcap

# Ví dụ: chỉ hiển thị các SYN chưa kèm ACK:
tshark -r api-timeout.pcap \
  -Y 'tcp.flags.syn == 1 && tcp.flags.ack == 0' \
  -T fields -e frame.time_relative -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e tcp.stream
~~~

Trong Wireshark, có thể dùng các display filter:

| Mục đích | Display filter |
| --- | --- |
| Tìm SYN đầu tiên | `tcp.flags.syn == 1 && tcp.flags.ack == 0` |
| Tìm reset TCP | `tcp.flags.reset == 1` |
| Tìm packet bị Wireshark đánh dấu retransmission | `tcp.analysis.retransmission` |
| Lọc một TCP stream **trong tệp đang mở** | `tcp.stream == 3` |
| Truy vấn DNS | `dns` |
| Chỉ các phản hồi DNS có RCODE khác NOERROR | `dns.flags.response == 1 && dns.flags.rcode != 0` |
| Handshake TLS có thể giải mã phần metadata | `tls.handshake` |
| ICMP IPv4 | `icmp` |
| ICMPv6 | `icmpv6` |

Chỉ số `tcp.stream` do Wireshark/tshark gán theo **từng tệp phân tích**, không phải mã định danh cố định xuyên mọi điểm bắt. Khi ghép PCAP ở hai thiết bị, nên đối chiếu 5-tuple (IP nguồn/đích, port nguồn/đích, protocol), sequence/ack và thời gian; với NAT, cần log dịch địa chỉ/port.

## 9. Những mẫu dấu hiệu cho thấy PCAP hữu ích

### Tình huống A: TCP kết nối tới API bị timeout

Giả sử ứng dụng client không kết nối được `10.20.30.40:443`.

~~~text
Client capture
12:00:00.000  Client -> API  SYN
12:00:01.020  Client -> API  SYN (retransmission)
12:00:03.060  Client -> API  SYN (retransmission)
                 (không quan sát thấy SYN-ACK)
~~~

**Bằng chứng:** client đã cố gửi SYN và trong tệp bắt tại client không có SYN-ACK. **Chưa đủ bằng chứng** để kết luận firewall drop. Cần xem ingress/router/firewall/server: nếu server không thấy SYN, nghi đoạn đường trước server; nếu server thấy SYN và đã gửi SYN-ACK nhưng client không nhận, nghi đường về hoặc NAT/stateful firewall; nếu server chủ động RST, xem lại dịch vụ, ACL và chính sách máy chủ.

### Tình huống B: DNS thỉnh thoảng trả kết quả chậm

~~~text
10:15:00.000  Client -> Resolver  DNS query example.internal A
10:15:02.001  Client -> Resolver  DNS query example.internal A (lặp)
10:15:02.015  Resolver -> Client  DNS response
~~~

Trong mẫu này, có truy vấn lặp và phản hồi muộn. Để tìm nguyên nhân, cần đối chiếu resolver log, tốc độ phản hồi ở phía server, cache, packet loss, firewall và ứng dụng gửi DNS. **Truy vấn lặp không tự chứng minh resolver bị lỗi**: client có thể gửi lại do timeout hoặc ứng dụng tự phát nhiều truy vấn.

### Tình huống C: MTU sau khi bật VPN

Một kết nối TCP nhỏ vẫn hoạt động nhưng upload lớn chậm hoặc treo. Kiểm tra kích thước packet, TCP retransmission, gói ICMP IPv4 type 3 code 4 ("Fragmentation Needed") hoặc ICMPv6 Packet Too Big; kiểm tra MTU tunnel và các chính sách firewall cho ICMP cần thiết. Nếu không thấy ICMP ở điểm bắt, đó có thể là do capture không đúng chỗ, filter thiếu hoặc đường mạng thật sự đang chặn; cần thêm bằng chứng.

### Tình huống D: IDS báo luồng quét hoặc kết nối bất thường

PCAP tại sensor giúp kiểm tra TCP flags, số lượng kết nối, mục tiêu, nhịp request và chiều phản hồi; đối chiếu chữ ký cảnh báo, flow log, firewall decisions và endpoint telemetry. Nếu sensor chỉ thấy một chiều, một số heuristic có thể sai; ưu tiên xác minh bằng nhiều nguồn trước khi phân loại false positive hoặc sự cố thật.

## 10. Các giới hạn dễ dẫn đến kết luận sai

| Giới hạn | Hệ quả | Cách kiểm tra |
| --- | --- | --- |
| **TLS/SSH/VPN mã hóa** | Không đọc được payload ở điểm quan sát ngoài lớp mã hóa | Phân tích metadata hoặc bắt ở endpoint giải mã có quyền |
| **NAT / load balancer** | IP/port thay đổi giữa các điểm quan sát | Dùng NAT/session log, VIP/backend mapping và đồng bộ thời gian |
| **Packet drop của công cụ capture** | Một số gói không được lưu | Kiểm tra thống kê packet received/dropped của tcpdump và tải thiết bị |
| **SPAN oversubscription** | Cảm biến bỏ packet khi lưu lượng mirror vượt khả năng | Kiểm tra port, mirror direction, counters, tốc độ sensor |
| **NIC offloading (TSO/GSO/GRO/LRO/checksum)** | PCAP tại host có gói lớn bất thường hoặc checksum "sai" giả | So sánh điểm bắt trên dây, cấu hình offloading và vị trí packet trong network stack |
| **Bắt một chiều** | Không thấy response hoặc ACK | Bắt hai chiều tại điểm phù hợp, kiểm tra asymmetric routing |
| **Clock skew** | Không khớp thứ tự sự kiện ở hai máy | Đồng bộ NTP/PTP, ghi timezone và độ lệch ước lượng |
| **Capture filter quá hẹp** | Mất DNS, ICMP hoặc các flow phụ | Điều chỉnh filter theo giả thuyết; cân nhắc capture trước khi NAT |
| **Snaplen quá thấp** | Thiếu trường cần giải mã | Chọn snaplen phù hợp với protocol và nhu cầu điều tra |
| **Cloud/overlay encapsulation** | Chỉ thấy outer packet hoặc header đã thay đổi | Chọn đúng interface/điểm mirror, xác nhận tunnel và chế độ offload |

Đặc biệt, Wireshark đánh dấu **TCP retransmission**, **out-of-order** hoặc **bad checksum** dựa trên packet đã nhìn thấy và heuristics. Capture bị mất gói, offloading và đường đi bất đối xứng có thể tạo false positive. Không quy kết "mạng bị mất gói" chỉ vì bộ lọc `tcp.analysis.retransmission` trả nhiều kết quả; hãy kiểm tra sequence, ACK, cửa sổ TCP, RTT, thống kê capture và điểm quan sát thứ hai.

HTTP/3 sử dụng QUIC trên UDP, thường là cổng 443; vì thế chỉ lọc `tcp port 443` có thể bỏ qua cả luồng HTTP/3. Khi cần chẩn đoán kết nối web hiện đại, xác định ứng dụng thực tế đang dùng HTTP/1.1, HTTP/2 hay HTTP/3 trước khi đặt filter.

## 11. Thu thập PCAP an toàn và có thể kiểm chứng

**PCAP có thể chứa nội dung email, credential, cookie, IP nội bộ, dữ liệu ứng dụng hoặc thông tin định danh** nếu lưu lượng chưa được mã hóa hoặc nếu bắt tại điểm giải mã. Ngay cả khi payload được mã hóa, metadata và timing cũng có thể là dữ liệu nhạy cảm trong một số môi trường.

Trước khi capture:

1. Có quyền thu thập tại hệ thống/giao diện cụ thể; tuân thủ chính sách tổ chức và quy định bảo vệ dữ liệu áp dụng.
2. Chọn host, subnet, port và thời gian ít nhất đủ để trả lời câu hỏi; mặc định ưu tiên snaplen ngắn hoặc metadata nếu thích hợp.
3. Giới hạn dung lượng, đặt nơi lưu riêng với phân quyền phù hợp, không lưu vào thư mục dùng chung công khai.
4. Ghi lại thời gian UTC, timezone, thiết bị, interface, phiên bản công cụ, filter, snaplen và người thực hiện để tái hiện.
5. Khi chấm dứt, kiểm tra thống kê dropped packets và xem capture có đủ chiều request/response hay không.

Sau khi capture, chuyển tệp qua kênh bảo mật, giới hạn truy cập, áp dụng retention và quy trình xóa an toàn của tổ chức. Khi cần giữ bằng chứng cho điều tra sự cố hoặc an ninh, nên tạo hash để phát hiện thay đổi ngoài ý muốn:

~~~bash
sha256sum api-timeout.pcap
~~~

Lưu hash và metadata trong biên bản điều tra. Hash **không tự chứng minh dữ liệu đã được thu đúng chỗ**; giá trị của nó là hỗ trợ kiểm tra tệp có bị chỉnh sửa kể từ thời điểm ghi nhận hay không. Khi chia sẻ cho nhà cung cấp hoặc nhóm khác, cần giảm thiểu, ẩn danh hoặc lọc nội dung nhạy cảm theo chính sách, và giữ rõ bản nào là bản gốc.

Ở hệ thống tải cao, cân nhắc CPU, I/O, dung lượng và khả năng packet loss của cảm biến. Nếu việc capture có nguy cơ ảnh hưởng dịch vụ đang chạy, ưu tiên cổng TAP/traffic mirror chuyên dụng hoặc lựa chọn telemetry ít xâm lấn hơn. **Bắt packet ở nhiều điểm** chỉ hiệu quả nếu dung lượng, đồng bộ thời gian và ranh giới an toàn được chuẩn bị.

## 12. Quy trình thực hành điều tra một lỗi kết nối

Giả sử một dịch vụ Java trong mạng nội bộ báo timeout khi gọi API qua firewall và reverse proxy. Quy trình hợp lý:

1. **Nhận diện triệu chứng:** từ log ứng dụng lấy thời gian, host nguồn, tên miền hoặc IP đích, port, correlation ID và tỷ lệ lỗi. Đọc dashboard độ trễ và firewall log trước.
2. **Đặt giả thuyết có thể kiểm chứng:** "SYN không đi qua firewall" hoặc "SYN-ACK đi ra nhưng không về đến client". Tránh đặt câu hỏi quá rộng như "mạng có vấn đề gì?".
3. **Chọn điểm quan sát:** tại client và một điểm sau firewall; nếu có NAT, lấy mapping từ thiết bị để đối chiếu IP/port giữa hai phía.
4. **Thiết kế capture:** lấy cả hai chiều TCP/443 cho cặp endpoint, đặt thời lượng hoặc giới hạn packet, chọn snaplen theo câu hỏi. Nếu chưa biết IP do DNS, xác định đích trước hoặc thu thêm DNS trong phạm vi hợp lệ.
5. **Tái hiện có kiểm soát:** chạy request thử, ghi timestamp chính xác, correlation ID và thời điểm bắt đầu/kết thúc; không lẫn nhiều luồng kiểm thử nếu có thể.
6. **So sánh PCAP:** kiểm tra SYN/SYN-ACK/ACK/RST, retransmission, RTT và bất đối xứng. Đánh dấu vị trí cuối cùng quan sát được packet và điểm đầu tiên không còn thấy nó.
7. **Đối chiếu nhiều nguồn:** kết hợp với policy firewall, NAT table, route, IDS/IPS alert, DNS log, metric và application trace. Phân biệt dữ kiện quan sát được với giả thuyết.
8. **Khắc phục, kiểm chứng, lưu bằng chứng:** thay đổi cấu hình phù hợp theo quy trình; tái hiện lại điều kiện ban đầu để xác nhận kết quả, lưu PCAP và ghi chú có kiểm soát.

Ví dụ báo cáo điều tra có bằng chứng tốt:

> 14:03:12 UTC, client 10.10.10.25 gửi SYN đến 10.20.30.40:443. PCAP tại client ghi nhận ba lần SYN và không ghi nhận SYN-ACK. PCAP phía trong firewall cùng thời gian không thấy các SYN này; counter rule deny tăng tương ứng với nguồn, đích và port. Kết luận: lưu lượng bị chặn tại firewall theo rule đã xác định, cần kiểm tra chính sách truy cập của phân đoạn này. Giới hạn: dữ liệu được thu trong cửa sổ 30 giây trên hai interface đã mô tả.

Kết luận sẽ mạnh hơn khi có **thời gian, vị trí, filter, quan sát, log đối chiếu và giới hạn**. Nếu không có PCAP tại một điểm, đừng suy diễn toàn bộ đường đi chỉ từ packet của client.

## 13. Checklist quyết định nhanh

Trước khi đề xuất packet capture cho sự cố mạng hoặc an ninh mạng, hãy trả lời:

- **Tại sao:** cần kiểm chứng một câu hỏi nào ở cấp packet mà metric, log hoặc flow chưa trả lời được?
- **Ở đâu:** interface/segment/tunnel nào thực sự nhìn thấy luồng trước và sau điểm nghi vấn?
- **Khi nào:** thời điểm hoặc trigger nào chắc chắn trùng với hiện tượng cần bắt?
- **Bắt gì:** IP, port, protocol, cả hai chiều, có cần DNS/ICMP hay dữ liệu lớp 2 không?
- **Bao nhiêu:** giới hạn theo packet, thời gian, dung lượng và snaplen là gì?
- **Ai được xem:** quyền thu, quyền đọc tệp, lưu trữ, mã hóa và retention đã được xác định chưa?
- **Đọc kết quả ra sao:** ai sẽ đối chiếu packet với firewall, DNS, IDS/IPS, trace và sự kiện ứng dụng?

**Nguyên tắc lựa chọn:** sử dụng PCAP khi cần bằng chứng về trình tự và nội dung trường giao thức mà telemetry hiện có không cung cấp được, có thể đặt cảm biến đúng vị trí và kiểm soát an toàn phạm vi thu thập. Phân tích mạng hiệu quả bắt đầu bằng câu hỏi có thể kiểm chứng, rồi chọn mức dữ liệu nhỏ nhất đủ để trả lời; PCAP là công cụ đi sâu khi cần xác thực hành vi thực tế của packet trên đường truyền.
