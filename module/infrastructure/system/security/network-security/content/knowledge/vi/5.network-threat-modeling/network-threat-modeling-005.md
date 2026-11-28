# Spoofing trên mạng: nhận diện giả mạo và mô hình hóa mối đe dọa

**Spoofing (giả mạo)** là hành vi làm cho thông tin nhận dạng trong một gói tin, thông điệp hoặc điểm truy cập trông như thuộc về một thực thể khác. Trong mạng máy tính, kẻ tấn công có thể giả mạo địa chỉ IP, địa chỉ MAC, ánh xạ ARP, câu trả lời DNS, thông tin DHCP, thông điệp Neighbor Discovery của IPv6 hoặc danh tính mạng Wi-Fi. Mục tiêu có thể là chuyển hướng lưu lượng, vượt qua một chính sách tin cậy yếu, che giấu nguồn phát, gây gián đoạn hoặc tạo điều kiện cho **man-in-the-middle (MITM)**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, hiểu spoofing giúp thiết kế phòng vệ theo lớp: phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS và Wi-Fi, cùng biện pháp bảo vệ trong hạ tầng đám mây. Bài học đặt các hình thức giả mạo vào quy trình **threat modeling** để trả lời ba câu hỏi: *có thể giả mạo điều gì, giả mạo được ở đâu và hệ thống cần kiểm chứng danh tính bằng cách nào?*

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **địa chỉ/nhãn do gói tin khai báo** với **danh tính đã được xác thực**.
2. Giải thích điều kiện xảy ra và hậu quả của IP spoofing, MAC spoofing, ARP spoofing, DNS spoofing, DHCP spoofing, IPv6 Neighbor Discovery/Router Advertisement spoofing và Wi-Fi evil twin.
3. Mô hình hóa spoofing theo **STRIDE** và xác định các **ranh giới tin cậy (trust boundaries)**.
4. Đọc một số dấu hiệu từ ARP table, DNS, gói tin và log mạng để xây dựng giả thuyết điều tra.
5. Chọn biện pháp phòng vệ theo lớp mạng, nhận biết giới hạn của từng biện pháp và đánh giá rủi ro còn lại.

## 2. Khái niệm cốt lõi: khai báo danh tính khác với xác thực danh tính

Một máy có thể gửi gói IPv4 với trường **Source Address** bất kỳ nếu hệ thống hoặc mạng cho phép tạo gói tương ứng. Tuy nhiên, **địa chỉ nguồn được ghi trong header không chứng minh ai đã gửi gói**. Tương tự, MAC address hay tên SSID của Wi-Fi là những giá trị có thể bị sao chép hoặc thay đổi; chỉ so khớp các giá trị này thường không đủ để xác thực thực thể.

Xét ba cấp độ thông tin:

| Cấp độ | Ví dụ | Mức tin cậy cần lưu ý |
|---|---|---|
| **Thông tin tự khai** | IP nguồn, MAC nguồn, tên SSID, câu trả lời DNS | Có thể bị sửa, giả mạo hoặc đến từ một hệ thống sai nguồn. |
| **Thông tin được ràng buộc bởi hạ tầng** | Cổng switch, VLAN, bản ghi gán IP–MAC từ DHCP snooping, cloud network interface | Đáng tin hơn khi cấu hình và kiểm soát hạ tầng đúng; vẫn phải xét thay đổi hợp lệ và sai cấu hình. |
| **Danh tính được xác thực bằng mật mã** | Chứng chỉ TLS được kiểm chứng, xác thực EAP-TLS, peer của IPsec/mTLS được xác minh | Có thể bảo đảm thực thể sở hữu khóa phù hợp với danh tính được chính sách tin cậy chấp nhận; còn phụ thuộc cấu hình, khóa và chuỗi tin cậy. |

**Spoofing không tự động đồng nghĩa với MITM.** Giả mạo chỉ mô tả việc mạo danh thông tin/đối tượng. MITM là vị trí trung gian có thể quan sát hoặc can thiệp lưu lượng. Một vụ giả mạo có thể dùng để tạo MITM, nhưng nhiều trường hợp chỉ gây từ chối dịch vụ (DoS), phân giải sai tên miền hoặc làm nhiễu log. Ngược lại, một thiết bị trung gian được cấu hình hợp lệ không nhất thiết là tấn công.

**Phạm vi kiểm soát quyết định khả năng giả mạo.** Người trong cùng miền quảng bá (broadcast domain) thường có cơ hội tác động ARP/DHCP nhiều hơn người chỉ có khả năng gửi lưu lượng từ Internet. Giả mạo IP nguồn trên Internet vẫn có thể bị hạn chế bởi kiểm tra chống spoofing của ISP hoặc router biên. Các điều kiện này phải được nêu rõ khi mô hình hóa.

## 3. Các dạng spoofing thường gặp

### 3.1. IP source spoofing — giả mạo địa chỉ IP nguồn

**Vị trí:** Tầng mạng (OSI Layer 3), trong header IPv4 hoặc IPv6.

Một gói có thể khai báo IP nguồn khác với IP của thiết bị thực sự tạo gói. Điều này có thể làm log quy nhầm nguồn lưu lượng, gây khó khăn cho điều tra, hoặc hỗ trợ một số kiểu tấn công làm cạn tài nguyên và phản xạ/khuếch đại khi giao thức cho phép.

Ví dụ khái niệm: một firewall nhận gói UDP tự khai **192.0.2.10** là nguồn, dù gói thực tế được phát từ mạng không được ủy quyền. Nếu chính sách chỉ dựa vào trường địa chỉ nguồn mà thiếu kiểm tra điểm vào, firewall có thể đưa ra quyết định sai.

**Giới hạn quan trọng:** Chỉ giả mạo địa chỉ nguồn thường không đủ để hoàn tất kết nối TCP thông thường, vì phản hồi của quá trình bắt tay sẽ đi đến địa chỉ bị giả mạo. Khả năng quan sát đường hồi đáp, điều khiển tuyến hoặc tấn công khi ở trên đường truyền sẽ thay đổi mô hình nguy cơ; không thể suy ra mọi kết nối TCP đều dễ bị mạo danh chỉ từ việc IP header có thể sửa được.

**Phòng vệ:** ingress/egress filtering theo nguyên tắc **BCP 38**; kiểm tra địa chỉ nguồn hợp lệ trên cổng giao tiếp; **uRPF** khi phù hợp với kiến trúc định tuyến; không dùng IP nguồn làm chứng cứ xác thực duy nhất. Hệ thống giám sát phải phân biệt địa chỉ được gói tin khai báo với nguồn nhận biết từ cổng/đường đi.

### 3.2. MAC spoofing — giả mạo địa chỉ vật lý

**Vị trí:** Tầng liên kết dữ liệu (Layer 2), ví dụ địa chỉ MAC nguồn trong Ethernet frame.

Một thiết bị có thể sử dụng MAC của thiết bị khác hoặc một MAC do nó tự đặt. Điều này có thể đánh lừa các kiểm soát **chỉ dựa vào danh sách MAC được phép**, gây xung đột bảng học MAC hoặc che giấu nguồn thực trong phạm vi mạng cục bộ.

Khác với IP nguồn có thể đi qua nhiều hop, **MAC trong Ethernet frame chủ yếu có ý nghĩa trên liên kết hiện tại**: router tạo frame mới với MAC tương ứng ở hop kế tiếp. Vì thế MAC mà thiết bị giám sát nhìn thấy không nhất thiết là MAC của máy đầu cuối ở mạng xa.

**Phòng vệ:** xác thực truy cập mạng **IEEE 802.1X** (ưu tiên cấu hình dựa trên chứng chỉ như EAP-TLS khi phù hợp), giới hạn cổng switch, kiểm soát thiết bị và theo dõi biến động MAC. **MAC allowlist** chỉ nên được xem là kiểm soát phụ trợ, không phải bằng chứng xác thực mạnh.

### 3.3. ARP spoofing/ARP poisoning — giả mạo ánh xạ IPv4–MAC

**Vị trí:** ARP trong miền liên kết cục bộ của IPv4.

ARP dùng để tìm MAC tương ứng với một địa chỉ IPv4 trong mạng liên kết. Khi một máy tiếp nhận thông tin ARP giả, nó có thể cập nhật bảng láng giềng để cho rằng **IP của gateway** ứng với **MAC của một thiết bị khác**. Khi đó traffic có thể bị chuyển sai, gián đoạn hoặc đi qua một điểm trung gian ngoài ý muốn.

~~~text
Trạng thái đúng:
Máy A ── ARP: Gateway 192.0.2.1 → MAC-GW ──> Gateway

Trạng thái bị đầu độc:
Máy A ── ARP: Gateway 192.0.2.1 → MAC-X  ──> Thiết bị X
                                             │
                                             └── Có thể chặn, chuyển tiếp
                                                 hoặc làm gián đoạn lưu lượng
~~~

Ví dụ dùng địa chỉ **192.0.2.0/24** dành cho tài liệu. Mô tả không có nghĩa mọi mạng đều chấp nhận cập nhật ARP tùy ý: cấu hình OS, switch, cơ chế kiểm soát ARP và kiến trúc VLAN ảnh hưởng trực tiếp tới kết quả.

**Điều kiện điển hình:** tác nhân có khả năng gửi thông điệp trên **cùng miền liên kết có liên quan**, hoặc có quyền kiểm soát thiết bị mạng tại điểm đó. Một kẻ tấn công từ mạng xa thường không thể tùy ý gửi ARP tới LAN qua router chuẩn.

**Phòng vệ:** bật **DHCP snooping** để xây dựng cơ sở gán IP–MAC–cổng đáng tin cậy khi môi trường hỗ trợ; áp dụng **Dynamic ARP Inspection (DAI)**; dùng cấu hình ARP tĩnh một cách chọn lọc cho trường hợp thích hợp; tách VLAN/guest Wi-Fi và giám sát ARP thay đổi bất thường. DAI cần được cấu hình đúng cổng trusted/untrusted và xử lý host IP tĩnh theo thiết kế, nếu không có thể gây mất kết nối hợp lệ.

### 3.4. DNS spoofing — giả mạo thông tin phân giải tên

**Vị trí:** Hệ thống phân giải tên (DNS), nơi tên miền được chuyển thành các bản ghi như A/AAAA/CNAME.

Lưu lượng có thể bị dẫn tới địa chỉ sai nếu thiết bị nhận một câu trả lời DNS giả, nếu bản ghi trong cache bị đầu độc, hoặc nếu máy bị đổi sang resolver do tác nhân không đáng tin điều khiển. Hậu quả bao gồm truy cập website giả, chuyển hướng API hoặc làm gián đoạn hệ thống.

**DNS spoofing, DNS cache poisoning và domain impersonation không hoàn toàn là một.** DNS spoofing nói đến thông tin DNS bị giả mạo; cache poisoning là một cách làm sai cache của resolver; domain impersonation có thể chỉ là đăng ký tên miền trông giống thương hiệu thật, ngay cả khi DNS của tên miền đó hoạt động đúng.

**Phòng vệ theo chức năng:**

- **DNSSEC:** khi vùng DNS được ký, chuỗi tin cậy được thiết lập và resolver **thực sự xác thực chữ ký**, giúp phát hiện dữ liệu DNS đã bị giả mạo trong phạm vi bảo vệ. DNSSEC không tự mã hóa truy vấn, không ký mọi tên miền và không bảo vệ máy khỏi việc người dùng chủ động truy cập một tên miền độc hại có bản ghi hợp lệ.
- **DoT/DoH:** mã hóa và bảo vệ kết nối giữa client và resolver nếu được xác thực đúng; chúng không tự bảo đảm rằng dữ liệu do resolver trả về là đúng nếu chính resolver không đáng tin.
- **TLS/HTTPS với kiểm tra chứng chỉ:** giúp xác thực máy chủ ứng dụng khi tên miền phân giải sai. Cảnh báo chứng chỉ là tín hiệu cần điều tra; không nên hướng dẫn người dùng bỏ qua cảnh báo.
- **Quản trị resolver:** hạn chế thay đổi DNS không được phép, giám sát bản ghi quan trọng và kiểm soát cấu hình DHCP/VPN cung cấp DNS cho client.

### 3.5. Rogue DHCP — giả mạo máy chủ cấp phát cấu hình mạng

**Vị trí:** DHCP trong mạng cục bộ.

Một DHCP server không được phê duyệt có thể cấp **IP, default gateway hoặc DNS resolver** khác cấu hình dự kiến cho client. Thiết bị đầu cuối có thể nhận nhầm default gateway hoặc chuyển truy vấn DNS sang máy chủ không đáng tin, từ đó tạo điều kiện cho chuyển hướng hoặc gián đoạn lưu lượng.

**Phòng vệ:** DHCP snooping trên switch với cổng cung cấp DHCP đã được ủy quyền; 802.1X và kiểm soát cổng; giám sát log cấp phát và phát hiện nhiều DHCP server bất thường. Cần phân biệt server chính/phụ được cấp phép với server lạ trước khi kết luận sự cố.

### 3.6. IPv6 Neighbor Discovery và Router Advertisement spoofing

**Vị trí:** IPv6 dùng **ICMPv6 Neighbor Discovery (ND)** thay cho ARP; Router Advertisement (RA) giúp host biết router và một số tham số mạng.

Trong môi trường không có biện pháp bảo vệ phù hợp, thông điệp **Neighbor Advertisement** giả có thể làm sai ánh xạ IPv6–MAC. **Router Advertisement** giả có thể khiến host nhận thông tin router hoặc prefix ngoài ý muốn, gây thay đổi đường đi hay cấu hình mạng.

**Phòng vệ:** **RA Guard** trên thiết bị chuyển mạch hỗ trợ và cấu hình đúng; kiểm soát ND theo khả năng của nền tảng; phân tách miền L2 và áp dụng chính sách IPv6 tương ứng. RA Guard có giới hạn triển khai, đặc biệt với việc xử lý IPv6 extension headers và các biến thể gói tin: cần xác minh theo thiết bị/phiên bản. Những gói ICMPv6 phục vụ ND và Path MTU Discovery là thiết yếu cho IPv6; chặn bừa bãi mọi ICMPv6 có thể làm mạng lỗi.

### 3.7. Wi-Fi evil twin — giả mạo mạng không dây

**Vị trí:** Nhận diện và kết nối với điểm truy cập không dây.

Một điểm truy cập không được ủy quyền có thể phát **SSID giống mạng hợp lệ**, khiến người dùng nhận diện nhầm. Chỉ nhìn thấy cùng tên SSID **không** chứng minh điểm truy cập là của tổ chức. Trong một số cấu hình yếu, kẻ tấn công có thể dụ người dùng kết nối rồi quan sát/chuyển hướng lưu lượng hoặc đưa tới captive portal giả.

**Phòng vệ:** xác thực Wi-Fi doanh nghiệp bằng **802.1X/EAP-TLS**, cấu hình và **kiểm chứng chứng chỉ của máy chủ xác thực** đúng cách; quản lý hồ sơ mạng; kiểm tra AP/BSSID từ hệ thống quản trị không dây; WIDS/WIPS khi phù hợp. **Protected Management Frames (PMF)** bảo vệ một số frame quản lý trong phiên Wi-Fi, nhưng tự nó không xác thực rằng SSID/AP là điểm truy cập doanh nghiệp đúng.

## 4. Liên hệ spoofing với STRIDE và ranh giới tin cậy

**STRIDE** là cách phân loại mối đe dọa gồm **Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege**. Spoofing là một nhóm trong STRIDE, nhưng một cuộc tấn công bắt đầu từ giả mạo có thể dẫn tới các nhóm khác:

| Hành vi | Phân loại STRIDE liên quan | Hệ quả minh họa |
|---|---|---|
| Thiết bị giả mạo gateway bằng ARP | **S** (Spoofing), có thể dẫn tới **T/I/D** | Lưu lượng bị chuyển hướng, sửa đổi, lộ hoặc gián đoạn. |
| Câu trả lời DNS giả | **S**, có thể dẫn tới **T/I** | Client kết nối địa chỉ khác mong đợi; rủi ro phụ thuộc xác thực tầng ứng dụng. |
| Rogue DHCP cấp default gateway sai | **S**, có thể dẫn tới **D/I** | Máy nhận cấu hình sai, mất mạng hoặc gửi lưu lượng qua điểm khác. |
| Source IP spoof trong log | **S**, có thể gây khó khăn cho việc truy vết **R** | Không xác định đúng tác nhân nếu chỉ dựa trên IP được khai báo. |
| Evil twin yêu cầu xác thực giả | **S**, có thể dẫn tới **I/E** | Lộ thông tin đăng nhập, có thể phát sinh truy cập trái phép nếu thông tin bị lạm dụng. |

Các chữ cái khác trong STRIDE chỉ là **hậu quả có thể xảy ra**, không tự động xảy ra trong mọi vụ spoofing. Ví dụ, ARP giả mà không có khả năng nhận/chuyển tiếp lưu lượng thường gây gián đoạn hơn là MITM hoàn chỉnh.

### Ví dụ kiến trúc cần bảo vệ

Xét một hệ thống tổ chức có nhân viên dùng Wi-Fi, truy cập ứng dụng nội bộ và dịch vụ chạy trên cloud:

~~~text
                  [Thiết bị nhân viên]
                          │
       Ranh giới 1: xác thực Wi-Fi / cấp quyền thiết bị
                          │
                    [Access Point]
                          │
               [Switch / VLAN nội bộ]
                    │            │
        [DHCP & DNS nội bộ]    [Gateway / Firewall]
                                    │
                    Ranh giới 2: mạng nội bộ ↔ Internet
                                    │
                         [Internet / VPN tunnel]
                                    │
                    Ranh giới 3: xác thực VPN và cloud
                                    │
                       [VPC/VNet + workload API]
~~~

Với sơ đồ này, spoofing cần được xét ở nhiều ranh giới:

- **Ranh giới 1:** ai được phép tham gia mạng Wi-Fi/VLAN; thiết bị có thể mạo danh MAC hay SSID không?
- **Trong VLAN:** thiết bị nào có thể gửi ARP, DHCP, Neighbor Discovery hoặc RA; host có tin thông điệp từ nguồn không được kiểm soát không?
- **Ranh giới 2:** router/firewall có loại bỏ địa chỉ nguồn bất hợp lý trên đường vào/ra không; firewall có phụ thuộc quá nhiều vào IP không?
- **Ranh giới 3:** kết nối VPN, tài khoản thiết bị và API cloud có xác thực mật mã đúng danh tính không; địa chỉ IP riêng trong cloud có bị xem nhầm là đủ để cấp quyền không?

Ở cloud, mức độ chống spoofing của card mạng ảo, gateway, hypervisor và chính sách mạng tùy nhà cung cấp, loại dịch vụ và cấu hình. Không thể mặc định cơ chế kiểm soát VLAN/DAI của switch vật lý áp dụng y nguyên cho mọi VPC/VNet.

## 5. Quy trình threat modeling cho spoofing

Một cách thực hiện có thể lặp lại:

1. **Xác định tài sản:** tài khoản/phiên đăng nhập, thông tin khách hàng, lưu lượng quản trị, DNS nội bộ, gateway, workload cloud, tính sẵn sàng của dịch vụ.
2. **Vẽ luồng dữ liệu:** từ client qua AP/switch/router/VPN/DNS đến backend; nêu rõ các giao thức L2/L3/L7 và bên nào có quyền ghi cấu hình.
3. **Đánh dấu ranh giới tin cậy:** miền quảng bá, mạng khách/nội bộ, biên Internet, tunnel VPN, vùng cloud, tài khoản dịch vụ.
4. **Nêu tác nhân và năng lực:** khách Wi-Fi không xác thực, máy nội bộ đã bị xâm nhập, đối tác có quyền VPN giới hạn, nguồn Internet, quản trị viên sai cấu hình. Không gộp mọi tác nhân thành một kẻ tấn công “toàn năng”.
5. **Liệt kê đường giả mạo và điều kiện:** loại thông điệp nào có thể bị làm giả; thiết bị nhận dựa vào trường tự khai hay bằng chứng xác thực; spoofing có thực sự vượt qua ranh giới này không?
6. **Ước lượng khả năng/hậu quả, chọn kiểm soát và kiểm tra:** ưu tiên theo phạm vi ảnh hưởng và dữ liệu được bảo vệ; đo khả năng phát hiện, ngăn chặn và phục hồi.

Một mẫu ghi nhận ngắn cho từng mối đe dọa:

~~~text
ID: SP-01
Tài sản: Kết nối tới API nội bộ và dữ liệu phiên
Tác nhân: Thiết bị lạ được kết nối vào cùng VLAN với máy nhân viên
Điểm vào: Thông điệp ARP trong VLAN
Giả định/điều kiện: Host tin ánh xạ ARP nhận được; switch chưa có DAI
Kịch bản: Host nhận ánh xạ gateway-IP → MAC không thuộc gateway
Hậu quả: Chuyển hướng/gián đoạn; rủi ro lộ dữ liệu tùy TLS và đường đi
Kiểm soát: 802.1X, VLAN, DHCP snooping + DAI, TLS xác thực máy chủ
Phát hiện: Thay đổi IP–MAC gateway bất thường, log switch, bắt gói xác minh
Rủi ro còn lại: Sai cấu hình DAI, máy hợp lệ bị chiếm quyền, thiếu log tập trung
~~~

### Bảng ưu tiên ví dụ

Các mức trong bảng chỉ là **ví dụ định tính** cho một mạng văn phòng giả định, không phải kết quả đo của một hệ thống thực:

| ID | Kịch bản và giả định | Khả năng | Tác động | Ưu tiên ban đầu |
|---|---|---|---|---|
| SP-01 | ARP poisoning trong VLAN nhân viên không có DAI | Trung bình | Cao: chuyển hướng kết nối nội bộ | **Cao** |
| SP-02 | Wi-Fi evil twin khi máy khách xác thực EAP-TLS và xác minh chứng chỉ đúng | Thấp hơn | Cao nếu xác thực người dùng thất bại | **Trung bình** |
| SP-03 | Forged source IP từ Internet nhắm vào dịch vụ UDP có thể phản xạ, biên không lọc nguồn | Trung bình | Cao: ảnh hưởng tính sẵn sàng và bên thứ ba | **Cao** |
| SP-04 | DNS response giả tới client kiểm tra TLS hợp lệ và resolver có DNSSEC validation cho vùng đã ký | Thấp hơn | Trung bình, tùy loại dịch vụ | **Thấp–trung bình** |

Mức ưu tiên thay đổi nếu tổ chức dùng VLAN khác, có threat actor nội bộ, dữ liệu nhạy cảm hơn, phát hiện chậm hơn hoặc có các biện pháp bổ sung. Nên ghi rõ tiêu chí chấm điểm khả năng/tác động và người chịu trách nhiệm cho rủi ro.

## 6. Quan sát và phát hiện: tìm bằng chứng, tránh suy diễn

### Dấu hiệu theo lớp mạng

| Lớp/nguồn log | Dấu hiệu cần đối chiếu | Giới hạn của dấu hiệu |
|---|---|---|
| **Switch CAM/MAC table** | MAC xuất hiện bất thường trên nhiều cổng, thay đổi vị trí liên tục | Di chuyển thiết bị, link aggregation, virtual machine cũng có thể gây thay đổi hợp lệ. |
| **ARP table / bắt gói ARP** | IP gateway ánh xạ tới MAC mới không thuộc thiết bị quản lý; thông điệp ARP trả lời bất thường | Gateway HA/failover, chuyển NIC, thay router có thể đổi MAC hợp lệ. |
| **DHCP snooping/lease log** | Có DHCP server hoặc option gateway/DNS chưa được phê duyệt | DHCP server dự phòng hoặc chuyển đổi hệ thống là trường hợp bình thường cần đối chiếu cấu hình. |
| **IPv6 ND/RA** | Router Advertisement từ cổng không được cấp phép hoặc thay đổi router/prefix ngoài kế hoạch | Router/switch chuyển trạng thái và cập nhật mạng có thể là hoạt động bảo trì. |
| **DNS log** | Bản ghi A/AAAA trả về khác resolver chuẩn; resolver client bị thay | CDN, cân bằng tải, split-horizon DNS và TTL có thể tạo khác biệt hợp lệ. |
| **IDS/IPS và flow logs** | IP nguồn trái với subnet/cổng vào dự kiến, lưu lượng không khớp đường đi | NAT, VPN, proxy, định tuyến bất đối xứng cần được tính vào mô hình. |
| **Wi-Fi controller/WIDS** | SSID trùng tên từ BSSID lạ, certificate server không hợp lệ | AP mới, bộ phát hợp pháp hoặc mạng gần đó dùng cùng tên cần được xác minh. |

**Nguyên tắc điều tra:** một tín hiệu đơn lẻ hiếm khi đủ kết luận spoofing. Hãy tương quan timestamp, VLAN/interface, DHCP lease, MAC-to-port, địa chỉ IP, resolver, log xác thực, tài khoản và trạng thái thay đổi hạ tầng.

### Lệnh quan sát an toàn trên hệ thống được phép kiểm tra

Các lệnh sau chỉ dùng để **đọc thông tin cấu hình, láng giềng hoặc DNS**; kết quả phụ thuộc hệ điều hành, quyền và trạng thái cache.

Trên **Linux**:

~~~bash
ip -br addr                   # Địa chỉ và interface đang hoạt động
ip route                      # Đường đi IPv4, gồm default gateway
ip neigh show                 # Bảng láng giềng ARP/ND hiện tại
resolvectl status             # Resolver theo liên kết, nếu dùng systemd-resolved
~~~

Trên **Windows (Command Prompt hoặc PowerShell)**:

~~~text
ipconfig /all                 # Địa chỉ, gateway, DHCP và DNS server
arp -a                        # Bảng ánh xạ IPv4–MAC đang lưu
route print                   # Bảng định tuyến
nslookup example.com          # Câu trả lời DNS từ resolver được chọn
~~~

Trên hệ thống có **dig**, có thể so kết quả từ resolver mặc định với một resolver được tổ chức phê duyệt:

~~~bash
dig example.com A
dig example.com AAAA
~~~

Khác biệt về IP **không tự chứng minh** DNS giả mạo; cần xét CDN, TTL, DNS nội bộ và vị trí truy vấn. Cờ DNSSEC **AD** chỉ có ý nghĩa khi hiểu cách resolver xác thực dữ liệu và cách kết nối client–resolver được bảo vệ; không thể mặc định một kết quả có AD nghĩa là mọi thành phần trên đường đều đáng tin.

### Bộ lọc Wireshark hữu ích

~~~text
arp                              # Thông điệp ARP
arp.opcode == 2                  # ARP reply
bootp                            # DHCPv4 trong nhiều phiên bản Wireshark
icmpv6.type == 134               # IPv6 Router Advertisement
icmpv6.type == 136               # IPv6 Neighbor Advertisement
dns.flags.response == 1          # Thông điệp trả lời DNS
ip.src == 192.0.2.10             # Gói IPv4 tự khai địa chỉ nguồn ví dụ
~~~

Phần lớn bộ lọc chỉ **chọn gói để xem**, không trực tiếp khẳng định spoofing. Một cuộc kiểm tra cần thêm địa chỉ MAC hợp lệ, sơ đồ mạng, VLAN, mapping IP–MAC–switch port và log thay đổi. Nếu thiếu quyền bắt gói, có thể dùng PCAP mẫu đã được cấp phép.

## 7. Thiết kế phòng vệ nhiều lớp

Không có một cơ chế riêng lẻ chặn được mọi loại spoofing. Một kiến trúc phòng vệ tốt kết hợp **kiểm soát điểm vào**, **kiểm chứng thông tin mạng** và **xác thực thực thể ở cấp ứng dụng**.

| Lớp phòng vệ | Biện pháp | Ngăn hoặc hạn chế điều gì? | Điểm cần kiểm tra khi triển khai |
|---|---|---|---|
| Truy cập LAN/Wi-Fi | 802.1X với EAP-TLS, quản trị hồ sơ client, phân đoạn VLAN/SSID | Thiết bị lạ khó tham gia vùng tin cậy chỉ bằng việc đổi MAC hoặc SSID | Kiểm tra chứng chỉ, vòng đời thiết bị, VLAN và guest isolation. |
| Ethernet/IPv4 cục bộ | DHCP snooping, DAI, IP Source Guard (nếu hỗ trợ) | Rogue DHCP, ARP poisoning, nguồn IP/MAC không khớp binding tại cổng | Đặt đúng cổng trusted, IP tĩnh, failover, phạm vi switch. |
| IPv6 cục bộ | RA Guard, cơ chế ND inspection tương thích | RA/ND giả trong cùng mạng liên kết | Khả năng nhận diện extension headers, host hợp lệ và ICMPv6 thiết yếu. |
| Router/Internet edge | Ingress/egress filtering, uRPF phù hợp | Gói đến/đi với địa chỉ nguồn không hợp lệ tại biên | Định tuyến bất đối xứng, multi-homing, tunnel và route dự phòng. |
| DNS | Resolver được quản lý, DNSSEC validation, giám sát DNS, DoT/DoH phù hợp | Sai lệch DNS, resolver trái phép, giả mạo dữ liệu từ vùng được ký | Chuỗi tin cậy DNSSEC và cấu hình client; mã hóa DNS không thay thế xác thực kết quả. |
| Vận chuyển/ứng dụng | TLS/mTLS, IPsec hoặc VPN với xác thực peer, ủy quyền theo danh tính | Giả mạo endpoint hoặc đọc/sửa dữ liệu ngay cả khi lưu lượng bị chuyển hướng | Kiểm tra chứng chỉ/tên, khóa, thu hồi, phân quyền, DNS nội bộ. |
| Phát hiện và phản ứng | IDS/IPS, SIEM, flow logs, Wi-Fi controller, switch logs | Nhận diện lệch chuẩn, khoanh vùng ảnh hưởng, lưu bằng chứng | Chuẩn hóa thời gian, độ bao phủ log, cảnh báo giả, thử nghiệm phục hồi. |

**Phân đoạn mạng giảm phạm vi ảnh hưởng**, nhưng không tự xác thực thiết bị trong cùng VLAN. **Firewall theo IP/cổng** cần kết hợp chính sách theo danh tính khi bảo vệ tài nguyên quan trọng. **VPN mã hóa đường hầm** khi được cấu hình đúng, nhưng không chứng minh rằng mỗi máy/tài khoản bên trong đường hầm đều an toàn; vẫn cần kiểm soát truy cập ở đích.

Trong môi trường cloud hoặc hybrid, cần đồng thời kiểm tra firewall/security group, route table, mạng riêng, cấu hình DNS private, quyền của workload và tính năng chống IP/MAC spoofing của nền tảng. Nếu ứng dụng cấp quyền chỉ vì request xuất phát từ một private IP, việc một workload được cấp quyền mạng quá rộng vẫn có thể trở thành rủi ro dù không hề có giả mạo gói ở tầng thấp.

## 8. Tình huống thực hành: phát hiện gateway có ánh xạ bất thường

**Bối cảnh giả định:** Một máy nhân viên có IP **192.0.2.20/24**, default gateway **192.0.2.1**. Hệ thống quản trị mạng xác nhận MAC gateway hợp lệ là **02:11:22:33:44:55**; sau một thời điểm, máy nhân viên ghi nhận:

~~~text
IP gateway:    192.0.2.1
MAC trước đó:  02:11:22:33:44:55
MAC hiện tại:  02:AA:BB:CC:DD:EE
Triệu chứng:   Một số kết nối chậm hoặc bị ngắt quãng
~~~

Đây là **dấu hiệu cần điều tra**, chưa đủ để kết luận bị tấn công. Hãy xử lý theo quy trình:

1. **Xác minh thực tế:** kiểm tra xem gateway có thay thiết bị, HA failover, đổi MAC ảo hoặc bảo trì gần thời điểm đó hay không.
2. **Đối chiếu độc lập:** lấy mapping IP–MAC từ switch/router hoặc hệ thống quản lý được tin cậy; xác định cổng/VLAN có MAC mới.
3. **Kiểm tra bằng chứng:** nếu có quyền, xem log ARP và switch, thời điểm MAC đổi, những máy khác bị tác động, sự hiện diện của DHCP server lạ và sự thay đổi DNS.
4. **Đánh giá hậu quả:** xác định liệu lưu lượng bị mất hay chỉ đổi đường, có bằng chứng chuyển hướng, thay đổi chứng chỉ TLS, lỗi xác thực hoặc mất dữ liệu hay không.
5. **Khống chế trong phạm vi được ủy quyền:** cô lập cổng/thiết bị gây nghi vấn theo quy trình sự cố; kiểm tra cấu hình DHCP snooping/DAI; tránh tự ý chặn gateway hợp lệ khi chưa xác nhận nguồn.
6. **Khôi phục và phòng ngừa tái diễn:** xác minh mapping đúng, kết nối ứng dụng bình thường và bổ sung cảnh báo IP–MAC bất thường cùng nhật ký từ switch.

Nếu MAC mới được quản trị mạng xác nhận thuộc gateway dự phòng hoạt động đúng, sự kiện là **false positive**. Nếu MAC mới thuộc thiết bị trái phép trong VLAN, có các thông điệp ARP bất thường tương ứng và lưu lượng bị chuyển hướng, bằng chứng ủng hộ giả thuyết ARP spoofing.

### Câu hỏi vận dụng

1. Vì sao ARP poisoning thường đòi hỏi tác nhân ở cùng miền liên kết, trong khi IP source spoofing có thể xuất hiện ở ranh giới Internet?
2. Vì sao chỉ cấu hình MAC allowlist chưa đủ để bảo vệ mạng Wi-Fi doanh nghiệp?
3. DNSSEC, DoT/DoH và TLS giải quyết **những khâu tin cậy nào khác nhau**?
4. Vì sao một hệ thống bật TLS đúng cách vẫn nên triển khai DAI/RA Guard và theo dõi chuyển hướng gateway?
5. Trong ví dụ gateway đổi MAC, thông tin nào có thể phân biệt **failover hợp lệ** với **ARP spoofing**?

## 9. Checklist áp dụng vào kiến trúc thực tế

Khi review một sơ đồ mạng, có thể sử dụng các câu hỏi sau:

- **Ranh giới truy cập:** Thiết bị và người dùng xác thực qua gì? Có cấp quyền chỉ vì cùng SSID/VLAN/MAC không?
- **Tầng liên kết:** Switch có DHCP snooping/DAI hoặc cơ chế tương đương không? Giao thức IPv6 có được bảo vệ tương ứng không?
- **Tầng IP:** Có kiểm tra địa chỉ nguồn ở biên mạng? Định tuyến đa đường có làm sai giả định của uRPF không?
- **DNS:** Client nhận resolver từ đâu? Có kiểm soát thay đổi cấu hình, kiểm chứng DNSSEC ở nơi phù hợp và theo dõi truy vấn/bản ghi bất thường không?
- **Tầng ứng dụng:** TLS/mTLS/IPsec có xác minh danh tính peer và được quản lý khóa đúng không? Quyền truy cập có phụ thuộc duy nhất vào IP không?
- **Giám sát:** Log từ switch, AP, DNS, firewall, VPN và cloud có timestamp tương quan được không? Có quy trình phân biệt sự cố thật với failover hợp lệ không?
- **Phản ứng:** Ai có quyền cô lập cổng/SSID/workload, thu thập bằng chứng, khôi phục gateway và xác nhận dịch vụ hoạt động?

Checklist này giúp chuyển mô hình đe dọa từ danh sách kiểu tấn công thành **yêu cầu kiểm soát có thể kiểm tra**, gắn từng rủi ro với vị trí cụ thể trong kiến trúc.

## 10. Ghi nhớ trọng tâm

**Spoofing là làm sai thông tin mà hệ thống dùng để nhận diện nguồn, đích hoặc thực thể mạng.** IP, MAC, ARP, DNS, DHCP, IPv6 ND/RA và SSID đều có những điểm tin cậy riêng; khả năng bị giả mạo phụ thuộc vị trí tác nhân và mức kiểm soát của hạ tầng.

Khi mô hình hóa theo STRIDE, hãy xác định **tài sản**, **đường dữ liệu**, **ranh giới tin cậy**, **điều kiện tiên quyết**, **hậu quả** và **cách kiểm chứng danh tính**. Phòng vệ hiệu quả cần nhiều lớp: xác thực thiết bị, DHCP snooping/DAI và bảo vệ ND/RA, lọc nguồn IP ở biên, DNSSEC/DNS bảo mật, TLS/VPN xác thực đúng peer, phân đoạn mạng và giám sát tập trung. Một địa chỉ hoặc thông điệp nhìn có vẻ hợp lệ chỉ là **dữ liệu cần được kiểm tra**, không tự thân là bằng chứng danh tính.
