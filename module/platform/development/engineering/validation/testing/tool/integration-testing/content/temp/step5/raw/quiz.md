Một test gọi HTTP vào controller rồi kiểm tra database nhằm xác minh điều gì?
A. Chỉ cú pháp annotation controller được khai báo đúng
B. Chỉ thứ tự lời gọi trong một mock service nội bộ
C. Luồng HTTP, service và DB được kiểm chứng cùng nhau
D. Luôn chứng minh ứng dụng chịu tải cao khi nhiều user
Đáp án đúng: C

Muốn kiểm thử nhiều bean Spring phối hợp trong ngữ cảnh ứng dụng, chọn hướng nào?
A. Chỉ kiểm tra JSON schema mà không khởi tạo bean
B. Nạp nhiều bean thật bằng @SpringBootTest
C. Chỉ mở connection JDBC bỏ qua cấu hình Spring
D. Chỉ tạo controller bằng new và tự thay mọi service
Đáp án đúng: B

Testcontainers hỗ trợ bài tích hợp với PostgreSQL bằng cách nào?
A. Tạo mock repository để bỏ qua mọi ràng buộc SQL
B. Thay mọi truy vấn SQL bằng dữ liệu giả trong List
C. Đọc dữ liệu trực tiếp từ database production chung
D. Chạy DB container tạm theo cấu hình của bài test
Đáp án đúng: D

Spring TestContext tái sử dụng application context, test cần chú ý điều gì?
A. Mọi bean đều được tạo mới sau từng lời gọi assertion
B. Tất cả transaction của HTTP server đều tự rollback
C. Tất cả mock mặc định chỉ có thể dùng trong một test
D. State dùng chung có thể rò giữa những bài test
Đáp án đúng: D

Để chỉ kiểm tra binding, validation và phản hồi HTTP của MVC, lựa chọn nào phù hợp?
A. Sử dụng @WebMvcTest cho phần MVC và cô lập service
B. Dùng @DataJpaTest để kiểm tra định tuyến HTTP
C. Chỉ dùng Mockito trên repository thay vì MVC context
D. Chạy toàn bộ broker thật trong mọi bài controller test
Đáp án đúng: A

Tại sao @Transactional ở test không bảo đảm rollback dữ liệu từ HTTP request thật?
A. Các bảng quan hệ không có khả năng rollback
B. Annotation này luôn commit mọi thay đổi sau test
C. Request có thể dùng thread và transaction khác
D. Spring tự vô hiệu mọi transaction trong servlet
Đáp án đúng: C

Bài test broker nhận sự kiện bất đồng bộ nên đợi kết quả theo cách nào?
A. Ngủ cố định vài giây rồi coi consumer đã thành công
B. Chờ side effect xuất hiện trong thời hạn xác định
C. Chỉ xác nhận producer gọi send mà không có lỗi
D. Dừng consumer trước khi gửi để dữ liệu ổn định
Đáp án đúng: B

Muốn phát hiện sai khác schema giữa CI và ứng dụng thật, nên chuẩn bị DB thế nào?
A. Áp migration rồi kiểm tra SQL với schema thật
B. Dùng một H2 schema tùy ý thay database mục tiêu
C. Bỏ kiểm thử index và constraint của schema chính
D. Để DB tự tạo bảng từ dữ liệu mẫu ngẫu nhiên
Đáp án đúng: A

Dịch vụ ngoài không ổn định, bài integration test lặp lại ở CI nên xử lý thế nào?
A. Bỏ kiểm tra trạng thái lỗi vì phản hồi có thể thay đổi
B. Luôn gọi endpoint production và tự động bỏ qua mọi lỗi
C. Thay toàn bộ lời gọi HTTP bằng đối tượng null tĩnh
D. Dùng stub theo contract, kiểm tra API thật riêng
Đáp án đúng: D

Khi broker có thể giao cùng message nhiều lần, tích hợp consumer cần kiểm tra gì?
A. Xử lý trùng không gây thêm tác dụng nghiệp vụ sai
B. Producer luôn gửi đúng một lần trong vòng đời hệ thống
C. Mọi message phải dùng một kết nối JDBC duy nhất
D. Broker luôn rollback dữ liệu DB khi consumer xử lý lỗi
Đáp án đúng: A

Service cập nhật hai bảng trong cùng transaction rồi ném RuntimeException, test cần xác minh gì?
A. Chỉ log exception mà không quan tâm trạng thái DB
B. Request luôn nhận HTTP 200 nếu đã ghi bảng đầu
C. Các cập nhật được rollback khi transaction thất bại
D. Cả hai cập nhật vẫn lưu vì lệnh SQL đã chạy
Đáp án đúng: C

Muốn kiểm tra đường lỗi khi client HTTP bên ngoài timeout, cách làm nào phù hợp?
A. Chuyển toàn bộ lỗi mạng thành phản hồi 200 mặc định
B. Bỏ cấu hình timeout để bài test không bao giờ fail
C. Điều khiển stub gây timeout và kiểm tra xử lý lỗi
D. Chỉ kiểm tra code client có phương thức gọi GET
Đáp án đúng: C

Nhiều bài test tạo tài khoản trùng email và phụ thuộc thứ tự chạy, nên sửa thế nào?
A. Chạy các lớp theo thứ tự tên để tránh va chạm
B. Cấp fixture riêng và cleanup sau mỗi ca
C. Tắt unique constraint trong schema dành cho CI
D. Cho mọi test dùng tài khoản mặc định của production
Đáp án đúng: B

Hai CI job integration test chạy song song, môi trường nào giúp tránh xung đột?
A. Dùng một database staging chung không reset dữ liệu
B. Cho job thứ hai bỏ qua các câu test bị fail
C. Cả hai job chia sẻ schema và xóa bảng tùy ý
D. Mỗi job có DB và broker cô lập với vòng đời riêng
Đáp án đúng: D

Controller trả 201 khi tạo đơn hàng; assertion nào xác nhận tích hợp sâu hơn?
A. Đọc lại đơn hàng và kiểm tra trường đã được lưu
B. Chỉ xác minh mock repository đã được gọi đúng lần
C. Chỉ xác nhận status response và kết thúc bài test
D. Chỉ đếm số method trong lớp controller
Đáp án đúng: A

Một ca tích hợp fail ngẫu nhiên ở ranh giới API và broker; bằng chứng nào hữu ích nhất?
A. Chỉ nhìn tên test và số lần build trên CI
B. Đối chiếu request, trace và trạng thái broker
C. Chỉ nâng số lần retry để build chuyển xanh
D. Bỏ qua lỗi nếu unit test của service vẫn pass
Đáp án đúng: B
