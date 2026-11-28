# TCP segment và UDP datagram

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **TCP segment** và **UDP datagram** nằm ở đâu trong mô hình OSI/TCP-IP, được đóng gói trong gói IP như thế nào.
2. Đọc các trường quan trọng của TCP/UDP header, đặc biệt là port, sequence number, acknowledgment number, flags, length, window và checksum.
3. Phân tích một luồng TCP có bắt tay, truyền dữ liệu, xác nhận và truyền lại; phân biệt với cách UDP gửi từng datagram độc lập.
4. Chọn TCP hoặc UDP theo yêu cầu ứng dụng và nhận diện các tác động bảo mật: lọc theo trạng thái, giả mạo địa chỉ, SYN flood, UDP amplification và mã hóa đường truyền.
5. Sử dụng Wireshark hoặc `tcpdump` để quan sát, diễn giải gói tin mà không nhầm triệu chứng mạng với kết luận về tấn công.

## 1. TCP segment và UDP datagram ở đâu trong mạng?

Trong mô hình **OSI**, cả TCP (Transmission Control Protocol) và UDP (User Datagram Protocol) thường được xếp ở **lớp 4 – Transport**. Trong mô hình **TCP/IP**, chúng thuộc tầng transport, nằm trên IP và dưới giao thức ứng dụng như HTTP, DNS hoặc các giao thức thời gian thực.

- **TCP segment** là đơn vị dữ liệu của TCP, gồm *TCP header* và dữ liệu do tầng ứng dụng cung cấp (nếu có). TCP cung cấp một **luồng byte hai chiều**, có thiết lập kết nối, kiểm soát thứ tự, xác nhận và truyền lại.
- **UDP datagram** gồm *UDP header* và một thông điệp ứng dụng. UDP cung cấp cách gửi thông điệp **không thiết lập kết nối ở tầng UDP**, không tự đảm bảo gói đến nơi, đến đúng thứ tự hay chỉ đến một lần.
- Cả hai đều sử dụng **port** để giúp hệ điều hành phân phối dữ liệu đến đúng ứng dụng/socket; cặp địa chỉ IP nguồn–đích giúp định tuyến qua mạng.

```text
Ứng dụng:       HTTP, DNS, SSH, VoIP, QUIC, ...
                      |
Transport:      TCP segment     hoặc     UDP datagram
                      |                    |
Internet:          IPv4 / IPv6 packet (IP header + transport payload)
                      |
Liên kết:         Ethernet frame / Wi-Fi frame / ...
                      |
Vật lý:          tín hiệu điện, quang hoặc vô tuyến
```

Ví dụ, khi trình duyệt truy cập một máy chủ qua **HTTPS sử dụng HTTP/2**, dữ liệu ứng dụng thường được mã hóa bằng TLS rồi chuyên chở qua TCP; khi sử dụng **HTTP/3**, dữ liệu đi qua QUIC trên UDP. Vì vậy, **UDP không đồng nghĩa với thiếu bảo mật hoặc thiếu độ tin cậy ở cấp ứng dụng**: QUIC bổ sung mã hóa, xác nhận, truyền lại và kiểm soát tắc nghẽn ở lớp giao thức chạy trên UDP.

### Phân biệt các khái niệm thường dễ lẫn

| Khái niệm | Đơn vị/cấu trúc | Vai trò |
|---|---|---|
| TCP segment | TCP header + phần dữ liệu TCP | Chở một phần của luồng byte TCP |
| UDP datagram | UDP header + một thông điệp UDP | Giữ ranh giới thông điệp được gửi bởi ứng dụng |
| IP packet (IP datagram) | IP header + payload, ví dụ TCP/UDP | Mang thông tin để chuyển tiếp giữa các mạng |
| Ethernet frame | Header/trailer liên kết + IP packet | Chuyển dữ liệu trên một liên kết Ethernet |

Từ **datagram** có thể xuất hiện ở cả IP và UDP. Hãy luôn nêu rõ đang nói về *IP datagram* hay *UDP datagram*. Một IP packet chứa một TCP segment hoặc UDP datagram trong trường hợp thông thường, nhưng IP fragmentation có thể khiến các phần của một IP datagram được gửi bằng nhiều IP fragment.

## 2. Cấu trúc TCP segment

### 2.1. Các trường header

TCP header có **tối thiểu 20 byte**, tối đa **60 byte** theo trường *Data Offset*. Header có thể dài hơn 20 byte khi có các option như MSS, Window Scale, SACK Permitted hoặc Timestamp.

```text
  0                      15 16                     31
 +------------------------+------------------------+
 |    Source Port (16)    | Destination Port (16)  |
 +------------------------+------------------------+
 |                 Sequence Number (32)            |
 +-------------------------------------------------+
 |              Acknowledgment Number (32)         |
 +-----+----------+--------+-----------------------+
 |Data | Reserved | Flags  |     Window (16)       |
 |Off. |          |  (8)   |                       |
 +------------------------+------------------------+
 |     Checksum (16)      |   Urgent Pointer (16)  |
 +------------------------+------------------------+
 |        Options + Padding (nếu có)                |
 +-------------------------------------------------+
 |               Application Data ...              |
 +-------------------------------------------------+

 Mỗi dòng đầy đủ biểu thị 32 bit (4 byte).
```

| Trường | Độ rộng | Ý nghĩa thực tế |
|---|---:|---|
| Source Port / Destination Port | 16 bit/trường | Cổng nguồn và đích; cùng IP và giao thức giúp xác định luồng dữ liệu. |
| Sequence Number (SEQ) | 32 bit | Đánh số theo **byte** trong mỗi chiều của kết nối, phục vụ tái sắp xếp và xác nhận. |
| Acknowledgment Number (ACK number) | 32 bit | Khi cờ ACK được bật, cho biết **byte tiếp theo** mà bên nhận đang mong đợi; đây là xác nhận cộng dồn. |
| Data Offset | 4 bit | Số đơn vị **4 byte** của TCP header: giá trị 5 tương ứng 20 byte. |
| Flags / Control bits | 8 bit phổ biến | Điều khiển thiết lập, đóng, reset và một số hành vi khác của kết nối. |
| Window | 16 bit | Cửa sổ nhận được công bố, có thể nhân với hệ số Window Scale đã thương lượng. |
| Checksum | 16 bit | Phát hiện lỗi truyền tải trên header, dữ liệu và IP pseudo-header; **không** xác thực danh tính. |
| Urgent Pointer | 16 bit | Liên quan cờ URG; ít dùng trong ứng dụng hiện đại. |
| Options + Padding | Biến đổi | MSS, Window Scale, SACK, Timestamp; padding giúp header căn theo 4 byte. |

Một TCP segment có thể **không mang application data**, chẳng hạn SYN, SYN-ACK hoặc ACK thuần. Ngược lại, một lệnh ghi của ứng dụng không tương ứng cố định với đúng một TCP segment: TCP là *byte stream*, có thể gộp hoặc chia dữ liệu tùy MSS, bộ đệm, thuật toán truyền và khả năng offload của hệ điều hành/NIC.

### 2.2. Các cờ (flags) quan trọng

| Cờ | Ý nghĩa | Dấu hiệu khi phân tích |
|---|---|---|
| `SYN` | Đồng bộ sequence number khi mở kết nối | Thường ở bước đầu handshake; **tiêu thụ một số SEQ**. |
| `ACK` | Trường acknowledgment number có hiệu lực | Thường bật ở các segment sau SYN đầu tiên. |
| `FIN` | Bên gửi đã hết dữ liệu trong một chiều | Đóng một chiều của kết nối; **tiêu thụ một số SEQ**. |
| `RST` | Reset/huỷ bỏ kết nối | Có thể do ứng dụng, hệ điều hành hoặc thiết bị mạng; không tự chứng minh có tấn công. |
| `PSH` | Gợi ý chuyển dữ liệu đang chờ đến ứng dụng kịp thời | **Không** xác định ranh giới message. |
| `URG` | Urgent Pointer có ý nghĩa | Hiếm gặp; không nên xây dựng giao thức ứng dụng dựa vào nó. |
| `ECE`, `CWR` | Phục vụ Explicit Congestion Notification (ECN) | Liên quan tín hiệu tắc nghẽn khi hai phía hỗ trợ ECN. |

### 2.3. Ví dụ TCP three-way handshake và đánh số byte

Giả sử máy khách `203.0.113.10:51514` kết nối máy chủ `198.51.100.20:443`. Hai địa chỉ IP thuộc dải dùng trong tài liệu minh họa, không đại diện một máy chủ thực. Các SEQ ở ví dụ được chọn đơn giản để dễ tính; trong triển khai thực tế, initial sequence number thường khó đoán hơn nhiều.

```text
Client: 203.0.113.10:51514                 Server: 198.51.100.20:443

   SYN, SEQ=1000                ------->
                                <-------  SYN, ACK, SEQ=5000, ACK=1001
   ACK, SEQ=1001, ACK=5001      ------->

   DATA, SEQ=1001, LEN=1200     ------->
                                <-------  ACK=2201
```

Diễn giải:

1. Client gửi `SYN` với SEQ ban đầu 1000.
2. Server xác nhận SYN bằng `ACK=1001` và gửi SYN của riêng mình với SEQ ban đầu 5000.
3. Client xác nhận bằng `ACK=5001`. Hai phía có thể bắt đầu truyền dữ liệu TCP; TLS handshake (nếu dùng) diễn ra ở phía trên TCP.
4. Client gửi **1.200 byte** bắt đầu tại SEQ=1001, nên nếu nhận đủ liên tục, server xác nhận `ACK=1001+1200=2201`.

Các lưu ý khi đọc số liệu:

- **SEQ đếm byte, không đếm số segment**. Sau khi truyền `N` byte, số SEQ tiếp theo thường tăng `N` (theo modulo 2³²).
- `SYN` và `FIN` mỗi cờ chiếm một vị trí trong không gian SEQ; một ACK thuần không có dữ liệu thường không làm SEQ tăng.
- `ACK=2201` có nghĩa phía nhận đã nhận liên tục đến hết byte 2200 theo chiều client → server. Nó **không** đảm bảo ứng dụng phía server đã đọc hoặc xử lý thành công dữ liệu đó.
- TCP ACK là **theo từng chiều**. SEQ/ACK của client và server thuộc hai không gian số độc lập.

Khi đóng bình thường, mỗi phía có thể gửi `FIN` cho chiều truyền của mình và bên kia xác nhận. `RST` biểu thị đóng đột ngột; không phải mọi kết nối đều có đầy đủ chuỗi FIN trong bản capture nếu bắt gói giữa chừng hoặc có mất gói.

### 2.4. TCP cung cấp tính tin cậy như thế nào?

**Sắp xếp và truyền lại.** Bên nhận dựa trên SEQ để sắp xếp byte, loại dữ liệu trùng và xác nhận phần đã nhận liên tục. Bên gửi có thể truyền lại khi hết thời gian chờ hoặc phát hiện dấu hiệu mất gói qua ACK/SACK. TCP cung cấp luồng byte đúng thứ tự cho ứng dụng khi kết nối hoạt động; nếu không thể hoàn tất, kết nối có thể lỗi/thất bại.

**Flow control.** Giá trị `Window` bên nhận công bố giới hạn lượng dữ liệu đang chờ mà bên gửi có thể đưa vào bộ đệm nhận. Nếu `Window=0`, bên gửi thường phải chờ khả năng nhận tiếp. Cần phân biệt với **congestion control**: giới hạn lượng dữ liệu trên đường truyền nhằm tránh làm quá tải mạng. Bên gửi phải tuân thủ cả cửa sổ nhận và giới hạn tắc nghẽn.

**Selective acknowledgment (SACK).** Khi hai phía hỗ trợ, SACK giúp bên nhận thông báo các vùng byte đã nhận ngoài thứ tự. SACK bổ trợ ACK cộng dồn để bên gửi biết chính xác hơn vùng cần truyền lại.

**Không cung cấp mã hóa mặc định.** SEQ, ACK, checksum và truyền lại giải quyết vấn đề vận chuyển dữ liệu, **không** cung cấp tính bí mật hoặc xác thực chống kẻ tấn công có chủ đích. Ứng dụng thường dùng TLS (ví dụ HTTPS) hoặc lớp bảo vệ tương đương.

## 3. Cấu trúc UDP datagram

UDP header cố định **8 byte** và chỉ có bốn trường, mỗi trường 16 bit:

```text
  0                      15 16                     31
 +------------------------+------------------------+
 |    Source Port (16)    | Destination Port (16)  |
 +------------------------+------------------------+
 |      Length (16)       |      Checksum (16)     |
 +------------------------+------------------------+
 |               Application Data ...              |
 +-------------------------------------------------+
```

| Trường | Ý nghĩa |
|---|---|
| Source Port | Cổng nguồn; có thể giúp phía nhận gửi phản hồi về đúng socket. |
| Destination Port | Cổng ứng dụng ở phía nhận, chẳng hạn UDP/53 đối với DNS thông thường. |
| Length | Độ dài **toàn bộ UDP datagram**, bao gồm header 8 byte và dữ liệu. |
| Checksum | Phát hiện sai lệch bit trên UDP header, dữ liệu và IP pseudo-header. |

Ví dụ, một thông điệp DNS dài **32 byte** đặt trong UDP datagram sẽ có `UDP Length = 8 + 32 = 40 byte`. Với IPv4 header 20 byte và không có IP option, tổng chiều dài IP packet là `20 + 40 = 60 byte` (chưa tính header/trailer Ethernet hoặc Wi-Fi).

**Checksum và IPv4/IPv6:**

- Với **IPv4**, UDP checksum có thể được bỏ qua theo chuẩn; trên wire, giá trị zero biểu thị không tạo checksum. Dùng checksum khi khả thi vẫn là lựa chọn an toàn hơn để phát hiện lỗi vô tình.
- Với **IPv6**, UDP checksum nhìn chung **bắt buộc**, trừ một số ngoại lệ được chuẩn hóa cho các tình huống tunneling đặc thù. Không mặc định coi zero checksum trên IPv6 là hợp lệ.
- Checksum **không phải MAC/chữ ký số**. Kẻ tấn công có thể sửa dữ liệu rồi tính lại checksum, vì vậy muốn chống giả mạo hoặc nghe lén phải dùng cơ chế bảo vệ riêng như DTLS, QUIC hoặc bảo vệ ở tầng mạng.

### 3.1. Điều UDP làm và không làm

UDP chuyển từng thông điệp do ứng dụng gửi dưới dạng một datagram riêng, giữ **ranh giới thông điệp** ở tầng socket. Tuy nhiên:

- Datagram có thể **mất**, **đến trễ**, **đảo thứ tự** hoặc **bị trùng**.
- UDP không có three-way handshake, ACK, retransmission, flow control hay congestion control tích hợp như TCP.
- Một lời gọi `sendto()` thành công chỉ cho biết dữ liệu đã được hệ điều hành chấp nhận để gửi; **không** chứng minh phía đích đã nhận.
- Một lời gọi `recvfrom()` với bộ đệm quá nhỏ có thể dẫn đến dữ liệu datagram bị cắt, tùy hệ điều hành và API.
- UDP dùng chung hạ tầng IP nên vẫn chịu tác động của MTU, định tuyến, NAT, firewall và packet loss.

Ứng dụng như gọi thoại/video trực tiếp thường ưu tiên độ trễ thấp và có cơ chế riêng để thích nghi với mất gói. DNS thường dùng UDP cho truy vấn thông thường, nhưng có thể dùng TCP trong những trường hợp phù hợp; DNS cũng có các biến thể được bảo vệ khác. QUIC dùng UDP làm lớp chuyên chở để xây dựng một giao thức truyền tải bảo mật với các cơ chế tin cậy phù hợp.

### 3.2. Vì sao nên tránh datagram quá lớn?

UDP không tự chia một thông điệp thành nhiều datagram nhỏ rồi ghép lại ở đầu nhận. Nếu UDP datagram lớn hơn MTU đường đi, nó có thể cần **IP fragmentation** hoặc bị loại bỏ, tùy phiên bản IP, cấu hình và chính sách mạng.

IP fragmentation có rủi ro: mất **một fragment** cũng có thể khiến toàn bộ datagram không tái lắp được; một số firewall/NAT không xử lý tốt fragment; fragment khó phân tích khi thiếu các phần liên quan. Với IPv6, router không phân mảnh packet trên đường truyền; đầu gửi cần quản lý kích thước phù hợp với path MTU.

Do đó, ứng dụng UDP nên chọn kích thước payload phù hợp với MTU thực tế, dùng Path MTU Discovery khi thích hợp và triển khai cơ chế điều chỉnh kích thước; tránh giả định mọi đường mạng đều có MTU 1500 byte.

## 4. So sánh TCP segment và UDP datagram

| Tiêu chí | TCP segment | UDP datagram |
|---|---|---|
| Transport header | Tối thiểu 20 byte, có thể có options | Cố định 8 byte |
| Thiết lập kết nối | Có trạng thái kết nối, thường khởi tạo bằng three-way handshake | Không có handshake ở **tầng UDP** |
| Dạng dữ liệu | Luồng byte; không giữ ranh giới lệnh ghi | Theo thông điệp/datagram |
| Thứ tự và truyền lại | Tích hợp cơ chế xác nhận, sắp xếp và truyền lại | Tầng UDP không cung cấp; ứng dụng có thể tự bổ sung |
| Kiểm soát lưu lượng/tắc nghẽn | Tích hợp | Do giao thức/ứng dụng phía trên xử lý nếu cần |
| Tác động mất gói | Có thể gây truyền lại và chờ byte còn thiếu | Datagram mất thường không tự phục hồi |
| Chi phí truyền | Header và duy trì trạng thái lớn hơn; không có nghĩa luôn chậm hơn UDP | Header nhỏ, ít cơ chế ở transport; không đảm bảo độ trễ thực tế luôn thấp hơn |
| Mã hóa/xác thực | Không có mặc định | Không có mặc định |
| Ví dụ thường gặp | SSH, HTTPS qua HTTP/1.1 hoặc HTTP/2, SMTP | DNS thông thường, VoIP, QUIC/HTTP/3 |

Điểm ra quyết định là **yêu cầu ứng dụng**, không phải khẩu hiệu “TCP an toàn, UDP nhanh”. Ví dụ, ứng dụng truyền tệp cần đủ và đúng thứ tự mọi byte; ứng dụng truyền âm thanh thời gian thực có thể chấp nhận một số khung bị mất để giữ độ trễ thấp. QUIC cho thấy một giao thức trên UDP vẫn có thể triển khai xác nhận, truyền lại, kiểm soát tắc nghẽn và mã hóa.

## 5. MSS, MTU, segmentation và fragmentation

Đây là bốn khái niệm khác nhau:

- **MTU (Maximum Transmission Unit)**: kích thước IP packet tối đa mà một liên kết/đường đi truyền được mà không phải phân mảnh ở mức IP. MTU Ethernet thường gặp là 1500 byte, nhưng đường đi thực tế có thể thấp hơn.
- **MSS (Maximum Segment Size)**: số **byte dữ liệu TCP** tối đa bên nhận công bố có thể nhận trong mỗi TCP segment. MSS thường được quảng bá trong TCP SYN; không tính TCP/IP header.
- **TCP segmentation**: chia luồng byte thành các TCP segment phù hợp với MSS và giới hạn truyền; phía nhận tái tạo luồng byte theo SEQ.
- **IP fragmentation**: chia một IP datagram thành fragment ở tầng IP trong các trường hợp được phép. TCP segmentation không đồng nghĩa với IP fragmentation.

Ví dụ với **MTU = 1500 byte**, header IPv4 = 20 byte và TCP header = 20 byte (không có option bổ sung trên data segment):

```text
MSS TCP tham khảo = 1500 - 20 (IPv4) - 20 (TCP) = 1460 byte
Với IPv6 header cơ bản 40 byte và TCP header 20 byte:
MSS tham khảo     = 1500 - 40 (IPv6) - 20 (TCP) = 1440 byte
```

Đây chỉ là ví dụ trong điều kiện đã nêu. TCP options, IPv6 extension headers, tunnel/VPN, PPPoE và MTU trên đường đi có thể làm giảm chỗ cho dữ liệu. **MSS được thỏa thuận lúc thiết lập TCP; MTU là giới hạn truyền trên đường đi**, và hai giá trị cần được cân nhắc cùng nhau để tránh rơi vào tình trạng gói quá lớn.

Trong capture từ máy phát, bạn còn có thể thấy TCP segment có vẻ lớn hơn MTU vì **TCP Segmentation Offload (TSO/GSO)**: hệ điều hành/NIC chưa chia dữ liệu thành các segment thực tế tại vị trí capture. Ở máy nhận, **GRO/LRO** có thể gộp segment trước khi phần mềm phân tích nhìn thấy. Không kết luận mạng đang gửi frame vượt MTU chỉ từ một bản capture tại host.

## 6. Góc nhìn bảo mật mạng

### 6.1. Kiểm soát truy cập và trạng thái kết nối

Firewall cần kết hợp **IP nguồn/đích, giao thức và port**, cùng chính sách xác thực/nhận dạng phù hợp. `TCP/443` và `UDP/443` là **hai luồng khác giao thức** dù cùng số port; cho phép TCP/443 không tự động cho phép HTTP/3 chạy trên UDP/443.

Stateful firewall có thể theo dõi trạng thái TCP thông qua SYN, ACK, FIN, RST và timeout. Với UDP, thiết bị thường lưu **trạng thái giả lập theo phiên (connection tracking)** dựa trên địa chỉ/port và timeout để cho phép lưu lượng phản hồi. Bản thân UDP không có trạng thái kết nối tương đương TCP.

**Port mở không đồng nghĩa với ứng dụng an toàn.** Cần xác thực, giới hạn quyền, giảm bề mặt dịch vụ, lọc nguồn truy cập và mã hóa phù hợp; port filtering chỉ là một lớp phòng vệ.

### 6.2. Các mối đe dọa liên quan

| Hiện tượng/mối đe dọa | TCP hay UDP | Cơ chế và biện pháp tiêu biểu |
|---|---|---|
| SYN flood | TCP | Gửi nhiều SYN gây áp lực lên hàng đợi/trạng thái; cân nhắc SYN cookies, rate limiting, bảo vệ DDoS và điều chỉnh hệ thống. |
| Giả mạo RST hoặc chiếm phiên | TCP | Kẻ tấn công tìm cách tạo segment phù hợp thông số kết nối; phòng vệ bằng khó đoán SEQ, lọc chống spoofing và bảo vệ ứng dụng bằng TLS. |
| UDP reflection/amplification | UDP | Giả IP nguồn của nạn nhân để máy chủ phản hồi lớn hơn yêu cầu; áp dụng anti-spoofing/BCP 38, không phơi bày reflector, rate limit và kiểm soát dịch vụ. |
| Quét port/dò dịch vụ | Cả hai | TCP SYN hoặc UDP probe có thể giúp suy đoán dịch vụ; cần kiểm soát truy cập, giảm dịch vụ mở, log và giám sát hợp lý. |
| Dữ liệu lộ hoặc bị sửa | Cả hai | Transport checksum không thay thế mã hóa/xác thực; áp dụng TLS, DTLS, QUIC hoặc bảo vệ phù hợp. |
| Fragment gây né tránh phân tích | IP mang TCP/UDP | Fragment không đầy đủ/chồng lấp có thể khó xử lý; chuẩn hóa, kiểm tra tái lắp và chính sách firewall nhất quán. |

**Về spoofing:** TCP handshake làm cho việc hoàn tất phiên bằng địa chỉ giả mạo khó hơn trong nhiều tình huống, nhưng không ngăn tuyệt đối mọi hình thức giả mạo hoặc tấn công vào TCP. UDP không có handshake tích hợp nên một số dịch vụ UDP dễ bị lợi dụng làm reflector nếu trả lời lớn cho nguồn không được xác minh.

**Về mã hóa:** TCP + TLS và UDP + QUIC/DTLS có thể cung cấp bảo mật ở tầng giao thức phía trên. Tuy nhiên, header IP và các thông tin định tuyến/port thường vẫn quan sát được, kể cả khi payload ứng dụng đã được mã hóa.

## 7. Quan sát trong Wireshark và tcpdump

Chỉ bắt gói trên máy/mạng bạn có quyền quản trị hoặc đã được cho phép. Gói capture có thể chứa token, địa chỉ nội bộ, tên miền truy cập và dữ liệu cá nhân; lưu và chia sẻ có kiểm soát.

### 7.1. Bộ lọc hiển thị Wireshark

Đây là **display filter** (lọc gói đã thu), khác với cú pháp capture filter của `tcpdump`.

| Bộ lọc | Mục đích |
|---|---|
| `tcp` | Hiển thị các gói TCP. |
| `udp` | Hiển thị các gói UDP. |
| `tcp.port == 443` | TCP có port nguồn hoặc đích là 443. |
| `udp.port == 53` | UDP có port nguồn hoặc đích là 53. |
| `tcp.flags.syn == 1 && tcp.flags.ack == 0` | Tìm SYN khởi tạo kết nối TCP. |
| `tcp.flags.reset == 1` | Tìm segment có cờ RST. |
| `tcp.analysis.retransmission` | Xem gói được Wireshark phân loại là TCP retransmission. |
| `tcp.stream == 0` | Xem toàn bộ gói thuộc luồng TCP số 0 trong capture. |

Ví dụ khi phân tích sự cố HTTPS: tìm `tcp.flags.syn == 1 && tcp.flags.ack == 0`, kiểm tra SYN-ACK có trở lại không, xem các ACK và dấu hiệu retransmission. Nếu TCP handshake hoàn tất nhưng ứng dụng vẫn lỗi, tiếp tục phân tích DNS, TLS, HTTP, chính sách proxy/firewall và log ứng dụng; **TCP thành công không chứng minh ứng dụng thành công**.

### 7.2. Lệnh tcpdump minh họa

Các lệnh sau dùng trên Linux có `tcpdump`; thay `eth0` bằng tên interface thực tế. `-n` tránh đổi địa chỉ thành hostname, `-i` chọn interface, `-c` giới hạn số gói; `-s 0` thu đủ snap length do công cụ cho phép.

```bash
# Bắt tối đa 20 gói TCP liên quan port 443
sudo tcpdump -ni eth0 -c 20 'tcp port 443'

# Quan sát các gói UDP liên quan DNS truyền thống
sudo tcpdump -ni eth0 -c 20 'udp port 53'

# Lưu lại để xem trong Wireshark (cần quản lý file pcap như dữ liệu nhạy cảm)
sudo tcpdump -ni eth0 -s 0 -c 100 -w /tmp/transport-sample.pcap 'tcp or udp'

# Đọc lại file đã thu với thông tin chi tiết hơn
tcpdump -nn -vv -r /tmp/transport-sample.pcap
```

Trong output `tcpdump`, các dạng thường gặp:

```text
Flags [S]   : TCP SYN
Flags [S.]  : TCP SYN + ACK
Flags [.]   : TCP ACK
Flags [P.]  : TCP PSH + ACK
Flags [F.]  : TCP FIN + ACK
Flags [R]  : TCP RST (có thể đi cùng cờ khác)
UDP, length 32 : 32 byte UDP payload được tcpdump báo cáo
```

Lưu ý: `UDP, length 32` trong dòng tóm tắt của `tcpdump` thường diễn tả **32 byte payload UDP**, trong khi trường `Length` của **UDP header** sẽ là **40 byte** (8 byte header + 32 byte payload). Đừng đánh đồng nhãn công cụ với trường header.

### 7.3. Tình huống chẩn đoán

| Quan sát | Có thể gợi ý | Cần xác minh thêm |
|---|---|---|
| Liên tiếp SYN nhưng không có SYN-ACK trong capture | Server không nghe, gói bị lọc, mất đường về, hoặc capture thiếu hướng phản hồi | Firewall log, routing, điểm đặt capture, trạng thái dịch vụ. |
| Nhiều TCP retransmission | Packet loss, tắc nghẽn, receiver/path issue | RTT, SACK, interface counters, offload và điểm bắt gói. |
| Nhiều RST | Ứng dụng/OS chủ động reset, thiết bị trung gian can thiệp | Bên phát RST, log ứng dụng, rule firewall. |
| UDP request không có response | Server không trả lời, packet loss, lọc UDP, phản hồi tới port khác, hoặc giao thức không yêu cầu trả lời | Log server, cả hai phía đường truyền, NAT timeout và thiết kế ứng dụng. |
| Checksum bị báo sai ở capture trên máy gửi | Có thể do checksum offload chưa tính checksum lúc capture | Capture ở máy nhận hoặc tắt offload trong môi trường thử nghiệm được kiểm soát. |

Một công cụ gắn nhãn “retransmission” dựa trên **heuristic** và phần dữ liệu nhìn thấy; bản capture thiếu gói có thể dẫn đến diễn giải sai. Luôn xem thời điểm, hai chiều truyền, vị trí bắt gói và log tương ứng trước khi kết luận.

## 8. Bài tập tự kiểm tra

**Bài 1 — Tính độ dài UDP.** Một ứng dụng gửi 100 byte payload UDP qua IPv4, IP header 20 byte, không có option. Hãy tính UDP Length và IP Total Length.

**Đáp án:** UDP Length = `8 + 100 = 108 byte`; IP Total Length = `20 + 108 = 128 byte`.

**Bài 2 — Đọc ACK TCP.** Client đã bắt tay xong, gửi 600 byte với `SEQ=7001`. Server nhận đủ liên tục và không có byte nào bị mất. ACK tiếp theo xác nhận dữ liệu này là bao nhiêu?

**Đáp án:** `ACK = 7001 + 600 = 7601`. ACK cho biết byte tiếp theo server mong đợi, không chứng minh ứng dụng đã xử lý 600 byte đó.

**Bài 3 — Đọc chính sách firewall.** Hệ thống cho phép outbound TCP/443 nhưng chặn outbound UDP/443. HTTP/2 qua HTTPS hoạt động, nhưng HTTP/3 không kết nối trực tiếp được. Vì sao?

**Đáp án:** HTTP/2 thường dùng TLS qua TCP/443; HTTP/3 dùng QUIC qua UDP/443. Port 443 giống nhau nhưng **giao thức transport** khác nhau nên hai rule firewall có kết quả khác nhau. Tùy client và server, trình duyệt có thể fallback về HTTP/2.

**Bài 4 — Đánh giá dấu hiệu tấn công.** Bạn thấy một host gửi nhiều UDP request nhưng không có phản hồi trong capture. Có thể kết luận bị UDP flood không?

**Đáp án:** **Chưa thể kết luận.** Cần kiểm tra tần suất, kích thước, đích đến, baseline bình thường, log máy đích, luồng phản hồi và điểm đặt capture. Một số ứng dụng UDP vốn không yêu cầu trả lời cho từng datagram.

## 9. Ghi nhớ khi thiết kế và kiểm tra mạng an toàn

- TCP truyền **luồng byte có thứ tự**; UDP truyền **datagram giữ ranh giới thông điệp**. Cả hai dựa vào IP để chuyển tiếp.
- TCP header tối thiểu **20 byte**; UDP header **8 byte**. TCP có SEQ/ACK, flags và window; UDP có Length nhưng không có các cơ chế tin cậy đó ở chính tầng UDP.
- **Transport checksum phát hiện lỗi vô tình**, không cung cấp xác thực hay mã hóa. Chọn TLS, DTLS, QUIC hoặc lớp bảo vệ phù hợp với dữ liệu cần bảo vệ.
- **TCP segmentation khác IP fragmentation**. Cần xét đồng thời MSS, MTU, đường đi, VPN/tunnel và các cơ chế offload khi đọc pcap.
- Quy tắc an ninh mạng cần phân biệt **TCP/port** với **UDP/port** và xét trạng thái kết nối/NAT một cách đúng đắn.
- Khi phân tích traffic, kết hợp header, hai chiều gói tin, log và vị trí capture trước khi suy đoán lỗi hay tấn công.

### Tài liệu chuẩn để tra cứu thêm

- [RFC 9293 — Transmission Control Protocol (TCP)](https://www.rfc-editor.org/rfc/rfc9293): cấu trúc TCP header, sequence/acknowledgment, cơ chế kết nối.
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): định dạng header UDP, length và checksum.
- [RFC 8200 — Internet Protocol, Version 6 (IPv6)](https://www.rfc-editor.org/rfc/rfc8200): IPv6 packet, giới hạn xử lý fragmentation trên đường truyền.
- [RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000): ví dụ giao thức tin cậy, bảo mật xây dựng phía trên UDP.
