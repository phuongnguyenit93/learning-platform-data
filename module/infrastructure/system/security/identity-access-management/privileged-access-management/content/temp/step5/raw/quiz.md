1. Một tổ chức cần kiểm kê tài khoản đặc quyền trên máy chủ, cloud, database và thiết bị mạng; cách thu thập nào đáng tin cậy nhất?
A. Chọn HR roster làm nguồn duy nhất rồi suy ra tài khoản quản trị theo chức danh nhân sự.
B. Import danh sách vault vì tài khoản đặc quyền đều phải lưu tại đó trước khi đưa vào inventory.
C. Đối chiếu directory, cấu hình nền tảng và log sử dụng để hợp nhất inventory.
D. Dùng CMDB làm nguồn chính, không cần đối chiếu quyền hiệu lực trên từng nền tảng.
Đáp án đúng: C

2. Khi phát hiện tài khoản quản trị không rõ chủ sở hữu, bước xử lý nào phù hợp nhất?
A. Gán trưởng bộ phận hiện tại làm owner để hoàn tất inventory trước kỳ audit.
B. Xác minh owner và mục đích với hệ thống liên quan, rồi hạn chế hoặc thu hồi quyền.
C. Đổi mật khẩu nhưng giữ nguyên quyền tới kỳ review kế tiếp vì chưa có bằng chứng lạm dụng.
D. Xóa ngay tài khoản mà không kiểm tra dependency hoặc tài khoản phục vụ khẩn cấp.
Đáp án đúng: B

3. Một tài khoản nhận quyền qua nested group và role kế thừa; access review cần đánh giá điều gì?
A. Chỉ xem role gán trực tiếp và coi nested group là quyền của nhóm khác.
B. Xem nhóm cấp cao nhất, bỏ qua membership lồng nhau để tránh đếm trùng quyền.
C. Tính quyền hiệu lực từ mọi đường cấp trực tiếp, gián tiếp và tài nguyên.
D. So sánh chức danh với ma trận role mà không tính quyền trên tài nguyên cha.
Đáp án đúng: C

4. Cách thiết kế least privilege cho nhóm quản trị production nào phù hợp nhất?
A. Cấp quyền Owner cho cả nhóm để xử lý sự cố nhanh trong production.
B. Dùng một role admin chung cho mọi môi trường để dễ vận hành và cấp quyền.
C. Giữ quyền thường trực rộng và chỉ xin phê duyệt khi có kỳ audit.
D. Cấp quyền theo tác vụ, tài nguyên và thời hạn cần thiết.
Đáp án đúng: D

5. Một quy trình yêu cầu quyền nhạy cảm cần separation of duties; thiết kế nào giảm xung đột lợi ích?
A. Cho người yêu cầu tự duyệt khi ticket đủ chi tiết và có lịch sử tốt.
B. Tách người yêu cầu, người phê duyệt và người thực thi theo mức rủi ro.
C. Để vault admin tự duyệt vì họ là người giữ credential trong hệ thống.
D. Dùng nhóm trực ca vừa yêu cầu vừa duyệt để rút ngắn thời gian xử lý.
Đáp án đúng: B

6. Một kỹ sư cần quyền production trong vài phút để xử lý ticket; JIT nên được cấu hình thế nào?
A. Ràng buộc danh tính, tài nguyên, ticket, phê duyệt và thời hạn ngắn.
B. Cấp role quản trị cố định rồi nhắc người dùng tự gỡ quyền sau công việc.
C. Cho phép người dùng tự chọn thời lượng dài nhất để tránh xin gia hạn giữa ca.
D. Cấp quyền theo nhóm công việc và để quyền tồn tại đến kỳ rà soát.
Đáp án đúng: A

7. Hết thời hạn JIT nhưng access token đã cấp vẫn còn hiệu lực; kiểm soát nào hoàn tất việc thu hồi?
A. Xóa yêu cầu JIT khỏi portal vì token cũ sẽ tự mất quyền ngay lập tức.
B. Thu hồi grant và vô hiệu hóa token, session còn quyền truy cập.
C. Đổi mật khẩu vault nhưng không xử lý token hoặc session đã phát hành.
D. Chờ browser đóng tab rồi coi phiên đặc quyền đã kết thúc.
Đáp án đúng: B

8. JEA khác với cấp shell quản trị toàn quyền ở điểm nào?
A. Chỉ công bố thao tác, tham số và tài nguyên được phép cho nhiệm vụ.
B. Cấp root ngắn hạn rồi lưu lại lịch sử lệnh đã chạy trên máy đích.
C. Giới hạn thời gian đăng nhập nhưng giữ nguyên tập lệnh và module hệ thống.
D. Ẩn lệnh trên giao diện nhưng shell vẫn gọi được trực tiếp từ command line.
Đáp án đúng: A

9. Password vault và privileged session broker có vai trò khác nhau như thế nào?
A. Vault ghi hình phiên, còn broker chỉ lưu password được mã hóa để tái sử dụng.
B. Vault giữ credential; broker kiểm soát kết nối và phiên quản trị.
C. Vault phê duyệt yêu cầu, còn broker kiểm kê tài khoản không có owner.
D. Vault và broker cùng lưu secret, khác nhau chủ yếu ở giao diện quản trị.
Đáp án đúng: B

10. Khi onboarding một tài khoản quản trị vào vault, trình tự nào giảm nguy cơ nhận nhầm credential?
A. Import trước, rồi tìm owner nếu checkout báo lỗi.
B. Đổi password ngay mà không hỏi consumer đang phụ thuộc vào tài khoản.
C. Xác minh owner và dependency, rồi kiểm soát chuyển đổi và rotation.
D. Giữ plaintext cạnh vault để phục hồi nếu chuyển đổi ban đầu gặp lỗi.
Đáp án đúng: C

11. Nhiều máy chủ dùng chung mật khẩu local administrator; biện pháp nào giảm lateral movement?
A. Giữ mật khẩu chung, tăng độ dài và complexity.
B. Dùng credential riêng theo máy và quản lý rotation tập trung.
C. Đổi mật khẩu chung theo tháng rồi gửi qua email nội bộ.
D. Bật MFA cho domain account, giữ password local như cũ.
Đáp án đúng: B

12. Trước khi rotation service account, thông tin nào cần có để tránh gián đoạn workload?
A. Danh sách người đọc vault và lần đăng nhập gần nhất của từng nhân viên.
B. Inventory consumer, dependency và lịch cập nhật để kiểm tra kết nối.
C. Số lượng hash và độ dài password đang lưu trong database.
D. Danh sách subnet, không cần xác định tiến trình đang dùng credential.
Đáp án đúng: B

13. Rotation đã đổi secret trong vault nhưng cập nhật hệ thống đích thất bại; cách phục hồi nào phù hợp?
A. Xóa bản ghi cũ trong vault để mọi consumer tự lấy credential mới.
B. Retry vô hạn trên tất cả hệ thống mà không theo dõi trạng thái từng đích.
C. Đánh dấu lệch trạng thái, cập nhật consumer và kiểm tra kết nối.
D. Ghi nhận rotation thành công vì vault đã lưu mật khẩu mới.
Đáp án đúng: C

14. Một service account chỉ phục vụ batch job nhưng có thể đăng nhập shell tương tác; kiểm soát nào phù hợp?
A. Đổi tên để nhận diện tài khoản máy trong danh sách quản trị.
B. Cho phép shell nhưng chỉ xem log theo lịch hằng tháng.
C. Tắt interactive login, giới hạn quyền và nguồn gọi của job.
D. Chia sẻ credential cho nhóm vận hành để xử lý job lỗi.
Đáp án đúng: C

15. Workload cần truy cập cloud API mà không dùng access key dài hạn; lựa chọn nào tốt hơn?
A. Dùng workload identity để cấp credential ngắn hạn theo workload.
B. Tạo access key quản trị mới mỗi lần deploy.
C. Dùng tài khoản cá nhân của kỹ sư cho workload.
D. Mã hóa key dài hạn trong image của workload.
Đáp án đúng: A

16. SSH key và certificate đặc quyền cần vòng đời quản lý nào?
A. Giữ private key lâu dài nếu file được mã hóa và passphrase đủ mạnh.
B. Kiểm kê public key, không lưu thông tin owner của private key.
C. Thu hồi key khi nhân sự nghỉ việc, không xét thay đổi quyền.
D. Gắn owner, phạm vi, hạn dùng và quy trình thu hồi rõ ràng.
Đáp án đúng: D

17. Một thao tác reveal credential có mức ảnh hưởng rất cao; dual control nên được áp dụng ra sao?
A. Cho vault administrator tự phê duyệt vì họ chịu trách nhiệm vận hành vault.
B. Cho người yêu cầu xác nhận lần hai bằng cùng một tài khoản và phiên làm việc.
C. Yêu cầu hai cá nhân độc lập phê duyệt hoặc đồng kiểm soát theo mức rủi ro.
D. Chỉ ghi log sau khi reveal để kiểm toán viên có thể xem lại.
Đáp án đúng: C

18. Cách giảm việc người quản trị nhìn thấy secret khi cần kết nối hệ thống đích là gì?
A. Cho phép tải secret xuống máy trạm nhưng xóa file sau khi kết thúc phiên.
B. Lưu secret trên máy trạm rồi xóa file sau khi phiên quản trị kết thúc.
C. Gửi credential qua email mã hóa để người dùng nhập thủ công khi kết nối.
D. Inject credential qua broker mà không hiển thị secret gốc.
Đáp án đúng: D

19. Session brokering đem lại kiểm soát nào cho SSH hoặc RDP đặc quyền?
A. Thay xác thực đích bằng một tài khoản dùng chung cho toàn bộ phiên quản trị.
B. Tăng tốc kết nối bằng cách cache password trên máy người dùng cuối.
C. Ghi lại IP đích nhưng không kiểm tra danh tính người mở phiên quản trị.
D. Định tuyến qua điểm kiểm soát, áp policy và gắn phiên với danh tính.
Đáp án đúng: D

20. Session recording cần metadata nào để phục vụ điều tra và kiểm toán?
A. Video tự chứng minh ai đăng nhập và ai đã phê duyệt thao tác quản trị.
B. Username và hostname, rồi suy thời gian từ log hệ điều hành ở máy đích.
C. Ghi danh tính, thời điểm, tài sản, ticket và bằng chứng toàn vẹn.
D. Clipboard và secret nhập vào để tái hiện mọi thao tác trong phiên.
Đáp án đúng: C

21. Một phiên đặc quyền đang xóa dữ liệu ngoài phạm vi ticket; hệ thống nên phản ứng thế nào?
A. Chờ phiên kết thúc rồi mới phân tích recording để tránh gián đoạn người dùng.
B. Cảnh báo thời gian thực và cho phép chấm dứt phiên theo thẩm quyền.
C. Ghi sự kiện để xem lại sau khi phiên đóng, không can thiệp lúc đang chạy.
D. Chỉ gửi email nhắc nhở vì session đã được phê duyệt từ đầu.
Đáp án đúng: B

22. Khi ghi hình terminal hoặc RDP, làm thế nào hạn chế thu thập bí mật và dữ liệu cá nhân?
A. Che vùng nhạy cảm, giới hạn người xem và retention theo mục đích.
B. Ghi toàn bộ màn hình và clipboard, cấp quyền đọc rộng cho nhóm quản trị.
C. Tắt recording cho phiên nhạy cảm mà không tạo bằng chứng thay thế tương đương.
D. Lưu recording vô thời hạn vì có thể cần cho điều tra trong tương lai.
Đáp án đúng: A

23. Một break-glass account phải dùng khi IdP hoặc PAM gián đoạn; thiết kế nào phù hợp?
A. Dùng tài khoản quản trị thường ngày để tránh phải học quy trình mới.
B. Tách luồng khẩn cấp, bảo vệ credential và kiểm tra định kỳ.
C. Đặt mật khẩu break-glass trong wiki nội bộ để luôn truy cập được.
D. Tắt cảnh báo khi đăng nhập break-glass để tránh nhiễu lúc sự cố.
Đáp án đúng: B

24. Sau khi sử dụng break-glass trong sự cố, việc nào cần thực hiện?
A. Giữ nguyên credential để dùng lại khi khẩn cấp lần sau mà không cần chuẩn bị.
B. Xóa recording vì break-glass là ngoại lệ ngoài quy trình PAM thông thường.
C. Chỉ báo quản lý trực ca, không review quyền đã dùng trong sự cố.
D. Thu hồi phiên, xoay credential và lưu bằng chứng sau sự cố.
Đáp án đúng: D

25. Một trung tâm dữ liệu cần truy cập offline khi mạng và IdP mất kết nối; kiểm soát nào tăng trách nhiệm giải trình?
A. Giao một bản mật khẩu cho bất kỳ kỹ sư nào có mặt tại phòng máy.
B. Lưu credential trên USB dùng chung và không ghi lại người đã nhận.
C. Cho phép đăng nhập offline vô thời hạn để bảo đảm tính sẵn sàng.
D. Niêm phong credential, custody kép, ghi nhận người nhận và đối soát sau khôi phục.
Đáp án đúng: D

26. Kiểm toán phát hiện local admin đăng nhập trực tiếp ngoài PAM; bước nào giúp tìm đường bypass?
A. Đối chiếu log host, network path, inventory và nguồn xác thực.
B. Xem log PAM vì phiên ngoài luồng không được ghi nhận trong hệ thống.
C. Đổi mật khẩu vault để ngăn mọi hình thức đăng nhập trực tiếp trên host.
D. Tắt local account mà không xác minh dependency của ứng dụng đang chạy.
Đáp án đúng: A

27. Nhà cung cấp cần bảo trì một máy chủ production; cách cấp quyền nào phù hợp?
A. Tạo VPN dùng chung cho subnet quản trị để nhà cung cấp tự kết nối.
B. Cấp quyền thường trực để nhà cung cấp xử lý yêu cầu bất ngờ ngoài giờ.
C. Gửi mật khẩu root qua kênh hỗ trợ và yêu cầu đổi sau vài tháng.
D. Cấp danh tính riêng, MFA, tài nguyên cụ thể, thời hạn và giám sát.
Đáp án đúng: D

28. PAM cần xác minh posture thiết bị trước khi mở phiên đặc quyền; tín hiệu nào có ích?
A. Kích thước màn hình, phiên bản browser và ngôn ngữ hiển thị của máy.
B. Tên user local và số ứng dụng đang mở trên desktop của quản trị viên.
C. Dựa vào IP công cộng mà không kiểm tra trạng thái bảo vệ endpoint.
D. Kiểm tra quản lý, mã hóa, EDR và compliance của thiết bị.
Đáp án đúng: D

29. MFA cho quản trị viên cần chống phishing real-time; lựa chọn nào mạnh hơn OTP qua SMS?
A. Dùng MFA chống phishing gắn xác thực với origin hoặc thiết bị.
B. Tăng độ dài mã SMS và yêu cầu đọc mã qua điện thoại bàn khi đăng nhập.
C. Gửi OTP email thứ hai để attacker phải kiểm soát thêm một hộp thư.
D. Chỉ yêu cầu MFA khi người dùng truy cập từ ngoài giờ làm việc.
Đáp án đúng: A

30. Log PAM cần gửi SIEM để tái dựng chuỗi truy cập; tập dữ liệu nào có giá trị nhất?
A. Tương quan danh tính, approval, ticket, checkout, session và tài sản.
B. Gửi số lần login thành công theo ngày để giảm lượng dữ liệu ingest.
C. Gửi username và IP vì các sự kiện approval, checkout đã nằm trong vault.
D. Gửi toàn bộ secret và clipboard để SIEM có đủ ngữ cảnh điều tra.
Đáp án đúng: A

31. Làm thế nào bảo vệ audit log và recording khỏi bị sửa bởi chính quản trị viên PAM?
A. Cho vault administrator xóa log khi dọn dung lượng rồi ghi lại lý do.
B. Lưu log trên máy chủ quản trị và dựa vào phân quyền hệ điều hành.
C. Lưu bất biến, tách quyền quản trị và kiểm tra tính toàn vẹn.
D. Xuất log khi audit, không cần giữ bản gốc sau khi gửi báo cáo.
Đáp án đúng: C

32. Retention cho session recording và audit evidence nên được thiết kế thế nào?
A. Theo mục đích, yêu cầu kiểm toán, độ nhạy và thời hạn lưu cần thiết.
B. Lưu recording vĩnh viễn để không bỏ sót bằng chứng tiềm năng cho điều tra.
C. Xóa recording sau 24 giờ dù đang có điều tra hoặc legal hold.
D. Dùng cùng thời hạn cho log, video, credential và dữ liệu nghiệp vụ.
Đáp án đúng: A

33. Vault HA và disaster recovery cần kiểm chứng điều gì ngoài khả năng truy cập secret?
A. Phục hồi dữ liệu, metadata, khóa, audit trail và nhất quán failover.
B. Đo thời gian mở giao diện vì secret thiếu có thể tạo lại khi cần.
C. Đếm node hoạt động và coi nhiều node là bằng chứng không mất dữ liệu.
D. Dùng tài khoản admin chung khi primary lỗi để khôi phục nhanh hơn.
Đáp án đúng: A

34. Một chương trình PAM muốn đo hiệu quả sau triển khai; bộ chỉ số nào phản ánh tốt hơn?
A. Đếm số tài khoản import và người dùng có portal trong hệ thống.
B. Đếm số lần login và ticket đóng trong tháng mà không xét quyền còn lại.
C. Đếm recording lưu trữ mà không xét phiên nào thiếu bằng chứng kiểm toán.
D. Đo quyền thường trực, JIT, rotation, session evidence và thời gian thu hồi.
Đáp án đúng: D

35. Ticket JIT có thể được tái sử dụng để mở nhiều phiên khác nhau; ràng buộc nào khắc phục?
A. Kiểm tra ticket còn mở, không cần ràng buộc phiên với tài nguyên đích.
B. Gắn phê duyệt với danh tính, tài nguyên, thời hạn và session.
C. Cho phép tái sử dụng ticket nếu cùng người yêu cầu và cùng nhóm trực.
D. Tăng thời hạn ticket để người dùng không phải xin phê duyệt nhiều lần.
Đáp án đúng: B

36. Một credential automation bị lộ trong repository; phản ứng ban đầu nào phù hợp nhất?
A. Xóa commit chứa secret và kiểm tra không còn tham chiếu trong repository.
B. Chuyển repository sang private và chờ lần rotation định kỳ tiếp theo.
C. Thu hồi secret, xác định consumer, rà soát sử dụng và giữ bằng chứng.
D. Đổi tên service account để attacker không nhận ra credential cũ.
Đáp án đúng: C
