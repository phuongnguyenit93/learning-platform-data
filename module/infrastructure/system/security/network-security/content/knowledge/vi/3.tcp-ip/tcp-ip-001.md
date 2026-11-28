# Vai trò của IP address trong mạng TCP/IP và bảo mật mạng

> **Chương:** TCP IP  
> **Bài học:** Vai trò của IP address (địa chỉ IP)  
> **Bối cảnh:** Nắm cách địa chỉ IP giúp thiết bị và dịch vụ liên lạc qua nhiều mạng; dùng hiểu biết này để phân đoạn, xây dựng chính sách firewall/VPN, phân tích lưu lượng, phát hiện xâm nhập và thiết kế hạ tầng mạng an toàn.

## 1. Địa chỉ IP giải quyết vấn đề gì?

Giả sử máy tính nhân viên cần mở ứng dụng đặt hàng ở một máy chủ thuộc mạng khác. Máy tính biết phải gửi dữ liệu đi đâu bằng cách nào? Khi gói tin đi qua nhiều router, mỗi router dựa vào thông tin nào để chuyển tiếp? Nếu đội bảo mật muốn ngăn máy nhân viên truy cập trực tiếp cơ sở dữ liệu, họ sẽ mô tả đích cần chặn ra sao?

**Địa chỉ IP (Internet Protocol address)** là địa chỉ logic được gán cho giao diện mạng, giúp **xác định điểm nguồn và điểm đích của gói tin IP** và cho phép hệ thống định tuyến chuyển các gói tin giữa các mạng. Hai phiên bản phổ biến là **IPv4** (32 bit) và **IPv6** (128 bit).

Địa chỉ IP có hai vai trò liên hệ mật thiết:

1. **Định vị ở cấp mạng:** Cho biết địa chỉ thuộc phạm vi mạng nào để router chọn tuyến chuyển tiếp thích hợp.
2. **Xác định đầu cuối ở cấp IP:** Cho biết gói tin được gửi từ địa chỉ nào và hướng tới địa chỉ nào, để máy đích và các điểm kiểm soát mạng xử lý.

Địa chỉ IP **không phải danh tính bất biến của người dùng hay thiết bị**. Một thiết bị có thể có nhiều địa chỉ IP; nhiều người dùng có thể đi ra Internet qua cùng một IP công cộng; IP có thể thay đổi khi DHCP cấp lại, thiết bị chuyển mạng, workload được tạo lại hoặc người dùng kết nối qua VPN. Địa chỉ nguồn trong gói tin cũng có thể bị giả mạo trong một số tình huống.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích chức năng IP trong bộ giao thức TCP/IP và phân biệt địa chỉ IP với địa chỉ MAC, cổng TCP/UDP, tên miền và danh tính người dùng.
- Đọc địa chỉ IPv4/IPv6, hiểu phần tiền tố mạng (*prefix*), subnet và vai trò của default gateway.
- Mô tả đường đi của gói tin qua router, sự ảnh hưởng của NAT và các thông tin nhìn thấy trong log mạng.
- Xác định vì sao địa chỉ IP quan trọng với firewall, phân đoạn, VPN, DNS, giám sát và phân tích lưu lượng.
- Nhận diện các giới hạn của kiểm soát chỉ dựa vào IP, cũng như các rủi ro giả mạo, định tuyến sai và bỏ sót IPv6.

## 2. IP nằm ở đâu trong mô hình TCP/IP?

Trong mô hình TCP/IP, **IP hoạt động ở tầng Internet** (thường tương ứng tầng mạng, lớp 3 của OSI). IP vận chuyển *datagram* giữa các địa chỉ mạng trên nhiều liên kết. Tầng này không tự bảo đảm gói tin sẽ đến đích, đến đúng thứ tự hay không bị lặp. TCP, nếu được sử dụng, bổ sung các cơ chế điều khiển truyền tin ở tầng vận chuyển; UDP cung cấp một hình thức truyền datagram đơn giản hơn.

| Thành phần | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| **Tên miền / DNS** | Tên dễ nhớ này hiện được ánh xạ đến địa chỉ nào? | app.example.com → 203.0.113.80 |
| **IP address** | Gói tin phải tới giao diện/đích mạng nào? | 203.0.113.80 |
| **Địa chỉ MAC / liên kết** | Trên liên kết Ethernet/Wi-Fi hiện tại, frame cần đến thiết bị kế tiếp nào? | MAC của default gateway |
| **Cổng TCP/UDP** | Tại máy đích, giao tiếp thuộc dịch vụ hoặc socket nào? | TCP 443 |
| **TLS và lớp ứng dụng** | Bảo mật phiên và xử lý yêu cầu thuộc dịch vụ nào? | HTTPS, chứng chỉ, HTTP request |
| **Danh tính & quyền** | Ai/ứng dụng nào thực hiện hành động; có được phép không? | Tài khoản nhân viên, service identity, policy |

> Một kết nối thường được mô tả bởi bộ thông tin: **IP nguồn, cổng nguồn, IP đích, cổng đích và giao thức vận chuyển**. Bộ năm trường này thường được gọi là *5-tuple*, rất hữu ích để theo dõi phiên, phân loại luồng và đọc firewall log.

Ví dụ mô phỏng một kết nối HTTPS:

~~~text
Source IP      : 10.20.10.25
Source TCP port: 52144        (cổng tạm thời của máy khách)
Destination IP : 203.0.113.80
Dest TCP port  : 443
Protocol       : TCP
Ứng dụng       : HTTPS
~~~

Hai địa chỉ IP cho biết các đầu cuối ở tầng mạng; hai cổng TCP giúp phân biệt phiên dịch vụ. **Không thể kết luận người dùng cụ thể là ai chỉ từ năm trường này**.

## 3. Cấu trúc địa chỉ: IPv4, IPv6 và tiền tố mạng

### 3.1. IPv4

IPv4 dài **32 bit**, thường viết bằng bốn số thập phân từ 0 đến 255, ngăn bằng dấu chấm:

~~~text
10.20.10.25
~~~

Địa chỉ luôn phải được hiểu cùng với **prefix/mặt nạ mạng** khi xác định phạm vi subnet. Với ký hiệu CIDR:

~~~text
10.20.10.25/24
~~~

- **/24** nghĩa là 24 bit đầu tạo thành phần tiền tố mạng, 8 bit còn lại thuộc phần địa chỉ trong subnet.
- Mặt nạ IPv4 tương đương là **255.255.255.0**.
- Địa chỉ mạng của ví dụ là **10.20.10.0/24**.
- Phạm vi địa chỉ của subnet là **10.20.10.0 đến 10.20.10.255**.
- Trong subnet IPv4 /24 thông thường, **10.20.10.0** được dùng làm địa chỉ mạng và **10.20.10.255** là địa chỉ broadcast; các địa chỉ host thông thường có thể nằm trong khoảng **10.20.10.1–10.20.10.254**.

Không nên dùng số lượng địa chỉ host như một quy tắc tuyệt đối cho mọi loại mạng: các trường hợp đặc biệt như liên kết IPv4 /31, /32 và một số môi trường đám mây có quy tắc cấp phát riêng.

Ví dụ chia một mạng:

| Subnet | Dải địa chỉ | Ý nghĩa minh họa |
|---|---|---|
| 10.20.10.0/24 | 10.20.10.0–10.20.10.255 | Toàn bộ mạng người dùng giả định ban đầu |
| 10.20.10.0/25 | 10.20.10.0–10.20.10.127 | Nhóm người dùng A |
| 10.20.10.128/25 | 10.20.10.128–10.20.10.255 | Nhóm người dùng B |

Việc chia subnet cho phép thiết kế chính sách khác nhau, nhưng **chỉ đặt hai subnet khác nhau không tự động tạo ra kiểm soát truy cập**: cần có ACL, firewall hoặc cơ chế thực thi tương ứng trên đường truyền.

### 3.2. IPv6

IPv6 dài **128 bit**, thường biểu diễn thành tám nhóm số hệ thập lục phân, phân tách bằng dấu hai chấm:

~~~text
2001:0db8:0010:0000:0000:0000:0000:0025
~~~

Có thể bỏ số 0 ở đầu nhóm và nén **một chuỗi liên tiếp** gồm các nhóm toàn 0 bằng ký hiệu “::”:

~~~text
2001:db8:10::25/64
~~~

Ở đây **/64** là độ dài tiền tố mạng; phần còn lại dài 64 bit. Phần tiền tố IPv6 được thể hiện theo bit, tương tự nguyên tắc CIDR của IPv4. Dải **2001:db8::/32** được dành cho tài liệu và ví dụ, không phải dải địa chỉ công cộng để triển khai ngoài thực tế.

Một giao diện IPv6 có thể đồng thời có địa chỉ **link-local**, địa chỉ toàn cục, địa chỉ tạm thời để tăng tính riêng tư và các địa chỉ khác. IPv6 không sử dụng broadcast như IPv4; một số chức năng sử dụng **multicast**.

### 3.3. Các loại địa chỉ quan trọng

| Địa chỉ/dải | Vai trò | Lưu ý bảo mật |
|---|---|---|
| **10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16** | IPv4 private dùng trong mạng nội bộ | Không định tuyến trực tiếp trên Internet công cộng; vẫn cần chính sách bảo mật giữa các vùng |
| **127.0.0.0/8**, thường dùng 127.0.0.1 | IPv4 loopback | Phục vụ liên lạc nội bộ trên cùng thiết bị |
| **169.254.0.0/16** | IPv4 link-local | Thường gặp khi địa chỉ liên kết được cấu hình tự động; không định tuyến qua router |
| **0.0.0.0** | Địa chỉ IPv4 không xác định; trong cấu hình còn có thể biểu thị mọi giao diện của máy | Ý nghĩa phụ thuộc ngữ cảnh: gói tin, cấu hình lắng nghe hay bảng định tuyến |
| **255.255.255.255** | IPv4 limited broadcast | Broadcast không được router chuyển tiếp theo cách thông thường |
| **224.0.0.0/4** | IPv4 multicast | Cần quy tắc và định tuyến multicast phù hợp |
| **100.64.0.0/10** | IPv4 shared address space, thường dùng cho CGNAT | Không phải RFC 1918; không coi là địa chỉ công cộng định tuyến Internet |
| **::1/128** | IPv6 loopback | Địa chỉ loopback trên thiết bị |
| **fe80::/10** | IPv6 link-local | Phục vụ giao tiếp trên liên kết cục bộ, bao gồm một số chức năng ND |
| **fc00::/7** | IPv6 unique local | Địa chỉ cục bộ, không được định tuyến trên Internet toàn cục |
| **2000::/3** | Khối IPv6 global unicast phân bổ thông dụng hiện nay | Quyền truy cập không tự an toàn vì địa chỉ là toàn cục |
| **ff00::/8** | IPv6 multicast | Cần hiểu lưu lượng multicast/ICMPv6, tránh chặn vô điều kiện |

Các dải dùng làm tài liệu trong bài như **192.0.2.0/24**, **198.51.100.0/24**, **203.0.113.0/24** (IPv4) và **2001:db8::/32** (IPv6) không đại diện cho địa chỉ hệ thống đang hoạt động.

## 4. Vai trò của IP trong chuyển tiếp gói tin và định tuyến

### 4.1. Cùng subnet và khác subnet

Giả sử:

- Máy khách có địa chỉ **10.20.10.25/24**.
- Default gateway của máy khách là **10.20.10.1**.
- Máy chủ ứng dụng nằm tại **10.20.20.15/24**.

Địa chỉ **10.20.20.15** không cùng subnet **10.20.10.0/24** với máy khách. Vì vậy, máy khách gửi frame trên liên kết tới **MAC của default gateway**; gói IP bên trong vẫn mang đích **10.20.20.15**. Gateway tra bảng định tuyến và chuyển tiếp gói IP về hướng mạng **10.20.20.0/24**, nếu có tuyến và chính sách cho phép.

Ngược lại, khi hai thiết bị ở cùng một mạng trực tiếp kết nối, hệ điều hành có thể chuyển frame cho thiết bị đích qua liên kết đó mà không cần đi qua default gateway. Các kiểm soát mạng phải tính đến cả **lưu lượng giữa các máy cùng subnet**, vì firewall chỉ đặt ở gateway có thể không nhìn thấy luồng này.

### 4.2. Sơ đồ đường đi gói tin

~~~mermaid
flowchart LR
    Client["Máy khách\n10.20.10.25/24"]
    GW["Gateway / Firewall\n10.20.10.1"]
    FW["Firewall phân đoạn"]
    App["Máy chủ ứng dụng\n10.20.20.15/24"]
    Db["Cơ sở dữ liệu\n10.20.30.12/24"]
    Client -->|"IP đích: 10.20.20.15"| GW
    GW -->|"Tra bảng định tuyến / kiểm tra ACL"| FW
    FW -->|"Chỉ cho luồng được cấp quyền"| App
    App -->|"IP đích: 10.20.30.12"| Db
~~~

Lưu ý rằng địa chỉ IP đích ở mỗi gói **thông thường được giữ nguyên xuyên qua các router** (trừ khi có cơ chế làm thay đổi địa chỉ như NAT). Trái lại, **địa chỉ MAC trên mỗi hop thay đổi** vì frame tầng liên kết được tạo lại trên từng đoạn kết nối.

Router thường thực hiện:

1. Nhận gói IP ở một giao diện.
2. Kiểm tra thông tin cần thiết và tra bảng định tuyến theo **địa chỉ IP đích**.
3. Chọn tuyến phù hợp nhất theo nguyên tắc **longest prefix match**: trong số các tuyến phù hợp, ưu tiên tiền tố dài nhất.
4. Giảm **TTL** của IPv4 hoặc **Hop Limit** của IPv6; xử lý trường hợp giá trị cạn.
5. Chuyển tiếp về next hop nếu tuyến, trạng thái đường truyền và chính sách cho phép.

IP hỗ trợ gửi gói qua nhiều mạng, nhưng **có tuyến chưa đồng nghĩa có quyền truy cập**. Một router có thể biết đường đi tới subnet dữ liệu, trong khi firewall phải chủ động từ chối kết nối từ mạng người dùng tới subnet đó.

### 4.3. Prefix, default route và lựa chọn đường đi

Ví dụ bảng định tuyến rút gọn:

~~~text
Destination prefix   Next hop          Ý nghĩa
10.20.10.0/24        directly connected Mạng cục bộ của máy
10.20.20.0/24        10.20.10.1        Tuyến riêng tới vùng ứng dụng
0.0.0.0/0            10.20.10.1        Default route IPv4
~~~

Nếu bảng định tuyến có cả tuyến **10.20.20.0/24** và **10.0.0.0/8**, gói gửi tới **10.20.20.15** sẽ ưu tiên **/24** vì đây là tiền tố cụ thể hơn. **0.0.0.0/0** biểu thị tuyến mặc định IPv4; **::/0** là tuyến mặc định IPv6.

Những sai sót về prefix, default route, chính sách định tuyến hoặc route propagation trong mạng đám mây có thể dẫn tới **mất kết nối**, **định tuyến sai vùng** hoặc **đường đi vòng qua kiểm soát bảo mật**. Vì vậy, đọc địa chỉ IP luôn gắn với việc hiểu tuyến của nó.

## 5. Địa chỉ IP được cấp và ánh xạ như thế nào?

### 5.1. Địa chỉ tĩnh, DHCP, SLAAC

Địa chỉ IP có thể được đặt **tĩnh** hoặc cấp động:

- **IPv4 DHCP:** Máy nhận địa chỉ IPv4 cùng thông số liên quan như subnet mask, gateway và DNS theo cấu hình máy chủ DHCP.
- **IPv6 SLAAC:** Thiết bị dùng thông tin từ Router Advertisement để tự cấu hình một hoặc nhiều địa chỉ theo tiền tố được công bố.
- **DHCPv6:** Có thể cung cấp địa chỉ và/hoặc các thông số IPv6 tùy chế độ triển khai.
- **Mạng đám mây/container:** Địa chỉ có thể gắn với giao diện ảo, instance, pod hoặc tài nguyên có vòng đời ngắn; cần theo dõi việc cấp phát và thay đổi.

DHCP, SLAAC và trạng thái giao diện khiến IP thường **không ổn định theo thời gian**. Đối với truy vết sự cố, đội vận hành cần biết **địa chỉ IP đã được gán cho ai/cái gì vào thời điểm nào**, thay vì chỉ tra bản ghi cấp phát hiện tại.

### 5.2. ARP và Neighbor Discovery

IP làm việc ở tầng mạng nhưng vẫn cần cơ chế ánh xạ tới địa chỉ tầng liên kết trên nhiều môi trường:

| Môi trường | Cơ chế phổ biến | Công dụng | Rủi ro tiêu biểu |
|---|---|---|---|
| IPv4 trên Ethernet | **ARP** | Tìm địa chỉ MAC tương ứng với địa chỉ IPv4 trong cùng liên kết | ARP spoofing/poisoning có thể làm sai đường chuyển frame |
| IPv6 trên Ethernet | **Neighbor Discovery (ND)** dựa trên ICMPv6 | Phân giải láng giềng, phát hiện router, địa chỉ trùng và chức năng liên quan | Router Advertisement giả, ND spoofing hoặc cấu hình bảo vệ sai |

Ở mạng phù hợp, các kỹ thuật như DHCP snooping, Dynamic ARP Inspection, RA Guard, giám sát rogue router và kiểm soát cổng switch có thể hạn chế một số rủi ro, nhưng phải kiểm tra khả năng hỗ trợ và ngữ cảnh vận hành. **Không chặn mọi ICMPv6**: nhiều chức năng quan trọng của IPv6 phụ thuộc vào ICMPv6, kể cả ND và thông báo phục vụ định tuyến/MTU.

## 6. DNS: Tên dịch vụ và địa chỉ IP không đồng nhất

Người dùng thường nhập **tên miền**, chứ không nhớ địa chỉ IP. DNS có thể trả về bản ghi **A** (IPv4) hoặc **AAAA** (IPv6) để máy khách biết những địa chỉ có thể dùng để kết nối. Một tên miền có thể ánh xạ tới nhiều địa chỉ; địa chỉ trả về có thể thay đổi do cân bằng tải, CDN, failover hoặc dịch vụ đám mây.

~~~text
Người dùng nhập: app.example.com
              |
              v
DNS tra cứu A / AAAA
              |
              v
Một địa chỉ đích phù hợp, ví dụ 203.0.113.80
              |
              v
Thiết lập kết nối IP + TCP/QUIC + TLS theo ứng dụng
~~~

**DNS không tự xác thực người dùng được phép vào ứng dụng**, và việc một IP từng phục vụ tên miền này không có nghĩa nó luôn thuộc cùng chủ sở hữu hay cùng dịch vụ. DNSSEC giúp xác thực tính toàn vẹn/nguồn gốc dữ liệu DNS trong chuỗi tin cậy khi được kiểm tra đúng, nhưng không mã hóa nội dung truy vấn. DoH/DoT có thể bảo vệ truy vấn khi truyền tới resolver; chính sách doanh nghiệp vẫn cần xác định resolver nào được phép dùng.

Trong bảo mật mạng, cần kết hợp **DNS log** và **lưu lượng IP** để liên hệ việc tra cứu tên miền với kết nối thực tế. Với các dịch vụ thay đổi IP thường xuyên, chính sách chỉ ghim một IP có thể hết hiệu lực hoặc tạo ra ngoại lệ khó quản lý; lựa chọn kiểm soát theo danh tính dịch vụ, tên miền hoặc proxy cần phù hợp khả năng của hệ thống.

## 7. NAT thay đổi cách nhìn địa chỉ nguồn và đích

**Network Address Translation (NAT)** thay đổi trường địa chỉ IP, và trong nhiều triển khai còn ánh xạ cổng, tại điểm trung gian. Một dạng thường gặp là **NAPT/PAT**: nhiều máy trong mạng private cùng chia sẻ một địa chỉ IPv4 công cộng, nhờ phân biệt phiên theo cổng.

Ví dụ một máy khách nội bộ kết nối ra máy chủ HTTPS:

~~~text
Trước NAT tại máy khách:
  10.20.10.25:52144  -> 203.0.113.80:443  TCP

Sau NAT tại cổng mạng:
  198.51.100.25:61001 -> 203.0.113.80:443 TCP

Phản hồi đi về:
  203.0.113.80:443 -> 198.51.100.25:61001 TCP

NAT ánh xạ lại về:
  203.0.113.80:443 -> 10.20.10.25:52144 TCP
~~~

Các địa chỉ thuộc khối tài liệu ở đây là **ví dụ giả định**, không đại diện cho kết nối đang diễn ra. Hệ thống NAT duy trì trạng thái ánh xạ để chuyển phản hồi về máy khách tương ứng.

Hệ quả:

- Phía máy chủ Internet có thể chỉ thấy **IP công cộng của điểm NAT**, không thấy trực tiếp IP private của máy khách.
- Firewall nằm trước và sau NAT có thể **ghi các địa chỉ/cổng khác nhau** cho cùng một luồng.
- Muốn gắn sự kiện với máy khách nội bộ, có thể cần **thời gian, IP, cổng, giao thức, log NAT và log cấp phát DHCP/VPN**.
- NAT có thể làm thay đổi khả năng truy cập trực tiếp giữa hai đầu cuối, nhưng **không được xem là cơ chế phân quyền hay firewall thay thế**.

IPv6 thường cung cấp đủ không gian địa chỉ để không cần NAT theo cách IPv4 truyền thống. Địa chỉ IPv6 có thể là global unicast nhưng vẫn phải chịu chính sách firewall và kiểm soát truy cập; **địa chỉ toàn cục không mặc định đồng nghĩa có thể truy cập từ Internet**.

## 8. Tại sao IP quan trọng trong kiến trúc phòng thủ theo lớp?

Địa chỉ IP là đầu vào nền tảng cho nhiều kiểm soát mạng, nhưng mỗi cơ chế nên được kết hợp với những bằng chứng khác thay vì coi IP là bằng chứng danh tính duy nhất.

### 8.1. Phân đoạn và firewall

**Phân đoạn mạng** chia hạ tầng thành những vùng có mức tin cậy, nhiệm vụ và quyền truy cập khác nhau: mạng người dùng, dịch vụ công khai, ứng dụng, cơ sở dữ liệu, quản trị và khách. **Prefix IP** giúp mô tả vùng và luồng ở tầng mạng; firewall/ACL thực thi chính sách.

Ví dụ quy hoạch minh họa:

| Vùng | CIDR | Vai trò | Chính sách truy cập chủ yếu |
|---|---|---|---|
| Users | 10.20.10.0/24 | Máy trạm nhân viên | Chỉ gọi API cần dùng; không gọi trực tiếp DB |
| App | 10.20.20.0/24 | Dịch vụ ứng dụng | Chỉ tới DB, DNS và dịch vụ phụ thuộc được duyệt |
| Data | 10.20.30.0/24 | Cơ sở dữ liệu | Chỉ tiếp nhận từ ứng dụng được cấp quyền |
| Admin | 10.20.40.0/24 | Bastion, quản trị | Truy cập giới hạn theo vai trò, MFA và nhật ký |
| Guest | 10.20.50.0/24 | Wi-Fi khách | Truy cập Internet theo chính sách, không vào vùng nội bộ |

Ma trận luồng ở mức khái niệm:

| Nguồn | Đích | Dịch vụ minh họa | Quyết định |
|---|---|---|---|
| Users | App | TCP 443 | **ALLOW** nếu ứng dụng được công bố nội bộ |
| App | Data | TCP 5432 | **ALLOW** chỉ từ đúng workload được duyệt |
| Users | Data | TCP 5432 | **DENY + LOG** |
| Guest | Admin | TCP 22/3389 | **DENY + LOG** |
| Admin qua bastion | Máy cần quản trị | Cổng quản trị được phê duyệt | **ALLOW có điều kiện** |
| App | Internet tùy ý | Bất kỳ | **DENY**, chỉ cấp ngoại lệ egress cần thiết |

Các cổng và subnet trong bảng chỉ để diễn giải; hệ thống thật phải dựa vào kiến trúc, giao thức và yêu cầu nghiệp vụ.

Một chính sách minh họa, **không phải cú pháp của firewall cụ thể**:

~~~yaml
default: deny
rules:
  - source: 10.20.10.0/24
    destination: 10.20.20.0/24
    protocol: tcp
    destination_port: 443
    action: allow
  - source: app-workload-identity
    destination: data-service
    protocol: tcp
    destination_port: 5432
    action: allow
  - source: 10.20.10.0/24
    destination: 10.20.30.0/24
    action: deny
    log: true
~~~

Quy tắc có thể tham chiếu IP, subnet, nhãn workload hoặc danh tính tùy sản phẩm. Với máy hoặc dịch vụ thay đổi IP thường xuyên, **chỉ dựa vào IP tĩnh** có thể gây hỏng kết nối hoặc mở quyền sai. Lớp phân đoạn càng gần workload thì càng cần kết hợp định danh dịch vụ và chính sách động.

### 8.2. VPN, ZTNA và danh tính

VPN có thể cấp địa chỉ IP từ một **pool VPN** cho máy truy cập từ xa. Hệ thống có thể dựa vào pool này để định tuyến và áp dụng quy tắc, nhưng **sở hữu IP từ pool không chứng minh người dùng đáng tin cậy**. Cần kiểm tra thêm tài khoản, MFA, thiết bị, vai trò, phiên và đích truy cập.

ZTNA thường tập trung cấp quyền truy cập ứng dụng hoặc dịch vụ cụ thể. Trong cả VPN và ZTNA, log **ánh xạ IP ↔ phiên ↔ danh tính ↔ thời điểm** giúp điều tra một kết nối nghi vấn.

### 8.3. DNS, Wi-Fi và mạng đám mây

- **DNS:** Resolver, chính sách truy vấn, tên miền và IP trả về hỗ trợ nhận diện kết nối bất thường; cần tính đến cache, CDN và các cách phân giải mã hóa.
- **Wi-Fi:** Điểm truy cập và chính sách mạng có thể đưa khách hoặc thiết bị quản lý vào VLAN/subnet khác nhau; IP của khách không được cho quyền tới tài sản nội bộ chỉ vì đang sử dụng cùng hạ tầng không dây.
- **Đám mây:** VPC/VNet, subnet, route table, security group, network ACL, private endpoint và NAT gateway đều sử dụng địa chỉ/prefix. Một subnet “private” về mục đích thiết kế vẫn phải kiểm tra đường đi thực tế và sự hiện diện của public endpoint.
- **Container/Kubernetes:** Pod IP có thể thay đổi. Hạn chế truy cập hiệu quả nên dùng NetworkPolicy, nhãn hoặc danh tính workload nếu nền tảng mạng hỗ trợ thực thi, thay vì duy trì danh sách IP pod thủ công.

### 8.4. Theo dõi gói tin, IDS/IPS và ứng phó

Trong giám sát, các trường **source IP**, **destination IP**, **protocol**, **port**, **timestamp**, **action** và **interface/zone** cho biết một luồng được nhìn thấy ở đâu và xử lý như thế nào. IDS/IPS có thể dùng IP để nhóm các dấu hiệu quét cổng, liên lạc tới điểm nghi vấn hoặc kết nối ngang bất thường.

Một cảnh báo như “10.20.10.25 thử tới 10.20.30.12:5432” cần được tương quan với log firewall, DNS, DHCP/VPN, thiết bị và ứng dụng. IP một mình không đủ kết luận máy tính đó do ai sử dụng, có bị chiếm quyền hay không, hoặc hành vi có phải tấn công.

## 9. Hệ quả bảo mật: IP hữu ích nhưng có thể bị lạm dụng

### 9.1. Giả mạo địa chỉ IP (*IP spoofing*)

Kẻ tấn công có thể tạo gói tin chứa **source IP giả**. Kỹ thuật này có thể xuất hiện trong một số kiểu tấn công DDoS/phản xạ hoặc thử qua mặt cơ chế tin tưởng quá mức vào IP.

Giả mạo source IP không tự cấp khả năng nhận phản hồi ở địa chỉ giả: TCP có cơ chế bắt tay và việc định tuyến gói phản hồi tạo ra những giới hạn thực tế; tuy nhiên, không nên vì thế coi source IP là xác thực mạnh.

Các biện pháp hỗ trợ gồm:

- **Ingress/egress filtering:** Kiểm tra địa chỉ nguồn có hợp lý với mạng/đường truyền nhận gói hay không; giảm phát tán gói có nguồn giả.
- **uRPF** khi phù hợp: Kiểm tra tính hợp lệ của hướng/đường quay về nguồn; cần cẩn trọng ở mạng định tuyến bất đối xứng.
- **Xác thực ở tầng cao hơn:** TLS/mTLS, xác thực người dùng, khóa hoặc token được quản lý, phân quyền ứng dụng.
- **Theo dõi bất thường:** Phát hiện lưu lượng có nguồn sai dải, địa chỉ private xuất hiện ở giao diện Internet hoặc sự kiện không phù hợp với sơ đồ tuyến.

### 9.2. Nhầm IP với danh tính và quyền truy cập

Một IP công cộng có thể đại diện cho hàng nghìn thiết bị sau CGNAT; một dịch vụ có thể dùng địa chỉ IP chia sẻ tại CDN; IP private có thể được tái sử dụng giữa các VPC hoặc mạng VPN khác nhau; một thiết bị có thể đổi IP trong cùng ngày.

Do đó, quy tắc “địa chỉ X là người A” dễ dẫn đến **gán nhầm sự kiện**, **cấp quyền nhầm** hoặc **chặn nhầm**. IP allowlist hữu ích như một lớp thu hẹp bề mặt tấn công, nhưng phải kết hợp xác thực/ủy quyền mạnh và quy trình duy trì danh sách.

### 9.3. Quét địa chỉ và di chuyển ngang

Khi kẻ tấn công đã chiếm một máy, việc dò các địa chỉ đích trong subnet hoặc trên nhiều subnet có thể giúp tìm dịch vụ không được bảo vệ. **Phân đoạn** giới hạn phạm vi truy cập; **firewall nội bộ** chặn các cổng không cần thiết; **IDS/telemetry** phát hiện lưu lượng bất thường; **xác thực ứng dụng** giảm thiệt hại nếu kết nối mạng vẫn đến được dịch vụ.

### 9.4. Lộ bề mặt tấn công vì định tuyến hoặc cấu hình sai

Các lỗi điển hình gồm:

- Đặt giao diện quản trị vào subnet có thể truy cập từ Internet, hoặc công bố IP công cộng ngoài ý muốn.
- Cho phép quá rộng cả dải **0.0.0.0/0** hay **::/0** trong luật truy cập nhạy cảm.
- Đặt subnet riêng nhưng có route/firewall cho phép kết nối tự do giữa các vùng.
- Chỉ viết chính sách IPv4 mà bỏ sót IPv6 đang bật.
- Hiểu nhầm địa chỉ source IP được hiển thị sau NAT/proxy là địa chỉ thật của người dùng.
- Chặn toàn bộ ICMP/ICMPv6 khiến một số chức năng mạng, phát hiện lỗi và cơ chế Path MTU hoạt động không đúng.

Nguyên tắc quan trọng là **kiểm tra cả cấu hình lẫn đường truyền thực tế**: một luật deny chỉ hữu ích nếu lưu lượng thật đi qua nơi thực thi luật đó.

## 10. Đọc log mạng: từ một IP tới bức tranh sự kiện

Giả sử firewall ghi nhận sự kiện minh họa:

~~~text
time=2026-11-28T09:00:00+07:00
src_ip=10.20.10.25 src_port=52341
dst_ip=10.20.30.12 dst_port=5432 protocol=tcp
src_zone=users dst_zone=data
action=deny rule=block-users-to-data
~~~

Cách diễn giải:

1. **IP nguồn 10.20.10.25** thuộc vùng người dùng trong sơ đồ giả định; cần đối chiếu địa chỉ đã được cấp cho thiết bị nào **tại thời điểm log**.
2. **IP đích 10.20.30.12** thuộc vùng dữ liệu; cổng **5432** thường gắn với PostgreSQL, nhưng chỉ nhìn cổng không thể chứng minh dịch vụ thực tế.
3. **action=deny** cho biết điểm kiểm soát đã từ chối lưu lượng theo luật nêu trong log.
4. Cần kiểm tra xem đây là cấu hình sai của ứng dụng, kiểm thử được phép, hay một thiết bị cố dò tìm dịch vụ.
5. Nếu có dấu hiệu tấn công, điều tra thêm log DNS, VPN/DHCP, endpoint, IDS và các luồng cùng nguồn trong cửa sổ thời gian liên quan.

Lưu ý về vị trí quan sát:

| Vị trí log | IP có thể nhìn thấy | Hệ quả |
|---|---|---|
| Máy khách trước NAT | IP private máy khách và IP đích bên ngoài | Dễ liên hệ tiến trình, tài khoản và địa chỉ cấp phát nội bộ |
| Firewall trước NAT | Thường thấy địa chỉ private, tùy mô hình và thứ tự xử lý | Hữu ích để gán luồng cho subnet nội bộ |
| Firewall sau NAT | Có thể thấy IP công cộng và cổng đã dịch | Cần log ánh xạ NAT để liên hệ về máy gốc |
| Reverse proxy / load balancer | Có thể thấy IP của proxy hoặc peer gần nhất | Cần cơ chế chuyển thông tin client có nguồn tin cậy; không tin header tự khai từ Internet |
| IDS qua cổng mirror | Chỉ thấy lưu lượng đi qua vị trí được mirror | Có thể bỏ sót east-west traffic trong cùng subnet hoặc đoạn mã hóa |

Khi dùng IPv6, log có thể chứa nhiều địa chỉ cho cùng thiết bị vì địa chỉ tạm thời hoặc nhiều giao diện. Luôn lưu **timestamp chính xác**, thông tin múi giờ, giao diện, vùng mạng, định danh thiết bị/người dùng nếu có, và bảo vệ log khỏi sửa đổi trái phép.

## 11. Thực hành quan sát IP và đường đi gói tin

Đây là bài thực hành **đọc và xác minh** trong mạng/lab do bạn được phép quản lý. Các địa chỉ trong ví dụ là địa chỉ tài liệu hoặc nội bộ giả định.

### 11.1. Quan sát địa chỉ, prefix và route

Trên Linux:

~~~bash
# Xem địa chỉ IPv4/IPv6 của các giao diện
ip -br address

# Xem tuyến IPv4 và IPv6
ip route
ip -6 route

# Xem hệ điều hành chọn tuyến nào tới đích IPv4 ví dụ
ip route get 10.20.20.15
~~~

Trên Windows PowerShell:

~~~powershell
# Xem địa chỉ IPv4/IPv6 và độ dài prefix
Get-NetIPAddress

# Xem bảng định tuyến IP
Get-NetRoute

# Kiểm tra cổng TCP của một dịch vụ trong lab được phép
Test-NetConnection -ComputerName 10.20.20.15 -Port 443
~~~

Hãy tìm địa chỉ hiện dùng, prefix length, default gateway/route và giao diện được chọn. **Đừng suy luận rằng có route thì kết nối sẽ thành công**; firewall, dịch vụ không lắng nghe, DNS, TLS hoặc quyền ứng dụng đều có thể khiến giao tiếp thất bại.

### 11.2. Quan sát ánh xạ tên miền sang IP

Trên Linux (nếu máy có tiện ích phù hợp):

~~~bash
dig A example.com
dig AAAA example.com
~~~

Trên Windows:

~~~powershell
Resolve-DnsName example.com -Type A
Resolve-DnsName example.com -Type AAAA
~~~

Kiểm tra xem cùng tên có thể có nhiều bản ghi không, TTL của câu trả lời DNS là bao nhiêu và địa chỉ được trả về có thể đổi theo thời gian hay không. Kết quả không nhất thiết giống nhau giữa các resolver hoặc các vị trí mạng.

### 11.3. Bài lab phân đoạn an toàn

Trong mạng thử nghiệm có hai subnet **10.20.10.0/24** và **10.20.30.0/24**:

1. Gán máy khách thử nghiệm ở vùng Users, máy chủ thử nghiệm ở vùng Data.
2. Cấu hình chính sách chỉ cho phép những luồng hợp lệ của bài lab, đồng thời từ chối Users → Data tới cổng không được duyệt.
3. Xác minh từ máy khách rằng truy cập tới dịch vụ được phép thành công và truy cập tới dịch vụ bị cấm không thành công.
4. Đối chiếu firewall log tại thời điểm thử nghiệm, ghi nhận source IP, destination IP, cổng, quyết định và vị trí quan sát.
5. Nếu lab có VPN/NAT, thử lại để xem IP nào được log trước và sau điểm dịch địa chỉ.

Kết quả kỳ vọng về mặt chính sách:

~~~text
10.20.10.25 -> 10.20.20.15:443    ALLOW (nếu được duyệt)
10.20.10.25 -> 10.20.30.12:5432   DENY + LOG
10.20.20.15 -> 10.20.30.12:5432   ALLOW (nếu ứng dụng cần)
~~~

Đây là **kết quả mô phỏng**, không phải log thực thu được từ hệ thống. Khi đánh giá mạng thật, cần xét chiều trả lời, kết nối đang tồn tại, IPv6, tuyến dự phòng và luồng quản trị/giám sát.

### 11.4. Câu hỏi tự kiểm tra

1. Vì sao máy có IP **10.20.10.25/24** thường cần default gateway để liên lạc với **10.20.20.15/24**?
2. Tại sao router thay đổi MAC của frame khi chuyển tiếp nhưng bình thường không thay đổi destination IP?
3. Với một máy có IP động qua DHCP, cần những log nào để xác định ai sử dụng IP ấy ở một thời điểm trong quá khứ?
4. Vì sao một địa chỉ IP công cộng sau NAT không đủ chứng minh người dùng gây ra kết nối?
5. IPv6 có thể khiến kiến trúc chỉ lọc IPv4 thiếu kiểm soát theo những cách nào?
6. Nếu firewall đã chặn kết nối tới DB nhưng IDS vẫn báo quét IP hàng loạt, hai tín hiệu này bổ sung cho nhau ra sao?

**Gợi ý:** Khi trả lời, luôn phân biệt địa chỉ, subnet, route, dịch vụ, danh tính và thời điểm. Đây là các yếu tố khác nhau dù chúng có thể xuất hiện trong cùng một bản ghi sự kiện mạng.

## 12. Những điểm cần ghi nhớ

- **Địa chỉ IP định vị nguồn và đích ở tầng mạng**, hỗ trợ router quyết định đường đi qua các mạng; nó không tự chứng minh danh tính và không bảo đảm gói tin được giao thành công.
- **Prefix/CIDR và bảng định tuyến** cho biết địa chỉ thuộc phạm vi nào và gói tin đi hướng nào; firewall/ACL quyết định luồng nào được phép qua ranh giới.
- **IPv4 và IPv6 cùng cần được bảo vệ**. Sự khác biệt về cấp phát, Neighbor Discovery, multicast và địa chỉ tạm thời ảnh hưởng đến chính sách và truy vết.
- **DNS, NAT, DHCP, VPN và proxy** tạo thêm các phép ánh xạ giữa tên miền, người dùng, địa chỉ và phiên; điều tra sự cố phải giữ đúng thời điểm và vị trí quan sát.
- **Bảo mật theo lớp không thể chỉ dựa vào IP**: hãy kết hợp phân đoạn, xác thực, quyền ứng dụng, TLS, kiểm soát egress, IDS/IPS, log và quy trình ứng phó.

Khi gặp một gói tin lạ, ba câu hỏi hữu ích nhất là: **Địa chỉ này hiện thuộc đâu? Gói tin đi qua ranh giới nào? Ngoài IP, còn bằng chứng gì để xác định đây là kết nối được phép?** Trả lời được ba câu hỏi ấy sẽ giúp bạn đọc lưu lượng chính xác hơn và đặt kiểm soát bảo mật ở đúng chỗ.
