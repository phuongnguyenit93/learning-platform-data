1. Mục tiêu chính khi xây dựng domain model từ yêu cầu nghiệp vụ là gì?
A. Biến từng trường dữ liệu thành một bảng vật lý riêng
B. Ánh xạ trực tiếp từng màn hình thành một lớp domain
C. Diễn đạt khái niệm, hành vi và quy tắc nghiệp vụ
D. Tách mọi thao tác thành thủ tục không có trạng thái
Đáp án đúng: C

2. Ubiquitous language giúp nhóm kỹ thuật và chuyên gia miền làm gì?
A. Dùng cùng tên cột kỹ thuật cho mọi bảng của hệ thống
B. Tránh trao đổi với chuyên gia khi tài liệu đã được viết
C. Dùng một tên duy nhất cho mọi khái niệm ở mọi ngữ cảnh
D. Dùng chung thuật ngữ với ý nghĩa rõ trong phạm vi miền
Đáp án đúng: D

3. Khi phỏng vấn để khám phá miền, câu hỏi nào hữu ích nhất?
A. Kiểu dữ liệu SQL nào được dùng nhiều nhất ở công ty?
B. Tình huống nào làm quy tắc xử lý đơn hàng thay đổi?
C. Màn hình nào nên chứa toàn bộ phương thức lưu dữ liệu?
D. IDE nào đang được từng nhân viên dùng để viết Java?
Đáp án đúng: B

4. Hai khách hàng có cùng tên và ngày sinh nhưng là hai người khác nhau. Nên mô hình thế nào?
A. Value object bằng nhau vì có cùng giá trị thuộc tính
B. Entity có danh tính riêng dù thuộc tính trùng nhau
C. Một singleton dùng chung cho cả hai khách hàng
D. Một enum ứng với từng tổ hợp tên và ngày sinh
Đáp án đúng: B

5. Hai Money cùng số tiền và đơn vị tiền tệ có thể xem bằng nhau theo tiêu chí nào?
A. So bằng ID được cấp mỗi lần khởi tạo đối tượng
B. So theo địa chỉ ô nhớ đang giữ mỗi bản Money
C. So theo giá trị nếu Money được thiết kế là value object
D. So theo thời điểm được ghi vào bảng giao dịch
Đáp án đúng: C

6. Đặc điểm nào thường phù hợp nhất với value object?
A. Không có danh tính nghiệp vụ riêng, so sánh theo giá trị
B. Có vòng đời và mã định danh độc lập theo từng bản
C. Luôn cần repository riêng để sửa thuộc tính bên trong
D. Chỉ dùng để biểu diễn record của bảng cơ sở dữ liệu
Đáp án đúng: A

7. Quy tắc số dư tài khoản không được âm là ví dụ của gì?
A. Invariant phải giữ khi thay đổi trạng thái liên quan
B. Quy tắc chỉ áp dụng khi hiển thị số dư trên UI
C. Thuộc tính phi chức năng chỉ đo trong performance test
D. Điều kiện chỉ cần kiểm tra khi tạo migration dữ liệu
Đáp án đúng: A

8. Nếu thay đổi đơn hàng cần giữ tổng tiền bằng tổng dòng hàng, nên đặt kiểm soát ở đâu?
A. Trong controller sau khi đã lưu xong toàn bộ thay đổi
B. Trong query báo cáo vào cuối mỗi ngày vận hành
C. Trong client, bỏ kiểm tra lại phía server khi ghi
D. Trong hành vi miền duy trì invariant của đơn hàng
Đáp án đúng: D

9. Vai trò của aggregate root trong mô hình domain là gì?
A. Đối tượng chứa toàn bộ entity của mọi miền nghiệp vụ
B. Điểm truy cập kiểm soát invariant bên trong aggregate
C. Lớp chỉ làm nhiệm vụ đổi JSON sang đối tượng Java
D. Đối tượng chuyên nối mọi repository vào cùng một bảng
Đáp án đúng: B

10. Vì sao thay đổi value object thường tạo giá trị mới thay vì sửa tại chỗ?
A. Bảo đảm tất cả entity có chung cùng một định danh
B. Cho phép hai transaction đồng thời bỏ qua kiểm tra
C. Buộc mọi value object phải được lưu vào event store
D. Giữ tính bất biến và tránh ảnh hưởng tham chiếu chia sẻ
Đáp án đúng: D

11. Trường hợp nào phù hợp mô hình hóa hành vi thay vì setter công khai?
A. `order.setStatus(CANCELLED)` do UI tự quyết định
B. `order.status = CANCELLED` không kiểm tra điều kiện
C. `order.cancel()` tự kiểm tra trạng thái có thể hủy
D. `order.setAnyField()` nhận mọi thay đổi từ request
Đáp án đúng: C

12. Khi một tên 'Customer' có hai nghĩa ở bán hàng và hỗ trợ, bước thiết kế nào phù hợp?
A. Gộp hai nghĩa thành một entity có mọi thuộc tính
B. Làm rõ ngữ cảnh và định nghĩa riêng của từng miền
C. Đổi cả hai tên thành mã UUID để tránh phân biệt
D. Chỉ lấy định nghĩa của nhóm có database lớn hơn
Đáp án đúng: B

13. Ranh giới bounded context giúp ích gì trong domain modeling?
A. Giới hạn nơi một ngôn ngữ và mô hình có hiệu lực
B. Bắt mọi context dùng chung entity và bảng dữ liệu
C. Xác định chính xác số lượng server cần để triển khai
D. Buộc mỗi context phải là một microservice độc lập
Đáp án đúng: A

14. Khi mô hình một mối quan hệ giữa Order và Customer khác aggregate, nên làm gì?
A. Luôn cập nhật trực tiếp dữ liệu Customer từ Order
B. Thường tham chiếu danh tính thay vì giữ object graph sâu
C. Luôn sao chép toàn bộ Customer vào mọi dòng Order
D. Gộp hai aggregate để mọi truy vấn chỉ cần một lần đọc
Đáp án đúng: B

15. Một domain event như `OrderShipped` nên biểu thị điều gì?
A. Yêu cầu thực hiện giao hàng ở một thời điểm tương lai
B. Thao tác truy vấn trạng thái giao hàng không thay đổi dữ liệu
C. Lệnh đổi tên phương thức `ship()` trong ứng dụng
D. Sự kiện nghiệp vụ đã xảy ra và có ý nghĩa trong miền
Đáp án đúng: D

16. Khi quy tắc tính phí có nhiều biến thể thay đổi theo chính sách, cách mô hình nào phù hợp?
A. Đặt mọi nhánh điều kiện trong lớp trình bày UI
B. Đóng gói quy tắc thành chính sách miền rõ ràng
C. Chỉ lưu mô tả quy tắc như một chuỗi trong database
D. Nhân bản đoạn mã tính phí ở mỗi endpoint ứng dụng
Đáp án đúng: B

17. Một domain service thường phù hợp khi nào?
A. Mọi thay đổi thuộc tính đơn giản của một entity
B. Mọi truy vấn lấy dữ liệu theo khóa chính từ repository
C. Hành vi nghiệp vụ không thuộc tự nhiên về một entity
D. Mọi tác vụ biến đổi JSON đầu vào sang DTO
Đáp án đúng: C

18. Vì sao domain model không nên phụ thuộc chặt vào bảng lưu trữ?
A. Khái niệm nghiệp vụ có thể thay đổi độc lập với schema
B. Vì database không thể chứa các mối quan hệ nghiệp vụ
C. Vì entity không bao giờ có thuộc tính được lưu trữ
D. Vì mọi quy tắc đều phải được triển khai tại controller
Đáp án đúng: A

19. Khi đặt tên quan hệ nghiệp vụ, lựa chọn nào phản ánh miền rõ nhất?
A. `Invoice` nối `Order` chỉ vì có foreign key kỹ thuật
B. `Invoice` luôn thuộc mọi entity qua bảng join chung
C. `Invoice` chỉ là trường JSON trong mọi DTO phản hồi
D. `Invoice` thuộc `Order` theo quy tắc xuất hóa đơn
Đáp án đúng: D

20. Khi chuyên gia thay đổi định nghĩa 'đơn hoàn tất', nhóm nên xử lý gì?
A. Cập nhật thuật ngữ, invariant và ca kiểm thử liên quan
B. Chỉ đổi nhãn giao diện mà giữ mọi quy tắc cũ
C. Chỉ đổi cấu hình CI để build lại mã nguồn hiện tại
D. Giữ định nghĩa cũ vì entity đã có schema ổn định
Đáp án đúng: A

21. Ví dụ nào cho thấy cần phân biệt identity với equality theo giá trị?
A. Hai Money cùng amount và currency luôn khác vì tạo hai lần
B. Hai DateRange có cùng đầu cuối phải có hai ID riêng
C. Hai Address bằng nhau luôn là cùng một entity suốt đời
D. Hai Customer trùng tên vẫn khác nhau theo customerId
Đáp án đúng: D

22. Khi khám phá quy trình hoàn tiền, cách nào giúp lộ invariant bị ẩn?
A. Chỉ vẽ màn hình happy path từ tài liệu thiết kế
B. Chỉ xem cấu trúc bảng mà không hỏi ca nghiệp vụ
C. Hỏi ví dụ thất bại, ngoại lệ và điểm không thể đổi
D. Chỉ thống kê số lần gọi endpoint hoàn tiền mỗi ngày
Đáp án đúng: C

23. Khi một aggregate quá lớn khiến mọi thao tác cùng tranh chấp, hướng xem xét nào hợp lý?
A. Thêm nhiều getter để bỏ qua mọi giới hạn giao dịch
B. Chuyển toàn bộ entity trong aggregate thành singleton
C. Đánh giá lại ranh giới và invariant cần atomic thật sự
D. Cho phép thay đổi trực tiếp từ UI để giảm thời gian khóa
Đáp án đúng: C

24. Dấu hiệu nào cho thấy mô hình miền cần được cải tiến theo thời gian?
A. Quy tắc mới tạo nhiều ngoại lệ khó giải thích bằng mô hình
B. Số lượng file source đã được formatter cập nhật gần đây
C. Thời gian khởi động IDE của lập trình viên tăng lên
D. Tên repository Git được thay đổi theo phiên bản sản phẩm
Đáp án đúng: A
