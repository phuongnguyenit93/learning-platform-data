# Adversary có khả năng gì? Mô hình hóa năng lực đối thủ trong an ninh mạng

Khi thiết kế mạng an toàn, câu hỏi **“Adversary (đối thủ) có khả năng gì?”** quan trọng hơn việc chỉ hỏi “Có hacker nào tấn công không?”. Hai đối thủ đều muốn lấy dữ liệu nhưng năng lực rất khác nhau: một người dùng Internet chỉ gửi được yêu cầu tới dịch vụ công khai; một thiết bị đã nằm trong VLAN nội bộ có thể tiếp xúc với broadcast và một số dịch vụ nội bộ; một quản trị viên bị chiếm tài khoản có thể thay đổi cả định tuyến, chính sách firewall và cấu hình DNS.

**Threat modeling (mô hình hóa mối đe dọa)** cần nêu rõ đối thủ có thể quan sát, truy cập, gửi, thay đổi, giả mạo hoặc làm gián đoạn điều gì; **từ vị trí nào, với quyền gì và trong điều kiện nào**. Đây là cơ sở để chọn biện pháp phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và hạ tầng cloud của học phần **SECURITY_NETWORK_SECURITY**, thuộc chương **Threat modeling mạng**.

Sau bài này, người học có thể phân biệt mục tiêu với năng lực đối thủ, lập hồ sơ adversary có điều kiện và giới hạn rõ ràng, gắn năng lực với đường tấn công thực tế, đồng thời đánh giá tác dụng và khoảng trống của từng lớp phòng vệ.

## 1. Phân biệt adversary, mục tiêu, năng lực và bề mặt tấn công

**Adversary** là chủ thể có thể cố ý gây hại cho hệ thống: cá nhân bên ngoài, người nội bộ lạm dụng quyền, nhóm tấn công hoặc một bên đã chiếm quyền kiểm soát thiết bị/tài khoản. Trong một số mô hình, đối thủ còn được biểu diễn như **năng lực mà người tấn công hiện có**, thay vì cố gắng xác định danh tính hay động cơ cụ thể.

Các khái niệm thường bị nhầm lẫn:

| Khái niệm | Câu hỏi trả lời | Ví dụ trong mạng doanh nghiệp |
|---|---|---|
| **Mục tiêu (goal/objective)** | Đối thủ muốn đạt kết quả gì? | Lấy dữ liệu khách hàng, làm gián đoạn VPN, kiểm soát DNS |
| **Năng lực (capability)** | Đối thủ thực sự làm được gì ở thời điểm xét? | Gửi gói tới IP public, đọc log DNS, sửa một security group |
| **Vị trí (position/vantage point)** | Đối thủ đang quan sát/tác động từ đâu? | Internet, cùng VLAN khách, thiết bị định tuyến, máy trạm bị chiếm |
| **Quyền hạn (privilege)** | Đối thủ đã có quyền gì? | Không có danh tính, tài khoản người dùng, quyền cấu hình switch |
| **Bề mặt tấn công (attack surface)** | Những điểm nào có thể bị tiếp cận hoặc tương tác? | Cổng HTTPS công khai, cổng access switch, API quản trị cloud |
| **Đường tấn công (attack path)** | Những bước và điều kiện nào dẫn đến mục tiêu? | Lộ thông tin đăng nhập → vào VPN → truy cập subnet quản trị |
| **Rủi ro (risk)** | Khả năng xảy ra và tác động của kịch bản là gì? | Mất bí mật dữ liệu do tài khoản cloud quá quyền |

**Ví dụ:** “Đối thủ muốn đọc nội dung HTTPS” là **mục tiêu**, không chứng minh họ **có khả năng** đọc dữ liệu. Người quan sát đường truyền có thể thấy một số metadata như IP đích, lưu lượng và thời điểm, nhưng việc đọc nội dung trong phiên TLS được cấu hình đúng thường đòi hỏi thêm điều kiện như chiếm endpoint, chiếm khóa liên quan hoặc khiến khách hàng chấp nhận một điểm kết thúc TLS mà họ kiểm soát.

Mô hình tốt luôn tách ba câu:

1. **Đối thủ mong đạt được gì?**
2. **Đối thủ đã có khả năng và phạm vi hành động nào?**
3. **Muốn chuyển từ khả năng hiện tại đến mục tiêu, còn phải vượt qua những điều kiện nào?**

Không được tự nâng “có thể gửi gói tin” thành “có thể đăng nhập”, hoặc “cùng mạng Wi-Fi” thành “đọc được mọi dữ liệu”.

## 2. Năm chiều năng lực cần xem xét

Có thể mô tả adversary theo năm chiều, mỗi chiều phải gắn với phạm vi mạng hoặc tài nguyên cụ thể.

### 2.1. Quan sát (observe)

Đối thủ **nhìn thấy thông tin gì**?

- **Thông tin công khai:** IP/domain đang quảng bá, giao diện Internet công khai, thông tin DNS public, tài liệu công khai.
- **Metadata luồng mạng:** địa chỉ IP, cổng, kích thước gói, thời gian, hướng lưu lượng, đôi khi tên miền hoặc thông tin giao thức hiện ra tùy lớp mã hóa và thiết kế.
- **Payload không mã hóa:** nội dung một số giao thức khi đối thủ thực sự nằm trên đường quan sát hoặc kiểm soát điểm thu.
- **Log và cấu hình:** lịch sử truy vấn DNS, lưu lượng NetFlow, log reverse proxy, sơ đồ VLAN, firewall rule nếu đối thủ có quyền đọc tương ứng.
- **Dữ liệu sau khi giải mã:** trường hợp đối thủ kiểm soát endpoint, dịch vụ xử lý, điểm kết thúc TLS hoặc một nơi hợp lệ giữ bản rõ.

Năng lực quan sát không đồng nhất với việc có quyền thay đổi dữ liệu. **Một packet capture từ một cổng bình thường trên switch không mặc nhiên thấy toàn bộ lưu lượng giữa các cổng khác.** SPAN/mirroring, network tap hoặc quyền trên thiết bị chuyển mạch sẽ thay đổi phạm vi quan sát.

### 2.2. Tác động lên lưu lượng (inject, alter, block)

Đối thủ **có thể gửi hoặc kiểm soát những gói/frame nào**?

| Khả năng | Diễn giải | Điều kiện và giới hạn quan trọng |
|---|---|---|
| **Send/inject** | Phát gói mới hoặc yêu cầu ứng dụng tới một đích | Phải có kết nối/đường mạng phù hợp; firewall, ACL, authentication có thể chặn |
| **Spoof** | Giả địa chỉ nguồn hoặc danh tính ở một lớp | Địa chỉ có thể giả không có nghĩa đối thủ nhận được phản hồi hoặc vượt qua xác thực |
| **Modify** | Sửa nội dung gói/frame đang đi qua | Thường cần quyền trên đường truyền/thiết bị trung gian; integrity checks, TLS/MACsec có thể phát hiện hoặc ngăn sửa đổi hữu hiệu |
| **Drop/block** | Loại bỏ, từ chối chuyển tiếp hay làm gián đoạn | Có thể xảy ra khi đối thủ điều khiển thành phần đường đi; DoS từ xa cũng có thể gây nghẽn trước nơi nhận |
| **Delay/reorder/replay** | Làm chậm, đảo thứ tự hoặc gửi lại thông điệp cũ | Tùy vị trí, giao thức và trạng thái phiên; các giao thức bảo vệ có cơ chế chống phát lại khác nhau |
| **Redirect** | Điều hướng người dùng/lưu lượng sang điểm khác | Cần kiểm soát DNS, định tuyến, gateway, proxy hoặc một cơ chế chuyển hướng được tin cậy |
| **Create configuration changes** | Sửa rule firewall, route, ACL, security group, VPN policy | Cần đặc quyền quản trị hoặc quyền API thực tế; ảnh hưởng có thể rất rộng |

Đặc biệt, **đối thủ ở ngoài đường truyền (off-path)** và **đối thủ trên đường truyền (on-path)** khác nhau: người off-path có thể gửi yêu cầu tới dịch vụ nhưng thường không trực tiếp thấy hay sửa luồng giữa hai endpoint; người on-path có thể quan sát hoặc can thiệp lưu lượng đi qua thành phần do họ kiểm soát, song vẫn chịu giới hạn của bảo vệ mật mã.

### 2.3. Danh tính và quyền (identity & privilege)

Khả năng thao tác với hạ tầng phụ thuộc vào quyền đã có:

- **Không xác thực:** chỉ sử dụng được các cổng/giao diện được công khai hoặc cho phép kết nối trước xác thực.
- **Người dùng thường:** vào VPN, Wi-Fi hoặc tài nguyên nội bộ theo vai trò được cấp.
- **Thiết bị/workload đã tham gia mạng:** có thể giao tiếp với các endpoint được ACL/segmentation cho phép; một máy bị chiếm không mặc nhiên có quyền quản trị mạng.
- **Quản trị hạ tầng:** có thể tác động lên switch, firewall, DNS, IAM hoặc cấu hình cloud trong đúng phạm vi được cấp.
- **Quyền dịch vụ/CI/CD:** token hoặc service account có thể thay đổi những tài nguyên cho phép bởi IAM và các chính sách tổ chức.

Phải phân biệt **đăng nhập được** với **được phép thực thi hành động nhạy cảm**. Các hệ thống thực tế có RBAC, chính sách điều kiện, phân tách nhiệm vụ, xác thực đa yếu tố và ghi nhận phiên. Đối thủ có một credential bị lộ chỉ có khả năng của credential đó, trừ khi chứng minh được con đường nâng quyền.

### 2.4. Nguồn lực và thời gian (resources & duration)

Năng lực còn phụ thuộc vào tài chính, số lượng máy hoặc danh tính điều khiển, độ bền của điểm bám, thời gian có mặt trên mạng và khả năng hoạt động liên tục. Một botnet phân tán có thể gửi tổng lưu lượng lớn mà không cần quyền truy cập nội bộ; một insider có thể kiểm soát ít thiết bị nhưng hiểu sơ đồ mạng và lịch bảo trì.

Các yếu tố nguồn lực ảnh hưởng **mức độ khả thi và xác suất**, nhưng không nên gán số lượng bot, ngân sách hay thời gian chiếm quyền nếu không có căn cứ. Nếu chưa biết, hãy ghi giả định hoặc đánh dấu **chưa xác minh**.

### 2.5. Phạm vi và ranh giới tin cậy (scope & trust boundary)

Một adversary có thể mạnh ở phạm vi này nhưng yếu ở phạm vi khác:

- Có quyền đọc DNS log nhưng không thể thay đổi bản ghi DNS.
- Điều khiển host trong VLAN 20 nhưng không thể gửi trực tiếp gói sang VLAN 10 vì firewall chặn.
- Sửa được security group của một workload nhưng không có quyền thay route table toàn bộ VPC.
- Kiểm soát Wi-Fi của khách nhưng không kiểm soát máy trạm nhân viên.
- Truy cập được kết nối VPN nhưng bị giới hạn đến một subnet hoặc nhóm ứng dụng.

**Ranh giới tin cậy** là nơi giả định về quyền và mức độ tin cậy thay đổi: Internet ↔ DMZ, guest Wi-Fi ↔ LAN nhân viên, người dùng ↔ mặt phẳng quản trị, workload ↔ control plane cloud, subnet ứng dụng ↔ subnet dữ liệu.

## 3. Các vị trí adversary trong một hệ thống mạng

Không nên chỉ chia người tấn công thành “bên trong” và “bên ngoài”. Vị trí tác động trực tiếp đến quyền quan sát và khả năng tiếp cận.

| Vị trí / hồ sơ | Khả năng có thể có | Không nên tự giả định |
|---|---|---|
| **Remote, off-path** từ Internet | Gửi yêu cầu tới dịch vụ public, quan sát phản hồi của chính mình, gây tải lên dịch vụ công khai | Thấy traffic nội bộ, đọc phiên TLS của người khác, truy cập cổng chỉ mở nội bộ |
| **Người ở cùng phân đoạn L2** | Gửi frame trên VLAN được cấp, thấy broadcast/multicast thích hợp, giao tiếp với host cùng phân đoạn nếu chính sách cho phép | Tự động đọc mọi unicast của switch, điều khiển mọi host trong VLAN |
| **Thiết bị ở trên đường truyền (on-path)** | Có thể quan sát, ngắt, sửa hoặc chuyển hướng lưu lượng đi qua thành phần bị điều khiển | Giải mã TLS/MACsec một cách tự động, giả được chứng chỉ đáng tin cậy |
| **Endpoint/workload bị xâm nhập** | Đọc dữ liệu/quyền của tiến trình hoặc tài khoản bị chiếm; gửi yêu cầu từ vị trí host | Đã có đặc quyền hệ thống cao nhất, đã chiếm thiết bị khác, tự động truy cập mọi subnet |
| **Thành phần hạ tầng bị kiểm soát** | Thay route/ACL/VLAN/DNS hoặc mirror traffic theo quyền trên thiết bị | Có quyền tương tự trên toàn bộ tổ chức nếu chỉ điều khiển một thiết bị |
| **Cloud principal bị lộ quyền** | Gọi API quản trị tài nguyên nằm trong IAM scope, ví dụ sửa security group cụ thể | Đã có quyền đọc dữ liệu workload, KMS key hoặc mọi tài khoản cloud |
| **Người có tiếp cận vật lý hoặc RF** | Cắm vào cổng để lộ, can thiệp kết nối, quan sát/gây nhiễu vô tuyến tùy thiết bị và môi trường | Đi xuyên qua 802.1X, WPA3, kiểm soát cổng hoặc lớp mã hóa mà không có tiền đề bổ sung |

Những nhóm này **không tạo thành thang sức mạnh tuyệt đối**. Kẻ DDoS từ Internet có thể làm nghẽn đường uplink lớn hơn khả năng của một user VPN; ngược lại, một tài khoản quản trị DNS bị chiếm có thể thay đổi hướng truy cập dịch vụ mà không điều khiển được cáp hay router.

### 3.1. Cùng mạng không có nghĩa on-path

Ví dụ laptop X và laptop Y cắm vào switch Ethernet cùng VLAN. X có thể thấy một số broadcast/multicast, gửi lưu lượng đến Y và giao tiếp với gateway theo chính sách; X **không mặc nhiên nhận được** mọi frame unicast Y ↔ gateway. Để trở thành on-path, đối thủ thường cần một điều kiện bổ sung như quyền trên thiết bị trung gian, thao túng phân giải láng giềng nếu mạng cho phép, cấu hình mirror hoặc khả năng kiểm soát một node trên đường đi.

Ví dụ khác, hai máy ở cùng SSID Wi-Fi vẫn có thể bị chặn nói chuyện trực tiếp bởi **client isolation**. Có cùng SSID không đủ để kết luận chúng ở cùng phạm vi quảng bá hay đọc được dữ liệu lẫn nhau.

### 3.2. Trên đường truyền không đồng nghĩa đọc được bản rõ

Một router, proxy hoặc node chuyển tiếp nằm trên đường đi có thể biết IP và một số thông tin giao thức, có thể chặn gói hoặc gây lỗi kết nối. Tuy nhiên, với TLS được xác thực đúng, nó không nên đọc được payload hay sửa payload mà endpoint chấp nhận, nếu không nắm khóa/không kiểm soát một đầu mút hay cơ chế tin cậy của TLS.

Điều này dẫn đến hai loại mục tiêu khác nhau:

- **Confidentiality/integrity:** bảo vệ nội dung và việc không bị sửa đổi; HTTPS, mTLS, VPN, MACsec có thể phát huy tác dụng ở phạm vi tương ứng.
- **Availability:** đường truyền vẫn có thể bị nghẽn hoặc ngắt dù nội dung đã mã hóa hoàn hảo.

## 4. Mô hình adversary ở các tầng mạng

| Tầng/phạm vi | Dữ liệu và điều khiển mà đối thủ có thể nhắm đến | Ví dụ kịch bản | Lớp kiểm soát phù hợp |
|---|---|---|---|
| **L1 — Vật lý** | Cổng, cáp, bộ thu phát, nguồn, sóng RF | Ngắt kết nối, gây nhiễu, cắm thiết bị trái phép | An ninh vật lý, dự phòng, kiểm tra cáp, khóa cổng, kiểm soát RF |
| **L2 — Liên kết** | MAC, VLAN, ARP/ND, BPDU, truy cập switch/AP | MAC spoofing, ARP spoofing khi đủ điều kiện, cổng trunk sai cấu hình | 802.1X, phân đoạn, DAI/DHCP snooping, BPDU Guard, WPA2/WPA3 |
| **L3 — Mạng** | IP, tuyến đường, ICMP, ACL, gateway | Gửi traffic tới subnet bị lộ, định tuyến sai, flood | Firewall/ACL, phân vùng mạng, kiểm soát định tuyến, anti-spoofing |
| **L4 — Giao vận** | TCP/UDP, kết nối và trạng thái | Lạm dụng kết nối mở, gây quá tải cổng/dịch vụ | Rate limit, stateful filtering, chống DDoS, hardening dịch vụ |
| **L7 — Ứng dụng/DNS/Identity** | HTTP, DNS, VPN, phiên đăng nhập, API quản trị | Lạm dụng token, điều khiển DNS nếu có quyền, khai thác API | TLS/mTLS, MFA, xác thực/ủy quyền, DNSSEC khi phù hợp, bảo vệ API |
| **Control plane hạ tầng/cloud** | IAM, route table, security group, firewall policy, DNS zones, KMS policy | Thay đổi chính sách mạng bằng quyền cloud bị lộ | IAM tối thiểu, phê duyệt thay đổi, log audit, guardrail và kiểm soát drift |

Một đối thủ có thể **bắt đầu ở một tầng nhưng ảnh hưởng tầng khác**. Chẳng hạn, máy trạm bị chiếm (endpoint) có thể phát các gói ARP tới VLAN của nó (L2), tìm các API nội bộ được phép (L7) hoặc lợi dụng quyền cloud trên máy (control plane). Một bảng phân loại tầng chỉ để tránh bỏ sót, không giới hạn đường tấn công trong một tầng cố định.

## 5. Mô hình “đối thủ điều khiển mạng” và những giả định mật mã

Trong phân tích giao thức, người ta đôi khi dùng mô hình đối thủ mạng rất mạnh, thường được gọi theo hướng **Dolev–Yao**: đối thủ có thể nhận, tạo, chặn, phát lại và sắp xếp các thông điệp đi qua mạng họ kiểm soát; họ chỉ thực hiện các thao tác mật mã mà mô hình cho phép, không tùy ý phá các nguyên thủy mật mã được giả định an toàn.

Đây là một mô hình hữu ích để kiểm tra giao thức trước đối thủ chủ động, **không phải mô tả mặc định của mọi người dùng Internet hoặc mọi thiết bị cùng VLAN**. Khi áp dụng, cần ghi rõ:

- **Mạng nào** thuộc quyền kiểm soát của đối thủ: đường Internet cụ thể, LAN khách, VPN, một kênh ứng dụng hay toàn bộ giao vận giữa hai đầu?
- Đối thủ có thể **quan sát, chặn, sửa, phát lại, thêm thông điệp** tới phạm vi nào?
- **Khóa, chứng chỉ và thiết bị đầu cuối** có còn bí mật và đáng tin hay đã bị chiếm?
- Hệ thống có **xác thực bên đối tác, kiểm tra tính toàn vẹn, chống phát lại và đảm bảo freshness** hay không?
- Nội dung nào vẫn lộ dưới dạng metadata, DNS, IP/port, kích thước và thời điểm liên lạc?

**Ví dụ:** giả sử adversary điều khiển một router trung gian nhưng không có khóa TLS và client kiểm tra chứng chỉ đúng. Mô hình vẫn nên cho phép đối thủ làm mất kết nối, chậm gói, quan sát nhiều metadata hoặc chuyển hướng packet. Nó **không được tự giả định** đối thủ sửa nội dung HTTPS mà client vẫn chấp nhận.

Ngược lại, nếu adversary kiểm soát máy chủ ứng dụng nơi TLS kết thúc, họ có thể thấy dữ liệu bản rõ mà ứng dụng xử lý; khi đó mã hóa trên đường truyền không giải quyết toàn bộ rủi ro.

### 5.1. Các cơ chế bảo vệ giới hạn năng lực nào?

| Cơ chế | Năng lực bị giảm trong điều kiện triển khai đúng | Giới hạn cần hiểu |
|---|---|---|
| **TLS / HTTPS** | Nghe lén và sửa đổi payload ứng dụng trên đường truyền giữa các đầu TLS | Không ngăn nghẽn mạng, không bảo vệ endpoint đã bị chiếm, không che mọi metadata |
| **mTLS** | Bổ sung xác thực hai chiều cho các đầu kết nối TLS | Quyền ứng dụng vẫn cần kiểm tra; mất khóa/chứng chỉ làm thay đổi giả định |
| **VPN IPsec / WireGuard / TLS VPN** | Bảo vệ lưu lượng trong phạm vi tunnel, xác thực các đầu tunnel theo cấu hình | Không tự bảo vệ dữ liệu sau khi thoát tunnel; không tự chặn lateral movement trong mạng đích |
| **MACsec** | Bảo vệ tính bí mật, toàn vẹn và chống phát lại ở liên kết Ethernet được hỗ trợ/cấu hình | Bảo vệ từng liên kết, không mặc nhiên xuyên suốt nhiều hop |
| **WPA2/WPA3** | Bảo vệ truy cập và lưu lượng qua liên kết Wi-Fi theo chế độ và cấu hình | Bảo mật Wi-Fi không thay thế TLS, xác thực ứng dụng hay phân đoạn mạng |
| **DNSSEC** | Giúp bên kiểm tra xác minh nguồn gốc và tính toàn vẹn của dữ liệu DNS được ký | Không mã hóa truy vấn DNS; không sửa được endpoint hay DNS zone bị chiếm quyền quản trị hợp lệ |
| **DoH / DoT** | Mã hóa kết nối giữa client và resolver hỗ trợ | Resolver vẫn có thể thấy truy vấn; cần chính sách tin cậy resolver |
| **802.1X** | Kiểm soát quyền tham gia mạng khi kết hợp định danh và policy phù hợp | Chứng thực vào mạng không tự làm endpoint an toàn hoặc thay thế ACL |
| **Firewall / ACL** | Hạn chế luồng được phép đi qua điểm thực thi policy | Không thay thế bảo vệ cùng VLAN, không kiểm soát tất cả lối đi nếu tồn tại đường bypass |
| **IDS/IPS** | Phát hiện hoặc ngăn một tập hành vi theo nơi quan sát, chữ ký và phân tích | Không mặc nhiên thấy lưu lượng đã giải mã hoặc phát hiện mọi hành vi mới |

Chọn kiểm soát bằng cách hỏi **“cơ chế này chặn được năng lực cụ thể nào, tại ranh giới nào?”**, thay vì đánh dấu “đã có firewall/VPN” rồi coi mọi mối đe dọa đã được loại bỏ.

## 6. Mô tả năng lực theo điều kiện, không theo nhãn chung

Các nhãn như “kẻ tấn công mạnh”, “người dùng độc hại”, “hacker nội bộ” quá mơ hồ. Một đặc tả hữu ích có các trường:

| Trường trong hồ sơ | Cách viết có thể kiểm tra |
|---|---|
| **Adversary ID / vai trò** | A-GUEST: một thiết bị chưa được quản trị trên guest Wi-Fi |
| **Điểm đứng** | SSID Guest, VLAN 50, chỉ có route Internet |
| **Quyền sẵn có** | Người dùng hợp lệ của guest Wi-Fi; không có tài khoản nhân viên |
| **Có thể quan sát** | Kết nối do chính thiết bị tạo, metadata truyền trên liên kết có thể thu được, dữ liệu public |
| **Có thể chủ động** | Gửi yêu cầu tới dịch vụ Internet và các đích được policy guest cho phép |
| **Không thể giả định** | Truy cập thẳng subnet quản trị, giải mã HTTPS của nhân viên, sửa cấu hình AP |
| **Tiền đề để leo thang** | Có cấu hình sai ở guest isolation/ACL, có credential bị lộ, hoặc một điểm yếu khác được chứng minh |
| **Tài sản mục tiêu** | Portal nội bộ, DNS resolver, thiết bị quản trị |
| **Bằng chứng** | Sơ đồ VLAN, policy firewall, log kết nối, thử nghiệm kết nối được cho phép |
| **Độ chắc chắn** | Đã kiểm tra / giả định / chưa xác minh; nêu người chịu trách nhiệm xác minh |

Cụm **“có thể”** cần thể hiện ba cấp độ khác nhau:

- **Đã xác nhận:** có bằng chứng từ cấu hình, tài liệu vận hành, kết quả kiểm tra hợp lệ hoặc sự kiện từng xảy ra.
- **Giả định dùng để phân tích:** chưa được xác nhận nhưng hợp lý và được ghi rõ điều kiện, ví dụ “nếu một tài khoản IAM có quyền thay route table bị lộ”.
- **Chưa rõ:** thông tin thiếu; đây là câu hỏi cần thu thập thêm, không nên điền bằng suy đoán.

### 6.1. Mẫu hồ sơ có thể tái sử dụng

~~~yaml
adversary_id: A-02
objective: "Làm gián đoạn kết nối từ người dùng đến ứng dụng nội bộ"
vantage_point: "Thiết bị của khách tại VLAN 50"
current_access:
  - "Có kết nối Wi-Fi Guest"
  - "Được truy cập Internet theo firewall policy"
observations:
  - "Traffic và phản hồi của chính thiết bị"
active_capabilities:
  - "Gửi yêu cầu tới các đích mà ACL cho phép"
not_assumed:
  - "Quyền quản trị AP/switch"
  - "Khả năng đọc TLS của người khác"
  - "Khả năng truy cập trực tiếp VLAN 10"
required_preconditions:
  - "Phải chứng minh có đường từ VLAN 50 đến tài sản cần tấn công"
trust_boundaries:
  - "Guest Wi-Fi -> LAN nhân viên"
evidence:
  - "Bản cấu hình VLAN, ACL đã được người quản trị xác minh"
confidence: "partially_verified"
~~~

Mẫu trên là **dữ liệu minh họa trong bài**, không đại diện cho cấu hình của một hệ thống thật. Các trường **not_assumed** và **required_preconditions** đặc biệt hữu ích để ngăn đội phân tích vô tình cấp cho đối thủ những quyền mà họ chưa có.

## 7. Từ năng lực đến đường tấn công

Hãy dùng một tình huống doanh nghiệp có mạng nhân viên, mạng khách, dịch vụ nội bộ và workloads cloud:

~~~mermaid
flowchart LR
    I[Internet] --> E[Firewall biên]
    E --> W[Ứng dụng public HTTPS]
    E --> V[VPN Gateway]
    V --> F[LAN nhân viên]
    G[Guest Wi-Fi / VLAN 50] --> GF[Policy guest]
    GF --> I
    F --> IF[Firewall nội bộ]
    IF --> D[Ứng dụng & dữ liệu nội bộ]
    W --> CF[Cloud network policy]
    CF --> DB[(CSDL riêng tư)]
    CP[Cloud IAM / Control plane] -.cấu hình.-> CF
    CP -.cấu hình.-> W
~~~

**Giới hạn giả định:** sơ đồ chỉ mô tả các liên kết logic cần đánh giá. Mũi tên không khẳng định rằng mọi gói đều được phép qua firewall; luật cụ thể quyết định reachability. Người phân tích phải xác minh đường đi thực tế, bao gồm public endpoint, private endpoint, NAT, route, service mesh và quyền IAM.

### 7.1. Kịch bản A — đối thủ từ Internet

**Mục tiêu:** lấy dữ liệu trong CSDL private.

**Khả năng ban đầu:** tìm thấy ứng dụng HTTPS public và gửi yêu cầu hợp lệ tới nó; chưa có tài khoản hay kết nối đến subnet DB.

Một đường tấn công tiềm năng cần các điều kiện liên tiếp:

1. Đầu vào ứng dụng public có điểm yếu cho phép thực hiện hành động trái phép **hoặc** thông tin xác thực bị lộ.
2. Danh tính/workload của ứng dụng có quyền đến dữ liệu nhạy cảm.
3. Đường mạng và policy từ ứng dụng đến CSDL cho phép hoạt động tương ứng.
4. Cơ chế xác thực/ủy quyền của CSDL không chặn hành động lạm dụng.

Nếu từng mắt xích không tồn tại, đường tấn công đó có thể bị chặn. Ví dụ **security group chỉ cho phép app → DB** vẫn là thiết kế cần thiết, nhưng chưa đủ nếu bản thân app đã bị chiếm và có quyền DB rộng. Cần kiểm soát ứng dụng, IAM/database permission, xác thực và audit song song với phân đoạn mạng.

### 7.2. Kịch bản B — thiết bị ở cùng VLAN nội bộ

**Mục tiêu:** làm máy trạm gửi một số traffic tới điểm trung gian do đối thủ kiểm soát.

**Khả năng ban đầu:** một thiết bị đã kết nối VLAN 10; gửi được frame/ARP trong VLAN theo kiểm soát của switch.

**Điều kiện bổ sung phải kiểm tra:** có client isolation không, Dynamic ARP Inspection hoặc cơ chế tương đương có hiệu lực không, có ràng buộc IP/MAC/cổng không, hai endpoint có thật sự cùng miền L2 không. Nếu điều kiện phù hợp, một số hình thức lừa phân giải địa chỉ có thể làm đối thủ trở thành điểm trung gian. Tuy nhiên, **payload HTTPS có xác thực TLS đúng vẫn được bảo vệ về bí mật và toàn vẹn** trước việc chỉ chuyển tiếp gói.

**Phòng vệ theo năng lực:** xác thực thiết bị qua 802.1X, phân đoạn endpoint, DHCP snooping + DAI theo khả năng thiết bị, giám sát biến động ARP/MAC, và dùng TLS/mTLS cho ứng dụng quan trọng.

### 7.3. Kịch bản C — quyền quản trị DNS bị lộ

**Mục tiêu:** hướng người dùng đến đích sai.

**Khả năng ban đầu:** một credential có quyền sửa bản ghi của vùng DNS cụ thể.

Khả năng này **khác** với việc quan sát gói DNS trên mạng. Adversary có thể thực hiện các thay đổi nằm trong phạm vi quyền quản trị zone, nhưng kết quả có thể bị giới hạn bởi cache, TTL, quy trình phê duyệt, chính sách DNSSEC hoặc cơ chế xác thực độc lập tại ứng dụng. Một bản ghi DNS bị đổi không tự cấp cho adversary chứng chỉ TLS hợp lệ của dịch vụ hoặc quyền truy cập dữ liệu tại backend.

**Phòng vệ:** IAM tối thiểu cho DNS zone, MFA/phê duyệt thay đổi, audit log, giám sát drift, DNSSEC trong phạm vi phù hợp, chứng chỉ TLS được kiểm tra nghiêm ngặt, quản trị vòng đời domain.

### 7.4. Kịch bản D — cloud workload hoặc control plane bị chiếm

Có hai hồ sơ khác nhau:

- **Đã chiếm một container:** đối thủ dùng được network namespace và credential mà container có; khả năng di chuyển phụ thuộc segmentation, workload identity, network policy và secrets được cấp.
- **Đã chiếm IAM principal có quyền sửa security group:** đối thủ có thể thay inbound/outbound rule trong đúng phạm vi cho phép; chưa thể kết luận họ có quyền thay route table, đọc DB hoặc tạo tài khoản quản trị.

Kịch bản cho thấy **data plane** (gói đang được chuyển) và **control plane** (API dùng cấu hình mạng) phải được mô hình hóa riêng. Firewall chặn traffic trực tiếp có thể bị vô hiệu nếu chính adversary có quyền sửa luật và không có guardrail độc lập.

### 7.5. Kịch bản E — đối thủ gây nghẽn dịch vụ từ Internet

Đối thủ không cần ở trên đường truyền để gửi lượng lớn traffic tới một dịch vụ public. Nếu khả năng phát lưu lượng hoặc nguồn lực phân tán đủ lớn, **uplink, DNS, CDN, firewall, VPN concentrator hay ứng dụng** có thể bị quá tải.

TLS không giải quyết cạn băng thông; rate limit ở web server có thể quá muộn nếu nghẽn xảy ra tại ISP. Mô hình nên xác định **điểm có nguy cơ cạn tài nguyên đầu tiên**, năng lực chống DDoS của nhà cung cấp, failover và phương án ứng phó.

### 7.6. Kịch bản F — đối thủ ở gần vùng phủ Wi-Fi

Người ở phạm vi sóng RF có thể nhìn thấy một số thông tin phát quảng bá và thử tương tác với các cơ chế kết nối không dây. Điều đó **không đồng nghĩa** họ giải mã được payload của một mạng WPA2/WPA3 cấu hình đúng. Mô hình cần xác định chế độ xác thực mạng, cách client kiểm tra danh tính máy chủ EAP, PMF, guest isolation, danh sách AP tin cậy và phạm vi quan sát thực tế.

Các kịch bản từ A đến F minh họa cùng một nguyên tắc: **lựa chọn phòng vệ dựa trên năng lực và điều kiện cụ thể**, không dựa vào một tên kiểu tấn công.

## 8. Ma trận năng lực, giả định và biện pháp kiểm soát

Đối với mạng ở phần trước, có thể lập bảng **minh họa**:

| Hồ sơ đối thủ | Nhìn thấy | Tác động ban đầu | Tài sản rủi ro | Ranh giới và kiểm soát chính |
|---|---|---|---|---|
| **A1: Internet remote** | Thông tin dịch vụ public, phản hồi của yêu cầu do mình tạo | Gửi yêu cầu tới IP/cổng được public | Ứng dụng web, VPN gateway | WAF/firewall, TLS, rate limit, auth, chống DDoS |
| **A2: Thiết bị Guest Wi-Fi** | Traffic của chính mình và dữ liệu L2 được phép quan sát | Truy cập đích được guest policy cho phép | Guest portal, dịch vụ bị mở nhầm | Guest isolation, VLAN/ACL, DNS policy, giám sát |
| **A3: Host nhân viên bị chiếm** | Dữ liệu/tokens trong quyền host, dịch vụ nội bộ reachable | Gửi yêu cầu trong quyền host; khai thác cấu hình yếu nếu có | Workstation, ứng dụng nội bộ | EDR, 802.1X, phân đoạn, least privilege, mTLS, logging |
| **A4: Router trung gian bị chiếm** | Lưu lượng đi qua router, metadata | Drop/delay/redirect gói trên đường đi | Tính sẵn sàng, lưu lượng không mã hóa | TLS/VPN, monitoring route, quản trị thiết bị, dự phòng |
| **A5: IAM cloud có quyền hạn chế** | Metadata tài nguyên theo quyền IAM | Chỉnh tài nguyên mà policy cho phép | Route/security group, workload tương ứng | IAM scope, guardrail, audit trail, change control |

Để ma trận có giá trị, cần ghi **giới hạn đã được kiểm chứng**: VLAN guest có ACL ra sao, có đường IPv6 không, policy cloud có điều kiện gì, tài khoản VPN có được truy cập mạng quản trị không, route có đường thay thế không. Không chỉ kiểm tra IPv4 nếu hệ thống chạy dual-stack; một đường IPv6 bị bỏ quên có thể làm sai kết luận phân đoạn.

## 9. Quy trình xác định năng lực adversary trong thực tế

Một quy trình có thể dùng trong threat modeling workshop hoặc khi review kiến trúc:

### Bước 1 — Chốt tài sản, mục tiêu và tác động

Liệt kê tài sản cần bảo vệ: dữ liệu, khóa, VPN gateway, DNS resolver, router, cloud control plane, hệ thống giám sát, đường uplink. Với mỗi tài sản xác định tổn thất theo ba trục:

- **Confidentiality:** dữ liệu nào không được lộ, ai có quyền xem?
- **Integrity:** cấu hình hay thông điệp nào không được thay đổi trái phép?
- **Availability:** gián đoạn bao lâu hoặc mức suy giảm nào không chấp nhận được?

Ví dụ: **tính toàn vẹn của DNS zone nội bộ** ảnh hưởng định tuyến ứng dụng theo tên; **tính sẵn sàng của VPN** ảnh hưởng hoạt động từ xa; **tính bí mật của DB** phụ thuộc cả quyền ứng dụng và đường mạng.

### Bước 2 — Vẽ đường đi và ranh giới tin cậy

Vẽ endpoint, switch/VLAN, firewall, router, DNS, VPN, Wi-Fi, load balancer, app, DB, cloud IAM cùng các luồng dữ liệu cần thiết. Phân biệt:

- **Data plane:** luồng packet thực tế.
- **Control plane:** quyền thay route/ACL/DNS/IAM, cập nhật cấu hình.
- **Management plane:** giao diện quản trị, SSH/API, giám sát, backup và cơ chế khôi phục.

Vẽ thêm luồng quản trị và đường dự phòng. Một sơ đồ chỉ có đường nghiệp vụ thường bỏ qua những điểm có quyền thay chính sách.

### Bước 3 — Đặt điểm đứng và quyền ban đầu

Chọn từng hồ sơ adversary có thực tế trong phạm vi đánh giá: khách Internet, thiết bị Wi-Fi khách, máy nhân viên bị chiếm, nhà thầu VPN, tài khoản quản trị cloud bị lộ, bên thứ ba xử lý DNS. Với mỗi hồ sơ, nêu **điểm xuất phát, quyền hiện có và nguồn bằng chứng**.

Không nên gom tất cả các đặc quyền “có thể có” của nhiều vai trò vào một người tấn công vô danh; làm vậy dễ tạo đường tấn công không thực tế và làm lệch ưu tiên bảo vệ.

### Bước 4 — Lập bảng thao tác được phép theo từng ranh giới

Với mỗi cặp **đối thủ → tài sản**, lần lượt hỏi:

1. **Reach:** có đường mạng đến IP/port/protocol hay API tương ứng không? IPv4 và IPv6 có cùng chính sách không?
2. **Observe:** có quan sát được luồng liên quan không; thấy payload hay chỉ metadata; ở trước hay sau điểm giải mã?
3. **Inject:** có gửi yêu cầu/frame/message vào kênh đó không; ai kiểm tra xác thực nguồn?
4. **Alter:** có thể sửa, drop, redirect hoặc replay thông tin không; có ràng buộc cryptographic integrity/freshness không?
5. **Authenticate/authorize:** sở hữu danh tính/token/certificate nào, policy chỉ cho thao tác gì?
6. **Control:** có thể đổi cấu hình/route/firewall/DNS/IAM tại đâu? Việc đổi đó có cần phê duyệt hay vượt qua guardrail khác không?
7. **Persist/scale:** có thể tồn tại trong bao lâu hoặc tạo tác động trên bao nhiêu host/băng thông, trong điều kiện nào?

Nếu chưa có chứng cứ, ghi **UNKNOWN** và tạo việc xác minh cụ thể.

### Bước 5 — Vẽ đường tấn công và điều kiện cần

Một đường tấn công có thể biểu diễn bằng cây điều kiện:

~~~mermaid
flowchart TD
    G[Đọc dữ liệu private DB]
    G --> A{Có quyền truy cập dữ liệu?}
    A -->|Có| B{Có đường truy cập DB hoặc API đọc DB?}
    A -->|Chưa| C[Cần chiếm danh tính hoặc quyền ứng dụng]
    C --> A
    B -->|Có| D{DB / ứng dụng cho phép thao tác đọc?}
    B -->|Không| E[Cần thêm điều kiện ở mạng hoặc thông qua ứng dụng]
    E --> B
    D -->|Có| F[Rủi ro đọc trái phép nếu không có kiểm soát khác]
    D -->|Không| H[Đường này bị chặn bởi quyền / policy hiện tại]
~~~

Đây là biểu diễn điều kiện, **không phải hướng dẫn thao tác tấn công**. Mỗi nhánh cần chỉ ra một biện pháp có thể ngắt đường tấn công hoặc một giả định cần kiểm tra.

### Bước 6 — Xác định kiểm soát, bằng chứng và lỗ hổng

Một kiểm soát chỉ được tính có hiệu lực khi xác định rõ:

- Nó nằm **trên đường đi bắt buộc** của hành động đối thủ, hay có đường thay thế?
- Nó thực thi đối với **đúng loại traffic, VLAN, IP version và danh tính**?
- Có thể bị đổi bởi chính quyền adversary đang mô hình hóa không?
- Có chứng cứ từ **cấu hình, log, thử nghiệm đã được phê duyệt hoặc audit**?
- Khi đối thủ vượt qua hoặc làm tê liệt kiểm soát, còn lớp bảo vệ độc lập nào?

Ví dụ: policy chặn Guest → Employee có thể hiệu quả với lưu lượng L3, nhưng cần kiểm tra máy khách có nằm trong cùng broadcast domain ở nơi khác không và còn đường quản trị qua VPN hay IPv6 ngoài policy không.

### Bước 7 — Ưu tiên xử lý rồi cập nhật mô hình

Đánh giá độ quan trọng của tài sản, mức tác động, bằng chứng về khả năng tiếp cận, mức độ dễ khai thác, độ tin cậy của kiểm soát và khả năng phát hiện/khôi phục. Không nên tự gán xác suất chính xác như “73%” khi không có dữ liệu phù hợp.

Threat model phải được cập nhật khi thay VLAN, firewall policy, hệ thống IAM, kiến trúc cloud, nhà cung cấp DNS, phạm vi VPN hoặc xuất hiện phương thức truy cập mới.

## 10. Gắn năng lực adversary với chiến lược phòng vệ

| Năng lực quan trọng của đối thủ | Cách thu hẹp năng lực | Cách phát hiện/điều tra |
|---|---|---|
| Nhìn thấy hoặc tác động vào lưu lượng trên đường truyền | TLS/mTLS, VPN, MACsec ở phạm vi thích hợp, bảo vệ thiết bị trung gian | Chứng chỉ bất thường, thay đổi route, log proxy/VPN, sai lệch endpoint |
| Tham gia mạng cục bộ với thiết bị lạ | 802.1X, quản lý NAC, tắt cổng không sử dụng, guest isolation | Log 802.1X/RADIUS, MAC moves, inventory thiết bị |
| Gửi lưu lượng vượt phân đoạn | Firewall/ACL, microsegmentation, chính sách egress, phân quyền service-to-service | Flow logs, log deny/allow, IDS/IPS theo phạm vi quan sát |
| Thao túng phân giải tên hoặc địa chỉ lân cận | Quản lý DNS và DNSSEC phù hợp, DAI/DHCP snooping, xác thực ứng dụng | DNS audit, thay đổi bản ghi, tín hiệu ARP/ND bất thường |
| Lạm dụng quyền quản trị mạng/cloud | IAM tối thiểu, MFA, phân tách vai trò, policy guardrail, change approval | Cloud audit logs, config drift, log thay rule/route/security group |
| Cạn tài nguyên hoặc làm mất kết nối | Chống DDoS upstream, rate limiting, load balancing, capacity planning, đường dự phòng | Telemetry băng thông, saturation, mất gói, latency, trạng thái dịch vụ |
| Di chuyển trong nội bộ từ host bị chiếm | Endpoint hardening, phân đoạn, mTLS, quyền tối thiểu, kiểm soát secrets | EDR, DNS/flow analytics, xác thực bất thường, lateral movement indicators |

**Nguyên tắc nhiều lớp:** firewall kiểm soát tuyến đường qua nó, 802.1X kiểm soát gia nhập mạng, TLS bảo vệ phiên, IDS/IPS hỗ trợ phát hiện/ngăn chặn trong phạm vi có thể quan sát. Những lớp này bổ sung nhau vì chúng giới hạn **các khả năng khác nhau** của adversary.

Một biện pháp chỉ ghi “đã triển khai” chưa đủ. Cần diễn đạt kiểm soát dưới dạng một tuyên bố kiểm chứng được, ví dụ: “Từ VLAN Guest, chính sách egress chỉ cho phép DNS thông qua resolver được quản lý và HTTPS ra Internet; không có route trực tiếp đến subnet quản trị qua cả IPv4 và IPv6.” Sau đó kiểm tra bằng cấu hình và phép thử trong phạm vi cho phép.

## 11. Những sai lầm thường gặp khi đánh giá đối thủ

1. **Đồng nhất ý định với năng lực.** Muốn đánh cắp khóa không chứng minh đã đọc được kho lưu trữ khóa.
2. **Gán quyền tuyệt đối cho đối thủ.** Có quyền truy cập LAN không có nghĩa đang on-path, đã có admin hoặc đã đọc được payload TLS.
3. **Bỏ qua control plane.** Một IAM principal sửa được network policy có thể thay đổi giả định về reachability, dù ban đầu không chạm được subnet đích.
4. **Xem mã hóa như bảo vệ mọi thuộc tính.** TLS bảo vệ nội dung và tính toàn vẹn phiên theo giả định; không đảm bảo đường truyền luôn sẵn sàng, không tự bảo vệ máy bị xâm nhập.
5. **Quên đường dự phòng và IPv6.** Chính sách IPv4 trên một firewall không bảo vệ các đường khác nếu kiến trúc không ép đi qua cùng điểm kiểm soát.
6. **Xem cùng SSID/VLAN là có thể nghe mọi traffic.** Switch, isolation, mã hóa và kiến trúc AP giới hạn quan sát khác nhau.
7. **Không ghi tiền đề.** “ARP spoofing khả thi” cần xác nhận cùng miền L2 và các kiểm soát liên quan, thay vì khẳng định dựa trên nhãn thiết bị nội bộ.
8. **Tin vào kiểm soát chưa xác minh.** Firewall rule, DNSSEC, 802.1X hay NAC chỉ có ý nghĩa ở trạng thái thực thi đúng trên đường cần bảo vệ.
9. **Bỏ qua giới hạn quyền của tài khoản bị lộ.** Quyền chỉ đọc và quyền sửa cấu hình tạo hai loại hậu quả rất khác nhau.
10. **Coi mô hình bất biến.** Sau thay đổi cloud IAM, Wi-Fi/VLAN, VPN hoặc DNS, năng lực adversary cần được đánh giá lại.

## 12. Bài tập tư duy và đáp án gợi ý

### Tình huống 1 — Khách đến văn phòng

Một khách được cấp Wi-Fi riêng và không có tài khoản nhân viên. Khách nói: “Tôi cùng địa điểm với máy chủ công ty nên chắc chắn đọc được lưu lượng máy chủ.”

**Câu hỏi:** nhận định đó đã đủ căn cứ chưa? Muốn đánh giá cần dữ kiện gì?

**Gợi ý đáp án:** chưa đủ. Cần xác minh guest có tách VLAN không, có client isolation không, route/ACL tới server ra sao, lưu lượng server có đi qua cùng điểm quan sát không, các phiên có mã hóa không. Vị trí địa lý hoặc dùng cùng AP không chứng minh có khả năng nhận toàn bộ traffic hoặc giải mã TLS.

### Tình huống 2 — Router giữa client và server

Giả sử đối thủ điều khiển một router trên đường client ↔ server. Client kết nối HTTPS và xác minh chứng chỉ đúng; endpoint và khóa TLS chưa bị chiếm.

**Câu hỏi:** nên gán những năng lực nào cho đối thủ?

**Gợi ý đáp án:** có thể quan sát nhiều metadata, drop/delay hoặc chuyển tiếp packet theo quyền router, làm gián đoạn tính sẵn sàng. Không nên gán khả năng đọc/sửa payload HTTPS mà client vẫn chấp nhận nếu chưa có điều kiện vượt qua TLS hoặc chiếm endpoint.

### Tình huống 3 — Tài khoản cloud có quyền thay một security group

Một credential bị lộ chỉ cho phép sửa security group của dịch vụ web; không có quyền đọc database và không có quyền IAM administrator.

**Câu hỏi:** việc này có đồng nghĩa DB đã bị lộ hay không?

**Gợi ý đáp án:** chưa. Đối thủ có thể thay đổi **một ranh giới mạng** của web, qua đó tạo cơ hội tiếp cận nếu còn route và policy cho phép; nhưng muốn đọc DB còn cần đường đi và quyền được DB/ứng dụng cấp. Đánh giá cần IAM policy thực tế, association của security group, route, network ACL, thông số dịch vụ, quyền DB và các guardrail độc lập.

### Tình huống 4 — DNS nội bộ trả sai địa chỉ

Một nhân viên truy cập tên miền nội bộ nhưng được trả về địa chỉ IP khác thường.

**Câu hỏi:** từ hiện tượng này có thể kết luận adversary đang điều khiển DNS hay chưa?

**Gợi ý đáp án:** chưa. Có thể do cấu hình zone, split-horizon DNS, TTL/cache, cấu hình resolver hoặc thay đổi hợp lệ. Cần đối chiếu bản ghi authoritative, nhật ký thay đổi, đường truy vấn, kết quả từ resolver tin cậy và chính sách DNSSEC nếu có. Sau khi có bằng chứng, mới gán quyền quan sát hay chỉnh sửa DNS cho một hồ sơ adversary cụ thể.

## 13. Checklist khi chốt một hồ sơ adversary

- [ ] Đã xác định mục tiêu và tài sản bị đe dọa, phân biệt rõ mục tiêu với năng lực.
- [ ] Đã ghi điểm đứng ban đầu và điều kiện được tham gia mạng.
- [ ] Đã phân biệt năng lực quan sát **metadata** với quan sát **bản rõ**.
- [ ] Đã ghi quyền gửi, sửa, chặn, trì hoãn, phát lại hoặc chuyển hướng **trên đúng đường đi**.
- [ ] Đã liệt kê danh tính/quyền IAM/role hiện có và giới hạn từng quyền.
- [ ] Đã xét lớp vật lý, LAN/Wi-Fi, định tuyến, firewall, DNS/VPN và hạ tầng cloud khi phù hợp.
- [ ] Đã xem ranh giới tin cậy, cả IPv4/IPv6 và các đường kết nối thay thế.
- [ ] Đã xác định tình trạng TLS/mTLS, VPN, MACsec hoặc bảo vệ tương đương ở đúng chặng.
- [ ] Đã nêu điều kiện cần để đối thủ mở rộng khả năng và bằng chứng kiểm tra từng điều kiện.
- [ ] Đã đánh dấu các giả định/chỗ chưa biết thay vì tự điền quyền cho đối thủ.
- [ ] Đã gắn mỗi đường tấn công với biện pháp ngăn, phát hiện và khôi phục cụ thể.
- [ ] Đã ghi người phụ trách xác minh và điều kiện cần cập nhật mô hình.

**Điểm cốt lõi:** một mô hình adversary hữu ích không được đo bằng số lượng kiểu tấn công được kể tên, mà bằng việc có thể trả lời một cách kiểm chứng được: **“Ở trạng thái và vị trí hiện tại, đối thủ có thể làm gì với tài sản nào, cần điều kiện gì để tiến xa hơn, và lớp phòng vệ nào giới hạn đúng năng lực đó?”**.
