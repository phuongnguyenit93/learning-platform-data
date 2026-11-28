# Tầng transport (Transport Layer) trong mô hình OSI

Trong chương **OSI và giao thức**, tầng transport (tầng vận chuyển, **Layer 4**) giải quyết một câu hỏi rất thực tế: khi một máy tính chạy nhiều ứng dụng cùng lúc, làm sao dữ liệu đi qua mạng được chuyển đến **đúng tiến trình**, và ứng dụng có thể kỳ vọng điều gì về cách dữ liệu được chuyển giao? Hiểu tầng này là nền tảng để phân tích lưu lượng TCP/UDP, thiết kế quy tắc firewall, nhận diện dấu hiệu tấn công và xử lý sự cố kết nối trong hệ thống mạng an toàn.

Sau bài học, bạn có thể:

- Giải thích vị trí của tầng transport và phân biệt chức năng của nó với tầng network và application.
- Đọc địa chỉ IP, cổng, giao thức và bộ thông tin định danh một luồng kết nối.
- Mô tả cách TCP thiết lập kết nối, truyền dữ liệu đáng tin cậy, kiểm soát luồng và tắc nghẽn; so sánh với UDP.
- Nhận biết QUIC/HTTP/3 sử dụng UDP như thế nào và vì sao TCP/UDP tự thân không bảo mật nội dung.
- Dùng thông tin tầng transport để lập quy tắc bảo vệ, đọc packet capture và khoanh vùng lỗi kết nối.

## 1. Tầng transport nằm ở đâu trong mô hình mạng?

Mô hình OSI có bảy tầng. Tầng transport nằm **trên tầng network (tầng 3)** và **dưới tầng session (tầng 5)**. Trong cách triển khai thực tế theo TCP/IP, ứng dụng thường dùng trực tiếp API socket của TCP hoặc UDP; việc ánh xạ các giao thức hiện đại vào bảy tầng OSI chỉ mang tính mô hình hóa.

| Tầng / thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Application (và các chức năng tầng trên) | Quy định ý nghĩa thông điệp, nghiệp vụ và giao thức ứng dụng | HTTP, DNS, SSH |
| **Transport – Layer 4** | Chuyển dữ liệu giữa các tiến trình, phân biệt cổng; tùy giao thức có thể bảo đảm thứ tự, truyền lại và kiểm soát tốc độ | **TCP, UDP** |
| Network – Layer 3 | Địa chỉ IP và chuyển tiếp gói tin giữa các mạng | IPv4, IPv6, ICMP |
| Data link – Layer 2 | Truyền frame trên liên kết cục bộ | Ethernet, Wi-Fi |

Quá trình **đóng gói (encapsulation)** có thể hình dung như sau:

```text
Ứng dụng tạo dữ liệu (ví dụ: yêu cầu HTTP)
           ↓
Transport thêm thông tin TCP/UDP (cổng nguồn, cổng đích, ...)
           ↓
Network thêm header IP (địa chỉ nguồn, địa chỉ đích, ...)
           ↓
Data link đóng thành frame để truyền qua liên kết

Ví dụ khái niệm: [Ethernet header][IP header][TCP header][Dữ liệu ứng dụng]
```

Ở phía nhận, các tầng tháo thông tin đóng gói theo chiều ngược lại. IP giúp gói tin đến **máy đích**; cổng transport giúp hệ điều hành phân phối dữ liệu đến **socket/ứng dụng** phù hợp. Vì vậy, hai tiến trình trên cùng máy có thể đồng thời truy cập mạng bằng những kết nối độc lập.

> **Ranh giới quan trọng:** Tầng transport không quyết định nội dung một yêu cầu HTTP có hợp lệ hay không và TCP/UDP không tự mã hóa dữ liệu. Việc xác thực, phân quyền và bảo vệ nội dung phải được thực hiện bằng giao thức hoặc cơ chế bảo mật thích hợp ở các tầng trên.

## 2. Những chức năng cốt lõi của tầng transport

### 2.1. Ghép kênh và phân kênh bằng port

**Port (cổng)** là số nguyên 16 bit từ `0` đến `65535`, dùng để phân biệt điểm giao tiếp của tiến trình. Chẳng hạn, một máy chủ có thể cung cấp HTTPS trên TCP/443 và DNS trên UDP/53 mà không nhầm lẫn hai dịch vụ.

| Nhóm cổng theo IANA | Phạm vi | Cách sử dụng thường gặp |
| --- | --- | --- |
| System / Well-known | `0–1023` | Các dịch vụ phổ biến như DNS `53`, HTTP `80`, HTTPS `443` |
| User / Registered | `1024–49151` | Dịch vụ, ứng dụng được đăng ký hoặc cấu hình |
| Dynamic / Private | `49152–65535` | Một phạm vi thường dùng cho cổng tạm thời; **phạm vi cổng tạm thời thực tế do hệ điều hành cấu hình** |

Cổng `0` mang ý nghĩa đặc biệt và thông thường không được dùng làm cổng dịch vụ đích. **TCP và UDP có không gian cổng riêng**: `TCP/443` và `UDP/443` là hai endpoint giao thức khác nhau.

Một kết nối TCP thường được nhận diện bằng **5-tuple**:

```text
(source IP, source port, destination IP, destination port, transport protocol)

(192.0.2.10, 51520, 198.51.100.20, 443, TCP)
```

Các địa chỉ trong ví dụ thuộc dải dành cho tài liệu. Máy khách sử dụng cổng nguồn tạm thời `51520` để kết nối tới dịch vụ TCP/443. Một máy chủ có thể có hàng nghìn kết nối TCP đến cùng cổng `443` vì mỗi kết nối có tổ hợp địa chỉ/cổng khác nhau. Firewall stateful, NAT, bộ cân bằng tải và hệ thống giám sát thường sử dụng thông tin tương tự 5-tuple để theo dõi luồng; **NAT có thể thay đổi địa chỉ hoặc cổng** khi gói tin đi qua thiết bị.

### 2.2. Phân chia dữ liệu, kiểm tra lỗi và quản lý truyền tải

- **Phân chia và tái hợp:** TCP biểu diễn dữ liệu ứng dụng như một dòng byte và phân thành các TCP segment để vận chuyển. UDP mang từng thông điệp dưới dạng datagram và giữ ranh giới thông điệp khi ứng dụng nhận.
- **Checksum:** TCP và UDP có cơ chế phát hiện lỗi truyền tải. Checksum giúp phát hiện dữ liệu hỏng, nhưng không thay thế xác thực và bảo vệ tính toàn vẹn bằng mật mã.
- **Độ tin cậy và thứ tự:** TCP cung cấp truyền dữ liệu theo thứ tự, truyền lại phần bị mất khi có thể. UDP không cung cấp sẵn các bảo đảm này.
- **Điều khiển luồng và tắc nghẽn:** TCP điều chỉnh lượng dữ liệu đang truyền theo khả năng nhận của đầu bên kia và tình trạng mạng. UDP không tự triển khai các chức năng tương đương; ứng dụng hoặc giao thức bên trên phải tự xử lý nếu cần.

## 3. TCP: giao thức hướng kết nối

**TCP (Transmission Control Protocol)** thích hợp cho các ứng dụng cần **dòng byte truyền đúng thứ tự** và có cơ chế khôi phục mất mát, như SSH, nhiều kết nối HTTPS, tải file hoặc giao tiếp với cơ sở dữ liệu.

TCP cung cấp một kết nối logic **hai chiều (full-duplex)**. TCP không bảo đảm mọi lần gửi đều thành công bất kể sự cố: khi mạng đứt kéo dài, timeout hoặc một phía reset kết nối, ứng dụng vẫn nhận được lỗi. TCP cũng không bảo đảm độ trễ cố định hay bảo tồn ranh giới các lời gọi `send()`.

### 3.1. Bắt tay ba bước (three-way handshake)

Trước khi trao đổi dữ liệu thông thường, hai phía thống nhất các số thứ tự ban đầu và thiết lập trạng thái kết nối:

```text
Client 192.0.2.10:51520                    Server 198.51.100.20:443
         |                                           |
         | ---- SYN, seq=x -----------------------> |
         | <--- SYN+ACK, seq=y, ack=x+1 ----------- |
         | ---- ACK, ack=y+1 ---------------------> |
         |                                           |
         |       Kết nối TCP được thiết lập          |
         | <---------- dữ liệu hai chiều ----------> |
```

1. **SYN:** máy khách đề nghị mở kết nối, công bố số thứ tự ban đầu.
2. **SYN+ACK:** máy chủ xác nhận SYN và gửi SYN của mình.
3. **ACK:** máy khách xác nhận SYN từ máy chủ; hai phía có thể trao đổi dữ liệu.

Trong thực tế, TCP còn thỏa thuận các tùy chọn như **MSS**, window scaling và SACK nếu được hỗ trợ. Khi kết nối kết thúc bình thường, mỗi hướng truyền có thể đóng bằng **FIN/ACK**; **RST** biểu thị việc reset, từ chối hoặc hủy kết nối trong một số tình huống. Trạng thái **TIME_WAIT** giúp tránh nhầm lẫn segment trễ từ kết nối cũ; nó không đồng nghĩa một dịch vụ vẫn đang hoạt động.

### 3.2. Sequence number, ACK và truyền lại

TCP đánh số **byte** trong luồng. Một ACK cộng dồn cho biết **byte tiếp theo đang được mong đợi**. Ví dụ, nếu bên nhận đã nhận liên tục 500 byte bắt đầu từ `seq=1000`, nó có thể trả `ack=1500`. Nếu một đoạn bị mất, TCP có thể phát hiện qua timeout hoặc tín hiệu ACK và truyền lại. Tùy chọn **SACK (Selective Acknowledgment)** giúp phía gửi biết thêm các vùng dữ liệu đã đến khi có khoảng trống.

TCP bảo tồn thứ tự byte cho ứng dụng, nhưng điều đó có thể gây **head-of-line blocking**: byte đến sau phải chờ byte trước còn thiếu. Các lần gọi `send()` và `recv()` không có quan hệ 1–1; ứng dụng cần tự quy định ranh giới bản tin, ví dụ bằng độ dài hoặc ký tự phân cách.

### 3.3. Flow control khác congestion control

Hai cơ chế thường bị nhầm lẫn:

| Cơ chế | Câu hỏi cần giải quyết | Thông tin tiêu biểu |
| --- | --- | --- |
| **Flow control – kiểm soát luồng** | Bên nhận còn đủ bộ đệm để tiếp nhận bao nhiêu dữ liệu? | `rwnd` (receive window), do phía nhận quảng bá |
| **Congestion control – kiểm soát tắc nghẽn** | Mạng có thể chịu thêm bao nhiêu dữ liệu mà không làm tắc nghẽn nghiêm trọng? | `cwnd` (congestion window), do thuật toán phía gửi điều chỉnh |

Lượng dữ liệu TCP có thể đang chờ xác nhận bị giới hạn bởi cả hai cửa sổ (và các ràng buộc khác). Mất gói, độ trễ tăng, bộ đệm đầy hoặc cửa sổ nhận nhỏ đều có thể làm tốc độ ứng dụng chậm lại, nhưng cần phân tích đúng nguyên nhân trước khi điều chỉnh cấu hình.

**MSS (Maximum Segment Size)** là kích thước tối đa của phần dữ liệu TCP trong một segment mà đầu cuối thông báo, còn **MTU** là giới hạn kích thước packet trên một liên kết/đường truyền. Ví dụ, với Ethernet MTU `1500`, IPv4 header `20` byte và TCP header `20` byte (không có tùy chọn), MSS thường là `1460` byte. Kích thước thực tế phụ thuộc đường đi, IPv4/IPv6, các header bổ sung và tùy chọn giao thức; lỗi Path MTU có thể khiến kết nối bắt tay thành công nhưng truyền dữ liệu lớn gặp trục trặc.

## 4. UDP: giao thức không hướng kết nối

**UDP (User Datagram Protocol)** gửi và nhận **datagram** mà không cần bắt tay ba bước như TCP. Header UDP cơ bản chỉ dài **8 byte**, gồm cổng nguồn, cổng đích, độ dài và checksum. UDP giữ ranh giới datagram nhưng tự nó **không bảo đảm** datagram được giao, chỉ được giao một lần, đến theo đúng thứ tự hoặc đến đúng thời điểm.

UDP phù hợp khi ứng dụng có nhu cầu độ trễ thấp, trao đổi thông điệp ngắn hoặc tự xây cơ chế truyền tải bên trên. Ví dụ:

- **DNS truyền thống** thường dùng UDP/53 cho truy vấn thông thường; TCP/53 cũng được sử dụng trong các trường hợp như phản hồi bị cắt ngắn, chuyển vùng hoặc triển khai khác.
- **Thời gian thực** như thoại, trò chơi trực tuyến có thể ưu tiên cập nhật mới hơn việc truyền lại mọi dữ liệu cũ; các giao thức ứng dụng phải xử lý jitter, mất gói và điều chỉnh tốc độ.
- **QUIC** hoạt động bên trên UDP, cung cấp các tính năng nâng cao như kết nối bảo mật, luồng truyền và khôi phục mất mát. Vì vậy **ứng dụng sử dụng UDP không có nghĩa ứng dụng đó thiếu cơ chế tin cậy**.

### TCP và UDP: bảng đối chiếu

| Tiêu chí | TCP | UDP |
| --- | --- | --- |
| Kiểu giao tiếp | Hướng kết nối | Gửi datagram, không có kết nối TCP-style |
| Đơn vị dữ liệu ứng dụng nhìn thấy | Luồng byte, không giữ ranh giới bản tin | Datagram, giữ ranh giới bản tin |
| Thiết lập | Bắt tay TCP trước khi truyền dữ liệu thông thường | Không cần bắt tay ở tầng UDP |
| Thứ tự và truyền lại | Có cơ chế sắp thứ tự, ACK, truyền lại | Không cung cấp sẵn |
| Flow/congestion control | Có trong TCP | Không tích hợp trong UDP |
| Header tối thiểu | 20 byte | 8 byte |
| Bảo mật nội dung | Không mã hóa | Không mã hóa |
| Ví dụ | SSH, HTTP/1.1 và HTTP/2 trên TCP | DNS thường, một số dịch vụ thời gian thực, QUIC |

**Không thể kết luận UDP luôn nhanh hơn TCP:** thời gian hoàn thành của ứng dụng còn phụ thuộc loại lưu lượng, RTT, mất gói, số lần bắt tay, thuật toán của giao thức bên trên, chất lượng đường truyền và cấu hình hạ tầng.

## 5. QUIC, TLS và HTTP/3: hiểu đúng ranh giới tầng

Trong mạng hiện đại, tên giao thức không luôn khớp hoàn toàn với một tầng OSI. Hai cách trao đổi HTTPS phổ biến là:

```text
HTTP/1.1 hoặc HTTP/2
        ↓
       TLS
        ↓
    TCP / 443
        ↓
        IP

HTTP/3
   ↓
 QUIC (tích hợp TLS 1.3, hỗ trợ nhiều stream)
   ↓
 UDP / 443
   ↓
   IP
```

QUIC được triển khai trên UDP nhưng bổ sung xác thực/mã hóa với TLS 1.3, quản lý kết nối, kiểm soát tắc nghẽn và truyền lại dữ liệu cho các stream đáng tin cậy. Các stream độc lập giúp tránh một dạng chặn đầu hàng giữa các stream mà TCP gây ra cho HTTP/2 khi mất gói. QUIC còn dùng **connection ID** để hỗ trợ duy trì kết nối trong một số tình huống thay đổi địa chỉ mạng; cách nhận diện luồng vì thế không chỉ dựa vào 5-tuple.

**TLS** bảo vệ dữ liệu ứng dụng khỏi bị đọc hoặc sửa trái phép trên đường truyền khi được cấu hình và xác thực đúng. TLS trên TCP, **DTLS** trên UDP và bảo vệ tích hợp trong QUIC giải quyết các yêu cầu khác với checksum TCP/UDP. Không nên gán TLS cứng vào một tầng OSI duy nhất khi mô tả hệ thống thực tế.

## 6. Tầng transport trong kiến trúc an ninh mạng

Tầng 4 là điểm quan trọng để **firewall, IDS/IPS, thiết bị NAT, load balancer và hệ thống quan sát lưu lượng** áp dụng chính sách. Tuy vậy, địa chỉ và cổng chỉ thể hiện một phần ý nghĩa của lưu lượng; chính sách ứng dụng còn cần kiểm soát danh tính, giao thức và nội dung phù hợp.

### 6.1. Stateful firewall và theo dõi kết nối

Một **stateless firewall** đánh giá gói tin dựa trên các trường của từng gói, như IP nguồn/đích, protocol, cổng và TCP flags. Một **stateful firewall** bổ sung bảng trạng thái hoặc cơ chế *connection tracking* để biết gói tin có thuộc luồng được cho phép trước đó hay không.

Ví dụ chính sách cho máy chủ web đặt trong mạng được bảo vệ:

| Hướng | Quy tắc khái niệm | Mục đích |
| --- | --- | --- |
| Client → web server | Cho phép TCP đến cổng `443` từ các vùng được cấp quyền | Cung cấp HTTPS trên TCP |
| Client → web server | Chỉ cho phép UDP đến `443` nếu chủ động triển khai HTTP/3 | Hỗ trợ QUIC khi cần |
| Web server → client | Cho phép lưu lượng phản hồi thuộc kết nối/luồng đã được cho phép | Tránh mở rộng quyền không cần thiết |
| Mạng quản trị → server | Chỉ cho phép SSH TCP/22 từ địa chỉ hoặc mạng quản trị được xác định | Hạn chế bề mặt truy cập quản trị |

Với TCP, hệ thống có thể dựa vào quá trình bắt tay và các trạng thái kết nối. Với UDP, firewall không nhìn thấy SYN/FIN như TCP; nó thường **duy trì trạng thái tạm dựa trên lưu lượng và timeout**, vì thế phải chọn timeout và chính sách phản hồi phù hợp. Một kết nối được firewall cho phép vẫn có thể thất bại ở DNS, định tuyến, TLS, xác thực ứng dụng hoặc chính dịch vụ đích.

### 6.2. Mối đe dọa thường gặp và biện pháp phòng vệ

| Hiện tượng / rủi ro | Liên quan đến tầng transport | Hướng phòng vệ |
| --- | --- | --- |
| **TCP SYN flood** | Nhiều yêu cầu mở kết nối gây áp lực lên bảng kết nối, hàng đợi và tài nguyên máy chủ | Giới hạn tốc độ theo bối cảnh, SYN cookies khi phù hợp, cân bằng tải/chống DDoS, giám sát backlog |
| **UDP flood / reflection-amplification** | Lưu lượng UDP lớn hoặc phản hồi từ dịch vụ bị lợi dụng làm nghẽn đường truyền; có thể liên quan IP nguồn giả mạo | Chặn IP spoofing ở rìa mạng, hạn chế dịch vụ phản hồi công khai, lọc/giới hạn lưu lượng và bảo vệ DDoS upstream |
| **Quét cổng và lộ dịch vụ** | Dịch vụ mở cổng không cần thiết làm tăng bề mặt tấn công | Kiểm kê cổng lắng nghe, nguyên tắc tối thiểu quyền, phân đoạn mạng, ghi log và cảnh báo |
| **Cạn trạng thái firewall/NAT** | Quá nhiều luồng hoặc timeout không phù hợp làm đầy bảng theo dõi | Theo dõi mức sử dụng bảng, điều chỉnh giới hạn/timeout có kiểm chứng, phân tải và lọc tại biên |
| **Truyền dữ liệu không mã hóa** | Header TCP/UDP không cung cấp bí mật hay xác thực ứng dụng | Dùng TLS/DTLS/QUIC bảo mật, xác minh chứng chỉ, cấu hình mã hóa và phân quyền đúng |

Các biện pháp tầng 4 nên phối hợp với bảo vệ DNS, segmentation, IDS/IPS và chính sách tầng ứng dụng. Ví dụ, chỉ cho phép TCP/443 không chứng minh mọi dữ liệu đi qua cổng đó đều là HTTPS hợp lệ; ngược lại, một kết nối HTTPS được mã hóa vẫn có thể mang yêu cầu ứng dụng độc hại.

## 7. Phân tích lưu lượng và khắc phục sự cố

Khi ứng dụng báo *không kết nối được*, cần tách sự cố theo tầng để tránh đưa ra kết luận chỉ từ một tín hiệu. **Ping thành công** chủ yếu xác nhận một dạng trao đổi ICMP/IP; nó không chứng minh TCP/443 hoặc UDP/443 đi được, cũng không chứng minh ứng dụng hoạt động.

### 7.1. Quan sát socket tại máy chủ

Ví dụ trên **Linux**, trong môi trường bạn có quyền quản trị/kiểm tra:

```bash
# Xem socket TCP đang lắng nghe cùng cổng và địa chỉ bind.
ss -lnt

# Xem socket UDP và các cổng đang sử dụng.
ss -lun

# Xem kết nối TCP và trạng thái (ESTAB, SYN-SENT, TIME-WAIT, ...).
ss -tan

# Ghi tối đa 30 gói liên quan TCP/UDP cổng 443 để phân tích.
# Chỉ chạy trên máy/mạng được phép giám sát; quyền capture có thể cần sudo.
sudo tcpdump -ni any -c 30 '(tcp port 443 or udp port 443)'
```

Đối với Windows, PowerShell có thể quan sát các TCP endpoint bằng `Get-NetTCPConnection` và các UDP endpoint bằng `Get-NetUDPEndpoint`. Cần nhớ rằng `0.0.0.0:443` (hoặc địa chỉ IPv6 wildcard) thường có nghĩa tiến trình đang lắng nghe trên nhiều interface, còn `127.0.0.1:443` chỉ lắng nghe loopback IPv4.

Trong **Wireshark**, một số *display filter* hữu ích:

```text
tcp.flags.syn == 1 && tcp.flags.ack == 0
tcp.analysis.retransmission
tcp.port == 443
udp.port == 443
udp.port == 53
```

Lọc theo `tcp.port`/`udp.port` chỉ phản ánh cổng; muốn biết giao thức ứng dụng nào thực sự được dùng cần kiểm tra thêm nội dung hoặc metadata mà bạn có quyền xem. Dữ liệu ứng dụng đã mã hóa có thể không đọc được bằng packet capture thông thường.

### 7.2. Đọc dấu hiệu trên đường truyền

| Quan sát | Ý nghĩa có thể có | Bước xác minh tiếp theo |
| --- | --- | --- |
| Client gửi SYN lặp lại nhưng **không thấy SYN+ACK** | Chưa hoàn tất bắt tay TCP; có thể mất gói, sai đường đi, lọc firewall, máy chủ không phản hồi | Capture ở cả hai đầu nếu được phép; kiểm tra tuyến, ACL, firewall, dịch vụ |
| Có **RST** khi thử kết nối | Một phía hoặc thiết bị trung gian từ chối/reset phiên | Kiểm tra nguồn phát RST, dịch vụ có lắng nghe và chính sách kết nối |
| Bắt tay TCP hoàn tất nhưng ứng dụng vẫn lỗi | Vấn đề có thể nằm ở TLS, giao thức ứng dụng, chứng chỉ hoặc backend | Kiểm tra TLS handshake, log server, phản hồi ứng dụng |
| Nhiều retransmission, RTT tăng, throughput thấp | Mất gói/tắc nghẽn, đường truyền không ổn định hoặc sự cố khác | Kiểm tra cả hai chiều, thông số RTT, receive window, đường đi |
| Gói UDP ra nhưng không có phản hồi | UDP không có xác nhận kết nối; đích có thể im lặng, bị lọc hoặc không hỗ trợ dịch vụ | Đối chiếu capture phía nhận, timeout firewall/NAT và cấu hình server |

Một capture tại một điểm chỉ cho biết **điều quan sát được ở điểm đó**. Ví dụ, không thấy SYN+ACK ở máy khách chưa đủ để khẳng định firewall là nguyên nhân: máy chủ có thể không nhận SYN, phản hồi có thể mất trên đường quay về, hoặc capture bỏ sót gói.

### 7.3. Tình huống thực hành: ping được nhưng không mở HTTPS

Giả sử máy khách `192.0.2.10` truy cập dịch vụ `https://example.com` và kết quả phân tích cho thấy địa chỉ đích là `198.51.100.20`. Ping có phản hồi nhưng trình duyệt báo timeout.

1. **Xác nhận đích:** kiểm tra phân giải DNS có trả về đúng địa chỉ được mong đợi, kể cả IPv4 và IPv6 nếu có.
2. **Quan sát TCP/443:** nếu SYN được gửi nhưng không có SYN+ACK, kiểm tra cổng lắng nghe, route, ACL, stateful firewall và capture ở phía máy chủ.
3. **Nếu TCP đã ESTABLISHED:** xem tiếp TLS handshake và log dịch vụ; lỗi chứng chỉ hoặc lỗi HTTP không nên quy về TCP.
4. **Nếu trình duyệt thử HTTP/3:** theo dõi thêm UDP/443. Khi QUIC không khả dụng, khả năng chuyển sang HTTP/2 hoặc HTTP/1.1 trên TCP phụ thuộc client, server và cấu hình thực tế.
5. **Đối chiếu chính sách bảo mật:** xem quy tắc có cho phép đúng IP, cổng, protocol và chiều phản hồi không; chỉ mở lưu lượng thực sự phục vụ kiến trúc.

Tình huống này thể hiện ích lợi của việc phân biệt **khả năng đi đến IP**, **khả năng thiết lập transport**, **khả năng thiết lập mã hóa** và **khả năng xử lý yêu cầu ứng dụng**.

## 8. Những nhầm lẫn cần tránh

1. **“TCP bảo mật hơn UDP vì có ACK.”** ACK và checksum không chứng minh danh tính và không bảo vệ dữ liệu khỏi bị nghe lén; cần cơ chế mật mã phù hợp.
2. **“TCP nhận từng message đúng như ứng dụng gửi.”** TCP là luồng byte. Ứng dụng phải thiết kế cách đóng khung thông điệp.
3. **“UDP luôn không đáng tin cậy ở mọi tầng.”** UDP không tự bảo đảm giao hàng, nhưng giao thức bên trên như QUIC có thể triển khai độ tin cậy.
4. **“Mở cổng 443 là hỗ trợ mọi HTTPS.”** HTTPS trên TCP/443 và HTTP/3 trên QUIC/UDP/443 là hai đường truyền khác nhau; chính sách firewall phải thể hiện đúng nhu cầu.
5. **“Có phản hồi ping nghĩa là cổng dịch vụ mở.”** ICMP, TCP và UDP được xử lý bằng các chính sách và trạng thái khác nhau.
6. **“Không thấy phản hồi UDP chắc chắn là cổng đã đóng.”** Không có bắt tay và ACK ở UDP; cần thêm log, capture hai phía hoặc thông tin ứng dụng để phân biệt các nguyên nhân.

## 9. Ghi nhớ và vận dụng

Tầng transport nối nhu cầu của ứng dụng với khả năng chuyển tiếp IP. **Port** đưa dữ liệu đến đúng tiến trình; **TCP** bổ sung dòng byte có thứ tự, xác nhận, truyền lại và điều tiết tốc độ; **UDP** cung cấp datagram với cơ chế tối giản để giao thức bên trên lựa chọn cách xử lý. **QUIC** là ví dụ quan trọng cho việc xây dựng transport hiện đại trên UDP và tích hợp bảo mật.

Trong công việc bảo mật mạng, hãy đọc mỗi luồng theo **IP nguồn/đích, cổng nguồn/đích, protocol, trạng thái và thời điểm**; sau đó đối chiếu với sơ đồ mạng, quy tắc firewall, log và hành vi ứng dụng. Phân tích theo từng tầng giúp xác định đúng điểm lỗi và thiết lập phòng vệ phù hợp mà không mở quyền truy cập quá rộng.
