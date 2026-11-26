Bước Red trong TDD nhằm xác nhận điều gì?
A. Test mới thất bại vì hành vi còn thiếu
B. Mã hiện tại biên dịch nhanh hơn bản trước
C. Tất cả test cũ đều đã được loại bỏ
D. Bộ test tự động chưa có kết nối CI
Đáp án đúng: A

Khi test Red thất bại do lỗi cấu hình môi trường, nên làm gì?
A. Chuyển ngay sang viết code tính năng mới
B. Bỏ assertion rồi ghi nhận giai đoạn Red
C. Sửa môi trường để lỗi do hành vi thiếu
D. Xóa test vì thất bại không liên quan code
Đáp án đúng: C

Trong Green, cách triển khai được ưu tiên là gì?
A. Xây sẵn framework cho mọi nhu cầu tương lai
B. Tối ưu mọi đường chạy trước khi test xanh
C. Viết đủ mã để bài test hiện tại qua
D. Đổi toàn bộ kiến trúc ngay khi test đỏ
Đáp án đúng: C

Refactor trong vòng TDD nên thực hiện khi nào?
A. Khi test mới đỏ do sai hành vi còn thiếu
B. Khi các test đang xanh và đáng tin cậy
C. Chỉ sau khi phát hành lên môi trường thật
D. Trước khi viết bất kỳ test mới nào
Đáp án đúng: B

Lợi ích của vòng Red–Green–Refactor ngắn là gì?
A. Giảm yêu cầu phải hiểu hợp đồng nghiệp vụ
B. Cho phép bỏ qua test hồi quy hiện tại
C. Bảo đảm tính năng tự tối ưu về latency
D. Phát hiện sai lệch gần nơi vừa thay đổi
Đáp án đúng: D

Khi một test mới đã xanh trước khi viết code, điều gì cần xem lại?
A. Công cụ build có đang dùng phiên bản mới không
B. Test có thực sự kiểm tra hành vi còn thiếu không
C. Tất cả dependency có được khai báo trong pom không
D. Số lượng test trước đó có đang quá nhiều không
Đáp án đúng: B

Test tốt trong TDD nên tập trung vào yếu tố nào?
A. Thứ tự chi tiết từng câu lệnh Java nội bộ
B. Hành vi quan sát được của đơn vị cần test
C. Tên biến riêng được khai báo trong method
D. Số branch được compiler tạo trong bytecode
Đáp án đúng: B

Vì sao không nên viết nhiều production code ở bước Green?
A. Làm JVM không cho phép khởi tạo object mới
B. Buộc test dùng chung tất cả dữ liệu đầu vào
C. Làm mọi refactor kế tiếp phải bỏ inheritance
D. Dễ vượt phạm vi hành vi được test bảo vệ
Đáp án đúng: D

Một tên test có giá trị nên thể hiện gì?
A. Số dòng code mà class production sẽ chứa
B. Tên tác giả và thời điểm viết method đó
C. Điều kiện và kết quả mong đợi rõ ràng
D. Tên framework dùng để khởi tạo test runner
Đáp án đúng: C

Trong JUnit Jupiter, @Test thường biểu thị gì?
A. Một điểm ghi dữ liệu vào database thật
B. Method được thực thi như một test
C. Một class tự động thay thế dependency
D. Một bước kết thúc transaction Spring
Đáp án đúng: B

Khi kiểm tra exception mong đợi trong JUnit, dùng gì?
A. assertThrows với kiểu lỗi được kỳ vọng
B. assertEquals so sánh hai stack trace thô
C. assertTrue chỉ kiểm tra object không null
D. assertTimeout chỉ kiểm tra kiểu lỗi trả về
Đáp án đúng: A

Khi nào @ParameterizedTest hữu ích?
A. Mỗi trường hợp cần hệ thống hoàn toàn khác
B. Chỉ cần kiểm tra thứ tự gọi các mock
C. Một quy tắc cần thử nhiều bộ dữ liệu
D. Cần chạy cùng test mà không có assertion
Đáp án đúng: C

Arrange–Act–Assert tổ chức một test thế nào?
A. Xác minh, triển khai rồi khởi tạo dữ liệu
B. Viết mã sản phẩm, deploy rồi chạy test
C. Mock toàn bộ, bỏ hành động và log lỗi
D. Chuẩn bị, thực thi, rồi xác minh kết quả
Đáp án đúng: D

Bước Refactor trong TDD có mục đích gì?
A. Bổ sung quy tắc mới khi không có test
B. Thay đầu ra kỳ vọng cho dễ chạy test
C. Xóa các assertion trước khi gộp code
D. Làm mã rõ hơn mà giữ nguyên hành vi
Đáp án đúng: D

Vì sao nên chạy toàn bộ test liên quan sau Refactor?
A. Đo tốc độ biên dịch của mọi module
B. Xác minh số lượng commit được giữ nguyên
C. Phát hiện regression ngoài test vừa viết
D. Bảo đảm source code không dùng annotation
Đáp án đúng: C

Unit test độc lập cần kiểm soát điều gì?
A. Các test dùng chung object mutable thay đổi
B. Dữ liệu riêng và không phụ thuộc test khác
C. Thứ tự chạy cố định giữa mọi test class
D. Chỉ những ca đã pass ở lần trước mới chạy
Đáp án đúng: B

Khi logic phụ thuộc đồng hồ hệ thống, nên cải thiện thiết kế thế nào?
A. Tiêm nguồn thời gian có thể kiểm soát
B. Thêm Thread.sleep trước mỗi lời gọi xử lý
C. Đọc trực tiếp thời gian trong mọi assertion
D. Chuyển tất cả test thành integration test
Đáp án đúng: A

Một test double thường giúp giải quyết vấn đề gì?
A. Cô lập phụ thuộc khó kiểm soát
B. Thay thế hoàn toàn hợp đồng nghiệp vụ
C. Giảm yêu cầu kiểm thử mọi trường hợp biên
D. Bảo đảm dữ liệu production không thay đổi
Đáp án đúng: A

Khi nào stub phù hợp hơn mock xác minh tương tác?
A. Cần kiểm tra chính xác số lần gửi thông báo
B. Cần điều khiển dữ liệu trả về của phụ thuộc
C. Cần xác nhận thứ tự giao tiếp nhiều đối tượng
D. Cần phát hiện thiếu lời gọi có tác dụng phụ
Đáp án đúng: B

Khi nào nên dùng verify với Mockito?
A. Khi mọi lệnh gọi private đều phải được đếm
B. Khi chỉ cần so sánh giá trị trả về thuần túy
C. Khi muốn thay thế mọi assertion trên kết quả
D. Khi tương tác là hợp đồng quan trọng
Đáp án đúng: D

Test dễ vỡ khi refactor thường có dấu hiệu gì?
A. Bám quá sát chi tiết thực thi
B. Xác minh kết quả qua API công khai
C. Tạo dữ liệu thử độc lập cho từng ca
D. Nêu rõ quy tắc nghiệp vụ bằng tên test
Đáp án đúng: A

Với giới hạn tuổi từ 18 trở lên, bộ test biên cần gì?
A. Chỉ trường hợp đủ 30 tuổi trở lên
B. Ba giá trị ngẫu nhiên trên 18 tuổi
C. Một trường hợp nhận giá trị null
D. Trường hợp 17, 18 và 19 tuổi
Đáp án đúng: D

Để kiểm tra đầu vào rỗng, test nên diễn đạt điều gì?
A. Cách vòng lặp Java được compiler tối ưu
B. Hành vi mong đợi khi không có dữ liệu
C. Số lần constructor được tạo trong một phút
D. Tên biến nhận chuỗi tại tầng controller
Đáp án đúng: B

Trong TDD, test lỗi ban đầu phải đáng tin vì sao?
A. Nếu quá nhanh sẽ không ghi đủ log lỗi
B. Nếu quá ít mock thì không chạy trong CI
C. Phải thất bại vì hành vi đang thiếu
D. Nếu tên ngắn thì JUnit sẽ tự bỏ qua
Đáp án đúng: C

Khi dependency gửi email cần được cô lập, nên làm gì?
A. Luôn gửi mail thật qua hệ thống production
B. Tiêm gateway giả trong unit test của use case
C. Đưa lệnh gửi email vào method private
D. Bỏ mọi kiểm chứng về việc gửi thông báo
Đáp án đúng: B

TDD khuyến khích đơn giản hóa thiết kế bằng cách nào?
A. Để test mới dẫn tới thay đổi nhỏ cần thiết
B. Dự đoán sẵn mọi lớp trừu tượng tương lai
C. Thiết kế toàn bộ interface trước ca kiểm thử
D. Viết tất cả tính năng rồi thêm test về sau
Đáp án đúng: A

Khi code trùng lặp xuất hiện sau vài vòng Green, nên làm gì?
A. Refactor phần chung sau khi test xanh
B. Bỏ một test vì đã trùng câu lệnh
C. Thêm logic mới vào test để code ngắn
D. Đợi đến khi mọi tính năng đã phát hành
Đáp án đúng: A

Trong TDD, tiêu chí để dừng bước Green là gì?
A. Mọi đường chạy đã được tối ưu tối đa
B. Đã thêm đủ số dòng theo kế hoạch
C. Kiến trúc đã sẵn sàng cho năm năm tới
D. Test mới xanh với giải pháp đủ dùng
Đáp án đúng: D

Một test được xây trên dữ liệu random không kiểm soát có nguy cơ gì?
A. Bảo đảm phát hiện mọi lỗi trong hệ thống
B. Tự tăng mutation score ở mọi lần chạy
C. Giúp assertion độc lập với các input
D. Thất bại khó tái hiện giữa các lần chạy
Đáp án đúng: D

Khi test phụ thuộc database thật chạy chậm, nên cân nhắc gì?
A. Tách unit test khỏi integration test cần DB
B. Thay mọi test bằng chạy thủ công trên UI
C. Bỏ transaction khỏi mọi phương thức Java
D. Xóa dữ liệu test sau khi deploy production
Đáp án đúng: A

Một class khó khởi tạo trong unit test có thể báo hiệu điều gì?
A. Cần tăng số trường static để dùng chung
B. Cần chuyển mọi method sang private
C. Dependency hoặc trách nhiệm bị kết dính quá chặt
D. Cần thêm trực tiếp kết nối HTTP trong constructor
Đáp án đúng: C

TDD và kiểm thử viết sau code khác nhau chủ yếu ở đâu?
A. TDD chỉ chạy với một framework cố định
B. Test viết sau code luôn chạy nhanh hơn
C. Test dẫn hướng quyết định thiết kế từ đầu
D. TDD không cho phép sửa mã đã chạy xanh
Đáp án đúng: C

Khi assertion chỉ kiểm tra object khác null, nguy cơ gì?
A. Tự động xác minh đúng mọi quy tắc nghiệp vụ
B. Bỏ lọt kết quả sai nhưng object vẫn tồn tại
C. Giảm tốc độ build của toàn bộ ứng dụng
D. Cấm việc sử dụng Mockito trong unit test
Đáp án đúng: B

Một test báo xanh nhưng không có assertion hữu ích nên xử lý sao?
A. Đánh dấu test thành integration test
B. Bổ sung kiểm chứng hành vi cụ thể
C. Tăng timeout để giữ trạng thái xanh
D. Giữ nguyên vì test đã chạy không lỗi
Đáp án đúng: B

Để tránh test phụ thuộc thứ tự chạy, nên dùng gì?
A. Thiết lập trạng thái mới trước mỗi trường hợp
B. Chia sẻ một biến static mutable giữa mọi test
C. Cho phép test A tạo dữ liệu cho test B
D. Chạy tất cả test trong một thread cố định
Đáp án đúng: A

Trường hợp nào nên ưu tiên test cho ngoại lệ nghiệp vụ?
A. Một helper chỉ nối hai chuỗi hằng
B. Một getter thuần trả về field bất biến
C. Một lệnh vi phạm điều kiện domain quan trọng
D. Một class chỉ khai báo tên package
Đáp án đúng: C

Khi refactor từ if/switch sang Strategy, nên bảo vệ gì?
A. Tên class và số lượng method private cũ
B. Thứ tự các dòng lệnh trong mỗi nhánh
C. Hành vi cho từng loại đầu vào đã hỗ trợ
D. Cấu trúc import của những class bị tách
Đáp án đúng: C

Mutation testing bổ sung cho TDD bằng khả năng nào?
A. Kiểm tra test có phát hiện sai lệch nhỏ không
B. Thay thế quá trình viết test trước code
C. Bảo đảm code luôn nhanh hơn khi build
D. Tự sinh các yêu cầu nghiệp vụ mới
Đáp án đúng: A

Khi quy tắc chưa rõ để viết test Red, cách phù hợp là gì?
A. Tự chọn đầu ra dễ cài đặt nhất
B. Bỏ test và viết toàn bộ chức năng
C. Chỉ dựa trên tên method trong interface
D. Xin ví dụ cụ thể từ người hiểu nghiệp vụ
Đáp án đúng: D

Thước đo nào phản ánh TDD hiệu quả hơn số lượng test?
A. Số dòng annotation @Test trong dự án
B. Số lần IDE tự động tạo test class
C. Tổng số mock trong mỗi test method
D. Phản hồi nhanh và thay đổi mã an toàn
Đáp án đúng: D
