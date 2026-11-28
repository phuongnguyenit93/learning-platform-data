# TCP handshake: Thiết lập kết nối TCP và những điều cần biết về bảo mật

Khi trình duyệt mở một trang web chạy trên HTTPS qua TCP, thông thường máy khách không gửi ngay yêu cầu HTTP. Trước tiên, hai đầu cuối phải thiết lập một **kết nối TCP** để thống nhất trạng thái ban đầu và các số thứ tự dùng cho việc truyền dữ liệu đáng tin cậy. Quy trình đó được gọi là **TCP three-way handshake** hay **bắt tay TCP ba bước**: **SYN → SYN-ACK → ACK**.

Trong chương **TCP IP** thuộc module **SECURITY_NETWORK_SECURITY**, hiểu TCP handshake giúp phân tích lưu lượng, xác định lỗi firewall và định tuyến, nhận diện kết nối đáng ngờ, thiết kế phân đoạn mạng, triển khai IDS/IPS và bảo vệ dịch vụ khỏi các kiểu tấn công như **SYN flood**. Handshake chỉ tạo trạng thái kết nối ở tầng vận chuyển; nó **không tự mã hóa dữ liệu, xác thực danh tính ứng dụng hoặc cấp quyền truy cập**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao TCP cần bắt tay ba bước và phân biệt TCP với UDP.
2. Đọc đúng cờ **SYN**, **ACK**, các trường **Sequence Number** và **Acknowledgment Number**.
3. Mô tả trạng thái **LISTEN**, **SYN-SENT**, **SYN-RECEIVED**, **ESTABLISHED** ở hai phía.
4. Phân tích một bản bắt gói TCP bằng Wireshark hoặc tcpdump, xác định điểm kết nối bị gián đoạn.
5. Giải thích liên hệ giữa handshake với **stateful firewall**, NAT, thiết bị cân bằng tải và IDS/IPS.
6. Nhận diện rủi ro **SYN flood**, giả mạo địa chỉ IP, chiếm kết nối và nguyên tắc phòng vệ nhiều lớp.
7. Phân biệt **TCP handshake**, **TLS handshake** và quy trình thiết lập kết nối bằng QUIC.

## 1. TCP handshake là gì và vì sao cần nó?

**TCP (Transmission Control Protocol)** là giao thức tầng vận chuyển hướng kết nối. Nó cung cấp luồng byte hai chiều có thứ tự, cơ chế xác nhận, truyền lại khi mất dữ liệu và điều khiển luồng/tắc nghẽn. TCP không bảo đảm kết nối luôn tồn tại hay dữ liệu đến trong một thời hạn cố định; khi đường truyền có sự cố, ứng dụng vẫn phải xử lý timeout và lỗi.

Trước khi trao đổi luồng byte bình thường, hai bên cần thiết lập trạng thái đủ để:

- Xác nhận đã nhận các thông điệp thiết lập cần thiết của phía kia.
- Trao đổi **Initial Sequence Number (ISN)**, tức số thứ tự khởi đầu cho hai chiều truyền độc lập.
- Thương lượng một số tùy chọn TCP được công bố trong gói SYN như MSS, Window Scale, SACK Permitted và Timestamp (nếu được hỗ trợ).
- Tạo trạng thái kết nối để theo dõi byte đã gửi/đã nhận, cửa sổ nhận và việc truyền lại.

Một kết nối TCP thường được nhận diện bởi bộ bốn **IP nguồn, cổng nguồn, IP đích, cổng đích** trong phạm vi giao thức TCP. Khi phân tích nhiều loại lưu lượng, người ta thường gọi thêm trường giao thức (TCP/UDP) là **5-tuple**.

Ví dụ:

| Thành phần | Giá trị minh họa |
|---|---|
| Client | 10.20.10.15 |
| Cổng nguồn tạm thời do hệ điều hành chọn | TCP 51542 |
| Server | 10.20.20.25 |
| Cổng dịch vụ đích | TCP 443 |
| Kết nối | 10.20.10.15:51542 → 10.20.20.25:443 |

Địa chỉ và cổng nguồn trên chỉ là ví dụ. Server thường **lắng nghe** ở cổng đã cấu hình; client thường dùng **ephemeral port**, tức cổng tạm thời được hệ điều hành cấp cho phiên kết nối.

### Vì sao ba bước thay vì hai?

Mỗi bên có **không gian số thứ tự độc lập**. Client phải báo số khởi đầu của mình; server phải vừa xác nhận SYN của client vừa báo số khởi đầu của server; cuối cùng client phải xác nhận đã nhận SYN của server. Bước ACK thứ ba là tín hiệu để server hoàn tất thiết lập theo quy trình thông thường. Các bước cũng giúp hai bên xử lý tốt hơn các gói bị trễ, trùng lặp hoặc mất trên mạng.

Handshake không phải bằng chứng định danh bằng mật mã. Một bên quan sát được lưu lượng, hoặc kiểm soát đường đi, có thể gây ra những tình huống mà ba gói TCP vẫn xuất hiện nhưng phía ứng dụng chưa được bảo vệ đúng.

## 2. Ba bước bắt tay TCP

Giả sử client chọn ISN là **1000**, server chọn ISN là **7000** và không gửi dữ liệu trong SYN.

~~~mermaid
sequenceDiagram
    participant C as Client 10.20.10.15:51542
    participant S as Server 10.20.20.25:443
    Note over C: CLOSED → SYN-SENT
    C->>S: 1. SYN, Seq=1000
    Note over S: LISTEN → SYN-RECEIVED
    S-->>C: 2. SYN + ACK, Seq=7000, Ack=1001
    Note over C: ESTABLISHED sau khi gửi ACK
    C->>S: 3. ACK, Seq=1001, Ack=7001
    Note over S: ESTABLISHED sau khi nhận ACK hợp lệ
    C->>S: Dữ liệu ứng dụng khi sẵn sàng
    S-->>C: ACK / dữ liệu phản hồi
~~~

| Bước | Hướng | Cờ TCP | Sequence | Acknowledgment | Ý nghĩa |
|---|---|---|---:|---:|---|
| 1 | Client → Server | SYN | 1000 | Không có ACK hợp lệ | Client yêu cầu thiết lập và công bố ISN của mình |
| 2 | Server → Client | SYN, ACK | 7000 | 1001 | Server xác nhận SYN của client và công bố ISN của server |
| 3 | Client → Server | ACK | 1001 | 7001 | Client xác nhận SYN của server; hoàn tất bắt tay bình thường |

**Quy tắc cần nhớ:** với ACK hợp lệ, trường **Acknowledgment Number** biểu diễn **số thứ tự của byte tiếp theo phía nhận đang chờ**. Vì **SYN tiêu thụ một vị trí trong không gian số thứ tự**, ACK dành cho SYN có giá trị **ISN + 1**, dù gói SYN thông thường không mang payload ứng dụng.

### Bước 1 — SYN

Client gọi thao tác mở kết nối (chẳng hạn một lời gọi connect từ ứng dụng). Hệ điều hành gửi phân đoạn TCP có cờ **SYN = 1**, công bố ISN và các TCP option mong muốn. Client chuyển sang trạng thái **SYN-SENT**.

Ở thời điểm này, chưa thể khẳng định server đang lắng nghe hay sẽ chấp nhận kết nối. Một gói SYN chỉ cho biết một phía đã **thử bắt đầu** phiên TCP.

### Bước 2 — SYN-ACK

Nếu SYN đến đúng dịch vụ đang lắng nghe và được ngăn xếp TCP xử lý, server thông thường gửi phân đoạn có **SYN = 1, ACK = 1**. Server công bố ISN của mình và dùng Ack = client ISN + 1. Phía server bước vào **SYN-RECEIVED** trong mô hình bắt tay thông thường.

Nếu không có tiến trình lắng nghe ở cổng và gói được xử lý bình thường, phía đích có thể trả **RST** để từ chối kết nối. Nếu firewall lặng lẽ loại bỏ SYN, client có thể không nhận được bất kỳ phản hồi nào.

### Bước 3 — ACK

Client nhận và kiểm tra SYN-ACK, rồi gửi ACK với Ack = server ISN + 1. Client có thể xem kết nối đã thiết lập khi hoàn tất xử lý SYN-ACK và gửi ACK; server chuyển sang **ESTABLISHED** khi nhận ACK hợp lệ. Sau đó hai phía có thể trao đổi byte của ứng dụng qua TCP.

Một gói ACK chỉ có cờ ACK, không mang dữ liệu, **không tiêu thụ số thứ tự**. Vì vậy ở ví dụ, Sequence của client vẫn là 1001 ở bước 3. Gói bước 3 đôi khi có thể mang dữ liệu, nhưng không cần dữ liệu để hoàn tất bắt tay.

### Hình dung bằng công thức

Gọi **x** là ISN của client, **y** là ISN của server:

~~~text
Client → Server: SYN      Seq = x
Server → Client: SYN,ACK  Seq = y      Ack = x + 1
Client → Server: ACK      Seq = x + 1  Ack = y + 1
~~~

Các số thứ tự là giá trị 32 bit và được diễn giải theo phép tính modulo 2³² khi cần. Quy tắc trên áp dụng cho bắt tay TCP thông thường, **không tính dữ liệu trong SYN**; một số phần mở rộng như TCP Fast Open có thể cho phép dữ liệu trong gói SYN và khi đó việc tính ACK phải xét cả byte payload.

## 3. Đọc cờ và trường trong TCP header

TCP header chứa các trường quan trọng sau:

| Trường / cờ | Ý nghĩa trong handshake | Lưu ý khi phân tích |
|---|---|---|
| Source Port / Destination Port | Cổng nguồn của client và cổng dịch vụ của server | Cổng 443 thường dùng HTTPS/TCP, nhưng chỉ nhìn số cổng chưa chứng minh ứng dụng đang chạy TLS |
| Sequence Number | Số thứ tự cho chiều đang gửi; SYN công bố số khởi đầu | Không nhầm Sequence với số thứ tự **gói tin**; TCP đánh số **byte** |
| Acknowledgment Number | Số byte tiếp theo phía kia cần gửi, khi cờ ACK được đặt | Phải xét cờ ACK; giá trị trường ACK ở SYN đầu tiên không có ý nghĩa xác nhận |
| SYN | Yêu cầu đồng bộ số thứ tự khi bắt đầu kết nối | Một SYN được truyền lại có thể có cùng ISN |
| ACK | Cho biết trường Acknowledgment Number hợp lệ | Các phân đoạn dữ liệu TCP thông thường cũng thường có ACK |
| RST | Đặt lại/từ chối kết nối hoặc báo không có trạng thái phù hợp | Cần xác định ai phát RST và quy tắc firewall/thiết bị trung gian |
| FIN | Bên gửi đã truyền xong luồng byte theo chiều đó | **FIN thuộc đóng kết nối**, không thuộc ba bước mở kết nối |
| Window | Cửa sổ nhận được quảng bá cho điều khiển luồng | Khác với cửa sổ tắc nghẽn mà phía gửi tự điều chỉnh |
| Options | Tùy chọn hỗ trợ hiệu năng/chức năng TCP | Nhiều tùy chọn phải được thương lượng ngay trong SYN |
| Checksum | Kiểm tra lỗi của segment TCP và phần pseudo-header IP | Checksum không cung cấp xác thực chống sửa đổi cố ý |

Wireshark và tcpdump thường ký hiệu:

~~~text
[S]   = SYN
[S.]  = SYN + ACK
[.]   = ACK
[R]   = RST
[R.]  = RST + ACK
[F.]  = FIN + ACK
[P.]  = PSH + ACK
~~~

Dấu chấm trong ký hiệu tcpdump biểu diễn cờ **ACK**; nó không có nghĩa kết thúc kết nối. Cờ **PSH** thường xuất hiện khi truyền dữ liệu, nhưng không quyết định riêng một ranh giới thông điệp của ứng dụng.

### TCP options trong SYN

| Option | Vai trò | Điểm cần tránh nhầm |
|---|---|---|
| **MSS (Maximum Segment Size)** | Công bố kích thước TCP payload tối đa mà bên gửi option muốn nhận trong một segment | MSS không phải MTU; MSS chủ yếu áp dụng cho hướng dữ liệu được gửi **đến** bên công bố |
| **Window Scale** | Cho phép biểu diễn cửa sổ nhận lớn hơn trường Window 16 bit ban đầu | Hệ số phải được thương lượng lúc thiết lập, không tùy tiện bổ sung ở giữa phiên |
| **SACK Permitted** | Báo khả năng dùng Selective Acknowledgment để mô tả các vùng byte đã nhận | SACK giúp phục hồi khi mất gói; không xác thực dữ liệu |
| **Timestamp** | Hỗ trợ đo RTT và cơ chế bảo vệ chống gói cũ trong một số triển khai | Không phải đồng hồ hệ thống có thể dùng để xác thực danh tính |
| **ECN-related signaling** | Có thể hỗ trợ báo tắc nghẽn theo cơ chế ECN khi hai đầu và đường mạng phù hợp | Không phải cơ chế chống tấn công hoặc mã hóa |

MSS, cửa sổ nhận và RTT ảnh hưởng hiệu năng, còn TLS/mTLS, xác thực ứng dụng và chính sách mạng xử lý các mục tiêu bảo mật khác. Không thể suy ra một phiên “an toàn” chỉ từ việc có đủ TCP options.

## 4. Các trạng thái TCP và điều gì xảy ra khi mất gói?

Một mô hình mở kết nối phổ biến:

~~~mermaid
flowchart TD
    CL["Client: CLOSED"] -->|"Gửi SYN"| CS["SYN-SENT"]
    SL["Server: LISTEN"] -->|"Nhận SYN, gửi SYN-ACK"| SR["SYN-RECEIVED"]
    CS -->|"Nhận SYN-ACK, gửi ACK"| CE["Client: ESTABLISHED"]
    SR -->|"Nhận ACK hợp lệ"| SE["Server: ESTABLISHED"]
    CS -.->|"Timeout / lỗi / RST"| CF["Lỗi kết nối"]
    SR -.->|"Không nhận ACK, vượt thời gian xử lý"| SF["Bỏ trạng thái đang chờ"]
~~~

Có các nhánh đặc biệt như simultaneous open (hai phía cùng gửi SYN), nhưng không phải đường đi phổ biến của client kết nối đến server lắng nghe.

### Trường hợp A: SYN đầu tiên bị mất

Client không nhận phản hồi nên có thể **truyền lại SYN** theo chiến lược timeout của hệ điều hành. Nếu vẫn không có phản hồi, connect có thể thất bại do quá thời gian. Không có SYN-ACK không đủ để khẳng định server đã tắt: có thể lỗi DNS dẫn đến chọn sai IP, đường đi một chiều, NAT, ACL, firewall hoặc vấn đề ở server.

### Trường hợp B: SYN-ACK bị mất

Server có thể ở trạng thái **SYN-RECEIVED**, chờ ACK và truyền lại SYN-ACK theo cơ chế của hệ điều hành. Client chưa nhận phản hồi nên cũng có thể truyền lại SYN. Trong packet capture, nhiều SYN hoặc SYN-ACK lặp lại **không tự động chứng minh có tấn công**.

### Trường hợp C: ACK thứ ba bị mất

Client có thể đã coi kết nối là thiết lập trong khi server còn đợi ACK; server có thể truyền lại SYN-ACK. Một ACK hợp lệ hoặc dữ liệu tiếp theo của client có thể giúp server hoàn tất trạng thái, tùy triển khai và tình huống. Vì vậy phải quan sát **cả hai đầu** khi điều tra trạng thái kết nối không nhất quán.

### Trường hợp D: RST hoặc ICMP

Nếu server nhận SYN ở cổng không có dịch vụ lắng nghe, thường có phản hồi TCP **RST**. Một thiết bị lọc cũng có thể từ chối chủ động bằng RST hoặc ICMP thích hợp, hoặc **drop** gói khiến client đợi timeout. Cần xác định nguồn phát, thời gian và chính sách trước khi quy kết nguyên nhân.

### Handshake thành công chưa có nghĩa ứng dụng hoạt động

Khi TCP đã ESTABLISHED, ứng dụng vẫn có thể thất bại vì TLS không bắt tay được, chứng chỉ sai, proxy không kết nối được backend, thiếu quyền, server trả HTTP 5xx hoặc database không sẵn sàng. Kiểm tra TCP chỉ xác nhận một phần của đường truyền.

## 5. Phân tích một bản bắt gói đơn giản

Giả sử Wireshark/tcpdump ghi nhận ba phân đoạn sau. Các địa chỉ riêng và giá trị Sequence chỉ dùng để minh họa; phần mềm bắt gói có thể hiển thị số thứ tự **tương đối** thay vì số tuyệt đối:

~~~text
09:00:00.000000 IP 10.20.10.15.51542 > 10.20.20.25.443: Flags [S],  seq 1000, win 64240, length 0
09:00:00.012000 IP 10.20.20.25.443 > 10.20.10.15.51542: Flags [S.], seq 7000, ack 1001, win 64240, length 0
09:00:00.013000 IP 10.20.10.15.51542 > 10.20.20.25.443: Flags [.],  seq 1001, ack 7001, win 502, length 0
~~~

**Các bước đọc đúng:**

1. **Ghép cùng kết nối** bằng IP/cổng nguồn và đích, xét cả chiều đi và về.
2. Tìm **SYN không có ACK** để xác định ai chủ động mở kết nối.
3. Kiểm tra có **SYN-ACK đúng chiều về**, ACK có bằng ISN client + 1 không.
4. Kiểm tra có **ACK thứ ba** xác nhận ISN server + 1 không.
5. Xem gói dữ liệu/TLS tiếp theo để biết ứng dụng có bắt đầu trao đổi hay không.
6. Đối chiếu log firewall, load balancer, proxy, hệ điều hành và thời gian thực của các điểm quan sát.

Độ chênh thời gian giữa SYN và SYN-ACK là chỉ báo hữu ích về đường đi và thời gian xử lý phản hồi; **không** thể mặc định nó bằng RTT mạng thuần túy vì còn thời gian xử lý, vị trí capture và yếu tố triển khai.

### Ví dụ bắt gói có kiểm soát trên Linux

Chỉ thực hiện trên máy hoặc mạng mà bạn có quyền quản trị, đúng phạm vi cần kiểm tra:

~~~bash
# Xem tên giao diện và địa chỉ hiện tại
ip -br address

# Kiểm tra TCP socket theo trạng thái
ss -nt state syn-sent
ss -nt state syn-recv
ss -nt state established

# Quan sát tối đa 30 phân đoạn của dịch vụ TCP 443 tới một host được phép
sudo tcpdump -i eth0 -nn -c 30 'host 10.20.20.25 and tcp port 443'

# Nếu chỉ cần tìm các gói có cờ SYN: bao gồm SYN và SYN-ACK
sudo tcpdump -i eth0 -nn -c 30 'host 10.20.20.25 and tcp[tcpflags] & tcp-syn != 0'
~~~

**eth0** chỉ là tên giao diện giả định; trong môi trường thật, hãy thay bằng tên phù hợp. Lệnh lọc chỉ SYN sẽ **không** hiện ACK thứ ba nếu ACK không mang cờ SYN. Vì vậy, muốn xác minh đủ ba bước thì dùng bộ lọc TCP/host/cổng chung và kiểm tra từng gói.

Ví dụ trên Windows PowerShell:

~~~powershell
# Kiểm tra khả năng kết nối TCP từ máy hiện tại tới đích được phép
Test-NetConnection -ComputerName 10.20.20.25 -Port 443
~~~

Lệnh trên có thể cho biết việc kết nối TCP thành công hay không nhưng **không thay thế packet capture** và không chứng minh chứng chỉ TLS, phân quyền ứng dụng hoặc dữ liệu HTTP hoạt động đúng.

Trong Wireshark, có thể dùng các display filter:

~~~text
tcp.flags.syn == 1
tcp.flags.syn == 1 && tcp.flags.ack == 0
ip.addr == 10.20.20.25 && tcp.port == 443
tcp.analysis.retransmission
~~~

Display filter hiển thị các gói đã bắt; nếu bộ lọc bắt gói ban đầu bỏ sót ACK hoặc chỉ thu một chiều, không thể dựa vào kết quả hiển thị để kết luận phía kia không gửi. Với các giao thức có dùng IPv6, cần điều chỉnh bộ lọc IP cho phù hợp. Bản bắt gói có thể chứa IP nội bộ, metadata hoặc dữ liệu nhạy cảm; kiểm soát phạm vi, người truy cập và thời gian lưu trữ.

## 6. TCP handshake đi qua firewall, NAT và load balancer

### 6.1. Stateful firewall theo dõi luồng

**Stateful firewall** thường dùng thông tin kết nối để cho phép phản hồi đi ngược chiều qua những chính sách đã được thiết kế. Một gói SYN có thể làm phát sinh trạng thái theo dõi; các gói SYN-ACK/ACK và dữ liệu tiếp theo cần khớp chính sách và trạng thái hợp lệ. Việc tạo trạng thái trước khi handshake hoàn tất **không** có nghĩa client đã được xác thực bằng ứng dụng.

Ví dụ cho phép client từ vùng ứng dụng truy cập TCP 443 của một dịch vụ nội bộ: firewall có thể cho phép SYN theo luật nguồn–đích và cho lưu lượng chiều về thuộc kết nối hợp lệ. Không nhất thiết tạo một luật rộng cho phép mọi gói từ server về toàn bộ mạng client.

### 6.2. NAT thay đổi địa chỉ và/hoặc cổng

Ở NAT/PAT, địa chỉ và cổng quan sát **trước** và **sau** thiết bị dịch địa chỉ có thể khác nhau. Khi ghép log handshake qua nhiều điểm, cần thêm bản ghi dịch NAT, timestamp và connection tracking. Không nên so sánh hai 5-tuple ở hai phía NAT rồi kết luận chúng thuộc hai kết nối khác nhau.

### 6.3. Load balancer có thể kết thúc kết nối

Load balancer ở chế độ TCP proxy có thể thiết lập **hai kết nối TCP riêng**: một từ client đến load balancer, một từ load balancer đến backend. Vì vậy, bắt tay phía client thành công nhưng backend vẫn lỗi là tình huống có thể xảy ra. Trong chế độ chuyển tiếp gói (pass-through) hoặc các thiết kế khác, đường gói và chủ thể bắt tay có thể khác; cần kiểm tra kiến trúc cụ thể.

### 6.4. Đường đi bất đối xứng

Nếu SYN qua firewall A nhưng SYN-ACK trở về theo đường không có trạng thái tương ứng, thiết bị kiểm soát có thể loại gói. Hiện tượng này thường được khảo sát bằng cách đối chiếu định tuyến hai chiều, NAT, connection tracking và log ở từng điểm. Một số triển khai hỗ trợ đồng bộ trạng thái hoặc thiết kế đường đi phù hợp; không nên “sửa nhanh” bằng cách mở toàn bộ lưu lượng liên vùng.

### 6.5. Phân đoạn và nguyên tắc quyền tối thiểu

Các vùng Internet, DMZ, ứng dụng, database và quản trị nên có **ma trận kết nối được phép**. Chẳng hạn, gateway công khai được nhận HTTPS từ Internet, nhưng cổng SSH của mạng quản trị không cần xuất hiện trên đường công khai. Một handshake thành công đến database từ nguồn không thuộc luồng nghiệp vụ là dấu hiệu cần kiểm tra chính sách, dù nó chưa đủ chứng minh có đăng nhập database trái phép.

## 7. Rủi ro bảo mật gắn với handshake

### 7.1. SYN flood: làm cạn tài nguyên xử lý kết nối

Một cuộc **SYN flood** cố tạo rất nhiều yêu cầu mở kết nối. Nếu server hoặc thiết bị trung gian duy trì lượng lớn trạng thái **SYN-RECEIVED** hoặc phải xử lý lưu lượng quá tải, tài nguyên dành cho các kết nối hợp lệ có thể bị ảnh hưởng. Tấn công có thể dùng địa chỉ nguồn giả mạo, nguồn thực phân tán hoặc nhiều chiến thuật khác nhau; không phải SYN flood nào cũng chỉ thể hiện bằng bảng kết nối nửa mở lớn.

~~~mermaid
sequenceDiagram
    participant A as Nhiều nguồn / lưu lượng bất thường
    participant F as Thiết bị biên
    participant S as Server
    A->>F: Rất nhiều TCP SYN
    F->>S: SYN qua chính sách
    S-->>F: SYN-ACK / cấp tài nguyên
    Note over S: Có thể phát sinh áp lực trạng thái và xử lý
    Note over F,S: Lọc, hạn chế tốc độ, SYN cookies / SYN proxy tùy kiến trúc
~~~

Những lớp phòng vệ nên cân nhắc:

- **Giảm bề mặt công khai:** chỉ mở cổng dịch vụ thật sự cần thiết; giới hạn mạng quản trị và các cổng nội bộ.
- **SYN cookies** khi được hệ điều hành hỗ trợ và phù hợp: giảm nhu cầu giữ trạng thái cho một số yêu cầu đang chờ; tính năng và sự đánh đổi tùy hệ điều hành, phiên bản và tùy chọn TCP.
- **SYN proxy / TCP proxy** hoặc thiết bị chống DDoS: xác minh/điều tiết kết nối trước khi chuyển đến backend, theo đặc tính sản phẩm.
- **Giới hạn tốc độ và tài nguyên có kiểm soát:** điều chỉnh backlog, timeout và năng lực phục vụ dựa trên đo đạc, tránh chặn nhầm người dùng hợp lệ.
- **Lọc giả mạo nguồn và phối hợp nhà mạng:** anti-spoofing ở nơi có thể thực hiện; dùng dịch vụ bảo vệ upstream nếu lưu lượng đã bão hòa đường truyền.
- **Quan sát và ứng phó:** theo dõi tốc độ SYN, tỷ lệ hoàn tất handshake, retransmission, số kết nối chờ, độ trễ dịch vụ và tỷ lệ từ chối.

Không nên coi việc “tăng backlog” là giải pháp đầy đủ: nếu băng thông đầu vào bị bão hòa, tài nguyên ứng dụng hoặc tầng biên bị nghẽn thì phải xử lý ở điểm khác trên đường đi.

### 7.2. Giả mạo IP và dự đoán số thứ tự

Gói SYN có thể mang **địa chỉ IP nguồn bị giả mạo** khi hạ tầng cho phép. Nhưng với kết nối TCP thông thường, để hoàn tất ba bước từ ngoài đường đi, phía giả mạo còn cần ACK hợp lệ cho ISN của server, vốn thường không nhìn thấy trong phản hồi gửi đến IP bị mạo danh.

Việc **chọn ISN khó dự đoán** và sử dụng cơ chế bảo vệ TCP thích hợp giúp giảm rủi ro tấn công giả mạo hoặc chèn gói ngoài đường đi. Tuy vậy, một tác nhân quan sát hoặc kiểm soát đường truyền vẫn tạo ra rủi ro khác. **TCP handshake không chứng minh người gửi thực sự là chủ tài khoản hay có quyền sử dụng ứng dụng.**

### 7.3. RST giả mạo, chiếm phiên và chèn dữ liệu

Khi kẻ tấn công có đủ thông tin và vị trí phù hợp, việc gửi các gói RST hoặc phân đoạn giả có thể làm gián đoạn hoặc thao túng phiên TCP. Kiểm tra số thứ tự và trạng thái làm những hành vi đó khó hơn trong nhiều trường hợp nhưng không thay cho mã hóa và xác thực nội dung.

Đối với dữ liệu nhạy cảm, cần triển khai **TLS** thích hợp, xác minh chứng chỉ máy chủ, quản lý khóa và xác thực/ủy quyền ở tầng ứng dụng. Một IDS/IPS hoặc firewall có thể hỗ trợ phát hiện một số mẫu bất thường, nhưng không nên coi đó là nguồn bảo đảm duy nhất.

### 7.4. Lạm dụng trạng thái tại firewall và thiết bị trung gian

Không chỉ server, firewall/NAT/load balancer cũng có thể phải giữ trạng thái theo dõi kết nối. Khi lượng handshake bất thường tăng cao, bảng trạng thái hoặc CPU của thiết bị này có thể chịu áp lực. Cần theo dõi số session, trạng thái chờ, drop reason, khả năng khôi phục và chính sách khi thiết bị cạn tài nguyên.

## 8. Tách TCP handshake khỏi TLS, HTTP và QUIC

Trong hệ thống web, chữ “handshake” có thể chỉ những việc khác nhau:

| Giai đoạn/cơ chế | Tác dụng chính | Có thay thế TCP handshake không? |
|---|---|---|
| **DNS lookup** | Tìm địa chỉ của dịch vụ theo tên | Không. DNS thường diễn ra trước việc kết nối tới đích, nhưng có thể dùng cache hoặc cách phân giải khác |
| **TCP three-way handshake** | Tạo kết nối TCP, đồng bộ số thứ tự và tùy chọn | Đây là bắt tay của TCP |
| **TLS handshake** | Thỏa thuận tham số mật mã, xác thực máy chủ và thiết lập khóa, có thể xác thực client theo cấu hình | Không. Với TLS chạy trên TCP, việc thiết lập TCP thường diễn ra trước |
| **HTTP request/response** | Trao đổi thông điệp nghiệp vụ sau khi tầng truyền và bảo mật cần thiết sẵn sàng | Không. HTTP định nghĩa ngữ nghĩa yêu cầu/phản hồi |
| **QUIC / HTTP/3** | QUIC chạy trên **UDP**, tích hợp bảo mật TLS 1.3 và cơ chế truyền tải riêng | Không dùng TCP three-way handshake cho kết nối QUIC |

Ví dụ với HTTPS dùng HTTP/1.1 hoặc HTTP/2 qua TCP:

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant W as Web server
    B->>W: TCP SYN
    W-->>B: TCP SYN-ACK
    B->>W: TCP ACK
    B->>W: TLS ClientHello
    W-->>B: Các thông điệp TLS của server
    B->>W: Các bước TLS còn lại theo phiên bản/cấu hình
    Note over B,W: Kênh TLS được thiết lập
    B->>W: HTTP request qua TLS
    W-->>B: HTTP response qua TLS
~~~

Trình tự TLS chi tiết tùy phiên bản, khả năng tiếp tục phiên và tính năng được dùng; sơ đồ chỉ nêu ranh giới giao thức. Nếu TCP handshake thành công nhưng kiểm tra chứng chỉ TLS thất bại thì trình duyệt vẫn không nên chấp nhận kết nối HTTPS.

**HTTP/3 sử dụng QUIC trên UDP** (thường cổng UDP 443); khi điều tra một dịch vụ web hiện đại, không thấy TCP SYN ở cổng 443 **không tự động** đồng nghĩa không có lưu lượng HTTPS. Phải xét cả TCP và UDP theo công nghệ triển khai.

## 9. Chẩn đoán sự cố từ các mẫu gói phổ biến

| Mẫu quan sát | Khả năng cần kiểm tra | Bước xác minh tiếp |
|---|---|---|
| Nhiều SYN từ client, không thấy phản hồi | Lỗi đường đi, ACL/firewall drop, IP/port sai, server không tới được hoặc mất phản hồi | Bắt gói phía server/biên, kiểm tra route, NAT, log deny |
| SYN → RST nhanh | Không có dịch vụ lắng nghe, thiết bị từ chối hoặc chính sách reject | Xác định chính xác nguồn phát RST, kiểm tra socket dịch vụ |
| Có SYN và SYN-ACK, không thấy ACK cuối | Đường về/chiều đi mất gói, firewall bất đối xứng, capture chưa đủ hai chiều | So sánh capture hai đầu và trạng thái firewall |
| SYN-ACK được truyền lại nhiều lần | Server chưa nhận ACK hợp lệ, lỗi mất gói hoặc trạng thái không nhất quán | Đối chiếu sequence, thời gian, NAT và thiết bị trung gian |
| Đủ SYN/SYN-ACK/ACK nhưng ứng dụng không trả dữ liệu | Lỗi TLS, xác thực ứng dụng, proxy/backend, server quá tải hoặc timeout tầng cao | Kiểm tra TLS alert, HTTP, access/error log và backend |
| Nhiều SYN tăng đột biến, rất ít kết nối được hoàn tất | SYN flood, lỗi kết nối quy mô lớn, khách hàng retry hàng loạt | So sánh baseline, nhiều nguồn/đích, tỷ lệ handshake và tài nguyên |
| Bắt được handshake hoàn tất ở client nhưng server báo thiếu kết nối | Capture qua load balancer/proxy, mất trạng thái backend, khác thời điểm hoặc đường đi | Xác định có một hay nhiều TCP session; so sánh đúng 5-tuple ở từng chặng |
| TCP 443 không có SYN nhưng vẫn có HTTPS | Kết nối TCP được giữ lại và tái sử dụng hoặc ứng dụng dùng HTTP/3 trên UDP | Xem đầy đủ khoảng thời gian, TCP hiện có và UDP/QUIC |

Một mẫu gói chỉ là **dấu hiệu**, không phải kết luận cuối cùng. Ví dụ, SYN lặp lại có thể do mạng mất gói, retry của client hoặc lưu lượng tấn công. Cần đối chiếu **tài sản đích, mục đích nghiệp vụ, thay đổi gần đây, baseline, số lượng nguồn, thời gian và log tại điểm kiểm soát**.

### Quy trình điều tra ngắn

1. **Xác định kết nối:** hostname/IP, cổng, nguồn thực, NAT, giao thức TCP hay UDP.
2. **Kiểm tra dịch vụ lắng nghe:** đúng địa chỉ và cổng hay chưa, ứng dụng có chạy không.
3. **Quan sát đường hai chiều:** có SYN, SYN-ACK, ACK? Có RST, retransmission hoặc ICMP không?
4. **Đối chiếu firewall/NAT/load balancer:** rule cho phép/deny, trạng thái session, bảng dịch, hướng định tuyến, tình trạng tài nguyên.
5. **Tách lỗi tầng vận chuyển và tầng cao:** nếu TCP đã ESTABLISHED, chuyển sang TLS/HTTP/application logs.
6. **Xác nhận biện pháp sửa:** thử cả kết nối được phép và kết nối phải bị chặn; giám sát tránh mở quyền quá rộng.

## 10. Tình huống thực tế: API kết nối database qua firewall

Giả sử hệ thống có ba vùng mạng:

- **Frontend:** 10.20.10.0/24, phục vụ yêu cầu người dùng.
- **Backend:** 10.20.20.0/24, chứa API được phép truy cập database.
- **Database:** 10.20.30.0/24, có PostgreSQL nghe tại TCP 5432.

Theo nguyên tắc quyền tối thiểu, chỉ nhóm backend cần thiết được phép tạo kết nối mới đến database. Frontend không có lý do truy cập trực tiếp vào cổng database.

| Nguồn → đích | SYN | Kết quả chính sách mong muốn |
|---|---|---|
| API 10.20.20.15 → DB 10.20.30.25:5432 | Đi qua điểm kiểm soát | Được phép nếu đúng workload và luật đã duyệt |
| Frontend 10.20.10.16 → DB 10.20.30.25:5432 | Đi qua điểm kiểm soát | Bị từ chối hoặc drop theo cấu hình |
| Internet → DB 10.20.30.25:5432 | Không có đường công khai hợp lệ | Không thể truy cập trực tiếp |
| Quản trị viên → DB qua kênh quản trị được phép | Qua nguồn/đích và xác thực riêng | Chỉ được cấp quyền đúng nhu cầu và có log |

**Bẫy thường gặp:** Nhìn thấy SYN-ACK trong capture ở API không đủ để kết luận API đã được xác thực vào PostgreSQL. SYN-ACK chỉ chứng minh dịch vụ TCP đã phản hồi yêu cầu mở kết nối. Cần kiểm tra cả xác thực database, TLS khi dùng, quyền của tài khoản và các quy tắc ứng dụng.

Khi database đột ngột không kết nối được, một hướng điều tra hợp lý:

~~~text
API gửi SYN?
   |
   +-- Không --> Kiểm tra ứng dụng, DNS, socket, routing ở API.
   |
   +-- Có --> SYN có tới database / firewall không?
                 |
                 +-- Không --> Kiểm tra routing, ACL, NAT, phân đoạn.
                 |
                 +-- Có --> Database có trả SYN-ACK hay RST không?
                               |
                               +-- Không --> Kiểm tra cổng lắng nghe,
                               |            firewall phía DB, tài nguyên.
                               |
                               +-- Có SYN-ACK --> ACK cuối có đến DB không?
                                                |
                                                +-- Không --> Kiểm tra đường về,
                                                |            firewall state, NAT.
                                                |
                                                +-- Có --> Chuyển sang TLS/DB
                                                             auth và log ứng dụng.
~~~

Khi có nhiều đường truyền, mỗi dấu hiệu cần xác nhận ở điểm quan sát liên quan. Không suy ra gói thực sự đến server chỉ vì đã thấy gói tại client.

## 11. Các hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “SYN-ACK nghĩa là hai phía đã hoàn tất bắt tay.” | Phía server thông thường vẫn đợi ACK hợp lệ ở bước ba. |
| “ACK bằng số gói vừa nhận cộng một.” | ACK là số **byte tiếp theo chờ nhận**, không phải số thứ tự gói; SYN/FIN tiêu thụ một vị trí. |
| “Kết nối TCP được mở thì dữ liệu được mã hóa.” | TCP không cung cấp mã hóa; cần TLS hoặc cơ chế thích hợp khác. |
| “TCP handshake xác thực người dùng.” | Handshake tạo trạng thái truyền tải, không thay việc kiểm tra danh tính và phân quyền ứng dụng. |
| “Không thấy gói SYN chứng tỏ trang web không hoạt động.” | Có thể đang dùng kết nối giữ lại, capture thiếu, hoặc HTTP/3 chạy qua QUIC/UDP. |
| “Mỗi SYN bị lặp lại là tấn công.” | Retransmission có thể do mất gói hoặc lỗi mạng; phải xem tần suất, mẫu nguồn và trạng thái. |
| “TCP port 443 luôn là HTTPS hợp lệ.” | Cổng chỉ là thông tin định tuyến tới dịch vụ, không chứng minh TLS hay chứng chỉ đúng. |
| “Firewall chỉ cần mở cổng đi là đủ.” | Stateful inspection, đường về, NAT, định tuyến bất đối xứng và chính sách liên vùng đều có thể ảnh hưởng. |
| “SYN cookies giải quyết mọi kiểu DDoS.” | Chúng giảm một số áp lực giữ trạng thái nhưng không chữa nghẽn băng thông, quá tải ứng dụng hay tấn công khác. |

## 12. Câu hỏi ôn tập và bài tập

**Câu 1.** Client có ISN = 42000 và server có ISN = 81000. Nếu không có payload trong SYN, ba bước có Sequence/Acknowledgment là bao nhiêu?

**Đáp án:** Client SYN Seq = 42000; Server SYN-ACK Seq = 81000, Ack = 42001; Client ACK Seq = 42001, Ack = 81001.

**Câu 2.** Một capture ở client thấy SYN, SYN-ACK, ACK, sau đó TLS alert. TCP handshake đã thất bại chưa?

**Đáp án:** Bắt tay TCP thông thường đã hoàn tất theo capture ở client. Lỗi quan sát được ở giai đoạn TLS hoặc ngữ cảnh cao hơn, cần kiểm tra alert, chứng chỉ, giao thức và log server.

**Câu 3.** Vì sao thiết bị lọc trạng thái có thể chặn SYN-ACK dù client đã gửi SYN?

**Gợi ý:** SYN có thể đi theo đường khác, bảng trạng thái chưa được tạo hoặc đã hết hạn, chính sách không khớp, NAT sai, thiết bị quá tải hoặc tuyến phản hồi bất đối xứng.

**Câu 4.** Một máy chủ nhận nhiều SYN nhưng rất ít ACK thứ ba. Có thể khẳng định đang bị tấn công không?

**Đáp án:** Chưa. Cần xem lưu lượng nền, nguồn IP, mức tăng đột biến, độ trễ, mất gói, định tuyến và tài nguyên server/firewall. SYN flood là một khả năng, nhưng sự cố mạng hoặc retry quy mô lớn cũng có thể tạo tín hiệu tương tự.

**Bài thực hành có kiểm soát:** Trên một máy client và server thử nghiệm mà bạn quản trị, cho server lắng nghe ở một cổng TCP, dùng công cụ kết nối thông thường từ client và bắt gói cả hai phía. Hãy:

1. Xác định SYN, SYN-ACK, ACK và đối chiếu Sequence/Acknowledgment.
2. Ghi lại cổng nguồn tạm thời, cổng đích, MSS và Window Scale nếu có.
3. Xác minh client kết nối đúng cổng có dịch vụ hoạt động, rồi quan sát phản hồi khi dùng một cổng **không có dịch vụ lắng nghe** trong môi trường kiểm thử.
4. So sánh quan sát từ hai phía và nhật ký firewall; phân biệt rõ RST, timeout và kết nối đã thiết lập.
5. Nếu ứng dụng dùng TLS, chỉ ra điểm TCP handshake kết thúc và TLS bắt đầu.

Không thực hiện thử nghiệm flood hoặc gây quá tải trên hệ thống production; mục tiêu của bài là hiểu giao thức và phân tích chính xác lưu lượng được phép quan sát.

## Ghi nhớ

**TCP three-way handshake = SYN → SYN-ACK → ACK.** Client và server trao đổi hai ISN riêng và xác nhận số thứ tự của nhau; SYN tiêu thụ một số thứ tự, nên phản hồi ACK cho SYN thông thường bằng **ISN + 1**. Server chỉ hoàn tất bắt tay theo luồng thường khi nhận ACK hợp lệ cuối cùng.

Khi kiểm tra an toàn mạng, hãy đối chiếu handshake với **luồng được phép, ranh giới tin cậy, stateful firewall, NAT, IDS/IPS và khả năng quan sát hai chiều**. Handshake cho biết kết nối TCP được thiết lập ra sao; còn danh tính, mã hóa, quyền ứng dụng và tính sẵn sàng đòi hỏi các lớp phòng vệ bổ sung.
