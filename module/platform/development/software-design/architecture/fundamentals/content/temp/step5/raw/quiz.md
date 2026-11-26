1. Khi phân tích kiến trúc, đầu vào nào nên được làm rõ trước khi chọn công nghệ?
A. Danh sách framework quen thuộc của từng lập trình viên
B. Kích thước thư mục mã nguồn trên máy phát triển
C. Bối cảnh, ràng buộc và mục tiêu chất lượng hệ thống
D. Số plugin được cài trong IDE của nhóm dự án
Đáp án đúng: C

2. Một yêu cầu chức năng khác thuộc tính chất lượng ở điểm nào?
A. Chức năng mô tả làm gì; thuộc tính mô tả mức đáp ứng
B. Chức năng chỉ dùng tại frontend; chất lượng chỉ ở database
C. Chức năng luôn đo bằng độ trễ; chất lượng không thể đo
D. Chức năng chỉ quan trọng lúc build; chất lượng lúc deploy
Đáp án đúng: A

3. Để đánh giá kiến trúc theo độ trễ, kịch bản chất lượng cần nêu gì?
A. Chỉ tên công nghệ được lựa chọn cho API và database
B. Tác nhân, tình huống tải và ngưỡng phản hồi
C. Chỉ số lớp của module được dùng khi đo tải
D. Chỉ danh sách giao diện sẽ được thiết kế mới
Đáp án đúng: B

4. Khi một yêu cầu là 'phản hồi nhanh', cách làm rõ hữu ích nhất là gì?
A. Tuyên bố máy chủ luôn phải có CPU đời mới nhất
B. Cố định một framework web mà không cần thử tải
C. Chỉ tính thời gian lập trình cần để hoàn thành API
D. Đặt ngưỡng p95 ở mức tải và điều kiện cụ thể
Đáp án đúng: D

5. Tính sẵn sàng của dịch vụ cần xem xét điều gì ngoài tốc độ xử lý?
A. Chỉ kích thước response theo đơn vị byte
B. Chỉ quy tắc đặt tên endpoint ở tầng giao diện
C. Gián đoạn, phương án dự phòng và phục hồi
D. Chỉ số lượng màn hình người dùng đã mở
Đáp án đúng: C

6. Khả năng mở rộng ngang thể hiện thay đổi nào của hệ thống?
A. Thêm instance để chia sẻ khối lượng công việc
B. Tăng RAM của một máy chủ mà không thêm instance
C. Giảm độ lớn file cấu hình mỗi lần triển khai
D. Đổi toàn bộ code Java sang một ngôn ngữ khác
Đáp án đúng: A

7. Một module có cohesion cao thường mang đặc trưng nào?
A. Chứa mọi phương thức tiện ích của toàn bộ hệ thống
B. Các thành phần cùng phục vụ trách nhiệm liên quan chặt
C. Phụ thuộc trực tiếp vào chi tiết lưu trữ của mọi module
D. Tập hợp các lớp chỉ vì cùng được tạo một lúc
Đáp án đúng: B

8. Vì sao kiến trúc ưu tiên loose coupling giữa các module?
A. Bảo đảm không module nào cần trao đổi dữ liệu
B. Buộc mọi module được triển khai thành dịch vụ riêng
C. Giảm tác động khi hợp đồng giữa module thay đổi
D. Làm cho mọi call đồng bộ đều không có chi phí
Đáp án đúng: C

9. Trong đồ thị phụ thuộc, một chu trình giữa các module gây khó khăn gì?
A. Tự bảo đảm tất cả module cùng bảo toàn invariant
B. Khó phát triển và thay đổi module một cách độc lập
C. Giúp phát hiện tất cả lỗi bảo mật trước khi release
D. Giảm toàn bộ nhu cầu khai báo hợp đồng giao tiếp
Đáp án đúng: B

10. Khi một module công bố API cho module khác, hợp đồng nên thể hiện gì?
A. Đầu vào, đầu ra, lỗi và hành vi của hợp đồng
B. Chi tiết bảng và câu truy vấn SQL bên trong module
C. Tên lớp triển khai nội bộ và cấu trúc file nguồn
D. Cách bố trí nút bấm của giao diện người dùng
Đáp án đúng: A

11. Trong kiến trúc phân lớp, ý nghĩa chính của ranh giới lớp là gì?
A. Buộc mỗi lớp hoạt động trên một server vật lý riêng
B. Đảm bảo từng lớp có đúng số lượng class giống nhau
C. Tách các trách nhiệm và quy tắc phụ thuộc giữa lớp
D. Cho phép UI trực tiếp thay đổi mọi dữ liệu nghiệp vụ
Đáp án đúng: C

12. Vì sao không nên để quy tắc nghiệp vụ phụ thuộc trực tiếp vào HTTP controller?
A. Controller không có khả năng nhận request hợp lệ
B. Miền khó kiểm thử và tái sử dụng độc lập hơn
C. Mọi request HTTP bắt buộc là giao dịch bất đồng bộ
D. Bởi tất cả ứng dụng đều phải dùng cùng một router
Đáp án đúng: B

13. Khi nào giao tiếp bất đồng bộ qua message phù hợp hơn RPC đồng bộ?
A. Khi lệnh cần trả kết quả tức thì trong cùng request
B. Khi cần một transaction ACID chung trên mọi dịch vụ
C. Khi người dùng yêu cầu đọc dữ liệu mới nhất tức thời
D. Khi bên gửi không cần phản hồi ngay và cần tách tải
Đáp án đúng: D

14. Khi chọn sở hữu dữ liệu theo module, ranh giới nào quan trọng nhất?
A. Mọi module truy cập ghi trực tiếp tất cả bảng để tiện join
B. Schema vật lý tự quyết định phạm vi nghiệp vụ của module
C. Bất kỳ client nào cũng tự chọn nơi ghi dữ liệu nguồn
D. Module bảo vệ invariant và kiểm soát thao tác với dữ liệu
Đáp án đúng: D

15. Khi tách dữ liệu qua dịch vụ bất đồng bộ, đánh đổi nào cần giải thích?
A. Giảm liên kết nhưng dữ liệu đọc có thể trễ so với ghi
B. Tự động bảo đảm dữ liệu nhất quán tức thời ở mọi nơi
C. Mọi lệnh đều hoàn tất trong cùng một transaction toàn cục
D. Không cần kiểm tra trùng thông điệp khi có retry
Đáp án đúng: A

16. Khi thiết kế ranh giới bảo mật, tại sao cần xác thực quyền tại server?
A. Client luôn cung cấp thông tin phân quyền đáng tin tuyệt đối
B. API gateway tự kiểm soát tất cả invariant nghiệp vụ
C. TLS tự xác định mọi quyền đọc ghi theo vai trò người dùng
D. Client có thể bị sửa hoặc gọi API ngoài giao diện dự kiến
Đáp án đúng: D

17. Một SLO cho dịch vụ nên được thể hiện như thế nào?
A. Chỉ bằng lời hứa rằng mọi request luôn thành công
B. Chỉ bằng số lượng server trong sơ đồ kiến trúc
C. Chỉ bằng version framework web đang sử dụng
D. Chỉ số đo được, mục tiêu và chu kỳ theo dõi cụ thể
Đáp án đúng: D

18. Nếu một node có thể hỏng, thiết kế tăng availability thường dùng gì?
A. Bản sao dự phòng kèm điều phối chuyển đổi khi node lỗi
B. Chạy toàn bộ traffic trên một node không có phương án dự phòng
C. Chỉ tăng dung lượng đĩa của node đang xử lý yêu cầu
D. Đổi tên node theo môi trường staging hay production
Đáp án đúng: A

19. Khi truy vết request đi qua nhiều dịch vụ, dữ liệu nào hữu ích nhất?
A. Chỉ tổng số dòng code theo tên từng dịch vụ
B. Chỉ danh sách các dependency Maven của ứng dụng
C. Chỉ thời điểm người lập trình mở IDE gần nhất
D. Trace ID, span, thời gian và lỗi tại từng bước
Đáp án đúng: D

20. Để đánh giá trade-off của một phương án kiến trúc, cần so sánh gì?
A. Lợi ích chất lượng và chi phí triển khai, vận hành
B. Chỉ số lượng file Markdown của tài liệu kiến trúc
C. Chỉ số lượng phương thức public trong module Java
D. Chỉ mức độ phổ biến của framework trên mạng xã hội
Đáp án đúng: A

21. Architecture Decision Record (ADR) hữu ích nhất vì ghi lại điều gì?
A. Chỉ toàn bộ log biên dịch của từng bản phát hành
B. Chỉ bảng theo dõi thành viên tham gia mỗi cuộc họp
C. Bối cảnh, quyết định, lý do và hệ quả đi kèm
D. Chỉ danh sách endpoint đang được test trong CI
Đáp án đúng: C

22. Khi so modular monolith với microservices, câu hỏi nào thiết thực?
A. Ngôn ngữ lập trình nào tạo nhiều class hơn trong repo?
B. Có nhu cầu triển khai và mở rộng độc lập theo miền?
C. Server nào đặt tên module dài hơn trong hệ thống?
D. IDE nào dễ kéo thả biểu tượng microservice hơn?
Đáp án đúng: B

23. Anti-corruption layer giữa hệ thống mới và cũ giúp giải quyết gì?
A. Đồng bộ mọi dữ liệu nguồn mà không cần quy tắc ánh xạ
B. Ánh xạ mô hình để giữ đúng ngữ nghĩa giữa hai hệ thống
C. Thay thế hoàn toàn xác thực người dùng ở hệ thống cũ
D. Cho phép gọi trực tiếp cấu trúc bảng nội bộ của đối tác
Đáp án đúng: B

24. Architecture fitness function nhằm kiểm soát điều gì theo thời gian?
A. Chỉ đánh giá giao diện có giống bản thiết kế hình ảnh
B. Chỉ đo thời gian dựng project trong IDE của người dùng
C. Tự động kiểm tra việc tuân thủ ràng buộc kiến trúc
D. Chỉ đếm số request từ hệ thống monitor mỗi ngày
Đáp án đúng: C
