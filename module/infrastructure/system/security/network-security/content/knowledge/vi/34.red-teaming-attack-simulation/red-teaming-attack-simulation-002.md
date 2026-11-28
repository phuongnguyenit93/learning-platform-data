# Rules of engagement cho kiểm thử tấn công

## 1. Tổng quan: vì sao red team cần Rules of Engagement?

Một đội kiểm thử có thể được giao mô phỏng hành vi của đối thủ để kiểm tra xem mạng nội bộ có thực sự được bảo vệ bởi phân đoạn, firewall, VPN, IDS/IPS, DNS security, các lớp xác thực và giám sát hay không. Tuy nhiên, việc **có khả năng kỹ thuật** không đồng nghĩa với việc **được phép thực hiện**. Ngay cả thao tác như quét cổng, đăng nhập tài khoản thử nghiệm hoặc gửi một lưu lượng mô phỏng cũng có thể ảnh hưởng dịch vụ, tạo cảnh báo thật, làm lộ thông tin hoặc vượt phạm vi sở hữu.

**Rules of Engagement (RoE)** là bộ quy tắc được các bên có thẩm quyền thống nhất **trước khi kiểm thử**, xác định mục đích, phạm vi, hành động được phép và bị cấm, giới hạn kỹ thuật và thời gian, trách nhiệm, kênh liên lạc, điều kiện dừng, cách xử lý sự cố và nghĩa vụ bảo vệ dữ liệu. RoE là một **ranh giới vận hành và ủy quyền**, không chỉ là tệp biểu mẫu để ký.

Trong chương **Red team và mô phỏng tấn công mạng** thuộc module **SECURITY_NETWORK_SECURITY**, RoE giúp tổ chức đánh giá năng lực phòng vệ nhiều lớp mà không biến buổi diễn tập thành rủi ro không được chấp nhận. Điều này đặc biệt quan trọng khi phép thử chạm tới phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây và hạ tầng đám mây.

Sau bài này, bạn sẽ:

- Giải thích RoE khác gì mục tiêu kiểm thử, phạm vi (scope), kế hoạch kỹ thuật và báo cáo.
- Xác định các bên có thẩm quyền phê duyệt và các tài sản, vùng, tài khoản, kênh tấn công **thuộc/ngoài** phạm vi.
- Phân loại hoạt động được phép, hoạt động có điều kiện và hoạt động bị cấm.
- Xây dựng giới hạn an toàn: mức tải, giờ thử, quyền tài khoản, xử lý dữ liệu, kiểm soát tác động, điểm dừng.
- Thiết kế liên lạc, escalation, deconfliction, ghi nhật ký và quy trình khẩn cấp.
- Đặt tiêu chí thành công dựa trên kiểm soát an ninh được quan sát và khả năng phát hiện/ứng phó.
- Biên soạn mẫu RoE có thể rà soát và áp dụng cho một bài diễn tập có kiểm soát.

> **Quy tắc cơ bản:** Không có **ủy quyền rõ ràng, cụ thể và còn hiệu lực** cho một hoạt động thì không suy diễn rằng hoạt động ấy được phép. Khi xuất hiện tài sản ngoài phạm vi, dữ liệu thật ngoài dự kiến hoặc rủi ro mới, phải dừng phần liên quan và xin quyết định từ đúng người có thẩm quyền.

## 2. Phân biệt RoE, Scope, Test Plan và Authorization

| Khái niệm | Câu hỏi trả lời | Đầu ra điển hình |
|---|---|---|
| **Authorization (ủy quyền)** | Ai có quyền cho phép hoạt động và quyền đó áp dụng đến đâu? | Văn bản/phê duyệt có phạm vi, thời hạn, bên chịu trách nhiệm |
| **Scope (phạm vi)** | Những hệ thống, người dùng, IP/FQDN/tenant, dịch vụ, thời gian nào thuộc bài thử? | Danh sách in-scope/out-of-scope và điều kiện |
| **Rules of Engagement** | Những hành động nào được phép/cấm; giới hạn và quy trình khi phát sinh tình huống? | Quy tắc ràng buộc, stop conditions, escalation, dữ liệu, trách nhiệm |
| **Test Plan/Runbook** | Trình tự kỹ thuật kiểm thử theo phê duyệt được triển khai thế nào? | Kịch bản, công cụ, bước kiểm tra, bằng chứng và rollback |
| **Threat model / scenario** | Hành vi đối thủ nào cần mô phỏng, vì sao? | Giả định, mục tiêu và chuỗi hành vi cấp cao |
| **Report/lessons learned** | Phòng vệ phát hiện/ứng phó ra sao, điểm nào cần cải thiện? | Kết quả, timeline, mức tin cậy, khuyến nghị và action items |

**RoE không thay thế quyền sở hữu tài sản hoặc thẩm quyền pháp lý.** Một người quản trị có thể thao tác kỹ thuật trên thiết bị nhưng không nhất thiết có quyền cho phép đưa dữ liệu khách hàng, hệ thống của nhà cung cấp hoặc mạng đối tác vào bài diễn tập. Cần kiểm tra ranh giới nhiều bên trước khi bắt đầu.

### 2.1. Red team, penetration test và purple team

- **Penetration test:** thường tập trung xác minh điểm yếu trong phạm vi kỹ thuật đã xác định và mô tả khả năng tác động; RoE giới hạn cách kiểm tra và khai thác khi được phép.
- **Red team:** mô phỏng mục tiêu/hành vi đối thủ theo kịch bản nhằm đánh giá phối hợp của nhiều lớp phòng vệ, khả năng phát hiện và ứng phó; RoE quản lý hoạt động có thể kéo dài, nhiều bước và nhiều nhóm.
- **Purple team:** red/blue cùng trao đổi bằng chứng để tinh chỉnh phát hiện/kiểm soát; RoE vẫn phải chỉ rõ kênh chia sẻ, phần nào công khai trước và điều kiện dừng.
- **Breach and attack simulation (BAS):** hoạt động tự động mô phỏng kỹ thuật hoặc tác động được chuẩn hóa; automation không miễn yêu cầu giới hạn tần suất, quyền, dữ liệu, khả năng dừng và trách nhiệm.

Tùy mục tiêu, có thể cho đội blue biết toàn bộ bài thử, chỉ cho biết khung thời gian, hoặc áp dụng cơ chế blind test với nhóm white cell nắm quyền can thiệp. **Không giấu thông tin với người có trách nhiệm an toàn và dừng khẩn cấp** chỉ để tăng tính thực tế.

## 3. Nguyên tắc thiết kế RoE

### 3.1. Sáu nguyên tắc

1. **Ủy quyền cụ thể:** ghi chủ thể duyệt, tổ chức/tài sản được phép, mục đích, thời điểm bắt đầu/kết thúc và giới hạn. Sự đồng ý miệng mơ hồ không nên được coi là bằng chứng đủ cho hoạt động rủi ro.
2. **Phạm vi kiểm chứng được:** tài sản xác định bằng định danh ổn định; IP/FQDN chỉ là một phần vì NAT, cloud autoscaling, load balancer và DNS có thể đổi theo thời gian.
3. **Ưu tiên giảm tác động:** dùng dữ liệu mẫu, tài khoản thử, kỹ thuật không phá hoại và quy trình thay thế an toàn khi có thể; cường độ thử không vượt nhu cầu.
4. **Có người chịu trách nhiệm:** mỗi nhóm hành động có owner, người giám sát, đầu mối điều phối và quyền dừng rõ ràng.
5. **Có thể quan sát và tái lập:** ghi thời gian UTC, nguồn kiểm thử, hành động, kết quả, bằng chứng, cảnh báo và thay đổi; bảo vệ tài liệu như dữ liệu an ninh nhạy cảm.
6. **Dừng và thay đổi có kiểm soát:** khi lệch scope, xảy ra sự cố, xuất hiện dữ liệu không dự kiến hoặc chưa rõ quyền, không tự mở rộng kịch bản.

### 3.2. Vì sao “được phép kiểm thử hệ thống X” vẫn chưa đủ?

Một máy chủ có thể chạy nhiều ứng dụng hoặc lưu dữ liệu do đơn vị khác quản lý; cloud account có dịch vụ dùng chung; reverse proxy trên một IP có thể phục vụ nhiều virtual host. Nếu văn bản chỉ ghi “được kiểm thử dải mạng A” mà không nêu **các ngoại lệ, dữ liệu, hình thức tương tác và tác động chấp nhận được**, nhóm kiểm thử có thể vô tình bước sang một ranh giới không được phép.

Cần mô tả phạm vi ở nhiều chiều: *asset identity + network path + ứng dụng/dịch vụ + account/role + kỹ thuật + thời gian + mức tác động*. Khi một chiều không chắc chắn, xác minh trước thay vì suy đoán.

## 4. Xác định phạm vi và quyền sở hữu

RoE phải liệt kê cả **in-scope** và **out-of-scope**; chỉ ghi danh sách in-scope thường để lại nhiều khoảng mơ hồ.

| Thuộc tính | Cần ghi | Rủi ro nếu bỏ qua |
|---|---|---|
| Tài sản | Asset ID, CMDB, hostname, cloud resource ID, IP/CIDR | IP tái sử dụng hoặc đổi thành tài sản khác |
| Vị trí | Data center, VPC/VNet, VLAN/VRF, Wi-Fi SSID, site, VPN zone | Kết quả từ một vùng bị suy ra cho toàn bộ mạng |
| Môi trường | Lab, staging, production và phần dùng chung | Dữ liệu thật hoặc workload production bị ảnh hưởng |
| Ứng dụng | FQDN, service, port/protocol, API route được phép | Vhost hoặc backend của đơn vị khác bị chạm tới |
| Danh tính | Test user, service account, role, thiết bị kiểm thử | Sử dụng account thật với quyền quá lớn |
| Dữ liệu | Synthetic/production, loại nhạy cảm, quyền xem/sao chép | Thu thông tin cá nhân/credential ngoài chủ đích |
| Bên thứ ba | CDN, MSSP, SaaS, cloud, đối tác, nhà mạng | Tài sản không thuộc thẩm quyền phê duyệt |
| Khung thời gian | UTC, cửa sổ thử, blackout, gia hạn | Chạm đợt vận hành cao điểm hoặc ngoài thời hạn |
| Phương pháp | Quan sát, mô phỏng kiểm soát, kỹ thuật có điều kiện | Thành viên tự suy diễn mức can thiệp được phép |

**Ví dụ:** `192.0.2.10` là địa chỉ tài liệu thuộc dải TEST-NET; được dùng trong biểu mẫu bên dưới như một ký hiệu minh họa, **không phải một mục tiêu đã được ủy quyền thực tế**.

### 4.1. Tài sản động và phạm vi thay đổi

- **DNS/CDN:** FQDN có thể trả nhiều IP, trong đó có hạ tầng của bên thứ ba; không tự xem mọi IP đã phân giải là in-scope.
- **Cloud:** instance, pod và public IP có thể bị thay thế; nên gắn resource ID/account/region, tag và version của inventory.
- **Kubernetes/service mesh:** một service có thể định tuyến tới pod khác ở các thời điểm khác nhau; RBAC và tenant boundary cần được xem xét.
- **VPN/NAT:** một IP nội bộ có thể đại diện cho nhiều người dùng/session; tránh dùng IP một mình để xác định user.
- **Mạng không dây:** việc cho phép kiểm tra SSID của tổ chức không tự cho phép tương tác với thiết bị khách hoặc access point của bên cạnh.
- **Dịch vụ chung:** IdP, DNS resolver, VPN concentrator, CI/CD, database và monitoring có thể phục vụ nhiều đơn vị; giới hạn hành động ảnh hưởng chung.

RoE nên có một **scope snapshot có phiên bản** và quy trình cập nhật khi phát hiện tài sản động mới. Các phát hiện ngoài phạm vi chỉ được ghi nhận ở mức cho phép; không tự truy vấn sâu hơn.

### 4.2. Bên thứ ba và dịch vụ cloud

Sự đồng ý của chủ ứng dụng chưa chắc cho phép thử hạ tầng nền của cloud/CDN/SaaS. Cần rà soát hợp đồng, quy định kiểm thử của nhà cung cấp và điều kiện thực hiện theo chính sách hiện hành. Nếu không đủ quyền đối với lớp hạ tầng, chuyển sang cách **đánh giá cấu hình** hoặc **mô phỏng bằng tài sản do tổ chức kiểm soát**, không mở rộng việc kiểm thử sang hệ thống của nhà cung cấp.

## 5. Định nghĩa hành động được phép, có điều kiện và bị cấm

Một bảng phân loại minh bạch giúp người tham gia không phải tự quyết về những hành động có hậu quả lớn. **Các mục bên dưới là ví dụ định hướng**, mức cho phép thực tế do RoE đã ký quyết định.

| Hoạt động | Phân loại gợi ý | Điều kiện/mục tiêu |
|---|---|---|
| Kiểm kê tài sản và phân tích log sẵn có | Được phép trong scope | Không vượt quyền xem và retention/dữ liệu |
| Kiểm tra kết nối, dịch vụ từ máy kiểm thử được cấp phép | Được phép có giới hạn | Cổng/host cụ thể, tốc độ, khung giờ và cảnh báo SOC |
| Kiểm tra segmentation/firewall bằng traffic mẫu | Được phép có giới hạn | Traffic không gây gián đoạn, nguồn/đích cố định, test ID |
| Mô phỏng chuỗi truy cập bằng tài khoản test | Có điều kiện | Quyền tối thiểu, tách dữ liệu thật, cơ chế reset/rollback |
| Thử workflow phishing nhận thức với nội dung được duyệt | Có điều kiện riêng | Phê duyệt nhân sự/pháp lý, danh sách người nhận, không thu mật khẩu thật |
| Truy cập dữ liệu production thật | Mặc định không được phép | Chỉ có thể xem xét bằng quy trình riêng, mục đích và biện pháp bảo vệ cụ thể |
| Thử privilege escalation/lateral movement | Có điều kiện riêng | Đích/đường rõ, tài khoản thử, mức tác động và kill switch |
| Duy trì foothold/persistence trên hệ thống thật | Mặc định cấm | Nếu mục tiêu đòi hỏi, phải có ủy quyền bổ sung, cơ chế dọn dẹp/giám sát |
| Truyền dữ liệu để mô phỏng exfiltration | Chỉ dùng dữ liệu giả/marker được phê duyệt | Đích do tổ chức kiểm soát, dung lượng/loại dữ liệu giới hạn |
| Đọc, xuất hoặc chuyển thông tin khách hàng thật | Mặc định cấm | Không được suy ra quyền chỉ vì tài khoản test nhìn thấy dữ liệu |
| DDoS, làm cạn tài nguyên, gây ngừng dịch vụ | Cấm trong RoE thông thường | Cần quy trình thử tải/khả năng chịu lỗi riêng, môi trường kiểm soát |
| Thay đổi/xóa dữ liệu, tắt backup hoặc vô hiệu kiểm soát an ninh | Mặc định cấm | Không thực hiện nếu không có thẩm quyền và kế hoạch riêng |
| Can thiệp thiết bị của bên thứ ba hoặc ngoài scope | Cấm | Dừng và báo owner khi phát hiện ranh giới |
| Thu thập credential/secret thật từ người dùng | Mặc định cấm | Dùng token giả/honey credential chỉ khi được duyệt |
| Phá giám sát, xóa log, né tránh điều phối an toàn | Cấm | Test phát hiện bằng tín hiệu được phê duyệt, không phá audit |

**Quan trọng:** “Có điều kiện” **không tự biến thành được phép**. Khi tài liệu phê duyệt không ghi rõ điều kiện và người duyệt, nhóm kiểm thử phải coi là chưa được phép.

### 5.1. Phân biệt mô phỏng và gây tác động thật

RoE có thể yêu cầu chứng minh firewall chặn một tuyến truy cập, IDS phát hiện một mẫu hành vi hoặc DLP cảnh báo luồng dữ liệu bất thường. Không cần đẩy tệp thật ra bên ngoài hay cố vượt mọi kiểm soát để có số liệu. Hãy ưu tiên:

- **Tài khoản thử:** phân quyền đủ để tái hiện một bước, không sử dụng đặc quyền production không cần thiết.
- **Dữ liệu tổng hợp:** file canary chứa nội dung giả được đánh dấu; không gắn tên/mã số cá nhân thật.
- **Đích kiểm soát:** sink endpoint nội bộ hoặc hạ tầng thử nghiệm có quyền rõ, thu metric thay vì dữ liệu nhạy cảm.
- **Tác động mô phỏng:** đánh giá log, alert, luồng phê duyệt và khả năng ứng phó mà không thực hiện hành động phá hoại.
- **Giới hạn lượng tải:** giới hạn số request, băng thông, byte, session, thời gian thử và tài nguyên.

Mục tiêu của red team là đánh giá **khả năng phòng vệ/ứng phó**, không phải thu được càng nhiều dữ liệu thật càng tốt.

## 6. Rules of Engagement theo từng giai đoạn kiểm thử

| Giai đoạn | Giới hạn cần có | Bằng chứng kỳ vọng |
|---|---|---|
| Chuẩn bị | Scope, ủy quyền, inventory, threat model, kênh liên hệ | RoE phê duyệt, test ID, liên hệ khẩn cấp |
| Khảo sát | Dùng tài sản/nguồn thử được duyệt; tần suất và giao thức giới hạn | Source/destination, UTC, log/capture, phát hiện ngoài scope |
| Kiểm tra xác thực và phân quyền | Test account, RBAC, MFA đúng quy trình, không brute force | Auth decision, log, policy mapping |
| Mô phỏng di chuyển trong mạng | Chỉ những vùng/đường đi được duyệt, không mở rộng sang dịch vụ chung | Firewall/segmentation logs và kết quả |
| Mô phỏng thực hiện mục tiêu | Dữ liệu canary, marker, không thay đổi dữ liệu thật | Alert/DLP/EDR/IDS response, metric |
| Ứng phó blue team | Người giám sát an toàn có quyền dừng, ghi escalation | Timeline phát hiện, phân loại, containment |
| Dọn dẹp và phục hồi | Gỡ tài khoản/file/test agent, thu hồi token, xác minh dịch vụ | Checklist cleanup, config diff, chủ sở hữu xác nhận |
| Báo cáo và hậu kiểm | Dữ liệu giảm nhạy cảm, đánh giá rủi ro và action owner | Báo cáo, bằng chứng, test coverage, lessons learned |

Một kịch bản nhiều giai đoạn cần **điểm kiểm tra (checkpoint)** giữa các giai đoạn rủi ro. Quyền khảo sát không tự động cho phép thực hiện hành động duy trì truy cập hoặc tác động tới dữ liệu.

## 7. Thiết kế giới hạn tải và độ an toàn vận hành

Kiểm thử trên thiết bị mạng và dịch vụ an ninh có rủi ro khác máy chủ ứng dụng thông thường. Firewall/VPN/IDS/IPS có thể gặp giới hạn session table, CPU, bộ nhớ hoặc bộ phân tích giao thức; router/switch cũ và hệ thống OT/IoT có thể phản ứng khác với probe.

### 7.1. Các giới hạn phải đo được

- **Thời gian:** ngày giờ UTC bắt đầu/kết thúc, blackout window, thời gian mỗi phase và quy tắc gia hạn.
- **Tốc độ:** số request/giây, packets/giây, connections đồng thời, số lần thử lại và số host một lần.
- **Tải hệ thống:** ngưỡng CPU, memory, connection exhaustion, latency và error rate để dừng.
- **Lưu lượng mạng:** bandwidth, packet loss, queue/drop counters và giới hạn tổng byte.
- **Số tài khoản/phiên:** test identities, số lần đăng nhập thất bại cho phép, tự động khóa account.
- **Dữ liệu:** loại/khối lượng file canary, endpoint nhận, khả năng xóa, thời gian giữ.
- **Thay đổi cấu hình:** nếu được phép, cần snapshot, change owner, kiểm tra trước/sau và rollback.
- **Giám sát:** dashboard theo dõi live, người liên hệ trực, luồng SOC xác định để phân biệt test với sự cố thật.

RoE nên điền **giá trị số do người sở hữu hệ thống phê duyệt**, không sao chép cứng một ngưỡng “an toàn cho mọi mạng”. Ví dụ giới hạn 5 kết nối đồng thời có thể phù hợp với một thiết bị nhưng vẫn quá nhiều với thiết bị cũ; số liệu phải dựa trên lab/baseline và khả năng thiết bị.

### 7.2. Điều kiện dừng (stop conditions)

Dừng ngay phần hoạt động liên quan nếu:

1. Tác động vượt ngưỡng đã duyệt hoặc có dấu hiệu gián đoạn dịch vụ thật.
2. Phạm vi thực tế khác scope: chuyển sang hệ thống/tenant của bên khác, tài nguyên mới hoặc dữ liệu không mong đợi.
3. Công cụ tạo hành động ngoài dự kiến, ghi/đọc dữ liệu thật vượt phạm vi hoặc quyền admin vượt yêu cầu.
4. Có dấu hiệu sự cố an ninh thật trùng thời điểm kiểm thử mà không thể phân biệt với bài thử.
5. Blue team, incident commander, owner hoặc white cell có thẩm quyền ra lệnh dừng.
6. Mất liên lạc với đầu mối an toàn khi giai đoạn thử yêu cầu giám sát trực tiếp.
7. Log/evidence bị mất tính toàn vẹn, đồng hồ sai lớn hoặc không thể xác minh tác động đang diễn ra.

Tùy severity, **dừng có thể áp dụng cho một hành động, một phase hoặc toàn bộ diễn tập**. Cần chỉ rõ **ai ra quyết định dừng và ai thực thi**, cách xác nhận đã dừng, cách cô lập/làm sạch và tiêu chí được phép tiếp tục. Không tự “thử thêm một lần” khi stop condition đã kích hoạt.

## 8. Vai trò, trách nhiệm và quyền ra quyết định

| Vai trò | Trách nhiệm |
|---|---|
| Executive sponsor / accountable owner | Chấp thuận mục tiêu và rủi ro tổng thể, bảo đảm nguồn lực và quyền tài sản |
| Asset/service owner | Xác nhận ownership, scope, giới hạn tác động và tiêu chí phục hồi |
| Test lead (red team lead) | Chịu trách nhiệm phương pháp, giám sát hành động, logs, tuân thủ RoE |
| White cell / exercise control | Điều phối giữa test và vận hành, giải quyết xung đột, quyết định pause/stop theo phân quyền |
| Blue team / SOC | Giám sát, phát hiện, xử lý alert theo kịch bản đã thỏa thuận; có kênh dừng khẩn |
| Incident commander / on-call | Điều phối khi xuất hiện sự cố thật hoặc ảnh hưởng vận hành |
| Network/security operations | Theo dõi firewall, VPN, IDS/IPS, segmentation, đường đi và khả năng rollback |
| Privacy/legal/compliance | Xác nhận ranh giới quyền, dữ liệu cá nhân và xử lý bên thứ ba khi liên quan |
| Evidence custodian | Quản lý log, PCAP, dữ liệu thử, retention và chain of custody |
| Report reviewer / action owner | Kiểm tra phát hiện, đề xuất khắc phục, theo dõi re-test và hậu kiểm |

Đối với dự án nhỏ, một người có thể đảm nhiệm nhiều vai trò nhưng **quyền quyết định phải được ghi rõ**. Người thực hiện phép thử không nên tự phê duyệt mở rộng sang một hệ thống không thuộc scope.

### 8.1. RACI mẫu

| Hoạt động | Sponsor | Asset owner | Test lead | White cell | SOC |
|---|---|---|---|---|---|
| Xác nhận mục tiêu/phạm vi | A | R | C | C | I |
| Phê duyệt giới hạn ảnh hưởng | A | R | C | C | C |
| Thực hiện bước trong RoE | I | I | A/R | C | I/C theo thiết kế |
| Yêu cầu dừng khẩn | I | R | R | A theo ủy quyền | R |
| Điều phối sự cố thật | I | C | C | C | R với incident commander |
| Xác minh cleanup/khôi phục | I | A | R | C | C |
| Duyệt báo cáo cuối | A | C | R | C | C |

*R = Responsible, A = Accountable, C = Consulted, I = Informed.* Ma trận chỉ minh họa. Với tình huống dừng khẩn, cần nêu rõ quyền **dừng ngay** của nhiều bên; không đợi người phê duyệt cấp cao phản hồi khi có ảnh hưởng thực.

## 9. Giao tiếp, deconfliction và escalation

**Deconfliction** là cơ chế phân biệt hoạt động diễn tập đã được phép với sự cố/hoạt động độc hại thật mà không làm mất mục đích đánh giá. Nó đặc biệt quan trọng khi SOC có thể kích hoạt phong tỏa, cô lập endpoint hoặc báo cáo bên ngoài.

RoE cần ghi:

- Kênh chính và dự phòng: incident channel nội bộ, điện thoại khẩn cấp, phương án khi chat/VPN không hoạt động.
- Danh tính xác minh khi yêu cầu dừng/tiếp tục: người nhận, phương thức xác thực, ai có thể ban hành lệnh.
- Nhịp cập nhật: trước khi bắt đầu, khi chuyển phase, khi xảy ra bất thường và khi kết thúc.
- **Test ID** và danh sách nguồn/đích được duyệt gửi tới đúng người cần biết, với quyền truy cập giới hạn.
- Cách xử lý alert trong SOC: thông báo trước bao nhiêu, ai có thể tra mã diễn tập, trường hợp nào vẫn xử lý như sự cố thật.
- Khi nào blue team được phép biết chi tiết kỹ thuật: thông báo trước, sau mỗi phase hoặc sau khi kết thúc; tùy mức blind/purple test.
- Cách chuyển sự cố thật sang incident response: ai tiếp nhận, mốc UTC, log cần bảo toàn, ai quyết định pause/abort.

### 9.1. Mô hình liên lạc

~~~mermaid
flowchart TD
    A["Red team thực hiện phase được duyệt"] --> B{"Có dấu hiệu bất thường hoặc vượt ngưỡng?"}
    B -->|"Không"| C["Ghi log, cập nhật checkpoint"]
    C --> A
    B -->|"Có"| D["Dừng hành động liên quan; giữ trạng thái an toàn"]
    D --> E["Liên hệ white cell và incident/on-call"]
    E --> F{"Sự cố thật hoặc tác động chưa kiểm soát?"}
    F -->|"Có"| G["Incident response; ưu tiên an toàn và bảo toàn chứng cứ"]
    F -->|"Không, đã xác minh"| H["Xem xét scope/rủi ro và quyền tiếp tục"]
    H --> I{"Có phê duyệt tiếp tục?"}
    I -->|"Có"| C
    I -->|"Không"| J["Cleanup và kết thúc phần thử"]
    G --> J
~~~

Không có cơ chế deconfliction nào cho phép bỏ qua cảnh báo thật. Nếu nghi bị tấn công ngoài bài diễn tập, xử lý như sự cố thật và cân nhắc dừng toàn bộ cuộc thử để không làm nhiễu chứng cứ.

### 9.2. Mẫu thông báo checkpoint

~~~text
Test ID: RT-EX-002
Phase: kiểm chứng segmentation bằng traffic tổng hợp
Time (UTC): 2026-11-28T09:00:00Z
Source zone: redteam-lab
Destination scope: approved test VPC segment
Expected signal: firewall deny/allow log và IDS/IPS event
Impact observed: chưa phát hiện bất thường
Next checkpoint: theo lịch đã phê duyệt
Contact: test lead và white cell qua kênh nội bộ được xác nhận
~~~

Thông báo chỉ minh họa cấu trúc; không chèn credential, payload nhạy cảm hoặc chỉ dẫn truy cập production vào kênh chat không được bảo vệ.

## 10. Xử lý trường hợp nhạy cảm: credential, dữ liệu và con người

### 10.1. Credential và quyền tài khoản

Khi diễn tập cần xác thực:

- Ưu tiên **tài khoản thử riêng**, quyền tối thiểu, credential có thời hạn và được quản lý qua vault.
- Không thử password spraying, brute force hoặc dùng mật khẩu bị lộ của nhân viên nếu RoE không có phê duyệt rất cụ thể; đây không phải yêu cầu mặc định.
- Không sao chép token, private key, session cookie hoặc mật khẩu thật ra khỏi hệ thống quản lý.
- Nếu vô tình thấy secret thật: dừng bước gây lộ, không sử dụng nó, thông báo đúng đầu mối để đánh giá thu hồi và bảo toàn chứng cứ tối thiểu.
- Sau diễn tập: revoke test account/token, xóa khóa, đóng session, xác minh không còn quyền dự phòng bất ngờ.

### 10.2. Phishing/social engineering

Kiểm thử yếu tố con người phải được xem là **một phạm vi riêng**. Cần có phê duyệt từ các bộ phận có thẩm quyền, xác định nhóm người nhận, kênh gửi, thời gian, nội dung, trang đích, chính sách không thu mật khẩu thật, xử lý khi người tham gia báo cáo và biện pháp bảo vệ sức khỏe/an toàn/tôn trọng người dùng.

Không giả mạo tình huống khẩn cấp có thể gây hoảng loạn hoặc buộc người nhận thực hiện chuyển tiền, tiết lộ dữ liệu nhạy cảm hay hành động rủi ro ngoài bài thử. Có thể đo **tỷ lệ báo cáo**, thời gian SOC phản ứng và chất lượng hướng dẫn an toàn thay vì thu credential thật.

### 10.3. Mô phỏng data exfiltration

Để đo DLP, firewall egress hoặc SOC response, sử dụng **canary data không mang thông tin thật** và endpoint thử do tổ chức kiểm soát. RoE cần định nghĩa:

- Kích thước/tổng byte, loại file, mã nhận dạng, địa chỉ nhận và giới hạn thời gian.
- Không lấy dữ liệu khách hàng, log cá nhân, bí mật sản xuất làm “mẫu”.
- Không tạo đường thoát dữ liệu ra dịch vụ không thuộc quyền; không che giấu dữ liệu trong kênh ngoài phạm vi.
- Cách kiểm tra log/DLP alert; ngưỡng dừng; thời hạn xóa file giả và xác nhận cleanup.

Trong nhiều tình huống, một marker đã định danh và xác minh receipt trong sink nội bộ **đủ** để chứng minh kiểm soát phát hiện luồng di chuyển; không cần truy cập nội dung có giá trị thực.

## 11. Kiểm soát công cụ, hạ tầng và tự động hóa

Một bộ công cụ mô phỏng tấn công cần được kiểm soát như phần mềm có thể gây tác động:

1. **Inventory:** tool, version, hash, mục tiêu, host chạy, quyền, các module/plugin được bật.
2. **Configuration review:** xác nhận đích, nguồn, rate, timeout, retry, giới hạn đồng thời và hành động hậu kiểm; không chạy cấu hình mặc định nếu chưa biết tác động.
3. **Lab validation:** thử cùng phiên bản trên môi trường đại diện, kiểm tra stop condition và telemetry.
4. **Change control:** kịch bản hoặc cấu hình tool thay đổi phải được review; người vận hành không tự thêm chức năng ngoài RoE.
5. **Logs:** lưu time, operator, action, parameters an toàn, output ref, error, cleanup; tránh lưu secret trong terminal history.
6. **Kill switch:** có cách dừng công cụ/job và thu hồi quyền/kết nối khi cần; kiểm chứng kill switch trước phase rủi ro.
7. **Infrastructure:** máy test do tổ chức kiểm soát, bảo vệ endpoint, không dùng máy cá nhân không quản lý hoặc host bên thứ ba làm nguồn phát ngoài phạm vi.
8. **Recovery:** chuẩn bị hoàn nguyên test account, rule tạm, agent, file và thay đổi cấu hình; xác nhận với owner.

Lệnh thử tự động cần có cơ chế **dry-run**, giới hạn phạm vi và xác nhận điều kiện trước khi thực hiện. Một job có thể chạy lại hoặc retry sau lỗi; phải bảo đảm lần chạy lại không vượt cửa sổ được phép hay tạo tác động cộng dồn.

## 12. Bảo vệ bằng chứng và dữ liệu trong suốt diễn tập

Bài red team có thể tạo log nhạy cảm về topology, tuyến VPN, chính sách IDS/IPS, tài khoản, lỗ hổng chưa vá và khả năng kiểm soát của SOC. Phải coi kết quả là dữ liệu bảo mật theo chính sách tổ chức.

### 12.1. Evidence tối thiểu

| Loại | Dữ liệu cần giữ | Giới hạn |
|---|---|---|
| Authorization/RoE | Phiên bản đã duyệt, người phê duyệt, thời hạn, scope | Chỉ chia sẻ theo vai trò |
| Execution log | Test ID, phase, actor, nguồn/đích, UTC, action và outcome | Không chép password/token trong plaintext |
| Network evidence | Firewall/IDS alerts, flow telemetry, PCAP có phạm vi | Dữ liệu người dùng, packet loss, clock drift |
| Identity evidence | Auth decision, role, MFA logs của tài khoản test | Không lộ credential hoặc thông tin nhân sự dư thừa |
| Change/rollback | Config diff, version, approval, kết quả khôi phục | Không đặt secret vào report |
| Cleanup | Tài khoản/agent/file đã loại bỏ, owner xác nhận | Không khẳng định đã dọn nếu chưa kiểm tra |
| Detection/response | Thời điểm alert, triage, containment, false positive | Cần định nghĩa thời điểm và độ lệch đồng hồ |

Giữ bản gốc của những artifact quan trọng, tính hash sau khi file được chốt, quản lý nơi lưu, người truy cập và chain of custody khi áp dụng; bản trích xuất đã redact có định danh riêng. Thống nhất event time, ingest time và collection time khi đo thời gian phát hiện/ứng phó.

### 12.2. Retention và bảo vệ thông tin

- Chỉ thu những gì phục vụ mục tiêu và phạm vi đã được duyệt.
- Mã hóa khi truyền và lưu; phân quyền theo case, MFA, audit tải/xem/chuyển giao.
- Hạn chế screenshot/tài liệu có tên người dùng, token, dữ liệu cá nhân hoặc cấu hình mạng bí mật.
- Ghi retention, người phê duyệt, ngày xem xét và xử lý legal hold khi có yêu cầu hợp lệ.
- Sau khi kết thúc, xóa bản test/working copy và các kho không còn cần thiết theo chính sách; không suy rằng xóa một bản chính là xóa hết bản sao/backup.

**Bảo toàn chứng cứ không mâu thuẫn với giảm thu thập**: có thể lưu log đã lọc và ký hiệu marker để đo kiểm soát, đồng thời giữ bản thu gốc hạn chế khi thật sự cần điều tra.

## 13. Tiêu chí thành công phải đo được

RoE nên định nghĩa trước **điều gì được xem là bằng chứng** cho năng lực phòng vệ, chứ không đánh giá bằng “red team có chiếm được gì hay không” theo cách bất chấp an toàn.

| Mục tiêu | Tín hiệu có thể đo | Giới hạn diễn giải |
|---|---|---|
| Segmentation | Phân đoạn không được phép bị firewall/ACL chặn, log có rule ID | Cần kiểm tra từng nguồn và IPv4/IPv6, không chỉ một điểm |
| IDS/IPS | Event đúng kịch bản xuất hiện với ngữ cảnh và severity phù hợp | Có alert chưa chứng minh người trực đã triage |
| DNS security | Query thử đến domain mẫu được phân loại/xử lý đúng policy | Cache/DoH/split DNS có thể ảnh hưởng quan sát |
| VPN/ZTNA | Chỉ user/device thuộc nhóm thử truy cập đúng zone | Đăng nhập VPN chưa đồng nghĩa có quyền mọi service |
| Identity | MFA, RBAC, policy quyết định đúng với tài khoản thử | Không cần thu credential thật |
| SOC response | Thời gian từ tín hiệu đầu tới alert, ack, triage, containment | Phải thống nhất timestamp và mức độ mô phỏng |
| Resilience | Dịch vụ hợp lệ vẫn trong SLO trong suốt diễn tập | Bài test ít tải chưa chứng minh chịu được mọi tình huống |
| Cleanup | Không còn test account, file, agent, rule tạm, session | Phải kiểm tra bằng owner/config/log, không chỉ báo cáo tự khai |

Đo **phát hiện, xác minh, quyết định và phối hợp**. Nếu blue team không phát hiện một kỹ thuật trong bài thử, RoE cần cho phép rút bài học và tạo action item, không mặc định phải tiếp tục hành động đến khi gây tác động thật.

### 13.1. Chỉ số và mẫu tính toán

Có thể dùng các mốc (được định nghĩa trong RoE):

~~~text
T0 = Thời điểm hành động kiểm thử bắt đầu theo log red team
T1 = Sự kiện đầu tiên được cảm biến ghi nhận
T2 = Alert xuất hiện trong SIEM/SOC queue
T3 = Analyst acknowledge
T4 = Đã có quyết định/động tác ứng phó được ghi nhận

Detection pipeline delay = T2 - T1
SOC acknowledgement delay = T3 - T2
Response decision delay = T4 - T3
~~~

Nếu log nguồn/SIEM/chat lệch đồng hồ, không được tính chênh lệch thành số đo chính xác. Từ **không có alert** không suy ra hệ thống không quan sát được activity; cần kiểm tra sensor coverage, chính sách logging, ingest lag và phạm vi dữ liệu được phép.

## 14. Quy trình phê duyệt thay đổi RoE

Không mở rộng kỹ thuật hoặc địa chỉ bằng một tin nhắn thiếu lịch sử. Có thể dùng quy trình:

~~~mermaid
flowchart TD
    A["Phát hiện nhu cầu thay đổi scope/method"] --> B["Tạm dừng phần liên quan"]
    B --> C["Mô tả mục đích, tác động và tài sản liên quan"]
    C --> D["Xác nhận ownership, bên thứ ba và dữ liệu"]
    D --> E["Asset owner + người có thẩm quyền đánh giá"]
    E --> F{"Phê duyệt cụ thể?"}
    F -->|"Không"| G["Giữ nguyên RoE; không thực hiện"]
    F -->|"Có"| H["Cập nhật phiên bản, time window, giới hạn"]
    H --> I["Thông báo white cell/SOC và đầu mối an toàn"]
    I --> J["Xác nhận lại stop conditions và tiếp tục"]
~~~

RoE nên có **version**, lịch sử thay đổi, chữ ký/phê duyệt, hiệu lực và người đã nhận bản mới. Không sửa thầm tài liệu sau khi một bước kiểm thử đã chạy rồi gắn nhãn “đã được duyệt”.

Khi kịch bản gặp ranh giới không rõ (ví dụ proxy chuyển sang SaaS của nhà cung cấp), chọn xử lý **giảm thiểu tương tác**: ghi phát hiện tối thiểu được phép, dừng và xin đánh giá scope. Nếu cần kiểm chứng hiệu quả phòng vệ mà không có quyền với đích thật, thay thế bằng endpoint giả có kiểm soát.

## 15. Mẫu RoE có thể tái sử dụng

Mẫu dưới đây là **minh họa học tập**, không cấu thành giấy phép kiểm thử một hệ thống thực. Khi triển khai cần cập nhật bằng thông tin chính xác và được ký bởi người có thẩm quyền.

~~~markdown
# Rules of Engagement — RT-EX-002
## A. Thông tin và phê duyệt
- Tổ chức/đơn vị sở hữu:
- Sponsor và người phê duyệt có thẩm quyền:
- Asset owner và white cell:
- Red team lead / SOC / incident commander:
- Version, ngày duyệt, ngày có hiệu lực:
- Mục tiêu và mức rủi ro chấp nhận:

## B. Phạm vi
- In-scope assets (asset ID, FQDN, IP, tenant, region, zone):
- Out-of-scope assets/data/people/services:
- Test source (định danh máy, IP, tài khoản):
- Môi trường và các phụ thuộc dùng chung:
- Bên thứ ba và giấy phép liên quan:
- UTC start/end, blackout windows:

## C. Hoạt động và ranh giới
- Được phép: [mô tả từng nhóm hành động có điều kiện]
- Chỉ khi có phê duyệt bổ sung:
- Cấm: [phá hoại, truy cập dữ liệu thật, DoS, ngoài scope ...]
- Giới hạn rates, concurrent connections, thời lượng, byte:
- Account/credential dùng cho bài thử:
- Dữ liệu canary, sink nhận, giới hạn thông tin:
- Test tool versions, cơ chế dừng và rollback:

## D. An toàn và điều phối
- SLO/telemetry cần giám sát:
- Stop conditions và quyền ra lệnh dừng:
- White cell contact, on-call contact, kênh dự phòng:
- Mức công khai cho blue team:
- Deconfliction / escalation / incident handling:
- Cách xác minh đã dừng và điều kiện tiếp tục:

## E. Bằng chứng và báo cáo
- Test ID, log format, UTC và đồng bộ thời gian:
- Bằng chứng cần giữ, classification, kho lưu:
- Hash / bàn giao / quyền xem:
- Thời hạn retention và điều kiện xóa:
- Tiêu chí thành công, cách đo phát hiện/phản ứng:
- Mẫu báo cáo cuối, hạn bàn giao, action owner:

## F. Cleanup và đóng bài thử
- Thu hồi test account/key/token, gỡ file/agent/rule tạm:
- Khôi phục cấu hình, so config diff và health:
- Người xác nhận cleanup và dịch vụ ổn định:
- Lessons learned, review action items:
- Phê duyệt đóng bài thử:
~~~

### 15.1. Ví dụ điền một số giới hạn cho lab

~~~yaml
exercise_id: RT-EX-002
classification: internal-restricted
purpose: "Xác minh phân đoạn VPN và khả năng phát hiện IDS/IPS"
environment: "controlled-lab"
scope:
  source_zone: "redteam-lab"
  destinations:
    - "test-application.example.test"
    - "192.0.2.10" # TEST-NET: địa chỉ minh họa, không phải đích thật
  excluded:
    - "production-databases"
    - "third-party-saas"
    - "employee-devices"
  time_window_utc: "2026-11-28T09:00:00Z/2026-11-28T10:00:00Z"
activities:
  allowed:
    - "Synthetic TCP connectivity check"
    - "Traffic mô phỏng tới endpoint test đã kiểm soát"
    - "Quan sát IDS/IPS và firewall logs tương ứng"
  prohibited:
    - "Denial of service hoặc làm cạn tài nguyên"
    - "Đọc và đưa dữ liệu thật ra ngoài"
    - "Thử mật khẩu thật hoặc vượt phạm vi"
safety:
  limits: "Điền theo baseline và phê duyệt của lab owner"
  stop_on: ["service-impact", "unexpected-scope", "unknown-real-incident"]
  authority: "white-cell-and-incident-commander"
data:
  only_synthetic: true
  evidence_storage: "approved-secure-repository"
  cleanup_required: true
approval:
  status: "NOT_APPROVED_EXAMPLE_ONLY"
~~~

Trường `approval.status` cố ý đặt `NOT_APPROVED_EXAMPLE_ONLY`. Không tự thay bằng `APPROVED` để sử dụng: người có quyền phải xác minh và phê duyệt phạm vi, số liệu rate/load, hành động và các đầu mối thật.

## 16. Case study: mô phỏng kiểm chứng phân đoạn VPN và IDS/IPS

### 16.1. Mục tiêu và bối cảnh giả định

Một tổ chức có VPN cho nhân viên, phân đoạn quản trị tách biệt và IDS/IPS quan sát luồng tới ứng dụng nội bộ. Đội bảo mật muốn biết: từ một tài khoản VPN không có quyền admin, chính sách có ngăn kết nối tới management zone không? Nếu có lưu lượng thử vượt policy, SOC có nhận tín hiệu đúng không?

Tổ chức chỉ cấp phép kiểm tra trong **lab tích hợp** với hệ thống giả và tài khoản thử, không cho phép truy cập production user data hoặc khai thác dịch vụ thật.

### 16.2. RoE thu gọn

| Mục | Nội dung minh họa |
|---|---|
| Tài sản | App lab, firewall policy lab, VPN test profile, IDS/IPS sensor lab |
| Nguồn | Máy kiểm thử được quản lý, chỉ trong redteam-lab |
| Đích | Management service giả và app lab có owner xác nhận |
| Được phép | Connectivity check và traffic tổng hợp với volume đã duyệt |
| Cấm | Brute force, tấn công làm cạn tài nguyên, persistence, exfil dữ liệu thật |
| Dữ liệu | Marker canary, không dùng credential người thật |
| Thời gian | Một cửa sổ UTC định trước, checkpoint mỗi phase |
| Giám sát | SOC theo dõi policy logs, IDS/IPS alert và health dashboard |
| Dừng | Firewall/IDS quá tải, app latency tăng bất thường, traffic đi ngoài scope |
| Cleanup | Thu hồi VPN test credential, xóa marker, xác minh không có rule tạm |

### 16.3. Thực hiện ở mức quan sát

1. Trước khi thử, xác nhận số liệu SLO, logging, source/destination, danh tính tài khoản thử và người có quyền dừng.
2. Tạo lưu lượng **được cho phép** tới app lab và lưu lượng **không được phép** tới endpoint giả thuộc management zone theo giới hạn đã duyệt.
3. Ghi UTC, test ID, kết quả từ client, firewall allow/deny và IDS/IPS events; không cố vượt rule bằng kỹ thuật không thuộc RoE.
4. SOC xác nhận nhận diện test event, đánh giá rule ID và escalation; nếu có dấu hiệu sự cố thật, dừng và chuyển incident response.
5. So sánh hành vi với policy mong đợi; nếu lưu lượng bị chặn nhưng không có alert, ghi riêng thiếu hụt phát hiện/observability.
6. Thu hồi tài khoản/token dùng thử, xác nhận không còn thay đổi tạm thời, báo cáo và đề xuất action item.

### 16.4. Kết quả và bài học

Giả định firewall đã chặn luồng trái policy, IDS/IPS có alert nhưng SOC chỉ thấy sau một khoảng trễ do pipeline. Khi đó cần phân biệt:

- **Phòng ngừa:** đường truy cập trái phép đã bị chặn theo rule.
- **Phát hiện:** sensor tạo event và gửi tới SIEM, có thể có ingest delay.
- **Ứng phó:** analyst acknowledge và triage theo playbook, có thể chậm do nhiễu.
- **An toàn bài thử:** dịch vụ hợp lệ không gián đoạn, không có dữ liệu thật bị truy cập, cleanup có xác nhận.

Những phát hiện này tạo ra action item như bổ sung correlation ID, kiểm tra pipeline latency, điều chỉnh mức ưu tiên cảnh báo, cải thiện runbook hoặc kiểm thử lại sau thay đổi. **Không cần phá policy để tăng “độ thành công” của red team**.

## 17. Xử lý sự cố ngoài dự kiến và kết thúc bài thử

### 17.1. Khi xuất hiện ảnh hưởng thật

Giả sử một lưu lượng tổng hợp khiến VPN gateway tăng CPU hoặc số phiên, gây timeout cho một số user:

1. Dừng phần test liên quan theo stop condition và xác nhận công cụ không còn chạy/retry.
2. Thông báo white cell, incident commander và owner qua kênh đã thống nhất, ghi mốc UTC.
3. Ưu tiên giảm tác động và khôi phục: rollback theo playbook do người vận hành có quyền thực hiện; red team không tự sửa hệ thống ngoài thẩm quyền.
4. Bảo toàn bằng chứng tối thiểu (metric, log, config/version, test ID, timeline), không phát tán dữ liệu nhạy cảm.
5. Phân tích tác động và nguyên nhân với nhóm liên quan, quyết định hủy/gia hạn/chỉnh RoE; việc tiếp tục phải được phê duyệt lại.
6. Ghi phát hiện vận hành và action item, kể cả khi mục tiêu kiểm thử chưa hoàn thành.

Không coi tai nạn làm gián đoạn là “bằng chứng thành công của tấn công”; đó là sự kiện cần xử lý theo quy trình an toàn.

### 17.2. Checklist cleanup

- Tài khoản thử, service principal, token, SSH key/cert và VPN session đã được thu hồi/đóng.
- File canary, test marker, agent, cron/job và endpoint thử đã được gỡ theo phạm vi.
- Firewall/NAT/IDS/IPS rules tạm, redirect, route và quyền cloud được đối chiếu với cấu hình trước thử.
- Hệ thống nghiệp vụ và đường quản trị hợp lệ đạt baseline về availability/latency.
- Log/evidence được lưu đúng kho và retention; dữ liệu dư thừa/working copy được xử lý theo chính sách.
- Asset owner/SOC xác nhận trạng thái, tồn đọng nếu có được gán owner và thời hạn.
- Báo cáo cuối ghi các phần được làm, phần bị dừng, không làm, giới hạn của bằng chứng và phê duyệt đóng.

## 18. Những sai lầm thường gặp khi xây dựng RoE

1. **Chỉ ghi dải IP mà không xác nhận owner:** IP động hoặc NAT/CDN có thể dẫn tới tài sản bên thứ ba.
2. **Xem scan nhẹ là không cần phép:** kết nối thăm dò vẫn có thể tạo tải, gây lỗi trên thiết bị cũ hoặc vi phạm scope.
3. **Cho phép “mọi kỹ thuật cần thiết”:** không có giới hạn hoạt động, mức tác động, dữ liệu và quyền dừng.
4. **Không xác định mức phơi bày dữ liệu:** tài khoản thử nhìn thấy production data nhưng không có quy tắc xử lý.
5. **Không có người trực và kênh dừng:** bài thử tiếp tục khi SOC đang xử lý sự cố thật.
6. **Không ghi rõ blind/deconfliction:** SOC phong tỏa không chủ đích hoặc red team làm nhiễu bằng chứng.
7. **Dùng private key hoặc credential dùng chung:** khó thu hồi, khó xác định người chịu trách nhiệm.
8. **Không kiểm tra giới hạn công cụ:** một probe tự động retry hoặc mở rộng dải đích ngoài ý muốn.
9. **Thiếu clock synchronization:** thời gian phát hiện/ứng phó bị tính sai giữa SIEM, firewall và máy kiểm thử.
10. **Không làm sạch tài nguyên test:** để lại token, agent, chính sách tạm hoặc file marker.
11. **Gắn nhãn “lỗ hổng” chỉ từ suy luận:** cần xác minh điều kiện, quyền và nguồn quan sát; không buộc phải khai thác.
12. **Sửa RoE sau khi chạy để hợp thức hóa:** phải ghi version, thời điểm hiệu lực và phê duyệt trước hoạt động.
13. **Đánh đồng thiếu alert với thiếu phòng vệ:** có thể traffic bị chặn trước sensor hoặc sensor không quan sát được.
14. **Ưu tiên điểm số thành công hơn an toàn:** cố vượt giới hạn để đạt “kill chain” có thể làm hỏng mục đích kiểm thử.

## 19. Checklist chuẩn bị, vận hành và đóng bài

### Trước khi chạy

- [ ] Có văn bản/phê duyệt rõ bên sở hữu, người duyệt, scope và thời hạn.
- [ ] Liệt kê in-scope và out-of-scope theo asset ID/FQDN/IP/tenant/zone và dữ liệu.
- [ ] Kiểm tra sự phụ thuộc cloud/CDN/SaaS, mạng người dùng thật và hệ thống chung.
- [ ] Các hành động được phép, có điều kiện và bị cấm được viết cụ thể.
- [ ] Có giới hạn tải/tần suất/dữ liệu, stop conditions và phương án rollback.
- [ ] Có người giám sát, liên lạc dự phòng, white cell, SOC và incident commander.
- [ ] Có tài khoản thử, canary data, vault và nơi lưu chứng cứ phù hợp.
- [ ] Công cụ và cấu hình đã được kiểm tra trong lab; có cơ chế dừng đáng tin.
- [ ] Tiêu chí thành công, phương pháp đo và phạm vi quan sát được thống nhất.

### Trong diễn tập

- [ ] Mỗi hoạt động gắn test ID, UTC, nguồn/đích, phiên bản tool và phase.
- [ ] Chỉ thực hiện trong cửa sổ và hạn mức được duyệt; theo dõi sức khỏe hệ thống.
- [ ] Dừng phần liên quan khi xuất hiện dấu hiệu ảnh hưởng, dữ liệu thật hoặc tài sản ngoài scope.
- [ ] Không tự mở rộng quyền; đổi RoE phải được duyệt và phát hành version mới.
- [ ] Phân biệt bài thử với sự cố thật qua white cell và cơ chế deconfliction.
- [ ] Ghi dấu vết đúng mức, không chứa credential/payload thật vượt phạm vi.

### Khi kết thúc

- [ ] Có danh sách đầy đủ hoạt động đã thực hiện, chưa làm, bị dừng và nguyên nhân.
- [ ] Đối chiếu log firewall, IDS/IPS, DNS, IAM và SOC timeline theo clock uncertainty.
- [ ] Thu hồi tài khoản, token, file, route/rule tạm, agent và xác minh rollback.
- [ ] Asset owner xác nhận dịch vụ và kiểm soát an ninh đã trở về trạng thái mong đợi.
- [ ] Bằng chứng được lưu đúng phân loại, có hash/retention/quyền, không phát tán rộng.
- [ ] Báo cáo có tác động thực, giới hạn chứng cứ, hành động cải tiến, owner và thời hạn.
- [ ] Có phê duyệt đóng diễn tập và kế hoạch re-test khi cần.

## 20. Câu hỏi tự kiểm tra

**1. Một người quản trị cloud nói “bạn cứ kiểm thử toàn bộ account này”. Đã đủ RoE chưa?**

Chưa. Cần xác định người có thẩm quyền, các tài sản và tenant thuộc phạm vi, dịch vụ dùng chung, thời hạn, cách thử, giới hạn tác động, dữ liệu và trách nhiệm. Quyền admin kỹ thuật không tự xác nhận quyền cho phép mọi hành động.

**2. Khi một endpoint đổi IP sang dải của CDN bên thứ ba trong lúc diễn tập, red team có thể tiếp tục theo FQDN không?**

Không tự động. Cần kiểm tra quyền và điều kiện dịch vụ của bên thứ ba, ranh giới scope và policy nhà cung cấp; nếu chưa rõ, dừng phần liên quan và xin đánh giá hoặc dùng endpoint giả.

**3. Vì sao giới hạn packets/giây vẫn chưa đủ để bảo vệ dịch vụ?**

Tác động còn phụ thuộc request nội dung gì, kết nối đồng thời, retries, session table, CPU/memory và trạng thái của thiết bị. RoE phải có theo dõi và stop conditions theo baseline thực.

**4. Có cần dùng dữ liệu khách hàng thật để kiểm thử DLP không?**

Thường không. Nên dùng file canary có nội dung giả, đích nhận do tổ chức kiểm soát và tiêu chí phát hiện tương ứng; xử lý dữ liệu thật cần thẩm quyền/quy trình riêng.

**5. Nếu SOC phát hiện một sự cố thật trong lúc diễn tập, ai quyết định tiếp tục?**

Thực hiện stop/pause theo RoE; white cell và incident commander/owner có thẩm quyền đánh giá tác động, xử lý sự cố thật và chỉ cho phép tiếp tục sau khi được xác nhận hợp lệ. Không vì mục tiêu diễn tập mà bỏ qua incident response.

**6. Vì sao “phishing được phép” vẫn là mô tả quá mơ hồ?**

Cần danh sách người nhận, kênh, nội dung, thời gian, loại dữ liệu được thu, phạm vi không gửi và thủ tục khi người nhận báo cáo. Không tự diễn giải thành cho phép thu mật khẩu thật hoặc gây tác động tâm lý không cần thiết.

**7. RoE khác test plan ở điểm nào?**

RoE xác định ranh giới ủy quyền, điều kiện và trách nhiệm; test plan mô tả trình tự kỹ thuật trong các ranh giới đó. Test plan không thể hợp thức hóa hoạt động nằm ngoài RoE.

**8. Blue team không có alert nhưng firewall chặn mọi traffic trái policy. Kết luận gì?**

Phòng ngừa có thể đã hoạt động; khả năng phát hiện cần đánh giá riêng theo vị trí sensor, logging, SIEM pipeline và mục tiêu đã định. Không đồng nhất thiếu alert với thất bại của toàn hệ thống.

**9. Tại sao cleanup cần có xác nhận của asset owner?**

Vì red team có thể không nhìn thấy toàn bộ side effect: token còn hiệu lực, cấu hình tạm, session, agent hoặc ảnh hưởng dịch vụ. Chủ tài sản cần kiểm tra trạng thái vận hành và baseline trước khi đóng bài thử.

---

**Ghi nhớ:** Một RoE tốt biến mục tiêu mô phỏng tấn công thành **hoạt động có ủy quyền, giới hạn kiểm chứng được, rủi ro được kiểm soát, bằng chứng có thể tái lập và cơ chế dừng khẩn cấp**. Thành công của red team không nằm ở việc vượt mọi ranh giới, mà ở chỗ giúp tổ chức hiểu chính xác năng lực phòng vệ và cải thiện nó mà không tạo thêm sự cố.
