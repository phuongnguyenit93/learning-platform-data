# TCP handshake trong bản ghi gói tin: Đọc SYN, SYN/ACK, ACK và tìm nguyên nhân lỗi kết nối

## 1. Vì sao cần đọc TCP handshake từ packet capture?

Một ứng dụng báo *connection timed out*, VPN đã kết nối nhưng không truy cập được database, load balancer liên tục thấy backend **unhealthy**, hoặc firewall ghi nhận nhiều TCP SYN mà không có phiên hoàn chỉnh. Những tình huống này đòi hỏi người điều tra hiểu **ba bước bắt tay TCP** (*three-way handshake*) trên **bản ghi gói tin**, thay vì chỉ suy từ việc một cổng đang `LISTEN` hoặc từ một dòng log `connection failed`.

Khi có capture ở đúng vị trí, ta có thể xác định **ai chủ động mở kết nối, địa chỉ/port thực tế, cờ TCP, số thứ tự và xác nhận, độ trễ quan sát, tùy chọn TCP, retransmission và các phản hồi RST/ICMP**. Khi thiếu một gói, ta phải đánh giá **điểm thu, filter, NAT, đường bất đối xứng và khả năng mất gói trong chính công cụ capture** trước khi kết luận mạng đã drop.

Chủ đề thuộc chương **Packet capture và phân tích lưu lượng**, module **SECURITY_NETWORK_SECURITY**: phân tích gói giúp kiểm chứng phân đoạn mạng, firewall, VPN, IDS/IPS, TLS, DNS, network threat modeling và kiến trúc mạng an toàn dựa trên chứng cứ. TCP handshake là bước tạo **trạng thái transport**, không tự xác thực người dùng hay mã hóa dữ liệu ứng dụng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả đúng các trạng thái cơ bản của **TCP active open** và **passive open**, gồm SYN, SYN/ACK, ACK.
2. Đọc các trường **source/destination IP/port, flags, sequence/acknowledgment numbers, window, TCP options** và phân biệt số tuyệt đối với số tương đối.
3. Chứng minh cách **SYN và FIN tiêu tốn một sequence number**, trong khi ACK thuần không tiêu tốn sequence space.
4. Dùng **Wireshark**, **tshark** và **tcpdump** để chọn đúng một TCP flow, phân biệt capture filter BPF với display filter.
5. Ước lượng thời gian bắt tay từ capture và giới hạn của việc suy **RTT**.
6. Giải thích **MSS, Window Scale, SACK Permitted, Timestamps, ECN** trong SYN và SYN/ACK.
7. Phân biệt **SYN retransmission, TCP RST, silent drop, ICMP reject, backlog pressure và SYN cookies** qua những bằng chứng có thể và không thể quan sát.
8. Nhận diện **NAT, proxy, load balancer, TLS termination, asymmetric routing, offloads** và capture vantage ảnh hưởng phân tích.
9. Làm lab an toàn trong phạm vi kiểm soát, lập ma trận **positive/negative tests** và lưu chứng cứ có bảo vệ dữ liệu.
10. Viết runbook điều tra sự cố TCP connect và an ninh mạng mà không khẳng định quá mức từ một pcap.

> **Phạm vi và an toàn:** ví dụ dùng IP tài liệu `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` và hostname `*.example.test` theo RFC 5737. Chỉ capture trên host, interface và kết nối bạn có quyền quản lý/kiểm thử; không nghe lén traffic của người khác, không gửi SYN flood, quét port diện rộng hoặc vô hiệu hóa firewall/IDS để làm bài. Khi dùng ví dụ lệnh cần thay host/port bằng endpoint của lab được phê duyệt. File pcap có thể chứa cookies, token, địa chỉ nội bộ và dữ liệu nhạy cảm ngay cả khi mục tiêu chỉ là handshake.

## 2. TCP nằm ở đâu trong mô hình mạng?

TCP là giao thức transport **hướng kết nối**, cung cấp luồng byte có thứ tự và cơ chế xác nhận/retransmission/flow control. Trước khi phần lớn ứng dụng gửi dữ liệu qua một kết nối TCP thông thường, hai đầu thực hiện quá trình thiết lập trạng thái. TCP chạy trên IP; dưới IP có thể là Ethernet, Wi-Fi, VPN tunnel, overlay hoặc một phương tiện khác.

~~~mermaid
flowchart LR
    APP["Ứng dụng / HTTP hoặc SSH"] --> TCP["TCP transport"]
    TCP --> IP["IPv4 / IPv6"]
    IP --> LINK["Ethernet / Wi-Fi / overlay"]
    CAP["Packet capture tại interface"] -. "Quan sát packet headers và payload nếu có" .-> LINK
    FW["Firewall / NAT / proxy"] -. "Có thể lọc, chuyển địa chỉ, kết thúc hoặc tạo kết nối mới" .-> IP
~~~

Một flow TCP thường được nhận diện bằng **giao thức, địa chỉ nguồn/đích và port nguồn/đích**:

~~~text
TCP/IPv4 flow (hướng client -> server):
  Source IP:      192.0.2.10
  Source port:    51514
  Destination IP: 198.51.100.20
  Destination port: 443
  Protocol:       TCP (IP protocol number 6)

Response direction:
  198.51.100.20:443 -> 192.0.2.10:51514
~~~

Ở IPv6, nguyên tắc tương tự với hai IPv6 addresses. Một **5-tuple** giúp nhóm packets tại một điểm quan sát, nhưng **NAT/proxy có thể đổi tuple** giữa hai capture points. Ngoài ra, cùng một tuple có thể được sử dụng lại theo thời gian sau khi kết nối cũ kết thúc; cần xem timestamps, SYN sequence numbers và TCP lifecycle để phân biệt.

### 2.1. TCP handshake không phải TLS handshake

| TCP handshake | TLS handshake |
|---|---|
| Tạo trạng thái transport và đồng bộ sequence spaces | Thỏa thuận cơ chế bảo vệ kênh và xác thực peer theo cấu hình |
| Quan sát chính qua SYN, SYN/ACK, ACK | Quan sát bản tin TLS hoặc QUIC crypto sau/ngoài TCP tùy giao thức |
| Không xác nhận danh tính user/application và không mã hóa | Có thể xác minh certificate/hostname, trao đổi khóa và bảo vệ dữ liệu |
| Có thể hoàn tất ngay cả khi ứng dụng trả HTTP 403/500 | Có thể lỗi dù TCP connection đã thành công |
| TCP SYN có thể mang TCP options | TLS ClientHello nằm trong byte stream sau khi TCP established trong TLS-over-TCP thông thường |

**TCP connect thành công không chứng minh HTTPS, SSH login, VPN application access hoặc quyền dùng dịch vụ thành công.** Với HTTP/3, **QUIC chạy trên UDP**, không có TCP three-way handshake cho chính kết nối HTTP/3.

## 3. Three-way handshake: SYN → SYN/ACK → ACK

Hãy giả sử client `192.0.2.10:51514` chủ động kết nối server `198.51.100.20:443`:

~~~mermaid
sequenceDiagram
    participant C as Client 192.0.2.10:51514
    participant S as Server 198.51.100.20:443
    C->>S: SYN, seq=x, ACK flag=0
    S-->>C: SYN,ACK, seq=y, ack=x+1
    C->>S: ACK, seq=x+1, ack=y+1
    Note over C,S: Kết nối established ở hai phía theo trạng thái TCP
    C->>S: Application data / TLS ClientHello có thể theo sau
~~~

### 3.1. Gói 1 — Client gửi SYN

Client muốn khởi tạo kết nối nên đặt **SYN flag** và chọn một **Initial Sequence Number (ISN)**, ví dụ `x=1000`. SYN có thể mang tùy chọn về MSS, window scaling, SACK permitted và timestamps. SYN thường không mang application data trong TCP thông thường.

~~~text
192.0.2.10:51514 -> 198.51.100.20:443
Flags: [S]
Seq: 1000  (absolute, ví dụ)
Ack: không hợp lệ vì ACK flag chưa bật
TCP payload length: 0
~~~

Máy client thường đi từ `CLOSED` sang `SYN-SENT`. Việc một SYN xuất hiện trong pcap ở client **chưa chứng minh server đã nhận nó**.

### 3.2. Gói 2 — Server đáp SYN/ACK

Nếu đường đến server và chính sách cho phép, TCP listener có thể trả:

~~~text
198.51.100.20:443 -> 192.0.2.10:51514
Flags: [S.]
Seq: 7000 (server ISN y)
Ack: 1001 (= client ISN + 1)
TCP payload length: 0
~~~

Server vừa **đồng bộ sequence space của mình** bằng SYN, vừa xác nhận SYN của client. Trong normal passive open, server đi qua trạng thái `SYN-RECEIVED` và chờ ACK hợp lệ; cụ thể implementation có thể sử dụng SYN cookies, offload hoặc state handling khác.

### 3.3. Gói 3 — Client ACK lại SYN của server

~~~text
192.0.2.10:51514 -> 198.51.100.20:443
Flags: [.]
Seq: 1001
Ack: 7001 (= server ISN + 1)
TCP payload length: 0
~~~

ACK cuối xác nhận ISN của server. Client có thể xem kết nối established khi nhận SYN/ACK hợp lệ và gửi ACK; server coi hoàn tất khi nhận ACK tương ứng theo TCP state machine, trừ những cơ chế đặc biệt. Vì vậy một capture ở **client** thấy ACK phát ra không chứng minh ACK đã tới server.

### 3.4. SYN tiêu tốn một số thứ tự

Trong TCP sequence space, **SYN và FIN mỗi cờ chiếm một sequence number**; application payload chiếm số tương đương **số byte dữ liệu**. Một ACK thuần không tiêu tốn sequence number. Công thức đơn giản cho segment thông thường:

\[
\mathrm{next\ seq}=\mathrm{seq}
+\mathrm{payload\ bytes}
+I_{\mathrm{SYN}}
+I_{\mathrm{FIN}}
\]

Trong đó mỗi biến chỉ báo SYN/FIN bằng 1 nếu flag có mặt, ngược lại bằng 0. TCP sequence numbers là **32-bit, có wraparound**; các phép tính đơn giản cần hiểu modulo \(2^{32}\) nếu phân tích các kết nối dài hoặc số gần giới hạn.

### 3.5. Handshake bình thường chưa nói gì về dữ liệu ứng dụng

Sau ba bước, client có thể gửi TLS ClientHello, SSH version exchange hoặc HTTP request plaintext tùy dịch vụ. Một cổng TCP có listener sẵn có thể hoàn tất handshake nhưng **application process gặp lỗi ngay sau đó**, authentication thất bại, hoặc một proxy trả lỗi upstream. Phải theo dõi các packets **sau ACK cuối** và logs tương ứng khi điều tra service health.

## 4. Đọc một bản ghi gói tin chuẩn

Dưới đây là một đoạn **mô phỏng kiểu output `tcpdump`** đã lược giản các TCP options để làm rõ flags và sequence/ack:

~~~text
12:00:00.000000 IP 192.0.2.10.51514 > 198.51.100.20.443:
  Flags [S], seq 1000, win 64240, length 0
12:00:00.025000 IP 198.51.100.20.443 > 192.0.2.10.51514:
  Flags [S.], seq 7000, ack 1001, win 65160, length 0
12:00:00.025500 IP 192.0.2.10.51514 > 198.51.100.20.443:
  Flags [.], ack 7001, win 502, length 0
~~~

**Lưu ý quan trọng:** dòng ACK cuối thực tế có trường `seq` hoặc bị formatter ẩn tùy verbosity và cách `tcpdump` hiển thị **relative sequence numbers**. Đoạn trên minh họa cú pháp, **không phải log được chạy thật**. Những số `win` chỉ có ý nghĩa đúng khi biết negotiation window scale và cách formatter chọn hiển thị; không thể so giá trị win 502 và win 64240 như cùng một đơn vị *effective window* mà thiếu ngữ cảnh.

### 4.1. Bảng diễn giải từng packet

| # | Source → destination | TCP flags | Seq tuyệt đối | Ack tuyệt đối | Ý nghĩa |
|---|---|---|---:|---:|---|
| 1 | Client:51514 → Server:443 | SYN | 1000 | Không hợp lệ | Đề nghị mở kết nối |
| 2 | Server:443 → Client:51514 | SYN, ACK | 7000 | 1001 | Xác nhận client SYN, công bố server ISN |
| 3 | Client:51514 → Server:443 | ACK | 1001 | 7001 | Xác nhận server SYN |

### 4.2. Cờ TCP thường gặp

| Ký hiệu `tcpdump` | Flag | Ý nghĩa cơ bản |
|---|---|---|
| `S` | SYN | Đồng bộ sequence numbers, đề nghị tạo kết nối |
| `.` | ACK | Trường acknowledgment number có hiệu lực |
| `F` | FIN | Bên gửi không còn dữ liệu gửi sau vị trí FIN |
| `R` | RST | Reset/abort kết nối hoặc từ chối một segment theo trạng thái |
| `P` | PSH | Gợi ý về push dữ liệu tới ứng dụng nhận |
| `U` | URG | Urgent pointer có ý nghĩa khi được sử dụng |
| `E` | ECE | Liên quan ECN khi được đàm phán/sử dụng |
| `W` | CWR | Congestion Window Reduced, liên quan ECN |

Một segment **có thể mang nhiều cờ cùng lúc**. Ví dụ `[S.]` là SYN+ACK; `[P.]` là PSH+ACK; `[R.]` là RST+ACK. Không suy TCP state chỉ từ **một** flag mà không xem sequence, ack, flow và hướng.

### 4.3. `length 0` thường gặp trong handshake

Trong TCP thông thường, SYN, SYN/ACK và ACK hoàn tất có thể có `TCP payload length = 0`; options nằm trong **TCP header** nên không làm tăng TCP data length. **TCP Fast Open** và một số trường hợp đặc biệt có thể đưa data vào SYN; không khẳng định mọi SYN bắt buộc không có payload. Ngoài ra, packet có thể bị truncated bởi capture `snaplen`, làm thông tin data/options hiển thị không đầy đủ.

## 5. Sequence và acknowledgment numbers: tuyệt đối, tương đối và wraparound

Số **Sequence Number** trong TCP header là số thứ tự của byte đầu tiên của dữ liệu segment (hoặc ISN khi SYN). **Acknowledgment Number** khi ACK flag được bật cho biết **next byte expected** từ đối tác, nghĩa là bên nhận xác nhận đã nhận liên tục mọi byte trước giá trị ack đó theo semantics TCP.

### 5.1. Absolute sequence number

Trên dây, TCP header chứa số 32-bit. Ví dụ:

~~~text
Client SYN absolute seq = 3,200,000,000
Server SYN/ACK absolute ack = 3,200,000,001
~~~

ISN được chọn để bảo vệ tính đúng của kết nối và hạn chế trùng sequence giữa incarnations; **không suy ISN theo thứ tự mỗi kết nối hoặc theo thời gian chỉ bằng ví dụ thủ công**.

### 5.2. Relative sequence number trong Wireshark

Wireshark thường bật tùy chọn **Relative sequence numbers**, cho phép hiển thị các giá trị tương đối với ISN của mỗi hướng để dễ đọc:

~~~text
Frame 1  Client -> Server SYN      Seq=0       Len=0
Frame 2  Server -> Client SYN,ACK  Seq=0 Ack=1 Len=0
Frame 3  Client -> Server ACK      Seq=1 Ack=1 Len=0
Frame 4  Client -> Server data     Seq=1       Len=120
Frame 5  Server -> Client ACK      Ack=121
~~~

Ở dòng 5, `Ack=121` là **số tương đối phía client**, vì client đã dùng một sequence cho SYN và gửi 120 bytes dữ liệu từ relative `Seq=1` đến `120`; next expected byte là `121`. Wireshark có thể hiển thị sequence thực bên dưới thông tin raw nếu mở trường header, hoặc tắt relative sequence display trong preferences.

**Không nhầm relative `Seq=0` với giá trị ISN=0 thật trên mạng**. Khi so pcap ở hai vị trí, có thể dùng raw absolute numbers, TCP stream mapping, timestamp và 5-tuples đã tính tới NAT.

### 5.3. ACK là cumulative acknowledgment

TCP ACK thường mang tính **cộng dồn** (*cumulative*): `Ack=N` báo đã nhận liên tục các bytes trước N, chứ không chỉ xác nhận riêng packet gần nhất. Với SACK negotiation, TCP receiver còn có thể báo các **khối byte nhận được ngoài thứ tự** bên cạnh cumulative ACK, giúp sender tái truyền chính xác hơn.

### 5.4. ACK number chỉ có hiệu lực khi ACK flag bật

Trong SYN đầu tiên, một trường acknowledgment number có thể vẫn tồn tại về mặt vị trí bit trong TCP header nhưng **không được sử dụng làm xác nhận** vì ACK flag không bật. Tránh diễn giải giá trị thô của ACK number trên một segment chưa đặt ACK flag như một phản hồi từ peer.

### 5.5. Data trên gói ACK cuối

ACK hoàn tất handshake thường là gói rỗng, nhưng chuẩn TCP cho phép dữ liệu đi kèm khi trạng thái và implementation cho phép. Vì vậy bộ lọc tìm **chính xác `tcp.len == 0`** có thể bỏ sót một ACK cuối kèm dữ liệu trong trường hợp cụ thể; cần xem cờ/seq/ack và state, không phụ thuộc một mẫu ba dòng cứng.

## 6. Trạng thái TCP trong và sau quá trình bắt tay

TCP có **state machine** ở mỗi endpoint, còn file pcap chỉ là bằng chứng packets tại một điểm quan sát. Không phải packet capture luôn đủ để suy trạng thái thực trong kernel của cả hai máy.

| Trạng thái | Vị trí thường gặp | Ý nghĩa |
|---|---|---|
| `LISTEN` | Server trước kết nối | Chờ yêu cầu kết nối ở một local address/port theo cấu hình |
| `SYN-SENT` | Client sau khi gửi SYN | Đang đợi SYN/ACK hoặc trường hợp simultaneous open |
| `SYN-RECEIVED` | Server sau khi nhận SYN và gửi SYN/ACK | Đợi acknowledgment của SYN đã gửi; implementation có thể dùng SYN cookies |
| `ESTABLISHED` | Hai đầu sau handshake hợp lệ | Luồng byte có thể được trao đổi theo TCP |
| `FIN-WAIT-*`, `CLOSE-WAIT`, `LAST-ACK` | Giai đoạn đóng có trật tự | Thường liên quan FIN/ACK, **khác bắt tay mở kết nối** |
| `TIME-WAIT` | Một endpoint sau đóng theo điều kiện TCP | Giúp xử lý segments cũ và những vấn đề đóng kết nối |
| `CLOSED` | Không có kết nối ở trạng thái đang mở | Có thể nhận một SYN hợp lệ để bắt đầu phiên mới |

### 6.1. Khác nhau giữa active open và passive open

Trong mô hình thông thường, **client thực hiện active open** (gửi SYN) và server **passive open** (LISTEN). Tuy nhiên, một ứng dụng peer-to-peer hoặc một mô hình đặc biệt có thể xảy ra **simultaneous open**: cả hai bên chủ động gửi SYN, sau đó trao đổi SYN/ACK theo TCP state machine. **Không xem mẫu 3 gói là duy nhất** cho mọi sự kiện TCP hợp lệ.

### 6.2. `accept()` và handshake ở server

Một ứng dụng server thường gọi `listen()` rồi `accept()` để nhận connection được TCP stack hoàn tất. Packet SYN/ACK có thể được tạo bởi kernel trước khi chương trình ứng dụng nhận được socket đã established. Một server bị nghẽn application thread/accept queue có thể cho thấy TCP behavior khác nhau tùy implementation/backlog; **không kết luận ứng dụng đã xử lý request chỉ vì SYN/ACK đã gửi**.

### 6.3. Half-open không luôn là tấn công

Trong ngữ cảnh SYN backlog, một connection ở `SYN-RECEIVED` **chưa nhận được ACK cuối** thường được mô tả là half-open. Nó có thể phát sinh từ mạng chập chờn, loss, peer mất kết nối, firewall state, hoặc traffic độc hại. Cần xem **tỷ lệ SYN/ACK/ACK theo baseline, backlog metrics, source identity/network và tác động dịch vụ** trước khi phân loại là SYN flood.

### 6.4. ACK cuối không tới server

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Firewall / network
    participant S as Server
    C->>F: SYN
    F->>S: SYN
    S-->>F: SYN/ACK
    F-->>C: SYN/ACK
    C->>F: ACK cuối
    Note over F,S: ACK có thể bị drop trên đường tiếp
    S-->>F: SYN/ACK retransmission theo timeout nếu cần
    F-->>C: SYN/ACK lại
~~~

Ở client, ta có thể thấy **đã phát ACK** nhưng server vẫn **retransmit SYN/ACK**. Đây là manh mối cho thấy server chưa hoàn tất tiến trình như mong đợi; tuy vậy cũng có thể do capture thiếu packet, duplicate, trạng thái offload hoặc retransmission đã gửi trước ACK được xử lý. Phải đối chiếu **cả hai phía và timestamps**.

## 7. TCP options trong SYN và SYN/ACK

SYN thường mang nhiều thông tin thương lượng. Người phân tích không nên dừng ở ba flags; **TCP options ảnh hưởng hiệu năng, flow control và cách diễn giải các packet tiếp theo**.

### 7.1. Ví dụ options

~~~text
Client SYN:
  MSS 1460
  SACK permitted
  Timestamp TSval=100000 TSecr=0
  Window Scale=7

Server SYN/ACK:
  MSS 1380
  SACK permitted
  Timestamp TSval=600000 TSecr=100000
  Window Scale=8
~~~

Các giá trị là **minh họa**, không phải kết quả thật từ host. Cú pháp và thứ tự options trên bản ghi phụ thuộc OS, TCP stack và formatter.

### 7.2. MSS — Maximum Segment Size

**MSS option** trong SYN/SYN/ACK thông báo **kích thước tối đa của TCP data payload mỗi segment mà phía gửi option sẵn sàng nhận**, không phải MTU của link và không gồm TCP/IP headers.

Với một đường IPv4 không có IP/TCP options, MTU 1500 thường tương ứng **MSS 1460** do IPv4 header 20 B + TCP header 20 B. Nhưng thực tế **IPv6, tunnels/VPN encapsulation, TCP options và path MTU** có thể làm số khác. Nếu tunnel thêm overhead nhưng MSS không được điều chỉnh hay PMTUD lỗi, một TCP handshake có thể thành công nhưng **payload lớn bị treo**.

**MSS là thông tin từng chiều**: server gửi MSS trong SYN/ACK để nói kích cỡ nó có thể nhận, client gửi MSS trong SYN để nói kích cỡ client có thể nhận. Không suy hai đầu đang dùng cùng MSS chỉ vì một SYN.

### 7.3. Window Scale

TCP header có trường advertised **Window 16-bit**. **Window Scale option** được thương lượng trong SYN/SYN/ACK để cho phép receive window hiệu dụng lớn hơn 65.535 bytes trong các kết nối hỗ trợ. Scale factor bên nhận khai báo áp dụng cho **những window values mà chính bên đó quảng bá** sau giai đoạn handshake theo chuẩn; **không lấy raw window ở SYN và nhân scale tùy tiện**.

Ví dụ:

~~~text
Server SYN/ACK announces Window Scale=8
Later server ACK advertises raw window=512
Effective advertised receive window (illustrative) = 512 * 2^8
                                               = 131072 bytes
~~~

Để diễn giải đúng, cần xem cả hai hướng SYN negotiation, Wireshark `Calculated window size`, window scaling setting và việc capture có đủ giai đoạn bắt tay hay không. Nếu pcap bắt đầu giữa luồng, analyzer có thể không biết scale factor.

### 7.4. SACK Permitted và SACK blocks

**SACK Permitted** trong SYN cho biết một endpoint sẵn sàng hỗ trợ **Selective Acknowledgment**. Khi cả hai phía thương lượng phù hợp, những ACK về sau có thể chứa **SACK blocks**, chỉ rõ các đoạn byte nhận ngoài thứ tự. Không nhầm **SACK Permitted** trong handshake với **SACK blocks** xuất hiện trong giai đoạn truyền dữ liệu.

SACK giúp sender phục hồi sau mất gói hiệu quả hơn trong nhiều trường hợp, nhưng chỉ nhìn thấy SACK option không chứng minh **đã có loss**. Cần xem ACKs, sequence gaps, retransmissions và network path.

### 7.5. TCP Timestamps

**Timestamp option** thường gồm `TSval` (giá trị timestamp của sender) và `TSecr` (echo của peer theo semantics TCP). Nó có thể hỗ trợ RTT measurement và bảo vệ trước old duplicate segments (PAWS) theo RFC 7323. Không dùng TSval như đồng hồ UTC hoặc giả định nó có đơn vị một mili giây: nhịp/tốc độ timestamp phụ thuộc implementation.

Một SYN có thể có `TSecr=0`, SYN/ACK echo `TSval` của client trong `TSecr`, nhưng phải xét lựa chọn TCP options thật và phiên. TCP timestamp khác **timestamp do pcap/OS ghi khi bắt gói**.

### 7.6. ECN và những tính năng khác

Nếu dùng **Explicit Congestion Notification (ECN)**, các flags ECE/CWR và IP ECN bits liên quan thương lượng/đánh dấu congestion theo phiên bản TCP. **Không suy có congestion thực chỉ vì SYN chứa flags cho phép ECN**. Một số triển khai sử dụng TCP Fast Open option; nếu thấy application data trong SYN, cần xem capability, cookie và trạng thái tương ứng, không dùng quy tắc “mọi SYN dài 0” để bỏ gói.

### 7.7. Bảng tổng hợp TCP SYN options

| Option | Xuất hiện thường ở | Nói lên | Không tự chứng minh |
|---|---|---|---|
| MSS | SYN, SYN/ACK | Giới hạn receive segment data | MTU thật của cả đường |
| Window Scale | SYN, SYN/ACK | Khả năng mở rộng advertised receive window | Throughput thực, send congestion window |
| SACK Permitted | SYN, SYN/ACK | Đồng ý hỗ trợ selective ACK | Đã có packet loss |
| Timestamp | SYN, SYN/ACK và các segments sau nếu thương lượng | Timestamp echo/PAWS/RTT hỗ trợ | Unix time, latency chính xác không cần ngữ cảnh |
| TCP Fast Open | SYN và các trường hợp hỗ trợ | Khả năng gửi dữ liệu sớm | Mọi ứng dụng/đường mạng hỗ trợ |
| ECN signaling | TCP flags và IP bits | Khả năng sử dụng ECN theo thỏa thuận | Congestion đang xảy ra ngay lúc bắt tay |

## 8. Capture ở đâu? Chọn điểm quan sát trước khi chọn filter

Capture ở client, firewall, SPAN port, host server hoặc proxy có thể cho **những bức tranh khác nhau của cùng một request**:

~~~mermaid
flowchart LR
    C["Client host"] --> R["Router / VPN"]
    R --> FW["Stateful firewall / NAT"]
    FW --> LB["Load balancer / proxy"]
    LB --> S["Backend server"]
    PC["Capture C"] -. "Packet trước NAT" .-> C
    PF["Capture F"] -. "Ngoài/trong firewall" .-> FW
    PL["Capture L"] -. "Frontend hoặc upstream proxy" .-> LB
    PS["Capture S"] -. "Packet mà server host nhận" .-> S
~~~

### 8.1. Câu hỏi cần trả lời trước khi thu

1. **Ai là client thật và server thật theo giao thức tại điểm đang đo?** Proxy có thể trở thành client mới tới backend.
2. Capture **interface nào**, trước hay sau NAT, trong namespace/Pod hay node host?
3. Có thấy **cả hai hướng** của một flow không? Có asymmetric routing/ECMP?
4. Có VPN/overlay/encapsulation khiến packet quan sát là **outer tunnel** thay vì inner TCP?
5. Có **NIC offload, GRO/LRO/TSO/GSO, checksum offload** làm packet hiển thị khác on-wire?
6. Clock của hai thiết bị có được đồng bộ đủ để so timestamps?
7. Có **snaplen, capture drops, sampling, port mirror oversubscription**?
8. Dữ liệu có chứa thông tin cá nhân hoặc bí mật cần che không?

### 8.2. SPAN/mirror chưa chắc thu toàn bộ gói

Switch SPAN hoặc cloud traffic mirroring có thể bị giới hạn capacity, thiếu packet do oversubscription, sampling hoặc drop khi buffer đầy. Thiết bị có thể mirror **một hướng**, không giữ original link-layer headers hoặc tạo duplicate. Không suy “server không gửi SYN/ACK” chỉ vì capture mirror không thấy nó.

### 8.3. Asymmetric routing

Trong routing bất đối xứng, **SYN client→server** đi qua firewall A nhưng **SYN/ACK server→client** đi qua firewall B. Capture trên A có thể chỉ thấy một chiều. Một stateful firewall không có shared session state có thể chặn return traffic, nhưng cần xác nhận **effective routes, firewall rules/logs và flow directions**; chỉ một chiều pcap không đủ chứng minh.

### 8.4. NAT và 5-tuple translation

Ví dụ SNAT có thể biến:

~~~text
Before SNAT:
  192.0.2.10:51514 -> 198.51.100.20:443

After SNAT (illustrative):
  203.0.113.10:62001 -> 198.51.100.20:443

Return packet observed at server:
  198.51.100.20:443 -> 203.0.113.10:62001
~~~

Để ghép hai pcaps ở hai bên NAT, dùng **NAT translation/session table logs với timestamp** và sequence/ack progression; không chỉ grep theo client IP gốc. Khi proxy **terminate và tạo TCP connection mới**, ISNs, ports, timings có thể hoàn toàn khác, nên không ghép hai legs như một handshake duy nhất.

## 9. Chuẩn bị thu gói bằng tcpdump một cách an toàn

`tcpdump` dùng **capture filters** thường theo ngữ pháp Berkeley Packet Filter (BPF); filter quyết định gói nào được nhận/ghi ở quá trình capture, không phải Wireshark display filter.

### 9.1. Xác nhận đúng interface và mục tiêu

~~~bash
# Chỉ đọc trên Linux host được cho phép.
ip -br address
ip route get 198.51.100.20

# Liệt kê interfaces để chọn đúng capture device;
# thao tác xem interface có thể cần quyền tùy OS.
tcpdump -D
~~~

Lệnh `ip route get` có thể hiển thị route/source IP dự kiến trên host đó nhưng không tự chứng minh **firewall/return path**. Dùng endpoint thực thuộc lab khi làm phép thử; IP trong ví dụ là địa chỉ dành cho tài liệu.

### 9.2. Filter giới hạn đúng một kết nối TCP thử nghiệm

~~~bash
# Trên host có quyền capture; thay IP/port/interface theo lab.
# -nn: không phân giải tên; -i: interface; -s 96: capture 96 bytes/gói;
# -c 20: giới hạn số packets để lệnh tự kết thúc; -w: ghi pcap.
sudo tcpdump -i eth0 -nn -s 96 -c 20 \
  -w /tmp/tcp-handshake-lab.pcap \
  'tcp and host 198.51.100.20 and port 443'
~~~

**Đây là lệnh THU gói**, không phải lệnh chỉ đọc thụ động tuyệt đối: nó tạo file và truy cập packet data. Chỉ chạy khi có quyền trên interface/traffic đó. `-s 96` giảm lượng payload ghi nhưng **không bảo đảm loại bỏ toàn bộ payload hoặc metadata nhạy cảm**; TCP headers với nhiều options có thể dài và một phần application data vẫn lọt vào. Nếu phân tích TLS hoặc đầy đủ options, có thể cần snaplen lớn hơn, đi kèm chính sách xử lý dữ liệu chặt hơn.

Không mặc định `/tmp` là nơi lưu forensics an toàn. Khi xử lý incident thật, chọn thư mục hạn chế truy cập và encryption/retention theo chính sách; đường `/tmp/...` chỉ là ví dụ cho lab trên máy cá nhân được kiểm soát.

### 9.3. Đọc pcap đã thu mà không tiếp tục nghe traffic

~~~bash
# Chỉ đọc file pcap đã được cấp quyền.
tcpdump -nn -tttt -r /tmp/tcp-handshake-lab.pcap \
  'tcp and host 198.51.100.20 and port 443'
~~~

`-r` đọc pcap; việc phân tích file có thể lộ addresses/ports và payload nếu bật verbose/hex dump, nên không gửi output tùy tiện vào chat/ticket. `-tttt` hiển thị thời gian theo format của tcpdump/host, cần ghi **timezone** khi so logs từ nhiều nguồn.

### 9.4. Chỉ xem SYN-related packets với BPF

~~~bash
# SYN bit đặt: gồm SYN và SYN/ACK.
sudo tcpdump -i eth0 -nn -c 30 \
  'tcp and host 198.51.100.20 and (tcp[13] & 2 != 0)'

# Chỉ SYN có SYN=1, ACK=0; không tính SYN/ACK.
sudo tcpdump -i eth0 -nn -c 30 \
  'tcp and host 198.51.100.20 and (tcp[13] & 18 = 2)'
~~~

Trong TCP header, byte flags ở offset 13: SYN bit `0x02`, ACK bit `0x10`; mask `0x12` (18 thập phân) dùng để phân biệt **SYN không có ACK**. Đây là syntax cho BPF capture filter, **không phải Wireshark display filter**. Với encapsulation, IPv6 extension headers, offloads hoặc đường mạng đặc biệt, cấu trúc offsets/filter optimization cần được kiểm chứng trên interface thật; nên ưu tiên biểu thức BPF phổ biến và kiểm tra bằng capture sample.

### 9.5. Không chỉ capture SYN nếu mục tiêu là chứng minh handshake hoàn tất

Một filter chỉ giữ SYN/SYNACK sẽ **bỏ ACK cuối** (ACK thuần không có SYN bit), làm người phân tích tưởng thiếu gói thứ ba. Khi cần chứng minh ba bước, filter theo **host/port/5-tuple** để thu cả các gói response, hoặc capture rộng hơn trong phạm vi được cấp quyền rồi lọc display lúc phân tích.

### 9.6. Chỉ số gói mất ở chính tcpdump

Khi kết thúc `tcpdump`, tool thường báo số packet captured, received by filter và dropped by kernel (theo khả năng nền tảng). **Capture drops ≠ network packet drops**. Nếu capture process bị mất gói do thiếu buffer/CPU, pcap có thể thiếu ACK/SYNACK dù mạng vẫn truyền chúng. Một số nền tảng không báo đủ các bộ đếm nên giá trị 0 cũng phải hiểu theo implementation.

## 10. Wireshark: tìm một TCP stream và xem SYN/ACK trực quan

**Wireshark** cho phép xem từng frame, phân rã headers, theo dõi một TCP stream và hiển thị **Expert Information**. Để phân tích pcap an toàn, mở **file được cấp phép**; tránh bật live capture trên interface không được phép.

### 10.1. Các display filters hữu ích

~~~wireshark
# Chỉ những frame được dissect như TCP.
tcp

# SYN bit set (gồm cả SYN/ACK):
tcp.flags.syn == 1

# SYN đầu tiên (SYN=1 và ACK=0):
tcp.flags.syn == 1 && tcp.flags.ack == 0

# SYN/ACK:
tcp.flags.syn == 1 && tcp.flags.ack == 1

# RST:
tcp.flags.reset == 1

# Một TCP stream được Wireshark gán trong file:
tcp.stream == 3

# Một địa chỉ nguồn/đích IPv4:
ip.addr == 198.51.100.20 && tcp.port == 443
~~~

Những filter trên là **Wireshark display filter syntax** và được trình bày để sử dụng **từng biểu thức một**, không phải một file script có thể nạp nguyên khối. `tcp.stream` là **index cục bộ của analyzer trong file/phiên**, không phải một identifier toàn mạng và có thể thay khi file bị lọc/trộn/sắp thứ tự khác.

### 10.2. Các bước phân tích ba gói

1. Mở pcap đã được phép thu và chọn packet có `tcp.flags.syn == 1 && tcp.flags.ack == 0`.
2. Kiểm tra **Ethernet/IP source-destination, source/destination ports** và timestamp.
3. Chuột phải **Follow → TCP Stream** hoặc dùng `tcp.stream == N` để thu đúng kết nối trong file.
4. Trong **Transmission Control Protocol**, xem flags, raw/relative Seq, Ack, `TCP Len`, Window và options.
5. Tìm SYN/ACK ngược chiều, đối chiếu Ack với `client ISN + 1`.
6. Tìm ACK tiếp theo từ client, đối chiếu Ack với `server ISN + 1`.
7. Xem dữ liệu ứng dụng bắt đầu khi nào, có RST/retransmission hay không; chú ý capture point và time.
8. Nếu mất một gói, xem **Expert Info, TCP analysis flags và capture statistics** như gợi ý, không xem chúng là verdict tuyệt đối.

### 10.3. Các trường hiển thị và tầng dữ liệu

| Wireshark field/khái niệm | Dùng để đọc | Giới hạn |
|---|---|---|
| `tcp.flags.syn` / `.ack` | Gói SYN và SYN/ACK | Flags chỉ biểu diễn một segment |
| `tcp.seq` / `tcp.ack` | Seq/Ack theo thiết lập relative display | Có thể khác raw header values |
| `tcp.seq_raw` / `tcp.ack_raw` | Raw 32-bit values khi field có trong phiên bản | Cần xác nhận field availability theo version |
| `tcp.len` | TCP segment payload data length | Không bằng frame length; offload/capture snaplen ảnh hưởng |
| `tcp.options.mss_val` | MSS option nếu có | Không phải MTU toàn path |
| `tcp.options.wscale.shift` | Window scale option theo dissector | Không luôn có nếu bắt giữa phiên |
| `tcp.analysis.retransmission` | Analyzer đánh dấu retransmission | Heuristic có thể sai khi capture thiếu gói |
| `tcp.analysis.duplicate_ack` | Analyzer đánh dấu duplicate ACK | Không phải bằng chứng độc lập về lỗi đường truyền |
| `frame.time_relative` | Thời gian tương đối từ đầu capture | Không phải RTT của flow |
| `tcp.stream` | Nhóm packets vào một stream | Index chỉ có nghĩa trong file/analyzer |

### 10.4. Follow TCP Stream có thể thấy plaintext

Tính năng **Follow TCP Stream** có thể tái dựng application bytes. Với SSH/TLS, payload thường mã hóa sau handshake bảo mật; nhưng **SNI, certificate metadata và endpoint addresses** vẫn có thể lộ tùy protocol, trong khi HTTP plaintext/legacy protocols có thể chứa **cookies, credentials, tokens**. Chỉ mở/chia sẻ khi cần thiết và áp dụng chính sách bảo vệ dữ liệu.

## 11. tshark: trích xuất handshake từ pcap bằng dòng lệnh

`tshark` là công cụ dòng lệnh của hệ sinh thái Wireshark, dùng dissector/display filters phù hợp. Nó hữu ích khi cần **tổng hợp trường TCP theo bảng** mà không mở UI.

### 11.1. Chỉ hiển thị TCP SYN/SYNACK trong pcap

~~~bash
# Đọc file đã thu, không mở live capture.
tshark -r /tmp/tcp-handshake-lab.pcap \
  -Y 'tcp.flags.syn == 1' \
  -T fields \
  -e frame.number \
  -e frame.time_epoch \
  -e ip.src \
  -e tcp.srcport \
  -e ip.dst \
  -e tcp.dstport \
  -e tcp.flags \
  -e tcp.seq \
  -e tcp.ack
~~~

`-r` đọc pcap, `-Y` lọc **để hiển thị**, `-T fields` xuất các trường được chọn. Nếu file chứa IPv6 packets, hãy dùng thêm **`ipv6.src`, `ipv6.dst`** hoặc xử lý cả hai kiểu địa chỉ. Nếu cần so raw values, chọn trường raw được hỗ trợ như `tcp.seq_raw` và `tcp.ack_raw` với phiên bản TShark tương ứng.

### 11.2. Lọc đầy đủ một stream

~~~bash
# Số stream 3 là ví dụ, phải lấy từ pcap đang phân tích.
tshark -r /tmp/tcp-handshake-lab.pcap \
  -Y 'tcp.stream == 3' \
  -T fields \
  -e frame.number \
  -e frame.time_relative \
  -e ip.src \
  -e ip.dst \
  -e tcp.flags.str \
  -e tcp.seq \
  -e tcp.ack \
  -e tcp.len
~~~

Tùy phiên bản dissector, `tcp.flags.str` có thể không có hoặc trả khác format. Khi field không tồn tại, xem danh sách fields của **phiên bản đang dùng** và thay bằng `tcp.flags` hoặc các boolean flags. Không phụ thuộc tên trường chưa xác minh để viết parser sản xuất.

### 11.3. Phân biệt capture filter và display filter

| Nhiệm vụ | tcpdump/libpcap BPF | Wireshark/tshark display |
|---|---|---|
| Chỉ TCP đến host | `tcp and host 198.51.100.20` | `tcp && ip.addr == 198.51.100.20` |
| SYN đầu tiên | `tcp[13] & 18 = 2` trong biểu thức phù hợp | `tcp.flags.syn == 1 && tcp.flags.ack == 0` |
| SYN/ACK | Bitmask với SYN+ACK | `tcp.flags.syn == 1 && tcp.flags.ack == 1` |
| TCP stream index | Không có chỉ số stream cục bộ của dissector | `tcp.stream == N` |
| TCP retransmission heuristic | Không thể quyết định chỉ từ BPF tĩnh | `tcp.analysis.retransmission` nếu analyzer đánh dấu |

**BPF** chạy ở đường thu để giảm lượng packets được ghi. **Display filter** áp sau khi packets đã capture, có thể sử dụng **stateful/analyzer-derived fields** như stream index và retransmission heuristic. Khi đã capture chỉ SYN bằng BPF, không thể dùng display filter để “khôi phục” ACK cuối bị loại khỏi pcap.

### 11.4. Xuất kết quả có kiểm soát

Khi cần đính kèm một bảng tóm tắt cho ticket, chỉ đưa **frame number, relative time, anonymized endpoints/ports, flags, seq/ack, TCP options cần thiết và kết luận có mức tin cậy**. Không xuất mọi payload, DNS user info hoặc session tokens. Nếu cần bảo toàn bản gốc, lưu checksum/file metadata theo quy trình forensic có thẩm quyền; **không sửa pcap gốc rồi coi đó vẫn là raw evidence**.

## 12. Đo thời gian TCP handshake và giới hạn khi suy RTT

Ba packets trong capture có timestamps:

~~~text
Frame 1: t1=12:00:00.000  Client -> Server  SYN
Frame 2: t2=12:00:00.025  Server -> Client  SYN/ACK
Frame 3: t3=12:00:00.026  Client -> Server  ACK
~~~

Nếu capture được thực hiện trên **client host**, một ước lượng quan sát là:

\[
\Delta t_{\mathrm{SYN\rightarrow SYNACK}}=t_2-t_1=25\ \mathrm{ms}.
\]

Nó thường gần một **handshake round trip** từ điểm client đến server rồi quay lại, cộng processing/queueing ở các hops và capture timestamp behavior. **Không mặc định đây là RTT thuần của đường truyền**: server có thể trì hoãn trả SYN/ACK, SYN/ACK có thể đến từ proxy/SYN proxy, và packet timestamping có độ lệch.

### 12.1. Còn ACK cuối?

Ở client, \(t_3-t_2=1\) ms chủ yếu phản ánh xử lý lập tức của client/capture path, không phải đường mạng. Khoảng \(t_3-t_1=26\) ms cũng không chứng minh ACK cuối đã tới server. Muốn biết **thời gian server nhận ACK**, cần quan sát/telemetry phía server và đồng bộ đồng hồ hoặc dùng đo riêng tại server.

### 12.2. Nếu capture ở server

Một capture ở server có thể đo từ **khi nhận SYN** đến **khi nhận ACK cuối**, chứa thời gian server gửi SYN/ACK và round-trip của response qua client, thay vì cùng định nghĩa với \(t_2-t_1\) ở client. Tránh so hai giá trị từ hai vantage như cùng một metric latency mà chưa mô tả mốc.

### 12.3. Phân tách DNS, TCP, TLS, application latency

~~~text
Client application timer
| DNS | TCP SYN/SYNACK/ACK | TLS handshake | HTTP request/response |

tcpdump:
  thấy TCP flags và có thể TLS records/metadata

curl timing:
  thấy các elapsed milestones theo cách curl đo

application trace:
  thấy backend handler/dependency spans
~~~

**TCP handshake latency chỉ là một thành phần**, và chỉ diễn ra khi tạo kết nối mới. Với HTTP keep-alive/HTTP2 multiplexing, nhiều requests dùng một connection; với HTTP/3, QUIC không dùng TCP handshake. Nếu connection pooling đã có, so “request total time” với TCP SYN latency trên một connection cũ có thể sai đối tượng.

### 12.4. Retransmission làm thời gian tăng thế nào?

~~~text
t0      SYN #1
t0+RTO  SYN retransmission #2 (nếu timer/logic TCP phát lại)
t0+...  SYN/ACK nhận được
t0+...  ACK hoàn tất
~~~

Nếu packet đầu tiên bị mất, SYN được gửi lại theo cơ chế retransmission timeout và backoff của TCP stack. Các khoảng retry **không nhất thiết cố định hoặc giống mọi OS**. Nếu capture bắt đầu giữa quá trình, segment đầu tiên thấy được có thể đã là retransmission. Không suy nguyên nhân từ chênh thời gian mà thiếu capture completeness và endpoint telemetry.

### 12.5. Đo độ trễ trên hai capture points

Muốn chứng minh packet bị giữ lại ở firewall/IPS, thu **hai phía thiết bị** với:

- Same TCP flow mapping (NAT translation nếu có).
- Timestamping/clock sync có độ chính xác đủ cho phép đo yêu cầu.
- Packet signatures: ports, sequence, options, IP ID khi phù hợp, payload hash theo quyền.
- Packet capture drop statistics.
- Evidence của thiết bị: queue, policy, CPU, session state.

Khi clocks không đồng bộ, so thời điểm tuyệt đối có thể tạo **latency âm** hoặc lớn giả. Chỉ có hai pcap chưa đồng bộ không thể tính một-way delay đáng tin.

## 13. Các mẫu lỗi handshake quan sát được

Không có một “bản đồ lỗi” hoàn hảo từ packet flags: một firewall có thể chủ động reject hoặc âm thầm drop; client có thể dừng retry; server có thể gửi RST; một proxy có thể trả SYN/ACK dù backend thất bại. Dưới đây là các **mẫu thường gặp**, không phải kết luận bắt buộc.

### 13.1. Chỉ có SYN lặp, không thấy SYN/ACK

~~~text
Client -> Server  SYN seq=1000
Client -> Server  SYN seq=1000   (sau một khoảng chờ)
Client -> Server  SYN seq=1000   (sau khoảng chờ tiếp)
... client connect timeout
~~~

**Giả thuyết:** SYN outbound bị drop, return SYN/ACK bị drop, server không nhận hoặc không trả, capture chỉ có một chiều, NAT state/route lỗi, host/network unreachable hoặc SYN backlog pressure. Một pcap ở client **không xác định được hop gây mất**. Cần capture ở phía server/thiết bị trung gian, firewall logs và route evidence.

### 13.2. SYN → RST,ACK

~~~text
Client -> Server  SYN seq=1000
Server -> Client  RST,ACK ack=1001
~~~

**Giả thuyết:** không có process listen trên port, TCP stack từ chối yêu cầu, policy/firewall active reject hoặc một middlebox giả lập RST. **Một RST có source IP của server không chứng minh chính application server đã tạo**; NAT, firewalls và proxies có thể phản hồi thay.

### 13.3. SYN → ICMP unreachable / administratively prohibited

~~~text
Client -> Server  TCP SYN
Router/firewall -> Client  ICMP destination unreachable (type/code tùy IPv4/IPv6)
~~~

Đây có thể là reject do route, firewall ACL hoặc network control. Cần đọc **ICMP type/code, IP header được quote và router source** theo protocol. **Không tự kết luận mọi ICMP unreachable đều do firewall policy**, và không xem thiếu ICMP là chứng minh bị DROP (ICMP có thể bị rate-limit/chặn).

### 13.4. SYN/ACK thấy ở server, không thấy ở client

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Return-path device
    participant S as Server
    C->>F: SYN
    F->>S: SYN
    S-->>F: SYN/ACK
    Note over F,C: Return path/ACL/NAT/routing cần xác minh
    C->>C: Timeout / SYN retransmission
~~~

Nếu capture tại server thấy đã **phát SYN/ACK**, còn client không thấy nó **tới host**, ưu tiên kiểm tra **return route, policy state, NAT, tunnel/MTU, packet capture completeness và middleboxes**. Chỉ kết luận thiết bị nào drop khi có log/packet evidence tại đúng hop.

### 13.5. Client thấy SYN/ACK và ACK, server cứ gửi lại SYN/ACK

Gợi ý **ACK cuối không tới hoặc không được chấp nhận ở server**, hoặc các captures không cùng flow/đường/clock. Đối chiếu client ACK với server ISN, NAT translated tuple, stateful firewall route và ACK capture ở server trước khi quy trách nhiệm.

### 13.6. Handshake xong nhưng RST ngay sau đó

~~~text
SYN -> SYN/ACK -> ACK -> TLS ClientHello / application bytes -> RST
~~~

Lỗi có thể nằm ở **ứng dụng, TLS policy, proxy reset, idle/session rule hoặc dịch vụ upstream**, không phải nhất thiết ở TCP 3-way handshake. Kiểm tra ai phát RST, thứ tự/ack, payload length, proxy logs, server application logs và vị trí TLS termination. Một RST sau app data cũng có thể do timeout/abort từ peer.

### 13.7. SYN/ACK retransmission không đồng nghĩa SYN flood

Server có thể gửi lại SYN/ACK vì ACK bị mất trên đường, client không còn sống, bị drop bởi return path hoặc server quá tải. Phải xem **source distribution, rate per second, unique tuples, backlog, syn cookies counters và trải nghiệm client hợp lệ** mới đánh giá nghi ngờ SYN flood.

### 13.8. Bảng so sánh biểu hiện

| Pattern ở vantage đã nêu | Điểm cần xác minh | Không kết luận ngay |
|---|---|---|
| Client thấy SYN lặp | Outbound/return path, server listener, capture scope | Firewall chắc chắn drop SYN |
| Client thấy RST ngay | RST origin, port listener, reject policy | Server có lỗ hổng |
| Server thấy SYN, không gửi SYN/ACK | Host policy, TCP stack, backlog, interface drops | Network chắc chắn chặn return |
| Server gửi SYN/ACK, client không nhận | Reverse path, NAT, stateful firewall, SPAN completeness | Server ứng dụng lỗi |
| Client gửi ACK, server vẫn SYN/ACK retry | ACK path, tuple, server state, capture gaps | Client đã established ở cả hai phía |
| SYNs tăng, completed handshakes giảm | Load/backlog, source distribution, bot/attack evidence | Chắc chắn tấn công |
| Three-way hoàn tất, TLS fail | Certificate/SNI/trust/handshake/inspection | TCP handshake lỗi |
| TCP OK, HTTP 503 | Backend/ingress/upstream/application health | Kết nối IP bị chặn |

## 14. Firewall, IDS/IPS, NetworkPolicy và TCP state

Trong mô hình **stateful firewall**, quyết định với SYN mới có thể tạo state cho return packets, sau đó `SYN/ACK` và `ACK` phải phù hợp với flow/state theo chính sách và implementation. **Không phải mọi firewall đều theo dõi TCP state giống nhau**: có TCP sequence validation, SYN proxy, loose/asymmetric mode, conntrack, offload, timeout và reset action khác nhau.

### 14.1. NetworkPolicy ở Kubernetes

Một `NetworkPolicy` L3/L4 có thể cho Pod A kết nối tới Pod B theo selector/port và chặn nguồn khác, nếu **CNI thực sự hỗ trợ enforce**. Packet capture từ Pod A thấy SYN phát ra nhưng không có SYN/ACK chưa chứng minh CNI drop; cần **positive control cùng destination, CNI flow logs/metrics và kiểm tra cả egress lẫn ingress**.

NetworkPolicy cũng **không cung cấp xác thực danh tính ứng dụng/người dùng**; nguồn đã được phép có thể cần mTLS/JWT và app authorization. Nếu security policy yêu cầu chặn traffic, packet drop có thể là **kết quả đúng**, không tự tính như sự cố availability cho các callers không được phép.

### 14.2. TCP RST do firewall tạo

Một firewall có thể chủ động từ chối kết nối bằng TCP RST thay vì silent drop. Trong pcap, RST có thể trông như xuất phát từ server vì thiết bị tạo packet với các địa chỉ theo flow; cần xem **firewall action logs, packet TTL/hop-limit, timing, options, captures hai phía**, nhưng đừng xem TTL differences là bằng chứng quyết định duy nhất.

### 14.3. SYN proxy và SYN cookies

Một thiết bị **SYN proxy** có thể trả SYN/ACK cho client **trước khi backend server nhận một handshake tương ứng**. Vì vậy capture ở client thấy kết nối tới “server IP” có SYN/ACK **không chứng minh backend đã sẵn sàng**. SYN cookies ở TCP stack cũng có thể giảm nhu cầu giữ state cho các SYN chưa hoàn tất khi chịu tải theo implementation. Cần phân biệt **SYN proxy ở middlebox** với **SYN cookies ở endpoint**, và không suy hình thức triển khai từ duy nhất TCP flags.

### 14.4. TCP segmentation và IDS/IPS

Inline IDS/IPS có thể kiểm tra stateful TCP reassembly, policy theo source/destination và signature. Một thiết bị cấu hình chặt có thể chặn segment có flags/sequence bất thường hoặc làm reset kết nối, trong khi passive IDS chỉ ghi alert. Khi điều tra:

- Xác định IDS **inline hay out-of-band**, action block/drop/reset thực tế.
- Đối chiếu policy ID, source identity, pcap trước/sau thiết bị.
- Xem normalization, retransmission và TCP options làm analyzer khó hiểu không.
- Giữ **traffic hợp lệ** làm positive control và **traffic bị cấm** làm negative control.
- Không tắt inspection hoặc cho phép mọi source để “sửa nhanh” một timeout.

### 14.5. Nguy cơ false positives

Một firewall policy được thay có thể từ chối SYN hợp lệ trước khi tới backend. Backend metrics sẽ **không ghi lỗi HTTP** vì request chưa tới được ứng dụng. Monitoring phải gồm **synthetic TCP/TLS/HTTPS từ nguồn có quyền, firewall deny logs và network drops**, không chỉ server 5xx.

## 15. Offloads, checksum và các hiện tượng “gói ảo” trong capture

Khi capture ngay trên host, phần mềm có thể quan sát packet **trước hoặc sau những công việc mà NIC phần cứng thực hiện**. Vì thế pcap tại host không luôn phản ánh chính xác các Ethernet frames đã xuất hiện trên dây.

### 15.1. Checksum offload

Một TCP segment outgoing có thể được capture **trước khi NIC điền TCP checksum thực**. Wireshark có thể hiển thị `incorrect checksum` dù packet truyền ra mạng có checksum hợp lệ, vì NIC tính checksum ở bước sau.

**Không kết luận mạng bị hỏng checksum chỉ từ một capture trên source host có checksum offload.** Đối chiếu vị trí capture, NIC offload capabilities, capture ở phía nhận hoặc network tap/SPAN và receiver counters. Nếu có checksum error thật tại nhận, cần xác minh sự kiện bằng đúng interface/driver và packet evidence.

### 15.2. GRO/LRO/GSO/TSO

| Cơ chế | Nguyên lý tóm tắt | Ảnh hưởng khi đọc pcap |
|---|---|---|
| **TSO** (TCP Segmentation Offload) | NIC chia một buffer lớn thành nhiều TCP segments để gửi | Source capture có thể thấy gói TCP “khổng lồ” chưa chia |
| **GSO** (Generic Segmentation Offload) | Hỗ trợ segmentation trong network stack | Packet được capture có kích thước khác on-wire |
| **GRO** (Generic Receive Offload) | Gộp các packets nhận để xử lý hiệu quả hơn | Host capture có thể thấy payload được gộp |
| **LRO** (Large Receive Offload) | NIC/driver gộp một số TCP segments | Packet count/size có thể khác wire packets |
| **Checksum offload** | NIC tính/kiểm tra checksum | Có thể báo checksum chưa tính hoặc được xác thực ở phần cứng |

Các cơ chế này thường **không làm thay đổi logic ba cờ SYN/SYNACK/ACK** nhưng có thể làm lẫn lộn phân tích payload, segmentation, checksum và RTT/packet counts. Một số triển khai có offload khác, tùy NIC/OS/driver. Chỉ điều chỉnh/tắt offload trên **lab có quyền** và có rollback; không tắt offload production chỉ để packet trace “đẹp”.

### 15.3. VLAN tags và encapsulation

VLAN tagging có thể được NIC strip/insert offload, nên capture ở host có thể không hiển thị tag như trên switch. Với **VXLAN, Geneve, GRE, WireGuard/IPsec hoặc cloud overlays**, người quan sát tại outer interface có thể thấy **outer IP/UDP headers** thay vì inner TCP handshake. Việc chọn filter `tcp and port 443` trên outer interface có thể không match nếu TCP được bọc trong tunnel.

Để phân tích inner handshake, capture ở **đúng virtual interface/namespace hoặc giải mã/decapsulate theo quyền và khả năng công cụ**, không tự suy từ việc filter không thấy TCP.

### 15.4. NIC and capture loss khác network loss

Một capture bị thiếu các frames do kernel drop, BPF filter sai, snaplen quá ngắn hoặc port mirror quá tải. Để kết luận **packet loss thật**:

1. Kiểm tra capture loss counters và collector health.
2. Đối chiếu source/receiver packet capture cùng flow nếu có.
3. Kiểm tra counters của thiết bị trung gian/host NIC.
4. Đối chiếu TCP retransmission/ACK progression.
5. Ghi rõ **vị trí mất lần đầu được chứng minh** và độ chắc chắn.

Một retransmission marker do Wireshark suy ra chỉ là **dấu hiệu phân tích dựa vào packets có trong file**; khi capture thiếu phần đầu của flow, heuristic có thể đánh dấu sai. Tránh dùng marker đơn lẻ như một phán quyết forensic.

## 16. NAT, load balancer, proxy, VPN và TLS termination

Một yêu cầu HTTPS trong cloud/container network có thể tạo **nhiều kết nối TCP độc lập**:

~~~mermaid
flowchart LR
    C["Browser / client"] <-->|"TCP connection #1"| CDN["CDN / external LB"]
    CDN <-->|"TCP connection #2"| ING["Ingress proxy"]
    ING <-->|"TCP connection #3"| API["Backend API"]
    API <-->|"TCP connection #4"| DB["Database"]
~~~

Các kết nối có thể dùng TCP khác nhau về **source/destination ports, ISNs, RTT, TCP options, MSS, congestion state và TLS termination**. Khi reverse proxy kết thúc client TCP connection và mở upstream connection mới, **không so thẳng sequence numbers qua hai legs** như cùng một flow.

### 16.1. L4 passthrough so với TCP termination

- **L4 load balancer giữ end-to-end TCP semantics** trong một số thiết kế sẽ forward packets/NAT tới backend; seq/ack progression có thể giữ tính liên tục qua translation.
- **Full proxy** kết thúc TCP ở proxy và chủ động mở connection mới tới backend; hai handshakes khác nhau.
- **SYN proxy** có thể trả SYN/ACK thay backend để kiểm tra client trước khi chuyển tiếp hoặc thiết lập kết nối về backend.
- **Service mesh sidecar/waypoint** có thể tạo những connections bảo vệ bằng mTLS giữa proxies và local app hops, tùy topology.

Không suy loại LB/mesh chỉ từ tên dịch vụ hoặc annotation. Cần **data plane config** và captures hai bên để xác định đâu là TCP termination point.

### 16.2. Client handshake success không chứng minh backend success

Một client có thể bắt tay thành công với CDN hoặc gateway, rồi bị HTTP 502/503 vì backend unreachable. Nếu chỉ thu phía client, ta thấy một TCP 3-way handshake **đẹp hoàn toàn** nhưng request vẫn thất bại. Cần backend health, upstream connection metrics, proxy logs và nếu được phép **capture upstream leg**.

### 16.3. VPN và tunnel encapsulation

Với IPsec/WireGuard hoặc VPN tunnel:

~~~text
Inner TCP:
  Client private IP:51514 -> Service private IP:443, SYN

Outer tunnel packet:
  VPN endpoint A -> VPN endpoint B, encrypted encapsulation
~~~

Ở outer network capture, inner TCP SYN có thể **không nhìn thấy** vì được mã hóa/encapsulate. Kiểm tra handshake tại **client pre-tunnel, tunnel interface (nếu hệ thống hỗ trợ), hoặc server sau decapsulation** với quyền phù hợp. Với VPN đang lên nhưng dịch vụ không tới được, cần phân biệt **tunnel establishment** và **inner TCP connection**.

### 16.4. MTU và MSS khi có overlay

Nếu tunnel overhead làm effective MTU nhỏ, **SYN/SYNACK/ACK nhỏ có thể thành công** trong khi TLS certificate chain hoặc HTTP response lớn bị mất/trễ vì PMTUD/fragmentation. Đây là lý do **không kết luận application path healthy chỉ từ ba gói TCP handshake**. Kiểm tra segment size, MSS clamping, ICMP Packet Too Big, IPv4/IPv6 behavior và TLS/data packets sau handshake.

### 16.5. Capture khi có NAT hairpin và dual stack

Trong NAT hairpin, client và server cùng nội bộ có thể đi qua NAT address rồi quay lại. Với IPv4/IPv6 dual stack, client có thể thử **nhiều connection attempts tới A/AAAA khác nhau** (Happy Eyeballs hoặc client-specific selection). Một attempt IPv6 fail và IPv4 succeed có thể làm người dùng vẫn truy cập được nhưng delay tăng; cần phân nhóm **cả hai attempts**, không chỉ flow đã thành công.

### 16.6. TLS không che TCP flags

Với TLS-over-TCP thông thường, TCP/IP header và SYN flags vẫn có thể quan sát trên đường mạng, trong khi application payload sau khi TLS thiết lập được mã hóa. **TCP-level metadata** như IPs, ports, flags, sizes, timing có thể là thông tin nhạy cảm; không coi TLS encryption là cho phép chia sẻ pcap không kiểm soát.

## 17. SYN flood, backlog và phân tích bảo mật dựa trên handshake

SYN flood là một dạng **denial-of-service** nhằm làm tăng tải/state hoặc xử lý handshake ở server/middlebox, thường liên quan lượng lớn SYN và những kết nối không hoàn tất. Nhưng **nhiều SYN không tự chứng minh có tấn công**: có thể là legitimate flash crowd, kết nối ngắn, client failures, retries hoặc SYN proxy.

### 17.1. Các số liệu nên quan sát

| Metric/evidence | Cách dùng | Giới hạn |
|---|---|---|
| SYN packets/s | Xu hướng attempt mới ở điểm đo | Retransmission có thể đếm cùng attempt nhiều lần |
| SYN/ACK responses/s | Server/PEP phản hồi attempt | Thiếu response trong một capture không chứng minh không phát |
| Established/accepted connections/s | Khả năng hoàn tất kết nối | Phụ thuộc server kernel/app logs |
| SYN-RECEIVED/backlog occupancy | Số trạng thái chờ ACK ở triển khai cụ thể | SYN cookies có thể làm cách đếm khác |
| SYN retransmission rate | Path failures/overload signals | Không phân biệt loss với attack một mình |
| Source IP/AS distribution | Patterns, concentration, spoofing clues | Source IP có thể NAT, spoof hoặc là proxy |
| CPU/conntrack/memory/pps | Capacity pressure của host và firewall | Link bandwidth thấp vẫn có thể bão hòa pps |
| Legitimate connection success/latency | Tác động với người dùng thật | Cần synthetic from trusted locations |
| SYN cookies activation counters | Gợi ý host dùng bảo vệ khi backlog pressure | Phụ thuộc OS/config/counters và không tự xác nhận attack |

### 17.2. SYN cookies là gì ở mức ý niệm?

Một TCP stack có thể sử dụng **SYN cookies** như biện pháp giảm việc giữ per-connection state khi nhận SYN dưới áp lực phù hợp. Một số thông tin trạng thái được mã hóa trong giá trị SYN/ACK sequence number, và server kiểm tra ACK sau. Vì **không giữ trạng thái thông thường cho mỗi half-open request** trong giai đoạn đó, một số TCP options/capabilities có thể bị giới hạn hoặc phụ thuộc implementation.

**Không dùng ISN pattern trong một pcap để khẳng định chắc chắn host đang dùng SYN cookies**, vì selection ISN và encoding khác theo stack. Dùng **kernel metrics, cấu hình, server logs và context**. Tương tự, bật SYN cookies không thay thế ingress rate limits, upstream capacity, firewall rules hay việc xử lý traffic hợp lệ.

### 17.3. SYN flood khác SYN scanning

| Dấu hiệu | SYN scan | SYN flood |
|---|---|---|
| Mục tiêu thông thường | Tìm dịch vụ/cổng đang mở | Làm suy giảm khả năng xử lý kết nối |
| Phân phối destination ports | Có thể nhiều ports | Thường một/một số services nhạy cảm |
| Rate/volume | Có thể thấp hoặc cao | Thường cao so baseline/capacity |
| Kết nối có hoàn tất? | Có thể chủ động không hoàn tất | Có thể không hoàn tất hoặc dùng nhiều attempts |
| Bằng chứng chính | Port coverage và pattern | Tác động backlog/pps/availability |

**Không có ngưỡng hoặc pattern hoàn hảo** để tự phân loại. Một công cụ quản trị/monitoring cũng có thể tạo SYN attempts; phải xem authorized scans, change tickets và origin.

### 17.4. Điều tra mà không tái tạo tấn công

Không phát lưu lượng SYN flood để “kiểm thử chống DDoS” trên production. Trong môi trường được phép, có thể:

1. Phân tích **pcap đã được thu hợp lệ** hoặc mô phỏng trace nhỏ.
2. Đếm SYN, SYN/ACK và ACK completion theo window.
3. Đối chiếu legitimate client SLI và kernel/firewall state metrics.
4. Kiểm tra **rate-limit/WAF/DoS protection events** và false positives.
5. Theo dõi trước/sau thay đổi chính sách bằng **canary requests có lưu lượng thấp**.

Kết luận “SYN flood” cần **bằng chứng tải bất thường và tác động**, không chỉ một hình ảnh có nhiều `[S]`.

### 17.5. An ninh và quyền riêng tư

Packet captures có thể là dữ liệu điều tra nhạy cảm vì chứa network topology, service identities, auth tokens hoặc nội dung chưa mã hóa. Việc bảo vệ dữ liệu là một phần của an ninh: thu đúng phạm vi/time window, phân quyền file, mã hóa khi lưu/chuyển, xóa theo retention, ghi chain of custody nếu liên quan forensic. **Không upload pcap nguyên gốc lên diễn đàn công khai để nhờ phân tích**.

## 18. Case study 1: SYN/ACK bị mất trên đường về qua firewall

### 18.1. Bối cảnh lab giả định

Một ứng dụng nội bộ kết nối database qua firewall stateful:

~~~text
Client 192.0.2.10:51514
  -> Router A
  -> Firewall F
  -> Database 198.51.100.20:5432

Symptom:
  Client báo connection timeout.
  Database process đang LISTEN.
  Host health và route ở client trông bình thường.
~~~

Ngay sau một thay đổi route/ACL, capture **phía client** có SYN lặp; capture **phía database** nhận được SYN và **phát SYN/ACK**. Đường về có thể đi qua **firewall khác** do asymmetric routing, hoặc state ở firewall không khớp NAT mapping.

### 18.2. Dữ liệu pcap minh họa

~~~text
CLIENT CAPTURE (example, relative timestamps)
0.000 192.0.2.10:51514 -> 198.51.100.20:5432 SYN   seq=9000
1.010 192.0.2.10:51514 -> 198.51.100.20:5432 SYN   seq=9000
3.030 192.0.2.10:51514 -> 198.51.100.20:5432 SYN   seq=9000

SERVER CAPTURE (independent clock; illustrative)
0.105 192.0.2.10:51514 -> 198.51.100.20:5432 SYN     seq=9000
0.106 198.51.100.20:5432 -> 192.0.2.10:51514 SYN,ACK seq=6000 ack=9001
1.115 192.0.2.10:51514 -> 198.51.100.20:5432 SYN     seq=9000
1.116 198.51.100.20:5432 -> 192.0.2.10:51514 SYN,ACK seq=6000 ack=9001
~~~

**Không so 0.105 ở server với 0.000 ở client để suy one-way delay** vì clocks chưa được xác nhận đồng bộ. Dữ liệu chỉ đủ khẳng định từng vantage **đã thu những packet nào**; chưa chứng minh firewall F là nơi drop.

### 18.3. Sơ đồ nghi vấn

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Firewall F
    participant S as Database
    C->>F: SYN
    F->>S: SYN
    S-->>F: SYN/ACK
    Note over F,C: SYN/ACK không xuất hiện trong client capture
    C->>F: SYN retransmission
    Note over F,S: Cần xem reverse path và session state
~~~

### 18.4. Những câu hỏi phải điều tra

| Câu hỏi | Nguồn bằng chứng | Vì sao quan trọng |
|---|---|---|
| Server thật sự đã phát SYN/ACK? | Server capture, TCP/kernel counters | Xác nhận không chỉ do listener application |
| Return traffic đi qua firewall nào? | Routing tables, traceroute hợp lệ, cloud routes | Asymmetric path có thể bypass state |
| Firewall có state cho SYN gốc? | Conntrack/session table, policy logs | Stateful return path cần state phù hợp |
| Có SNAT/DNAT trên flow? | Translation table và trước/sau captures | Return tuple có thể khác |
| Có block/deny log tương ứng? | Firewall rule ID, timestamp, flow | Xác định enforcement point cụ thể |
| Client capture có thiếu packet? | Capture counters, NIC/offload context | Tránh kết luận sai từ pcap |
| Có IPv6/alternate connection? | Client resolver/captures | Không ghép nhầm attempt khác |

### 18.5. Cách xử lý đúng

1. Xác nhận **client được phép** kết nối database và cổng đúng theo policy.
2. Kiểm tra **return route** và session/NAT state để tìm bất đối xứng.
3. Có thể thu một **capture ngắn tại hai phía firewall** trong lab, có scope/time/authorization.
4. Sửa route/stateful firewall design theo change control; không mở mọi TCP source hoặc tắt inspection.
5. Sau sửa, kiểm thử **SYN → SYN/ACK → ACK** từ client có quyền và **SQL authentication riêng** nếu cần.
6. Giữ **negative test**: một client không được phép vẫn bị firewall/NetworkPolicy từ chối.
7. Thu log/capture evidence sau sửa và giám sát TCP connect success, latency cùng firewall state.

### 18.6. Kết quả mong muốn, chưa chạy

~~~text
Authorized client:
  SYN reaches database: PASS
  SYN/ACK reaches client: PASS
  Final ACK reaches database: PASS
  TCP established according to both endpoints: PASS
  Database authentication/application response: verified separately

Unauthorized client:
  No access to database port by intended policy: PASS
  Enforcement decision logged: PASS

Status: PENDING controlled test
~~~

**Bài học:** “server phát SYN/ACK nhưng client timeout” thu hẹp điểm cần điều tra sang **return path, middleboxes và capture completeness**, nhưng **không đủ để xác định thủ phạm duy nhất** nếu thiếu bằng chứng ở các hop.

## 19. Case study 2: TCP handshake hoàn tất với proxy nhưng backend vẫn lỗi

### 19.1. Bối cảnh giả định

Một người dùng gọi `https://api.example.test`; giao diện API đi qua CDN rồi cloud load balancer/ingress có cơ chế **TCP termination**. Sau một thay đổi Kubernetes Service target port, một số backend upstream không còn accept TCP connect.

Client thấy:

~~~text
Client -> Public proxy: SYN
Proxy  -> Client: SYN/ACK
Client -> Proxy: ACK
Client -> Proxy: TLS ClientHello
Proxy  -> Client: TLS handshake response
Client -> Proxy: HTTPS GET
Proxy  -> Client: HTTP 503 (decrypted at client)
~~~

Người điều tra chỉ mở pcap phía client và thấy ba bước TCP thành công. Họ kết luận **“mạng hoàn toàn ổn”** rồi chuyển lỗi cho business logic. Kết luận đó quá rộng: client chỉ chứng minh đã thiết lập TCP với **public proxy**.

### 19.2. Upstream handshake riêng

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as CDN / Ingress Proxy
    participant S as Backend Pod
    C->>P: SYN
    P-->>C: SYN/ACK
    C->>P: ACK
    Note over C,P: Frontend TCP connection established
    P->>S: SYN tới backend targetPort
    S-->>P: RST hoặc không phản hồi
    Note over P,S: Upstream TCP connection failed
    P-->>C: HTTP 502/503 tùy proxy behavior
~~~

### 19.3. So sánh evidence

| Nguồn | Quan sát | Ý nghĩa |
|---|---|---|
| Client pcap | Frontend SYN/SYNACK/ACK thành công | Kết nối tới proxy được thiết lập |
| Proxy access log | Client request tới đúng hostname/path | Request vào proxy |
| Proxy upstream log | Connection refused/timeout tới Pod/Service | Lỗi leg proxy→backend |
| Backend pcap | SYN tới sai port hoặc RST reply | Phát hiện listener/port mismatch |
| Kubernetes Service/EndpointSlice | `port`, `targetPort`, endpoints readiness | Mapping service→backend |
| Application log | Không nhận request tương ứng | Lỗi có thể xảy ra trước app handler |

### 19.4. Hướng sửa có kiểm soát

1. Xác định **proxy thực sự terminate TCP** và có upstream connection riêng.
2. Đối chiếu **backend Service port, targetPort, Pod listener** và readiness.
3. Kiểm tra **NetworkPolicy source egress/destination ingress** và cloud firewall.
4. Chỉ sửa manifest/route được phép, có rollback và test từ proxy tới backend.
5. Lặp test từ client: TCP/TLS hợp lệ, HTTP response theo contract; test direct backend bypass từ nguồn không được phép vẫn DENY.

### 19.5. Các tình huống tương tự

Một SYN proxy có thể cho client hoàn thành bước đầu dù backend không khỏe; một WAF/ingress có thể **trả 403** trước khi gọi upstream; một TLS termination gateway có thể chấp nhận TCP rồi **từ chối certificate hoặc JWT**. Các trường hợp này đều chứng minh một điều: **TCP handshake thành công tại hop A không suy ra end-to-end service success**.

**Bài học:** với proxy/LB/service mesh, luôn phân biệt **front-end và back-end TCP legs**, điểm TLS termination và source/destination identity theo từng hop.

## 20. Lab an toàn: tạo và đọc handshake trên loopback

### 20.1. Phạm vi

Lab này dùng **chính máy Linux lab do bạn kiểm soát** và địa chỉ loopback `127.0.0.1`, không gửi traffic sang bên ngoài. Mục tiêu chỉ là mở một TCP connection, thu ít packets và đọc **SYN/SYNACK/ACK**, rồi so với phản hồi khi không có listener trên một cổng thử.

**Yêu cầu:** Linux với `tcpdump`, `nc` hoặc công cụ TCP listener tương đương; quyền `sudo`/capture được cấp trên máy lab; interface `lo`; không dùng máy của người khác hoặc production host. Cú pháp `nc` có thể khác giữa **OpenBSD netcat, GNU netcat và Ncat**, vì vậy kiểm tra `nc -h` của bản cài trước khi dùng. Các lệnh bên dưới là mẫu không bảo đảm mọi phân phối hỗ trợ nguyên xi.

### 20.2. Kiểm tra port lab và bảo đảm không có listener xung đột

~~~bash
# Chỉ đọc host lab, xem TCP listeners.
ss -lnt

# Ví dụ cổng thử 18080; bảo đảm không có process khác đang dùng nó.
ss -lnt '( sport = :18080 )'
~~~

Không dừng một dịch vụ đang chạy chỉ để chiếm port. Nếu `18080` đang được dùng, chọn một port lab khác được phê duyệt và điều chỉnh cả capture/test.

### 20.3. Mở TCP listener chỉ trên loopback

Trong **terminal A** của Linux lab, một số bản OpenBSD netcat hỗ trợ:

~~~bash
# Lab only: giới hạn bind vào loopback.
nc -l 127.0.0.1 18080
~~~

Nếu bản `nc` yêu cầu `-p` hoặc không hỗ trợ bind syntax trên, sử dụng cú pháp theo chính bản đã cài hoặc một test server có sẵn của lab. Không thay bằng `0.0.0.0` cho tiện, vì có thể mở listener trên mọi interface. Terminal này có thể giữ kết nối tới khi client đóng; chỉ thử một phiên.

### 20.4. Capture handshake ở terminal B

~~~bash
# Lab only: thu tối đa 12 packets tới chính loopback port.
# File output chỉ dùng trên máy lab được kiểm soát.
sudo tcpdump -i lo -nn -s 96 -c 12 \
  -w /tmp/loopback-handshake-lab.pcap \
  'tcp and host 127.0.0.1 and port 18080'
~~~

`-c 12` sẽ kết thúc khi có đủ 12 packets **matching filter**; một kết nối đơn giản có thể ít hơn 12, khiến lệnh vẫn chờ. Trong trường hợp đó hãy **dừng bằng Ctrl+C** sau khi test đã gửi một kết nối và chờ một khoảng đủ để capture được ghi. Không tạo nhiều kết nối để “đủ count” ngoài mục tiêu học; ghi rõ packet count thực.

### 20.5. Tạo đúng một kết nối từ terminal C

~~~bash
# Lab only: nc TCP client tới loopback listener.
printf 'lab-only\n' | nc -w 2 127.0.0.1 18080
~~~

Tùy bản `nc`, `-w` quản lý timeout connect/IO với semantics khác nhau. Nếu client còn chờ EOF hoặc listener chưa đóng, kết thúc phiên bằng Ctrl+C theo môi trường lab. **Chỉ một kết nối** đủ cho mục tiêu quan sát; không sinh tải hoặc scan.

### 20.6. Phân tích file được tạo

~~~bash
# Đọc file, chú ý TCP flags và relative seq/ack.
tcpdump -nn -tttt -r /tmp/loopback-handshake-lab.pcap

# Nếu có tshark, chỉ trích các trường quan trọng.
tshark -r /tmp/loopback-handshake-lab.pcap \
  -Y 'tcp.flags.syn == 1 || tcp.flags.ack == 1' \
  -T fields \
  -e frame.number -e frame.time_relative \
  -e tcp.srcport -e tcp.dstport \
  -e tcp.flags -e tcp.seq -e tcp.ack -e tcp.len
~~~

Phép filter `tcp.flags.ack == 1` cũng match **các ACK/data/FIN packets có ACK bật**, không chỉ ACK thứ ba. Lọc theo đúng **TCP stream** và xem timestamps để đánh dấu packet nào thực sự hoàn tất handshake.

### 20.7. Ghi chú về loopback

- Cả client và server ở cùng máy nên **RTT cực thấp**, không đại diện Internet/VPN.
- Loopback capture có thể dùng **cơ chế packet presentation/offloads khác network interface thật**.
- Hướng interface và Ethernet framing có thể không giống NIC vật lý.
- `tcpdump` không phải ứng dụng TCP listener; nó chỉ quan sát được packet do kernel networking stack xử lý.
- Gói `PSH,ACK`, FIN hoặc RST sau ba gói sẽ tùy `nc` implementation và cách đóng socket.

### 20.8. Test “connection refused” trên port không có listener

Trong lab, sau khi chắc chắn **không có listener** trên port `18081`, có thể thu một trace ngắn ở `lo` rồi thử **một kết nối**:

~~~bash
# Trên máy lab, sau khi xác nhận port 18081 không có listener.
ss -lnt '( sport = :18081 )'

# Terminal capture: đặt filter đúng cổng và dừng bằng Ctrl+C khi đủ trace.
sudo tcpdump -i lo -nn -s 96 \
  'tcp and host 127.0.0.1 and port 18081'

# Một terminal riêng, một lần kết nối có thời gian chờ ngắn.
nc -w 2 -z 127.0.0.1 18081
~~~

Tùy OS/stack, client có thể thấy **SYN → RST,ACK** cho port đóng; nếu không thấy mẫu đó, kiểm tra local firewall, tooling và capture. `-z` của netcat kiểm tra kết nối không gửi payload nhưng tùy implementation; chỉ sử dụng trên **một port loopback được kiểm soát**, không mở rộng thành port scan.

### 20.9. Mẫu báo cáo lab

~~~yaml
lab_id: TCP-LOOPBACK-HANDSHAKE-01
environment: authorized-local-linux-lab
interface: lo
source_ip: 127.0.0.1
destination_ip: 127.0.0.1
destination_port: 18080
expected:
  - syn-client-to-server
  - synack-server-to-client
  - ack-client-to-server
  - sequence-acknowledgment-consistency
evidence_to_record:
  - capture-start-time-and-timezone
  - capture-filter-and-snaplen
  - pcap-file-checksum-if-required
  - packet-count-and-capture-drops
  - frame-numbers-and-relative-times
  - syn-synack-ack-flags-and-seq-ack
  - negotiated-tcp-options-if-present
  - tcp-connection-outcome
result: pending
~~~

**Không điền giá trị “PASS” chỉ từ việc chạy command.** Đọc chính gói ở pcap và ghi kết quả quan sát. Khi lab thực sự không thể chạy do thiếu quyền capture/công cụ, trạng thái là **NOT RUN**, không phải thất bại của TCP.

## 21. Ma trận 36 trường hợp kiểm thử handshake và chất lượng capture

Các test bên dưới là **phương án xác minh có phép**, chưa chạy. Mỗi trường hợp cần ghi **network vantage, 5-tuple, interface, capture/filter, expected packet sequence và mức chắc chắn**.

| Test ID | Mục tiêu | Phép thử / nguồn bằng chứng | PASS khi |
|---|---|---|---|
| **HS-01** | TCP active open bình thường | Loopback local connection | SYN→SYN/ACK→ACK đúng hướng |
| **HS-02** | Seq/Ack của SYN hợp lệ | So raw ISN x với SYN/ACK ack | Ack=x+1 |
| **HS-03** | Seq/Ack của SYN/ACK hợp lệ | So server ISN y với ACK cuối | Ack=y+1 |
| **HS-04** | Relative sequence display | Wireshark/tshark relative vs raw | Không nhầm relative Seq=0 với actual ISN |
| **HS-05** | ACK thuần không tiêu sequence space | Xem segment không payload/FIN/SYN | Next seq không tăng do ACK flag |
| **HS-06** | SYN và FIN tiêu sequence | So flow data + flags | Next expected byte đúng |
| **HS-07** | Same 5-tuple nhiều lần | Phân đoạn theo timestamps và SYN ISNs | Không ghép hai incarnations làm một |
| **OPT-01** | MSS option | Đọc client/server SYN options | Phân biệt mỗi chiều, không nhầm MTU |
| **OPT-02** | Window Scale negotiation | Kiểm tra cả SYN, SYN/ACK | Scale áp đúng window direction |
| **OPT-03** | SACK Permitted | Kiểm tra SYN options | Không suy đã mất gói |
| **OPT-04** | TCP Timestamps | TSval/TSecr trong capture có hỗ trợ | Không nhầm TSval với UTC |
| **OPT-05** | Data trong SYN nếu có | Trace được cấp phép có TCP Fast Open | Không bỏ segment chỉ vì SYN+payload |
| **TIME-01** | TCP handshake RTT estimate ở client | Timestamp SYN và SYN/ACK cùng vantage | Đơn vị và giới hạn ghi đúng |
| **TIME-02** | Server ACK receipt | Capture phía server | Không lấy client send ACK làm server receive |
| **TIME-03** | Clock skew giữa hai pcaps | Đối chiếu clocks và time sync | Không tạo one-way delay âm giả |
| **TIME-04** | TCP vs TLS/app duration | Packet capture + client timers | Không coi SYN RTT là total request |
| **FAIL-01** | Port đóng | Một loopback controlled connection | RST/response được diễn giải đúng |
| **FAIL-02** | SYN retransmission | Phân tích pcap có sẵn từ lab bị loss | Không suy nguyên nhân duy nhất |
| **FAIL-03** | Thiếu SYN/ACK ở client | Capture cả hai phía + route evidence | Chỉ nêu hop lỗi khi có chứng cứ |
| **FAIL-04** | ACK cuối không tới server | Capture cả hai phía + server state | Không suy server established từ client pcap |
| **FAIL-05** | ICMP reject | Phân tích trace lab có ICMP type/code | Phân biệt ICMP với TCP RST |
| **FAIL-06** | Post-handshake RST | Theo dõi sau ACK cuối | Phân biệt handshake và TLS/app lỗi |
| **PATH-01** | Firewall allow đúng | Approved client TCP test | Bắt tay thành công tại destination |
| **PATH-02** | Firewall deny đúng | Unauthorized test từ lab có quyền | Deny bởi intended firewall/PEP |
| **PATH-03** | NAT translation | Before/after NAT captures và mapping | Ghép tuple đúng, không dựa một IP |
| **PATH-04** | Asymmetric return path | Routes, state logs, two-sided capture | Xác định đúng đường về |
| **PATH-05** | TCP termination tại proxy | Frontend/upstream flows | Xem hai handshakes riêng |
| **PATH-06** | VPN encapsulation | Outer vs inner capture point | Không lẫn tunnel packet với TCP inner |
| **PATH-07** | Dual-stack attempts | IPv4 và IPv6 packets | Không chỉ phân tích successful flow |
| **CAP-01** | BPF và display filter khác nhau | SYN-only filter vs full stream | Không nghĩ ACK bị mạng drop nếu do filter |
| **CAP-02** | Capture loss vs network loss | `tcpdump`/SPAN drop metrics | Không đồng nhất hai loại drop |
| **CAP-03** | Checksum offload | Host vs receiver capture | Không khẳng định corrupted wire packet khi chưa đối chứng |
| **CAP-04** | GRO/TSO effect | Host stack vs interface observation | Hiểu khác biệt packet size/count |
| **CAP-05** | Snaplen đầy đủ cho TCP options | So caplen và header fields | Không coi truncated option là packet lỗi |
| **SEC-01** | SYN flood suspicion | Rate/backlog/legitimate SLI/host metrics | Không kết luận chỉ vì nhiều SYN |
| **SEC-02** | SYN proxy/middlebox response | Device policy + upstream capture | Không nhầm proxy reply với backend |

### 21.1. Đánh giá PASS, FAIL, INCONCLUSIVE

- **PASS:** positive flow chứng minh endpoint sống; negative flow bị **đúng policy** từ chối; Seq/Ack/flags đúng với capture và các artifacts đủ để kiểm tra.
- **FAIL:** suy sai state/sequence, bỏ mất ACK vì filter nhưng kết luận network drop, diễn giải proxy frontend như backend, hoặc một unauthorized flow thực sự bypass policy.
- **INCONCLUSIVE:** capture chỉ một chiều, thiếu SYN, clock skew không biết, capture drops, NAT mapping không rõ, backend down khi thử DENY hoặc không biết implementation TCP middlebox.

Ví dụ: gói SYN xuất hiện hai lần ở client không chứng minh server đang down, firewall đang drop hay ai đó tấn công. Chỉ đánh dấu **mẫu đã thấy SYN retransmission**, còn **nguyên nhân** phải chờ chứng cứ đường về hoặc phía server.

### 21.2. Mẫu test evidence

~~~yaml
test_id: PATH-03
environment: authorized-nat-lab
observation_window_utc: pending
client:
  ip: 192.0.2.10
  source_port: 51514
server:
  ip: 198.51.100.20
  port: 443
nat:
  translated_source_ip: 203.0.113.10
  translated_source_port: 62001
capture_points:
  - pre-nat-client-segment
  - post-nat-server-segment
evidence:
  - packet-timestamps-and-filter
  - syn-seq-and-ack-correspondence
  - nat-session-translation-logs
  - capture-drop-counters
  - policy-rule-and-change-revision
result: pending-execution
~~~

Địa chỉ/port trong mẫu là **ví dụ**, không phải NAT table thật. Mọi raw pcap bằng chứng phải được lưu và phân quyền theo chính sách tổ chức.

## 22. Troubleshooting handshake: từ biểu hiện đến kiểm chứng

### 22.1. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần có |
|---|---|---|
| Chỉ thấy SYN trên client | Outbound/return drop, capture một chiều, server không phản hồi | Capture server, routes, firewall/ACL logs |
| Thấy SYN lặp và timeout | SYN/SYNACK mất, state/backlog, network path | Inter-arrival times, retrans metrics, both sides |
| SYN rồi RST,ACK | Port đóng, OS/proxy active reject, firewall TCP reset | Source of RST, listener config, rule ID |
| SYN rồi ICMP unreachable | Router/ACL reject, route failure | ICMP type/code và quoted IP/TCP header |
| Server thấy SYN nhưng không thấy SYNACK | Host firewall/kernel/listener/backlog, capture gap | Host TCP counters, local capture and logs |
| Server gửi SYNACK nhưng client không thấy | Return route, NAT/session state, asymmetric path | Return captures, translation state, route evidence |
| Client gửi ACK cuối nhưng server SYNACK lại | ACK mất, rejected ACK, state mismatch, capture gaps | Server capture, sequence, tuple, conntrack |
| Handshake OK, HTTPS thất bại | TLS certificate/SNI/trust, gateway, upstream | Client TLS logs, proxy/backend evidence |
| Handshake OK, HTTP 503 | Backend health, service port, upstream connection | LB/ingress logs, EndpointSlice, second TCP leg |
| Handshake OK với VPN nhưng app treo khi data lớn | MTU/MSS/PMTUD, app/proxy size constraints | MSS options, path MTU, TLS/data packets |
| TCP options “biến mất” | Capture bắt giữa flow, snaplen thấp, middlebox rewrite | SYN cả hai phía, caplen, capture point |
| Seq=0 trên nhiều streams | Relative numbering, không phải cùng ISN | `tcp.seq_raw`, stream mapping |
| `Ack` không bằng payload byte count | SYN/FIN sequence, multiple segments, relative numbering | ISN, SYN/FIN, TCP len, cumulative ACK |
| TCP checksum “bad” trên source | TX checksum offload hoặc packet thật lỗi | Capture receiver/SPAN, NIC offload state |
| Một TCP segment lớn hơn MTU | TSO/GSO/GRO hoặc capture offload | Physical capture, stack configuration |
| Wireshark đánh dấu retransmission nhưng app ổn | Analyzer missing packets/out-of-order, capture duplicate | Capture drops, sequence progression, both sides |
| tcpdump không thấy ACK thứ ba | SYN-only BPF filter, capture stop quá sớm | Capture filter, start/end timestamps |
| Flow trên client khác tuple ở server | SNAT/DNAT, port mapping, proxy | NAT logs, pre/post captures |
| Firewall không thấy return traffic | Asymmetric routing, wrong mirror/zone, overlay | Routes, interface ingress/egress, middlebox |
| IDS có alert nhưng không thấy block | Passive/out-of-band mode, alert-only action | Sensor policy/action mode |
| SYNs/s tăng mạnh | Legit traffic spike, retries, scan, DoS | Load, source distribution, backlog, user impact |
| Backend không có SYN dù proxy trả SYN/ACK | SYN proxy hoặc TCP-terminating LB | Frontend/backend capture, proxy config |
| IPv4 OK, IPv6 timeout | AAAA records, IPv6 ACL/routes, address selection | Separate IPv4/IPv6 flow captures |
| DNS OK nhưng TCP SYN không phát | Proxy selection, client OS policy, local firewall/app | Client application/socket logs, interface capture |
| Một pcap có RTT âm khi so server/client | Clock skew hoặc timestamp source khác | Time sync, local relative times, clock origin |
| No packets vì capture ở eth0 | Flow thực đi qua `lo`, `tun0`, `veth`, CNI/overlay | Route, interface inventory, namespace |
| TCP established nhưng user nhận 403 | Application authz hoặc WAF/mTLS layer sau TCP | HTTP and security decision logs |
| Nhiều resets khi connection reuse | Keepalive/idle timeout, proxy close, app reset | Connection timeline, idle config, packet direction |

### 22.2. Chẩn đoán bằng các câu hỏi có thứ tự

1. **Đúng connection chưa?** Xác nhận hostname, resolved A/AAAA, source port, destination port, TCP stream và timestamp.
2. **Client đã phát SYN chưa?** Nếu chưa, điều tra client application, local routing và network stack; không đổ lỗi ngay cho server.
3. **Server có nhận SYN không?** Nếu không, tìm network path, ACL/NAT và capture visibility.
4. **Server có phát SYN/ACK hoặc RST không?** Nếu không, xem listener, host firewall, backlog và kernel telemetry.
5. **SYN/ACK có tới client không?** Nếu không, xem return path, NAT/state, reverse routes và mirror completeness.
6. **Client đã ACK đúng chưa?** Kiểm seq/ack, flags và sự tương ứng của hai hướng.
7. **ACK cuối có tới server không?** Đừng coi client-side capture là chứng cứ phía server.
8. **Có handshake/proxy leg khác không?** Nếu có LB/CDN/ingress, mở rộng điều tra sang upstream flow.
9. **Sau established xảy ra gì?** TLS, app protocol, RST, FIN, HTTP status, timeout, MTU và dependencies.
10. **Các logs/policies có xác nhận không?** Gắn bằng chứng với firewall rule, route revision, Pod UID hoặc proxy config.

### 22.3. Phân biệt ba kiểu kết luận

**Quan sát:** “Client pcap có ba SYN cùng tuple và ISN, cách nhau theo thời gian, không có SYN/ACK trong file.”

**Giả thuyết:** “Return path có thể bị firewall/NAT chặn hoặc server không phản hồi.”

**Kết luận đã chứng minh:** “Firewall F ghi drop session X do rule Y tại timestamp Z; capture trước firewall có SYN/ACK, capture sau không có; change rollback khôi phục cùng flow hợp lệ.” Chỉ đưa câu thứ ba nếu các chứng cứ thực đã có.

### 22.4. Rủi ro khi chỉ xem HTTP status

Một TCP reset hoặc timeout **trước TLS** có thể không tạo HTTP status code. Ngược lại, TCP handshake đẹp không ngăn HTTP 401/403/404/500. Do đó user-facing availability phải có **client-side synthetic TCP/TLS/HTTP metrics**, chứ không chỉ đếm HTTP 5xx ở backend.

## 23. Runbook điều tra TCP handshake từ packet capture

### Bước 1 — Xác định quyền, mục tiêu và phạm vi

Trước khi capture:

~~~yaml
# Policy-as-intent cho case/ticket; không phải chương trình thực thi.
case_id: TCP-HANDSHAKE-LAB-003
purpose: investigate-authorized-tcp-connect-failure
authorized_network: controlled-lab
request_owner: application-or-network-team
source: 192.0.2.10
destination: 198.51.100.20
destination_port: 443
protocol: TCP
allowed_capture_points:
  - client-lab-host
  - server-lab-host
capture_window_minutes: 2
capture_filter: host-specific-tcp-port
data_handling:
  - no-unnecessary-payload
  - access-controlled-storage
  - limited-retention
expected_evidence:
  - tcp-flags-seq-ack
  - capture-drop-stats
  - firewall-route-state-logs
  - positive-and-negative-policy-test
status: planned
~~~

Đây là form mô tả **phạm vi thu được phép**. Không có quyền capture chỉ vì biết source/destination IP. Phải xác định trách nhiệm dữ liệu, tenant privacy và cách xử lý pcap nguyên gốc.

### Bước 2 — Lập sơ đồ network path

~~~mermaid
flowchart LR
    C["Client"] --> R["Gateway / VPN / overlay"]
    R --> F["Firewall / NAT"]
    F --> P["LB / proxy / ingress"]
    P --> S["Backend"]
    C -. "Capture source" .-> CAP1["Pcap A"]
    F -. "Capture boundary" .-> CAP2["Pcap B"]
    S -. "Capture receive" .-> CAP3["Pcap C"]
~~~

Đánh dấu rõ **TCP termination point, NAT mappings, interface/tunnel names, IPv4/IPv6 và những hops không thể nhìn traffic plaintext**. Không nhất thiết thu ở mọi hop: chọn hai hoặc ba điểm giúp trả lời câu hỏi mà vẫn giảm exposure.

### Bước 3 — Thống nhất thời gian và cấu hình capture

- Ghi UTC start/end, device hostname, interface, timezone và clock sync.
- Chọn filter giới hạn source/destination/port; tránh capture cả subnet không cần thiết.
- Chọn `snaplen` đủ đọc TCP headers/options, nhưng không lấy application payload nếu không cần.
- Ghi tcpdump/Wireshark/tshark version để người khác tái lập cách parse.
- Giới hạn duration/packet count, quyền file và retention.
- Ghi capture drop counters sau thu.

### Bước 4 — Tạo một phép thử có phép

Dùng **client được phép** tạo một kết nối test duy nhất tới endpoint đã duyệt. Nếu service là HTTP/TLS, giữ TLS verification và có thể dùng `curl` một request low-impact:

~~~bash
# MINH HỌA: chỉ dùng khi đã thay hostname bằng service lab có phép.
curl --verbose --head \
  --connect-timeout 3 --max-time 10 \
  https://api.lab.example.test/health
~~~

Lệnh này có thể tạo **nhiều TCP connection attempts** tùy DNS/IPv4/IPv6/proxy/retry behavior; phải đối chiếu logs để chọn đúng flow. `HEAD` có thể không được mọi server hỗ trợ; nếu nhận `405 Method Not Allowed`, đó không đồng nghĩa TCP handshake thất bại. Nếu endpoint chỉ hỗ trợ GET, dùng một GET ít tác động trong phạm vi lab.

### Bước 5 — Phân tích SYN, SYN/ACK và ACK

Ghi:

~~~text
Packet #1:
  timestamp, source/dest, flags SYN, absolute and relative seq
  MSS, WScale, SACK, TS options, TCP payload length

Packet #2:
  timestamp, reversed endpoints, flags SYN+ACK
  server seq, ack matching client ISN+1, negotiated options

Packet #3:
  timestamp, client -> server, ACK flag
  seq matching client SYN consumption and ack=server ISN+1

Outcome:
  observed-at-client? observed-at-server? established in endpoint telemetry?
  TLS or application result? packet capture completeness?
~~~

Nếu không thấy ba packet, ghi **đúng những packet có trong file** rồi kiểm tra filter/coverage. Đừng tự điền một SYN/ACK chỉ vì giả định service đang chạy.

### Bước 6 — Ghép logs và capture ở các ranh giới

| Hệ thống | Thông tin có thể liên kết |
|---|---|
| Client | Socket error, source port, connect timestamp, DNS result |
| Host TCP stack | SYN-SENT/SYN-RECEIVED, retransmissions, listener/backlog |
| Firewall/CNI | Rule/action, flow ID, session state, NAT translation |
| Cloud LB/ingress | Frontend connect result và upstream connect result |
| VPN gateway | Tunnel and inner route/ACL status |
| Backend | Listener, accept queue, application/TLS errors |
| Metrics backend | TCP connect success/latency, 5xx, packet drops, pps |

Ghép theo **timestamp, connection identifiers/5-tuple, source/destination after NAT và request IDs** khi có. Không đưa những packet từ nhiều client hoặc nhiều retry attempts vào một câu chuyện sai.

### Bước 7 — Đưa ra kết luận có mức độ chắc chắn

Ví dụ:

~~~text
OBSERVED:
  Client sends SYN twice, same absolute ISN and 5-tuple.
  Server capture receives both SYNs and emits SYN/ACKs.
  Client capture has no SYN/ACK.

LIKELY:
  Return path issue or capture visibility gap.

NOT YET PROVEN:
  Which firewall/device dropped the response.

NEXT:
  Review return routes/NAT/ACL; scoped dual-side capture.
~~~

Đây là báo cáo tốt hơn một câu “mạng lỗi”, vì nó chỉ ra **đúng bằng chứng, giới hạn và bước phân biệt giả thuyết**.

### Bước 8 — Sửa có kiểm soát và kiểm thử hồi quy

Sau khi xác định nguyên nhân bằng bằng chứng và được phê duyệt, chỉ thay **đúng route/ACL/Service port/TLS configuration cần thiết**, có change diff, owner và rollback. Lặp:

- **Positive:** approved client hoàn tất TCP handshake, TLS/application request hợp lệ.
- **Negative:** unapproved source vẫn bị chặn bởi đúng firewall/NetworkPolicy.
- **Telemetry:** error rate, TCP SYN retransmissions, connect latency và capture drops trở lại bình thường theo baseline.
- **Safety:** pcap được phân quyền/lưu giữ đúng, không lộ credentials.

### Bước 9 — Hậu kiểm khi lỗi đã được xử lý

Kiểm tra cùng vấn đề có thể tái xuất ở **IPv6, DR region, proxy upstream leg, container network namespace và VPN split routes** không. Nếu xuất hiện sau policy deploy, thêm test vào regression pipeline có phép hoặc alert vận hành; không dùng một thay đổi firewall mở rộng toàn mạng như giải pháp vĩnh viễn.

## 24. Bài tập tự kiểm tra và thực hành phân tích

### Bài 1 — Nhận diện ba gói

Trong trace có ba TCP segments:

~~~text
A -> B: SYN
B -> A: SYN,ACK
A -> B: ACK
~~~

**Câu hỏi:** endpoint nào chủ động mở kết nối theo mô hình thông thường, và server thường ở trạng thái gì ngay sau khi phát SYN/ACK?

*Đáp án gợi ý:* A là active opener/client; B là passive opener/server và thường ở `SYN-RECEIVED` chờ ACK hợp lệ, với caveat khi implementation dùng SYN cookies hoặc các cơ chế đặc biệt.

### Bài 2 — ACK của SYN

Client gửi SYN với absolute `Seq=123456`. Server SYN/ACK phải ACK giá trị nào nếu nhận SYN bình thường?

*Đáp án:* `Ack=123457`, vì SYN tiêu một sequence number.

### Bài 3 — ACK cuối

Server SYN/ACK có `Seq=900000` và `Ack=123457`. Gói ACK tiếp theo từ client (không payload) cần `Ack` là bao nhiêu?

*Đáp án:* `900001`. Client sequence dùng sau SYN là `123457` nếu không có data khác.

### Bài 4 — Relative Seq=0

Wireshark hiển thị `Seq=0` cho SYN của cả hai bên. Hai ISN trên dây có nhất thiết là 0 không?

*Đáp án:* không; Wireshark có thể đang hiển thị **relative sequence numbers**. Xem raw sequence fields hoặc tắt preference.

### Bài 5 — Data sau handshake

Client gửi SYN `Seq=500`, ACK hoàn tất rồi 200 bytes application data từ `Seq=501`. Khi server đã nhận liên tục, `Ack` mong đợi sau data là gì?

*Đáp án:* `701` (`500 + 1 SYN + 200 bytes`).

### Bài 6 — ACK thuần

Một ACK thuần có payload length 0, không SYN/FIN, `Seq=701`. ACK flag tự làm `Seq` tăng một không?

*Đáp án:* không; ACK thuần không tiêu sequence space.

### Bài 7 — TCP flags

Ý nghĩa của `[S.]`, `[R.]`, `[P.]` trong một output `tcpdump` là gì?

*Đáp án gợi ý:* SYN+ACK; RST+ACK; PSH+ACK. Cần xem hướng và state để diễn giải hành vi.

### Bài 8 — MSS và MTU

Một client SYN khai MSS=1460. Có thể kết luận mọi link trên toàn đường đều MTU 1500 không?

*Đáp án:* không. MSS là giới hạn receive TCP payload của một endpoint, trong khi path MTU, tunnels/VPN/IP options và middleboxes có thể khác.

### Bài 9 — Window Scale

Peer trong SYN khai Window Scale=7 và sau đó quảng bá raw window=1000 trong một ACK ở giai đoạn phù hợp. Effective advertised receive window là bao nhiêu?

*Đáp án gợi ý:* `1000 × 2^7 = 128000 bytes`, giả định scale negotiation hợp lệ và đó là window field của peer đã khai scale.

### Bài 10 — SACK Permitted

SYN có `SACK Permitted`. Điều đó đã chứng minh có packet loss chưa?

*Đáp án:* chưa. Nó chỉ là thương lượng hỗ trợ SACK; cần ACK/SACK blocks và packet evidence về loss/reordering.

### Bài 11 — Timestamps

SYN có `TSval=12345678`. Đây có phải Unix timestamp có thể đổi trực tiếp thành ngày giờ không?

*Đáp án:* không; TCP timestamp có clock/tick semantics phụ thuộc implementation, khác capture timestamp.

### Bài 12 — Đo RTT

Capture trên client có SYN ở `t=0.000` và SYN/ACK ở `t=0.040`. Có thể nói RTT mạng chính xác bằng 40 ms không?

*Gợi ý:* chỉ có thể nói **khoảng quan sát SYN→SYN/ACK là 40 ms** tại vantage đó; còn server processing, proxy, capture timestamp jitter và đường đi phải xét riêng.

### Bài 13 — Client đã gửi ACK

Client capture thấy ACK cuối, nhưng server tiếp tục retransmit SYN/ACK. Có thể kết luận server chắc chắn established không?

*Đáp án:* không. Có thể ACK chưa đến hoặc bị từ chối, hoặc capture/state không đầy đủ. Cần evidence tại server.

### Bài 14 — Filter chỉ SYN

Một pcap thu bằng BPF `tcp[13] & 2 != 0` chỉ có SYN và SYN/ACK. Vì sao không thấy ACK thứ ba?

*Đáp án:* ACK cuối thường không có SYN bit nên bị **capture filter loại**, không phải chắc chắn mất trên mạng.

### Bài 15 — SYN rồi RST

Client thấy SYN→RST,ACK. Điều gì có thể xảy ra? Có nên kết luận server process đã phát RST?

*Gợi ý:* port không listen, OS reject hoặc firewall/proxy tạo RST. Phải dùng listener/firewall logs/captures hai phía để xác định origin.

### Bài 16 — SYN lặp

Client gửi ba SYN cùng ISN nhưng không thấy SYN/ACK. Hãy nêu **bốn giả thuyết** không được xem là kết luận chắc chắn.

*Gợi ý:* outbound SYN drop, return SYN/ACK drop, server listener/backlog issue, capture một chiều/sampling, NAT state/route lỗi.

### Bài 17 — NAT

Trước NAT, packet là `192.0.2.10:51514 → 198.51.100.20:443`. Sau NAT, nguồn là `203.0.113.10:62001`. Có thể tìm cùng flow trên server chỉ bằng `192.0.2.10` không?

*Đáp án:* không. Cần dịch source IP/port theo NAT mapping và timestamp; proxy termination còn tạo flow mới.

### Bài 18 — Offload

Source pcap báo TCP checksum incorrect và segment data lớn hơn MTU. Điều gì nên kiểm tra trước khi quy lỗi đường truyền?

*Gợi ý:* checksum offload, TSO/GSO/GRO, capture stage, receive-side/SPAN capture và NIC errors.

### Bài 19 — SYN flood

Trong năm phút, SYN/s tăng 10 lần và tỷ lệ completed handshakes giảm. Có thể kết luận chắc chắn DDoS không?

*Đáp án:* không. Cần source distribution, backlog/CPU/pps/conntrack, legitimate traffic impact, retry rates, change history và security enforcement evidence.

### Bài 20 — VPN

Trên outer VPN interface chỉ thấy encrypted UDP packets, không thấy SYN tới ứng dụng nội bộ. Có thể nói client không phát TCP SYN không?

*Gợi ý:* chưa. Inner TCP có thể nằm trong tunnel mã hóa. Capture pre-tunnel/decapsulated path tại điểm có quyền.

### Bài 21 — TLS và TCP

TCP SYN/SYNACK/ACK thành công, sau đó TLS handshake fail vì certificate hostname sai. Có nên đánh dấu TCP handshake lỗi không?

*Đáp án:* không. Đây là lỗi ở **TLS identity validation** sau khi TCP thiết lập; user-visible HTTPS vẫn có thể fail.

### Bài 22 — Proxy và backend

Client TCP thành công với CDN nhưng CDN trả 503 vì upstream Pod không có listener. Cần thu thêm ở đâu?

*Gợi ý:* ở **upstream TCP leg** của CDN/ingress tới Service/Pod; đối chiếu targetPort, EndpointSlice, NetworkPolicy, proxy connect logs.

### Bài 23 — Positive và negative controls

Một Pod không có quyền bị timeout tới DB, nhưng DB service đang Down. Có thể đánh dấu NetworkPolicy deny PASS không?

*Đáp án:* không. Cần một nguồn có quyền gọi thành công tới cùng destination và CNI/firewall logs chứng minh deny đúng rule.

### Bài 24 — Dữ liệu forensics

Vì sao không nên đăng pcap đầy đủ lên diễn đàn để nhờ xem handshake, kể cả traffic HTTPS?

*Gợi ý:* pcap có IPs, hostnames, metadata, SNI/cert tùy protocol, timings, một phần plaintext trước TLS hoặc credentials từ các flow khác. Trích xuất/redact tối thiểu và bảo vệ bằng chứng gốc.

### Bài 25 — Phân tích tổng hợp

Cho sơ đồ **client → VPN → firewall NAT → load balancer full proxy → API Pod**. Client thấy SYN lặp, server API không thấy SYN. Hãy vẽ **các TCP legs**, đề xuất **ba vị trí capture**, nêu **hai phép thử dương/âm** và một plan kiểm chứng NAT/return path.

*Gợi ý:* phân biệt client→LB frontend với LB→API upstream; capture tại client trước tunnel, firewall sau decapsulation/NAT hoặc LB frontend, và LB upstream/API; xem route, NAT mapping, proxy session/logs. Positive từ approved client tới đúng service; negative từ unauthorized client phải bị đúng PEP chặn. Không khẳng định API Pod lỗi khi client chưa thể bắt tay với frontend gateway.

## 25. Checklist thực hành và điều tra TCP handshake

### 25.1. Quyền thu và mục tiêu

- [ ] Đã xác định **chủ sở hữu kết nối, mục tiêu điều tra, nguồn/đích và phạm vi pháp lý/quyền thu**.
- [ ] Capture đúng **host, interface, namespace, network segment và cửa sổ thời gian**; không thu toàn bộ traffic ngoài nhu cầu.
- [ ] Mọi địa chỉ/hostname/cổng trong lệnh mẫu đã thay bằng **lab endpoint được phê duyệt**.
- [ ] Có phương pháp **chỉ lấy TCP headers** nếu đủ cho mục tiêu; xử lý snaplen, options và nguy cơ payload lọt vào.
- [ ] File pcap được **lưu có kiểm soát, giới hạn quyền truy cập, encryption/retention và chain of custody** khi cần.
- [ ] Không dùng SYN flood, port scan diện rộng hoặc vô hiệu hóa security controls chỉ để chứng minh mô hình.

### 25.2. Kiểm tra đúng ba bước

- [ ] Nhận diện **active opener, passive opener, 5-tuple, capture interface và chiều kết nối**.
- [ ] Có SYN client→server với ACK flag không bật theo normal active open.
- [ ] Có SYN/ACK phản hồi, `Ack = client ISN + 1`.
- [ ] Có ACK cuối chiều client→server, `Ack = server ISN + 1`.
- [ ] Phân biệt **Seq/Ack tuyệt đối với Wireshark relative display**.
- [ ] Nhớ **SYN/FIN chiếm một sequence number, TCP data chiếm đúng số bytes, ACK flag tự nó không chiếm**.
- [ ] Chỉ kết luận server nhận ACK cuối khi có bằng chứng tại server/endpoint; không suy từ gói phát tại client.
- [ ] Phân biệt handshake thông thường với TCP Fast Open, simultaneous open hoặc SYN proxy khi có bằng chứng.

### 25.3. TCP options và thông số hiệu năng

- [ ] Đọc **MSS từng chiều**, phân biệt MSS với link/path MTU và encapsulation.
- [ ] Đọc **Window Scale** đúng hướng, không áp shift bừa cho SYN raw window.
- [ ] Phân biệt **SACK Permitted** trong handshake với SACK blocks sau khi truyền dữ liệu.
- [ ] Hiểu **TSval/TSecr** là TCP timestamp fields, không phải UTC.
- [ ] Không kết luận ECN congestion chỉ từ các flags thương lượng hỗ trợ.
- [ ] Khi handshake OK nhưng data lớn lỗi, tiếp tục xem **MTU/PMTUD, TCP segment sizes, TLS payload và tunnel overhead**.
- [ ] Đo SYN→SYN/ACK elapsed tại **đúng vantage**, không coi nó là server processing time hoặc một-way latency chính xác.

### 25.4. Capture quality và công cụ

- [ ] Biết **BPF capture filter** và **Wireshark display filter** có ngữ pháp/khả năng khác nhau.
- [ ] Không dùng SYN-only capture filter để kết luận thiếu ACK cuối.
- [ ] Kiểm tra **packet count, capture drops, snaplen và stop time**.
- [ ] Kiểm tra **SPAn/mirror direction, oversubscription, sampling và return path**.
- [ ] Nhận diện **checksum offload, GRO/LRO/GSO/TSO**, không coi mọi packet trông lạ là lỗi trên dây.
- [ ] Phân tích **inner vs outer packets** khi có VPN/overlay/VXLAN/IPsec.
- [ ] Có raw sequence values và TCP stream mapping trước khi so hai pcaps.
- [ ] Đồng bộ **timestamps/timezone**, không tính one-way delay từ clocks không đủ tin cậy.

### 25.5. Firewall, NAT, proxy và an ninh

- [ ] Đã xem **route/firewall/CNI/NAT/session state** ở cả hai hướng.
- [ ] Có NAT translation mapping khi source/destination IP hoặc port khác giữa captures.
- [ ] Đã kiểm tra có **load balancer/TCP proxy/SYN proxy/service mesh** tạo kết nối riêng không.
- [ ] Không nhầm SYN/ACK từ proxy với backend application readiness.
- [ ] Phân biệt **RST active reject, ICMP reject, silent drop và TCP timeout** bằng packet/log evidence.
- [ ] Có **positive control** từ nguồn có quyền, **negative control** từ nguồn bị cấm, cùng destination/port phù hợp.
- [ ] Một deny đúng chính sách không tự được tính là outage của người dùng đủ điều kiện.
- [ ] Nếu nghi SYN flood, đã xem **SYN/s, completed connections, backlog/SYN cookies, pps, conntrack, legitimate user impact và source patterns**.
- [ ] Không gắn nhãn “tấn công” chỉ từ SYN lặp hoặc một bộ lọc Wireshark.
- [ ] Đã phân biệt lỗi TCP với **TLS certificate/SNI/authentication, HTTP status và application permissions**.

### 25.6. Báo cáo và khắc phục

- [ ] Báo cáo có **OBSERVED / LIKELY / NOT PROVEN / NEXT ACTION**, tránh kết luận vượt chứng cứ.
- [ ] Chỉ ra **vị trí capture, interface, time window, direction, filter, drops, 5-tuple và TCP flags/Seq/Ack**.
- [ ] Có **firewall rule ID, NAT state, service owner, config revision và log correlation** khi nêu nguyên nhân.
- [ ] Chỉnh sửa route/ACL/proxy/service port phải có **phê duyệt, canary, rollback và post-change validation**.
- [ ] Sau sửa đã kiểm tra cả **handshake của nguồn được phép** và **deny của nguồn không có quyền**.
- [ ] Giữ pcap, logs và tài liệu điều tra theo **privacy/security retention**, không để raw payload/token bị lộ.

**Kết luận:** ba gói **SYN → SYN/ACK → ACK** là dấu vết thiết lập trạng thái TCP, nhưng cách đọc đúng đòi hỏi hiểu **sequence space, cờ TCP, tùy chọn thương lượng, điểm capture, đường NAT/firewall/proxy và chất lượng bản ghi**. Một pcap cho biết **những packets quan sát được ở điểm đó**, không tự chứng minh mọi packet đến được endpoint còn lại hoặc ứng dụng hoạt động. Kỹ thuật điều tra đáng tin là **thu hẹp giả thuyết theo từng hop, xác minh cả hai chiều và dùng positive/negative controls**, đồng thời tách lỗi kết nối TCP khỏi TLS, authorization và xử lý nghiệp vụ.

### Tài liệu tham khảo

- [RFC 9293 — Transmission Control Protocol (TCP)](https://www.rfc-editor.org/rfc/rfc9293): TCP header, sequence space, flags, handshake và state machine.
- [RFC 7323 — TCP Extensions for High Performance](https://www.rfc-editor.org/rfc/rfc7323): Window Scale, TCP Timestamps và PAWS.
- [RFC 2018 — TCP Selective Acknowledgment Options](https://www.rfc-editor.org/rfc/rfc2018): SACK Permitted và SACK blocks.
- [RFC 5681 — TCP Congestion Control](https://www.rfc-editor.org/rfc/rfc5681): congestion window và loss-related behavior.
- [RFC 3168 — ECN Addition to IP](https://www.rfc-editor.org/rfc/rfc3168): TCP/IP ECN signaling và congestion indication.
- [RFC 7413 — TCP Fast Open](https://www.rfc-editor.org/rfc/rfc7413): data trong SYN và ảnh hưởng của TCP Fast Open.
- [RFC 4987 — TCP SYN Flooding Attacks and Common Mitigations](https://www.rfc-editor.org/rfc/rfc4987): SYN flooding, SYN cookies và các chiến lược phòng vệ.
- [RFC 5737 — IPv4 Address Blocks Reserved for Documentation](https://www.rfc-editor.org/rfc/rfc5737): các dải IP minh họa.
- [Wireshark User's Guide — Display Filters](https://www.wireshark.org/docs/wsug_html_chunked/ChapterWork.html): cách đọc và chọn lọc packets trong Wireshark.
- [Wireshark Display Filter Reference — TCP](https://www.wireshark.org/docs/dfref/t/tcp.html): các trường flags, sequence, acknowledgment, options và analysis.
- [Wireshark User's Guide — Follow TCP Stream](https://www.wireshark.org/docs/wsug_html_chunked/ChAdvFollowStreamSection.html): phân tích đúng một TCP stream.
- [Wireshark TShark Manual](https://www.wireshark.org/docs/man-pages/tshark.html): trích xuất packet fields từ pcap bằng dòng lệnh.
- [tcpdump Manual](https://www.tcpdump.org/manpages/tcpdump.1.html): options capture/read pcap và output format.
- [pcap-filter Manual](https://www.tcpdump.org/manpages/pcap-filter.7.html): cú pháp capture filter BPF.
- [Linux Kernel — Networking Documentation](https://docs.kernel.org/networking/index.html): các chức năng network stack/offload theo triển khai.
- [NIST SP 800-94 — Guide to Intrusion Detection and Prevention Systems](https://csrc.nist.gov/pubs/sp/800/94/final): IDS/IPS deployment, visibility và operational constraints.
- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations](https://csrc.nist.gov/pubs/sp/800/61/r3/final): quy trình điều tra và bảo toàn bằng chứng.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log provenance và xử lý dữ liệu nhạy cảm.









