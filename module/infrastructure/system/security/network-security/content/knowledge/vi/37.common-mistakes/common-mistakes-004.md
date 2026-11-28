# Sai lầm thường gặp: Đặt rule quá rộng theo địa chỉ IP

## 1. Vấn đề: một rule đơn giản có thể mở quá nhiều đường đi

Trong vận hành mạng an toàn, firewall, ACL (Access Control List), security group, network policy và gateway được dùng để giới hạn lưu lượng theo nguồn, đích, cổng, giao thức và các điều kiện liên quan. Một sai lầm phổ biến là **đặt phạm vi địa chỉ IP rộng hơn nhu cầu thực tế**, ví dụ cho phép toàn bộ Internet, toàn bộ mạng nội bộ hoặc cả một subnet lớn truy cập vào tài nguyên vốn chỉ cần kết nối với vài máy cụ thể.

Ví dụ, đội ứng dụng cần máy **10.44.20.15** truy cập cơ sở dữ liệu **10.44.30.25** bằng TCP/5432. Một rule như sau có thể giúp kết nối chạy ngay:

~~~text
ALLOW  source=10.0.0.0/8  destination=10.44.30.0/24  protocol=ANY  port=ANY
~~~

Nhưng rule này cho phép nhiều nguồn trong dải **10.0.0.0/8** chạm đến nhiều địa chỉ thuộc **10.44.30.0/24**, qua các giao thức/cổng mà công việc không yêu cầu. Nếu một máy khác trong mạng bị chiếm quyền, kẻ tấn công có thể tận dụng đường đi đó để thăm dò, truy cập trái phép hoặc di chuyển ngang (lateral movement).

Một rule phù hợp hơn với nhu cầu nêu trên là:

~~~text
ALLOW  source=10.44.20.15/32  destination=10.44.30.25/32  protocol=TCP  port=5432
~~~

Đây là **ví dụ cú pháp trung lập nhà cung cấp**, không phải lệnh của một firewall cụ thể. Các ví dụ phía dưới dùng địa chỉ mạng riêng để minh họa, cần thay bằng địa chỉ và chính sách được xác minh tại hệ thống thực tế.

Trong module **SECURITY_NETWORK_SECURITY**, vấn đề này gắn trực tiếp với phân đoạn mạng, firewall, VPN, IDS/IPS, bảo vệ DNS, mạng không dây, môi trường đám mây, phân tích lưu lượng và mô hình hóa mối đe dọa. Firewall rule quá rộng có thể làm suy yếu các lớp phòng vệ còn lại dù chúng vẫn đang hoạt động bình thường.

**Mục tiêu bài học:** nhận diện rule IP quá rộng, đánh giá tác động, thiết kế rule theo đặc quyền tối thiểu, kiểm thử trước khi thay đổi và duy trì khả năng kiểm toán trong vận hành.

## 2. “Quá rộng” nghĩa là gì?

Một rule mạng thường được mô tả bằng các chiều sau:

| Chiều kiểm soát | Câu hỏi cần trả lời | Biểu hiện quá rộng |
| --- | --- | --- |
| **Nguồn** (source) | Ai/máy/vùng mạng nào khởi tạo kết nối? | Cho phép mọi nguồn hoặc cả mạng tổ chức |
| **Đích** (destination) | Tài nguyên nào cần nhận kết nối? | Cho phép cả subnet dù chỉ cần một dịch vụ |
| **Giao thức** | TCP, UDP, ICMP hay giao thức khác? | Cho phép mọi giao thức để xử lý một lỗi TCP |
| **Cổng/dịch vụ** | Ứng dụng cần cổng nào? | Cho phép mọi cổng, cả dịch vụ quản trị |
| **Chiều lưu lượng** | Luồng đi từ vùng nào sang vùng nào? | Mở hai chiều hoặc nhiều vùng hơn cần thiết |
| **Thời gian** | Cần vĩnh viễn hay trong cửa sổ thay đổi? | Ngoại lệ tạm trở thành quyền thường trực |
| **Đối tượng danh tính** | Người, workload, máy có được xác thực không? | Giả định cùng IP là cùng một người/dịch vụ |
| **Môi trường** | Production, staging, tenant nào? | Quy tắc áp dụng chung cả môi trường nhạy cảm |

**Độ rộng phải được đánh giá theo nhu cầu nghiệp vụ, không chỉ nhìn vào kích thước CIDR.** Chẳng hạn, cho phép cả subnet của một cụm ứng dụng đã được kiểm soát có thể là yêu cầu hợp lệ. Ngược lại, mở duy nhất một IP quản trị ra Internet vẫn nguy hiểm nếu sai dịch vụ hoặc sai vị trí kiểm soát.

### Hiểu CIDR trước khi cấp quyền

CIDR sử dụng số bit tiền tố để mô tả tập địa chỉ. Với IPv4, **tiền tố càng ngắn thì tập địa chỉ càng lớn**:

| CIDR | Số địa chỉ IPv4 trong tập | Diễn giải |
| --- | ---: | --- |
| **/32** | 1 | Một địa chỉ cụ thể |
| **/30** | 4 | Một dải bốn địa chỉ |
| **/24** | 256 | Ví dụ một mạng lớp nhỏ |
| **/16** | 65.536 | Tập địa chỉ lớn, thường bao phủ nhiều phân đoạn |
| **/8** | 16.777.216 | Tập địa chỉ rất lớn |
| **0.0.0.0/0** | 4.294.967.296 | Toàn bộ không gian IPv4 |

Đây là **số địa chỉ nằm trong dải**, không phải số thiết bị có thể truy cập thực tế. Khả năng truy cập còn phụ thuộc định tuyến, vùng mạng, NAT, lớp chính sách khác và tình trạng thiết bị. Tuy nhiên, sự mở rộng tập địa chỉ vẫn giúp nhận diện rủi ro tiềm ẩn.

IPv6 cũng có các phạm vi rất rộng: **::/0** là toàn bộ không gian IPv6; **/128** là một địa chỉ IPv6 duy nhất. Không thể kết luận IPv6 an toàn chỉ vì firewall IPv4 đã được cấu hình chặt; cần xem xét chính sách cho cả hai họ địa chỉ.

## 3. Các kiểu sai lầm thường gặp

### 3.1. Mở nguồn là toàn bộ Internet

~~~text
ALLOW  source=0.0.0.0/0  destination=10.44.40.10/32  protocol=TCP  port=22
~~~

Quy tắc này mở đường SSH từ mọi địa chỉ IPv4 có thể định tuyến tới điểm thực thi rule. Nếu đích còn được công bố ra Internet, nó tạo bề mặt tấn công lớn: dò quét cổng, thử đăng nhập, khai thác lỗi dịch vụ hoặc lạm dụng thông tin xác thực bị lộ.

**Cách sửa:** yêu cầu quản trị qua VPN/ZTNA có MFA, bastion/PAM, tập nguồn được kiểm soát hoặc một kết hợp các biện pháp phù hợp. Không coi việc giới hạn IP đơn thuần là cơ chế xác thực người dùng. Đôi khi dịch vụ HTTPS công khai cần **0.0.0.0/0** ở cổng 443; khi đó phạm vi rộng là quyết định chủ ý, thường đặt tại reverse proxy/WAF và phải được bảo vệ ở lớp ứng dụng.

### 3.2. Mở cả dải nội bộ vì cho rằng “mạng bên trong đáng tin”

~~~text
ALLOW  source=10.0.0.0/8  destination=10.44.30.25/32  protocol=TCP  port=5432
~~~

Mạng nội bộ có thể chứa thiết bị khách, máy người dùng, workload ở môi trường thử nghiệm, hạ tầng chi nhánh và hệ thống đã bị chiếm quyền. Địa chỉ RFC 1918 không tự chứng minh máy là đáng tin cậy. Rule trên có thể biến database thành điểm đến dễ tiếp cận khi xảy ra sự cố tại một vùng khác.

**Cách sửa:** lập danh sách thực tế các workload cần truy cập database; giới hạn theo subnet ứng dụng được quản trị, IP cụ thể hoặc danh tính workload nếu nền tảng hỗ trợ. Giữ chính sách chặn giữa các vùng (inter-zone) làm nền tảng và thêm các luồng cho phép rõ ràng.

### 3.3. Mở cả subnet đích để “phòng trường hợp đổi IP”

~~~text
ALLOW  source=10.44.20.15/32  destination=10.44.30.0/24  protocol=TCP  port=5432
~~~

Nếu chỉ một database đang cần kết nối, toàn bộ subnet đích là phạm vi quá rộng. Về sau subnet có thể nhận thêm máy chứa dữ liệu nhạy cảm; rule cũ vẫn tự động cho phép nguồn ban đầu kết nối tới các máy đó trên TCP/5432.

**Cách sửa:** ràng buộc theo đích chính xác hoặc theo **nhóm dịch vụ có kiểm soát**. Đối với IP động hoặc cụm HA, nên dùng service discovery/nhóm địa chỉ được quản trị, security group tham chiếu lẫn nhau hoặc selector theo nhãn nếu nền tảng hỗ trợ, thay vì chọn một CIDR lớn tùy tiện.

### 3.4. Mở tất cả cổng để “đỡ phải xin rule sau”

~~~text
ALLOW  source=10.44.20.0/24  destination=10.44.30.0/24  protocol=ANY  port=ANY
~~~

Giới hạn IP chưa đủ khi mọi cổng đều thông. Nếu máy đích mở thêm giao diện quản trị, cơ sở dữ liệu khác hoặc dịch vụ phát sinh, rule sẽ cho phép truy cập mà không cần thay đổi chính sách.

**Cách sửa:** khai báo giao thức/cổng theo giao tiếp thực tế; nếu cần nhiều cổng, lập danh sách có giải thích riêng. Không mở tất cả cổng chỉ vì việc chẩn đoán chưa tìm ra lỗi.

### 3.5. Mở hai chiều dù ứng dụng chỉ khởi tạo một chiều

Một ứng dụng ở vùng A khởi tạo TCP tới vùng B không đồng nghĩa B cần được phép **chủ động khởi tạo** mọi kết nối tới A. Với firewall **stateful**, lưu lượng trả lời thuộc kết nối hợp lệ thường được theo dõi trạng thái; không cần một rule inbound quá rộng chỉ để “mở đường về”. Còn ACL **stateless** phải được thiết kế rõ cho chiều phản hồi, có thể cần dải cổng tạm (ephemeral ports) theo yêu cầu từng nền tảng.

**Cách sửa:** nắm rõ loại điểm kiểm soát, chiều khởi tạo kết nối và hành vi theo dõi phiên; kiểm tra đủ hai chiều trước khi mở rộng rule.

### 3.6. Dùng địa chỉ IP như một danh tính người dùng

Một IP có thể đại diện nhiều người sau NAT, một egress gateway, VPN tập trung, proxy hay thiết bị dùng chung. Ngược lại, một người hoặc workload có thể đổi IP do DHCP, autoscaling, di chuyển pod/VM hoặc roaming Wi-Fi.

**Cách sửa:** với người dùng, ràng buộc tại lớp IAM, ZTNA, VPN, MFA, PAM. Với workload, cân nhắc danh tính dịch vụ, mTLS hoặc chính sách theo workload nếu công nghệ cho phép. IP vẫn hữu ích để kiểm soát đường đi, nhưng là **một tín hiệu và điều kiện mạng**, không phải bằng chứng danh tính đầy đủ.

## 4. Vì sao rule rộng làm tăng rủi ro?

Mô hình đe dọa đơn giản:

~~~mermaid
flowchart LR
    A["Máy trạm bị xâm nhập"] --> B["Vùng nội bộ"]
    B --> C{"Rule firewall"}
    C -- "Allow 10.0.0.0/8 tới DB" --> D["Mạng cơ sở dữ liệu"]
    C -- "Chỉ allow app-service tới DB:5432" --> E["Chặn luồng ngoài phạm vi"]
    D --> F["Thăm dò / di chuyển ngang / truy cập trái phép"]
~~~

Khi rule bao phủ nhiều địa chỉ hơn nhu cầu, rủi ro tăng theo nhiều cách:

1. **Gia tăng bề mặt tiếp xúc:** nhiều nguồn hơn có thể gửi lưu lượng tới dịch vụ nhạy cảm.
2. **Tạo đường di chuyển ngang:** sự cố ở vùng ít tin cậy có thể lan tới vùng dữ liệu hoặc điều khiển.
3. **Phá vỡ phân đoạn:** sơ đồ VLAN/subnet có vẻ tách biệt nhưng allow rule quá rộng tạo đường vượt phân đoạn.
4. **Khiến thay đổi về sau trở nên nguy hiểm:** máy mới được thêm vào CIDR đã được cho phép có thể nhận quyền truy cập ngoài ý muốn.
5. **Làm khó phát hiện bất thường:** lưu lượng ngoài nhu cầu vẫn được firewall chấp nhận, giảm giá trị của tín hiệu chặn và tạo nhiễu cho giám sát.
6. **Tăng phạm vi ảnh hưởng khi lộ credential:** tài khoản hoặc thiết bị bị xâm nhập có thể đi xa hơn mức yêu cầu của vai trò ban đầu.

Không phải mọi rule rộng đều dẫn tới khai thác thành công. Phân tích đầy đủ còn xem dịch vụ thực sự lắng nghe ở đâu, có route/NAT hay không, xác thực ở lớp ứng dụng, IDS/IPS, chính sách máy chủ, trạng thái phiên và các luật phủ định. Tuy vậy, **quyền mạng thừa vẫn là một rủi ro cần giảm**.

## 5. Tình huống thiết kế: ứng dụng kết nối cơ sở dữ liệu

Giả sử một hệ thống có các vùng sau:

| Thành phần | IP minh họa | Vai trò |
| --- | --- | --- |
| Reverse proxy DMZ | **10.44.10.20/32** | Nhận HTTPS và chuyển tiếp đến ứng dụng |
| Ứng dụng | **10.44.20.15/32** | Xử lý nghiệp vụ |
| PostgreSQL | **10.44.30.25/32** | Lưu trữ dữ liệu |
| Bastion quản trị | **10.44.40.10/32** | Điểm trung gian cho phiên quản trị |

Luồng được duyệt là: reverse proxy kết nối ứng dụng qua TCP/8443, và ứng dụng kết nối database qua TCP/5432. Người quản trị có quyền riêng qua bastion; quản trị không được đi thẳng từ mọi máy trạm tới database.

### Trước khi sửa: một rule cho cả mạng

~~~text
ID: DB-ANY-LEGACY
action: ALLOW
source: 10.0.0.0/8
destination: 10.44.30.0/24
protocol: ANY
destination_port: ANY
description: "Cho app va ho tro ky thuat"
expires_at: none
~~~

Rule này không phân biệt ứng dụng với máy người dùng, không giới hạn database cụ thể và không giới hạn giao thức. Dòng mô tả “hỗ trợ kỹ thuật” cũng không thay thế cho tài liệu lý do, phê duyệt và chủ sở hữu.

### Sau khi sửa: mô tả rõ các luồng cần thiết

~~~yaml
# Pseudo-policy minh hoa; khong phai cu phap firewall san xuat.
policySet: production-segmentation
defaultInterZoneAction: deny
rules:
  - id: dmz-proxy-to-app
    action: allow
    source: 10.44.10.20/32
    destination: 10.44.20.15/32
    protocol: tcp
    destinationPorts: [8443]
    owner: application-team
    purpose: "Reverse proxy goi ung dung"

  - id: app-to-postgres
    action: allow
    source: 10.44.20.15/32
    destination: 10.44.30.25/32
    protocol: tcp
    destinationPorts: [5432]
    owner: database-team
    purpose: "Ung dung truy cap PostgreSQL"

  - id: bastion-to-postgres-admin
    action: allow
    source: 10.44.40.10/32
    destination: 10.44.30.25/32
    protocol: tcp
    destinationPorts: [22]
    owner: platform-security
    purpose: "Quan tri he dieu hanh qua bastion"
~~~

Ví dụ trên **giả định** máy database có SSH và đội vận hành đã phê duyệt đường quản trị này. Trong thực tế, nếu không cần SSH tới database, không tạo rule cuối. Quyền truy cập dịch vụ PostgreSQL và quyền đăng nhập hệ điều hành là hai loại quyền khác nhau; giới hạn mạng phải đi kèm xác thực tại đích và ghi nhật ký.

Một chính sách **default deny** ở ranh giới vùng có ý nghĩa khi đã kiểm kê đủ các luồng hợp lệ. Tránh bật chặn đột ngột làm hỏng DNS, giám sát, sao lưu, đồng bộ dữ liệu hoặc hoạt động HA mà chưa rà soát các phụ thuộc.

### Lưu ý cho cụm động, dịch vụ cloud và container

Việc khóa đúng một IP /32 dễ hiểu nhưng không phải lúc nào cũng bền vững. IP của pod, VM tự mở rộng hay node thay thế có thể đổi. Khi đó nên sử dụng một trong các cơ chế có quản trị vòng đời:

- **Cloud security group:** tham chiếu nhóm nguồn/đích hoặc tài nguyên thay vì CIDR lớn, nếu nền tảng hỗ trợ. Kiểm soát quyền sửa nhóm và membership vì đây là nơi quyết định ai thực sự được truy cập.
- **Kubernetes NetworkPolicy:** giới hạn theo namespace/pod selectors và cổng; cần kiểm tra CNI có thực thi NetworkPolicy. Selector quá rộng như chọn mọi pod cũng có thể tạo ra lỗi tương tự CIDR rộng.
- **Firewall doanh nghiệp:** sử dụng object/address group được quản lý, cập nhật từ inventory/CMDB hoặc automation có kiểm soát.
- **Service mesh hoặc ZTNA:** gắn luồng với danh tính workload hay người dùng, dùng mã hóa/xác thực khi phù hợp; vẫn giữ chặn mạng ở nơi có thể.

Mục tiêu không phải luôn luôn dùng /32; mục tiêu là **chỉ bao phủ đúng tập nguồn và đích có trách nhiệm nghiệp vụ, ngay cả khi thành viên của tập thay đổi**.

## 6. Quy trình phát hiện và thu hẹp rule quá rộng

### Bước 1 — Xác định rule có hiệu lực thực tế

Thu thập policy từ các điểm cưỡng chế liên quan (firewall ở biên và giữa vùng, security group, NACL, host firewall, ZTNA, thiết bị VPN). Đừng chỉ đọc một dòng cấu hình mà bỏ qua:

- Thứ tự ưu tiên, policy đầu tiên khớp hoặc logic ưu tiên theo sản phẩm.
- Rule cho phép khác nằm trước rule vừa sửa, rule bị che khuất (**shadowed**) hoặc đối tượng nhóm có thành viên rộng.
- NAT trước/sau firewall, định tuyến, IP công khai chuyển tiếp về IP riêng.
- Khác biệt giữa inbound/ingress và outbound/egress, giữa IPv4 và IPv6.
- Trạng thái các phiên đã thiết lập khi thay đổi rule.

Một allow rule được “siết” nhưng vẫn còn allow khác rộng hơn có thể **không thay đổi** khả năng truy cập thực tế. Cần đánh giá **effective policy**, tức kết quả cuối cùng sau khi áp dụng tất cả luật liên quan.

### Bước 2 — Kiểm kê luồng cần thiết bằng bằng chứng

Kết hợp sơ đồ kiến trúc, chủ sở hữu dịch vụ, log firewall, flow logs, lưu lượng mạng, telemetry ứng dụng và thay đổi cấu hình. Với dịch vụ nhạy cảm, có thể phân tích PCAP hoặc NetFlow/IPFIX trong phạm vi được cho phép để biết nguồn nào thực sự kết nối, đến đích/cổng nào và vào thời điểm nào.

Phân biệt rõ:

- **Luồng bắt buộc:** cần cho nghiệp vụ bình thường; chủ hệ thống xác nhận.
- **Luồng quản trị/bảo trì:** có thể đi qua bastion/PAM và chỉ hoạt động theo cửa sổ thời gian.
- **Luồng chưa biết:** không tự động coi là hợp lệ chỉ vì từng xuất hiện trong log.
- **Luồng nghi vấn:** cần xác minh với vận hành an ninh trước khi giữ quyền.

Log gần đây có thể bỏ sót các tác vụ chạy hàng tuần/hàng tháng, failover, backup định kỳ hoặc giao dịch ít xuất hiện. Vì vậy cần đối chiếu tài liệu và lịch vận hành, không quyết định chỉ dựa trên một đoạn quan sát ngắn.

### Bước 3 — Viết lại policy theo phạm vi tối thiểu

Với từng luồng, xác nhận **nguồn → đích → giao thức/cổng → hướng → chủ sở hữu → mục đích → thời hạn**. Chỉ dùng nhóm địa chỉ đủ lớn để bao quát các máy thực sự cần kết nối. Nếu một luồng dùng nhiều máy, chọn nhóm quản lý có nguyên tắc membership và kiểm toán việc bổ sung máy mới.

Đối với các rule tạm cho nhà cung cấp, thử nghiệm hoặc xử lý sự cố, đặt thời hạn và cơ chế thu hồi có kiểm chứng. Quyền rộng “trong 30 phút” vẫn cần lý do, phê duyệt và các lớp bảo vệ khác; thời gian ngắn không bù được rủi ro của việc mở toàn bộ vùng dữ liệu.

### Bước 4 — Triển khai an toàn

Rà soát ảnh hưởng ứng dụng và đường quay lui (rollback). Thử trên staging hoặc trong khung bảo trì nếu thay đổi có khả năng gián đoạn, lưu cấu hình trước thay đổi và phối hợp với người phụ trách hạ tầng. Áp dụng rule hẹp, kiểm tra đường đúng được cho phép, sau đó gỡ rule cũ theo kế hoạch; tránh để hai policy cùng tồn tại lâu ngoài nhu cầu.

### Bước 5 — Kiểm chứng, giám sát và duy trì

Thử từ các máy được phép và máy không được phép; kiểm tra trên chính điểm cưỡng chế. Theo dõi log deny/allow, error rate của ứng dụng và độ trễ. Gắn rule với ticket, người phê duyệt, chủ dịch vụ và thời điểm rà soát tiếp theo. Định kỳ đối chiếu policy với inventory và phát hiện drift (sai khác với cấu hình đã duyệt).

~~~mermaid
flowchart TD
    A["Phát hiện rule rộng"] --> B["Lấy effective policy và lưu lượng"]
    B --> C["Xác nhận nhu cầu với chủ dịch vụ"]
    C --> D["Đề xuất phạm vi nguồn-đích-cổng"]
    D --> E["Phê duyệt và kiểm thử"]
    E --> F["Áp dụng, bỏ rule thừa"]
    F --> G{"Đường hợp lệ hoạt động? Đường trái phép bị chặn?"}
    G -- "Không" --> H["Điều tra và rollback có kiểm soát"]
    H --> D
    G -- "Có" --> I["Ghi bằng chứng, giám sát, tái kiểm"]
~~~

## 7. Bảng kiểm thử hành vi sau thay đổi

Giả sử mục tiêu là chỉ cho phép **10.44.20.15 → 10.44.30.25 TCP/5432**. Kiểm thử thực tế phải thực hiện từ máy/điểm mạng được ủy quyền, phù hợp thay đổi đã duyệt.

| Kiểm thử | Kết quả mong đợi | Ý nghĩa |
| --- | --- | --- |
| Nguồn đúng, đích đúng, TCP/5432 | **ALLOW** | Ứng dụng hoạt động |
| Nguồn **10.44.20.16**, đích đúng, TCP/5432 | **DENY** nếu nguồn này không được duyệt | Chặn workload ngoài phạm vi |
| Nguồn đúng, đích **10.44.30.26**, TCP/5432 | **DENY** nếu đích này không được duyệt | Không mở cả subnet DB |
| Nguồn đúng, đích đúng, TCP/22 | **DENY** theo rule ứng dụng | Không mở cổng quản trị |
| Nguồn đúng, đích đúng, UDP/5432 | **DENY** nếu chỉ duyệt TCP | Kiểm tra giới hạn giao thức |
| Nguồn ở mạng người dùng tới DB | **DENY** | Bảo vệ phân đoạn |
| Truy cập theo IPv6 vào dịch vụ cùng loại | Theo **chính sách IPv6 được duyệt** | Không để sót đường song song |
| Kết nối tồn tại trước khi đổi rule | Xử lý theo chính sách phiên và đặc tính firewall | Phát hiện phiên tiếp tục tồn tại |
| Backup/failover/HA trong khung phù hợp | Hoạt động theo luồng được duyệt | Giảm nguy cơ gián đoạn |
| Rule cho phép khác bao trùm luồng bị chặn | Không còn đường bypass ngoài ý muốn | Kiểm tra effective policy |

Các công cụ như firewall policy simulator, cloud reachability analyzer hoặc kiểm thử kết nối có kiểm soát đều hữu ích, nhưng không nên chỉ dựa vào kết quả một công cụ. Chẳng hạn một kết nối TCP không thành công có thể do dịch vụ chưa lắng nghe, route lỗi hoặc hệ thống đích chặn; nó **chưa chứng minh** firewall đã chặn đúng. Kết hợp sự kiện từ điểm cưỡng chế với kiểm thử đầu cuối.

## 8. Các trường hợp dễ gây nhầm lẫn

### 8.1. Có NAT thì source IP nhìn thấy có thể khác source gốc

Nếu nhiều nhân viên kết nối qua VPN/egress NAT, firewall ở phía database có thể thấy **một địa chỉ nguồn chung**. Allow /32 của egress gateway tuy hẹp về số địa chỉ nhưng có thể cấp đường đi cho hàng trăm người. Xác minh vị trí NAT so với điểm đặt firewall và gắn quyền với user/session tại gateway để không cấp quyền chỉ dựa trên IP chung.

### 8.2. Public IP và private IP không tự quyết định mức độ tin cậy

IP RFC 1918 như **10.0.0.0/8**, **172.16.0.0/12**, **192.168.0.0/16** không được định tuyến công khai trên Internet, nhưng có thể xuất hiện ở nhiều segment, VPN, liên kết giữa tổ chức hoặc môi trường cloud. “Private” không đồng nghĩa “an toàn”. Ngược lại, một ứng dụng public HTTPS có thể chủ động nhận **0.0.0.0/0** ở lớp edge và được bảo vệ bằng WAF, giới hạn truy cập ở backend.

### 8.3. “Chỉ allow /32” vẫn có thể là sai

Một /32 có thể trỏ tới NAT gateway dùng chung, load balancer hoặc proxy phục vụ nhiều tenant. Nếu IP này được tái sử dụng hoặc gán cho máy mới, phạm vi chủ thể thay đổi mà rule giữ nguyên. Phải biết chủ thể đứng sau IP, quyền đổi membership và vòng đời địa chỉ.

### 8.4. Rule được biểu diễn theo domain hay nhãn vẫn có thể rộng

Một object group chứa nhiều subnet, một nhãn cloud được gắn cho hàng trăm instance hoặc selector Kubernetes khớp toàn bộ namespace đều có thể mở rộng hơn dự định. Việc dùng tên nhóm thay IP không tự đảm bảo đặc quyền tối thiểu; vẫn phải quản lý và rà soát thành viên.

### 8.5. Stateful firewall và stateless ACL xử lý chiều phản hồi khác nhau

Stateful firewall thường cho phép gói phản hồi của phiên đã hợp lệ theo bảng trạng thái. Stateless ACL có thể cần rule cho chiều về, gồm cổng nguồn/đích tương ứng. Không sao chép rule “allow any any” từ hướng dẫn thiết bị khác mà chưa xác minh loại điểm cưỡng chế.

### 8.6. Giới hạn địa chỉ IP không thay thế bảo mật ứng dụng

Rule hẹp vẫn cần các lớp: IAM/RBAC đúng vai trò, xác thực mạnh, TLS/mTLS khi phù hợp, vá lỗi, quản lý bí mật, mã hóa dữ liệu, DNS an toàn, giám sát IDS/IPS và log truy cập. Những lớp này bảo vệ các tình huống mà lọc IP đơn thuần không giải quyết được.

## 9. Phát hiện rule quá rộng bằng quy tắc kiểm soát chất lượng

Có thể tích hợp việc rà soát vào pipeline Infrastructure as Code (IaC), quản lý firewall tập trung hoặc hệ thống CSPM. Các dấu hiệu nên được **gắn cờ để xem xét** gồm:

- Ingress quản trị (SSH, RDP, cổng API quản trị) từ **0.0.0.0/0** hoặc **::/0**.
- Luồng từ mạng người dùng/guest/đối tác tới vùng database hoặc mạng quản trị.
- Allow liên vùng với **protocol=ANY**, **port=ANY**, đặc biệt khi nguồn/đích cũng rộng.
- CIDR được mở rộng đột ngột, ví dụ từ một /32 thành /24 hoặc từ /24 thành /16, không kèm phê duyệt.
- Rule không có chủ sở hữu, lý do, ngày rà soát; ngoại lệ hết hạn vẫn còn hiệu lực.
- Overlap/shadow giữa rule hẹp và rule rộng, đối tượng nhóm chứa thành viên ngoài yêu cầu.
- Security group tham chiếu đến nhóm quá rộng hoặc nhãn/selector lấy toàn bộ workload production.

Đây là **tín hiệu phát hiện**, không phải bộ điều kiện tuyệt đối để xóa rule. Ví dụ cổng HTTPS của một dịch vụ công khai có thể hợp pháp khi mở rộng ra Internet. Hệ thống nên kết hợp phân loại tài nguyên, hướng lưu lượng, dịch vụ, môi trường và ngoại lệ đã duyệt để tránh nhiều cảnh báo sai.

Một bản ghi rà soát có thể dùng cấu trúc:

~~~yaml
# Ho so danh gia rule; khong phai cau hinh thiet bi
ruleId: FW-PROD-071
owner: database-team
sourceScope: "10.0.0.0/8"
destinationScope: "10.44.30.0/24"
protocols: ["any"]
businessPurpose: "Ung dung ket noi PostgreSQL"
riskFinding: "Nguon, dich va cong deu rong hon nhu cau"
proposedScope:
  source: "10.44.20.15/32"
  destination: "10.44.30.25/32"
  protocol: tcp
  destinationPort: 5432
approvalTicket: "CHG-EXAMPLE-071"
validation:
  permittedFlowWorks: true
  outOfScopeDenied: true
  effectivePolicyReviewed: true
reviewedBy: security-engineer
~~~

Kết quả kiểm thử trong bản ghi trên là **dữ liệu giả định nhằm minh họa** các trường nên lưu; không được hiểu là kết quả đã xác minh trên hệ thống nào.

## 10. Xử lý khi siết rule gây gián đoạn

Giả sử sau khi đổi rule, ứng dụng báo lỗi kết nối database. Không nên ngay lập tức trả rule thành **10.0.0.0/8 → 10.44.30.0/24 ANY** và để tồn tại vô hạn. Trước tiên:

1. Xác minh lỗi nằm ở đường mạng hay ở ứng dụng, DNS, TLS, xác thực database, routing hoặc trạng thái service.
2. Kiểm tra flow log/deny log tại điểm cưỡng chế, nguồn/đích nhìn thấy **sau NAT** và thứ tự luật thực tế.
3. Đối chiếu ứng dụng có thêm pod/VM, kết nối HA, tác vụ backup hoặc job theo lịch chưa được kiểm kê.
4. Bổ sung **luồng cụ thể** đã xác nhận và cập nhật inventory, tài liệu, kiểm thử.
5. Nếu cần khôi phục gấp, thực hiện rollback theo kế hoạch thay đổi với phạm vi và thời hạn được kiểm soát, theo dõi dấu hiệu truy cập bất thường, rồi hoàn thành khắc phục nguyên nhân.

Không nên đồng nhất “thử mở rộng rule thì ứng dụng chạy” với kết luận “phải giữ rule rộng”. Việc mở rộng có thể vô tình che giấu lỗi kiến trúc, cấu hình sai hoặc thiếu thông tin về phụ thuộc mạng.

## 11. Bài tập tình huống

Một hệ thống hỗ trợ khách hàng có frontend trong subnet **10.51.10.0/24**, backend tại **10.51.20.18** và database tại **10.51.30.11**. Khi cài đặt ban đầu, nhóm dự án thêm:

~~~text
ALLOW source=10.51.0.0/16 destination=10.51.0.0/16 protocol=ANY port=ANY
~~~

Vài tháng sau, có thêm subnet máy người dùng, máy test và một hệ thống chứa dữ liệu nhạy cảm nằm trong dải **10.51.0.0/16**. Nhóm bảo mật muốn giảm rủi ro nhưng không làm gián đoạn dịch vụ.

**Yêu cầu:** chỉ ra lỗi, nêu thông tin cần thu thập, đề xuất quy trình sửa và cách chứng minh sửa thành công.

**Phân tích tham khảo:**

- Lỗi nằm ở phạm vi nguồn/đích bao trùm toàn bộ /16 và mở mọi giao thức/cổng, khiến phân đoạn bên trong /16 không còn được bảo vệ như thiết kế.
- Thu thập tài liệu các luồng frontend → backend, backend → database, DNS, quản trị, giám sát, backup, HA, đồng thời kiểm tra NAT, rule chồng chéo và log thực tế.
- Tạo allow rule riêng cho từng luồng đã duyệt; ví dụ backend **10.51.20.18/32** kết nối database **10.51.30.11/32** đúng cổng ứng dụng sử dụng. Không tự đoán database chạy cổng gì khi chưa xác minh.
- Đưa thay đổi qua đánh giá ảnh hưởng và phê duyệt, kiểm thử các luồng được phép và các đường sai nguồn/đích/cổng, sau đó gỡ allow rộng.
- Đánh giá kết quả bằng effective policy, log tại điểm cưỡng chế, kiểm thử đầu cuối, chỉ số lỗi ứng dụng và dữ liệu kiểm toán. Tiếp tục rà soát khi có máy hoặc dịch vụ mới trong dải.

Nếu sau khi thu hẹp, một công việc backup định kỳ bị chặn, hãy xác minh nguồn backup và cổng cần thiết rồi mở **luồng backup cụ thể**, thay vì khôi phục lại quyền liên vùng không giới hạn.

## 12. Checklist trước khi duyệt một rule IP

- [ ] Đã xác định rõ công việc và chủ sở hữu của mỗi luồng mạng.
- [ ] Nguồn và đích được giới hạn đúng máy, nhóm dịch vụ hoặc subnet thật sự cần thiết.
- [ ] Giao thức, cổng, chiều kết nối và môi trường được ghi rõ.
- [ ] Đã kiểm tra IPv4, IPv6, NAT, routing, rule ưu tiên và nhóm địa chỉ liên quan.
- [ ] Đã xem xét nguồn có dùng IP chung, proxy/VPN/NAT hoặc workload thay IP hay không.
- [ ] Đã kiểm tra sự cần thiết của quyền quản trị, MFA, bastion, ZTNA và xác thực ứng dụng.
- [ ] Các ngoại lệ tạm có thời hạn và cơ chế thu hồi/kiểm chứng.
- [ ] Đã kiểm thử trường hợp hợp lệ, sai nguồn, sai đích, sai cổng và ảnh hưởng tới HA/backup.
- [ ] Đã chuẩn bị kế hoạch rollback có kiểm soát, log giám sát và trách nhiệm trực sự cố.
- [ ] Policy có ticket phê duyệt, ngày rà soát và quy trình cập nhật khi hạ tầng thay đổi.

**Ghi nhớ:** “Allow ít IP hơn” chỉ là bước khởi đầu. Một rule an toàn cần **đúng chủ thể, đúng nguồn, đúng đích, đúng dịch vụ, đúng chiều, đúng thời gian và có bằng chứng thực thi**. Trong kiến trúc mạng nhiều lớp, thu hẹp rule theo nhu cầu thật giúp giảm đường di chuyển ngang, duy trì phân đoạn và làm cho giám sát an ninh có ý nghĩa hơn.
