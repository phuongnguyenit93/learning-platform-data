Bạn xây dựng mô hình đe dọa cho một mạng doanh nghiệp như thế nào để xác định tài sản, luồng dữ liệu, ranh giới tin cậy và đối tượng tấn công?
Bạn lựa chọn các nguyên tắc kiến trúc mạng an toàn như defense in depth, least privilege và default deny để áp dụng vào môi trường thực tế ra sao?
Bạn xác định những luồng giao tiếp cần được cho phép giữa các vùng mạng dựa trên yêu cầu nghiệp vụ và chủ sở hữu dịch vụ như thế nào?
Bạn thiết kế phân đoạn mạng theo mức độ nhạy cảm của hệ thống, môi trường và loại workload như thế nào?
Bạn phân biệt VLAN, subnet, VRF và security zone trong việc tạo ranh giới phân đoạn mạng ra sao?
Bạn đánh giá giới hạn của việc chỉ dùng VLAN để cách ly hệ thống và xác định những lớp kiểm soát bổ sung cần có như thế nào?
Bạn thiết kế microsegmentation để kiểm soát lưu lượng east-west giữa workload trong cùng một vùng mạng ra sao?
Bạn lựa chọn giữa phân đoạn dựa trên mạng, danh tính workload và nhãn ứng dụng theo đặc điểm hạ tầng nào?
Bạn kiểm chứng rằng quy tắc phân đoạn thực sự ngăn được đường đi ngoài dự kiến giữa các vùng như thế nào?
Bạn xử lý luồng quản trị từ mạng người dùng tới server quan trọng bằng bastion, jump host hoặc privileged access gateway ra sao?
Bạn thiết kế vùng DMZ cho dịch vụ công khai như thế nào để giới hạn tác động khi một máy chủ bị xâm nhập?
Bạn kiểm soát lưu lượng từ DMZ vào mạng nội bộ và từ mạng nội bộ ra Internet theo nguyên tắc nào?
Bạn lựa chọn firewall stateless, stateful và next-generation firewall dựa trên loại lưu lượng và yêu cầu kiểm soát nào?
Bạn tổ chức rulebase firewall theo thứ tự, phạm vi nguồn/đích, service và owner như thế nào để dễ kiểm toán và tránh rule quá rộng?
Bạn áp dụng default-deny mà vẫn bảo đảm các luồng nghiệp vụ cần thiết hoạt động ổn định như thế nào?
Bạn thiết kế quy trình yêu cầu, phê duyệt, kiểm thử, hết hạn và rà soát định kỳ firewall rule ra sao?
Bạn phát hiện và loại bỏ rule shadowed, duplicate, unused hoặc any-any trong chính sách firewall như thế nào?
Bạn phân biệt security group và network ACL trong cloud, đặc biệt về stateful và stateless filtering, như thế nào?
Bạn xử lý tình huống firewall cho phép kết nối chiều đi nhưng traffic phản hồi bị chặn do state hoặc ephemeral port như thế nào?
Bạn thiết kế egress filtering để hạn chế máy chủ nội bộ kết nối tới đích không cần thiết mà không làm gián đoạn cập nhật và dịch vụ hợp lệ ra sao?
Bạn lựa chọn vị trí đặt firewall giữa các subnet, vùng tin cậy, điểm ra Internet và kết nối đối tác dựa trên luồng dữ liệu nào?
Bạn đánh giá rủi ro khi nhiều dịch vụ dùng chung một firewall cluster hoặc một policy domain như thế nào?
Bạn thiết kế site-to-site VPN để kết nối hai tổ chức hoặc hai trung tâm dữ liệu với phạm vi mạng tối thiểu ra sao?
Bạn phân biệt IPsec tunnel mode và transport mode, và lựa chọn cách dùng trong các kịch bản kết nối nào?
Bạn lựa chọn IKEv2, thuật toán mã hóa, integrity và cơ chế trao đổi khóa cho IPsec VPN theo tiêu chuẩn hiện hành như thế nào?
Bạn thiết kế remote-access VPN cho nhân viên từ xa với MFA, xác thực thiết bị và kiểm tra posture ra sao?
Bạn đánh giá rủi ro của split tunneling và xác định khi nào lưu lượng Internet của người dùng từ xa cần đi qua mạng doanh nghiệp như thế nào?
Bạn kiểm soát quyền truy cập qua VPN theo danh tính, nhóm, thiết bị và vai trò công việc ra sao?
Bạn quản lý chứng thư, pre-shared key và credential của VPN như thế nào để giảm nguy cơ lộ hoặc tái sử dụng?
Bạn thiết kế quy trình cấp phát, xoay vòng và thu hồi chứng thư cho thiết bị VPN như thế nào khi thiết bị thất lạc hoặc nhân sự rời tổ chức?
Bạn xử lý vấn đề MTU, fragmentation và giảm hiệu năng khi lưu lượng ứng dụng đi qua VPN như thế nào?
Bạn lựa chọn TLS VPN hay IPsec VPN cho truy cập từ xa và kết nối site-to-site dựa trên yêu cầu tương thích và vận hành nào?
Bạn triển khai Network Access Control bằng 802.1X như thế nào để xác thực người dùng hoặc thiết bị trước khi cấp quyền vào mạng?
Bạn phân biệt EAP-TLS với phương thức xác thực Wi-Fi hoặc LAN dựa trên mật khẩu dùng chung như thế nào?
Bạn xử lý thiết bị không hỗ trợ 802.1X bằng guest VLAN, restricted access hoặc cơ chế onboarding nào để vẫn giữ được phân đoạn?
Bạn thiết kế RADIUS và chính sách cấp quyền mạng theo danh tính như thế nào để tránh một tài khoản được truy cập mọi VLAN?
Bạn lựa chọn vị trí triển khai IDS và IPS để quan sát hoặc chặn lưu lượng north-south và east-west như thế nào?
Bạn phân biệt IDS thụ động và IPS inline về khả năng phát hiện, độ trễ, điểm lỗi và rủi ro false positive ra sao?
Bạn kết hợp signature-based detection và anomaly-based detection như thế nào để phát hiện cả mối đe dọa đã biết lẫn hành vi bất thường?
Bạn điều chỉnh rule IDS/IPS như thế nào để giảm false positive mà không bỏ lọt dấu hiệu xâm nhập quan trọng?
Bạn xử lý tình huống IPS chặn nhầm lưu lượng nghiệp vụ quan trọng như thế nào để khôi phục dịch vụ và cải thiện chính sách?
Bạn xác định nguồn telemetry cần thu thập từ firewall, router, switch, VPN, DNS, IDS/IPS và endpoint như thế nào?
Bạn kết hợp NetFlow/IPFIX, packet capture và firewall log để điều tra một kết nối bất thường ra sao?
Bạn thiết kế điểm capture và lưu giữ PCAP như thế nào để đủ dữ liệu điều tra mà không vượt ngân sách lưu trữ hoặc thu thập dữ liệu quá mức?
Bạn phân tích lưu lượng mã hóa TLS khi không thể giải mã payload như thế nào bằng metadata, DNS, certificate và hành vi kết nối?
Bạn cân nhắc rủi ro quyền riêng tư, dữ liệu nhạy cảm và kiểm soát truy cập khi triển khai TLS inspection như thế nào?
Bạn xây dựng quy trình bảo vệ private key và chứng thư của thiết bị TLS inspection ra sao để tránh biến thiết bị kiểm tra thành điểm giải mã tập trung dễ bị lạm dụng?
Bạn bảo vệ hạ tầng DNS nội bộ bằng resolver phân tầng, recursion policy và phân tách zone như thế nào?
Bạn phân biệt authoritative DNS, recursive resolver và forwarder trong kiến trúc DNS an toàn ra sao?
Bạn sử dụng DNSSEC để xác thực tính toàn vẹn và nguồn gốc dữ liệu DNS như thế nào, đồng thời quản lý rủi ro khi cấu hình sai trust chain?
Bạn lựa chọn DNS over TLS hoặc DNS over HTTPS trong môi trường doanh nghiệp như thế nào để cân bằng quyền riêng tư, khả năng giám sát và chính sách phân giải tập trung?
Bạn phát hiện và điều tra dấu hiệu DNS tunneling hoặc DNS-based data exfiltration bằng tín hiệu và ngữ cảnh nào?
Bạn bảo vệ resolver trước cache poisoning, open recursion và lạm dụng khuếch đại DNS như thế nào?
Bạn thiết kế lọc tên miền độc hại bằng threat intelligence, RPZ hoặc sinkhole ra sao và kiểm soát false positive như thế nào?
Bạn xử lý sự cố DNS bị chiếm quyền hoặc bản ghi bị thay đổi trái phép như thế nào để khôi phục trust và xác định phạm vi ảnh hưởng?
Bạn thiết kế bảo mật Wi-Fi doanh nghiệp bằng WPA3-Enterprise, 802.1X và xác thực chứng thư như thế nào?
Bạn phân biệt WPA2-Personal, WPA2-Enterprise và WPA3-Enterprise về mô hình xác thực và rủi ro vận hành ra sao?
Bạn phát hiện rogue access point, evil twin và thiết bị không được phép kết nối vào mạng không dây bằng phương pháp nào?
Bạn phân đoạn guest Wi-Fi, thiết bị IoT và mạng nhân viên như thế nào để hạn chế truy cập ngang?
Bạn xử lý thiết bị IoT hoặc thiết bị cũ không hỗ trợ chuẩn mã hóa Wi-Fi hiện đại bằng vùng mạng hạn chế nào?
Bạn đánh giá rủi ro từ WPS, mật khẩu Wi-Fi dùng chung và cấu hình access point mặc định như thế nào?
Bạn giám sát hành vi roaming, deauthentication bất thường và thay đổi cấu hình access point ra sao để phát hiện sự cố hoặc tấn công?
Bạn thiết kế mạng cloud VPC/VNet với public subnet, private subnet và route table như thế nào để giảm bề mặt tấn công?
Bạn phân biệt security group, network ACL, route table và cloud firewall trong việc kiểm soát luồng mạng cloud ra sao?
Bạn kiểm soát kết nối giữa VPC/VNet qua peering, transit gateway hoặc hub-and-spoke như thế nào để tránh mở rộng trust ngoài ý muốn?
Bạn lựa chọn private endpoint hoặc service endpoint để truy cập dịch vụ cloud mà không cần đi qua Internet công khai như thế nào?
Bạn thiết kế hybrid connectivity qua VPN hoặc private circuit như thế nào để bảo vệ định tuyến, mã hóa và phân đoạn giữa on-premises với cloud?
Bạn đánh giá rủi ro route leak hoặc cấu hình BGP sai trong kết nối hybrid và xây dựng biện pháp kiểm soát ra sao?
Bạn kiểm soát egress từ workload cloud để giảm nguy cơ command-and-control và exfiltration mà vẫn hỗ trợ dependency hợp lệ như thế nào?
Bạn thiết kế bảo vệ control plane và data plane của thiết bị mạng cloud hoặc network appliance như thế nào?
Bạn phân tích tác động của cấu hình mặc định, public IP và management interface mở trên router, switch hoặc firewall như thế nào?
Bạn bảo vệ giao thức quản trị mạng bằng SSH, SNMPv3, AAA và mạng quản trị riêng ra sao?
Bạn thiết kế xác thực và phân quyền quản trị thiết bị mạng theo vai trò, MFA và ghi nhận phiên thao tác như thế nào?
Bạn kiểm soát thay đổi cấu hình router, switch và firewall để phát hiện drift, cấu hình trái phép và sai sót triển khai ra sao?
Bạn phòng chống IP spoofing bằng ingress/egress filtering, uRPF hoặc biện pháp phù hợp với topology như thế nào?
Bạn xây dựng khả năng chống DDoS ở các lớp mạng và ứng dụng bằng rate limiting, scrubbing, anycast hoặc dịch vụ bảo vệ như thế nào?
Bạn phân biệt volumetric attack, protocol exhaustion và application-layer DDoS để lựa chọn cách giảm thiểu phù hợp ra sao?
Bạn thiết kế TLS và mutual TLS cho giao tiếp service-to-service như thế nào để xác thực hai đầu và quản lý vòng đời chứng thư?
Bạn xác minh certificate chain, hostname, validity và revocation status ra sao khi một hệ thống kết nối tới dịch vụ bên ngoài?
Bạn xử lý việc certificate hết hạn, CA bị xâm phạm hoặc private key bị lộ trong hạ tầng mạng như thế nào?
Bạn xây dựng baseline lưu lượng bình thường theo ứng dụng, subnet, thời gian và danh tính để phát hiện lateral movement ra sao?
Bạn điều tra một máy nội bộ tạo nhiều kết nối outbound tới địa chỉ hoặc domain hiếm gặp bằng cách kết hợp flow log, DNS log và endpoint telemetry như thế nào?
Bạn ứng phó khi phát hiện một thiết bị mạng bị chiếm quyền điều khiển như thế nào để cô lập, bảo toàn bằng chứng và khôi phục an toàn?
Bạn xây dựng playbook xử lý sự cố cho port scanning, brute-force VPN, DNS compromise và lateral movement ra sao?
Bạn kiểm thử hiệu quả của network segmentation, firewall policy, VPN access và IDS/IPS bằng phương pháp an toàn nào?
Bạn tổ chức vulnerability assessment và penetration test cho hạ tầng mạng như thế nào để kiểm tra ranh giới tin cậy mà không gây gián đoạn dịch vụ?
Bạn ưu tiên khắc phục phát hiện bảo mật mạng dựa trên mức độ phơi nhiễm, khả năng khai thác, đường đi tới tài sản quan trọng và tác động nghiệp vụ ra sao?
Bạn thiết kế dashboard và cảnh báo cho lưu lượng bất thường, thay đổi rule, VPN failure, DNS anomaly và IDS/IPS alert như thế nào?
Bạn xác định SLO hoặc chỉ số vận hành nào để theo dõi độ sẵn sàng, độ trễ và hiệu quả của các lớp phòng vệ mạng?
Bạn tổ chức rà soát định kỳ kiến trúc, rulebase, luồng kết nối, chứng thư và quyền quản trị mạng như thế nào để loại bỏ cấu hình không còn cần thiết?
