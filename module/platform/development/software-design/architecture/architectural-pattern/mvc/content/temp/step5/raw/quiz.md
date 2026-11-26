Câu 1: Trong MVC, Controller chịu trách nhiệm chính nào khi nhận request web?
A. Thực thi trực tiếp mọi truy vấn JDBC trong view
B. Lưu toàn bộ dữ liệu phiên vào domain entity tĩnh
C. Render template mà không cần chọn hành vi nghiệp vụ
D. Nhận input và chuyển xử lý cho model/service phù hợp
Đáp án đúng: D

Câu 2: Trong MVC, Model thường đại diện cho phần nào?
A. Hình thức hiển thị HTML của từng trang cụ thể
B. Trạng thái và dữ liệu gắn với nghiệp vụ ứng dụng
C. Lớp lắng nghe HTTP và quyết định route URL
D. Quy tắc CSS được dùng cho các nút giao diện
Đáp án đúng: B

Câu 3: Trong MVC, View có vai trò gì với dữ liệu từ Model?
A. Tự quyết định transaction trong cơ sở dữ liệu
B. Trình bày dữ liệu theo cấu trúc giao diện
C. Kiểm tra trực tiếp mật khẩu với backend LDAP
D. Chứa toàn bộ nghiệp vụ duyệt yêu cầu thanh toán
Đáp án đúng: B

Câu 4: Trong ứng dụng MVC web, luồng xử lý request thông thường là gì?
A. View gọi thẳng SQL, tạo Controller rồi mới định tuyến
B. Model xử lý HTTP socket trước khi lập request mapping
C. Router tới Controller, xử lý Model, rồi chọn View
D. Database tự render View trước khi Controller chạy
Đáp án đúng: C

Câu 5: Khi request GET /orders/42 đến, ai nên trích ID và gọi nghiệp vụ đọc đơn?
A. Template view tạo transaction và đọc dữ liệu trực tiếp
B. Entity domain phân tích HTTP header và path servlet
C. Controller lấy path ID rồi gọi application/service
D. Bộ chuyển JSON thực thi lệnh JDBC thay Controller
Đáp án đúng: C

Câu 6: Trong Spring MVC, @Controller thường được dùng cho tình huống nào?
A. Xử lý request và chọn view để render
B. Đánh dấu mọi class JPA là persistent entity
C. Tự chuyển toàn bộ SQL thành REST endpoint
D. Khởi tạo từng connection pool theo request
Đáp án đúng: A

Câu 7: Trong Spring, @RestController khác @Controller thường ở điểm nào?
A. Mọi method bắt buộc trả tên template để render
B. Tự bật CSRF protection không cần cấu hình security
C. Mọi method chạy trong transaction chỉ đọc mặc định
D. Method trả dữ liệu làm response body theo mặc định
Đáp án đúng: D

Câu 8: Với API POST nhận JSON vào DTO, annotation Spring nào thường dùng?
A. @PathVariable để ánh xạ nội dung HTTP body
B. @RequestParam để ánh xạ nội dung HTTP body
C. @ResponseStatus để ánh xạ nội dung HTTP body
D. @RequestBody để ánh xạ nội dung HTTP body
Đáp án đúng: D

Câu 9: Khi HTML form gửi dữ liệu qua name/value, cách binding nào phù hợp trong Spring MVC?
A. @ResponseBody để bind form vào đối tượng dữ liệu
B. @ExceptionHandler để bind form vào đối tượng dữ liệu
C. @ModelAttribute để bind form vào đối tượng dữ liệu
D. @PathVariable để bind form vào đối tượng dữ liệu
Đáp án đúng: C

Câu 10: Muốn đọc orderId từ đường dẫn /orders/{orderId}, dùng annotation nào?
A. @RequestHeader để nhận phần biến của URL path
B. @RequestBody để nhận phần biến của URL path
C. @CookieValue để nhận phần biến của URL path
D. @PathVariable để nhận phần biến của URL path
Đáp án đúng: D

Câu 11: Khi cần lọc danh sách bằng ?status=OPEN, Controller có thể dùng gì?
A. @PathVariable để lấy status từ query string
B. @RequestBody để lấy status từ query string
C. @RequestParam để lấy status từ query string
D. @SessionAttribute để lấy status từ query string
Đáp án đúng: C

Câu 12: Trong form validation của Spring MVC, @Valid và BindingResult giúp gì?
A. Validate dữ liệu rồi đọc lỗi để phản hồi form
B. Luôn ghi form vào database trước khi kiểm lỗi
C. Tự bỏ mọi ràng buộc nghiệp vụ sau khi parse
D. Biến mọi lỗi nhập liệu thành HTTP 500 mặc định
Đáp án đúng: A

Câu 13: Vì sao BindingResult thường đặt ngay sau tham số được validate?
A. Spring gắn kết quả lỗi vào đúng đối tượng binding
B. Để JVM tự chuyển form thành transaction read-only
C. Để view template chạy trước bước xác thực quyền
D. Để validation bị bỏ qua nếu handler không gọi view
Đáp án đúng: A

Câu 14: Post/Redirect/Get thường giải quyết vấn đề thực tế nào?
A. Đảm bảo mọi POST trở thành idempotent ở database
B. Tránh gửi lại POST khi người dùng refresh trang
C. Bỏ hoàn toàn nhu cầu kiểm tra dữ liệu trước lưu
D. Giữ nguyên request body trong mọi redirect của browser
Đáp án đúng: B

Câu 15: Khi Controller tạo model attribute orderSummary cho template, nguyên tắc nào đúng?
A. View nên gọi repository để hoàn thiện dữ liệu còn thiếu
B. View nên quyết định luật hoàn tiền từ biến input
C. View nên tự commit đơn trước khi hiển thị HTML
D. View đọc dữ liệu trình bày, không tự truy cập DB
Đáp án đúng: D

Câu 16: Vì sao nên tách request DTO khỏi JPA entity khi xử lý form nhạy cảm?
A. Để request tự đi thẳng qua repository không cần service
B. Để view bắt buộc dùng cùng schema với database
C. Giới hạn trường có thể bind và tránh lộ nội bộ
D. Để Jackson luôn nhận mọi field client tự gửi
Đáp án đúng: C

Câu 17: Mass assignment xảy ra trong web MVC khi nào?
A. Bind dữ liệu client vào field không được phép sửa
B. Lỗi xảy ra chỉ vì controller có hai URL mapping
C. Lỗi chỉ phát sinh do dùng hai view template khác nhau
D. Lỗi xảy ra khi response thiếu header Content-Type
Đáp án đúng: A

Câu 18: Trong Spring MVC, @ControllerAdvice hỗ trợ tình huống nào?
A. Tự map mọi bảng cơ sở dữ liệu thành form HTML
B. Xử lý lỗi dùng chung cho nhiều controller
C. Tự render tất cả template dù không có route
D. Tự thêm transaction vào mọi domain entity
Đáp án đúng: B

Câu 19: Khi resource không tồn tại, response API MVC nên được ánh xạ như thế nào?
A. Trả 404 và cấu trúc lỗi nhất quán với API
B. Trả 200 kèm object trống trong mọi trường hợp
C. Trả 500 vì không tìm thấy dữ liệu luôn là lỗi server
D. Trả 201 và URL mới để người dùng tạo resource
Đáp án đúng: A

Câu 20: Request có token hợp lệ nhưng thiếu quyền xem đơn, response thường là gì?
A. 401 Unauthorized vì token hợp lệ nhưng thiếu role
B. 403 Forbidden cho trường hợp thiếu phân quyền
C. 404 Not Found bắt buộc cho mọi lỗi phân quyền
D. 302 Found bắt buộc với mọi API có access token
Đáp án đúng: B

Câu 21: Với form web dùng cookie session, CSRF token có tác dụng gì?
A. Thay hoàn toàn xác thực tài khoản bằng cookie
B. Bảo vệ mọi trường dữ liệu khỏi SQL injection
C. Mã hóa toàn bộ response body của trình duyệt
D. Giảm nguy cơ request giả mạo từ trang khác
Đáp án đúng: D

Câu 22: Để giảm XSS khi render giá trị người dùng trong HTML, nên làm gì?
A. Tắt hoàn toàn mọi bước validate form ở controller
B. Đưa HTML đầu vào vào template dưới dạng raw
C. Escape dữ liệu theo ngữ cảnh output của view
D. Ghi dữ liệu input trực tiếp vào thuộc tính script
Đáp án đúng: C

Câu 23: Trong MVC, trạng thái đăng nhập qua session nên quản lý thế nào?
A. Lưu userId hiện tại vào field singleton controller
B. Lưu mỗi token vào biến static dùng chung mọi request
C. Trộn session vào domain entity dùng lại giữa người dùng
D. Giữ session ở cơ chế phù hợp, không ở field Controller
Đáp án đúng: D

Câu 24: Vì sao controller Spring nên tránh field mutable chứa dữ liệu theo request?
A. Instance có thể dùng chung giữa nhiều request đồng thời
B. Vì controller luôn bị JVM tạo mới mỗi lần gọi
C. Vì mỗi HTTP request có một bean controller riêng
D. Vì Spring tự biến mọi field thành thread-local
Đáp án đúng: A

Câu 25: Khi thiết kế Model cho View, điều nào giúp giảm phụ thuộc giao diện vào persistence?
A. Dùng view model chỉ chứa dữ liệu cần hiển thị
B. Truyền thẳng EntityManager để view tự query
C. Truyền Hibernate Session làm thuộc tính template
D. Truyền toàn bộ JPA entity graph bất kể nhu cầu
Đáp án đúng: A

Câu 26: Khi kiểm tra Controller trả JSON và status trong Spring MVC, công cụ nào phù hợp?
A. JUnit chỉ so sánh hashCode của Controller class
B. MockMvc gọi handler và assert HTTP response
C. JPA EntityManager chỉ kiểm tra persistence mapping
D. JMH chỉ đo thời gian của method xử lý
Đáp án đúng: B

Câu 27: Trong Spring Boot, @WebMvcTest thường phù hợp để kiểm tra gì?
A. Toàn bộ workflow thật qua database và các service ngoài
B. Một phần web layer với dependency được mock cần thiết
C. Hiệu năng của tất cả endpoint ở tải production
D. Toàn bộ persistence mapping của mọi entity trong app
Đáp án đúng: B

Câu 28: Một phép thử MVC đủ chặt khi form không hợp lệ cần khẳng định gì?
A. Chỉ xác nhận route tồn tại mà không xem kết quả
B. Chỉ xác nhận form có nút submit trên HTML
C. Lỗi validation, response/view và không gọi xử lý lưu
D. Chỉ kiểm tra connection pool không báo timeout
Đáp án đúng: C
