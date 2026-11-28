# Lộ trình từ packet cơ bản đến kiến trúc Zero Trust

> **Chương:** Nhập môn  
> **Phạm vi:** SECURITY_NETWORK_SECURITY — bảo mật mạng từ phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và hạ tầng đám mây đến phân tích lưu lượng, mô hình hóa mối đe dọa và thiết kế kiến trúc mạng an toàn.

Một kiến trúc Zero Trust có nhiều thành phần như danh tính, trạng thái thiết bị, chính sách truy cập, phân đoạn và giám sát. Tuy nhiên, muốn thiết kế hoặc khắc phục sự cố các thành phần này, trước hết cần hiểu **một gói tin đi từ đâu đến đâu, qua những lớp kiểm soát nào và để lại bằng chứng gì**. Bài học xây dựng lộ trình theo thứ tự đó: bắt đầu từ packet, hình thành tư duy về luồng mạng, rồi bổ sung từng lớp phòng vệ trước khi ghép thành kiến trúc Zero Trust.

## 1. Mục tiêu sau bài học

Sau khi hoàn thành lộ trình và các bài thực hành, bạn có thể:

1. Đọc một luồng TCP/IP cơ bản, phân biệt frame, packet, segment, cổng dịch vụ, DNS và TLS; dùng công cụ để tìm điểm lỗi hoặc điểm kiểm soát.
2. Vẽ sơ đồ phân đoạn mạng và diễn đạt chính sách cho phép/từ chối theo **nguồn, đích, dịch vụ và mục đích nghiệp vụ**.
3. Giải thích vai trò và giới hạn của firewall, VPN, IDS/IPS, xác thực kết nối, DNS security, Wi-Fi security và các bộ lọc mạng trong cloud.
4. Nhận diện tài sản, ranh giới tin cậy, đường tấn công và bằng chứng giám sát khi mô hình hóa mối đe dọa.
5. Thiết kế một luồng truy cập Zero Trust với xác thực danh tính, đánh giá thiết bị, cấp quyền tối thiểu, thực thi chính sách và nhật ký kiểm toán.

**Nguyên tắc học xuyên suốt:** mọi biện pháp phòng vệ phải trả lời được ba câu hỏi: *đang bảo vệ tài sản nào, chặn hoặc phát hiện luồng nào, và kiểm chứng bằng dữ liệu nào?*

## 2. Bản đồ các chặng học

| Chặng | Câu hỏi trọng tâm | Sản phẩm cần tự làm được |
| --- | --- | --- |
| 1. Packet và giao thức | Một yêu cầu HTTPS thực sự tạo những luồng gì? | Sơ đồ đường đi và một bản phân tích packet capture |
| 2. Địa chỉ hóa và phân đoạn | Các máy có thể nói chuyện với nhau ở đâu? | Bản đồ subnet, vùng tin cậy và luồng được phép |
| 3. Firewall và chính sách | Ai được phép kết nối qua ranh giới mạng? | Ma trận rule, kiểm thử cho phép/từ chối |
| 4. VPN, TLS và xác thực kết nối | Người dùng và dịch vụ chứng minh quyền kết nối thế nào? | Thiết kế kênh mã hóa và cơ chế xác thực phù hợp |
| 5. IDS/IPS và giám sát | Hoạt động đáng ngờ được nhìn thấy ở đâu? | Bộ log tối thiểu, giả thuyết phát hiện và quy trình xử lý |
| 6. DNS, Wi-Fi và cloud | Các bề mặt tấn công chuyên biệt thay đổi cách phòng vệ ra sao? | Kiểm soát DNS, mạng không dây và luồng mạng cloud |
| 7. Threat modeling | Kẻ tấn công có thể đi từ điểm nào đến tài sản quan trọng? | Sơ đồ luồng dữ liệu, bảng nguy cơ và biện pháp giảm thiểu |
| 8. Zero Trust | Quyết định truy cập được đưa ra và thu hồi bằng tín hiệu nào? | Kiến trúc đề xuất, chính sách và kịch bản xác minh |

Đây là **thứ tự phụ thuộc kiến thức**, không phải lời hứa rằng chỉ cần cấu hình đủ tám chặng là đạt Zero Trust. Mỗi chặng phải đi kèm quan sát, thử nghiệm và giải thích giới hạn của cơ chế đang dùng.

## 3. Chặng 1 — Đọc được packet và một phiên kết nối

### 3.1. Từ frame đến dữ liệu ứng dụng

Giả sử máy nhân viên truy cập một ứng dụng nội bộ qua HTTPS. Dữ liệu ứng dụng được đóng gói qua nhiều lớp:

| Lớp nhìn nhận | Đơn vị / thông tin tiêu biểu | Câu hỏi bảo mật |
| --- | --- | --- |
| Liên kết (Ethernet/Wi-Fi) | Frame, địa chỉ MAC, VLAN | Thiết bị nằm ở mạng nào, có vượt được ranh giới L2 không? |
| Mạng (IP) | Packet, IP nguồn/đích, TTL/Hop Limit | Gói tin đi qua router nào, đến subnet nào? |
| Giao vận (TCP/UDP) | Segment/datagram, port, cờ TCP, trạng thái phiên | Đây là dịch vụ gì, phiên được thiết lập hay bị từ chối? |
| Mã hóa phiên (TLS, khi được dùng) | Bắt tay TLS, chứng chỉ, khóa phiên | Đúng đầu cuối đã được xác thực chưa; dữ liệu có được mã hóa không? |
| Ứng dụng | HTTPS, DNS, SSH, giao thức cơ sở dữ liệu | Người dùng được làm hành động gì với tài nguyên? |

**Frame, packet và segment không đồng nghĩa.** Ethernet chuyển frame trong một liên kết; IP chuyển packet qua các mạng; TCP quản lý kết nối bằng segment, số thứ tự, xác nhận và truyền lại. UDP truyền datagram và không tự cung cấp bắt tay hoặc đảm bảo truyền tin như TCP. Ở các môi trường hiện đại, HTTP/3 chạy trên QUIC qua UDP; không nên đồng nhất mọi truy cập HTTPS với TCP/443.

Ví dụ luồng truy cập ứng dụng dùng HTTPS qua TCP:

1. Máy khách tìm địa chỉ IP của tên miền bằng DNS, trừ khi có kết quả cache hoặc cơ chế phân giải khác.
2. Máy khách xác định đích cùng hay khác subnet; nếu khác subnet, chuyển frame đến default gateway sau khi phân giải địa chỉ liên kết bằng ARP (IPv4) hoặc Neighbor Discovery (IPv6).
3. Với TCP, hai phía trao đổi SYN, SYN-ACK, ACK để thiết lập phiên. Firewall có trạng thái có thể dùng thông tin phiên để xử lý gói phản hồi.
4. TLS tiến hành bắt tay, xác thực máy chủ qua chứng chỉ và tạo khóa bảo vệ dữ liệu. Chỉ bắt tay TCP thành công **chưa** chứng minh TLS hoặc quyền truy cập ứng dụng đã thành công.
5. Ứng dụng xử lý HTTP request, xác thực người dùng và phân quyền thao tác; phản hồi đi qua các lớp mạng tương ứng.

Một **địa chỉ IP hợp lệ không chứng minh danh tính người dùng**; một kết nối TCP thành công không chứng minh người dùng có quyền đọc dữ liệu. Các kiểm soát ở lớp mạng và lớp ứng dụng bổ sung cho nhau.

### 3.2. Những gì quan sát được và không quan sát được

Trong bản capture, có thể thường thấy IP, cổng, thời điểm, kích thước, số gói và trạng thái kết nối. Với lưu lượng TLS được cấu hình đúng, nội dung HTTP nhạy cảm được mã hóa; thiết bị quan sát giữa đường không mặc nhiên đọc được nội dung. Một số metadata như DNS truyền thống hoặc thông tin bắt tay có thể hiển thị tùy giao thức và cấu hình; DNS mã hóa hoặc ECH có thể làm giảm mức hiển thị đó.

Khi phân tích lỗi, phân biệt:

- **Không phân giải tên:** kiểm tra DNS resolver, kết quả trả về và chính sách DNS.
- **Không tới đích:** kiểm tra route, subnet, ACL và firewall.
- **Không lập được phiên TCP:** kiểm tra SYN/SYN-ACK, cổng lắng nghe, rule và đường phản hồi.
- **TLS thất bại:** kiểm tra chuỗi chứng chỉ, hostname, thời gian hệ thống và cấu hình phiên bản giao thức.
- **HTTP 401/403:** đã chạm tới ứng dụng, nhưng thiếu xác thực hoặc quyền; vấn đề có thể không nằm ở firewall.

### 3.3. Lab quan sát đầu tiên

Thực hiện trong mạng thực hành mà bạn có quyền quản trị. Các địa chỉ 10.10.x.x và tên miền *.lab.test trong bài đều là **giả định**, cần thay bằng cấu hình lab thực tế.

~~~bash
# Quan sát địa chỉ, đường đi, socket và phân giải tên trên Linux
ip addr show
ip route
ss -tn
dig @10.10.40.53 app.lab.test

# Bắt tối đa 30 gói tới máy ứng dụng thử nghiệm
sudo tcpdump -ni eth0 -c 30 'host 10.10.20.10 and (tcp port 443 or udp port 53)'

# Xem giai đoạn kết nối và thông tin chứng chỉ từ phía client
curl -v https://app.lab.test/
~~~

Lưu bản capture và trả lời: máy nguồn/đích là gì, kết nối dùng TCP hay UDP, DNS có xảy ra không, thời điểm bắt tay, kết quả TLS và mã phản hồi ứng dụng là gì. Nếu không thấy DNS trong capture, kiểm tra cache, giao diện thu thập hoặc resolver thay vì kết luận là không có phân giải tên. File PCAP có thể chứa thông tin nội bộ hoặc dữ liệu nhạy cảm; chỉ thu thập, chia sẻ và lưu trữ trong phạm vi được phép.

**Điều kiện qua chặng:** giải thích được một truy cập thành công và một truy cập thất bại bằng các bằng chứng packet, DNS, route hoặc log, thay vì suy đoán từ thông báo lỗi trình duyệt.

## 4. Chặng 2 — Địa chỉ hóa, tuyến đường và phân đoạn mạng

### 4.1. Vùng mạng và ranh giới tin cậy

Subnet và VLAN giúp tổ chức hệ thống, giảm miền quảng bá ở lớp 2 và tạo điểm áp chính sách. Tuy nhiên, **chỉ tạo VLAN không tự động ngăn mọi kết nối giữa VLAN**: router, switch lớp 3, firewall, ACL hoặc cơ chế tương đương phải thực thi ranh giới khi lưu lượng được định tuyến.

Một lab có thể dùng bốn vùng:

| Vùng | Dải IP mẫu | Tài sản | Mức tiếp xúc dự kiến |
| --- | --- | --- | --- |
| User | 10.10.10.0/24 | Máy người dùng quản trị | Chỉ tới ứng dụng và dịch vụ được cấp |
| App | 10.10.20.0/24 | Web/API, 10.10.20.10 | Chỉ nhận kết nối cần thiết từ user/gateway |
| Data | 10.10.30.0/24 | Database, 10.10.30.10 | Chỉ chấp nhận từ service được phép |
| Management | 10.10.40.0/24 | DNS nội bộ, log, quản trị | Chỉ các vai trò và luồng vận hành xác định |

**North–south traffic** thường chỉ lưu lượng đi vào/ra một ranh giới như Internet ↔ trung tâm dữ liệu. **East–west traffic** thường chỉ liên lạc giữa các máy hoặc workload trong nội bộ. Một cuộc xâm nhập thường có thể chuyển từ điểm vào ban đầu sang lateral movement ở hướng east–west, vì thế không thể chỉ bảo vệ biên Internet.

### 4.2. Vẽ sơ đồ trước khi đặt rule

~~~mermaid
flowchart LR
    U["User 10.10.10.0/24"] -->|"HTTPS 443"| F["Firewall / ACL"]
    F --> A["App 10.10.20.10"]
    A -->|"DB 5432"| D["Data 10.10.30.10"]
    A -->|"DNS 53"| M["Resolver 10.10.40.53"]
    A -.->|"Telemetry"| L["Log / monitoring"]
    U -.->|"Không cho phép trực tiếp"| D
~~~

Phân biệt **địa chỉ mạng** (CIDR, route, subnet), **vị trí thực thi** (gateway, host firewall, security group, network policy) và **quyết định cho phép**. Một sơ đồ chỉ có đường nối mà không ghi dịch vụ và bên thực thi chưa đủ để kiểm toán chính sách.

## 5. Chặng 3 — Firewall, ACL và chính sách truy cập tối thiểu

Firewall lọc lưu lượng dựa trên bộ điều kiện như IP, protocol, port và trạng thái phiên; các giải pháp nâng cao còn hiểu ngữ cảnh ứng dụng, danh tính hoặc nội dung ở mức có thể quan sát. ACL thường là tập luật lọc ở một điểm mạng. **Stateful firewall** theo dõi trạng thái kết nối để xử lý luồng phản hồi; **stateless filter** đánh giá từng gói theo rule, nên có thể cần quy tắc hai chiều.

Trước khi cấu hình, hãy lập **ma trận luồng**: mỗi dòng phải có chủ thể, đích, cổng, lý do nghiệp vụ, nơi thực thi và cách xác minh.

| Nguồn | Đích | Dịch vụ | Quyết định | Lý do |
| --- | --- | --- | --- | --- |
| User được cấp quyền | App gateway | TCP/443 | Allow | Sử dụng giao diện ứng dụng |
| App service | Database | TCP/5432 | Allow | Truy xuất dữ liệu của ứng dụng |
| App service | DNS nội bộ | UDP/TCP 53 | Allow | Phân giải tên được quản lý |
| User | Database | TCP/5432 | Deny | Không truy cập trực tiếp dữ liệu |
| Mọi nguồn khác | Các vùng nội bộ | Mọi cổng còn lại | Deny theo thiết kế | Giảm bề mặt tấn công |

Ví dụ **pseudo-policy** để diễn đạt ý định; không phải cú pháp có thể chạy trên một thiết bị cụ thể:

~~~text
ALLOW src=user-authorized     dst=app-gateway      proto=tcp dst_port=443
ALLOW src=app-service         dst=db-10.10.30.10  proto=tcp dst_port=5432
ALLOW src=app-service         dst=dns-10.10.40.53 proto=udp,tcp dst_port=53
DENY  src=user-zone           dst=data-zone        proto=any
DENY  src=any                 dst=internal         proto=any   # default policy
~~~

Trong hệ thống thật, rule ở mức IP/port chỉ là **lớp hạn chế đường đi**. Nguồn “user-authorized” hoặc “app-service” phải được hiện thực qua biên truy cập, danh tính workload, cơ chế xác thực hoặc đối tượng rule phù hợp; không thể tin rằng chỉ đặt tên như vậy là firewall xác minh được danh tính.

Những điểm cần phân biệt:

- **NAT** thay đổi địa chỉ/cổng trong luồng mạng; NAT tự thân không thay cho kiểm soát truy cập hoặc xác thực.
- **WAF** phân tích các mẫu yêu cầu web ở tầng ứng dụng; WAF không thay cho chính sách phân đoạn hoặc phân quyền nghiệp vụ.
- **Lọc inbound và egress:** chặn nguồn ngoài không đủ nếu máy bị chiếm quyền vẫn gửi dữ liệu ra Internet không giới hạn.
- **Mặc định từ chối** là nguyên tắc thiết kế rule; phải kiểm kê luồng cần thiết, gồm DNS, thời gian, chứng chỉ, health check và giám sát, để tránh làm hỏng vận hành.

**Điều kiện qua chặng:** kiểm thử được một luồng được phép và một luồng bị chặn, xác định đúng điểm áp rule và chứng minh từ log hoặc capture. Với rule từ chối, phải kiểm tra cả đường kết nối trực tiếp lẫn đường đi vòng qua các vùng trung gian.

## 6. Chặng 4 — Kênh bảo mật và xác thực kết nối

### 6.1. TLS, VPN và quyền ứng dụng là các vấn đề khác nhau

| Cơ chế | Bảo vệ chính | Không tự bảo đảm |
| --- | --- | --- |
| TLS (ví dụ HTTPS) | Bảo mật và tính toàn vẹn kênh client ↔ server; xác thực server qua chứng chỉ | Người dùng được quyền nào trong ứng dụng |
| mTLS | Hai đầu kết nối cùng xác thực qua chứng chỉ | Quyền nghiệp vụ chính xác của mỗi request |
| VPN (ví dụ IPsec hoặc WireGuard) | Tạo đường truyền được mã hóa giữa các điểm/thiết bị tham gia | Mọi ứng dụng trong mạng VPN đều an toàn hoặc có quyền phù hợp |
| 802.1X/EAP với hệ thống danh tính | Kiểm soát thiết bị/người dùng trước khi cấp truy cập vào mạng có dây hoặc Wi-Fi | Mỗi kết nối sau đó đều được cấp quyền tối thiểu |
| MFA và xác thực ứng dụng | Tăng mức tin cậy về chủ thể đăng nhập | Thiết bị và mạng đã an toàn tuyệt đối |

Một VPN truyền thống có thể đưa thiết bị từ xa vào một phạm vi mạng tương đối rộng. Thiết kế an toàn cần xét **split tunnel so với full tunnel**, DNS đi theo đường nào, chính sách thiết bị, MFA, quyền subnet nào được phép và log phiên. Tùy nhu cầu, truy cập theo từng ứng dụng qua ZTNA có thể giảm phạm vi mạng mà người dùng nhìn thấy.

Khi dùng TLS, cần kiểm tra hostname khớp chứng chỉ, chuỗi tin cậy, thời hạn, cấu hình phiên bản/thuật toán hiện hành và cách quản lý khóa. **Mã hóa đường truyền không thay thế xác thực người dùng, kiểm tra quyền hay bảo vệ đầu cuối.**

### 6.2. Bài tập thiết kế

Cho hai nhóm người dùng là nhân viên và nhà thầu cần dùng cùng cổng HTTPS nhưng chỉ nhân viên quản trị được vào giao diện vận hành. Hãy mô tả rõ:

1. Nơi xác thực danh tính và MFA.
2. Kênh bảo vệ lưu lượng (TLS; VPN/ZTNA nếu có).
3. Điểm áp chính sách phân quyền ứng dụng theo vai trò.
4. Cách thu hồi phiên khi hết hợp đồng, thay đổi quyền hoặc thiết bị không còn đạt yêu cầu.

Kết quả đúng phải cho thấy **truy cập được mạng** và **được phép làm thao tác** là hai quyết định riêng.

## 7. Chặng 5 — IDS/IPS, telemetry và phản ứng sự cố

**IDS** tạo tín hiệu phát hiện và cảnh báo; **IPS** có thể can thiệp để chặn lưu lượng dựa trên chính sách và vị trí triển khai. IDS/IPS có thể nhận diện dấu hiệu đã biết, mẫu bất thường hoặc hành vi vi phạm chính sách, nhưng không bảo đảm phát hiện mọi tấn công, đặc biệt khi nội dung bị mã hóa hoặc cảm biến không thấy luồng.

| Nguồn quan sát | Ví dụ dữ liệu | Dùng để trả lời |
| --- | --- | --- |
| Firewall/ACL | Allow/deny, địa chỉ, cổng, rule, thời điểm | Luồng bị chặn ở đâu? |
| Flow log/NetFlow tương đương | Nguồn/đích, cổng, byte, thời lượng | Có lateral movement hoặc chuyển dữ liệu bất thường không? |
| DNS resolver | Tên miền hỏi, kết quả, máy hỏi, thời gian | Máy nào liên lạc tên miền lạ hoặc thất bại lặp lại? |
| IDS/IPS | Chữ ký, mức nghiêm trọng, hướng lưu lượng | Có dấu hiệu khai thác hoặc quét mạng không? |
| Identity/IdP/ZTNA | Đăng nhập, MFA, posture, policy decision | Ai được cấp quyền, ở ngữ cảnh nào? |
| Endpoint và ứng dụng | Sự kiện tiến trình, lỗi xác thực, request | Hoạt động trên host có khớp với sự kiện mạng không? |

Hãy định nghĩa một giả thuyết phát hiện có thể kiểm chứng, chẳng hạn: *“Máy thuộc vùng User cố gắng mở kết nối TCP trực tiếp tới nhiều IP ở vùng Data trong thời gian ngắn.”* Tín hiệu gồm số đích khác nhau, lần deny, danh tính thiết bị và sự kiện endpoint. Đặt tiêu chí điều tra trước khi coi là sự cố: hành vi quét kiểm kê hợp lệ có thể là **false positive**; thiếu cảm biến hoặc traffic mã hóa có thể tạo **false negative**.

Quy trình xử lý căn bản: **phát hiện → xác minh bối cảnh → khoanh vùng → ngăn chặn phù hợp → khắc phục → phục hồi → rút kinh nghiệm**. Đồng bộ thời gian và lưu log theo chính sách bảo vệ dữ liệu để có thể liên hệ các sự kiện. Không tự động cô lập thiết bị chỉ dựa trên một cảnh báo chưa được đánh giá tác động.

**Điều kiện qua chặng:** lập được timeline từ tối thiểu hai nguồn log cho một sự kiện giả lập, chỉ ra bằng chứng hỗ trợ và điểm còn chưa chắc chắn.

## 8. Chặng 6 — Bảo vệ DNS, mạng không dây và hạ tầng cloud

### 8.1. DNS: lớp điều hướng cần được bảo vệ

DNS gắn tên dịch vụ với thông tin truy cập và thường xuất hiện trước yêu cầu ứng dụng. Những rủi ro cần hiểu gồm cấu hình resolver sai, câu trả lời bị giả mạo, tên miền độc hại, rò rỉ truy vấn và kênh DNS không được kiểm soát.

- **DNSSEC** giúp kiểm tra tính xác thực và toàn vẹn của dữ liệu DNS được ký trên chuỗi tin cậy; không mã hóa truy vấn.
- **DoT/DoH** mã hóa đường trao đổi DNS giữa client và resolver phù hợp; bản thân cơ chế mã hóa không chứng minh rằng tên miền là an toàn.
- **Resolver do tổ chức quản lý** có thể áp dụng lọc tên miền, log có kiểm soát, tách vùng nội bộ và cảnh báo; cần xử lý trường hợp thiết bị dùng resolver riêng hoặc DNS mã hóa ngoài chính sách.

Thử nghiệm: truy vấn một tên nội bộ, một tên không tồn tại, và so sánh DNS log với lưu lượng ứng dụng. Hãy phân biệt **resolver trả lời được tên** với **kết nối đến IP đích được phép**.

### 8.2. Wi-Fi: ranh giới bắt đầu trước cả IP

Mạng không dây có các rủi ro như điểm truy cập giả, cấu hình xác thực yếu, chia sẻ khóa quá rộng và mạng khách nhìn thấy hệ thống nội bộ. Ưu tiên cấu hình bảo mật phù hợp năng lực thiết bị, ví dụ WPA3-Enterprise và 802.1X trong môi trường đáp ứng được; môi trường chuyển tiếp có thể cần cơ chế tương thích có quản lý. Tách guest/IoT và mạng nhân viên, giới hạn quyền theo vai trò và giám sát điểm truy cập trái phép. **Ẩn SSID hoặc chỉ lọc địa chỉ MAC không phải lớp xác thực đáng tin cậy.**

Đầu ra cần có: bảng ánh xạ loại thiết bị/người dùng → cơ chế xác thực → VLAN/segment được cấp → đích có thể truy cập → cách ghi nhận sự kiện.

### 8.3. Cloud và workload động

Trong cloud, subnet, route table, security group, network ACL, private endpoint, load balancer và log mạng thay thế hoặc bổ sung thiết bị vật lý; chi tiết **stateful/stateless khác nhau theo nhà cung cấp**. Ví dụ trong AWS, security group thường có trạng thái còn network ACL không có trạng thái; không suy rộng nguyên tắc đó cho mọi sản phẩm cloud.

Một thiết kế cần quan tâm cả public exposure, kết nối qua mạng riêng, quyền quản trị, egress, khóa/secret và quyền dịch vụ. Trong Kubernetes, NetworkPolicy chỉ có hiệu lực khi giải pháp mạng thực thi hỗ trợ; bản thân NetworkPolicy không thay cho xác thực service-to-service, RBAC hoặc quản lý secret.

**Bài tập chuyển đổi:** lấy kiến trúc User → App → Data ở phần 4, triển khai sơ đồ logic trên virtual network cloud; đặt App sau lớp ingress phù hợp, Data ở vùng private, giới hạn nguồn tới Data, bật flow log và xác định thành phần nào chịu trách nhiệm thực thi từng rule.

## 9. Chặng 7 — Mô hình hóa mối đe dọa theo luồng dữ liệu

Thay vì bắt đầu từ danh sách sản phẩm bảo mật, hãy bắt đầu từ **tài sản cần bảo vệ**: dữ liệu khách hàng, thông tin xác thực, bí mật dịch vụ, khả năng vận hành, hoặc máy quản trị. Vẽ sơ đồ luồng dữ liệu, đánh dấu các vùng tin cậy và điểm đổi chủ thể. Với mỗi đường đi, hỏi ai có thể làm giả nguồn, sửa thông điệp, xem dữ liệu hoặc đi tiếp sau khi chiếm một máy.

Ví dụ dùng STRIDE làm khung gợi ý:

| Nguy cơ | Tình huống trong lab | Kiểm soát liên quan | Bằng chứng cần kiểm tra |
| --- | --- | --- | --- |
| Spoofing (giả mạo) | Đăng nhập bằng danh tính bị đánh cắp | MFA, xác thực ứng dụng, mTLS cho service | Log IdP, chứng chỉ, policy decision |
| Tampering (sửa đổi) | Can thiệp dữ liệu trên đường truyền | TLS, bảo vệ khóa, kiểm tra toàn vẹn | Kết quả bắt tay, log lỗi chứng chỉ |
| Repudiation (chối bỏ) | Thao tác quản trị thiếu nhật ký | Audit log gắn danh tính và thời gian | Log truy vết thao tác |
| Information disclosure (lộ dữ liệu) | User truy cập trực tiếp Data | Segmentation, phân quyền, mã hóa | Rule deny, log DB và ứng dụng |
| Denial of service (gián đoạn) | Lưu lượng quá tải gateway | Giới hạn lưu lượng, kiến trúc dự phòng, điều tra | Chỉ số tải, log ở biên |
| Elevation of privilege (leo thang quyền) | App bị chiếm rồi truy cập tài nguyên quản trị | Quyền tối thiểu, kiểm soát east–west, workload identity | Luồng bị từ chối, sự kiện identity |

STRIDE giúp đặt câu hỏi, nhưng **không phải một bộ rule tự động**. Cần xác định đường tấn công thực tế, mức độ ảnh hưởng, khả năng xảy ra, biện pháp hiện có, rủi ro còn lại và người chịu trách nhiệm. Đặc biệt, xem xét kịch bản **giả định một máy đã bị xâm nhập**: máy đó có thể quét và kết nối sang máy nào, dùng quyền nào và để lại dấu vết gì?

**Điều kiện qua chặng:** mô tả được ít nhất một chuỗi tấn công gồm điểm xâm nhập → quyền đạt được → lateral movement hoặc truy cập dữ liệu → cách phát hiện/chặn ở từng đoạn.

## 10. Chặng 8 — Từ phòng vệ theo vùng mạng đến kiến trúc Zero Trust

### 10.1. Tư tưởng cốt lõi

Zero Trust là cách thiết kế trong đó **không cấp sự tin cậy mặc định chỉ vì một chủ thể đang ở mạng nội bộ hoặc đã đi qua VPN**. Trước khi cho phép truy cập tài nguyên, hệ thống đánh giá danh tính, trạng thái thiết bị, ngữ cảnh, chính sách và độ nhạy tài nguyên; chỉ cấp quyền cần thiết và tiếp tục thu thập tín hiệu để điều chỉnh hoặc thu hồi quyền. Đây là các ý chính tương thích với mô hình Zero Trust Architecture trong NIST SP 800-207.

Ba mục tiêu thực hành:

1. **Verify explicitly:** xác minh chủ thể và các tín hiệu liên quan thay vì dựa đơn độc vào vị trí IP.
2. **Least-privilege access:** cấp quyền nhỏ nhất theo tài nguyên, hành động và thời gian cần thiết.
3. **Assume breach:** thiết kế sao cho một máy hoặc một danh tính bị chiếm không mở sẵn đường đến toàn bộ hệ thống.

Zero Trust **không phải một sản phẩm, một VPN mới, một firewall mạnh hơn hoặc việc xóa hoàn toàn các lớp mạng**. Nó cần cơ chế nhận dạng, thực thi, chính sách, giám sát và vận hành được kết nối với nhau.

### 10.2. Các thành phần trong một quyết định truy cập

| Thành phần | Vai trò trong kiến trúc |
| --- | --- |
| Identity Provider (IdP), MFA | Xác thực người dùng, dịch vụ và cung cấp tín hiệu phiên đăng nhập |
| Device posture / endpoint security | Đánh giá thiết bị có thuộc quản lý, cập nhật, được bảo vệ hay đang có tín hiệu rủi ro |
| Policy Engine / Policy Decision Point (PDP) | Quyết định cho phép, từ chối hoặc yêu cầu thêm điều kiện theo chính sách |
| Policy Enforcement Point (PEP) | Thực thi quyết định tại cổng truy cập, proxy, host, service mesh hoặc điểm kiểm soát phù hợp |
| Application authorization / workload identity | Kiểm tra quyền hành động và danh tính dịch vụ ở mức tài nguyên |
| Telemetry, SIEM, audit | Cung cấp bằng chứng cho giám sát, điều tra và điều chỉnh quyết định |

~~~mermaid
flowchart LR
    U["Người dùng / dịch vụ"] -->|"Yêu cầu tài nguyên"| PEP["PEP: điểm thực thi"]
    PEP -->|"Xin quyết định"| PDP["PDP: chính sách"]
    ID["IdP / MFA"] --> PDP
    DEV["Tín hiệu thiết bị"] --> PDP
    RISK["Rủi ro và độ nhạy tài nguyên"] --> PDP
    PDP -->|"Cho phép có điều kiện"| PEP
    PDP -->|"Từ chối"| STOP["Không cấp truy cập"]
    PEP -->|"Luồng được cấp quyền"| APP["Ứng dụng / API"]
    PEP -.-> LOG["Giám sát / audit"]
    APP -.-> LOG
~~~

Đây là **sơ đồ logic**. Trong hệ thống thật, nhiều chức năng có thể được gộp vào một sản phẩm hoặc phân tán ở nhiều lớp. Việc kiểm tra lại điều kiện truy cập có thể diễn ra theo phiên, sự kiện, mức rủi ro hoặc chính sách; không có nghĩa mọi packet đều phải gọi tới PDP.

### 10.3. Kịch bản áp dụng trên kiến trúc User → App → Data

Giả sử nhân viên dùng thiết bị quản lý để xem báo cáo, còn nhà thầu chỉ được xem trang hỗ trợ. App xử lý dữ liệu qua database ở vùng riêng.

| Chủ thể / yêu cầu | Điều kiện | Quyết định mong muốn | Điểm thực thi |
| --- | --- | --- | --- |
| Nhân viên xem báo cáo | Danh tính hợp lệ, MFA, thiết bị đáp ứng posture, vai trò phù hợp | Cho phép phiên HTTPS tới ứng dụng báo cáo | ZTNA/gateway và ứng dụng |
| Nhà thầu vào trang hỗ trợ | Danh tính hợp lệ, MFA và phạm vi hợp đồng đang hiệu lực | Chỉ cho phép tài nguyên hỗ trợ | Gateway và ứng dụng |
| User bất kỳ tới Database | Không có lý do nghiệp vụ truy cập DB trực tiếp | Từ chối TCP/5432 từ vùng User | Segmentation firewall / cloud policy |
| App service tới Database | Workload identity hợp lệ, luồng dịch vụ và quyền DB được cấp | Cho phép kết nối và thao tác cụ thể | Network policy, mTLS khi phù hợp, DB authorization |
| Máy bị đánh dấu rủi ro cao | Posture không đạt hoặc có cảnh báo nghiêm trọng đã được xác minh | Yêu cầu khắc phục, hạn chế hoặc thu hồi phiên theo chính sách | PDP/PEP và quản lý phiên |

Một lần truy cập hợp lệ có chuỗi quyết định như sau:

1. Người dùng yêu cầu tài nguyên, PEP buộc yêu cầu đi qua điểm kiểm soát.
2. IdP và cơ chế thiết bị cung cấp tín hiệu cho PDP; PDP xét chính sách theo tài nguyên và ngữ cảnh.
3. Nếu hợp lệ, PEP cấp đường đến **đúng ứng dụng**; ứng dụng vẫn kiểm tra quyền đối với chức năng và dữ liệu.
4. App gọi DB bằng danh tính dịch vụ có quyền giới hạn; đường mạng chỉ mở từ App đến DB.
5. Hệ thống thu log quyết định, truy cập và bất thường. Khi quyền người dùng bị thu hồi hoặc rủi ro thay đổi, cơ chế quản lý phiên và thực thi phải phản ánh thay đổi đó.

**Cần thử cả trường hợp từ chối:** thiếu MFA, thiết bị không đạt điều kiện, quyền ứng dụng không phù hợp, User cố truy cập DB trực tiếp, hoặc App truy cập sai cổng. Không có kiểm thử deny thì chưa có bằng chứng rằng quyền tối thiểu được thực thi.

### 10.4. Chuyển đổi theo từng bước

Một hệ thống đang dùng VPN, subnet và firewall không cần thay đổi tất cả trong một lần. Trình tự thực tế là: **kiểm kê tài nguyên và luồng hiện có → chuẩn hóa danh tính và MFA → giảm quyền mạng/ứng dụng → đặt PEP trước tài nguyên quan trọng → xác thực workload → bổ sung tín hiệu posture và giám sát → đo, điều chỉnh, mở rộng phạm vi**. Ở mỗi bước cần có chủ sở hữu chính sách, phương án xử lý lỗi cấp quyền và kịch bản phục hồi để tránh ảnh hưởng hệ thống quan trọng.

## 11. Đồ án xuyên suốt: bảo vệ một ứng dụng ba tầng

Hãy dựng môi trường thử nghiệm cô lập gồm User, App, Data và Management. Có thể dùng VM, container và các bộ điều khiển mạng thích hợp; thứ tự bài tập quan trọng hơn lựa chọn sản phẩm.

| Mốc | Việc triển khai | Minh chứng nộp / tiêu chí đạt |
| --- | --- | --- |
| A. Quan sát | Tạo một request HTTPS; xem DNS, route, TCP/QUIC và TLS | Capture hoặc flow log có chú giải, chỉ ra đúng điểm lỗi giả lập |
| B. Phân đoạn | Tách User/App/Data/Management; dựng sơ đồ luồng | Chứng minh User không có tuyến truy cập tự do tới Data |
| C. Rule | Chỉ cho phép User → App và App → DB cần thiết; thiết lập egress rõ ràng | Ma trận rule, thử nghiệm allow và deny có log |
| D. Kênh và danh tính | Bảo vệ HTTPS, thêm xác thực người dùng và cơ chế remote access phù hợp | Thử chứng chỉ không hợp lệ, quyền thấp và phiên hợp lệ |
| E. Phát hiện | Bật firewall/DNS/identity log, tạo tín hiệu quét hoặc truy cập sai quyền trong lab | Timeline sự kiện, phân biệt cảnh báo và sự cố |
| F. Bề mặt mở rộng | Tách Wi-Fi guest hoặc mô phỏng kiểm soát cloud | Ma trận segment/identity/đích và log kiểm chứng |
| G. Threat model | Chọn một tài sản quan trọng, mô tả tấn công từ máy User bị chiếm | Sơ đồ trust boundary, bảng nguy cơ và rủi ro còn lại |
| H. Zero Trust | Đặt PEP, điều kiện danh tính/posture, quyền ứng dụng và giới hạn App → DB | Kiểm thử cấp, từ chối, thu hồi quyền và lateral movement |

Một bộ hồ sơ nộp gọn nhưng đủ bằng chứng gồm: **sơ đồ kiến trúc, bảng luồng được phép, chính sách truy cập, ảnh/chứng cứ kiểm thử, timeline giám sát, threat model và mô tả cách thu hồi quyền**. Không cần triển khai sản phẩm thương mại để hiểu logic, nhưng phải nêu rõ điểm nào đang được *mô phỏng* và điểm nào *thật sự có cơ chế thực thi*.

## 12. Những sai lầm cần nhận diện sớm

| Ngộ nhận | Cách kiểm chứng đúng |
| --- | --- |
| “Ở cùng VPN hoặc VLAN thì đã đáng tin.” | Kiểm tra danh tính, tình trạng thiết bị, phạm vi tài nguyên và policy deny. |
| “Có TLS thì mọi hoạt động sau đó đều an toàn.” | Kiểm tra cả chứng chỉ, quyền người dùng, kiểm soát API và đầu cuối. |
| “Đã bật IDS nên sẽ thấy tất cả tấn công.” | Xác định vị trí cảm biến, traffic mã hóa, nguồn log bổ trợ và false negative. |
| “NAT hoặc private IP thay được firewall.” | Kiểm tra rule thực thi và kết nối east–west bên trong. |
| “Zero Trust chỉ là mua ZTNA.” | Xác minh từng tài nguyên có chính sách, điểm thực thi, thu hồi quyền và log. |
| “Rule allow trên port 443 đủ cấp quyền.” | Thử user có đúng quyền ứng dụng không và service có cần thêm xác thực không. |
| “Chỉ cần thử kết nối thành công.” | Phải có kiểm thử **không được phép** và bằng chứng deny. |

## 13. Tự kiểm tra trước khi học chuyên sâu

Hãy tự giải thích các tình huống sau, kèm sơ đồ hoặc dấu vết kiểm thử:

1. DNS trả đúng IP, nhưng client vẫn timeout khi truy cập HTTPS. Nêu thứ tự kiểm tra từ route, firewall, TCP/QUIC đến TLS và ứng dụng.
2. User không kết nối trực tiếp đến DB, nhưng App bị khai thác. Những cơ chế nào hạn chế App truy cập vượt quyền sang DB hoặc mạng Management?
3. Vì sao một VPN đã xác thực MFA vẫn có thể để lộ quá nhiều tài nguyên nếu không có phân đoạn và chính sách ứng dụng?
4. Firewall hiển thị deny liên tục vào DB. Dữ liệu nào giúp phân biệt cấu hình ứng dụng lỗi, hoạt động kiểm kê hợp lệ và hành vi dò quét đáng ngờ?
5. Khi danh tính nhân viên bị vô hiệu hóa giữa phiên, những thành phần nào phải phối hợp để hạn chế hoặc thu hồi quyền truy cập đã cấp?

Nếu có thể trả lời các câu hỏi này bằng **luồng packet → ranh giới kiểm soát → danh tính và chính sách → bằng chứng quan sát**, bạn đã có nền tảng để đi sâu vào cấu hình firewall, VPN, IDS/IPS, DNS security, Wi-Fi, network security trên cloud và thiết kế Zero Trust thực tế.

## 14. Tài liệu chuẩn để đào sâu

- **NIST SP 800-207 — Zero Trust Architecture:** các khái niệm kiến trúc, policy decision/enforcement và cách tiếp cận Zero Trust.
- **RFC 8200 — IPv6 Specification:** cấu trúc và cách xử lý gói IPv6.
- **RFC 8446 — TLS 1.3:** cơ chế bắt tay và bảo vệ kênh truyền.
- **RFC 4301 — Security Architecture for the Internet Protocol:** cơ sở kiến trúc IPsec.
- **Tài liệu Wireshark và tcpdump:** cách nhận diện giao thức và phân tích dấu vết gói tin.

Các chuẩn là điểm tựa để xác định nguyên lý; khi triển khai trên hệ điều hành, cloud hoặc thiết bị cụ thể, cần đối chiếu tài liệu của phiên bản đang sử dụng.
