Câu 1: API nhận webhook vài chục lần mỗi ngày, mỗi lần chạy dưới một giây, nhiều giờ không có yêu cầu. Kiến trúc tính toán nào phù hợp để hạn chế tài nguyên nhàn rỗi?
A. Duy trì VM thường trực dành riêng cho webhook.
B. Duy trì pod cố định luôn sẵn sàng nhận webhook.
C. Dùng HTTP-triggered FaaS mở rộng theo yêu cầu.
D. Dùng batch job mỗi đêm gộp các webhook.
Đáp án đúng: C

Câu 2: Java function HTTP nhận JSON sai schema; cần báo lỗi đầu vào trước khi ghi dữ liệu. Phản hồi nào phù hợp?
A. Trả HTTP 400 kèm mô tả trường không hợp lệ.
B. Trả HTTP 200 kèm lỗi trong nội dung phản hồi.
C. Trả HTTP 503 để client retry ngay lập tức.
D. Trả HTTP 302 chuyển hướng sang trang tài liệu.
Đáp án đúng: A

Câu 3: Queue có cơ chế at-least-once nên sự kiện tạo hóa đơn có thể được giao hai lần. Bảo vệ nào tránh lập hai hóa đơn?
A. Tăng thời gian visibility timeout của message.
B. Ghi các event đã thấy vào biến static trong JVM.
C. Đánh dấu message xong ngay trước khi ghi hóa đơn.
D. Dùng event ID làm khóa duy nhất khi tạo hóa đơn.
Đáp án đúng: D

Câu 4: Hàm Java cần giữ giỏ hàng qua nhiều request; thực thi có thể ở instance khác hoặc mới. Nơi lưu trạng thái nào phù hợp?
A. Lưu giỏ hàng vào DB dùng chung theo session ID.
B. Lưu giỏ hàng trong trường static của Java class.
C. Lưu giỏ hàng trong thư mục tạm trên instance.
D. Lưu giỏ hàng trong ThreadLocal của mỗi request.
Đáp án đúng: A

Câu 5: Một message lỗi dữ liệu, mỗi lần xử lý đều ném exception; retry vô hạn làm tắc hàng đợi. Giải pháp nào phù hợp?
A. Chạy lại vô hạn với thời gian chờ bằng nhau.
B. Giới hạn lần thử rồi đưa message vào DLQ.
C. Nuốt exception rồi ack như đã xử lý thành công.
D. Tăng số instance song song để nhận thêm lỗi.
Đáp án đúng: B

Câu 6: Java FaaS sau thời gian rảnh: lần gọi đầu mất hai giây, lần kế chỉ 100 ms, không đổi tải. Hiện tượng nào giải thích hợp lý nhất?
A. Mỗi lần gọi đầu đều phải chờ bộ nhớ cache CDN.
B. Bộ cân bằng tải giữ nhiều connection hơn lần đầu.
C. Instance mới cần khởi tạo JVM và dependency.
D. Mọi request sau đều bỏ qua xác thực đầu vào.
Đáp án đúng: C

Câu 7: Yêu cầu HTTP đến Java function mất tối đa năm giây, trong khi xử lý ảnh hết hai phút. Nên thiết kế thế nào?
A. Giữ request HTTP mở đến khi tác vụ hoàn tất.
B. Đẩy công việc vào queue và trả 202 Accepted.
C. Tăng số luồng Java để xử lý ngay trong request.
D. Trả 200 trước khi lưu yêu cầu vào hệ thống.
Đáp án đúng: B

Câu 8: Hàm serverless có thể scale tới 300 invocation đồng thời nhưng DB chỉ chịu 40 kết nối. Cách phòng ngừa nào thích hợp?
A. Tăng thời gian chờ DB cho mọi invocation.
B. Bỏ giới hạn concurrency cho hàm truy cập DB.
C. Thêm retry tức thì khi DB từ chối kết nối.
D. Giới hạn concurrency và dùng pool/proxy DB.
Đáp án đúng: D

Câu 9: Java function được kích hoạt khi có ảnh mới và chỉ cần đọc ảnh từ một bucket để tạo thumbnail. Nên cấp quyền lưu trữ nào?
A. Quyền quản trị mọi bucket của tài khoản.
B. Quyền ghi đối tượng vào mọi bucket có sẵn.
C. Quyền đọc và xóa mọi dữ liệu object storage.
D. Chỉ quyền đọc đối tượng ở bucket nguồn.
Đáp án đúng: D

Câu 10: Trước khi chuyển cron job chạy vài lần mỗi ngày sang FaaS, cần ước tính phần chi phí thực thi dựa trên yếu tố nào?
A. Số IP tĩnh và số máy ảo đang ở trạng thái bật.
B. Số lượt gọi, thời lượng và bộ nhớ cấu hình.
C. Số user IAM và số rule của firewall trong VPC.
D. Số record DNS và số subnet trong tài khoản.
Đáp án đúng: B

Câu 11: Trong luồng HTTP đến queue rồi đến Java function, log phân tán khiến khó ghép các bước lỗi. Bổ sung cơ chế nào để truy vết?
A. Chỉ ghi timestamp của từng service vào log.
B. Đổi tên queue theo mỗi lần gửi sự kiện.
C. Truyền correlation ID và log có cấu trúc.
D. Ghi toàn bộ payload nhạy cảm vào mọi log.
Đáp án đúng: C

Câu 12: Sự kiện cập nhật tồn kho phiên bản 12 đến sau phiên bản 13 do được giao lại. Cách nào tránh ghi đè trạng thái mới bằng trạng thái cũ?
A. Kiểm tra version và chỉ áp dụng khi mới hơn.
B. Dùng thời điểm function nhận event làm thứ tự.
C. Luôn ghi state theo event đến sau cùng.
D. Giữ kết quả trong biến static của JVM.
Đáp án đúng: A

Câu 13: Hàm Java có thể được tái sử dụng cùng instance qua nhiều invocation. Cách tổ chức HTTP client gọi dịch vụ ngoài nào phù hợp?
A. Tái dùng HTTP client, xử lý timeout và lỗi.
B. Khởi tạo lại HTTP client sau mỗi dòng log.
C. Lưu token người dùng cuối vào biến static.
D. Tắt connection timeout để giữ client luôn mở.
Đáp án đúng: A

Câu 14: Function xử lý sự kiện object-created và ghi thumbnail về cùng bucket, gây vòng lặp kích hoạt. Thiết kế nào ngăn vòng lặp?
A. Tăng memory limit trước khi ghi tệp mới.
B. Chuyển sang retry với backoff lớn hơn.
C. Giảm concurrency xuống một invocation.
D. Lọc prefix sự kiện, tách prefix ảnh xuất.
Đáp án đúng: D

Câu 15: Một ETL Java chạy bốn giờ liên tục với CPU ổn định và kết nối cơ sở dữ liệu dài; nhận định nào đúng khi cân nhắc FaaS?
A. FaaS luôn rẻ hơn do không giữ máy chủ riêng.
B. Ưu tiên batch/container job cho xử lý kéo dài.
C. Chỉ cần tăng memory để bỏ hết giới hạn thời gian.
D. Chỉ cần ping giữ ấm để chạy không gián đoạn.
Đáp án đúng: B

Câu 16: Nhóm muốn nâng phiên bản Java function mà không chuyển toàn bộ request một lúc, cần quan sát lỗi và có thể rollback. Cách nào?
A. Thay toàn bộ code trên phiên bản đang chạy.
B. Đổi DNS ứng dụng tới cùng một endpoint.
C. Chia traffic giữa các revision đã gắn phiên bản.
D. Tăng concurrency để che lỗi từ bản mới.
Đáp án đúng: C
