1. Một dịch vụ đặt hàng ngừng hoạt động khiến khách hàng không thể tạo giao dịch dù dữ liệu không bị lộ hoặc sửa. Thuộc tính CIA nào bị ảnh hưởng trực tiếp?
A. Confidentiality vì người dùng không xem được thông tin.
B. Integrity vì trạng thái giao dịch không được cập nhật.
C. Availability vì dịch vụ không sẵn sàng sử dụng.
D. Authenticity vì hệ thống không xác minh người dùng.
Đáp án đúng: C

2. Đánh giá rủi ro an toàn thông tin thường kết hợp những yếu tố nào?
A. Số lượng tài sản và số lượng chính sách đã ban hành.
B. Khả năng xảy ra của kịch bản và mức tác động.
C. Tuổi hệ thống và số lượng nhân viên vận hành.
D. Số phát hiện scanner và số lượng cảnh báo SIEM.
Đáp án đúng: B

3. Trong mô hình threat-vulnerability-risk, vulnerability là gì?
A. Tác nhân có thể gây hại cho tài sản.
B. Tổn thất khi một kịch bản xảy ra.
C. Điểm yếu có thể bị khai thác.
D. Biện pháp giảm khả năng hoặc tác động.
Đáp án đúng: C

4. Defense in depth nhằm đạt mục tiêu nào?
A. Dùng một kiểm soát mạnh duy nhất để bảo vệ toàn hệ thống.
B. Đặt mọi kiểm soát ở mạng biên để đơn giản hóa vận hành.
C. Tin dịch vụ nội bộ sau khi xác thực tại gateway.
D. Kết hợp nhiều lớp bảo vệ để tránh phụ thuộc một lớp.
Đáp án đúng: D

5. Nguyên tắc least privilege yêu cầu cấp quyền như thế nào?
A. Cấp quyền quản trị cho nhân viên để tránh gián đoạn.
B. Chỉ cấp quyền tối thiểu cần cho nhiệm vụ được giao.
C. Cấp cùng một nhóm quyền cho mọi người trong phòng ban.
D. Giữ quyền cũ để phòng trường hợp người dùng đổi nhiệm vụ.
Đáp án đúng: B

6. Zero Trust khác mô hình tin cậy theo mạng nội bộ ở điểm nào?
A. Cho phép mọi thiết bị trong subnet truy cập dịch vụ nội bộ.
B. Xác minh rõ danh tính và ngữ cảnh cho từng lần truy cập.
C. Chỉ yêu cầu MFA khi request đến từ Internet công cộng.
D. Bỏ kiểm soát nội bộ nếu kết nối đã dùng VPN.
Đáp án đúng: B

7. Một ứng dụng cũ không thể vá và chứa dữ liệu nhạy cảm. Biện pháp nào là xử lý rủi ro phù hợp khi chưa thể thay thế?
A. Ghi nhận lỗ hổng và giữ nguyên kết nối hiện tại.
B. Chấp nhận rủi ro vô thời hạn vì ứng dụng đã ổn định.
C. Tắt giám sát để tránh phát sinh cảnh báo từ hệ thống cũ.
D. Cô lập mạng, hạn chế quyền và bổ sung giám sát bù trừ.
Đáp án đúng: D

8. Kiểm soát nào là ví dụ điển hình của biện pháp phát hiện?
A. IDS phát hiện mẫu lưu lượng có dấu hiệu tấn công.
B. MFA thêm yếu tố xác minh trước khi cấp quyền truy cập.
C. Bản vá loại bỏ điểm yếu đã được nhà cung cấp xác nhận.
D. Mã hóa ổ đĩa bảo vệ dữ liệu khi thiết bị bị mất.
Đáp án đúng: A

9. Khác biệt giữa authentication và authorization là gì?
A. Authentication ghi log; authorization bảo vệ thông tin đăng nhập.
B. Authentication xác minh danh tính; authorization xác định quyền.
C. Authentication cấp role; authorization xác minh mật khẩu.
D. Authentication giới hạn tốc độ; authorization phát hiện mã độc.
Đáp án đúng: B

10. MFA được xem là mạnh hơn khi kết hợp những yếu tố nào?
A. Mật khẩu dài và câu hỏi bảo mật do người dùng tự đặt.
B. Các yếu tố thuộc những nhóm khác nhau như biết, có và là.
C. Hai mật khẩu khác nhau được gửi qua cùng một thiết bị.
D. Username và email phụ cùng được kiểm soát bởi một hộp thư.
Đáp án đúng: B

11. Vì sao passkey/WebAuthn có khả năng chống phishing tốt?
A. Credential gắn với RP ID/origin khi ký challenge.
B. Mã bí mật được gửi qua SMS và chỉ có hiệu lực một lần.
C. Người dùng xác nhận mọi domain qua hộp thoại của trình duyệt.
D. Website nhận được mật khẩu dùng chung để so sánh với bản lưu.
Đáp án đúng: A

12. Cách lưu mật khẩu người dùng nào phù hợp nhất?
A. Mã hóa AES rồi lưu khóa giải mã trong cùng database.
B. Tính SHA-256 nhanh nhiều lần với một salt dùng chung.
C. Dùng Argon2id với salt riêng và work factor phù hợp.
D. Lưu mật khẩu đã mã hóa Base64 để có thể khôi phục.
Đáp án đúng: C

13. Cách giảm brute force mà hạn chế nguy cơ attacker khóa tài khoản nạn nhân là gì?
A. Kết hợp rate limit, backoff và tín hiệu rủi ro.
B. Khóa vĩnh viễn tài khoản ngay khi nhập sai một lần.
C. Chỉ giới hạn số request theo một địa chỉ IP nguồn.
D. Tắt xác thực khi hệ thống nhận quá nhiều request đăng nhập.
Đáp án đúng: A

14. Khi thiết kế RBAC, quyền truy cập thường được gán theo cách nào?
A. Gán từng quyền trực tiếp cho từng request runtime.
B. So sánh vị trí mạng với nhãn phân loại của tài nguyên.
C. Dựa trên quan hệ giữa người dùng và đối tượng dữ liệu.
D. Gán permission cho role rồi gán role cho chủ thể.
Đáp án đúng: D

15. Separation of duties giúp giảm rủi ro nào?
A. Một cá nhân tự yêu cầu và tự phê duyệt thao tác nhạy cảm.
B. Một dịch vụ dùng nhiều instance để tăng khả năng sẵn sàng.
C. Một người dùng có nhiều thiết bị đăng nhập trong ngày.
D. Một hệ thống ghi log tại nhiều vùng lưu trữ khác nhau.
Đáp án đúng: A

16. Biện pháp nào giúp giảm session fixation sau khi xác thực thành công?
A. Giữ nguyên session ID để bảo toàn trạng thái trước đăng nhập.
B. Đưa session ID vào URL để ứng dụng dễ đồng bộ.
C. Tạo session ID mới sau đăng nhập và thay đổi đặc quyền.
D. Kéo dài thời hạn session cũ để tránh người dùng bị ngắt.
Đáp án đúng: C

17. Khi nào nên chọn mã hóa đối xứng thay vì bất đối xứng?
A. Khi cần xác minh chữ ký độc lập bằng public key.
B. Khi cần thiết lập danh tính signer bằng certificate.
C. Khi nhiều bên cần xác minh chữ ký mà không giữ secret.
D. Khi cần mã hóa lượng dữ liệu lớn với hiệu năng tốt.
Đáp án đúng: D

18. Phát biểu nào phân biệt đúng hashing và encryption?
A. Hashing có thể giải mã bằng khóa; encryption không thể khôi phục.
B. Hashing bảo đảm bí mật; encryption chỉ phát hiện thay đổi.
C. Hashing một chiều; encryption có thể giải mã bằng khóa phù hợp.
D. Hashing và encoding đều dùng secret key để bảo vệ dữ liệu.
Đáp án đúng: C

19. Client xác minh chứng chỉ TLS của server cần kiểm tra điều gì?
A. Chỉ kiểm tra chứng chỉ còn hạn và có public key.
B. Chỉ so sánh tên tổ chức trong subject với tên ứng dụng.
C. Chỉ xác minh chữ ký của server trên response đầu tiên.
D. Chain tin cậy, hostname, thời hạn và mục đích sử dụng.
Đáp án đúng: D

20. Vai trò phù hợp của KMS hoặc HSM trong quản lý khóa là gì?
A. Lưu mật khẩu người dùng dạng rõ để hỗ trợ khôi phục.
B. Thay thế hoàn toàn phân quyền cho ứng dụng sử dụng khóa.
C. Quản lý vòng đời khóa và giới hạn quyền sử dụng.
D. Tự động bảo đảm mọi dữ liệu được mã hóa đúng mục đích.
Đáp án đúng: C

21. Nguồn nào phù hợp để tạo khóa, nonce và token cần tính không đoán được?
A. Dùng CSPRNG với entropy và seed được quản lý an toàn.
B. Timestamp hiện tại ghép với process ID của ứng dụng.
C. Bộ đếm tăng dần được khởi tạo lại sau mỗi lần reboot.
D. Hàm random tổng quát không bảo đảm tính ngẫu nhiên mật mã.
Đáp án đúng: A

22. Network segmentation giúp giảm tác động của sự cố bằng cách nào?
A. Mã hóa mọi gói tin và loại bỏ nhu cầu kiểm soát truy cập.
B. Giới hạn luồng giữa các vùng để chặn lateral movement.
C. Cho phép mọi máy cùng subnet truy cập các dịch vụ nội bộ.
D. Thay thế endpoint protection bằng một firewall ở biên.
Đáp án đúng: B

23. Firewall policy theo deny-by-default nên được triển khai thế nào?
A. Chặn mặc định và chỉ mở luồng đã có nhu cầu, chủ sở hữu.
B. Cho phép mặc định rồi chặn các cổng có cảnh báo.
C. Mở mọi outbound traffic để ứng dụng dễ tích hợp.
D. Chỉ lọc theo địa chỉ IP, không cần xét port hoặc protocol.
Đáp án đúng: A

24. Phòng vệ DDoS cho dịch vụ công khai nên kết hợp biện pháp nào?
A. Chỉ tăng CPU của server khi lưu lượng tăng đột biến.
B. Chỉ chặn IP nguồn có số request lớn trong một phút.
C. Tắt TLS để giảm chi phí xử lý ở tầng ứng dụng.
D. Kết hợp scrubbing upstream, rate limit và WAF.
Đáp án đúng: D

25. Ưu tiên xử lý lỗ hổng nên dựa trên cơ sở nào?
A. Chỉ dựa vào điểm CVSS cao nhất trong danh sách.
B. Chỉ vá hệ thống có số lượng người dùng đông nhất.
C. Ưu tiên máy chủ cũ trước các tài sản mới.
D. Xét khai thác, phơi lộ, tác động và biện pháp bù trừ.
Đáp án đúng: D

26. Cách nào giảm nguy cơ SQL injection trong truy vấn database?
A. Chỉ xóa dấu nháy đơn khỏi chuỗi do người dùng gửi.
B. Mã hóa toàn bộ input bằng Base64 trước khi ghép SQL.
C. Dùng parameterized query, giới hạn quyền database.
D. Chặn từ khóa SELECT trong giao diện nhập liệu.
Đáp án đúng: C

27. Biện pháp nào giảm nguy cơ XSS khi hiển thị dữ liệu người dùng?
A. Chỉ kiểm tra độ dài chuỗi trước khi lưu vào database.
B. Encode output theo đúng ngữ cảnh hiển thị.
C. Dùng TLS để trình duyệt tự loại bỏ script độc hại.
D. Mã hóa database để nội dung HTML không thể thực thi.
Đáp án đúng: B

28. Trong mô hình shared responsibility của cloud, khách hàng thường vẫn chịu trách nhiệm gì?
A. Bảo vệ mọi thành phần vật lý của trung tâm dữ liệu cloud.
B. Thay thế hệ thống kiểm soát truy cập do nhà cung cấp quản lý.
C. Cấu hình danh tính, quyền, dữ liệu và workload của mình.
D. Tự vận hành nguồn điện và kiểm soát vật lý của vùng cloud.
Đáp án đúng: C

29. Kiểm soát nào giúp giảm rủi ro từ container image?
A. Quét image, chọn nguồn tin cậy, chạy ít quyền.
B. Chạy container bằng root để tránh lỗi quyền truy cập.
C. Dùng tag latest để luôn nhận image mới nhất tự động.
D. Nhúng secret vào image để runtime không cần truy xuất.
Đáp án đúng: A

30. Chữ ký artifact và provenance trong software supply chain giúp xác minh điều gì?
A. Artifact đến từ quy trình build và signer được tin cậy.
B. Artifact không chứa lỗ hổng hoặc lỗi logic nghiệp vụ.
C. Artifact luôn tương thích với mọi môi trường triển khai.
D. Artifact được mã hóa nên không thể bị đọc hoặc sao chép.
Đáp án đúng: A

31. Khi ghi log để điều tra sự cố, cần xử lý secret như thế nào?
A. Ghi đầy đủ password và token để có thể tái hiện request.
B. Chỉ xóa log khi phát hiện có người dùng trái phép.
C. Gửi nguyên header và body tới mọi hệ thống giám sát.
D. Loại bỏ hoặc che credential, token và dữ liệu nhạy cảm.
Đáp án đúng: D

32. SIEM phát hiện chuỗi tấn công tốt hơn khi làm gì?
A. Tương quan log identity, endpoint, network và app.
B. Chỉ đếm tổng số log nhận được từ firewall mỗi ngày.
C. Chỉ cảnh báo khi một máy chủ gửi lượng log bất thường.
D. Lưu riêng từng nguồn log và không chuẩn hóa timestamp.
Đáp án đúng: A

33. Khi phát hiện máy chủ có dấu hiệu xâm nhập, hành động nào phù hợp cho ứng phó sự cố?
A. Xóa file đáng ngờ ngay trước khi ghi nhận trạng thái máy.
B. Khởi động lại máy để loại bỏ mọi tiến trình lạ.
C. Chờ có kết luận pháp chứng rồi mới hạn chế kết nối.
D. Bảo toàn bằng chứng rồi khoanh vùng theo kế hoạch.
Đáp án đúng: D

34. Biện pháp nào giúp backup chống ransomware hiệu quả hơn?
A. Dùng chung tài khoản quản trị backup với production.
B. Lưu backup bất biến, tách biệt và thử restore định kỳ.
C. Chỉ giữ một bản sao trực tuyến để khôi phục nhanh.
D. Cho phép mọi admin production xóa backup khi cần dung lượng.
Đáp án đúng: B

35. Data minimization trong bảo vệ quyền riêng tư có nghĩa là gì?
A. Mã hóa tất cả dữ liệu rồi thu thập không giới hạn.
B. Giữ dữ liệu lâu dài để tránh phải thu thập lại.
C. Chỉ thu thập dữ liệu cần thiết cho mục đích đã xác định.
D. Chia sẻ dữ liệu định danh cho nhiều nhóm để tiện phân tích.
Đáp án đúng: C

36. Chỉ số nào phản ánh hiệu quả chương trình quản trị bảo mật tốt hơn số policy đã ban hành?
A. Tổng số tài liệu và số trang quy trình được phê duyệt.
B. Đo hiệu lực kiểm soát và tiến độ xử lý rủi ro.
C. Số lượng nhân viên đã nhận email nhắc nhở bảo mật.
D. Số công cụ bảo mật được mua và số dashboard được tạo.
Đáp án đúng: B
