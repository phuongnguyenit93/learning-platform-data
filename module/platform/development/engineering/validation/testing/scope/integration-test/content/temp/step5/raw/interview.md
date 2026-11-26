Bạn phân biệt integration test với unit test và E2E test theo các thành phần thật được ghép nối và bằng chứng cần thu thập như thế nào?
Bạn xác định ranh giới một integration test cho API, service và database dựa trên hợp đồng nào cần được kiểm chứng ra sao?
Bạn lựa chọn tương tác nào giữa hai thành phần có rủi ro cao nhất để ưu tiên viết integration test như thế nào?
Bạn thiết kế kiểm thử một API tạo đơn hàng để xác minh cả HTTP response lẫn dữ liệu thực sự được ghi xuống database ra sao?
Bạn xác định phần nào của hệ thống cần dùng phụ thuộc thật và phần nào có thể dùng stub để giữ đúng mục tiêu kiểm thử tích hợp như thế nào?
Bạn tổ chức kiểm thử luồng service gọi repository khi dữ liệu đầu vào vi phạm ràng buộc cơ sở dữ liệu ra sao?
Bạn xác minh mapping giữa đối tượng Java và schema thực tế khi kiểu cột, giá trị NULL hoặc khóa ngoại có khác biệt như thế nào?
Bạn thiết kế integration test cho luồng đọc ghi trong một transaction để kiểm tra commit và rollback như thế nào?
Bạn phân tích ảnh hưởng của transaction bao quanh test tới khả năng quan sát commit thực trong ứng dụng Spring ra sao?
Khi test chạy qua HTTP server thật, bạn làm rõ vì sao rollback transaction của test không nhất thiết khôi phục dữ liệu phía server như thế nào?
Bạn lựa chọn @SpringBootTest hay cấu hình test slice của Spring dựa trên phạm vi bean và đường xử lý cần kiểm tra ra sao?
Bạn cấu hình Spring TestContext để tải đúng profile, properties và các bean cho môi trường tích hợp như thế nào?
Bạn quyết định khi nào tái sử dụng ApplicationContext và khi nào cần làm mới context để tránh rò rỉ trạng thái giữa các test ra sao?
Bạn thiết kế JUnit Jupiter lifecycle cho fixture cấp test và cấp class nhằm giữ từng integration test độc lập như thế nào?
Bạn dùng JUnit parameterized test để kiểm tra cùng một hợp đồng API với nhiều biến thể dữ liệu hợp lệ và không hợp lệ ra sao?
Bạn tổ chức việc kiểm tra JSON response để xác nhận trường nghiệp vụ quan trọng mà không phụ thuộc vào thứ tự thuộc tính như thế nào?
Bạn chọn MockMvc, WebTestClient hay HTTP client thực dựa trên đường đi qua web server mà bài test phải kiểm chứng như thế nào?
Bạn thiết kế test kiểm tra phân quyền API từ token hoặc identity thật để phát hiện thiếu bộ lọc truy cập dữ liệu như thế nào?
Bạn xác định cách kiểm thử lỗi validation đầu vào đi qua controller, service và lớp lưu trữ mà không che giấu lỗi gốc ra sao?
Bạn xây dựng dữ liệu đầu vào tối thiểu vẫn thể hiện được toàn bộ ràng buộc quan hệ của một tình huống tích hợp như thế nào?
Bạn lựa chọn SQL seed, factory Java hay API setup để tạo fixture theo tiêu chí dễ đọc và ít phụ thuộc như thế nào?
Bạn đặt chiến lược định danh dữ liệu thử nghiệm để tránh xung đột unique key giữa các lượt chạy song song ra sao?
Bạn thiết kế dọn dẹp dữ liệu bằng transaction, truncate hoặc schema riêng khi test có nhiều kết nối và tài nguyên ngoài database như thế nào?
Bạn nhận diện một bài test phụ thuộc thứ tự chạy hoặc dữ liệu sót lại và tái cấu trúc fixture để loại bỏ phụ thuộc như thế nào?
Bạn lựa chọn database nhúng hay database thật qua Testcontainers dựa trên khác biệt dialect, transaction và migration ra sao?
Bạn sử dụng Testcontainers để khởi chạy database cùng phiên bản dự kiến của production và tiêm thông tin kết nối vào Spring như thế nào?
Bạn thiết kế việc tái sử dụng container giữa nhiều bài test mà vẫn duy trì dữ liệu cô lập như thế nào?
Bạn kiểm tra migration schema trong integration test trước khi chạy các truy vấn ứng dụng để phát hiện lỗi nâng cấp sớm ra sao?
Bạn xử lý tình huống Testcontainers khởi động thất bại trên CI bằng thông tin chẩn đoán và giới hạn tài nguyên nào?
Bạn thiết kế integration test cho thao tác ghi database và phát sự kiện vào message broker để xác minh kết quả của cả hai phía như thế nào?
Bạn lựa chọn chạy broker thật bằng container hay dùng in-memory test double dựa trên những bảo đảm giao hàng cần kiểm chứng như thế nào?
Bạn xác minh nội dung, khóa định tuyến và header của message phát ra khi service xử lý một yêu cầu nghiệp vụ ra sao?
Bạn thiết kế kiểm thử consumer xử lý một message trùng lặp mà không tạo bản ghi nghiệp vụ trùng như thế nào?
Bạn kiểm thử cơ chế retry và dead-letter queue với thông điệp lỗi mà không phụ thuộc vào việc ngủ một khoảng thời gian cố định ra sao?
Bạn chờ kết quả bất đồng bộ trong integration test bằng điều kiện quan sát được và thời hạn rõ ràng như thế nào?
Bạn mô phỏng một sự cố mạng hoặc timeout của phụ thuộc bên ngoài để kiểm tra cơ chế fallback của service ra sao?
Bạn xác định giới hạn của mock HTTP server trong việc mô phỏng một dịch vụ bên ngoài và chọn trường hợp cần sandbox thật như thế nào?
Bạn xây dựng test hợp đồng cho client HTTP để phát hiện thay đổi schema phản hồi hoặc mã trạng thái của đối tác như thế nào?
Bạn kiểm tra headers, thời gian chờ và chính sách thử lại của HTTP client trong môi trường tích hợp như thế nào?
Bạn xác minh rằng một hành động chỉ gọi dịch vụ bên ngoài đúng một lần hoặc theo cơ chế idempotency đã thiết kế như thế nào?
Bạn xử lý thời gian hệ thống, múi giờ và dữ liệu hết hạn khi integration test liên quan token hoặc lịch trình ra sao?
Bạn thiết kế test cho optimistic locking bằng hai luồng cập nhật cùng phiên bản dữ liệu và kiểm chứng kết quả xung đột như thế nào?
Bạn kiểm tra ràng buộc isolation khi hai transaction đồng thời đọc và ghi cùng dữ liệu mà không làm test phụ thuộc lịch thực thi ngẫu nhiên như thế nào?
Bạn phân loại lỗi integration test do code, schema, cấu hình, dữ liệu hoặc hạ tầng container theo dấu vết nào?
Bạn cấu hình log SQL, request và trace cho integration test để điều tra nhanh nhưng không lộ dữ liệu nhạy cảm ra sao?
Bạn quyết định phần nào của integration suite cần chạy trên mỗi pull request và phần nào chạy trong pipeline mở rộng như thế nào?
Bạn tổ chức chạy song song integration test trong CI khi các test cùng dùng database và broker như thế nào?
Bạn ngăn kiểm thử vô tình kết nối tới môi trường production bằng cấu hình và cơ chế kiểm tra an toàn nào?
Bạn giới hạn thời gian khởi tạo context, khởi chạy container và thực hiện test để tránh pipeline bị treo như thế nào?
Bạn sử dụng các metric về thời gian, tỷ lệ flaky và số lần khởi động container để chọn hướng tối ưu suite ra sao?
Bạn đánh giá khi nào một bài integration test đang kiểm tra quá nhiều tầng và cần tách thành các trường hợp tập trung hơn như thế nào?
Bạn phát hiện false positive khi test chỉ xác nhận HTTP 200 mà không kiểm chứng thay đổi trạng thái nghiệp vụ ra sao?
Bạn tổ chức integration test cho các đường xử lý lỗi và bù trừ khi một bước ghi thành công nhưng bước gửi message thất bại như thế nào?
Bạn dùng dữ liệu thử nghiệm sát production ở mức cấu trúc và phân bố nhưng vẫn bảo vệ thông tin nhạy cảm như thế nào?
Bạn đánh giá bằng chứng từ integration suite để quyết định một thay đổi schema hoặc API có đủ an toàn để phát hành ra sao?
