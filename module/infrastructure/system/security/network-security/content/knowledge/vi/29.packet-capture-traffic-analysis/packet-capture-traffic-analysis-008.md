# BPF filter và giới hạn dữ liệu thu thập khi packet capture

Một nhóm vận hành cần xác định vì sao API nội bộ đôi lúc mất kết nối tới database. Trên máy chủ có hàng nghìn kết nối đồng thời, nếu ghi tất cả traffic bằng packet capture trong một giờ, nhóm có thể tạo ra nhiều gigabyte PCAP chứa địa chỉ hệ thống, DNS queries, session tokens, nội dung giao thức chưa mã hóa và cả dữ liệu người dùng không liên quan. Ngược lại, nếu lọc chỉ một cổng TCP quá sớm, nhóm có thể bỏ sót DNS, ICMP báo lỗi MTU hoặc những gói TCP bị phân mảnh.

**BPF capture filter** là một công cụ để chọn những gói tin phù hợp với biểu thức ở thời điểm thu thập. Nhưng **lọc gói** không tự bảo đảm rằng thông tin được thu là tối thiểu, đầy đủ, đã được khử định danh hoặc không chứa dữ liệu cá nhân. Cần kết hợp **filter có mục đích, chọn đúng vị trí quan sát, giới hạn thời gian/số gói/độ dài gói, kiểm chứng packet loss và quản trị vòng đời PCAP**.

Bài thuộc chương **Packet capture và phân tích lưu lượng** của module **SECURITY_NETWORK_SECURITY**. Kiến thức gắn với phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, TCP/IP, TLS, giám sát, mô hình hóa mối đe dọa và bảo vệ dữ liệu trong môi trường mạng nội bộ, cloud hoặc Kubernetes.

**Nguyên tắc trung tâm:** thu **đủ cho câu hỏi kỹ thuật đã được phê duyệt**, **không thu rộng chỉ vì công cụ cho phép**, và luôn đánh giá **độ chính xác lẫn dữ liệu nhạy cảm còn lại** sau khi áp capture filter.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Berkeley Packet Filter (BPF)** trong bối cảnh capture, phân biệt **classic BPF (cBPF)**, eBPF và display filter.
2. Viết capture filter theo **host, network, direction, protocol, port, port range** và kết hợp các toán tử logic.
3. Đọc đúng **ngoặc, `and`/`or`/`not`**, quan hệ giữa peer và port, và phạm vi của điều kiện IPv4/IPv6.
4. Phân biệt **lọc đầu vào khi capture** với **lọc gói đã ghi để hiển thị/phân tích**; hiểu tác động tới tính đầy đủ của evidence.
5. Thiết kế phạm vi thu thập theo **interface, vị trí mạng, thời gian, packet count, snaplen, file-size/rotation**.
6. Nhận diện các điểm mù do **VLAN, tunnels, NAT, TCP/UDP fragmentation, IPv6 extension headers, offloading, SPAN/TAP và encryption**.
7. Sử dụng an toàn các lệnh minh họa `tcpdump` và `tshark` trên môi trường được ủy quyền; đọc các counters và file PCAP.
8. Biết rằng **snaplen và capture filter không phải biện pháp ẩn danh hóa dữ liệu**; quản lý PCAP bằng phân quyền, mã hóa, thời hạn lưu và quy trình xóa.
9. Lập **positive/negative tests** và checklist trước khi triển khai một phiên capture phục vụ troubleshooting hoặc điều tra sự cố.

## 2. Packet capture nằm ở đâu trong quy trình quan sát mạng?

Một packet capture lưu lại các gói được nhìn thấy tại một **điểm quan sát (vantage point)**. Hệ điều hành, card mạng, virtual switch, tunnel, cloud mirroring hoặc thiết bị TAP/SPAN có thể cung cấp gói cho công cụ thu thập.

~~~mermaid
flowchart LR
    SRC["Client / workload"] --> NET["Router, firewall, NAT, tunnel, switch"]
    NET --> DST["Server / service"]
    NET -.->|"SPAN/TAP/mirror tùy kiến trúc"| SENSOR["Capture sensor"]
    SENSOR --> BPF["Capture filter: BPF predicate"]
    BPF --> BUF["Buffer / capture engine"]
    BUF --> PCAP[("PCAP/PCAPNG file")]
    PCAP --> DISP["Display filter / analysis"]
    DISP --> REPORT["Kết luận có bằng chứng"]
    GOV["Approval, minimization, access & retention"] -.-> SENSOR
    GOV -.-> PCAP
~~~

**Lưu ý về sơ đồ:** capture có thể diễn ra ngay trên host/server, trong container/VM, ở switch mirror hoặc tại điểm mạng khác, không nhất thiết gói phải đi qua một thiết bị tên “sensor”. Bộ lọc capture áp ở một giai đoạn do nền tảng/libpcap/driver hỗ trợ; vị trí thực thi ảnh hưởng số gói được chuyển lên userspace nhưng **không khôi phục được gói sensor chưa bao giờ nhìn thấy**.

### 2.1. Bốn câu hỏi phải trả lời trước khi chọn filter

| Câu hỏi | Ví dụ | Rủi ro nếu bỏ qua |
|---|---|---|
| **Đang tìm dấu hiệu gì?** | TCP handshake timeout tới database | Thu cả traffic không liên quan hoặc bỏ mất dấu hiệu cần xem |
| **Quan sát ở đâu?** | NIC của API host, node Kubernetes hay phía database? | NAT, tunnel, offload làm IP/port quan sát khác nhau |
| **Cần bao nhiêu chi tiết?** | Chỉ TCP flags/timestamps hay TLS/application payload? | Snaplen quá ngắn làm không đủ bằng chứng; quá dài lộ dữ liệu |
| **Giới hạn và quyền là gì?** | 60 giây, ứng dụng cụ thể, owner và nơi lưu PCAP | Vượt phạm vi thu thập, rò rỉ hoặc giữ evidence quá lâu |

Trong nhiều tình huống, **flow logs, eBPF network telemetry, application tracing hoặc firewall counters** có thể đủ để trả lời câu hỏi mà không cần thu raw packet payload.

## 3. BPF là gì? Classic BPF khác eBPF như thế nào?

**BPF (Berkeley Packet Filter)** bắt nguồn từ mô hình lọc và bắt gói tin. Trong hệ sinh thái `libpcap`/`tcpdump`, người vận hành thường viết một **filter expression** dễ đọc như `tcp port 443 and host 192.0.2.10`. Công cụ biên dịch biểu thức thành chương trình lọc thích hợp cho capture backend.

### 3.1. Classic capture filter

Đặc điểm cốt lõi:

- Kiểm tra các **trường có thể nhận diện trong packet** như loại giao thức, IP, port, địa chỉ MAC hoặc một số byte offset.
- Quyết định **giữ hay loại** gói cho pipeline capture theo môi trường thực thi.
- Giảm lượng gói phải sao chép/lưu/đọc, hỗ trợ thu hẹp phạm vi phục vụ điều tra.
- Không phải bộ phân tích trạng thái kết nối, không phải DLP engine, không tự tái lắp ráp stream hoặc giải mã TLS.
- Semantics cụ thể phụ thuộc **link-layer type, backend và khả năng của trình biên dịch/filter engine**.

Trong tài liệu này, **“BPF filter” mặc định chỉ capture filter theo cú pháp libpcap/tcpdump**, trừ khi có nhắc rõ đến một loại khác.

### 3.2. eBPF không đồng nghĩa với bộ lọc này

**eBPF** là công nghệ chạy chương trình được kiểm chứng trong nhiều hook của Linux và một số hệ thống liên quan; nó có thể hỗ trợ **networking, observability, tracing, security policy** và nhiều use cases khác.

| Khía cạnh | cBPF/libpcap capture filtering | eBPF (khái quát) |
|---|---|---|
| Mục đích điển hình | Chọn packet cho một phiên capture | Chạy chương trình ở nhiều hook tùy loại |
| Đầu vào người vận hành | Biểu thức như `host`, `port`, `net`, `tcp` | Chương trình/bytecode theo framework và verifier |
| Trạng thái phức tạp | Không mặc định theo dõi session/flow state | Có thể dùng maps/state theo thiết kế |
| Dữ liệu quan sát | Header/trường packet ở capture point | Packet, socket, process, kernel events tùy hook |
| Quyền và an toàn | Cần quyền capture, bảo vệ file PCAP | Cần kiểm soát quyền nạp/chạy chương trình và dữ liệu maps |
| Khả năng thay thế nhau | Không tự tạo host firewall hoặc network-policy engine | Không tự biến mọi chương trình eBPF thành libpcap filter |

Một hệ thống như CNI/EDR dùng eBPF để **enforce security policy** có thể có semantics hoàn toàn khác một câu `tcpdump 'tcp port 443'`. Đừng dùng “BPF” để suy ra khả năng lọc L7, identity awareness hay decryption khi chưa xác định sản phẩm.

### 3.3. Capture filter và display filter

| Thuộc tính | **Capture filter** | **Display filter** |
|---|---|---|
| Thời điểm | Trước/khi gói vào tập dữ liệu capture | Sau khi đã thu hoặc mở file |
| Mục đích | Giới hạn packet được lưu | Hiển thị/phân tích một phần packet đã lưu |
| Cú pháp thường gặp | libpcap: `tcp port 443` | Wireshark/TShark: `tcp.port == 443` |
| Giảm file PCAP ngay từ đầu? | **Có**, nếu filter được áp đúng và còn data path | **Không**, nếu chỉ dùng để hiển thị |
| Có khôi phục gói bị bỏ bởi capture filter? | Không | Không |
| Ảnh hưởng độ nhạy dữ liệu file gốc | Có thể giảm dữ liệu được ghi nhưng không bảo đảm ẩn danh | File gốc vẫn chứa những gì đã capture |

**Bẫy:** trong Wireshark, `tcp.port == 443` là **display filter**, không phải `tcpdump` capture expression. Trong TShark, `-f` dùng **capture filter**, còn `-Y` dùng **display filter**; nhầm hai loại có thể khiến thu rộng hơn dự tính.

## 4. Cú pháp BPF capture filter cơ bản

Filter thường được viết bằng **primitive qualifiers**, có thể gắn với **hướng**, **kiểu đối tượng**, **giao thức** và kết hợp logic.

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| Host | `host 192.0.2.10` | Gói có source hoặc destination IP phù hợp |
| Source host | `src host 192.0.2.10` | Source address là host này |
| Destination host | `dst host 198.51.100.20` | Destination address là host này |
| CIDR | `net 198.51.100.0/24` | Gói gắn với mạng CIDR theo semantics IP |
| Source CIDR | `src net 198.51.100.0/24` | Source nằm trong CIDR |
| Port | `port 443` | Một đầu endpoint có port phù hợp, trong phạm vi protocol được nhận dạng |
| Destination TCP | `tcp dst port 443` | TCP có destination port 443 |
| Source UDP | `udp src port 53` | UDP có source port 53 |
| Port range | `tcp portrange 8000-8100` | TCP port nằm trong dải ở một trong hai phía |
| Protocol | `tcp`, `udp`, `icmp`, `icmp6`, `arp` | Giao thức theo decode/link type được hỗ trợ |
| IPv4/IPv6 | `ip`, `ip6` | Xét gói IPv4 hoặc IPv6 |
| Layer 2 | `ether host 02:00:00:00:00:01` | MAC nguồn/đích, khi link type phù hợp |
| VLAN | `vlan` | Match VLAN encapsulation khi capture path giữ tag và decoder hỗ trợ |

**Các địa chỉ `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` và `2001:db8::/32` trong bài là dải dành cho tài liệu**, không phải địa chỉ để tự ý bắt traffic ngoài mạng lab.

### 4.1. Kết hợp `and`, `or`, `not`

~~~text
# Chỉ từ host A tới host B qua TCP/443.
src host 192.0.2.10 and dst host 198.51.100.20 and tcp dst port 443

# Cho cả TCP/443 và UDP/443 tới cùng host đích.
dst host 198.51.100.20 and (tcp dst port 443 or udp dst port 443)

# Bắt cả query và response DNS qua UDP/TCP port 53, không giới hạn host.
(udp port 53 or tcp port 53)

# Bắt IPv4 hoặc IPv6, nhưng vẫn phải test extension headers/tunnels.
(ip or ip6) and tcp port 443
~~~

**Dùng ngoặc một cách tường minh** khi trộn các toán tử. Không dựa vào trí nhớ về độ ưu tiên để viết biểu thức có thể ghi nhầm dữ liệu của dịch vụ khác.

### 4.2. Một lỗi logic gây capture quá rộng

~~~text
# DỄ SAI: thiếu ngoặc, điều kiện host có thể không giới hạn toàn bộ OR.
host 192.0.2.10 and tcp port 443 or udp port 53

# RÕ Ý: chỉ thu TCP/443 hoặc UDP/53 khi có host A.
host 192.0.2.10 and (tcp port 443 or udp port 53)
~~~

Trong biểu thức đầu, nhánh `udp port 53` có thể match DNS của **những host khác** không nằm trong phạm vi đang điều tra. Cả hai biểu thức vẫn cần kiểm tra **chiều source/destination** nếu mục tiêu chỉ là traffic gửi từ host A tới server B.

### 4.3. `host` và `port` có hai chiều

~~~text
# Bắt cả chiều gửi và nhận của một flow TCP/443 liên quan host A:
host 192.0.2.10 and tcp port 443

# Chỉ gói đi từ A đến B, cổng đích 443:
src host 192.0.2.10 and dst host 198.51.100.20 and tcp dst port 443
~~~

Hai câu hỏi điều tra khác nhau:

- Nếu chỉ cần **request outbound**, lọc source/destination có thể phù hợp.
- Nếu cần **handshake, reset, retransmission, response timing**, phải giữ **cả hai chiều** hoặc capture từ hai phía phù hợp.

Chỉ nhìn được chiều đi mà không thấy chiều về **không chứng minh server không phản hồi**; phản hồi có thể đi đường khác hoặc bị capture filter loại bỏ.

## 5. Capture filter phải gắn với mục tiêu kỹ thuật

### 5.1. Kiểm tra TCP handshake tới API

**Câu hỏi:** client A có nhận SYN/ACK từ server B qua TCP/443 không?

~~~text
host 192.0.2.10 and host 198.51.100.20 and tcp port 443
~~~

Biểu thức giữ **hai chiều** giữa hai host nếu địa chỉ quan sát không bị NAT đổi và TCP headers được decode đúng. Có thể dùng thêm **TCP flags filter** để thu hẹp handshake khi chỉ cần kiểm tra SYN, nhưng không nên bỏ ACK/RST/retransmission khi đang tìm nguyên nhân kết nối chậm.

### 5.2. Quan sát DNS resolution của một host

~~~text
host 192.0.2.10 and (udp port 53 or tcp port 53)
~~~

Nó **không** bao phủ DNS-over-HTTPS (thường TCP/443), DNS-over-TLS (thường TCP/853), DNS-over-QUIC hoặc resolver logic bên trong ứng dụng. Không kết luận "không có DNS" chỉ vì không thấy UDP/53.

### 5.3. Kiểm tra dịch vụ dùng TCP và QUIC

~~~text
host 192.0.2.10 and (tcp port 443 or udp port 443)
~~~

Gói trên UDP/443 **có thể** mang QUIC/HTTP/3, nhưng port không chứng minh một protocol cụ thể. Capture filter cũng **không tự đọc được URL, user, TLS SNI hay plaintext request** trong traffic đã mã hóa.

### 5.4. Ghi nhận ICMP liên quan kết nối chậm

~~~text
host 192.0.2.10 and (tcp port 443 or icmp or icmp6)
~~~

**Giới hạn quan trọng:** một thông báo ICMP lỗi từ router/trung gian có thể có **source IP là router**, không phải client A/server B, nên điều kiện `host A` có thể loại bỏ chính ICMP đang cần xem. Trong lab được ủy quyền, cân nhắc một **phiên capture mục tiêu thứ hai** chỉ cho ICMP/ICMPv6 trên interface và thời gian ngắn, thay vì mở toàn bộ packet traffic vô hạn.

## 6. TCP flags và byte-offset filters: mạnh nhưng dễ sai

Classic BPF có thể kiểm tra byte/field trong packet header:

~~~text
# Ví dụ chọn các gói TCP có bật SYN bit, bao gồm cả SYN và SYN-ACK.
tcp[tcpflags] & tcp-syn != 0

# Chỉ khi SYN bật, ACK chưa bật (initial SYN theo flags).
tcp[tcpflags] & (tcp-syn|tcp-ack) == tcp-syn
~~~

**Cảnh báo:**

- Các filter kiểm tra TCP header phụ thuộc parser/link type, IP fragmentation và IPv6 extension header handling.
- SYN không có ACK **không tự chứng minh một kết nối hoàn toàn mới** hoặc một hành vi tấn công; có thể là retransmission.
- Không chỉ thu SYN rồi bỏ SYN/ACK/RST/ICMP nếu câu hỏi cần chẩn đoán kết nối hai chiều.
- `tcpdump` có thể có tối ưu/compiler và cách render BPF khác theo OS/libpcap.

### 6.1. Filter theo port không phải một stateful firewall

Classic capture filter thường không có thông tin **dòng TCP hoàn chỉnh**, không biết user đã xác thực, không tái lắp ráp payload TLS và không kiểm tra `HTTP GET /admin` trong stream encrypted.

Không dùng capture filter như cơ chế **ngăn truy cập trái phép**. Muốn chặn kết nối phải dùng firewall, CNI NetworkPolicy, ACL, WAF, mTLS/authorization hoặc biện pháp enforcement chuyên biệt.

## 7. Lọc gói quá sớm có thể xóa luôn chứng cứ

Một display filter có thể được thay đổi mà **không ảnh hưởng file PCAP gốc**. Một capture filter loại gói **trước khi ghi**, và **không có cách nào lấy lại từ chính file đó** những gói đã loại.

Ví dụ điều tra lỗi HTTPS:

| Lọc quá hẹp | Thông tin có nguy cơ mất |
|---|---|
| Chỉ `tcp port 443` | DNS, UDP/443 QUIC, ICMP/ICMPv6 errors, route changes |
| Chỉ `dst port 443` | SYN/ACK, responses, RST từ server khi source port là 443 |
| Chỉ source IP client trước NAT | Traffic nhìn từ capture point phía sau NAT |
| Chỉ IPv4 | IPv6 happy-eyeballs/fallback path |
| Chỉ outer TCP ở tunnel endpoint | Inner workload traffic hoặc encapsulated protocols |
| Chỉ các gói có SYN bit | Application stalls, window updates, retransmissions của data segments |
| Chỉ một interface | Traffic asymmetric trên NIC/namespace khác |

### 7.1. Hai cấp phạm vi hữu ích

1. **Vùng thu thập chính:** giới hạn theo interface, host/service, thời gian, độ dài gói và quyền được phê duyệt.
2. **Vùng bổ sung có điều kiện:** chỉ mở thêm protocol/đường liên quan (DNS, ICMP, router/NAT side) nếu kết quả ban đầu cho thấy cần và được cho phép.

Chiến lược này cân bằng **minimization** với **độ đầy đủ**. Không tự thu tất cả raw payload chỉ vì "forensics cần đủ": mức mở rộng phải có lý do, thời hạn, owner và kho lưu an toàn.

## 8. Giới hạn dữ liệu: phải kiểm soát nhiều chiều

**Capture filter chỉ là một chiều giới hạn**. Cần đánh giá ít nhất:

| Chiều giới hạn | Công cụ/biện pháp | Giới hạn cần hiểu |
|---|---|---|
| **Vị trí** | Đúng host/NIC/network namespace/SPAN port | Sai vantage point có thể không thấy gói |
| **Đối tượng** | `host/net/port/protocol` BPF | Không lọc user/tenant/HTTP body khi mã hóa |
| **Thời gian** | Cửa sổ capture, stop condition | Sự cố xảy ngoài cửa sổ không có evidence |
| **Số gói** | Packet count limit | Đạt ngưỡng sớm trước khi lỗi xuất hiện |
| **Độ dài mỗi gói** | Snaplen `-s` | Không chắc bỏ hết payload, có thể thiếu headers cần thiết |
| **Dung lượng** | File rotation/size quota | Rotation có thể overwrite evidence hoặc dừng thu sớm |
| **Dữ liệu trường** | Flow-only/metadata telemetry thay PCAP | Ít khả năng phân tích payload chi tiết |
| **Người truy cập** | RBAC, encryption, log access | File PCAP vẫn là nguồn dữ liệu nhạy cảm |
| **Thời gian lưu** | Retention, deletion, backups | Xóa local không đủ nếu có bản sao |
| **Trích xuất/chia sẻ** | Redaction, anonymization được đánh giá | Hash IP không bảo đảm ẩn danh tuyệt đối |

### 8.1. Snaplen: cắt gói, không phải xóa payload an toàn

**Snaplen (snapshot length)** giới hạn **số byte tối đa được lưu cho mỗi gói**. Ví dụ `-s 96` thường cố giữ một phần header nhưng cũng có thể chứa **byte của payload ứng dụng** tùy Ethernet/VLAN/IP options, header length và encapsulation.

~~~text
Gói thật trên wire:           1514 byte
Snaplen được chọn:             96 byte
Captured length:          tối đa 96 byte
Original packet length:      1514 byte (metadata nếu capture format ghi)

Phần bị cắt không nằm trong bản ghi packet đó.
Nhưng 96 byte đầu có thể đã chứa dữ liệu nhạy cảm.
~~~

**Không được kết luận `-s 96` nghĩa là “chỉ có metadata” hoặc “không thể chứa token”.** Một số header có thể ngắn và byte payload bắt đầu trước byte 96. Ngược lại, với VLAN/QinQ, IPv6 extension headers, GRE/VXLAN hoặc TLS parsing, snaplen 96 có thể **không đủ để xem trường cần phân tích**.

### 8.2. Snaplen và phân tích TLS

TLS traffic được mã hóa có thể vẫn để lộ metadata như IP/port, packet sizes và timing. Để phân tích handshake, cần đủ các record bytes; snaplen quá ngắn có thể không lưu đủ handshake extensions. Việc capture đủ TLS handshake **không đồng nghĩa có thể giải mã application data**.

Trong TLS 1.3, không kỳ vọng đọc được payload ứng dụng chỉ từ PCAP. Không thu hoặc yêu cầu private keys/session secrets nếu nhiệm vụ không được phê duyệt rõ, và không đưa chúng vào ticket/chat/logs.

### 8.3. Dung lượng và packet rate

Một ước lượng thô:

\[
\text{Dung lượng} \approx \text{packets/giây} \times \text{giây thu}
\times \text{số byte ghi trung bình mỗi packet}
\]

Cần cộng **per-record overhead, file headers, container format, metadata, buffer/write amplification và nhiều file khi rotation**. Đây không phải cam kết đo chính xác. Số bytes lưu có thể thấp hơn packets on wire nhờ snaplen, nhưng **sensor và mirror path vẫn phải nhận traffic trước khi filter ở điểm tương ứng**.

### 8.4. Không nhầm packet truncation với packet loss

- **Truncation:** gói được ghi, nhưng `captured length < original length` do snaplen/capture backend.
- **Packet loss/drop:** gói cần quan sát **không được ghi lại** do filter, nguồn không thấy gói, buffer overflow, driver/mirror limitations hoặc failure.
- **Filter exclusion:** gói bị loại **theo chủ đích**; không phải lỗi capture engine nhưng làm mất phạm vi phân tích.

Từ file PCAP có gói bị cắt, không thể khôi phục bytes đã không được lưu. Từ một file có 0 packet, không thể tự kết luận hệ thống không phát ra traffic.

## 9. Vị trí capture, chiều gói và các điểm mù mạng

### 9.1. Client-side, server-side và điểm giữa

Giả sử một client gọi API qua NAT:

~~~mermaid
flowchart LR
    CLIENT["Client 192.0.2.10"] -->|"Trước NAT: source A"| NAT["NAT / firewall"]
    NAT -->|"Sau NAT: source khác"| SERVER["API server 198.51.100.20"]
    CP1["Capture point A"] -.-> CLIENT
    CP2["Capture point B"] -.-> NAT
    CP3["Capture point C"] -.-> SERVER
~~~

Vị trí capture quan trọng hơn việc filter trông đẹp:

- Trước NAT có thể thấy **client private/source address ban đầu**.
- Sau SNAT có thể chỉ thấy địa chỉ **đã dịch**; filter theo source ban đầu không match.
- Nếu có DNAT/load balancer, destination IP/port nhìn thấy có thể là **Service VIP**, backend IP hoặc Pod IP tùy vị trí.
- Với routing bất đối xứng, điểm quan sát chỉ có thể thấy **một hướng**.
- Capture trên một Pod/node có thể không thấy lưu lượng tới replica khác, interface khác hoặc namespace khác.

Muốn so sánh hai điểm capture phải ghi **đồng hồ và độ lệch thời gian**, vị trí, link type, chiều luồng, chính sách NAT và tính toàn vẹn file; không so timestamps như thể clock hai máy chắc chắn đồng bộ.

### 9.2. VLAN và QinQ

Ở Ethernet có VLAN tag, filter có thể cần từ khóa `vlan` tùy cách gói được capture:

~~~text
# Ví dụ khi packet được lưu với 802.1Q VLAN tag thực sự nhìn thấy.
vlan and ip and tcp port 443

# Ví dụ QinQ/double-tag chỉ khi decoder và capture path hỗ trợ.
vlan and vlan and ip and tcp port 443
~~~

**Cảnh báo:** từ khóa `vlan` có thể thay đổi **offset được compiler sử dụng cho những phần biểu thức phía sau**; nếu trộn `vlan`/`or` phức tạp, cần compile/test trên đúng **DLT/link type**. Card NIC hoặc vSwitch có thể **strip VLAN tags bằng hardware offload**, làm capture nhìn khác gói trên dây. Không mặc định mọi PCAP giữ được VLAN ID.

### 9.3. VXLAN, Geneve, GRE, IPsec và những đường hầm khác

~~~text
Outer packet:
  Outer IP + UDP (có thể là VXLAN/Geneve)
    -> Tunnel header
      -> Inner Ethernet/IP/TCP/application
~~~

Một `tcp port 443` tại NIC vật lý của node có thể **không match inner TCP/443** khi ở điểm quan sát đó chỉ thấy outer UDP tunnel. Một số backend cho phép decode/tunnel filters đặc biệt, nhưng support và offset phụ thuộc sản phẩm.

Khi điều tra Kubernetes/cloud overlay:

1. Xác định capture point **trước hay sau encapsulation**.
2. Biết outer endpoint IP/port và overlay ID phù hợp.
3. Ưu tiên capture **bên trong network namespace hoặc tại workload interface** nếu được phép và phù hợp câu hỏi.
4. Không cố giải mã VPN/IPsec/TLS để xem dữ liệu ngoài phạm vi được phê duyệt.
5. Ghép trace/counters từ CNI, VPC flow logs và service telemetry khi raw payload không cần thiết.

### 9.4. Fragmentation: port có thể không nằm trong từng mảnh

IP fragmentation tạo ra nhiều mảnh, trong đó **không phải mọi mảnh đều mang đầy đủ TCP/UDP header**:

- Một capture filter `tcp port 443` có thể match **mảnh đầu** nhưng không match mảnh tiếp theo do không có port field ở vị trí mong đợi.
- Phân tích thiếu các mảnh còn lại có thể dẫn đến kết luận sai về retransmission hoặc payload.
- IPv6 dùng extension headers và fragment header; việc nhận dạng transport/port trong biểu thức BPF có thể hạn chế tùy backend và vị trí header.
- Sự cố MTU/PMTUD có thể liên quan **ICMP Fragmentation Needed** hoặc **ICMPv6 Packet Too Big** phát ra bởi router trung gian, nên `host client` filter quá hẹp có thể bỏ sót.

Khi cần điều tra fragmentation, hãy **mở rộng đúng giao thức/địa chỉ và khoảng thời gian** theo phê duyệt, thay vì suy mọi packet transport đều có port decode được.

### 9.5. Tính riêng tư vẫn tồn tại với traffic đã mã hóa

Một PCAP không giải mã TLS/QUIC vẫn có thể chứa:

- IPs công khai hoặc private, hostname (khi protocol lộ), MAC, VLAN IDs, network topology.
- DNS queries, timing patterns, traffic volumes và endpoint activity.
- TLS handshake metadata được phép quan sát ở một số phiên/giao thức.
- Thông tin khách hàng qua non-encrypted HTTP, SMTP/IMAP hoặc legacy protocols khác.
- Metadata có thể kết hợp với logs khác để suy ra user hay hành vi.

**Mã hóa payload không biến PCAP thành dữ liệu công khai.** Bảo vệ PCAP theo phân loại thông tin có thể suy ra hoặc trực tiếp xuất hiện.

## 10. Offloading, performance và giới hạn packet accuracy

### 10.1. TSO/GSO/GRO/LRO/checksum offload

Card mạng và kernel có thể xử lý packet theo **offloading**:

| Cơ chế | Tác động có thể quan sát trong capture trên host |
|---|---|
| TSO / GSO | Capture thấy **large segments** trước khi NIC chia thành frame trên dây |
| GRO / LRO | Capture có thể thấy nhiều segments được **gộp** trước/ở một điểm xử lý |
| Checksum offload | Checksum hiển thị “incorrect” tại capture point dù packet trên dây hợp lệ |
| VLAN offload | Tag có thể không hiển thị như tưởng trong gói bắt tại host |
| Hardware filtering | NIC/driver có thể loại traffic trước khi capture engine nhận được |

Không sửa NIC production hoặc tắt offload chỉ để PCAP giống Wireshark examples; thay đổi offload có thể ảnh hưởng throughput và latency. Nếu cần evidence “trên wire” chính xác, cân nhắc TAP/SPAN ở đúng vị trí, sensor được phê duyệt và cách đo không làm tăng rủi ro hệ thống.

### 10.2. SPAN/TAP/mirroring có thể làm mất gói

SPAN/mirror port thường có giới hạn băng thông và mức ưu tiên; khi aggregate traffic từ nhiều cổng, gói có thể bị drop trước sensor. Cloud traffic mirroring cũng có giới hạn theo dịch vụ, instance type và đường mạng.

Do đó:

- Một file PCAP thiếu packet **không tự chứng minh trên wire không có packet đó**.
- Cần thu interface/sensor drop counters, tổng lưu lượng, queue/buffer pressure và time synchronization.
- Packet ordering/timestamps ở mirror có thể không hoàn toàn trùng với đường gốc.
- BPF lọc ở sensor **không làm giảm băng thông đã tới mirror port** nếu traffic đã được copy trước filter.

### 10.3. Counter packet capture: đọc đúng ngữ cảnh

Khi `tcpdump` dừng, công cụ thường báo các số liệu dạng:

~~~text
<n> packets captured
<m> packets received by filter
<k> packets dropped by kernel
~~~

**Ý nghĩa counters có thể phụ thuộc OS, driver và libpcap implementation.** Không tự lấy `received by filter − captured` để suy chính xác số packet bị mất nếu tài liệu của capture backend chưa định nghĩa semantics. “Dropped by kernel” có thể bằng 0 trong khi gói đã bị drop ở switch/SPAN/driver hoặc bị capture filter loại hợp lệ.

**Kiểm tra cần thiết:**

1. Số packets và duration so với baseline traffic ở cùng interface.
2. Drops ở sensor, kernel buffer, NIC/vSwitch và mirror infrastructure nếu có.
3. CPU, disk I/O, free space, PCAP write errors và flow distribution.
4. Timestamp quality/clock offset khi so nhiều sensors.
5. **Positive control**: một flow hợp lệ mà sensor chắc chắn phải nhìn thấy.

## 11. Chuẩn bị một phiên capture được ủy quyền

Trước khi chạy bất kỳ lệnh live capture nào, xác nhận:

- **Owner và mục đích:** ticket/sự cố, người phê duyệt, dữ liệu nào cần quan sát.
- **Environment:** chỉ lab hoặc hệ thống thuộc quyền, không capture mạng của bên khác.
- **Interface:** đúng NIC/network namespace và hướng traffic.
- **Filter:** reviewed expression, hai chiều khi cần, protocol/port/host đúng.
- **Duration:** deadline rõ ràng; không bật capture vô hạn.
- **Bounds:** `snaplen`, số gói, file size/rotation, disk quota và nơi ghi.
- **Access:** chỉ nhân sự điều tra có quyền, thư mục lưu được phân quyền và mã hóa nếu cần.
- **Privacy:** đánh giá khả năng capture payload/PII, lấy dữ liệu ít nhạy cảm nhất đủ dùng.
- **Evidence:** time source, version công cụ, exact command/filter, hash/file metadata và chain of custody nếu phục vụ incident response.
- **Cleanup:** retention/deletion plan, kiểm soát bản sao trong ticket/chat/email/backups.

### 11.1. Những quyền không nên mở rộng để capture

Packet capture có thể yêu cầu **elevated network privileges** ở OS/container/capture backend. Không:

- Cấp `root`/`CAP_NET_RAW`/`CAP_NET_ADMIN` rộng cho ứng dụng production để tiện debug.
- Mount host network namespace, runtime socket hoặc privileged container cho một thử nghiệm chưa được duyệt.
- Đổi firewall/IDS rules, disable TLS hoặc bật interface promiscuous mode trên production nếu chưa có change approval.
- Copy PCAP tới laptop cá nhân hoặc chèn payload vào issue tracker không được phép.

Tổ chức có thể cung cấp **capture service, approved diagnostic host hoặc flow telemetry** để giảm số người cần quyền live packet capture.

## 12. Ví dụ thực hành `tcpdump`: cú pháp và giới hạn

**Lưu ý quan trọng:** toàn bộ địa chỉ và hostname ví dụ là **dữ liệu dành cho lab/tài liệu**. Các câu lệnh sau **không được thực thi trong lúc viết bài** và **không tạo traffic**; chúng chỉ có kết quả hữu ích khi lab thực sự có giao tiếp phù hợp, interface tồn tại và người chạy có quyền. `sudo` chỉ dùng theo chính sách hệ thống; không tự nâng quyền bằng cách sửa permissions.

### 12.1. Xem interface và compile filter mà không bắt gói

~~~bash
# Hiển thị interfaces theo góc nhìn libpcap/tcpdump.
tcpdump -D

# In chương trình lọc được biên dịch để kiểm tra expression.
# Không phải live packet capture.
tcpdump -d 'host 192.0.2.10 and (tcp port 443 or udp port 53)'
~~~

`tcpdump -d` hiển thị dạng đọc được của chương trình lọc và thoát; `-dd`/`-ddd` cho cách biểu diễn khác. Việc compiler chấp nhận filter **không chứng minh** nó match đúng gói ở interface thực tế; cần test trên PCAP lab có link type phù hợp và biết layout packet.

### 12.2. Capture vào file với số gói và snaplen giới hạn

~~~bash
# Chỉ chạy trong lab hoặc endpoint được ủy quyền.
# Interface lo và 127.0.0.1 chỉ là ví dụ local loopback.
# Thay bằng interface/lab-host cụ thể khi được phê duyệt.
sudo tcpdump \
  -i lo \
  -nn \
  -s 96 \
  -c 50 \
  -w ./lab-loopback-443.pcap \
  'host 127.0.0.1 and tcp port 443'
~~~

| Tùy chọn | Ý nghĩa | Giới hạn |
|---|---|---|
| `-i lo` | Chọn loopback interface ở Linux lab | Không thấy packet NIC/VM khác |
| `-nn` | Không phân giải hostname và service port names khi in output | Không giảm IP/payload được ghi vào PCAP |
| `-s 96` | Chỉ giữ tối đa 96 byte mỗi gói | **Có thể còn payload hoặc thiếu headers** |
| `-c 50` | Dừng sau số gói đã match/thu theo semantics công cụ | Nếu không có packet thì có thể chờ lâu |
| `-w file.pcap` | Ghi packet vào file | File chứa packet bytes nhạy cảm; bảo vệ và giới hạn nơi lưu |
| `'host ... and tcp port ...'` | Capture filter | Giới hạn theo predicate, không chứng minh tính đầy đủ |

**Quan trọng:** mặc dù có `-c 50`, lệnh có thể **không tự dừng sớm** nếu traffic không có hoặc không match. Do đó khi cần bảo đảm thời lượng, hãy kết hợp giới hạn thời gian bằng cơ chế được nền tảng hỗ trợ (ví dụ tool orchestration hoặc `timeout` trên Linux).

### 12.3. Dừng sau khoảng thời gian xác định

~~~bash
# GNU coreutils timeout trên Linux; SIGINT giúp tcpdump kết thúc có kiểm soát.
# Chỉ chạy nếu có permission và path lưu đã được phê duyệt.
sudo timeout --signal=INT 30s tcpdump \
  -i lo \
  -nn \
  -s 96 \
  -c 100 \
  -w ./lab-loopback-443-window.pcap \
  'host 127.0.0.1 and tcp port 443'
~~~

Ở một số phiên bản `timeout`, khi deadline kích hoạt, **exit status** có thể thể hiện timeout, dù tcpdump đã được yêu cầu kết thúc và file PCAP tồn tại. **Không coi file tồn tại là chắc chắn hợp lệ**; cần mở kiểm tra cấu trúc file sau khi kết thúc. Không dùng shell redirection hoặc process kill mạnh làm hỏng việc flush/close nếu có cách kết thúc chuẩn.

### 12.4. Giới hạn dung lượng bằng file rotation

~~~bash
# Ví dụ tcpdump với rotation theo dung lượng ở Linux lab.
# -C 5: ngưỡng xấp xỉ 5 triệu byte mỗi file (theo tcpdump).
# -W 3: giới hạn số file khi dùng cùng -C; có thể ghi đè vòng.
sudo tcpdump \
  -i lo \
  -nn \
  -s 96 \
  -C 5 \
  -W 3 \
  -w ./lab-rotating.pcap \
  'host 127.0.0.1 and tcp port 443'
~~~

**Không dùng lệnh này cho evidence cần bảo toàn nguyên trạng** khi chưa đánh giá rotation/overwrite. Với `-C` kết hợp `-W`, các phiên bản tcpdump có thể dùng **circular rotation** và ghi đè file cũ. Lệnh trên **không giới hạn thời gian tự thân**; phải có bên ngoài điều khiển thời lượng/stop condition.

Với sự cố an ninh, nên dùng **evidence repository đủ dung lượng, kiểm soát rotation và hash/chain-of-custody** theo runbook; không cho phép một job ghi đè chứng cứ chưa được lưu an toàn.

### 12.5. Đọc file offline mà không in raw payload

~~~bash
# Chỉ đọc PCAP lab đã có, hiển thị summary hai chiều theo filter.
tcpdump -nn -r ./lab-loopback-443.pcap 'tcp port 443'

# Đọc metadata tệp trước khi di chuyển.
ls -lh ./lab-loopback-443.pcap

# Tạo SHA-256 digest để đối chiếu tính toàn vẹn của file.
sha256sum ./lab-loopback-443.pcap
~~~

Lệnh `tcpdump -r` **không tạo thêm packet capture**, nhưng kết quả summary có thể lộ IPs/ports/timestamps. Tránh `-A` hoặc `-X` (ASCII/hex payload dump) khi không thực sự cần và không có quyền xem dữ liệu nội dung.

**Hash không tự mã hóa/khử định danh file.** Hash chỉ giúp nhận biết file được đối chiếu có thay đổi không trong quy trình evidence; nội dung PCAP vẫn phải có access control và encryption phù hợp.

## 13. TShark/Wireshark: không nhầm `-f` và `-Y`

### 13.1. Capture có bounds bằng TShark

~~~bash
# Ví dụ với lab interface lo (Linux).
# -f: capture filter theo libpcap.
# -a duration:30: tự dừng theo thời lượng.
# -c 100: thêm giới hạn packet count.
# -s 96: snaplen (không bảo đảm xóa payload).
tshark \
  -i lo \
  -f 'host 127.0.0.1 and tcp port 443' \
  -a duration:30 \
  -c 100 \
  -s 96 \
  -w ./lab-tshark.pcapng
~~~

Với `-w`, output có thể là **PCAPNG** theo định dạng mặc định/TShark version. Suffix của file không tự chứng minh format; kiểm tra bằng công cụ đọc phù hợp.

### 13.2. Display filter cho file đã thu

~~~bash
# -Y là display filter trên dữ liệu đã có trong file.
# Không làm file gốc nhỏ đi hoặc thay đổi bytes đã capture.
tshark \
  -r ./lab-tshark.pcapng \
  -Y 'tcp.port == 443' \
  -T fields \
  -e frame.time_epoch \
  -e ip.src \
  -e ip.dst \
  -e tcp.srcport \
  -e tcp.dstport
~~~

**Lưu ý:** khi capture bao gồm IPv6, các fields `ip.src`/`ip.dst` dành cho IPv4 có thể trống với IPv6; cần chọn thêm `ipv6.src`/`ipv6.dst` nếu phân tích dual-stack. Exported field output cũng cần bảo vệ vì có thể chứa telemetry định danh endpoint.

### 13.3. Khác biệt cú pháp

| Nhu cầu | Capture filter libpcap | Wireshark/TShark display filter |
|---|---|---|
| TCP port 443 | `tcp port 443` | `tcp.port == 443` |
| Host IPv4 A | `host 192.0.2.10` | `ip.addr == 192.0.2.10` |
| DNS port 53 | `udp port 53 or tcp port 53` | `dns` khi decoder nhận dạng DNS |
| TCP SYN bit | `tcp[tcpflags] & tcp-syn != 0` | `tcp.flags.syn == 1` |
| IPv6 traffic | `ip6` | `ipv6` |

Display filter `dns` có thể dựa vào **dissector nhận dạng protocol**, còn capture filter chỉ biết các byte/header mà bộ lọc hỗ trợ tại điểm thu. Không thay một cách máy móc từ khóa giữa hai hệ thống.

## 14. Những cách hiểu sai về khả năng lọc theo ứng dụng

### 14.1. “Lọc TCP/443 tức là chỉ HTTPS của ứng dụng X”

Sai vì:

- TCP/443 có thể chứa nhiều loại giao thức hoặc tunnel.
- Một ứng dụng có thể dùng HTTPS trên port khác.
- HTTP/3/QUIC thường chạy **UDP/443**, không phải TCP.
- Nhiều website hoặc tenants dùng chung CDN IP.
- NAT/proxy có thể thay đổi endpoint quan sát.

Lọc theo IP/port là **network-level selection**, không tự xác nhận URL, SNI, domain, user hoặc tenant.

### 14.2. “Lọc gói có `not port 22` là an toàn vì không thu SSH”

Một bộ lọc phủ định không làm những packet còn lại tự an toàn. Nó có thể bỏ chứng cứ liên quan incident hoặc giữ những payload khác nhạy cảm hơn. Một số ứng dụng dùng nonstandard ports, tunneling hoặc multiplexing.

**Mặc định nên dùng positive allow filter gắn mục tiêu** hơn là một danh sách `not` dài cố đoán mọi dữ liệu cần bỏ. Ngoại lệ phải được review theo threat model và kiểm thử với traffic mẫu.

### 14.3. “Snaplen nhỏ thì không thu PII”

Sai. IP/MAC, DNS name, TLS metadata và một phần payload đều có thể đủ liên kết tới một con người/thiết bị. `-s 96` không được xem là biện pháp khử định danh.

### 14.4. “PCAP đã mã hóa transport thì có thể chia sẻ”

Sai. Metadata và những protocol khác trong capture có thể nhạy cảm, và keying material/cleartext có thể xuất hiện trên những luồng khác. Cần phân loại PCAP dựa trên **toàn bộ nội dung thực tế**, kiểm soát người xem và thời hạn lưu.

### 14.5. “0 packets = không có giao tiếp”

Chưa đủ bằng chứng. Có thể sai interface, filter không match, traffic qua IPv6/tunnel/hostNetwork, capture path bị drop, hoặc không có positive control. Cần kiểm tra nguồn log/counters độc lập và điểm quan sát khác khi được phép.

## 15. Quản trị dữ liệu PCAP: “thu ít” chưa phải “bảo vệ đủ”

Raw packet capture có thể chứa:

- Địa chỉ IP, MAC, DNS queries, hostname, topology, tên máy và thời gian hoạt động.
- HTTP headers/cookies/URLs hoặc payload từ dịch vụ không mã hóa.
- Dữ liệu ứng dụng, email, tệp truyền và thông tin xác thực khi protocol hoặc cấu hình để lộ.
- Bản ghi mTLS/TLS handshake, certificates, service names và metadata của kết nối.
- Dữ liệu nhiều tenant/người dùng nằm trên cùng một interface, không liên quan ticket.
- Tín hiệu hoạt động có thể liên kết với một người dù payload đã mã hóa.

Vì vậy, **PCAP có thể là dữ liệu nhạy cảm ngay cả sau khi đã dùng capture filter**. Các phương án xử lý phải tương ứng với phân loại bảo mật và quy định của tổ chức.

### 15.1. Vòng đời có kiểm soát

~~~mermaid
flowchart TD
    REQ["Ticket / purpose / scope / owner"] --> REVIEW["Duyệt privacy, filter, location, duration"]
    REVIEW --> CAP["Bounded capture với telemetry drops"]
    CAP --> VERIFY["Kiểm tra file, hash, format, time, completeness"]
    VERIFY --> SEC["Lưu evidence bảo mật, phân quyền, mã hóa"]
    SEC --> ANA["Phân tích bằng bản sao tối thiểu cần thiết"]
    ANA --> REP["Báo cáo được redaction / approved extracts"]
    REP --> RET["Retention / legal hold nếu có"]
    RET --> DEL["Xóa đúng quy trình và kiểm tra bản sao"]
~~~

**Chain of custody** quan trọng nếu PCAP dùng làm chứng cứ điều tra: lưu người tạo, thời điểm, máy/điểm thu, filter, công cụ/phiên bản, hash, lần truy cập và những bản sao/chuyển giao. Một file hash đúng **không chứng minh sensor đã nhìn mọi packet**; nó chứng minh tính nhất quán của bytes được hash tại các thời điểm đối chiếu.

### 15.2. Chọn loại dữ liệu thấp nhất vẫn trả lời được câu hỏi

| Câu hỏi điều tra | Dữ liệu nên ưu tiên | Khi nào cần mở rộng |
|---|---|---|
| Đã có TCP connection tới DB chưa? | Flow logs, SYN/SYN-ACK/RST, firewall counters | Khi cần đo retransmission/timing |
| Vì sao DNS không trả lời? | DNS resolver logs, query/response summaries | Khi cần header DNS hoặc packet timing |
| Có TLS handshake failure? | App/proxy TLS alerts, metadata, bounded capture | Khi cần record-level bằng chứng được phép |
| Có packet loss trên link? | Interface/drop counters, telemetry, bounded header capture | Khi counters không giải thích nguyên nhân |
| Có dữ liệu nhạy cảm đi ra ngoài? | DLP, egress logs, proxy/application audit | Raw payload chỉ theo phê duyệt riêng, không mặc định |
| Giao tiếp Kubernetes Pod nào? | CNI flow verdict, workload identity, service traces | Overlay/Pod PCAP nếu cần và được phép |

**Bắt gói toàn payload không phải bước đầu bắt buộc** trong mọi sự cố. Đối với hệ thống có dữ liệu cá nhân, dữ liệu khách hàng hoặc bí mật, việc dùng application/service telemetry thường giảm rủi ro hơn mà vẫn trả lời được câu hỏi.

### 15.3. Mã hóa, access control và nơi lưu

- Ghi file ở thư mục evidence có **quyền truy cập hạn chế**, không dùng world-readable temporary directory.
- Áp **encryption at rest** cho nơi lưu, quản lý keys phù hợp và TLS cho truyền file.
- Không gửi PCAP trực tiếp vào email/chat/ticket thiếu phân quyền hoặc dịch vụ chia sẻ công khai.
- Không copy PCAP sang máy cá nhân hoặc cloud storage không được phê duyệt.
- Chỉ chia sẻ **trích xuất phù hợp** hoặc kết quả thống kê nếu người nhận không cần raw bytes.
- Có audit truy cập/download và không cho một service account dùng chung quyền xem mọi PCAP.
- Tránh ghi secrets và raw payload vào debug output khi chạy `-A`, `-X` hoặc export fields.

Nếu cần chuyển evidence giữa nhóm, dùng kho có **integrity verification và recipient authorization**. File được nén vẫn chứa dữ liệu gốc; việc nén không thay encryption.

### 15.4. Ẩn danh hóa, pseudonymization và redaction

Việc thay IP bằng một định danh giả có thể hữu ích, nhưng:

- Một IP đã hash vẫn có thể bị suy ra nếu tập địa chỉ nhỏ, có dữ liệu phụ hoặc hash không có khóa.
- DNS names, timestamps, packet size và traffic pattern có thể liên kết về người dùng.
- Redaction payload có thể làm mất thông tin kỹ thuật như checksums, sequence numbers, offsets hoặc làm thay đổi PCAP decode.
- Cần lưu **bản raw được bảo vệ** khi nghiệp vụ/điều tra hợp lệ yêu cầu, còn bản dùng để chia sẻ được rút gọn.
- Phải xác minh công cụ redaction không để sót fields do tunnel, protocol không nhận dạng hoặc packet truncation.

**Không tuyên bố file “anonymous” chỉ vì đã xóa cột IP khỏi bảng export.** Khi cần bảo vệ danh tính, áp privacy review và xác minh tính không thể liên kết theo mục đích sử dụng.

### 15.5. Retention, legal hold và xóa dữ liệu

Một kế hoạch capture cần ghi:

1. **Thời điểm hết hạn lưu** theo mục đích, phân loại và chính sách hiện hành.
2. Chủ sở hữu có quyền quyết định giữ tiếp hoặc xóa.
3. Nơi có bản sao: sensor, analysis workstation, SIEM, ticket, email, backup, object storage.
4. Trường hợp **legal hold** hoặc sự cố an ninh bắt buộc bảo toàn evidence theo quy trình.
5. Cách **xóa/thu hồi quyền** trên môi trường lưu tương ứng và bằng chứng đã hoàn tất.

Không tự xóa chứng cứ đang bị bảo toàn theo quy trình pháp lý/incident response; cũng không giữ PCAP vô hạn vì “biết đâu cần”.

## 16. Thẩm định BPF filter trước khi dùng trên production

### 16.1. Filter review theo nhiều bước

1. **Viết giả thuyết:** ví dụ "TLS connection lỗi giữa API A và DB B".
2. **Vẽ data flow:** client/server IP/port, NAT/VIP, IPv4/IPv6, DNS, tunnel.
3. **Chọn điểm capture:** có nhìn thấy chiều đi/về và chính xác giao thức ở điểm đó?
4. **Viết biểu thức BPF có ngoặc:** tránh mở rộng `or` ngoài ý định.
5. **Compile/syntax check:** ví dụ `tcpdump -d` trên môi trường hỗ trợ, không xem compile PASS là test PASS.
6. **Dùng PCAP lab đã được cho phép:** so các gói dự kiến match và các gói không được phép.
7. **Ước lượng dữ liệu:** packet rate, average caplen, snaplen, time/count/file caps.
8. **Kiểm tra độ nhạy:** metadata/payload có thể chứa những gì, file lưu ở đâu?
9. **Chạy capture ngắn có positive control** và quan sát drop counters.
10. **Review kết quả:** nếu còn thiếu bằng chứng, mở rộng scope theo lý do/owner được phê duyệt.

### 16.2. Kiểm thử biểu thức bằng một PCAP lab có sẵn

Giả sử người học **đã có** file `./approved-lab-traffic.pcap` từ môi trường thuộc quyền:

~~~bash
# Không tạo capture mới, không thay file gốc.
# Chỉ in packet summaries khớp điều kiện.
tcpdump -nn -r ./approved-lab-traffic.pcap \
  'host 192.0.2.10 and (tcp port 443 or udp port 53)'

# Thử biểu thức chặt hơn để so tập kết quả.
tcpdump -nn -r ./approved-lab-traffic.pcap \
  'src host 192.0.2.10 and dst host 198.51.100.20 and tcp dst port 443'
~~~

**Cách đánh giá:** file lab cần có **gói dương tính** (đúng host/protocol/port), **gói âm tính** (host khác, protocol khác, chiều khác), **gói phản hồi** và nếu cần **fragment/IPv6/VLAN/tunnel**. Nếu file không có những mẫu đó, test không thể chứng minh mức coverage mong muốn.

Không lấy kết quả `tcpdump -r` của một file được tạo bằng filter cũ làm **ground truth** cho những loại gói đã bị loại từ đầu.

### 16.3. BPF optimizer không sửa được vấn đề sai mục tiêu

Một biểu thức có thể được compile tối ưu, chạy nhanh và không làm dropped packets, nhưng vẫn **thu nhầm người dùng** hoặc **bỏ sót sự cố** vì IP/port chọn sai. Tính đúng nên được đánh giá theo:

\[
\text{Filter match correctness}
 + \text{capture-point coverage}
 + \text{capture health}
 + \text{data governance}
\]

Đây là một **khung review khái niệm**, không phải công thức cộng điểm bảo mật. Một yếu tố không đạt có thể làm toàn bộ kết luận mất giá trị.

## 17. Ma trận threat modeling: rủi ro khi thu thập packet

| ID | Rủi ro | Điều gì xảy ra? | Kiểm soát và evidence |
|---|---|---|---|
| B01 | **Thu không có mục đích rõ** | Bật full capture “cho chắc” trên network chung | Ticket, purpose, owner, scope approval |
| B02 | **Capture filter OR quá rộng** | `udp port 53` match cả host ngoài phạm vi | Parentheses review, offline test |
| B03 | **Capture sai interface** | Không thấy response/traffic thật | Interface and vantage-point evidence |
| B04 | **Chỉ một chiều packet** | Kết luận nhầm server không trả lời | Both-direction test, reverse-route review |
| B05 | **NAT làm filter sai IP** | Source IP sau SNAT khác host đã chọn | Before/after NAT path documentation |
| B06 | **IPv6 không được xét** | Không thấy luồng dùng Happy Eyeballs/AAAA | Dual-stack probes and filters |
| B07 | **VLAN tag bị strip** | Filter `vlan` không match | DLT/offload review, tagged/untagged examples |
| B08 | **Overlay tunnel** | BPF lọc outer UDP bỏ inner TCP | Encapsulation vantage-point tests |
| B09 | **Fragmentation và ext headers** | Port không nằm trong mọi fragment | Controlled fragment/ICMP observations |
| B10 | **Không thu ICMP PMTUD** | Mất dấu hiệu MTU/packet-too-big | Additional bounded ICMP capture |
| B11 | **Snaplen quá ngắn** | Thiếu fields và handshake bytes | Captured/original lengths, sample review |
| B12 | **Snaplen bị coi là ẩn danh hóa** | Payload/token vẫn nằm trong byte đầu | Sensitive-data review, restricted access |
| B13 | **Mirror drops** | Không thấy packet dù có trên wire | SPAN/TAP/driver drop counters |
| B14 | **NIC offloads** | Checksum sai hoặc large segments giả | Offload awareness, comparison point |
| B15 | **Clock drift** | Kết luận nhầm thứ tự packet ở hai sensors | Clock sync/offset and timestamp review |
| B16 | **Rotation overwrite evidence** | File cũ bị ghi đè trước khi bảo toàn | Rotation design, chain of custody |
| B17 | **PCAP lộ dữ liệu nhạy cảm** | Raw file vào ticket/email/chia sẻ quá rộng | Encryption, RBAC, approved repository |
| B18 | **Hash bị coi là bảo mật dữ liệu** | File chưa mã hóa dù có SHA-256 | Encryption, classification, recipient access |
| B19 | **Redaction chưa đầy đủ** | Tunnel/DNS/metadata còn định danh | Privacy verification, minimized exports |
| B20 | **Retention không kiểm soát** | PCAP tồn tại vô hạn ở nhiều bản sao | Retention schedule, deletion verification |
| B21 | **Packet count quá nhỏ** | Đạt `-c` trước khi lỗi xuất hiện | Time-window design, trigger/context |
| B22 | **Capture quá dài** | Full disk, ảnh hưởng ứng dụng/sensor | Time/count/size caps, monitoring |
| B23 | **Nhầm display với capture filter** | File gốc chứa mọi gói dù màn hình chỉ vài dòng | Compare `-f` / `-Y` semantics |
| B24 | **TLS/QUIC visibility overclaim** | Suy URL/identity từ port hoặc metadata | Protocol-aware scope, app audit corroboration |
| B25 | **Thiếu positive control** | 0 packets được xem là không có kết nối | Known-good flow, path/health checks |
| B26 | **Thu bằng quyền quá rộng** | Cấp privileged container/host admin để debug | Approved capture service, least privilege |

### 17.1. Đánh giá blast radius

Một capture ở **cổng mirror tổng hợp nhiều tenant** có blast radius dữ liệu lớn hơn một capture giới hạn tại host ứng dụng, dù hai nơi dùng cùng cú pháp `tcp port 443`. Một PCAP nhỏ có vài credential plaintext có thể **nhạy cảm hơn** PCAP lớn chỉ chứa network headers.

Đánh giá rủi ro dựa vào **mục đích, quyền quan sát, nội dung, số lượng principal liên quan, thời gian lưu và khả năng phát hiện rò rỉ**, không chỉ MB của file.

## 18. Ma trận kiểm thử BPF và giới hạn capture

Chỉ chạy trên traffic lab/test được ủy quyền; các phép thử có payload giả, địa chỉ tài liệu và không dùng session/token thật.

| ID | Kiểm thử | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | IPv4 client A → server B TCP/443 | Match filter hai host/cổng | Known-good PCAP frames |
| P02 | Server B → client A TCP source port 443 | Match khi dùng `host` và `tcp port` | SYN/ACK/response summary |
| N01 | Host C khác TCP/443 | Không match filter A↔B | Negative sample vs filter |
| N02 | A → B TCP/8443 | Không match filter chỉ 443 | Port comparison |
| P03 | A → resolver UDP/53 trong scope | Match DNS filter được duyệt | DNS sample |
| P04 | A → resolver TCP/53 trong scope | Match khi filter cho cả TCP DNS | DNS TCP sample |
| N03 | DNS của host C khác | Không match nếu filter gắn A đúng ngoặc | Expression diff và counts |
| N04 | `A and tcp443 or udp53` thiếu ngoặc | Review/test phát hiện nhánh DNS quá rộng | Controlled negative sample |
| P05 | SYN/SYN-ACK TCP đúng hai chiều | Hai chiều xuất hiện ở điểm thấy được | Packet flags/timestamps |
| N05 | Filter chỉ `dst port 443` | Nhận diện bỏ response chiều ngược | Reverse packet control |
| N06 | Chỉ IPv4 trên flow IPv6 | Phát hiện không có coverage IPv6 | IPv6 sample / filter test |
| P06 | VLAN-tagged packet được decoder hỗ trợ | Filter phù hợp link type | VLAN tagged PCAP |
| N07 | VLAN offload làm mất tag hiển thị | Không kết luận không có VLAN | NIC/driver metadata |
| N08 | VXLAN/Geneve outer/inner path | Không mặc định `tcp443` match inner packet | Overlay lab comparison |
| N09 | Non-initial IP fragment | Phát hiện filter port không đầy đủ | Fragmented test PCAP |
| P07 | ICMPv6 Packet Too Big lab | Quan sát khi mở rộng scope phù hợp | ICMPv6 and timing evidence |
| N10 | PMTUD ICMP có router source | Không bị loại nhầm khi filter host quá hẹp | Controlled ICMP example |
| P08 | Capture với `-s 96` | File có caplen ≤ 96 | Packet metadata/length |
| N11 | Header dài hơn snaplen | Phân tích nhận diện truncation | Original vs captured length |
| N12 | Packet ngắn có payload bắt đầu trước byte 96 | Không tuyên bố dữ liệu đã ẩn danh | Sanitized training packet |
| P09 | Count/time bounds trong lab | Capture dừng theo điều kiện | Process exit, file and command logs |
| N13 | Không có matching packet | Time limit vẫn bảo đảm dừng | Duration evidence |
| N14 | File rotation bắt đầu overwrite | Thiết kế phát hiện rủi ro mất evidence | Rotation config, file inventory |
| P10 | PCAP offline mở được | Readback/format parse PASS | `tcpdump -r` / TShark parsing |
| N15 | Bị drop ở mirror/kernel | Không gọi capture “đầy đủ” khi có missing data | Drop counters, external control |
| N16 | Nghi checksum lỗi do offload | Đối chiếu packet path trước kết luận lỗi mạng | Offload/alternate capture evidence |
| P11 | TShark `-f` khi capture | File chỉ có gói match phạm vi | File inventory + sample test |
| N17 | TShark `-Y` trên file có sẵn | File gốc vẫn giữ packet không hiển thị | Original hash/size comparison |
| N18 | PCAP chứa dữ liệu test nhạy cảm | Access controls/redaction policy xử lý đúng | Approved storage/access audit |
| P12 | File evidence có hash SHA-256 | Digest tương ứng bytes được bảo toàn | Hash record + transfer verification |
| N19 | Bản copy chia sẻ ngoài phạm vi | Bị ngăn bởi permissions/data policy | RBAC/access denial evidence |
| N20 | Retention hết hạn, không legal hold | Xóa/thu hồi đúng quy trình | Deletion audit/scope |
| P13 | Phân tích TCP summary đủ để trả lời câu hỏi | Không yêu cầu raw payload bổ sung | Root-cause analysis note |

### 18.1. Negative test cần điểm đối chứng

Ví dụ không thấy SYN/ACK trong file:

1. **Known-good control:** một flow tương tự trên sensor đúng vẫn xuất hiện.
2. **BPF review:** filter có giữ được source port 443 cho gói phản hồi không?
3. **Vantage point:** đường về có đi qua NIC/SPAN này không?
4. **Sensor health:** dropped packets, capture truncation, disk/buffer pressure?
5. **Destination health:** server có listening, firewall có deny hoặc ứng dụng không trả?

Chỉ sau các kiểm tra này mới có cơ sở suy luận server không phản hồi trên đường đang quan sát. **Không kết luận từ một khoảng trống dữ liệu thiếu coverage**.

## 19. Troubleshooting: khi filter hoặc PCAP không trả lời được câu hỏi

| Hiện tượng | Giả thuyết cần phân biệt | Kiểm tra không làm mở rộng quyền |
|---|---|---|
| File PCAP rỗng | Không có traffic, sai interface, sai filter, capture không có quyền | Interface inventory, filter offline test, known-good control |
| Chỉ thấy SYN không thấy SYN/ACK | Server/network không phản hồi **hoặc** filter bỏ chiều về | Dùng `host` hai chiều, reverse route, firewall logs |
| Capture TCP/443 nhưng app dùng HTTP/3 | Traffic thật qua UDP/443 | Service/proxy logs, approved UDP capture |
| Không thấy DNS trên port 53 | DoH/DoT, cache hoặc resolver khác | Endpoint resolver settings, DNS/app telemetry |
| Không thấy ICMP “Packet Too Big” | Router ở ngoài host filter, sensor không nằm đúng đường | Bounded ICMP/ICMPv6 scope và routing evidence |
| Không thấy host A sau NAT | Source đã đổi, server nhìn địa chỉ SNAT | NAT/firewall translation table và vantage point |
| VLAN filter không match | NIC strip tag, DLT khác hoặc filter offset sai | Driver/capture metadata và tagged lab sample |
| Pod traffic không match TCP filter trên node NIC | VXLAN/Geneve hoặc traffic nằm ở inner interface | CNI/overlay documentation, controlled inner/outer captures |
| Wireshark báo malformed/truncated | Snaplen không đủ, packet thật lỗi hoặc decoder mismatch | Caplen/original length, DLT, offline parser |
| TCP checksum bị đánh dấu sai | Offloading hoặc packet thực sự lỗi | NIC offload status và alternate vantage point |
| Số TCP segments không giống trên wire | TSO/GSO/GRO/LRO làm gộp/chia segments | Capture point/driver behavior |
| Packet loss dù filter hẹp | Sensor/mirror quá tải, kernel drops, disk I/O | Counters ở tất cả layers và capacity |
| File tăng nhanh dù display filter hẹp | Đã dùng `-Y` thay capture `-f`, hoặc filter quá rộng | Capture command và file sample |
| File bị ghi đè khi đang điều tra | `-C` + `-W` rotation/circular buffer | File naming/rotation policy và evidence hashes |
| PCAP chứa thông tin ngoài phạm vi | Filter match rộng, mixed traffic cùng host/port | Review approval, isolate/store, minimize sharing |
| Không parse được PCAPNG bằng tool cũ | Không tương thích format/interface metadata | Confirm magic/file format, use compatible reader |
| Capture làm đầy disk | Không có time/size cap, rotation không hoạt động | Stop condition, quota, disk monitoring |
| Hai sensor có timestamp lệch | Clock skew, timestamp source khác | NTP/PTP monitoring và offset estimation |
| HTTPS không thấy URL hoặc body | TLS mã hóa, không phải lỗi của BPF | Application/proxy logs trong scope được duyệt |
| Log app nói có request nhưng PCAP không thấy | Sai interface, offload, datapath bypass hoặc BPF filter | Trace/network path/counters correlation |

### 19.1. Quy trình chẩn đoán một capture rỗng

~~~mermaid
flowchart TD
    A["PCAP có 0 packet"] --> B{"Interface và vị trí đúng?"}
    B -->|"Không"| FIX["Sửa capture point theo phê duyệt"]
    B -->|"Có"| C{"Có known-good traffic tại điểm đó?"}
    C -->|"Không rõ"| FLOW["Đối chiếu interface counters / app / flow logs"]
    C -->|"Có"| D{"BPF đúng syntax và match test PCAP?"}
    D -->|"Không"| FIL["Sửa biểu thức có review"]
    D -->|"Có"| E{"Data path có NAT / IPv6 / tunnel / VLAN?"}
    E -->|"Có"| PATH["So outer/inner và source/destination ở vantage point"]
    E -->|"Không"| SENSOR["Kiểm tra permission, backend health, drops, time"]
    FIX --> RET["Thử capture ngắn có bounds"]
    FLOW --> RET
    FIL --> RET
    PATH --> RET
    SENSOR --> RET
~~~

**Không “sửa” PCAP rỗng bằng cách tắt toàn bộ filter và bật capture vô hạn trên interface chia sẻ.** Mở phạm vi theo từng giả thuyết, có giới hạn và ghi nhận lý do.

## 20. Quy trình 10 bước thu thập có trách nhiệm

### Bước 1 — Nêu rõ câu hỏi

Ví dụ: "Từ 14:00–14:05, trên API host A có retransmission hoặc reset TCP khi gọi DB host B qua 5432 không?" Tránh yêu cầu "bắt tất cả traffic để tìm mọi lỗi" nếu chưa có mục tiêu.

### Bước 2 — Xác nhận ủy quyền và privacy review

Ghi ticket, owner, mục tiêu, thời gian, loại hệ thống, phạm vi dữ liệu, retention và người có quyền xem. Trong môi trường multi-tenant hoặc có dữ liệu khách hàng, xác định ranh giới pháp lý/nội bộ trước khi thu.

### Bước 3 — Chọn vị trí, interface và flow

Ghi NIC, network namespace, source/destination, IP version, giao thức, port, NAT/VIP, tunnel và các điểm có thể bị routing bất đối xứng.

### Bước 4 — Chọn nguồn dữ liệu ít nhạy cảm nhất

Thử flow logs, application tracing, CNI verdict, firewall counters hoặc metrics trước. Chỉ raw capture khi câu hỏi cần packet-level details và phạm vi đã được phê duyệt.

### Bước 5 — Viết/review BPF filter

Dùng biểu thức có ngoặc, đúng chiều, host và port. Xác minh có giữ response/ICMP/DNS cần thiết; không dùng `or` thiếu ngoặc hoặc phủ định rộng.

### Bước 6 — Đặt giới hạn và kho lưu

Chọn **time window, packet count, snaplen, file size/rotation**, disk quota, nơi lưu có phân quyền và encryption. Không dùng snaplen làm tuyên bố “đã anonymize”.

### Bước 7 — Kiểm tra lab và positive/negative controls

Biên dịch filter, đọc PCAP mẫu, kiểm tra cả luồng match và non-match. Xem sự khác biệt với NAT/IPv6/VLAN/tunnel nếu liên quan.

### Bước 8 — Thu ngắn và ghi telemetry

Trong thời gian chạy, theo dõi CPU, buffer, disk, packet/drop counters và service SLO. Nếu ảnh hưởng hệ thống hoặc dữ liệu vượt phạm vi, dừng theo runbook.

### Bước 9 — Xác minh file và phân tích trên bản sao

Đọc lại file PCAP/PCAPNG, lưu exact command/filter, source capture, hash SHA-256, timestamps và missing-packet caveats. Chia sẻ chỉ trích xuất/nhận định cần thiết thay vì raw payload.

### Bước 10 — Kết luận có mức độ tin cậy và cleanup

Nêu rõ **điều đã thấy**, **điều chưa thể chứng minh**, giới hạn của capture và dữ liệu cần thêm nếu có. Áp retention/legal hold và xóa các bản sao không cần thiết theo quy trình.

## 21. Bài tập tình huống: DNS, HTTPS và MTU trên mạng hybrid

**Bối cảnh giả định:**

Ứng dụng `orders-api` tại site A đôi lúc không kết nối được tới service `payments-api` ở cloud. Luồng đi qua VPN và một gateway NAT. Người vận hành đặt capture trên NIC của server Orders và dùng:

~~~text
# Filter ban đầu được đưa ra để REVIEW; chưa chạy.
src host 192.0.2.10 and tcp dst port 443
~~~

File thu được có nhiều SYN nhưng không có SYN/ACK. Team kết luận "Payments API không bao giờ trả lời". Sau đó đội network thấy client có thể thử HTTP/3 trên UDP/443, gateway VPN có một đường MTU không đồng nhất, và địa chỉ nguồn ở phía cloud đã bị SNAT sang địa chỉ khác.

### 21.1. Những điểm cần kiểm tra lại

| Dấu hiệu | Câu hỏi đúng | Tại sao kết luận ban đầu yếu |
|---|---|---|
| Chỉ thấy SYN outbound | Filter có giữ inbound SYN/ACK/RST không? | `src host A and tcp dst port 443` loại chiều ngược |
| Không thấy UDP/443 | Ứng dụng/gateway có dùng QUIC không? | Filter chỉ chọn TCP |
| Không thấy ICMP | Có PMTUD failure, router source khác không? | Filter chỉ giữ host A và TCP |
| Server cloud không thấy source A | NAT translation thay source IP? | Filter theo IP trước NAT ở cloud sẽ sai |
| Có packet loss trong VPN | Capture trước/ngoài tunnel hay sau encapsulation? | Inner TCP có thể nằm trong outer UDP/ESP |
| PCAP nhỏ sau snaplen | Có bị cắt field cần thiết không? | Caplen không bảo đảm đủ header |
| File không chứa dữ liệu user | Đã kiểm tra payload/metadata nhạy cảm chưa? | Snaplen không tự anonymize |

### 21.2. Câu hỏi thực hành

1. Viết BPF filter **hai chiều** cho TCP/443 giữa client A và server B ở điểm capture trước NAT.
2. Viết filter bao gồm **TCP/443 và UDP/443** cho một host đã phê duyệt.
3. Vì sao cần **một phiên ICMP/ICMPv6 có scope riêng** khi nghi PMTUD?
4. Nếu sau SNAT source IP đã thay, cần thêm evidence gì để liên hệ hai capture points?
5. Vì sao capture ở NIC có tunnel **không thể luôn match inner TCP port 443**?
6. So sánh `-s 96` và `-s 0` về mức chi tiết và rủi ro dữ liệu.
7. Viết ba negative tests chứng minh filter không thu host ngoài scope và vẫn giữ chiều phản hồi.
8. Nếu `tcpdump` báo drops, có được kết luận server không gửi packet không?
9. Đề xuất kho lưu, phân quyền, hash, retention và cách chia sẻ kết quả không lộ PCAP.
10. Nêu ít nhất ba điều một PCAP tại client **không thể khẳng định** nếu thiếu logs/capture ở server hoặc gateway.

### 21.3. Hướng giải minh họa

~~~text
# Hai chiều cho TCP/443 giữa hai host tại điểm trước NAT.
host 192.0.2.10 and host 198.51.100.20 and tcp port 443

# Gồm TCP/443 và UDP/443 liên quan client A.
host 192.0.2.10 and (tcp port 443 or udp port 443)
~~~

Giải thích:

- `host A and host B` match cả hai chiều nếu gói còn đúng địa chỉ ở điểm thu và không bị các hạn chế protocol/header đã nêu.
- `src host A and tcp dst port 443` có thể bỏ **phản hồi** từ B.
- ICMP lỗi có thể do **router trung gian** phát ra; cần xác định scope theo giao thức, interface và thời gian thay vì filter phụ thuộc source A.
- Với VPN, cần phân biệt **outer ESP/UDP tunnel** và **inner TCP/UDP flow**; áp đúng filter ở đúng point.
- Với NAT, liên kết evidence theo **flow translation logs, timestamps, 5-tuple** và các source/destination đã dịch.
- `-s 0` trên nhiều phiên bản tcpdump yêu cầu full capture/snaplen tối đa phù hợp, dễ tăng rủi ro lưu payload; **không chọn full capture nếu chỉ cần header**. `-s 96` có thể thiếu dữ liệu cần phân tích hoặc vẫn chứa byte nhạy cảm.
- Negative tests cần host C ngoài scope, chiều reverse B→A, protocol/port khác; một test deny cần positive control cho traffic tương ứng.
- Packet drops hoặc thiếu chiều capture khiến kết luận "server không trả lời" **chưa đủ tin cậy**.
- Không gửi raw PCAP vào ticket nếu một bản ghi flow/timing đã đủ. Lưu raw theo chính sách, chia sẻ trích xuất được redaction, hash và quản lý retention.

## 22. Checklist BPF filter và giới hạn dữ liệu thu thập

- [ ] Đã xác định câu hỏi kỹ thuật, owner, approval, ứng dụng và khoảng thời gian.
- [ ] Đã cân nhắc flow logs, app tracing, firewall/CNI counters trước khi chọn raw packet capture.
- [ ] Đã xác định đúng interface, network namespace, sensor và routing/NAT vantage point.
- [ ] Biết **capture filter** khác **display filter**; `tcpdump` expression khác Wireshark `tcp.port == 443`.
- [ ] Biết cBPF/libpcap capture filtering khác các chương trình eBPF/XDP/security policy khác.
- [ ] Đã đặt ngoặc cho `and`/`or`/`not`, kiểm tra nguồn/đích và các nhánh OR.
- [ ] Filter theo host/net/protocol/port/port range đúng nhiệm vụ, tránh capture ngoài scope.
- [ ] Có giữ **hai chiều request/response** nếu phân tích handshake/retransmission.
- [ ] Đã đánh giá DNS, ICMP/ICMPv6, UDP/443 QUIC và cổng khác nếu sự cố liên quan.
- [ ] Đã đánh giá IPv4/IPv6, dual-stack resolver và Happy Eyeballs khi phù hợp.
- [ ] Đã kiểm tra tác động của NAT/SNAT/DNAT, proxy, Service VIP, asymmetric routing.
- [ ] Đã xem xét VLAN/QinQ tags, NIC offloads, outer/inner tunnel và link type.
- [ ] Đã cân nhắc fragmentation/IPv6 extension headers và giới hạn port matching.
- [ ] Không kỳ vọng BPF classic stateful tracking, L7 identity, TLS decryption hoặc firewall enforcement.
- [ ] Đã có known-good traffic và negative samples để test biểu thức trước khi thu.
- [ ] Đã kiểm tra syntax/compiler và hiểu compile PASS không chứng minh filter đúng logic.
- [ ] Có **time bound** ngoài packet count; không để capture vô hạn khi không có match.
- [ ] Có `snaplen` phù hợp mục tiêu, biết cắt packet có thể còn payload/PII.
- [ ] Có file size/rotation/disk quota và không để rotation overwrite evidence cần bảo toàn.
- [ ] Dùng `-nn` để giảm DNS resolution khi hiển thị, nhưng không coi nó là ẩn danh hóa PCAP.
- [ ] Có telemetry về packet/drop counters, NIC/mirror drops, CPU/disk pressure và clock sync.
- [ ] Phân biệt filter exclusion, packet truncation, offload artifact và actual packet loss.
- [ ] PCAP/PCAPNG được đọc lại bằng công cụ tương thích, có final newline cho tài liệu đi kèm.
- [ ] Evidence có source, timestamps, exact filter/command, file metadata, hash và custody nếu cần.
- [ ] Raw PCAP được mã hóa và phân quyền theo độ nhạy, không đưa lên chat/ticket công khai.
- [ ] Chỉ trích xuất/share những fields cần thiết; không tự tuyên bố anonymous từ snaplen hoặc IP hashing.
- [ ] Có retention, legal hold, bản sao và deletion plan rõ ràng.
- [ ] Người vận hành có quyền capture đúng phạm vi; không bật privileged container hoặc host access tùy tiện.
- [ ] Có positive/negative test và điểm đối chứng trước khi kết luận packet thực sự không tồn tại.
- [ ] Khi không đủ evidence, ghi hạn chế và đề xuất thu bổ sung **có scope**, không tự mở full capture.

**Ghi nhớ:** **BPF capture filter quyết định packet nào được đưa vào tập dữ liệu bắt gói; nó không phải firewall, không tái lắp ráp traffic, không giải mã TLS và không tự khử dữ liệu nhạy cảm.** Một phiên capture đáng tin cần **đúng điểm quan sát, filter logic chính xác, giới hạn thời gian/số gói/snaplen/dung lượng, quan sát drops và offload, cùng bảo mật PCAP từ lúc tạo tới khi xóa**. Mục tiêu không phải file lớn nhất hay nhỏ nhất, mà là **bằng chứng đủ để trả lời câu hỏi, có thể kiểm chứng và không thu thập dữ liệu vượt nhu cầu được phép**.
