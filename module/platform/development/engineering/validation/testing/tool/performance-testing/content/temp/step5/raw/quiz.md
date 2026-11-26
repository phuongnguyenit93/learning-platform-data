Báo cáo latency ghi p95 = 800 ms; cách hiểu nào phù hợp?
A. Trung bình mọi yêu cầu có thời gian đáp ứng đúng 800 ms
B. Khoảng 95% yêu cầu có độ trễ không quá 800 ms
C. Khoảng 95% yêu cầu mất thời gian nhiều hơn 800 ms
D. Thời gian của mọi yêu cầu đều nhỏ hơn 800 ms
Đáp án đúng: B

Trong kiểm thử hiệu năng, throughput thường biểu thị điều gì?
A. Số user đã đăng ký tài khoản trong hệ thống
B. Mức dùng CPU trung bình khi không có request
C. Độ trễ lớn nhất của một request trong quá trình đo
D. Số thao tác hoàn tất trên một đơn vị thời gian
Đáp án đúng: D

Thêm tải khiến latency tăng nhưng throughput gần như không đổi; suy luận nào hợp lý?
A. Có thể hệ thống đã tiến gần giới hạn năng lực xử lý
B. Tỷ lệ lỗi chắc chắn đã giảm theo số request
C. Độ trễ tăng chứng tỏ hệ thống tự động mở rộng tốt
D. Throughput không đổi chứng minh chưa phát sinh hàng đợi
Đáp án đúng: A

Load test ở mức tải dự kiến nhằm trả lời câu hỏi nào?
A. Hệ thống đáp ứng chỉ tiêu chất lượng ở tải kỳ vọng?
B. Khi nào hệ thống hoàn toàn ngừng phản hồi dưới tải cực đại?
C. Bộ nhớ rò rỉ thế nào sau nhiều ngày liên tục?
D. Phản ứng tức thời ra sao khi lưu lượng tăng đột biến?
Đáp án đúng: A

Một spike test được thiết kế chủ yếu để quan sát điều gì?
A. Thời gian chạy unit test của một method không có I/O
B. Chi phí duy trì một virtual user khi không gửi request
C. Độ ổn định khi lưu lượng tăng đột biến
D. Rò rỉ bộ nhớ sau nhiều giờ chạy tại tải ổn định
Đáp án đúng: C

Soak test khác bài đo ngắn ở mục tiêu nào quan trọng?
A. Chỉ đo thời gian khởi động của công cụ phát tải
B. Duy trì tải lâu để lộ rò rỉ và suy giảm dần
C. Dồn mọi user vào một giây để tạo đỉnh rất cao
D. Đổi tất cả request thành truy vấn read-only
Đáp án đúng: B

Muốn mô phỏng hành vi người dùng thật, kịch bản phát tải nên dựa vào gì?
A. Chỉ một API GET với payload nhỏ cho toàn bộ lượt
B. Mọi user luôn gửi request cùng một mili giây
C. Chỉ số thread tối đa của máy phát tải
D. Tỷ lệ tác vụ, cỡ dữ liệu và nhịp thao tác
Đáp án đúng: D

Chỉ cấu hình 100 virtual users đã đủ xác định throughput hay chưa?
A. Đủ; mỗi user chỉ phát một request trong cả test
B. Đủ; throughput bằng đúng số connection đang mở
C. Chưa; còn tùy nhịp yêu cầu và thời gian xử lý
D. Đủ; luôn đạt chính xác 100 request mỗi giây
Đáp án đúng: C

Vì sao cần đo CPU, RAM và I/O đồng thời với latency khi phát tải?
A. Liên hệ độ trễ với điểm nghẽn tài nguyên
B. Để loại bỏ nhu cầu đo throughput của hệ thống
C. Để suy ra mọi lỗi đều đến từ thiếu bộ nhớ
D. Để thay thế hoàn toàn việc thống kê tỷ lệ lỗi
Đáp án đúng: A

Vì sao nên nhìn p99 ngoài giá trị latency trung bình?
A. p99 luôn bằng median nếu lượng request đủ lớn
B. p99 là tổng thời gian xử lý của mọi request
C. Phát hiện đuôi chậm bị trung bình che lấp
D. p99 đo tỷ lệ lỗi HTTP chứ không phải thời gian
Đáp án đúng: C

Khi đánh giá error rate dưới tải, cách tính nào hữu ích?
A. Lấy số user ảo chia cho số luồng xử lý của server
B. Lấy yêu cầu lỗi và timeout chia cho tổng yêu cầu
C. Chỉ đếm lỗi có stack trace trong log ứng dụng
D. Chỉ lấy số phản hồi 500 mà bỏ lỗi mạng và timeout
Đáp án đúng: B

Dữ liệu thử cho performance test cần có đặc điểm nào để kết quả đáng tin?
A. DB luôn rỗng nên chỉ mục không phải hoạt động
B. Dữ liệu đại diện về kích thước và phân phối khóa
C. Cùng một khóa duy nhất để mọi request dùng chung
D. Mọi payload chỉ có một field để phản hồi nhanh
Đáp án đúng: B

Trước khi đo giai đoạn steady state trên Java, warm-up có ích gì?
A. Tắt garbage collector để giảm biến động của kết quả
B. Buộc mọi request tiếp theo bỏ qua bước xác thực
C. Biến tất cả lần chạy thành cùng một kết quả latency
D. Để JIT và cache ổn định trước khi đo
Đáp án đúng: D

Để kiểm chứng một tối ưu SQL làm latency tốt hơn, cách so sánh nào đáng tin?
A. Giữ tải, môi trường và cách đo giống nhau trước-sau
B. Chỉ so số request giữa các lần có dữ liệu khác nhau
C. Chỉ đo lần chạy nhanh nhất rồi loại mọi kết quả còn lại
D. Tăng cả sức mạnh máy chủ và số client ở lần đo sau
Đáp án đúng: A

Máy phát tải đạt 100% CPU trong khi server còn rảnh; điều này gợi ý gì?
A. Không cần quan sát gì ngoài latency của server
B. Server chắc chắn đã đạt công suất xử lý cực đại
C. Máy phát tải có thể giới hạn kết quả đo
D. Database chắc chắn đã bị khóa toàn bộ các bảng
Đáp án đúng: C

Khi tải tăng, DB lock wait và latency cùng tăng, nên điều tra gì trước?
A. Tăng thread ứng dụng mà không xem thời gian chờ SQL
B. Bỏ hết timeout để request có thể chờ vô hạn
C. Giảm số assertion của unit test để hạ độ trễ
D. Rà query, transaction và tranh chấp khóa
Đáp án đúng: D
