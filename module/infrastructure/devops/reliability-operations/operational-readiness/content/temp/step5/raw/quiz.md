Câu 1: Dịch vụ mới có dashboard và kiểm thử chức năng đạt, nhưng chưa có nhóm chịu trách nhiệm ngoài giờ. Quyết định ORR nào phù hợp?
A. Cho phát hành khi pipeline CI/CD không còn lỗi kiểm thử và lịch đã chốt.
B. Chuyển việc nhận cảnh báo cho đội phát triển sau ngày go-live.
C. Ghi số điện thoại hỗ trợ vào wiki rồi xem như đã bàn giao.
D. Chốt owner, lịch trực và đường escalation trước khi phát hành.
Đáp án đúng: D

Câu 2: API có SLO thành công 99,9% đối với các yêu cầu hợp lệ. SLI nào phản ánh trực tiếp mục tiêu này khi đánh giá sẵn sàng?
A. Tỷ lệ VM hoạt động trên tổng số VM của cụm hạ tầng hiện tại.
B. Tỷ lệ yêu cầu hợp lệ thành công trên tổng yêu cầu hợp lệ.
C. Tỷ lệ thời gian CPU dưới 80% của máy chạy API.
D. Tỷ lệ ổ đĩa còn dung lượng trên tổng dung lượng cấp phát.
Đáp án đúng: B

Câu 3: Dự kiến lượt truy cập tăng ba lần vào đợt mở bán; hệ thống chưa được thử tại mức tải này. Bằng chứng nào cần có trước go-live?
A. Kết quả thử tải gần mức dự báo, điểm nghẽn và khả năng mở rộng.
B. Số VM hiện tại cùng giả định mỗi VM đáp ứng mọi mức tăng tải.
C. Báo cáo CPU của tuần ít người dùng để ngoại suy dịp mở bán.
D. Danh sách instance dự phòng chưa kiểm chứng khả năng khởi tạo.
Đáp án đúng: A

Câu 4: CPU tăng lên 95% trong vài giây mỗi đêm, nhưng API không lỗi và vẫn đạt SLO. Chính sách cảnh báo nào hợp lý cho production?
A. Page đội trực mỗi lần CPU vượt 90% dù dịch vụ không bị lỗi API.
B. Tắt hết cảnh báo vì API chưa từng vi phạm SLO trong một tuần.
C. Chỉ gửi email khi CPU trung bình cả tháng vượt 90%.
D. Ưu tiên page theo burn rate SLO, theo dõi CPU bằng ngưỡng phù hợp.
Đáp án đúng: D

Câu 5: Khi cache lỗi, người trực mới chưa biết xác định ảnh hưởng hay khôi phục dịch vụ. Runbook nào đạt yêu cầu bàn giao vận hành?
A. Sơ đồ kiến trúc chi tiết kèm tên tác giả từng microservice.
B. Các biểu đồ CPU, RAM và chi phí thu thập trong quý trước.
C. Điều kiện kích hoạt, bước chẩn đoán, giảm tác động và leo thang.
D. Danh sách lệnh khởi động lại mà không có cách kiểm tra kết quả.
Đáp án đúng: C

Câu 6: Dịch vụ đặt RPO 15 phút, RTO 1 giờ nhưng hiện chỉ có snapshot hằng ngày và chưa thử restore. Cần xác minh điều gì?
A. Thiết lập bảo vệ dữ liệu đáp ứng RPO rồi diễn tập đo thời gian phục hồi.
B. Số snapshot đã tạo thành công trong tháng và dung lượng từng bản sao lưu.
C. Thời gian tạo snapshot hằng ngày mà không phục hồi dữ liệu thử.
D. Số replica ứng dụng có thể chạy khi database mất toàn bộ dữ liệu.
Đáp án đúng: A

Câu 7: Ứng dụng được triển khai canary; phiên bản mới có thể khiến lỗi thanh toán tăng. Điều kiện go-live nào cần chứng minh trước khi tăng lưu lượng?
A. Canary có ít request nhưng toàn bộ pod khởi động thành công.
B. Có ngưỡng lỗi/độ trễ để dừng canary và rollback đã thử nghiệm.
C. Đã chuẩn bị lịch phát hành, nên bỏ giám sát trong thời gian chuyển.
D. Có đủ tài liệu thiết kế để hoàn tác bằng sửa mã trong ngày sau.
Đáp án đúng: B

Câu 8: Hai đội cùng xử lý sự cố nhưng chưa thống nhất ai chỉ huy và ai cập nhật khách hàng. Bài kiểm tra ORR nào phát hiện lỗ hổng này?
A. Đo băng thông giữa các máy để bảo đảm luồng thông tin ổn định.
B. Chạy kiểm thử hiệu năng cho endpoint không liên quan tới sự cố.
C. Diễn tập tình huống, phân vai chỉ huy và thử quy trình liên lạc.
D. Đọc danh sách thành viên hai đội để xác nhận nhân sự đầy đủ.
Đáp án đúng: C

Câu 9: Checkout phụ thuộc cổng thanh toán bên ngoài; nhà cung cấp này thường timeout. ORR cần bằng chứng nào về khả năng chịu lỗi?
A. Bảo đảm tỷ lệ CPU của checkout vẫn thấp trong điều kiện bình thường.
B. Tăng số lần retry không giới hạn để tránh bỏ giao dịch khi cổng thanh toán chậm.
C. Thay cổng thanh toán bằng kết nối trực tiếp ở mọi môi trường.
D. Thử lỗi phụ thuộc, xác nhận timeout, retry có giới hạn và xử lý an toàn.
Đáp án đúng: D

Câu 10: Request đi qua gateway và ba microservice nhưng khi tăng độ trễ không lần ra chỗ chậm. Năng lực quan sát nào nên là tiêu chí ORR?
A. Chỉ thu CPU trung bình của gateway và số pod đang hoạt động.
B. Thu log riêng từng dịch vụ mà không liên kết ID yêu cầu.
C. Có tracing xuyên dịch vụ và liên kết trace với log, metric.
D. Đo tổng băng thông hằng ngày của mạng giữa các vùng.
Đáp án đúng: C

Câu 11: Workload trên cloud dùng khóa quản trị cố định để đọc database, lưu trong cấu hình triển khai. Điều gì cần làm trước khi chấp thuận vận hành?
A. Đổi tên khóa quản trị để khó đoán khi bị lộ trong log.
B. Bật thêm audit log nhưng giữ quyền quản trị để tránh lỗi quyền sau nâng cấp.
C. Chuyển sang danh tính/quyền tối thiểu, quản lý và xoay secret an toàn.
D. Chỉ mã hóa đường truyền, không đổi quyền của khóa đã cấp.
Đáp án đúng: C

Câu 12: Hồ sơ ORR ghi 'đã thử phục hồi' nhưng không nêu phiên bản, thời điểm hay kết quả. Bằng chứng nào giúp người duyệt đánh giá?
A. Bản tự khai rằng đội phát triển đã chạy mọi phép thử quan trọng.
B. Kết quả restore có thời điểm, phạm vi, RTO/RPO và người xác nhận.
C. Số lượng ticket đóng trong sprint gần nhất của đội dự án.
D. Bản tổng hợp đường dẫn dashboard mà không có kết quả khôi phục.
Đáp án đúng: B

Câu 13: Phát hành mới thêm cột bắt buộc vào CSDL khi phiên bản ứng dụng cũ và mới có thể chạy song song. Cách triển khai nào giảm rủi ro?
A. Dùng expand-contract, giữ tương thích giữa phiên bản và thử rollback.
B. Đổi schema trước và giả định mọi instance đã nhận bản ứng dụng mới trong một đợt.
C. Xóa cột cũ ngay lập tức vì quá trình rollout sẽ hoàn tất nhanh.
D. Tắt kiểm tra tương thích schema để rút ngắn thời gian chuyển đổi.
Đáp án đúng: A

Câu 14: Sự kiện dồn vào queue làm consumer xử lý chậm; ORR cần chứng minh hệ thống chịu được đợt tăng tải. Cách đánh giá nào phù hợp?
A. Theo dõi CPU của producer và bỏ qua backlog của hàng đợi.
B. Thử tải đột biến, đo tuổi message, backlog và năng lực xử lý.
C. Đếm tổng message đã gửi từ đầu tháng để ước tính throughput cao nhất.
D. Tăng thời gian lưu message thay cho kiểm thử tốc độ consumer.
Đáp án đúng: B

Câu 15: Runbook đã được viết nhưng nhóm trực chưa có quyền thao tác và chưa nhận thử alert. Việc nào phải hoàn tất trước bàn giao?
A. Gửi tài liệu qua email, coi quyền truy cập là việc sau go-live.
B. Chỉ định một người viết runbook thay cho người trực ban đêm.
C. Thêm dashboard hiển thị trạng thái mà chưa kiểm tra cảnh báo.
D. Kiểm tra quyền người trực, page thử và thực hành bước xử lý.
Đáp án đúng: D

Câu 16: ORR phát hiện thiếu thử nghiệm phục hồi dữ liệu và chưa có phương án rollback, trong khi ngày phát hành đã công bố. Quyết định nào phù hợp?
A. Tạm hoãn go-live đến khi khắc phục và chứng minh khả năng phục hồi.
B. Triển khai đúng lịch rồi xây rollback khi có sự cố production.
C. Phát hành nếu các bài kiểm thử chức năng hiện đều thành công.
D. Chuyển trách nhiệm phục hồi sang nhóm trực sau khi phát hành.
Đáp án đúng: A
