Câu 1: Doanh nghiệp chạy ứng dụng trên VM thuộc dịch vụ IaaS và phát hiện guest OS chưa được vá. Ai chịu trách nhiệm thực hiện bản vá hệ điều hành này?
A. Đội vận hành hạ tầng vật lý của nhà cung cấp cloud.
B. Đội quản trị workload của doanh nghiệp sử dụng VM.
C. Đội quản lý trung tâm dữ liệu của nhà cung cấp cloud.
D. Đội hỗ trợ đường truyền của doanh nghiệp sử dụng VM.
Đáp án đúng: B

Câu 2: Doanh nghiệp dùng ứng dụng nhân sự SaaS. Công việc bảo mật nào vẫn cần đội nội bộ trực tiếp quản trị theo mô hình trách nhiệm chia sẻ?
A. Quản lý tài khoản người dùng và quyền xem hồ sơ nhân sự.
B. Cập nhật bản vá hypervisor trên hạ tầng chạy dịch vụ SaaS.
C. Thay thế các ổ đĩa vật lý bị hỏng ở trung tâm dữ liệu SaaS.
D. Cấu hình mạng lưu trữ của máy chủ vật lý cung cấp SaaS.
Đáp án đúng: A

Câu 3: Nhân viên truy cập tài nguyên của hai nhà cung cấp cloud; đội bảo mật cần thu hồi truy cập nhanh khi nhân viên nghỉ việc. Mô hình IAM nào phù hợp nhất?
A. Tạo tài khoản cloud riêng rồi đặt mật khẩu cùng chính sách.
B. Dùng một tài khoản quản trị cloud cho mọi thành viên nhóm.
C. Liên kết IAM với IdP tập trung, SSO và quyền theo vai trò.
D. Tạo API key cố định theo nhân viên ở từng tài khoản cloud.
Đáp án đúng: C

Câu 4: Tổ chức cần tài khoản quản trị khẩn cấp khi hệ thống SSO gặp sự cố. Cơ chế quản trị nào phù hợp cho break-glass access?
A. Duy trì tài khoản dự phòng có MFA, giám sát và quy trình sử dụng.
B. Cấp quyền quản trị khẩn cấp thường trực cho mọi kỹ sư của ca trực.
C. Tắt MFA của toàn bộ nhóm quản trị khi dịch vụ SSO bị lỗi.
D. Dùng chung tài khoản tác vụ CI/CD làm tài khoản quản trị khẩn.
Đáp án đúng: A

Câu 5: Pipeline CI/CD chạy ngoài hai nền tảng cloud cần triển khai hạ tầng nhưng không muốn giữ secret dài hạn. Cách cấp quyền nào an toàn hơn?
A. Lưu API key dài hạn của hai cloud trong kho secret CI/CD và xoay mỗi quý.
B. Dùng liên kết danh tính workload để lấy quyền tạm thời theo vai trò.
C. Tạo mỗi nền tảng một tài khoản quản trị và chia sẻ mật khẩu.
D. Nhúng token cloud của lập trình viên vào bước triển khai.
Đáp án đúng: B

Câu 6: Hệ thống cần mã hóa đối tượng lưu trữ và quản trị quyền sử dụng khóa độc lập với dịch vụ lưu dữ liệu. Cơ chế nào phù hợp?
A. Mã hóa TLS cho kết nối nhưng giữ đối tượng ở dạng plaintext.
B. Chỉ mã hóa bản sao lưu, không mã hóa dữ liệu đang được lưu.
C. Dùng KMS quản lý khóa và chính sách truy cập khi mã hóa lưu trữ.
D. Thay quyền truy cập bucket bằng whitelist IP ứng dụng.
Đáp án đúng: C

Câu 7: Quy định yêu cầu dữ liệu định danh khách hàng luôn lưu ở một vùng địa lý được duyệt, kể cả bản sao lưu. Kiểm soát nào giúp thực thi?
A. Chỉ gắn tag khu vực cho dữ liệu rồi để nhóm tự chọn nơi lưu.
B. Mã hóa dữ liệu trước khi sao chép sang mọi region nhà cung cấp hỗ trợ.
C. Chỉ kiểm tra vị trí máy chủ chính khi triển khai ban đầu.
D. Áp chính sách vùng cho cả lưu trữ chính và backup, kiểm tra liên tục.
Đáp án đúng: D

Câu 8: Một bucket bị mở quyền public ngoài ý muốn sau khi quản trị viên chỉnh trên console. Cách nào phát hiện và ngăn tái diễn hiệu quả?
A. Chỉ rà soát bucket trong đợt đánh giá bảo mật hằng quý.
B. Kiểm tra policy khi triển khai và giám sát drift cấu hình liên tục.
C. Chỉ quét mã nguồn và image container trước khi đưa ứng dụng lên production.
D. Thêm WAF ở frontend mà không kiểm tra ACL của bucket.
Đáp án đúng: B

Câu 9: IaC tạo firewall cho phép truy cập quản trị từ mọi địa chỉ IP. Điểm kiểm soát nào nên chặn cấu hình trước khi triển khai?
A. Đọc metric CPU và mạng sau triển khai để nhận ra dấu hiệu cấu hình sai.
B. Dựa vào cảnh báo chi phí hằng tháng để nhận ra rule mở rộng.
C. Chạy thử ứng dụng xong rồi sửa firewall nếu có sự cố.
D. Dùng policy-as-code trong CI để từ chối rule quản trị quá rộng.
Đáp án đúng: D

Câu 10: Nhóm SOC cần điều tra ai đã thay đổi IAM policy ở nhiều cloud trong 90 ngày qua. Thiết kế lưu bằng chứng nào đáp ứng?
A. Chỉ giữ dashboard IAM hiện tại cùng bản xuất cấu hình quyền hằng tuần.
B. Lưu log ứng dụng nhưng bỏ qua các sự kiện quản trị IAM.
C. Tập trung audit log có danh tính, thời gian và lưu giữ chống sửa.
D. Chỉ chụp màn hình danh sách quyền khi đến kỳ kiểm toán.
Đáp án đúng: C

Câu 11: Phát hiện access key của service account bị lộ trong kho mã nguồn công khai. Bước ứng phó nào giảm nguy cơ ngay và hỗ trợ điều tra?
A. Đổi tên service account rồi theo dõi lỗi của ứng dụng.
B. Xóa commit chứa key và giữ nguyên key để tránh gián đoạn.
C. Thu hồi key, cấp thay thế an toàn và rà lại log truy cập.
D. Đóng cảnh báo sau khi repository chuyển về chế độ private.
Đáp án đúng: C

Câu 12: Kiểm toán viên yêu cầu chứng minh chính sách chặn public storage đã được thực thi trong quý vừa qua. Bằng chứng nào thuyết phục nhất?
A. Lưu bản chính sách, lịch sử đánh giá, ngoại lệ và thời điểm kiểm tra.
B. Cung cấp danh sách các bucket ở thời điểm cuối quý, không có lịch sử.
C. Gửi một ảnh màn hình của policy hiện hành mà thiếu mốc hiệu lực.
D. Đưa báo cáo chi phí lưu trữ ba tháng làm bằng chứng kiểm soát.
Đáp án đúng: A

Câu 13: Tổ chức dùng IaaS, PaaS và SaaS từ nhiều nhà cung cấp. Cách nào giúp tránh khoảng trống trách nhiệm bảo mật?
A. Lập ma trận chủ sở hữu kiểm soát theo dịch vụ và mô hình triển khai.
B. Yêu cầu một nhà cung cấp chịu trách nhiệm cho mọi dữ liệu ở mọi cloud.
C. Dùng chung chính sách IAM một dòng cho tất cả dịch vụ cloud.
D. Chỉ phân công SOC xử lý mọi rủi ro và bỏ qua nhóm vận hành.
Đáp án đúng: A

Câu 14: Pipeline triển khai container phát hiện thư viện trong image có lỗ hổng nghiêm trọng đã có bản vá. Cách quản trị nào phù hợp?
A. Chỉ thay Security Group để chặn cổng của container đang chạy.
B. Chờ kết quả kiểm thử ứng dụng rồi mới cân nhắc vá thư viện có lỗi.
C. Tạm ẩn cảnh báo từ trình quét để pipeline tiếp tục phát hành.
D. Chặn phát hành, cập nhật thư viện và quét lại image trước triển khai.
Đáp án đúng: D

Câu 15: Doanh nghiệp đặt RPO 15 phút và RTO 1 giờ cho hệ thống dữ liệu đa vùng. Hoạt động nào kiểm chứng được hai mục tiêu đó?
A. Đếm số snapshot được tạo thành công và tổng kích thước lưu trữ.
B. Diễn tập phục hồi hoặc failover, đo dữ liệu mất và thời gian khôi phục.
C. Kiểm tra quyền của nhóm quản trị backup mà không phục hồi thử.
D. Chỉ kiểm tra dịch vụ đang có ít nhất hai bản sao ở một vùng.
Đáp án đúng: B

Câu 16: Dự án xin ngoại lệ tạm thời cho một chính sách bảo mật vì chưa thể nâng cấp. Cách xử lý nào bảo đảm ngoại lệ được quản trị?
A. Xóa policy khỏi phạm vi dự án để không tiếp tục phát hiện vi phạm.
B. Gia hạn ngoại lệ mặc định mỗi năm nếu dự án chưa báo sự cố.
C. Chấp nhận qua chat nhóm và bỏ qua đánh giá tác động bảo mật.
D. Ghi rủi ro, người phê duyệt, kiểm soát bù và ngày hết hạn ngoại lệ.
Đáp án đúng: D
