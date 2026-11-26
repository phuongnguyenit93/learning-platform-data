Anh/chị xác định phạm vi và mục tiêu của chương trình Security Operations cho một tổ chức như thế nào?
Làm thế nào xây dựng inventory tài sản có thể hỗ trợ SOC biết hệ thống, dữ liệu và dịch vụ nào cần được giám sát?
Anh/chị xác định owner, mức độ quan trọng, môi trường và mức phơi lộ của từng tài sản ra sao?
Những nguồn nào giúp phát hiện tài sản mới, tài sản không được quản lý hoặc hệ thống đã ngừng sử dụng nhưng vẫn có kết nối?
Anh/chị ưu tiên đưa endpoint, máy chủ, workload cloud, danh tính, thiết bị mạng và ứng dụng vào phạm vi giám sát theo tiêu chí nào?
Làm thế nào liên kết asset inventory với vulnerability management, SIEM và quy trình ứng phó sự cố để tránh dữ liệu phân mảnh?
Anh/chị xác định những nguồn log và telemetry tối thiểu cần thu thập để phát hiện hoạt động bất thường trên từng loại tài sản như thế nào?
Những rủi ro nào xuất hiện khi một nguồn log quan trọng bị mất, trễ, sai định dạng hoặc ngừng gửi dữ liệu?
Anh/chị thiết kế pipeline thu thập, truyền tải, chuẩn hóa và lưu trữ log để bảo đảm tính đầy đủ và khả năng truy vết ra sao?
Làm thế nào đồng bộ timestamp và xử lý sai lệch múi giờ giữa endpoint, cloud service, ứng dụng và thiết bị mạng?
Anh/chị xác định schema và trường dữ liệu chuẩn để tương quan sự kiện từ nhiều nguồn khác nhau như thế nào?
Những biện pháp nào giúp bảo vệ tính toàn vẹn, quyền truy cập và thời hạn lưu giữ của log phục vụ điều tra?
Anh/chị giảm dữ liệu nhạy cảm trong log mà vẫn giữ đủ ngữ cảnh cần thiết cho detection và incident investigation ra sao?
Làm thế nào giám sát chính pipeline logging để phát hiện mất nguồn, giảm lưu lượng bất thường hoặc lỗi parser?
Anh/chị lựa chọn kiến trúc SIEM, nguồn dữ liệu và chiến lược lưu trữ dựa trên quy mô, độ trễ và nhu cầu điều tra như thế nào?
Những tiêu chí nào giúp xác định use case SIEM cần triển khai trước dựa trên rủi ro và mức độ quan trọng của tài sản?
Anh/chị chuyển threat scenario thành detection logic với điều kiện, cửa sổ thời gian và ngữ cảnh phù hợp như thế nào?
Làm thế nào kết hợp correlation rule, threshold, sequence và behavioral analytics để phát hiện hành vi nhiều bước?
Anh/chị xác định các nguồn dữ liệu cần thiết cho một detection và cách xử lý khi một nguồn chưa có coverage ra sao?
Những cách nào giúp phát hiện hành vi đáng ngờ mà không phụ thuộc hoàn toàn vào indicator tĩnh hoặc chữ ký đã biết?
Anh/chị kiểm thử detection rule bằng dữ liệu lịch sử, mô phỏng an toàn hoặc purple-team exercise như thế nào?
Làm thế nào đo precision, recall, false positive và false negative của một detection trong điều kiện vận hành thực tế?
Anh/chị điều chỉnh detection để giảm alert fatigue mà không làm mất khả năng phát hiện các hành vi nghiêm trọng ra sao?
Khi một detection rule thay đổi, anh/chị quản lý phiên bản, lý do thay đổi, kiểm thử hồi quy và phê duyệt như thế nào?
Anh/chị ưu tiên phát triển detection dựa trên threat intelligence, incident đã xảy ra và kỹ thuật tấn công quan sát được ra sao?
Những thông tin nào cần được enrichment cho một alert để analyst đánh giá nhanh danh tính, tài sản, tiến trình và mức độ phơi lộ?
Anh/chị thiết kế quy trình triage để phân biệt sự kiện thông thường, cảnh báo cần theo dõi và incident thực sự như thế nào?
Làm thế nào xác định severity và priority của alert dựa trên độ tin cậy, tác động, asset criticality và khả năng lan rộng?
Anh/chị xử lý alert trùng lặp hoặc nhiều cảnh báo cùng bắt nguồn từ một hoạt động như thế nào để giữ được bức tranh sự cố?
Những điều kiện nào khiến một alert cần được escalation ngay tới incident commander hoặc nhóm chuyên trách?
Anh/chị ghi nhận quyết định đóng alert để bảo đảm có đủ lý do, bằng chứng và khả năng review sau này như thế nào?
Làm thế nào phối hợp giữa Tier 1, Tier 2, Tier 3 và nhóm chuyên môn để tránh mất ngữ cảnh khi chuyển ca hoặc escalation?
Anh/chị phân loại incident theo loại hình, phạm vi ảnh hưởng, mức độ nghiêm trọng và nghĩa vụ thông báo như thế nào?
Những bước đầu tiên nào giúp bảo toàn bằng chứng số khi nghi ngờ một endpoint, tài khoản hoặc workload bị xâm nhập?
Anh/chị xây dựng timeline sự cố bằng cách tương quan log xác thực, endpoint telemetry, network flow và hoạt động cloud ra sao?
Làm thế nào phân biệt hoạt động quản trị hợp lệ với hành vi sử dụng công cụ quản trị cho mục đích độc hại?
Anh/chị xác định phạm vi ảnh hưởng và blast radius khi một danh tính, thiết bị hoặc secret có dấu hiệu bị chiếm quyền như thế nào?
Những nguyên tắc nào giúp quyết định containment mà không gây gián đoạn không cần thiết cho dịch vụ trọng yếu?
Anh/chị lựa chọn giữa cô lập endpoint, chặn chỉ dấu mạng, vô hiệu hóa danh tính hoặc thu hồi credential dựa trên tiêu chí nào?
Làm thế nào bảo đảm hành động containment được phê duyệt, ghi nhận, có thể đảo ngược khi phù hợp và không phá hủy bằng chứng?
Anh/chị xác định khi nào cần eradication, rebuild, credential rotation hoặc loại bỏ persistence khỏi môi trường như thế nào?
Những điều kiện nào cần được xác nhận trước khi khôi phục hệ thống và đưa tài sản trở lại mạng production?
Anh/chị xây dựng runbook cho các tình huống như ransomware, credential compromise, data exfiltration và cloud account takeover ra sao?
Làm thế nào kiểm tra runbook có đủ rõ để người trực ca thực hiện trong điều kiện áp lực và thiếu thông tin?
Anh/chị tổ chức tabletop exercise và diễn tập kỹ thuật để kiểm tra phối hợp giữa SOC, IT, pháp chế, truyền thông và lãnh đạo như thế nào?
Những thông tin nào cần được truyền đạt cho các bên liên quan trong incident mà không làm lộ dữ liệu điều tra hoặc gây nhiễu?
Anh/chị quản lý chain of custody và quyền truy cập evidence để kết quả điều tra có thể được kiểm tra độc lập như thế nào?
Làm thế nào xác định nguyên nhân gốc, điều kiện tạo thuận lợi và khoảng trống kiểm soát sau khi incident được xử lý?
Anh/chị chuyển lessons learned thành detection mới, thay đổi control, cập nhật runbook và backlog remediation như thế nào?
Anh/chị xây dựng chương trình threat hunting dựa trên giả thuyết từ threat intelligence, telemetry và các khoảng trống detection ra sao?
Những nguồn dữ liệu nào cần có để hunt hành vi bất thường của tài khoản, tiến trình, persistence và di chuyển ngang?
Làm thế nào phân biệt một phát hiện từ threat hunting với hoạt động bất thường hợp lệ hoặc hành vi chưa đủ bằng chứng?
Anh/chị ghi nhận giả thuyết, truy vấn, phạm vi, kết quả âm tính và phát hiện của mỗi hunt để người khác tái lập ra sao?
Những tiêu chí nào giúp quyết định chuyển kết quả hunting thành detection rule hoặc yêu cầu bổ sung telemetry?
Anh/chị tích hợp threat intelligence vào hoạt động SOC mà không tạo quá nhiều cảnh báo từ indicator lỗi thời hoặc thiếu ngữ cảnh như thế nào?
Làm thế nào đánh giá mức độ liên quan và độ tin cậy của nguồn threat intelligence trước khi dùng để chặn hoặc điều tra?
Anh/chị tổ chức vulnerability management dựa trên tài sản, mức phơi lộ, khả năng khai thác và tác động kinh doanh như thế nào?
Những nguồn nào giúp xác định lỗ hổng đang bị khai thác thực tế và cách ưu tiên so với điểm CVSS đơn thuần ra sao?
Anh/chị theo dõi thời gian từ phát hiện lỗ hổng đến xác nhận khắc phục và xử lý các trường hợp quá hạn như thế nào?
Làm thế nào phối hợp SOC với đội sở hữu hệ thống để xác minh bản vá, biện pháp bù trừ và rủi ro còn lại?
Anh/chị phát hiện cấu hình sai hoặc tài sản phơi lộ mới trong cloud và hạ tầng bằng telemetry nào?
Những kiểm soát nào giúp giám sát danh tính đặc quyền, service account và hoạt động truy cập dữ liệu nhạy cảm hiệu quả?
Anh/chị thiết kế playbook automation hoặc SOAR để tự động enrichment và containment mà vẫn kiểm soát được rủi ro thao tác như thế nào?
Khi nào một hành động phản ứng nên tự động hoàn toàn, cần phê duyệt của analyst hoặc phải chuyển cho incident commander?
Làm thế nào kiểm thử automation để tránh chặn nhầm tài khoản, cô lập nhầm hệ thống hoặc tạo vòng lặp hành động?
Anh/chị xác định SLA, lịch trực, escalation path và mô hình phối hợp cho SOC theo mức độ nghiêm trọng của incident ra sao?
Những chỉ số nào phản ánh hiệu quả SOC ngoài số lượng alert đã đóng hoặc số incident đã xử lý?
Anh/chị sử dụng MTTD, MTTA, MTTR, false positive rate và dwell time để tìm điểm nghẽn vận hành như thế nào?
Làm thế nào đo coverage của tài sản, log source và detection use case để nhận diện vùng mù của SOC?
Anh/chị đánh giá chất lượng bàn giao ca, độ đầy đủ của case notes và tính nhất quán trong quyết định triage ra sao?
Những yếu tố nào giúp xác định SOC cần cải thiện con người, quy trình, công cụ hay chất lượng dữ liệu trước tiên?
Anh/chị lập kế hoạch cải tiến Security Operations từ xu hướng incident, kết quả hunting, audit và diễn tập như thế nào?
