1. Trong kiểm thử độ tin cậy, SLI thường biểu diễn điều gì?
A. Cam kết pháp lý áp dụng cho mọi khách hàng
B. Một lần triển khai thử nghiệm ở môi trường dự phòng
C. Chỉ số đo mức dịch vụ thực nhận được của hệ thống
D. Tập lệnh bắt buộc để khởi động lại ứng dụng
Đáp án đúng: C

2. SLO về availability 99,9% có ý nghĩa gì trong kỳ đo?
A. Mỗi sự cố phải được khôi phục trong 99,9 giây
B. Ít nhất 99,9% CPU của máy chủ phải được sử dụng
C. Mọi request phải có độ trễ đúng 99,9 mili giây
D. Mục tiêu khả dụng ít nhất 99,9% trong kỳ đo
Đáp án đúng: D

3. Với SLO thành công 99,9%, error budget theo tỷ lệ là bao nhiêu?
A. Cho phép tối đa 1% request lỗi trong kỳ áp dụng
B. Cho phép tối đa 0,1% request lỗi trong kỳ áp dụng
C. Cho phép tối đa 9,9% request lỗi trong kỳ áp dụng
D. Cho phép tối đa 0,01% request lỗi trong kỳ áp dụng
Đáp án đúng: B

4. SLA khác SLO ở khía cạnh nào thường gặp?
A. SLA là cam kết với khách hàng, có thể kèm chế tài
B. SLA là chỉ số kỹ thuật ghi lại mỗi giây trên server
C. SLA là bước tự động retry mọi request bị thất bại
D. SLA là phép đo thời gian khởi động JVM tại local
Đáp án đúng: A

5. RTO trong kế hoạch khôi phục thảm họa dùng để xác định gì?
A. Số bản sao dữ liệu cần được ghi trên từng node
B. Giới hạn thời gian gián đoạn chấp nhận được
C. Số lượng retry tối đa cho mỗi request thất bại
D. Khoảng thời gian giữa các lần chạy unit test
Đáp án đúng: B

6. RPO trong kiểm thử phục hồi mô tả giới hạn nào?
A. Thời gian lâu nhất để ứng dụng chạy lại thành công
B. Lượng dữ liệu có thể mất tính theo thời gian
C. Mức CPU cao nhất có thể dùng khi chuyển vùng
D. Số lần failover được cho phép trong một ca trực
Đáp án đúng: B

7. RTO 15 phút và RPO 2 phút đòi hỏi kiểm chứng gì?
A. Phục hồi ≤15 phút, mất dữ liệu không quá 2 phút
B. Khôi phục dữ liệu trong 15 phút, khởi động dưới 2 phút
C. Mọi replica phải nhận bản ghi sau đúng 15 phút
D. Hệ thống chỉ cần báo lỗi trong tối đa 2 phút
Đáp án đúng: A

8. Khi chạy fault injection vào một dependency, bước kiểm soát nào cần có?
A. Ngắt toàn bộ vùng sản xuất mà không thông báo
B. Bỏ mọi cảnh báo để tránh làm sai số liệu thử
C. Khoanh vùng ảnh hưởng và chuẩn bị dừng thử
D. Thay dữ liệu thật bằng dữ liệu trống vĩnh viễn
Đáp án đúng: C

9. Khái niệm steady state trong chaos experiment thường là gì?
A. Lúc mọi máy chủ có mức tiêu thụ RAM bằng nhau
B. Trạng thái SLI ổn định trước lúc gây lỗi thử
C. Lúc mọi request trong hệ thống có cùng độ trễ
D. Lúc môi trường đã ngắt toàn bộ nguồn phụ thuộc
Đáp án đúng: B

10. Khi inject timeout vào API phụ thuộc, cần quan sát gì ở dịch vụ gọi?
A. Chỉ số lượng JAR có sẵn trong thư mục build
B. Chỉ độ dài tên endpoint của dịch vụ phụ thuộc
C. Chỉ số lần Java compiler chạy trong pipeline
D. Tỷ lệ lỗi, timeout, fallback và queue chờ
Đáp án đúng: D

11. Circuit breaker bảo vệ dịch vụ khi dependency lỗi liên tục bằng cách nào?
A. Tăng số request trực tiếp để dò dependency hồi phục
B. Ngừng gọi tạm thời khi lỗi vượt ngưỡng cho phép
C. Xóa tất cả cache của hệ thống khi nhận lỗi
D. Tự động nâng version thư viện mỗi lần kết nối lỗi
Đáp án đúng: B

12. Retry với exponential backoff và jitter giải quyết rủi ro nào?
A. Buộc mọi retry chạy ngay đồng thời khi gặp timeout
B. Chuyển tất cả thao tác ghi thành đọc không đồng bộ
C. Bảo đảm dependency luôn trả lời trước deadline
D. Giảm các đợt retry đồng loạt khi dịch vụ vừa hồi
Đáp án đúng: D

13. Vì sao kiểm thử retry của lệnh thanh toán cần chú ý idempotency?
A. Retry chỉ làm giảm số request đến máy chủ phía sau
B. Retry tự động bảo đảm mọi response luôn giống hệt
C. Tránh ghi lặp nếu cùng request được gửi lại
D. Retry chỉ áp dụng được khi gọi API kiểu GET
Đáp án đúng: C

14. Khi primary database bị ngắt và replica tiếp quản, cần xác minh gì?
A. Khả năng đọc ghi và tính nhất quán sau failover
B. Chỉ thời gian tải trang dashboard sau khi đăng nhập
C. Chỉ dung lượng file cấu hình ở máy primary cũ
D. Chỉ tổng số request test gửi trước khi gây lỗi
Đáp án đúng: A

15. Để kiểm chứng khôi phục dữ liệu, chỉ kiểm tra backup tạo thành công có đủ không?
A. Có; file backup tồn tại luôn bảo đảm dữ liệu đúng
B. Có; metadata của backup thay thế được phép restore
C. Không; cần thử restore và đối chiếu điểm dữ liệu
D. Không; chỉ cần đếm số lượng log lỗi mỗi ngày
Đáp án đúng: C

16. Kịch bản mất node giữa lúc xử lý message cần đo nguy cơ nào?
A. Chỉ khả năng đổi màu giao diện khi chuyển node
B. Mất, lặp message và trạng thái sau xử lý lại
C. Chỉ số lượng test class được compiler tìm thấy
D. Chỉ độ dài file log ghi trước khi node ngừng
Đáp án đúng: B

17. Soak test kéo dài với tải đều giúp phát hiện hiện tượng nào?
A. Chỉ lỗi parse JSON ngay tại request đầu tiên
B. Chỉ thay đổi định dạng thời gian trong file test
C. Chỉ số commit tăng ở kho mã nguồn của dự án
D. Rò rỉ tài nguyên hoặc suy giảm qua nhiều giờ
Đáp án đúng: D

18. Hàng đợi tăng mãi khi worker phía sau chậm thường cho thấy gì?
A. Tốc độ xử lý thấp hơn tốc độ message đến
B. Cơ chế backup đang sao chép dữ liệu nhanh hơn
C. Cache luôn đạt hit ratio 100% ở mọi request
D. Bộ cân bằng tải đã tự nhân đôi số worker
Đáp án đúng: A

19. Khi mô phỏng network partition giữa các node, cần quan sát gì?
A. Chỉ danh sách dependency của các module Maven
B. Chỉ timestamp khi ứng dụng được biên dịch xong
C. Chỉ mức sử dụng bộ nhớ của máy sinh tải ảo
D. Quy tắc đọc ghi khi các node mất liên lạc
Đáp án đúng: D

20. Để đánh giá failover đa vùng, yếu tố nào quan trọng?
A. Số biểu tượng hiển thị trên trang giám sát sự cố
B. Số branch Git đang mở trong khoảng thời gian thử
C. Thứ tự đóng gói artifact trên máy phát triển
D. Chuyển traffic và nhất quán dữ liệu sau failover
Đáp án đúng: D

21. Tại sao cần lưu timeline khi thực hiện diễn tập sự cố?
A. Đối chiếu mốc phát hiện, chuyển vùng và phục hồi
B. Chỉ đo số thành viên có quyền truy cập server
C. Chỉ kiểm tra mức độ dễ đọc của tài liệu hướng dẫn
D. Chỉ đếm các plugin đang được cài trong Jenkins
Đáp án đúng: A

22. Sau khi lỗi dependency kết thúc, kiểm chứng recovery nên theo dõi gì?
A. Chỉ thấy pod ở trạng thái Running là đủ
B. Chỉ giảm thời gian triển khai artifact trong CI
C. Tỷ lệ lỗi về ngưỡng và backlog được xử lý hết
D. Chỉ tăng số lượng request gửi từ công cụ tạo tải
Đáp án đúng: C

23. Trong fault injection, vì sao cần đặt guardrail tự động?
A. Dừng thử khi SLI vượt giới hạn an toàn
B. Cho phép thử luôn mở rộng tác động sang toàn vùng
C. Thay mọi cảnh báo thật bằng giá trị mặc định
D. Tắt tính năng ghi log trong lúc dịch vụ đang lỗi
Đáp án đúng: A

24. Một reliability test có đủ bằng chứng trước khi release khi nào?
A. Chỉ cần mô tả kịch bản mà chưa chạy thử nghiệm
B. Chỉ cần có file backup tạo từ tuần trước đó
C. Có SLI, kết quả phục hồi và đối chiếu RTO/RPO
D. Chỉ cần số request kiểm thử lớn hơn tuần trước
Đáp án đúng: C
