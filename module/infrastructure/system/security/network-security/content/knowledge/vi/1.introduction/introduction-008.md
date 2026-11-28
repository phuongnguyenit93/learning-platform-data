# Mạng nội bộ không mặc nhiên đáng tin

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao một thiết bị, người dùng hoặc dịch vụ ở trong LAN, kết nối Wi-Fi công ty hay đi qua VPN vẫn có thể trở thành nguồn tấn công.
- Phân biệt vị trí mạng, danh tính, trạng thái thiết bị và quyền truy cập; nhận ra những giả định tin cậy nguy hiểm.
- Mô tả cách kẻ tấn công di chuyển ngang (lateral movement) và khai thác lưu lượng nội bộ (east–west traffic).
- Kết hợp phân đoạn mạng, firewall, xác thực kết nối, mã hóa, kiểm soát quyền, DNS an toàn và giám sát để hạn chế phạm vi ảnh hưởng.
- Đề xuất quy tắc truy cập, kịch bản kiểm thử và tín hiệu giám sát cho một hệ thống có nhiều vùng mạng.

## 1. Một mạng có ranh giới, nhưng ranh giới không bảo đảm độ tin cậy

Trong mô hình truyền thống, doanh nghiệp dựng firewall ở biên, chặn nhiều kết nối từ Internet và cho phép tương đối rộng những kết nối xuất phát từ mạng nội bộ. Mô hình này có giá trị trong việc giảm bề mặt tấn công, nhưng dễ dẫn tới suy luận sai: **đã ở bên trong thì được tin cậy**.

Xét một hệ thống quản lý đơn hàng:

1. Nhân viên kết nối mạng văn phòng hoặc VPN.
2. Máy tính nhân viên gửi yêu cầu tới API nội bộ.
3. API đọc dữ liệu trong cơ sở dữ liệu (CSDL) và gọi các dịch vụ khác.

Nếu API chỉ kiểm tra địa chỉ IP thuộc dải nội bộ rồi cho phép thao tác, một máy nhân viên nhiễm mã độc, tài khoản VPN bị chiếm hoặc một dịch vụ nội bộ bị xâm nhập đều có thể được hưởng quyền mà chúng không đáng có. **Địa chỉ mạng cho biết đường đi của kết nối; nó không chứng minh người gửi là ai, thiết bị có an toàn hay người gửi được phép làm gì.**

Những tình huống thực tế khiến ranh giới bên ngoài không còn đủ mạnh:

- Máy tính trong văn phòng bị cài mã độc qua tệp đính kèm hoặc trình duyệt.
- Đối tác có quyền vào một phân đoạn mạng qua VPN nhưng tìm thấy các cổng dịch vụ không liên quan.
- Thiết bị IoT, máy in hoặc camera có phần mềm cũ bị chiếm quyền điều khiển.
- Wi-Fi khách bị cấu hình chung VLAN với hệ thống quản trị.
- Kẻ tấn công kiểm soát một container hoặc máy chủ ứng dụng, rồi dò tìm các máy khác trong cùng mạng.
- Nhân viên nội bộ hoặc tài khoản dịch vụ có quyền vượt quá nhu cầu công việc.

Vấn đề không nằm ở việc mọi thành phần nội bộ đều độc hại. Vấn đề là **không được dùng vị trí nội bộ làm bằng chứng đủ để cấp quyền**.

## 2. Phân biệt các khái niệm tin cậy

| Khái niệm | Trả lời câu hỏi | Điều không chứng minh được |
| --- | --- | --- |
| Vị trí mạng | Kết nối đến từ VLAN, subnet, VPC hay đường hầm nào? | Danh tính người dùng, mục đích hoặc quyền nghiệp vụ |
| Xác thực (authentication) | Người dùng, thiết bị hoặc dịch vụ là ai? | Chủ thể được quyền đọc hoặc sửa mọi tài nguyên |
| Ủy quyền (authorization) | Chủ thể được làm hành động gì với tài nguyên nào? | Thiết bị đang sạch mã độc hoặc phiên vẫn an toàn |
| Trạng thái thiết bị (device posture) | Thiết bị có đáp ứng các điều kiện quản lý, cập nhật, bảo vệ không? | Người sử dụng được phép truy cập mọi hệ thống |
| Mã hóa kênh truyền | Dữ liệu trên đường truyền có được bảo vệ trước nghe lén/sửa đổi không? | Nội dung yêu cầu là hợp lệ về nghiệp vụ |
| Giám sát | Có tín hiệu để phát hiện và điều tra hành vi bất thường không? | Có thể ngăn chặn mọi hành vi ngay lập tức |

Ví dụ: nhân viên A đã đăng nhập hợp lệ và đang sử dụng laptop được quản lý. A vẫn không thể được phép đọc hồ sơ của khách hàng B nếu vai trò và quy tắc nghiệp vụ không cho phép. Tương tự, kết nối TLS hợp lệ không làm cho một câu lệnh nguy hiểm trở nên an toàn.

Hai hướng lưu lượng cũng cần được phân biệt:

- **North–south:** từ bên ngoài vào hệ thống hoặc từ hệ thống ra mạng bên ngoài, thường đi qua gateway, proxy hoặc firewall biên.
- **East–west:** giữa các máy chủ, dịch vụ, pod, subnet hoặc vùng mạng trong cùng tổ chức/đám mây. Đây là hướng dễ bị bỏ sót nếu chỉ bảo vệ cửa ngõ Internet.

## 3. Rủi ro khi tin mọi thứ bên trong mạng

### 3.1. Di chuyển ngang sau khi xâm nhập

Giả sử kẻ tấn công chiếm được một laptop của nhân viên:

~~~text
Laptop bị xâm nhập
   |
   +--> Dò tìm IP, cổng và dịch vụ nội bộ
   |
   +--> Thử truy cập máy chủ file, API, bảng điều khiển quản trị
   |
   +--> Lợi dụng mật khẩu, token hoặc phiên đăng nhập bị lộ
   |
   +--> Tiếp cận CSDL hoặc hệ thống quan trọng hơn
~~~

Quá trình này gọi là **di chuyển ngang**. Nếu mọi máy cùng một mạng phẳng, các dịch vụ mở cổng rộng và quyền tài khoản dùng chung, một điểm xâm nhập nhỏ có thể lan thành sự cố lớn. Phân đoạn và kiểm soát quyền theo từng kết nối có thể cắt đứt nhiều bước của chuỗi này.

### 3.2. Các kiểu tấn công trên mạng nội bộ

| Nguy cơ | Ví dụ | Biện pháp hạn chế |
| --- | --- | --- |
| Nghe lén lưu lượng | Dữ liệu hoặc token gửi qua giao thức không mã hóa | TLS, mTLS khi phù hợp, loại bỏ giao thức rõ văn bản |
| Giả mạo hoặc chen giữa kết nối | ARP spoofing trong cùng miền quảng bá, điểm truy cập Wi-Fi giả | Bảo vệ lớp 2, Wi-Fi doanh nghiệp, xác minh chứng chỉ, TLS |
| Truy cập ngang | Laptop người dùng kết nối trực tiếp cổng quản trị CSDL | VLAN/VRF, firewall nội bộ, ACL, chính sách deny-by-default |
| Lạm dụng quyền | Dịch vụ bị chiếm dùng token có quyền quá rộng | Danh tính riêng cho dịch vụ, quyền tối thiểu, token ngắn hạn |
| DNS bị lợi dụng | Máy trạm bị hướng tới tên miền giả hoặc phát truy vấn bất thường | DNS resolver được quản lý, kiểm soát truy vấn, ghi log và cảnh báo |
| Thiết bị không quản lý | Camera hoặc laptop khách chung vùng mạng với ứng dụng | 802.1X/NAC, mạng khách riêng, cô lập thiết bị |
| Khai thác cấu hình đám mây | Security group mở quá rộng cho cả dải private | Security group/NSG theo luồng cần thiết, kiểm toán định kỳ |

Các biện pháp trong bảng là những lớp bảo vệ bổ sung cho nhau. Chẳng hạn, VLAN chỉ chia miền quảng bá; nếu bộ định tuyến cho phép liên lạc giữa mọi VLAN, việc phân VLAN không ngăn được truy cập ngang.

## 4. Tư duy Zero Trust: xác minh theo từng yêu cầu truy cập

**Zero Trust** là cách thiết kế trong đó không cấp quyền mặc định chỉ vì một kết nối ở trong LAN, ở cùng data center hoặc đã vào VPN. Mỗi yêu cầu truy cập phải được đánh giá dựa trên danh tính, tài nguyên, hành động và tín hiệu ngữ cảnh phù hợp.

Một số nguyên tắc thực hành:

1. **Xác minh rõ chủ thể:** người dùng bằng cơ chế đăng nhập thích hợp; thiết bị bằng cơ chế quản lý hoặc chứng chỉ; dịch vụ bằng danh tính máy/dịch vụ.
2. **Cấp ít quyền nhất:** chỉ cho phép những phương thức, cổng, dịch vụ và dữ liệu cần thiết; mặc định từ chối những đường chưa được phê duyệt.
3. **Giảm vùng có thể bị ảnh hưởng:** chia mạng và giới hạn luồng east–west, tách rõ hệ thống quản trị, người dùng, ứng dụng và dữ liệu.
4. **Đánh giá theo ngữ cảnh:** khi cần, kết hợp MFA, trạng thái thiết bị, loại tài nguyên, rủi ro phiên và chính sách truy cập.
5. **Theo dõi và điều chỉnh:** lưu nhật ký để phát hiện bất thường, thu hồi phiên/quyền và cô lập thiết bị khi xuất hiện tín hiệu rủi ro.

Không nên hiểu Zero Trust là yêu cầu một sản phẩm đơn lẻ hay phải xác thực thủ công mỗi gói tin. Kiểm tra có thể diễn ra khi thiết lập kết nối, cấp phiên/token, gửi yêu cầu API hoặc truy cập một đối tượng nghiệp vụ; vị trí và tần suất kiểm tra phụ thuộc hệ thống.

**Phân biệt quan trọng:** xác thực một thiết bị được vào mạng bằng 802.1X, xác thực người dùng bằng MFA, xác thực dịch vụ bằng mTLS và ủy quyền một yêu cầu API là **những quyết định khác nhau**. Thực hiện một bước không tự động thay thế được các bước còn lại.

## 5. Thiết kế các vùng và luồng được phép

Giả sử doanh nghiệp có nhân viên, khách, ứng dụng xử lý đơn hàng và CSDL. Có thể phân chia các vùng với những đường truy cập xác định:

~~~mermaid
flowchart LR
    E["Laptop nhân viên"] --> N["Kiểm soát truy cập mạng<br/>802.1X / NAC"]
    N --> U["Vùng người dùng"]
    G["Thiết bị khách"] --> W["Wi-Fi khách cách ly"]
    W --> I["Internet"]
    U --> P["Gateway / Reverse proxy"]
    P --> A["Vùng ứng dụng<br/>API đơn hàng"]
    A --> D["Vùng dữ liệu<br/>CSDL"]
    M["Quản trị viên"] --> B["Bastion / Cổng quản trị<br/>MFA và ghi vết"]
    B --> D
    A --> O["Giám sát tập trung"]
    P --> O
    D --> O
~~~

Sơ đồ chỉ mô tả **luồng mong muốn**, không có nghĩa mọi kết nối trên mũi tên đều tự được cấp quyền. Cần firewall/network policy cho đường mạng, TLS cho bảo vệ truyền dẫn và xác thực/ủy quyền ở đầu nhận.

Một bảng chính sách mẫu:

| Nguồn | Đích | Luồng được phép | Điều kiện bổ sung |
| --- | --- | --- | --- |
| Wi-Fi khách | Hệ thống nội bộ | Không cho phép | Khách chỉ ra Internet qua chính sách phù hợp |
| Laptop nhân viên | Gateway ứng dụng | HTTPS đến điểm công bố | Người dùng đăng nhập; ứng dụng kiểm tra quyền |
| Laptop nhân viên | CSDL | Từ chối trực tiếp | Không dùng subnet nội bộ làm vé thông hành |
| API đơn hàng | CSDL đơn hàng | TCP tới cổng CSDL cần thiết | Tài khoản CSDL riêng, TLS, quyền truy vấn tối thiểu |
| API đơn hàng | Dịch vụ không liên quan | Mặc định từ chối | Mở theo nhu cầu được xác minh |
| Máy quản trị qua bastion | Giao diện quản trị | Chỉ phiên được cấp phép | MFA, quyền theo vai trò, nhật ký phiên |

Trong mạng thực tế, các quy tắc này có thể triển khai bằng firewall giữa các VLAN/VRF, ACL trên thiết bị mạng, security group/NSG trên đám mây, network policy trong môi trường container và lớp ủy quyền ứng dụng. Cấu hình ở một lớp **không mặc nhiên áp dụng** sang các lớp khác.

### Ví dụ quy tắc ở mức ý tưởng

~~~text
DENY   guest_network  -> internal_network   ANY
ALLOW  employee_zone  -> app_gateway        TCP/443
DENY   employee_zone  -> database_zone      ANY
ALLOW  order_api      -> orders_database    TCP/5432
DENY   application_zone -> database_zone    ANY khác
~~~

Đây là mô hình chính sách để phân tích, **không phải cú pháp cấu hình dùng trực tiếp** cho một hãng firewall. Khi hiện thực, cần kiểm tra thứ tự quy tắc, chiều kết nối, tính stateful, NAT, địa chỉ thực tế, ngoại lệ DNS/giám sát và chính sách mặc định. Chỉ dựa vào IP nguồn của dịch vụ vẫn chưa đủ: CSDL còn phải xác thực ứng dụng và giới hạn quyền truy vấn.

## 6. Các lớp kiểm soát bổ trợ

### 6.1. Phân đoạn và firewall

- **VLAN** chia miền quảng bá ở lớp 2, hỗ trợ cô lập tương đối theo nhóm thiết bị; để ngăn liên vùng cần chính sách định tuyến/firewall/ACL.
- **VRF** chia bảng định tuyến; phù hợp khi cần tách không gian định tuyến của các khu vực hoặc đơn vị.
- **Firewall nội bộ** kiểm soát luồng giữa các subnet/vùng, giúp hạn chế dò quét và di chuyển ngang.
- **Microsegmentation** đưa chính sách đến gần từng workload hoặc dịch vụ, có thể dùng danh tính/nhãn workload thay vì chỉ một dải IP rộng.
- **Deny-by-default** là quy tắc thiết kế: xác định rõ các luồng hợp lệ rồi chỉ mở những luồng đó; bảo đảm có phương án vận hành và khôi phục khi chính sách chặn nhầm.

Phân đoạn phải phản ánh **luồng dữ liệu và nhu cầu truy cập**; chỉ chia nhiều subnet mà vẫn cho phép tất cả đi qua lại thì không đạt mục tiêu bảo vệ.

### 6.2. Xác thực thiết bị, kết nối và dịch vụ

- **802.1X** kết hợp cơ chế xác thực như EAP-TLS và hệ thống AAA/RADIUS để kiểm soát thiết bị được tham gia mạng có dây hoặc Wi-Fi. Kiểm soát này là cửa vào mạng, không thay thế phân quyền API.
- **NAC (Network Access Control)** có thể áp chính sách cho thiết bị được quản lý, khách hoặc thiết bị không đạt yêu cầu; thường cần vùng cách ly và quy trình xử lý ngoại lệ.
- **VPN** mã hóa và cung cấp đường kết nối từ xa, nhưng việc kết nối VPN thành công không có nghĩa người dùng được quyền tới mọi subnet. Hạn chế tuyến, đích và quyền theo nhu cầu.
- **TLS** bảo vệ tính bí mật/toàn vẹn của kết nối và xác thực máy chủ khi chứng chỉ được kiểm tra đúng.
- **mTLS** yêu cầu hai bên xuất trình/xác minh chứng chỉ, hữu ích cho nhận diện dịch vụ với dịch vụ. Chứng chỉ hợp lệ vẫn cần được ánh xạ tới quyền truy cập cụ thể.

### 6.3. Ủy quyền tại ứng dụng và dữ liệu

Giả sử một API chỉ lắng nghe trên địa chỉ private và firewall chỉ mở từ gateway. API vẫn phải xác minh token/phiên, kiểm tra chữ ký, thời hạn, bên phát hành, đối tượng nhận token khi phù hợp, rồi kiểm tra quyền với hành động và đối tượng được yêu cầu.

Ví dụ, quyền đọc đơn hàng không nên suy ra từ điều kiện “đến từ subnet văn phòng”. Người dùng phải có quyền đọc và còn cần được kiểm tra phạm vi đơn hàng của chính họ hoặc của tổ chức mà họ phụ trách.

Ở tầng dữ liệu, dùng tài khoản riêng cho mỗi ứng dụng, giới hạn quyền theo nhu cầu (ví dụ tài khoản chỉ đọc không được tự ý sửa bảng), bảo vệ thông tin xác thực và ghi nhật ký các thao tác quan trọng.

### 6.4. DNS, Wi-Fi và hạ tầng đám mây

- **DNS:** cung cấp resolver do tổ chức quản lý, giới hạn đường truy vấn cần thiết, theo dõi những tên miền bất thường và bảo vệ khả năng phân giải; DNSSEC giúp xác thực dữ liệu DNS được ký nhưng không thay thế TLS hay đánh giá an toàn của trang web.
- **Wi-Fi:** dùng bảo mật hiện đại phù hợp, ưu tiên WPA2/WPA3-Enterprise và xác thực 802.1X trong môi trường doanh nghiệp; tách mạng khách, hạn chế truy cập giữa khách với khách nếu cần.
- **Đám mây:** mạng private trong VPC/VNet cũng có thể bị lạm dụng; đánh giá security group/NSG, route table, điểm truy cập quản trị, kết nối giữa tài khoản/dự án và quyền của workload.
- **Container/Kubernetes:** kiểm tra khả năng thực thi NetworkPolicy của giải pháp mạng (CNI); phân biệt chính sách ingress và egress, đồng thời không suy ra rằng mọi pod cùng namespace đều đáng tin.

### 6.5. Giám sát và phát hiện xâm nhập

**IDS** tìm dấu hiệu tấn công và phát cảnh báo; **IPS** có thể chặn lưu lượng phù hợp với quy tắc và vị trí triển khai. Ngoài IDS/IPS, nên kết hợp nhật ký firewall, VPN, DNS, xác thực, gateway, endpoint và ứng dụng.

Các tín hiệu đáng chú ý gồm một máy trạm đột ngột thử kết nối nhiều cổng nội bộ, một dịch vụ gọi các đích chưa từng dùng, số lần đăng nhập thất bại tăng mạnh, truy vấn DNS bất thường hoặc một danh tính dịch vụ xuất hiện từ vị trí không hợp lệ.

Khi điều tra, cần tương quan **thời điểm, IP, thiết bị, người dùng và danh tính dịch vụ**. IP có thể đổi vì DHCP/NAT và nhiều thiết bị có thể dùng chung một IP công cộng; log chỉ có IP thường không đủ kết luận chủ thể.

## 7. Tình huống thực hành: máy nhân viên bị xâm nhập

**Bối cảnh:** công ty có VLAN nhân viên, VLAN ứng dụng, VLAN CSDL và Wi-Fi khách. Một laptop nhân viên đã bị nhiễm mã độc; kẻ tấn công thử kết nối trực tiếp tới CSDL và trang quản trị.

**Nếu mạng phẳng:** laptop có thể nhìn thấy nhiều máy chủ, quét các cổng đang mở, khai thác dịch vụ yếu hoặc thử thông tin xác thực đánh cắp. Một firewall chỉ chặn kết nối từ Internet không giải quyết được luồng này.

**Nếu có phòng vệ theo lớp:**

1. NAC và hệ thống quản lý thiết bị có thể phát hiện máy không đạt yêu cầu và đưa vào vùng hạn chế (khả năng phát hiện phụ thuộc tín hiệu thực tế).
2. Firewall nội bộ từ chối laptop đi trực tiếp đến CSDL; chỉ gateway được phép công bố dịch vụ cần thiết.
3. Gateway và API yêu cầu xác thực, kiểm tra quyền của từng hành động và đối tượng dữ liệu.
4. CSDL chỉ nhận kết nối từ ứng dụng được phép, dùng xác thực riêng và quyền tối thiểu.
5. Nhật ký kết nối bị từ chối, EDR và dấu hiệu dò quét giúp nhóm vận hành phát hiện, cô lập thiết bị và thu hồi phiên/token.

Hệ thống vẫn có rủi ro: một yêu cầu độc hại có thể đi qua đường hợp lệ nếu tài khoản hợp lệ bị chiếm hoặc ứng dụng có lỗ hổng. Vì vậy kiểm soát mạng cần đi kèm quản lý lỗ hổng, bảo mật ứng dụng, bảo vệ thiết bị đầu cuối và ứng cứu sự cố.

### Mô hình hóa mối đe dọa cho trường hợp này

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Tài sản cần bảo vệ | Dữ liệu khách hàng, đơn hàng, quyền quản trị, thông tin xác thực |
| Điểm vào khả dĩ | Laptop nhân viên, VPN, Wi-Fi, dịch vụ web, workload bị chiếm |
| Ranh giới tin cậy | Giữa máy người dùng và gateway; ứng dụng và CSDL; mạng thường và mạng quản trị |
| Đường tấn công | Dò mạng → truy cập dịch vụ → dùng sai quyền → đọc/sửa dữ liệu |
| Kiểm soát phòng ngừa | Phân đoạn, xác thực, ủy quyền, TLS, quyền tối thiểu |
| Kiểm soát phát hiện | Log kết nối, log truy cập dữ liệu, sự kiện xác thực, IDS/EDR |
| Phản ứng cần có | Cô lập máy, vô hiệu hóa phiên, xoay vòng bí mật bị lộ, điều tra phạm vi |

Không cần giả định mọi đường tấn công đều thành công. Mục tiêu mô hình hóa là liệt kê **đường đi khả dĩ, điều kiện để đi tiếp và lớp kiểm soát cắt đường đó**.

## 8. Cách kiểm chứng một kiến trúc mạng không tin cậy mặc định

Khi đã có sơ đồ mạng, bảng luồng và quyền truy cập, nhóm vận hành có thể kiểm thử trong môi trường được cho phép:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Thiết bị Wi-Fi khách truy cập địa chỉ private của CSDL | Không thiết lập được kết nối |
| Laptop nhân viên truy cập trực tiếp cổng CSDL | Bị chặn, có tín hiệu kiểm toán phù hợp |
| Laptop nhân viên truy cập gateway ứng dụng | Đến được điểm phục vụ HTTPS, nhưng chỉ thao tác được sau khi được xác thực/ủy quyền |
| API đơn hàng truy cập CSDL qua cổng được quy định | Hoạt động với danh tính và quyền CSDL được cấp |
| API đơn hàng thử tới một CSDL không liên quan | Bị chặn theo chính sách |
| Token không hợp lệ hoặc thiếu quyền gọi API | Bị từ chối dù kết nối xuất phát từ mạng nội bộ |
| Tài khoản đã bị thu hồi thử tiếp tục truy cập | Phiên/token được xử lý theo cơ chế thu hồi và thời hạn đã thiết kế |
| Giả lập một nguồn kết nối nội bộ bất thường | Có dấu vết đủ để xác định nguồn, thời điểm, đích và hành động xử lý |

Kết quả kiểm thử cần dựa trên cả **hành vi thực tế** lẫn log cấu hình; việc chỉ đọc một bộ quy tắc firewall chưa chứng minh được rằng không tồn tại đường đi vòng qua VPN, proxy, route khác hoặc cấu hình đám mây.

Một số câu hỏi nên đặt khi rà soát:

1. Nếu mất quyền kiểm soát một laptop hoặc một container, kẻ tấn công còn có thể kết nối tới những đích nào?
2. Có dịch vụ nào cho phép truy cập chỉ vì IP nguồn thuộc dải private?
3. Khi người dùng vào VPN, họ có thấy nhiều hệ thống hơn công việc cần thiết không?
4. Có tách Wi-Fi khách, thiết bị IoT, mạng quản trị, ứng dụng và dữ liệu theo rủi ro không?
5. Nếu một chứng chỉ/token/tài khoản dịch vụ bị lộ, quyền đó có bị giới hạn và thu hồi được không?
6. Log có giúp nối một kết nối tới đúng danh tính và tài nguyên tại thời điểm xảy ra sự kiện không?

## 9. Những hiểu lầm thường gặp

**“Địa chỉ 10.x.x.x hoặc 192.168.x.x là an toàn.”** Đó là các dải IP dùng trong mạng riêng, không phải bằng chứng về danh tính hoặc mức độ tin cậy.

**“Đã dùng VPN thì không cần kiểm tra quyền.”** VPN tạo đường truyền bảo vệ tới phạm vi được cấu hình. Quyền sử dụng ứng dụng và dữ liệu vẫn phải được kiểm tra.

**“Có VLAN là đã ngăn được di chuyển ngang.”** VLAN không tự ngăn được lưu lượng được định tuyến giữa các VLAN. Cần chính sách cụ thể và kiểm chứng đường đi.

**“Có mTLS thì mọi API call đều hợp lệ.”** mTLS nhận diện hai đầu kết nối khi thiết lập đúng; API vẫn phải quyết định chủ thể có được truy cập tài nguyên hoặc thực hiện hành động cụ thể không.

**“Chỉ cần chặn ở firewall biên.”** Kết nối giữa các dịch vụ nội bộ cũng phải có kiểm soát, nhất là sau khi một thiết bị hoặc dịch vụ bị xâm nhập.

**“Zero Trust nghĩa là không tin bất cứ thứ gì trong mọi thời điểm.”** Thực tế, hệ thống đưa ra các quyết định tin cậy **có điều kiện, có giới hạn và có thể xem xét lại**, thay cho việc cấp quyền rộng theo vị trí mạng.

## 10. Tự kiểm tra kiến thức

1. Một API chỉ cho phép IP thuộc mạng văn phòng gọi vào. Hãy chỉ ra ít nhất ba tình huống khiến biện pháp này không đủ và đề xuất lớp kiểm soát bổ sung.
2. Sự khác biệt giữa 802.1X, VPN, TLS/mTLS và ủy quyền ở ứng dụng là gì? Mỗi cơ chế giải quyết câu hỏi nào?
3. Công ty đã tách CSDL sang VLAN riêng nhưng laptop nhân viên vẫn truy cập trực tiếp cổng CSDL. Điều này cho biết gì về chính sách liên vùng?
4. Trong tình huống một pod ứng dụng bị chiếm, bạn cần kiểm tra những luồng east–west, danh tính dịch vụ và nhật ký nào?
5. Vì sao một cảnh báo chỉ chứa IP nguồn mà không có thời gian, thiết bị hoặc danh tính liên quan có thể khó điều tra?

**Gợi ý đánh giá:** câu trả lời tốt phải xác định được tài sản, đường kết nối, chủ thể, quyền tối thiểu, nơi thực thi chính sách và cách xác nhận biện pháp thực sự có hiệu lực.

## Kết luận

Mạng nội bộ là một **vùng kết nối**, không phải một chứng nhận an toàn. Kiến trúc mạng vững chắc không dựa vào giả định “đã ở trong là đáng tin”, mà dựa vào xác minh danh tính, cấp quyền phù hợp, phân đoạn luồng truy cập, bảo vệ truyền dẫn và quan sát liên tục. Khi áp dụng đồng thời các lớp này, một sự cố ở laptop, Wi-Fi, VPN hoặc dịch vụ nội bộ sẽ khó lan sang toàn bộ hệ thống hơn.
