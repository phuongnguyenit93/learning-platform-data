# Thu thập packet capture và log liên quan

**Packet capture (PCAP)** ghi nhận các gói tin quan sát được tại một interface hoặc điểm giám sát mạng, trong khi **log** ghi lại sự kiện ở các lớp khác nhau: máy đầu cuối, firewall, DNS, VPN, proxy, IDS/IPS, máy chủ và SIEM. Khi sự cố mạng hoặc dấu hiệu xâm nhập xảy ra, chỉ một nguồn dữ liệu thường không đủ để trả lời toàn bộ câu hỏi: *gói tin có thực sự đi qua mạng không, hệ thống bảo mật đã xử lý thế nào, ứng dụng có nhận yêu cầu không và ai là chủ thể tạo kết nối?*

Bài thực hành thuộc chương **Dự án thực hành bảo mật mạng** trong module **SECURITY_NETWORK_SECURITY**. Người học sẽ triển khai một lab nhỏ để **tạo lưu lượng giả lập, thu PCAP, lưu log liên quan, ghép sự kiện theo thời gian và định danh luồng, rồi viết báo cáo bằng chứng**. Kỹ năng này hỗ trợ kiểm tra phân đoạn mạng, firewall, VPN, DNS, IDS/IPS, mạng không dây, hệ thống cloud và xử lý sự cố an ninh.

**Giới hạn an toàn:** chỉ thu lưu lượng trên thiết bị, mạng và khoảng thời gian được cấp phép. Lab chính sử dụng **127.0.0.1 (loopback)**, dữ liệu tổng hợp và một web server cục bộ; không giám sát người dùng khác, không thu secret và không gửi dữ liệu tới Internet. Mọi ví dụ về mạng sản xuất chỉ nhằm mô tả phương pháp điều tra có thẩm quyền, không phải yêu cầu quét hoặc bắt gói trên hệ thống thật.

## 1. Mục tiêu học tập và sản phẩm bàn giao

Sau bài này, người học có thể:

1. Chọn đúng điểm capture và xác định giới hạn quan sát của từng vị trí.
2. Thu gói tin có giới hạn bằng tcpdump hoặc Wireshark, phân biệt capture filter và display filter.
3. Đọc được metadata TCP/IP, nhận diện phiên TCP, truy vấn DNS và dấu hiệu của TLS mà không suy đoán nội dung đã mã hóa.
4. Đồng bộ mốc thời gian giữa PCAP và log, xử lý khác biệt timezone, NAT và các ID phiên.
5. Đối chiếu bản ghi giữa máy phát, máy nhận và các thiết bị bảo mật để phân biệt **đã phát**, **đã đến**, **đã bị từ chối** và **chưa đủ bằng chứng**.
6. Bảo đảm tính toàn vẹn, kiểm soát quyền truy cập và thời gian lưu giữ dữ liệu PCAP/log.
7. Hoàn thành một báo cáo điều tra có timeline, bằng chứng, kết luận, giới hạn và kiến nghị.

**Sản phẩm mong đợi của lab:** một file PCAP chỉ chứa traffic mô phỏng, một file server log, bảng timeline ngắn, bảng đối chiếu trường dữ liệu, hash của file chứng cứ và báo cáo kết luận. Tên file sử dụng trong ví dụ là minh họa cho thư mục lab riêng của người học.

## 2. Vì sao cần cả PCAP và log?

PCAP và log trả lời những nhóm câu hỏi khác nhau:

| Nguồn | Thường cho biết | Không tự chứng minh |
| --- | --- | --- |
| PCAP tại điểm quan sát | Gói tin thấy được, IP/port, TCP flags, thời gian, packet size và payload nếu capture có chứa | Gói có đi tới endpoint cuối hay được ứng dụng xử lý không |
| Firewall log | Rule, interface/zone, verdict allow/deny, session, NAT theo nền tảng | Toàn bộ payload hoặc nguyên nhân lỗi ứng dụng |
| DNS resolver log | Client, QNAME, QTYPE, trả lời hoặc chính sách từ chối | Client thực sự kết nối tới IP đã được phân giải |
| Proxy/WAF log | HTTP host/path/status, rule ứng dụng, verdict theo khả năng visibility | Mọi luồng đi ngoài proxy hoặc hoạt động sau endpoint |
| VPN log | User/tunnel, IP cấp phát, trạng thái kết nối, thời gian | Mọi giao dịch của user với ứng dụng |
| IDS/IPS alert | Dấu hiệu khớp signature/behavior và liên quan flow | Tấn công chắc chắn thành công; alert có thể false positive |
| Endpoint/EDR | Process, PID, account, socket hoặc sự kiện kết nối | Mọi hop trung gian có cho phép gói hay không |
| Web/app server log | Request được nhận, xử lý và trả status | Từng gói bị mất trên đường mạng |
| NetFlow/IPFIX/cloud flow log | Flow tuple, bytes/packets, thời gian, action nếu nguồn có | Payload đầy đủ hoặc handshake chi tiết |

**Tương quan đa nguồn** có thể chứng minh chuỗi: tiến trình phát kết nối → firewall cho phép → sensor nhìn thấy các gói → server nhận yêu cầu → server trả mã HTTP. Nếu một mắt xích thiếu, phải diễn đạt rõ giới hạn thay vì điền giả định.

Ví dụ một firewall ghi **ALLOW** không có nghĩa kết nối ứng dụng thành công: gói có thể bị drop ở hop sau, DNS có thể sai hoặc server trả 503. Tương tự, không thấy gói trong một PCAP không chứng minh chưa từng có kết nối; có thể capture nhầm interface, sai filter, traffic đi tuyến khác hoặc sensor mất gói.

## 3. Các thuật ngữ cần nắm

- **Packet:** một đơn vị dữ liệu truyền trên mạng, có header và có thể có payload.
- **Frame:** đơn vị ở lớp liên kết, có địa chỉ MAC/VLAN tùy công nghệ; không phải mọi capture đều chứa header Ethernet.
- **Flow / five-tuple:** thường được mô tả bằng source IP, source port, destination IP, destination port và protocol.
- **Session / connection:** ngữ cảnh giao tiếp; TCP có handshake và state, UDP không có handshake TCP.
- **Capture point / vantage point:** vị trí thực tế mà công cụ nhìn lưu lượng; trước hay sau NAT, bên trong hay ngoài VPN, trước hay sau firewall.
- **Capture filter:** điều kiện libpcap/BPF áp dụng lúc bắt gói để giảm dữ liệu thu.
- **Display filter:** điều kiện hiển thị sau khi đã thu, ví dụ trong Wireshark; không làm thay đổi dữ liệu gốc.
- **Snap length (snaplen):** số byte tối đa lưu từ mỗi gói; thấp hơn kích thước gói có thể khiến payload bị cắt.
- **Promiscuous mode:** NIC nhận một số frame không nhắm tới chính nó khi hạ tầng cho phép; không đồng nghĩa nhìn thấy mọi traffic trong switch.
- **Dropped packet:** gói bị mất tại kernel/capture buffer, sensor hoặc đường truyền; ảnh hưởng độ tin cậy của PCAP.
- **Chain of custody:** quy trình ghi lại ai thu thập, xử lý, chuyển giao, lưu và sử dụng chứng cứ.

PCAP ghi nhận dữ liệu ở **điểm nhìn của sensor**, không phải mô hình hoàn chỉnh của toàn bộ kết nối trên mọi thiết bị.

## 4. Xác định câu hỏi điều tra trước khi bắt gói

Đặt câu hỏi cụ thể giúp chọn vị trí và bộ lọc đúng:

| Câu hỏi | Điểm quan sát hữu ích | Log hỗ trợ |
| --- | --- | --- |
| Client có gửi SYN tới API không? | Interface client hoặc phía trước firewall | Endpoint TCP log, firewall flow |
| Firewall có chặn kết nối không? | Trước và sau firewall nếu có quyền | Firewall deny/allow log với rule ID |
| DNS có trả lời sai hoặc bị policy chặn? | Resolver nội bộ hoặc client hợp lệ | DNS query/response log, DNS firewall |
| VPN có mang traffic đến subnet đích? | Gateway/tunnel endpoint theo thiết kế | VPN session, route và NAT log |
| IPS có tạo alert đúng lúc? | Sensor/TAP inline hoặc packet broker | IDS/IPS alert, signature ID, verdict |
| Server có nhận HTTP request? | Server interface hoặc reverse proxy | Web/app access log và trace ID |
| Cloud instance có thể truy cập dịch vụ? | ENI/cloud mirror nếu hỗ trợ | Cloud flow logs, SG/NACL policy, app logs |

**Nguyên tắc chọn điểm capture:** ưu tiên nơi trả lời được câu hỏi, tối thiểu dữ liệu nhạy cảm và ít ảnh hưởng hiệu năng. Đừng bắt toàn bộ traffic của một VLAN sản xuất chỉ để điều tra một host và một cổng.

## 5. Chuẩn bị quyền, phạm vi và an toàn dữ liệu

Trước khi thu PCAP trên bất kỳ mạng nào, cần xác nhận bằng văn bản hoặc quy trình được chấp nhận:

1. **Phạm vi:** asset, interface, subnet, IP, ứng dụng, vùng mạng, thời gian, protocol và câu hỏi điều tra.
2. **Thẩm quyền:** người phê duyệt, chủ hệ thống, người xử lý dữ liệu và đầu mối xử lý sự cố.
3. **Tính nhạy cảm:** PCAP có thể chứa cookie, token, session, thông tin nội bộ, dữ liệu người dùng hoặc payload ứng dụng chưa mã hóa.
4. **Giới hạn lượng dữ liệu:** filter, snaplen, dung lượng đĩa, thời gian capture và giới hạn tải.
5. **Phương án dừng:** hiệu năng giảm, capture gây disk pressure, phát hiện dữ liệu thật ngoài phạm vi, ảnh hưởng ứng dụng.
6. **Lưu trữ:** phân quyền đọc, mã hóa khi lưu/chuyển, thời hạn giữ, cách xóa và người có thể tiếp cận chứng cứ.
7. **Tính toàn vẹn:** thời điểm bắt đầu/kết thúc, phiên bản công cụ, hash và người bàn giao.
8. **Không can thiệp:** không đổi firewall, VPN, DNS hoặc logging chỉ để tạo bằng chứng nếu không có change được phê duyệt.

Với lab tại máy cá nhân, chỉ dùng nội dung tổng hợp. Với điều tra thật, ưu tiên metadata, rút ngắn thời gian thu, loại traffic không liên quan từ **lúc capture**, và áp dụng chính sách bảo vệ dữ liệu của tổ chức. Nếu cần ẩn dữ liệu khi báo cáo, giữ bản gốc được bảo vệ và tạo **bản sao đã biên tập** có hash riêng; không ghi đè file gốc.

## 6. Topology của lab loopback

Bài tập có một máy Linux với công cụ **Python 3, curl, tcpdump**; **Wireshark/TShark** là tùy chọn. Máy này tự chạy web server và client trên loopback:

~~~mermaid
flowchart LR
    C["Client curl"] -->|"HTTP GET, 127.0.0.1:8765"| L["Linux loopback (lo)"]
    L --> S["Python HTTP server"]
    L -.-> P["tcpdump → lab-011.pcap"]
    S -.-> A["http-server.log"]
    P --> T["Timeline / protocol analysis"]
    A --> T
~~~

**Không có tuyến Internet.** Port 8765 chỉ được bind tới 127.0.0.1, nên máy khác không truy cập web server qua interface mạng thông thường. Giao tiếp HTTP không mã hóa chỉ được chấp nhận ở đây vì dữ liệu hoàn toàn là synthetic và không rời khỏi loopback.

Trên macOS, interface thường có tên **lo0**, không phải lo. Trên Windows, có thể dùng Npcap/Wireshark với loopback adapter được hỗ trợ hoặc chạy lab trong VM Linux được cô lập. Các thao tác thu bắt yêu cầu quyền hệ điều hành phù hợp; dùng quyền tối thiểu và theo chính sách lab.

### 6.1. Tài nguyên cần chuẩn bị

| Thành phần | Yêu cầu |
| --- | --- |
| OS | Linux có loopback; terminal với quyền bắt gói được cho phép |
| Python 3 | Chạy web server cục bộ, không cần cài package bên ngoài |
| curl | Tạo một request HTTP với marker tổng hợp |
| tcpdump | Bắt packet tại interface lo |
| TShark/Wireshark (tùy chọn) | Kiểm tra HTTP request, stream và timeline |
| Dung lượng | Một thư mục lab rỗng và vài MB dung lượng |
| Dữ liệu | Tệp văn bản marker không chứa thông tin thật |

**Không bắt đầu từ việc kết nối tới dịch vụ public hoặc tải một file từ Internet.** Mục tiêu bài này là học phương pháp thu và đối chiếu bằng chứng, không phải kiểm tra mục tiêu bên ngoài.

## 7. Bước 1 — Tạo dữ liệu synthetic và thư mục lab

Trong môi trường Linux được ủy quyền, chuẩn bị thư mục lab riêng:

~~~bash
mkdir -p lab-pcap-011
cd lab-pcap-011

printf 'EXERCISE_ID=NET-PCAP-011\nDATA_CLASS=SYNTHETIC\n' > marker.txt

# Kiểm tra đúng dữ liệu giả lập trước khi chạy server.
cat marker.txt
~~~

Tệp marker.txt chỉ có hai dòng do người học tạo. Không copy tài liệu khách hàng, log thật, file cấu hình có secret hoặc backup vào thư mục này.

Ghi metadata cơ bản bằng lệnh:

~~~bash
date -u '+%Y-%m-%dT%H:%M:%SZ'
hostname
~~~

**Không** cần ghi hostname thật vào tài liệu chia sẻ công khai. Trong báo cáo nội bộ, có thể dùng mã tài sản lab và xác định timezone, ví dụ UTC.

## 8. Bước 2 — Mở web server loopback và lưu log

Ở terminal thứ nhất, trong thư mục lab-pcap-011, chạy:

~~~bash
python3 -u -m http.server 8765 --bind 127.0.0.1 2>&1 | tee http-server.log
~~~

Các thuộc tính:

- Dịch vụ chỉ lắng nghe trên **127.0.0.1:8765**.
- Python SimpleHTTPRequestHandler phục vụ các file trong thư mục hiện tại; vì vậy chỉ chạy từ **thư mục lab chứa duy nhất dữ liệu không nhạy cảm**.
- Log đầu ra có timestamp, IP client 127.0.0.1, request line và HTTP status.
- Đường dẫn và query string được in trong log, do đó marker phải không mang secret.
- Lệnh tee ghi log vào http-server.log phục vụ đối chiếu, ngoài bản log hiện ở terminal.

Nếu cổng 8765 đã được chương trình khác sử dụng, dừng và xác nhận chương trình đó trước; có thể chọn cổng lab khác, nhưng **phải thay nhất quán** ở server, capture, client và câu lệnh phân tích.

**Giới hạn:** đây là web server đơn giản để thực hành, không phải hệ thống web server production, reverse proxy hay công cụ phân tích bảo mật.

## 9. Bước 3 — Bắt packet bằng tcpdump

Ở terminal thứ hai, cùng thư mục lab, chạy trước khi phát request:

~~~bash
# Trên Linux; quyền root/capture cần tuân thủ quy định hệ điều hành.
sudo tcpdump -i lo -nn -s 256 -w lab-011.pcap 'tcp and port 8765'
~~~

Giải thích:

| Tham số | Ý nghĩa |
| --- | --- |
| -i lo | Chỉ capture interface loopback trong lab Linux |
| -nn | Không phân giải địa chỉ IP và tên dịch vụ trong output tcpdump |
| -s 256 | Chỉ lưu tối đa 256 byte đầu mỗi gói, giảm dữ liệu cần lưu; có thể cắt payload |
| -w lab-011.pcap | Ghi packet ở định dạng được tcpdump hỗ trợ (thường pcap) |
| 'tcp and port 8765' | Capture filter libpcap/BPF chỉ thu TCP của port lab |

Sau khi chạy, đợi đến khi tcpdump báo đang lắng nghe rồi mới tạo request; sau khi thực hiện bài tập, **nhấn Ctrl+C** để tcpdump đóng file và in thống kê gói đã thu/được kernel drop. Nếu chưa có gói do chưa phát request, không cần thay filter bằng “capture tất cả”.

**Vì sao chọn snaplen 256?** Trong bài này chỉ cần IP/TCP và phần đầu request HTTP với marker ngắn. Khi phân tích ứng dụng phức tạp cần nhiều nội dung hơn, việc tăng snaplen chỉ được thực hiện theo phạm vi và kiểm soát dữ liệu đã duyệt. Nếu gói bị cắt, không được kết luận ứng dụng gửi payload ngắn.

### 9.1. Các bộ lọc capture tham khảo

Ví dụ chỉ để hiểu cú pháp, không phải yêu cầu bắt gói tới địa chỉ ngoài lab:

~~~text
tcp port 8765

host 192.0.2.10 and tcp port 443

host 192.0.2.10 and (tcp port 443 or udp port 53)

src host 192.0.2.10 and dst host 198.51.100.20

(ip6 and tcp port 443) or (ip and tcp port 443)
~~~

**192.0.2.0/24 và 198.51.100.0/24** là các dải địa chỉ phục vụ tài liệu, không đại diện một hệ thống thực. Capture filter dùng cú pháp BPF; Wireshark display filter dùng cú pháp khác, ví dụ **tcp.port == 8765**, **http.request** hoặc **ip.addr == 192.0.2.10**. Không đặt nguyên display filter vào tham số tcpdump rồi kỳ vọng hoạt động.

### 9.2. Chọn điểm capture phù hợp

Trên Linux, -i any có thể tập hợp gói từ nhiều interface, nhưng metadata link-layer và khả năng xuất hiện bản ghi trùng tùy hạ tầng; nó **không tự giải quyết** bài toán lưu lượng qua nhiều node hoặc đường VPN. Trong lab biết chắc traffic đi qua **lo**, vì vậy chọn đúng interface thay vì any.

Với mạng switch, capture trên cổng của một máy **không nhìn thấy mọi unicast** của các máy khác. Sensor cần TAP, SPAN/mirror, packet broker hoặc telemetry được triển khai đúng vị trí và có thẩm quyền. SPAN có thể drop gói khi quá tải; kiểm tra khả năng mất packet trước khi dùng PCAP làm bằng chứng phủ định.

## 10. Bước 4 — Tạo một yêu cầu có dấu mốc nhận diện

Ở terminal thứ ba, cùng máy:

~~~bash
curl --noproxy '*' \
  --connect-timeout 3 --max-time 5 \
  -sS -o /dev/null \
  -w 'HTTP=%{http_code} bytes=%{size_download}\n' \
  'http://127.0.0.1:8765/marker.txt?exercise_id=NET-PCAP-011'
~~~

Kết quả dự kiến:

~~~text
HTTP=200 bytes=46
~~~

Con số byte có thể khác nếu sửa tệp marker hoặc encoding. **HTTP 200** cho biết server nhận và phục vụ file thành công trong lab. Nó không phải bằng chứng firewall ngoài mạng cho phép traffic, vì luồng này chỉ đi qua loopback.

Marker **NET-PCAP-011** giúp đối chiếu request trong PCAP và server log. Dấu mốc là thông tin synthetic, không được thay bằng session token hoặc ID người dùng thật.

Ở terminal thứ nhất, có thể thấy dòng log gần dạng:

~~~text
127.0.0.1 - - [28/Nov/2026 14:00:00] "GET /marker.txt?exercise_id=NET-PCAP-011 HTTP/1.1" 200 -
~~~

Thời gian này chỉ là **ví dụ minh họa**; máy thực sẽ ghi giờ hiện tại theo cấu hình môi trường. Đảm bảo giờ máy và timezone được ghi vào báo cáo.

Sau request, nhấn **Ctrl+C** ở terminal bắt gói để hoàn tất PCAP; sau khi đã xác minh log, nhấn Ctrl+C ở server để kết thúc lab.

## 11. Bước 5 — Đọc lại PCAP và đối chiếu log

Trước hết kiểm tra file không rỗng và xem các gói đã thu:

~~~bash
ls -lh lab-011.pcap http-server.log

# Đọc PCAP ở chế độ không phân giải DNS/service name.
tcpdump -nn -tttt -r lab-011.pcap 'tcp port 8765'
~~~

Trong kết quả có thể xuất hiện:

- **SYN:** client đề nghị thiết lập kết nối TCP đến 127.0.0.1:8765.
- **SYN, ACK:** server trả lời handshake nếu bắt đầu capture đủ sớm.
- **ACK:** hoàn thành bắt tay TCP.
- Các segment chứa HTTP request, HTTP response và ACK, sau đó kết thúc phiên.
- Do chạy trên loopback, source và destination IP đều là 127.0.0.1; phân biệt hai phía dựa trên **port**, TCP flags và sequence/acknowledgment.
- Nếu capture bắt đầu quá muộn, có thể không có SYN dù đã thấy request. Đó là **giới hạn điểm bắt đầu**, không có nghĩa kết nối không cần handshake.

Với TShark nếu đã cài:

~~~bash
# Ép dissector nhận TCP/8765 là HTTP cho bài lab.
tshark -r lab-011.pcap \
  -d tcp.port==8765,http \
  -Y 'http.request' \
  -T fields \
  -e frame.time_epoch \
  -e ip.src -e tcp.srcport \
  -e ip.dst -e tcp.dstport \
  -e http.request.method -e http.request.uri

# Tìm HTTP response theo cùng cổng lab.
tshark -r lab-011.pcap \
  -d tcp.port==8765,http \
  -Y 'http.response' \
  -T fields \
  -e frame.time_epoch -e http.response.code
~~~

**Vì sao có -d?** HTTP server ở cổng 8765 không nhất thiết được Wireshark tự động nhận diện là HTTP. Cơ chế **Decode As** chỉ thay cách phân tích dữ liệu đã thu, không sửa packet thật. Nếu snaplen 256 khiến phần cần thiết bị cắt, TShark có thể không phân tích được request; tăng snaplen trên một lần thu lab **mới** nếu cần và vẫn chỉ dùng synthetic traffic.

Trong Wireshark, mở file **lab-011.pcap**, nhập display filter **tcp.port == 8765**, chọn packet, xem các lớp IP/TCP, xác định TCP stream rồi đọc phần HTTP không mã hóa của **lab synthetic**. Tắt name resolution nếu việc hiển thị hostname làm khó đối chiếu IP. **Follow TCP Stream** có thể ghép payload và vì thế cũng có thể làm lộ dữ liệu nếu áp dụng trên PCAP thật; phải bảo vệ quyền đọc.

### 11.1. Đối chiếu sự kiện theo marker

| Bằng chứng | Tìm gì | Ý nghĩa |
| --- | --- | --- |
| Lệnh curl | HTTP status và số byte | Client tạo và nhận phản hồi HTTP |
| Server log | GET /marker.txt?... và mã 200 | HTTP server đã xử lý request synthetic |
| PCAP | Cổng 8765, request URI, response code | Capture thấy một phần hoặc toàn bộ gói của phiên |
| Timestamp | Thứ tự và độ lệch thời gian giữa nguồn | Có thể ghép đúng request theo thời gian |
| Marker | NET-PCAP-011 | Tránh nhầm với request khác trong lab |

Nếu một phía không có dấu mốc nhưng các phía khác có, kiểm tra **điểm capture, filter, thời gian, truncation, decoder và log buffering** trước khi kết luận có sự cố mạng.

## 12. Khác biệt giữa PCAP và log về thời gian

### 12.1. Chuẩn hóa thời gian

Hầu hết bản ghi sự kiện có một hoặc nhiều thời gian:

- **Event time:** thời điểm hành vi xảy ra theo đồng hồ hệ thống tạo log.
- **Capture timestamp:** thời điểm sensor gắn timestamp khi quan sát packet.
- **Ingest time:** thời điểm SIEM hoặc hệ thống log tập trung nhận record.
- **Processing/alert time:** thời điểm rule phân tích tạo alert.

Các mốc này không bắt buộc trùng nhau. SIEM có thể nhận log trễ hàng chục giây hoặc phút, đặc biệt khi có hàng đợi mạng.

Ví dụ minh họa:

| Nguồn | Timestamp gốc | Chuẩn hóa UTC | Ghi chú |
| --- | --- | --- | --- |
| PCAP | Epoch 179585... (ví dụ) | Theo frame.time_epoch | Nên chuyển từ giá trị epoch thực |
| Web server | 28/Nov/2026 14:00:00 +07:00 | 2026-11-28T07:00:00Z | Log Python mặc định có thể không ghi offset |
| Firewall | 2026-11-28T07:00:00.130Z | Không đổi | Có thể phản ánh thời điểm policy xử lý |
| SIEM ingest | 2026-11-28T07:00:03Z | Không đổi | Trễ ingest ≈ 3 giây |

Giá trị epoch viết rút gọn trong bảng **không dùng để tính toán**; trong báo cáo thật phải lưu giá trị đầy đủ và định dạng nguồn.

**Quan trọng:** log Python http.server thường hiển thị giờ địa phương mà **không ghi timezone rõ ràng**. Khi ghép với PCAP, phải biết timezone cấu hình trên host và sai lệch đồng hồ. Không tự coi chuỗi thời gian thiếu offset là UTC.

### 12.2. Kiểm tra đồng hồ và thứ tự

- Đồng bộ các thiết bị quan trọng bằng NTP hoặc cơ chế thời gian được tổ chức quản lý.
- Ghi tình trạng clock sync và độ lệch được biết tại thời điểm thu, đặc biệt với firewall, endpoint và SIEM khác múi giờ.
- Chuyển timestamp về UTC để sắp xếp; khi trình bày, có thể thêm timezone địa phương cho người vận hành.
- Không sắp xếp theo **ingest time** rồi kết luận thứ tự sự kiện mạng nếu event time đáng tin cậy cho thấy điều khác.
- Nếu hai record cách nhau 50 ms mà độ lệch đồng hồ có thể 2 giây, chỉ kết luận chúng **gần thời gian nhau**, chưa đủ chắc chắn thứ tự trước–sau.

### 12.3. Dùng marker và ID luồng

Trong lab, marker ở URL là điểm nối mạnh giữa log HTTP và PCAP. Trong sản xuất, dùng các định danh do hệ thống sinh và được phép thu thập, chẳng hạn request ID, trace ID, session ID, DNS transaction ID, 5-tuple và timestamp.

Không đưa thông tin bí mật vào marker để “dễ tìm” trong log. Marker nên là ID ngẫu nhiên hoặc mã bài tập **không nhạy cảm** và có scope rõ.

## 13. Đối chiếu flow qua nhiều thiết bị

Trong điều tra mạng thật, một flow có thể xuất hiện ở nhiều dạng do **NAT**, load balancer, proxy và VPN:

~~~mermaid
flowchart LR
    C["Client 10.20.0.15:51000"] --> F["Firewall / NAT"]
    F -->|"Public source 203.0.113.10:61000"| P["Proxy / edge"]
    P --> S["Server 198.51.100.20:443"]
    F -.-> FL["Firewall log: pre/post NAT"]
    P -.-> PL["Proxy log: request ID"]
    S -.-> SL["Server log"]
    FL --> COR["Correlation"]
    PL --> COR
    SL --> COR
~~~

Các địa chỉ thuộc 203.0.113.0/24 và 198.51.100.0/24 là **địa chỉ dành cho tài liệu**, không phải server thật. Số port cũng chỉ là giả định.

### 13.1. Ghép bằng khóa nào?

| Trường | Khả năng dùng | Giới hạn |
| --- | --- | --- |
| Source/destination IP | Xác định hai phía tại một hop | NAT/proxy/IPv6 translation có thể đổi địa chỉ |
| TCP/UDP ports | Phân biệt kết nối từ cùng IP | NAT có thể đổi source port; port có thể tái sử dụng |
| Protocol | TCP, UDP, ICMP và các giao thức khác | Không đủ để định danh một phiên |
| Timestamp | Thu hẹp cửa sổ liên hệ | Đồng hồ có thể lệch; ingest trễ |
| NAT/session ID | Liên kết pre-NAT/post-NAT trên thiết bị cụ thể | Không có chung giữa các vendor |
| HTTP request/trace ID | Liên kết proxy và ứng dụng | Có thể không được truyền qua mọi hop |
| Zeek uid | Liên hệ các log Zeek cùng kết nối khi sensor ghi được | Không phải ID toàn cầu của mọi thiết bị |
| Suricata EVE flow_id | Liên hệ các event thuộc cùng flow trên một nguồn quan sát | Không thay được kết hợp IP/port/time giữa nhiều sensor |
| TCP stream index | Gom packet trong một file Wireshark/TShark | Chỉ có ý nghĩa cục bộ của phiên phân tích/file |

**Không dùng chỉ một IP hoặc chỉ một thời điểm để ghép sự kiện** ở mạng có tải lớn. Một IP public NAT có thể đại diện cho hàng nghìn kết nối; cần tối thiểu protocol, port, cửa sổ thời gian và mapping NAT nếu có.

### 13.2. Quy tắc ghép đề xuất

1. Đặt **cửa sổ thời gian đủ hẹp** theo đồng hồ đã đồng bộ, nhưng không hẹp hơn độ trễ/sai lệch thực tế.
2. So khớp protocol, 5-tuple tại mỗi điểm quan sát và xác định chiều luồng.
3. Đọc NAT translation hoặc proxy request ID để nối các hop.
4. Xem TCP flags, byte/packet counts, durations và response code để phân biệt các phiên gần giống.
5. Đối chiếu sensor còn nhìn thấy cùng flow hay không; đánh dấu các nhánh không có bằng chứng.
6. Ghi **mức tin cậy** của mối tương quan: chắc chắn, khả năng cao, chưa đủ bằng chứng.

## 14. Mở rộng điều tra: DNS, HTTPS/TLS và VPN

Lab loopback chỉ dùng HTTP để người học có thể thấy request/response rõ ràng. Hệ thống doanh nghiệp lại thường có DNS, HTTPS/TLS, VPN và QUIC.

### 14.1. DNS

Trong một cuộc điều tra được cấp phép, đối chiếu:

1. Client hỏi resolver nào, QNAME/QTYPE gì, lúc nào?
2. Resolver trả IP nào, có NXDOMAIN/timeout/SERVFAIL hay bị DNS firewall từ chối?
3. Client có tạo flow tới IP trả về ngay sau đó không?
4. Domain có ánh xạ tới nhiều IP/CDN hoặc bị cache cũ làm sai kỳ vọng không?

Một truy vấn DNS thành công **không chứng minh** kết nối tới server đã thành công. DNS over HTTPS (DoH) hoặc DNS over TLS (DoT) có thể khiến truy vấn không hiện thành packet UDP/53 ở sensor thường; cần telemetry ở resolver/proxy/endpoint tương ứng.

### 14.2. HTTPS/TLS

PCAP thường thấy IP/port, TCP handshake, TLS handshake metadata có thể có, kích thước và hướng gói, nhưng **không tự đọc nội dung ứng dụng đã mã hóa**. Một số tên miền từ SNI có thể hiển thị tùy phiên bản giao thức/cấu hình và ECH; không giả định luôn có hostname trong PCAP.

Để giải thích HTTP status trên TLS, thường cần log của reverse proxy, load balancer, ứng dụng hoặc hệ thống inspection được phê duyệt. Không yêu cầu trích xuất private key, phá TLS hoặc bật giải mã lưu lượng thật chỉ để hoàn thành bài tập này.

### 14.3. VPN, tunnel và overlay

- Sensor ở **ngoài tunnel** có thể chỉ thấy hai tunnel endpoint và gói đã mã hóa.
- Sensor ở **trong tunnel** hoặc tại gateway sau giải mã có thể thấy IP/port nội bộ theo khả năng quan sát.
- Kiểm tra IPsec/IKE session, VPN user/session ID, route, NAT, policy selector và thời gian kết nối.
- Trong cloud overlay và container networking, có thể cần telemetry từ host, CNI, virtual switch hoặc cloud flow logs.

Không kết luận một host không liên lạc với nhau chỉ vì outer interface thấy traffic mã hóa không thể đọc destination bên trong.

## 15. Liên hệ với firewall, IDS/IPS, DNS và cloud logs

Một phương pháp điều tra có thể đi theo chuỗi **phát hiện → xác minh đường đi → đối chiếu policy → xác nhận tác động**.

### 15.1. Firewall

Các trường cần ghi theo khả năng thiết bị:

~~~text
timestamp_utc
device_id / virtual_context
src_zone, src_ip, src_port
dst_zone, dst_ip, dst_port
protocol
action: allow / deny / drop / reset / ...
policy_id / rule_name
pre_nat_src, pre_nat_dst
post_nat_src, post_nat_dst
session_id, bytes_sent, bytes_received
~~~

Không phải mọi firewall ghi đầy đủ trường trên. Một event DENY có thể chỉ chứng minh firewall xử lý packet ở vị trí nó nhìn thấy; để giải thích tại sao server không nhận request, cần kiểm tra đường khác và chính xác policy enforcement point.

### 15.2. IDS/IPS

IDS/IPS thường tạo alert chứa signature ID, action, severity, sensor interface, source/destination và thời gian. Alert cần được đối chiếu với PCAP/flow trước khi nhận định đây là traffic tấn công. IPS có thể drop, reject hoặc chỉ alert theo chế độ hoạt động; không tự suy ra block từ một event chỉ có tên signature.

Với Zeek, một số log liên hệ theo **uid** và fields connection; với Suricata EVE, có thể nối các event cùng flow bằng **flow_id** trong phạm vi cùng nguồn. Các ID này **không phải request ID ứng dụng toàn hệ thống**.

### 15.3. Cloud flow logs

Trong cloud, flow logs thường là metadata được tổng hợp theo khoảng, có thể có độ trễ và giới hạn phạm vi tùy dịch vụ. Một bản ghi ACCEPT/REJECT không cho biết payload hoặc nhất thiết xác định rule security group nào đã tác động. Phải kết hợp SG/NACL, route tables, NAT, endpoint policy và application logs.

### 15.4. Wi-Fi và truy cập từ xa

Với Wi-Fi, có thể cần log AP/controller, 802.1X/RADIUS, DHCP, roaming, VLAN assignment và association event. Nếu chỉ bắt Ethernet ở server, sẽ khó biết client đã rớt Wi-Fi hay 802.1X từ chối trước khi xuất hiện IP packet. Đặt capture và yêu cầu log đúng lớp gây nghi ngờ.

## 16. Nhận diện các giai đoạn của một phiên TCP

Để diễn giải PCAP, cần hiểu các quan sát cơ bản:

| Dấu hiệu | Cách diễn giải thường gặp | Cẩn trọng |
| --- | --- | --- |
| SYN từ client | Client đề nghị mở TCP connection | Chưa chứng minh đích nhận |
| SYN-ACK từ server | Đích phản hồi yêu cầu thiết lập | Cần đối chiếu vị trí sensor và phiên tương ứng |
| ACK hoàn tất handshake | Ba bước handshake xuất hiện đầy đủ | Không chứng minh app đã xử lý request |
| Retransmission | Segment cần gửi lại hoặc bị công cụ phân tích suy luận | Có thể do mất gói, capture loss, reorder, offload |
| RST | Một phía hoặc thiết bị trung gian đóng/reset flow | Cần ngữ cảnh để biết ai/điểm nào gây ra |
| FIN | Đóng kết nối theo luồng TCP | Không tự phản ánh lỗi ứng dụng |
| HTTP 4xx/5xx | Ứng dụng hoặc proxy trả mã từ chối/lỗi | Có thể là policy ứng dụng chứ không phải firewall |
| TLS alert | Thông báo thuộc giao thức TLS | Cần xem loại alert, chiều và phiên bản giao thức |
| ICMP unreachable | Thông điệp về đường mạng/đích không tới được | Có thể bị firewall lọc hoặc không đại diện toàn tuyến |

Không kết luận “bị tấn công”, “lỗi firewall” hay “mất packet” chỉ từ một cờ TCP. Cần xem **cả chuỗi phiên**, hành vi ứng dụng và điểm capture.

### 16.1. TCP retransmission có thật hay chỉ là artefact?

Trên máy chủ có NIC offload như TSO/GSO/GRO, capture gần host có thể cho thấy packet size hoặc checksum “lạ” so với các gói trên dây. Wireshark có thể đánh dấu checksum invalid do offload, không nhất thiết do packet hỏng thật. Trên loopback, một số kernel cũng xử lý gói theo cách không giống Ethernet vật lý.

Khi nghi mất gói, kết hợp sequence/ACK, TCP RTT, thống kê drop của capture, tình trạng NIC, interface error, đường truyền và log ứng dụng. Nếu có thể, so sánh PCAP ở **hai phía một đoạn mạng** dưới phạm vi được phép để xác nhận nơi gói biến mất.

## 17. Thu đủ nhưng không thu quá nhiều

Một bộ dữ liệu quá lớn làm tăng chi phí lưu trữ, lộ dữ liệu và thời gian phân tích. Một bộ dữ liệu quá nhỏ hoặc filter sai lại làm mất bằng chứng.

**Nguyên tắc thực hành:**

- Chỉ capture **interface** thực sự chứa traffic cần khảo sát.
- Chọn filter theo host/subnet/port/protocol và cửa sổ thời gian đã được phê duyệt.
- Ghi mục tiêu snaplen: lấy metadata hoặc cần payload ở mức nào, vì sao.
- Nếu traffic bùng nổ, dùng cơ chế ring buffer/rotation theo tài liệu công cụ và giới hạn đĩa đã phê duyệt; tránh để PCAP lấp đầy phân vùng.
- Theo dõi dropped packets từ tcpdump/kernel và sensor; ghi cùng số lượng gói đã capture.
- Giữ một khoảng **trước, trong và sau** sự kiện nếu có cơ chế ghi phù hợp; không chỉ thu đúng lúc alert xuất hiện khi triệu chứng đã qua.
- Không chỉnh sửa file gốc sau thu; phân tích trên bản sao read-only.
- Đảm bảo log ứng dụng, firewall và IDS/IPS có retention đủ để ghép với PCAP.

**Giới hạn của lab:** dùng -s 256 và capture vài request là đủ để thực hành quy trình; chưa thể dùng đó làm baseline cho traffic sản xuất hoặc đánh giá hiệu năng IDS/IPS.

## 18. Xác minh tính toàn vẹn và lưu bằng chứng

Sau khi dừng capture, ghi hash SHA-256 và metadata cho file PCAP và log:

~~~bash
sha256sum lab-011.pcap http-server.log
ls -lh lab-011.pcap http-server.log
~~~

Ví dụ bản ghi manifest, không phải kết quả chạy thật:

~~~text
exercise_id: NET-PCAP-011
capture_point: 127.0.0.1 / lo (Linux lab)
capture_filter: tcp and port 8765
snaplen: 256
capture_start_utc: <UTC start>
capture_end_utc: <UTC end>
pcap_file: lab-011.pcap
pcap_sha256: <hex SHA-256 from tool output>
server_log_file: http-server.log
server_log_sha256: <hex SHA-256 from tool output>
collector: <authorized lab operator>
storage_classification: internal-training
retention: <approved period>
notes: synthetic traffic only; no Internet destinations
~~~

Hash giúp phát hiện file bị thay đổi sau khi ghi; **hash một mình không chứng minh nguồn thu đáng tin hoặc chuỗi bàn giao đầy đủ**. Phải ghi ai thu, trên thiết bị nào, đồng hồ và filter, thời gian, cách chuyển, quyền lưu và mọi thao tác biên tập.

Nếu cần trích một subset PCAP để chia sẻ, giữ bản gốc được bảo vệ và tính **hash riêng cho bản trích**. Không đăng PCAP/log thật lên website phân tích công khai khi chưa có quyền và đánh giá bảo mật dữ liệu.

## 19. Tổ chức timeline điều tra

Dùng cùng một timezone (ưu tiên UTC) và phân biệt **quan sát** với **suy luận**.

Ví dụ giả lập có chuỗi:

| Thời gian UTC (minh họa) | Nguồn | Sự kiện | Độ tin cậy |
| --- | --- | --- | --- |
| 07:00:00.000 | Client curl | Gửi GET marker | Cao nếu có log terminal |
| 07:00:00.010 | PCAP lo | TCP SYN tới 127.0.0.1:8765 | Cao tại điểm capture |
| 07:00:00.018 | PCAP lo | HTTP request URI mang exercise_id | Cao nếu payload không bị cắt |
| 07:00:00.020 | Server log | GET marker, 200 | Cao về xử lý ứng dụng |
| 07:00:00.024 | PCAP lo | HTTP response 200 | Cao nếu decoder nhận đúng |
| 07:00:00.030 | Client curl | In HTTP=200 | Cao về kết quả client nhận |

Các mốc chỉ là **số liệu dạy học giả định**. Trong log thật, cần lấy thời gian nguyên bản và quy đổi; không bịa millisecond nếu server chỉ ghi tới giây.

### 19.1. Kết luận chính xác trong lab

Nếu curl nhận 200, server log có request và PCAP chứa HTTP request/response, có thể kết luận:

> Trong lab loopback, client đã gửi request synthetic, web server đã xử lý và trả HTTP 200; capture ở interface lo có quan sát các gói của phiên tương ứng.

Không thể kết luận:

- Firewall Internet đã cho phép traffic.
- IDS/IPS của tổ chức phát hiện được tấn công.
- Dữ liệu đã đi ra ngoài máy.
- TLS được bảo mật hay ứng dụng có xác thực đúng.
- Tất cả packet đều được capture nếu chưa xem thống kê drop.

**Viết điều gì PCAP/log thực sự chứng minh, không viết điều muốn chúng chứng minh.**

## 20. Bài tập phân tích tình huống nhiều nguồn log

Một ứng dụng nội bộ được giả định có client **10.40.20.15** truy cập API **10.50.30.25:443** qua firewall. Client báo timeout. Các mẩu chứng cứ (tổng hợp, không phải log từ hệ thống thật):

~~~text
A - Endpoint:
  10:12:01.100Z connect(10.50.30.25:443) started
  10:12:06.100Z connect timeout

B - Firewall:
  10:12:01.101Z src=10.40.20.15:50120 dst=10.50.30.25:443
  action=allow rule=APP_TO_API policy_version=42

C - PCAP trước firewall:
  10:12:01.100Z SYN 10.40.20.15:50120 -> 10.50.30.25:443
  10:12:02.200Z TCP SYN retransmission (theo phân tích)

D - PCAP sau firewall:
  chưa có bản capture

E - API server log:
  chưa thấy request cho client này trong cửa sổ 10:11-10:13Z
~~~

### 20.1. Câu hỏi cần trả lời

1. Đã chắc firewall làm rơi gói chưa?
2. Firewall ALLOW chứng minh API nhận request không?
3. Log API không có request có thể do những nguyên nhân nào?
4. Cần đặt capture tiếp theo ở đâu với phạm vi nào?
5. Nếu có NAT hoặc load balancer, cần trường bổ sung nào?
6. Khi nào được gọi đây là sự cố mạng, và khi nào còn là **INCONCLUSIVE**?

### 20.2. Hướng phân tích

- A, B và C cho thấy client phát SYN và firewall ghi một quyết định allow liên quan.
- Chưa có D nên **không đủ chứng cứ** packet rời firewall hay tới API. Chưa có SYN-ACK ở capture trước firewall có thể do đường trả về, đích, filter, routing, packet loss hoặc sensor.
- Không có API access log là điều dễ hiểu nếu TCP handshake chưa hoàn thành; ứng dụng HTTP chưa nhận request.
- Cần thêm capture **sau firewall hoặc gần API**, firewall session/NAT log, route và interface counters theo đúng quyền kiểm thử.
- Nếu có load balancer, kiểm tra target health, listener rule và proxy/app log. Nếu traffic qua tunnel, xác định phía trong hay ngoài tunnel của mỗi sensor.
- Kết luận tạm: **client không thiết lập được TCP connection trong cửa sổ quan sát; nguyên nhân nằm ở một hoặc nhiều đoạn chưa có đủ bằng chứng**.

Không tự thay firewall rule để “thử cho qua” trước khi có phê duyệt; việc mở tạm có thể làm đổi môi trường chứng cứ và tạo thêm rủi ro bảo mật.

## 21. Lỗi thường gặp trong thu thập và phân tích

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Bắt sai interface | Không thấy traffic rồi kết luận host không gửi | Xem route, tunnel/overlay, interface thực và điểm sensor |
| Bắt quá muộn | Thiếu SYN, DNS query hoặc bước bắt đầu phiên | Ghi rõ cửa sổ, thu lại trong lab với trigger sớm |
| Filter quá hẹp hoặc sai cú pháp | Mất packet quan trọng | Kiểm tra capture filter trước, phân biệt BPF và display filter |
| Dùng -s quá ngắn | Không có payload cần phân tích | Ghi snaplen, thu lại synthetic với mức cho phép |
| Bắt tất cả traffic trên production | Lộ dữ liệu, tăng tải, lấp đĩa | Scope hẹp, giới hạn thời gian/dung lượng và approval |
| Không xem dropped packets | Kết luận phủ định từ PCAP không đầy đủ | Lưu thống kê drop, sensor health và giới hạn |
| Tin checksum lỗi trên host capture | Chẩn đoán nhầm lỗi dây mạng | Xem offload/GRO/TSO và capture tại điểm khác |
| Ghép sự kiện chỉ bằng IP sau NAT | Nhầm session của nhiều client | Correlate port, time, translation/session ID |
| Đồng nhất SIEM ingest với event time | Timeline sai thứ tự | Chuẩn hóa UTC và xem clock skew |
| Coi DNS query là HTTP connection | Gán nhầm hành vi | Tìm flow thực tới IP/port và log đích |
| Coi TLS không thể giám sát | Bỏ qua metadata và endpoint evidence | Kết hợp flow, proxy, EDR và app logs được phép |
| Coi firewall ALLOW là delivery | Bỏ sót hop sau hoặc lỗi ứng dụng | Ghép PCAP ở nhiều điểm và server log |
| Coi IDS alert là exploit thành công | Sai mức độ sự cố | Xác minh traffic, payload khả dụng và hậu quả |
| Sửa trực tiếp PCAP gốc | Mất khả năng kiểm chứng | Lưu bản gốc bất biến; làm việc trên bản sao |
| Chia sẻ PCAP không kiểm soát | Lộ secret/PII | Phân quyền, mã hóa, giữ/chuyển/xóa theo chính sách |

## 22. Đánh giá chất lượng bằng chứng

Có thể chấm chất lượng một bộ dữ liệu theo các trục:

| Trục | Câu hỏi | PASS khi |
| --- | --- | --- |
| Authorization | Điểm capture và traffic trong phạm vi? | Có quyền và mục tiêu rõ |
| Coverage | Đã thu đúng interface, thời điểm và giao thức? | Có log cấu hình capture và thống kê |
| Integrity | File có hash, manifest, người thu và thời gian? | Có bản gốc được bảo vệ |
| Clock accuracy | Thiết bị có timezone/độ lệch được xác định? | Timeline có thể quy về UTC |
| Correlation | Các nguồn log có cùng marker/flow không? | Có bằng chứng đối chiếu nhiều trường |
| Fidelity | Snapshot đủ dài, ít mất gói, snaplen phù hợp? | Đủ để trả lời câu hỏi trong scope |
| Privacy | Chỉ có dữ liệu được phép, đã hạn chế chia sẻ? | Không tiết lộ dữ liệu ngoài scope |
| Interpretation | Kết luận phản ánh bằng chứng hay suy đoán? | Nêu giới hạn và giả thuyết thay thế |
| Actionability | Có bước tiếp theo hoặc kiểm thử lại? | Owner biết cần kiểm tra hoặc sửa gì |

Nên dùng **PASS / FAIL / INCONCLUSIVE** cho từng mục, không buộc mọi trường hợp thành nhị phân. Ví dụ packet capture thiếu handshake đầu nhưng còn log HTTP 200 có thể vẫn đủ cho câu hỏi “server đã xử lý request chưa”, nhưng không đủ để phân tích thời gian TCP connect.

## 23. Mẫu báo cáo lab hoàn chỉnh

~~~text
TITLE: Thu thập PCAP và đối chiếu HTTP server log
EXERCISE_ID: NET-PCAP-011

SCOPE:
  Host: Linux lab do người học quản lý
  Interface: lo
  Network: 127.0.0.1 only
  Protocol/port: TCP/8765, HTTP synthetic
  Authorization: lab cá nhân, không có traffic production

OBJECTIVE:
  Chứng minh request synthetic xuất hiện trong PCAP
  và server log, đối chiếu timestamp và kết quả HTTP.

TOOLS:
  tcpdump; curl; Python 3 http.server; TShark (optional)

COLLECTION:
  PCAP: lab-011.pcap
  Capture filter: tcp and port 8765
  Snaplen: 256
  Capture start/end UTC: <ghi thời gian thực>
  Packet captured/kernel dropped: <ghi thống kê thực>
  Server log: http-server.log

INTEGRITY:
  SHA-256 PCAP: <tính từ file thực>
  SHA-256 server log: <tính từ file thực>
  Người thu thập: <authorized operator>
  Vị trí lưu: <đường dẫn lưu được kiểm soát>

RESULT:
  Client HTTP status: <thực tế>
  Server request path: <thực tế>
  PCAP request/response: <có hoặc không và packet number>
  Correlation marker: NET-PCAP-011
  Clock offset / timezone: <ghi nhận>

CONCLUSION:
  <diễn giải dựa trên cả PCAP và log>
LIMITATIONS:
  Loopback only; no Internet, firewall hoặc TLS inspection.
NEXT STEPS:
  <nếu có> cải thiện filter, timestamp, logging, retest.
CLEANUP:
  Đã dừng server/capture; xử lý file theo retention của lab.
~~~

Nếu dùng report này trong điều tra thật, cần thêm incident/ticket ID, asset owner, chain of custody, approval, phân loại dữ liệu, đường lưu chứng cứ, thay đổi cấu hình liên quan và kiểm soát truy cập.

## 24. Checklist thực hành

### Trước khi capture

- [ ] Có câu hỏi điều tra và mục tiêu quan sát cụ thể.
- [ ] Đã xác minh đúng owner, asset, interface và phạm vi thu.
- [ ] Không có dữ liệu thật hoặc tài nguyên ngoài lab trong ví dụ loopback.
- [ ] Có filter, thời lượng, snaplen và giới hạn dung lượng.
- [ ] Đã biết timezone và tình trạng đồng hồ của các nguồn log.
- [ ] Đã chọn nơi lưu file, quyền truy cập, retention và người xử lý.

### Trong khi capture

- [ ] Đã bắt đầu tcpdump trước request synthetic.
- [ ] Client gửi marker NET-PCAP-011 tới 127.0.0.1:8765.
- [ ] Server log ghi nhận request và mã phản hồi.
- [ ] Dừng capture bằng Ctrl+C, ghi packet/drop stats.
- [ ] Không đổi filter hoặc interface mà không ghi lại phiên thu mới.

### Sau khi capture

- [ ] Kiểm tra PCAP/log tồn tại, đọc được và khớp phạm vi.
- [ ] Đã tách capture filter khỏi display filter.
- [ ] Đã đối chiếu timestamp, request marker, 5-tuple và status.
- [ ] Đã ghi hash SHA-256 và thông tin bàn giao/bảo vệ file.
- [ ] Đã mô tả những gì chứng cứ có thể và không thể chứng minh.
- [ ] Đã viết timeline, kết luận và giới hạn rõ ràng.
- [ ] Đã dừng tiến trình lab và dọn dữ liệu theo chính sách.

## 25. Câu hỏi tự kiểm tra và mở rộng

1. Một firewall ghi ALLOW nhưng ứng dụng không có access log: cần kiểm tra ở đâu và vì sao?
2. Vì sao một PCAP không có SYN không nhất thiết chứng minh phiên TCP thiếu bắt tay ba bước?
3. Khi capture -s 256, điểm giới hạn nào có thể ảnh hưởng phân tích HTTP hoặc TLS?
4. Khác biệt giữa BPF capture filter và Wireshark display filter là gì?
5. Vì sao không thể ghép log trên firewall pre-NAT với proxy post-NAT chỉ dựa vào IP nguồn?
6. Nêu ba trường hữu ích giúp đối chiếu packet với DNS resolver log.
7. TLS được mã hóa ảnh hưởng thế nào đến khả năng thấy URL, HTTP status và payload?
8. Nếu server log thiếu timezone, phải làm gì trước khi ghép với frame.time_epoch?
9. Vì sao hash SHA-256 là cần nhưng chưa đủ để đảm bảo chain of custody?
10. Khi tcpdump báo kernel dropped packets, kết luận nào từ PCAP trở nên yếu hơn?
11. Ở một mạng dùng IPsec, nên thu ở vị trí nào để thấy traffic nội bộ thay vì chỉ thấy tunnel endpoints?
12. Tại sao IDS alert không đồng nghĩa có xâm nhập thành công?
13. Trình bày tiêu chí PASS/FAIL/INCONCLUSIVE cho mục tiêu “server nhận được request synthetic”.
14. Nếu một rule firewall mới gây timeout, nên thu gói và log trước/sau enforcement point như thế nào?
15. Sau điều tra, những dữ liệu nào phải được hạn chế truy cập hoặc xóa theo retention?

### Bài tập nâng cao (không bắt buộc)

- **Điều chỉnh snaplen trong lab:** so sánh hai bản capture với -s 96 và -s 256 trên lưu lượng synthetic, ghi rõ trường nào bị cắt và không thể kết luận.
- **Thử nhiều request:** dùng hai marker synthetic khác nhau vào cùng server loopback, phân biệt bằng URI và TCP stream. Không dùng tài khoản hay token thật.
- **Giả lập log trễ:** tạo bảng timeline mà SIEM ingest trễ hơn server event; sắp xếp theo event time thay vì ingest time.
- **Bài phân tích thiếu chứng cứ:** dùng tình huống ở mục 20 để đề xuất capture point thứ hai, những trường log cần thu và kết luận tạm thời phù hợp.

**Ghi nhớ:** một bản PCAP chỉ phản ánh **những gói sensor đã quan sát tại vị trí và thời gian cụ thể**. Giá trị điều tra xuất hiện khi ghép PCAP với log nguồn/đích, firewall, DNS, VPN, IDS/IPS và ứng dụng bằng timestamp, 5-tuple, NAT/session ID và marker phù hợp. Thu thập an toàn, chứng minh tính toàn vẹn, mô tả giới hạn và tránh suy luận quá mức là điều kiện để biến dữ liệu mạng thành bằng chứng hữu ích cho vận hành và bảo mật.

