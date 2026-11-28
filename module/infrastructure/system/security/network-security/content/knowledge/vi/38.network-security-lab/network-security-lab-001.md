# Đặt mục tiêu và phạm vi cho lab network security

## 1. Bối cảnh: vì sao cần xác định mục tiêu trước khi dựng lab?

Trong chương **Dự án thực hành bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**, nhiệm vụ đầu tiên không phải cài firewall hoặc chạy công cụ, mà là trả lời rõ: **lab được tạo để kiểm chứng năng lực bảo mật nào, trên tài sản nào, với giới hạn an toàn và bằng chứng hoàn thành ra sao?**

Một lab network security có thể phục vụ nhiều chủ đề: phân đoạn VLAN/VRF, firewall và ACL, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi, hạ tầng cloud, phân tích lưu lượng, mô hình hóa mối đe dọa, giám sát xâm nhập và thiết kế kiến trúc phòng thủ. Nếu đưa tất cả vào cùng một môi trường mà không xác định trọng tâm, người học rất dễ dành phần lớn thời gian xử lý kết nối, cấu hình công cụ hoặc chạy các phép thử không dẫn đến kết luận kiểm chứng được.

**Lab tốt là môi trường được kiểm soát để kiểm tra giả thuyết.** Ví dụ: “Máy ở vùng Guest không được mở TCP/22 tới máy quản trị, trong khi bastion được phép truy cập SSH và hệ thống log ghi nhận đúng hai hành vi.” Câu này xác định được ranh giới, hành vi mong đợi và bằng chứng; khác với mục tiêu mơ hồ “học firewall”.

Sau bài học, người học có thể:

1. Phân biệt **mục tiêu học tập, yêu cầu kiểm soát, phạm vi, điều kiện giả định, ngoại lệ và tiêu chí nghiệm thu**.
2. Viết mục tiêu theo nguyên tắc **SMART**, liên kết mỗi mục tiêu với một hoặc nhiều ca kiểm thử an toàn.
3. Chọn số vùng mạng, tài sản, công nghệ và hành vi mô phỏng vừa đủ để chứng minh mục tiêu.
4. Xác định **in-scope, out-of-scope, rules of engagement (ROE)** và trách nhiệm phê duyệt.
5. Thiết kế topology lab cô lập, ma trận traffic, nguồn telemetry và cơ chế phục hồi.
6. Ước lượng thời gian, công sức, phụ thuộc, rủi ro và mức ưu tiên khi nguồn lực hạn chế.
7. Chuẩn bị **Lab Charter, Scope Register, Test Matrix, Evidence Plan, Risk Register và Exit Criteria**.
8. Biết khi nào cần thu hẹp, tạm dừng, thay đổi hoặc kết thúc lab mà không tự mở rộng phạm vi.

> **Nguyên tắc cốt lõi:** mục tiêu quyết định phạm vi; phạm vi quyết định topology và công cụ; các bài kiểm thử và bằng chứng quyết định kết quả đạt hay chưa đạt. Không thực hiện quy trình ngược lại chỉ vì có sẵn một công cụ.

## 2. Thuật ngữ và các quyết định phải ghi thành văn bản

### 2.1. Mục tiêu, phạm vi và tiêu chí thành công khác nhau thế nào?

| Thuật ngữ | Câu hỏi nó trả lời | Ví dụ cụ thể |
|---|---|---|
| **Learning objective** | Người học sẽ hiểu hoặc thực hiện được điều gì? | Phân biệt luồng USER → APP được phép với USER → MGMT bị cấm |
| **Security control objective** | Biện pháp phòng vệ phải bảo đảm điều gì? | Guest không truy cập management plane |
| **Scope** | Những tài sản, mạng, dịch vụ, giao thức và thời điểm nào được dùng? | Ba VM trong mạng 10.88.0.0/16 của lab cô lập |
| **Out-of-scope** | Điều gì tuyệt đối không được thử hoặc sửa? | Production, mạng công cộng, máy người khác, dữ liệu thật |
| **Assumption** | Điều gì tạm được coi là đúng và cần xác minh? | Firewall ảo hỗ trợ stateful policy và log DENY |
| **Dependency** | Thành phần nào phải có trước khi bắt đầu? | DNS lab, gateway, NTP, quyền truy cập console |
| **Test case** | Sẽ tạo/đọc sự kiện nào để kiểm tra? | Từ Client-G thử đúng một kết nối SSH tới Mgmt01 |
| **Evidence** | Dựa vào đâu kết luận kết quả? | Client output, firewall rule hit, capture và log máy đích |
| **Exit criteria** | Khi nào hoàn thành hoặc dừng? | Test bắt buộc đạt; mọi FAIL/NOT RUN được giải trình |
| **Risk acceptance** | Rủi ro còn lại nào được chủ sở hữu chấp nhận? | Chưa kiểm thử IPv6 vì toàn bộ VM lab chỉ bật IPv4 |

**Đích cuối cùng của lab** không phải “mọi công cụ chạy được”, mà là một tập phát hiện có thể trình bày, tái lập và phản biện.

### 2.2. Những sai lầm do định nghĩa mục tiêu quá rộng

- “Mô phỏng tất cả các cuộc tấn công mạng”: không xác định cách đo, độ phủ hay điều kiện dừng.
- “Cài càng nhiều công cụ càng tốt”: công cụ có nhưng chưa biết nó phát hiện hoặc chặn gì.
- “Chạy scan để xem hệ thống có an toàn không”: không có giả thuyết, phạm vi mục tiêu và tiêu chí đánh giá.
- “Không ping được tức là firewall an toàn”: ICMP không đại diện cho SSH, HTTPS, UDP hoặc IPv6.
- “IDS báo alert nghĩa là đã có sự cố”: alert có thể là false positive, log replay hoặc hành vi có phê duyệt.
- “Lab nằm trên laptop nên không cần ROE”: cấu hình bridge, route, VPN hoặc DNS có thể đưa traffic ra ngoài thiết bị thật.

Thay các câu trên bằng mục tiêu có chủ thể, hành vi, giới hạn và nguồn chứng cứ.

## 3. Từ nhu cầu học tập đến bài toán có thể kiểm chứng

### 3.1. Quy trình chuyển đổi nhu cầu thành mục tiêu

~~~mermaid
flowchart TD
    A["Nhu cầu học / rủi ro cần hiểu"] --> B["Tài sản và ranh giới tin cậy"]
    B --> C["Yêu cầu bảo vệ"]
    C --> D["Giả thuyết có thể kiểm thử"]
    D --> E["Topology + công cụ tối thiểu"]
    E --> F["Positive / negative tests"]
    F --> G["Log, packet, metric, evidence"]
    G --> H{"Kết quả có đủ chứng cứ?"}
    H -->|Có| I["PASS / FAIL có lý do"]
    H -->|Chưa| J["INCONCLUSIVE / bổ sung dữ liệu"]
    I --> K["Báo cáo và bài học"]
    J --> K
~~~

Ví dụ xuất phát từ nhu cầu “học bảo vệ mạng quản trị”:

1. **Rủi ro:** máy người dùng bị chiếm quyền có thể mở kết nối tới SSH của router.
2. **Tài sản:** một client USER, một thiết bị MGMT mô phỏng và một firewall giữa hai zone.
3. **Yêu cầu:** USER → MGMT:22 bị chặn; ADMIN-BASTION → MGMT:22 được phép.
4. **Giả thuyết:** sau khi áp default deny và allow hẹp, test TCP/22 từ USER không tới được đích vì rule firewall DENY.
5. **Bài kiểm thử:** kiểm tra cả USER (negative) và bastion (positive), từ IP đúng zone.
6. **Bằng chứng:** rule ID, 5-tuple, action, timestamp, client result và trạng thái SSH server.
7. **Kết luận:** PASS/FAIL/INCONCLUSIVE theo dữ liệu, không dựa trên cảm giác “đã cấu hình xong”.

### 3.2. Áp dụng SMART cho mục tiêu thực hành

SMART giúp tránh yêu cầu khó kiểm tra:

- **S – Specific:** nói rõ biện pháp, nguồn, đích, giao thức và điều kiện.
- **M – Measurable:** định nghĩa quan sát và tiêu chí đạt; không chỉ nói “hiểu tốt hơn”.
- **A – Achievable:** phù hợp số VM, tài nguyên, kiến thức và thời lượng.
- **R – Relevant:** gắn trực tiếp năng lực bảo mật mạng muốn rèn luyện.
- **T – Time-bound:** có mốc bàn giao, cửa sổ thực hiện và thời gian review.

Ví dụ:

**Mơ hồ:** “Nắm vững IDS/IPS”.

**Đo được:** “Trong một buổi lab đã phê duyệt, nạp ba bộ sự kiện tổng hợp gồm truy cập hợp lệ, truy cập trái chính sách và tình huống nhiễu vào hệ thống giám sát; người học xác định đúng ít nhất hai tình huống cần điều tra, giải thích trường hợp không đủ chứng cứ và lưu đường dẫn log theo Test ID.”

Cần phân biệt hai loại thước đo:

- **Thước đo học tập:** người học lý giải được vì sao test PASS/FAIL, biết sửa sai và báo cáo.
- **Thước đo hệ thống:** policy thực thi đúng; resolver trả lời; sensor có log; alert xuất hiện theo kỳ vọng.

Có thể hệ thống chạy đúng nhưng người học chưa hiểu; cũng có thể người học điều tra đúng một trường hợp FAIL và vẫn đạt năng lực phân tích.

## 4. Xếp ưu tiên mục tiêu theo giá trị và nguồn lực

Một lab đầu tiên không nhất thiết dựng đủ mọi công nghệ cùng lúc. Nên có **mục tiêu bắt buộc (must-have)**, **mục tiêu mở rộng (should-have/could-have)** và những yêu cầu hoãn lại.

| ID | Năng lực | Mục tiêu tối thiểu có thể đo | Ưu tiên |
|---|---|---|---|
| OBJ-01 | Phân vùng mạng | USER, APP, MGMT, GUEST có subnet/zone và route rõ ràng | Must |
| OBJ-02 | Firewall / ACL | Luồng HTTPS hợp lệ được phép, SSH từ USER tới MGMT bị chặn và có log | Must |
| OBJ-03 | DNS | Client hỏi resolver lab được phép; tên không tồn tại có phản hồi/RCODE giải thích được | Must |
| OBJ-04 | Quan sát lưu lượng | Gắn được Test ID với client, firewall và service log hoặc PCAP | Must |
| OBJ-05 | IDS/NDR | Nhận một bộ log tổng hợp gồm tình huống đáng ngờ và false positive | Should |
| OBJ-06 | VPN | Tài khoản lab qua VPN riêng được phép đi đến bastion, guest không được vào MGMT | Should |
| OBJ-07 | Xác thực | Có user/role giả lập và ghi nhận login thành công/thất bại | Should |
| OBJ-08 | Wi-Fi | So sánh SSID/GUEST mapping, isolation và lỗi 802.1X bằng log lab/simulator | Could |
| OBJ-09 | Cloud | VPC/VNet sandbox mô phỏng hoặc triển khai zone APP riêng có flow log | Could |
| OBJ-10 | Threat modeling | Có một trust-boundary diagram và ít nhất ba tình huống rủi ro | Must |
| OBJ-11 | Incident response | Triage một alert, phân biệt fact/hypothesis và viết ticket | Should |
| OBJ-12 | Automation/retest | Lặp lại ma trận test sau khi đổi một rule và so với baseline | Could |

Các mức trên là đề xuất cho **lab học tập**, không phải tiêu chuẩn vận hành production. Nếu chỉ có một máy cá nhân, ưu tiên mạng ảo + firewall + client + ứng dụng mẫu + logging trước, rồi bổ sung chức năng nếu không phá vỡ baseline.

### 4.1. Một quy tắc giới hạn độ phức tạp

Mỗi thành phần thêm vào phải trả lời được: **Nó phục vụ mục tiêu nào, test nào và bằng chứng nào?** Nếu chưa trả lời được, đưa vào danh sách tùy chọn thay vì scope hiện tại.

## 5. Xây danh mục tài sản và ranh giới tin cậy

### 5.1. Danh mục tài sản mẫu cho lab

Địa chỉ sau là IP riêng dùng **chỉ trong lab cô lập**; không lấy IP từ mạng thật và không tự quảng bá chúng ra production.

| ID | Tên tài sản | Vùng | Địa chỉ ví dụ | Vai trò và dữ liệu |
|---|---|---|---|---|
| AS-01 | FW-LAB | Gateway các zone | Gateway từng subnet 10.88.x.1 | Policy, NAT, log, route |
| AS-02 | USER-01 | USER | 10.88.10.25/24 | Máy tạo test traffic được phép |
| AS-03 | GUEST-01 | GUEST | 10.88.20.25/24 | Nguồn negative test |
| AS-04 | APP-01 | APP | 10.88.30.10/24 | Web HTTPS lab, health endpoint |
| AS-05 | DB-01 | DATA | 10.88.40.10/24 | Dữ liệu giả lập, service test |
| AS-06 | MGMT-01 | MGMT | 10.88.90.11/24 | SSH quản trị mock device |
| AS-07 | BASTION-01 | ADMIN | 10.88.91.10/24 | Nguồn quản trị được phê duyệt |
| AS-08 | DNS-01 | SHARED | 10.88.60.53/24 | Resolver/zone chỉ dùng trong lab |
| AS-09 | LOG-01 | SHARED | 10.88.60.10/24 | Syslog/SIEM giả lập, evidence |
| AS-10 | VPN-CLIENT | VPN-LAB | 10.88.70.25/24 | Nguồn test VPN nếu có |
| AS-11 | CLOUD-APP | CLOUD-OPT | 10.89.30.10/24 | Tùy chọn sandbox cloud/VM network |
| AS-12 | Host hypervisor | HOST/CONTROL | Không cấp IP test mặc định | Quản lý vòng đời VM, bảo vệ dữ liệu lab |

**Nguyên tắc inventory:** mỗi asset có ID, owner, địa chỉ, role, credential quản lý riêng, phiên bản nếu cần, mốc tạo/xóa, kết nối được phép và tiêu chí khôi phục. Không dùng tài khoản sản xuất hoặc sao chép dữ liệu khách hàng vào các VM.

### 5.2. Topology mục tiêu

~~~mermaid
flowchart LR
    U["USER<br/>10.88.10.0/24"] --> F["FW-LAB<br/>Inter-zone policies"]
    G["GUEST<br/>10.88.20.0/24"] --> F
    V["VPN-LAB<br/>10.88.70.0/24"] --> F
    A["ADMIN bastion<br/>10.88.91.10"] --> F
    F --> APP["APP<br/>APP-01 10.88.30.10"]
    F --> DATA["DATA<br/>DB-01 10.88.40.10"]
    F --> MG["MGMT<br/>MGMT-01 10.88.90.11"]
    F --> SH["SHARED<br/>DNS-01 + LOG-01"]
    F -. "traffic / rule logs" .-> SH
    U -. "local resolver query" .-> F
~~~

Mọi đường trong hình chỉ thể hiện kết nối logic qua ranh giới kiểm soát; **không đồng nghĩa mọi kết nối đều được phép**. Những luồng cụ thể được quyết định bởi ma trận ở phần sau.

**Cô lập mạng lab** không chỉ là đặt tên subnet khác. Phải kiểm tra cấu hình virtual switch: host-only/internal network, vNIC, default route, NAT, bridge, adapter USB/Wi-Fi và VPN trên máy chủ. Một adapter vô tình bridge vào mạng công ty có thể làm mọi giả định về tính cô lập trở nên sai.

### 5.3. Mô hình tin cậy

| Ranh giới | Mối quan tâm | Kiểm soát dự kiến |
|---|---|---|
| USER → APP | Chỉ ứng dụng đã công bố | Firewall allow TCP/443, HTTPS và authorization |
| USER → DATA | Không truy cập dữ liệu trực tiếp | Firewall deny, app là trung gian |
| USER/GUEST → MGMT | Không được quản trị thiết bị | Default deny và local-in/management ACL |
| ADMIN → MGMT | Người được phép mới đăng nhập | Bastion, tài khoản lab, SSH và audit |
| Client → DNS | Dùng resolver nội bộ | DNS01, firewall egress và query log |
| APP → DATA | Chỉ ứng dụng cần thiết | Allow theo IP/service có owner |
| Lab → host/Internet | Không rò route hoặc dữ liệu | Virtual switch isolation, outbound deny |

## 6. Chốt phạm vi: in-scope, out-of-scope và vùng phụ thuộc

### 6.1. In-scope được định nghĩa theo năm chiều

Không chỉ liệt kê IP; cần nêu **đúng**:

1. **Tài sản:** VM, vNIC, virtual switch, firewall ảo, DNS mock, collector và tài khoản lab.
2. **Vùng:** USER, GUEST, APP, DATA, MGMT, SHARED, ADMIN; vùng tùy chọn ghi rõ.
3. **Đường traffic:** cặp nguồn–đích, direction, TCP/UDP, port, dịch vụ và trạng thái kết nối.
4. **Thời gian:** khung giờ được thực hiện, mốc thu baseline và hạn dọn dẹp.
5. **Hoạt động:** cấu hình lab, test traffic lượng nhỏ, đọc log, phân tích PCAP, đổi rule thử nghiệm, rollback và viết báo cáo.

Ví dụ phạm vi cho phiên đầu: chỉ có USER-01, GUEST-01, APP-01, MGMT-01, DNS-01, FW-LAB và LOG-01; cloud và Wi-Fi để giai đoạn sau. Cách chia này giảm đồng thời chi phí, sai sót routing và nguồn gây false positive.

### 6.2. Out-of-scope phải nêu tường minh

| Loại ngoài phạm vi | Quy định minh họa |
|---|---|
| Mạng production | Không kết nối, định tuyến, quét, gửi traffic hoặc sửa policy |
| Thiết bị không thuộc sở hữu lab | Không cấu hình hoặc đăng nhập |
| Internet và tài nguyên bên thứ ba | Không sử dụng làm đích thử nếu chưa có sự cho phép riêng |
| Dữ liệu thật | Không sao chép thông tin người dùng, log có bí mật, token hoặc mật khẩu production |
| Hành vi xâm nhập thực | Không chạy malware, persistence, thu credential, exfiltration, khai thác lỗ hổng ngoài nhu cầu học |
| DDoS và stress diện rộng | Không flood, không tạo lưu lượng làm cạn tài nguyên hạ tầng chung |
| Chuyển tiếp sang mạng host | Không bật bridge/forwarding khiến lab trở thành điểm trung chuyển |
| Thay đổi ngoài cửa sổ | Không tự kéo dài bài test hoặc mở rộng thêm subnet khi chưa duyệt |

Dù một địa chỉ nằm trong dải RFC 1918, **điều đó không tự cho phép kiểm thử**. Dải nội bộ có thể thuộc doanh nghiệp, VPN hoặc cloud khác. Quyền thử nghiệm dựa trên sở hữu và phê duyệt, không dựa trên loại địa chỉ.

### 6.3. Các phụ thuộc cần đưa vào scope

- CPU/RAM/đĩa và khả năng dùng hypervisor.
- Bộ cài đặt, image, license và phiên bản ứng dụng.
- DNS/NTP, certificate CA lab, hostnames có thể phân giải.
- Cổng management của firewall và đường console phục hồi.
- Quyền đọc log từ firewall, DNS, APP, VPN và SIEM.
- Nguồn học/mentor và người phê duyệt khi lab chia sẻ.
- Kế hoạch snapshot, khôi phục và hủy dữ liệu.
- Nếu dùng cloud sandbox: ngân sách, IAM, tagging, quota, quyền xóa và egress policy.

Một phụ thuộc chưa sẵn sàng có thể làm ca test **NOT RUN**; không phải lý do để tự mở rộng quyền sang hệ thống khác.

## 7. Quy tắc tương tác (ROE): điều kiện được phép thử

### 7.1. ROE tối thiểu cho network security lab

ROE (Rules of Engagement) là ràng buộc về **ai được làm gì, ở đâu, khi nào và phải dừng khi nào**. Ngay cả lab cá nhân cũng cần ROE tối thiểu để tránh ảnh hưởng máy host, đường VPN và những hệ thống vô tình kết nối.

| Thành phần | Nội dung cần có |
|---|---|
| Authorization | Owner xác nhận lab asset và kỹ thuật được phép dùng |
| Asset scope | Danh sách asset ID, IP, subnet, tenant/account sandbox |
| Activity scope | Đọc log, test TCP/UDP hẹp, thay rule lab, packet capture giới hạn |
| Forbidden actions | Tấn công ngoài scope, làm nghẽn mạng chung, đọc dữ liệu người khác |
| Test window | Bắt đầu/kết thúc, người trực, kênh liên hệ |
| Rate/volume limit | Giới hạn probe, số kết nối, kích thước file, CPU, dung lượng log |
| Stop condition | Sai đích, traffic ra ngoài lab, mất management, quá tải, phát hiện sự cố thật |
| Evidence handling | Ẩn dữ liệu nhạy cảm, lưu bản gốc có quyền và retention |
| Containment/rollback | Quyền thay đổi, snapshot, console và cách khôi phục |
| Exception approval | Thay scope cần owner chấp thuận, cập nhật charter/test matrix |

**Ví dụ lệnh dừng diễn tập:** “LAB STOP – cô lập đường kết nối thử nghiệm và ngừng sinh traffic; bảo toàn log hiện có; thông báo owner trước khi tiếp tục.” Không được mặc định ngừng logging hoặc xóa bằng chứng khi dừng test.

### 7.2. Nếu lab chia sẻ với lớp học hoặc nhiều nhóm

Chỉ định rõ người được tạo VM, đổi routing, bật capture và xem log. Các nhóm dùng subnet hoặc namespace riêng để tránh chồng IP. Không cho nhóm khác biết mật khẩu admin chung. Cần dùng credential không có giá trị ngoài lab và thay vòng đời khi bàn giao.

Khi cần mô phỏng sự kiện tấn công, ưu tiên **log tổng hợp, PCAP công khai được phép sử dụng hoặc inject tabletop**; ghi rõ đâu là mô phỏng. Một alert từ replay không chứng minh network firewall đã chặn traffic live.

## 8. Mối đe dọa cần kiểm chứng, không phải kỹ thuật cần khai thác

Mục tiêu học là hiểu và đánh giá khả năng phòng vệ. Có thể dùng mô hình **asset → trust boundary → threat hypothesis → control → evidence** để giới hạn kịch bản.

| Rủi ro/giả thuyết | Ranh giới | Kiểm soát cần chứng minh | Cách thực hành an toàn |
|---|---|---|---|
| User truy cập trực tiếp DB | USER → DATA | Firewall deny, app-mediated access | Test kết nối vào port DB từ hai nguồn lab |
| Guest tới management | GUEST → MGMT | Default deny, management ACL | Một negative TCP connect và policy log |
| DNS ra ngoài resolver không được duyệt | USER → external resolver | DNS egress allowlist | Kiểm tra route/rule hoặc replay log DENY, không gửi tới đích thật |
| Lỗi nhận diện alert mạng | Log → IDS/NDR/SIEM | Parser, alert và phân loại false positive | Nạp dữ liệu giả lập có nhãn |
| VPN vượt quyền | VPN → ADMIN/MGMT | VPN group, route, AAA | Hai user lab có role khác nhau, đọc auth log |
| Wi-Fi guest isolation yếu | GUEST Wi-Fi → APP/MGMT | VLAN/NAC/client isolation | Emulator, lab AP hoặc tabletop mapping |
| Cloud SG quá rộng | Cloud zone → APP/DATA | SG/NSG và route inspection | IaC sandbox/flow simulation, không mở Internet ngoài scope |
| Route leak/đường bypass | VRF/các zone | Enforcement point bắt buộc | Review route và negative test an toàn |
| Log bị thiếu hoặc trễ | Sensor → LOG | Pipeline health, NTP | Inject log delay hoặc tắt một nguồn telemetry lab có phê duyệt |

**Không cần thực hiện một cuộc xâm nhập thực tế** để chứng minh các giả thuyết ở mức kiến trúc. Kiểm tra reachability, authorization, log correlation và các lựa chọn response đã đủ hữu ích cho giai đoạn nền tảng.

### 8.1. Giữ scenario mapping với mục tiêu

Nếu một scenario không gắn được với ít nhất một OBJ ID, một kiểm soát và một evidence ID, nên bỏ hoặc hoãn. Tránh “scope creep”: phát hiện một tính năng thú vị rồi mở rộng sang kiểm thử hệ thống không có trong kế hoạch.

## 9. Đặt tiêu chí thành công cho từng mục tiêu

### 9.1. Ví dụ Definition of Done có thể quan sát

| Mục tiêu | Hành vi phải chứng minh | Bằng chứng tối thiểu |
|---|---|---|
| OBJ-01 phân vùng | Mỗi VM thuộc zone và subnet định trước; route rõ ràng | IP/route snapshot, topology, gateway |
| OBJ-02 firewall | USER → APP TCP/443 ALLOW; GUEST → MGMT TCP/22 DENY | Client test + firewall action/rule hit + app/SSH state |
| OBJ-03 DNS | DNS01 trả kết quả đúng cho tên lab; query được log | Output DNS client, resolver log, time UTC |
| OBJ-04 quan sát | Ghép được cùng Test ID giữa client/firewall/server | Evidence manifest, 5-tuple, timestamp |
| OBJ-05 IDS/NDR | Test replay sinh alert cho tình huống gán nhãn và không nhầm nhóm đối chứng | Alert ID, log nguồn, decision analyst |
| OBJ-06 VPN | Người dùng lab đúng role đến bastion; role khác bị từ chối | VPN/AAA log, firewall rule, test kết nối |
| OBJ-08 Wi-Fi | Guest không vào mạng MGMT; client được gán VLAN dự kiến | Controller/NAC log, policy/negative test |
| OBJ-09 cloud | Spoke sandbox không bypass inspection đến DATA | Effective route, security policy, flow log, test |
| OBJ-10 threat model | Ít nhất ba giả thuyết có control và test tương ứng | Threat table và người review xác nhận |

### 9.2. Không viết tiêu chí “không có lỗi” quá chung

Nếu test bị timeout, chưa thể kết luận firewall đang chặn. Có thể server không chạy hoặc route không tồn tại. Vì vậy, một **negative test PASS** cần:

1. Nguồn và đích đúng scope.
2. Lưu lượng test đã đến điểm kiểm soát phải đánh giá.
3. Rule/policy DENY được xác nhận bằng log/counter/trace tương ứng.
4. Không có đường khác trong phạm vi kiểm thử làm bypass.
5. Thời điểm, trạng thái dịch vụ đích và cấu hình được ghi lại.

Một **positive test PASS** phải cho thấy ứng dụng hợp lệ hoạt động, không chỉ TCP port mở. Nếu mục tiêu là DNS, nên kiểm tra phản hồi ứng dụng DNS; nếu mục tiêu là HTTPS, kiểm tra TLS và endpoint health.

### 9.3. Ba loại kết luận chưa hoàn thành

- **FAIL:** hành vi trái chính sách được chứng minh.
- **INCONCLUSIVE:** chưa đủ dữ liệu hoặc sensor chưa chứng minh đường đi.
- **NOT RUN:** chưa chạy do thiếu công cụ, sai thời điểm hoặc ngoài scope.

Không biến NOT RUN thành PASS khi thiếu tính năng, cũng không gọi một kết quả FAIL là hoàn thành bảo mật chỉ vì lab “đã chạy”.

## 10. Ma trận traffic và bộ test tối thiểu

### 10.1. Ma trận luồng mục tiêu

| Nguồn | Đích | Dịch vụ | Kỳ vọng | Mục tiêu |
|---|---|---|---|---|
| USER-01 | APP-01 | HTTPS TCP/443 | ALLOW | OBJ-02 |
| USER-01 | DB-01 | TCP/5432 | DENY | OBJ-01/02 |
| APP-01 | DB-01 | TCP/5432 | ALLOW có điều kiện | OBJ-02 |
| GUEST-01 | MGMT-01 | SSH TCP/22 | DENY | OBJ-01/02 |
| BASTION-01 | MGMT-01 | SSH TCP/22 | ALLOW + auth phù hợp | OBJ-02/07 |
| USER-01 | DNS-01 | DNS UDP/TCP 53 | ALLOW | OBJ-03 |
| GUEST-01 | APP-01 | HTTPS TCP/443 | DENY mặc định nếu không có ngoại lệ | OBJ-02 |
| VPN-CLIENT role được duyệt | BASTION-01 | Dịch vụ đã phê duyệt | ALLOW | OBJ-06 |
| VPN-CLIENT role chưa được duyệt | MGMT-01 | SSH TCP/22 | DENY | OBJ-06 |
| USER-01 | ADMIN/MGMT | Các cổng quản trị khác | DENY | OBJ-02 |
| CLOUD-APP sandbox | APP-01 | HTTPS TCP/443 | Theo kiến trúc mở rộng | OBJ-09 |
| Các nguồn không liệt kê | Các vùng nhạy cảm | Mọi dịch vụ | DENY mặc định | OBJ-01/02 |

Một **ALLOW** mạng đến SSH không đồng nghĩa user có quyền đăng nhập. Hệ thống SSH/AAA phải kiểm soát quyền người dùng riêng; ma trận cần nêu cả mạng lẫn lớp ứng dụng khi cần.

### 10.2. Bộ Test ID có thể chạy lại

| Test ID | Thao tác ở mức kiểm thử | Kỳ vọng | Evidence |
|---|---|---|---|
| LAB-01 | Xem IP/route và zone của tất cả VM | Đúng inventory | E-IP |
| LAB-02 | USER-01 truy cập APP-01:443 | TCP/TLS và health OK | E-APP, E-FW |
| LAB-03 | USER-01 thử một kết nối DB-01:5432 | FW DENY đúng rule | E-FW, E-CLIENT |
| LAB-04 | GUEST-01 thử MGMT-01:22 | FW DENY đúng rule | E-FW, E-MGMT |
| LAB-05 | BASTION-01 tới MGMT-01:22 | Network allow, auth kiểm soát đúng | E-FW, E-AAA |
| LAB-06 | USER-01 truy vấn tên lab từ DNS-01 bằng UDP/53 | Resolver trả lời hợp lệ | E-DNS |
| LAB-07 | USER-01 truy vấn tên lab từ DNS-01 bằng TCP/53 | Resolver trả lời hợp lệ | E-DNS |
| LAB-08 | Nạp log giả lập có cảnh báo và log benign | Detector phân loại theo kỳ vọng | E-SIEM |
| LAB-09 | Lặp LAB-02 và LAB-04 sau thay rule lab | Không làm hỏng ALLOW và DENY | E-REG |
| LAB-10 | Review route IPv6 hoặc ghi rõ không có IPv6 | Không có đường bypass chưa đánh giá | E-IPV6 |
| LAB-11 | Kiểm tra health/ingest của log collector | Log đến đúng thời điểm, không im lặng giả | E-LOG |
| LAB-12 | Thực hành rollback một rule thử nghiệm | Khôi phục policy ban đầu và test lại | E-CHANGE |

Với các ca chưa có VM tương ứng, ghi **NOT RUN** hoặc điều chỉnh phạm vi qua phê duyệt, không tự tạo thêm nguồn/đích ngoài scope.

## 11. Quan sát, bằng chứng và điểm mù

### 11.1. Thiết kế bằng chứng từ đầu

| Nguồn | Trường cần lưu | Nó chứng minh được gì? | Giới hạn |
|---|---|---|---|
| Client test output | Thời điểm, IP đích, port, kết quả | Ứng dụng thấy kết nối như thế nào | Timeout không chứng minh firewall DENY |
| Firewall traffic log | Original/translated 5-tuple, zone, rule, action, session | Policy đã xử lý một luồng cụ thể | ALLOW không chứng minh server đã trả lời |
| APP-01 log | Request, status, client identity theo kiến trúc | Ứng dụng nhận và xử lý yêu cầu | Proxy/NAT có thể thay IP nguồn |
| DNS-01 log | Client, QNAME, QTYPE, RCODE, answer | Resolver thấy truy vấn và kết quả | Cache, DoH/DoT hoặc DNS ngoài scope |
| EDR/host log | Process, user, socket, action | Gắn hoạt động với host/process | Agent có thể thiếu log |
| IDS/NDR/SIEM | Rule/alert ID, confidence, event time | Detector đã sinh alert | Alert không chứng minh khai thác thành công |
| PCAP | Packet/flow tại vị trí capture | Kiểm tra thời gian, TCP flags, địa chỉ | Chỉ thấy điểm thu; TLS có thể mã hóa payload |
| Change log | Tên rule, trước/sau, người thay | Tái tạo thay đổi | Không bảo đảm hành vi nếu chưa test |

**Evidence manifest** phải ghi Test ID, source, collector, UTC event window, thời gian thu, filter, checksum nếu có file và nơi lưu. Không tạo hash giả. PCAP hoặc log chứa payload nhạy cảm cần hạn chế quyền truy cập.

### 11.2. Mốc thời gian và ảnh hưởng tới kết luận

Ba thời điểm không được trộn:

- **Event time:** khi sự kiện xảy ra ở client/firewall/DNS.
- **Ingest time:** khi collector/SIEM nhận dữ liệu.
- **Observation time:** khi người học nhìn thấy và ghi kết quả.

Nếu log trễ 90 giây, điều đó **không tự nghĩa** detector mất 90 giây để nhận diện sau khi log đến. Cần nêu định nghĩa và kiểm tra đồng bộ NTP.

### 11.3. Các điểm mù thường gặp

- Sau SNAT, địa chỉ nhìn thấy ở server khác IP nguồn thực.
- DNS resolver cache khiến không phát sinh query ở điểm capture dự kiến.
- DoH/DoT và TLS mã hóa phần nội dung mà sensor mạng không thấy.
- Hai workload cùng subnet có thể giao tiếp không đi qua firewall L3.
- IPv6 hoặc split-tunnel VPN đi tuyến khác IPv4.
- NetFlow/sensor sampling khiến số flow trong log không bằng số request.
- Session state cũ vẫn cho kết nối hoạt động sau khi thay rule.
- Firewall log bị tắt hoặc rule không bật logging.

Tập test phải phát hiện hoặc **ghi nhận rõ** các điểm mù ảnh hưởng đến mục tiêu, tránh kết luận quá mức.

## 12. Thiết kế công cụ và tài nguyên tối thiểu

### 12.1. Chọn công cụ theo vai trò

| Nhu cầu | Nhóm công cụ có thể dùng | Quy tắc chọn |
|---|---|---|
| Chạy VM và mạng ảo | Hypervisor, virtual switch, container network cho mục đích phù hợp | Phải hỗ trợ isolation và snapshot |
| Chính sách phân vùng | Firewall ảo/router lab, host firewall | Có rule lookup, log ALLOW/DENY, export config |
| Test chức năng | curl, nc, dig, các client hợp lệ | Tạo ít traffic, theo đúng protocol trong Test ID |
| Đọc packet | tcpdump, Wireshark, tshark | Capture hẹp, có quyền và điểm thu rõ |
| IDS/IPS/NDR | Sensor lab hoặc replay engine và alert parser | Có thể mô phỏng log, không cần payload nguy hiểm |
| Logging/SIEM | Syslog collector, dashboard, log parser | Timestamp chuẩn, lưu raw evidence |
| Identity/VPN | VPN gateway và mock AAA/IdP nếu thuộc scope | Dùng tài khoản lab riêng, không trộn credential thật |
| Wi-Fi | Emulator/controller lab hoặc AP riêng được phép | Không phát SSID gây nhầm với mạng thật |
| Cloud | Sandbox account với budget guardrail | IAM, tagging, private routing và giới hạn egress |

Chỉ đưa công cụ vào phần **must-have** nếu phục vụ Test ID bắt buộc. Ví dụ, chưa cần cài SIEM lớn để bắt đầu nếu có thể lưu và đối chiếu syslog trong một VM nhỏ; không cần cloud account để học logic VLAN và firewall.

### 12.2. Kích thước lab theo ba mức

| Mức | Thành phần | Năng lực trọng tâm | Giới hạn |
|---|---|---|---|
| **L0 — Offline analysis** | PCAP/log tổng hợp, sơ đồ, bảng policy | Nhận biết dấu hiệu, đọc log, viết test plan | Chưa chứng minh network control live |
| **L1 — Core isolated lab** | Firewall, USER, GUEST, APP/MGMT, DNS và log | Reachability, allow/deny, positive/negative test | Ít hoặc không có VPN, cloud, Wi-Fi |
| **L2 — Extended lab** | Thêm VPN, IDS/IPS, DATA, NAC/Wi-Fi, cloud sandbox | Correlation, identity, hybrid, incident response | Cần nhiều tài nguyên, ROE/monitoring kỹ hơn |

Nên xây **L0 → L1 → L2** có mốc nghiệm thu. Nếu L1 chưa chứng minh được ranh giới, thêm L2 sẽ làm tăng biến số và khiến nguyên nhân lỗi khó tìm hơn.

## 13. Kế hoạch xây dựng lab theo pha

### 13.1. Pha A — Thiết kế và kiểm tra giả định

- Chốt mục tiêu Must/Should/Could, Test ID và definition of done.
- Lập inventory, IP plan, sơ đồ zone/route/virtual switch, lưu lượng và log.
- Kiểm tra host không bridge vào mạng ngoài scope.
- Xác nhận người phê duyệt, thời gian, công cụ và điều kiện dừng.
- Tính toán tối thiểu tài nguyên, snapshot, lưu trữ log và đường quản trị.

**Gate A:** tài liệu đủ để một người khác hiểu ai thử cái gì mà không cần đoán.

### 13.2. Pha B — Khởi tạo mạng và dịch vụ cơ sở

- Tạo các zone/vSwitch và VM cần thiết.
- Đặt IP/gateway/DNS và chứng minh mỗi host thuộc đúng mạng.
- Xác minh không có NAT/bridge/route đi tới mạng thực ngoài scope.
- Tạo một dịch vụ web health, một dịch vụ DNS nội bộ và hệ thống log.
- Bật đồng bộ thời gian, kiểm tra log ingest và đường quản trị khôi phục.
- Chụp snapshot sạch.

**Gate B:** dịch vụ lab hoạt động và có bằng chứng topology, không còn kết nối ngoài phạm vi.

### 13.3. Pha C — Thiết lập baseline

- Ghi cấu hình rule/route hiện tại, policy mặc định và phiên bản firewall.
- Thử các kết nối phải ALLOW trước khi áp thêm chính sách có thể làm gián đoạn.
- Kiểm tra DNS, web, logging, process/port listener của các VM.
- Ghi latency, thời gian test, packet flow và chất lượng log theo mức cần thiết.
- Tách điều kiện baseline khỏi điều kiện sau khi thay policy.

**Gate C:** đủ dữ liệu để diễn giải thay đổi; không kết luận false FAIL do dịch vụ đích chưa chạy.

### 13.4. Pha D — Áp chính sách và kiểm thử

- Cấu hình firewall/VLAN/VRF/ACL theo ma trận đã review.
- Chạy một ca tại một thời điểm, ghi Test ID và time window.
- Với negative test, kiểm tra rule DENY ở đúng ranh giới, không chỉ kết quả timeout.
- Với positive test, kiểm tra service health và log đích.
- Nếu có IDS/IPS, dùng telemetry giả lập có nhãn và nhóm đối chứng benign.
- Lưu kết quả, lỗi/điểm mù và quyết định sửa hoặc hoãn.

**Gate D:** có kết quả PASS/FAIL/INCONCLUSIVE rõ ràng, không tự ý mở rộng scope.

### 13.5. Pha E — Regression, teardown và tổng kết

- Lặp lại các ca then chốt sau một thay đổi rule hoặc route có chủ đích.
- Thực hành khôi phục snapshot/rollback trong lab.
- Thu log, PCAP và bản xuất policy, đảm bảo bằng chứng được lưu có kiểm soát.
- Dừng traffic, xóa credential tạm và hủy tài nguyên cloud nếu đã tạo.
- Xác minh host/vSwitch không còn bridge hoặc route tạm.
- Viết báo cáo mục tiêu–thực hiện–bằng chứng–bài học–rủi ro còn lại.

**Gate E:** lab có thể được khôi phục hoặc teardown an toàn; báo cáo phản ánh đúng điều đã thử và chưa thử.

## 14. Ví dụ thao tác đọc kiểm tra ban đầu

Các ví dụ dưới đây chỉ phục vụ **môi trường lab có quyền** và tập trung vào quan sát; không phải lệnh tấn công. Thay địa chỉ theo inventory lab và giới hạn kiểm thử theo ROE.

### 14.1. Xác minh địa chỉ và route của máy lab Linux

~~~bash
ip -br address
ip route
ip route get 10.88.30.10
ip route get 10.88.90.11
ip -s link show
~~~

Những lệnh này cho biết IP, interface, route dự kiến và thống kê đường truyền, nhưng **không chứng minh** firewall đã cho phép hay chặn gói. Cần đối chiếu với firewall logs và điểm đích.

### 14.2. Kiểm thử đúng một cổng TCP đã được cho phép

~~~bash
# LAB-02: từ USER-01 tới APP-01 trong mạng cô lập
nc -vz -w 3 10.88.30.10 443

# LAB-04: từ GUEST-01 tới MGMT-01, negative test được phê duyệt
nc -vz -w 3 10.88.90.11 22
~~~

Để kiểm chứng HTTPS ứng dụng với hostname do DNS lab quản lý:

~~~bash
curl -v --connect-timeout 3 --max-time 10 \
  --resolve app.lab.example:443:10.88.30.10 \
  https://app.lab.example/health
~~~

Nếu dùng certificate CA nội bộ, cấu hình trust store hoặc cung cấp CA phù hợp; tránh bỏ qua kiểm tra TLS chỉ để có kết quả PASS. Endpoint health phải do chủ lab triển khai và ghi rõ kết quả kỳ vọng.

### 14.3. Kiểm thử DNS nội bộ

~~~bash
dig @10.88.60.53 app.lab.example A +tries=1 +time=2
dig +tcp @10.88.60.53 app.lab.example A +tries=1 +time=2
~~~

Phải xác nhận DNS01 được cấu hình đúng zone và bản ghi. DNS trả NXDOMAIN không nhất thiết là lỗi mạng: đó có thể là câu trả lời hợp lệ cho tên không tồn tại, nhưng sẽ FAIL một test yêu cầu IP cụ thể.

### 14.4. Đọc PCAP đã thu

~~~bash
sha256sum /path/to/lab-02.pcapng
capinfos /path/to/lab-02.pcapng
tshark -r /path/to/lab-02.pcapng -q -z conv,tcp
~~~

Khi được phép capture, chỉ lọc host/port/time window cần thiết và có cơ chế dừng. Không lưu toàn bộ nội dung người dùng hoặc các file bí mật vào PCAP để “có nhiều dữ liệu”. Với TLS mã hóa, PCAP không mặc nhiên hiển thị HTTP payload.

### 14.5. PowerShell khi dùng Windows VM

~~~powershell
Get-NetIPAddress -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv4
Test-NetConnection -ComputerName 10.88.30.10 -Port 443
~~~

Kết quả mạng chỉ nói về địa chỉ/port tại thời điểm chạy. Mọi kết luận kiểm soát vẫn cần rule và evidence tại firewall/dịch vụ.

## 15. Quản lý thay đổi, khôi phục và tình huống lỗi

### 15.1. Những việc phải chuẩn bị trước khi sửa policy

- Có bản backup cấu hình firewall, IP plan và snapshot VM.
- Có cách truy cập console/out-of-band để sửa lỗi route mà không cần chính mạng đang thay.
- Có **test baseline** hoạt động, ít nhất một positive test và một negative test.
- Biết rule nào sẽ thay đổi, owner, tác động dự kiến và thời điểm bắt đầu/kết thúc.
- Có lệnh hoặc thao tác hoàn tác phù hợp đúng công cụ đang sử dụng.
- Không đẩy cấu hình lab vào production bằng shared automation credentials.
- Không để rule test mở không thời hạn hoặc thiếu người sở hữu.

### 15.2. Một kịch bản rollback mẫu

**Tình huống:** sau khi tách USER/APP và đặt default deny, USER-01 không truy cập được APP-01:443.

**Cách xử lý:**

1. Dừng các test mới và ghi timestamp xảy ra lỗi.
2. Kiểm tra địa chỉ, gateway, route, DNS, listener APP-01 và firewall rule match.
3. Xác định đó là rule DENY sai, đường về sai, NAT hoặc dịch vụ APP-01 lỗi.
4. Nếu tác động ngoài phạm vi chấp nhận, hoàn tác **đúng thay đổi lab** theo snapshot/backup đã xác nhận.
5. Chạy lại LAB-02 để kiểm tra APP hoạt động và LAB-04 để bảo đảm GUEST vẫn không tới MGMT.
6. Ghi nguyên nhân, evidence và quyết định tiếp tục hay hoãn mục tiêu.

Đừng sửa lỗi bằng cách bật ALLOW ANY-ANY trên mọi zone khi chưa hiểu vấn đề. Nó có thể làm dường như ứng dụng đã “khỏe” nhưng phá hỏng mục tiêu segmentation.

### 15.3. Phản ứng khi phát hiện kết nối thoát lab

Đây là **stop condition quan trọng**. Người thực hành phải ngừng sinh traffic, kiểm tra virtual switch/bridge/NAT/route và báo owner của hệ thống bị ảnh hưởng nếu có. Không tự tạo thêm traffic để “thử xem ra đến đâu”, không che giấu log. Chỉ tiếp tục sau khi kiểm chứng môi trường đã quay lại phạm vi được phép.

## 16. Quản lý rủi ro và giới hạn tài nguyên

### 16.1. Risk register mẫu

| Risk ID | Rủi ro | Xác suất/tác động tương đối | Biện pháp giảm thiểu | Owner |
|---|---|---|---|---|
| R-01 | VM vô tình bridge vào mạng thật | Thấp/Cao | Dùng internal vSwitch, review NIC/route, stop test khi sai | Lab owner |
| R-02 | Không có firewall log cho negative test | Trung bình/Trung bình | Bật logging theo rule lab, PCAP giới hạn, test trước | Security tester |
| R-03 | Thiếu RAM/CPU khiến sensor lỗi | Trung bình/Trung bình | Khởi đầu L0/L1, giới hạn số VM và log | Lab operator |
| R-04 | DNS hoặc clock sai làm test FAIL giả | Trung bình/Thấp–Trung bình | Time sync, kiểm tra zone và baseline | DNS/operator |
| R-05 | Chỉnh rule khóa đường quản trị | Trung bình/Trung bình | Console, snapshot, thay đổi nhỏ và rollback | Firewall owner |
| R-06 | Capture thu dữ liệu không cần thiết | Thấp/Trung bình | Filter hẹp, retention, quyền đọc, synthetic data | Evidence owner |
| R-07 | Cloud sandbox phát sinh chi phí | Trung bình/Trung bình | Budget alert, quota/tagging, teardown check | Cloud owner |
| R-08 | Người học mở rộng scope giữa buổi | Cao/Trung bình | Scope freeze, change request và phê duyệt | Exercise lead |
| R-09 | Thiếu chứng cứ nhưng vẫn ghi PASS | Trung bình/Cao | Tiêu chí evidence bắt buộc, reviewer độc lập | Evaluator |
| R-10 | Test lẫn vào sự kiện production hoặc SOC thật | Thấp/Cao | Nhãn EXERCISE, lab isolation, thông báo đúng kênh | Lab owner |

Đây là đánh giá định tính cho bài học; mỗi nhóm phải sửa xác suất, tác động và owner theo môi trường thực. Rủi ro có thể được giảm, chuyển, chấp nhận có lý do hoặc tránh bằng cách loại bỏ chức năng khỏi scope.

### 16.2. Dự toán nguồn lực

Một lịch minh họa cho lab L1 có thể là:

| Mốc | Công việc | Sản phẩm |
|---|---|---|
| Buổi 1 | Charter, mục tiêu SMART, inventory, threat table | Scope v1 được review |
| Buổi 2 | Topology, network isolation, DNS và APP | Sơ đồ và baseline |
| Buổi 3 | Firewall policy, logging, test traffic | Test matrix chạy lần 1 |
| Buổi 4 | Replay IDS/NDR, triage và evidence | Detection/ticket exercise |
| Buổi 5 | Regression, rollback, report và review | Report + action tracker |

Đây **không phải ước tính bắt buộc**; lab lớn có thể cần nhiều hơn, còn người đã có môi trường dựng sẵn có thể giảm thời lượng. Không đẩy tiến độ bằng cách bỏ kiểm tra isolation, quyền truy cập hoặc rollback.

## 17. Phân quyền và quản trị công việc nhóm

### 17.1. Vai trò gợi ý

| Vai trò | Quyết định/chịu trách nhiệm chính | Sản phẩm |
|---|---|---|
| Lab owner / instructor | Chốt phạm vi, ROE, điều kiện dừng và nguồn lực | Charter và approval |
| Network architect | Topology, IP/VLAN/VRF, route, firewall placement | Sơ đồ và IP plan |
| Security tester | Test matrix, phương pháp test, log evidence | Test run và kết luận |
| Operator/NOC | Sensor health, connectivity, snapshot, support | Baseline và runbook |
| SOC analyst / evaluator | Diễn giải alert và phân loại false positive | Detection/ticket evaluation |
| Service owner | App/DNS/DB health và tác động chức năng | Positive test acceptance |
| Evidence custodian | Lưu trữ log/PCAP, quyền truy cập và checksum | Evidence manifest |

Với lab cá nhân, một người có thể đảm nhiệm nhiều vai, nhưng vẫn nên ghi **ai phê duyệt thay đổi**, **ai đánh giá kết quả** và **ai xác nhận an toàn**. Với lab dùng chung, tránh để tester tự thay điều kiện đạt sau khi thấy kết quả FAIL.

### 17.2. Định kỳ quản lý thay đổi phạm vi

Mọi đề xuất thêm asset, subnet, kỹ thuật, Internet/cloud connectivity hoặc tài khoản quản trị phải có:

1. Lý do gắn với mục tiêu học tập hoặc yêu cầu bảo mật cụ thể.
2. Tác động đến ROE, threat model, rủi ro và timebox.
3. Thay đổi Test ID/expected/evidence và inventory.
4. Quyền phê duyệt của lab owner.
5. Kế hoạch rollback/teardown cập nhật.

Nếu không đủ nguồn lực, đưa đề xuất vào **backlog** để làm ở phiên sau; không sửa scope lặng lẽ.

## 18. Mẫu Lab Charter hoàn chỉnh

Đây là mẫu nội dung có thể sử dụng như tài liệu khởi động dự án. Nó **không thay thế** file metadata của bài học và không phải cấu hình có thể triển khai trực tiếp.

~~~yaml
lab:
  id: NS-LAB-001
  title: "Network security foundational lab"
  module: SECURITY_NETWORK_SECURITY
  language: vi
  owner: "Lab owner được chỉ định"
  state: proposed

purpose:
  - "Thực hành bảo vệ traffic liên vùng"
  - "Đo hiệu quả firewall rule và khả năng quan sát"
  - "Phân biệt sự kiện bảo mật với lỗi vận hành"

objectives:
  must:
    - id: OBJ-01
      description: "Phân vùng USER/APP/GUEST/MGMT/SHARED theo IP plan"
      evidence: "topology, interfaces, routes"
    - id: OBJ-02
      description: "Cho phép USER->APP:443, chặn GUEST->MGMT:22"
      evidence: "client test, firewall rule/action, server health"
    - id: OBJ-03
      description: "Resolver lab trả lời và ghi log DNS query"
      evidence: "DNS response, resolver event"
    - id: OBJ-04
      description: "Ghép được log nhiều nguồn theo Test ID và UTC"
      evidence: "evidence manifest, log records"
  optional:
    - OBJ-05
    - OBJ-06
    - OBJ-08
    - OBJ-09

scope:
  networks:
    - "10.88.10.0/24 USER"
    - "10.88.20.0/24 GUEST"
    - "10.88.30.0/24 APP"
    - "10.88.40.0/24 DATA"
    - "10.88.60.0/24 SHARED"
    - "10.88.90.0/24 MGMT"
    - "10.88.91.0/24 ADMIN"
  assets:
    - FW-LAB
    - USER-01
    - GUEST-01
    - APP-01
    - MGMT-01
    - DNS-01
    - LOG-01
  excluded:
    - "Production, external third-party networks"
    - "Real credentials or production data"
    - "Malware execution, persistence, exfiltration"
    - "Broad scanning, flood or denial of service"

rules_of_engagement:
  lab_only: true
  network_mode: "isolated/internal; no unapproved bridge"
  allowed: "Narrow traffic tests, lab policy changes, log analysis"
  stop_conditions:
    - "Traffic appears outside authorized lab"
    - "Unexpected impact on host or shared infrastructure"
    - "Loss of safe management/rollback path"
  test_window: "Approved by owner before execution"
  approval: "Pending"
  rollback: "Restore verified snapshot/config"

verification:
  required_tests:
    - LAB-01
    - LAB-02
    - LAB-03
    - LAB-04
    - LAB-06
    - LAB-07
    - LAB-09
    - LAB-11
  result_values:
    - PASS
    - FAIL
    - INCONCLUSIVE
    - NOT_RUN
  acceptance: "Required tests evidenced; all exceptions documented"
  artifacts:
    - topology
    - scope_register
    - threat_model
    - test_matrix
    - evidence_manifest
    - final_report
~~~

**Lưu ý:** các trường văn bản như approval/test_window chỉ là chỗ ghi quyết định. Không được coi giá trị “Pending” hoặc mô tả YAML là sự phê duyệt thật.

## 19. Tình huống làm mẫu từ đầu đến cuối

### 19.1. Yêu cầu ban đầu

“Một lớp học muốn dựng lab để kiểm tra firewall ngăn người dùng truy cập vùng quản trị, đồng thời vẫn cho phép dịch vụ HTTPS nội bộ. Thời gian có hạn, chỉ một máy đủ chạy vài VM.”

**Thiết kế không tốt:** dựng luôn VPN, cloud, Wi-Fi controller, SIEM lớn, IDS/IPS, DNS, container cluster và thêm tình huống tấn công mà chưa có sơ đồ hoặc Test ID.

**Thiết kế có thể kiểm chứng:**

1. Chọn **Must**: OBJ-01, OBJ-02, OBJ-04; DNS OBJ-03 nếu phục vụ hostname lab.
2. Chọn asset tối thiểu: firewall, USER client, GUEST client, APP web server, MGMT SSH server và log collector; có thể gom vai trò DNS/log nếu tài nguyên hạn chế và vẫn giữ đúng ranh giới.
3. Xác định rủi ro: USER/GUEST truy cập MGMT, firewall route bypass, không có log chứng minh.
4. Vẽ network isolation và xác nhận không bridge vào adapter thật.
5. Lập ma trận USER → APP:443 ALLOW, GUEST → MGMT:22 DENY, BASTION → MGMT:22 ALLOW nếu có bastion.
6. Chạy một positive test và một negative test; ghép client output, firewall log và server state.
7. Lưu kết quả, thay một rule lab, chạy regression và thực hiện rollback.
8. Đóng phiên với báo cáo: điều chứng minh được, điều chưa kiểm thử, giới hạn tài nguyên, công việc phiên sau.

### 19.2. Ví dụ kết quả minh họa

Bảng này là **tình huống giả lập**, không phải kết quả chạy trên môi trường thực.

| Test ID | Kỳ vọng | Quan sát | Quyết định |
|---|---|---|---|
| LAB-01 | VM ở đúng zone | Interface và route phù hợp inventory | PASS |
| LAB-02 | USER → APP:443 ALLOW | TCP/TLS thành công, HTTP 200, FW ALLOW | PASS |
| LAB-04 | GUEST → MGMT:22 DENY | Timeout, nhưng firewall không có log/capture tương ứng | INCONCLUSIVE |
| LAB-06 | DNS query có kết quả | Resolver trả A record đúng và có query log | PASS |
| LAB-09 | Không mất chức năng sau thay rule | APP vẫn hoạt động, chưa test MGMT âm tính | INCONCLUSIVE |
| LAB-11 | Log ingest ổn định | Syslog đến trễ do clock mismatch | FAIL |

Một bài học quan trọng ở đây: **LAB-04 chưa thể PASS chỉ vì timeout**. Cần tìm xem packet có đến firewall, có đúng rule DENY hoặc nguyên nhân là thiếu listener/route. LAB-09 cũng chưa đạt regression đầy đủ vì negative test chưa được lặp.

### 19.3. Cách thay đổi phạm vi hợp lệ

Nếu mất nhiều thời gian khắc phục log collector, nhóm có thể xin phép **hoãn IDS/NDR** và giữ mục tiêu bắt buộc cho firewall, DNS, log cơ bản. Không được thay tiêu chí bắt buộc sau khi thấy kết quả FAIL rồi báo cáo “100% thành công” mà không ghi ngoại lệ.

## 20. Báo cáo kết quả và các trường bắt buộc

### 20.1. Cấu trúc báo cáo cuối lab

1. **Executive summary:** mục tiêu, những gì đã kiểm chứng, rủi ro còn lại.
2. **Scope và ROE:** in-scope, exclusions, approvals và thay đổi đã chấp thuận.
3. **Topology và inventory:** sơ đồ network zone, IP plan, asset owner, công cụ.
4. **Threat model:** giả thuyết, ranh giới, kiểm soát và mức ưu tiên.
5. **Test matrix:** Test ID, kỳ vọng, actual, kết quả và điều kiện test.
6. **Evidence:** firewall/DNS/app/IDS logs, captures, timestamp, hash và nguồn.
7. **Phân tích:** vì sao PASS/FAIL/INCONCLUSIVE, false positive, điểm mù.
8. **Vận hành:** change log, rollback, tác động, lỗi môi trường và khôi phục.
9. **Kết luận:** mục tiêu đạt/chưa đạt, công việc cần làm và retest.
10. **Appendix:** thông tin phiên bản, cấu hình đã ẩn bí mật, ghi chú kỹ thuật.

### 20.2. Mẫu evidence manifest và test result

~~~text
LAB REPORT: NS-LAB-001
RUN ID: RUN-001
TEST ID: LAB-04
EXPECTED: GUEST-01 -> MGMT-01 TCP/22 = DENY
ACTUAL: Client connection timeout
FIREWALL RULE: not yet confirmed
EVIDENCE:
  E-CLIENT-04: client output, time UTC
  E-FW-04: no matching firewall log found in current query
LIMITATION:
  Destination listener status not verified
  Ingress packet path not confirmed
RESULT: INCONCLUSIVE
NEXT ACTION:
  Verify source zone, service listener, firewall ingress
  Capture narrow flow in authorized test window
OWNER: Lab network tester
~~~

Lý do báo cáo cần cụ thể: người review phải biết **đã nhìn thấy điều gì, chưa thể kết luận điều gì và cách lặp lại**. Không dùng những từ chung chung như “an toàn”, “hết lỗi”, “đã chặn được hacker” khi chỉ kiểm tra một vài luồng lab.

## 21. Tiêu chí chấp nhận, điểm dừng và đánh giá

### 21.1. Một bản charter đủ chất lượng cần có

- **Rõ mục tiêu:** ít nhất ba yêu cầu có Test ID và evidence, không mơ hồ.
- **Giới hạn được:** biết chính xác asset/subnet/time window và hoạt động cấm.
- **An toàn:** không route ngoài lab, dùng dữ liệu giả lập, có quyền và stop condition.
- **Khả thi:** hạ tầng đủ tài nguyên cho các yêu cầu Must và có phase riêng cho mở rộng.
- **Đo được:** PASS/FAIL/INCONCLUSIVE/NOT RUN có định nghĩa.
- **Tái lập được:** lưu topology, phiên bản, policy, log và cách chạy lại.
- **Phục hồi được:** có snapshot, console, rollback và teardown.
- **Có trách nhiệm:** biết owner, approver, reviewer và thời điểm đánh giá.

### 21.2. Rubric 100 điểm

| Hạng mục | Điểm tối đa | Điều kiện chấm |
|---|---:|---|
| Mục tiêu SMART và ưu tiên | 20 | Mục tiêu gắn với nhu cầu, có điều kiện đạt |
| In-scope/out-of-scope/ROE | 20 | Giới hạn tài sản, kỹ thuật, quyền và dừng rõ |
| Topology, trust zone, inventory | 15 | Sơ đồ khớp IP plan và đường đi |
| Threat/control/test mapping | 15 | Có mối liên hệ giữa rủi ro, chính sách và Test ID |
| Evidence và tiêu chí nghiệm thu | 15 | Phân biệt PASS/FAIL/INCONCLUSIVE, nguồn log rõ |
| Khả thi, rủi ro, rollback | 10 | Timebox, phụ thuộc, snapshot, stop condition |
| Bản charter/báo cáo mạch lạc | 5 | Người khác có thể tái lập và review |
| **Tổng** | **100** | Không chấm kết quả cao nếu vi phạm ROE |

**Điều kiện không thể bù bằng điểm:** thao tác ngoài phạm vi được phép, đụng production hoặc tạo tác động không kiểm soát phải được xử lý theo quy định an toàn, dù bài viết và công cụ khác đúng.

## 22. Câu hỏi tự kiểm tra

### Câu 1 — Mục tiêu nào thực sự đo được?

A. “Hiểu hết bảo mật mạng.”  
B. “Cài mọi công cụ nổi tiếng.”  
C. “Trong lab có hai zone, tạo một positive và một negative test, lưu log policy và kết quả ứng dụng để đánh giá.”  
D. “Không thấy alert nghĩa là hệ thống an toàn.”

**Đáp án:** C. Vì xác định môi trường, hành vi, bằng chứng và kết quả kiểm thử. Các lựa chọn còn lại thiếu phạm vi và tiêu chí đo.

### Câu 2 — Có thể gọi negative test là PASS nếu client timeout?

**Gợi ý:** Không tự động. Cần chứng minh request tới đúng firewall/rule hoặc control point đã chặn; timeout có thể do route, server không chạy hoặc host firewall.

### Câu 3 — Có nhất thiết dùng cloud và Wi-Fi trong lab đầu tiên?

**Gợi ý:** Không. Công nghệ chỉ đưa vào khi phục vụ mục tiêu bắt buộc, có đủ tài nguyên, quyền và bằng chứng. Có thể tách thành giai đoạn mở rộng.

### Câu 4 — Một VM trong mạng 10.88.10.0/24 có mặc nhiên được phép test?

**Gợi ý:** Không. Địa chỉ private không đồng nghĩa quyền sử dụng. Phải kiểm chứng đó là VM sở hữu lab, được chỉ định trong scope và không route sang hệ thống thực.

### Câu 5 — Nếu IDS cảnh báo đúng sau khi nạp log replay, đã chứng minh firewall live chặn tấn công chưa?

**Gợi ý:** Chưa. Đó là kiểm chứng detector/parser với dữ liệu replay. Cần traffic test có phạm vi và bằng chứng firewall riêng để chứng minh enforcement.

### Câu 6 — Một yêu cầu “đặt luôn 20 subnet cho tương lai” có nên đưa vào scope L1?

**Gợi ý:** Không cần nếu không phục vụ mục tiêu hiện tại. Phân biệt khả năng mở rộng của IP plan với những subnet thật phải dựng, quản lý và kiểm thử.

### Câu 7 — Thay đổi scope có thể hợp lệ khi nào?

**Gợi ý:** Khi có lý do gắn mục tiêu, cập nhật inventory/ROE/risk/test/evidence, được owner phê duyệt và có phương án rollback; không nên mở rộng ngầm giữa phiên.

### Câu 8 — Tiêu chí nghiệm thu và mục tiêu học tập có giống nhau?

**Gợi ý:** Chúng liên hệ nhưng khác nhau. Hệ thống có thể FAIL một kiểm soát và người học vẫn đạt kỹ năng điều tra nếu xác định đúng nguyên nhân và chứng cứ; báo cáo phải ghi rõ cả hai trục.

## 23. Checklist chốt scope trước khi bắt đầu dựng lab

- [ ] Đã xác định mục tiêu học tập và kiểm soát cụ thể, có Test ID đi kèm.
- [ ] Mỗi mục tiêu Must có tiêu chí PASS và evidence tối thiểu.
- [ ] Danh sách in-scope gồm asset, IP, zone, protocol, dịch vụ, hoạt động và thời gian.
- [ ] Danh sách out-of-scope nêu rõ production, bên thứ ba, dữ liệu thật và hoạt động nguy hiểm.
- [ ] ROE xác định chủ sở hữu, phê duyệt, quyền thao tác và điều kiện dừng.
- [ ] Topology lab và virtual switch/bridge/NAT đã được review để bảo đảm cô lập.
- [ ] Có inventory asset và các quyền/credential tách khỏi production.
- [ ] Ranh giới tin cậy và threat hypotheses gắn với control/test rõ ràng.
- [ ] Ma trận lưu lượng có cả positive lẫn negative test và chiều phản hồi khi cần.
- [ ] Công cụ được chọn theo bằng chứng cần thu, không chỉ vì muốn cài.
- [ ] Log/PCAP/SIEM/DNS có timestamp, ID và quyền lưu trữ thích hợp.
- [ ] Có baseline network/service và phân biệt lỗi môi trường với lỗi chính sách.
- [ ] Các phụ thuộc, rủi ro và giới hạn tài nguyên đã có người chịu trách nhiệm.
- [ ] Có snapshot, đường quản trị và rollback/teardown đã kiểm tra.
- [ ] Có kế hoạch xử lý FAIL, INCONCLUSIVE và NOT RUN mà không làm sai lệch báo cáo.
- [ ] Mục tiêu mở rộng VPN, Wi-Fi, cloud hoặc IDS/IPS đã được ưu tiên và tách pha nếu cần.
- [ ] Báo cáo cuối có charter, topology, test matrix, evidence, kết quả và bài học.
- [ ] Không có traffic hoặc quyền truy cập nào vượt ra ngoài môi trường được cho phép.

**Kết luận:** đặt mục tiêu và phạm vi là bước thiết kế **khả năng kiểm chứng** của dự án thực hành bảo mật mạng. Một lab vừa sức, cô lập tốt và có ma trận bằng chứng rõ ràng thường dạy được nhiều hơn một hệ thống lớn nhưng không biết chính xác điều gì đã được kiểm tra. Khi mục tiêu, ranh giới, phép thử, dữ liệu quan sát và tiêu chí nghiệm thu được thống nhất ngay từ đầu, người học có nền tảng vững chắc để tiến đến các bài phân đoạn, firewall, VPN, DNS, IDS/IPS, Wi-Fi và cloud một cách an toàn, có hệ thống và có thể lặp lại.

