# Port scanning: khảo sát cổng và đánh giá bề mặt mạng

**Port scanning (quét cổng)** là kỹ thuật gửi các gói tin hoặc yêu cầu kết nối đến những cổng giao vận của một thiết bị nhằm suy luận cổng nào có dịch vụ tiếp nhận, cổng nào từ chối kết nối và cổng nào đang bị lọc hoặc không thể kết luận. Đây là một phần của **reconnaissance**: thu thập thông tin về bề mặt mạng trước khi đánh giá bảo mật, triển khai dịch vụ hoặc điều tra sự cố.

Trong học phần **SECURITY_NETWORK_SECURITY**, port scanning liên hệ trực tiếp với kiểm soát firewall, phân đoạn mạng, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi và môi trường cloud. Một kết quả quét có ý nghĩa khi xác định rõ **đang quan sát từ đâu, đối tượng nào, giao thức gì, tại thời điểm nào và chính sách mạng nào đang tác động**.

Port scanning có hai cách sử dụng lớn: người quản trị kiểm kê dịch vụ và kiểm chứng chính sách kết nối; đối thủ khảo sát những cổng có thể tiếp cận để lựa chọn mục tiêu tiếp theo. Vì vậy mọi hoạt động quét chủ động phải nằm trong **phạm vi tài sản được sở hữu hoặc được cho phép kiểm tra**, với giới hạn số lượng cổng, tần suất và mức tác động phù hợp.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích địa chỉ IP, giao thức, cổng và socket cùng cách một dịch vụ lắng nghe kết nối.
2. Phân biệt các trạng thái **open**, **closed**, **filtered**, **unfiltered**, **open|filtered** và **closed|filtered** trong kết quả quét.
3. Giải thích khác nhau giữa cách khảo sát TCP, UDP, IPv4 và IPv6, cũng như các giới hạn khi suy luận dịch vụ.
4. Thực hiện một số ví dụ quét **localhost trong môi trường thử nghiệm được kiểm soát** và kiểm tra chéo với trạng thái dịch vụ cục bộ.
5. Đọc kết quả từ góc nhìn của firewall, NAT, VPN, VLAN, cloud security group và IDS/IPS.
6. Chuyển kết quả quét thành nhận định bề mặt tấn công và đề xuất giảm tiếp xúc dịch vụ, giám sát phù hợp.

## 2. Port là gì và vì sao cần khảo sát?

### 2.1. Cổng giao vận khác với cổng vật lý

Trong TCP/IP, **port** là số 16 bit dùng để phân biệt các điểm giao tiếp của giao thức TCP hoặc UDP trên một địa chỉ IP. Dải biểu diễn là **0–65535**; port 0 được dành riêng và không dùng như cổng dịch vụ thông thường. Trong hoạt động vận hành, các dịch vụ thường sử dụng cổng từ 1 đến 65535.

Một phiên giao tiếp có thể được nhận diện theo bộ năm: **IP nguồn, port nguồn, IP đích, port đích, giao thức vận chuyển**. Với TCP và UDP, số port trùng nhau nhưng thuộc hai không gian giao thức khác nhau; **TCP/53 và UDP/53 là hai đích khác nhau**.

~~~text
Client 192.0.2.10:51432 -- TCP --> Server 192.0.2.20:443
   IP nguồn       port nguồn          IP đích       port đích

Cổng vật lý switch: lỗ cắm/cổng uplink trên thiết bị mạng.
Cổng TCP/UDP: định danh logic cho quá trình giao tiếp của phần mềm.
~~~

Một ứng dụng có thể **lắng nghe (listen/bind)** trên một địa chỉ cụ thể như 127.0.0.1, trên một IP của máy hoặc trên mọi địa chỉ phù hợp. Vì vậy cùng port 8080 có thể truy cập từ chính máy nhưng không truy cập được từ máy khác.

Một máy có thể có nhiều IP, nhiều giao diện mạng, nhiều namespace/container và chính sách firewall khác nhau. Phát hiện port mở trên một IP **không đồng nghĩa** port đó mở trên tất cả IP của máy.

### 2.2. Số cổng chỉ gợi ý loại dịch vụ

| Port thường gặp | Giao thức | Dịch vụ liên quan | Lưu ý |
|---|---|---|---|
| 22 | TCP | SSH | Có thể đổi port; cần xác thực và giới hạn quản trị |
| 53 | UDP/TCP | DNS | DNS dùng cả UDP và TCP; còn DoT/DoH trên cổng khác |
| 80 | TCP | HTTP | Có thể redirect sang HTTPS hoặc là reverse proxy |
| 123 | UDP | NTP | UDP không có bắt tay như TCP |
| 443 | TCP | HTTPS | Có thể là load balancer, reverse proxy hoặc ứng dụng khác |
| 443 | UDP | QUIC/HTTP/3 | Không suy luận kết quả UDP từ TCP/443 |
| 445 | TCP | SMB | Thường không nên để lộ trực tiếp Internet |
| 3389 | TCP/UDP | RDP tùy cấu hình | Cần giới hạn nguồn truy cập và bảo vệ xác thực |
| 5432 | TCP | PostgreSQL | Port mặc định, nhưng dịch vụ có thể chạy ở port khác |
| 6379 | TCP | Redis | Không nên coi kết quả port mở là chứng minh đã có quyền truy cập dữ liệu |
| 8080, 8443 | TCP | Các dịch vụ web thay thế | Chỉ là quy ước phổ biến, không phải ánh xạ bắt buộc |

IANA phân biệt các nhóm **System/Well-Known Ports (0–1023)**, **User/Registered Ports (1024–49151)** và **Dynamic/Private Ports (49152–65535)**. Việc đăng ký hay quen dùng một port không bắt buộc ứng dụng thực tế phải sử dụng đúng port đó.

**Quy tắc đọc kết quả:** “TCP/443 open” có nghĩa đầu quét có bằng chứng một dịch vụ hoặc thành phần mạng đang chấp nhận kết nối TCP tại địa chỉ/port đó. Nó **chưa chứng minh** đó là HTTPS, chứng chỉ hợp lệ, nội dung website an toàn hay ứng dụng có lỗ hổng.

## 3. Port scanning là một phép đo từ một vị trí

Hình dung sơ đồ sau:

~~~mermaid
flowchart LR
    E[Máy khảo sát ngoài Internet] --> FW[Firewall biên]
    FW --> RP[Reverse proxy TCP/443]
    RP --> APP[Ứng dụng nội bộ TCP/8080]
    APP --> DB[(CSDL TCP/5432)]
    VPN[Máy kiểm tra qua VPN] --> VFW[Policy VPN]
    VFW --> APP
~~~

Một máy ngoài Internet có thể chỉ thấy **443/tcp open**, trong khi người có quyền ở mạng ứng dụng thấy **8080/tcp open**, và chỉ workload được cấp quyền mới thấy **5432/tcp open**.

Port scanning đo **tính tiếp cận tại một thời điểm và một hướng đường đi**:

- **Source/vantage point:** IP nguồn, VLAN, vị trí địa lý hoặc vùng cloud, trạng thái VPN.
- **Destination:** IP đích, họ địa chỉ IPv4/IPv6, giao diện/hostname được phân giải.
- **Transport:** TCP, UDP; các giao thức khác không được suy diễn từ kết quả TCP/UDP.
- **Path:** route, ACL, security group, NAT, proxy, load balancer, host firewall.
- **Time:** trạng thái dịch vụ, rule, scaling, ngưỡng rate limit thay đổi theo thời gian.

Nếu hai nguồn quét nhận kết quả khác nhau, **đó có thể là hệ quả chính xác của chính sách phân đoạn**. Không vội kết luận công cụ sai hay hệ thống có lỗ hổng.

### 3.1. Địa chỉ IP, DNS và mục tiêu quét

Tên miền có thể trỏ đến nhiều IPv4/IPv6, CDN hoặc load balancer; một địa chỉ IP có thể phục vụ nhiều tên miền dựa trên SNI/Host header. Quét một IP không đại diện cho toàn bộ đường truy cập ứng dụng thông qua DNS và reverse proxy.

Trong cloud/Kubernetes, DNS record, IP ảo hoặc load balancer có thể thay đổi. Khi lập báo cáo cần ghi cả hostname được kiểm tra, địa chỉ đã phân giải, thời gian, nguồn quan sát và kiến trúc mạng liên quan.

## 4. Port scanning TCP hoạt động thế nào?

TCP là giao thức có trạng thái thiết lập kết nối. Phép khảo sát thường dựa trên **SYN, SYN-ACK, ACK, RST** và phản hồi lỗi mạng.

### 4.1. Trạng thái TCP khi cổng chấp nhận kết nối

~~~text
Máy kiểm tra                            Dịch vụ TCP lắng nghe
     | ------- SYN ------------------------> |
     | <------ SYN + ACK ------------------- |
     | ------- ACK ------------------------> |
     |              Kết nối TCP được thiết lập
~~~

Một phản hồi **SYN-ACK** từ đúng đích cho thấy cổng có dấu hiệu **open** đối với phép thử SYN. Một công cụ quét TCP connect thường hoàn tất bắt tay thông qua hệ điều hành và có thể đóng kết nối ngay sau đó.

### 4.2. Trạng thái TCP khi cổng từ chối

~~~text
Máy kiểm tra                            Host có TCP stack
     | ------- SYN ------------------------> |
     | <------ RST (thường kèm ACK) -------- |
     |              Kết nối bị từ chối
~~~

Một phản hồi **RST** thích hợp thường khiến công cụ nhận định **closed**: host hoặc một thành phần đại diện cho đích phản hồi rằng không chấp nhận kết nối ở port này. Trạng thái có thể do host, firewall hoặc thiết bị trung gian tạo ra, nên không phải bằng chứng tuyệt đối về tiến trình trên host đích.

### 4.3. Trạng thái khi gói bị lọc hoặc không có phản hồi

~~~text
Máy kiểm tra                            Firewall / đích
     | ------- SYN ------------------------> |    [DROP]
     |                  ...                  |
     | <------ không nhận phản hồi --------- |
~~~

Công cụ có thể kết luận **filtered** nếu không nhận phản hồi sau các lần thử theo chính sách hoặc nhận một số ICMP unreachable biểu thị bị chặn. Tuy nhiên **im lặng** còn có thể do mất gói, nghẽn mạng, rate limit, host down hoặc đường phản hồi không đến được nguồn kiểm tra.

**Quan trọng:** không nhận SYN-ACK không đủ để khẳng định rằng không có dịch vụ đang chạy. Firewall có thể che dịch vụ phía sau.

## 5. Các trạng thái trong Nmap và cách hiểu đúng

Nmap thường dùng sáu nhãn trạng thái cổng. Đây là **suy luận từ các phép thử**, không phải nhãn cố định bên trong hệ điều hành đích.

| Trạng thái Nmap | Ý nghĩa thực dụng | Điều không thể tự kết luận |
|---|---|---|
| **open** | Có dấu hiệu một ứng dụng/thành phần nhận kết nối hoặc datagram ở cổng tương ứng | Dịch vụ có lỗ hổng hay người quét có quyền sử dụng |
| **closed** | Đích có thể truy cập, nhưng cổng không chấp nhận dạng kết nối/gói được thử | Mọi dịch vụ khác đều đóng; firewall không tồn tại |
| **filtered** | Bộ lọc hoặc đường truyền khiến công cụ không thể xác định cổng có mở không | Đích chắc chắn không có tiến trình lắng nghe |
| **unfiltered** | Cổng có thể tiếp cận bằng phép thử nhưng chưa biết mở hay đóng, thường gặp trong ACK scan | Có ứng dụng đang lắng nghe |
| **open|filtered** | Phản hồi không phân biệt được cổng mở với bị lọc; thường gặp khi quét UDP | Dịch vụ chắc chắn mở |
| **closed|filtered** | Phép thử không phân biệt được cổng đóng hay bị lọc trong một số kiểu quét đặc biệt | Đã xác nhận được cấu hình dịch vụ |

Một dòng như **8080/tcp open http-proxy** có hai lớp thông tin: **trạng thái cổng** và **nhãn dịch vụ** dựa trên cơ sở dữ liệu/cách nhận diện. Nhãn dịch vụ có thể sai khi ứng dụng chạy trên port khác thông lệ; nhận diện phiên bản cũng có độ tin cậy và điều kiện riêng.

### 5.1. Bảng tình huống TCP thông dụng

| Tín hiệu từ TCP SYN | Suy luận thường gặp | Những yếu tố phải đối chiếu |
|---|---|---|
| SYN-ACK hợp lệ | open | Load balancer, proxy, SYN proxy hay chính host có thể trả lời |
| RST hợp lệ | closed | Phản hồi có thể được host hoặc firewall tạo |
| Không phản hồi sau retry phù hợp | filtered hoặc không chắc chắn | Drop, host down, mất gói, rate limit, route |
| ICMP loại không thể tới đích do bị chặn | filtered | Loại ICMP, bộ định tuyến/thiết bị trung gian sinh phản hồi |
| Kết nối mở rồi đóng ngay | TCP có thể đã open | Chính sách ứng dụng, TLS, allowlist, mức tải |

**Ví dụ:** nếu 22/tcp là **filtered** từ Internet nhưng **open** qua VPN quản trị thì đó có thể là kết quả mong muốn của kiến trúc bảo mật. Cần xác minh đường VPN và phân quyền mới kết luận kiểm soát được triển khai hiệu quả.

## 6. Các cách khảo sát cổng phổ biến

### 6.1. TCP connect scan

Công cụ dùng giao diện kết nối TCP của hệ điều hành để thử thiết lập phiên. Trong Nmap, thường được gọi là **-sT**.

- **Ưu điểm:** phù hợp môi trường không có đặc quyền raw socket; cơ chế đơn giản, dễ giải thích và đối chiếu.
- **Giới hạn:** có thể tạo kết nối hoàn chỉnh tới dịch vụ, dẫn đến log kết nối, sử dụng tài nguyên ứng dụng hoặc kích hoạt một số chính sách bảo vệ.
- **Khi dùng:** khảo sát đã được cho phép, kiểm tra một tập cổng nhỏ trong lab hoặc kiểm tra điểm tiếp cận hợp lệ.

### 6.2. TCP SYN scan

Công cụ phát TCP SYN và phân tích SYN-ACK, RST hoặc thiếu phản hồi mà không nhất thiết hoàn thành một phiên TCP ứng dụng. Trong Nmap thường là **-sS**.

- **Ưu điểm:** cho phép đánh giá trạng thái TCP từ dấu hiệu bắt tay ban đầu.
- **Giới hạn:** thường cần quyền gửi/nhận raw packets; hệ thống, firewall và IDS vẫn có thể ghi nhận hoặc cảnh báo; SYN proxy, packet loss và chính sách thiết bị trung gian có thể làm thay đổi kết quả.
- **Lưu ý:** cụm từ “half-open” mô tả phương thức bắt tay; **không có nghĩa là vô hình đối với hệ thống giám sát**.

### 6.3. UDP scan

UDP không có quá trình bắt tay thiết lập phiên như TCP. Công cụ phải dựa vào phản hồi ứng dụng hoặc thông báo lỗi mạng:

- Nhận phản hồi UDP hợp lệ từ dịch vụ → có cơ sở kết luận **open**.
- Nhận ICMP Destination Unreachable, **Port Unreachable** (IPv4 Type 3 Code 3) từ đích trong điều kiện phù hợp → thường là **closed**.
- Không có phản hồi → có thể là **open|filtered**, vì ứng dụng UDP có thể chỉ trả lời request hợp lệ, firewall có thể drop hoặc ICMP có thể bị giới hạn tốc độ.
- Một số phản hồi lỗi cho biết lọc mạng → có thể là **filtered**, tùy mã ICMP và phép thử.

Chính vì cơ chế này, scan UDP có thể **chậm** và khó kết luận hơn TCP. Những dịch vụ như DNS, NTP và QUIC có thể yêu cầu đúng định dạng thông điệp để trả lời. Không nên suy luận UDP/443 đóng hay mở chỉ từ kết quả TCP/443.

### 6.4. ACK scan và kiểm tra bộ lọc

Một phép khảo sát TCP ACK có thể giúp suy luận về việc gói tin có đi qua một số bộ lọc hay không, nhưng **không trực tiếp xác định port đang open**. Chẳng hạn kết quả **unfiltered** không đồng nghĩa “dịch vụ đang lắng nghe”. Một firewall stateful có thể xử lý gói ACK không thuộc kết nối đã thiết lập theo cách khác nhau, ảnh hưởng đến khả năng suy luận.

Vì vậy phải phân biệt **port/service inventory scan** với **phép thử đường đi hoặc chính sách lọc gói**. Chúng trả lời các câu hỏi khác nhau.

### 6.5. Service discovery và kiểm tra phiên bản

Sau khi biết cổng có thể tiếp cận, công cụ có thể gửi yêu cầu ứng dụng để cố gắng nhận diện giao thức, banner hoặc phiên bản (ví dụ chế độ **-sV** của Nmap).

Điều này bổ sung thông tin nhưng không đảm bảo:

- Banner có thể bị thay đổi, bị ẩn hoặc do reverse proxy trả lời.
- Hai ứng dụng có thể sử dụng cùng một port và một ứng dụng có thể chạy trên port không mặc định.
- TLS khiến việc đọc trực tiếp nội dung ứng dụng cần thêm bước bắt tay phù hợp.
- Phiên bản hiển thị có thể không phản ánh đầy đủ các bản vá đã được backport.
- Phát hiện phiên bản **không tương đương** xác nhận lỗ hổng có thể khai thác.

Trên môi trường sản xuất nhạy cảm, việc gửi probe nhận diện dịch vụ cần có giới hạn riêng vì có thể tạo nhiều yêu cầu hơn một lần kiểm tra kết nối cơ bản.

## 7. Xác định phạm vi trước khi quét

Với mục đích kiểm kê hoặc kiểm chứng bảo mật, trước khi thực hiện bất kỳ lệnh chủ động nào cần chốt phạm vi bằng văn bản hoặc thỏa thuận vận hành tương đương:

| Thành phần phạm vi | Câu hỏi cần xác nhận |
|---|---|
| **Tài sản** | IP, hostname, CIDR, endpoint, môi trường lab/staging hay production nào thuộc quyền đánh giá? |
| **Quyền kiểm tra** | Ai sở hữu tài sản, ai cho phép và hình thức đánh giá nào được chấp thuận? |
| **Giao thức/cổng** | TCP/UDP, tập cổng nào cần kiểm tra; có cần IPv6 không? |
| **Nguồn quét** | IP nguồn, VLAN, VPN hoặc mạng cloud nào là điểm quan sát phù hợp? |
| **Thời gian/tần suất** | Khi nào được phép, giới hạn tốc độ và số phiên là bao nhiêu? |
| **Vùng tránh tác động** | Hệ thống OT/ICS, máy y tế, thiết bị cũ, dịch vụ có giới hạn kết nối hay không? |
| **Dữ liệu và log** | Lưu kết quả ở đâu, ai được xem, cần loại bỏ địa chỉ nhạy cảm nào? |
| **Phương án dừng/ứng phó** | Ai giám sát, ngưỡng bất thường nào buộc dừng việc kiểm tra? |

Một lần quét có thể sinh lưu lượng bị IDS/IPS coi là bất thường, làm đầy log, kích hoạt chặn tự động hoặc chiếm tài nguyên của dịch vụ cũ. Phạm vi nhỏ và cách kiểm tra có kiểm soát thường cho **kết quả hữu ích hơn** quét rộng mà không biết mình đang đo gì.

## 8. Thực hành an toàn trên localhost

Phần này sử dụng **127.0.0.1** (IPv4 loopback). Mọi lệnh Nmap minh họa đều nhắm chính thiết bị đang chạy lab. Không thay địa chỉ bằng tài sản của người khác nếu chưa được cho phép. Các ví dụ giả sử đã cài **Python 3** và **Nmap**; đây là hướng dẫn thực hành để người học tự chạy trong lab, không phải thao tác đã thực hiện trong bài.

### 8.1. Tạo một dịch vụ HTTP thử nghiệm

Mở terminal thứ nhất:

~~~bash
python3 -m http.server 8080 --bind 127.0.0.1
~~~

Trên Windows, lệnh tương đương có thể là:

~~~powershell
py -3 -m http.server 8080 --bind 127.0.0.1
~~~

Dịch vụ chỉ bind vào loopback, phục vụ qua HTTP/TCP cổng **8080**. Nên chạy trong một thư mục thử nghiệm không chứa dữ liệu bí mật, vì HTTP server đơn giản có thể cung cấp tệp trong thư mục đang đứng cho client truy cập. Dừng bằng **Ctrl+C** khi thực hành xong.

### 8.2. Kiểm tra cổng TCP bằng Nmap

Mở terminal thứ hai:

~~~bash
# Kiểm tra đúng hai cổng trên máy cục bộ
nmap -sT -p 8080,8081 127.0.0.1
~~~

Kết quả **minh họa**, sẽ thay đổi theo dịch vụ, hệ điều hành, firewall và điều kiện lab:

~~~text
PORT     STATE  SERVICE
8080/tcp open   http-proxy
8081/tcp closed blackice-icecap
~~~

Những nhãn ở cột **SERVICE** trong dạng output cơ bản thường xuất phát từ cơ sở dữ liệu port→service, **không nhất thiết do xác nhận giao thức thực tế**. Ở lab này, ta biết **8080 là HTTP server** từ lệnh đã khởi chạy; cột trạng thái **open** chỉ ra cổng chấp nhận kết nối từ localhost. Nếu port 8081 đã được ứng dụng khác sử dụng, nó sẽ không còn đóng.

Có thể yêu cầu nhận diện dịch vụ cho cổng 8080:

~~~bash
# Chỉ yêu cầu thêm nhận diện trên một cổng lab
nmap -sT -sV -p 8080 127.0.0.1
~~~

Nhận diện thêm có thể trả về thông tin về HTTP hoặc Python server, nhưng độ chính xác tùy phiên bản, phản hồi dịch vụ và phiên bản Nmap.

### 8.3. Kiểm tra chéo trạng thái lắng nghe trên máy

Trên Linux:

~~~bash
# Xem TCP listening sockets, kiểm tra cột Local Address
ss -lnt

# Lọc các dòng chứa cổng 8080 nếu cần
ss -lnt | grep ':8080'
~~~

Trên Windows PowerShell:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
  Format-Table LocalAddress, LocalPort, State, OwningProcess
~~~

**So sánh hai góc nhìn:**

- **Local listener:** tiến trình bind địa chỉ nào, port nào.
- **Remote scan:** từ một nguồn cụ thể có kết nối được tới địa chỉ/port đó hay không.

Một listener bind **127.0.0.1:8080** thường không thể được truy cập từ một máy khác qua IP LAN của máy chủ. Muốn kiểm tra kiểm soát trên đường mạng thật, cần một lab nhiều máy hoặc mạng ảo riêng đã được phê duyệt, có sơ đồ đường đi và rule rõ ràng.

### 8.4. Kiểm tra UDP ở phạm vi nhỏ

UDP cần diễn giải thận trọng hơn; một ví dụ quan sát trên localhost:

~~~bash
# Một cổng UDP cụ thể trên chính máy lab
nmap -sU -p 5353 127.0.0.1
~~~

Trạng thái có thể là **closed**, **open** hoặc **open|filtered** tùy ứng dụng và phản hồi của hệ điều hành. Nếu cổng UDP chưa có dịch vụ trả lời, đừng coi không phản hồi là bằng chứng có dịch vụ. Chỉ dùng các đầu dò chuyên biệt khi hiểu rõ giao thức và có quyền thử nghiệm.

### 8.5. IPv6 là không gian cần kiểm tra riêng

Nếu hệ điều hành và Nmap hỗ trợ IPv6 loopback:

~~~bash
nmap -6 -sT -p 8080,8081 ::1
~~~

Vì server ở bước 8.1 chỉ bind **127.0.0.1** (IPv4), nên **::1:8080** có thể không mở, dù **127.0.0.1:8080** đang open. Đây là ví dụ thực tế cho thấy **IPv4 và IPv6 không luôn có cùng listener hoặc cùng chính sách**.

Nếu máy không hỗ trợ IPv6 hoặc thiếu route phù hợp, kết quả có thể là lỗi không kết nối thay vì trạng thái port.

## 9. Phân tích packet và log để hiểu kết quả

Có thể quan sát lưu lượng của lab bằng công cụ bắt gói được hệ điều hành hỗ trợ. Trên Linux, với quyền phù hợp và giao diện loopback là **lo**:

~~~bash
# Quan sát lưu lượng TCP lab trên loopback
sudo tcpdump -i lo -nn 'tcp port 8080 or tcp port 8081'
~~~

Đây là lệnh **quan sát**; công cụ có thể cần quyền quản trị mạng. Trên một số nền tảng, tên giao diện loopback hoặc khả năng capture loopback khác nhau. Mục đích là đối chiếu:

- **SYN → SYN-ACK → ACK:** kết nối TCP được thiết lập.
- **SYN → RST:** cổng từ chối.
- **SYN không có phản hồi:** kiểm tra tiếp firewall, route, điểm đo và packet loss; chưa đủ cơ sở khẳng định lỗi nằm ở server.

Bộ lọc hiển thị Wireshark thường dùng:

| Display filter | Ý nghĩa quan sát |
|---|---|
| **tcp.port == 8080** | Traffic TCP có một đầu dùng port 8080 |
| **tcp.flags.syn == 1 && tcp.flags.ack == 0** | Các gói SYN mở đầu thường gặp |
| **tcp.flags.reset == 1** | Các gói TCP có cờ RST |
| **udp.port == 5353** | Traffic UDP tương ứng |
| **icmp || icmpv6** | Một số thông báo lỗi mạng/trạng thái đường đi |
| **ip.addr == 127.0.0.1** | Lọc lưu lượng IPv4 loopback trong file capture hỗ trợ |

**Giới hạn capture:** packet có thể bị bỏ qua bởi driver/offloading, không có gói do chọn sai interface, hoặc firewall chặn ở nơi khác trước khi gói đến máy. Trên switched Ethernet, một thiết bị bình thường không tự nhìn thấy toàn bộ unicast giữa các cổng khác; cần cấu hình SPAN/mirror/tap được phép nếu muốn quan sát ở vị trí đó.

## 10. Vì sao cùng một cổng cho kết quả khác nhau?

### 10.1. Host firewall so với network firewall

**Host firewall** chạy trên máy nhận và **network firewall** nằm trên đường truyền có thể áp các chính sách khác nhau. Dịch vụ vẫn có thể lắng nghe khi network scan trả **filtered**.

Ví dụ:

~~~text
Máy quản trị qua VPN -- allow TCP/22 --> Firewall --> Server SSH:22
Máy ngoài Internet -- deny TCP/22 --> Firewall --> Server SSH:22

SSH listener trên server: hoạt động.
Đầu quét Internet: có thể thấy filtered.
Đầu quét VPN: có thể thấy open.
~~~

Khi kiểm tra phải ghi cả rule mạng, rule host, trạng thái tiến trình và source IP thực tế.

### 10.2. NAT, reverse proxy và load balancer

Một địa chỉ public có thể được NAT hoặc proxy sang dịch vụ khác. Port trả lời đôi khi thuộc **load balancer hoặc reverse proxy**, không phải ứng dụng cuối. Dịch vụ public ở TCP/443 có thể chuyển tiếp tới các backend TCP/8080 hoặc TCP/8443 mà nguồn Internet không thể kết nối trực tiếp.

Đối với NAT có trạng thái, chiều đi, mapping và port forwarding quyết định reachability. Không được suy ra kết quả từ bên trong chỉ dựa vào quét địa chỉ public; một số thiết bị không hỗ trợ hoặc giới hạn NAT hairpin.

### 10.3. ACL theo nguồn, thời điểm hoặc danh tính

Firewall có thể lọc theo nguồn, vùng mạng, kết nối đã thiết lập, thời gian hoặc trạng thái xác thực. Một số dịch vụ chỉ mở sau khi kết nối VPN, cấp role, kiểm tra thiết bị hoặc thay đổi policy.

**Kết quả từ đúng một địa chỉ nguồn không phải chứng minh quy tắc áp dụng cho mọi nguồn.**

### 10.4. Dịch vụ biến động và giới hạn tài nguyên

Trong auto-scaling, container, Kubernetes hoặc hệ thống có failover, backend có thể biến mất hoặc thay đổi trạng thái. Dịch vụ đang quá tải, rate-limit hoặc gặp mất gói cũng có thể làm sai lệch suy luận.

Khi có kết quả mâu thuẫn, nên xác minh bằng **log, routing, firewall policy, địa chỉ đích và trạng thái listener tại cùng thời điểm**, thay vì tăng ngay tốc độ quét.

### 10.5. IPv4 và IPv6

Một dịch vụ có thể lắng nghe trên **0.0.0.0**, **127.0.0.1**, một IP IPv4 cụ thể, **::**, **::1** hoặc một IPv6 cụ thể. Tác động của chế độ dual-stack đối với listener IPv6 tùy hệ điều hành và cấu hình socket. Firewall và route IPv6 cũng có thể độc lập với IPv4.

Khi threat modeling, việc “không thấy port từ IPv4” không đủ để kết luận host không công khai dịch vụ đó qua IPv6.

## 11. Quy trình khảo sát cổng để kiểm chứng an ninh

Một quy trình vận hành đề xuất cho đội quản trị:

### Bước 1 — Xác định câu hỏi

Đặt câu hỏi cụ thể thay vì “scan xem có gì”:

- Dịch vụ quản trị SSH có bị lộ từ mạng khách không?
- DNS nội bộ chỉ nhận UDP/TCP 53 từ subnet được cấp quyền không?
- Sau khi cập nhật firewall, kết nối từ Internet đến cổng database đã bị chặn chưa?
- Có cổng TCP/UDP mới phát sinh trên server sau một lần triển khai không?

### Bước 2 — Thu thập sơ đồ và chính sách dự kiến

Ghi bảng tài sản: hostname, IP, chủ sở hữu, vai trò server, dịch vụ dự kiến, subnet/VLAN, zone, firewall/security group, VPN scope, cả IPv4/IPv6.

Ví dụ một chính sách kỳ vọng cho môi trường giả định:

| Đích | Nguồn kiểm tra | Dịch vụ dự kiến | Kết quả được kỳ vọng |
|---|---|---|---|
| Web frontend | Internet | TCP/443 | open |
| Web frontend | Internet | TCP/22 | filtered hoặc không tiếp cận theo thiết kế |
| Database | Subnet ứng dụng | TCP/5432 | open nếu đúng quyền |
| Database | Mạng khách | TCP/5432 | không truy cập được |
| Server quản trị | VPN quản trị hợp lệ | TCP/22 | open với người có quyền |
| Server quản trị | Internet công cộng | TCP/22 | không truy cập được |

Bảng này chỉ là **ví dụ kiến trúc**, không phải cấu hình đã được xác minh. Hãy bổ sung địa chỉ IPv6, rule đặc biệt và các luồng chiều ngược theo thực tế.

### Bước 3 — Chọn các cổng và nguồn kiểm tra tối thiểu

Trước tiên thử đúng danh sách dịch vụ cần chứng minh, từ từng vị trí cần xác nhận chính sách. Trong mạng nhạy cảm, phối hợp với vận hành để giới hạn băng thông, số kết nối và thời điểm.

Một bộ kết quả có phạm vi rõ ràng thường hữu ích hơn nhiều lần quét lớn: biết từ Guest VLAN **không tới được TCP/5432**, và từ subnet ứng dụng **tới được TCP/5432**, là bằng chứng trực tiếp cho một đường kiểm soát phân đoạn.

### Bước 4 — Lưu kết quả và bối cảnh

Với mỗi kết quả cần tối thiểu: **thời gian, máy nguồn, đích IP/hostname, giao thức, port, trạng thái, công cụ/phương pháp, thay đổi chính sách gần nhất, bằng chứng hỗ trợ**.

Nên chuẩn hóa bản ghi:

~~~yaml
asset_id: "database-lab"
timestamp: "2026-01-15T10:00:00+07:00" # Thời gian minh họa
source_zone: "test-app-subnet"
source_ip: "192.0.2.10"              # Địa chỉ tài liệu RFC 5737
target_ip: "192.0.2.20"              # Không phải endpoint thực
protocol: "tcp"
port: 5432
observed_state: "open"
expected_state: "open-for-approved-apps"
method: "tcp-connect"
assessment: "Cần đối chiếu rule và quyền xác thực DB"
evidence: "Kết quả kiểm tra được cho phép và log tương ứng"
confidence: "observed-once"
~~~

Các địa chỉ **192.0.2.0/24, 198.51.100.0/24 và 203.0.113.0/24** được dành cho tài liệu minh họa; không dùng để tìm tài sản hoạt động trên Internet.

### Bước 5 — Xác minh các kết quả bất ngờ

Nếu một port **open** nhưng không được kỳ vọng:

1. Xác nhận đúng IP, giao thức, VLAN/route và thời điểm.
2. Kiểm tra listener tại host, binding IP, tiến trình, container hoặc load balancer tương ứng.
3. Đối chiếu firewall, NAT, security group, ACL và log cho cùng luồng.
4. Xem dịch vụ có được phê duyệt và đã cấu hình xác thực/mã hóa, hạn chế nguồn hay chưa.
5. Ghi nhận chủ sở hữu, mức tác động và thay đổi cần thực hiện; kiểm chứng lại sau khi sửa.

Nếu port **filtered** khác dự kiến **open**, ưu tiên kiểm tra sự cố đường đi, trạng thái dịch vụ, DNS, routing, policy, packet loss và các điểm NAT/proxy trước khi khẳng định firewall “đang chặn đúng”.

### Bước 6 — Đánh giá mức rủi ro, không chỉ đếm cổng

**Số cổng open không phải thước đo rủi ro duy nhất.** Một ứng dụng công khai TCP/443 được harden, xác thực tốt và cập nhật có thể chấp nhận được; một cổng quản trị hoặc database mở ngoài dự kiến có thể là vấn đề nghiêm trọng dù chỉ là **một** cổng.

Đánh giá theo: độ nhạy tài sản, mức độ tiếp cận, xác thực/ủy quyền, mã hóa, cấu hình, phiên bản và bản vá, mức tác động khi bị chiếm, giám sát, khả năng ứng phó và mức chắc chắn của bằng chứng.

## 12. Port scanning trong threat modeling và kiến trúc nhiều lớp

Đặt năng lực adversary vào đúng vị trí:

| Hồ sơ adversary | Năng lực khảo sát | Điều chưa thể suy ra |
|---|---|---|
| Người từ Internet | Thử kết nối tới các dịch vụ public và ghi nhận phản hồi của chính mình | Thấy được các port chỉ mở trong VLAN nhân viên |
| Thiết bị trên guest Wi-Fi | Kiểm tra những đích mạng mà guest policy cho phép tiếp cận | Có thể tự vượt VLAN hoặc đọc dữ liệu HTTPS |
| Tài khoản VPN thông thường | Quan sát những dịch vụ được VPN ACL cho truy cập | Có quyền quản trị hoặc truy cập mọi subnet |
| Một host ở subnet ứng dụng | Thử các cổng DB/API reachable từ host đó | Có credential DB hoặc quyền sửa dữ liệu |
| Chủ thể có quyền đổi firewall rule/cloud policy | Có thể tác động tới reachability nếu quyền được cấp phù hợp | Có quyền độc lập đọc secret, chiếm workload hoặc giải mã mọi traffic |

Port scanning là một **nguồn bằng chứng về đường tấn công**: đích có thể được tiếp cận qua TCP/UDP nào? Nhưng một đường khai thác thực tế còn phụ thuộc ứng dụng, credential, cấu hình, lỗ hổng, kiểm soát bảo mật và điều kiện vận hành.

~~~mermaid
flowchart TD
    A[Adversary ở nguồn S] --> B{Có đường IP tới đích T?}
    B -->|Không| Z[Không thể đánh giá port theo đường này]
    B -->|Có| C{Firewall / ACL cho phép thử port P?}
    C -->|Không hoặc không rõ| D[Filtered / cần xác minh đường đi]
    C -->|Có| E{TCP/UDP có phản hồi phù hợp?}
    E -->|Có| F[Open hoặc Closed tùy giao thức & phản hồi]
    E -->|Không| G[Filtered hoặc Open|Filtered tùy phép thử]
    F --> H[Đánh giá xác thực, mã hóa và quyền ứng dụng]
    G --> I[Đối chiếu log, policy, listener và packet loss]
~~~

Sơ đồ nhằm giúp **suy luận**, không phải thuật toán luôn trả trạng thái duy nhất: cách phần mềm quét xử lý timeout, retry và phản hồi khác nhau có thể cho nhãn khác nhau.

## 13. Phát hiện hoạt động quét bằng giám sát mạng

Quét cổng thường tạo ra mẫu truy cập khác hành vi ứng dụng bình thường. Đội phòng thủ có thể quan sát qua firewall, IDS/IPS, flow logs, hệ thống quản lý endpoint và log dịch vụ.

### 13.1. Dấu hiệu có thể gặp

| Dấu hiệu | Diễn giải có thể | Giới hạn |
|---|---|---|
| Một nguồn thử **nhiều port trên một đích** trong thời gian ngắn | Khảo sát chiều sâu một host | Có thể là kiểm tra tài sản được phê duyệt hoặc hệ thống monitoring |
| Một nguồn thử **cùng port trên nhiều đích** | Kiểm kê một loại dịch vụ trên nhiều host | Cũng có thể do health check hoặc ứng dụng hợp lệ |
| Nhiều SYN không hoàn tất thành kết nối | Có thể là probe, lỗi kết nối, congestion hoặc SYN scan | Không đủ một mình để kết luận đối thủ |
| Tỷ lệ RST/ICMP Port Unreachable tăng | Nhiều kết nối bị từ chối/cổng không có listener | Có thể do deployment hoặc cấu hình service discovery sai |
| Nhiều firewall deny theo dải port hoặc đích | Luồng bị rule loại bỏ, có khả năng liên quan khảo sát | Các ứng dụng tự thử lại cũng có thể gây hiện tượng tương tự |
| Service banner requests không theo hành vi người dùng | Hoạt động nhận diện dịch vụ hoặc kiểm tra sức khỏe | Cần ngữ cảnh, nhãn thời gian và nguồn được cấp phép |

Hệ thống IDS/IPS như Suricata hoặc Snort có thể có rule phát hiện tín hiệu quét; phân tích kết nối như Zeek, NetFlow/IPFIX và firewall logs giúp dựng hành vi theo thời gian. **IDS phát hiện không đồng nghĩa IPS đã chặn**, và quan sát chỉ đầy đủ tại các điểm thu thập có khả năng thấy traffic liên quan.

### 13.2. Tương quan thay vì chỉ đếm gói

Một cảnh báo đáng tin hơn khi kết hợp:

1. **Nguồn:** IP nào, thuộc VLAN/VPN/role nào, có phải công cụ quét được cho phép?
2. **Đích:** có bao nhiêu host, có chạm hệ thống nhạy cảm hay vùng quản trị?
3. **Phân bố port:** cùng một cổng trên nhiều host hay nhiều cổng trên một host?
4. **Khoảng thời gian:** tốc độ, số lần retry, sự thay đổi theo thời điểm.
5. **Kết quả:** mức TCP RST, connection success, ICMP error và firewall deny.
6. **Bằng chứng khác:** log 802.1X/NAC, DNS, VPN, workload, thay đổi firewall và ticket vận hành.

Một địa chỉ IP nguồn có thể là NAT gateway của nhiều thiết bị, khiến hành vi nhiều client bị tổng hợp; cũng có thể là máy kiểm tra nội bộ được phân quyền. Không nên tự động quy mọi mẫu quét là tấn công khi thiếu ngữ cảnh.

### 13.3. Ví dụ quy tắc phát hiện khái niệm

Để giảm nhiễu, quy tắc nội bộ có thể tìm **một nguồn kết nối đến số lượng port đích khác nhau vượt ngưỡng trên cùng host trong một khoảng thời gian ngắn**, đồng thời loại trừ những máy quét tài sản được quản lý và những endpoint có workload tự động đặc thù.

Ngưỡng cụ thể cần được hiệu chỉnh từ baseline của tổ chức: mạng phát triển phần mềm có hành vi khác mạng OT, máy quản lý giám sát khác máy nhân viên. Ghi rõ thời gian, ngoại lệ, người duyệt và chính sách lưu log.

## 14. Biện pháp giảm bề mặt lộ diện

Port scanning không phải vấn đề cần “vô hiệu hóa hoàn toàn”; điều quan trọng là **chỉ các dịch vụ cần thiết mới tiếp cận được từ những nguồn phù hợp**.

### 14.1. Kiểm soát phía host

- Gỡ hoặc tắt listener không cần thiết; quản lý service và cấu hình bind IP đúng.
- Không xuất bản giao diện quản trị, debug, metrics hoặc database ra Internet khi không có nhu cầu.
- Dùng host firewall theo nguyên tắc quyền tối thiểu, kiểm tra cả IPv4 và IPv6.
- Áp xác thực mạnh, TLS/mTLS khi cần, cập nhật phần mềm và chính sách secret phù hợp.
- Ghi log truy cập và thay đổi cấu hình; không coi việc ẩn banner hay đổi port là biện pháp xác thực.

### 14.2. Kiểm soát ở mạng

- **Firewall/ACL:** giới hạn nguồn–đích–protocol–port theo use case; không cho phép toàn bộ vì thuận tiện.
- **Phân đoạn VLAN/subnet:** tách user, guest, server, database, quản trị; cấu hình chính sách liên vùng.
- **VPN/ZTNA:** chỉ mở đường tới các tài nguyên cần cho vai trò đã xác thực và được phép.
- **IDS/IPS:** quan sát/giới hạn hành vi bất thường tại các ranh giới có hiệu lực.
- **NAT và reverse proxy:** có thể giảm lộ diện backend nhưng cần đảm bảo không có đường vòng hoặc public interface ngoài dự kiến.
- **Quản lý cổng vật lý/Wi-Fi:** 802.1X, NAC, guest isolation để giới hạn thiết bị được tham gia các vùng có quyền cao.
- **Quản trị DNS:** DNS không chứng minh port mở, nhưng kiểm soát record và log giúp phát hiện dịch vụ public hoặc endpoint mới.

Một rule **deny** trên firewall ngoài không giúp ngăn host trong cùng VLAN truy cập dịch vụ trực tiếp, nếu traffic đó không đi qua firewall. Vì vậy phải biết vị trí thực thi chính sách.

### 14.3. Đối với cloud và Kubernetes

- Kiểm tra **security group, network ACL, route, public IP, Internet gateway, load balancer listener** và policy ở host.
- Không mặc định “private subnet” là đủ an toàn nếu tồn tại VPN, peering, Transit Gateway, private endpoint hoặc quyền cloud control plane rộng.
- Với container và Kubernetes, xem port do container listen, Service/Ingress/Gateway/NodePort và chính sách NetworkPolicy thực tế; việc một ứng dụng expose port nội bộ không nhất thiết đồng nghĩa public Internet.
- Cloud firewall có thể có rule stateful hoặc stateless; cần biết cách phản hồi được cho phép trên đường tương ứng.
- Giám sát cấu hình thay đổi, nhất là các cổng quản trị/database được tạo bởi deployment tự động.

**Kết quả cần đạt:** danh mục dịch vụ được phê duyệt, đường kết nối hợp lệ, chính sách tối thiểu, bằng chứng kiểm thử từ các vùng quan sát và cơ chế theo dõi thay đổi.

## 15. Giới hạn và những sai lầm thường gặp

### 15.1. “Closed” không đồng nghĩa an toàn

Một port **closed** thường không nhận kết nối tại thời điểm/quy mô kiểm tra. Các dịch vụ ở port khác, dịch vụ chỉ xuất hiện theo thời điểm hoặc lỗi bảo mật không liên quan mạng vẫn tồn tại. Hơn nữa, trạng thái từ một nguồn chưa thể đại diện toàn bộ mạng.

### 15.2. “Open” không đồng nghĩa có lỗ hổng

Port open có thể là dịch vụ cần thiết đã được harden và được phép công khai. Đánh giá lỗ hổng đòi hỏi thông tin phiên bản, cấu hình, xác thực và bằng chứng kỹ thuật phù hợp; port scanning đơn lẻ là **thu thập thông tin**, không phải kiểm chứng khai thác.

### 15.3. “Không có phản hồi” không đồng nghĩa filtered tuyệt đối

Timeout có thể do mất kết nối, firewall drop, dịch vụ quá tải hoặc bản chất UDP. Nmap dùng cơ chế thử lại và quy tắc phân loại; độ tin cậy cần kết hợp telemetry tại các điểm mạng.

### 15.4. Mở một cổng không chứng minh ứng dụng đích

TCP/443 có thể do reverse proxy trả SYN-ACK nhưng backend thực tế đang lỗi. Ngược lại, ứng dụng có thể chạy trên port không mặc định, dùng UNIX domain socket hoặc chỉ tiếp cận từ loopback.

### 15.5. Quét ngoài Internet không phản ánh nội bộ

Một port filtered bên ngoài có thể open với host ở VLAN ứng dụng; mạng guest, VPN và site-to-site khác nhau có thể thấy tập dịch vụ khác nhau. Kết luận đúng phải gắn với **điểm nhìn cụ thể**.

### 15.6. Chỉ quét TCP dễ bỏ sót UDP và IPv6

DNS, NTP, QUIC và nhiều giao thức khác dùng UDP. Một chính sách IPv4 có thể không áp dụng tương ứng với IPv6. Phạm vi kiểm tra phải khớp với tài sản và luồng mạng thật.

### 15.7. Tăng tốc độ không luôn tăng giá trị

Quét dồn dập có thể làm đầy log, bị rate limit, gây cảnh báo hoặc ảnh hưởng dịch vụ. Đặc biệt với thiết bị mạng cũ, OT hoặc sản phẩm giới hạn tài nguyên, cần phối hợp để giới hạn và theo dõi tác động.

## 16. Bài tập phân tích tình huống

### Tình huống A — SSH từ hai điểm nhìn

Từ Internet, quản trị viên thấy **22/tcp filtered**. Sau khi kết nối VPN được cấp quyền, cùng đích báo **22/tcp open**.

**Câu hỏi:** kết quả có mâu thuẫn không; cần thêm bằng chứng gì?

**Gợi ý:** không nhất thiết mâu thuẫn. VPN và firewall có thể cho phép TCP/22 chỉ từ subnet quản trị. Cần xác nhận địa chỉ đích, quyền VPN, rule theo nguồn, log firewall, trạng thái SSH listener và cả đường IPv6 nếu dùng. Không suy luận rằng port filtered nghĩa là SSH đã tắt.

### Tình huống B — UDP/53 im lặng

Kết quả khảo sát **53/udp open|filtered** từ một máy khách; trong khi kiểm tra dịch vụ DNS trên máy chủ cho thấy DNS server đang chạy.

**Câu hỏi:** có thể kết luận DNS nhận truy vấn từ máy khách không?

**Gợi ý:** chưa. Có thể công cụ gửi probe không phù hợp, thiết bị chỉ phản hồi với subnet được phép, ICMP bị rate limit hoặc firewall drop. Nên đối chiếu bằng một phép kiểm tra truy vấn DNS hợp lệ đã được cấp phép, log resolver và firewall; phân biệt listener nội bộ với tính tiếp cận từ máy khách.

### Tình huống C — Database private có port open

Từ một máy ứng dụng, **5432/tcp open** trên database. Từ máy ngoài Internet, **5432/tcp filtered**.

**Câu hỏi:** có cần đóng cổng database không?

**Gợi ý:** có thể đây là thiết kế đúng: ứng dụng cần kết nối DB còn Internet không được truy cập. Đánh giá tiếp network policy, authentication, encryption, quyền DB của workload và các đường thay thế. Không nên đóng port phục vụ nghiệp vụ nếu không có yêu cầu thay đổi thiết kế.

### Tình huống D — Dịch vụ HTTP ở cổng 8080

Máy lab chạy HTTP server trên **127.0.0.1:8080**. Local scan trả **open**, máy khác trong cùng LAN không thể truy cập **IP-LAN:8080**.

**Câu hỏi:** vì sao?

**Gợi ý:** listener bind vào IPv4 loopback; IP-LAN là địa chỉ khác. Kiểm tra địa chỉ bind, host firewall và route. Kết quả local quét loopback không dự đoán được khả năng truy cập từ máy khác.

### Tình huống E — IDS báo nhiều cổng bị thử

IDS ghi một nguồn thử 15 cổng của server quản trị trong một phút. Nguồn là máy scanner định kỳ theo lịch đã được phê duyệt.

**Câu hỏi:** nên xử lý cảnh báo thế nào?

**Gợi ý:** xác nhận lịch quét, scope, danh tính máy kiểm tra, ticket thay đổi và loại lưu lượng; ghi kết luận có căn cứ. Không gắn nhãn “tấn công” chỉ vì thấy nhiều cổng; cũng không nên bỏ qua mọi sự kiện từ máy scanner nếu có bất thường về đích, tần suất hoặc credential.

## 17. Checklist kiểm kê và kiểm chứng cổng

- [ ] Đã có quyền đánh giá, phạm vi tài sản, thời gian và giới hạn tác động.
- [ ] Đã phân biệt **port TCP**, **port UDP** và cổng vật lý.
- [ ] Đã ghi **nguồn quan sát**, địa chỉ đích và thời điểm quét.
- [ ] Đã xác định port cần khảo sát theo dịch vụ/nghiệp vụ.
- [ ] Đã cân nhắc cả IPv4 và IPv6, DNS và địa chỉ sau phân giải.
- [ ] Đã hiểu ý nghĩa các trạng thái **open, closed, filtered, unfiltered, open|filtered, closed|filtered**.
- [ ] Đã kiểm tra chéo kết quả bất thường với listener, firewall, NAT, route, proxy và log.
- [ ] Đã ghi nhận chính sách VLAN/VPN/cloud áp dụng cho từng luồng.
- [ ] Đã phân biệt **tính tiếp cận của cổng** với **xác thực, quyền truy cập và lỗ hổng**.
- [ ] Đã xem cơ chế phát hiện quét và cách xử lý false positive.
- [ ] Đã xác định cổng bất ngờ nào cần đóng, thu hẹp nguồn hoặc bổ sung bảo vệ.
- [ ] Đã kiểm tra lại sau thay đổi và lưu bằng chứng theo quy trình.

**Kết luận học thuật:** port scanning cung cấp một lát cắt về **dịch vụ có thể tiếp cận từ một điểm mạng**. Giá trị lớn nhất của kỹ thuật không nằm ở số lượng cổng được liệt kê, mà ở việc dùng kết quả để đối chiếu thiết kế phân đoạn, firewall, VPN, cloud policy và tình trạng dịch vụ; từ đó giảm đường tấn công, phát hiện sai lệch và duy trì kiến trúc mạng an toàn.
