# MTU, packet loss và độ trễ trong giao tiếp giữa workload

Hai máy ảo có thể nằm trong cùng một VPC/VNet, có route và security rule hợp lệ nhưng vẫn giao tiếp chậm, chập chờn hoặc thất bại với một số loại dữ liệu. Nguyên nhân có thể nằm ở MTU không phù hợp, gói tin bị mất, đường truyền bị nghẽn, độ trễ tăng hoặc thiết bị trung gian xử lý gói tin khác với dự kiến.

Khi vận hành workload trên cloud, cần hiểu kích thước gói tin, cơ chế phân mảnh, Path MTU Discovery, ảnh hưởng của packet loss và cách đo độ trễ. Những kiến thức này giúp chẩn đoán lỗi như kết nối TCP treo khi truyền payload lớn, API có p99 cao, VPN hoạt động với request nhỏ nhưng thất bại với file lớn hoặc throughput thấp dù băng thông danh nghĩa cao.

## 1. MTU là gì?

**MTU (Maximum Transmission Unit)** là kích thước tối đa của một gói dữ liệu ở lớp mạng mà một giao diện hoặc liên kết có thể chuyển tiếp trong một lần truyền mà không cần phân mảnh ở lớp IP. Trong mạng IP trên Ethernet, MTU thường được hiểu là kích thước tối đa của IP packet, không bao gồm Ethernet header và frame overhead.

Ethernet thông thường thường dùng IP MTU 1500 byte. Một số môi trường hỗ trợ jumbo frame với MTU lớn hơn, chẳng hạn khoảng 9000 byte hoặc giá trị gần đó. Con số chính xác phụ thuộc thiết bị, nền tảng cloud, loại instance và đường đi end-to-end. Không nên giả định mọi NIC, subnet, gateway, VPN, peering hoặc dịch vụ trung gian đều hỗ trợ cùng một MTU.

MTU ảnh hưởng đến số lượng gói cần gửi để truyền một lượng dữ liệu nhất định:

- MTU nhỏ hơn làm một luồng dữ liệu cần nhiều packet hơn, tăng số header và công việc xử lý packet.
- MTU lớn hơn có thể giảm số packet và overhead trên đường truyền, nhưng chỉ có lợi khi toàn bộ path hỗ trợ kích thước đó.
- Nếu packet vượt quá MTU của một hop, gói có thể bị phân mảnh theo cơ chế IP, bị loại bỏ hoặc cần nguồn gửi giảm kích thước.

Phân biệt MTU với kích thước Ethernet frame. Nếu IP MTU là 1500 byte, Ethernet frame còn có header và trailer riêng. Vì vậy, khi đọc thông số NIC hoặc công cụ capture, hãy xác định thông số đang nói đến IP packet, Ethernet frame hay payload của giao thức ứng dụng.

## 2. MTU, MSS và kích thước payload

MTU giới hạn kích thước IP packet. Với TCP, hai đầu kết nối trao đổi **MSS (Maximum Segment Size)** để giới hạn lượng dữ liệu TCP trong mỗi segment. MSS không bao gồm IP header và TCP header.

Trong trường hợp đơn giản, không có IP option hoặc TCP option:

\[
\text{MSS} = \text{Path MTU} - \text{IP header} - \text{TCP header}
\]

Ví dụ với IPv4 MTU 1500 byte, IPv4 header 20 byte và TCP header cơ bản 20 byte:

\[
1500 - 20 - 20 = 1460\text{ byte}
\]

Với IPv6 cơ bản, IP header là 40 byte, nên cùng MTU 1500 byte và TCP header cơ bản 20 byte cho MSS 1440 byte. TCP options như timestamp chiếm thêm header trong packet thực tế; TCP điều chỉnh dữ liệu segment để không vượt giới hạn packet.

MSS được thương lượng trong TCP handshake theo từng chiều. Tuy nhiên, MSS advertisement không tự khám phá chính xác mọi MTU trên đường đi. Nếu path có MTU thấp hơn MTU của hai đầu, Path MTU Discovery hoặc một cơ chế điều chỉnh tương đương vẫn cần hoạt động.

Với UDP, ứng dụng tự chọn kích thước datagram. UDP không có cơ chế thương lượng MSS như TCP và bản thân UDP không tự truyền lại datagram bị mất. Ứng dụng dùng UDP cần cân nhắc MTU path, kích thước datagram và cơ chế phục hồi ở tầng ứng dụng. Gửi datagram quá lớn có thể gây phân mảnh IP hoặc bị loại bỏ trên một số đường truyền.

## 3. Phân mảnh IP và Path MTU Discovery

Một đường truyền có thể gồm nhiều hop: NIC của máy nguồn, mạng ảo, gateway, thiết bị bảo mật, tunnel VPN, mạng đích và NIC máy nhận. MTU nhỏ nhất trên đường đi quyết định **Path MTU (PMTU)**:

\[
\text{PMTU} = \min(\text{MTU của từng hop trên đường đi})
\]

Nếu nguồn gửi packet lớn hơn PMTU, packet cần được xử lý theo quy tắc của phiên bản IP và các cờ liên quan.

### IPv4

IPv4 có thể phân mảnh packet tại nguồn hoặc tại router trung gian nếu packet vượt MTU của hop và cờ Don't Fragment (DF) không được bật. Các fragment được ghép lại ở đích. Nếu một fragment bị mất, toàn bộ datagram ban đầu không thể được tái lắp ráp đầy đủ.

Phân mảnh làm tăng overhead và có thể giảm hiệu quả truyền dữ liệu. Một số firewall, NAT hoặc thiết bị mạng có thể xử lý fragment khác nhau hoặc loại bỏ fragment vì lý do bảo mật, giới hạn tài nguyên hay cấu hình. Nếu bật DF, router không được phân mảnh packet; thay vào đó, router có thể gửi ICMP báo cần giảm kích thước packet.

### IPv6

Router IPv6 không phân mảnh packet khi chuyển tiếp. Nếu packet quá lớn so với MTU của link kế tiếp, router loại bỏ packet và gửi ICMPv6 Packet Too Big để nguồn điều chỉnh. Nguồn có thể phân mảnh packet IPv6 bằng Fragment header khi cần, nhưng việc này do node nguồn thực hiện.

### Path MTU Discovery

Path MTU Discovery (PMTUD) cho phép nguồn phát hiện MTU phù hợp trên đường đi. Với IPv4, cơ chế truyền thống dựa vào packet có DF và ICMP Destination Unreachable, fragmentation needed. Với IPv6, PMTUD dựa vào ICMPv6 Packet Too Big.

Quy trình khái quát:

1. Nguồn gửi packet có kích thước phù hợp với MTU mà nó đang giả định.
2. Nếu packet quá lớn ở một hop, thiết bị không thể chuyển tiếp sẽ loại bỏ packet và gửi thông báo ICMP thích hợp.
3. Nguồn nhận thông báo, giảm kích thước packet hoặc cập nhật PMTU cache.
4. Luồng tiếp tục với kích thước phù hợp hơn.

Nếu ICMP cần thiết bị chặn trên đường đi, thông báo không đến được nguồn. Khi đó, packet nhỏ có thể đi qua nhưng packet lớn bị loại bỏ, tạo hiện tượng **PMTU black hole**. Với TCP, ứng dụng có thể kết nối và trao đổi một ít dữ liệu nhưng bị treo khi truyền response lớn. Với IPv6, chặn ICMPv6 Packet Too Big có thể làm hỏng PMTUD và ảnh hưởng nghiêm trọng đến kết nối.

Không nên chặn toàn bộ ICMP/ICMPv6 theo một chính sách chung. Hãy cho phép những loại ICMP cần thiết theo khuyến nghị của nền tảng và chính sách bảo mật, đồng thời giới hạn các loại thông điệp khác nếu có yêu cầu.

## 4. MTU trong mạng cloud và tunnel

Trong cloud, packet có thể đi qua nhiều lớp mạng ảo và encapsulation nội bộ của nhà cung cấp. Người dùng thường không nhìn thấy toàn bộ hạ tầng vật lý, nhưng vẫn phải tuân theo MTU mà dịch vụ công bố cho NIC và đường kết nối.

Các điểm cần chú ý:

- **NIC và loại instance:** MTU tối đa có thể khác theo loại instance, driver, enhanced networking hoặc dịch vụ mạng.
- **VPC/VNet và subnet:** khả năng dùng jumbo frame có thể phụ thuộc nền tảng và loại lưu lượng; subnet không phải lúc nào cũng là nơi cấu hình MTU.
- **Peering và transit:** các đường đi qua dịch vụ trung chuyển có thể có giới hạn khác đường nội bộ trực tiếp.
- **VPN/IPsec:** encapsulation thêm outer IP, UDP, ESP hoặc header khác, làm giảm phần payload bên trong có thể truyền mà không vượt MTU bên ngoài.
- **Overlay network:** VXLAN, Geneve hoặc cơ chế encapsulation khác thêm header, nên MTU của workload cần chừa phần overhead.
- **Internet và đối tác:** không kiểm soát được MTU của mọi mạng ngoài cloud; không giả định jumbo frame end-to-end.

Với tunnel, kích thước hiệu dụng của packet bên trong thường nhỏ hơn MTU của đường truyền bên ngoài. Overhead chính xác phụ thuộc IPv4 hay IPv6, chế độ tunnel, thuật toán bảo mật, NAT-T và tùy chọn encapsulation. Không nên trừ một con số cố định cho mọi VPN. Hãy lấy MTU/MSS được nhà cung cấp hoặc thiết bị VPN khuyến nghị, rồi kiểm thử từ hai đầu tunnel.

Một nguyên tắc thực tế là chọn MTU theo path có giới hạn thấp nhất mà workload phải đi qua. Nếu ứng dụng giao tiếp cả trong mạng nội bộ jumbo và qua VPN có MTU thấp, có thể cần MTU phù hợp cho interface hoặc route riêng, MSS clamping trên gateway, hoặc thiết kế tách đường truyền để tránh một luồng đi qua path không tương thích.

## 5. Packet loss là gì và gây ảnh hưởng ra sao?

**Packet loss** xảy ra khi packet được gửi nhưng không đến được đích hoặc không được xử lý thành công ở tầng mạng. Nguyên nhân có thể gồm:

- Congestion làm hàng đợi tại NIC, switch, router hoặc gateway đầy.
- Giới hạn packet-per-second (PPS), bandwidth hoặc quota của instance/gateway.
- Lỗi vật lý hoặc lỗi interface, driver, virtual NIC hay thiết bị trung gian.
- Firewall, ACL, route hoặc NAT loại bỏ packet.
- MTU không phù hợp, fragment bị mất hoặc ICMP cần thiết bị chặn.
- CPU guest hoặc host quá tải khiến packet không được xử lý kịp.
- Wi-Fi, Internet công cộng hoặc đường truyền đối tác có chất lượng không ổn định.

Packet loss tác động khác nhau theo giao thức. TCP phát hiện mất dữ liệu qua ACK, duplicate ACK hoặc timeout rồi truyền lại. Việc truyền lại làm tăng độ trễ và kích hoạt cơ chế congestion control, thường khiến TCP giảm tốc độ gửi để tránh làm nghẽn mạng hơn. Vì vậy, một tỷ lệ mất packet nhỏ cũng có thể làm throughput giảm đáng kể trên đường truyền có RTT cao.

UDP không tự truyền lại. Ứng dụng có thể mất datagram, âm thanh/video bị giật hoặc telemetry bị thiếu mẫu. Nếu ứng dụng cần độ tin cậy trên UDP, nó phải tự thiết kế sequence number, timeout, retransmission hoặc cơ chế sửa lỗi phù hợp.

Không phải mọi packet bị drop đều là lỗi. Firewall có thể chủ động loại bỏ lưu lượng không được phép; ICMP echo có thể bị giới hạn; một số metric có thể ghi nhận packet bị loại theo chính sách. Cần đối chiếu packet loss với loại traffic, interface counter, flow log, firewall log và metric tại hai đầu.

## 6. Độ trễ: latency, RTT và jitter

**Latency** là thời gian để dữ liệu đi từ nguồn tới đích. Trong vận hành, thường đo **RTT (Round-Trip Time)**, tức thời gian từ khi gửi packet đến khi nhận phản hồi. RTT bao gồm đường đi và đường về, nên không nhất thiết bằng hai lần one-way latency nếu hai chiều có route khác nhau.

Độ trễ có thể gồm nhiều thành phần:

\[
\text{Latency} \approx \text{Propagation} + \text{Serialization} + \text{Queueing} + \text{Processing}
\]

- **Propagation delay:** thời gian tín hiệu truyền qua khoảng cách vật lý; phụ thuộc khoảng cách và môi trường truyền.
- **Serialization delay:** thời gian đưa toàn bộ packet lên đường truyền; packet lớn hoặc tốc độ link thấp làm thành phần này tăng.
- **Queueing delay:** thời gian chờ trong hàng đợi khi có congestion hoặc burst traffic.
- **Processing delay:** thời gian router, firewall, host hoặc ứng dụng xử lý packet.

Latency trung bình thấp chưa chắc đảm bảo trải nghiệm ổn định. Cần xem phân vị p50, p95 và p99 để nhận ra đuôi độ trễ. **Jitter** là mức biến động độ trễ giữa các packet hoặc các lần đo; jitter cao đặc biệt ảnh hưởng đến voice, video và giao thức thời gian thực.

Độ trễ ứng dụng còn bao gồm thời gian xử lý tại server, chờ thread pool, database, cache và các dịch vụ phụ thuộc. Nếu ping giữa hai máy thấp nhưng API vẫn chậm, hãy đo riêng DNS, thiết lập kết nối, TLS handshake, thời gian xử lý server và các lời gọi phụ thuộc.

## 7. Mối quan hệ giữa bandwidth, RTT và throughput

Bandwidth là năng lực truyền dữ liệu tối đa của đường truyền trong điều kiện nhất định. Throughput là tốc độ dữ liệu thực tế ứng dụng đạt được. Hai giá trị không giống nhau: throughput có thể thấp hơn bandwidth do packet loss, congestion, giới hạn PPS, cửa sổ TCP, CPU, mã hóa, disk I/O hoặc server xử lý chậm.

Một khái niệm hữu ích là **Bandwidth-Delay Product (BDP)**, lượng dữ liệu cần đang “trên đường truyền” để lấp đầy một đường truyền có băng thông và RTT nhất định:

\[
\text{BDP (bit)} = \text{Bandwidth (bit/s)} \times \text{RTT (s)}
\]

Ví dụ, đường truyền 1 Gbit/s với RTT 40 ms có BDP:

\[
1.000.000.000 \times 0,04 = 40.000.000\text{ bit}
\]

Tương đương khoảng 5 MB dữ liệu đang truyền. Nếu TCP receive window hoặc congestion window nhỏ hơn nhiều so với BDP, kết nối có thể không tận dụng hết băng thông dù không có packet loss.

Khi throughput thấp, không nên lập tức tăng băng thông instance. Hãy xác định bottleneck bằng cách đo đồng thời RTT, retransmission, window, CPU, PPS, NIC throughput và hiệu năng ứng dụng. Một luồng TCP đơn lẻ cũng có thể không đạt tốc độ tối đa của nhiều luồng tổng hợp.

## 8. Jumbo frame: lợi ích và giới hạn

Jumbo frame là Ethernet frame có kích thước lớn hơn frame Ethernet tiêu chuẩn. Trong nhiều môi trường, người ta dùng thuật ngữ này cho IP MTU khoảng 9000 byte, nhưng định nghĩa và giá trị hỗ trợ không đồng nhất giữa các nền tảng.

Lợi ích tiềm năng:

- Ít packet hơn để truyền cùng lượng dữ liệu.
- Giảm overhead header và số lần xử lý packet ở một số workload.
- Có thể cải thiện hiệu quả với truyền dữ liệu lớn, storage network hoặc luồng nội bộ có throughput cao.

Giới hạn và rủi ro:

- Mọi hop trên path cần hỗ trợ kích thước tương ứng; một hop MTU thấp có thể làm packet bị drop hoặc phân mảnh.
- Không phải tất cả dịch vụ cloud, Internet gateway, VPN, load balancer hoặc endpoint đều hỗ trợ jumbo.
- MTU lớn không giải quyết congestion, packet loss do PPS limit hay latency do khoảng cách.
- Một số ứng dụng gửi datagram lớn hoặc overlay cần điều chỉnh MTU riêng.

Chỉ bật jumbo frame khi nhà cung cấp xác nhận path hỗ trợ và đã kiểm thử end-to-end. Không tăng MTU trên một NIC đơn lẻ rồi kỳ vọng mọi kết nối đều nhanh hơn.

## 9. Đo MTU và kiểm tra PMTU

Có thể kiểm tra MTU của interface trong guest OS, sau đó kiểm tra kích thước packet lớn nhất đi qua path. Hai phép đo này trả lời hai câu hỏi khác nhau: MTU cục bộ đang đặt bao nhiêu và PMTU thực tế giữa hai endpoint là bao nhiêu.

### Linux

Xem địa chỉ và MTU của interface:

```bash
ip -br link
ip link show dev eth0
```

Thử IPv4 packet không phân mảnh với `ping`:

```bash
ping -4 -M do -s 1472 -c 4 10.20.16.25
```

Với IPv4 header 20 byte và ICMP header 8 byte, payload 1472 byte tạo packet IP 1500 byte. Nếu path MTU nhỏ hơn và DF được đặt, lệnh có thể nhận thông báo cần phân mảnh hoặc timeout. Hạ dần payload để tìm kích thước phù hợp, nhưng hãy xác nhận ICMP không bị chặn và đích phản hồi echo.

`tracepath` có thể hỗ trợ phát hiện PMTU trên đường đi:

```bash
tracepath 10.20.16.25
```

Kết quả phụ thuộc thiết bị trung gian và loại ICMP được phép. Không phải mọi router đều cung cấp đủ thông tin cho tracepath.

### Windows

Xem cấu hình interface:

```powershell
Get-NetIPInterface | Format-Table InterfaceAlias,AddressFamily,NlMtu
```

Thử IPv4 packet với DF:

```powershell
ping -f -l 1472 10.20.16.25
```

Tham số `-f` đặt Don't Fragment và `-l` đặt kích thước payload ICMP. Cũng cần tính 20 byte IPv4 header và 8 byte ICMP header khi suy ra kích thước IP packet.

Các lệnh trên là ví dụ; thay interface và địa chỉ đích bằng endpoint thực tế. ICMP echo có thể bị chặn hoặc rate limit, vì vậy ping thất bại không tự chứng minh path bị packet loss. Khi cần, kiểm tra bằng TCP connection hoặc công cụ đo chuyên dụng.

## 10. Đo packet loss, latency và throughput

Đo từ nhiều điểm giúp khoanh vùng vấn đề. Nên chạy phép đo từ workload nguồn đến workload đích, từ mỗi máy đến gateway và tới một endpoint kiểm soát được. Ghi lại thời điểm, vùng/AZ, loại instance, interface và hướng lưu lượng để so sánh.

| Công cụ | Mục đích | Giới hạn cần biết |
|---|---|---|
| `ping` | RTT và tỷ lệ echo reply bị mất | ICMP có thể bị chặn hoặc ưu tiên thấp hơn traffic ứng dụng |
| `traceroute` / `tracert` | Quan sát các hop và thời gian phản hồi từng hop | Một số hop không trả lời; route có thể bất đối xứng |
| `mtr` / `pathping` | Theo dõi loss và latency theo hop trong nhiều mẫu | Loss ở hop trung gian nhưng không ở đích có thể do rate limit ICMP |
| `tracepath` | Kiểm tra đường đi và PMTU trên Linux | Phụ thuộc hỗ trợ ICMP của path |
| `iperf3` | Đo TCP/UDP throughput giữa hai endpoint kiểm soát được | Cần chọn đúng số luồng, hướng, thời gian và tránh làm ảnh hưởng production |
| `ss` / `netstat` | Xem socket, retransmission hoặc trạng thái kết nối | Không thay thế phép đo end-to-end |
| Cloud metrics / flow logs | Quan sát throughput, drop, error và traffic theo interface hoặc luồng | Tên metric và độ chi tiết khác nhau theo nhà cung cấp |

Ví dụ đo throughput với `iperf3` trong môi trường thử nghiệm:

```bash
# Tren may dich
iperf3 -s

# Tren may nguon, do TCP trong 30 giay
iperf3 -c 10.20.16.25 -t 30

# Thu nhieu luong TCP de so sanh
iperf3 -c 10.20.16.25 -t 30 -P 4
```

Chỉ chạy server `iperf3` trên cổng được cho phép trong một mạng thử nghiệm hoặc cửa sổ kiểm thử có kiểm soát. Nhiều luồng có thể tạo tải lớn và không đại diện cho một kết nối ứng dụng thực tế. Khi đo UDP, đặt bitrate phù hợp và theo dõi jitter/loss; không gửi ở tốc độ cao hơn khả năng đường truyền.

## 11. Chẩn đoán một số triệu chứng thường gặp

### Kết nối thành công nhưng truyền dữ liệu lớn bị treo

Khả năng cần kiểm tra đầu tiên là PMTU black hole hoặc MSS không phù hợp. Packet nhỏ và TCP handshake có thể đi qua, trong khi packet dữ liệu lớn bị drop. Kiểm tra MTU interface, thử DF với nhiều kích thước, xác nhận ICMP fragmentation-needed hoặc Packet Too Big được phép quay về nguồn và kiểm tra tunnel overhead. Nếu path đi qua VPN, đối chiếu MTU/MSS theo khuyến nghị của thiết bị hoặc nhà cung cấp.

### Ping có loss nhưng ứng dụng không có lỗi tương ứng

Một số thiết bị ưu tiên thấp hoặc giới hạn ICMP echo trong khi vẫn chuyển tiếp TCP/UDP bình thường. So sánh ping với packet loss ở tầng ứng dụng, TCP retransmission, flow log và đo tới endpoint cuối. Nếu loss chỉ xuất hiện ở một hop trung gian nhưng hop cuối không mất packet, có thể đó là rate limit phản hồi ICMP của router.

### RTT tăng vào giờ cao điểm

Kiểm tra queueing delay, throughput, PPS, CPU, NIC drop và giới hạn gateway. Nếu RTT tăng cùng với mức sử dụng đường truyền cao, congestion có thể là nguyên nhân. Nếu RTT tăng nhưng bandwidth thấp, xem xét CPU host, firewall inspection, route thay đổi hoặc dịch vụ phụ thuộc bị chậm.

### Throughput TCP thấp trên đường truyền RTT cao

Kiểm tra packet retransmission, congestion window, receive window và socket buffer. Dùng BDP để đánh giá lượng dữ liệu cần in-flight. Thử một luồng và nhiều luồng riêng biệt trong môi trường kiểm soát. Nếu nhiều luồng đạt tổng throughput cao nhưng một luồng thấp, cần xem TCP window, congestion control và đặc điểm ứng dụng.

### UDP bị mất dữ liệu hoặc jitter cao

Kiểm tra bitrate gửi, PPS, queue drop và khả năng xử lý packet ở máy nhận. Xác nhận ứng dụng có sequence number, buffer jitter hoặc cơ chế phục hồi phù hợp. UDP không tự retransmit, nên chỉ tăng MTU hoặc băng thông không xử lý được mọi nguyên nhân mất datagram.

## 12. Tối ưu MTU và mạng cho workload

Không có một giá trị MTU tối ưu cho mọi workload. Cần chọn theo đường đi thực tế, loại traffic và yêu cầu tương thích.

| Workload | Điều cần ưu tiên |
|---|---|
| API web qua Internet | MTU tương thích rộng, PMTUD hoạt động, TCP retransmission và p95/p99 ổn định |
| Giao tiếp nội bộ giữa VM cùng mạng cloud | Xác nhận hỗ trợ jumbo end-to-end trước khi tăng MTU; theo dõi PPS và throughput |
| Database replication hoặc backup | Throughput ổn định, loss thấp, RTT phù hợp và MTU nhất quán trên mọi node |
| VPN site-to-site | Tính overhead tunnel, chọn MTU/MSS phù hợp và cho phép ICMP cần thiết |
| Voice/video hoặc realtime UDP | Jitter, packet loss, queueing delay và kích thước datagram phù hợp |
| Overlay/container network | Tính overhead encapsulation như VXLAN/Geneve và giảm MTU workload tương ứng |

Các bước tối ưu có thể thực hiện theo thứ tự:

1. Xác định endpoint, protocol, hướng lưu lượng và các hop mà traffic đi qua.
2. Đo MTU hiện tại trên NIC và PMTU end-to-end.
3. Kiểm tra ICMP cần thiết, firewall, VPN và overlay overhead.
4. Đo baseline RTT, loss, retransmission, throughput, PPS và interface drops.
5. Thay đổi MTU/MSS hoặc route trong môi trường thử nghiệm trước.
6. Kiểm tra cả packet nhỏ, packet lớn, TCP và UDP nếu workload sử dụng.
7. Triển khai theo từng nhóm máy, theo dõi metric và có kế hoạch rollback.

Tránh thay MTU đồng loạt trên production nếu chưa xác nhận mọi path. Thay đổi MTU trên một đầu mà không cập nhật đầu còn lại hoặc thiết bị trung gian có thể làm mất kết nối. Với hệ thống có nhiều route, cần kiểm tra từng path thay vì chỉ test một cặp máy.

## 13. Ví dụ: API nội bộ qua VPN bị treo khi trả response lớn

Một API chạy trên máy ảo private có thể nhận request nhỏ từ mạng tại chỗ qua site-to-site VPN. Health check và TCP handshake đều thành công. Tuy nhiên, khi API trả file hoặc JSON lớn, client chờ lâu rồi timeout.

Quy trình chẩn đoán:

1. Xác nhận lỗi có liên quan đến kích thước response: response nhỏ hoạt động, response lớn thất bại.
2. Đo RTT và packet loss tới endpoint; kiểm tra retransmission ở cả client và server.
3. Kiểm tra MTU NIC ở hai phía và cấu hình tunnel VPN.
4. Thử packet IPv4 có DF với payload giảm dần để ước lượng PMTU; kiểm tra ICMP fragmentation-needed có quay về nguồn hay không.
5. Xem tunnel overhead, NAT-T và firewall có loại bỏ fragment hoặc ICMP cần thiết không.
6. Điều chỉnh tunnel MTU hoặc TCP MSS theo hướng dẫn thiết bị, rồi thử lại với payload lớn.
7. Theo dõi lỗi và latency sau thay đổi ở cả hai chiều.

Trong trường hợp này, tăng timeout của API có thể chỉ làm client chờ lâu hơn. Cần sửa nguyên nhân packet lớn không đi qua được path. Nếu đã điều chỉnh MTU/MSS mà vẫn có retransmission, tiếp tục kiểm tra congestion, route bất đối xứng và packet drop ở gateway.

## 14. Những sai lầm thường gặp

- **Tăng MTU mà không kiểm tra end-to-end:** packet lớn bị drop ở một hop trung gian. Đo PMTU trên từng path quan trọng.
- **Chặn toàn bộ ICMP:** PMTUD không nhận được thông báo cần giảm kích thước. Cho phép ICMP/ICMPv6 cần thiết theo chính sách.
- **Nhầm MTU với MSS:** MTU giới hạn IP packet, MSS giới hạn TCP payload. Tính header đúng khi chẩn đoán.
- **Coi ping là phép đo đầy đủ:** ICMP có thể bị rate limit hoặc xử lý khác TCP/UDP. Đối chiếu traffic ứng dụng.
- **Đổ lỗi cho băng thông khi throughput thấp:** packet loss, RTT, PPS, CPU hoặc cửa sổ TCP có thể là nút thắt.
- **Dùng jumbo frame qua VPN hoặc Internet:** tunnel và đường ngoài có thể không hỗ trợ kích thước đó. Chọn theo PMTU thực tế.
- **Chỉ đo một chiều:** route bất đối xứng làm latency và loss hai chiều khác nhau. Kiểm tra cả nguồn, đích và đường về.
- **Chạy iperf tải cao trên production:** phép thử có thể tự gây congestion. Dùng môi trường và cửa sổ kiểm thử được kiểm soát.

## 15. Checklist vận hành

- [ ] Đã biết MTU của từng NIC và MTU được hỗ trợ trên path quan trọng.
- [ ] Đã phân biệt IP MTU, Ethernet frame size và TCP MSS.
- [ ] PMTUD hoạt động; ICMP fragmentation-needed hoặc ICMPv6 Packet Too Big cần thiết không bị chặn.
- [ ] Tunnel VPN và overlay đã tính phần overhead encapsulation.
- [ ] Jumbo frame chỉ được bật khi toàn bộ path được xác nhận hỗ trợ.
- [ ] Đã đo RTT, p95/p99 latency, jitter và packet loss từ endpoint thực tế.
- [ ] Đã theo dõi TCP retransmission, NIC drops/errors, PPS và throughput.
- [ ] Đã phân biệt ICMP rate limit với packet loss của traffic ứng dụng.
- [ ] Bài đo throughput có giới hạn tải và không ảnh hưởng workload production.
- [ ] Thay đổi MTU/MSS được thử nghiệm, rollout theo nhóm và có kế hoạch rollback.

MTU, packet loss và latency có quan hệ trực tiếp với độ ổn định của giao tiếp giữa workload. Khi hiểu PMTU và MSS, giữ PMTUD hoạt động, đo loss/RTT/throughput ở đúng hai đầu và kiểm tra các giới hạn của NIC, gateway cùng tunnel, đội vận hành có thể khoanh vùng lỗi mạng chính xác hơn và tối ưu hiệu năng theo bằng chứng.
