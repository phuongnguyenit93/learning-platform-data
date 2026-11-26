Câu 1. Khi quy trình đặt hàng đi qua ba dịch vụ có cơ sở dữ liệu riêng, Saga duy trì giao dịch nghiệp vụ bằng cách nào?
A. Giữ một khóa database chung cho cả ba dịch vụ
B. Commit tất cả bằng một lệnh SQL từ dịch vụ đầu
C. Dùng giao dịch cục bộ kèm bước bù khi lỗi
D. Chuyển mọi ghi dữ liệu sang một transaction toàn cục
Đáp án đúng: C

Câu 2. Đặt hàng đã giữ tồn kho nhưng bước thanh toán bị từ chối; thao tác bù phù hợp là gì?
A. Giải phóng lượng hàng đã giữ theo đơn
B. Xóa trực tiếp dữ liệu của dịch vụ thanh toán
C. Chạy lại thao tác trừ tiền đến khi thành công
D. Đánh dấu đơn hoàn tất dù chưa thanh toán
Đáp án đúng: A

Câu 3. Choreography Saga khác orchestration ở đặc điểm phối hợp nào?
A. Mọi dịch vụ cùng chờ một database coordinator
B. Các bước đều bắt buộc chạy trên một tiến trình
C. Một scheduler chung gọi từng câu SQL nội bộ
D. Dịch vụ theo sự kiện, không cần bộ điều phối trung tâm
Đáp án đúng: D

Câu 4. Trong Saga orchestration, thành phần nào thường quyết định bước tiếp theo sau phản hồi của dịch vụ?
A. Orchestrator lưu tiến trình và chọn lệnh tiếp
B. Message broker tự quyết định quy tắc thanh toán
C. Database của bước cuối quyết định mọi bước trước
D. Gateway HTTP chỉ kiểm tra kiểu dữ liệu đầu vào
Đáp án đúng: A

Câu 5. Saga có thể bảo đảm điều gì khi từng dịch vụ đã commit giao dịch cục bộ?
A. Rollback SQL xuyên mọi database ngay khi có lỗi
B. Phục hồi nghiệp vụ qua các bước bù phù hợp
C. Đọc nhất quán tức thời mọi dịch vụ ở mọi lúc
D. Không còn cần theo dõi trạng thái tiến trình
Đáp án đúng: B

Câu 6. Vì sao bù trừ nghiệp vụ không phải lúc nào cũng là đảo ngược tuyệt đối?
A. Hành động bù bắt buộc dùng cùng câu SQL trước đó
B. Mọi thao tác cục bộ đều là phép toán giao hoán
C. Tác động bên ngoài có thể không thể đảo ngược
D. Thông điệp bù luôn được phát trước giao dịch chính
Đáp án đúng: C

Câu 7. Client gửi lại lệnh xác nhận đơn do timeout; xử lý nào giúp tránh tạo hai Saga?
A. Luôn tạo Saga mới rồi để consumer tự phát hiện
B. Nhận diện cùng request bằng khóa idempotency
C. Bỏ hết mọi request sau lần đầu trong một giờ
D. Đổi requestId ở mỗi retry để dễ theo dõi
Đáp án đúng: B

Câu 8. Một worker nhận lại thông điệp ReserveStock vì broker phát lặp; handler nên làm gì?
A. Trừ tồn kho thêm một lần để bảo đảm đủ số lượng
B. Đánh dấu mọi đơn đã hoàn thành ngay khi nhận
C. Xóa thông điệp trước khi ghi bất cứ kết quả nào
D. Dùng mã thao tác để không giữ hàng lần nữa
Đáp án đúng: D

Câu 9. Khi gọi dịch vụ vận chuyển bị timeout, điều gì phải được xem xét trước khi bù?
A. Lệnh có thể đã thực thi dù phản hồi bị mất
B. Timeout luôn chứng minh lệnh chưa được gửi
C. Bên vận chuyển chắc chắn rollback toàn bộ dữ liệu
D. Saga phải lặp lệnh liên tục mà không truy vấn trạng thái
Đáp án đúng: A

Câu 10. Một bước Saga thất bại vì lỗi mạng tạm thời, lựa chọn retry nào phù hợp?
A. Retry vô hạn và không cần ghi nhận số lần thử
B. Retry giới hạn với backoff và tính idempotent
C. Không retry bất kỳ lỗi nào kể cả kết nối gián đoạn
D. Luôn bù ngay sau lần thử đầu tiên thất bại
Đáp án đúng: B

Câu 11. Hệ thống cần theo dõi Saga đang chờ xác nhận hoàn tiền; thông tin nào cần lưu bền vững?
A. Chỉ tên thread xử lý yêu cầu lúc khởi tạo
B. Chỉ response HTTP cuối từ API của người dùng
C. Saga ID, bước hiện tại và trạng thái chờ
D. Chỉ timestamp của lần deploy gần nhất
Đáp án đúng: C

Câu 12. Nếu hành động bù ReleaseStock cũng lỗi tạm thời, phương án phục hồi nào hợp lý?
A. Đánh dấu bù thành công dù không nhận xác nhận
B. Lưu bước bù chưa xong để retry hoặc xử lý tay
C. Xóa mọi bản ghi giao dịch trước khi bù xong
D. Bỏ qua bước bù và xác nhận đơn đã hoàn thành
Đáp án đúng: B

Câu 13. Dịch vụ phát event sau commit, nhưng tiến trình chết trước lúc publish; rủi ro Saga nào xảy ra?
A. Tất cả dịch vụ tự rollback giao dịch đã commit
B. Broker chắc chắn nhận event ngay trước transaction
C. Không thể xảy ra vì publish thuộc cùng database
D. Dữ liệu đã đổi nhưng bước sau không được gọi
Đáp án đúng: D

Câu 14. Kết hợp Transactional Outbox với Saga chủ yếu giải quyết vấn đề gì ở một bước cục bộ?
A. Ghi nghiệp vụ và outbox trong một transaction
B. Biến mọi consumer thành hệ thống xử lý đúng một lần
C. Thực hiện khóa ghi đồng bộ xuyên các database dịch vụ
D. Loại bỏ hoàn toàn nhu cầu retry ở message relay
Đáp án đúng: A

Câu 15. Trong Saga có bước gửi email xác nhận không thể thu hồi, thiết kế nào hạn chế tác động khi phải bù?
A. Cho gửi email ngay ở bước đầu để giảm latency
B. Dùng email thay cho mọi giao dịch bù trừ
C. Đánh dấu đơn hoàn tất trước khi giữ tồn kho
D. Để hành động khó bù sau các bước có thể bù
Đáp án đúng: D

Câu 16. Một người dùng hủy đơn khi Saga thanh toán đang xử lý; thiết kế cần làm rõ điều gì?
A. Chỉ cần đặt timeout mạng ngắn hơn ở mọi API
B. Cho cả hai luồng tự cập nhật trạng thái không kiểm soát
C. Quy tắc trạng thái ngăn hủy và hoàn tất đồng thời
D. Thay việc ghi trạng thái bằng gửi email bất đồng bộ
Đáp án đúng: C

Câu 17. Vì sao Saga thường tạo ra khoảng thời gian dữ liệu chưa nhất quán giữa các dịch vụ?
A. Vì từng dịch vụ không được dùng khóa chính riêng
B. Vì transaction cục bộ hoàn tất khác thời điểm
C. Vì broker bắt buộc thay đổi schema thông điệp khi gửi
D. Vì mọi bước Saga phải được chạy song song
Đáp án đúng: B

Câu 18. Khi UI hiển thị đơn đang ở trạng thái Pending, diễn giải nào đúng với Saga?
A. Có bước đang xử lý, chưa có kết quả cuối
B. Toàn bộ database đã được đồng bộ và xác nhận
C. Chắc chắn cần hoàn tiền vì tất cả bước đã thất bại
D. Không thể truy vấn trạng thái khi đang chạy Saga
Đáp án đúng: A

Câu 19. Để theo dõi nguyên nhân một Saga dừng ở bước thanh toán, telemetry nào hữu ích nhất?
A. Chỉ bộ đếm số request toàn hệ thống theo ngày
B. Chỉ nội dung log khởi động của message broker
C. Saga ID xuyên log, sự kiện và bước xử lý
D. Chỉ lượng bộ nhớ heap ở dịch vụ khởi tạo Saga
Đáp án đúng: C

Câu 20. Trong choreography, thêm nhiều dịch vụ đăng ký cùng sự kiện có thể gây đánh đổi gì?
A. Luồng sự kiện phân tán trở nên khó theo dõi
B. Mọi subscriber tự động có chung transaction ACID
C. Một subscriber lỗi sẽ rollback transaction của tất cả
D. Sự kiện không thể dùng lại giữa hai bounded context
Đáp án đúng: A

Câu 21. Trong orchestration, nhược điểm thiết kế nào cần quản trị ở orchestrator?
A. Không thể kiểm tra trạng thái một Saga bất kỳ
B. Không thể tách logic nghiệp vụ thành các dịch vụ
C. Mọi bước phải chia sẻ cùng một bảng dữ liệu
D. Bộ điều phối dễ thành điểm tập trung phức tạp
Đáp án đúng: D

Câu 22. Với thao tác thanh toán có khả năng retry, hợp đồng dịch vụ nên bao gồm gì?
A. Mỗi request phải tự sinh một mã giao dịch mới
B. Mã idempotency ổn định và cách tra cứu kết quả
C. Chỉ status code mà không cần danh tính thao tác
D. Yêu cầu client luôn gửi yêu cầu qua cùng một host
Đáp án đúng: B

Câu 23. Một Saga phải bù hai bước đã thành công A rồi B. Thứ tự bù nào thường cần xem xét trước?
A. Bù A rồi commit B thêm một lần cho an toàn
B. Bù mọi bước song song bất kể phụ thuộc dữ liệu
C. Bù B rồi A theo hướng đảo phụ thuộc nghiệp vụ
D. Xóa trạng thái Saga trước khi phát lệnh bù
Đáp án đúng: C

Câu 24. Làm sao xác minh một Saga đã hoàn tất thực sự thay vì chỉ gửi xong lệnh cuối?
A. Chỉ xem orchestrator đã phát đủ số thông điệp
B. Chỉ kiểm tra hàng đợi message đang rỗng
C. Chỉ chờ một khoảng thời gian cố định trên CI
D. Kiểm tra xác nhận bước cuối và trạng thái Saga
Đáp án đúng: D
