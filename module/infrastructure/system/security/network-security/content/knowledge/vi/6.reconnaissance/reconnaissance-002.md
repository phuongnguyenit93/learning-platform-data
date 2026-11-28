# Active scanning: thăm dò chủ động trong reconnaissance mạng

**Active scanning (quét chủ động)** là quá trình gửi gói tin hoặc yêu cầu có chủ đích tới một thiết bị, dịch vụ hay phạm vi mạng rồi phân tích phản hồi để tìm hiểu những gì có thể kết nối và quan sát được. Khác với việc chỉ đọc tài liệu hay thu thập nguồn dữ liệu có sẵn, active scanning **tạo lưu lượng mới** tới mục tiêu và có thể được phát hiện qua firewall, IDS/IPS, nhật ký máy chủ hoặc hệ thống giám sát.

Trong học phần **SECURITY_NETWORK_SECURITY**, hiểu active scanning giúp người học kiểm kê bề mặt tấn công, kiểm tra phân đoạn và quy tắc firewall, đánh giá mức độ lộ diện của dịch vụ, xác minh tín hiệu IDS/IPS và xây dựng kiến trúc mạng an toàn cho môi trường LAN, VPN, Wi-Fi và cloud. Kỹ thuật này có thể được người quản trị dùng để đánh giá hệ thống của mình hoặc bị đối tượng bên ngoài dùng để khảo sát mục tiêu. **Kết quả quét phản ánh những gì quan sát được từ một vị trí và thời điểm cụ thể**, không phải bản kiểm kê tuyệt đối về mọi tài sản hoặc lỗ hổng.

> **Phạm vi thực hành:** Chỉ quét các địa chỉ, dịch vụ và tài khoản trong môi trường phòng lab hoặc hệ thống đã được cấp quyền rõ ràng. Quét chủ động có thể gây tải, kích hoạt cơ chế bảo vệ và ảnh hưởng dịch vụ yếu hoặc thiết bị công nghiệp/IoT; phải xác định phạm vi và giới hạn lưu lượng trước khi triển khai.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **passive reconnaissance** với **active scanning**, và các nhóm host discovery, port scanning, service discovery, kiểm tra cấu hình.
2. Giải thích vai trò của ICMP, TCP, UDP, ARP và IPv6 Neighbor Discovery khi thăm dò sự hiện diện và dịch vụ.
3. Diễn giải các kết quả **open, closed, filtered, open|filtered** mà không đồng nhất chúng với lỗ hổng bảo mật.
4. Mô tả quy trình quét được ủy quyền, có kiểm soát tải và có bằng chứng kiểm chứng.
5. Liên hệ active scanning với firewall, IDS/IPS, phân đoạn mạng, VPN, DNS và các lớp kiểm soát truy cập cloud.

## 2. Active scanning nằm ở đâu trong reconnaissance?

**Reconnaissance** là giai đoạn tìm hiểu mục tiêu, mạng và bề mặt có thể tiếp cận. Có hai nhóm kỹ thuật bổ trợ:

| Tiêu chí | Passive reconnaissance | Active scanning |
|---|---|---|
| Cách thu thập | Đọc nguồn công khai, dữ liệu kiểm kê, tài liệu và log có sẵn, hoặc quan sát lưu lượng đã được phép tiếp cận | Gửi gói thăm dò/yêu cầu tới hệ thống đích và xem phản hồi |
| Tương tác với mục tiêu | Có thể không tạo phiên hay lưu lượng mới tới máy đích | Có tương tác qua mạng với địa chỉ hoặc dịch vụ mục tiêu |
| Ví dụ | Xem sơ đồ mạng nội bộ, bản ghi DNS từ nguồn đã có, CMDB, flow logs | Host discovery, TCP/UDP port scan, truy vấn banner dịch vụ |
| Dấu vết | Thường ít rõ trên chính máy đích; truy cập nguồn dữ liệu vẫn có thể được ghi log | Dễ xuất hiện trong firewall log, NetFlow/IPFIX, web/server log và cảnh báo IDS |
| Độ tin cậy | Có thể thiếu cập nhật hoặc sai nguồn | Quan sát trực tiếp hơn nhưng bị ảnh hưởng bởi điểm quét, lọc gói và thời điểm |
| Rủi ro vận hành | Thường thấp nếu chỉ đọc nguồn được phép | Có thể gây tải, log noise hoặc ảnh hưởng dịch vụ nhạy cảm |

Quét chủ động **không đồng nghĩa với khai thác lỗ hổng**. Phát hiện cổng TCP/443 mở cho thấy có dịch vụ hoặc thiết bị trung gian nhận kết nối tại cổng đó; chưa chứng minh dịch vụ có CVE, thực thi mã được hay rò rỉ dữ liệu. Kiểm tra điểm yếu chuyên sâu cần phạm vi, phương pháp và quyền riêng phù hợp.

Một quy trình sử dụng trong đội an ninh mạng:

~~~text
Phạm vi và quyền kiểm tra
          │
          ▼
Kiểm kê sơ bộ, sơ đồ mạng, giả định
          │
          ▼
Host discovery có giới hạn
          │
          ▼
Port scanning theo danh sách cổng cần kiểm tra
          │
          ▼
Nhận diện dịch vụ và đối chiếu cấu hình
          │
          ▼
Xác minh kết quả bằng log và chủ sở hữu hệ thống
          │
          ▼
Khuyến nghị phòng vệ, ghi nhận thay đổi và quét lại
~~~

## 3. Quét chủ động nhìn thấy gì ở các tầng giao thức?

Một **probe** là gói tin hoặc yêu cầu gửi đi để kiểm tra một giả thuyết. Phản hồi có thể là trả lời thành công, từ chối, báo lỗi hoặc im lặng. Không có phản hồi **không đủ** để kết luận máy đã tắt; có thể do thiết bị lọc gói, định tuyến không đến được, mất gói hoặc giao thức không được hỗ trợ.

| Giao thức / tầng | Ví dụ thăm dò có kiểm soát | Tín hiệu quan sát | Giới hạn |
|---|---|---|---|
| **ARP / L2 IPv4** | Kiểm tra ánh xạ IP–MAC trên liên kết cục bộ | ARP reply, MAC và giao diện liên quan | Không đi qua router IPv4 thông thường; proxy ARP có thể thay đổi hành vi |
| **ICMP / L3** | ICMP Echo Request, chẩn đoán lỗi | Echo Reply, Destination Unreachable, Time Exceeded | Nhiều hệ thống hạn chế/chặn ICMP; mất Echo Reply không đồng nghĩa máy offline |
| **ICMPv6 / IPv6** | Echo hoặc Neighbor Discovery trong phạm vi liên kết thích hợp | Echo Reply; ND Neighbor Advertisement trên cùng link | ND không phải phương pháp xuyên mạng; nhiều loại ICMPv6 phục vụ chức năng thiết yếu |
| **TCP / L4** | Kết nối thử tới cổng dịch vụ được phép | SYN-ACK, RST, kết nối thành công hoặc timeout | Proxy, firewall và load balancer có thể trả lời thay máy đích |
| **UDP / L4** | Gửi yêu cầu tối thiểu đúng giao thức tới cổng xác định | Phản hồi UDP hoặc ICMP Port Unreachable; cũng có thể im lặng | Im lặng thường mơ hồ; rate limiting và chính sách ICMP dễ làm sai nhận định |
| **Ứng dụng / L7** | Yêu cầu HTTP HEAD/GET, TLS handshake, truy vấn DNS tới resolver được phép | Header HTTP, chứng chỉ TLS, banner hoặc phản hồi DNS | Phiên bản/banner có thể bị ẩn, thay đổi, giả lập hoặc do reverse proxy cung cấp |

### 3.1. Host discovery: thiết bị có phản hồi hay không?

**Host discovery** ước lượng những địa chỉ nào có thể đang hoạt động và có thể tiếp cận từ nơi quét. Công cụ có thể dùng ICMP, TCP probe hoặc, trong một số mạng cục bộ, ARP/Neighbor Discovery.

- **ICMP Echo Reply** hỗ trợ suy luận đích có phản hồi ICMP tại thời điểm kiểm tra.
- **TCP SYN-ACK hoặc TCP RST** từ mục tiêu có thể cho thấy một host/ngăn xếp mạng đang phản hồi probe TCP, kể cả khi ICMP Echo bị chặn.
- **ARP reply** hữu ích khi xác định láng giềng IPv4 trên cùng lớp liên kết; không chứng minh chắc chắn đó là ứng dụng cuối vì cơ chế proxy/ảo hóa có thể tham gia.
- **Không phản hồi** là trạng thái không chắc chắn: cần đối chiếu tuyến đường, ACL, log và nguồn kiểm kê.

Ví dụ, một server có thể không trả lời ping từ mạng khách nhưng vẫn chấp nhận HTTPS từ mạng ứng dụng. Báo cáo “host chết” chỉ dựa vào một lần ping sẽ sai với mô hình truy cập này.

### 3.2. TCP port scanning: dịch vụ TCP có tiếp nhận kết nối?

TCP sử dụng cơ chế bắt tay kết nối. Với một probe TCP phổ biến:

~~~text
                       TCP SYN
Máy quét --------------------------------> Đích :443

Trường hợp A: nhận SYN-ACK  ──> cổng có dấu hiệu open
Trường hợp B: nhận RST      ──> cổng có dấu hiệu closed
Trường hợp C: không phản hồi hoặc nhận lỗi lọc
                               ──> có thể filtered/không xác định
~~~

Trong **TCP connect scan**, công cụ sử dụng cơ chế kết nối TCP của hệ điều hành; nếu thành công, nó có thể hoàn tất bắt tay rồi đóng kết nối. Trong **SYN scan**, công cụ quan sát kết quả từ SYN mà không cần hoàn tất một phiên ứng dụng bình thường; thường yêu cầu quyền tạo gói thô hoặc khả năng tương đương. Hai kiểu đều gửi lưu lượng tới mục tiêu và đều có thể bị ghi nhận.

Nhiều yếu tố ảnh hưởng kết quả:

- Firewall có thể **drop** probe khiến máy quét nhìn thấy timeout, hoặc **reject** với thông báo/đáp trả cụ thể.
- Stateful firewall có thể chấp nhận gói thuộc phiên hợp lệ và từ chối probe mới.
- Host-based firewall có thể lọc một cổng dù tiến trình vẫn đang lắng nghe trên máy.
- Load balancer và reverse proxy có thể mở cổng trên địa chỉ công khai dù nhiều backend không trực tiếp truy cập được.
- Kết quả chỉ đúng với **giao thức, IP đích, cổng, đường đi, nguồn quét và thời điểm** đã kiểm tra.

### 3.3. UDP scanning: im lặng không chứng minh cổng mở

UDP không có bắt tay tương đương TCP. Nếu có phản hồi đúng giao thức từ một cổng UDP, đó là bằng chứng mạnh hơn rằng một dịch vụ đã nhận yêu cầu. Nếu nhận **ICMP Destination Unreachable / Port Unreachable** (đối với IPv4, type 3 code 3) từ host đích, đây thường là dấu hiệu cổng không có dịch vụ nhận.

Tuy nhiên, nhiều dịch vụ UDP chỉ trả lời khi payload đúng định dạng; firewall có thể chặn; thiết bị có thể giới hạn tốc độ ICMP. Vì thế công cụ có thể báo **open|filtered** — chưa phân biệt được cổng thực sự nhận hay gói bị lọc. Không nên tự chuyển trạng thái mơ hồ thành “open” trong báo cáo.

Các dịch vụ thường dùng UDP gồm DNS trên cổng 53, NTP trên 123 và một số chế độ VPN. Cần hiểu giao thức trước khi quyết định loại probe và tránh tạo khối lượng yêu cầu lớn hoặc dữ liệu không mong muốn tới dịch vụ.

### 3.4. Nhận diện dịch vụ: cổng không phải phiên bản ứng dụng

Cổng **22** thường dùng SSH, **53** thường liên quan DNS và **443** thường dùng HTTPS, nhưng dịch vụ thực tế không bị ràng buộc vào cổng mặc định. Một TCP listener tại 443 có thể là reverse proxy, API gateway hoặc dịch vụ không phải HTTPS.

**Service detection** gửi thăm dò ở mức ứng dụng hoặc kiểm tra phản hồi như lời chào SSH, HTTP header hay thông tin handshake TLS để ước đoán dịch vụ và phiên bản. Kết quả vẫn có giới hạn: banner có thể bị làm giả, proxy có thể che backend và bản phân phối phần mềm có thể **backport** bản vá mà không đổi số phiên bản theo cách công cụ dự đoán.

**Quy tắc suy luận:** Dấu hiệu dịch vụ không tự động là bằng chứng dịch vụ dễ bị khai thác. Kết luận về điểm yếu cần xác nhận bằng cấu hình, trạng thái bản vá, tài liệu nhà sản xuất và quy trình đánh giá lỗ hổng được ủy quyền.

## 4. Đọc kết quả quét đúng cách

Nhiều công cụ, đặc biệt Nmap, dùng các nhãn trạng thái cổng sau. Đây là **kết luận quan sát theo phương pháp quét**, không phải thuộc tính vĩnh viễn của host:

| Trạng thái | Ý nghĩa thực hành | Điều không thể kết luận chỉ từ trạng thái |
|---|---|---|
| **open** | Có phản hồi phù hợp với việc cổng tiếp nhận lưu lượng theo kỹ thuật đang dùng | Không chứng minh dịch vụ an toàn hoặc có lỗ hổng |
| **closed** | Địa chỉ có phản hồi cho biết cổng không tiếp nhận kết nối/dịch vụ ở thời điểm đo | Không chứng minh host không tồn tại hay sẽ luôn đóng |
| **filtered** | Bộ lọc hoặc thiếu phản hồi khiến khó xác định trạng thái cổng | Không xác định chắc chắn tiến trình có đang lắng nghe hay không |
| **unfiltered** | Cổng có thể tiếp cận theo kỹ thuật thăm dò phù hợp nhưng chưa phân biệt open/closed | Không đồng nghĩa open |
| **open|filtered** | Chưa phân biệt được giữa có dịch vụ và bị lọc; thường gặp trong UDP scan | Không được ghi thành open chắc chắn |
| **closed|filtered** | Chưa phân biệt được giữa cổng đóng và cổng bị lọc trong một số kỹ thuật | Không được ghi thành closed chắc chắn |

Ví dụ báo cáo giả định:

~~~text
Target: 192.0.2.25
Vantage point: VLAN quản trị của lab
TCP/22    open          SSH (dự đoán)
TCP/443   open          HTTPS (dự đoán)
TCP/3389  filtered      Chưa xác định dịch vụ ở đích
UDP/53    open|filtered Chưa đủ bằng chứng xác nhận DNS
~~~

Địa chỉ **192.0.2.25** là ví dụ trong dải IP dành cho tài liệu; kết quả trên **được dựng để minh họa**, không phải kết quả quét thực tế.

Khi đánh giá phát hiện:

1. Ghi rõ **vị trí quét** và nguồn IP: máy trong cùng VLAN, mạng nhân viên, VPN, cloud subnet hoặc điểm Internet có thể nhìn thấy những bề mặt khác nhau.
2. Ghi rõ **thời gian**, phương pháp và cổng đích: một lần đo ngắn có thể gặp mất gói hoặc dịch vụ đang cập nhật.
3. Xác minh **tài sản thuộc ai** và dịch vụ có chủ đích hay không: thông tin trong CMDB, cấu hình máy, load balancer và firewall hữu ích hơn banner đơn lẻ.
4. Tách **phát hiện quan sát được** khỏi **giả thuyết rủi ro**: một cổng quản trị công khai là vấn đề cần kiểm tra chính sách; bản thân cổng mở chưa đủ chứng minh cấu hình sai nếu có kiểm soát phù hợp.

## 5. Thiết kế đợt quét được ủy quyền và giới hạn tác động

Một đợt active scanning đáng tin phải cho phép người quản trị biết chính xác **ai quét, quét ở đâu, quét gì, với nhịp độ nào và dùng kết quả vào việc gì**.

| Nội dung cần xác định trước | Ví dụ yêu cầu cho một lab/đợt đánh giá nội bộ |
|---|---|
| **Phạm vi** | Danh sách IP/host do chủ sở hữu phê duyệt; địa chỉ trong cloud và hệ thống bên thứ ba có thể cần phạm vi chấp thuận riêng |
| **Vị trí quét** | Máy quản trị thuộc VLAN lab, VPN quản trị hoặc scanner trong subnet được cấp phép |
| **Loại probe** | Host discovery, một tập cổng TCP chỉ định, kiểm tra dịch vụ nhẹ; tránh thăm dò xâm lấn khi chưa được chấp thuận |
| **Thời gian** | Khung giờ không ảnh hưởng cao điểm; phối hợp với SOC/NOC và đội vận hành |
| **Giới hạn tải** | Số host, số cổng, đồng thời/tốc độ phù hợp với khả năng hệ thống; thiết bị nhạy cảm cần cách kiểm tra riêng |
| **Quy tắc dừng** | Dừng khi xuất hiện lỗi dịch vụ, tăng latency, cảnh báo có mức độ nghiêm trọng hoặc yêu cầu từ chủ sở hữu |
| **Lưu bằng chứng** | Thời điểm, nguồn/đích, tham số, phiên bản công cụ, log liên quan và cách xử lý dữ liệu nhạy cảm |
| **Xác nhận kết quả** | Đối chiếu với firewall rule, CMDB, tiến trình đang lắng nghe và owner trước khi phát hành phát hiện |

Các thiết bị như PLC/OT, máy in cũ, hệ thống nhúng hoặc cảm biến công nghiệp có thể phản ứng không ổn định trước lưu lượng thăm dò thông thường. Với nhóm này, ưu tiên **kiểm kê thụ động, dữ liệu quản trị hoặc phương pháp do nhà cung cấp phê duyệt** cho đến khi đánh giá rủi ro và có cửa sổ kiểm tra phù hợp.

Trong hệ thống cloud, các địa chỉ IP công khai hoặc private không nhất thiết thuộc quyền kiểm soát trực tiếp của cùng một đội. Đọc chính sách của tài khoản/nền tảng, xác nhận phạm vi sở hữu và phối hợp với chủ workload trước khi tạo lưu lượng kiểm tra.

## 6. Thực hành phòng lab: quan sát máy của chính mình

Ví dụ dưới đây thực hiện trên **loopback 127.0.0.1**, tức thiết bị chạy lệnh. Dữ liệu trả về phụ thuộc dịch vụ đang lắng nghe trên máy; không có cổng nào được mặc định là mở. Yêu cầu cài đặt Nmap trên máy lab và có quyền chạy công cụ trong phạm vi được cho phép.

### Bước 1. Quan sát kết nối TCP tới một số cổng

~~~bash
nmap -sT -p 22,80,443 127.0.0.1
~~~

Ý nghĩa tham số:

- **-sT**: sử dụng **TCP connect scan** qua API kết nối của hệ điều hành.
- **-p 22,80,443**: chỉ kiểm tra đúng ba cổng TCP này.
- **127.0.0.1**: loopback của máy hiện tại, tránh vô tình nhắm tới tài sản khác.

Nếu kết quả là **closed** ở cả ba cổng, hãy hiểu rằng tại điểm quét này không có dịch vụ chấp nhận TCP connect trên các cổng đó. Nếu **open**, xác minh bằng công cụ quản trị tiến trình đang lắng nghe, thay vì suy ra dịch vụ thực tế chỉ theo số cổng.

### Bước 2. Nhận diện một dịch vụ lab được chủ động bật

Nếu chính bạn đã cấu hình một dịch vụ HTTP thử nghiệm lắng nghe TCP **8080** trên loopback, có thể thăm dò nhẹ:

~~~bash
nmap -sT -sV --version-light -p 8080 127.0.0.1
~~~

**-sV** cho phép phát hiện dịch vụ; **--version-light** chọn mức kiểm tra phiên bản nhẹ hơn mặc định. Nếu chưa có dịch vụ trên 8080 thì kết quả đóng là bình thường; không cần mở dịch vụ chỉ để ép kết quả thành open.

### Bước 3. Quan sát một phép thử UDP có giới hạn

Nếu lab có dịch vụ UDP được phép kiểm tra, ví dụ resolver cục bộ tại cổng 53:

~~~bash
nmap -sU -p 53 127.0.0.1
~~~

Trạng thái **open|filtered** có thể xuất hiện khi không nhận phản hồi phân biệt. Nó không chứng minh rằng DNS đang hoạt động. Kiểm tra thêm cấu hình dịch vụ hoặc dùng một truy vấn ứng dụng hợp lệ trong chính lab nếu cần xác minh.

### Bước 4. Ghi phiếu quan sát

~~~text
Tên bài: Active scanning tại loopback
Phạm vi: 127.0.0.1 của máy cá nhân được phép kiểm tra
Thời gian: [giờ và múi giờ thực tế]
Nguồn quét: [tên host và địa chỉ giao diện liên quan]
Công cụ: Nmap [phiên bản thực tế]
TCP cổng: 22, 80, 443; dịch vụ lab 8080 nếu có
UDP cổng: 53 (chỉ khi phù hợp)
Trạng thái quan sát: [open/closed/filtered/open|filtered]
Xác minh bổ sung: [tiến trình lắng nghe, log, cấu hình]
Kết luận: [phát hiện và mức độ chắc chắn]
~~~

Mỗi lần quét là một lần quan sát; ghi nhận kết quả thực tế thay vì sao chép kết quả của ví dụ minh họa.

## 7. Active scanning đi qua firewall, VPN và phân đoạn như thế nào?

Một thiết bị có thể có dịch vụ đang lắng nghe nhưng chỉ truy cập được từ một mạng con hoặc danh tính được phép.

~~~text
                   +----------------------+
                   | Ứng dụng nội bộ      |
                   | TCP 443; TCP 22      |
                   +----------+-----------+
                              |
                       [Firewall / ACL]
                       /              \
        Nguồn A: VLAN quản trị      Nguồn B: mạng khách
        HTTPS được cho phép         HTTPS bị từ chối
        SSH chỉ admin               SSH bị từ chối
~~~

Nếu nguồn A quét thấy TCP/443 **open** còn nguồn B thấy **filtered**, điều này **có thể** là dấu hiệu chính sách phân đoạn đang phát huy tác dụng. Cần đối chiếu cùng IP đích, route, thời điểm và log firewall để loại trừ sự khác biệt do mạng không tới được hoặc điểm quét khác.

Các lớp bảo vệ có ảnh hưởng đến kết quả:

- **Firewall/ACL:** xác định nguồn, đích, giao thức, cổng và hướng kết nối nào được phép; có thể drop hoặc reject.
- **Stateful firewall:** phân biệt kết nối mới với lưu lượng thuộc phiên đã thiết lập; một cổng mở không cho biết toàn bộ rule stateful.
- **VPN:** tạo đường đi khác và có thể gán IP/route riêng cho máy kiểm tra. Quét qua VPN có thể thấy dịch vụ nội bộ nhưng không được kết luận dịch vụ công khai trên Internet.
- **IDS/IPS:** có thể ghi nhận nhiều probe tới cổng khác nhau hoặc một chuỗi kết nối bất thường; IPS cũng có thể chặn/ngắt kết nối theo chính sách.
- **Load balancer/API gateway:** có thể lắng nghe ở phía trước và chuyển tiếp đến backend theo host/path, TLS SNI và quy tắc định tuyến ứng dụng.
- **Cloud security group/NACL:** kết quả phụ thuộc subnet, attachment, hướng truy cập và chính sách áp dụng; khác biệt giữa nhà cung cấp và nền tảng cần kiểm tra tài liệu.

Một cuộc kiểm tra có ích cho **network segmentation validation** là lập ma trận truy cập mong muốn rồi so với lưu lượng thực sự đi được:

| Nguồn được phép | Đích | Dịch vụ dự kiến | Quan sát quét | Hành động đánh giá |
|---|---|---|---|---|
| VLAN quản trị | Máy quản trị nội bộ | SSH 22 được phép | open | Kiểm tra xác thực, log và hạn chế nhóm admin |
| VLAN nhân viên | Máy quản trị nội bộ | SSH 22 bị chặn | filtered | Đối chiếu rule deny và log firewall |
| VLAN khách | API nội bộ | HTTPS 443 bị chặn | filtered hoặc không tới được | Xác minh ranh giới và route, không kết luận chỉ từ timeout |
| VPN quản trị | API nội bộ | HTTPS 443 được phép | open | Kiểm tra chứng chỉ TLS và phân quyền API |

Bảng là **kịch bản giả định**, không phải kết quả kiểm tra môi trường thực. Một rule cho phép TCP/443 có thể cần thêm điều kiện danh tính, mTLS hoặc authorization ở tầng ứng dụng.

## 8. Nhận diện hoạt động quét từ góc nhìn phòng thủ

Vì quét chủ động phát sinh lưu lượng, người vận hành thường tìm dấu hiệu tại nhiều điểm quan sát:

| Nguồn dữ liệu | Tín hiệu có thể cho thấy hoạt động quét | Điều cần kiểm chứng |
|---|---|---|
| **Firewall logs** | Nhiều kết nối mới hoặc nhiều cổng đích từ một nguồn, tăng số lần drop/reject | Nguồn có phải scanner đã đăng ký? Có thay đổi rule hoặc hành vi ứng dụng hợp lệ không? |
| **NetFlow/IPFIX/VPC flow logs** | Một nguồn liên hệ nhiều đích hoặc nhiều cổng trong thời gian ngắn | Đây là kiểm kê định kỳ, health check, service discovery hay hoạt động lạ? |
| **IDS/IPS** | Cảnh báo port scan, host sweep, mẫu SYN hoặc lỗi giao thức | Rule phát hiện có báo nhầm do load balancer, giám sát uptime hoặc NAT không? |
| **Server/application logs** | Nhiều lần mở kết nối, lỗi HTTP hoặc handshake không hoàn tất | Hành vi của client thật, bot hợp lệ hay scanner? |
| **DNS logs** | Nhiều truy vấn tên host liên tiếp hoặc sự thay đổi vùng truy vấn | Có hoạt động quản trị, giám sát và cache DNS bình thường hay không? |
| **Endpoint telemetry** | Tiến trình lạ phát sinh nhiều kết nối tới các địa chỉ/cổng | Có phê duyệt cho công cụ quét? Endpoint có bị xâm nhập không? |

**Không phải mọi quét đều độc hại.** Vulnerability management, kiểm kê tài sản, dịch vụ giám sát và kiểm tra tuân thủ thường tạo mẫu lưu lượng tương tự. Quy trình phân loại cần kết hợp **nguồn, thời gian, phạm vi, tài khoản thực hiện, thông báo lịch kiểm tra và hành vi tiếp theo**.

### Ví dụ phân tích một cảnh báo

SOC nhận cảnh báo: “Một IP nội bộ thử kết nối TCP tới 40 cổng trên 12 máy chủ trong 3 phút”. Quy trình hợp lý:

1. Xác định IP thực hiện, interface/VLAN, NAT/VPN liên quan và ai sở hữu máy.
2. Đối chiếu lịch quét đã được phê duyệt và inventory scanner.
3. Kiểm tra các cổng, máy đích, chiều kết nối, tỷ lệ success/deny và timestamp.
4. Phân biệt kiểm kê có giới hạn với hành vi bất thường như cố đăng nhập, tạo nhiều request ứng dụng hoặc thực thi trái phép trên endpoint.
5. Nếu chưa có phê duyệt hoặc nghi ngờ xâm nhập, chuyển quy trình sự cố để thu thập bằng chứng và hạn chế theo quyền của đội vận hành.

Không nên tuyên bố “đã có tấn công” chỉ vì IDS gắn nhãn port scan. Ngược lại, chỉ vì nguồn IP thuộc mạng nội bộ cũng chưa đủ coi là an toàn: thiết bị hợp lệ có thể bị chiếm quyền.

## 9. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| Ping không trả lời nên kết luận host offline | ICMP có thể bị chặn hoặc host từ chối trả lời | Đối chiếu CMDB, route, các probe được phép và log |
| Một cổng open được báo ngay là lỗ hổng | Cổng mở chỉ xác nhận dấu hiệu dịch vụ có thể truy cập | Xác minh owner, chính sách, xác thực, cấu hình và bản vá |
| open|filtered được ghi là open | UDP có thể im lặng dù bị lọc | Giữ nguyên mức không chắc chắn và kiểm tra ở tầng ứng dụng |
| Chỉ quét từ VPN rồi kết luận Internet đã được bảo vệ | VPN và Internet có đường đi/chính sách khác nhau | Xác nhận từ từng điểm quan sát được phê duyệt |
| Nhận diện dịch vụ chỉ từ số cổng | Dịch vụ có thể đổi cổng, đặt sau proxy hoặc dùng giao thức khác | Kiểm tra phản hồi ứng dụng và cấu hình máy chủ |
| Tin hoàn toàn vào banner phiên bản | Banner có thể lỗi thời hoặc được tùy chỉnh, bản vá có thể backport | Kiểm tra package, patch advisory và inventory |
| Quét hệ thống nhạy cảm không có giới hạn tải | Probe có thể làm chậm hoặc gây lỗi dịch vụ yếu | Giới hạn phạm vi, lên lịch, dùng phương pháp phù hợp thiết bị |
| Bỏ qua IPv6 khi kiểm tra mạng dual-stack | IPv6 có thể có đường đi và rule khác IPv4 | Xây dựng inventory và ma trận truy cập cho cả IPv4/IPv6 |
| Chỉ dùng kết quả từ một thời điểm | Trạng thái dịch vụ và cấu hình có thể thay đổi | Lưu timestamp, tái kiểm tra có kiểm soát và theo dõi biến động |

## 10. Bài tập tình huống: đối chiếu ma trận truy cập

**Bối cảnh giả định:** Công ty có một server nội bộ chạy API trên **TCP/8443** và chức năng quản trị trên **TCP/22**. Chính sách mong muốn:

- VLAN quản trị được kết nối TCP/22 và TCP/8443.
- VLAN nhân viên chỉ được kết nối TCP/8443.
- VLAN khách không được kết nối hai cổng này.

Đội vận hành kiểm tra có ủy quyền từ ba nguồn đại diện và ghi nhận:

| Nguồn quét | TCP/22 | TCP/8443 |
|---|---|---|
| VLAN quản trị | open | open |
| VLAN nhân viên | filtered | open |
| VLAN khách | filtered | open |

Các kết quả là **dữ liệu bài tập**, không phải phát hiện từ môi trường thật. Cổng TCP/8443 **open** khi quét từ VLAN khách là điểm **không phù hợp với chính sách mong muốn**, cần xác minh trước khi kết luận cấu hình firewall sai: có thể tồn tại route, proxy, load balancer, quy tắc ACL khác hoặc nhầm IP đích.

### Cách xử lý đề xuất

1. Kiểm tra cả ba nguồn quét có cùng đích thực sự hay không; nếu qua proxy hoặc DNS khác nhau phải ghi rõ.
2. Từ VLAN khách, xác minh kết nối tới **đúng IP/cổng** theo cách được cho phép và đối chiếu log firewall, router và load balancer.
3. Kiểm tra cấu hình ACL/security group và điều kiện theo nguồn, trạng thái phiên; tìm điểm cho phép ngoài chủ ý.
4. Nếu xác nhận vi phạm chính sách, đề xuất thay đổi rule qua quy trình quản lý thay đổi và xác thực ảnh hưởng của ứng dụng.
5. Quét lại có giới hạn sau thay đổi, cập nhật ma trận “mong muốn → quan sát → bằng chứng” và tạo giám sát phát hiện tái diễn.

**Câu hỏi tự kiểm tra:**

1. Một host không trả lời ICMP Echo nhưng TCP/443 open có mâu thuẫn không? Vì sao?
2. Khi Nmap hiển thị UDP/53 open|filtered, cần thêm bằng chứng gì để kết luận DNS đang phục vụ yêu cầu?
3. Vì sao quét từ VPN quản trị không thay thế việc kiểm tra từ VLAN khách hoặc điểm Internet đã được phép?
4. Một reverse proxy mở TCP/443 có chứng minh rằng mọi backend đều mở TCP/443 không?
5. Hệ thống IDS báo nhiều lần kết nối tới 50 cổng từ một IP nội bộ: thông tin nào giúp phân biệt scanner được quản lý với hoạt động trái phép?

## 11. Ghi nhớ trọng tâm

**Active scanning là gửi probe chủ động để đo khả năng tiếp cận của host, cổng và dịch vụ từ một điểm quan sát xác định.** Host discovery, TCP/UDP scanning và service detection cung cấp những loại bằng chứng khác nhau; trạng thái **open, closed, filtered hoặc open|filtered** phải được giải thích trong ngữ cảnh giao thức, firewall và nguồn quét.

Quét chủ động hữu ích cho **kiểm kê bề mặt tấn công, xác minh phân đoạn, kiểm tra firewall/VPN, đánh giá cấu hình cloud và đối chiếu cảnh báo IDS/IPS**. Một quy trình chất lượng bắt đầu bằng phạm vi được ủy quyền, chọn probe đủ nhẹ, giới hạn tác động, ghi nhận vị trí/thời điểm, xác minh với nguồn quản trị và quét lại sau khi thay đổi. **Khả năng tiếp cận là một phép đo; mức độ rủi ro cần được đánh giá bằng chính sách, cấu hình và bằng chứng bổ sung.**
