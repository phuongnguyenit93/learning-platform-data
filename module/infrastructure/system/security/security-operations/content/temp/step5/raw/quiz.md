Câu 1. Thông tin nào giúp asset inventory hỗ trợ ưu tiên điều tra sự cố?
A. Owner, criticality, vị trí, exposure và phụ thuộc của tài sản.
B. Chỉ hostname và địa chỉ IP hiện tại của từng máy trong mạng.
C. Số lượng tiến trình đang chạy và phiên bản trình duyệt người dùng.
D. Tên nhóm hỗ trợ cùng ngày mua thiết bị và thời hạn bảo hành.
Đáp án đúng: A

Câu 2. Khi hợp nhất nhiều nguồn asset inventory, cách nào giảm tài sản trùng hoặc đã lỗi thời?
A. Gộp mọi bản ghi cùng subnet rồi giữ bản ghi được cập nhật gần nhất.
B. Xóa bản ghi không được EDR nhìn thấy trong lần quét gần nhất.
C. Hợp nhất theo ID chuẩn, nguồn tin cậy và vòng đời tài sản.
D. Ưu tiên nguồn có nhiều trường nhất mà không kiểm tra độ tin cậy.
Đáp án đúng: C

Câu 3. EDR phát hiện một máy chủ lạ trong mạng nhưng CMDB không có bản ghi; SOC nên xử lý thế nào?
A. Bỏ qua vì CMDB không ghi nhận nên thiết bị không thuộc quản lý.
B. Xóa cảnh báo để tránh tạo incident từ tài sản chưa đăng ký.
C. Xác minh nguồn phát hiện, chủ sở hữu và cô lập theo mức rủi ro.
D. Tắt EDR trên máy để kiểm tra xem thiết bị có tiếp tục hoạt động.
Đáp án đúng: C

Câu 4. Thiết kế log collection cho máy chủ ở mạng chập chờn cần ưu tiên cơ chế nào?
A. Buffer có giới hạn, retry backoff và chuyển tiếp an toàn.
B. Gửi UDP không lưu đệm để tránh log tồn đọng khi mất kết nối.
C. Tăng vô hạn hàng đợi trên endpoint và bỏ qua cảnh báo dung lượng.
D. Giữ log tại máy đến cuối tháng rồi chuyển thủ công về SIEM.
Đáp án đúng: A

Câu 5. Vì sao log bảo mật nên được chuyển tới kho tập trung có quyền ghi hạn chế và chống sửa đổi?
A. Giảm nguy cơ sửa hoặc xóa dấu vết và hỗ trợ điều tra tập trung.
B. Cho phép mọi analyst sửa log để bổ sung ngữ cảnh ngay khi triage.
C. Lưu duy nhất trên endpoint để tránh phụ thuộc hệ thống trung tâm.
D. Chỉ mã hóa log khi truyền, không cần kiểm soát quyền ghi dữ liệu.
Đáp án đúng: A

Câu 6. Timestamp giữa endpoint, firewall và SIEM lệch nhau gây khó điều tra; kiểm soát nền tảng nào cần được chuẩn hóa?
A. Đổi mọi timestamp sang giờ địa phương của analyst trực ca.
B. Dùng thời điểm SIEM nhận log thay cho thời điểm sự kiện xảy ra.
C. Đồng bộ NTP, dùng UTC nhất quán và giám sát clock drift.
D. Tăng độ dài timestamp để bù cho sai lệch giữa các máy chủ.
Đáp án đúng: C

Câu 7. Chuẩn hóa log từ nhiều nhà cung cấp giúp detection engineering đạt mục tiêu nào?
A. Thay mọi field khác nhau bằng một chuỗi message nguyên bản duy nhất.
B. Chuyển toàn bộ log sang cùng định dạng văn bản nhưng giữ tên field riêng.
C. Loại bỏ field ít xuất hiện để giảm kích thước mà không xem xét use case.
D. Ánh xạ sự kiện về schema chung để truy vấn và tương quan nhất quán.
Đáp án đúng: D

Câu 8. Một SIEM correlation rule nên kết hợp sự kiện theo nguyên tắc nào để phát hiện hành vi đáng ngờ?
A. Gộp mọi event trong cùng subnet thành một incident duy nhất mỗi ngày.
B. Kích hoạt alert khi một event riêng lẻ xuất hiện bất kể ngữ cảnh.
C. So khớp chuỗi log nguyên văn mà không chuẩn hóa danh tính hoặc thời gian.
D. Liên kết event theo thực thể, thời gian, ngữ cảnh và chuỗi hành vi.
Đáp án đúng: D

Câu 9. Khi xây correlation cho chuỗi đăng nhập thất bại rồi thành công, yếu tố nào giúp giảm cảnh báo sai?
A. Kết hợp cùng principal, nguồn, thiết bị, cửa sổ thời gian và kết quả.
B. Chỉ đếm tổng số lần đăng nhập thất bại của toàn bộ tổ chức.
C. Gộp mọi lần đăng nhập từ cùng quốc gia thành một chuỗi tấn công.
D. Bỏ qua đăng nhập thành công vì sự kiện này thường là hoạt động bình thường.
Đáp án đúng: A

Câu 10. Đánh giá severity của alert nên dựa trên tập yếu tố nào?
A. Số lượng event tương tự trong một phút mà không xét tài sản đích.
B. Mức độ nghiêm trọng mặc định của signature do nhà cung cấp đặt.
C. Thứ tự alert xuất hiện trên dashboard và số analyst đang trực.
D. Impact, độ tin cậy, phạm vi, exploitability và ngữ cảnh tài sản.
Đáp án đúng: D

Câu 11. Analyst nhận cảnh báo malware mức cao nhưng endpoint đã bị cách ly tự động; bước triage đầu tiên nên làm gì?
A. Xác minh phạm vi, bằng chứng, hành động tự động và trạng thái endpoint.
B. Đóng alert ngay vì EDR đã cách ly nên không còn nguy cơ tồn tại.
C. Khởi động lại máy để xóa tiến trình đáng ngờ trước khi thu thập dữ liệu.
D. Nâng severity lên mức cao nhất mà không kiểm tra tài sản hoặc tác động.
Đáp án đúng: A

Câu 12. Quy tắc phát hiện tạo nhiều false positive do hoạt động quản trị hợp lệ; cách tinh chỉnh nào phù hợp?
A. Tắt rule trên toàn bộ môi trường để giảm số lượng alert ngay lập tức.
B. Loại mọi event từ tài khoản quản trị khỏi nguồn telemetry của SIEM.
C. Dùng suppression hẹp theo ngữ cảnh đã xác minh và theo dõi độ bao phủ.
D. Tăng threshold đến khi alert biến mất mà không kiểm tra hành vi bị bỏ sót.
Đáp án đúng: C

Câu 13. Trước khi đưa detection rule mới vào production, nhóm nên kiểm chứng bằng cách nào?
A. Chờ incident thật xảy ra rồi mới xác nhận rule có phát hiện được hay không.
B. Chạy rule trên một mẫu log nhỏ chỉ chứa sự kiện bình thường.
C. Đánh dấu rule đã đạt vì cú pháp truy vấn được SIEM chấp nhận.
D. Replay dữ liệu, kiểm thử logic và đo false positive/negative.
Đáp án đúng: D

Câu 14. MITRE ATT&CK mapping hỗ trợ SOC ra sao và giới hạn nào cần nhớ?
A. Thay thế hoàn toàn phân tích rủi ro bằng danh sách kỹ thuật ATT&CK.
B. Xác nhận mọi kỹ thuật được map đều có thể phát hiện chính xác trong SOC.
C. Dùng mã kỹ thuật ATT&CK làm severity mặc định cho mọi alert.
D. Map kỹ thuật đối thủ để tìm gap, không chứng minh full coverage.
Đáp án đúng: D

Câu 15. Nhiều alert phát sinh từ cùng một chiến dịch trên một endpoint; SIEM nên xử lý thế nào để analyst không bị ngập?
A. Tạo ticket độc lập cho từng event để không bỏ sót thông tin ban đầu.
B. Deduplicate và group theo thực thể, thời gian cùng incident context.
C. Xóa alert trùng dựa trên nội dung message mà không giữ liên kết nguồn.
D. Gộp tất cả alert trong ngày vào một incident bất kể nguồn hoặc đối tượng.
Đáp án đúng: B

Câu 16. Quản lý detection-as-code đem lại lợi ích vận hành nào?
A. Review version control, test, approval và rollout có kiểm soát.
B. Sửa truy vấn trực tiếp trên SIEM production để giảm thời gian phát hành.
C. Cho phép mọi analyst thay đổi rule mà không lưu lịch sử phiên bản.
D. Đóng băng toàn bộ rule sau khi phát hành để tránh mọi thay đổi.
Đáp án đúng: A

Câu 17. Khi tổ chức quy trình incident response, trình tự hoạt động tổng quát nào phù hợp?
A. Phát hiện, xóa toàn bộ dữ liệu, khôi phục backup rồi mới xác định nguyên nhân.
B. Chuẩn bị, phát hiện, ngăn chặn, loại bỏ, phục hồi và cải tiến.
C. Containment, công bố truyền thông, đóng ticket và bỏ qua hậu kiểm.
D. Điều tra, vá hệ thống, thông báo rồi chỉ chuẩn bị runbook sau sự cố.
Đáp án đúng: B

Câu 18. Containment và eradication khác nhau như thế nào trong xử lý sự cố?
A. Containment xóa malware; eradication chỉ cô lập thiết bị khỏi mạng.
B. Containment hạn chế lan rộng; eradication loại bỏ attacker foothold.
C. Hai hoạt động giống nhau và có thể thay thế tùy công cụ EDR.
D. Eradication luôn phải hoàn tất trước khi áp dụng bất kỳ biện pháp cô lập nào.
Đáp án đúng: B

Câu 19. Khi cô lập một máy chủ nghi bị xâm nhập, analyst cần cân nhắc điều gì để bảo toàn chứng cứ?
A. Tắt nguồn ngay trong mọi trường hợp để chắc chắn attacker không tiếp tục hoạt động.
B. Xóa tài khoản và tệp đáng ngờ trước khi lưu dấu vết hệ thống.
C. Để máy tiếp tục kết nối mạng cho đến khi đội điều tra hoàn tất phân tích.
D. Cân nhắc tác động nghiệp vụ, thu thập volatile evidence và ghi lại hành động.
Đáp án đúng: D

Câu 20. Ransomware đang lan qua SMB trong mạng nội bộ; hành động containment ban đầu nào phù hợp?
A. Cô lập máy bị ảnh hưởng, chặn đường lan truyền và bảo toàn bằng chứng.
B. Tắt toàn bộ máy chủ trong doanh nghiệp để ngăn mọi kết nối SMB.
C. Xóa các bản sao mã hóa ngay lập tức trước khi xác định phạm vi lây nhiễm.
D. Chờ phân tích đầy đủ mọi file rồi mới ngăn kết nối ngang giữa các máy.
Đáp án đúng: A

Câu 21. Tài khoản nhân viên bị chiếm và token phiên vẫn còn hiệu lực; nhóm ứng phó nên ưu tiên việc gì?
A. Chỉ đổi mật khẩu, giữ session hiện tại để người dùng không bị gián đoạn.
B. Revoke session, reset credential và kiểm tra truy cập liên quan.
C. Xóa tài khoản khỏi directory nhưng không kiểm tra token đã phát hành.
D. Chặn địa chỉ IP gần nhất và coi sự cố danh tính đã được xử lý.
Đáp án đúng: B

Câu 22. Chain of custody của chứng cứ số cần ghi nhận những thông tin nào?
A. Tên file và người gửi qua email, không cần ghi các lần chuyển giao.
B. Người thu thập, thời điểm, nguồn, phương pháp, hash và lịch sử bàn giao.
C. Chỉ ghi hash cuối cùng vì giá trị hash tự chứng minh toàn bộ quá trình.
D. Chỉ ghi thời điểm phân tích và kết luận của analyst chịu trách nhiệm.
Đáp án đúng: B

Câu 23. Trong điều tra máy nghi bị compromise, vì sao cần thu thập dữ liệu volatile trước khi tắt máy khi tình huống cho phép?
A. Dữ liệu trên ổ đĩa luôn biến mất trước dữ liệu trong bộ nhớ khi tắt máy.
B. Tắt máy giúp giữ nguyên mọi trạng thái và chứng cứ trong bộ nhớ.
C. Dữ liệu RAM, tiến trình và kết nối có thể mất khi hệ thống tắt.
D. Dữ liệu volatile không có giá trị điều tra nếu đã có log từ SIEM.
Đáp án đúng: C

Câu 24. Để tạo forensic image có thể kiểm chứng, quy trình thu thập nên áp dụng kiểm soát nào?
A. Dùng write blocker khi phù hợp, tạo image và xác minh hash nguồn/bản sao.
B. Sao chép file bằng trình quản lý tệp rồi tin vào kích thước bản sao.
C. Mount ổ đĩa ở chế độ ghi để công cụ pháp chứng đọc nhanh hơn.
D. Chỉ tính hash sau khi analyst đã chỉnh sửa image để loại dữ liệu thừa.
Đáp án đúng: A

Câu 25. Threat hunting khác alert triage ở điểm trọng tâm nào?
A. Triage xử lý mọi cảnh báo hiện có; hunt chủ động tìm dấu hiệu chưa được cảnh báo.
B. Hunt chỉ chạy lại các alert severity cao để xác nhận kết quả tự động.
C. Threat hunting tìm dấu hiệu theo giả thuyết ngoài cảnh báo sẵn có.
D. Triage tập trung vào giả thuyết; hunt chỉ phân loại ticket theo SLA.
Đáp án đúng: C

Câu 26. Một cuộc hunt không tìm thấy dấu hiệu xâm nhập; báo cáo nên thể hiện những gì?
A. Chỉ ghi “không phát hiện gì” vì không có sự kiện đáng ngờ trong dữ liệu.
B. Xóa truy vấn sau khi hunt để tránh người khác hiểu sai kết quả.
C. Chỉ lưu số lượng event được kiểm tra mà không ghi nguồn telemetry.
D. Giả thuyết, phạm vi, dữ liệu, truy vấn, giới hạn và kết luận.
Đáp án đúng: D

Câu 27. Đội vulnerability management nên ưu tiên lỗ hổng nào khi nhiều hệ thống có cùng CVSS?
A. Sắp xếp chỉ theo CVSS giảm dần mà không xét vị trí triển khai.
B. Ưu tiên máy có nhiều lỗ hổng nhất bất kể khả năng bị khai thác.
C. Exposure, exploitability, criticality và compensating controls.
D. Chọn lỗ hổng có bản vá nhỏ nhất để hoàn tất nhiều ticket nhanh hơn.
Đáp án đúng: C

Câu 28. KEV hoặc bằng chứng khai thác thực tế nên ảnh hưởng thế nào đến thứ tự xử lý lỗ hổng?
A. Bỏ qua CVSS vì KEV hoặc EPSS đã thay thế mọi đánh giá tác động.
B. Tăng ưu tiên khi có khai thác thực tế hoặc bằng chứng exploitation.
C. Chỉ xử lý KEV nếu hệ thống đã ghi nhận bị xâm nhập thành công.
D. Giữ nguyên thứ tự ban đầu vì dữ liệu khai thác không ảnh hưởng risk.
Đáp án đúng: B

Câu 29. Triển khai bản vá bảo mật trên hệ thống trọng yếu cần quy trình nào để giảm rủi ro gián đoạn?
A. Cài đồng loạt mọi bản vá ngay khi phát hành mà không cần đánh giá phụ thuộc.
B. Kiểm thử tương thích, triển khai theo đợt và có kế hoạch rollback.
C. Trì hoãn mọi bản vá cho đến kỳ nâng cấp phần cứng tiếp theo.
D. Chỉ vá máy có cảnh báo malware vì lỗ hổng chưa khai thác không gây rủi ro.
Đáp án đúng: B

Câu 30. Khi chưa thể vá một lỗ hổng nghiêm trọng, exception nên được quản trị ra sao?
A. Đánh dấu accepted vĩnh viễn để tránh lặp lại quá trình xin phê duyệt.
B. Chỉ ghi lý do kỹ thuật và bỏ qua người chịu trách nhiệm nghiệp vụ.
C. Ẩn finding khỏi dashboard cho đến khi đội vận hành có thời gian xử lý.
D. Ngoại lệ cần người chịu trách nhiệm, biện pháp bù và hạn review.
Đáp án đúng: D

Câu 31. Một incident runbook hữu ích cần có những thành phần nào?
A. Danh sách công cụ được cài đặt trên máy analyst và mật khẩu quản trị.
B. Trigger, scope, validation, actions, escalation và exit criteria.
C. Một tập lệnh tự chạy mọi hành động mà không cần xác minh điều kiện.
D. Mô tả sự cố chung và đường dẫn tới tài liệu sản phẩm liên quan.
Đáp án đúng: B

Câu 32. SOAR playbook tự động khóa tài khoản khi phát hiện hành vi đáng ngờ; kiểm soát nào nên đi kèm?
A. Tự động khóa mọi tài khoản có một alert mà không kiểm tra ngữ cảnh.
B. Cho phép playbook xóa log để giảm dung lượng khi xử lý incident.
C. Chạy lại hành động vô hạn đến khi API trả về trạng thái thành công.
D. Human approval hoặc guardrail cho hành động tác động lớn và có audit.
Đáp án đúng: D

Câu 33. MTTD và MTTR đo lường khía cạnh nào của hoạt động SOC?
A. MTTD đo tổng alert; MTTR đo số incident được mở trong một tháng.
B. MTTD là thời gian phát hiện; MTTR là thời gian phản ứng/phục hồi.
C. MTTD đo thời gian vá lỗ hổng; MTTR đo thời gian cập nhật asset inventory.
D. Hai chỉ số đều đo thời gian analyst dành để đóng một cảnh báo.
Đáp án đúng: B

Câu 34. Vì sao chỉ đếm số alert đã đóng không phản ánh đầy đủ hiệu quả SOC?
A. Số alert đóng càng cao thì mức độ bảo vệ và hiệu quả SOC càng tốt.
B. Số ticket mỗi analyst càng lớn thì năng lực điều tra càng cao.
C. Cần xét chất lượng phát hiện, tác động, false positive và kết quả xử lý.
D. Số rule được triển khai đủ để chứng minh coverage của toàn bộ hệ thống.
Đáp án đúng: C

Câu 35. Thông tin nào cần có trong bàn giao ca SOC để tránh mất ngữ cảnh điều tra?
A. Chỉ số alert đã đóng trong ca và tên người nhận ca sau.
B. Incident, owner, timeline, evidence, actions và next steps.
C. Toàn bộ log thô của ngày mà không có ưu tiên hay trạng thái xử lý.
D. Danh sách công cụ SOC đang hoạt động mà không cần ghi sự cố tồn đọng.
Đáp án đúng: B

Câu 36. Khi alert liên quan tới hệ thống thanh toán trọng yếu, tiêu chí nào nên kích hoạt escalation?
A. Tác động dịch vụ, dữ liệu, lan rộng và nghĩa vụ báo cáo.
B. Số lượng alert cùng loại trong dashboard của ca trực hiện tại.
C. Tên nhóm phát hiện và số lượng analyst có thể tham gia xử lý.
D. Mức độ quen thuộc của analyst với sản phẩm bị cảnh báo.
Đáp án đúng: A

Câu 37. Sự cố xảy ra tại nhà cung cấp SaaS lưu dữ liệu doanh nghiệp; SOC cần phối hợp theo hướng nào?
A. Chờ nhà cung cấp tự đóng sự cố rồi xóa alert khỏi SIEM nội bộ.
B. Chỉ điều tra khi có quyền truy cập trực tiếp vào hạ tầng nhà cung cấp.
C. Phối hợp, xác minh dữ liệu và phân định nghĩa vụ thông báo.
D. Chuyển toàn bộ trách nhiệm xử lý cho bộ phận mua sắm và hợp đồng.
Đáp án đúng: C

Câu 38. Post-incident review nên tạo ra kết quả nào để giảm khả năng tái diễn?
A. Nguyên nhân gốc, kiểm soát thiếu, action owner, deadline và kiểm chứng.
B. Một bản tóm tắt sự kiện để lưu trữ mà không cần hành động tiếp theo.
C. Chỉ thay đổi chữ ký phát hiện để tránh tạo lại cùng loại alert.
D. Đóng incident sau khi dịch vụ hoạt động mà không đánh giá khả năng tái diễn.
Đáp án đúng: A

Câu 39. Detection rule phụ thuộc DNS log nhưng một vùng mạng chưa gửi DNS telemetry; SOC nên xử lý khoảng trống này thế nào?
A. Tắt detection rule vì dữ liệu DNS không có trong mọi phân vùng mạng.
B. Giả định không có DNS event đồng nghĩa không có truy vấn đáng ngờ.
C. Bổ sung nguồn log và đánh giá phần phát hiện đang mù.
D. Thay DNS log bằng số liệu tổng lưu lượng mạng mà không cập nhật detection.
Đáp án đúng: C

Câu 40. Dấu hiệu nào giúp phát hiện data exfiltration khi lưu lượng outbound tăng nhưng vẫn nằm trong ngưỡng tổng băng thông?
A. Chỉ cảnh báo khi tổng băng thông vượt ngưỡng cố định của toàn doanh nghiệp.
B. Chỉ kiểm tra kết nối tới IP nằm trong danh sách chặn công khai.
C. Bỏ qua lưu lượng mã hóa vì không thể đọc payload để nhận diện dữ liệu.
D. Phân tích đích đến, loại dữ liệu, danh tính nguồn và baseline theo thời gian.
Đáp án đúng: D
