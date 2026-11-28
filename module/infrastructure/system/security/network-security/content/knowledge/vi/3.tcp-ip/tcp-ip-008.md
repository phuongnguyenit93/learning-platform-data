# UDP và đặc điểm không kết nối

**UDP (User Datagram Protocol)** là giao thức tầng vận chuyển (transport layer) trong bộ giao thức TCP/IP, thường được sử dụng khi ứng dụng cần trao đổi thông điệp gọn, phản hồi nhanh hoặc tự quyết định cách xử lý mất gói. UDP gửi dữ liệu dưới dạng **datagram**: mỗi lần ứng dụng gửi một thông điệp, UDP đóng gói nó với thông tin cổng nguồn, cổng đích và chuyển cho IP đưa tới đích. Giao thức **không thiết lập phiên kết nối trước khi gửi**, không tự đánh số thứ tự thông điệp để bảo đảm giao đúng trình tự và không tự truyền lại các gói đã mất.

Tính đơn giản này giúp UDP phù hợp với DNS, DHCP, NTP, truyền thông thời gian thực và các giao thức được xây dựng bên trên như QUIC. Tuy vậy, với bảo mật mạng, việc UDP ít duy trì trạng thái hơn TCP cũng làm thay đổi cách thiết kế firewall, NAT, giám sát, chống giả mạo và giảm thiểu DDoS.

Bài học trong chương **TCP IP** thuộc module **SECURITY_NETWORK_SECURITY** trình bày UDP từ cách vận hành đến các nguyên tắc bảo vệ: phân đoạn, kiểm soát luồng, xác thực kết nối, quan sát lưu lượng và mô hình hóa mối đe dọa.

## 1. UDP nằm ở đâu trong mô hình TCP/IP?

Một yêu cầu có thể đi qua các lớp như sau:

~~~mermaid
flowchart TB
    APP["Ứng dụng: DNS, thoại, game, QUIC..."]
    UDP["Transport: UDP (port nguồn, port đích)"]
    IP["Internet: IPv4 / IPv6 (địa chỉ và định tuyến)"]
    LINK["Liên kết: Ethernet / Wi-Fi / mạng khác"]
    APP --> UDP --> IP --> LINK
~~~

Các lớp đảm nhiệm vai trò khác nhau:

| Lớp | Thông tin quan trọng | Nhiệm vụ |
| --- | --- | --- |
| Ứng dụng | Dữ liệu nghiệp vụ, quy tắc yêu cầu/phản hồi | Quyết định nội dung, thời điểm, cách xử lý mất hoặc lặp thông điệp |
| UDP | Cổng nguồn, cổng đích, độ dài, checksum | Chuyển thông điệp tới đúng tiến trình/ứng dụng; kiểm tra lỗi theo cấu hình giao thức |
| IP | Địa chỉ IP nguồn/đích, định tuyến | Đưa IP packet qua các mạng; không bảo đảm giao thành công |
| Liên kết | Địa chỉ và cấu trúc frame theo công nghệ | Truyền frame trên từng chặng mạng |

**IP xác định host đích; cổng UDP giúp xác định tiến trình đích.** Ví dụ, hai ứng dụng trên cùng một máy có thể nhận datagram ở các cổng UDP khác nhau.

UDP là **giao thức không kết nối (connectionless)** ở tầng vận chuyển: không có bắt tay ba bước như TCP và không có trạng thái kết nối UDP riêng được thương lượng giữa hai phía trước khi gửi. Tuy nhiên, một ứng dụng **có thể duy trì phiên logic** của chính nó phía trên UDP. QUIC là ví dụ: QUIC dùng UDP để chuyển gói nhưng tự triển khai quá trình thiết lập kết nối, mã hóa, điều khiển tắc nghẽn và cơ chế tin cậy cho các stream.

### 1.1. Datagram khác byte stream

Với TCP, ứng dụng trao đổi **luồng byte liên tục**; ranh giới giữa các lần ghi không được bảo tồn thành ranh giới đọc. Với UDP, mỗi lần gửi thông thường tương ứng **một datagram độc lập**, nên bên nhận có thể phân biệt thông điệp nếu nó được giao đầy đủ.

Ví dụ ứng dụng gửi lần lượt:

- Datagram A: **HELLO**
- Datagram B: **STATUS**
- Datagram C: **DONE**

Bên nhận có thể quan sát A, B, C; hoặc B rồi A; hoặc chỉ A và C; hoặc không nhận thông điệp nào. Mạng và các thành phần phía trên UDP cũng có thể gây hiện tượng trùng thông điệp. UDP không có cơ chế sửa những tình huống này cho ứng dụng.

Nếu vùng đệm nhận nhỏ hơn kích thước datagram, một số API/socket sẽ **cắt phần dữ liệu vượt quá**. Phần dư thường không tự được giao ở lần nhận tiếp theo như cách đọc tiếp một TCP stream. Vì vậy, kích thước buffer và giới hạn thông điệp phải được quy định rõ.

## 2. Cấu trúc header của một UDP datagram

Theo cấu trúc UDP cơ bản, header cố định dài **8 byte**, gồm bốn trường, mỗi trường 16 bit:

~~~text
 0                   15 16                  31
+----------------------+----------------------+
|    Source Port       |   Destination Port   |
+----------------------+----------------------+
|      Length          |      Checksum        |
+----------------------+----------------------+
|                 Application Data            |
|                      ...                    |
+---------------------------------------------+
~~~

| Trường | Kích thước | Ý nghĩa |
| --- | --- | --- |
| **Source Port** | 16 bit | Cổng của bên gửi, thường được dùng để bên nhận biết nơi gửi phản hồi; có thể bằng 0 khi không dùng cổng nguồn theo quy định UDP |
| **Destination Port** | 16 bit | Cổng dịch vụ nhận datagram; trường bắt buộc có ý nghĩa để phân phối dữ liệu tới ứng dụng |
| **Length** | 16 bit | Độ dài UDP header **cộng** UDP payload, tính bằng byte; tối thiểu là 8 byte trong datagram thông thường |
| **Checksum** | 16 bit | Giúp phát hiện lỗi dữ liệu, có xét cả một số trường IP qua pseudo-header; không phải mã xác thực chống kẻ tấn công |

Cổng UDP thuộc miền giá trị 16 bit. Theo quy ước thực hành, các cổng **0–1023** thường là cổng dịch vụ chuẩn/đặc quyền; **1024–49151** là cổng đăng ký; **49152–65535** là dải động/riêng. Đây là phân loại phục vụ cấp phát và sử dụng cổng, không phải cơ chế bảo mật. Cổng nguồn của máy khách thường được hệ điều hành chọn từ dải cổng tạm thời theo cấu hình thực tế.

### 2.1. Checksum và giới hạn bảo vệ

Checksum UDP được tính trên header UDP, dữ liệu và một **pseudo-header** lấy thông tin mạng như IP nguồn/đích và định danh giao thức. Pseudo-header giúp phát hiện một số lỗi dẫn datagram tới sai địa chỉ; nó không được gửi như một phần header UDP.

- Với **UDP trên IPv4**, trường checksum có thể bằng 0 để biểu thị **không tính checksum UDP**. Cấu hình này làm giảm khả năng phát hiện dữ liệu lỗi và không nên tùy tiện lựa chọn.
- Với **UDP trên IPv6**, checksum UDP **thông thường là bắt buộc**; chỉ có các ngoại lệ được quy định hẹp cho một số trường hợp tunnel cụ thể. Không xem các ngoại lệ đó là quy tắc chung.
- Checksum chỉ hỗ trợ **phát hiện lỗi truyền dữ liệu**, không xác thực danh tính nguồn, không chống được kẻ tấn công chủ động tự tạo hoặc thay đổi datagram rồi tính lại checksum.

Nếu ứng dụng cần **confidentiality, integrity chống giả mạo và xác thực đầu mút**, cần cơ chế mật mã phù hợp như **DTLS, QUIC/TLS hoặc IPsec**, kết hợp với xác thực và phân quyền ở tầng ứng dụng theo yêu cầu.

### 2.2. Địa chỉ IP và cổng có phải là danh tính?

Bộ thông tin **IP nguồn, port nguồn, IP đích, port đích và giao thức** hữu ích để quan sát luồng lưu lượng. Tuy nhiên, một datagram UDP có thể mang **địa chỉ IP nguồn giả** trong một số bối cảnh mạng nếu không có bộ lọc chống giả mạo. Ngay cả khi IP nguồn là thật, địa chỉ/port vẫn không chứng minh một người dùng hay một dịch vụ cụ thể có quyền gửi dữ liệu.

Không nên coi địa chỉ IP hoặc việc firewall cho phép cổng UDP là đủ để xác thực và phân quyền yêu cầu nghiệp vụ.

## 3. Vì sao gọi UDP là “không kết nối”?

Khi ứng dụng gọi thao tác gửi UDP, giao thức không bắt đầu quy trình tương đương **SYN → SYN/ACK → ACK** của TCP. Một máy có thể gửi datagram tới IP/port mà chưa biết có tiến trình nào đang lắng nghe tại đích hay không.

~~~mermaid
sequenceDiagram
    participant A as Client
    participant B as Server
    A->>B: UDP datagram #1
    A->>B: UDP datagram #2
    Note over A,B: Không có bắt tay UDP, ACK hay retransmission tự động
    B-->>A: Phản hồi ứng dụng (nếu có)
    Note over A: Nếu timeout, ứng dụng quyết định cách xử lý
~~~

Các tính chất cần phân biệt:

1. **Không thiết lập kết nối ở UDP:** datagram có thể được gửi độc lập, không cần trao đổi điều khiển UDP trước.
2. **Không bảo đảm giao hàng:** datagram có thể rơi ở host, firewall, router, buffer, hoặc mạng trung gian mà ứng dụng gửi không được thông báo ngay.
3. **Không bảo đảm thứ tự:** datagram đến sau có thể được nhận trước.
4. **Không tự loại bỏ trùng lặp:** ứng dụng phải có cơ chế phân biệt và xử lý nếu thứ tự hoặc tính duy nhất là quan trọng.
5. **Không có flow control và congestion control tích hợp như TCP:** ứng dụng hoặc giao thức phía trên cần tự giới hạn tốc độ gửi để tránh gây tắc nghẽn.
6. **Không có mã hóa hay xác thực tích hợp:** UDP thuần không bảo vệ nội dung và danh tính trước người tấn công trên đường truyền.

Một socket UDP đôi khi được gọi **connect()** trong API lập trình. Thao tác này thường chỉ **gán địa chỉ peer mặc định và lọc datagram đầu vào theo peer** tại hệ điều hành; nó **không tạo bắt tay UDP hay bảo đảm datagram đến đích**.

### 3.1. Nếu cổng đích không có dịch vụ?

Ở một số mạng, host nhận datagram tới cổng không lắng nghe có thể gửi ICMP **Destination Unreachable / Port Unreachable**. Tuy nhiên, firewall, chính sách hệ điều hành hoặc cấu hình mạng có thể chặn thông điệp đó. Do vậy:

- **Không có phản hồi** chưa đủ để kết luận cổng đóng hay dịch vụ đã ngừng chạy.
- **Gửi thành công tại máy khách** chỉ xác nhận hệ điều hành chấp nhận yêu cầu gửi, chưa chứng minh bên nhận xử lý nó.
- **Có gói phản hồi ứng dụng** chứng minh một phần trao đổi đã diễn ra, nhưng vẫn phải kiểm tra phản hồi có hợp lệ và đến từ peer đáng tin cậy hay không.

## 4. So sánh UDP và TCP

| Khía cạnh | UDP | TCP |
| --- | --- | --- |
| Kiểu truyền dữ liệu | Datagram giữ ranh giới thông điệp | Luồng byte không giữ ranh giới lần ghi |
| Bắt tay tầng vận chuyển | Không | Có thiết lập kết nối trước trao đổi dữ liệu |
| Header cơ bản | 8 byte | 20 byte, chưa tính option |
| Giao dữ liệu đúng thứ tự | Không được bảo đảm | Dữ liệu ứng dụng được trình bày theo thứ tự luồng byte |
| Truyền lại khi mất dữ liệu | Không tích hợp | Có cơ chế xác nhận và truyền lại |
| Flow control | Không tích hợp | Có cơ chế cửa sổ nhận |
| Congestion control | Không tích hợp | Có cơ chế kiểm soát tắc nghẽn |
| Broadcast/multicast | Có thể dùng với UDP tùy mạng và ứng dụng | Kết nối TCP thông thường là giữa hai đầu mút, không dùng broadcast/multicast |
| Bảo vệ mật mã | Không tích hợp | TCP thuần cũng không mã hóa; thường kết hợp TLS |
| Ví dụ | DNS, DHCP, NTP, RTP, QUIC | HTTPS dùng TCP/TLS, SSH, nhiều kết nối cơ sở dữ liệu |

**UDP không đồng nghĩa luôn nhanh hơn TCP.** Header nhỏ và không cần bắt tay tầng UDP giúp giảm một số chi phí, nhưng độ trễ thực tế còn phụ thuộc mức mất gói, tốc độ, kích thước datagram, thiết kế ứng dụng, điều khiển tắc nghẽn và giao thức bảo mật phía trên. Với một ứng dụng phải tự bổ sung retransmission và bảo đảm thứ tự, tổng độ phức tạp có thể ngang hoặc lớn hơn dùng một giải pháp tin cậy có sẵn.

Ví dụ, **HTTP/3 chạy trên QUIC/UDP**, nhưng QUIC tự cung cấp độ tin cậy cho stream, điều khiển tắc nghẽn và bảo mật dựa trên TLS 1.3. Không được suy luận rằng HTTP/3 gửi dữ liệu web theo kiểu “mất gói cũng bỏ qua” chỉ vì lớp dưới là UDP.

## 5. Khi nào ứng dụng sử dụng UDP?

| Ứng dụng/giao thức | Cổng thường gặp | Vì sao có thể sử dụng UDP? | Điều cần lưu ý |
| --- | --- | --- | --- |
| **DNS truyền thống** | UDP/53 | Câu hỏi/phản hồi nhỏ, dễ gửi một datagram | DNS vẫn dùng TCP/53 trong nhiều trường hợp, ví dụ khi cần xử lý phản hồi bị cắt hoặc theo chính sách giao thức; DoT/DoH có phương thức vận chuyển khác |
| **DHCPv4** | UDP/67 (server), UDP/68 (client) | Trao đổi cấp địa chỉ lúc client có thể chưa có IP hoàn chỉnh | Có thể dùng broadcast IPv4 trong một số bước; cần DHCP snooping và kiểm soát DHCP giả mạo ở mạng phù hợp |
| **NTP** | UDP/123 | Trao đổi thông tin đồng bộ thời gian theo mô hình hỏi/đáp | Cần giới hạn truy cập máy chủ NTP và xác thực khi phù hợp |
| **RTP/VoIP** | Cổng UDP theo phiên/cấu hình | Ưu tiên dữ liệu mới; dữ liệu thoại quá trễ thường ít giá trị | Dùng SRTP/DTLS-SRTP hoặc cơ chế phù hợp để bảo vệ media, cộng với xử lý jitter và mất gói |
| **Game thời gian thực** | Cổng do ứng dụng quy định | Gửi cập nhật vị trí/trạng thái với tần suất cao | Cần sequence number, cơ chế bù mất gói và chống gian lận ở tầng ứng dụng |
| **QUIC / HTTP/3** | Thường UDP/443 | Dùng UDP làm nền cho giao thức vận chuyển hiện đại | QUIC tự triển khai kết nối, mã hóa, xác thực và điều khiển tắc nghẽn |
| **Syslog qua UDP** | Thường UDP/514 | Cách vận chuyển bản tin log đơn giản | Không bảo đảm giao hoặc bảo mật; với log quan trọng, cân nhắc vận chuyển bảo vệ và tin cậy hơn |

**Port không đồng nghĩa chắc chắn có dịch vụ.** Việc thấy UDP/53 không đủ để khẳng định gói là DNS hợp lệ; ứng dụng có thể dùng cổng khác hoặc gửi dữ liệu tùy ý trên cổng phổ biến. Phân tích an toàn cần dựa trên cấu hình, nội dung có thể quan sát, danh tính nguồn và bối cảnh luồng.

## 6. Kích thước datagram, MTU và hiện tượng phân mảnh

UDP có trường Length 16 bit bao gồm header 8 byte. Với **IPv4 không có option**, kích thước tối đa lý thuyết của UDP payload trong IP packet dài tối đa 65.535 byte là:

~~~text
IPv4 datagram tối đa       = 65.535 byte
IPv4 header tối thiểu      =     20 byte
UDP header                 =      8 byte
UDP payload tối đa IPv4    = 65.535 - 20 - 8
                          = 65.507 byte
~~~

**Đây không phải kích thước gói nên dùng trong vận hành.** Trên đường truyền thật, giới hạn quan trọng là **MTU (Maximum Transmission Unit)** nhỏ nhất của các chặng. Ethernet thường có IP MTU 1.500 byte trong cấu hình phổ biến.

Ví dụ, để một UDP/IPv4 packet đi qua Ethernet MTU 1.500 byte **mà không cần phân mảnh**, giả sử IPv4 header 20 byte và không có overhead khác:

~~~text
UDP payload tối đa ví dụ = 1.500 - 20 - 8 = 1.472 byte
~~~

Với IPv6 header cơ bản 40 byte, không có extension header, ví dụ tương đương là **1.452 byte**. VPN, tunnel, PPPoE, header mở rộng và các đường truyền khác có thể làm MTU hiệu dụng **nhỏ hơn** nữa.

### 6.1. Vì sao fragmentation gây khó khăn?

- **IPv4** có cơ chế phân mảnh khi điều kiện và cờ điều khiển cho phép; nếu packet quá lớn và không được phép phân mảnh, nó có thể bị loại bỏ và mạng có thể trả thông điệp ICMP liên quan đến MTU.
- **IPv6 router không phân mảnh packet trên đường đi**; host nguồn phải điều chỉnh kích thước và xử lý theo cơ chế IPv6 phù hợp.
- Khi một datagram bị phân mảnh thành nhiều IP fragment, **mất một mảnh có thể khiến cả datagram không thể tái lắp**.
- Fragmentation cũng làm phức tạp quan sát firewall/IDS, reassembly và xử lý tại host, tùy khả năng thiết bị.

Một số firewall hoặc mạng chặn ICMP cần cho **Path MTU Discovery (PMTUD)**, dẫn tới lỗi khó chẩn đoán: datagram nhỏ đi qua bình thường, datagram lớn lại timeout. Vì vậy, với ứng dụng UDP hãy đo đường đi, giới hạn kích thước thông điệp, tránh phân mảnh khi có thể và không mặc định rằng payload 65 KB sẽ hoạt động.

## 7. Quan hệ giữa UDP, firewall, NAT và phân đoạn mạng

### 7.1. Firewall lọc UDP như thế nào?

Firewall có thể kiểm tra **IP nguồn/đích, UDP port, zone/interface, danh tính workload hoặc chính sách ứng dụng** tùy sản phẩm. Với TCP, firewall stateful có thể theo dõi các trạng thái kết nối và cờ TCP. Với UDP, vì không có bắt tay và kết thúc phiên tích hợp, firewall/NAT thường duy trì **trạng thái giả lập theo lưu lượng và timeout** để cho phép datagram phản hồi phù hợp.

Hệ quả:

- Bên gửi đã gửi một datagram không có nghĩa firewall sẽ cho phép mọi lưu lượng UDP chiều ngược lại.
- Một ánh xạ UDP của NAT hoặc mục theo dõi trạng thái có thể **hết hạn khi không có lưu lượng**; thời gian tùy thiết bị/cấu hình.
- Nếu ứng dụng phải nhận datagram chủ động từ Internet, cần thiết kế **đường vào rõ ràng**: ví dụ load balancer có hỗ trợ UDP, NAT/port mapping hoặc gateway phù hợp; không dựa vào kết nối outbound tồn tại mãi.
- Rule mở rộng **any-source → any-destination UDP** làm tăng bề mặt tấn công và khó xác định hành vi hợp lệ.

Ví dụ, dịch vụ đồng bộ thời gian nội bộ chỉ dành cho các máy chủ ứng dụng:

| Nguồn | Đích | Giao thức | Quyết định | Giải thích |
| --- | --- | --- | --- | --- |
| 10.10.20.0/24 | 10.10.30.15 | UDP/123 | Allow | Các ứng dụng được cấp quyền truy vấn NTP nội bộ |
| Internet | 10.10.30.15 | UDP/123 | Deny | Dịch vụ NTP nội bộ không được công khai |
| 10.10.20.0/24 | Mọi IP/mọi UDP port | UDP/* | Deny theo mặc định, ngoại lệ có phê duyệt | Hạn chế kết nối ngoài nhu cầu |

Các dải trên là **ví dụ**. Trên firewall stateful, luồng phản hồi phù hợp thường được cấp thông qua trạng thái đang theo dõi; với ACL stateless, có thể phải xét chính sách chiều ngược và dải cổng phía nhận một cách riêng biệt.

### 7.2. Phân đoạn không chỉ là tách subnet

Một mạng có nhiều VLAN hoặc subnet chưa chắc đã hạn chế được UDP giữa các hệ thống. Phải xác định **điểm thực thi chính sách** trên đường định tuyến giữa các subnet/VPC và kiểm tra gói thực sự đi qua điểm đó.

- **On-premises:** ACL trên router/L3 switch, firewall nội bộ, DHCP snooping, giám sát tại điểm giao giữa các VLAN.
- **Cloud:** VPC/VNet subnet, security group/network policy, cloud firewall, route table, flow logs, private endpoint.
- **Hybrid:** VPN/IPsec, cloud gateway, firewall hai phía, kiểm soát CIDR, NAT và đường phản hồi; không cho phép UDP trên toàn bộ hai miền chỉ vì đã nối mạng riêng.

Một số IDS/IPS theo dõi UDP dựa vào metadata/luồng, nhưng **không thể phân tích payload đã được mã hóa** nếu không có điểm quan sát thích hợp. Do đó nên liên kết flow logs với DNS, gateway và log ứng dụng.

## 8. Mối đe dọa bảo mật đặc trưng của UDP

UDP thuần thiếu cơ chế xác thực phiên và mã hóa. Điều này không có nghĩa mọi ứng dụng UDP đều kém an toàn; mức độ an toàn phụ thuộc lớp giao thức được xây dựng bên trên và mạng triển khai.

### 8.1. Giả mạo địa chỉ nguồn (IP spoofing)

Nếu mạng gửi không kiểm soát nguồn hợp lệ, đối tượng tấn công có thể tạo IP packet mang địa chỉ nguồn giả. Dịch vụ UDP thiếu xác thực ứng dụng có thể nhầm nguồn gửi, trả lời sai bên hoặc cho phép thao tác không được phép.

**Bảo vệ:**

- Áp dụng kiểm soát nguồn hợp lệ ở biên mạng, ví dụ **source-address validation theo BCP 38** hoặc uRPF khi phù hợp kiến trúc định tuyến.
- Không dựa vào IP/port để quyết định quyền nghiệp vụ; yêu cầu token, khóa phiên, chứng thực hoặc giao thức mật mã được thiết kế phù hợp.
- Kiểm tra replay, giới hạn thời gian hiệu lực và gắn yêu cầu với danh tính/ngữ cảnh hợp lệ nếu thông điệp có tác động quan trọng.

### 8.2. Reflection và amplification DDoS

Một số dịch vụ UDP trả lời yêu cầu mà không xác thực người gửi. Nếu mạng cho phép **giả mạo địa chỉ nguồn**, phản hồi có thể được gửi tới một địa chỉ nạn nhân khác: đây là **reflection**. Khi phản hồi lớn hơn yêu cầu rất nhiều, có thể xuất hiện **amplification**.

Các dịch vụ UDP như DNS resolver mở, NTP cấu hình không an toàn hoặc dịch vụ giao thức khác có khả năng bị lạm dụng tùy bản triển khai. Vấn đề không nằm ở mọi gói UDP mà ở **giao thức phản hồi, xác thực nguồn và khả năng gửi lượng phản hồi vượt quá yêu cầu**.

**Kiểm soát phòng vệ:**

1. Không công khai dịch vụ UDP không cần thiết; hạn chế resolver, dịch vụ thời gian và các dịch vụ chỉ dùng nội bộ.
2. Giới hạn tỷ lệ phản hồi, số truy vấn và tài nguyên theo thiết kế dịch vụ; cân nhắc hành vi khi nguồn IP có thể bị giả mạo.
3. Thực thi chống spoofing tại mạng nguồn và phối hợp với ISP/nhà cung cấp chống DDoS cho lưu lượng vượt khả năng xử lý tại chỗ.
4. Giám sát lưu lượng UDP bất thường theo nguồn/đích, cổng, kích thước gói, packet-per-second và chênh lệch inbound/outbound.
5. Giữ phần mềm và cấu hình dịch vụ được cập nhật, kiểm tra các tính năng phản hồi lớn không thực sự cần thiết.

**Rate limiting tại máy chủ không thể thay thế lọc ở upstream** khi đường truyền Internet đã nghẽn trước khi lưu lượng đến máy chủ.

### 8.3. Flood và cạn tài nguyên

Do UDP không đòi hỏi bắt tay như TCP, một ứng dụng có thể phải tiếp nhận nhiều datagram mà chưa xác minh được bên gửi. Lưu lượng có thể làm cạn:

- băng thông và năng lực xử lý gói của router/firewall;
- buffer nhận UDP và CPU xử lý packet;
- trạng thái theo dõi tạm thời của firewall/NAT;
- tài nguyên ở tầng ứng dụng nếu mỗi datagram kích hoạt công việc tốn kém.

Cần **đặt giới hạn tài nguyên và tốc độ** trước công việc đắt tiền, tránh tạo phản hồi quá lớn cho nguồn chưa được xác thực, theo dõi tình trạng mất gói/overflow và dùng dịch vụ giảm thiểu DDoS khi có yêu cầu.

### 8.4. Payload giả, replay và nghe lén

Một datagram UDP thông thường không có bảo vệ bí mật hoặc xác thực người gửi. Kẻ có khả năng quan sát đường truyền có thể đọc payload rõ; kẻ có khả năng chèn gói có thể gửi thông điệp giả hoặc phát lại dữ liệu đã thu được.

Giải pháp phù hợp tùy trường hợp:

- **DTLS**: cung cấp cơ chế bảo mật kiểu TLS cho giao tiếp datagram; ứng dụng vẫn phải xử lý ngữ nghĩa nghiệp vụ.
- **QUIC**: cung cấp vận chuyển bảo mật trên UDP với xác thực, quản lý kết nối, điều khiển tắc nghẽn và cơ chế tin cậy phù hợp cho các luồng dữ liệu.
- **IPsec**: bảo vệ lưu lượng IP giữa các đầu mút hoặc gateway, phạm vi phụ thuộc chế độ tunnel/transport và cấu hình.
- **Bảo mật tầng ứng dụng**: xác thực thông điệp, chống replay, kiểm tra quyền và giới hạn dữ liệu đầu vào; nên dùng giao thức/thư viện mật mã đã được kiểm chứng thay vì tự thiết kế.

**Checksum UDP không thay thế các cơ chế trên.** Đặc biệt, mã hóa giữa hai gateway VPN không mặc nhiên xác thực người dùng hoặc tiến trình đang gửi datagram trong mạng ở hai đầu.

## 9. Ví dụ ứng dụng Java: UDP echo chạy trên localhost

Ví dụ này dùng các API chuẩn Java để quan sát rằng UDP gửi một datagram mà **không cần bắt tay tầng vận chuyển**, và bên gửi muốn biết kết quả thì phải **tự chờ phản hồi của ứng dụng**. Mọi trao đổi chỉ xảy ra trên địa chỉ loopback **127.0.0.1**, cổng UDP **9999**.

### 9.1. Máy chủ nhận một datagram

Tạo file **UdpEchoServer.java**:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class UdpEchoServer {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (DatagramSocket socket = new DatagramSocket(9999, loopback)) {
            socket.setSoTimeout(30_000);
            System.out.println("UDP server listening on 127.0.0.1:9999");

            byte[] buffer = new byte[2048];
            DatagramPacket request = new DatagramPacket(buffer, buffer.length);

            try {
                socket.receive(request);
                String message = new String(
                    request.getData(),
                    request.getOffset(),
                    request.getLength(),
                    StandardCharsets.UTF_8
                );

                System.out.println("Received: " + message);
                byte[] answer = ("APP-REPLY: " + message)
                    .getBytes(StandardCharsets.UTF_8);

                socket.send(new DatagramPacket(
                    answer, answer.length, request.getSocketAddress()
                ));
            } catch (SocketTimeoutException e) {
                System.out.println("No datagram received before timeout");
            }
        }
    }
}
~~~

Đây là server minh họa nhận **một thông điệp** rồi kết thúc; buffer 2.048 byte chỉ dành cho dữ liệu thử nhỏ, không nên sao chép cấu hình này như một chuẩn cho mọi ứng dụng.

### 9.2. Máy khách gửi một datagram và chờ phản hồi

Tạo file **UdpEchoClient.java**:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class UdpEchoClient {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setSoTimeout(2_000);

            byte[] data = "HELLO UDP".getBytes(StandardCharsets.UTF_8);
            socket.send(new DatagramPacket(data, data.length, loopback, 9999));
            System.out.println("Datagram submitted to OS");

            byte[] buffer = new byte[2048];
            DatagramPacket reply = new DatagramPacket(buffer, buffer.length);

            try {
                socket.receive(reply);
                System.out.println("Reply: " + new String(
                    reply.getData(),
                    reply.getOffset(),
                    reply.getLength(),
                    StandardCharsets.UTF_8
                ));
            } catch (SocketTimeoutException e) {
                System.out.println("No application reply before timeout");
            }
        }
    }
}
~~~

Biên dịch hai file và chạy trên **hai terminal** trong thư mục chứa file:

~~~bash
javac UdpEchoServer.java UdpEchoClient.java
java UdpEchoServer
~~~

Sau khi server đang lắng nghe, ở terminal thứ hai chạy:

~~~bash
java UdpEchoClient
~~~

Kết quả điển hình:

~~~text
Server:
UDP server listening on 127.0.0.1:9999
Received: HELLO UDP

Client:
Datagram submitted to OS
Reply: APP-REPLY: HELLO UDP
~~~

Chuỗi **APP-REPLY** là phản hồi do **code ứng dụng** tự gửi, **không phải ACK tự động của UDP**.

Thử chạy client khi không có server: thao tác gửi có thể vẫn thành công, nhưng chờ phản hồi sẽ timeout. Tùy hệ điều hành và thông tin lỗi ICMP, socket cũng có thể báo lỗi khác, chẳng hạn **PortUnreachableException**. Không được kết luận chỉ từ một kiểu phản hồi rằng datagram chắc chắn đã tới hay chưa.

### 9.3. Nhìn datagram bằng công cụ quan sát

Trên máy mà bạn có quyền kiểm tra, có thể quan sát UDP ở cổng thử nghiệm:

~~~bash
# Linux: quan sát UDP socket đang lắng nghe
ss -lunp

# Linux: chỉ quan sát cổng UDP demo trên loopback
sudo tcpdump -ni lo 'udp and port 9999'
~~~

Trên Windows PowerShell:

~~~powershell
Get-NetUDPEndpoint | Where-Object { $_.LocalPort -eq 9999 }
~~~

Trong Wireshark, có thể dùng display filter:

~~~text
udp.port == 9999
~~~

Bài thử giúp phân biệt:

- **socket** đang mở trên host;
- **datagram** xuất hiện tại điểm capture;
- **ứng dụng** nhận được và phản hồi thông điệp.

Ba quan sát này không tương đương nhau. Ví dụ thấy datagram ở máy nguồn chưa chứng minh datagram đã vượt qua firewall tới máy đích. Khi điều tra lỗi thực tế, cần kết hợp log ứng dụng, lưu lượng tại cả hai phía và trạng thái NAT/firewall.

## 10. Thiết kế một dịch vụ thu thập telemetry qua UDP

Giả sử một hệ thống nội bộ có các thiết bị giám sát gửi số liệu tới dịch vụ tập trung:

~~~mermaid
flowchart LR
    S["Sensors: 10.40.10.0/24"] -->|"UDP/5005; datagram nhỏ"| F["Firewall phân đoạn"]
    F --> I["Ingest: 10.40.20.10"]
    I --> Q["Queue / storage"]
    I --> M["Log + metric lỗi/mất dữ liệu"]
~~~

Mục tiêu: hạn chế số liệu giả, tránh kẻ gửi flood làm nghẽn dịch vụ và nhận diện được mất dữ liệu.

### 10.1. Thiết kế luồng tối thiểu

| Nguồn | Đích | Port | Quyết định |
| --- | --- | --- | --- |
| 10.40.10.0/24 (nhóm sensor được phép) | 10.40.20.10 | UDP/5005 | Allow có kiểm soát và giới hạn tốc độ |
| Các vùng máy khách khác | 10.40.20.10 | UDP/5005 | Deny, trừ ngoại lệ có phê duyệt |
| Internet công cộng | 10.40.20.10 | UDP/5005 | Deny |
| Ingest service | Queue/storage | Cổng dịch vụ thực tế | Allow theo đúng nhu cầu, xác thực ở tầng ứng dụng |

Đây là dải địa chỉ minh họa. **Rule cho phép subnet sensor là lớp lọc mạng**, chưa chứng thực nguồn dữ liệu. Một thiết bị trong subnet bị chiếm quyền vẫn có thể gửi số liệu giả. Nếu dữ liệu quan trọng, cần cơ chế xác thực thông điệp/kết nối phù hợp, kiểm tra giới hạn giá trị và chống replay.

### 10.2. Format thông điệp và xử lý mất gói

Ví dụ ở mức khái niệm, một thông điệp telemetry có thể chứa:

~~~json
{
  "deviceId": "sensor-17",
  "sequence": 10842,
  "sentAt": "2026-11-28T01:00:00Z",
  "temperatureC": 27.4
}
~~~

**deviceId trong payload chưa phải bằng chứng danh tính.** Hệ thống cần xác thực giá trị này với thông tin mật mã/ngữ cảnh đáng tin cậy trước khi chấp nhận.

Thiết kế xử lý:

1. **Sequence number** cho từng thiết bị giúp phát hiện khoảng trống, gói đến sai thứ tự hoặc trùng lặp ở mức ứng dụng.
2. **Timestamp và giới hạn thời gian hiệu lực** giúp đánh giá độ trễ và một phần chính sách chống replay; cần xem xét đồng bộ đồng hồ.
3. **Deduplication** giúp tránh lưu nhiều lần cùng một số liệu khi sensor tự retry.
4. **Giới hạn kích thước datagram**, số lượng thông điệp mỗi giây và thời gian xử lý giúp giảm cạn tài nguyên.
5. **Queue hoặc bộ đệm có giới hạn** hỗ trợ hấp thụ dao động tải; khi quá tải, phải có chiến lược bỏ dữ liệu cũ/mới hoặc backpressure ở tầng ứng dụng.
6. Nếu mọi số liệu đều bắt buộc được nhận, cần **ACK tầng ứng dụng, retry có giới hạn, lưu bền vững tại thiết bị hoặc chọn transport có bảo đảm tốt hơn**.

Một ứng dụng truyền số đo định kỳ có thể chấp nhận bỏ qua một mẫu cũ nếu mẫu mới sắp đến. Ngược lại, **lệnh điều khiển thiết bị, giao dịch tài chính hoặc sự kiện audit quan trọng** thường không thể dựa vào UDP thuần mà không có cơ chế độ tin cậy và bảo mật bổ sung.

### 10.3. Bằng chứng vận hành nên theo dõi

- Số datagram vào/giây, byte/giây theo sensor, cổng và vùng mạng.
- Tỷ lệ sequence gap, trùng lặp, sai thứ tự, thông điệp quá lớn hoặc lỗi định dạng.
- UDP receive buffer overflow, socket errors, mức dùng CPU và độ dài hàng đợi.
- Firewall drops, thay đổi ACL, số phiên giả lập UDP trong NAT/firewall.
- Chênh lệch thời gian gửi–nhận và khả năng truy vấn dữ liệu sau lưu trữ.
- Cảnh báo khi số lượng nguồn, kích thước datagram hay lưu lượng phản hồi tăng đột ngột.

Những chỉ số này giúp đội bảo mật và vận hành phân biệt **mất gói tự nhiên**, **lỗi cấu hình**, **sự cố hiệu năng** và **lưu lượng tấn công**.

## 11. Các nhầm lẫn thường gặp

1. **“UDP không có kết nối nên không thể có phiên.”** UDP không thương lượng kết nối ở tầng vận chuyển; giao thức trên nó vẫn có thể tạo phiên riêng, như QUIC.
2. **“UDP không tin cậy nên luôn mất gói.”** UDP không **bảo đảm** giao, nhưng datagram vẫn có thể tới bình thường trên mạng hoạt động tốt.
3. **“Gửi socket thành công nghĩa là server nhận được.”** Thao tác gửi thành công không chứng minh bên nhận đã đọc hoặc xử lý.
4. **“Dùng UDP chắc chắn nhanh hơn TCP.”** Hiệu năng còn phụ thuộc tổn thất mạng, cách xử lý của ứng dụng và các cơ chế bảo vệ, điều khiển lưu lượng.
5. **“Có checksum là chống được sửa gói có chủ đích.”** Checksum không xác thực nguồn và có thể bị tính lại; cần cơ chế mật mã phù hợp.
6. **“UDP không có trạng thái nên firewall không theo dõi được.”** Stateful firewall và NAT có thể tạo trạng thái tạm thời theo luồng UDP với idle timeout.
7. **“UDP là broadcast.”** UDP có thể dùng unicast, broadcast trong IPv4 hoặc multicast khi mạng và ứng dụng hỗ trợ; không phải mọi datagram đều được phát tới tất cả host. IPv6 không dùng broadcast.
8. **“Thấy UDP/53 là DNS hợp lệ.”** Port chỉ là thông tin định tuyến ứng dụng, không xác nhận cấu trúc nội dung, danh tính hay quyền.
9. **“Chặn hết ICMP thì UDP an toàn hơn.”** ICMP cần thiết cho báo lỗi và PMTUD trong nhiều tình huống; chặn bừa bãi có thể gây lỗi khó chẩn đoán.
10. **“VPN có UDP nghĩa là mọi ứng dụng UDP bên trong được bảo vệ hoàn toàn.”** Phạm vi tunnel phụ thuộc cấu hình; an toàn đầu mút và quyền ứng dụng vẫn phải được kiểm tra.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một client gửi ba datagram UDP A, B và C. Server nhận C trước A, không nhận B. Đây có phải vi phạm bảo đảm của UDP?

**Trả lời:** Không. UDP không bảo đảm thứ tự và không tự truyền lại datagram bị mất. Nếu thứ tự quan trọng, ứng dụng cần sequence number và cơ chế xử lý phù hợp.

**Câu 2.** Một ứng dụng UDP gọi connect() trên socket. Điều đó có nghĩa nó đã bắt tay với server như TCP chưa?

**Trả lời:** Chưa. connect() của socket UDP thường chỉ ghi nhận peer mặc định và ảnh hưởng cách gửi/nhận ở phía hệ điều hành, không tạo phiên bắt tay UDP.

**Câu 3.** Datagrams mang checksum hợp lệ có chắc đến từ server đáng tin cậy không?

**Trả lời:** Không. Checksum giúp phát hiện lỗi ngẫu nhiên, không xác thực danh tính. Cần DTLS, QUIC hoặc bảo vệ tầng ứng dụng phù hợp.

**Câu 4.** Vì sao một datagram UDP payload 10 KB có thể hoạt động trong mạng nội bộ nhưng timeout qua kết nối VPN?

**Trả lời:** Tunnel làm giảm MTU hiệu dụng. Gói lớn có thể phải phân mảnh hoặc bị loại bỏ; PMTUD có thể không hoạt động đúng nếu ICMP cần thiết bị chặn. Cần kiểm tra MTU, đường đi và kích thước datagram.

**Câu 5.** Firewall chỉ cho phép UDP từ subnet sensor nhưng số liệu vẫn bị giả mạo. Nguyên nhân khả dĩ là gì?

**Trả lời:** IP nguồn không phải danh tính ứng dụng; thiết bị trong subnet có thể bị xâm nhập hoặc có nguồn giả mạo nếu mạng không kiểm soát địa chỉ. Cần xác thực thông điệp/thiết bị, kiểm tra dữ liệu và giám sát.

**Câu 6.** Một dịch vụ DNS mở trả phản hồi lớn tới địa chỉ không đúng người hỏi. Hai rủi ro chính là gì, và cách hạn chế?

**Trả lời:** Rủi ro reflection/amplification và tiêu tốn băng thông/tài nguyên. Hạn chế truy vấn và phản hồi, giới hạn resolver công khai không cần thiết, kiểm soát nguồn hợp lệ tại mạng, giám sát và kết hợp bảo vệ DDoS ở upstream.

## 13. Checklist khi triển khai dịch vụ UDP an toàn

- [ ] Xác định rõ ứng dụng **có chấp nhận mất, trùng hoặc sai thứ tự thông điệp không**.
- [ ] Thiết kế **ACK, retry, sequence, deduplication, idempotency** nếu nghiệp vụ yêu cầu.
- [ ] Định nghĩa **giới hạn kích thước datagram** có xét MTU và overhead tunnel; xử lý dữ liệu vượt kích thước.
- [ ] Xác định IP/port nguồn–đích, subnet, vùng mạng; áp dụng **default deny** và cấp quyền theo luồng cần thiết.
- [ ] Không dùng IP/port hoặc checksum làm cơ chế xác thực; bổ sung **mã hóa, chứng thực và phân quyền** thích hợp.
- [ ] Xem xét **source validation**, ngăn reflection/amplification, giới hạn phản hồi và phối hợp giảm thiểu DDoS.
- [ ] Kiểm tra **state timeout** của firewall/NAT, đặc biệt khi ứng dụng nhàn rỗi hoặc dùng kết nối hybrid.
- [ ] Bật telemetry cho **packet loss, buffer drops, timeout, sequence gap, flow logs** và sự kiện bảo mật.
- [ ] Kiểm thử có kiểm soát tình huống **mất gói, đảo thứ tự, trùng gói, thay đổi đường đi, tăng độ trễ và ngắt kết nối**.
- [ ] Có runbook để phân biệt lỗi **DNS, route, firewall, MTU, socket, bảo mật tầng ứng dụng và quá tải**.

**Ghi nhớ:** UDP cung cấp kênh truyền datagram đơn giản, header nhỏ và không có bắt tay tầng vận chuyển. Đổi lại, UDP **không tự bảo đảm độ tin cậy, thứ tự, điều khiển tắc nghẽn hay bảo mật**. Khi thiết kế mạng an toàn, luôn đánh giá **giao thức ứng dụng chạy trên UDP**, ranh giới mạng, chính sách firewall/NAT, nguy cơ giả mạo và DDoS, giới hạn MTU, cùng khả năng giám sát và phục hồi.
