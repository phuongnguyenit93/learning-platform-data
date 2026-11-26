1. Khi chia một hệ thống thành microservices, tiêu chí ranh giới nào đáng ưu tiên?
A. Năng lực nghiệp vụ có quy tắc và vòng đời riêng
B. Mỗi bảng quan hệ cần một dịch vụ độc lập riêng
C. Mỗi REST endpoint được triển khai như một dịch vụ
D. Mỗi class Java được tách ra một container riêng
Đáp án đúng: A

2. Ý nghĩa của triển khai độc lập giữa các microservice là gì?
A. Mọi dịch vụ phải nâng version đồng thời trong mỗi lần sửa
B. Mọi dịch vụ dùng chung cùng một pipeline triển khai duy nhất
C. Không dịch vụ nào được gọi API của dịch vụ khác
D. Sửa một dịch vụ không buộc phát hành các dịch vụ khác
Đáp án đúng: D

3. Đối với dữ liệu nghiệp vụ của mỗi microservice, nguyên tắc nào phù hợp?
A. Mọi dịch vụ có thể cập nhật bảng của nhau theo nhu cầu
B. Một dịch vụ quản lý toàn bộ schema của các miền khác
C. Mọi consumer được tự quyết định schema của producer
D. Sở hữu dữ liệu và kiểm soát quyền ghi theo miền
Đáp án đúng: D

4. Vì sao truy cập trực tiếp database của service khác là rủi ro?
A. Gắn kết hai dịch vụ với schema nội bộ của nhau
B. Giúp bỏ qua API nên mọi lần ghi đều được xác thực
C. Bảo đảm mọi thay đổi schema đều tương thích ngược
D. Tăng tính độc lập triển khai nhờ dùng khóa ngoại
Đáp án đúng: A

5. Khi thay đổi response API, điều kiện nào giúp bảo vệ consumer cũ?
A. Giữ tương thích hoặc quản lý phiên bản API
B. Chỉ tăng số field mà bỏ mọi kiểm tra hợp đồng
C. Đổi ý nghĩa field cũ mà vẫn giữ nguyên tên và type
D. Cho mọi consumer đọc trực tiếp bảng dữ liệu nguồn
Đáp án đúng: A

6. Với gọi HTTP đồng bộ giữa hai dịch vụ, biện pháp nào cần có?
A. Luôn chờ vô hạn để tránh bỏ mất response thành công
B. Tự retry vô hạn với tất cả thao tác ghi nhạy cảm
C. Bỏ kiểm tra status lỗi để tăng số request hoàn tất
D. Đặt timeout, deadline và xử lý khi phụ thuộc lỗi
Đáp án đúng: D

7. Một API gọi đồng bộ liên tiếp nhiều dịch vụ có thể chịu rủi ro nào?
A. Mọi dịch vụ tự đồng bộ dữ liệu theo một transaction
B. Mọi API con luôn trả về nhanh hơn API gốc
C. Độ trễ cộng dồn và một phụ thuộc chậm kéo theo
D. Sự cố một service không thể ảnh hưởng request
Đáp án đúng: C

8. Khi nào messaging bất đồng bộ đặc biệt phù hợp?
A. Một thao tác buộc trả kết quả xác nhận tức thời
B. Tách nhịp tải khi không cần phản hồi ngay
C. Lệnh phải được commit cùng transaction ở mọi DB
D. Người dùng cần thấy trạng thái mới nhất ngay lập tức
Đáp án đúng: B

9. Sau khi cập nhật dữ liệu qua event, read model có thể cũ tạm thời. Điều gì đúng?
A. Cần quản lý eventual consistency và thông báo phù hợp
B. Lệnh ghi chắc chắn chưa được commit nếu read model cũ
C. Mọi client phải retry ghi cho tới khi query thay đổi
D. Broker sẽ tự rollback thay đổi nếu consumer xử lý trễ
Đáp án đúng: A

10. Trong mô hình vừa ghi DB vừa publish message, lỗi dual-write xảy ra khi nào?
A. Consumer xử lý một message thành công đúng một lần
B. Cả DB và broker cùng rollback theo một transaction
C. Dữ liệu đã commit nhưng message không được công bố
D. Mọi event mới đều được query đọc ngay lập tức
Đáp án đúng: C

11. Transactional outbox hỗ trợ độ tin cậy bằng cách nào?
A. Publish vào broker trước rồi mới cập nhật DB bất kỳ
B. Lưu dữ liệu nghiệp vụ và outbox chung transaction
C. Bắt consumer đồng bộ hoàn tất trước khi commit DB
D. Ghi event trực tiếp vào database của các consumer
Đáp án đúng: B

12. Saga có giá trị khi phối hợp giao dịch giữa nhiều dịch vụ vì sao?
A. Tạo một giao dịch ACID chung cho mọi database độc lập
B. Bảo đảm mọi bước luôn thành công mà không có retry
C. Thay thế toàn bộ kiểm tra quy tắc nghiệp vụ tại service
D. Local transaction phối hợp với bước bù khi lỗi
Đáp án đúng: D

13. Trong Saga, một bước bù được hiểu đúng như thế nào?
A. Rollback trực tiếp tất cả DB từng commit của quy trình
B. Một hành động nghiệp vụ khắc phục bước đã hoàn tất
C. Xóa toàn bộ message trên broker để hủy lịch sử
D. Ghi đè dữ liệu của dịch vụ khác bằng SQL từ client
Đáp án đúng: B

14. Tại sao idempotency quan trọng khi retry command tạo thanh toán?
A. Mọi retry phải tạo một mã giao dịch mới cho an toàn
B. Mỗi retry phải gọi một instance khác để tránh lỗi
C. Gửi lại cùng yêu cầu không làm thu tiền nhiều lần
D. Tăng timeout là đủ để bảo đảm không tạo thanh toán lặp
Đáp án đúng: C

15. Với cơ chế giao message at-least-once, consumer cần chuẩn bị gì?
A. Khả năng gặp event trùng và xử lý an toàn khi lặp
B. Bảo đảm mọi message chỉ được gửi đúng một lần duy nhất
C. Giả định mọi message đến theo thứ tự tuyệt đối toàn broker
D. Giả định broker đã giao thì không thể bị mất kết nối
Đáp án đúng: A

16. Circuit breaker thường bảo vệ dịch vụ gọi như thế nào?
A. Tạm ngừng gọi dependency lỗi nhiều để tránh quá tải
B. Tăng số request vào dependency để thử hồi nhanh hơn
C. Cho mọi request vượt qua timeout khi backend đã chậm
D. Buộc mọi lỗi chuyển thành response thành công 200
Đáp án đúng: A

17. Mẫu bulkhead hạn chế sự cố lan truyền bằng cách nào?
A. Cho mọi request chia sẻ một pool không giới hạn
B. Cho các service dùng chung một transaction khổng lồ
C. Loại bỏ mọi giới hạn đồng thời của tiến trình gọi
D. Cách ly pool hoặc tài nguyên của từng nhóm công việc
Đáp án đúng: D

18. Service discovery giải quyết nhu cầu nào khi instance thay đổi?
A. Tự đồng bộ toàn bộ dữ liệu của các database độc lập
B. Thay thế API contract bằng kết nối SQL trực tiếp
C. Bảo đảm thông điệp được xử lý theo đúng một thứ tự
D. Tìm địa chỉ các instance đang phục vụ
Đáp án đúng: D

19. API gateway trong microservices có thể đảm nhiệm vai trò nào?
A. Nắm mọi invariant nghiệp vụ của toàn bộ hệ thống
B. Ghi trực tiếp vào mọi database của các service
C. Định tuyến và kiểm soát truy cập chung ở lớp rìa
D. Đảm nhiệm mọi local transaction trong quy trình Saga
Đáp án đúng: C

20. Muốn chẩn đoán một request qua nhiều dịch vụ, tín hiệu nào quan trọng?
A. Chỉ số lượng dòng code trên từng module nguồn
B. Trace ID nối span và lỗi trong luồng gọi
C. Chỉ danh sách thư viện có trong Docker image
D. Chỉ số lần cập nhật version ở mỗi service
Đáp án đúng: B

21. Consumer-driven contract test giúp xác nhận điều gì?
A. Consumer có thể bỏ qua mọi version của response mới
B. Provider còn đáp ứng các tương tác consumer cần
C. API đang chạy nhanh hơn mức p95 đã được đặt
D. Mọi database đã tự động chia sẻ schema giống nhau
Đáp án đúng: B

22. Trong kiểm thử chịu lỗi phân tán, kịch bản nào hữu ích?
A. Chỉ kiểm thử từng hàm thuần bằng một dữ liệu nhỏ
B. Chỉ kiểm tra formatter và package của từng module
C. Cho dependency timeout có kiểm soát và đo khôi phục
D. Chỉ đếm số nhãn endpoint trên tài liệu API
Đáp án đúng: C

23. Phát hành canary cho một microservice nên được đánh giá bằng gì?
A. Đưa ngay toàn bộ request vào bản mới để rút ngắn test
B. Chỉ xác nhận container mới bắt đầu là phát hành thành công
C. Tăng dần lưu lượng dựa trên lỗi và độ trễ quan sát
D. Giữ hai phiên bản cùng ghi chung một DB không kiểm chứng
Đáp án đúng: C

24. Khi nào lợi ích microservices có thể không đáng chi phí?
A. Khi có nhiều nhóm cần triển khai theo lịch độc lập
B. Khi nhu cầu triển khai độc lập chưa bù chi phí phân tán
C. Khi miền có ranh giới rõ và mỗi nhóm sở hữu dữ liệu
D. Khi nhiều phần cần mở rộng ở mức tải khác nhau
Đáp án đúng: B
