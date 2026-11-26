Bài integration test của repository Java nên xác minh điều gì?
A. Chỉ logic phân nhánh trong một method thuần
B. Chỉ số lần Mockito được gọi trong unit test
C. Truy vấn và ánh xạ kết quả với database thực
D. Chỉ tên property khai báo trong class entity
Đáp án đúng: C

Muốn kiểm thử luồng nhiều bean Spring trong application context, lựa chọn nào phù hợp?
A. Chỉ khởi tạo class service bằng toán tử new
B. Chỉ mock mọi bean rồi chạy method riêng lẻ
C. Chỉ tạo MockitoExtension không nạp Spring
D. Dùng @SpringBootTest để nạp ngữ cảnh ứng dụng
Đáp án đúng: D

Testcontainers giúp bài test tích hợp database theo hướng nào?
A. Dùng một mock trả dữ liệu được mã hóa cứng
B. Thay toàn bộ JDBC bằng danh sách trong bộ nhớ
C. Khởi chạy DB container phù hợp cho bài test
D. Chia sẻ DB production với mọi job kiểm thử
Đáp án đúng: C

Để test tạo người dùng chạy được nhiều lần trên CI, dữ liệu nên được tổ chức thế nào?
A. Dùng định danh riêng và cơ chế dọn dữ liệu
B. Dùng chung email cố định ở mọi lần chạy
C. Đổi thứ tự test để tránh lỗi trùng khóa
D. Chỉ xóa dữ liệu khi lần kiểm thử thành công
Đáp án đúng: A

Trong Spring integration test, @Transactional trên test thường có giới hạn nào?
A. Luôn rollback mọi request qua server HTTP riêng
B. Rollback gắn với transaction của luồng kiểm thử
C. Luôn rollback cả message đã gửi đến broker
D. Tự xóa bản ghi trong mọi DB bên ngoài
Đáp án đúng: B

Test tạo record rồi gọi repository, cách kiểm chứng phù hợp là gì?
A. Đọc lại qua repository và so dữ liệu đã lưu
B. Chỉ kiểm tra mock DAO đã được gọi đúng lần
C. Chỉ đếm số annotation trên entity Java
D. Chỉ so thời gian phương thức save trả về
Đáp án đúng: A

Khi test một consumer nhận message bất đồng bộ, nên xác nhận kết quả thế nào?
A. Sleep cố định đủ lâu rồi coi message đã xử lý
B. Chỉ kiểm tra producer không ném exception
C. Tắt consumer để tránh thay đổi dữ liệu bên dưới
D. Đợi có giới hạn đến khi side effect xuất hiện
Đáp án đúng: D

Với nhà cung cấp API ngoài không ổn định, chiến lược test tích hợp nào hợp lý?
A. Thay mọi kiểm tra bằng unit test không có HTTP
B. Dùng stub có hợp đồng rõ và test riêng với API thật
C. Gọi API thật trong mọi commit mà không giới hạn
D. Tắt xác minh cấu trúc request và response
Đáp án đúng: B

Test gửi lệnh tạo đơn qua API và nhận 201; kiểm tra nào tăng độ tin cậy?
A. Chỉ kiểm tra controller có đúng một method POST
B. Chỉ kiểm tra log không chứa stack trace
C. Chỉ xác minh mock service có một lần được gọi
D. Đọc lại đơn hàng và đối chiếu trạng thái lưu
Đáp án đúng: D

Integration test sửa dữ liệu chung làm test khác fail; biện pháp nào trực tiếp nhất?
A. Cho mọi test chạy một luồng theo tên lớp
B. Tăng timeout để test sau chờ đủ lâu
C. Tách dữ liệu và cleanup sau từng ca phù hợp
D. Giữ DB chung không reset để mô phỏng production
Đáp án đúng: C

Message broker có thể phát lại một sự kiện, integration test nên kiểm chứng điều gì?
A. Consumer xử lý lặp mà không tạo tác dụng sai
B. Consumer chỉ nhận đúng một sự kiện suốt đời
C. Producer luôn gửi message từ một thread
D. Broker tự rollback cả transaction của database
Đáp án đúng: A

Khi Spring TestContext tái sử dụng application context, nguy cơ nào cần để ý?
A. State mutable trong bean có thể rò giữa các test
B. Mọi bean đều bị tạo lại sau mỗi assertion
C. Mọi transaction đều tự commit sau khi test kết thúc
D. Các annotation của test không còn được xử lý
Đáp án đúng: A

Vì sao integration test nên chạy migration schema tương thích môi trường thật?
A. Để tránh phải seed dữ liệu cho mọi repository
B. Để phát hiện sai lệch bảng, cột và ràng buộc
C. Để bỏ hết kiểm thử SQL trước khi phát hành
D. Để container tự giữ dữ liệu giữa các lần chạy
Đáp án đúng: B

Một test API qua service đến DB fail, bước chẩn đoán hữu ích nào?
A. Chỉ xem tên test có viết theo chuẩn JUnit
B. Chỉ tăng số lượt retry trước khi lưu báo cáo
C. Chỉ đổi thứ tự chạy các class test có lỗi
D. Kiểm tra request, log SQL và trạng thái DB
Đáp án đúng: D

Muốn kiểm tra một method gửi dữ liệu tới broker thật, cần quan sát điều gì?
A. Chỉ kiểm tra method hoàn thành không lỗi
B. Chỉ so interface của client với tên topic
C. Message được broker nhận và có payload đúng
D. Chỉ kiểm tra cấu hình serializer trong source
Đáp án đúng: C

Khi chạy integration test song song trên CI, lựa chọn nào giúp ổn định môi trường?
A. Cho toàn bộ job cùng dùng schema dữ liệu cố định
B. Cấp tài nguyên tách biệt và quản lý vòng đời test
C. Chỉ dùng database production trên môi trường CI
D. Cho phép các job tự xóa bảng của job khác
Đáp án đúng: B
