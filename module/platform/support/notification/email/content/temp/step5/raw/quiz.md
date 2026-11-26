Provider trả trạng thái đã nhận yêu cầu gửi email; kết luận nào phù hợp?
A. Yêu cầu được nhận, chưa chứng minh thư đã tới hộp
B. Hộp thư người nhận đã xác nhận phát thành công
C. Tên miền gửi đã qua kiểm tra SPF và DMARC
D. Thư chắc chắn được người nhận mở và đọc
Đáp án đúng: A

Bản ghi SPF giúp hệ thống nhận thư kiểm chứng điều gì?
A. Nội dung email không bị thay đổi trong đường truyền
B. Máy chủ gửi có được phép gửi cho domain envelope
C. Địa chỉ From luôn khớp DKIM dù chưa xác thực
D. Người nhận đã đồng ý nhận thông báo từ ứng dụng
Đáp án đúng: B

DKIM chủ yếu hỗ trợ xác thực email bằng cơ chế nào?
A. Kiểm tra chữ ký trên header/body với khóa DNS
B. Mã hóa toàn bộ nội dung thư để chỉ người nhận đọc
C. Chỉ so địa chỉ IP server với bản ghi MX domain
D. Xác minh mailbox người nhận còn hoạt động
Đáp án đúng: A

DMARC liên hệ với SPF và DKIM theo cách nào?
A. Mã hóa SMTP password bằng khóa DNS của domain
B. Áp chính sách theo SPF hoặc DKIM aligned với From
C. Tự thay danh sách địa chỉ được phép gửi của SPF
D. Kiểm tra bản dịch nội dung email theo template
Đáp án đúng: B

Template HTML chứa tên khách hàng do người dùng nhập; biện pháp nào cần làm?
A. Tin cậy chuỗi biến vì template đã được duyệt
B. Escape dữ liệu biến trước khi chèn vào HTML email
C. Chỉ lọc phần subject, không lọc HTML body
D. Tự dùng biến làm tên thẻ để giữ định dạng
Đáp án đúng: B

Lệnh gửi email trả thành công qua API provider; cách theo dõi phát thư nào thích hợp?
A. Lưu duy nhất thời gian render template nội bộ
B. Chỉ dựa trên HTTP status đã nhận để kết luận delivered
C. Đánh dấu mọi email delivered trước khi gọi API
D. Gắn message ID và cập nhật theo delivery event
Đáp án đúng: D

SMTP trả mã lỗi 4xx tạm thời; hàng đợi nên xử lý thế nào?
A. Chặn địa chỉ nhận vĩnh viễn sau lỗi đầu tiên
B. Gửi lặp liên tục không chờ và không giới hạn
C. Retry giới hạn với backoff phù hợp chính sách
D. Coi email đã giao thành công và xóa khỏi queue
Đáp án đúng: C

Một địa chỉ báo hard bounce vì mailbox không tồn tại; nên hành động gì?
A. Tăng tần suất gửi để kiểm tra mailbox hồi phục
B. Thử lại không giới hạn vì email chắc chắn bị chậm
C. Dừng gửi tới địa chỉ đó và ghi lý do suppression
D. Xóa toàn bộ tài khoản của người dùng trên ứng dụng
Đáp án đúng: C

Khi có feedback complaint rằng người nhận đánh dấu spam, điều gì quan trọng?
A. Ghi complaint và cân nhắc chặn gửi tiếp tới địa chỉ
B. Thay From ngẫu nhiên để tiếp tục gửi ngay
C. Chuyển complaint thành trạng thái delivered mới
D. Bỏ qua vì không liên quan chất lượng danh sách
Đáp án đúng: A

Trong hệ thống queue email, idempotency key giúp giải quyết gì?
A. Tránh gửi trùng một thông báo khi job retry
B. Tự sửa nội dung template khi người dùng đổi email
C. Bỏ yêu cầu lưu trạng thái cho mỗi job đang gửi
D. Bảo đảm thư không bao giờ bị provider lọc spam
Đáp án đúng: A

Khi provider áp giới hạn số email mỗi phút, cách vận hành nào phù hợp?
A. Cho worker gửi không giới hạn để đo sức chịu tải
B. Tăng số kết nối mà không điều chỉnh tốc độ gửi
C. Bỏ thống kê rate limit vì không ảnh hưởng người nhận
D. Điều tiết tốc độ tiêu thụ queue và quan sát backlog
Đáp án đúng: D

Muốn gửi email cá nhân hóa cho nhiều người mà vẫn giữ riêng tư, nên làm gì?
A. Lưu dữ liệu nhạy cảm vào header để dễ đối soát
B. Đặt toàn bộ địa chỉ khách hàng vào trường To
C. Đưa token đăng nhập chung vào mọi template email
D. Render nội dung riêng, tránh lộ danh sách người nhận
Đáp án đúng: D

Webhook báo delivered/bounced từ provider nên được tiếp nhận thế nào?
A. Nhận event không cần đối chiếu message ID của job
B. Thay trạng thái bất kể thứ tự hay thời điểm event
C. Xác thực callback và loại bỏ event trùng
D. Tin mọi HTTP POST có tên event tương tự provider
Đáp án đúng: C

Hai callback giao hàng đến không đúng thứ tự, cập nhật trạng thái thế nào hợp lý?
A. Luôn lấy event đến sau làm sự thật dù timestamp cũ
B. Dùng nội dung subject để đoán event nào mới nhất
C. Xóa log event trước rồi tính lại từ email template
D. Áp quy tắc chuyển trạng thái để tránh sự kiện cũ ghi đè
Đáp án đúng: D

Nhóm metric nào hữu ích để giám sát vận hành gửi email?
A. Tỷ lệ cache hit của hệ thống dịch thuật tài liệu
B. Số lượng class Java và tổng số interface đang dùng
C. Tỷ lệ bounce/complaint, độ trễ và backlog queue
D. Mức CPU của IDE lập trình trên máy cá nhân
Đáp án đúng: C

SMTP credential và nội dung thư nhạy cảm nên được bảo vệ thế nào?
A. Ghi nội dung thư đầy đủ vào mọi dòng log gửi
B. Lưu secret an toàn, dùng TLS và hạn chế log
C. Chuyển tất cả credential sang header email hiển thị
D. Nhúng mật khẩu vào source để dễ tái tạo lỗi
Đáp án đúng: B
