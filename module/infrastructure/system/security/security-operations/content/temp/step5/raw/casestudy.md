Một tổ chức hợp nhất hai hệ thống CMDB sau sáp nhập nhưng hostname, cloud resource ID và owner không được chuẩn hóa; SOC không xác định được tài sản nào đang phát sinh cảnh báo.
Máy chủ production mới được tạo tự động trong cloud nhưng chưa đăng ký vào asset inventory; hệ thống SIEM nhận log từ máy chủ mà không gắn được môi trường, chủ sở hữu hoặc mức độ quan trọng.
Một endpoint EDR ngừng gửi telemetry sau khi agent bị gỡ trong đợt nâng cấp; dashboard vẫn hiển thị máy trạm ở trạng thái compliant vì không có kiểm tra độ mới của dữ liệu.
Đội SOC phát hiện nhiều địa chỉ IP public mới trong log firewall nhưng không thể xác định dịch vụ và nhóm chịu trách nhiệm do inventory không lưu quan hệ giữa IP, hostname và workload.
Một tài khoản dịch vụ cũ vẫn có quyền truy cập production sau khi ứng dụng bị decommission; quy trình kiểm kê tài sản chỉ theo dõi máy chủ mà không rà soát identity và credential liên quan.
Log từ firewall, hệ điều hành và cloud control plane dùng múi giờ khác nhau; khi điều tra một sự cố, thứ tự sự kiện bị sai lệch và timeline không thể đối chiếu chính xác.
Một collector trung gian mất kết nối trong ba giờ; log được buffer tại một số nguồn nhưng nguồn khác loại bỏ sự kiện, khiến SIEM có khoảng trống không được cảnh báo.
Pipeline log nhận cùng một sự kiện từ agent và syslog relay; thiếu cơ chế deduplication khiến số lần đăng nhập thất bại bị đếm gấp đôi và detection kích hoạt sai.
Một nguồn log thay đổi schema sau khi nâng cấp agent; parser SIEM âm thầm bỏ trường username và source IP nên các rule phát hiện không còn đủ ngữ cảnh.
Log ứng dụng chứa access token và dữ liệu cá nhân; pipeline chuyển nguyên payload sang SIEM và nhân rộng phạm vi người có thể xem thông tin nhạy cảm.
Đội vận hành bật debug logging để điều tra lỗi production nhưng không đặt thời hạn tắt; lượng log tăng đột biến làm đầy storage và đẩy chi phí SIEM vượt ngân sách.
Một nguồn log quan trọng ngừng gửi sự kiện nhưng không có cảnh báo ingestion lag hoặc heartbeat; SOC chỉ phát hiện thiếu dữ liệu khi điều tra sự cố đã xảy ra.
SIEM nhận log từ hàng nghìn endpoint nhưng một số thiết bị gửi sự kiện không có asset ID; analyst phải tra cứu thủ công và không thể ưu tiên theo criticality.
Một quy tắc detection phụ thuộc trường process command line nhưng chính sách thu thập endpoint không bật trường này trên máy chủ Linux; rule không bao giờ tạo cảnh báo.
Rule phát hiện nhiều lần đăng nhập thất bại dùng ngưỡng cố định cho mọi hệ thống; máy chủ xác thực công khai tạo hàng nghìn cảnh báo hợp lệ trong khi tài khoản quản trị bị password spraying ở ngưỡng thấp hơn.
Một detection rule kết hợp nhiều sự kiện trong cửa sổ thời gian nhưng timestamp nguồn bị trễ; sự kiện đến sau cửa sổ khiến chuỗi hành vi tấn công không được ghép thành một alert.
Rule SIEM phát hiện đăng nhập từ quốc gia mới dựa trên GeoIP đơn lẻ; nhân viên đi công tác và người dùng VPN tạo nhiều false positive khiến analyst bỏ qua cảnh báo.
Một quy tắc phát hiện PowerShell bất thường được triển khai rộng nhưng không phân biệt script quản trị đã ký với lệnh mã hóa dữ liệu đáng ngờ; số cảnh báo tăng vượt khả năng xử lý.
Detection engineering thay đổi logic correlation nhưng không chạy replay trên dữ liệu lịch sử; sau khi phát hành, rule bỏ sót một mẫu tấn công đã từng xuất hiện.
Một rule mới được đánh dấu enabled nhưng query tham chiếu sai index và không trả kết quả; không có test alert hoặc kiểm tra độ phủ để phát hiện rule không hoạt động.
Nhóm SOC điều chỉnh suppression để giảm alert lặp; điều kiện suppression quá rộng vô tình che cả cảnh báo từ tài khoản đặc quyền và tài sản trọng yếu.
Một cảnh báo EDR về hành vi mã hóa hàng loạt file được gộp vào nhóm low severity vì hệ thống chỉ dựa vào độ phổ biến của hash mà không xét hành vi và mức nhạy cảm tài sản.
SIEM tạo hàng trăm alert cho cùng một chiến dịch phishing nhưng mỗi alert được xử lý như sự cố riêng; analyst không nhận ra quan hệ giữa người nhận, URL và hạ tầng gửi.
Một cảnh báo đăng nhập bất thường được phân loại medium nhưng không có quy tắc escalation theo đặc quyền tài khoản, loại dữ liệu và dấu hiệu truy cập thành công.
Ca trực SOC nhận alert không có owner, runbook hoặc thông tin liên hệ đội hệ thống; thời gian xác định người chịu trách nhiệm kéo dài quá SLA.
Analyst đóng alert do không thấy hoạt động độc hại trong vài phút quan sát; dữ liệu endpoint và identity chưa được truy vấn nên quyết định đóng thiếu bằng chứng.
Một vụ phishing bị nhiều người báo cáo nhưng quy trình triage không liên kết email, URL, attachment hash và sự kiện đăng nhập sau khi người dùng bấm liên kết.
Alert về credential stuffing xuất hiện trên nhiều IP và nhiều tài khoản; analyst chỉ chặn từng IP nên chiến dịch tiếp tục qua proxy và tài khoản khác.
Một máy chủ database gửi cảnh báo outbound bất thường vào ban đêm; SOC không có baseline theo vai trò workload nên không biết đây là backup định kỳ hay dấu hiệu exfiltration.
Runbook ứng phó ransomware yêu cầu cô lập endpoint ngay nhưng không phân biệt máy trạm thông thường với máy chủ điều khiển sản xuất; thao tác tự động có thể làm gián đoạn dịch vụ trọng yếu.
Trong sự cố nghi ngờ tài khoản quản trị bị chiếm, đội trực thu hồi mọi phiên ngay lập tức nhưng không lưu token accessor, session metadata và bằng chứng cần thiết cho điều tra.
Một playbook tự động chặn địa chỉ IP theo threat intelligence; IP đó thuộc NAT của đối tác hợp lệ nên hành động containment gây gián đoạn kết nối nghiệp vụ.
EDR phát hiện tiến trình độc hại trên máy chủ nhưng hành động quarantine thất bại do agent mất kết nối; runbook không có bước xác minh trạng thái cô lập thay thế.
Một cuộc điều tra phát hiện dữ liệu bị tải xuống từ object storage; đội phản ứng chỉ thu thập log ứng dụng mà không bảo toàn audit log cloud, IAM change và network flow.
Trong quá trình xử lý sự cố, nhiều nhóm cùng chỉnh firewall và thu hồi credential mà không có incident commander; thay đổi chồng chéo khiến phạm vi ảnh hưởng khó xác định.
Một sự cố được đánh dấu contained sau khi chặn IP ban đầu nhưng attacker vẫn duy trì persistence qua scheduled task và tài khoản dịch vụ khác.
Nhóm ứng phó khôi phục máy chủ từ image sạch nhưng chưa xác minh điểm xâm nhập ban đầu và credential liên quan; hệ thống bị tái xâm nhập sau khi mở lại mạng.
Threat hunting phát hiện nhiều lần sử dụng công cụ quản trị từ xa ngoài khung giờ; nhóm chưa có giả thuyết cụ thể và truy vấn chỉ tìm tên tiến trình nên bỏ sót biến thể đổi tên.
Analyst săn tìm hành vi lateral movement qua remote service nhưng log xác thực liên máy không được lưu đủ lâu; dữ liệu lịch sử không còn để kiểm tra chuỗi di chuyển.
Một chiến dịch exfiltration dùng DNS query có entropy cao; nhóm threat hunting chỉ tìm lưu lượng outbound lớn nên không phát hiện kênh truyền dữ liệu nhỏ nhưng kéo dài.
Threat intelligence feed cung cấp nhiều IP và domain hết hạn hoặc dùng chung CDN; SOC tự động chặn toàn bộ indicator mà không kiểm tra độ tin cậy, thời gian hiệu lực và ngữ cảnh.
Nhóm hunting tìm dấu hiệu persistence trên endpoint nhưng không có inventory phần mềm và baseline startup service; các thay đổi hợp lệ bị nhầm là bất thường và ngược lại.
Vulnerability scanner phát hiện lỗ hổng nghiêm trọng trên máy chủ public nhưng ticket được xếp hàng theo CVSS đơn thuần; không xét exploit đang bị khai thác và mức độ quan trọng của tài sản.
Một bản vá được đánh dấu hoàn tất sau khi cập nhật image chuẩn nhưng instance đang chạy và máy chủ ngoại lệ vẫn dùng phiên bản dễ bị tấn công.
Quét lỗ hổng xác thực cần tài khoản đặc quyền nhưng credential scan hết hạn; báo cáo vẫn được xem là đầy đủ dù nhiều máy chủ không được kiểm tra cấu hình bên trong.
Đội quản lý lỗ hổng nhận hàng nghìn finding trùng từ nhiều scanner; không có quy trình deduplicate theo tài sản, package và CVE nên remediation bị phân tán.
Một lỗ hổng bị đánh giá false positive dựa trên phiên bản package hiển thị; backport của nhà cung cấp chưa được xem xét và ticket bị đóng sai.
Nhóm vận hành cần áp dụng biện pháp giảm thiểu tạm thời cho hệ thống không thể vá ngay; exception không có owner, thời hạn, compensating control hoặc lịch đánh giá lại.
Dashboard SOC báo MTTR giảm nhưng thời gian được tính từ lúc analyst nhận ticket đến lúc đóng, không tính thời gian phát hiện, xác minh và khôi phục dịch vụ.
Trung tâm SOC đo số lượng alert đã đóng mỗi ca; analyst ưu tiên đóng nhanh cảnh báo đơn giản trong khi incident nghiêm trọng chờ escalation quá lâu.
Quy trình phân loại severity khác nhau giữa các ca trực; cùng một dấu hiệu xâm nhập tài khoản đặc quyền được ghi nhận là high ở ca này và medium ở ca khác.
Nhóm SOC thuê ngoài nhận log và xử lý alert nhưng hợp đồng không quy định thời gian escalation, quyền truy cập bằng chứng và trách nhiệm thông báo sự cố nghiêm trọng.
Playbook incident response được cập nhật sau sự cố nhưng bản runbook trong hệ thống trực ca vẫn là phiên bản cũ; analyst thực hiện bước đã lỗi thời trong lần cảnh báo tiếp theo.
Một cuộc diễn tập tabletop thành công vì các bên thảo luận đúng quy trình, nhưng không có kiểm thử thực tế việc cô lập endpoint, thu hồi token và khôi phục backup.
SIEM bị quá tải trong một đợt tấn công volumetric; pipeline ưu tiên log ứng dụng ít quan trọng và làm rơi sự kiện từ IAM cùng firewall vốn cần cho điều tra.
Credential của tài khoản tích hợp SIEM bị lộ; đội vận hành đổi mật khẩu nhưng chưa rà soát truy vấn đã chạy, export dữ liệu và quyền truy cập của token cũ.
Một incident cần chia sẻ bằng chứng với pháp chế và nhà cung cấp; log chứa dữ liệu cá nhân và bí mật xác thực nhưng chưa có quy trình redaction, chain of custody và kiểm soát bản sao.
Sau khi đóng một incident, nhóm không thực hiện post-incident review hoặc cập nhật detection, runbook và asset owner; cùng kỹ thuật tấn công tái diễn ở hệ thống khác.
Một dịch vụ cloud thay đổi audit event schema và quyền mặc định; SIEM ingestion tiếp tục hoạt động nhưng các sự kiện thay đổi IAM policy không còn được parse vào detection.
Một tổ chức có SOC ở nhiều múi giờ; incident handover thiếu timeline, hành động đã thực hiện, giả thuyết còn mở và người liên hệ nên ca tiếp theo lặp lại điều tra.
Một detection rule có tỷ lệ false positive cao được tắt để giảm tải mà không có đánh giá rủi ro còn lại, owner chấp thuận hoặc thời hạn bật lại.
Một chiến dịch threat hunting phát hiện tài khoản service không có owner và đăng nhập từ nhiều workload; quy trình SecOps chưa có luồng chuyển finding sang IAM để thu hồi hoặc giới hạn quyền.
