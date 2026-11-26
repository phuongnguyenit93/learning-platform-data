Một mạng văn phòng phẳng cho phép máy trạm, máy chủ tài chính, máy in và thiết bị IoT truy cập lẫn nhau; sau khi máy in bị chiếm quyền, kẻ tấn công dò được máy chủ chứa dữ liệu nhạy cảm.
Doanh nghiệp đã chia VLAN theo phòng ban nhưng các VLAN đều được định tuyến qua một thiết bị core với rule allow-any; nhóm vận hành xem việc tách VLAN là đã hoàn tất phân đoạn bảo mật.
Máy chủ web ở DMZ cần truy cập một dịch vụ backend nội bộ; firewall hiện cho phép toàn bộ subnet DMZ kết nối tới mọi port của mạng ứng dụng.
Một rule firewall tạm thời mở inbound TCP từ Internet tới cổng quản trị để xử lý sự cố; ticket đã đóng nhưng rule không có ngày hết hạn và không còn owner.
Rule firewall mới được thêm phía trên rule deny-all nhưng bị một rule rộng hơn ở đầu danh sách che khuất; luồng truy cập ngoài dự kiến vẫn được cho phép.
Nhóm vận hành dùng NAT để che địa chỉ IP máy chủ và coi đó là biện pháp kiểm soát truy cập; một dịch vụ nội bộ vẫn có thể được truy cập từ các mạng không tin cậy.
ACL stateless chỉ cho phép chiều request nhưng không cho phép gói phản hồi của kết nối hợp lệ; nhóm vận hành mở rộng dải port ephemeral quá rộng để khắc phục.
Firewall stateful hết bảng connection tracking trong đợt tải cao; các kết nối hợp lệ bị drop và nhóm ứng dụng nhầm sự cố thành lỗi database.
Thiết bị firewall có hai đường uplink bất đối xứng; gói request và response đi qua hai node khác nhau khiến stateful inspection loại bỏ kết nối.
Một nhóm triển khai IPv6 cho máy chủ nhưng chỉ cập nhật firewall IPv4; dịch vụ quản trị vô tình có thể truy cập qua địa chỉ IPv6 công khai.
VPN remote access cấp cùng một dải mạng và quyền định tuyến cho nhân viên, nhà thầu và quản trị viên; thiết bị cá nhân của nhà thầu bị nhiễm mã độc có thể tiếp cận hệ thống quản trị.
VPN dùng split tunneling để tối ưu băng thông; laptop đồng thời kết nối Wi-Fi công cộng và mạng công ty, tạo đường chuyển tiếp giữa hai mạng.
VPN site-to-site dùng pre-shared key chung cho nhiều chi nhánh; một chi nhánh bị xâm nhập buộc tổ chức phải thay khóa và rà soát toàn bộ tunnel.
VPN vẫn chấp nhận tài khoản chỉ dùng mật khẩu dù hệ thống hỗ trợ MFA; thông tin đăng nhập bị phishing dẫn đến truy cập mạng nội bộ.
Nhân viên nghỉ việc nhưng chứng thư client VPN chưa bị thu hồi và thiết bị vẫn giữ profile kết nối; tài khoản danh tính đã khóa nhưng tunnel vẫn được thiết lập bằng certificate cũ.
Nhóm bảo mật triển khai mTLS giữa các dịch vụ nhưng không kiểm tra SAN hoặc identity trong certificate; mọi certificate được ký bởi CA nội bộ đều có thể gọi API.
Certificate của thiết bị VPN sắp hết hạn nhưng không có cảnh báo; tunnel liên chi nhánh mất kết nối ngoài giờ và hệ thống giao dịch bị gián đoạn.
Network Access Control chỉ kiểm tra trạng thái antivirus tại thời điểm kết nối; thiết bị đã được cấp quyền vẫn giữ phiên mạng sau khi posture chuyển sang không đạt.
IDS phát hiện nhiều cảnh báo port scan từ scanner kiểm thử hợp lệ; nhóm SOC tắt toàn bộ signature liên quan và bỏ lỡ hoạt động trinh sát thật từ một nguồn khác.
IPS inline dùng signature quá rộng và chặn lưu lượng hợp lệ của ứng dụng tài chính; việc chuyển sang chế độ block không qua giai đoạn quan sát gây gián đoạn nghiệp vụ.
Kẻ tấn công chia nhỏ payload và thay đổi thứ tự fragment để né signature IDS; hệ thống chỉ phân tích từng packet mà không tái lắp luồng ở tầng phù hợp.
Lưu lượng mã hóa TLS chiếm phần lớn mạng; IDS không có telemetry endpoint hoặc metadata đủ để phát hiện beaconing và hành vi bất thường.
Sensor IDS đặt sau NAT chỉ thấy địa chỉ nguồn của gateway; nhóm điều tra không thể xác định máy nội bộ nào tạo kết nối đáng ngờ.
DNS resolver nội bộ cho phép recursion từ mọi mạng, kể cả guest Wi-Fi; máy chủ có thể bị lợi dụng làm open resolver và tham gia khuếch đại DNS reflection.
Một máy trạm nhận phản hồi DNS giả trong cùng mạng LAN; resolver không xác thực nguồn trả lời và cache bản ghi độc hại cho nhiều người dùng.
DNSSEC được bật ở zone công khai nhưng resolver xác thực không đầy đủ hoặc chuyển sang insecure khi gặp lỗi; người dùng vẫn nhận bản ghi giả mà không có cảnh báo.
Ứng dụng cần truy cập domain mới nhưng DNS filter chặn nhầm do rule phân loại; đội vận hành thêm allowlist wildcard rộng, vô tình cho phép nhiều domain độc hại cùng nhóm.
Máy chủ bị nhiễm mã độc gửi truy vấn DNS có nhãn dài và tần suất cao; hệ thống giám sát chỉ theo dõi truy vấn thất bại nên bỏ lỡ DNS tunneling.
Split-horizon DNS trả IP nội bộ cho client VPN và IP công khai cho Internet; cấu hình resolver sai khiến client từ xa nhận địa chỉ nội bộ không thể định tuyến.
DNS cache có TTL dài và bản ghi dịch vụ đã chuyển sang địa chỉ mới; một số client tiếp tục kết nối tới máy chủ cũ đã ngừng được bảo vệ.
Wi-Fi khách và mạng nhân viên dùng chung VLAN; thiết bị khách có thể quét và truy cập máy in, NAS cùng dịch vụ nội bộ.
Mạng không dây doanh nghiệp dùng WPA2-PSK chung cho toàn bộ nhân viên; khi một nhân viên rời tổ chức, tổ chức không thể thu hồi riêng quyền truy cập Wi-Fi của người đó.
Access point giả mạo phát SSID giống mạng doanh nghiệp; nhân viên kết nối nhầm và gửi thông tin xác thực qua captive portal giả.
Mạng Wi-Fi dùng WPS và mật khẩu quản trị mặc định trên access point; kẻ ở gần tòa nhà có thể chiếm quyền cấu hình điểm truy cập.
Nhóm vận hành tắt xác minh certificate của máy chủ xác thực trong cấu hình Wi-Fi enterprise để khắc phục lỗi kết nối; client có thể gửi credential tới máy chủ giả.
Thiết bị IoT không hỗ trợ cập nhật firmware vẫn kết nối vào mạng nhân viên; một thiết bị bị chiếm quyền có thể di chuyển ngang sang máy chủ nội bộ.
Cloud security group cho phép inbound SSH từ `0.0.0.0/0` để tiện quản trị; địa chỉ quản trị không được giới hạn và không có bastion hoặc access broker.
Network ACL stateless của subnet cloud chỉ mở port ứng dụng mà không cho phép return traffic cần thiết; nhóm vận hành mở rộng outbound toàn bộ để khôi phục kết nối.
Workload trong private subnet có route tới Internet qua NAT gateway nhưng không có egress filtering; máy chủ bị xâm nhập có thể tải payload và gửi dữ liệu ra ngoài.
Peering giữa hai cloud VPC được cấu hình route rộng; một workload ở môi trường development có thể kết nối subnet chứa dữ liệu production.
VPN hybrid nối on-premises với cloud nhưng quảng bá route chồng lấn; lưu lượng tới subnet nhạy cảm đi nhầm qua mạng đối tác.
Cloud firewall policy được quản lý ở nhiều lớp account, subnet và workload; rule ở lớp rộng hơn vô hiệu hóa ý định deny của nhóm ứng dụng.
Một storage service chỉ được xem là private vì không có public IP, nhưng policy mạng và identity cho phép workload ngoài dự án truy cập qua private endpoint.
Load balancer công khai chuyển tiếp tới backend; firewall backend tin toàn bộ header địa chỉ client do request gửi lên và áp allowlist dựa trên header có thể giả mạo.
Một dịch vụ bị DDoS ở tầng ứng dụng; firewall chỉ giới hạn số kết nối TCP nên request HTTP đắt đỏ vẫn làm cạn CPU và connection pool backend.
Nhóm SOC phát hiện outbound traffic tăng vào ban đêm nhưng dashboard chỉ tổng hợp theo subnet; không có phân tích theo host, process hoặc đích nên khó khoanh vùng máy bị xâm nhập.
Packet capture được bật trên mạng sản xuất để điều tra sự cố nhưng lưu cả payload có thông tin xác thực và dữ liệu cá nhân; file capture được chia sẻ không kiểm soát.
Threat model của hệ thống chỉ xem xét truy cập từ Internet và bỏ qua east-west traffic; kẻ tấn công chiếm một workload nội bộ có thể di chuyển tới control plane.
Firewall rule và network route thay đổi trực tiếp khi xử lý sự cố nhưng không có baseline hoặc log thay đổi; sau sự cố nhóm không tái dựng được đường đi của lưu lượng.
Một sự cố lateral movement được phát hiện qua nhiều kết nối nội bộ bất thường; các subnet không có flow log đồng nhất và đồng hồ thiết bị lệch nhau nên không thể dựng timeline đáng tin cậy.
