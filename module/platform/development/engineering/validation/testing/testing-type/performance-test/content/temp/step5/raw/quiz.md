1. Trong báo cáo độ trễ HTTP, p95 = 320 ms được hiểu thế nào?
A. 95% request có độ trễ lớn hơn mức 320 ms
B. Độ trễ trung bình của mọi request là 320 ms
C. Chỉ 5% request trả về thành công trong 320 ms
D. 95% request có độ trễ không vượt quá 320 ms
Đáp án đúng: D

2. Vì sao cần báo cáo cả p99 bên cạnh độ trễ trung bình?
A. p99 luôn bằng độ trễ trung bình khi tải ổn định
B. p99 giúp nhận diện phần đuôi request rất chậm
C. p99 thể hiện số request được xử lý mỗi giây
D. p99 chỉ phản ánh số lỗi mạng khi chạy kiểm thử
Đáp án đúng: B

3. Đơn vị nào phù hợp để biểu diễn thông lượng của API?
A. Số kết nối đồng thời tồn tại trong một thời điểm
B. Độ trễ lớn nhất ghi được trong một lần kiểm thử
C. Phần trăm bộ nhớ heap còn trống của dịch vụ
D. Số request hoàn tất mỗi giây trong thời gian đo
Đáp án đúng: D

4. Mục tiêu chính của load test với tải dự kiến là gì?
A. Đánh giá đáp ứng hệ thống ở mức tải vận hành
B. Tăng tải mãi đến khi tìm điểm hệ thống sụp
C. Duy trì tải nhiều ngày để dò rò rỉ tài nguyên
D. Ngắt một dependency để kiểm tra khả năng failover
Đáp án đúng: A

5. Trong stress test, điều gì cần quan sát khi tải vượt thiết kế?
A. Chỉ độ trễ ở một request khi hệ thống rảnh
B. Điểm bão hòa và cách hồi phục khi hạ tải
C. Chỉ kích thước file kết quả của trình tải ảo
D. Thời gian biên dịch source trước khi chạy test
Đáp án đúng: B

6. Soak test dùng để phát hiện loại vấn đề nào hiệu quả?
A. Rò rỉ bộ nhớ hay suy giảm khi tải kéo dài
B. Chỉ xung đột version dependency lúc startup
C. Chỉ lỗi hiển thị khi đổi kích thước trình duyệt
D. Số endpoint chưa khai báo trong tài liệu API
Đáp án đúng: A

7. Kịch bản spike test mô phỏng điều kiện nào?
A. Số user tăng đều trong cả ngày mà không giảm
B. Tốc độ gửi request luôn giữ một hằng số nhỏ
C. Lượng request tăng đột ngột rồi quay về nền
D. Chạy từng request riêng lẻ không có đồng thời
Đáp án đúng: C

8. Trong mô hình tải open, arrival rate được kiểm soát ra sao?
A. Cấp lượt đến theo tốc độ, không chờ phản hồi
B. Mỗi user chỉ gửi lượt mới khi lượt trước đã xong
C. Số request mới luôn bằng số thread xử lý sẵn
D. Lượt đến dừng ngay khi mọi phản hồi hơi chậm
Đáp án đúng: A

9. Vì sao số virtual user không đồng nghĩa trực tiếp với RPS?
A. Tốc độ phụ thuộc thời gian phản hồi và think time
B. Mỗi virtual user luôn gửi chính xác một RPS cố định
C. Virtual user chỉ tạo kết nối mà không gửi request
D. RPS chỉ do số CPU của máy chạy ứng dụng quyết định
Đáp án đúng: A

10. Warm-up trước khi đo Java service nhằm giảm sai lệch nào?
A. Ảnh hưởng duy nhất của phiên bản công cụ JMeter
B. Thay đổi kết quả do ngẫu nhiên tên endpoint API
C. Ảnh hưởng khởi tạo JIT, pool kết nối và cache
D. Chênh lệch định dạng log giữa các lần đóng gói
Đáp án đúng: C

11. Trong JMeter, Thread Group thường cấu hình thành phần nào?
A. Số byte tối đa của kết quả trả về từ dịch vụ
B. Số user ảo, thời gian ramp-up và số vòng lặp
C. Chỉ thứ tự xuất bản các artifact của ứng dụng
D. Chỉ luật eviction cho cache dữ liệu phía server
Đáp án đúng: B

12. Khi script tải HTTP có nhiều response 500, cần xử lý kết quả ra sao?
A. Chỉ ghi nhận request nhanh nên bỏ toàn bộ lỗi
B. Coi mọi phản hồi HTTP là thành công vì có status
C. Tăng timeout để mọi request tự được xem hợp lệ
D. Đếm lỗi HTTP, không coi phản hồi 500 là thành công
Đáp án đúng: D

13. Trong k6, `vus` biểu diễn khái niệm nào?
A. Số virtual user thực thi kịch bản tải
B. Số HTTP response thành công tính theo mỗi phút
C. Số máy chủ đích tham gia vào mạng cân bằng tải
D. Số lần Java garbage collector thu hồi object
Đáp án đúng: A

14. Threshold trong k6 phù hợp để kiểm tra điều gì?
A. Tự sửa code ứng dụng nếu độ trễ vượt ngưỡng
B. Sinh cấu hình Redis để loại bỏ bottleneck mạng
C. Bộ chỉ số có đáp ứng tiêu chí pass/fail đã đặt
D. Đổi build tool tự động khi lỗi HTTP vượt giới hạn
Đáp án đúng: C

15. Executor `constant-arrival-rate` của k6 kiểm soát gì?
A. Số VU cố định chờ xong lượt trước rồi mới lặp
B. Số response nhận được từ từng máy backend
C. Số iteration khởi tạo theo tốc độ xác định
D. Tổng dung lượng heap sử dụng bởi load generator
Đáp án đúng: C

16. Trong Gatling, kịch bản người dùng được mô hình hóa qua gì?
A. Chỉ một danh sách JAR cần đưa lên test server
B. Chỉ các rule Checkstyle dùng kiểm tra mã nguồn
C. Chỉ những thread hệ điều hành cần bị giám sát
D. Scenario, các bước request và injection tải
Đáp án đúng: D

17. Vì sao cần correlation token trong script JMeter hoặc Gatling?
A. Để buộc mọi user chia sẻ chung một session token
B. Để chặn mọi lần refresh access token hợp lệ
C. Để làm tăng đồng thời mà không gửi thêm request
D. Để lấy giá trị phiên động từ phản hồi trước đó
Đáp án đúng: D

18. Thêm think time phù hợp trong luồng thao tác giúp gì?
A. Tạo thêm độ trễ trên server trước khi chạy SQL
B. Phản ánh khoảng dừng thực tế giữa các thao tác
C. Bỏ qua bước đăng nhập để giảm chi phí xác thực
D. Giữ tất cả kết nối mạng hoạt động vô thời hạn
Đáp án đúng: B

19. Để so hai bản release, điều kiện chạy test nào nên nhất quán?
A. Cùng mô hình tải, dữ liệu thử và môi trường đo
B. Chỉ cùng tên file report nhưng dùng tải khác nhau
C. Chỉ cùng số lượng commit giữa hai bản release
D. Chỉ cùng người chạy, không cần giữ môi trường
Đáp án đúng: A

20. Theo định luật Little ở trạng thái ổn định, quan hệ nào đúng?
A. Throughput bằng số thread chia cho lượng bộ nhớ
B. p99 luôn bằng số kết nối chia cho tần suất lỗi
C. Số request đồng thời luôn bằng số core vật lý
D. Số request trong hệ ≈ throughput × thời gian ở hệ
Đáp án đúng: D

21. CPU gần 100% và hàng chờ tăng theo tải gợi ý điều gì?
A. Bộ nhớ cache nhất định đang tăng hit ratio
B. Độ trễ mạng nhất định đã giảm về gần bằng 0
C. Hệ có thể đã bão hòa năng lực xử lý CPU
D. Ứng dụng chắc chắn gặp deadlock ở mọi thread
Đáp án đúng: C

22. JFR trên JVM hỗ trợ phân tích hiện tượng nào?
A. Chỉ version artifact sẽ được publish lên kho
B. Chỉ số request ảo đã được JMeter phát sinh
C. Xem CPU, allocation và sự kiện GC lúc chạy
D. Chỉ việc đúng sai của khai báo JSON Schema
Đáp án đúng: C

23. Khi p99 tăng cùng thời gian chờ connection pool, nên kiểm tra gì?
A. Chỉ tăng số lượng VU mà bỏ qua timeout DB
B. Pool, thời gian giữ kết nối và truy vấn chậm
C. Chỉ thay màu biểu đồ latency trên dashboard
D. Chỉ đặt lại tên project trong báo cáo performance
Đáp án đúng: B

24. Khi đưa performance gate vào CI, phương án nào hợp lý?
A. Chỉ so số lượng dòng log ở hai bản release
B. So cùng tải với ngưỡng p95, lỗi và tài nguyên
C. Chỉ kiểm tra task package chạy mà không đo API
D. Chỉ đo một request khi không có người dùng khác
Đáp án đúng: B
