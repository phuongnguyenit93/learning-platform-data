# Không kiểm tra đường bypass proxy hoặc firewall

## 1. Vấn đề: có chính sách bảo mật nhưng lưu lượng có thật sự đi qua điểm kiểm soát?

Trong chương **Sai lầm thường gặp** của học phần **SECURITY_NETWORK_SECURITY**, một lỗi kiến trúc và vận hành đặc biệt nguy hiểm là **chỉ kiểm tra cấu hình proxy hoặc firewall mà không xác minh những đường kết nối có thể đi vòng qua chúng**.

Một tổ chức có thể đầu tư vào phân đoạn mạng, firewall, VPN, IDS/IPS, DNS security, giám sát xâm nhập và hạ tầng cloud an toàn nhưng vẫn bỏ sót những luồng không đi qua điểm thực thi dự kiến. Firewall có rule chặn chặt chẽ nhưng một subnet có route ra Internet riêng; proxy yêu cầu xác thực nhưng một ứng dụng kết nối trực tiếp tới đích; kết nối IPv4 bị kiểm tra còn IPv6 lại có đường đi khác. Trong các trường hợp đó, nhận định “đã triển khai control” khác xa với “control bảo vệ toàn bộ lưu lượng thuộc phạm vi”.

Bài học này hướng đến người thiết kế và vận hành mạng an toàn, SOC, cloud/platform engineer và người kiểm thử phòng thủ. Sau khi học, người đọc có thể:

1. Giải thích thế nào là **đường bypass**, vì sao nó tồn tại và khi nào đó là ngoại lệ được phép.
2. Phân biệt **policy đã cấu hình**, **điểm thực thi thực tế** và **lưu lượng được quan sát**.
3. Lập sơ đồ đường đi và ranh giới tin cậy để tìm các nhánh chưa được kiểm soát.
4. Thiết kế phép kiểm thử có ủy quyền cho đường qua proxy/firewall và các đường ngoài dự kiến.
5. Thu bằng chứng từ routing, proxy, firewall, DNS, NAT, flow log và telemetry, kể cả khi một hệ thống không thấy sự kiện.
6. Đề xuất biện pháp giảm bypass bằng kiến trúc mạng, guardrail, kiểm thử hồi quy và ownership rõ ràng.

**Phạm vi an toàn:** mọi kiểm thử trực tiếp phải thực hiện trên hệ thống được phép, tốt nhất dùng mạng lab, tài khoản thử nghiệm, dịch vụ canary và dữ liệu tổng hợp. Không biến quy trình xác minh thành hành động vượt kiểm soát của môi trường production hoặc né cơ chế giám sát đang bảo vệ tổ chức.

## 2. Khái niệm: bypass, exception và blind spot

**Proxy** thường hoạt động như trung gian giữa client và dịch vụ đích. Với forward proxy hoặc secure web gateway, proxy có thể xác thực người dùng, áp chính sách truy cập web, ghi log URL/domain, phân loại rủi ro hoặc kiểm tra nội dung theo chính sách tổ chức.

**Firewall** thực thi chính sách ở ranh giới mạng hoặc workload, dựa vào thông tin như zone, địa chỉ, port, giao thức, trạng thái phiên và đôi khi định danh ứng dụng/người dùng. Một thiết bị chỉ bảo vệ những luồng **đi qua nó hoặc thuộc phạm vi enforcement của nó**.

**Đường bypass (bypass path)** là đường đi kết nối nằm ngoài một điểm kiểm soát mà kiến trúc dự kiến phải áp dụng. Nó có thể xuất hiện do route, giao thức, interface, cấu hình proxy, môi trường cloud, overlay, kênh khẩn cấp hoặc thiết kế phân tán.

Cần phân biệt ba khái niệm:

| Khái niệm | Diễn giải | Cách đánh giá |
| --- | --- | --- |
| **Bypass ngoài ý muốn** | Lưu lượng thuộc diện bắt buộc kiểm soát nhưng đi theo đường không được bảo vệ | Lỗ hổng coverage hoặc policy enforcement |
| **Ngoại lệ được phê duyệt** | Một luồng đặc biệt được phép dùng đường khác, có owner và biện pháp bù trừ | Đánh giá theo phạm vi, thời hạn, rủi ro và telemetry |
| **Đường không thuộc phạm vi** | Lưu lượng vốn không cần đi qua control này theo kiến trúc | Không tự coi là lỗ hổng; ghi rõ boundaries |
| **Điểm mù quan sát** | Có thể có luồng nhưng log/sensor không đủ xác nhận đường đi | Khoảng trống bằng chứng, cần kiểm tra thêm |

Một luồng đi ngoài proxy không tự động là tấn công. Ví dụ dịch vụ nội bộ có thể cố ý không sử dụng forward proxy; DNS resolver có thể trao đổi với authoritative DNS theo đường quản trị được phép; workload đặc biệt có egress gateway riêng. Điều quan trọng là **đường đi thực tế phù hợp thiết kế đã được chấp thuận, rủi ro được kiểm soát và có bằng chứng xác minh**.

### 2.1. Bốn câu hỏi quyết định

Với một kết nối cụ thể, phải trả lời:

- **Ai phát sinh?** User, máy chủ, container, workload, account, VPN client, thiết bị IoT; định danh của nó được ghi nhận thế nào?
- **Đi đâu?** IP, FQDN, protocol, port, địa chỉ sau NAT, đích trong hoặc ngoài tổ chức.
- **Đi bằng đường nào?** Interface, route, VPN, proxy, transit gateway, firewall, NAT, service mesh, cloud endpoint.
- **Ai thực thi và ai nhìn thấy?** Policy owner, enforcement point, kết quả allow/deny, log nhận tại SOC, khả năng truy vết.

Nếu không chỉ ra được đường đi hoặc bằng chứng enforcement, không nên kết luận control đã bao phủ chỉ vì nó tồn tại trong inventory.

## 3. Vì sao sai lầm này nguy hiểm?

Giả sử doanh nghiệp quy định mọi kết nối web của máy trạm đi qua secure web gateway có xác thực, lọc tên miền và giám sát. Quản trị viên thử trình duyệt trên một máy mẫu và thấy log proxy xuất hiện, rồi kết luận toàn bộ máy trạm đã được bảo vệ.

Kết luận có thể sai vì:

- Một máy có nhiều kết nối mạng, trong đó một interface đi Internet trực tiếp.
- Một ứng dụng không dùng proxy của trình duyệt hoặc của hệ điều hành.
- Một route cụ thể tới đích được ưu tiên hơn route tới gateway kiểm tra.
- VPN split tunnel cho một số đích đi ngoài đường doanh nghiệp.
- Chính sách IPv6 không tương xứng với IPv4.
- Một kết nối dùng UDP hoặc giao thức khác không thuộc cơ chế proxy dành cho HTTP.
- Một cloud workload có public egress ngoài gateway tập trung.
- Proxy bị lỗi và client có cơ chế fallback ra kết nối trực tiếp.
- Một ngoại lệ cũ hoặc network ACL còn cho phép đường ngoài thiết kế.

Hệ quả không chỉ là mất khả năng chặn nội dung. Đường bypass còn có thể làm giảm hiệu quả **DNS security, IDS/IPS, data loss prevention, ghi log truy cập, phân tích lưu lượng và điều tra sự cố**. SOC không có log tại gateway không thể kết luận không có kết nối; có thể luồng đã đi nơi khác.

~~~mermaid
flowchart LR
    C["Client / workload"] --> P["Forward proxy\nlọc + log"]
    P --> F["Egress firewall"]
    F --> I["Dịch vụ bên ngoài"]
    C -. "Nhánh ngoài dự kiến" .-> R["Gateway/route khác"]
    R -. "Không đi qua proxy dự kiến" .-> I
    P --> L["Telemetry / SOC"]
    F --> L
    R -. "Có thể thiếu telemetry" .-> L
~~~

Sơ đồ thể hiện **rủi ro kiến trúc**, không khẳng định mọi mạng đều có nhánh bypass. Muốn xác định có tồn tại hay không cần dựa vào sơ đồ kết nối, effective routes, policy áp dụng và thử nghiệm được phép.

## 4. Một proxy hoặc firewall kiểm soát những gì?

### 4.1. Explicit forward proxy

Client hoặc ứng dụng biết địa chỉ proxy và chủ động gửi request đến nó. Cấu hình có thể đến từ chính ứng dụng, hệ điều hành, quản lý thiết bị, PAC hoặc cấu hình dịch vụ.

**Sai lầm thường gặp:** cho rằng đặt một biến cấu hình proxy trên máy đã buộc tất cả ứng dụng và giao thức dùng proxy. Trên thực tế, hỗ trợ proxy và mức tuân thủ khác nhau giữa ứng dụng, thư viện HTTP, service agent và runtime. Một số kết nối không thuộc giao thức mà proxy hỗ trợ.

Để bảo đảm lưu lượng **bắt buộc** đi qua proxy, cần kiểm soát mạng bên dưới, ví dụ chỉ cho phép kết nối egress thuộc diện áp proxy đến các địa chỉ/port proxy đã phê duyệt. Chi tiết thực thi tùy mô hình bảo vệ, không thể dựa riêng vào cài đặt phía client.

### 4.2. Transparent hoặc inline inspection

Trong kiến trúc inline, client không nhất thiết biết proxy/firewall nhưng tuyến mạng dẫn lưu lượng qua enforcement point. Kiểu này phụ thuộc mạnh vào **routing, chính sách chuyển tiếp, thiết bị HA, NAT và đường hồi đáp**.

**Sai lầm thường gặp:** kiểm tra một route mẫu trong giờ bình thường rồi bỏ qua tuyến backup, peering, cloud attachment hoặc policy-based routing. Khi route thay đổi, lưu lượng có thể không còn đi qua điểm kiểm tra.

### 4.3. Firewall và segmentation

Một firewall stateful có thể áp rule ở biên Internet, giữa zone hoặc bên trong VPC. Tuy nhiên **firewall biên không tự bảo vệ toàn bộ east–west traffic** khi các hệ thống cùng subnet, cùng security domain hoặc giao tiếp qua đường peering không được inspection.

Firewall rule “deny mọi kết nối trực tiếp” chỉ có hiệu lực ở những vị trí nó thực sự bao phủ. Một đường ngoài enforcement là lỗ hổng kiến trúc ngay cả khi rule được viết chính xác.

### 4.4. Proxy, firewall và zero trust không thay thế hoàn toàn nhau

Proxy cung cấp khả năng điều khiển truy cập ở mức ứng dụng cho một số loại lưu lượng. Firewall kiểm soát đường kết nối theo các thuộc tính mạng hoặc ứng dụng tùy sản phẩm. ZTNA gắn truy cập tài nguyên với danh tính, thiết bị và policy. DNS security kiểm soát hoặc quan sát quá trình phân giải tên. IDS/NDR phát hiện bất thường.

Mỗi lớp có mục tiêu và giới hạn riêng. Thiết kế phòng thủ nên phối hợp nhiều lớp, đồng thời ghi rõ **luồng nào buộc phải đi qua lớp nào**.

## 5. Phân loại những đường bypass cần kiểm tra

### 5.1. Đường mạng và routing thay thế

Một máy hoặc subnet có thể có nhiều default gateway, nhiều route, nhiều VRF, nhiều network interface, đường site-to-site, peering hoặc kết nối cloud trực tiếp. Route tới một prefix cụ thể có thể được ưu tiên hơn default route.

**Dấu hiệu:** traffic thấy ở NAT gateway khác với dự kiến; số phiên trên proxy không tăng dù ứng dụng tạo kết nối; flow log chỉ ra next hop khác; SOC thiếu log từ vùng vừa được thêm.

**Nguyên tắc kiểm tra:** lập bản đồ effective routes từ **nguồn thật**, gồm đường hồi đáp, NAT và route propagation. Bảng cấu hình trên một thiết bị riêng lẻ chưa đủ để khẳng định datapath.

### 5.2. Cấu hình proxy khác nhau giữa ứng dụng

Trình duyệt có thể dùng proxy do chính sách doanh nghiệp cung cấp, trong khi runtime, service daemon, tác vụ nền hoặc thư viện kết nối sử dụng cấu hình khác.

Những yếu tố cần được quản lý:

- Cơ chế proxy của từng nhóm ứng dụng và thiết bị.
- Danh sách no-proxy/bypass được chấp thuận cho đích nội bộ hoặc một số luồng đặc biệt.
- PAC/WPAD, thứ tự lựa chọn proxy và hành vi khi proxy không sẵn sàng.
- Proxy authentication và quản lý phiên.
- Ứng dụng dùng HTTP CONNECT, SOCKS hoặc giao thức không được proxy hỗ trợ.
- Lưu lượng từ các service account, agent cập nhật hoặc container nằm ngoài chính sách dành cho trình duyệt.

Sự hiện diện của file PAC hoặc cấu hình proxy không tự chứng minh ứng dụng đã sử dụng nó; cần kiểm chứng từ phía client **và** từ log/counters của enforcement.

### 5.3. Khác biệt IPv4 và IPv6

Mạng có thể áp chính sách egress chặt với IPv4 nhưng bỏ sót IPv6 khi client có dual stack. Một hostname có thể phân giải cả A và AAAA; đường được chọn phụ thuộc hệ điều hành, ứng dụng và tính sẵn sàng của mạng.

Không nên kiểm tra chỉ IPv4 rồi kết luận mọi kết nối được bảo vệ. Phải kiểm tra routing và policy tương ứng cho cả IPv4 và IPv6; nếu tổ chức chưa hỗ trợ IPv6, cần quyết định chính thức cách xử lý và xác minh kết quả, thay vì bỏ mặc một đường hoạt động không được giám sát.

### 5.4. Giao thức và cổng nằm ngoài phạm vi proxy

Một HTTP forward proxy không nhất thiết quan sát tất cả lưu lượng UDP hoặc giao thức không phải HTTP. QUIC/HTTP/3 thường sử dụng UDP 443; DNS có thể dùng UDP/TCP 53 hoặc các cơ chế phân giải được mã hóa. Một kiểm soát chỉ theo dõi TCP 80/443 có thể không thấy tất cả kiểu kết nối ứng dụng hiện đại.

**Không đồng nhất:** một dịch vụ dùng cổng 443 chưa chắc là HTTPS truyền thống; một flow có TLS chưa chắc là web browsing; một tên miền đã được truy vấn chưa chứng minh nội dung dữ liệu sau đó đi qua proxy.

Chính sách cần định nghĩa rõ các giao thức được phép và phương thức giám sát tương ứng, không dùng suy luận “cổng 443 đồng nghĩa qua web gateway”.

### 5.5. VPN và truy cập từ xa

Với full tunnel, thiết kế kỳ vọng luồng nhất định được đưa về hệ thống doanh nghiệp; với split tunnel, một phần lưu lượng có chủ đích đi ngoài tunnel. Cả hai mô hình đều có thể hợp lệ khi được đánh giá rủi ro và giám sát phù hợp.

Điểm cần xác minh:

- Danh sách prefix được tunnel hóa và route thực tế trên endpoint.
- Chính sách DNS của VPN và các domain phân giải qua resolver nào.
- Ứng dụng SaaS được cho phép đi Internet trực tiếp có cần lớp bảo vệ endpoint/cloud riêng không.
- Hành vi khi VPN ngắt, client roaming hoặc đổi interface.
- Kết nối của người dùng ngoài văn phòng có chịu policy tương đương khi không dùng VPN không.

Một trạng thái “VPN connected” chỉ chứng minh phiên VPN được thiết lập; không chứng minh **mọi lưu lượng thuộc diện bắt buộc** đang đi trong tunnel.

### 5.6. Cloud, container và service mesh

Trong cloud, một workload có thể dùng NAT gateway, internet gateway, peering, transit hub, private endpoint hoặc đường kết nối liên vùng. Các đường này có thể áp lớp enforcement khác nhau.

Trong Kubernetes, network policy phụ thuộc CNI và phạm vi pod/namespace; service mesh có thể chỉ áp chính sách với workload tham gia mesh. Lưu lượng từ node, host networking, daemon, job hoặc workload ngoài mesh cần được đánh giá riêng, không tự động coi là được bảo vệ bởi policy dành cho service mesh.

### 5.7. Ngoại lệ, bảo trì và failover

Một ngoại lệ khẩn cấp có thể cấp route hoặc rule tạm để khôi phục dịch vụ. Một đường dự phòng có thể chỉ được kích hoạt khi gateway chính lỗi. Nếu chỉ kiểm thử lúc hệ thống vận hành bình thường, nhóm an ninh có thể không nhìn thấy đường bypass tồn tại trong trạng thái suy giảm.

Bảo vệ cần áp dụng ở cả **normal mode**, **failover mode** và **degraded mode** theo thiết kế đã duyệt. Nếu luồng nào được phép bỏ qua inspection để đảm bảo hoạt động khẩn cấp, phải có ràng buộc về danh tính, đích, thời hạn, giám sát và chấp thuận rủi ro.

## 6. Lập mô hình đường đi bắt buộc và các đường đi khả dĩ

Một cách thực tế là xây bảng **source → destination → required controls → actual path**. Đơn vị đánh giá nên là một nhóm luồng có policy và đường đi giống nhau; tránh chỉ liệt kê tên thiết bị.

Ví dụ với ứng dụng doanh nghiệp:

| Luồng | Đường bắt buộc theo thiết kế | Điểm cần xác minh |
| --- | --- | --- |
| Laptop công ty → Internet web | Secure web gateway + egress firewall | Proxy thực sự được sử dụng; firewall không cho Internet trực tiếp ngoài ngoại lệ |
| Server ứng dụng → API đối tác | Egress firewall vùng + kiểm soát đích | Route vùng, NAT, allowlist đích, log policy |
| Workload VPC-A → VPC-B | Segmentation control trên hub hoặc lớp tương đương | Peering/transit routes, security group, east–west logs |
| Pod → Internet | Egress policy + gateway đã chuẩn hóa | Namespace, CNI, node egress, mesh enrollment |
| User qua VPN → nội bộ | ZTNA/VPN policy + segmentation firewall | Identity, tunnel routes, DNS, quyền theo ứng dụng |
| Guest Wi-Fi → Internet | Guest isolation + egress filter | Không có đường tới zone nội bộ; guest firewall/logging đúng |
| Máy quản trị → thiết bị mạng | Bastion/ZTNA + ACL + audit | Không có đường quản trị trực tiếp ngoài break-glass |

Bảng này trả lời **control nào phải hiện diện**. Muốn chứng minh hiện trạng cần thêm bằng chứng về đường đi.

### 6.1. Sơ đồ luồng qua và ngoài proxy

~~~mermaid
flowchart TD
    A["Managed endpoint"] --> B{"Đường egress thực tế"}
    B -->|"Luồng web thuộc diện quản lý"| P["Secure web gateway\nAuth / policy / logging"]
    P --> F["Egress firewall"]
    F --> E["Dịch vụ Internet"]
    B -. "Nhánh phải được kiểm chứng" .-> D["Route/interface/transport khác"]
    D -.-> E
    P --> L["SOC / SIEM"]
    F --> L
    D -. "Nếu không có sensor phù hợp,\nSOC thiếu bằng chứng" .-> L
~~~

**Điểm học:** nếu test chỉ quan sát proxy, ta có thể chứng minh proxy xử lý được *những request đi qua nó*, nhưng không chứng minh các nhánh khác bị chặn.

### 6.2. Mô hình hóa coverage theo tập hợp

Gọi **S** là tập những flow nằm trong phạm vi bắt buộc kiểm soát; **P** là tập flow đi qua proxy theo yêu cầu; **F** là tập flow chịu firewall policy tương ứng. Nếu chính sách yêu cầu cả hai lớp, coverage đúng phải dựa trên **S ∩ P ∩ F**, không dựa trên tổng log của riêng P hoặc F.

Để đo tỷ lệ:

\[
\text{Coverage} = \frac{\text{Số flow trong S có bằng chứng đi qua đủ control bắt buộc}}{\text{Tổng flow thuộc S đã được xác định}}
\]

Cần định nghĩa “flow” rõ ràng: kết nối, nguồn–đích–giao thức theo cửa sổ, workload hoặc kịch bản thử nghiệm. Chỉ số không đáng tin khi mẫu số chỉ gồm những flow đã xuất hiện trong proxy log, bởi chính cách chọn đó loại mất bypass.

## 7. Phân biệt kiểm tra cấu hình với kiểm tra hiệu lực

| Loại kiểm tra | Ví dụ | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- | --- |
| Kiểm tra cấu hình | Proxy host, PAC, firewall rule, route table | Tồn tại cấu hình mong muốn | Mọi ứng dụng và mọi đường đi tuân thủ |
| Kiểm tra deployment | Phiên bản rule trên firewall/agent | Policy đã được áp lên instance cụ thể | Lưu lượng thực tế không có route vòng |
| Kiểm tra telemetry | Proxy log có request, firewall có allow/deny | Một số request đi qua điểm ghi log | Request vắng log không hề xảy ra |
| Kiểm tra đường đi | Effective route, NAT, flow logs, log tại sensor | Phần đường quan sát được của flow đã thử | Mọi đường khác cũng giống flow đã thử |
| Kiểm tra negative case | Kết nối không được phép bị từ chối ở đúng enforcement point | Một nhánh bị chặn theo kỳ vọng | Những nhánh chưa thử cũng bị chặn |
| Kiểm tra failover | Chuyển sang tuyến dự phòng trong lab | Hành vi lúc chuyển chế độ | Khả năng bảo vệ ở tất cả trạng thái chưa kiểm thử |

**Kết luận kỹ thuật phải tương ứng bằng chứng.** Ví dụ “đã xác minh workstation A, ứng dụng X, IPv4 TCP 443 khi dùng proxy P” là nhận định có giới hạn rõ. Nó không đủ để tuyên bố workstation A không có đường bypass qua mọi giao thức hoặc interface.

## 8. Chuẩn bị một cuộc kiểm thử bypass hợp lệ

### 8.1. Xác định phạm vi

Trước khi chạy, lập bảng:

- **Nhóm nguồn:** máy trạm, VPN client, máy chủ ứng dụng, workload cloud, pod, thiết bị Wi-Fi/IoT.
- **Nhóm đích:** dịch vụ nội bộ, dịch vụ cloud, Internet và điểm canary.
- **Protocol:** HTTP/HTTPS, TCP khác HTTP, UDP/QUIC, DNS và IPv4/IPv6 khi nằm trong phạm vi.
- **Điều kiện:** văn phòng, remote VPN, on-site Wi-Fi, nhiều vùng cloud, bình thường và failover được phép.
- **Expected path:** thiết bị hoặc dịch vụ kiểm soát bắt buộc ở từng loại flow.
- **Owner:** người phụ trách nguồn, network platform, proxy, firewall, SOC và người duyệt test.
- **Giới hạn:** thời gian, tải tối đa, dữ liệu kiểm thử, điều kiện dừng, cách khôi phục và thời gian giữ bằng chứng.

Đặt **ground truth** độc lập: khi nào và từ đâu một kết nối được thử, tới đích nào, kết quả phía client và phía server canary, giá trị flow ID, người chạy, phiên bản policy.

### 8.2. Kiểm thử an toàn trước

Nên ưu tiên:

1. **Tài liệu kiến trúc và inventory:** đọc sơ đồ, cấu hình routing/peering, proxy deployment, các chính sách áp dụng.
2. **Truy vấn read-only:** effective routes, cấu hình proxy ứng dụng, quyết định policy và log.
3. **Phép thử đối chứng có giới hạn:** dùng endpoint canary do tổ chức quản lý, không chứa dữ liệu nhạy cảm.
4. **Thử chính sách cấm:** từ vùng lab đã được ủy quyền, kiểm tra một flow được thiết kế phải bị chặn; xác minh điểm chặn.
5. **Thử failover có kiểm soát:** chỉ khi có approval và điều kiện rollback rõ; tránh gây gián đoạn production.

Không cần thực hiện thử nghiệm gây tải lớn hoặc kỹ thuật né tránh sâu để chứng minh các lỗi cấu hình phổ biến. Với thiết bị production nhạy cảm, log, route simulation của nhà cung cấp và policy analysis có thể cung cấp phần lớn bằng chứng trước khi chạy bất kỳ lưu lượng mới nào.

### 8.3. Positive control và negative control

- **Positive control:** flow hợp lệ đi qua proxy/firewall và được cho phép. Mục tiêu: chứng minh đường hợp lệ hoạt động và được ghi log.
- **Negative control:** flow không được phép, phải bị từ chối bởi lớp thực thi đã xác định. Mục tiêu: chứng minh không có nhánh thay thế giúp nó ra đích trong phạm vi thử.
- **Control thất bại:** nếu canary đích không sẵn sàng hoặc DNS sai, phép thử không hợp lệ. Không coi timeout đó là firewall chặn thành công.

Phải ghi rõ điều kiện quan sát và điểm xác nhận kết nối: **client thấy timeout không đủ**, nên cần log deny hoặc bằng chứng tại enforcement point và trạng thái sức khỏe của canary.

## 9. Ma trận kiểm thử theo đường đi

Bảng ví dụ cho môi trường kiểm thử giả định. “Kỳ vọng” phải phù hợp baseline của tổ chức; không phải mọi doanh nghiệp đều dùng chính sách giống nhau.

| ID | Nguồn / điều kiện | Luồng thử trong lab | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- | --- | --- |
| BP-01 | Laptop được quản lý, LAN | HTTP(S) đến canary web qua cấu hình chuẩn | Đi qua proxy, được kiểm tra và ghi log | Proxy request ID + egress FW log |
| BP-02 | Cùng laptop, direct transport được mô phỏng | Kết nối thử không sử dụng proxy ứng dụng | Bị network egress policy từ chối nếu luồng thuộc diện bắt buộc | Egress deny event; canary không nhận |
| BP-03 | Laptop dual-stack | Kết nối thử qua IPv4 và IPv6 nếu được hỗ trợ | Cùng mức kiểm soát theo baseline | Route v4/v6, proxy/firewall logs |
| BP-04 | Laptop trong VPN | Luồng tới mạng nội bộ và Internet theo phân loại | Mỗi nhóm đi đúng tunnel/direct route đã duyệt | VPN routes, flow log, ZTNA decision |
| BP-05 | Máy chủ tại VPC thử nghiệm | Đích Internet được phép và không được phép | Qua egress gateway vùng, không dùng public route ngoài kiểm soát | VPC flow logs + gateway log |
| BP-06 | Pod thường và pod thuộc diện thử riêng | Egress tới canary | Áp đúng CNI/egress/mesh policy từng trường hợp | Namespace, NetworkPolicy, CNI logs |
| BP-07 | Client có ứng dụng khác trình duyệt | Luồng HTTP/TCP theo yêu cầu ứng dụng | Có cùng enforcement bắt buộc hoặc ngoại lệ hợp lệ | Process identity, network/endpoint telemetry |
| BP-08 | Mạng lab kích hoạt failover | Luồng thử lúc gateway/proxy chuyển chế độ | Không mất chính sách bắt buộc ngoài trường hợp đã duyệt | HA event, route, logs, canary |
| BP-09 | Guest Wi-Fi | Kết nối tới zone nội bộ không được phép | Bị chặn tại guest isolation hoặc firewall | AP/NAC/ACL log, canary health |
| BP-10 | Workload dùng private endpoint | Kết nối tới dịch vụ cloud qua endpoint | Đi đúng đường private đã thiết kế, policy/log đủ | Route/endpoint config, flow logs |

Một test có thể chứng minh một nhánh bị chặn, nhưng **không chứng minh mọi nhánh khả dĩ bị chặn**. Nên kết hợp kiểm thử đại diện với đánh giá toàn bộ route/policy và kiểm soát drift liên tục.

## 10. Thu thập bằng chứng từ client, gateway và đích

### 10.1. Một ví dụ log đối chứng

Một lần chạy giả định gồm các mốc:

| Mốc | Nguồn chứng cứ | Quan sát |
| --- | --- | --- |
| T0 | Bộ kiểm thử lab | Khởi tạo flow BP-02 đến canary |
| T1 | Endpoint telemetry | Process/test ID và destination IP |
| T2 | Router / effective path | Chọn next-hop trên đường egress được quản lý |
| T3 | Firewall | Rule block direct access, action deny, policy ID |
| T4 | Canary | Không có session/request tương ứng |
| T5 | SIEM | Đã ingest sự kiện deny với source identity |

Đây là kết quả tốt nếu yêu cầu là **chặn direct flow**. Ngược lại, nếu canary nhận request nhưng proxy không có log, cần tiếp tục kiểm tra xem luồng có bị đưa qua một loại kiểm soát tương đương hay thực sự bypass. Không đủ chứng cứ để kết luận chỉ dựa trên sự vắng mặt một event.

### 10.2. Tương quan log có NAT và proxy

Một flow từ client có thể bị NAT qua nhiều lớp. Proxy còn có thể thiết lập **kết nối upstream riêng**, khiến source IP ở phía đích là IP của proxy chứ không phải IP client. Do đó cần liên kết theo:

- Timestamp UTC có độ lệch đồng hồ được biết hoặc đo.
- Source identity, original source IP/port và NAT translated IP/port khi có.
- Destination IP/port, FQDN, request ID, proxy session ID.
- Firewall action, rule ID, zone, interface và device ID.
- VPC/flow log hoặc NDR event ID, định danh workload/node/namespace.
- TLS SNI hoặc HTTP Host khi có thể sử dụng hợp pháp và phù hợp; không dựa độc nhất vào trường này vì ECH và các biến thể mã hóa có thể làm giảm thông tin quan sát.

Với IPv6, không nên tìm NAT IPv4 tương ứng một cách máy móc. Với proxy chain, phải ghép nhiều segment khác nhau của cùng request, không coi một TCP flow đơn lẻ là toàn bộ giao dịch.

### 10.3. Sai lầm “không thấy trong log = không có traffic”

Không thấy trong proxy log có thể do:

- Luồng không dùng proxy.
- Proxy không hỗ trợ giao thức đó.
- Log bị sampling, drop, parser lỗi hoặc chậm ingest.
- Chính sách logging không áp cho nhóm kết nối đang thử.
- Clock skew khiến tra sai khoảng thời gian.
- Request đi qua proxy khác hoặc gateway tại vùng khác.
- Request chưa thực sự được gửi vì DNS/ứng dụng lỗi từ trước.

Phải đối chiếu ít nhất một nguồn độc lập trước khi kết luận. Nếu chưa biết đường đi, trạng thái hợp lý là **INSUFFICIENT_EVIDENCE**, không phải PASS.

## 11. Kiểm tra chỉ đọc trong phòng lab

Những ví dụ dưới đây minh họa cách kiểm tra *đường định tuyến và trạng thái kết nối* trên thiết bị **được ủy quyền**. Kết quả phụ thuộc hệ điều hành, cấu hình quản trị và môi trường ứng dụng; không được dùng để thử đi vòng hệ thống đang bảo vệ mạng thật khi chưa có phê duyệt.

### 11.1. Linux

~~~bash
# Các interface và địa chỉ trên máy lab
ip -br address

# Bảng định tuyến IPv4/IPv6
ip -4 route show
ip -6 route show

# Các rule định tuyến dựa trên policy
ip rule show

# Đường tới địa chỉ tài liệu IPv4 và IPv6
ip -4 route get 198.51.100.20
ip -6 route get 2001:db8::20

# Thử phản hồi HTTPS từ canary được quản lý
curl --head --max-time 10 https://canary.example.test
~~~

Các lệnh route cho thấy quyết định của network stack tại một thời điểm, chưa đủ chứng minh toàn bộ đường đi sau NAT, firewall hoặc proxy. Lệnh HTTP sử dụng hành vi proxy theo cấu hình của chính công cụ; ứng dụng khác có thể không giống. Không lưu full debug log chứa header xác thực.

### 11.2. Windows PowerShell

~~~powershell
# Địa chỉ, interface, gateway và route
Get-NetIPConfiguration
Get-NetRoute -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv6

# Cấu hình proxy của WinHTTP (không đại diện cho mọi ứng dụng)
netsh winhttp show proxy

# Kiểm tra kết nối TCP tới canary từ thiết bị được phép
Test-NetConnection canary.example.test -Port 443 -InformationLevel Detailed
~~~

Cấu hình **WinHTTP** có thể khác proxy của trình duyệt, ứng dụng dùng WinINet hoặc các runtime bên thứ ba. Một phép kiểm tra TCP thành công không chứng minh request HTTP đã đi qua proxy hoặc TLS được kiểm chứng đúng.

### 11.3. Kiểm tra trực tiếp và qua proxy trong lab

Trong một **lab cô lập** với proxy và canary thuộc quyền kiểm soát của nhóm thử nghiệm, có thể so sánh hai chế độ client. Ví dụ có chủ đích và **không dùng trên endpoint doanh nghiệp khi chưa được phê duyệt**:

~~~bash
# Nhánh dự kiến: đi qua proxy lab
curl --head --max-time 10 \
  --proxy http://proxy-lab.example.test:3128 \
  https://canary.example.test

# Nhánh thử âm tính: yêu cầu client không dùng proxy ứng dụng.
# Bản thân lệnh KHÔNG chứng minh direct path đã được phép.
curl --head --max-time 10 \
  --noproxy '*' \
  https://canary.example.test
~~~

Đọc kết quả theo **policy lab**:

- Request qua proxy thành công và xuất hiện trong log proxy: bằng chứng proxy đang xử lý nhánh có chủ đích.
- Request direct bị deny tại egress firewall, canary không nhận phiên, và có event ID: bằng chứng nhánh trực tiếp đã bị chặn theo kịch bản.
- Request direct thành công dù policy bắt buộc qua proxy: **phát hiện cần điều tra**, đối chiếu network path, NAT và telemetry.
- Cả hai đều thất bại nhưng canary cũng đang down: phép thử không hợp lệ; không quy chụp proxy/firewall.

Dấu sao được bao bởi dấu nháy đơn trong ví dụ để shell truyền nguyên giá trị. Với Windows hay ứng dụng khác, cú pháp có thể thay đổi; không suy từ một công cụ rằng mọi client sẽ hành xử giống nhau.

### 11.4. Công cụ cloud và Kubernetes

Với cloud, ưu tiên mô hình đường đi của nhà cung cấp, effective route, network ACL/security group, VPC/VNet flow logs, NAT gateway metrics và endpoint connections. Với Kubernetes, so sánh Service/Namespace, NetworkPolicy và CNI/mesh enforcement bằng các lệnh đọc:

~~~bash
kubectl get networkpolicies -n app-lab
kubectl get pods -n app-lab -o wide
kubectl get services -n app-lab
kubectl get endpointslices -n app-lab
~~~

Lệnh lấy danh sách **không chứng minh policy đang thực thi**. Cần kết hợp trạng thái CNI, network namespace, policy engine, actual flow logs và traffic tests được phép. Nếu thiếu quyền đọc hoặc log, ghi rõ giới hạn thay vì tự ý mở rộng quyền.

## 12. Trường hợp đặc biệt: proxy fallback và mất kiểm soát trong trạng thái lỗi

Một thiết kế đôi khi dùng nhiều proxy/gateway để tăng khả dụng. Khi proxy chính mất kết nối, client có thể chuyển sang proxy phụ hoặc chuyển chế độ khác. Không nên mặc định mọi fallback đều là lỗ hổng; đánh giá phải dựa vào kiến trúc đã chấp thuận.

### 12.1. Điều kiện cần được định nghĩa

| Câu hỏi | Quyết định cần có |
| --- | --- |
| Proxy chính không phản hồi | Client thử proxy phụ, hiển thị lỗi hay sử dụng đường khác? |
| Proxy phụ không sẵn sàng | Thực thi policy bằng control tương đương hay từ chối flow? |
| Mất kết nối đến IdP | Có token đã xác thực và cache được dùng trong phạm vi nào? |
| Firewall HA failover | Rule, state, route và logging có được đồng bộ không? |
| VPN mất kết nối | Luồng công việc nào được phép đi ngoài tunnel? |
| DNS resolver lỗi | Có resolver dự phòng đúng chính sách, hay chuyển ra DNS công cộng? |
| Egress gateway theo vùng mất khả dụng | Chuyển qua vùng khác có giữ inspection và data residency không? |

**Nguyên tắc thiết kế:** hành vi fail-open hoặc fail-closed phải được quyết định bằng threat model, yêu cầu kinh doanh và biện pháp kiểm soát bù trừ. Không phải hệ thống nào cũng chịu được fail-closed tuyệt đối, nhưng cũng không được tự thêm direct Internet access để “bảo đảm uptime”.

### 12.2. Mô phỏng lỗi an toàn

Trong lab, tạo lỗi có kiểm soát đối với **dịch vụ giả lập** hoặc dùng khả năng diễn tập của nền tảng; ghi lại thời điểm failover, tuyến hiệu lực, tình trạng log, kết quả policy. Trong production, ưu tiên kiểm chứng trên môi trường staging hoặc theo quy trình change có rollback và cửa sổ bảo trì được phê duyệt.

Khi phục hồi proxy chính, phải xác minh rule/route tạm được thu hồi và không để lại ngoại lệ tồn tại vô hạn.

## 13. Trường hợp đặc biệt: DNS và các đường phân giải ngoài kiểm soát

DNS security có thể là lớp phát hiện/chặn trước khi ứng dụng kết nối. Nếu thiết bị được phép gửi truy vấn tới các resolver không thuộc quản lý, một phần policy/domain logging có thể không còn áp dụng.

Tuy nhiên, “đã chặn UDP 53 ra ngoài” chưa chắc đồng nghĩa mọi hoạt động phân giải đều qua resolver doanh nghiệp. Các ứng dụng hiện đại có thể sử dụng dịch vụ DNS được mã hóa hoặc cơ chế phân giải riêng. Cần hiểu chính sách **theo ứng dụng và mạng**, thay vì kết luận dựa trên một port.

Một thiết kế phù hợp thường phối hợp:

1. Resolver doanh nghiệp có độ sẵn sàng cao và chính sách đúng nhu cầu.
2. Quản lý endpoint/browser để sử dụng resolver được phê duyệt khi chính sách yêu cầu.
3. Enforcement mạng cho các loại egress không được phép, có xét IPv4/IPv6.
4. DNS logging, proxy/gateway telemetry và cảnh báo mất nguồn dữ liệu.
5. Quy trình ngoại lệ rõ cho workload có yêu cầu đặc biệt.
6. Thử nghiệm có kiểm soát với cả tên miền hợp lệ, tên miền bị policy chặn và tình huống resolver lỗi.

**Giới hạn:** một truy vấn DNS bị từ chối không chứng minh mọi cách truy cập tới dịch vụ đích cũng bị từ chối nếu kết nối có thể dùng địa chỉ đã biết từ trước. Ngược lại, một ứng dụng không có DNS query ở thời điểm thử có thể dùng cache hợp lệ. Phải đo cả bước phân giải và kết nối thực tế khi mục tiêu là egress enforcement.

## 14. Trường hợp đặc biệt: cloud egress và east–west traffic

### 14.1. Cloud workload có nhiều lối ra

Trong một kiến trúc hub-and-spoke, các VPC hoặc VNet có thể được kỳ vọng đi qua transit hub và firewall. Nhưng peering trực tiếp, internet gateway, private endpoints, route table ở một subnet mới hay attachment khác có thể thay đổi đường đi.

~~~mermaid
flowchart TB
    A["Application VPC / VNet"] --> H["Transit hub"]
    H --> FW["Inspection firewall"]
    FW --> NET["Internet / partner"]
    A -. "Nhánh cần đối chiếu với policy" .-> NAT["NAT / internet gateway riêng"]
    NAT -.-> NET
    A -. "East-west path cần kiểm chứng" .-> B["Peer VPC / private endpoint"]
    FW --> LOG["Flow + firewall logs"]
    NAT -.-> LOG
    B -.-> LOG
~~~

Biện pháp phòng ngừa gồm guardrail cho route/security group, inventory tài khoản và subnet, policy-as-code, CI checks, kiểm tra drift, flow logs có độ phủ và review khi tạo VPC/endpoint mới.

### 14.2. Vấn đề với east–west traffic

Biên Internet không thấy hết kết nối trong mạng nội bộ. Nếu thiết kế yêu cầu cô lập giữa APP và DATA zone, việc hai workload cùng nằm trong cloud không chứng minh firewall nội bộ đã bảo vệ chúng.

Kiểm tra:

- Security group/NSG và network ACL thực thi tại đâu?
- Traffic cùng subnet có cần đi qua một điểm inspection hay được bảo vệ bằng policy tại workload?
- Route giữa các VPC/VNet và vùng có tạo đường không mong muốn?
- Workload có dùng hostNetwork, CNI overlay hoặc mesh bypass không?
- Log đủ định danh workload sau thay đổi IP động hoặc NAT không?

Một đường east–west không đi qua firewall tập trung **có thể hợp lệ** nếu có control tương đương được phê duyệt và chứng cứ hiệu lực. Điều phải tránh là tình trạng sơ đồ ghi “đã inspection” nhưng lưu lượng thực tế đi ngoài mà không ai chịu trách nhiệm.

## 15. Trường hợp đặc biệt: IPv6, QUIC và ứng dụng mới

### 15.1. IPv6 cần được đánh giá ngang với IPv4

Đối với client dual-stack, cần đo:

- IPv4 và IPv6 có route, firewall và DNS policy tương đương không?
- Proxy/security agent có hỗ trợ đích IPv6 và phân biệt đúng identity không?
- Flow logs có lưu IPv6 source/destination hay bị parser loại bỏ?
- Có luồng IPv6 trực tiếp nào nằm ngoài egress gateway dành cho IPv4 không?
- Nếu IPv6 chưa được cho phép trong kiến trúc, chính sách cô lập được thực thi và giám sát ở đâu?

Chỉ khóa một kiểu địa chỉ trong allowlist hoặc denylist không tự bảo vệ kiểu còn lại.

### 15.2. QUIC/HTTP/3 và UDP

QUIC có thể sử dụng UDP để vận chuyển HTTP/3 và có hành vi kết nối khác HTTP/1.1 hoặc HTTP/2 trên TCP. Khi proxy chỉ kiểm soát những request HTTP đi qua nó, lưu lượng UDP phải được đánh giá bằng chính sách mạng và khả năng hỗ trợ của gateway.

Không nên áp dụng thay đổi “chặn UDP 443 toàn tổ chức” chỉ từ giả định về bypass. Cần hiểu ứng dụng, yêu cầu hiệu năng, hỗ trợ HTTP/3 và phương án kiểm tra thay thế. Một số client có thể fallback sang TCP; một số có thể mất chức năng. Kiểm thử hiệu lực và tác động phải đi đôi.

### 15.3. Ứng dụng nhúng, agent và IoT

Thiết bị IoT, máy in, appliance, tác vụ nền, container hoặc runtime riêng có thể không hỗ trợ proxy xác thực như máy người dùng. Nếu chúng cần Internet, kiến trúc nên cấp **egress path riêng có giới hạn**, kiểm soát đích/giao thức, segment, identity thiết bị và logging.

Không ép cùng một cơ chế proxy cho tất cả thiết bị nếu thiết kế không tương thích; thay vào đó áp dụng mục tiêu bảo mật tương đương và đưa ngoại lệ vào inventory được kiểm tra.

## 16. Cách đánh giá một phát hiện bypass

Một kết quả test phải có phân loại nhất quán:

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| **PASS_CONTROLLED** | Flow hợp lệ đi đúng đường hoặc flow cấm bị chặn tại enforcement point đúng như thiết kế | Lưu bằng chứng và baseline |
| **APPROVED_ALTERNATIVE** | Dùng đường thay thế đã được phê duyệt, có control và telemetry tương đương theo đánh giá | Kiểm tra thời hạn, owner và kiểm soát bù trừ |
| **BYPASS_CONFIRMED** | Flow thuộc diện bắt buộc kiểm soát nhưng đi qua đường ngoài dự kiến và thành công hoặc thiếu enforcement yêu cầu | Mở finding, đánh giá tác động, khắc phục |
| **TELEMETRY_GAP** | Có dấu hiệu flow tồn tại nhưng không đủ log để chứng minh enforcement | Kiểm tra pipeline/sensor, chạy lại phép thử |
| **INCONCLUSIVE** | Route, timestamp hoặc bằng chứng không đủ phân loại | Bổ sung quan sát, không công bố PASS |
| **INVALID_TEST** | Canary down, traffic không gửi được, dữ liệu sai hoặc test không đúng phạm vi | Sửa bài test và lặp lại |
| **NOT_TESTED** | Đường đi chưa được kiểm chứng | Ghi rõ tồn đọng; không tính thành đạt |

**Lưu ý:** một kết quả “direct path thành công” không nhất thiết chứng minh vi phạm nếu đường đó đã có một lớp kiểm soát khác được phê duyệt. Ngược lại, “proxy có log” không xóa được phát hiện một đường direct khác cũng thành công.

### 16.1. Ưu tiên rủi ro

Khi có nhiều phát hiện, ưu tiên theo:

- Mức nhạy cảm của source và destination.
- Loại dữ liệu và mức độ truy cập có thể phát sinh.
- Mức độ thiếu control: mất chặn, mất xác thực, mất inspection hay mất logging.
- Số workload/user và vùng mạng có thể bị ảnh hưởng.
- Mức độ dễ xảy ra trong cấu hình vận hành thông thường hoặc sau failover.
- Có lớp kiểm soát độc lập còn hiệu lực hay không.
- Tính cấp bách của ngoại lệ tạm và khả năng kiểm soát bằng thay đổi hẹp.

Không nên dùng một thang điểm tự đặt như “mọi bypass đều Critical”. Một direct route tới dịch vụ cập nhật được phép, có egress ACL và logging, khác với direct route không được quản lý từ mạng chứa dữ liệu nhạy cảm. Kết luận cần gắn với threat model và bằng chứng.

## 17. Khắc phục theo nguyên nhân, tránh chỉ vá một ứng dụng

### 17.1. Từ lỗi cấu hình client đến enforcement ở tầng mạng

Nếu một ứng dụng không dùng proxy đúng cấu hình, cần sửa application config, profile quản lý thiết bị hoặc thư viện phù hợp. Tuy nhiên với luồng **bắt buộc đi proxy**, không nên đặt toàn bộ độ an toàn vào việc ứng dụng tự nguyện tuân thủ cấu hình.

Các biện pháp phòng vệ:

- Egress firewall mặc định chặn direct Internet theo zone/asset, chỉ cho đường egress đã duyệt.
- Rule dựa trên đích, dịch vụ và định danh, tránh mở rộng allowlist quá mức.
- Client policy/MDM và cấu hình proxy được version hóa, giám sát drift.
- Quy định các ngoại lệ hợp lệ và cơ chế thu hồi tự động.
- Endpoint telemetry để phát hiện ứng dụng tạo connection ngoài phương án đã duyệt.

### 17.2. Từ lỗi routing đến guardrail kiến trúc

Nếu một subnet có route ngoài inspection:

1. Đối chiếu expected topology, route hiện tại, tất cả đường thay thế và phụ thuộc kinh doanh.
2. Xác định lớp policy nào phải áp trên mỗi nhánh.
3. Đề xuất sửa routing/attachment/egress gateway theo hạ tầng-as-code, có review.
4. Kiểm tra thay đổi bằng flow test từ workload thật, cả chiều đi/về và IPv4/IPv6 nếu liên quan.
5. Bật kiểm soát phát hiện drift cho những subnet/VPC mới hoặc thay đổi peering.
6. Xác nhận log và alert đến SOC, cập nhật service catalog và owner.

**Không xóa route production ngay khi phát hiện vấn đề** mà chưa đánh giá blast radius; có thể ảnh hưởng dịch vụ có lịch bảo trì, đường DR hoặc private endpoint đang được sử dụng. Sử dụng change/incident workflow với rollback.

### 17.3. Từ blind spot đến bằng chứng liên tục

Nếu proxy hoặc firewall thiếu log:

- Kiểm tra trạng thái sensor/collector, parser, sampling, quota, queue, retention và clock sync.
- Chuẩn hóa trường source, dest, protocol, action, policy, identity, workload và NAT.
- Dùng heartbeat/synthetic logs để phát hiện nguồn log ngừng gửi.
- Theo dõi tỉ lệ asset/subnet được coverage, không chỉ tổng số event.
- Đối chiếu event flow ở nhiều điểm khi có nghi ngờ đường bypass.
- Phân biệt lỗi ingestion với thực tế không có lưu lượng.

Thiếu dữ liệu quan sát là một phát hiện riêng, vì nó làm giảm khả năng xác nhận sự hiệu lực của kiểm soát và điều tra sự cố sau này.

## 18. Kiểm thử hồi quy và giám sát thay đổi

Một lần kiểm thử đạt chưa đủ vì đường đi thay đổi theo vòng đời hệ thống: thêm VPC, subnet, peering, VPN profile, interface, PAC rule, proxy pool, mesh policy, firmware hoặc cloud route.

### 18.1. Khi nào cần chạy lại?

- Sau thay đổi proxy, firewall, route, NAT, VPN, cloud network và DNS security.
- Khi thêm mạng, tài khoản cloud, cluster, zone hoặc kiểu thiết bị mới.
- Khi thay đổi phương thức kết nối ứng dụng, bật IPv6, QUIC hoặc service mesh.
- Sau sự cố gateway/proxy, thay đổi phương án HA/failover hoặc emergency exception.
- Khi monitoring phát hiện nguồn flow log mất, policy drift, đường truyền mới hoặc subnet không có owner.
- Theo chu kỳ đánh giá rủi ro được tổ chức xác định.

### 18.2. Đề xuất chỉ số

**Bypass test coverage** = số tổ hợp đường đi/protocol/nguồn thuộc danh mục đã kiểm thử / tổng số tổ hợp cần kiểm thử. Cần công bố danh mục, mẫu số và khoảng thời gian.

**Control enforcement success rate** = số thử nghiệm hợp lệ cho kết quả policy đúng / tổng số thử nghiệm hợp lệ. Tách flow được phép và flow bị cấm để tránh che khuất lỗ hổng.

**Telemetry completeness** = số thử nghiệm hợp lệ có đủ event tại các lớp bắt buộc / tổng số thử nghiệm yêu cầu telemetry.

**Unapproved bypass count** = số đường bypass ngoài chính sách đã xác nhận và chưa được xử lý; công bố theo mức rủi ro, owner và tuổi tồn đọng.

**Exception hygiene** = số ngoại lệ có owner, phê duyệt, thời hạn, kiểm soát bù trừ và review / tổng số ngoại lệ còn hiệu lực.

Không lấy tổng số log proxy làm mẫu số chung: nơi có bypass có thể không xuất hiện trong proxy log, tạo sai lệch selection bias.

### 18.3. Policy-as-code và kiểm tra đường đi

Một pipeline hạ tầng có thể thực hiện **static checks**: ngăn tạo route trực tiếp hoặc security group rộng trong vùng bắt buộc inspection, kiểm tra CIDR/IPv6, xác minh policy gắn đúng subnet/namespace. Runtime checks xác nhận route và enforcement thực tế, vì policy-as-code không chứng minh hoạt động của datapath hay tính đầy đủ log.

Ví dụ tiêu chí kiểm tra dạng giả mã:

~~~text
FOR EACH managed_network_zone:
    inventory all source workloads and their authorized egress classes
    map effective routes for each required address family
    identify all enforcement points reachable from each egress path
    compare actual policy and telemetry to the approved design

    FOR EACH approved synthetic test:
        record source, destination, protocol, time, expected decision
        collect client result + gateway event + canary observation
        classify PASS, APPROVED_ALTERNATIVE, BYPASS, or INCONCLUSIVE

    IF unexpected route OR missing enforcement OR missing telemetry:
        open finding with owner, impact, evidence and retest condition
~~~

Giả mã là mô hình kiểm toán phòng thủ, không phải script có quyền thay đổi mạng. Các thuật toán reachability hoặc graph analysis có thể hỗ trợ phát hiện đường bị bỏ sót, nhưng cần kiểm chứng với thực trạng routing và policy của sản phẩm cụ thể.

## 19. Case study: proxy hoạt động bình thường nhưng một subnet không được bảo vệ

### 19.1. Bối cảnh

Một công ty có **secure web gateway** dùng chung cho máy trạm và server ứng dụng. Đội SOC thấy log từ văn phòng và cho rằng mọi traffic web outbound đều đi qua proxy. Sau khi mở rộng cloud, một subnet ứng dụng mới được tạo để chạy tác vụ nền.

**Thiết kế mong đợi:** mọi outbound web của subnet ứng dụng phải qua egress gateway vùng, nơi áp policy đích và gửi log tới SIEM.

### 19.2. Dấu hiệu ban đầu

- Proxy vẫn có nhiều request từ các subnet cũ.
- Metrics gateway vùng bình thường.
- Tác vụ ở subnet mới kết nối được tới một dịch vụ kiểm thử, nhưng không có proxy request ID tương ứng.
- Effective route của subnet mới khác baseline: nó dùng một NAT gateway chưa nằm trong sơ đồ kiểm soát được phê duyệt.

Đây là **giả thuyết bypass**, cần xác minh log NAT/flow, policy cloud và kết quả ở canary trước khi kết luận.

### 19.3. Kiểm thử có bằng chứng

Nhóm được ủy quyền dùng dịch vụ canary trong lab, gắn execution ID và tạo hai request có nội dung vô hại:

1. Request từ subnet cũ được ghi ở egress gateway theo thiết kế.
2. Request từ subnet mới được canary nhận, có flow log trên NAT path nhưng không có enforcement event ở gateway bắt buộc.
3. Bảng routing xác nhận subnet mới có đường ra trực tiếp ngoài điểm kiểm soát; việc thiếu log không do parser hay sai giờ.
4. Phân tích policy cho thấy NAT path không có lớp kiểm soát tương đương đã được phê duyệt.

**Kết luận:** xác nhận bypass egress protection cho subnet mới, không kết luận các subnet khác đều có lỗi.

### 19.4. Khắc phục

Network Platform và Cloud Platform xác định route và guardrail cần sửa; Security Architecture xác nhận baseline, App Owner kiểm tra phụ thuộc. Thay đổi được triển khai qua quy trình review có rollback.

Sau sửa:

- Canary request hợp lệ vẫn hoàn tất qua gateway bắt buộc.
- Thử negative control chứng minh direct egress ngoài chính sách bị từ chối.
- Gateway log có source workload và policy ID; SIEM nhận sự kiện.
- Các luồng của ứng dụng qua private endpoint và traffic hợp lệ khác không bị gián đoạn.
- Pipeline IaC bổ sung kiểm tra route cho những subnet mới.

**Bài học:** gateway đang hoạt động và có log không phải bằng chứng toàn bộ subnet thuộc phạm vi đã đi qua nó. Kiểm soát phải gắn với inventory, route và phép thử từ nguồn thực tế.

## 20. Case study: remote endpoint và đường đi khác nhau giữa IPv4/IPv6

### 20.1. Bối cảnh

Tổ chức quy định truy cập web trên thiết bị được quản lý phải chịu secure web gateway policy. Một ứng dụng dùng địa chỉ IPv4 hoạt động đúng và được log; một phiên bản ứng dụng mới hỗ trợ dual-stack.

### 20.2. Tình huống minh họa

Ở môi trường lab, nhóm kiểm thử phát hiện:

- IPv4 HTTPS request đi qua gateway và được log đầy đủ.
- IPv6 từ client tới canary sử dụng route khác.
- Egress policy trên IPv6 không tương xứng với IPv4.
- DNS trả AAAA hợp lệ, và client ưu tiên kết nối IPv6 trong phép thử đó.

**Phân tích:** đây là lỗi parity giữa hai address family. Sửa proxy setting riêng không đủ nếu IPv6 path không đi qua điểm kiểm soát.

### 20.3. Phòng ngừa

Inventory bắt buộc ghi trạng thái IPv4/IPv6, route và policy tương ứng; thiết bị mạng, gateway và SIEM phải hỗ trợ trường IPv6. Nếu organization chủ động không cho IPv6, cần kiểm soát theo chuẩn đã duyệt và xem xét tác động ứng dụng; không thể giả định “không dùng IPv6” mà thiếu bằng chứng.

**Bài học:** chỉ kiểm thử một address family tạo khoảng trống đo lường.

## 21. Runbook khi phát hiện nghi vấn bypass

Mẫu quy trình này hướng đến người trực mạng, cloud platform, SOC và security engineer.

### Bước 1 — Giữ nguyên bằng chứng

Ghi thời điểm, nguồn/đích, giao thức, identity, route, policy version, canary result và event IDs. Bảo toàn log theo chính sách; tránh vô tình làm mất dấu vì thay đổi cấu hình vội.

### Bước 2 — Kiểm tra phạm vi và tính hợp lệ

Flow có thật không? Test có được phép không? Canary có khỏe không? Có proxy chain khác hoặc kiểm soát thay thế được phê duyệt không? Nguồn nào chịu ảnh hưởng?

### Bước 3 — Xác minh nguyên nhân

So sánh đường dự kiến với actual effective routes, firewall/proxy decision, NAT, VPC flow, VPN, IPv4/IPv6 và trạng thái log. Nếu chỉ thiếu log, phân loại telemetry gap trước khi kết luận bypass.

### Bước 4 — Điều phối owner

- Network/Cloud Platform: route, NAT, gateway, attachment, HA.
- Endpoint/Workload Owner: proxy config, application behavior, interface.
- Security Architecture: policy baseline, exception, risk, guardrail.
- SOC: nguồn log, detection coverage, sự kiện đáng ngờ.
- Risk Owner/Incident Commander: phê duyệt ngoại lệ hoặc biện pháp khẩn cấp theo quy trình.

### Bước 5 — Đề xuất thay đổi có rollback

Chọn thay đổi nhỏ nhất đủ khôi phục yêu cầu kiểm soát; phân tích impact của việc chuyển route, chặn direct transport hoặc cập nhật gateway. Ghi change ID, người duyệt, cửa sổ, rollback, positive và negative tests.

### Bước 6 — Kiểm chứng sau thay đổi

- Luồng được phép còn hoạt động.
- Luồng bị cấm không thể kết nối theo nhánh ngoài dự kiến.
- IPv4/IPv6, TCP/UDP và các môi trường liên quan đạt mức policy định nghĩa.
- Log từ enforcement point xuất hiện và SOC tra được.
- Failover/ngoại lệ không tạo đường bypass tồn đọng.
- Ứng dụng không phát sinh timeout hoặc lỗi ngoài mức chấp nhận.

### Bước 7 — Đóng finding và chống tái phát

Cập nhật owner, inventory, route diagram, policy-as-code, checklist onboarding và bài regression. Nếu một nhánh chưa kiểm thử, ghi rõ chưa có bằng chứng; không đóng toàn bộ phạm vi bằng một test đại diện.

## 22. Mẫu bằng chứng cho một phát hiện

~~~yaml
finding_id: NET-BYPASS-010
title: Unapproved egress path from test subnet
environment: lab
test_execution_id: BP-05-RUN-003
source:
  workload: app-lab-worker
  subnet: 192.0.2.0/24
destination:
  hostname: canary.example.test
  ip: 198.51.100.20
  protocol: TCP
  port: 443
expected:
  path: managed-egress-gateway
  enforcement: policy-set-egress-01
  telemetry: proxy-or-firewall-event-required
observed:
  client_result: connected
  canary_result: request-received
  actual_path: alternate-nat-path
  managed_gateway_event: absent-after-ingest-validation
  alternate_flow_log: present
classification: BYPASS_CONFIRMED
severity: organization-assessed
owner: network-platform
security_reviewer: security-architecture
recommended_action:
  - Review route and enforce approved egress path
  - Add configuration guardrail for new subnets
  - Retest allowed and denied traffic
status: OPEN
~~~

Đây là **mẫu tổng hợp**, không phải bản ghi sản xuất. Với hệ thống thật, bằng chứng phải có tài liệu tham chiếu riêng, quyền truy cập phù hợp và tránh đưa dữ liệu nhạy cảm lên kho mở.

## 23. Các sai lầm phổ biến cần tránh khi đánh giá

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Chỉ xem proxy log | Không thấy luồng không đi qua proxy | Dùng nguồn độc lập, effective routes và canary |
| Chỉ xem firewall rules | Rule có thể không nằm trên đường đi | Xác minh enforcement point và đường thực tế |
| Chỉ thử trình duyệt | App/agent có cơ chế proxy riêng | Xem nhóm client/workload thực tế |
| Chỉ thử IPv4 | IPv6 có thể đi đường khác | Đưa dual-stack vào test matrix |
| Chỉ xét TCP 443 | UDP/QUIC và giao thức khác có thể có policy khác | Phân loại protocol và yêu cầu control |
| Coi mọi split tunnel là lỗi | Một số đường direct được phê duyệt | Đối chiếu policy, risk và control bù trừ |
| Coi mọi kết nối direct là tấn công | Có workload được thiết kế sử dụng egress riêng | Phân biệt expected/approved/unapproved |
| Thử proxy chỉ lúc bình thường | Failover có thể thay route hoặc fallback | Thử degraded mode trong phạm vi an toàn |
| Dựa vào timeout để kết luận firewall chặn | Canary hoặc DNS cũng có thể lỗi | Thu bằng chứng deny tại enforcement |
| Mở rộng allow rule để sửa lỗi | Có thể tạo bypass mới và phá segmentation | Least privilege, approval, rollback và negative test |
| Đóng finding khi sửa một subnet | Subnet mới có thể lặp lỗi | Guardrail + inventory + regression |
| Không xác định owner | Không ai xử lý ngoại lệ hoặc drift | Service catalog, RACI và on-call |
| Đếm số test PASS mà không nêu mẫu số | Che đường chưa kiểm thử | Coverage theo tập đường đi đã xác định |

## 24. Bài tập thực hành có kiểm soát

### 24.1. Mục tiêu bài lab

Mô hình hóa hai phân đoạn thử nghiệm: một segment client và một segment canary. Trong lab, proxy/gateway chung là điểm kiểm soát bắt buộc cho lưu lượng web của segment client. Nhóm thực hành phải chứng minh **luồng hợp lệ đi đúng đường** và **luồng trực tiếp ngoài chính sách bị chặn**.

Không cần thiết lập hạ tầng như môi trường sản xuất. Có thể dùng log tổng hợp, sơ đồ mạng giả lập hoặc phép thử canary nội bộ để đánh giá.

### 24.2. Nhiệm vụ

1. Viết policy mong đợi bằng câu rõ ràng: ai được kết nối, đích nào, qua control nào, ứng dụng/protocol nào.
2. Vẽ ít nhất hai đường đi khả dĩ: qua gateway chuẩn và đường còn lại từ cấu hình giả lập.
3. Lập test matrix cho IPv4, IPv6 nếu có, hai nhóm client và một trạng thái lỗi giả lập.
4. Ghi ground truth và thu ba loại bằng chứng: kết quả phía client, event từ enforcement và log phía canary.
5. Chấm PASS, BYPASS_CONFIRMED hoặc INCONCLUSIVE theo tiêu chí đã định nghĩa trước.
6. Chỉ ra biện pháp sửa ở lớp routing/firewall/client policy phù hợp nguyên nhân.
7. Mô tả positive và negative tests cần chạy lại sau sửa.
8. Đề xuất một kiểm tra CI/guardrail ngăn lỗi quay lại khi thêm subnet mới.

### 24.3. Bảng dữ liệu giả định

| Test | Client | Enforcement log | Canary log | Expected | Đánh giá |
| --- | --- | --- | --- | --- | --- |
| T1: qua proxy | Success | Proxy allow, có request ID | Có request | Allow qua proxy | **PASS_CONTROLLED** |
| T2: direct không được phép | Timeout | Firewall deny, policy ID rõ | Không có request | Deny | **PASS_CONTROLLED** |
| T3: direct không được phép | Success | Không thấy log tại gateway chuẩn; alternate flow log và route xác nhận đường ngoài | Có request | Deny | **BYPASS_CONFIRMED** |
| T4: canary down | Timeout | Không có sự kiện đáng tin cậy | Không nhận được do service down | Deny | **INVALID_TEST** |
| T5: proxy log mất | Success | Firewall flow có, proxy log không truy được | Có request | Allow qua proxy | **TELEMETRY_GAP** nếu chưa đủ bằng chứng đường đi |

**Lưu ý:** nếu T5 có bằng chứng từ đường đi/thiết bị khác chứng minh request qua proxy, có thể phân loại enforcement PASS riêng nhưng vẫn ghi telemetry gap. Không gộp hai loại vấn đề vào một câu kết luận.

### 24.4. Tiêu chí nghiệm thu

Người học đạt nếu có sơ đồ và bảng test tương ứng, phân loại đúng các trạng thái, không nhầm thiếu log với bypass chắc chắn, biết kiểm tra route và control tương đương, và đề xuất retest có ít nhất một positive cùng một negative case.

## 25. Câu hỏi ôn tập

**Câu 1.** Một proxy có log đầy đủ cho trình duyệt của 500 máy. Điều này chứng minh cả 500 máy không thể kết nối Internet trực tiếp không?

**Trả lời:** Không. Log chứng minh request đã đi qua proxy, chưa chứng minh các đường đi khác bị chặn. Cần đánh giá route, enforcement ở lớp mạng và kiểm thử negative control từ những nhóm nguồn/ứng dụng đại diện.

**Câu 2.** Máy khách dual-stack đi qua egress firewall đối với IPv4 nhưng IPv6 dùng route khác. Nên đánh giá thế nào?

**Trả lời:** Kiểm tra chính sách IPv6, điểm enforcement, đường hồi đáp và log. Nếu IPv6 bypass control bắt buộc và không có lớp tương đương đã duyệt, đó là thiếu coverage; khắc phục theo kiến trúc và retest cả hai address family.

**Câu 3.** Trong mạng cloud, proxy không có event cho một request, nhưng canary nhận request. Có thể lập tức gọi là BYPASS_CONFIRMED không?

**Trả lời:** Chưa. Cần xác nhận client, NAT/route, gateway khác, sự đầy đủ log, timestamp và policy. Nếu sau đối chiếu xác nhận request thuộc diện bắt buộc đi gateway nhưng đi ngoài, mới kết luận bypass.

**Câu 4.** Split tunnel luôn là cấu hình sai?

**Trả lời:** Không. Có thể là lựa chọn kiến trúc hợp lệ, miễn đường direct được xét rủi ro, bảo vệ tương ứng, logging và giới hạn phạm vi. Vấn đề là kết nối thuộc diện bắt buộc kiểm soát đã đi ngoài khi không có phê duyệt.

**Câu 5.** Firewall log deny một flow thử nghiệm. Đã chứng minh mọi đường tới đích đều bị chặn chưa?

**Trả lời:** Chưa. Chỉ chứng minh flow cụ thể bị chặn tại điểm đó. Cần đánh giá topology, route, các address family, giao thức và alternative paths trong phạm vi đã xác định.

**Câu 6.** Vì sao không nên giảm mức bảo vệ chỉ để sửa lỗi kết nối của ứng dụng?

**Trả lời:** Vì mở rule quá rộng hoặc tắt inspection có thể tạo lỗ hổng khác. Cần tìm nguyên nhân, giới hạn thay đổi, có phê duyệt, đo tác động, xác nhận luồng hợp lệ hoạt động và luồng bị cấm vẫn bị từ chối.

**Câu 7.** Khi proxy lỗi, client có thể sử dụng một gateway dự phòng. Vậy bài test bypass cần thêm điều gì?

**Trả lời:** Kiểm tra cả normal/failover/degraded mode, xác nhận gateway phụ áp control đúng yêu cầu, giữ telemetry và không để lại ngoại lệ sau khi phục hồi.

**Câu 8.** Bước tối thiểu để tuyên bố một VPC mới tuân thủ egress security là gì?

**Trả lời:** Xác minh inventory/scope, effective routes, security policy, đường đi thực sự đến enforcement, log và positive/negative tests trong phạm vi; đồng thời có owner và phương án giám sát drift sau triển khai.

## 26. Checklist ngăn bỏ sót đường bypass

Dùng checklist cho mỗi phân đoạn hoặc nhóm workload trước khi đưa vào production hoặc sau thay đổi lớn:

- [ ] Phân loại rõ traffic cần proxy, firewall, ZTNA, DNS security hoặc control tương đương.
- [ ] Có inventory nguồn/đích, chủ sở hữu, route, NAT và enforcement point.
- [ ] Đã kiểm tra kết nối theo ứng dụng, interface, site, zone và mạng remote liên quan.
- [ ] Đã đánh giá IPv4, IPv6 và các giao thức thuộc phạm vi.
- [ ] Có policy ở lớp mạng cho direct egress ngoài danh sách được duyệt.
- [ ] Route, peering, gateway backup, private endpoints, VPN split tunnel và cloud attachments không tạo đường ngoài dự kiến.
- [ ] Các ứng dụng không sử dụng proxy trình duyệt có phương án kiểm soát tương đương.
- [ ] Cấu hình PAC/no-proxy và exception được quản lý phiên bản, có owner và thời hạn review.
- [ ] Normal mode và các trạng thái failover/degraded đã được xem xét.
- [ ] Positive và negative tests có ground truth cùng tiêu chí phân loại.
- [ ] Có đủ bằng chứng từ client, enforcement, route và canary khi cần.
- [ ] Proxy/firewall/DNS/flow logs đến SOC đầy đủ, xác định được nguồn lưu lượng.
- [ ] Có quy trình phân loại INCONCLUSIVE/TELEMETRY_GAP thay vì tự đánh dấu PASS.
- [ ] Có plan sửa theo change management, rollback và kiểm thử hồi quy.
- [ ] Guardrail/CI hoặc kiểm tra drift bảo vệ những subnet và workload mới.
- [ ] Những đường thay thế đã phê duyệt có người sở hữu, kiểm soát bù trừ và hồ sơ rủi ro.

---

**Thông điệp trọng tâm:** firewall hoặc proxy chỉ bảo vệ được những luồng thật sự thuộc phạm vi kiểm soát của nó. Muốn khẳng định kiến trúc mạng an toàn, phải kiểm tra **đường đi thực tế**, **enforcement**, **đường thay thế**, **bằng chứng telemetry** và **hành vi khi lỗi/failover**. Bài kiểm thử thành công luôn có cả luồng được phép hoạt động và luồng không được phép bị chặn, với phạm vi và điều kiện rõ ràng.
