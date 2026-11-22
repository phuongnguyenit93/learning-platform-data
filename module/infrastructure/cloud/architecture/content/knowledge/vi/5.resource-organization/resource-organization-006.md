# Tài khoản dùng chung cho bảo mật, kết nối và ghi nhật ký

Khi hệ thống đám mây phát triển từ một ứng dụng thành nhiều môi trường, đội ngũ và sản phẩm, việc đặt tất cả tài nguyên vào một tài khoản trở nên khó kiểm soát. Một nhóm cần triển khai ứng dụng; nhóm khác phải điều tra sự cố; bộ phận an ninh cần xem dấu vết truy cập; đội nền tảng cần quản lý kết nối Internet, kết nối nội bộ và đường đến hệ thống tại chỗ. Nếu mọi quyền và tài nguyên trộn lẫn, lỗi cấu hình hoặc tài khoản bị xâm nhập có thể ảnh hưởng đến nhiều workload cùng lúc.

Một cách tổ chức phổ biến trong **cloud landing zone** là tạo các tài khoản hoặc đơn vị quản trị dùng chung (*shared accounts*) cho những năng lực xuyên suốt: **bảo mật**, **kết nối mạng** và **lưu trữ nhật ký tập trung**. Các workload vẫn có tài khoản riêng và chịu trách nhiệm về ứng dụng, nhưng nhận dịch vụ nền tảng theo các giao diện và chính sách đã công bố.

Trong bài học này, từ **tài khoản** được dùng theo nghĩa ranh giới quản trị tài nguyên cloud, không phải “một tên đăng nhập dùng chung”. Trên AWS đó có thể là account; trên Azure thường là subscription trong hệ thống management group và tenant; trên Google Cloud thường là project trong organization/folder. Các mô hình có điểm tương đồng về phân quyền, nhưng **không hoàn toàn tương đương về giới hạn dịch vụ, bảo mật và thanh toán**.

Bài học nằm trong phần **Tổ chức tài nguyên** của học phần thiết kế kiến trúc đám mây: biến yêu cầu nghiệp vụ thành lựa chọn mạng, compute, dữ liệu và triển khai; đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo nguyên tắc Well-Architected.

Sau bài học, bạn có thể:

- Giải thích vai trò và phạm vi của **Security**, **Network/Connectivity** và **Log Archive** accounts.
- Phân biệt tài khoản quản trị tổ chức, tài khoản dịch vụ nền tảng và tài khoản workload.
- Phác họa luồng kết nối, luồng ghi log và luồng cấp quyền xuyên tài khoản.
- Thiết kế ranh giới quyền tối thiểu, giảm khả năng sửa hoặc xóa nhật ký điều tra.
- Nhận diện điểm lỗi tập trung, chi phí, độ phức tạp và cách kiểm chứng từng quyết định.
- Đánh giá một thiết kế landing zone bằng câu hỏi Well-Architected và các thử nghiệm thực tế.

## 1. Vì sao cần tổ chức tài nguyên thành nhiều tài khoản?

Một tài khoản cloud chứa tài nguyên, chính sách truy cập, quota và cấu hình quản trị nhất định. Đặt môi trường production, development, công cụ security và hệ thống log trong cùng tài khoản có thể gây ra:

- **Phạm vi ảnh hưởng lớn:** thay đổi nhầm route, policy, key hoặc quota có thể tác động nhiều dịch vụ không liên quan.
- **Khó phân quyền:** để quản trị một thành phần, người dùng có thể được cấp quyền rộng hơn mức công việc yêu cầu.
- **Khó phân tách trách nhiệm:** nhóm vận hành ứng dụng cũng có thể sửa cơ chế audit hoặc xóa dấu vết điều tra.
- **Chi phí thiếu minh bạch:** khó phân biệt ngân sách workload với chi phí nền tảng dùng chung.
- **Khó thiết lập kiểm soát nhất quán:** các tài nguyên mới có thể thiếu logging, policy bảo mật và cấu hình mạng chuẩn.

Mục tiêu của **multi-account organization** là tạo ranh giới quản trị và trách nhiệm rõ ràng. Trong một kiến trúc hợp lý, workload production bị xâm nhập **không tự động có quyền** tắt kiểm toán của tổ chức hoặc sửa nhật ký đã lưu. Đội quản trị mạng được phép thay đổi kết nối được giao, nhưng không vì thế được đọc dữ liệu ứng dụng.

Tách account **không tự động bảo đảm cách ly tuyệt đối**. Quyền quản trị cấp tổ chức, trust relationship xuyên account, khóa mã hóa, mạng dùng chung, cấu hình policy và cách cấp danh tính vẫn cần được thiết kế và kiểm tra.

### So sánh ba mô hình tổ chức

| Mô hình | Ưu điểm | Giới hạn và trường hợp cần cân nhắc |
| --- | --- | --- |
| **Một tài khoản cho mọi thứ** | Khởi tạo nhanh, ít bước quản trị | Khó kiểm soát ảnh hưởng, phân quyền và chi phí khi quy mô tăng |
| **Tài khoản riêng cho workload, dịch vụ chung gom vào một tài khoản nền tảng** | Phân tách workload cơ bản, ít tài khoản nền tảng | SecOps, mạng và log vẫn có thể ảnh hưởng nhau hoặc chia sẻ quyền quá rộng |
| **Tài khoản riêng cho bảo mật, kết nối và lưu log** | Tách nhiệm vụ và quyền; dễ chuẩn hóa tài nguyên dùng chung | Cần tổ chức quyền, kết nối, triển khai, giám sát và cơ chế phối hợp xuyên account |

Không có số lượng tài khoản “chuẩn” cho mọi doanh nghiệp. Một ứng dụng thử nghiệm có thể chưa cần đầy đủ các account nền tảng, nhưng một hệ thống production xử lý dữ liệu nhạy cảm thường cần tách chức năng bảo vệ và dấu vết kiểm toán khỏi quyền của đội ứng dụng.

## 2. Sơ đồ tham chiếu: một tổ chức cloud có các tài khoản dùng chung

Ví dụ một doanh nghiệp có ứng dụng đặt lịch, cổng quản trị và dịch vụ báo cáo. Có thể tổ chức như sau:

~~~mermaid
flowchart TB
    ORG["Organization / Management hierarchy<br/>Quản trị tổ chức, guardrails, billing"]
    ID["Identity provider / SSO<br/>Danh tính cá nhân, MFA, nhóm quyền"]
    ORG --> SEC["Security account<br/>Phát hiện rủi ro, giám sát bảo mật"]
    ORG --> NET["Network account<br/>Hub, DNS, kết nối dùng chung"]
    ORG --> LOG["Log Archive account<br/>Nhận và bảo quản audit logs"]
    ORG --> P1["Workload: Booking Prod"]
    ORG --> P2["Workload: Admin Prod"]
    ORG --> NP["Workload: Nonprod"]
    ID -. "Cấp phiên, vai trò theo nguyên tắc tối thiểu" .-> SEC
    ID -. "Cấp phiên, vai trò theo nguyên tắc tối thiểu" .-> NET
    ID -. "Cấp phiên, vai trò theo nguyên tắc tối thiểu" .-> LOG
    ID -. "Cấp phiên, vai trò theo nguyên tắc tối thiểu" .-> P1
    ID -. "Cấp phiên, vai trò theo nguyên tắc tối thiểu" .-> P2
    ID -. "Cấp phiên, vai trò theo nguyên tắc tối thiểu" .-> NP
    P1 -. "Telemetry và audit" .-> LOG
    P2 -. "Telemetry và audit" .-> LOG
    NP -. "Telemetry và audit" .-> LOG
    SEC -. "Đọc/điều tra theo quyền" .-> LOG
    P1 -. "Kết nối theo route cho phép" .-> NET
    P2 -. "Kết nối theo route cho phép" .-> NET
    NP -. "Kết nối theo route cho phép" .-> NET
~~~

Sơ đồ thể hiện **các quan hệ logic**, không có nghĩa mọi packet ứng dụng phải đi qua Network account hoặc mọi loại log phải luôn có một hop mạng đến Log Archive. Dịch vụ cloud có thể cung cấp đường gửi log do chính nhà cung cấp quản lý; một luồng đọc/ghi nội bộ trong cùng workload vẫn có thể đi theo route cục bộ.

### Các vai trò nên phân biệt

| Nhóm tài khoản | Chức năng chính | Ai thường quản trị? | Điều không nên mặc nhiên có quyền |
| --- | --- | --- | --- |
| Organization / Management | Quản lý tổ chức, account, policy nền, thanh toán hoặc đăng ký dịch vụ | Nhóm nền tảng rất hạn chế | Vận hành ứng dụng hằng ngày hoặc truy vấn dữ liệu khách hàng |
| Security | Giám sát posture, vulnerability, threat finding, điều tra và điều phối ứng cứu | SecOps, cloud security | Thay đổi nghiệp vụ ứng dụng hoặc tự ý xóa log archive |
| Network / Connectivity | Kết nối giữa workload, DNS, đường đi hybrid, egress và các tài nguyên mạng chung | Platform/network team | Đọc secrets, dữ liệu database hoặc log nhạy cảm không phục vụ vận hành mạng |
| Log Archive | Nhận và bảo quản log theo chính sách retention/kiểm toán | Platform logging với quyền hạn chế; kiểm soát retention có giám sát | Cho workload quyền xóa log đã lưu |
| Workload Prod | Compute, database, queue, storage và cấu hình ứng dụng production | Đội sản phẩm và SRE theo phạm vi | Sửa chính sách tổ chức, xóa nhật ký audit tập trung |
| Workload Nonprod | Dev/test/staging hoặc môi trường thử nghiệm khác | Đội phát triển theo phạm vi | Truy cập dữ liệu thật hoặc quyền production mặc định |

Ở một số tổ chức, **Security Tooling** và **Log Archive** là hai account riêng để nhóm phát hiện/điều tra không mặc nhiên có toàn quyền với dữ liệu gốc. Ở tổ chức nhỏ, hai chức năng có thể cùng account nhưng vẫn phải tách vai trò, khóa và chính sách. Sự tách biệt nên phù hợp với rủi ro và khả năng vận hành thực tế.

## 3. Tài khoản bảo mật dùng chung: giám sát và phản ứng trên toàn tổ chức

Security account là nơi triển khai hoặc điều phối các năng lực bảo mật chung. Mục tiêu là có **góc nhìn xuyên workload** mà không cần cấp quyền quản trị toàn bộ cho từng nhân viên SecOps ở mỗi tài khoản sản phẩm.

### 3.1. Những năng lực thường tập trung

- **Security posture:** tập hợp phát hiện về cấu hình sai, chính sách không phù hợp, tài nguyên công khai, khóa hoặc chứng chỉ có vấn đề.
- **Threat detection:** cảnh báo hành vi bất thường từ hoạt động danh tính, mạng hoặc dịch vụ được hỗ trợ.
- **Vulnerability management:** tổng hợp điểm yếu của image, workload, máy ảo, thư viện hoặc cấu hình theo công cụ sử dụng.
- **Security findings và workflow:** phân loại, giao chủ sở hữu, mức ưu tiên, theo dõi xử lý, liên kết tài liệu chứng cứ.
- **Incident response:** quyền truy cập khẩn cấp theo quy trình, khả năng cô lập nguồn gây hại hoặc thu thập chứng cứ khi cần.
- **Compliance reporting:** báo cáo trạng thái guardrail, mã hóa, logging, cấu hình định kỳ và ngoại lệ đã phê duyệt.

Không nhất thiết mọi công cụ đều phải *chạy* trong Security account; một số dịch vụ được bật ở từng tài khoản workload và **gửi findings về trung tâm**. Điều quan trọng là ownership và quyền truy cập rõ ràng.

### 3.2. Tách nhiệm vụ theo nguyên tắc quyền tối thiểu

Thiết kế nên xác định:

1. **Quyền phát hiện/đọc:** SecOps đọc finding, cấu hình và một phần log phục vụ điều tra; không đồng nghĩa có quyền đọc toàn bộ dữ liệu khách hàng.
2. **Quyền thay đổi:** một vài runbook có thể cần cách ly instance, chặn policy hoặc thu hồi credential; sử dụng quyền được cấp chính xác cho từng hành động, ưu tiên quy trình có phê duyệt nếu tác động lớn.
3. **Quyền lưu và bảo vệ chứng cứ:** bộ phận phát hiện không nên mặc nhiên sửa/xóa audit log gốc. Cần quy trình chain of custody và retention.
4. **Quyền quản trị tổ chức:** giữ trong nhóm được giao quyền rất hạn chế, không cấp đại trà để tiện tích hợp.

Ví dụ, một kỹ sư SecOps được xem security findings của Booking Prod và tạo ticket xử lý; kỹ sư đó **chưa cần** có quyền xóa database lịch hẹn. Một tài khoản ứng dụng bị xâm nhập cũng không nên được quyền vô hiệu hóa logging của các tài khoản khác.

### 3.3. Tổ chức danh tính và quyền xuyên account

Nên dùng identity provider / SSO phù hợp, xác thực đa yếu tố (MFA), vai trò ngắn hạn và phân quyền theo nhóm công việc. Tránh chia sẻ tài khoản root, owner hoặc credential tĩnh giữa nhiều người.

Các nguyên tắc cốt lõi:

- **Least privilege:** người và workload chỉ có các hành động trên tài nguyên thật sự cần.
- **Separation of duties:** đội triển khai ứng dụng, người quản trị mạng, người kiểm tra bảo mật và người thay retention log có phạm vi quyền khác nhau.
- **Just-in-time hoặc quyền theo phiên:** nâng quyền trong thời gian cần thiết, có ghi nhận và hết hạn.
- **Break-glass:** đường truy cập khẩn cấp được bảo vệ, giám sát và diễn tập; không biến nó thành tài khoản dùng hằng ngày.
- **Guardrails:** ràng buộc cấp tổ chức ngăn cấu hình rủi ro trong khả năng nền tảng hỗ trợ; một guardrail áp dụng không đúng phạm vi có thể làm gián đoạn production.

**Ví dụ kỹ thuật:** AWS có thể sử dụng AWS Organizations, IAM roles, service control policies (SCP) và delegated administrator cho một số dịch vụ bảo mật; Azure sử dụng Entra ID, management groups, Azure RBAC và policy; Google Cloud sử dụng organization/folder/project, IAM và organization policies. Cách tích hợp cụ thể tùy dịch vụ và vùng, không thể chỉ “dịch” tên role giữa các cloud.

### 3.4. Rủi ro của việc tập trung bảo mật

Security account có góc nhìn và quyền rộng, vì vậy **bản thân nó là mục tiêu có giá trị cao**. Cần kiểm soát role assumption, quyền automation, secret và khóa; lưu audit của thao tác quản trị. Một playbook tự động cô lập sai đối tượng cũng có thể làm hệ thống production gián đoạn.

Phương án thiết kế tốt có bước đối chiếu môi trường, tài nguyên, mức độ tin cậy của finding và phạm vi tác động trước khi kích hoạt biện pháp mạnh. Bảo mật tự động cần khả năng dừng, theo dõi và khôi phục.

## 4. Tài khoản kết nối dùng chung: quản lý đường đi, không quản lý nghiệp vụ

Network account tập trung **các năng lực kết nối dùng chung** cho nhiều workload: mạng hub, cổng kết nối, dịch vụ DNS, quản lý IP, egress hoặc kết nối từ cloud đến văn phòng/data center.

### 4.1. Mô hình hub-and-spoke

~~~mermaid
flowchart TD
    OFF["Hệ thống tại chỗ / đối tác"] --- VPN["VPN / dedicated private connectivity"]
    VPN --- HUB["Network hub<br/>Routing, kiểm soát luồng, DNS dùng chung"]
    HUB --- PROD["Spoke VPC/VNet: Booking Prod"]
    HUB --- ADMIN["Spoke VPC/VNet: Admin Prod"]
    HUB --- TEST["Spoke VPC/VNet: Nonprod"]
    PROD --- DB["Database riêng của Booking"]
    HUB --- EGRESS["Egress/inspection theo chính sách"]
    EGRESS --> INTERNET["Internet / external APIs"]
~~~

Mạng hub có thể dùng các dịch vụ kết nối của nhà cung cấp như transit gateway, virtual WAN/hub, network connectivity center hoặc Shared VPC theo mô hình tương ứng. Chúng **không phải các dịch vụ hoán đổi trực tiếp**; cần xét route, số lượng kết nối, băng thông, DNS, ranh giới quyền và khả năng mở rộng.

Ở phương án hub-and-spoke, workload sở hữu mạng hoặc phân đoạn mạng phục vụ riêng cho mình, còn đội nền tảng điều phối kết nối dùng chung. Traffic **chỉ đi qua hub nếu route và kiến trúc yêu cầu**. Lưu lượng từ ứng dụng đến database cùng VPC/VNet có thể giữ tại chỗ. Không nên buộc mọi giao tiếp nội bộ đi qua một gateway tập trung nếu không có nhu cầu kiểm soát cụ thể.

### 4.2. Những vấn đề phải quyết định trước

| Quyết định | Câu hỏi thiết kế | Rủi ro khi bỏ qua |
| --- | --- | --- |
| IP addressing | CIDR có chồng lấn khi nối nhiều workload hoặc on-premise? | Không định tuyến được hoặc phải NAT phức tạp |
| Segmentation | Prod có thể kết nối Nonprod không? Workload A được gọi workload B qua giao thức nào? | Di chuyển ngang khi bị xâm nhập |
| Routing | Luồng nào trực tiếp, qua hub, qua firewall hoặc qua private endpoint? | Route bất đối xứng, tăng độ trễ, mất kết nối |
| DNS | Ai sở hữu zone private, resolver và bản ghi chia sẻ? | Phân giải sai tên, khó xử lý lỗi |
| Egress | Workload được ra Internet qua đâu, với giới hạn nào? | Rò rỉ dữ liệu, chi phí NAT/egress cao |
| Ingress | Public endpoint nào cần WAF/CDN/LB, TLS được kết thúc ở đâu? | Mở bề mặt tấn công không cần thiết |
| Hybrid | Kết nối đến on-premise dùng VPN hay đường riêng, có dự phòng? | Một đường kết nối trở thành điểm lỗi |
| Observability | Có flow log, route change log, network metric, cảnh báo và runbook không? | Khó xác định sự cố nằm ở app, DNS hay route |

**IPAM (IP Address Management)** có ích khi tổ chức lớn và thường xuyên cấp mạng mới. Dùng bảng quy hoạch CIDR, quy trình duyệt và tự động cấp phát phù hợp để tránh trùng dải giữa account và môi trường.

### 4.3. Shared VPC, hub-and-spoke và tài khoản mạng không phải một khái niệm

Với **Google Cloud Shared VPC**, host project sở hữu mạng dùng chung và service projects dùng subnet theo quyền được cấp. Với **Azure**, mô hình hub-and-spoke thường bố trí hub VNet ở một subscription kết nối và spoke VNets ở subscription workload. Với **AWS**, một network account có thể sở hữu kết nối trung tâm như transit gateway; các workload có VPC riêng và kết nối theo chính sách. Có nền tảng cũng hỗ trợ chia sẻ subnet hoặc tài nguyên mạng ở các phạm vi khác nhau.

Chọn mô hình dựa vào **ai sở hữu cấu hình mạng**, **độ tự chủ của đội sản phẩm**, **cách cách ly prod/nonprod** và **giới hạn của dịch vụ**. Không kết luận rằng “tất cả dịch vụ sẽ có cùng mô hình subnet, route hoặc IAM” khi chuyển nhà cung cấp.

### 4.4. Tránh điểm lỗi và nút thắt tập trung

Một firewall, NAT gateway, DNS resolver hay đường VPN chung có thể trở thành **single point of failure** hoặc điểm nghẽn chi phí/băng thông. Thiết kế dự phòng theo availability zone, region và chính sách định tuyến thực tế; đo failover và cảnh báo. Sử dụng dịch vụ managed có tính sẵn sàng cao không bảo đảm cấu hình tuyến, cặp tunnel hoặc vùng triển khai của khách hàng đã có dự phòng đúng.

Không nên xem Network account là nơi đội mạng được toàn quyền vào các database workload. Quyền thay route và kiểm tra flow log khác với quyền đọc nội dung giao dịch, secrets hay mã nguồn.

## 5. Tài khoản lưu nhật ký tập trung: bảo quản bằng chứng và hỗ trợ điều tra

Log Archive account nhận và lưu các loại nhật ký cần giữ lâu dài để **kiểm toán, điều tra, đáp ứng nghĩa vụ bảo mật và phục hồi bối cảnh khi có sự cố**. Nó thường tách khỏi nền tảng tìm kiếm/phân tích log nhằm hạn chế sửa, xóa chứng cứ gốc.

### 5.1. Những nhóm log cần cân nhắc

| Nhóm log | Ví dụ nội dung | Mục tiêu |
| --- | --- | --- |
| Control plane audit | Tạo/xóa tài nguyên, sửa role, policy, cấu hình mạng | Truy vết ai làm gì, khi nào, ở đâu |
| Identity & authentication | Đăng nhập, cấp phiên, thao tác quyền, hành vi thất bại | Phát hiện chiếm đoạt tài khoản và lạm dụng quyền |
| Network | Flow log, DNS query log, firewall decision nếu cần | Điều tra lưu lượng, egress bất thường, lỗi kết nối |
| Security findings | Cảnh báo posture, threat, vulnerability, quyết định ứng cứu | Theo dõi rủi ro và xử lý sự cố |
| Application & database audit | Truy cập API nhạy cảm, thay đổi nghiệp vụ, audit DB | Kiểm toán hành vi ứng dụng theo yêu cầu |
| Deployment & configuration | Sự kiện deploy, thay đổi IaC, kết quả kiểm tra | Liên hệ sự cố với thay đổi hệ thống |

Không phải mọi debug log, trace hoặc metric đều phải giữ lâu trong cùng kho audit. Có thể có **observability account/workspace** để truy vấn nhanh, và **log archive riêng** cho bản gốc cần bảo quản theo chính sách. Tách **mục đích sử dụng** giúp tối ưu quyền truy cập, retention và chi phí.

### 5.2. Luồng thu thập và bảo vệ log

~~~mermaid
flowchart LR
    W1["Workload Prod"] --> PIPE["Dịch vụ thu thập/chuyển log"]
    W2["Workload Nonprod"] --> PIPE
    CONTROL["Organization audit / Security events"] --> PIPE
    PIPE --> STORE["Log Archive<br/>Storage, encryption, retention"]
    STORE -. "Quyền đọc có kiểm soát" .-> SEC["Security investigation"]
    PIPE --> QUERY["Observability / SIEM<br/>Tìm kiếm, phân tích, cảnh báo"]
    SEC --> CASE["Incident record / evidence"]
~~~

Một số dịch vụ log có thể gửi trực tiếp đến đích được ủy quyền, không cần một hệ thống PIPE tự xây. Sơ đồ chỉ mô tả **luồng trách nhiệm**: nguồn phát → thu thập/chuyển tiếp → kho lưu trữ và công cụ phân tích.

Với các log quan trọng:

- **Bật thu thập ở phạm vi tổ chức hoặc tài khoản phù hợp**, tự áp dụng cho account mới khi nền tảng hỗ trợ; kiểm tra các region, loại sự kiện và data events cần thiết.
- **Hạn chế quyền ghi:** bên gửi chỉ được thêm sự kiện qua đường được cho phép, không được xóa hoặc sửa sự kiện cũ.
- **Hạn chế quyền quản trị kho:** thiết lập chính sách retention, versioning và bất biến/khóa đối tượng khi cần và khi dịch vụ hỗ trợ; tách người cấu hình với người sử dụng.
- **Mã hóa khi truyền và khi lưu:** kiểm soát cả key policy và quyền giải mã. Nếu dùng khóa tự quản, phải đảm bảo quy trình rotation, recovery và quyền của dịch vụ ghi log.
- **Gắn nguồn gốc rõ ràng:** organization, account/project/subscription, region, resource, timestamp, loại sự kiện, request/trace ID khi có.
- **Theo dõi chính pipeline:** cảnh báo khi nguồn ngừng phát, delivery thất bại, backlog tăng, sink bị thay đổi hoặc log bị thiếu so với baseline.
- **Quản lý vòng đời:** phân biệt dữ liệu cần truy vấn nhanh với archive dài hạn, có thời hạn lưu và cơ chế xóa hợp lệ.

Từ “immutable” cần sử dụng chính xác: một bucket có versioning chưa chắc đã đáp ứng yêu cầu WORM hoặc ngăn chủ sở hữu có đặc quyền xóa trước hạn. Hiệu quả phụ thuộc cấu hình object lock/retention, quyền, chính sách pháp lý và khả năng thay đổi khóa. Cần kiểm tra hành vi thực tế với các vai trò có quyền cao, trong phạm vi an toàn.

### 5.3. Phân quyền để workload không thể xóa chứng cứ

Một mô hình quyền có thể là:

| Vai trò | Gửi log mới | Đọc log | Đổi retention | Xóa log trước hạn |
| --- | --- | --- | --- | --- |
| Workload runtime | Theo quyền và kênh được chỉ định | Chỉ phần được cấp, thường không cần log gốc toàn tổ chức | Không | Không |
| Central log ingestion | Có | Chỉ metadata/trạng thái cần vận hành | Không | Không |
| Security analyst | Không cần | Có theo phạm vi điều tra và kiểm soát nhạy cảm | Không | Không |
| Log platform admin | Theo công việc | Hạn chế | Có thể theo quy trình được phê duyệt | Bị hạn chế bởi retention/guardrail |
| Auditor | Không | Chỉ đọc, có lưu vết truy vấn | Không | Không |

Quyền thực tế phụ thuộc dịch vụ, chính sách retention, encryption key và mô hình truy cập. **Tách account thôi chưa đủ**: nếu một role cấp tổ chức vẫn có thể gỡ retention hoặc vô hiệu hóa log, tổ chức cần kiểm soát đặc biệt với role đó.

### 5.4. Nhật ký có thể chứa dữ liệu nhạy cảm

Log đôi khi vô tình chứa token, email, số điện thoại, địa chỉ IP, payload yêu cầu hoặc dữ liệu cá nhân. Kho tập trung vì thế có thể trở thành nơi chứa lượng dữ liệu nhạy cảm lớn.

Trước khi gửi, cần xác định data classification, che thông tin nhạy cảm, quy định thời gian lưu, quyền truy vấn và khu vực lưu dữ liệu. Đối với ứng dụng đặt lịch, nên ghi **mã sự kiện**, **mã yêu cầu**, **mã lịch hẹn được kiểm soát**, **thời điểm** và **kết quả**, tránh mặc định log toàn bộ thông tin cá nhân hay nội dung token.

Tập trung log từ nhiều region không được vi phạm ràng buộc data residency. Một tổ chức có thể cần **kho log theo vùng địa lý hoặc loại dữ liệu**, cộng với tầng tổng hợp chỉ chứa metadata được phép.

## 6. Tách nhiệm vụ giữa ba tài khoản như thế nào?

Một nguyên tắc quan trọng: **Security phát hiện và điều tra; Network cung cấp kết nối; Log Archive bảo quản dấu vết.** Ba chức năng phối hợp nhưng không mặc định quản trị thay nhau.

Ví dụ khi có cảnh báo API đặt lịch gửi lưu lượng bất thường:

1. Workload tạo application log và network flow log. Cơ chế thu thập gửi dữ liệu tới Log Archive hoặc hệ thống phân tích theo cấu hình.
2. Security account tổng hợp finding với tài nguyên nguồn, account, thời gian và mức ảnh hưởng, rồi mở incident.
3. Security analyst truy vấn log đã được cấp quyền, xác nhận dấu hiệu. Người điều phối đánh giá mức tác động nghiệp vụ nếu cô lập workload.
4. Network team triển khai chặn egress hay cô lập segment **nếu đây là biện pháp đã được duyệt**; đội ứng dụng có thể thu hồi credential hoặc thay cấu hình.
5. Log Archive tiếp tục giữ bản chứng cứ theo retention; các quyền điều tra và thao tác khẩn cấp được ghi lại.
6. Sau sự cố, đội ngũ review guardrail, alert, cấu hình mạng và khả năng phục hồi để tránh tái diễn.

Nếu cùng một danh tính có thể thay route, tắt logging, xóa log gốc và xóa tài nguyên ứng dụng mà không cần kiểm soát bổ sung, mục tiêu phân tách nhiệm vụ đã bị suy yếu dù tài nguyên nằm ở ba tài khoản khác nhau.

### Bảng quyền liên tài khoản để thảo luận

| Chủ thể / tài nguyên | Security | Network | Log Archive | Workload Prod |
| --- | --- | --- | --- | --- |
| SecOps analyst | Đọc findings, điều phối incident | Xem cấu hình cần điều tra | Đọc log theo phạm vi | Đọc metadata được duyệt |
| Network engineer | Xem ticket liên quan | Quản trị kết nối được giao | Xem flow log cần thiết | Không quản trị database |
| Log platform operator | Xem tình trạng pipeline | Chỉ quyền mạng cần thiết | Quản trị ingest và lưu trữ theo quy trình | Không triển khai ứng dụng |
| Application team | Xem findings của mình | Gửi yêu cầu thay route | Gửi log, xem phần log của mình | Triển khai và vận hành theo vai trò |
| Organization administrator | Quản trị bảo vệ cấp tổ chức theo phân quyền | Quyền khẩn cấp có kiểm soát | Quyền đặc biệt theo quy trình | Quyền đặc biệt theo quy trình |

Bảng này là **mẫu chính sách mong muốn**, không phải ma trận IAM triển khai trực tiếp. Khi hiện thực hóa, cần xác định chính xác resource ID, action, điều kiện, trust policy, permission boundary, thời gian hiệu lực và bằng chứng audit.

## 7. Tổ chức chính sách cấp cao và account vending

Landing zone có hiệu quả khi tài khoản workload mới nhận được **cấu hình nền nhất quán ngay từ lúc tạo**.

Một quy trình cấp tài khoản (*account vending*) thường gồm:

1. Đề nghị account theo thông tin bắt buộc: tên workload, môi trường, chủ sở hữu, mức dữ liệu, khu vực, ngân sách và mục tiêu vận hành.
2. Tạo account/subscription/project dưới cấu trúc tổ chức phù hợp, không để tài nguyên production trôi nổi bên ngoài khu vực quản lý.
3. Gắn chính sách nền: region được phép, hạn chế tài nguyên công khai, encryption, tag/label, danh tính và cơ chế theo dõi thay đổi.
4. Đăng ký bảo mật trung tâm: threat detection, posture, inventory và cách đưa finding về Security.
5. Bật audit/log forwarding theo quy định và xác nhận sự kiện thử đã tới Log Archive.
6. Cấp kết nối mạng nếu cần: CIDR/subnet, route, DNS, private endpoint, firewall; mặc định từ chối những luồng chưa được duyệt.
7. Cấp ngân sách, cảnh báo, dashboard và quyền cho đội ứng dụng; lưu cấu hình bằng IaC.
8. Kiểm tra tự động hoặc đối soát cấu hình, ghi trạng thái bàn giao và chủ sở hữu.

**Guardrail phòng ngừa** giới hạn việc cấu hình nguy hiểm được phép thực hiện; **guardrail phát hiện** phát hiện thay đổi không hợp lệ sau khi đã xảy ra. Thường cần cả hai. Một số kiểm soát không thể diễn đạt bằng policy cấp tổ chức, mà phải dùng workflow, công cụ kiểm tra hoặc cấu hình trong ứng dụng.

Các chính sách cần có **quy trình ngoại lệ**: lý do nghiệp vụ, phạm vi tài nguyên, người phê duyệt, thời hạn và biện pháp bù trừ. Nếu không, đội ứng dụng có thể tìm cách vượt kiểm soát để kịp tiến độ.

## 8. Minh họa trên AWS, Azure và Google Cloud

Ba hệ sinh thái đều hỗ trợ các mô hình quản trị nhiều ranh giới, nhưng cách thực hiện khác nhau. Bảng dưới đây là **ánh xạ khái niệm**, không phải hướng dẫn cấu hình có thể áp dụng nguyên xi.

| Năng lực | AWS (ví dụ) | Microsoft Azure (ví dụ) | Google Cloud (ví dụ) |
| --- | --- | --- | --- |
| Cấu trúc tổ chức | AWS Organizations, organizational units, accounts | Entra tenant, management groups, subscriptions, resource groups | Organization, folders, projects |
| Phân quyền nền | IAM/roles, SCP và cơ chế kiểm soát dịch vụ tương ứng | Azure RBAC, Azure Policy, quyền Entra theo mục đích | IAM, organization policies |
| An ninh tập trung | Delegated admin/aggregation cho dịch vụ bảo mật được hỗ trợ; Security Hub, GuardDuty | Defender for Cloud, Defender plans, Sentinel và workspace phù hợp | Security Command Center và tổ chức findings |
| Kết nối dùng chung | Network account, VPC, Transit Gateway, Route 53 Resolver, private connectivity | Connectivity subscription, hub VNet/Virtual WAN, Private DNS, ExpressRoute | Host project/Shared VPC, Cloud DNS, Network Connectivity Center, Cloud Interconnect |
| Audit/logging | Organization CloudTrail và CloudWatch/S3 theo nhu cầu | Activity Log, diagnostic settings, Azure Monitor, Log Analytics hoặc storage | Cloud Audit Logs, Cloud Logging aggregated sinks/buckets |
| IaC và tự động hóa | CloudFormation/Terraform/CDK theo lựa chọn | Bicep/ARM/Terraform theo lựa chọn | Terraform/Infrastructure Manager theo lựa chọn |

Một số điểm cần nhớ:

- **AWS:** quản trị organization account phải được bảo vệ đặc biệt. Có thể dùng dedicated Security account và Log Archive account; account mạng sở hữu các cấu phần kết nối được chia sẻ cho workload. Kiểm tra phạm vi region và loại log khi cấu hình.
- **Azure:** management group tạo tầng áp chính sách lên subscriptions; identity gắn với Entra tenant. Azure subscription là ranh giới quản trị và thanh toán quan trọng, còn resource group là phạm vi tổ chức tài nguyên **bên trong subscription**. Workspace quan sát và nơi archive log có thể đặt ở subscription phù hợp.
- **Google Cloud:** project là ranh giới quản trị và quota phổ biến; Shared VPC có host project và service projects. Organization/folder-level logging sinks có thể giúp tổng hợp log theo yêu cầu, nhưng phải kiểm tra quyền đích nhận, phạm vi log và policy tổ chức.

Tên dịch vụ và tính năng có thể thay đổi theo thời gian. Khi triển khai thật, kiểm tra tài liệu của nhà cung cấp cho region, quota, IAM, khả năng cross-account và điều khoản dịch vụ đang áp dụng.

## 9. Một ví dụ đầy đủ: nền tảng đặt lịch nhiều đội phát triển

Giả sử doanh nghiệp vận hành ba sản phẩm: Booking, Admin Portal và Analytics. Hệ thống có production và nonproduction, dữ liệu lịch hẹn là dữ liệu nghiệp vụ quan trọng, đội an ninh cần điều tra hành vi đăng nhập bất thường và đội nền tảng quản trị đường nối từ cloud đến hệ thống kế toán tại chỗ.

### Yêu cầu đầu vào

| Yêu cầu | Hàm ý với tổ chức tài nguyên |
| --- | --- |
| Mỗi đội sản phẩm triển khai độc lập | Tách workload account; quyền deploy theo phạm vi |
| Production không được phụ thuộc tùy tiện vào test | Tách account/mạng/quyền giữa prod và nonprod |
| Có thể điều tra thao tác quản trị đáng ngờ | Audit xuyên account, Log Archive bảo quản chứng cứ |
| Cần kết nối bảo mật tới hệ thống tại chỗ | Network account quản trị VPN/private connection, DNS, route |
| Chặn truy cập trái phép và phát hiện misconfiguration | Security account tổng hợp findings; guardrail tổ chức |
| Biết chi phí mỗi sản phẩm và chi phí nền tảng | Cost allocation theo account, tag, dịch vụ chung |
| Có quy trình xử lý sự cố và phục hồi | Runbook và kiểm thử liên account; trách nhiệm rõ |

### Phân chia tài khoản tham khảo

~~~text
Organization / Tenant
├── Management / Governance
├── Security Tooling
├── Log Archive
├── Network / Connectivity
├── Workloads / Production
│   ├── Booking Prod
│   ├── Admin Prod
│   └── Analytics Prod
└── Workloads / Nonproduction
    ├── Booking Nonprod
    ├── Admin Nonprod
    └── Analytics Nonprod
~~~

Đây là ví dụ, không phải danh sách bắt buộc. Có thể cần thêm account cho backup, observability, sandbox hoặc nghiệp vụ có yêu cầu tuân thủ riêng. Ngược lại, một công ty nhỏ có thể bắt đầu với số account ít hơn, nhưng vẫn cần quyết định rõ quyền và audit ở production.

### Luồng đặt lịch trong hoạt động bình thường

1. Khách hàng gọi Booking API được triển khai ở **Booking Prod**; public ingress chỉ mở các endpoint được công bố, có TLS và kiểm soát truy cập thích hợp.
2. Booking API ghi transaction xuống database do Booking Prod sở hữu. Luồng API → DB không bắt buộc qua Network hub khi ở cùng mạng và route phù hợp.
3. Workload cần gọi hệ thống kế toán on-premise thì đi qua kết nối được cấp bởi **Network account**; chỉ route và cổng được cho phép.
4. Thao tác cloud control plane, thay đổi chính sách và các audit event cần thiết được gửi tới **Log Archive**. Log debug phục vụ đội ứng dụng có thể lưu/truy vấn riêng theo chính sách.
5. **Security account** nhận findings từ các tài khoản sản phẩm; nhân viên an ninh có thể truy cập log đã được ủy quyền để điều tra.
6. Bộ phận tài chính nhận báo cáo chi phí theo workload, cùng phần chi phí mạng, bảo mật và lưu log dùng chung có quy tắc phân bổ.

### Khi một tài khoản workload bị xâm nhập

Giả sử credential của workload bị lộ. Thiết kế phải giúp giới hạn thiệt hại:

- Role của workload chỉ có quyền cần cho Booking; không được cấp quyền thay IAM toàn tổ chức.
- Workload có thể tiếp tục phát sinh audit event theo cơ chế hiện hành, nhưng không được xóa log gốc ở Log Archive.
- Security có tín hiệu để phát hiện và runbook cô lập danh tính/tài nguyên; các thao tác khẩn cấp có audit.
- Network giới hạn các luồng kết nối giữa Booking Prod và các mạng khác theo chính sách, giảm phạm vi di chuyển ngang.
- Sau sự cố, dữ liệu log gốc và cấu hình trước/sau giúp đối soát phạm vi ảnh hưởng.

**Giới hạn cần nhìn nhận:** nếu attacker kiểm soát nguồn phát log hoặc tắt dịch vụ trước khi log được gửi, kho log tập trung không thể tái tạo sự kiện chưa bao giờ được tạo hoặc chuyển đi. Vì vậy cần kiểm soát ở nguồn, dịch vụ audit cấp tổ chức, giám sát độ trễ/thiếu log và điều tra từ nhiều nguồn.

## 10. Thiết kế độ tin cậy, hiệu năng và khả năng mở rộng cho dịch vụ chung

Tập trung quyền quản trị không có nghĩa phải **tập trung mọi data path vào một máy chủ hoặc region**. Một dịch vụ dùng chung gặp sự cố có thể tác động nhiều ứng dụng, nên cần phân biệt **management plane** với **data plane**.

| Thành phần | Sự cố giả định | Điều phải kiểm chứng |
| --- | --- | --- |
| Kết nối mạng trung tâm | Một gateway/tunnel/zone không khả dụng | Workload nào mất kết nối? Route dự phòng và thời gian chuyển tải có đạt mục tiêu? |
| DNS chung | Resolver hoặc forwarding rule lỗi | Dịch vụ nào không phân giải tên? Có dự phòng, cache hoặc giải pháp thay thế phù hợp? |
| Log ingest | Pipeline delay hoặc quota vượt ngưỡng | Log có được buffer/retry? Có cảnh báo trễ và đối soát số sự kiện? |
| Log archive | Lỗi đích hoặc quyền ghi/khóa bị thay | Có cảnh báo mất dữ liệu, dữ liệu tạm và khả năng phục hồi khi ghi trở lại? |
| Security tools | Aggregation hoặc notification không hoạt động | Workload còn vận hành? Đội phản ứng biết findings bị trễ qua kênh nào? |
| Identity/SSO | SSO bị gián đoạn | Người vận hành có phương án break-glass an toàn và kiểm chứng được? |
| Policy tổ chức | Áp rule sai phạm vi | Có kiểm thử trên sandbox, cơ chế roll out và revert không? |

**Chỉ tiêu minh họa:** đội nền tảng có thể đặt SLO cho pipeline audit như “99,9% sự kiện đủ điều kiện tới kho tiếp nhận trong 5 phút, xét trên một tháng”, cùng cảnh báo theo nguồn khi log ngừng đến. Đây là ví dụ đặt SLO, **không phải khả năng mặc định của bất kỳ dịch vụ**; phải đo được tổng sự kiện đầu vào, độ trễ và tỷ lệ thất bại.

Nếu nghiệp vụ yêu cầu khôi phục kết nối trong 30 phút (RTO), đội mạng phải chứng minh điều đó qua diễn tập. Nếu yêu cầu log không thất lạc, cần cơ chế delivery/buffer bền vững và giải thích semantics (ví dụ at-least-once có khả năng trùng), không dựa vào câu “log đã bật nên an toàn”.

### Bài toán multi-region

Tài khoản chung có thể quản lý tài nguyên ở nhiều region nếu nền tảng cho phép; nhưng một network hub ở region A không tự cung cấp đường đi tối ưu hoặc dự phòng cho region B. Đồng thời, tập trung log về một region có thể vướng data residency, phí truyền dữ liệu và yêu cầu phục hồi. Có thể cần mô hình **điểm thu thập theo vùng**, **kho lưu dữ liệu theo vùng**, còn **bảng tổng hợp bảo mật** chứa metadata ở mức được phép.

## 11. Chi phí của các tài khoản dùng chung

Tách tài khoản thường không tự tạo chi phí tài nguyên cố định theo kiểu “mỗi account trả một giá giống nhau”; hóa đơn chủ yếu đến từ **dịch vụ và mức sử dụng**. Tuy nhiên, kiến trúc nhiều tài khoản tạo thêm công quản trị và có thể phát sinh các dịch vụ chung phải chạy thường trực.

Các nhóm chi phí thường bị bỏ sót:

- **Network:** transit/attachment, VPN, gateway, NAT, firewall inspection, DNS resolver, dữ liệu qua zone/region và egress Internet.
- **Logging:** ingestion, forwarding, storage, replication, archive, retention, query, SIEM và data transfer.
- **Security:** scanning, threat detection, configuration monitoring, event analysis, đội ngũ ứng cứu.
- **Operations:** account provisioning, IaC, policy testing, patching công cụ tự quản, trực sự cố, cải tiến runbook.
- **Nonprod và kiểm thử:** môi trường diễn tập routing, log delivery, DR và ứng cứu.

### Ước tính lưu trữ log trước khi chọn retention

Giả sử tổ chức phát sinh **20 GB log/ngày**, giữ **30 ngày** ở lớp dễ truy vấn và thêm **335 ngày** ở archive. Nếu dung lượng không đổi, chưa tính nén, bản sao, index và overhead:

~~~text
Hot storage:       20 GB/ngày × 30 ngày  = 600 GB
Archive storage:   20 GB/ngày × 335 ngày = 6.700 GB
Tổng dữ liệu gốc giữ 365 ngày           = 7.300 GB ≈ 7,3 TB
~~~

Đây chỉ là **ước lượng dung lượng gốc**, không phải dự báo giá. Hóa đơn phụ thuộc cách tính phí lưu trữ, ingest, truy vấn, bản sao, nén và truyền dữ liệu. Đặc biệt cần đánh giá tác động của log debug ồn ào và việc ghi trùng nhiều pipeline.

### Phân bổ chi phí dùng chung

Có thể phân bổ theo:

| Loại chi phí | Phương án phân bổ có thể dùng | Điều cần lưu ý |
| --- | --- | --- |
| Logging | Khối lượng log theo account/workload hoặc mức ingest | Cần hạn chế khuyến khích tắt log quan trọng để tiết kiệm |
| Network egress | Lưu lượng theo workload/đường truyền có telemetry | Một số khoản phí chung khó ánh xạ chính xác |
| Security tooling | Số tài nguyên, mức dùng hoặc ngân sách nền tảng chung | Không tạo động cơ tránh kiểm soát bảo mật |
| Shared operations | Ngân sách platform hoặc cơ chế phân bổ nội bộ | Công bố cách phân bổ và người chịu trách nhiệm |

Đội sản phẩm nên biết phần chi phí do quyết định của mình tạo ra. Đội nền tảng nên có dashboard cho **tổng chi phí hạ tầng chung**, cảnh báo tăng trưởng bất thường và chính sách tối ưu dựa trên dữ liệu thực tế.

## 12. Những sai lầm thiết kế phổ biến

**1. Gộp “tài khoản dùng chung” với “credential dùng chung”.** Shared account là ranh giới chứa dịch vụ nền tảng; mỗi người và mỗi workload vẫn phải có danh tính và quyền riêng.

**2. Tách account nhưng cấp quyền quản trị chéo quá rộng.** Việc mọi workload đều có role có thể xóa log archive phá vỡ mục tiêu bảo vệ bằng chứng.

**3. Cho mọi traffic đi qua một hub duy nhất.** Tăng điểm lỗi, độ trễ và chi phí; cần quyết định đường đi theo luồng dữ liệu và yêu cầu kiểm soát cụ thể.

**4. Tập trung log nhưng không kiểm tra tính đầy đủ.** Dashboard có dữ liệu không chứng minh mọi account, region và loại event đều đang được thu. Cần inventory nguồn và cảnh báo khi thiếu.

**5. Lưu log dài hạn không có data classification.** Token, thông tin cá nhân và dữ liệu không được phép lưu xuyên vùng có thể tạo rủi ro lớn hơn lợi ích điều tra.

**6. Coi dịch vụ security managed là đủ bảo mật.** Vẫn phải cấu hình onboarding, permissions, coverage, cảnh báo, phân loại findings và quy trình ứng cứu.

**7. Chính sách tổ chức chặn production ngoài dự kiến.** Guardrail cần kiểm thử, triển khai dần và có chủ sở hữu để đánh giá ngoại lệ.

**8. Không phân biệt công cụ phân tích log với kho chứng cứ.** Một SIEM phục vụ điều tra nhanh có thể cho phép quyền xử lý khác với kho lưu log có retention bất biến.

**9. Quên trách nhiệm chi phí nền tảng.** Khi không phân bổ hoặc quan sát, lượng log và network egress có thể tăng mà không ai chịu trách nhiệm.

**10. Vẽ sơ đồ accounts mà không có runbook liên đội.** Khi sự cố xảy ra, đội ứng dụng, SecOps và network phải biết ai có quyền thao tác gì, ai quyết định và thông báo cho ai.

## 13. Thực hành: xây landing zone cho hệ thống đặt lịch

**Đề bài:** Bạn là cloud architect cho doanh nghiệp chuẩn bị đưa ứng dụng đặt lịch lên production. Có ba đội phát triển (Booking, Admin, Analytics), một nhóm platform gồm hai người và một nhóm security kiêm nhiệm. Hệ thống cần kết nối tới một dịch vụ kế toán on-premise; các thao tác quản trị cloud và thay đổi quyền phải có log phục vụ điều tra 12 tháng. Có hai môi trường: production và nonproduction.

Các thông số sau chỉ để thực hành, cần được xác nhận trong dự án thật:

- Booking phục vụ khoảng 300 yêu cầu/giây ở đỉnh.
- Luồng đặt lịch yêu cầu SLO tỷ lệ thành công 99,9%/tháng.
- Mục tiêu RTO của kết nối kế toán là 60 phút; thiếu kết nối phải có cách xử lý nghiệp vụ tạm thời.
- Nhật ký audit dự kiến 20 GB/ngày; thời gian giữ 365 ngày.
- Dữ liệu khách hàng và log có thông tin nhận dạng phải tuân theo ràng buộc vùng lưu được xác định.

### Nhiệm vụ 1 — Thiết kế account hierarchy

Vẽ sơ đồ account/subscription/project thể hiện Management/Governance, Security, Network, Log Archive, Booking Prod, Admin Prod, Analytics Prod và các môi trường Nonprod. Ghi **chủ sở hữu** và **phạm vi quyền** của từng nhóm.

**Câu hỏi:** Có cần tách Log Archive khỏi Security Tooling không? Trả lời dựa trên yêu cầu bảo quản chứng cứ, quyền và nguồn lực vận hành, thay vì viện dẫn một mẫu cứng.

### Nhiệm vụ 2 — Vẽ hai luồng quan trọng

Vẽ sơ đồ kết nối Booking Prod → on-premise và sơ đồ control-plane audit từ workload → Log Archive → Security. Với từng đường, ghi các chính sách:

- Destination/port/route được cho phép; DNS và khả năng dự phòng.
- Ai có quyền thay route và ai chỉ được kiểm tra trạng thái?
- Nguồn log nào phải gửi, vùng lưu, retention và người được đọc?
- Điều gì xảy ra nếu đường gửi log hoặc kênh kết nối on-premise bị lỗi?

### Nhiệm vụ 3 — Xây ma trận quyền và guardrail

Lập ít nhất năm vai trò: Organization Admin, SecOps Analyst, Network Engineer, Log Operator, Booking Developer. Với mỗi vai trò, mô tả **tác vụ được phép** và **tác vụ bị từ chối** ở bốn nhóm tài khoản: Security, Network, Log Archive và Booking Prod.

Đề xuất tối thiểu ba guardrail, ví dụ: không cho workload xóa nguồn audit cấp tổ chức, giới hạn vùng triển khai, yêu cầu log forwarding cho account production. Chỉ rõ guardrail nào phòng ngừa, cái nào phát hiện.

### Nhiệm vụ 4 — Chứng minh thiết kế bằng phép thử

| Phép thử | Tình huống tạo ra | Bằng chứng mong đợi |
| --- | --- | --- |
| Quyền xóa log | Dùng role Booking Prod thử xóa audit object trong kho lưu chung | Bị từ chối; thao tác thất bại có dấu vết phù hợp |
| Phạm vi thu audit | Tạo sự kiện thay đổi role ở cả Prod và Nonprod | Sự kiện được nhận đúng nguồn, timestamp và region |
| Mất đường gửi log | Tạm ngắt/kích hoạt lỗi pipeline trong môi trường thử nghiệm | Có alert; biết số sự kiện bị chậm/mất và quy trình phục hồi |
| Mạng chặn truy cập | Từ Nonprod thử kết nối database Booking Prod trái phép | Lưu lượng bị chặn theo chính sách, có bằng chứng kiểm tra |
| Kết nối hybrid | Giả lập một tunnel/gateway lỗi | Chuyển tuyến hoặc xử lý suy giảm theo RTO/thiết kế |
| Danh tính khẩn cấp | Giả lập SSO gián đoạn theo quy trình cho phép | Break-glass hoạt động, có giám sát và thu hồi sau kiểm thử |
| Guardrail mới | Đưa policy vào sandbox trước production | Phát hiện ảnh hưởng ngoài ý muốn và có rollback |

Không dùng dữ liệu khách hàng thật hoặc thao tác phá hoại trong môi trường production để kiểm thử. Sử dụng tài nguyên thử nghiệm có phạm vi rõ ràng và được kiểm soát.

### Nhiệm vụ 5 — Review theo sáu trụ cột Well-Architected

| Trụ cột | Câu hỏi đánh giá thiết kế shared accounts |
| --- | --- |
| **Operational Excellence** | Account mới có được tạo bằng quy trình lặp lại, có owner, runbook và kiểm thử policy không? |
| **Security** | Có tách duties, least privilege, bảo vệ audit, MFA và giám sát quyền đặc biệt không? |
| **Reliability** | Hub, DNS, log ingestion và identity có điểm lỗi chung nào? RTO và xử lý thiếu log đã thử chưa? |
| **Performance Efficiency** | Route mạng và pipeline log có đáp ứng tải đỉnh? Có đo latency, throughput và quota? |
| **Cost Optimization** | Có dự báo chi phí gateway, egress, log retention và cách phân bổ cho workload không? |
| **Sustainability** | Có giảm dữ liệu log trùng, tài nguyên nhàn rỗi và sao chép qua vùng không cần thiết không? |

### Đầu ra tối thiểu của bài thực hành

Một bộ hồ sơ thiết kế có thể review gồm:

1. Sơ đồ account hierarchy kèm chủ sở hữu.
2. Sơ đồ networking và log flow với ranh giới truy cập.
3. Ma trận quyền cho các vai trò; danh sách guardrails và ngoại lệ.
4. SLO/RTO giả định, kịch bản lỗi và bằng chứng phép thử.
5. Ước lượng chi phí logging/network/security theo tải, retention và số môi trường.
6. Bảng phát hiện Well-Architected gồm bằng chứng, mức ảnh hưởng, hành động, người phụ trách và tiêu chí nghiệm thu.

Người review nên tìm câu trả lời cho ba câu hỏi: **ai sở hữu năng lực dùng chung; workload được phép làm gì với nó; nếu nó bị xâm nhập hoặc không khả dụng, những hệ thống nào bị ảnh hưởng?** Khi các câu trả lời dựa trên sơ đồ, cấu hình, quyền và thử nghiệm thực tế, thiết kế đã có nền tảng tốt để chuyển sang triển khai.

## 14. Checklist trước khi đưa tài khoản dùng chung vào production

- [ ] Tài khoản tổ chức, security, network, log archive và workload có owner và danh sách phụ thuộc rõ ràng.
- [ ] Nhóm production/nonproduction được tách theo mức rủi ro, dữ liệu và quyền cần thiết.
- [ ] Danh tính người dùng riêng, MFA, quyền ngắn hạn, quyền tối thiểu và break-glass có kiểm soát.
- [ ] Guardrail áp dụng đúng phạm vi, đã thử trên sandbox và có cơ chế ngoại lệ/rollback.
- [ ] Sơ đồ kết nối mô tả CIDR, routes, DNS, ingress/egress, hybrid và điểm lỗi tập trung.
- [ ] Các nguồn audit quan trọng được liệt kê và kiểm chứng log đến đích từ account/region phù hợp.
- [ ] Log Archive có retention, mã hóa, chính sách bảo vệ sửa/xóa và giới hạn quyền đọc tương xứng.
- [ ] Đội ứng dụng không thể tùy ý vô hiệu hóa audit cấp tổ chức hoặc xóa log gốc đã lưu.
- [ ] Có cảnh báo khi logging, security finding aggregation hoặc đường mạng dùng chung suy giảm.
- [ ] Network/DNS/logging có thử nghiệm lỗi, khả năng phục hồi và chỉ tiêu chất lượng đo được.
- [ ] Data classification và ràng buộc vị trí dữ liệu được áp dụng cho cả nhật ký lẫn dữ liệu nghiệp vụ.
- [ ] Chi phí gateway, egress, ingestion, retention và security tooling được theo dõi, dự báo và phân bổ.
- [ ] Có IaC, inventory, tài liệu bàn giao, runbook ứng cứu và lịch review Well-Architected.

Tài khoản dùng chung tạo ra **nền tảng vận hành và kiểm soát cho nhiều workload**, vì vậy thiết kế phải giữ cân bằng. Tách Security, Network và Log Archive giúp tổ chức phân quyền rõ, giảm phạm vi ảnh hưởng và giữ chứng cứ điều tra; đồng thời khiến kết nối xuyên tài khoản, khả năng dự phòng, chi phí và phối hợp liên đội quan trọng hơn. Giá trị của cách tổ chức này được chứng minh khi một workload mới có thể được cấp phát an toàn, một sự cố được phát hiện và điều tra đầy đủ, và một thành phần dùng chung gặp lỗi mà tác động đã được hiểu và kiểm soát.
